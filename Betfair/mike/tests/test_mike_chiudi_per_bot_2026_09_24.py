"""B16 (24/09/2026) - il «Chiudi» della Control Room cablato PER SINGOLO BOT.

Reperto GRAVISSIMO: il «Chiudi» di una riga di Mike accodava una richiesta a
SAFE (``safe_request('cashout', {trade_id})``): Mike non la leggeva mai e la
posizione restava aperta. Ora la riga di Mike manda ``mike_request('cashout',
{event_id, trade_id, bot, mode})``, cioe' il percorso che il servizio di Mike
esegue gia' (cash out della PARTITA: Mike chiude il ciclo intero, non una
riga).

Qui il lato MIKE, dal ciclo vero (``run_once`` -> ``process_requests`` ->
``_request_flatten`` -> engine ``manual_close``):
  1. la richiesta della riga di Mike arma la chiusura e il giro dopo chiude
     l'ABBINATO nella modalita' della PARTITA, con esito scritto;
  2. altro bot / altra modalita' / riga di un'altra partita / riga
     inesistente = rifiuto con motivo, niente armato, nessun ordine;
  3. il gesto di prima (scheda di Mike: solo ``event_id``) resta valido.

Finti: quelli di ``test_mike_service`` (chiavi di ``mike_*``); le righe di
``mike_trades`` portano ``mode`` come la colonna vera.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from Betfair.mike import db as MDB
from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_audit_2026_09_11 import asdict, fill, live_event
from Betfair.mike.tests.test_mike_feed import KO_IN_FINESTRA, payload, row
from Betfair.mike.tests.test_mike_service import NOW, FakeDB, FakeMarket, legs, run


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    S._LAST_HEARTBEAT.clear()
    S._CONFIG_WARNED.clear()
    S._DAILY_STOP_LOGGED.clear()
    MDB._TOTALS.clear()
    MDB._AGG_RPC.clear()
    monkeypatch.setenv("SAFE_PRE_KO_OU_HOURS", "3")
    yield


def _partita(mode="paper"):
    """Under 3.5 chiesto 10,00 @ 1,50, ABBINATO 6,00 (pre-KO, PRE_OPEN)."""
    db = FakeDB(mode=mode, params={"stake": 10})
    entry = fill(E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                       side="back", price=1.50, size=10.0, ref="under_entry-1-1",
                       cycle_no=1), size=6.0, price=1.50)
    entry.placed_at = NOW.timestamp() - 120
    db.events["E1"] = live_event([asdict(entry)], state_="PRE_OPEN", ctx={}, mode=mode,
                                 ko=KO_IN_FINESTRA)
    db.trades = [{"id": 41, "event_id": "E1", "signal_key": "under_entry-1-1",
                  "status": "open", "mode": mode, "side": "back", "price": 1.50,
                  "size": 6.0, "size_requested": 10.0, "size_matched": 6.0,
                  "pnl": 0, "meta": {}},
                 # una riga di UN'ALTRA partita, stesso bot
                 {"id": 42, "event_id": "E2", "signal_key": "under_entry-1-1",
                  "status": "open", "mode": mode, "pnl": 0, "meta": {}}]
    db._id = 42
    return db


def _richiesta(db, payload_):
    """Una riga di ``mike_requests`` come la scrive la RPC ``mike_request``."""
    db.requests.append({"id": len(db.requests) + 1, "kind": "cashout",
                        "payload": dict(payload_), "status": "pending", "result": None,
                        "created_at": NOW.isoformat()})
    return db.requests[-1]


def _chiusure_manuali(db):
    return [l for l in legs(db) if l["role"] == "manual_close"]


def test_riga_mike_chiusa_dal_suo_bot_sull_abbinato():
    db = _partita()
    mk = FakeMarket()
    req = _richiesta(db, {"event_id": "E1", "trade_id": 41, "bot": "mike", "mode": "paper"})
    run(db, mk, NOW, [row(payload())])
    assert req["status"] == "done", req["result"]
    assert req["result"]["ok"] is True
    t = NOW + timedelta(seconds=2)
    run(db, mk, t, [row(payload(), updated=t)])
    chiusure = _chiusure_manuali(db)
    assert chiusure, legs(db)
    c = chiusure[0]
    assert c["side"] == "lay"
    # L'ABBINATO: 6,00 @ 1,50 coperto a ~1,52 -> ~5,9; il chiesto sarebbe ~9,9
    esposto = sum(float(x["size"]) for x in chiusure)
    assert esposto == pytest.approx(6.0 * 1.50 / float(c["price"]), abs=0.15), chiusure
    assert esposto < 7.0
    # la gamba di chiusura e' nella modalita' della partita (colonna della riga)
    righe_close = [r for r in db.trades if str(r.get("signal_key", "")).startswith("manual_close")]
    assert righe_close and all(r["mode"] == "paper" for r in righe_close), righe_close


@pytest.mark.parametrize("extra, parola", [
    ({"bot": "safe"}, "bot 'safe'"),
    ({"bot": "omega"}, "bot 'omega'"),
    ({"mode": "live"}, "modalita'"),
    ({"trade_id": 42}, "non e' di questa partita"),
    ({"trade_id": 999}, "non esiste"),
])
def test_richiesta_ambigua_rifiutata_niente_armato(extra, parola):
    db = _partita()
    mk = FakeMarket()
    p = {"event_id": "E1", "trade_id": 41, "bot": "mike", "mode": "paper"}
    p.update(extra)
    req = _richiesta(db, p)
    run(db, mk, NOW, [row(payload())])
    assert req["status"] == "rejected", req["result"]
    assert req["result"]["code"] == "richiesta_ambigua"
    assert parola in req["result"]["message"], req["result"]
    ev = db.events["E1"]
    assert not (ev.get("ctx") or {}).get("flatten_pending"), "niente di armato"
    t = NOW + timedelta(seconds=2)
    run(db, mk, t, [row(payload(), updated=t)])
    assert _chiusure_manuali(db) == [], "nessun ordine su una richiesta ambigua"


def test_il_gesto_di_prima_solo_event_id_resta_valido():
    db = _partita()
    mk = FakeMarket()
    req = _richiesta(db, {"event_id": "E1"})
    run(db, mk, NOW, [row(payload())])
    assert req["status"] == "done", req["result"]


def test_partita_live_chiusa_in_live():
    """Riga e partita LIVE, servizio tornato in paper: la chiusura resta LIVE
    (la modalita' congelata sulla partita), mai declassata ne' promossa."""
    seen = {}
    db = _partita(mode="live")
    db.control["mode"] = "paper"
    mk = FakeMarket()
    orig = S._request_flatten

    def spy(db_, market, ev, row_, params, now, dry, **kw):
        seen["mode"] = ev.get("mode")
        return orig(db_, market, ev, row_, params, now, dry, **kw)

    S._request_flatten = spy
    try:
        req = _richiesta(db, {"event_id": "E1", "trade_id": 41, "bot": "mike", "mode": "live"})
        run(db, mk, NOW, [row(payload())])
    finally:
        S._request_flatten = orig
    assert req["status"] == "done", req["result"]
    assert seen["mode"] == "live"
