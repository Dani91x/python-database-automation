"""W1-A1 - ``limiti.py``: i numeri ufficiali di 02_COMPETITOR.md par. 3.2-3.3 e le funzioni pure.

Ogni valore atteso e' scritto qui A MANO dal documento (non ricalcolato con il
codice sotto prova); i blocchi di oggi (scanner 25, board 25, odds_refresh 20)
sono importati dal codice di oggi per la parita'.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import math
from fractions import Fraction

import pytest

from Betfair.nucleo.betfair import limiti as L

# (priceData, peso per mercato dal documento, mercati massimi per richiesta)
GRIGLIA_DOC = [
    ([], 2, 100),
    (["SP_AVAILABLE"], 3, 66),
    (["SP_TRADED"], 7, 28),
    (["EX_BEST_OFFERS"], 5, 40),
    (["EX_ALL_OFFERS"], 17, 11),
    (["EX_TRADED"], 17, 11),
    (["EX_BEST_OFFERS", "EX_TRADED"], 20, 10),
    (["EX_ALL_OFFERS", "EX_TRADED"], 32, 6),
    (["EX_ALL_OFFERS", "EX_BEST_OFFERS"], 17, 11),                 # ALL prevale su BEST
    (["EX_BEST_OFFERS", "SP_AVAILABLE"], 8, 25),
    (["EX_ALL_OFFERS", "EX_TRADED", "SP_AVAILABLE", "SP_TRADED"], 42, 4),
]


@pytest.mark.parametrize("price_data,peso,massimo", GRIGLIA_DOC)
def test_pesi_list_market_book_dal_documento(price_data, peso, massimo):
    pp = {"priceData": price_data} if price_data else None
    assert L.peso_list_market_book(pp) == peso
    assert L.mercati_massimi_per_richiesta(L.peso_list_market_book(pp)) == massimo


def test_tabella_dei_pesi_identica_al_documento():
    assert dict(L.PESI_LIST_MARKET_BOOK) == {
        "": 2, "SP_AVAILABLE": 3, "SP_TRADED": 7, "EX_BEST_OFFERS": 5, "EX_ALL_OFFERS": 17,
        "EX_TRADED": 17, "EX_BEST_OFFERS+EX_TRADED": 20, "EX_ALL_OFFERS+EX_TRADED": 32}
    assert L.PESO_MASSIMO_RICHIESTA == 200
    assert L.PESO_LIST_MARKET_PROFIT_AND_LOSS == 4
    assert L.RICHIESTE_CONCORRENTI_PER_CONTO == 3
    assert (L.LOGIN_RIUSCITI_AL_MINUTO_PER_CONTO, L.DURATA_BAN_LOGIN_S) == (100, 1200)
    assert L.VITA_SESSIONE_ITALIA_S == 1200
    assert (L.ISTRUZIONI_PER_PLACE_ITALIA, L.ISTRUZIONI_PER_PLACE_GLOBALE, L.ISTRUZIONI_AL_SECONDO) == (50, 200, 1000)
    assert L.URL_KEEPALIVE_ITALIA == "https://identitysso.betfair.it/api/keepAlive"
    assert L.URL_CERTLOGIN_ITALIA == "https://identitysso-cert.betfair.it/api/certlogin"


@pytest.mark.parametrize("profondita,peso,massimo", [(1, 5, 40), (2, 5, 40), (3, 5, 40), (5, Fraction(25, 3), 24),
                                                     (10, Fraction(50, 3), 12)])
def test_profondita_moltiplica_il_peso(profondita, peso, massimo):
    pp = {"priceData": ["EX_BEST_OFFERS"], "exBestOffersOverrides": {"bestPricesDepth": profondita}}
    assert L.peso_list_market_book(pp) == peso
    assert L.mercati_massimi_per_richiesta(L.peso_list_market_book(pp)) == massimo


def test_profondita_non_tocca_all_offers_e_scelta_prudente_sulla_combinazione():
    pp = {"priceData": ["EX_ALL_OFFERS"], "exBestOffersOverrides": {"bestPricesDepth": 10}}
    assert L.peso_list_market_book(pp) == 17
    pp = {"priceData": ["EX_BEST_OFFERS", "EX_TRADED"], "exBestOffersOverrides": {"bestPricesDepth": 6}}
    assert L.peso_list_market_book(pp) == 40                      # 20 x 6/3 (prudente, dichiarato)


def test_proiezioni_sconosciute_e_pesi_non_validi_rifiutati():
    with pytest.raises(ValueError):
        L.peso_list_market_book({"priceData": ["EX_TUTTO"]})
    for cattiva in (0, -1, True, 2.5, "3"):
        with pytest.raises(ValueError):
            L.peso_list_market_book({"priceData": ["EX_BEST_OFFERS"], "exBestOffersOverrides": {"bestPricesDepth": cattiva}})
    with pytest.raises(ValueError):
        L.mercati_massimi_per_richiesta(0)
    with pytest.raises(ValueError):
        L.mercati_massimi_per_richiesta(201)
    assert L.mercati_massimi_per_richiesta(200) == 1


def test_blocchi_su_griglia_mai_oltre_200_punti_ordine_conservato():
    for price_data, peso, massimo in GRIGLIA_DOC:
        for n in (0, 1, massimo - 1, massimo, massimo + 1, 2 * massimo, 250):
            ids = [f"1.{1000 + i}" for i in range(max(n, 0))]
            blocchi = L.blocchi_per_peso(ids, peso)
            assert [m for b in blocchi for m in b] == ids
            assert len(blocchi) == math.ceil(len(ids) / massimo)
            assert all(1 <= len(b) <= massimo and len(b) * peso <= 200 for b in blocchi)


def test_blocco_massimo_riproduce_i_blocchi_di_oggi():
    from Betfair.odds_refresh import BATCH
    from Betfair.safe_strategy.service import _BOOK_CHUNK as CHUNK_SCANNER
    from Betfair.stream.board_worker import _BOOK_CHUNK as CHUNK_BOARD

    ids = [f"1.{i}" for i in range(73)]
    for chunk in (CHUNK_SCANNER, CHUNK_BOARD, BATCH):
        oggi = [ids[i:i + chunk] for i in range(0, len(ids), chunk)]   # il ciclo di oggi
        assert L.blocchi_per_peso(ids, L.peso_list_market_book({"priceData": ["EX_BEST_OFFERS"]}),
                                  blocco_massimo=chunk) == oggi
    # i commenti di oggi ("peso 125", "peso 100") tornano coi pesi ufficiali
    assert CHUNK_SCANNER * L.peso_list_market_book({"priceData": ["EX_BEST_OFFERS"]}) == 125
    assert BATCH * L.peso_list_market_book({"priceData": ["EX_BEST_OFFERS"]}) == 100
    with pytest.raises(ValueError):
        L.blocchi_per_peso(ids, 5, blocco_massimo=0)


def test_peso_richiesta_e_catalogo():
    assert L.peso_richiesta("listMarketBook", {"price_projection": {"priceData": ["EX_TRADED"]}}) == 17
    assert L.peso_richiesta("listMarketBook", {}) == 2
    assert L.peso_richiesta("listMarketProfitAndLoss", {"market_ids": ["1.1"]}) == 4
    assert L.peso_richiesta("listCurrentOrders", {}) is None
    assert L.peso_richiesta("listMarketCatalogue", {}) is None
    assert L.peso_list_market_catalogue(["MARKET_START_TIME", "RUNNER_DESCRIPTION", "MARKET_DESCRIPTION", "EVENT"]) == 1
    assert L.peso_list_market_catalogue(["MARKET_DESCRIPTION", "RUNNER_METADATA"]) == 2
    assert L.peso_list_market_catalogue(None) == 0


@pytest.mark.parametrize("metodo,parametri,atteso", [
    ("listCurrentOrders", {}, True),
    ("listMarketProfitAndLoss", {"market_ids": ["1.1"]}, True),
    ("listMarketBook", {"order_projection": "EXECUTABLE"}, True),
    ("listMarketBook", {"match_projection": "ROLLED_UP_BY_PRICE"}, True),
    ("listMarketBook", {"price_projection": {"priceData": ["EX_BEST_OFFERS"]}}, False),
    ("listClearedOrders", {}, False),
    ("listMarketCatalogue", {}, False),
    ("placeOrders", {}, False),
])
def test_metodi_contesi(metodo, parametri, atteso):
    assert L.e_metodo_conteso(metodo, parametri) is atteso


def test_istruzioni_e_quote_di_login():
    assert not L.istruzioni_oltre_tetto(50) and L.istruzioni_oltre_tetto(51)
    assert not L.istruzioni_oltre_tetto(200, italia=False) and L.istruzioni_oltre_tetto(201, italia=False)
    assert [L.tetto_login_per_processo(p) for p in (0, 1, 3, 10, 1000)] == [100, 100, 33, 10, 1]
    assert L.METODI_MUTAZIONE == ("placeOrders", "cancelOrders", "replaceOrders", "updateOrders")
