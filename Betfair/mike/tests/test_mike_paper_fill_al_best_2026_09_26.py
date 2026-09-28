"""Mike PAPER: chi esegue l'ordine (26/09 R7, riscritto il 29/09 da D1).

26/09 (R7): il paper di Mike riempiva IN CASA al best del feed (ladder passata a
``execution.place``). 29/09 (D1, ordine dell'utente «il paper deve essere lo
specchio del live per tutti i bot»): il fill in casa NON esiste piu'. L'ordine
paper di Mike va al RUNNER sul canale di comando (``Betfair/mike/porta_ordini``):
stesso limite, stesso lato, stessa size (cappata alla liquidita' come il live),
FOK come il REST del live; l'abbinamento (e il suo prezzo, anche migliore del
limite) lo dice il runner. Runner giu' = non eseguito, mai un fill in casa.

Funzioni VERE: ``execute_place`` -> ``execution.place`` ->
``execution._place_via_canale`` -> ``VistaMike`` -> runner finto che valida col
``motore_ordini.valida_comando`` di produzione (``tests/runner_finto.py``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_loop_taker_2026_09_16 import db_vuoto, info_vera
from Betfair.safe_strategy import execution as X

ORA = datetime(2026, 9, 26, 9, 30, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _freni_aperti(monkeypatch):
    monkeypatch.setattr(X, "_freno_aperture", lambda: None)
    monkeypatch.setattr(X, "_live_brake", lambda: None)


def _params() -> Dict[str, Any]:
    return dict(C.merge_params(None))


def _book(**kw: Any) -> E.Book:
    base = dict(status="OPEN", best_back=5.8, back_size=100.0, best_lay=6.0,
                lay_size=100.0, inplay=True)
    base.update(kw)
    return E.Book(**base)


def _gamba(side: str, price: float, size: float, role: str = "over_cover") -> E.Leg:
    return E.Leg(role=role, market=E.MARKET_OU45, selection=E.SEL_OVER, side=side,
                 price=price, size=size, ref="t-r7")


def _esegui(leg: E.Leg, book: E.Book, mode: str = "paper", db: Any = None) -> str:
    return S.execute_place(db=db if db is not None else db_vuoto(), market=SimpleNamespace(),
                           info=info_vera(), leg=leg, book=book, mode=mode,
                           params=_params(), now=ORA, dry=False, minute=60, score="1-1",
                           feed_fresh=True)


def test_il_comando_paper_e_quello_del_live(runner) -> None:
    leg = _gamba("back", 5.5, 10.0)
    assert _esegui(leg, _book(best_back=5.8, back_size=3.0)) == "open"
    c = runner.comandi[-1]
    assert c["attore"] == "mike" and c["strategy_ref"] == "mike" and c["mode"] == "paper"
    assert c["azione"] == "place" and c["side"] == "BACK" and c["price"] == 5.5
    assert c["size"] == 3.0, "size cappata alla liquidita' come il live"
    assert c["time_in_force"] == "FILL_OR_KILL" and c["persistence"] == "LAPSE"
    assert c["ref"].startswith("mike-t") and c["origine"]["tabella"] == "mike_trades"


def test_il_prezzo_lo_dice_il_RUNNER(runner) -> None:
    # 5073: limite 5,5, il runner abbina a 5,8 (miglioramento di prezzo)
    runner.prezzo_taker = 5.8
    leg = _gamba("back", 5.5, 2.0)
    assert _esegui(leg, _book(best_back=5.8)) == "open"
    assert leg.avg_price == pytest.approx(5.8) and leg.matched == pytest.approx(2.0)


def test_best_peggiore_del_limite_nessun_ordine(runner) -> None:
    leg = _gamba("back", 6.0, 2.0)
    assert _esegui(leg, _book(best_back=5.8)) == "cancelled"
    assert runner.comandi == []


def test_FOK_ucciso_dal_runner_nessuna_posizione(runner) -> None:
    runner.rifiuta_fok = True
    db = db_vuoto()
    leg = _gamba("back", 5.5, 2.0)
    assert _esegui(leg, _book(), db=db) == "cancelled"
    assert leg.matched == 0.0
    righe = db.trades_for_event(info_vera().event_id)
    assert righe[-1]["status"] == "error"


def test_runner_giu_NESSUN_fill_in_casa_e_nessuna_riga(runner) -> None:
    runner.collegato = False
    db = db_vuoto()
    leg = _gamba("back", 5.5, 2.0)
    assert _esegui(leg, _book(), db=db) == "cancelled"
    assert db.trades_for_event(info_vera().event_id) == []
    assert runner.comandi == []


def test_chiusura_con_canale_caduto_all_invio_NESSUN_fill_in_casa(runner) -> None:
    """La finestra di corsa: disponibile al controllo, invio non uscito. Per una
    CHIUSURA ``execution`` ripiega sul percorso di sempre: la ladder a
    liquidita' zero impedisce il fill in casa -> dichiarato non eseguito."""
    runner.perdi_invio = True
    db = db_vuoto()
    leg = _gamba("lay", 3.0, 2.0, role="over_close")
    assert _esegui(leg, _book(best_back=2.86, best_lay=2.9), db=db) == "cancelled"
    assert leg.matched == 0.0
    assert db.trades_for_event(info_vera().event_id)[-1]["status"] == "error"


def test_live_invariato_limite_nessuna_ladder_nessuna_porta(monkeypatch: pytest.MonkeyPatch) -> None:
    chiamate: List[Dict[str, Any]] = []

    def spia(**kw: Any) -> X.PlaceOutcome:
        chiamate.append(kw)
        return X.PlaceOutcome("error", None, 0.0, None, "spia")
    monkeypatch.setattr(X, "place", spia)
    _esegui(_gamba("back", 5.5, 2.0), _book(best_back=5.8), mode="live")
    assert len(chiamate) == 1
    assert chiamate[0]["price"] == 5.5 and chiamate[0]["ladder"] == ()
    assert chiamate[0]["best_size"] == 100.0 and "porta" not in chiamate[0]


def test_paper_porta_del_runner_e_ladder_senza_liquidita(monkeypatch: pytest.MonkeyPatch) -> None:
    chiamate: List[Dict[str, Any]] = []

    def spia(**kw: Any) -> X.PlaceOutcome:
        chiamate.append(kw)
        return X.PlaceOutcome("error", None, 0.0, None, "spia")
    monkeypatch.setattr(X, "place", spia)
    _esegui(_gamba("back", 5.5, 2.0), _book(best_back=5.8, back_size=40.0))
    assert chiamate[0]["price"] == 5.5
    assert chiamate[0]["ladder"] == ((0.0, 0.0),), "nessuna liquidita' in casa"
    assert getattr(chiamate[0]["porta"], "via_canale", False) is True
    assert chiamate[0]["porta"].attore == "mike"
