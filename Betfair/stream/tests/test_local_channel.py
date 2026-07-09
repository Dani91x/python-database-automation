"""Test A7 — canale locale desktop: server WS reale (localhost) + drain nel worker.

MONEY-CRITICAL: i comandi locali passano dallo STESSO _dispatch del path DB con
le STESSE guardie (mode, kill-switch, azioni permesse); l'esito viene risposto
al client e REGISTRATO nella coda DB (audit/follow-through identici).
"""
from __future__ import annotations

import json
import socket
import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

import Betfair.stream.live_order_worker as wk
from Betfair.stream import local_channel
from Betfair.stream.local_channel import LocalChannel, LocalRequest


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---------------------------------------------------------------------------
# Integrazione WS reale (hello, richiesta→coda→risposta, publish)
# ---------------------------------------------------------------------------
def test_ws_roundtrip_and_publish():
    from websockets.sync.client import connect

    port = _free_port()
    ch = LocalChannel(port, sport="calcio")
    assert ch.start() is True
    with connect(f"ws://127.0.0.1:{port}", open_timeout=5) as ws:
        hello = json.loads(ws.recv(timeout=5))
        assert hello["t"] == "hello" and hello["d"]["sport"] == "calcio"
        # il flag attivo si aggiorna alla connessione
        deadline = time.time() + 2
        while not ch.is_active() and time.time() < deadline:
            time.sleep(0.02)
        assert ch.is_active() is True

        ws.send(json.dumps({"id": 7, "m": "order", "p": {"action": "place", "mode": "paper"}}))
        reqs: List[LocalRequest] = []
        deadline = time.time() + 2
        while not reqs and time.time() < deadline:
            reqs = ch.pop_requests()
            time.sleep(0.02)
        assert len(reqs) == 1 and reqs[0].method == "order"
        ch.respond(reqs[0], True, {"ok": True, "bet_id": "B1"})
        res = json.loads(ws.recv(timeout=5))
        assert res == {"id": 7, "ok": True, "d": {"ok": True, "bet_id": "B1"}}

        ch.publish("ladder", {"market_id": "1.1"})
        push = json.loads(ws.recv(timeout=5))
        assert push == {"t": "ladder", "d": {"market_id": "1.1"}}

        ws.send(json.dumps({"id": 8, "m": "boh", "p": {}}))
        err = json.loads(ws.recv(timeout=5))
        assert err["ok"] is False and "sconosciuto" in err["e"]


def test_publish_without_clients_is_noop():
    ch = LocalChannel(_free_port(), sport="calcio")
    assert ch.start() is True
    ch.publish("ladder", {"x": 1})  # nessun client: nessuna eccezione
    assert ch.is_active() is False


# ---------------------------------------------------------------------------
# Drain nel worker (fake channel: nessuna rete)
# ---------------------------------------------------------------------------
class _FakeCh:
    def __init__(self, reqs: List[LocalRequest]) -> None:
        self._reqs = list(reqs)
        self.responses: List[Dict[str, Any]] = []

    def pop_requests(self, max_n: int = 20) -> List[LocalRequest]:
        out, self._reqs = self._reqs[:max_n], self._reqs[max_n:]
        return out

    def respond(self, req: LocalRequest, ok: bool, data: Any = None, error: Optional[str] = None) -> None:
        self.responses.append({"id": req.msg_id, "ok": ok, "d": data, "e": error})


class _RealSb:
    """sb 'reale' fake: cattura insert su coda (registrazione) e audit."""

    def __init__(self) -> None:
        self.queue_inserts: List[Dict[str, Any]] = []
        self.audit: List[Dict[str, Any]] = []

    def table(self, name: str) -> Any:
        sb = self

        class _T:
            def insert(self, payload: Dict[str, Any]) -> "_T":
                self._p = dict(payload)
                self._name = name
                return self

            def execute(self) -> Any:
                if name == wk._TABLE:
                    sb.queue_inserts.append(self._p)
                    return SimpleNamespace(data=[{"id": 555}])
                sb.audit.append(self._p)
                return SimpleNamespace(data=[])

        return _T()


def _req(params: Dict[str, Any], method: str = "order", msg_id: int = 1) -> LocalRequest:
    return LocalRequest(ws=object(), msg_id=msg_id, method=method, params=params)


@pytest.fixture()
def env(monkeypatch):
    state: Dict[str, Any] = {"journal": [], "kill": False}
    monkeypatch.setattr(wk, "_kill_switch", lambda: state["kill"])
    monkeypatch.setattr(wk, "_db_kill_switch", lambda: False)
    monkeypatch.setattr(wk, "_journal_done", lambda _sb, _fl, row, _m: state["journal"].append(dict(row)))
    return state


def test_local_order_dispatched_responded_and_recorded(env, monkeypatch):
    def _ok_dispatch(lsb, _fl, row, mode, _s):
        wk._write_done(lsb, row["id"], {"ok": True, "action": row["action"], "mode": mode, "bet_id": "B9"})

    monkeypatch.setattr(wk, "_dispatch", _ok_dispatch)
    ch = _FakeCh([_req({"action": "place", "mode": "paper", "market_id": "1.1",
                        "selection_id": 111, "side": "back", "price": 2.0, "size": 5})])
    monkeypatch.setattr(local_channel, "_CHANNEL", ch)
    sb = _RealSb()
    n = wk._process_local_requests(sb, SimpleNamespace(), "paper", object())
    assert n == 1
    # risposta IMMEDIATA col risultato catturato
    assert ch.responses[0]["ok"] is True and ch.responses[0]["d"]["bet_id"] == "B9"
    # registrazione nella coda DB (status done, client_ref local<rid>)
    rec = sb.queue_inserts[0]
    assert rec["status"] == "done" and rec["client_ref"].startswith("local")
    assert rec["action"] == "place" and rec["mode"] == "paper"
    # journal chiamato con l'id REALE della riga registrata
    assert env["journal"][0]["id"] == 555


def test_local_kill_blocks_opens_allows_closures(env, monkeypatch):
    env["kill"] = True
    calls: List[str] = []
    monkeypatch.setattr(
        wk, "_dispatch",
        lambda lsb, _fl, row, mode, _s: (
            calls.append(row["action"]),
            wk._write_done(lsb, row["id"], {"ok": True, "action": row["action"], "mode": mode}),
        ),
    )
    ch = _FakeCh([
        _req({"action": "place", "mode": "paper"}, msg_id=1),
        _req({"action": "cashout_all", "mode": "paper", "market_id": "1.1"}, msg_id=2),
    ])
    monkeypatch.setattr(local_channel, "_CHANNEL", ch)
    wk._process_local_requests(_RealSb(), SimpleNamespace(), "paper", object())
    assert calls == ["cashout_all"]  # apertura respinta, chiusura eseguita
    r1 = next(r for r in ch.responses if r["id"] == 1)
    assert r1["ok"] is False and "kill-switch" in r1["e"]


def test_local_mode_mismatch_and_unsupported_action(env, monkeypatch):
    monkeypatch.setattr(wk, "_dispatch", lambda *a: (_ for _ in ()).throw(AssertionError("mai")))
    ch = _FakeCh([
        _req({"action": "place", "mode": "live"}, msg_id=1),          # runner è paper
        _req({"action": "place_submin", "mode": "paper"}, msg_id=2),  # escluso dal locale
    ])
    monkeypatch.setattr(local_channel, "_CHANNEL", ch)
    wk._process_local_requests(_RealSb(), SimpleNamespace(), "paper", object())
    assert ch.responses[0]["ok"] is False and "mode" in ch.responses[0]["e"]
    assert ch.responses[1]["ok"] is False and "non supportata" in ch.responses[1]["e"]


def test_local_dispatch_error_responds_and_records_error(env, monkeypatch):
    def _boom(_lsb, _fl, _row, _m, _s):
        raise ValueError("prezzo non valido")

    monkeypatch.setattr(wk, "_dispatch", _boom)
    ch = _FakeCh([_req({"action": "place", "mode": "paper", "market_id": "1.1"})])
    monkeypatch.setattr(local_channel, "_CHANNEL", ch)
    sb = _RealSb()
    wk._process_local_requests(sb, SimpleNamespace(), "paper", object())
    assert ch.responses[0]["ok"] is False and "prezzo non valido" in ch.responses[0]["e"]
    assert sb.queue_inserts[0]["status"] == "error"
    assert env["journal"] == []  # mai journal su comando fallito


def test_local_snapshot_from_blotter(env, monkeypatch):
    order = SimpleNamespace(lookup=("1.1", 111, 0.0))

    class _Blotter:
        def strategy_orders(self, _s):
            return [order]

    market = SimpleNamespace(market_id="1.1", event_id="ev1", blotter=_Blotter())
    flu = SimpleNamespace(markets=SimpleNamespace(markets={"1.1": market}))
    strategy = SimpleNamespace(
        _order_row=lambda o, event_id, market_id: {"mode": "paper", "bet_id": "B1",
                                                   "market_id": market_id, "event_id": event_id},
        _position_row=lambda m, ev, mid, sel, h: {"market_id": mid, "selection_id": sel},
    )
    ch = _FakeCh([_req({"market_id": "1.1"}, method="snapshot")])
    monkeypatch.setattr(local_channel, "_CHANNEL", ch)
    wk._process_local_requests(_RealSb(), flu, "paper", strategy)
    d = ch.responses[0]["d"]
    assert d["orders"][0]["bet_id"] == "B1"
    assert d["positions"][0]["selection_id"] == 111
