"""02/10 - FEED STANTIO: la stessa gamba respinta NON si ripropone a ogni giro.

Regressione accertata il 02/10 (scenario ``lettura-dati-ko`` del banco, partita
35760084): da ``aa5749a`` («bot MAI ciechi», 01/10) lo scanner TIENE la riga
della partita anche quando la lettura dei dati cade, quindi Mike continua a
decidere su un feed STANTIO. In PRE_OPEN il motore proponeva a ogni giro la
stessa ``under_green lay 10.12 @ 1.69``, il servizio la respingeva per
``feed_stantio``, e il giro dopo si ricominciava: 373 proposte identiche contro
6 ordini veri (P1, P2, P3 del banco). Il bot reggeva solo grazie al freno a valle.

Correzione (solo MIKE, l'ordine «bot mai ciechi» non si tocca): il rifiuto per
feed stantio si scrive nel ctx (``_rifiutata``); finche' il feed resta stantio la
STESSA richiesta non si ripropone (``engine._tieni_a_feed_stantio``: il motore
TIENE con motivo esplicito, nessuna gamba nuova); al ritorno del feed la gamba
parte UNA volta. Nessuna condotta di strategia cambia: cosa e quando chiudere
restano quelli.

Finti: ``FakeDB``/``FakeMarket`` di ``test_mike_service`` (le firme di
``mike/db.py``), righe e payload di ``test_mike_feed`` (chiavi vere dello
scanner), runner finto sul protocollo vero, ``MatchCtx``/``Leg``/``Snapshot``
di produzione. File ASCII-only.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import service as SV
from Betfair.mike.tests.test_mike_feed import payload, row
from Betfair.mike.tests.test_mike_service import NOW, FakeDB, FakeMarket, legs, run, state

N_GIRI_STANTII = 12


def _greens(db) -> List[Dict[str, Any]]:
    return [l for l in legs(db) if l["role"] == "under_green"]


def _no_fill_stantio(db) -> List[Dict[str, Any]]:
    return [p for k, p, _ in db.activity if k == "no_fill" and p.get("reason") == "feed_stantio"]


def _feed_stantio(db, quando):
    """Riga vecchia di 10 minuti E scanner muto: e' il feed stantio di
    ``feed.feed_fresh`` (riga > 15 s e scanner > 30 s), quello della lettura KO."""
    vecchio = quando - timedelta(minutes=10)
    db.scanner = {"updated_at": vecchio.isoformat(), "payload": {}}
    return [row(payload(), updated=vecchio)]


def _feed_fresco(db, quando, **kw):
    db.scanner = {"updated_at": quando.isoformat(), "payload": {}}
    return [row(payload(**kw), updated=quando)]


# ---------------------------------------------------------------------------
# 1 - il caso del replay: PRE_OPEN, lay appoggiata di green, feed stantio
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["paper", "live"])
def test_green_appoggiata_respinta_a_feed_stantio_non_si_ripropone(runner, monkeypatch, mode):
    piazzate: List[Dict[str, Any]] = []
    monkeypatch.setattr(SV, "_piazza_resting_live", lambda **kw: piazzate.append(kw))
    monkeypatch.setattr(SV, "_piazza_resting_paper", lambda **kw: piazzate.append(kw))
    db = FakeDB(params={"stake": 10}, mode=mode)
    mk = FakeMarket()
    if mode == "live":
        from Betfair.omega.omega_market import PlaceResult
        from Betfair.safe_strategy import execution as XX
        monkeypatch.setattr(XX, "_live_brake", lambda: None)
        mk.place_order_live = lambda **kw: PlaceResult(
            ok=True, order_status="EXECUTION_COMPLETE", bet_id="B1", size_matched=kw["size"],
            avg_price_matched=kw["price"], raw={})
    run(db, mk, NOW, _feed_fresco(db, NOW))
    assert legs(db)[0]["status"] == "open", "precondizione: ingresso abbinato"
    # N giri di feed stantio con la posizione aperta e nessuna green sul book
    for i in range(N_GIRI_STANTII):
        quando = NOW + timedelta(seconds=2 + 2 * i)
        run(db, mk, quando, _feed_stantio(db, quando))
    assert piazzate == [], "lay appoggiata inviata su prezzi non vivi"
    # oggi: N proposte e N rifiuti; atteso: UNA proposta, UN rifiuto
    assert len(_greens(db)) == 1, [g["status"] for g in _greens(db)]
    assert len(_no_fill_stantio(db)) == 1
    assert state(db) == "PRE_OPEN"
    # il feed torna fresco: la gamba parte UNA volta
    ritorno = NOW + timedelta(seconds=2 + 2 * N_GIRI_STANTII)
    run(db, mk, ritorno, _feed_fresco(db, ritorno))
    assert len(piazzate) == 1, piazzate
    assert len(_greens(db)) == 2
    # e non riparte di nuovo al giro dopo (e' sul book)
    dopo = ritorno + timedelta(seconds=2)
    run(db, mk, dopo, _feed_fresco(db, dopo))
    assert len(piazzate) == 1 and len(_greens(db)) == 2


# ---------------------------------------------------------------------------
# 2 - il ramo TAKER (execute_place): stessa regola
# ---------------------------------------------------------------------------
def test_green_taker_respinta_a_feed_stantio_non_si_ripropone(runner):
    db = FakeDB(params={"stake": 10, "pre_exit_mode": "taker"})
    mk = FakeMarket()
    run(db, mk, NOW, _feed_fresco(db, NOW))
    assert legs(db)[0]["status"] == "open", "precondizione: ingresso abbinato"
    n_comandi = len(runner.comandi)
    # il lay al target (2 tick): il ramo taker propone la chiusura
    for i in range(N_GIRI_STANTII):
        quando = NOW + timedelta(seconds=2 + 2 * i)
        vecchio = quando - timedelta(minutes=10)
        db.scanner = {"updated_at": vecchio.isoformat(), "payload": {}}
        run(db, mk, quando, [row(payload(u35=(1.46, 1.48, 30.0, 25.0)), updated=vecchio)])
    assert len(runner.comandi) == n_comandi, "ordine inviato su prezzi non vivi"
    assert len(_greens(db)) == 1, [g["status"] for g in _greens(db)]
    assert len(_no_fill_stantio(db)) == 1
    # ritorno del feed: parte UNA volta
    ritorno = NOW + timedelta(seconds=2 + 2 * N_GIRI_STANTII)
    run(db, mk, ritorno, _feed_fresco(db, ritorno, u35=(1.46, 1.48, 30.0, 25.0)))
    assert len(runner.comandi) == n_comandi + 1
    assert len(_greens(db)) == 2


# ---------------------------------------------------------------------------
# 3 - il motore da solo: chi tiene, chi passa
# ---------------------------------------------------------------------------
def _ctx_pre_open() -> E.MatchCtx:
    ingresso = E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                     side="back", price=1.50, size=10.0, ref="under_entry-0-1", cycle_no=0,
                     placed_at=NOW.timestamp(), status="open", matched=10.0, avg_price=1.50)
    return E.MatchCtx(state="PRE_OPEN", legs=[ingresso], entry_price_initial=1.50)


def _snap(*, fresco: bool, now: float) -> E.Snapshot:
    bk = E.Book(status="OPEN", best_back=1.50, back_size=30.0, best_lay=1.52, lay_size=25.0,
                inplay=False)
    return E.Snapshot(now=now, ko_at=(NOW + timedelta(minutes=30)).timestamp(),
                      books={(E.MARKET_OU35, E.SEL_UNDER): bk}, feed_fresh=fresco,
                      order_fresh=fresco)


def _respingi_come_il_servizio(ctx: E.MatchCtx, d: E.Decision, now: float) -> None:
    """Quello che fa ``service`` col feed stantio: la gamba nasce e viene
    respinta (``cancelled``) con il rifiuto scritto nel ctx."""
    for leg in E.apply_decision(ctx, d, now):
        leg.status = "cancelled"
        SV._rifiutata(ctx, leg, E.MOTIVO_FEED_STANTIO)


def test_motore_tiene_a_feed_stantio_e_riparte_una_volta():
    p = dict(C.merge_params(None))
    ctx = _ctx_pre_open()
    t0 = NOW.timestamp()
    proposte = 0
    motivi = []
    for i in range(N_GIRI_STANTII):
        d = E.decide(ctx, _snap(fresco=False, now=t0 + i), p)
        proposte += sum(1 for a in d.actions if a.kind == "place")
        motivi.append(d.reason)
        _respingi_come_il_servizio(ctx, d, t0 + i)
    assert proposte == 1, motivi
    assert ctx.state == "PRE_OPEN"
    assert "feed stantio" in motivi[-1] and "under_green" in motivi[-1], motivi[-1]
    d = E.decide(ctx, _snap(fresco=True, now=t0 + 100), p)
    assert [a.role for a in d.actions if a.kind == "place"] == ["under_green"]


def test_rifiuto_per_feed_stantio_non_blocca_a_feed_fresco():
    """Il rifiuto per feed stantio NON e' una risposta del mercato: col feed
    fresco ``tentativo_gia_rifiutato`` non lo conta."""
    ctx = _ctx_pre_open()
    a = E._place("under_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.48, 10.14)
    leg = E.Leg(role=a.role, market=a.market, selection=a.selection, side=a.side,
                price=a.price, size=a.size, ref="under_green-0-2", cycle_no=0)
    SV._rifiutata(ctx, leg, E.MOTIVO_FEED_STANTIO)
    assert E.tentativo_gia_rifiutato(ctx, a) is None
    assert E.gia_respinta_a_feed_stantio(ctx, a) is not None
    # un rifiuto VERO del mercato resta un rifiuto
    SV._rifiutata(ctx, leg, "prezzo non disponibile (1.5)")
    assert E.tentativo_gia_rifiutato(ctx, a) is not None
    assert E.gia_respinta_a_feed_stantio(ctx, a) is None


def test_una_richiesta_DIVERSA_a_feed_stantio_si_propone():
    """Prezzo o size diversi = domanda nuova: passa (e il servizio la respinge
    lui, una volta)."""
    p = dict(C.merge_params(None))
    ctx = _ctx_pre_open()
    leg = E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                price=1.47, size=10.2, ref="under_green-0-2", cycle_no=0)
    SV._rifiutata(ctx, leg, E.MOTIVO_FEED_STANTIO)
    d = E.decide(ctx, _snap(fresco=False, now=NOW.timestamp()), p)
    assert [a.role for a in d.actions if a.kind == "place"] == ["under_green"]


def test_tenere_non_consuma_aggiornamenti_ne_tentativi():
    """Tolta l'unica gamba, lo stato resta quello di adesso e gli aggiornamenti
    della decisione NON si applicano (un ``attempts + 1`` consumerebbe i
    tentativi di chiusura senza nessun ordine)."""
    ctx = _ctx_pre_open()
    a = E._place("under_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.48, 10.14)
    leg = E.Leg(role=a.role, market=a.market, selection=a.selection, side=a.side,
                price=a.price, size=a.size, ref="x", cycle_no=0)
    SV._rifiutata(ctx, leg, E.MOTIVO_FEED_STANTIO)
    d = E.Decision("PRE_GREEN_PENDING", [a], "green", updates={"attempts": 3})
    out = E._tieni_a_feed_stantio(ctx, d, _snap(fresco=False, now=NOW.timestamp()))
    assert out.actions == [] and out.state == "PRE_OPEN" and out.updates == {}
    # col feed fresco la decisione passa intatta
    assert E._tieni_a_feed_stantio(ctx, d, _snap(fresco=True, now=NOW.timestamp())) is d
