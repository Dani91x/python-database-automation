"""Accesso Supabase per il sottosistema live (backend = service_role, bypassa RLS).

Tutte le scritture sono IDEMPOTENTI:
  - live_follow / live_now / live_markets / live_run_log → upsert on_conflict
  - snapshot / timeline → delete-per-evento + insert (re-curazione ripetibile)
Pattern chunked come Ai Engine/ai_engine/db_adapter.py (CHUNK righe per insert).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db_client import get_supabase_client

from .config_stream import UPLOAD_CHUNK

try:  # postgrest e' una dip di supabase-py; l'import puo' variare tra versioni
    from postgrest.exceptions import APIError
except Exception:  # noqa: BLE001 - fallback: cattura generica in _is_statement_timeout
    APIError = Exception  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


def _is_statement_timeout(exc: Exception) -> bool:
    """True se l'errore Postgres e' uno statement_timeout (SQLSTATE 57014).

    Su INSERT/DELETE di molte righe (o con JSONB grandi / tabella con bloat) Postgres
    puo' abortire la singola statement al superamento di ``statement_timeout``. Lo
    riconosciamo per riprovare con batch piu' piccoli invece di fallire l'upload.
    """
    code = getattr(exc, "code", None)
    if code == "57014":
        return True
    msg = str(exc).lower()
    return "57014" in msg or "statement timeout" in msg


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _exec_retry(builder: Any) -> Any:
    """Esegue una query PostgREST con retry SOLO su errori transitori di rete
    (A1 — WinError 10035 sotto picco in-play). Le scritture qui sono upsert
    IDEMPOTENTI → un retry non può mai duplicare. L'ultima eccezione risale
    al chiamante (le scritture specchio restano best-effort con log)."""
    from .net_retry import with_backoff

    return with_backoff(
        builder.execute,
        attempts=3,
        base_delay=0.15,
        on_retry=lambda exc, i: logger.warning(
            "[db] scrittura transitoriamente KO (tentativo %d): %s", i, str(exc)[:120]
        ),
    )


# ----------------------------------------------------------------------------
# live_follow
# ----------------------------------------------------------------------------
def register_follow(
    event_id: str,
    home_name: str,
    away_name: str,
    open_date: str,
    fixture_id: Optional[int] = None,
    watchlist_id: Optional[int] = None,
    league_name: Optional[str] = None,
    league_id: Optional[int] = None,
    status: str = "PENDING",
) -> None:
    sb = get_supabase_client()
    row = {
        "event_id": event_id,
        "fixture_id": fixture_id,
        "watchlist_id": watchlist_id,
        "league_name": league_name,
        "league_id": league_id,
        "home_name": home_name,
        "away_name": away_name,
        "open_date": open_date,
        "status": status,
        "updated_at": _now_iso(),
    }
    sb.table("live_follow").upsert(row, on_conflict="event_id").execute()


def set_follow_status(event_id: str, status: str, error_detail: Optional[str] = None) -> None:
    sb = get_supabase_client()
    # cap difensivo: error_detail può contenere messaggi d'eccezione → max 200 char
    safe_detail = (error_detail or "")[:200] or None
    sb.table("live_follow").update(
        {"status": status, "error_detail": safe_detail, "updated_at": _now_iso()}
    ).eq("event_id", event_id).execute()


def list_pending_follows() -> List[Dict[str, Any]]:
    """Partite da agganciare (PENDING o STREAMING non chiuse)."""
    sb = get_supabase_client()
    resp = (
        sb.table("live_follow")
        .select("*")
        .in_("status", ["PENDING", "STREAMING"])
        .execute()
    )
    return getattr(resp, "data", None) or []


def get_fixture_prematch_lambdas(
    fixture_id: Optional[int],
) -> Optional[tuple]:
    """λ pre-match PER-SQUADRA (Dixon-Coles) dal DB → (λ_casa, λ_trasferta, league_id).

    È il PRIOR migliore per il motore live: forza attacco/difesa per-squadra stimata
    sullo storico di lega (tactical_engine), non un totale generico. Catena:
    ``tactical_engine_json.lambda_*`` → ``db_json_analisi.inputs.lambda_*``. None se assente.
    """
    if fixture_id is None:
        return None
    sb = get_supabase_client()
    resp = (
        sb.table("fixture_predictions")
        .select("league_id,tactical_engine_json,db_json_analisi")
        .eq("fixture_id", int(fixture_id))
        .limit(1)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    if not rows:
        return None
    row = rows[0]
    league_id = row.get("league_id")
    for key, path in (("tactical_engine_json", None), ("db_json_analisi", "inputs")):
        node = row.get(key)
        if isinstance(node, str):
            try:
                import json as _json
                node = _json.loads(node)
            except (ValueError, TypeError):
                node = None
        if path and isinstance(node, dict):
            node = node.get(path)
        if isinstance(node, dict):
            lh, la = node.get("lambda_home"), node.get("lambda_away")
            try:
                if lh is not None and la is not None and float(lh) > 0 and float(la) > 0:
                    return (float(lh), float(la), league_id)
            except (TypeError, ValueError):
                pass
    return None


# ----------------------------------------------------------------------------
# live_markets (catalogo)
# ----------------------------------------------------------------------------
def upsert_markets(event_id: str, markets: List[Dict[str, Any]]) -> None:
    """markets: [{market_id, market_type, market_name, sort_priority, selections}]"""
    if not markets:
        return
    sb = get_supabase_client()
    rows = [
        {
            "event_id": event_id,
            "market_id": m["market_id"],
            "market_type": m.get("market_type"),
            "market_name": m.get("market_name"),
            "sort_priority": m.get("sort_priority"),
            "selections": m.get("selections", []),
            "n_updates": m.get("n_updates", 0),
        }
        for m in markets
    ]
    for i in range(0, len(rows), UPLOAD_CHUNK):
        sb.table("live_markets").upsert(
            rows[i : i + UPLOAD_CHUNK], on_conflict="event_id,market_id"
        ).execute()


# ----------------------------------------------------------------------------
# live_now (glance real-time)
# ----------------------------------------------------------------------------
def update_live_now(
    event_id: str,
    state: Dict[str, Any],
    inplay: bool = False,
    minute: Optional[int] = None,
    score_home: Optional[int] = None,
    score_away: Optional[int] = None,
    status: str = "OPEN",
    score_source: Optional[str] = None,
) -> None:
    sb = get_supabase_client()
    row = {
        "event_id": event_id,
        "inplay": inplay,
        "minute": minute,
        "score_home": score_home,
        "score_away": score_away,
        "status": status,
        "score_source": score_source,
        "state": state,
        "updated_at": _now_iso(),
    }
    # A7: push locale PRIMA della scrittura cloud (il desktop non aspetta la rete).
    from .local_channel import publish as _lpub

    _lpub("now", row)
    _exec_retry(sb.table("live_now").upsert(row, on_conflict="event_id"))


# ----------------------------------------------------------------------------
# snapshot + timeline (post-match, delete+insert per idempotenza)
# ----------------------------------------------------------------------------
def delete_event_rows(
    table: str,
    event_id: str,
    select_page: int = 2000,
    delete_chunk: int = 500,
) -> int:
    """DELETE a blocchi per chiave primaria di tutte le righe di un evento.

    La delete monolitica ``delete().eq("event_id", ...)`` cancella tutte le righe in
    UN solo statement: su eventi grandi (decine/centinaia di migliaia di snapshot, o
    con bloat da re-curazioni ripetute) supera lo ``statement_timeout`` di Postgres
    (errore 57014) e fallisce. Qui invece selezioniamo gli ``id`` a pagine (via
    l'indice su ``event_id``) e li cancelliamo per PK a piccoli blocchi: ogni
    operazione tocca poche righe → sempre sotto il timeout, a prescindere dalla
    dimensione dell'evento. Ritorna il numero di righe cancellate.

    NB: ``delete_chunk`` tiene corta l'URL PostgREST ``id=in.(...)`` (500 bigint ~6KB,
    sotto i limiti tipici dei proxy); ``select_page`` limita i round-trip di lettura.
    """
    sb = get_supabase_client()
    total = 0
    while True:
        res = sb.table(table).select("id").eq("event_id", event_id).limit(select_page).execute()
        ids = [r["id"] for r in (res.data or [])]
        if not ids:
            break
        for i in range(0, len(ids), delete_chunk):
            sb.table(table).delete().in_("id", ids[i : i + delete_chunk]).execute()
        total += len(ids)
        if len(ids) < select_page:
            break  # ultima pagina già cancellata → evita una select finale a vuoto
    return total


def insert_rows_resilient(table: str, rows: List[Dict[str, Any]], start_chunk: int = UPLOAD_CHUNK) -> int:
    """INSERT a blocchi con auto-riduzione della dimensione sullo statement_timeout.

    Parte da ``start_chunk`` righe per insert; se Postgres aborta la statement per
    timeout (57014) — tipico su eventi con snapshot pesanti (ladder ``trd`` full-depth)
    o su tabella con bloat — DIMEZZA la dimensione del blocco e riprova, mantenendo poi
    quella piu' piccola per il resto delle righe. Cosi' gli eventi normali restano veloci
    (500/blocco al primo colpo) e quelli grandi convergono a un batch che passa, invece
    di far fallire l'intero upload. Ritorna il numero di righe inserite.
    """
    sb = get_supabase_client()
    size = max(1, start_chunk)
    i = 0
    net_retry = 0
    while i < len(rows):
        chunk = rows[i : i + size]
        try:
            sb.table(table).insert(chunk).execute()
            i += len(chunk)
            net_retry = 0
        except APIError as e:  # type: ignore[misc]
            if _is_statement_timeout(e) and size > 1:
                new_size = max(1, size // 2)
                logger.warning(
                    "[db] insert %s: statement_timeout su blocco da %d → riprovo con %d",
                    table, size, new_size,
                )
                size = new_size
                continue  # riprova la STESSA posizione con blocco piu' piccolo
            raise
        except Exception as e:  # noqa: BLE001 - reset/timeout di RETE (httpx)
            # Upload lunghi (centinaia di blocchi) muoiono per un singolo reset
            # TCP (WinError 10054, visto 03/07 sull'evento da 437MB): l'insert
            # e' append-only per-evento dopo la delete iniziale → riprovare lo
            # STESSO blocco e' sicuro. Backoff esponenziale, max 5 tentativi.
            net_retry += 1
            if net_retry > 5:
                raise
            import time as _t
            wait = min(30.0, 2.0 * net_retry)
            logger.warning(
                "[db] insert %s: errore di rete (%s) — retry %d/5 tra %.0fs",
                table, str(e)[:80], net_retry, wait,
            )
            _t.sleep(wait)
            continue
    return len(rows)


def upload_snapshots(event_id: str, rows: List[Dict[str, Any]]) -> int:
    delete_event_rows("live_market_snapshots", event_id)
    return insert_rows_resilient("live_market_snapshots", rows)


def upload_timeline(event_id: str, rows: List[Dict[str, Any]]) -> int:
    delete_event_rows("live_score_timeline", event_id)
    return insert_rows_resilient("live_score_timeline", rows)


# ----------------------------------------------------------------------------
# live_run_log
# ----------------------------------------------------------------------------
def write_run_log(event_id: str, fields: Dict[str, Any]) -> None:
    sb = get_supabase_client()
    row = {"event_id": event_id, "updated_at": _now_iso(), **fields}
    sb.table("live_run_log").upsert(row, on_conflict="event_id").execute()


# ----------------------------------------------------------------------------
# live_signals (motore live, write-on-change)
# ----------------------------------------------------------------------------
def upsert_live_signals(
    event_id: str,
    signals: Dict[str, Any],
    model_meta: Optional[Dict[str, Any]] = None,
) -> None:
    sb = get_supabase_client()
    row = {
        "event_id": event_id,
        "signals": signals,
        "model_meta": model_meta,
        "updated_at": _now_iso(),
    }
    _exec_retry(sb.table("live_signals").upsert(row, on_conflict="event_id"))


# ----------------------------------------------------------------------------
# live_ladder (ladder LIVE per-mercato, write-on-change dal ladder_worker)
# ----------------------------------------------------------------------------
def upsert_live_ladder(row: Dict[str, Any]) -> None:
    """Ladder corrente di UN mercato → ``live_ladder`` (idempotente, write-on-change).

    Chiave UNICA: ``(event_id, market_id)`` → una sola riga per mercato, aggiornata in
    place ad ogni cambiamento del book (il ladder_worker salta la scrittura se la firma
    back/lay/trd/ltp non e' cambiata, per non stressare il DB). ``updated_at`` forzato.

    NB: l'``on_conflict`` DEVE puntare all'indice UNIQUE **NON parziale**
    ``idx_live_ladder_event_market`` su (event_id, market_id): un indice PARZIALE non e'
    utilizzabile come arbitro di ON CONFLICT (PostgREST/Postgres → errore 42P10).
    """
    sb = get_supabase_client()
    payload = dict(row)
    payload["updated_at"] = _now_iso()
    _exec_retry(sb.table("live_ladder").upsert(
        payload, on_conflict="event_id,market_id"
    ))


# ----------------------------------------------------------------------------
# live_alerts (avvisi limiti Betfair)
# ----------------------------------------------------------------------------
def insert_alert(
    level: str,
    code: str,
    message: str,
    event_id: Optional[str] = None,
) -> None:
    sb = get_supabase_client()
    sb.table("live_alerts").insert(
        {
            "level": level,
            "code": code,
            "message": message[:500],
            "event_id": event_id,
        }
    ).execute()


# ----------------------------------------------------------------------------
# Backtest Automatico (coda richieste + risultati) — usato dal worker locale
# ----------------------------------------------------------------------------
def claim_backtest_request() -> Optional[Dict[str, Any]]:
    """Prende UNA richiesta PENDING e la porta a RUNNING (claim ottimistico)."""
    sb = get_supabase_client()
    resp = (
        sb.table("live_backtest_requests")
        .select("*")
        .eq("status", "PENDING")
        .order("created_at")
        .limit(1)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    if not rows:
        return None
    req = rows[0]
    upd = (
        sb.table("live_backtest_requests")
        .update({"status": "RUNNING", "updated_at": _now_iso()})
        .eq("id", req["id"])
        .eq("status", "PENDING")  # guard contro doppia presa
        .execute()
    )
    if not (getattr(upd, "data", None) or []):
        return None  # presa da un altro worker
    return req


def set_backtest_status(
    request_id: str, status: str, error_detail: Optional[str] = None
) -> None:
    sb = get_supabase_client()
    sb.table("live_backtest_requests").update(
        {"status": status, "error_detail": (error_detail or None) and error_detail[:500],
         "updated_at": _now_iso()}
    ).eq("id", request_id).execute()


def write_backtest_results(request_id: str, rows: List[Dict[str, Any]]) -> int:
    sb = get_supabase_client()
    sb.table("live_backtest_results").delete().eq("request_id", request_id).execute()
    n = 0
    for i in range(0, len(rows), UPLOAD_CHUNK):
        chunk = [{"request_id": request_id, **r} for r in rows[i : i + UPLOAD_CHUNK]]
        sb.table("live_backtest_results").insert(chunk).execute()
        n += len(chunk)
    return n


# ----------------------------------------------------------------------------
# Live trading — specchio ordini + posizioni (scritti dal runner come service_role).
# Write-on-change da LiveTradingStrategy.process_orders. MONEY-CRITICAL: i numeri
# delle posizioni provengono SEMPRE da flumine ``blotter.get_exposures`` (mai
# ricalcolati a mano qui). Tabelle: betfair_live_orders, betfair_live_positions.
# ----------------------------------------------------------------------------
def upsert_live_order(row: Dict[str, Any]) -> None:
    """Specchio di UN ordine → ``betfair_live_orders`` (idempotente, write-on-change).

    Chiave UNICA per ordine: ``(mode, client_order_ref)``. ``client_order_ref`` (il nostro
    ``awlq<request_id>``, o in fallback il customerOrderRef di flumine) è SEMPRE presente e
    unico per ordine → una sola riga, aggiornata in place (bet_id/fill/status). Niente ghost
    possibili (una chiave = una riga); ``bet_id`` è solo una colonna che si valorizza quando
    l'Exchange/SimulatedExecution lo assegna. ``updated_at`` forzato ad ogni scrittura.

    NB money-critical: l'``on_conflict`` DEVE puntare a un indice UNIQUE **NON parziale**
    (``idx_blo_order_key`` su (mode, client_order_ref)). PostgREST/Postgres NON può usare un
    indice PARZIALE come arbitro di ON CONFLICT → errore 42P10 e specchio mai scritto.
    """
    sb = get_supabase_client()
    payload = dict(row)
    payload["updated_at"] = _now_iso()
    from .local_channel import publish as _lpub

    _lpub("order", payload)  # A7: fill realtime sul desktop
    _exec_retry(sb.table("betfair_live_orders").upsert(
        payload, on_conflict="mode,client_order_ref"
    ))


def find_live_order_ref(mode: str, bet_id: str) -> Optional[str]:
    """client_order_ref già presente nello specchio per (mode, bet_id), None se assente.

    Usato dalla riconciliazione post-riavvio di ``LiveTradingStrategy``: un ordine
    ricostruito dall'order stream perde il ref interno ``awlq<rid>``; se il suo bet_id è
    già specchiato, si deve AGGIORNARE quella riga, non crearne una seconda (chi somma lo
    specchio — xhedge — conterebbe l'esposizione due volte). Predilige il ref ``awlq…``.
    """
    sb = get_supabase_client()
    rows = (
        sb.table("betfair_live_orders")
        .select("client_order_ref")
        .eq("mode", mode)
        .eq("bet_id", bet_id)
        .limit(5)
        .execute()
        .data
        or []
    )
    refs = [r.get("client_order_ref") for r in rows if r.get("client_order_ref")]
    if not refs:
        return None
    for ref in refs:
        if str(ref).startswith("awlq"):
            return str(ref)
    return str(refs[0])


def upsert_live_position(row: Dict[str, Any]) -> None:
    """Esposizione di UNA selezione → ``betfair_live_positions`` (idempotente).

    Chiave di upsert: ``(mode, market_id, selection_id, handicap)``. I valori sono
    quelli restituiti da ``blotter.get_exposures`` / ``selection_exposure`` (flumine),
    mai ricalcolati a mano. ``updated_at`` forzato ad ogni scrittura.
    """
    sb = get_supabase_client()
    payload = dict(row)
    payload["updated_at"] = _now_iso()
    from .local_channel import publish as _lpub

    _lpub("position", payload)  # A7: esposizioni realtime sul desktop
    _exec_retry(sb.table("betfair_live_positions").upsert(
        payload, on_conflict="mode,market_id,selection_id,handicap"
    ))


# ----------------------------------------------------------------------------
# E34/E37 — P&L settled per mercato, stato rischio giornaliero, trade journal
# ----------------------------------------------------------------------------
def upsert_live_settled(row: Dict[str, Any]) -> None:
    """P&L REALIZZATO di UN mercato → ``betfair_live_settled`` (idempotente).

    Chiave di upsert: ``(mode, market_id)``. ``profit`` è la somma dei profit
    flumine (PAPER: ``order.simulated.profit``; LIVE: cleared orders Betfair),
    MAI ricalcolato a mano. ``updated_at`` forzato ad ogni scrittura.
    """
    sb = get_supabase_client()
    payload = dict(row)
    payload["updated_at"] = _now_iso()
    _exec_retry(sb.table("betfair_live_settled").upsert(
        payload, on_conflict="mode,market_id"
    ))


def upsert_live_risk_state(row: Dict[str, Any]) -> None:
    """Stato rischio giornaliero (singleton id=1) → ``betfair_live_risk_state``.

    Pubblicato dal daily_stop_worker (write-on-change): P&L di giornata,
    soglia attiva e flag stop_fired. La UI lo legge in realtime (top bar).
    """
    sb = get_supabase_client()
    payload = dict(row)
    payload["id"] = 1
    payload["updated_at"] = _now_iso()
    _exec_retry(sb.table("betfair_live_risk_state").upsert(payload, on_conflict="id"))


def insert_live_journal(row: Dict[str, Any]) -> None:
    """Una riga di trade journal (E37) → ``betfair_live_journal`` (append-only).

    Best-effort BY DESIGN nel chiamante: il journal non deve MAI bloccare o
    far fallire un ordine — gli errori vanno gestiti a monte (alert WARN).
    """
    sb = get_supabase_client()
    sb.table("betfair_live_journal").insert(dict(row)).execute()


# ----------------------------------------------------------------------------
# A2/A5/A6 — conto Betfair, heartbeat, pulizia specchio al riavvio
# ----------------------------------------------------------------------------
def upsert_live_account(available: Optional[float], exposure: Optional[float]) -> None:
    """Saldo/exposure del CONTO Betfair (fonte REST getAccountFunds) →
    ``betfair_live_account`` (singleton id=1, realtime → top bar)."""
    sb = get_supabase_client()
    _exec_retry(sb.table("betfair_live_account").upsert(
        {"id": 1, "available": available, "exposure": exposure, "updated_at": _now_iso()},
        on_conflict="id",
    ))


def upsert_live_heartbeat(*, runner: bool, pid: int, mode: Optional[str] = None) -> None:
    """Heartbeat del runner (``runner=True``: ts/pid/mode) o del watchdog
    (``runner=False``: watchdog_ts/watchdog_pid) → singleton id=1."""
    sb = get_supabase_client()
    now = _now_iso()
    if runner:
        payload = {"id": 1, "ts": now, "pid": pid, "mode": mode, "updated_at": now}
    else:
        payload = {"id": 1, "watchdog_ts": now, "watchdog_pid": pid, "updated_at": now}
    _exec_retry(sb.table("betfair_live_heartbeat").upsert(payload, on_conflict="id"))


def cleanup_paper_mirror() -> "tuple[int, int]":
    """A6 — pulizia dello specchio PAPER stantio al RIAVVIO del runner.

    Dopo un restart il blotter PAPER è vuoto: le righe paper di sessioni
    precedenti sono orfane (ordini/posizioni che non esistono più). Si
    eliminano SOLO le righe ``mode='paper'`` — le righe LIVE non vengono
    MAI toccate (specchiano denaro reale). Ritorna (n_ordini, n_posizioni).
    """
    sb = get_supabase_client()
    res_o = sb.table("betfair_live_orders").delete().eq("mode", "paper").execute()
    res_p = sb.table("betfair_live_positions").delete().eq("mode", "paper").execute()
    n_o = len(getattr(res_o, "data", None) or [])
    n_p = len(getattr(res_p, "data", None) or [])
    return n_o, n_p


def fail_stale_pending_requests(max_age_sec: float = 120.0) -> int:
    """A6 — al RIAVVIO marca ERROR le richieste orfane più vecchie di
    ``max_age_sec`` (entrambe le mode): sia le ``pending`` mai claimate, sia le
    ``processing`` interrotte a metà da un crash (fix review CRITICAL — senza
    questo restano bloccate per sempre, invisibili a ogni recupero).

    MONEY-CRITICAL: un comando accodato PRIMA di un crash e processato minuti
    dopo eseguirebbe a un mercato completamente diverso — mai eseguire comandi
    stantii. Le ``processing`` interrotte hanno esito INCERTO (parte delle
    operazioni può essere arrivata a Betfair): il messaggio lo DICHIARA e la
    riconciliazione col conto (reconcile_worker) mostra la verità.
    Eccezione: ``place_submin`` in processing ha la sua macchina a stati
    ripristinabile (submin_state) e NON va toccata.
    """
    from datetime import timedelta

    sb = get_supabase_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max_age_sec)).isoformat()
    res = (
        sb.table("betfair_live_order_requests")
        .update({
            "status": "error",
            "error": "richiesta STANTIA al riavvio del runner: non eseguita (ripetere se serve)",
            "processed_at": _now_iso(),
        })
        .eq("status", "pending")
        .lt("requested_at", cutoff)
        .execute()
    )
    n = len(getattr(res, "data", None) or [])
    res2 = (
        sb.table("betfair_live_order_requests")
        .update({
            "status": "error",
            "error": "richiesta INTERROTTA a metà da un riavvio del runner: esito INCERTO — "
                     "VERIFICARE ordini/posizioni sul conto (riconciliazione in corso) prima di ripetere",
            "processed_at": _now_iso(),
        })
        .eq("status", "processing")
        .neq("action", "place_submin")
        .lt("requested_at", cutoff)
        .execute()
    )
    return n + len(getattr(res2, "data", None) or [])
