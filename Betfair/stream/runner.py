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
from typing import Any, Dict, List, Optional, Set, Tuple

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
    FIRST_ATTACH_MIN_INTERVAL_SEC,
    IDLE_FOLLOW_POLL_SEC,
    HARD_MARKET_CAP,
    LIVE_MARKET_TYPES,
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
    SUB_WORKER_POLL_SEC,
    WATCHLIST_POLL_SEC,
    XHEDGE_POLL_SEC,
)
from . import local_channel as _lc
from . import canale_bot as _cb
from . import ladder_canale as _lcad
from .config_stream import LADDER_CANALE_MS
from . import avvio_app as AA
from . import modo_ordini as _MO
from .board_worker import board_worker
from .board_worker import giro_da_parcheggiato as _board_da_parcheggiato
from .daily_stop_worker import daily_stop_worker
from .reconcile_worker import (
    attiva_saldo_su_evento,
    reconcile_worker,
    run_account_sync_if_due,
    sync_account_worker,
)
from .engine.live_trading_strategy import LiveTradingStrategy
from .live_order_worker import live_order_worker
from . import live_order_worker as _LOW
from . import motore_ordini as _MOT  # 24/09: _MO e' modo_ordini (master)
from . import auto_follow as _AF  # 25/09: i bot seguono da soli le partite
from . import frammenti_mercato as _FR  # 28/09: piu' connessioni di mercato (cantiere B)
from . import arresto_ordinato as _AO  # 28/09: spegnimento ordinato dell'app
from . import stream_muto as _SM  # 28/09: lo stream di mercato e' vivo? (cantiere J2)
from . import riserva_prezzi as _RP  # 28/09: prezzi di riserva a stream muto (cantiere J2)
from .risk_engine_worker import risk_engine_worker
from .trading.controls import LiveEventExposureControl, LiveExposureControl, LiveRateControl
from .xhedge_worker import xhedge_worker
from .raw_listener import RawTeeMarketStream, close_raw, configure_raw
from .recorder import MarketRecorderStrategy
from . import valuta as _valuta
from .runner_lifecycle import (
    any_follow_alive,
    effective_stall_seconds,
    raw_stall_seconds,
    stall_restart_due,
    uptime_exceeded,
    verdetto_post_ricostruzione,
    e_errore_di_rete,
    EXIT_PLANNED_RESTART,
    VERDETTO_ATTENDI,
    VERDETTO_GUARITO,
)
from .single_instance import acquire_single_instance_lock
from .scores.api_football import ApiFootballProvider
from .scores.betfair_inplay import BetfairInPlayProvider
from .scores.poller import ScorePoller
from .scores.scan_feed import ScanFeedScoreProvider
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
        # whitelist opzionale (LIVE_MARKET_TYPES): meno mercati per evento = più
        # partite seguibili entro il limite Betfair di 200 mercati/connessione
        if LIVE_MARKET_TYPES and str(desc.get("marketType") or "").upper() not in LIVE_MARKET_TYPES:
            continue
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
        # REGISTRAZIONE OPT-IN (17/07): event_id con live_follow.record=true →
        # solo questi passano dal tee raw e vengono caricati nel Replay.
        # None = colonna assente (migrazione non applicata) → registra TUTTO
        # (comportamento storico, mai rompere il runner).
        self.record_events: Optional[set] = None
        self._record_col_warned = False
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
        # AGGANCIO RAPIDO (fix 17/07 "Trading = streaming immediato"):
        #   * attach_attempted: eventi per cui un rebuild F3 è GIÀ stato richiesto
        #     (il bypass primo-aggancio vale solo per eventi mai tentati);
        #   * last_first_attach_bypass_ts: monotonic dell'ultimo rebuild ottenuto
        #     COL bypass (una sola finestra "gratis" ogni MIN_RESUBSCRIBE_INTERVAL);
        #   * last_resolve_ts: throttle interno di resolve_and_register (REST
        #     pesante) ora che il worker gira a cadenza fitta per la SELECT leggera.
        self.attach_attempted: set = set()
        self.last_first_attach_bypass_ts = -1e9
        self.last_resolve_ts = 0.0
        # PARITÀ CALCIO/TENNIS (fix 17/07): il restart F3 per nuovi follow è
        # RINVIATO finché ci sono blocker (ordini vivi/regole armate). Qui il
        # monotonic del PRIMO rinvio e dell'ultimo alert CRITICAL (anti-spam).
        self.sub_restart_deferred_since: Optional[float] = None
        self.sub_restart_defer_alert_ts = 0.0
        # backoff dell'alert (fix 17/07, terza review "alert fatigue"): il
        # blocco da regola armata è spesso ATTESO e può durare ore — l'alert
        # si ripete a intervalli CRESCENTI (x2, cap 1h), non ogni 5 minuti.
        self.sub_restart_defer_alert_interval = 0.0
        self.backoff = limits.Backoff(base_sec=BACKOFF_BASE_SEC, max_sec=BACKOFF_MAX_SEC)
        # ultima cattura timeline per evento (throttle, vedi _capture_timeline)
        self._timeline_ts: Dict[str, float] = {}
        # True se l'auto-spegnimento è un ricambio pianificato (desktop): il
        # processo esce con EXIT_PLANNED_RESTART e il watchdog lo rilancia
        self.planned_restart: bool = False
        # R-STREAM-1 (26/09): mercati della subscription corrente (manuali +
        # auto-follow; i secondi NON sono in market_to_event), monotonic della
        # ricostruzione chiesta per stallo (None = nessuna in osservazione),
        # uscita per stallo (i follow NON si chiudono: il processo nuovo li
        # riaggancia) e ultimo alert d'escalation rinviata (anti-spam).
        self.stream_market_count: int = 0
        self.stallo_rebuild_mono: Optional[float] = None
        self.riavvio_per_stallo: bool = False
        self.stallo_escala_alert_mono: float = -1e9

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
            # 24/09: e' il modo EFFETTIVO (tetto del .env x scelta dalla Control Room,
            # ``modo_ordini``), lo STESSO che il worker applica alle aperture; accanto
            # il tetto dell'ambiente e la scelta letta, perche' il badge dica il perche'.
            "order_mode": _MO.modo_corrente(),
            "order_mode_tetto": live_order_mode(),
            "order_mode_scelto": _MO.valore_db(),
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
        # 28/09 (cantiere A): un mercato CHIUSO non e' in gioco (l'ultimo book
        # porta ancora inplay=true: la riga direbbe "in gioco" fino al finalize)
        inplay = any(
            (latest.get(m["market_id"], {}) or {}).get("inplay")
            and str((latest.get(m["market_id"], {}) or {}).get("status") or "") != "CLOSED"
            for m in session.markets_by_event.get(event_id, [])
        )
        # cattura cronologia eventi Betfair (gol/cartellini/kickoff col minuto)
        _capture_timeline(event_id, session)
        # arricchisci live_now con statistiche live (corner/cartellini) + eventi recenti
        state["stats"] = snap.stats if snap is not None else {}
        state["events"] = session._recent_events.get(event_id, [])
        if event_id in session.finished_events:
            # 28/09 (cantiere A): finalizzata mentre questo giro leggeva il
            # punteggio: non si riscrive "in gioco" sopra la riga CLOSED
            continue

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


_TIMELINE_MIN_INTERVAL_SEC = float(os.getenv("LIVE_TIMELINE_POLL_SEC", "30"))


def _capture_timeline(event_id: str, session: LiveSession) -> None:
    """Cattura la cronologia eventi Betfair (gol/cartellini/...) e registra i nuovi.

    Scrive ogni evento NUOVO (per update_id) su <event>.timeline.jsonl e mantiene
    gli ultimi eventi in memoria per live_now. Best-effort: non rompe mai il worker.
    """
    poller = session.pollers.get(event_id)
    primary = getattr(poller, "primary", None) if poller else None
    if not isinstance(primary, (ScanFeedScoreProvider, BetfairInPlayProvider)):
        return
    # THROTTLE (audit 09/09): la timeline cambia a eventi discreti (gol,
    # cartellini) — prima era richiesta a OGNI giro del worker (5s) per evento.
    # Col feed dello scanner è una lettura in cache; la chiamata diretta (fallback)
    # non deve comunque superare una ogni _TIMELINE_MIN_INTERVAL_SEC.
    now_mono = time.monotonic()
    if now_mono - session._timeline_ts.get(event_id, 0.0) < _TIMELINE_MIN_INTERVAL_SEC:
        return
    session._timeline_ts[event_id] = now_mono
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
    """Costruisce { updated_ms, selections:[...] } da un book serializzato (latest_books).

    ``updated_ms`` = istante del book di flumine (``pt`` = publish_time_epoch, ms) se
    presente, altrimenti adesso (23/09: prima era sempre l'ora del worker).
    """
    selections = [
        build_ladder_selection(sel_id, r, names.get(str(sel_id)), max_levels)
        for sel_id, r in (book.get("runners") or {}).items()
    ]
    return {
        "updated_ms": _lcad.updated_ms_del_book(book),
        "selections": selections,
    }


def ladder_worker(context: dict, flumine: Flumine, session: LiveSession) -> None:
    """Pubblica la ladder PIENA di ogni mercato sottoscritto su ``live_ladder``.

    SOLA LETTURA dal punto di vista Betfair: usa esclusivamente i book GIA' in cache
    (recorder.latest_books) → ZERO chiamate API aggiuntive. WRITE-ON-CHANGE per mercato
    (firma back/lay/trd/ltp) → non stressa il DB. Best-effort: un errore su un mercato non
    deve far cadere il runner. Registrato SEMPRE quando si streamma (a prescindere da
    LIVE_ORDER_MODE), come score_worker/finalize_worker.

    23/09 - DUE CADENZE nello stesso worker (ladder_canale.py): il CANALE locale
    riceve il ladder ogni LIVE_LADDER_CANALE_MS (default 200 ms, 0 = a ogni book
    nuovo) e SOLO se ha client; il DB (live_ladder) resta a LADDER_PUBLISH_SEC
    (2 s) write-on-change. Firme separate: il canale non marca mai il DB come
    scritto (prima, col desktop collegato, un cambio caduto nella finestra dei 2 s
    poteva non arrivare mai al DB se il book poi restava fermo).
    """
    if session.recorder is None:
        return
    st = _lcad.stato_della_sessione(session, LADDER_PUBLISH_SEC, LADDER_CANALE_MS)
    fare_canale, fare_db = st.giro(_lc.channel_active())
    if not (fare_canale or fare_db):
        return  # nessun client e DB non ancora dovuto: giro a costo zero
    latest = session.recorder.latest_books()
    for event_id, markets in list(session.markets_by_event.items()):
        if event_id in session.finished_events:
            continue
        for m in markets:
            mid = m["market_id"]
            book = latest.get(mid)
            if not book:
                continue

            def _costruisci(book: Dict[str, Any] = book, mid: str = mid) -> Any:
                payload = build_ladder_payload(
                    book, session.selection_names.get(mid, {}), LADDER_MAX_LEVELS
                )
                # lo STATUS entra nella firma: un OPEN->SUSPENDED->CLOSED deve pubblicarsi
                # (la UI sbiadisce sospeso/chiuso) anche se i livelli non cambiano.
                sig = (book.get("status") or "") + "|" + ladder_signature(payload["selections"])
                return payload, sig
            try:
                sig, payload = st.versione(mid, book, _costruisci)
            except Exception as e:  # noqa: BLE001 - un mercato malformato non blocca gli altri
                logger.debug("[ladder-worker] build KO %s: %s", mid, e)
                continue
            al_canale = fare_canale and st.canale_cambiato(mid, sig)
            al_db = fare_db and session._last_ladder_sig.get(mid) != sig
            if not (al_canale or al_db):
                continue  # write-on-change: book invariato -> nessuna pubblicazione
            row = {
                "event_id": event_id,
                "market_id": mid,
                "market_type": m.get("market_type"),
                "market_name": m.get("market_name"),
                "status": book.get("status"),
                "ladder": payload,
            }
            if al_canale:
                _lc.publish("ladder", row)
                st.segna_canale(mid, sig)
            if not al_db:
                continue
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
    # 28/09 (cantiere A): un mercato di una partita gia' finita che chiude DOPO
    # (es. "To Qualify" ai supplementari) esce dal tetto al giro dopo
    if session.finished_events:
        _rilascia_mercati_finiti(session)
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
    # igiene (review 17/07, LOW): l'evento finito non serve più al bypass
    # primo-aggancio — il set non cresce senza bound per tutta la vita.
    getattr(session, "attach_attempted", set()).discard(event_id)
    _safe_set_status(event_id, "CLOSED")
    # 28/09 (cantiere A, fine evento): anche la riga live_now smette di dire
    # "in gioco" (il 26/09: 48 righe inplay=true mai ripulite dal 26/06) e i
    # mercati CHIUSI della partita escono dal tetto dell'auto-follow (e dalla
    # sottoscrizione, alla prossima risottoscrizione a caldo).
    _chiudi_live_now_sicuro(event_id)
    _rilascia_mercati_finiti(session)
    # REGISTRAZIONE OPT-IN (17/07): l'upload nel Replay avviene SOLO se la
    # partita era in registrazione ("Segui live", live_follow.record=true).
    # La verita' si legge dal DB al momento del finalize (mai da set in memoria:
    # un follow appena uscito da list_pending_follows non deve cambiare esito).
    # None = colonna assente/rete KO → comportamento STORICO (upload): meglio
    # un upload di troppo che perdere una registrazione voluta.
    should_record = db.get_follow_record(event_id)
    if should_record is False:
        # CLOSED e' lo status terminale pulito senza upload (il frontend lo
        # mostra come "Chiusa"; UPLOADED resta riservato ai Replay reali).
        logger.info(
            "[finalize] evento %s senza 'Segui live' (record=false): "
            "chiuso SENZA upload nel Replay.", event_id)
    else:
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


def _chiudi_live_now_sicuro(event_id: str) -> None:
    """``live_now`` della partita finita a CLOSED (best-effort: mai fermare il
    finalize per la riga di vetrina)."""
    try:
        db.chiudi_live_now(event_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("[finalize] live_now CLOSED di %s KO: %s", event_id, str(e)[:160])


def mercati_manuali_vivi(session: Any) -> Dict[str, set]:
    """28/09 (cantiere A): i mercati delle partite seguite A MANO che il runner
    deve ancora tenere nella sottoscrizione (e nel tetto dell'auto-follow).

    * partita non finita: tutti i suoi mercati (come prima);
    * partita FINITA (``finished_events``: MATCH_ODDS chiuso o tutti i mercati
      chiusi, oppure follow ritirato): solo i mercati NON ancora chiusi
      secondo il recorder (es. un "To Qualify" che continua ai supplementari).
      Quelli chiusi escono: Betfair li ha regolati, non c'e' piu' niente da
      vedere ne' da tradare, e occupavano il tetto dei 180 fino alla
      ricostruzione successiva (che puo' non arrivare mai)."""
    finite = set(getattr(session, "finished_events", None) or ())
    rec = getattr(session, "recorder", None)
    out: Dict[str, set] = {}
    for ev, ms in list((getattr(session, "event_markets", None) or {}).items()):
        tenuti = {str(m) for m in (ms or ())}
        if ev in finite:
            chiusi: set = set()
            if rec is not None and hasattr(rec, "mercati_chiusi"):
                try:
                    chiusi = {str(m) for m in rec.mercati_chiusi(ev)}
                except Exception:  # noqa: BLE001 - illeggibile: si tiene tutto
                    chiusi = set()
            tenuti -= chiusi
        if tenuti:
            out[str(ev)] = tenuti
    return out


def mercati_manuali_da_sottoscrivere(session: Any) -> List[str]:
    """28/09 (cantiere A): i mercati dei follow MANUALI da mettere nella
    sottoscrizione a ogni ricostruzione: quelli delle partite NON finite.
    Prima ``session.all_market_ids()`` (tutti, finite comprese): i mercati di
    una partita finita restavano sottoscritti per tutta la vita del processo."""
    finite = set(getattr(session, "finished_events", None) or ())
    return sorted(str(mid) for mid, ev in list(session.market_to_event.items())
                  if ev not in finite)


def _chiudi_live_now_orfani_all_avvio() -> int:
    """All'avvio: ``db.chiudi_live_now_orfani`` best-effort (mai bloccare il
    runner per la vetrina). Ritorna le righe chiuse (0 su errore)."""
    try:
        n = db.chiudi_live_now_orfani()
    except Exception as e:  # noqa: BLE001
        logger.warning("[runner] pulizia live_now orfane KO (ignorata): %s", str(e)[:160])
        return 0
    if n:
        logger.info("[runner] %d righe live_now di partite non piu' seguite portate a "
                    "CLOSED.", n)
    return n


def _rilascia_mercati_finiti(session: Any) -> None:
    """Il piano dell'auto-follow riceve i mercati manuali ancora vivi: i
    mercati chiusi delle partite finite escono dal tetto e, al giro dopo del
    thread dell'auto-follow, dalla sottoscrizione (risottoscrizione A CALDO
    sulla stessa connessione, blotter intatto). Senza auto-follow: niente (la
    ricostruzione successiva li esclude comunque, vedi ``setup_and_run``)."""
    auto = _auto_attivo()
    if auto is None:
        return
    try:
        auto.imposta_manuali(mercati_manuali_vivi(session))
    except Exception as e:  # noqa: BLE001 - mai fermare il finalize
        logger.warning("[finalize] rilascio mercati finiti KO: %s", str(e)[:160])


def chiudi_alla_uscita(session: Any) -> Dict[str, List[str]]:
    """28/09 (cantiere A, R-28-3 + "il finally del riavvio ordinato chiude i
    follow manuali"): cosa succede ai follow quando il processo del runner
    esce in modo ordinato (vita massima, riavvio per stallo, Ctrl+C, idle).

    * partite FINITE (il recorder ha visto la chiusura, anche se il
      finalize_worker non l'ha ancora drenata): finalizzate come sempre
      (CLOSED, live_now CLOSED, Replay se in registrazione);
    * partite NON finite (in corso o future): tornano ``PENDING``. Nessun
      processo le segue piu' (mai una riga STREAMING senza chi la segue) e il
      prossimo runner le riaggancia da solo (``list_pending_follows`` legge
      PENDING e STREAMING). PRIMA si finalizzavano tutte: CLOSED = partita
      dell'utente persa a ogni ricambio del processo, Replay caricato a meta'.

    Ritorna ``{"finalizzati": [...], "in_attesa": [...]}``."""
    finiti: List[str] = []
    rec = getattr(session, "recorder", None)
    if rec is not None:
        try:
            finiti = [str(e) for e in rec.drain_finished()]
        except Exception:  # noqa: BLE001
            finiti = []
    out: Dict[str, List[str]] = {"finalizzati": [], "in_attesa": []}
    for event_id in finiti:
        if event_id not in session.finished_events:
            _finalize_event(event_id, session)
            out["finalizzati"].append(event_id)
    fine = getattr(session, "fine_evento", None) or {}
    # anche le partite col catalogo vuoto in conferma o trattenute per soldi:
    # nessuno le streamma, la riga non puo' restare STREAMING
    in_fine = set(fine.get("vuoto_dal") or ()) | set(fine.get("trattenute") or ())
    for event_id in sorted(set(getattr(session, "cataloged_events", None) or ()) | in_fine):
        if event_id in session.finished_events:
            continue
        _safe_set_status(event_id, "PENDING")
        out["in_attesa"].append(event_id)
    if out["finalizzati"] or out["in_attesa"]:
        logger.info("[runner] uscita ordinata: %d partite finite chiuse, %d partite "
                    "ancora vive rimesse in attesa (il prossimo runner le riaggancia).",
                    len(out["finalizzati"]), len(out["in_attesa"]))
    return out


def _sync_record_events(session: Any, follows: List[Dict[str, Any]]) -> None:
    """Risincronizza il set di eventi in REGISTRAZIONE opt-in (colonna
    ``live_follow.record``) e lo propaga al tee raw (RAW_STATE).

    Chiamato ovunque il runner rilegga i follow (main loop + sub-worker): un
    click su "Segui live" A PARTITA IN CORSO entra nel set al giro successivo
    e il tee inizia a scrivere da quel momento.

    FALLBACK DIFENSIVO: se la colonna ``record`` non esiste ancora (migrazione
    live_follow_record.sql non applicata) le righe non hanno la chiave →
    gating DISATTIVATO (None = registra tutto, comportamento storico) con
    warning UNA volta — mai rompere il runner.
    """
    from .raw_listener import RAW_STATE

    if follows and not any("record" in f for f in follows):
        if not getattr(session, "_record_col_warned", False):
            session._record_col_warned = True
            logger.warning(
                "[runner] colonna live_follow.record ASSENTE (migrazione "
                "live_follow_record.sql non applicata): registro TUTTE le "
                "partite (comportamento storico).")
        session.record_events = None
        RAW_STATE.set_record_events(None)
        return
    rec = {str(f["event_id"]) for f in follows if f.get("record")}
    session.record_events = rec
    RAW_STATE.set_record_events(rec)


# ----------------------------------------------------------------------------
# Worker: auto-sottoscrizione nuove GIOCATA (F3)
# ----------------------------------------------------------------------------
def subscription_worker(context: dict, flumine: Flumine, session: LiveSession) -> None:
    rest: BetfairClient = context["rest"]
    # AGGANCIO RAPIDO (fix 17/07): il worker gira a cadenza fitta
    # (SUB_WORKER_POLL_SEC, ~2s) per il check dei nuovi follow — una SELECT
    # leggera su live_follow, ZERO chiamate Betfair. La parte PESANTE
    # (resolve_and_register: REST listEvents + matcher watchlist) resta alla
    # cadenza storica WATCHLIST_POLL_SEC, throttled qui dentro. Un errore REST
    # non blocca più il check follow (il click "Trading" scrive live_follow via
    # RPC: l'aggancio non deve dipendere dalla risoluzione watchlist).
    now = time.monotonic()
    last_resolve = getattr(session, "last_resolve_ts", 0.0)
    if last_resolve == 0.0 or (now - last_resolve) >= WATCHLIST_POLL_SEC:
        # timestamp consumato ANCHE su errore: mai martellare un REST rotto a 2s
        session.last_resolve_ts = now
        try:
            resolve_and_register(rest)
        except Exception as e:  # noqa: BLE001
            logger.warning("[sub-worker] resolve_and_register KO: %s", e)
    try:
        follows = db.list_pending_follows()
    except Exception as e:  # noqa: BLE001
        logger.warning("[sub-worker] list_pending_follows KO: %s", e)
        return
    # opt-in 17/07: risincronizza QUI il set degli eventi in registrazione —
    # e' il punto in cui il runner rilegge i follow periodicamente, quindi un
    # toggle "Segui live" a partita in corso diventa efficace al giro dopo.
    try:
        _sync_record_events(session, follows)
    except Exception as e:  # noqa: BLE001 - il gating non deve rompere il worker
        logger.warning("[sub-worker] sync record opt-in KO (ignorato): %s", e)
    # 28/09 (cantiere A): catalogo vuoto in conferma / trattenute per soldi
    try:
        _ricontrolla_fine(rest, session, follows)
    except Exception as e:  # noqa: BLE001 - mai fermare il worker
        logger.warning("[sub-worker] ricontrollo fine partita KO: %s", str(e)[:160])
    new_events = _nuovi_follow_manuali(follows, session, _auto_attivo())
    if not new_events:
        session.sub_restart_deferred_since = None
        return
    # 06/10: con l'auto-follow agganciato la partita seguita a mano entra A
    # CALDO, come quelle dei bot: niente ricostruzione, niente attesa del flat
    if _aggancio_a_caldo(rest, session, new_events, _auto_attivo(), now):
        session.sub_restart_deferred_since = None
        return
    # THROTTLE con BYPASS primo-aggancio (fix 17/07 "Trading = streaming
    # immediato"): MIN_RESUBSCRIBE_INTERVAL_SEC protegge dal CHURN (rebuild
    # ripetuti sugli stessi eventi), ma il PRIMO aggancio di un evento MAI
    # sottoscritto non deve pagarlo — l'utente ha appena cliccato Trading e
    # aspetta il ladder. Il bypass scatta SOLO se:
    #   1. tra i new_events c'è almeno un evento mai tentato prima
    #      (attach_attempted: un retry di un evento già tentato NON bypassa);
    #   2. l'ultimo rebuild (di qualunque tipo) è più vecchio del minimo
    #      ASSOLUTO FIRST_ATTACH_MIN_INTERVAL_SEC (anti-loop back-to-back);
    #   3. l'ultimo rebuild ottenuto COL bypass è più vecchio di
    #      MIN_RESUBSCRIBE_INTERVAL_SEC → UNA sola finestra "gratis" per
    #      intervallo: 3 nuovi eventi in 30s = 1 rebuild aggiuntivo (il primo),
    #      gli altri si accodano al giro normale del throttle.
    now = time.monotonic()
    gap = now - session.last_resubscribe_ts
    attempted = getattr(session, "attach_attempted", set())
    first_attach = any(f["event_id"] not in attempted for f in new_events)
    bypass = (
        first_attach
        and gap >= FIRST_ATTACH_MIN_INTERVAL_SEC
        and (now - getattr(session, "last_first_attach_bypass_ts", -1e9))
        >= MIN_RESUBSCRIBE_INTERVAL_SEC
    )
    if gap < MIN_RESUBSCRIBE_INTERVAL_SEC and not bypass:
        return
    # GUARDIA FLAT (fix 17/07, parità con il tennis di ieri): il rebuild
    # ricostruisce flumine con un blotter VUOTO — forzarlo con ordini vivi o
    # regole armate ORFANIZZEREBBE le posizioni live. Rinvia finché non si è
    # flat; se il rinvio persiste, alert CRITICAL visibile (grazia, mai forzare).
    blocker = _lifecycle_blockers(flumine)
    if blocker is not None:
        first = session.sub_restart_deferred_since
        if first is None:
            session.sub_restart_deferred_since = now
            session.sub_restart_defer_alert_interval = _SUB_RESTART_DEFER_ALERT_SEC
            logger.warning(
                "[sub-worker] %d nuove partite GIOCATA ma restart RINVIATO: %s.",
                len(new_events), blocker)
        elif (now - first) >= _SUB_RESTART_DEFER_ALERT_SEC and (
                now - session.sub_restart_defer_alert_ts) >= (
                session.sub_restart_defer_alert_interval
                or _SUB_RESTART_DEFER_ALERT_SEC):
            session.sub_restart_defer_alert_ts = now
            # backoff esponenziale (fix "alert fatigue"): il primo CRITICAL
            # arriva presto, i successivi si diradano (x2 fino a 1h) — un
            # blocco by-design (stop armato per ore) non inonda il pannello.
            session.sub_restart_defer_alert_interval = min(
                3600.0, (session.sub_restart_defer_alert_interval
                         or _SUB_RESTART_DEFER_ALERT_SEC) * 2.0)
            logger.critical(
                "[sub-worker] %d nuove partite in ATTESA da %.0f min: restart "
                "RINVIATO (%s) — gestisci l'esposizione per sbloccare l'aggancio.",
                len(new_events), (now - first) / 60.0, blocker)
            try:
                db.insert_alert(
                    "CRITICAL", "NEW_MATCHES",
                    f"{len(new_events)} nuove partite NON agganciate da "
                    f"{(now - first) / 60.0:.0f} min: restart della subscription "
                    f"RINVIATO ({blocker}). Chiudi/gestisci l'esposizione per "
                    "sbloccare l'aggancio.")
            except Exception as e:  # noqa: BLE001 - alert best-effort
                logger.warning("[sub-worker] insert_alert KO (ignorato): %s", e)
        return
    prior_deferred_since = session.sub_restart_deferred_since
    session.sub_restart_deferred_since = None
    logger.info("[sub-worker] %d nuove partite GIOCATA → ricostruzione subscription.", len(new_events))
    try:
        db.insert_alert("INFO", "NEW_MATCHES", f"{len(new_events)} nuove partite agganciate al live.")
    except Exception as e:  # noqa: BLE001 - un errore di alert NON deve bloccare la ri-subscription
        logger.warning("[sub-worker] insert_alert KO (ignorato): %s", e)
    deferred = _request_soft_restart(
        flumine, session, f"F3: {len(new_events)} nuove partite GIOCATA")
    if deferred is not None:
        # TOCTOU: un ordine è comparso tra il check sopra e lo stop → rinvio.
        # La durata di rinvio GIÀ accumulata va preservata (review 17/07):
        # azzerarla a `now` ritarderebbe l'alert CRITICAL di altri 5 minuti
        # in un blocco persistente che ha solo "respirato" per un ciclo.
        session.sub_restart_deferred_since = prior_deferred_since or now
        logger.warning("[sub-worker] restart RINVIATO all'ultimo check: %s.", deferred)
        return
    session.last_resubscribe_ts = now
    # bookkeeping del bypass primo-aggancio (fix 17/07): gli eventi appena
    # richiesti non sono più "mai visti" (un loro retry NON bypasserà più il
    # throttle); se questo rebuild è passato GRAZIE al bypass (gap sotto il
    # throttle standard), consuma la finestra "gratis" → il prossimo bypass
    # potrà scattare solo dopo MIN_RESUBSCRIBE_INTERVAL_SEC (anti-churn).
    if getattr(session, "attach_attempted", None) is not None:
        session.attach_attempted.update(f["event_id"] for f in new_events)
    if gap < MIN_RESUBSCRIBE_INTERVAL_SEC:
        session.last_first_attach_bypass_ts = now


def _aggancio_a_caldo(rest: Any, session: Any, new_events: List[Dict[str, Any]],
                      auto: Optional[Any], now: float) -> bool:
    """06/10 (Segui Live fermo su "Aggancio stream"): una partita seguita A MANO
    entra nello stream SENZA ricostruire il framework, con la stessa
    risottoscrizione a caldo dell'auto-follow (``PianoFollow``: manuali +
    automatiche sulla stessa connessione; blotter, posizioni e ordini intatti).
    Prima ogni partita nuova chiedeva il restart della subscription, rinviato
    finche' il runner non era flat: con i bot al lavoro non arrivava mai.

    Il catalogo (REST ``listMarketCatalogue``) di una stessa partita si ritenta
    al piu' ogni ``MIN_RESUBSCRIBE_INTERVAL_SEC`` (mercati non ancora
    pubblicati, tetto pieno): il worker gira ogni 2 s. False = auto-follow
    assente o non agganciato a un framework: resta la ricostruzione di sempre."""
    if auto is None:
        return False
    try:
        if not auto.agganciato():
            return False
    except Exception:  # noqa: BLE001 - versione senza il metodo: strada di sempre
        return False
    tentati = getattr(session, "catalogo_a_caldo_ts", None)
    if tentati is None:
        tentati = {}
        session.catalogo_a_caldo_ts = tentati
    da_fare = [f for f in new_events
               if now - tentati.get(f["event_id"], -1e9) >= MIN_RESUBSCRIBE_INTERVAL_SEC]
    if not da_fare:
        return True
    for f in da_fare:
        tentati[f["event_id"]] = now
    prima = set(session.cataloged_events)
    _catalog_events(rest, session, da_fare)
    nuovi = sorted(set(session.cataloged_events) - prima)
    if nuovi:
        auto.imposta_manuali(mercati_manuali_vivi(session))
        auto.sveglia()
        logger.info("[sub-worker] %d partite seguite a mano agganciate A CALDO (nessuna "
                    "ricostruzione): %s", len(nuovi), ", ".join(nuovi))
        try:
            db.insert_alert("INFO", "NEW_MATCHES",
                            f"{len(nuovi)} nuove partite agganciate al live (a caldo).")
        except Exception as e:  # noqa: BLE001 - alert best-effort
            logger.warning("[sub-worker] insert_alert KO (ignorato): %s", e)
    return True


def _nuovi_follow_manuali(follows: List[Dict[str, Any]], session: Any,
                          auto: Optional[Any]) -> List[Dict[str, Any]]:
    """I follow da agganciare con la ricostruzione di sempre. 25/09: una riga
    STREAMING di un evento che l'AUTO-FOLLOW segue gia' (scritta da lui,
    ``origine='auto'``) e' gia' nello stream a caldo: niente ricostruzione, che
    col blotter vuoto azzererebbe le posizioni. Un clic dell'utente la porta a
    PENDING e torna un follow manuale come sempre."""
    out = []
    fine = getattr(session, "fine_evento", None) or {}
    in_fine = set(fine.get("vuoto_dal") or ()) | set(fine.get("trattenute") or ())
    for f in follows:
        ev = f["event_id"]
        if ev in session.cataloged_events or ev in session.finished_events:
            continue
        if ev in in_fine:
            # 28/09 (cantiere A): catalogo vuoto in conferma o trattenuta per
            # soldi: la rilegge ``_ricontrolla_fine`` senza ricostruire lo stream
            continue
        if (auto is not None and str(f.get("status") or "") == "STREAMING"
                and auto.segue_auto(ev)):
            continue
        out.append(f)
    return out


# throttle dell'alert CRITICAL quando il restart F3 resta rinviato (fix 17/07)
_SUB_RESTART_DEFER_ALERT_SEC = float(
    os.getenv("LIVE_SUB_RESTART_DEFER_ALERT_SEC", "300"))


def _request_soft_restart(flumine: Flumine, session: LiveSession, reason: str) -> Optional[str]:
    """Richiede un restart SOFT della subscription (rebuild del framework).

    * RE-VERIFICA i blocker IMMEDIATAMENTE prima dello stop (fix TOCTOU 17/07):
      tra il check del chiamante e ``_stop_framework`` il live_order_worker
      (stesso processo, thread flumine) può piazzare un ordine. Il doppio check
      riduce la finestra ai pochi ms tra quest'ultima verifica e l'accodamento
      del TerminationEvent: un lock condiviso col percorso di piazzamento
      richiederebbe di toccare live_order_worker (fuori perimetro) — finestra
      residua DICHIARATA e accettata.
    * Scrive il marker ``resubscribe`` nel sidecar .recmeta.jsonl (fix 17/07):
      i restart soft ora lasciano traccia per la validazione delle registrazioni.

    Ritorna il blocker (str) se il restart è stato RINVIATO, None se richiesto.
    """
    # check FINALE pre-stop: SEMPRE fresco (mai fidarsi della cache qui)
    blocker = _lifecycle_blockers(flumine, fresh=True)
    if blocker is not None:
        return blocker
    try:
        from .raw_listener import RAW_STATE

        RAW_STATE.mark_resubscribe(reason)
    except Exception as e:  # noqa: BLE001 - il marker è best-effort
        logger.debug("[runner] marker resubscribe KO (ignorato): %s", e)
    session.restart_requested.set()
    _stop_framework(flumine)
    return None


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


# Cache del verdetto "regole armate" (review 17/07, carico DB): col worker a 2s
# la SELECT su betfair_live_risk_rules girava a ogni tick per TUTTA la durata di
# un rinvio (che per design può durare ore). Si cachea SOLO l'esito BLOCCATO
# (direzione sicura: lo sblocco può ritardare di ≤TTL, un blocco appena armato
# non può MAI sfuggire perché l'esito "libero" viene SEMPRE ri-verificato).
_RISK_RULES_BLOCKED_UNTIL = 0.0
_RISK_RULES_CACHE_TTL_S = float(os.getenv("LIVE_RISK_RULES_CHECK_TTL_SEC", "15"))


def _lifecycle_blockers(flumine: Flumine, fresh: bool = False) -> Optional[str]:
    """Motivo per cui NON è sicuro spegnersi (None = via libera). Il denaro viene PRIMA
    del comfort: ordini VIVI nel blotter o regole risk armate/innescate (stop, offset,
    chase, stop-entry) = il runner resta acceso — spegnerlo lascerebbe protezioni morte
    e ordini non gestiti. In dubbio (blotter/DB illeggibili) si resta ACCESI.

    ``fresh=True`` (check finale pre-stop): ignora la cache del verdetto bloccato."""
    global _RISK_RULES_BLOCKED_UNTIL
    try:
        for market in flumine.markets:
            blotter = getattr(market, "blotter", None)
            live = list(getattr(blotter, "live_orders", None) or []) if blotter is not None else []
            if live:
                return f"{len(live)} ordini vivi sul mercato {getattr(market, 'market_id', '?')}"
    except Exception:  # noqa: BLE001
        return "blotter non leggibile (prudenza: resto acceso)"
    if LIVE_ORDER_MODE.strip().upper() in ("PAPER", "LIVE"):
        if not fresh and time.monotonic() < _RISK_RULES_BLOCKED_UNTIL:
            return "regole di rischio armate/innescate (verdetto in cache ≤15s)"
        try:
            from db_client import get_supabase_client
            rows = (get_supabase_client().table("betfair_live_risk_rules").select("id")
                    .in_("status", ["armed", "triggered"])
                    .eq("mode", LIVE_ORDER_MODE.strip().lower())
                    .limit(1).execute().data or [])
            if rows:
                _RISK_RULES_BLOCKED_UNTIL = time.monotonic() + _RISK_RULES_CACHE_TTL_S
                return "regole di rischio armate/innescate (stop/offset/chase/stop-entry)"
            _RISK_RULES_BLOCKED_UNTIL = 0.0
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
# hard-cap del silenzio dati PURO (review 17/07): oltre, il restart scatta
# anche con heartbeat freschi (heartbeat = socket vivo, non subscription sana).
# 30 min > qualunque quiete legittima (metà tempo ~15-20 min). 0 = disattivo.
_RAW_STALL_HARD_CAP_SEC = float(
    os.getenv("LIVE_RAW_STALL_HARD_CAP_SEC", "1800")) or None
# keepAlive sessione Betfair ANCHE durante lo streaming (fix 16/07): prima era
# rinnovata SOLO nel loop idle → dopo ore di stream una RICONNESSIONE (drop di
# rete, restart F3) usava un token scaduto e lo stream restava muto per sempre.
_STREAM_KEEPALIVE_SEC = float(os.getenv("LIVE_STREAM_KEEPALIVE_SEC", "480"))
_STREAM_KA_LAST = 0.0
# R-STREAM-1 (26/09): dopo una ricostruzione chiesta per STALLO, se i dati
# restano fermi per questa finestra (il 26/09: 89 ladder in 8 min, poi niente)
# si esce con EXIT_PLANNED_RESTART e il watchdog rilancia un processo nuovo.
# Osservazione: oltre, la ricostruzione e' considerata riuscita. 0 = spento.
_STALL_POST_REBUILD_SEC = float(os.getenv("LIVE_STALL_POST_REBUILD_SEC", "180"))
_STALL_POST_REBUILD_OSSERVA_SEC = float(
    os.getenv("LIVE_STALL_POST_REBUILD_OBSERVE_SEC", "900"))
# alert CRITICAL dell'escalation RINVIATA (ordini vivi/regole armate): al piu'
# uno ogni 5 minuti, il tentativo si ripete a ogni giro del battito.
_STALL_ESCALA_ALERT_SEC = 300.0


_ATTESA_RETE_SEC = 15.0


def _attendi_se_rete(dove: str, exc: BaseException) -> None:
    """26/09 (crash exit 1): un guasto di RETE nel ciclo principale (SELECT dei
    follow, catalogo REST) non deve uccidere il processo -- e con lui ogni
    follow chiuso nel ``finally`` e il budget di 5 riavvii/ora del watchdog.
    Guasto di rete: avviso, attesa, nuovo giro. Altro: si RILANCIA (un errore
    di programmazione non si maschera)."""
    if not e_errore_di_rete(exc):
        raise exc
    logger.warning("[runner] %s KO per RETE (%s): riprovo tra %.0fs, il processo "
                   "resta vivo.", dove, str(exc)[:160], _ATTESA_RETE_SEC)
    time.sleep(_ATTESA_RETE_SEC)


def _mercati_sottoscritti(session: Any) -> int:
    """Mercati della subscription corrente (R-STREAM-1, 26/09).

    Prima il controllo di stallo guardava solo ``market_to_event`` (i follow
    MANUALI): con i soli mercati dell'auto-follow (26/09: 0 manuali, 32
    partite seguite) la mappa era vuota e lo stallo non veniva MAI misurato
    -> 4 ore di runner cieco. ``stream_market_count`` e' fissato all'avvio di
    ogni ``framework.run()`` con tutti i mercati sottoscritti."""
    manuali = len(getattr(session, "market_to_event", None) or {})
    return max(manuali, int(getattr(session, "stream_market_count", 0) or 0))


def _escalation_stallo(flumine: Any, session: Any, stall_s: Optional[float],
                       dati_dopo_rebuild: bool, now_mono: float) -> bool:
    """Dopo una ricostruzione per stallo: attende, chiude l'osservazione o
    ESCALA a un processo nuovo (R-STREAM-1, 26/09: la ricostruzione nello
    stesso processo non ha ridato dati).

    Ritorna True finche' c'e' una ricostruzione in osservazione (il ciclo
    normale di ricostruzione non riparte nel frattempo). L'uscita passa dalla
    stessa guardia MONEY-CRITICAL dell'auto-spegnimento (``_lifecycle_blockers``:
    mai con ordini vivi o regole armate): se bloccata, alert CRITICAL (al piu'
    ogni 5 min) e nuovo tentativo al prossimo giro. Solo con il watchdog
    (``LIVE_RUNNER_KEEP_ALIVE=1``, app desktop): senza, un'uscita lascerebbe il
    runner morto e resta il ciclo di ricostruzione di prima.

    ``dati_dopo_rebuild``: ``configure_raw`` azzera i battiti a ogni
    ricostruzione, quindi un battito > 0 = almeno un dato DOPO di essa."""
    t0 = getattr(session, "stallo_rebuild_mono", None)
    if t0 is None:
        return False
    if getattr(session, "riavvio_per_stallo", False):
        return True  # uscita gia' chiesta: niente altro
    verdetto = verdetto_post_ricostruzione(
        stall_s, dati_dopo_rebuild, now_mono - t0, _STALL_POST_REBUILD_SEC,
        _STALL_POST_REBUILD_OSSERVA_SEC)
    if verdetto == VERDETTO_ATTENDI:
        return True
    if verdetto == VERDETTO_GUARITO:
        session.stallo_rebuild_mono = None
        logger.info("[runner] ricostruzione per stallo riuscita: dati di nuovo vivi.")
        return False
    if os.getenv("LIVE_RUNNER_KEEP_ALIVE", "").strip() != "1":
        session.stallo_rebuild_mono = None
        logger.critical(
            "[runner] stream fermo da %.0fs anche dopo la ricostruzione: senza watchdog "
            "(LIVE_RUNNER_KEEP_ALIVE) il processo NON esce, resta il ciclo di "
            "ricostruzione.", stall_s or 0.0)
        return False
    blocker = _lifecycle_blockers(flumine)
    if blocker is None:
        try:
            db.insert_alert(
                "CRITICAL", "RAW_RECORDER",
                f"stream mercati ancora MUTO {stall_s or 0:.0f}s dopo la "
                "ricostruzione: riavvio del processo runner (il watchdog lo rilancia).")
        except Exception:  # noqa: BLE001 - l'alert non blocca il riavvio
            pass
        # check FINALE fresco subito prima dello stop (stessa lezione TOCTOU 17/07)
        blocker = _lifecycle_blockers(flumine, fresh=True)
    if blocker is not None:
        if (now_mono - float(getattr(session, "stallo_escala_alert_mono", -1e9))
                >= _STALL_ESCALA_ALERT_SEC):
            session.stallo_escala_alert_mono = now_mono
            logger.critical("[runner] riavvio per stream muto RINVIATO: %s.", blocker)
            try:
                db.insert_alert(
                    "CRITICAL", "RAW_RECORDER",
                    f"stream mercati MUTO anche dopo la ricostruzione ma riavvio del "
                    f"processo RINVIATO ({blocker}): gestisci l'esposizione a mano.")
            except Exception:  # noqa: BLE001
                pass
        return True
    logger.critical("[runner] stream MUTO dopo la ricostruzione: esco con %d, il "
                    "watchdog rilancia un processo nuovo.", EXIT_PLANNED_RESTART)
    session.riavvio_per_stallo = True
    session.planned_restart = True
    session.shutdown_requested.set()
    _stop_framework(flumine)
    return True




def _custode_sessione(session: Any) -> Any:
    """Il custode della sessione Betfair del runner (uno per processo, FIX-C 26/09)."""
    c = getattr(session, "_custode_sessione", None)
    if c is None:
        from .auth import CustodeSessione
        c = CustodeSessione(session.context_api_client, periodo_s=_STREAM_KEEPALIVE_SEC)
        session._custode_sessione = c
    return c


def _dopo_relogin(session: Any, flumine: Any) -> None:
    """Sessione Betfair RIFATTA dal custode: lo stream flumine ha una sessione
    propria -> alert + ricostruzione della subscription (stesso path del recovery
    da stallo, con le stesse guardie money-critical)."""
    logger.critical("[runner] sessione Betfair RIFATTA dal custode: ricostruisco la subscription")
    try:
        db.insert_alert("CRITICAL", "SESSIONE_BETFAIR",
                        "sessione Betfair rifatta dal custode (keepAlive KO/NO_SESSION): "
                        "ricostruisco la subscription dello stream")
    except Exception:  # noqa: BLE001
        pass
    try:
        late = _request_soft_restart(flumine, session, "relogin sessione Betfair (custode)")
        if late is not None:
            logger.critical("[runner] ricostruzione dopo relogin RINVIATA: %s", late)
    except Exception as ex:  # noqa: BLE001
        logger.error("[runner] ricostruzione dopo relogin KO: %s", str(ex)[:160])

def _partite_in_streaming(session: Any) -> Optional[int]:
    """Quante partite il runner sta seguendo ADESSO, dalla SUA memoria.

    25/09 (punto 6 dell'audit tempo reale): e' il numero ``streaming`` del
    battito sul canale. Nessuna lettura DB: gli eventi catalogati (follow
    manuali portati a STREAMING da ``_catalog_event``) meno quelli finalizzati,
    piu' gli eventi dell'AUTO-FOLLOW (righe ``origine='auto'`` STREAMING).
    ``None`` se non contabile (strutture cambiate sotto mano): mai un numero
    inventato."""
    try:
        eventi = set(getattr(session, "cataloged_events", None) or ()) - set(
            getattr(session, "finished_events", None) or ())
        auto = _auto_attivo()
        if auto is not None:
            for voce in auto.piano.voci().values():
                if voce.event_id:
                    eventi.add(str(voce.event_id))
        return len(eventi)
    except Exception:  # noqa: BLE001 - conteggio best-effort, mai fermare il battito
        return None


def _pubblica_battito(session: Any) -> None:
    """25/09 (punto 6) - il battito del runner anche sul canale 47331, topic
    ``battito`` ``{ts, mode, streaming}`` (``canale_bot.battito_runner``).

    Esce DOVE si scrive ``betfair_live_heartbeat`` (worker e attesa), con lo
    stesso ``mode``; prima di questo la UI deduceva il battito dal saldo (~20 s).
    Senza canale non esce niente; non solleva mai (``pubblica_stato_processo``)."""
    try:
        _cb.pubblica_stato_processo(
            _cb.TOPIC["battito"],
            _cb.battito_runner(heartbeat_mode(), _partite_in_streaming(session)))
    except Exception as ex:  # noqa: BLE001 - mostrare non ferma mai il runner
        logger.debug("[runner] battito sul canale KO: %s", str(ex)[:120])


def _ordini_vivi_nel_blotter(flumine: Any) -> Optional[str]:
    """Gli ordini VIVI nel blotter del runner (sola memoria, nessuna lettura DB):
    cio' che a stream muto non ha piu' prezzi nuovi su cui essere gestito."""
    try:
        parti = []
        for market in list(getattr(flumine, "markets", None) or []):
            blotter = getattr(market, "blotter", None)
            live = list(getattr(blotter, "live_orders", None) or []) if blotter is not None else []
            if live:
                parti.append(f"{len(live)} ordini vivi su {getattr(market, 'market_id', '?')}")
        return "; ".join(parti[:5]) or None
    except Exception:  # noqa: BLE001 - dichiarazione best-effort
        return "blotter non leggibile"


def _sorveglia_flusso_runner(session: Any, flumine: Any,
                             adesso_s: Optional[float] = None,
                             adesso_mono: Optional[float] = None) -> Dict[str, Any]:
    """CANTIERE J2 (28/09) - lo stream di mercato del runner calcio e' vivo?

    Misura: il battito PER CONNESSIONE che ``frammenti_mercato.FrammentoListener``
    gia' tiene (``ultimo_msg_mono``, heartbeat compresi): nessuna seconda misura.
    Una volta per episodio: ``live_alerts`` CRITICAL (con gli ordini vivi che
    restano senza prezzi nuovi) e INFO al rientro. La dichiarazione resta in
    ``session.flusso_runner`` (la leggono la riserva dei prezzi e il canale) ed
    esce sul canale 47331, topic ``flusso_stream``, a ogni battito. Mai solleva."""
    ora = time.time() if adesso_s is None else float(adesso_s)
    sorv = getattr(session, "flusso_sorveglia", None)
    if sorv is None:
        sorv = _SM.SorvegliaStream()
        try:
            session.flusso_sorveglia = sorv
        except Exception:  # noqa: BLE001
            pass
    try:
        st = _SM.stato_stream(flumine, adesso_mono=adesso_mono)
        posizione = (_ordini_vivi_nel_blotter(flumine)
                     if st.get("vivo") is False and not sorv.interrotto else None)
        avviso = sorv.osserva(st, ora, posizione)
    except Exception as ex:  # noqa: BLE001 - la misura non ferma mai il runner
        logger.debug("[runner] sorveglianza flusso KO: %s", str(ex)[:120])
        return sorv.dichiarazione(ora)
    if avviso:
        if avviso["level"] == "CRITICAL":
            logger.critical("[runner] %s", avviso["message"])
        else:
            logger.info("[runner] %s", avviso["message"])
        try:
            db.insert_alert(avviso["level"], "RUNNER_" + avviso["code"],
                            "runner calcio: " + avviso["message"])
        except Exception:  # noqa: BLE001 - alert best-effort
            pass
    dich = sorv.dichiarazione(ora)
    try:
        session.flusso_runner = dich
    except Exception:  # noqa: BLE001
        pass
    # blocco 3 (cantiere J2): la RISERVA dei prezzi sa quali mercati hanno lo
    # stream muto (``live_order_worker._best_prices`` e le regole di rischio)
    _RP.imposta_stato(dich)
    if st.get("vivo") is None and not sorv.interrotto:
        return dich                     # nessuno stream di mercato: niente da dire
    try:
        _cb.pubblica_stato_processo(_cb.TOPIC["flusso_stream"],
                                    _SM.messaggio_canale(dich, ora * 1000.0))
    except Exception as ex:  # noqa: BLE001 - mostrare non ferma mai il runner
        logger.debug("[runner] flusso sul canale KO: %s", str(ex)[:120])
    return dich


def _battito_in_attesa(session: Any, adesso: float) -> None:
    """Il battito del runner PARCHEGGIATO in attesa di eventi (14/09): stessa
    cadenza di ``heartbeat_worker`` (``HEARTBEAT_SEC``), sul DB come prima e, dal
    25/09 (punto 6), anche sul canale. Estratto dal ciclo di attesa senza
    cambiarne la logica, per poterlo provare."""
    if (adesso - getattr(session, "_idle_hb_ts", -1e9)) >= float(HEARTBEAT_SEC or 10.0):
        session._idle_hb_ts = adesso
        try:
            db.upsert_live_heartbeat(runner=True, pid=os.getpid(), mode=heartbeat_mode())
        except Exception as _hb:  # noqa: BLE001 - best-effort come nel worker
            logger.debug("[runner] heartbeat idle KO: %s", str(_hb)[:120])
        # 25/09 (punto 6): stesso battito sul canale (in attesa)
        _pubblica_battito(session)


# 09/10 (programma del giorno, contratto par. 4): un comando del desktop arrivato
# sul 47331 a runner PARCHEGGIATO e SENZA motore ordini (che altrimenti lo
# serve lui, con l'aggancio al volo) non ha nessuno che lo drena: prima restava
# in RAM senza risposta (la pagina andava in timeout a 10 s) e partiva quando il
# framework nasceva, minuti dopo. Adesso riceve SUBITO il rifiuto col motivo.
_MOTIVO_PARCHEGGIATO_SENZA_MOTORE = (
    "runner calcio parcheggiato (nessuna partita agganciata) e senza motore ordini "
    "attivo: aggancio al volo non disponibile, comando NON eseguito. Apri la partita "
    "(Trading) e riprova")


def _rispondi_comandi_locali_da_parcheggiato() -> int:
    """09/10: drena la coda ``/order``/``snapshot`` del canale e risponde a ogni
    richiesta ``ok=False`` col motivo (stessa disciplina di B-1: nessun comando
    resta in RAM per partire dopo). Solo SENZA motore ordini. Ritorna quante."""
    ch = _lc.get_channel()
    if ch is None:
        return 0
    gestite = 0
    while True:
        reqs = ch.pop_requests()
        if not reqs:
            break
        for req in reqs:
            gestite += 1
            ch.respond(req, False, error=_MOTIVO_PARCHEGGIATO_SENZA_MOTORE)
    if gestite:
        logger.warning("[runner] %d comandi del desktop rifiutati a runner parcheggiato "
                       "senza motore ordini", gestite)
    return gestite


def _attesa_board_e_canale(session: Any) -> None:
    """09/10 - il runner PARCHEGGIATO (ciclo d'attesa, framework non ancora
    nato) pubblica il BOARD come il ``board_worker`` del framework (stessa
    funzione, stessa cadenza ``BOARD_POLL_SEC``, stesso stato; zero costo senza
    desktop) e, senza motore ordini, risponde ai comandi del canale. Mai solleva."""
    _board_da_parcheggiato(session, "1", BOARD_POLL_SEC or 10.0)
    if _motore_attivo() is None:
        try:
            _rispondi_comandi_locali_da_parcheggiato()
        except Exception as ex:  # noqa: BLE001 - il ciclo d'attesa non cade mai
            logger.warning("[runner] risposta ai comandi da parcheggiato KO: %s", str(ex)[:160])


def heartbeat_worker(context: dict, flumine: Flumine, session: LiveSession) -> None:  # noqa: ARG001
    """A5 — battito del runner → betfair_live_heartbeat (singleton, realtime).

    La UI mostra "runner vivo Xs fa" in top bar; oltre soglia il chip diventa
    rosso (runner giù/appeso). Best-effort: un DB momentaneamente KO non deve
    mai far cadere il runner (il prossimo battito riallinea)."""
    try:
        db.upsert_live_heartbeat(runner=True, pid=os.getpid(), mode=heartbeat_mode())
    except Exception as ex:  # noqa: BLE001 - heartbeat best-effort
        logger.debug("[runner] heartbeat KO: %s", str(ex)[:120])
    # 25/09 (punto 6): lo stesso battito sul canale locale (anche se il DB e' KO:
    # il processo e' vivo comunque, ed e' questo che il battito dice)
    _pubblica_battito(session)
    # 28/09 (cantiere J2): lo stream di mercato del runner e' vivo? (alert una
    # volta per episodio, dichiarazione sul canale e nella sessione)
    _sorveglia_flusso_runner(session, flumine)
    # keepAlive periodico della sessione Betfair mentre si streamma (fix 16/07,
    # vedi _STREAM_KEEPALIVE_SEC): best-effort, mai far cadere il runner.
    # 26/09 (FIX-C, causa della cecita' delle 10:41Z): il keepAlive che ingoiava
    # l'errore lasciava scadere la sessione .it per sempre (NO_SESSION su REST e
    # stream). Ora il CUSTODE ritenta con backoff e rifa' il login su NO_SESSION o
    # al 90 % della vita della sessione; su «relogin» lo stream va ricostruito.
    now_mono = time.monotonic()
    if _STREAM_KEEPALIVE_SEC > 0:
        try:
            esito = _custode_sessione(session).tick(now_mono)
        except Exception as ex:  # noqa: BLE001 - mai far cadere il runner
            esito = None
            logger.warning("[runner] custode sessione KO: %s", str(ex)[:120])
        if esito == "relogin":
            _dopo_relogin(session, flumine)
    # RECORDER VIVO (fix 11/07, lezione 10/07: tee nativo morto in silenzio =
    # in-play irrecuperabile): se il tee e' abilitato, ci sono mercati
    # sottoscritti ma NESSUN write raw da >120s → alert WARN (una volta,
    # si riarma quando il flusso riprende). write_errors incluso.
    try:
        from .raw_listener import RAW_STATE

        global _RAW_STALL_ALERTED, _RAW_STALL_LAST_RESTART
        h = RAW_STATE.health()
        # R-STREAM-1 (26/09): lo stallo si misura SEMPRE quando ci sono mercati
        # sottoscritti (manuali O dell'auto-follow), a tee raw acceso o spento:
        # il vecchio cancello `enabled and market_to_event` ha tenuto il runner
        # cieco 4 ore (solo mercati auto-follow, mappa manuali vuota).
        if _mercati_sottoscritti(session) > 0:
            # OPT-IN 17/07: con la registrazione a scelta la maggior parte delle
            # partite NON scrive raw → lo stallo si misura sull'ULTIMO DATO
            # visto dallo stream (last_data_ms, aggiornato anche per gli eventi
            # non registrati), oltre che sugli write raw effettivi. Senza
            # questo, uno stream sano con zero partite in registrazione
            # sembrerebbe muto e il runner si auto-infliggerebbe restart.
            last_vals = list(h.get("last_write_ms", {}).values() or [])
            last_vals.append(float(h.get("last_data_ms") or 0))
            last = max(last_vals)
            now_ms = time.time() * 1000.0
            started = getattr(session, "stream_started_monotonic", None)
            age_s = (now_mono - started) if started is not None else None
            # last==0 = MAI scritto in questa vita del processo (il caso 16/07:
            # stream mai connesso dopo il rebuild) → conta dall'avvio dello stream.
            data_stall_s = raw_stall_seconds(last, now_ms, age_s)
            # HEARTBEAT DI CONNESSIONE (fix 17/07): Betfair manda ct=HEARTBEAT
            # ogni 0.5-5s quando non c'è traffico → heartbeat freschi + dati
            # fermi = mercato QUIETO (metà tempo), NIENTE alert/restart. Lo
            # stallo effettivo supera la soglia solo se ENTRAMBI sono vecchi
            # (connessione morta davvero). Heartbeat mai visti (0) → età stream.
            hb_stall_s = raw_stall_seconds(
                float(h.get("last_heartbeat_ms") or 0), now_ms, age_s)
            # Hard-cap indipendente (review 17/07): oltre questo silenzio dati
            # puro si riparte COMUNQUE, anche con heartbeat freschi — gli
            # heartbeat provano il socket, non la salute della subscription.
            stall_s = effective_stall_seconds(
                data_stall_s, hb_stall_s, _RAW_STALL_HARD_CAP_SEC)
            stalled = stall_s is not None and stall_s > 120.0
            # TEE ROTTO SU EVENTO SCELTO (review 17/07, MEDIUM): col gating
            # opt-in `last_data_ms` (globale) domina il max — se il tee
            # dell'UNICO evento in registrazione si rompe mentre gli altri
            # match streamano, lo stallo globale non scatta mai. Check
            # dedicato: evento in record_events senza write da >120s con
            # stream sano = il dato che l'utente ha SCELTO di conservare
            # sta andando perso — alert esplicito.
            rec_events = getattr(session, "record_events", None) or set()
            rec_stalled = []
            if rec_events and not stalled:
                writes = h.get("last_write_ms", {}) or {}
                for _ev in rec_events:
                    w = float(writes.get(_ev) or 0)
                    if w <= 0:
                        continue  # mai scritto (toggle appena acceso): niente
                        # falso allarme sull'età dello stream — si valuta dal
                        # primo write in poi.
                    w_stall = raw_stall_seconds(w, now_ms, age_s)
                    if w_stall is not None and w_stall > 120.0:
                        rec_stalled.append((_ev, w_stall))
            if stalled and not _RAW_STALL_ALERTED:
                _RAW_STALL_ALERTED = True
                db.insert_alert(
                    "WARN", "RAW_RECORDER",
                    f"tee raw NATIVO fermo da {stall_s:.0f}s "
                    f"con stream attivo (write_errors={h.get('write_errors')}) "
                    "— i backtest/Atlante perderebbero questi dati",
                )
            elif rec_stalled and not _RAW_STALL_ALERTED:
                _RAW_STALL_ALERTED = True
                _ev, _st = rec_stalled[0]
                db.insert_alert(
                    "WARN", "RAW_RECORDER",
                    f"REGISTRAZIONE FERMA sull'evento {_ev} da {_st:.0f}s "
                    f"(stream generale SANO, write_errors={h.get('write_errors')}) "
                    "— la partita scelta con Segui live sta perdendo dati",
                )
            elif not stalled and not rec_stalled:
                _RAW_STALL_ALERTED = False
            # ESCALATION (fix 16/07): stallo PERSISTENTE → CRITICAL + ricostruzione
            # della subscription (throttled). L'alert WARN da solo non recupera
            # nulla: il 16/07 lo stream e' rimasto muto per ore con runner vivo.
            # R-STREAM-1 (26/09): una ricostruzione per stallo gia' chiesta e' in
            # osservazione -> niente seconda ricostruzione; se non ridarà dati si
            # esce e il watchdog rilancia un processo nuovo.
            in_osservazione = (not session.shutdown_requested.is_set()
                               and _escalation_stallo(flumine, session,
                                                      stall_s, last > 0, now_mono))
            if (not session.shutdown_requested.is_set()
                    and not in_osservazione
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
                        stall_s, _mercati_sottoscritti(session))
                    try:
                        db.insert_alert(
                            "CRITICAL", "RAW_RECORDER",
                            f"stream mercati MUTO da {stall_s:.0f}s: registrazione "
                            "interrotta, ricostruisco la subscription (auto-recovery).")
                    except Exception:  # noqa: BLE001 - l'alert non blocca il recovery
                        pass
                    # fix TOCTOU 17/07: _request_soft_restart RI-VERIFICA i
                    # blocker subito prima dello stop (l'insert_alert sopra può
                    # durare centinaia di ms: tempo per un place concorrente) e
                    # scrive il marker resubscribe nel .recmeta.jsonl.
                    late_blocker = _request_soft_restart(
                        flumine, session,
                        f"stall-recovery: stream muto {stall_s:.0f}s")
                    if late_blocker is None:
                        # R-STREAM-1 (26/09): la ricostruzione va in osservazione;
                        # se non ridà dati, _escalation_stallo passa al processo nuovo
                        session.stallo_rebuild_mono = now_mono
                    if late_blocker is not None:
                        logger.critical(
                            "[runner] recovery RINVIATO all'ultimo check: %s.",
                            late_blocker)
                        try:
                            db.insert_alert(
                                "CRITICAL", "RAW_RECORDER",
                                f"recovery RINVIATO all'ultimo check ({late_blocker}): "
                                "esposizione comparsa durante la verifica.")
                        except Exception:  # noqa: BLE001
                            pass
    except Exception:  # noqa: BLE001 - telemetria best-effort
        pass


def arresto_worker(context: dict, flumine: Any, session: Any) -> None:  # noqa: ARG001
    """28/09 (cantiere A): l'app chiede lo spegnimento ORDINATO (file di
    ``arresto_ordinato``) -> il framework si ferma, ``setup_and_run`` esce dal
    ciclo col ``finally`` (follow: finite CLOSED, vive PENDING, righe
    automatiche CLOSED) ed exit 0 (il watchdog non rilancia). Nessuna guardia
    sugli ordini: l'app sta chiudendo comunque, e un'uscita ordinata e' meglio
    del taskkill che arriva dopo."""
    if session.shutdown_requested.is_set() or not _AO.richiesto():
        return
    logger.warning("[runner] ARRESTO ORDINATO richiesto dall'app: fermo lo stream.")
    session.planned_restart = False
    session.shutdown_requested.set()
    _stop_framework(flumine)


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
    keep_alive_desktop = os.getenv("LIVE_RUNNER_KEEP_ALIVE", "").strip() == "1"
    if uptime_exceeded(session.started_monotonic, time.monotonic(), _RUNNER_MAX_HOURS):
        reason = f"vita massima {_RUNNER_MAX_HOURS:.0f}h raggiunta"
        # app desktop: NON è una fine voluta ma un ricambio del processo → exit
        # code dedicato (EXIT_PLANNED_RESTART) così il watchdog riavvia subito
        # invece di fermarsi per sempre (audit 09/09: calcio morto dopo 18h).
        session.planned_restart = keep_alive_desktop
    # BUG FIX cert 10/07 (VISTO DAL VIVO): con LIVE_RUNNER_KEEP_ALIVE=1 (app desktop)
    # il ramo IDLE non deve spegnere — il main loop è progettato per restare in
    # ATTESA senza eventi (canale locale + board vivi), ma il lifecycle spegneva
    # comunque alla fine dell'ultima partita e il watchdog (correttamente) non
    # riavvia su exit 0 → runner desktop MORTO dopo la prima partita. La vita
    # massima resta attiva anche col keep-alive (backstop anti-"giorni acceso").
    elif keep_alive_desktop:
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
    # fix TOCTOU 17/07: tra il primo check e qui (log + insert_alert = anche
    # centinaia di ms) il live_order_worker può aver piazzato un ordine →
    # RI-VERIFICA subito prima dello stop. Finestra residua (pochi ms fino al
    # TerminationEvent) dichiarata: un lock condiviso col percorso di
    # piazzamento richiederebbe di toccare live_order_worker (altro cantiere).
    blocker = _lifecycle_blockers(flumine)
    if blocker is not None:
        logger.warning(
            "[lifecycle] spegnimento RINVIATO all'ultimo check (%s): %s.", reason, blocker)
        return
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


def _finito_senza_mercati(follow: Dict[str, Any]) -> bool:
    """28/09 (cantiere A): catalogo REST VUOTO + partita gia' iniziata =
    partita FINITA.

    Documentazione Betfair (listMarketCatalogue): "Returns a list of
    information about published (ACTIVE/SUSPENDED) markets [...]
    listMarketCatalogue does not return markets that are CLOSED". Un evento
    iniziato i cui mercati non sono piu' in catalogo ha quindi tutti i mercati
    CLOSED (regolati o annullati): e' la regola dell'utente, "quando i mercati
    per quella partita sono tutti chiusi l'evento e' terminato". Un errore di
    rete NON arriva qui (``betting_rpc`` solleva, mai una lista vuota).
    Prima si aspettavano 3 ore dal calcio d'inizio: la partita finita restava
    PENDING/STREAMING e ogni giro del sub-worker la ricontava come nuova
    (ricostruzione dello stream a ogni intervallo) fino alla soglia.

    Evento futuro (open_date nel futuro) o open_date illeggibile/assente: NON
    finito (i mercati possono non essere ancora pubblicati)."""
    open_date = follow.get("open_date")
    if not open_date:
        return False
    try:
        dt = datetime.fromisoformat(str(open_date).replace("Z", "+00:00"))
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= dt


#: 28/09 (cantiere A, guardia di CONFERMA richiesta dal coordinatore): una
#: partita si ritira per catalogo vuoto solo alla SECONDA lettura vuota fatta
#: almeno tanti secondi dopo la prima. 120 s: (1) Betfair regola il MATCH_ODDS
#: ~5 minuti dopo la fine, quindi una fine vera resta vuota per sempre e 2
#: minuti in piu' non costano niente (lo stream, se il mercato e' sottoscritto,
#: chiude comunque da solo col CLOSED); (2) una risposta vuota anomala e
#: isolata (ripubblicazione del catalogo, nodo REST in ritardo) non si ripete
#: due volte a 2 minuti; (3) e' il tempo che il sub-worker impiega comunque a
#: ripassare (2 s) senza riaprire ricostruzioni: la rilettura e' mirata.
FINE_CONFERMA_S = float(os.getenv("LIVE_FINE_CONFERMA_S", "120") or 120.0) or 120.0
#: partita col catalogo vuoto ma con SOLDI dentro: si ricontrolla ogni tanto
#: (catalogo + soldi), mai a ogni giro (una lettura REST e 3 SELECT).
FINE_RIVERIFICA_SOLDI_S = float(os.getenv("LIVE_FINE_RIVERIFICA_SOLDI_S", "300") or 300.0) or 300.0


def _stato_fine(session: Any) -> Dict[str, Dict[str, float]]:
    """``{"vuoto_dal": {ev: mono}, "trattenute": {ev: mono ultimo controllo}}``
    (memoria di processo; una sessione finta senza attributi la riceve qui)."""
    st = getattr(session, "fine_evento", None)
    if st is None:
        st = {"vuoto_dal": {}, "trattenute": {}}
        try:
            session.fine_evento = st
        except Exception:  # noqa: BLE001
            pass
    return st


def _fine_dimentica(session: Any, event_id: str) -> None:
    st = _stato_fine(session)
    st["vuoto_dal"].pop(str(event_id), None)
    st["trattenute"].pop(str(event_id), None)


def _fine_da_rileggere(session: Any, event_id: str, ora: float) -> bool:
    """Il catalogo dell'evento va riletto adesso? Mai visto vuoto: si'. In
    conferma: solo dopo FINE_CONFERMA_S dalla prima lettura vuota. Trattenuto
    per soldi: ogni FINE_RIVERIFICA_SOLDI_S."""
    st = _stato_fine(session)
    ev = str(event_id)
    if ev in st["trattenute"]:
        return ora - st["trattenute"][ev] >= FINE_RIVERIFICA_SOLDI_S
    if ev in st["vuoto_dal"]:
        return ora - st["vuoto_dal"][ev] >= FINE_CONFERMA_S
    return True


def _soldi_sull_evento(session: Any, event_id: str) -> Optional[str]:
    """Denaro in gioco sull'evento (paper o live): specchio e coda dal DB
    (``db.soldi_sull_evento``) e comandi PARCHEGGIATI nel motore ordini (RAM)
    su un suo mercato. Illeggibile = soldi presunti (mai al buio)."""
    try:
        mercati = db.mercati_evento(event_id)
        motivo = db.soldi_sull_evento(event_id, mercati)
    except Exception as e:  # noqa: BLE001
        return "denaro non verificabile (%s)" % str(e)[:120]
    if motivo:
        return motivo
    mot = _motore_attivo()
    parcheggiati = getattr(mot, "_in_aggancio", None) if mot is not None else None
    if isinstance(parcheggiati, dict) and mercati:
        sul_evento = [r for r in list(parcheggiati.values())
                      if str((r or {}).get("market_id")) in set(mercati)]
        if sul_evento:
            return "%d comandi in volo nel motore sull'evento" % len(sul_evento)
    return None


def _valuta_catalogo_vuoto(session: Any, event_id: str, ora: float) -> str:
    """Partita INIZIATA col catalogo vuoto: ``in_conferma`` | ``trattenuta`` |
    ``finita``. Solo ``finita`` ritira la partita (``_finalize_event``).

    * prima lettura vuota: si annota l'orario, niente altro (guardia CONFERMA);
    * lettura vuota dopo FINE_CONFERMA_S: se c'e' denaro sull'evento la partita
      NON si ritira (guardia SOLDI DENTRO): resta seguita com'e', alert
      CRITICAL una volta, ricontrollo ogni FINE_RIVERIFICA_SOLDI_S finche' la
      posizione non e' regolata o chiusa;
    * senza denaro: finita."""
    st = _stato_fine(session)
    ev = str(event_id)
    dal = st["vuoto_dal"].setdefault(ev, ora)
    if ora - dal < FINE_CONFERMA_S:
        logger.info("[runner] %s: partita iniziata e catalogo vuoto (prima lettura): "
                    "riletto fra %.0fs prima di ritirarla.", ev, FINE_CONFERMA_S)
        return "in_conferma"
    motivo = _soldi_sull_evento(session, ev)
    if motivo:
        prima_volta = ev not in st["trattenute"]
        st["trattenute"][ev] = ora
        if prima_volta:
            logger.critical("[runner] %s: catalogo vuoto (partita finita?) ma %s: NON "
                            "ritirata, resta seguita.", ev, motivo)
            try:
                db.insert_alert(
                    "CRITICAL", "FINE_PARTITA_CON_SOLDI",
                    f"partita {ev}: nessun mercato piu' in catalogo (finita?) ma {motivo}. "
                    "Non la ritiro: resta seguita finche' la posizione non e' regolata "
                    "o chiusa. Verifica a mano.", ev)
            except Exception:  # noqa: BLE001 - l'alert non decide niente
                pass
        return "trattenuta"
    logger.info("[runner] follow %s: partita iniziata e nessun mercato in catalogo "
                "(tutti CLOSED, confermato dopo %.0fs, nessun denaro) -> finita, "
                "ritiro e carico nel Replay.", ev, ora - dal)
    _fine_dimentica(session, ev)
    _finalize_event(ev, session)
    return "finita"


def _ricontrolla_fine(rest: Any, session: Any, follows: List[Dict[str, Any]]) -> None:
    """Dal sub-worker (2 s): rilegge il catalogo SOLO degli eventi in conferma o
    trattenuti per soldi arrivati al loro momento. Nessuna ricostruzione dello
    stream: mercati tornati -> l'evento esce dalla memoria e il giro normale lo
    aggancia; ancora vuoto -> ``_valuta_catalogo_vuoto``."""
    st = _stato_fine(session)
    if not st["vuoto_dal"] and not st["trattenute"]:
        return
    ora = time.monotonic()
    for f in follows:
        ev = str(f.get("event_id"))
        if ev not in st["vuoto_dal"] and ev not in st["trattenute"]:
            continue
        if ev in session.finished_events or not _fine_da_rileggere(session, ev, ora):
            continue
        try:
            markets = fetch_event_markets(rest, ev)
        except Exception as e:  # noqa: BLE001 - si riprova al momento dopo
            logger.warning("[sub-worker] catalogo di %s KO: %s", ev, str(e)[:120])
            continue
        if markets:
            _fine_dimentica(session, ev)
        elif _finito_senza_mercati(f):
            _valuta_catalogo_vuoto(session, ev, ora)


def _catalog_events(rest: BetfairClient, session: LiveSession, follows: List[Dict[str, Any]]) -> None:
    """Scarica il catalogo dei nuovi eventi, applica il budget mercati (F5)."""
    for f in follows:
        event_id = f["event_id"]
        if event_id in session.cataloged_events or event_id in session.finished_events:
            continue
        if not _fine_da_rileggere(session, event_id, time.monotonic()):
            continue        # 28/09: in conferma o trattenuta, non ancora il momento
        markets = fetch_event_markets(rest, event_id)
        if markets:
            _fine_dimentica(session, event_id)   # mercati di nuovo in catalogo
        if not markets:
            if _finito_senza_mercati(f):
                # Partita finita/rimossa dal catalogo. NON lasciarla PENDING:
                # altrimenti subscription_worker la riconta come "nuova" ad ogni
                # poll e riavvia lo stream all'infinito (loop F3, bug 07/07).
                # _finalize_event la CARICA nel Replay (se ci sono dati grezzi),
                # porta lo status a terminale e la mette in finished_events così
                # non viene più ritentata. → "le vecchie caricate, le nuove seguite".
                # 28/09: iniziata + catalogo vuoto (mercati CLOSED, vedi
                # _finito_senza_mercati), con le due guardie di
                # _valuta_catalogo_vuoto: CONFERMA (seconda lettura vuota dopo
                # FINE_CONFERMA_S) e SOLDI DENTRO (mai ritirata con denaro in gioco).
                _valuta_catalogo_vuoto(session, event_id, time.monotonic())
            else:
                # Evento futuro: mercati non ancora pubblicati. Lascia PENDING,
                # verrà catalogato al prossimo giro quando i mercati escono.
                logger.warning("[runner] nessun mercato per %s (non ancora pubblicati?)", event_id)
            continue
        # 06/10: i mercati delle partite FINITE restano in ``market_to_event``
        # (lo legge il registratore) ma non si sottoscrivono piu': contarli
        # riempiva il tetto in un processo lungo e la partita nuova restava
        # PENDING per sempre (REFUSE). Si contano i manuali che si sottoscrivono.
        prospective = len(mercati_manuali_da_sottoscrivere(session)) + len(markets)
        # 28/09 (cantiere B): il tetto e' la capacita' di TUTTE le connessioni
        # di mercato (frammenti), non piu' di una sola; soglia d'allerta in
        # proporzione (150/180 di sempre)
        cap = _capacita_mercati()
        soglia = max(1, cap * SAFE_MARKET_THRESHOLD // max(1, HARD_MARKET_CAP))
        verdict = limits.check_market_budget(prospective, soglia, cap)
        if verdict == "REFUSE":
            msg = limits.budget_message(verdict, prospective, soglia, cap)
            logger.error("[runner] %s", msg)
            db.insert_alert("CRITICAL", "MARKET_CAP", msg, event_id)
            continue  # lascia PENDING: niente ban
        if verdict == "WARN":
            msg = limits.budget_message(verdict, prospective, soglia, cap)
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
        # poller per evento — PRIMARIO = feed unico dello scanner Safe Strategy
        # (scores/scan_feed.py: stesso stato IPS, già scaricato in batch per tutti
        # gli in-play), con fallback INTERNO alla chiamata IPS diretta se la riga
        # manca o è stantia; API-Football resta il fallback del circuit breaker.
        session.pollers[event_id] = ScorePoller(
            ScanFeedScoreProvider(BetfairInPlayProvider(session.context_api_client)),  # type: ignore[attr-defined]
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


# F0 (16/09) - il client PAPER affiancato vive dal 24/09 in un modulo condiviso
# (lo usa anche il runner tennis per i bot PAPER a runner LIVE, reperto T1):
# codice SPOSTATO senza modifiche, stesso nome qui per chi importa dal runner.
from .client_paper_affiancato import PaperCompanionClient  # noqa: E402,F401


def build_paper_companion_client(api_client: Any) -> "PaperCompanionClient":
    """Client SIMULATO da affiancare a quello reale in un runner LIVE (F0).

    Stessi parametri del client PAPER di ``build_order_client`` (order_stream=True ->
    SimulatedOrderStream, ``min_bet_validation=False``, ``transaction_limit``), cosi'
    che una riga paper si comporti esattamente come nel runner PAPER. La latenza
    simulata del fill (``flumine_config.place_latency``) e' impostata anche qui:
    senza, il paper dentro un runner LIVE sarebbe piu' veloce del paper puro.
    """
    if PAPER_SIMULATED_LATENCY_MS and PAPER_SIMULATED_LATENCY_MS > 0:
        flumine_config.place_latency = float(PAPER_SIMULATED_LATENCY_MS) / 1000.0
    return PaperCompanionClient(
        api_client,
        order_stream=True,
        order_stream_conflate_ms=ORDER_STREAM_CONFLATE_MS or None,
        paper_trade=True,
        min_bet_validation=False,
        transaction_limit=LIVE_TRANSACTION_LIMIT,
    )


def heartbeat_mode() -> str:
    """Valore da scrivere in ``betfair_live_heartbeat.mode``: le modalita' che il
    runner SERVE, non solo quella in cui gira (F0).

    Un runner LIVE serve anche le righe 'paper' (client simulato affiancato), e chi
    legge il battito (gate dei bot) deve poterlo sapere. La tabella ha una sola
    colonna ``mode`` TEXT e nessun campo JSON (``migrations/betfair_live_account_heartbeat.sql:53``),
    quindi le modalita' servite si dichiarano NELLA STESSA colonna, separate da '+':
    ``LIVE+PAPER``. Compatibilita' garantita nei due sensi:
      * una riga VECCHIA ``mode='LIVE'`` dichiara solo LIVE -> il gate paper resta
        CHIUSO (era il comportamento prima di F0, e deve restare tale);
      * ``mode='PAPER'`` (runner paper) resta identico a prima.
    Migrazione da fare (elencata, NON scritta qui): una riga di heartbeat per
    runner/modalita', o una colonna ``modes JSONB`` su ``betfair_live_heartbeat``.
    """
    mode = live_order_mode().strip().upper()
    return "LIVE+PAPER" if mode == "LIVE" else mode


def _testo_modo_ordini(mode: str, effettivo: Optional[str] = None) -> Tuple[str, str, str]:
    """(modo effettivo, banner, livello dell'alert) - F-9 (26/09).

    Prima il banner e l'alert CRITICAL «LIVE... SOLDI VERI» annunciavano il
    TETTO del .env (``LIVE_ORDER_MODE``) mentre il modo EFFETTIVO e' il piu'
    restrittivo fra tetto e scelta dalla UI (``modo_ordini.modo_effettivo``,
    riga ``betfair_live_settings.order_mode``: il 26/09 paper). Ora si
    annuncia l'EFFETTIVO; se differisce dal tetto lo si dice esplicitamente.
    CRITICAL solo se l'effettivo e' LIVE. ``effettivo=None`` = uguale al tetto
    (comportamento di prima). Solo testo: il gate degli ordini non cambia."""
    tetto = (mode or "OFF").strip().upper()
    eff = (effettivo or tetto).strip().upper()
    base = {
        "LIVE": "*** LIVE *** ORDINI REALI (SOLDI VERI) attivi",
        "PAPER": "PAPER -- ordini SIMULATI (soldi finti, dati live)",
        "OFF": "OFF -- nessun ordine (solo registrazione/segnali)",
    }.get(eff, f"{eff} -- modalita' sconosciuta: trattata come OFF")
    if eff != tetto:
        banner = f"tetto {tetto}, effettivo {eff} -- {base}"
    else:
        banner = base
    level = "CRITICAL" if eff == "LIVE" else "INFO"
    return eff, banner, level


def _announce_order_mode(mode: str, orders_enabled: bool,
                         effettivo: Optional[str] = None) -> None:
    """Logga in modo EVIDENTE la modalità ordini e (se attiva) la annuncia in live_alerts.

    In OFF nessun side-effect oltre al log (ZERO regressioni: nessuna scrittura DB nuova).
    F-9 (26/09): banner e livello seguono il modo EFFETTIVO (vedi _testo_modo_ordini).
    """
    eff, banner, level = _testo_modo_ordini(mode, effettivo)
    bar = "=" * 64
    logger.info("%s", bar)
    logger.info("[runner] MODALITA' ORDINI: %s", banner)
    logger.info("%s", bar)
    if not orders_enabled:
        return  # OFF → nessuna scrittura DB aggiuntiva
    try:
        db.insert_alert(level, "ORDER_MODE", f"Live trading: modalita' {eff} attiva. {banner}")
    except Exception as e:  # noqa: BLE001 - un alert non deve mai bloccare l'avvio
        logger.warning("[runner] insert_alert modalita' ordini KO (ignorato): %s", e)


# 23/09 - (5) la modalita' ordini del client si decide all'AVVIO con
# ``live_order_mode()`` (come il worker), non con la costante letta all'import.
_RANGO_MODO = {"OFF": 0, "PAPER": 1, "LIVE": 2}


def _modo_ordini_client(modo_avvio: str) -> str:
    """Modalita' con cui (ri)costruire client ordini e worker a ogni giro dello
    stream: SEMPRE quella d'avvio. Un client non si costruisce mai a caldo.

    Se ``live_order_mode()`` e' SALITO dopo l'avvio (PAPER->LIVE, OFF->...):
    errore "serve il riavvio" (il worker, che rilegge il modo a ogni giro, non
    trova il client della modalita' nuova e rifiuta le righe). Se e' SCESO
    (LIVE->PAPER/OFF): avviso, il worker declassa gia' a caldo gli ordini."""
    avvio = (modo_avvio or "OFF").strip().upper()
    ora = live_order_mode().strip().upper()
    if ora != avvio:
        if _RANGO_MODO.get(ora, 0) > _RANGO_MODO.get(avvio, 0):
            logger.error("[runner] LIVE_ORDER_MODE cambiato a caldo da %s a %s: il client "
                         "ordini NON si costruisce a caldo, resta %s - serve il riavvio "
                         "del runner", avvio, ora, avvio)
        else:
            logger.warning("[runner] LIVE_ORDER_MODE sceso a caldo da %s a %s: il worker "
                           "declassa gli ordini a ogni giro; il client resta %s fino al "
                           "riavvio", avvio, ora, avvio)
    return avvio


# 23/09 - (6) GUARDIA D'AVVIO del runner calcio (``Betfair/stream/avvio_app.py``).
# Il runner non ha una riga di controllo per-bot: la guardia sta sul CLIENT
# ORDINI. Finche' la ripresa d'avvio (specchio paper pulito + richieste
# ereditate stantie marcate error) non e' riuscita, il worker della coda non
# esegue NULLA - fail-closed: prima la ripresa era best-effort e, se il DB non
# rispondeva, la coda ereditata veniva eseguita lo stesso.
_GUARDIA_AVVIO = AA.Guardia("runner_calcio")
_RIPRESA_RIPROVA_S = 10.0
_RIPRESA_STATO: dict = {"ultimo": 0.0}


# 24/09 - MOTORE ORDINI (F1/F2/F3, ``motore_ordini.py``): esecutore a evento dei
# comandi del canale 47331 (``/order`` di sempre e ``/comando/<attore>``), con
# diario write-ahead e IO DB differito. SPENTO di serie: si accende con
# ``MOTORE_ORDINI_CANALE=1`` (lavoro nuovo, da certificare prima dell'uso).
# Spento = comportamento di prima, identico (il worker della coda drena il canale).
_MOTORE: Dict[str, Any] = {"motore": None, "api": None, "auto": None}


def _motore_abilitato() -> bool:
    return os.getenv("MOTORE_ORDINI_CANALE", "").strip() == "1"


def _motore_attivo() -> Optional[Any]:
    return _MOTORE.get("motore")


def _auto_attivo() -> Optional[Any]:
    """25/09 - l'AUTO-FOLLOW del runner (``auto_follow.AutoFollow``), o None."""
    return _MOTORE.get("auto")


def _costruisci_auto_follow(ch: Any) -> Any:
    """L'auto-follow: thread nel runner, piano col tetto della connessione di
    mercato, righe live_follow ``origine='auto'``, feed unico per il proattivo,
    attori collegati dal canale di comando (zero IO), stato alla UI sul canale."""
    def _feed() -> Optional[List[Dict[str, Any]]]:
        from db_client import get_supabase_client
        return _AF.leggi_feed_calcio(get_supabase_client())

    def _pubblica(stato: Dict[str, Any]) -> None:
        ch.set_hello(auto_follow=stato)
        _lc.publish("auto_follow", stato)

    # 28/09 (cantiere B): la connessione di mercato a FRAMMENTI (piu'
    # connessioni, ognuna <= HARD_MARKET_CAP mercati): il tetto del piano e'
    # la capacita' vera (connessioni concesse x mercati per connessione)
    gestore = _FR.GestoreFrammenti.da_ambiente()
    return _AF.AutoFollow(piano=_AF.PianoFollow(gestore.capacita(None)),
                          sottoscrittore=gestore, follow_db=_AF.FollowDb(), feed=_feed,
                          attori_collegati=ch.attori_comando, pubblica=_pubblica)


def _capacita_mercati() -> int:
    """28/09: i mercati che la connessione di mercato del runner puo' portare.
    Con l'auto-follow (frammenti): il tetto del suo piano; senza: una sola
    connessione, ``HARD_MARKET_CAP`` come sempre."""
    auto = _auto_attivo()
    tetto = getattr(getattr(auto, "piano", None), "tetto", None)
    return int(tetto) if isinstance(tetto, int) and tetto > 0 else int(HARD_MARKET_CAP)


def _mercati_con_soldi_dallo_specchio(candidati: List[str]) -> Set[str]:
    """28/09 (cantiere B): fra i mercati che si stanno per sottoscrivere, quelli
    con soldi dentro secondo lo SPECCHIO che il runner stesso scrive, paper e
    live. Serve dopo un riavvio del PROCESSO (blotter perso): e' la sola
    memoria dei soldi senza chiamare Betfair. Le regole sono quelle della
    guardia «soldi dentro» del cantiere A (``db.mercati_con_soldi`` usa gli
    stessi ``STATI_ORDINE_VIVO``, ``esposizione_aperta`` e l'esclusione dei
    regolati di ``db.soldi_sull_evento``). Qui e' una PRIORITA', non una
    guardia: illeggibile -> insieme vuoto e avviso (restano blotter precedente
    e comandi), la costruzione prosegue."""
    try:
        return {str(m) for m in db.mercati_con_soldi(list(candidati))}
    except Exception as ex:  # noqa: BLE001 - priorita', mai un blocco dell'avvio
        logger.warning("[runner] specchio ordini/posizioni non letto per il frammento 0 "
                       "(restano blotter precedente e comandi): %s", str(ex)[:200])
        return set()


def _mercati_con_soldi(prec: Set[str], auto: Any, candidati: List[str],
                       specchio: Any = None) -> "Tuple[Set[str], Dict[str, int]]":
    """28/09 (cantiere B, punto 1 del coordinatore): i mercati con soldi dentro
    alla (ri)costruzione del framework, dalle fonti che il runner ha GIA' (mai
    una chiamata Betfair): blotter del framework precedente (``prec``, stesso
    processo), auto-follow (voci con ordini allo sgancio e voci di comando),
    specchio ordini/posizioni (``specchio``, di serie il DB). Ritorna
    (mercati fra i candidati, conteggio per fonte)."""
    cand = {str(m) for m in candidati}
    da_auto: Set[str] = set()
    try:
        da_auto = set(auto.mercati_da_proteggere()) if auto is not None else set()
    except Exception:  # noqa: BLE001
        da_auto = set()
    lettore = specchio or _mercati_con_soldi_dallo_specchio
    da_specchio = set(lettore(sorted(cand)))
    fonti = {"blotter_precedente": len(set(prec) & cand), "auto_follow": len(da_auto & cand),
             "specchio_db": len(da_specchio & cand)}
    return (set(prec) | da_auto | da_specchio) & cand, fonti


def _frammento0(market_ids: List[str], manuali: List[str], auto: Any,
                con_soldi: Set[str], fonti: Dict[str, int]) -> List[str]:
    """28/09 (cantiere B): i mercati della connessione che nasce col framework.
    Ordine: con soldi dentro, manuali, il resto (``primo_frammento``). Se i
    mercati con soldi superano da soli un frammento, quelli in eccesso vanno
    sui frammenti aperti a caldo dall'auto-follow appena lo stream gira (pochi
    secondi; i loro comandi aspettano un book nuovo, ``servibile``): lo si
    DICHIARA (stato ``frammenti.costruzione``, log, alert CRITICAL).
    Senza auto-follow: tutti i mercati (una connessione, budget di sempre)."""
    gestore = getattr(auto, "sottoscrittore", None) if auto is not None else None
    if not isinstance(gestore, _FR.GestoreFrammenti):
        return list(market_ids)
    ids0 = _FR.primo_frammento(market_ids, manuali, gestore.per_conn, con_soldi)
    c = gestore.segna_costruzione(set(con_soldi) & set(market_ids), ids0, fonti)
    if c["oltre_frammento0"]:
        msg = ("%d mercati con posizioni/ordini vivi, piu' di un frammento (%d): %d attendono "
               "la connessione aperta a caldo (%s)" % (c["con_soldi"], gestore.per_conn,
                                                       c["oltre_frammento0"],
                                                       ", ".join(c["oltre_frammento0_mercati"][:10])))
        logger.error("[runner] %s", msg)
        try:
            db.insert_alert("CRITICAL", "SOLDI_OLTRE_FRAMMENTO0", msg)
        except Exception as ex:  # noqa: BLE001 - l'alert non blocca la costruzione
            logger.warning("[runner] alert frammento 0 KO: %s", str(ex)[:160])
    elif c["con_soldi"]:
        logger.info("[runner] frammento 0: %d mercati con soldi dentro davanti a tutti (%s)",
                    c["con_soldi"], fonti)
    return ids0


def _lista_ordini_ripresa(customer_order_refs: List[str]) -> Any:
    """``listCurrentOrders`` per customerOrderRef (risposta lightweight, chiavi
    Betfair). Usata SOLO dalla ripresa del motore, prima del disarmo."""
    api = _MOTORE.get("api")
    if api is None:
        raise RuntimeError("client Betfair non disponibile per la ripresa")
    return api.betting.list_current_orders(customer_order_refs=list(customer_order_refs),
                                           lightweight=True)


def _costruisci_motore(ch: Any) -> Any:
    cartella = os.getenv("MOTORE_DIARIO_DIR", "").strip() or os.path.join(
        DATA_DIR, "_diario_ordini")
    return _MOT.MotoreOrdini(
        "calcio", canale=ch, diario=_MOT.Diario(cartella),
        scrittore=_MOT.ScrittoreAsincrono(nome="scrittore-db-calcio"),
        guardia_armata=lambda: bool(_GUARDIA_AVVIO.blocca_aperture),
        motivo_guardia_order=_MOTIVO_GUARDIA_LOCALE,
        aggancio=_auto_attivo())
# 24/09 - MODO ORDINI DALLA UI: all'avvio dell'app la scelta torna a PAPER
# (``modo_ordini.dichiara_avvio``, stesso schema di ``avvio_app`` per Omega/Mike/
# Safe) e il runner dichiara il TETTO del suo .env. Finche' non riesce la scelta
# dalla UI non vale (``modo_ordini.richiedi_avvio``): aperture OFF, chiusure si'.
_MODO_AVVIO_STATO = {"ultimo": -1e9}


def _dichiara_modo_ordini_all_avvio(forza: bool = False) -> bool:
    """True = fatto (o non serviva). Riprova al massimo ogni ``_RIPRESA_RIPROVA_S``."""
    if not _MO.avvio_in_attesa():
        return True
    adesso = time.monotonic()
    if not forza and adesso - _MODO_AVVIO_STATO["ultimo"] < _RIPRESA_RIPROVA_S:
        return False
    _MODO_AVVIO_STATO["ultimo"] = adesso
    try:
        from db_client import get_supabase_client

        sb = get_supabase_client()
        riga = getattr(sb.rpc("get_live_settings", {}).execute(), "data", None)
        _MO.dichiara_avvio(sb, riga, AA.boot_id_ambiente(), live_order_mode())
        return True
    except Exception as ex:  # noqa: BLE001 - si riprova: intanto aperture OFF
        logger.error("[runner] modo ordini all'avvio NON dichiarato (aperture ferme, "
                     "chiusure servite; migrazione live_order_mode_control applicata?): %s",
                     str(ex)[:200])
        return False


def _ripresa_all_avvio() -> bool:
    """Ripresa dopo crash/riavvio (A6). True = riuscita, guardia disarmata."""
    try:
        n_ord, n_pos = db.cleanup_paper_mirror()
        n_stale = db.fail_stale_pending_requests(120.0)
    except Exception as ex:  # noqa: BLE001 - la guardia resta armata, si riprova
        logger.error("[runner] pulizia di ripresa KO: coda ordini FERMA (guardia "
                     "d'avvio armata) finche' non riesce: %s", str(ex)[:200])
        return False
    motore = _motore_attivo()
    if motore is not None and not motore.riprendi_da_diario(_lista_ordini_ripresa):
        # 24/09 F1: comandi in volo al riavvio non verificati su Betfair: la
        # guardia resta ARMATA (solo cancel) e si riprova al giro dopo.
        logger.error("[runner] ripresa dal diario del motore NON completa: guardia "
                     "d'avvio armata")
        return False
    _GUARDIA_AVVIO.fatto = True
    if n_ord or n_pos or n_stale:
        logger.info(
            "[runner] ripresa: specchio paper pulito (%d ordini, %d posizioni), "
            "%d richieste stantie marcate error", n_ord, n_pos, n_stale,
        )
        try:
            db.insert_alert(
                "INFO", "RUNNER_RESUME",
                f"riavvio runner: specchio paper pulito ({n_ord} ordini, {n_pos} "
                f"posizioni), {n_stale} richieste stantie scartate",
            )
        except Exception as ex:  # noqa: BLE001 - l'alert non blocca l'avvio
            logger.warning("[runner] alert di ripresa KO: %s", str(ex)[:200])
    return True


_MOTIVO_GUARDIA_LOCALE = "runner in ripresa: comando NON eseguito, riprova"


def _rispondi_comandi_locali_in_guardia(flumine: Any, strategy: Any) -> int:
    """23/09 (B-1, revisore B): a guardia d'avvio ARMATA il worker della coda non
    gira, ma il canale locale 47331 e' gia' aperto e accetta i comandi del desktop.
    Prima restavano in coda in RAM (fino a 200) senza risposta e partivano TUTTI
    al disarmo, minuti dopo (anche doppi: il trader riprova con client_ref nuovi).
    Adesso a ogni giro la coda si DRENA per intero e ogni comando riceve subito
    ``ok=False`` con il motivo: nessun comando resta in coda per dopo.

    Scelta documentata: passa SOLO ``cancel`` (ritira un ordine, riduce
    l'esposizione e non ne crea), con le stesse regole del giro normale (il
    kill-switch oggi lo lascia sempre passare, ``_CLOSING_ACTIONS``). greenup e
    cashout NO: piazzano ordini nuovi (hedge) prima che la ripresa sia riuscita.
    Anche ``snapshot`` riceve il rifiuto (nessuna lettura del blotter a ripresa
    non fatta). Ritorna quante richieste ha gestito."""
    ch = _lc.get_channel()
    if ch is None:
        return 0
    annulli: list = []
    gestite = 0
    while True:
        reqs = ch.pop_requests()
        if not reqs:
            break
        for req in reqs:
            gestite += 1
            params = req.params if isinstance(req.params, dict) else {}
            if req.method == "order" and str(params.get("action") or "") == "cancel":
                annulli.append(req)
                continue
            ch.respond(req, False, error=_MOTIVO_GUARDIA_LOCALE)
    if annulli:
        try:
            _LOW.esegui_richieste_locali_scelte(flumine, strategy, annulli)
        except Exception as ex:  # noqa: BLE001 - mai lasciare un annullo senza risposta
            logger.warning("[runner] annulli locali in guardia KO: %s", str(ex)[:200])
            for req in annulli:
                ch.respond(req, False, error=f"annullo NON eseguito: {str(ex)[:120]}")
    return gestite


def _live_order_worker_guardato(context: dict, flumine: Any, session: Any = None,
                                strategy: Any = None) -> None:
    """``live_order_worker`` dietro la guardia d'avvio: guardia armata e ripresa
    non riuscita -> nessun ordine (riprova la ripresa ogni ``_RIPRESA_RIPROVA_S``);
    i comandi del canale locale ricevono subito il rifiuto (B-1), salvo ``cancel``."""
    if _GUARDIA_AVVIO.blocca_aperture:
        adesso = time.monotonic()
        if adesso - _RIPRESA_STATO["ultimo"] >= _RIPRESA_RIPROVA_S:
            _RIPRESA_STATO["ultimo"] = adesso
            _ripresa_all_avvio()
        if _GUARDIA_AVVIO.blocca_aperture:
            # col motore montato il canale lo serve LUI (stessa regola B-1)
            if _motore_attivo() is None:
                _rispondi_comandi_locali_in_guardia(flumine, strategy)
            return
    _dichiara_modo_ordini_all_avvio()  # 24/09: no-op quando gia' fatto
    live_order_worker(context, flumine, session=session, strategy=strategy)


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
    # K1 (26/09): cambio GBP->EUR delle size dello stream (listCurrencyRates,
    # rinfresco orario, cache su disco). Mai un'eccezione.
    _valuta.CAMBIO.avvia(api_client)

    session = LiveSession()
    session.context_api_client = api_client  # type: ignore[attr-defined]
    session.only_event = only_event  # type: ignore[attr-defined]
    # 28/09 (cantiere A): righe live_now "in gioco" di partite non piu' seguite
    # (follow CLOSED/UPLOADED/ERROR) -> CLOSED, una volta per processo
    _chiudi_live_now_orfani_all_avvio()
    # A7 — canale LOCALE per l'app desktop (bind SOLO 127.0.0.1). Best-effort:
    # se la porta è occupata il runner vive comunque (path DB invariato).
    # 23/09 - modalita' ordini letta ADESSO (live_order_mode, come il worker), non
    # la costante dell'import: e' quella con cui si costruisce il client.
    modo_avvio = live_order_mode().strip().upper()
    # 24/09: la scelta del modo ordini dalla UI non vale finche' la riga non e'
    # stata riportata a PAPER per QUESTO avvio (e dichiarato il tetto del .env).
    _MO.richiedi_avvio()
    _dichiara_modo_ordini_all_avvio(forza=True)
    ch = _lc.start_channel(int(os.getenv("LIVE_LOCAL_WS_PORT", "47331")), "calcio")
    if ch is not None:
        ch.set_hello(mode=modo_avvio)
    # 24/09 - motore ordini (opt-in): montato PRIMA della ripresa d'avvio, che
    # rilegge il suo diario; il thread parte subito ma senza framework rifiuta.
    _MOTORE["api"] = api_client
    if ch is not None and modo_avvio in ("PAPER", "LIVE") and _motore_abilitato():
        # 25/09 AUTO-FOLLOW (di serie col motore; RUNNER_AUTO_FOLLOW=0 lo
        # spegne): costruito PRIMA del motore, che lo riceve; le righe
        # automatiche di un processo precedente si chiudono PRIMA del primo
        # ``list_pending_follows`` (se no diventerebbero follow manuali).
        if _AF.acceso():
            try:
                _MOTORE["auto"] = _costruisci_auto_follow(ch)
                chiusi = _MOTORE["auto"].follow_db.chiudi_orfani()
                _MOTORE["auto"].avvia()
                logger.info("[runner] AUTO-FOLLOW ATTIVO: i bot operano da soli su tutte "
                            "le partite (aggancio al volo + feed), tetto %d mercati sulla "
                            "connessione di mercato (limite Betfair %d), %d follow auto "
                            "di prima chiusi", _MOTORE["auto"].piano.tetto,
                            _AF.LIMITE_BETFAIR_MERCATI, chiusi)
            except Exception as ex:  # noqa: BLE001 - senza auto-follow: come prima
                logger.error("[runner] AUTO-FOLLOW NON avviato (%s): i mercati non "
                             "seguiti restano rifiutati", str(ex)[:200])
                _MOTORE["auto"] = None
        else:
            logger.warning("[runner] AUTO-FOLLOW SPENTO (RUNNER_AUTO_FOLLOW=0): il motore "
                           "rifiuta gli ordini sulle partite non seguite")
        try:
            _MOTORE["motore"] = _costruisci_motore(ch)
            _MOTORE["motore"].avvia()
            logger.info("[runner] motore ordini ATTIVO sul canale %d (diario %s)",
                        ch.port, _MOTORE["motore"].diario.cartella)
        except Exception as ex:  # noqa: BLE001 - senza motore: percorso di prima
            logger.error("[runner] motore ordini NON avviato (%s): resta il percorso "
                         "del worker della coda", str(ex)[:200])
            _MOTORE["motore"] = None
    interrupted = False
    # 28/09 (cantiere B): mercati con ordini nel blotter del framework
    # precedente (stesso processo), per il frammento 0 della ricostruzione
    mercati_con_ordini_prec: Set[str] = set()

    # Annuncia UNA volta la modalità ordini (il banner nei log + alert se PAPER/LIVE).
    # I restart F3 ricostruiscono il framework ma non ri-annunciano (niente spam alert).
    # F-9 (26/09): si annuncia il modo EFFETTIVO (tetto .env x scelta UI letta
    # all'avvio), non il solo tetto; non ancora letto -> OFF, come il gate.
    _announce_order_mode(modo_avvio, modo_avvio in ("PAPER", "LIVE"),
                         _MO.modo_effettivo(modo_avvio, _MO.valore_db()))

    # A6 — RIPRESA dopo crash/riavvio (una volta per processo, PRIMA del framework):
    #   * specchio PAPER stantio → pulito (il blotter paper riparte vuoto: le righe
    #     di sessioni precedenti sono orfane). Le righe LIVE non si toccano MAI.
    #   * richieste ancora 'pending' più vecchie di 120s → ERROR esplicito: un
    #     comando accodato prima di un crash NON va eseguito minuti dopo a un
    #     mercato completamente diverso (money-critical, mai comandi stantii).
    # La ricostruzione LIVE dal conto (listCurrentOrders) è del reconcile_worker.
    # 23/09 - guardia d'avvio: armata qui, disarmata SOLO da una ripresa riuscita
    # (se fallisce, il worker della coda non esegue nulla e la riprova).
    if modo_avvio in ("PAPER", "LIVE"):
        _GUARDIA_AVVIO.attiva = True
        _GUARDIA_AVVIO.boot_id = AA.boot_id_ambiente()
        _ripresa_all_avvio()

    try:
        while not interrupted:
            session.restart_requested.clear()
            # 28/09 (cantiere A): arresto ORDINATO chiesto dall'app (file
            # ``arresto_ordinato``): anche parcheggiati in attesa si esce dal
            # ciclo e il ``finally`` chiude i follow come da specifica
            if _AO.richiesto():
                logger.warning("[runner] ARRESTO ORDINATO richiesto dall'app: esco.")
                session.planned_restart = False
                break

            if not only_event:
                # throttle ~15s (fix 17/07): il loop idle ora gira ogni
                # IDLE_FOLLOW_POLL_SEC (~2s) per vedere SUBITO i follow creati
                # via RPC (click Trading) — la risoluzione watchlist (REST
                # listEvents + matcher) resta alla cadenza storica del vecchio
                # sleep(15), mai martellata a 2s.
                _now_mono = time.monotonic()
                if (_now_mono - getattr(session, "_idle_resolve_ts", -1e9)) >= 15.0:
                    session._idle_resolve_ts = _now_mono
                    try:
                        resolve_and_register(rest)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("[runner] resolve_and_register iniziale KO: %s", e)

            try:
                follows = db.list_pending_follows()
            except Exception as e:  # noqa: BLE001 - solo la rete: il resto si rilancia
                _attendi_se_rete("lettura dei follow", e)  # 26/09 crash exit 1
                continue
            if only_event:
                follows = [f for f in follows if f["event_id"] == only_event]
            follows = [f for f in follows if f["event_id"] not in session.finished_events]
            # 25/09: le righe scritte dall'AUTO-FOLLOW non sono follow manuali
            # (niente catalogo intero, niente live_now): i loro mercati entrano
            # dal piano dell'auto-follow qui sotto.
            auto = _auto_attivo()
            if auto is not None:
                follows = [f for f in follows
                           if not (str(f.get("status") or "") == "STREAMING"
                                   and auto.segue_auto(f["event_id"]))]
            # opt-in 17/07: set degli eventi con "Segui live" attivo (record=true)
            # PRIMA di configure_raw — il tee parte gia' col gating giusto.
            try:
                _sync_record_events(session, follows)
            except Exception as e:  # noqa: BLE001 - mai bloccare l'avvio per il gating
                logger.warning("[runner] sync record opt-in KO (ignorato): %s", e)
            # 25/09: senza partite seguite a mano il runner parte lo stesso se
            # l'auto-follow ha mercati (feed o comando di un bot)
            if not follows and not (auto is not None and auto.mercati_auto()):
                # DESKTOP (keep-alive): senza eventi il runner NON esce — resta in
                # attesa (canale locale + board vivi) e ricontrolla ogni 15s: il
                # click "Segui live" nell'app crea il follow e si parte subito.
                # Senza il flag (uso storico da terminale/cron): esce come sempre.
                if os.getenv("LIVE_RUNNER_KEEP_ALIVE", "").strip() == "1":
                    # attesa di aggancio RIDOTTA (fix 17/07 "Trading = streaming
                    # immediato"): il check dei follow è una SELECT leggera →
                    # girare ogni ~2s invece di 15s toglie fino a 13s di latenza
                    # click→ladder a runner idle. Log throttled (~30s): a 2s
                    # spammerebbe. resolve/keepAlive restano alle cadenze storiche.
                    _now_i = time.monotonic()
                    if (_now_i - getattr(session, "_idle_log_ts", -1e9)) >= 30.0:
                        session._idle_log_ts = _now_i
                        logger.info("[runner] nessun evento da streammare: attendo (keep-alive desktop).")
                    # 14/09 — IL BATTITO DEVE DIRE «IL PROCESSO E' VIVO», NON
                    # «la subscription e' su». `heartbeat_worker` e' un
                    # BackgroundWorker e nasce solo dentro `framework.run()`:
                    # finche' il runner resta parcheggiato qui, NESSUNO scrive il
                    # battito. Il 14/09 questo ha fatto credere a tre sessioni che
                    # il runner fosse morto dal 2 settembre — mentre girava, in
                    # attesa di eventi da agganciare. «Vivo ma senza lavoro» e' uno
                    # stato LEGITTIMO e va dichiarato come tale: un indicatore che
                    # grida guasto su un comportamento normale fa ignorare anche i
                    # guasti veri. Chi legge distingue i tre stati cosi':
                    #   battito VECCHIO                      -> runner spento
                    #   battito FRESCO + nessun follow STREAMING -> vivo, in attesa
                    #   battito FRESCO + follow STREAMING        -> in streaming
                    _battito_in_attesa(session, _now_i)
                    # A2 (fix 18/09 sera, reperto del coordinatore) — STESSO motivo del
                    # battito appena sopra: sync_account_worker e' un BackgroundWorker,
                    # vive SOLO dentro framework.run(); qui, parcheggiati in idle SENZA
                    # eventi (lo stato normale ad app aperta), framework non esiste
                    # ancora. Chiamata DIRETTA alla stessa funzione condivisa, stesso
                    # orologio di cadenza (_LAST_ACCOUNT_TS in reconcile_worker.py): mai
                    # una doppia chiamata REST nel passaggio idle->run o viceversa.
                    run_account_sync_if_due(session)
                    # 09/10 (programma del giorno): STESSO motivo anche per il board
                    # (BackgroundWorker): il tabellone parte anche da parcheggiati
                    _attesa_board_e_canale(session)
                    time.sleep(IDLE_FOLLOW_POLL_SEC)
                    # SESSIONE Betfair .it: scade dopo ~20 min di INATTIVITA' —
                    # senza keepAlive periodico il primo Segui live fallirebbe
                    # con INVALID_SESSION. Ogni ~8 min (monotonic, indipendente
                    # dalla cadenza del loop; prima erano 32 giri da 15s).
                    _last_ka = getattr(session, "_idle_ka_ts", None)
                    if _last_ka is None:
                        session._idle_ka_ts = _now_i  # epoca del primo giro idle
                    elif (_now_i - _last_ka) >= 480.0:
                        session._idle_ka_ts = _now_i
                        try:
                            from .auth import keep_alive as _bf_keep_alive
                            _bf_keep_alive(api_client)
                            # la sessione JSON-RPC (rest) è tenuta viva dal
                            # resolve_and_register ogni 15s: nessun re-login (audit 09/09)
                            logger.info("[runner] keepAlive sessione Betfair ok (idle).")
                        except Exception as _ex:  # noqa: BLE001
                            logger.warning("[runner] keepAlive sessione KO: %s", str(_ex)[:120])
                    continue
                logger.warning("[runner] nessun evento da streammare.")
                break

            try:
                _catalog_events(rest, session, follows)
            except Exception as e:  # noqa: BLE001 - solo la rete: il resto si rilancia
                _attendi_se_rete("catalogo mercati (REST)", e)  # 26/09 crash exit 1
                continue
            # 28/09 (cantiere A): i mercati delle partite FINITE non si
            # risottoscrivono alla ricostruzione (prima restavano nella
            # sottoscrizione per tutta la vita del processo)
            market_ids = mercati_manuali_da_sottoscrivere(session)
            con_soldi: Set[str] = set()
            fonti_soldi: Dict[str, int] = {}
            if auto is not None:
                # 25/09: sottoscrizione = manuali + automatici, dentro il tetto
                # della connessione (le automatiche meno prioritarie escono se i
                # manuali sono cresciuti; a ricostruzione il blotter e' vuoto)
                auto.imposta_manuali({
                    ev: ms for ev, ms in session.event_markets.items()
                    if ev not in session.finished_events})
                # 28/09 (cantiere B): i mercati con soldi dentro PRIMA del
                # rientro nel tetto (le loro voci sono protette) e davanti a tutti
                # nel frammento 0
                con_soldi, fonti_soldi = _mercati_con_soldi(
                    mercati_con_ordini_prec, auto,
                    sorted(set(market_ids) | set(auto.mercati_da_sottoscrivere())))
                auto.imposta_con_soldi(con_soldi)
                auto.rientra_nel_tetto()
                market_ids = sorted(set(market_ids) | set(auto.mercati_da_sottoscrivere()))
            if not market_ids:
                if os.getenv("LIVE_RUNNER_KEEP_ALIVE", "").strip() == "1":
                    logger.info("[runner] nessun mercato sottoscrivibile: attendo (keep-alive desktop).")
                    # A2 (fix 18/09 sera): stesso motivo del ramo idle sopra — anche
                    # qui framework non esiste ancora (nessun BackgroundWorker vivo).
                    run_account_sync_if_due(session)
                    _attesa_board_e_canale(session)   # 09/10: board anche da qui
                    time.sleep(15)
                    continue
                logger.warning("[runner] nessun mercato sottoscrivibile (budget?).")
                break

            # 28/09 (cantiere B): il framework nasce col FRAMMENTO 0 (<= un
            # frammento di mercati, prima le partite seguite a mano); gli altri
            # frammenti (connessioni in piu') li apre l'auto-follow a caldo appena
            # lo stream gira: flumine all'avvio aspetta OGNI stream connesso e una
            # connessione rifiutata bloccherebbe tutto il runner. Senza
            # auto-follow il budget resta una connessione (``_capacita_mercati``).
            # 28/09 (A+B): i "manuali" davanti sono quelli VIVI (le partite
            # finite non si risottoscrivono, ``mercati_manuali_da_sottoscrivere``)
            mercati_frammento0 = _frammento0(market_ids, mercati_manuali_da_sottoscrivere(session),
                                             auto, con_soldi, fonti_soldi)
            recorder = MarketRecorderStrategy(
                market_filter=streaming_market_filter(market_ids=mercati_frammento0),
                market_data_filter=streaming_market_data_filter(
                    fields=list(STREAM_FIELDS), ladder_levels=LADDER_DEPTH
                ),
                conflate_ms=STREAM_CONFLATE_MS or None,
                # F1: tee del raw nativo; 28/09: + battito per connessione e
                # nessuna riconnessione dopo la chiusura (frammenti_mercato)
                stream_class=_FR.FrammentoMarketStream,
                context={
                    "data_dir": DATA_DIR,
                    "market_to_event": session.market_to_event,
                    "market_type_by_id": session.market_type_by_id,
                    "event_markets": session.event_markets,
                    "depth": LADDER_DEPTH,
                    # OPT-IN (fix CRITICAL review 17/07): il file curato
                    # <event>.jsonl (il più pesante, quello del Replay) si
                    # scrive SOLO per gli eventi scelti. Getter VIVO: il
                    # toggle a partita in corso è efficace subito.
                    "record_events": lambda: session.record_events,
                },
            )
            session.recorder = recorder
            # opt-in 17/07: il tee raw scrive SOLO gli eventi con record=true
            # (None = colonna assente → registra tutto, comportamento storico).
            configure_raw(DATA_DIR, session.market_to_event, RAW_RECORDING,
                          session.record_events)

            # NB: NON usare market_recording_mode=True → sopprime process_market_book
            # (i book parsati servono a live_now + segnali). Il raw nativo è comunque
            # registrato dal tee nel listener. Il client ordini dipende da LIVE_ORDER_MODE:
            # OFF (default) = order_stream=False, identico ad oggi → nessuna regressione.
            modo_client = _modo_ordini_client(modo_avvio)  # 23/09: mai client a caldo
            client, orders_enabled = build_order_client(api_client, modo_client)
            framework = Flumine(client=client)
            # K1 (26/09): lo stream consegna size/volumi in GBP, il conto e' in EUR.
            # PRIMO middleware: prima del SimulatedMiddleware (paper) e di ogni
            # strategia (recorder -> ladder/live_now/canale, specchio ordini).
            _valuta.monta_su_flumine(framework)
            # F0 (16/09) - UN SOLO processo serve paper E live. In LIVE si affianca al
            # client reale un client SIMULATO: flumine instrada per ORDINE
            # (market.place_order(..., client=...) -> client.execution), quindi le due
            # modalita' convivono senza mai toccarsi. Se il runner NON e' in LIVE il
            # client reale NON viene costruito affatto: la separazione dei soldi veri
            # e' FISICA, non una convenzione (vedi live_order_worker._client_for_mode).
            paper_companion = None
            if modo_client == "LIVE":
                paper_companion = build_paper_companion_client(api_client)
                framework.add_client(paper_companion)
                logger.info(
                    "[runner] F0: client PAPER affiancato al client REALE (%s) - "
                    "le righe 'paper' della coda NON toccano mai l'Exchange",
                    paper_companion.username,
                )
                # 23/09 - saldo riletto dopo ogni ordine REALE / regolazione
                # (una chiamata per evento, ordini simulati ignorati).
                attiva_saldo_su_evento(framework, session)
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
                # 28/09 (cantiere B): STESSO stream del recorder. Col solo
                # market_filter flumine apriva una SECONDA connessione di mercato
                # (market_data_filter di serie != quello del recorder), sulla quale
                # i mercati dell'auto-follow non arrivavano mai
                # (``frammenti_mercato.kwargs_stream_condiviso``).
                live_strategy = LiveTradingStrategy(
                    **_FR.kwargs_stream_condiviso(recorder),
                    session=session, mode=modo_client.lower())
                framework.add_strategy(live_strategy)
                # F0: una strategy PER MODALITA'. In flumine il blotter e' per-strategia
                # (blotter.strategy_orders / get_exposures(strategy, ...)), quindi due
                # istanze separate tengono esposizioni, specchio DB (betfair_live_orders /
                # _positions, che portano la ``mode`` della strategy) e settled di paper e
                # live SEPARATI dentro lo stesso processo. ``name`` DIVERSO obbligatorio:
                # flumine indicizza le strategie per name_hash (Strategies.hashes) e due
                # nomi uguali si sovrascriverebbero nel recupero ordini dallo stream.
                # Stesso market_filter -> flumine RIUSA lo stream esistente
                # (Streams.add_stream): zero connessioni e zero mercati in piu'.
                strategies_by_mode = {modo_client.lower(): live_strategy}
                if paper_companion is not None:
                    paper_strategy = LiveTradingStrategy(
                        **_FR.kwargs_stream_condiviso(recorder),
                        session=session, mode="paper", name="LiveTradingStrategyPaper")
                    framework.add_strategy(paper_strategy)
                    strategies_by_mode["paper"] = paper_strategy
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
                # F0: al worker della coda va la MAPPA modalita'->strategy (sceglie per
                # riga); gli altri worker (risk/xhedge/daily stop/reconcile) restano sulla
                # strategy della modalita' del processo, come prima.
                framework.add_worker(BackgroundWorker(
                    framework, function=_live_order_worker_guardato,  # 23/09: guardia d'avvio
                    interval=LIVE_ORDER_QUEUE_POLL_SEC or 1.0,
                    func_kwargs={"session": session, "strategy": strategies_by_mode},
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
            # 23/09: il worker gira alla cadenza del CANALE (LIVE_LADDER_CANALE_MS,
            # mai < 20 ms); il DB resta a LADDER_PUBLISH_SEC dentro il worker.
            framework.add_worker(BackgroundWorker(
                framework, function=ladder_worker,
                interval=_lcad.stato_della_sessione(
                    session, LADDER_PUBLISH_SEC, LADDER_CANALE_MS).intervallo_worker(),
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
            # A2 (fix 18/09) — saldo del CONTO Betfair SEMPRE (OFF/PAPER/LIVE, come
            # heartbeat_worker sopra): altri bot (Omega/Safe/Mike/tennis, PROCESSI
            # SEPARATI) possono essere LIVE sullo stesso conto mentre il runner
            # calcio e' fermo o in PAPER — il saldo deve aggiornarsi comunque.
            # Tick al ritmo del battito (10s): la cadenza REST reale (20s fissi,
            # 3 chiamate/min) e' garantita DENTRO sync_account_worker, non qui.
            # session.context_api_client e' gia' valorizzato dal login sopra (riga
            # ~1599), a prescindere da LIVE_ORDER_MODE: nessun secondo login.
            framework.add_worker(BackgroundWorker(
                framework, function=sync_account_worker, interval=HEARTBEAT_SEC or 10.0,
                func_kwargs={"session": session}, name="sync_account_worker"))
            # auto-spegnimento (fix 2026-07-08): controlla ogni minuto vita massima
            # e inattività — mai più runner accesi per giorni a martellare Betfair.
            framework.add_worker(BackgroundWorker(
                framework, function=lifecycle_worker, interval=60.0,
                func_kwargs={"session": session}, name="lifecycle_worker"))
            # 28/09 (cantiere A): arresto ordinato dall'app (una stat al secondo)
            framework.add_worker(BackgroundWorker(
                framework, function=arresto_worker, interval=1.0,
                func_kwargs={"session": session}, name="arresto_worker"))
            if auto_subscribe and not only_event:
                # interval BASSO (fix 17/07): il giro del worker è una SELECT
                # leggera su live_follow — la parte REST (resolve watchlist) è
                # throttled DENTRO il worker a WATCHLIST_POLL_SEC. Così un nuovo
                # follow (click Trading) è visto entro ~SUB_WORKER_POLL_SEC.
                framework.add_worker(BackgroundWorker(
                    framework, function=subscription_worker, interval=SUB_WORKER_POLL_SEC or 2.0,
                    func_kwargs={"session": session}, context={"rest": rest}, name="subscription_worker"))

            logger.info("[runner] stream avviato: %d eventi, %d mercati.",
                        len(session.cataloged_events) - len(session.finished_events), len(market_ids))
            # epoca dello stream corrente: serve al rilevamento "stream MAI
            # connesso" del heartbeat_worker (stallo con last_write_ms==0).
            session.stream_started_monotonic = time.monotonic()
            # R-STREAM-1 (26/09): tutti i mercati sottoscritti (anche auto-follow)
            session.stream_market_count = len(market_ids)
            motore = _motore_attivo()
            if motore is not None and orders_enabled:
                motore.aggancia(framework, strategies_by_mode)
            if auto is not None:
                # 28/09: gli "applicati" sono i mercati del frammento 0; il resto
                # lo sottoscrive l'auto-follow sui frammenti in piu'
                auto.aggancia(framework, mercati_frammento0)
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
                    if motore is not None:
                        motore.sgancia()  # framework morto: i comandi si rifiutano
                    delay = session.backoff.next_delay()
                    logger.warning("[runner] retry tra %.0fs (backoff)...", delay)
                    time.sleep(delay)
                    continue  # ricostruisce e ritenta (multi-match)
            finally:
                # 28/09 (cantiere B): prima che il blotter si perda
                mercati_con_ordini_prec = _FR.mercati_con_ordini(framework)
                if motore is not None:
                    motore.sgancia()
                if auto is not None:
                    auto.sgancia()

            if session.shutdown_requested.is_set():
                logger.info("[runner] auto-spegnimento: finalizzo e esco.")
                break
            if session.restart_requested.is_set() and not interrupted:
                logger.info("[runner] ricostruisco la subscription con le nuove partite...")
                continue
            break
    finally:
        # 28/09 (cantiere A): all'uscita ordinata si chiudono SOLO le partite
        # FINITE; quelle ancora vive tornano PENDING e il prossimo runner le
        # riaggancia da solo. Prima si finalizzavano TUTTE (CLOSED): ogni
        # ricambio del processo (vita massima) perdeva i follow dell'utente.
        # R-STREAM-1 (26/09, uscita per stallo) e' ora lo stesso caso generale.
        try:
            chiudi_alla_uscita(session)
        except Exception:  # noqa: BLE001 - uscita: best-effort dichiarato
            logger.exception("[runner] chiusura dei follow all'uscita KO")
        session.close_score_files()
        close_raw()
        auto = _auto_attivo()
        if auto is not None:
            try:
                auto.ferma()
            except Exception:  # noqa: BLE001 - uscita: best-effort dichiarato
                logger.exception("[runner] arresto dell'auto-follow KO")
            # R-28-3 (28/09): nessuna riga automatica resta STREAMING senza un
            # processo che la segue (il prossimo runner le riapre dal feed)
            try:
                auto.chiudi_righe()
            except Exception:  # noqa: BLE001 - uscita: best-effort dichiarato
                logger.exception("[runner] chiusura delle righe auto-follow KO")
            _MOTORE["auto"] = None
        motore = _motore_attivo()
        if motore is not None:
            # 24/09: le scritture DB differite si svuotano prima di uscire
            try:
                motore.scrittore.svuota(5.0)
                motore.ferma()
            except Exception:  # noqa: BLE001 - uscita: best-effort dichiarato
                logger.exception("[runner] arresto del motore ordini KO")
            _MOTORE["motore"] = None
        safe_logout(api_client)

    global _PLANNED_RESTART  # noqa: PLW0603 - letto da _main per l'exit code
    _PLANNED_RESTART = bool(getattr(session, "planned_restart", False))
    return sorted(session.finished_events)


_PLANNED_RESTART = False


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
    if _PLANNED_RESTART:
        logger.info("[runner] ricambio pianificato (vita massima, desktop): exit %d, il watchdog rilancia.",
                    EXIT_PLANNED_RESTART)
        raise SystemExit(EXIT_PLANNED_RESTART)


if __name__ == "__main__":
    _main()
