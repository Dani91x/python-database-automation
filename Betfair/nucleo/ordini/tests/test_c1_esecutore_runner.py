"""W1-C1 - ``esecutori/runner.py``: il dispatch di OGGI dietro il contratto ``Esecutore``.

Finti come quelli del motore (``stream/tests/test_motore_ordini_2026_09_24.py``): client
VERI di flumine (``clients.BetfairClient`` reale e simulato nel registro VERO
``clients.Clients``), strategie ``BaseStrategy`` vere, ordini flumine VERI costruiti da
``build_order``; il ``Market`` e' un doppio che assegna il bet_id e rende l'ordine
EXECUTABLE come Betfair. Nessuna rete, nessun DB.

Prove: (a) place paper e live sul client della RIGA; (b) la riga ``ordine`` del diario
porta il ``customer_order_ref`` VERO di flumine ed e' scritta PRIMA di ``place_order``;
(c) rifiuto dei trading control -> ``rifiutato``; (d) eccezione dentro ``place_order``
(``post_place:``) -> SALE e la porta la fa ``ignoto``; (e) la fase dell'evento coincide
con quella del motore di oggi sullo stesso comando (stesso ``_dispatch``).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from flumine import BaseStrategy, clients

from Betfair.nucleo.ordini import porta as PT
from Betfair.nucleo.ordini.adattatore_comando import comando_da_richiesta
from Betfair.nucleo.ordini.contratto import RichiestaOrdine
from Betfair.nucleo.ordini.esecutori.runner import FASE_DA_MOTORE, EsecutoreRunner
from Betfair.stream import live_order_worker as LOW
from Betfair.stream import motore_ordini as MO

_STRAT_PAPER = BaseStrategy(market_filter={}, name="c1_runner_paper")
_STRAT_LIVE = BaseStrategy(market_filter={}, name="c1_runner_live")
GIORNO = "2025-10-09"


class _Blotter:
    def __init__(self) -> None:
        self.ordini: Dict[str, Any] = {}

    def get_order_bet_id(self, bet_id: str) -> Optional[Any]:
        return self.ordini.get(bet_id)

    def strategy_orders(self, _s: Any) -> List[Any]:
        return list(self.ordini.values())

    def __iter__(self):
        return iter(list(self.ordini.values()))


class _Market:
    def __init__(self, registro: Any) -> None:
        self.market_id = "1.234"
        self.event_id = "E1"
        self.market_book = None
        self.blotter = _Blotter()
        self._registro = registro
        self.chiamate: List[tuple] = []
        self.rifiuta = False
        self.solleva = False
        self.su_place: Any = None
        self.dopo_place: Any = None          # l'abbinamento arriva DOPO il place
        self._n = 0

    def place_order(self, order: Any, customer_strategy_ref: Any = None,
                    client: Any = None, **_k: Any) -> bool:
        if self.su_place is not None:
            self.su_place(order)
        self.chiamate.append(("place", order, customer_strategy_ref, client))
        if self.solleva:
            raise ConnectionError("risposta persa")
        if self.rifiuta:
            order.violation("Order has violated: STRATEGY_EXPOSURE")
            return False
        self._n += 1
        order.client = client
        order.bet_id = f"3124260{self._n:04d}"
        order.executable()
        if self.dopo_place is not None:
            self.dopo_place(order)
        self.blotter.ordini[order.bet_id] = order
        return True

    def cancel_order(self, order: Any, size_reduction: Optional[float] = None) -> bool:
        self.chiamate.append(("cancel", order, size_reduction))
        order.execution_complete()
        return True


def _framework() -> Any:
    registro = clients.Clients()
    registro.add_client(clients.BetfairClient(paper_trade=False, order_stream=False))
    registro.add_client(clients.BetfairClient(paper_trade=True, order_stream=False))
    market = _Market(registro)
    return SimpleNamespace(markets=SimpleNamespace(markets={"1.234": market}),
                           clients=registro), market


@pytest.fixture()
def amb(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> Any:
    monkeypatch.setattr(LOW, "_modo_processo", lambda: "LIVE")
    monkeypatch.setattr(LOW, "_live_order_mode", lambda: "LIVE")
    monkeypatch.setattr(LOW, "_kill_switch", lambda: False)
    monkeypatch.setattr(LOW, "_jurisdiction", lambda: "it")
    monkeypatch.setattr(LOW, "_max_stake", lambda: None)
    fl, market = _framework()
    diario = MO.Diario(str(tmp_path / "d"), giorno=lambda: GIORNO)
    es = EsecutoreRunner(fl, {"live": _STRAT_LIVE, "paper": _STRAT_PAPER}, diario=diario,
                         orologio_ms=lambda: 1)
    return SimpleNamespace(fl=fl, market=market, diario=diario, es=es, tmp=tmp_path)


def _r(**k: Any) -> RichiestaOrdine:
    base: Dict[str, Any] = dict(ref="safe-t1", attore="safe", sport="calcio", modo="paper",
                                azione="place", market_id="1.234", selection_id=47972,
                                lato="back", prezzo=2.5, importo=3.0, creato_ms=1)
    base.update(k)
    return RichiestaOrdine(**base)


@pytest.mark.parametrize("modo", ["paper", "live"])
def test_place_sul_client_della_riga(amb: Any, modo: str) -> None:
    ev = amb.es.place(_r(modo=modo))
    assert ev.fase == "accettato" and ev.bet_id == "31242600001" and ev.seq == 0
    _, order, csr, client = amb.market.chiamate[-1]
    assert client.paper_trade is (modo == "paper")          # MAI soldi veri da paper
    assert csr == "safe"                                      # customerStrategyRef = attore
    assert order.order_type.size == 3.0 and order.side == "BACK"


def test_diario_ordine_prima_di_place_order(amb: Any) -> None:
    visto: List[Any] = []

    def _su_place(order: Any) -> None:
        righe = amb.diario.leggi([GIORNO])
        visto.append([r for r in righe if r.get("tipo") == "ordine"])

    amb.market.su_place = _su_place
    amb.es.place(_r())
    _, order, _csr, _c = amb.market.chiamate[-1]
    assert len(visto) == 1 and len(visto[0]) == 1
    assert visto[0][0]["ref"] == "safe-t1" and visto[0][0]["cor"] == order.customer_order_ref
    assert order.customer_order_ref                           # quello VERO di flumine


def test_rifiuto_dei_control_e_rifiutato(amb: Any) -> None:
    amb.market.rifiuta = True
    ev = amb.es.place(_r())
    assert ev.fase == "rifiutato" and ev.bet_id is None


@pytest.mark.parametrize("tipo_archivio", ["finto", "vero"])
def test_eccezione_dentro_place_order_e_esito_ignoto(amb: Any, tipo_archivio: str) -> None:
    """Integrazione W1-G1 + W1-C1 (09/10): la porta gira col finto E con l'``ArchivioLocale``
    VERO di W1-G1 (cartella temporanea, chiuso alla fine)."""
    amb.market.solleva = True
    with pytest.raises(RuntimeError, match="post_place"):
        amb.es.place(_r())

    class _Freni:
        def kill_switch(self) -> bool:
            return False

        def modo_processo(self) -> str:
            return "LIVE"

        def blocco_apertura(self, *_a: Any) -> Optional[str]:
            return None

        def eta_settings_s(self) -> float:
            return 0.0

    from Betfair.nucleo.ordini.tests.test_c1_porta import _ArchivioMemoria, _ArchivioVero

    archivio: Any = (_ArchivioMemoria() if tipo_archivio == "finto"
                     else _ArchivioVero("runner", base=amb.tmp / "archivio").apri())
    try:
        porta = PT.PortaLocale(amb.es, freni=_Freni(), archivio=archivio,
                               diario=MO.Diario(str(amb.tmp / "p"), giorno=lambda: GIORNO),
                               orologio_ms=lambda: 1)
        a = porta.invia(_r(ref="safe-t7"))
        assert a.accettato and porta.stato("safe-t7").fase == "ignoto"
        assert len([c for c in amb.market.chiamate if c[0] == "place"]) == 2   # nessun ritento
        porta.chiudi()
        assert archivio.tabelle[PT.TABELLA_REF] != {}                    # il ref e' nell'archivio
    finally:
        archivio.chiudi()


def test_cancel_per_bet_id(amb: Any) -> None:
    amb.es.place(_r())
    ev = amb.es.cancel(_r(ref="safe-c31242600001", azione="cancel", bet_id="31242600001",
                          lato=None, prezzo=None, importo=None, selection_id=0))
    assert ev.fase != "rifiutato" and amb.market.chiamate[-1][0] == "cancel"


def test_fase_uguale_al_motore_di_oggi(amb: Any, monkeypatch: pytest.MonkeyPatch,
                                       tmp_path: Any) -> None:
    """Lo stesso comando eseguito dal MOTORE di oggi (``MotoreOrdini._esegui``) su un
    framework gemello: la fase del suo evento ``order``, tradotta con ``FASE_DA_MOTORE``,
    e' quella dell'esecutore."""
    import Betfair.stream.db as DB

    for rifiuta in (False, True):
        fl2, market2 = _framework()
        market2.rifiuta = rifiuta
        amb.market.rifiuta = rifiuta
        r = _r(ref=f"safe-t{int(rifiuta) + 10}")
        mio = amb.es.place(r)
        sb = SimpleNamespace(table=lambda *_a: None)
        scrittore = MO.ScrittoreAsincrono(sb_factory=lambda: sb, dormi=lambda _s: None)
        motore = MO.MotoreOrdini("calcio", canale=None,
                                 diario=MO.Diario(str(tmp_path / f"m{rifiuta}"),
                                                  giorno=lambda: GIORNO),
                                 scrittore=scrittore)
        motore.aggancia(fl2, {"live": _STRAT_LIVE, "paper": _STRAT_PAPER})
        piano = MO.valida_comando("safe", comando_da_richiesta(r))
        riga = piano["riga"]
        riga["id"] = next(LOW._LOCAL_RID)
        riga["action"], riga["mode"] = piano["azione"], piano["mode"]
        motore._esegui("safe", r.ref, piano)
        ordini = [m["d"] for m in motore._memoria["safe"] if m["t"] == "order"]
        assert ordini, "il motore non ha emesso l'evento"
        fase_motore = ordini[0]["fase"]
        atteso = "rifiutato" if fase_motore == "errore" else FASE_DA_MOTORE[fase_motore]
        assert mio.fase == atteso, (rifiuta, fase_motore, mio)
        assert (mio.bet_id is None) == (ordini[0].get("bet_id") is None)
        DB.imposta_scrittore(None)


def _ordine_corrente(order: Any, abbinato: float, stato: str) -> Any:
    """Lo stato dell'ordine come lo porta Betfair (``listCurrentOrders``/order stream):
    risorsa VERA ``CurrentOrder`` di betfairlightweight dal JSON camelCase."""
    from betfairlightweight.resources.bettingresources import CurrentOrder

    size = float(order.order_type.size)
    return CurrentOrder(
        betId=order.bet_id, marketId="1.234", selectionId=47972, handicap=0.0,
        priceSize={"price": 2.5, "size": size}, bspLiability=0.0, side="BACK",
        status=stato, persistenceType="LAPSE", orderType="LIMIT",
        placedDate="2026-10-09T10:00:00.000Z", matchedDate="2026-10-09T10:00:00.500Z",
        averagePriceMatched=2.52 if abbinato else 0.0, sizeMatched=abbinato,
        sizeRemaining=round(size - abbinato, 2), sizeLapsed=0.0, sizeCancelled=0.0,
        sizeVoided=0.0, regulatorCode="X", customerOrderRef=order.customer_order_ref)


@pytest.mark.parametrize("abbinato,fase", [(1.0, "parziale"), (3.0, "abbinato")])
def test_ordine_abbinato_e_parziale(amb: Any, abbinato: float, fase: str) -> None:
    """V52-V54: abbinato, residuo e prezzo medio letti dall'ordine flumine VERO."""
    amb.market.dopo_place = lambda o: o.update_current_order(
        _ordine_corrente(o, abbinato, "EXECUTABLE"))
    ev = amb.es.place(_r(modo="live"))
    assert (ev.fase, ev.abbinato, ev.residuo, ev.prezzo_medio) == (
        fase, abbinato, round(3.0 - abbinato, 2), 2.52)


class _LowConEsito:
    """``live_order_worker`` VERO, salvo un ``_dispatch`` che scrive un esito ok False
    (ramo difensivo dell'esecutore: oggi place/cancel/replace sollevano)."""

    def __getattr__(self, nome: str) -> Any:
        return getattr(LOW, nome)

    @staticmethod
    def _dispatch(sb: Any, _fl: Any, riga: Dict[str, Any], mode: str, _s: Any) -> None:
        LOW._write_done(sb, riga["id"], {"ok": False, "error": "kill_switch: no",
                                         "bet_id": None, "status": None})


def test_esito_ok_false_e_rifiutato(amb: Any) -> None:
    """V23."""
    es = EsecutoreRunner(amb.fl, {"live": _STRAT_LIVE, "paper": _STRAT_PAPER},
                         low=_LowConEsito())
    ev = es.place(_r())
    assert (ev.fase, ev.codice_errore) == ("rifiutato", "kill_switch")


def test_dispatch_senza_esito_e_ignoto(amb: Any) -> None:
    class _Muto(_LowConEsito):
        @staticmethod
        def _dispatch(*_a: Any) -> None:
            return None

    es = EsecutoreRunner(amb.fl, {"live": _STRAT_LIVE, "paper": _STRAT_PAPER}, low=_Muto())
    with pytest.raises(RuntimeError, match="senza esito"):
        es.place(_r())


def test_params_nella_riga_del_dispatch(amb: Any) -> None:
    ev = amb.es.place(_r(importo=3.0), params={"max_stake": 1.0})
    assert ev.fase == "rifiutato" and amb.market.chiamate == []   # cap rispettato
