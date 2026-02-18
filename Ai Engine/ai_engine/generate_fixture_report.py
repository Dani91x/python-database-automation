"""
Generate human-readable fixture report with value bets and confidence gates.

Produces a markdown report showing:
- Top recommended bets (with EV, Kelly stake, confidence)
- Markets excluded (with reasons)
- Coverage and reliability details
- Profit balance
"""
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


def _action_label(market: str, pred_label: str) -> str:
    pl = str(pred_label)
    if market.startswith("Home Over "):
        line = market.replace("Home Over ", "").replace(".", ",")
        return f"Casa segna 1+ gol (Over {line})" if pl in ("True", "over") else "Casa a secco (0 gol)"
    if market.startswith("Away Over "):
        line = market.replace("Away Over ", "").replace(".", ",")
        return f"Trasferta segna 1+ gol (Over {line})" if pl in ("True", "over") else "Trasferta a secco (0 gol)"
    if market.startswith("Over "):
        line = market.replace("Over ", "").replace(".", ",")
        return f"Under {line}" if pl in ("False", "under") else f"Over {line}"
    if market == "BTTS":
        return "NO (entrambe NON segnano)" if pl in ("False", "no") else "SI (entrambe segnano)"
    if market in ("1X2", "FT 1X2", "HT 1X2"):
        return {"H": "Casa", "D": "Pareggio", "A": "Trasferta"}.get(pl, pl)
    if market == "HT/FT":
        return "Dati insufficienti" if pl == "_" else pl.replace("_", "->")
    if market == "Clean Sheet Home":
        return "SI (clean sheet casa)" if pl in ("True",) else "NO"
    if market == "Clean Sheet Away":
        return "SI (clean sheet trasferta)" if pl in ("True",) else "NO"
    return pl


def _confidence_text(conf: float) -> str:
    if conf >= 0.75:
        return "alta"
    if conf >= 0.6:
        return "media"
    return "bassa"


def generate_report(fixture_id: int) -> str:
    """Generate a complete fixture report with value betting analysis."""
    result = predict_fixture(fixture_id)

    report_dir = os.path.join("Ai Engine", "reports")
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, f"fixture_{fixture_id}_report.md")

    lines = []
    lines.append(f"# Fixture Report — {fixture_id}")
    lines.append("")
    lines.append(f"Generated at: {result.get('generated_at', datetime.now(timezone.utc).isoformat())} UTC")
    lines.append("")

    # ── Reliability Summary ──────────────────────────────────
    rel = result.get("reliability", {})
    coverage = result.get("coverage", {})
    lines.append("## Affidabilità Dati")
    lines.append("")
    grade_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(rel.get("grade", "low"), "⚪")
    lines.append(f"- **Grado**: {grade_emoji} {rel.get('grade', 'N/A').upper()} (score: {rel.get('score', 0):.2f})")
    lines.append(f"- Copertura feature: {coverage.get('features_pct', 0):.0%}")
    lines.append(f"- Partite storiche: casa {coverage.get('matches_home', 0)}, trasferta {coverage.get('matches_away', 0)}")
    lines.append("")

    # ── Value Bets Section ──────────────────────────────────
    bet_signals = result.get("bet_signals", [])
    no_bet_reasons = result.get("no_bet_reasons", [])

    if bet_signals:
        lines.append("## ✅ Scommesse Consigliate (Value Bets)")
        lines.append("")
        lines.append("| Mercato | Azione | Prob Modello | Prob Implicita | EV | Quota | Stake Kelly | Conf |")
        lines.append("|---------|--------|-------------|---------------|------|-------|-------------|------|")
        for s in bet_signals:
            market_name = TARGET_TO_MARKET.get(s["market"], s["market"])
            action = _action_label(market_name, s["action"])
            lines.append(
                f"| {market_name} "
                f"| {action} "
                f"| {s['model_prob']:.1%} "
                f"| {s['implied_prob']:.1%} "
                f"| +{s['expected_value']:.1%} "
                f"| {s['decimal_odds']:.2f} "
                f"| €{s['kelly_stake']:.0f} "
                f"| {s['confidence_grade']} |"
            )
        lines.append("")
        lines.append("> **Come leggere**: EV (Expected Value) > 0 = scommessa con valore.")
        lines.append("> Stake Kelly = importo consigliato su bankroll €1000 (quarter-Kelly).")
        lines.append("> Tutte le scommesse hanno superato i 3 gate di sicurezza.")
        lines.append("")
    else:
        lines.append("## ⚠️ Nessuna Scommessa Consigliata")
        lines.append("")
        lines.append("Nessun mercato supera tutti i gate di sicurezza per questa partita.")
        lines.append("")

    # ── NO BET Section ──────────────────────────────────────
    if no_bet_reasons:
        lines.append("## ❌ Mercati Esclusi (NO BET)")
        lines.append("")
        for nb in no_bet_reasons[:15]:
            market_name = TARGET_TO_MARKET.get(nb.get("target", ""), nb.get("target", ""))
            lines.append(f"- **{market_name}**: {nb.get('reason', 'N/A')}")
        lines.append("")

    # ── Ensemble Agreement ──────────────────────────────────
    agreement = result.get("ensemble_agreement", {})
    if agreement:
        lines.append("## Consenso Modelli (Ensemble)")
        lines.append("")
        lines.append("| Target | Predizione | Accordo | Voti |")
        lines.append("|--------|-----------|---------|------|")
        for target, info in list(agreement.items())[:10]:
            market_name = TARGET_TO_MARKET.get(target, target)
            pred_class = info.get("predicted_class", "?")
            agr = info.get("agreement_ratio", 0)
            votes = info.get("votes", {})
            votes_str = ", ".join(f"{k}={v}" for k, v in votes.items())
            agr_emoji = "✅" if agr >= 0.66 else "⚠️"
            lines.append(f"| {market_name} | {pred_class} | {agr_emoji} {agr:.0%} | {votes_str} |")
        lines.append("")

    # ── Profit Balance ──────────────────────────────────────
    pb = result.get("profit_balance", {})
    if pb:
        lines.append("## Profit Balance (Odds)")
        lines.append("")
        for market, val in pb.items():
            lines.append(f"- {market}: {val}")
        lines.append("")

    # ── Coverage Detail ──────────────────────────────────────
    detail = coverage.get("detail", {})
    if detail:
        lines.append("## Dettaglio Copertura")
        lines.append("")
        for name, data in detail.items():
            ok = data.get("ok", 0)
            total = data.get("total", 0)
            pct = ok / total if total > 0 else 0
            bar = "█" * int(pct * 10) + "░" * (10 - int(pct * 10))
            lines.append(f"- {name}: {ok}/{total} {bar} {pct:.0%}")
        lines.append("")

    # ── Raw Probabilities ──────────────────────────────────
    lines.append("## Probabilità Grezze (Tutti i Target)")
    lines.append("")
    targets = result.get("targets", {})
    for target, probs in targets.items():
        if not probs:
            continue
        market_name = TARGET_TO_MARKET.get(target, target)
        best = max(probs, key=probs.get)
        best_prob = probs[best]
        probs_str = ", ".join(f"{k}={v:.2f}" for k, v in probs.items())
        lines.append(f"- **{market_name}** → {best} ({best_prob:.0%}) | {probs_str}")
    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python generate_fixture_report.py <fixture_id>")
    fid = int(sys.argv[1])
    out = generate_report(fid)
    print(f"Report: {out}")
