"""26/09/2026 - R7: il fill PAPER dello strato condiviso (``execution.place``) al BEST.

CANTIERE P (28/09) - QUESTO FILE E' STATO RISCRITTO.
Il 26/09 fissava il contratto del fill paper «di casa» di ``execution.place``
(a gate della coda chiuso): fill al best del livello del feed, liquidita' del
livello, nessun fill oltre il limite, fill al limite senza ladder. Ordine
dell'utente del 28/09 («deve essere lo specchio per tutti i bot»): quel fill
era istantaneo, senza bet delay e senza coda, dove il live va a Betfair; era
il difetto S3 della tabella di parita' di Safe. Il fill di casa non esiste
piu': un ordine paper vive solo sul runner, dove l'abbinamento AL BEST, la
liquidita', il limite e il FOK li fa il client simulato di flumine sul book
vero (certificato dal banco, ``trasporto_rapido`` R1/R3), non questo modulo.

I test di prima asserivano un fill che oggi sarebbe un BUG; qui si asserisce
che, per OGNUNO dei loro scenari, a runner giu' nessun fill nasce in casa e,
col runner, l'ordine parte identico (prezzo limite, size, FOK) verso di lui.
``bot_service._paper_ladder`` resta una funzione pura (nessuno la usa piu' per
piazzare): il suo contratto e' ancora collaudato.
ASCII-only.
"""
from __future__ import annotations

import pytest

from Betfair.safe_strategy import execution as X
from test_execution import NOW, FakeDB, FakeMarket

#: gli scenari del 26/09: (lato, limite, ladder, size, best_size)
SCENARI = [
    ("back", 5.5, ((5.8, 100.0),), 2.0, 100.0),     # best migliore del limite
    ("lay", 3.0, ((2.9, 100.0),), 2.0, 100.0),
    ("back", 6.0, ((5.8, 100.0),), 2.0, 100.0),     # best peggiore del limite
    ("lay", 2.8, ((2.9, 100.0),), 2.0, 100.0),
    ("back", 5.5, ((5.8, 3.0),), 10.0, 3.0),        # liquidita' del livello
    ("back", 5.5, (), 2.0, 100.0),                  # senza ladder
]


def _place(side, price, ladder, size, best_size, *, runner: bool):
    db, mk = FakeDB(), FakeMarket()
    if not runner:
        db.follow = "NONE"
    tid = db.insert_trade({"event_id": "1.1", "status": "pending", "side": side})
    out = X.place(db=db, market=mk, mode="paper", event_id="1.1", market_id="m1",
                  selection_id=7, side=side, price=price, size=size,
                  best_size=best_size, ladder=ladder, client_ref=f"safe-t{tid}",
                  trade_id=tid, now=NOW, params={})
    assert mk.placed == [], "in paper non si tocca Betfair"
    return out, db


@pytest.mark.parametrize("side,limite,ladder,size,best_size", SCENARI)
def test_a_runner_giu_nessun_fill_di_casa(side, limite, ladder, size, best_size) -> None:
    out, db = _place(side, limite, ladder, size, best_size, runner=False)
    assert out.status == "error" and out.fill_note.startswith("paper_senza_runner:")
    assert out.size == 0.0 and out.price is None and out.esecuzione is None
    assert db.queue == []


@pytest.mark.parametrize("side,limite,ladder,size,best_size", SCENARI)
def test_col_runner_l_ordine_parte_al_limite_col_fok(side, limite, ladder, size,
                                                      best_size) -> None:
    out, db = _place(side, limite, ladder, size, best_size, runner=True)
    assert out.status == "pending"
    q = db.queue[-1]
    # il prezzo e' il LIMITE (sul tick valido), mai il best del feed: il
    # miglioramento al best lo da' l'abbinamento del runner, come Betfair
    assert q["price"] == pytest.approx(limite)
    assert q["size"] == pytest.approx(min(size, best_size))
    assert q["time_in_force"] == "FILL_OR_KILL" and q["mode"] == "paper"


def test_safe_paper_ladder_resta_una_funzione_pura() -> None:
    from Betfair.safe_strategy import bot_service as BS

    lvl = BS._paper_ladder("back", {"back": 5.8, "back_size": 100.0, "lay": 6.0,
                                    "lay_size": 50.0}, None)
    assert lvl == ((5.8, 100.0),)
    assert BS._paper_ladder("back", None, None) is None
    assert BS._paper_ladder("back", {"lay": 6.0}, None) == ((0.0, 0.0),)
