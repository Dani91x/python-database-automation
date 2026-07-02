"""Test del CONNETTORE motori → bias (logica pura, nessuna rete).

Le regole certificate il 02/07 (dossier §9.8): consenso ML+Poisson,
dominio, edge moderato, mapping runner PER NOME (mai sortPriority).
"""
from __future__ import annotations

import pytest

from Betfair.stream.scalper.bias_resolver import (
    BiasDecision,
    match_runner_roles,
    resolve_bias,
)


def _pred(ml_1x2=None, po_1x2=None, league_id=365):
    row = {"league_id": league_id}
    if ml_1x2 is not None:
        row["model_predictions_json"] = {"targets": {"target_1x2": ml_1x2}}
    if po_1x2 is not None:
        row["db_json_analisi"] = {"markets": {"1x2": po_1x2}}
    return row


NAMES = {30: "Norway", 75104: "Ivory Coast", 58805: "The Draw"}
HOME, AWAY = "Ivory Coast", "Norway"
MKT = {"H": 0.50, "D": 0.28, "A": 0.24}  # prob implicite mid (fittizie)


def test_consenso_attiva_il_bias_back_sulla_direzione():
    d = resolve_bias(
        _pred(ml_1x2={"H": 0.55, "D": 0.25, "A": 0.20},
              po_1x2={"H": 0.57, "D": 0.23, "A": 0.20}),
        NAMES, HOME, AWAY, MKT,
    )
    assert d.consensus and d.direction == "H"
    # BACK sulla casa (Ivory Coast = 75104), LAY sulle altre due
    assert d.bias[75104] == "BACK"
    assert d.bias[30] == "LAY"
    assert d.bias[58805] == "LAY"
    assert d.edge == pytest.approx((0.56 / 0.50) - 1.0, abs=1e-9)


def test_motori_discordi_nessun_bias():
    d = resolve_bias(
        _pred(ml_1x2={"H": 0.48, "D": 0.22, "A": 0.30},
              po_1x2={"H": 0.30, "D": 0.29, "A": 0.41}),
        NAMES, HOME, AWAY, MKT,
    )
    assert not d.consensus and d.bias == {}


def test_manca_poisson_nessun_bias():
    # es. amichevole femminile: solo ML → consenso impossibile (regola dominio)
    d = resolve_bias(
        _pred(ml_1x2={"H": 0.52, "D": 0.23, "A": 0.25}, po_1x2=None),
        NAMES, HOME, AWAY, MKT,
    )
    assert d.bias == {} and not d.consensus


def test_edge_enorme_e_sospetto_nessun_bias():
    # consenso H al 75% contro mercato al 50% = edge 50% → errore modello
    d = resolve_bias(
        _pred(ml_1x2={"H": 0.75, "D": 0.15, "A": 0.10},
              po_1x2={"H": 0.75, "D": 0.15, "A": 0.10}),
        NAMES, HOME, AWAY, MKT,
    )
    assert d.consensus and d.bias == {}
    assert any("SOSPETTO" in r for r in d.reasons)


def test_edge_sotto_il_minimo_nessun_bias():
    d = resolve_bias(
        _pred(ml_1x2={"H": 0.50, "D": 0.26, "A": 0.24},
              po_1x2={"H": 0.505, "D": 0.26, "A": 0.235}),
        NAMES, HOME, AWAY, MKT,
    )
    assert d.consensus and d.bias == {}


def test_senza_quote_di_mercato_bias_prudente_spento():
    d = resolve_bias(
        _pred(ml_1x2={"H": 0.55, "D": 0.25, "A": 0.20},
              po_1x2={"H": 0.57, "D": 0.23, "A": 0.20}),
        NAMES, HOME, AWAY, None,
    )
    assert d.consensus and d.bias == {}


def test_mapping_per_nome_con_ordine_betfair_invertito():
    # caso reale 35764745: Betfair listava Norway per prima. Il mapping per
    # NOME deve restare corretto qualunque sia l'ordine.
    roles = match_runner_roles(NAMES, HOME, AWAY)
    assert roles == {"H": 75104, "A": 30, "D": 58805}


def test_mapping_fallito_significa_niente_bias():
    d = resolve_bias(
        _pred(ml_1x2={"H": 0.55, "D": 0.25, "A": 0.20},
              po_1x2={"H": 0.57, "D": 0.23, "A": 0.20}),
        {1: "Squadra Misteriosa", 2: "Altra", 3: "The Draw"},
        HOME, AWAY, MKT,
    )
    assert d.bias == {}
    assert any("mapping" in r for r in d.reasons)


def test_probabilita_invalide_nessun_bias():
    d = resolve_bias(
        _pred(ml_1x2={"H": 5.0, "D": 3.0, "A": 2.0},   # quote, non prob
              po_1x2={"H": 0.5, "D": 0.3, "A": 0.2}),
        NAMES, HOME, AWAY, MKT,
    )
    assert d.bias == {}


def test_lega_esclusa():
    d = resolve_bias(
        _pred(ml_1x2={"H": 0.55, "D": 0.25, "A": 0.20},
              po_1x2={"H": 0.57, "D": 0.23, "A": 0.20}, league_id=667),
        NAMES, HOME, AWAY, MKT, excluded_league_ids={667},
    )
    assert d.bias == {}


def test_decision_to_meta_serializzabile():
    import json
    d = BiasDecision(bias={30: "LAY"}, consensus=True, direction="H",
                     reasons=("ok",))
    json.dumps(d.to_meta())
