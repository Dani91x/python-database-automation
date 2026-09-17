# -*- coding: utf-8 -*-
"""F2 — IL P&L E IL RIFERIMENTO STABILE NELLO SPECCHIO DEGLI ORDINI.

Due cose che mancavano e per cui lo storico dei quattro bot tennis non poteva
esistere (`AUDIT_4_BOT_TENNIS_2026-09-17.md` §F.2 e §F.4):

  1. `tennis_live_orders` non riceveva `pnl`, `commission`, `settled_at`: le
     colonne le aggiunge `migrations/tennis_bot_pnl_2026-09-17.sql`, ma NESSUNO
     le scriveva. Uno storico senza P&L non e' uno storico.
  2. il ref dello specchio era `"bot:" + order.id`, e `Order.id` e'
     `str(uuid.uuid1().time)` (`flumine/order/order.py:78`): cambia a ogni
     istanza. Il runner tennis ricostruisce il framework a ogni arm/disarm,
     quindi lo stesso ordine di Betfair tornava con un ref NUOVO — righe
     duplicate e righe vecchie ferme su `Executable` per sempre.

Ogni regola ha il suo contrario: una regola che non sa dire di no non e' una
regola (CLAUDE.md, «un test che non sa diventare rosso non certifica»).

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import types

import pytest
from flumine.order.order import OrderStatus

from Betfair.stream.tennis_live import tennis_live_order_worker as OW


# ---------------------------------------------------------------------------
# i finti: identiche chiavi e tipi del vero
# ---------------------------------------------------------------------------
class _Simulated:
    """IL FINTO PARLA COME IL VERO: `flumine.simulation.simulatedorder.Simulated`
    espone `profit` ed e' **falsy fuori dalla simulazione**
    (`__bool__` = `config.simulated or paper_trade`). In LIVE quel `profit` e'
    0 e scriverlo sarebbe una bugia: il finto deve saper essere falsy, altrimenti
    il caso LIVE non si puo' collaudare."""

    def __init__(self, profit, simulato: bool) -> None:
        self.profit = profit
        self._simulato = bool(simulato)

    def __bool__(self) -> bool:
        return self._simulato


def _ordine(*, bet_id=None, sel=111, side="LAY", price=1.08, size=2.0,
            matched=2.0, stato=OrderStatus.EXECUTION_COMPLETE, profit=None,
            simulato=True, oid="140089425876222758"):
    """Un `BetfairOrder` come lo vede il worker: `order_type` con `price`/`size`
    (mai `order.price`), `status` Enum, `simulated` con `profit`."""
    sim = _Simulated(profit, simulato)
    return types.SimpleNamespace(
        id=oid, bet_id=bet_id, selection_id=sel, side=side,
        size_matched=matched, size_remaining=0.0, size_cancelled=0.0,
        size_lapsed=0.0, size_voided=0.0, average_price_matched=price,
        status=stato, market_id="1.259781331", handicap=0.0, simulated=sim,
        order_type=types.SimpleNamespace(price=price, size=size),
        customer_order_ref=None, violation_msg=None,
    )


class _MarketBook:
    def __init__(self, base_rate=5.0):
        self.market_definition = types.SimpleNamespace(market_base_rate=base_rate)


class _Market:
    market_id = "1.259781331"

    def __init__(self, chiuso=False, base_rate=5.0):
        self.closed = chiuso
        self.market_book = _MarketBook(base_rate) if base_rate is not None else None


# ===========================================================================
# 1. il riferimento STABILE
# ===========================================================================
def test_il_ref_si_ancora_al_bet_id_di_betfair():
    """Il `bet_id` e' l'identita' di Betfair: sopravvive a qualunque riavvio."""
    o = _ordine(bet_id="123456789")
    assert OW.ref_bot_stabile("tennis_flb", "35794049", o) == "tfl-123456789"


def test_lo_stesso_ordine_dopo_un_RIAVVIO_ha_lo_STESSO_ref():
    """LA REGRESSIONE CHE CONTA: dopo un rebuild del framework `order.id`
    cambia. Il ref no."""
    prima = _ordine(bet_id="123456789", oid="111111111111111111")
    dopo = _ordine(bet_id="123456789", oid="999999999999999999")
    assert (OW.ref_bot_stabile("tennis_flb", "35794049", prima)
            == OW.ref_bot_stabile("tennis_flb", "35794049", dopo))


def test_senza_bet_id_il_ref_e_deterministico_sui_fatti_del_piazzamento():
    """Anche senza `bet_id` due letture dello stesso ordine danno lo stesso
    ref: bot, evento, mercato, selezione, lato, prezzo, size."""
    a = _ordine(bet_id=None, oid="111111111111111111")
    b = _ordine(bet_id=None, oid="999999999999999999")
    ra = OW.ref_bot_stabile("tennis_swing", "35794049", a)
    rb = OW.ref_bot_stabile("tennis_swing", "35794049", b)
    assert ra == rb and ra.startswith("tsw-x")


@pytest.mark.parametrize("cambia", [
    {"sel": 222}, {"side": "BACK"}, {"price": 1.09}, {"size": 3.0},
])
def test_ordini_DIVERSI_hanno_ref_diversi(cambia):
    """LA FALSIFICAZIONE: un ref che non distingue due ordini diversi li
    fonderebbe in una riga sola, e lo specchio mentirebbe."""
    base = _ordine(bet_id=None)
    altro = _ordine(bet_id=None, **cambia)
    assert (OW.ref_bot_stabile("tennis_pro", "35794049", base)
            != OW.ref_bot_stabile("tennis_pro", "35794049", altro))


def test_bot_diversi_non_si_mescolano_mai():
    o = _ordine(bet_id="123456789")
    assert (OW.ref_bot_stabile("tennis_flb", "35794049", o)
            != OW.ref_bot_stabile("tennis_pro", "35794049", o))


def test_il_ref_sta_nei_32_caratteri_della_colonna():
    """`tennis_live_orders.client_order_ref` e' la chiave unica: un ref piu'
    lungo verrebbe troncato e due ordini diversi collasserebbero."""
    for bet in (None, "1" * 20):
        r = OW.ref_bot_stabile("tennis_scalper", "35794049", _ordine(bet_id=bet))
        assert len(r) <= 32


# ===========================================================================
# 2. il P&L, la commissione, il settled_at
# ===========================================================================
def test_la_commissione_viene_dal_marketDefinition_streamato():
    """5 nel `marketBaseRate` vuol dire 5%: non un numero scritto in casa."""
    assert OW._commissione_mercato(_Market(base_rate=5.0)) == pytest.approx(0.05)


def test_senza_marketDefinition_la_commissione_e_IGNOTA_non_zero():
    """Dato assente non e' zero (catalogo §7.21)."""
    assert OW._commissione_mercato(_Market(base_rate=None)) is None


def test_il_pnl_si_legge_dal_settlement_simulato():
    assert OW._pnl_ordine(_ordine(profit=1.5)) == 1.5


def test_in_LIVE_il_pnl_simulato_NON_si_scrive():
    """`Simulated.__bool__` e' falsy fuori dalla simulazione: li' `profit` e' 0
    e scriverlo sarebbe una bugia. Meglio `None` — la UI mostra un trattino."""
    assert OW._pnl_ordine(_ordine(profit=0.0, simulato=False)) is None


def test_lo_specchio_scrive_pnl_commissione_e_settled_at():
    scritte = []
    vero = OW.tennis_db.upsert_tennis_order
    OW.tennis_db.upsert_tennis_order = lambda row: scritte.append(dict(row))
    try:
        OW._mirror_order("paper", "35794049", "tfl-123", _ordine(bet_id="123"),
                         {}, source="tennis_flb", pnl=1.5, commission=0.08,
                         settled_at="2026-09-17T18:00:00+00:00")
    finally:
        OW.tennis_db.upsert_tennis_order = vero
    assert scritte and scritte[0]["pnl"] == 1.5
    assert scritte[0]["commission"] == 0.08
    assert scritte[0]["settled_at"] == "2026-09-17T18:00:00+00:00"
    assert scritte[0]["source"] == "tennis_flb"
    assert scritte[0]["mode"] == "paper"


def test_finche_non_e_regolato_le_colonne_del_regolamento_NON_si_scrivono():
    """LA FALSIFICAZIONE: scrivere `pnl=0` su un ordine non regolato
    sporcherebbe lo storico con zeri che non sono risultati. Le chiavi proprio
    non compaiono, cosi' un DB senza la migrazione non riceve campi ignoti."""
    scritte = []
    vero = OW.tennis_db.upsert_tennis_order
    OW.tennis_db.upsert_tennis_order = lambda row: scritte.append(dict(row))
    try:
        OW._mirror_order("paper", "35794049", "tfl-123", _ordine(bet_id="123"),
                         {}, source="tennis_flb")
    finally:
        OW.tennis_db.upsert_tennis_order = vero
    assert scritte
    for chiave in ("pnl", "commission", "settled_at"):
        assert chiave not in scritte[0]


# ===========================================================================
# 3. il giro vero: `_reconcile_bots` a mercato chiuso
# ===========================================================================
class _Blotter:
    def __init__(self, ordini):
        self._o = list(ordini)

    def strategy_orders(self, _s):
        return list(self._o)


class _Flumine:
    def __init__(self, market):
        self.markets = types.SimpleNamespace(markets={market.market_id: market})


class _Session:
    def __init__(self, market, strat):
        self.hosted = {("35794049", "tennis_flb"): strat}
        self.market_meta = {"35794049": {"market_id": market.market_id}}
        self.order_mode = "paper"


def _gira(chiuso: bool, profit=1.5):
    strat = object()
    market = _Market(chiuso=chiuso)
    market.blotter = _Blotter([_ordine(bet_id="555", profit=profit)])
    scritte = []
    vero = OW.tennis_db.upsert_tennis_order
    OW.tennis_db.upsert_tennis_order = lambda row: scritte.append(dict(row))
    try:
        OW._reconcile_bots(_Session(market, strat), _Flumine(market), {})
    finally:
        OW.tennis_db.upsert_tennis_order = vero
    return scritte


def test_a_mercato_chiuso_il_giro_scrive_il_regolamento():
    scritte = _gira(chiuso=True, profit=2.0)
    assert scritte, "lo specchio deve ricevere la riga"
    r = scritte[0]
    assert r["client_order_ref"] == "tfl-555", "ref stabile, non bot:<uuid>"
    assert r["pnl"] == 2.0
    # commissione sul PROFITTO: 5% di 2,00
    assert r["commission"] == pytest.approx(0.10)
    assert r["settled_at"] is not None


def test_a_mercato_APERTO_non_si_regola_niente():
    """LA FALSIFICAZIONE: un mercato aperto non ha ancora un esito, e scriverlo
    vorrebbe dire inventarlo."""
    scritte = _gira(chiuso=False, profit=2.0)
    assert scritte
    for chiave in ("pnl", "commission", "settled_at"):
        assert chiave not in scritte[0]


def test_la_commissione_non_si_paga_sulle_perdite():
    scritte = _gira(chiuso=True, profit=-3.0)
    assert scritte[0]["pnl"] == -3.0
    assert scritte[0]["commission"] == 0.0
