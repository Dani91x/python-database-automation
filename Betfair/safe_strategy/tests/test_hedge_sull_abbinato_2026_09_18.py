"""18/09 - l'hedge conta l'ABBINATO delle chiusure, non il chiesto (ordine dell'utente).

Esempio dell'utente: lay 10 EUR @3.00, chiusura back 12 EUR @2.50 di cui solo 5 abbinati.
Prima: 12*2.5/3 = 10 coperti -> 'complete' -> apertura 'hedged' con 12,50 EUR ancora a rischio.
Le righe hanno le STESSE chiavi di ``safe_strategy_trades`` (snake_case, colonne del 16/09).
"""
from __future__ import annotations

from Betfair.safe_strategy import execution as X

APERTURA = {"id": 1, "side": "lay", "size": 10.0, "price": 3.0, "status": "open", "commission": 0.05}


def _chiusura(**kw):
    base = {"id": 2, "side": "back", "size": 12.0, "price": 2.5, "status": "open",
            "closes_trade_id": 1, "size_requested": 12.0, "size_matched": None,
            "size_remaining": None, "avg_price_matched": None}
    base.update(kw)
    return base


def test_chiusura_abbinata_per_intero_completa_come_prima():
    st = X.hedge_state(APERTURA, [_chiusura(size_matched=12.0, size_remaining=0.0, avg_price_matched=2.5)])
    assert st["complete"] is True
    assert st["residual_size"] == 0.0
    assert st["locked_pnl"] == -2.0
    assert st["blocked"] is False


def test_chiusura_abbinata_in_parte_non_e_completa_e_il_rischio_e_quello_vero():
    st = X.hedge_state(APERTURA, [_chiusura(size_matched=5.0, size_remaining=0.0, avg_price_matched=2.5)])
    assert st["complete"] is False
    assert st["locked_pnl"] is None
    assert st["hedged_size"] == 4.17           # 5 * 2.5 / 3
    assert st["residual_size"] == 5.83
    assert st["if_win"] == -12.5               # -20 + 5*1.5
    assert st["if_lose"] == 5.0                # +10 - 5


def test_riga_vecchia_senza_consapevolezza_resta_il_comportamento_di_sempre():
    st = X.hedge_state(APERTURA, [_chiusura()])  # size_matched None
    assert st["complete"] is True
    assert st["residual_size"] == 0.0


def test_prezzo_medio_abbinato_vince_sul_prezzo_chiesto():
    st = X.hedge_state(APERTURA, [_chiusura(size_matched=12.0, size_remaining=0.0, avg_price_matched=2.6)])
    assert st["hedged_size"] == 10.4           # 12 * 2.6 / 3
    assert st["if_win"] == round(-20 + 12 * 1.6, 2)


def test_residuo_vivo_a_mercato_blocca_una_seconda_chiusura():
    st = X.hedge_state(APERTURA, [_chiusura(size_matched=5.0, size_remaining=7.0, avg_price_matched=2.5)])
    assert st["complete"] is False
    assert st["blocked"] is True


def test_valori_non_finiti_non_contano_come_abbinato():
    st = X.hedge_state(APERTURA, [_chiusura(size_matched=float("nan"))])
    assert st["complete"] is True              # nan = dato assente -> comportamento di sempre
    st2 = X.hedge_state(APERTURA, [_chiusura(size_matched=0.0, size_remaining=0.0)])
    assert st2["complete"] is False            # zero abbinato = zero copertura
    assert st2["residual_size"] == 10.0
