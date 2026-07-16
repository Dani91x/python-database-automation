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
import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import betfairlightweight
from betfairlightweight.filters import streaming_market_data_filter, streaming_market_filter
from flumine import Flumine, clients
from flumine import config as flumine_config
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
    LADDER_MAX_LEVELS,
    LADDER_PUBLISH_SEC,
    LADDER_WOM_LEVELS,
    LIVE_ORDER_MODE,
    live_order_mode,
    LIVE_ORDER_QUEUE_POLL_SEC,
    LIVE_TRANSACTION_LIMIT,
    MIN_RESUBSCRIBE_INTERVAL_SEC,
    ORDER_STREAM_CONFLATE_MS,
    PAPER_SIMULATED_LATENCY_MS,
    BOARD_POLL_SEC,
    DAILY_STOP_POLL_SEC,
    HEARTBEAT_SEC,
    RAW_RECORDING,
    RECONCILE_POLL_SEC,
    RISK_ENGINE_POLL_SEC,
    SAFE_MARKET_THRESHOLD,
    SCORE_POLL_SEC,
    SIGNAL_MIN_EDGE,
    SIGNAL_MIN_LIQUIDITY,
    SIGNALS_ENABLED,
    SIGNALS_KEEPALIVE_SEC,
    STREAM_CONFLATE_MS,
    STREAM_FIELDS,
    WATCHLIST_POLL_SEC,
    XHEDGE_POLL_SEC,
)
from . import local_channel as _lc
from .board_worker import board_worker
from .daily_stop_worker import daily_stop_worker
from .reconcile_worker import reconcile_worker
from .engine.live_trading_strategy import LiveTradingStrategy
from .live_order_worker import live_order_worker
from .risk_engine_worker import risk_engine_worker
from .trading.controls import LiveEventExposureControl, LiveExposureControl, LiveRateControl
from .xhedge_worker import xhedge_worker
from .raw_listener import RawTeeMarketStream, close_raw, configure_raw
from .recorder import MarketRecorderStrategy
from .runner_lifecycle import (
    any_follow_alive,
    raw_stall_seconds,
    stall_restart_due,
    uptime_exceeded,
)
from .single_instance import acquire_single_instance_lock
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
        # auto-spegnimento (fix 2026-07-08: runner mai più attivi per giorni)
        self.shutdown_requested = threading.Event()
        self.started_monotonic = time.monotonic()
        # epoca (monotonic) dell'ULTIMO framework.run(): rilevamento stallo
        # "stream mai connesso" nel heartbeat_worker (None = mai avviato).
        self.stream_started_monotonic: Optional[float] = None
        self.pollers: Dict[str, ScorePoller] = {}             # event_id -> poller
        self.markets_by_event: Dict[str, List[Dict[str, Any]]] = {}
        self.fixture_by_event: Dict[str, Any] = {}            # event_id -> fixture_id (per λ DB)
        self.market_to_event: Dict[str, str] = {}             # riferimento vivo (raw tee)
        self.market_type_by_id: Dict[str, str] = {}
        self.event_markets: Dict[str, set] = {}               # event_id -> set(market_id)
        self.selection_names: Dict[str, Dict[str, str]] = {}  # market_id -> {sel: name}
        self.prematch_lambdas: Dict[str, tuple] = {}          # event_id -> (lh, la, league)
        self.finished_events: set = set()                     # eventi finalizzati
        self.cataloged_events: set = set()                    # eventi con catalogo già scaricato
        self._score_files: Dict[str, Any] = {}
        self._timeline_files: Dict[str, Any] = {}
        self._seen_events: Dict[str, set] = {}     # event_id -> set(update_id) già scritti
        self._recent_events: Dict[str, list] = {}  # event_id -> ultimi eventi (per live_now)
        self._last_score_sig: Dict[str, tuple] = {}
        self._last_signal_sig: Dict[str, Any] = {}
        # F38: epoch dell'ultima SCRITTURA di live_signals per evento (keepalive:
        # un segnale invariato ma ancora CONFERMATO dal motore va rinfrescato, o
        # la UI lo crederebbe stantio e nasconderebbe fair/Kelly ancora validi).
        self._last_signal_write: Dict[str, float] = {}
        self._last_ladder_sig: Dict[str, str] = {}  # market_id -> firma (write-on-change ladder)
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

    def timeline_file(self, event_id: str) -> Any:
        fh = self._timeline_files.get(event_id)
        if fh is None:
            ev_dir = os.path.join(DATA_DIR, event_id)
            os.makedirs(ev_dir, exist_ok=True)
            fh = open(os.path.join(ev_dir, f"{event_id}.timeline.jsonl"), "a", encoding="utf-8")  # noqa: SIM115
            self._timeline_files[event_id] = fh
        return fh

    def close_score_files(self) -> None:
        for fh in list(self._score_files.values()) + list(self._timeline_files.values()):
            try:
                fh.close()
            except Exception:  # noqa: BLE001
                pass
        self._score_files.clear()
        self._timeline_files.clear()

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
                    "status": book.get("status"),  # OPEN/SUSPENDED/CLOSED → badge/banner UI
                    "selections": sels,
                }
            )
        return {
            "markets": markets_out,
            # modalità ordini attiva del runner (OFF|PAPER|LIVE): la UI la legge da
            # live_now.state.order_mode per mostrare il badge giusto nel pannello Live Trading.
            # live_order_mode() RI-LEGGE l'env ad ogni call (coerente col worker): se a runtime
            # si declassa LIVE→OFF/PAPER, il badge segue subito invece di restare "LIVE" stale.
            "order_mode": live_order_mode(),
            "updated_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
        }

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
        # cattura cronologia eventi Betfair (gol/cartellini/kickoff col minuto)
        _capture_timeline(event_id, session)
        # arricchisci live_now con statistiche live (corner/cartellini) + eventi recenti
        state["stats"] = snap.stats if snap is not None else {}
        state["events"] = session._recent_events.get(event_id, [])

        if snap is not None:
            try:
                db.update_live_now(
                    event_id, state=state, inplay=inplay,
                    minute=snap.minute, score_home=snap.score_home, score_away=snap.score_away,
                    status="OPEN" if inplay else "SUSPENDED", score_source=snap.source,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[score-worker] update_live_now KO %s: %s", event_id, e)
            # write-on-change su punteggio O statistiche (corner/cartellini)
            sig = (snap.minute, snap.score_home, snap.score_away,
                   snap.corners_home, snap.corners_away,
                   snap.yellow_home, snap.yellow_away, snap.red_home, snap.red_away)
            if session._last_score_sig.get(event_id) != sig:
                session._last_score_sig[event_id] = sig
                try:
                    ts_ms = int(datetime.fromisoformat(snap.ts).timestamp() * 1000)
                except (ValueError, TypeError):
                    ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                rec = {
                    "ts": snap.ts, "ts_ms": ts_ms, "source": snap.source, "minute": snap.minute,
                    "score_home": snap.score_home, "score_away": snap.score_away,
                    "event_type": snap.event_type, "stats": snap.stats, "payload": snap.payload,
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


def _capture_timeline(event_id: str, session: LiveSession) -> None:
    """Cattura la cronologia eventi Betfair (gol/cartellini/...) e registra i nuovi.

    Scrive ogni evento NUOVO (per update_id) su <event>.timeline.jsonl e mantiene
    gli ultimi eventi in memoria per live_now. Best-effort: non rompe mai il worker.
    """
    poller = session.pollers.get(event_id)
    primary = getattr(poller, "primary", None) if poller else None
    if not isinstance(primary, BetfairInPlayProvider):
        return
    try:
        events = primary.get_timeline(event_id)
    except Exception as e:  # noqa: BLE001
        logger.debug("[timeline] KO %s: %s", event_id, e)
        return
    if not events:
        return
    seen = session._seen_events.setdefault(event_id, set())
    fh = None
    for ev in events:
        uid = ev.get("update_id")
        if uid in seen:
            continue
        seen.add(uid)
        ev_rec = {**ev, "ts": datetime.now(timezone.utc).isoformat()}
        if fh is None:
            fh = session.timeline_file(event_id)
        fh.write(json.dumps(ev_rec, default=str) + "\n")
    if fh is not None:
        fh.flush()
    # ultimi eventi per il pannello live (gol/cartellini ordinati per minuto)
    session._recent_events[event_id] = events[-8:]


def _signals_write_due(
    last_sig: Any, last_write_ts: float, sig_key: Any, now_s: float, keepalive_sec: float,
) -> bool:
    """PURA (testabile): va scritta la riga live_signals? True se il segnale è CAMBIATO
    (write-on-change) oppure se è invariato ma l'ultima scrittura è più vecchia del
    keepalive (F38: il motore lo sta ri-confermando → refresh updated_at, così la UI
    distingue 'stabile e valido' da 'motore fermo')."""
    if last_sig != sig_key:
        return True
    return (now_s - last_write_ts) >= keepalive_sec


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
            # PRIOR #1 (migliore): λ PER-SQUADRA Dixon-Coles dal pre-match DB.
            db_lam = None
            try:
                db_lam = db.get_fixture_prematch_lambdas(session.fixture_by_event.get(event_id))
            except Exception as e:  # noqa: BLE001 - mai bloccare i segnali per il DB
                logger.debug("[signals] λ DB KO %s: %s", event_id, e)
            if db_lam:
                lam = db_lam
                session.prematch_lambdas[event_id] = lam   # storico per-squadra: stabile
            else:
                # PRIOR #2: TOTALE gol dal mercato O/U — VALIDO SOLO PRE-MATCH (a 0-0,
                # prima del kickoff l'O/U prezza i gol di TUTTA la partita). In-play
                # l'O/U prezza i gol RIMANENTI → invertirlo come totale è distorto
                # (caveat double-counting). Quindi lo usiamo solo a inizio partita;
                # il λ viene poi BLOCCATO e riusato per tutto il match.
                _mn = getattr(snap, "minute", None)
                _sc = (getattr(snap, "score_home", 0) or 0) + (getattr(snap, "score_away", 0) or 0)
                prematch = (_mn is None or _mn <= 3) and _sc == 0
                total = pro.total_goals_from_ou(session.markets_by_event.get(event_id, []), ladder) if prematch else None
                mo_market = mo_ladder = None
                for m in session.markets_by_event.get(event_id, []):
                    if m.get("market_type") == "MATCH_ODDS":
                        mo_market = m
                        mo_ladder = ladder.get(m["market_id"])
                        break
                lh, la, league = pro.get_prematch_lambdas(
                    event_id, None, match_odds_market=mo_market, ladder=mo_ladder,
                    expected_total_goals=total,
                )
                lam = (lh, la, league)
                # cache solo con totale data-driven (no lock sul default)
                if mo_market and mo_ladder and total is not None:
                    session.prematch_lambdas[event_id] = lam
        signals = pro.evaluate_event(
            score_home=getattr(snap, "score_home", None) or 0,
            score_away=getattr(snap, "score_away", None) or 0,
            minute=getattr(snap, "minute", None),
            prematch_lambda_home=lam[0], prematch_lambda_away=lam[1], league_id=lam[2],
            markets=session.markets_by_event.get(event_id, []),
            ladder_by_market=ladder, bankroll=BANKROLL,
            min_edge=SIGNAL_MIN_EDGE, kelly_fraction=KELLY_FRACTION,
            min_liquidity=SIGNAL_MIN_LIQUIDITY,
            # stato LIVE: cartellini rossi correnti (la pressione corner/tiri è un
            # hook neutro finché non calibrata).
            red_home=getattr(snap, "red_home", 0) or 0,
            red_away=getattr(snap, "red_away", 0) or 0,
            yellow_home=getattr(snap, "yellow_home", 0) or 0,
            yellow_away=getattr(snap, "yellow_away", 0) or 0,
        )
        payload = pro.signals_to_json(signals)
        payload["updated_ms"] = int(datetime.now(timezone.utc).timestamp() * 1000)
        # F40: hazard gol imminente (stessa matematica dei segnali: λ residui calibrati
        # + CDF tempi-gol). None pre-match → chiave assente; best-effort dichiarato.
        try:
            hz = pro.event_goal_hazard(
                score_home=getattr(snap, "score_home", None),
                score_away=getattr(snap, "score_away", None),
                minute=getattr(snap, "minute", None),
                prematch_lambda_home=lam[0], prematch_lambda_away=lam[1], league_id=lam[2],
                red_home=getattr(snap, "red_home", 0) or 0,
                red_away=getattr(snap, "red_away", 0) or 0,
                yellow_home=getattr(snap, "yellow_home", 0) or 0,
                yellow_away=getattr(snap, "yellow_away", 0) or 0,
            )
            if hz is not None:
                payload["hazard"] = hz
        except Exception as e:  # noqa: BLE001 - l'hazard non deve mai rompere i segnali
            logger.debug("[signals] hazard KO %s: %s", event_id, e)
        # write-on-change: aggiorna quando cambia direzione O la prob (arrotondata
        # a 2 decimali) di qualche selezione → fresco ma senza stressare il DB.
        # F38 KEEPALIVE: un segnale INVARIATO è comunque ri-CONFERMATO dal motore a
        # ogni snapshot — se dall'ultima scrittura è passato più di
        # SIGNALS_KEEPALIVE_SEC, riscriviamo la riga (refresh updated_at) così la UI
        # distingue "stabile e ancora valido" (visibile) da "motore fermo/evento non
        # più seguito" (stantio → overlay nascosto). Mai un fair vecchio in UI.
        sig_key = tuple(sorted(
            (s.market_id, s.selection_id, s.direction, round(s.model_prob, 2)) for s in signals
        ))
        now_s = datetime.now(timezone.utc).timestamp()
        if _signals_write_due(
            session._last_signal_sig.get(event_id),
            session._last_signal_write.get(event_id, 0.0),
            sig_key, now_s, SIGNALS_KEEPALIVE_SEC,
        ):
            session._last_signal_sig[event_id] = sig_key
            session._last_signal_write[event_id] = now_s
            db.upsert_live_signals(event_id, payload)
    except Exception as e:  # noqa: BLE001
        logger.warning("[signals] calcolo KO %s: %s", event_id, e)


# ----------------------------------------------------------------------------
# Worker: ladder LIVE per-mercato (pubblica live_ladder, SOLA LETTURA / display)
# ----------------------------------------------------------------------------
def _as_levels(raw: Any, max_levels: Optional[int]) -> List[List[float]]:
    """Normalizza una lista [[price,size],...] a float, limitata a ``max_levels``.

    ``max_levels`` None/<=0 = tutti i livelli (usato per ``trd``, sempre full).
    Tollera dati malformati: salta i livelli non numerici senza sollevare.
    """
    out: List[List[float]] = []
    if not raw:
        return out
    seq = raw if (max_levels is None or max_levels <= 0) else raw[:max_levels]
    for lvl in seq:
        try:
            price, size = lvl[0], lvl[1]
            if price is None or float(price) <= 0:
                continue  # prezzo 0/negativo = dato corrotto: mai una riga "0.00" in UI
            out.append([float(price), float(size or 0.0)])
        except (TypeError, ValueError, IndexError):
            continue
    return out


def compute_wom(
    back: List[List[float]],
    lay: List[List[float]],
    levels: int = LADDER_WOM_LEVELS,
) -> Dict[str, float]:
    """Weight of Money: pressione rosa(back)/blu(lay) nei ~``levels`` livelli vicino al best.

    Somma le size disponibili al BACK e al LAY nei primi ``levels`` livelli e ne ricava la
    ripartizione percentuale. ``back_pct`` + ``lay_pct`` == 100.0 quando c'e' size; entrambi
    0.0 se non c'e' alcuna size (mercato vuoto/sospeso) → niente divisione per zero. Le due
    percentuali sono complementari (``lay_pct = 100 - back_pct``) per evitare drift di
    arrotondamento e tenere la somma esatta.
    """
    n = levels if levels and levels > 0 else 1
    back_sz = sum(s for _, s in back[:n])
    lay_sz = sum(s for _, s in lay[:n])
    total = back_sz + lay_sz
    if total <= 0:
        return {"back_pct": 0.0, "lay_pct": 0.0}
    back_pct = round(back_sz / total * 100.0, 1)
    return {"back_pct": back_pct, "lay_pct": round(100.0 - back_pct, 1)}


def build_ladder_selection(
    selection_id: Any,
    runner: Dict[str, Any],
    name: Optional[str],
    max_levels: int = LADDER_MAX_LEVELS,
) -> Dict[str, Any]:
    """Una selezione della ladder dai dati dello stream (recorder.latest_books runner).

    back/lay limitati a ``max_levels`` (profondita' sottoscritta); ``trd`` (volume tradato
    per-prezzo) sempre FULL; WOM calcolato sui livelli vicino al best.
    """
    back = _as_levels(runner.get("b"), max_levels)
    lay = _as_levels(runner.get("l"), max_levels)
    trd = _as_levels(runner.get("trd"), None)
    return {
        "selection_id": int(selection_id),
        "name": name,
        "ltp": runner.get("ltp"),
        "tv": runner.get("tv"),
        "back": back,
        "lay": lay,
        "trd": trd,
        "wom": compute_wom(back, lay),
    }


def ladder_signature(selections: List[Dict[str, Any]]) -> str:
    """Firma stabile della ladder per il WRITE-ON-CHANGE.

    Cattura ESATTAMENTE i campi che muovono il display: ltp + livelli back/lay + volume
    tradato per-prezzo (trd) di ogni selezione. tv/wom sono DERIVATI da questi (tv segue il
    traded, wom segue back/lay) → non serve includerli e non causano riscritture spurie.
    SHA-1 su una rappresentazione deterministica: compatto da tenere in memoria per mercato.
    """
    payload = [
        (
            s["selection_id"],
            s["ltp"],
            tuple(tuple(lvl) for lvl in s["back"]),
            tuple(tuple(lvl) for lvl in s["lay"]),
            tuple(tuple(lvl) for lvl in s["trd"]),
        )
        # ordine STABILE per selection_id: dopo un restart F3 la libreria potrebbe
        # consegnare i runner in ordine diverso → senza sort la firma cambierebbe a parità
        # di dati (una riscrittura spuria per mercato per riconnessione).
        for s in sorted(selections, key=lambda x: x["selection_id"])
    ]
    return hashlib.sha1(repr(payload).encode("utf-8")).hexdigest()  # noqa: S324 - firma, non crittografia


def build_ladder_payload(
    book: Dict[str, Any],
    names: Dict[str, str],
    max_levels: int = LADDER_MAX_LEVELS,
) -> Dict[str, Any]:
    """Costruisce { updated_ms, selections:[...] } da un book serializzato (latest_books)."""
    selections = [
        build_ladder_selection(sel_id, r, names.get(str(sel_id)), max_levels)
        for sel_id, r in (book.get("runners") or {}).items()
    ]
    return {
        "updated_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
        "selections": selections,
    }


def ladder_worker(context: dict, flumine: Flumine, session: LiveSession) -> None:
    """Pubblica la ladder PIENA di ogni mercato sottoscritto su ``live_ladder``.

    SOLA LETTURA dal punto di vista Betfair: usa esclusivamente i book GIA' in cache
    (recorder.latest_books) → ZERO chiamate API aggiuntive. WRITE-ON-CHANGE per mercato
    (firma back/lay/trd/ltp) → non stressa il DB. Best-effort: un errore su un mercato non
    deve far cadere il runner. Registrato SEMPRE quando si streamma (a prescindere da
    LIVE_ORDER_MODE), come score_worker/finalize_worker.
    """
    if session.recorder is None:
        return
    latest = session.recorder.latest_books()
    for event_id, markets in list(session.markets_by_event.items()):
        if event_id in session.finished_events:
            continue
        for m in markets:
            mid = m["market_id"]
            book = latest.get(mid)
            if not book:
                continue
            try:
                payload = build_ladder_payload(
                    book, session.selection_names.get(mid, {}), LADDER_MAX_LEVELS
                )
                # lo STATUS entra nella firma: un OPEN→SUSPENDED→CLOSED deve pubblicarsi
                # (la UI sbiadisce sospeso/chiuso) anche se i livelli non cambiano.
                sig = (book.get("status") or "") + "|" + ladder_signature(payload["selections"])
            except Exception as e:  # noqa: BLE001 - un mercato malformato non blocca gli altri
                logger.debug("[ladder-worker] build KO %s: %s", mid, e)
                continue
            if session._last_ladder_sig.get(mid) == sig:
                continue  # write-on-change: book invariato → nessuna scrittura
            row = {
                "event_id": event_id,
                "market_id": mid,
                "market_type": m.get("market_type"),
                "market_name": m.get("market_name"),
                "status": book.get("status"),
                "ladder": payload,
            }
            # A7: push locale IMMEDIATO su ogni cambio del book (il desktop vede il
            # tick alla velocità del worker); il DB resta il fallback remoto e viene
            # scritto al massimo ogni 2s per mercato quando il desktop è collegato
            # (write-on-change invariato quando il desktop NON c'è).
            local_on = _lc.channel_active()
            if local_on:
                _lc.publish("ladder", row)
                now_m = time.monotonic()
                ts_map = getattr(session, "_last_ladder_db_ts", None)
                if ts_map is None:
                    ts_map = {}
                    session._last_ladder_db_ts = ts_map
                if now_m - ts_map.get(mid, 0.0) < 2.0:
                    session._last_ladder_sig[mid] = sig
                    continue
                ts_map[mid] = now_m
            try:
                db.upsert_live_ladder(row)
                session._last_ladder_sig[mid] = sig
            except Exception as e:  # noqa: BLE001 - un errore DB non deve far cadere il runner
                logger.warning("[ladder-worker] upsert KO %s: %s", mid, e)


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
    """Ferma DAVVERO ``framework.run()`` (resubscribe/auto-spegnimento/daily-stop).

    BUG FIX (cert PAPER 10/07): flumine 2.13.11 (flumine/flumine.py::run) è un
    ``while True`` bloccato su ``handler_queue.get()`` che esce SOLO estraendo un
    evento TERMINATOR — ``_running=False`` non è MAI testato nel loop. Con lo
    stream quieto (mercati chiusi) il vecchio stop non fermava nulla: il
    sub-worker chiedeva la ricostruzione ogni 2 minuti senza effetto e le nuove
    partite restavano PENDING per sempre. Stesso fix già presente nel tennis
    (tennis_runner._stop_framework): accodiamo un ``TerminationEvent`` → il loop
    fa ``break`` → ``__exit__`` chiude worker/stream puliti → il main loop
    ricostruisce la subscription.
    """
    try:
        from flumine.events.events import TerminationEvent

        flumine._running = False  # noqa: SLF001 - coerenza di stato (non basta a fermare run())
        flumine.handler_queue.put(TerminationEvent(flumine))
    except Exception as e:  # noqa: BLE001
        logger.warning("[runner] stop framework KO: %s", e)


# ----------------------------------------------------------------------------
# AUTO-SPEGNIMENTO (fix incidente 2026-07-08: runner attivi per giorni)
# ----------------------------------------------------------------------------
# (a) vita massima assoluta; (b) uscita per inattività quando NESSUN follow attivo è
# in corso o imminente. 0 = disattiva la singola condizione. Il lock di singola
# istanza (porta localhost) impedisce i runner duplicati.
_RUNNER_MAX_HOURS = float(os.getenv("LIVE_RUNNER_MAX_HOURS", "18"))
_RUNNER_IDLE_EXIT_MIN = float(os.getenv("LIVE_RUNNER_IDLE_EXIT_MIN", "45"))
_RUNNER_LOCK_PORT = int(os.getenv("LIVE_RUNNER_LOCK_PORT", "47311"))
_INSTANCE_LOCK = None  # socket del lock di singola istanza (referenza viva, vedi _main)


def _lifecycle_blockers(flumine: Flumine) -> Optional[str]:
    """Motivo per cui NON è sicuro spegnersi (None = via libera). Il denaro viene PRIMA
    del comfort: ordini VIVI nel blotter o regole risk armate/innescate (stop, offset,
    chase, stop-entry) = il runner resta acceso — spegnerlo lascerebbe protezioni morte
    e ordini non gestiti. In dubbio (blotter/DB illeggibili) si resta ACCESI."""
    try:
        for market in flumine.markets:
            blotter = getattr(market, "blotter", None)
            live = list(getattr(blotter, "live_orders", None) or []) if blotter is not None else []
            if live:
                return f"{len(live)} ordini vivi sul mercato {getattr(market, 'market_id', '?')}"
    except Exception:  # noqa: BLE001
        return "blotter non leggibile (prudenza: resto acceso)"
    if LIVE_ORDER_MODE.strip().upper() in ("PAPER", "LIVE"):
        try:
            from db_client import get_supabase_client
            rows = (get_supabase_client().table("betfair_live_risk_rules").select("id")
                    .in_("status", ["armed", "triggered"])
                    .eq("mode", LIVE_ORDER_MODE.strip().lower())
                    .limit(1).execute().data or [])
            if rows:
                return "regole di rischio armate/innescate (stop/offset/chase/stop-entry)"
        except Exception:  # noqa: BLE001
            return "regole di rischio non verificabili (prudenza: resto acceso)"
    return None


_RAW_STALL_ALERTED = False
# Stallo PERSISTENTE del flusso di mercato (incidente 2026-07-16: stream MUTO
# dalle 15:29Z con runner vivo per ~1.5h → nessun dato registrato, raw MAI
# creati per i nuovi follow): oltre questa soglia il runner ricostruisce la
# subscription da solo (stesso path collaudato del restart F3). 0 = disattivo.
_RAW_STALL_RESTART_SEC = float(os.getenv("LIVE_RAW_STALL_RESTART_SEC", "600"))
# throttle delle ricostruzioni forzate (mai churn di subscription)
_RAW_STALL_RESTART_MIN_INTERVAL_SEC = float(
    os.getenv("LIVE_RAW_STALL_RESTART_MIN_INTERVAL_SEC", "900"))
_RAW_STALL_LAST_RESTART = 0.0
# keepAlive sessione Betfair ANCHE durante lo streaming (fix 16/07): prima era
# rinnovata SOLO nel loop idle → dopo ore di stream una RICONNESSIONE (drop di
# rete, restart F3) usava un token scaduto e lo stream restava muto per sempre.
_STREAM_KEEPALIVE_SEC = float(os.getenv("LIVE_STREAM_KEEPALIVE_SEC", "480"))
_STREAM_KA_LAST = 0.0


def heartbeat_worker(context: dict, flumine: Flumine, session: LiveSession) -> None:  # noqa: ARG001
    """A5 — battito del runner → betfair_live_heartbeat (singleton, realtime).

    La UI mostra "runner vivo Xs fa" in top bar; oltre soglia il chip diventa
    rosso (runner giù/appeso). Best-effort: un DB momentaneamente KO non deve
    mai far cadere il runner (il prossimo battito riallinea)."""
    try:
        db.upsert_live_heartbeat(runner=True, pid=os.getpid(), mode=live_order_mode())
    except Exception as ex:  # noqa: BLE001 - heartbeat best-effort
        logger.debug("[runner] heartbeat KO: %s", str(ex)[:120])
    # keepAlive periodico della sessione Betfair mentre si streamma (fix 16/07,
    # vedi _STREAM_KEEPALIVE_SEC): best-effort, mai far cadere il runner.
    global _STREAM_KA_LAST
    now_mono = time.monotonic()
    if _STREAM_KEEPALIVE_SEC > 0 and now_mono - _STREAM_KA_LAST >= _STREAM_KEEPALIVE_SEC:
        _STREAM_KA_LAST = now_mono
        try:
            from .auth import keep_alive as _bf_keep_alive

            _bf_keep_alive(session.context_api_client)
        except Exception as ex:  # noqa: BLE001 - keepAlive best-effort
            logger.warning("[runner] keepAlive sessione (stream) KO: %s", str(ex)[:120])
    # RECORDER VIVO (fix 11/07, lezione 10/07: tee nativo morto in silenzio =
    # in-play irrecuperabile): se il tee e' abilitato, ci sono mercati
    # sottoscritti ma NESSUN write raw da >120s → alert WARN (una volta,
    # si riarma quando il flusso riprende). write_errors incluso.
    try:
        from .raw_listener import RAW_STATE

        global _RAW_STALL_ALERTED, _RAW_STALL_LAST_RESTART
        h = RAW_STATE.health()
        if h.get("enabled") and session.market_to_event:
            last = max(h.get("last_write_ms", {}).values() or [0])
            now_ms = time.time() * 1000.0
            started = getattr(session, "stream_started_monotonic", None)
            # last==0 = MAI scritto in questa vita del processo (il caso 16/07:
            # stream mai connesso dopo il rebuild) → conta dall'avvio dello stream.
            stall_s = raw_stall_seconds(
                last, now_ms, (now_mono - started) if started is not None else None)
            stalled = stall_s is not None and stall_s > 120.0
            if stalled and not _RAW_STALL_ALERTED:
                _RAW_STALL_ALERTED = True
                db.insert_alert(
                    "WARN", "RAW_RECORDER",
                    f"tee raw NATIVO fermo da {stall_s:.0f}s "
                    f"con stream attivo (write_errors={h.get('write_errors')}) "
                    "— i backtest/Atlante perderebbero questi dati",
                )
            elif not stalled:
                _RAW_STALL_ALERTED = False
            # ESCALATION (fix 16/07): stallo PERSISTENTE → CRITICAL + ricostruzione
            # della subscription (throttled). L'alert WARN da solo non recupera
            # nulla: il 16/07 lo stream e' rimasto muto per ore con runner vivo.
            if (not session.shutdown_requested.is_set()
                    and stall_restart_due(
                        stall_s, _RAW_STALL_RESTART_SEC,
                        _RAW_STALL_LAST_RESTART, now_mono,
                        _RAW_STALL_RESTART_MIN_INTERVAL_SEC)):
                # GUARDIA MONEY-CRITICAL (review 16/07, stessa lezione del
                # tennis audit #1): il restart ricostruisce flumine con un
                # blotter VUOTO — MAI a ordini vivi o regole armate. Con un
                # blocker si alza solo l'alert (il retry avviene al prossimo
                # scadere del throttle, quando si è flat).
                blocker = _lifecycle_blockers(flumine)
                _RAW_STALL_LAST_RESTART = now_mono
                if blocker is not None:
                    logger.critical(
                        "[runner] stream MUTO da %.0fs ma restart RINVIATO: %s "
                        "— chiudi/gestisci manualmente per sbloccare il recovery.",
                        stall_s, blocker)
                    try:
                        db.insert_alert(
                            "CRITICAL", "RAW_RECORDER",
                            f"stream mercati MUTO da {stall_s:.0f}s ma recovery "
                            f"RINVIATO ({blocker}): il restart azzererebbe il "
                            "blotter con esposizione viva.")
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    logger.critical(
                        "[runner] REGISTRAZIONE INTERROTTA: nessun dato di mercato da "
                        "%.0fs con %d mercati sottoscritti — ricostruisco la subscription.",
                        stall_s, len(session.market_to_event))
                    try:
                        db.insert_alert(
                            "CRITICAL", "RAW_RECORDER",
                            f"stream mercati MUTO da {stall_s:.0f}s: registrazione "
                            "interrotta, ricostruisco la subscription (auto-recovery).")
                    except Exception:  # noqa: BLE001 - l'alert non blocca il recovery
                        pass
                    session.restart_requested.set()
                    _stop_framework(flumine)
    except Exception:  # noqa: BLE001 - telemetria best-effort
        pass


def lifecycle_worker(context: dict, flumine: Flumine, session: LiveSession) -> None:  # noqa: ARG001
    """Spegne il runner quando non serve più (mai più 'martellare Betfair' per giorni).

    Vita massima superata OPPURE nessuna partita in corso/imminente tra i follow
    attivi → shutdown pulito: il flusso normale finalizza e carica i Replay nel
    ``finally`` di setup_and_run. GUARDIE MONEY-CRITICAL su ENTRAMBI i trigger
    (fix review CRITICAL): mai spegnere con ordini vivi o regole di rischio armate.
    In caso di dubbio (DB/blotter illeggibili, open_date ambigua) resta ACCESO.
    """
    if session.shutdown_requested.is_set():
        return
    reason: Optional[str] = None
    if uptime_exceeded(session.started_monotonic, time.monotonic(), _RUNNER_MAX_HOURS):
        reason = f"vita massima {_RUNNER_MAX_HOURS:.0f}h raggiunta"
    # BUG FIX cert 10/07 (VISTO DAL VIVO): con LIVE_RUNNER_KEEP_ALIVE=1 (app desktop)
    # il ramo IDLE non deve spegnere — il main loop è progettato per restare in
    # ATTESA senza eventi (canale locale + board vivi), ma il lifecycle spegneva
    # comunque alla fine dell'ultima partita e il watchdog (correttamente) non
    # riavvia su exit 0 → runner desktop MORTO dopo la prima partita. La vita
    # massima resta attiva anche col keep-alive (backstop anti-"giorni acceso").
    elif os.getenv("LIVE_RUNNER_KEEP_ALIVE", "").strip() == "1":
        pass  # idle-exit disattivato dal keep-alive desktop
    elif _RUNNER_IDLE_EXIT_MIN > 0:
        try:
            follows = db.list_pending_follows()
        except Exception as e:  # noqa: BLE001 - DB illeggibile: non spegnere al buio
            logger.debug("[lifecycle] list_pending_follows KO (resto acceso): %s", e)
            return
        if session.only_event:  # modalità test single-event: solo il backstop (a)
            return
        stale_h = _FOLLOW_STALE_AFTER.total_seconds() / 3600.0
        if not any_follow_alive(follows, imminent_min=_RUNNER_IDLE_EXIT_MIN, stale_hours=stale_h):
            reason = (f"nessuna partita in corso o in partenza entro "
                      f"{_RUNNER_IDLE_EXIT_MIN:.0f} min ({len(follows)} follow in attesa)")
    if reason is None:
        return
    blocker = _lifecycle_blockers(flumine)
    if blocker is not None:
        logger.warning("[lifecycle] spegnimento RINVIATO (%s): %s.", reason, blocker)
        return
    logger.warning("[lifecycle] AUTO-SPEGNIMENTO runner: %s.", reason)
    try:
        db.insert_alert("INFO", "RUNNER_AUTO_STOP", f"Runner spento da solo: {reason}.")
    except Exception:  # noqa: BLE001 - l'alert è best-effort
        pass
    session.shutdown_requested.set()
    _stop_framework(flumine)


def _safe_set_status(event_id: str, status: str, error_detail: Optional[str] = None) -> None:
    try:
        db.set_follow_status(event_id, status, error_detail)
    except Exception as e:  # noqa: BLE001
        logger.warning("[runner] set status %s per %s KO: %s", status, event_id, e)


# ----------------------------------------------------------------------------
# Costruzione catalogo + budget limiti (F5)
# ----------------------------------------------------------------------------
# Un follow senza mercati nel catalogo Betfair è ambiguo: può essere una partita
# FINITA (mercati rimossi/CLOSED) oppure un evento FUTURO i cui mercati non sono
# ancora pubblicati. Se è iniziato da più di questa soglia è certamente concluso
# (una partita di calcio dura ~2h) → va ritirato, non lasciato PENDING.
_FOLLOW_STALE_AFTER = timedelta(hours=float(os.getenv("LIVE_FOLLOW_STALE_HOURS", "3")))


def _is_finished_stale(follow: Dict[str, Any]) -> bool:
    """True se l'evento è iniziato da oltre ``_FOLLOW_STALE_AFTER`` (quindi finito).

    Serve a distinguere, quando il catalogo non ha mercati, una partita conclusa
    (da ritirare: caricare nel Replay + chiudere) da un evento futuro con mercati
    non ancora pubblicati (da lasciare PENDING, si catalogherà al prossimo giro).
    """
    open_date = follow.get("open_date")
    if not open_date:
        return False
    try:
        dt = datetime.fromisoformat(str(open_date).replace("Z", "+00:00"))
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - dt > _FOLLOW_STALE_AFTER


def _catalog_events(rest: BetfairClient, session: LiveSession, follows: List[Dict[str, Any]]) -> None:
    """Scarica il catalogo dei nuovi eventi, applica il budget mercati (F5)."""
    for f in follows:
        event_id = f["event_id"]
        if event_id in session.cataloged_events or event_id in session.finished_events:
            continue
        markets = fetch_event_markets(rest, event_id)
        if not markets:
            if _is_finished_stale(f):
                # Partita finita/rimossa dal catalogo. NON lasciarla PENDING:
                # altrimenti subscription_worker la riconta come "nuova" ad ogni
                # poll e riavvia lo stream all'infinito (loop F3, bug 07/07).
                # _finalize_event la CARICA nel Replay (se ci sono dati grezzi),
                # porta lo status a terminale e la mette in finished_events così
                # non viene più ritentata. → "le vecchie caricate, le nuove seguite".
                logger.info("[runner] follow stantio %s: nessun mercato + iniziato da "
                            ">%s → ritiro e carico nel Replay.", event_id, _FOLLOW_STALE_AFTER)
                _finalize_event(event_id, session)
            else:
                # Evento futuro: mercati non ancora pubblicati. Lascia PENDING,
                # verrà catalogato al prossimo giro quando i mercati escono.
                logger.warning("[runner] nessun mercato per %s (non ancora pubblicati?)", event_id)
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
        session.fixture_by_event[event_id] = f.get("fixture_id")  # per λ pre-match DB
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
# Costruzione client flumine per modalità ordini (OFF / PAPER / LIVE)
# ----------------------------------------------------------------------------
def build_order_client(api_client: Any, mode: str) -> "tuple[clients.BetfairClient, bool]":
    """Costruisce il client flumine in base a ``LIVE_ORDER_MODE``.

    Ritorna ``(client, orders_enabled)`` dove ``orders_enabled`` indica se vanno
    registrati ``LiveTradingStrategy`` + ``live_order_worker`` (cioè mode != OFF):

      OFF   → order_stream=False, paper_trade=False. IDENTICO al comportamento storico
              (``clients.BetfairClient(api_client, order_stream=False)``): nessun order
              stream, nessuna esecuzione ordini → ZERO regressioni. orders_enabled=False.
      PAPER → paper_trade=True (forza SimulatedExecution su dati live, soldi FINTI) +
              order_stream=True → flumine apre un SimulatedOrderStream (NON quello reale): è lui a
              generare i CurrentOrdersEvent che fanno scattare process_orders → specchio ordini/pos.
      LIVE  → order_stream=True (fill REALI async via order stream). SOLDI VERI.

    NB: ``market_recording_mode`` resta False in tutte le modalità (i book parsati
    servono a live_now/segnali); il raw nativo è registrato dal tee nel listener.

    Controlli NATIVI flumine, cablati in modo COERENTE sulle 3 modalità:
      * ``min_bet_validation=False`` (fix CRITICAL-3) → il control nativo ``OrderValidation``
        NON conosce l'eccezione Betfair "bet che RIDUCE la liability" (green-up / hedge /
        cash-out sotto-minimo, che l'Exchange ACCETTA): con True rifiuterebbe client-side
        ogni chiusura di posizione piccola (per conto EUR: size < €1 e payout < €20) →
        cash-out falliti, e lo step1 del place-and-trim (LAY €0,50@1.01) mai piazzabile.
        La validazione dei minimi resta STRETTA, giurisdizione-aware (.it: back €2 /
        lay €0,50) e consapevole di ``reduces_liability`` in
        ``live_order_build.min_stake_rules`` — che copre OGNI ordine del worker.
      * ``transaction_limit=LIVE_TRANSACTION_LIMIT`` → soglia oraria del control nativo
        ``MaxTransactionCount`` (registrato da flumine in ``add_client``): guardia anti-runaway
        di place/cancel/replace, tenuta sotto la soglia Betfair (5000/h) degli addebiti.
      In OFF questi parametri sono INERTI (nessuna strategia ordini né worker coda registrati →
      nessun place possibile); servono solo a tenere i tre client coerenti. I trading_controls
      CUSTOM (``LiveExposureControl``/``LiveRateControl``) sono registrati sul framework in
      ``setup_and_run`` quando orders_enabled=True.
    """
    mode_u = (mode or "OFF").strip().upper()
    if mode_u == "LIVE":
        client = clients.BetfairClient(
            api_client,
            order_stream=True,
            order_stream_conflate_ms=ORDER_STREAM_CONFLATE_MS or None,
            paper_trade=False,
            # False: l'OrderValidation nativo non conosce l'eccezione reduces_liability
            # (green-up sotto-minimo, ammesso da Betfair) → i minimi li valida
            # live_order_build.min_stake_rules (fix CRITICAL-3, vedi docstring).
            min_bet_validation=False,
            transaction_limit=LIVE_TRANSACTION_LIMIT,
        )
        return client, True
    if mode_u == "PAPER":
        # Latenza simulata del fill PAPER: la SimulatedExecution di flumine usa
        # flumine.config.place_latency (secondi) come ritardo prima del match. Applichiamo
        # PAPER_SIMULATED_LATENCY_MS qui (ms→s) così l'utente controlla la velocità del paper
        # (come fa run_backtest.py per la simulazione). Solo PAPER: in OFF/LIVE non si tocca.
        if PAPER_SIMULATED_LATENCY_MS and PAPER_SIMULATED_LATENCY_MS > 0:
            flumine_config.place_latency = float(PAPER_SIMULATED_LATENCY_MS) / 1000.0
        client = clients.BetfairClient(
            api_client,
            # order_stream=True ANCHE in paper: con paper_trade=True flumine NON apre lo stream
            # ordini REALE ma un SimulatedOrderStream (streams.add_client: l'order stream — anche
            # simulato — si crea SOLO se order_stream=True). È lui a generare i CurrentOrdersEvent
            # che fanno scattare LiveTradingStrategy.process_orders → lo specchio si popola.
            order_stream=True,
            order_stream_conflate_ms=ORDER_STREAM_CONFLATE_MS or None,
            paper_trade=True,
            # False come in LIVE (fix CRITICAL-3): PAPER deve replicare il path reale.
            min_bet_validation=False,
            transaction_limit=LIVE_TRANSACTION_LIMIT,
        )
        return client, True
    # OFF (default) o valore sconosciuto → comportamento storico, nessun ordine.
    # min_bet_validation/transaction_limit sono inerti in OFF (nessun place possibile): li
    # passiamo solo per tenere i tre client coerenti.
    client = clients.BetfairClient(
        api_client,
        order_stream=False,
        min_bet_validation=False,
        transaction_limit=LIVE_TRANSACTION_LIMIT,
    )
    return client, False


def _announce_order_mode(mode: str, orders_enabled: bool) -> None:
    """Logga in modo EVIDENTE la modalità ordini e (se attiva) la annuncia in live_alerts.

    In OFF nessun side-effect oltre al log (ZERO regressioni: nessuna scrittura DB nuova).
    """
    mode_u = (mode or "OFF").strip().upper()
    banner = {
        "LIVE": "*** LIVE *** ORDINI REALI (SOLDI VERI) attivi",
        "PAPER": "PAPER -- ordini SIMULATI (soldi finti, dati live)",
        "OFF": "OFF -- nessun ordine (solo registrazione/segnali)",
    }.get(mode_u, f"{mode_u} -- modalita' sconosciuta: trattata come OFF")
    bar = "=" * 64
    logger.info("%s", bar)
    logger.info("[runner] MODALITA' ORDINI: %s", banner)
    logger.info("%s", bar)
    if not orders_enabled:
        return  # OFF → nessuna scrittura DB aggiuntiva
    level = "CRITICAL" if mode_u == "LIVE" else "INFO"
    try:
        db.insert_alert(level, "ORDER_MODE", f"Live trading: modalita' {mode_u} attiva. {banner}")
    except Exception as e:  # noqa: BLE001 - un alert non deve mai bloccare l'avvio
        logger.warning("[runner] insert_alert modalita' ordini KO (ignorato): %s", e)


# ----------------------------------------------------------------------------
# Supervisore: costruisce e (ri)avvia lo stream finché ci sono partite
# ----------------------------------------------------------------------------
def setup_and_run(only_event: Optional[str] = None, auto_subscribe: bool = True) -> List[str]:
    os.makedirs(DATA_DIR, exist_ok=True)
    # SWEEP di recupero Replay (best-effort, in background): carica le partite
    # finite rimaste non-UPLOADED (es. stream in ERROR a fine match, 02/07).
    # PERIODICO (non piu' one-shot all'avvio): se una registrazione va in ERROR
    # e il finalize non scatta, la partita finita viene comunque caricata nel
    # Replay entro ~15 min, senza bisogno di riavviare il runner.
    def _periodic_sweep() -> None:
        while True:
            try:
                # idle 10 min: una partita VIVA scrive il raw di continuo
                # (idle ~0) → mai toccata; solo le finite/interrotte (file
                # fermo da >=10 min) vengono curate e caricate nel Replay.
                uploader.sweep_pending(min_idle_min=10.0)
            except Exception:  # noqa: BLE001 - lo sweep non deve fermare il runner
                logger.exception("[uploader] sweep periodico KO")
            time.sleep(300)  # 5 min
    threading.Thread(target=_periodic_sweep, daemon=True,
                     name="uploader-sweep").start()
    rest = BetfairClient()
    rest.login_cert()
    api_client: betfairlightweight.APIClient = build_client(login=True)

    session = LiveSession()
    session.context_api_client = api_client  # type: ignore[attr-defined]
    session.only_event = only_event  # type: ignore[attr-defined]
    # A7 — canale LOCALE per l'app desktop (bind SOLO 127.0.0.1). Best-effort:
    # se la porta è occupata il runner vive comunque (path DB invariato).
    ch = _lc.start_channel(int(os.getenv("LIVE_LOCAL_WS_PORT", "47331")), "calcio")
    if ch is not None:
        ch.set_hello(mode=LIVE_ORDER_MODE)
    interrupted = False

    # Annuncia UNA volta la modalità ordini (il banner nei log + alert se PAPER/LIVE).
    # I restart F3 ricostruiscono il framework ma non ri-annunciano (niente spam alert).
    _announce_order_mode(LIVE_ORDER_MODE, LIVE_ORDER_MODE.strip().upper() in ("PAPER", "LIVE"))

    # A6 — RIPRESA dopo crash/riavvio (una volta per processo, PRIMA del framework):
    #   * specchio PAPER stantio → pulito (il blotter paper riparte vuoto: le righe
    #     di sessioni precedenti sono orfane). Le righe LIVE non si toccano MAI.
    #   * richieste ancora 'pending' più vecchie di 120s → ERROR esplicito: un
    #     comando accodato prima di un crash NON va eseguito minuti dopo a un
    #     mercato completamente diverso (money-critical, mai comandi stantii).
    # La ricostruzione LIVE dal conto (listCurrentOrders) è del reconcile_worker.
    if LIVE_ORDER_MODE.strip().upper() in ("PAPER", "LIVE"):
        try:
            n_ord, n_pos = db.cleanup_paper_mirror()
            n_stale = db.fail_stale_pending_requests(120.0)
            if n_ord or n_pos or n_stale:
                logger.info(
                    "[runner] ripresa: specchio paper pulito (%d ordini, %d posizioni), "
                    "%d richieste stantie marcate error", n_ord, n_pos, n_stale,
                )
                db.insert_alert(
                    "INFO", "RUNNER_RESUME",
                    f"riavvio runner: specchio paper pulito ({n_ord} ordini, {n_pos} "
                    f"posizioni), {n_stale} richieste stantie scartate",
                )
        except Exception as ex:  # noqa: BLE001 - la ripresa non blocca l'avvio
            logger.warning("[runner] pulizia ripresa KO: %s", str(ex)[:200])

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
                # DESKTOP (keep-alive): senza eventi il runner NON esce — resta in
                # attesa (canale locale + board vivi) e ricontrolla ogni 15s: il
                # click "Segui live" nell'app crea il follow e si parte subito.
                # Senza il flag (uso storico da terminale/cron): esce come sempre.
                if os.getenv("LIVE_RUNNER_KEEP_ALIVE", "").strip() == "1":
                    logger.info("[runner] nessun evento da streammare: attendo (keep-alive desktop).")
                    time.sleep(15)
                    # SESSIONE Betfair .it: scade dopo ~20 min di INATTIVITA' —
                    # senza keepAlive periodico il primo Segui live fallirebbe
                    # con INVALID_SESSION. Ogni ~8 min (32 giri da 15s).
                    _ka = getattr(session, "_idle_ka_count", 0) + 1
                    session._idle_ka_count = _ka
                    if _ka % 32 == 0:
                        try:
                            from .auth import keep_alive as _bf_keep_alive
                            _bf_keep_alive(api_client)
                            rest.login_cert()  # anche la sessione JSON-RPC del catalogo
                            logger.info("[runner] keepAlive sessione Betfair ok (idle).")
                        except Exception as _ex:  # noqa: BLE001
                            logger.warning("[runner] keepAlive sessione KO: %s", str(_ex)[:120])
                    continue
                logger.warning("[runner] nessun evento da streammare.")
                break

            _catalog_events(rest, session, follows)
            market_ids = session.all_market_ids()
            if not market_ids:
                if os.getenv("LIVE_RUNNER_KEEP_ALIVE", "").strip() == "1":
                    logger.info("[runner] nessun mercato sottoscrivibile: attendo (keep-alive desktop).")
                    time.sleep(15)
                    continue
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
            # registrato dal tee nel listener. Il client ordini dipende da LIVE_ORDER_MODE:
            # OFF (default) = order_stream=False, identico ad oggi → nessuna regressione.
            client, orders_enabled = build_order_client(api_client, LIVE_ORDER_MODE)
            framework = Flumine(client=client)
            framework.add_strategy(recorder)
            # Live trading (PAPER/LIVE): strategia specchio + worker coda ordini. In OFF
            # NON vengono registrati → comportamento storico invariato. Ri-registrati ad
            # ogni ricostruzione della subscription (F3 restart) come gli altri worker.
            if orders_enabled:
                # UNA sola istanza LiveTradingStrategy: registrata nel framework E passata al
                # worker. Gli ordini sono creati sotto QUESTA istanza (build_order(strategy=...))
                # così che flumine instradi process_orders → specchio ordini/posizioni. Senza
                # questo legame l'ordine resta orfano e lo specchio DB non si popola mai.
                # market_filter ESPLICITO (obbligatorio: BaseStrategy di flumine lo richiede
                # posizionale → senza, TypeError e il runner NON parte in PAPER/LIVE). Stessi
                # market_ids del recorder: la strategia è sottoscritta esattamente ai mercati
                # degli ordini. NB: process_orders è comunque dispatchato per OGNI mercato in cui
                # la strategia ha ordini nel blotter (baseflumine._process_current_orders itera
                # tutte le strategie a prescindere dal filtro) → lo specchio funziona sempre.
                live_strategy = LiveTradingStrategy(
                    market_filter=streaming_market_filter(market_ids=market_ids),
                    session=session, mode=LIVE_ORDER_MODE.lower())
                framework.add_strategy(live_strategy)
                # Controlli NATIVI flumine (Fase 6, #11): guardia esposizione per selezione +
                # rate-limit ordini/min, letti da betfair_live_settings (opt-in, NULL = off).
                # Sono l'ultima barriera money-critical DENTRO flumine, oltre a quelle del worker.
                framework.add_trading_control(LiveExposureControl)
                framework.add_trading_control(LiveRateControl)
                # E35: esposizione aggregata per EVENTO/CAMPIONATO (worst-case flumine
                # market_exposure sommato sui mercati; chiusure mai bloccate).
                framework.add_trading_control(LiveEventExposureControl)
                # interval FLOAT: BackgroundWorker lo passa a time.sleep → int() troncava i poll
                # sub-secondo (0.5→0→1). Usiamo il float direttamente (or 1.0 = guardia anti-zero).
                framework.add_worker(BackgroundWorker(
                    framework, function=live_order_worker, interval=LIVE_ORDER_QUEUE_POLL_SEC or 1.0,
                    func_kwargs={"session": session, "strategy": live_strategy},
                    name="live_order_worker"))
                # Risk engine (Fase 3): monitora le regole armate (offset/stop-loss/take-profit/
                # trailing) e ACCODA le chiusure nella STESSA coda ordini (path audited/mirror).
                # Usa la STESSA istanza LiveTradingStrategy per leggere le esposizioni MATCHED.
                framework.add_worker(BackgroundWorker(
                    framework, function=risk_engine_worker, interval=RISK_ENGINE_POLL_SEC or 1.0,
                    func_kwargs={"session": session, "strategy": live_strategy},
                    name="risk_engine_worker"))
                # Hedging cross-market (#9): analisi P&L per-scoreline dell'evento → betfair_live_xhedge
                # (sola lettura, display). Cadenza lenta. Usa la session per catalogo + book in cache.
                framework.add_worker(BackgroundWorker(
                    framework, function=xhedge_worker, interval=XHEDGE_POLL_SEC or 5.0,
                    func_kwargs={"session": session, "strategy": live_strategy},
                    name="xhedge_worker"))
                # E34 — stop giornaliero di conto: P&L di giornata (settled + MTM
                # blotter) vs daily_loss_limit → kill-switch AUTOMATICO + alert
                # CRITICAL. Pubblica betfair_live_risk_state (top bar). Stessa
                # istanza strategy per leggere le esposizioni dal blotter.
                framework.add_worker(BackgroundWorker(
                    framework, function=daily_stop_worker, interval=DAILY_STOP_POLL_SEC or 5.0,
                    func_kwargs={"session": session, "strategy": live_strategy},
                    name="daily_stop_worker"))
                # A2/A6 — riconciliazione col CONTO Betfair (verità ultima):
                # saldo in betfair_live_account; in LIVE: ordini esterni visibili,
                # divergenze specchio↔conto corrette+alert, settled da REST,
                # report di ripresa + verifica regole armate al primo giro.
                framework.add_worker(BackgroundWorker(
                    framework, function=reconcile_worker, interval=RECONCILE_POLL_SEC or 30.0,
                    func_kwargs={"session": session, "strategy": live_strategy},
                    name="reconcile_worker"))
            framework.add_worker(BackgroundWorker(
                framework, function=score_worker, interval=SCORE_POLL_SEC,
                func_kwargs={"session": session}, name="score_worker"))
            # Ladder LIVE: pubblica live_ladder per ogni mercato sottoscritto (display
            # SOLA LETTURA). Registrato SEMPRE (come score_worker), a prescindere da
            # LIVE_ORDER_MODE: usa solo i book in cache → nessuna API Betfair aggiuntiva.
            # interval FLOAT (sub-secondo possibile): BackgroundWorker lo passa a time.sleep.
            framework.add_worker(BackgroundWorker(
                framework, function=ladder_worker, interval=LADDER_PUBLISH_SEC or 1.0,
                func_kwargs={"session": session}, name="ladder_worker"))
            framework.add_worker(BackgroundWorker(
                framework, function=finalize_worker, interval=FINALIZE_POLL_SEC,
                func_kwargs={"session": session}, name="finalize_worker"))
            # A7 — board del giorno per il desktop (quote standard, REST leggero;
            # NESSUN costo senza client locali collegati).
            framework.add_worker(BackgroundWorker(
                framework, function=board_worker, interval=BOARD_POLL_SEC or 10.0,
                func_kwargs={"session": session, "event_type_id": "1"},
                name="board_worker"))
            # A5 — heartbeat del runner (SEMPRE, anche in OFF): la top bar mostra
            # "runner vivo Xs fa" e il watchdog/l'utente vedono subito un runner giù.
            framework.add_worker(BackgroundWorker(
                framework, function=heartbeat_worker, interval=HEARTBEAT_SEC or 10.0,
                func_kwargs={"session": session}, name="heartbeat_worker"))
            # auto-spegnimento (fix 2026-07-08): controlla ogni minuto vita massima
            # e inattività — mai più runner accesi per giorni a martellare Betfair.
            framework.add_worker(BackgroundWorker(
                framework, function=lifecycle_worker, interval=60.0,
                func_kwargs={"session": session}, name="lifecycle_worker"))
            if auto_subscribe and not only_event:
                framework.add_worker(BackgroundWorker(
                    framework, function=subscription_worker, interval=WATCHLIST_POLL_SEC,
                    func_kwargs={"session": session}, context={"rest": rest}, name="subscription_worker"))

            logger.info("[runner] stream avviato: %d eventi, %d mercati.",
                        len(session.cataloged_events) - len(session.finished_events), len(market_ids))
            # epoca dello stream corrente: serve al rilevamento "stream MAI
            # connesso" del heartbeat_worker (stallo con last_write_ms==0).
            session.stream_started_monotonic = time.monotonic()
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

            if session.shutdown_requested.is_set():
                logger.info("[runner] auto-spegnimento: finalizzo e esco.")
                break
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
    # SINGOLA ISTANZA (fix 2026-07-08: due runner attivi insieme): il lock vive quanto
    # il processo (il socket va tenuto referenziato); la seconda istanza esce subito.
    global _INSTANCE_LOCK  # noqa: PLW0603 - referenza viva per tutta la vita del processo
    _INSTANCE_LOCK = acquire_single_instance_lock(_RUNNER_LOCK_PORT, "runner")
    # NB: l'endpoint HTTP quote/ordini (8787) NON è ospitato qui: vive solo in
    # start_order_server.py (aggiorna_quote_betfair.bat). Così questo runner e il
    # server quote/ordini possono girare INSIEME senza contendersi la porta.
    done = setup_and_run(only_event=args.event, auto_subscribe=not args.no_auto_subscribe)
    logger.info("[runner] terminato. Eventi finalizzati: %s", done)


if __name__ == "__main__":
    _main()
