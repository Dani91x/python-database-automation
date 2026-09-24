# -*- coding: utf-8 -*-
"""B16 (24/09/2026) - il «Chiudi» della Control Room cablato PER SINGOLO BOT.

Reperto GRAVISSIMO: il bottone «Chiudi» di QUALUNQUE riga (Omega, Mike, Safe)
accodava ``safe_request('cashout', {trade_id})``. Il servizio di Safe legge
``trade_id`` nella SUA tabella: un id di Omega poteva chiudere la riga di Safe
con lo stesso numero - una posizione che l'utente non aveva chiesto di toccare.

Qui il lato SAFE, dal ciclo vero (``run_once`` -> ``process_requests`` ->
``_request_cashout`` -> ``execution.close_trade``):
  1. la richiesta della riga Safe (bot, partita, modalita' della riga) chiude
     l'ABBINATO nella modalita' della riga, con esito scritto;
  2. una richiesta di un ALTRO bot con lo stesso id NON tocca la riga di Safe;
  3. partita o modalita' diverse = rifiuto con motivo, nessun ordine;
  4. il gesto di prima (scheda di Safe, solo ``trade_id``) resta valido;
  5. Safe TENNIS passa dallo stesso percorso, nella sua modalita'.

I finti sono quelli di ``test_bot_service`` (chiavi di ``safe_strategy_*``).
"""
from __future__ import annotations

import pytest

from Betfair.safe_strategy import bot_service as S

from test_bot_service import NOW, FakeDB, FakeMarket, _feed_row


def _riga_parziale(db, *, mode="paper", sport="calcio", event_id="1.1"):
    """Lay chiesto 16,00 EUR, ABBINATO 10,00 @ 6,0: ``size`` e' l'abbinato,
    ``size_requested`` il chiesto (colonne della migrazione del 16/09)."""
    return db.insert_trade({
        "event_id": event_id, "event_name": "Home v Away", "sport": sport,
        "strategy": "base", "market_id": "m1", "market_type": "MATCH_ODDS",
        "selection_id": 7, "selection_name": "Home", "side": "lay",
        "size": 10.0, "size_requested": 16.0, "size_matched": 10.0,
        "size_remaining": 0.0, "avg_price_matched": 6.0, "price": 6.0,
        "liability": 50.0, "status": "open", "mode": mode, "commission": 0.05,
        # origin 'manual': le uscite AUTOMATICHE del bot (strategia, fuori
        # perimetro) non toccano la riga, cosi' ogni ordine di chiusura che
        # compare qui e' figlio SOLO della richiesta sotto esame.
        "origin": "manual", "meta": {},
    })


def _richiesta(db, payload):
    """Una riga di ``safe_strategy_requests`` come la scrive ``safe_request``."""
    db._id += 1
    db.requests.append({"id": db._id, "kind": "cashout", "status": "pending",
                        "payload": dict(payload), "result": None,
                        "created_at": S._now().isoformat()})
    return db.requests[-1]


def _chiusure(db, tid):
    return [t for t in db.trades if t.get("closes_trade_id") == tid]


def _giro(db):
    return S.run_once(db=db, market=FakeMarket(), engine=None, now=NOW)


def test_riga_safe_chiusa_dal_suo_bot_sull_abbinato():
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row(back=5.0, lay=5.2)]
    tid = _riga_parziale(db)
    req = _richiesta(db, {"trade_id": tid, "fraction": 1, "bot": "safe",
                          "event_id": "1.1", "mode": "paper"})
    _giro(db)
    assert req["status"] == "done", req["result"]
    figlie = _chiusure(db, tid)
    assert len(figlie) == 1, figlie
    c = figlie[0]
    assert c["side"] == "back" and c["mode"] == "paper" and c["origin"] == "manual"
    # L'ABBINATO (10 @ 6,0 chiuso a 5,0 = 12,00), mai il chiesto (16 -> 19,20)
    assert c["size"] == pytest.approx(12.0, abs=0.01), c["size"]
    assert db.get_trade(tid)["status"] == "hedged"


def test_la_riga_di_un_ALTRO_bot_con_lo_stesso_id_non_tocca_safe():
    """Il reperto esatto: la riga Omega n. X cliccata in Control Room. Il payload
    dichiara ``bot='omega'``: Safe NON deve chiudere la propria riga n. X."""
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row(back=5.0, lay=5.2)]
    tid = _riga_parziale(db)
    req = _richiesta(db, {"trade_id": tid, "fraction": 1, "bot": "omega",
                          "event_id": "1.1", "mode": "paper"})
    _giro(db)
    assert req["status"] == "rejected", req["result"]
    assert req["result"]["rejected"] == "richiesta_ambigua"
    assert "Omega" in req["result"]["message"] or "omega" in req["result"]["message"]
    assert _chiusure(db, tid) == []
    assert db.get_trade(tid)["status"] == "open"
    assert any(k == "skip" and p.get("reason") == "richiesta_ambigua"
               for k, p in db.activity)


@pytest.mark.parametrize("extra, parola", [
    ({"event_id": "9.999"}, "partita"),
    ({"mode": "live"}, "modalita'"),
    ({"bot": "mike"}, "bot 'mike'"),
])
def test_richiesta_ambigua_rifiutata_con_motivo(extra, parola):
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row(back=5.0, lay=5.2)]
    tid = _riga_parziale(db)
    payload = {"trade_id": tid, "fraction": 1, "bot": "safe", "event_id": "1.1",
               "mode": "paper"}
    payload.update(extra)
    req = _richiesta(db, payload)
    _giro(db)
    assert req["status"] == "rejected"
    assert parola in req["result"]["message"], req["result"]
    assert _chiusure(db, tid) == []


def test_il_gesto_di_prima_senza_chiavi_nuove_resta_valido():
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row(back=5.0, lay=5.2)]
    tid = _riga_parziale(db)
    req = _richiesta(db, {"trade_id": tid})
    _giro(db)
    assert req["status"] == "done", req["result"]
    assert len(_chiusure(db, tid)) == 1


def test_la_modalita_della_chiusura_e_quella_della_riga(monkeypatch):
    """Riga LIVE: ``close_trade`` riceve ``mode='live'`` (quella della riga),
    anche con il servizio in paper. Paper e live mai mischiati."""
    from Betfair.safe_strategy import execution as X

    visto = {}

    def _close(**kw):
        visto.update(kw)
        return {"ok": True, "closing_trade_id": 999, "price": 5.0, "size": 12.0}

    monkeypatch.setattr(X, "close_trade", _close)
    db = FakeDB(status="stopped", mode="paper")
    db.scan_rows = [_feed_row(back=5.0, lay=5.2)]
    tid = _riga_parziale(db, mode="live")
    req = _richiesta(db, {"trade_id": tid, "fraction": 1, "bot": "safe",
                          "event_id": "1.1", "mode": "live"})
    _giro(db)
    assert req["status"] == "done", req["result"]
    assert visto["mode"] == "live" and visto["table_prefix"] == "safe"
    assert visto["trade"]["id"] == tid


def test_safe_tennis_stesso_percorso_nella_sua_modalita(monkeypatch):
    from Betfair.safe_strategy import execution as X

    visto = {}

    def _close(**kw):
        visto.update(kw)
        return {"ok": True, "closing_trade_id": 999, "price": 5.0, "size": 12.0}

    monkeypatch.setattr(X, "close_trade", _close)
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row(back=5.0, lay=5.2)]
    tid = _riga_parziale(db, sport="tennis")
    req = _richiesta(db, {"trade_id": tid, "fraction": 1, "bot": "safe",
                          "event_id": "1.1", "mode": "paper"})
    _giro(db)
    assert req["status"] == "done", req["result"]
    assert visto["mode"] == "paper"
    assert visto["extra_row"]["sport"] == "tennis"
