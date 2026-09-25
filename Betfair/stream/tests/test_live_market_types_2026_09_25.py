"""LIVE_MARKET_TYPES (whitelist dei mercati per evento nel runner calcio).

Referto AUDIT_2026-09-25/LIVE_MARKET_TYPES_E_BETA.md. La whitelist proposta
(``config_stream.LIVE_MARKET_TYPES_PROPOSTA``, non ancora attiva: la costante
usata in produzione ``LIVE_MARKET_TYPES`` resta vuota finche' l'utente non la
imposta nel .env) deve coprire OGNI market type che un bot calcio registrato
legge davvero (fonte: registro_bot.py, campo ``mercati``, la stessa che il
test di contratto verifica contro i moduli di produzione) piu' i mercati letti
dallo scanner Safe condiviso per il motore opportunita'/anomaly.

Falsificazione: togliendo CORRECT_SCORE dalla whitelist (usato da omega,
safe_base, safe_esatto) il test diventa rosso (§8 del referto).
"""
from __future__ import annotations

from Betfair.stream import config_stream as CS
from Betfair.safe_strategy import scanner as SC
from Betfair.stream.backtest.registro_bot import REGISTRO

# mercati che lo scanner Safe condiviso tiene sotto quote per il motore
# opportunita'/anomaly (letto da Safe/Omega in decisione, non solo mostrato in
# UI): non hanno una riga propria nel registro perche' non sono di un bot.
MERCATI_SCANNER_OPPORTUNITA = frozenset(SC.OPP_MARKET_TYPES)


def _mercati_bot_calcio() -> frozenset:
    unione = set()
    for bot in REGISTRO.values():
        if bot.sport != "calcio":
            continue
        unione.update(bot.mercati)
    return frozenset(unione)


def test_whitelist_proposta_copre_tutti_i_bot_calcio():
    mancanti = _mercati_bot_calcio() - CS.LIVE_MARKET_TYPES_PROPOSTA
    assert not mancanti, f"mercati usati da un bot calcio ma esclusi dalla whitelist proposta: {mancanti}"


def test_whitelist_proposta_copre_lo_scanner_opportunita():
    mancanti = MERCATI_SCANNER_OPPORTUNITA - CS.LIVE_MARKET_TYPES_PROPOSTA
    assert not mancanti, f"mercati dello scanner opportunita' esclusi dalla whitelist proposta: {mancanti}"


def test_whitelist_proposta_non_e_vuota_e_non_tocca_il_default(monkeypatch):
    # LIVE_MARKET_TYPES (quella USATA dal runner) resta vuota di DEFAULT, cioe'
    # senza la variabile d'ambiente: la whitelist proposta e' solo documentazione.
    # 25/09: il .env del checkout principale ORA imposta LIVE_MARKET_TYPES (scelta
    # dell'utente), quindi il default si verifica ricaricando il modulo a env vuota
    # e poi si ricarica con l'env vero per non alterare gli altri test.
    import importlib

    assert CS.LIVE_MARKET_TYPES_PROPOSTA
    # con l'env impostata la whitelist usata deve stare dentro la proposta
    assert CS.LIVE_MARKET_TYPES <= CS.LIVE_MARKET_TYPES_PROPOSTA
    with monkeypatch.context() as m:
        # stringa vuota (non delenv): config_stream chiama load_dotenv() all'import,
        # che NON sovrascrive una variabile gia' presente, quindi il .env non rientra
        m.setenv("LIVE_MARKET_TYPES", "")
        importlib.reload(CS)
        assert CS.LIVE_MARKET_TYPES == frozenset()
    importlib.reload(CS)  # env ripristinata dal monkeypatch: valori originali


def test_falsificazione_senza_correct_score_il_test_diventa_rosso():
    whitelist_rotta = CS.LIVE_MARKET_TYPES_PROPOSTA - {"CORRECT_SCORE"}
    mancanti = _mercati_bot_calcio() - whitelist_rotta
    assert "CORRECT_SCORE" in mancanti  # omega/safe_base/safe_esatto lo usano
