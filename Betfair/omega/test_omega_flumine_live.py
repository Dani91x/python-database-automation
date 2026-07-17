"""Test dell'esecuzione LIVE via flumine (COSTITUZIONE §6-bis v2, 2026-07-17):
gate live fail-closed su ogni condizione, INVARIANTE SUPREMO cross-mode (paper
mai live e viceversa), FOK vero nel payload (timeInForce=FILL_OR_KILL), kill-
switch ``omega_live_via_flumine``, fallback REST legacy su runner morto,
deadline → riconciliazione REST/revoca (mai zombie), aggregati coi pending
live, select ``meta`` in omega_db.aggregates (F2), keepAlive proattivo.

Riusa FakeQueueDB (coda+specchio simulati) e i fake di test_omega_service.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from Betfair.omega import omega_engine as E
from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_flumine_paper import FakeQueueDB, _mirror, _params
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


def _live_db(**kw):
    """FakeQueueDB con omega in LIVE e runner in order mode LIVE (gate ok)."""
    kw.setdefault("hb_mode", "LIVE")
    return FakeQueueDB(_control(mode="live"), **kw)


def _live_mirror(size_matched, avg, status, remaining, bet_id="lb1"):
    return {**_mirror(size_matched, avg, status, remaining, bet_id=bet_id),
            "mode": "live"}


def _placed_live(db, market):
    """Piazza il lay auto LIVE via coda flumine e ritorna (trade, rid)."""
    S.run_once(market=market, db=db, now=NOW)
    t = db.trades[0]
    rid = t["meta"]["flumine_request_id"]
    db.queue[rid]["status"] = "done"
    return t, rid


# ---------------------------------------------------------------------------
# Whitelist parametri (kill-switch / deadline)
# ---------------------------------------------------------------------------
def test_config_kill_switch_e_deadline():
    assert _params()["omega_live_via_flumine"] is True                    # default ON
    assert _params(omega_live_via_flumine=False)["omega_live_via_flumine"] is False
    assert _params(omega_live_via_flumine="false")["omega_live_via_flumine"] is False
    assert _params()["live_fill_deadline_s"] == 20                        # default
    assert _params(live_fill_deadline_s=1)["live_fill_deadline_s"] == 5   # clamp min
    assert _params(live_fill_deadline_s=9999)["live_fill_deadline_s"] == 300  # clamp max


# ---------------------------------------------------------------------------
# Gate LIVE — fail-closed su OGNI condizione
# ---------------------------------------------------------------------------
def test_gate_live_ok():
    ok, reason = S._flumine_gate("1.100", db=_live_db(), mode="live",
                                 params=_params(), now=NOW)
    assert ok and reason == "ok"


@pytest.mark.parametrize("kw,mode,params,expected", [
    ({}, "live", {"omega_live_via_flumine": False}, "live_via_flumine_off"),  # kill-switch
    ({}, "live", {"execution_mode": "rest"}, "execution_mode_rest"),          # forza legacy
    ({"hb_mode": "PAPER"}, "live", {}, "runner_mode_non_live"),   # runner in PAPER
    ({"hb_mode": "OFF"}, "live", {}, "runner_mode_non_live"),     # ordini spenti
    ({"hb_mode": None}, "live", {}, "runner_mode_non_live"),      # heartbeat assente
    ({"hb_age_s": 300}, "live", {}, "runner_heartbeat_stantio"),  # runner morto
    ({"follow_status": None}, "live", {}, "follow_assente"),      # evento non seguito
    ({"follow_status": "PENDING"}, "live", {}, "follow_pending"), # non STREAMING
    ({}, "LIVE", {}, "mode_sconosciuto"),                         # mode fuori whitelist
    ({}, "yolo", {}, "mode_sconosciuto"),
    ({}, "paper", {}, "runner_mode_non_paper"),                   # cross: paper su runner LIVE
])
def test_gate_live_combinazioni_ko(kw, mode, params, expected):
    kw.setdefault("hb_mode", "LIVE")
    db = FakeQueueDB(_control(mode="live"), **kw)
    ok, reason = S._flumine_gate("1.100", db=db, mode=mode,
                                 params=_params(**params), now=NOW)
    assert not ok and reason == expected


def test_gate_live_db_senza_coda():
    ok, reason = S._flumine_gate("1.100", db=FakeDB(_control(mode="live")),
                                 mode="live", params=_params(), now=NOW)
    assert not ok and reason == "db_senza_coda"


def test_gate_live_db_senza_revoca():
    # senza il contratto di revoca niente anti-zombie → gate chiuso (fail-closed)
    db = _live_db()
    db.revoke_live_order_request = None
    ok, reason = S._flumine_gate("1.100", db=db, mode="live",
                                 params=_params(), now=NOW)
    assert not ok and reason == "db_senza_revoca"


def test_gate_live_eccezione_fail_closed():
    db = _live_db()

    def _boom(_):
        raise RuntimeError("db down")

    db.live_follow_status = _boom
    ok, reason = S._flumine_gate("1.100", db=db, mode="live",
                                 params=_params(), now=NOW)
    assert not ok and reason.startswith("gate_error:")


# ---------------------------------------------------------------------------
# Enqueue LIVE col gate ok — FOK VERO nel payload, mode dal trade
# ---------------------------------------------------------------------------
def test_live_auto_gate_ok_accoda_fok():
    db = _live_db()
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 1
    assert len(market.placed) == 0                      # NESSUN place REST
    t = db.trades[0]
    assert t["status"] == "pending" and t["mode"] == "live"
    assert t["meta"]["phase"] == "flumine_wait"
    row = db.queue[t["meta"]["flumine_request_id"]]["payload"]
    assert row["mode"] == "live"                        # deriva SOLO dal mode del trade
    assert row["time_in_force"] == "FILL_OR_KILL"       # FOK VERO: lo esegue Betfair
    assert row["action"] == "place" and row["side"] == "lay"
    assert row["client_ref"] == f"omega-t{t['id']}"
    assert not any(k == "live_fok_fallback" for k, _ in db.activity)


def test_manuale_live_gate_ok_accoda_fok():
    db = FakeQueueDB(_control(status="idle", mode="live"), hb_mode="LIVE")
    db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-1.100",
                                  "selection_id": 4, "side": "lay", "mode": "live",
                                  "price": 110, "size": 2})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert db.manual_reqs[0]["status"] == "done"
    assert db.manual_reqs[0]["result"]["pending_fill"] is True
    t = db.trades[0]
    assert t["status"] == "pending" and t["mode"] == "live"
    payload = db.queue[1]["payload"]
    assert payload["mode"] == "live"
    assert payload["time_in_force"] == "FILL_OR_KILL"
    assert len(market.placed) == 0                      # niente REST


# ---------------------------------------------------------------------------
# INVARIANTE SUPREMO — cross-mode MAI (paper→mai live, live→mai paper)
# ---------------------------------------------------------------------------
def test_invariante_paper_mai_richieste_live():
    """Un trade paper non produce MAI una richiesta mode='live' (né FOK)."""
    db = FakeQueueDB(_control(mode="paper"))            # runner PAPER, gate paper ok
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert len(db.queue) == 1
    payload = db.queue[1]["payload"]
    assert payload["mode"] == "paper"
    assert "time_in_force" not in payload               # il FOK vero è SOLO live

def test_invariante_paper_su_runner_live_niente_coda():
    # omega paper + runner in LIVE: gate chiuso → fill legacy, coda MAI toccata
    db = FakeQueueDB(_control(mode="paper"), hb_mode="LIVE")
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert len(db.queue) == 0
    assert db.trades[0]["status"] == "open"             # fill legacy paper INVARIATO


def test_invariante_live_su_runner_paper_rest_legacy():
    # omega live + runner in PAPER: MAI una richiesta (di nessun mode) → REST FOK
    db = FakeQueueDB(_control(mode="live"), hb_mode="PAPER")
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert len(db.queue) == 0
    assert len(market.placed) == 1                      # REST FOK legacy
    assert db.trades[0]["status"] == "open" and db.trades[0]["bet_id"] == "b1"
    reasons = [p.get("reason") for k, p in db.activity if k == "live_fok_fallback"]
    assert "runner_mode_non_live" in reasons


def test_enqueue_mode_fuori_whitelist_rifiutato():
    db = _live_db()
    tid = db.insert_trade({"event_id": "E1", "market_id": "1.1", "selection_id": 1,
                           "side": "lay", "mode": "live", "status": "pending",
                           "price": 50.0, "size": 1.0, "liability": 49.0, "meta": {}})
    rid = S._flumine_enqueue_place(db=db, trade_id=tid, event_id="E1",
                                   market_id="1.1", selection_id=1, side="lay",
                                   price=50.0, size=1.0, base_meta={}, now=NOW,
                                   mode="LIVE!")        # mode inventato
    assert rid is None
    assert len(db.queue) == 0                           # MAI accodato


# ---------------------------------------------------------------------------
# Kill-switch e fallback REST legacy
# ---------------------------------------------------------------------------
def test_kill_switch_off_live_legacy_puro():
    # runner LIVE PERFETTO ma omega_live_via_flumine=False → REST, coda vuota,
    # NESSUN log di fallback (scelta esplicita, non un degrado)
    db = FakeQueueDB(_control(mode="live",
                              params={"omega_live_via_flumine": False}),
                     hb_mode="LIVE")
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert len(db.queue) == 0
    assert len(market.placed) == 1                      # REST FOK legacy
    assert db.trades[0]["status"] == "open" and db.trades[0]["bet_id"] == "b1"
    assert not any(k == "live_fok_fallback" for k, _ in db.activity)


def test_live_runner_morto_fallback_rest():
    db = _live_db(hb_age_s=300)                         # heartbeat stantio
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 1
    assert len(db.queue) == 0
    assert len(market.placed) == 1                      # REST FOK legacy: mai bloccati
    assert db.trades[0]["status"] == "open"
    reasons = [p.get("reason") for k, p in db.activity if k == "live_fok_fallback"]
    assert "runner_heartbeat_stantio" in reasons


def test_live_enqueue_ko_accertato_fallback_rest():
    # enqueue KO e lookup by-ref PULITO (richiesta MAI creata) → REST sicuro
    db = _live_db()
    db.enqueue_raises = True
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert len(market.placed) == 1
    t = db.trades[0]
    assert t["status"] == "open" and t["bet_id"] == "b1"
    assert "flumine_client_ref" not in (t.get("meta") or {})
    reasons = [p.get("reason") for k, p in db.activity if k == "live_fok_fallback"]
    assert "enqueue_failed" in reasons


def test_live_enqueue_esito_ignoto_mai_rest():
    """Enqueue KO E lookup by-ref KO: la richiesta POTREBBE esistere → su soldi
    veri MAI il place REST (doppio ordine). Riserva pending col marker."""
    class _UnknownDB(FakeQueueDB):
        def get_live_order_request_by_ref(self, client_ref):
            raise RuntimeError("rete giù")

    db = _UnknownDB(_control(mode="live"), hb_mode="LIVE")
    db.enqueue_raises = True
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 1
    assert len(market.placed) == 0                      # MAI il place REST
    t = db.trades[0]
    assert t["status"] == "pending"
    assert t["meta"]["flumine_client_ref"] == f"omega-t{t['id']}"


# ---------------------------------------------------------------------------
# Conferma dall'order stream (specchio) e trade fallito come il FOK legacy
# ---------------------------------------------------------------------------
def test_live_conferma_fill_da_specchio_order_stream():
    db = _live_db()
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_live(db, market)
    size = t["size"]
    db.mirrors[f"awlq{rid}"] = _live_mirror(size, 112.0, "EXECUTION_COMPLETE", 0.0)
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=5))
    t = db.trades[0]
    assert t["status"] == "open"
    assert t["price"] == 112.0                          # prezzo medio REALE dall'order stream
    assert t["size"] == size
    assert t["bet_id"] == "lb1"
    assert t["meta"]["fill"] == "flumine_live"
    assert len(market.placed) == 0                      # mai un secondo ordine


def test_live_fok_ucciso_senza_fill_trade_error():
    # matched 0 + EXECUTION_COMPLETE = FOK ucciso da Betfair → stesso esito
    # del legacy live_not_matched: riserva a 'error', evento consumato
    db = _live_db()
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_live(db, market)
    db.mirrors[f"awlq{rid}"] = _live_mirror(0.0, 0.0, "EXECUTION_COMPLETE", 0.0)
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=5))
    t = db.trades[0]
    assert t["status"] == "error"
    assert t["meta"]["reason"] == "flumine_live_fok_execution_complete"
    assert len(market.placed) == 0                      # MAI ripiazzato


def test_live_specchio_paper_ignorato():
    # uno specchio mode='paper' sotto lo stesso ref NON conferma mai un trade live
    db = _live_db()
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_live(db, market)
    db.mirrors[f"awlq{rid}"] = _mirror(t["size"], 112.0, "EXECUTION_COMPLETE", 0.0)
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=5))
    assert db.trades[0]["status"] == "pending"          # cross-mode: mai letto


def test_live_richiesta_error_senza_specchio_trade_error():
    # worker rifiuta PRIMA del place (violation): nessun ordine reale → error.
    # FIX 17/07: deciso SOLO oltre la hard deadline (dentro si aspetta sempre
    # lo specchio: l'errore della coda potrebbe essere post-place).
    db = _live_db()
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_live(db, market)
    db.queue[rid]["status"] = "error"
    db.queue[rid]["error"] = "place RIFIUTATO — violation"
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=5))
    assert db.trades[0]["status"] == "pending"  # dentro la deadline: si aspetta
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=30))
    t = db.trades[0]
    assert t["status"] == "error"
    assert t["meta"]["reason"].startswith("flumine_live_request_error")


# ---------------------------------------------------------------------------
# Hard deadline: riconciliazione REST per bet_id / revoca / alert (mai zombie)
# ---------------------------------------------------------------------------
def test_live_deadline_rest_conferma_per_bet_id():
    db = _live_db()
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_live(db, market)
    db.queue[rid]["bet_id"] = "bx9"                     # bet_id noto, specchio MUTO
    market.order_state_by_bet_id = lambda b: {
        "found": True, "size_matched": 3.0,
        "avg_price_matched": 108.0, "size_remaining": 0.0}
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=30))  # > deadline 20s
    t = db.trades[0]
    assert t["status"] == "open"
    assert t["size"] == 3.0 and t["price"] == 108.0     # verità REST
    assert t["bet_id"] == "bx9"


def test_live_deadline_rest_senza_fill_trade_error():
    db = _live_db()
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_live(db, market)
    db.queue[rid]["bet_id"] = "bx9"
    market.order_state_by_bet_id = lambda b: {
        "found": True, "size_matched": 0.0,
        "avg_price_matched": None, "size_remaining": 0.0}
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=30))
    t = db.trades[0]
    assert t["status"] == "error"
    assert t["meta"]["reason"] == "flumine_live_rest_no_fill"


def test_live_deadline_richiesta_mai_presa_revocata():
    """Richiesta rimasta 'pending' (runner giù) oltre la deadline → REVOCA
    atomica: il runner tornato vivo ORE dopo non può piazzare l'ordine stantio."""
    db = _live_db()
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)           # enqueue (resta 'pending')
    t = db.trades[0]
    rid = t["meta"]["flumine_request_id"]
    assert db.queue[rid]["status"] == "pending"
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=30))
    assert db.queue[rid]["status"] == "error"           # revocata: MAI più eseguibile
    t = db.trades[0]
    assert t["status"] == "error"
    assert t["meta"]["reason"] == "flumine_live_revoked_deadline"
    assert len(market.placed) == 0                      # nessun ordine reale


def test_live_deadline_esito_ignoto_alert_una_volta_resta_pending():
    """done senza specchio né bet_id (esito DAVVERO ignoto sui soldi veri):
    MAI esiti inventati → alert CRITICAL UNA volta, resta pending in verifica."""
    db = _live_db()
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_live(db, market)                   # done, nessun bet_id/specchio
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=30))
    t = db.trades[0]
    assert t["status"] == "pending"                     # mai confermato coi dati riserva
    assert t["meta"]["live_orphan_alerted"] is True
    assert sum(1 for k, _ in db.activity if k == "flumine_live_orphan") == 1
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=60))
    assert sum(1 for k, _ in db.activity if k == "flumine_live_orphan") == 1  # una sola escalation


# ---------------------------------------------------------------------------
# Recovery F1 (crash tra enqueue e persistenza) — versione LIVE
# ---------------------------------------------------------------------------
def test_live_recovery_orfano_adotta_richiesta_esistente():
    db = _live_db()
    tid = db.insert_trade({"event_id": "E9", "market_id": "1.9", "selection_id": 1,
                           "side": "lay", "mode": "live", "status": "pending",
                           "price": 50.0, "size": 1.0, "liability": 49.0,
                           "meta": {"flumine_client_ref": "omega-t7",
                                    "flumine_enqueued_at": NOW.isoformat()}})
    db.queue[7] = {"id": 7, "status": "done",
                   "payload": {"client_ref": "omega-t7"}}
    S.poll_flumine_pending(db=db, params={}, now=NOW)
    tr = next(t for t in db.trades if t["id"] == tid)
    assert tr["meta"]["flumine_request_id"] == 7        # adottata (mai doppio ordine)
    assert tr["status"] == "pending"


def test_live_recovery_orfano_senza_richiesta_libera_la_riserva():
    # richiesta MAI creata → nessun ordine reale può esistere → riserva LIBERATA
    # (come il reconcile 'free'), MAI conferme inventate
    db = _live_db()
    tid = db.insert_trade({"event_id": "E9", "market_id": "1.9", "selection_id": 1,
                           "side": "lay", "mode": "live", "status": "pending",
                           "price": 50.0, "size": 1.0, "liability": 49.0,
                           "meta": {"flumine_client_ref": "omega-t999"}})
    n = S.poll_flumine_pending(db=db, params={}, now=NOW)
    assert n == 1
    assert all(t["id"] != tid for t in db.trades)       # riga eliminata (free)
    assert any(k == "flumine_live_freed" for k, _ in db.activity)


# ---------------------------------------------------------------------------
# Riconciliazione legacy: NON tocca i pending live via flumine
# ---------------------------------------------------------------------------
def test_reconcile_non_tocca_i_live_flumine():
    """Un LIVE piazzato dal runner non porta il ref omega-*: il reconcile REST
    lo darebbe per mai piazzato ('error' se vecchio) mentre l'ordine ESISTE.
    Il poll (con deadline) è il solo proprietario di quei pending."""
    db = _live_db()
    tid = db.insert_trade({"event_id": "1.100", "market_id": "m1", "selection_id": 4,
                           "side": "lay", "mode": "live", "price": 110, "size": 5,
                           "liability": 545, "status": "pending",
                           "meta": {"flumine_request_id": 1,
                                    "flumine_client_ref": "omega-t1"}})
    tr = next(t for t in db.trades if t["id"] == tid)
    tr["placed_at"] = (NOW - timedelta(hours=25)).isoformat()  # il legacy lo darebbe 'error'
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    n = S.reconcile_pending(market=market, db=db, now=NOW)
    assert n == 0
    assert tr["status"] == "pending"                    # intoccato: è del poll


def test_reconcile_pending_live_legacy_ancora_gestito():
    # regressione: un pending live SENZA marker flumine resta del reconcile REST
    db = _live_db()
    db.trades = [{"id": 1, "event_id": "1.100", "market_id": "m1", "selection_id": 4,
                  "side": "lay", "mode": "live", "price": 110, "size": 5,
                  "liability": 545, "status": "pending",
                  "placed_at": (NOW - timedelta(seconds=300)).isoformat(), "meta": {}}]
    db._id = 1
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    n = S.reconcile_pending(market=market, db=db, now=NOW)
    assert n == 1
    assert db.trades == []                              # 'free': mai piazzato, liberato


# ---------------------------------------------------------------------------
# Aggregati: i pending LIVE in attesa dell'esito flumine CONTANO (F2)
# ---------------------------------------------------------------------------
def test_aggregati_contano_pending_live_flumine():
    rows = [{"status": "pending", "mode": "live", "liability": 49.0,
             "placed_at": NOW.isoformat(),
             "meta": {"flumine_client_ref": "omega-t1"}}]
    agg = E.aggregate_trades(rows, day_start=NOW - timedelta(hours=1))
    assert agg["matches_traded"] == 1
    assert agg["matches_traded_today"] == 1
    assert agg["open_liability"] == 49.0                # liability reale in attesa CONTA


def test_omega_db_aggregates_select_include_meta_e_mode(monkeypatch):
    """F2 HIGH (review): la select di omega_db.aggregates DEVE portare 'meta'
    (e 'mode') — senza, aggregate_trades non vede meta.flumine_client_ref e il
    conteggio dei pending flumine è dead code coi dati reali. Il test cattura
    la stringa della select: non deve MAI più regredire."""
    from Betfair.omega import omega_db

    captured: dict[str, str] = {}

    class _Query:
        def __init__(self, table_name):
            self._table = table_name

        def select(self, cols):
            captured[self._table] = cols
            return self

        def execute(self):
            class _Res:
                data: list = []
            return _Res()

    class _FakeSB:
        def table(self, name):
            return _Query(name)

    monkeypatch.setattr(omega_db, "get_supabase_client", lambda: _FakeSB())
    agg = omega_db.aggregates()
    cols = [c.strip() for c in captured["omega_trades"].split(",")]
    assert "meta" in cols
    assert "mode" in cols
    assert agg["matches_traded"] == 0                   # nessuna riga: aggregato vuoto


# ---------------------------------------------------------------------------
# keepAlive proattivo (~600s): il retry reattivo resta solo rete di sicurezza
# ---------------------------------------------------------------------------
def test_keepalive_proattivo_rispetta_l_intervallo():
    class _KA:
        def __init__(self):
            self.calls = 0

        def keep_alive(self):
            self.calls += 1

    m = _KA()
    last = S._maybe_keepalive(m, float("-inf"), now_ts=1000.0)
    assert last == 1000.0 and m.calls == 1              # primo giro: subito
    last = S._maybe_keepalive(m, last, now_ts=1000.0 + S.KEEPALIVE_EVERY_S - 1)
    assert m.calls == 1                                  # non ancora ora
    last = S._maybe_keepalive(m, last, now_ts=1000.0 + S.KEEPALIVE_EVERY_S)
    assert m.calls == 2
    assert last == 1000.0 + S.KEEPALIVE_EVERY_S


def test_keepalive_ko_non_ferma_il_loop():
    class _Boom:
        def keep_alive(self):
            raise RuntimeError("sessione giù")

    last = S._maybe_keepalive(_Boom(), float("-inf"), now_ts=5.0)
    assert last == 5.0                                   # KO assorbito, timestamp avanzato


def test_keepalive_market_senza_metodo_no_crash():
    market = FakeMarket([], _cs(), _open_snapshot())     # nessun keep_alive
    assert S._maybe_keepalive(market, float("-inf"), now_ts=5.0) == 5.0


# ---------------------------------------------------------------------------
# ⚠️ ADVERSARIAL FINDING (review 17/07, CRITICAL, NON FIXATO): il case-2 di
# ``_poll_one_flumine_live_trade`` ("richiesta in ERRORE senza specchio") tratta
# QUALUNQUE riga coda con status='error' + mirror assente + bet_id assente come
# PROVA che nessun ordine reale esiste — e lo fa SUBITO, PRIMA della hard
# deadline (``live_fill_deadline_s``) e SENZA aspettare lo specchio (order
# stream, l'UNICA fonte davvero autoritativa). Ma ``market.place_order`` di
# flumine ritorna True/False solo per la validazione dei trading control: la
# transazione viene poi ESEGUITA in modo ASINCRONO (execution queue del client,
# thread separato) — un ordine può essere REALMENTE in volo o già eseguito su
# Betfair anche se il worker (``live_order_worker._do_place``) fallisce DOPO
# ``_place_or_raise`` (es. l'update Supabase di '_write_done' va in timeout e
# l'except a monte scrive 'error' via ``_write_error``, che NON cattura mai
# bet_id/ordine perché non li riceve). Lo specchio (scritto da
# ``LiveTradingStrategy.process_orders``) è un percorso indipendente e può
# arrivare DOPO che il poll ha già liberato la riserva a 'error': una volta
# 'error' il trade esce per sempre da ``list_trades('pending')`` — NESSUN
# riconciliazione successiva lo recupera, anche se lo specchio poi mostra un
# fill REALE. Risultato: un ordine live REALMENTE matchato può finire
# contabilizzato come "mai piazzato" (liability/P&L/aggregati NON lo vedono),
# in violazione diretta dell'invariante "mai void/error automatico che sblocchi
# la liability con un ordine potenzialmente vivo" (COSTITUZIONE §6-bis).
#
# FIX 17/07 (post-review): il case-2 decide SOLO oltre la hard deadline, e un
# errore marcato ``post_place:`` dal worker (contratto: fallimento DOPO il
# dispatch dell'ordine) non libera MAI la riserva — cade nel ramo CRITICAL
# "esito ignoto" e resta pending finché lo specchio non porta la verità.
# I tre test sotto PINNANO il comportamento corretto.
# ---------------------------------------------------------------------------
def test_error_post_place_senza_specchio_mai_liberato_poi_confermato_dal_mirror():
    db = _live_db()
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_live(db, market)  # enqueued, coda 'done' (place accettato)

    # Il worker piazza DAVVERO l'ordine ma fallisce DOPO il dispatch (es.
    # timeout su _write_done): la riga coda finisce 'error' col prefisso
    # contrattuale post_place: e senza bet_id.
    db.queue[rid]["status"] = "error"
    db.queue[rid]["error"] = "post_place:APIError: timeout scrivendo il risultato"
    db.queue[rid]["bet_id"] = None

    # BEN PRIMA della hard deadline: NIENTE viene deciso (si aspetta lo specchio).
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=2))
    assert db.trades[0]["status"] == "pending"

    # OLTRE la deadline, ancora senza specchio: MAI liberare — alert CRITICAL
    # una volta sola, il trade resta pending in verifica.
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=30))
    t = db.trades[0]
    assert t["status"] == "pending"
    assert t["meta"].get("live_orphan_alerted") is True
    assert any(k == "flumine_live_orphan" for k, _ in db.activity)

    # Lo specchio arriva (in ritardo) con il fill REALE: riconciliato coi
    # numeri veri, mai persi.
    db.mirrors[f"awlq{rid}"] = _live_mirror(t.get("size") or 40.0, 110.0,
                                            "EXECUTION_COMPLETE", 0.0,
                                            bet_id="REAL_ORDER_RICONCILIATO")
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=120))
    t2 = db.trades[0]
    assert t2["status"] == "open"
    assert t2.get("bet_id") == "REAL_ORDER_RICONCILIATO"


def test_error_pre_place_liberato_solo_oltre_deadline():
    db = _live_db()
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_live(db, market)

    # Errore di VALIDAZIONE (pre-place, nessun prefisso): nessun ordine esiste.
    db.queue[rid]["status"] = "error"
    db.queue[rid]["error"] = "violation: EXPOSURE_LIMIT_EXCEEDED"
    db.queue[rid]["bet_id"] = None

    # Dentro la deadline non si decide comunque (lo specchio ha priorità).
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=2))
    assert db.trades[0]["status"] == "pending"

    # Oltre la deadline: riserva liberata a 'error' come il FOK legacy.
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=30))
    t = db.trades[0]
    assert t["status"] == "error"
    assert t["meta"]["reason"].startswith("flumine_live_request_error")


def test_error_post_place_con_mirror_terminale_conferma_normale():
    db = _live_db()
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_live(db, market)

    # Worker fallito post-place MA lo specchio è già arrivato (caso comune):
    # il case-1 (terminale dallo stream) risolve coi fill reali, l'errore
    # della riga coda è irrilevante.
    db.queue[rid]["status"] = "error"
    db.queue[rid]["error"] = "post_place:APIError: timeout scrivendo il risultato"
    db.queue[rid]["bet_id"] = None
    db.mirrors[f"awlq{rid}"] = _live_mirror(t.get("size") or 40.0, 110.0,
                                            "EXECUTION_COMPLETE", 0.0,
                                            bet_id="lb_real")
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=2))
    t2 = db.trades[0]
    assert t2["status"] == "open"
    assert t2.get("bet_id") == "lb_real"
