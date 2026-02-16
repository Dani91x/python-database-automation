from __future__ import annotations

from datetime import date, datetime
from typing import Dict

import pandas as pd


def _coverage_line(name: str, data: Dict[str, int]) -> str:
    ok = data.get("ok", 0)
    total = data.get("total", 0)
    return f"- {name}: {ok}/{total}"


def write_report(
    target_date: date,
    df: pd.DataFrame,
    coverage: Dict[str, Dict[str, int]],
    report_path: str,
    include_matches: bool = True,
) -> None:
    lines = []
    lines.append(f"# AI Validation Report - {target_date.isoformat()}")
    lines.append("")
    lines.append(f"Generated at: {datetime.utcnow().isoformat()} UTC")
    lines.append("")

    total = len(df)
    lines.append(f"Total fixtures: {total}")
    lines.append("")
    lines.append("Coverage:")
    for name, data in coverage.items():
        lines.append(_coverage_line(name, data))
    lines.append("")

    if not df.empty and "ordered_markets" in df.columns:
        lines.append("Top Markets (All Fixtures):")
        top = []
        for _, row in df.iterrows():
            fixture_id = row.get("fixture_id")
            home = row.get("home_team_name")
            away = row.get("away_team_name")
            ranked = row.get("ordered_markets", [])
            for mkt, score, label in ranked:
                top.append((score, fixture_id, home, away, mkt, label))
        top.sort(reverse=True, key=lambda x: x[0])
        for score, fixture_id, home, away, mkt, label in top[:50]:
            lines.append(f"- {score:.2f} | {fixture_id} | {home} vs {away} | {mkt} | pred={label}")
        lines.append("")

    if include_matches and not df.empty:
        lines.append("Match Details:")
        for _, row in df.iterrows():
            fixture_id = row.get("fixture_id")
            home = row.get("home_team_name")
            away = row.get("away_team_name")
            fdate = row.get("fixture_date")
            market = row.get("suggested_market")
            reason = row.get("suggested_reason")
            notes = row.get("suggested_notes")
            conf = row.get("suggested_confidence", "")
            lines.append(f"- {fixture_id} | {home} vs {away} | {fdate} | {market} | {reason} | {notes} | {conf}")
            ranked = row.get("ordered_markets", [])
            if ranked:
                for mkt, score, label in ranked:
                    lines.append(f"- {mkt} | score={score:.2f} | pred={label}")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
