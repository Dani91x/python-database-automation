"""29/09/2026 - MIKE, PACCHETTO P2-BIS.

A. Test mancanti trovati dalle mutazioni del coordinatore sul P2 (Z1, Z3, Z12,
   Z16, C3): il codice e' giusto, questi test lo inchiodano.
B. Punteggio ASSENTE (piano Mike, punto 8, M8.4: «i punteggi ci sono e Mike deve
   saperli sempre»; regola permanente: se i dati non sono vivi Mike non opera).
   In gioco con ``goals=None``: il cash out intelligente non scatta, la
   copertura ASPETTA (motivo «punteggio assente»), nessuna seconda puntata.

Finti: classi VERE del motore (``MatchCtx``/``Leg``/``Snapshot``/``Book``),
parametri da ``config.merge_params``, ``engine.decide``. File ASCII-only.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from Betfair.mike import certificazione as CERT
from Betfair.mike import engine as E
from Betfair.mike.tests.test_mike_engine import (KO, _live_covered, _live_uncovered, book,
                                                 fill, params, snap)
from Betfair.mike.tests.test_mike_p2_prepartita_2026_09_29 import (
    _al_segno, _aperta, _banca, _fischio, _p, _piatto_prima_del_segno, _posti)


def _codici(ctx, s, d, p):
    return [v.codice for v in CERT.verifica(ctx, s, d, p)]


# ===========================================================================
# A. test mancanti
# ===========================================================================
@pytest.mark.parametrize("stato_banca", ["pending", E.STATUS_RECONCILE])
def test_z1_al_fischio_conti_piatti_ma_banca_in_volo_non_si_chiude_il_giro(stato_banca):
    """Z1: esposizione gia' piatta (banca abbinata per intero) ma la banca e'
    ancora VIVA o a esito IGNOTO per Mike: non si dichiara il giro chiuso."""
    ctx, p = _al_segno()
    g = _banca(ctx)
    g.matched, g.avg_price, g.status = g.size, g.price, stato_banca
    w, l = E.exposure(ctx.legs, E.MARKET_OU35, E.SEL_UNDER)
    assert abs(w - l) < 0.01, "precondizione: conti piatti"
    d = E.decide(ctx, _fischio(), p)
    assert d.state != "IDLE_LIVE" and "cycle_no" not in d.updates
    assert _posti(d) == []


def test_z3_pre_partita_spento_dopo_il_segno_resta_watch():
    ctx, p = _piatto_prima_del_segno()
    p["pre_enabled"] = False
    d = E.decide(ctx, snap(KO - 9 * 60, u35=book(1.50)), p)
    assert d.state == "WATCH" and d.actions == []


def _ko_con_banca_ignota():
    ctx, p = _al_segno()
    E.apply_decision(ctx, E.decide(ctx, _fischio(), p), KO + 30)
    assert ctx.state == "LIVE_KO_GREEN"
    _banca(ctx).status = E.STATUS_RECONCILE           # annullo dall'esito ignoto
    return ctx, p


def test_z12_banca_a_esito_ignoto_al_fischio_nessuna_decisione_del_gioco():
    ctx, p = _ko_con_banca_ignota()
    d = E.decide(ctx, _fischio(KO + 40), p)
    assert d.state == "LIVE_KO_GREEN" and _posti(d) == []
    # gol precoce: nessuna seconda puntata finche' la banca non e' letta
    d2 = E.decide(ctx, _fischio(KO + 60, goals=1), p)
    assert d2.state == "LIVE_KO_GREEN" and _posti(d2) == []
    # finestra scaduta: nessuna copertura finche' la banca non e' letta
    d3 = E.decide(ctx, _fischio(KO + 30 + float(p["ko_green_window_s"]) + 5), p)
    assert d3.state == "LIVE_KO_GREEN" and _posti(d3) == []


def test_z16_veto_gia_scattato_niente_ultimo_ingresso_anche_se_ora_passerebbe():
    ctx, p = _piatto_prima_del_segno(_p(veto_p_under35_cal=True))
    ctx.veto_u35 = {"punto": "persist", "esito": "veto", "p_under35_cal": 0.40}
    s = replace(snap(KO - 9 * 60, u35=book(1.50)), p_under35_cal=0.95)
    d = E.decide(ctx, s, p)
    assert d.state == "HOLD" and _posti(d) == []
    assert "veto" in d.reason


def test_c3_banco_b6_segnala_un_ingresso_dopo_il_segno_non_da_watch():
    ctx, p = _aperta()                                  # gambe nate PRIMA del segno
    s = snap(KO - 9 * 60, u35=book(1.50))
    ingresso = E.Decision("PRE_ENTRY_PENDING", [E._place("under_entry", E.MARKET_OU35,
                                                         E.SEL_UNDER, "back", 1.50, 20.0)],
                          "ingresso")
    for stato in ("PRE_OPEN", "HOLD"):
        ctx.state = stato
        assert "B6" in _codici(ctx, s, ingresso, p), stato
    ctx.state = "WATCH"
    assert "B6" not in _codici(ctx, s, ingresso, p)


# ===========================================================================
# B. punteggio assente
# ===========================================================================
def test_b_cash_out_intelligente_non_scatta_senza_punteggio():
    ctx, p = _live_covered()
    # punteggio caldo (3 gol) chiude; stessi prezzi SENZA punteggio: niente
    caldo = snap(KO + 30 * 60, u35=book(1.41, bl=1.42, inplay=True),
                 o45=book(8.8, bl=9.0, inplay=True), inplay=True, minute=30, goals=3, hazard=0.02)
    assert E.decide(ctx, caldo, p).state == "LIVE_CLOSING"
    muto = replace(caldo, goals=None)
    d = E.decide(ctx, muto, p)
    assert d.state == "LIVE_COVERED" and _posti(d) == []
    assert d.telemetry["cashout"]["smart"]["punteggio_assente"] is True


@pytest.mark.usefixtures("forma_di_prima")
@pytest.mark.parametrize("forzata", [False, True])
def test_b_copertura_aspetta_senza_punteggio(forzata):
    ctx, p = _live_uncovered()
    ctx.cover_forced = forzata
    s = snap(KO + 20 * 60, u35=book(1.35, inplay=True), o45=book(9.0, bs=50, inplay=True),
             inplay=True, minute=20, goals=None, hazard=0.05, p4_market=0.12)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_UNCOVERED" and _posti(d) == []
    assert "punteggio assente" in d.reason
    # col punteggio si copre (stessa situazione)
    d2 = E.decide(ctx, replace(s, goals=0), p)
    assert d2.state == "LIVE_COVER_PENDING"


def test_b_cover_timing_con_punteggio_assente_aspetta():
    p = params()
    assert E.cover_timing(goals=None, minute=20, hazard=0.5, p4_market=0.5, last_goal_ts=None,
                          now=KO, params=dict(p, cover_policy="immediate")) == "wait"


def test_b_nessuna_seconda_puntata_senza_punteggio():
    ctx, p = _al_segno()
    _banca(ctx).status = "cancelled"
    E.apply_decision(ctx, E.decide(ctx, _fischio(), p), KO + 30)
    d = E.decide(ctx, _fischio(KO + 60, goals=None), p)
    assert d.state == "LIVE_KO_GREEN"
    assert all(r != "under_second" for r, *_ in _posti(d))
