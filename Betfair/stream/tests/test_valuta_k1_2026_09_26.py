"""K1 (26/09/2026): le size dello STREAM Betfair sono in GBP, il conto e' in EUR.

Reperto: `AUDIT_2026-09-25/e2e_fase2/ADMIN26_FEED_ATLANTE.md` sez. K1 (rapporto
size stream / size REST mediana 0,8599 su 94 coppie). Correzione:
`Betfair/stream/valuta.py` (UN punto di conversione, alla fonte).

I libri finti NON sono finti: nascono dalla cache VERA di betfairlightweight
(`MarketBookCache.update_cache` + `create_resource`) a partire da un messaggio
con la `marketDefinition` di una registrazione reale (`_live_raw/35674515`,
MATCH_ODDS 1.259401637), cioe' con le stesse chiavi e gli stessi tipi dello
stream vero. Il REST e' un `MarketBook(**json)` di betfairlightweight con le
chiavi di `listMarketBook`.
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, List

import pytest

from Betfair.stream import valuta as V

_RADICE = pathlib.Path(__file__).resolve().parents[3]
RATE = 1.1647   # EUR per 1 GBP (esempio del brief)

_DEFINIZIONE = {
    "bspMarket": False, "turnInPlayEnabled": True, "persistenceEnabled": True,
    "marketBaseRate": 5, "eventId": "35674515", "eventTypeId": "1",
    "numberOfWinners": 1, "bettingType": "ODDS", "marketType": "MATCH_ODDS",
    "marketTime": "2026-06-26T11:35:00.000Z", "suspendTime": "2026-06-26T11:35:00.000Z",
    "bspReconciled": False, "complete": True, "inPlay": True, "crossMatching": True,
    "runnersVoidable": False, "numberOfActiveRunners": 3, "betDelay": 5,
    "status": "OPEN", "betDelayModels": ["PASSIVE"],
    "runners": [{"status": "ACTIVE", "sortPriority": 1, "id": 11},
                {"status": "ACTIVE", "sortPriority": 2, "id": 22},
                {"status": "ACTIVE", "sortPriority": 3, "id": 33}],
    "regulators": ["MR_ITA"], "countryCode": "IT", "discountAllowed": True,
    "timezone": "GMT", "openDate": "2026-06-26T11:35:00.000Z",
    "version": 7469120253, "priceLadderDefinition": {"type": "CLASSIC"},
}


def _cache(market_id: str = "1.200"):
    from betfairlightweight.streaming.cache import MarketBookCache

    cache = MarketBookCache(market_id, 1782472864337, False, False, False)
    cache.update_cache({
        "id": market_id, "img": True, "marketDefinition": dict(_DEFINIZIONE),
        "rc": [
            {"id": 11, "atb": [[2.0, 100.0], [1.99, 50.0]], "atl": [[2.02, 40.0]],
             "trd": [[2.0, 1000.0]], "ltp": 2.0, "tv": 1000.0},
            {"id": 22, "atb": [[3.4, 10.0]], "atl": [[3.5, 20.0]], "ltp": 3.4, "tv": 10.0},
            {"id": 33, "atb": [[4.0, 0.86]], "atl": [[4.2, 2.59]], "ltp": 4.0, "tv": 5.0},
        ],
        "tv": 5000.0,
    }, 1782472864337, active=True)
    return cache


def _libro_stream(market_id: str = "1.200"):
    cache = _cache(market_id)
    return cache, cache.create_resource(1, snap=False)


def _livello(levels: Any, i: int = 0, campo: str = "size") -> Any:
    top = levels[i]
    return top.get(campo) if isinstance(top, dict) else getattr(top, campo)


def _runner(mb: Any, sid: int) -> Any:
    return next(r for r in mb.runners if r.selection_id == sid)


class _AlertFinti:
    def __init__(self) -> None:
        self.ricevuti: List[tuple] = []

    def __call__(self, livello: str, messaggio: str) -> None:
        self.ricevuti.append((livello, messaggio))


# ===========================================================================
# 1. L'ADATTATORE: 100 GBP -> 116,47 EUR
# ===========================================================================
def test_adattatore_converte_size_volumi_e_marca_il_libro():
    _c, mb = _libro_stream()
    V.converti_libro(mb, V.CambioGbpEur(fisso=RATE))
    r = _runner(mb, 11)
    assert _livello(r.ex.available_to_back) == 116.47          # 100 GBP
    assert _livello(r.ex.available_to_back, 1) == 58.24        # 50 GBP
    assert _livello(r.ex.available_to_lay) == 46.59            # 40 GBP
    assert _livello(r.ex.traded_volume) == 1164.7              # 1000 GBP
    assert _livello(r.ex.available_to_back, 0, "price") == 2.0  # i prezzi NON cambiano
    assert r.total_matched == 1164.7
    assert mb.total_matched == 5823.5
    # 0,86 GBP e' l'ordine da 1 EUR di un conto in euro
    assert _livello(_runner(mb, 33).ex.available_to_back) == 1.0
    assert mb.valuta == "EUR" and mb.size_gbp_convertite is True
    assert mb.cambio_gbp_eur == RATE


def test_adattatore_idempotente_sullo_stesso_libro():
    """Il banco RIUSA lo stesso MarketBook fra un giro e l'altro (GeneratoreLibri)."""
    _c, mb = _libro_stream()
    cambio = V.CambioGbpEur(fisso=RATE)
    V.converti_libro(mb, cambio)
    V.converti_libro(mb, cambio)
    assert _livello(_runner(mb, 11).ex.available_to_back) == 116.47
    assert mb.total_matched == 5823.5
    assert _runner(mb, 11).total_matched == 1164.7


def test_lista_gia_convertita_non_si_riconverte():
    """Il marcatore per tipo della lista: seconda difesa, indipendente dal runner."""
    una = V._livelli([{"price": 2.0, "size": 100.0}], RATE)
    assert V._livelli(una, RATE) is una
    assert una[0]["size"] == 116.47


def test_runner_condiviso_fra_due_libri_non_si_converte_due_volte():
    """`create_resource` riusa il RunnerBook in cache se il runner non e' cambiato."""
    cache, mb1 = _libro_stream()
    cambio = V.CambioGbpEur(fisso=RATE)
    V.converti_libro(mb1, cambio)
    # aggiornamento del SOLO runner 22: 11 resta lo stesso oggetto
    cache.update_cache({"id": "1.200", "rc": [{"id": 22, "atb": [[3.45, 12.0]]}]},
                       1782472865337, active=True)
    mb2 = cache.create_resource(1, snap=False)
    assert _runner(mb2, 11) is _runner(mb1, 11)
    V.converti_libro(mb2, cambio)
    assert _livello(_runner(mb2, 11).ex.available_to_back) == 116.47
    assert _runner(mb2, 11).total_matched == 1164.7                   # non 1356,54
    assert _livello(_runner(mb2, 22).ex.available_to_back) == 13.98   # 12 GBP


def test_la_cache_di_betfairlightweight_resta_in_gbp_anche_con_flumine():
    """Con flumine importato `ex.available_to_back` E' la lista di dict della
    cache: modificarla in place corromperebbe la cache e il book successivo
    (runner ri-serializzato per un ltp) verrebbe convertito DUE volte."""
    import flumine  # noqa: F401 - applica la patch EX di flumine

    cache, mb1 = _libro_stream()
    cambio = V.CambioGbpEur(fisso=RATE)
    V.converti_libro(mb1, cambio)
    rc = cache.runner_dict[(11, 0)]
    assert rc.available_to_back.serialised[0]["size"] == 100.0, "cache toccata"
    # cambia SOLO l'ltp del runner 11: nuovo RunnerBook, stesse liste di livelli
    cache.update_cache({"id": "1.200", "rc": [{"id": 11, "ltp": 2.02}]},
                       1782472865337, active=True)
    mb2 = cache.create_resource(1, snap=False)
    V.converti_libro(mb2, cambio)
    assert _livello(_runner(mb2, 11).ex.available_to_back) == 116.47


def test_cambio_congelato_per_mercato():
    """Il paper abbina sul DELTA del traded_volume: il cambio non si muove a meta' mercato."""
    cambio = V.CambioGbpEur(fisso=RATE)
    assert cambio.per_mercato("1.200") == RATE
    cambio.rate = 1.20
    assert cambio.per_mercato("1.200") == RATE      # mercato gia' visto
    assert cambio.per_mercato("1.300") == 1.20      # mercato nuovo


def test_libro_none_non_rompe():
    assert V.converti_libro(None, V.CambioGbpEur(fisso=RATE)) is None


# ===========================================================================
# 2. IL CAMBIO: Betfair, cache su disco, ripieghi e alert
# ===========================================================================
class _ClientBetfair:
    """`client.account.list_currency_rates(from_currency=...)` -> CurrencyRate veri."""

    def __init__(self, righe: Any = None, errore: Exception = None) -> None:
        self.chiamate: List[dict] = []
        outer = self

        class _Account:
            def list_currency_rates(self, from_currency=None, session=None, lightweight=None):
                outer.chiamate.append({"from_currency": from_currency})
                if errore is not None:
                    raise errore
                return righe

        self.account = _Account()


def _righe(eur: float):
    from betfairlightweight.resources.accountresources import CurrencyRate

    return [CurrencyRate(currencyCode="USD", rate=1.27),
            CurrencyRate(currencyCode="EUR", rate=eur)]


def test_cambio_letto_da_betfair_e_scritto_in_cache(tmp_path):
    p = str(tmp_path / "currency_rate.json")
    al = _AlertFinti()
    c = V.CambioGbpEur(percorso_cache=p, alert=al)
    cli = _ClientBetfair(_righe(RATE))
    assert c.aggiorna(cli) is True
    assert cli.chiamate == [{"from_currency": "GBP"}]
    assert (c.rate, c.fonte) == (RATE, "betfair")
    assert json.load(open(p, encoding="utf-8"))["rate"] == RATE
    assert al.ricevuti == []
    # riavvio SENZA rete: la cache basta
    c2 = V.CambioGbpEur(percorso_cache=p, alert=al)
    assert c2.per_mercato("1.9") == RATE and c2.fonte == "cache"


def test_rete_giu_con_cache_usa_ultimo_noto_e_warn(tmp_path):
    p = str(tmp_path / "currency_rate.json")
    json.dump({"rate": 1.17, "letto_at": 1.0}, open(p, "w", encoding="utf-8"))
    al = _AlertFinti()
    c = V.CambioGbpEur(percorso_cache=p, alert=al)
    assert c.aggiorna(_ClientBetfair(errore=ConnectionError("dns"))) is False
    assert c.rate == 1.17
    assert [x[0] for x in al.ricevuti] == ["WARN"]


def test_nessun_cambio_noto_usa_costante_e_critical(tmp_path):
    al = _AlertFinti()
    c = V.CambioGbpEur(percorso_cache=str(tmp_path / "manca.json"), alert=al)
    assert c.aggiorna(_ClientBetfair(errore=ConnectionError("dns"))) is False
    assert c.rate == V.CAMBIO_RIPIEGO == round(1 / 0.8586, 6)
    assert al.ricevuti[0][0] == "CRITICAL" and "cambio non letto" in al.ricevuti[0][1]


def test_cambio_implausibile_scartato(tmp_path):
    al = _AlertFinti()
    c = V.CambioGbpEur(percorso_cache=str(tmp_path / "x.json"), alert=al)
    assert c.aggiorna(_ClientBetfair(_righe(0.8586))) is False   # rate invertito
    assert c.rate == V.CAMBIO_RIPIEGO


def test_avvia_non_fa_mai_cadere_il_processo(tmp_path):
    al = _AlertFinti()
    c = V.CambioGbpEur(percorso_cache=str(tmp_path / "x.json"), alert=al)
    c.avvia(object())      # client senza `.account`: nessuna eccezione
    assert c.rate == V.CAMBIO_RIPIEGO and al.ricevuti[0][0] == "CRITICAL"


# ===========================================================================
# 3. SCANNER DEL FEED: lo stream si converte, il REST NO (stessa unita')
# ===========================================================================
def _scanner(client: Any = None):
    from Betfair.safe_strategy import service

    scan = service.Scanner(api_client=client, dry=True, use_stream=False, canale=False)
    scan.sports["calcio"].metas = {"c1": {
        "event_id": "c1", "market_id": "1.200", "event_name": "Roma v Lazio",
        "open_date": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
        "competition": "Serie A",
        "runners": [], "sides": {"home": 11, "draw": 22, "away": 33},
    }}
    scan.events["c1"] = {"sport": "calcio", "inplay": True, "mo_status": "OPEN"}
    scan._rebuild_market_index()
    return scan


def test_scanner_stream_converte_alla_fonte(monkeypatch):
    from Betfair.safe_strategy.stream import StreamShard

    monkeypatch.setattr(V, "CAMBIO", V.CambioGbpEur(fisso=RATE))
    shard = StreamShard(client=None, index=0)
    _c, mb = _libro_stream()
    shard.queue.put([mb])
    libri = shard.drain()
    scan = _scanner()
    for b in libri:
        scan._apply_market_book(b, dallo_stream=True)
    odds = scan.events["c1"]["odds"]
    assert odds["home"]["back_size"] == 116.47
    assert odds["home"]["lay_size"] == 46.59
    assert scan.events["c1"]["mo_total_matched"] == 5823.5


def _libro_rest(size: float):
    from betfairlightweight.resources.bettingresources import MarketBook

    return MarketBook(**{
        "marketId": "1.200", "isMarketDataDelayed": False, "status": "OPEN",
        "betDelay": 5, "bspReconciled": False, "complete": True, "inplay": True,
        "numberOfWinners": 1, "numberOfRunners": 3, "numberOfActiveRunners": 3,
        "lastMatchTime": "2026-06-26T12:00:00.000Z", "totalMatched": 5823.5,
        "totalAvailable": 1000.0, "crossMatching": True, "runnersVoidable": False,
        "version": 7469120253,
        "runners": [{"selectionId": sid, "handicap": 0.0, "status": "ACTIVE",
                     "lastPriceTraded": 2.0, "totalMatched": 1164.7,
                     "ex": {"availableToBack": [{"price": 2.0, "size": size}],
                            "availableToLay": [{"price": 2.02, "size": 46.59}],
                            "tradedVolume": []}}
                    for sid in (11, 22, 33)],
    })


class _ClientRest:
    def __init__(self, libri: List[Any]) -> None:
        outer = self
        self.libri = libri

        class _Betting:
            def list_market_book(self, market_ids=None, price_projection=None, **kw):
                return outer.libri

        self.betting = _Betting()


def test_scanner_rest_non_si_converte_due_volte(monkeypatch):
    """Il REST risponde nella valuta del CONTO (EUR): stesso campo, stessa unita'."""
    from Betfair.safe_strategy import service

    monkeypatch.setattr(V, "CAMBIO", V.CambioGbpEur(fisso=RATE))
    monkeypatch.setattr(service, "_REQ_DELAY", 0.0, raising=False)
    rest = _libro_rest(116.47)
    scan = _scanner(_ClientRest([rest]))
    scan.poll_books("calcio", ["1.200"])
    assert scan.events["c1"]["odds"]["home"]["back_size"] == 116.47
    assert not getattr(rest, "size_gbp_convertite", False)


def test_la_riga_del_feed_dichiara_la_valuta(monkeypatch):
    monkeypatch.setattr(V, "CAMBIO", V.CambioGbpEur(fisso=RATE))
    scan = _scanner()
    _c, mb = _libro_stream()
    scan._apply_market_book(V.converti_libro(mb, V.CAMBIO), dallo_stream=True)
    righe, _ = scan.build_rows(datetime.now(timezone.utc))
    payloads = [r.get("payload") for r in righe]
    assert payloads and all(p.get("valuta") == "EUR" for p in payloads)
    assert payloads[0]["odds"]["home"]["back_size"] == 116.47


# ===========================================================================
# 4. PARITA' LIVE / BANCO: stesso middleware, stesso posto, stesso numero
# ===========================================================================
def _libri_dal_quadro_live(mb: Any, cambio: Any) -> Any:
    from flumine import BaseStrategy, Flumine, clients
    from flumine.events import events as fev

    visti: List[Any] = []

    class _Cattura(BaseStrategy):
        def check_market_book(self, market, market_book):
            return True

        def process_market_book(self, market, market_book):
            visti.append(_livello(_runner(market_book, 11).ex.available_to_back))

    quadro = Flumine(client=clients.SimulatedClient())
    V.monta_su_flumine(quadro, cambio)
    strat = _Cattura(market_filter={"markets": ["1.200"]})
    quadro.add_strategy(strat)
    strat.historic_stream_ids = {mb.streaming_unique_id}
    quadro._process_market_books(fev.MarketBookEvent([mb]))
    return quadro, visti


def test_runner_live_middleware_primo_e_strategia_vede_eur():
    from flumine.markets.middleware import SimulatedMiddleware

    _c, mb = _libro_stream()
    quadro, visti = _libri_dal_quadro_live(mb, V.CambioGbpEur(fisso=RATE))
    assert isinstance(quadro._market_middleware[0], V._MW_CLASSE)
    assert any(isinstance(m, SimulatedMiddleware) for m in quadro._market_middleware[1:])
    assert visti == [116.47]


def test_monta_su_flumine_idempotente_e_resta_primo():
    from flumine import Flumine, clients
    from flumine.markets.middleware import Middleware, SimulatedMiddleware

    quadro = Flumine(client=clients.SimulatedClient())
    V.monta_su_flumine(quadro)
    V.monta_su_flumine(quadro)
    quadro.add_market_middleware(Middleware())   # chi arriva dopo va in coda
    tipi = [type(m) for m in quadro._market_middleware]
    assert tipi.count(V._MW_CLASSE) == 1 and tipi[0] is V._MW_CLASSE
    assert SimulatedMiddleware in tipi[1:] and tipi[-1] is Middleware


def test_parita_runner_banco_stesso_numero():
    """Stessa registrazione (stesso book GBP), stesso cambio: il runner live e il
    banco di replay consegnano alle strategie la STESSA size in EUR."""
    import flumine.config as fconf
    from flumine import FlumineSimulation

    from Betfair.stream.backtest import banco_comune as B

    _c1, mb_live = _libro_stream()
    _q, visti_live = _libri_dal_quadro_live(mb_live, V.CambioGbpEur(fisso=V.CAMBIO_RIPIEGO))

    prima = fconf.simulated
    fconf.simulated = True
    try:
        quadro = FlumineSimulation(client=B.cliente_simulato())
        B.assicura_middleware_simulato(quadro)
        assert isinstance(quadro._market_middleware[0], V._MW_CLASSE), \
            "il banco deve convertire nello STESSO punto del runner"
        _c2, mb_banco = _libro_stream()
        motore = B.MotoreReplay(quadro)
        mercato, _nuovo = motore._a_flumine(mb_banco)
    finally:
        fconf.simulated = prima
    banco = _livello(_runner(mercato.market_book, 11).ex.available_to_back)
    assert banco == visti_live[0] == round(100.0 * V.CAMBIO_RIPIEGO, 2)


def test_cambio_del_banco_fisso_e_riproducibile(monkeypatch):
    monkeypatch.delenv("BANCO_CAMBIO_EUR_PER_GBP", raising=False)
    assert V.cambio_banco().rate == V.CAMBIO_RIPIEGO
    monkeypatch.setenv("BANCO_CAMBIO_EUR_PER_GBP", "1.18")
    c = V.cambio_banco()
    assert c.rate == 1.18 and c.fonte == "fisso"
    assert c.aggiorna(_ClientBetfair(_righe(1.10))) is True and c.rate == 1.18


# ===========================================================================
# 5. CONTRATTO: nessuna fonte di book dello stream senza la conversione
# ===========================================================================
_ESCLUSI = ("/tests/", "/tools/")

# Chi COSTRUISCE una fonte di book dello stream (flumine o bflw diretto) e con
# quale aggancio si converte. Aggiungere una fonte = registrarla qui.
_FONTI_CONVERTITE = {
    # produzione
    "Betfair/stream/runner.py": "monta_su_flumine(",
    "Betfair/stream/tennis_live/tennis_runner.py": "monta_su_flumine(",
    "Betfair/stream/scalper/scalper_session.py": "monta_su_flumine(",
    "Betfair/safe_strategy/stream.py": "converti_libro(",
    # banco (la conversione la monta assicura_middleware_simulato)
    "Betfair/stream/backtest/banco_comune.py": "assicura_middleware_simulato(",
    "Betfair/stream/backtest/trasporto_rapido.py": "assicura_middleware_simulato(",
    "Betfair/stream/backtest/run_backtest.py": "assicura_middleware_simulato(",
}
# Fonti NON convertite, con il perche'. Registratori (il raw resta GBP) e
# laboratori/avviatori storici non lanciati dall'app (desktop/main.js).
_FONTI_ESENTI = {
    "Betfair/stream/tennis_scalper/record_multi.py": "registratore",
    "Betfair/stream/tennis_scalper/record_tennis.py": "registratore",
    "Betfair/stream/tennis_scalper/research_data.py": "ricerca",
    "Betfair/stream/scalper/run_scalper.py": "laboratorio",
    "Betfair/stream/scalper/run_theta.py": "laboratorio",
    "Betfair/stream/scalper/run_scalper_live.py": "avviatore storico",
    "Betfair/stream/tennis_scalper/run_tennis_pro.py": "avviatore storico",
    "Betfair/stream/tennis_scalper/run_tennis_scalper.py": "avviatore storico",
    "Betfair/stream/tennis_scalper/backtest_pro.py": "laboratorio",
    "Betfair/stream/tennis_scalper/flb_backtest.py": "laboratorio",
    "Betfair/stream/tennis_scalper/tune_tennis.py": "laboratorio",
    "Betfair/stream/tennis_live/paper_execution.py": "solo docstring, nessuna fonte",
}
_FONTE = re.compile(r"\bFlumine(Simulation)?\(|\.create_stream\(|\bStreamListener\(")


def _sorgenti():
    for cartella, _sub, files in os.walk(_RADICE / "Betfair"):
        if "__pycache__" in cartella:
            continue
        for nome in files:
            if nome.endswith(".py"):
                p = os.path.join(cartella, nome)
                rel = os.path.relpath(p, _RADICE).replace("\\", "/")
                if any(x in "/" + rel for x in _ESCLUSI) or nome.startswith("test_"):
                    continue
                yield rel, io.open(p, encoding="utf-8", errors="replace").read()


def test_contratto_ogni_fonte_di_book_dello_stream_e_convertita():
    trovate = {}
    for rel, testo in _sorgenti():
        codice = "\n".join(r for r in testo.splitlines() if not r.lstrip().startswith("#"))
        if _FONTE.search(codice):
            trovate[rel] = codice
    ignote = sorted(set(trovate) - set(_FONTI_CONVERTITE) - set(_FONTI_ESENTI))
    assert not ignote, (
        f"fonti di book dello stream NON registrate (size in GBP!): {ignote}. "
        "Montare Betfair.stream.valuta.monta_su_flumine (o converti_libro) e "
        "registrarle in _FONTI_CONVERTITE.")
    for rel, aggancio in _FONTI_CONVERTITE.items():
        assert rel in trovate, f"{rel} non costruisce piu' una fonte: aggiorna il contratto"
        assert aggancio in trovate[rel], f"{rel}: manca {aggancio} (size GBP non convertite)"


def test_contratto_il_banco_monta_la_conversione():
    testo = (_RADICE / "Betfair/stream/backtest/banco_comune.py").read_text(encoding="utf-8")
    corpo = testo.split("def assicura_middleware_simulato", 1)[1].split("\ndef ", 1)[0]
    assert "monta_su_flumine(" in corpo and "cambio_banco()" in corpo


# ===========================================================================
# 6. MARCATORE sul book serializzato (ladder / live_now / canale / file curato)
# ===========================================================================
def test_serialize_book_dichiara_la_valuta_solo_se_convertito():
    from Betfair.stream.recorder import serialize_book

    _c, mb = _libro_stream()
    grezzo = serialize_book(mb, 3)
    assert "valuta" not in grezzo                      # file storico: GBP
    assert grezzo["runners"]["11"]["b"][0] == [2.0, 100.0]
    V.converti_libro(mb, V.CambioGbpEur(fisso=RATE))
    eur = serialize_book(mb, 3)
    assert eur["valuta"] == "EUR"
    assert eur["runners"]["11"]["b"][0] == [2.0, 116.47]
    assert eur["tv"] == 5823.5
