"""26/09/2026 - R7: il PAPER di Mike riempie AL BEST del feed, non al prezzo limite.

Reperto del test e2e (AUDIT_2026-09-25/e2e_fase2/ADMIN26_ORDINI_SCHEDE.md, R7):
trade 5073 back limite 5,5 col best back 5,8 -> paper registrava 5,5; 5074
2,84 vs 2,9; 5075 1,88 vs 1,9. In LIVE un back a limite 5,5 col best 5,8 si
abbina a 5,8 (miglioramento di prezzo): il paper era pessimista di 2-3 tick.
Causa: ``service.execute_place`` passava ``ladder=()`` a ``execution.place``,
che senza ladder riempie a ``best_price=price`` (il limite).

Si prova con le funzioni VERE (``execute_place`` -> ``execution.place`` ->
``omega_engine.paper_fill``), il DB in memoria del banco comune e l'EventInfo
vera. Il live NON cambia: stesso limite, nessuna ladder (spia su ``X.place``).
ASCII-only.
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


def _esegui(leg: E.Leg, book: E.Book, mode: str = "paper") -> str:
    return S.execute_place(db=db_vuoto(), market=SimpleNamespace(), info=info_vera(),
                           leg=leg, book=book, mode=mode, params=_params(), now=ORA,
                           dry=False, minute=60, score="1-1", feed_fresh=True)


def test_back_paper_al_best_migliore_del_limite() -> None:
    # 5073: limite 5,5, best back 5,8 -> abbinato a 5,8 come in live
    leg = _gamba("back", 5.5, 2.0)
    assert _esegui(leg, _book(best_back=5.8)) == "open"
    assert leg.avg_price == pytest.approx(5.8)
    assert leg.matched == pytest.approx(2.0)


@pytest.mark.parametrize("limite,best", [(2.84, 2.9), (1.88, 1.9)])
def test_back_paper_casi_5074_5075(limite: float, best: float) -> None:
    leg = _gamba("back", limite, 3.0)
    assert _esegui(leg, _book(best_back=best, best_lay=best + 0.1)) == "open"
    assert leg.avg_price == pytest.approx(best)


def test_lay_paper_al_best_migliore_del_limite() -> None:
    # lay limite 3,0 col best lay 2,9 -> abbinato a 2,9
    leg = _gamba("lay", 3.0, 2.0, role="over_close")
    assert _esegui(leg, _book(best_back=2.86, best_lay=2.9)) == "open"
    assert leg.avg_price == pytest.approx(2.9)


def test_best_peggiore_del_limite_nessun_fill() -> None:
    # back limite 6,0 col best back 5,8: in live non si abbina (resta/lapse)
    leg = _gamba("back", 6.0, 2.0)
    assert _esegui(leg, _book(best_back=5.8)) == "cancelled"
    assert leg.matched == 0.0


def test_liquidita_del_livello_cappa_la_size() -> None:
    leg = _gamba("back", 5.5, 10.0)
    assert _esegui(leg, _book(best_back=5.8, back_size=3.0)) == "open"
    assert leg.matched == pytest.approx(3.0)
    assert leg.avg_price == pytest.approx(5.8)


def test_live_invariato_limite_e_nessuna_ladder(monkeypatch: pytest.MonkeyPatch) -> None:
    chiamate: List[Dict[str, Any]] = []

    def spia(**kw: Any) -> X.PlaceOutcome:
        chiamate.append(kw)
        return X.PlaceOutcome("error", None, 0.0, None, "spia")
    monkeypatch.setattr(X, "place", spia)
    _esegui(_gamba("back", 5.5, 2.0), _book(best_back=5.8), mode="live")
    assert len(chiamate) == 1
    assert chiamate[0]["price"] == 5.5 and chiamate[0]["ladder"] == ()
    assert chiamate[0]["best_size"] == 100.0


def test_paper_passa_il_livello_del_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    chiamate: List[Dict[str, Any]] = []

    def spia(**kw: Any) -> X.PlaceOutcome:
        chiamate.append(kw)
        return X.PlaceOutcome("error", None, 0.0, None, "spia")
    monkeypatch.setattr(X, "place", spia)
    _esegui(_gamba("back", 5.5, 2.0), _book(best_back=5.8, back_size=40.0))
    assert chiamate[0]["price"] == 5.5                      # il limite resta il limite
    assert chiamate[0]["ladder"] == ((5.8, 40.0),)          # il best del feed
