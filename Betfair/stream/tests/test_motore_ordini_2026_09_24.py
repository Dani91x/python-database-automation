"""24/09 - MOTORE ORDINI del runner (F1 diario, F2 svuotamento a evento, F3 protocollo).

Cosa certifica (brief del coordinatore, protocollo «comando ordine»):
  * protocollo completo su ``/comando/<attore>``: ack, rifiuto con motivo per OGNI
    causa (token, attore, ref, parametri, eta', aggancio, mode, guardia d'avvio,
    kill-switch env e DB, settings stantie, diario), dedup per ref (anche dopo il
    riavvio, dal diario), ``seq`` per attore, ``da_seq`` con memoria di 500;
  * DIARIO write-ahead: la riga ``ordine`` (con il customerOrderRef VERO di
    flumine) e' su disco PRIMA di ``market.place_order``;
  * ZERO IO DB nel percorso dell'ordine: ogni chiamata al DB avviene sul thread
    dello SCRITTORE asincrono, e al momento del place il DB non e' stato toccato;
  * latenza logica comando -> place < 20 ms col motore svegliato a evento
    (prima: il sonno di 1 s del BackgroundWorker);
  * ripresa all'avvio: comandi ``inviato`` senza esito riletti da Betfair
    (``listCurrentOrders`` con le chiavi VERE della risposta lightweight);
  * parita' del ``/order`` di sempre servito dal motore.

Finti: canale = ``LocalChannel`` VERO (solo l'invio sul socket e' registrato),
client = classi VERE di flumine (``clients.BetfairClient``) nel registro VERO
``clients.Clients``, strategie ``BaseStrategy`` vere (quindi ``customer_order_ref``
= name_hash + sep + uuid come in produzione), Market doppio fedele alla regola
``Market.transaction`` di flumine, righe della coda con le chiavi della tabella
vera, risposta di ``listCurrentOrders`` con le chiavi camelCase di Betfair.
NESSUNA rete, NESSUN login, NESSUN ordine reale, DB mai toccato.
"""
from __future__ import annotations

import json
import os
import threading
import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from flumine import BaseStrategy, clients

from Betfair.stream import db as DB
from Betfair.stream import live_order_worker as LOW
from Betfair.stream import local_channel as LC
from Betfair.stream import motore_ordini as MO

_STRAT_PAPER = BaseStrategy(market_filter={}, name="motore_test_paper")
_STRAT_LIVE = BaseStrategy(market_filter={}, name="motore_test_live")
TOKEN = "tok-motore-24-09-" + "0123456789abcdef" * 2   # >= 32 caratteri (C1)


# ---------------------------------------------------------------------------
# DB finto: registra OGNI chiamata con il thread che la fa
# ---------------------------------------------------------------------------
class _Q:
    def __init__(self, spia: "_SbSpia", tabella: str) -> None:
        self._spia = spia
        self._tab = tabella
        self._op = "?"
        self._payload: Any = None

    def _passo(self, op: str, payload: Any = None) -> "_Q":
        if op in ("select", "insert", "update", "upsert", "delete"):
            self._op = op
            self._payload = payload
        return self

    def select(self, *a: Any) -> "_Q":
        return self._passo("select")

    def insert(self, p: Any) -> "_Q":
        return self._passo("insert", p)

    def update(self, p: Any) -> "_Q":
        return self._passo("update", p)

    def upsert(self, p: Any, **_k: Any) -> "_Q":
        return self._passo("upsert", p)

    def eq(self, *_a: Any) -> "_Q":
        return self

    def limit(self, *_a: Any) -> "_Q":
        return self

    def order(self, *_a: Any) -> "_Q":
        return self

    def execute(self) -> Any:
        self._spia.chiamate.append((threading.get_ident(), self._tab, self._op, self._payload))
        if self._op == "insert" and self._tab == "betfair_live_order_requests":
            return SimpleNamespace(data=[{"id": 777}])
        return SimpleNamespace(data=[])


class _SbSpia:
    def __init__(self) -> None:
        self.chiamate: List[tuple] = []

    def table(self, nome: str) -> _Q:
        return _Q(self, nome)

    def rpc(self, nome: str, _p: Any = None) -> _Q:
        return _Q(self, f"rpc:{nome}")


# ---------------------------------------------------------------------------
# flumine finto fedele (stesso schema di test_paper_live_stesso_processo)
# ---------------------------------------------------------------------------
class _ClientSpia(clients.BetfairClient):
    def __init__(self, *a: Any, **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.eseguiti: List[Any] = []


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
    def __init__(self, market_id: str, registro: Any) -> None:
        self.market_id = market_id
        self.event_id = "E1"
        self.blotter = _Blotter()
        self.calls: List[tuple] = []
        self._registro = registro
        self.su_place: Any = None  # sonda chiamata DENTRO place_order

    def place_order(self, order: Any, customer_strategy_ref: Any = None,
                    client: Any = None, **_k: Any) -> bool:
        if client is None:
            client = self._registro.get_default()
        if self.su_place is not None:
            self.su_place(order)
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
    def __init__(self, markets: Dict[str, _Market], registro: Any) -> None:
        self.markets = _Markets(markets)
        self.clients = registro


def _scenario(con_reale: bool = True, con_paper: bool = True):
    registro = clients.Clients()
    reale = _ClientSpia(paper_trade=False, order_stream=False)
    paper = _ClientSpia(paper_trade=True, order_stream=False)
    if con_reale:
        registro.add_client(reale)
    if con_paper:
        registro.add_client(paper)
    market = _Market("1.234", registro)
    return _Framework({"1.234": market}, registro), market, paper, reale


# ---------------------------------------------------------------------------
# canale VERO, invio sul socket registrato
# ---------------------------------------------------------------------------
class _FintoWs:
    """Socket finto: hashable per identita' come la connessione vera."""

    def __init__(self, nome: str) -> None:
        self.nome = nome


class _Canale(LC.LocalChannel):
    def __init__(self) -> None:
        super().__init__(59997, "calcio")
        self.inviati: List[tuple] = []     # (ws, payload)
        self.risposte: List[tuple] = []    # /order: (msg_id, ok, data, error)
        self.ws_attori: Dict[Any, str] = {}

    def invia(self, ws: Any, payload: Dict[str, Any]) -> None:
        self.inviati.append((ws, json.loads(json.dumps(payload, default=str))))

    def invia_attore(self, attore: str, payload: Dict[str, Any]) -> None:
        for ws, att in self.ws_attori.items():
            if att == attore:
                self.invia(ws, payload)

    def respond(self, req: Any, ok: bool, data: Any = None, error: Optional[str] = None) -> None:
        self.risposte.append((req.msg_id, ok, data, error))

    def _send(self, ws: Any, payload: Dict[str, Any]) -> None:
        self.invia(ws, payload)

    def collega(self, attore: str, token: Optional[str] = TOKEN) -> Any:
        ws = _FintoWs(f"ws-{attore}-{len(self.ws_attori)}")
        # stessa verifica del canale vero (UNICO token: ``self._token``)
        self._comando_ws[ws] = (attore, self._token_valido(token))
        self.ws_attori[ws] = attore
        return ws

    def per_ws(self, ws: Any, t: Optional[str] = None) -> List[Dict[str, Any]]:
        return [p for w, p in self.inviati if w is ws and (t is None or p.get("t") == t)]


# ---------------------------------------------------------------------------
# fixture: ambiente del motore (LIVE runner con client reale + paper)
# ---------------------------------------------------------------------------
@pytest.fixture()
def amb(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_CHANNEL_TOKEN", TOKEN)
    # tetto dell'ambiente e modo effettivo dalla UI (master 24/09): entrambi LIVE
    monkeypatch.setattr(LOW, "_modo_processo", lambda: "LIVE")
    monkeypatch.setattr(LOW, "_live_order_mode", lambda: "LIVE")
    monkeypatch.setattr(LOW, "_kill_switch", lambda: False)
    monkeypatch.setattr(LOW, "_jurisdiction", lambda: "it")
    monkeypatch.setattr(LOW, "_max_stake", lambda: None)
    monkeypatch.setattr(LOW, "_SETTINGS", {"kill_switch": False})
    monkeypatch.setattr(LOW, "_SETTINGS_TS", time.monotonic())
    monkeypatch.setattr(LOW, "_LOCAL_SEEN", {})
    import db_client
    spia_diretta = _SbSpia()
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: spia_diretta)
    ch = _Canale()
    monkeypatch.setattr(LC, "get_channel", lambda: ch)
    fl, market, paper, reale = _scenario()
    sb = _SbSpia()
    scrittore = MO.ScrittoreAsincrono(sb_factory=lambda: sb, dormi=lambda _s: None)
    scrittore.avvia()
    guardia = {"armata": False}
    diario = MO.Diario(str(tmp_path / "_diario_ordini"))
    motore = MO.MotoreOrdini("calcio", canale=ch, diario=diario, scrittore=scrittore,
                             guardia_armata=lambda: guardia["armata"])
    motore.aggancia(fl, {"live": _STRAT_LIVE, "paper": _STRAT_PAPER})
    # sveglia registrata SENZA thread: i test sincroni chiamano ``drena`` a mano
    ch.set_su_comando(motore.sveglia)
    yield SimpleNamespace(ch=ch, fl=fl, market=market, paper=paper, reale=reale, sb=sb,
                          scrittore=scrittore, motore=motore, guardia=guardia,
                          diario=diario, tmp=tmp_path, spia_diretta=spia_diretta)
    scrittore.ferma()
    diario.chiudi()
    DB.imposta_scrittore(None)
    for cb in list(DB._OSSERVATORI_ORDINI):
        DB.rimuovi_osservatore_ordini(cb)
    LOW.imposta_drenaggio_esterno(False)


def _cmd(attore: str = "safe", n: int = 1, **kw: Any) -> Dict[str, Any]:
    d = {"ref": f"{attore}-t{n}", "attore": attore, "azione": "place", "mode": "paper",
         "market_id": "1.234", "selection_id": 47972, "side": "BACK", "price": 2.5,
         "size": 3.0, "persistence": "LAPSE", "strategy_ref": attore,
         "creato_ms": int(time.time() * 1000), "max_eta_ms": 3000,
         "origine": {"tabella": "safe_trades", "id": n}}
    d.update(kw)
    return d


def _manda(a: Any, ws: Any, d: Dict[str, Any], t: str = "comando") -> None:
    a.ch._on_comando(ws, json.dumps({"t": t, "d": d}))
    a.motore.drena()


def _ack(a: Any, ws: Any) -> Dict[str, Any]:
    acks = a.ch.per_ws(ws, "ack")
    assert acks, "nessun ack ricevuto"
    return acks[-1]["d"]


# ===========================================================================
# protocollo: ack, esecuzione, strategy ref dell'attore, evento con le chiavi vere
# ===========================================================================
def test_comando_place_ack_accettato_eseguito_col_client_della_modalita(amb):
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd())
    ack = _ack(amb, ws)
    assert ack["accettato"] is True and ack["motivo"] is None
    assert ack["ref"] == "safe-t1" and isinstance(ack["seq"], int)
    assert set(ack) == {"ref", "seq", "accettato", "motivo", "ricevuto_ms"}
    # un solo place, sul client PAPER (runner LIVE: mai il reale da paper)
    assert len(amb.market.calls) == 1
    order, strategy_ref, client = amb.market.calls[0]
    assert client is amb.paper and amb.reale.eseguiti == []
    assert strategy_ref == "safe"          # l'attore, non "live"
    assert order.trade.strategy is _STRAT_PAPER
    # evento order: chiavi dello specchio + ref/seq/fase/esito_ms, seq dopo l'ack
    ev = amb.ch.per_ws(ws, "order")
    assert len(ev) == 1
    d = ev[0]["d"]
    assert set(MO.CHIAVI_SPECCHIO) <= set(d)
    assert d["ref"] == "safe-t1" and d["fase"] == "inviato" and d["seq"] > ack["seq"]
    assert d["client_order_ref"].startswith("awlq") and d["mode"] == "paper"
    assert d["side"] == "back" and d["price"] == 2.5 and d["size"] == 3.0


def _mai_eseguito(a: Any) -> None:
    assert a.market.calls == []
    assert a.paper.eseguiti == [] and a.reale.eseguiti == []


@pytest.mark.parametrize("modifica,codice", [
    ({"side": "back"}, MO.M_PARAM),
    ({"price": float("nan")}, MO.M_PARAM),
    ({"price": 1.0}, MO.M_PARAM),
    ({"size": True}, MO.M_PARAM),
    ({"size": -1.0}, MO.M_PARAM),
    ({"azione": "dutch"}, MO.M_PARAM),
    ({"azione": "place_submin"}, MO.M_PARAM),
    ({"mode": "demo"}, MO.M_PARAM),
    ({"strategy_ref": "omega"}, MO.M_PARAM),
    ({"attore": "omega"}, MO.M_PARAM),
    ({"persistence": "MARKET_ON_CLOSE"}, MO.M_PARAM),
    ({"creato_ms": None}, MO.M_PARAM),
    ({"selection_id": "47972"}, MO.M_PARAM),
    ({"market_id": ""}, MO.M_PARAM),
])
def test_parametri_invalidi_rifiutati_con_motivo(amb, modifica, codice):
    ws = amb.ch.collega("safe")
    d = _cmd()
    d.update(modifica)          # ref resta "safe-t1": e' il CONTENUTO a essere invalido
    _manda(amb, ws, d)
    ack = _ack(amb, ws)
    assert ack["accettato"] is False and ack["motivo"].startswith(codice)
    assert isinstance(ack["seq"], int)       # rifiuto registrato: seq e dedup
    _mai_eseguito(amb)


def test_token_mancante_o_errato_rifiutato_senza_seq(amb):
    for tok in (None, "sbagliato"):
        ws = amb.ch.collega("safe", token=tok)
        _manda(amb, ws, _cmd(n=5))
        ack = _ack(amb, ws)
        assert ack["accettato"] is False and ack["motivo"].startswith(MO.M_TOKEN)
        assert ack["seq"] is None
    _mai_eseguito(amb)
    # un rifiuto per token non "prenota" il ref: col token giusto passa
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd(n=5))
    assert _ack(amb, ws)["accettato"] is True


def test_token_non_configurato_nessun_comando(amb, monkeypatch):
    # runner fuori dall'app (C1): nessun token nell'env -> token CASUALE che
    # nessuno conosce; ne' un token a caso ne' quello "vecchio" passano
    monkeypatch.delenv("LOCAL_CHANNEL_TOKEN", raising=False)
    ch = _Canale()
    amb.motore.canale = ch
    ch.set_su_comando(amb.motore.sveglia)
    for tok in ("qualunque", TOKEN, None):
        ws = ch.collega("safe", token=tok)
        ch._on_comando(ws, json.dumps({"t": "comando", "d": _cmd()}))
        amb.motore.drena()
        assert ch.per_ws(ws, "ack")[-1]["d"]["motivo"].startswith(MO.M_TOKEN)
    _mai_eseguito(amb)


def test_attore_non_ammesso_e_ref_malformato(amb):
    ws = amb.ch.collega("pirata")
    _manda(amb, ws, _cmd(attore="pirata"))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_ATTORE)
    ws2 = amb.ch.collega("safe")
    for ref in ("omega-t1", "safe-", "safe-" + "x" * 40, None):
        _manda(amb, ws2, _cmd(ref=ref))
        ack = _ack(amb, ws2)
        assert ack["accettato"] is False and ack["motivo"].startswith(MO.M_PARAM)
        assert ack["seq"] is None
    _mai_eseguito(amb)


def test_comando_troppo_vecchio_o_dal_futuro(amb):
    ws = amb.ch.collega("mike")
    ora = int(time.time() * 1000)
    _manda(amb, ws, _cmd("mike", 1, creato_ms=ora - 3500))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_ETA)
    _manda(amb, ws, _cmd("mike", 2, creato_ms=ora - 900, max_eta_ms=500))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_ETA)
    _manda(amb, ws, _cmd("mike", 3, creato_ms=ora + 5000))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_ETA)
    _mai_eseguito(amb)
    _manda(amb, ws, _cmd("mike", 4, creato_ms=ora - 900, max_eta_ms=5000))
    assert _ack(amb, ws)["accettato"] is True


def test_runner_non_agganciato_rifiuta_non_accoda(amb):
    amb.motore.sgancia()
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd())
    assert _ack(amb, ws)["motivo"].startswith(MO.M_AGGANCIO)
    # riagganciato, lo STESSO ref resta rifiutato (dedup) e nulla parte da solo
    amb.motore.aggancia(amb.fl, {"live": _STRAT_LIVE, "paper": _STRAT_PAPER})
    amb.motore.drena()
    _manda(amb, ws, _cmd())
    ack = _ack(amb, ws)
    assert ack["accettato"] is False and ack["motivo"] == MO.MOTIVO_REF_GIA_VISTO
    _mai_eseguito(amb)


def test_live_su_runner_paper_e_paper_senza_client_simulato(amb, monkeypatch):
    ws = amb.ch.collega("safe")
    monkeypatch.setattr(LOW, "_modo_processo", lambda: "PAPER")
    monkeypatch.setattr(LOW, "_live_order_mode", lambda: "PAPER")
    _manda(amb, ws, _cmd(n=1, mode="live"))
    ack = _ack(amb, ws)
    assert ack["accettato"] is False and ack["motivo"].startswith(MO.M_MODE)
    monkeypatch.setattr(LOW, "_modo_processo", lambda: "LIVE")
    monkeypatch.setattr(LOW, "_live_order_mode", lambda: "LIVE")
    fl, market, _p, reale = _scenario(con_paper=False)
    amb.motore.aggancia(fl, {"live": _STRAT_LIVE, "paper": _STRAT_PAPER})
    _manda(amb, ws, _cmd(n=2, mode="paper"))
    ack = _ack(amb, ws)
    assert ack["accettato"] is False and "paper_client_assente" in ack["motivo"]
    assert market.calls == [] and reale.eseguiti == []
    _mai_eseguito(amb)


def test_modo_effettivo_dalla_ui_blocca_le_aperture_non_le_chiusure(amb, monkeypatch):
    """Fusione con master (24/09): tetto .env LIVE ma scelta della Control Room
    PAPER -> apertura live rifiutata col motivo di ``_blocco_apertura_modo``,
    PRIMA del kill-switch; cancel e chiusura verificata passano."""
    monkeypatch.setattr(LOW, "_live_order_mode", lambda: "PAPER")
    ws = amb.ch.collega("mike")
    _manda(amb, ws, _cmd("mike", 1, mode="live"))
    ack = _ack(amb, ws)
    assert ack["accettato"] is False and ack["motivo"].startswith(MO.M_MODE)
    assert "RIFIUTATA" in ack["motivo"]
    # paper resta servito (modo effettivo PAPER)
    _manda(amb, ws, _cmd("mike", 2, mode="paper"))
    assert _ack(amb, ws)["accettato"] is True
    assert [c[2] for c in amb.market.calls] == [amb.paper]
    # riduzione DICHIARATA ma non verificata (posizione piatta): resta un'apertura
    _manda(amb, ws, _cmd("mike", 4, mode="live", side="LAY", reduces_liability=True))
    ack = _ack(amb, ws)
    assert ack["accettato"] is False and ack["motivo"].startswith(MO.M_MODE)
    assert len(amb.market.calls) == 1
    # chiusura live verificata: passa (le serve il modo di processo)
    monkeypatch.setattr(LOW, "_read_matched_exposures", lambda *a: (4.5, -3.0))
    _manda(amb, ws, _cmd("mike", 5, mode="live", side="LAY", price=2.0,
                         reduces_liability=True))
    assert _ack(amb, ws)["accettato"] is True
    assert amb.market.calls[-1][2] is amb.reale


def test_live_col_runner_live_va_al_client_reale(amb):
    ws = amb.ch.collega("mike")
    _manda(amb, ws, _cmd("mike", 1, mode="live"))
    assert _ack(amb, ws)["accettato"] is True
    order, sref, client = amb.market.calls[0]
    assert client is amb.reale and sref == "mike" and order.trade.strategy is _STRAT_LIVE


def test_guardia_avvio_armata_passa_solo_cancel(amb):
    amb.guardia["armata"] = True
    ws = amb.ch.collega("desktop")
    _manda(amb, ws, _cmd("desktop", 1))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_GUARDIA)
    _manda(amb, ws, _cmd("desktop", 2, azione="greenup"))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_GUARDIA)
    _manda(amb, ws, _cmd("desktop", 3, azione="cashout_event"))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_GUARDIA)
    assert amb.market.calls == []
    # cancel: passa (riduce l'esposizione), percorso vero del worker
    ordine = SimpleNamespace(bet_id="B-9", market_id="1.234", client=amb.paper)
    amb.market.blotter.ordini["B-9"] = ordine
    _manda(amb, ws, _cmd("desktop", 4, azione="cancel", bet_id="B-9"))
    assert _ack(amb, ws)["accettato"] is True
    assert amb.market.calls == [("cancel", ordine, None)]
    # chiusura dichiarata: passa SOLO se verificata sulle esposizioni
    _manda(amb, ws, _cmd("desktop", 5, side="LAY", reduces_liability=True))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_RIDUZIONE)


def test_guardia_armata_chiusura_verificata_passa(amb, monkeypatch):
    amb.guardia["armata"] = True
    monkeypatch.setattr(LOW, "_read_matched_exposures", lambda *a: (4.5, -3.0))
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd(side="LAY", price=2.0, reduces_liability=True))
    assert _ack(amb, ws)["accettato"] is True
    assert len(amb.market.calls) == 1


def test_fill_or_kill_arriva_a_flumine_e_valori_ammessi(amb):
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd(n=1, time_in_force="FILL_OR_KILL"))
    assert _ack(amb, ws)["accettato"] is True
    order = amb.market.calls[0][0]
    assert order.order_type.time_in_force == "FILL_OR_KILL"
    _manda(amb, ws, _cmd(n=2, time_in_force="GOOD_TILL_CANCEL"))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_PARAM)
    _manda(amb, ws, _cmd(n=3, reduces_liability="si"))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_PARAM)
    assert len(amb.market.calls) == 1


def test_reduces_liability_solo_dal_comando_mai_dai_params():
    piano = MO.valida_comando("safe", _cmd(params={"reduces_liability": True,
                                                   "fok_ttl_sec": 5}))
    assert "reduces_liability" not in piano["riga"]["params"]
    assert piano["riga"]["params"]["fok_ttl_sec"] == 5 and piano["riduce"] is False
    piano = MO.valida_comando("safe", _cmd(reduces_liability=True))
    assert piano["riga"]["params"]["reduces_liability"] is True and piano["riduce"] is True


def test_sotto_il_minimo_rifiutato_con_motivo_esplicito(amb):
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd(n=1, size=1.0))                 # BACK .it: minimo 2,00
    assert _ack(amb, ws)["motivo"].startswith(MO.M_SUBMIN)
    assert amb.market.calls == []
    _manda(amb, ws, _cmd(n=2, side="LAY", size=0.6))     # LAY .it: minimo 0,50
    assert _ack(amb, ws)["accettato"] is True


@pytest.mark.parametrize("win,lose,side,price,size,atteso", [
    (4.5, -3.0, "LAY", 2.0, 3.0, True),      # hedge della BACK
    (4.5, -3.0, "BACK", 2.5, 3.0, False),    # la raddoppia
    (0.0, 0.0, "LAY", 2.0, 1.0, False),      # piatta: niente da ridurre
    (-4.5, 3.0, "BACK", 2.0, 3.0, True),     # hedge di una LAY
    (4.5, -3.0, "LAY", 2.0, 20.0, False),    # la ribalta oltre
])
def test_riduce_esposizione(win, lose, side, price, size, atteso):
    assert MO.riduce_esposizione(win, lose, side, price, size) is atteso


@pytest.mark.parametrize("fonte", ["env", "db"])
def test_kill_switch_blocca_aperture_non_chiusure(amb, monkeypatch, fonte):
    if fonte == "env":
        monkeypatch.setattr(LOW, "_kill_switch", lambda: True)
    else:
        monkeypatch.setattr(LOW, "_SETTINGS", {"kill_switch": True})
    ws = amb.ch.collega("omega")
    _manda(amb, ws, _cmd("omega", 1))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_KILL)
    # reduces_liability dentro i params NON conta (tolto): resta un'apertura
    _manda(amb, ws, _cmd("omega", 2, side="LAY", params={"reduces_liability": True}))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_KILL)
    # dichiarata ma posizione piatta: non verificabile -> rifiuto con motivo
    _manda(amb, ws, _cmd("omega", 3, side="LAY", reduces_liability=True))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_RIDUZIONE)
    assert amb.market.calls == []
    # posizione abbinata BACK 3 @ 2.5 (win +4.5 / lose -3.0): il LAY la riduce
    monkeypatch.setattr(LOW, "_read_matched_exposures", lambda *a: (4.5, -3.0))
    _manda(amb, ws, _cmd("omega", 4, side="LAY", price=2.0, reduces_liability=True))
    assert _ack(amb, ws)["accettato"] is True
    assert len(amb.market.calls) == 1
    # un BACK dichiarato "chiusura" sulla stessa posizione la AUMENTA: rifiuto
    _manda(amb, ws, _cmd("omega", 5, side="BACK", reduces_liability=True))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_RIDUZIONE)
    assert len(amb.market.calls) == 1


def test_settings_stantie_rifiutano_aperture_senza_leggere_il_db(amb, monkeypatch):
    monkeypatch.setattr(LOW, "_SETTINGS_TS", time.monotonic() - 60.0)
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd(n=1))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_SETTINGS)
    monkeypatch.setattr(LOW, "_SETTINGS_TS", None)      # mai letti
    _manda(amb, ws, _cmd(n=2))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_SETTINGS)
    assert amb.market.calls == []
    assert amb.spia_diretta.chiamate == []                # nessuna lettura sincrona
    # le chiusure non dipendono dai settings: passano
    ordine = SimpleNamespace(bet_id="B-1", market_id="1.234", client=amb.paper)
    amb.market.blotter.ordini["B-1"] = ordine
    _manda(amb, ws, _cmd(n=3, azione="cancel", bet_id="B-1"))
    assert _ack(amb, ws)["accettato"] is True


def test_diario_non_scrivibile_nessun_ordine(amb, monkeypatch):
    def _rotto(*_a: Any, **_k: Any) -> None:
        raise OSError("disco pieno")
    monkeypatch.setattr(amb.diario, "scrivi", _rotto)
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd())
    ack = _ack(amb, ws)
    assert ack["accettato"] is False and ack["motivo"].startswith(MO.M_DIARIO)
    _mai_eseguito(amb)


def test_riga_ordine_del_diario_non_scrivibile_blocca_il_place(amb, monkeypatch):
    """Il comando e' nel diario, ma la riga ``ordine`` (subito prima del place)
    fallisce: il place NON parte, l'esito e' un rifiuto pre-place."""
    vero = amb.diario.scrivi

    def _scrivi(rec: Dict[str, Any], **k: Any) -> None:
        if rec.get("tipo") == "ordine":
            raise OSError("disco pieno")
        vero(rec, **k)
    monkeypatch.setattr(amb.diario, "scrivi", _scrivi)
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd())
    assert _ack(amb, ws)["accettato"] is True
    _mai_eseguito(amb)
    ev = amb.ch.per_ws(ws, "order")[-1]["d"]
    assert ev["fase"] == "rifiutato"


# ===========================================================================
# dedup, seq, da_seq
# ===========================================================================
def test_dedup_stesso_ref_stessa_risposta_mai_doppio_invio(amb):
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd())
    primo = _ack(amb, ws)
    _manda(amb, ws, _cmd(price=9.0))      # stesso ref, contenuto diverso
    secondo = _ack(amb, ws)
    assert secondo == dict(primo, motivo=MO.MOTIVO_REF_GIA_VISTO)
    assert secondo["accettato"] is True and secondo["seq"] == primo["seq"]
    assert len(amb.market.calls) == 1


def test_dedup_sopravvive_al_riavvio_dal_diario(amb):
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd(n=1))
    _manda(amb, ws, _cmd(n=2, side="x"))
    acc, rif = amb.ch.per_ws(ws, "ack")[0]["d"], amb.ch.per_ws(ws, "ack")[1]["d"]
    amb.diario.chiudi()
    # "riavvio": motore nuovo, stesso diario
    nuovo = MO.MotoreOrdini("calcio", canale=amb.ch, diario=MO.Diario(amb.diario.cartella),
                            scrittore=amb.scrittore)
    nuovo._carica_visti()
    nuovo.aggancia(amb.fl, {"live": _STRAT_LIVE, "paper": _STRAT_PAPER})
    amb.motore = nuovo
    _manda(amb, ws, _cmd(n=1))
    assert _ack(amb, ws) == dict(acc, motivo=MO.MOTIVO_REF_GIA_VISTO)
    _manda(amb, ws, _cmd(n=2))
    assert _ack(amb, ws) == dict(rif, motivo=MO.MOTIVO_REF_GIA_VISTO)
    assert rif["accettato"] is False
    assert len(amb.market.calls) == 1


def test_seq_crescente_per_attore_e_indipendente(amb):
    ws_s = amb.ch.collega("safe")
    ws_o = amb.ch.collega("omega")
    for i in range(3):
        _manda(amb, ws_s, _cmd("safe", i))
        _manda(amb, ws_o, _cmd("omega", i))
    for ws in (ws_s, ws_o):
        seqs = [m["d"]["seq"] for m in amb.ch.per_ws(ws)]
        assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    # l'altro attore non riceve gli eventi del primo
    assert all(m["d"]["ref"].startswith("omega-") for m in amb.ch.per_ws(ws_o))


def test_da_seq_rimanda_i_mancanti_in_ordine(amb):
    ws = amb.ch.collega("safe")
    for i in range(3):
        _manda(amb, ws, _cmd(n=i))
    tutti = amb.ch.per_ws(ws)
    dal = tutti[1]["d"]["seq"]
    ws2 = amb.ch.collega("safe")          # riconnessione
    _manda(amb, ws2, {"seq": dal}, t="da_seq")
    rimandati = amb.ch.per_ws(ws2)
    assert [m["d"]["seq"] for m in rimandati[:-1]] == [m["d"]["seq"] for m in tutti[2:]]
    sommario = rimandati[-1]
    assert sommario["t"] == "da_seq" and sommario["d"]["completo"] is True
    assert sommario["d"]["inviati"] == len(tutti) - 2


def test_da_seq_oltre_la_memoria_dichiara_incompleto(amb):
    ws = amb.ch.collega("safe")
    primo = None
    for i in range(MO.MEMORIA_EVENTI // 2 + 5):   # 2 messaggi per comando (ack + order)
        _manda(amb, ws, _cmd(n=i, side="x"))      # rifiuti registrati: 1 msg ciascuno
        if primo is None:
            primo = _ack(amb, ws)["seq"]
    for i in range(300):
        _manda(amb, ws, _cmd(n=1000 + i, side="x"))
    ws2 = amb.ch.collega("safe")
    _manda(amb, ws2, {"seq": primo}, t="da_seq")
    sommario = amb.ch.per_ws(ws2)[-1]["d"]
    assert sommario["completo"] is False
    assert sommario["inviati"] == MO.MEMORIA_EVENTI


# ===========================================================================
# F1 diario write-ahead
# ===========================================================================
def _righe_diario(a: Any) -> List[Dict[str, Any]]:
    p = a.diario.percorso()
    with open(p, encoding="ascii") as fh:
        return [json.loads(r) for r in fh if r.strip()]


def test_riga_ordine_su_disco_prima_del_place(amb):
    visto: Dict[str, Any] = {}

    def _sonda(order: Any) -> None:
        # dentro market.place_order: il diario su DISCO deve gia' avere il
        # comando e l'ordine con il customerOrderRef VERO di flumine
        righe = _righe_diario(amb)
        visto["inviato"] = [r for r in righe if r["tipo"] == "inviato"]
        visto["ordine"] = [r for r in righe if r["tipo"] == "ordine"]
        visto["cor"] = order.customer_order_ref
    amb.market.su_place = _sonda
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd())
    assert len(amb.market.calls) == 1
    assert [r["ref"] for r in visto["inviato"]] == ["safe-t1"]
    assert len(visto["ordine"]) == 1 and visto["ordine"][0]["cor"] == visto["cor"]
    assert visto["ordine"][0]["ref"] == "safe-t1"
    # dopo: la riga di esito con lo stesso ref
    esiti = [r for r in _righe_diario(amb) if r["tipo"] == "esito"]
    assert esiti and esiti[-1]["ref"] == "safe-t1" and esiti[-1]["ok"] is True


# ===========================================================================
# F2 zero IO DB nel percorso + scrittore asincrono
# ===========================================================================
def test_nessuna_chiamata_db_nel_percorso_tutto_sullo_scrittore(amb):
    al_place: Dict[str, int] = {}
    amb.market.su_place = lambda _o: al_place.setdefault(
        "n", len(amb.sb.chiamate) + len(amb.spia_diretta.chiamate))
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd())
    assert al_place["n"] == 0                       # DB intatto al momento del place
    assert amb.scrittore.svuota(5.0)
    assert amb.spia_diretta.chiamate == []          # nessun client DB diretto
    thread_db = {t for t, *_ in amb.sb.chiamate}
    assert thread_db == {amb.scrittore.thread_ident}
    tabelle = [(tab, op) for _t, tab, op, _p in amb.sb.chiamate]
    # stesso lavoro DB del /order di sempre: audit, riga di coda, journal
    assert ("betfair_live_audit", "insert") in tabelle
    assert ("betfair_live_order_requests", "insert") in tabelle
    assert ("betfair_live_journal", "insert") in tabelle
    assert tabelle.index(("betfair_live_audit", "insert")) < tabelle.index(
        ("betfair_live_order_requests", "insert")) < tabelle.index(
        ("betfair_live_journal", "insert"))
    riga = next(p for _t, tab, op, p in amb.sb.chiamate
                if tab == "betfair_live_order_requests" and op == "insert")
    assert riga["status"] == "done" and riga["mode"] == "paper"
    assert riga["params"]["comando"]["ref"] == "safe-t1"


def test_lettura_db_nel_percorso_differito_e_un_difetto_rosso():
    sbd = LOW._SbDifferito()
    sbd.table("betfair_live_audit").insert({"a": 1}).execute()
    with pytest.raises(LOW.LetturaNelPercorsoOrdine):
        sbd.table("live_now").select("minute").eq("event_id", "E").execute()
    spia = _SbSpia()
    sbd.rigioca(spia)
    assert [(tab, op) for _t, tab, op, _p in spia.chiamate] == [("betfair_live_audit", "insert")]


def test_specchio_con_scrittore_niente_io_sul_thread_chiamante(amb):
    DB.imposta_scrittore(amb.scrittore)
    riga = {"mode": "paper", "client_order_ref": "awlq123", "bet_id": "B1",
            "status": "EXECUTABLE"}
    DB.upsert_live_order(riga)
    DB.upsert_live_position({"mode": "paper", "market_id": "1.234", "selection_id": 1,
                             "handicap": 0.0})
    assert amb.scrittore.svuota(5.0)
    assert amb.spia_diretta.chiamate == []
    assert [(tab, op) for _t, tab, op, _p in amb.sb.chiamate] == [
        ("betfair_live_orders", "upsert"), ("betfair_live_positions", "upsert")]
    assert {t for t, *_ in amb.sb.chiamate} == {amb.scrittore.thread_ident}


def test_scrittore_ritenta_e_conserva_l_ordine():
    fatti: List[str] = []
    stato = {"n": 0}

    def _instabile(_sb: Any) -> None:
        stato["n"] += 1
        if stato["n"] < 3:
            raise ConnectionError("Server disconnected")
        fatti.append("a")
    s = MO.ScrittoreAsincrono(sb_factory=lambda: object(), dormi=lambda _s: None)
    s.avvia()
    s.accoda("a", _instabile, tentativi=5)
    s.accoda("b", lambda _sb: fatti.append("b"))
    assert s.svuota(5.0)
    s.ferma()
    assert fatti == ["a", "b"] and s.conti["eseguiti"] == 2 and s.conti["falliti"] == 0


# ===========================================================================
# eventi dallo specchio: fasi di Betfair, trattenute fino all'esito del dispatch
# ===========================================================================
def test_eventi_dallo_specchio_con_fasi_e_riga_identica(amb):
    ws = amb.ch.collega("safe")
    DB.aggiungi_osservatore_ordini(amb.motore._su_riga_specchio)
    DB.imposta_scrittore(amb.scrittore)
    _manda(amb, ws, _cmd())
    cust = amb.ch.per_ws(ws, "order")[0]["d"]["client_order_ref"]
    base = {"client_order_ref": cust, "request_id": None, "mode": "paper", "event_id": "E1",
            "market_id": "1.234", "selection_id": 47972, "handicap": 0.0, "side": "back",
            "order_type": "LIMIT", "price": 2.5, "size": 3.0, "size_cancelled": 0.0,
            "size_lapsed": 0.0, "size_voided": 0.0, "persistence": "LAPSE",
            "placed_at": None, "matched_at": None}
    DB.upsert_live_order({**base, "bet_id": "B1", "status": "EXECUTABLE",
                          "size_matched": 0.0, "size_remaining": 3.0,
                          "average_price_matched": 0.0})
    DB.upsert_live_order({**base, "bet_id": "B1", "status": "EXECUTABLE",
                          "size_matched": 1.0, "size_remaining": 2.0,
                          "average_price_matched": 2.5})
    DB.upsert_live_order({**base, "bet_id": "B1", "status": "EXECUTION_COMPLETE",
                          "size_matched": 3.0, "size_remaining": 0.0,
                          "average_price_matched": 2.52})
    # riga di un ordine NON nato da un comando: nessun evento
    DB.upsert_live_order({**base, "client_order_ref": "awlq55", "bet_id": "B2",
                          "status": "EXECUTABLE", "size_matched": 0.0,
                          "size_remaining": 1.0, "average_price_matched": 0.0})
    ev = [m["d"] for m in amb.ch.per_ws(ws, "order")]
    assert [e["fase"] for e in ev] == ["inviato", "accettato_betfair", "abbinato_parziale",
                                      "abbinato"]
    assert all(e["ref"] == "safe-t1" for e in ev)
    assert [e["seq"] for e in ev] == sorted(e["seq"] for e in ev)
    # la riga dello specchio passa IDENTICA (piu' ref/seq/fase/esito_ms)
    ultimo = dict(ev[-1])
    for k in ("ref", "seq", "fase", "esito_ms", "updated_at"):
        ultimo.pop(k)
    assert ultimo == {**base, "bet_id": "B1", "status": "EXECUTION_COMPLETE",
                      "size_matched": 3.0, "size_remaining": 0.0,
                      "average_price_matched": 2.52}


def test_righe_dello_specchio_prima_dell_esito_sono_trattenute(amb):
    ws = amb.ch.collega("safe")
    DB.aggiungi_osservatore_ordini(amb.motore._su_riga_specchio)

    def _specchio_subito(order: Any) -> None:
        # lo stream ordini arriva PRIMA che il dispatch sia tornato
        cust = order.context.get("customer_order_ref") if isinstance(order.context, dict) \
            else None
        amb.motore._su_riga_specchio({"client_order_ref": cust, "mode": "paper",
                                      "bet_id": "B7", "status": "EXECUTABLE",
                                      "size_matched": 0.0})
    amb.market.su_place = _specchio_subito
    _manda(amb, ws, _cmd())
    fasi = [m["d"]["fase"] for m in amb.ch.per_ws(ws, "order")]
    assert fasi == ["inviato", "accettato_betfair"]


@pytest.mark.parametrize("riga,fase", [
    ({"status": "PENDING"}, "inviato"),
    ({"status": "EXECUTABLE", "bet_id": None}, "inviato"),
    ({"status": "EXECUTABLE", "bet_id": "1"}, "accettato_betfair"),
    ({"status": "EXECUTABLE", "bet_id": "1", "size_matched": 0.5}, "abbinato_parziale"),
    ({"status": "EXECUTION_COMPLETE", "size_matched": 2.0}, "abbinato"),
    ({"status": "EXECUTION_COMPLETE", "size_matched": 1.0, "size_cancelled": 1.0},
     "annullato"),
    ({"status": "EXECUTION_COMPLETE", "size_matched": 0.0, "size_lapsed": 2.0}, "scaduto"),
    ({"status": "VIOLATION"}, "rifiutato"),
    ({"status": "EXPIRED"}, "scaduto"),
])
def test_fase_da_riga(riga, fase):
    assert MO.fase_da_riga(riga) == fase


# ===========================================================================
# F2 latenza: svuotamento a evento contro il sonno del BackgroundWorker
# ===========================================================================
def _misura_motore(amb: Any, n: int) -> List[float]:
    tempi: List[float] = []
    arrivato = threading.Event()
    amb.market.su_place = lambda _o: arrivato.set()
    amb.motore.avvia()
    try:
        ws = amb.ch.collega("safe")
        for i in range(n):
            arrivato.clear()
            t0 = time.perf_counter()
            amb.ch._on_comando(ws, json.dumps({"t": "comando", "d": _cmd(n=i)}))
            assert arrivato.wait(2.0), "place mai arrivato"
            tempi.append((time.perf_counter() - t0) * 1000.0)
    finally:
        amb.motore.ferma()
    return tempi


def test_latenza_logica_comando_place_sotto_20_ms(amb, capsys):
    tempi = sorted(_misura_motore(amb, 60))
    p50 = tempi[len(tempi) // 2]
    p95 = tempi[int(len(tempi) * 0.95) - 1]
    with capsys.disabled():
        print(f"\n[misura DOPO] motore a evento, comando->place: p50={p50:.2f} ms "
              f"p95={p95:.2f} ms max={tempi[-1]:.2f} ms (n={len(tempi)})")
    assert p95 < 20.0


def test_misura_prima_worker_a_1_secondo(amb, monkeypatch, capsys):
    """PRIMA: il /order aspettava il giro del BackgroundWorker (esegue, poi
    dorme 1,0 s). Stesso comando, stesso Market finto, IO DB azzerato (sb
    finto istantaneo): resta solo l'attesa del giro."""
    from flumine.worker import BackgroundWorker

    monkeypatch.setattr(LOW, "_refresh_settings", lambda _sb: None)
    arrivato = threading.Event()
    amb.market.su_place = lambda _o: arrivato.set()
    giro_fatto = threading.Event()

    def _funzione(ctx: Any, fl: Any, **kw: Any) -> None:
        LOW._process_once(_SbSpia(), fl, None, kw["strategy"])
        giro_fatto.set()
    w = BackgroundWorker(amb.fl, function=_funzione, interval=1.0,
                         func_kwargs={"strategy": {"live": _STRAT_LIVE,
                                                   "paper": _STRAT_PAPER}})
    w.start()
    tempi: List[float] = []
    try:
        for i in range(3):
            giro_fatto.clear()
            assert giro_fatto.wait(3.0)
            time.sleep(0.05 + 0.3 * i)        # arrivo in un punto diverso del sonno
            arrivato.clear()
            t0 = time.perf_counter()
            amb.ch._requests.put_nowait(LC.LocalRequest(
                ws=None, msg_id=i, method="order",
                params={"action": "place", "mode": "paper", "client_ref": f"prima-{i}",
                        "market_id": "1.234", "selection_id": 47972, "side": "BACK",
                        "price": 2.5, "size": 3.0, "persistence": "LAPSE"}))
            assert arrivato.wait(3.0)
            tempi.append((time.perf_counter() - t0) * 1000.0)
    finally:
        w._running = False
    with capsys.disabled():
        print(f"\n[misura PRIMA] worker a 1,0 s, comando->place: "
              f"{', '.join(f'{t:.0f}' for t in tempi)} ms")
    assert min(tempi) > 100.0


# ===========================================================================
# ripresa all'avvio dal diario
# ===========================================================================
def _scrivi_diario(diario: MO.Diario, righe: List[Dict[str, Any]]) -> None:
    for r in righe:
        diario.scrivi(r)


def test_ripresa_rilegge_betfair_per_i_comandi_in_volo(amb):
    _scrivi_diario(amb.diario, [
        {"tipo": "inviato", "ref": "mike-t1", "mode": "live", "azione": "place",
         "ack": {"ref": "mike-t1", "seq": 5, "accettato": True, "motivo": None,
                 "ricevuto_ms": 1}},
        {"tipo": "ordine", "ref": "mike-t1", "cor": "abc123-0001"},
        {"tipo": "inviato", "ref": "mike-t2", "mode": "live", "azione": "place"},
        {"tipo": "ordine", "ref": "mike-t2", "cor": "abc123-0002"},
        {"tipo": "inviato", "ref": "mike-t3", "mode": "live", "azione": "place"},
        {"tipo": "inviato", "ref": "safe-t9", "mode": "paper", "azione": "place"},
        {"tipo": "inviato", "ref": "safe-t10", "mode": "live", "azione": "place"},
        {"tipo": "esito", "ref": "safe-t10", "ok": True},
    ])
    chieste: List[List[str]] = []

    def _lista(refs: List[str]) -> Dict[str, Any]:
        chieste.append(list(refs))
        # risposta lightweight di listCurrentOrders: chiavi VERE di Betfair
        return {"currentOrders": [{
            "betId": "31242604945", "marketId": "1.234", "selectionId": 47972,
            "handicap": 0.0, "priceSize": {"price": 2.5, "size": 3.0}, "bspLiability": 0.0,
            "side": "BACK", "status": "EXECUTABLE", "persistenceType": "LAPSE",
            "orderType": "LIMIT", "placedDate": "2026-09-24T10:00:00.000Z",
            "averagePriceMatched": 0.0, "sizeMatched": 0.0, "sizeRemaining": 3.0,
            "sizeLapsed": 0.0, "sizeCancelled": 0.0, "sizeVoided": 0.0,
            "regulatorCode": "ITALIAN GAMING", "customerOrderRef": "abc123-0001",
            "customerStrategyRef": "mike"}], "moreAvailable": False}
    assert amb.motore.riprendi_da_diario(_lista) is True
    assert chieste == [["abc123-0001", "abc123-0002"]]
    riprese = {r["ref"]: r for r in _righe_diario(amb) if r["tipo"] == "ripresa"}
    assert riprese["mike-t1"]["esito"] == "ritrovato"
    assert riprese["mike-t1"]["dettaglio"][0]["betId"] == "31242604945"
    assert riprese["mike-t2"]["esito"] == "non_trovato"
    assert riprese["mike-t3"]["esito"] == "mai_inviato_place"
    assert riprese["safe-t9"]["esito"] == "perso_paper"
    assert "safe-t10" not in riprese
    # seconda ripresa: niente piu' in volo, nessuna chiamata
    assert amb.motore.riprendi_da_diario(_lista) is True
    assert len(chieste) == 1


def test_ripresa_betfair_giu_guardia_resta_armata(amb):
    _scrivi_diario(amb.diario, [
        {"tipo": "inviato", "ref": "mike-t1", "mode": "live", "azione": "place"},
        {"tipo": "ordine", "ref": "mike-t1", "cor": "abc-1"},
    ])

    def _giu(_refs: List[str]) -> Any:
        raise ConnectionError("api.betfair.com irraggiungibile")
    assert amb.motore.riprendi_da_diario(_giu) is False
    assert amb.motore.riprendi_da_diario(None) is False
    assert not [r for r in _righe_diario(amb) if r["tipo"] == "ripresa"]


def test_runner_ripresa_col_motore_non_disarma_se_betfair_giu(amb, monkeypatch):
    from Betfair.stream import runner as R

    class _Db:
        def cleanup_paper_mirror(self):
            return (0, 0)

        def fail_stale_pending_requests(self, older_than_sec=120.0):
            return 0

        def insert_alert(self, *a):
            pass
    monkeypatch.setattr(R, "db", _Db())
    _scrivi_diario(amb.diario, [
        {"tipo": "inviato", "ref": "mike-t1", "mode": "live", "azione": "place"},
        {"tipo": "ordine", "ref": "mike-t1", "cor": "abc-1"},
    ])
    monkeypatch.setitem(R._MOTORE, "motore", amb.motore)
    monkeypatch.setitem(R._MOTORE, "api", None)       # Betfair non disponibile
    R._GUARDIA_AVVIO.azzera()
    R._GUARDIA_AVVIO.attiva = True
    try:
        assert R._ripresa_all_avvio() is False
        assert R._GUARDIA_AVVIO.blocca_aperture is True
        api = SimpleNamespace(betting=SimpleNamespace(
            list_current_orders=lambda **kw: {"currentOrders": [], "moreAvailable": False}))
        monkeypatch.setitem(R._MOTORE, "api", api)
        assert R._ripresa_all_avvio() is True
        assert R._GUARDIA_AVVIO.blocca_aperture is False
    finally:
        R._GUARDIA_AVVIO.azzera()


# ===========================================================================
# parita' del /order di sempre servito dal motore
# ===========================================================================
def _req(msg_id: Any, **p: Any) -> LC.LocalRequest:
    base = {"action": "place", "mode": "paper", "client_ref": f"cr-{msg_id}",
            "market_id": "1.234", "selection_id": 47972, "side": "BACK", "price": 2.5,
            "size": 3.0, "persistence": "LAPSE"}
    base.update(p)
    return LC.LocalRequest(ws=None, msg_id=msg_id, method="order", params=base)


def _scenari_order() -> List[LC.LocalRequest]:
    return [
        _req(1),                                           # place ok
        _req(1, client_ref="cr-1"),                        # reinvio identico (dedup)
        _req(2, action="cancel", bet_id="NON-C-E"),        # cancel ordine assente
        _req(3, action="dutch_non_esiste"),                # azione non supportata
        _req(4, mode="demo"),                              # mode sconosciuta
        _req(5, side="BOH"),                               # errore di validazione
    ]


def _normalizza(risposte: List[tuple]) -> List[tuple]:
    out = []
    for mid, ok, data, err in risposte:
        d = dict(data) if isinstance(data, dict) else data
        if isinstance(d, dict):
            d.pop("customer_order_ref", None)             # rid sintetico: diverso
        out.append((mid, ok, d, err))
    return out


def test_parita_order_motore_contro_worker(amb, monkeypatch):
    # PRIMA: il worker di sempre (percorso diretto, sb sincrono)
    for r in _scenari_order():
        amb.ch._requests.put_nowait(r)
    sb_prima = _SbSpia()
    LOW._process_local_requests(sb_prima, amb.fl, "live", {"live": _STRAT_LIVE,
                                                            "paper": _STRAT_PAPER})
    prima = _normalizza(amb.ch.risposte)
    tab_prima = [(tab, op) for _t, tab, op, _p in sb_prima.chiamate]
    calls_prima = len(amb.market.calls)
    # DOPO: stesso canale, stesso market, servito dal MOTORE
    amb.ch.risposte.clear()
    monkeypatch.setattr(LOW, "_LOCAL_SEEN", {})
    for r in _scenari_order():
        amb.ch._requests.put_nowait(r)
    amb.motore.drena()
    dopo = _normalizza(amb.ch.risposte)
    assert amb.scrittore.svuota(5.0)
    tab_dopo = [(tab, op) for _t, tab, op, _p in amb.sb.chiamate]
    assert dopo == prima
    assert len(amb.market.calls) - calls_prima == calls_prima
    # stesso lavoro DB (stesse tabelle, stesso ordine), ma sullo scrittore
    assert tab_dopo == tab_prima
    assert {t for t, *_ in amb.sb.chiamate} == {amb.scrittore.thread_ident}
    # il /order passa dal diario (comando + ordine) con ref "order-<client_ref>"
    righe = _righe_diario(amb)
    assert any(r["tipo"] == "inviato" and r["ref"] == "order-cr-1" for r in righe)
    assert any(r["tipo"] == "ordine" and r["ref"] == "order-cr-1" for r in righe)


def test_order_via_motore_in_guardia_come_b1(amb):
    from Betfair.stream import runner as R

    amb.guardia["armata"] = True
    ordine = SimpleNamespace(bet_id="B-1", market_id="1.234", client=amb.paper)
    amb.market.blotter.ordini["B-1"] = ordine
    amb.ch._requests.put_nowait(_req(1))
    amb.ch._requests.put_nowait(_req(2, action="cancel", bet_id="B-1"))
    amb.ch._requests.put_nowait(LC.LocalRequest(ws=None, msg_id=3, method="snapshot",
                                                params={"market_id": "1.234"}))
    amb.motore.drena()
    per_id = {m: (ok, err) for m, ok, _d, err in amb.ch.risposte}
    assert per_id[1] == (False, R._MOTIVO_GUARDIA_LOCALE)
    assert per_id[3] == (False, R._MOTIVO_GUARDIA_LOCALE)
    assert per_id[2][0] is True
    assert amb.market.calls == [("cancel", ordine, None)]
    assert amb.ch._requests.qsize() == 0


def test_order_via_motore_senza_framework_rifiuta_non_accoda(amb):
    amb.motore.sgancia()
    amb.ch._requests.put_nowait(_req(1))
    amb.motore.drena()
    assert [(m, ok) for m, ok, _d, _e in amb.ch.risposte] == [(1, False)]
    assert amb.ch._requests.qsize() == 0
    _mai_eseguito(amb)


def test_worker_della_coda_non_drena_il_canale_col_motore(amb, monkeypatch):
    from Betfair.stream import runner as R

    amb.ch._requests.put_nowait(_req(1))
    LOW.imposta_drenaggio_esterno(True)
    monkeypatch.setattr(LOW, "_refresh_settings", lambda _sb: None)
    LOW._process_once(_SbSpia(), amb.fl, None, {"live": _STRAT_LIVE, "paper": _STRAT_PAPER})
    assert amb.ch._requests.qsize() == 1                 # lasciato al motore
    # guardia armata + motore montato: il runner non drena (lo fa il motore)
    monkeypatch.setitem(R._MOTORE, "motore", amb.motore)
    monkeypatch.setattr(R, "_ripresa_all_avvio", lambda: False)
    R._GUARDIA_AVVIO.azzera()
    R._GUARDIA_AVVIO.attiva = True
    R._RIPRESA_STATO["ultimo"] = 0.0
    try:
        R._live_order_worker_guardato({}, amb.fl, strategy={})
        assert amb.ch._requests.qsize() == 1
    finally:
        R._GUARDIA_AVVIO.azzera()
        R._RIPRESA_STATO["ultimo"] = 0.0


# ===========================================================================
# canale: /comando/, token, niente motore, busta, non conta come desktop
# ===========================================================================
def test_canale_percorso_comando_e_token(monkeypatch):
    assert LC.attore_del_comando("/comando/safe") == "safe"
    assert LC.attore_del_comando("/comando/safe?x=1") == "safe"
    assert LC.attore_del_comando("/comando/") == ""
    assert LC.attore_del_comando("/lettore/order") is None
    assert LC.attore_del_comando(None) is None
    # UNA sola sorgente del token: quella di C1 (``token_di_sessione`` al
    # costruttore del canale), letta da ``token_canale`` sul canale attivo
    monkeypatch.setenv("LOCAL_CHANNEL_TOKEN", TOKEN)
    ch = LC.LocalChannel(59995, "calcio")
    assert ch._token_valido(TOKEN) and not ch._token_valido(TOKEN[:-1] + "x")
    assert not ch._token_valido(None) and not ch._token_valido("")
    monkeypatch.setattr(LC, "_CHANNEL", ch)
    assert LC.token_canale() == TOKEN
    monkeypatch.setattr(LC, "_CHANNEL", None)
    assert LC.token_canale() is None
    monkeypatch.setenv("LOCAL_CHANNEL_TOKEN", "corto")
    assert not LC.LocalChannel(59994, "calcio")._token_valido("corto")


def test_canale_senza_motore_rifiuta_subito(monkeypatch):
    monkeypatch.setenv("LOCAL_CHANNEL_TOKEN", TOKEN)
    ch = _Canale()
    ws = ch.collega("safe")
    ch._on_comando(ws, json.dumps({"t": "comando", "d": _cmd()}))
    ack = ch.per_ws(ws, "ack")[-1]["d"]
    assert ack["accettato"] is False and ack["motivo"].startswith("motore_non_attivo")
    assert ch._comandi.qsize() == 0
    ch._on_comando(ws, "{non json")
    assert ch.per_ws(ws, "ack")[-1]["d"]["motivo"].startswith("parametri_invalidi")
    ch._on_comando(ws, json.dumps({"t": "boh", "d": {}}))
    assert ch.per_ws(ws, "ack")[-1]["d"]["motivo"].startswith("parametri_invalidi")


def test_canale_coda_comandi_piena_e_sveglia(monkeypatch):
    ch = _Canale()
    sveglie = []
    ch.set_su_comando(lambda: sveglie.append(1))
    ws = ch.collega("safe")
    for i in range(LC._MAX_COMANDI + 1):
        ch._on_comando(ws, json.dumps({"t": "comando", "d": _cmd(n=i)}))
    assert ch._comandi.qsize() == LC._MAX_COMANDI
    assert len(sveglie) == LC._MAX_COMANDI
    assert ch.per_ws(ws, "ack")[-1]["d"]["motivo"].startswith("coda_piena")
    # anche il /order di sempre (connessione col token di C1) sveglia il motore
    desktop = _FintoWs("desktop")
    ch._autorizzati.add(desktop)
    ch._on_message(desktop, json.dumps({"id": 1, "m": "order", "p": {}}))
    assert len(sveglie) == LC._MAX_COMANDI + 1
    # senza token C1 il /order e' rifiutato dal canale: nessuna sveglia
    ch._on_message(_FintoWs("estraneo"), json.dumps({"id": 2, "m": "order", "p": {}}))
    assert len(sveglie) == LC._MAX_COMANDI + 1


def test_socket_di_comando_non_conta_come_desktop():
    import asyncio

    ch = LC.LocalChannel(59996, "calcio", token=TOKEN)

    class _Ws:
        def __init__(self, path: str, tok: Optional[str] = "x") -> None:
            headers = {"X-Canale-Token": tok} if tok is not None else {}
            self.request = SimpleNamespace(path=path, headers=headers)
            self.inviati: List[str] = []

        async def send(self, t: str) -> None:
            self.inviati.append(t)

        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.sleep(0.05)
            raise StopAsyncIteration

    async def _prova() -> None:
        ws = _Ws("/comando/mike")
        task = asyncio.ensure_future(ch._handler(ws))
        await asyncio.sleep(0.01)
        assert ch._comando_ws[ws] == ("mike", False)     # token sbagliato
        assert ch.is_active() is False
        await task
        assert ws not in ch._comando_ws
        # token giusto: dall'header oppure da ``?t=`` (C1), UNICA sorgente
        for w in (_Ws("/comando/mike", TOKEN), _Ws(f"/comando/mike?t={TOKEN}", None)):
            t = asyncio.ensure_future(ch._handler(w))
            await asyncio.sleep(0.01)
            assert ch._comando_ws[w] == ("mike", True)
            await t
    asyncio.run(_prova())
