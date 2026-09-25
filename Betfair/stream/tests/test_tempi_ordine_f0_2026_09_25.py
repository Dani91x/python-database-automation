"""F0 "misura" (25/09): i 5 tempi del percorso di un ordine (``tempi_ordine.py``).

Cosa si prova (brief del coordinatore, AUDIT_STRADE_ORDINE 24/09 par. 5 riga F0):
  (a) coda DB -> riga ``tempi_ordine`` con tutti i tratti valorizzati e coerenti;
      con la riga VERA di oggi (params ``source``/``trade_id``) la decisione e' ``na``;
  (b) canale 47331 -> strada=canale; motore ``/comando/<attore>`` -> strada=comando;
  (c) tennis (canale 47332 e coda tennis) -> strada=tennis;
  (d) interruttore spento -> nessuna riga e nessuna chiamata al modulo;
  (e) TTL e tetto della cache;
  (f) script di lettura su un log finto -> p50/p95 giusti;
  (g) traccia identica: la sequenza delle chiamate a mercato e DB di ``_process_once``
      (coda + canale) e' la stessa a strumentazione accesa e spenta.

I finti parlano come il vero: riga di ``betfair_live_order_requests`` con le colonne
della migrazione (``requested_at`` ISO, ``client_ref``, ``params`` jsonb), riga di
``tennis_live_order_queue`` (``payload``, ``created_at``), ``LocalChannel`` e
``LocalRequest`` VERI, ordini flumine VERI costruiti da ``build_order`` /
``Trade.create_order``, risposta di Betfair con ``PlaceOrderInstructionReports`` e
stream ordini con ``UnmatchedOrder`` di betfairlightweight (``pd``/``md`` in epoch ms).
Nessuna rete, nessun DB vero, nessun processo.
"""
from __future__ import annotations

import logging
import time
import types
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest
from betfairlightweight.resources.bettingresources import PlaceOrderInstructionReports
from betfairlightweight.streaming.cache import UnmatchedOrder
from flumine import BaseStrategy

from Betfair.stream import live_order_build  # noqa: F401 - import fuori dalla misura
from Betfair.stream import live_order_worker as wk
from Betfair.stream import local_channel as LC
from Betfair.stream import tempi_ordine as T
from Betfair.stream.engine import live_trading_strategy as LTS
from Betfair.stream.tennis_live import guardie_tennis as GT
from Betfair.stream.tennis_live import tennis_live_order_worker as W
from Betfair.stream.tests.test_live_order_worker import (
    _STRAT, _FakeFlumine, _FakeMarket, _row)
from Betfair.stream.tools import leggi_tempi_ordine as L
from Betfair.stream.trading import stato_mercato  # noqa: F401 - idem

# harness VERO del motore ordini (fixture ``amb`` e helper dei suoi test)
from Betfair.stream.tests.test_motore_ordini_2026_09_24 import (  # noqa: F401
    _cmd, _manda, amb)

_LOGGER = T.__name__


# ===========================================================================
# impalcatura
# ===========================================================================
@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    monkeypatch.setenv("LIVE_TEMPI_ORDINE", "1")
    T._azzera_per_test()
    monkeypatch.setattr(wk, "_live_order_mode", lambda: "PAPER")
    monkeypatch.setattr(wk, "_modo_processo", lambda: "PAPER")
    monkeypatch.setattr(wk, "_kill_switch", lambda: False)
    monkeypatch.setattr(wk, "_db_kill_switch", lambda: False)
    monkeypatch.setattr(wk, "_jurisdiction", lambda: "it")
    monkeypatch.setattr(wk, "_batch", lambda: 5)
    monkeypatch.setattr(wk, "_max_stake", lambda: 10.0)
    monkeypatch.setattr(wk, "_LOCAL_SEEN", {})
    GT.azzera_per_i_test()
    yield
    T._azzera_per_test()
    GT.azzera_per_i_test()


def _righe(caplog) -> List[Dict[str, str]]:
    out = []
    for r in caplog.records:
        if r.name == _LOGGER:
            c = L.analizza_riga(r.getMessage())
            if c is not None:
                out.append(c)
    return out


def _iso(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def _num(c: Dict[str, str], k: str) -> Optional[float]:
    v = c.get(k)
    return None if v in (None, "na") else float(v)


class _Q:
    """Catena PostgREST finta che REGISTRA ogni execute (tabella, passi, chiavi)
    ed emula la coda ``betfair_live_order_requests`` (select/update/insert)."""

    def __init__(self, sb: "_SbSpia", nome: str) -> None:
        self.sb, self.nome = sb, nome
        self.passi: List[str] = []
        self.op: Optional[str] = None
        self.payload: Any = None
        self.filtri: List[tuple] = []
        self.lim: Optional[int] = None

    def __getattr__(self, passo: str) -> Any:
        if passo.startswith("__"):
            raise AttributeError(passo)

        def _f(*a: Any, **_k: Any) -> "_Q":
            self.passi.append(passo)
            if passo in ("select", "update", "insert", "upsert", "delete"):
                self.op = passo
                self.payload = a[0] if (a and passo != "select") else None
            elif passo == "eq":
                self.filtri.append((a[0], a[1]))
            elif passo == "limit":
                self.lim = a[0]
            return self
        return _f

    def execute(self) -> Any:
        chiavi = tuple(sorted(self.payload)) if isinstance(self.payload, dict) else None
        self.sb.traccia.append((self.nome, tuple(self.passi), chiavi))
        if self.nome != wk._TABLE:
            return types.SimpleNamespace(data=[])
        righe = [r for r in self.sb.righe if all(r.get(k) == v for k, v in self.filtri)]
        if self.op == "select":
            righe.sort(key=lambda r: r.get("id"))
            if self.lim is not None:
                righe = righe[: self.lim]
            return types.SimpleNamespace(data=[dict(r) for r in righe])
        if self.op == "update":
            if self.payload == {"status": "processing"} and self.sb.ritardo_claim:
                time.sleep(self.sb.ritardo_claim)       # il claim e' un giro al DB
            for r in righe:
                r.update(self.payload)
            return types.SimpleNamespace(data=[dict(r) for r in righe])
        if self.op == "insert":
            nuova = dict(self.payload, id=10_000 + len(self.sb.righe))
            self.sb.righe.append(nuova)
            return types.SimpleNamespace(data=[dict(nuova)])
        return types.SimpleNamespace(data=[])


class _SbSpia:
    def __init__(self, righe: List[Dict[str, Any]], ritardo_claim: float = 0.0) -> None:
        self.righe = righe
        self.traccia: List[tuple] = []
        self.ritardo_claim = ritardo_claim

    def table(self, nome: str) -> _Q:
        return _Q(self, nome)

    def rpc(self, nome: str, *_a: Any, **_k: Any) -> _Q:
        return _Q(self, f"rpc:{nome}")


def _riga_coda_vera(rid: int, requested_ms: float, params: Any) -> Dict[str, Any]:
    """Riga come la scrive ``request_betfair_live_order`` (colonne della migrazione)."""
    return _row(rid, client_ref=f"omega-t{rid}-L", requested_at=_iso(requested_ms),
                processed_at=None, params=params)


def _risposta_e_abbinamento(order: Any, pd_ms: int, dopo_ms: int = 1500,
                            con_stream: bool = True) -> None:
    """Quello che fa flumine all'arrivo della risposta di placeOrders
    (``BaseExecution._order_logger`` -> ``responses.placed``) e dello stream
    ordini (``update_current_order`` con l'``UnmatchedOrder`` della cache)."""
    rapporto = PlaceOrderInstructionReports(
        status="SUCCESS", orderStatus="EXECUTABLE", betId=228000000001,
        averagePriceMatched=0.0, sizeMatched=0.0 if con_stream else 2.0,
        placedDate=_iso(pd_ms).replace("+00:00", "Z"))
    order.responses.placed(rapporto)
    if con_stream:
        order.update_current_order(UnmatchedOrder(
            publish_time=pd_ms + dopo_ms, id="228000000001", p=3.0, s=5.0, side="B",
            status="EC", ot="L", pd=pd_ms, sm=5.0, sr=0.0, sl=0.0, sc=0.0, sv=0.0,
            rfo="", rfs="", pt="L", md=pd_ms + dopo_ms, avp=3.0))


def _strategia_specchio(monkeypatch) -> Any:
    s = LTS.LiveTradingStrategy(market_filter={"marketIds": ["1.1"]}, session=None,
                                mode="paper")
    monkeypatch.setattr(s, "_mirror_orders", lambda market, orders: None)
    return s


# ===========================================================================
# (a) coda DB
# ===========================================================================
def test_a_coda_tutti_i_tratti_valorizzati_e_coerenti(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=_LOGGER)
    adesso = time.time() * 1000.0
    decisione = adesso - 900.0
    requested = adesso - 400.0
    sb = _SbSpia([_riga_coda_vera(1, requested, {"source": "omega", "trade_id": 7,
                                                 "decisione_ms": int(decisione)})],
                 ritardo_claim=0.04)
    market = _FakeMarket("1.1")
    assert wk._process_once(sb, _FakeFlumine({"1.1": market}), strategy=_STRAT) == 1
    assert _righe(caplog) == []                      # nessuna riga prima dell'esito
    order = market.calls[0][1]
    time.sleep(0.01)                                  # la risposta arriva DOPO il place
    pd_ms = int(time.time() * 1000) + 2070            # orologio del PC indietro ~2 s
    _risposta_e_abbinamento(order, pd_ms, dopo_ms=1500)
    _strategia_specchio(monkeypatch).process_orders(market, [order])

    righe = _righe(caplog)
    assert len(righe) == 1
    c = righe[0]
    assert (c["strada"], c["via"], c["ref"], c["azione"], c["mode"], c["esito"]) == (
        "coda", "coda", "awlq1", "place", "paper", "abbinato")
    assert c["ordine"] == str(order.id) and c["rif"] == "omega-t1-L"
    tratti = ("decisione_ms", "ricezione_ms", "presa_ms", "place_ms", "risposta_ms",
              "abbinato_ms", "interno_ms", "risposta_bf_ms")
    assert all(_num(c, k) is not None for k in tratti), c
    assert _num(c, "decisione_ms") == pytest.approx(500, abs=1)   # requested - decisione
    assert 400 - 1 <= _num(c, "ricezione_ms") < 400 + 5000         # lettura - requested
    for k in ("presa_ms", "place_ms", "risposta_ms", "interno_ms"):
        assert _num(c, k) >= 0, (k, c)
    assert _num(c, "risposta_ms") >= 10 - 1                         # sleep prima della risposta
    # il claim (40 ms) sta fra lettura e presa, NON fra presa e place
    assert _num(c, "presa_ms") >= 40 - 1 and _num(c, "place_ms") < 40 - 1
    # monotonia: lettura <= presa <= place (interno = presa + place)
    assert _num(c, "interno_ms") == pytest.approx(
        _num(c, "presa_ms") + _num(c, "place_ms"), abs=2)
    assert _num(c, "abbinato_ms") == 1500 and c["abbinato_fonte"] == "betfair"
    assert _num(c, "risposta_bf_ms") >= 2070 - 1
    assert c["orologi"] == "decisione:pc/db,ricezione:db/pc,risposta_bf:pc/betfair"
    assert T._voci == {} and T._ordini == {}          # niente resta in memoria


def test_a_coda_riga_vera_di_oggi_decisione_assente(monkeypatch, caplog):
    """Omega e Safe accodano ``params = {source, trade_id}``: nessun istante di
    decisione -> ``decisione_ms=na`` (lo dichiara il referto), il resto c'e'."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    sb = _SbSpia([_riga_coda_vera(2, time.time() * 1000.0 - 50,
                                  {"source": "omega", "trade_id": 8})])
    market = _FakeMarket("1.1")
    wk._process_once(sb, _FakeFlumine({"1.1": market}), strategy=_STRAT)
    order = market.calls[0][1]
    _risposta_e_abbinamento(order, int(time.time() * 1000), con_stream=False)
    _strategia_specchio(monkeypatch).process_orders(market, [order])
    (c,) = _righe(caplog)
    assert c["decisione_ms"] == "na" and _num(c, "ricezione_ms") is not None
    # senza stream ordini (size abbinata dal rapporto): fonte = osservazione locale
    assert c["abbinato_fonte"] == "osservato" and _num(c, "abbinato_ms") >= 0


def test_a_coda_errore_pre_place_scrive_subito(caplog):
    caplog.set_level(logging.INFO, logger=_LOGGER)
    sb = _SbSpia([_riga_coda_vera(3, time.time() * 1000.0, None)])
    wk._process_once(sb, _FakeFlumine({}), strategy=_STRAT)   # mercato non sottoscritto
    (c,) = _righe(caplog)
    assert c["esito"] == "errore" and c["ordine"] == "na" and c["place_ms"] == "na"
    assert _num(c, "presa_ms") >= 0 and T._voci == {}


# ===========================================================================
# (b) canale 47331 e motore /comando
# ===========================================================================
def _canale(monkeypatch) -> Any:
    ch = LC.LocalChannel(59996, "calcio")
    risposte: List[tuple] = []
    monkeypatch.setattr(ch, "respond", lambda req, ok, data=None, error=None:
                        risposte.append((req.msg_id, ok, error)))
    monkeypatch.setattr(LC, "get_channel", lambda: ch)
    ch.risposte_test = risposte
    return ch


def _ordine_desktop(msg_id: int, client_ref: str) -> LC.LocalRequest:
    return LC.LocalRequest(ws=None, msg_id=msg_id, method="order", params={
        "action": "place", "mode": "paper", "market_id": "1.1", "selection_id": 47999,
        "handicap": 0, "side": "back", "order_type": "LIMIT", "price": 3.0, "size": 5.0,
        "persistence": "LAPSE", "client_ref": client_ref})


def test_b_canale_47331_strada_canale(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=_LOGGER)
    ch = _canale(monkeypatch)
    ch._requests.put_nowait(_ordine_desktop(1, "c0ffee00-0000-4000-8000-000000000001"))
    market = _FakeMarket("1.1")
    sb = _SbSpia([])
    assert wk._process_local_requests(sb, _FakeFlumine({"1.1": market}), "paper", _STRAT) == 1
    assert ch.risposte_test[0][1] is True
    order = market.calls[0][1]
    _risposta_e_abbinamento(order, int(time.time() * 1000))
    _strategia_specchio(monkeypatch).process_orders(market, [order])
    (c,) = _righe(caplog)
    assert c["strada"] == "canale" and c["ref"].startswith("awlq9")
    assert c["rif"] == "c0ffee00-0000-4000-8000-000000000001"
    # il desktop non porta l'istante del clic e LocalRequest non porta l'arrivo
    assert c["decisione_ms"] == "na" and c["ricezione_ms"] == "na"
    for k in ("presa_ms", "place_ms", "interno_ms", "risposta_ms"):
        assert _num(c, k) >= 0
    assert _num(c, "abbinato_ms") == 1500


def test_b_motore_comando_strada_comando(amb, caplog):  # noqa: F811
    caplog.set_level(logging.INFO, logger=_LOGGER)
    ws = amb.ch.collega("safe")
    creato = int(time.time() * 1000) - 250
    _manda(amb, ws, _cmd(creato_ms=creato))
    order, _ref, _client = amb.market.calls[0]
    _risposta_e_abbinamento(order, int(time.time() * 1000), dopo_ms=700)
    T.osserva([order])                    # stesso punto dello stream (process_orders)
    (c,) = _righe(caplog)
    assert (c["strada"], c["rif"], c["azione"], c["mode"]) == (
        "comando", "safe-t1", "place", "paper")
    assert _num(c, "decisione_ms") >= 250 - 1          # ricevuto_ms - creato_ms (stesso PC)
    assert _num(c, "ricezione_ms") >= 0 and c["orologi"] == "risposta_bf:pc/betfair"
    assert _num(c, "abbinato_ms") == 700


# ===========================================================================
# (c) tennis: canale 47332 e coda tennis
# ===========================================================================
MID_T, EV_T, SEL_T = "1.100", "35794049", 47972


class _DbCodaTennis:
    """Firme di ``tennis_db`` usate dal worker (come nei test del 24/09)."""

    def __init__(self, righe: List[Dict[str, Any]]) -> None:
        self.righe = list(righe)
        self.fatte: List[tuple] = []
        self.errori: List[tuple] = []

    def list_pending_tennis_orders(self, limit: int = 5) -> List[Dict[str, Any]]:
        out, self.righe = self.righe[:limit], self.righe[limit:]
        return out

    def claim_tennis_order(self, rid: int) -> bool:
        return True

    def write_tennis_order_done(self, rid: int, result: Dict[str, Any]) -> None:
        self.fatte.append((rid, result))

    def write_tennis_order_error(self, rid: int, result: Dict[str, Any]) -> None:
        self.errori.append((rid, result))

    def get_tennis_client(self) -> Any:
        return _SbSpia([])

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()


def _quadro_tennis(monkeypatch, righe_coda: List[Dict[str, Any]]) -> Dict[str, Any]:
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "PAPER")
    monkeypatch.setattr(GT, "aggiorna_impostazioni", lambda sb, forza=False: None)
    monkeypatch.setattr(W, "_last_db_queue_poll", 0.0)
    monkeypatch.setattr(W, "_LOCAL_SEEN", {})
    monkeypatch.setattr(W, "_mirror_order", lambda *a, **k: None)
    monkeypatch.setattr(W, "_reconcile_bots", lambda *a, **k: None)
    db = _DbCodaTennis(righe_coda)
    monkeypatch.setattr(W, "tennis_db", db)
    market = _FakeMarket(MID_T)
    cattura = BaseStrategy(market_filter={}, name="cattura_tennis")
    sessione = types.SimpleNamespace(market_meta={EV_T: {"market_id": MID_T}},
                                     capture={EV_T: cattura}, tracked_orders={},
                                     framework_gen=0)
    return {"db": db, "market": market, "fl": _FakeFlumine({MID_T: market}),
            "sessione": sessione}


def _riga_tennis(rid: int, created_ms: float) -> Dict[str, Any]:
    return {"id": rid, "client_ref": f"ref-{rid}",
            "payload": {"action": "place", "mode": "paper", "market_id": MID_T,
                        "selection_id": SEL_T, "side": "back", "price": 2.0, "size": 2.0},
            "status": "pending", "result": None, "error": None,
            "created_at": _iso(created_ms), "processed_at": None}


def test_c_tennis_canale_e_coda_strada_tennis(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=_LOGGER)
    q = _quadro_tennis(monkeypatch, [_riga_tennis(21, time.time() * 1000.0 - 300)])
    ch = LC.LocalChannel(59995, "tennis")
    risposte: List[tuple] = []
    monkeypatch.setattr(ch, "respond", lambda req, ok, data=None, error=None:
                        risposte.append((req.msg_id, ok, error)))
    monkeypatch.setattr(LC, "get_channel", lambda: ch)
    ch._requests.put_nowait(LC.LocalRequest(ws=None, msg_id=1, method="order", params={
        "action": "place", "mode": "paper", "market_id": MID_T, "selection_id": SEL_T,
        "side": "back", "price": 2.0, "size": 2.0, "client_ref": "loc-1"}))
    W.tennis_live_order_worker({}, q["fl"], q["sessione"])
    assert risposte and risposte[0][1] is True, risposte
    assert len(q["market"].calls) == 2 and q["db"].fatte
    assert _righe(caplog) == []
    ora_ms = int(time.time() * 1000)
    for i, call in enumerate(q["market"].calls):
        _risposta_e_abbinamento(call[1], ora_ms, dopo_ms=400 + i)
    W._reconcile_tracked(q["sessione"], q["fl"])           # il reconcile vero
    righe = sorted(_righe(caplog), key=lambda c: c["via"])
    assert [(c["strada"], c["via"]) for c in righe] == [("tennis", "canale"),
                                                        ("tennis", "coda")]
    canale, coda = righe
    assert canale["ref"].startswith("awtq9") and coda["ref"] == "awtq21"
    assert canale["ricezione_ms"] == "na"
    assert 300 - 1 <= _num(coda, "ricezione_ms") and "ricezione:db/pc" in coda["orologi"]
    assert {_num(canale, "abbinato_ms"), _num(coda, "abbinato_ms")} == {400, 401}
    for c in righe:
        assert c["esito"] == "abbinato"
        for k in ("presa_ms", "place_ms", "interno_ms", "risposta_ms"):
            assert _num(c, k) >= 0


# ===========================================================================
# (d) interruttore spento: nessuna riga, nessuna chiamata al modulo
# ===========================================================================
def test_d_interruttore_spento_modulo_mai_chiamato(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=_LOGGER)
    monkeypatch.setenv("LIVE_TEMPI_ORDINE", "0")
    chiamate: List[str] = []
    for nome in ("ora", "nuovo", "presa", "place", "fine", "osserva", "decisione_da"):
        monkeypatch.setattr(T, nome, lambda *a, _n=nome, **k: chiamate.append(_n))
    # coda + canale calcio
    ch = _canale(monkeypatch)
    ch._requests.put_nowait(_ordine_desktop(1, "d0000000-0000-4000-8000-000000000001"))
    sb = _SbSpia([_riga_coda_vera(1, time.time() * 1000.0, None)])
    market = _FakeMarket("1.1")
    wk._process_once(sb, _FakeFlumine({"1.1": market}), strategy=_STRAT)
    assert len(market.calls) == 2 and sb.righe[0]["status"] == "done"
    for call in market.calls:
        _risposta_e_abbinamento(call[1], int(time.time() * 1000))
    _strategia_specchio(monkeypatch).process_orders(market, [c[1] for c in market.calls])
    # tennis
    q = _quadro_tennis(monkeypatch, [_riga_tennis(5, time.time() * 1000.0)])
    monkeypatch.setattr(LC, "get_channel", lambda: None)
    W.tennis_live_order_worker({}, q["fl"], q["sessione"])
    assert len(q["market"].calls) == 1
    W._reconcile_tracked(q["sessione"], q["fl"])
    assert chiamate == []
    assert _righe(caplog) == []


# ===========================================================================
# (e) TTL e tetto
# ===========================================================================
class _Orologio:
    def __init__(self) -> None:
        self.t = 1000.0

    def monotonic(self) -> float:
        return self.t

    def time(self) -> float:
        return 1_758_800_000.0 + self.t


def test_e_ttl_scaduto_scrive_e_libera(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=_LOGGER)
    oro = _Orologio()
    monkeypatch.setattr(T, "time", oro)
    monkeypatch.setattr(T, "TTL_S", 600.0)
    T.nuovo("awlq1", "coda")
    T.presa("awlq1")
    ordine = types.SimpleNamespace(id="ord-1", responses=None, size_matched=0.0,
                                   status=None)
    T.place(ordine)
    assert "ord-1" in T._ordini
    oro.t += 599.0
    T.nuovo("awlq2", "coda")
    assert "awlq1" in T._voci                            # non ancora scaduta
    oro.t += 2.0
    T.nuovo("awlq3", "coda")
    assert "awlq1" not in T._voci and "ord-1" not in T._ordini
    (c,) = _righe(caplog)
    assert c["ref"] == "awlq1" and c["esito"] == "scaduto" and c["ordine"] == "ord-1"


def test_e_tetto_voci(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=_LOGGER)
    monkeypatch.setattr(T, "MAX_VOCI", 3)
    for i in range(1, 6):
        T.nuovo(f"awlq{i}", "canale")
    assert list(T._voci) == ["awlq3", "awlq4", "awlq5"]
    assert [(c["ref"], c["esito"]) for c in _righe(caplog)] == [("awlq1", "tetto"),
                                                                ("awlq2", "tetto")]


def test_e_modulo_non_solleva_mai():
    """Best-effort: input assurdi non arrivano mai al chiamante (il worker)."""
    T.nuovo(None, None, t=("x", "y"))           # type: ignore[arg-type]
    T.presa(object())                           # type: ignore[arg-type]
    T.place(None)
    T.fine("inesistente", True)
    T.osserva([object(), None])
    T.osserva(None)                             # type: ignore[arg-type]


# ===========================================================================
# (f) script di lettura
# ===========================================================================
def _linea(strada: str, via: str, presa: Any, abbinato: Any, orologi: str = "na",
           ricezione: Any = "na") -> str:
    return (f"2026-09-25 10:00:00,000 INFO tempi_ordine ref=awlq1 strada={strada} "
            f"via={via} azione=place mode=paper ordine=o1 decisione_ms=na "
            f"ricezione_ms={ricezione} presa_ms={presa} place_ms=1 risposta_ms=na "
            f"abbinato_ms={abbinato} interno_ms=na risposta_bf_ms=na abbinato_fonte=na "
            f"orologi={orologi} esito=abbinato rif=x")


def test_f_script_p50_p95(capsys, tmp_path):
    righe = [_linea("coda", "coda", v, "na") for v in range(1, 21)]         # 1..20
    righe += [f"[runner] {_linea('canale', 'canale', 7, v)}" for v in (10, 20, 30, 40)]
    righe += [_linea("tennis", "coda", 5, "na", orologi="ricezione:db/pc", ricezione=v)
              for v in (100, 300)]
    righe += ["riga qualunque senza misure", "tempi_ordine senza_campi"]
    d = L.tabella(L.raccogli(righe))
    per = {(r["strada"], r["tratto"]): r for r in d}
    assert per[("coda", "presa_ms")]["n"] == 20
    assert per[("coda", "presa_ms")]["p50"] == pytest.approx(10.5)
    assert per[("coda", "presa_ms")]["p95"] == pytest.approx(19.05)
    assert per[("coda", "presa_ms")]["max"] == 20
    assert per[("canale", "abbinato_ms")]["p50"] == pytest.approx(25.0)
    assert per[("canale", "abbinato_ms")]["p95"] == pytest.approx(38.5)
    assert ("coda", "abbinato_ms") not in per                              # solo na
    assert per[("tennis", "ricezione_ms")]["misti"] == 2
    assert per[("tennis", "presa_ms")]["misti"] == 0
    assert L.percentile([5.0], 95) == 5.0 and L.percentile([], 50) is None
    # per via e da file, come si usera' al prossimo avvio
    f = tmp_path / "runner.log"
    f.write_text("\n".join(righe) + "\n", encoding="utf-8")
    assert L.main([str(f), "--per-via"]) == 0
    out = capsys.readouterr().out
    assert "coda" in out and "p95" in out and "19.1" in out


def test_f_script_legge_le_righe_vere_del_modulo(caplog):
    """Il formato scritto dal modulo e' quello che lo script legge."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    T.nuovo("awlq7", "coda", invio=time.time() * 1000.0 - 5, invio_orologio="db")
    T.presa("awlq7")
    T.fine("awlq7", False, "place RIFIUTATO = mercato non operabile")
    msg = [r.getMessage() for r in caplog.records if r.name == _LOGGER]
    d = L.tabella(L.raccogli(msg))
    assert {r["tratto"] for r in d} == {"ricezione_ms", "presa_ms"}
    assert all(r["strada"] == "coda" for r in d)


# ===========================================================================
# (g) traccia identica a strumentazione accesa e spenta
# ===========================================================================
def _giro_completo(monkeypatch, acceso: bool, n: int) -> Dict[str, Any]:
    monkeypatch.setenv("LIVE_TEMPI_ORDINE", "1" if acceso else "0")
    monkeypatch.setattr(wk, "_throttled", lambda *_a, **_k: False)
    monkeypatch.setattr(wk, "_LOCAL_SEEN", {})
    ch = _canale(monkeypatch)
    ch._requests.put_nowait(_ordine_desktop(1, f"e000000{n}-0000-4000-8000-000000000001"))
    ch._requests.put_nowait(LC.LocalRequest(ws=None, msg_id=2, method="order", params={
        "action": "cancel", "mode": "paper", "market_id": "1.1", "bet_id": "999",
        "client_ref": f"e000000{n}-0000-4000-8000-000000000002"}))
    adesso = time.time() * 1000.0
    sb = _SbSpia([_riga_coda_vera(1, adesso, {"source": "safe", "trade_id": 1}),
                  _riga_coda_vera(2, adesso, None) | {"market_id": "1.9"},   # errore
                  _riga_coda_vera(3, adesso, None) | {"action": "cancel", "bet_id": "1"}])
    market = _FakeMarket("1.1")
    wk._process_once(sb, _FakeFlumine({"1.1": market}), strategy=_STRAT)
    mercato = [(c[0], getattr(c[1], "side", None),
                getattr(getattr(c[1], "order_type", None), "price", None),
                tuple(sorted(c[2])) if isinstance(c[2], dict) else c[2])
               for c in market.calls]
    return {"db": list(sb.traccia), "mercato": mercato,
            "risposte": [(m, ok) for m, ok, _e in ch.risposte_test],
            "stati": [(r["id"], r["status"]) for r in sb.righe if r["id"] < 10_000]}


def test_g_traccia_identica_accesa_e_spenta(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=_LOGGER)
    spenta = _giro_completo(monkeypatch, False, 1)
    assert _righe(caplog) == []
    accesa = _giro_completo(monkeypatch, True, 2)
    assert len(_righe(caplog)) >= 3          # la misura c'era davvero (errori/annulli)
    assert accesa["db"] == spenta["db"]
    assert accesa["mercato"] == spenta["mercato"]
    assert accesa["risposte"] == spenta["risposte"]
    assert accesa["stati"] == spenta["stati"]
    # il giro ha lavorato davvero: place dal canale e dalla coda, righe chiuse
    assert [m[0] for m in spenta["mercato"]] == ["place_order", "place_order"]
    assert spenta["stati"] == [(1, "done"), (2, "error"), (3, "error")]
    assert spenta["risposte"] == [(1, True), (2, False)]
