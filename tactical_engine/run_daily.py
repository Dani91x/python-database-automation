"""CLI manuale del Tactical Engine (per test/backfill puntuale di una data).
In produzione il motore gira agganciato a Prediction/today_predictions_backfill.py
(vedi tactical_engine/serving.py). Uso:  python -m tactical_engine.run_daily [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import logging
import os

from tactical_engine.serving import run_for_date

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: oggi UTC)")
    ap.add_argument("--max-leagues", type=int, default=int(os.getenv("TE_MAX_LEAGUES", "0")))
    args = ap.parse_args()
    res = run_for_date(args.date, max_leagues=args.max_leagues)
    print(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
