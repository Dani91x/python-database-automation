"""Esperimento discriminante fra FAMIGLIE di strategia (RD-Agent round 0).

Domanda: quale famiglia CHIUDE round-trip a profitto (non gambe nude) su
mercati NON-elite? Gira poche config rappresentative su un set veloce, sia
pre-match che in-play(8s). Guida dove puntare le migliaia di test successive.

Uso: python -m Betfair.stream.scalper_lab.exp_families
"""
from __future__ import annotations

import json

from Betfair.stream.scalper_lab.bt_lab import run_config

# set veloci (raw piccolo). Pre-match: solo match CON finestra pre-match.
PRE_SET = ["35760084", "35774000"]           # 55m / 39m pre-match, raw ~7-8MB
INPLAY_SET = ["35772591", "35759636", "35774000", "35760084"]  # tutti in-play

# bande di quota di esempio (tick dinamici): quote basse = piu' tolleranti sui
# tick (valgono poco), quote alte = piu' stretto (1 tick vale molto).
BANDS = [
    {"max_odds": 2.0, "max_spread_ticks": 3, "min_size": 30, "scalp_ticks": 2, "stop_ticks": 3, "capture_max_ticks": 10},
    {"max_odds": 4.0, "max_spread_ticks": 2, "min_size": 20, "scalp_ticks": 1, "stop_ticks": 2, "capture_max_ticks": 8},
    {"max_odds": 1000, "max_spread_ticks": 2, "min_size": 10, "scalp_ticks": 1, "stop_ticks": 2, "capture_max_ticks": 6},
]

FAMILIES = {
    "neutral_default": {},
    "neutral_loose": {"min_size": 20, "min_flow": 2, "max_spread_ticks": 4},
    "neutral_banded": {"min_flow": 2, "tick_bands": BANDS},
    "reversion_1_2": {"mode": "reversion", "scalp_ticks": 1, "stop_ticks": 2,
                       "max_spread_ticks": 3, "min_size": 5, "min_flow": 0},
    "reversion_2_3": {"mode": "reversion", "scalp_ticks": 2, "stop_ticks": 3,
                       "max_spread_ticks": 4, "min_size": 5, "min_flow": 0},
    "reversion_far": {"mode": "reversion", "scalp_ticks": 2, "stop_ticks": 2,
                       "stop_ticks_far": 5, "max_spread_ticks": 4, "min_size": 5, "min_flow": 0},
    "trend_surf": {"trend_mode": True, "swing_only": True, "trend_min_ticks": 3,
                    "trend_flow_ratio": 1.5, "min_size": 5, "min_flow": 1,
                    "max_spread_ticks": 5},
}


def _row(res: dict) -> str:
    return (f"act={res['n_active']}/{res['n_events']} grn={res['n_green']} "
            f"NET={res['tot_net']:+.2f} locked={res['tot_locked']:+.2f} "
            f"rt={res['tot_roundtrips']} ord={res['tot_orders']} "
            f"nk={res['tot_naked_sels']}(risk{res['tot_naked_risk']:.0f})")


def main() -> None:
    for mode, events in (("prematch", PRE_SET), ("inplay", INPLAY_SET)):
        print(f"\n{'='*72}\n {mode.upper()}  set={events}\n{'='*72}")
        print(f"{'FAMIGLIA':<18} risultato")
        ranking = []
        for name, params in FAMILIES.items():
            p = {"stake": 25.0, **params}
            res = run_config(p, mode, events, label=name)
            ranking.append((name, res))
            print(f"{name:<18} {_row(res)}")
        # miglior P&L reale netto
        ranking.sort(key=lambda kv: kv[1]["tot_net"], reverse=True)
        best = ranking[0]
        print(f"\n>>> miglior NET reale [{mode}]: {best[0]} = {best[1]['tot_net']:+.2f} "
              f"(locked={best[1]['tot_locked']:+.2f}, rt={best[1]['tot_roundtrips']}, "
              f"naked={best[1]['tot_naked_sels']})")


if __name__ == "__main__":
    main()
