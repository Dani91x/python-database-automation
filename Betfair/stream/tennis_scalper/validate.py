"""VALIDAZIONE iper-affidabile: train/test split su TUTTE le 808 combo.

Gira le due griglie (544 price + 264 score-cond) su ogni match CONCLUSO, raccoglie
il P&L per (config, match), poi:
  - tiene solo i match ATTIVI (dove almeno una config ha tradato -> c'era liquidita')
  - split deterministico TRAIN/TEST dei match (alternati per event-id ordinato)
  - classifica le config sul TRAIN, riporta la loro resa sul TEST
  - IL VERDETTO = config verde su ENTRAMBI train e test, con alto win-rate su test
    (generalizza -> non e' overfitting). Questo e' il candidato live.

Fill reali (coda PIQ) + delay in-play 3s (modellato in TennisLab).

Uso:
  python -m Betfair.stream.tennis_scalper.validate --data DIR [--min-active 6]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Tuple

import flumine.config
from flumine import FlumineSimulation, clients
from flumine.markets.middleware import SimulatedMiddleware

from . import lab_grid as PG          # price grid
from . import lab_grid_score as SG    # score grid
from .tennis_lab import TennisLabStrategy
from .tennis_swing_bot import TennisSwingStrategy

# z-swing detector con GATE APERTO (bug #5: i suoi gate z+ER lo bloccano; qui
# apriamo liquidita' e allarghiamo la banda per vedere se ha segnale).
SWING_GRID = [
    (f"swing z{z} stop{s} {'mk' if mk else 'tk'}",
     {"zin": z, "stop_ticks": s, "maker": mk, "maker_offset": 1,
      "min_matched": 2000.0, "price_min": 1.01, "price_max": 8.0})
    for z in (1.5, 2.0, 2.5) for s in (6, 10) for mk in (True, False)]


def _run_swing(raw_path, params):
    """Rigioca UNA partita con TennisSwingStrategy. Ritorna (settled, locked, entries)."""
    flumine.config.simulated = True
    flumine.config.simulation_available_prices = False
    c = clients.SimulatedClient(min_bet_validation=False)
    try:
        c.commission_base = 0.0
    except (TypeError, ValueError):
        pass
    fw = FlumineSimulation(client=c)
    fw.add_market_middleware(SimulatedMiddleware())
    s = TennisSwingStrategy(market_filter={"markets": [raw_path]},
                            swing_params={**params, "dry_run": False},
                            max_selection_exposure=1e6, max_order_exposure=1e6,
                            max_trade_count=int(1e9), max_live_trade_count=int(1e9))
    fw.add_strategy(s)
    fw.run()
    settled = float(getattr(s, "settled_pnl", 0.0))
    locked = 0.0
    try:
        for mk in fw.markets.markets.values():
            orders = list(mk.blotter.strategy_orders(s))
            locked += TennisLabStrategy._locked_from_orders(orders, mk.market_book)
    except Exception:  # noqa: BLE001
        pass
    entries = int(getattr(s, "stats", {}).get("entries", 0))
    return settled, locked, entries


def _liquid_events(files: List[str]) -> List[str]:
    return [os.path.basename(os.path.dirname(f)) for f in files]


def _override_minmatched(grid, mm):
    if mm is None:
        return grid
    return [(n, {**p, "min_matched": float(mm)}) for n, p in grid]


def collect(data_dir: str, min_matched=None,
            min_coverage=None) -> Tuple[Dict[str, Dict[str, float]], List[str]]:
    """Ritorna (results[config][event]=pnl, lista match attivi).

    min_matched: override del gate liquidita' su TUTTE le config (bug #6: il gate
    10k nasconde i match sottili; abbassalo per sbloccare il campione).
    min_coverage: esclude i raw con copertura registrazione sotto soglia (fix
    17/07 "tuning senza guardia"; None = solo warning visibile)."""
    files = [f for f in PG.find_matches(data_dir) if PG.is_settled(f)]
    from ..tools.validate_recordings import check_raw_paths_for_backtest

    files = check_raw_paths_for_backtest(files, min_coverage)
    price_grid = _override_minmatched(PG.build_grid(), min_matched)
    score_grid = _override_minmatched(SG.build_grid(), min_matched)
    events_all = [os.path.basename(os.path.dirname(f)) for f in files]
    names_cache = SG.build_names_cache(data_dir, events_all)

    results: Dict[str, Dict[str, float]] = {}
    locked_res: Dict[str, Dict[str, float]] = {}
    entries_by_ev: Dict[str, int] = {}

    for f in files:
        ev = os.path.basename(os.path.dirname(f))
        # --- price grid ---
        try:
            pres = PG.run_match(f, price_grid)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{ev}] price ERR: {exc}"); pres = {}
        # --- score grid ---
        tl = SG.load_timeline(os.path.join(os.path.dirname(f), f"{ev}.score.jsonl"), ev)
        ts0 = tl[-1][1] if tl else None
        side_map = SG.build_side_map(names_cache.get(ev, {}), ts0)
        try:
            sres = SG.run_match(f, tl, side_map, score_grid)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{ev}] score ERR: {exc}"); sres = {}

        ent = 0
        for name, (pnl, st) in list(pres.items()):
            results.setdefault("P:" + name, {})[ev] = pnl
            locked_res.setdefault("P:" + name, {})[ev] = float(st.get("locked", 0.0))
            ent += int(st.get("entries", 0))
        for name, (pnl, st) in list(sres.items()):
            results.setdefault("S:" + name, {})[ev] = pnl
            locked_res.setdefault("S:" + name, {})[ev] = float(st.get("locked", 0.0))
            ent += int(st.get("entries", 0))
        # --- z-swing (bug #5: gate aperto) ---
        for sname, sparams in SWING_GRID:
            try:
                sett, lck, sent = _run_swing(f, sparams)
            except Exception:  # noqa: BLE001
                sett, lck, sent = 0.0, 0.0, 0
            results.setdefault("SW:" + sname, {})[ev] = sett
            locked_res.setdefault("SW:" + sname, {})[ev] = lck
            ent += sent
        entries_by_ev[ev] = ent
        print(f"  [{ev}] price={len(pres)} score={len(sres)} swing={len(SWING_GRID)} entries={ent}")

    active = [ev for ev, e in entries_by_ev.items() if e > 0]
    collect.locked_res = locked_res  # esposto per la summary
    return results, active


def summarize(results: Dict[str, Dict[str, float]], active: List[str],
              min_active: int) -> None:
    if len(active) < min_active:
        print(f"\n# Solo {len(active)} match ATTIVI (<{min_active}): campione ancora "
              f"troppo piccolo per un verdetto affidabile. Rilancia piu' tardi.")
        # mostra comunque l'aggregato sui match attivi
    active_sorted = sorted(active)
    train = active_sorted[::2]   # match pari
    test = active_sorted[1::2]   # match dispari
    print(f"\n# Match attivi: {len(active_sorted)}  |  TRAIN {len(train)}  TEST {len(test)}")
    if not train or not test:
        print("# Split train/test non ancora possibile (servono >=2 match attivi).")
        return

    locked_res = getattr(collect, "locked_res", {})

    def agg(d: Dict[str, Dict[str, float]], cfg: str, evs: List[str]):
        tot = 0.0; wins = 0; n = 0
        dd = d.get(cfg, {})
        for ev in evs:
            if ev in dd:
                tot += dd[ev]; n += 1
                if dd[ev] > 1e-9:
                    wins += 1
        return tot, wins, n

    rows = []
    for cfg in results:
        s_tr = agg(results, cfg, train); s_te = agg(results, cfg, test)
        l_tr = agg(locked_res, cfg, train); l_te = agg(locked_res, cfg, test)
        rows.append({"cfg": cfg, "s_tr": s_tr, "s_te": s_te,
                     "l_tr": l_tr, "l_te": l_te})

    # gate campione: sotto soglia il "verde su entrambi" e' rumore.
    if len(active_sorted) < min_active or len(train) < 3 or len(test) < 3:
        print("\n" + "#" * 100)
        print(f"VERDETTO NON DISPONIBILE — solo {len(active_sorted)} match ATTIVI "
              f"(TRAIN {len(train)}/TEST {len(test)}). Servono >=8-10 match attivi con "
              f">=3 per lato per un verdetto NON-rumore. Attendere il settlement dei liquidi.")
        print("#" * 100)
        return

    # === VERDETTO PRIMARIO: LOCKED (profitto GARANTITO = trade, non scommessa) ===
    # daniele: non tenere a settlement (direzionale); chiudere in profit. Il locked>0
    # su ENTRAMBI train e test = edge che chiude in verde a prescindere dal risultato.
    lrows = sorted(rows, key=lambda r: min(r["l_tr"][0], r["l_te"][0]), reverse=True)
    print("\n" + "#" * 100)
    print("VERDETTO PRIMARIO — LOCKED (profitto GARANTITO, result-INDIPENDENTE):")
    print("  config con LOCKED>0 su train E test = chiude in profit senza dipendere da chi vince")
    print("#" * 100)
    robust_locked = [r for r in lrows if r["l_tr"][0] > 0 and r["l_te"][0] > 0]
    if not robust_locked:
        print("  NESSUNA config ha locked>0 su entrambi i lati finora.")
    for r in robust_locked[:15]:
        lt, ltw, ltn = r["l_tr"]; le, lew, len_ = r["l_te"]
        print(f"  {r['cfg']}\n     LOCKED train {lt:+.2f} ({ltw}/{ltn})  test {le:+.2f} ({lew}/{len_})"
              f"  -> GARANTITO {lt+le:+.2f}")

    # === riferimento: settled (direzionale, dipende dal risultato) ===
    srows = sorted(rows, key=lambda r: min(r["s_tr"][0], r["s_te"][0]), reverse=True)
    print("\n" + "=" * 100)
    print("RIFERIMENTO — SETTLED (direzionale: dipende da chi vince, puo' essere fortuna):")
    print("=" * 100)
    print(f"{'#':>3} {'TRAIN':>8} {'TR_WR':>6} {'TEST':>8} {'TE_WR':>6}  CONFIG")
    for i, r in enumerate(srows[:15], 1):
        st, sw, sn = r["s_tr"]; et, ew, en = r["s_te"]
        print(f"{i:>3} {st:>+8.2f} {sw:>2}/{sn:<3} {et:>+8.2f} {ew:>2}/{en:<3}  {r['cfg']}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Validazione train/test 808 combo")
    p.add_argument("--data", required=True)
    p.add_argument("--min-active", type=int, default=6)
    p.add_argument("--min-matched", type=float, default=None,
                   help="override gate liquidita' su tutte le config (bug #6)")
    p.add_argument("--min-coverage", type=float, default=None,
                   help="esclude i raw con copertura registrazione sotto soglia (%%)")
    args = p.parse_args(argv)

    results, active = collect(args.data, min_matched=args.min_matched,
                              min_coverage=args.min_coverage)
    summarize(results, active, args.min_active)

    out = os.path.join(args.data, "_validation.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"active": sorted(active), "results": results}, fh, default=str)
    print(f"\n# dettaglio -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
