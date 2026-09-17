# -*- coding: utf-8 -*-
"""REPERTO 17/09 (trade live #297, tennis, back 1,03 x 3 EUR): la conferma
dell'apertura in `bot_service._execute` (ramo `out.status == "open"`) scriveva
`db.update_trade(...)` DIRETTO, senza passare da `execution.aggiorna_trade`.
Il blocco `meta.esecuzione` portava i numeri giusti (`size_richiesta 3.0,
size_abbinata 3.0, size_residua 0.0, price_medio 1.03`) ma le CINQUE colonne
nuove della migrazione `trades_consapevolezza_ordine_2026-09-16.sql`
(`size_requested, size_matched, size_remaining, avg_price_matched,
betfair_updated_at`) restavano NULL sulla riga, mentre Omega e Mike le
scrivevano gia' perche' passano da `execution.aggiorna_trade`.

Il fix estrae la conferma in `bot_service._conferma_apertura`, che chiama
`X.aggiorna_trade(..., consapevolezza=out.consapevolezza)`: questo test
verifica quella funzione isolata, col fake db con le STESSE firme del vero
(`update_trade(trade_id, **fields)`, come `bot_db.update_trade`).

FALSIFICAZIONE (obbligatoria, PROCESSO_STANDARD_BOT.md): eseguito PRIMA della
correzione con `db.update_trade` diretto al posto di `X.aggiorna_trade` dentro
`_conferma_apertura` -> ROSSO (le quattro colonne mancavano). Dopo la
correzione -> VERDE. Vedi il referto della sessione per l'output dei due giri.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from Betfair.safe_strategy import bot_service as BS
from Betfair.safe_strategy import execution as X


class FakeDB:
    """Specchio minimo di `bot_db`: stessa firma di `update_trade`, nessuno
    schema (come una riga di dizionario), cosi' non nasconde il difetto sotto
    un fallback che il vero non ha."""

    def __init__(self, trade: dict) -> None:
        self.trades = [dict(trade)]
        self.ultimo_update: dict | None = None

    def update_trade(self, trade_id, **fields):
        self.ultimo_update = dict(fields)
        for t in self.trades:
            if int(t["id"]) == int(trade_id):
                t.update(fields)


def _row_e_out():
    """La riga RISERVATA (come la scrive `_reserve_row`) e l'esito REST reale
    di un'apertura completa: sono i numeri del reperto del 17/09."""
    row = {
        "id": 297,
        "event_id": "35792939",
        "market_id": "1.999",
        "selection_id": 123456,
        "side": "back",
        "price": 1.03,
        "size": 3.0,
        "mode": "live",
        "strategy": "S",
        "meta": {"phase": "reserved", "idempotency_key": "abc"},
    }
    out = X.PlaceOutcome(
        "open", 1.03, 3.0, "443177803518", "live_rest:EXECUTION_COMPLETE",
        esecuzione={
            "price_richiesto": 1.03, "price_medio": 1.03,
            "size_richiesta": 3.0, "size_abbinata": 3.0, "size_residua": 0.0,
        },
        size_requested=3.0, size_remaining=0.0, avg_price_matched=1.03,
        betfair_updated_at="2026-09-17T10:40:00Z",
    )
    return row, out


def test_apertura_scrive_le_colonne_di_consapevolezza():
    row, out = _row_e_out()
    db = FakeDB({"id": row["id"], "status": "pending"})
    meta = {"fill": out.fill_note, "esecuzione": out.esecuzione}

    BS._conferma_apertura(db, row["id"], row, out, meta)

    assert db.ultimo_update is not None, "la conferma non ha mai chiamato update_trade"
    scritto = db.ultimo_update
    # i campi di SEMPRE, invariati
    assert scritto["status"] == "open"
    assert scritto["price"] == 1.03
    assert scritto["size"] == 3.0
    assert scritto["bet_id"] == "443177803518"
    # C.12a — le colonne NUOVE, quelle che mancavano il 17/09
    assert scritto.get("size_requested") == 3.0, scritto
    assert scritto.get("size_matched") == 3.0, scritto
    assert scritto.get("size_remaining") == 0.0, scritto
    assert scritto.get("avg_price_matched") == 1.03, scritto
    assert scritto.get("betfair_updated_at") == "2026-09-17T10:40:00Z", scritto


def test_apertura_paper_scrive_comunque_le_colonne_anche_senza_betfair_updated_at():
    """PAPER=LIVE anche qui: `execution.place` in paper non valorizza
    `betfair_updated_at` (nessun 'placedDate' da un exchange simulato), ma le
    altre quattro colonne devono esserci lo stesso."""
    row, out = _row_e_out()
    row["mode"] = "paper"
    out = X.PlaceOutcome(
        "open", 1.03, 3.0, None, "paper_fill:legacy",
        esecuzione={"size_richiesta": 3.0, "size_abbinata": 3.0, "size_residua": 0.0,
                   "price_medio": 1.03},
        size_requested=3.0, size_remaining=0.0, avg_price_matched=1.03,
    )
    db = FakeDB({"id": row["id"], "status": "pending"})
    meta = {"fill": out.fill_note, "esecuzione": out.esecuzione}

    BS._conferma_apertura(db, row["id"], row, out, meta)

    scritto = db.ultimo_update
    assert scritto.get("size_requested") == 3.0, scritto
    assert scritto.get("size_matched") == 3.0, scritto
    assert scritto.get("size_remaining") == 0.0, scritto
    assert scritto.get("avg_price_matched") == 1.03, scritto
    assert "betfair_updated_at" not in scritto, scritto
