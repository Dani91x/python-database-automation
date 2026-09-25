"""Note dell'atlante con LIVELLO e CONFIDENZA (25/09/2026, atlante a domanda).

Safe e Mike ricevono dall'atlante lo stesso numero di prima; in piu' la nota
dice da che livello viene (squadra+lega / lega / globale), su quante
partite-minuto e con che confidenza, e una lega che l'atlante sta
calcolando ora si dichiara "in preparazione" (non "non coperta"). Soglie
``hazard_warn``/``hazard_drop`` e decisioni INVARIATE.

I finti hanno le chiavi del vero (``hazard_atlas_v2.json`` + i campi nuovi
che ``genera_atlante.assembla`` scrive: meta.affidabile, meta.confidenza,
cella.conf, meta.leghe_in_preparazione).
"""
from __future__ import annotations

from typing import Any, Dict

from Betfair.safe_strategy.opportunity import OpportunityModel, resolve_lambdas
from Betfair.safe_strategy.tests.test_opportunity import payload_1_1_65

LEGA = 39


def _lam(p: dict):
    got = resolve_lambdas(p, fixture=None)
    return (got[0], got[1])


def _pm(p: dict) -> float:
    from Betfair.stream.engine.live_engine_pro import event_goal_hazard
    lam = _lam(p)
    return float(event_goal_hazard(score_home=p["score_home"], score_away=p["score_away"],
                                   minute=p["minute"], prematch_lambda_home=lam[0],
                                   prematch_lambda_away=lam[1], league_id=LEGA,
                                   horizon_min=3.0)["p_next"])


def _atlante(p: float, *, n: int = 800, preparazione=()) -> Dict[str, Any]:
    cella = {"p_goal_next_3min": round(p, 6), "p_goal_next_2min": round(p * 0.66, 6), "n": n,
             "conf": "media"}
    return {"meta": {"name": "hazard_atlas_v3", "generated_at": "2026-09-25T02:00:00+00:00",
                     "n_fixtures_used": 61234, "min_fixtures_league": 300,
                     "shrinkage": {"K_league_fixture_minutes": 1500.0},
                     "leghe_in_preparazione": list(preparazione)},
            "global": {"65-70": {"2": dict(cella, n=90000, conf="alta")}},
            "by_league": {str(LEGA): {"meta": {"league_name": "Premier League", "n_fixtures": 3800,
                                               "affidabile": True, "confidenza": "alta",
                                               "side_rate_per_bucket": {"65-70": 0.07}},
                                      "grid": {"65-70": {"2": cella}}}},
            "by_team": {}, "h2h_hint": {}}


def test_nota_safe_dice_livello_n_e_confidenza_senza_cambiare_la_decisione():
    p = payload_1_1_65()
    pm = _pm(p)
    hz = OpportunityModel(atlas=_atlante(pm * 1.10))._hazard_check(
        p, lambdas=_lam(p), league_id=LEGA, minute=65)
    assert hz["source"] == "league" and hz["penalty"] == 1.0 and hz["drop"] is False
    assert hz["livello"] == "lega" and hz["n"] == 800 and hz["confidenza"] == "media"
    assert "[league] (lega, n=800, confidenza media)" in hz["note"]
    assert hz["note"].startswith("hazard coerente con l'atlante (verificato: modello")
    # oltre drop: stessa decisione di prima, la nota porta il dettaglio
    hz = OpportunityModel(atlas=_atlante(pm * 3.0))._hazard_check(
        p, lambdas=_lam(p), league_id=LEGA, minute=65)
    assert hz["drop"] is True and hz["penalty"] == 0.0
    assert "(lega, n=800, confidenza media)" in hz["note"]


def test_lega_in_preparazione_dichiarata_e_confronto_sul_globale():
    p = payload_1_1_65()
    pm = _pm(p)
    atl = _atlante(pm * 5, preparazione=[4321])
    atl["global"]["65-70"]["2"]["p_goal_next_3min"] = round(pm, 6)
    hz = OpportunityModel(atlas=atl)._hazard_check(p, lambdas=_lam(p), league_id=4321, minute=65)
    assert hz["source"] == "global" and hz["livello"] == "globale"
    assert hz["note"].startswith("atlante: lega 4321 in preparazione, confronto con lo storico globale")
    # una lega che NON e' in preparazione e non c'e': la nota di prima
    hz = OpportunityModel(atlas=atl)._hazard_check(p, lambdas=_lam(p), league_id=999, minute=65)
    assert hz["note"].startswith("atlante: lega non coperta (999)")


def test_mike_live_frame_porta_livello_confidenza_e_nota():
    from Betfair.mike import dossier as D
    atl = _atlante(0.12)
    out = D.live_frame({"league_id": LEGA}, minute=66, score_home=1, score_away=1, atlas=atl)
    assert out["hazard_atlas"] == 0.12 and out["hazard_source"] == "league"
    assert out["hazard_livello"] == "lega" and out["hazard_n"] == 800
    assert out["hazard_confidenza"] == "media"
    assert out["hazard_nota"].startswith("storico Premier League (lega, 3800 partite)")
