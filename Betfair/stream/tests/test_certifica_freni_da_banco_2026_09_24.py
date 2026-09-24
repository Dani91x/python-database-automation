"""24/09 - il banco dichiara i freni degli ordini reali SENZA database, per
tutti i bot: modo ordini "dalla UI" a LIVE senza kill e cache dei settings
di controls a kill spento. Senza, ogni apertura live tentava una lettura del
DB (sandbox: connessione rifiutata) e il replay impiegava ore."""
from __future__ import annotations

from Betfair.stream import modo_ordini as _mo
from Betfair.stream.backtest import certifica as C
from Betfair.stream.trading import controls as _ctl


def test_dentro_il_replay_i_freni_sono_dichiarati_dal_banco(monkeypatch):
    visto: dict = {}
    prima = dict(_ctl._SETTINGS_CACHE)

    class _Ref:
        def __init__(self, event_id):
            self.event_id = event_id
            self.note = []

    def finto_replay(ev, **kw):
        visto["banco"] = bool(_mo._STATO.get("banco"))
        visto["modo"] = _mo._STATO.get("modo")
        visto["kill"] = _mo._STATO.get("kill")
        visto["cache"] = dict(_ctl._SETTINGS_CACHE)
        return _Ref(ev)

    class _Scheda:
        def funzione_replay(self):
            return finto_replay

        def modulo_controlli(self):
            class _M:
                Referto = _Ref
            return _M

    monkeypatch.setattr(C.REG, "bot", lambda nome: _Scheda())
    r, _mem = C._lavora(("finto", "1", "dir", "base", 0, 0))
    assert r.event_id == "1"
    assert visto["banco"] is True and visto["modo"] == "LIVE" and visto["kill"] is False
    assert visto["cache"]["data"] == {"kill_switch": False}
    assert visto["cache"]["ts"] == float("inf")
    # fuori dal replay il banco NON resta dichiarato e la cache torna com'era
    assert not _mo._STATO.get("banco")
    assert dict(_ctl._SETTINGS_CACHE) == prima
