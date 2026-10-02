"""02/10/2026 - VERIFICA E INTEGRAZIONE DELLA CHIUSURA DI MIKE (decisioni dell'utente).

Sopra la patch del 01/10 (``test_mike_chiusura_copertura_2026_10_01.py``):

  * PRECISAZIONE DELL'UTENTE (02/10 12:40) + DECISIONE 12: si chiude sulla
    STESSA selezione della posizione. Banca Under 4,5 S @ q -> PUNTA Under 4,5
    S*q/p (Ashdod: 6,32 @ 1,23 -> 7,55 @ 1,03), in profitto E in perdita; punta
    -> banca sulla stessa selezione. L'altra selezione (banca Over 4,5) solo come
    ripiego quando la stessa selezione non e' piazzabile, mai sotto il minimo.
    Una prova per OGNI via di chiusura (tabella nel referto
    ``AUDIT_2026-10-02/MIKE_CHIUSURA_INTEGRATA.md``);
  * DECISIONE 13: residuo non chiudibile = LIVE_CLOSING fino al regolamento,
    SENZA RIENTRI, anche se poi il residuo si chiude;
  * correzione del runner (punto 2): il codice del rifiuto arriva anche sulla
    strada ASINCRONA (evento ``order``): Mike lo legge;
  * controllo L1 del banco: anche una PUNTA d'apertura sotto 0,50.

Finti: gli oggetti veri dell'engine; per il servizio ``PlaceResult`` vero, il DB
in memoria della suite, il runner finto sul protocollo vero (``runner_finto``,
evento con le chiavi di ``motore_ordini._estremi_errore``)."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple

import pytest

from Betfair.mike import certificazione as CERT
from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_chiusura_copertura_2026_10_01 import (
    COMM, KO, T0, chiusura_35, copertura, foto, gamba, ingresso, libri, libro, params)
from Betfair.mike.tests.test_mike_loop_taker_2026_09_16 import (EVENTO, ORA, db_vuoto,
                                                               info_vera)
from Betfair.mike.tests.test_mike_p4_ordini_2026_09_29 import _live  # noqa: F401 (fixture)
from Betfair.omega.omega_market import PlaceResult

# ---------------------------------------------------------------------------
# libri: in PROFITTO (i prezzi di Ashdod alle 19:07) e in PERDITA (due gol in
# piu' dell'atteso: l'Under 3,5 e' crollato, l'Under 4,5 e' a 1,70)
# ---------------------------------------------------------------------------
PROFITTO = dict(u35=(1.18, 1.20), u45=(1.06, 1.07), o45=(17.0, 18.0))
PERDITA = dict(u35=(3.00, 3.10), u45=(1.70, 1.72), o45=(2.36, 2.40))


def posizioni(legs: List[E.Leg]) -> Dict[Tuple[str, str], str]:
    """(mercato, selezione) -> lato delle APERTURE abbinate."""
    return {(l.market, l.selection): l.side for l in legs
            if l.role in E.OPENING_ROLES and float(l.matched) > 0}


def stessa_selezione(legs: List[E.Leg], acts) -> None:
    """Ogni ordine di chiusura sta sulla selezione di un'apertura, col lato opposto."""
    pos = posizioni(legs)
    piazz = [a for a in acts if a.kind == "place"]
    assert piazz, "nessun ordine di chiusura"
    for a in piazz:
        assert (a.market, a.selection) in pos, (a.role, a.market, a.selection, pos)
        assert a.side != pos[(a.market, a.selection)], (a.role, a.side)


def copertura_banca() -> List[E.Leg]:
    return [ingresso(), copertura()]


def copertura_punta() -> List[E.Leg]:
    return [ingresso(), gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 5.4, 3.0,
                              ref="over_cover-0-2")]


# ===========================================================================
# 1. la STESSA selezione, per ogni via di chiusura, in profitto e in perdita
# ===========================================================================
@pytest.mark.parametrize("prezzi", [PROFITTO, PERDITA], ids=["profitto", "perdita"])
def test_chiusure_di_serie_stessa_selezione_copertura_banca(prezzi):
    """``_close_actions``: la via UNICA di cash out «profit», «profit smart»,
    uscita a modello e a regola fissa (in perdita), e delle uscite firmate
    dall'utente (``gate_uscite`` esegue la stessa decisione)."""
    legs = copertura_banca()
    cv = E.cashout_value(legs, libri(**prezzi), COMM)
    acts = E._close_actions(E.MatchCtx(state="LIVE_COVERED", legs=legs), cv, params())
    stessa_selezione(legs, acts)
    [c45] = [a for a in acts if a.kind == "place" and a.market == E.MARKET_OU45]
    # stake = S * q / p sulla stessa selezione
    p = prezzi["u45"][0]
    assert (c45.selection, c45.side) == (E.SEL_UNDER, "back")
    assert c45.size == round(6.32 * 1.23 / p, 2) and c45.price == p


@pytest.mark.parametrize("prezzi", [PROFITTO, PERDITA], ids=["profitto", "perdita"])
def test_chiusure_di_serie_stessa_selezione_forma_di_prima(prezzi):
    """Forma di prima (punta Over 4,5): la chiusura e' la banca Over 4,5 (stessa
    selezione) quando e' piazzabile."""
    legs = copertura_punta()
    cv = E.cashout_value(legs, libri(**prezzi), COMM)
    acts = E._close_actions(E.MatchCtx(state="LIVE_COVERED", legs=legs), cv,
                            params(cover_form=E.COVER_BACK_O45))
    piazz45 = [a for a in acts if a.kind == "place" and a.market == E.MARKET_OU45]
    # la banca Over di chiusura e' sopra il minimo in entrambi i libri qui sotto?
    plan = cv.plans[(E.MARKET_OU45, E.SEL_OVER)]
    if E.size_chiudibile(plan.size, "lay"):
        stessa_selezione(legs, acts)
        assert [(a.selection, a.side) for a in piazz45] == [(E.SEL_OVER, "lay")]
    else:
        # banca sotto il minimo: ripiego sull'altra selezione SOLO se piazzabile
        assert all(E.via_ordine(a.role, a.side, a.size) == E.VIA_DIRETTA for a in piazz45)


def test_cash_out_automatico_in_profitto_chiude_sulla_stessa_selezione():
    """Il ramo vero del motore (``_decide_covered`` -> «profit»): la chiusura della
    copertura-banca e' la punta Under 4,5, mai la banca Over 0,43 @ 18."""
    legs = copertura_banca()
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=legs)
    d = E.decide(ctx, foto(**PROFITTO), params())
    assert d.state == "LIVE_CLOSING" and d.reason.startswith("profit"), d.reason
    stessa_selezione(legs, d.actions)
    assert not any(a.kind == "place" and a.selection == E.SEL_OVER for a in d.actions)


@pytest.mark.parametrize("prezzi", [PROFITTO, PERDITA], ids=["profitto", "perdita"])
def test_chiudi_dell_utente_stessa_selezione(prezzi):
    """«Chiudi» / cash out manuale (``_decide_flatten`` -> ``force_flat_plan``)."""
    legs = copertura_banca()
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=legs, flatten_pending=True)
    d = E.decide(ctx, foto(**prezzi), params())
    stessa_selezione(legs, d.actions)
    assert all(a.role == "manual_close" for a in d.actions if a.kind == "place")


@pytest.mark.parametrize("prezzi", [PROFITTO, PERDITA], ids=["profitto", "perdita"])
def test_riprezzo_della_chiusura_resta_sulla_stessa_selezione(prezzi):
    """``_decide_closing``: la chiusura viva non abbinata, prezzo mosso: annullo e
    riprezzo sulla STESSA selezione (punta Under 4,5)."""
    legs = copertura_banca() + [gamba("over_close", E.MARKET_OU45, E.SEL_UNDER, "back",
                                      1.01, 0.0, ref="over_close-0-5", status="pending",
                                      size=7.70, placed_at=T0)]
    ctx = E.MatchCtx(state="LIVE_CLOSING", legs=legs, close_reason="profit", attempts=1)
    d = E.decide(ctx, foto(now=T0 + 60, **prezzi), params(close_retry_s=10))
    piazz = [a for a in d.actions if a.kind == "place"]
    assert piazz, d.reason
    stessa_selezione(legs, d.actions)


def test_green_e_chiusura_del_3_5_stessa_selezione():
    """under_close (e i green dell'Under 3,5): banca sulla selezione della punta."""
    legs = copertura_banca()
    cv = E.cashout_value(legs, libri(**PROFITTO), COMM)
    acts = E._close_actions(E.MatchCtx(state="LIVE_COVERED", legs=legs), cv, params())
    [c35] = [a for a in acts if a.kind == "place" and a.market == E.MARKET_OU35]
    assert (c35.role, c35.selection, c35.side) == ("under_close", E.SEL_UNDER, "lay")


def test_proposta_del_residuo_propone_prima_la_stessa_selezione():
    """La proposta all'utente (``_ordini_che_chiudono``): se banca Over e punta
    Under sono entrambe piazzabili, si propone la punta Under (stessa selezione
    della copertura-banca)."""
    legs = copertura_banca()
    ctx = E.MatchCtx(state="LIVE_CLOSING", legs=legs, close_reason="profit", attempts=99)
    books = dict(u35=(1.80, 1.82), u45=(1.30, 1.31), o45=(4.2, 4.3))
    ordini, _esp = E._ordini_che_chiudono(ctx, foto(**books), params(), COMM)
    [o45] = [o for o in ordini if o["mercato"] == E.MARKET_OU45]
    assert (o45["selezione"], o45["lato"], o45["piazzabile"]) == (E.SEL_UNDER, "back", True)
    # e la banca Over sarebbe stata piazzabile anche lei (1,81): non e' un ripiego forzato
    cv = E.cashout_value(legs, libri(**books), COMM)
    assert E.size_chiudibile(cv.plans[(E.MARKET_OU45, E.SEL_OVER)].size, "lay")


def test_ripiego_sull_altra_selezione_solo_senza_prezzo_e_mai_sotto_minimo():
    """L'Under 4,5 senza quota (libro assente): la banca Over e' il RIPIEGO
    ammesso, piazzabile (>= 1,00). Con la banca sotto il minimo nessun ordine."""
    legs = copertura_banca()
    senza_under = libri(u45=(1.30, 1.31), o45=(4.2, 4.3))
    del senza_under[(E.MARKET_OU45, E.SEL_UNDER)]
    cv = E.cashout_value(legs, senza_under, COMM)
    acts = E._close_actions(E.MatchCtx(state="LIVE_COVERED", legs=legs), cv, params())
    [c45] = [a for a in acts if a.kind == "place" and a.market == E.MARKET_OU45]
    assert (c45.selection, c45.side, c45.size) == (E.SEL_OVER, "lay", 1.81)
    # banca Over sotto il minimo (Over a 18) e Under senza quota: nulla sul 4,5
    senza_under2 = libri(**PROFITTO)
    del senza_under2[(E.MARKET_OU45, E.SEL_UNDER)]
    cv2 = E.cashout_value(legs, senza_under2, COMM)
    acts2 = E._close_actions(E.MatchCtx(state="LIVE_COVERED", legs=legs), cv2, params())
    assert not [a for a in acts2 if a.kind == "place" and a.market == E.MARKET_OU45]


def test_il_servizio_manda_la_selection_id_della_posizione(monkeypatch, _live):
    """Al servizio VERO arriva la chiusura: ``place_order_live`` riceve la
    selection_id dell'Under 4,5 (la stessa della copertura), non quella dell'Over."""
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    chiamate: List[dict] = []

    def place_order_live(**kw):
        chiamate.append(kw)
        return PlaceResult(ok=True, order_status="EXECUTION_COMPLETE", bet_id="B-9",
                           size_matched=float(kw["size"]), avg_price_matched=float(kw["price"]),
                           raw={}, size_requested=float(kw["size"]),
                           price_requested=float(kw["price"]), size_remaining=0.0,
                           size_cancelled=0.0, error_code=None, betfair_updated_at=None)
    legs = copertura_banca()
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=legs)
    d = E.decide(ctx, foto(**PROFITTO), params())
    nuove = E.apply_decision(ctx, d, T0)
    [leg45] = [l for l in nuove if l.market == E.MARKET_OU45]
    info = info_vera()
    S.execute_place(db=db_vuoto(), market=SimpleNamespace(place_order_live=place_order_live),
                    info=info, leg=leg45, book=libri(**PROFITTO)[(E.MARKET_OU45, E.SEL_UNDER)],
                    mode="live", params=params(), now=ORA, dry=False, feed_fresh=True, ctx=ctx)
    assert len(chiamate) == 1
    assert chiamate[0]["selection_id"] == info.selection_id(E.MARKET_OU45, E.SEL_UNDER)
    assert chiamate[0]["selection_id"] != info.selection_id(E.MARKET_OU45, E.SEL_OVER)
    assert str(chiamate[0].get("side")).lower() == "back"


# ===========================================================================
# 2. DECISIONE 13: residuo non chiudibile -> nessun rientro, mai
# ===========================================================================
def _ashdod_residuo() -> E.MatchCtx:
    rifiutate = [gamba("over_close", E.MARKET_OU45, E.SEL_UNDER, "back", 1.03, 0.0,
                       ref=f"over_close-0-{n}", status="cancelled", size=7.55, placed_at=T0)
                 for n in range(6, 9)]
    ctx = E.MatchCtx(state="LIVE_CLOSING", legs=[ingresso(), copertura(), chiusura_35(),
                                                *rifiutate],
                     close_reason="profit", attempts=20)
    for leg in rifiutate:
        S._rifiutata(ctx, leg, "rifiutata da Betfair (INVALID_BET_SIZE)")
    return ctx


def test_decisione_13_residuo_dichiarato_spegne_il_rientro():
    ctx = _ashdod_residuo()
    d = E.decide(ctx, foto(now=T0 + 24), params())
    assert d.state == "LIVE_CLOSING" and d.reason.startswith("chiusura parziale")
    assert d.updates.get("reentry_allowed") is False and d.updates.get("reentry_done") is True


def test_decisione_13_anche_a_residuo_chiuso_la_partita_non_rientra():
    """Il residuo poi si chiude (l'utente mette la punta): FLAT, e da FLAT nessun
    rientro anche con le condizioni del rientro (1 gol, primo tempo, Under 4,5
    sopra l'ingresso, liquidita')."""
    ctx = _ashdod_residuo()
    E.apply_decision(ctx, E.decide(ctx, foto(now=T0 + 24), params()), T0 + 24)
    assert ctx.reentry_done is True
    ctx.legs.append(gamba("manual_close", E.MARKET_OU45, E.SEL_UNDER, "back", 1.03, 7.55,
                          ref="manual_close-0-30", placed_at=T0 + 200))
    d = E.decide(ctx, foto(now=T0 + 230), params())
    assert d.state == "FLAT"
    E.apply_decision(ctx, d, T0 + 230)
    rientro = E.Snapshot(now=T0 + 300, ko_at=KO, books=libri(u45=(1.60, 1.62), o45=(2.5, 2.6)),
                         inplay=True, minute=20, goals=1, feed_fresh=True, order_fresh=True)
    d2 = E.decide(ctx, rientro, params(reentry_enabled=True))
    assert d2.state == "FLAT" and not [a for a in d2.actions if a.kind == "place"], d2.reason
    assert d2.reason == "flat", d2.reason


# ===========================================================================
# 3. il codice del rifiuto sulla strada ASINCRONA (runner, punto 2)
# ===========================================================================
@pytest.mark.parametrize("codice", ["SOTTO_MINIMO_NON_PIAZZABILE", "INVALID_BET_SIZE"])
def test_codice_del_rifiuto_dal_runner_asincrono_blocca_lo_strumento(runner, codice):
    """PAPER: la chiusura passa dal runner; il runner la rifiuta e il codice
    arriva SOLO nell'evento ``order`` (strada asincrona). Mike lo legge: lo
    strumento (punta Under 4,5) non si ripropone a nessun importo."""
    ctx = E.MatchCtx(state="LIVE_CLOSING", legs=[ingresso(), copertura(), chiusura_35()],
                     close_reason="profit", attempts=0)
    d = E.decide(ctx, foto(now=T0 + 30), params())
    [leg] = [l for l in E.apply_decision(ctx, d, T0 + 30) if l.market == E.MARKET_OU45]
    assert (leg.selection, leg.side) == (E.SEL_UNDER, "back")
    db = db_vuoto()
    runner.trattieni = True                    # l'esito arriva DOPO (strada asincrona)
    runner.rifiuto_codice = codice
    S.execute_place(db=db, market=SimpleNamespace(), info=info_vera(), leg=leg,
                    book=libri()[(E.MARKET_OU45, E.SEL_UNDER)], mode="paper",
                    params=params(), now=ORA, dry=False, feed_fresh=True, ctx=ctx)
    runner.trattieni = False
    runner.rilascia()
    e = runner.esiti(runner.comandi[-1]["ref"])
    assert e["fase"] == "rifiutato" and e["error_code"] == codice
    S._segui_ordini_paper_su_runner(db=db, ctx=ctx, ev={"event_id": EVENTO},
                                    now_ts=ORA.timestamp() + 5, params=params())
    assert leg.status == "cancelled"
    prova = E._place("over_close", E.MARKET_OU45, E.SEL_UNDER, "back", 1.04, 7.40)
    assert E.chiusura_gia_rifiutata(ctx, prova) is not None, ctx.rifiuti


# ===========================================================================
# 4. controllo L1 del banco: anche la punta d'apertura sotto 0,50
# ===========================================================================
def _l1(azioni, **p):
    ctx = E.MatchCtx(state="WATCH", legs=[])
    snap = foto()
    d = E.Decision("PRE_ENTRY_PENDING", azioni, "prova")
    return CERT._l1(ctx, snap, d, params(**p))


def test_L1_punta_d_apertura_sotto_0_50_e_una_violazione():
    a = E._place("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.54, 0.30)
    assert _l1([a]) is not None
    # dal floor in su passa (place-and-trim), e con exact_sizes spento si legalizza
    assert _l1([E._place("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.54, 0.60)]) is None
    assert _l1([a], exact_sizes=False) is None
