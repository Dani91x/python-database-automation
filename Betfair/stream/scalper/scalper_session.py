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
    # min_size 300 = gate VALIDATO (backtest 12 match 07-08/07, dossier
    # §6.4: 150 → -0.90 €, 300 → +0.77 €). fix 09/07: qui era rimasto 150
    # e sovrascriveva il default 300 gia' portato in produzione nel bot.
    "min_size": 300.0, "min_flow": 10.0, "flow_window_ms": 90_000,
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
    # MISSIONE "2 tick per evento": 1 ciclo verde pre-match + 1 in-play
    # (intervallo), poi stop ingressi di fase. Off di default: la UI la
    # attiva esplicitamente (e forza anche ht_mode).
    "one_green_per_phase": False,
}
UI_PARAM_WHITELIST = {
    "scalp_ticks", "stop_ticks", "min_size", "min_flow", "price_min",
    "price_max", "join_max_spread", "improve_inside", "reprice_ticks",
    "capture_min_ticks", "capture_max_ticks", "max_signal_ticks",
    "cooldown_ms", "flatten_before_s", "entry_stop_before_s", "wom_block",
    "entry_ttl_ms", "lock_ttl_ms", "max_cycles", "max_txn_hour",
    "event_profit_target", "event_target_giveback", "event_loss_cap",
    "ht_mode", "one_green_per_phase",
    "flow_balance_min", "flow_balance_window_ms", "min_inside_flow",
    "require_oscillation", "trend_mode", "max_drift_ticks",
    # SNIPER in-play (bibbia §6): toggle + stake dedicato (default 10)
    "sniper_mode", "sniper_stake",
}
SESSION_MARKET_TYPES = [
    "MATCH_ODDS", "OVER_UNDER_15", "OVER_UNDER_25", "OVER_UNDER_35",
]
# SNIPER: tutte le linee O/U — la linea target Under (gol+1).5 si sposta coi
# gol, quindi a stream servono anche le alte (bibbia §6).
SNIPER_MARKET_TYPES = [f"OVER_UNDER_{n}5" for n in range(0, 9)]

# ---- WATCHER INTERVALLO: firma "minuto congelato" (dati storici 35768365) ----
# Il minuto del feed si blocca a 45-46 per ~15-18 minuti durante l'intervallo.
# fix 10/07: staleness a 300s (i recuperi del 1° tempo arrivano a 5': con la
# vecchia soglia 150s il watcher scattava DURANTE il recupero, con la palla in
# gioco; l'intervallo dura 15', i 5 minuti di attesa non lo consumano) e
# vincolo minute <= 48 (un feed che avanza oltre non e' l'intervallo).
HT_STALE_S = 300.0
HT_MINUTE_MIN = 45
HT_MINUTE_MAX = 48


def ht_should_start(minute: Optional[int], stale_s: float) -> bool:
    """True se il feed indica l'INIZIO dell'intervallo (minuto congelato).

    ``minute`` = minuto corrente da live_now; ``stale_s`` = da quanti secondi
    il minuto non avanza. Logica pura, testabile senza thread/DB.
    """
    return (
        minute is not None
        and HT_MINUTE_MIN <= int(minute) <= HT_MINUTE_MAX
        and stale_s >= HT_STALE_S
    )


def _strategy_flat(strategy: Any) -> bool:
    """True se la strategia e' FLAT: slot tutti a riposo (IDLE/DONE) e nessun
    ordine ancora vivo. Usata dallo stop sicuro (fix 10/07: prima si dormiva
    12s "alla cieca" e si usciva anche con posizioni aperte)."""
    try:
        for slot in getattr(strategy, "_slots", {}).values():
            if slot.status not in ("IDLE", "DONE"):
                return False
            for o in (slot.entry, slot.entry_back, slot.entry_lay,
                      slot.close, slot.next_entry, *slot.flatten_orders):
                if strategy._has_live(o):  # noqa: SLF001 - helper del bot
                    return False
    except Exception:  # noqa: BLE001 - il check non deve mai rompere lo stop
        return False
    return True


def _wait_flat(strategy: Any, timeout_s: float = 30.0) -> bool:
    """Attende (max ``timeout_s``) che la strategia risulti flat."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _strategy_flat(strategy):
            return True
        time.sleep(1.0)
    return _strategy_flat(strategy)


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

        # SNIPER: la linea target e' Under (gol totali + 1).5 e in live si
        # SPOSTA coi gol -> a catalogo/stream servono TUTTE le OU (05..85).
        # Il maker resta blindato sui SESSION_MARKET_TYPES (vedi sotto).
        sniper_mode = bool((control.get("params") or {}).get("sniper_mode"))
        cat_types = list(SESSION_MARKET_TYPES)
        if sniper_mode:
            cat_types = sorted(set(cat_types) | set(SNIPER_MARKET_TYPES))
        cat = trading.betting.list_market_catalogue(
            filter=filters.market_filter(
                event_ids=[ev], market_type_codes=cat_types),
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
            # fix 10/07: il vecchio setdefault era INEFFICACE (la chiave
            # esiste gia' in VALIDATED_PARAMS a 1.5, quindi restava 1.5).
            # In ht_mode il cap evento DEVE essere 1.0 come certificato
            # 03/07: si puo' solo ABBASSARE (min), mai alzare.
            params["event_loss_cap"] = min(
                float(params.get("event_loss_cap", 1.0)), 1.0)
        else:
            params["allow_inplay"] = False

        # ---- SNIPER IN-PLAY (bibbia §6, config S16) ----
        # Strategia SEPARATA accanto al maker pre-match: un tick sull'Under
        # al momento letto dal book (cadenza + coda + spread), poi stop.
        # Con dry_run (default della sessione) emette solo i trigger
        # ``sniper_dry_fire``: e' la modalita' DEMO. (sniper_mode e' letto
        # PRIMA del catalogo: servono le OU alte a stream.)
        if sniper_mode and ht_mode:
            raise RuntimeError(
                "sniper_mode e ht_mode insieme non sono supportati "
                "(bibbia §5: ht_mode e' NO-GO; usa solo sniper_mode)")
        if sniper_mode:
            # il maker NON deve quotare le OU alte aggiunte per lo sniper:
            # blindalo sui tipi di sessione storici.
            params["market_types"] = list(SESSION_MARKET_TYPES)

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
        sniper = None
        if sniper_mode:
            from .sniper_bot import SniperStrategy
            sniper_stake = float(
                (control.get("params") or {}).get("sniper_stake") or 10.0)
            sniper = SniperStrategy(
                market_filter=filters.streaming_market_filter(
                    market_ids=market_ids),
                sniper_params={
                    "stake": sniper_stake,
                    "dry_run": params["dry_run"],
                    # protezioni .it IDENTICHE al maker (multipli 0,50,
                    # minimi per lato, uscite a size ESATTA via submin):
                    # il green resta spalmato al centesimo sui due esiti
                    "exact_exits": True,
                    "size_step": 0.5,
                    "live_min_bet": 2.0,
                },
                event_sink=sink,
                # esposizione: BACK -> liability = stake (margine x3)
                max_selection_exposure=sniper_stake * 3.0,
                max_order_exposure=sniper_stake * 3.0,
                max_trade_count=int(1e6),
                max_live_trade_count=int(1e6),
            )
            db.log(ev, "info", {"msg": "sniper armato (S16)",
                                "stake": sniper_stake,
                                "dry_run": params["dry_run"]})
        # min_bet_validation=False COME IL RUNNER LIVE (fix CRITICAL-3 del
        # live-trading): l'OrderValidation di flumine (size>=1 o payout>=20)
        # non conosce le eccezioni Betfair (green-up sotto-minimo, park-trim)
        # e ci ha rifiutato 528 park LAY il 02/07. I minimi veri li garantisce
        # la strategia (side-aware + park legali).
        # ---- WATCHER INTERVALLO (solo ht_mode): rilevatore REALE da live_now.
        # Regole (vedi ht_should_start): minute in 45-48 fermo da >=300s ->
        # HT INIZIATO (ht_active=True); minute che riavanza (>=46 con nuovo
        # update) -> HT FINITO: stop ingressi + chiusura immediata dei cicli.
        # Il clock 48'-59' resta come sanita' dentro la strategia.
        stop_flag = threading.Event()

        def _ht_watcher(strategy_ref, ko_epoch: Optional[float]) -> None:
            last_min = None
            last_change = time.time()
            started = False
            while not stop_flag.is_set():
                time.sleep(20)
                if ko_epoch is None or time.time() < ko_epoch + 44 * 60:
                    continue
                if time.time() > ko_epoch + 70 * 60:
                    if started and strategy_ref.ht_active:
                        strategy_ref.ht_active = False
                        strategy_ref.inplay_close_now = True
                        db.log(ev, "ht_end", {"perche": "clock-sanita' 70'"})
                    return
                try:
                    r = db.sb.table("live_now").select("minute,inplay")                         .eq("event_id", ev).execute()
                    row = (r.data or [None])[0] or {}
                    m = row.get("minute")
                except Exception:  # noqa: BLE001
                    continue
                now_t = time.time()
                if m is not None and m != last_min:
                    if started and last_min is not None and m >= 46:
                        # il minuto RIAVANZA: secondo tempo ripreso
                        strategy_ref.ht_active = False
                        strategy_ref.inplay_close_now = True
                        db.log(ev, "ht_end", {"minute": m})
                        return
                    last_min = m
                    last_change = now_t
                elif not started and ht_should_start(m, now_t - last_change):
                    started = True
                    strategy_ref.ht_active = True
                    db.log(ev, "ht_start", {"minute": m})

        framework = Flumine(client=clients.BetfairClient(
            trading, min_bet_validation=False, order_stream=True,
        ))
        framework.add_strategy(strategy)
        if sniper is not None:
            framework.add_strategy(sniper)

        def _stats() -> Dict[str, Any]:
            s = dict(strategy.stats)
            if sniper is not None:
                s.update({f"sniper_{k}": v for k, v in sniper.stats.items()})
            return s

        db.set_control(ev, status="running", stats=_stats())

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
        if ht_mode:
            strategy.ht_active = False  # chiuso finche' il rilevatore non apre
            threading.Thread(
                target=_ht_watcher, args=(strategy, ko_ts),
                daemon=True, name="ht-watcher",
            ).start()

        # ---- WATCHER LINEA SNIPER: Under (gol totali + 1).5 da live_now ----
        # (pattern del watcher HT: feed punteggi -> controllo esterno del bot)
        def _sniper_line_watcher(sniper_ref) -> None:
            while not stop_flag.is_set():
                try:
                    r = db.sb.table("live_now").select(
                        "score_home,score_away").eq("event_id", ev).execute()
                    row = (r.data or [None])[0] or {}
                    h, a = row.get("score_home"), row.get("score_away")
                    if h is not None and a is not None:
                        tot = int(h) + int(a)
                        # oltre 8.5 non esistono linee: "NONE" spegne il fuoco
                        line = (f"OVER_UNDER_{tot + 1}5" if tot <= 7
                                else "NONE")
                        sniper_ref.set_line(line)
                except Exception:  # noqa: BLE001 - il watcher non muore mai
                    pass
                time.sleep(15)

        if sniper is not None:
            threading.Thread(
                target=_sniper_line_watcher, args=(sniper,),
                daemon=True, name="sniper-line",
            ).start()

        def _force_flat_all() -> None:
            strategy.force_flat = True
            if sniper is not None:
                sniper.force_flat = True

        def _all_flat(timeout_s: float = 30.0) -> bool:
            ok = _wait_flat(strategy, timeout_s=timeout_s)
            if sniper is not None:
                deadline = time.time() + timeout_s
                while time.time() < deadline and not sniper.is_flat():
                    time.sleep(1.0)
                ok = ok and sniper.is_flat()
            return ok

        while runner.is_alive():
            time.sleep(HEARTBEAT_S)
            flush()
            db.set_control(ev, heartbeat_at=_now_iso(), stats=_stats())
            status = db.control_status(ev)
            if status == "stopping" or os.path.isfile(KILL_FILE):
                stopped_by_ui = status == "stopping"
                _force_flat_all()
                db.log(ev, "info", {"msg": "stop richiesto: force-flat"})
                # fix 10/07: niente sleep cieco da 12s — si attende (max 30s)
                # che la strategia sia DAVVERO flat (slot IDLE/DONE, nessun
                # ordine vivo); se non lo e', si esce comunque e lo stato
                # finale lo raccontera' (mai promettere il flat).
                if not _all_flat(timeout_s=30.0):
                    db.log(ev, "error",
                           {"msg": "stop: posizione NON flat dopo 30s"})
                break
            # vita sessione: pre-match KO+10'; ht_mode ~KO+70'; sniper fino a
            # fine partita (KO+130', recupero incluso)
            _life_s = 7800 if sniper_mode else (4200 if ht_mode else 600)
            if ko_ts is not None and time.time() > ko_ts + _life_s:
                # fix 10/07: anche il fine-vita passa dal force-flat (in
                # ht_mode un ciclo intervallo ancora aperto restava vivo
                # mentre il framework veniva spento 2s dopo).
                _force_flat_all()
                db.log(ev, "info", {"msg": "kickoff passato: fine sessione"})
                if not _all_flat(timeout_s=30.0):
                    db.log(ev, "error",
                           {"msg": "fine sessione: posizione NON flat dopo 30s"})
                break
        stop_flag.set()
        try:
            # BUG FIX (cert 10/07): flumine 2.13.11 esce dal run() SOLO con un
            # TerminationEvent in handler_queue — _running=False non è mai testato
            # (stesso fix di runner/tennis_runner._stop_framework).
            from flumine.events.events import TerminationEvent

            framework._running = False  # noqa: SLF001 - coerenza di stato
            framework.handler_queue.put(TerminationEvent(framework))
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
        flush()
        final = "stopped" if stopped_by_ui else "done"
        _final_stats = _stats() if strategy is not None else None
        db.set_control(ev, status=final, stopped_at=_now_iso(),
                       stats=_final_stats)
        db.log(ev, "info", {"msg": f"sessione {final}",
                            "stats": _final_stats})
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
