"""W1-A1 - prove delle CORREZIONI dopo la revisione indipendente (ALTA-1..BASSE).

Le prove del revisore sono in ``test_a1_rest_revisore.py`` (tenute com'erano);
qui le prove mie sulle stesse correzioni, sullo stesso finto a livello di trasporto.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import pytest
from betfairlightweight import filters
from betfairlightweight.exceptions import APIError

from Betfair.nucleo.betfair import limiti as L
from Betfair.nucleo.betfair import rest as R
from Betfair.nucleo.betfair import sessione as S
from Betfair.nucleo.betfair.tests.test_a1_finto_betfair import (
    OrologioFinto,
    ServerBetfairFinto,
    installa_finto,
    peso_finto,
)
from Betfair.nucleo.betfair.tests.test_a1_rest import _PARAMETRI_MUTAZIONE, _cliente, _ids
from Betfair.odds_refresh import BetfairLimitHit


@pytest.fixture
def finto(monkeypatch):
    server = ServerBetfairFinto(OrologioFinto())
    installa_finto(monkeypatch, server)
    yield server
    S.chiudi_sessione_del_processo()


def _aping(codice: str) -> APIError:
    return APIError({"error": {"code": -32099, "data": {"APINGException": {"errorCode": codice}}}},
                    method="SportsAPING/v1.0/placeOrders")


# ---------------------------------------------------------------------------
# ALTA-1: il rifiuto di sessione delle mutazioni si legge da str(e) e __cause__, mai da __context__
# ---------------------------------------------------------------------------
def _con_contesto(errore: BaseException) -> BaseException:
    try:
        try:
            raise RuntimeError("lettura: INVALID_SESSION_INFORMATION")
        except RuntimeError:
            raise errore
    except BaseException as e:  # noqa: BLE001
        return e


def _con_causa(errore: BaseException) -> BaseException:
    try:
        raise errore from RuntimeError("NO_SESSION")
    except BaseException as e:  # noqa: BLE001
        return e


@pytest.mark.parametrize("fabbrica,atteso", [
    (lambda: _aping("INVALID_SESSION_INFORMATION"), True),
    (lambda: _aping("NO_SESSION"), True),
    (lambda: _aping("UNEXPECTED_ERROR"), False),
    (lambda: _con_contesto(APIError(None, "m", {}, TimeoutError("timeout"))), False),
    (lambda: _con_contesto(_aping("TOO_MANY_REQUESTS")), False),
    (lambda: _con_causa(RuntimeError("involucro senza codice")), True),
])
def test_rifiuto_di_sessione_mai_dal_contesto(fabbrica, atteso):
    from Betfair.omega.omega_market import _is_session_error

    e = fabbrica()
    assert R.rifiuto_di_sessione(e) is atteso
    if e.__cause__ is None:                    # parita' con call_mutating (che legge solo str(ex))
        assert _is_session_error(e) is atteso


def test_mutazione_con_rifiuto_di_sessione_ripete_stessi_parametri_e_customer_ref(finto):
    cliente = _cliente(finto)
    cliente._sessione.client()
    finto.invalida_tutti()
    cliente.mutazione("placeOrders", **_PARAMETRI_MUTAZIONE["placeOrders"])
    invii = [r["params"] for r in finto.richieste if r["tipo"] == "placeOrders"]
    assert len(invii) == 2 and invii[0] == invii[1] and invii[1]["customerRef"] == "rif-0001"


# ---------------------------------------------------------------------------
# ALTA-2: rifai_login rispetta il backoff del custode
# ---------------------------------------------------------------------------
def test_rifai_login_rifiutato_durante_il_backoff_poi_permesso(finto):
    s = S.SessioneBetfair(ora=finto.ora)
    s.client()
    finto.invalida_tutti()
    finto.guasta("login", "INVALID_USERNAME_OR_PASSWORD")
    err = _aping("INVALID_SESSION_INFORMATION")
    assert s.rifai_login(err, s.generazione) is False          # login fallito: backoff 15 s
    assert s.in_backoff() is True and s.stato()["in_backoff"] is True
    n = finto.conta("login")
    finto.ora.avanza(14)
    assert s.rifai_login(err, s.generazione) is False and finto.conta("login") == n
    finto.ora.avanza(1)
    assert s.in_backoff() is False
    assert s.rifai_login(err, s.generazione) is True and finto.conta("login") == n + 1


# ---------------------------------------------------------------------------
# MEDIA-5: freno di processo per conto (e orologio)
# ---------------------------------------------------------------------------
def test_freno_del_conto_condiviso_dalle_sessioni_dello_stesso_processo(finto):
    a = S.SessioneBetfair(ora=finto.ora)
    b = S.SessioneBetfair(ora=finto.ora)
    a.client()
    b.client()
    assert a.freno is b.freno is S.freno_del_conto("conto_finto", finto.ora)
    assert a.freno.stato()["login_ultimo_minuto"] == 2
    altro = OrologioFinto()
    assert S.freno_del_conto("conto_finto", altro) is not a.freno
    esplicito = S.FrenoLogin(ora=finto.ora)
    assert S.SessioneBetfair(ora=finto.ora, freno=esplicito).freno is esplicito


# ---------------------------------------------------------------------------
# MEDIA-6: d < 3 mai sotto il peso base; un mercato oltre 200 punti: risponde Betfair
# ---------------------------------------------------------------------------
def test_un_mercato_oltre_200_punti_stimati_parte_da_solo_e_decide_betfair(finto):
    cliente = _cliente(finto)
    pp = filters.price_projection(price_data=["EX_BEST_OFFERS", "EX_TRADED"],
                                  ex_best_offers_overrides=filters.ex_best_offers_overrides(best_prices_depth=33))
    assert L.peso_list_market_book(pp) == 220 and peso_finto(pp) <= 200     # stima prudente > lettura letterale
    libri = cliente.lettura("listMarketBook", market_ids=_ids(3), price_projection=pp, lightweight=True)
    assert [b["marketId"] for b in libri] == _ids(3)
    assert [len(r["params"]["marketIds"]) for r in finto.richieste if r["tipo"] == "listMarketBook"] == [1, 1, 1]
    troppo = filters.price_projection(price_data=["EX_BEST_OFFERS"],
                                      ex_best_offers_overrides=filters.ex_best_offers_overrides(best_prices_depth=150))
    with pytest.raises(BetfairLimitHit, match="TOO_MUCH_DATA"):
        cliente.lettura("listMarketBook", market_ids=_ids(2), price_projection=troppo)
    assert finto.conta("listMarketBook") == 4                 # 3 + 1: il limite non si ritenta


def test_profondita_sotto_3_non_abbassa_il_peso_e_il_finto_resta_indipendente():
    pp1 = {"priceData": ["EX_BEST_OFFERS"], "exBestOffersOverrides": {"bestPricesDepth": 1}}
    assert L.peso_list_market_book(pp1) == 5 and peso_finto(pp1) == pytest.approx(5 / 3)
    pp6 = {"priceData": ["EX_BEST_OFFERS", "EX_TRADED"], "exBestOffersOverrides": {"bestPricesDepth": 6}}
    assert L.peso_list_market_book(pp6) == 40 and peso_finto(pp6) == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# BASSE: periodo validato, generazione che non riparte dopo chiudi
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("periodo", [0, -1, 1081, 1200])
def test_periodo_keepalive_fuori_campo_rifiutato(periodo):
    with pytest.raises(ValueError):
        S.SessioneBetfair(periodo_keepalive_s=periodo)


def test_periodo_keepalive_al_bordo_accettato():
    assert S.SessioneBetfair(periodo_keepalive_s=S.PERIODO_KEEPALIVE_MASSIMO_S).periodo_keepalive_s == 1080.0


def test_generazione_non_riparte_dopo_chiudi(finto):
    s = S.SessioneBetfair(ora=finto.ora)
    visti = []
    s.alla_sessione_rifatta(lambda: visti.append(1))
    s.client()
    s.chiudi()
    assert s.generazione == 1 and s.stato()["connessa"] is False
    s.client()
    assert s.generazione == 2 and visti == []                # riaprire non e' un relogin
    assert s.rifai_login(_aping("INVALID_SESSION_INFORMATION"), 1) is True    # generazione vecchia: gia' nuova
    assert finto.conta("login") == 2
