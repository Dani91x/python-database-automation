# -*- coding: utf-8 -*-
"""08/10/2026 (cantiere W2) - CHIUDERE DALL'APP GLI ORDINI FATTI SUL SITO.

Ordine dell'utente: "se apro dal sito devo poter chiudere anche dall'app". Il
``greenup`` con ``params.esposizione='fuori_bot'`` copre PER INTERO l'esposizione
ABBINATA degli ordini del CONTO che non sono dei bot, letta con ``listCurrentOrders``
del mercato (``live_order_worker._do_greenup_fuori_bot``).

I finti parlano come il vero (catalogo par.7, difetti 1 e 27):
  * il CONTO e' il client VERO di flumine (``BetfairClient``) attorno all'``APIClient``
    VERO di betfairlightweight: si sostituisce SOLO il trasporto HTTP
    (``betting.request``), la risposta e' il JSON di Betfair (camelCase, chiavi di
    ``listCurrentOrders``) e la trasforma in ``CurrentOrders`` la libreria vera;
  * il book e' il ``MarketBook`` VERO di betfairlightweight dalle chiavi di Betfair;
  * le tabelle del DB hanno le colonne vere (``bet_id``, ``mode``, ``source``,
    ``client_ref``, ``params``);
  * i verdetti di conto dei bot sono le funzioni VERE di Mike e di Omega, con le righe
    normalizzate dalla funzione VERA ``omega_market._riga_corrente``.

Ogni test e' stato falsificato (mutazioni nel referto
``AUDIT_2026-10-08/W2_CHIUSURA_ORDINI_SITO.md``). ASCII-only.
"""
from __future__ import annotations

import inspect
import json
import pathlib
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import flumine  # noqa: F401 - applica il patch del ladder a dict (come in produzione)
import pytest
from betfairlightweight import APIClient
from betfairlightweight.resources import MarketBook
from flumine import BaseStrategy
from flumine.clients import BetfairClient

import Betfair.stream.live_order_worker as wk
from Betfair.stream.trading import esposizione_fuori_bot as EFB

MKT = "1.35"          # Over/Under 3,5: due esiti (Under/Over)
UNDER = 47999
OVER = 47998
MO = "1.100"          # Match Odds: tre esiti
HOME, AWAY, DRAW = 47999, 48000, 58805


# ---------------------------------------------------------------------------
# il CONTO: JSON di Betfair -> APIClient vero -> client vero di flumine
# ---------------------------------------------------------------------------
def ordine(bet_id: str, side: str, abbinato: float, prezzo: float, *,
           csr: Optional[str] = None, cor: Optional[str] = None, residuo: float = 0.0,
           sel: int = UNDER, market: str = MKT) -> Dict[str, Any]:
    """UN ordine come lo manda Betfair in ``listCurrentOrders`` (camelCase). Le chiavi
    facoltative assenti restano ASSENTI (un ordine del sito non ha ne'
    ``customerStrategyRef`` ne' ``customerOrderRef``)."""
    d: Dict[str, Any] = {
        "betId": bet_id, "marketId": market, "selectionId": sel, "handicap": 0.0,
        "priceSize": {"price": prezzo, "size": round(abbinato + residuo, 2)},
        "bspLiability": 0.0, "side": side,
        "status": "EXECUTABLE" if residuo > 0 else "EXECUTION_COMPLETE",
        "persistenceType": "LAPSE", "orderType": "LIMIT",
        "placedDate": "2026-10-08T12:00:00.000Z",
        "averagePriceMatched": prezzo if abbinato > 0 else 0.0,
        "sizeMatched": abbinato, "sizeRemaining": residuo, "sizeLapsed": 0.0,
        "sizeCancelled": 0.0, "sizeVoided": 0.0, "regulatorCode": "MALTA LOTTERIES AND GAMBLING AUTHORITY",
    }
    if abbinato > 0:
        d["matchedDate"] = "2026-10-08T12:00:01.000Z"
    if csr is not None:
        d["customerStrategyRef"] = csr
    if cor is not None:
        d["customerOrderRef"] = cor
    return d


class Conto:
    """Il trasporto HTTP di ``listCurrentOrders``: tutto il resto e' la libreria vera."""

    def __init__(self, ordini: List[Dict[str, Any]], *, per_pagina: int = 1000,
                 esplode: bool = False) -> None:
        self.ordini = list(ordini)
        self.per_pagina = per_pagina
        self.esplode = esplode
        self.chiamate: List[tuple] = []

    def request(self, method: str, params: Dict[str, Any], session: Any = None) -> tuple:
        self.chiamate.append((method, dict(params)))
        if self.esplode:
            raise RuntimeError("rete giu'")
        mids = [str(m) for m in (params.get("marketIds") or [])]
        tutti = [o for o in self.ordini if not mids or str(o["marketId"]) in mids]
        fr = int(params.get("fromRecord") or 0)
        pagina = tutti[fr:fr + self.per_pagina]
        altre = fr + len(pagina) < len(tutti)
        return (None, {"jsonrpc": "2.0", "id": 1,
                       "result": {"currentOrders": [dict(o) for o in pagina],
                                  "moreAvailable": altre}}, 0.01)


def client_reale(conto: Conto) -> BetfairClient:
    api = APIClient("utente", "password", app_key="chiave", lightweight=False)
    api.betting.request = conto.request
    return BetfairClient(api)


# ---------------------------------------------------------------------------
# il mercato (book vero) e il framework
# ---------------------------------------------------------------------------
def _runner(sel: int, back: float, lay: float) -> Dict[str, Any]:
    return {"selectionId": sel, "handicap": 0.0, "status": "ACTIVE",
            "ex": {"availableToBack": [{"price": back, "size": 500.0}],
                   "availableToLay": [{"price": lay, "size": 500.0}],
                   "tradedVolume": []}}


def book(market_id: str, runners: List[Dict[str, Any]]) -> MarketBook:
    return MarketBook(marketId=market_id, isMarketDataDelayed=False, status="OPEN",
                      betDelay=5, bspReconciled=False, complete=True, inplay=True,
                      numberOfWinners=1, numberOfRunners=len(runners),
                      numberOfActiveRunners=len(runners), totalMatched=0.0,
                      totalAvailable=0.0, crossMatching=True, runnersVoidable=False,
                      version=1, runners=runners, publishTime=1_700_000_000_000)


class Blotter:
    """Il blotter del runner: il green-up FUORI BOT non lo deve MAI leggere."""

    def __init__(self) -> None:
        self.letture = 0

    def get_exposures(self, strategy: Any, lookup: tuple) -> Dict[str, float]:
        self.letture += 1
        return {"matched_profit_if_win": 99.0, "matched_profit_if_lose": -99.0}

    def strategy_orders(self, strategy: Any) -> List[Any]:
        return []


class Mercato:
    def __init__(self, market_id: str, mb: MarketBook) -> None:
        self.market_id = market_id
        self.market_book = mb
        self.blotter = Blotter()
        self.piazzati: List[tuple] = []

    def place_order(self, order: Any, **kw: Any) -> bool:
        self.piazzati.append((order, kw))
        return True


def mercato_ou(lay_under: float = 1.40, back_under: float = 1.39) -> Mercato:
    return Mercato(MKT, book(MKT, [_runner(UNDER, back_under, lay_under),
                                   _runner(OVER, 3.5, 3.6)]))


def mercato_mo(back: float = 2.98, lay: float = 3.0) -> Mercato:
    return Mercato(MO, book(MO, [_runner(HOME, back, lay), _runner(AWAY, 4.0, 4.2),
                                 _runner(DRAW, 3.4, 3.5)]))


def framework(mercato: Mercato, conto: Conto) -> Any:
    fl = SimpleNamespace(markets=SimpleNamespace(markets={mercato.market_id: mercato}))
    # il runner LIVE registra i DUE client (reale + simulato), come in produzione
    simulato = BetfairClient(APIClient("utente", "password", app_key="chiave"),
                             paper_trade=True)
    fl.clients = [client_reale(conto), simulato]
    return fl


# ---------------------------------------------------------------------------
# il DB: tabelle con le colonne vere
# ---------------------------------------------------------------------------
class _Q:
    def __init__(self, sb: "Sb", nome: str) -> None:
        self.sb, self.nome = sb, nome
        self.op = "select"
        self.payload: Dict[str, Any] = {}
        self.filtri: List[tuple] = []

    def select(self, *_a: Any) -> "_Q":
        self.op = "select"
        return self

    def update(self, payload: Dict[str, Any]) -> "_Q":
        self.op, self.payload = "update", dict(payload)
        return self

    def insert(self, payload: Dict[str, Any]) -> "_Q":
        self.op, self.payload = "insert", dict(payload)
        return self

    def eq(self, k: str, v: Any) -> "_Q":
        self.filtri.append(("eq", k, v))
        return self

    def in_(self, k: str, v: List[Any]) -> "_Q":
        self.filtri.append(("in", k, [str(x) for x in v]))
        return self

    def gte(self, k: str, v: Any) -> "_Q":
        self.filtri.append(("gte", k, v))
        return self

    def order(self, k: str, **_kw: Any) -> "_Q":
        self.ordina = k
        return self

    def limit(self, n: int) -> "_Q":
        self.massimo = n
        return self

    def _ok(self, r: Dict[str, Any]) -> bool:
        for tipo, k, v in self.filtri:
            if tipo == "eq" and r.get(k) != v:
                return False
            if tipo == "in" and str(r.get(k)) not in v:
                return False
            if tipo == "gte" and not (r.get(k) is not None and str(r.get(k)) >= str(v)):
                return False
        return True

    def execute(self) -> Any:
        if self.sb.esplode_su and self.nome in self.sb.esplode_su and self.op == "select":
            raise RuntimeError(f"DB giu' su {self.nome}")
        righe = self.sb.tabelle.setdefault(self.nome, [])
        if self.op == "insert":
            righe.append(dict(self.payload))
            return SimpleNamespace(data=[dict(self.payload)])
        if self.op == "select":
            self.sb.letture.append(self.nome)
        trovate = [r for r in righe if self._ok(r)]
        if getattr(self, "ordina", None):
            trovate.sort(key=lambda r: r.get(self.ordina))
        if getattr(self, "massimo", None) is not None and self.op == "select":
            trovate = trovate[:self.massimo]
        if self.op == "update":
            for r in trovate:
                r.update(self.payload)
        return SimpleNamespace(data=[dict(r) for r in trovate])


class Sb:
    def __init__(self, **tabelle: List[Dict[str, Any]]) -> None:
        self.tabelle: Dict[str, List[Dict[str, Any]]] = {k: list(v) for k, v in tabelle.items()}
        self.esplode_su: Optional[set] = None
        self.letture: List[str] = []
        self.rpc_chiamate: List[tuple] = []

    def table(self, nome: str) -> _Q:
        return _Q(self, nome)

    def rpc(self, nome: str, args: Dict[str, Any]) -> Any:
        self.rpc_chiamate.append((nome, args))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=999))

    def riga(self, rid: int) -> Dict[str, Any]:
        return next(r for r in self.tabelle["betfair_live_order_requests"] if r["id"] == rid)


def riga_greenup(rid: int = 501, *, market: str = MKT, sel: int = UNDER,
                 mode: str = "live", params: Any = None) -> Dict[str, Any]:
    return {"id": rid, "action": "greenup", "mode": mode, "status": "processing",
            "client_ref": f"ui-{rid}", "market_id": market, "selection_id": sel,
            "handicap": 0, "side": None, "price": None, "size": None,
            "params": ({"esposizione": "fuori_bot"} if params is None else params),
            "result": None, "error": None, "bet_id": None}


STRAT = BaseStrategy(market_filter={}, name="live_trading")


@pytest.fixture(autouse=True)
def _runner_live(monkeypatch):
    monkeypatch.setattr(wk, "_modo_processo", lambda: "LIVE")
    monkeypatch.setattr(wk, "_live_order_mode", lambda: "LIVE")
    monkeypatch.setattr(wk, "_kill_switch", lambda: False)
    monkeypatch.setattr(wk, "_jurisdiction", lambda: "it")
    monkeypatch.setattr(wk, "_max_stake", lambda: 10.0)


def esegui(sb: Sb, fl: Any, riga: Dict[str, Any]) -> Dict[str, Any]:
    """Come il giro della coda (``_process_once``): dispatch, e su eccezione la riga
    'error' scritta da ``_write_error``."""
    sb.tabelle.setdefault("betfair_live_order_requests", []).append(riga)
    try:
        wk._dispatch(sb, fl, riga, riga["mode"], {"live": STRAT, "paper": STRAT})
    except Exception as ex:  # noqa: BLE001
        wk._write_error(sb, riga["id"], riga, riga["mode"], ex)
    return sb.riga(riga["id"])


def piazzati(m: Mercato) -> List[tuple]:
    return [(o.side, o.order_type.price, o.order_type.size) for o, _kw in m.piazzati]


# ===========================================================================
# 1. ESPOSIZIONE DAI SOLI ORDINI DEL SITO
# ===========================================================================
def test_solo_sito_back_si_copre_con_una_lay_al_miglior_lay():
    """Sito: BACK Under 5 @3,0 -> W=10, L=-5. Miglior lay 2,5: LAY (10+5)/2,5 = 6,00,
    con il ref di strategia del terminale manuale ('live'): e' un ordine dell'utente."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = Conto([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME)])
    sb = Sb()
    r = esegui(sb, framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "done", r.get("error")
    assert piazzati(m) == [("LAY", 2.5, 6.0)]
    kw = m.piazzati[0][1]
    assert kw["customer_strategy_ref"] == "live"
    assert kw["client"] is not None and kw["client"].paper_trade is False
    res = r["result"]
    assert res["esposizione"] == "fuori_bot"
    assert res["conto"]["fuori_bot"] == ["S1"] and res["conto"]["bot"] == []
    assert (res["conto"]["w"], res["conto"]["l"]) == (10.0, -5.0)
    assert res["side"] == "lay" and res["size"] == 6.0
    # il conto letto UNA volta, sul SOLO mercato della riga; il blotter MAI
    assert len(conto.chiamate) == 1
    metodo, par = conto.chiamate[0]
    assert metodo.endswith("listCurrentOrders") and par["marketIds"] == [MO]
    assert "customerStrategyRefs" not in par
    assert m.blotter.letture == 0


def test_solo_sito_lay_si_copre_con_una_back_al_miglior_back():
    """Sito: LAY 4 @2,5 -> W=-6, L=+4, diff -10. Miglior back 2,0: BACK 10/2 = 5,00
    (multiplo di 0,50: nessun arrotondamento della regola delle punte)."""
    m = mercato_mo(back=2.0, lay=2.02)
    conto = Conto([ordine("S1", "LAY", 4.0, 2.5, market=MO, sel=HOME)])
    r = esegui(Sb(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "done", r.get("error")
    assert piazzati(m) == [("BACK", 2.0, 5.0)]
    assert (r["result"]["conto"]["w"], r["result"]["conto"]["l"]) == (-6.0, 4.0)


# ===========================================================================
# 2. SITO + APP, SITO + BOT
# ===========================================================================
def test_sito_e_app_si_sommano():
    """Sito BACK 5 @3 (W 10, L -5) + app ('live') BACK 2 @4 (W 6, L -2): W 16, L -7,
    LAY 23/2,5 = 9,20."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = Conto([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME),
                   ordine("A1", "BACK", 2.0, 4.0, csr="live", cor="9f1c2-1a", market=MO,
                          sel=HOME)])
    sb = Sb(betfair_live_orders=[{"bet_id": "A1", "mode": "live", "source": "runner"}])
    r = esegui(sb, framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "done", r.get("error")
    assert piazzati(m) == [("LAY", 2.5, 9.2)]
    assert sorted(r["result"]["conto"]["fuori_bot"]) == ["A1", "S1"]


def test_gli_ordini_dei_bot_sulla_stessa_selezione_non_si_toccano():
    """Sulla selezione: sito BACK 5 @3, Mike (REST, csr 'mike', ref mike-t1) BACK 10 @3,
    Omega dalla CODA del runner (csr 'live', bet_id in omega_trades) BACK 3 @3, lo
    scalper (specchio 'scalper') BACK 1 @3, Safe appena piazzato dalla coda (bet_id
    solo nella riga di coda con client_ref safe-t4). La copertura e' SOLO del sito."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = Conto([
        ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME),
        ordine("M1", "BACK", 10.0, 3.0, csr="mike", cor="mike-t1", market=MO, sel=HOME),
        ordine("O1", "BACK", 3.0, 3.0, csr="live", cor="abc-1", market=MO, sel=HOME),
        ordine("X1", "BACK", 1.0, 3.0, csr="live", cor="abc-2", market=MO, sel=HOME),
        ordine("F1", "BACK", 2.0, 3.0, csr="live", cor="abc-3", market=MO, sel=HOME),
    ])
    sb = Sb(omega_trades=[{"id": 7, "bet_id": "O1", "mode": "live"}],
            betfair_live_orders=[{"bet_id": "X1", "mode": "live", "source": "scalper"},
                                 {"bet_id": "O1", "mode": "live", "source": "runner"}],
            betfair_live_order_requests=[{"id": 300, "bet_id": "F1", "mode": "live",
                                          "client_ref": "safe-t4",
                                          "params": {"source": "safe"}}])
    r = esegui(sb, framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "done", r.get("error")
    assert piazzati(m) == [("LAY", 2.5, 6.0)], "coperto anche un ordine di un bot"
    motivi = {b["bet_id"]: b["motivo"] for b in r["result"]["conto"]["bot"]}
    assert motivi == {"M1": "strategia:mike", "O1": "tabella:omega_trades",
                      "X1": "specchio:scalper", "F1": "coda:safe-t4"}
    assert r["result"]["conto"]["fuori_bot"] == ["S1"]


@pytest.mark.parametrize("csr", ["omega", "safe", "safe_tennis", "LiveScalperStr", "x"])
def test_ogni_strategia_che_non_e_dell_utente_e_esclusa(csr):
    """Nel dubbio NON fuori bot: qualunque ``customerStrategyRef`` che non sia
    assente (sito) o 'live' (app) e' escluso, anche se il DB non ne sa niente."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = Conto([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME),
                   ordine("B1", "BACK", 4.0, 3.0, csr=csr, market=MO, sel=HOME)])
    r = esegui(Sb(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert piazzati(m) == [("LAY", 2.5, 6.0)]
    assert r["result"]["conto"]["bot"] == [{"bet_id": "B1", "motivo": f"strategia:{csr}"}]


def test_mike_role_utente_resta_escluso_come_nella_rpc():
    """Una riga di mike_trades per quel bet_id (anche ``role='utente'``) lo esclude:
    stessa regola della RPC ``get_live_orders_account_open`` (la pagina non lo
    mostra fra gli ordini fuori bot)."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = Conto([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME),
                   ordine("U9", "LAY", 5.0, 3.0, market=MO, sel=HOME)])
    sb = Sb(mike_trades=[{"id": 3, "bet_id": "U9", "mode": "live", "role": "utente"}])
    r = esegui(sb, framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert piazzati(m) == [("LAY", 2.5, 6.0)]
    assert r["result"]["conto"]["bot"] == [{"bet_id": "U9", "motivo": "tabella:mike_trades"}]


# ===========================================================================
# 3. PARZIALI, NON ABBINATI, PIATTA, IDEMPOTENZA
# ===========================================================================
def test_parziale_conta_solo_l_abbinato():
    """Sito BACK 10 chiesti, 4 abbinati @3 e 6 ancora in attesa: si copre l'abbinato
    (W 8, L -4 -> LAY 12/2,5 = 4,80), il residuo NON conta."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = Conto([ordine("S1", "BACK", 4.0, 3.0, residuo=6.0, market=MO, sel=HOME)])
    r = esegui(Sb(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "done", r.get("error")
    assert piazzati(m) == [("LAY", 2.5, 4.8)]


def test_ordini_non_abbinati_non_contano_e_non_si_piazza_niente():
    m = mercato_mo(back=2.48, lay=2.5)
    conto = Conto([ordine("S1", "BACK", 0.0, 3.0, residuo=5.0, market=MO, sel=HOME)])
    r = esegui(Sb(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "done" and piazzati(m) == []
    assert "gia' piatta" in r["result"]["detail"]
    assert r["result"]["size"] is None


def test_idempotenza_il_secondo_comando_trova_la_posizione_piatta():
    """Primo comando: LAY 6,00 @2,5. La copertura (ordine dell'app, csr 'live') si
    abbina e sta sul conto. Secondo comando (doppio click, o retry): la rilettura del
    conto la contiene -> W = L -> nessun ordine."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = Conto([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME)])
    fl = framework(m, conto)
    sb = Sb()
    r1 = esegui(sb, fl, riga_greenup(601, market=MO, sel=HOME))
    assert r1["status"] == "done" and piazzati(m) == [("LAY", 2.5, 6.0)]
    conto.ordini.append(ordine("H1", "LAY", 6.0, 2.5, csr="live", cor="9f1c2-77",
                               market=MO, sel=HOME))
    sb.tabelle["betfair_live_orders"] = [{"bet_id": "H1", "mode": "live",
                                          "source": "runner"}]
    r2 = esegui(sb, fl, riga_greenup(602, market=MO, sel=HOME))
    assert r2["status"] == "done", r2.get("error")
    assert piazzati(m) == [("LAY", 2.5, 6.0)], "secondo ordine su posizione piatta"
    assert "gia' piatta" in r2["result"]["detail"]
    assert (r2["result"]["conto"]["w"], r2["result"]["conto"]["l"]) == (1.0, 1.0)


def test_copertura_dell_app_ancora_appesa_sul_lato_della_copertura_ferma_il_secondo():
    """La prima copertura e' ancora EXECUTABLE non abbinata: un secondo ordine potrebbe
    abbinarsi insieme e invertire la posizione -> rifiuto esplicito, nessun ordine."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = Conto([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME),
                   ordine("H1", "LAY", 0.0, 2.5, csr="live", cor="9f1c2-77", residuo=6.0,
                          market=MO, sel=HOME)])
    r = esegui(Sb(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "error" and piazzati(m) == []
    assert "ancora non abbinato" in r["error"]


def test_un_ordine_del_sito_appeso_sul_lato_della_copertura_non_ferma():
    """Un ordine del SITO non abbinato non e' una nostra copertura: non conta e non
    ferma (il contratto: i non abbinati non contano)."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = Conto([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME),
                   ordine("S2", "LAY", 0.0, 2.6, residuo=3.0, market=MO, sel=HOME)])
    r = esegui(Sb(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "done" and piazzati(m) == [("LAY", 2.5, 6.0)]


def test_mercato_a_due_esiti_posizione_piatta_sul_mercato():
    """Sito BACK Under 5 @2 e BACK Over 5 @2: il MERCATO e' piatto (vince l'uno o
    l'altro: +5 -5 = 0). Come nel green-up di sempre (punto 9 del 02/10) la posizione
    si legge sul mercato: nessun ordine (mai una seconda chiusura)."""
    m = mercato_ou(lay_under=2.02, back_under=2.0)
    conto = Conto([ordine("S1", "BACK", 5.0, 2.0, sel=UNDER),
                   ordine("S2", "BACK", 5.0, 2.0, sel=OVER)])
    r = esegui(Sb(), framework(m, conto), riga_greenup(sel=UNDER))
    assert r["status"] == "done", r.get("error")
    assert piazzati(m) == []
    assert "due esiti" in r["result"]["detail"]


def test_paginazione_del_conto():
    """Tre pagine da 2 ordini: tutti contano (moreAvailable seguito)."""
    m = mercato_mo(back=2.48, lay=2.5)
    ordini = [ordine(f"S{i}", "BACK", 1.0, 3.0, market=MO, sel=HOME) for i in range(5)]
    conto = Conto(ordini, per_pagina=2)
    r = esegui(Sb(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert len(conto.chiamate) == 3
    assert [c[1]["fromRecord"] for c in conto.chiamate] == [0, 2, 4]
    assert piazzati(m) == [("LAY", 2.5, 6.0)]
    assert len(r["result"]["conto"]["fuori_bot"]) == 5


# ===========================================================================
# 4. RIFIUTI ESPLICITI: paper, conto/DB illeggibili, parametri, comando di un bot
# ===========================================================================
def test_paper_rifiutato_con_motivo_e_nessuna_lettura():
    m = mercato_mo()
    conto = Conto([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME)])
    r = esegui(Sb(), framework(m, conto), riga_greenup(market=MO, sel=HOME, mode="paper"))
    assert r["status"] == "error" and piazzati(m) == []
    assert "solo LIVE" in r["error"]
    assert conto.chiamate == []


def test_conto_illeggibile_rifiuto_esplicito():
    m = mercato_mo()
    conto = Conto([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME)], esplode=True)
    r = esegui(Sb(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "error" and piazzati(m) == []
    assert "conto non leggibile" in r["error"]


@pytest.mark.parametrize("tabella", ["omega_trades", "betfair_live_orders",
                                     "betfair_live_order_requests"])
def test_db_illeggibile_rifiuto_esplicito(tabella):
    """Mai un "fuori bot" dedotto da una lettura KO: rifiuto, nessun ordine."""
    m = mercato_mo()
    conto = Conto([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME)])
    sb = Sb()
    sb.esplode_su = {tabella}
    r = esegui(sb, framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "error" and piazzati(m) == []
    assert "conto non leggibile" in r["error"]


def test_runner_senza_client_reale_rifiuto_esplicito():
    """Framework senza registro dei client (nessun client reale): niente conto."""
    m = mercato_mo()
    fl = SimpleNamespace(markets=SimpleNamespace(markets={MO: m}))
    r = esegui(Sb(), fl, riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "error" and piazzati(m) == []
    assert "conto non leggibile" in r["error"]


def test_runner_in_paper_non_serve_la_riga_live(monkeypatch):
    monkeypatch.setattr(wk, "_modo_processo", lambda: "PAPER")
    m = mercato_mo()
    conto = Conto([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME)])
    r = esegui(Sb(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "error" and piazzati(m) == [] and conto.chiamate == []


@pytest.mark.parametrize("extra", [{"amount": 2.0}, {"target_price": 3.5},
                                   {"place_at_ticks": 2}, {"cancel_unmatched": True},
                                   {"fraction": 0.5}, {"risk_rule_id": 4},
                                   {"comando": {"attore": "mike", "ref": "mike-t1"}}])
def test_parametri_del_greenup_parziale_e_comandi_dei_bot_rifiutati(extra):
    m = mercato_mo()
    conto = Conto([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME)])
    r = esegui(Sb(), framework(m, conto),
               riga_greenup(market=MO, sel=HOME, params={"esposizione": "fuori_bot", **extra}))
    assert r["status"] == "error" and piazzati(m) == [] and conto.chiamate == []


@pytest.mark.parametrize("valore", ["fuori-bot", "bot", "", 1, True])
def test_valore_di_esposizione_sconosciuto_rifiutato(valore):
    """Un refuso NON ripiega sul green-up del blotter (sarebbe un'altra posizione)."""
    m = mercato_mo()
    conto = Conto([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME)])
    r = esegui(Sb(), framework(m, conto),
               riga_greenup(market=MO, sel=HOME, params={"esposizione": valore}))
    assert r["status"] == "error" and piazzati(m) == []
    assert m.blotter.letture == 0


def test_frazione_uno_e_ft_ammessi():
    """Il re-hedge del follow-through porta ``fraction=1.0``, ``ft_parent``,
    ``ft_retry``: e' la stessa copertura piena."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = Conto([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME)])
    r = esegui(Sb(), framework(m, conto), riga_greenup(
        market=MO, sel=HOME, params={"esposizione": "fuori_bot", "fraction": 1.0,
                                     "ft_parent": 9, "ft_retry": 1}))
    assert r["status"] == "done" and piazzati(m) == [("LAY", 2.5, 6.0)]


def test_dalla_coda_del_runner_process_once():
    """Il cammino vero della coda: riga 'pending' -> claim -> dispatch -> 'done'."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = Conto([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME)])
    riga = riga_greenup(market=MO, sel=HOME)
    riga["status"] = "pending"
    sb = Sb(betfair_live_order_requests=[riga])
    wk._LAST_CYCLE.clear()
    n = wk._process_once(sb, framework(m, conto), strategy={"live": STRAT, "paper": STRAT})
    assert n >= 1
    assert sb.riga(riga["id"])["status"] == "done"
    assert piazzati(m) == [("LAY", 2.5, 6.0)]


# ===========================================================================
# 5. FOLLOW-THROUGH (A4) COERENTE
# ===========================================================================
def test_il_rehedge_di_una_copertura_fuori_bot_resta_fuori_bot():
    sb = Sb()
    madre = {"id": 700, "action": "greenup", "mode": "live", "market_id": MO,
             "selection_id": HOME, "handicap": 0, "params": {"esposizione": "fuori_bot"}}
    leg = {"market_id": MO, "selection_id": HOME, "handicap": 0.0}
    assert wk._ft_enqueue_rehedge(sb, madre, leg, 1, 1.0) == 999
    nome, args = sb.rpc_chiamate[-1]
    assert nome == "request_betfair_live_order"
    assert args["p"]["params"] == {"fraction": 1.0, "ft_parent": 700, "ft_retry": 1,
                                   "esposizione": "fuori_bot"}


def test_il_rehedge_del_greenup_di_sempre_e_identico_a_prima():
    sb = Sb()
    madre = {"id": 701, "action": "greenup", "mode": "live", "market_id": MO,
             "selection_id": HOME, "handicap": 0, "params": {"fraction": 0.5}}
    leg = {"market_id": MO, "selection_id": HOME, "handicap": 0.0}
    wk._ft_enqueue_rehedge(sb, madre, leg, 2, 0.5)
    assert sb.rpc_chiamate[-1][1]["p"] == {
        "client_ref": f"ft701s{HOME}r2", "action": "greenup", "mode": "live",
        "market_id": MO, "selection_id": HOME, "handicap": 0,
        "params": {"fraction": 0.5, "ft_parent": 701, "ft_retry": 2}}


def test_il_follow_through_segue_la_copertura_fuori_bot():
    """La riga 'done' della copertura ha bet_id/ref/size come il green-up di sempre:
    il follow-through ne ricava la gamba da seguire."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = Conto([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME)])
    sb = Sb()
    r = esegui(sb, framework(m, conto), riga_greenup(800, market=MO, sel=HOME))
    gambe = wk._ft_legs_from_result(r)
    assert gambe == [{"market_id": MO, "selection_id": HOME, "handicap": 0.0,
                      "ref": "awlq800", "bet_id": None}]


# ===========================================================================
# 6. PARITA': SENZA ``esposizione`` IL GREEN-UP E' QUELLO DI PRIMA (b5547eb)
# ===========================================================================
_SNAPSHOT = pathlib.Path(__file__).parent / "dati" / "greenup_parita_b5547eb.json"


class _BlotterParita:
    def __init__(self, exp: Dict[int, Dict[str, float]]) -> None:
        self.exp = exp

    def get_exposures(self, strategy: Any, lookup: tuple) -> Dict[str, float]:
        return dict(self.exp.get(int(lookup[1]), {"matched_profit_if_win": 0.0,
                                                  "matched_profit_if_lose": 0.0}))

    def strategy_orders(self, strategy: Any) -> List[Any]:
        return []


class _MercatoParita:
    def __init__(self, market_id: str, mb: MarketBook, exp: Dict[int, Dict[str, float]]):
        self.market_id = market_id
        self.market_book = mb
        self.blotter = _BlotterParita(exp)
        self.calls: List[Dict[str, Any]] = []

    def place_order(self, order: Any, **kw: Any) -> bool:
        self.calls.append({"side": order.side, "price": order.order_type.price,
                           "size": order.order_type.size,
                           "persistence": order.order_type.persistence_type,
                           "kw": sorted(kw.keys()),
                           "csr": kw.get("customer_strategy_ref")})
        return True


class _SbParita:
    def __init__(self) -> None:
        self.updates: List[Dict[str, Any]] = []
        self.altro: List[str] = []

    def table(self, name: str) -> Any:
        sb = self

        class Q:
            def __init__(self) -> None:
                self.payload = None

            def update(self, payload):
                self.payload = payload
                return self

            def insert(self, payload):
                sb.altro.append(name)
                return self

            def select(self, *a):
                sb.altro.append("select:" + name)
                return self

            def eq(self, *a):
                return self

            def in_(self, *a):
                return self

            def execute(self):
                if self.payload is not None and name == "betfair_live_order_requests":
                    p = dict(self.payload)
                    p.pop("processed_at", None)
                    sb.updates.append(p)
                return SimpleNamespace(data=[])
        return Q()

    def rpc(self, *a, **k):
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=None))


def _scenari_parita() -> List[Dict[str, Any]]:
    out = []
    lay_led = {HOME: {"matched_profit_if_win": 10.0, "matched_profit_if_lose": -5.0}}
    back_led = {HOME: {"matched_profit_if_win": -8.0, "matched_profit_if_lose": 4.0}}
    flat = {HOME: {"matched_profit_if_win": 3.0, "matched_profit_if_lose": 3.0}}
    plist = [None, {}, {"fraction": 0.5}, {"amount": 2.5}, {"amount": 100.0},
             {"target_price": 3.5}, {"place_at_ticks": 2}, {"persistence": "PERSIST"},
             {"cancel_unmatched": True}, {"esposizione": None},
             {"esposizione": None, "fraction": 0.25}, {"amount": "x"},
             {"persistence": "BOH"}, {"cancel_unmatched": True, "target_price": 3.5},
             {"fraction": 1.0, "ft_parent": 9, "ft_retry": 1},
             {"allow_sub_minimum": False, "fraction": 0.05}]
    for nome_exp, exp in (("lay_led", lay_led), ("back_led", back_led), ("flat", flat)):
        for i, p in enumerate(plist):
            out.append({"nome": f"MO-{nome_exp}-{i}", "market": "1.100", "exp": exp,
                        "params": p})
    ou_exp = {HOME: {"matched_profit_if_win": 6.0, "matched_profit_if_lose": -3.0},
              48000: {"matched_profit_if_win": -2.0, "matched_profit_if_lose": 1.0}}
    for i, p in enumerate([None, {"fraction": 0.5}, {"esposizione": None}]):
        out.append({"nome": f"OU-{i}", "market": "1.200", "exp": ou_exp, "params": p})
    return out


def _esegui_parita(sc: Dict[str, Any]) -> Dict[str, Any]:
    def r(sel, atb, atl):
        return {"selectionId": sel, "handicap": 0.0, "status": "ACTIVE",
                "ex": {"availableToBack": [{"price": p, "size": s} for p, s in atb],
                       "availableToLay": [{"price": p, "size": s} for p, s in atl],
                       "tradedVolume": []}}
    if sc["market"] == "1.100":
        mb = book("1.100", [r(HOME, [(2.98, 60)], [(3.0, 80)]), r(48000, [(4.0, 10)], [(4.2, 10)]),
                            r(58805, [(3.4, 10)], [(3.5, 10)])])
    else:
        mb = book("1.200", [r(HOME, [(1.9, 60)], [(1.95, 80)]), r(48000, [(2.0, 10)], [(2.1, 10)])])
    mb.publish_time = 1_700_000_000_000
    m = _MercatoParita(sc["market"], mb, sc["exp"])
    fl = SimpleNamespace(markets=SimpleNamespace(markets={sc["market"]: m}))
    row = {"id": 77, "action": "greenup", "mode": "paper", "status": "processing",
           "market_id": sc["market"], "selection_id": HOME, "handicap": 0,
           "side": None, "price": None, "size": None, "params": sc["params"],
           "result": None, "error": None}
    sb = _SbParita()
    errore = None
    try:
        wk._dispatch(sb, fl, row, "paper", STRAT)
    except Exception as ex:  # noqa: BLE001
        errore = f"{type(ex).__name__}: {ex}"
    return json.loads(json.dumps({"calls": m.calls, "updates": sb.updates,
                                  "errore": errore, "altro": sb.altro}, default=str))


def test_parita_byte_per_byte_con_il_greenup_di_b5547eb(monkeypatch):
    """51 scenari (frazione, importo, prezzo scelto, tick oltre, persistenza, annullo dei
    non abbinati, ``esposizione: null``, parametri malformati, sotto-minimo, mercato a
    due esiti) eseguiti dal worker di b5547eb hanno prodotto ``dati/greenup_parita_
    b5547eb.json`` (ordini piazzati con tutti i loro parametri, righe di coda scritte,
    errori, tabelle toccate). Il worker di oggi deve riprodurli IDENTICI."""
    monkeypatch.setattr(wk, "_modo_processo", lambda: "PAPER")
    monkeypatch.setattr(wk, "_live_order_mode", lambda: "PAPER")
    attesi = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    scenari = _scenari_parita()
    assert len(scenari) == len(attesi) == 51
    diversi = [sc["nome"] for sc in scenari if _esegui_parita(sc) != attesi[sc["nome"]]]
    assert diversi == []
    # la fotografia non e' vuota: ordini, rifiuti e no-op ci sono tutti
    assert sum(1 for v in attesi.values() if v["calls"]) == 27
    assert sum(1 for v in attesi.values() if v["errore"]) == 11


# ===========================================================================
# 7. LA LOGICA PURA
# ===========================================================================
def test_riconoscimento_per_riferimenti():
    f = EFB.motivo_bot_da_riferimenti
    assert f({"betId": "1"}) is None                                   # sito
    assert f({"betId": "1", "customerStrategyRef": "live"}) is None     # app
    assert f({"betId": "1", "customerStrategyRef": "LIVE"}) is None
    assert f({"betId": "1", "customerStrategyRef": "mike"}) == "strategia:mike"
    assert f({"betId": "1", "customerStrategyRef": "tennis"}) == "strategia:tennis"
    assert f({"betId": "1", "customerOrderRef": "mike-t5"}) == "ref:mike-t5"
    assert f({"betId": "1", "customerOrderRef": "safe_tennis-t3"}) == "ref:safe_tennis-t3"
    assert f({"betId": "1", "customerStrategyRef": "live",
              "customerOrderRef": "omega-t9"}) == "ref:omega-t9"
    assert f({"betId": "1", "customerOrderRef": "9f1c2-1a"}) is None


def test_riconoscimento_dalla_riga_di_coda():
    f = EFB.motivo_bot_da_coda
    assert f({"client_ref": "omega-t1", "params": {}}) == "coda:omega-t1"
    assert f({"client_ref": "ui-1", "params": {"source": "safe"}}) == "coda_source:safe"
    assert f({"client_ref": "ui-1", "params": {"source": "scalper"}}) == "coda_source:scalper"
    assert f({"client_ref": "ui-1", "params": {"comando": {"attore": "mike"}}}) \
        == "coda_attore:mike"
    assert f({"client_ref": "ui-1", "params": {"comando": {"attore": "desktop"}}}) is None
    assert f({"client_ref": "ft12s4r1", "params": {"fraction": 1.0}}) is None
    assert f({"client_ref": None, "params": None}) is None


def test_esposizione_abbinata_e_quella_di_flumine():
    """BACK 5 @3 -> (+10, -5); LAY 4 @2,5 -> (-6, +4); i due insieme (+4, -1). I
    numeri sono quelli di ``flumine.utils.calculate_matched_exposure``."""
    o = [ordine("a", "BACK", 5.0, 3.0), ordine("b", "LAY", 4.0, 2.5),
         ordine("c", "BACK", 0.0, 9.0, residuo=3.0)]
    assert EFB.esposizione_abbinata(o[:1]) == (10.0, -5.0)
    assert EFB.esposizione_abbinata(o[1:2]) == (-6.0, 4.0)
    assert EFB.esposizione_abbinata(o) == (4.0, -1.0)
    assert EFB.esposizione_abbinata([]) == (0.0, 0.0)
    rotto = dict(ordine("d", "BACK", 2.0, 3.0), averagePriceMatched=0.0)
    with pytest.raises(ValueError):
        EFB.esposizione_abbinata([rotto])


def test_normalizzazione_dal_current_order_vero():
    """``CurrentOrder`` vero di betfairlightweight -> chiavi camelCase di Betfair."""
    from betfairlightweight.resources.bettingresources import CurrentOrders

    co = CurrentOrders(currentOrders=[ordine("S1", "LAY", 2.0, 4.5, csr="live",
                                             cor="x-1")], moreAvailable=False)
    n = EFB.normalizza(co.orders[0])
    assert (n["betId"], n["side"], n["sizeMatched"], n["averagePriceMatched"],
            n["customerStrategyRef"], n["customerOrderRef"], n["selectionId"]) == \
        ("S1", "LAY", 2.0, 4.5, "live", "x-1", UNDER)


def test_effetto_sui_bot():
    """08/10 (W3a): ``effetto_sui_bot`` prevede il verdetto dei bot con la LORO
    funzione (``esiti_ordini_canale.verdetto_posizione``, in ESPOSIZIONE): conta la
    parte direzionale degli ordini dell'utente, non il netto in size."""
    mike = [ordine("M1", "BACK", 10.0, 1.50, csr="mike", cor="mike-t1")]
    sito = [ordine("S1", "BACK", 5.0, 1.50)]
    # green-up dell'utente del SUO back col prezzo sceso (LAY 5,36 @1,40): in size
    # il netto scende a 9,64 ma la direzione dell'utente va a ~0 -> Mike intero
    assert EFB.effetto_sui_bot({"mike": mike}, sito,
                               EFB.riga_copertura("lay", 5.36, 1.40)) == []
    # secondo esempio del coordinatore: Mike back 2, sito back 10 @5,0, copertura
    # LAY 33,33 @1,50 -> in size "chiusa" (falso), in esposizione intero
    assert EFB.effetto_sui_bot({"mike": [ordine("M2", "BACK", 2.0, 1.50, csr="mike")]},
                               [ordine("S2", "BACK", 10.0, 5.0)],
                               EFB.riga_copertura("lay", 33.33, 1.50)) == []
    # una copertura che e' DIREZIONALE contro Mike (posizione dell'utente sull'ALTRO
    # esito, coperta sulla selezione di Mike): LAY 6 @1,50 -> 15-9 = 6 di 15: ridotta
    e = EFB.effetto_sui_bot({"mike": mike}, [], EFB.riga_copertura("lay", 6.0, 1.50))
    assert [(x["bot"], x["verdetto"], x["viva_dopo"]) for x in e] == [("mike", "ridotta", 4.0)]
    # ... LAY 20 @1,50 -> direzione -30 contro +15: chiusa
    e = EFB.effetto_sui_bot({"mike": mike}, [], EFB.riga_copertura("lay", 20.0, 1.50))
    assert [(x["bot"], x["verdetto"]) for x in e] == [("mike", "chiusa")]
    # bot LAY (Omega -5,26 @3): una copertura LAY lo lascia intero, una BACK che ne
    # annulla la size lo chiude (stessa etichetta del verdetto vero: «a pari size»)
    omega = [ordine("O1", "LAY", 5.26, 3.0, csr="omega")]
    assert EFB.effetto_sui_bot({"omega": omega}, [], EFB.riga_copertura("lay", 6.0, 2.5)) == []
    e = EFB.effetto_sui_bot({"omega": omega}, [], EFB.riga_copertura("back", 6.0, 2.5))
    assert [(x["bot"], x["verdetto"]) for x in e] == [("omega", "chiusa")]
    # posizione del bot sotto la tolleranza: nessuna voce
    assert EFB.effetto_sui_bot({"mike": [ordine("M3", "BACK", 0.04, 1.5)]}, [],
                               EFB.riga_copertura("lay", 20.0, 1.50)) == []


def test_effetto_sui_bot_e_il_verdetto_vero_dei_bot_sono_la_stessa_funzione(monkeypatch):
    """Nessuna copia dell'aritmetica: se si cambia ``verdetto_posizione``, cambiano
    insieme la previsione del worker e il verdetto dei bot."""
    from Betfair.stream import esiti_ordini_canale as EO

    chiamate: List[str] = []
    vera = EO.verdetto_posizione

    def spia(**kw: Any) -> Dict[str, Any]:
        chiamate.append("x")
        return vera(**kw)

    monkeypatch.setattr(EO, "verdetto_posizione", spia)
    EFB.effetto_sui_bot({"mike": [ordine("M1", "BACK", 10.0, 1.50)]}, [],
                        EFB.riga_copertura("lay", 6.0, 1.50))
    assert len(chiamate) == 2                         # prima e dopo la copertura


# ===========================================================================
# 8. CONTRATTI: le regole riusate sono quelle che esistono
# ===========================================================================
def test_contratti_con_le_regole_esistenti():
    from Betfair.stream import reconcile_worker as RW

    assert EFB.STRATEGIA_MANUALE_APP == wk.CUSTOMER_STRATEGY_REF
    assert EFB.TABELLE_BOT == RW._TABELLE_BOT
    assert set(RW._OUR_ORDER_REF_PREFIXES) <= set(EFB.prefissi_ref_bot())
    sql = (pathlib.Path(__file__).resolve().parents[3] / "migrations"
           / "live_orders_account_open_2026-09-30.sql").read_text(encoding="utf-8")
    assert "o.source IN ('runner', 'account')" in sql
    for t in EFB.TABELLE_BOT:
        assert f"FROM public.{t} t" in sql
    assert EFB.SOURCE_SPECCHIO_A_MANO == ("runner", "account")


def test_contratto_con_i_verdetti_dei_bot():
    """La tolleranza e la formula del "vivo" sono quelle dei tre verdetti: se un bot
    le cambia, questo test lo dice (e ``effetto_sui_bot`` va riallineata)."""
    from Betfair.mike import service as MS
    from Betfair.omega import omega_service as OS
    from Betfair.safe_strategy import bot_service as SS

    assert EFB.EPS_VERDETTO_BOT >= max(MS._CONTO_EPS, OS.CONTO_EPS, SS._CONTO_EPS)
    # 08/10 (W3a): la formula non e' piu' ricopiata in ogni bot: i tre verdetti e la
    # previsione del worker chiamano la STESSA funzione
    for f in (MS._verdetto_di_conto, OS._verdetto_di_conto, SS._verdetto_di_conto,
              EFB.effetto_sui_bot):
        src = inspect.getsource(f)
        assert "verdetto_posizione(" in src, f.__name__
        assert "vivo = (min(atteso" not in src, f.__name__
    from Betfair.stream import esiti_ordini_canale as EO

    assert EFB.vivo_nel_conto(10.0, 9.64) == EO.vivo_in_size(10.0, 9.64) == 9.64
    assert EFB.TABELLA_CODA == wk._TABLE


# ===========================================================================
# 9. I BOT DOPO LA COPERTURA: le funzioni VERE di Mike e di Omega
# ===========================================================================
def _righe_bot(ordini: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from Betfair.omega import omega_market as OM

    return [OM._riga_corrente(dict(o)) for o in ordini]


def _con_copertura(ordini: List[Dict[str, Any]], m: Mercato) -> List[Dict[str, Any]]:
    """Il conto DOPO: la copertura piazzata dal worker, abbinata al suo prezzo."""
    out = list(ordini)
    for i, (o, _kw) in enumerate(m.piazzati):
        out.append(ordine(f"H{i}", o.side, float(o.order_type.size),
                          float(o.order_type.price), csr="live", cor=f"9f1c2-{i}",
                          sel=int(o.selection_id), market=m.market_id))
    return out


def _verdetto_mike(righe: List[Dict[str, Any]], monkeypatch, abbinato: float = 10.0) -> tuple:
    from Betfair.mike import engine as ME
    from Betfair.mike import service as MS

    monkeypatch.setattr(MS, "_trade_row_for_leg", lambda db, eid, leg, cache=None: {
        "id": 1, "meta": {}, "status": "open", "bet_id": "M1", "mode": "live",
        "signal_key": leg.ref, "market_id": MKT, "selection_id": UNDER})
    leg = ME.Leg(role="under_entry", market=ME.MARKET_OU35, selection=ME.SEL_UNDER,
                 side="back", price=1.50, size=abbinato, matched=abbinato, avg_price=1.50,
                 ref="under_entry-0-1", status="open", placed_at=1_700_000_000.0)
    ctx = ME.MatchCtx(state="LIVE_COVERED", legs=[leg])
    ev = {"event_id": "E1", "markets": {ME.MARKET_OU35: {"market_id": MKT}}}
    extra = {"selections": {f"{ME.MARKET_OU35}|{ME.SEL_UNDER}": UNDER}}

    class Db:
        def log(self, *a, **k):
            pass
    chiuse, parziali, non_ritrovate = MS._verdetto_di_conto(
        ctx=ctx, ev=ev, extra=extra, db=Db(), eid="E1", cache=None,
        righe_di=lambda mid: righe if mid == MKT else None)
    return chiuse, parziali, non_ritrovate


MIKE_BACK = ordine("M1", "BACK", 10.0, 1.50, csr="mike", cor="mike-t1", sel=UNDER)


@pytest.mark.parametrize("lay_under", [1.50, 1.60])
def test_mike_resta_intera_quando_la_copertura_non_supera_la_puntata(lay_under, monkeypatch):
    """Mike BACK Under 10 @1,50; il sito BACK Under 5 @1,50. Prezzo invariato (lay
    1,50: copertura 5,00) o salito (1,60: 4,69): il netto di conto resta >= 10 e il
    verdetto VERO di Mike non dice ne' chiusa ne' ridotta. Il worker non annuncia
    effetti sui bot."""
    m = mercato_ou(lay_under=lay_under, back_under=lay_under - 0.01)
    prima = [MIKE_BACK, ordine("S1", "BACK", 5.0, 1.50, sel=UNDER)]
    r = esegui(Sb(), framework(m, Conto(prima)), riga_greenup(sel=UNDER))
    assert r["status"] == "done", r.get("error")
    assert len(m.piazzati) == 1 and "bot_toccati_nel_verdetto" not in r["result"]
    chiuse, parziali, non_rit = _verdetto_mike(_righe_bot(_con_copertura(prima, m)),
                                              monkeypatch)
    assert (chiuse, parziali, non_rit) == ([], [], [])


def test_mike_intera_quando_il_prezzo_e_sceso_green_up_dell_utente(monkeypatch):
    """Prezzo sceso (lay 1,40): la copertura del sito e' LAY 5,36 e il netto di conto
    IN SIZE scende a 9,64 < 10. 08/10 (W3a, reperto del coordinatore): il verdetto
    VERO di Mike e' in ESPOSIZIONE e giudica solo le gambe del bot contro gli ordini
    dell'utente: il green-up dell'utente del SUO back ha direzione ~0 -> Mike INTERA
    (prima «ridotta» 9,64, falso; e dal 08/10 una riduzione FERMA il bot). Il worker,
    con la STESSA funzione, non annuncia effetti."""
    m = mercato_ou(lay_under=1.40, back_under=1.39)
    prima = [MIKE_BACK, ordine("S1", "BACK", 5.0, 1.50, sel=UNDER)]
    r = esegui(Sb(), framework(m, Conto(prima)), riga_greenup(sel=UNDER))
    assert r["status"] == "done", r.get("error")
    assert piazzati(m) == [("LAY", 1.4, 5.36)]
    assert "bot_toccati_nel_verdetto" not in r["result"]
    chiuse, parziali, _nr = _verdetto_mike(_righe_bot(_con_copertura(prima, m)), monkeypatch)
    assert chiuse == [] and parziali == []


def test_mike_non_viene_dichiarata_chiusa_dal_green_up_dell_utente(monkeypatch):
    """Mike BACK Under 2 @1,50; il sito BACK Under 10 @5,0 (W 40, L -10). Lay 1,50:
    la copertura e' LAY 33,33. In SIZE il netto andrebbe a -21,33 («chiusa», falso);
    08/10 (W3a): in ESPOSIZIONE la direzione dell'utente va a 0 e Mike resta INTERA,
    quindi il worker NON rifiuta piu' una copertura che i bot accettano."""
    m = mercato_ou(lay_under=1.50, back_under=1.49)
    mike2 = ordine("M1", "BACK", 2.0, 1.50, csr="mike", cor="mike-t1", sel=UNDER)
    prima = [mike2, ordine("S1", "BACK", 10.0, 5.0, sel=UNDER)]
    r = esegui(Sb(), framework(m, Conto(prima)), riga_greenup(sel=UNDER))
    assert r["status"] == "done", r.get("error")
    assert piazzati(m) == [("LAY", 1.5, 33.33)]
    assert "bot_toccati_nel_verdetto" not in r["result"]
    chiuse, parziali, _n = _verdetto_mike(_righe_bot(_con_copertura(prima, m)), monkeypatch,
                                          abbinato=2.0)
    assert chiuse == [] and parziali == []


def test_il_worker_rifiuta_ancora_la_copertura_che_chiuderebbe_mike(monkeypatch):
    """La copertura che DAVVERO chiuderebbe Mike si rifiuta ancora: l'utente ha un
    LAY sull'OVER (l'altro esito del mercato a due esiti) e la sua posizione si copre
    sulla selezione di Mike (Under) con un LAY: per il verdetto di Mike, che guarda
    la sua selezione, quel LAY e' un ordine dell'utente CONTRO la sua posizione
    (direzione -30 contro +15): «chiusa dall'utente». Il worker RIFIUTA (nessun
    ordine), e il verdetto VERO di Mike con quella copertura lo conferma."""
    m = mercato_ou(lay_under=1.50, back_under=1.49)
    prima = [MIKE_BACK, ordine("S1", "LAY", 10.0, 3.0, sel=OVER)]
    r = esegui(Sb(), framework(m, Conto(prima)), riga_greenup(sel=UNDER))
    assert r["status"] == "error" and piazzati(m) == []
    assert "CHIUSA DALL'UTENTE" in r["error"] and "mike" in r["error"]
    ipotetica = prima + [ordine("H", "LAY", 20.0, 1.50, csr="live", sel=UNDER)]
    chiuse, _p, _n = _verdetto_mike(_righe_bot(ipotetica), monkeypatch)
    assert [c["verdetto"] for c in chiuse] == ["chiusa_dall_utente"]


class _DbOmega:
    """Le firme di ``omega_db`` che ``sorveglia_posizione_di_conto`` usa."""

    def __init__(self, trades: List[dict]) -> None:
        self.trades = [dict(t) for t in trades]
        self.attivita: List[tuple] = []

    def open_trades(self) -> List[dict]:
        return [t for t in self.trades if str(t.get("status")) == "open"]

    def update_trade(self, trade_id: int, **campi: Any) -> None:
        for t in self.trades:
            if int(t.get("id") or 0) == int(trade_id):
                t.update(campi)

    def log(self, kind: str, payload: Optional[dict] = None, **_kw: Any) -> None:
        self.attivita.append((kind, dict(payload or {})))

    def event_user_state(self, event_id: str) -> Optional[dict]:
        return None

    def set_event_user_state(self, event_id: str, stato: Optional[dict]) -> bool:
        return True


class _MercatoOmega:
    def __init__(self, righe: List[dict]) -> None:
        self.righe = righe

    def posizione_di_conto(self, market_id: str, selection_id: Optional[int] = None):
        return [r for r in self.righe if selection_id is None
                or int(r.get("selection_id") or -1) == int(selection_id)]


def _verdetto_omega(righe: List[Dict[str, Any]]) -> List[str]:
    from Betfair.omega import omega_config as OC
    from Betfair.omega import omega_engine as OE
    from Betfair.omega import omega_service as OS

    OS.svuota_le_cache()
    lay = {"id": 1, "event_id": "35760084", "market_id": MKT, "selection_id": UNDER,
           "side": "lay", "size": 5.26, "price": 3.0, "status": "open", "mode": "live",
           "origin": "auto", "bet_id": "O1", "liability": 10.52,
           "closes_trade_id": None, "meta": {}}
    assert OE.customer_ref_for(1)
    db = _DbOmega([lay])
    p = dict(OC.DEFAULTS)
    p["conto_every_s"] = 0.0
    OS.sorveglia_posizione_di_conto(params=p, market=_MercatoOmega(righe), db=db,
                                    now=datetime(2026, 10, 8, 20, 0, tzinfo=timezone.utc))
    OS.svuota_le_cache()
    return [str((pl or {}).get("verdetto") or k) for k, pl in db.attivita]


def _omega_lay() -> Dict[str, Any]:
    from Betfair.omega import omega_engine as OE

    return ordine("O1", "LAY", 5.26, 3.0, csr="omega", cor=OE.customer_ref_for(1),
                  sel=UNDER)


def test_omega_intera_dopo_la_copertura_del_sito_sul_suo_stesso_lato():
    """Omega LAY Under 5,26; il sito BACK Under 5 @3. La copertura (LAY 6,00 @2,5)
    va nel verso della posizione di Omega: il verdetto VERO di Omega resta muto."""
    m = mercato_ou(lay_under=2.5, back_under=2.48)
    prima = [_omega_lay(), ordine("S1", "BACK", 5.0, 3.0, sel=UNDER)]
    r = esegui(Sb(omega_trades=[{"id": 1, "bet_id": "O1", "mode": "live"}]),
               framework(m, Conto(prima)), riga_greenup(sel=UNDER))
    assert r["status"] == "done" and piazzati(m) == [("LAY", 2.5, 6.0)]
    assert "bot_toccati_nel_verdetto" not in r["result"]
    assert _verdetto_omega(_righe_bot(_con_copertura(prima, m))) == []


def test_omega_intera_la_previsione_del_worker_coincide_col_verdetto_vero():
    """Omega LAY Under 5,26; il sito LAY Under 5 @3 (W -10, L +5); miglior back 2,5:
    copertura BACK 6,00. In SIZE il netto passa da -10,26 a -4,26 («ridotta», falso);
    08/10 (W3a): in ESPOSIZIONE la direzione dell'utente (LAY 5 @3 + BACK 6 @2,5) va
    a 0 e Omega resta INTERA. Il worker, con la STESSA funzione, non annuncia
    effetti e il verdetto VERO di Omega e' muto."""
    m = mercato_ou(lay_under=2.52, back_under=2.5)
    prima = [_omega_lay(), ordine("S1", "LAY", 5.0, 3.0, sel=UNDER)]
    r = esegui(Sb(omega_trades=[{"id": 1, "bet_id": "O1", "mode": "live"}]),
               framework(m, Conto(prima)), riga_greenup(sel=UNDER))
    assert r["status"] == "done", r.get("error")
    assert piazzati(m) == [("BACK", 2.5, 6.0)]
    assert "bot_toccati_nel_verdetto" not in r["result"]
    assert _verdetto_omega(_righe_bot(_con_copertura(prima, m))) == []


def test_safe_stessa_aritmetica_del_verdetto():
    """Safe: la sua funzione VERA del verdetto sulle righe normalizzate dice quello
    che il worker prevede. 08/10 (W3a): il netto IN SIZE scende a 9,64 ma la
    direzione dell'utente (BACK 5 @1,50 + LAY 5,36 @1,40) va a 0: Safe INTERA, e
    il worker non annuncia effetti (prima «ridotta» 9,64, falso)."""
    from Betfair.safe_strategy import bot_service as SS

    m = mercato_ou(lay_under=1.40, back_under=1.39)
    safe = ordine("F1", "BACK", 10.0, 1.50, csr="omega", cor="safe-t4", sel=UNDER)
    prima = [safe, ordine("S1", "BACK", 5.0, 1.50, sel=UNDER)]
    r = esegui(Sb(safe_strategy_trades=[{"id": 4, "bet_id": "F1", "mode": "live"}]),
               framework(m, Conto(prima)), riga_greenup(sel=UNDER))
    assert r["status"] == "done", r.get("error")
    assert "bot_toccati_nel_verdetto" not in r["result"]
    righe = _righe_bot(_con_copertura(prima, m))
    mio = SS._netto_su_selezione(righe, MKT, UNDER, solo_refs={"safe-t4"})
    conto = SS._netto_su_selezione(righe, MKT, UNDER)
    assert (mio, conto) == (10.0, 9.64)               # la size dice «ridotta» ...
    v = SS._verdetto_di_conto(righe, MKT, UNDER, {"safe-t4"}, 10.0)
    assert (v["verdetto"], v["metro"]) == ("intera", "esposizione")   # ... il verdetto no
