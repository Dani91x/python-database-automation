"""Loop evolutivo stile RD-Agent per cercare una config scalper profittevole.

Metodo (adattato da microsoft/rd-agent):
  IPOTESI -> IMPLEMENTA (config) -> BACKTEST onesto (flumine) -> FEEDBACK -> EVOLVI

Per rendere fattibili migliaia di test senza aspettare ore:
  1) RICERCA GREZZA su FAST_SET (i match con raw piu' piccolo) = pruning rapido
  2) VALIDAZIONE dei sopravvissuti su FULL_SET (tutti i 12) = numero onesto
  3) EVOLUZIONE: prendi i top-K, muta i parametri, ri-valuta

Score (onesto, orientato alle OCCASIONI):
  premia netFLAT reale (edge vero) e n_active (occasioni), penalizza naked.
  Un verde da gamba nuda NON e' edge -> pesato a zero/negativo.

Knowledge store persistente -> knowledge_store.json (resume-able, mai perde lavoro).

Uso:
  python -m Betfair.stream.scalper_lab.rdloop --mode prematch --rounds 4 --topk 5
  python -m Betfair.stream.scalper_lab.rdloop --mode inplay --rounds 4
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import time
from typing import Any, Dict, List

from Betfair.stream.scalper_lab.bt_lab import COMPLETE, run_config

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "knowledge_store.json")

# FAST_SET: match con raw piccolo (~7-9 MB) per pruning veloce.
FAST_SET = ["35772591", "35760084", "35759636", "35774000"]
FULL_SET = COMPLETE


# ---------------------------------------------------------------- score
def score(res: Dict[str, Any]) -> float:
    """Score onesto. netFLAT = edge vero. n_active = occasioni. naked penalizzato."""
    n = max(res["n_events"], 1)
    edge = res["tot_net_flat"]                     # profitto reale bloccato
    occ = res["n_active"] / n                       # frazione match con occasioni
    green = res["n_green"] / n                       # frazione match in verde
    naked_pen = 0.15 * res["tot_naked_sels"]         # penalita' rischio scoperto
    # priorita': edge reale, poi copertura occasioni/green, meno le nude
    return edge + 2.0 * occ + 3.0 * green - naked_pen


# ---------------------------------------------------------------- store
def load_store() -> List[Dict[str, Any]]:
    if os.path.isfile(STORE):
        try:
            with open(STORE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_store(rows: List[Dict[str, Any]]) -> None:
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)


def _key(params: Dict[str, Any], mode: str) -> str:
    return mode + "|" + json.dumps(params, sort_keys=True)


# ---------------------------------------------------------------- spazio di ricerca
def seed_grid(mode: str, stake: float) -> List[Dict[str, Any]]:
    """Griglia iniziale: leve che governano OCCASIONI + cattura."""
    grids: Dict[str, List[Any]] = {
        "min_size": [10, 20, 40, 80],
        "min_flow": [0, 2, 5, 10],
        "max_spread_ticks": [2, 3, 4, 6],
        "mode": ["auto", "join", "maker"],
    }
    keys = list(grids)
    combos = []
    for vals in itertools.product(*[grids[k] for k in keys]):
        p: Dict[str, Any] = {"stake": stake}
        p.update(dict(zip(keys, vals)))
        combos.append(p)
    return combos


def mutate(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Evoluzione: perturba i parametri numerici del vincitore."""
    out = []
    numeric = {
        "min_size": [max(5, params.get("min_size", 40) * f) for f in (0.5, 0.75, 1.5, 2.0)],
        "min_flow": [round(max(0, params.get("min_flow", 5) + d), 1) for d in (-3, -1, 1, 3)],
        "max_spread_ticks": [max(1, params.get("max_spread_ticks", 3) + d) for d in (-1, 1, 2)],
    }
    for k, vals in numeric.items():
        for v in vals:
            child = dict(params)
            child[k] = v
            out.append(child)
    return out


# ---------------------------------------------------------------- eval
def evaluate(params: Dict[str, Any], mode: str, events: List[str],
             label: str) -> Dict[str, Any]:
    t0 = time.time()
    res = run_config(params, mode, events, label=label)
    res["score"] = round(score(res), 3)
    res["secs"] = round(time.time() - t0, 1)
    res["eval_set"] = "fast" if events is FAST_SET else "full"
    # non salvo per_event nel record compatto dello store
    compact = {k: v for k, v in res.items() if k != "per_event"}
    return compact


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["prematch", "inplay"], default="prematch")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--topk", type=int, default=5)
    ap.add_argument("--stake", type=float, default=25.0)
    ap.add_argument("--max-seed", type=int, default=0, help="limita la griglia seed (0=tutta)")
    args = ap.parse_args()

    store = load_store()
    seen = {_key(r["params"], r["mode"]) for r in store}

    # -------- ROUND 0: griglia seed su FAST_SET --------
    seed = seed_grid(args.mode, args.stake)
    if args.max_seed > 0:
        seed = seed[: args.max_seed]
    print(f"[{args.mode}] ROUND 0 seed: {len(seed)} config su FAST_SET {FAST_SET}")
    round_results: List[Dict[str, Any]] = []
    for i, p in enumerate(seed):
        k = _key(p, args.mode)
        if k in seen:
            continue
        r = evaluate(p, args.mode, FAST_SET, label=f"r0_{i}")
        seen.add(k); store.append(r); round_results.append(r)
        print(f"  seed {i+1}/{len(seed)} score={r['score']:+.2f} "
              f"act={r['n_active']} grn={r['n_green']} net={r['tot_net_flat']:+.2f} "
              f"scalp={r['tot_scalps']} nk={r['tot_naked_sels']} ({r['secs']}s) {json.dumps(p)}")
        save_store(store)

    # -------- ROUND 1..N: evoluzione dai migliori --------
    for rnd in range(1, args.rounds + 1):
        pool = [r for r in store if r["mode"] == args.mode and r["eval_set"] == "fast"]
        pool.sort(key=lambda r: r["score"], reverse=True)
        parents = pool[: args.topk]
        print(f"\n[{args.mode}] ROUND {rnd} evoluzione da top-{len(parents)}: "
              f"best score={parents[0]['score'] if parents else 0}")
        children: List[Dict[str, Any]] = []
        for par in parents:
            children.extend(mutate(par["params"]))
        for i, p in enumerate(children):
            k = _key(p, args.mode)
            if k in seen:
                continue
            r = evaluate(p, args.mode, FAST_SET, label=f"r{rnd}_{i}")
            seen.add(k); store.append(r); children_done = r
            print(f"  child {i+1}/{len(children)} score={r['score']:+.2f} "
                  f"act={r['n_active']} grn={r['n_green']} net={r['tot_net_flat']:+.2f} "
                  f"nk={r['tot_naked_sels']} {json.dumps(p)}")
            save_store(store)

    # -------- VALIDAZIONE top-K su FULL_SET --------
    pool = [r for r in store if r["mode"] == args.mode and r["eval_set"] == "fast"]
    pool.sort(key=lambda r: r["score"], reverse=True)
    print(f"\n[{args.mode}] VALIDAZIONE top-{args.topk} su FULL_SET (12 match)")
    for r in pool[: args.topk]:
        vk = _key(r["params"], args.mode) + "|FULL"
        if vk in seen:
            continue
        v = evaluate(r["params"], args.mode, FULL_SET, label="VALID")
        seen.add(vk); store.append(v)
        print(f"  VALID score={v['score']:+.2f} act={v['n_active']}/12 "
              f"grn={v['n_green']}/12 net={v['tot_net_flat']:+.2f} "
              f"scalp={v['tot_scalps']} nk={v['tot_naked_sels']} {json.dumps(r['params'])}")
        save_store(store)

    # -------- riepilogo migliori FULL --------
    full = [r for r in store if r["mode"] == args.mode and r["eval_set"] == "full"]
    full.sort(key=lambda r: r["score"], reverse=True)
    print(f"\n===== MIGLIORI su FULL_SET [{args.mode}] =====")
    for r in full[:8]:
        print(f"  score={r['score']:+.2f} act={r['n_active']}/12 grn={r['n_green']}/12 "
              f"net={r['tot_net_flat']:+.2f} nk={r['tot_naked_sels']} {json.dumps(r['params'])}")


if __name__ == "__main__":
    main()
