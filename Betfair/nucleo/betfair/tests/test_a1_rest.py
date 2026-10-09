"""W1-A1 - ``rest.py``: il solo punto REST (letture ritentate, mutazioni MAI ritentate, 200 punti, 3 concorrenti).

Client VERO di oggi (``auth.build_client``) sul trasporto HTTP finto di
``test_a1_finto_betfair`` (JSON ufficiali, gzip, regole di Betfair applicate dal
finto con una tabella sua). Parita' col codice di oggi: ``omega_market.call_mutating``
(mutazioni), ``odds_refresh._with_client`` (letture), le funzioni di
classificazione di ``odds_refresh``/``auth``, il ripiego ``listMarketBook`` a
blocchi dello scanner (best back/lay identici).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import threading

import pytest
import requests
from betfairlightweight import filters
from betfairlightweight.exceptions import APIError, StatusCodeError

from Betfair.monitor.registro import Istogramma, Registro
from Betfair.nucleo.betfair import limiti as L
from Betfair.nucleo.betfair import rest as R
from Betfair.nucleo.betfair import sessione as S
from Betfair.nucleo.betfair.salute import SaluteBetfair
from Betfair.nucleo.betfair.tests.test_a1_finto_betfair import (
    OrologioFinto,
    ServerBetfairFinto,
    installa_finto,
    peso_finto,
)
from Betfair.odds_refresh import BetfairLimitHit


@pytest.fixture
def finto(monkeypatch):
    server = ServerBetfairFinto(OrologioFinto())
    installa_finto(monkeypatch, server)
    return server


def _cliente(server, **kw):
    sessione = S.SessioneBetfair(ora=server.ora, salute=kw.pop("salute", None))
    pause = []
    kw.setdefault("dormi", pause.append)
    cliente = R.ClienteRestBetfair(sessione, **kw)
    cliente.pause_viste = pause  # type: ignore[attr-defined]
    return cliente


def _ids(n, base=1000):
    return [f"1.{base + i}" for i in range(n)]


BEST = filters.price_projection(price_data=["EX_BEST_OFFERS"])


# ---------------------------------------------------------------------------
# letture: oggetti veri, parita' col ripiego di oggi (best back/lay identici)
# ---------------------------------------------------------------------------
def _best(book):
    return [(r.selection_id,
             r.ex.available_to_back[0]["price"] if r.ex.available_to_back else None,
             r.ex.available_to_lay[0]["price"] if r.ex.available_to_lay else None) for r in book.runners]


def test_list_market_book_parita_col_ripiego_dello_scanner(finto):
    """Le due fonti sugli stessi 73 mercati: il ciclo di oggi (``poll_books``:
    blocchi da 25, ``client.betting.list_market_book``) e ``lettura``: stessi book,
    stessi best back/lay per runner, stesso ordine."""
    from Betfair.safe_strategy.service import _BOOK_CHUNK

    cliente = _cliente(finto)
    ids = _ids(73)
    client = cliente._sessione.client()
    vecchi = []
    for i in range(0, len(ids), _BOOK_CHUNK):
        vecchi += client.betting.list_market_book(market_ids=ids[i:i + _BOOK_CHUNK], price_projection=BEST)
    nuovi = cliente.lettura("listMarketBook", market_ids=ids, price_projection=BEST)
    assert [b.market_id for b in nuovi] == [b.market_id for b in vecchi] == ids
    assert [_best(b) for b in nuovi] == [_best(b) for b in vecchi]
    assert type(nuovi[0]) is type(vecchi[0])
    # il nuovo usa blocchi da 40 (peso 5): 2 richieste invece di 3, mai oltre 200
    blocchi = [len(r["params"]["marketIds"]) for r in finto.richieste if r["tipo"] == "listMarketBook"]
    assert blocchi == [25, 25, 23, 40, 33]


@pytest.mark.parametrize("price_data", [[], ["EX_BEST_OFFERS"], ["EX_ALL_OFFERS"], ["EX_TRADED"],
                                        ["EX_BEST_OFFERS", "EX_TRADED"], ["EX_ALL_OFFERS", "EX_TRADED"],
                                        ["SP_AVAILABLE", "SP_TRADED"], ["EX_ALL_OFFERS", "EX_BEST_OFFERS"]])
@pytest.mark.parametrize("n", [1, 6, 11, 40, 41, 201])
def test_suddivisione_per_peso_su_griglia_mai_too_much_data(finto, price_data, n):
    cliente = _cliente(finto)
    pp = filters.price_projection(price_data=price_data)
    ids = _ids(n)
    libri = cliente.lettura("listMarketBook", market_ids=ids, price_projection=pp, lightweight=True)
    assert [b["marketId"] for b in libri] == ids
    richieste = [r for r in finto.richieste if r["tipo"] == "listMarketBook"]
    massimo = int(200 // peso_finto(pp))
    assert len(richieste) == -(-n // massimo)
    assert all(peso_finto(pp) * len(r["params"]["marketIds"]) <= 200 for r in richieste)


def test_profondita_e_profit_and_loss_suddivisi(finto):
    cliente = _cliente(finto)
    pp = filters.price_projection(price_data=["EX_BEST_OFFERS"],
                                  ex_best_offers_overrides=filters.ex_best_offers_overrides(best_prices_depth=10))
    assert len(cliente.lettura("listMarketBook", market_ids=_ids(30), price_projection=pp)) == 30
    assert [len(r["params"]["marketIds"]) for r in finto.richieste if r["tipo"] == "listMarketBook"] == [12, 12, 6]
    pnl = cliente.lettura("listMarketProfitAndLoss", market_ids=_ids(120), lightweight=True)
    assert len(pnl) == 120
    assert [len(r["params"]["marketIds"]) for r in finto.richieste
            if r["tipo"] == "listMarketProfitAndLoss"] == [50, 50, 20]


def test_blocco_massimo_e_pausa_fra_blocchi(finto):
    cliente = _cliente(finto, blocco_massimo={"listMarketBook": 25}, pausa_tra_blocchi_s=0.35)
    cliente.lettura("listMarketBook", market_ids=_ids(60), price_projection=BEST)
    assert [len(r["params"]["marketIds"]) for r in finto.richieste if r["tipo"] == "listMarketBook"] == [25, 25, 10]
    assert cliente.pause_viste == [0.35, 0.35]
    assert cliente.lettura("listMarketBook", market_ids=[], price_projection=BEST) == []


def test_letture_non_suddivise_passano_intere(finto):
    cliente = _cliente(finto)
    tipi = cliente.lettura("listEventTypes", filter=filters.market_filter())
    assert tipi[0].event_type.id == "1"
    fondi = cliente.lettura("getAccountFunds")
    assert fondi.available_to_bet_balance == 100.0
    assert finto.richieste[-1]["url"] == "https://api.betfair.com/exchange/account/json-rpc/v1"


def test_metodi_sbagliati_rifiutati_senza_rete(finto):
    cliente = _cliente(finto)
    for metodo in L.METODI_MUTAZIONE:
        with pytest.raises(ValueError, match="mutazione"):
            cliente.lettura(metodo, market_id="1.1", instructions=[])
    with pytest.raises(ValueError, match="non e' una mutazione"):
        cliente.mutazione("listMarketBook", market_ids=["1.1"])
    with pytest.raises(ValueError, match="sconosciuto"):
        cliente.lettura("listaInventata")
    assert finto.richieste == []


# ---------------------------------------------------------------------------
# letture: classificazione degli errori di oggi
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("codice", ["TOO_MANY_REQUESTS", "TOO_MUCH_DATA"])
def test_lettura_limite_stop_pulito_mai_ritentata(finto, codice):
    cliente = _cliente(finto)
    cliente._sessione.client()
    finto.guasta("listEventTypes", codice)
    with pytest.raises(BetfairLimitHit, match=codice):
        cliente.lettura("listEventTypes", filter={})
    assert finto.conta("listEventTypes") == 1 and finto.conta("login") == 1
    assert cliente.salute.stato()["esiti"]["listEventTypes"] == {"limite": 1}


@pytest.mark.parametrize("guasto", ["rete", "timeout", "http503", "UNEXPECTED_ERROR", "SERVICE_BUSY"])
def test_lettura_errore_di_rete_un_ritento_con_pausa(finto, guasto):
    cliente = _cliente(finto)
    finto.guasta("listEventTypes", guasto)
    assert cliente.lettura("listEventTypes", filter={})[0].event_type.name == "Soccer"
    assert finto.conta("listEventTypes") == 2 and finto.conta("login") == 1
    assert cliente.pause_viste == [1.0]
    assert cliente.salute.stato()["ritenti"] == {"listEventTypes": 1}


def test_lettura_due_errori_di_rete_rilancia(finto):
    cliente = _cliente(finto)
    finto.guasta("listEventTypes", "rete", "rete", "rete")
    with pytest.raises(APIError):
        cliente.lettura("listEventTypes", filter={})
    assert finto.conta("listEventTypes") == 2
    finto.guasti.clear()
    tre = _cliente(finto, politica=R.PoliticaLettura(tentativi=3, pause_s=(2.0, 4.0)))
    finto.guasta("listEventTypes", "rete", "rete")
    tre.lettura("listEventTypes", filter={})
    assert tre.pause_viste == [2.0, 4.0]


def test_lettura_sessione_scaduta_relogin_e_ritento(finto):
    cliente = _cliente(finto)
    cliente._sessione.client()
    finto.ora.avanza(1201)
    assert cliente.lettura("listMarketBook", market_ids=_ids(3), price_projection=BEST)[2].market_id == "1.1002"
    assert finto.tipi() == ["login", "listMarketBook", "login", "listMarketBook"]
    assert cliente.pause_viste == []
    assert cliente._sessione.stato()["contatori"]["relogin"] == 1


def test_lettura_errore_permanente_non_ritentata(finto, monkeypatch):
    cliente = _cliente(finto)
    client = cliente._sessione.client()
    chiamate = []

    def _rotta(**kw):
        chiamate.append(kw)
        raise LookupError("runner non trovato")

    monkeypatch.setattr(client.betting, "list_events", _rotta)
    with pytest.raises(LookupError):
        cliente.lettura("listEvents", filter={})
    assert len(chiamate) == 1


@pytest.mark.parametrize("fabbrica,attesa", [
    (lambda: APIError({"error": {"data": {"APINGException": {"errorCode": "TOO_MANY_REQUESTS"}}}}, "m"), "limite"),
    (lambda: APIError({"error": {"data": {"APINGException": {"errorCode": "TOO_MUCH_DATA"}}}}, "m"), "limite"),
    (lambda: APIError({"error": {"data": {"APINGException": {"errorCode": "INVALID_SESSION_INFORMATION"}}}}, "m"),
     "sessione"),
    (lambda: RuntimeError("API keepAlive FAIL: NO_SESSION"), "sessione"),
    (lambda: APIError(None, "m", {}, requests.ConnectionError("x")), "rete"),
    (lambda: StatusCodeError("503"), "rete"),
    (lambda: ValueError("dato"), "permanente"),
    (lambda: KeyError("k"), "permanente"),
    (lambda: APIError({"error": {"data": {"APINGException": {"errorCode": "UNEXPECTED_ERROR"}}}}, "m"), "rete"),
    (lambda: RuntimeError("risposta con X-Authentication: TOKSEGRETO0001"), "rete"),
])
def test_classificazione_coincide_con_le_funzioni_di_oggi(fabbrica, attesa):
    from Betfair.odds_refresh import _is_limit
    from Betfair.stream.auth import e_errore_di_sessione

    e = fabbrica()
    assert R.classifica_errore(e) == attesa
    assert (attesa == "limite") == _is_limit(e)
    assert (attesa == "sessione") == (e_errore_di_sessione(e) and not _is_limit(e))
    assert "TOKSEGRETO" not in R.descrivi_errore(e)


def test_parita_letture_con_odds_refresh_with_client(monkeypatch):
    """``odds_refresh._with_client`` di oggi e ``lettura`` sugli stessi guasti:
    stesso esito e stesse chiamate al metodo; il vecchio rifa' anche il login
    sugli errori di RETE (divergenza dichiarata: il nuovo no, un login in meno)."""
    import Betfair.odds_refresh as OR

    from Betfair.stream import auth

    esiti = {}
    for guasto in ("TOO_MANY_REQUESTS", "INVALID_SESSION_INFORMATION", "rete"):
        # vecchio: la sessione condivisa di oggi (login pigro, reset = nuovo login)
        srv_v = ServerBetfairFinto(OrologioFinto())
        mp = pytest.MonkeyPatch()
        installa_finto(mp, srv_v)
        stato = {"c": None}

        def _get():
            if stato["c"] is None:
                stato["c"] = auth.build_client(login=True)
            return stato["c"]

        mp.setattr(OR, "_get_client", _get)
        mp.setattr(OR, "_reset_client", lambda: stato.update(c=None))
        srv_v.guasta("listEventTypes", guasto)
        try:
            OR._with_client(lambda c: c.betting.list_event_types())
            vecchio = "ok"
        except OR.BetfairLimitHit:
            vecchio = "limite"
        mp.undo()

        srv_n = ServerBetfairFinto(OrologioFinto())
        mp = pytest.MonkeyPatch()
        installa_finto(mp, srv_n)
        srv_n.guasta("listEventTypes", guasto)
        try:
            _cliente(srv_n).lettura("listEventTypes")
            nuovo = "ok"
        except BetfairLimitHit:
            nuovo = "limite"
        mp.undo()
        esiti[guasto] = ((vecchio, srv_v.conta("listEventTypes"), srv_v.conta("login")),
                         (nuovo, srv_n.conta("listEventTypes"), srv_n.conta("login")))
    assert esiti == {
        "TOO_MANY_REQUESTS": (("limite", 1, 1), ("limite", 1, 1)),
        "INVALID_SESSION_INFORMATION": (("ok", 2, 2), ("ok", 2, 2)),
        "rete": (("ok", 2, 2), ("ok", 2, 1)),
    }


# ---------------------------------------------------------------------------
# MUTAZIONI: mai ritentate (falsificazione: "mutazione ritentata -> rosso")
# ---------------------------------------------------------------------------
_PARAMETRI_MUTAZIONE = {
    "placeOrders": {"market_id": "1.1001", "customer_ref": "rif-0001", "instructions": [filters.place_instruction(
        order_type="LIMIT", selection_id=47972, side="BACK",
        limit_order=filters.limit_order(size=2.0, price=1.51, persistence_type="LAPSE"))]},
    "cancelOrders": {"market_id": "1.1001", "instructions": [filters.cancel_instruction(bet_id="345678901234")]},
    "replaceOrders": {"market_id": "1.1001", "instructions": [filters.replace_instruction(
        bet_id="345678901234", new_price=1.6)]},
    "updateOrders": {"market_id": "1.1001", "instructions": [filters.update_instruction(
        bet_id="345678901234", new_persistence_type="PERSIST")]},
}


@pytest.mark.parametrize("metodo", list(L.METODI_MUTAZIONE))
@pytest.mark.parametrize("guasto", ["rete", "timeout", "http503", "UNEXPECTED_ERROR", "TOO_MANY_REQUESTS",
                                    "SERVICE_BUSY"])
def test_mutazione_mai_ritentata(finto, metodo, guasto):
    cliente = _cliente(finto)
    cliente._sessione.client()
    finto.guasta(metodo, guasto)
    with pytest.raises((APIError, StatusCodeError)):
        cliente.mutazione(metodo, **_PARAMETRI_MUTAZIONE[metodo])
    assert finto.conta(metodo) == 1                       # UNA richiesta sul filo
    assert finto.conta("login") == 1 and cliente.pause_viste == []


@pytest.mark.parametrize("metodo", list(L.METODI_MUTAZIONE))
def test_mutazione_riuscita_una_richiesta_esito_vero(finto, metodo):
    cliente = _cliente(finto)
    esito = cliente.mutazione(metodo, **_PARAMETRI_MUTAZIONE[metodo])
    assert finto.conta(metodo) == 1
    assert esito.status == "SUCCESS"
    if metodo == "placeOrders":
        assert esito.place_instruction_reports[0].bet_id == "345678901234"
        assert finto.richieste[-1]["params"]["customerRef"] == "rif-0001"


def test_mutazione_sessione_non_valida_una_ripetizione_dopo_relogin(finto):
    cliente = _cliente(finto)
    cliente._sessione.client()
    finto.invalida_tutti()
    cliente.mutazione("placeOrders", **_PARAMETRI_MUTAZIONE["placeOrders"])
    assert finto.tipi() == ["login", "placeOrders", "login", "placeOrders"]
    # senza la parita' con call_mutating: nessuna ripetizione
    spenta = _cliente(finto, rifai_mutazione_su_sessione=False)
    spenta._sessione.client()
    finto.invalida_tutti()
    n = finto.conta("placeOrders")
    with pytest.raises(APIError, match="INVALID_SESSION_INFORMATION"):
        spenta.mutazione("placeOrders", **_PARAMETRI_MUTAZIONE["placeOrders"])
    assert finto.conta("placeOrders") == n + 1


def test_mutazione_relogin_frenato_nessuna_ripetizione(finto):
    freno = S.FrenoLogin(tetto_riusciti_al_minuto=1, ora=finto.ora)
    cliente = R.ClienteRestBetfair(S.SessioneBetfair(ora=finto.ora, freno=freno), dormi=lambda s: None)
    cliente._sessione.client()
    finto.invalida_tutti()
    with pytest.raises(APIError, match="INVALID_SESSION_INFORMATION"):
        cliente.mutazione("placeOrders", **_PARAMETRI_MUTAZIONE["placeOrders"])
    assert finto.conta("placeOrders") == 1 and finto.conta("login") == 1


def test_parita_mutazioni_con_call_mutating(monkeypatch):
    """``omega_market.call_mutating`` di oggi e ``mutazione`` sugli stessi guasti:
    stesse chiamate. Divergenza DICHIARATA: oggi NO_APP_KEY/INVALID_APP_KEY
    contano come sessione (relogin + ripetizione), nel nuovo no (classificazione
    di ``auth``): una ripetizione in meno, mai una in piu'."""
    import Betfair.odds_refresh as OR
    from Betfair.omega import omega_market as OM

    tabella = {}
    for guasto in ("rete", "timeout", "UNEXPECTED_ERROR", "TOO_MANY_REQUESTS", "INVALID_SESSION_INFORMATION",
                   "NO_SESSION", "NO_APP_KEY", "INVALID_APP_KEY"):
        conteggi = []
        for lato in ("vecchio", "nuovo"):
            srv = ServerBetfairFinto(OrologioFinto())
            mp = pytest.MonkeyPatch()
            installa_finto(mp, srv)
            srv.guasta("placeOrders", guasto)
            if lato == "vecchio":
                from Betfair.stream import auth

                stato = {"c": None}

                def _get():
                    if stato["c"] is None:
                        stato["c"] = auth.build_client(login=True)
                    return stato["c"]

                mp.setattr(OR, "get_shared_client", _get)
                mp.setattr(OR, "reset_shared_client", lambda: stato.update(c=None))
                mp.setattr(OM, "_segnala_saldo", lambda motivo: None)
                try:
                    OM.call_mutating(lambda c: c.betting.place_orders(**_PARAMETRI_MUTAZIONE["placeOrders"]))
                except Exception:  # noqa: BLE001 - qui conta solo quante volte e' partita
                    pass
            else:
                try:
                    _cliente(srv).mutazione("placeOrders", **_PARAMETRI_MUTAZIONE["placeOrders"])
                except Exception:  # noqa: BLE001
                    pass
            mp.undo()
            conteggi.append(srv.conta("placeOrders"))
        tabella[guasto] = tuple(conteggi)
    assert tabella == {"rete": (1, 1), "timeout": (1, 1), "UNEXPECTED_ERROR": (1, 1), "TOO_MANY_REQUESTS": (1, 1),
                       "INVALID_SESSION_INFORMATION": (2, 2), "NO_SESSION": (2, 2),
                       "NO_APP_KEY": (2, 1), "INVALID_APP_KEY": (2, 1)}


# ---------------------------------------------------------------------------
# tetto delle 3 richieste concorrenti per conto (thread veri)
# ---------------------------------------------------------------------------
def _in_parallelo(n, fn):
    barriera = threading.Barrier(n)
    errori = []

    def _lavoro(i):
        barriera.wait()
        try:
            fn(i)
        except Exception as e:  # noqa: BLE001
            errori.append(e)

    fili = [threading.Thread(target=_lavoro, args=(i,)) for i in range(n)]
    for f in fili:
        f.start()
    for f in fili:
        f.join(30)
    return errori


def test_tre_concorrenti_per_conto_sui_metodi_contesi(finto):
    cliente = _cliente(finto)
    cliente._sessione.client()
    finto.ritardo_s.update({"listCurrentOrders": 0.05, "listMarketProfitAndLoss": 0.05, "listMarketBook": 0.05})

    def _contesa(i):
        if i % 3 == 0:
            cliente.lettura("listCurrentOrders")
        elif i % 3 == 1:
            cliente.lettura("listMarketProfitAndLoss", market_ids=_ids(2, base=i * 10))
        else:
            cliente.lettura("listMarketBook", market_ids=_ids(2, base=i * 10), price_projection=BEST,
                            order_projection="EXECUTABLE")

    assert _in_parallelo(9, _contesa) == []
    assert finto.max_contesi_in_volo == 3
    assert cliente.salute.stato()["attesa_tetto"]["n"] == 9


def test_letture_non_contese_non_frenate(finto):
    cliente = _cliente(finto)
    cliente._sessione.client()
    finto.ritardo_s["listMarketBook"] = 0.1
    assert _in_parallelo(6, lambda i: cliente.lettura("listMarketBook", market_ids=_ids(2, base=i * 10),
                                                        price_projection=BEST)) == []
    assert finto.max_in_volo["listMarketBook"] > 3


def test_due_clienti_dello_stesso_conto_condividono_il_tetto(finto):
    sessione = S.SessioneBetfair(ora=finto.ora)
    a = R.ClienteRestBetfair(sessione, dormi=lambda s: None)
    b = R.ClienteRestBetfair(sessione, dormi=lambda s: None)
    sessione.client()
    finto.ritardo_s["listCurrentOrders"] = 0.05
    assert _in_parallelo(8, lambda i: (a if i % 2 else b).lettura("listCurrentOrders")) == []
    assert finto.max_contesi_in_volo == 3
    assert R.tetto_del_conto("conto_finto") is R.tetto_del_conto("conto_finto")
    with pytest.raises(ValueError):
        R.tetto_del_conto("conto_finto", 2)
    with pytest.raises(ValueError):
        R.tetto_del_conto("altro", 4)


def test_coda_del_conto_piena_oltre_l_attesa(finto):
    cliente = _cliente(finto, attesa_tetto_s=0.05, politica=R.PoliticaLettura(tentativi=1))
    cliente._sessione.client()
    sem = R.tetto_del_conto("conto_finto")
    presi = [sem.acquire(timeout=1) for _ in range(3)]
    try:
        with pytest.raises(R.CodaContoPiena):
            cliente.lettura("listCurrentOrders")
    finally:
        for p in presi:
            if p:
                sem.release()
    assert finto.conta("listCurrentOrders") == 0
    cliente.lettura("listCurrentOrders")


# ---------------------------------------------------------------------------
# Connection keep-alive, gzip, UNA sessione HTTP
# ---------------------------------------------------------------------------
def test_keep_alive_gzip_e_una_sola_sessione_http(finto):
    cliente = _cliente(finto)
    risposte = []
    cliente._sessione.client().session.hooks["response"].append(lambda r, *a, **k: risposte.append(r))
    cliente.lettura("listMarketBook", market_ids=_ids(90), price_projection=BEST)
    cliente.lettura("listCurrentOrders")
    cliente.mutazione("placeOrders", **_PARAMETRI_MUTAZIONE["placeOrders"])
    rpc = [r for r in finto.richieste if r["tipo"] not in ("login", "keepAlive")]
    assert len(rpc) == 5
    for r in rpc:
        assert r["headers"]["Connection"] == "keep-alive"
        assert "gzip" in r["headers"]["Accept-Encoding"]
        assert r["headers"]["X-Authentication"] == "TOKSEGRETO0001"
        assert "Expect" not in r["headers"]
    assert finto.sessioni_http == {1}
    assert all(r.headers["Content-Encoding"] == "gzip" for r in risposte)


# ---------------------------------------------------------------------------
# Salute: contatori, latenze p50/p99, compatibilita' col modulo Salute
# ---------------------------------------------------------------------------
def test_salute_latenze_p50_p99_come_il_monitor(finto):
    finto.avanza_orologio_s.update({"listMarketBook": 0.0625, "listCurrentOrders": 0.25})
    cliente = R.ClienteRestBetfair(S.SessioneBetfair(ora=finto.ora), orologio=finto.ora, dormi=lambda s: None)
    for _ in range(3):
        cliente.lettura("listMarketBook", market_ids=_ids(2), price_projection=BEST)
    cliente.lettura("listCurrentOrders")
    lat = cliente.salute.stato()["latenze"]
    attesa = Istogramma()
    for _ in range(3):
        attesa.aggiungi(62.5)
    assert lat["listMarketBook"]["secchi"] == attesa.riassunto()["secchi"]
    assert (lat["listMarketBook"]["n"], lat["listMarketBook"]["p50"], lat["listMarketBook"]["p99"]) == (3, 62.5, 62.5)
    assert (lat["listCurrentOrders"]["p50"], lat["listCurrentOrders"]["p99"]) == (250.0, 250.0)
    assert cliente.salute.stato()["esiti"] == {"listCurrentOrders": {"ok": 1}, "listMarketBook": {"ok": 3}}


def test_salute_inoltro_al_registro_del_monitor_con_nomi_propri(finto):
    from Betfair.monitor import sonde

    registro = Registro()
    salute = SaluteBetfair(inoltra_a=registro)
    cliente = _cliente(finto, salute=salute)
    risposte = []
    cliente._sessione.client().session.hooks["response"].append(lambda r, *a, **k: risposte.append(r))
    finto.guasta("listEventTypes", "rete")
    cliente.lettura("listEventTypes")
    cliente.lettura("listMarketBook", market_ids=_ids(2), price_projection=BEST)
    foto = registro.fotografa_e_azzera()
    assert foto["contatori"]["betfair_sessione"] == {"login": 1}
    assert foto["contatori"]["betfair_rest_esiti"] == {"listEventTypes ok": 1, "listEventTypes rete": 1,
                                                       "listMarketBook ok": 1}
    assert set(foto["tratti"]) == {"a1_rest_ms.listEventTypes", "a1_rest_ms.listMarketBook"}
    assert not set(foto["contatori"]) & {"betfair_rest", "betfair_rest_errori"}   # niente doppioni col gancio HTTP
    # i nomi dei metodi sono gli stessi che il gancio del monitor legge dalle risposte
    assert {sonde._metodo_betfair(r) for r in risposte} == {"listEventTypes", "listMarketBook"}


def test_salute_inoltro_rotto_non_rompe_la_chiamata(finto):
    class _Rotto:
        def conta(self, *a):
            raise RuntimeError("monitor rotto")

        def tratto(self, *a):
            raise RuntimeError("monitor rotto")

    cliente = _cliente(finto, salute=SaluteBetfair(inoltra_a=_Rotto()))
    assert cliente.lettura("listEventTypes")[0].event_type.id == "1"
    with pytest.raises(KeyError):
        cliente.salute.evento_sessione("inventata")


def test_sessione_scaduta_vista_da_sei_thread_un_solo_relogin(finto):
    cliente = _cliente(finto)
    cliente._sessione.client()
    finto.invalida_tutti()
    finto.ritardo_s["listEventTypes"] = 0.02
    assert _in_parallelo(6, lambda i: cliente.lettura("listEventTypes")) == []
    assert finto.conta("login") == 2
    assert finto.conta("listEventTypes") == 12


def test_implementa_il_contratto_cliente_rest():
    import inspect

    from Betfair.nucleo.betfair import contratto

    nomi = [n for n, v in vars(contratto.ClienteRest).items() if callable(v) and not n.startswith("_")]
    assert sorted(nomi) == ["lettura", "mutazione"]
    for n in nomi:
        proto = [(p.name, p.kind) for p in inspect.signature(getattr(contratto.ClienteRest, n)).parameters.values()]
        impl = [(p.name, p.kind) for p in inspect.signature(getattr(R.ClienteRestBetfair, n)).parameters.values()]
        assert impl == proto, n
