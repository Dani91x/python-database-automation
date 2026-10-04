"""CANTIERE P (28/09/2026) - SAFE E CHIUSURE: NESSUN FILL DI CASA IN PAPER.

Ordine dell'utente: «deve essere lo specchio per tutti i bot». Fino a oggi, con
il runner non raggiungibile (gate della coda chiuso, canale giu' su una
chiusura), ``execution.place`` riempiva l'ordine PAPER in casa sul libro del
feed: istantaneo, senza bet delay, senza coda (riga S3 della tabella di
parita'); il sotto-minimo era un FOK diretto della size invece del
place-and-trim (riga S6); la chiusura senza size nota veniva rimandata solo in
paper (riga S7). Il live, negli stessi punti, va a Betfair.

Qui, dal codice di produzione (``X.place``, ``X.close_trade``,
``bot_service._execute``, ``run_once``), con i finti di ``test_bot_service``
(chiavi di ``safe_strategy_*``) e il runner paper finto (coda + specchio con le
chiavi di ``bot_db``):
  1. apertura paper senza runner = 'error' ``paper_senza_runner:<motivo>``,
     nessun ordine, e il budget ``place_max_attempts`` si CONSUMA come per un
     rifiuto in live;
  2. uscita paper senza runner = gamba 'error', uscita da RITENTARE (non
     inviata, non fallita per sempre), apertura ancora 'open'; col runner di
     nuovo su, l'uscita parte e la posizione si chiude;
  3. Safe TENNIS a canale spento e runner giu' (reperto F-1 del cantiere D2):
     stessa regola;
  4. ``execution_mode='rest'`` (scelta del pannello per i soldi veri) non
     spegne il paper: aperture e chiusure paper vanno comunque al runner;
  5. Mike riconosce ancora il motivo nuovo (``_NOTE_SENZA_RUNNER``);
  6. parita': lo stesso ordine paper (al runner) e live (REST) ha stesso lato,
     prezzo, size e FOK.
ASCII-only.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy.tests.test_bot_service import (
    NOW, FakeDB, FakeMarket, _auto_trade, _closings, _exit_feed_row, _poll_runner,
    _reset_module_state,
)


@pytest.fixture(autouse=True)
def _pulito():
    _reset_module_state()
    yield
    _reset_module_state()


def _riga(db, *, sport="calcio", event_id="1.1", market_id="m1", selection_id=7,
          side="back", price=3.0, size=5.0, mode="paper", signal_key="1.1:base:1-0"):
    row = {"event_id": event_id, "event_name": "Home v Away", "sport": sport,
           "strategy": "tennis" if sport == "tennis" else "base",
           "market_id": market_id, "market_type": "MATCH_ODDS",
           "selection_id": selection_id, "side": side, "price": price, "size": size,
           "liability": size, "status": "pending", "mode": mode, "commission": 0.05,
           "origin": "auto", "signal_key": signal_key, "pnl": 0.0,
           "meta": {"phase": "reserved"}}
    tid = db.insert_trade(dict(row))
    return tid, db.get_trade(tid)


def _esegui(db, tid, row, params=None, market=None):
    return S._execute(db=db, market=market or FakeMarket(), trade_id=tid, row=row,
                      params=S.resolve_params(params or {}), now=NOW, best_size=100.0,
                      ladder=(), feed_prices=None)


# ---------------------------------------------------------------------------
# 1. apertura paper senza runner
# ---------------------------------------------------------------------------
def test_apertura_paper_senza_runner_non_eseguita_e_NON_consuma_il_tentativo():
    """Correzione del coordinatore (28/09, brief standard par. 2 punti 6-7): il
    runner non raggiungibile NON e' un rifiuto del mercato. La riga si chiude
    col motivo, ma nessun tentativo si consuma e il segnale non si esaurisce:
    un runner giu' per pochi minuti non deve bruciare le partite idonee."""
    db = FakeDB()
    db.follow = "NONE"
    mk = FakeMarket()
    tid, row = _riga(db)
    out = _esegui(db, tid, row, market=mk)
    assert out.status == "error" and out.fill_note == "paper_senza_runner:follow_none"
    t = db.get_trade(tid)
    assert t["status"] == "error" and t["meta"]["error_final"] is True
    assert t["meta"]["reason"] == "paper_senza_runner:follow_none"
    assert t["meta"]["place"]["attempts"] == 0 and t["meta"]["place"]["final"] is False
    assert t["meta"]["place"]["senza_runner"] is True
    assert "fill" not in t["meta"] and mk.placed == [] and db.queue == []
    crit = [p for k, p in db.activity if k == "skip" and p.get("critical")]
    assert len(crit) == 1 and crit[0]["critical"] is True
    assert not [p for k, p in db.activity if k in ("place_retry", "place_exhausted")]
    # dieci esiti di fila: mai esaurito, e la riga critica al piu' 1 al minuto
    for i in range(10):
        tid, row = _riga(db)
        S._place_fail(db, tid, row, "paper_senza_runner:follow_none",
                      NOW + timedelta(seconds=i), S.resolve_params({}))
    assert S.place_allowed(db, NOW + timedelta(hours=1), {}, "1.1", "1.1:base:1-0") is None
    assert len([p for k, p in db.activity if k == "skip" and p.get("critical")]) == 1
    # prima del primo gradino del backoff (5 s) il segnale aspetta
    assert S.place_allowed(db, NOW + timedelta(seconds=10), {}, "1.1",
                           "1.1:base:1-0") == "place_backoff"


def test_runner_giu_per_cinque_giri_poi_su_l_apertura_parte_senza_tentativi_consumati():
    from Betfair.safe_strategy.tests.test_bot_service import FakeEngine, _feed_row, _signal

    db = FakeDB()
    db.follow = "NONE"
    eng = FakeEngine([_signal(key="1.1:base:1-0")])
    at = NOW
    for i in range(5):
        at = NOW + timedelta(seconds=6 * i)
        db.scan_rows = [_feed_row(updated_at=at)]
        S.run_once(db=db, market=FakeMarket(), engine=eng, now=at)
    giu = [t for t in db.trades if not t.get("closes_trade_id")]
    assert giu and all(t["status"] == "error" for t in giu)
    assert all(t["meta"]["reason"].startswith("paper_senza_runner") for t in giu)
    db.follow = "STREAMING"                       # il runner torna
    at = at + timedelta(seconds=6)
    db.scan_rows = [_feed_row(updated_at=at)]
    S.run_once(db=db, market=FakeMarket(), engine=eng, now=at)
    _poll_runner(db)
    aperte = [t for t in db.trades if t.get("status") == "open"]
    assert len(aperte) == 1, [(t["status"], t["meta"].get("reason")) for t in db.trades]
    st = S._PLACE_ATTEMPTS.get(S._place_key("1.1", "1.1:base:1-0")) or {}
    assert int(st.get("attempts") or 0) == 0, "nessun tentativo consumato dal runner giu'"


def test_tre_rifiuti_veri_del_mercato_restano_place_exhausted():
    db = FakeDB()
    for i in range(3):
        tid, row = _riga(db)
        S._place_fail(db, tid, row, "flumine_terminal_expired", NOW + timedelta(seconds=i),
                      S.resolve_params({}))
    assert S.place_allowed(db, NOW + timedelta(hours=1), {}, "1.1", "1.1:base:1-0") \
        == "place_exhausted"


def test_dopo_il_riavvio_le_righe_senza_runner_non_contano(monkeypatch):
    """Il seme dal DB: la funzione VERA ``bot_db.place_attempts`` sulle righe
    'error' (chiavi di ``safe_strategy_trades``) non riconta i
    ``paper_senza_runner`` come tentativi."""
    from Betfair.safe_strategy import bot_db

    def riga(i, reason, attempts, senza_runner=False, final=False):
        pl = {"attempts": attempts, "last_error": reason, "last_ts": NOW.isoformat(),
              "final": final}
        if senza_runner:
            pl["senza_runner"] = True
        return {"event_id": "1.1", "signal_key": f"1.1:base:{i}",
                "meta": {"reason": reason, "place": pl}}

    righe = [riga(1, "paper_senza_runner:follow_none", 0, True),
             riga(1, "paper_senza_runner:follow_none", 0, True),
             riga(1, "paper_senza_runner:follow_none", 0, True),
             riga(2, "flumine_terminal_expired", 3, final=True)]
    monkeypatch.setattr(bot_db, "_fetch_all", lambda q: righe)
    semi = bot_db.place_attempts()
    assert ("1.1", "1.1:base:1") not in semi
    assert semi[("1.1", "1.1:base:2")]["final"] is True

    class DbSeme(FakeDB):
        def place_attempts(self):
            return bot_db.place_attempts()

    db = DbSeme()
    S.seed_place_attempts(db, NOW.timestamp() + 10_000)
    assert S.place_allowed(db, NOW + timedelta(hours=1), {}, "1.1", "1.1:base:1") is None
    assert S.place_allowed(db, NOW + timedelta(hours=1), {}, "1.1", "1.1:base:2") \
        == "place_exhausted"


def test_apertura_paper_col_runner_va_in_coda_e_si_conferma_dal_poll():
    db = FakeDB()
    tid, row = _riga(db)
    out = _esegui(db, tid, row)
    assert out.status == "pending"
    q = db.queue[-1]
    assert (q["mode"], q["action"], q["time_in_force"]) == ("paper", "place", "FILL_OR_KILL")
    assert q["client_ref"] == f"safe-t{tid}"
    _poll_runner(db)
    t = db.get_trade(tid)
    assert t["status"] == "open" and t["size"] == 5.0 and t["meta"]["fill"] == "flumine_paper"


# ---------------------------------------------------------------------------
# 2. uscita paper senza runner: resta da ritentare, visibile
# ---------------------------------------------------------------------------
def test_uscita_paper_senza_runner_resta_da_ritentare_e_poi_esce():
    db = FakeDB(status="running")
    # 04/10/2026 (regola delle punte): lay 9@8.5 (non 10@8.5): la chiusura a 9.0 e' una
    # punta di 8,50 multipla di 0,50 (con 10 sarebbe 9,44 -> 9,00 + residuo 0,44 e la
    # posizione non tornerebbe 'hedged'); esposizione 9 * 7,5 = 67,50 (era 75,00)
    tid = _auto_trade(db, "base", size=9.0)
    db.follow = "NONE"
    # runner giu' per 2 minuti: giri ogni 6 s
    for s in range(0, 120, 6):
        at = NOW + timedelta(seconds=s)
        db.scan_rows = [_exit_feed_row(80, 1, 0, updated_at=at)]
        S.run_once(db=db, market=FakeMarket(), engine=None, now=at)
    # nessuna gamba riservata a ogni ritentativo: la chiusura non puo' partire
    assert _closings(db, tid) == []
    apri = db.get_trade(tid)
    assert apri["status"] == "open", "nessuna copertura inventata"
    req = apri["meta"]["exit_requested"]
    assert req["sent"] is False and req["failed"] is False
    assert req["attempts"] == 0, "il runner giu' non consuma i tentativi dell'uscita"
    assert req.get("detail", "").startswith("paper_senza_runner:")
    assert apri["meta"]["exit"]["state"] == "retrying"
    crit = [p for k, p in db.activity if k == "exit_retry" and p.get("senza_runner")]
    assert 2 <= len(crit) <= 3, "riga critica al piu' una volta al minuto"
    assert crit[0]["critical"] is True and crit[0]["esposizione_eur"] == 67.5
    # il runner torna: al giro dopo l'uscita parte e la posizione si chiude
    db.follow = "STREAMING"
    at = NOW + timedelta(seconds=126)
    db.heartbeat = {"ts": at.isoformat(), "mode": "PAPER"}   # battito fresco
    db.scan_rows = [_exit_feed_row(80, 1, 0, updated_at=at)]
    S.run_once(db=db, market=FakeMarket(), engine=None, now=at)
    _poll_runner(db)
    assert db.get_trade(tid)["status"] == "hedged"
    assert db.get_trade(tid)["meta"]["exit_requested"]["sent"] is True
    vive = [g for g in _closings(db, tid) if g["status"] != "error"]
    assert len(vive) == 1 and vive[0]["status"] == "open"


# ---------------------------------------------------------------------------
# 3. Safe TENNIS (reperto F-1 di D2)
# ---------------------------------------------------------------------------
def test_safe_tennis_paper_senza_runner_non_riempie_in_casa():
    db = FakeDB()
    db.follow = "NONE"
    tid, row = _riga(db, sport="tennis", event_id="2.1", market_id="mt",
                     selection_id=11, price=1.3, size=4.0, signal_key="2.1:tennis:set 1-0")
    out = _esegui(db, tid, row)
    assert out.status == "error" and out.fill_note.startswith("paper_senza_runner:")
    assert db.get_trade(tid)["status"] == "error" and db.queue == []


def test_safe_tennis_paper_col_runner_usa_il_ref_del_tennis():
    db = FakeDB()
    tid, row = _riga(db, sport="tennis", event_id="2.1", market_id="mt",
                     selection_id=11, price=1.3, size=4.0, signal_key="2.1:tennis:set 1-0")
    out = _esegui(db, tid, row)
    assert out.status == "pending" and db.queue[-1]["client_ref"] == f"safe_tennis-t{tid}"


# ---------------------------------------------------------------------------
# 4. execution_mode='rest' vale per i soldi veri, non spegne il paper
# ---------------------------------------------------------------------------
def test_params_ordine_rest_diventa_auto_solo_in_paper():
    p = {"execution_mode": "rest", "x": 1}
    assert S._params_ordine(p, {"mode": "paper"}) == {"execution_mode": "auto", "x": 1}
    assert S._params_ordine(p, {"mode": "live"}) is p
    q = {"execution_mode": "auto"}
    assert S._params_ordine(q, {"mode": "paper"}) is q
    assert p == {"execution_mode": "rest", "x": 1}, "il dict del chiamante non si tocca"


def test_apertura_paper_con_rest_va_comunque_al_runner():
    db = FakeDB()
    tid, row = _riga(db)
    out = _esegui(db, tid, row, params={"execution_mode": "rest"})
    assert out.status == "pending" and db.queue and db.queue[-1]["mode"] == "paper"


def test_chiusura_paper_con_rest_va_comunque_al_runner():
    db = FakeDB()
    tid = _auto_trade(db, "base")
    res = X.close_trade(db=db, market=FakeMarket(), trade=db.get_trade(tid),
                        prices={"back": 9.0, "back_size": 500.0, "lay": 9.5,
                                "lay_size": 500.0},
                        now=NOW, params={"execution_mode": "rest"}, table_prefix="safe")
    assert res.get("ok") is True and res["pending_fill"] is True
    assert db.queue[-1]["params"]["reduces_liability"] is True


def test_chiusura_live_con_rest_resta_rest():
    db = FakeDB(mode="live")
    mk = FakeMarket()
    tid = _auto_trade(db, "base", mode="live")
    res = X.close_trade(db=db, market=mk, trade=db.get_trade(tid),
                        prices={"back": 9.0, "back_size": 500.0, "lay": 9.5,
                                "lay_size": 500.0},
                        now=NOW, params={"execution_mode": "rest"}, table_prefix="safe")
    assert res.get("ok") is True and len(mk.placed) == 1 and db.queue == []


# ---------------------------------------------------------------------------
# 5. Mike: il motivo nuovo e' ancora riconosciuto come «runner assente»
# ---------------------------------------------------------------------------
def test_mike_riconosce_il_motivo_nuovo():
    from Betfair.mike import service as MS

    assert MS._nota_senza_runner("paper_senza_runner:follow_none")
    assert MS._nota_senza_runner("paper_senza_runner:execution_mode_rest")


# ---------------------------------------------------------------------------
# 6. parita': stesso ordine, cambia solo chi lo esegue
# ---------------------------------------------------------------------------
def test_stesso_ordine_paper_al_runner_e_live_a_betfair():
    def ordine(mode):
        db, mk = FakeDB(mode=mode), FakeMarket()
        if mode == "live":
            db.follow = "NONE"                       # live in REST
        tid, row = _riga(db, mode=mode, side="lay", price=6.0, size=10.0)
        _esegui(db, tid, row, market=mk)
        return db.queue[-1] if mode == "paper" else mk.placed[-1]

    p, l = ordine("paper"), ordine("live")
    for k in ("side", "price", "size", "market_id", "selection_id"):
        assert str(p[k]) == str(l[k]), k
    assert p["time_in_force"] == "FILL_OR_KILL"      # il REST live e' FOK di costruzione
