"""scan_feed.py — punteggi/timeline dal FEED UNICO dello scanner Safe Strategy.

PERCHÉ (audit 09/09): lo scanner ``Betfair/safe_strategy`` interroga già l'IPS
Betfair in BATCH (chunk da 20, ogni 3s, tutti gli in-play calcio+tennis, più la
timeline calcio ogni 30s) e pubblica lo stato grezzo su ``safe_strategy_scan``.
I runner (calcio, tennis) facevano per OGNI evento seguito le stesse chiamate
(``get_scores([1 evento])`` ogni 5s/2s + ``get_event_timeline``) verso un
endpoint NON ufficiale senza rate-limit dichiarato: ~231 chiamate/min di cui
l'84% ridondanti. Qui i runner LEGGONO ciò che lo scanner ha già scaricato
(stesso pattern con cui Omega legge ``live_now``), con FALLBACK automatico alla
chiamata diretta quando la riga manca o è stantia (scanner giù, evento fuori dal
suo catalogo, pre-match): mai un buco dati, mai un punteggio vecchio.

Fedeltà: lo scanner salva lo ``state`` IPS INTEGRALE (``score_raw``): il runner
lo parsa con gli STESSI parser di sempre (``parse_score_dict`` calcio,
``parse_tennis_scores`` tennis) → nessuna differenza di formato.

Efficienza: UNA SELECT per ciclo per tutti gli eventi richiesti (cache con TTL
breve, condivisa fra i poller dello stesso processo), non una per evento.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from .base import ScoreSnapshot
from .betfair_inplay import BetfairInPlayProvider, parse_score_dict

logger = logging.getLogger(__name__)

SCAN_TABLE = "safe_strategy_scan"
STATUS_TABLE = "safe_strategy_status"
# heartbeat dello scanner più vecchio di così = scanner fermo: le righe non
# sono più affidabili anche se presenti (write-on-change: nessuna riscrittura)
SCANNER_ALIVE_MAX_AGE_SEC = 30.0
# riga più vecchia di così = stantia (scanner fermo/lento): si torna alla chiamata
# diretta. Lo scanner pubblica i cambi di punteggio SUBITO (fuori throttle) con
# poll IPS a 3s: 15s è ampiamente sopra la cadenza normale.
DEFAULT_MAX_AGE_SEC = 15.0
# LIMITE ASSOLUTO di eta' della riga: vale ANCHE con lo scanner vivo. Lo scanner
# riscrive la riga a ogni cambio di quota/punteggio/minuto (throttle 2.5 s), e il
# minuto entra nella firma critica: in-play una riga piu' vecchia di questo
# limite NON significa "non e' cambiato nulla", significa che il feed di QUEL
# singolo evento si e' fermato (IPS muto per il suo chunk, evento uscito dal
# catalogo e non ancora ripulito) mentre lo scanner resta vivo per gli altri.
# Senza questo tetto un punteggio fermo da ore veniva servito come fresco.
# Override: SCAN_FEED_HARD_MAX_AGE_SEC (env vuota = default, mai `??`).
def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        v = float(raw)
    except ValueError:
        return default
    return v if v > 0 else default


HARD_MAX_AGE_SEC = _env_float("SCAN_FEED_HARD_MAX_AGE_SEC", 180.0)
# RITARDO NOTO dell'IPS Betfair sul campo: il punteggio arriva 2-3 s dopo il
# fatto reale. Va SOMMATO all'eta' della riga per sapere quanto e' vecchio
# davvero il punteggio che si sta usando (vedi ``score_age_sec``).
IPS_SCORE_LAG_SEC = 3.0
# una SELECT al massimo ogni TTL per l'insieme di eventi richiesti
DEFAULT_CACHE_TTL_SEC = 1.0
# eventi non più richiesti da tanto escono dall'insieme letto
_WANTED_EXPIRE_SEC = 120.0

# ===========================================================================
# PUNTEGGI_CANALE (23/09) - le righe del feed dal CANALE LOCALE dello scanner
# ===========================================================================
# Regola permanente dell'utente (23/09): chi opera live legge dal canale locale
# al tick, il DB e' SOLO il ripiego quando il canale tace, e i punteggi hanno
# UN SOLO poll per tutti i consumatori.
#
# Il poll esterno e' GIA' unico: lo scanner (``safe_strategy/service.py``,
# ``ScoreFeedWorker``) interroga l'IPS in batch ogni 2 s per tutti gli in-play,
# e la riga che scrive su ``safe_strategy_scan`` porta GIA' minuto, punteggio,
# rossi, ``score_raw`` e ``timeline``. Dal 18/09 la STESSA riga esce anche sul
# canale 47336 (``scan_calcio``/``scan_tennis``) a ogni cambio, prima del freno
# di scrittura del DB, e il battito esce su ``scanner_stato``. Nessun topic
# nuovo, quindi: un topic ``punteggi`` sarebbe un secondo messaggio con lo
# stesso dato. Qui si toglie il poll DUPLICATO, cioe' la SELECT di
# ``safe_strategy_scan``/``safe_strategy_status`` che OGNI processo (runner
# calcio, runner tennis, Omega, Mike) rifaceva ogni secondo.
#
# Il contratto e' quello di ``canale_scan`` (F4 del bot Safe), riusato e non
# riscritto: il DATABASE resta la LISTA (il canale non aggiunge partite) e il
# ripiego; la riga del canale sostituisce quella del DB solo se STRETTAMENTE
# piu' recente e con ``odds_ts_ms`` numerico (``canale_scan.piu_recente``).
# La freschezza si giudica poi con le stesse funzioni di sempre
# (``fresh_payload``/``row_age_sec``): nessun privilegio per il canale.
#
# Interruttore ``PUNTEGGI_CANALE``: default SPENTO, acceso solo se scritto
# (``1``/``true``/``si``/``yes``, regola di ``canale_bot.acceso``). Spento, la
# cache e' quella di prima istruzione per istruzione: nessun client aperto,
# stessa SELECT alla stessa cadenza.
ENV_PUNTEGGI_CANALE = "PUNTEGGI_CANALE"
# Con il canale VIVO (battito dello scanner arrivato da <= 30 s) e TUTTI gli
# eventi richiesti coperti dal canale, il DB si rilegge come RIALLINEAMENTO
# ogni tanti secondi invece che a ogni TTL. Stesso numero del bot Safe
# (``bot_service._RISINC_DB_S``): nessun numero nuovo.
RISINC_DB_CANALE_SEC = 10.0


def punteggi_canale_acceso() -> bool:
    """L'interruttore, letto a OGNI chiamata (mai memorizzato)."""
    from Betfair.stream.canale_bot import acceso

    return acceso(ENV_PUNTEGGI_CANALE)


_LETTORE: Optional[Any] = None
_LETTORE_LOCK = threading.Lock()


def lettore_canale() -> Optional[Any]:
    """Il client del canale dello scanner di QUESTO processo, o ``None``.

    Uno per processo, avviato alla prima richiesta con l'interruttore acceso:
    e' un CLIENT della porta che lo scanner gia' possiede (47336), non una
    porta nuova e non un processo nuovo. Con l'interruttore spento non importa
    nemmeno ``websockets``. Non solleva MAI: senza lettore si lavora come oggi.
    """
    global _LETTORE  # noqa: PLW0603 - singleton di processo
    if not punteggi_canale_acceso():
        return None
    with _LETTORE_LOCK:
        if _LETTORE is not None:
            return _LETTORE
        try:
            from Betfair.safe_strategy import canale_scan as CS

            client = CS.ClientScan(CS.porta_scan(), CS.CacheScan())
            client.avvia()
            _LETTORE = client
            logger.info("[scan-feed] PUNTEGGI_CANALE acceso: righe del feed dal "
                        "canale locale %d (il DB resta la lista e il ripiego)",
                        client.porta)
        except Exception as e:  # noqa: BLE001 - senza canale si lavora come oggi
            logger.warning("[scan-feed] lettore del canale NON avviato: %s", str(e)[:160])
            return None
        return _LETTORE


def azzera_lettore_canale() -> None:
    """Spegne e dimentica il lettore di processo. Per i test e il riavvio."""
    global _LETTORE  # noqa: PLW0603
    with _LETTORE_LOCK:
        client = _LETTORE
        _LETTORE = None
    if client is not None:
        try:
            client.ferma()
        except Exception:  # noqa: BLE001
            pass


def canale_vivo(lettore: Optional[Any]) -> bool:
    """Il canale conta SOLO se: interruttore acceso, lettore presente, battito
    dello scanner arrivato su quel lettore da non piu' di
    ``SCANNER_ALIVE_MAX_AGE_SEC`` (la stessa soglia con cui oggi si dice
    "scanner vivo" dal DB). Altrimenti il canale TACE e si legge il DB come
    oggi. Non solleva mai."""
    if lettore is None or not punteggi_canale_acceso():
        return False
    try:
        eta = lettore.eta_stato_s()
    except Exception:  # noqa: BLE001
        return False
    return eta is not None and float(eta) <= SCANNER_ALIVE_MAX_AGE_SEC


def _parse_ts(value: Any) -> Optional[float]:
    """ISO8601 (Postgres timestamptz) → epoch UTC; None se malformato."""
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


class ScanRowCache:
    """Cache per-processo delle righe ``safe_strategy_scan`` degli eventi richiesti.

    ``rows_for(event_ids)`` ritorna ``{event_id: row}``; la SELECT viene rifatta
    al massimo ogni ``ttl_sec`` sull'UNIONE degli eventi richiesti di recente, così
    N poller dello stesso processo costano UNA query, non N. Thread-safe.
    ``fetch`` iniettabile (test senza DB).
    """

    def __init__(
        self,
        ttl_sec: float = DEFAULT_CACHE_TTL_SEC,
        fetch: Optional[Callable[[List[str]], List[Dict[str, Any]]]] = None,
        clock: Callable[[], float] = time.monotonic,
        fetch_status: Optional[Callable[[], Optional[Dict[str, Any]]]] = None,
        canale: Optional[Any] = None,
        canale_auto: bool = False,
    ) -> None:
        # PUNTEGGI_CANALE: ``canale`` = un lettore con ``cache`` (CacheScan) ed
        # ``eta_stato_s()`` (``canale_scan.ClientScan``), iniettabile nei test;
        # ``canale_auto`` = prendere il lettore di processo (``lettore_canale``)
        # alla prima chiamata con l'interruttore acceso. Default: niente canale,
        # cioe' la cache di sempre.
        self._canale = canale
        self._canale_auto = bool(canale_auto)
        # il giro precedente ha trovato TUTTI gli eventi richiesti coperti dal
        # canale? Solo allora il DB si rilegge al passo del riallineamento.
        self._coperti_dal_canale = False
        self.dal_canale = 0
        self._ttl = max(0.0, float(ttl_sec))
        self._fetch = fetch or _fetch_rows
        self._fetch_status_fn = fetch_status
        self._clock = clock
        self._lock = threading.Lock()
        self._rows: Dict[str, Dict[str, Any]] = {}
        self._wanted: Dict[str, float] = {}   # event_id → ultimo monotonic richiesto
        self._loaded_at = -1e9
        self._pending: Set[str] = set()       # richiesti dopo l'ultima SELECT
        self._status_row: Optional[Dict[str, Any]] = None
        self._status_loaded_at = -1e9

    # ------------------------------------------------------ PUNTEGGI_CANALE
    def _lettore(self) -> Optional[Any]:
        if self._canale is None and self._canale_auto:
            self._canale = lettore_canale()
        return self._canale

    def canale_vivo(self) -> bool:
        """True se le righe di questa cache vengono (anche) dal canale adesso.
        Spento l'interruttore e' sempre False, senza toccare nessun lettore."""
        if not punteggi_canale_acceso():
            return False
        return canale_vivo(self._lettore())

    def _fondi_canale(self, lettore: Any, ids: List[str],
                      out: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Le righe del DB con quelle del canale al posto delle piu' vecchie.

        Si itera sulle righe del DB (il canale non aggiunge partite) e decide
        ``canale_scan.piu_recente`` (a parita' e nel dubbio vince il DB). Qui si
        stabilisce anche se il DB si puo' rileggere al passo lento: SOLO se ogni
        evento richiesto e' coperto (riga del canale almeno recente quanto
        quella del DB e con ``odds_ts_ms`` numerico), oppure non esiste ne' sul
        DB ne' sul canale. Un evento che il canale non copre tiene il DB alla
        cadenza di oggi: mai un punteggio piu' vecchio di prima. Non solleva.
        """
        try:
            from Betfair.safe_strategy import canale_scan as CS

            coperti = True
            fuori = dict(out)
            for eid in ids:
                eid = str(eid)
                dal_db = out.get(eid)
                cand = lettore.cache.riga(eid)
                if dal_db is None:
                    if cand is not None:
                        coperti = False     # il canale la vede, il DB non ancora
                    continue
                if not copre(dal_db, cand):
                    coperti = False
                scelta = CS.piu_recente(dal_db, cand)
                if cand is not None and scelta is cand:
                    fuori[eid] = cand
                    self.dal_canale += 1
            self._coperti_dal_canale = coperti
            return fuori
        except Exception as e:  # noqa: BLE001 - il canale non ferma mai il feed
            logger.debug("[scan-feed] fusione col canale KO: %s", str(e)[:120])
            self._coperti_dal_canale = False
            return out

    def rows_for(self, event_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        # PUNTEGGI_CANALE: valutato FUORI dal lock (legge l'ambiente e il
        # lettore). Spento -> ``lettore`` None e tutto cio' che segue e' la
        # cache di sempre, istruzione per istruzione.
        lettore = self._lettore() if punteggi_canale_acceso() else None
        vivo = canale_vivo(lettore)
        if not vivo:
            self._coperti_dal_canale = False
        ttl = max(self._ttl, RISINC_DB_CANALE_SEC) if (vivo and self._coperti_dal_canale) \
            else self._ttl
        now = self._clock()
        with self._lock:
            for eid in event_ids:
                eid = str(eid)
                if eid not in self._wanted:
                    self._pending.add(eid)
                self._wanted[eid] = now
            # prune degli eventi non più richiesti
            for eid in [e for e, t in self._wanted.items() if now - t > _WANTED_EXPIRE_SEC]:
                self._wanted.pop(eid, None)
                self._rows.pop(eid, None)
            stale = now - self._loaded_at >= ttl
            if stale or self._pending:
                ids = sorted(self._wanted)
                self._pending.clear()
                self._loaded_at = now
                try:
                    fetched = self._fetch(ids) if ids else []
                    self._rows = {
                        str(r.get("event_id")): r for r in fetched
                        if isinstance(r, dict) and r.get("event_id") is not None
                    }
                except Exception as e:  # noqa: BLE001 - DB KO: si usa il fallback diretto
                    logger.debug("[scan-feed] SELECT KO (fallback diretto): %s", str(e)[:120])
                    self._rows = {}
            out = {str(e): self._rows[str(e)] for e in event_ids if str(e) in self._rows}
        if vivo:
            return self._fondi_canale(lettore, [str(e) for e in event_ids], out)
        return out

    def scanner_age_sec(self) -> Optional[float]:
        """Età del heartbeat dello scanner (None = mai visto / DB KO). Letto al
        massimo ogni TTL: serve a dire se una riga NON riscritta di recente è
        comunque valida (scanner vivo = write-on-change, la riga è l'ultimo stato).

        PUNTEGGI_CANALE: con il canale vivo l'eta' e' quella del battito
        ``scanner_stato`` arrivato sul canale, senza SELECT di
        ``safe_strategy_status``. Canale muto = la lettura di oggi."""
        if punteggi_canale_acceso():
            lettore = self._lettore()
            if canale_vivo(lettore):
                try:
                    return lettore.eta_stato_s()
                except Exception:  # noqa: BLE001 - si ripiega sul DB
                    pass
        now = self._clock()
        with self._lock:
            if now - self._status_loaded_at >= self._ttl:
                self._status_loaded_at = now
                try:
                    self._status_row = (self._fetch_status_fn or _fetch_status)()
                except Exception as e:  # noqa: BLE001
                    logger.debug("[scan-feed] status KO: %s", str(e)[:120])
                    self._status_row = None
            row = self._status_row
        return row_age_sec(row) if row else None

    def scanner_alive(self) -> bool:
        age = self.scanner_age_sec()
        return age is not None and age <= SCANNER_ALIVE_MAX_AGE_SEC

    def payload_if_fresh(self, event_id: str, max_age_sec: float = DEFAULT_MAX_AGE_SEC) -> Optional[Dict[str, Any]]:
        """Payload dell'evento se AFFIDABILE: riga riscritta entro max_age, oppure
        scanner vivo (heartbeat fresco → la riga presente è l'ultimo stato)."""
        row = self.rows_for([str(event_id)]).get(str(event_id))
        return fresh_payload(row, max_age_sec, scanner_age_sec=self.scanner_age_sec())

    def row_age_for(self, event_id: str) -> Optional[float]:
        """Età REALE (secondi) della riga del feed per l'evento; None se la riga
        manca o il timestamp è illeggibile. Serve a DICHIARARE la freschezza,
        non solo a filtrarla."""
        row = self.rows_for([str(event_id)]).get(str(event_id))
        return row_age_sec(row) if row else None


def copre(dal_db: Dict[str, Any], dal_canale: Optional[Dict[str, Any]]) -> bool:
    """La riga del canale COPRE quella del DB: esiste, dichiara l'istante del
    proprio prezzo (``odds_ts_ms`` numerico, invariante B11) ed e' recente
    ALMENO quanto la riga del DB (a parita' e' la stessa riga: lo scanner
    spinge sul canale lo stesso oggetto che scrive). Serve SOLO a decidere il
    passo di rilettura del DB, non quale riga si usa (quello lo decide
    ``canale_scan.piu_recente``)."""
    if not isinstance(dal_canale, dict):
        return False
    payload = dal_canale.get("payload")
    ots = payload.get("odds_ts_ms") if isinstance(payload, dict) else None
    if not isinstance(ots, (int, float)) or isinstance(ots, bool):
        return False
    a = _parse_ts(dal_db.get("updated_at"))
    b = _parse_ts(dal_canale.get("updated_at"))
    return a is not None and b is not None and b >= a


def _fetch_status() -> Optional[Dict[str, Any]]:
    from db_client import get_supabase_client

    sb = get_supabase_client()
    res = sb.table(STATUS_TABLE).select("id,payload,updated_at").eq("id", "scanner").execute()
    data = getattr(res, "data", None) or []
    return data[0] if data else None


def _fetch_rows(event_ids: List[str]) -> List[Dict[str, Any]]:
    from db_client import get_supabase_client

    sb = get_supabase_client()
    res = (
        sb.table(SCAN_TABLE)
        .select("event_id,sport,payload,updated_at")
        .in_("event_id", event_ids)
        .execute()
    )
    return getattr(res, "data", None) or []


# cache condivisa del processo (un runner = un processo)
_SHARED_CACHE: Optional[ScanRowCache] = None
_SHARED_LOCK = threading.Lock()


def shared_cache() -> ScanRowCache:
    global _SHARED_CACHE  # noqa: PLW0603 - singleton di processo
    with _SHARED_LOCK:
        if _SHARED_CACHE is None:
            # PUNTEGGI_CANALE: la cache di processo prende il lettore del canale
            # da sola, alla prima chiamata con l'interruttore acceso.
            _SHARED_CACHE = ScanRowCache(canale_auto=True)
        return _SHARED_CACHE


def row_age_sec(row: Dict[str, Any], now_epoch: Optional[float] = None) -> Optional[float]:
    ts = _parse_ts(row.get("updated_at"))
    if ts is None:
        return None
    return max(0.0, (now_epoch if now_epoch is not None else time.time()) - ts)


def fresh_payload(
    row: Optional[Dict[str, Any]], max_age_sec: float, now_epoch: Optional[float] = None,
    scanner_age_sec: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Payload della riga se AFFIDABILE, altrimenti None. PURA.

    Affidabile = riga riscritta entro ``max_age_sec`` OPPURE scanner vivo
    (``scanner_age_sec`` ≤ SCANNER_ALIVE_MAX_AGE_SEC): lo scanner scrive
    write-on-change, quindi con lo scanner vivo una riga vecchia è semplicemente
    un evento in cui nulla è cambiato (0-0 fermo), non un dato stantio.

    MA con un TETTO ASSOLUTO (``HARD_MAX_AGE_SEC``): oltre quello nemmeno lo
    scanner vivo rende buona la riga — è il feed di QUEL evento che si è fermato.
    Meglio la chiamata diretta che un punteggio vecchio spacciato per fresco."""
    if not row:
        return None
    age = row_age_sec(row, now_epoch)
    if age is None:
        return None
    # il tetto non può essere più stretto di quello chiesto esplicitamente dal
    # chiamante: max_age_sec resta la soglia "normale", HARD è solo il limite
    # oltre il quale cade anche la deroga "scanner vivo".
    if age > max(float(max_age_sec), HARD_MAX_AGE_SEC):
        return None
    alive = scanner_age_sec is not None and scanner_age_sec <= SCANNER_ALIVE_MAX_AGE_SEC
    if age > max_age_sec and not alive:
        return None
    payload = row.get("payload")
    return payload if isinstance(payload, dict) else None


class ScanFeedScoreProvider:
    """ScoreProvider PRIMARIO dei runner: legge dal feed dello scanner, altrimenti
    delega alla chiamata IPS diretta (``direct``). Espone anche ``get_raw_state``
    (tennis: parser proprio) e ``get_timeline`` (calcio)."""

    name = "scan_feed"

    def __init__(
        self,
        direct: BetfairInPlayProvider,
        max_age_sec: float = DEFAULT_MAX_AGE_SEC,
        cache: Optional[ScanRowCache] = None,
    ) -> None:
        self.direct = direct
        self.max_age_sec = float(max_age_sec)
        self._cache = cache or shared_cache()
        self.feed_hits = 0
        self.direct_calls = 0

    # ------------------------------------------------------------ lettura feed
    def fresh_payload(self, event_id: str) -> Optional[Dict[str, Any]]:
        return self._cache.payload_if_fresh(event_id, self.max_age_sec)

    # ------------------------------------------------------------- freschezza
    def feed_age_sec(self, event_id: str) -> Optional[float]:
        """Età (secondi) della riga del feed per l'evento; None se assente."""
        return self._cache.row_age_for(event_id)

    def score_age_sec(self, event_id: str) -> Optional[float]:
        """Età ONESTA del PUNTEGGIO servito: età della riga PIÙ il ritardo noto
        dell'IPS Betfair (``IPS_SCORE_LAG_SEC``, 2-3 s fra il gol sul campo e il
        dato pubblicato). Chi decide con soldi veri deve vedere questo numero,
        non solo l'età della riga. None se la riga non c'è (dato dal diretto)."""
        age = self.feed_age_sec(event_id)
        return None if age is None else age + IPS_SCORE_LAG_SEC

    def get_raw_state(self, event_id: str) -> Optional[Dict[str, Any]]:
        """``state`` IPS grezzo dell'evento dal feed (None = assente/stantio)."""
        p = self.fresh_payload(event_id)
        raw = p.get("score_raw") if p else None
        if isinstance(raw, dict):
            self.feed_hits += 1
            return raw
        return None

    # ------------------------------------------------------- ScoreProvider API
    def get_score(self, event_id: str) -> Optional[ScoreSnapshot]:
        raw = self.get_raw_state(event_id)
        if raw is not None:
            return parse_score_dict(str(event_id), raw)
        self.direct_calls += 1
        return self.direct.get_score(event_id)

    def get_timeline(self, event_id: str) -> List[Dict[str, Any]]:
        p = self.fresh_payload(event_id)
        tl = p.get("timeline") if p else None
        if isinstance(tl, list):
            return [x for x in tl if isinstance(x, dict)]
        self.direct_calls += 1
        return self.direct.get_timeline(event_id)

    def healthcheck(self) -> bool:
        return self.direct.healthcheck()
