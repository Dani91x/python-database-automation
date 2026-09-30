# -*- coding: utf-8 -*-
"""PNL REALE (30/09): Omega regola GIA' al NETTO di commissione e non usa mai
il ``profit`` di Betfair (che e' LORDO) come P&L.

Omega regola in due posti, entrambi col CALCOLO (mai coi cleared orders):

* ``omega_service.settle_open`` (posizione singola): ``omega_engine.settle_pnl``
  con la commissione FISSATA sulla riga (lay vinta = size x (1 - c));
* ``omega_service._settle_hedged`` (apertura + chiusure):
  ``execution.settle_position`` SENZA ``cleared_orders`` -> ``settle_group``,
  commissione sul netto di mercato.

Questi test lo dimostrano con uno sportello che ESPONE anche il regolato di
Betfair (lordo, forma vera di ``_riga_regolata``): il P&L scritto resta il
netto al centesimo. Il reperto 6842 del referto (``profit=profit``) e'
l'etichetta dell'uscita (bool "in utile"), non un importo.

ASCII-only nel codice; commenti in italiano.
"""
from __future__ import annotations

from datetime import timedelta

from Betfair.omega import omega_engine as E
from Betfair.omega import omega_market as M
from Betfair.omega.test_omega_service import (NOW, FakeDB, FakeMarket, _closed_snapshot,
                                              _control, _cs, _event, _open_snapshot)
from Betfair.omega.tests.runner_paper_finto import attiva_runner_paper, gira
from Betfair.safe_strategy import execution as X


class _MercatoConRegolatoLordo(FakeMarket):
    """Lo sportello dei test di Omega con, in piu', il regolato di Betfair
    LORDO (``profit`` = size x (prezzo - 1) sulla vincente, nessuna
    commissione a livello di scommessa): se Omega lo usasse, il P&L sarebbe
    lordo e il test diventerebbe rosso."""

    def list_cleared_orders(self, strategy_ref="omega", market_ids=None, lookback_hours=72):
        return [M._riga_regolata({"betId": "b1", "marketId": "m-1.100", "selectionId": 4,
                                  "side": "LAY", "priceMatched": 110.0, "sizeSettled": 2.0,
                                  "profit": 2.0, "betOutcome": "WON",
                                  "customerOrderRef": "omega-t1"})]

    def list_account_cleared_bets(self, market_ids, stato="SETTLED"):
        return self.list_cleared_orders()

    def list_account_cleared_markets(self, market_ids):
        return [{"market_id": "m-1.100", "profit": 2.0, "commission": 0.1,
                 "bet_count": 1, "settled_date": None}]


def test_omega_posizione_singola_regolata_al_netto_esatto():
    db = attiva_runner_paper(FakeDB(_control()))
    market = _MercatoConRegolatoLordo([_event()], _cs(), _open_snapshot())
    gira(market=market, db=db, now=NOW)
    t = db.trades[0]
    size, comm = float(t["size"]), float(t.get("commission") or 0.05)
    assert comm > 0
    market._snapshot = _closed_snapshot(winner_id=1)      # il nostro 3-2 NON esce
    gira(market=market, db=db, now=NOW + timedelta(hours=2))
    t = db.trades[0]
    assert t["status"] == "won"
    assert t["pnl"] == E.net_profit_if_win(size, comm)
    assert t["pnl"] == round(size * (1 - comm), 2)
    assert t["pnl"] < round(size, 2)                       # mai il lordo


def test_omega_coppia_regolata_senza_cleared_e_netta_sul_mercato():
    """La chiamata di ``_settle_hedged`` (nessun ``cleared_orders``): lay 2,00 @
    110 sul 3-2 chiusa in parte con back 1,00 @ 100; esce 0-0 -> lay +2,00,
    back -1,00: mercato +1,00 -> commissione 0,05 tutta sulla gamba in utile
    (1,95 / -1,00, posizione 0,95). Poi la lay vinta da sola -> 2 x 0,95."""
    rows: dict = {}

    class DB:
        def get_trade(self, tid):
            return dict(rows[int(tid)])

        def update_trade(self, tid, **f):
            rows[int(tid)].update(f)

        def log(self, *_a):
            pass

    class Snap:
        closed, voided, status, winner_selection_id = True, False, "CLOSED", 1

    tr = {"id": 1, "side": "lay", "price": 110.0, "size": 2.0, "selection_id": 4,
          "market_id": "m-1.100", "mode": "live", "bet_id": "b1", "commission": 0.05,
          "status": "hedged", "event_id": "1.100", "meta": {}}
    cl = {"id": 2, "side": "back", "price": 100.0, "size": 1.0, "selection_id": 4,
          "market_id": "m-1.100", "mode": "live", "bet_id": "b2", "commission": 0.05,
          "status": "open", "event_id": "1.100", "closes_trade_id": 1, "meta": {}}
    rows[1], rows[2] = dict(tr), dict(cl)
    assert X.settle_position(db=DB(), trade=tr, closings=[cl], snap=Snap(), commission=0.05,
                             now=NOW) is True
    assert rows[1]["meta"]["pnl_source"]["kind"] == "calcolato"
    assert (rows[1]["pnl"], rows[2]["pnl"]) == (1.95, -1.0)
    assert rows[1]["meta"]["position_pnl"] == 0.95
    # da sola (nessuna chiusura): 2,00 x 0,95 = 1,90, non 2,00
    rows[3] = {**tr, "id": 3, "status": "open", "meta": {}}
    assert X.settle_position(db=DB(), trade=rows[3], closings=[], snap=Snap(),
                             commission=0.05, now=NOW) is True
    assert rows[3]["pnl"] == 1.9
