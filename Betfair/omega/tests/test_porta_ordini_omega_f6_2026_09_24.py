"""F6 (24/09) - Omega: la PORTA degli ordini sul canale di comando del runner.

Protocollo "COMANDO ORDINE" (lo stesso di Safe): ``/comando/omega`` su 47331,
header ``X-Canale-Token``, busta ``{"t":..., "d":{...}}``, ``comando`` -> ``ack``
-> eventi ``order`` con ``seq``, ``da_seq`` alla riconnessione.

Il FINTO del motore parla il protocollo esatto e VALIDA ogni comando con la
funzione VERA del runner (``motore_ordini.valida_comando``): un comando che il
runner rifiuterebbe (``strategy_ref`` diverso dall'attore, chiave mancante,
``time_in_force`` fuori protocollo) fa fallire il test. Le righe degli eventi
``order`` nascono dalla ``LiveTradingStrategy._order_row`` VERA (stesso encoder
del test di Safe). Le righe del bot sono quelle di ``omega_trades`` (i finti
storici di Omega: ``FakeQueueDB``, ``_DB``).

Falsificazioni (vedi il referto del delegato): ref casuale, ripiego su una
place, mode ereditato, seq ignorato, interruttore ignorato, esito di altra
modalita', FOK perso, riduzione persa, riconciliazione REST sulle righe canale.
ASCII-only.
"""
from __future__ import annotations

import itertools
import json
import queue
import threading
import time
from datetime import timedelta
from typing import Any, Optional

import pytest

from Betfair.omega import omega_service as S
from Betfair.omega import porta_ordini as PO
from Betfair.omega.test_omega_flumine_paper import FakeQueueDB, _params
from Betfair.omega.test_omega_greenup_2026_09_10 import _DB, CS_MID, _trade
from Betfair.omega.test_omega_service import (
    NOW,
    FakeMarket,
    _control,
    _cs,
    _event,
    _manual_req,
    _open_snapshot,
)
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy import porta_ordini as SPO
from Betfair.safe_strategy.tests.test_porta_ordini_f5_2026_09_24 import riga_specchio_vera
from Betfair.stream import motore_ordini as MO

TOKEN = "tok-omega-di-prova"
_BET = itertools.count(1)


# ---------------------------------------------------------------------------
# il FINTO del motore del runner (lato /comando/omega)
# ---------------------------------------------------------------------------
class FintaWS:
    def __init__(self, motore: "FintoMotore", url: str, headers: dict) -> None:
        self.motore = motore
        self.url = url
        self.headers = dict(headers)
        self.uscita: "queue.Queue[str]" = queue.Queue()
        self.chiusa = False

    def __enter__(self) -> "FintaWS":
        return self

    def __exit__(self, *a: Any) -> None:
        self.chiusa = True

    def send(self, testo: str) -> None:
        if self.chiusa:
            raise ConnectionError("socket chiuso")
        self.motore.gestisci(self, testo)

    def recv(self, timeout: Optional[float] = None) -> str:
        fine = time.monotonic() + (timeout or 0.0)
        while True:
            if self.chiusa:
                raise ConnectionError("socket chiuso")
            try:
                return self.uscita.get(timeout=0.02)
            except queue.Empty:
                if time.monotonic() >= fine:
                    raise TimeoutError()

    def close(self) -> None:
        self.chiusa = True


class FintoMotore:
    """``comportamento``: 'accetta' | 'rifiuta' | 'muto'. ``fase_finale``:
    'abbinato' | 'annullato' | None. ``parziale``: frazione abbinata prima
    della fine (evento ``abbinato_parziale``)."""

    def __init__(self) -> None:
        self.comportamento = "accetta"
        self.fase_finale: Optional[str] = "abbinato"
        self.motivo = "kill_switch"
        self.parziale: Optional[float] = None
        self.connessioni: list = []
        self.comandi: list = []
        self.da_seq: list = []
        self.eventi: list = []
        self.per_bet: dict = {}
        self.matched_per_bet: dict = {}
        self.visti: set = set()
        self.seq = 0
        self.rifiuta_connessione = False
        self.manda_eventi = True
        self._lock = threading.Lock()

    def connetti(self, url: str, headers: dict) -> FintaWS:
        if self.rifiuta_connessione:
            raise ConnectionRefusedError("runner giu'")
        if headers.get(SPO.HEADER_TOKEN) != TOKEN or not url.endswith("/comando/omega"):
            raise PermissionError("token o percorso errato: chiusura")
        ws = FintaWS(self, url, headers)
        self.connessioni.append(ws)
        return ws

    def _manda(self, ws: Optional[FintaWS], t: str, d: dict) -> None:
        if ws is not None and not ws.chiusa:
            ws.uscita.put(json.dumps({"t": t, "d": d}))

    def _nuovo_seq(self) -> int:
        with self._lock:
            self.seq += 1
            return self.seq

    def evento(self, ws: Optional[FintaWS], cmd: dict, fase: str, *, matched: float,
               remaining: float, status: str, bet_id: str, avg: float = 0.0) -> dict:
        riga = riga_specchio_vera(mode=cmd["mode"], bet_id=bet_id, size=cmd["size"],
                                  price=cmd["price"], side=cmd["side"], matched=matched,
                                  remaining=remaining, status=status, avg=avg)
        riga.update({"ref": cmd["ref"], "seq": self._nuovo_seq(), "fase": fase,
                     "esito_ms": round(time.time() * 1000.0, 1)})
        self.eventi.append(riga)
        if self.manda_eventi:
            self._manda(ws, "order", riga)
        return riga

    def gestisci(self, ws: FintaWS, testo: str) -> None:
        msg = json.loads(testo)
        t, d = msg.get("t"), msg.get("d")
        if t == "da_seq":
            n = int(d["seq"])
            self.da_seq.append(n)
            for e in list(self.eventi):
                if e["seq"] > n:
                    self._manda(ws, "order", e)
            return
        assert t == "comando", t
        # CONTRATTO: tutte e sole le chiavi, e il validatore VERO del runner
        assert tuple(d.keys()) == PO.CHIAVI_COMANDO, list(d.keys())
        MO.valida_comando("omega", d)
        self.comandi.append(d)
        if self.comportamento == "muto":
            return
        ack_seq = self._nuovo_seq()
        if self.comportamento == "rifiuta":
            self._manda(ws, "ack", {"ref": d["ref"], "seq": ack_seq, "accettato": False,
                                    "motivo": self.motivo, "ricevuto_ms": 1.0})
            return
        if d["ref"] in self.visti:
            self._manda(ws, "ack", {"ref": d["ref"], "seq": ack_seq, "accettato": True,
                                    "motivo": MO.MOTIVO_REF_GIA_VISTO, "ricevuto_ms": 1.0})
            return
        self.visti.add(d["ref"])
        self._manda(ws, "ack", {"ref": d["ref"], "seq": ack_seq, "accettato": True,
                                "motivo": None, "ricevuto_ms": 1.0})
        self._fine(ws, d)

    def _fine(self, ws: FintaWS, d: dict) -> None:
        if d["azione"] == "cancel":
            bet = str(d["bet_id"])
            cmd = self.per_bet.get(bet) or dict(d, ref="omega-t0", side="LAY", size=2.0,
                                                  price=3.0)
            m = self.matched_per_bet.get(bet, 0.0)
            self.evento(ws, cmd, "annullato", matched=m, remaining=0.0,
                        status="EXECUTION_COMPLETE", bet_id=bet, avg=cmd["price"])
            return
        bet = "3%011d" % next(_BET)
        self.per_bet[bet] = d
        self.evento(ws, d, "accettato_betfair", matched=0.0, remaining=d["size"],
                    status="EXECUTABLE", bet_id=bet)
        if self.parziale is not None:
            m = round(d["size"] * self.parziale, 2)
            self.matched_per_bet[bet] = m
            self.evento(ws, d, "abbinato_parziale", matched=m,
                        remaining=round(d["size"] - m, 2), status="EXECUTABLE",
                        bet_id=bet, avg=d["price"])
        if self.fase_finale == "abbinato":
            self.evento(ws, d, "abbinato", matched=d["size"], remaining=0.0,
                        status="EXECUTION_COMPLETE", bet_id=bet, avg=d["price"])
        elif self.fase_finale == "annullato":
            self.evento(ws, d, "annullato", matched=0.0, remaining=0.0,
                        status="EXECUTION_COMPLETE", bet_id=bet)


def _attendi(cond, timeout: float = 3.0) -> bool:
    fine = time.monotonic() + timeout
    while time.monotonic() < fine:
        if cond():
            return True
        time.sleep(0.01)
    return bool(cond())


@pytest.fixture
def motore(monkeypatch):
    """Interruttore ACCESO e la porta di Omega collegata al finto (thread vero)."""
    m = FintoMotore()
    monkeypatch.setenv(PO.ENV_CANALE, "1")
    monkeypatch.setattr(SPO, "MAX_ETA_MS", 400)
    monkeypatch.setattr(PO, "_crea_porta", lambda: PO.PortaCanaleOmega(
        porta_ws=47331, attore="omega", sport="calcio", connetti=m.connetti,
        token_fn=lambda: TOKEN))
    PO.azzera()
    porta = PO.porta_omega()
    assert _attendi(porta.disponibile)
    yield m
    PO.azzera()


@pytest.fixture
def spento(monkeypatch):
    """Interruttore SPENTO: la porta non deve MAI nascere."""
    monkeypatch.delenv(PO.ENV_CANALE, raising=False)

    def _vietato():
        raise AssertionError("porta creata a interruttore spento")

    monkeypatch.setattr(PO, "_crea_porta", _vietato)
    PO.azzera()
    yield
    PO.azzera()


class Mercato(FakeMarket):
    """FakeMarket storico + le firme vere di annullo e stato per bet_id."""

    def __init__(self, *a: Any, **k: Any) -> None:
        super().__init__(*a, **k)
        self.cancels: list = []
        self.stati: dict = {}
        self.current_orders: list = []
        self.cleared_orders: list = []

    def cancel_order_live(self, bet_id: str, market_id: str, size_reduction: Any = None):
        from Betfair.omega.omega_market import CancelResult

        self.cancels.append((bet_id, market_id, size_reduction))
        return CancelResult(ok=True, status="SUCCESS", bet_id=bet_id, size_cancelled=2.0,
                            riletto=True, size_matched=0.0, size_remaining=0.0)

    def order_state_by_bet_id(self, bet_id: str) -> dict:
        return self.stati.get(str(bet_id), {"found": False})


def _mercato() -> Mercato:
    return Mercato([_event()], _cs(), _open_snapshot())


def _poll(db, market, secondi: float, **params):
    return S.poll_flumine_pending(db=db, params=_params(**params),
                                  now=NOW + timedelta(seconds=secondi), market=market)


def _logs(db, kind):
    return [p for k, p in db.activity if k == kind]


def _pending(db):
    return [t for t in db.trades if t["status"] == "pending"]


# ===========================================================================
# 1. il comando di Omega: chiavi, validatore vero, adattamento
# ===========================================================================
def test_adatta_comando_chiavi_e_validatore_vero():
    base = SPO.costruisci_comando(ref="omega-t7", attore="omega", azione="place",
                                  mode="live", market_id="1.2", selection_id=3,
                                  side="lay", price=4.0, size=2.0, persistence="LAPSE",
                                  creato_ms=1.0,
                                  origine={"tabella": SPO.TABELLA_ORIGINE, "id": 7})
    d = PO.adatta_comando(base, time_in_force=PO.FOK, riduce=True)
    assert tuple(d.keys()) == PO.CHIAVI_COMANDO
    assert d["strategy_ref"] == "omega" and d["attore"] == "omega"
    assert d["origine"] == {"tabella": "omega_trades", "id": 7}
    assert d["time_in_force"] == "FILL_OR_KILL" and d["reduces_liability"] is True
    piano = MO.valida_comando("omega", d)
    assert piano["riduce"] is True and piano["riga"]["time_in_force"] == "FILL_OR_KILL"
    # (24/09 sera) la porta di Safe e' stata corretta: strategy_ref segue l'attore e
    # creato_ms e' intero, quindi il comando GREZZO passa la validazione del runner;
    # l'adattamento di Omega resta necessario per tabella d'origine, FOK e riduzione
    grezzo = MO.valida_comando("omega", base)
    assert grezzo["riga"].get("time_in_force") is None and not grezzo["riduce"]
    assert base["origine"]["tabella"] != PO.TABELLA_ORIGINE
    # cancel: ref di Omega, niente FOK ne' riduzione
    c = SPO.costruisci_comando(ref=SPO.ref_annullo("301"), attore="omega", azione="cancel",
                               mode="paper", market_id="1.2", bet_id="301", creato_ms=1.0)
    dc = PO.adatta_comando(c, time_in_force=PO.FOK, riduce=True)
    assert dc["ref"] == "omega-c301" and dc["time_in_force"] is None
    assert dc["reduces_liability"] is False
    MO.valida_comando("omega", dc)
    for sbagliato in ({"attore": "safe"}, {"ref": "safe-t7"}, {"mode": "LIVE"}):
        with pytest.raises(ValueError):
            PO.adatta_comando(dict(base, **sbagliato))
    with pytest.raises(ValueError):
        PO.adatta_comando(base, time_in_force="GOOD_TILL")


def test_ref_deterministico():
    assert PO.ref_ordine(42) == "omega-t42" == PO.ref_ordine("42")
    assert PO.ref_annullo("300123456789") == PO.ref_annullo("300123456789")
    assert len(PO.ref_annullo("300123456789012", 0.5)) <= 32


def test_vista_non_manda_un_comando_non_adattabile(motore):
    vista = PO.VistaOmega(PO.porta_esistente())
    base = SPO.costruisci_comando(ref="safe-t9", attore="omega", azione="place",
                                  mode="paper", market_id="1.2", selection_id=3,
                                  side="lay", price=4.0, size=2.0, creato_ms=1.0)
    ack = vista.invia(base)
    assert not ack.accettato and ack.motivo == PO.MOTIVO_NON_VALIDO
    assert motore.comandi == []


# ===========================================================================
# 2. interruttore SPENTO: byte per byte come oggi
# ===========================================================================
@pytest.mark.parametrize("valore", [None, "", "0", "no", "false", "off"])
def test_interruttore_spento_valori(monkeypatch, valore):
    if valore is None:
        monkeypatch.delenv(PO.ENV_CANALE, raising=False)
    else:
        monkeypatch.setenv(PO.ENV_CANALE, valore)
    monkeypatch.setattr(PO, "_crea_porta", lambda: (_ for _ in ()).throw(AssertionError()))
    PO.azzera()
    assert PO.porta_omega() is None
    assert S._porta_per(_params(), "live") is None
    assert S._porta_kw_chiusura(_params(), "paper") == {}
    assert S._porta_kw_annullo({"mode": "live"}) == {}
    assert not S.avvia_porta_ordini()


def test_spento_parita_apertura_paper_coda(spento):
    db = FakeQueueDB(_control(mode="paper"))
    market = _mercato()
    S.run_once(market=market, db=db, now=NOW)
    t = db.trades[0]
    assert t["meta"]["phase"] == "flumine_wait" and "canale_ref" not in t["meta"]
    payload = db.queue[t["meta"]["flumine_request_id"]]["payload"]
    assert payload["client_ref"] == "omega-t%d" % t["id"]
    assert payload["mode"] == "paper" and "time_in_force" not in payload
    assert market.placed == []


def test_spento_parita_apertura_live_coda_e_rest(spento):
    db = FakeQueueDB(_control(mode="live"), hb_mode="LIVE")
    market = _mercato()
    S.run_once(market=market, db=db, now=NOW)
    payload = db.queue[db.trades[0]["meta"]["flumine_request_id"]]["payload"]
    assert payload["time_in_force"] == "FILL_OR_KILL" and payload["mode"] == "live"
    # runner non LIVE: il REST FOK di sempre
    db2 = FakeQueueDB(_control(mode="live"), hb_mode="PAPER")
    m2 = _mercato()
    S.run_once(market=m2, db=db2, now=NOW)
    assert len(m2.placed) == 1 and db2.queue == {}
    assert db2.trades[0]["status"] == "open"


def test_spento_chiusure_e_annulli_senza_kwarg_nuovi(spento, monkeypatch):
    visti: dict = {"close": [], "annulla": []}
    vero_close, vero_annulla = X.close_trade, X.annulla_su_betfair

    def _close(**kw):
        visti["close"].append(set(kw))
        return vero_close(**kw)

    def _annulla(*a, **kw):
        visti["annulla"].append(set(kw))
        return vero_annulla(*a, **kw)

    monkeypatch.setattr(X, "close_trade", _close)
    monkeypatch.setattr(X, "annulla_su_betfair", _annulla)
    from Betfair.omega.test_omega_cashout_manuale_fallito_2026_09_23 import _MercatoOK

    db = _DB({"status": "idle", "params": {}})
    tr = _trade(db, price=55.0, size=5.0)
    out = S._manual_cashout(market=_MercatoOK([], None, None), db=db,
                            payload={"trade_id": tr["id"]}, now=NOW)
    assert out.get("ok") is True, out
    riga = {"id": 99, "bet_id": "B1", "mode": "live", "market_id": "1.2", "event_id": "e"}
    m = _mercato()
    assert S._ordine_ancora_vivo(m, riga, db=db, now=NOW) is False
    assert visti["close"] and all("porta" not in k for k in visti["close"])
    assert visti["annulla"] == [{"bet_id", "market_id"}]
    assert m.cancels == [("B1", "1.2", None)]


# ===========================================================================
# 3. aperture sul canale
# ===========================================================================
def test_apertura_paper_comando_giusto_e_conferma_da_evento(motore):
    db = FakeQueueDB(_control(mode="paper"))
    market = _mercato()
    S.run_once(market=market, db=db, now=NOW)
    t = db.trades[0]
    assert t["status"] == "pending" and t["meta"]["canale_ref"] == "omega-t%d" % t["id"]
    assert db.queue == {} and market.placed == []           # nessun altro trasporto
    cmd = motore.comandi[-1]
    assert (cmd["ref"], cmd["attore"], cmd["azione"], cmd["mode"]) == \
        ("omega-t%d" % t["id"], "omega", "place", "paper")
    assert (cmd["market_id"], cmd["selection_id"], cmd["side"]) == \
        (t["market_id"], t["selection_id"], "LAY")
    assert (cmd["price"], cmd["size"], cmd["persistence"]) == (t["price"], t["size"], "LAPSE")
    assert cmd["time_in_force"] is None                     # paper: TTL come la coda
    assert cmd["reduces_liability"] is False
    assert cmd["origine"] == {"tabella": "omega_trades", "id": t["id"]}
    porta = PO.porta_esistente()
    assert _attendi(lambda: PO.terminale(porta.esiti(cmd["ref"]) or {}))
    assert _poll(db, market, 2) == 1
    t = db.trades[0]
    assert t["status"] == "open" and t["size"] == cmd["size"] and t["bet_id"]
    assert "reason" not in t["meta"]                        # non piu' in riconciliazione
    assert len(motore.comandi) == 1


def test_apertura_live_porta_il_fok_e_conferma(motore):
    db = FakeQueueDB(_control(mode="live"), hb_mode="LIVE")
    market = _mercato()
    S.run_once(market=market, db=db, now=NOW)
    cmd = motore.comandi[-1]
    assert cmd["mode"] == "live" and cmd["time_in_force"] == "FILL_OR_KILL"
    assert cmd["reduces_liability"] is False
    assert db.queue == {} and market.placed == []
    porta = PO.porta_esistente()
    assert _attendi(lambda: PO.terminale(porta.esiti(cmd["ref"]) or {}))
    assert _poll(db, market, 1) == 1
    t = db.trades[0]
    assert t["status"] == "open" and t["mode"] == "live" and t["bet_id"]


def test_fok_ucciso_riga_errore_gamba_ritentabile(motore):
    motore.fase_finale = "annullato"
    db = FakeQueueDB(_control(mode="live"), hb_mode="LIVE")
    market = _mercato()
    S.run_once(market=market, db=db, now=NOW)
    ref = motore.comandi[-1]["ref"]
    assert _attendi(lambda: PO.terminale(PO.porta_esistente().esiti(ref) or {}))
    _poll(db, market, 1)
    t = db.trades[0]
    assert t["status"] == "error" and t["meta"]["leg_failed"] is True
    assert t["meta"]["reason"] == "flumine_canale_annullato"


def test_ack_rifiutato_nessun_ordine_nessun_secondo_invio(motore):
    motore.comportamento = "rifiuta"
    db = FakeQueueDB(_control(mode="live"), hb_mode="LIVE")
    market = _mercato()
    S.run_once(market=market, db=db, now=NOW)
    assert len(motore.comandi) == 1
    assert db.trades == []                                  # riserva cancellata (certo)
    skip = [p for p in _logs(db, "skip") if p.get("percorso") == "canale"]
    assert skip and skip[0]["reason"] == "canale_rifiutato:kill_switch"
    assert market.placed == [] and db.queue == {}


def test_ack_mancante_nessun_ripiego_poi_riconciliazione_per_mercato(motore):
    motore.comportamento = "muto"
    db = FakeQueueDB(_control(mode="live"), hb_mode="LIVE")
    market = _mercato()
    S.run_once(market=market, db=db, now=NOW)
    t = db.trades[0]
    assert t["status"] == "pending" and t["meta"]["canale_esito_ignoto"] is True
    assert market.placed == [] and db.queue == {} and len(motore.comandi) == 1
    # dentro la scadenza: si aspetta, nessun invio, nessuna lettura Betfair
    assert _poll(db, market, 5) == 0
    assert len(motore.comandi) == 1 and market.placed == []
    # il reconcile REST NON la tocca (e' del poll)
    S.reconcile_pending(market=market, db=db, now=NOW + timedelta(seconds=500))
    assert db.trades[0]["status"] == "pending"
    # oltre la scadenza: Betfair per mercato/selezione/lato, poi per bet_id
    market.current_orders = [{"bet_id": "B77", "market_id": t["market_id"],
                              "selection_id": t["selection_id"], "side": "lay",
                              "status": "EXECUTION_COMPLETE", "size_matched": t["size"],
                              "size_remaining": 0.0, "customer_order_ref": "awlq-x"}]
    market.stati["B77"] = {"found": True, "size_matched": t["size"],
                           "avg_price_matched": t["price"], "size_remaining": 0.0,
                           "matched_date": None, "placed_date": None}
    assert _poll(db, market, 25) == 1
    t = db.trades[0]
    assert t["status"] == "open" and t["bet_id"] == "B77" and market.placed == []
    assert len(motore.comandi) == 1


def test_ack_mancante_nessun_ordine_su_betfair_errore_solo_dopo_la_grazia(motore):
    motore.comportamento = "muto"
    db = FakeQueueDB(_control(mode="live"), hb_mode="LIVE")
    market = _mercato()
    S.run_once(market=market, db=db, now=NOW)
    assert _poll(db, market, 25) == 0                       # grazia di propagazione
    assert db.trades[0]["status"] == "pending"
    assert _poll(db, market, 200) == 1
    t = db.trades[0]
    assert t["status"] == "error" and t["meta"]["reason"] == "flumine_canale_mai_visto_su_betfair"


def test_ack_mancante_candidati_ambigui_resta_in_verifica(motore):
    motore.comportamento = "muto"
    db = FakeQueueDB(_control(mode="live"), hb_mode="LIVE")
    market = _mercato()
    S.run_once(market=market, db=db, now=NOW)
    t = db.trades[0]
    base = {"market_id": t["market_id"], "selection_id": t["selection_id"], "side": "lay"}
    market.current_orders = [dict(base, bet_id="B1"), dict(base, bet_id="B2")]
    assert _poll(db, market, 500) == 0
    assert db.trades[0]["status"] == "pending"
    assert _logs(db, "flumine_live_orphan")


def test_canale_giu_apertura_non_inviata_nessun_ripiego(motore):
    PO.porta_esistente().ferma()
    motore.rifiuta_connessione = True
    assert _attendi(lambda: not PO.porta_esistente().disponibile())
    db = FakeQueueDB(_control(mode="live"), hb_mode="LIVE")
    market = _mercato()
    S.run_once(market=market, db=db, now=NOW)
    assert motore.comandi == [] and market.placed == [] and db.queue == {}
    assert db.trades == []
    assert any(p.get("reason") == "canale_giu:apertura_non_inviata"
               for p in _logs(db, "skip"))


def test_parametri_rest_rispettati_anche_ad_interruttore_acceso(motore):
    db = FakeQueueDB(_control(mode="live", params={"omega_live_via_flumine": False}),
                     hb_mode="LIVE")
    market = _mercato()
    S.run_once(market=market, db=db, now=NOW)
    assert motore.comandi == [] and len(market.placed) == 1


def test_manuale_live_via_canale(motore):
    db = FakeQueueDB(_control(status="idle", mode="live"), hb_mode="LIVE")
    db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-1.100",
                                  "selection_id": 4, "side": "lay", "mode": "live",
                                  "price": 110, "size": 2})
    market = _mercato()
    S.run_once(market=market, db=db, now=NOW)
    assert db.manual_reqs[0]["result"]["pending_fill"] is True
    cmd = motore.comandi[-1]
    assert cmd["mode"] == "live" and cmd["time_in_force"] == "FILL_OR_KILL"
    assert (cmd["selection_id"], cmd["price"], cmd["size"]) == (4, 110.0, 2.0)
    assert market.placed == [] and db.queue == {}


# ===========================================================================
# 4. esiti: intermedi, altra modalita', seq, TTL paper, da_seq
# ===========================================================================
def test_evento_intermedio_aggiorna_la_consapevolezza(motore):
    motore.fase_finale = None
    motore.parziale = 0.5
    db = FakeQueueDB(_control(mode="live"), hb_mode="LIVE")
    market = _mercato()
    S.run_once(market=market, db=db, now=NOW)
    ref = motore.comandi[-1]["ref"]
    porta = PO.porta_esistente()
    assert _attendi(lambda: (porta.esiti(ref) or {}).get("fase") == "abbinato_parziale")
    assert _poll(db, market, 2) == 0
    t = db.trades[0]
    assert t["status"] == "pending" and t["bet_id"]
    assert t["meta"]["canale_fase"] == "abbinato_parziale"
    assert t["size_matched"] == round(motore.comandi[-1]["size"] * 0.5, 2)
    assert t["size_remaining"] > 0


def test_evento_di_altra_modalita_ignorato(motore):
    motore.comportamento = "muto"
    db = FakeQueueDB(_control(mode="paper"))
    market = _mercato()
    S.run_once(market=market, db=db, now=NOW)
    cmd = motore.comandi[-1]
    finto = riga_specchio_vera(mode="live", bet_id="999", size=cmd["size"],
                               price=cmd["price"], side="LAY", matched=cmd["size"],
                               remaining=0.0, status="EXECUTION_COMPLETE", avg=cmd["price"])
    finto.update({"ref": cmd["ref"], "seq": 50, "fase": "abbinato", "esito_ms": 1.0})
    assert PO.porta_esistente().memoria.ricevi_evento(finto)
    assert _poll(db, market, 2) == 0
    t = db.trades[0]
    assert t["status"] == "pending" and not t.get("bet_id")


def test_evento_piu_vecchio_non_sostituisce(motore):
    db = FakeQueueDB(_control(mode="live"), hb_mode="LIVE")
    tid = db.insert_trade({"event_id": "E9", "market_id": "1.9", "selection_id": 5,
                           "side": "lay", "mode": "live", "status": "pending",
                           "price": 4.0, "size": 2.0, "liability": 6.0,
                           "meta": {"canale_ref": "omega-t999", "canale_seq": 10,
                                    "canale_fase": "abbinato_parziale"}})
    tr = db.get_trade(tid)
    vecchio = {"ref": "omega-t999", "seq": 5, "fase": "accettato_betfair", "mode": "live",
               "bet_id": "VECCHIO", "size": 2.0, "size_matched": 0.0, "size_remaining": 2.0}
    S._aggiorna_da_evento(tr, vecchio, db=db)
    assert db.get_trade(tid)["meta"]["canale_seq"] == 10 and not db.get_trade(tid).get("bet_id")


def test_paper_al_ttl_annulla_il_residuo_sul_canale(motore):
    motore.fase_finale = None
    motore.parziale = 0.5
    db = FakeQueueDB(_control(mode="paper"))
    market = _mercato()
    S.run_once(market=market, db=db, now=NOW)
    place = motore.comandi[-1]
    porta = PO.porta_esistente()
    assert _attendi(lambda: (porta.esiti(place["ref"]) or {}).get("fase") == "abbinato_parziale")
    assert _poll(db, market, 10) == 0                        # dentro il TTL
    assert len(motore.comandi) == 1
    assert _poll(db, market, 50) == 1                        # TTL 45 s: cancel e conferma
    cancel = motore.comandi[-1]
    assert cancel["azione"] == "cancel" and cancel["mode"] == "paper"
    assert cancel["ref"].startswith("omega-c") and market.cancels == []
    t = db.trades[0]
    assert t["status"] == "open" and t["size"] == round(place["size"] * 0.5, 2)


def test_paper_senza_esito_nessun_fill_inventato(motore):
    motore.comportamento = "muto"
    db = FakeQueueDB(_control(mode="paper"))
    market = _mercato()
    S.run_once(market=market, db=db, now=NOW)
    assert _poll(db, market, 50) == 0
    S.reconcile_pending(market=market, db=db, now=NOW + timedelta(seconds=60))
    assert db.trades[0]["status"] == "pending"               # il reconcile paper non conferma
    assert _poll(db, market, 200) == 1
    t = db.trades[0]
    assert t["status"] == "error" and t["meta"]["reason"] == "flumine_canale_senza_esito"


def test_da_seq_alla_riconnessione_recupera_l_esito(motore):
    motore.manda_eventi = False                              # esiti persi sulla prima connessione
    db = FakeQueueDB(_control(mode="live"), hb_mode="LIVE")
    market = _mercato()
    S.run_once(market=market, db=db, now=NOW)
    ref = motore.comandi[-1]["ref"]
    porta = PO.porta_esistente()
    assert porta.esiti(ref) is None and porta.memoria.seq_visto >= 1
    motore.manda_eventi = True
    motore.connessioni[-1].chiusa = True                     # il runner cade e torna
    assert _attendi(lambda: PO.terminale(porta.esiti(ref) or {}), timeout=5.0)
    assert motore.da_seq and motore.da_seq[-1] >= 1
    assert _poll(db, market, 2) == 1 and db.trades[0]["status"] == "open"


# ===========================================================================
# 5. chiusure (cash out / green-up) e annulli
# ===========================================================================
def _cashout(db, tr):
    from Betfair.omega.test_omega_cashout_manuale_fallito_2026_09_23 import _MercatoOK

    return S._manual_cashout(market=_MercatoOK([], None, None), db=db,
                             payload={"trade_id": tr["id"]}, now=NOW)


def test_cashout_manda_fok_e_reduces_liability(motore):
    db = _DB({"status": "idle", "params": {}})
    tr = _trade(db, price=55.0, size=5.0)
    out = _cashout(db, tr)
    assert out.get("ok") is True and out.get("pending_fill") is True, out
    cmd = motore.comandi[-1]
    chiusura = next(t for t in db.trades if t.get("closes_trade_id") == tr["id"])
    assert cmd["ref"] == "omega-t%d" % chiusura["id"] and cmd["side"] == "BACK"
    assert cmd["time_in_force"] == "FILL_OR_KILL" and cmd["reduces_liability"] is True
    assert cmd["mode"] == "paper" and cmd["market_id"] == CS_MID
    assert cmd["origine"] == {"tabella": "omega_trades", "id": chiusura["id"]}
    porta = PO.porta_esistente()
    assert _attendi(lambda: PO.terminale(porta.esiti(cmd["ref"]) or {}))
    _poll(db, _mercato(), 2)
    assert db.get_trade(chiusura["id"])["status"] == "open"


def test_cashout_a_canale_giu_usa_il_trasporto_di_oggi(motore):
    PO.porta_esistente().ferma()
    motore.rifiuta_connessione = True
    assert _attendi(lambda: not PO.porta_esistente().disponibile())
    db = _DB({"status": "idle", "params": {}})
    tr = _trade(db, price=55.0, size=5.0)
    out = _cashout(db, tr)
    assert out.get("ok") is True, out
    assert motore.comandi == []
    chiusura = next(t for t in db.trades if t.get("closes_trade_id") == tr["id"])
    assert chiusura["status"] == "open"                      # fill paper di sempre
    assert _logs(db, "canale_giu_ripiego")


def _riga_viva(db, mode="live"):
    tid = db.insert_trade({"event_id": "E5", "market_id": "1.5", "selection_id": 7,
                           "side": "lay", "mode": mode, "status": "pending", "price": 3.0,
                           "size": 2.0, "liability": 4.0, "bet_id": "B500",
                           "meta": {"canale_ref": "omega-t777"}})
    return db.get_trade(tid)


def test_annullo_live_sul_canale(motore):
    db = FakeQueueDB(_control(mode="live"))
    m = _mercato()
    tr = _riga_viva(db)
    assert S._ordine_ancora_vivo(m, tr, db=db, now=NOW, ignoto_e_vivo=True) is False
    cmd = motore.comandi[-1]
    assert (cmd["azione"], cmd["ref"], cmd["bet_id"], cmd["mode"]) == \
        ("cancel", "omega-cB500", "B500", "live")
    assert m.cancels == []


def test_annullo_live_senza_ack_ripiega_sul_rest(motore):
    motore.comportamento = "muto"
    db = FakeQueueDB(_control(mode="live"))
    m = _mercato()
    tr = _riga_viva(db)
    S._ordine_ancora_vivo(m, tr, db=db, now=NOW, ignoto_e_vivo=True)
    assert len(motore.comandi) == 1 and m.cancels == [("B500", "1.5", None)]


def test_annullo_paper_senza_ack_mai_rest(motore):
    motore.comportamento = "muto"
    db = FakeQueueDB(_control(mode="paper"))
    m = _mercato()
    tr = _riga_viva(db, mode="paper")
    assert S._ordine_ancora_vivo(m, tr, db=db, now=NOW, ignoto_e_vivo=True) is True
    assert m.cancels == []
