"""R1 (24/09) - customerStrategyRef per ATTORE sugli ordini REST.

Prima: Safe piazzava con ``omega_market.place_*`` e i suoi ordini uscivano con
``customerStrategyRef="omega"`` (omega_market.py, place_order_live e parcheggio
del place-and-trim). ``listCurrentOrders("omega")`` di Omega vedeva anche Safe.

Il client finto riceve le STESSE chiamate di betfairlightweight
(``place_orders(market_id, instructions, customer_ref=, customer_strategy_ref=)``,
``list_current_orders(customer_strategy_refs=)``,
``list_cleared_orders(bet_status=, customer_strategy_refs=, market_ids=,
settled_from=)``) e risponde con le chiavi grezze di Betfair (camelCase), come
il vero: il filtro per strategia lo applica LUI, come fa l'exchange.
"""
from __future__ import annotations

import pytest

from Betfair.mike import service as MS
from Betfair.omega import omega_market as OM
from Betfair.safe_strategy import bot_service as SB


def _report_ok(size):
    return {"status": "SUCCESS", "instructionReports": [{
        "status": "SUCCESS", "orderStatus": "EXECUTION_COMPLETE", "betId": "9001",
        "sizeMatched": size, "averagePriceMatched": 2.5,
        "placedDate": "2026-09-24T20:00:00.000Z"}]}


# ordini sul CONTO: chi li ha piazzati e con quale strategia
_CONTO = [
    {"betId": "1", "marketId": "1.10", "selectionId": 7, "side": "LAY", "status": "EXECUTABLE",
     "customerOrderRef": "omega-t11", "customerStrategyRef": "omega"},
    {"betId": "2", "marketId": "1.10", "selectionId": 7, "side": "BACK", "status": "EXECUTABLE",
     "customerOrderRef": "safe-t22", "customerStrategyRef": "safe"},
    # ordine di Safe nato PRIMA del 24/09, col ref di Omega
    {"betId": "3", "marketId": "1.10", "selectionId": 8, "side": "BACK", "status": "EXECUTABLE",
     "customerOrderRef": "safe-t33", "customerStrategyRef": "omega"},
    {"betId": "4", "marketId": "1.10", "selectionId": 8, "side": "LAY", "status": "EXECUTABLE",
     "customerOrderRef": "mike-t44", "customerStrategyRef": "mike"},
]


class _Client:
    def __init__(self):
        self.place: list = []
        self.letture: list = []

    def place_orders(self, market_id, instructions, customer_ref=None,
                     customer_strategy_ref=None, **kw):
        self.place.append({"market_id": market_id, "customer_ref": customer_ref,
                           "customer_strategy_ref": customer_strategy_ref})
        return _report_ok(instructions[0]["limitOrder"]["size"])

    def list_current_orders(self, customer_strategy_refs=None, **kw):
        self.letture.append(list(customer_strategy_refs or []))
        return {"currentOrders": [o for o in _CONTO
                                  if o["customerStrategyRef"] in (customer_strategy_refs or [])]}

    def list_cleared_orders(self, bet_status=None, customer_strategy_refs=None,
                            market_ids=None, settled_from=None, **kw):
        self.letture.append(list(customer_strategy_refs or []))
        if bet_status != "SETTLED":
            return {"clearedOrders": []}
        return {"clearedOrders": [
            {**o, "sizeSettled": 2.0, "priceMatched": 2.5, "profit": 1.0}
            for o in _CONTO if o["customerStrategyRef"] in (customer_strategy_refs or [])]}


@pytest.fixture
def client(monkeypatch):
    c = _Client()
    monkeypatch.setattr(OM, "call_mutating", lambda fn, **k: fn(c))
    monkeypatch.setattr(OM, "call", lambda fn, **k: fn(c))
    return c


_ORDINE = dict(market_id="1.10", selection_id=7, price=2.5, size=4.0, event_id="E1", side="back")


# ---------------------------------------------------------------------------
# Scrittura
# ---------------------------------------------------------------------------
def test_omega_piazza_con_omega_come_prima(client):
    OM.place_order_live(**_ORDINE, customer_ref="omega-t11")
    OM.place_lay_live(market_id="1.10", selection_id=7, price=2.5, size=4.0,
                      event_id="E1", customer_ref="omega-t12")
    assert [p["customer_strategy_ref"] for p in client.place] == ["omega", "omega"]


def test_safe_piazza_con_safe(client):
    SB._real_market.place_order_live(**_ORDINE, customer_ref="safe-t22")
    # importo sopra il minimo: il place-and-trim diventa un ordine normale
    SB._real_market.place_submin_live(**_ORDINE, customer_ref="safe-t23")
    assert [p["customer_strategy_ref"] for p in client.place] == ["safe", "safe"]
    assert [p["customer_ref"] for p in client.place] == ["safe-t22", "safe-t23"]


def test_safe_sotto_minimo_il_parcheggio_porta_safe(client, monkeypatch):
    """Il parcheggio del place-and-trim era l'altra riga col ref di Omega."""
    monkeypatch.setattr(client, "place_orders",
                        lambda market_id, instructions, customer_ref=None,
                        customer_strategy_ref=None, **kw:
                        client.place.append({"customer_strategy_ref": customer_strategy_ref,
                                             "customer_ref": customer_ref}) or {})
    with pytest.raises(RuntimeError, match="IGNOTO al parcheggio"):
        SB._real_market.place_submin_live(market_id="1.10", selection_id=7, price=2.5,
                                          size=0.73, event_id="E1", side="back",
                                          customer_ref="safe-t24", fill_or_kill=False,
                                          best_back=2.5, best_lay=2.52)
    assert client.place == [{"customer_strategy_ref": "safe", "customer_ref": "safe-t24"}]


def test_mike_piazza_con_mike(client, monkeypatch):
    monkeypatch.setenv("MIKE_LIVE_ENABLED", "1")
    monkeypatch.setattr(OM, "CUSTOMER_STRATEGY_REF", OM.CUSTOMER_STRATEGY_REF)   # ripristino
    MS._RealMarket.place_order_live(**_ORDINE, customer_ref="mike-t44")
    assert client.place[-1]["customer_strategy_ref"] == "mike"


@pytest.mark.parametrize("ref", ["", "x" * 16, "con spazio", "caff" + chr(232), 5])
def test_ref_non_valido_nessuna_chiamata_a_betfair(client, ref):
    with pytest.raises(ValueError, match="customerStrategyRef"):
        OM.place_order_live(**_ORDINE, strategy_ref=ref)
    assert client.place == []


# ---------------------------------------------------------------------------
# Lettura
# ---------------------------------------------------------------------------
def test_omega_legge_solo_omega_e_non_vede_safe(client):
    visti = {r["customer_order_ref"] for r in OM.list_current_orders()}
    assert "safe-t22" not in visti and "mike-t44" not in visti
    assert "omega-t11" in visti
    assert client.letture == [["omega"]]


def test_safe_legge_i_suoi_anche_quelli_nati_col_ref_di_omega_e_non_vede_omega(client):
    visti = {r["customer_order_ref"] for r in SB._real_market.list_current_orders()}
    assert visti == {"safe-t22", "safe-t33"}
    assert client.letture == [["safe", "omega"]]


def test_safe_cleared_per_mercato_solo_i_suoi(client):
    regolati = SB._real_market.list_cleared_orders(market_ids=["1.10"])
    assert {r["customer_order_ref"] for r in regolati} == {"safe-t22", "safe-t33"}


def test_omega_cleared_non_vede_safe(client):
    regolati = OM.list_cleared_orders(market_ids=["1.10"])
    assert {r["customer_order_ref"] for r in regolati} == {"omega-t11", "safe-t33"}


def test_lettura_con_elenco_di_ref_e_mai_senza_filtro(client):
    OM.list_current_orders(["mike"])
    assert client.letture[-1] == ["mike"]
    with pytest.raises(ValueError):
        OM.list_current_orders([])        # senza filtro Betfair darebbe TUTTO il conto


def test_il_mercato_di_safe_passa_il_resto_al_modulo():
    assert SB._real_market.CorrectScoreMarket is OM.CorrectScoreMarket
    assert SB._real_market.cancel_order_live is OM.cancel_order_live
    assert SB._real_market.posizione_di_conto is OM.posizione_di_conto
