"""Accesso Supabase per il sottosistema live TENNIS (service_role, bypassa RLS).

Mirror di ``Betfair/stream/db.py`` (calcio) ma su storage tennis DEDICATO: qui si
scrivono SOLO tabelle ``tennis_*``. Nessuna riga/tabella/RPC del calcio.

CLIENT PER-THREAD: il runner tennis gira più worker flumine (ladder, score/now,
bot-control, ordini) su thread distinti. supabase-py/httpx non è garantito
thread-safe sotto carico → ogni thread usa la PROPRIA istanza di client
(``threading.local``), tutte con la service-role key da ``config``.

Tutte le scritture di stato sono IDEMPOTENTI (upsert on_conflict). Le scritture
"a firma" (ladder/now) sono write-on-change: il chiamante salta la scrittura se la
firma non è cambiata (vedi ``tennis_runner``), per non stressare il DB.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

from config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

from .. import canale_bot as _cb

logger = logging.getLogger(__name__)

# --- F3 (18/09): lo stato e l'armatura dei 4 bot tennis sul canale -----------
# Il database resta il registro: si pubblica DOPO la scrittura riuscita e si
# pubblica la riga che la scrittura ha RESTITUITO (PostgREST torna di serie la
# rappresentazione: NESSUNA lettura in piu' - il 13/09 il budget di IO e'
# finito). Interruttore ``TENNIS_BOT_CANALE`` nel ``.env``, DEFAULT SPENTO.
#
# Su quale canale escono: su quello del PROCESSO che ha scritto la riga. Nel
# servizio dei bot avviato dall'app (``tennis_bot_service --bridge-only``,
# ``desktop/main.js:268``) e' il 47337; dentro il runner tennis e' il 47332.
# Sono entrambi canali del TENNIS: calcio e tennis non si mischiano comunque.
_CANALE_ACCESO = _cb.acceso(_cb.ENV_TENNIS_BOT)

_ORDER_TABLE = "tennis_live_order_queue"

# 24/09: il `source` delle righe d'ordine dei 4 bot (una sola lista, nel modulo
# puro del canale; un test la confronta con `tennis_bot_service._BOT_KEYS`).
from .canale_bot_tennis import SORGENTI_BOT_TENNIS as _SORGENTI_BOT  # noqa: E402

# ---------------------------------------------------------------------------
# Client Supabase PER-THREAD (service_role)
# ---------------------------------------------------------------------------
_local = threading.local()


def get_tennis_client() -> Client:
    """Client Supabase service_role dedicato al thread corrente (creato on-demand)."""
    sb = getattr(_local, "client", None)
    if sb is None:
        sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        _local.client = sb
    return sb


def _exec_retry(builder) -> object:
    """Esegue una query PostgREST con retry SOLO su errori transitori di rete
    (A1 — WinError 10035 sotto picco in-play, come Betfair/stream/db.py).
    Upsert idempotenti → un retry non può mai duplicare."""
    from ..net_retry import with_backoff

    return with_backoff(
        builder.execute,
        attempts=3,
        base_delay=0.15,
        on_retry=lambda exc, i: logger.warning(
            "[tennis-db] scrittura transitoriamente KO (tentativo %d): %s", i, str(exc)[:120]
        ),
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# tennis_live_follow — eventi tennis da seguire live
# ---------------------------------------------------------------------------
def register_tennis_follow(
    event_id: str,
    market_id: str,
    player1_name: str,
    player2_name: str,
    open_date: Optional[str] = None,
    competition_name: Optional[str] = None,
    status: str = "PENDING",
    origine: Optional[str] = None,
) -> None:
    """Registra/aggiorna un evento tennis da seguire (idempotente su event_id).

    ``origine`` (25/09, auto-mode): ``'auto'`` quando il follow lo crea il
    ponte dal FEED UNICO; ``None`` = non si scrive (la colonna tiene il suo
    default ``'manuale'``). Colonna assente (migrazione
    ``tennis_uscite_manuali_2026-09-25.sql`` non applicata) -> ``ColonnaAssente``:
    un follow automatico che non si puo' marcare come tale NON si scrive
    (verrebbe scambiato per una scelta dell'utente)."""
    sb = get_tennis_client()
    row = {
        "event_id": event_id,
        "market_id": market_id,
        "player1_name": player1_name,
        "player2_name": player2_name,
        "open_date": open_date,
        "competition_name": competition_name,
        "status": status,
        "updated_at": _now_iso(),
    }
    if origine is not None:
        row["origine"] = str(origine)
    try:
        sb.table("tennis_live_follow").upsert(row, on_conflict="event_id").execute()
    except Exception as e:  # noqa: BLE001
        if origine is not None and colonna_assente(e, "origine"):
            raise ColonnaAssente("tennis_live_follow.origine") from e
        raise


class ColonnaAssente(RuntimeError):
    """Una colonna di una migrazione additiva non esiste ancora sul DB."""


def colonna_assente(e: Exception, colonna: str) -> bool:
    """PostgREST PGRST204 ("Could not find the 'x' column") o Postgres 42703.
    Solo questi: un DB giu' non e' una migrazione mancante."""
    t = str(e)
    return (("'%s'" % colonna) in t or ('"%s"' % colonna) in t) and (
        "PGRST204" in t or "42703" in t or "Could not find" in t
        or "does not exist" in t)


# ---------------------------------------------------------------------------
# 25/09 - AUTO-MODE: la lista partite dal FEED UNICO (sola lettura)
# ---------------------------------------------------------------------------
def list_tennis_feed_rows() -> Optional[List[Dict[str, Any]]]:
    """Le righe TENNIS del feed unico (``safe_strategy_scan``, scritte dallo
    scanner Safe): la stessa tabella che legge Safe (``bot_db.fetch_scan_rows``),
    filtrata su ``sport='tennis'``. ``None`` = NON letto (mai «feed vuoto»).

    Si leggono SOLO le chiavi del payload che servono a seguire una partita
    (``payload->chiave``, tipi JSON conservati), non ``score_raw``/quote: il
    ponte gira ogni 15 s e l'IO del database e' la risorsa scarsa (13/09).
    La riga torna nella forma di sempre (``payload`` dizionario)."""
    sb = get_tennis_client()
    try:
        resp = (sb.table("safe_strategy_scan")
                .select(",".join(["event_id", "sport", "updated_at"]
                                 + ["%s:payload->%s" % (k, k) for k in _CHIAVI_FEED]))
                .eq("sport", "tennis").execute())
    except Exception as e:  # noqa: BLE001
        logger.warning("[tennis-db] lettura feed tennis KO: %s", str(e)[:160])
        return None
    out: List[Dict[str, Any]] = []
    for r in (getattr(resp, "data", None) or []):
        if not isinstance(r, dict):
            continue
        out.append({"event_id": r.get("event_id"), "sport": r.get("sport"),
                    "updated_at": r.get("updated_at"),
                    "payload": {k: r.get(k) for k in _CHIAVI_FEED}})
    return out


#: le chiavi del payload tennis dello scanner (``safe_strategy/service.py::
#: build_rows``, ramo tennis) che servono all'auto-mode
_CHIAVI_FEED = ("p1", "p2", "competition", "open_date", "inplay",
                "mo_market_id", "mo_status")


def scanner_heartbeat() -> Optional[Dict[str, Any]]:
    """Il battito dello scanner (``safe_strategy_status`` id='scanner'):
    ``{payload, updated_at}`` o ``None`` (non letto / mai scritto)."""
    sb = get_tennis_client()
    try:
        resp = (sb.table("safe_strategy_status").select("payload,updated_at")
                .eq("id", "scanner").limit(1).execute())
    except Exception as e:  # noqa: BLE001
        logger.warning("[tennis-db] battito scanner KO: %s", str(e)[:160])
        return None
    rows = getattr(resp, "data", None) or []
    return rows[0] if rows else None


def list_tennis_now_status(event_ids: List[str]) -> Optional[Dict[str, str]]:
    """``{event_id: status}`` da ``tennis_live_now`` (lo scrive il runner dal
    book dello stream): dice se il mercato di una partita uscita dal feed e'
    davvero CHIUSO. ``None`` = non letto."""
    ids = [str(e) for e in event_ids if e]
    if not ids:
        return {}
    sb = get_tennis_client()
    try:
        resp = (sb.table("tennis_live_now").select("event_id,status")
                .in_("event_id", ids).execute())
    except Exception as e:  # noqa: BLE001
        logger.warning("[tennis-db] tennis_live_now KO: %s", str(e)[:160])
        return None
    return {str(r.get("event_id")): str(r.get("status") or "")
            for r in (getattr(resp, "data", None) or []) if r.get("event_id")}


def set_tennis_bot_uscite(event_id: str, bot_key: str, automatiche: bool) -> bool:
    """25/09 - propaga l'interruttore «uscite automatiche» del bot sulla riga
    PER PARTITA (``tennis_bot_control.uscite_automatiche``), che il runner
    rilegge a caldo a ogni giro. ``False`` = non scritto (colonna assente o DB
    KO): il runner resta sull'ultimo valore letto."""
    sb = get_tennis_client()
    try:
        res = (sb.table("tennis_bot_control")
               .update({"uscite_automatiche": bool(automatiche), "updated_at": _now_iso()})
               .eq("event_id", str(event_id)).eq("bot_key", str(bot_key)).execute())
    except Exception as e:  # noqa: BLE001
        if not colonna_assente(e, "uscite_automatiche"):
            logger.warning("[tennis-db] uscite %s/%s KO: %s", event_id, bot_key, str(e)[:160])
        return False
    if _CANALE_ACCESO:
        _cb.pubblica_scritte(_cb.TOPIC["tennis_bot_armamento"], res)
    return True


def set_tennis_follow_status(
    event_id: str, status: str, error_detail: Optional[str] = None
) -> None:
    sb = get_tennis_client()
    safe_detail = (error_detail or "")[:500] or None
    sb.table("tennis_live_follow").update(
        {"status": status, "error_detail": safe_detail, "updated_at": _now_iso()}
    ).eq("event_id", event_id).execute()


def list_pending_tennis_follows() -> List[Dict[str, Any]]:
    """Eventi da agganciare (PENDING o STREAMING non chiusi)."""
    sb = get_tennis_client()
    resp = (
        sb.table("tennis_live_follow")
        .select("*")
        .in_("status", ["PENDING", "STREAMING"])
        .execute()
    )
    return getattr(resp, "data", None) or []


# ---------------------------------------------------------------------------
# tennis_live_ladder — ladder LIVE per-mercato (write-on-change dal ladder_worker)
# ---------------------------------------------------------------------------
def upsert_tennis_ladder(row: Dict[str, Any]) -> None:
    """Ladder corrente di UN mercato tennis → ``tennis_live_ladder`` (idempotente).

    Chiave: ``market_id`` (il frontend legge la ladder per market_id, maybeSingle).
    ``updated_at`` forzato. Shape ``ladder`` identica al calcio (LiveLadderState).
    """
    sb = get_tennis_client()
    payload = dict(row)
    payload["updated_at"] = _now_iso()
    _exec_retry(sb.table("tennis_live_ladder").upsert(payload, on_conflict="market_id"))


# ---------------------------------------------------------------------------
# tennis_live_now — stato glance real-time (mercati + order_mode + punteggio)
# ---------------------------------------------------------------------------
def upsert_tennis_now(
    event_id: str,
    inplay: bool,
    status: str,
    state: Dict[str, Any],
    score: Optional[Dict[str, Any]] = None,
    points: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Stato live di UN evento tennis → ``tennis_live_now`` (idempotente su event_id).

    ``state`` = TennisLiveNowState (markets + order_mode); ``score`` = TennisScoreState;
    ``points`` = ultimi TennisPointEvent. Match 1:1 con lib/tennis.ts::TennisLiveNowRow.
    """
    sb = get_tennis_client()
    row = {
        "event_id": event_id,
        "inplay": inplay,
        "status": status,
        "state": state,
        "score": score,
        "points": points,
        "updated_at": _now_iso(),
    }
    from ..local_channel import publish as _lpub

    _lpub("now", row)  # A7: push locale prima del cloud
    _exec_retry(sb.table("tennis_live_now").upsert(row, on_conflict="event_id"))


# ---------------------------------------------------------------------------
# tennis_bot_control / tennis_bot_activity — hosting dei bot armati
# ---------------------------------------------------------------------------
def list_tennis_bot_controls(
    event_id: Optional[str] = None,
    statuses: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Righe di controllo bot (opz. filtrate per evento e/o stato)."""
    sb = get_tennis_client()
    q = sb.table("tennis_bot_control").select("*")
    if event_id is not None:
        q = q.eq("event_id", event_id)
    if statuses:
        q = q.in_("status", statuses)
    return getattr(q.execute(), "data", None) or []


def set_tennis_bot_status(
    event_id: str,
    bot_key: str,
    status: str,
    *,
    error: Optional[str] = None,
    stats: Optional[Dict[str, Any]] = None,
    heartbeat: bool = False,
    started: bool = False,
    stopped: bool = False,
) -> None:
    """Aggiorna lo stato/heartbeat/stat di un bot in ``tennis_bot_control``."""
    sb = get_tennis_client()
    now = _now_iso()
    upd: Dict[str, Any] = {"status": status}
    if error is not None:
        upd["error"] = str(error)[:300]
    if stats is not None:
        upd["stats"] = stats
    if heartbeat:
        upd["heartbeat_at"] = now
    if started:
        upd["started_at"] = now
    if stopped:
        upd["stopped_at"] = now
    res = sb.table("tennis_bot_control").update(upd).eq("event_id", event_id).eq(
        "bot_key", bot_key
    ).execute()
    if _CANALE_ACCESO:          # F3: l'armatura per evento, come il DB l'ha scritta
        # 24/09: topic `tennis_bot_armamento` (prima usciva come
        # `tennis_bot_posizioni`, nome che ora porta le righe d'ordine dei bot)
        _cb.pubblica_scritte(_cb.TOPIC["tennis_bot_armamento"], res)


# Marker che distingue un motivo d'ATTESA (benigno) da un errore terminale nel
# campo condiviso ``error``: la UI lo renderizza come stato informativo, e la
# pulizia NON può cancellare un errore reale scritto nel frattempo.
WAIT_REASON_PREFIX = "[ATTESA] "


def set_tennis_bot_wait_reason(
    event_id: str, bot_key: str, reason: Optional[str]
) -> None:
    """Scrive/ripulisce il motivo d'ATTESA di un bot nel campo ``error`` ESISTENTE
    di ``tennis_bot_control`` — SENZA toccare lo status (il bot resta
    'requested'/'armed': è in coda, non in errore terminale). Usato dal fix
    "restart bloccato visibile" (cantiere D 17/07): l'utente vede sul control-row
    perché un bot armato non sta tradando. ``reason=None`` ripulisce.

    Il testo è sempre prefissato con ``WAIT_REASON_PREFIX`` e sia la SCRITTURA
    sia la pulizia sono CONDIZIONATE server-side: un errore reale scritto da un
    altro percorso (senza prefisso) non viene MAI sovrascritto né cancellato —
    la condizione vive nella singola UPDATE, quindi niente race lettura→scrittura."""
    sb = get_tennis_client()
    if reason is not None:
        msg = str(reason)
        if not msg.startswith(WAIT_REASON_PREFIX):
            msg = WAIT_REASON_PREFIX + msg
        upd = {"error": msg[:300]}
        # due UPDATE condizionate (error assente / error ancora in attesa):
        # una riga con errore REALE non matcha nessuna delle due.
        sb.table("tennis_bot_control").update(upd).is_("error", "null").eq(
            "event_id", event_id).eq("bot_key", bot_key).execute()
        sb.table("tennis_bot_control").update(upd).like(
            "error", f"{WAIT_REASON_PREFIX}%").eq(
            "event_id", event_id).eq("bot_key", bot_key).execute()
    else:
        # solo le righe il cui error è ANCORA un motivo d'attesa
        sb.table("tennis_bot_control").update({"error": None}).like(
            "error", f"{WAIT_REASON_PREFIX}%").eq(
            "event_id", event_id).eq("bot_key", bot_key).execute()


def write_tennis_bot_activity(
    event_id: str, bot_key: str, kind: str, payload: Dict[str, Any]
) -> None:
    """Append di una riga di attività bot → ``tennis_bot_activity`` (best-effort)."""
    sb = get_tennis_client()
    sb.table("tennis_bot_activity").insert(
        {
            "event_id": event_id,
            "bot_key": bot_key,
            "kind": kind,
            "payload": payload,
            "ts": _now_iso(),
        }
    ).execute()


# ---------------------------------------------------------------------------
# tennis_live_order_queue — coda comandi ordine manuali (drenata dal worker)
# ---------------------------------------------------------------------------
def list_pending_tennis_orders(limit: int = 5) -> List[Dict[str, Any]]:
    sb = get_tennis_client()
    resp = (
        sb.table(_ORDER_TABLE)
        .select("*")
        .eq("status", "pending")
        .order("created_at")
        .limit(limit)
        .execute()
    )
    return getattr(resp, "data", None) or []


def claim_tennis_order(rid: int) -> bool:
    """CLAIM atomico pending → processing. True se questa chiamata l'ha preso."""
    sb = get_tennis_client()
    claimed = (
        sb.table(_ORDER_TABLE)
        .update({"status": "processing"})
        .eq("id", rid)
        .eq("status", "pending")
        .execute()
        .data
        or []
    )
    return len(claimed) > 0


def write_tennis_order_done(rid: int, result: Dict[str, Any]) -> None:
    # BUG FIX cert 10/07 (VISTO DAL VIVO): la coda ``tennis_live_order_queue`` NON ha
    # la colonna top-level ``bet_id`` (colonne reali: id, client_ref, payload, status,
    # result, error, processed_at, created_at — il bet_id era copiato dal pattern
    # dello SPECCHIO): l'update falliva con PGRST204/42703 e la riga finiva 'error'
    # CON L'ORDINE GIÀ A MERCATO (l'utente lo crede fallito e lo ripete = doppio
    # ordine). Il bet_id resta dentro ``result`` jsonb, che è ciò che la UI legge.
    sb = get_tennis_client()
    sb.table(_ORDER_TABLE).update(
        {
            "status": "done",
            "result": result,
            "error": result.get("error"),
            "processed_at": _now_iso(),
        }
    ).eq("id", rid).execute()


def write_tennis_order_error(rid: int, result: Dict[str, Any]) -> None:
    sb = get_tennis_client()
    sb.table(_ORDER_TABLE).update(
        {
            "status": "error",
            "error": (result.get("error") or "")[:300] or None,
            "result": result,
            "processed_at": _now_iso(),
        }
    ).eq("id", rid).execute()


# ---------------------------------------------------------------------------
# tennis_live_orders / tennis_live_positions — specchio ordini + esposizioni
# ---------------------------------------------------------------------------
def upsert_tennis_order(row: Dict[str, Any]) -> None:
    """Specchio di UN ordine tennis → ``tennis_live_orders`` (idempotente).

    Chiave: ``(mode, client_order_ref)`` (una riga per ordine). ``updated_at`` forzato.
    """
    sb = get_tennis_client()
    payload = dict(row)
    payload["updated_at"] = _now_iso()
    from ..local_channel import publish as _lpub

    _lpub("order", payload)  # A7: fill realtime sul desktop
    res = _exec_retry(sb.table("tennis_live_orders").upsert(
        payload, on_conflict="mode,client_order_ref"
    ))
    # 24/09 - le righe d'ordine dei 4 BOT anche sul topic `tennis_bot_posizioni`:
    # DOPO la scrittura riuscita, la riga che la upsert ha RESTITUITO (con `id`,
    # nessuna lettura in piu'). Esce sul canale di QUESTO processo (il runner,
    # 47332); il ponte la inoltra identica sul 47337 (`canale_bot_tennis.py`).
    # Gli ordini manuali restano sul solo topic `order`.
    if _CANALE_ACCESO and str(payload.get("source") or "") in _SORGENTI_BOT:
        _cb.pubblica_scritte(_cb.TOPIC["tennis_bot_posizioni"], res)


def upsert_tennis_position(row: Dict[str, Any]) -> None:
    """Esposizione di UNA selezione tennis → ``tennis_live_positions`` (idempotente).

    Chiave: ``(mode, market_id, selection_id, handicap)``. ``updated_at`` forzato.
    """
    sb = get_tennis_client()
    payload = dict(row)
    payload["updated_at"] = _now_iso()
    from ..local_channel import publish as _lpub

    _lpub("position", payload)  # A7: esposizioni realtime sul desktop
    _exec_retry(sb.table("tennis_live_positions").upsert(
        payload, on_conflict="mode,market_id,selection_id,handicap"
    ))


# ---------------------------------------------------------------------------
# tennis_bot_service_control — L'INTERRUTTORE PER BOT (Control Room)
# ---------------------------------------------------------------------------
# ⚠️ Richiede `migrations/tennis_bot_service_control_2026-09-17.sql`, che NON e'
# ancora applicata. Finche' la tabella non c'e' queste funzioni NON esplodono e
# NON inventano: dicono «non letto» e lo scrivono nel log UNA volta sola. Un bot
# di cui non si sa lo stato non si comanda (fail-closed).
_SERVICE_TABLE = "tennis_bot_service_control"
_servizio_assente_detto = False


def _tabella_servizi_assente(e: Exception) -> bool:
    """La tabella non esiste ancora (migrazione non applicata)? PostgREST
    risponde PGRST205 / 42P01. Qualunque ALTRO errore non va mascherato: un DB
    giu' e una migrazione mancante sono due cose diverse."""
    t = str(e)
    return ("PGRST205" in t or "42P01" in t
            or ("does not exist" in t and _SERVICE_TABLE in t)
            or ("Could not find the table" in t and _SERVICE_TABLE in t))


def list_tennis_bot_services() -> Optional[List[Dict[str, Any]]]:
    """Le righe di interruttore dei quattro bot tennis.

    `None` = NON LETTO (tabella assente o DB KO). Chi chiama non deve dedurre
    «tutti fermi»: non sapere non e' sapere che sono fermi.
    """
    global _servizio_assente_detto
    sb = get_tennis_client()
    try:
        resp = sb.table(_SERVICE_TABLE).select("*").execute()
    except Exception as e:  # noqa: BLE001
        if _tabella_servizi_assente(e):
            if not _servizio_assente_detto:
                _servizio_assente_detto = True
                logger.warning(
                    "[tennis-db] %s non esiste ancora (migrazione "
                    "tennis_bot_service_control_2026-09-17.sql NON applicata): "
                    "l'interruttore per bot della Control Room resta inerte.",
                    _SERVICE_TABLE)
            return None
        logger.warning("[tennis-db] lettura %s KO: %s", _SERVICE_TABLE, str(e)[:160])
        return None
    return getattr(resp, "data", None) or []


def set_tennis_bot_service_state(
    bot_key: str,
    *,
    status: Optional[str] = None,
    stats: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    heartbeat: bool = False,
    stopped: bool = False,
) -> bool:
    """Aggiorna la riga di interruttore di UN bot. `False` = non scritto."""
    sb = get_tennis_client()
    upd: Dict[str, Any] = {"updated_at": _now_iso()}
    if status is not None:
        upd["status"] = str(status)
    if stats is not None:
        upd["stats"] = stats
    if error is not None:
        upd["error"] = str(error)[:300]
    if heartbeat:
        upd["heartbeat_at"] = _now_iso()
    if stopped:
        upd["stopped_at"] = _now_iso()
    try:
        res = sb.table(_SERVICE_TABLE).update(upd).eq("bot_key", str(bot_key)).execute()
    except Exception as e:  # noqa: BLE001
        if not _tabella_servizi_assente(e):
            logger.warning("[tennis-db] scrittura %s KO (%s): %s",
                           _SERVICE_TABLE, bot_key, str(e)[:160])
        return False
    if _CANALE_ACCESO:          # F3: DOPO la scrittura riuscita, mai prima
        _cb.pubblica_scritte(_cb.TOPIC["tennis_bot_stato"], res)
    return True


def upsert_tennis_bot_control(row: Dict[str, Any]) -> None:
    """Riga di armatura PER EVENTO, idempotente su (event_id, bot_key).

    E' la stessa tabella che la scheda partita usa da sempre: l'interruttore per
    bot non la sostituisce, la ALIMENTA.
    """
    sb = get_tennis_client()
    payload = dict(row)
    payload["updated_at"] = _now_iso()
    try:
        res = _upsert_control(sb, payload)
    except Exception as e:  # noqa: BLE001
        # T1 (24/09): la colonna `mode` arriva con la migrazione
        # `tennis_bot_control_mode_2026-09-24.sql`, che applica l'utente. Finche'
        # manca, la riga si scrive SENZA `mode` e il runner la legge PAPER
        # (`guardie_tennis.modalita_riga`): fail-closed, il paper resta usabile e
        # il live e' impossibile finche' la colonna non c'e'.
        if "mode" not in payload or not _colonna_mode_assente(e):
            raise
        global _mode_assente_detto
        if not _mode_assente_detto:
            _mode_assente_detto = True
            logger.warning(
                "[tennis-db] tennis_bot_control.mode non esiste ancora (migrazione "
                "tennis_bot_control_mode_2026-09-24.sql NON applicata): riga scritta "
                "SENZA modalita' = PAPER per il runner.")
        senza = {k: v for k, v in payload.items() if k != "mode"}
        res = _upsert_control(sb, senza)
    if _CANALE_ACCESO:          # F3: DOPO la scrittura riuscita, mai prima
        _cb.pubblica_scritte(_cb.TOPIC["tennis_bot_armamento"], res)


def _upsert_control(sb: Any, payload: Dict[str, Any]) -> Any:
    """L'upsert di ``tennis_bot_control``. 25/09: ``uscite_automatiche`` arriva
    con ``tennis_uscite_manuali_2026-09-25.sql``; finche' manca, la riga si
    scrive SENZA e il runner la legge AUTOMATICA
    (``auto_mode.uscite_automatiche_riga``), il comportamento di prima.
    Qualunque altro errore (compresa la colonna ``mode`` assente, che gestisce
    il chiamante) risale identico."""
    global _uscite_assente_detto
    if _uscite_assente_detto and "uscite_automatiche" in payload:
        payload = {k: v for k, v in payload.items() if k != "uscite_automatiche"}
    try:
        return _exec_retry(sb.table("tennis_bot_control").upsert(
            payload, on_conflict="event_id,bot_key"))
    except Exception as e:  # noqa: BLE001
        if "uscite_automatiche" not in payload \
                or not colonna_assente(e, "uscite_automatiche"):
            raise
        if not _uscite_assente_detto:
            logger.warning(
                "[tennis-db] tennis_bot_control.uscite_automatiche non esiste ancora "
                "(migrazione tennis_uscite_manuali_2026-09-25.sql NON applicata): riga "
                "scritta SENZA = uscite AUTOMATICHE per il runner.")
        _uscite_assente_detto = True
        senza = {k: v for k, v in payload.items() if k != "uscite_automatiche"}
        return _exec_retry(sb.table("tennis_bot_control").upsert(
            senza, on_conflict="event_id,bot_key"))


_mode_assente_detto = False
_uscite_assente_detto = False


def _colonna_mode_assente(e: Exception) -> bool:
    """PostgREST risponde PGRST204 ("Could not find the 'mode' column") o
    Postgres 42703 (colonna inesistente). Solo questi: un DB giu' non e' una
    migrazione mancante."""
    t = str(e)
    return ("'mode'" in t or '"mode"' in t) and ("PGRST204" in t or "42703" in t
                                                  or "Could not find" in t
                                                  or "does not exist" in t)


# ---------------------------------------------------------------------------
# T2 (24/09) - RIPRESA del runner tennis (``guardie_tennis.ripresa_all_avvio``)
# ---------------------------------------------------------------------------
# stati flumine di un ordine ancora VIVO (tutto il resto e' terminale)
_STATI_VIVI = ("PENDING", "CANCELLING", "UPDATING", "REPLACING", "EXECUTABLE")
_CAMPI_POSIZIONE = (
    "matched_if_win", "matched_if_lose", "worst_if_win", "worst_if_lose",
    "selection_exposure", "unmatched_back_exposure", "unmatched_lay_exposure",
    "net_position",
)


def fail_stale_pending_tennis_orders(max_age_sec: float = 120.0) -> int:
    """All'avvio del runner le richieste della coda desktop piu' vecchie di
    ``max_age_sec`` vanno in 'error' SENZA esecuzione (gemella di
    ``db.fail_stale_pending_requests`` del calcio): un comando di prima del
    crash eseguito minuti dopo agirebbe su un mercato diverso. Le 'processing'
    interrotte hanno esito INCERTO e il messaggio lo dichiara. Ritorna quante."""
    from datetime import timedelta

    sb = get_tennis_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max_age_sec)).isoformat()
    res = (
        sb.table(_ORDER_TABLE)
        .update({
            "status": "error",
            "error": "richiesta STANTIA al riavvio del runner tennis: non eseguita "
                     "(ripetere se serve)",
            "processed_at": _now_iso(),
        })
        .eq("status", "pending")
        .lt("created_at", cutoff)
        .execute()
    )
    n = len(getattr(res, "data", None) or [])
    res2 = (
        sb.table(_ORDER_TABLE)
        .update({
            "status": "error",
            "error": "richiesta INTERROTTA a meta' da un riavvio del runner tennis: "
                     "esito INCERTO - verificare ordini e posizioni sul conto prima "
                     "di ripetere",
            "processed_at": _now_iso(),
        })
        .eq("status", "processing")
        .lt("created_at", cutoff)
        .execute()
    )
    return n + len(getattr(res2, "data", None) or [])


def chiudi_specchio_paper_orfano() -> "tuple[int, int]":
    """All'avvio del runner il blotter SIMULATO e' vuoto: gli ordini paper
    ancora 'vivi' nello specchio sono morti col processo di prima. Si chiudono
    (status VOIDED, NON si cancellano: il P&L regolato resta) e le posizioni
    paper vanno a zero. Le righe LIVE non si toccano MAI (soldi veri: la verita'
    la dice lo stream ordini). Ritorna (ordini chiusi, posizioni azzerate)."""
    sb = get_tennis_client()
    res_o = (
        sb.table("tennis_live_orders")
        .update({"status": "VOIDED", "updated_at": _now_iso()})
        .eq("mode", "paper")
        .in_("status", list(_STATI_VIVI))
        .execute()
    )
    zero: Dict[str, Any] = {f: 0.0 for f in _CAMPI_POSIZIONE}
    zero["updated_at"] = _now_iso()
    res_p = (
        sb.table("tennis_live_positions")
        .update(zero)
        .eq("mode", "paper")
        .execute()
    )
    return (len(getattr(res_o, "data", None) or []),
            len(getattr(res_p, "data", None) or []))
