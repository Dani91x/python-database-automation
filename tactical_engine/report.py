"""Report PARLANTE per partita (condizione 6): chiaro e leggibile per l'utente.

Trasforma le probabilita' del motore in testo comprensibile + un consiglio
sintetico, onesto (probabilita', non certezze).
"""
from __future__ import annotations

from typing import Dict, List, Optional


def pct(p: float) -> str:
    return f"{100.0 * p:.0f}%"


def _confidence_word(p: float) -> str:
    if p >= 0.65:
        return "nettamente favorita"
    if p >= 0.50:
        return "favorita"
    if p >= 0.40:
        return "leggermente favorita"
    return "incerta"


def build_advice(pred_ft: Dict, names: Dict[int, str]) -> str:
    """Consiglio sintetico in linguaggio naturale, basato sui segnali piu' forti."""
    m = pred_ft["markets"]
    home = names.get(pred_ft["home_id"], str(pred_ft["home_id"]))
    away = names.get(pred_ft["away_id"], str(pred_ft["away_id"]))

    # esito 1X2 piu' probabile
    outcomes = {"1": (m["home"], f"vittoria {home}"),
                "X": (m["draw"], "pareggio"),
                "2": (m["away"], f"vittoria {away}")}
    best_key = max(outcomes, key=lambda k: outcomes[k][0])
    best_p, best_label = outcomes[best_key]

    parts: List[str] = []
    if best_key == "X":
        parts.append(f"Esito piu' probabile: **pareggio** ({pct(best_p)}), partita equilibrata.")
    else:
        squadra = home if best_key == "1" else away
        parts.append(f"Esito piu' probabile: **{best_label}** ({pct(best_p)}) — {squadra} {_confidence_word(best_p)}.")
        # doppia chance come rete di sicurezza se non e' netta
        if best_p < 0.55:
            if best_key == "1":
                parts.append(f"Rete di sicurezza: 1X (casa o pareggio) {pct(m['double_1x'])}.")
            else:
                parts.append(f"Rete di sicurezza: X2 (pareggio o trasferta) {pct(m['double_x2'])}.")

    # linea gol
    if m["over_2_5"] >= 0.58:
        parts.append(f"Tendenza gol: **Over 2.5** ({pct(m['over_2_5'])}), match aperto.")
    elif m["under_2_5"] >= 0.58:
        parts.append(f"Tendenza gol: **Under 2.5** ({pct(m['under_2_5'])}), match chiuso.")
    else:
        parts.append(f"Linea gol equilibrata (Over 2.5 {pct(m['over_2_5'])}).")

    # BTTS
    if m["btts_yes"] >= 0.55:
        parts.append(f"Entrambe a segno: **Si'** ({pct(m['btts_yes'])}).")
    elif m["btts_no"] >= 0.58:
        parts.append(f"Entrambe a segno: **No** ({pct(m['btts_no'])}).")

    return " ".join(parts)


def build_match_report(pred_ft: Dict, pred_ht: Optional[Dict], names: Dict[int, str],
                       counterfactual: Optional[Dict] = None) -> str:
    home = names.get(pred_ft["home_id"], str(pred_ft["home_id"]))
    away = names.get(pred_ft["away_id"], str(pred_ft["away_id"]))
    m = pred_ft["markets"]
    neutro = " [campo neutro]" if pred_ft.get("neutral") else ""

    lines: List[str] = []
    lines.append("=" * 60)
    lines.append(f"  {home}  vs  {away}{neutro}")
    lines.append("=" * 60)
    lines.append(f"  Gol attesi:   {home} {pred_ft['exp_goals_home']:.2f}   |   "
                 f"{away} {pred_ft['exp_goals_away']:.2f}")
    lines.append("")
    lines.append(f"  ESITO 1X2:        1 = {pct(m['home'])}    X = {pct(m['draw'])}    2 = {pct(m['away'])}")
    lines.append(f"  Doppia chance:    1X = {pct(m['double_1x'])}   12 = {pct(m['double_12'])}   X2 = {pct(m['double_x2'])}")
    lines.append(f"  Over/Under 2.5:   Over {pct(m['over_2_5'])}   Under {pct(m['under_2_5'])}")
    lines.append(f"  Over/Under 1.5:   Over {pct(m['over_1_5'])}   Under {pct(m['under_1_5'])}")
    lines.append(f"  BTTS:             Si' {pct(m['btts_yes'])}    No {pct(m['btts_no'])}")
    if pred_ht is not None:
        mh = pred_ht["markets"]
        lines.append(f"  Primo tempo 1X2:  1 = {pct(mh['home'])}    X = {pct(mh['draw'])}    2 = {pct(mh['away'])}")
        lines.append(f"  Primo tempo O/U 0.5: Over {pct(mh['over_0_5'])}   Under {pct(mh['under_0_5'])}")
    lines.append("")
    lines.append("  Risultati esatti piu' probabili:")
    for x, y, p in pred_ft["top_scores"]:
        lines.append(f"     {x}-{y}  ->  {pct(p)}")

    if counterfactual:
        lines.append("")
        lines.append("  Controllo counterfactual (sanita' causale):")
        for k, v in counterfactual.items():
            lines.append(f"     {v}")

    lines.append("")
    lines.append("  CONSIGLIO: " + build_advice(pred_ft, names))
    lines.append("=" * 60)
    return "\n".join(lines)
