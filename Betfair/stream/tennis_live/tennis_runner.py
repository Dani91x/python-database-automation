"""tennis_runner.py — runner live TENNIS a STREAM UNICO (proiezioni + hosting bot).

Ottimizzazione dati (requisito esplicito): per ogni evento tennis seguito si apre UNA
SOLA subscription flumine (market_filter = [market_id del MATCH_ODDS]). Su quello stesso
stream:
  * una capture-strategy (costruita da ``_make_capture``) cattura l'ultimo MarketBook →
    alimenta ladder + now;
  * i BOT ARMATI (tennis_scalper/pro/flb/swing) sono aggiunti con lo STESSO
    market_filter dell'evento → flumine li fonde nella STESSA MarketStream (nessuna
    subscription Betfair duplicata, nessun REST extra oltre al feed punteggio IPS).

Come i bot si agganciano allo stream unico
------------------------------------------
flumine raggruppa le strategie per definizione di stream (market_filter + data_filter +
conflate). Capture-strategy e bot di UNO STESSO evento usano un market_filter IDENTICO
(``streaming_market_filter(market_ids=[market_id])``) → una sola MarketStream per evento.
Quando un bot viene armato/disarmato a runtime (tabella ``tennis_bot_control``) il
``bot_control_worker`` richiede un RESTART del framework: il supervisore ricostruisce lo
stream aggiungendo/togliendo i bot, SEMPRE sullo stesso filtro per-evento (mirror del
pattern F3 del runner calcio). Nessuno stream nuovo viene aperto per-bot.

Scrive SOLO tabelle ``tennis_*``. Riusa VERBATIM le strategie tennis, ``tennis_score`` e
il modello ``tennis_winprob`` (import, nessuna modifica).
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from betfairlightweight.filters import (
    streaming_market_data_filter,
    streaming_market_filter,
)
from flumine import Flumine, clients
from flumine import config as flumine_config
from flumine.worker import BackgroundWorker

from ..auth import build_client, safe_logout
from ..recorder import serialize_book
from ..runner_lifecycle import any_follow_alive, uptime_exceeded
from ..single_instance import acquire_single_instance_lock
from ..tennis_scalper.run_tennis_scalper import TENNIS_PARAMS as SCALPER_TENNIS_PARAMS
from ..tennis_scalper.tennis_flb_bot import TennisFLBStrategy
from ..tennis_scalper.tennis_pro_bot import TennisProStrategy
from ..tennis_scalper.tennis_scalper_bot import TennisScalperStrategy
from ..tennis_scalper.tennis_score import (
    TennisScore,
    _rank,
    parse_tennis_scores,
)
from ..tennis_scalper.tennis_swing_bot import TennisSwingStrategy
from ..tennis_scalper.tennis_winprob import estimate_holds, p_match
from . import tennis_db

logger = logging.getLogger(__name__)

TENNIS_EVENT_TYPE_ID = "2"

# --- Config (env DEDICATE al tennis, così nulla è condiviso col calcio) ---
LADDER_DEPTH = int(os.getenv("TENNIS_LADDER_DEPTH", "10"))
LADDER_MAX_LEVELS = int(os.getenv("TENNIS_LADDER_MAX_LEVELS", str(LADDER_DEPTH)))
LADDER_WOM_LEVELS = int(os.getenv("TENNIS_LADDER_WOM_LEVELS", "3"))
LADDER_PUBLISH_SEC = float(os.getenv("TENNIS_LADDER_PUBLISH_SEC", "2.0"))
SCORE_POLL_SEC = float(os.getenv("TENNIS_SCORE_POLL_SEC", "2.0"))
BOT_CONTROL_POLL_SEC = float(os.getenv("TENNIS_BOT_CONTROL_POLL_SEC", "3.0"))
FOLLOW_POLL_SEC = float(os.getenv("TENNIS_FOLLOW_POLL_SEC", "20.0"))
ORDER_POLL_SEC = float(os.getenv("TENNIS_ORDER_POLL_SEC", "1.0"))
STREAM_CONFLATE_MS = int(os.getenv("TENNIS_STREAM_CONFLATE_MS", "0"))
RECENT_POINTS = int(os.getenv("TENNIS_RECENT_POINTS", "12"))

STREAM_FIELDS = ("EX_BEST_OFFERS", "EX_LTP", "EX_TRADED", "EX_TRADED_VOL", "EX_MARKET_DEF")

# whitelist bot → (classe, kwarg dei params, richiede name_to_sel)
_BOT_REGISTRY: Dict[str, Any] = {
    "tennis_scalper": (TennisScalperStrategy, "scalper_params", False),
    "tennis_pro": (TennisProStrategy, "pro_params", True),
    "tennis_flb": (TennisFLBStrategy, "flb_params", False),
    "tennis_swing": (TennisSwingStrategy, "swing_params", False),
}
_ARMED_STATUSES = ("requested", "arming", "armed", "running")


# ---------------------------------------------------------------------------
# Modalità ordini OFF / PAPER / LIVE (DEDICATA al tennis: TENNIS_LIVE_ORDER_MODE)
# ---------------------------------------------------------------------------
def live_order_mode() -> str:
    """OFF | PAPER | LIVE (UPPER), RI-LETTA ad ogni chiamata (downgrade immediato)."""
    return os.getenv("TENNIS_LIVE_ORDER_MODE", "OFF").strip().upper()


def build_order_client(api_client: Any, mode: str) -> "tuple[clients.BetfairClient, bool]":
    """Client flumine per la modalità ordini. Ritorna (client, orders_enabled).

    KILL-SWITCH DI MODALITA' (security C2): è IMPOSSIBILE piazzare ordini REALI se
    ``mode != LIVE``. Solo ``LIVE`` costruisce un client con ``paper_trade=False`` (soldi
    veri). OFF **e** PAPER forzano ``paper_trade=True``: qualunque ``market.place_order``
    (anche di un bot ospitato con ``dry_run=False`` per errore) finisce nella
    ``SimulatedExecution`` di flumine, MAI all'Exchange. In OFF, inoltre, il worker ordini
    NON viene registrato (``orders_enabled=False``) e i bot sono forzati in dry-run
    (vedi ``_instantiate_bot``): tripla difesa.
    """
    mode_u = (mode or "OFF").strip().upper()
    if mode_u == "LIVE":
        return clients.BetfairClient(
            api_client, order_stream=True, paper_trade=False, min_bet_validation=False
        ), True
    if mode_u == "PAPER":
        lat = float(os.getenv("TENNIS_PAPER_LATENCY_MS", "0") or 0)
        if lat > 0:
            flumine_config.place_latency = lat / 1000.0
        return clients.BetfairClient(
            api_client, order_stream=True, paper_trade=True, min_bet_validation=False
        ), True
    # OFF (o modalità sconosciuta): paper_trade FORZATO → nessun ordine reale possibile.
    # orders_enabled=False → il worker ordini non gira (nessun ordine del tutto).
    return clients.BetfairClient(
        api_client, order_stream=True, paper_trade=True, min_bet_validation=False
    ), False


# ---------------------------------------------------------------------------
# Ladder JSON — helper PURI (tennis-local, nessun import dal calcio)
# ---------------------------------------------------------------------------
def _as_levels(raw: Any, max_levels: Optional[int]) -> List[List[float]]:
    out: List[List[float]] = []
    if not raw:
        return out
    seq = raw if (max_levels is None or max_levels <= 0) else raw[:max_levels]
    for lvl in seq:
        try:
            price, size = lvl[0], lvl[1]
            if price is None or float(price) <= 0:
                continue
            out.append([float(price), float(size or 0.0)])
        except (TypeError, ValueError, IndexError):
            continue
    return out


def compute_wom(back: List[List[float]], lay: List[List[float]],
                levels: int = LADDER_WOM_LEVELS) -> Dict[str, float]:
    """Weight of Money: ripartizione % della size back/lay nei primi ``levels`` livelli."""
    n = levels if levels and levels > 0 else 1
    back_sz = sum(s for _, s in back[:n])
    lay_sz = sum(s for _, s in lay[:n])
    total = back_sz + lay_sz
    if total <= 0:
        return {"back_pct": 0.0, "lay_pct": 0.0}
    back_pct = round(back_sz / total * 100.0, 1)
    return {"back_pct": back_pct, "lay_pct": round(100.0 - back_pct, 1)}


def build_ladder_selection(selection_id: Any, runner: Dict[str, Any],
                           name: Optional[str], max_levels: int = LADDER_MAX_LEVELS) -> Dict[str, Any]:
    """Una selezione della ladder dal book serializzato (serialize_book runner)."""
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


def build_ladder_payload(book: Dict[str, Any], names: Dict[str, str],
                         max_levels: int = LADDER_MAX_LEVELS) -> Dict[str, Any]:
    selections = [
        build_ladder_selection(sel_id, r, names.get(str(sel_id)), max_levels)
        for sel_id, r in (book.get("runners") or {}).items()
    ]
    return {
        "updated_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
        "selections": selections,
    }


def ladder_signature(selections: List[Dict[str, Any]]) -> str:
    payload = [
        (
            s["selection_id"], s["ltp"],
            tuple(tuple(lvl) for lvl in s["back"]),
            tuple(tuple(lvl) for lvl in s["lay"]),
            tuple(tuple(lvl) for lvl in s["trd"]),
        )
        for s in sorted(selections, key=lambda x: x["selection_id"])
    ]
    return hashlib.sha1(repr(payload).encode("utf-8")).hexdigest()  # noqa: S324


# ---------------------------------------------------------------------------
# TennisScoreState — derivazione PURA da TennisScore (p1=home, p2=away)
# ---------------------------------------------------------------------------
def _int0(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _looks_tiebreak(ph: Any, pa: Any) -> bool:
    def _num(p: Any) -> bool:
        s = str(p)
        return s.isdigit() and s not in ("0", "15", "30", "40")
    return _num(ph) or _num(pa)


def _set_summary(seq_p1: List[str], seq_p2: List[str], gh: int, ga: int) -> Optional[str]:
    pairs = list(zip(seq_p1, seq_p2))
    if pairs:
        return " ".join(f"{a}-{b}" for a, b in pairs)
    if gh or ga:
        return f"{gh}-{ga}"
    return None


def _win_prob_p1(ts: TennisScore, sh: int, sa: int, gh: int, ga: int,
                 breaks_p1: int, breaks_p2: int) -> Optional[float]:
    """P(vittoria p1) dal modello Markov p_match. None se non calcolabile."""
    try:
        a_serves = ts.server != "away"  # server home o ignoto → assume p1 al servizio
        # estimate_holds: breaks_a = break subiti da A. breaks_b = subiti da B.
        ha, hb = estimate_holds(breaks_p1, breaks_p2, gh, ga)
        return round(p_match(int(sh), int(sa), int(gh), int(ga), bool(a_serves), ha, hb, 3), 4)
    except Exception:  # noqa: BLE001 - il fair value non deve mai rompere il worker
        return None


def tennis_score_state(ts: Optional[TennisScore], *, source: str = "ips") -> Optional[Dict[str, Any]]:
    """TennisScoreState (dict, match 1:1 con lib/tennis.ts) da un TennisScore."""
    if ts is None:
        return None
    sh, sa = ts.sets_home or 0, ts.sets_away or 0
    gh, ga = ts.games_home or 0, ts.games_away or 0
    ph = ts.point_home if ts.point_home is not None else "0"
    pa = ts.point_away if ts.point_away is not None else "0"
    server = 1 if ts.server == "home" else (2 if ts.server == "away" else None)
    bp, spt, gp = ts.pressures()
    raw = ts.raw or {}
    score = raw.get("score") or {}
    home = score.get("home") or {}
    away = score.get("away") or {}
    seq_p1 = [str(x) for x in (home.get("gameSequence") or [])]
    seq_p2 = [str(x) for x in (away.get("gameSequence") or [])]
    breaks_p1 = _int0(home.get("serviceBreaks"))
    breaks_p2 = _int0(away.get("serviceBreaks"))
    return {
        "status": ts.status,
        "sets": {"p1": sh, "p2": sa},
        "games": {"p1": gh, "p2": ga},
        "points": {"p1": str(ph), "p2": str(pa)},
        "server": server,
        "tiebreak": bool((gh == 6 and ga == 6) or _looks_tiebreak(ph, pa)),
        "game_sequence": {"p1": seq_p1, "p2": seq_p2},
        "service_breaks": {"p1": breaks_p1, "p2": breaks_p2},
        "current_set": raw.get("currentSet"),
        "current_game": raw.get("currentGame"),
        "set_summary": _set_summary(seq_p1, seq_p2, gh, ga),
        "pressure": {"break_point": bool(bp), "set_point": bool(spt), "game_point": bool(gp)},
        "win_prob_p1": _win_prob_p1(ts, sh, sa, gh, ga, breaks_p1, breaks_p2),
        "source": source,
        "updated_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
    }


def point_event(prev: Optional[TennisScore], cur: Optional[TennisScore]) -> Optional[Dict[str, Any]]:
    """Un TennisPointEvent dalla transizione prev→cur (best-effort sul vincitore)."""
    if cur is None:
        return None
    winner: Optional[int] = None
    server = 1 if cur.server == "home" else (2 if cur.server == "away" else None)
    if prev is not None:
        dgh = (cur.games_home or 0) - (prev.games_home or 0)
        dga = (cur.games_away or 0) - (prev.games_away or 0)
        dsh = (cur.sets_home or 0) - (prev.sets_home or 0)
        dsa = (cur.sets_away or 0) - (prev.sets_away or 0)
        if dsh > 0 or dgh > 0:
            winner = 1
        elif dsa > 0 or dga > 0:
            winner = 2
        else:
            rh0, ra0 = _rank(prev.point_home), _rank(prev.point_away)
            rh1, ra1 = _rank(cur.point_home), _rank(cur.point_away)
            if None not in (rh0, ra0, rh1, ra1):
                if rh1 > rh0 and ra1 <= ra0:
                    winner = 1
                elif ra1 > ra0 and rh1 <= rh0:
                    winner = 2
    bp, spt, gp = cur.pressures()
    tags = [t for t, on in (("break", bp), ("set", spt), ("game", gp)) if on]
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "set_no": (cur.raw or {}).get("currentSet"),
        "game_no": (cur.raw or {}).get("currentGame"),
        "winner": winner,
        "server": server,
        "tags": tags,
        "score_after": f"{cur.point_home or '0'}-{cur.point_away or '0'}",
    }


# ---------------------------------------------------------------------------
# Strategia di cattura (proiezioni). NON piazza ordini: legge solo il book.
# La classe flumine reale è costruita da ``_make_capture`` a runtime (così il modulo
# resta importabile senza creare strategie né toccare la rete).
# ---------------------------------------------------------------------------
def _make_capture(market_id: str, event_id: str) -> Any:
    """Istanzia una BaseStrategy flumine che cattura i book del market indicato."""
    from flumine import BaseStrategy

    class _Capture(BaseStrategy):
        def __init__(self, **kw: Any) -> None:
            super().__init__(**kw)
            self.event_id = event_id
            self.market_id = market_id
            self._latest: Dict[str, Dict[str, Any]] = {}
            self._lock = threading.Lock()

        def check_market_book(self, market: Any, market_book: Any) -> bool:  # noqa: ARG002
            return True

        def process_market_book(self, market: Any, market_book: Any) -> None:  # noqa: ARG002
            with self._lock:
                self._latest[market_book.market_id] = serialize_book(market_book, LADDER_DEPTH)

        def latest(self) -> Dict[str, Dict[str, Any]]:
            with self._lock:
                return dict(self._latest)

    return _Capture(market_filter=streaming_market_filter(market_ids=[market_id]))


# ---------------------------------------------------------------------------
# Sessione live tennis (persiste tra i restart del supervisore)
# ---------------------------------------------------------------------------
class TennisLiveSession:
    def __init__(self, trading: Any) -> None:
        self.trading = trading
        # event_id -> {market_id, market_type, market_name, name_to_sel, selection_names}
        self.market_meta: Dict[str, Dict[str, Any]] = {}
        self.capture: Dict[str, Any] = {}                 # event_id -> capture strategy
        self.hosted: Dict[tuple, Any] = {}                # (event_id, bot_key) -> strategy
        self.last_score: Dict[str, Optional[TennisScore]] = {}
        self.recent_points: Dict[str, Deque[Dict[str, Any]]] = {}
        self._ladder_sig: Dict[str, str] = {}             # market_id -> firma
        # ordini manuali tracciati: cust_ref -> record {order, trade, mode, event_id, source}
        self.tracked_orders: Dict[str, Any] = {}
        # firma write-on-change dello specchio ordini (manuali + bot): ref -> firma
        self.order_sig_cache: Dict[str, Any] = {}
        # disarm in corso: (event_id, bot_key) -> scadenza monotonic della finestra di
        # chiusura FLAT (il bot resta attivo per appiattire la posizione prima di 'stopped').
        self.stopping_deadline: Dict[tuple, float] = {}
        self.restart_requested = threading.Event()
        # auto-spegnimento (fix 2026-07-08: runner mai più attivi per giorni)
        self.shutdown_requested = threading.Event()
        self.started_monotonic = time.monotonic()

    def reset_streams(self) -> None:
        self.capture.clear()
        self.hosted.clear()
        self.stopping_deadline.clear()

    def points_deque(self, event_id: str) -> Deque[Dict[str, Any]]:
        dq = self.recent_points.get(event_id)
        if dq is None:
            dq = deque(maxlen=RECENT_POINTS)
            self.recent_points[event_id] = dq
        return dq


# ---------------------------------------------------------------------------
# Risoluzione mercato MATCH_ODDS + mappa nomi (come run_tennis_pro._resolve)
# ---------------------------------------------------------------------------
def _resolve_market(trading: Any, market_id: Optional[str], event_id: Optional[str]) -> Dict[str, Any]:
    from betfairlightweight import filters

    filt = (
        filters.market_filter(market_ids=[market_id]) if market_id
        else filters.market_filter(
            event_ids=[event_id], event_type_ids=[TENNIS_EVENT_TYPE_ID],
            market_type_codes=["MATCH_ODDS"],
        )
    )
    cat = trading.betting.list_market_catalogue(
        filter=filt, market_projection=["RUNNER_DESCRIPTION", "EVENT"],
        sort="MAXIMUM_TRADED", max_results=5,
    )
    if not cat:
        raise ValueError("nessun mercato MATCH_ODDS trovato")
    mo = cat[0]
    name_to_sel = {r.runner_name: r.selection_id for r in (mo.runners or [])}
    selection_names = {str(r.selection_id): r.runner_name for r in (mo.runners or [])}
    ev = getattr(getattr(mo, "event", None), "id", None) or event_id
    return {
        "market_id": mo.market_id,
        "event_id": str(ev) if ev else event_id,
        "market_type": "MATCH_ODDS",
        "market_name": "Match Odds",
        "name_to_sel": name_to_sel,
        "selection_names": selection_names,
    }


def _catalog_follow(session: TennisLiveSession, follow: Dict[str, Any]) -> None:
    event_id = follow["event_id"]
    if event_id in session.market_meta:
        return
    try:
        meta = _resolve_market(session.trading, follow.get("market_id"), event_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("[tennis-runner] catalogo KO %s: %s", event_id, e)
        tennis_db.set_tennis_follow_status(event_id, "ERROR", str(e))
        return
    session.market_meta[event_id] = meta


# ---------------------------------------------------------------------------
# Bot: istanziazione (params + dry_run + event_sink → attività/stat)
# ---------------------------------------------------------------------------
def _make_sink(event_id: str, bot_key: str) -> Any:
    def _sink(kind: str, payload: Dict[str, Any]) -> None:
        try:
            tennis_db.write_tennis_bot_activity(event_id, bot_key, kind, dict(payload))
        except Exception as e:  # noqa: BLE001 - la telemetria non deve mai rompere il bot
            logger.debug("[tennis-runner] sink %s/%s KO: %s", event_id, bot_key, e)
    return _sink


def _instantiate_bot(bot_key: str, control: Dict[str, Any], market_id: str,
                     name_to_sel: Dict[str, int], sink: Any,
                     data_filter: Dict[str, Any], mode: str) -> Any:
    """Istanzia un bot AGGANCIATO allo stream unico dell'evento.

    STREAM UNICO (#1): passa lo STESSO ``market_data_filter`` (``data_filter``) della
    capture-strategy. flumine (``Streams.add_stream``) fonde due strategie nella STESSA
    MarketStream solo se COINCIDONO market_filter + market_data_filter + streaming_timeout
    + conflate_ms. La capture usa ``streaming_market_filter(market_ids=[market_id])`` e
    ``data_filter`` (streaming_timeout/conflate = default None): qui usiamo identici →
    UNA sola subscription Betfair per evento (capture + bot).

    KILL-SWITCH DI MODALITA' (#3): se ``mode != LIVE`` il bot è FORZATO in ``dry_run=True``
    (i bot tennis gateano ogni ``market.place_order`` su ``self.dry_run``): impossibile
    piazzare al di fuori di LIVE, a prescindere da ciò che chiede il control.
    """
    cls, params_kw, needs_names = _BOT_REGISTRY[bot_key]
    params = dict(control.get("params") or {})
    params["stake"] = float(control.get("stake") or params.get("stake") or 2.0)
    is_live = (mode or "OFF").strip().upper() == "LIVE"
    # dry-run forzato fuori da LIVE (difesa in profondità oltre al paper_trade del client).
    params["dry_run"] = True if not is_live else bool(control.get("dry_run", True))
    if bot_key == "tennis_scalper":
        # PRESET TENNIS (fix 2026-07-09): senza questa base lo scalper armato dalla UI
        # partiva coi default CALCIO della classe (max_signal_ticks=4 → l'anti-gap blocca
        # OGNI punto tennis che muove 2-6 tick; max_spread_ticks=2, min_size=150,
        # price 1.50-4.6; e in LIVE mancavano le blindature .it size_step/live_min_bet →
        # green-up con size non-multipla di 0,50 RIFIUTATO = posizione scoperta).
        # Base = preset validato del runner standalone (run_tennis_scalper.TENNIS_PARAMS);
        # i valori del control (UI) hanno SEMPRE la precedenza (setdefault).
        for _k, _v in SCALPER_TENNIS_PARAMS.items():
            params.setdefault(_k, _v)
        if not is_live:
            # PAPER/OFF: fill simulati a size ESATTE (mirror di run_tennis_scalper
            # --paper): la granularità .it non esiste in simulazione → green-up esatti.
            params["size_step"] = 0.0
            params["live_min_bet"] = 0.0
    stake = params["stake"]
    cap = stake * (float(params.get("price_max", 6.0)) + 2.0) * 3.0
    kwargs: Dict[str, Any] = {
        "market_filter": streaming_market_filter(market_ids=[market_id]),
        "market_data_filter": data_filter,
        params_kw: params,
        "event_sink": sink,
        "max_selection_exposure": cap,
        "max_order_exposure": cap,
        "max_trade_count": int(1e6),
        "max_live_trade_count": int(1e6),
    }
    if needs_names:
        kwargs["name_to_sel"] = name_to_sel
    return cls(**kwargs)


def _disable_strategy(strat: Any) -> None:
    """Neutralizza SUBITO un bot disarmato: NON deve piazzare nulla nella finestra tra il
    disarm e il teardown dello stream al restart (money-critical: lo status DB 'stopped'
    dev'essere VERITIERO). Difesa multipla, tutta per-istanza (nessuna modifica di classe):
      1) ``dry_run=True`` — i bot tennis gateano ``market.place_order`` su ``self.dry_run``;
      2) tetti di esposizione a 0 — il control nativo ``StrategyExposure`` rifiuta ogni place;
      3) ``check_market_book`` shadowato a False — ``process_market_book`` non verrà più
         invocato (vedi baseflumine._process_market_books), quindi nessuna logica di trading.
    """
    try:
        strat.dry_run = True
    except Exception as e:  # noqa: BLE001
        logger.debug("[tennis-runner] disable dry_run KO: %s", e)
    for attr in ("max_order_exposure", "max_selection_exposure", "max_market_exposure"):
        try:
            setattr(strat, attr, 0.0)
        except Exception:  # noqa: BLE001
            pass
    try:
        strat.check_market_book = lambda *a, **k: False  # type: ignore[assignment]
    except Exception as e:  # noqa: BLE001
        logger.debug("[tennis-runner] disable hook KO: %s", e)
    strat._tennis_disabled = True


def _desired_controls(event_id: str) -> Dict[str, Dict[str, Any]]:
    rows = tennis_db.list_tennis_bot_controls(event_id, statuses=list(_ARMED_STATUSES))
    return {r["bot_key"]: r for r in rows if r.get("bot_key") in _BOT_REGISTRY}


# ---------------------------------------------------------------------------
# Disarm con chiusura FLAT (contratto tennis_bots.sql: 'stopping' → flat → 'stopped')
# ---------------------------------------------------------------------------
# Finestra concessa al bot per appiattire la posizione dopo il disarm. Scaduta la
# finestra senza flat, lo stato diventa 'error' (MAI uno 'stopped' bugiardo).
_STOPPING_GRACE_S = 45.0

# Stati flumine di un ordine ancora VIVO sul book (tutto il resto è terminale).
_LIVE_ORDER_STATUSES = frozenset({"PENDING", "CANCELLING", "UPDATING", "REPLACING", "EXECUTABLE"})


def _stopping_controls(event_id: str) -> Dict[str, Dict[str, Any]]:
    rows = tennis_db.list_tennis_bot_controls(event_id, statuses=["stopping"])
    return {r["bot_key"]: r for r in rows if r.get("bot_key") in _BOT_REGISTRY}


def _strategy_is_flat(flumine: Any, strat: Any) -> bool:
    """True se la strategy non ha né ordini VIVI sul book né esposizione MATCHED
    sbilanciata, su nessun mercato del framework. Fonte: SOLO il blotter flumine
    (autoritativo) — mai numeri ricalcolati a mano. In caso di dubbio (blotter non
    leggibile) ritorna False: mai dichiarare flat una posizione non verificata."""
    try:
        for market in flumine.markets:
            blotter = getattr(market, "blotter", None)
            if blotter is None:
                continue
            try:
                orders = blotter.strategy_orders(strat) or []
            except Exception:  # noqa: BLE001 - blotter illeggibile → NON è flat verificato
                return False
            lookups = set()
            for o in orders:
                st = getattr(o, "status", None)
                st_name = getattr(st, "name", None) or (str(st) if st is not None else "")
                if st_name in _LIVE_ORDER_STATUSES:
                    return False  # un ordine ancora sul book: non flat
                sel = getattr(o, "selection_id", None)
                if sel is None:
                    continue
                hcap = getattr(o, "handicap", 0.0) or 0.0
                lookups.add((getattr(market, "market_id", None), int(sel), float(hcap)))
            for lookup in lookups:
                try:
                    exp = blotter.get_exposures(strat, lookup)
                except Exception:  # noqa: BLE001
                    return False
                if not isinstance(exp, dict):
                    return False
                w = float(exp.get("matched_profit_if_win") or 0.0)
                l = float(exp.get("matched_profit_if_lose") or 0.0)
                if abs(w - l) >= 0.01:
                    return False  # posizione matched aperta (sbilancio ≥ 1 cent)
    except Exception:  # noqa: BLE001
        return False
    return True


# ---------------------------------------------------------------------------
# Worker: ladder LIVE (write-on-change) → tennis_live_ladder
# ---------------------------------------------------------------------------
def ladder_worker(context: dict, flumine: Any, session: TennisLiveSession) -> None:  # noqa: ARG001
    for event_id, cap in list(session.capture.items()):
        meta = session.market_meta.get(event_id) or {}
        names = meta.get("selection_names", {})
        for mid, book in cap.latest().items():
            if not book:
                continue
            try:
                payload = build_ladder_payload(book, names, LADDER_MAX_LEVELS)
                sig = (book.get("status") or "") + "|" + ladder_signature(payload["selections"])
            except Exception as e:  # noqa: BLE001
                logger.debug("[tennis-ladder] build KO %s: %s", mid, e)
                continue
            if session._ladder_sig.get(mid) == sig:
                continue
            row = {
                "event_id": event_id,
                "market_id": mid,
                "market_type": meta.get("market_type"),
                "market_name": meta.get("market_name"),
                "status": book.get("status"),
                "ladder": payload,
            }
            # A7: push locale immediato; DB throttled a 2s/mercato col desktop attivo
            # (write-on-change invariato senza desktop) — stesso schema del calcio.
            from .. import local_channel as _lc
            if _lc.channel_active():
                _lc.publish("ladder", row)
                now_m = time.monotonic()
                ts_map = getattr(session, "_ladder_db_ts", None)
                if ts_map is None:
                    ts_map = {}
                    session._ladder_db_ts = ts_map
                if now_m - ts_map.get(mid, 0.0) < 2.0:
                    session._ladder_sig[mid] = sig
                    continue
                ts_map[mid] = now_m
            try:
                tennis_db.upsert_tennis_ladder(row)
                session._ladder_sig[mid] = sig
            except Exception as e:  # noqa: BLE001
                logger.warning("[tennis-ladder] upsert KO %s: %s", mid, e)


# ---------------------------------------------------------------------------
# Worker: punteggio IPS + now (UNA poll IPS per evento → score+state+points)
# ---------------------------------------------------------------------------
def _now_selections(book: Dict[str, Any], names: Dict[str, str]) -> List[Dict[str, Any]]:
    sels = []
    for sel_id, r in (book.get("runners") or {}).items():
        back = r.get("b") or []
        lay = r.get("l") or []
        sels.append({
            "selection_id": int(sel_id),
            "name": names.get(str(sel_id)),
            "back": back[0][0] if back else None,
            "lay": lay[0][0] if lay else None,
            "ltp": r.get("ltp"),
        })
    return sels


def _build_now_state(session: TennisLiveSession, event_id: str) -> "tuple[Dict[str, Any], bool, str]":
    meta = session.market_meta.get(event_id) or {}
    cap = session.capture.get(event_id)
    latest = cap.latest() if cap is not None else {}
    markets_out = []
    inplay = False
    status = "SUSPENDED"
    for mid, book in latest.items():
        inplay = inplay or bool(book.get("inplay"))
        status = book.get("status") or status
        markets_out.append({
            "market_id": mid,
            "market_type": meta.get("market_type"),
            "market_name": meta.get("market_name"),
            "status": book.get("status"),
            "selections": _now_selections(book, meta.get("selection_names", {})),
        })
    state = {
        "markets": markets_out,
        "order_mode": live_order_mode(),
        "updated_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
    }
    return state, inplay, status


def score_and_now_worker(context: dict, flumine: Any, session: TennisLiveSession) -> None:  # noqa: ARG001
    trading = session.trading
    for event_id in list(session.market_meta.keys()):
        # UNA poll IPS per evento (unico REST oltre allo stream)
        ts: Optional[TennisScore] = None
        try:
            raw = trading.in_play_service.get_scores(
                event_ids=[int(event_id)] if str(event_id).isdigit() else [event_id],
                lightweight=True,
            )
            ts = parse_tennis_scores(raw, event_id)
        except Exception as e:  # noqa: BLE001 - il feed non deve mai rompere il worker
            logger.debug("[tennis-score] get_scores KO %s: %s", event_id, e)

        # alimenta i bot ospitati per l'evento (riuso VERBATIM: usano .score/.point_pressure).
        # snapshot con list(...): bot_control_worker può mutare session.hosted da un altro thread.
        for (ev, _bk), strat in list(session.hosted.items()):
            if ev != event_id:
                continue
            if hasattr(strat, "score"):
                strat.score = ts
            if hasattr(strat, "point_pressure"):
                strat.point_pressure = bool(ts.point_pressure) if ts is not None else False

        # punto-per-punto (write-on-change della score key)
        prev = session.last_score.get(event_id)
        if ts is not None and (prev is None or prev.key() != ts.key()):
            evt = point_event(prev, ts)
            if evt is not None:
                session.points_deque(event_id).append(evt)
        session.last_score[event_id] = ts

        state, inplay, status = _build_now_state(session, event_id)
        score_state = tennis_score_state(ts)
        points = list(session.points_deque(event_id))
        try:
            tennis_db.upsert_tennis_now(event_id, inplay, status, state, score_state, points)
        except Exception as e:  # noqa: BLE001
            logger.warning("[tennis-now] upsert KO %s: %s", event_id, e)


# ---------------------------------------------------------------------------
# Worker: controllo bot (arm/disarm) + heartbeat/stat → tennis_bot_control
# ---------------------------------------------------------------------------
def bot_control_worker(context: dict, flumine: Any, session: TennisLiveSession) -> None:  # noqa: ARG001
    need_restart = False
    now_mono = time.monotonic()
    for event_id in list(session.market_meta.keys()):
        desired = _desired_controls(event_id)
        stopping = _stopping_controls(event_id)
        # nuovi bot richiesti non ancora ospitati → restart per agganciarli allo stream
        for bot_key in desired:
            if (event_id, bot_key) not in session.hosted:
                need_restart = True
        # DISARM (contratto tennis_bots.sql: 'stopping' → chiusura FLAT → 'stopped').
        # Fix review CRITICAL: prima di questo fix lo stato 'stopping' era ignorato e il
        # bot veniva congelato all'istante con la posizione APERTA (mentre la UI diceva
        # "chiusura flat"). Ora:
        #   * bot con force_flat (scalper): resta ATTIVO con force_flat=True → cancella i
        #     resting e appiattisce da solo; quando il blotter lo conferma flat (o scade
        #     la finestra) si disabilita e lo stato diventa 'stopped'/'error' VERITIERO.
        #   * bot senza chiusura autonoma: disabilitato subito, ma lo stato finale dice
        #     la VERITÀ ('stopped' solo se flat; altrimenti 'error' con avviso).
        for (ev, bot_key) in list(session.hosted.keys()):
            if ev != event_id or bot_key in desired:
                continue
            strat = session.hosted[(ev, bot_key)]
            key = (ev, bot_key)
            if bot_key in stopping and not getattr(strat, "_tennis_disabled", False):
                deadline = session.stopping_deadline.get(key)
                if deadline is None:
                    if hasattr(strat, "force_flat"):
                        # il bot sa appiattirsi da solo: chiediglielo e lascialo lavorare.
                        strat.force_flat = True
                        session.stopping_deadline[key] = now_mono + _STOPPING_GRACE_S
                        try:
                            tennis_db.write_tennis_bot_activity(
                                ev, bot_key, "disarm_flat",
                                {"note": f"force_flat attivato; finestra {int(_STOPPING_GRACE_S)}s"},
                            )
                        except Exception:  # noqa: BLE001 - attività best-effort
                            pass
                        continue
                    # bot senza chiusura autonoma: non può appiattirsi → disabilita subito
                    # e scrivi uno stato finale VERITIERO qui sotto (deadline "già scaduta").
                    session.stopping_deadline[key] = now_mono
                    deadline = now_mono
                flat = _strategy_is_flat(flumine, strat)
                if not flat and now_mono < deadline:
                    continue  # chiusura in corso: lascia lavorare il bot fino alla finestra
                _disable_strategy(strat)
                session.stopping_deadline.pop(key, None)
                if flat:
                    tennis_db.set_tennis_bot_status(ev, bot_key, "stopped", stopped=True)
                else:
                    tennis_db.set_tennis_bot_status(
                        ev, bot_key, "error", stopped=True,
                        error=(f"disarm: posizione NON flat dopo {int(_STOPPING_GRACE_S)}s — "
                               "chiudi manualmente su Betfair/ladder e verifica l'esposizione"),
                    )
                need_restart = True
                continue
            # non in 'stopping' (riga rimossa/stato cambiato fuori contratto): comportamento
            # conservativo — disabilita e scrivi lo stato in base al flat REALE.
            if not getattr(strat, "_tennis_disabled", False):
                flat = _strategy_is_flat(flumine, strat)
                _disable_strategy(strat)
                session.stopping_deadline.pop(key, None)
                if flat:
                    tennis_db.set_tennis_bot_status(event_id, bot_key, "stopped", stopped=True)
                else:
                    tennis_db.set_tennis_bot_status(
                        event_id, bot_key, "error", stopped=True,
                        error="bot rimosso con posizione NON flat — verifica manuale su Betfair",
                    )
                need_restart = True
        # righe 'stopping' di bot NON più ospitati (es. restart avvenuto durante il disarm):
        # nessuno può più chiuderle → stato finale onesto, mai 'stopping' per sempre.
        for bot_key in stopping:
            if (event_id, bot_key) not in session.hosted:
                tennis_db.set_tennis_bot_status(
                    event_id, bot_key, "stopped", stopped=True,
                    error=("disarm durante un riavvio dello stream: chiusura flat NON "
                           "verificata — controlla le posizioni su Betfair"),
                )
        # heartbeat + stat SOLO dei bot ancora desiderati e non disabilitati: un bot appena
        # disarmato resta in session.hosted fino al restart, ma il suo status DB dev'essere
        # 'stopped' (fix #2) — NON va sovrascritto con 'running' dall'heartbeat.
        for (ev, bot_key), strat in list(session.hosted.items()):
            if ev != event_id or bot_key not in desired or getattr(strat, "_tennis_disabled", False):
                continue
            try:
                tennis_db.set_tennis_bot_status(
                    event_id, bot_key, "running",
                    stats=getattr(strat, "stats", None), heartbeat=True,
                )
            except Exception as e:  # noqa: BLE001
                logger.debug("[tennis-runner] heartbeat %s/%s KO: %s", event_id, bot_key, e)
    if need_restart:
        session.restart_requested.set()
        _stop_framework(flumine)


# ---------------------------------------------------------------------------
# AUTO-SPEGNIMENTO (fix incidente 2026-07-08: runner attivi per giorni)
# ---------------------------------------------------------------------------
_TENNIS_MAX_HOURS = float(os.getenv("TENNIS_RUNNER_MAX_HOURS", "18"))
_TENNIS_IDLE_EXIT_MIN = float(os.getenv("TENNIS_RUNNER_IDLE_EXIT_MIN", "45"))
_TENNIS_LOCK_PORT = int(os.getenv("TENNIS_RUNNER_LOCK_PORT", "47312"))
_TENNIS_STALE_HOURS = 5.0  # un match tennis può durare ben oltre le 3h del calcio
_INSTANCE_LOCK = None      # socket del lock di singola istanza (referenza viva)


def _tennis_lifecycle_blockers(flumine: Any, session: TennisLiveSession) -> Optional[str]:
    """Motivo per cui NON è sicuro spegnersi (None = via libera). Il denaro viene PRIMA
    del comfort: bot ospitati ancora attivi, disarm in corso (chiusura flat da
    completare) o ordini VIVI nel blotter = si resta accesi. In dubbio: accesi."""
    if session.stopping_deadline:
        return "disarm in corso (chiusura flat da completare)"
    for (ev, bot_key), strat in session.hosted.items():
        if not getattr(strat, "_tennis_disabled", False):
            return f"bot attivo: {bot_key}@{ev}"
    try:
        for market in flumine.markets:
            blotter = getattr(market, "blotter", None)
            live = list(getattr(blotter, "live_orders", None) or []) if blotter is not None else []
            if live:
                return f"{len(live)} ordini vivi sul mercato {getattr(market, 'market_id', '?')}"
    except Exception:  # noqa: BLE001
        return "blotter non leggibile (prudenza: resto acceso)"
    return None


def lifecycle_worker(context: dict, flumine: Any, session: TennisLiveSession) -> None:  # noqa: ARG001
    """Spegne il runner tennis quando non serve più (vita massima o inattività).

    GUARDIE MONEY-CRITICAL su ENTRAMBI i trigger (fix review CRITICAL): MAI spegnere
    con un bot attivo, un disarm in corso o ordini vivi nel blotter. In dubbio
    (DB/blotter illeggibili) resta acceso.
    """
    if session.shutdown_requested.is_set():
        return
    reason: Optional[str] = None
    if uptime_exceeded(session.started_monotonic, time.monotonic(), _TENNIS_MAX_HOURS):
        reason = f"vita massima {_TENNIS_MAX_HOURS:.0f}h raggiunta"
    elif _TENNIS_IDLE_EXIT_MIN > 0:
        try:
            follows = tennis_db.list_pending_tennis_follows()
        except Exception as e:  # noqa: BLE001 - DB illeggibile: non spegnere al buio
            logger.debug("[tennis-lifecycle] follows KO (resto acceso): %s", e)
            return
        if not any_follow_alive(follows, imminent_min=_TENNIS_IDLE_EXIT_MIN,
                                stale_hours=_TENNIS_STALE_HOURS):
            reason = (f"nessun match in corso o in partenza entro "
                      f"{_TENNIS_IDLE_EXIT_MIN:.0f} min")
    if reason is None:
        return
    blocker = _tennis_lifecycle_blockers(flumine, session)
    if blocker is not None:
        logger.warning("[tennis-lifecycle] spegnimento RINVIATO (%s): %s.", reason, blocker)
        return
    logger.warning("[tennis-lifecycle] AUTO-SPEGNIMENTO runner tennis: %s.", reason)
    session.shutdown_requested.set()
    _stop_framework(flumine)


def follow_worker(context: dict, flumine: Any, session: TennisLiveSession) -> None:  # noqa: ARG001
    try:
        follows = tennis_db.list_pending_tennis_follows()
    except Exception as e:  # noqa: BLE001
        logger.warning("[tennis-follow] list KO: %s", e)
        return
    new = [f for f in follows if f["event_id"] not in session.market_meta]
    if new:
        logger.info("[tennis-follow] %d nuovi eventi → ricostruzione stream.", len(new))
        session.restart_requested.set()
        _stop_framework(flumine)


def _stop_framework(flumine: Any) -> None:
    """Ferma DAVVERO ``framework.run()`` per il restart dello stream.

    VERIFICA vs flumine 2.13.11 (flumine/flumine.py::run): il loop ``while True`` esce SOLO
    quando dalla ``handler_queue`` viene estratto un evento di tipo TERMINATOR (EventType.
    TERMINATOR → ``break``). Impostare ``_running=False`` NON interrompe nulla (``_running``
    non è mai testato nel loop). Perciò accodiamo un ``TerminationEvent`` (QUEUE_TYPE=HANDLER):
    al prossimo giro il loop lo estrae e fa ``break`` → ``__exit__`` chiude worker/stream
    puliti → ``setup_and_run`` ricostruisce lo stream (arm/disarm/follow diventano REALI).
    """
    try:
        from flumine.events.events import TerminationEvent

        flumine._running = False  # noqa: SLF001 - coerenza di stato (non basta a fermare run())
        flumine.handler_queue.put(TerminationEvent(flumine))
    except Exception as e:  # noqa: BLE001
        logger.warning("[tennis-runner] stop framework KO: %s", e)


# ---------------------------------------------------------------------------
# Supervisore: costruisce e (ri)avvia lo stream unico per-evento
# ---------------------------------------------------------------------------
def _announce_order_mode(mode: str) -> None:
    """Banner FEDELE alla garanzia reale (fix #3): solo LIVE piazza ordini veri; OFF e PAPER
    forzano ``paper_trade=True`` nel client → soldi veri IMPOSSIBILI fuori da LIVE."""
    banner = {
        "LIVE": "*** LIVE *** ordini REALI (soldi veri) — unica modalità che piazza sull'Exchange",
        "PAPER": "PAPER — ordini SIMULATI (paper_trade forzato, mai soldi veri)",
        "OFF": "OFF — nessun ordine (worker ordini spento, bot in dry-run, client paper_trade)",
    }.get(mode.upper(), f"{mode} — sconosciuta (trattata come OFF, nessun ordine reale)")
    logger.info("[tennis-runner] MODALITA' ORDINI: %s", banner)


def setup_and_run(only_event: Optional[str] = None, auto_follow: bool = True) -> List[str]:
    trading = build_client(login=True)
    session = TennisLiveSession(trading)
    session.context_api_client = trading  # per board_worker (REST leggero)
    # A7 — canale LOCALE desktop (bind SOLO 127.0.0.1); best-effort come il calcio.
    from .. import local_channel as _lc
    _ch = _lc.start_channel(int(os.getenv("TENNIS_LOCAL_WS_PORT", "47332")), "tennis")
    if _ch is not None:
        _ch.set_hello(mode=live_order_mode())
    interrupted = False
    _announce_order_mode(live_order_mode())
    try:
        while not interrupted:
            session.restart_requested.clear()
            follows = tennis_db.list_pending_tennis_follows()
            if only_event:
                follows = [f for f in follows if f["event_id"] == only_event]
            if not follows:
                logger.warning("[tennis-runner] nessun evento tennis da streammare.")
                break

            session.market_meta.clear()
            session.reset_streams()
            for f in follows:
                _catalog_follow(session, f)
            if not session.market_meta:
                logger.warning("[tennis-runner] nessun mercato sottoscrivibile.")
                break

            mode = live_order_mode()
            client, orders_enabled = build_order_client(trading, mode)
            data_filter = streaming_market_data_filter(
                fields=list(STREAM_FIELDS), ladder_levels=LADDER_DEPTH
            )
            framework = Flumine(client=client)

            for event_id, meta in session.market_meta.items():
                cap = _make_capture(meta["market_id"], event_id)
                cap.market_data_filter = data_filter
                session.capture[event_id] = cap
                framework.add_strategy(cap)
                for bot_key, ctrl in _desired_controls(event_id).items():
                    tennis_db.set_tennis_bot_status(event_id, bot_key, "arming")
                    sink = _make_sink(event_id, bot_key)
                    try:
                        bot = _instantiate_bot(
                            bot_key, ctrl, meta["market_id"], meta["name_to_sel"], sink,
                            data_filter, mode,
                        )
                    except Exception as e:  # noqa: BLE001
                        logger.warning("[tennis-runner] arm KO %s/%s: %s", event_id, bot_key, e)
                        tennis_db.set_tennis_bot_status(event_id, bot_key, "error", error=str(e))
                        continue
                    framework.add_strategy(bot)
                    # VERIFICA STREAM UNICO (#1): dopo add_strategy, se il bot avesse aperto una
                    # subscription propria avrebbe stream_ids diversi da quelli della capture.
                    # Condividendo la MarketStream (stesso filtro+data_filter) gli stream_ids
                    # coincidono: una sola subscription Betfair per evento.
                    if set(bot.stream_ids) != set(cap.stream_ids):
                        logger.error(
                            "[tennis-runner] STREAM DUPLICATO %s/%s: bot=%s capture=%s "
                            "(market_data_filter non coincide?)",
                            event_id, bot_key, list(bot.stream_ids), list(cap.stream_ids),
                        )
                    session.hosted[(event_id, bot_key)] = bot
                    tennis_db.set_tennis_bot_status(event_id, bot_key, "running", started=True)

            framework.add_worker(BackgroundWorker(
                framework, function=ladder_worker, interval=LADDER_PUBLISH_SEC or 1.0,
                func_kwargs={"session": session}, name="tennis_ladder"))
            from ..board_worker import board_worker as _board
            framework.add_worker(BackgroundWorker(
                framework, function=_board, interval=float(os.getenv("LIVE_BOARD_POLL_SEC", "10.0")),
                func_kwargs={"session": session, "event_type_id": "2"},
                name="tennis_board"))
            framework.add_worker(BackgroundWorker(
                framework, function=score_and_now_worker, interval=SCORE_POLL_SEC or 2.0,
                func_kwargs={"session": session}, name="tennis_score_now"))
            framework.add_worker(BackgroundWorker(
                framework, function=bot_control_worker, interval=BOT_CONTROL_POLL_SEC or 3.0,
                func_kwargs={"session": session}, name="tennis_bot_control"))
            if orders_enabled:
                from .tennis_live_order_worker import (
                    positions_worker,
                    tennis_live_order_worker,
                )
                framework.add_worker(BackgroundWorker(
                    framework, function=tennis_live_order_worker, interval=ORDER_POLL_SEC or 1.0,
                    func_kwargs={"session": session}, name="tennis_orders"))
                # posizioni/esposizioni (#7): esposizione per selezione dal blotter flumine →
                # tennis_live_positions (senza aprire alcuna subscription: legge il blotter).
                framework.add_worker(BackgroundWorker(
                    framework, function=positions_worker, interval=ORDER_POLL_SEC or 1.0,
                    func_kwargs={"session": session}, name="tennis_positions"))
            if auto_follow and not only_event:
                framework.add_worker(BackgroundWorker(
                    framework, function=follow_worker, interval=FOLLOW_POLL_SEC or 20.0,
                    func_kwargs={"session": session}, name="tennis_follow"))
            # auto-spegnimento (fix 2026-07-08): vita massima + inattività, MAI con
            # bot attivi o disarm in corso.
            framework.add_worker(BackgroundWorker(
                framework, function=lifecycle_worker, interval=60.0,
                func_kwargs={"session": session}, name="tennis_lifecycle"))

            for event_id in session.market_meta:
                tennis_db.set_tennis_follow_status(event_id, "STREAMING")
            logger.info("[tennis-runner] stream avviato: %d eventi, %d bot ospitati.",
                        len(session.market_meta), len(session.hosted))
            try:
                framework.run()
            except KeyboardInterrupt:
                logger.info("[tennis-runner] interruzione richiesta.")
                interrupted = True
            except Exception as e:  # noqa: BLE001
                logger.exception("[tennis-runner] errore framework.run: %s", e)
                if only_event:
                    interrupted = True
                else:
                    time.sleep(5.0)
                    continue
            if session.shutdown_requested.is_set():
                logger.info("[tennis-runner] auto-spegnimento: esco.")
                break
            if session.restart_requested.is_set() and not interrupted:
                logger.info("[tennis-runner] ricostruzione stream…")
                continue
            break
    finally:
        safe_logout(trading)
    return sorted(session.market_meta.keys())


def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Runner live TENNIS (stream unico)")
    ap.add_argument("--event", default=None, help="streamma solo questo event_id")
    ap.add_argument("--no-auto-follow", action="store_true", help="niente ri-aggancio dinamico")
    args = ap.parse_args()
    # SINGOLA ISTANZA (fix 2026-07-08): la seconda istanza esce subito.
    global _INSTANCE_LOCK  # noqa: PLW0603 - referenza viva per tutta la vita del processo
    _INSTANCE_LOCK = acquire_single_instance_lock(_TENNIS_LOCK_PORT, "tennis-runner")
    done = setup_and_run(only_event=args.event, auto_follow=not args.no_auto_follow)
    logger.info("[tennis-runner] terminato. Eventi: %s", done)


if __name__ == "__main__":
    _main()
