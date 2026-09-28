"""Test dell'esecuzione PAPER via flumine (DEMO=LIVE) — gate, enqueue, conferma,
TTL quasi-FOK, fallback legacy e garanzia che il LIVE non passi MAI dalla coda.

Riusa i fake di test_omega_service (FakeDB/FakeMarket) estendendoli con la coda
``betfair_live_order_requests`` + specchio ``betfair_live_orders`` simulati.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from Betfair.omega import omega_config
from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_service import (
    NOW,
    FakeDB,
    FakeMarket,
    _control,
    _cs,
    _event,
    _manual_req,
    _open_snapshot,
)


@pytest.fixture(autouse=True)
def _canale_ordini_spento(monkeypatch):
    """Cantiere C (28/09): questi test collaudano la coda/il runner paper, non la
    porta del canale. Il ``.env`` VERO (letto da ``load_dotenv``) accende gli
    interruttori dal 26/09: qui si spengono apposta, o il percorso provato non
    sarebbe quello dichiarato."""
    from Betfair.omega import porta_ordini as _PO_TEST

    for nome in ("OMEGA_ORDINI_VIA_CANALE", "ESITI_ORDINI_CANALE", "OMEGA_LEGGE_CANALE",
                 "PUNTEGGI_CANALE"):
        monkeypatch.setenv(nome, "0")
    _PO_TEST.azzera()
    yield
    _PO_TEST.azzera()


# ---------------------------------------------------------------------------
# Fake con coda flumine (contratto di betfair_live_order_queue.sql)
# ---------------------------------------------------------------------------
class FakeQueueDB(FakeDB):
    def __init__(self, control, *, follow_status="STREAMING", hb_mode="PAPER",
                 hb_age_s=5):
        super().__init__(control)
        self.follow_status = follow_status
        self.hb_mode = hb_mode          # None = nessuna riga heartbeat
        self.hb_age_s = hb_age_s
        self.queue: dict[int, dict] = {}  # rid -> riga coda
        self._rid = 0
        self.mirrors: dict[str, dict] = {}  # client_order_ref -> riga specchio
        self.enqueue_raises = False

    # --- contratto coda/heartbeat/follow ---
    def live_follow_status(self, event_id):
        return self.follow_status

    def runner_heartbeat(self):
        if self.hb_mode is None:
            return None
        return {"ts": (NOW - timedelta(seconds=self.hb_age_s)).isoformat(),
                "mode": self.hb_mode, "pid": 123}

    def enqueue_live_order(self, payload):
        if self.enqueue_raises:
            raise RuntimeError("rpc down")
        # idempotenza su client_ref come la RPC reale
        for rid, row in self.queue.items():
            if row["payload"]["client_ref"] == payload["client_ref"]:
                return rid
        self._rid += 1
        self.queue[self._rid] = {"id": self._rid, "status": "pending",
                                 "result": None, "error": None, "bet_id": None,
                                 "payload": dict(payload)}
        return self._rid

    def get_live_order_request(self, request_id):
        row = self.queue.get(int(request_id))
        if row is None:
            return None
        return {k: row.get(k) for k in ("id", "status", "result", "error", "bet_id")}

    def get_live_order_request_by_ref(self, client_ref):
        # idempotenza per client_ref (recovery F1, come la tabella reale)
        for row in self.queue.values():
            if row["payload"]["client_ref"] == str(client_ref):
                return {k: row.get(k) for k in ("id", "status", "result", "error", "bet_id")}
        return None

    def get_live_order_mirror(self, client_order_ref, mode="paper"):
        # fedeltà all'indice reale (mode, client_order_ref): MAI letture cross-mode
        row = self.mirrors.get(str(client_order_ref))
        if row is not None and str(row.get("mode", mode)) != str(mode):
            return None
        return row

    def revoke_live_order_request(self, request_id):
        # transizione ATOMICA pending→error, come la revoca reale (omega_db)
        row = self.queue.get(int(request_id))
        if row is None or row.get("status") != "pending":
            return False
        row["status"] = "error"
        row["error"] = "revocata da omega (deadline live)"
        return True


def _params(**over):
    return omega_config.resolve_params(over)


def _mirror(size_matched, avg, status, remaining, bet_id="sim1"):
    return {"size_matched": size_matched, "average_price_matched": avg,
            "status": status, "size_remaining": remaining, "bet_id": bet_id,
            "mode": "paper"}


# ---------------------------------------------------------------------------
# Whitelist parametri (execution_mode / paper_fill_ttl_s)
# ---------------------------------------------------------------------------
def test_config_execution_mode_whitelist():
    assert _params()["execution_mode"] == "auto"                       # default
    assert _params(execution_mode="rest")["execution_mode"] == "rest"
    assert _params(execution_mode="yolo")["execution_mode"] == "auto"  # sconosciuto → default


def test_config_paper_fill_ttl_clamp():
    assert _params()["paper_fill_ttl_s"] == 45                          # default
    assert _params(paper_fill_ttl_s=1)["paper_fill_ttl_s"] == 5         # clamp min
    assert _params(paper_fill_ttl_s=10_000)["paper_fill_ttl_s"] == 600  # clamp max


# ---------------------------------------------------------------------------
# Gate — tutte le combinazioni
# ---------------------------------------------------------------------------
def test_gate_ok():
    db = FakeQueueDB(_control())
    ok, reason = S._flumine_paper_gate("1.100", db=db, mode="paper",
                                       params=_params(), now=NOW)
    assert ok and reason == "ok"


@pytest.mark.parametrize("kw,mode,params,expected", [
    ({}, "live", {}, "mode_non_paper"),                                  # LIVE mai in coda
    ({"follow_status": None}, "paper", {}, "follow_assente"),            # evento non seguito
    ({"follow_status": "PENDING"}, "paper", {}, "follow_pending"),       # non STREAMING
    ({"hb_mode": "LIVE"}, "paper", {}, "runner_mode_non_paper"),         # runner in LIVE
    ({"hb_mode": "OFF"}, "paper", {}, "runner_mode_non_paper"),          # ordini spenti
    ({"hb_mode": None}, "paper", {}, "runner_mode_non_paper"),           # heartbeat assente
    ({"hb_age_s": 300}, "paper", {}, "runner_heartbeat_stantio"),        # runner morto
])
def test_gate_combinazioni_ko(kw, mode, params, expected):
    db = FakeQueueDB(_control(), **kw)
    ok, reason = S._flumine_paper_gate("1.100", db=db, mode=mode,
                                       params=_params(**params), now=NOW)
    assert not ok and reason == expected


def test_gate_paper_ignora_execution_mode_rest():
    """CANTIERE C (28/09): 'rest' e' una scelta del LIVE (il REST di Betfair);
    per l'apertura paper di Omega il runner resta l'unica strada."""
    db = FakeQueueDB(_control())
    ok, reason = S._flumine_paper_gate("1.100", db=db, mode="paper",
                                       params=_params(execution_mode="rest"), now=NOW)
    assert ok and reason == "ok"


def _non_eseguita(db, motivo_runner):
    """CANTIERE C (28/09): senza runner l'apertura paper NON e' eseguita (esito
    certo, nessun ordine esiste, tentativo non consumato); mai un fill di casa."""
    assert not [t for t in db.trades if t.get("status") in ("open", "pending")]
    skip = [p for k, p in db.activity
            if k == "skip" and p.get("reason") == "paper_runner_non_disponibile"]
    assert skip and skip[0]["motivo_runner"] == motivo_runner
    assert skip[0]["tentativo_consumato"] is False
    assert not any(k == "paper_fill_fallback" for k, _ in db.activity)


def test_gate_db_senza_coda_fallback():
    # un db senza il contratto della coda (FakeDB liscio) → gate chiuso
    ok, reason = S._flumine_paper_gate("1.100", db=FakeDB(_control()), mode="paper",
                                       params=_params(), now=NOW)
    assert not ok and reason == "db_senza_coda"


def test_gate_eccezione_fail_closed():
    db = FakeQueueDB(_control())

    def _boom(_):
        raise RuntimeError("db down")

    db.live_follow_status = _boom
    ok, reason = S._flumine_paper_gate("1.100", db=db, mode="paper",
                                       params=_params(), now=NOW)
    assert not ok and reason.startswith("gate_error:")


# ---------------------------------------------------------------------------
# Enqueue col gate ok (auto + manuale) — riserva resta 'pending'
# ---------------------------------------------------------------------------
def test_auto_place_gate_ok_accoda_e_resta_pending():
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 1
    assert len(db.trades) == 1
    t = db.trades[0]
    assert t["status"] == "pending"                     # NIENTE fill istantaneo
    assert t["meta"]["phase"] == "flumine_wait"
    assert t["meta"]["flumine_request_id"] == 1
    row = db.queue[1]["payload"]
    assert row["action"] == "place" and row["mode"] == "paper"
    assert row["client_ref"] == f"omega-t{t['id']}"
    assert row["market_id"] == "m-1.100" and row["selection_id"] == 4
    assert row["side"] == "lay" and row["price"] == 110.0
    assert row["size"] == t["size"]
    assert not any(k == "paper_fill_fallback" for k, _ in db.activity)


def test_auto_place_flumine_idempotente_secondo_ciclo():
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    S.run_once(market=market, db=db, now=NOW)           # secondo ciclo, fill non arrivato
    assert len(db.trades) == 1                          # I1: nessun secondo trade
    assert len(db.queue) == 1                           # nessuna seconda richiesta
    assert db.trades[0]["status"] == "pending"


def test_manuale_paper_gate_ok_accoda():
    db = FakeQueueDB(_control(status="idle"))
    db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-1.100",
                                  "selection_id": 4, "side": "lay", "mode": "paper",
                                  "price": 110, "size": 2})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert db.manual_reqs[0]["status"] == "done"
    assert db.manual_reqs[0]["result"]["ok"] is True
    assert db.manual_reqs[0]["result"]["pending_fill"] is True
    t = db.trades[0]
    assert t["status"] == "pending" and t["meta"]["manual"] is True
    assert t["meta"]["flumine_request_id"] == 1
    assert db.queue[1]["payload"]["side"] == "lay"
    assert db.queue[1]["payload"]["size"] == 2


# ---------------------------------------------------------------------------
# Fallback legacy (gate KO / enqueue KO / execution_mode='rest')
# ---------------------------------------------------------------------------
def test_gate_ko_runner_giu_apertura_non_eseguita():
    # CANTIERE C (28/09): prima qui il paper riempiva in casa (fill legacy)
    db = FakeQueueDB(_control(), hb_age_s=300)          # runner morto
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 0
    assert len(db.queue) == 0                           # niente in coda
    _non_eseguita(db, "runner_heartbeat_stantio")


def test_enqueue_ko_apertura_non_eseguita():
    db = FakeQueueDB(_control())
    db.enqueue_raises = True
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    _non_eseguita(db, "enqueue_failed")


def test_execution_mode_rest_in_paper_usa_comunque_il_runner():
    # CANTIERE C (28/09): runner PERFETTO e execution_mode='rest' -> in paper
    # l'ordine va comunque al runner (il REST di Betfair non esiste per un
    # ordine simulato) e l'attivita' lo dice all'utente
    db = FakeQueueDB(_control(params={"execution_mode": "rest"}))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert db.trades[0]["status"] == "pending"
    assert db.trades[0]["meta"]["phase"] == "flumine_wait"
    assert len(db.queue) == 1 and db.queue[1]["payload"]["time_in_force"] == "FILL_OR_KILL"
    assert any(k == "execution_mode_rest_in_paper" for k, _ in db.activity)
    assert not any(k == "paper_fill_fallback" for k, _ in db.activity)


def test_manuale_gate_ko_ordine_non_eseguito():
    # CANTIERE C (28/09): prima il manuale paper riempiva in casa (paper_at_price)
    db = FakeQueueDB(_control(status="idle"), follow_status=None)
    db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-1.100",
                                  "selection_id": 4, "side": "lay", "mode": "paper",
                                  "price": 110, "size": 2})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    t = db.trades[0]
    assert t["status"] == "error" and t["meta"]["reason"] == "paper_runner_non_disponibile"
    assert t["meta"]["motivo_runner"] == "follow_assente" and t["meta"]["leg_failed"] is True
    assert db.manual_reqs[0]["result"]["error"] == "paper_runner_non_disponibile"
    assert len(db.queue) == 0
    assert not any(k == "paper_fill_fallback" for k, _ in db.activity)


# ---------------------------------------------------------------------------
# Conferma dal fill (totale / parziale) e TTL quasi-FOK
# ---------------------------------------------------------------------------
def _placed_flumine(db, market):
    """Piazza il lay auto via coda flumine e ritorna (trade, rid)."""
    S.run_once(market=market, db=db, now=NOW)
    t = db.trades[0]
    rid = t["meta"]["flumine_request_id"]
    db.queue[rid]["status"] = "done"
    return t, rid


def test_conferma_fill_totale_con_prezzo_medio_reale():
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_flumine(db, market)
    size = t["size"]
    db.mirrors[f"awlq{rid}"] = _mirror(size, 112.0, "EXECUTION_COMPLETE", 0.0)
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=20))
    t = db.trades[0]
    assert t["status"] == "open"
    assert t["price"] == 112.0                          # prezzo medio REALE simulato
    assert t["size"] == size
    assert t["bet_id"] == "sim1"
    assert t["meta"]["fill"] == "flumine_paper"
    assert any(k == "flumine_fill" for k, _ in db.activity)


def test_attesa_dentro_ttl_resta_pending():
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_flumine(db, market)
    db.mirrors[f"awlq{rid}"] = _mirror(0.0, 0.0, "EXECUTABLE", t["size"])
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=10))  # < TTL 45s
    assert db.trades[0]["status"] == "pending"          # si aspetta il fill
    assert len(db.queue) == 1                           # nessun cancel accodato


def test_ttl_scaduto_accoda_cancel_poi_conferma_parziale():
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_flumine(db, market)
    db.mirrors[f"awlq{rid}"] = _mirror(2.0, 110.0, "EXECUTABLE", t["size"] - 2.0)
    # TTL (45s) scaduto → cancel del residuo accodato, trade ancora pending
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=60))
    t = db.trades[0]
    assert t["status"] == "pending"
    assert t["meta"]["phase"] == "flumine_cancel"
    cancel = db.queue[t["meta"]["flumine_cancel_request_id"]]["payload"]
    assert cancel["action"] == "cancel" and cancel["bet_id"] == "sim1"
    assert cancel["client_ref"] == f"omega-t{t['id']}-cancel"
    # il cancel esegue: ordine terminale col matched parziale → conferma i 2.0€
    db.mirrors[f"awlq{rid}"] = _mirror(2.0, 110.0, "EXECUTION_COMPLETE", 0.0)
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=80))
    t = db.trades[0]
    assert t["status"] == "open"
    assert t["size"] == 2.0                             # SOLO i € realmente matchati
    assert t["liability"] == pytest.approx(2.0 * 109.0, abs=0.01)


def test_ttl_scaduto_nessun_fill_libera_la_riserva():
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_flumine(db, market)
    db.mirrors[f"awlq{rid}"] = _mirror(0.0, 0.0, "EXECUTABLE", t["size"])
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=60))   # → cancel
    assert db.trades[0]["meta"]["phase"] == "flumine_cancel"
    db.mirrors[f"awlq{rid}"] = _mirror(0.0, 0.0, "EXECUTION_COMPLETE", 0.0)
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=80))
    t = db.trades[0]
    assert t["status"] == "error"                       # riserva liberata, log esplicito
    assert t["meta"]["reason"].startswith("flumine_")
    assert any(k == "flumine_no_fill" for k, _ in db.activity)


def test_fill_parziale_sotto_min_stake_contabilizzato_comunque():
    # mai posizioni nude: anche 0.30€ matchati vengono confermati (con nota)
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_flumine(db, market)
    db.mirrors[f"awlq{rid}"] = _mirror(0.30, 110.0, "EXECUTION_COMPLETE", 0.0)
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=20))
    t = db.trades[0]
    assert t["status"] == "open" and t["size"] == 0.30
    assert t["meta"]["below_min_stake"] is True


def test_richiesta_in_errore_non_e_un_fill():
    # AUDIT 11/09 (H-12): coda in errore (es. mercato non sottoscritto) = NESSUN
    # ordine simulato attivo → NO-FILL. Prima si confermava un fill PIENO al
    # prezzo della riserva (paper ≠ live, P&L regalato "a risultato noto").
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_flumine(db, market)
    db.queue[rid]["status"] = "error"
    db.queue[rid]["error"] = "market m-1.100 non sottoscritto nel runner"
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=20))
    t = db.trades[0]
    assert t["status"] == "error"
    assert t["meta"]["reason"].startswith("flumine_request_error")
    assert t["meta"]["error_final"] is True and t["meta"]["leg_failed"] is True
    # riga TERMINALE (M-05) ma NON regolata (review L5): l'istante sta nel meta
    assert t["meta"]["error_at"] and t.get("settled_at") in (None, "")
    reasons = [p.get("reason") for k, p in db.activity if k == "flumine_no_fill"]
    assert reasons and reasons[0].startswith("request_error")


def test_runner_muto_oltre_hard_deadline_no_fill():
    # done ma NESSUNO specchio (runner morto prima di specchiare) e nessun bet_id
    # → oltre TTL+grace l'esito non è conoscibile: NO-FILL (AUDIT 11/09 H-12),
    # mai un fill inventato ai dati della riserva 100 s dopo la decisione
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_flumine(db, market)                # nessuna riga specchio
    S.run_once(market=market, db=db,
               now=NOW + timedelta(seconds=45 + S.FLUMINE_CANCEL_GRACE_S + 5))
    t = db.trades[0]
    assert t["status"] == "error"
    assert t["meta"]["reason"] == "flumine_no_mirror_after_ttl"
    reasons = [p.get("reason") for k, p in db.activity if k == "flumine_no_fill"]
    assert "no_mirror_after_ttl" in reasons


def test_cancel_in_errore_risolve_col_matched():
    # cancel 'error' (ordine sparito dal blotter) → si risolve subito col matched
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_flumine(db, market)
    db.mirrors[f"awlq{rid}"] = _mirror(1.5, 111.0, "EXECUTABLE", t["size"] - 1.5)
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=60))   # → cancel
    crid = db.trades[0]["meta"]["flumine_cancel_request_id"]
    db.queue[crid]["status"] = "error"
    db.queue[crid]["error"] = "ordine non trovato nel blotter"
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=70))
    t = db.trades[0]
    assert t["status"] == "open" and t["size"] == 1.5 and t["price"] == 111.0


# ---------------------------------------------------------------------------
# Riconciliazione e settlement NON toccano i pending flumine
# ---------------------------------------------------------------------------
def test_reconcile_pending_non_conferma_i_flumine_wait():
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    _placed_flumine(db, market)
    db.queue[1]["status"] = "pending"                   # fill non ancora arrivato
    n = S.reconcile_pending(market=market, db=db, now=NOW)
    assert n == 0
    assert db.trades[0]["status"] == "pending"          # NON confermato dai dati riserva


def test_reconcile_pending_paper_legacy_confermato_solo_se_eseguito():
    # i pending paper SENZA flumine_request_id restano del reconcile. CANTIERE C
    # (28/09): si confermano SOLO se il simulatore legacy li ha eseguiti (fonte
    # vera del paper, come Betfair per il live); prima si confermavano sempre.
    db = FakeQueueDB(_control())
    db.trades = [{"id": 1, "event_id": "1.100", "market_id": "m1", "selection_id": 4,
                  "side": "lay", "mode": "paper", "price": 110, "size": 5,
                  "liability": 545, "status": "pending", "placed_at": NOW.isoformat()}]
    db._id = 1
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S._ricorda_ordine_paper(1, market_id="m1", selection_id=4, side="lay",
                            size=5.0, price=110.0, now=NOW)
    n = S.reconcile_pending(market=market, db=db, now=NOW)
    assert n == 1 and db.trades[0]["status"] == "open"


# ---------------------------------------------------------------------------
# LIVE: mai nulla in coda (il percorso live è INTOCCATO)
# ---------------------------------------------------------------------------
def test_live_auto_non_accoda_mai():
    db = FakeQueueDB(_control(mode="live"))             # runner PAPER perfetto attivo
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 1
    assert len(market.placed) == 1                      # REST place_lay_live chiamato
    assert len(db.queue) == 0                           # coda MAI toccata in live
    assert db.trades[0]["status"] == "open" and db.trades[0]["bet_id"] == "b1"


def test_live_manuale_non_accoda_mai():
    db = FakeQueueDB(_control(status="idle"))
    db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-1.100",
                                  "selection_id": 4, "side": "lay", "mode": "live",
                                  "price": 110, "size": 2})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert len(market.placed) == 1                      # FOK REST invariato
    assert len(db.queue) == 0                           # mai in coda
    assert db.trades[0]["mode"] == "live" and db.trades[0]["bet_id"] == "bm1"


# ---------------------------------------------------------------------------
# FIX review 16/07 (F1/F2/F4): crash window, aggregati, zombie
# ---------------------------------------------------------------------------
def test_f1_marker_persistito_prima_dell_enqueue():
    """F1: il marker flumine_client_ref deve essere già sul trade QUANDO parte
    l'enqueue — un crash tra le due scritture resta riconoscibile/recuperabile."""
    class _OrderCheckDB(FakeQueueDB):
        def __init__(self, control):
            super().__init__(control)
            self.marker_at_enqueue = "MAI-CHIAMATO"

        def enqueue_live_order(self, payload):
            pend = [t for t in self.trades if t.get("status") == "pending"]
            meta = (pend[0].get("meta") or {}) if pend else {}
            self.marker_at_enqueue = meta.get("flumine_client_ref")
            return super().enqueue_live_order(payload)

    db = _OrderCheckDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert db.marker_at_enqueue == f"omega-t{db.trades[0]['id']}"


def test_f1_enqueue_ko_ripristina_meta_e_non_esegue():
    """Enqueue KO e richiesta MAI creata: nessun ordine simulato esiste.
    CANTIERE C (28/09): prima il chiamante confermava col fill legacy; ora
    l'apertura e' NON eseguita e la riserva si chiude (nessun marker resta)."""
    db = FakeQueueDB(_control())
    db.enqueue_raises = True
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert not [t for t in db.trades if "flumine_client_ref" in (t.get("meta") or {})
                and t.get("status") == "pending"]
    _non_eseguita(db, "enqueue_failed")


def test_f1_enqueue_ko_ma_richiesta_gia_creata_viene_adottata():
    """Risposta persa DOPO l'insert idempotente: la richiesta esistente per
    client_ref viene ADOTTATA (mai doppia esecuzione legacy+flumine)."""
    db = FakeQueueDB(_control())
    tid = db.insert_trade({"event_id": "E9", "market_id": "1.9", "selection_id": 1,
                           "side": "lay", "mode": "paper", "status": "pending",
                           "price": 50.0, "size": 1.0, "liability": 49.0,
                           "meta": {}})
    db.queue[41] = {"id": 41, "status": "pending",
                    "payload": {"client_ref": f"omega-t{tid}"}}
    db._rid = 41
    db.enqueue_raises = True
    rid = S._flumine_enqueue_place(
        db=db, trade_id=tid, event_id="E9", market_id="1.9", selection_id=1,
        side="lay", price=50.0, size=1.0, base_meta={}, now=NOW)
    assert rid == 41
    tr = next(t for t in db.trades if t["id"] == tid)
    assert tr["meta"]["flumine_request_id"] == 41


def test_recovery_orfano_adotta_request_per_client_ref():
    """Poll: pending con marker ma senza request_id (crash) → adozione della
    richiesta esistente; al giro dopo si risolve normalmente."""
    db = FakeQueueDB(_control())
    tid = db.insert_trade({"event_id": "E9", "market_id": "1.9", "selection_id": 1,
                           "side": "lay", "mode": "paper", "status": "pending",
                           "price": 50.0, "size": 1.0, "liability": 49.0,
                           "meta": {"flumine_client_ref": None,
                                    "flumine_enqueued_at": NOW.isoformat()}})
    tr = next(t for t in db.trades if t["id"] == tid)
    tr["meta"]["flumine_client_ref"] = f"omega-t{tid}"
    db.queue[7] = {"id": 7, "status": "done",
                   "payload": {"client_ref": f"omega-t{tid}"}}
    S.poll_flumine_paper(db=db, params={}, now=NOW)
    assert tr["meta"]["flumine_request_id"] == 7
    assert tr["status"] == "pending"                   # risolto al giro dopo


def test_recovery_orfano_senza_richiesta_no_fill():
    # AUDIT 11/09 (H-12): la richiesta non è MAI stata creata → nessun ordine
    # simulato è esistito → NO-FILL (prima: fill pieno al prezzo della riserva)
    db = FakeQueueDB(_control())
    tid = db.insert_trade({"event_id": "E9", "market_id": "1.9", "selection_id": 1,
                           "side": "lay", "mode": "paper", "status": "pending",
                           "price": 50.0, "size": 1.0, "liability": 49.0,
                           "meta": {"flumine_client_ref": f"omega-t999"}})
    S.poll_flumine_paper(db=db, params={}, now=NOW)
    tr = next(t for t in db.trades if t["id"] == tid)
    assert tr["status"] == "error"
    assert tr["meta"]["reason"] == "flumine_request_missing"
    assert tr["meta"]["error_final"] is True


def test_f4_eta_non_calcolabile_risolve_subito_mai_zombie():
    """F4: riga malformata senza timestamp → hard deadline IMMEDIATA (il
    pending non può restare zombie escluso anche dal reconcile)."""
    db = FakeQueueDB(_control())
    tid = db.insert_trade({"event_id": "E9", "market_id": "1.9", "selection_id": 1,
                           "side": "lay", "mode": "paper", "status": "pending",
                           "price": 50.0, "size": 1.0, "liability": 49.0,
                           "meta": {"flumine_client_ref": f"omega-tX",
                                    "flumine_request_id": 5}})
    db.queue[5] = {"id": 5, "status": "done", "payload": {"client_ref": "omega-tX"}}
    tr = next(t for t in db.trades if t["id"] == tid)
    tr["placed_at"] = None                             # riga davvero malformata
    S.poll_flumine_paper(db=db, params={}, now=NOW)
    assert tr["status"] in ("open", "error")           # risolto SUBITO, mai pending


def test_f2_aggregati_contano_i_pending_flumine():
    """F2: il pending in attesa del fill flumine occupa il posto (max_events /
    liability) — l'ordine simulato È sul book del runner."""
    from Betfair.omega import omega_engine as E

    rows = [{"status": "pending", "liability": 49.0, "placed_at": NOW.isoformat(),
             "meta": {"flumine_client_ref": "omega-t1"}}]
    agg = E.aggregate_trades(rows, day_start=NOW - timedelta(hours=1))
    assert agg["matches_traded"] == 1
    assert agg["matches_traded_today"] == 1
    assert agg["open_liability"] == 49.0
    # pending SENZA marker né bet_id: come prima, NON conta
    agg0 = E.aggregate_trades([{"status": "pending", "liability": 49.0,
                                "meta": {}}], day_start=None)
    assert agg0["matches_traded"] == 0
