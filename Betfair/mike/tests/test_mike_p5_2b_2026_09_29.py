"""PIANO MIKE 29/09, P5 blocco 2B (richieste del coordinatore dopo la revisione):

1. punteggio ASSENTE con la copertura ordinata dal flusso (``cover_forced``):
   anche nella forma banca Under 4,5 nessun ordine (M8.4, stessa guardia del
   ramo della forma di prima portata da P2-bis);
2. mutazione Q19 sopravvissuta al blocco 1: la riga del mercato 4,5 in
   ``posizione_per_selezione`` conta la banca Under anche se la chiave e' l'Over;
3. domanda (a): ``cover_matched_value`` su una banca Under abbinata IN PARTE;
4. domanda (b): nel rientro un resto vero (0,05 di banca a 1,50) NON e' piatto,
   anche se prima c'e' stata la chiusura della copertura a quota 21.

Finti: gli oggetti veri dell'engine.
"""
from __future__ import annotations

from typing import Optional

from Betfair.mike import config as C
from Betfair.mike import engine as E

KO = 1_800_000_000.0
COMM = 0.05


def params(**over):
    p = C.merge_params(None)
    p["uscite_automatiche"] = True
    p["cover_form"] = E.COVER_LAY_U45
    p.update(over)
    return p


def gamba(role, market, selection, side, prezzo, abbinato, *, ref, status="open",
          size: Optional[float] = None) -> E.Leg:
    return E.Leg(role=role, market=market, selection=selection, side=side, price=prezzo,
                 size=abbinato if size is None else size, matched=abbinato,
                 avg_price=prezzo if abbinato > 0 else None, ref=ref, status=status,
                 placed_at=KO)


def ingresso():
    return gamba("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 10.0,
                 ref="under_entry-0-1")


def libro(bb, bl, bs=500.0, ls=500.0):
    return E.Book(best_back=bb, back_size=bs, best_lay=bl, lay_size=ls, status="OPEN",
                  inplay=True)


def _snap(goals):
    books = {(E.MARKET_OU35, E.SEL_UNDER): libro(1.45, 1.46),
             (E.MARKET_OU45, E.SEL_UNDER): libro(1.17, 1.18),
             (E.MARKET_OU45, E.SEL_OVER): libro(6.6, 6.8)}
    return E.Snapshot(now=KO + 1200, ko_at=KO, books=books, inplay=True, minute=20,
                      goals=goals, feed_fresh=True, order_fresh=True)


def test_punteggio_assente_con_copertura_ordinata_nessuna_banca():
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[ingresso()], cover_forced=True)
    d = E.decide(ctx, _snap(None), params())
    assert [a for a in d.actions if a.kind == "place"] == []
    assert d.state == "LIVE_UNCOVERED"
    assert d.reason == "copertura: punteggio assente, attendo"
    # con il punteggio la stessa copertura ordinata parte (il test non passa a vuoto)
    d2 = E.decide(ctx, _snap(0), params())
    assert [(a.selection, a.side) for a in d2.actions if a.kind == "place"] == [
        (E.SEL_UNDER, "lay")]


def test_riga_del_mercato_4_5_conta_la_banca_under():
    legs = [ingresso(), gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.18, 12.63,
                              ref="over_cover-0-2")]
    righe = {(r["market"], r["selection"]): r for r in E.posizione_per_selezione(legs, {}, COMM)}
    r = righe[(E.MARKET_OU45, E.SEL_OVER)]
    assert r["abbinato"] == 12.63
    assert r["abbinato_per_selezione"] == {E.SEL_UNDER: {"back": 0.0, "lay": 12.63}}


def test_cover_matched_value_banca_under_abbinata_in_parte():
    """Domanda (a): 5,00 abbinati a 1,18 su una tranche da 9,47. Con 5+ gol
    l'Under 4,5 perde e la banca incassa 5,00, netto 4,75: e' il gia' coperto A.
    Il resto per la copertura piena: (12 - 4,75) / 0,95 = 7,63."""
    legs = [ingresso(), gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.18, 5.0,
                              ref="over_cover-0-2", size=9.47)]
    a = E.cover_matched_value(legs, COMM)
    assert a == 4.75
    assert round(E.cover_residual_lay(E.under_liability(legs), COMM, 1.2, a), 2) == 7.63


def test_rientro_con_resto_vero_non_e_piatto_dopo_la_chiusura_a_quota_21():
    """Domanda (b): copertura (punta Over) chiusa a 21, rientro 10 a 1,30, green
    abbinata in parte (8,61 a 1,50): resta 0,079 di sbilancio (0,05 di banca a
    1,50). L'ultima chiusura abbinata e' la green (1,50): tolleranza 0,01, non
    0,105 della chiusura a 21. Non e' piatto e la green del resto riparte."""
    legs = [gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 6.6, 2.26, ref="over_cover-0-2"),
            gamba("over_close", E.MARKET_OU45, E.SEL_OVER, "lay", 21.0, 0.71, ref="over_close-0-3"),
            gamba("reentry", E.MARKET_OU45, E.SEL_UNDER, "back", 1.30, 10.0, ref="reentry-0-4"),
            gamba("reentry_green", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.50, 8.61,
                  ref="reentry_green-0-5", size=8.67)]
    w, l = E.exposure(legs, E.MARKET_OU45, E.SEL_UNDER)
    assert round(w - l, 3) == 0.079
    assert E.tolleranza_piatto_ou45(legs) == 0.01
    assert E.open_selections(legs) == [(E.MARKET_OU45, E.SEL_UNDER)]
    ctx = E.MatchCtx(state="REENTRY_OPEN", legs=legs)
    d = E._decide_reentry_open(ctx, _snap(1), params(), COMM)
    assert d.state == "REENTRY_OPEN"
    [a] = [x for x in d.actions if x.kind == "place"]
    assert (a.role, a.side, a.size) == ("reentry_green", "lay", 0.06)
