"""W1-A1 - ``sessione.py``: UNA sessione per processo, custode di oggi, freno dei login, .it 20 minuti.

Client VERO (``auth.build_client``, il codice di oggi) su trasporto HTTP finto
(``test_a1_finto_betfair``): JSON ufficiali, regole di Betfair nel finto,
orologio finto condiviso. La parita' con il custode di oggi si prova facendo
girare lo STESSO copione sul vecchio (``auth.CustodeSessione`` sul client) e sul
nuovo (``SessioneBetfair``) e confrontando esiti e richieste HTTP.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import threading
import time

import pytest
from betfairlightweight.exceptions import APIError

from Betfair.nucleo.betfair import limiti as L
from Betfair.nucleo.betfair import sessione as S
from Betfair.nucleo.betfair.tests.test_a1_finto_betfair import (
    OrologioFinto,
    ServerBetfairFinto,
    installa_finto,
)


@pytest.fixture
def finto(monkeypatch):
    server = ServerBetfairFinto(OrologioFinto())
    installa_finto(monkeypatch, server)
    yield server
    S.chiudi_sessione_del_processo()


def _sessione(server, **kw) -> S.SessioneBetfair:
    kw.setdefault("ora", server.ora)
    return S.SessioneBetfair(**kw)


def _errore_sessione() -> APIError:
    return APIError({"error": {"code": -32099, "data": {"APINGException": {
        "errorCode": "INVALID_SESSION_INFORMATION"}}}}, method="SportsAPING/v1.0/listMarketBook")


# ---------------------------------------------------------------------------
# endpoint, certificati, nessun effetto alla costruzione
# ---------------------------------------------------------------------------
def test_endpoint_e_certificati_come_oggi(finto):
    s = _sessione(finto)
    c = s.client()
    c.betting.list_event_types()
    c.keep_alive()
    login, rpc, ka = finto.richieste
    assert login["url"] == L.URL_CERTLOGIN_ITALIA
    assert login["cert"] == ("/finto/client-2048.crt", "/finto/client-2048.key")
    assert rpc["url"] == L.URL_BETTING_JSONRPC
    assert ka["url"] == L.URL_KEEPALIVE_ITALIA
    assert ka["headers"]["X-Authentication"] == "TOKSEGRETO0001"
    assert (c.locale, c.session_timeout, c.username) == ("italy", L.VITA_SESSIONE_ITALIA_S, "conto_finto")
    # stesso client del costruttore di oggi
    from Betfair.stream import auth

    vecchio = auth.build_client(login=False)
    for attr in ("identity_uri", "identity_cert_uri", "api_uri", "session_timeout", "cert", "app_key"):
        assert getattr(vecchio, attr) == getattr(c, attr), attr
    assert type(vecchio.session) is type(c.session)


def test_costruire_non_tocca_rete_ne_thread(finto):
    prima = threading.active_count()
    s = _sessione(finto)
    assert finto.richieste == [] and threading.active_count() == prima
    assert s.stato()["connessa"] is False and s.rinnova() is None
    s.client()
    s.client()
    assert finto.tipi() == ["login"]
    assert s.stato()["connessa"] is True and s.generazione == 1


# ---------------------------------------------------------------------------
# PARITA' col custode di oggi: stesso copione, stessi esiti, stesse richieste
# ---------------------------------------------------------------------------
_COPIONE = (
    [(100, (), None), (380, (), None), (0, ("keepAlive", "rete"), None), (480, (), None)]
    + [(15, ("keepAlive", "rete"), None), (30, ("keepAlive", "rete"), None), (60, (), None)]
    + [(480, ("keepAlive", "rete"), None)] + [(t, ("keepAlive", "rete"), None) for t in (15, 30, 60)]
    + [(60, ("keepAlive", "rete"), None)] * 9
    + [(0, ("invalida", ""), None), (480, (), None)]
    + [(0, ("invalida", ""), None), (0, ("login", "rete"), None), (480, (), None), (15, (), None)]
    + [(10, (), "segnala"), (0, (), None)]
)


def _gira_copione(server, tick, segnala):
    esiti = []
    for avanza, guasto, azione in _COPIONE:
        server.ora.avanza(avanza)
        if guasto and guasto[0] == "invalida":
            server.invalida_tutti()
            server.guasti.clear()
        elif guasto:
            server.guasta(*guasto)
        if azione == "segnala":
            segnala(_errore_sessione())
        n = len(server.richieste)
        esito = tick()
        esiti.append((round(server.ora() - 1000.0, 1), esito, tuple(r["tipo"] for r in server.richieste[n:])))
    return esiti


def test_parita_custode_di_oggi_stesso_copione(monkeypatch):
    from Betfair.stream import auth

    vecchio_srv = ServerBetfairFinto(OrologioFinto())
    installa_finto(monkeypatch, vecchio_srv)
    client = auth.build_client(login=True)
    custode = auth.CustodeSessione(client, periodo_s=480.0, ora=vecchio_srv.ora)
    vecchi = _gira_copione(vecchio_srv, custode.tick, custode.segnala_errore)

    nuovo_srv = ServerBetfairFinto(OrologioFinto())
    installa_finto(monkeypatch, nuovo_srv)
    s = _sessione(nuovo_srv, periodo_keepalive_s=480.0)
    s.client()
    nuovi = _gira_copione(nuovo_srv, s.rinnova, s.segnala_errore)

    assert nuovi == vecchi
    assert [r["tipo"] for r in nuovo_srv.richieste] == [r["tipo"] for r in vecchio_srv.richieste]
    assert s.stato()["custode"] == custode.stato()
    # il copione ha davvero esercitato tutte le strade del custode
    assert {e for _, e, _ in vecchi} == {None, "ok", "ko", "relogin"}
    assert sum(1 for _, _, t in vecchi if t == ("login",)) >= 2           # relogin al 90% e dopo NO_SESSION
    assert ("keepAlive", "login") in {t for _, _, t in vecchi}            # NO_SESSION -> login subito


def test_contatori_della_salute_seguono_il_copione(finto):
    s = _sessione(finto, periodo_keepalive_s=480.0)
    s.client()
    esiti = _gira_copione(finto, s.rinnova, s.segnala_errore)
    c = s.stato()["contatori"]
    assert c["login"] + c["login_falliti"] == finto.conta("login")
    assert c["keepalive"] + c["keepalive_falliti"] == finto.conta("keepAlive")
    assert c["relogin"] == s.stato()["custode"]["relogin"] == c["login"] - 1
    assert c["login_falliti"] == 1


# ---------------------------------------------------------------------------
# scadenza della sessione .it (20 minuti) e REPERTO della sessione `rest` di oggi
# ---------------------------------------------------------------------------
def test_sessione_it_scade_senza_keepalive_e_si_rifa(finto):
    s = _sessione(finto)
    c = s.client()
    finto.ora.avanza(L.VITA_SESSIONE_ITALIA_S + 1)
    gen = s.generazione
    with pytest.raises(APIError, match="INVALID_SESSION_INFORMATION") as err:
        c.betting.list_event_types()
    assert s.rifai_login(err.value, gen) is True
    assert s.client().betting.list_event_types()[0].event_type.name == "Soccer"
    assert finto.tipi() == ["login", "listEventTypes", "login", "listEventTypes"]


def test_custode_tiene_viva_la_sessione_oltre_i_20_minuti(finto):
    s = _sessione(finto, periodo_keepalive_s=480.0)
    c = s.client()
    for _ in range(12):                      # 96 minuti, un giro ogni 8 minuti
        finto.ora.avanza(480)
        assert s.rinnova() == "ok"
        c.betting.list_event_types()
    assert finto.conta("login") == 1 and finto.conta("keepAlive") == 12


def test_reperto_rest_del_runner_muore_a_20_minuti(finto, monkeypatch):
    """La sessione JSON-RPC ``rest`` di oggi (``BetfairClient``) non ha keepAlive:
    dopo 20 minuti ogni chiamata fallisce (il reperto A par. 1.7, riprodotto sul finto)."""
    import Betfair.client as vecchio_client

    monkeypatch.setattr(vecchio_client.time, "sleep", lambda s: None)
    rest = vecchio_client.BetfairClient(app_key="finto", username="conto_finto", password="finto",
                                        cert_file="/finto/c.crt", key_file="/finto/c.key",
                                        identity_url=L.URL_CERTLOGIN_ITALIA)
    rest.login_cert()
    rest.betting_rpc("SportsAPING/v1.0/listEventTypes", {"filter": {}})
    finto.ora.avanza(L.VITA_SESSIONE_ITALIA_S + 1)
    with pytest.raises(RuntimeError, match="INVALID_SESSION_INFORMATION"):
        rest.betting_rpc("SportsAPING/v1.0/listEventTypes", {"filter": {}})
    assert finto.conta("listEventTypes") == 1 + 3          # 3 tentativi inutili, nessun relogin
    assert finto.conta("login") == 1


def test_reperto_keepalive_di_omega_con_list_event_types_non_rinnova(finto, monkeypatch):
    """``omega_market.keep_alive`` (``omega_market.py:140-150``, chiamato ogni 600 s da
    ``omega_service.py:8849``) fa ``listEventTypes``: per la regola ufficiale (02 par.
    3.3: la durata .it NON e' estesa dall'attivita' API) la sessione condivisa scade
    comunque a 20 minuti e la chiamata dopo fallisce (oggi la salva il relogin di
    ``call``/``call_mutating``). Prova sul finto, che applica la regola; dal vivo: U-06."""
    import Betfair.client as vecchio_client

    monkeypatch.setattr(vecchio_client.time, "sleep", lambda s: None)
    rest = vecchio_client.BetfairClient(app_key="finto", username="conto_finto", password="finto",
                                        cert_file="/finto/c.crt", key_file="/finto/c.key",
                                        identity_url=L.URL_CERTLOGIN_ITALIA)
    rest.login_cert()
    esiti = []
    for _ in range(2):                                    # il "keepAlive" di Omega a 600 e 1200 s
        finto.ora.avanza(600)
        try:
            rest.betting_rpc("SportsAPING/v1.0/listEventTypes", {"filter": {}}, max_retries=1)
            esiti.append("ok")
        except RuntimeError as e:
            esiti.append("INVALID_SESSION_INFORMATION" if "INVALID_SESSION_INFORMATION" in str(e) else "altro")
    assert esiti == ["ok", "INVALID_SESSION_INFORMATION"]
    assert finto.conta("keepAlive") == 0


# ---------------------------------------------------------------------------
# INVALID_SESSION_INFORMATION visto da piu' thread: UN relogin
# ---------------------------------------------------------------------------
def test_errore_di_sessione_da_otto_thread_un_solo_relogin(finto):
    s = _sessione(finto)
    s.client()
    finto.invalida_tutti()
    gen = s.generazione
    barriera = threading.Barrier(8)
    esiti = []

    def _lavoro():
        barriera.wait()
        esiti.append(s.rifai_login(_errore_sessione(), gen))

    fili = [threading.Thread(target=_lavoro) for _ in range(8)]
    for f in fili:
        f.start()
    for f in fili:
        f.join(10)
    assert esiti == [True] * 8
    assert finto.conta("login") == 2 and s.generazione == 2


def test_rifai_login_ignora_errori_non_di_sessione(finto):
    s = _sessione(finto)
    s.client()
    rete = APIError(None, exception=ConnectionError("x"))
    assert s.rifai_login(rete, s.generazione) is False
    assert s.segnala_errore(rete) is False
    assert finto.conta("login") == 1


# ---------------------------------------------------------------------------
# FRENO dei login (per processo) e ban di Betfair
# ---------------------------------------------------------------------------
def _forza_relogin(s, server) -> bool:
    server.invalida_tutti()
    return s.rifai_login(_errore_sessione(), s.generazione)


def test_freno_tetto_dei_login_riusciti_al_minuto(finto):
    s = _sessione(finto, freno=S.FrenoLogin(tetto_riusciti_al_minuto=3, tetto_tentativi_al_minuto=50,
                                            ora=finto.ora))
    s.client()
    assert [_forza_relogin(s, finto) for _ in range(5)] == [True, True, False, False, False]
    assert finto.conta("login") == 3                      # il 4o e il 5o non sono partiti
    assert s.stato()["freno"]["rifiuti"] == 3 and s.stato()["contatori"]["login_frenati"] == 3
    finto.ora.avanza(61)
    assert _forza_relogin(s, finto) is True and finto.conta("login") == 4


def test_freno_tetto_dei_tentativi_al_minuto(finto):
    s = _sessione(finto, freno=S.FrenoLogin(tetto_riusciti_al_minuto=10, tetto_tentativi_al_minuto=3,
                                            ora=finto.ora))
    s.client()
    finto.guasta("login", "rete", "rete", "rete", "rete")
    assert [_forza_relogin(s, finto) for _ in range(4)] == [False, False, False, False]
    assert finto.conta("login") == 3                      # 1 riuscito + 2 falliti, poi frenato


def test_freno_di_serie_mai_il_ban_di_betfair_anche_in_un_ciclo_impazzito(finto):
    """1000 relogin forzati in 10 minuti (un ciclo che non si ferma): col freno di
    serie Betfair non vede mai piu' di 10 login al minuto e non banna."""
    s = _sessione(finto)
    s.client()
    for _ in range(1000):
        finto.ora.avanza(0.6)
        _forza_relogin(s, finto)
    tempi = [r["t"] for r in finto.richieste if r["tipo"] == "login"]
    assert finto.ban_fino is None
    assert max(sum(1 for u in tempi if t - 60 < u <= t) for t in tempi) <= S.TETTO_LOGIN_RIUSCITI_DI_SERIE
    assert S.TETTO_LOGIN_RIUSCITI_DI_SERIE == 10 and S.TETTO_TENTATIVI_LOGIN_DI_SERIE == 20


def test_ban_di_betfair_ferma_i_login_per_20_minuti(finto):
    s = _sessione(finto)
    s.client()
    finto.guasta("login", L.CODICE_BAN_LOGIN)
    assert _forza_relogin(s, finto) is False
    n = finto.conta("login")
    for _ in range(19):
        finto.ora.avanza(60)
        assert _forza_relogin(s, finto) is False
        assert s.rinnova() in (None, "ko")
    assert finto.conta("login") == n                       # nessun tentativo durante il ban
    assert s.stato()["freno"]["ban_per_altri_s"] == pytest.approx(60.0)
    assert s.stato()["contatori"]["ban_login"] == 1
    finto.ora.avanza(60)
    assert _forza_relogin(s, finto) is True


def test_freno_rifiuta_tetti_oltre_il_conto():
    with pytest.raises(ValueError):
        S.FrenoLogin(tetto_riusciti_al_minuto=101)
    with pytest.raises(ValueError):
        S.FrenoLogin(tetto_riusciti_al_minuto=0)
    assert S.e_ban_login(RuntimeError("API login: TEMPORARY_BAN_TOO_MANY_REQUESTS"))
    assert not S.e_ban_login(RuntimeError("API login: INVALID_USERNAME_OR_PASSWORD"))


def test_primo_login_frenato_non_parte_e_lo_dice(finto):
    freno = S.FrenoLogin(ora=finto.ora)
    freno.registra_ban()
    s = _sessione(finto, freno=freno)
    with pytest.raises(S.LoginFrenato, match="ban"):
        s.client()
    assert finto.richieste == []


def test_primo_login_fallito_stesso_errore_di_build_client(finto):
    from Betfair.stream import auth

    finto.guasta("login", "INVALID_USERNAME_OR_PASSWORD", "INVALID_USERNAME_OR_PASSWORD")
    with pytest.raises(auth.BetfairStreamAuthError) as vecchio:
        auth.build_client(login=True)
    s = _sessione(finto)
    with pytest.raises(auth.BetfairStreamAuthError) as nuovo:
        s.client()
    assert str(nuovo.value) == str(vecchio.value) == "Cert login Betfair fallito (LoginError)"
    assert type(nuovo.value.__cause__) is type(vecchio.value.__cause__)
    assert s.generazione == 0
    s.client()                                             # al giro dopo il login riesce
    assert s.generazione == 1


# ---------------------------------------------------------------------------
# evento sessione_rifatta, stato senza token, thread del custode
# ---------------------------------------------------------------------------
def test_sessione_rifatta_notificata_a_ogni_relogin_mai_al_primo(finto):
    s = _sessione(finto)
    visti = []
    s.alla_sessione_rifatta(lambda: visti.append(finto.ora()))
    s.alla_sessione_rifatta(lambda: (_ for _ in ()).throw(RuntimeError("consumatore rotto")))
    s.client()
    assert visti == []
    _forza_relogin(s, finto)
    finto.ora.avanza(480)
    finto.invalida_tutti()
    assert s.rinnova() == "relogin"
    assert len(visti) == 2


def test_stato_senza_token_con_tutte_le_chiavi(finto):
    s = _sessione(finto)
    s.client()
    _forza_relogin(s, finto)
    st = s.stato()
    assert set(st) == {"nome", "connessa", "generazione", "periodo_keepalive_s", "vita_s", "ultimo_esito",
                       "custode", "freno", "contatori", "thread_custode"}
    assert "TOKSEGRETO" not in repr(st)
    assert st["vita_s"] == 1200.0 and st["periodo_keepalive_s"] == S.PERIODO_KEEPALIVE_DI_SERIE_S == 480.0
    assert st["contatori"]["login"] == 2 and st["contatori"]["relogin"] == 1


def test_thread_del_custode_solo_con_avvia_e_si_ferma(finto):
    s = _sessione(finto, periodo_keepalive_s=480.0)
    s.client()
    nomi = lambda: {t.name for t in threading.enumerate()}  # noqa: E731
    assert "a1-sessione-betfair" not in nomi()
    s.avvia(intervallo_s=0.01)
    assert "a1-sessione-betfair" in nomi() and s.stato()["thread_custode"] is True
    finto.ora.avanza(480)
    limite = time.monotonic() + 5
    while finto.conta("keepAlive") == 0 and time.monotonic() < limite:
        time.sleep(0.01)
    assert finto.conta("keepAlive") == 1
    s.ferma()
    assert "a1-sessione-betfair" not in nomi() and s.stato()["thread_custode"] is False


def test_una_sessione_per_processo_un_login_con_dieci_thread(finto):
    from Betfair.nucleo.betfair import sessione as modulo

    finto.ritardo_s["login"] = 0.05
    prima = modulo.sessione_del_processo(ora=finto.ora)
    fili = [threading.Thread(target=lambda: modulo.sessione_del_processo().client()) for _ in range(10)]
    for f in fili:
        f.start()
    for f in fili:
        f.join(10)
    assert modulo.sessione_del_processo() is prima
    assert finto.conta("login") == 1
    with pytest.raises(ValueError):
        modulo.sessione_del_processo(periodo_keepalive_s=600.0)
    modulo.chiudi_sessione_del_processo()
    assert finto.tipi()[-1] == "logout" and finto.richieste[-1]["url"] == L.URL_LOGOUT_ITALIA
    assert modulo.sessione_del_processo(ora=finto.ora) is not prima


def test_implementa_il_contratto_sessione():
    """Ogni metodo del protocollo ``contratto.Sessione`` esiste con gli stessi parametri."""
    import inspect

    from Betfair.nucleo.betfair import contratto

    nomi = [n for n, v in vars(contratto.Sessione).items() if callable(v) and not n.startswith("_")]
    assert sorted(nomi) == ["client", "rinnova_se_serve", "stato"]
    for n in nomi:
        proto = list(inspect.signature(getattr(contratto.Sessione, n)).parameters)
        impl = list(inspect.signature(getattr(S.SessioneBetfair, n)).parameters)
        assert impl[:len(proto)] == proto, n
