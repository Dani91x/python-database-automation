# -*- coding: utf-8 -*-
"""REPERTO 17/09 — consapevolezza dell'ordine sul percorso FLUMINE di Omega.

Il reperto iniziale ipotizzava che ``_flumine_confirm``/``_poll_one_flumine_live_trade``
scrivessero con ``db.update_trade`` DIRETTO (come il difetto trovato su Safe,
trade live #297, corretto in ``bot_service._conferma_apertura`` il 17/09) e
lasciassero le cinque colonne di ``trades_consapevolezza_ordine_2026-09-16.sql``
NULL. Verificato col diff: NON e' cosi' — dal 16/09 sera (commit ``f562fff``)
``_flumine_confirm`` passa GIA' da ``_confirm_open_trade`` → ``X.aggiorna_trade``,
sia in paper (``_poll_one_flumine_trade``) sia in live
(``_poll_one_flumine_live_trade``).

Il difetto VERO era piu' piccolo ma reale: ``_mirror_fill`` (lo specchio
``betfair_live_orders``, autoritativo) leggeva SOLO ``size_matched`` e
``average_price_matched`` dallo specchio — mai ``size_remaining`` ne'
l'istante REALE di Betfair (``matched_at``, cioe' ``date_time_status_update``
via ``LiveTradingStrategy._order_row``). ``_flumine_confirm`` quindi non
poteva mettere questi due valori nel ``meta`` prima di ``_confirm_open_trade``,
e le colonne ``size_remaining``/``betfair_updated_at`` restavano NULL su OGNI
riga confermata dalla coda flumine (paper E live), pur avendo gia'
``size_matched``/``avg_price_matched``/``size_requested`` corretti.

Corretto estendendo ``_mirror_fill`` a 5 valori e infilando i due mancanti nel
``meta`` di ``_flumine_confirm`` (stessa strada di ``requested_size`` sul
percorso REST, righe ~1689-1704 di ``omega_service.py``).

FALSIFICAZIONE: la funzione precedente alla correzione non aveva i parametri
``size_remaining``/``betfair_updated_at`` su ``_flumine_confirm`` — chiamarla
COME VENIVA CHIAMATA ALLORA (senza quei due argomenti, che di default sono
``None``) riproduce ESATTAMENTE il comportamento di prima e lascia le due
colonne NULL: e' la riga rossa qui sotto (``test_falsificazione_...``).
Il referto della sessione porta l'output di ``pytest`` rilanciato con
``git stash`` sul file, PRIMA e DOPO la correzione.
"""
from __future__ import annotations

from datetime import timedelta

from Betfair.omega import certificazione as CERT
from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_flumine_paper import (
    FakeMarket,
    FakeQueueDB,
    _control,
    _cs,
    _event,
    _mirror,
    _open_snapshot,
)
from Betfair.omega.test_omega_service import NOW

COLONNE = ("size_requested", "size_matched", "size_remaining",
           "avg_price_matched", "betfair_updated_at")


def _placed_flumine(db, market):
    """Piazza il lay auto via coda flumine e ritorna (trade, rid)."""
    S.run_once(market=market, db=db, now=NOW)
    t = db.trades[0]
    rid = t["meta"]["flumine_request_id"]
    db.queue[rid]["status"] = "done"
    return t, rid


# ---------------------------------------------------------------------------
# PAPER — percorso completo (S.run_once → poll → _flumine_confirm → aggiorna_trade)
# ---------------------------------------------------------------------------
def test_flumine_confirm_paper_scrive_le_cinque_colonne():
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_flumine(db, market)
    size = t["size"]
    mirror = _mirror(size, 112.0, "EXECUTION_COMPLETE", 0.0)
    mirror["matched_at"] = "2026-09-17T10:00:05Z"     # istante REALE di Betfair
    db.mirrors[f"awlq{rid}"] = mirror

    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=20))

    t = db.trades[0]
    assert t["status"] == "open"
    for c in COLONNE:
        assert t.get(c) is not None, f"colonna {c} NULL: {t}"
    # size_requested e' il TARGET prima del cap di liquidita' (audit §6): puo'
    # essere maggiore dell'abbinato quando il book e' sottile, mai minore.
    assert t["size_requested"] >= size
    assert t["size_matched"] == size
    assert t["size_remaining"] == 0.0
    assert t["avg_price_matched"] == 112.0
    assert t["betfair_updated_at"] == "2026-09-17T10:00:05Z"


def test_flumine_confirm_paper_fill_parziale_residuo_dichiarato():
    """Fill parziale sotto TTL scaduto (cancel del residuo): il RESIDUO
    dichiarato deve essere quello vero (non zero), non solo l'abbinato."""
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_flumine(db, market)
    size = t["size"]
    parziale = round(size * 0.4, 2)
    residuo = round(size - parziale, 2)
    mirror = _mirror(parziale, 111.5, "EXECUTABLE", residuo)
    mirror["matched_at"] = "2026-09-17T10:05:12Z"
    db.mirrors[f"awlq{rid}"] = mirror

    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=50))   # oltre il TTL
    # TTL scaduto → cancel accodato; lo specchio segue lo stato 'done' del cancel
    mirror["status"] = "EXECUTION_COMPLETE"
    db.queue[max(db.queue)]["status"] = "done"                          # richiesta di cancel
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=51))

    t = db.trades[0]
    assert t["status"] == "open"
    assert t["size_matched"] == parziale
    assert t["size_remaining"] == residuo
    assert t["avg_price_matched"] == 111.5
    assert t["betfair_updated_at"] == "2026-09-17T10:05:12Z"
    assert t["size_requested"] >= size


# ---------------------------------------------------------------------------
# LIVE — _poll_one_flumine_live_trade diretto (esito TERMINALE dallo specchio)
# ---------------------------------------------------------------------------
class _FakeLiveDB:
    """Le sole firme che il percorso LIVE via coda usa qui: stessa firma reale
    ``update_trade(id, **campi)`` (contratto di ``omega_db``/``FakeDB``)."""

    def __init__(self, mirror: dict, req_status: str = "done"):
        self._mirror = mirror
        self._req_status = req_status
        self.updates: list[dict] = []
        self.activity: list[tuple] = []

    def get_live_order_request(self, request_id):
        return {"id": request_id, "status": self._req_status, "result": None,
                "error": None, "bet_id": None}

    def get_live_order_mirror(self, client_order_ref, mode="live"):
        assert mode == "live"          # fedeltà all'indice reale (mode, client_order_ref)
        return self._mirror

    def update_trade(self, trade_id, **fields):
        self.updates.append({"id": trade_id, **fields})

    def log(self, kind, payload=None):
        self.activity.append((kind, payload or {}))


def _tr_live(rid=42, size=5.0, price=1.90):
    return {
        "id": 501, "event_id": "1.500", "side": "lay", "mode": "live",
        "price": price, "size": size,
        "meta": {"flumine_request_id": rid,
                 "flumine_enqueued_at": (NOW - timedelta(seconds=25)).isoformat(),
                 "requested_size": size},
        "placed_at": (NOW - timedelta(seconds=25)).isoformat(),
    }


def test_flumine_confirm_live_scrive_le_cinque_colonne():
    mirror = {"size_matched": 5.0, "average_price_matched": 1.92,
              "status": "EXECUTION_COMPLETE", "size_remaining": 0.0,
              "bet_id": "b555", "mode": "live",
              "matched_at": "2026-09-17T10:05:00Z"}
    db = _FakeLiveDB(mirror)
    params = {"live_fill_deadline_s": 20, "min_stake": 0.5}

    n = S._poll_one_flumine_live_trade(_tr_live(), db=db, market=None,
                                       params=params, now=NOW)

    assert n == 1
    scritto = db.updates[-1]
    assert scritto["status"] == "open"
    assert scritto["bet_id"] == "b555"
    assert scritto["size_requested"] == 5.0
    assert scritto["size_matched"] == 5.0
    assert scritto["size_remaining"] == 0.0
    assert scritto["avg_price_matched"] == 1.92
    assert scritto["betfair_updated_at"] == "2026-09-17T10:05:00Z"


# ---------------------------------------------------------------------------
# FALSIFICAZIONE — chiamare _flumine_confirm come veniva chiamata PRIMA della
# correzione (senza size_remaining/betfair_updated_at): le due colonne restano
# NULL nonostante size_matched/avg_price_matched siano corretti. Con git stash
# di omega_service.py (pre-fix) questa STESSA riga di produzione non accetta
# nemmeno i due kwargs nuovi (TypeError) — vedi il referto per l'output.
# ---------------------------------------------------------------------------
def test_falsificazione_senza_i_due_argomenti_nuovi_le_colonne_restano_null():
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_flumine(db, market)
    tr = db.trades[0]

    # chiamata IDENTICA a come _poll_one_flumine_trade chiamava _flumine_confirm
    # prima del 17/09 (nessun size_remaining/betfair_updated_at)
    S._flumine_confirm(tr, db=db, matched=t["size"], avg=112.0, bet_id="sim1",
                       min_stake=0.5, mode="paper")

    scritto = db.trades[0]
    assert scritto["status"] == "open"
    assert scritto["size_matched"] == t["size"]          # questo il difetto lasciava intatto
    assert scritto["avg_price_matched"] == 112.0         # anche questo
    # le due colonne che il difetto lasciava NULL:
    assert scritto.get("size_remaining") is None, scritto
    assert scritto.get("betfair_updated_at") is None, scritto


# ---------------------------------------------------------------------------
# K7 (certificazione.py) — la colonna non resta NULL quando il meta ha gia'
# il numero giusto. Falsificazione della falsificazione: se K7 non guardasse
# le colonne (o guardasse solo il meta, come K6), non saprebbe diventare rosso
# su ESATTAMENTE il difetto di oggi.
# ---------------------------------------------------------------------------
def _riga_k7(id_=1, *, status="open", bet_id="B1", meta=None, colonne=None):
    r = {"id": id_, "status": status, "bet_id": bet_id, "meta": dict(meta or {})}
    r.update(colonne or {})
    return r


def test_k7_rosso_quando_il_meta_ha_il_residuo_e_la_colonna_no():
    """Riproduce ESATTAMENTE il difetto di oggi: meta.size_remaining c'e' (lo ha
    scritto _flumine_confirm/_confirm_open_trade nel blob), la colonna
    size_remaining resta None (la scrittura NON e' passata da X.aggiorna_trade,
    o la migrazione non era ancora applicata quando la riga e' stata scritta)."""
    r = _riga_k7(meta={"size_remaining": 3.0})
    viol = CERT.verifica_consapevolezza([r], {}, set())
    codici = {v.codice for v in viol}
    assert "K7" in codici, [str(v) for v in viol]


def test_k7_rosso_quando_il_meta_ha_l_istante_di_betfair_e_la_colonna_no():
    r = _riga_k7(meta={"betfair_updated_at": "2026-09-17T09:00:00Z"})
    viol = CERT.verifica_consapevolezza([r], {}, set())
    assert "K7" in {v.codice for v in viol}


def test_k7_silenzioso_quando_le_colonne_ci_sono_gia():
    r = _riga_k7(meta={"size_remaining": 3.0, "betfair_updated_at": "2026-09-17T09:00:00Z",
                       "requested_size": 5.0},
                colonne={"size_remaining": 3.0, "betfair_updated_at": "2026-09-17T09:00:00Z",
                         "size_requested": 5.0})
    viol = CERT.verifica_consapevolezza([r], {}, set())
    assert "K7" not in {v.codice for v in viol}


def test_k7_silenzioso_su_riga_sana_pre_migrazione_meta_muto():
    """Una riga che non parla affatto di consapevolezza (nessun requested_size/
    size_remaining/betfair_updated_at ne' in meta ne' in colonna) non e' una
    PROVA di niente: K7 tace, non e' K7 il controllo che deve accorgersi che la
    migrazione manca del tutto (falso positivo dello stesso genere di quelli
    gia' trovati dal banco il 16/09 su K1/K5, vedi ``test_omega_consapevolezza_
    2026_09_16.py::test_sano_nessuna_violazione``)."""
    r = _riga_k7(meta={})
    viol = CERT.verifica_consapevolezza([r], {}, set())
    assert "K7" not in {v.codice for v in viol}


def test_k7_non_accusa_le_righe_non_ancora_confermate():
    """Una riserva 'pending' porta gia' meta.requested_size PRIMA che
    X.aggiorna_trade sia mai stato chiamato (lo scrive _place_one al momento
    della riserva, non della conferma): accusarla sarebbe un falso positivo su
    ogni singola riga ancora in coda."""
    r = _riga_k7(status="pending", bet_id=None, meta={"requested_size": 5.0})
    viol = CERT.verifica_consapevolezza([r], {}, set())
    assert "K7" not in {v.codice for v in viol}


def test_k7_non_accusa_il_paper_senza_bet_id():
    r = _riga_k7(bet_id=None, meta={"size_remaining": 3.0})
    viol = CERT.verifica_consapevolezza([r], {}, set())
    assert "K7" not in {v.codice for v in viol}
