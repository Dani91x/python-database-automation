"""Cache degli algoritmi del cloud fuori dal ciclo di decisione (comparto G, tappa T7).

Scopo
    Togliere dal ciclo di decisione le letture SINCRONE del cloud degli algoritmi che restano nel
    cloud (G parte 2, 04 par. 6.3) senza cambiare un valore ne' una scadenza:
      * tabella HT->FT (RPC ``get_omega_ht_ft``) e tabella per minuto (RPC ``get_omega_minute_ft``)
        di Omega (G-035) e di Mike (G-034): ``ReplicaEmpirica``, prefetch per lega di TUTTI i
        bucket, riletta dopo ogni giro del pg_cron (sentinella: ``omega_transitions_state``,
        ``built_at`` di ``omega_ht_ft_transitions``, ``omega_build_jobs``);
      * dossier pre-match di Mike (G-033): ``DossierPrematch``, ponte evento->fixture e righe di
        ``fixture_predictions`` lette a blocchi PRIMA dell'aggancio (``lambda_home/away``, ``rho``,
        ``p4_pre``, ``p_under35_cal`` restano calcolati da ``mike/dossier.build_prematch``).

Le scadenze di oggi NON cambiano (U-53): la cache di Omega scade dopo 6 h
(``omega_service.EMPIRICAL_CACHE_TTL_S``) e quella di Mike mai (``mike/dossier._EMPIRICAL_CACHE``):
restano NEI BOT, sopra questa replica, che risponde con le STESSE firme delle funzioni di oggi
(``omega_db.ht_ft_transitions``/``minute_transitions``, ``mike.db.fixture_id_for_event``/
``fixture_lambdas``/``fixture_analysis``/``ht_ft_rows``) e con le STESSE righe dell'RPC, compresa la
distinzione "[] = vuota, None = errore (mai in cache)". Il dossier tiene in memoria SOLO le risposte
positive (fixture trovata, gol attesi presenti) e per al massimo ``SCADENZA_DOSSIER_S`` = 300 s (il
ritento di Mike, ``mike/service._DOSSIER_RETRY_SEC``): un negativo va sempre al ripiego, come oggi.

Entrate: un ``Cloud`` (``cloud.ClienteCloud``), le leghe e gli eventi da preparare.
Uscite: righe identiche a quelle delle RPC/letture di oggi, servite dalla memoria.

Cosa NON fa
    Non importa nessun bot (le funzioni di oggi sono gli ARBITRI nei test). Non decide nulla. Non
    apre thread all'import: il thread di prefetch e sorveglianza nasce solo con ``avvia`` e muore con
    ``ferma``. Un mancato prefetch (chiave assente) va al ``ripiego`` (la funzione di oggi, sincrona,
    identica) se c'e', altrimenti risponde None come un errore di oggi (mai in cache) e chiede di
    nuovo il prefetch della lega (al piu' ogni ``RITARDO_RIPREFETCH_S``): e' l'unico punto in cui il
    nuovo puo' differire, e l'ombra (ondata 2, ``ARCH_PREFETCH_<BOT>=vecchio|ombra|nuovo``) lo misura.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .contratto import Cloud

logger = logging.getLogger("nucleo.dati.cache_cloud")

# ---------------------------------------------------------------------------
# Costanti di oggi (provate uguali a quelle dei bot nei test di parita')
# ---------------------------------------------------------------------------
#: bucket della tabella per minuto: ``omega_empirical.minute_bucket`` (passo 5, max 85 FT, 40 HT)
BUCKET_FT: Tuple[int, ...] = tuple(range(0, 86, 5))
BUCKET_HT: Tuple[int, ...] = tuple(range(0, 41, 5))
CHIAVI_PER_LEGA = 1 + len(BUCKET_FT) + len(BUCKET_HT)
#: scadenze delle cache DEI BOT, che restano nei bot (U-53): qui solo dichiarate
SCADENZA_OMEGA_S = 6 * 3600.0        # omega_service.EMPIRICAL_CACHE_TTL_S
SCADENZA_MIKE_S: Optional[float] = None  # mike/dossier._EMPIRICAL_CACHE: mai
#: ogni quanto il thread rilegge la sentinella (giro del pg_cron delle 04:00 UTC)
INTERVALLO_SORVEGLIANZA_S = 300.0
#: una lega con chiavi mancanti si richiede di nuovo al piu' ogni tanti secondi
RITARDO_RIPREFETCH_S = 60.0
#: il dossier positivo vale al massimo quanto il ritento di Mike (mike/service._DOSSIER_RETRY_SEC)
SCADENZA_DOSSIER_S = 300.0
COLONNE_PREMATCH = "fixture_id,league_id,tactical_engine_json,db_json_analisi,home_team_id,away_team_id"
BLOCCO_IN = 50                        # valori per filtro ``in`` (URL corte)
ENV_PREFETCH = "ARCH_PREFETCH_{bot}"  # vecchio | ombra | nuovo (ondata 2)


def _lega(league_id: Any) -> Optional[int]:
    """Come ``omega_db``: ``int(league_id)`` o None."""
    return int(league_id) if league_id is not None else None


def _lista_o_vuota(dati: Any) -> List[Dict[str, Any]]:
    """Come ``omega_db``: una lista resta lista (copia), ogni altra cosa diventa []."""
    return list(dati) if isinstance(dati, list) else []


def _copia(righe: Optional[Sequence[Mapping[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    return None if righe is None else [dict(r) for r in righe]


# ---------------------------------------------------------------------------
# 1. Le due RPC di Omega con gli argomenti e i ritorni di oggi
# ---------------------------------------------------------------------------
class SorgenteOmega:
    """``get_omega_ht_ft`` e ``get_omega_minute_ft`` via ``Cloud.rpc``: stessi argomenti e stessi
    ritorni di ``omega_db.ht_ft_transitions``/``minute_transitions`` ([] = vuota, None = errore).
    Differenza dichiarata: il ``Cloud`` ritenta i guasti di rete (RPC di lettura), oggi no."""

    def __init__(self, cloud: Cloud) -> None:
        self._cloud = cloud

    def ht_ft(self, league_id: Optional[int]) -> Optional[List[Dict[str, Any]]]:
        try:
            return _lista_o_vuota(self._cloud.rpc("get_omega_ht_ft", {"p_league_id": _lega(league_id)}))
        except Exception as ex:  # noqa: BLE001 - errore = None, mai in cache (come omega_db)
            logger.warning("[cache_cloud] get_omega_ht_ft KO (%s): %s", league_id, str(ex)[:120])
            return None

    def minuti(self, league_id: Optional[int], bucket: int, target: str) -> Optional[List[Dict[str, Any]]]:
        try:
            return _lista_o_vuota(self._cloud.rpc("get_omega_minute_ft", {
                "p_league_id": _lega(league_id), "p_bucket": int(bucket), "p_target": str(target)}))
        except Exception as ex:  # noqa: BLE001
            logger.warning("[cache_cloud] get_omega_minute_ft KO (%s,%s,%s): %s", league_id, bucket, target,
                           str(ex)[:120])
            return None

    def sentinella(self) -> Optional[str]:
        """Impronta dell'ultima ricostruzione delle DUE tabelle: la riga di ``omega_transitions_state``
        (``updated_at`` a ogni giro del pg_cron incrementale, anche quando cambia solo la tabella per
        minuto; ``published_at``), il ``built_at`` massimo di ``omega_ht_ft_transitions`` e l'ultimo
        ``omega_build_jobs`` (costruzione a mano v3/v4 della tabella per minuto). None se una
        delle letture fallisce (la sorveglianza riprova al giro dopo: nessuna rilettura a vuoto)."""
        letture = (("omega_transitions_state", {"select": "updated_at,published_at", "id": 1}),
                   ("omega_ht_ft_transitions", {"select": "built_at", "order": "built_at.desc", "limit": 1}),
                   ("omega_build_jobs", {"select": "job,updated_at", "order": "updated_at.desc", "limit": 1}))
        pezzi = []
        for tabella, filtri in letture:
            try:
                righe = self._cloud.leggi(tabella, filtri)
            except Exception as ex:  # noqa: BLE001
                logger.warning("[cache_cloud] sentinella %s non leggibile: %s", tabella, str(ex)[:120])
                return None
            pezzi.append(json.dumps(righe[:1], sort_keys=True, default=str))
        return "|".join(pezzi)


# ---------------------------------------------------------------------------
# 2. Replica delle tabelle empiriche (prefetch per lega, rilettura dopo la sentinella)
# ---------------------------------------------------------------------------
Chiave = Tuple[Any, ...]   # ("ht_ft", lega) | ("minuti", lega, bucket, target)
Righe = List[Dict[str, Any]]
_FINE = object()           # sentinella di ``ferma`` nella coda (None e' una lega valida: il globale)


@dataclass(frozen=True)
class EsitoPrefetch:
    lette: int
    errori: int


class ReplicaEmpirica:
    """Memoria delle righe delle due RPC per chiave, ogni voce marcata con la GENERAZIONE della
    sentinella in cui e' stata letta. Le letture (``ht_ft_transitions``, ``minute_transitions``,
    ``ht_ft_rows``) NON vanno in rete se la chiave e' pronta. Una scrittura iniziata in una
    generazione e finita in un'altra si scarta (mai righe della notte vecchia dopo il cambio);
    la rilettura dopo la ricostruzione FONDE, non sostituisce (le leghe preparate nel frattempo
    restano)."""

    def __init__(self, sorgente: SorgenteOmega, *, ripiego_sincrono: bool = True,
                 intervallo_sorveglianza_s: float = INTERVALLO_SORVEGLIANZA_S,
                 ritardo_riprefetch_s: float = RITARDO_RIPREFETCH_S,
                 orologio: Callable[[], float] = time.monotonic) -> None:
        self._sorgente = sorgente
        self._ripiego = ripiego_sincrono
        self._intervallo = float(intervallo_sorveglianza_s)
        self._ritardo = float(ritardo_riprefetch_s)
        self._orologio = orologio
        self._lock = threading.Lock()
        self._righe: Dict[Chiave, Tuple[int, Righe]] = {}
        self._leghe: set = set()
        self._richieste: Dict[Optional[int], float] = {}
        self._gen = 0
        self._sentinella: Optional[str] = None
        self._coda: "queue.Queue[Any]" = queue.Queue()
        self._ferma = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._conti: Dict[str, int] = {"colpi": 0, "mancati": 0, "ripieghi": 0, "letture_rete": 0,
                                       "ricostruzioni": 0, "errori": 0, "scartate": 0, "riprefetch": 0}

    # --------------------------------------------- firme di omega_db / mike.db (ciclo di decisione)
    def ht_ft_transitions(self, league_id: Optional[int]) -> Optional[Righe]:
        lega = _lega(league_id)
        return self._servi(("ht_ft", lega), lambda: self._sorgente.ht_ft(lega), lega)

    def minute_transitions(self, league_id: Optional[int], bucket: int, target: str) -> Optional[Righe]:
        lega = _lega(league_id)
        chiave = ("minuti", lega, int(bucket), str(target))
        return self._servi(chiave, lambda: self._sorgente.minuti(lega, int(bucket), str(target)), lega)

    def ht_ft_rows(self, league_id: Optional[int]) -> Optional[Righe]:
        """Firma di ``mike.db.ht_ft_rows`` (che delega a ``omega_db.ht_ft_transitions``)."""
        return self.ht_ft_transitions(league_id)

    # --------------------------------------------- riempimento (fuori dal ciclo)
    def prefetch_lega(self, league_id: Optional[int], *, solo_mancanti: bool = False) -> EsitoPrefetch:
        """Legge HT->FT e TUTTI i bucket (FT 0..85, HT 0..40) della lega (o solo le chiavi che
        mancano nella generazione corrente). Gli errori non entrano in memoria."""
        lega = _lega(league_id)
        with self._lock:
            self._leghe.add(lega)
            gen = self._gen
            presenti = {k for k, (g, _) in self._righe.items() if g == gen} if solo_mancanti else set()
        lette = errori = 0
        for chiave, leggi in self._chiavi_di(lega):
            if chiave in presenti:
                continue
            righe = leggi()
            self._memorizza(chiave, righe, gen)
            lette += righe is not None
            errori += righe is None
        return EsitoPrefetch(lette, errori)

    def richiedi_prefetch(self, league_id: Optional[int], *, forza: bool = True) -> bool:
        """Accoda la lega al thread (non blocca). Con ``forza=False`` al piu' una richiesta ogni
        ``ritardo_riprefetch_s`` per lega. Ritorna True se accodata."""
        lega = _lega(league_id)
        adesso = self._orologio()
        with self._lock:
            if not forza and adesso - self._richieste.get(lega, -1e18) < self._ritardo:
                return False
            self._richieste[lega] = adesso
        self._coda.put(lega)
        return True

    def drena_coda(self) -> int:
        """Esegue SUBITO i prefetch in coda (le chiavi mancanti delle leghe richieste): lo usa il
        thread; senza thread lo chiama chi vuole un riempimento sincrono fuori dal ciclo."""
        fatte = 0
        while True:
            try:
                lega = self._coda.get_nowait()
            except queue.Empty:
                return fatte
            if lega is _FINE:
                self._coda.put(_FINE)
                return fatte
            self.prefetch_lega(lega, solo_mancanti=True)
            fatte += 1

    def richiedi_incomplete(self) -> int:
        """Riaccoda (col ritardo minimo) le leghe note a cui manca qualche chiave."""
        with self._lock:
            per_lega: Dict[Optional[int], int] = {lega: 0 for lega in self._leghe}
            for chiave, (g, _) in self._righe.items():
                if g == self._gen and chiave[1] in per_lega:
                    per_lega[chiave[1]] += 1
        incomplete = [lega for lega, n in per_lega.items() if n < CHIAVI_PER_LEGA]
        accodate = sum(self.richiedi_prefetch(lega, forza=False) for lega in incomplete)
        with self._lock:
            self._conti["riprefetch"] += accodate
        return accodate

    def controlla_ricostruzione(self) -> bool:
        """Legge la sentinella: se e' cambiata apre una generazione nuova, rilegge TUTTE le chiavi
        delle leghe note e le FONDE nella memoria; alla fine toglie le voci rimaste della
        generazione vecchia (rilettura fallita = errore = mai in cache). La prima lettura registra
        soltanto. Durante la rilettura si servono le voci vecchie (finestra dichiarata)."""
        nuova = self._sorgente.sentinella()
        if nuova is None:
            return False
        with self._lock:
            vecchia = self._sentinella
            if vecchia == nuova:
                return False
            self._sentinella = nuova
            if vecchia is None:
                return False
            self._gen += 1
            gen = self._gen
            leghe = sorted(self._leghe, key=lambda x: (x is None, x))
        lette = 0
        for lega in leghe:
            for chiave, leggi in self._chiavi_di(lega):
                righe = leggi()
                lette += self._memorizza(chiave, righe, gen)
        with self._lock:
            if self._gen == gen:
                for chiave in [k for k, (g, _) in self._righe.items() if g < gen]:
                    del self._righe[chiave]
            self._conti["ricostruzioni"] += 1
        logger.info("[cache_cloud] ricostruzione del pg_cron: %d chiavi rilette (generazione %d)", lette, gen)
        return True

    # --------------------------------------------- thread
    def avvia(self) -> None:
        """Thread di prefetch (coda) e sorveglianza della sentinella (ogni ``intervallo``)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._ferma.clear()
        self._thread = threading.Thread(target=self._giro, name="cache_cloud_replica", daemon=True)
        self._thread.start()

    def ferma(self, attesa_s: float = 5.0) -> None:
        self._ferma.set()
        self._coda.put(_FINE)
        if self._thread is not None:
            self._thread.join(attesa_s)
            if self._thread.is_alive():
                logger.error("[cache_cloud] il thread della replica non si e' fermato in %.1f s", attesa_s)
        self._thread = None

    def vivo(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def statistiche(self) -> Mapping[str, Any]:
        with self._lock:
            return {**self._conti, "chiavi": len(self._righe), "leghe": len(self._leghe),
                    "generazione": self._gen, "sentinella": self._sentinella}

    # --------------------------------------------- interni
    def _chiavi_di(self, lega: Optional[int]) -> List[Tuple[Chiave, Callable[[], Optional[Righe]]]]:
        s = self._sorgente
        out: List[Tuple[Chiave, Callable[[], Optional[Righe]]]] = [(("ht_ft", lega), lambda: s.ht_ft(lega))]
        for target, bucket_di in (("ft", BUCKET_FT), ("ht", BUCKET_HT)):
            for b in bucket_di:
                out.append((("minuti", lega, b, target), lambda b=b, t=target: s.minuti(lega, b, t)))
        return out

    def _memorizza(self, chiave: Chiave, righe: Optional[Righe], gen: int) -> bool:
        """Salva le righe lette nella generazione ``gen`` SOLO se e' ancora la corrente."""
        with self._lock:
            self._conti["letture_rete"] += 1
            if righe is None:
                self._conti["errori"] += 1
                return False
            if gen != self._gen:
                self._conti["scartate"] += 1
                return False
            self._righe[chiave] = (gen, righe)
            return True

    def _servi(self, chiave: Chiave, leggi: Callable[[], Optional[Righe]], lega: Optional[int]) -> Optional[Righe]:
        with self._lock:
            voce = self._righe.get(chiave)
            if voce is not None:
                self._conti["colpi"] += 1
                return _copia(voce[1])
            self._conti["mancati"] += 1
            gen = self._gen
        self.richiedi_prefetch(lega, forza=False)      # lega nuova o chiave mancante: di nuovo
        if not self._ripiego:
            return None                               # come un errore di oggi: il bot riprova
        righe = leggi()
        with self._lock:
            self._conti["ripieghi"] += 1
        self._memorizza(chiave, righe, gen)
        return _copia(righe)

    def _giro(self) -> None:
        prossima = 0.0
        while not self._ferma.is_set():
            adesso = time.monotonic()
            if adesso >= prossima:
                try:
                    self.controlla_ricostruzione()
                    self.richiedi_incomplete()
                except Exception:  # noqa: BLE001 - il thread non muore: si logga e si riprova
                    logger.exception("[cache_cloud] sorveglianza della ricostruzione fallita")
                prossima = adesso + self._intervallo
            try:
                lega = self._coda.get(timeout=max(0.05, min(1.0, prossima - time.monotonic())))
            except queue.Empty:
                continue
            if lega is _FINE or self._ferma.is_set():
                break
            try:
                self.prefetch_lega(lega, solo_mancanti=True)
            except Exception:  # noqa: BLE001
                logger.exception("[cache_cloud] prefetch della lega %s fallito", lega)


# ---------------------------------------------------------------------------
# 3. Dossier pre-match di Mike
# ---------------------------------------------------------------------------
def lambdas_da_riga(riga: Mapping[str, Any], *, con_squadre: bool = True) -> Optional[tuple]:
    """Lambda pre-match dalla riga di ``fixture_predictions``: catena ``tactical_engine_json`` ->
    ``db_json_analisi.inputs`` (JSON in stringa ammesso). Riscrittura di
    ``Betfair/stream/db.get_fixture_prematch_lambdas`` sulla riga gia' letta: la parita' e' provata
    da ``test_g2_cache_cloud.py`` su una griglia di righe (stessi ritorni, compresa la tupla con
    lambda None quando la riga c'e' e le lambda no)."""
    league_id = riga.get("league_id")
    for chiave, sotto in (("tactical_engine_json", None), ("db_json_analisi", "inputs")):
        nodo = riga.get(chiave)
        if isinstance(nodo, str):
            try:
                nodo = json.loads(nodo)
            except (ValueError, TypeError):
                nodo = None
        if sotto and isinstance(nodo, dict):
            nodo = nodo.get(sotto)
        if isinstance(nodo, dict):
            lh, la = nodo.get("lambda_home"), nodo.get("lambda_away")
            try:
                if lh is not None and la is not None and float(lh) > 0 and float(la) > 0:
                    if con_squadre:
                        return (float(lh), float(la), league_id, riga.get("home_team_id"), riga.get("away_team_id"))
                    return (float(lh), float(la), league_id)
            except (TypeError, ValueError):
                pass
    if con_squadre:
        return (None, None, league_id, riga.get("home_team_id"), riga.get("away_team_id"))
    return None


_ASSENTE = object()   # nessuna voce valida in memoria: si va al ripiego


class DossierPrematch:
    """Le letture del dossier di Mike preparate PRIMA dell'aggancio, con le firme di ``mike.db``
    usate da ``mike/dossier.build_prematch``. In memoria SOLO i positivi (evento con fixture, riga
    con gol attesi) e per ``scadenza_s``: un negativo (fixture non trovata, previsione assente o
    senza lambda) NON si memorizza, cosi' la fixture che arriva dopo accende il modello al ritento
    di Mike (CERT 12/09) esattamente come oggi. Chiave non pronta -> ``ripiego`` (il modulo
    ``mike.db`` di oggi, sincrono) o None se non c'e'."""

    def __init__(self, cloud: Cloud, *, replica: Optional[ReplicaEmpirica] = None, ripiego: Any = None,
                 orologio: Callable[[], float] = time.time, scadenza_s: float = SCADENZA_DOSSIER_S) -> None:
        self._cloud = cloud
        self._replica = replica
        self._ripiego = ripiego
        self._orologio = orologio
        self._scadenza = float(scadenza_s)
        self._lock = threading.Lock()
        self._ponte: Dict[str, Tuple[float, int]] = {}
        self._fixture: Dict[int, Tuple[float, Mapping[str, Any]]] = {}
        self._conti: Dict[str, int] = {"colpi": 0, "mancati": 0, "ripieghi": 0, "letture_rete": 0, "errori": 0}

    # --------------------------------------------- preparazione (fuori dal ciclo)
    def precarica(self, event_ids: Iterable[str]) -> int:
        """Ponte evento->fixture (``live_follow`` poi ``omega_events``) e righe di
        ``fixture_predictions`` per gli eventi dati, a blocchi. Ritorna gli eventi con fixture."""
        eventi = sorted({str(e) for e in event_ids})
        ponte = self._leggi_ponte(eventi)
        adesso = self._orologio()
        with self._lock:
            for ev, fid in ponte.items():
                self._ponte[ev] = (adesso, fid)
        self._precarica_fixture(sorted(set(ponte.values())))
        return len(ponte)

    # --------------------------------------------- firme di mike.db (ciclo)
    def fixture_id_for_event(self, event_id: str) -> Optional[int]:
        voce = self._fresca(self._ponte, str(event_id))
        if voce is not _ASSENTE:
            return voce  # type: ignore[return-value]
        return self._da_ripiego("fixture_id_for_event", str(event_id))

    def fixture_lambdas(self, fixture_id: Optional[int]) -> Optional[tuple]:
        if fixture_id is None:
            return None
        riga = self._fresca(self._fixture, int(fixture_id))
        if riga is _ASSENTE:
            return self._da_ripiego("fixture_lambdas", fixture_id)
        return lambdas_da_riga(riga)

    def fixture_analysis(self, fixture_id: Optional[int]) -> Optional[Dict[str, Any]]:
        if fixture_id is None:
            return None
        riga = self._fresca(self._fixture, int(fixture_id))
        if riga is _ASSENTE:
            return self._da_ripiego("fixture_analysis", fixture_id)
        return riga.get("db_json_analisi")

    def ht_ft_rows(self, league_id: Optional[int]) -> Optional[Righe]:
        if self._replica is not None:
            return self._replica.ht_ft_rows(league_id)
        return self._da_ripiego("ht_ft_rows", league_id)

    def statistiche(self) -> Mapping[str, int]:
        with self._lock:
            return {**self._conti, "eventi": len(self._ponte), "fixture": len(self._fixture)}

    # --------------------------------------------- interni
    def _fresca(self, memoria: Dict[Any, Tuple[float, Any]], chiave: Any) -> Any:
        with self._lock:
            voce = memoria.get(chiave)
            if voce is None or self._orologio() - voce[0] >= self._scadenza:
                self._conti["mancati"] += 1
                return _ASSENTE
            self._conti["colpi"] += 1
            return voce[1]

    def _da_ripiego(self, funzione: str, argomento: Any) -> Any:
        if self._ripiego is None:
            return None
        with self._lock:
            self._conti["ripieghi"] += 1
        return getattr(self._ripiego, funzione)(argomento)

    def _leggi_blocchi(self, tabella: str, colonne: str, colonna: str, valori: Sequence[Any]) -> Tuple[Righe, bool]:
        """Righe di ``tabella`` con ``colonna`` in ``valori``, a blocchi. (righe, tutto_letto)."""
        righe: Righe = []
        ok = True
        for i in range(0, len(valori), BLOCCO_IN):
            try:
                righe.extend(self._cloud.leggi(tabella, {"select": colonne, colonna: list(valori[i:i + BLOCCO_IN])}))
                with self._lock:
                    self._conti["letture_rete"] += 1
            except Exception as ex:  # noqa: BLE001 - il blocco non entra in memoria: ripiego al ciclo
                ok = False
                with self._lock:
                    self._conti["errori"] += 1
                logger.warning("[cache_cloud] %s non letta (%d valori): %s", tabella, len(valori[i:i + BLOCCO_IN]),
                               str(ex)[:120])
        return righe, ok

    def _leggi_ponte(self, eventi: List[str]) -> Dict[str, int]:
        """Come ``mike.db.fixture_id_for_event``: la prima tabella con ``fixture_id`` intero vince.
        Solo i POSITIVI, e solo se le tabelle consultate prima della risposta sono state lette senza
        errori (altrimenti la risposta di oggi potrebbe essere un'altra)."""
        out: Dict[str, int] = {}
        da_cercare = list(eventi)
        for tabella in ("live_follow", "omega_events"):
            if not da_cercare:
                break
            righe, ok = self._leggi_blocchi(tabella, "event_id,fixture_id", "event_id", da_cercare)
            if not ok:
                return out
            per_evento = {str(r.get("event_id")): r.get("fixture_id") for r in righe}
            restano = []
            for ev in da_cercare:
                fid = per_evento.get(ev)
                try:
                    if fid is not None:
                        out[ev] = int(fid)
                        continue
                except (TypeError, ValueError):
                    pass
                restano.append(ev)
            da_cercare = restano
        return out

    def _precarica_fixture(self, fixture_ids: List[int]) -> None:
        if not fixture_ids:
            return
        righe, _ok = self._leggi_blocchi("fixture_predictions", COLONNE_PREMATCH, "fixture_id", fixture_ids)
        adesso = self._orologio()
        with self._lock:
            for r in righe:
                fid = r.get("fixture_id")
                if fid is not None and int(fid) in fixture_ids and lambdas_da_riga(r)[0] is not None:
                    self._fixture[int(fid)] = (adesso, r)     # solo la riga CON i gol attesi
