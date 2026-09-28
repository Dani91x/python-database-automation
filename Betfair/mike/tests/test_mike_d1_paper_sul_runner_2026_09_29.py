"""D1 (29/09) - MIKE PAPER SULLA STRADA VERA: il RUNNER esegue, Mike legge.

Ordine dell'utente: «il paper deve essere lo specchio del live per tutti i
bot». Qui si provano i pezzi del blocco 1 che i test di ciclo non sollecitano:
  * prezzi non vivi = nessun ordine in PAPER E IN LIVE (decisione del 28/09);
  * taker paper senza nessun esito dal runner: NON eseguito (mai inventato);
  * lay appoggiata paper: stesso ordine del live (lay, prezzo, size, niente
    FOK, LAPSE), runner giu' = nessuna riga;
  * annullo paper sul runner (anche prima di conoscere il bet_id);
  * la riconciliazione paper non chiude per deduzione una riga del runner;
  * alla riapertura dopo una sospensione, una lay ancora viva sul runner si
    annulla li' e si legge l'esito vero.
Finti: ``DbMemoria`` del banco comune (le firme di ``mike/db.py``), ``EventInfo``
e ``Book`` di produzione, runner finto sul protocollo vero (``runner_finto``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_loop_taker_2026_09_16 import EVENTO, db_vuoto, info_vera
from Betfair.omega.omega_market import PlaceResult
from Betfair.safe_strategy import execution as X

ORA = datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _freni_aperti(monkeypatch):
    monkeypatch.setattr(X, "_freno_aperture", lambda: None)
    monkeypatch.setattr(X, "_live_brake", lambda: None)
    monkeypatch.setattr(S, "_freno_aperture_rest", lambda: None)
    monkeypatch.setattr(S, "mike_live_abilitato", lambda: True)

    def _vietato(*_a, **_k):
        raise AssertionError("accesso al database vero da un test")
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", _vietato)


def _params(**kw: Any) -> Dict[str, Any]:
    p = dict(C.merge_params(None))
    p.update(kw)
    return p


def _book(**kw: Any) -> E.Book:
    base = dict(status="OPEN", best_back=1.53, back_size=100.0, best_lay=1.55,
                lay_size=100.0, inplay=True)
    base.update(kw)
    return E.Book(**base)


def _green(ref: str = "ko_green-0-3") -> E.Leg:
    return E.Leg(role="ko_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                 price=1.48, size=10.14, ref=ref, cycle_no=0, placed_at=ORA.timestamp())


def _taker(ref: str = "over_cover-1-2") -> E.Leg:
    return E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER, side="back",
                 price=1.52, size=3.0, ref=ref, cycle_no=1, placed_at=ORA.timestamp())


# ---------------------------------------------------------------------------
# 4a - prezzi non vivi: nessun ordine, identico in paper e in live
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["paper", "live"])
def test_feed_stantio_nessun_ordine_in_entrambi_i_modi(mode, monkeypatch, runner):
    chiamate: List[Dict[str, Any]] = []
    monkeypatch.setattr(X, "place", lambda **kw: chiamate.append(kw))
    db = db_vuoto()
    leg = _taker()
    esito = S.execute_place(db=db, market=SimpleNamespace(), info=info_vera(), leg=leg,
                            book=_book(), mode=mode, params=_params(), now=ORA, dry=False,
                            feed_fresh=False)
    assert esito == "cancelled" and chiamate == [] and runner.comandi == []
    assert any(k == "no_fill" and p.get("reason") == "feed_stantio" and p.get("mode") == mode
               for k, p, _e in db.attivita), db.attivita


# ---------------------------------------------------------------------------
# taker paper: il runner non dice niente
# ---------------------------------------------------------------------------
def test_taker_senza_esito_dal_runner_non_e_eseguito(runner):
    runner.trattieni = True
    db = db_vuoto()
    leg = _taker()
    ctx = E.MatchCtx(legs=[leg])
    esito = S.execute_place(db=db, market=SimpleNamespace(), info=info_vera(), leg=leg,
                            book=_book(), mode="paper", params=_params(), now=ORA, dry=False,
                            feed_fresh=True, ctx=ctx)
    assert esito == "pending" and leg.status == "pending"
    tardi = ORA.timestamp() + S._SCADENZA_TAKER_PAPER_S + 1
    S._segui_ordini_paper_su_runner(db=db, ctx=ctx, ev={"event_id": EVENTO}, now_ts=tardi,
                                    params=_params())
    assert leg.status == "cancelled" and leg.matched == 0.0
    riga = db.trades_for_event(EVENTO)[-1]
    assert riga["status"] == "error" and riga["meta"]["reason"] == "runner_senza_esito"


# ---------------------------------------------------------------------------
# lay appoggiata paper: stesso ordine del live
# ---------------------------------------------------------------------------
def _piazza_paper(db, leg, ctx=None):
    S._piazza_resting_paper(db=db, market=SimpleNamespace(), info=info_vera(), leg=leg,
                            params=_params(), minuto=1, score="0-0", chiude=77, motivo=None,
                            ev={"event_id": EVENTO}, now=ORA, ctx=ctx)


def test_lay_appoggiata_paper_e_lo_stesso_ordine_del_live(runner):
    # il LIVE: cosa manda _piazza_resting_live a Betfair
    live: List[Dict[str, Any]] = []

    def place_order_live(**kw):
        live.append(kw)
        return PlaceResult(ok=True, order_status="EXECUTABLE", bet_id="B1",
                           size_matched=0.0, avg_price_matched=None, raw={})
    S._piazza_resting_live(db=db_vuoto(), market=SimpleNamespace(place_order_live=place_order_live),
                           info=info_vera(), leg=_green(), mode="live", params=_params(),
                           minuto=1, score="0-0", chiude=77, motivo=None,
                           ev={"event_id": EVENTO})
    # il PAPER: cosa manda al runner
    db = db_vuoto()
    _piazza_paper(db, _green())
    c = runner.comandi[-1]
    assert (c["side"], c["price"], c["size"]) == ("LAY", live[0]["price"], live[0]["size"])
    assert live[0]["fill_or_kill"] is False and c["time_in_force"] is None
    assert c["persistence"] == "LAPSE"
    assert c["market_id"] == str(live[0]["market_id"])
    assert c["selection_id"] == int(live[0]["selection_id"])
    riga = db.trades_for_event(EVENTO)[-1]
    assert riga["status"] == "pending" and riga["meta"]["canale_ref"] == c["ref"]


def test_lay_appoggiata_paper_runner_giu_nessuna_riga(runner):
    runner.collegato = False
    db = db_vuoto()
    leg = _green()
    _piazza_paper(db, leg)
    assert leg.status == "cancelled" and db.trades_for_event(EVENTO) == []
    assert runner.comandi == []


# ---------------------------------------------------------------------------
# annulli paper sul runner
# ---------------------------------------------------------------------------
def test_annullo_paper_arriva_al_runner(runner):
    db = db_vuoto()
    leg = _green()
    ctx = E.MatchCtx(legs=[leg])
    _piazza_paper(db, leg, ctx)
    S._segui_ordini_paper_su_runner(db=db, ctx=ctx, ev={"event_id": EVENTO},
                                    now_ts=ORA.timestamp(), params=_params())
    assert db.trades_for_event(EVENTO)[-1]["bet_id"], "il bet_id del runner e' sulla riga"
    esito = S._mark_trade_cancelled(db, EVENTO, leg, "cancelled_by_engine",
                                    market=SimpleNamespace())
    annulli = [c for c in runner.comandi if c["azione"] == "cancel"]
    assert len(annulli) == 1 and annulli[0]["ref"].startswith("mike-c")
    assert esito == "cancelled" and leg.status == "cancelled"
    assert db.trades_for_event(EVENTO)[-1]["status"] == "error"


def test_annullo_prima_del_bet_id_resta_in_verifica_e_parte_appena_noto(runner):
    runner.trattieni = True
    db = db_vuoto()
    leg = _green()
    ctx = E.MatchCtx(legs=[leg])
    _piazza_paper(db, leg, ctx)
    esito = S._mark_trade_cancelled(db, EVENTO, leg, "cancelled_by_engine",
                                    market=SimpleNamespace())
    assert esito == E.STATUS_RECONCILE, "mai «cancelled» su un ordine che potrebbe vivere"
    assert [c for c in runner.comandi if c["azione"] == "cancel"] == []
    runner.trattieni = False
    runner.rilascia()
    S._segui_ordini_paper_su_runner(db=db, ctx=ctx, ev={"event_id": EVENTO},
                                    now_ts=ORA.timestamp(), params=_params())
    assert [c for c in runner.comandi if c["azione"] == "cancel"], "annullo mai partito"
    assert leg.status == "cancelled"


def test_riconciliazione_paper_non_chiude_per_deduzione_una_riga_del_runner(runner):
    runner.trattieni = True
    db = db_vuoto()
    leg = _green()
    ctx = E.MatchCtx(legs=[leg])
    _piazza_paper(db, leg, ctx)
    leg.status = E.STATUS_RECONCILE
    S._reconcile_unknown(db, SimpleNamespace(), EVENTO, ctx, "paper", ORA)
    assert db.trades_for_event(EVENTO)[-1]["status"] == "pending"
    runner.trattieni = False
    runner.rilascia()
    runner.abbina(runner.comandi[-1]["ref"])
    S._segui_ordini_paper_su_runner(db=db, ctx=ctx, ev={"event_id": EVENTO},
                                    now_ts=ORA.timestamp(), params=_params())
    assert leg.status == "open" and leg.matched == pytest.approx(10.14)


def test_parziale_poi_scadenza_la_parte_abbinata_resta_posizione(runner):
    db = db_vuoto()
    leg = _green()
    ctx = E.MatchCtx(legs=[leg])
    _piazza_paper(db, leg, ctx)
    ref = runner.comandi[-1]["ref"]
    runner.abbina(ref, size=4.0, prezzo=1.47)
    runner.scadi(ref)
    S._segui_ordini_paper_su_runner(db=db, ctx=ctx, ev={"event_id": EVENTO},
                                    now_ts=ORA.timestamp(), params=_params())
    assert leg.status == "open" and leg.matched == pytest.approx(4.0)
    assert leg.avg_price == pytest.approx(1.47)
    riga = db.trades_for_event(EVENTO)[-1]
    assert riga["status"] == "open" and riga["size"] == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# la porta di Mike: il comando che esce e' di Mike, sempre
# ---------------------------------------------------------------------------
def test_adatta_comando_annullo_col_ref_di_un_altro_attore_diventa_di_mike():
    from Betfair.mike import porta_ordini as MP
    from Betfair.safe_strategy import porta_ordini as PO

    c = PO.costruisci_comando(ref=PO.ref_annullo("777", attore="safe"), attore="safe",
                              azione="cancel", mode="paper", market_id="1.2", bet_id="777")
    d = MP.adatta_comando(c)
    assert d["ref"] == "mike-c777" and d["attore"] == "mike" and d["strategy_ref"] == "mike"
    with pytest.raises(ValueError):
        MP.adatta_comando({**PO.costruisci_comando(
            ref="safe-t9", attore="safe", azione="place", mode="paper", market_id="1.2",
            selection_id=1, side="lay", price=1.5, size=2.0)})


# ---------------------------------------------------------------------------
# riapertura dopo una sospensione: la lay viva sul runner si annulla li'
# ---------------------------------------------------------------------------
def test_riapertura_lay_ancora_viva_sul_runner_si_annulla_e_si_legge(runner):
    db = db_vuoto()
    leg = _green()
    ctx = E.MatchCtx(legs=[leg])
    _piazza_paper(db, leg, ctx)
    S._segui_ordini_paper_su_runner(db=db, ctx=ctx, ev={"event_id": EVENTO},
                                    now_ts=ORA.timestamp(), params=_params())
    par = _params()
    sosp = E.Snapshot(now=ORA.timestamp() + 100, ko_at=ORA.timestamp(),
                      books={(E.MARKET_OU35, E.SEL_UNDER): _book(status="SUSPENDED")},
                      inplay=True)
    riap = E.Snapshot(now=ORA.timestamp() + 105, ko_at=ORA.timestamp(),
                      books={(E.MARKET_OU35, E.SEL_UNDER): _book()}, inplay=True)
    ev = {"event_id": EVENTO}
    S._sorveglia_sospensione(db=db, market=SimpleNamespace(), ctx=ctx, snap=sosp,
                             params=par, mode="paper", now_ts=ORA.timestamp() + 100, ev=ev)
    S._sorveglia_sospensione(db=db, market=SimpleNamespace(), ctx=ctx, snap=riap,
                             params=par, mode="paper", now_ts=ORA.timestamp() + 105, ev=ev)
    assert [c for c in runner.comandi if c["azione"] == "cancel"], "la lay e' rimasta viva"
    assert ctx.riapertura["esiti"]["ko_green-0-3"] == "scaduto"
    assert leg.status == "cancelled"
