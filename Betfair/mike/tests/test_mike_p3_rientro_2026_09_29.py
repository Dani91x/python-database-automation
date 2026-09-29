"""29/09/2026 - MIKE, PACCHETTO P3: IL RIENTRO SULL'UNDER 4,5 CON 1 O 2 GOL.

Specifica: ``PIANO_MODIFICHE_MIKE_2026-09-29.md`` punto 6 (decisione 20
dell'utente, M6.1): «il numero di gol NON ESATTAMENTE 1, ma 1-2 gol, il resto
delle condizioni resta invariato». ``reentry_max_goals``: valore di serie 2,
limite massimo 2; il minimo di 1 gol e' nel codice e resta.

Finti: classi VERE del motore, parametri da ``config.merge_params``,
``engine.decide``. File ASCII-only.
"""
from __future__ import annotations

import pytest

from Betfair.mike import certificazione as CERT
from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike.tests.test_mike_engine import KO, book, params, snap


def _flat_in_profitto():
    return E.MatchCtx(state="FLAT", entry_price_initial=1.50, reentry_allowed=True)


def _s(goals, minute=30, u45=1.70):
    return snap(KO + minute * 60, u35=book(2.5, inplay=True), o45=book(5.0, inplay=True),
                u45=book(u45, bs=50, inplay=True), inplay=True, minute=minute, goals=goals)


def test_m6_1_parametro_di_serie_2_e_limite_2():
    assert C.PARAM_SPEC["reentry_max_goals"] == (2, int, 0, 2, None)
    assert C.merge_params(None)["reentry_max_goals"] == 2
    assert C.merge_params({"reentry_max_goals": 1})["reentry_max_goals"] == 1
    assert C.merge_params({"reentry_max_goals": 9})["reentry_max_goals"] == 2


@pytest.mark.parametrize("goals,entra", [(0, False), (1, True), (2, True), (3, False)])
def test_m6_1_rientro_con_1_o_2_gol(goals, entra):
    for automatiche in (True, False):
        ctx = _flat_in_profitto()
        d = E.decide(ctx, _s(goals), params(uscite_automatiche=automatiche))
        posti = [(a.role, a.market, a.selection, a.side, a.price, a.size)
                 for a in d.actions if a.kind == "place"]
        if entra:
            assert d.state == "REENTRY_PENDING"
            assert posti == [("reentry", E.MARKET_OU45, E.SEL_UNDER, "back", 1.70, 10.0)]
        else:
            assert d.state == "FLAT" and posti == [] and "fuori range" in d.reason


def test_m6_1_le_altre_condizioni_restano_con_2_gol():
    p = params()
    # oltre il 45'
    assert E.decide(_flat_in_profitto(), _s(2, minute=50), p).actions == []
    # quota Under 4,5 non sopra la quota del primo ingresso
    assert E.decide(_flat_in_profitto(), _s(2, u45=1.45), p).actions == []
    # solo dopo una chiusura in profitto
    ctx = _flat_in_profitto()
    ctx.reentry_allowed = False
    assert E.decide(ctx, _s(2), p).actions == []
    # una volta sola
    ctx = _flat_in_profitto()
    ctx.reentry_done = True
    assert E.decide(ctx, _s(2), p).actions == []
    # mai dopo una chiusura dell'utente
    ctx = _flat_in_profitto()
    ctx.no_reentry = True
    assert E.decide(ctx, _s(2), p).actions == []


def test_m6_1_col_valore_1_salvato_resta_esattamente_1_gol():
    """Il valore salvato nel database vince sul valore di serie: con 1 si
    rientra solo con 1 gol (migrazione `mike_reentry_max_goals_2026-09-29.sql`)."""
    p = params(reentry_max_goals=1)
    assert E.decide(_flat_in_profitto(), _s(2), p).actions == []
    assert E.decide(_flat_in_profitto(), _s(1), p).state == "REENTRY_PENDING"


def _codici(ctx, s, d, p):
    return [v.codice for v in CERT.verifica(ctx, s, d, p)]


def test_banco_h2_ammette_1_o_2_gol_e_vede_il_3():
    p = params()
    ctx = _flat_in_profitto()
    for g in (1, 2):
        s = _s(g)
        d = E.decide(ctx, s, p)
        assert "H2" not in _codici(ctx, s, d, p)
    s3 = _s(3)
    finta = E.Decision("REENTRY_PENDING", [E._place("reentry", E.MARKET_OU45, E.SEL_UNDER,
                                                    "back", 1.70, 10.0)], "re-ingresso")
    assert "H2" in _codici(ctx, s3, finta, p)
    s0 = _s(0)
    assert "H2" in _codici(ctx, s0, finta, p)
