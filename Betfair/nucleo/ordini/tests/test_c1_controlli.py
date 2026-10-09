"""W1-C1 - ``nucleo/ordini/controlli.py``: contatore delle transazioni per CONTO e freni.

1. Il contatore ha la semantica del control VERO di flumine (``MaxTransactionCount``:
   conteggio, blocco a totale > tetto, cambio d'ora UTC) su sequenze casuali con l'ora
   che scorre; la regola di conteggio e' confrontata con l'ESECUZIONE VERA di flumine
   (``BetfairExecution.execute_place/execute_cancel``) su risposte ``PlaceOrders`` /
   ``CancelOrders`` VERE di betfairlightweight (chiavi camelCase di Betfair).
2. UN contatore per conto: la somma di piu' attori ferma tutti al tetto.
3. ``controlla`` da' lo STESSO verdetto (codice e testo) di ``MotoreOrdini._controlla`` su
   una griglia di modo di processo, modo della riga, azione, riduzione, kill-switch,
   guardia d'avvio, blocco del modo effettivo e freschezza dei settings.
"""
from __future__ import annotations

import datetime as _dt
import itertools
import random
import uuid
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from betfairlightweight.resources.bettingresources import CancelOrders, PlaceOrders
from flumine import BaseStrategy, clients
from flumine.controls import clientcontrols as CC
from flumine.execution.betfairexecution import BetfairExecution
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade

from Betfair.nucleo.ordini import adattatore_comando as AC
from Betfair.nucleo.ordini import controlli as CT
from Betfair.nucleo.ordini.contratto import RichiestaOrdine
from Betfair.stream import live_order_worker as LOW
from Betfair.stream import motore_ordini as MO

ORA0_MS = 1_760_000_000_000 - (1_760_000_000_000 % 3_600_000) + 600_000   # hh:10:00 UTC


class _Orologio:
    def __init__(self, ms: int) -> None:
        self.ms = ms

    def __call__(self) -> int:
        return self.ms


def _datetime_finto(orologio: _Orologio) -> Any:
    """Il modulo ``datetime`` visto da ``clientcontrols`` con ``now`` = l'orologio."""

    class _DT(_dt.datetime):
        @classmethod
        def now(cls, tz: Any = None) -> "_dt.datetime":  # type: ignore[override]
            return _dt.datetime.fromtimestamp(orologio.ms / 1000.0, tz)

    return SimpleNamespace(datetime=_DT, timedelta=_dt.timedelta, timezone=_dt.timezone)


@pytest.mark.parametrize("seme", [1, 7, 42, 2026])
def test_contatore_parita_col_control_di_flumine(seme: int,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    rnd = random.Random(seme)
    orologio = _Orologio(ORA0_MS)
    monkeypatch.setattr(CC, "datetime", _datetime_finto(orologio))
    tetto = rnd.choice([3, 10, 50])
    vero = CC.MaxTransactionCount(None, SimpleNamespace(transaction_limit=tetto, info={}))
    nuovo = CT.ContatoreTransazioni(tetto, orologio)
    for _ in range(3000):
        mossa = rnd.random()
        if mossa < 0.45:
            n, fallite = rnd.randint(1, 3), rnd.random() < 0.3
            vero.add_transaction(n, failed=fallite)
            nuovo.aggiungi(n, fallite=fallite)
        elif mossa < 0.9:
            vero._check_hour()
            assert nuovo.consentito() == vero.safe
        else:
            orologio.ms += rnd.choice([1_000, 600_000, 3_000_000, 3_600_000, 7_300_000])
        assert (nuovo.correnti, nuovo.correnti_fallite) == (
            vero.current_transaction_count, vero.current_failed_transaction_count)
        assert (nuovo.totali, nuovo.totali_fallite) == (
            vero.transaction_count, vero.failed_transaction_count)


def test_regola_betfair_del_conteggio() -> None:
    c = CT.ContatoreTransazioni(1000, _Orologio(ORA0_MS))
    c.registra("place", "ok")
    c.registra("cancel", "ok")                 # piazza + cancella = 1
    assert c.totale_ora == 1
    c.registra("cancel", "fallito")            # una cancellazione fallita conta
    assert c.totale_ora == 2
    c.registra("place", "fallito")             # un place rifiutato conta
    assert c.totale_ora == 3
    c.registra("place", "ignoto")              # nessuna risposta: flumine non conta
    assert c.totale_ora == 3
    c.registra("replace", "ok")                # il nuovo place del replace
    c.registra("replace", "ok", cancellazione_fallita=True)
    assert (c.correnti, c.correnti_fallite) == (4, 2)
    with pytest.raises(ValueError):
        c.registra("greenup", "ok")


# ---------------------------------------------------------------------------
# la regola di conteggio contro l'ESECUZIONE VERA di flumine
# ---------------------------------------------------------------------------
_STRAT = BaseStrategy(market_filter={}, name="c1_controlli")


class _Pacchetto:
    """L'``OrderPackage`` che ``BetfairExecution`` legge: stessi nomi di attributo."""

    def __init__(self, client: Any, ordini: List[Any], tipo: str) -> None:
        self.client = client
        self.orders = ordini
        self.market_id = "1.234"
        self.elapsed_seconds = 0.0
        self.retry_count = 0
        self.id = uuid.uuid4()
        self.market_version = None
        self.customer_strategy_ref = "c1"
        self.async_ = False
        self.info: Dict[str, Any] = {}
        self.package_type = tipo
        self.place_instructions = [{"x": 1}]
        self.cancel_instructions = [{"betId": o.bet_id} for o in ordini]

    def __iter__(self):
        return iter(self.orders)

    def __len__(self) -> int:
        return len(self.orders)


def _sessione_http() -> Any:
    """La sessione http che l'esecuzione rimette nel suo pool (nessuna rete: la chiamata
    a Betfair e' il ``betting`` finto che restituisce la risposta VERA)."""
    return SimpleNamespace(time_created=0.0, time_returned=0.0)


def _ordine(bet_id: Optional[str] = None) -> Any:
    t = Trade("1.234", 47972, 0.0, _STRAT)
    o = t.create_order("BACK", LimitOrder(price=2.0, size=2.0))
    o.bet_id = bet_id
    return o


def _report_place(stato: str, bet_id: Optional[str]) -> Dict[str, Any]:
    r: Dict[str, Any] = {"status": stato, "instruction": {
        "selectionId": 47972, "handicap": 0.0, "side": "BACK", "orderType": "LIMIT",
        "limitOrder": {"size": 2.0, "price": 2.0, "persistenceType": "LAPSE"}}}
    if stato == "SUCCESS":
        r.update({"betId": bet_id, "placedDate": "2026-10-09T10:00:00.000Z",
                  "averagePriceMatched": 0.0, "sizeMatched": 0.0, "orderStatus": "EXECUTABLE"})
    else:
        r["errorCode"] = "INVALID_BET_SIZE"
    return r


def _report_cancel(stato: str, bet_id: str) -> Dict[str, Any]:
    r: Dict[str, Any] = {"status": stato, "instruction": {"betId": bet_id}}
    if stato == "SUCCESS":
        r.update({"sizeCancelled": 2.0, "cancelledDate": "2026-10-09T10:00:01.000Z"})
    else:
        r["errorCode"] = "BET_TAKEN_OR_LAPSED"
    return r


@pytest.mark.parametrize("seme", [3, 11])
def test_registra_parita_con_esecuzione_vera_di_flumine(seme: int,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    rnd = random.Random(seme)
    orologio = _Orologio(ORA0_MS)
    monkeypatch.setattr(CC, "datetime", _datetime_finto(orologio))
    risposte: List[Any] = []
    betting = SimpleNamespace(place_orders=lambda **_k: risposte.pop(0),
                              cancel_orders=lambda **_k: risposte.pop(0))
    client = clients.BetfairClient(paper_trade=False, order_stream=False,
                                   transaction_limit=10_000)
    client.betting_client = SimpleNamespace(betting=betting)
    control = CC.MaxTransactionCount(None, client)
    client.trading_controls.append(control)
    esecuzione = BetfairExecution(SimpleNamespace(log_control=lambda _e: None))
    nuovo = CT.ContatoreTransazioni(10_000, orologio)
    n_bet = 0
    for _ in range(200):
        n_bet += 1
        if rnd.random() < 0.5:
            stati = [rnd.choice(["SUCCESS", "FAILURE"]) for _ in range(rnd.randint(1, 3))]
            ordini = [_ordine() for _ in stati]
            risposte.append(PlaceOrders(status="SUCCESS", marketId="1.234", customerRef="c",
                                        instructionReports=[
                                            _report_place(s, f"9{n_bet}{i}") for i, s in
                                            enumerate(stati)]))
            esecuzione.execute_place(_Pacchetto(client, ordini, "PLACE"), _sessione_http())
            # la porta registra UN'operazione per istruzione con il suo esito
            for s in stati:
                nuovo.registra("place", "ok" if s == "SUCCESS" else "fallito")
        else:
            stato = rnd.choice(["SUCCESS", "FAILURE"])
            bet = f"8{n_bet}"
            risposte.append(CancelOrders(status=stato, marketId="1.234", customerRef="c",
                                         instructionReports=[_report_cancel(stato, bet)]))
            esecuzione.execute_cancel(_Pacchetto(client, [_ordine(bet)], "CANCEL"),
                                     _sessione_http())
            nuovo.registra("cancel", "ok" if stato == "SUCCESS" else "fallito")
        assert (nuovo.correnti, nuovo.correnti_fallite) == (
            control.current_transaction_count, control.current_failed_transaction_count)
    assert control.transaction_count > 50 and control.failed_transaction_count > 10


def test_un_contatore_per_conto_somma_gli_attori() -> None:
    orologio = _Orologio(ORA0_MS)
    c = CT.ContatoreTransazioni(5, orologio)
    for attore in ("safe", "omega", "mike"):
        for _ in range(2):
            assert c.consentito()
            c.registra("place", "ok", attore=attore)
    # 6 > 5: fermi TUTTI, anche un attore che da solo ne ha fatti 2
    assert not c.consentito()
    assert c.stato()["per_attore"] == {"safe": 2, "omega": 2, "mike": 2}
    orologio.ms += 3_600_000                       # ora nuova: si riparte
    assert c.consentito() and c.totale_ora == 0


def test_tetto_di_oggi_dal_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from Betfair.stream import config_stream

    assert CT.tetto_di_oggi() == config_stream.LIVE_TRANSACTION_LIMIT
    monkeypatch.setattr(config_stream, "LIVE_TRANSACTION_LIMIT", 77)
    assert CT.tetto_di_oggi() == 77


def test_servibili_parita_col_worker() -> None:
    for m in ("LIVE", "live", "PAPER", "OFF", "", None, "boh"):
        assert CT.servibili(m) == LOW._servable_modes(m or "OFF")


# ---------------------------------------------------------------------------
# i freni: stessa decisione del motore
# ---------------------------------------------------------------------------
class _Freni:
    def __init__(self, proc: str, eff: str, kill: bool, eta: float) -> None:
        self.proc, self.eff, self.kill, self.eta = proc, eff, kill, eta

    def kill_switch(self) -> bool:
        return self.kill

    def modo_processo(self) -> str:
        return self.proc

    def blocco_apertura(self, modo_riga: str, azione: str, params: Any) -> Optional[str]:
        # la regola di ``_blocco_apertura_modo`` col modo effettivo ``eff``
        if azione in CT.AZIONI_CHIUSURA or (params or {}).get("reduces_liability"):
            return None
        if modo_riga not in CT.servibili(self.proc):
            return None
        if modo_riga in CT.servibili(self.eff):
            return None
        return f"modo ordini {self.eff}: apertura '{modo_riga}' RIFIUTATA"

    def eta_settings_s(self) -> float:
        return self.eta


class _Market:
    def __init__(self) -> None:
        self.market_id = "1.234"
        self.market_book = None
        self.blotter: List[Any] = []


def _motore(freni: _Freni, guardia: bool) -> MO.MotoreOrdini:
    registro = clients.Clients()
    registro.add_client(clients.BetfairClient(paper_trade=False, order_stream=False))
    registro.add_client(clients.BetfairClient(paper_trade=True, order_stream=False))
    flumine = SimpleNamespace(markets=SimpleNamespace(markets={"1.234": _Market()}),
                              clients=registro)
    m = MO.MotoreOrdini("calcio", canale=None, diario=None, scrittore=None,  # type: ignore[arg-type]
                        guardia_armata=lambda: guardia, blocco_modo=freni.blocco_apertura,
                        eta_settings=freni.eta_settings_s)
    m.aggancia(flumine, {"live": _STRAT, "paper": _STRAT})
    return m


def test_controlla_parita_col_motore(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(LOW, "_jurisdiction", lambda: "it")
    ora = ORA0_MS
    n = 0
    visti = set()
    for proc, eff, modo, azione, riduce, verificata, kill, guardia, eta in itertools.product(
            ("OFF", "PAPER", "LIVE"), ("PAPER", "LIVE"), ("paper", "live"),
            ("place", "cancel", "replace"), (False, True), (False, True), (False, True),
            (False, True), (1.0, 25.0)):
        if azione != "place" and riduce:
            continue
        freni = _Freni(proc, eff, kill, eta)
        monkeypatch.setattr(LOW, "_modo_processo", lambda p=proc: p)
        monkeypatch.setattr(LOW, "_kill_switch", lambda k=kill: k)
        monkeypatch.setattr(LOW, "_db_kill_switch", lambda: False)
        r = RichiestaOrdine(ref="safe-t1", attore="safe", sport="calcio", modo=modo,
                            azione=azione, market_id="1.234", selection_id=47972,
                            lato="back" if azione == "place" else None,
                            prezzo=2.5 if azione == "place" else None,
                            importo=3.0 if azione == "place" else None,
                            riduce_esposizione=riduce,
                            bet_id=None if azione == "place" else "31",
                            nuovo_prezzo=2.6 if azione == "replace" else None,
                            creato_ms=ora - 100)
        motore = _motore(freni, guardia)
        monkeypatch.setattr(motore, "_riduzione_verificata", lambda *_a, v=verificata: v)
        piano = MO.valida_comando("safe", AC.comando_da_richiesta(r))
        try:
            motore._controlla(piano, ora)
            vecchio = (True, None)
        except MO.Rifiuto as rif:
            vecchio = (False, str(rif))
        e = CT.controlla(r, freni, None, ricevuto_ms=ora, max_eta_ms=3000,
                         riduzione_verificata=lambda v=verificata: v,
                         guardia_armata=lambda g=guardia: g, max_eta_settings_s=10.0)
        assert (e.ammesso, e.motivo) == vecchio, (proc, eff, modo, azione, riduce,
                                                  verificata, kill, guardia, eta)
        visti.add(e.codice)
        n += 1
    assert n > 500
    # il test non passa a vuoto: ogni ramo dei freni e' stato sollecitato
    assert visti == {None, MO.M_MODE, MO.M_GUARDIA, MO.M_RIDUZIONE, MO.M_KILL, MO.M_SETTINGS}


def test_controlla_eta_e_tetto() -> None:
    freni = _Freni("LIVE", "LIVE", False, 1.0)
    r = RichiestaOrdine(ref="safe-t1", attore="safe", sport="calcio", modo="live",
                        azione="place", market_id="1", selection_id=1, lato="back",
                        prezzo=2.0, importo=2.0, creato_ms=ORA0_MS)
    assert CT.controlla(r, freni, None, ricevuto_ms=ORA0_MS + 3001, max_eta_ms=3000).codice \
        == MO.M_ETA
    assert CT.controlla(r, freni, None, ricevuto_ms=ORA0_MS - 1001, max_eta_ms=3000).codice \
        == MO.M_ETA
    c = CT.ContatoreTransazioni(0, _Orologio(ORA0_MS))
    assert CT.controlla(r, freni, c, ricevuto_ms=ORA0_MS, max_eta_ms=3000).ammesso
    c.registra("place", "ok")
    e = CT.controlla(r, freni, c, ricevuto_ms=ORA0_MS, max_eta_ms=3000)
    assert (e.ammesso, e.codice) == (False, CT.CODICE_TETTO)
