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
    # 24/09: modo EFFETTIVO dichiarato LIVE (tetto .env x scelta dalla UI): qui
    # si prova il canale; la regola del modo ha i suoi test.
    monkeypatch.setattr(wk, "_live_order_mode", lambda: "LIVE")
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



# ---------------------------------------------------------------------------
# d3 (23/09) - il ramo "sveglia" di _on_message (local_channel.py:157), F6
# 18/09: l'unico messaggio che il canale accetta anche in sola lettura, esce
# PRIMA della coda dei comandi, non porta mai un parametro d'ordine.
# ---------------------------------------------------------------------------
def _canale_senza_socket(solo_lettura: bool = True) -> LocalChannel:
    """Il canale VERO, mai avviato: nessun socket, ``_on_message`` testabile
    senza rete (stesso schema di
    ``test_canale_scan_f4_2026_09_18.py::_canale_finto``). ``_send`` e' un
    no-op quando ``_loop`` e' None: qui si cattura la risposta prima.
    """
    ch = LocalChannel(_free_port(), sport="calcio", solo_lettura=solo_lettura)
    ch.risposte: List[Dict[str, Any]] = []
    vero_send = ch._send
    ch._send = lambda ws, payload: ch.risposte.append(payload) or vero_send(ws, payload)
    return ch


def test_sveglia_chiama_su_sveglia_col_payload_e_non_tocca_i_topic():
    """method == 'sveglia' chiama ``_su_sveglia`` col SOLO ``p``; non entra
    mai nella coda dei comandi (nessuno stato di richieste/topic toccato)."""
    ch = _canale_senza_socket()
    ricevuti: List[Dict[str, Any]] = []
    ch.set_sveglia(lambda p: ricevuti.append(p))
    ch._on_message(object(), json.dumps({"id": 9, "m": "sveglia",
                                         "p": {"motivo": "approvazione"}}))
    assert ricevuti == [{"motivo": "approvazione"}]
    assert ch.pop_requests() == []                  # niente in coda dei comandi
    assert ch.risposte == [{"id": 9, "ok": True}]    # ok = (cb is not None)


def test_sveglia_funziona_anche_su_canale_NON_di_sola_lettura():
    """Il ramo sveglia esce PRIMA del controllo ``solo_lettura``: deve
    funzionare identico sia sul canale dei bot (solo_lettura=True) sia su
    quello del runner (solo_lettura=False)."""
    ch = _canale_senza_socket(solo_lettura=False)
    ricevuti: List[Dict[str, Any]] = []
    ch.set_sveglia(lambda p: ricevuti.append(p))
    ch._on_message(object(), json.dumps({"m": "sveglia", "p": {"motivo": "comando"}}))
    assert ricevuti == [{"motivo": "comando"}]
    assert ch.pop_requests() == []


def test_sveglia_con_p_non_dict_passa_un_dict_vuoto():
    """Un ``p`` che non e' un dict (o assente) non deve arrivare cosi' com'e'
    al callback: il canale lo normalizza a ``{}`` (local_channel.py:165-166)."""
    ch = _canale_senza_socket()
    ricevuti: List[Any] = []
    ch.set_sveglia(lambda p: ricevuti.append(p))
    ch._on_message(object(), json.dumps({"id": 1, "m": "sveglia", "p": "boh"}))
    ch._on_message(object(), json.dumps({"id": 2, "m": "sveglia"}))  # "p" assente
    assert ricevuti == [{}, {}]


def test_sveglia_senza_set_sveglia_nessun_errore_messaggio_ignorato():
    """Senza nessuno registrato con ``set_sveglia``: nessuna eccezione, la
    sveglia e' ignorata (nessun comando in coda) e la risposta dichiara
    ``ok: False`` (``cb is None``, local_channel.py:169)."""
    ch = _canale_senza_socket()
    ch._on_message(object(), json.dumps({"id": 2, "m": "sveglia", "p": {"motivo": "comando"}}))
    assert ch.pop_requests() == []
    assert ch.risposte == [{"id": 2, "ok": False}]


def test_sveglia_con_callback_che_solleva_non_ferma_il_canale():
    """Una sveglia non puo' MAI fermare il canale (docstring
    local_channel.py:158-161): un callback che solleva viene inghiottito."""
    ch = _canale_senza_socket()

    def _boom(_p):
        raise RuntimeError("bug nel callback")

    ch.set_sveglia(_boom)
    ch._on_message(object(), json.dumps({"id": 3, "m": "sveglia", "p": {"motivo": "comando"}}))
    # nessuna eccezione propagata fin qui: la callback E' installata quindi
    # risponde comunque ok=True (cb is not None), come una sveglia normale.
    assert ch.risposte == [{"id": 3, "ok": True}]


def test_sveglia_ignora_messaggio_malformato_senza_sollevare():
    """JSON non valido su ``_on_message`` non deve sollevare ne' alterare lo
    stato del canale.

    NOTA (d3, divergenza dal brief da riportare al coordinatore): il codice
    attuale di ``_on_message`` (local_channel.py:183-187) NON tiene un
    contatore dedicato ai messaggi malformati, solo un log a ``debug``;
    ``self._conti`` resta quello di ``publish``/contropressione ("saltati" /
    "saltati_client", vedi ``statistiche()``). Qui si verifica il
    comportamento VERO, senza inventare un contatore che non c'e'.
    """
    ch = _canale_senza_socket()
    prima_conti = dict(ch._conti)
    ch._on_message(object(), "{questo non e' json valido")
    assert ch.pop_requests() == []
    assert ch.risposte == []           # nessun id leggibile: nessuna risposta
    assert ch._conti == prima_conti    # nessun contatore dedicato: stato invariato


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
