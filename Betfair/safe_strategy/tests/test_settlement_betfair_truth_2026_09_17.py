# -*- coding: utf-8 -*-
"""REPERTO 17/09 (registro Betfair, listClearedOrders, sola lettura, contro il
DB): #298 (apertura back, tennis) aveva sulla riga il prezzo MEDIO di due
fill (2,92 EUR a 1,06 + 0,08 EUR a 1,07 = 1,0602666666666665), mentre Betfair
aveva regolato l'ordine con profit +0,19 WON; la sua chiusura #299 (lay,
priceMatched 1.03, sizeSettled 3.09) con profit -0,09 LOST. Netto Betfair
della coppia = +0,10. Il calcolo del bot (prezzo medio, esposizioni nette,
commissione sul netto) pianificava +0,09: un centesimo di differenza per
l'arrotondamento del prezzo medio, non un errore di logica — ma «il trader
deve avere tutto sotto controllo con dati reali» (ordine dell'utente).
#297 (back, senza chiusura: tenuto a settlement) era gia' coerente (DB price
1.03 = Betfair priceMatched 1.03, pnl 0.09): resta cosi', e questo file lo
verifica anche per quel caso.

I3 ("Betfair e' la verita'"): `execution.settle_position` regola con il
``profit`` dei cleared orders VERI (via `omega_market._riga_regolata`, le
STESSE chiavi della produzione: betId, priceRequested, priceMatched,
sizeSettled, profit, commission, betOutcome, customerOrderRef) quando OGNI
gamba della posizione li ha gia' con un profit numerico, e ripiega sul calcolo
di sempre altrimenti (mai un numero VERO mischiato con uno STIMATO sulla
stessa posizione).

FALSIFICAZIONE (obbligatoria, PROCESSO_STANDARD_BOT.md): tolta la lettura dai
cleared orders (chiamando ``settle_group``/``omega_engine.settle_pnl`` anche
quando Betfair li ha gia') i test del profit di Betfair (0.19/-0.09/+0.10 e
0.09) vanno ROSSI — vedi il referto della sessione per l'output del giro
falsificato.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from datetime import datetime, timezone

from Betfair.omega import omega_market as M
from Betfair.safe_strategy import execution as X

NOW = datetime(2026, 9, 17, 9, 5, tzinfo=timezone.utc)


class FakeDB:
    """Le sole firme che `settle_row`/`settle_position` usano: `get_trade`
    (rilettura fresca del meta, M12), `update_trade`, `log`."""

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


class FakeSnap:
    """Mercato CHIUSO, non annullato: solo `winner_selection_id` cambia fra i
    test (la selezione che ha vinto)."""
    closed = True
    voided = False
    winner_selection_id = 7


def _ordine_betfair(**kw) -> dict:
    """Un ordine REGOLATO come lo restituisce l'API VERA di Betfair (chiavi
    camelCase: betId, priceRequested, priceMatched, sizeSettled, profit,
    commission, betOutcome, customerOrderRef), passato dalla STESSA
    normalizzazione della produzione (`omega_market._riga_regolata`): un
    finto con chiavi diverse dal vero e' il difetto 1 del catalogo."""
    raw = {"betId": kw["bet_id"], "marketId": kw.get("market_id", "1.9999"),
           "selectionId": kw["selection_id"], "side": kw["side"],
           "priceRequested": kw.get("price_requested"), "priceMatched": kw["price_matched"],
           "sizeSettled": kw["size_settled"], "profit": kw["profit"],
           "commission": kw.get("commission", "0.05"), "betOutcome": kw["bet_outcome"],
           "customerOrderRef": kw["ref"]}
    return M._riga_regolata(raw)


def _cleared_298_299() -> list[dict]:
    return [
        _ordine_betfair(bet_id="b298", selection_id=7, side="BACK", price_requested=1.05,
                        price_matched=1.06, size_settled=3.0, profit=0.19,
                        bet_outcome="WON", ref="safe-t298"),
        _ordine_betfair(bet_id="b299", selection_id=7, side="LAY", price_requested=1.03,
                        price_matched=1.03, size_settled=3.09, profit=-0.09,
                        bet_outcome="LOST", ref="safe-t299"),
    ]


def _trade_298() -> dict:
    return {"id": 298, "side": "back", "price": 1.0602666666666665, "size": 3.0,
            "selection_id": 7, "market_id": "1.9999", "mode": "live",
            "bet_id": "b298", "commission": 0.05, "status": "hedged",
            "event_id": "e1", "meta": {}}


def _closing_299() -> dict:
    return {"id": 299, "side": "lay", "price": 1.03, "size": 3.09,
            "closes_trade_id": 298, "selection_id": 7, "market_id": "1.9999",
            "mode": "live", "bet_id": "b299", "commission": 0.05,
            "status": "open", "event_id": "e1", "meta": {}}


def test_regolamento_legge_il_profit_di_betfair_quando_ce_su_tutte_le_gambe():
    db = FakeDB()
    trade, closing = _trade_298(), _closing_299()
    db.seed(trade)
    db.seed(closing)
    ok = X.settle_position(db=db, trade=trade, closings=[closing], snap=FakeSnap(),
                           commission=0.05, now=NOW, cleared_orders=_cleared_298_299(),
                           table_prefix="safe")
    assert ok is True
    assert db.rows[298]["pnl"] == 0.19 and db.rows[298]["status"] == "won"
    assert db.rows[299]["pnl"] == -0.09 and db.rows[299]["status"] == "lost"
    assert db.rows[298]["meta"]["position_pnl"] == 0.10, db.rows[298]["meta"]
    assert db.rows[298]["meta"]["pnl_source"]["kind"] == "betfair_cleared"
    assert db.rows[299]["meta"]["pnl_source"]["kind"] == "betfair_cleared"
    assert db.rows[298]["meta"]["pnl_source"]["commission"] == "0.05"


def test_senza_cleared_orders_si_ripiega_sul_calcolo_di_sempre():
    """Nessun `cleared_orders`: comportamento IDENTICO a prima del 17/09 (i
    chiamanti che non lo passano, come Omega, restano invariati). Il calcolo
    sul prezzo medio arrotondato non deve coincidere per caso col netto vero
    di Betfair (+0,10): e' esattamente la differenza che I3 corregge quando i
    cleared orders ci sono."""
    db = FakeDB()
    trade, closing = _trade_298(), _closing_299()
    db.seed(trade)
    db.seed(closing)
    ok = X.settle_position(db=db, trade=trade, closings=[closing], snap=FakeSnap(),
                           commission=0.05, now=NOW)   # niente cleared_orders
    assert ok is True
    assert db.rows[298]["meta"]["pnl_source"]["kind"] == "calcolato"
    posizione = db.rows[298]["meta"]["position_pnl"]
    assert posizione != 0.10, ("il calcolo sul prezzo medio arrotondato non deve "
                               "coincidere col netto vero di Betfair: se coincide "
                               "il test non falsifica nulla")


def test_una_sola_gamba_nei_cleared_non_basta_si_ripiega_intero():
    """Solo l'apertura e' gia' nei cleared (la chiusura non ancora, es. si e'
    regolata un attimo dopo): niente numero VERO mischiato con uno STIMATO
    sulla stessa posizione, si ripiega TUTTO sul calcolo di sempre."""
    db = FakeDB()
    trade, closing = _trade_298(), _closing_299()
    db.seed(trade)
    db.seed(closing)
    solo_apertura = [_cleared_298_299()[0]]
    ok = X.settle_position(db=db, trade=trade, closings=[closing], snap=FakeSnap(),
                           commission=0.05, now=NOW, cleared_orders=solo_apertura,
                           table_prefix="safe")
    assert ok is True
    assert db.rows[298]["meta"]["pnl_source"]["kind"] == "calcolato"
    assert db.rows[299]["meta"]["pnl_source"]["kind"] == "calcolato"


def _trade_297() -> dict:
    return {"id": 297, "side": "back", "price": 1.03, "size": 3.0,
            "selection_id": 5, "market_id": "1.8888", "mode": "live",
            "bet_id": "b297", "commission": 0.05, "status": "open",
            "event_id": "e2", "meta": {}}


def _cleared_297() -> list[dict]:
    return [_ordine_betfair(bet_id="b297", selection_id=5, side="BACK", price_requested=1.02,
                            price_matched=1.03, size_settled=3.0, profit=0.09,
                            bet_outcome="WON", ref="safe-t297")]


def test_riga_singola_senza_chiusura_legge_anch_essa_il_profit_di_betfair():
    """#297: gia' coerente (DB 1.03 = Betfair 1.03), ma la strada e' la stessa
    per una posizione SENZA chiusure (tenuta a settlement): deve leggere il
    profit di Betfair anche qui, non solo quando ci sono gambe di chiusura."""
    db = FakeDB()
    trade = _trade_297()
    db.seed(trade)
    snap = FakeSnap()
    snap.winner_selection_id = 5
    ok = X.settle_position(db=db, trade=trade, closings=[], snap=snap,
                           commission=0.05, now=NOW, cleared_orders=_cleared_297(),
                           table_prefix="safe")
    assert ok is True
    assert db.rows[297]["pnl"] == 0.09 and db.rows[297]["status"] == "won"
    assert db.rows[297]["meta"]["pnl_source"]["kind"] == "betfair_cleared"
