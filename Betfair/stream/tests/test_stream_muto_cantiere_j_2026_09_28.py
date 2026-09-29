"""CANTIERE J (28/09/2026) - lo stream di mercato di un processo flumine e' vivo?

Il listener e' quello VERO di betfairlightweight (``StreamListener`` con il suo
``MarketStream``), alimentato con messaggi grezzi nel formato di Betfair
(``op=mcm``, ``ct=SUB_IMAGE``/``HEARTBEAT``, ``status``): e' da li' che nascono
``time_updated`` e ``status``. Il contenitore dello stream di flumine e' un finto
con i soli attributi che ``flumine.streams.basestream.BaseStream`` espone e che
il modulo legge (``_listener``, ``market_filter``, ``stream_id``).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from betfairlightweight import StreamListener

from Betfair.stream import stream_muto as SM


def _listener() -> StreamListener:
    ls = StreamListener(max_latency=None)
    ls.register_stream(1, "marketSubscription")
    return ls


def _msg(ls: StreamListener, **kw) -> None:
    data = {"op": "mcm", "id": 1, "clk": "AAA", "pt": 1789000000000}
    data.update(kw)
    ls.on_data(json.dumps(data))


def _framework(ls: StreamListener, ids=("1.200",)):
    stream = SimpleNamespace(_listener=ls, market_filter={"marketIds": list(ids)}, stream_id=1)
    ordini = SimpleNamespace(_listener=SimpleNamespace(stream=None), market_filter=None, stream_id=2)
    return SimpleNamespace(streams=[stream, ordini])


def test_heartbeat_tiene_vivo_lo_stream_anche_senza_dati():
    ls = _listener()
    _msg(ls, ct="SUB_IMAGE", mc=[])
    _msg(ls, ct="HEARTBEAT")
    st = SM.stato_stream(_framework(ls))
    assert st["vivo"] is True and st["eta_s"] is not None and st["eta_s"] < 2


def test_nessun_messaggio_oltre_soglia_e_muto():
    ls = _listener()
    _msg(ls, ct="HEARTBEAT")
    dopo = datetime.now(timezone.utc) + timedelta(seconds=SM.SOGLIA_S + 1)
    st = SM.stato_stream(_framework(ls), adesso=dopo)
    assert st["vivo"] is False and st["motivo"] == "flusso_interrotto"
    assert st["mercati_fermi"] == ["1.200"]


def test_status_503_e_latente():
    ls = _listener()
    _msg(ls, ct="HEARTBEAT", status=503)
    st = SM.stato_stream(_framework(ls))
    assert st["vivo"] is False and st["motivo"] == "stream_latente"


def test_mai_connesso():
    fw = SimpleNamespace(streams=[SimpleNamespace(_listener=SimpleNamespace(stream=None, status=None),
                                                  market_filter={"marketIds": ["1.1"]}, stream_id=1)])
    st = SM.stato_stream(fw)
    assert st["vivo"] is False and st["motivo"] == "mai_connesso"


def test_nessuno_stream_di_mercato_non_noto():
    assert SM.stato_stream(SimpleNamespace(streams=[]))["vivo"] is None


def test_episodio_detto_una_volta_inizio_e_fine():
    sv = SM.SorvegliaStream()
    muto = {"vivo": False, "motivo": "flusso_interrotto", "eta_s": 16.0}
    vivo = {"vivo": True, "motivo": None, "eta_s": 1.0}
    a = sv.osserva(muto, 100.0, posizione="lay 2,00 su 1.200")
    assert a["code"] == SM.CODICE_INIZIO and a["level"] == "CRITICAL"
    assert "POSIZIONE APERTA NON GESTITA" in a["message"]
    assert sv.osserva(muto, 105.0) is None
    assert sv.osserva(muto, 110.0) is None
    assert sv.dichiarazione(110.0)["muto_da_s"] == 10.0
    f = sv.osserva(vivo, 130.0)
    assert f["code"] == SM.CODICE_FINE
    assert sv.osserva(vivo, 135.0) is None
    assert sv.episodi == 1 and sv.dichiarazione(135.0)["muto_da_s"] is None
