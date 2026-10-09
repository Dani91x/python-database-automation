"""W1-A1 - prove del REVISORE INDIPENDENTE (mutazioni in piu', percorsi di doppio invio).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import threading
import time

import pytest
from betfairlightweight import filters
from betfairlightweight.exceptions import APIError, StatusCodeError

from Betfair.nucleo.betfair import limiti as L
from Betfair.nucleo.betfair import rest as R
from Betfair.nucleo.betfair import sessione as S
from Betfair.nucleo.betfair.tests.test_a1_finto_betfair import (
    OrologioFinto,
    ServerBetfairFinto,
    installa_finto,
)
from Betfair.nucleo.betfair.tests.test_a1_rest import _PARAMETRI_MUTAZIONE, _cliente, _ids


@pytest.fixture
def finto(monkeypatch):
    server = ServerBetfairFinto(OrologioFinto())
    installa_finto(monkeypatch, server)
    return server


@pytest.mark.parametrize("metodo", list(L.METODI_MUTAZIONE))
@pytest.mark.parametrize("guasto", ["timeout", "rete", "http503", "UNEXPECTED_ERROR"])
def test_errore_generico_con_relogin_di_un_altro_thread_non_rimanda_la_mutazione(finto, metodo, guasto):
    """Il thread A manda la mutazione con la sessione di generazione 1; MENTRE la
    richiesta e' in volo, il thread B vede un errore di sessione e rifa' il login
    (generazione 2). La richiesta di A cade poi con un errore GENERICO (timeout: l'ordine
    puo' essere gia' sull'exchange). ``rifai_login(e, gen_vista)`` risponde True
    ("la sessione e' nuova") perche' la generazione e' cambiata: la mutazione NON
    deve comunque ripartire, perche' l'errore di A non e' un rifiuto di sessione.
    Rosso se in ``mutazione`` si toglie ``classifica_errore(e) != "sessione"``."""
    cliente = _cliente(finto)
    cliente._sessione.client()                               # login: generazione 1
    assert cliente._sessione.generazione == 1
    finto.ritardo_s[metodo] = 0.4                            # la richiesta di A resta in volo
    finto.guasta(metodo, guasto)
    esiti = {}

    def _thread_a():
        try:
            cliente.mutazione(metodo, **_PARAMETRI_MUTAZIONE[metodo])
        except Exception as e:  # noqa: BLE001 - interessa solo quante richieste sono partite
            esiti["a"] = e

    a = threading.Thread(target=_thread_a)
    a.start()
    t0 = time.monotonic()
    while finto.conta(metodo) < 1 and time.monotonic() - t0 < 5:
        time.sleep(0.005)
    assert finto.conta(metodo) == 1                          # A e' in volo
    # B: errore di sessione visto con la generazione 1 -> relogin (generazione 2)
    assert cliente._sessione.rifai_login(RuntimeError("INVALID_SESSION_INFORMATION"), 1) is True
    assert cliente._sessione.generazione == 2
    a.join(10)
    assert not a.is_alive()
    assert isinstance(esiti.get("a"), (APIError, StatusCodeError, Exception))
    assert finto.conta(metodo) == 1, "la mutazione e' stata RIMANDATA: possibile ordine doppio"


@pytest.mark.parametrize("guasto", ["timeout", "rete", "http503", "UNEXPECTED_ERROR"])
def test_mutazione_chiamata_dentro_un_except_di_sessione_non_si_ripete_su_errore_generico(finto, guasto):
    """Concatenamento IMPLICITO delle eccezioni (``__context__``): un bot che, dentro il
    suo ``except`` per un errore di sessione di una lettura, chiama ``mutazione`` e riceve
    un errore GENERICO (timeout: l'ordine puo' essere gia' arrivato) vede quel timeout
    agganciato all'errore di sessione. ``e_errore_di_sessione`` percorre la catena
    ``__cause__ or __context__`` e classifica il timeout come "sessione": relogin e RIPETIZIONE.
    ``call_mutating`` di oggi guarda solo ``str(ex)`` e qui NON ripete."""
    cliente = _cliente(finto)
    cliente._sessione.client()
    finto.guasta("placeOrders", guasto)
    try:
        raise RuntimeError("listMarketBook: INVALID_SESSION_INFORMATION")      # la lettura del bot
    except RuntimeError:
        with pytest.raises((APIError, StatusCodeError)):
            cliente.mutazione("placeOrders", **_PARAMETRI_MUTAZIONE["placeOrders"])
    assert finto.conta("placeOrders") == 1, "la mutazione e' stata RIMANDATA su un errore generico"
    assert finto.conta("login") == 1


def test_parita_con_call_mutating_dentro_un_except_di_sessione(monkeypatch):
    """Stessa scena sul codice di OGGI: ``call_mutating`` non ripete (1 invio)."""
    import Betfair.odds_refresh as OR
    from Betfair.omega import omega_market as OM
    from Betfair.stream import auth

    srv = ServerBetfairFinto(OrologioFinto())
    installa_finto(monkeypatch, srv)
    srv.guasta("placeOrders", "timeout")
    c = {"c": None}

    def _get():
        c["c"] = c["c"] or auth.build_client(login=True)
        return c["c"]

    monkeypatch.setattr(OR, "get_shared_client", _get)
    monkeypatch.setattr(OR, "reset_shared_client", lambda: c.update(c=None))
    monkeypatch.setattr(OM, "_segnala_saldo", lambda motivo: None)
    try:
        raise RuntimeError("INVALID_SESSION_INFORMATION")
    except RuntimeError:
        with pytest.raises(APIError):
            OM.call_mutating(lambda cl: cl.betting.place_orders(**_PARAMETRI_MUTAZIONE["placeOrders"]))
    assert srv.conta("placeOrders") == 1


def test_misura_una_mutazione_aspetta_il_keepalive_in_volo(finto):
    """MISURA (non asserzione di correttezza): ``client()`` prende ``_lock`` a ogni
    chiamata e ``rinnova`` tiene lo stesso lucchetto durante l'HTTP di keepAlive/login:
    una cancellazione aspetta tutto il keepAlive in volo."""
    cliente = _cliente(finto)
    cliente._sessione.client()
    finto.ora.avanza(500)                        # keepAlive dovuto (periodo 480)
    finto.ritardo_s["keepAlive"] = 1.0
    t = threading.Thread(target=cliente._sessione.rinnova)
    t.start()
    limite = time.monotonic() + 5            # (W1-A1) attesa limitata: senza keepAlive il test va rosso, non si blocca
    while finto.conta("keepAlive") < 1 and time.monotonic() < limite:
        time.sleep(0.005)
    assert finto.conta("keepAlive") == 1
    t0 = time.monotonic()
    cliente.mutazione("cancelOrders", **_PARAMETRI_MUTAZIONE["cancelOrders"])
    attesa = time.monotonic() - t0
    t.join(5)
    print("attesa della cancellazione:", round(attesa, 2), "s")
    assert attesa < 0.5, f"la cancellazione ha aspettato {attesa:.2f}s il keepAlive"


def test_misura_market_ids_stringa_diventa_lista_di_caratteri(finto):
    cliente = _cliente(finto)
    cliente.lettura("listMarketBook", market_ids="1.234567", lightweight=True)
    inviati = [r["params"]["marketIds"] for r in finto.richieste if r["tipo"] == "listMarketBook"]
    assert inviati == [["1.234567"]], inviati


def test_periodo_keepalive_oltre_la_vita_della_sessione_va_rifiutato(finto):
    with pytest.raises(ValueError):
        S.SessioneBetfair(ora=finto.ora, periodo_keepalive_s=1500.0)


def test_misura_keepalive_regolare_sotto_carico(finto):
    """16 thread martellano il REST (orologio vero) mentre il thread del custode, con
    periodo 0,3 s, tiene la sessione: i keepAlive sul filo devono restare regolari."""
    sessione = S.SessioneBetfair(periodo_keepalive_s=0.3)       # orologio vero (time.monotonic)
    cliente = R.ClienteRestBetfair(sessione, dormi=lambda s: None)
    cliente.lettura("getAccountFunds")
    sessione.avvia(intervallo_s=0.05)
    stop = threading.Event()

    def _martello():
        while not stop.is_set():
            cliente.lettura("getAccountFunds")

    fili = [threading.Thread(target=_martello) for _ in range(16)]
    for f in fili:
        f.start()
    time.sleep(3.0)
    stop.set()
    for f in fili:
        f.join(10)
    sessione.ferma()
    tempi = [r["thread"] for r in finto.richieste if r["tipo"] == "keepAlive"]
    n = len(tempi)
    print("keepAlive sul filo in 3 s con periodo 0,3 s:", n)
    assert 8 <= n <= 11


def test_ban_ricordato_dopo_chiudi_e_riapri_la_sessione_del_processo(finto, monkeypatch):
    """Il freno vive nell'istanza: ``chiudi_sessione_del_processo`` + nuova sessione = freno
    vuoto, ban dimenticato, un login VERO verso Betfair durante i 20 minuti."""
    s1 = S.sessione_del_processo(ora=finto.ora)
    try:
        s1.client()
        finto.guasta("login", "TEMPORARY_BAN_TOO_MANY_REQUESTS")
        finto.invalida_tutti()
        assert s1.rifai_login(RuntimeError("NO_SESSION"), s1.generazione) is False
        n = finto.conta("login")
        S.chiudi_sessione_del_processo()
        s2 = S.sessione_del_processo(ora=finto.ora)
        finto.ora.avanza(30)
        try:
            s2.client()
        except Exception:  # noqa: BLE001
            pass
        assert finto.conta("login") == n, "nuova sessione: un login e' partito durante il ban"
    finally:
        S.chiudi_sessione_del_processo()


def test_blocco_massimo_piu_largo_del_peso_non_supera_mai_i_200_punti(finto):
    """``blocco_massimo`` puo' solo STRINGERE il blocco: con EX_ALL_OFFERS+EX_TRADED (peso 32,
    6 mercati) un blocco_massimo di 25 non deve portare 25 mercati (800 punti, TOO_MUCH_DATA)."""
    cliente = _cliente(finto, blocco_massimo={"listMarketBook": 25})
    pp = filters.price_projection(price_data=["EX_ALL_OFFERS", "EX_TRADED"])
    libri = cliente.lettura("listMarketBook", market_ids=_ids(30), price_projection=pp, lightweight=True)
    assert len(libri) == 30
    assert [len(r["params"]["marketIds"]) for r in finto.richieste if r["tipo"] == "listMarketBook"] == [6] * 5
    assert L.blocchi_per_peso(_ids(30), 32, 25) == [_ids(30)[i:i + 6] for i in range(0, 30, 6)]


def test_login_fallito_il_backoff_del_custode_non_viene_aggirato_dalle_letture(finto):
    """Credenziali rifiutate (login KO per ogni tentativo) e sessione morta: oggi il custode
    ritenta a 15/30/60 s. Qui ogni lettura che vede l'errore di sessione chiama
    ``rifai_login`` -> ``segnala_errore`` riporta ``_prossimo`` a ADESSO: il backoff e'
    scavalcato e il solo freno (20 tentativi/min) limita i login falliti sul filo."""
    cliente = _cliente(finto)
    cliente._sessione.client()
    finto.invalida_tutti()
    finto.guasta("login", *(["INVALID_USERNAME_OR_PASSWORD"] * 60))
    for _ in range(30):
        try:
            cliente.lettura("getAccountFunds")
        except Exception:  # noqa: BLE001
            pass
    falliti = finto.conta("login") - 1
    print("login falliti sul filo in 30 letture, orologio fermo:", falliti)
    assert falliti <= 2, f"{falliti} login falliti verso Betfair senza attendere il backoff del custode"
