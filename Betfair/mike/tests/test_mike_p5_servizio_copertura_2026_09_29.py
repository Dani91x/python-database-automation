"""PIANO MIKE 29/09, P5 blocco 3: il SERVIZIO con la copertura come banca
Under 4,5.

1. ``_sorveglia_mercato_copertura`` legge il libro della selezione su cui sta
   (o stara') la copertura: con la forma banca e' l'Under 4,5. Prima leggeva
   sempre l'Over: una sospensione dell'Under non veniva mai detta.
2. La riga ``mike_trades`` della copertura porta ``meta.cover_form`` (il ruolo
   resta ``over_cover``: nessuna migrazione).

Finti: ``FakeDB`` del servizio (stesse chiavi del vero, gia' usato dai test del
freno), ``F.event_info`` vero su un payload del feed, oggetti veri dell'engine.
"""
from __future__ import annotations

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import feed as F
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_feed import payload
from Betfair.mike.tests.test_mike_service import FakeDB
from test_mike_engine import KO, book, fill, snap


def _ctx_scoperto() -> E.MatchCtx:
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", entry_price_initial=1.50)
    ctx.legs.append(fill(E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                               side="back", price=1.50, size=10.0)))
    return ctx


def _ev():
    return {"event_id": "E1", "markets": {E.MARKET_OU35: {"market_id": "1.35"},
                                          E.MARKET_OU45: {"market_id": "1.45"}}}


def _foto(t, *, u45_status="OPEN", o45_status="OPEN"):
    return snap(t, u35=book(1.35, inplay=True),
                o45=book(6.6, inplay=True, status=o45_status),
                u45=book(1.17, inplay=True, status=u45_status),
                inplay=True, minute=20, goals=0)


def _params(forma):
    return dict(C.merge_params(None), cover_form=forma)


def test_forma_banca_la_sospensione_dell_under45_si_dice():
    db = FakeDB()
    ctx = _ctx_scoperto()
    p = _params(E.COVER_LAY_U45)
    S._sorveglia_mercato_copertura(db=db, ctx=ctx, snap=_foto(KO), now_ts=KO, ev=_ev(), params=p)
    assert db.kinds() == []
    # SOLO l'Under 4,5 sospeso (l'Over aperto): e' il libro della copertura-banca
    S._sorveglia_mercato_copertura(db=db, ctx=ctx, snap=_foto(KO + 5, u45_status="SUSPENDED"),
                                   now_ts=KO + 5, ev=_ev(), params=p)
    sosp = [pl for k, pl, _ in db.activity if k == "mercato_sospeso"]
    assert len(sosp) == 1
    assert sosp[0]["selezione"] == E.SEL_UNDER and "Under 4.5 (banca)" in sosp[0]["nota"]


def test_forma_di_prima_guarda_l_over_come_prima():
    db = FakeDB()
    ctx = _ctx_scoperto()
    p = _params(E.COVER_BACK_O45)
    S._sorveglia_mercato_copertura(db=db, ctx=ctx, snap=_foto(KO), now_ts=KO, ev=_ev(), params=p)
    S._sorveglia_mercato_copertura(db=db, ctx=ctx, snap=_foto(KO + 5, u45_status="SUSPENDED"),
                                   now_ts=KO + 5, ev=_ev(), params=p)
    assert db.kinds() == []                       # l'Under non e' il suo libro
    S._sorveglia_mercato_copertura(db=db, ctx=ctx, snap=_foto(KO + 9, o45_status="SUSPENDED"),
                                   now_ts=KO + 9, ev=_ev(), params=p)
    sosp = [pl for k, pl, _ in db.activity if k == "mercato_sospeso"]
    assert len(sosp) == 1 and sosp[0]["selezione"] == E.SEL_OVER
    assert "mercato della copertura Over 4.5 non operabile" in sosp[0]["nota"]


def test_una_copertura_gia_sul_book_decide_il_libro():
    """Al cambio di forma: la punta Over vecchia ancora viva si sorveglia
    sull'Over anche con la forma nuova scelta."""
    ctx = _ctx_scoperto()
    ctx.state = "LIVE_COVER_PENDING"
    ctx.legs.append(E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER,
                          side="back", price=6.6, size=2.26, ref="over_cover-0-2"))
    assert S._selezione_copertura(ctx, _params(E.COVER_LAY_U45)) == E.SEL_OVER
    assert S._selezione_copertura(_ctx_scoperto(), _params(E.COVER_LAY_U45)) == E.SEL_UNDER
    assert S._selezione_copertura(_ctx_scoperto(), None) == E.SEL_OVER


def test_la_riga_della_copertura_porta_la_sua_forma():
    info = F.event_info("E1", payload(inplay=True, minute=20, sh=1, sa=0))
    p = C.merge_params(None)
    banca = E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_UNDER, side="lay",
                  price=1.20, size=12.63, ref="over_cover-0-2")
    punta = E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER, side="back",
                  price=6.6, size=2.26, ref="over_cover-0-3")
    rb = S._trade_row(info, banca, "paper", p, 20, "1-0")
    rp = S._trade_row(info, punta, "paper", p, 20, "1-0")
    assert rb["meta"]["cover_form"] == E.COVER_LAY_U45 and rb["strategy"] == "over_cover"
    assert rb["side"] == "lay" and rb["liability"] == round(12.63 * 0.20, 2)
    assert rp["meta"]["cover_form"] == E.COVER_BACK_O45
    ingresso = E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                     side="back", price=1.5, size=10.0, ref="under_entry-0-1")
    assert "cover_form" not in S._trade_row(info, ingresso, "paper", p, 0, None)["meta"]
