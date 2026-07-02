"""CONNETTORE motori → bias dello scalper ("Model Exec").

Le TRE regole (tutte uscite dai test 02/07 su dati registrati, dossier §9.8):

  1. CONSENSO: ML e Poisson devono CONCORDARE sulla direzione 1X2
     (nei test: consenso → 4/4 direzioni giuste; senza Poisson o senza ML
     il consenso e' impossibile → nessun bias, il bot resta neutro).
  2. DOMINIO: entrambe le predizioni presenti E create PRIMA del kickoff
     (anti-leakage); leghe escludibili via ``excluded_league_ids``.
  3. EDGE MODERATO: la prob di consenso vs la prob implicita di mercato
     (mid) deve stare in [min_edge, max_edge]. Un edge ENORME contro un
     mercato liquido e' un errore del modello, non valore (test 1:
     banda 3-10% ≈ pari, banda 25-50% = disastro) → si scarta.

Output: bias {selection_id: 'BACK'|'LAY'} sul MATCH_ODDS (BACK sulla
selezione di consenso, LAY sulle altre due) + meta di debug con i motivi
di ogni decisione. La logica e' PURA (testabile senza rete): i dati
arrivano da fuori (fixture_predictions, nomi runner, quote correnti).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# banda di edge "moderato" (vs prob implicita mid): fuori banda niente bias
DEFAULT_MIN_EDGE = 0.02
DEFAULT_MAX_EDGE = 0.20


@dataclass(frozen=True)
class BiasDecision:
    """Esito del connettore. ``bias`` vuoto = bot resta neutro."""

    bias: Dict[int, str] = field(default_factory=dict)   # selection_id -> side
    consensus: bool = False
    direction: Optional[str] = None                      # 'H' | 'D' | 'A'
    prob_ml: Optional[float] = None
    prob_poisson: Optional[float] = None
    prob_market: Optional[float] = None
    edge: Optional[float] = None
    reasons: Tuple[str, ...] = ()

    def to_meta(self) -> Dict[str, Any]:
        return {
            "consenso": self.consensus,
            "direzione": self.direction,
            "prob_ml": self.prob_ml,
            "prob_poisson": self.prob_poisson,
            "prob_mercato": self.prob_market,
            "edge": self.edge,
            "motivi": list(self.reasons),
            "bias": {str(k): v for k, v in self.bias.items()},
        }


def _argmax_1x2(probs: Optional[Dict[str, Any]]) -> Optional[Tuple[str, float]]:
    """('H'|'D'|'A', prob) dalla mappa {H,D,A}; None se incompleta."""
    if not isinstance(probs, dict):
        return None
    vals = {}
    for k in ("H", "D", "A"):
        v = probs.get(k)
        if v is None:
            return None
        try:
            vals[k] = float(v)
        except (TypeError, ValueError):
            return None
    tot = sum(vals.values())
    if not (0.5 < tot < 1.5):   # sanity: devono essere probabilita'
        return None
    best = max(vals, key=lambda k: vals[k])
    return best, vals[best]


def extract_1x2(pred_row: Dict[str, Any]) -> Dict[str, Optional[Dict[str, float]]]:
    """Estrae le mappe 1X2 di ML e Poisson da una riga fixture_predictions."""
    ml = None
    tgt = ((pred_row.get("model_predictions_json") or {}).get("targets") or {})
    t = tgt.get("target_1x2") or tgt.get("target_ft_1x2")
    if isinstance(t, dict):
        ml = {"H": t.get("H"), "D": t.get("D"), "A": t.get("A")}
    po = None
    mkts = ((pred_row.get("db_json_analisi") or {}).get("markets") or {})
    if isinstance(mkts.get("1x2"), dict):
        po = mkts["1x2"]
    return {"ml": ml, "poisson": po}


def match_runner_roles(
    runner_names: Dict[int, str], home_name: str, away_name: str
) -> Optional[Dict[str, int]]:
    """{'H': sid, 'A': sid, 'D': sid} dai NOMI dei runner del MATCH_ODDS.

    ⚠️ SEMPRE per nome, MAI per sortPriority: su Betfair l'ordine casa/ospite
    puo' essere INVERTITO rispetto all'API (visto su dati reali 02/07).
    """
    def norm(s: str) -> str:
        return " ".join(str(s).lower().split())

    def team_match(sel: str, team: str) -> bool:
        a, b = norm(sel), norm(team)
        if not a or not b:
            return False
        if a == b or a in b or b in a:
            return True
        return len(set(a.split()) & set(b.split())) >= 1

    roles: Dict[str, int] = {}
    for sid, name in runner_names.items():
        if norm(name) == "the draw":
            roles["D"] = int(sid)
        elif team_match(name, home_name):
            roles["H"] = int(sid)
        elif team_match(name, away_name):
            roles["A"] = int(sid)
    if len(roles) != 3:
        return None
    return roles


def resolve_bias(
    pred_row: Optional[Dict[str, Any]],
    runner_names: Dict[int, str],
    home_name: str,
    away_name: str,
    market_mid_probs: Optional[Dict[str, float]] = None,   # {'H','D','A'} implied
    *,
    min_edge: float = DEFAULT_MIN_EDGE,
    max_edge: float = DEFAULT_MAX_EDGE,
    excluded_league_ids: Optional[set] = None,
) -> BiasDecision:
    """Applica le tre regole e produce la decisione di bias (PURA, no rete)."""
    reasons: List[str] = []
    if not pred_row:
        return BiasDecision(reasons=("nessuna predizione in fixture_predictions",))

    league_id = pred_row.get("league_id")
    if excluded_league_ids and league_id in excluded_league_ids:
        return BiasDecision(reasons=(f"lega {league_id} esclusa dal dominio",))

    probs = extract_1x2(pred_row)
    ml = _argmax_1x2(probs["ml"])
    po = _argmax_1x2(probs["poisson"])
    if ml is None:
        reasons.append("ML 1X2 assente/invalido")
    if po is None:
        reasons.append("Poisson 1X2 assente/invalido")
    if ml is None or po is None:
        return BiasDecision(reasons=tuple(reasons) + ("niente consenso → bot neutro",))

    if ml[0] != po[0]:
        return BiasDecision(
            consensus=False, prob_ml=ml[1], prob_poisson=po[1],
            reasons=(f"motori DISCORDI (ML={ml[0]}, Poisson={po[0]}) → bot neutro",),
        )

    direction = ml[0]
    p_avg = (ml[1] + po[1]) / 2.0

    # regola 3: edge moderato vs mercato (se le quote sono disponibili)
    p_mkt = None
    edge = None
    if market_mid_probs:
        p_mkt = market_mid_probs.get(direction)
        if p_mkt and p_mkt > 0:
            edge = p_avg / p_mkt - 1.0
            if edge < min_edge:
                return BiasDecision(
                    consensus=True, direction=direction, prob_ml=ml[1],
                    prob_poisson=po[1], prob_market=p_mkt, edge=edge,
                    reasons=(f"edge {edge:+.1%} sotto il minimo {min_edge:.0%} → bot neutro",),
                )
            if edge > max_edge:
                return BiasDecision(
                    consensus=True, direction=direction, prob_ml=ml[1],
                    prob_poisson=po[1], prob_market=p_mkt, edge=edge,
                    reasons=(f"edge {edge:+.1%} SOSPETTO (> {max_edge:.0%}): "
                             "probabile errore modello → bot neutro",),
                )
    else:
        reasons.append("quote di mercato non disponibili: edge non verificato → bias prudente NON attivato")
        return BiasDecision(
            consensus=True, direction=direction, prob_ml=ml[1], prob_poisson=po[1],
            reasons=tuple(reasons),
        )

    roles = match_runner_roles(runner_names, home_name, away_name)
    if roles is None:
        return BiasDecision(
            consensus=True, direction=direction, prob_ml=ml[1], prob_poisson=po[1],
            prob_market=p_mkt, edge=edge,
            reasons=("mapping runner per NOME fallito → bot neutro (sicurezza)",),
        )

    bias = {}
    for role, sid in roles.items():
        bias[sid] = "BACK" if role == direction else "LAY"
    return BiasDecision(
        bias=bias, consensus=True, direction=direction, prob_ml=ml[1],
        prob_poisson=po[1], prob_market=p_mkt, edge=edge,
        reasons=(f"consenso {direction} (ML {ml[1]:.0%} / Poisson {po[1]:.0%}) "
                 f"vs mercato {p_mkt:.0%}, edge {edge:+.1%} in banda → bias attivo",),
    )
