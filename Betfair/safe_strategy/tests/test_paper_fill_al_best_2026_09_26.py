"""26/09/2026 - R7: il fill PAPER dello strato condiviso (``execution.place``) al BEST.

Il contratto che Safe usa da sempre e che Mike ora rispetta (reperto R7 del
test e2e, AUDIT_2026-09-25/e2e_fase2/ADMIN26_ORDINI_SCHEDE.md):
  * con il livello del feed in ``ladder`` il fill paper avviene AL BEST del
    livello quando e' migliore del limite (back: best >= limite; lay: best <=
    limite), con la liquidita' del livello, come l'abbinamento vero di Betfair;
  * best peggiore del limite = nessun fill (``paper_no_fill``);
  * SENZA ladder il fill e' al prezzo passato (il limite): e' la trappola in cui
    cadeva Mike (``ladder=()``) - chi vuole il best deve dichiarare il livello.
Safe costruisce il livello con ``bot_service._paper_ladder`` dal feed.

``execution.py`` NON e' modificato da questo cantiere: questi test fissano il
contratto (falsificazione: togliere la ladder da ``paper_fill`` li fa rossi).
ASCII-only.
"""
from __future__ import annotations

import pytest

from Betfair.safe_strategy import execution as X
from test_execution import NOW, FakeDB, FakeMarket


def _place(side: str, price: float, ladder, size: float = 2.0, best_size=None):
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"                      # gate chiuso -> percorso paper legacy
    tid = db.insert_trade({"event_id": "1.1", "status": "pending", "side": side})
    out = X.place(db=db, market=mk, mode="paper", event_id="1.1", market_id="m1",
                  selection_id=7, side=side, price=price, size=size,
                  best_size=best_size, ladder=ladder, client_ref=f"safe-t{tid}",
                  trade_id=tid, now=NOW, params={})
    assert mk.placed == [], "in paper non si tocca Betfair"
    return out


def test_back_al_best_migliore_del_limite() -> None:
    out = _place("back", 5.5, ((5.8, 100.0),), best_size=100.0)
    assert out.status == "open"
    assert out.price == pytest.approx(5.8)
    assert out.avg_price_matched == pytest.approx(5.8)
    assert out.esecuzione["price_richiesto"] == 5.5
    assert out.esecuzione["scorrimento_tick"] < 0        # meglio del chiesto, detto


def test_lay_al_best_migliore_del_limite() -> None:
    out = _place("lay", 3.0, ((2.9, 100.0),), best_size=100.0)
    assert out.status == "open" and out.price == pytest.approx(2.9)


@pytest.mark.parametrize("side,limite,best", [("back", 6.0, 5.8), ("lay", 2.8, 2.9)])
def test_best_peggiore_del_limite_nessun_fill(side: str, limite: float, best: float) -> None:
    out = _place(side, limite, ((best, 100.0),), best_size=100.0)
    assert out.status == "error" and out.fill_note.startswith("paper_no_fill")


def test_liquidita_del_livello() -> None:
    out = _place("back", 5.5, ((5.8, 3.0),), size=10.0, best_size=3.0)
    assert out.status == "open" and out.size == pytest.approx(3.0)
    assert out.price == pytest.approx(5.8)


def test_senza_ladder_il_fill_e_al_prezzo_passato() -> None:
    # la trappola di Mike fino al 26/09: nessun livello -> fill al limite
    out = _place("back", 5.5, (), best_size=100.0)
    assert out.status == "open" and out.price == pytest.approx(5.5)


def test_safe_costruisce_il_livello_dal_feed_e_riempie_al_best() -> None:
    from Betfair.safe_strategy import bot_service as BS

    lvl = BS._paper_ladder("back", {"back": 5.8, "back_size": 100.0, "lay": 6.0,
                                    "lay_size": 50.0}, None)
    assert lvl == ((5.8, 100.0),)
    out = _place("back", 5.5, lvl, best_size=None)
    assert out.status == "open" and out.price == pytest.approx(5.8)
