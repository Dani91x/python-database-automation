"""postino.py - il postino verso il cloud (W1-G1, implementa ``Postino``).

Scopo
    Portare al cloud, DOPO la decisione e fuori dal ciclo, ogni riga che
    l'archivio locale ha in coda: la outbox dei due file SQLite (``denaro`` e
    ``vivo``) e i file JSONL dei log (letti a offset). Ordine dell'utente: il
    cloud non perde NESSUN dato rispetto a oggi (stessa tabella, stesse
    colonne, senza doppioni); cio' che non si puo' consegnare resta in coda con
    un allarme, MAI scartato in silenzio.

Come consegna
    UNA RPC generica del cloud, ``postino_consegna`` (migrazione
    ``migrations/architettura_uid_ombra_2026-10-09.sql``), chiamata con il
    protocollo ``Cloud.rpc`` (il client unico di W1-G2): per ogni riga
      * ``insert`` -> ``INSERT ... ON CONFLICT (chiave naturale) DO NOTHING``
        (log con ``uid``: il ritento non duplica);
      * ``upsert`` -> ``ON CONFLICT ... DO UPDATE ... WHERE excluded.rev > t.rev``
        quando la tabella ha ``rev_colonna``: una riga vecchia arrivata tardi
        non riporta MAI indietro il cloud (R02);
      * ``patch``/``delete`` per chiave naturale, con la stessa regola di versione.
    La RPC risponde con un esito PER RIGA (``ok`` | ``ignorata`` | ``errore`` con
    SQLSTATE): una riga guasta non ferma le altre del blocco.

Regole sugli errori
    * errore di rete/gateway su tutta la chiamata (``db_client.classifica_guasto_rete``,
      riuso) -> OFFLINE: niente si muove, attese 2-4-8-16-32 s con tetto 60 s
      (G par. 4.2), evento ``dati.postino_offline(da)`` una volta, la coda cresce;
    * 57014 su tutta la chiamata -> il blocco di quella tabella si dimezza (come
      ``stream/db.py`` fa oggi), poi si riprova;
    * altro errore su tutta la chiamata (RPC assente, permessi, colonna di
      conflitto senza indice unico...) -> la TABELLA e' ``bloccata``: righe ferme in
      coda, evento ``dati.postino_bloccato``; MAI dead_letter (non e' colpa della riga);
    * esito per riga 23503 (chiave esterna) e gli altri SQLSTATE transitori ->
      ritento con tetto (R06), poi ``dead_letter`` con allarme;
    * qualunque altro errore per riga (CHECK 23514, NOT NULL 23502, tipo 22P02,
      colonna sconosciuta 42703...) -> ``dead_letter`` subito, evento
      ``dati.dead_letter(tabella, riga, errore)``: mai un warning (PSB par. 7 n.18).
    Ordine padre -> figlio da ``SpecTabella.dipende_da``: in un giro le tabelle
    padre partono prima; se un padre non e' andato a buon fine, i figli
    aspettano il giro dopo.

Disco
    ``tetto_disco_mb``: oltre il tetto, evento ``dati.tetto_disco`` e
    ``ripiego_diretto`` vero: il SEGNALE esplicito per l'aggancio dell'ondata 2
    di tornare alla scrittura diretta di oggi (con lo stesso ``uid``/``rev``:
    nessun doppione quando il postino recupera). L'archivio NON smette di
    scrivere: niente si perde.

Ombra
    ``ombra=True`` -> ogni riga va su ``<tabella>_ombra`` (stessa forma, creata
    dalla migrazione): mai due scrittori sulle chiavi del vecchio (R02, R21).

Cosa NON fa
    Nessun thread all'import; il thread ``postino`` nasce solo con ``avvia()``.
    Non legge mai le tabelle per decidere; non tocca la strategia.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from .archivio import REGIME_SERVIZIO, REGIMI_SQLITE, ArchivioLocale, Eventi, VoceOutbox, _eventi_nel_log
from .contratto import (Cloud, EsitoDrenaggio, Operazione, RapportoRiconciliazione, SpecTabella,
                        StatoPostino)
from .schema_locale import chiave_canonica, giorno_utc, leggi_riga_log, tabella_della_riga_log

logger = logging.getLogger(__name__)

RPC_CONSEGNA = "postino_consegna"
#: SQLSTATE per riga che passano ritentando (con tetto): chiave esterna (R06),
#: serializzazione, stallo, lock, connessioni, database in arresto
TRANSITORI_RIGA = frozenset({"23503", "40001", "40P01", "55P03", "53300", "57P01", "57P03"})
#: SQLSTATE per riga che NON sono colpa della riga (permessi): la tabella si blocca,
#: le righe restano in coda (mai dead_letter)
BLOCCANTI_RIGA = frozenset({"42501"})
TETTO_TENTATIVI_RIGA = 12
TETTO_ATTESA_S = 60.0
ATTESE_PREDEFINITE_S: Tuple[float, ...] = (2.0, 4.0, 8.0, 16.0, 32.0)   # G par. 4.2 = db_client.ATTESE_RETE_S
BLOCCO_PREDEFINITO = 200
LETTURA_LOG_BYTE = 1_048_576


def _attese_rete() -> Tuple[float, ...]:
    """Riuso delle attese di ``db_client`` (import pigro: ``config`` legge l'ambiente)."""
    try:
        from db_client import ATTESE_RETE_S
        return tuple(ATTESE_RETE_S)
    except Exception as exc:  # fuori dal repo (test isolati): le stesse attese, dichiarate
        logger.debug("[postino] db_client non importabile (%s): attese predefinite", exc)
        return ATTESE_PREDEFINITE_S


def classifica_errore_chiamata(exc: BaseException) -> str:
    """'rete' | 'statement_timeout' | 'bloccante' per un errore su TUTTA la chiamata.

    La classe di rete viene da ``db_client.classifica_guasto_rete`` (riuso, nessuna
    copia): 5xx/HTML del gateway, connessione terminata, timeout, connessione."""
    codice = str(getattr(exc, "code", "") or "")
    messaggio = str(getattr(exc, "message", "") or exc)
    if codice == "57014" or "statement timeout" in messaggio.lower():
        return "statement_timeout"
    try:
        from db_client import classifica_guasto_rete
    except Exception as imp:  # senza il classificatore vero non si inventa: si blocca e si dice
        logger.error("[postino] classifica_guasto_rete non importabile: %s", imp)
        return "bloccante"
    return "rete" if classifica_guasto_rete(exc) is not None else "bloccante"


def _attesa(tentativi: int, attese: Sequence[float]) -> float:
    if tentativi <= 0:
        return 0.0
    return min(TETTO_ATTESA_S, attese[min(tentativi, len(attese)) - 1] if tentativi <= len(attese) else TETTO_ATTESA_S)


@dataclass
class _Voce:
    """Una riga da consegnare, da outbox o da file di log."""

    tabella: str
    op: str
    chiave: Optional[str]
    testo: str
    creato_ms: int
    tentativi: int
    regime: Optional[str] = None       # outbox: regime del file
    seq: Optional[int] = None          # outbox: seq
    file: Optional[str] = None         # log: nome del file


@dataclass
class _Giro:
    consegnate: int = 0
    ritentate: int = 0
    morte: int = 0
    errore: Optional[str] = None
    interrotto: bool = False
    fallite: Set[str] = field(default_factory=set)
    # esiti per fonte
    ok_seq: Dict[str, List[int]] = field(default_factory=dict)
    rimandate: Dict[str, List[Tuple[int, int, int, str]]] = field(default_factory=dict)
    morte_seq: Dict[str, List[Tuple[int, str, str, int]]] = field(default_factory=dict)
    log_morte: Dict[str, List[Tuple[str, str, str, str, int, str, str, int]]] = field(default_factory=dict)
    log_ritenti: Dict[str, List[Tuple[str, str, str, str, int, int, int, str]]] = field(default_factory=dict)


class PostinoLocale:
    """Implementazione di ``contratto.Postino`` sopra ``ArchivioLocale`` e un ``Cloud``."""

    def __init__(self, archivio: ArchivioLocale, cloud: Cloud, *, ombra: bool = False,
                 eventi: Optional[Eventi] = None, tetto_disco_mb: float = 2048.0,
                 tetto_tentativi_riga: int = TETTO_TENTATIVI_RIGA, blocco: int = BLOCCO_PREDEFINITO,
                 orologio_ms: Optional[Callable[[], int]] = None,
                 riconciliatore: Optional[Any] = None) -> None:
        self.archivio = archivio
        self.cloud = cloud
        self.ombra = bool(ombra)
        self._eventi = eventi or _eventi_nel_log
        self._tetto_disco = int(tetto_disco_mb * 1_048_576)
        self._tetto_riga = int(tetto_tentativi_riga)
        self._blocco = max(1, int(blocco))
        self._blocco_tabella: Dict[str, int] = {}
        self._ora_ms = orologio_ms or (lambda: time.time_ns() // 1_000_000)
        self._attese = _attese_rete()
        self._lock = threading.Lock()                # un giro alla volta
        self._guasti_di_fila = 0
        self._prossimo_giro_ms = 0
        self._bloccate: Dict[str, Tuple[int, int, str]] = {}   # tabella -> (prossimo_ms, tentativi, errore)
        self.offline_da: Optional[datetime] = None
        self.ultimo_errore: Optional[str] = None
        self.ripiego_diretto = False
        self.contatori: Counter[str] = Counter()
        self._riconciliatore = riconciliatore
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ contratto Postino
    def destinazione(self, tabella: str) -> str:
        return f"{tabella}_ombra" if self.ombra else tabella

    def accoda(self, tabella: str, op: Operazione, chiave: Optional[str], riga: Mapping[str, Any], *,
               coalesce: bool = False) -> int:
        """Forma sincrona: riga locale + outbox nella stessa transazione, ritorna il seq."""
        return self.archivio.accoda(tabella, op, chiave, riga, coalesce=coalesce)

    def stato(self) -> StatoPostino:
        adesso = self._ora_ms()
        per: Counter[str] = Counter()
        vecchio: Optional[int] = None
        morti = 0
        for regime in REGIMI_SQLITE:
            p, v, m = self.archivio.conteggi_outbox(regime)
            per.update(p)
            morti += m
            if v is not None:
                vecchio = v if vecchio is None else min(vecchio, v)
        for percorso in self.archivio.file_log():
            p, v = self._conta_log(percorso)
            per.update(p)
            if v is not None:
                vecchio = v if vecchio is None else min(vecchio, v)
        self._controlla_disco()
        return StatoPostino(in_coda=sum(per.values()),
                            eta_max_s=None if vecchio is None else max(0.0, (adesso - vecchio) / 1000.0),
                            per_tabella=dict(per), ultimo_errore=self.ultimo_errore, offline_da=self.offline_da,
                            dead_letter=morti)

    def drena(self, max_righe: int = 200) -> EsitoDrenaggio:
        """UN giro: raccoglie fino a ``max_righe`` righe pronte e le consegna."""
        with self._lock:
            adesso = self._ora_ms()
            if adesso < self._prossimo_giro_ms:
                return EsitoDrenaggio(0, 0, 0, f"in attesa ({(self._prossimo_giro_ms - adesso) / 1000.0:.1f} s): "
                                               f"{self.ultimo_errore}")
            voci = self._raccogli(max(1, int(max_righe)), adesso)
            giro = _Giro()
            for tabella, op, gruppo in self._ordina(voci):
                if giro.interrotto:
                    break
                spec = self.archivio.spec(tabella)
                if any(p in giro.fallite for p in spec.dipende_da):
                    self._rimanda_senza_contare(gruppo, giro, adesso, "padre non ancora consegnato")
                    giro.fallite.add(tabella)
                    continue
                bloc = self._bloccate.get(tabella)
                if bloc is not None and adesso < bloc[0]:
                    self._rimanda_senza_contare(gruppo, giro, bloc[0], f"tabella bloccata: {bloc[2]}")
                    giro.fallite.add(tabella)
                    continue
                self._consegna_gruppo(spec, op, gruppo, giro, adesso)
            self._chiudi_giro(voci, giro)
            self._controlla_disco()
            return EsitoDrenaggio(giro.consegnate, giro.ritentate, giro.morte, giro.errore)

    def riconcilia(self, tabella: str, da_ts: datetime) -> RapportoRiconciliazione:
        """Confronto locale contro cloud da ``da_ts`` (vedi ``riconcilia.py``)."""
        rapporto = self._riconciliatore_pronto().confronta(tabella, da_ts)
        self._evento("dati.riconciliazione", {"tabella": tabella, "da": da_ts.isoformat(),
                                              "mancanti": len(rapporto.mancanti_nel_cloud),
                                              "in_piu": len(rapporto.in_piu_nel_cloud),
                                              "diverse": len(rapporto.diverse)})
        return rapporto

    # ------------------------------------------------------------------ thread (facoltativo)
    def avvia(self, intervallo_s: float = 1.0, max_righe: int = 200) -> None:
        """Thread ``postino``: drena finche' c'e' lavoro, poi dorme ``intervallo_s``."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()

        def ciclo() -> None:
            while not self._stop.is_set():
                try:
                    esito = self.drena(max_righe)
                    pieno = esito.consegnate + esito.dead_letter >= max_righe and esito.errore is None
                except Exception as exc:  # un giro guasto si vede e si riprova, il thread non muore
                    logger.error("[postino] giro fallito: %s", exc)
                    self.ultimo_errore = f"giro: {exc}"[:300]
                    pieno = False
                if not pieno:
                    self._stop.wait(intervallo_s)

        self._thread = threading.Thread(target=ciclo, name="postino", daemon=True)
        self._thread.start()

    def ferma(self, timeout_s: float = 10.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout_s)
            self._thread = None

    # ------------------------------------------------------------------ raccolta
    def _raccogli(self, max_righe: int, adesso: int) -> List[_Voce]:
        voci: List[_Voce] = []
        for regime in REGIMI_SQLITE:
            for v in self.archivio.outbox_pronta(regime, adesso, max_righe - len(voci)):
                voci.append(self._da_outbox(v))
            if len(voci) >= max_righe:
                return voci
        for percorso in self.archivio.file_log():
            if len(voci) >= max_righe:
                break
            voci.extend(self._leggi_log(percorso, max_righe - len(voci)))
        return voci

    @staticmethod
    def _da_outbox(v: VoceOutbox) -> _Voce:
        return _Voce(v.tabella, v.op, v.chiave, v.testo, v.creato_ms, v.tentativi, regime=v.regime, seq=v.seq)

    def _leggi_log(self, percorso: Path, quante: int) -> List[_Voce]:
        """Righe COMPLETE dopo il marcatore; una riga guasta si segnala e si salta."""
        offset = self.archivio.offset_log(percorso.name)
        voci: List[_Voce] = []
        with open(percorso, "rb") as f:
            f.seek(offset)
            dati = f.read(LETTURA_LOG_BYTE)
        pos = offset
        for linea in dati.splitlines(keepends=True):
            if not linea.endswith(b"\n") or len(voci) >= quante:
                break                                     # riga in scrittura o quota piena
            fine = pos + len(linea)
            try:
                tabella, op, ms, riga = leggi_riga_log(linea.decode("ascii"))
                spec = self.archivio.spec(tabella)
                voci.append(_Voce(tabella, op, chiave_canonica(spec, riga),
                                  json.dumps(riga, ensure_ascii=False, separators=(",", ":")), ms, 0,
                                  file=percorso.name, seq=fine))
            except (ValueError, KeyError, UnicodeDecodeError) as exc:
                dettagli = {"file": percorso.name, "offset": pos, "errore": str(exc)[:200],
                            "anteprima": linea[:200].decode("ascii", "replace")}
                self.contatori["righe_log_guaste"] += 1
                self.archivio.segnala("riga_log_guasta", dettagli)
                self._evento("dati.riga_troncata", dettagli)
                voci.append(_Voce("", "salta", None, "", 0, 0, file=percorso.name, seq=fine))
            pos = fine
        return voci

    def _conta_log(self, percorso: Path) -> Tuple[Counter[str], Optional[int]]:
        per: Counter[str] = Counter()
        primo: Optional[int] = None
        offset = self.archivio.offset_log(percorso.name)
        try:
            with open(percorso, "rb") as f:
                f.seek(offset)
                for linea in f:
                    if not linea.endswith(b"\n"):
                        break
                    testo = linea.decode("ascii", "replace")
                    t = tabella_della_riga_log(testo)
                    if t:
                        per[t] += 1
                        if primo is None:
                            try:
                                primo = leggi_riga_log(testo)[2]
                            except (ValueError, KeyError):
                                primo = None
        except FileNotFoundError:
            pass
        return per, primo

    def _ordina(self, voci: Sequence[_Voce]) -> List[Tuple[str, str, List[_Voce]]]:
        """Gruppi = corse consecutive (tabella, op) nell'ordine di arrivo; tabelle padre prima."""
        per_tabella: Dict[str, List[_Voce]] = {}
        for v in voci:
            if v.op != "salta":
                per_tabella.setdefault(v.tabella, []).append(v)
        profondita = {t: self._profondita(t, set()) for t in per_tabella}
        gruppi: List[Tuple[str, str, List[_Voce]]] = []
        for tabella in sorted(per_tabella, key=lambda t: profondita[t]):
            corsa: List[_Voce] = []
            for v in per_tabella[tabella]:
                if corsa and corsa[-1].op != v.op:
                    gruppi.append((tabella, corsa[0].op, corsa))
                    corsa = []
                corsa.append(v)
            if corsa:
                gruppi.append((tabella, corsa[0].op, corsa))
        return gruppi

    def _profondita(self, tabella: str, visti: Set[str]) -> int:
        if tabella in visti:
            return 0                                        # ciclo dichiarato: nessun ordine imposto
        try:
            padri = self.archivio.spec(tabella).dipende_da
        except KeyError:
            return 0
        return 1 + max((self._profondita(p, visti | {tabella}) for p in padri), default=-1)

    # ------------------------------------------------------------------ consegna
    def _consegna_gruppo(self, spec: SpecTabella, op: str, gruppo: List[_Voce], giro: _Giro, adesso: int) -> None:
        i = 0
        while i < len(gruppo):
            if giro.interrotto:
                return
            n = self._blocco_tabella.get(spec.nome, self._blocco)
            pezzo = gruppo[i:i + n]
            argomenti = {"p_tabella": self.destinazione(spec.nome), "p_op": op,
                         "p_conflitto": list(spec.chiave_naturale), "p_rev": spec.rev_colonna,
                         "p_righe": [json.loads(v.testo) for v in pezzo]}
            try:
                esiti = self.cloud.rpc(RPC_CONSEGNA, argomenti)
                if not isinstance(esiti, list) or len(esiti) != len(pezzo):
                    raise ValueError(f"risposta inattesa di {RPC_CONSEGNA}: {str(esiti)[:200]}")
            except Exception as exc:
                self._errore_chiamata(spec, pezzo, exc, giro, adesso)
                if not giro.interrotto:
                    bloc = self._bloccate.get(spec.nome)
                    pronta = bloc[0] if bloc is not None else adesso
                    for v in gruppo[i + len(pezzo):]:
                        self._rimanda(v, giro, pronta, "tabella ferma in questo giro", contare=False)
                    giro.fallite.add(spec.nome)
                return
            self._in_linea()
            self._bloccate.pop(spec.nome, None)
            for v, esito in zip(pezzo, esiti):
                self._esito_riga(spec, v, esito, giro, adesso)
            i += len(pezzo)

    def _esito_riga(self, spec: SpecTabella, v: _Voce, esito: Any, giro: _Giro, adesso: int) -> None:
        tipo = esito.get("esito") if isinstance(esito, dict) else None
        if tipo in ("ok", "ignorata"):
            giro.consegnate += 1
            self.contatori["consegnate" if tipo == "ok" else "ignorate"] += 1
            if v.file is None and v.regime is not None and v.seq is not None:
                giro.ok_seq.setdefault(v.regime, []).append(v.seq)
            return
        codice = str((esito or {}).get("codice") or "") if isinstance(esito, dict) else ""
        messaggio = str((esito or {}).get("messaggio") or esito) if isinstance(esito, dict) else str(esito)
        errore = f"{codice} {messaggio}".strip()[:500]
        giro.fallite.add(spec.nome)
        if codice in BLOCCANTI_RIGA:
            self._blocca(spec, errore, 1, adesso)
            self._rimanda(v, giro, self._bloccate[spec.nome][0], errore, contare=False)
            return
        if codice in TRANSITORI_RIGA and v.tentativi + 1 < self._tetto_riga:
            self._rimanda(v, giro, adesso, errore, contare=True)
            return
        self._morta(v, codice or "risposta", errore, giro)

    def _errore_chiamata(self, spec: SpecTabella, pezzo: List[_Voce], exc: BaseException, giro: _Giro,
                         adesso: int) -> None:
        classe = classifica_errore_chiamata(exc)
        descr = f"{type(exc).__name__}: {getattr(exc, 'code', '') or ''} {getattr(exc, 'message', '') or exc}"[:300]
        self.ultimo_errore = f"{spec.nome}: {descr}"
        if classe == "rete":
            self._guasti_di_fila += 1
            attesa = _attesa(self._guasti_di_fila, self._attese)
            self._prossimo_giro_ms = adesso + int(attesa * 1000)
            if self.offline_da is None:
                self.offline_da = datetime.fromtimestamp(adesso / 1000.0, tz=timezone.utc)
                self._evento("dati.postino_offline", {"da": self.offline_da.isoformat(), "errore": descr})
            self.contatori["guasti_rete"] += 1
            giro.errore = f"offline: {descr}"
            giro.interrotto = True                          # niente si muove: si riprova tutto dopo l'attesa
            return
        if classe == "statement_timeout":
            nuovo = max(1, len(pezzo) // 2)
            self._blocco_tabella[spec.nome] = nuovo
            self.contatori["blocchi_dimezzati"] += 1
            giro.errore = f"57014 su {spec.nome}: blocco ridotto a {nuovo}"
            for v in pezzo:
                self._rimanda(v, giro, adesso, "57014: blocco ridotto", contare=False)
            return
        self._blocca(spec, descr, len(pezzo), adesso)
        giro.errore = f"bloccata {spec.nome}: {descr}"
        for v in pezzo:
            self._rimanda(v, giro, self._bloccate[spec.nome][0], descr, contare=False)

    def _blocca(self, spec: SpecTabella, descr: str, righe: int, adesso: int) -> None:
        """La tabella si ferma (attesa crescente, tetto 60 s): righe in coda, allarme visibile."""
        prec = self._bloccate.get(spec.nome)
        if prec is not None and prec[0] > adesso:
            return                                          # gia' bloccata in questo giro
        tentativi = (prec[1] if prec else 0) + 1
        self._bloccate[spec.nome] = (adesso + int(_attesa(tentativi, self._attese) * 1000), tentativi, descr)
        self.contatori["tabelle_bloccate"] += 1
        self.ultimo_errore = f"{spec.nome}: {descr}"
        self._evento("dati.postino_bloccato", {"tabella": spec.nome, "destinazione": self.destinazione(spec.nome),
                                               "errore": descr, "righe_ferme": righe})

    def _in_linea(self) -> None:
        if self.offline_da is not None:
            self._evento("dati.postino_online", {"offline_da": self.offline_da.isoformat()})
        self.offline_da = None
        self._guasti_di_fila = 0
        self._prossimo_giro_ms = 0

    # ------------------------------------------------------------------ esiti verso l'archivio
    def _rimanda(self, v: _Voce, giro: _Giro, adesso: int, errore: str, *, contare: bool) -> None:
        """``contare``: ritento vero (tentativi+1, attesa crescente). Altrimenti la riga
        torna pronta all'istante ``adesso`` passato (es. fine del blocco della tabella)."""
        tentativi = v.tentativi + (1 if contare else 0)
        prossimo = adesso + int(_attesa(max(1, tentativi), self._attese) * 1000) if contare else adesso
        if contare:
            giro.ritentate += 1
            self.contatori["ritentate"] += 1
        if v.file is not None:
            giro.log_ritenti.setdefault(v.file, []).append(
                (v.tabella, v.op, v.chiave or "", v.testo, v.creato_ms, tentativi, prossimo, errore))
        elif v.regime is not None and v.seq is not None:
            giro.rimandate.setdefault(v.regime, []).append((v.seq, tentativi, prossimo, errore))

    def _rimanda_senza_contare(self, gruppo: List[_Voce], giro: _Giro, adesso: int, errore: str) -> None:
        for v in gruppo:
            self._rimanda(v, giro, adesso, errore, contare=False)

    def _morta(self, v: _Voce, codice: str, errore: str, giro: _Giro) -> None:
        giro.morte += 1
        self.contatori["dead_letter"] += 1
        if v.file is not None:
            giro.log_morte.setdefault(v.file, []).append(
                (v.tabella, v.op, v.chiave or "", v.testo, v.creato_ms, codice, errore, v.tentativi + 1))
        elif v.regime is not None and v.seq is not None:
            giro.morte_seq.setdefault(v.regime, []).append((v.seq, codice, errore, v.tentativi + 1))
        self._evento("dati.dead_letter", {"tabella": v.tabella, "destinazione": self.destinazione(v.tabella),
                                          "riga": json.loads(v.testo), "errore": errore})

    def _chiudi_giro(self, voci: Sequence[_Voce], giro: _Giro) -> None:
        for regime in REGIMI_SQLITE:
            ok = giro.ok_seq.get(regime, [])
            rim = [r for r in giro.rimandate.get(regime, [])]
            morte = giro.morte_seq.get(regime, [])
            if ok or rim or morte:
                self.archivio.chiudi_voci(regime, ok, rim, morte)
        if giro.interrotto:
            return                                          # offline: i file di log non avanzano
        fine_per_file: Dict[str, int] = {}
        for v in voci:
            if v.file is not None and v.seq is not None:
                fine_per_file[v.file] = max(fine_per_file.get(v.file, 0), v.seq)
        for nome, fine in fine_per_file.items():
            self.archivio.chiudi_log(nome, fine, giro.log_morte.get(nome, []), giro.log_ritenti.get(nome, []))

    # ------------------------------------------------------------------ disco, eventi, riconcilia
    def _controlla_disco(self) -> None:
        dim = self.archivio.dimensione_byte()
        if dim > self._tetto_disco and not self.ripiego_diretto:
            self.ripiego_diretto = True
            self._evento("dati.tetto_disco", {"byte": dim, "tetto": self._tetto_disco,
                                              "segnale": "ripiego alla scrittura diretta di oggi"})
        elif self.ripiego_diretto and dim < int(self._tetto_disco * 0.9):
            self.ripiego_diretto = False
            self._evento("dati.tetto_disco_rientrato", {"byte": dim, "tetto": self._tetto_disco})

    def _riconciliatore_pronto(self) -> Any:
        if self._riconciliatore is None:
            from .riconcilia import Riconciliatore
            self._riconciliatore = Riconciliatore(self.archivio, self.cloud, destinazione=self.destinazione)
        return self._riconciliatore

    def riconcilia_giorno(self, giorno: str, tabelle: Sequence[str]) -> List[RapportoRiconciliazione]:
        """Confronto notturno di un giorno UTC per ogni tabella; scrive il marcatore
        (``ok`` = nessuna differenza) che abilita la pulizia."""
        da = datetime.strptime(giorno, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        rapporti = []
        for t in tabelle:
            r = self._riconciliatore_pronto().confronta(t, da, da + timedelta(days=1))
            esito = "ok" if not (r.mancanti_nel_cloud or r.in_piu_nel_cloud or r.diverse) else "differenze"
            self.archivio.scrivi_riconciliazione(t, giorno, esito, {
                "locali": r.righe_locali, "cloud": r.righe_cloud, "mancanti": list(r.mancanti_nel_cloud[:50]),
                "in_piu": list(r.in_piu_nel_cloud[:50]), "diverse": list(r.diverse[:50])})
            self._evento("dati.riconciliazione", {"tabella": t, "giorno": giorno, "esito": esito,
                                                  "mancanti": len(r.mancanti_nel_cloud),
                                                  "in_piu": len(r.in_piu_nel_cloud), "diverse": len(r.diverse)})
            rapporti.append(r)
        return rapporti

    def _evento(self, nome: str, dati: Mapping[str, Any]) -> None:
        try:
            self._eventi(nome, dati)
        except Exception as exc:  # un ascoltatore guasto non ferma il postino, ma si vede
            logger.error("[postino] ascoltatore dell'evento %s: %s", nome, exc)


__all__ = ["PostinoLocale", "classifica_errore_chiamata", "RPC_CONSEGNA", "TRANSITORI_RIGA", "giorno_utc",
           "REGIME_SERVIZIO"]
