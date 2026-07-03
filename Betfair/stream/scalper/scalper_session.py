"""SESSIONE SCALPER per UN evento — PROCESSO DEDICATO.

Ogni partita gira in un processo separato con il PROPRIO login Betfair e la
PROPRIA istanza flumine: e' l'architettura per cui flumine e' progettato.
(Due framework nello stesso processo con un client condiviso producevano
WinError 10035 sui socket dello stream — visto live il 02/07.)

Avvio (dal servizio supervisore, o a mano per debug):
    python -m Betfair.stream.scalper.scalper_session <event_id>

Il processo: legge la sua riga in ``scalper_control``, arma il bot (connettore
bias per mode bias/both), gira fino a stop UI ('stopping'), kill-switch
(file STOP_SCALPER), o KO+10' — poi chiude flat, scrive lo stato finale ed esce.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

KILL_FILE = "STOP_SCALPER"
HEARTBEAT_S = 5.0

# default VALIDATI (grid 02/07) + protezioni live
VALIDATED_PARAMS: Dict[str, Any] = {
    "mode": "auto", "allow_inplay": False,
    "scalp_ticks": 1, "stop_ticks": 1,
    "entry_ttl_ms": 600_000, "lock_ttl_ms": 3_600_000, "max_cycles": 500,
    "min_size": 150.0, "min_flow": 10.0, "flow_window_ms": 90_000,
    "warmup_ms": 60_000, "price_min": 1.50, "price_max": 4.6,
    "join_max_spread": 2, "improve_inside": True, "reprice_ticks": 2,
    "capture_min_ticks": 3, "capture_max_ticks": 10,
    "max_signal_ticks": 4, "signal_window_ms": 15_000, "cooldown_ms": 30_000,
    "flatten_before_s": 180.0, "entry_stop_before_s": 420.0, "wom_block": 0.90,
    # protezioni LIVE (exchange .it): min bet 2€, size in multipli di 0,50€
    # (verificato: INVALID_BET_SIZE altrimenti), anti-churn flatten 1,5s
    "live_min_bet": 2.0, "size_step": 0.5, "max_txn_hour": 300,
    "flatten_min_interval_ms": 1500,
    # uscite a SIZE ESATTA (come i tool pro): parte diretta + resto via
    # park-trim-replace (trading/submin.py) → si esce con qualsiasi importo
    "exact_exits": True,
    # PROTEZIONI DI REDDITO PER EVENTO (certificate 03/07): target col
    # cricchetto (raggiunto 1€ si continua ma i profitti sono protetti) e
    # tetto di perdita che scatena il force-flat totale.
    "event_profit_target": 1.0, "event_target_giveback": 0.30,
    "event_loss_cap": 1.5,
}
UI_PARAM_WHITELIST = {
    "scalp_ticks", "stop_ticks", "min_size", "min_flow", "price_min",
    "price_max", "join_max_spread", "improve_inside", "reprice_ticks",
    "capture_min_ticks", "capture_max_ticks", "max_signal_ticks",
    "cooldown_ms", "flatten_before_s", "entry_stop_before_s", "wom_block",
    "entry_ttl_ms", "lock_ttl_ms", "max_cycles", "max_txn_hour",
    "event_profit_target", "event_target_giveback", "event_loss_cap",
    "ht_mode",
    "flow_balance_min", "flow_balance_window_ms", "min_inside_flow",
    "require_oscillation", "trend_mode", "max_drift_ticks",
}
SESSION_MARKET_TYPES = [
    "MATCH_ODDS", "OVER_UNDER_15", "OVER_UNDER_25", "OVER_UNDER_35",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Db:
    def __init__(self) -> None:
        from db_client import get_supabase_client
        self.sb = get_supabase_client()

    def set_control(self, event_id: str, **fields: Any) -> None:
        fields["updated_at"] = _now_iso()
        try:
            self.sb.table("scalper_control").update(fields) \
                .eq("event_id", event_id).execute()
        except Exception:  # noqa: BLE001
            logger.warning("[scalper-sess] set_control fallito", exc_info=True)

    def control_status(self, event_id: str) -> Optional[str]:
        try:
            r = self.sb.table("scalper_control").select("status") \
                .eq("event_id", event_id).execute()
            return (r.data or [{}])[0].get("status")
        except Exception:  # noqa: BLE001
            return None

    def get_control(self, event_id: str) -> Optional[Dict[str, Any]]:
        r = self.sb.table("scalper_control").select("*") \
            .eq("event_id", event_id).execute()
        return (r.data or [None])[0]

    def follow(self, event_id: str) -> Optional[Dict[str, Any]]:
        r = self.sb.table("live_follow").select("*") \
            .eq("event_id", event_id).execute()
        return (r.data or [None])[0]

    def prediction(self, fixture_id: Optional[int]) -> Optional[Dict[str, Any]]:
        if not fixture_id:
            return None
        r = self.sb.table("fixture_predictions").select(
            "fixture_id,league_id,model_predictions_json,db_json_analisi,"
            "created_at,updated_at"
        ).eq("fixture_id", fixture_id).execute()
        return (r.data or [None])[0]

    def log(self, event_id: str, kind: str, payload: Dict[str, Any]) -> None:
        try:
            self.sb.table("scalper_activity").insert({
                "event_id": event_id, "kind": kind,
                "payload": json.loads(json.dumps(payload, default=str)),
            }).execute()
        except Exception:  # noqa: BLE001
            logger.warning("[scalper-sess] log fallito", exc_info=True)

    def log_many(self, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        try:
            self.sb.table("scalper_activity").insert(rows).execute()
        except Exception:  # noqa: BLE001
            logger.warning("[scalper-sess] log batch fallito", exc_info=True)


def _resolve_bias(db: Db, trading: Any, follow: Dict[str, Any],
                  mo_market: Any) -> Dict[str, Any]:
    from .bias_resolver import match_runner_roles, resolve_bias

    pred = db.prediction(follow.get("fixture_id"))
    runner_names: Dict[int, str] = {}
    mid_probs: Optional[Dict[str, float]] = None
    if mo_market is not None:
        for r in getattr(mo_market, "runners", []) or []:
            runner_names[int(r.selection_id)] = str(r.runner_name)
        try:
            books = trading.betting.list_market_book(
                market_ids=[mo_market.market_id])
            probs: Dict[int, float] = {}
            for rb in (books[0].runners if books else []):
                atb = rb.ex.available_to_back or []
                atl = rb.ex.available_to_lay or []
                if atb and atl:
                    mid = (atb[0].price + atl[0].price) / 2.0
                    if mid > 1.0:
                        probs[int(rb.selection_id)] = 1.0 / mid
            roles = match_runner_roles(
                runner_names, follow.get("home_name") or "",
                follow.get("away_name") or "")
            if probs and roles:
                mid_probs = {role: probs.get(sid) for role, sid in roles.items()}
                if any(v is None for v in mid_probs.values()):
                    mid_probs = None
        except Exception:  # noqa: BLE001
            logger.warning("[scalper-sess] book MO non disponibile", exc_info=True)
    decision = resolve_bias(
        pred, runner_names,
        follow.get("home_name") or "", follow.get("away_name") or "",
        mid_probs,
    )
    return {"bias": decision.bias, "meta": decision.to_meta()}


def run_session(event_id: str) -> None:  # noqa: C901 - flusso lineare
    from flumine import Flumine, clients
    from betfairlightweight import filters

    from ..auth import build_client
    from .scalper_bot import ScalperStrategy

    db = Db()
    ev = event_id
    buf: List[Dict[str, Any]] = []
    buf_lock = threading.Lock()

    def sink(kind: str, payload: Dict[str, Any]) -> None:
        with buf_lock:
            buf.append({"event_id": ev, "kind": kind, "payload": payload})
            if len(buf) > 400:
                del buf[:200]

    def flush() -> None:
        with buf_lock:
            rows, buf[:] = list(buf), []
        db.log_many(rows)

    strategy = None
    framework = None
    stopped_by_ui = False
    try:
        control = db.get_control(ev)
        if not control or control.get("status") not in ("requested", "arming", "running"):
            raise RuntimeError(f"controllo non attivabile (status={control and control.get('status')})")
        db.set_control(ev, status="arming", started_at=_now_iso(), error=None)

        follow = db.follow(ev)
        if not follow:
            raise RuntimeError("evento non presente in live_follow")

        # login DEDICATO a questo processo (nessuna condivisione tra sessioni)
        trading = build_client(login=True)

        cat = trading.betting.list_market_catalogue(
            filter=filters.market_filter(
                event_ids=[ev], market_type_codes=SESSION_MARKET_TYPES),
            market_projection=["RUNNER_DESCRIPTION", "MARKET_START_TIME"],
            sort="MAXIMUM_TRADED", max_results=25,
        )
        if not cat:
            raise RuntimeError("nessun mercato validato trovato a catalogo")
        market_ids = [m.market_id for m in cat]
        mo = next((m for m in cat
                   if any(getattr(r, "runner_name", "") == "The Draw"
                          for r in (m.runners or []))), None)

        mode = str(control.get("mode") or "maker")
        bias: Dict[int, str] = {}
        meta: Dict[str, Any] = {"modalita": mode}
        if mode in ("bias", "both"):
            res = _resolve_bias(db, trading, follow, mo)
            bias = res["bias"]
            meta.update(res["meta"])
        db.set_control(ev, bias={str(k): v for k, v in bias.items()} or None,
                       bias_meta=meta)
        db.log(ev, "info", {"msg": "armato", "mode": mode,
                            "markets": market_ids, "bias_meta": meta,
                            "pid": os.getpid()})
        if mode == "bias" and not bias:
            db.set_control(ev, status="armed")
            return

        params = dict(VALIDATED_PARAMS)
        for k, v in dict(control.get("params") or {}).items():
            if k in UI_PARAM_WHITELIST:
                params[k] = v
        params["stake"] = float(control.get("stake") or 25.0)
        params["dry_run"] = bool(control.get("dry_run", True))
        params["bias"] = {str(k): v for k, v in bias.items()}
        params["only_bias"] = mode == "bias"
        # MODALITA' INTERVALLO (ht_mode, whitelistata): dopo il pre-match il
        # bot tradera' ANCHE l'intervallo (48'-59', zero rischio gol) con le
        # blindature certificate 03/07: finestra ingressi, max 3 cicli
        # concorrenti, circuit-breaker per-ciclo 0.50, cap evento 1.0.
        # Regola operativa: SOLO su partite habitat/GO (le elite non si
        # armano affatto: il loro intervallo e' invalicabile, -8 misurato).
        ht_mode = bool((control.get("params") or {}).get("ht_mode"))
        if ht_mode:
            params["allow_inplay"] = True
            params.setdefault("inplay_from_s", 2880.0)
            params.setdefault("inplay_to_s", 3540.0)
            params.setdefault("max_inplay_slots", 3)
            params.setdefault("cycle_loss_breaker", 0.50)
            params.setdefault("event_loss_cap", 1.0)
        else:
            params["allow_inplay"] = False

        price_max = float(params.get("price_max", 4.6))
        cap = params["stake"] * (price_max - 1.0) * 2.0
        # ⚠️ filtro nel formato STREAMING di Betfair (marketIds, camelCase):
        # con una chiave sconosciuta il filtro e' VUOTO e flumine si abbona a
        # TUTTO l'exchange → SUBSCRIPTION_LIMIT_EXCEEDED (visto live 02/07).
        strategy = ScalperStrategy(
            market_filter=filters.streaming_market_filter(
                market_ids=market_ids),
            scalper_params=params,
            event_sink=sink,
            max_selection_exposure=cap,
            max_order_exposure=cap,
            max_trade_count=int(1e6),
            max_live_trade_count=int(1e6),
        )
        # min_bet_validation=False COME IL RUNNER LIVE (fix CRITICAL-3 del
        # live-trading): l'OrderValidation di flumine (size>=1 o payout>=20)
        # non conosce le eccezioni Betfair (green-up sotto-minimo, park-trim)
        # e ci ha rifiutato 528 park LAY il 02/07. I minimi veri li garantisce
        # la strategia (side-aware + park legali).
        framework = Flumine(client=clients.BetfairClient(
            trading, min_bet_validation=False, order_stream=True,
        ))
        framework.add_strategy(strategy)
        db.set_control(ev, status="running", stats=strategy.stats)

        runner = threading.Thread(target=framework.run, daemon=True,
                                  name=f"flumine-{ev}")
        runner.start()

        ko_ts = None
        ko_iso = follow.get("open_date")
        if ko_iso:
            try:
                ko_ts = datetime.fromisoformat(
                    str(ko_iso).replace("Z", "+00:00")).timestamp()
            except ValueError:
                ko_ts = None

        while runner.is_alive():
            time.sleep(HEARTBEAT_S)
            flush()
            db.set_control(ev, heartbeat_at=_now_iso(), stats=strategy.stats)
            status = db.control_status(ev)
            if status == "stopping" or os.path.isfile(KILL_FILE):
                stopped_by_ui = status == "stopping"
                strategy.force_flat = True
                db.log(ev, "info", {"msg": "stop richiesto: force-flat"})
                time.sleep(12)   # tempo per chiudere flat da maker/cross
                break
            _life_s = 4200 if ht_mode else 600   # HT: vivo fino a ~KO+70'
            if ko_ts is not None and time.time() > ko_ts + _life_s:
                db.log(ev, "info", {"msg": "kickoff passato: fine sessione"})
                break
        try:
            framework._running = False  # noqa: SLF001 - stop documentato flumine
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
        flush()
        final = "stopped" if stopped_by_ui else "done"
        db.set_control(ev, status=final, stopped_at=_now_iso(),
                       stats=strategy.stats if strategy else None)
        db.log(ev, "info", {"msg": f"sessione {final}",
                            "stats": strategy.stats if strategy else None})
    except Exception as exc:  # noqa: BLE001
        logger.exception("[scalper-sess] sessione %s in errore", ev)
        flush()
        db.set_control(ev, status="error", error=str(exc)[:500],
                       stopped_at=_now_iso())
        db.log(ev, "error", {"msg": str(exc)[:500]})
        sys.exit(1)


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if len(sys.argv) < 2:
        raise SystemExit("uso: python -m Betfair.stream.scalper.scalper_session <event_id>")
    # repo root nel path (db_client, config) quando lanciato con -m dal root
    sys.path.insert(0, os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "..")))
    run_session(str(sys.argv[1]))


if __name__ == "__main__":
    main()
