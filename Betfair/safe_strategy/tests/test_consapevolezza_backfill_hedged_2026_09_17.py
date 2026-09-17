# -*- coding: utf-8 -*-
"""REPERTO 17/09: `reconcile_pending` (via `_racconta_il_vero`) scrive le
colonne di consapevolezza (`size_matched`, `size_remaining`,
`avg_price_matched`, `betfair_updated_at`) SOLO mentre la riga e' ancora
'pending'. Una riga piazzata PRIMA del fix di `bot_service._conferma_apertura`
(17/09) e' passata a 'open' (o poi a 'hedged', chiusura confermata) con quelle
colonne NULL, e nessun percorso la rivisita piu': `_sorveglia_posizione_di_conto`
guarda solo le righe 'open' (mai 'hedged') e per un motivo diverso (chiusura
dell'utente fuori app, non consapevolezza).

`bot_service._completa_consapevolezza_mancante` colma il buco: per le righe
LIVE 'open'/'hedged' che hanno gia' un bet_id e non hanno ancora
`size_matched`, chiede lo stato REALE per bet_id (`market.order_state_by_bet_id`,
lo stesso della riconciliazione) e scrive con `_racconta_il_vero` — che e' la
STESSA funzione che gia' scrive le colonne per le righe 'pending'.

FALSIFICAZIONE (obbligatoria): con la funzione disattivata (o chiamata solo
sulle righe 'pending', come prima) la riga 'hedged' resta con `size_matched`
None per sempre — il test va ROSSO. Vedi il referto della sessione per
l'output del giro falsificato.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from Betfair.safe_strategy import bot_service as S

# id di fantasia MA distinto da quelli usati altrove nella suite: la cache
# module-level `_CONSAPEVOLEZZA_SCRITTA` di `_racconta_il_vero` e' per id, un
# id gia' visto da un altro test la farebbe apparire "gia' scritta".
TRADE_ID = 987298


class FakeDB:
    def __init__(self) -> None:
        self.updates: list[dict] = []

    def update_trade(self, trade_id, **fields):
        self.updates.append({"id": trade_id, **fields})


class FakeMarket:
    """Le sole firme che `_completa_consapevolezza_mancante` usa: lo stato per
    bet_id, con le STESSE chiavi di `omega_market.order_state_by_bet_id`."""

    def __init__(self, stato: dict) -> None:
        self.stato = stato
        self.chiamate: list[str] = []

    def order_state_by_bet_id(self, bet_id: str) -> dict:
        self.chiamate.append(bet_id)
        return self.stato


def _riga_hedged_senza_colonne() -> dict:
    return {"id": TRADE_ID, "mode": "live", "status": "hedged", "bet_id": "b298",
            "size_matched": None, "size_remaining": None, "avg_price_matched": None,
            "meta": {}}


def setup_function(_fn):
    # la cache di `_racconta_il_vero` e' module-level: si azzera per questo id
    # prima di ogni test, cosi' un giro precedente non ne inquina un altro.
    S._CONSAPEVOLEZZA_SCRITTA.pop(TRADE_ID, None)


def test_completa_consapevolezza_su_riga_gia_hedged():
    db = FakeDB()
    stato = {"found": True, "size_matched": 3.0, "avg_price_matched": 1.0602666666666665,
             "size_remaining": 0.0, "matched_date": "2026-09-17T09:00:35Z",
             "placed_date": "2026-09-17T08:55:00Z"}
    market = FakeMarket(stato)
    tr = _riga_hedged_senza_colonne()

    n = S._completa_consapevolezza_mancante(db=db, market=market, rows=[tr])

    assert n == 1
    assert market.chiamate == ["b298"]
    assert len(db.updates) == 1, db.updates
    scritto = db.updates[0]
    assert scritto.get("size_matched") == 3.0, scritto
    assert scritto.get("size_remaining") == 0.0, scritto
    assert scritto.get("avg_price_matched") == 1.0602666666666665, scritto
    assert scritto.get("betfair_updated_at") == "2026-09-17T09:00:35Z", scritto


def test_riga_gia_completa_non_chiama_betfair():
    db = FakeDB()
    market = FakeMarket({"found": True, "size_matched": 1.0})
    tr = _riga_hedged_senza_colonne()
    tr["size_matched"] = 3.0   # gia' riempita: nessun bisogno del backfill
    n = S._completa_consapevolezza_mancante(db=db, market=market, rows=[tr])
    assert n == 0
    assert market.chiamate == []
    assert db.updates == []


def test_riga_paper_non_chiama_betfair():
    """Il paper non ha un ordine vero da interrogare: nessuna chiamata."""
    db = FakeDB()
    market = FakeMarket({"found": True, "size_matched": 1.0})
    tr = _riga_hedged_senza_colonne()
    tr["mode"] = "paper"
    n = S._completa_consapevolezza_mancante(db=db, market=market, rows=[tr])
    assert n == 0
    assert market.chiamate == []


def test_budget_per_ciclo_rispettato():
    """`CONSAPEVOLEZZA_BACKFILL_PER_CICLO` righe al massimo per giro: non tutte
    insieme al primo riavvio dopo tante righe storiche."""
    db = FakeDB()
    stato = {"found": True, "size_matched": 3.0, "avg_price_matched": 1.05,
             "size_remaining": 0.0}
    market = FakeMarket(stato)
    righe = []
    for i in range(S.CONSAPEVOLEZZA_BACKFILL_PER_CICLO + 2):
        S._CONSAPEVOLEZZA_SCRITTA.pop(TRADE_ID + i, None)
        r = _riga_hedged_senza_colonne()
        r["id"] = TRADE_ID + i
        r["bet_id"] = f"b{i}"
        righe.append(r)
    n = S._completa_consapevolezza_mancante(db=db, market=market, rows=righe)
    assert n == S.CONSAPEVOLEZZA_BACKFILL_PER_CICLO
