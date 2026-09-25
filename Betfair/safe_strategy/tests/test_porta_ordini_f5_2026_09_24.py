"""F5 (24/09) - Safe calcio: la PORTA degli ordini sul canale di comando del runner.

Protocollo "COMANDO ORDINE" (contratto del coordinatore): ``/comando/safe`` su
47331, header ``X-Canale-Token``, busta ``{"t":..., "d":{...}}``, ``comando`` ->
``ack`` -> eventi ``order`` con ``seq``, ``da_seq`` alla riconnessione.

Il FINTO del motore del runner VALIDA ogni comando con la funzione VERA
(``Betfair/stream/motore_ordini.py::valida_comando``, lo stesso modulo che il
runner monta in produzione — vedi il test di contratto sulle chiavi): un
comando che il runner rifiuterebbe davvero (``creato_ms`` float,
``strategy_ref`` diverso dall'attore, chiave mancante) fa fallire il test. Le
righe degli eventi ``order`` del finto NON sono scritte a mano: nascono dalla
``LiveTradingStrategy._order_row`` VERA (piu' ``updated_at`` di
``db.upsert_live_order`` e le quattro chiavi del protocollo), e un test di
contratto lo verifica.

Difetti 24/09 (referto del delegato che ha costruito la porta di Omega,
``Betfair/omega/porta_ordini.py::adatta_comando``, corretti qui):
``creato_ms`` float (respinto da ``motore_ordini._intero``), ``strategy_ref``
fisso a "safe" (respinto per l'attore ``safe_tennis``), chiusure via canale
senza ``time_in_force``/``reduces_liability`` (la coda flumine li mette gia'
oggi, vedi ``execution.enqueue_place``). Piu' le fasi INTERMEDIE del
place-and-trim (``parcheggiato``/``ridotto``), mai terminali.

Ogni test e' falsificato (vedi il referto del delegato): ref casuale, ripiego
automatico su una place, mode ereditato, seq ignorato, interruttore ignorato.
ASCII-only.
"""
from __future__ import annotations

import itertools
import json
import queue
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Optional

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy import porta_ordini as PO
from Betfair.stream import motore_ordini as MO

NOW = datetime(2026, 9, 24, 20, 0, tzinfo=timezone.utc)
TOKEN = "tok-di-prova"
_IDS = itertools.count(1)


# ---------------------------------------------------------------------------
# la riga dello specchio VERA (encoder di produzione)
# ---------------------------------------------------------------------------
class _Enum:
    def __init__(self, name: str) -> None:
        self.name = name


def _ordine_flumine(*, bet_id: str, size: float, price: float, side: str,
                    matched: float, remaining: float, status: str,
                    ref: str = "awlq0", avg: float = 0.0) -> Any:
    ot = SimpleNamespace(ORDER_TYPE=_Enum("LIMIT"), price=price, size=size,
                         persistence_type="LAPSE")
    return SimpleNamespace(
        order_type=ot, side=side, context={"customer_order_ref": ref}, notes=None,
        responses=SimpleNamespace(date_time_placed=NOW),
        size_matched=matched, date_time_status_update=NOW + timedelta(milliseconds=5),
        bet_id=bet_id, market_id="1.234", selection_id=47972, handicap=0.0,
        size_remaining=remaining, size_cancelled=round(size - matched - remaining, 2),
        size_lapsed=0.0, size_voided=0.0, average_price_matched=avg,
        status=_Enum(status))


def riga_specchio_vera(*, mode: str, bet_id: str, size: float, price: float, side: str,
                       matched: float, remaining: float, status: str, avg: float = 0.0
                       ) -> dict:
    from Betfair.stream.engine.live_trading_strategy import LiveTradingStrategy

    riga = LiveTradingStrategy._order_row(
        SimpleNamespace(mode=mode),
        _ordine_flumine(bet_id=bet_id, size=size, price=price, side=side, matched=matched,
                        remaining=remaining, status=status, avg=avg),
        event_id="35760084", market_id="1.234")
    riga = dict(riga)
    riga["updated_at"] = (NOW + timedelta(milliseconds=6)).isoformat()   # upsert_live_order
    return riga


# ---------------------------------------------------------------------------
# il FINTO del motore del runner: parla il protocollo esatto
# ---------------------------------------------------------------------------
class FintaChiusa(Exception):
    pass


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
            raise FintaChiusa("socket chiuso")
        self.motore.gestisci(self, testo)

    def recv(self, timeout: Optional[float] = None) -> str:
        fine = time.monotonic() + (timeout or 0.0)
        while True:
            if self.chiusa:
                raise FintaChiusa("socket chiuso")
            try:
                return self.uscita.get(timeout=0.02)
            except queue.Empty:
                if time.monotonic() >= fine:
                    raise TimeoutError()

    def close(self) -> None:
        self.chiusa = True


class FintoMotore:
    """Lato runner. ``comportamento``: 'accetta' | 'rifiuta' | 'muto' |
    'muto_con_esito' (ack perso, esito arrivato). ``fase_finale``: 'abbinato' |
    'annullato' | None (nessun esito terminale). ``parziale``: size abbinata
    prima della fine (evento ``abbinato_parziale``)."""

    def __init__(self, *, comportamento: str = "accetta", fase_finale: Optional[str] = "abbinato",
                 motivo: str = "kill_switch", parziale: Optional[float] = None,
                 attore: str = "safe") -> None:
        self.comportamento = comportamento
        self.fase_finale = fase_finale
        self.motivo = motivo
        self.parziale = parziale
        # l'attore REGISTRATO nel motore per questa porta (``safe`` calcio,
        # ``safe_tennis`` tennis): usato per il percorso ``/comando/<attore>``
        # e per validare i comandi con la funzione VERA del runner.
        self.attore = attore
        self.connessioni: list[FintaWS] = []
        self.comandi: list[dict] = []
        self.buste: list[dict] = []
        self.da_seq: list[int] = []
        self.seq = 0
        self.eventi: list[dict] = []
        self.visti: set = set()
        self._lock = threading.Lock()
        self.rifiuta_connessione = False

    # -- connessione -------------------------------------------------------
    def connetti(self, url: str, headers: dict) -> FintaWS:
        if self.rifiuta_connessione:
            raise ConnectionRefusedError("runner giu'")
        ws = FintaWS(self, url, headers)
        if headers.get(PO.HEADER_TOKEN) != TOKEN or not url.endswith("/comando/%s" % self.attore):
            raise PermissionError("token o percorso errato: chiusura")
        self.connessioni.append(ws)
        return ws

    def attuale(self) -> FintaWS:
        return self.connessioni[-1]

    # -- protocollo --------------------------------------------------------
    def _manda(self, ws: FintaWS, t: str, d: dict) -> None:
        ws.uscita.put(json.dumps({"t": t, "d": d}))

    def _nuovo_seq(self) -> int:
        self.seq += 1
        return self.seq

    def evento(self, ws: Optional[FintaWS], cmd: dict, fase: str, *, matched: float,
               remaining: float, status: str, avg: float = 0.0,
               bet_id: str = "3000000001", manda: bool = True) -> dict:
        riga = riga_specchio_vera(mode=cmd["mode"], bet_id=bet_id, size=cmd["size"] or 0.0,
                                  price=cmd["price"] or 0.0, side=(cmd["side"] or "LAY"),
                                  matched=matched, remaining=remaining, status=status, avg=avg)
        with self._lock:
            riga.update({"ref": cmd["ref"], "seq": self._nuovo_seq(), "fase": fase,
                         "esito_ms": round(time.time() * 1000.0, 1)})
            self.eventi.append(riga)
        if manda and ws is not None:
            self._manda(ws, "order", riga)
        return riga

    def gestisci(self, ws: FintaWS, testo: str) -> None:
        msg = json.loads(testo)
        self.buste.append(msg)
        t, d = msg.get("t"), msg.get("d")
        if t == "da_seq":
            n = int(d["seq"])
            self.da_seq.append(n)
            for e in list(self.eventi):
                if e["seq"] > n:
                    self._manda(ws, "order", e)
            return
        assert t == "comando", t
        # CONTRATTO: tutte e sole le chiavi del protocollo, e il validatore
        # VERO del runner (un comando che il motore rifiuterebbe fa fallire
        # il test, non solo il finto)
        assert tuple(d.keys()) == PO.CHIAVI_COMANDO, list(d.keys())
        MO.valida_comando(self.attore, d)
        self.comandi.append(d)
        if self.comportamento in ("muto", "muto_con_esito"):
            if self.comportamento == "muto_con_esito":
                self._fine(ws, d)
            return
        with self._lock:
            ack_seq = self._nuovo_seq()
        if self.comportamento == "rifiuta":
            self._manda(ws, "ack", {"ref": d["ref"], "seq": ack_seq, "accettato": False,
                                    "motivo": self.motivo, "ricevuto_ms": 1.0})
            return
        if d["ref"] in self.visti:
            self._manda(ws, "ack", {"ref": d["ref"], "seq": ack_seq, "accettato": False,
                                    "motivo": PO.MOTIVO_REF_GIA_VISTO, "ricevuto_ms": 1.0})
            return
        self.visti.add(d["ref"])
        self._manda(ws, "ack", {"ref": d["ref"], "seq": ack_seq, "accettato": True,
                                "motivo": None, "ricevuto_ms": 1.0})
        self._fine(ws, d)

    def _fine(self, ws: FintaWS, d: dict) -> None:
        if d["azione"] == "cancel":
            cmd = dict(d, size=2.0, price=3.0, side="LAY", ref="safe-t5")
            self.evento(ws, cmd, "annullato", matched=0.0, remaining=0.0,
                        status="EXECUTION_COMPLETE", bet_id=str(d["bet_id"]))
            return
        self.evento(ws, d, "accettato_betfair", matched=0.0, remaining=d["size"],
                    status="EXECUTABLE")
        if self.parziale is not None:
            self.evento(ws, d, "abbinato_parziale", matched=self.parziale,
                        remaining=round(d["size"] - self.parziale, 2), status="EXECUTABLE",
                        avg=d["price"])
        if self.fase_finale == "abbinato":
            self.evento(ws, d, "abbinato", matched=d["size"], remaining=0.0,
                        status="EXECUTION_COMPLETE", avg=d["price"])
        elif self.fase_finale == "annullato":
            self.evento(ws, d, "annullato", matched=0.0, remaining=0.0,
                        status="EXECUTION_COMPLETE")


def _attendi(cond, timeout: float = 3.0) -> bool:
    fine = time.monotonic() + timeout
    while time.monotonic() < fine:
        if cond():
            return True
        time.sleep(0.01)
    return bool(cond())


@pytest.fixture
def porta_e_motore(monkeypatch):
    """Una PortaCanale collegata al finto (thread vero, nessun socket)."""
    monkeypatch.setattr(PO, "MAX_ETA_MS", 400)
    motore = FintoMotore(attore="safe")
    porta = PO.PortaCanale(porta_ws=47331, attore="safe", connetti=motore.connetti,
                           token_fn=lambda: TOKEN)
    porta.avvia()
    assert _attendi(porta.disponibile)
    yield porta, motore
    porta.ferma()


@pytest.fixture
def porta_e_motore_tennis(monkeypatch):
    """Come ``porta_e_motore`` ma per l'attore Safe TENNIS: il motore lo
    registra come attore SEPARATO da ``safe`` (``ATTORI_COMANDO`` di
    ``motore_ordini.py``), quindi ``strategy_ref`` deve seguirlo, non restare
    fisso a "safe" (difetto 2)."""
    monkeypatch.setattr(PO, "MAX_ETA_MS", 400)
    motore = FintoMotore(attore="safe_tennis")
    porta = PO.PortaCanale(porta_ws=47332, attore="safe_tennis", connetti=motore.connetti,
                           token_fn=lambda: TOKEN)
    porta.avvia()
    assert _attendi(porta.disponibile)
    yield porta, motore
    porta.ferma()


# ---------------------------------------------------------------------------
# i finti del bot: stesse firme di bot_db / omega_market
# ---------------------------------------------------------------------------
class FakeDB:
    def __init__(self) -> None:
        self.trades: list[dict] = []
        self.activity: list[tuple] = []
        self.chiamate: list[tuple] = []
        self.queue: list[dict] = []
        self._id = 0

    def log(self, kind: str, payload: Optional[dict] = None) -> None:
        self.activity.append((kind, payload or {}))

    def insert_trade(self, trade: dict) -> Optional[int]:
        # id UNICI in tutto il file, come la sequenza vera della tabella: due
        # FakeDB che riusano l'id 1 farebbero collidere i ref sul runner finto
        self._id = next(_IDS)
        row = dict(trade)
        row["id"] = self._id
        row.setdefault("placed_at", NOW.isoformat())
        self.trades.append(row)
        return self._id

    def update_trade(self, trade_id: int, **fields: Any) -> None:
        self.chiamate.append(("update_trade", int(trade_id), dict(fields)))
        for t in self.trades:
            if t["id"] == int(trade_id):
                t.update(fields)

    def delete_trade(self, trade_id: int) -> None:
        self.trades = [t for t in self.trades if t["id"] != int(trade_id)]

    def get_trade(self, trade_id: int) -> Optional[dict]:
        return next((t for t in self.trades if t["id"] == int(trade_id)), None)

    def list_trades(self, status: Optional[str] = None) -> list[dict]:
        return [t for t in self.trades if status is None or t.get("status") == status]

    def closing_trades_for(self, trade_ids: list) -> list[dict]:
        ids = {int(i) for i in trade_ids}
        return [t for t in self.trades if t.get("closes_trade_id") in ids]

    # coda del runner: NON deve essere toccata sul percorso del canale
    def live_follow_status(self, event_id: str) -> Optional[str]:
        return "STREAMING"

    def runner_heartbeat(self) -> Optional[dict]:
        return {"ts": NOW.isoformat(), "mode": "LIVE+PAPER"}

    def enqueue_live_order(self, payload: dict) -> Optional[int]:
        self.queue.append(payload)
        return len(self.queue)

    def get_live_order_request_by_ref(self, client_ref: str) -> Optional[dict]:
        return None

    def get_live_order_request(self, request_id: int) -> Optional[dict]:
        return None

    def get_live_order_mirror(self, client_order_ref: str, mode: str = "paper") -> Optional[dict]:
        return None

    def revoke_live_order_request(self, request_id: int) -> bool:
        return True


class FakeMarket:
    """Stesse firme di ``omega_market`` (keyword, customer_ref)."""

    def __init__(self) -> None:
        self.placed: list[dict] = []
        self.cancels: list[tuple] = []
        self.list_calls = 0
        self.current: list[dict] = []
        self.cleared: list[dict] = []

    def place_order_live(self, **kw: Any) -> Any:
        self.placed.append(kw)
        return SimpleNamespace(ok=True, bet_id="REST1", size_matched=kw["size"],
                               avg_price_matched=kw["price"], order_status="EXECUTION_COMPLETE",
                               size_requested=kw["size"], size_remaining=0.0,
                               error_code=None, betfair_updated_at=None)

    def place_submin_live(self, **kw: Any) -> Any:
        return self.place_order_live(**kw)

    def cancel_order_live(self, bet_id: str, market_id: str, size_reduction: Any = None) -> Any:
        self.cancels.append((bet_id, market_id, size_reduction))
        from Betfair.omega.omega_market import CancelResult
        return CancelResult(ok=True, status="SUCCESS", bet_id=bet_id, size_cancelled=2.0,
                            riletto=True, size_matched=0.0, size_remaining=0.0)

    def list_current_orders(self, *a: Any, **k: Any) -> list[dict]:
        self.list_calls += 1
        return list(self.current)

    def list_cleared_orders(self, *a: Any, **k: Any) -> list[dict]:
        return list(self.cleared)

    def order_state_by_bet_id(self, bet_id: str) -> Optional[dict]:
        return None


def _riserva(db: FakeDB, *, mode: str = "paper", side: str = "lay", price: float = 3.0,
             size: float = 2.0, closes: Optional[int] = None, sport: str = "calcio") -> dict:
    riga = {"event_id": "35760084", "sport": sport, "market_id": "1.234",
            "selection_id": 47972, "side": side, "mode": mode, "price": price, "size": size,
            "status": "pending", "strategy": "base", "origin": "auto",
            "meta": {"phase": "reserved"}}
    if closes is not None:
        riga["closes_trade_id"] = closes
        riga["meta"] = {"phase": "reserved", "cashout": True, "closes_trade_id": closes}
    tid = db.insert_trade(riga)
    return db.get_trade(tid)


def _place(db, market, porta, tr, **extra) -> X.PlaceOutcome:
    # F1 (25/09): ref sport-aware come lo costruisce DAVVERO
    # ``bot_service._execute`` (``porta_ordini.ref_ordine``), non piu' un
    # "safe-t<id>" fisso — una riga tennis (``tr["sport"] == "tennis"``)
    # riceve il ref col prefisso dell'attore ``safe_tennis``.
    ref = extra.pop("client_ref", None) or PO.ref_ordine(
        tr["id"], sport=str(tr.get("sport") or "calcio"))
    return X.place(db=db, market=market, mode=tr["mode"], event_id=tr["event_id"],
                   market_id=tr["market_id"], selection_id=tr["selection_id"],
                   side=tr["side"], price=tr["price"], size=tr["size"], best_size=100.0,
                   ladder=((tr["price"], 100.0),), client_ref=ref,
                   trade_id=tr["id"], meta=dict(tr.get("meta") or {}), now=NOW,
                   params={}, porta=porta, **extra)


# ===========================================================================
# 1. il comando: chiavi esatte, ref deterministico, mode della riga
# ===========================================================================
def test_comando_ha_tutte_e_sole_le_chiavi_del_protocollo():
    d = PO.costruisci_comando(ref="safe-t7", attore="safe", azione="place", mode="paper",
                              market_id="1.234", selection_id=47972, side="lay", price=3.0,
                              size=2.0, persistence="LAPSE", creato_ms=1.0,
                              origine={"tabella": PO.TABELLA_ORIGINE, "id": 7})
    assert tuple(d.keys()) == PO.CHIAVI_COMANDO
    assert d["side"] == "LAY" and d["strategy_ref"] == "safe" and d["max_eta_ms"] == 3000
    assert isinstance(d["selection_id"], int) and isinstance(d["market_id"], str)
    busta = json.loads(PO.busta("comando", d))
    assert busta == {"t": "comando", "d": d}
    for sbagliato in ({"azione": "place_submin"}, {"mode": "LIVE"}, {"side": "buy"},
                      {"persistence": "KEEP"}, {"ref": "x" * 33}):
        kw = dict(ref="safe-t7", attore="safe", azione="place", mode="paper",
                  market_id="1.2", selection_id=1, side="LAY", price=2.0, size=2.0)
        kw.update(sbagliato)
        with pytest.raises(ValueError):
            PO.costruisci_comando(**kw)


def test_ref_deterministico_dalla_riga():
    assert PO.ref_ordine(123) == "safe-t123" == PO.ref_ordine("123")
    assert PO.ref_annullo("300123456789") == PO.ref_annullo("300123456789")
    assert len(PO.ref_annullo("300123456789", 0.5)) <= 32


def test_ref_ordine_tennis_unificato_sul_prefisso_attore():
    """F1 (25/09) - il ref del tennis porta il prefisso dell'attore
    ``safe_tennis`` (``PO.ATTORE_TENNIS``): prima di questo fix era identico
    al calcio ("safe-t<id>"), e il motore del runner rifiuta OGNI comando il
    cui ref non inizia con ``f"{attore}-"`` (``_dispatch``, non modificabile).
    Il calcio resta INVARIATO."""
    assert PO.ref_ordine(7, sport="tennis") == "safe_tennis-t7"
    assert PO.ref_ordine("7", sport="tennis") == PO.ref_ordine(7, sport="tennis")
    assert PO.ref_ordine(7, sport="calcio") == "safe-t7" == PO.ref_ordine(7)
    # falsificazione: il vecchio prefisso del tennis non e' piu' quello
    # dell'attore ``safe_tennis`` (motivo del difetto)
    assert not PO.ref_ordine(7, sport="tennis").startswith(PO.ATTORE_CALCIO + "-")
    assert PO.ref_ordine(7, sport="tennis").startswith(PO.ATTORE_TENNIS + "-")


def test_place_paper_e_live_mandano_il_comando_giusto(porta_e_motore):
    porta, motore = porta_e_motore
    for mode in ("paper", "live"):
        db, market = FakeDB(), FakeMarket()
        tr = _riserva(db, mode=mode)
        out = _place(db, market, porta, tr)
        assert out.status == "pending", out
        assert out.fill_note == "canale_%s:safe-t%d" % (mode, tr["id"])
        cmd = motore.comandi[-1]
        assert cmd["ref"] == "safe-t%d" % tr["id"]
        assert cmd["attore"] == "safe" and cmd["azione"] == "place" and cmd["mode"] == mode
        assert (cmd["market_id"], cmd["selection_id"], cmd["side"]) == ("1.234", 47972, "LAY")
        assert (cmd["price"], cmd["size"], cmd["persistence"]) == (3.0, 2.0, "LAPSE")
        assert cmd["strategy_ref"] == "safe" and cmd["max_eta_ms"] == PO.MAX_ETA_MS
        assert cmd["origine"] == {"tabella": "safe_strategy_trades", "id": tr["id"]}
        assert cmd["bet_id"] is None and cmd["size_reduction"] is None
        # nessun altro trasporto: niente coda DB, niente REST
        assert db.queue == [] and market.placed == []
        # write-ahead: il marcatore del canale e' scritto PRIMA dell'invio
        prima = db.chiamate[0]
        assert prima[0] == "update_trade" and prima[2]["meta"]["canale_ref"] == cmd["ref"]
        assert db.get_trade(tr["id"])["meta"]["canale_ack_seq"] is not None


def test_mode_viene_dalla_riga_non_dal_servizio(porta_e_motore, monkeypatch):
    """Il servizio dichiarato LIVE non promuove una riga paper (e viceversa)."""
    porta, motore = porta_e_motore
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    db, market = FakeDB(), FakeMarket()
    tr = _riserva(db, mode="paper")
    _place(db, market, porta, tr)
    assert motore.comandi[-1]["mode"] == "paper"
    monkeypatch.setenv("LIVE_ORDER_MODE", "PAPER")
    tr2 = _riserva(db, mode="live")
    _place(db, market, porta, tr2)
    assert motore.comandi[-1]["mode"] == "live"


def test_stesso_ordine_rimandato_ha_lo_stesso_ref(porta_e_motore):
    porta, motore = porta_e_motore
    db, market = FakeDB(), FakeMarket()
    tr = _riserva(db, mode="live")
    _place(db, market, porta, tr)
    out2 = _place(db, market, porta, tr)
    assert motore.comandi[0]["ref"] == motore.comandi[1]["ref"]
    # il runner lo riconosce come doppione: NON e' un rifiuto dell'ordine
    assert out2.status == "pending"
    assert market.placed == []


def test_ordine_in_volo_conta_nei_tetti_e_non_si_annulla_a_mano(porta_e_motore):
    """Dal primo istante (prima dell'ack) la riga conta come PIAZZATA nei tetti
    (``bot_db._counts_as_placed``) e l'annullo manuale della riserva e' rifiutato."""
    from Betfair.safe_strategy import bot_db as BD

    porta, motore = porta_e_motore
    motore.fase_finale = None
    db, market = FakeDB(), FakeMarket()
    tr = _riserva(db, mode="live")
    _place(db, market, porta, tr)
    riga = db.get_trade(tr["id"])
    assert riga["status"] == "pending" and BD._counts_as_placed(riga)
    res = S._request_cancel(db=db, payload={"trade_id": tr["id"]}, now=NOW)
    assert "rejected" in res and db.get_trade(tr["id"]) is not None


# ===========================================================================
# 2. ack rifiutato / mancante
# ===========================================================================
def test_ack_rifiutato_marca_la_riga_e_non_rimanda(porta_e_motore):
    porta, motore = porta_e_motore
    motore.comportamento = "rifiuta"
    motore.motivo = "kill_switch"
    db, market = FakeDB(), FakeMarket()
    tr = _riserva(db, mode="live")
    out = _place(db, market, porta, tr)
    assert out.status == "error"
    assert out.fill_note == "canale_rifiutato:kill_switch"
    assert out.error_code == "kill_switch"
    assert len(motore.comandi) == 1
    assert market.placed == [] and db.queue == []
    assert any(k == "canale_rifiutato" for k, _ in db.activity)


def test_ack_mancante_su_place_nessun_ripiego(porta_e_motore):
    porta, motore = porta_e_motore
    motore.comportamento = "muto"
    for mode in ("live", "paper"):
        db, market = FakeDB(), FakeMarket()
        tr = _riserva(db, mode=mode)
        out = _place(db, market, porta, tr)
        assert out.status == "pending"
        assert out.fill_note.startswith("canale_esito_ignoto:")
        # NESSUN ripiego: ne' REST ne' coda DB
        assert market.placed == [] and db.queue == []
        riga = db.get_trade(tr["id"])
        assert riga["status"] == "pending"
        assert riga["meta"]["canale_esito_ignoto"] is True
        assert riga["meta"]["canale_ref"] == "safe-t%d" % tr["id"]
    assert len(motore.comandi) == 2


def test_ack_mancante_su_chiusura_nessun_ripiego_immediato(porta_e_motore):
    """Anche una CHIUSURA inviata senza ack non si rimanda: una seconda
    chiusura sopra la prima rovescerebbe la posizione."""
    porta, motore = porta_e_motore
    motore.comportamento = "muto"
    db, market = FakeDB(), FakeMarket()
    tr = _riserva(db, mode="live", side="back", closes=99)
    out = _place(db, market, porta, tr)
    assert out.status == "pending" and market.placed == [] and db.queue == []


def test_ack_mancante_su_cancel_ripiego_consentito(porta_e_motore):
    porta, motore = porta_e_motore
    motore.comportamento = "muto"
    market = FakeMarket()
    res = X.annulla_su_betfair(market, bet_id="300111", market_id="1.234",
                               porta=porta, mode="live")
    assert [c["azione"] for c in motore.comandi] == ["cancel"]
    assert market.cancels == [("300111", "1.234", None)]
    assert res is not None and res.ok


def test_cancel_via_canale_accettato_esito_dall_evento(porta_e_motore):
    porta, motore = porta_e_motore
    market = FakeMarket()
    res = X.annulla_su_betfair(market, bet_id="300222", market_id="1.234",
                               porta=porta, mode="live")
    cmd = motore.comandi[-1]
    assert cmd["azione"] == "cancel" and cmd["bet_id"] == "300222"
    assert cmd["ref"] == PO.ref_annullo("300222") and cmd["mode"] == "live"
    assert market.cancels == []                 # niente REST: il canale ha risposto
    assert res is not None and res.riletto and res.size_remaining == 0.0


def test_cancel_paper_senza_ack_non_ripiega_sul_rest(porta_e_motore):
    """Paper e live mai mischiati: un annullo PAPER non va MAI al REST vero."""
    porta, motore = porta_e_motore
    motore.comportamento = "muto"
    market = FakeMarket()
    res = X.annulla_su_betfair(market, bet_id="300333", market_id="1.234",
                               porta=porta, mode="paper")
    assert res is None and market.cancels == []


# ===========================================================================
# 3. canale giu' PRIMA dell'invio
# ===========================================================================
def test_canale_giu_apertura_non_parte_chiusura_va_col_trasporto_di_oggi():
    motore = FintoMotore()
    motore.rifiuta_connessione = True
    porta = PO.PortaCanale(porta_ws=47331, attore="safe", connetti=motore.connetti,
                           token_fn=lambda: TOKEN)       # mai avviata: giu'
    db, market = FakeDB(), FakeMarket()
    tr = _riserva(db, mode="live")
    out = _place(db, market, porta, tr)
    assert out.status == "error" and out.fill_note == "canale_giu:apertura_non_inviata"
    assert market.placed == [] and db.queue == [] and motore.comandi == []
    # CHIUSURA (D5): trasporto di oggi. Qui il gate della coda e' chiuso
    # (``now``/omega gate): REST FOK, esente dal freno come oggi.
    ch = _riserva(db, mode="live", side="back", closes=tr["id"])
    out2 = X.place(db=db, market=market, mode="live", event_id=ch["event_id"],
                   market_id=ch["market_id"], selection_id=ch["selection_id"], side="back",
                   price=3.0, size=2.0, best_size=100.0, ladder=((3.0, 100.0),),
                   client_ref="safe-t%d" % ch["id"], trade_id=ch["id"],
                   meta=dict(ch["meta"]), now=None, params={}, porta=porta)
    assert out2.status == "open" and len(market.placed) == 1
    assert market.placed[0]["customer_ref"] == "safe-t%d" % ch["id"]
    assert "canale_ref" not in (db.get_trade(ch["id"])["meta"] or {})


def test_senza_token_la_porta_resta_giu():
    motore = FintoMotore()
    porta = PO.PortaCanale(porta_ws=47331, attore="safe", connetti=motore.connetti,
                           token_fn=lambda: None)
    with pytest.raises(RuntimeError):
        porta.collega_una_volta()
    assert not porta.disponibile() and motore.connessioni == []


# ===========================================================================
# 4. esiti dagli eventi order (resolver in reconcile_pending)
# ===========================================================================
def _manda_e_risolvi(porta, motore, *, mode: str, fase_finale: Optional[str],
                     parziale: Optional[float] = None, now: datetime = NOW):
    motore.fase_finale = fase_finale
    motore.parziale = parziale
    db, market = FakeDB(), FakeMarket()
    tr = _riserva(db, mode=mode)
    _place(db, market, porta, tr)
    assert _attendi(lambda: porta.esiti(tr_ref(tr)) is not None
                    and (fase_finale is None or PO.terminale(porta.esiti(tr_ref(tr)))
                         or parziale is not None))
    return db, market, tr


def tr_ref(tr: dict) -> str:
    return "safe-t%d" % tr["id"]


@pytest.fixture
def porta_registrata(porta_e_motore, monkeypatch):
    porta, motore = porta_e_motore
    monkeypatch.setattr(PO, "porta_esistente", lambda sport: porta)
    return porta, motore


def test_evento_abbinato_conferma_la_riga_con_abbinato_e_medio(porta_registrata):
    porta, motore = porta_registrata
    for mode in ("paper", "live"):
        db, market, tr = _manda_e_risolvi(porta, motore, mode=mode, fase_finale="abbinato")
        n = S.reconcile_pending(market=market, db=db, now=NOW)
        riga = db.get_trade(tr["id"])
        assert n == 1 and riga["status"] == "open", riga
        assert riga["size"] == 2.0 and riga["price"] == 3.0
        assert riga["bet_id"] == "3000000001"
        assert market.list_calls == 0            # nessuna lettura REST


def test_evento_annullato_senza_abbinato_riga_in_errore(porta_registrata):
    porta, motore = porta_registrata
    db, market, tr = _manda_e_risolvi(porta, motore, mode="live", fase_finale="annullato")
    S.reconcile_pending(market=market, db=db, now=NOW)
    riga = db.get_trade(tr["id"])
    assert riga["status"] == "error"
    assert riga["meta"]["reason"] == "flumine_canale_annullato"


def test_parziale_aggiorna_abbinato_residuo_medio(porta_registrata):
    porta, motore = porta_registrata
    db, market, tr = _manda_e_risolvi(porta, motore, mode="live", fase_finale=None,
                                      parziale=0.8)
    assert _attendi(lambda: (porta.esiti(tr_ref(tr)) or {}).get("fase") == "abbinato_parziale")
    S.reconcile_pending(market=market, db=db, now=NOW)
    riga = db.get_trade(tr["id"])
    assert riga["status"] == "pending"
    assert riga["size_matched"] == 0.8 and riga["size_remaining"] == 1.2
    assert riga["avg_price_matched"] == 3.0 and riga["bet_id"] == "3000000001"
    assert riga["meta"]["canale_fase"] == "abbinato_parziale"
    # un secondo giro senza eventi nuovi NON riscrive la riga
    scritture = len(db.chiamate)
    S.reconcile_pending(market=market, db=db, now=NOW)
    assert len(db.chiamate) == scritture


def test_evento_dell_altra_modalita_non_si_applica(porta_registrata):
    """Un evento 'live' non risolve MAI una riga 'paper' con lo stesso ref."""
    porta, motore = porta_registrata
    db, market, tr = _manda_e_risolvi(porta, motore, mode="paper", fase_finale=None)
    ev = porta.esiti(tr_ref(tr))
    finto = dict(ev, mode="live", fase="abbinato", seq=ev["seq"] + 100,
                 size_matched=2.0, status="EXECUTION_COMPLETE")
    porta.memoria.ricevi_evento(finto)
    S.reconcile_pending(market=market, db=db, now=NOW)
    assert db.get_trade(tr["id"])["status"] == "pending"


def test_live_senza_esito_oltre_la_scadenza_si_interroga_per_ref(porta_registrata):
    porta, motore = porta_registrata
    motore.comportamento = "muto"
    db, market = FakeDB(), FakeMarket()
    tr = _riserva(db, mode="live")
    _place(db, market, porta, tr)
    # dentro la scadenza: si aspetta, nessuna lettura REST
    S.reconcile_pending(market=market, db=db, now=NOW + timedelta(seconds=5))
    assert market.list_calls == 0 and db.get_trade(tr["id"])["status"] == "pending"
    # oltre: si chiede a Betfair PER REF (listCurrentOrders), l'ordine c'e'
    market.current = [{"bet_id": "BF9", "customer_order_ref": tr_ref(tr),
                       "market_id": "1.234", "selection_id": 47972, "side": "LAY",
                       "size_matched": 2.0, "size_remaining": 0.0,
                       "avg_price_matched": 3.05}]
    S.reconcile_pending(market=market, db=db, now=NOW + timedelta(seconds=25))
    riga = db.get_trade(tr["id"])
    assert market.list_calls == 1
    assert riga["status"] == "open" and riga["price"] == 3.05 and riga["bet_id"] == "BF9"


def test_paper_senza_esito_oltre_la_scadenza_nessun_fill_inventato(porta_registrata):
    porta, motore = porta_registrata
    motore.comportamento = "muto"
    db, market = FakeDB(), FakeMarket()
    tr = _riserva(db, mode="paper")
    _place(db, market, porta, tr)
    S.reconcile_pending(market=market, db=db, now=NOW + timedelta(seconds=10))
    assert db.get_trade(tr["id"])["status"] == "pending"
    S.reconcile_pending(market=market, db=db, now=NOW + timedelta(seconds=600))
    riga = db.get_trade(tr["id"])
    assert riga["status"] == "error" and riga["meta"]["reason"] == "flumine_canale_senza_esito"
    assert market.list_calls == 0


def test_ack_perso_ed_esito_arrivato(porta_registrata):
    porta, motore = porta_registrata
    motore.comportamento = "muto_con_esito"
    db, market = FakeDB(), FakeMarket()
    tr = _riserva(db, mode="live")
    out = _place(db, market, porta, tr)
    assert out.fill_note.startswith("canale_esito_ignoto:")
    assert _attendi(lambda: PO.terminale(porta.esiti(tr_ref(tr))))
    S.reconcile_pending(market=market, db=db, now=NOW)
    assert db.get_trade(tr["id"])["status"] == "open"
    assert market.list_calls == 0


# ===========================================================================
# 5. sequenza e riconnessione
# ===========================================================================
def test_memoria_evento_vecchio_non_sostituisce_e_terminale_non_torna_indietro():
    m = PO.MemoriaComandi()
    base = {"ref": "safe-t1", "fase": "accettato_betfair", "size_matched": 0.0}
    assert m.ricevi_evento(dict(base, seq=2))
    assert not m.ricevi_evento(dict(base, seq=1, fase="abbinato"))
    assert m.ricevi_evento(dict(base, seq=3, fase="abbinato"))
    assert not m.ricevi_evento(dict(base, seq=4, fase="abbinato_parziale"))
    assert m.esito("safe-t1")["fase"] == "abbinato"
    assert not m.ricevi_evento({"ref": "safe-t1", "fase": "abbinato"})   # senza seq


def test_riconnessione_chiede_da_seq_e_recupera_gli_eventi(porta_e_motore):
    porta, motore = porta_e_motore
    db, market = FakeDB(), FakeMarket()
    tr = _riserva(db, mode="live")
    motore.fase_finale = None
    _place(db, market, porta, tr)
    assert _attendi(lambda: porta.memoria.seq_visto >= 2)
    visto = porta.memoria.seq_visto
    # il runner produce l'esito MENTRE il canale e' giu': l'evento si perde
    motore.attuale().close()
    assert _attendi(lambda: not porta.disponibile(), 2.0)
    motore.evento(None, motore.comandi[-1], "abbinato", matched=2.0, remaining=0.0,
                  status="EXECUTION_COMPLETE", avg=3.0, manda=False)
    assert _attendi(porta.disponibile, 5.0)
    assert _attendi(lambda: motore.da_seq and motore.da_seq[-1] == visto)
    assert _attendi(lambda: PO.terminale(porta.esiti(tr_ref(tr))))


def test_buco_di_sequenza_chiede_da_seq(porta_e_motore):
    porta, motore = porta_e_motore
    ws = motore.attuale()
    ws.uscita.put(json.dumps({"t": "order", "d": {"ref": "safe-t50", "seq": 1,
                                                  "fase": "accettato_betfair"}}))
    ws.uscita.put(json.dumps({"t": "order", "d": {"ref": "safe-t50", "seq": 3,
                                                  "fase": "abbinato"}}))
    assert _attendi(lambda: motore.da_seq == [1])
    assert porta.memoria.buchi >= 1


# ===========================================================================
# 6. interruttore spento = parita' totale
# ===========================================================================
def test_interruttore_spento_nessuna_porta(monkeypatch):
    monkeypatch.delenv(PO.ENV_CANALE, raising=False)
    monkeypatch.delenv(PO.ENV_CANALE_TENNIS, raising=False)
    PO.azzera()
    assert PO.porta_per_sport("calcio") is None
    assert PO.porta_per_sport("tennis") is None
    assert PO._PORTE == {}
    for valore in ("", "0", "false", "no", "off"):
        monkeypatch.setenv(PO.ENV_CANALE, valore)
        assert PO.porta_per_sport("calcio") is None
    assert S._porta_kw({"sport": "calcio"}) == {}
    assert S._porta_kw({"sport": "tennis"}) == {}


def test_interruttore_spento_execute_chiama_place_come_oggi(monkeypatch):
    """Spento: ``X.place`` riceve ESATTAMENTE gli argomenti di sempre (nessun
    ``porta``), e nessuna connessione viene tentata."""
    monkeypatch.delenv(PO.ENV_CANALE, raising=False)
    tentativi: list = []
    monkeypatch.setattr(PO, "_connetti_ws", lambda *a, **k: tentativi.append(a))
    chiamate: list = []

    def finta_place(**kw):
        chiamate.append(kw)
        return X.PlaceOutcome("error", None, 0.0, None, "finta")

    monkeypatch.setattr(S.X, "place", finta_place)
    monkeypatch.setattr(S, "_place_fail", lambda *a, **k: None)
    db = FakeDB()
    tr = _riserva(db, mode="live")
    S._execute(db=db, market=FakeMarket(), trade_id=tr["id"], row=tr, params={},
               now=NOW, best_size=10.0, ladder=((3.0, 10.0),))
    assert len(chiamate) == 1
    assert set(chiamate[0]) == {"db", "market", "mode", "event_id", "market_id",
                                "selection_id", "side", "price", "size", "best_size",
                                "ladder", "client_ref", "trade_id", "meta", "now", "params"}
    assert tentativi == []


def test_interruttore_acceso_execute_passa_la_porta(monkeypatch):
    monkeypatch.setenv(PO.ENV_CANALE, "1")
    finta = object()
    monkeypatch.setattr(PO, "porta_per_sport", lambda sport, **k: finta if sport == "calcio" else None)
    chiamate: list = []
    monkeypatch.setattr(S.X, "place", lambda **kw: chiamate.append(kw) or
                        X.PlaceOutcome("error", None, 0.0, None, "finta"))
    monkeypatch.setattr(S, "_place_fail", lambda *a, **k: None)
    db = FakeDB()
    tr = _riserva(db, mode="paper")
    S._execute(db=db, market=FakeMarket(), trade_id=tr["id"], row=tr, params={},
               now=NOW, best_size=10.0, ladder=((3.0, 10.0),))
    assert chiamate[0]["porta"] is finta
    assert chiamate[0]["client_ref"] == "safe-t%d" % tr["id"]


def test_parita_place_senza_porta_uguale_a_porta_none():
    """``porta=None`` e ``PortaOggi`` percorrono lo STESSO codice di oggi: stessa
    sequenza di chiamate sui finti, riga per riga."""
    tracce = []
    for porta in (None, PO.PortaOggi()):
        db, market = FakeDB(), FakeMarket()
        tr = _riserva(db, mode="live")
        tr["id"] = 900                     # stesso id nelle due corse
        kw = {} if porta is None else {"porta": porta}
        out = X.place(db=db, market=market, mode="live", event_id=tr["event_id"],
                      market_id="1.234", selection_id=47972, side="lay", price=3.0,
                      size=2.0, best_size=100.0, ladder=((3.0, 100.0),),
                      client_ref="safe-t%d" % tr["id"], trade_id=tr["id"],
                      meta={}, now=None, params={}, **kw)
        tracce.append((out.status, out.price, out.size, out.bet_id, out.fill_note,
                       db.chiamate, db.activity, market.placed, db.queue))
    assert tracce[0] == tracce[1]


# ===========================================================================
# 7. contratto: il finto parla come il vero
# ===========================================================================
def test_contratto_evento_del_finto_uguale_alla_riga_vera_piu_protocollo():
    from Betfair.stream.engine.live_trading_strategy import LiveTradingStrategy

    vera = LiveTradingStrategy._order_row(
        SimpleNamespace(mode="live"),
        _ordine_flumine(bet_id="1", size=2.0, price=3.0, side="LAY", matched=0.0,
                        remaining=2.0, status="EXECUTABLE"),
        event_id="e", market_id="1.234")
    motore = FintoMotore()
    cmd = PO.costruisci_comando(ref="safe-t1", attore="safe", azione="place", mode="live",
                                market_id="1.234", selection_id=47972, side="LAY",
                                price=3.0, size=2.0, persistence="LAPSE")
    ev = motore.evento(None, cmd, "accettato_betfair", matched=0.0, remaining=2.0,
                       status="EXECUTABLE", manda=False)
    assert set(ev) == set(vera) | {"updated_at"} | set(PO.CHIAVI_EVENTO_EXTRA)
    for k in vera:
        assert type(ev[k]) is type(vera[k]), k


def test_websocket_vero_token_percorso_e_ack():
    """Un giro su un server WebSocket VERO (127.0.0.1, porta effimera): header
    del token, percorso ``/comando/safe``, busta comando -> ack."""
    ws_server = pytest.importorskip("websockets.sync.server")
    visti: dict = {}

    def gestore(conn):
        visti["path"] = conn.request.path
        visti["token"] = conn.request.headers.get(PO.HEADER_TOKEN)
        for grezzo in conn:
            msg = json.loads(grezzo)
            visti.setdefault("buste", []).append(msg)
            if msg["t"] == "comando":
                conn.send(json.dumps({"t": "ack", "d": {
                    "ref": msg["d"]["ref"], "seq": 1, "accettato": True,
                    "motivo": None, "ricevuto_ms": 1.0}}))

    server = ws_server.serve(gestore, "127.0.0.1", 0)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    try:
        porta_n = server.socket.getsockname()[1]
        porta = PO.PortaCanale(porta_ws=porta_n, attore="safe", token_fn=lambda: TOKEN)
        porta.avvia()
        assert _attendi(porta.disponibile, 5.0)
        cmd = PO.costruisci_comando(ref="safe-t9", attore="safe", azione="place",
                                    mode="paper", market_id="1.2", selection_id=1,
                                    side="BACK", price=2.0, size=2.0, persistence="LAPSE")
        ack = porta.invia(cmd)
        assert ack.accettato and ack.arrivato and ack.seq == 1
        assert visti["path"] == "/comando/safe" and visti["token"] == TOKEN
        assert visti["buste"][0] == {"t": "comando", "d": cmd}
        porta.ferma()
    finally:
        server.shutdown()


# ===========================================================================
# 8. difetti 24/09 (referto della porta di Omega): creato_ms intero,
#    strategy_ref per attore, FOK/reduces_liability sulle chiusure, fasi
#    intermedie del place-and-trim
# ===========================================================================
def test_creato_ms_e_intero_il_motore_vero_lo_accetta():
    """Difetto 1: ``creato_ms`` era ``round(ms, 1)`` (float): il motore vero
    (``motore_ordini._intero``) rifiuta QUALSIASI float, anche un numero
    tondo — ogni comando di Safe sarebbe stato respinto."""
    cmd = PO.costruisci_comando(ref="safe-t1", attore="safe", azione="place", mode="paper",
                                market_id="1.2", selection_id=1, side="LAY", price=2.0,
                                size=2.0, persistence="LAPSE")
    assert type(cmd["creato_ms"]) is int
    piano = MO.valida_comando("safe", cmd)
    assert piano["creato_ms"] == cmd["creato_ms"]
    # un creato_ms passato ESPLICITO (float, come faceva execution.py prima)
    # arrotonda a intero, non resta float
    cmd2 = PO.costruisci_comando(ref="safe-t2", attore="safe", azione="place", mode="paper",
                                 market_id="1.2", selection_id=1, side="LAY", price=2.0,
                                 size=2.0, persistence="LAPSE", creato_ms=1234.7)
    assert cmd2["creato_ms"] == 1235 and type(cmd2["creato_ms"]) is int
    MO.valida_comando("safe", cmd2)


def test_place_via_canale_manda_creato_ms_intero(porta_e_motore):
    """End-to-end: il comando che ESCE dal canale (``execution._place_via_canale``)
    ha ``creato_ms`` intero. Il finto lo valida col motore VERO (``FintoMotore.
    gestisci``): un ``creato_ms`` float farebbe fallire QUESTO test dentro il
    finto stesso, prima ancora dell'assert qui sotto."""
    porta, motore = porta_e_motore
    db, market = FakeDB(), FakeMarket()
    tr = _riserva(db, mode="live")
    _place(db, market, porta, tr)
    cmd = motore.comandi[-1]
    assert type(cmd["creato_ms"]) is int


def test_strategy_ref_segue_l_attore_calcio_e_tennis(porta_e_motore, porta_e_motore_tennis):
    """Difetto 2: ``strategy_ref`` era fisso a "safe": un comando dell'attore
    ``safe_tennis`` veniva rifiutato dal motore (``strategy_ref`` diverso
    dall'attore del percorso, ``motore_ordini.valida_comando``)."""
    porta_c, motore_c = porta_e_motore
    porta_t, motore_t = porta_e_motore_tennis
    db, market = FakeDB(), FakeMarket()

    tr_c = _riserva(db, mode="live", sport="calcio")
    _place(db, market, porta_c, tr_c)
    cmd_c = motore_c.comandi[-1]
    assert cmd_c["attore"] == "safe" and cmd_c["strategy_ref"] == "safe"
    MO.valida_comando("safe", cmd_c)                    # non solleva

    tr_t = _riserva(db, mode="live", sport="tennis")
    _place(db, market, porta_t, tr_t)
    cmd_t = motore_t.comandi[-1]
    assert cmd_t["attore"] == "safe_tennis" and cmd_t["strategy_ref"] == "safe_tennis"
    MO.valida_comando("safe_tennis", cmd_t)             # non solleva
    # F1 (25/09): il ref e' unificato sul prefisso dell'attore, non piu' lo
    # stesso "safe-t<id>" del calcio (quello che questo test mandava prima del
    # fix, mai rifiutato QUI perche' ``valida_comando`` non controlla il
    # prefisso del ref: lo controlla ``_dispatch``, provato per intero — ack
    # vero, falsificazione vera — in ``test_motore_ordini_2026_09_24.py``).
    assert cmd_t["ref"] == "safe_tennis-t%d" % tr_t["id"]

    # il difetto ERA: strategy_ref fisso a "safe" -> il motore rifiuta
    # l'attore tennis (riprodotto qui a mano, senza toccare il codice)
    rotto = dict(cmd_t, strategy_ref="safe")
    with pytest.raises(MO.Rifiuto):
        MO.valida_comando("safe_tennis", rotto)


def test_place_via_canale_apertura_e_chiusura_portano_fok_come_la_coda(porta_e_motore):
    """Difetto 3: le chiusure via canale partivano SENZA ``time_in_force`` ne'
    ``reduces_liability``. La coda flumine (``execution.enqueue_place``) mette
    FOK su OGNI place normale — apertura e chiusura, paper e live — e
    ``reduces_liability`` SOLO sulle chiusure: qui si riproduce lo STESSO
    comportamento, verificato dal motore vero."""
    porta, motore = porta_e_motore
    db, market = FakeDB(), FakeMarket()

    # apertura: FOK si', reduces_liability no
    tr = _riserva(db, mode="live")
    _place(db, market, porta, tr)
    cmd_open = motore.comandi[-1]
    assert cmd_open["time_in_force"] == "FILL_OR_KILL"
    assert cmd_open["reduces_liability"] is False
    MO.valida_comando("safe", cmd_open)

    # chiusura: FOK si', reduces_liability si' (closes_trade_id nel meta)
    ch = _riserva(db, mode="live", side="back", closes=tr["id"])
    out = X.place(db=db, market=market, mode="live", event_id=ch["event_id"],
                  market_id=ch["market_id"], selection_id=ch["selection_id"], side="back",
                  price=3.0, size=2.0, best_size=100.0, ladder=((3.0, 100.0),),
                  client_ref="safe-t%d" % ch["id"], trade_id=ch["id"],
                  meta=dict(ch["meta"]), now=NOW, params={}, porta=porta)
    assert out.status == "pending"
    cmd_close = motore.comandi[-1]
    assert cmd_close["time_in_force"] == "FILL_OR_KILL"
    assert cmd_close["reduces_liability"] is True
    piano = MO.valida_comando("safe", cmd_close)
    assert piano["riduce"] is True

    # paper: la coda mette FOK ANCHE in paper (CERT. 14/09: "il paper uccide
    # come il live") — stessa regola qui
    db2 = FakeDB()
    tr2 = _riserva(db2, mode="paper")
    _place(db2, market, porta, tr2)
    assert motore.comandi[-1]["time_in_force"] == "FILL_OR_KILL"


def test_fasi_intermedie_place_and_trim_non_terminali():
    """La porta accetta le fasi INTERMEDIE del place-and-trim (``parcheggiato``
    = ordine al minimo non abbinabile, ``ridotto`` = tagliato sotto il minimo,
    ``trading/submin.py``) come NON terminali: non si scartano, e un esito
    VERO arrivato dopo le sostituisce comunque."""
    assert "parcheggiato" in PO.FASI and "ridotto" in PO.FASI
    assert "parcheggiato" not in PO.FASI_TERMINALI
    assert "ridotto" not in PO.FASI_TERMINALI
    assert not PO.terminale({"fase": "parcheggiato"})
    assert not PO.terminale({"fase": "ridotto"})

    m = PO.MemoriaComandi()
    base = {"ref": "safe-t1", "size_matched": 0.0}
    assert m.ricevi_evento(dict(base, seq=1, fase="parcheggiato"))    # non scartato
    assert m.esito("safe-t1")["fase"] == "parcheggiato"
    assert not PO.terminale(m.esito("safe-t1"))
    assert m.ricevi_evento(dict(base, seq=2, fase="ridotto"))         # non scartato
    assert m.esito("safe-t1")["fase"] == "ridotto"
    assert not PO.terminale(m.esito("safe-t1"))
    # l'esito VERO arriva dopo: una fase intermedia non e' terminale, quindi
    # non blocca l'aggiornamento (la regola "un esito terminale non torna
    # indietro" vale SOLO per un esito gia' terminale)
    assert m.ricevi_evento(dict(base, seq=3, fase="abbinato"))
    assert PO.terminale(m.esito("safe-t1"))
    assert m.esito("safe-t1")["fase"] == "abbinato"


def test_attendi_esito_bet_ignora_le_fasi_intermedie(porta_e_motore):
    """``attendi_esito_bet`` aspetta un esito VERO: una fase intermedia del
    place-and-trim (size ancora viva a mercato) non deve soddisfarlo."""
    porta, motore = porta_e_motore
    porta.memoria.ricevi_evento({"ref": "safe-t1", "seq": 1, "fase": "parcheggiato",
                                 "bet_id": "B1", "size_remaining": 2.0})
    assert porta.attendi_esito_bet("B1", 0.1) is None
    porta.memoria.ricevi_evento({"ref": "safe-t1", "seq": 2, "fase": "ridotto",
                                 "bet_id": "B1", "size_remaining": 0.3})
    assert porta.attendi_esito_bet("B1", 0.1) is None
    porta.memoria.ricevi_evento({"ref": "safe-t1", "seq": 3, "fase": "abbinato",
                                 "bet_id": "B1", "size_remaining": 0.0})
    ev = porta.attendi_esito_bet("B1", 1.0)
    assert ev is not None and ev["fase"] == "abbinato"
