"""Due falsi positivi dei controlli trovati dal coordinatore nel replay del
17/09 sera col motore v3 (scenario `cashout-globale`, 35777617 e 35797769).

A9 giudica SOLO le aperture (lay): il cash-out dell'utente sulla gamba 'Any
Unquoted Draw' (lay 1,00 @65) manda un BACK da 1,48 @44, dimensionato da s*L/B e
non dallo stake; A9 lo accusava come «lay da 1.48 EUR con lo stake fisso a 1.0».

B2 e la barra sotto lo zero: dopo una chiusura in PERDITA il realizzato di
giornata e' negativo e `goal_pct` vale -6,6 %: e' un numero onesto, non un
fuori scala. Il fuori scala vero e' un pct negativo SENZA una perdita, o sopra
il 100 %.

Falsificazione (eseguita dal coordinatore): togliere la condizione sul lato in
`_a9` fa tornare rosso `test_a9_non_giudica_il_back_di_chiusura`; togliere il
riferimento al realizzato in `_b2` fa tornare rosso
`test_b2_accetta_la_barra_sotto_zero_dopo_una_perdita`.
"""
from __future__ import annotations

from Betfair.omega import certificazione as CERT
from Betfair.omega.test_omega_replay_2026_09_16 import ADESSO, _db, _params, _scatta


def _ordine(side: str, size: float) -> CERT.Momento:
    return CERT.Momento(
        tipo="ordine", now=ADESSO, motore="v3",
        params=_params(strategy_version=3, v3_stake_eur=1.0), db=_db(),
        richiesta={"market_id": "1.2", "selection_id": 13, "side": side,
                   "price": 44.0 if side == "back" else 65.0, "size": size,
                   "customer_ref": "omega-t2"})


def test_a9_non_giudica_il_back_di_chiusura():
    # il back di chiusura del cash-out (s*L/B = 1,48) NON e' uno stake d'apertura
    assert "A9" not in _scatta("A9", _ordine("back", 1.48))


def test_a9_accusa_ancora_il_lay_fuori_stake():
    # la direzione opposta: un LAY da 1,48 con stake fisso 1,00 resta un'accusa
    assert "A9" in _scatta("A9", _ordine("lay", 1.48))


def test_a9_verde_sul_lay_esatto():
    assert "A9" not in _scatta("A9", _ordine("lay", 1.0))


def _giro(goal_pct: float, realizzato: float) -> CERT.Momento:
    # chiavi IDENTICHE alle stats del servizio (`omega_service.run_once`)
    return CERT.Momento(
        tipo="giro", now=ADESSO, params=_params(strategy_version=3), db=_db(),
        stats={"target_leg": 0.0, "target_match": 0.0, "goal": 250.0,
               "goal_pct": goal_pct, "realized_effective": realizzato,
               "realized_today": realizzato, "events_today": 1, "legs_today": 2})


def test_b2_accetta_la_barra_sotto_zero_dopo_una_perdita():
    assert "B2" not in _scatta("B2", _giro(-6.6, -16.5))


def test_b2_accusa_un_pct_negativo_senza_perdita():
    assert "B2" in _scatta("B2", _giro(-6.6, 5.0))


def test_b2_accusa_ancora_sopra_il_cento():
    assert "B2" in _scatta("B2", _giro(120.0, 300.0))
