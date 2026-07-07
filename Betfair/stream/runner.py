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
    RAW_RECORDING,
    RISK_ENGINE_POLL_SEC,
    SAFE_MARKET_THRESHOLD,
    SCORE_POLL_SEC,
    SIGNAL_MIN_EDGE,
    SIGNAL_MIN_LIQUIDITY,
    SIGNALS_ENABLED,
    STREAM_CONFLATE_MS,
    STREAM_FIELDS,
    WATCHLIST_POLL_SEC,
    XHEDGE_POLL_SEC,
)
from .engine.live_trading_strategy import LiveTradingStrategy
from .live_order_worker import live_order_worker
from .risk_engine_worker import risk_engine_worker
from .trading.controls import LiveExposureControl, LiveRateControl
from .xhedge_worker import xhedge_worker
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
    interrupted = False

    # Annuncia UNA volta la modalità ordini (il banner nei log + alert se PAPER/LIVE).
    # I restart F3 ricostruiscono il framework ma non ri-annunciano (niente spam alert).
    _announce_order_mode(LIVE_ORDER_MODE, LIVE_ORDER_MODE.strip().upper() in ("PAPER", "LIVE"))

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
            if auto_subscribe and not only_event:
                framework.add_worker(BackgroundWorker(
                    framework, function=subscription_worker, interval=WATCHLIST_POLL_SEC,
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
    # NB: l'endpoint HTTP quote/ordini (8787) NON è ospitato qui: vive solo in
    # start_order_server.py (aggiorna_quote_betfair.bat). Così questo runner e il
    # server quote/ordini possono girare INSIEME senza contendersi la porta.
    done = setup_and_run(only_event=args.event, auto_subscribe=not args.no_auto_subscribe)
    logger.info("[runner] terminato. Eventi finalizzati: %s", done)


if __name__ == "__main__":
    _main()
