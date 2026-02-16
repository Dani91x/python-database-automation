from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd


def _coverage_count(df: pd.DataFrame, columns: List[str]) -> Tuple[int, int]:
    if not columns:
        return 0, len(df)
    existing = [c for c in columns if c in df.columns]
    if not existing:
        return 0, len(df)
    ok = df[existing].notna().all(axis=1).sum()
    return int(ok), int(len(df))


def _coverage_any(df: pd.DataFrame, columns: List[str]) -> Tuple[int, int]:
    if not columns:
        return 0, len(df)
    existing = [c for c in columns if c in df.columns]
    if not existing:
        return 0, len(df)
    ok = df[existing].notna().any(axis=1).sum()
    return int(ok), int(len(df))


def build_coverage_report(df: pd.DataFrame) -> Dict[str, Dict[str, int]]:
    if df.empty:
        return {}

    groups = {
        "odds_1x2": ["odds_1x2_home", "odds_1x2_draw", "odds_1x2_away"],
        "odds_ou_25": ["odds_over_2_5", "odds_under_2_5"],
        "odds_btts": ["odds_btts_yes", "odds_btts_no"],
        "pre_xg": ["goals_home_line", "goals_away_line"],
        "events": [c for c in df.columns if c.startswith("home_hist_") or c.startswith("away_hist_")],
        "team_stats": [c for c in df.columns if c.startswith("home_hist_") or c.startswith("away_hist_")],
        "player_stats": [c for c in df.columns if c.startswith("home_hist_") or c.startswith("away_hist_")],
        "injuries": [c for c in df.columns if c.startswith("home_hist_") or c.startswith("away_hist_")],
        "standings": [c for c in df.columns if c.startswith("home_standings_") or c.startswith("away_standings_")],
        "form": [c for c in df.columns if c.startswith("home_form_") or c.startswith("away_form_")],
    }

    report: Dict[str, Dict[str, int]] = {}
    for name, cols in groups.items():
        if name in {"events", "team_stats", "player_stats", "injuries"}:
            ok, total = _coverage_any(df, cols)
        else:
            ok, total = _coverage_count(df, cols)
        report[name] = {"ok": ok, "total": total}

    return report
