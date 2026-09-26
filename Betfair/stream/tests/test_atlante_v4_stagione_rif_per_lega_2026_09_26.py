"""O-4 (test e2e del 26/09/2026): ``stagione_rif`` del blocco v4 PER LEGA.

Reperto: ``genera_atlante.assembla_blocco_v4`` usava UN riferimento per tutto
l'atlante (max + 1 fra tutte le leghe): 3 leghe con una stagione 2027 portavano
il riferimento a 2028 per tutte, e i pesi per eta' (emivita 3) delle altre si
spostavano rispetto al validato (addestra <= S, riferimento S + 1, per lega).
Ora ogni lega ha S + 1 della SUA ultima stagione; emivita/BETA/ETA invariati.

Stati v4 finti con la forma vera (``atlante_v4._blocco_stagione``: n_fixtures,
gol, celle NT*NG*3, rec2 NG*2, durate).
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from Betfair.stream.scalper import atlante_v4 as V4
from Betfair.stream.scalper import genera_atlante as G

N_CELLA = 100.0


def _blocco(n_fixtures: int, gol: int) -> Dict[str, Any]:
    b = V4._blocco_stagione()
    b["n_fixtures"] = n_fixtures
    b["gol"] = gol
    b["celle"] = [N_CELLA, 10.0, 12.0] * (V4.NT * V4.NG)
    b["rec2"] = [50.0, 1.0] * V4.NG
    return b


def _stato(lid: int, anni: List[int]) -> Dict[str, Any]:
    st = V4.stato_lega_v4_vuoto(lid, f"Lega {lid}")
    st["stagioni"] = {str(a): _blocco(300, 800) for a in anni}
    return {"league_name": f"Lega {lid}", "v4": st}


def _n_atteso(anni: List[int], rif: int) -> float:
    return N_CELLA * sum(0.5 ** ((rif - a) / V4.EMIVITA) for a in anni)


def test_riferimento_per_lega_con_calendari_diversi():
    anni_a = [2023, 2024, 2025]        # calendario europeo: ultima 2025 -> rif 2026
    anni_b = [2025, 2026, 2027]        # lega con gia' una stagione 2027 -> rif 2028
    blocco = G.assembla_blocco_v4({"501": _stato(501, anni_a), "36": _stato(36, anni_b)},
                                  generated_at="2026-09-26T12:00:00+00:00")
    assert blocco["meta"]["stagione_rif_per_lega"] == {"36": 2028, "501": 2026}
    assert blocco["meta"]["stagione_rif"] == 2028          # compatibilita': la piu' recente
    assert blocco["meta"]["emivita"] == V4.EMIVITA == 3.0   # pesi invariati
    n_a = blocco["by_league"]["501"]["n"][0][0]
    n_b = blocco["by_league"]["36"]["n"][0][0]
    assert n_a == pytest.approx(_n_atteso(anni_a, 2026), abs=0.05)     # 192.4 (era 121.2 con 2028)
    assert n_b == pytest.approx(_n_atteso(anni_b, 2028), abs=0.05)
    assert n_a == pytest.approx(n_b, abs=0.05)                          # stessa eta' relativa, stesso peso


def test_una_lega_non_sposta_i_pesi_di_un_altra():
    sola = G.assembla_blocco_v4({"501": _stato(501, [2023, 2024, 2025])}, generated_at="g")
    insieme = G.assembla_blocco_v4({"501": _stato(501, [2023, 2024, 2025]),
                                    "36": _stato(36, [2025, 2026, 2027])}, generated_at="g")
    assert sola["by_league"]["501"]["n"] == insieme["by_league"]["501"]["n"]
    assert sola["meta"]["stagione_rif_per_lega"]["501"] == insieme["meta"]["stagione_rif_per_lega"]["501"] == 2026


def test_intero_come_prima():
    stati = {"501": _stato(501, [2024, 2025])["v4"], "36": _stato(36, [2026, 2027])["v4"]}
    b = V4.assembla_v4(stati, generated_at="g", stagione_rif=2028)
    assert b["meta"]["stagione_rif"] == 2028
    assert b["meta"]["stagione_rif_per_lega"] == {"36": 2028, "501": 2028}
    assert b["by_league"]["501"]["n"][0][0] == pytest.approx(_n_atteso([2024, 2025], 2028), abs=0.05)
