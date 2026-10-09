"""postino.py - il postino verso il cloud (W1-G1, implementa ``Postino``).

Scopo
    Portare al cloud, DOPO la decisione e fuori dal ciclo, ogni riga che
    l'archivio locale ha in coda: la outbox dei due file SQLite (``denaro`` e
    ``vivo``) e i file JSONL dei log (letti a offset). Ordini dell'utente: il
    cloud non perde NESSUN dato rispetto a oggi (stessa tabella, stesse
    colonne, senza doppioni); il DB locale e' invisibile e totalmente
    automatico: cio' che non si puo' consegnare resta in coda con un allarme,
    MAI scartato in silenzio, e rientra da solo.

Come consegna
    UNA RPC generica del cloud, ``postino_consegna`` (migrazione
    ``migrations/architettura_uid_ombra_2026-10-09.sql``), chiamata con il
    protocollo ``Cloud.rpc`` (il client unico di W1-G2): per ogni riga
      * ``insert`` -> ``INSERT ... ON CONFLICT (chiave naturale) DO NOTHING``
        (log con ``uid``: il ritento non duplica);
      * ``upsert`` -> ``ON CONFLICT ... DO UPDATE`` (fusione delle colonne, come oggi);
      * ``patch``/``delete`` per chiave naturale.
    VERSIONE (R1, terza revisione, "identico a oggi"): ogni voce porta la ``vseq``
    LOCALE del suo file e la chiamata l'``origine`` del file (``p_origine``,
    ``p_versioni``). Il cloud confronta le versioni SOLO fra voci della STESSA
    origine (tabella ``postino_versioni``): una voce vecchia della stessa origine
    (ritento, rientro da dead_letter) torna ``vecchia`` e non tocca la riga; fra
    origini diverse vince l'ultima arrivata, come oggi. La colonna del bot
    (``updated_at``) non decide nulla e arriva tale e quale.
    La RPC risponde con un esito PER RIGA (``ok`` | ``ignorata`` | ``vecchia`` |
    ``errore`` con SQLSTATE): una riga guasta non ferma le altre del blocco.

Regole sugli errori (revisione 09/10, A1-A4, M1, M4)
    * valore non JSON (NaN, Infinity, surrogato isolato): la riga va in dead_letter
      PRIMA della chiamata (oggi httpx la rifiuta e la riga si perde con un warning);
    * errore di rete/gateway su tutta la chiamata (``db_client.classifica_guasto_rete``,
      riuso) -> OFFLINE: niente si muove, attese 2-4-8-16-32 s con tetto 60 s;
    * 57014 su tutta la chiamata -> il blocco della tabella si dimezza;
    * errore di DATO su tutta la chiamata (classe 22/23 tranne 23503, corpo non
      valido, \\u0000 rifiutato dal jsonb) -> BISEZIONE fino alla riga singola,
      dead_letter di quella sola, le altre passano;
    * altro errore su tutta la chiamata (RPC assente, permessi, schema) -> la TABELLA
      e' bloccata (segnalata UNA volta), si ritenta piu' tardi; MAI dead_letter;
    * esito per riga: classe 22 e 23 (tranne 23503) -> dead_letter subito (dato non
      valido); classe 42 e 0A (colonna sconosciuta, permessi) -> tabella bloccata,
      riga in coda; tutto il resto (23503, 08, 25006, 40, 53, 55, 57...) ->
      transitorio, ritento con tetto ``TETTO_TENTATIVI_RIGA`` (~6 h), poi dead_letter
      ``transitorio``;
    * le dead_letter RIENTRANO DA SOLE (archivio ``rientro_dead_letter``): transitorie
      ogni 15 min, dato e registro ogni 24 h; una di dato che fallisce
      ``RIENTRI_MAX_DATO`` rientri diventa ARCHIVIATA (fuori dall'allarme, contata a
      parte in ``stato().archiviate``); una superata da una scrittura piu' nuova della
      stessa chiave non rientra (R2);
    * voce di una tabella non registrata -> dead_letter ``registro`` (M1);
    * ordine: tabelle padre prima (``dipende_da``); per chiave al massimo UNA voce
      per chiamata; dopo un fallimento di una chiave le voci successive della
      stessa chiave aspettano (M4).

Disco
    ``tetto_disco_mb``: oltre il tetto, evento ``dati.tetto_disco`` e
    ``ripiego_diretto`` vero (segnale per l'aggancio di tornare alla scrittura di
    oggi con lo stesso ``uid``/``rev``). L'archivio NON smette di scrivere.

Ombra
    ``ombra=True`` -> ogni riga va su ``<tabella>_ombra`` (R02, R21).

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
from .schema_locale import (chiave_canonica, firma_file, giorno_utc, leggi_riga_log, tabella_della_riga_log,
                            testo_json)

logger = logging.getLogger(__name__)

RPC_CONSEGNA = "postino_consegna"
#: ~6 h di ritenti (attese fino a 60 s) prima che una riga transitoria diventi dead_letter
#: (che poi rientra da sola ogni 15 min): un padre scritto da un altro processo ha tempo (D10)
TETTO_TENTATIVI_RIGA = 360
TETTO_ATTESA_S = 60.0
ATTESE_PREDEFINITE_S: Tuple[float, ...] = (2.0, 4.0, 8.0, 16.0, 32.0)   # G par. 4.2 = db_client.ATTESE_RETE_S
BLOCCO_PREDEFINITO = 200
LETTURA_LOG_BYTE = 1_048_576
#: dopo quest'ora UTC il thread del postino riconcilia il giorno prima (pulizia abilitata)
ORA_RICONCILIAZIONE_UTC = 3
#: ogni quanto il postino fa rientrare le dead_letter scadute
RIENTRO_CONTROLLO_MS = 60_000
#: SQLSTATE delle intestazioni della RPC (errori di chiamata, mai della riga)
CODICE_INTESTAZIONE = "GP001"


class RispostaInattesa(RuntimeError):
    """La RPC ha risposto con una forma diversa da quella attesa (mai colpa delle righe)."""


@dataclass(frozen=True)
class StatoPostinoArchivio(StatoPostino):
    """``StatoPostino`` del contratto (campi invariati) piu' i conteggi del comparto G:

    * ``dead_letter``  (del contratto): righe nell'ALLARME (dead_letter attive + scarti
      recenti dello scrittore);
    * ``archiviate``   R2b: archiviate (rientri esauriti o superate) + scarti oltre la
      finestra d'allarme: su disco, visibili nel referto e in Salute, nessun allarme;
    * ``guasti_codice`` R3: volte in cui un errore di codice ha colpito TUTTE le voci
      (``guasto_codice`` = l'ultimo, None se lo scrittore e' ripartito)."""

    archiviate: int = 0
    guasti_codice: int = 0
    guasto_codice: Optional[str] = None


def _attese_rete() -> Tuple[float, ...]:
    """Riuso delle attese di ``db_client`` (import pigro: ``config`` legge l'ambiente)."""
    try:
        from db_client import ATTESE_RETE_S
        return tuple(ATTESE_RETE_S)
    except Exception as exc:  # fuori dal repo (test isolati): le stesse attese, dichiarate
        logger.debug("[postino] db_client non importabile (%s): attese predefinite", exc)
        return ATTESE_PREDEFINITE_S


def classe_riga(codice: str) -> str:
    """A4: 'dato' (dead_letter subito) | 'schema' (tabella bloccata) | 'transitorio'."""
    c = (codice or "").strip()
    if c.startswith("22") or (c.startswith("23") and c != "23503"):
        return "dato"
    if c.startswith("42") or c.startswith("0A") or c == CODICE_INTESTAZIONE:
        return "schema"
    return "transitorio"


def classifica_errore_chiamata(exc: BaseException) -> str:
    """'rete' | 'statement_timeout' | 'dati' | 'bloccante' per un errore su TUTTA la chiamata.

    La classe di rete viene da ``db_client.classifica_guasto_rete`` (riuso, nessuna
    copia): 5xx/HTML del gateway, connessione terminata, timeout, connessione."""
    codice = str(getattr(exc, "code", "") or "")
    messaggio = str(getattr(exc, "message", "") or exc)
    if codice == "57014" or "statement timeout" in messaggio.lower():
        return "statement_timeout"
    if isinstance(exc, RispostaInattesa):
        return "bloccante"
    try:
        from db_client import classifica_guasto_rete
    except Exception as imp:  # senza il classificatore vero non si inventa: si blocca e si dice
        logger.error("[postino] classifica_guasto_rete non importabile: %s", imp)
        return "bloccante"
    if classifica_guasto_rete(exc) is not None:
        return "rete"
    if not codice and isinstance(exc, (ValueError, UnicodeError, TypeError, OverflowError)):
        return "dati"                                        # il client non sa codificare il corpo
    if codice == "PGRST102" or (codice != CODICE_INTESTAZIONE and classe_riga(codice) == "dato"):
        return "dati"
    return "bloccante"


def _attesa(tentativi: int, attese: Sequence[float]) -> float:
    if tentativi <= 0:
        return 0.0
    return min(TETTO_ATTESA_S, attese[min(tentativi, len(attese)) - 1] if tentativi <= len(attese) else TETTO_ATTESA_S)


def _valida_json(riga: Any) -> Optional[str]:
    """Come httpx codifica il corpo (``allow_nan=False``, UTF-8): None se va, altrimenti il motivo."""
    try:
        json.dumps(riga, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return None
    except (ValueError, UnicodeError, TypeError, OverflowError) as exc:
        return f"{type(exc).__name__}: {exc}"[:300]


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
    seq: Optional[int] = None          # outbox: seq; log: offset di FINE riga
    file: Optional[str] = None         # log: nome del file
    vseq: Optional[int] = None         # outbox: versione LOCALE della voce (R1)


@dataclass
class _Giro:
    consegnate: int = 0
    ritentate: int = 0
    morte: int = 0
    errore: Optional[str] = None
    interrotto: bool = False
    fallite: Set[str] = field(default_factory=set)
    chiavi_fallite: Set[Tuple[str, Optional[str]]] = field(default_factory=set)
    # esiti per fonte
    ok_seq: Dict[str, List[int]] = field(default_factory=dict)
    rimandate: Dict[str, List[Tuple[int, int, int, str]]] = field(default_factory=dict)
    morte_seq: Dict[str, List[Tuple[int, str, str, int, str]]] = field(default_factory=dict)
    log_morte: Dict[str, List[Tuple[Any, ...]]] = field(default_factory=dict)
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
        self._prossimo_rientro_ms = 0
        self._bloccate: Dict[str, Tuple[int, int, str]] = {}   # tabella -> (prossimo_ms, tentativi, errore)
        self._cache_log: Dict[str, Tuple[int, int, Counter[str], Optional[int]]] = {}
        self.offline_da: Optional[datetime] = None
        self.ultimo_errore: Optional[str] = None
        self.ripiego_diretto = False
        self.contatori: Counter[str] = Counter()
        self._riconciliatore = riconciliatore
        self._riconciliato_fino: Optional[str] = None
        self._prossima_riconciliazione_ms = 0
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
        morti = self.archivio.conteggio_scarti(adesso)[0]
        for regime in REGIMI_SQLITE:
            p, v, m = self.archivio.conteggi_outbox(regime)
            per.update(p)
            morti += m
            if v is not None:
                vecchio = v if vecchio is None else min(vecchio, v)
        file = self.archivio.file_log()
        for nome in [n for n in self._cache_log if n not in {f.name for f in file}]:
            del self._cache_log[nome]
        for percorso in file:
            p, v = self._conta_log(percorso)
            per.update(p)
            if v is not None:
                vecchio = v if vecchio is None else min(vecchio, v)
        self._controlla_disco()
        return StatoPostinoArchivio(in_coda=sum(per.values()),
                                    eta_max_s=None if vecchio is None else max(0.0, (adesso - vecchio) / 1000.0),
                                    per_tabella=dict(per), ultimo_errore=self.ultimo_errore,
                                    offline_da=self.offline_da, dead_letter=morti,
                                    archiviate=self.archivio.conteggio_archiviate(),
                                    guasti_codice=int(self.archivio.contatori["guasti_codice"]),
                                    guasto_codice=self.archivio.guasto_codice)

    def drena(self, max_righe: int = 200) -> EsitoDrenaggio:
        """UN giro: raccoglie fino a ``max_righe`` righe pronte e le consegna."""
        with self._lock:
            adesso = self._ora_ms()
            if adesso < self._prossimo_giro_ms:
                return EsitoDrenaggio(0, 0, 0, f"in attesa ({(self._prossimo_giro_ms - adesso) / 1000.0:.1f} s): "
                                               f"{self.ultimo_errore}")
            if adesso >= self._prossimo_rientro_ms:
                self._prossimo_rientro_ms = adesso + RIENTRO_CONTROLLO_MS
                self.archivio.rientro_dead_letter(adesso)
            voci = self._raccogli(max(1, int(max_righe)), adesso)
            giro = _Giro()
            note: List[_Voce] = []
            for v in voci:
                if v.op == "salta":
                    continue
                try:
                    self.archivio.spec(v.tabella)
                    note.append(v)
                except (KeyError, ValueError) as exc:                       # M1: mai saltata, mai un blocco
                    self._morta(v, "registro", f"tabella non registrata: {exc}"[:300], giro, "registro")
            for tabella, op, gruppo in self._ordina(note):
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
    def avvia(self, intervallo_s: float = 1.0, max_righe: int = 200, *,
              ora_riconciliazione_utc: Optional[int] = ORA_RICONCILIAZIONE_UTC) -> None:
        """Thread ``postino``: drena finche' c'e' lavoro, poi dorme ``intervallo_s``.

        Una volta per giorno UTC, dopo ``ora_riconciliazione_utc``, riconcilia il giorno
        prima (marcatori che abilitano la pulizia automatica). ``None`` = mai."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()

        def ciclo() -> None:
            while not self._stop.is_set():
                try:
                    esito = self.drena(max_righe)
                    pieno = esito.consegnate + esito.dead_letter >= max_righe and esito.errore is None
                    if not pieno and ora_riconciliazione_utc is not None:
                        self.riconciliazione_notturna(ora_riconciliazione_utc)
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
        """Quota equa: ogni fonte (denaro, vivo, log) ha almeno un terzo del giro; cio'
        che una fonte non usa passa alle altre. Nessuna fonte affama le altre."""
        quota = max(1, -(-max_righe // 3))
        per_fonte: List[List[_Voce]] = []
        for regime in REGIMI_SQLITE:
            per_fonte.append([self._da_outbox(v) for v in self.archivio.outbox_pronta(regime, adesso, max_righe)])
        log: List[_Voce] = []
        for percorso in self.archivio.file_log():
            if len(log) >= max_righe:
                break
            log.extend(self._leggi_log(percorso, max_righe - len(log)))
        per_fonte.append(log)
        prese = [min(len(f), quota) for f in per_fonte]
        resto = max_righe - sum(prese)
        for i, f in enumerate(per_fonte):
            extra = min(len(f) - prese[i], max(0, resto))
            prese[i] += extra
            resto -= extra
        voci: List[_Voce] = []
        for f, n in zip(per_fonte, prese):
            voci.extend(f[:n])                  # per i log: righe CONTIGUE dall'offset, l'avanzamento resta esatto
        return voci

    @staticmethod
    def _da_outbox(v: VoceOutbox) -> _Voce:
        return _Voce(v.tabella, v.op, v.chiave, v.testo, v.creato_ms, v.tentativi, regime=v.regime, seq=v.seq,
                     vseq=v.vseq)

    def _marcatore_valido(self, percorso: Path) -> int:
        """M2: un marcatore oltre la fine del file o di un file sostituito torna a 0 e si segnala."""
        offset, firma = self.archivio.marcatore_log(percorso.name)
        if offset == 0:
            return 0
        dimensione = percorso.stat().st_size
        firma_ora = firma_file(percorso)
        if offset > dimensione or (firma is not None and firma_ora != firma):
            self.archivio.azzera_marcatore(percorso.name, {"file": percorso.name, "offset": offset,
                                                           "dimensione": dimensione,
                                                           "firma_cambiata": firma is not None and firma_ora != firma})
            self.contatori["marcatori_azzerati"] += 1
            return 0
        return offset

    def _leggi_log(self, percorso: Path, quante: int) -> List[_Voce]:
        """Righe COMPLETE dopo il marcatore; una riga non leggibile si segnala e si salta;
        la riga di una tabella non registrata diventa una voce (dead_letter ``registro``)."""
        offset = self._marcatore_valido(percorso)
        voci: List[_Voce] = []
        with open(percorso, "rb") as f:
            f.seek(offset)
            dati = f.read(LETTURA_LOG_BYTE)
            while b"\n" not in dati and len(dati) >= LETTURA_LOG_BYTE:
                altro = f.read(LETTURA_LOG_BYTE)      # una riga piu' lunga del blocco: si legge per intero
                if not altro:
                    break
                dati += altro
        pos = offset
        for linea in dati.splitlines(keepends=True):
            if not linea.endswith(b"\n") or len(voci) >= quante:
                break                                     # riga in scrittura o quota piena
            fine = pos + len(linea)
            try:
                tabella, op, ms, riga = leggi_riga_log(linea.decode("ascii"))
            except (ValueError, KeyError, UnicodeDecodeError) as exc:
                dettagli = {"file": percorso.name, "offset": pos, "errore": str(exc)[:200],
                            "anteprima": linea[:200].decode("ascii", "replace")}
                self.contatori["righe_log_guaste"] += 1
                self.archivio.segnala("riga_log_guasta", dettagli)
                self._evento("dati.riga_troncata", dettagli)
                voci.append(_Voce("", "salta", None, "", 0, 0, file=percorso.name, seq=fine))
                pos = fine
                continue
            try:
                chiave: Optional[str] = chiave_canonica(self.archivio.spec(tabella), riga)
            except (KeyError, ValueError):
                chiave = None                             # tabella sconosciuta o chiave mancante: la decide drena
            voci.append(_Voce(tabella, op, chiave, testo_json(riga), ms, 0, file=percorso.name, seq=fine))
            pos = fine
        return voci

    def _conta_log(self, percorso: Path) -> Tuple[Counter[str], Optional[int]]:
        """B7: conteggio INCREMENTALE della coda di un file (si legge solo cio' che e'
        cambiato dall'ultima volta: le righe nuove e quelle appena consegnate)."""
        nome = percorso.name
        marcatore = self.archivio.offset_log(nome)
        try:
            dimensione = percorso.stat().st_size
        except FileNotFoundError:
            self._cache_log.pop(nome, None)
            return Counter(), None
        c = self._cache_log.get(nome)
        if c is None or marcatore < c[0] or marcatore > c[1] or dimensione < c[1]:
            conta, fine = self._scansiona(percorso, marcatore, dimensione)
            primo = self._primo_ms(percorso, marcatore, fine)
        else:
            conta, fine, primo = Counter(c[2]), c[1], c[3]
            if marcatore > c[0]:
                via, _ = self._scansiona(percorso, c[0], marcatore)
                conta.subtract(via)
                conta = +conta
                primo = self._primo_ms(percorso, marcatore, fine)
            if dimensione > fine:
                nuove, fine = self._scansiona(percorso, fine, dimensione)
                conta.update(nuove)
                if primo is None:
                    primo = self._primo_ms(percorso, marcatore, fine)
        self._cache_log[nome] = (marcatore, fine, conta, primo)
        return Counter(conta), primo

    @staticmethod
    def _scansiona(percorso: Path, da: int, a: int) -> Tuple[Counter[str], int]:
        """Righe complete in [da, a): conteggio per tabella e fine dell'ultima riga completa."""
        conta: Counter[str] = Counter()
        fine = da
        with open(percorso, "rb") as f:
            f.seek(da)
            dati = f.read(max(0, a - da))
        for linea in dati.splitlines(keepends=True):
            if not linea.endswith(b"\n"):
                break
            fine += len(linea)
            t = tabella_della_riga_log(linea.decode("ascii", "replace"))
            if t:
                conta[t] += 1
        return conta, fine

    @staticmethod
    def _primo_ms(percorso: Path, da: int, a: int) -> Optional[int]:
        if a <= da:
            return None
        with open(percorso, "rb") as f:
            f.seek(da)
            linea = f.readline()
        try:
            return leggi_riga_log(linea.decode("ascii", "replace"))[2]
        except (ValueError, KeyError):
            return None

    def _ordina(self, voci: Sequence[_Voce]) -> List[Tuple[str, str, List[_Voce]]]:
        """Gruppi = corse consecutive (tabella, op) nell'ordine di arrivo; tabelle padre prima."""
        per_tabella: Dict[str, List[_Voce]] = {}
        for v in voci:
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
        except (KeyError, ValueError):
            return 0
        return 1 + max((self._profondita(p, visti | {tabella}) for p in padri), default=-1)

    # ------------------------------------------------------------------ consegna
    def _consegna_gruppo(self, spec: SpecTabella, op: str, gruppo: List[_Voce], giro: _Giro, adesso: int) -> None:
        """Pezzi di al massimo ``blocco`` righe, al massimo UNA voce per chiave per chiamata;
        una voce di una chiave gia' fallita in questo giro aspetta (M4)."""
        pendenti = list(gruppo)
        while pendenti and not giro.interrotto:
            n = self._blocco_tabella.get(spec.nome, self._blocco)
            pezzo: List[_Voce] = []
            resto: List[_Voce] = []
            chiavi: Set[Tuple[str, Optional[str]]] = set()
            for v in pendenti:
                k = (v.tabella, v.chiave)
                if v.chiave is not None and k in giro.chiavi_fallite:
                    self._rimanda(v, giro, adesso, "attende la voce precedente della stessa chiave", contare=False)
                    continue
                if len(pezzo) < n and (v.chiave is None or k not in chiavi):
                    pezzo.append(v)
                    chiavi.add(k)
                else:
                    resto.append(v)
            if not pezzo:
                return
            if not self._invia(spec, op, pezzo, giro, adesso):
                if not giro.interrotto:
                    bloc = self._bloccate.get(spec.nome)
                    pronta = bloc[0] if bloc is not None else adesso
                    for v in resto:
                        self._rimanda(v, giro, pronta, "tabella ferma in questo giro", contare=False)
                    giro.fallite.add(spec.nome)
                return
            pendenti = resto

    def _invia(self, spec: SpecTabella, op: str, pezzo: List[_Voce], giro: _Giro, adesso: int) -> bool:
        """Una chiamata. Falso = la tabella si ferma in questo giro (le voci del pezzo sono
        gia' state rimandate, o il giro e' interrotto perche' offline)."""
        valide: List[Tuple[_Voce, Any]] = []
        for v in pezzo:
            riga = json.loads(v.testo)
            motivo = _valida_json(riga)
            if motivo is not None:                      # A1: NaN, Infinity, surrogato isolato
                self._morta(v, "valore_non_json", motivo, giro, "dato")
                continue
            valide.append((v, riga))
        if not valide:
            return True
        versioni = [v.vseq for v, _ in valide]
        origine = next((self.archivio.origine(v.regime) for v, _ in valide
                        if v.vseq is not None and v.regime is not None), None)
        argomenti = {"p_tabella": self.destinazione(spec.nome), "p_op": op,
                     "p_conflitto": list(spec.chiave_naturale), "p_righe": [r for _, r in valide],
                     "p_origine": origine, "p_versioni": versioni if origine is not None else None}
        try:
            esiti = self.cloud.rpc(RPC_CONSEGNA, argomenti)
            if not isinstance(esiti, list) or len(esiti) != len(valide):
                raise RispostaInattesa(f"risposta inattesa di {RPC_CONSEGNA}: {str(esiti)[:200]}")
        except Exception as exc:
            if classifica_errore_chiamata(exc) != "dati":
                self._errore_chiamata(spec, [v for v, _ in valide], exc, giro, adesso)
                return False
            descr = f"{type(exc).__name__}: {getattr(exc, 'code', '') or ''} {getattr(exc, 'message', '') or exc}"[:300]
            if len(valide) == 1:                         # A1: la riga velenosa e' isolata
                self._morta(valide[0][0], str(getattr(exc, "code", "") or "dato"), descr, giro, "dato")
                return True
            self.contatori["bisezioni"] += 1
            meta = len(valide) // 2
            prima, seconda = [v for v, _ in valide[:meta]], [v for v, _ in valide[meta:]]
            if not self._invia(spec, op, prima, giro, adesso):
                if not giro.interrotto:
                    bloc = self._bloccate.get(spec.nome)
                    for v in seconda:
                        self._rimanda(v, giro, bloc[0] if bloc else adesso, "tabella ferma in questo giro",
                                      contare=False)
                return False
            return self._invia(spec, op, seconda, giro, adesso)
        self._in_linea()
        prima = self.contatori["tabelle_bloccate"]
        for (v, _), esito in zip(valide, esiti):
            self._esito_riga(spec, v, esito, giro, adesso)
        if self.contatori["tabelle_bloccate"] == prima and self._bloccate.pop(spec.nome, None) is not None:
            self._evento("dati.postino_sbloccato", {"tabella": spec.nome})     # sblocco solo se nessuna riga ribloccata
        return True

    def _esito_riga(self, spec: SpecTabella, v: _Voce, esito: Any, giro: _Giro, adesso: int) -> None:
        tipo = esito.get("esito") if isinstance(esito, dict) else None
        if tipo in ("ok", "ignorata", "vecchia"):
            giro.consegnate += 1
            self.contatori["consegnate" if tipo == "ok" else ("vecchie" if tipo == "vecchia" else "ignorate")] += 1
            if tipo == "vecchia":                        # R1: voce vecchia della STESSA origine, scartata dal cloud
                self._evento("dati.riga_vecchia", {"tabella": v.tabella, "chiave": v.chiave, "vseq": v.vseq,
                                                   "destinazione": self.destinazione(v.tabella)})
            if v.file is None and v.regime is not None and v.seq is not None:
                giro.ok_seq.setdefault(v.regime, []).append(v.seq)
            return
        codice = str((esito or {}).get("codice") or "") if isinstance(esito, dict) else ""
        messaggio = str((esito or {}).get("messaggio") or esito) if isinstance(esito, dict) else str(esito)
        errore = f"{codice} {messaggio}".strip()[:500]
        classe = classe_riga(codice)
        giro.fallite.add(spec.nome)                      # i figli aspettano il giro dopo
        if classe == "dato":
            self._morta(v, codice, errore, giro, "dato")
            return
        giro.chiavi_fallite.add((v.tabella, v.chiave))
        if classe == "schema":                           # A4: colonna sconosciuta, permessi: la tabella
            self._blocca(spec, errore, 1, adesso)
            self._rimanda(v, giro, self._bloccate[spec.nome][0], errore, contare=False)
            return
        if v.tentativi + 1 < self._tetto_riga:
            self._rimanda(v, giro, adesso, errore, contare=True)
            return
        self._morta(v, codice or "risposta", errore, giro, "transitorio")

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
        """La tabella si ferma (attesa crescente, tetto 60 s): righe in coda; l'allarme
        parte UNA volta per episodio (non a ogni giro)."""
        prec = self._bloccate.get(spec.nome)
        if prec is not None and prec[0] > adesso:
            return                                          # gia' bloccata in questo giro
        tentativi = (prec[1] if prec else 0) + 1
        self._bloccate[spec.nome] = (adesso + int(_attesa(tentativi, self._attese) * 1000), tentativi, descr)
        self.contatori["tabelle_bloccate"] += 1
        self.ultimo_errore = f"{spec.nome}: {descr}"
        if prec is None:
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

    def _morta(self, v: _Voce, codice: str, errore: str, giro: _Giro, motivo: str) -> None:
        giro.morte += 1
        self.contatori["dead_letter"] += 1
        if v.file is not None:
            giro.log_morte.setdefault(v.file, []).append(
                (v.tabella, v.op, v.chiave or "", v.testo, v.creato_ms, codice, errore, v.tentativi + 1, motivo))
        elif v.regime is not None and v.seq is not None:
            giro.morte_seq.setdefault(v.regime, []).append((v.seq, codice, errore, v.tentativi + 1, motivo))
        self._evento("dati.dead_letter", {"tabella": v.tabella, "destinazione": self.destinazione(v.tabella),
                                          "motivo": motivo, "riga": json.loads(v.testo), "errore": errore})

    def _chiudi_giro(self, voci: Sequence[_Voce], giro: _Giro) -> None:
        for regime in REGIMI_SQLITE:
            ok = giro.ok_seq.get(regime, [])
            rim = list(giro.rimandate.get(regime, []))
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
            self.archivio.chiudi_log(nome, fine, giro.log_morte.get(nome, []), giro.log_ritenti.get(nome, []),
                                     firma=firma_file(self.archivio.cartella_log() / nome))

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

    def riconciliazione_notturna(self, ora_utc: int = 3) -> Optional[str]:
        """Se e' passata l'ora ``ora_utc`` e il giorno prima non e' ancora riconciliato in
        questo processo, lo riconcilia (tabelle con righe locali quel giorno). Ritorna il
        giorno riconciliato o ``None``. Offline: solleva, e il giro dopo riprova."""
        adesso = self._ora_ms()
        if self.offline_da is not None:
            return None
        ora = datetime.fromtimestamp(adesso / 1000.0, tz=timezone.utc)
        giorno = (ora - timedelta(days=1)).strftime("%Y-%m-%d")
        if ora.hour < ora_utc or self._riconciliato_fino == giorno or adesso < self._prossima_riconciliazione_ms:
            return None
        self._prossima_riconciliazione_ms = adesso + 300_000        # un errore non diventa un martellamento
        tabelle = self.archivio.tabelle_del_giorno(giorno)
        self.riconcilia_giorno(giorno, tabelle)
        self._riconciliato_fino = giorno
        return giorno

    def riconcilia_giorno(self, giorno: str, tabelle: Sequence[str]) -> List[RapportoRiconciliazione]:
        """Confronto notturno di un giorno UTC per ogni tabella; scrive il marcatore
        (``ok`` = nessuna differenza) che abilita la pulizia."""
        da = datetime.strptime(giorno, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        rapporti = []
        for t in tabelle:
            try:
                self.archivio.spec(t)
            except (KeyError, ValueError):
                continue                                    # tabella non piu' registrata: nessun marcatore
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


__all__ = ["PostinoLocale", "classifica_errore_chiamata", "classe_riga", "RPC_CONSEGNA", "giorno_utc",
           "REGIME_SERVIZIO"]
