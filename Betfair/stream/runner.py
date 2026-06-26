"""Runner: orchestratore long-running del sistema live (auto, multi-match, safe).

Da eseguire in LOCALE durante le partite. Caratteristiche:
  F1  registrazione DUALE su UNA subscription (raw nativo via tee + parsato).
  F2  motore segnali live (live_engine_pro) → live_signals (write-on-change).
  F3  auto-sottoscrizione: rileva nuove partite GIOCATA e le aggancia (supervisor
      che ricostruisce la subscription, debounced, niente sub/unsub rapidi).
  F4  auto-stop: a fine partita (MATCH_ODDS CLOSED) finalizza e carica QUEL evento,
      distanziando gli upload (anti-stress DB), e smette di tracciarlo.
  F5  sicurezza limiti Betfair: budget mercati (WARN/REFUSE), backoff, alert in-app.

Uso:
    python -m Betfair.stream.runner            # aggancia le GIOCATA e streamma (auto)
    python -m Betfair.stream.runner --event <event_id>   # solo un evento (test)
    python -m Betfair.stream.runner --no-auto-subscribe  # niente ri-subscription dinamica
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import betfairlightweight
from betfairlightweight.filters import streaming_market_data_filter, streaming_market_filter
from flumine import Flumine, clients
from flumine.worker import BackgroundWorker

from Betfair.client import BetfairClient

from . import db, limits, uploader
from .auth import build_client, safe_logout
from .config_stream import (
    BACKOFF_BASE_SEC,
    BACKOFF_MAX_SEC,
    BANKROLL,
    DATA_DIR,
    FALLBACK_RETRY_PRIMARY_SEC,
    FALLBACK_THRESHOLD,
    FINALIZE_POLL_SEC,
    FINALIZE_SPACING_SEC,
    HARD_MARKET_CAP,
    KELLY_FRACTION,
    LADDER_DEPTH,
    MIN_RESUBSCRIBE_INTERVAL_SEC,
    RAW_RECORDING,
    SAFE_MARKET_THRESHOLD,
    SCORE_POLL_SEC,
    SIGNAL_MIN_EDGE,
    SIGNALS_ENABLED,
    STREAM_CONFLATE_MS,
    STREAM_FIELDS,
    WATCHLIST_POLL_SEC,
)
from .raw_listener import RawTeeMarketStream, close_raw, configure_raw
from .recorder import MarketRecorderStrategy
from .scores.api_football import ApiFootballProvider
from .scores.betfair_inplay import BetfairInPlayProvider
from .scores.poller import ScorePoller
from .watchlist import resolve_and_register

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Catalogo mercati completo (tutti i tipi) via REST JSON-RPC
# ----------------------------------------------------------------------------
def fetch_event_markets(rest: BetfairClient, event_id: str) -> List[Dict[str, Any]]:
    """Catalogo COMPLETO dei mercati di un evento (tutti i market type)."""
    params = {
        "filter": {"eventIds": [event_id]},
        "maxResults": 1000,
        "marketProjection": ["MARKET_START_TIME", "RUNNER_DESCRIPTION", "MARKET_DESCRIPTION", "EVENT"],
    }
    catalogues = rest.betting_rpc("SportsAPING/v1.0/listMarketCatalogue", params) or []
    markets: List[Dict[str, Any]] = []
    for i, c in enumerate(catalogues):
        desc = c.get("description") or {}
        runners = [
            {
                "selection_id": r.get("selectionId"),
                "name": r.get("runnerName"),
                "sort_priority": r.get("sortPriority"),
            }
            for r in (c.get("runners") or [])
        ]
        markets.append(
            {
                "market_id": c.get("marketId"),
                "market_type": desc.get("marketType"),
                "market_name": c.get("marketName"),
                "sort_priority": i,
                "selections": runners,
            }
        )
    return markets


# ----------------------------------------------------------------------------
# Sessione live condivisa (persiste tra i restart del supervisore)
# ----------------------------------------------------------------------------
class LiveSession:
    def __init__(self) -> None:
        self.recorder: Optional[MarketRecorderStrategy] = None
        self.context_api_client: Optional[Any] = None         # APIClient (set dal runner)
        self.only_event: Optional[str] = None
        self.pollers: Dict[str, ScorePoller] = {}             # event_id -> poller
        self.markets_by_event: Dict[str, List[Dict[str, Any]]] = {}
        self.market_to_event: Dict[str, str] = {}             # riferimento vivo (raw tee)
        self.market_type_by_id: Dict[str, str] = {}
        self.event_markets: Dict[str, set] = {}               # event_id -> set(market_id)
        self.selection_names: Dict[str, Dict[str, str]] = {}  # market_id -> {sel: name}
        self.prematch_lambdas: Dict[str, tuple] = {}          # event_id -> (lh, la, league)
        self.finished_events: set = set()                     # eventi finalizzati
        self.cataloged_events: set = set()                    # eventi con catalogo già scaricato
        self._score_files: Dict[str, Any] = {}
        self._last_score_sig: Dict[str, tuple] = {}
        self._last_signal_sig: Dict[str, Any] = {}
        self._finalize_lock = threading.Lock()
        self.restart_requested = threading.Event()
        self.last_resubscribe_ts = 0.0
        self.backoff = limits.Backoff(base_sec=BACKOFF_BASE_SEC, max_sec=BACKOFF_MAX_SEC)

    def score_file(self, event_id: str) -> Any:
        fh = self._score_files.get(event_id)
        if fh is None:
            ev_dir = os.path.join(DATA_DIR, event_id)
            os.makedirs(ev_dir, exist_ok=True)
            fh = open(os.path.join(ev_dir, f"{event_id}.scores.jsonl"), "a", encoding="utf-8")  # noqa: SIM115
            self._score_files[event_id] = fh
        return fh

    def close_score_files(self) -> None:
        for fh in self._score_files.values():
            try:
                fh.close()
            except Exception:  # noqa: BLE001
                pass
        self._score_files.clear()

    def all_market_ids(self) -> List[str]:
        return list(self.market_to_event.keys())

    def build_live_state(self, event_id: str) -> Dict[str, Any]:
        """State compatto per live_now (best back/lay/ltp con nomi)."""
        latest = self.recorder.latest_books() if self.recorder else {}
        markets_out: List[Dict[str, Any]] = []
        for m in self.markets_by_event.get(event_id, []):
            mid = m["market_id"]
            book = latest.get(mid)
            if not book:
                continue
            names = self.selection_names.get(mid, {})
            sels = []
            for sel_id, r in (book.get("runners") or {}).items():
                back = r.get("b") or []
                lay = r.get("l") or []
                sels.append(
                    {
                        "selection_id": int(sel_id),
                        "name": names.get(str(sel_id)),
                        "back": back[0][0] if back else None,
                        "lay": lay[0][0] if lay else None,
                        "ltp": r.get("ltp"),
                    }
                )
            markets_out.append(
                {
                    "market_id": mid,
                    "market_type": m.get("market_type"),
                    "market_name": m.get("market_name"),
                    "selections": sels,
                }
            )
        return {"markets": markets_out, "updated_ms": int(datetime.now(timezone.utc).timestamp() * 1000)}

    def ladder_by_market(self, event_id: str) -> Dict[str, Any]:
        """Ladder per il motore: {market_id: {sel: {back,lay,ltp,tv}}}."""
        latest = self.recorder.latest_books() if self.recorder else {}
        out: Dict[str, Any] = {}
        for m in self.markets_by_event.get(event_id, []):
            mid = m["market_id"]
            book = latest.get(mid)
            if not book:
                continue
            out[mid] = {
                sel: {"back": r.get("b", []), "lay": r.get("l", []), "ltp": r.get("ltp"), "tv": r.get("tv")}
                for sel, r in (book.get("runners") or {}).items()
            }
        return out


# ----------------------------------------------------------------------------
# Worker: punteggio + motore segnali (F2)
# ----------------------------------------------------------------------------
def score_worker(context: dict, flumine: Flumine, session: LiveSession) -> None:
    for event_id, poller in list(session.pollers.items()):
        if event_id in session.finished_events:
            continue
        try:
            snap = poller.poll(event_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("[score-worker] poll KO %s: %s", event_id, e)
            continue

        state = session.build_live_state(event_id)
        # un solo snapshot della cache (evita N acquisizioni di lock per evento)
        latest = session.recorder.latest_books() if session.recorder else {}
        inplay = any(
            (latest.get(m["market_id"], {}) or {}).get("inplay")
            for m in session.markets_by_event.get(event_id, [])
        )

        if snap is not None:
            try:
                db.update_live_now(
                    event_id, state=state, inplay=inplay,
                    minute=snap.minute, score_home=snap.score_home, score_away=snap.score_away,
                    status="OPEN" if inplay else "SUSPENDED", score_source=snap.source,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[score-worker] update_live_now KO %s: %s", event_id, e)
            sig = (snap.minute, snap.score_home, snap.score_away)
            if session._last_score_sig.get(event_id) != sig:
                session._last_score_sig[event_id] = sig
                try:
                    ts_ms = int(datetime.fromisoformat(snap.ts).timestamp() * 1000)
                except (ValueError, TypeError):
                    ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                rec = {
                    "ts": snap.ts, "ts_ms": ts_ms, "source": snap.source, "minute": snap.minute,
                    "score_home": snap.score_home, "score_away": snap.score_away,
                    "event_type": snap.event_type, "payload": snap.payload,
                }
                fh = session.score_file(event_id)
                fh.write(json.dumps(rec, default=str) + "\n")
                fh.flush()
        else:
            try:
                db.update_live_now(event_id, state=state, inplay=inplay, status="OPEN")
            except Exception:  # noqa: BLE001
                pass

        # --- F2: motore segnali live (write-on-change) ---
        if SIGNALS_ENABLED:
            _compute_and_write_signals(event_id, session, snap)


def _compute_and_write_signals(event_id: str, session: LiveSession, snap: Any) -> None:
    try:
        from .engine import live_engine_pro as pro  # import lazy (modulo costruito a parte)
    except Exception as e:  # noqa: BLE001
        logger.debug("[signals] live_engine_pro non disponibile: %s", e)
        return
    try:
        lam = session.prematch_lambdas.get(event_id)
        ladder = session.ladder_by_market(event_id)
        if lam is None:
            # ricava λ dal mercato MATCH_ODDS se già disponibile (home/away per
            # sort_priority, non per probabilità → niente inversione casa/trasferta)
            mo_market = None
            mo_ladder = None
            for m in session.markets_by_event.get(event_id, []):
                if m.get("market_type") == "MATCH_ODDS":
                    mo_market = m
                    mo_ladder = ladder.get(m["market_id"])
                    break
            lh, la, league = pro.get_prematch_lambdas(
                event_id, None, match_odds_market=mo_market, ladder=mo_ladder
            )
            lam = (lh, la, league)
            # CACHE solo se i λ provengono da dati reali; altrimenti ricalcola al
            # prossimo tick (evita di restare bloccati su λ di default).
            if mo_market and mo_ladder:
                session.prematch_lambdas[event_id] = lam
        signals = pro.evaluate_event(
            score_home=getattr(snap, "score_home", None) or 0,
            score_away=getattr(snap, "score_away", None) or 0,
            minute=getattr(snap, "minute", None),
            prematch_lambda_home=lam[0], prematch_lambda_away=lam[1], league_id=lam[2],
            markets=session.markets_by_event.get(event_id, []),
            ladder_by_market=ladder, bankroll=BANKROLL,
            min_edge=SIGNAL_MIN_EDGE, kelly_fraction=KELLY_FRACTION,
        )
        payload = pro.signals_to_json(signals)
        payload["updated_ms"] = int(datetime.now(timezone.utc).timestamp() * 1000)
        # write-on-change: aggiorna quando cambia direzione O la prob (arrotondata
        # a 2 decimali) di qualche selezione → fresco ma senza stressare il DB.
        sig_key = tuple(sorted(
            (s.market_id, s.selection_id, s.direction, round(s.model_prob, 2)) for s in signals
        ))
        if session._last_signal_sig.get(event_id) != sig_key:
            session._last_signal_sig[event_id] = sig_key
            db.upsert_live_signals(event_id, payload)
    except Exception as e:  # noqa: BLE001
        logger.warning("[signals] calcolo KO %s: %s", event_id, e)


# ----------------------------------------------------------------------------
# Worker: finalize per-evento a fine partita (F4)
# ----------------------------------------------------------------------------
def finalize_worker(context: dict, flumine: Flumine, session: LiveSession) -> None:
    if session.recorder is None:
        return
    finished = session.recorder.drain_finished()
    for event_id in finished:
        if event_id in session.finished_events:
            continue
        _finalize_event(event_id, session)
        time.sleep(FINALIZE_SPACING_SEC)  # distanzia gli upload (anti-stress DB)
    # auto-exit (modalità --event): a partita finita ferma il framework → il
    # processo esce e notifica. In multi-match il supervisore continua a girare.
    if finished and getattr(session, "only_event", None):
        active = [e for e in session.cataloged_events if e not in session.finished_events]
        if not active:
            logger.info("[finalize] tutte le partite finite (modalità --event): stop.")
            _stop_framework(flumine)


def _finalize_event(event_id: str, session: LiveSession) -> None:
    with session._finalize_lock:
        if event_id in session.finished_events:
            return
        session.finished_events.add(event_id)
    _safe_set_status(event_id, "CLOSED")
    try:
        uploader.upload_event(event_id)
        logger.info("[finalize] evento %s caricato e chiuso.", event_id)
    except FileNotFoundError:
        logger.warning("[finalize] nessun dato grezzo per %s", event_id)
        _safe_set_status(event_id, "ERROR", "nessun file grezzo")
    except Exception as e:  # noqa: BLE001
        logger.exception("[finalize] upload KO %s: %s", event_id, e)
        _safe_set_status(event_id, "ERROR", str(e)[:300])
    # smette di tracciare l'evento
    session.pollers.pop(event_id, None)
    fh = session._score_files.pop(event_id, None)
    if fh is not None:
        try:
            fh.close()
        except Exception:  # noqa: BLE001
            pass


# ----------------------------------------------------------------------------
# Worker: auto-sottoscrizione nuove GIOCATA (F3)
# ----------------------------------------------------------------------------
def subscription_worker(context: dict, flumine: Flumine, session: LiveSession) -> None:
    rest: BetfairClient = context["rest"]
    try:
        resolve_and_register(rest)
    except Exception as e:  # noqa: BLE001
        logger.warning("[sub-worker] resolve_and_register KO: %s", e)
        return
    try:
        follows = db.list_pending_follows()
    except Exception as e:  # noqa: BLE001
        logger.warning("[sub-worker] list_pending_follows KO: %s", e)
        return
    new_events = [
        f for f in follows
        if f["event_id"] not in session.cataloged_events
        and f["event_id"] not in session.finished_events
    ]
    if not new_events:
        return
    # rispetta l'intervallo minimo tra ri-subscription (niente churn rapido)
    now = time.monotonic()
    if (now - session.last_resubscribe_ts) < MIN_RESUBSCRIBE_INTERVAL_SEC:
        return
    logger.info("[sub-worker] %d nuove partite GIOCATA → ricostruzione subscription.", len(new_events))
    try:
        db.insert_alert("INFO", "NEW_MATCHES", f"{len(new_events)} nuove partite agganciate al live.")
    except Exception as e:  # noqa: BLE001 - un errore di alert NON deve bloccare la ri-subscription
        logger.warning("[sub-worker] insert_alert KO (ignorato): %s", e)
    session.last_resubscribe_ts = now
    session.restart_requested.set()
    _stop_framework(flumine)


def _stop_framework(flumine: Flumine) -> None:
    """Ferma flumine in modo pulito (per ricostruire la subscription)."""
    try:
        flumine._running = False  # noqa: SLF001 - meccanismo di stop documentato di flumine
    except Exception as e:  # noqa: BLE001
        logger.warning("[runner] stop framework KO: %s", e)


def _safe_set_status(event_id: str, status: str, error_detail: Optional[str] = None) -> None:
    try:
        db.set_follow_status(event_id, status, error_detail)
    except Exception as e:  # noqa: BLE001
        logger.warning("[runner] set status %s per %s KO: %s", status, event_id, e)


# ----------------------------------------------------------------------------
# Costruzione catalogo + budget limiti (F5)
# ----------------------------------------------------------------------------
def _catalog_events(rest: BetfairClient, session: LiveSession, follows: List[Dict[str, Any]]) -> None:
    """Scarica il catalogo dei nuovi eventi, applica il budget mercati (F5)."""
    for f in follows:
        event_id = f["event_id"]
        if event_id in session.cataloged_events or event_id in session.finished_events:
            continue
        markets = fetch_event_markets(rest, event_id)
        if not markets:
            logger.warning("[runner] nessun mercato per %s", event_id)
            continue
        prospective = len(session.market_to_event) + len(markets)
        verdict = limits.check_market_budget(prospective, SAFE_MARKET_THRESHOLD, HARD_MARKET_CAP)
        if verdict == "REFUSE":
            msg = limits.budget_message(verdict, prospective, SAFE_MARKET_THRESHOLD, HARD_MARKET_CAP)
            logger.error("[runner] %s", msg)
            db.insert_alert("CRITICAL", "MARKET_CAP", msg, event_id)
            continue  # lascia PENDING: niente ban
        if verdict == "WARN":
            msg = limits.budget_message(verdict, prospective, SAFE_MARKET_THRESHOLD, HARD_MARKET_CAP)
            logger.warning("[runner] %s", msg)
            db.insert_alert("WARN", "MARKET_NEAR_CAP", msg, event_id)

        db.upsert_markets(event_id, markets)
        session.markets_by_event[event_id] = markets
        session.event_markets[event_id] = set()
        for m in markets:
            mid = m["market_id"]
            session.market_to_event[mid] = event_id
            session.market_type_by_id[mid] = m.get("market_type")
            session.event_markets[event_id].add(mid)
            session.selection_names[mid] = {str(s["selection_id"]): s.get("name") for s in m.get("selections", [])}
        # poller per evento
        session.pollers[event_id] = ScorePoller(
            BetfairInPlayProvider(session.context_api_client),  # type: ignore[attr-defined]
            ApiFootballProvider(fixture_id=f.get("fixture_id")),
            threshold=FALLBACK_THRESHOLD, retry_primary_sec=FALLBACK_RETRY_PRIMARY_SEC,
        )
        session.cataloged_events.add(event_id)
        _safe_set_status(event_id, "STREAMING")


# ----------------------------------------------------------------------------
# Supervisore: costruisce e (ri)avvia lo stream finché ci sono partite
# ----------------------------------------------------------------------------
def setup_and_run(only_event: Optional[str] = None, auto_subscribe: bool = True) -> List[str]:
    os.makedirs(DATA_DIR, exist_ok=True)
    rest = BetfairClient()
    rest.login_cert()
    api_client: betfairlightweight.APIClient = build_client(login=True)

    session = LiveSession()
    session.context_api_client = api_client  # type: ignore[attr-defined]
    session.only_event = only_event  # type: ignore[attr-defined]
    interrupted = False

    try:
        while not interrupted:
            session.restart_requested.clear()

            if not only_event:
                try:
                    resolve_and_register(rest)
                except Exception as e:  # noqa: BLE001
                    logger.warning("[runner] resolve_and_register iniziale KO: %s", e)

            follows = db.list_pending_follows()
            if only_event:
                follows = [f for f in follows if f["event_id"] == only_event]
            follows = [f for f in follows if f["event_id"] not in session.finished_events]
            if not follows:
                logger.warning("[runner] nessun evento da streammare.")
                break

            _catalog_events(rest, session, follows)
            market_ids = session.all_market_ids()
            if not market_ids:
                logger.warning("[runner] nessun mercato sottoscrivibile (budget?).")
                break

            recorder = MarketRecorderStrategy(
                market_filter=streaming_market_filter(market_ids=market_ids),
                market_data_filter=streaming_market_data_filter(
                    fields=list(STREAM_FIELDS), ladder_levels=LADDER_DEPTH
                ),
                conflate_ms=STREAM_CONFLATE_MS or None,
                stream_class=RawTeeMarketStream,  # F1: tee del raw nativo
                context={
                    "data_dir": DATA_DIR,
                    "market_to_event": session.market_to_event,
                    "market_type_by_id": session.market_type_by_id,
                    "event_markets": session.event_markets,
                    "depth": LADDER_DEPTH,
                },
            )
            session.recorder = recorder
            configure_raw(DATA_DIR, session.market_to_event, RAW_RECORDING)

            # NB: NON usare market_recording_mode=True → sopprime process_market_book
            # (i book parsati servono a live_now + segnali). Il raw nativo è comunque
            # registrato dal tee nel listener. order_stream=False: non piazziamo ordini.
            client = clients.BetfairClient(api_client, order_stream=False)
            framework = Flumine(client=client)
            framework.add_strategy(recorder)
            framework.add_worker(BackgroundWorker(
                framework, function=score_worker, interval=int(SCORE_POLL_SEC),
                func_kwargs={"session": session}, name="score_worker"))
            framework.add_worker(BackgroundWorker(
                framework, function=finalize_worker, interval=int(FINALIZE_POLL_SEC),
                func_kwargs={"session": session}, name="finalize_worker"))
            if auto_subscribe and not only_event:
                framework.add_worker(BackgroundWorker(
                    framework, function=subscription_worker, interval=int(WATCHLIST_POLL_SEC),
                    func_kwargs={"session": session}, context={"rest": rest}, name="subscription_worker"))

            logger.info("[runner] stream avviato: %d eventi, %d mercati.",
                        len(session.cataloged_events) - len(session.finished_events), len(market_ids))
            try:
                framework.run()
            except KeyboardInterrupt:
                logger.info("[runner] interruzione richiesta: finalizzo tutto...")
                interrupted = True
            except Exception as e:  # noqa: BLE001 - errore stream non gestito da flumine
                logger.exception("[runner] errore framework.run: %s", e)
                if only_event:
                    interrupted = True
                else:
                    delay = session.backoff.next_delay()
                    logger.warning("[runner] retry tra %.0fs (backoff)...", delay)
                    time.sleep(delay)
                    continue  # ricostruisce e ritenta (multi-match)

            if session.restart_requested.is_set() and not interrupted:
                logger.info("[runner] ricostruisco la subscription con le nuove partite...")
                continue
            break
    finally:
        # finalize di sicurezza: ogni evento ancora attivo non finalizzato
        for event_id in list(session.cataloged_events):
            if event_id not in session.finished_events:
                _finalize_event(event_id, session)
        session.close_score_files()
        close_raw()
        safe_logout(api_client)

    return sorted(session.finished_events)


def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Runner stream live Betfair (auto)")
    ap.add_argument("--event", default=None, help="streamma solo questo event_id (test)")
    ap.add_argument("--no-auto-subscribe", action="store_true", help="disabilita la ri-subscription dinamica")
    args = ap.parse_args()
    done = setup_and_run(only_event=args.event, auto_subscribe=not args.no_auto_subscribe)
    logger.info("[runner] terminato. Eventi finalizzati: %s", done)


if __name__ == "__main__":
    _main()
