# -*- coding: utf-8 -*-
"""PNL REALE (ordine dell'utente, 30/09): il regolato di Betfair per Safe e'
NETTO di commissione.

REPERTO. ``execution._posizione_da_cleared`` scriveva come P&L il ``profit``
di ``listClearedOrders`` per scommessa, credendolo netto. E' LORDO:

* documentazione nel repo (``Betfair/Betfair_api_documentation.pdf`` pag. 54):
  back 2,00 @ 1,28 WON -> ``profit`` 0,56 (= 2 x 0,28), ``commission`` 0,03 a
  parte, e solo raggruppando per mercato;
* conto vero (DB, sola lettura, ``meta.pnl_source`` di ``safe_strategy_trades``):
  #332 back 3,00 @ 1,16 WON -> ``profit`` 0,48 = 3 x 0,16 esatto (un netto al
  5 % sarebbe 0,46); #335 back 3,00 @ 1,12 WON -> 0,36 = 3 x 0,12; la
  ``commission`` della scommessa e' null su tutte le 14 righe regolate.

REGOLA (una sola, quella del runner che scrive ``pnl_betfair`` e di Mike):
netto della scommessa = profit - quota della commissione del SUO MERCATO
(``reconcile_worker.commissioni_per_ordine``: commissione del mercato ripartita
sui profit positivi di TUTTE le scommesse del conto su quel mercato, somma
esatta al centesimo; mercato in perdita = nessuna commissione).

I finti parlano come il vero: le scommesse passano da
``omega_market._riga_regolata`` a partire dalle chiavi camelCase di Betfair,
la lettura per mercato ha le chiavi di ``omega_market.list_cleared_markets_account``.

ASCII-only nel codice; commenti in italiano.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from Betfair.omega import omega_market as M
from Betfair.safe_strategy import bot_service as B
from Betfair.safe_strategy import execution as X

NOW = datetime(2026, 9, 30, 21, 0, tzinfo=timezone.utc)
MID = "1.262746473"


class FakeDB:
    """Le sole firme che ``settle_row``/``settle_position`` usano."""

    def __init__(self) -> None:
        self.rows: dict[int, dict] = {}
        self.activity: list[tuple[str, dict]] = []

    def seed(self, row: dict) -> None:
        self.rows[int(row["id"])] = dict(row)

    def get_trade(self, tid):
        r = self.rows.get(int(tid))
        return dict(r) if r else None

    def update_trade(self, tid, **fields):
        self.rows[int(tid)].update(fields)

    def log(self, kind, payload):
        self.activity.append((kind, dict(payload)))


class Snap:
    closed = True
    voided = False
    status = "CLOSED"

    def __init__(self, winner: int) -> None:
        self.winner_selection_id = winner


def _bet(bet_id: str, *, sel: int, side: str, price: float, size: float, profit: float,
         outcome: str, ref, market_id: str = MID) -> dict:
    """UNA scommessa regolata come la da' Betfair (livello scommessa, nessun
    groupBy: niente ``commission``), normalizzata dalla produzione."""
    raw = {"eventTypeId": "1", "eventId": "35760084", "marketId": market_id,
           "selectionId": sel, "handicap": 0.0, "betId": bet_id,
           "placedDate": "2026-09-30T19:00:00.000Z", "persistenceType": "LAPSE",
           "orderType": "LIMIT", "side": side, "betOutcome": outcome,
           "priceRequested": price, "settledDate": "2026-09-30T20:55:00.000Z",
           "lastMatchedDate": "2026-09-30T19:00:01.000Z", "betCount": 1,
           "priceMatched": price, "priceReduced": False, "sizeSettled": size,
           "profit": profit}
    if ref is not None:
        raw["customerOrderRef"] = ref
    return M._riga_regolata(raw)


def _mercato(profit: float, commission, market_id: str = MID) -> dict:
    """La lettura per MERCATO nella forma di ``list_cleared_markets_account``."""
    return {"market_id": market_id, "profit": profit, "commission": commission,
            "bet_count": 1, "settled_date": "2026-09-30T20:55:00.000Z"}


def _apertura(tid: int, *, side: str, price: float, size: float, bet_id: str,
              sel: int = 47972) -> dict:
    return {"id": tid, "side": side, "price": price, "size": size, "selection_id": sel,
            "market_id": MID, "mode": "live", "bet_id": bet_id, "commission": 0.05,
            "status": "open", "event_id": "35760084", "meta": {}}


def _chiusura(tid: int, parent: int, *, side: str, price: float, size: float,
              bet_id: str, sel: int = 47972) -> dict:
    r = _apertura(tid, side=side, price=price, size=size, bet_id=bet_id, sel=sel)
    r["closes_trade_id"] = parent
    return r


# ---------------------------------------------------------------------------
# 1. vincente con commissione > 0 (reperto #332)
# ---------------------------------------------------------------------------
def test_vincente_netto_uguale_lordo_meno_commissione_del_mercato():
    db = FakeDB()
    tr = _apertura(332, side="back", price=1.16, size=3.0, bet_id="444017854383")
    db.seed(tr)
    bets = [_bet("444017854383", sel=47972, side="BACK", price=1.16, size=3.0,
                 profit=0.48, outcome="WON", ref="safe-t332")]
    assert bets[0]["profit"] == 0.48 and bets[0]["commission"] is None
    ok = X.settle_position(db=db, trade=tr, closings=[], snap=Snap(47972), commission=0.05,
                           now=NOW, cleared_orders=bets,
                           cleared_markets=[_mercato(0.48, 0.02)], table_prefix="safe")
    assert ok is True
    r = db.rows[332]
    assert r["pnl"] == 0.46 and r["status"] == "won"
    src = r["meta"]["pnl_source"]
    assert src["kind"] == "betfair_cleared"
    assert (src["lordo"], src["commissione_quota"], src["netto"]) == (0.48, 0.02, 0.46)
    assert src["profit"] == 0.48          # il lordo di Betfair resta dichiarato


# ---------------------------------------------------------------------------
# 2. perdente: nessuna commissione
# ---------------------------------------------------------------------------
def test_perdente_nessuna_commissione():
    db = FakeDB()
    tr = _apertura(307, side="back", price=1.12, size=3.0, bet_id="443223141303")
    db.seed(tr)
    bets = [_bet("443223141303", sel=47972, side="BACK", price=1.12, size=3.0,
                 profit=-3.0, outcome="LOST", ref="safe-t307")]
    ok = X.settle_position(db=db, trade=tr, closings=[], snap=Snap(1), commission=0.05,
                           now=NOW, cleared_orders=bets,
                           cleared_markets=[_mercato(-3.0, 0.0)], table_prefix="safe")
    assert ok is True
    assert db.rows[307]["pnl"] == -3.0 and db.rows[307]["status"] == "lost"
    assert db.rows[307]["meta"]["pnl_source"]["commissione_quota"] == 0.0


# ---------------------------------------------------------------------------
# 3. posizione coperta: commissione sul NETTO di mercato (reperto #326/#327)
# ---------------------------------------------------------------------------
def test_posizione_coperta_commissione_sul_netto_di_mercato():
    db = FakeDB()
    tr = _apertura(326, side="back", price=1.15, size=3.0, bet_id="443369327545")
    tr["status"] = "hedged"
    cl = _chiusura(327, 326, side="lay", price=1.08, size=3.17, bet_id="443369658288")
    db.seed(tr)
    db.seed(cl)
    bets = [_bet("443369327545", sel=47972, side="BACK", price=1.15, size=3.0,
                 profit=0.45, outcome="WON", ref="safe-t326"),
            _bet("443369658288", sel=47972, side="LAY", price=1.08, size=3.17,
                 profit=-0.25, outcome="LOST", ref="safe-t327")]
    # mercato: +0,45 - 0,25 = +0,20 lordo -> commissione 5 % = 0,01 (tutta
    # sulla scommessa in utile, mai sulla perdente)
    ok = X.settle_position(db=db, trade=tr, closings=[cl], snap=Snap(47972),
                           commission=0.05, now=NOW, cleared_orders=bets,
                           cleared_markets=[_mercato(0.20, 0.01)], table_prefix="safe")
    assert ok is True
    assert db.rows[326]["pnl"] == 0.44
    assert db.rows[327]["pnl"] == -0.25
    assert db.rows[326]["meta"]["position_pnl"] == 0.19
    assert db.rows[327]["meta"]["position_pnl"] == 0.19
    pos = [p for k, p in db.activity if k == "settle_position"][-1]
    assert pos["pnl_source"] == "betfair_cleared" and pos["position_pnl"] == 0.19


# ---------------------------------------------------------------------------
# 4. parziali: due chiusure (parziale + residuo) e un record doppio di Betfair
# ---------------------------------------------------------------------------
def test_parziali_due_chiusure_somma_esatta_al_centesimo():
    db = FakeDB()
    tr = _apertura(400, side="back", price=2.0, size=10.0, bet_id="b400")
    tr["status"] = "hedged"
    c1 = _chiusura(401, 400, side="lay", price=1.8, size=5.0, bet_id="b401")
    c2 = _chiusura(402, 400, side="lay", price=1.9, size=5.1, bet_id="b402")
    for r in (tr, c1, c2):
        db.seed(r)
    bets = [
        # Betfair puo' dare piu' record per la stessa scommessa: i profit si sommano
        _bet("b400", sel=47972, side="BACK", price=2.0, size=6.0, profit=6.0,
             outcome="WON", ref="safe-t400"),
        _bet("b400", sel=47972, side="BACK", price=2.0, size=4.0, profit=4.0,
             outcome="WON", ref="safe-t400"),
        _bet("b401", sel=47972, side="LAY", price=1.8, size=5.0, profit=-4.0,
             outcome="LOST", ref="safe-t401"),
        _bet("b402", sel=47972, side="LAY", price=1.9, size=5.1, profit=-4.59,
             outcome="LOST", ref="safe-t402"),
    ]
    # mercato: 10,00 - 4,00 - 4,59 = +1,41 -> commissione 0,07
    ok = X.settle_position(db=db, trade=tr, closings=[c1, c2], snap=Snap(47972),
                           commission=0.05, now=NOW, cleared_orders=bets,
                           cleared_markets=[_mercato(1.41, 0.07)], table_prefix="safe")
    assert ok is True
    assert db.rows[400]["pnl"] == 9.93
    assert db.rows[401]["pnl"] == -4.0
    assert db.rows[402]["pnl"] == -4.59
    assert db.rows[400]["meta"]["position_pnl"] == 1.34
    assert round(db.rows[400]["pnl"] + db.rows[401]["pnl"] + db.rows[402]["pnl"], 2) \
        == round(1.41 - 0.07, 2)


# ---------------------------------------------------------------------------
# 5. il conto intero: un ordine dell'UTENTE sullo stesso mercato prende la sua
#    parte della commissione (ripartizione su TUTTE le scommesse in utile)
# ---------------------------------------------------------------------------
def test_commissione_ripartita_anche_sull_ordine_dell_utente():
    db = FakeDB()
    tr = _apertura(332, side="back", price=1.16, size=3.0, bet_id="444017854383")
    db.seed(tr)
    bets = [_bet("444017854383", sel=47972, side="BACK", price=1.16, size=3.0,
                 profit=0.48, outcome="WON", ref="safe-t332"),
            # ordine fatto dall'utente sul sito: nessun customerOrderRef
            _bet("444099999999", sel=47972, side="BACK", price=1.52, size=1.0,
                 profit=0.52, outcome="WON", ref=None)]
    # mercato: +1,00 -> commissione 0,05; quota di Safe = 0,05 x 0,48 = 0,024 -> 0,02
    ok = X.settle_position(db=db, trade=tr, closings=[], snap=Snap(47972), commission=0.05,
                           now=NOW, cleared_orders=bets,
                           cleared_markets=[_mercato(1.00, 0.05)], table_prefix="safe")
    assert ok is True
    assert db.rows[332]["pnl"] == 0.46
    assert db.rows[332]["meta"]["pnl_source"]["commissione_quota"] == 0.02


# ---------------------------------------------------------------------------
# 6. commissione del mercato NON letta: mai il lordo come netto, si ripiega
#    sul calcolo (gia' netto) dichiarato "calcolato"
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mercati", [None, [], [_mercato(0.48, None)],
                                     [_mercato(0.48, 0.02, market_id="1.000")]])
def test_senza_commissione_del_mercato_si_ripiega_sul_calcolo(mercati):
    db = FakeDB()
    tr = _apertura(332, side="back", price=1.16, size=3.0, bet_id="444017854383")
    db.seed(tr)
    bets = [_bet("444017854383", sel=47972, side="BACK", price=1.16, size=3.0,
                 profit=0.48, outcome="WON", ref="safe-t332")]
    ok = X.settle_position(db=db, trade=tr, closings=[], snap=Snap(47972), commission=0.05,
                           now=NOW, cleared_orders=bets, cleared_markets=mercati,
                           table_prefix="safe")
    assert ok is True
    assert db.rows[332]["meta"]["pnl_source"]["kind"] == "calcolato"
    assert db.rows[332]["pnl"] == 0.46          # 3 x 0,16 x 0,95 = 0,456 -> 0,46
    assert db.rows[332]["pnl"] != 0.48          # mai il lordo


# ---------------------------------------------------------------------------
# 7. la lettura al regolamento (bot_service): regolato del CONTO + mercato,
#    chiamate contate
# ---------------------------------------------------------------------------
class _MercatoFinto:
    """Lo sportello con i NOMI di produzione (``_MercatoSafe``) e del banco."""

    def __init__(self, bets, mercati, *, rompi: bool = False) -> None:
        self.bets, self.mercati, self.rompi = bets, mercati, rompi
        self.chiamate: list[tuple[str, tuple]] = []

    def list_account_cleared_bets(self, market_ids, stato="SETTLED"):
        self.chiamate.append(("bets", tuple(market_ids)))
        if self.rompi:
            raise RuntimeError("rete giu'")
        return list(self.bets)

    def list_account_cleared_markets(self, market_ids):
        self.chiamate.append(("mercati", tuple(market_ids)))
        return list(self.mercati)


def test_lettura_al_regolamento_due_chiamate_per_mercato():
    bets = [_bet("b1", sel=1, side="BACK", price=1.5, size=2.0, profit=1.0,
                 outcome="WON", ref="safe-t1")]
    mk = _MercatoFinto(bets, [_mercato(1.0, 0.05)])
    got = B._cleared_orders_for_market(mk, MID)
    assert got == (bets, [_mercato(1.0, 0.05)])
    assert mk.chiamate == [("bets", (MID,)), ("mercati", (MID,))]


def test_lettura_al_regolamento_nessun_regolato_una_sola_chiamata():
    mk = _MercatoFinto([], [_mercato(1.0, 0.05)])
    assert B._cleared_orders_for_market(mk, MID) is None
    assert mk.chiamate == [("bets", (MID,))]


def test_lettura_al_regolamento_rete_giu_o_sportello_muto_si_ripiega():
    mk = _MercatoFinto([], [], rompi=True)
    assert B._cleared_orders_for_market(mk, MID) is None

    class Muto:
        def list_cleared_orders(self, **_k):     # la lettura di prima: non basta piu'
            raise AssertionError("non va chiamata")

    assert B._cleared_orders_for_market(Muto(), MID) is None


def test_mercato_safe_delega_alle_letture_del_conto_di_omega_market():
    visti: list = []

    class Modulo:
        def list_cleared_bets_account(self, market_ids, stato):
            visti.append(("bets", list(market_ids), stato))
            return [{"bet_id": "x"}]

        def list_cleared_markets_account(self, market_ids):
            visti.append(("mercati", list(market_ids)))
            return [{"market_id": "1.1"}]

    ms = B._MercatoSafe(Modulo())
    assert ms.list_account_cleared_bets(["1.1"]) == [{"bet_id": "x"}]
    assert ms.list_account_cleared_markets(["1.1"]) == [{"market_id": "1.1"}]
    assert visti == [("bets", ["1.1"], "SETTLED"), ("mercati", ["1.1"])]


# ---------------------------------------------------------------------------
# 8. le due letture REST nuove di omega_market: forma vera della richiesta e
#    della risposta (client finto con i metodi del client vero)
# ---------------------------------------------------------------------------
class _ClientFinto:
    def __init__(self) -> None:
        self.rpc: list = []
        self.cleared: list = []

    def betting_rpc(self, method, params):
        self.rpc.append((method, params))
        return {"clearedOrders": [
            {"eventTypeId": "1", "eventId": "35760084", "marketId": MID,
             "settledDate": "2026-09-30T20:55:00.000Z", "betCount": 2,
             "commission": 0.02, "profit": 0.48}], "moreAvailable": False}

    def list_cleared_orders(self, bet_status="SETTLED", customer_strategy_refs=None,
                            market_ids=None, settled_from=None, **_k):
        self.cleared.append((bet_status, customer_strategy_refs, market_ids))
        return {"clearedOrders": [
            {"eventTypeId": "1", "eventId": "35760084", "marketId": MID,
             "selectionId": 47972, "handicap": 0.0, "betId": "444017854383",
             "side": "BACK", "betOutcome": "WON", "priceRequested": 1.16,
             "priceMatched": 1.16, "sizeSettled": 3.0, "profit": 0.48,
             "customerOrderRef": "safe-t332", "betCount": 1}]}


def test_omega_market_lettura_per_mercato_groupby_market(monkeypatch):
    cl = _ClientFinto()
    monkeypatch.setattr(M, "call", lambda fn: fn(cl))
    out = M.list_cleared_markets_account([MID])
    assert out == [{"market_id": MID, "profit": 0.48, "commission": 0.02, "bet_count": 2,
                    "settled_date": "2026-09-30T20:55:00.000Z"}]
    method, params = cl.rpc[0]
    assert method == "SportsAPING/v1.0/listClearedOrders"
    assert params["groupBy"] == "MARKET" and params["betStatus"] == "SETTLED"
    assert params["marketIds"] == [MID]


def test_omega_market_scommesse_del_conto_senza_filtro_di_strategia(monkeypatch):
    cl = _ClientFinto()
    monkeypatch.setattr(M, "call", lambda fn: fn(cl))
    out = M.list_cleared_bets_account([MID])
    assert cl.cleared == [("SETTLED", None, [MID])]
    assert out[0]["profit"] == 0.48 and out[0]["commission"] is None
    assert out[0]["bet_id"] == "444017854383" and out[0]["customer_order_ref"] == "safe-t332"


# ---------------------------------------------------------------------------
# 9. DAL GIRO VERO: ``bot_service.settle_open`` con lo sportello di PRODUZIONE
#    (``_MercatoSafe`` su ``omega_market``) e un client che risponde come
#    Betfair (listMarketBook, listClearedOrders a livello scommessa e per
#    MERCATO). Il P&L scritto e' il NETTO; al regolamento 2 chiamate.
# ---------------------------------------------------------------------------
class _ClientConto:
    def __init__(self) -> None:
        self.chiamate: list[str] = []

    def list_market_book(self, ids):
        self.chiamate.append("listMarketBook")
        return [{"marketId": "m-fin", "status": "CLOSED", "inplay": False,
                 "runners": [{"selectionId": s, "status": "WINNER" if s == 7 else "LOSER",
                              "ex": {"availableToBack": [], "availableToLay": []}}
                             for s in (8, 7, 9)]}]

    def list_current_orders(self, **_k):
        self.chiamate.append("listCurrentOrders")
        return {"currentOrders": []}

    def list_cleared_orders(self, bet_status="SETTLED", customer_strategy_refs=None,
                            market_ids=None, settled_from=None, **_k):
        self.chiamate.append(f"listClearedOrders:{bet_status}:"
                             f"{'strategia' if customer_strategy_refs else 'conto'}")
        if bet_status != "SETTLED":
            return {"clearedOrders": []}
        # lay 10,00 @ 8,5 sull'ospite (sel 8), ha vinto la casa: la lay VINCE +10,00
        return {"clearedOrders": [
            {"eventTypeId": "1", "eventId": "35926090", "marketId": "m-fin",
             "selectionId": 8, "handicap": 0.0, "betId": "BF1", "side": "LAY",
             "betOutcome": "WON", "priceRequested": 8.5, "priceMatched": 8.5,
             "sizeSettled": 10.0, "profit": 10.0, "customerOrderRef": "safe-t1",
             "settledDate": "2026-09-30T20:55:00.000Z", "betCount": 1}]}

    def betting_rpc(self, method, params):
        nome = str(method).split("/")[-1]
        if nome != "listClearedOrders" or params.get("groupBy") != "MARKET":
            # altre letture del giro (es. stato dell'ordine per betId): nessun dato
            self.chiamate.append(f"{nome}:{params.get('betStatus') or ''}")
            return {"currentOrders": [], "clearedOrders": [], "moreAvailable": False}
        self.chiamate.append("listClearedOrders:MARKET")
        return {"clearedOrders": [{"eventTypeId": "1", "eventId": "35926090",
                                   "marketId": "m-fin", "betCount": 1, "profit": 10.0,
                                   "commission": 0.5,
                                   "settledDate": "2026-09-30T20:55:00.000Z"}]}


def test_giro_vero_live_netto_di_betfair_e_due_chiamate(monkeypatch):
    from datetime import timedelta

    import db_client
    from Betfair.safe_strategy.tests.test_bot_service import FakeDB as DBB
    from Betfair.safe_strategy.tests.test_bot_service import NOW as NOW_B
    from Betfair.safe_strategy.tests.test_bot_service import _auto_trade, _reset_module_state

    _reset_module_state()
    B._EVENTI_CHIUSI.clear()

    def _vietato(*_a, **_k):
        raise AssertionError("accesso al database vero da un test")
    monkeypatch.setattr(db_client, "get_supabase_client", _vietato)
    cl = _ClientConto()
    monkeypatch.setattr(M, "call", lambda fn: fn(cl))
    db = DBB(status="stopped", mode="live")
    tid = _auto_trade(db, "esatto", event_id="35926090", market_id="m-fin", mode="live",
                      bet_id="BF1", signal_key="35926090:esatto:x")
    try:
        B.settle_open(params=B.resolve_params(None), market=B._MercatoSafe(M), db=db,
                      now=NOW_B + timedelta(days=2), rows_by_event={})
    finally:
        _reset_module_state()
    t = db.get_trade(tid)
    assert t["status"] == "won"
    assert t["pnl"] == 9.5, t          # 10,00 lordo - 0,50 commissione del mercato
    assert t["meta"]["pnl_source"]["kind"] == "betfair_cleared"
    assert cl.chiamate.count("listClearedOrders:MARKET") == 1
    # la lettura di prima (solo Safe, SETTLED + VOIDED) non si fa piu'
    assert "listClearedOrders:SETTLED:strategia" not in cl.chiamate
    assert "listClearedOrders:VOIDED:strategia" not in cl.chiamate
