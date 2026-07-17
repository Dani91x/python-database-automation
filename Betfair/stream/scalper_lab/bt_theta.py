"""Backtest ONESTO della ThetaStrategy (time-decay DIREZIONALE su Under).

Idea (tua, 06/07): a 0-0 la quota Under CALA col tempo -> BACK Under, green al
target, TAGLIA se sale (gol). Direzionale, edge STRUTTURALE (non serve liquidita'
per chiudere la 2a gamba come nel maker neutro).

Metrica = P&L REALE flumine (order.simulated.profit, dato il risultato del match)
+ locked = Σ min(P&L vince, P&L perde). Delay in-play 8s. Comm 5%.

Uso: python -m Betfair.stream.scalper_lab.bt_theta [k=v ...]
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from typing import Any, Dict

REPO = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
sys.path.insert(0, REPO)
os.chdir(REPO)

import flumine.config  # noqa: E402
from flumine import FlumineSimulation, clients  # noqa: E402
from flumine.markets.middleware import SimulatedMiddleware  # noqa: E402

from Betfair.stream.scalper_lab.theta_strategy import ThetaStrategy  # noqa: E402
from Betfair.stream.scalper.scalper_bot import compute_green  # noqa: E402

DATA = os.path.join(REPO, "_live_raw")
COMM = 0.05
INPLAY_DELAY = 8.0
# modello di fill: False = solo volume tradato (conservativo, giusto per maker puri);
# True = riempie contro le quote disponibili (realistico per i TAKE a mercato di theta).
AVAIL_PRICES = False


# Match COMPLETI a RUNTIME dal validatore registrazioni (fix 17/07: la lista
# hardcoded era pre-validatore — cieco su raw nuovi, monchi o senza CLOSED).
def complete_events(min_coverage=None):
    from Betfair.stream.tools.validate_recordings import (
        check_events_for_backtest, complete_event_ids)

    ids = complete_event_ids(DATA)
    if min_coverage is not None:
        ids = check_events_for_backtest(ids, DATA, float(min_coverage))
    return ids


GOALS = {
    "35674515": "gol 13-19-28-31-40", "35759636": "20-53-62-84",
    "35760084": "7-27-45-62", "35764745": "38-73-85", "35765620": "12-54",
    "35768297": "0-0 FINO 52!", "35768365": "28-65-88", "35772591": "44-53-62",
    "35774000": "15-80-87", "35777617": "gol 2' poi tardi", "35780184": "?",
    "35781607": "?",
}


def run_event(ev: str, params: Dict[str, Any]) -> Dict[str, Any]:
    raw = os.path.join(DATA, ev, f"{ev}.raw.jsonl")
    if not os.path.isfile(raw):
        return {"event": ev, "error": "no raw"}
    prev = (flumine.config.simulated,
            getattr(flumine.config, "simulation_available_prices", False),
            getattr(flumine.config, "place_latency", 0.120))
    flumine.config.simulated = True
    flumine.config.simulation_available_prices = AVAIL_PRICES
    flumine.config.place_latency = INPLAY_DELAY
    flumine.config.cancel_latency = 0.170
    try:
        client = clients.SimulatedClient(min_bet_validation=False)
        try:
            client.commission_base = 0.0
        except Exception:
            pass
        fw = FlumineSimulation(client=client)
        fw.add_market_middleware(SimulatedMiddleware())
        strat = ThetaStrategy(market_filter={"markets": [raw]}, theta_params=params,
                              max_selection_exposure=1e7, max_order_exposure=1e7,
                              max_trade_count=int(1e9), max_live_trade_count=int(1e9))
        fw.add_strategy(strat)
        fw.run()
    except Exception as exc:  # noqa: BLE001
        (flumine.config.simulated, flumine.config.simulation_available_prices,
         flumine.config.place_latency) = prev
        return {"event": ev, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        (flumine.config.simulated, flumine.config.simulation_available_prices,
         flumine.config.place_latency) = prev

    # METRICA CORRETTA per strategia che CHIUDE IN-PLAY = mark-to-market:
    # valuta ogni posizione al prezzo corrente (last mid). Il residuo aperto a
    # fine finestra e' valutato al mercato, non al settlement (che nel replay
    # non arriva per gli OU). locked = min(win,lose) = pavimento conservativo.
    last_mids = getattr(strat, "last_mids", {}) or {}
    by_sel = defaultdict(list)
    for o, _ in strat.settled_orders:
        by_sel[(o.market_id, o.selection_id)].append(o)
    mtm = 0.0
    locked = 0.0
    open_resid = 0.0
    for key, orders in by_sel.items():
        sb = sl = sbp = slp = 0.0
        for o in orders:
            m = float(getattr(o, "size_matched", 0.0) or 0.0)
            if m <= 0:
                continue
            pp = float(getattr(o, "average_price_matched", 0.0) or 0.0)
            if (getattr(o, "side", "") or "").upper() == "BACK":
                sb += m; sbp += pp * m
            else:
                sl += m; slp += pp * m
        if sb <= 0 and sl <= 0:
            continue
        ob = sbp / sb if sb else 0.0
        ol = slp / sl if sl else 0.0
        nw = sb * (ob - 1.0) - sl * (ol - 1.0)   # P&L se Under vince
        nl = sl - sb                             # P&L se Under perde
        mp = last_mids.get(key)
        g = compute_green(nw, nl, mp) if (mp and mp > 1.0) else None
        mtm += g[2] if g is not None else nl     # valore mark-to-market
        locked += min(nw, nl)
        open_resid += abs(nw - nl)
    net = mtm - (mtm * COMM if mtm > 0 else 0.0)
    st = strat.stats
    return dict(event=ev, orders=int(st.get("orders", 0)),
                entries=int(st.get("entries", 0)), greens=int(st.get("greens", 0)),
                stops=int(st.get("stops", 0)), net=round(net, 2),
                locked=round(locked, 2), resid=round(open_resid, 2))


def main() -> None:
    params = dict(stake=10.0, max_units=3, add_step_ticks=3, target_ticks=4,
                  stop_ticks=3, entry_mode="maker", inplay_from_s=300.0,
                  inplay_to_s=2400.0, min_size=50.0)
    global AVAIL_PRICES
    events_arg = None
    min_coverage = None
    for a in sys.argv[1:]:
        if "=" in a:
            k, v = a.split("=", 1)
            if k == "avail":            # modello di fill (0/1), non e' un theta_param
                AVAIL_PRICES = bool(int(v))
                continue
            if k == "events":           # lista esplicita (guardia del validatore)
                events_arg = [e.strip() for e in v.split(",") if e.strip()]
                continue
            if k == "min_coverage":     # soglia %% di copertura registrazione
                min_coverage = float(v)
                continue
            params[k] = float(v) if v.replace(".", "").replace("-", "").isdigit() else v
    if events_arg:
        from Betfair.stream.tools.validate_recordings import check_events_for_backtest

        events = check_events_for_backtest(events_arg, DATA, min_coverage)
    else:
        events = complete_events(min_coverage)
    if not events:
        print(f"# Nessuna registrazione COMPLETE in {DATA}")
        return
    print(f"params: {params}\n")
    print(f"{'event':>10} {'NETmtm':>8} {'locked':>8} {'resid':>6} {'ent':>4} "
          f"{'grn':>4} {'stp':>4}  gol")
    print("-" * 70)
    tot = tot_lock = 0.0
    ngreen = 0
    for ev in events:
        r = run_event(ev, dict(params))
        if "error" in r:
            print(f"{ev:>10}  ERR {r['error'][:40]}")
            continue
        print(f"{ev:>10} {r['net']:>8.2f} {r['locked']:>8.2f} {r['resid']:>6.2f} "
              f"{r['entries']:>4} {r['greens']:>4} {r['stops']:>4}  {GOALS.get(ev, '')}")
        tot += r["net"]; tot_lock += r["locked"]
        if r["net"] > 0.01:
            ngreen += 1
    print("-" * 70)
    print(f"{'TOTALE':>10} {tot:>8.2f} {tot_lock:>8.2f}   verde su {ngreen}/{len(events)} match")


if __name__ == "__main__":
    main()
