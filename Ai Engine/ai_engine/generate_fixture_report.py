from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
AI_ENGINE_DIR = os.path.join(ROOT, "Ai Engine")
if AI_ENGINE_DIR not in sys.path:
    sys.path.insert(0, AI_ENGINE_DIR)

from ai_engine.market_ranking import TARGET_TO_MARKET
from ai_engine.predict_fixture import predict_fixture
from ai_engine.db_adapter import fetch_fixture_prediction_by_id, fetch_matches_for_league_seasons, fetch_seasons_for_league
from ai_engine.feature_pipeline import build_feature_dataframe_for_fixtures
from ai_engine.coverage import build_coverage_report


def _rank_markets(preds: dict) -> list[tuple[str, float, str]]:
    ranked = []
    for target, probs in preds.items():
        if not probs:
            continue
        label = max(probs, key=probs.get)
        confidence = float(probs[label])
        market = TARGET_TO_MARKET.get(target, target)
        ranked.append((market, confidence, label))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


def _format_line(line: str) -> str:
    return line.replace(".", ",")


def _action_label(market: str, pred_label: str) -> str:
    # Make the action explicit for the user
    pl = str(pred_label)
    if market.startswith("Home Over "):
        line = _format_line(market.replace("Home Over ", ""))
        return f"Casa segna 1+ gol (Over {line})" if pl in ("True", "over") else "Casa a secco (0 gol)"
    if market.startswith("Away Over "):
        line = _format_line(market.replace("Away Over ", ""))
        return f"Trasferta segna 1+ gol (Over {line})" if pl in ("True", "over") else "Trasferta a secco (0 gol)"
    if market.startswith("Over "):
        line = _format_line(market.replace("Over ", ""))
        return f"Under {line}" if pl in ("False", "under") else f"Over {line}"
    if market == "BTTS":
        return "NO (entrambe NON segnano)" if pl in ("False", "no") else "SI (entrambe segnano)"
    if market == "1X2" or market == "FT 1X2" or market == "HT 1X2":
        return {"H": "Casa", "D": "Pareggio", "A": "Trasferta"}.get(pl, pl)
    if market == "HT/FT":
        return "Dati insufficienti" if pl == "_" else pl.replace("_", "->")
    return pl


def _confidence_text(conf: float) -> str:
    if conf >= 0.75:
        return "alta"
    if conf >= 0.6:
        return "media"
    return "bassa"


def _explain_top_markets(
    ranked: list[tuple[str, float, str]],
    preds: dict,
    data_summary: str,
) -> list[str]:
    lines = []
    for market, conf, label in ranked[:5]:
        action = _action_label(market, label)
        if market.startswith("Over "):
            target = None
            for t, m in TARGET_TO_MARKET.items():
                if m == market:
                    target = t
                    break
            probs = preds.get(target, {})
            over_prob = probs.get("True") or probs.get("over")
            detail = (
                f"prob Over {market.replace('Over ', '').replace('.', ',')} ~ {over_prob:.2f}"
                if over_prob is not None
                else "prob Over non disponibile"
            )
            if action.startswith("Under"):
                lines.append(f"- {action}: prob bassa di molti gol ({detail}). {data_summary}")
            else:
                lines.append(f"- {action}: prob alta di molti gol ({detail}). {data_summary}")
        elif market == "BTTS":
            lines.append(f"- BTTS {action}: conf {conf:.2f} ({_confidence_text(conf)}). {data_summary}")
        elif market == "1X2":
            lines.append(f"- 1X2: esito {action} con conf {conf:.2f} ({_confidence_text(conf)}). {data_summary}")
        else:
            lines.append(f"- {market}: esito {action} con conf {conf:.2f} ({_confidence_text(conf)}). {data_summary}")
    return lines


def _hist_feature_breakdown(features_df: pd.DataFrame) -> list[str]:
    if features_df.empty:
        return []

    hist_cols = [c for c in features_df.columns if c.startswith("home_hist_") or c.startswith("away_hist_")]
    if not hist_cols:
        return []

    row = features_df.iloc[0]
    player_keys = {
        "minutes",
        "shots_total",
        "shots_on",
        "goals_total",
        "assists_total",
        "passes_total",
        "passes_key",
        "passes_accurate",
        "tackles_total",
        "interceptions",
        "duels_total",
        "duels_won",
        "dribbles_attempts",
        "dribbles_success",
        "fouls_drawn",
        "fouls_committed",
        "yellow_cards",
        "red_cards",
        "offsides",
        "rating",
    }
    event_keys = {"goals", "yellow_cards", "red_cards", "avg_goal_minute"}

    groups = {
        "eventi": [],
        "team_stats": [],
        "player_stats": [],
        "injuries": [],
        "base_match": [],
    }

    for col in hist_cols:
        raw = col
        raw = raw.replace("home_hist_", "").replace("away_hist_", "")
        # remove rolling prefix
        for n in (5, 10, 15):
            raw = raw.replace(f"hist_w{n}_", "")
        if "injuries_count" in raw:
            groups["injuries"].append(col)
        elif raw in event_keys:
            groups["eventi"].append(col)
        elif raw in player_keys:
            groups["player_stats"].append(col)
        elif raw in {"gf", "ga"}:
            groups["base_match"].append(col)
        else:
            groups["team_stats"].append(col)

    lines = []
    for name, cols in groups.items():
        if not cols:
            continue
        ok = int(row[cols].notna().sum())
        total = int(len(cols))
        lines.append(f"- {name}: {ok}/{total}")
    return lines


def generate_report(fixture_id: int) -> str:
    preds = predict_fixture(fixture_id)
    ranked = _rank_markets(preds)

    # coverage info
    fx_rows = fetch_fixture_prediction_by_id(fixture_id)
    fx_df = pd.DataFrame(fx_rows)
    league_id = int(fx_df.iloc[0]["league_id"]) if not fx_df.empty else None
    seasons = fetch_seasons_for_league(league_id) if league_id is not None else []
    league_seasons = [(league_id, s) for s in seasons[-3:]] if league_id is not None else []
    history_rows = fetch_matches_for_league_seasons(league_seasons) if league_seasons else []
    history_df = pd.DataFrame(history_rows)
    features_df = build_feature_dataframe_for_fixtures(
        fx_df,
        history_df,
        league_seasons,
        include_events=True,
        include_team_stats=True,
        include_injuries=True,
        include_player_stats=True,
        pre_match=True,
    )
    coverage = build_coverage_report(features_df) if not features_df.empty else {}

    # historical coverage depth
    hist_cols = [c for c in features_df.columns if c.startswith("home_hist_") or c.startswith("away_hist_")]
    hist_non_null = int(features_df[hist_cols].notna().sum(axis=1).iloc[0]) if hist_cols else 0
    hist_total = int(len(hist_cols)) if hist_cols else 0
    hist_ratio = (hist_non_null / hist_total) if hist_total else 0.0

    # historical matches per team
    home_team_id = int(fx_df.iloc[0]["home_team_id"]) if not fx_df.empty else None
    away_team_id = int(fx_df.iloc[0]["away_team_id"]) if not fx_df.empty else None
    home_matches = 0
    away_matches = 0
    if not history_df.empty and home_team_id is not None and away_team_id is not None:
        home_matches = int(
            (history_df["home_team_id"].eq(home_team_id) | history_df["away_team_id"].eq(home_team_id)).sum()
        )
        away_matches = int(
            (history_df["home_team_id"].eq(away_team_id) | history_df["away_team_id"].eq(away_team_id)).sum()
        )
    min_matches = min(home_matches, away_matches) if home_matches and away_matches else 0

    report_dir = os.path.join("Ai Engine", "reports")
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, f"fixture_{fixture_id}_report.md")

    lines = []
    lines.append(f"# Fixture Report - {fixture_id}")
    lines.append("")
    lines.append(f"Generated at: {datetime.now(timezone.utc).isoformat()} UTC")
    lines.append("")
    lines.append("Sintesi consigliata:")
    if ranked:
        top_action = _action_label(ranked[0][0], ranked[0][2])
        lines.append(f"- Mercato piu affidabile: {top_action} (conf {ranked[0][1]:.2f})")
    lines.append("")
    data_summary = (
        f"Storico disponibile: casa {home_matches} partite, trasferta {away_matches} partite. "
        f"Medie calcolate su finestre 5/10/15. "
        f"Copertura feature {hist_non_null}/{hist_total} ({hist_ratio:.0%})."
    )
    lines.append("Perche (prime 5):")
    lines.extend(_explain_top_markets(ranked, preds, data_summary))
    lines.append("")
    lines.append("Copertura dati:")
    lines.append(
        f"- Partite storiche disponibili: casa {home_matches}, trasferta {away_matches}, "
        f"minimo {min_matches} (finestre 5/10/15)."
    )
    if hist_total:
        lines.append(f"- Feature storiche disponibili: {hist_non_null}/{hist_total} ({hist_ratio:.0%}).")
    if min_matches < 10 or hist_ratio < 0.6:
        lines.append("- Avvertenza: copertura dati bassa, affidabilita potenzialmente ridotta.")
    for name, data in coverage.items():
        lines.append(f"- {name}: {data.get('ok', 0)}/{data.get('total', 0)}")
    breakdown_lines = _hist_feature_breakdown(features_df)
    if breakdown_lines:
        lines.append("- Dettaglio feature storiche per categoria:")
        lines.extend(breakdown_lines)
    lines.append("")
    lines.append("Tutti i mercati (ordine per affidabilita):")
    for market, conf, label in ranked:
        action = _action_label(market, label)
        lines.append(
            f"- {market}: consiglio {action} | conf {conf:.2f} ({_confidence_text(conf)}) | {data_summary}"
        )
    lines.append("")
    lines.append("Dettagli tecnici (probabilita grezze):")
    for target, probs in preds.items():
        lines.append(f"- {target}: {probs}")
    if "target_exact_score" in preds and preds["target_exact_score"]:
        lines.append("")
        lines.append("Risultati esatti piu probabili:")
        exact_probs = preds["target_exact_score"]
        top_scores = sorted(exact_probs.items(), key=lambda x: x[1], reverse=True)[:5]
        for score, prob in top_scores:
            lines.append(f"- {score}: {prob:.2f}")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python generate_fixture_report.py <fixture_id>")
    fid = int(sys.argv[1])
    out = generate_report(fid)
    print(out)
