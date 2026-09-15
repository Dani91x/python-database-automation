"""Certificazione chirurgica dell'engine di Mike - 12/09/2026.

Test di REGRESSIONE dei difetti money-critical trovati leggendo ``engine.py``
riga per riga: ognuno FALLISCE con il codice precedente e passa con il fix.
Nessuna rete, nessun DB. File ASCII-only (console Windows cp1252).
"""
from __future__ import annotations

import math

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E

KO = 1_800_000_000.0
H = 3600.0

# Un istante DENTRO la finestra di ingresso pre-match.
#
# ⚠️ 15/09 — qui c'erano `KO - 2 * H` e `KO - 1.5 * H`, scritti quando la
# finestra valeva 3 ore. Portata a 1 ora (ordine dell'utente, per validare prima
# la fase pre-match) quei due istanti sono finiti FUORI, e ventidue test hanno
# cominciato a leggere «WATCH» dove si aspettavano un ingresso — senza che
# nessuno di loro parlasse di finestre. Mezz'ora sta dentro qualunque finestra
# ragionevole. Chi vuole un istante FUORI lo scrive esplicito (`KO - 5 * H` in
# `test_watch_before_window_does_nothing`), ed e' giusto cosi': la distanza dal
# KO dev'essere una scelta del test, non l'eredita' muta di una configurazione
# di mesi prima.
DENTRO_FINESTRA = KO - 0.5 * H

COMM = 0.05


def params(**over):
    p = C.merge_params(None)
    p.update(over)
    return p


def book(bb, bs=100.0, bl=None, ls=100.0, status="OPEN", inplay=False):
    if bl is None and bb is not None and isinstance(bb, float) and math.isfinite(bb):
        bl = E.ticks_away(bb, 1)
    return E.Book(best_back=bb, back_size=bs, best_lay=bl, lay_size=ls, status=status, inplay=inplay)


def snap(now, *, books=None, **kw):
    return E.Snapshot(now=now, ko_at=KO, books=books or {}, **kw)


def leg(role, market, selection, side, price, size, matched=None, avg=None,
        status="open", archived=False, ref=""):
    return E.Leg(role=role, market=market, selection=selection, side=side, price=price,
                 size=size, matched=size if matched is None else matched,
                 avg_price=avg if avg is not None else price, status=status,
                 archived=archived, ref=ref)


def under_back(size=20.0, price=1.50, ref="e1", role="under_last"):
    return leg(role, E.MARKET_OU35, E.SEL_UNDER, "back", price, size, ref=ref)


# ---------------------------------------------------------------------------
# 1. Copertura Over 4.5: liability NETTA, non stake lordo (COSTITUZIONE 4.1)
# ---------------------------------------------------------------------------
def test_copertura_dimensionata_sulla_liability_netta_non_sullo_stake_lordo():
    """Con una lay di green ABBINATA in parte la liability Under e' minore dello
    stake: coprire lo stake intero compra Over di troppo e peggiora ogni finale 0-4."""
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", entry_price_initial=1.50)
    ctx.legs.append(under_back(20.0, 1.50, ref="e1"))
    ctx.legs.append(leg("under_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.48, 20.27,
                        matched=8.0, avg=1.48, ref="g1"))
    assert E.under_liability(ctx.legs) == pytest.approx(12.0)     # non 20

    p = params()
    s = snap(KO + 20 * 60, books={(E.MARKET_OU35, E.SEL_UNDER): book(1.35, inplay=True),
                                  (E.MARKET_OU45, E.SEL_OVER): book(8.0, bs=50, inplay=True)},
             inplay=True, minute=20, goals=0, hazard=0.05, p4_market=0.12)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_COVER_PENDING"
    # size dimensionata sul BEST (prezzo di abbinamento), limite col cuscinetto
    x_atteso = E.cover_residual(12.0, 8.0, COMM, 1.2, 0.0)
    assert d.actions[-1].size == pytest.approx(round(x_atteso, 2))
    assert d.actions[-1].price == pytest.approx(
        float(E.ticks_away(8.0, -int(p["cover_place_at_ticks"]))))
    assert d.actions[-1].size < E.cover_size(20.0, 8.0, COMM, 1.2)

    # invariante COSTITUZIONE 4.3 sulla liability NETTA: con 5+ gol il netto e' +20% di 12 = +2.40
    E.apply_decision(ctx, d, s.now)
    cov = ctx.legs[-1]
    # l'ordine si abbina al MIGLIOR prezzo disponibile (8,00), non al proprio
    # limite (7,60): e' cosi' che funziona un limite su un exchange, ed e' il
    # motivo per cui la size si dimensiona sul best
    cov.matched, cov.avg_price, cov.status = cov.size, 8.0, "open"
    dist = E.net_pnl_by_total(ctx.legs, COMM)
    assert dist[5] == pytest.approx(0.2 * 12.0, abs=0.05)
    assert dist[0] > 0 and dist[3] > 0          # con 0-3 gol si resta in profitto


def test_nessuna_copertura_se_la_liability_netta_e_zero():
    ctx = E.MatchCtx(state="LIVE_UNCOVERED")
    ctx.legs.append(under_back(20.0, 1.50, ref="e1"))
    ctx.legs.append(leg("under_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.30, 23.08,
                        matched=23.08, avg=1.30, ref="g1"))
    p = params()
    s = snap(KO + 20 * 60, books={(E.MARKET_OU45, E.SEL_OVER): book(8.0, bs=50, inplay=True)},
             inplay=True, minute=20, goals=0, hazard=0.05, p4_market=0.12)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_COVERED" and d.updates.get("cover_skipped") is True
    assert not [a for a in d.actions if a.kind == "place"]


# ---------------------------------------------------------------------------
# 2. Riprezzo copertura: contano TUTTE le gambe gia' abbinate, non solo l'ultima
# ---------------------------------------------------------------------------
def test_riprezzo_copertura_conta_tutte_le_coperture_gia_abbinate():
    """Due gambe over_cover (fill parziale + riprezzo): dimensionare il residuo
    sulla sola ultima gamba ricompra Over gia' comprato."""
    p = params()
    ctx = E.MatchCtx(state="LIVE_COVER_PENDING", attempts=0)
    ctx.legs.append(under_back(20.0, 1.50, ref="e1"))
    # copertura 1: 1.00 EUR abbinato a 8.0, residuo gia' annullato
    ctx.legs.append(leg("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.0, 3.61,
                        matched=1.0, avg=8.0, status="open", ref="c1"))
    # copertura 2 (viva): 1.50 EUR abbinato a 6.0
    ctx.legs.append(E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER,
                          side="back", price=6.0, size=3.65, matched=1.5, avg_price=6.0,
                          status="pending", ref="c2", placed_at=KO + 20 * 60))
    s = snap(KO + 21 * 60, books={(E.MARKET_OU45, E.SEL_OVER): book(5.0, bs=50, inplay=True)},
             inplay=True, minute=21, goals=0)
    d = E.decide(ctx, s, p)
    assert [a.kind for a in d.actions] == ["cancel", "place"]
    gia = E.cover_matched_value(ctx.legs, COMM)
    atteso = E.cover_residual(20.0, 5.0, COMM, 1.2, gia)
    assert d.actions[1].size == pytest.approx(round(atteso, 2))
    # e il residuo della SOLA ultima gamba sarebbe stato molto piu' grande
    sbagliato = E.cover_size_residual(20.0, 5.0, COMM, 1.2, matched=1.5, matched_price=6.0)
    assert d.actions[1].size < round(sbagliato, 2) - 0.5

    # invariante: chiuse tutte e tre le coperture il netto con 5+ gol e' +20% di 20
    finali = [ctx.legs[0], ctx.legs[1],
              leg("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 6.0, 1.5, ref="c2m"),
              leg("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 5.0, d.actions[1].size, ref="c3")]
    assert E.net_pnl_by_total(finali, COMM)[5] == pytest.approx(4.0, abs=0.02)


# ---------------------------------------------------------------------------
# 3. Cash-out: commissione per MERCATO sul netto positivo (COSTITUZIONE 4.4)
# ---------------------------------------------------------------------------
def test_cashout_applica_la_commissione_per_mercato_non_per_selezione():
    legs = [leg("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.0, 4.0, ref="c1"),
            leg("reentry", E.MARKET_OU45, E.SEL_UNDER, "back", 1.40, 10.0, ref="r1")]
    books = {(E.MARKET_OU45, E.SEL_OVER): book(9.0, bl=9.4),
             (E.MARKET_OU45, E.SEL_UNDER): book(1.30, bl=1.32)}
    cv = E.cashout_value(legs, books, COMM)
    lordo_mercato = sum(cv.per_selection.values())
    atteso = lordo_mercato * (1.0 - COMM) if lordo_mercato > 0 else lordo_mercato
    assert cv.net == pytest.approx(round(atteso, 2), abs=0.01)
    # la commissione non si applica due volte: la somma delle selezioni fa il netto
    assert sum(cv.per_selection_net.values()) == pytest.approx(cv.net, abs=0.02)


def test_cashout_una_sola_selezione_per_mercato_resta_invariato():
    """Il caso normale (Under 3.5 + Over 4.5, un mercato ciascuno) non cambia."""
    legs = [under_back(20.0, 1.50, ref="e1"),
            leg("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.0, 4.0, ref="c1")]
    books = {(E.MARKET_OU35, E.SEL_UNDER): book(1.30, bl=1.31),
             (E.MARKET_OU45, E.SEL_OVER): book(12.0, bl=12.5)}
    cv = E.cashout_value(legs, books, COMM)
    atteso = sum(v * (1.0 - COMM) if v > 0 else v for v in cv.per_selection.values())
    assert cv.net == pytest.approx(round(atteso, 2), abs=0.01)
    assert sum(cv.per_selection_net.values()) == pytest.approx(cv.net, abs=0.02)


# ---------------------------------------------------------------------------
# 4. P&L netto per OGNI totale gol 0..8, calcolato a mano
# ---------------------------------------------------------------------------
def test_pnl_netto_per_ogni_totale_gol_con_portafoglio_completo():
    """Back Under 3.5 20@1.50 + Back Over 4.5 4@8.00 + lay di chiusura 2@10.0
    sull'Over. Commissione 5% SOLO sul netto positivo di CIASCUN mercato."""
    legs = [under_back(20.0, 1.50, ref="e1"),
            leg("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.0, 4.0, ref="c1"),
            leg("over_close", E.MARKET_OU45, E.SEL_OVER, "lay", 10.0, 2.0, ref="x1")]
    got = E.net_pnl_by_total(legs, COMM)
    atteso = {}
    for t in range(0, 9):
        ou35 = 20.0 * 0.5 if t <= 3 else -20.0
        if t >= 5:                       # Over 4.5 vince: back +4*7, lay -2*9
            ou45 = 4.0 * 7.0 - 2.0 * 9.0
        else:                            # Over 4.5 perde: back -4, lay +2
            ou45 = -4.0 + 2.0
        atteso[t] = round((ou35 * 0.95 if ou35 > 0 else ou35) +
                          (ou45 * 0.95 if ou45 > 0 else ou45), 2)
    assert got == atteso
    assert atteso[3] == pytest.approx(9.5 - 2.0)
    assert atteso[4] == pytest.approx(-22.0)
    assert atteso[5] == pytest.approx(-20.0 + 10.0 * 0.95)
    # la liability dell'evento e' la perdita peggiore su tutti i totali
    assert E.event_liability(legs, COMM) == pytest.approx(22.0, abs=0.01)


# ---------------------------------------------------------------------------
# 5. Uscita in perdita a modello: i cicli ARCHIVIATI non spostano la soglia
# ---------------------------------------------------------------------------
def test_uscita_a_modello_non_conta_i_cicli_archiviati():
    # ``ht_loss_goals_min=2``: dal 13/09 il default e' 3, ma qui si misura l'EV
    # del modello, non la finestra dei gol (che ha il suo test dedicato)
    p = params(loss_exit_mode="model", h2_loss_exit_enabled=True, cashout_smart_enabled=False,
               ht_loss_goals_min=2)
    ctx = E.MatchCtx(state="LIVE_COVERED")
    # ciclo pre-match gia' chiuso in green (+0.66 bloccati): non e' capitale a rischio
    ctx.legs.append(leg("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 20.0,
                        archived=True, ref="a1"))
    ctx.legs.append(leg("under_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.45, 20.69,
                        archived=True, ref="a2"))
    ctx.legs.append(under_back(20.0, 1.50, ref="e1"))
    ctx.legs.append(leg("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.0, 4.0, ref="c1"))
    books = {(E.MARKET_OU35, E.SEL_UNDER): book(2.50, bl=2.52, inplay=True),
             (E.MARKET_OU45, E.SEL_OVER): book(4.0, bl=4.1, inplay=True)}
    dist = {0: 0.05, 1: 0.12, 2: 0.20, 3: 0.25, 4: 0.20, 5: 0.10, 6: 0.05, 7: 0.02, 8: 0.01}
    s = snap(KO + 60 * 60, books=books, inplay=True, minute=60, goals=2,
             p_total_model=dist, p4_market=0.20)
    d = E.decide(ctx, s, p)
    le = d.telemetry.get("loss_exit") or {}
    assert le.get("mode") == "model"
    attivo = E.net_pnl_by_total(E.active_legs(ctx.legs), COMM)
    ev_atteso, _p4 = E.hold_expectation(attivo, dist, 0.20)
    assert le["ev_hold"] == pytest.approx(round(ev_atteso, 2), abs=0.02)
    # con TUTTE le gambe (archiviate comprese) l'EV sarebbe piu' alto: e' il bug
    tutto = E.net_pnl_by_total(ctx.legs, COMM)
    ev_gonfio, _ = E.hold_expectation(tutto, dist, 0.20)
    assert ev_gonfio > ev_atteso + 0.3


# ---------------------------------------------------------------------------
# 6. Prezzi None / NaN dal feed: nessuna eccezione, nessun numero inventato
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("prezzo", [float("nan"), float("inf"), 0.0, 1.0, None])
def test_prezzo_non_valido_non_produce_ordini_ne_eccezioni(prezzo):
    p = params()
    bad = E.Book(best_back=prezzo, back_size=100.0, best_lay=None, status="OPEN", inplay=True)

    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[under_back(20.0, 1.50, ref="e1")])
    s = snap(KO + 20 * 60, books={(E.MARKET_OU45, E.SEL_OVER): bad},
             inplay=True, minute=20, goals=0, hazard=0.05, p4_market=0.12)
    d = E.decide(ctx, s, p)
    assert not [a for a in d.actions if a.kind == "place"]

    ctx2 = E.MatchCtx(state="LIVE_COVER_PENDING")
    ctx2.legs.append(under_back(20.0, 1.50, ref="e1"))
    ctx2.legs.append(E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER,
                           side="back", price=6.0, size=4.0, matched=1.0, avg_price=6.0,
                           status="pending", ref="c1", placed_at=KO))
    d2 = E.decide(ctx2, s, p)
    assert not [a for a in d2.actions if a.kind == "place"]

    ctx3 = E.MatchCtx()
    s3 = snap(DENTRO_FINESTRA, books={(E.MARKET_OU35, E.SEL_UNDER): bad})
    d3 = E.decide(ctx3, s3, p)
    assert d3.state == "WATCH" and d3.actions == []


def test_price_ok_e_size_ok():
    assert E.price_ok(1.01) and E.price_ok(1000.0)
    assert not E.price_ok(None) and not E.price_ok(1.0) and not E.price_ok(float("nan"))
    assert not E.price_ok(float("inf")) and not E.price_ok(-3.0)
    assert E.size_ok(0.01) and E.size_ok(2.0)
    assert not E.size_ok(0.0) and not E.size_ok(None) and not E.size_ok(float("nan"))


# ---------------------------------------------------------------------------
# 7. Probabilita' sempre in [0, 1]
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("p4", [1.5, 2.0, -1.0, float("nan")])
def test_p4_di_mercato_fuori_range_non_sporca_l_ev(p4):
    pnl = {t: (5.5 if t <= 3 else (-24.0 if t == 4 else 6.6)) for t in range(9)}
    dist = {t: 1.0 / 9.0 for t in range(9)}
    ev, p4_usata = E.hold_expectation(pnl, dist, p4)
    assert 0.0 <= p4_usata <= 1.0
    assert min(pnl.values()) - 0.01 <= ev <= max(pnl.values()) + 0.01


def test_blend_totals_normalizza_sempre_a_uno():
    d = E.blend_totals({0: 1.0, 1: 3.0}, {0: 1.0, 1: 1.0})
    assert sum(d.values()) == pytest.approx(1.0)
    assert E.blend_totals(None, None) is None
    assert E.blend_totals({0: 0.0, 1: 0.0}) is None


# ---------------------------------------------------------------------------
# 8. C2 - selezione GIA' decisa: niente prezzo preteso, niente congelamento
# ---------------------------------------------------------------------------
def test_selezione_decisa_non_pretende_prezzo_e_non_congela():
    """Dopo il 4o gol la linea 3.5 sparisce dal feed: l'Under 3.5 vale -stake
    senza prezzo, il cash-out resta ``complete`` e l'engine continua a decidere."""
    p = params(event_loss_cap_pct=10.0, cashout_smart_enabled=False)
    ctx = E.MatchCtx(state="LIVE_COVERED")
    ctx.legs.append(under_back(20.0, 1.50, ref="e1"))
    ctx.legs.append(leg("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.0, 4.0, ref="c1"))
    books = {(E.MARKET_OU45, E.SEL_OVER): book(2.0, bl=2.02, inplay=True)}   # 3.5 assente
    s = snap(KO + 70 * 60, books=books, inplay=True, minute=70, goals=4)
    cv = E.cashout_value(ctx.legs, books, COMM, 0, goals=4)
    assert cv.complete is True
    assert (E.MARKET_OU35, E.SEL_UNDER) in cv.decided
    assert cv.per_selection[(E.MARKET_OU35, E.SEL_UNDER)] == pytest.approx(-20.0)
    assert (E.MARKET_OU35, E.SEL_UNDER) not in cv.plans
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_CLOSING"
    roles = {a.role for a in d.actions if a.kind == "place"}
    assert roles == {"over_close"}                    # nessun ordine sulla linea 3.5


def test_con_cinque_gol_tutto_e_deciso_e_si_va_in_flat():
    p = params()
    ctx = E.MatchCtx(state="LIVE_COVERED")
    ctx.legs.append(under_back(20.0, 1.50, ref="e1"))
    ctx.legs.append(leg("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.0, 4.0, ref="c1"))
    s = snap(KO + 80 * 60, books={}, inplay=True, minute=80, goals=5)
    d = E.decide(ctx, s, p)
    assert d.state == "FLAT" and d.actions == []


def test_chiusura_in_attesa_su_selezione_decisa_viene_annullata():
    p = params()
    ctx = E.MatchCtx(state="LIVE_CLOSING")
    ctx.legs.append(under_back(20.0, 1.50, ref="e1"))
    ctx.legs.append(E.Leg(role="under_close", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                          side="lay", price=2.5, size=12.0, status="pending", ref="x1",
                          placed_at=KO))
    s = snap(KO + 70 * 60, books={}, inplay=True, minute=70, goals=4)
    d = E.decide(ctx, s, p)
    assert [a.kind for a in d.actions] == ["cancel"] and d.actions[0].ref == "x1"


# ---------------------------------------------------------------------------
# 9. Archiviazione: mai marcare 'cancellata' una gamba viva o a esito ignoto
# ---------------------------------------------------------------------------
def test_archiviazione_non_nasconde_gambe_vive_o_da_riconciliare():
    ctx = E.MatchCtx(state="PRE_OPEN", cycle_no=0)
    viva = E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                 price=1.50, size=20.0, status="pending", ref="viva", placed_at=KO)
    ignota = E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                   price=1.50, size=20.0, status=E.STATUS_RECONCILE, ref="ignota", placed_at=KO)
    chiusa = leg("under_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.48, 10.0, ref="chiusa")
    ctx.legs = [viva, ignota, chiusa]
    d = E.Decision("WATCH", [], "ciclo chiuso", updates={"_archive_legs": True})
    E.apply_decision(ctx, d, KO)
    assert viva.status == "pending" and viva.archived is False
    assert ignota.status == E.STATUS_RECONCILE and ignota.archived is False
    assert chiusa.archived is True
    # la gamba a esito ignoto continua a pesare al PEGGIOR CASO (C3 / M4)
    assert E.event_liability(ctx.legs, COMM) > 0.0
    assert E.has_unknown_orders(ctx) is True


def test_chiusura_ciclo_annulla_gli_ordini_ancora_vivi():
    ctx = E.MatchCtx(state="PRE_OPEN", cycle_no=0)
    ctx.legs.append(leg("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 20.0,
                        matched=20.0, ref="e1"))
    ctx.legs.append(leg("under_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.48, 20.27,
                        matched=20.27, ref="g1"))
    ctx.legs.append(E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                          side="back", price=1.49, size=20.0, status="pending",
                          ref="residuo", placed_at=KO - 3 * H))
    p = params()
    s = snap(DENTRO_FINESTRA, books={(E.MARKET_OU35, E.SEL_UNDER): book(1.46)})
    d = E.decide(ctx, s, p)
    assert d.state == "WATCH"
    assert [(a.kind, a.ref) for a in d.actions] == [("cancel", "residuo")]


# ---------------------------------------------------------------------------
# 10. Contratto UI: i campi letti dalla card esistono davvero
# ---------------------------------------------------------------------------
def test_telemetria_cover_wait_ha_i_campi_letti_dalla_card():
    """``coverWaitLabel`` legge hazard, p4/p4_market e until_min/max_min."""
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[under_back(20.0, 1.50, ref="e1")])
    p = params()
    s = snap(KO + 300, books={(E.MARKET_OU35, E.SEL_UNDER): book(1.45, inplay=True),
                              (E.MARKET_OU45, E.SEL_OVER): book(6.0, bs=50, inplay=True)},
             inplay=True, minute=5, goals=0, hazard=0.05, p4_market=0.12)
    d = E.decide(ctx, s, p)
    w = d.telemetry["cover_wait"]
    for k in ("minute", "goals", "hazard", "p4_market", "price_over", "max_min", "x_now"):
        assert k in w, k
    assert w["max_min"] == int(p["cover_wait_max_min"])


def test_exit_kind_sempre_dentro_il_contratto():
    casi = [("manual_close", None), ("under_green", None), ("under_green", "reentry_time"),
            ("under_close", "profit"), ("over_close", "loss_ht"), ("over_close", "loss_cap"),
            ("reentry_green", "reentry_time"), ("under_close", None), ("under_close", "manual")]
    for role, reason in casi:
        assert E.exit_kind_for(role, reason) in E.EXIT_KINDS
    assert E.exit_kind_for("under_close", "loss_cap") == "forced"
    assert E.exit_kind_for("over_close", "loss_2t") == "loss"
    assert E.exit_kind_for("manual_close", None) == "manual"


def test_stati_e_ruoli_sono_quelli_dichiarati():
    # 19 stati storici + LIVE_KO_GREEN e LIVE_SECOND_ENTRY (flusso dal fischio, 13/09)
    assert len(E.STATES) == 21 and len(set(E.STATES)) == 21
    assert set(E.TERMINAL_STATES) <= set(E.STATES)
    # 9 ruoli storici + under_second (seconda puntata) e ko_green (uscita al fischio)
    assert len(E.ROLES) == 11
    assert set(E.UNDER_ROLES) <= set(E.OPENING_ROLES)
    assert set(E.OPENING_ROLES) | set(E.CLOSING_ROLES) == set(E.ROLES)
    assert not (set(E.OPENING_ROLES) & set(E.CLOSING_ROLES))


# ---------------------------------------------------------------------------
# 11. H4 - P&L per riga NETTO, somma = netto partita, closes_ref sulle chiusure
# ---------------------------------------------------------------------------
def test_settle_per_riga_netto_somma_al_netto_della_partita():
    legs = [under_back(20.0, 1.50, ref="e1"),
            leg("under_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.40, 6.0, ref="g1"),
            leg("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.0, 4.0, ref="c1")]
    for totale in range(0, 9):
        r = E.settle_legs(legs, totale, COMM)
        assert sum(p for _r, _s, p in r.per_leg) == pytest.approx(r.net, abs=0.02)
        assert r.net == pytest.approx(E.net_pnl_by_total(legs, COMM)[totale], abs=0.02)
        lordo = sum(p for _r, _s, p in r.per_leg_gross)
        comm = sum(r.commission_by_market.values())
        assert lordo - comm == pytest.approx(r.net, abs=0.02)


def test_void_per_mercato_non_azzera_l_altro_mercato():
    legs = [under_back(20.0, 1.50, ref="e1"),
            leg("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.0, 4.0, ref="c1")]
    r = E.settle_legs_by_market(legs, {E.MARKET_OU35: E.SEL_OVER, E.MARKET_OU45: None}, COMM)
    assert r.per_market[E.MARKET_OU35] == pytest.approx(-20.0)
    assert E.MARKET_OU45 not in r.per_market
    assert r.net == pytest.approx(-20.0)


def test_ogni_chiusura_porta_il_riferimento_dell_apertura():
    ctx = E.MatchCtx(state="LIVE_COVERED")
    ctx.legs.append(under_back(20.0, 1.50, ref="e1"))
    ctx.legs.append(leg("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.0, 4.0, ref="c1"))
    books = {(E.MARKET_OU35, E.SEL_UNDER): book(1.20, bl=1.21, inplay=True),
             (E.MARKET_OU45, E.SEL_OVER): book(20.0, bl=21.0, inplay=True)}
    p = params(cashout_smart_enabled=False)
    s = snap(KO + 40 * 60, books=books, inplay=True, minute=40, goals=0)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_CLOSING"
    nuove = E.apply_decision(ctx, d, s.now)
    for l in nuove:
        assert l.role in E.CLOSING_ROLES
        assert l.closes_ref in ("e1", "c1")


# ---------------------------------------------------------------------------
# 12. M4 - capitale a rischio: mai apertura + chiusura + cicli archiviati
# ---------------------------------------------------------------------------
def test_capitale_a_rischio_non_somma_chiusure_ne_cicli_archiviati():
    legs = [
        leg("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 20.0, archived=True, ref="a1"),
        leg("under_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.45, 20.69, archived=True, ref="a2"),
        under_back(20.0, 1.50, ref="e1"),
        leg("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.0, 4.0, ref="c1"),
        leg("under_close", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.40, 5.0, ref="x1"),
    ]
    assert E.invested(legs) == pytest.approx(24.0)          # 20 + 4, senza chiusure/archivi
    # liability = perdita peggiore sulle posizioni NETTE, non somma delle gambe
    peggiore = -min(E.net_pnl_by_total(E.active_legs(legs), COMM).values())
    assert E.event_liability(legs, COMM) == pytest.approx(peggiore, abs=0.01)
    assert E.event_liability(legs, COMM) < 24.0


def test_locked_pnl_solo_a_posizione_piatta():
    chiuse = [leg("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 20.0, ref="e1"),
              leg("under_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.48, 20.27, ref="g1")]
    v = E.locked_pnl(chiuse, COMM)
    assert v is not None and v == pytest.approx(E.net_pnl_by_total(chiuse, COMM)[0], abs=0.01)
    aperte = chiuse + [leg("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.0, 4.0, ref="c1")]
    assert E.locked_pnl(aperte, COMM) is None


# ---------------------------------------------------------------------------
# 13. Re-ingresso: una sola volta per partita
# ---------------------------------------------------------------------------
def test_re_ingresso_una_sola_volta():
    p = params(stake=10.0)
    ctx = E.MatchCtx(state="FLAT", entry_price_initial=1.50, reentry_allowed=True)
    books = {(E.MARKET_OU45, E.SEL_UNDER): book(1.60, bs=50, inplay=True)}
    s = snap(KO + 30 * 60, books=books, inplay=True, minute=30, goals=1)
    d = E.decide(ctx, s, p)
    assert d.state == "REENTRY_PENDING"
    E.apply_decision(ctx, d, s.now)
    # il re-ingresso non si abbina e scade: reentry_done, mai piu' un secondo tentativo
    ctx.legs[-1].status = "cancelled"
    d2 = E.decide(ctx, snap(s.now + 120, books=books, inplay=True, minute=32, goals=1), p)
    assert d2.state == "FLAT" and d2.updates.get("reentry_done") is True
    E.apply_decision(ctx, d2, s.now + 120)
    d3 = E.decide(ctx, snap(s.now + 240, books=books, inplay=True, minute=34, goals=1), p)
    assert d3.state == "FLAT" and not d3.actions


def test_dopo_una_uscita_in_perdita_niente_re_ingresso():
    p = params()
    ctx = E.MatchCtx(state="LIVE_CLOSING", close_reason="loss_ht", attempts=0)
    d = E.decide(ctx, snap(KO + 50 * 60, books={}, inplay=True, minute=50, goals=2), p)
    assert d.state == "FLAT" and d.updates.get("reentry_allowed") is False


# ---------------------------------------------------------------------------
# 14. Ordine a esito ignoto: si tolgono le APERTURE, restano le riduzioni
# ---------------------------------------------------------------------------
def test_ordine_a_esito_ignoto_blocca_solo_le_aperture():
    p = params(stake=10.0)
    ctx = E.MatchCtx(state="LIVE_UNCOVERED")
    ctx.legs.append(under_back(20.0, 1.50, ref="e1"))
    ctx.legs.append(E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                          side="back", price=1.50, size=10.0, status=E.STATUS_RECONCILE,
                          ref="ignota", placed_at=KO))
    s = snap(KO + 20 * 60, books={(E.MARKET_OU35, E.SEL_UNDER): book(1.35, inplay=True),
                                  (E.MARKET_OU45, E.SEL_OVER): book(8.0, bs=50, inplay=True)},
             inplay=True, minute=20, goals=0, hazard=0.05, p4_market=0.12)
    d = E.decide(ctx, s, p)
    assert not [a for a in d.actions if a.kind == "place" and a.role in E.OPENING_ROLES]
    assert "ignoto" in d.reason


# ---------------------------------------------------------------------------
# 15. Cash out / Flatten manuale: la chiusura non si autocancella ogni ciclo
# ---------------------------------------------------------------------------
def _flatten_ctx():
    ctx = E.MatchCtx(state="LIVE_COVERED", flatten_pending=True)
    ctx.legs.append(under_back(20.0, 1.50, ref="e1"))
    return ctx, params(stake=20.0)


def _flat_books():
    return {(E.MARKET_OU35, E.SEL_UNDER): book(1.30, bl=1.31, inplay=True)}


def test_chiusura_manuale_non_cancella_il_proprio_ordine_a_ogni_ciclo():
    ctx, p = _flatten_ctx()
    s = snap(KO + 3000, books=_flat_books(), inplay=True, minute=50, goals=0)
    d0 = E.decide(ctx, s, p)
    assert [(a.kind, a.role) for a in d0.actions] == [("place", "manual_close")]
    E.apply_decision(ctx, d0, s.now)
    # ciclo successivo dentro close_retry_s: si ASPETTA il fill, non si cancella
    s1 = snap(s.now + 3, books=_flat_books(), inplay=True, minute=50, goals=0)
    d1 = E.decide(ctx, s1, p)
    assert d1.actions == [] and "attendo" in d1.reason
    # oltre close_retry_s: riprezzo (cancel + nuova chiusura), non loop di soli cancel
    s2 = snap(s.now + float(p["close_retry_s"]) + 1, books=_flat_books(), inplay=True,
              minute=50, goals=0)
    d2 = E.decide(ctx, s2, p)
    assert [(a.kind, a.role) for a in d2.actions] == [("cancel", "manual_close"),
                                                      ("place", "manual_close")]
    assert d2.updates.get("attempts") == 1


def test_chiusura_manuale_annulla_prima_gli_altri_ordini_vivi():
    """H1: una lay di green appoggiata va tolta PRIMA di chiudere la posizione."""
    ctx, p = _flatten_ctx()
    ctx.legs.append(E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                          side="lay", price=1.48, size=20.27, status="pending", ref="g1",
                          placed_at=KO))
    s = snap(KO + 3000, books=_flat_books(), inplay=True, minute=50, goals=0)
    d = E.decide(ctx, s, p)
    assert [(a.kind, a.ref) for a in d.actions] == [("cancel", "g1")]
    assert d.updates.get("close_reason") == "manual"


def test_chiusura_manuale_senza_prezzo_non_archivia_una_posizione_aperta():
    ctx, p = _flatten_ctx()
    s = snap(KO + 3000, books={}, inplay=True, minute=50, goals=0)
    d = E.decide(ctx, s, p)
    assert d.actions == [] and d.updates == {}
    assert d.state == "LIVE_COVERED"


# ---------------------------------------------------------------------------
# 16. COSTITUZIONE 4.15 - la somma dei P&L delle righe fa ESATTAMENTE il netto
# ---------------------------------------------------------------------------
def test_fuzz_somma_righe_uguale_al_settled_pnl_al_centesimo():
    """Fuzz deterministico: con qualunque combinazione di size/quote/commissione
    ``sum(per_leg) == net`` al centesimo (prima lo scarto arrivava a 0,02 EUR)."""
    import random

    rng = random.Random(20260912)
    ruoli_back = ["under_entry", "under_last", "over_cover", "reentry"]
    ruoli_lay = ["under_green", "under_close", "over_close", "reentry_green", "manual_close"]
    combinazioni = [(E.MARKET_OU35, E.SEL_UNDER), (E.MARKET_OU45, E.SEL_OVER),
                    (E.MARKET_OU45, E.SEL_UNDER)]
    peggiore = 0.0
    for caso in range(4000):
        comm = rng.choice([0.0, 0.02, 0.05, 0.065, 0.07])
        legs = []
        for i in range(rng.randint(1, 6)):
            market, selection = rng.choice(combinazioni)
            side = rng.choice(["back", "lay"])
            ruolo = rng.choice(ruoli_back if side == "back" else ruoli_lay)
            prezzo = round(rng.uniform(1.01, 40.0), 2)
            size = round(rng.uniform(0.01, 120.0), 2)
            matched = round(size * rng.choice([0.0, 0.13, 0.5, 0.777, 1.0]), 2)
            legs.append(leg(ruolo, market, selection, side, prezzo, size,
                            matched=matched, avg=prezzo, ref=f"{caso}-{i}"))
        for totale in (0, 3, 4, 5, 8):
            r = E.settle_legs(legs, totale, comm)
            somma = round(sum(p for _ref, _st, p in r.per_leg), 2)
            peggiore = max(peggiore, abs(somma - r.net))
            assert somma == pytest.approx(r.net, abs=0.0001), (caso, totale, comm, somma, r.net)
            # coerenza con la distribuzione per totale gol
            assert r.net == pytest.approx(E.net_pnl_by_total(legs, comm, 8)[totale], abs=0.02)
    assert peggiore < 0.0001


def test_residuo_di_arrotondamento_finisce_su_una_riga_in_utile():
    legs = [leg("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.37, 3.33, ref="a"),
            leg("under_last", E.MARKET_OU35, E.SEL_UNDER, "back", 2.11, 7.77, ref="b"),
            leg("under_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.91, 1.11, ref="c")]
    for comm in (0.05, 0.065):
        r = E.settle_legs(legs, 2, comm)
        assert sum(p for _ref, _st, p in r.per_leg) == pytest.approx(r.net, abs=0.0001)
        vinc = [p for _ref, st, p in r.per_leg if st == "won"]
        assert vinc and all(p > 0 for p in vinc)


# ---------------------------------------------------------------------------
# 17. Numerazione dei cicli nei testi: UNA convenzione, 1-based come la UI
# ---------------------------------------------------------------------------
def _numero_nel_testo(testo):
    import re
    m = re.search(r"ciclo\s+(\d+)", testo)
    assert m, f"nessun numero di ciclo nel testo: {testo!r}"
    return int(m.group(1))


def test_i_testi_dei_reason_numerano_i_cicli_da_uno_come_la_ui():
    """``d.reason`` finisce GREZZO in mike_activity (state.reason) e su ctx.last_reason:
    deve usare la stessa numerazione della card (lib/mike.ts::cycleNumber = +1)."""
    p = params(stake=20.0, pre_exit_mode="resting")

    def books(bb):
        return {(E.MARKET_OU35, E.SEL_UNDER): book(bb)}

    ctx = E.MatchCtx()
    t = DENTRO_FINESTRA
    for atteso in (1, 2, 3):
        cycle_no_apertura = ctx.cycle_no
        d = E.decide(ctx, snap(t, books=books(1.50)), p)
        assert d.state == "PRE_ENTRY_PENDING"
        assert _numero_nel_testo(d.reason) == atteso
        assert _numero_nel_testo(d.reason) == E.cycle_label(cycle_no_apertura)
        E.apply_decision(ctx, d, t)
        for l in ctx.legs:
            if l.status == "pending":
                l.matched, l.avg_price, l.status = l.size, l.price, "open"
        t += 5
        E.apply_decision(ctx, E.decide(ctx, snap(t, books=books(1.50)), p), t)
        for l in ctx.legs:
            if l.status == "pending":
                l.matched, l.avg_price, l.status = l.size, l.price, "open"
        t += 5
        cycle_no_chiusura = ctx.cycle_no
        d2 = E.decide(ctx, snap(t, books=books(1.46)), p)
        assert d2.state == "WATCH"
        # stesso numero all'apertura e alla chiusura dello STESSO ciclo
        assert _numero_nel_testo(d2.reason) == atteso
        assert _numero_nel_testo(d2.reason) == E.cycle_label(cycle_no_chiusura)
        # il dato STRUTTURATO resta 0-based (lo converte la UI, e ci passa il signal_key)
        assert d2.telemetry["pre_cycle"]["cycle"] == cycle_no_chiusura == atteso - 1
        E.apply_decision(ctx, d2, t)
        t += 70
    assert ctx.cycle_no == 3


def test_cycle_label_e_il_riferimento_delle_gambe():
    assert [E.cycle_label(n) for n in (0, 1, 2, 9)] == [1, 2, 3, 10]
    assert E.cycle_label(-1) == 1
    # il ref (signal_key sul DB) NON cambia: resta sul cycle_no 0-based
    ctx = E.MatchCtx(state="WATCH", cycle_no=0)
    p = params(stake=20.0)
    s = snap(DENTRO_FINESTRA, books={(E.MARKET_OU35, E.SEL_UNDER): book(1.50)})
    nuove = E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    assert nuove[0].ref.startswith("under_entry-0-")
    assert nuove[0].cycle_no == 0


def test_ciclo_chiuso_in_perdita_non_scrive_un_piu_davanti_al_meno():
    ctx = E.MatchCtx(state="PRE_OPEN", cycle_no=1)
    d = E._cycle_done(ctx, snap(KO - H), 20.0, 1.50, None, locked_w=-0.27)
    assert "+-" not in d.reason
    assert d.reason == "ciclo 2 chiuso: -0.27"
    d2 = E._cycle_done(ctx, snap(KO - H), 20.0, 1.50, None, locked_w=0.27)
    assert d2.reason == "ciclo 2 chiuso: +0.27"


# ===========================================================================
# CERTIFICAZIONE P&L 12/09 - riscontro incrociato con il DB reale
# (Betfair/tools/verifica_pnl_2026_09_12.py).
# ===========================================================================
def _ciclo_greenato(n: int) -> list:
    """Un ciclo reale di Mike sul mercato 3.5: back 10.00@1.53 + lay 10.13@1.51."""
    return [
        leg("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.53, 10.0,
            ref="under_entry-%d-1" % n),
        leg("under_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.51, 10.13,
            ref="under_green-%d-2" % n),
    ]


def test_commissione_una_volta_sola_sul_MERCATO_anche_con_cinque_cicli():
    """Caso reale (mike_trades 7..20, mercato 1.262279694, 5 cicli sullo stesso
    mercato): lordo 0,65 -> commissione 0,03 -> netto 0,62.

    Sul DB quelle righe sommano 0,60: due centesimi persi perche' ogni ciclo
    arrotondava la propria quota di commissione a 0,01 (5 x 0,01 = 0,05 invece
    di 0,03). Il residuo di arrotondamento (§4.15) corregge la deriva: questo
    test lo BLOCCA, ed e' la prova che il codice di oggi non rifarebbe l'errore.
    """
    legs = [l for n in range(5) for l in _ciclo_greenato(n)]
    res = E.settle_legs_by_market(legs, {E.MARKET_OU35: E.SEL_OVER}, COMM)
    assert res.commission_by_market[E.MARKET_OU35] == 0.03
    assert res.per_market[E.MARKET_OU35] == 0.62
    assert round(sum(p for _ref, _st, p in res.per_leg), 2) == 0.62, \
        "la somma delle righe DEVE fare il netto del mercato (mai 0,60)"


def test_commissione_zero_se_il_mercato_chiude_in_perdita():
    legs = _ciclo_greenato(0)
    # UNDER vince: il back incassa, il lay paga -> netto positivo; qui invece
    # si forza il caso opposto con un solo back perdente
    solo_back = [legs[0]]
    res = E.settle_legs_by_market(solo_back, {E.MARKET_OU35: E.SEL_OVER}, COMM)
    assert res.commission_by_market[E.MARKET_OU35] == 0.0
    assert res.per_market[E.MARKET_OU35] == -10.0


def test_mercato_void_vale_zero_e_non_paga_commissione():
    legs = _ciclo_greenato(0)
    res = E.settle_legs_by_market(legs, {E.MARKET_OU35: None}, COMM)
    assert [p for _r, _s, p in res.per_leg] == [0.0, 0.0]
    assert res.net == 0.0


def test_il_bloccato_di_mike_e_NETTO_commissione():
    """Differenza dichiarata fra le sezioni (certificazione 12/09): il
    «P&L bloccato» di Mike e' NETTO (``E.locked_pnl`` passa per
    ``net_pnl_by_total``), quello di Omega/Safe e' LORDO
    (``safe_strategy.execution.hedge_state``). Se un giorno si uniformano,
    questo test dice da che parte si stava."""
    legs = _ciclo_greenato(0)
    for l in legs:
        l.status = "settled"
    lordo = sum(E.net_pnl_by_total(legs, 0.0).values()) / len(E.net_pnl_by_total(legs, 0.0))
    netto = E.locked_pnl(legs, COMM)
    assert netto is not None
    assert netto <= round(lordo, 2) + 1e-9
