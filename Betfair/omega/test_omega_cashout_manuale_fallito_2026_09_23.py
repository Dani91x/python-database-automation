"""CORREZIONE 23/09/2026 -- tracciamento del CASH OUT MANUALE fallito (Omega).

Reperto del banco (replay `certifica omega` su 35797769 e 35777617, scenario
`chiusura-abbinata-in-parte`): quando `execution.close_trade` fallisce DOPO
avere gia' piazzato l'ordine di chiusura (es. 'chiusura_non_eseguita' porta
comunque `closing_trade_id`), `_manual_cashout` tornava PRIMA di scrivere
l'attivita' `cashout_manual`. Il controllo G1 del banco
(`Betfair/omega/certificazione.py` r.1425-1443, `_ATTIVITA_DI_CHIUSURA_UMANA`)
non trovava nessuna firma umana per quel BACK e lo scambiava per una chiusura
automatica.

Questi test certificano SOLO il tracciamento: nessuna decisione di trading e'
cambiata (stessi prezzi, stessa size, stesso comportamento "bot riapre" dopo
un cash-out manuale ucciso).
"""
from __future__ import annotations

from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_greenup_2026_09_10 import _DB, CS_MID, EID, _trade
from Betfair.omega.test_omega_service import NOW, FakeMarket as FM


def _control(status="idle"):
    return {"status": status, "params": {}}


class _MercatoOK(FM):
    """Book REST OPEN con la selezione del trade -- chiavi identiche al vero
    lettore `_cashout_prices` (che chiama `market.read_book(market_id, {})`)."""

    def read_book(self, market_id, _runner_names):
        return {"market_id": CS_MID, "status": "OPEN",
                "runners": [{"selection_id": 14, "back_price": 7.6, "back_size": 500.0,
                             "lay_price": 8.0, "lay_size": 500.0,
                             "lay_ladder": ((8.0, 500.0),)}]}


def _cashout_activity(db):
    return [p for k, p in db.activity if k == "cashout_manual"]


def test_close_trade_fallito_scrive_cashout_manual_con_esito_fallito(monkeypatch):
    """Se `close_trade` fallisce DOPO avere piazzato l'ordine (closing_trade_id
    presente, come nel ramo 'chiusura_non_eseguita' di execution.close_trade),
    l'attivita' `cashout_manual` va scritta lo stesso -- con esito 'fallito' e
    il motivo -- cosi' il banco (G1) vede la firma umana su quel BACK."""
    db = _DB(_control())
    tr = _trade(db, price=55.0, size=5.0, score="1-0")

    from Betfair.safe_strategy import execution as X

    esito_finto = {"error": "chiusura_non_eseguita", "detail": "REJECTED dal book",
                    "closing_trade_id": 999}
    monkeypatch.setattr(X, "close_trade", lambda **kw: dict(esito_finto))

    out = S._manual_cashout(market=_MercatoOK([], None, None), db=db,
                            payload={"trade_id": tr["id"]}, now=NOW)

    # la funzione continua a ritornare l'errore cosi' com'e' alla UI (nessuna
    # decisione nuova, nessun retry: il chiamante vede lo stesso esito di oggi)
    assert out == esito_finto, out

    righe = _cashout_activity(db)
    assert len(righe) == 1, righe
    riga = righe[0]
    assert riga["trade_id"] == tr["id"]
    assert riga["event_id"] == EID
    assert riga["closing_trade_id"] == 999
    assert riga["esito"] == "fallito"
    assert riga["motivo"] == "chiusura_non_eseguita"
    assert riga["detail"] == "REJECTED dal book"
    assert riga["mode"] == tr.get("mode")
    # la gamba resta APERTA: nessuna decisione di chiusura e' stata presa qui
    assert db.get_trade(tr["id"])["status"] == "open"


def test_close_trade_fallito_senza_closing_trade_id_scrive_comunque_lattivita(monkeypatch):
    """Anche quando `close_trade` fallisce PRIMA di piazzare un ordine (es.
    'chiusura_in_corso', nessun `closing_trade_id`), l'attivita' va scritta lo
    stesso: il banco deve sapere che l'utente ha TENTATO un cash out, anche se
    non e' partito nessun ordine."""
    db = _DB(_control())
    tr = _trade(db, price=55.0, size=5.0, score="1-0")

    from Betfair.safe_strategy import execution as X

    monkeypatch.setattr(X, "close_trade", lambda **kw: {"error": "chiusura_in_corso",
                                                         "pending_closing_ids": [7]})

    out = S._manual_cashout(market=_MercatoOK([], None, None), db=db,
                            payload={"trade_id": tr["id"]}, now=NOW)
    assert out.get("error") == "chiusura_in_corso"

    righe = _cashout_activity(db)
    assert len(righe) == 1, righe
    assert righe[0]["closing_trade_id"] is None
    assert righe[0]["esito"] == "fallito"
    assert righe[0]["motivo"] == "chiusura_in_corso"


def test_close_trade_riuscito_attivita_invariata(monkeypatch):
    """Controprova: sul ramo RIUSCITO l'attivita' resta esattamente come oggi
    -- niente 'esito'/'motivo' (quelle chiavi esistono SOLO sul ramo fallito)."""
    db = _DB(_control())
    tr = _trade(db, price=55.0, size=5.0, score="1-0")

    out = S._manual_cashout(market=_MercatoOK([], None, None), db=db,
                            payload={"trade_id": tr["id"]}, now=NOW)
    assert out.get("ok") is True, out

    righe = _cashout_activity(db)
    assert len(righe) == 1, righe
    riga = righe[0]
    assert "esito" not in riga, riga
    assert "motivo" not in riga, riga
    assert riga["exit_kind"] == "manual"
    opened = db.get_trade(tr["id"])
    assert opened["meta"]["exit_kind"] == "manual"
