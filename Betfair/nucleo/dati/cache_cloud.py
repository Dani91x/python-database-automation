"""Cache degli algoritmi del cloud fuori dal ciclo di decisione (comparto G, tappa T7).

Scopo
    Togliere dal ciclo di decisione le letture SINCRONE del cloud degli algoritmi che restano nel
    cloud (G parte 2, 04 par. 6.3) senza cambiare un valore ne' una scadenza:
      * tabella HT->FT (RPC ``get_omega_ht_ft``) e tabella per minuto (RPC ``get_omega_minute_ft``)
        di Omega (G-035) e di Mike (G-034): ``ReplicaEmpirica``, prefetch per lega di TUTTI i
        bucket, riletta dopo ogni ricostruzione notturna del pg_cron delle 04:00 UTC
        (``built_at`` di ``omega_ht_ft_transitions``);
      * dossier pre-match di Mike (G-033): ``DossierPrematch``, ponte evento->fixture e righe di
        ``fixture_predictions`` lette a blocchi PRIMA dell'aggancio (``lambda_home/away``, ``rho``,
        ``p4_pre``, ``p_under35_cal`` restano calcolati da ``mike/dossier.build_prematch``).

Le scadenze di oggi NON cambiano (U-53): la cache di Omega scade dopo 6 h
(``omega_service.EMPIRICAL_CACHE_TTL_S``) e quella di Mike mai (``mike/dossier._EMPIRICAL_CACHE``):
restano NEI BOT, sopra questa replica, che risponde con le STESSE firme delle funzioni di oggi
(``omega_db.ht_ft_transitions``/``minute_transitions``, ``mike.db.fixture_id_for_event``/
``fixture_lambdas``/``fixture_analysis``/``ht_ft_rows``) e con le STESSE righe dell'RPC, compresa la
distinzione "[] = vuota, None = errore (mai in cache)".

Entrate: un ``Cloud`` (``cloud.ClienteCloud``), le leghe e gli eventi da preparare.
Uscite: righe identiche a quelle delle RPC/letture di oggi, servite dalla memoria.

Cosa NON fa
    Non importa nessun bot (le funzioni di oggi sono gli ARBITRI nei test). Non decide nulla. Non
    apre thread all'import: il thread di prefetch e sorveglianza nasce solo con ``avvia`` e muore con
    ``ferma``. Un mancato prefetch (chiave assente) va al ``ripiego`` (la funzione di oggi, sincrona,
    identica) se c'e', altrimenti risponde None come un errore di oggi (mai in cache) e chiede il
    prefetch: e' l'unico punto in cui il nuovo puo' differire, e l'ombra (ondata 2,
    ``ARCH_PREFETCH_<BOT>=vecchio|ombra|nuovo``) lo misura.
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
#: scadenze delle cache DEI BOT, che restano nei bot (U-53): qui solo dichiarate
SCADENZA_OMEGA_S = 6 * 3600.0        # omega_service.EMPIRICAL_CACHE_TTL_S
SCADENZA_MIKE_S: Optional[float] = None  # mike/dossier._EMPIRICAL_CACHE: mai
#: ogni quanto il thread rilegge ``built_at`` (ricostruzione del pg_cron delle 04:00 UTC)
INTERVALLO_SORVEGLIANZA_S = 300.0
#: il dossier si rinfresca ogni ora (G par. 4.4: "all'avvio dell'app e ogni ora")
SCADENZA_DOSSIER_S = 3600.0
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

    def built_at(self) -> Optional[str]:
        """Istante dell'ultima ricostruzione (``omega_ht_ft_transitions.built_at`` massimo; la
        stessa notte ricostruisce anche la tabella per minuto). None se non leggibile."""
        try:
            righe = self._cloud.leggi("omega_ht_ft_transitions",
                                      {"select": "built_at", "order": "built_at.desc", "limit": 1})
        except Exception as ex:  # noqa: BLE001 - la sorveglianza riprova al prossimo giro
            logger.warning("[cache_cloud] built_at non leggibile: %s", str(ex)[:120])
            return None
        return str(righe[0].get("built_at")) if righe and righe[0].get("built_at") is not None else None


# ---------------------------------------------------------------------------
# 2. Replica delle tabelle empiriche (prefetch per lega, rilettura dopo built_at)
# ---------------------------------------------------------------------------
Chiave = Tuple[Any, ...]   # ("ht_ft", lega) | ("minuti", lega, bucket, target)
_FINE = object()           # sentinella di ``ferma`` nella coda (None e' una lega valida: il globale)


@dataclass(frozen=True)
class EsitoPrefetch:
    lette: int
    errori: int


class ReplicaEmpirica:
    """Memoria delle righe delle due RPC per chiave. Le letture (``ht_ft_transitions``,
    ``minute_transitions``, ``ht_ft_rows``) NON vanno in rete se la chiave e' pronta; il
    riempimento avviene in ``prefetch_lega`` (thread di ``avvia`` o chiamata esplicita)."""

    def __init__(self, sorgente: SorgenteOmega, *, ripiego_sincrono: bool = True,
                 intervallo_sorveglianza_s: float = INTERVALLO_SORVEGLIANZA_S) -> None:
        self._sorgente = sorgente
        self._ripiego = ripiego_sincrono
        self._intervallo = float(intervallo_sorveglianza_s)
        self._lock = threading.Lock()
        self._righe: Dict[Chiave, List[Dict[str, Any]]] = {}
        self._leghe: set = set()
        self._built_at: Optional[str] = None
        self._coda: "queue.Queue[Any]" = queue.Queue()
        self._ferma = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._conti: Dict[str, int] = {"colpi": 0, "mancati": 0, "ripieghi": 0, "letture_rete": 0,
                                       "ricostruzioni": 0, "errori": 0}

    # --------------------------------------------- firme di omega_db / mike.db (ciclo di decisione)
    def ht_ft_transitions(self, league_id: Optional[int]) -> Optional[List[Dict[str, Any]]]:
        lega = _lega(league_id)
        return self._servi(("ht_ft", lega), lambda: self._sorgente.ht_ft(lega), lega)

    def minute_transitions(self, league_id: Optional[int], bucket: int, target: str) -> Optional[List[Dict[str, Any]]]:
        lega = _lega(league_id)
        chiave = ("minuti", lega, int(bucket), str(target))
        return self._servi(chiave, lambda: self._sorgente.minuti(lega, int(bucket), str(target)), lega)

    def ht_ft_rows(self, league_id: Optional[int]) -> Optional[List[Dict[str, Any]]]:
        """Firma di ``mike.db.ht_ft_rows`` (che delega a ``omega_db.ht_ft_transitions``)."""
        return self.ht_ft_transitions(league_id)

    # --------------------------------------------- riempimento (fuori dal ciclo)
    def prefetch_lega(self, league_id: Optional[int]) -> EsitoPrefetch:
        """Legge HT->FT e TUTTI i bucket (FT 0..85, HT 0..40) della lega. Gli errori non entrano."""
        lega = _lega(league_id)
        with self._lock:
            self._leghe.add(lega)
        lette = errori = 0
        for chiave, leggi in self._chiavi_di(lega):
            righe = leggi()
            with self._lock:
                self._conti["letture_rete"] += 1
                if righe is None:
                    self._conti["errori"] += 1
                else:
                    self._righe[chiave] = righe
            lette += righe is not None
            errori += righe is None
        return EsitoPrefetch(lette, errori)

    def richiedi_prefetch(self, league_id: Optional[int]) -> None:
        """Accoda la lega al thread (non blocca). Senza thread avviato resta in coda."""
        self._coda.put(_lega(league_id))

    def controlla_ricostruzione(self) -> bool:
        """Legge ``built_at``: se e' cambiato rilegge TUTTE le chiavi delle leghe note e sostituisce
        la memoria in un colpo (le chiavi che falliscono escono: errore = mai in cache)."""
        nuovo = self._sorgente.built_at()
        if nuovo is None:
            return False
        with self._lock:
            vecchio = self._built_at
            leghe = sorted(self._leghe, key=lambda x: (x is None, x))
        if vecchio == nuovo:
            return False
        fresche: Dict[Chiave, List[Dict[str, Any]]] = {}
        for lega in leghe:
            for chiave, leggi in self._chiavi_di(lega):
                righe = leggi()
                if righe is not None:
                    fresche[chiave] = righe
        with self._lock:
            self._righe = fresche
            self._built_at = nuovo
            self._conti["ricostruzioni"] += vecchio is not None
        if vecchio is not None:
            logger.info("[cache_cloud] ricostruzione notturna %s -> %s: %d chiavi rilette", vecchio, nuovo,
                        len(fresche))
        return vecchio is not None

    # --------------------------------------------- thread
    def avvia(self) -> None:
        """Thread di prefetch (coda) e sorveglianza di ``built_at`` (ogni ``intervallo``)."""
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
                    "built_at": self._built_at}

    # --------------------------------------------- interni
    def _chiavi_di(self, lega: Optional[int]) -> List[Tuple[Chiave, Callable[[], Optional[List[Dict[str, Any]]]]]]:
        s = self._sorgente
        out: List[Tuple[Chiave, Callable[[], Optional[List[Dict[str, Any]]]]]] = [
            (("ht_ft", lega), lambda: s.ht_ft(lega))]
        for target, bucket_di in (("ft", BUCKET_FT), ("ht", BUCKET_HT)):
            for b in bucket_di:
                out.append((("minuti", lega, b, target), lambda b=b, t=target: s.minuti(lega, b, t)))
        return out

    def _servi(self, chiave: Chiave, leggi: Callable[[], Optional[List[Dict[str, Any]]]],
               lega: Optional[int]) -> Optional[List[Dict[str, Any]]]:
        with self._lock:
            righe = self._righe.get(chiave)
            if righe is not None:
                self._conti["colpi"] += 1
                return _copia(righe)
            self._conti["mancati"] += 1
            nota = lega in self._leghe
        if not nota:
            self.richiedi_prefetch(lega)
        if not self._ripiego:
            return None                               # come un errore di oggi: il bot riprova
        righe = leggi()
        with self._lock:
            self._conti["ripieghi"] += 1
            self._conti["letture_rete"] += 1
            if righe is not None:
                self._righe[chiave] = righe
        return _copia(righe)

    def _giro(self) -> None:
        prossima = 0.0
        while not self._ferma.is_set():
            adesso = time.monotonic()
            if adesso >= prossima:
                try:
                    self.controlla_ricostruzione()
                except Exception:  # noqa: BLE001 - il thread non muore: si logga e si riprova
                    logger.exception("[cache_cloud] sorveglianza built_at fallita")
                prossima = adesso + self._intervallo
            try:
                lega = self._coda.get(timeout=max(0.05, min(1.0, prossima - time.monotonic())))
            except queue.Empty:
                continue
            if lega is _FINE or self._ferma.is_set():
                break
            try:
                self.prefetch_lega(lega)
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


_ASSENTE = object()   # riga letta e assente (risposta valida, diversa da "non letta")


class DossierPrematch:
    """Le letture del dossier di Mike preparate PRIMA dell'aggancio, con le firme di ``mike.db``
    usate da ``mike/dossier.build_prematch``. Chiave non pronta o scaduta -> ``ripiego`` (il modulo
    ``mike.db`` di oggi, sincrono) o None se non c'e'."""

    def __init__(self, cloud: Cloud, *, replica: Optional[ReplicaEmpirica] = None, ripiego: Any = None,
                 orologio: Callable[[], float] = time.time, scadenza_s: float = SCADENZA_DOSSIER_S) -> None:
        self._cloud = cloud
        self._replica = replica
        self._ripiego = ripiego
        self._orologio = orologio
        self._scadenza = float(scadenza_s)
        self._lock = threading.Lock()
        self._ponte: Dict[str, Tuple[float, Optional[int]]] = {}
        self._fixture: Dict[int, Tuple[float, Any]] = {}
        self._conti: Dict[str, int] = {"colpi": 0, "mancati": 0, "ripieghi": 0, "letture_rete": 0, "errori": 0}

    # --------------------------------------------- preparazione (fuori dal ciclo)
    def precarica(self, event_ids: Iterable[str]) -> int:
        """Ponte evento->fixture (``live_follow`` poi ``omega_events``) e righe di
        ``fixture_predictions`` per gli eventi dati, a blocchi. Ritorna gli eventi pronti."""
        eventi = sorted({str(e) for e in event_ids})
        ponte = self._leggi_ponte(eventi)
        adesso = self._orologio()
        with self._lock:
            for ev, fid in ponte.items():
                self._ponte[ev] = (adesso, fid)
        self._precarica_fixture(sorted({f for f in ponte.values() if f is not None}))
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
        return lambdas_da_riga(riga) if riga is not None else None

    def fixture_analysis(self, fixture_id: Optional[int]) -> Optional[Dict[str, Any]]:
        if fixture_id is None:
            return None
        riga = self._fresca(self._fixture, int(fixture_id))
        if riga is _ASSENTE:
            return self._da_ripiego("fixture_analysis", fixture_id)
        return riga.get("db_json_analisi") if riga is not None else None

    def ht_ft_rows(self, league_id: Optional[int]) -> Optional[List[Dict[str, Any]]]:
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

    def _leggi_blocchi(self, tabella: str, colonne: str, colonna: str, valori: Sequence[Any]) -> Tuple[List[Dict[str, Any]], bool]:
        """Righe di ``tabella`` con ``colonna`` in ``valori``, a blocchi. (righe, tutto_letto)."""
        righe: List[Dict[str, Any]] = []
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

    def _leggi_ponte(self, eventi: List[str]) -> Dict[str, Optional[int]]:
        """Come ``mike.db.fixture_id_for_event``: la prima tabella con ``fixture_id`` non nullo vince.
        Un evento entra in memoria SOLO se le tabelle consultate fino alla risposta sono state lette
        senza errori (altrimenti la risposta di oggi potrebbe essere diversa)."""
        out: Dict[str, Optional[int]] = {}
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
        for ev in da_cercare:
            out[ev] = None
        return out

    def _precarica_fixture(self, fixture_ids: List[int]) -> None:
        if not fixture_ids:
            return
        righe, ok = self._leggi_blocchi("fixture_predictions", COLONNE_PREMATCH, "fixture_id", fixture_ids)
        adesso = self._orologio()
        per_fixture = {int(r["fixture_id"]): r for r in righe if r.get("fixture_id") is not None}
        with self._lock:
            for fid in fixture_ids:
                if fid in per_fixture:
                    self._fixture[fid] = (adesso, per_fixture[fid])
                elif ok:
                    self._fixture[fid] = (adesso, None)       # letta e assente: risposta valida
