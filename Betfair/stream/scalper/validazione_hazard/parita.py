"""parita.py - controllo di PARITA' di A0 col v3 committato.

Il v3 (24/09, 21 leghe, 2016-2025/26) e' stato fatto dal generatore sul DB vero.
A0 del banco rifa' lo stesso generatore sulla cache. Sulle leghe comuni con le
stesse stagioni (tutte tranne la 71, che nel v3 ha anche il 2026) devono
coincidere ESATTAMENTE le grandezze grezze: n_fixtures, n_goals, n per cella,
side_rate per bucket; i successi s3/s2 per cella si ricostruiscono dal v3
invertendo lo shrinkage (s = p*(n+K) - K*p_globale_v3) e devono tornare interi
entro l'arrotondamento a 5 decimali (|errore| <= (n+K)*5e-6 + K*5e-6).
"""
from __future__ import annotations

from typing import Any, Dict, List

from Betfair.stream.scalper.genera_atlante import BUCKETS, GOAL_KEYS, K_LEAGUE


def confronta_v3(v3: Dict[str, Any], stati: Dict[str, Dict[str, Any]], leghe: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"leghe": {}, "celle_confrontate": 0, "n_diversi": 0,
                           "s3_fuori_tolleranza": 0, "s2_fuori_tolleranza": 0,
                           "side_rate_diversi": 0, "max_err_s3": 0.0, "max_err_s2": 0.0}
    for lid in leghe:
        blk = (v3.get("by_league") or {}).get(lid)
        st = stati.get(lid)
        if not blk or not st:
            out["leghe"][lid] = "assente"
            continue
        meta = blk["meta"]
        riga = {"n_fixtures_v3": meta["n_fixtures"], "n_fixtures_banco": st["n_fixtures"],
                "n_goals_v3": meta["n_goals"], "n_goals_banco": st["n_goals"]}
        nf = st["n_fixtures"]
        for b in BUCKETS:
            sr = round(st["side_goals"][b] / (2.0 * nf), 5) if nf else None
            if sr != meta["side_rate_per_bucket"].get(b):
                out["side_rate_diversi"] += 1
            for k in GOAL_KEYS:
                cv = blk["grid"][b][k]
                n, s3, s2 = st["cells"][b][k]
                out["celle_confrontate"] += 1
                if cv.get("n") != n:
                    out["n_diversi"] += 1
                    continue
                g = v3["global"][b][k]
                if cv.get("p_goal_next_3min") is None or g.get("p_goal_next_3min") is None:
                    continue
                tol = (n + K_LEAGUE) * 5e-6 + K_LEAGUE * 5e-6 + 1e-9
                s3_v3 = cv["p_goal_next_3min"] * (n + K_LEAGUE) - K_LEAGUE * g["p_goal_next_3min"]
                s2_v3 = cv["p_goal_next_2min"] * (n + K_LEAGUE) - K_LEAGUE * g["p_goal_next_2min"]
                e3, e2 = abs(s3_v3 - s3), abs(s2_v3 - s2)
                out["max_err_s3"] = max(out["max_err_s3"], e3)
                out["max_err_s2"] = max(out["max_err_s2"], e2)
                if e3 > tol:
                    out["s3_fuori_tolleranza"] += 1
                if e2 > tol:
                    out["s2_fuori_tolleranza"] += 1
        out["leghe"][lid] = riga
    return out
