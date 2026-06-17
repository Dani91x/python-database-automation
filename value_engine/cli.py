"""
cli.py — interfaccia a riga di comando del calcolatore.

Mercati a gol totali (FT/HT), retro-compatibile col prototipo:
  python -m value_engine.cli U35 1.30 8 1            # mercato, quota pre-match, minuto, gol nel periodo
  python -m value_engine.cli U35 1.30 17 1 3.60      # + quota opposta (de-vig)
  python -m value_engine.cli U35 1.30 17 1 3.60 0.05 # + commissione
"""
from __future__ import annotations
import sys
from . import markets
from . import goal_timing
from .devig import devig_pair
from .pricing import price


def main(argv=None) -> int:
    a = (argv if argv is not None else sys.argv[1:])
    if len(a) < 4:
        print(__doc__)
        return 1
    market = a[0].upper()
    try:
        q0 = float(a[1])
        minute = float(a[2])
        goals = int(a[3])
        q_opp = float(a[4]) if len(a) > 4 else None
        comm = float(a[5]) if len(a) > 5 else 0.05
    except ValueError as exc:
        print(f"[CLI] Argomenti non validi: {exc}", file=sys.stderr)
        return 1

    if not markets.is_total(market):
        print(f"[CLI] Mercato '{market}' non e' un totale; 1X2/BTTS arrivano col modulo bivariate (task #5).")
        return 2

    p0 = devig_pair(q0, q_opp) if q_opp else 1.0 / q0
    vig = f"de-vig con quota opposta {q_opp}" if q_opp else "implicita 1/quota (include margine)"
    p = markets.prob_total(market, p0, minute, goals, remaining_frac=goal_timing.remaining_frac)
    mp = price(market, p, comm)

    side, line, T = markets.TOTALS[market]
    print("=" * 58)
    print(f"  {market}  ({side} {line}, periodo {T}')  |  quota pre-match {q0}  ({vig})")
    print("=" * 58)
    print(f"  Minuto {minute:.0f}'  gol nel periodo: {goals}")
    print(f"  Probabilita' reale : {p*100:.1f}%")
    print(f"  Quota FAIR         : {mp.fair_odds}")
    print(f"  BACK: entra se quota live >= {mp.min_back}")
    print(f"  LAY : entra se quota lay  <= {mp.max_lay}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
