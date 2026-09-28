"""D1 (28/09) - SAFE: UN ORDINE, UN ESITO, IN PAPER COME IN LIVE.

Difetto (``AUDIT_2026-09-25/FIX_C_RESILIENZA_RETE_2026-09-26.md`` §7 punto 5):
se l'accodamento sulla coda del runner va in errore (risposta persa: la riga
di coda puo' essere GIA' stata scritta) e anche la ricerca per ``client_ref``
fallisce, in LIVE la riga resta 'pending' e si risolve per ref; in PAPER invece
``enqueue_place`` tornava None e ``place`` ripiegava sul fill simulato in casa.
Il runner, pero', aveva gia' la richiesta: DUE esecuzioni dello stesso ordine.

Il finto del database parla come ``Betfair/safe_strategy/bot_db.py``:
``enqueue_live_order`` torna l'id (int) dall'RPC ``request_betfair_live_order``;
``get_live_order_request_by_ref`` torna la riga con le colonne
``id,status,result,error,bet_id,processed_at`` o None. La rete «giu'» e' un
``httpx.ReadTimeout``, cioe' l'eccezione che la libreria alza davvero.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from Betfair.omega import omega_market as M
from Betfair.omega import omega_service as OS
from Betfair.safe_strategy import execution as X

NOW = datetime(2026, 9, 28, 20, 0, tzinfo=timezone.utc)


class DbRisposteRotte:
    """Specchio in memoria di ``bot_db`` (trade + coda), con la rete che puo'
    perdere la RISPOSTA dopo che il server ha gia' scritto."""

    def __init__(self, *, mode_runner: str = "PAPER") -> None:
        self.trades: list[dict] = []
        self.activity: list[tuple] = []
        self.coda: dict[int, dict] = {}          # id -> riga di betfair_live_order_requests
        self.follow = "STREAMING"
        self.heartbeat = {"ts": NOW.isoformat(), "mode": mode_runner, "pid": 1}
        self._id = 0
        self._qid = 0
        # interruttori della rete
        self.enqueue_scrive_poi_perde_risposta = False
        self.ricerca_per_ref_giu = False

    # --- log / trade ---
    def log(self, kind, payload=None):
        self.activity.append((kind, payload or {}))

    def insert_trade(self, trade):
        self._id += 1
        row = dict(trade, id=self._id)
        row.setdefault("placed_at", NOW.isoformat())
        self.trades.append(row)
        return self._id

    def update_trade(self, trade_id, **fields):
        for t in self.trades:
            if t["id"] == trade_id:
                t.update(fields)

    def delete_trade(self, trade_id):
        self.trades = [t for t in self.trades
                       if not (t["id"] == trade_id and t.get("status") == "pending")]

    def get_trade(self, trade_id):
        return next((t for t in self.trades if t["id"] == int(trade_id)), None)

    def list_trades(self, status=None):
        return [t for t in self.trades if status is None or t.get("status") == status]

    # --- coda del runner (stesso contratto di bot_db) ---
    def live_follow_status(self, event_id):
        return self.follow

    def runner_heartbeat(self):
        return self.heartbeat

    def enqueue_live_order(self, payload):
        self._qid += 1
        self.coda[self._qid] = {"id": self._qid, "status": "pending", "result": None,
                                "error": None, "bet_id": None, "processed_at": None,
                                "client_ref": payload["client_ref"], "payload": dict(payload)}
        if self.enqueue_scrive_poi_perde_risposta:
            # la riga E' in coda, ma la risposta non arriva mai al bot
            raise httpx.ReadTimeout("The read operation timed out")
        return self._qid

    def get_live_order_request_by_ref(self, client_ref):
        if self.ricerca_per_ref_giu:
            raise httpx.ConnectTimeout("timed out")
        for r in self.coda.values():
            if r["client_ref"] == str(client_ref):
                return {k: r[k] for k in ("id", "status", "result", "error", "bet_id",
                                          "processed_at")}
        return None

    def get_live_order_request(self, rid):
        r = self.coda.get(int(rid))
        return None if r is None else {k: r[k] for k in ("id", "status", "result", "error",
                                                         "bet_id", "processed_at")}

    def get_live_order_mirror(self, ref, mode="paper"):
        return None

    def revoke_live_order_request(self, rid):
        return True


class MercatoCheConta:
    """Conta ogni chiamata REST: un ordine vero in piu' e' il difetto."""

    def __init__(self) -> None:
        self.piazzati: list[dict] = []

    def place_order_live(self, **kw):
        self.piazzati.append(kw)
        return M.PlaceResult(ok=True, order_status="EXECUTION_COMPLETE", bet_id="b-1",
                             size_matched=kw["size"], avg_price_matched=kw["price"])


PARAMS_GATE_APERTO = {"execution_mode": "auto", "omega_live_via_flumine": True}


@pytest.fixture(autouse=True)
def _freni_spenti(monkeypatch):
    # i freni globali non sono l'oggetto del test: aperti in entrambi i modi
    monkeypatch.setattr(X, "_live_brake", lambda: None)
    monkeypatch.setattr(X, "_freno_aperture", lambda: None)

    def _vietato(*_a, **_k):
        raise AssertionError("accesso al database vero da un test")
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", _vietato)


def _piazza(db, mk, mode):
    tid = db.insert_trade({"event_id": "35000001", "status": "pending", "side": "back",
                           "mode": mode, "market_id": "1.250", "selection_id": 47972,
                           "price": 2.5, "size": 4.0, "meta": {"phase": "reserved"}})
    out = X.place(db=db, market=mk, mode=mode, event_id="35000001", market_id="1.250",
                  selection_id=47972, side="back", price=2.5, size=4.0, best_size=50.0,
                  ladder=((2.5, 50.0),), client_ref=f"safe-t{tid}", trade_id=tid,
                  meta={"phase": "reserved"}, now=NOW, params=dict(PARAMS_GATE_APERTO))
    return tid, out


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_risposta_persa_e_ricerca_giu_NESSUN_secondo_percorso(mode):
    """Il caso del difetto: richiesta gia' in coda, risposta persa, ricerca KO.
    Atteso in ENTRAMBI i modi: la riga resta 'pending' col marcatore del ref,
    nessun fill simulato, nessun ordine REST."""
    db = DbRisposteRotte(mode_runner=mode.upper())
    db.enqueue_scrive_poi_perde_risposta = True
    db.ricerca_per_ref_giu = True
    mk = MercatoCheConta()

    tid, out = _piazza(db, mk, mode)

    assert out.status == "pending", f"{mode}: esito {out.status} ({out.fill_note})"
    assert out.fill_note == f"flumine_{mode}:unknown"
    assert mk.piazzati == [], "nessun ordine REST"
    riga = db.get_trade(tid)
    assert riga["status"] == "pending"
    assert riga["meta"]["flumine_client_ref"] == f"safe-t{tid}"
    assert "fill" not in riga["meta"], "nessun fill simulato in casa"
    assert len(db.coda) == 1, "una sola richiesta in coda"


def test_paper_e_live_danno_lo_STESSO_esito_sul_dubbio():
    esiti = {}
    for mode in ("paper", "live"):
        db = DbRisposteRotte(mode_runner=mode.upper())
        db.enqueue_scrive_poi_perde_risposta = True
        db.ricerca_per_ref_giu = True
        _tid, out = _piazza(db, MercatoCheConta(), mode)
        esiti[mode] = (out.status, out.fill_note.replace(mode, "MODO"), out.size, out.bet_id)
    assert esiti["paper"] == esiti["live"]


def test_paper_al_giro_dopo_la_richiesta_si_ADOTTA_per_ref():
    """Ripresa della rete: il poll della coda (``poll_flumine_pending``, lo
    stesso di Omega) trova la richiesta per ref e la aggancia alla riga. Un
    ordine, una richiesta, un esito."""
    db = DbRisposteRotte()
    db.enqueue_scrive_poi_perde_risposta = True
    db.ricerca_per_ref_giu = True
    tid, _out = _piazza(db, MercatoCheConta(), "paper")

    db.ricerca_per_ref_giu = False               # la rete torna
    OS.poll_flumine_pending(db=db, params=dict(PARAMS_GATE_APERTO), now=NOW)

    riga = db.get_trade(tid)
    assert riga["meta"]["flumine_request_id"] == 1, "richiesta adottata per ref"
    assert riga["status"] == "pending", "l'esito arriva dal runner, non da un fill in casa"
    assert len(db.coda) == 1


def test_paper_se_la_richiesta_non_esiste_si_chiude_come_NON_eseguito():
    """Il ramo opposto: l'accodamento non era arrivato. Al giro dopo la ricerca
    per ref dice «non esiste» e la riga si chiude senza fill (riga terminale,
    gamba ritentabile): mai una posizione inventata."""
    db = DbRisposteRotte()
    db.ricerca_per_ref_giu = True

    def enqueue_perso(payload):
        raise httpx.ReadTimeout("The read operation timed out")   # nulla scritto
    db.enqueue_live_order = enqueue_perso
    tid, out = _piazza(db, MercatoCheConta(), "paper")
    assert out.status == "pending"

    db.ricerca_per_ref_giu = False
    OS.poll_flumine_pending(db=db, params=dict(PARAMS_GATE_APERTO), now=NOW)

    riga = db.get_trade(tid)
    assert riga["status"] == "error"
    assert str(riga["meta"].get("reason") or "").startswith("flumine_request_missing")
    assert "fill" not in riga["meta"]


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_accodamento_CERTAMENTE_mancato_ripiega_uguale_nei_due_modi(mode):
    """Cintura: se la ricerca per ref RISPONDE «non c'e'», l'accodamento non e'
    avvenuto e il ripiego di sempre resta (paper: fill sul libro; live: REST).
    Un solo esito in entrambi i modi."""
    db = DbRisposteRotte(mode_runner=mode.upper())

    def enqueue_perso(payload):
        raise httpx.ReadTimeout("The read operation timed out")
    db.enqueue_live_order = enqueue_perso
    mk = MercatoCheConta()
    tid, out = _piazza(db, mk, mode)
    assert out.status == "open"
    assert len(mk.piazzati) == (1 if mode == "live" else 0)
    assert "flumine_client_ref" not in (db.get_trade(tid)["meta"] or {})
