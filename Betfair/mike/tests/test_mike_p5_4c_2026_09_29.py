"""PIANO MIKE 29/09, P5 blocco 4C (richiesta del coordinatore): la chiusura
manuale in gioco e lo STATO del mercato.

- SOSPESO o ignoto (riaprira'): si aspetta, nessun ordine, stato fermo;
- CHIUSO su una delle chiusure: quella non si puo' fare e NON ferma le altre;
- ``force_flat_plan`` non mette fra le chiusure una selezione gia' DECISA dai gol
  (l'Under 3,5 dopo il 4o gol): la guardia non puo' bloccare l'altra gamba.

Finti: oggetti veri dell'engine.
"""
from __future__ import annotations

from Betfair.mike import config as C
from Betfair.mike import engine as E

KO = 1_800_000_000.0


def params():
    p = C.merge_params(None)
    p["uscite_automatiche"] = True
    return p


def gamba(role, market, selection, side, prezzo, abbinato, *, ref):
    return E.Leg(role=role, market=market, selection=selection, side=side, price=prezzo,
                 size=abbinato, matched=abbinato, avg_price=prezzo, ref=ref, status="open",
                 placed_at=KO)


def _ctx():
    legs = [gamba("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 10.0,
                  ref="under_entry-0-1"),
            gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.18, 12.63,
                  ref="over_cover-0-2")]
    return E.MatchCtx(state="LIVE_COVERED", legs=legs, flatten_pending=True)


def libro(bb, bl, status="OPEN"):
    return E.Book(best_back=bb, back_size=500.0, best_lay=bl, lay_size=500.0,
                  status=status, inplay=True)


def foto(st35="OPEN", st45="OPEN", goals=2):
    books = {(E.MARKET_OU35, E.SEL_UNDER): libro(1.40, 1.41, st35),
             (E.MARKET_OU45, E.SEL_UNDER): libro(1.10, 1.11, st45),
             (E.MARKET_OU45, E.SEL_OVER): libro(10.0, 11.0, st45)}
    return E.Snapshot(now=KO + 3000, ko_at=KO, books=books, inplay=True, minute=50,
                      goals=goals, feed_fresh=True, order_fresh=True)


def _posti(d):
    return [(a.market, a.selection, a.side) for a in d.actions if a.kind == "place"]


def test_sospeso_si_aspetta_tutto():
    for st45 in ("SUSPENDED", "QUALCOSA_DI_IGNOTO"):
        d = E._decide_flatten(_ctx(), foto(st45=st45), params())
        assert _posti(d) == [] and d.state == "LIVE_COVERED", st45
        assert "attendo la riapertura" in d.reason


def test_un_mercato_chiuso_non_ferma_la_chiusura_dell_altro():
    d = E._decide_flatten(_ctx(), foto(st45="CLOSED"), params())
    assert _posti(d) == [(E.MARKET_OU35, E.SEL_UNDER, "lay")]
    # 02/10 (decisione 12 dell'utente): la chiusura della copertura-banca e' la
    # PUNTA Under 4,5 di serie, quindi il mercato chiuso si dice sulla selezione
    # di quell'ordine (prima: banca Over, «OU45|OVER»). Condotta identica:
    # nessun ordine sul 4,5 chiuso, la chiusura del 3,5 parte.
    assert "CHIUSO su OU45|UNDER" in d.reason and d.state == "LIVE_CLOSING"


def test_tutti_chiusi_nessun_ordine_e_lo_si_dice():
    d = E._decide_flatten(_ctx(), foto(st35="CLOSED", st45="CLOSED"), params())
    assert _posti(d) == [] and "nessuna chiusura possibile" in d.reason


def test_selezione_gia_decisa_dai_gol_non_e_fra_le_chiusure():
    """Con 4 gol l'Under 3,5 e' PERSO (``selection_decided``): ``cashout_value``
    lo mette fra i ``decided`` senza piano (engine.py, ``cashout_value``, ramo
    ``won is not None``), quindi ``_close_actions`` non lo chiude e la guardia
    del mercato non lo guarda. La chiusura della copertura parte."""
    cancels, closes = E.force_flat_plan(_ctx(), foto(goals=4).books, params(), goals=4)
    # 02/10 (decisione 12 dell'utente): la chiusura della copertura-banca e' la
    # PUNTA Under 4,5 di serie (prima: banca Over 4,5). Il punto del test resta:
    # l'Under 3,5 deciso non e' fra le chiusure e quella del 4,5 parte.
    assert [(a.market, a.selection) for a in closes] == [(E.MARKET_OU45, E.SEL_UNDER)]
    # anche con il mercato 3,5 CHIUSO (linea potata dopo il 4o gol) la chiusura parte
    d = E._decide_flatten(_ctx(), foto(st35="CLOSED", goals=4), params())
    assert _posti(d) == [(E.MARKET_OU45, E.SEL_UNDER, "back")]
