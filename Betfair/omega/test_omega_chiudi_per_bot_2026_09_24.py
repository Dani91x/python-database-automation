"""B16 (24/09/2026) - il «Chiudi» della Control Room cablato PER SINGOLO BOT.

Reperto (l'utente lo definisce GRAVISSIMO): il bottone «Chiudi» di una riga
chiamava la RPC di SAFE per qualunque bot. Su una riga di Omega il clic non
chiudeva niente - oppure, peggio, chiudeva la riga di Safe con lo stesso id
(gli id delle tabelle dei bot collidono).

Qui si certifica il lato OMEGA, dal ciclo vero delle richieste manuali
(``process_manual`` -> ``_manual_cashout`` -> ``execution.close_trade``):
  1. la richiesta della riga Omega (bot, partita, modalita' della riga) chiude
     la posizione ABBINATA, nella modalita' DELLA RIGA, con esito scritto;
  2. una richiesta che dichiara un altro bot, un'altra partita o un'altra
     modalita' e' RIFIUTATA con motivo, e nessun ordine parte;
  3. le richieste di prima (scheda di Omega: solo ``trade_id``) restano valide.

I finti parlano come il vero: la richiesta ha le colonne di
``omega_manual_requests`` (id, kind, payload, status, result, created_at,
processed_at), la riga quelle di ``omega_trades`` (snake_case).
"""
from __future__ import annotations

import pytest

from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_greenup_2026_09_10 import _DB, CS_MID, EID, _trade
from Betfair.omega.test_omega_service import NOW, FakeMarket as FM


class _MercatoOK(FM):
    """Book REST OPEN con la selezione del trade: chiavi identiche al vero
    lettore ``_cashout_prices`` (``market.read_book(market_id, {})``)."""

    def read_book(self, market_id, _runner_names):
        return {"market_id": CS_MID, "status": "OPEN",
                "runners": [{"selection_id": 14, "back_price": 7.6, "back_size": 500.0,
                             "lay_price": 8.0, "lay_size": 500.0,
                             "lay_ladder": ((8.0, 500.0),)}]}


def _db():
    return _DB({"status": "idle", "mode": "paper", "params": {}})


def _richiesta(db, payload, rid=1):
    """Una riga di ``omega_manual_requests`` come la scrive la RPC ``omega_request``."""
    reqs = getattr(db, "manual_reqs", None)
    if reqs is None:
        db.manual_reqs = reqs = []
    reqs.append({"id": rid, "kind": "cashout", "payload": dict(payload),
                 "status": "pending", "result": None,
                 "created_at": NOW.isoformat(), "processed_at": None})
    return reqs[-1]


def _chiusure(db, tid):
    return [t for t in db.trades if t.get("closes_trade_id") == tid]


def _riga_parziale(db, *, mode="paper"):
    """Lay chiesto 8,00 EUR, ABBINATO 5,00 (il residuo e' stato annullato):
    la riga di Omega porta in ``size`` l'abbinato e in ``size_requested`` il
    chiesto, come dopo la conferma di Betfair."""
    tr = _trade(db, price=55.0, size=5.0, score="1-0")
    db.update_trade(tr["id"], mode=mode, size_requested=8.0, size_matched=5.0,
                    size_remaining=0.0, avg_price_matched=55.0)
    return db.get_trade(tr["id"])


def test_riga_omega_chiusa_dal_suo_bot_sull_abbinato_nella_sua_modalita():
    db = _db()
    tr = _riga_parziale(db)
    req = _richiesta(db, {"trade_id": tr["id"], "fraction": 1, "bot": "omega",
                          "event_id": EID, "mode": "paper"})

    n = S.process_manual(market=_MercatoOK([], None, None), db=db, now=NOW)

    assert n == 1
    assert req["status"] == "done", req["result"]
    figlie = _chiusure(db, tr["id"])
    assert len(figlie) == 1, figlie
    c = figlie[0]
    # lato opposto, stessa modalita' della riga, origine manuale
    assert c["side"] == "back" and c["mode"] == "paper" and c["origin"] == "manual"
    # L'ABBINATO, non il chiesto: il green-up di 5,00 @ 55 a 7,6 e' 5*55/7,6
    assert c["size"] == pytest.approx(5.0 * 55.0 / 7.6, abs=0.02), c["size"]
    assert abs(c["size"] - 8.0 * 55.0 / 7.6) > 1.0
    # esito scritto e attivita' di chiusura umana
    assert db.get_trade(tr["id"])["meta"]["exit_kind"] == "manual"
    assert any(k == "cashout_manual" for k, _ in db.activity)


def test_la_modalita_e_quella_della_riga_non_quella_del_servizio(monkeypatch):
    """Riga LIVE con il servizio in paper: la chiusura parte in LIVE (la
    modalita' DELLA RIGA), mai promossa ne' declassata."""
    from Betfair.safe_strategy import execution as X

    visto = {}

    def _close(**kw):
        visto.update(kw)
        return {"ok": True, "closing_trade_id": 999, "price": 7.6, "size": 36.18,
                "locked_pnl": 0.5, "residual_size": 0.0}

    monkeypatch.setattr(X, "close_trade", _close)
    db = _db()
    tr = _riga_parziale(db, mode="live")
    req = _richiesta(db, {"trade_id": tr["id"], "fraction": 1, "bot": "omega",
                          "event_id": EID, "mode": "live"})
    S.process_manual(market=_MercatoOK([], None, None), db=db, now=NOW)
    assert req["status"] == "done", req["result"]
    assert visto["mode"] == "live"
    assert visto["table_prefix"] == "omega"
    assert visto["trade"]["id"] == tr["id"]


@pytest.mark.parametrize("payload_extra, parola", [
    ({"bot": "safe"}, "bot 'safe'"),
    ({"bot": "mike"}, "bot 'mike'"),
    ({"event_id": "9.999"}, "partita"),
    ({"mode": "live"}, "modalita'"),
])
def test_richiesta_ambigua_rifiutata_e_nessun_ordine(payload_extra, parola):
    db = _db()
    tr = _riga_parziale(db)
    payload = {"trade_id": tr["id"], "fraction": 1, "bot": "omega",
               "event_id": EID, "mode": "paper"}
    payload.update(payload_extra)
    req = _richiesta(db, payload)

    S.process_manual(market=_MercatoOK([], None, None), db=db, now=NOW)

    assert req["status"] == "error"
    assert req["result"]["error"] == "richiesta_ambigua"
    assert parola in req["result"]["message"], req["result"]
    assert _chiusure(db, tr["id"]) == [], "nessun ordine su una richiesta ambigua"
    assert db.get_trade(tr["id"])["status"] == "open"
    assert any(k == "error" and p.get("reason") == "richiesta_ambigua"
               for k, p in db.activity)


def test_la_scheda_di_omega_senza_le_chiavi_nuove_resta_valida():
    """Il gesto di prima (``Omega.tsx``: solo ``trade_id``) non viene rotto."""
    db = _db()
    tr = _riga_parziale(db)
    req = _richiesta(db, {"trade_id": tr["id"]})
    S.process_manual(market=_MercatoOK([], None, None), db=db, now=NOW)
    assert req["status"] == "done", req["result"]
    assert len(_chiusure(db, tr["id"])) == 1
