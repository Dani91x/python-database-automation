"""CANTIERE N (28/09/2026) - Omega: una proposta APPROVATA parte solo se la
condizione di uscita vale ancora.

Ordine di oggi (regola del pulsante uscite): "approvata, l'ordine parte sul
mercato di ADESSO e solo se la condizione vale ancora". Fino a oggi
``_manual_cashout`` eseguiva anche una proposta che il bot stesso aveva gia'
marcato ``valutazione.valida = False`` (ordine del 24/09: "la scheda deve
segnalarmi se c'e' ancora o no"): la scheda lo SEGNALA ancora, ma la firma su una
condizione caduta non chiude piu'. Per chiudere comunque resta il "Chiudi"/cash
out dell'utente (che non porta ``motivo_codice`` e non passa di qui).

Percorso vero: il produttore (``omega_proposte.process_proposte_uscita``) scrive
la proposta e la marca non piu' valida; la firma e' quella della RPC
(``DbFinto.approva``: payload conservato + ``approved_at``); l'esecuzione e'
``omega_service._manual_cashout``. Finti = quelli di ``test_omega_proposte_2026_09_17``.
File ASCII-only.
"""
from __future__ import annotations

from datetime import timedelta

from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_proposte_2026_09_17 import (  # noqa: F401 (fixture autouse)
    ADESSO, DbFinto, MercatoFinto, _gira, _lay, _params, _stato_pulito,
)


def _firmata(db: DbFinto) -> dict:
    riga = db.richieste[0]
    db.approva(int(riga["id"]), ADESSO + timedelta(seconds=5))
    return dict(db.richieste[0]["payload"])


def test_firma_su_condizione_caduta_non_chiude():
    db = DbFinto([_lay()])
    assert _gira(db) == 1                                   # proposta valida (cap)
    largo = _params(v3_max_liability_per_leg=1000.0, v3_max_liability_per_match=1000.0)
    assert _gira(db, params=largo) == 0                     # la condizione cade
    payload = _firmata(db)
    assert payload["valutazione"]["valida"] is False
    res = S._manual_cashout(market=MercatoFinto(), db=db, payload=payload,
                            now=ADESSO + timedelta(seconds=6))
    assert res["error"] == "condizione_non_piu_valida"
    assert "Chiudi" in res["message"]
    assert db.get_trade(1)["status"] == "open"
    err = db.payload_di("error")
    assert err["reason"] == "condizione_non_piu_valida"
    assert err["motivo_adesso"] == payload["valutazione"]["motivo_codice"]


def test_firma_su_condizione_valida_passa_il_ricontrollo():
    """Stessa proposta, condizione ancora vera: il ricontrollo non la ferma (il
    finto del mercato non ha prezzi di chiusura, quindi si ferma DOPO, a
    ``prezzi_non_disponibili``: e' la prova che il cancello nuovo e' passato)."""
    db = DbFinto([_lay()])
    assert _gira(db) == 1
    payload = _firmata(db)
    assert payload["valutazione"]["valida"] is True
    res = S._manual_cashout(market=MercatoFinto(), db=db, payload=payload,
                            now=ADESSO + timedelta(seconds=6))
    assert res.get("error") != "condizione_non_piu_valida"


def test_il_cash_out_dell_utente_non_passa_dal_ricontrollo():
    """Un "Cash out" premuto dall'utente non e' una proposta: nessun
    ``motivo_codice``, nessuna ``valutazione`` -> nessun ricontrollo."""
    assert S._condizione_caduta({"trade_id": 1, "fraction": 1.0}) is None
    assert S._condizione_caduta({"motivo_codice": "protezione",
                                 "valutazione": {"valida": True}}) is None
    assert S._condizione_caduta({"motivo_codice": "protezione"}) is None
    assert S._condizione_caduta({"motivo_codice": "protezione",
                                 "valutazione": {"valida": False,
                                                 "motivo_codice": "tenere"}}) == "tenere"


# ---------------------------------------------------------------------------
# 29/09 (verifica del coordinatore): la firma e' ferma al clic; conta cosa il
# produttore pensa ADESSO, in questo giro
# ---------------------------------------------------------------------------
from Betfair.omega import omega_proposte as PR  # noqa: E402


def test_firmata_valida_poi_la_condizione_cade_nel_giro_dopo_non_chiude():
    """La proposta era VALIDA al clic (payload 'pending' con valida=True); nel
    giro dopo il produttore non la propone piu' (il tetto e' stato alzato): la
    firma non chiude."""
    db = DbFinto([_lay()])
    assert _gira(db) == 1
    payload = _firmata(db)                                     # valida al clic
    assert payload["valutazione"]["valida"] is True
    largo = _params(v3_max_liability_per_leg=1000.0, v3_max_liability_per_match=1000.0)
    _gira(db, params=largo, now=ADESSO + timedelta(seconds=5))  # giro dopo
    res = S._manual_cashout(market=MercatoFinto(), db=db, payload=payload,
                            now=ADESSO + timedelta(seconds=6))
    assert res["error"] == "condizione_non_piu_valida"
    assert db.get_trade(1)["status"] == "open"


def test_firma_su_un_motivo_ma_adesso_il_bot_propone_per_un_altro_non_chiude():
    db = DbFinto([_lay()])
    assert _gira(db) == 1
    payload = _firmata(db)
    PR._annota_valutazione({"id": 1}, ADESSO + timedelta(seconds=5), True, "protezione")
    assert payload["motivo_codice"] != "protezione"
    res = S._manual_cashout(market=MercatoFinto(), db=db, payload=payload,
                            now=ADESSO + timedelta(seconds=6))
    assert res["error"] == "condizione_non_piu_valida"
    assert "cambiata" in res["message"]


def test_senza_una_valutazione_di_questo_giro_la_firma_non_chiude():
    """Dopo un riavvio (memoria vuota) o con la gamba non valutabile: fail-closed."""
    db = DbFinto([_lay()])
    assert _gira(db) == 1
    payload = _firmata(db)
    PR._VALUTAZIONI.clear()
    res = S._manual_cashout(market=MercatoFinto(), db=db, payload=payload,
                            now=ADESSO + timedelta(seconds=6))
    assert res["error"] == "condizione_non_piu_valida"
    assert "non verificabile" in res["message"]
