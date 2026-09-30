"""29/09/2026 - MIKE, PACCHETTO P2: IL PRE-PARTITA.

Specifica: ``PIANO_MODIFICHE_MIKE_2026-09-29.md`` punto 2 (decisioni 2, 3, 4, 5,
6, 7 dell'utente; modifiche M2.1-M2.4).

  * M2.1: a 10 minuti dal fischio la banca di green NON si ritira e NON si
    sostituisce con una chiusura al mercato: resta appoggiata a 2 tick sotto
    fino al fischio (LAPSE: la parte non abbinata la cancella Betfair).
  * M2.2: nel pre-partita nessuna chiusura in perdita, mai: il veto sull'Under
    3,5 non chiude piu' la posizione (blocca ancora l'ultimo ingresso).
  * M2.4: l'ULTIMO INGRESSO, valutato UNA volta al segno dei 10 minuti: Mike
    piatto -> entra (tutti i controlli d'ingresso di oggi) e appoggia subito la
    banca; Mike con posizione -> nessun altro ingresso, la banca resta. Dopo il
    segno nessun giro nuovo: se la banca si abbina Mike resta piatto.
  * M2.3: al fischio Mike LEGGE cosa resta della banca (abbinata per intero =
    piatto col profitto del giro; in parte o per niente = posizione vera
    residua da cui riparte il flusso del gioco).

Finti: classi VERE del motore (``MatchCtx``/``Leg``/``Snapshot``/``Book``),
parametri da ``config.merge_params``, test da ``engine.decide`` a interruttore
MANUALE (il default di produzione). File ASCII-only.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from Betfair.mike import engine as E
from Betfair.mike.tests.test_mike_engine import (DENTRO_FINESTRA, KO, book, conferma_annulli,
                                                 fill, params, snap)

ULTIMO = KO - 10 * 60            # il segno dei 10 minuti (pre_last_entry_min di serie)


def _p(**over):
    return params(uscite_automatiche=False, stake=20.0, **over)


def _posti(d):
    return [(a.role, a.side, a.price, a.size, a.persistence) for a in d.actions
            if a.kind == "place"]


def _annulli(d):
    return [a.role for a in d.actions if a.kind == "cancel"]


def _aperta(p=None, prezzo=1.50):
    """Ingresso 20 @ prezzo abbinato e banca a 2 tick sotto appoggiata."""
    p = p or _p()
    ctx = E.MatchCtx()
    s0 = snap(DENTRO_FINESTRA, u35=book(prezzo))
    E.apply_decision(ctx, E.decide(ctx, s0, p), s0.now)
    fill(ctx.legs[0])
    s1 = snap(DENTRO_FINESTRA + 5, u35=book(prezzo))
    d1 = E.decide(ctx, s1, p)
    E.apply_decision(ctx, d1, s1.now)
    assert ctx.state == "PRE_OPEN" and ctx.legs[-1].role == "under_green"
    assert ctx.legs[-1].status == "pending"
    return ctx, p


def _banca(ctx):
    return [l for l in ctx.legs if l.role == "under_green"][-1]


# ===========================================================================
# M2.1 / M2.2: al segno la banca resta, niente chiusura al mercato
# ===========================================================================
@pytest.mark.parametrize("bb,bl", [(1.44, 1.45),     # in profitto
                                   (1.54, 1.55)])    # in perdita
def test_m2_1_al_segno_la_banca_resta_e_niente_chiusura(bb, bl):
    ctx, p = _aperta()
    d = E.decide(ctx, snap(KO - 9 * 60, u35=book(bb, bl=bl)), p)
    assert _annulli(d) == [], "la banca appoggiata non si ritira a 10 minuti dal fischio"
    assert _posti(d) == [], "niente chiusura al mercato"
    assert d.state == "HOLD"
    assert not isinstance(d.updates.get("uscita_proposta"), dict)


def test_m2_2_il_veto_non_chiude_piu_in_perdita():
    ctx, p = _aperta(_p(veto_p_under35_cal=True))
    s = replace(snap(KO - 9 * 60, u35=book(1.50, bl=1.52)), p_under35_cal=0.10)
    for _ in range(3):
        d = E.decide(ctx, s, p)
        assert _posti(d) == [] and _annulli(d) == []
        assert "veto_u35" not in d.updates
        assert not isinstance(d.updates.get("uscita_proposta"), dict)
        E.apply_decision(ctx, d, s.now)
    assert ctx.state == "HOLD" and _banca(ctx).is_live


def test_m2_1_dopo_il_segno_la_banca_si_tiene_e_si_rimette_se_manca():
    ctx, p = _aperta()
    s = snap(KO - 9 * 60, u35=book(1.54, bl=1.55))
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    assert ctx.state == "HOLD"
    d = E.decide(ctx, snap(KO - 8 * 60, u35=book(1.54, bl=1.55)), p)
    assert d.actions == [] and d.state == "HOLD"
    # la banca e' sparita (rifiuto, annullo esterno): si rimette a 2 tick sotto
    _banca(ctx).status = "cancelled"
    d2 = E.decide(ctx, snap(KO - 7 * 60, u35=book(1.54, bl=1.55)), p)
    assert _posti(d2) == [("under_green", "lay", pytest.approx(1.48),
                           pytest.approx(20.27, abs=0.01), "LAPSE")]
    assert d2.state == "HOLD"


def test_m2_4_banca_abbinata_negli_ultimi_minuti_piatto_e_nessun_rientro():
    ctx, p = _aperta()
    s = snap(KO - 9 * 60, u35=book(1.54, bl=1.55))
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    fill(_banca(ctx))
    d = E.decide(ctx, snap(KO - 5 * 60, u35=book(1.47, bl=1.48)), p)
    assert d.state == "HOLD" and d.updates["cycle_no"] == 1
    assert d.telemetry["pre_cycle"]["locked"] == pytest.approx(0.27, abs=0.02)
    E.apply_decision(ctx, d, KO - 5 * 60)
    for t in (KO - 4 * 60, KO - 2 * 60, KO - 30):
        d = E.decide(ctx, snap(t, u35=book(1.50)), p)
        assert d.actions == [] and d.state == "HOLD", "nessun giro nuovo dopo il segno"
    d = E.decide(ctx, snap(KO + 30, u35=book(1.50, inplay=True), inplay=True, minute=0,
                           goals=0), p)
    assert d.state == "IDLE_LIVE" and d.actions == []


# ===========================================================================
# M2.4: l'ultimo ingresso
# ===========================================================================
def _piatto_prima_del_segno(p=None):
    """Un giro chiuso (banca abbinata) ben prima del segno: Mike e' piatto."""
    ctx, p = _aperta(p)
    fill(_banca(ctx))
    s = snap(ULTIMO - 5 * 60, u35=book(1.47))
    d = E.decide(ctx, s, p)
    assert d.state == "WATCH"
    E.apply_decision(ctx, d, s.now)
    return ctx, p


def test_m2_4_piatto_al_segno_entra_e_appoggia_subito_la_banca():
    ctx, p = _piatto_prima_del_segno()
    s = snap(KO - 9 * 60, u35=book(1.50))
    d = E.decide(ctx, s, p)
    assert d.state == "PRE_ENTRY_PENDING"
    assert _posti(d) == [("under_entry", "back", 1.50, 20.0, "LAPSE")]
    E.apply_decision(ctx, d, s.now)
    fill(ctx.legs[-1])
    d2 = E.decide(ctx, snap(s.now + 2, u35=book(1.50)), p)
    assert _posti(d2) == [("under_green", "lay", pytest.approx(1.48),
                           pytest.approx(20.27, abs=0.01), "LAPSE")]
    E.apply_decision(ctx, d2, s.now + 2)
    # e da li' la banca resta fino al fischio, nessun altro ingresso
    d3 = E.decide(ctx, snap(s.now + 10, u35=book(1.44, bl=1.45)), p)
    assert d3.state == "HOLD" and d3.actions == []


def test_m2_4_ultimo_ingresso_passa_dai_controlli_d_ingresso():
    ctx, p = _piatto_prima_del_segno()
    d = E.decide(ctx, snap(KO - 9 * 60, u35=book(1.50, bl=1.60)), p)     # spread 10 tick
    assert _posti(d) == [] and "spread" in d.reason
    # 30/09 (decisione dell'utente, "riprova fino al fischio"): un controllo
    # momentaneo che non passa e' ATTESA, non rinuncia; si riprova al giro dopo
    # (prima: HOLD fino al fischio). Test dedicato:
    # test_mike_ultimo_ingresso_2026_09_30.py
    assert d.state == "WATCH"
    E.apply_decision(ctx, d, KO - 9 * 60)
    d2 = E.decide(ctx, snap(KO - 8 * 60, u35=book(1.50)), p)
    assert d2.state == "PRE_ENTRY_PENDING"
    assert _posti(d2) == [("under_entry", "back", 1.50, 20.0, "LAPSE")]


def test_m2_4_ultimo_ingresso_non_abbinato_non_si_rifa():
    ctx, p = _piatto_prima_del_segno()
    s = snap(KO - 9 * 60, u35=book(1.50))
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    ctx.legs[-1].status = "cancelled"                  # FOK non abbinato
    d = E.decide(ctx, snap(s.now + 2, u35=book(1.50)), p)
    assert d.state == "WATCH" and d.actions == []
    E.apply_decision(ctx, d, s.now + 2)
    d2 = E.decide(ctx, snap(s.now + 4, u35=book(1.50)), p)
    assert _posti(d2) == [], "l'ultimo ingresso si valuta una volta sola"
    assert d2.state == "HOLD"


def test_m2_4_il_veto_blocca_ancora_l_ultimo_ingresso():
    ctx, p = _piatto_prima_del_segno(_p(veto_p_under35_cal=True))
    s = replace(snap(KO - 9 * 60, u35=book(1.50)), p_under35_cal=0.50)
    d = E.decide(ctx, s, p)
    assert _posti(d) == [] and d.state == "HOLD"
    assert d.updates["veto_u35"]["esito"] == "veto"
    v = d.telemetry["veto_under_calibrata"]
    assert v["punto"] == "persist" and v["eseguito"] is True


def test_m2_4_senza_veto_l_ultimo_ingresso_lo_dichiara():
    ctx, p = _piatto_prima_del_segno(_p(veto_p_under35_cal=True))
    s = replace(snap(KO - 9 * 60, u35=book(1.50)), p_under35_cal=0.90)
    d = E.decide(ctx, s, p)
    assert d.state == "PRE_ENTRY_PENDING"
    assert d.telemetry["veto_under_calibrata"]["esito"] == "nessun_veto"


def test_m2_4_ultimo_ingresso_spento_come_oggi():
    ctx, p = _piatto_prima_del_segno(_p(last_entry_persist=False))
    d = E.decide(ctx, snap(KO - 9 * 60, u35=book(1.50)), p)
    assert d.state == "WATCH" and d.actions == [] and "finestra" in d.reason


@pytest.mark.parametrize("sospeso", [True, False])
def test_m2_4_mercato_sospeso_o_prezzi_non_vivi_si_aspetta(sospeso):
    ctx, p = _piatto_prima_del_segno()
    if sospeso:
        s = snap(KO - 9 * 60, u35=book(1.50, status="SUSPENDED"))
    else:
        s = snap(KO - 9 * 60, u35=book(1.50), order_fresh=False)
    d = E.decide(ctx, s, p)
    assert d.actions == [] and d.state == "WATCH"
    d2 = E.decide(ctx, snap(KO - 8 * 60, u35=book(1.50)), p)
    assert d2.state == "PRE_ENTRY_PENDING", "ripresi i prezzi, l'ultimo ingresso si valuta"


def test_m2_4_con_posizione_al_segno_nessun_ingresso():
    ctx, p = _aperta()
    d = E.decide(ctx, snap(KO - 9 * 60, u35=book(1.50)), p)
    assert d.state == "HOLD" and _posti(d) == []


def test_m2_4_in_taker_la_green_abbinata_dopo_il_segno_non_fa_rientrare():
    p = _p(pre_exit_mode="taker")
    ctx = E.MatchCtx()
    s0 = snap(DENTRO_FINESTRA, u35=book(1.50))
    E.apply_decision(ctx, E.decide(ctx, s0, p), s0.now)
    fill(ctx.legs[0])
    E.apply_decision(ctx, E.decide(ctx, snap(DENTRO_FINESTRA + 5, u35=book(1.50)), p),
                     DENTRO_FINESTRA + 5)
    E.apply_decision(ctx, E.decide(ctx, snap(KO - 9 * 60, u35=book(1.50)), p), KO - 9 * 60)
    assert ctx.state == "HOLD"
    d = E.decide(ctx, snap(KO - 8 * 60, u35=book(1.47, bl=1.48)), p)    # 2 tick: green taker
    assert d.state == "PRE_GREEN_PENDING" and _posti(d)[0][0] == "under_green"
    E.apply_decision(ctx, d, KO - 8 * 60)
    fill(ctx.legs[-1])
    d2 = E.decide(ctx, snap(KO - 7 * 60, u35=book(1.47, bl=1.48)), p)
    E.apply_decision(ctx, d2, KO - 7 * 60)
    for t in (KO - 6 * 60, KO - 5 * 60):
        d3 = E.decide(ctx, snap(t, u35=book(1.50)), p)
        assert _posti(d3) == [], "dopo il segno nessun ingresso"
        E.apply_decision(ctx, d3, t)


# ===========================================================================
# M2.3: al fischio si legge cosa resta della banca
# ===========================================================================
def _al_segno(prezzo_ora=(1.54, 1.55)):
    ctx, p = _aperta()
    s = snap(KO - 9 * 60, u35=book(prezzo_ora[0], bl=prezzo_ora[1]))
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    assert ctx.state == "HOLD"
    return ctx, p


def _fischio(now=KO + 30, goals=0, **kw):
    return snap(now, u35=book(1.54, bl=1.55, inplay=True), inplay=True, minute=0, goals=goals, **kw)


def test_m2_3_banca_abbinata_per_intero_prima_del_fischio_piatto_col_profitto():
    ctx, p = _al_segno()
    fill(_banca(ctx))
    d = E.decide(ctx, _fischio(), p)
    assert d.state == "IDLE_LIVE", "banca abbinata: piatto, niente uscita al fischio"
    assert _posti(d) == []
    assert d.telemetry["pre_cycle"]["locked"] == pytest.approx(0.27, abs=0.02)


def test_m2_3_banca_non_abbinata_cancellata_da_betfair_parte_il_flusso_del_gioco():
    ctx, p = _al_segno()
    d = E.decide(ctx, _fischio(), p)
    # la banca era ancora viva per Mike: si chiede l'annullamento, e si aspetta
    # di SAPERE come e' finita prima di appoggiare l'uscita al fischio
    assert _annulli(d) == ["under_green"] and d.state == "LIVE_KO_GREEN"
    E.apply_decision(ctx, d, KO + 30)
    d2 = E.decide(ctx, _fischio(KO + 32), p)
    assert _posti(d2) == [] and "banca" in d2.reason
    _banca(ctx).status = "cancelled"                   # LAPSE letto: niente abbinato
    d3 = E.decide(ctx, _fischio(KO + 34), p)
    assert _posti(d3) == [("ko_green", "lay", pytest.approx(1.48),
                           pytest.approx(20.27, abs=0.01), "LAPSE")]


def test_m2_3_banca_abbinata_in_parte_l_uscita_al_fischio_sul_residuo():
    ctx, p = _al_segno()
    g = _banca(ctx)
    g.matched, g.avg_price, g.status = 8.0, 1.48, "open"   # 8 abbinati, il resto LAPSE
    d = E.decide(ctx, _fischio(), p)
    assert d.state == "LIVE_KO_GREEN"
    E.apply_decision(ctx, d, KO + 30)
    d2 = E.decide(ctx, _fischio(KO + 32), p)
    w, l = E.exposure(ctx.legs, E.MARKET_OU35, E.SEL_UNDER)
    assert _posti(d2) == [("ko_green", "lay", pytest.approx(1.48),
                           pytest.approx(round((w - l) / 1.48, 2), abs=0.01), "LAPSE")]


def test_m2_3_banca_scoperta_abbinata_dopo_il_fischio_piatto():
    ctx, p = _al_segno()
    E.apply_decision(ctx, E.decide(ctx, _fischio(), p), KO + 30)
    fill(_banca(ctx))                                   # si era abbinata per intero
    d = E.decide(ctx, _fischio(KO + 32), p)
    assert d.state == "IDLE_LIVE" and _posti(d) == []


def test_m2_3_con_la_banca_da_leggere_un_gol_non_fa_la_seconda_puntata():
    ctx, p = _al_segno()
    E.apply_decision(ctx, E.decide(ctx, _fischio(), p), KO + 30)
    d = E.decide(ctx, _fischio(KO + 60, goals=1), p)
    assert d.state == "LIVE_KO_GREEN" and _posti(d) == []
    _banca(ctx).status = "cancelled"
    d2 = E.decide(ctx, _fischio(KO + 62, goals=1), p)
    assert d2.state == "LIVE_SECOND_ENTRY", "letta la banca, riparte il flusso di sempre"


# ===========================================================================
# IL BANCO: controlli D3 (banca fino al fischio) e B6 (un solo ultimo ingresso)
# ===========================================================================
from Betfair.mike import certificazione as CERT  # noqa: E402


def _codici(ctx, s, d, p):
    return [v.codice for v in CERT.verifica(ctx, s, d, p)]


def test_banco_d3_b6_tacciono_sul_motore_vero():
    ctx, p = _piatto_prima_del_segno()
    for t, bb in ((KO - 9 * 60, 1.50), (KO - 8 * 60, 1.50), (KO - 7 * 60, 1.44), (KO - 6 * 60, 1.54)):
        s = snap(t, u35=book(bb))
        d = E.decide(ctx, s, p)
        assert not {"D3", "B6"} & set(_codici(ctx, s, d, p)), d.reason
        E.apply_decision(ctx, d, t)
        if ctx.legs and ctx.legs[-1].status == "pending" and ctx.legs[-1].role == "under_entry":
            fill(ctx.legs[-1])


def test_banco_d3_vede_la_banca_ritirata_al_segno():
    """FALSIFICAZIONE del controllo: la condotta di PRIMA (al segno si ritira la
    banca) giudicata dal controllo nuovo."""
    ctx, p = _aperta()
    s = snap(KO - 9 * 60, u35=book(1.54, bl=1.55))
    vecchia = E.Decision("HOLD", E._cancel_live(ctx, ("under_green",)), "ultimo ingresso: tengo")
    assert "D3" in _codici(ctx, s, vecchia, p)


def test_banco_b6_vede_un_secondo_ingresso_dopo_il_segno():
    ctx, p = _piatto_prima_del_segno()
    s = snap(KO - 9 * 60, u35=book(1.50))
    d = E.decide(ctx, s, p)
    E.apply_decision(ctx, d, s.now)
    ctx.legs[-1].status = "cancelled"
    ctx.state = "WATCH"
    s2 = snap(KO - 8 * 60, u35=book(1.50))
    secondo = E.Decision("PRE_ENTRY_PENDING", [E._place("under_entry", E.MARKET_OU35, E.SEL_UNDER,
                                                        "back", 1.50, 20.0)], "ingresso")
    assert "B6" in _codici(ctx, s2, secondo, p)
    ctx.state = "HOLD"
    assert "B6" in _codici(ctx, s2, secondo, p)


def test_chiusura_manuale_una_lay_in_volo_su_un_altra_selezione_non_la_ferma():
    """Complemento della guardia J5 di P1 (verifica del coordinatore, mutazione
    sopravvissuta): solo una lay in volo sulla STESSA selezione da chiudere
    ferma la chiusura manuale. Una lay a esito ignoto su un altro mercato
    (Under 4,5) non deve bloccare la chiusura dell'Under 3,5."""
    ctx = E.MatchCtx(state="LIVE_COVERED", flatten_pending=True)
    ctx.legs.append(fill(E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                               side="back", price=1.50, size=10.0, ref="under_entry-0-1")))
    ctx.legs.append(E.Leg(role="reentry_green", market=E.MARKET_OU45, selection=E.SEL_UNDER,
                          side="lay", price=1.30, size=5.0, ref="reentry_green-0-5",
                          status=E.STATUS_RECONCILE))
    s = snap(KO + 30 * 60, u35=book(1.50, bl=1.52, inplay=True), u45=book(1.30, bl=1.31, inplay=True),
             o45=book(5.0, inplay=True), inplay=True, minute=30, goals=0)
    d = E.decide(ctx, s, _p())
    assert [(a.role, a.market, a.selection) for a in d.actions if a.kind == "place"] == \
        [("manual_close", E.MARKET_OU35, E.SEL_UNDER)]
    assert d.state == "LIVE_CLOSING"


# ===========================================================================
# stati vecchi: una partita salvata prima dell'aggiornamento si riprende
# ===========================================================================
def test_stati_vecchi_si_riprendono_senza_errori():
    p = _p()
    for stato in ("PRE_LAST_ENTRY_PENDING", "PRE_GREEN_PENDING", "HOLD"):
        ctx = E.MatchCtx(state=stato)
        ctx.legs.append(fill(E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                                   side="back", price=1.50, size=20.0, ref="e-0-1")))
        if stato == "PRE_GREEN_PENDING":
            ctx.legs.append(E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                                  side="lay", price=1.45, size=20.69, ref="g-0-2", final=True,
                                  placed_at=KO - 9 * 60))
        d = E.decide(ctx, snap(KO - 5 * 60, u35=book(1.46, bl=1.47)), p)
        assert d.state in E.STATES and d.state != "ERROR", stato
        d2 = E.decide(ctx, _fischio(), p)
        assert d2.state in E.STATES and d2.state != "ERROR", stato
