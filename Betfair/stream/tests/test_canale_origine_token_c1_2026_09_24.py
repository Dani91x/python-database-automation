"""C1 (24/09) - ORIGINE + TOKEN sui canali locali (local_channel.py).

Reperto C1 dell'audit delle strade dell'ordine: i canali 47331/47332 accettavano
QUALSIASI connessione locale. Un WebSocket del browser non e' soggetto a CORS:
una pagina web aperta sulla stessa macchina poteva mandare {"m": "order"}.

Server WS VERO su 127.0.0.1 (porta libera), client VERI (websockets.sync):
  * origine estranea -> handshake rifiutato (403), mai un comando in coda;
  * origine dell'app -> accettata; col token il comando entra in coda;
  * comando senza token (o col token sbagliato) -> rifiutato, connessione CHIUSA
    (1008), coda vuota;
  * lettore Python (nessun Origin) -> accettato in sola lettura;
  * 'snapshot' (non esegue) resta libero, come la sveglia.
"""
from __future__ import annotations

import json
import socket
import time

import pytest

from Betfair.stream import local_channel as LC
from Betfair.stream.local_channel import LocalChannel

TOKEN = "0123456789abcdef" * 4          # 64 hex, come quello di desktop/main.js
APP = "http://127.0.0.1:47330"          # origine della UI dell'app (main.js UI_PORT)


def _porta_libera() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _canale(**kw) -> LocalChannel:
    ch = LocalChannel(_porta_libera(), sport="calcio", token=TOKEN, **kw)
    assert ch.start() is True
    return ch


def _attendi_richieste(ch: LocalChannel, attesa_s: float = 1.0) -> list:
    fine = time.time() + attesa_s
    viste: list = []
    while time.time() < fine:
        viste.extend(ch.pop_requests())
        if viste:
            break
        time.sleep(0.02)
    return viste


def _connetti(ch: LocalChannel, percorso: str = "", origin=None):
    from websockets.sync.client import connect

    return connect(f"ws://127.0.0.1:{ch.port}{percorso}", open_timeout=5, origin=origin)


# ---------------------------------------------------------------------------
# Origine
# ---------------------------------------------------------------------------
def test_origine_estranea_rifiutata_all_handshake(caplog):
    from websockets.exceptions import InvalidStatus

    ch = _canale()
    with caplog.at_level("WARNING"):
        with pytest.raises(InvalidStatus) as ex:
            _connetti(ch, f"/?t={TOKEN}", origin="https://pagina-cattiva.example")
    assert ex.value.response.status_code == 403
    # anche col token giusto: l'origine sbagliata non passa, e il motivo e' nel log
    assert ch.statistiche()["rifiutati_origine"] == 1
    assert "origine non ammessa" in caplog.text
    assert ch.pop_requests() == []
    assert ch.is_active() is False


def test_origine_null_mai_ammessa_nemmeno_se_scritta_nella_variabile(monkeypatch):
    from websockets.exceptions import InvalidStatus

    monkeypatch.setenv(LC.ENV_ORIGINI, "null, http://localhost:5173")
    assert "null" not in LC.origini_ammesse()
    assert "http://localhost:5173" in LC.origini_ammesse()
    ch = LocalChannel(_porta_libera(), sport="calcio", token=TOKEN)   # origini dall'env
    assert ch.start() is True
    with pytest.raises(InvalidStatus):
        _connetti(ch, f"/?t={TOKEN}", origin="null")
    # l'origine scritta a mano nella variabile invece passa
    with _connetti(ch, "", origin="http://localhost:5173") as ws:
        assert json.loads(ws.recv(timeout=5))["t"] == "hello"


def test_origine_dell_app_col_token_il_comando_entra_in_coda():
    ch = _canale()
    with _connetti(ch, f"/?t={TOKEN}", origin=APP) as ws:
        assert json.loads(ws.recv(timeout=5))["t"] == "hello"
        ws.send(json.dumps({"id": 1, "m": "order", "p": {"action": "place", "mode": "paper"}}))
        reqs = _attendi_richieste(ch)
        assert len(reqs) == 1 and reqs[0].method == "order"
        assert reqs[0].params == {"action": "place", "mode": "paper"}
        ch.respond(reqs[0], True, {"ok": True})
        assert json.loads(ws.recv(timeout=5)) == {"id": 1, "ok": True, "d": {"ok": True}}
    assert ch.statistiche()["rifiutati_token"] == 0


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("percorso", ["", "/", "/?t=", "/?t=" + "f" * 64, "/?x=" + TOKEN,
                                      f"/?t={TOKEN}&t={TOKEN}"])
def test_comando_senza_token_rifiutato_e_connessione_chiusa(percorso, caplog):
    from websockets.exceptions import ConnectionClosed

    ch = _canale()
    with caplog.at_level("WARNING"):
        with _connetti(ch, percorso, origin=APP) as ws:
            assert json.loads(ws.recv(timeout=5))["t"] == "hello"
            ws.send(json.dumps({"id": 5, "m": "order", "p": {"action": "place", "size": 100}}))
            risposta = json.loads(ws.recv(timeout=5))
            assert risposta["id"] == 5 and risposta["ok"] is False
            assert "token" in risposta["e"] and "NESSUN ordine" in risposta["e"]
            with pytest.raises(ConnectionClosed) as ex:
                ws.recv(timeout=5)
    assert ex.value.rcvd is not None and ex.value.rcvd.code == 1008
    assert ch.pop_requests() == [], "il comando non deve nemmeno entrare in coda"
    assert ch.statistiche()["rifiutati_token"] == 1
    assert "RIFIUTATO" in caplog.text and TOKEN not in caplog.text


def test_client_python_senza_origin_e_senza_token_non_comanda():
    """Un processo locale senza header Origin (es. un bot) si collega, ma non
    puo' mandare ordini: il token decide, non l'assenza dell'origine."""
    from websockets.exceptions import ConnectionClosed

    ch = _canale()
    with _connetti(ch, "") as ws:
        assert json.loads(ws.recv(timeout=5))["t"] == "hello"
        ws.send(json.dumps({"id": 2, "m": "order", "p": {"action": "place"}}))
        assert json.loads(ws.recv(timeout=5))["ok"] is False
        with pytest.raises(ConnectionClosed):
            ws.recv(timeout=5)
    assert ch.pop_requests() == []


def test_snapshot_non_esegue_e_resta_libero_senza_token():
    ch = _canale()
    with _connetti(ch, "", origin=APP) as ws:
        assert json.loads(ws.recv(timeout=5))["t"] == "hello"
        ws.send(json.dumps({"id": 3, "m": "snapshot", "p": {"market_id": "1.1"}}))
        reqs = _attendi_richieste(ch)
        assert [r.method for r in reqs] == ["snapshot"]
    assert ch.statistiche()["rifiutati_token"] == 0


def test_lettore_python_accettato_in_sola_lettura():
    ch = _canale()
    with _connetti(ch, "/lettore/order") as ws:          # nessun Origin: client Python
        assert json.loads(ws.recv(timeout=5))["t"] == "hello"
        fine = time.time() + 2
        while ch.statistiche()["lettori"] < 1 and time.time() < fine:
            time.sleep(0.02)
        ch.publish("order", {"bet_id": "B1"})
        assert json.loads(ws.recv(timeout=5)) == {"t": "order", "d": {"bet_id": "B1"}}
        ws.send(json.dumps({"id": 4, "m": "order", "p": {"action": "place"}}))
        r = json.loads(ws.recv(timeout=5))
        assert r["ok"] is False and "lettore" in r["e"]
    assert ch.pop_requests() == []
    assert ch.is_active() is False, "un lettore non e' un desktop"


def test_lettore_col_token_resta_lettore():
    """Il token non trasforma un lettore in un client che comanda."""
    ch = _canale()
    with _connetti(ch, f"/lettore/order?t={TOKEN}") as ws:
        assert json.loads(ws.recv(timeout=5))["t"] == "hello"
        ws.send(json.dumps({"id": 6, "m": "order", "p": {"action": "place"}}))
        assert json.loads(ws.recv(timeout=5))["ok"] is False
    assert ch.pop_requests() == []


# ---------------------------------------------------------------------------
# Il token di sessione
# ---------------------------------------------------------------------------
def test_token_di_sessione_dall_ambiente(monkeypatch):
    monkeypatch.setenv(LC.ENV_TOKEN, TOKEN)
    assert LC.token_di_sessione() == TOKEN
    ch = LocalChannel(_porta_libera(), sport="tennis")
    assert ch._token_valido(TOKEN) is True
    assert ch._token_valido("f" * 64) is False
    assert ch._token_valido(None) is False


@pytest.mark.parametrize("valore", [None, "", "corto"])
def test_senza_token_valido_nell_ambiente_nessuno_lo_conosce(monkeypatch, valore):
    """Runner avviato fuori dall'app: token casuale, diverso a ogni canale, mai
    vuoto -> nessun comando dal canale (la UI usa la coda DB)."""
    if valore is None:
        monkeypatch.delenv(LC.ENV_TOKEN, raising=False)
    else:
        monkeypatch.setenv(LC.ENV_TOKEN, valore)
    a, b = LC.token_di_sessione(), LC.token_di_sessione()
    assert a != b and len(a) == 64 and a != valore
    ch = LocalChannel(_porta_libera(), sport="calcio")
    assert ch._token_valido(valore or "") is False


def test_token_dal_percorso():
    assert LC.token_dal_percorso(f"/?t={TOKEN}") == TOKEN
    assert LC.token_dal_percorso("/") is None
    assert LC.token_dal_percorso("/?t=") is None
    assert LC.token_dal_percorso(f"/?t={TOKEN}&t=x") is None      # ambiguo: nessuno
    assert LC.token_dal_percorso(None) is None
