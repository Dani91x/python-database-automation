"""26/09 (FIX-C): i runner calcio e tennis usano il CUSTODE della sessione Betfair al
posto del keepAlive che ingoiava l'errore (causa della cecita' delle 10:41Z).
Falsificazione: rimettere `keep_alive` al posto del custode -> rossi."""
import types

import Betfair.stream.runner as R


class _Custode:
    def __init__(self, esito):
        self.esito = esito
        self.tick_chiamate = 0

    def tick(self, adesso=None):
        self.tick_chiamate += 1
        return self.esito


def test_custode_creato_una_volta_per_sessione(monkeypatch):
    creati = []

    class FakeCustode:
        def __init__(self, client, periodo_s):
            creati.append((client, periodo_s))

        def tick(self, adesso=None):
            return None

    import Betfair.stream.auth as A
    monkeypatch.setattr(A, "CustodeSessione", FakeCustode)
    sess = types.SimpleNamespace(context_api_client=object())
    c1 = R._custode_sessione(sess)
    c2 = R._custode_sessione(sess)
    assert c1 is c2 and len(creati) == 1
    assert creati[0][0] is sess.context_api_client
    assert creati[0][1] == R._STREAM_KEEPALIVE_SEC


def test_relogin_ricostruisce_la_subscription_con_le_guardie(monkeypatch):
    chiamate = []
    monkeypatch.setattr(R, "_request_soft_restart", lambda fl, s, reason: chiamate.append(reason) or None)
    alert = []
    monkeypatch.setattr(R.db, "insert_alert", lambda lvl, code, msg: alert.append((lvl, code)))
    R._dopo_relogin(types.SimpleNamespace(), object())
    assert chiamate == ["relogin sessione Betfair (custode)"]
    assert alert == [("CRITICAL", "SESSIONE_BETFAIR")]


def test_il_battito_del_runner_usa_il_custode_e_non_il_vecchio_keep_alive():
    import inspect
    src = inspect.getsource(R.heartbeat_worker)
    assert "_custode_sessione(session).tick(" in src
    assert "_bf_keep_alive(session.context_api_client)" not in src
    assert '"relogin"' in src and "_dopo_relogin(" in src


def test_il_runner_tennis_usa_il_custode():
    import inspect
    import Betfair.stream.tennis_live.tennis_runner as T
    src = inspect.getsource(T._maybe_keepalive)
    assert "CustodeSessione(session.trading" in src and ".tick(now_mono)" in src
    assert "_bf_keep_alive(session.trading)" not in src
