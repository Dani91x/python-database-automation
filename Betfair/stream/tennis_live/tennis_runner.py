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

25/09 - ISCRIZIONE E ARMAMENTO A CALDO (``iscrizione_a_caldo``, interruttore
``TENNIS_ISCRIZIONE_A_CALDO``, acceso di serie): con il framework vivo una partita
nuova entra con un nuovo ``marketSubscription`` sulla STESSA connessione e i suoi
bot si armano nel framework che gira (``_allinea_follow_a_caldo``,
``_arma_a_caldo``); nessuna ricostruzione, quindi nessun rinvio per i bot in
posizione. La ricostruzione resta per: avvio/ripresa del runner, errore di
``framework.run``, lista dei follow vuota (verso l'attesa), interruttore spento.

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

from .. import avvio_app as _aa
from .. import ladder_canale as _lcad
from ..auth import build_client, safe_logout
from ..recorder import serialize_book
from .. import valuta as _valuta
from ..runner_lifecycle import any_follow_alive, uptime_exceeded
from ..runner_lifecycle import (
    VERDETTO_ATTENDI,
    VERDETTO_GUARITO,
    e_errore_di_rete,
    effective_stall_seconds,
    raw_stall_seconds,
    stall_restart_due,
    verdetto_post_ricostruzione,
)
from ..single_instance import acquire_single_instance_lock
from ..tennis_scalper.run_tennis_scalper import TENNIS_PARAMS as SCALPER_TENNIS_PARAMS
from ..tennis_scalper.tennis_flb_bot import TennisFLBStrategy
from ..tennis_scalper import superficie as _SUP
from ..tennis_scalper.tennis_pro_bot import TennisProStrategy
from ..tennis_scalper.tennis_scalper_bot import TennisScalperStrategy
from ..tennis_scalper.tennis_score import (
    TennisScore,
    _rank,
    parse_tennis_scores,
)
from ..tennis_scalper.tennis_swing_bot import TennisSwingStrategy
from ..tennis_scalper.tennis_winprob import estimate_holds, p_match
from ..runner_lifecycle import EXIT_PLANNED_RESTART
from ..scores.betfair_inplay import BetfairInPlayProvider
from ..scores.scan_feed import ScanFeedScoreProvider
from . import auto_mode as _AM
from . import canale_bot_tennis as _CBT
from . import chiusura_manuale as _cm
from . import esecutore_tennis as _ET
from . import guardie_tennis as _gt
from . import iscrizione_a_caldo as _IAC
from . import tennis_db
from .paper_execution import install_fresh_delay_execution
from .tennis_recorder import RAW_TEE, TennisRecMarketStream, sync_record_flags

logger = logging.getLogger(__name__)

TENNIS_EVENT_TYPE_ID = "2"

# --- Config (env DEDICATE al tennis, così nulla è condiviso col calcio) ---
LADDER_DEPTH = int(os.getenv("TENNIS_LADDER_DEPTH", "10"))
LADDER_MAX_LEVELS = int(os.getenv("TENNIS_LADDER_MAX_LEVELS", str(LADDER_DEPTH)))
LADDER_WOM_LEVELS = int(os.getenv("TENNIS_LADDER_WOM_LEVELS", "3"))
LADDER_PUBLISH_SEC = float(os.getenv("TENNIS_LADDER_PUBLISH_SEC", "2.0"))
# 23/09: cadenza (ms) del ladder sul CANALE locale 47332 (0 = a ogni book nuovo,
# vuoto/illeggibile/negativo -> 200). Il DB resta a LADDER_PUBLISH_SEC. Vedi
# ladder_canale.py e LIVE_LADDER_CANALE_MS (calcio) in config_stream.py.
LADDER_CANALE_MS = _lcad.canale_ms_env("TENNIS_LADDER_CANALE_MS", 200)
SCORE_POLL_SEC = float(os.getenv("TENNIS_SCORE_POLL_SEC", "2.0"))
BOT_CONTROL_POLL_SEC = float(os.getenv("TENNIS_BOT_CONTROL_POLL_SEC", "3.0"))
RECORD_POLL_SEC = float(os.getenv("TENNIS_RECORD_POLL_SEC", "5.0"))
FOLLOW_POLL_SEC = float(os.getenv("TENNIS_FOLLOW_POLL_SEC", "20.0"))
ORDER_POLL_SEC = float(os.getenv("TENNIS_ORDER_POLL_SEC", "1.0"))
STREAM_CONFLATE_MS = int(os.getenv("TENNIS_STREAM_CONFLATE_MS", "0"))
RECENT_POINTS = int(os.getenv("TENNIS_RECENT_POINTS", "12"))

STREAM_FIELDS = ("EX_BEST_OFFERS", "EX_LTP", "EX_TRADED", "EX_TRADED_VOL", "EX_MARKET_DEF")

# Latenza paper di default (ms): SOLO rete/processing nostra — il betDelay
# in-play arriva dal marketDefinition streamato e lo dorme flumine (vedi
# build_order_client e docs/DELAY_SIMULAZIONE_FLUMINE.md).
TENNIS_PAPER_LATENCY_MS_DEFAULT = 600

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
        # LATENZA PAPER = SOLO rete/processing NOSTRA (fix cantiere D 17/07).
        # flumine dorme GIÀ il betDelay in-play del marketDefinition streamato
        # (execute_place: sleep(bet_delay + place_latency), simulatedexecution.py:35-36;
        # betDelay fresco garantito da FreshDelaySimulatedExecution, fix GAP-5).
        # Il vecchio default 3000ms metteva il "delay tennis ~3s" DENTRO
        # place_latency = DOPPIO CONTEGGIO (betDelay stream + 3s) → paper troppo
        # lento, distorto. Nessuna misura reale di round-trip place nei log/DB:
        # default 600ms scelto per principio con margine conservativo (flumine
        # modella 120ms co-locato; REST place da fibra IT ≈ 150-400ms + processing
        # runner). Vedi docs/DELAY_SIMULAZIONE_FLUMINE.md. Override via env
        # TENNIS_PAPER_LATENCY_MS (0 = nessuna latenza, solo debug consapevole);
        # da ricalibrare con timestamp decision→ack reali appena disponibili.
        lat = float(os.getenv("TENNIS_PAPER_LATENCY_MS", str(TENNIS_PAPER_LATENCY_MS_DEFAULT)) or 0)
        flumine_config.place_latency = max(0.0, lat) / 1000.0
        return clients.BetfairClient(
            api_client, order_stream=True, paper_trade=True, min_bet_validation=False
        ), True
    # OFF (o modalità sconosciuta): paper_trade FORZATO → nessun ordine reale possibile.
    # orders_enabled=False → il worker ordini non gira (nessun ordine del tutto).
    return clients.BetfairClient(
        api_client, order_stream=True, paper_trade=True, min_bet_validation=False
    ), False


def _wire_paper_execution(framework: Any, mode: str) -> bool:
    """FIX GAP-5 (betDelay stantio): in ogni modalità NON-LIVE il paper deve
    dormire il betDelay VIGENTE al momento dell'esecuzione (pre-off→in-play,
    cambio regime post-sospensione), non lo snapshot della decisione.
    Sostituisce ``framework.simulated_execution`` → shutdown pulito a ogni
    restart (vedi paper_execution.py). Ritorna True se installata."""
    if mode == "LIVE":
        return False
    install_fresh_delay_execution(framework)
    return True


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
        # 23/09: istante del book di flumine (pt) se presente, altrimenti adesso
        "updated_ms": _lcad.updated_ms_del_book(book),
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


_STATI_FINITI = ("finished", "complete", "completed", "ended", "closed")


def _set_summary(seq_p1: List[str], seq_p2: List[str], gh: int, ga: int,
                 sh: int = 0, sa: int = 0, status: Any = None) -> Optional[str]:
    """Riepilogo dei set, es. "6-4 3-6 2-1" (set in corso compreso).

    26/09 (F-10, e2e fase 3): ``gameSequence`` IPS porta i set gia' chiusi PRIMA
    di quello corrente; i game del set in corso (o dell'ultimo, a partita
    finita) stanno in ``games``. Prima si mostrava solo la sequenza: Bondar v
    Birrell finita 1-2 in set (ultimo set 1-6) diceva «5-7 6-2». Si aggiunge il
    set di ``games`` solo se la sequenza non lo contiene gia' (nessun doppione).
    """
    parti = [f"{a}-{b}" for a, b in zip(seq_p1, seq_p2)]
    finita = str(status or "").strip().lower() in _STATI_FINITI
    attesi = int(sh or 0) + int(sa or 0) + (0 if finita else 1)
    if (gh or ga) and len(parti) < attesi:
        parti.append(f"{gh}-{ga}")
    return " ".join(parti) if parti else None


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
        "set_summary": _set_summary(seq_p1, seq_p2, gh, ga, sh, sa, ts.status),
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
def _make_capture(market_id: str, event_id: str, market_ids: Optional[List[str]] = None) -> Any:
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

        def process_closed_market(self, market: Any, market_book: Any) -> None:  # noqa: ARG002
            """26/09 (R-FA-1): flumine NON passa mai un book CLOSED a
            ``process_market_book`` (``baseflumine._process_market_books``:
            ``CloseMarketEvent`` + ``continue``) ma chiama QUESTO. Prima la
            capture teneva l'ultimo book (SUSPENDED) e ``tennis_live_now`` non
            arrivava mai a CLOSED: il ponte non chiudeva le partite finite."""
            mid = str(getattr(market_book, "market_id", "") or "")
            if not mid:
                return
            with self._lock:
                try:
                    rec = serialize_book(market_book, LADDER_DEPTH)
                except Exception:  # noqa: BLE001 - book strano: si marca l'ultimo noto
                    rec = dict(self._latest.get(mid) or {"market_id": mid, "runners": {}})
                rec["status"] = "CLOSED"
                self._latest[mid] = rec

        def latest(self) -> Dict[str, Dict[str, Any]]:
            with self._lock:
                return dict(self._latest)

        def latest_for(self, market_id: str) -> Dict[str, Dict[str, Any]]:
            """Solo il book di UN mercato (la capture è CONDIVISA fra gli eventi:
            ogni consumer legge il proprio mercato, mai quelli degli altri)."""
            with self._lock:
                book = self._latest.get(market_id)
                return {market_id: book} if book else {}

    # BUG FIX cert 10/07 (VISTO DAL VIVO — stesso CRITICAL-2 già fixato sul calcio):
    # BaseStrategy ha default NASCOSTI pensati per bot automatici — max_order_exposure=10
    # (€10 di rischio max per ordine!), max_selection_exposure=100, max_live_trade_count=1
    # (UN solo ordine vivo per selezione: il 2° click sul ladder veniva RIFIUTATO con
    # STRATEGY_EXPOSURE, visto dal vivo su Fery v Zverev). Gli ordini MANUALI del
    # terminal si agganciano a QUESTA strategy → i default vanno disattivati; le
    # protezioni vere restano ai cap espliciti del build (max_stake) e ai limiti bot.
    # REGISTRAZIONE OPT-IN (17/07): lo stream della capture usa il MarketStream
    # tennis col tee del raw nativo (tennis_recorder). Il tee è NO-OP finché
    # nessun evento ha record=true (fast-path nel listener): zero impatto sulle
    # partite non registrate. STREAM UNICO preservato: la capture è aggiunta al
    # framework PRIMA dei bot e flumine fonde i bot (stream_class di default
    # MarketStream) nella stessa stream via isinstance(stream, strategy.
    # stream_class) — TennisRecMarketStream È un MarketStream; la verifica
    # stream_ids nel build lo certifica a ogni riavvio.
    # STREAM UNICO CROSS-EVENTO (audit 09/09): flumine riusa una MarketStream
    # SOLO a filtro identico — con un filtro per evento il runner apriva UNA
    # CONNESSIONE BETFAIR PER MATCH SEGUITO (5 match = 5 delle 10 connessioni
    # concesse per app key). ``market_ids`` = TUTTI i mercati seguiti → una sola
    # capture, una sola subscription; i bot ricevono lo stesso filtro
    # (_instantiate_bot) e sono scopati sul PROPRIO mercato.
    return _Capture(
        market_filter=streaming_market_filter(market_ids=list(market_ids or [market_id])),
        stream_class=TennisRecMarketStream,
        max_order_exposure=None,
        max_selection_exposure=None,
        max_trade_count=int(1e9),
        max_live_trade_count=int(1e9),
    )


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
        # ricambio pianificato (desktop, vita massima): exit EXIT_PLANNED_RESTART
        self.planned_restart: bool = False
        # mode ordini CATTURATA al build del framework (fix audit #14): i worker
        # specchio (ordini bot / posizioni) usano QUESTA, mai una ri-lettura env a
        # metà processo (la mode dello specchio non può divergere dagli ordini).
        self.order_mode: Optional[str] = None
        # generazione del framework (fix audit #8): incrementata a ogni rebuild;
        # gli ordini tracciati di una generazione smontata vanno chiusi/scartati.
        self.framework_gen: int = 0
        # (event_id, bot_key) già tracciati come 'restart_deferred' nell'episodio
        # di rinvio corrente (fix audit #1: una riga di attività per episodio).
        self._restart_deferred_logged: set = set()
        # inizio (monotonic) dell'episodio di rinvio restart e ultimo log di
        # escalation LIVE (fix controcheck 16/07: il rinvio non è mai eterno —
        # vedi _RESTART_GRACE_S in _request_restart).
        self.restart_deferred_since: Optional[float] = None
        # R-STREAM-1 (26/09): dalle 10:41Z anche il tennis ladder=0 per ore e
        # nessun controllo di stallo. Epoca dell'ultimo framework.run(), ultima
        # ricostruzione per stallo (throttle), ricostruzione in osservazione
        # (monotonic + battito dati di quel momento) e ultimo alert d'escalation.
        self.stream_started_monotonic: Optional[float] = None
        self.stall_last_restart: float = -1e9
        self.stallo_rebuild_mono: Optional[float] = None
        self.stallo_rebuild_dati_ms: int = 0
        self.stallo_escala_alert_mono: float = -1e9
        self._restart_blocked_logged_at: Optional[float] = None
        # control-row (event_id, bot_key) dei bot IN ATTESA annotati col motivo
        # del rinvio restart (fix cantiere D 17/07: un bot B armato su un altro
        # evento restava "armed" per sempre senza che l'utente sapesse perché).
        self._restart_wait_marked: set = set()
        # chiavi (mode, market_id, selection_id, handicap) scritte in
        # tennis_live_positions in questa sessione (fix audit #8: azzeramento
        # delle righe rimaste orfane dopo un restart del framework).
        self.positions_written: Dict[tuple, Dict[str, Any]] = {}
        # D3 (24/09): i "chiudi ora" in corso, (event_id, bot_key) -> record
        # (`chiusura_manuale`). NON si svuota a `reset_streams`: il comando va
        # ridato all'istanza nuova dopo un rebuild.
        self.chiusure_manuali: Dict[tuple, Dict[str, Any]] = {}
        # 25/09 - ISCRIZIONE/ARMAMENTO A CALDO (``iscrizione_a_caldo``): il
        # contesto del framework VIVO (None fra una build e l'altra), il lock
        # che serializza follow_worker e bot_control_worker sulle operazioni a
        # caldo, da quando un follow e' sparito (grazia d'uscita) e i rifiuti
        # per tetto gia' annotati (una scrittura per episodio).
        self.caldo: Optional["ContestoCaldo"] = None
        self.caldo_lock = threading.RLock()
        self.follow_assenti_dal: Dict[str, float] = {}
        self.caldo_rifiuti_annotati: set = set()
        # 25/09 (F8) - AGGANCIO A COMANDO (``esecutore_tennis.AgganciaTennis``):
        # le partite chieste da un ordine di un bot (event_id -> {market_id,
        # meta, ultimo_uso}), il book che flumine aveva quando la loro
        # sottoscrizione e' partita (market_id -> id(book)) e l'ultima lista dei
        # follow letta dal DB (None = mai letta: nessun allineamento a comando).
        self.comandi: Dict[str, Dict[str, Any]] = {}
        self.attesa_libro: Dict[str, Optional[int]] = {}
        self.ultimi_follows: Optional[List[Dict[str, Any]]] = None
        # 26/09 (R-FA-1): eventi con ``tennis_live_now.status='CLOSED'`` gia'
        # scritto (stato terminale: non si riscrive, NON si svuota a
        # ``reset_streams`` - dopo un rebuild il book vuoto direbbe SUSPENDED)
        self.now_chiusi: set = set()

    def reset_streams(self) -> None:
        self.capture.clear()
        self.hosted.clear()
        self.stopping_deadline.clear()
        # il framework vecchio non esiste piu': niente operazioni a caldo su di lui
        self.caldo = None
        self.follow_assenti_dal.clear()
        # nuovo framework in arrivo: gli Order del vecchio blotter sono orfani
        self.framework_gen += 1

    def points_deque(self, event_id: str) -> Deque[Dict[str, Any]]:
        dq = self.recent_points.get(event_id)
        if dq is None:
            dq = deque(maxlen=RECENT_POINTS)
            self.recent_points[event_id] = dq
        return dq


# ---------------------------------------------------------------------------
# Risoluzione mercato MATCH_ODDS + mappa nomi (come run_tennis_pro._resolve)
# ---------------------------------------------------------------------------
def _resolve_market(trading: Any, market_id: Optional[str], event_id: Optional[str],
                    solo_match_odds: bool = False) -> Dict[str, Any]:
    from betfairlightweight import filters

    filt = (
        # 25/09 (F8): un mercato chiesto da un COMANDO deve essere il MATCH_ODDS
        # di una partita di tennis (l'unico che il runner sottoscrive)
        filters.market_filter(market_ids=[market_id], event_type_ids=[TENNIS_EVENT_TYPE_ID],
                              market_type_codes=["MATCH_ODDS"])
        if market_id and solo_match_odds else
        filters.market_filter(market_ids=[market_id]) if market_id
        else filters.market_filter(
            event_ids=[event_id], event_type_ids=[TENNIS_EVENT_TYPE_ID],
            market_type_codes=["MATCH_ODDS"],
        )
    )
    cat = trading.betting.list_market_catalogue(
        # COMPETITION (25/09): il nome del torneo, da cui tennis_pro ricava la
        # SUPERFICIE (`tennis_scalper/superficie.py`). Stessa chiamata, peso 0.
        filter=filt, market_projection=["RUNNER_DESCRIPTION", "EVENT", "COMPETITION"],
        sort="MAXIMUM_TRADED", max_results=5,
    )
    if not cat:
        raise ValueError("nessun mercato MATCH_ODDS trovato")
    mo = cat[0]
    name_to_sel = {r.runner_name: r.selection_id for r in (mo.runners or [])}
    selection_names = {str(r.selection_id): r.runner_name for r in (mo.runners or [])}
    ev = getattr(getattr(mo, "event", None), "id", None) or event_id
    comp = getattr(getattr(mo, "competition", None), "name", None)
    return {
        "market_id": mo.market_id,
        "event_id": str(ev) if ev else event_id,
        "market_type": "MATCH_ODDS",
        "market_name": "Match Odds",
        "name_to_sel": name_to_sel,
        "selection_names": selection_names,
        "competition_name": str(comp) if comp else None,
    }


def _catalog_follow(session: TennisLiveSession, follow: Dict[str, Any]) -> None:
    event_id = follow["event_id"]
    if event_id in session.market_meta:
        return
    meta = _risolvi_follow(session, follow)
    if meta is not None:
        session.market_meta[event_id] = meta


def _risolvi_follow(session: TennisLiveSession, follow: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Il catalogo MATCH_ODDS di un follow (REST), SENZA toccare la sessione:
    la build lo scrive subito in ``market_meta``, l'iscrizione a caldo solo
    dopo che la risottoscrizione e' riuscita. None = follow marcato ERROR."""
    event_id = follow["event_id"]
    # 25/09 (F8): la partita di un COMANDO porta il catalogo gia' risolto
    # dall'aggancio (nessuna seconda chiamata REST, nessuna riga di follow)
    gia = _ET.meta_da_catalogo(follow.get("_meta"))
    if gia is not None:
        return _con_competizione(gia, follow)
    try:
        meta = _resolve_market(session.trading, follow.get("market_id"), event_id)
    except Exception as e:  # noqa: BLE001
        # SESSIONE SCADUTA (INVALID_SESSION dopo inattività .it): UN relogin e
        # retry prima di marcare ERROR — altrimenti ogni primo follow dopo un
        # periodo di quiete fallirebbe definitivamente (ladder mai partito).
        logger.warning("[tennis-runner] catalogo KO %s (%s): relogin e retry", event_id, str(e)[:80])
        try:
            session.trading.login()
            meta = _resolve_market(session.trading, follow.get("market_id"), event_id)
        except Exception as e2:  # noqa: BLE001
            logger.warning("[tennis-runner] catalogo KO anche dopo relogin %s: %s", event_id, e2)
            tennis_db.set_tennis_follow_status(event_id, "ERROR", str(e2))
            return None
    return _con_competizione(meta, follow)


def _con_competizione(meta: Dict[str, Any], follow: Dict[str, Any]) -> Dict[str, Any]:
    """25/09 - il nome del TORNEO nella meta della partita (serve a tennis_pro
    per la superficie). Prima il catalogo Betfair (``_resolve_market``), poi
    la riga di follow (``tennis_live_follow.competition_name``, che il ponte
    copia da ``tennis_markets`` o dal feed unico). Nessuna chiamata in piu'."""
    if not meta.get("competition_name") and follow.get("competition_name"):
        meta["competition_name"] = str(follow.get("competition_name"))
    return meta


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


def descrivi_esecuzione_bot(strat: Any, runner_mode: str) -> Dict[str, Any]:
    """T1: come esegue DAVVERO un bot armato, in parole (per l'attivita' e i log).

    ``esecuzione``: 'reale' SOLO se modalita' LIVE e dry_run spento; 'simulata'
    se PAPER e dry_run spento (blotter simulato, client paper_trade=True);
    'nessun ordine (dry-run)' altrimenti."""
    mod = str(getattr(strat, "_tennis_modalita_esecuzione", "OFF") or "OFF").upper()
    dry = bool(getattr(strat, "dry_run", True))
    client = getattr(strat, "_tennis_client_ordini", None)
    if dry:
        esecuzione = "nessun ordine (dry-run)"
    elif mod == "LIVE":
        esecuzione = "reale"
    else:
        esecuzione = "simulata"
    return {
        "modalita_bot": getattr(strat, "_tennis_modalita_riga", "paper"),
        "modalita_esecuzione": mod,
        "runner": str(runner_mode or "OFF").strip().upper(),
        "dry_run": dry,
        "esecuzione": esecuzione,
        "client": ("simulato affiancato (paper_trade=True)" if client is not None
                   else "di default del processo"),
    }


def _scrivi_attivita_modalita(event_id: str, bot_key: str, strat: Any,
                              runner_mode: str) -> None:
    """Riga di attivita' ``modalita`` all'armamento: dice come il bot esegue
    (T1: un bot paper in un runner LIVE lo deve DIRE, non solo farlo)."""
    try:
        tennis_db.write_tennis_bot_activity(
            event_id, bot_key, "modalita", descrivi_esecuzione_bot(strat, runner_mode))
    except Exception as e:  # noqa: BLE001 - l'attivita' non ferma mai l'armamento
        logger.debug("[tennis-runner] attivita' modalita' %s/%s KO: %s", event_id, bot_key, e)


def _instantiate_bot(bot_key: str, control: Dict[str, Any], market_id: str,
                     name_to_sel: Dict[str, int], sink: Any,
                     data_filter: Dict[str, Any], mode: str,
                     market_ids: Optional[List[str]] = None,
                     client_paper: Any = None,
                     competition_name: Optional[str] = None) -> Any:
    """Istanzia un bot AGGANCIATO allo stream unico dell'evento.

    STREAM UNICO (#1): passa lo STESSO ``market_data_filter`` (``data_filter``) della
    capture-strategy. flumine (``Streams.add_stream``) fonde due strategie nella STESSA
    MarketStream solo se COINCIDONO market_filter + market_data_filter + streaming_timeout
    + conflate_ms. La capture usa ``streaming_market_filter(market_ids=[market_id])`` e
    ``data_filter`` (streaming_timeout/conflate = default None): qui usiamo identici →
    UNA sola subscription Betfair per evento (capture + bot).

    KILL-SWITCH DI MODALITA' (#3): se ``mode == OFF`` il bot è FORZATO in ``dry_run=True``
    (i bot tennis gateano ogni ``market.place_order`` su ``self.dry_run``): impossibile
    piazzare con il runner spento, a prescindere da ciò che chiede il control.

    REGOLA SPECCHIO PAPER/LIVE (16/07): in PAPER il default è ``dry_run=False`` — gli
    ordini sono comunque SIMULATI per costruzione (``build_order_client`` forza
    ``paper_trade=True`` fuori da LIVE), ma così passano da ``market.place_order`` →
    blotter → mirror ``tennis_live_orders`` e diventano VISIBILI sul ladder come dal
    vivo. Il flag del control resta rispettato (un dry_run esplicito vince). In LIVE il
    default resta ``dry_run=True`` (prudenza sui soldi veri: va tolto consapevolmente).

    T1 (24/09) - LA MODALITA' E' DEL BOT, NON DEL RUNNER. ``mode`` qui e' la
    modalita' del PROCESSO; quella con cui il bot esegue la decide
    ``guardie_tennis.modalita_esecuzione_bot``: LIVE solo se il runner e' LIVE E la
    riga porta ``mode='live'``. Una riga paper (o senza ``mode``) dentro un runner
    LIVE esegue come nel runner PAPER (stessi params, ``dry_run`` di default falso)
    ma SOLO se le viene dato ``client_paper``: il bot viene instradato su quel
    client simulato (``instrada_ordini_su_client``). Senza client paper il bot
    nasce in ``dry_run`` FORZATO: non puo' piazzare niente, ne' finto ne' vero.
    Il reale, infine, vuole ``dry_run`` ESATTAMENTE ``False`` sulla riga (prima
    bastava un ``null``: ``bool(None)`` era gia' "reale").

    SUPERFICIE (25/09, decisione utente) - solo ``tennis_pro``: la decide il
    runner dal nome del TORNEO (``competition_name``; senza, il
    ``params['surface_torneo']`` di un armamento precedente) con
    ``superficie.risolvi``. Torneo sconosciuto = ``'hard'`` DICHIARATO
    (``surface_fonte='default'``). Vince SEMPRE sul ``surface`` dei params: la
    vecchia UI salvava ``'grass'`` di default, indistinguibile da una scelta.
    """
    cls, params_kw, needs_names = _BOT_REGISTRY[bot_key]
    params = dict(control.get("params") or {})
    params["stake"] = float(control.get("stake") or params.get("stake") or 2.0)
    runner_u = (mode or "OFF").strip().upper()
    mode_u = _gt.modalita_esecuzione_bot(control, runner_u)
    is_live = mode_u == "LIVE"
    # un bot PAPER in un runner LIVE: il client di default del framework e' quello
    # REALE, quindi il bot deve essere instradato sul client simulato affiancato
    paper_in_runner_live = runner_u == "LIVE" and mode_u == "PAPER"
    if mode_u == "PAPER" and paper_in_runner_live and client_paper is None:
        # nessun client simulato a disposizione: il bot non deve piazzare NULLA
        # (fail-closed, mai un ordine "paper" sul client reale)
        params["dry_run"] = True
    elif mode_u == "PAPER":
        # simulato per costruzione: default dry_run=False per la visibilità sul ladder
        # (l'ordine passa dal blotter SIMULATO: SimulatedExecution, mai Betfair)
        params["dry_run"] = bool(control.get("dry_run", False))
    elif is_live:
        # il reale e' un gesto per partita: SOLO un False esplicito toglie il dry-run
        params["dry_run"] = not _gt.dry_run_esplicito_falso(control)
    else:
        # OFF: dry-run FORZATO (kill-switch, il control non può aggirarlo)
        params["dry_run"] = True
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
    # BLINDATURE DI GIURISDIZIONE PER TUTTI E QUATTRO (17/09). Prima solo lo
    # scalper le riceveva, perché arrivavano dal suo preset: pro, FLB e swing
    # andavano in LIVE senza nessun minimo, e un green-up da 0,93 € veniva
    # RIFIUTATO da Betfair lasciando la gamba SCOPERTA (il runner passa
    # `min_bet_validation=False`, quindi flumine non intercetta). I quattro bot
    # leggono `live_min_bet` per sapere se sono in LIVE e legalizzano le size
    # con `condotta_ordini.size_legale`.
    if is_live:
        params.setdefault("live_min_bet", 2.0)   # .it BACK
        params.setdefault("size_step", 0.5)      # .it granularità
        # ⊘ USCITE A SIZE ESATTA (place-and-trim) — NON accese qui.
        # Il park-trim-replace esiste in casa (`Betfair/stream/trading/submin.py`,
        # usato da `_place_exact` dello scalper) e la regola dell'utente è che
        # QUALSIASI importo è piazzabile fino a 0,01 €. Accenderlo però NON è una
        # riga di configurazione: provato il 17/09 sul replay (35794049, scenario
        # `live`) porta il referto da 4.087 a 8.566 violazioni, perché la
        # sequenza park→trim→replace mette a mercato ordini che i controlli
        # leggono come «sotto il minimo» (che è il punto della tecnica: si
        # RIDUCE sotto il minimo, non si piazza sotto il minimo). Va certificato
        # come cantiere suo, con i controlli che sanno distinguere un ordine
        # PIAZZATO sotto il minimo da uno TRIMMATO. Finché non lo è, resta
        # spento e dichiarato.
    else:
        # PAPER/OFF: fill simulati a size ESATTE (mirror di run_tennis_scalper
        # --paper): la granularità .it non esiste in simulazione → green-up esatti,
        # e arrotondare falserebbe il confronto fra replay e paper.
        params["size_step"] = 0.0
        params["live_min_bet"] = 0.0
    sup = None
    if bot_key == "tennis_pro":
        sup = superficie_della_partita(competition_name, params)
        richiesta = params.get("surface")
        params.update(sup.come_params())
        if richiesta not in (None, "", sup.superficie):
            logger.info("[tennis-runner] tennis_pro: surface=%r dei params IGNORATA, "
                        "decide la partita: %s", richiesta, sup.testo())
    stake = params["stake"]
    cap = stake * (float(params.get("price_max", 6.0)) + 2.0) * 3.0
    kwargs: Dict[str, Any] = {
        # stesso filtro della capture (tutti i mercati seguiti) → stream unico;
        # il bot vede SOLO il suo mercato grazie allo scoping più sotto
        "market_filter": streaming_market_filter(market_ids=list(market_ids or [market_id])),
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
    strat = cls(**kwargs)
    _scope_to_market(strat, market_id)
    # 25/09: la superficie decisa viaggia con l'istanza (la scrive
    # ``_scrivi_superficie`` sulla riga e nell'attivita' all'armamento)
    strat._tennis_superficie = sup
    # T1: la modalita' viaggia con l'istanza. La leggono il trading control
    # ``ControlloModalitaBotTennis`` (seconda rete, dentro flumine), lo specchio
    # ordini/posizioni (``tennis_live_order_worker``) e l'attivita' d'armamento.
    strat._tennis_modalita_riga = _gt.modalita_riga(control)
    strat._tennis_modalita_esecuzione = mode_u
    # 25/09 - USCITE AUTOMATICHE/MANUALI: dalla riga per partita (il ponte la
    # allinea all'interruttore del bot), riletta a caldo nel battito del
    # ``bot_control_worker``. Colonna assente = automatiche (come prima). I bot
    # leggono ``self.uscite_automatiche`` SOLO nelle prese di profitto: stop e
    # protezioni non lo guardano. Lo scalper resta sempre automatico
    # (``auto_mode.BOT_USCITE_SEMPRE_AUTOMATICHE``).
    strat.uscite_automatiche = _AM.uscite_automatiche_bot(bot_key, control)
    if paper_in_runner_live and client_paper is not None:
        _gt.instrada_ordini_su_client(strat, client_paper)
    # CARRY-OVER delle stats (fix 17/07, incongruenza trovata dal monitor):
    # un restart del framework RE-ISTANZIA i bot e l'heartbeat sovrascriveva
    # le stats del control con ZERI — il P&L già fatto nel match spariva dal
    # pannello (restava solo nel log attività). Le stats accumulate della
    # PARTITA si riprendono dal control row (stessa chiave = stessa metrica).
    # Il RIARMO esplicito resetta comunque: la RPC arm scrive stats=NULL.
    prev = control.get("stats")
    st = getattr(strat, "stats", None)
    if isinstance(prev, dict) and isinstance(st, dict):
        for k, v in prev.items():
            if (k in st and isinstance(v, (int, float))
                    and isinstance(st.get(k), (int, float))):
                st[k] = v
    return strat


def superficie_della_partita(competition_name: Optional[str],
                             params: Optional[Dict[str, Any]] = None) -> "_SUP.Superficie":
    """La superficie di tennis_pro per UNA partita (25/09). Il nome del
    torneo: ``competition_name`` (catalogo Betfair / riga di follow); se
    assente, il ``surface_torneo`` gia' scritto sulla riga a un armamento
    precedente. Nessun nome = default DICHIARATO (``superficie.risolvi``)."""
    comp = competition_name
    if not comp and isinstance(params, dict):
        comp = params.get("surface_torneo") or None
    return _SUP.risolvi(comp)


def _scrivi_superficie(event_id: str, bot_key: str, strat: Any,
                       control: Dict[str, Any]) -> None:
    """25/09 - la superficie decisa per tennis_pro, A VIDEO: nei ``params``
    della riga ``tennis_bot_control`` (il pannello per partita la legge da
    li') e una riga di attivita' ``superficie``. Si scrive SOLO se la riga non
    la porta gia' identica. Mai solleva: la scrittura non ferma l'armamento."""
    sup = getattr(strat, "_tennis_superficie", None)
    if sup is None:
        return
    chiavi = sup.come_params()
    vecchi = dict(control.get("params") or {})
    if all(vecchi.get(k) == v for k, v in chiavi.items()):
        return
    try:
        tennis_db.set_tennis_bot_params(event_id, bot_key, {**vecchi, **chiavi})
    except Exception as e:  # noqa: BLE001
        logger.warning("[tennis-runner] superficie sulla riga %s/%s KO: %s",
                       event_id, bot_key, str(e)[:160])
    ignorata = vecchi.get("surface")
    if ignorata in (None, "", sup.superficie) or vecchi.get("surface_fonte"):
        ignorata = None
    try:
        tennis_db.write_tennis_bot_activity(event_id, bot_key, "superficie", {
            "superficie": sup.superficie, "fonte": sup.fonte, "voce": sup.voce,
            "torneo": sup.competizione, "testo": sup.testo(),
            "richiesta_ignorata": ignorata,
        })
    except Exception as e:  # noqa: BLE001
        logger.debug("[tennis-runner] attivita' superficie %s/%s KO: %s", event_id, bot_key, e)


def _scope_to_market(strat: Any, market_id: str) -> None:
    """MONEY-CRITICAL: su uno stream CONDIVISO fra eventi flumine consegna a OGNI
    strategia i book di TUTTI i mercati sottoscritti, e i bot tennis accettano
    qualunque book OPEN (``check_market_book`` non guarda il market_id). Qui il
    gate viene shadowato per-istanza: un book di un altro mercato NON passa mai
    (né process_market_book né la logica di trading). ``_disable_strategy``
    sovrascrive lo stesso attributo con ``False`` costante: coerente."""
    orig = strat.check_market_book

    def _scoped(market: Any, market_book: Any, _orig: Any = orig, _mid: str = str(market_id)) -> bool:
        if str(getattr(market_book, "market_id", "")) != _mid:
            return False
        return bool(_orig(market, market_book))

    strat.check_market_book = _scoped  # type: ignore[assignment]
    strat._tennis_scoped_market_id = str(market_id)


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

# Finestra massima di un episodio di rinvio del restart (fix controcheck 16/07:
# solo lo scalper ha force_flat — un bot pro/flb/swing non flat rinviava il
# restart ALL'INFINITO bloccando arm/disarm e nuovi follow su TUTTI gli eventi).
# Scaduta la grazia: PAPER/OFF → il restart parte comunque (posizione SIMULATA,
# la liveness vince; i tracciati orfani li gestisce framework_gen → VOIDED);
# LIVE → MAI forzato (posizione reale orfana), ma il blocco diventa VISIBILE
# (activity CRITICAL per finestra) finché l'utente non chiude a mano.
_RESTART_GRACE_S = 180.0

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
# Restart del framework SOLO a bot FLAT (fix audit #1 HIGH)
# ---------------------------------------------------------------------------
def _hosted_not_flat(flumine: Any, session: TennisLiveSession) -> List[tuple]:
    """(event_id, bot_key, strategy) dei bot ospitati ATTIVI (non disabilitati) con
    posizione NON flat. Fonte: SOLO ``_strategy_is_flat`` (blotter autoritativo,
    fail-safe: blotter illeggibile = non flat)."""
    out: List[tuple] = []
    for (ev, bot_key), strat in list(session.hosted.items()):
        if getattr(strat, "_tennis_disabled", False):
            continue
        # D3 (24/09): un "chiudi ora" non concluso blocca il restart anche a
        # posizione pari: il rebuild ri-istanzierebbe il bot dalla riga ancora
        # 'running' e quello potrebbe riaprire prima di ricevere il comando.
        if (not _strategy_is_flat(flumine, strat)
                or _cm.in_chiusura(session, (ev, bot_key))):
            out.append((ev, bot_key, strat))
    return out


def _mark_waiting_controls(session: TennisLiveSession, blockers: List[tuple],
                           reason: str) -> None:
    """Rende VISIBILE sul control-row dei bot IN ATTESA il motivo del rinvio.

    Fix cantiere D (17/07): un bot A non-flat in LIVE rinvia il restart del
    framework; un bot B armato/richiesto su un ALTRO evento resta in coda
    (appare 'armed'/'requested', non trada mai) senza alcuna spiegazione per
    l'utente. Qui si scrive nel campo ``error`` ESISTENTE della riga control
    (nessuna migrazione) un motivo esplicito, UNA volta per episodio; alla
    partenza del restart il motivo viene ripulito (``_clear_waiting_controls``)
    e comunque sovrascritto dal normale ciclo arming/running del build.
    """
    blocker_desc = ", ".join(f"{bk}@{ev}" for ev, bk, _s in blockers) or "?"
    msg = (f"in attesa: restart bloccato da {blocker_desc} non-flat "
           f"({reason})")[:300]
    try:
        rows = tennis_db.list_tennis_bot_controls(statuses=list(_ARMED_STATUSES))
    except Exception as e:  # noqa: BLE001 - visibilità best-effort, mai rompere il worker
        logger.debug("[tennis-runner] mark waiting KO (list controls): %s", e)
        return
    for r in rows:
        key = (r.get("event_id"), r.get("bot_key"))
        if key[1] not in _BOT_REGISTRY or key in session.hosted:
            continue  # ospitati/bloccanti: il loro stato lo gestisce il worker bot
        if key in session._restart_wait_marked:
            continue  # già annotato in questo episodio (no spam DB)
        try:
            tennis_db.set_tennis_bot_wait_reason(key[0], key[1], msg)
            session._restart_wait_marked.add(key)
        except Exception as e:  # noqa: BLE001
            logger.debug("[tennis-runner] mark waiting KO %s/%s: %s",
                         key[0], key[1], e)


def _clear_waiting_controls(session: TennisLiveSession) -> None:
    """Ripulisce il motivo d'attesa dai control-row annotati (restart partito)."""
    for (ev, bot_key) in list(session._restart_wait_marked):
        try:
            tennis_db.set_tennis_bot_wait_reason(ev, bot_key, None)
        except Exception as e:  # noqa: BLE001 - best-effort: riproverà il prossimo episodio
            logger.debug("[tennis-runner] clear waiting KO %s/%s: %s", ev, bot_key, e)
        session._restart_wait_marked.discard((ev, bot_key))


def _reset_restart_episode(session: TennisLiveSession) -> None:
    """Chiude l'episodio di rinvio corrente (restart partito o bot tornati flat)."""
    session._restart_deferred_logged = set()
    session._rinvio_mite_logged = set()     # 25/09
    session.restart_deferred_since = None
    session._restart_blocked_logged_at = None
    # il restart parte: i bot in attesa non sono più bloccati → via il motivo
    _clear_waiting_controls(session)


def _request_restart(flumine: Any, session: TennisLiveSession, reason: str,
                     forza: bool = True) -> bool:
    """Richiede il restart del framework SOLO se ogni bot ospitato è FLAT.

    25/09 - ``forza=False`` (AUTO-MODE): restart chiesto da un'infrastruttura
    che non ha fretta (partite NUOVE arrivate dal feed, oppure un disarmo
    senza nessun armamento in coda). Con un bot non flat il restart si RINVIA
    e basta: nessun ``force_flat`` (sarebbe un'uscita imposta alla strategia
    dall'arrivo di una partita altrui) e nessun restart forzato a fine grazia
    in PAPER (azzererebbe la posizione simulata). Si riprova al giro dopo.
    Anche con ``forza=True`` un bot a USCITE MANUALI non viene mai azzerato da
    un restart forzato in PAPER: la sua posizione la chiude l'utente, come in
    LIVE (paper = specchio del live).

    Fix audit #1 (HIGH): il restart ricostruisce flumine con un blotter VUOTO.
    Riavviare con una posizione MATCHED aperta la renderebbe ORFANA in LIVE
    (nessuno la gestisce più: ``_strategy_is_flat`` sul blotter nuovo mentirebbe
    "flat") e cancellerebbe lo stato simulato in PAPER. Con almeno un bot non
    flat il restart viene RINVIATO al prossimo giro del worker: dove il bot sa
    appiattirsi da solo si alza ``force_flat`` e si scrive UNA riga di attività
    'restart_deferred' per episodio.

    Fix controcheck 16/07 (liveness): il rinvio non è mai eterno. Oltre
    ``_RESTART_GRACE_S``: PAPER/OFF → restart FORZATO (posizione simulata,
    activity 'restart_forced'); LIVE → mai forzato, escalation 'restart_blocked'
    CRITICAL una volta per finestra. Ritorna True se il restart è partito."""
    blockers = _hosted_not_flat(flumine, session)
    if not blockers:
        _reset_restart_episode(session)
        session.restart_requested.set()
        _stop_framework(flumine)
        return True
    if not forza:
        _rinvio_senza_forzare(session, blockers, reason)
        return False
    now_mono = time.monotonic()
    since = getattr(session, "restart_deferred_since", None)
    if since is None:
        since = now_mono
        session.restart_deferred_since = since
    grace_expired = (now_mono - since) > _RESTART_GRACE_S
    is_live = (getattr(session, "order_mode", None) or "").upper() == "LIVE"
    # 25/09: un bloccante a uscite MANUALI tiene una posizione che chiude
    # l'utente: in PAPER non si azzera, esattamente come in LIVE.
    manuale = any(getattr(s, "uscite_automatiche", True) is False
                  for _e, _b, s in blockers)
    if grace_expired and not is_live and not manuale:
        # PAPER/OFF: posizione SIMULATA — dopo la grazia la liveness vince.
        # Lo stato demo dei bot bloccanti riparte da zero (annunciato); gli
        # ordini tracciati della generazione smontata li chiude framework_gen.
        for ev, bot_key, _strat in blockers:
            try:
                tennis_db.write_tennis_bot_activity(
                    ev, bot_key, "restart_forced",
                    {"reason": reason,
                     "note": (f"grazia {int(_RESTART_GRACE_S)}s scaduta con "
                              "posizione SIMULATA non flat: restart forzato "
                              "(solo paper/off) — lo stato demo del bot "
                              "riparte da zero")},
                )
            except Exception as e:  # noqa: BLE001 - l'attività non rompe il worker
                logger.debug("[tennis-runner] activity restart_forced %s/%s KO: %s",
                             ev, bot_key, e)
        logger.warning("[tennis-runner] restart FORZATO dopo %ds di rinvio (%s): "
                       "%d bot non flat in modalità simulata.",
                       int(_RESTART_GRACE_S), reason, len(blockers))
        _reset_restart_episode(session)
        session.restart_requested.set()
        _stop_framework(flumine)
        return True
    if grace_expired:
        # LIVE: MAI forzare (la posizione reale resterebbe orfana). Il blocco
        # diventa VISIBILE: activity CRITICAL una volta per finestra di grazia.
        last = getattr(session, "_restart_blocked_logged_at", None)
        if last is None or (now_mono - last) >= _RESTART_GRACE_S:
            session._restart_blocked_logged_at = now_mono
            for ev, bot_key, _strat in blockers:
                try:
                    tennis_db.write_tennis_bot_activity(
                        ev, bot_key, "restart_blocked",
                        {"reason": reason, "level": "CRITICAL",
                         "note": (("restart LIVE bloccato da posizione REALE non "
                                   if is_live else
                                   "restart PAPER bloccato da posizione simulata "
                                   "a USCITE MANUALI non ")
                                  + f"flat da oltre {int(_RESTART_GRACE_S)}s: "
                                  "chiudi la posizione a mano (ladder/Betfair) "
                                  "per sbloccare arm/disarm e nuovi follow")},
                    )
                except Exception as e:  # noqa: BLE001
                    logger.debug("[tennis-runner] activity restart_blocked %s/%s KO: %s",
                                 ev, bot_key, e)
        logger.error("[tennis-runner] restart LIVE BLOCCATO da %d bot non flat "
                     "oltre la grazia (%s): serve chiusura manuale.",
                     len(blockers), reason)
    logged = getattr(session, "_restart_deferred_logged", None)
    if logged is None:
        logged = set()
        session._restart_deferred_logged = logged
    for ev, bot_key, strat in blockers:
        if hasattr(strat, "force_flat"):
            # il bot sa appiattirsi da solo: chiediglielo subito (idempotente)
            strat.force_flat = True
        key = (ev, bot_key)
        if key in logged:
            continue
        logged.add(key)
        try:
            tennis_db.write_tennis_bot_activity(
                ev, bot_key, "restart_deferred",
                {"reason": reason,
                 "note": ("restart dello stream RINVIATO: posizione NON flat — "
                          "il rebuild azzererebbe il blotter e la posizione "
                          "resterebbe orfana; si riprova a chiusura completata")},
            )
        except Exception as e:  # noqa: BLE001 - l'attività non rompe il worker
            logger.debug("[tennis-runner] activity restart_deferred %s/%s KO: %s",
                         ev, bot_key, e)
    logger.warning("[tennis-runner] restart RINVIATO (%s): %d bot non flat.",
                   reason, len(blockers))
    # fix cantiere D: i bot IN CODA (armati/richiesti ma non ospitati, anche su
    # ALTRI eventi) mostrano sul control-row PERCHÉ non stanno tradando.
    _mark_waiting_controls(session, blockers, reason)
    return False


def _rinvio_senza_forzare(session: TennisLiveSession, blockers: List[tuple],
                          reason: str) -> None:
    """25/09 - il rinvio di un restart che NON ha fretta (``forza=False``):
    nessun ``force_flat``, nessun orologio di grazia, nessun restart forzato.
    Resta visibile: una riga di log per episodio e il motivo d'attesa sui bot
    in coda (``_mark_waiting_controls``), come il rinvio di sempre."""
    logged = getattr(session, "_rinvio_mite_logged", None)
    if logged is None:
        logged = set()
        session._rinvio_mite_logged = logged
    chiave = (reason, tuple(sorted((ev, bk) for ev, bk, _s in blockers)))
    if chiave not in logged:
        logged.add(chiave)
        logger.info("[tennis-runner] restart RINVIATO senza forzare (%s): %d bot non "
                    "flat, si attende che chiudano da soli.", reason, len(blockers))
    _mark_waiting_controls(session, blockers, reason)


# ---------------------------------------------------------------------------
# Worker: ladder LIVE (write-on-change) → tennis_live_ladder
# ---------------------------------------------------------------------------
def ladder_worker(context: dict, flumine: Any, session: TennisLiveSession) -> None:  # noqa: ARG001
    """Ladder tennis: CANALE locale ogni TENNIS_LADDER_CANALE_MS (solo con client),
    DB (tennis_live_ladder) ogni LADDER_PUBLISH_SEC write-on-change. Firme separate:
    il canale non marca mai il DB come scritto. Stesso schema del calcio (23/09,
    ladder_canale.py)."""
    from .. import local_channel as _lc
    st = _lcad.stato_della_sessione(session, LADDER_PUBLISH_SEC, LADDER_CANALE_MS)
    fare_canale, fare_db = st.giro(_lc.channel_active())
    if not (fare_canale or fare_db):
        return  # nessun client e DB non ancora dovuto: giro a costo zero
    for event_id, cap in list(session.capture.items()):
        meta = session.market_meta.get(event_id) or {}
        names = meta.get("selection_names", {})
        for mid, book in cap.latest_for(str(meta.get("market_id"))).items():
            if not book:
                continue

            def _costruisci(book: Dict[str, Any] = book, names: Dict[str, str] = names) -> Any:
                payload = build_ladder_payload(book, names, LADDER_MAX_LEVELS)
                sig = (book.get("status") or "") + "|" + ladder_signature(payload["selections"])
                return payload, sig
            try:
                sig, payload = st.versione(mid, book, _costruisci)
            except Exception as e:  # noqa: BLE001
                logger.debug("[tennis-ladder] build KO %s: %s", mid, e)
                continue
            al_canale = fare_canale and st.canale_cambiato(mid, sig)
            al_db = fare_db and session._ladder_sig.get(mid) != sig
            if not (al_canale or al_db):
                continue
            row = {
                "event_id": event_id,
                "market_id": mid,
                "market_type": meta.get("market_type"),
                "market_name": meta.get("market_name"),
                "status": book.get("status"),
                "ladder": payload,
            }
            if al_canale:
                _lc.publish("ladder", row)
                st.segna_canale(mid, sig)
            if not al_db:
                continue
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
    latest = cap.latest_for(str(meta.get("market_id"))) if cap is not None else {}
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
    if str(status).upper() == "CLOSED":
        # 26/09 (R-FA-1): un mercato chiuso non e' in gioco (l'ultimo book
        # della partita porta ancora inplay=true: la UI scriverebbe «LIVE»)
        inplay = False
    state = {
        "markets": markets_out,
        "order_mode": live_order_mode(),
        "updated_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
    }
    return state, inplay, status


_STREAM_KEEPALIVE_SEC = float(os.getenv("TENNIS_STREAM_KEEPALIVE_SEC", "480"))


def _maybe_keepalive(session: TennisLiveSession) -> None:
    """keepAlive della sessione Betfair MENTRE si streamma (audit 09/09: c'era
    solo nel loop idle; col feed condiviso dei punteggi il runner può non fare
    REST per ore → sessione .it scaduta → riconnessione stream/catalogo KO)."""
    now_mono = time.monotonic()
    last = getattr(session, "_stream_ka_ts", 0.0)
    if _STREAM_KEEPALIVE_SEC <= 0 or now_mono - last < _STREAM_KEEPALIVE_SEC:
        return
    session._stream_ka_ts = now_mono
    try:
        from ..auth import keep_alive as _bf_keep_alive
        _bf_keep_alive(session.trading)
    except Exception as ex:  # noqa: BLE001 - best-effort
        logger.warning("[tennis-runner] keepAlive (stream) KO: %s", str(ex)[:120])


def _scan_feed(session: TennisLiveSession) -> ScanFeedScoreProvider:
    feed = getattr(session, "_scan_feed", None)
    if feed is None:
        feed = ScanFeedScoreProvider(BetfairInPlayProvider(session.trading))
        session._scan_feed = feed
    return feed


def score_and_now_worker(context: dict, flumine: Any, session: TennisLiveSession) -> None:  # noqa: ARG001
    trading = session.trading
    _maybe_keepalive(session)
    feed = _scan_feed(session)
    # 26/09 (R-FA-1): le partite il cui CLOSED e' gia' scritto non si
    # riscrivono piu' ogni 2 s (IO sul DB) e non chiedono piu' il punteggio.
    chiusi = getattr(session, "now_chiusi", None)
    if chiusi is None:
        chiusi = set()
        try:
            session.now_chiusi = chiusi
        except Exception:  # noqa: BLE001 - sessione finta senza attributi
            pass
    for event_id in list(session.market_meta.keys()):
        if event_id in chiusi:
            continue
        # PUNTEGGIO dal FEED UNICO dello scanner Safe Strategy (stato IPS grezzo,
        # stesso parser): prima UNA get_scores per evento ogni 2s. Riga assente o
        # stantia → chiamata diretta come sempre (mai un buco, mai dati vecchi).
        ts: Optional[TennisScore] = None
        try:
            raw_state = feed.get_raw_state(event_id)
            if raw_state is not None:
                raw: Any = [raw_state]
            else:
                feed.direct_calls += 1
                raw = trading.in_play_service.get_scores(
                    event_ids=[int(event_id)] if str(event_id).isdigit() else [event_id],
                    lightweight=True,
                )
            ts = parse_tennis_scores(raw, event_id)
        except Exception as e:  # noqa: BLE001 - il feed non deve mai rompere il worker
            logger.debug("[tennis-score] punteggio KO %s: %s", event_id, e)

        # alimenta i bot ospitati per l'evento (riuso VERBATIM: usano .score/.point_pressure).
        # snapshot con list(...): bot_control_worker può mutare session.hosted da un altro thread.
        for (ev, _bk), strat in list(session.hosted.items()):
            if ev != event_id:
                continue
            if hasattr(strat, "score"):
                strat.score = ts
            if hasattr(strat, "point_pressure") and ts is not None:
                # FAIL-SAFE (fix 2026-07-10): con ts None (feed KO/pre-match) la
                # gap-guard resta INVARIATA — mai spegnerla per un buco del feed.
                strat.point_pressure = bool(ts.point_pressure)

        # punto-per-punto (write-on-change della score key)
        prev = session.last_score.get(event_id)
        if ts is not None and (prev is None or prev.key() != ts.key()):
            evt = point_event(prev, ts)
            if evt is not None:
                session.points_deque(event_id).append(evt)
        session.last_score[event_id] = ts

        # REGISTRAZIONE OPT-IN: tee del punteggio sincronizzato (.score.jsonl,
        # formato record_multi) SOLO se l'evento ha record=true. Best-effort e
        # dedup sulla score key dentro al tee: mai rompere il worker.
        try:
            RAW_TEE.write_score(event_id, ts)
        except Exception as e:  # noqa: BLE001
            logger.debug("[tennis-rec] score tee KO %s: %s", event_id, e)

        state, inplay, status = _build_now_state(session, event_id)
        score_state = tennis_score_state(ts)
        points = list(session.points_deque(event_id))
        try:
            tennis_db.upsert_tennis_now(event_id, inplay, status, state, score_state, points)
        except Exception as e:  # noqa: BLE001
            logger.warning("[tennis-now] upsert KO %s: %s", event_id, e)
            continue        # non scritto: si riprova al giro dopo
        if str(status).upper() == "CLOSED":
            chiusi.add(event_id)    # stato terminale scritto una volta


# ---------------------------------------------------------------------------
# Worker: controllo bot (arm/disarm) + heartbeat/stat → tennis_bot_control
# ---------------------------------------------------------------------------
# 24/09 - LA SVEGLIA DEL WORKER DI ARMATURA (``canale_bot_tennis``). Con
# ``TENNIS_RUNNER_SVEGLIA_CANALE=1`` il worker viene chiamato ogni
# ``PASSO_WORKER_S`` ma LAVORA (e legge il database) solo quando il cancello lo
# dice: ogni ``BOT_CONTROL_POLL_SEC`` come oggi, oppure appena arriva dal canale
# del ponte (47337, ``tennis_bot_armamento``) una riga di armatura per una
# partita seguita, con un pavimento di 1 s. Interruttore spento: ``None``, il
# worker e' identico a prima (stessa cadenza, nessun thread, nessuna porta).
_CANCELLO_BOT_CONTROL: Optional[_CBT.CancelloBotControl] = None
_SESSIONE_ARMAMENTO: Dict[str, Any] = {"session": None}


def _partita_seguita(event_id: str) -> bool:
    """Filtro della sveglia: la riga di armatura riguarda una partita che QUESTO
    runner segue? Legge solo la memoria (nessuna lettura al database)."""
    sess = _SESSIONE_ARMAMENTO.get("session")
    meta = getattr(sess, "market_meta", None) if sess is not None else None
    return isinstance(meta, dict) and str(event_id) in meta


def _avvia_sveglia_armamento(session: "TennisLiveSession") -> None:
    """Accende (una volta per processo) l'ascolto del canale del ponte. Non
    solleva mai: senza sveglia il worker gira ogni ``BOT_CONTROL_POLL_SEC``."""
    global _CANCELLO_BOT_CONTROL
    _SESSIONE_ARMAMENTO["session"] = session
    if _CANCELLO_BOT_CONTROL is not None or not _CBT.sveglia_runner_accesa():
        return
    cancello = _CBT.CancelloBotControl(BOT_CONTROL_POLL_SEC or 3.0)
    if _CBT.avvia_ascolto_armamento(cancello, _partita_seguita) is not None:
        _CANCELLO_BOT_CONTROL = cancello
        logger.info("[tennis-runner] sveglia dell'armatura ATTIVA: un bot armato dalla "
                    "Control Room non aspetta piu' il poll di %.0fs (pavimento %.1fs).",
                    BOT_CONTROL_POLL_SEC or 3.0, _CBT.PAVIMENTO_SVEGLIA_S)


def _intervallo_bot_control() -> float:
    """Cadenza del BackgroundWorker: quella di oggi, o il passo corto quando il
    cancello decide lui quando lavorare."""
    if _CANCELLO_BOT_CONTROL is not None:
        return _CBT.PASSO_WORKER_S
    return BOT_CONTROL_POLL_SEC or 3.0


def bot_control_worker(context: dict, flumine: Any, session: TennisLiveSession) -> None:  # noqa: ARG001
    cancello = _CANCELLO_BOT_CONTROL
    if cancello is not None and not cancello.deve_girare():
        return          # 24/09: ne' cadenza ne' sveglia: nessuna lettura
    need_restart = False
    # 25/09: il restart serve ad ARMARE qualcuno (forza come sempre) o solo a
    # ripulire dopo un disarmo (non ha fretta: ``_request_restart(forza=False)``)
    serve_armare = False
    now_mono = time.monotonic()
    # D3 (24/09) - "CHIUDI ORA" dell'utente: PRIMA di tutto il resto, cosi' un
    # bot che ha finito la sua uscita viene disabilitato e portato a 'stopped'
    # prima che l'heartbeat di questo giro lo riscriva 'running'.
    try:
        _cm.avanza(flumine, session, e_flat=_strategy_is_flat,
                   disabilita=_disable_strategy, db=tennis_db)
    except Exception as e:  # noqa: BLE001 - il chiudi non ferma il worker
        logger.warning("[tennis-runner] chiudi ora: avanzamento KO: %s", e)
    # T2 (24/09): a guardia d'avvio armata un bot nuovo NON provoca il restart
    # che lo armerebbe (si riprova la ripresa; disarmi e protezioni girano).
    guardia_armata = _gt.guardia_blocca()
    # 25/09 - ARMAMENTO A CALDO: con il framework vivo un bot richiesto si
    # arma nel framework che gira (``_arma_a_caldo``), senza ricostruire; il
    # disarmo non chiede piu' nessuna ricostruzione di pulizia (il bot
    # disabilitato resta inerte). Senza contesto a caldo: come prima.
    caldo = _caldo_attivo(flumine, session)
    da_armare: List[tuple] = []
    for event_id in list(session.market_meta.keys()):
        desired = _desired_controls(event_id)
        stopping = _stopping_controls(event_id)
        # FIX 17/07 (terza review, CRITICAL "riarmo nella finestra stopping"):
        # una riga control tornata 'requested' MENTRE l'istanza VECCHIA è
        # ancora ospitata = riarmo dentro la finestra di disarm (guard SQL
        # senza 'stopping' o migrazione non applicata). MAI dirottare la
        # vecchia istanza (parametri stantii, force_flat bloccato): va chiusa
        # SENZA toccare lo status 'requested', così il restart re-istanzia coi
        # parametri NUOVI. Heartbeat e mission la SALTANO (mai sovrascrivere
        # 'requested' con 'running'/'done' dell'istanza vecchia).
        hijacked = {
            bk for bk, row in desired.items()
            if (event_id, bk) in session.hosted
            and str((row or {}).get("status") or "") == "requested"
        }
        # nuovi bot richiesti non ancora ospitati → restart per agganciarli allo stream
        for bot_key in desired:
            if (event_id, bot_key) not in session.hosted and not guardia_armata:
                need_restart = True
                serve_armare = True     # 25/09: c'e' qualcuno da armare
        # MISSIONE COMPIUTA (one_tick_per_phase): il bot alza ``mission_done``
        # dopo 1 green pre-match + 1 green in-play (e si e' gia' auto-appiattito
        # via force_flat). Come per il disarm: si disabilita SOLO a flat
        # verificato dal blotter e lo status DB diventa 'done' (gia' nel
        # contratto tennis_bots.sql). NESSUN restart del framework: il bot
        # disabilitato resta ospitato ma inerte fino al prossimo restart utile.
        for (ev, bot_key), strat in list(session.hosted.items()):
            if ev != event_id or bot_key in hijacked \
                    or getattr(strat, "_tennis_disabled", False):
                continue
            if not getattr(strat, "mission_done", False):
                continue
            if not _strategy_is_flat(flumine, strat):
                continue  # il force_flat interno sta ancora chiudendo: aspetta
            _disable_strategy(strat)
            try:
                tennis_db.set_tennis_bot_status(
                    ev, bot_key, "done", stopped=True,
                    stats=getattr(strat, "stats", None),
                )
                tennis_db.write_tennis_bot_activity(
                    ev, bot_key, "mission",
                    {"phase": "done",
                     "note": "missione compiuta: 1 tick pre-match + 1 tick in-play"},
                )
            except Exception as e:  # noqa: BLE001 - lo stato DB non rompe il worker
                logger.warning("[tennis-runner] status 'done' %s/%s KO: %s",
                               ev, bot_key, e)
            # rimosso dai desiderati di questo giro: heartbeat 'running' saltato
            desired.pop(bot_key, None)
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
            if ev != event_id or (bot_key in desired and bot_key not in hijacked):
                continue
            strat = session.hosted[(ev, bot_key)]
            key = (ev, bot_key)
            if bot_key in hijacked:
                # chiusura dell'istanza VECCHIA senza toccare lo status
                # 'requested' del riarmo: force_flat se possibile, poi disable
                # a flat (o a fine grazia) e via da hosted → il restart
                # istanzia quella NUOVA coi parametri nuovi.
                if not getattr(strat, "_tennis_disabled", False):
                    flat = _strategy_is_flat(flumine, strat)
                    deadline = session.stopping_deadline.get(key)
                    if not flat and hasattr(strat, "force_flat"):
                        if deadline is None:
                            strat.force_flat = True
                            session.stopping_deadline[key] = (
                                now_mono + _STOPPING_GRACE_S)
                            try:
                                tennis_db.write_tennis_bot_activity(
                                    ev, bot_key, "disarm_flat",
                                    {"note": "riarmo nella finestra di disarm: "
                                             "chiudo l'istanza vecchia prima di "
                                             "istanziare quella nuova"})
                            except Exception:  # noqa: BLE001
                                pass
                            continue
                        if now_mono < deadline:
                            continue
                    _disable_strategy(strat)
                    if not flat:
                        try:
                            tennis_db.write_tennis_bot_activity(
                                ev, bot_key, "warn",
                                {"note": "riarmo con istanza vecchia NON flat a "
                                         "fine grazia: verifica l'esposizione "
                                         "su Betfair/ladder"})
                        except Exception:  # noqa: BLE001
                            pass
                session.stopping_deadline.pop(key, None)
                session.hosted.pop(key, None)
                need_restart = True
                serve_armare = True     # 25/09: l'istanza NUOVA va armata
                continue
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
            if ev != event_id or bot_key not in desired or bot_key in hijacked \
                    or getattr(strat, "_tennis_disabled", False):
                continue
            # 25/09 - USCITE a caldo: la riga per partita (allineata dal ponte
            # all'interruttore del bot) decide; nessuna lettura in piu'.
            _aggiorna_uscite(flumine, session, (ev, bot_key), strat, desired.get(bot_key))
            try:
                # ⚠️ ``stats_timbrate``: l'APP_BOOT_ID vive dentro ``stats``, che
                # qui si riscrive per intero. Senza il timbro l'id sparirebbe al
                # primo battito e il riavvio successivo del runner (watchdog,
                # ricambio pianificato) scambierebbe per «avvio nuovo» un bot
                # che l'utente aveva appena armato, disarmandolo.
                battito = _aa.stats_timbrate(getattr(strat, "stats", None),
                                             _aa.boot_id_ambiente())
                aperta_dal = session_posizioni_aperte(session).get((ev, bot_key))
                if aperta_dal:
                    battito[_AM.CHIAVE_POSIZIONE_APERTA] = aperta_dal
                tennis_db.set_tennis_bot_status(
                    event_id, bot_key, "running",
                    stats=battito,
                    heartbeat=True,
                )
            except Exception as e:  # noqa: BLE001
                logger.debug("[tennis-runner] heartbeat %s/%s KO: %s", event_id, bot_key, e)
        if caldo is not None and not guardia_armata:
            # i richiesti non ospitati (nuovi, o riarmati dopo che l'istanza
            # vecchia e' uscita da hosted qui sopra) si armano a caldo
            for bot_key, ctrl in desired.items():
                if (event_id, bot_key) not in session.hosted:
                    da_armare.append((event_id, bot_key, ctrl))
    if caldo is not None:
        if da_armare:
            with session.caldo_lock:
                _arma_a_caldo(flumine, session, caldo, da_armare)
        return
    if need_restart:
        # fix audit #1: restart SOLO a bot flat (altrimenti rinviato al giro dopo)
        # 25/09: un restart di sola pulizia (disarmo, nessuno da armare) non
        # impone uscite agli altri bot ne' azzera posizioni simulate.
        if serve_armare:
            _request_restart(flumine, session, "arm/disarm bot")
        else:
            _request_restart(flumine, session, "arm/disarm bot", forza=False)


# ---------------------------------------------------------------------------
# 25/09 - USCITE AUTOMATICHE / MANUALI (a caldo, per bot)
# ---------------------------------------------------------------------------
def session_posizioni_aperte(session: Any) -> Dict[tuple, str]:
    """(evento, bot) -> ISO da quando la posizione di un bot a uscite MANUALI
    e' aperta. Vive nella sessione (un restart la ricomincia: il restart
    avviene solo a bot flat, quindi non perde una posizione aperta)."""
    d = getattr(session, "_posizioni_aperte_dal", None)
    if d is None:
        d = {}
        session._posizioni_aperte_dal = d
    return d


def _aggiorna_uscite(flumine: Any, session: Any, key: tuple, strat: Any,
                     riga: Optional[Dict[str, Any]]) -> None:
    """Allinea ``strat.uscite_automatiche`` alla riga e, a uscite MANUALI,
    annota da quando la posizione e' aperta (per l'avviso permanente della
    Control Room). Il cambio si scrive UNA volta nell'attivita' del bot.
    Il flat si verifica SOLO per i bot a uscite manuali (costo zero per gli
    altri). Non solleva mai: le uscite non fermano il battito."""
    try:
        if riga is not None:
            voluto = _AM.uscite_automatiche_bot(key[1], riga)
            # 25/09 sera: fallback a False (manuale), il default nuovo.
            prima = getattr(strat, "uscite_automatiche", False)
            if voluto is not prima:
                strat.uscite_automatiche = voluto
                try:
                    tennis_db.write_tennis_bot_activity(
                        key[0], key[1], "uscite",
                        {"automatiche": bool(voluto),
                         "note": ("uscite AUTOMATICHE: il bot prende profitto da solo"
                                  if voluto else
                                  "uscite MANUALI: il bot non prende profitto da solo, "
                                  "stop e protezioni restano; chiudi con «Chiudi»")})
                except Exception:  # noqa: BLE001 - l'attivita' e' best-effort
                    pass
        aperte = session_posizioni_aperte(session)
        if getattr(strat, "uscite_automatiche", False) is False \
                and not _strategy_is_flat(flumine, strat):
            aperte.setdefault(key, datetime.now(timezone.utc).isoformat())
        else:
            aperte.pop(key, None)
    except Exception as e:  # noqa: BLE001
        logger.debug("[tennis-runner] uscite %s KO: %s", key, e)


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
    keep_alive_desktop = os.getenv("LIVE_RUNNER_KEEP_ALIVE", "").strip() == "1"
    if uptime_exceeded(session.started_monotonic, time.monotonic(), _TENNIS_MAX_HOURS):
        reason = f"vita massima {_TENNIS_MAX_HOURS:.0f}h raggiunta"
        # desktop: ricambio pianificato → exit code dedicato, il watchdog rilancia
        session.planned_restart = keep_alive_desktop
    elif keep_alive_desktop:
        # PARITÀ COL CALCIO (audit 09/09): l'idle-exit spegneva il runner tennis
        # appena nessun match era imminente → il watchdog si fermava per sempre
        # (rc=0) e tennis_bot_service rifaceva login+N stream ogni ~90s.
        pass
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


# ---------------------------------------------------------------------------
# R-STREAM-1 (26/09) - STALLO DELLO STREAM anche nel tennis. Stessa forma del
# calcio (runner.heartbeat_worker + _escalation_stallo), stesse funzioni pure
# di runner_lifecycle: stallo effettivo (dati E heartbeat, hard-cap sui soli
# dati) -> ricostruzione (via _request_restart, mai forzata); se dopo la
# ricostruzione lo stream resta fermo -> uscita EXIT_PLANNED_RESTART e il
# watchdog rilancia (solo app desktop, mai con bot non flat/ordini vivi).
# ---------------------------------------------------------------------------
_T_STALL_RESTART_SEC = float(os.getenv("TENNIS_RAW_STALL_RESTART_SEC", "600"))
_T_STALL_MIN_INTERVAL_SEC = float(os.getenv("TENNIS_RAW_STALL_RESTART_MIN_INTERVAL_SEC", "900"))
_T_STALL_HARD_CAP_SEC = float(os.getenv("TENNIS_RAW_STALL_HARD_CAP_SEC", "1800")) or None
_T_STALL_POST_REBUILD_SEC = float(os.getenv("TENNIS_STALL_POST_REBUILD_SEC", "180"))
_T_STALL_OSSERVA_SEC = float(os.getenv("TENNIS_STALL_POST_REBUILD_OBSERVE_SEC", "900"))
_T_STALL_ALERT_SEC = 300.0


def _alert_stallo_tennis(level: str, msg: str) -> None:
    """Alert su live_alerts (best-effort: mai fermare il worker)."""
    try:
        from .. import db as _db

        _db.insert_alert(level, "TENNIS_STREAM", msg)
    except Exception as e:  # noqa: BLE001
        logger.debug("[tennis-runner] alert stallo KO: %s", str(e)[:120])


def _tennis_blocker_uscita_stallo(flumine: Any, session: TennisLiveSession) -> Optional[str]:
    """Guardia MONEY-CRITICAL dell'uscita per stallo: il processo nuovo parte con
    un blotter VUOTO -> mai con disarm in corso, bot NON flat (stessa fonte del
    restart: ``_hosted_not_flat``) o ordini vivi nel blotter. Un bot armato e
    flat si riarma dalla sua riga come dopo un restart. In dubbio: resta."""
    if session.stopping_deadline:
        return "disarm in corso (chiusura flat da completare)"
    non_flat = _hosted_not_flat(flumine, session)
    if non_flat:
        return "bot non flat: " + ", ".join(f"{bk}@{ev}" for ev, bk, _s in non_flat)
    try:
        for market in flumine.markets:
            blotter = getattr(market, "blotter", None)
            live = list(getattr(blotter, "live_orders", None) or []) if blotter is not None else []
            if live:
                return f"{len(live)} ordini vivi sul mercato {getattr(market, 'market_id', '?')}"
    except Exception:  # noqa: BLE001
        return "blotter non leggibile (prudenza: resto acceso)"
    return None


def stall_worker(context: dict, flumine: Any, session: TennisLiveSession) -> None:  # noqa: ARG001
    """Rilevamento dello stallo dello stream tennis (R-STREAM-1, 26/09)."""
    try:
        if session.shutdown_requested.is_set() or not session.market_meta:
            return
        now_mono = time.monotonic()
        now_ms = time.time() * 1000.0
        started = getattr(session, "stream_started_monotonic", None)
        age_s = (now_mono - started) if started is not None else None
        dati_ms = int(RAW_TEE.last_data_ms or 0)
        data_stall_s = raw_stall_seconds(float(dati_ms), now_ms, age_s)
        hb_stall_s = raw_stall_seconds(float(RAW_TEE.last_heartbeat_ms or 0), now_ms, age_s)
        stall_s = effective_stall_seconds(data_stall_s, hb_stall_s, _T_STALL_HARD_CAP_SEC)
        t0 = session.stallo_rebuild_mono
        if t0 is not None:
            verdetto = verdetto_post_ricostruzione(
                stall_s, dati_ms > int(session.stallo_rebuild_dati_ms or 0),
                now_mono - t0, _T_STALL_POST_REBUILD_SEC, _T_STALL_OSSERVA_SEC)
            if verdetto == VERDETTO_ATTENDI:
                return
            if verdetto != VERDETTO_GUARITO:
                _escala_stallo_tennis(flumine, session, stall_s, now_mono)
                return
            session.stallo_rebuild_mono = None
            logger.info("[tennis-runner] ricostruzione per stallo riuscita: dati vivi.")
        if not stall_restart_due(stall_s, _T_STALL_RESTART_SEC, session.stall_last_restart,
                                 now_mono, _T_STALL_MIN_INTERVAL_SEC):
            return
        session.stall_last_restart = now_mono
        logger.critical("[tennis-runner] stream MUTO da %.0fs con %d partite: ricostruisco "
                        "la subscription.", stall_s or 0.0, len(session.market_meta))
        _alert_stallo_tennis("CRITICAL", f"stream tennis MUTO da {stall_s or 0:.0f}s: "
                             "ricostruisco la subscription (auto-recovery).")
        dati_prima = dati_ms
        if _request_restart(flumine, session, f"stall-recovery: stream muto {stall_s or 0:.0f}s",
                            forza=False):
            session.stallo_rebuild_mono = now_mono
            session.stallo_rebuild_dati_ms = dati_prima
    except Exception as e:  # noqa: BLE001 - telemetria best-effort, mai fermare il runner
        logger.debug("[tennis-runner] stall_worker KO: %s", str(e)[:160])


def _escala_stallo_tennis(flumine: Any, session: TennisLiveSession,
                          stall_s: Optional[float], now_mono: float) -> None:
    """Stream ancora fermo dopo la ricostruzione: processo nuovo (exit 75)."""
    if os.getenv("LIVE_RUNNER_KEEP_ALIVE", "").strip() != "1":
        session.stallo_rebuild_mono = None   # senza watchdog: resta il ciclo di prima
        logger.critical("[tennis-runner] stream fermo anche dopo la ricostruzione: senza "
                        "watchdog il processo NON esce.")
        return
    blocker = _tennis_blocker_uscita_stallo(flumine, session)
    if blocker is not None:
        if now_mono - session.stallo_escala_alert_mono >= _T_STALL_ALERT_SEC:
            session.stallo_escala_alert_mono = now_mono
            logger.critical("[tennis-runner] riavvio per stream muto RINVIATO: %s.", blocker)
            _alert_stallo_tennis("CRITICAL", "stream tennis MUTO anche dopo la ricostruzione "
                                 f"ma riavvio del processo RINVIATO ({blocker}).")
        return
    logger.critical("[tennis-runner] stream MUTO (%.0fs) dopo la ricostruzione: esco con "
                    "%d, il watchdog rilancia.", stall_s or 0.0, EXIT_PLANNED_RESTART)
    _alert_stallo_tennis("CRITICAL", f"stream tennis ancora MUTO {stall_s or 0:.0f}s dopo la "
                         "ricostruzione: riavvio del processo (il watchdog lo rilancia).")
    session.planned_restart = True
    session.shutdown_requested.set()
    _stop_framework(flumine)


# ---------------------------------------------------------------------------
# 25/09 - ISCRIZIONE E ARMAMENTO A CALDO (``iscrizione_a_caldo``)
# ---------------------------------------------------------------------------
class ContestoCaldo:
    """Quello che serve per sottoscrivere e armare a framework VIVO: gli stessi
    oggetti con cui la build ha costruito capture e bot (``data_filter``,
    modalita' CATTURATA al build, client paper affiancato in LIVE)."""

    def __init__(self, framework: Any, capture: Any, data_filter: Dict[str, Any],
                 mode: str, client_paper: Any = None) -> None:
        self.framework = framework
        self.capture = capture
        self.data_filter = data_filter
        self.mode = mode
        self.client_paper = client_paper


#: attesa massima del ciclo di flumine per un lavoro a caldo (poi si riprova)
_CALDO_TIMEOUT_S = 5.0


def _caldo_attivo(flumine: Any, session: Any) -> Optional[ContestoCaldo]:
    """Il contesto a caldo se il framework vivo e' QUELLO del worker e
    l'interruttore e' acceso (riletto a ogni giro: spento = come prima)."""
    caldo = getattr(session, "caldo", None)
    if caldo is None or not _IAC.acceso():
        return None
    if flumine is not None and caldo.framework is not flumine:
        return None
    return caldo


def _mercato_con_posizioni(flumine: Any, market_id: Optional[str]) -> bool:
    """True se sul mercato c'e' un ordine VIVO o un'esposizione MATCHED non
    pari, di QUALUNQUE strategia (bot, capture degli ordini manuali). Fonte:
    SOLO il blotter flumine. Mercato mai arrivato = niente posizioni; mercato
    CHIUSO (regolato) = niente rischio vivo. In dubbio: True (protetto)."""
    if not market_id or flumine is None:
        return False
    try:
        market = flumine.markets.markets.get(str(market_id))
    except Exception:  # noqa: BLE001 - struttura illeggibile: protetto
        return True
    if market is None:
        return False
    if getattr(market, "closed", False) is True:
        return False
    blotter = getattr(market, "blotter", None)
    if blotter is None:
        return False
    try:
        per_strategia: Dict[Any, set] = {}
        for o in list(blotter):
            st = getattr(o, "status", None)
            st_name = getattr(st, "name", None) or (str(st) if st is not None else "")
            if st_name in _LIVE_ORDER_STATUSES:
                return True
            sel = getattr(o, "selection_id", None)
            strat = getattr(getattr(o, "trade", None), "strategy", None)
            if sel is None or strat is None:
                continue
            hcap = float(getattr(o, "handicap", 0.0) or 0.0)
            per_strategia.setdefault(strat, set()).add((str(market_id), int(sel), hcap))
        for strat, lookups in per_strategia.items():
            for lookup in lookups:
                exp = blotter.get_exposures(strat, lookup)
                if not isinstance(exp, dict):
                    return True
                w = float(exp.get("matched_profit_if_win") or 0.0)
                l = float(exp.get("matched_profit_if_lose") or 0.0)
                if abs(w - l) >= 0.01:
                    return True
    except Exception:  # noqa: BLE001 - blotter illeggibile: protetto
        return True
    return False


def _evento_con_posizioni(flumine: Any, session: Any, event_id: str) -> bool:
    """Posizioni vive sulla partita (blotter del suo mercato) o un «chiudi ora»
    in corso su uno dei suoi bot: la partita non esce e non si espelle."""
    meta = (getattr(session, "market_meta", {}) or {}).get(event_id) or {}
    if _mercato_con_posizioni(flumine, meta.get("market_id")):
        return True
    for (ev, bot_key) in list((getattr(session, "hosted", {}) or {}).keys()):
        if ev == event_id and _cm.in_chiusura(session, (ev, bot_key)):
            return True
    return False


def _eventi_armati() -> set:
    """Le partite con almeno una riga bot armata (UNA lettura). KO = vuoto:
    le partite valgono «candidate» (meno prioritarie), mai piu' prioritarie."""
    try:
        rows = tennis_db.list_tennis_bot_controls(statuses=list(_ARMED_STATUSES))
    except Exception as e:  # noqa: BLE001
        logger.debug("[tennis-follow] righe armate illeggibili: %s", e)
        return set()
    return {str(r.get("event_id")) for r in rows or []
            if r.get("bot_key") in _BOT_REGISTRY and r.get("event_id")}


def _manuale(follow: Optional[Dict[str, Any]]) -> bool:
    """Seguita a mano: ne' dal feed (``origine='auto'``) ne' da un comando."""
    return (_AM.origine_follow(follow) != _AM.ORIGINE_AUTO
            and not _ET.e_comando(follow))


def _entro_il_tetto_al_build(follows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Alla BUILD la lista dei follow rientra nel tetto (limite Betfair 200 per
    connessione). Nessuna posizione esiste (la build parte solo a bot flat):
    a mano > armate > candidate, a parita' l'ordine della lista. Sotto il
    tetto: la lista com'e' (nessuna lettura in piu')."""
    tetto = _IAC.tetto_mercati()
    visti: Dict[str, Dict[str, Any]] = {}
    for f in follows:
        ev = str(f.get("event_id") or "")
        if ev and ev not in visti:
            visti[ev] = f
    if len(visti) <= tetto:
        return follows
    armate = _eventi_armati()
    voluti = [_IAC.Evento(ev, manuale=_manuale(f), armata=ev in armate,
                          comando=_ET.e_comando(f)) for ev, f in visti.items()]
    piano = _IAC.pianifica([], voluti, tetto)
    for ev in piano.rifiutati:
        if _ET.e_comando(visti.get(ev)):
            continue                     # nessuna riga di follow da annotare
        try:
            tennis_db.set_tennis_follow_status(
                ev, "PENDING", f"in attesa: tetto di {tetto} mercati sulla connessione pieno")
        except Exception:  # noqa: BLE001 - annotazione best-effort
            pass
    tenuti = set(piano.aggiungi)
    logger.warning("[tennis-runner] %d follow oltre il tetto di %d mercati: %d in attesa.",
                   len(visti), tetto, len(piano.rifiutati))
    return [f for f in follows if str(f.get("event_id") or "") in tenuti]


def _allinea_follow_a_caldo(flumine: Any, session: TennisLiveSession, caldo: ContestoCaldo,
                            follows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Porta lo stream alla lista dei follow SENZA ricostruire il framework.

    1. piano (``_IAC.pianifica``): nuove dentro il tetto per priorita', follow
       spariti fuori dopo la grazia, espulsioni solo di priorita' piu' bassa e
       senza posizioni;
    2. catalogo REST delle nuove FUORI dal ciclo di flumine;
    3. nel ciclo di flumine: posizioni RICONTROLLATE (una partita che ha
       aperto nel frattempo non esce), risottoscrizione sulla stessa
       connessione, poi (solo se riuscita) sessione aggiornata; i bot delle
       partite che escono si disabilitano (sono flat per costruzione);
    4. fuori: stati DB (follow STREAMING, bot 'stopped' col motivo) e
       armamento a caldo dei bot delle partite entrate.
    Ritorna l'esito (per i test e il log) o None se non c'era niente da fare."""
    ora = time.monotonic()
    voluti_righe: Dict[str, Dict[str, Any]] = {}
    for f in follows or []:
        ev = str(f.get("event_id") or "")
        if ev and ev not in voluti_righe:
            voluti_righe[ev] = f
    assenti = session.follow_assenti_dal
    for ev in list(assenti):
        if ev in voluti_righe or ev not in session.market_meta:
            assenti.pop(ev, None)
    for ev in list(session.market_meta):
        if ev not in voluti_righe:
            assenti.setdefault(ev, ora)
    grazia = _IAC.grazia_uscita_s()
    pronti = {ev for ev, t0 in assenti.items() if ora - t0 >= grazia}
    nuovi = [ev for ev in voluti_righe if ev not in session.market_meta]
    if not nuovi and not pronti:
        return None                      # niente da fare: zero letture in piu'
    tetto = _IAC.tetto_mercati()
    armate = _eventi_armati()
    attivi = {ev for (ev, _bk), st in list(session.hosted.items())
              if not getattr(st, "_tennis_disabled", False)}
    seguiti = [
        _IAC.Evento(ev,
                    manuale=(ev in voluti_righe and _manuale(voluti_righe[ev])),
                    armata=(ev in armate or ev in attivi),
                    # 25/09 (F8): un comando appena chiesto e' protetto come una
                    # posizione (il suo ordine e' in volo o parcheggiato)
                    posizioni=(_evento_con_posizioni(flumine, session, ev)
                               or _ET.comando_recente(session, ev, ora)),
                    comando=(ev in voluti_righe and _ET.e_comando(voluti_righe[ev])))
        for ev in list(session.market_meta)
    ]
    voluti = [_IAC.Evento(ev, manuale=_manuale(f), armata=ev in armate,
                          comando=_ET.e_comando(f))
              for ev, f in voluti_righe.items()]
    piano = _IAC.pianifica(seguiti, voluti, tetto, pronti)
    for ev in piano.rifiutati:
        if ev in session.caldo_rifiuti_annotati:
            continue
        session.caldo_rifiuti_annotati.add(ev)
        logger.warning("[tennis-follow] %s in attesa: tetto di %d mercati pieno e nessuna "
                       "partita espellibile (posizioni vive, a mano o piu' prioritarie).",
                       ev, tetto)
        if _ET.e_comando(voluti_righe.get(ev)):
            continue                     # comando: nessuna riga di follow da annotare
        try:
            tennis_db.set_tennis_follow_status(
                ev, "PENDING", f"in attesa: tetto di {tetto} mercati sulla connessione pieno")
        except Exception:  # noqa: BLE001 - annotazione best-effort
            pass
    if not piano.cambia:
        return None
    metas: Dict[str, Dict[str, Any]] = {}
    for ev in piano.aggiungi:
        meta = _risolvi_follow(session, voluti_righe[ev])
        if meta is not None:
            metas[ev] = meta
    uscenti = list(piano.togli) + list(piano.espulsi)
    if not metas and not uscenti:
        return None
    restano = [ev for ev in session.market_meta if ev not in uscenti]
    if not restano and not metas:
        # nessuna partita resta: un filtro vuoto non esiste (Betfair lo legge
        # come «tutto»). Framework senza partite = ricostruzione verso l'attesa,
        # che a questo punto e' sicura (niente posizioni, forza=False).
        _request_restart(flumine, session, "nessuna partita seguita", forza=False)
        return {"entrati": [], "usciti": [], "disarmati": [], "restart": True}

    def _applica(fw: Any) -> Dict[str, Any]:
        usciti = [ev for ev in uscenti if not _evento_con_posizioni(fw, session, ev)]
        trattenuti = [ev for ev in uscenti if ev not in usciti]
        base = [ev for ev in session.market_meta if ev not in usciti]
        entrano = []
        for ev in metas:
            if len(base) + len(entrano) < tetto:
                entrano.append(ev)
        mids = ([session.market_meta[ev]["market_id"] for ev in base]
                + [metas[ev]["market_id"] for ev in entrano])
        if not mids:
            return {"entrati": [], "usciti": [], "disarmati": [],
                    "trattenuti": trattenuti, "vuoto": True}
        stream = _IAC.stream_di_mercato(fw, caldo.capture)
        if sorted({str(m) for m in mids}) != _IAC.mercati_dello_stream(stream):
            # 25/09 (F8): il book che flumine ha ORA dei mercati che entrano
            # (siamo nel suo ciclo: nessun book nuovo puo' arrivare prima della
            # sottoscrizione). Un comando in attesa parte solo con un book NUOVO.
            mercati_fw = getattr(getattr(fw, "markets", None), "markets", {}) or {}
            attesa = {}
            for ev in entrano:
                mid_n = str(metas[ev]["market_id"])
                m_fw = mercati_fw.get(mid_n) if isinstance(mercati_fw, dict) else None
                libro = getattr(m_fw, "market_book", None) if m_fw is not None else None
                attesa[mid_n] = id(libro) if libro is not None else None
            _IAC.sottoscrivi(fw, stream, mids)
            session.attesa_libro.update(attesa)
        disarmati = []
        for ev in usciti:
            for (e, bk), st in list(session.hosted.items()):
                if e != ev:
                    continue
                if not getattr(st, "_tennis_disabled", False):
                    _disable_strategy(st)
                    disarmati.append((e, bk))
                session.hosted.pop((e, bk), None)
                session.stopping_deadline.pop((e, bk), None)
            session.attesa_libro.pop(
                str((session.market_meta.get(ev) or {}).get("market_id") or ""), None)
            session.market_meta.pop(ev, None)
            session.capture.pop(ev, None)
        for ev in entrano:
            session.market_meta[ev] = metas[ev]
            session.capture[ev] = caldo.capture
        return {"entrati": entrano, "usciti": usciti, "disarmati": disarmati,
                "trattenuti": trattenuti}

    try:
        esito = _IAC.esegui_nel_thread_di_flumine(caldo.framework, _applica, _CALDO_TIMEOUT_S)
    except _IAC.NonPronto as e:
        logger.info("[tennis-follow] iscrizione a caldo rinviata: %s", e)
        return None
    except Exception as e:  # noqa: BLE001 - niente e' cambiato: si riprova al giro dopo
        logger.warning("[tennis-follow] iscrizione a caldo KO (si riprova): %s", e)
        return None
    for ev in esito.get("entrati", []):
        session.caldo_rifiuti_annotati.discard(ev)
        if _ET.e_comando(voluti_righe.get(ev)):
            continue                     # comando: nessuna riga di follow
        try:
            tennis_db.set_tennis_follow_status(ev, "STREAMING")
        except Exception as e:  # noqa: BLE001
            logger.debug("[tennis-follow] status STREAMING %s KO: %s", ev, e)
    espulsi = set(piano.espulsi)
    for ev, bk in esito.get("disarmati", []):
        motivo = ((f"partita tolta dallo stream per far posto (tetto {tetto} mercati): "
                   "bot fermato a posizione flat")
                  if ev in espulsi else
                  "partita non piu' seguita (follow chiuso): bot fermato a posizione flat")
        try:
            tennis_db.set_tennis_bot_status(ev, bk, "stopped", stopped=True, error=motivo)
        except Exception as e:  # noqa: BLE001
            logger.debug("[tennis-follow] status stopped %s/%s KO: %s", ev, bk, e)
    for ev in esito.get("usciti", []):
        assenti.pop(ev, None)
        if ev in espulsi and not _ET.e_comando(voluti_righe.get(ev)):
            try:
                tennis_db.set_tennis_follow_status(
                    ev, "PENDING", f"in attesa: tolta per far posto (tetto {tetto} mercati)")
            except Exception:  # noqa: BLE001
                pass
    logger.info("[tennis-follow] a caldo sulla stessa connessione: +%d -%d (espulse %d, "
                "trattenute per posizioni %d), %d/%d mercati (limite Betfair %d).",
                len(esito.get("entrati", [])), len(esito.get("usciti", [])),
                len([e for e in esito.get("usciti", []) if e in espulsi]),
                len(esito.get("trattenuti", [])), len(session.market_meta), tetto,
                _IAC.LIMITE_BETFAIR_MERCATI)
    # i bot delle partite appena entrate si armano SUBITO (non al giro dopo)
    if esito.get("entrati") and not _gt.guardia_blocca():
        richieste = []
        for ev in esito["entrati"]:
            for bk, ctrl in _desired_controls(ev).items():
                richieste.append((ev, bk, ctrl))
        if richieste:
            esito["armati"] = _arma_a_caldo(flumine, session, caldo, richieste)
    return esito


def _arma_a_caldo(flumine: Any, session: TennisLiveSession, caldo: ContestoCaldo,
                  richieste: List[tuple]) -> List[tuple]:
    """Arma i bot sulle partite GIA' nello stream, nel framework vivo.

    Istanza costruita FUORI dal ciclo di flumine con la stessa
    ``_instantiate_bot`` della build (stessa guardia paper/live: modalita' di
    build, client paper affiancato, dry_run); ``add_strategy`` DENTRO il ciclo,
    sulla MarketStream esistente (``_IAC.aggiungi_strategia_sullo_stream``). Stati
    DB come alla build: 'arming' -> 'running' (o 'error' col motivo). Ritorna
    le chiavi (evento, bot) armate."""
    del flumine  # il framework e' quello del contesto
    pronti: List[tuple] = []
    ctrl_di = {(ev, bk): c for ev, bk, c in richieste}
    for ev, bot_key, ctrl in richieste:
        if (ev, bot_key) in session.hosted or ev not in session.market_meta:
            continue
        meta = session.market_meta[ev]
        try:
            tennis_db.set_tennis_bot_status(ev, bot_key, "arming")
        except Exception as e:  # noqa: BLE001
            logger.debug("[tennis-runner] status arming %s/%s KO: %s", ev, bot_key, e)
        try:
            bot = _instantiate_bot(
                bot_key, ctrl, meta["market_id"], meta["name_to_sel"],
                _make_sink(ev, bot_key), caldo.data_filter, caldo.mode,
                market_ids=sorted(str(m.get("market_id")) for m in session.market_meta.values()),
                client_paper=caldo.client_paper,
                competition_name=meta.get("competition_name"),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[tennis-runner] arm a caldo KO %s/%s: %s", ev, bot_key, e)
            tennis_db.set_tennis_bot_status(ev, bot_key, "error", error=str(e))
            continue
        pronti.append((ev, bot_key, bot))
    if not pronti:
        return []

    def _aggiungi(fw: Any) -> List[tuple]:
        stream = _IAC.stream_di_mercato(fw, caldo.capture)
        esiti = []
        for ev, bot_key, bot in pronti:
            if (ev, bot_key) in session.hosted or ev not in session.market_meta:
                esiti.append((ev, bot_key, bot, "saltato"))
                continue
            try:
                _IAC.aggiungi_strategia_sullo_stream(fw, stream, bot)
            except Exception as e:  # noqa: BLE001
                _disable_strategy(bot)
                esiti.append((ev, bot_key, bot, e))
                continue
            session.hosted[(ev, bot_key)] = bot
            esiti.append((ev, bot_key, bot, None))
        return esiti

    try:
        esiti = _IAC.esegui_nel_thread_di_flumine(caldo.framework, _aggiungi, _CALDO_TIMEOUT_S)
    except Exception as e:  # noqa: BLE001 - nessun bot aggiunto: righe 'arming', si riprova
        logger.warning("[tennis-runner] armamento a caldo rinviato: %s", e)
        return []
    armati: List[tuple] = []
    for ev, bot_key, bot, err in esiti:
        if err == "saltato":
            continue
        if err is not None:
            logger.error("[tennis-runner] arm a caldo %s/%s: %s", ev, bot_key, err)
            tennis_db.set_tennis_bot_status(ev, bot_key, "error", error=str(err)[:300])
            continue
        tennis_db.set_tennis_bot_status(ev, bot_key, "running", started=True)
        _scrivi_attivita_modalita(ev, bot_key, bot, caldo.mode)
        _scrivi_superficie(ev, bot_key, bot, ctrl_di.get((ev, bot_key)) or {})
        armati.append((ev, bot_key))
    if armati:
        logger.info("[tennis-runner] %d bot armati A CALDO (nessuna ricostruzione): %s",
                    len(armati), ", ".join(f"{bk}@{ev}" for ev, bk in armati))
    return armati


def record_flag_worker(context: dict, flumine: Any, session: TennisLiveSession) -> None:  # noqa: ARG001
    """REGISTRAZIONE OPT-IN per-partita (17/07): rilegge periodicamente il flag
    ``record`` da ``tennis_live_follow`` e allinea il tee raw (tennis_recorder).
    Rilettura periodica = il toggle A META' PARTITA funziona senza riavviare lo
    stream. Colonna assente (migrazione non applicata) → nessuna registrazione
    + warning una tantum dentro ``sync_record_flags``; DB KO → no-op."""
    try:
        follows = tennis_db.list_pending_tennis_follows()
    except Exception as e:  # noqa: BLE001 - il gating non rompe mai il runner
        logger.debug("[tennis-rec] lettura follow KO (ignorata): %s", e)
        return
    sync_record_flags(follows, session.market_meta)


def follow_worker(context: dict, flumine: Any, session: TennisLiveSession) -> None:  # noqa: ARG001
    try:
        follows = tennis_db.list_pending_tennis_follows()
    except Exception as e:  # noqa: BLE001
        logger.warning("[tennis-follow] list KO: %s", e)
        return
    # 25/09 (F8): l'ultima lista del DB (per l'aggancio a comando) e le partite
    # dei comandi dentro la lista (altrimenti uscirebbero dopo la grazia)
    session.ultimi_follows = list(follows)
    follows = _ET.follows_con_comandi(session, follows)
    # 25/09 - ISCRIZIONE A CALDO: con il framework vivo le partite nuove entrano
    # (e quelle chiuse escono) sulla STESSA connessione, senza ricostruire:
    # nessun rinvio per i bot in posizione, blotter e posizioni intatti.
    caldo = _caldo_attivo(flumine, session)
    if caldo is not None:
        with session.caldo_lock:
            _allinea_follow_a_caldo(flumine, session, caldo, follows)
        return
    new = [f for f in follows if f["event_id"] not in session.market_meta]
    if new:
        logger.info("[tennis-follow] %d nuovi eventi → ricostruzione stream.", len(new))
        # fix audit #1: anche il follow nuovo NON può riavviare con bot non flat
        # (il rinvio si risolve da solo: si riprova al prossimo giro del worker).
        # 25/09 AUTO-MODE: se TUTTI i follow nuovi vengono dal feed
        # (``origine='auto'``) il restart non ha fretta: nessun force_flat sui
        # bot in posizione, nessun restart forzato (``forza=False``). Una
        # partita seguita dall'utente a mano forza come sempre.
        if all(not _manuale(f) for f in new):
            _request_restart(flumine, session, f"{len(new)} nuovi follow", forza=False)
        else:
            _request_restart(flumine, session, f"{len(new)} nuovi follow")


# ---------------------------------------------------------------------------
# 25/09 (F8) - MOTORE ORDINI del runner tennis (``esecutore_tennis``): lo stesso
# ``MotoreOrdini`` del calcio sul canale 47332, col ``_dispatch`` vero del worker
# tennis, e l'aggancio a comando. SPENTO di serie: ``MOTORE_ORDINI_CANALE_TENNIS=1``.
# ---------------------------------------------------------------------------
_MOTORE_TENNIS: Dict[str, Any] = {"motore": None, "aggancio": None}


def _cartella_diario_tennis() -> str:
    from ..config_stream import DATA_DIR

    return (os.getenv("TENNIS_MOTORE_DIARIO_DIR", "").strip()
            or os.path.join(DATA_DIR, "_diario_ordini", "tennis"))


def _catalogo_comando(session: TennisLiveSession, market_id: str) -> Optional[Dict[str, Any]]:
    """Il catalogo del mercato di un comando (REST, thread dell'aggancio): SOLO
    un MATCH_ODDS di tennis. Un relogin e un secondo tentativo, poi None (il
    comando scade ``in_aggancio``, il bot ripete). Nessuna scrittura."""
    for tentativo in (1, 2):
        try:
            return _resolve_market(session.trading, market_id, None, solo_match_odds=True)
        except ValueError:
            return None                  # non e' un MATCH_ODDS di tennis
        except Exception as e:  # noqa: BLE001
            logger.warning("[tennis-aggancio] catalogo %s KO (tentativo %d): %s",
                           market_id, tentativo, str(e)[:120])
            if tentativo == 1:
                try:
                    session.trading.login()
                except Exception:  # noqa: BLE001
                    return None
    return None


def _allinea_per_comando(session: TennisLiveSession) -> None:
    """L'aggancio ha una partita nuova: lo stream si allinea SUBITO (non al giro
    del follow_worker), sulla stessa connessione. Senza framework vivo non si
    fa niente: la prossima build include le partite dei comandi."""
    ag = _MOTORE_TENNIS.get("aggancio")
    fw = getattr(ag, "_framework", None) if ag is not None else None
    if fw is None or session.ultimi_follows is None:
        return
    caldo = _caldo_attivo(fw, session)
    if caldo is None:
        # iscrizione a caldo spenta: la partita entra alla prossima ricostruzione
        _request_restart(fw, session, "partita chiesta da un comando", forza=False)
        return
    with session.caldo_lock:
        _allinea_follow_a_caldo(fw, session, caldo,
                                _ET.follows_con_comandi(session, session.ultimi_follows))


def _monta_motore_tennis(ch: Any, session: TennisLiveSession) -> None:
    """Costruisce e avvia aggancio e motore (una volta per processo)."""
    def _manuali() -> set:
        return {str(f.get("event_id")) for f in (session.ultimi_follows or [])
                if _manuale(f)}

    def _posizioni(ev: str) -> bool:
        ag = _MOTORE_TENNIS.get("aggancio")
        return _evento_con_posizioni(getattr(ag, "_framework", None), session, ev)

    ag = None
    if _IAC.acceso():
        ag = _ET.AgganciaTennis(
            session, risolvi=lambda mid: _catalogo_comando(session, mid),
            allinea=lambda: _allinea_per_comando(session),
            manuali=_manuali, posizioni=_posizioni)
        ag.avvia()
    else:
        logger.warning("[tennis-runner] iscrizione a caldo SPENTA: il motore rifiuta gli "
                       "ordini sulle partite non seguite")
    motore = _ET.costruisci_motore(
        ch, cartella_diario=_cartella_diario_tennis(),
        guardia_armata=lambda: bool(_gt.GUARDIA_RUNNER.blocca_aperture),
        motivo_guardia_order=_gt.MOTIVO_GUARDIA_LOCALE, aggancio=ag)
    # la ripresa d'avvio non disarma la guardia finche' il diario del motore non
    # e' verificato (comandi in volo al riavvio: listCurrentOrders per ref)
    _gt.imposta_ripresa_motore(
        lambda: motore.riprendi_da_diario(
            lambda refs: session.trading.betting.list_current_orders(
                customer_order_refs=list(refs), lightweight=True)))
    motore.avvia()
    if _gt.GUARDIA_RUNNER.attiva and _gt.GUARDIA_RUNNER.fatto:
        # la ripresa d'avvio e' gia' riuscita PRIMA che il motore esistesse: il
        # diario si verifica adesso; se Betfair non risponde la guardia si
        # RIARMA (solo cancel) e la ripresa riprova coi worker, diario compreso
        if not motore.riprendi_da_diario(
                lambda refs: session.trading.betting.list_current_orders(
                    customer_order_refs=list(refs), lightweight=True)):
            _gt.GUARDIA_RUNNER.fatto = False
            logger.error("[tennis-runner] ripresa dal diario del motore NON completa: "
                         "guardia d'avvio RIARMATA")
    # gli eventi ``order`` nascono dallo specchio del worker tennis
    from .tennis_live_order_worker import aggiungi_osservatore_ordini
    aggiungi_osservatore_ordini(motore._su_riga_specchio)
    _MOTORE_TENNIS.update({"motore": motore, "aggancio": ag})
    logger.info("[tennis-runner] motore ordini ATTIVO sul canale %s (diario %s), aggancio "
                "a comando %s", getattr(ch, "port", "?"), motore.diario.cartella,
                "ATTIVO" if ag is not None else "SPENTO")


def _smonta_motore_tennis() -> None:
    motore = _MOTORE_TENNIS.get("motore")
    ag = _MOTORE_TENNIS.get("aggancio")
    if ag is not None:
        ag.ferma()
    if motore is not None:
        try:
            from .tennis_live_order_worker import rimuovi_osservatore_ordini
            rimuovi_osservatore_ordini(motore._su_riga_specchio)
            motore.scrittore.svuota(5.0)
            motore.ferma()
        except Exception:  # noqa: BLE001
            logger.exception("[tennis-runner] arresto del motore ordini KO")
    _gt.imposta_ripresa_motore(None)
    _MOTORE_TENNIS.update({"motore": None, "aggancio": None})


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


def _cleanup_orphan_bot_controls(max_hb_age_s: float = 600.0) -> int:
    """RIPRESA all'avvio (fix 17/07, parità con scalper_service): righe di
    ``tennis_bot_control`` rimaste in stato ATTIVO con heartbeat stantio sono
    sessioni ORFANE (runner ucciso a metà: nessuno le ospita più) — senza
    questa pulizia un bot di IERI resta 'running' in UI per giorni. Stato
    onesto: 'error' con motivo esplicito. Le righe appena richieste (nessun
    heartbeat ma requested_at fresco) non vengono MAI toccate."""
    from datetime import datetime, timezone

    def _age_s(iso: Any) -> Optional[float]:
        try:
            dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds()
        except (TypeError, ValueError):
            return None

    try:
        rows = tennis_db.list_tennis_bot_controls(
            statuses=["requested", "arming", "armed", "running", "stopping"])
    except Exception as e:  # noqa: BLE001 - pulizia best-effort, mai bloccare l'avvio
        logger.warning("[tennis-runner] cleanup orfani KO (ignorato): %s", e)
        return 0
    n = 0
    for r in rows:
        age = _age_s(r.get("heartbeat_at")) or _age_s(r.get("requested_at"))
        if age is None or age <= max_hb_age_s:
            continue
        try:
            tennis_db.set_tennis_bot_status(
                r["event_id"], r["bot_key"], "error", stopped=True,
                error=("sessione orfana (runner riavviato, heartbeat "
                       f"fermo da {int(age / 60)} min) — riarma se serve"))
            n += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("[tennis-runner] cleanup orfano %s/%s KO: %s",
                           r.get("event_id"), r.get("bot_key"), e)
    if n:
        logger.info("[tennis-runner] ripresa: %d bot orfani marcati 'error'", n)
    return n


def _pubblica_battito_attesa() -> None:
    """25/09 (punto 6 dell'audit tempo reale) - il BATTITO del runner tennis
    PARCHEGGIATO in attesa, sul suo canale (47332), topic ``battito``
    ``{ts, mode, streaming}`` (``canale_bot.battito_runner``, le stesse chiavi
    del calcio). Il tennis non ha una riga di battito sul database e in attesa
    non pubblicava nulla (il saldo esce solo su evento): la pagina vedeva il
    socket vivo con l'eta' ferma all'hello. ``mode`` = la modalita' di questo
    processo (la stessa dell'hello); ``streaming`` = 0 (in attesa nessuna
    partita e' seguita). Nessun IO; senza canale non esce niente; mai solleva."""
    try:
        from .. import canale_bot as _cb

        _cb.pubblica_stato_processo(_cb.TOPIC["battito"],
                                    _cb.battito_runner(live_order_mode(), 0))
    except Exception as e:  # noqa: BLE001 - mostrare non ferma mai il runner
        logger.debug("[tennis-runner] battito sul canale KO: %s", str(e)[:120])


def _attiva_saldo_su_evento(framework: Any, trading: Any) -> None:
    """Rilettura del saldo su evento d'ordine (``stream/saldo_evento.py``) con
    il client Betfair di QUESTO processo. Mai solleva."""
    try:
        from .. import saldo_evento

        saldo_evento.attiva(lambda: trading.account.get_account_funds(), nome="tennis")
        framework.add_logging_control(saldo_evento.controllo_flumine())
    except Exception as e:  # noqa: BLE001 - il runner lavora comunque
        logger.warning("[tennis-runner] rilettura saldo su evento NON attiva: %s", e)


def setup_and_run(only_event: Optional[str] = None, auto_follow: bool = True) -> List[str]:
    trading = build_client(login=True)
    _valuta.CAMBIO.avvia(trading)   # K1 (26/09): cambio GBP->EUR, mai un'eccezione
    session = TennisLiveSession(trading)
    session.context_api_client = trading  # per board_worker (REST leggero)
    # FASE A (16/09) — all'avvio NUOVO dell'app nessun bot tennis resta armato:
    # gli stati requested/arming/armed/running sono persistiti per evento e il
    # runner li ri-arma da solo. Un riavvio dal watchdog (stesso APP_BOOT_ID)
    # non tocca niente. Va PRIMA della pulizia orfani, che guarda solo gli
    # heartbeat vecchi e una riga 'requested' fresca non la vede nemmeno.
    # T2 (24/09) - GUARDIA D'AVVIO (gemella di ``Guardia("runner_calcio")``): con
    # gli ordini accesi (PAPER/LIVE) la guardia si ARMA qui e la disarma SOLO una
    # ripresa riuscita (bot di un avvio vecchio fermati, coda stantia chiusa,
    # specchio paper orfano chiuso). Finche' e' armata nessun bot si arma e la
    # coda del desktop non si esegue; si riprova ogni 10 s dai worker.
    if live_order_mode() in ("PAPER", "LIVE"):
        _gt.arma_guardia_runner()
        _gt.ripresa_all_avvio()
    else:
        from .tennis_bot_service import ferma_bot_al_nuovo_avvio as _ferma_al_boot
        try:
            _ferma_al_boot()
        except Exception as e:  # noqa: BLE001 — mai bloccare l'avvio del runner
            logger.warning("[tennis-runner] controllo d'avvio bot KO (ignorato): %s", e)
    _cleanup_orphan_bot_controls()  # mai bot 'running' fantasma dopo un riavvio
    # A7 — canale LOCALE desktop (bind SOLO 127.0.0.1); best-effort come il calcio.
    from .. import local_channel as _lc
    _ch = _lc.start_channel(int(os.getenv("TENNIS_LOCAL_WS_PORT", "47332")), "tennis")
    if _ch is not None:
        _ch.set_hello(mode=live_order_mode())
    # 25/09 (F8) - motore ordini sul 47332 (opt-in): montato PRIMA del primo
    # framework; senza framework rifiuta (``runner_non_agganciato``).
    if (_ch is not None and live_order_mode() in ("PAPER", "LIVE") and _ET.acceso()
            and not only_event):
        try:
            _monta_motore_tennis(_ch, session)
        except Exception as ex:  # noqa: BLE001 - senza motore: percorso di prima
            logger.error("[tennis-runner] motore ordini NON avviato (%s): /comando/ "
                         "rifiutato come prima", str(ex)[:200])
            _smonta_motore_tennis()
    _avvia_sveglia_armamento(session)   # 24/09, interruttore spento di serie
    interrupted = False
    _announce_order_mode(live_order_mode())
    try:
        while not interrupted:
            session.restart_requested.clear()
            try:
                follows = tennis_db.list_pending_tennis_follows()
            except Exception as e:  # noqa: BLE001 - solo la rete: il resto si rilancia
                # 26/09 (crash exit 1): una SELECT fallita per RETE (anche nel
                # giro idle ogni 2 s) uccideva il processo; ora attesa e nuovo giro
                if not e_errore_di_rete(e):
                    raise
                logger.warning("[tennis-runner] lettura follow KO per RETE (%s): riprovo "
                               "tra 15s, il processo resta vivo.", str(e)[:160])
                time.sleep(15.0)
                continue
            if only_event:
                follows = [f for f in follows if f["event_id"] == only_event]
            else:
                # 25/09 (F8): le partite chieste dai comandi dei bot entrano con la build
                session.ultimi_follows = list(follows)
                follows = _ET.follows_con_comandi(session, follows)
            if not follows:
                if os.getenv("LIVE_RUNNER_KEEP_ALIVE", "").strip() == "1":
                    # PARITÀ COL CALCIO (review 17/07, "Trading immediato"):
                    # l'attesa idle era 15s fissi — un follow tennis nuovo
                    # poteva aspettare fino a 15s prima dell'aggancio. Default
                    # 2s (SELECT leggera), env per tarare.
                    _idle_s = float(os.getenv("TENNIS_IDLE_FOLLOW_POLL_SEC", "2.0")) or 2.0
                    logger.info("[tennis-runner] nessun evento: attendo (keep-alive desktop).")
                    _pubblica_battito_attesa()   # 25/09 (punto 6), a ogni giro di attesa
                    time.sleep(_idle_s)
                    # sessione .it: keepAlive ogni ~8 min o scade per inattività
                    # (soglia in CICLI derivata dallo sleep: ~480s reali).
                    _ka_every = max(1, int(480.0 / _idle_s))
                    _ka = getattr(session, "_idle_ka_count", 0) + 1
                    session._idle_ka_count = _ka
                    if _ka % _ka_every == 0:
                        try:
                            from ..auth import keep_alive as _bf_keep_alive
                            _bf_keep_alive(session.trading)
                            logger.info("[tennis-runner] keepAlive sessione Betfair ok (idle).")
                        except Exception as _ex:  # noqa: BLE001
                            logger.warning("[tennis-runner] keepAlive KO: %s", str(_ex)[:120])
                    continue
                logger.warning("[tennis-runner] nessun evento tennis da streammare.")
                break

            session.market_meta.clear()
            session.reset_streams()
            # 25/09: la build rientra nel tetto (limite Betfair 200 per connessione)
            follows = _entro_il_tetto_al_build(follows)
            for f in follows:
                _catalog_follow(session, f)
            if not session.market_meta:
                if os.getenv("LIVE_RUNNER_KEEP_ALIVE", "").strip() == "1":
                    logger.info("[tennis-runner] nessun mercato: attendo (keep-alive desktop).")
                    _pubblica_battito_attesa()   # 25/09 (punto 6)
                    time.sleep(15)
                    continue
                logger.warning("[tennis-runner] nessun mercato sottoscrivibile.")
                break

            mode = live_order_mode()
            # fix audit #14: mode CATTURATA al build — gli specchi (ordini bot,
            # posizioni) usano questa, così non possono divergere dalla mode con
            # cui il client/gli ordini sono stati costruiti se l'env cambia dopo.
            session.order_mode = mode
            client, orders_enabled = build_order_client(trading, mode)
            data_filter = streaming_market_data_filter(
                fields=list(STREAM_FIELDS), ladder_levels=LADDER_DEPTH
            )
            framework = Flumine(client=client)
            # K1 (26/09): size/volumi dello stream in GBP -> EUR, PRIMO middleware
            _valuta.monta_su_flumine(framework)
            _wire_paper_execution(framework, mode)
            # T1 (24/09) - in LIVE si AFFIANCA al client reale un client SIMULATO,
            # come nel runner calcio (F0): i bot dichiarati PAPER piazzano su di lui
            # (``_instantiate_bot(..., client_paper=...)``). Se non si costruisce,
            # i bot paper nascono in dry-run forzato: mai sul client reale.
            client_paper = None
            if str(mode).strip().upper() == "LIVE":
                try:
                    client_paper = _gt.build_client_paper_affiancato(trading)
                    framework.add_client(client_paper)
                    # il paper affiancato dorme il betDelay VIGENTE come il runner
                    # PAPER (fix GAP-5): stessa esecuzione simulata
                    install_fresh_delay_execution(framework)
                    logger.info("[tennis-runner] T1: client PAPER affiancato al client "
                                "REALE (%s): i bot 'paper' non toccano mai l'Exchange.",
                                client_paper.username)
                except Exception as e:  # noqa: BLE001 - fail-closed: bot paper in dry-run
                    logger.error("[tennis-runner] client PAPER affiancato NON costruito: "
                                 "i bot 'paper' nasceranno in dry-run forzato: %s", e)
                    client_paper = None
            if orders_enabled:
                # T1 seconda rete + T2 kill-switch, DENTRO flumine (ogni place, anche
                # quello di un bot, passa di qui prima di andare al client)
                framework.add_trading_control(_gt.ControlloModalitaBotTennis)
                framework.add_trading_control(_gt.ControlloKillSwitchTennis)
            # 23/09 - saldo del conto riletto dopo ogni ordine REALE confermato
            # (ladder tennis e 4 bot) e ogni regolazione: una chiamata per
            # evento, ordini simulati ignorati, SOLO in LIVE.
            if str(mode).strip().upper() == "LIVE":
                _attiva_saldo_su_evento(framework, trading)

            # UNA capture per TUTTI gli eventi (stream unico cross-evento, vedi
            # _make_capture): mappata sotto ogni event_id per i consumer esistenti
            # (ladder/now/ordini leggono il PROPRIO mercato via latest_for).
            # 25/09: filtro CANONICO (ordinato): l'iscrizione a caldo e i bot armati
            # a caldo usano lo stesso dizionario, o flumine aprirebbe un'altra
            # sottoscrizione (``_IAC.filtro_mercati``)
            all_market_ids = sorted({str(m["market_id"]) for m in session.market_meta.values()})
            shared_cap = _make_capture(all_market_ids[0], "*", market_ids=all_market_ids)
            shared_cap.market_data_filter = data_filter
            framework.add_strategy(shared_cap)
            # T2 (24/09): a guardia d'avvio armata (ripresa non riuscita) NESSUN bot
            # si arma; le righe restano 'requested' e si armano al restart che il
            # bot_control_worker chiede appena la ripresa riesce.
            guardia_armata = _gt.guardia_blocca()
            if guardia_armata:
                logger.error("[tennis-runner] guardia d'avvio ARMATA: nessun bot armato "
                             "in questo giro (ripresa non ancora riuscita).")
            for event_id, meta in session.market_meta.items():
                cap = shared_cap
                session.capture[event_id] = cap
                desiderati = {} if guardia_armata else _desired_controls(event_id)
                for bot_key, ctrl in desiderati.items():
                    tennis_db.set_tennis_bot_status(event_id, bot_key, "arming")
                    sink = _make_sink(event_id, bot_key)
                    try:
                        bot = _instantiate_bot(
                            bot_key, ctrl, meta["market_id"], meta["name_to_sel"], sink,
                            data_filter, mode, market_ids=all_market_ids,
                            client_paper=client_paper,
                            competition_name=meta.get("competition_name"),
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
                    _scrivi_attivita_modalita(event_id, bot_key, bot, mode)
                    _scrivi_superficie(event_id, bot_key, bot, ctrl)

            # 23/09: il worker gira alla cadenza del CANALE (mai < 20 ms); il DB
            # resta a LADDER_PUBLISH_SEC dentro il worker (ladder_canale.py).
            framework.add_worker(BackgroundWorker(
                framework, function=ladder_worker,
                interval=_lcad.stato_della_sessione(
                    session, LADDER_PUBLISH_SEC, LADDER_CANALE_MS).intervallo_worker(),
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
                framework, function=bot_control_worker, interval=_intervallo_bot_control(),
                func_kwargs={"session": session}, name="tennis_bot_control"))
            # registrazione opt-in per-partita: allinea il tee raw al flag `record`
            framework.add_worker(BackgroundWorker(
                framework, function=record_flag_worker, interval=RECORD_POLL_SEC or 5.0,
                func_kwargs={"session": session}, name="tennis_record"))
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
            # R-STREAM-1 (26/09): stallo dello stream (stessa cadenza del battito calcio)
            framework.add_worker(BackgroundWorker(
                framework, function=stall_worker, interval=10.0,
                func_kwargs={"session": session}, name="tennis_stall"))

            for event_id in session.market_meta:
                if event_id in session.comandi and not any(
                        str(f.get("event_id")) == event_id and not _ET.e_comando(f)
                        for f in follows):
                    continue             # 25/09 (F8): partita di un comando, nessuna riga
                tennis_db.set_tennis_follow_status(event_id, "STREAMING")
            # 25/09 - ISCRIZIONE/ARMAMENTO A CALDO: da qui in poi partite nuove e
            # bot nuovi entrano nel framework VIVO (stessi data_filter, modalita'
            # di build e client paper di questa build), senza ricostruire.
            session.caldo = (ContestoCaldo(framework, shared_cap, data_filter, mode,
                                           client_paper)
                             if _IAC.acceso() else None)
            logger.info("[tennis-runner] stream avviato: %d eventi, %d bot ospitati, "
                        "1 connessione Betfair (%d mercati).",
                        len(session.market_meta), len(session.hosted), len(all_market_ids))
            # 25/09 (F8): il motore e l'aggancio lavorano su QUESTO framework
            # (i comandi delle modalita' servibili: ``orders_enabled``)
            _motore = _MOTORE_TENNIS.get("motore")
            _aggancio = _MOTORE_TENNIS.get("aggancio")
            if _motore is not None and orders_enabled:
                session.attesa_libro.clear()     # book del framework di prima: morti
                _motore.aggancia(framework, session)
                if _aggancio is not None:
                    _aggancio.aggancia(framework)
            session.stream_started_monotonic = time.monotonic()  # R-STREAM-1 (26/09)
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
                    session.caldo = None
                    time.sleep(5.0)
                    continue
            session.caldo = None     # framework fermo: niente piu' lavori a caldo
            if _MOTORE_TENNIS.get("motore") is not None:
                _MOTORE_TENNIS["motore"].sgancia()   # framework morto: comandi rifiutati
                if _MOTORE_TENNIS.get("aggancio") is not None:
                    _MOTORE_TENNIS["aggancio"].sgancia()
            if session.shutdown_requested.is_set():
                logger.info("[tennis-runner] auto-spegnimento: esco.")
                break
            if session.restart_requested.is_set() and not interrupted:
                logger.info("[tennis-runner] ricostruzione stream…")
                continue
            break
    finally:
        _smonta_motore_tennis()          # 25/09 (F8): no-op se non montato
        try:
            RAW_TEE.close()  # chiusura pulita dei file di registrazione (best-effort)
        except Exception as e:  # noqa: BLE001
            logger.debug("[tennis-rec] close KO (ignorato): %s", e)
        safe_logout(trading)
    global _PLANNED_RESTART  # noqa: PLW0603 - letto da _main per l'exit code
    _PLANNED_RESTART = bool(getattr(session, "planned_restart", False))
    return sorted(session.market_meta.keys())


_PLANNED_RESTART = False


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
    if _PLANNED_RESTART:
        logger.info("[tennis-runner] ricambio pianificato (vita massima, desktop): exit %d.",
                    EXIT_PLANNED_RESTART)
        raise SystemExit(EXIT_PLANNED_RESTART)


if __name__ == "__main__":
    _main()
