"""Unit test per ``runner.build_order_client`` — FIX 6: controlli NATIVI flumine.

Verifica che il client flumine sia costruito in modo COERENTE sulle 3 modalità
(OFF / PAPER / LIVE) con i controlli nativi cablati:
  * ``min_bet_validation=False`` su TUTTE le modalità (fix CRITICAL-3): l'OrderValidation
    nativo NON conosce l'eccezione Betfair "bet che riduce la liability" e rifiuterebbe
    client-side ogni green-up/cash-out sotto-minimo (che l'Exchange invece ACCETTA) e lo
    step1 del place-and-trim. I minimi di giurisdizione restano validati STRETTI da
    ``live_order_build.min_stake_rules`` (consapevole di ``reduces_liability``);
  * ``transaction_limit=LIVE_TRANSACTION_LIMIT`` (control nativo MaxTransactionCount) idem;
  * ``order_stream`` / ``paper_trade`` / ``orders_enabled`` coerenti con la modalità.

Nessuna rete, nessun login: si passa un ``api_client`` fittizio (SimpleNamespace senza
attributo ``lightweight``, così il BaseClient salta la sua assert) e si costruisce il VERO
client flumine (il costruttore si limita a memorizzare gli attributi).
"""
from __future__ import annotations

import types

import pytest

from Betfair.stream import runner


def _fake_api_client() -> types.SimpleNamespace:
    # niente attributo .lightweight → BaseClient salta `assert betting_client.lightweight is False`
    return types.SimpleNamespace()


@pytest.mark.parametrize(
    "mode,exp_enabled,exp_order_stream,exp_paper",
    [
        ("OFF", False, False, False),
        # PAPER: order_stream=True È CORRETTO — con paper_trade=True flumine apre il
        # SimulatedOrderStream (non quello reale), che genera i CurrentOrdersEvent senza
        # cui process_orders non scatterebbe e lo specchio resterebbe vuoto. (bug fix 30/06)
        ("PAPER", True, True, True),
        ("LIVE", True, True, False),
        # valore sconosciuto → trattato come OFF (nessun ordine)
        ("garbage", False, False, False),
        # default/None → OFF
        (None, False, False, False),
        # case-insensitive + spazi
        ("  live  ", True, True, False),
    ],
)
def test_build_order_client_modes(mode, exp_enabled, exp_order_stream, exp_paper):
    client, orders_enabled = runner.build_order_client(_fake_api_client(), mode)

    assert orders_enabled is exp_enabled
    assert client.order_stream is exp_order_stream
    assert client.paper_trade is exp_paper

    # Fix CRITICAL-3: OrderValidation nativo DISATTIVATO su tutte le modalità (rifiuterebbe
    # i green-up sotto-minimo reduces_liability che Betfair accetta); i minimi li valida
    # live_order_build.min_stake_rules. Il transaction_limit nativo resta attivo.
    assert client.min_bet_validation is False
    assert client.transaction_limit == runner.LIVE_TRANSACTION_LIMIT


def test_transaction_limit_is_sensible():
    """Il tetto orario di transazioni deve essere positivo e sotto la soglia Betfair (5000/h)."""
    assert isinstance(runner.LIVE_TRANSACTION_LIMIT, int)
    assert 0 < runner.LIVE_TRANSACTION_LIMIT <= 5000


def test_off_is_historic_behavior():
    """OFF resta il comportamento storico: nessun order stream, niente paper, orders_enabled=False.

    I controlli nativi (min_bet_validation/transaction_limit) sono INERTI in OFF (nessun place
    possibile) quindi non introducono regressioni.
    """
    client, orders_enabled = runner.build_order_client(_fake_api_client(), "OFF")
    assert orders_enabled is False
    assert client.order_stream is False
    assert client.paper_trade is False


def test_live_order_stream_conflate_passed():
    """LIVE deve propagare la conflazione order-stream (None quando 0 = max reattività)."""
    client, _ = runner.build_order_client(_fake_api_client(), "LIVE")
    # ORDER_STREAM_CONFLATE_MS default 0 → passato come None al client
    assert client.order_stream_conflate_ms == (runner.ORDER_STREAM_CONFLATE_MS or None)
