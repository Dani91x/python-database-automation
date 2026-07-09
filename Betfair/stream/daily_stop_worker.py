"""daily_stop_worker.py — E34: STOP GIORNALIERO DI CONTO (kill-switch automatico).

BackgroundWorker del RUNNER (registrato SOLO con LIVE_ORDER_MODE ∈ {PAPER, LIVE}).
Ad ogni ciclo:

  1. (LIVE) sweep dei CLEARED ORDERS Betfair già arrivati sui mercati chiusi
     (flumine ``poll_market_closure`` → ``order.cleared_order``) → upsert del
     P&L realizzato per mercato in ``betfair_live_settled`` (write-on-change).
     In PAPER il settled è scritto da ``LiveTradingStrategy.process_closed_market``
     (``order.simulated.profit``) alla chiusura del mercato.
  2. Calcola il P&L DI GIORNATA dalla fonte autoritativa:
       realized (betfair_live_settled, giornata locale) + MTM aperto (blotter
       flumine + best prices del market_book) → ``trading.daily_pnl`` (math pura).
  3. Pubblica lo stato in ``betfair_live_risk_state`` (singleton, realtime → top bar).
  4. Se ``daily_loss_limit`` (betfair_live_settings) è sfondato → chiama la RPC
     ``set_live_kill_switch(true)`` + alert CRITICAL + riga di audit. Da quel
     momento il worker ordini blocca ogni place e permette SOLO le chiusure
     (``_CLOSING_ACTIONS``): comportamento già esistente del kill-switch.

MONEY-CRITICAL:
  * MAI un falso scatto silenzioso: l'attivazione è SEMPRE accompagnata da alert
    CRITICAL + audit; limite assente/invalido → stop spento (e alert WARN se
    invalido, una volta per giornata).
  * MAI un mancato scatto: prezzi mancanti → MTM worst-case (conservativo,
    anticipa lo scatto); dati settled corrotti → alert CRITICAL esplicito
    (mai trattati come 0); RPC kill fallita → alert CRITICAL + retry al ciclo
    successivo (lo stato resta "da scattare").
  * Il kill-switch NON viene mai riacceso/spento in automatico oltre allo
    scatto: disattivarlo è SEMPRE una decisione esplicita dell'utente. Se lo
    riattiva con il P&L ancora oltre soglia, lo stop riscatta (con nuovo alert).

Testabile a unità: supabase/flumine/strategy mockabili, nessuna rete.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import live_order_worker as low
from .trading import daily_pnl

logger = logging.getLogger(__name__)

_SETTLED_TABLE = "betfair_live_settled"

# Fuso della "giornata" dello stop: PINNATO a Europe/Rome (fix review HIGH — l'utente
# ragiona in ora italiana e il runner potrebbe girare su una macchina in UTC; un fuso
# di sistema diverso sposterebbe silenziosamente il reset giornaliero). Override via env.
_TZ_NAME = "LIVE_DAILY_STOP_TZ"
_TZ_DEFAULT = "Europe/Rome"

# write-on-change: firma dell'ultimo stato pubblicato / degli ultimi settled scritti.
# Un market_id presente in _LAST_SETTLED_SIG significa "realized già PERSISTITO nel DB
# con successo": è la condizione con cui il mercato chiuso esce dal calcolo MTM.
_LAST_STATE_SIG: Optional[Tuple] = None
_LAST_SETTLED_SIG: Dict[str, Tuple] = {}
# anti-spam: giornata per cui l'alert "limite invalido" / "dati corrotti" è già uscito.
_WARNED_DAY: Dict[str, str] = {}
# anti-flood per condizioni URGENTI ma persistenti (kill fallito, posizioni illeggibili):
# l'alert si RIPETE (il problema resta grave) ma con cooldown, mai ogni ciclo da 5s.
_ALERT_LAST_TS: Dict[str, float] = {}
_ALERT_COOLDOWN_SEC = 60.0


def _alert(level: str, msg: str) -> None:
    try:
        from . import db

        db.insert_alert(level, "DAILY_STOP", msg)
    except Exception:  # noqa: BLE001 - alert best-effort
        pass


def _warn_once(key: str, day: str, level: str, msg: str) -> None:
    """Alert al massimo UNA volta per giornata per ciascuna chiave (anti-spam)."""
    if _WARNED_DAY.get(key) == day:
        return
    _WARNED_DAY[key] = day
    _alert(level, msg)


def _alert_cooldown(key: str, level: str, msg: str) -> None:
    """Alert RIPETUTO con cooldown (fix review HIGH: condizioni persistenti e urgenti
    non devono né sparire dopo il primo avviso né floodare il canale ogni 5s)."""
    import time

    now = time.monotonic()
    if now - _ALERT_LAST_TS.get(key, -1e12) < _ALERT_COOLDOWN_SEC:
        return
    _ALERT_LAST_TS[key] = now
    _alert(level, msg)


def _tzinfo() -> Any:
    """ZoneInfo del fuso della giornata (default Europe/Rome). Fallback ESPLICITO
    (WARN una volta) al fuso di sistema se il database tz non è disponibile."""
    import os

    name = os.getenv(_TZ_NAME, _TZ_DEFAULT).strip() or _TZ_DEFAULT
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - tzdata assente/nome invalido
        _warn_once(
            "tz_fallback",
            datetime.now(timezone.utc).date().isoformat(),
            "WARN",
            f"STOP GIORNALIERO: fuso '{name}' non disponibile — uso il fuso di sistema "
            "(la giornata potrebbe non coincidere con la mezzanotte italiana).",
        )
        return None


def _now_local() -> datetime:
    """Ora nella timezone della giornata (Europe/Rome), timezone-aware e DST-corretta."""
    tz = _tzinfo()
    if tz is not None:
        return datetime.now(tz)
    return datetime.now().astimezone()


def _daily_loss_limit() -> Tuple[Optional[float], bool]:
    """(limite, presente_ma_invalido) da betfair_live_settings (snapshot del ciclo)."""
    raw = low._SETTINGS.get("daily_loss_limit")
    if raw is None:
        return None, False
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None, True
    if not (val > 0):
        return None, True
    return val, False


# ---------------------------------------------------------------------------
# 1) Sweep LIVE dei cleared orders → betfair_live_settled
# ---------------------------------------------------------------------------
def _cleared_profit(order: Any) -> Optional[float]:
    """Profit del cleared order Betfair (resource o dict). None = non ancora cleared."""
    cleared = low._val(order, "cleared_order")
    if cleared is None:
        return None
    if isinstance(cleared, dict):
        return low._f(cleared.get("profit"))
    return low._f(low._val(cleared, "profit"))


def _simulated_profit(order: Any) -> Optional[float]:
    """Profit SIMULATO flumine (autoritativo in PAPER). None = non disponibile."""
    sim = low._val(order, "simulated")
    if sim is None:
        return None
    return low._f(low._val(sim, "profit"))


def _order_realized_profit(order: Any, mode_l: str) -> Optional[float]:
    """Profit realizzato di UN ordine per la mode: LIVE = cleared orders Betfair
    (verità ultima del conto), PAPER = SimulatedExecution flumine."""
    if mode_l == "live":
        return _cleared_profit(order)
    return _simulated_profit(order)


def _sweep_settled(sb: Any, flumine: Any, mode_l: str, strategy: Any) -> None:
    """Upsert del P&L REALIZZATO per i mercati CHIUSI → betfair_live_settled.

    LIVE  → somma dei cleared orders Betfair già arrivati (poll_market_closure).
    PAPER → somma di order.simulated.profit: è il BACKSTOP con retry di
            LiveTradingStrategy.process_closed_market (fix review CRITICAL: la
            scrittura alla chiusura è one-shot — un blip DB in quel momento non
            deve mai perdere per sempre il P&L del mercato). Upsert idempotente
            sulla stessa chiave (mode, market_id): nessun doppio conteggio.
    Write-on-change per mercato; un upsert riuscito registra il mercato in
    _LAST_SETTLED_SIG → da quel momento esce dal calcolo MTM (realized nel DB).
    """
    markets = low._val(low._val(flumine, "markets"), "markets") or {}
    for market_id, market in dict(markets).items():
        if not low._val(market, "closed"):
            continue
        blotter = low._val(market, "blotter")
        if blotter is None or strategy is None:
            continue
        try:
            orders = list(blotter.strategy_orders(strategy))
        except Exception:  # noqa: BLE001 - blotter mock/edge
            continue
        total = 0.0
        count = 0
        for order in orders:
            profit = _order_realized_profit(order, mode_l)
            if profit is None:
                continue
            total += profit
            count += 1
        if count == 0:
            # fix review CRITICAL (gap cleared LIVE): mercato chiuso con nostri ordini
            # ma senza P&L realizzato disponibile → resta nel calcolo MTM (worst-case)
            # e, se il ritardo persiste, lo si DICHIARA (mai un buco silenzioso).
            if orders and mode_l == "live":
                elapsed = low._f(low._val(market, "elapsed_seconds_closed"))
                if elapsed is not None and elapsed > 120:
                    _alert_cooldown(
                        f"cleared_gap:{market_id}",
                        "WARN",
                        f"STOP GIORNALIERO: mercato {market_id} chiuso da {int(elapsed)}s "
                        "senza cleared orders Betfair — P&L stimato worst-case nel frattempo.",
                    )
            continue
        sig = (round(total, 2), count)
        if _LAST_SETTLED_SIG.get(market_id) == sig:
            continue
        row = {
            "mode": mode_l,
            "event_id": low._val(market, "event_id"),
            "market_id": market_id,
            "market_name": low._val(low._val(market, "market_catalogue"), "market_name"),
            "profit": round(total, 2),
            "orders": count,
            "source": "cleared" if mode_l == "live" else "simulated",
        }
        try:
            from . import db

            db.upsert_live_settled(row)
            _LAST_SETTLED_SIG[market_id] = sig
        except Exception as ex:  # noqa: BLE001 - retry al prossimo ciclo
            logger.warning("[daily-stop] upsert settled KO %s: %s", market_id, str(ex)[:200])


# ---------------------------------------------------------------------------
# 2) P&L di giornata: realized (DB) + MTM aperto (blotter)
# ---------------------------------------------------------------------------
def _read_realized(sb: Any, mode_l: str, start_iso: str, end_iso: str) -> float:
    """Somma dei profit settled della giornata. Dati corrotti → ValueError (loud)."""
    res = (
        sb.table(_SETTLED_TABLE)
        .select("profit")
        .eq("mode", mode_l)
        .gte("settled_at", start_iso)
        .lt("settled_at", end_iso)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    return daily_pnl.realized_pnl(rows)


def _open_positions(flumine: Any, strategy: Any) -> Tuple[List[daily_pnl.OpenPosition], int]:
    """Snapshot delle posizioni della strategia dai blotter flumine, per l'MTM.

    Include: mercati APERTI + mercati CHIUSI il cui realized NON è ancora stato
    persistito in betfair_live_settled (fix review CRITICAL: in LIVE i cleared
    orders arrivano minuti dopo la chiusura — in quella finestra il mercato NON
    deve sparire dal P&L di giornata; senza prezzi utilizzabili la posizione
    viene valutata worst-case da daily_pnl.open_mtm, conservativo per costruzione).
    Ritorna (posizioni, n_illeggibili). Una posizione illeggibile NON viene
    ignorata in silenzio: il chiamante degrada la stima e avvisa CRITICAL.
    """
    positions: List[daily_pnl.OpenPosition] = []
    unreadable = 0
    markets = low._val(low._val(flumine, "markets"), "markets") or {}
    for market_id, market in dict(markets).items():
        if low._val(market, "closed") and market_id in _LAST_SETTLED_SIG:
            continue  # realized già persistito nel DB → mai doppio conteggio
        blotter = low._val(market, "blotter")
        if blotter is None or strategy is None:
            continue
        try:
            orders = list(blotter.strategy_orders(strategy))
        except Exception:  # noqa: BLE001
            continue
        lookups = set()
        for order in orders:
            lookup = low._val(order, "lookup")
            if lookup is not None:
                lookups.add(lookup)
        for lookup in lookups:
            try:
                exp = blotter.get_exposures(strategy, lookup)
                if not isinstance(exp, dict):
                    raise ValueError("get_exposures non-dict")
                best_back, best_lay = low._best_prices(market, lookup[1], lookup[2])
                positions.append(
                    daily_pnl.OpenPosition(
                        matched_if_win=low._f(exp.get("matched_profit_if_win")) or 0.0,
                        matched_if_lose=low._f(exp.get("matched_profit_if_lose")) or 0.0,
                        best_back=best_back,
                        best_lay=best_lay,
                        worst_if_win=low._f(exp.get("worst_possible_profit_on_win")) or 0.0,
                        worst_if_lose=low._f(exp.get("worst_possible_profit_on_lose")) or 0.0,
                    )
                )
            except Exception:  # noqa: BLE001 - MAI ignorare in silenzio: si degrada
                unreadable += 1
    return positions, unreadable


# ---------------------------------------------------------------------------
# 3) Pubblicazione stato + 4) attivazione kill-switch
# ---------------------------------------------------------------------------
def _publish_state(
    mode_l: str, day: str, decision: daily_pnl.DailyStopDecision, kill_on: bool
) -> None:
    """betfair_live_risk_state (singleton, realtime) — write-on-change."""
    global _LAST_STATE_SIG
    sig = (
        mode_l,
        day,
        round(decision.realized, 2),
        round(decision.open_mtm, 2),
        decision.limit,
        decision.fire,
        kill_on,
    )
    if _LAST_STATE_SIG == sig:
        return
    row = {
        "mode": mode_l,
        "day": day,
        "realized": round(decision.realized, 2),
        "open_mtm": round(decision.open_mtm, 2),
        "total": round(decision.total or 0.0, 2),
        "limit_value": decision.limit,
        "stop_fired": bool(decision.fire),
        "detail": {
            "reason": decision.reason,
            "degraded": decision.degraded,
            "kill_switch": kill_on,
        },
    }
    try:
        from . import db

        db.upsert_live_risk_state(row)
        _LAST_STATE_SIG = sig
    except Exception as ex:  # noqa: BLE001 - retry al prossimo ciclo
        logger.warning("[daily-stop] publish state KO: %s", str(ex)[:200])


def _activate_kill(sb: Any, mode_l: str, decision: daily_pnl.DailyStopDecision) -> bool:
    """set_live_kill_switch(true) VERIFICATO. False = attivazione fallita (retry).

    MAI silenzioso: successo → alert CRITICAL + audit; fallimento → alert CRITICAL.
    """
    try:
        res = sb.rpc("set_live_kill_switch", {"p_on": True}).execute()
        data = getattr(res, "data", None)
        confirmed = isinstance(data, dict) and bool(data.get("kill_switch"))
    except Exception as ex:  # noqa: BLE001
        # fix review HIGH: alert RIPETUTO ma con cooldown — il retry dell'RPC resta a
        # OGNI ciclo, l'alert no (mai floodare il canale proprio durante l'emergenza).
        _alert_cooldown(
            "kill_fallito",
            "CRITICAL",
            f"STOP GIORNALIERO: attivazione kill-switch FALLITA ({str(ex)[:120]}) — "
            f"P&L giornata €{decision.total:.2f} oltre il limite −€{decision.limit:.2f}. RETRY.",
        )
        return False
    if not confirmed:
        _alert_cooldown(
            "kill_non_confermato",
            "CRITICAL",
            "STOP GIORNALIERO: set_live_kill_switch NON confermato dal DB — RETRY.",
        )
        return False
    _alert(
        "CRITICAL",
        f"STOP GIORNALIERO SCATTATO ({mode_l.upper()}): P&L giornata €{decision.total:.2f} "
        f"(settled €{decision.realized:.2f} + MTM €{decision.open_mtm:.2f}) ≤ "
        f"−€{decision.limit:.2f}. Kill-switch ATTIVATO: solo chiusure permesse."
        + (" [stima worst-case: prezzi mancanti]" if decision.degraded else ""),
    )
    try:
        sb.table("betfair_live_audit").insert(
            {
                "mode": mode_l,
                "action": "daily_stop",
                "status": "done",
                "detail": {
                    "realized": round(decision.realized, 2),
                    "open_mtm": round(decision.open_mtm, 2),
                    "total": round(decision.total or 0.0, 2),
                    "limit": decision.limit,
                    "degraded": decision.degraded,
                },
            }
        ).execute()
    except Exception:  # noqa: BLE001 - audit best-effort (l'alert CRITICAL è già uscito)
        pass
    return True


# ---------------------------------------------------------------------------
# Ciclo
# ---------------------------------------------------------------------------
def _process_once(sb: Any, flumine: Any, strategy: Any = None) -> None:
    mode = low._live_order_mode()
    if mode not in ("PAPER", "LIVE"):
        return
    mode_l = mode.lower()
    low._refresh_settings(sb)

    now_local = _now_local()
    day = now_local.date().isoformat()

    # settled sweep per ENTRAMBE le mode: LIVE = cleared orders Betfair; PAPER =
    # backstop con retry del settle one-shot della strategy (fix review CRITICAL).
    _sweep_settled(sb, flumine, mode_l, strategy)

    limit, invalid = _daily_loss_limit()
    if invalid:
        _warn_once(
            "limit_invalid",
            day,
            "WARN",
            "STOP GIORNALIERO: daily_loss_limit presente ma INVALIDO (dev'essere > 0) — stop SPENTO.",
        )

    start_utc, end_utc = daily_pnl.day_window_utc(now_local)
    try:
        realized = _read_realized(sb, mode_l, start_utc.isoformat(), end_utc.isoformat())
    except ValueError as ex:
        _warn_once(
            "settled_corrotti",
            day,
            "CRITICAL",
            f"STOP GIORNALIERO: dati settled ILLEGGIBILI ({str(ex)[:120]}) — "
            "P&L di giornata NON verificabile.",
        )
        return
    except Exception as ex:  # noqa: BLE001 - DB momentaneamente KO → retry
        logger.warning("[daily-stop] lettura settled KO: %s", str(ex)[:200])
        return

    positions, unreadable = _open_positions(flumine, strategy)
    try:
        mtm, degraded = daily_pnl.open_mtm(positions)
    except ValueError as ex:
        _warn_once(
            "mtm_corrotto",
            day,
            "CRITICAL",
            f"STOP GIORNALIERO: esposizioni ILLEGGIBILI ({str(ex)[:120]}) — "
            "MTM di giornata NON verificabile.",
        )
        return
    if unreadable:
        # fix review CRITICAL: una posizione illeggibile è un BUCO di rischio non
        # quantificabile (contribuisce zero all'MTM) → CRITICAL, e RIPETUTO finché
        # persiste (cooldown anti-flood), mai un WARN una-tantum che poi sparisce.
        degraded = True
        _alert_cooldown(
            "posizioni_illeggibili",
            "CRITICAL",
            f"STOP GIORNALIERO: {unreadable} posizioni NON leggibili dal blotter — "
            "esposizione NON quantificata nel P&L di giornata (stima per difetto). "
            "Verifica il runner: lo stop potrebbe scattare in ritardo.",
        )

    decision = daily_pnl.evaluate_daily_stop(realized, mtm, limit, degraded=degraded)

    kill_on = low._db_kill_switch()
    if decision.fire and not kill_on:
        if _activate_kill(sb, mode_l, decision):
            kill_on = True

    _publish_state(mode_l, day, decision, kill_on)


def daily_stop_worker(context: Any, flumine: Any, session: Any = None, strategy: Any = None) -> None:
    """Entry BackgroundWorker (vedi runner.py). Non solleva MAI."""
    if flumine is None:
        return
    try:
        from db_client import get_supabase_client

        sb = get_supabase_client()
    except Exception as ex:  # noqa: BLE001 - DB non raggiungibile: salta il giro
        logger.warning("[daily-stop] client supabase KO: %s", str(ex)[:200])
        return
    try:
        _process_once(sb, flumine, strategy)
    except Exception as ex:  # noqa: BLE001 - il worker non deve mai far cadere il runner
        logger.exception("[daily-stop] ciclo KO: %s", str(ex)[:200])
