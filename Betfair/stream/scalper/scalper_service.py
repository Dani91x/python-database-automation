"""SERVIZIO SCALPER — supervisore locale (processo SEPARATO dal runner).

Ciclo:
  1. polla ``scalper_control`` (service_role): righe 'requested' → ARMA:
     carica evento (live_follow), predizioni (fixture_predictions), catalogo
     mercati Betfair (REST), risolve il BIAS (bias_resolver, tre regole) e
     avvia una SESSIONE flumine live per l'evento (thread dedicato).
  2. righe 'stopping' → alza force_flat sulla strategia → chiusura garantita
     → 'stopped'.
  3. heartbeat + statistiche + log ``scalper_activity`` ogni pochi secondi.
  4. al kickoff il bot smette da solo (finestre KO validate); la sessione
     termina e lo stato diventa 'done'.

SICUREZZA:
  * ``dry_run`` (default TRUE da UI): NESSUN ordine reale, solo telemetria
    delle quote che il bot avrebbe piazzato → cablaggio verificabile a
    rischio zero.
  * kill-switch globale: file ``STOP_SCALPER`` nella cwd ferma tutto.
  * una sessione per evento; crash di una sessione → stato 'error', le
    altre continuano.

Avvio:  python -m Betfair.stream.scalper.scalper_service
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

KILL_FILE = "STOP_SCALPER"
POLL_S = 3.0
HEARTBEAT_S = 5.0
# mercati su cui lo scalper e' validato (dossier §9)
SESSION_MARKET_TYPES = [
    "MATCH_ODDS", "OVER_UNDER_15", "OVER_UNDER_25", "OVER_UNDER_35",
]
# default VALIDATI (grid 02/07) — la UI li mostra e puo' fare override via params
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
}
# chiavi che la UI puo' modificare (whitelist: tutto il resto viene ignorato)
UI_PARAM_WHITELIST = {
    "scalp_ticks", "stop_ticks", "min_size", "min_flow", "price_min",
    "price_max", "join_max_spread", "improve_inside", "reprice_ticks",
    "capture_min_ticks", "capture_max_ticks", "max_signal_ticks",
    "cooldown_ms", "flatten_before_s", "entry_stop_before_s", "wom_block",
    "entry_ttl_ms", "lock_ttl_ms", "max_cycles",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Accesso DB (service_role)
# ---------------------------------------------------------------------------
class Db:
    def __init__(self) -> None:
        from db_client import get_supabase_client
        self.sb = get_supabase_client()

    def pending_controls(self) -> List[Dict[str, Any]]:
        r = self.sb.table("scalper_control").select("*").in_(
            "status", ["requested", "stopping"]).execute()
        return r.data or []

    def set_control(self, event_id: str, **fields: Any) -> None:
        fields["updated_at"] = _now_iso()
        self.sb.table("scalper_control").update(fields) \
            .eq("event_id", event_id).execute()

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
        except Exception:  # noqa: BLE001 - il log non deve mai fermare il bot
            logger.warning("[scalper-svc] log fallito (%s %s)", event_id, kind,
                           exc_info=True)

    def log_many(self, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        try:
            self.sb.table("scalper_activity").insert(rows).execute()
        except Exception:  # noqa: BLE001
            logger.warning("[scalper-svc] log batch fallito", exc_info=True)


# ---------------------------------------------------------------------------
# Sessione per evento
# ---------------------------------------------------------------------------
class Session(threading.Thread):
    def __init__(self, db: Db, control: Dict[str, Any], trading: Any) -> None:
        super().__init__(daemon=True, name=f"scalper-{control['event_id']}")
        self.db = db
        self.event_id = str(control["event_id"])
        self.control = control
        self.trading = trading
        self.strategy = None
        self.framework = None
        self._buf: List[Dict[str, Any]] = []
        self._buf_lock = threading.Lock()
        self.stop_requested = threading.Event()

    # ---- sink telemetria della strategia (thread flumine) ----
    def sink(self, kind: str, payload: Dict[str, Any]) -> None:
        with self._buf_lock:
            self._buf.append({"event_id": self.event_id, "kind": kind,
                              "payload": payload})
            if len(self._buf) > 400:      # bound di sicurezza
                del self._buf[:200]

    def _flush(self) -> None:
        with self._buf_lock:
            rows, self._buf = self._buf, []
        self.db.log_many(rows)

    # ---- risoluzione del bias (connettore) ----
    def _resolve_bias(self, follow: Dict[str, Any], mo_market: Any) -> Dict[str, Any]:
        from .bias_resolver import resolve_bias
        pred = self.db.prediction(follow.get("fixture_id"))
        runner_names: Dict[int, str] = {}
        mid_probs: Optional[Dict[str, float]] = None
        if mo_market is not None:
            for r in getattr(mo_market, "runners", []) or []:
                runner_names[int(r.selection_id)] = str(r.runner_name)
            # prob implicite dal book corrente (REST list_market_book)
            try:
                books = self.trading.betting.list_market_book(
                    market_ids=[mo_market.market_id])
                probs: Dict[int, float] = {}
                for rb in (books[0].runners if books else []):
                    atb = rb.ex.available_to_back or []
                    atl = rb.ex.available_to_lay or []
                    if atb and atl:
                        mid = (atb[0].price + atl[0].price) / 2.0
                        if mid > 1.0:
                            probs[int(rb.selection_id)] = 1.0 / mid
                if probs:
                    from .bias_resolver import match_runner_roles
                    roles = match_runner_roles(
                        runner_names, follow.get("home_name") or "",
                        follow.get("away_name") or "")
                    if roles:
                        mid_probs = {role: probs.get(sid)
                                     for role, sid in roles.items()}
                        if any(v is None for v in mid_probs.values()):
                            mid_probs = None
            except Exception:  # noqa: BLE001
                logger.warning("[scalper-svc] %s: book MO non disponibile",
                               self.event_id, exc_info=True)
        decision = resolve_bias(
            pred, runner_names,
            follow.get("home_name") or "", follow.get("away_name") or "",
            mid_probs,
        )
        return {"bias": decision.bias, "meta": decision.to_meta()}

    # ---- corpo della sessione ----
    def run(self) -> None:  # noqa: C901 - flusso lineare, commentato
        from flumine import Flumine, clients
        from betfairlightweight import filters
        from .scalper_bot import ScalperStrategy

        ev = self.event_id
        try:
            self.db.set_control(ev, status="arming", started_at=_now_iso())
            follow = self.db.follow(ev)
            if not follow:
                raise RuntimeError("evento non presente in live_follow")

            # 1. mercati dell'evento dal catalogo (tipi validati)
            cat = self.trading.betting.list_market_catalogue(
                filter=filters.market_filter(
                    event_ids=[ev], market_type_codes=SESSION_MARKET_TYPES),
                market_projection=["RUNNER_DESCRIPTION", "MARKET_START_TIME"],
                sort="MAXIMUM_TRADED", max_results=25,
            )
            if not cat:
                raise RuntimeError("nessun mercato validato trovato a catalogo")
            market_ids = [m.market_id for m in cat]
            mo = next((m for m in cat
                       if getattr(m, "market_name", "").lower() == "match odds"
                       or any(getattr(r, "runner_name", "") == "The Draw"
                              for r in (m.runners or []))), None)

            # 2. connettore: bias (solo per mode bias/both)
            mode = str(self.control.get("mode") or "maker")
            bias: Dict[int, str] = {}
            meta: Dict[str, Any] = {"modalita": mode}
            if mode in ("bias", "both"):
                res = self._resolve_bias(follow, mo)
                bias = res["bias"]
                meta.update(res["meta"])
            self.db.set_control(ev, bias={str(k): v for k, v in bias.items()} or None,
                                bias_meta=meta)
            self.db.log(ev, "info", {"msg": "armato", "mode": mode,
                                     "markets": market_ids, "bias_meta": meta})
            if mode == "bias" and not bias:
                # niente consenso: in modalita' SOLO direzionale non c'e'
                # nulla da fare → armed (visibile in UI col motivo)
                self.db.set_control(ev, status="armed")
                return

            # 3. parametri strategia: VALIDATI + override whitelisted dalla UI
            params = dict(VALIDATED_PARAMS)
            ui = self.control.get("params") or {}
            for k, v in dict(ui).items():
                if k in UI_PARAM_WHITELIST:
                    params[k] = v
            params["stake"] = float(self.control.get("stake") or 25.0)
            params["dry_run"] = bool(self.control.get("dry_run", True))
            params["bias"] = {str(k): v for k, v in bias.items()}
            params["only_bias"] = mode == "bias"
            params["allow_inplay"] = False   # SEMPRE: pre-match only

            price_max = float(params.get("price_max", 4.6))
            cap = params["stake"] * (price_max - 1.0) * 2.0
            self.strategy = ScalperStrategy(
                market_filter={"market_ids": market_ids},
                scalper_params=params,
                event_sink=self.sink,
                max_selection_exposure=cap,
                max_order_exposure=cap,
                max_trade_count=int(1e6),
                max_live_trade_count=int(1e6),
            )
            self.framework = Flumine(client=clients.BetfairClient(self.trading))
            self.framework.add_strategy(self.strategy)

            self.db.set_control(ev, status="running", stats=self.strategy.stats)
            runner = threading.Thread(target=self.framework.run, daemon=True,
                                      name=f"flumine-{ev}")
            runner.start()

            # 4. loop di supervisione: heartbeat, stats, stop, fine pre-match
            ko_iso = follow.get("open_date")
            ko_ts = None
            if ko_iso:
                try:
                    ko_ts = datetime.fromisoformat(
                        str(ko_iso).replace("Z", "+00:00")).timestamp()
                except ValueError:
                    ko_ts = None
            while runner.is_alive():
                time.sleep(HEARTBEAT_S)
                self._flush()
                self.db.set_control(ev, heartbeat_at=_now_iso(),
                                    stats=self.strategy.stats)
                if self.stop_requested.is_set() or os.path.isfile(KILL_FILE):
                    self.strategy.force_flat = True
                    self.db.log(ev, "info", {"msg": "stop richiesto: force-flat"})
                    time.sleep(10)   # tempo per chiudere flat
                    break
                # oltre KO+10': il pre-match e' finito e le posizioni sono
                # gia' state chiuse dalle finestre KO → shutdown pulito
                if ko_ts is not None and time.time() > ko_ts + 600:
                    self.db.log(ev, "info", {"msg": "kickoff passato: fine sessione"})
                    break
            try:
                # meccanismo di stop pulito di flumine (stesso di runner.py)
                self.framework._running = False  # noqa: SLF001
            except Exception:  # noqa: BLE001
                pass
            self._flush()
            final = "stopped" if self.stop_requested.is_set() else "done"
            self.db.set_control(ev, status=final, stopped_at=_now_iso(),
                                stats=self.strategy.stats if self.strategy else None)
            self.db.log(ev, "info", {"msg": f"sessione {final}",
                                     "stats": self.strategy.stats})
        except Exception as exc:  # noqa: BLE001
            logger.exception("[scalper-svc] sessione %s in errore", ev)
            self._flush()
            self.db.set_control(ev, status="error", error=str(exc)[:500],
                                stopped_at=_now_iso())
            self.db.log(ev, "error", {"msg": str(exc)[:500]})


# ---------------------------------------------------------------------------
# Supervisore
# ---------------------------------------------------------------------------
def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "..")))
    from ..auth import build_client

    db = Db()
    trading = build_client(login=True)
    sessions: Dict[str, Session] = {}
    logger.info("[scalper-svc] avviato. Kill-switch: file %s", KILL_FILE)

    while True:
        if os.path.isfile(KILL_FILE):
            logger.warning("[scalper-svc] kill-switch: chiedo force-flat e esco")
            for s in sessions.values():
                s.stop_requested.set()
            time.sleep(15)
            return
        try:
            # sessioni terminate → rimuovi
            for ev in [e for e, s in sessions.items() if not s.is_alive()]:
                sessions.pop(ev, None)
            for row in db.pending_controls():
                ev = str(row["event_id"])
                if row["status"] == "requested" and ev not in sessions:
                    s = Session(db, row, trading)
                    sessions[ev] = s
                    s.start()
                    logger.info("[scalper-svc] sessione avviata per %s "
                                "(mode=%s dry=%s)", ev, row.get("mode"),
                                row.get("dry_run"))
                elif row["status"] == "stopping":
                    s = sessions.get(ev)
                    if s is not None:
                        s.stop_requested.set()
                    else:
                        db.set_control(ev, status="stopped",
                                       stopped_at=_now_iso())
        except Exception:  # noqa: BLE001
            logger.exception("[scalper-svc] errore nel loop di polling")
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
