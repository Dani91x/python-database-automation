"""Harness di backtest ONESTO per il loop RD-Agent-style sullo scalper Betfair.

Adatta bt_scalper.py con:
  * delay corretti: PRE-MATCH 0s, IN-PLAY 8s (bet-delay Betfair reale)
  * gira su TUTTI i 12 match completi (o subset via --events)
  * output JSON strutturato -> knowledge_store (leaderboard persistente)
  * report ORIENTATO ALLE OCCASIONI: n ingressi, n chiusure a profitto,
    win-rate dei cicli, oltre a FLAT (edge vero) vs NAKED (fortuna).

Test veritieri: FlumineSimulation, simulation_available_prices=False
(fill solo sul volume tradato, coda rispettata), commissione 5%.

Uso:
  python -m Betfair.stream.scalper_lab.bt_lab --mode prematch --stake 25
  python -m Betfair.stream.scalper_lab.bt_lab --mode inplay --params '{"min_size":20}'
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from collections import defaultdict
from typing import Any, Dict, List, Tuple

REPO = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
sys.path.insert(0, REPO)
os.chdir(REPO)

import flumine.config  # noqa: E402
from flumine import FlumineSimulation, clients  # noqa: E402
from flumine.markets.middleware import SimulatedMiddleware  # noqa: E402

# Usa la COPIA nel lab (l'originale scalper/scalper_bot.py resta intatto).
from Betfair.stream.scalper_lab.scalper_bot_base import ScalperStrategy  # noqa: E402

DATA_DIR = os.path.join(REPO, "_live_raw")
COMMISSION = 0.05
INPLAY_DELAY = 8.0     # bet-delay Betfair in-play (richiesta utente)
PREMATCH_DELAY = 0.0   # pre-match: nessun delay

# Match COMPLETI: filtro a RUNTIME del validatore registrazioni (fix 17/07 —
# la vecchia lista hardcoded era pre-validatore e non vedeva raw nuovi/monchi).
def complete_events(min_coverage: Any = None) -> List[str]:
    """Event id con registrazione COMPLETE in DATA_DIR secondo il validatore."""
    from Betfair.stream.tools.validate_recordings import complete_event_ids

    ids = complete_event_ids(DATA_DIR)
    if min_coverage is not None:
        from Betfair.stream.tools.validate_recordings import check_events_for_backtest

        ids = check_events_for_backtest(ids, DATA_DIR, float(min_coverage))
    return ids


def __getattr__(name: str) -> Any:  # PEP 562: compat import `COMPLETE` (rdloop)
    if name == "COMPLETE":
        return complete_events()
    raise AttributeError(name)


_CFG_LOCK = threading.Lock()


def run_event(event_id: str, params: Dict[str, Any], inplay: bool) -> Dict[str, Any]:
    raw = os.path.join(DATA_DIR, event_id, f"{event_id}.raw.jsonl")
    if not os.path.isfile(raw):
        return {"event": event_id, "error": "no raw file"}

    p = dict(params)
    p["allow_inplay"] = inplay
    delay = INPLAY_DELAY if inplay else PREMATCH_DELAY

    with _CFG_LOCK:
        prev = (flumine.config.simulated,
                getattr(flumine.config, "simulation_available_prices", False),
                getattr(flumine.config, "place_latency", 0.120),
                getattr(flumine.config, "cancel_latency", 0.170))
        flumine.config.simulated = True
        flumine.config.simulation_available_prices = False  # fill conservativi
        flumine.config.place_latency = float(delay)
        flumine.config.cancel_latency = 0.170
        try:
            client = clients.SimulatedClient(min_bet_validation=False)
            try:
                client.commission_base = 0.0
            except (TypeError, ValueError):
                pass
            fw = FlumineSimulation(client=client)
            fw.add_market_middleware(SimulatedMiddleware())
            strat = ScalperStrategy(
                market_filter={"markets": [raw]},
                scalper_params=p,
                max_selection_exposure=1e7,
                max_order_exposure=1e7,
                max_trade_count=int(1e9),
                max_live_trade_count=int(1e9),
            )
            fw.add_strategy(strat)
            fw.run()
        except Exception as exc:  # noqa: BLE001 - vogliamo l'evento non crasha il loop
            (flumine.config.simulated,
             flumine.config.simulation_available_prices,
             flumine.config.place_latency,
             flumine.config.cancel_latency) = prev
            return {"event": event_id, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            (flumine.config.simulated,
             flumine.config.simulation_available_prices,
             flumine.config.place_latency,
             flumine.config.cancel_latency) = prev

    return _decompose(event_id, strat)


def _decompose(event_id: str, strat: Any) -> Dict[str, Any]:
    """Metrica ONESTA basata sul P&L REALE di flumine (order.simulated.profit,
    dato il risultato effettivo del match) + scomposizione edge/rischio:

      realized = somma dei sim.profit reali (quello che avresti fatto davvero)
      locked   = somma min(P&L se vince, P&L se perde) per selezione = pavimento
                 result-INDIPENDENTE (edge puro, non fortuna)
      naked    = |P&L vince - P&L perde| = rischio scoperto residuo
      roundtrips = selezioni con back E lay bilanciati (scalp chiuso vero)
    """
    settled = list(strat.settled_orders)
    by_sel: Dict[Tuple[Any, Any], List[Any]] = defaultdict(list)
    realized = 0.0
    for order, _mtype in settled:
        sim = getattr(order, "simulated", None)
        prof = float(getattr(sim, "profit", 0.0) or 0.0) if sim is not None else 0.0
        realized += prof
        by_sel[(getattr(order, "market_id", None),
                getattr(order, "selection_id", None))].append(order)

    locked = 0.0
    naked_risk = 0.0
    roundtrips = 0
    naked_sels = 0
    for _key, orders in by_sel.items():
        sb = sl = sb_pw = sl_pw = 0.0
        for o in orders:
            m = float(getattr(o, "size_matched", 0.0) or 0.0)
            if m <= 0:
                continue
            pr = float(getattr(o, "average_price_matched", 0.0) or 0.0)
            if (getattr(o, "side", "") or "").upper() == "BACK":
                sb += m; sb_pw += pr * m
            else:
                sl += m; sl_pw += pr * m
        if sb <= 0 and sl <= 0:
            continue
        ob = sb_pw / sb if sb > 0 else 0.0
        ol = sl_pw / sl if sl > 0 else 0.0
        pnl_win = sb * (ob - 1.0) - sl * (ol - 1.0)   # selezione VINCE
        pnl_lose = sl - sb                            # selezione PERDE
        locked += min(pnl_win, pnl_lose)
        naked_risk += abs(pnl_win - pnl_lose)
        bal = (sb > 0 and sl > 0 and abs(sb - sl) / max(sb, sl) < 0.2)
        if bal:
            roundtrips += 1
        elif abs(sb - sl) >= 0.05:
            naked_sels += 1

    net = realized - (realized * COMMISSION if realized > 0 else 0.0)
    net_locked = locked - (locked * COMMISSION if locked > 0 else 0.0)
    s = dict(strat.stats)
    return {
        "event": event_id,
        "orders": len(settled),
        "realized": round(realized, 2),   # P&L reale lordo (dato il risultato)
        "net": round(net, 2),             # realized netto comm 5%
        "locked": round(net_locked, 2),   # edge result-indipendente (netto comm)
        "naked_risk": round(naked_risk, 2),
        "naked_sels": naked_sels,
        "roundtrips": roundtrips,
        "scalps": int(s.get("scalps", 0)),
        "stops": int(s.get("stops", 0)),
        "flattens": int(s.get("flattens", 0)),
    }


def run_config(params: Dict[str, Any], mode: str, events: List[str],
               label: str = "") -> Dict[str, Any]:
    """Gira una config su tutti gli eventi, aggrega, ritorna dict-risultato."""
    inplay = (mode == "inplay")
    per_event = []
    for ev in events:
        per_event.append(run_event(ev, params, inplay))

    ok = [r for r in per_event if "error" not in r]
    tot_net = sum(r["net"] for r in ok)             # P&L reale netto comm
    tot_locked = sum(r["locked"] for r in ok)       # edge result-indipendente
    tot_rt = sum(r["roundtrips"] for r in ok)
    tot_orders = sum(r["orders"] for r in ok)
    tot_naked = sum(r["naked_sels"] for r in ok)
    tot_naked_risk = sum(r["naked_risk"] for r in ok)
    n_active = sum(1 for r in ok if r["orders"] > 0)   # match dove ha operato
    n_green = sum(1 for r in ok if r["net"] > 0.01)    # match in verde reale

    return {
        "label": label,
        "mode": mode,
        "params": params,
        "n_events": len(ok),
        "n_active": n_active,
        "n_green": n_green,
        "tot_net": round(tot_net, 2),
        "tot_locked": round(tot_locked, 2),
        "tot_roundtrips": tot_rt,
        "tot_orders": tot_orders,
        "tot_naked_sels": tot_naked,
        "tot_naked_risk": round(tot_naked_risk, 2),
        "per_event": per_event,
    }


def _print_report(res: Dict[str, Any]) -> None:
    print(f"\n### {res['label']}  [{res['mode']}]  params={json.dumps(res['params'])}")
    print(f"{'EVENT':>10} {'ord':>5} {'NET':>8} {'locked':>8} "
          f"{'rt':>4} {'nkSel':>6} {'nkRisk':>7}")
    for r in res["per_event"]:
        if "error" in r:
            print(f"{r['event']:>10}  ERR: {r['error'][:60]}")
            continue
        print(f"{r['event']:>10} {r['orders']:>5} {r['net']:>8.2f} {r['locked']:>8.2f} "
              f"{r['roundtrips']:>4} {r['naked_sels']:>6} {r['naked_risk']:>7.2f}")
    print(f"{'-'*66}")
    print(f"OCCASIONI: operato {res['n_active']}/{res['n_events']} | "
          f"verde reale {res['n_green']}/{res['n_events']} | "
          f"roundtrip={res['tot_roundtrips']} | NET reale={res['tot_net']:+.2f} | "
          f"locked={res['tot_locked']:+.2f} | naked={res['tot_naked_sels']} "
          f"(risk {res['tot_naked_risk']:.1f})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["prematch", "inplay"], default="prematch")
    ap.add_argument("--events", default="")
    ap.add_argument("--stake", type=float, default=25.0)
    ap.add_argument("--params", default="{}", help="JSON override dei parametri")
    ap.add_argument("--label", default="baseline")
    ap.add_argument("--min-coverage", type=float, default=None,
                    help="esclude gli eventi con copertura registrazione sotto soglia (%%)")
    args = ap.parse_args()

    events = [e.strip() for e in args.events.split(",") if e.strip()]
    if events:
        # eventi ESPLICITI: guardia del validatore (warning visibile di default,
        # esclusione solo con --min-coverage) — fix 17/07 "tuning senza guardia".
        from Betfair.stream.tools.validate_recordings import check_events_for_backtest

        events = check_events_for_backtest(events, DATA_DIR, args.min_coverage)
    else:
        events = complete_events(args.min_coverage)
        if not events:
            print("# Nessuna registrazione COMPLETE in", DATA_DIR)
            return
    params: Dict[str, Any] = {"stake": args.stake}
    params.update(json.loads(args.params))

    res = run_config(params, args.mode, events, label=args.label)
    _print_report(res)


if __name__ == "__main__":
    main()
