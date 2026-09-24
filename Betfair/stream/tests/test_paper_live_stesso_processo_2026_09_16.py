"""F0 (16/09) — UN SOLO runner serve la coda di ENTRAMBE le modalita'.

Cosa certifica, riga per riga della coda REALE (schema
``migrations/betfair_live_order_queue.sql:33-66``: stesse chiavi, stessi tipi,
``mode IN ('paper','live')``):

  (a) paper e live accodati INSIEME: nessuna delle due righe muore e ciascuna e'
      eseguita dal client della SUA modalita';
  (b) processo NON in LIVE + riga 'live': riga in 'error' con motivo
      ``live_client_assente`` e NESSUNA chiamata al client reale;
  (c) riga 'paper' dentro un runner LIVE: mai il client reale (si asserisce sul
      DOPPIO del client reale, che resta senza esecuzioni);
  (d) il client PAPER di produzione e' registrabile accanto a quello reale nello
      STESSO framework (vincolo ``Clients.add_client``: username distinto).

I finti parlano come il vero: i client sono le CLASSI DI PRODUZIONE
(``flumine.clients.BetfairClient`` e ``runner.PaperCompanionClient``) dentro il
registro VERO (``flumine.clients.Clients``), e il Market doppio riproduce la regola
di flumine ``Market.transaction`` (``client is None -> clients.get_default()``):
se il worker dimenticasse il kwarg ``client=``, in un runner LIVE l'ordine
finirebbe sul client REALE — ed e' esattamente cio' che questi test vedono.
NESSUNA rete, NESSUN login, NESSUN ordine reale.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from flumine import BaseStrategy, clients

import Betfair.stream.live_order_worker as wk

_STRAT_PAPER = BaseStrategy(market_filter={}, name="live_trading_paper")
_STRAT_LIVE = BaseStrategy(market_filter={}, name="live_trading_live")


# ---------------------------------------------------------------------------
# Coda finta: chiavi e tipi della tabella VERA (betfair_live_order_queue.sql)
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.data = data


class _Query:
    def __init__(self, store: List[Dict[str, Any]]) -> None:
        self._store = store
        self._op: Optional[str] = None
        self._payload: Dict[str, Any] = {}
        self._eq: List[tuple] = []
        self._neq: List[tuple] = []
        self._in: List[tuple] = []
        self._order: Optional[str] = None
        self._limit: Optional[int] = None

    def select(self, *_a: Any) -> "_Query":
        self._op = "select"
        return self

    def update(self, payload: Dict[str, Any]) -> "_Query":
        self._op = "update"
        self._payload = dict(payload)
        return self

    def eq(self, k: str, v: Any) -> "_Query":
        self._eq.append((k, v))
        return self

    def neq(self, k: str, v: Any) -> "_Query":
        self._neq.append((k, v))
        return self

    def in_(self, k: str, vals: Any) -> "_Query":
        self._in.append((k, list(vals)))
        return self

    def gte(self, *_a: Any) -> "_Query":
        return self

    def order(self, k: str) -> "_Query":
        self._order = k
        return self

    def limit(self, n: int) -> "_Query":
        self._limit = n
        return self

    def _match(self, row: Dict[str, Any]) -> bool:
        return (
            all(row.get(k) == v for k, v in self._eq)
            and all(row.get(k) != v for k, v in self._neq)
            and all(row.get(k) in vals for k, vals in self._in)
        )

    def execute(self) -> _Resp:
        rows = [r for r in self._store if self._match(r)]
        if self._order:
            rows.sort(key=lambda r: r.get(self._order))
        if self._op == "select":
            if self._limit is not None:
                rows = rows[: self._limit]
            return _Resp([dict(r) for r in rows])
        for r in rows:
            r.update(self._payload)
        return _Resp([dict(r) for r in rows])


class _Sb:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self.rows = rows

    def table(self, _name: str) -> _Query:
        return _Query(self.rows)


def _riga(rid: int, mode: str, **kw: Any) -> Dict[str, Any]:
    """Riga della coda con le CHIAVI E I TIPI della tabella reale.

    ``betfair_live_order_queue.sql:33-66``: id BIGSERIAL, client_ref TEXT UNIQUE,
    action/mode/status TEXT con CHECK, handicap NUMERIC NOT NULL DEFAULT 0,
    params JSONB, result JSONB, error TEXT, processed_at TIMESTAMPTZ.
    """
    assert mode in ("paper", "live")  # CHECK (mode IN ('paper','live'))
    riga = {
        "id": rid,
        "client_ref": f"cert-f0-{rid}",
        "action": "place",
        "mode": mode,
        "market_id": "1.1",
        "selection_id": 47999,
        "handicap": 0,
        "side": "back",
        "order_type": "LIMIT",
        "price": 3.0,
        "size": 5.0,
        "liability": None,
        "persistence": "LAPSE",
        "time_in_force": None,
        "min_fill_size": None,
        "bet_id": None,
        "new_price": None,
        "size_reduction": None,
        "params": None,
        "status": "pending",
        "result": None,
        "error": None,
        "requested_at": "2026-09-16T10:00:00+00:00",
        "processed_at": None,
    }
    riga.update(kw)
    return riga


def _by_id(sb: _Sb, rid: int) -> Dict[str, Any]:
    return next(r for r in sb.rows if r["id"] == rid)


# ---------------------------------------------------------------------------
# Client VERI con una spia delle esecuzioni + Market doppio fedele a flumine
# ---------------------------------------------------------------------------
class _ClientSpia(clients.BetfairClient):
    """Client di produzione (stessa classe del runner) con l'elenco degli ordini
    che gli sono stati consegnati: se la lista non e' vuota, quel client ha
    eseguito qualcosa. ``betting_client=None`` -> username generato, quindi due
    istanze convivono nel registro VERO di flumine."""

    def __init__(self, *a: Any, **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.eseguiti: List[Any] = []


class _Blotter:
    def __init__(self) -> None:
        self._by_bet: Dict[str, Any] = {}
        self._by_id: Dict[str, Any] = {}

    def get_order_bet_id(self, bet_id: str) -> Optional[Any]:
        return self._by_bet.get(bet_id)

    def __getitem__(self, oid: str) -> Any:
        return self._by_id[oid]

    def __iter__(self):
        return iter(list(self._by_id.values()))


class _Market:
    """Market doppio che riproduce la regola di flumine ``Market.transaction``:
    senza ``client=`` esplicito si usa ``flumine.clients.get_default()`` (il PRIMO
    client aggiunto). E' il punto in cui un routing rotto si vede subito."""

    def __init__(self, market_id: str, registro: Any) -> None:
        self.market_id = market_id
        self.event_id = "E1"
        self.blotter = _Blotter()
        self.calls: List[tuple] = []
        self._registro = registro

    def place_order(self, order: Any, customer_strategy_ref: Any = None,
                    client: Any = None, **kw: Any) -> bool:
        if client is None:
            client = self._registro.get_default()
        self.calls.append((order, customer_strategy_ref, client))
        client.eseguiti.append(order)
        return True

    def cancel_order(self, order: Any, size_reduction: Optional[float] = None) -> bool:
        self.calls.append(("cancel", order, size_reduction))
        return True


class _Markets:
    def __init__(self, markets: Dict[str, _Market]) -> None:
        self.markets = markets

    def __iter__(self):
        return iter(list(self.markets.values()))


class _Framework:
    """Framework doppio con il registro client VERO di flumine."""

    def __init__(self, markets: Dict[str, _Market], registro: Any) -> None:
        self.markets = _Markets(markets)
        self.clients = registro


def _scenario(proc_mode: str, *, con_paper: bool = True, con_reale: bool = True):
    """Registro client VERO + market doppio. Ritorna (framework, market, paper, reale).

    ``reale`` esiste SEMPRE come oggetto (serve come DOPPIO su cui asserire "non e'
    stato chiamato") ma viene REGISTRATO nel framework solo se ``con_reale``:
    in un runner PAPER il client reale non esiste davvero nel processo.
    """
    registro = clients.Clients()
    reale = _ClientSpia(paper_trade=False, order_stream=False)
    paper = _ClientSpia(paper_trade=True, order_stream=False)
    if con_reale:
        registro.add_client(reale)     # primo aggiunto = default (come in LIVE)
    if con_paper:
        registro.add_client(paper)
    market = _Market("1.1", registro)
    return _Framework({"1.1": market}, registro), market, paper, reale


@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    monkeypatch.setattr(wk, "_kill_switch", lambda: False)
    monkeypatch.setattr(wk, "_db_kill_switch", lambda: False)
    monkeypatch.setattr(wk, "_jurisdiction", lambda: "it")
    monkeypatch.setattr(wk, "_batch", lambda: 5)
    monkeypatch.setattr(wk, "_max_stake", lambda: None)
    monkeypatch.setattr(wk, "_refresh_settings", lambda *_a: None)
    monkeypatch.setattr(wk, "_journal_done", lambda *_a: None)
    monkeypatch.setattr(wk, "_process_local_requests", lambda *_a: 0)


# ===========================================================================
# (a) paper e live accodati INSIEME: nessuno muore, ognuno al client giusto
# ===========================================================================
def test_paper_e_live_insieme_nessuna_riga_muore_e_ognuna_va_al_suo_client(monkeypatch):
    monkeypatch.setattr(wk, "_live_order_mode", lambda: "LIVE")
    monkeypatch.setattr(wk, "_modo_processo", lambda: "LIVE")
    sb = _Sb([_riga(1, "paper"), _riga(2, "live")])
    fl, market, paper, reale = _scenario("LIVE")

    n = wk._process_once(sb, fl, strategy={"paper": _STRAT_PAPER, "live": _STRAT_LIVE})

    assert n == 2
    assert _by_id(sb, 1)["status"] == "done"   # prima di F0: 'error' (cross-mode)
    assert _by_id(sb, 2)["status"] == "done"
    assert _by_id(sb, 1)["error"] is None and _by_id(sb, 2)["error"] is None
    # un ordine a testa, ciascuno sul client della SUA modalita'
    assert len(paper.eseguiti) == 1 and len(reale.eseguiti) == 1
    assert len(market.calls) == 2
    ordine_paper, _, client_paper = market.calls[0]
    ordine_live, _, client_live = market.calls[1]
    assert client_paper is paper and client_live is reale
    # e sotto la strategy della propria modalita' (blotter separato per modalita')
    assert ordine_paper.trade.strategy is _STRAT_PAPER
    assert ordine_live.trade.strategy is _STRAT_LIVE
    # l'esito scritto sulla riga porta la modalita' DELLA RIGA
    assert _by_id(sb, 1)["result"]["mode"] == "paper"
    assert _by_id(sb, 2)["result"]["mode"] == "live"


# ===========================================================================
# (b) processo NON in LIVE + riga live -> error, zero chiamate al client reale
# ===========================================================================
@pytest.mark.parametrize("proc_mode", ["PAPER", "OFF"])
def test_riga_live_in_processo_non_live_va_in_error_senza_toccare_il_reale(
    monkeypatch, proc_mode
):
    monkeypatch.setattr(wk, "_live_order_mode", lambda: proc_mode)
    monkeypatch.setattr(wk, "_modo_processo", lambda: proc_mode)
    sb = _Sb([_riga(7, "live")])
    fl, market, paper, reale = _scenario(proc_mode, con_reale=False)

    wk._process_once(sb, fl, strategy={"paper": _STRAT_PAPER})

    riga = _by_id(sb, 7)
    if proc_mode == "OFF":
        # worker inerte: la riga non viene nemmeno letta (nessun ordine, mai)
        assert riga["status"] == "pending"
    else:
        assert riga["status"] == "error"
        assert wk.ERR_LIVE_CLIENT_ASSENTE in riga["error"]
    assert reale.eseguiti == []      # il DOPPIO del client reale: mai chiamato
    assert paper.eseguiti == []      # e nemmeno un fill simulato spacciato per live
    assert market.calls == []


# ===========================================================================
# (c) riga paper: mai il client reale, nemmeno dentro un runner LIVE
# ===========================================================================
def test_riga_paper_non_raggiunge_mai_il_client_reale(monkeypatch):
    monkeypatch.setattr(wk, "_live_order_mode", lambda: "LIVE")
    monkeypatch.setattr(wk, "_modo_processo", lambda: "LIVE")
    sb = _Sb([_riga(3, "paper")])
    fl, market, paper, reale = _scenario("LIVE")
    # il client reale e' il DEFAULT del framework: se il worker non passasse
    # client=, l'ordine paper finirebbe qui (ed e' cio' che il test vieta).
    assert fl.clients.get_default() is reale

    wk._process_once(sb, fl, strategy={"paper": _STRAT_PAPER, "live": _STRAT_LIVE})

    assert _by_id(sb, 3)["status"] == "done"
    assert reale.eseguiti == []
    assert len(paper.eseguiti) == 1
    assert market.calls[0][2] is paper


def test_riga_paper_senza_client_simulato_non_si_esegue(monkeypatch):
    """Runner LIVE a cui manca il client simulato: la riga paper NON ripiega sul
    default (che li' e' il client REALE) — va in 'error' col motivo."""
    monkeypatch.setattr(wk, "_live_order_mode", lambda: "LIVE")
    monkeypatch.setattr(wk, "_modo_processo", lambda: "LIVE")
    sb = _Sb([_riga(4, "paper")])
    fl, market, paper, reale = _scenario("LIVE", con_paper=False)

    wk._process_once(sb, fl, strategy={"paper": _STRAT_PAPER, "live": _STRAT_LIVE})

    riga = _by_id(sb, 4)
    assert riga["status"] == "error"
    assert wk.ERR_PAPER_CLIENT_ASSENTE in riga["error"]
    assert reale.eseguiti == [] and market.calls == []


# ===========================================================================
# Canale locale: stessa regola (decide il mode della RICHIESTA)
# ===========================================================================
def test_client_for_mode_e_servable_modes_sono_coerenti(monkeypatch):
    monkeypatch.setattr(wk, "_live_order_mode", lambda: "PAPER")
    monkeypatch.setattr(wk, "_modo_processo", lambda: "PAPER")
    assert wk._servable_modes() == ("paper",)
    monkeypatch.setattr(wk, "_live_order_mode", lambda: "LIVE")
    monkeypatch.setattr(wk, "_modo_processo", lambda: "LIVE")
    assert wk._servable_modes() == ("live", "paper")
    monkeypatch.setattr(wk, "_live_order_mode", lambda: "OFF")
    monkeypatch.setattr(wk, "_modo_processo", lambda: "OFF")
    assert wk._servable_modes() == ()


def test_fail_cross_mode_non_uccide_piu_niente():
    """La strage delle righe dell'altra modalita' e' stata disarmata: la funzione
    resta come nota storica ma non tocca il DB e ritorna 0."""
    sb = _Sb([_riga(9, "live")])
    assert wk._fail_cross_mode(sb, "paper") == 0
    assert _by_id(sb, 9)["status"] == "pending"


# ===========================================================================
# (d) il client PAPER di produzione convive col reale nello stesso framework
# ===========================================================================
def test_companion_paper_registrabile_accanto_al_client_reale():
    """``Clients.add_client`` rifiuta due client con lo STESSO username sullo stesso
    venue: condividendo la sessione (stesso account) il companion deve distinguersi.
    Qui si usa la classe DI PRODUZIONE, con un betting_client dalla forma vera."""
    from flumine import config as flumine_config

    from Betfair.stream import runner as R

    api = SimpleNamespace(username="conto.betfair", lightweight=False,
                          session_timeout=1200)
    latenza_prima = flumine_config.place_latency
    try:
        reale = clients.BetfairClient(api, order_stream=True, paper_trade=False)
        companion = R.build_paper_companion_client(api)
        registro = clients.Clients()
        registro.add_client(reale)
        registro.add_client(companion)   # niente ClientError: username distinto
    finally:
        flumine_config.place_latency = latenza_prima

    assert companion.paper_trade is True and reale.paper_trade is False
    assert companion.username != reale.username
    assert companion.username.endswith("#paper")
    assert registro.get_default() is reale      # il default resta il reale
    assert registro.simulated is True           # -> flumine aggiunge SimulatedMiddleware
    # la sessione e' UNA e la possiede il client reale: il companion non fa
    # login/logout/keepAlive/saldo (mai chiamate Betfair doppie sullo stesso conto)
    assert companion.login() is None and companion.logout() is None
    assert companion.keep_alive() is True
    assert companion.update_account_details() is None
    # e il worker lo riconosce come client della modalita' 'paper'
    assert wk._is_paper_client(companion) is True
    assert wk._is_paper_client(reale) is False


def test_heartbeat_dichiara_le_modalita_servite(monkeypatch):
    """Il battito non dice piu' solo "in che modalita' giro" ma "quali modalita'
    servo": un runner LIVE serve anche le righe paper."""
    from Betfair.stream import runner as R

    monkeypatch.setattr(R, "live_order_mode", lambda: "LIVE")
    assert R.heartbeat_mode() == "LIVE+PAPER"
    monkeypatch.setattr(R, "live_order_mode", lambda: "PAPER")
    assert R.heartbeat_mode() == "PAPER"
    monkeypatch.setattr(R, "live_order_mode", lambda: "OFF")
    assert R.heartbeat_mode() == "OFF"
