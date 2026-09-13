"""Certificazione chirurgica del 12/09/2026 — perimetro service/db/feed/config/dossier.

Un test per ogni difetto corretto: void per mercato con totale deducibile
(COSTITUZIONE §10.B.1), regolamento che NON chiude la partita se le righe non
sono state scritte, ``pre_exit_mode`` per partita LIVE (H3), ``is_placed``
allineato al SQL (§10.B.4), aggregati che non si azzerano su una lettura
fallita, liability della riga ricostruita. ASCII-only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from Betfair.mike import db as MDB
from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_audit_2026_09_11 import asdict, fill, live_event, over_leg, under_leg
from Betfair.mike.tests.test_mike_feed import payload, row
from Betfair.mike.tests.test_mike_service import FakeDB, FakeMarket, run, state

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)

_SELS = {"OU35|UNDER": 1222344, "OU35|OVER": 1222345,
         "OU45|UNDER": 1222347, "OU45|OVER": 1222346}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    S._LAST_HEARTBEAT.clear()
    S._CONFIG_WARNED.clear()
    S._DAILY_STOP_LOGGED.clear()
    S._LAST_AGG.clear()
    S._MALFORMED_LOGGED.clear()
    MDB._TOTALS.clear()
    MDB._AGG_RPC.clear()
    monkeypatch.setenv("SAFE_PRE_KO_OU_HOURS", "3")
    yield


def _closed_event(db, *, ko=None):
    under = under_leg(size=10.0, price=1.50)
    under.placed_at = NOW.timestamp() - 7200
    over = over_leg(size=2.53, price=6.0)
    over.placed_at = NOW.timestamp() - 3600
    db.events["E1"] = live_event([asdict(under), asdict(over)], state_="LIVE_COVERED",
                                 ctx={"seen_inplay": True, "last_goals": 3, "selections": _SELS},
                                 ko=ko or (NOW - timedelta(hours=2)))
    db.trades = [{"id": 1, "event_id": "E1", "signal_key": "under_last-1-1", "status": "open",
                  "pnl": 0, "liability": 10.0, "meta": {}},
                 {"id": 2, "event_id": "E1", "signal_key": "over_cover-1-2", "status": "open",
                  "pnl": 0, "liability": 2.53, "meta": {}}]


# ===========================================================================
# §10.B.1 — void PER MERCATO anche quando il totale gol e' deducibile
# ===========================================================================
def test_void_per_mercato_vale_anche_con_totale_deducibile():
    """3.5 dichiara UNDER (totale dedotto = 3) e la 4.5 e' ANNULLATA.

    Prima si passava dalla strada normale (``final_total_from_books`` = 3) e la
    copertura sull'Over 4.5 veniva regolata come PERSA (-2,53 EUR inventati)
    invece che void.
    """
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    _closed_event(db)
    mk.books["1.35"] = {"market_id": "1.35", "status": "CLOSED",
                        "runners": [{"selection_id": 1222344, "status": "WINNER"},
                                    {"selection_id": 1222345, "status": "LOSER"}]}
    mk.books["1.45"] = {"market_id": "1.45", "status": "CLOSED",
                        "runners": [{"selection_id": 1222346, "status": "REMOVED"},
                                    {"selection_id": 1222347, "status": "REMOVED"}]}
    res = run(db, mk, NOW, [])
    assert res["settled"] == 1 and state(db) == "SETTLED"
    # Under 3.5 vinto: 10 @ 1.50 = +5,00 lordi, -5% di commissione = +4,75
    assert db.events["E1"]["settled_pnl"] == pytest.approx(4.75, abs=0.01)
    by_id = {t["id"]: t for t in db.trades}
    assert by_id[1]["status"] == "won" and by_id[1]["pnl"] == pytest.approx(4.75, abs=0.01)
    assert by_id[2]["status"] == "void" and by_id[2]["pnl"] == 0.0
    settled = [p for k, p, _ in db.activity if k == "settled"][0]
    assert settled["void"] is True and settled["voided"] == [E.MARKET_OU45]


def test_void_parziale_non_scatta_senza_mercati_annullati():
    """Nessun mercato annullato: si regola normalmente dal totale (nessuna
    regressione sul percorso principale)."""
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    _closed_event(db)
    mk.books["1.35"] = {"market_id": "1.35", "status": "CLOSED",
                        "runners": [{"selection_id": 1222344, "status": "WINNER"},
                                    {"selection_id": 1222345, "status": "LOSER"}]}
    mk.books["1.45"] = {"market_id": "1.45", "status": "CLOSED",
                        "runners": [{"selection_id": 1222346, "status": "LOSER"},
                                    {"selection_id": 1222347, "status": "WINNER"}]}
    res = run(db, mk, NOW, [])
    assert res["settled"] == 1 and state(db) == "SETTLED"
    by_id = {t["id"]: t for t in db.trades}
    assert by_id[1]["status"] == "won"
    assert by_id[2]["status"] == "lost" and by_id[2]["pnl"] == pytest.approx(-2.53, abs=0.01)
    settled = [p for k, p, _ in db.activity if k == "settled"][0]
    assert settled.get("void") is not True


# ===========================================================================
# Regolamento: righe NON scritte => la partita non diventa terminale
# ===========================================================================
def test_regolamento_non_chiude_la_partita_se_le_righe_non_si_scrivono():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    _closed_event(db)
    mk.books["1.35"] = {"market_id": "1.35", "status": "CLOSED",
                        "runners": [{"selection_id": 1222344, "status": "WINNER"},
                                    {"selection_id": 1222345, "status": "LOSER"}]}
    mk.books["1.45"] = {"market_id": "1.45", "status": "CLOSED",
                        "runners": [{"selection_id": 1222346, "status": "LOSER"},
                                    {"selection_id": 1222347, "status": "WINNER"}]}

    def _boom(*_a, **_k):
        raise RuntimeError("Supabase giu'")

    db.update_trade = _boom
    res = run(db, mk, NOW, [])
    # NON terminale: altrimenti il ciclo non guarderebbe piu' la partita e le
    # righe resterebbero 'open' per sempre (liability e posizioni fantasma)
    assert res["settled"] == 0 and state(db) == "SETTLING"
    assert any(p.get("reason") == "settle_rows_retry" for k, p, _ in db.activity if k == "error")
    assert all(t["status"] == "open" for t in db.trades)
    # dopo _SETTLE_ROWS_MAX_TRIES tentativi la partita si chiude comunque, GRIDANDO
    for i in range(1, S._SETTLE_ROWS_MAX_TRIES):
        res = run(db, mk, NOW + timedelta(minutes=2 * i), [])
    assert state(db) == "SETTLED" and res["settled"] == 1
    assert any(p.get("reason") == "settle_rows_failed" for k, p, _ in db.activity if k == "error")


def test_regolamento_normale_azzera_il_contatore_dei_tentativi():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    _closed_event(db)
    mk.books["1.35"] = {"market_id": "1.35", "status": "CLOSED",
                        "runners": [{"selection_id": 1222344, "status": "WINNER"},
                                    {"selection_id": 1222345, "status": "LOSER"}]}
    mk.books["1.45"] = {"market_id": "1.45", "status": "CLOSED",
                        "runners": [{"selection_id": 1222346, "status": "LOSER"},
                                    {"selection_id": 1222347, "status": "WINNER"}]}
    run(db, mk, NOW, [])
    assert "settle_rows_attempts" not in (db.events["E1"].get("ctx") or {})


# ===========================================================================
# H3 — pre_exit_mode dipende dal mode della PARTITA, non solo dal control
# ===========================================================================
def test_live_exit_override_forza_taker_solo_in_live():
    p = {"pre_exit_mode": "resting"}
    assert S._live_exit_override(p, "live")["pre_exit_mode"] == "taker"
    assert S._live_exit_override(p, "paper") is p           # nessuna copia inutile
    assert p["pre_exit_mode"] == "resting"                   # originale non mutato


def test_partita_live_non_riceve_resting_con_control_in_paper(monkeypatch):
    db = FakeDB(mode="paper", params={"stake": 10})
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg())], state_="LIVE_UNCOVERED", mode="live")
    seen: dict = {}
    real = E.decide

    def spy(ctx, snap, params):
        seen["pre_exit_mode"] = params.get("pre_exit_mode")
        return real(ctx, snap, params)

    monkeypatch.setattr(E, "decide", spy)
    run(db, mk, NOW, [row(payload(inplay=True, minute=30, sh=0, sa=0, ko=NOW - timedelta(hours=1)))])
    assert seen["pre_exit_mode"] == "taker"
    assert "resting_live_unsupported" not in db.kinds()


# ===========================================================================
# §10.B.4 — is_placed: UNA sola definizione, quella del SQL
# ===========================================================================
def test_is_placed_allineato_al_sql():
    day = datetime(2026, 9, 11, 22, 0, tzinfo=timezone.utc)
    rows = [
        # 'pending' accodata al runner flumine: PIAZZATA (come get_mike_aggregates)
        {"id": 1, "event_id": "A", "status": "pending", "pnl": 0,
         "placed_at": "2026-09-12T08:00:00+00:00", "meta": {"flumine_client_ref": "mike-t1"}},
        # 'pending' con bet_id reale: PIAZZATA
        {"id": 2, "event_id": "B", "status": "pending", "pnl": 0, "bet_id": "123",
         "placed_at": "2026-09-12T08:00:00+00:00", "meta": {}},
        # 'pending' nuda (riserva prima dell'ordine): NON piazzata
        {"id": 3, "event_id": "C", "status": "pending", "pnl": 0,
         "placed_at": "2026-09-12T08:00:00+00:00", "meta": {}},
    ]
    agg = MDB.aggregate_rows(rows, day)
    assert agg["cycles_today"] == 2 and agg["events_today"] == 2
    # nessuna delle tre conta come posizione APERTA (solo la riconciliazione lo fa)
    assert agg["open_count"] == 0


def test_open_liability_delle_righe_non_e_piu_fissa_a_zero():
    day = datetime(2026, 9, 11, 22, 0, tzinfo=timezone.utc)
    rows = [
        {"id": 1, "event_id": "A", "status": "open", "pnl": 0, "liability": 10.0,
         "placed_at": "2026-09-12T08:00:00+00:00", "meta": {}},
        {"id": 2, "event_id": "A", "status": "pending", "pnl": 0, "liability": 7.5,
         "placed_at": "2026-09-12T08:00:00+00:00",
         "meta": {"reason": "place_exception_reconciling"}},
        # chiusura: non e' capitale a rischio in piu'
        {"id": 3, "event_id": "A", "closes_trade_id": 1, "status": "open", "pnl": 0,
         "liability": 4.0, "placed_at": "2026-09-12T09:00:00+00:00", "meta": {}},
    ]
    agg = MDB.aggregate_rows(rows, day)
    assert agg["open_count"] == 2
    assert agg["open_liability"] == pytest.approx(17.5, abs=0.01)


# ===========================================================================
# Aggregati: una lettura fallita non vale "zero"
# ===========================================================================
def test_aggregati_riusano_l_ultima_lettura_buona():
    class _DB:
        def __init__(self):
            self.n = 0

        def aggregates(self, now=None):
            self.n += 1
            if self.n == 1:
                return {"realized_today": -60.0, "realized_total": -60.0, "open_count": 3}
            raise RuntimeError("Supabase giu'")

    d = _DB()
    assert S._aggregates(d, NOW)["realized_today"] == -60.0
    again = S._aggregates(d, NOW)
    assert again["realized_today"] == -60.0 and again["open_count"] == 3


def test_stop_giornaliero_non_si_spegne_se_gli_aggregati_falliscono():
    db = FakeDB(params={"stake": 10, "daily_loss_stop": 50.0})
    mk = FakeMarket()
    real_agg = db.aggregates
    calls = {"n": 0}

    def flaky(now=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"realized_today": -80.0, "realized_total": -80.0, "open_count": 0}
        raise RuntimeError("Supabase giu'")

    db.aggregates = flaky
    run(db, mk, NOW, [row(payload())])
    assert db.control["stats"]["daily_stop"] is True
    db2 = FakeDB(params={"stake": 10, "daily_loss_stop": 50.0})
    db2.aggregates = real_agg          # non usato: serve solo a tenere l'API viva
    # secondo ciclo con aggregati ROTTI: lo stop resta attivo (prima tornava False)
    S._DAILY_STOP_LOGGED.clear()
    res = run(db, mk, NOW + timedelta(seconds=30), [row(payload())])
    assert res["stats"]["daily_stop"] is True


# ===========================================================================
# H2 — la riga RICOSTRUITA porta la liability dell'ABBINATO, non della size chiesta
# ===========================================================================
def test_riga_ricostruita_usa_la_liability_dell_abbinato():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    entry = fill(E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                       side="back", price=1.50, size=10.0, ref="under_entry-1-1", cycle_no=1))
    green = E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                  price=1.48, size=10.14, ref="under_green-1-2", cycle_no=1,
                  status="open", matched=5.0, avg_price=1.48, closes_ref="under_entry-1-1")
    db.events["E1"] = live_event([asdict(entry), asdict(green)], state_="PRE_OPEN",
                                 ctx={"selections": _SELS}, ko=NOW + timedelta(hours=2))
    db.trades = []
    run(db, mk, NOW, [row(payload())])
    rebuilt = {t["signal_key"]: t for t in db.trades}
    assert "reconcile_fix" in db.kinds()
    # lay 5,00 abbinati @ 1,48 -> liability 2,40 (prima: 10,14 x 0,48 = 4,87)
    assert rebuilt["under_green-1-2"]["liability"] == pytest.approx(2.40, abs=0.01)
    assert rebuilt["under_green-1-2"]["size"] == pytest.approx(5.0, abs=0.01)
    assert rebuilt["under_entry-1-1"]["liability"] == pytest.approx(10.0, abs=0.01)


# ===========================================================================
# Tabella empirica HT->FT VUOTA: si ritenta, non si spegne per sempre
# ===========================================================================
def test_empirical_vuota_non_resta_in_cache_per_sempre():
    from Betfair.mike import dossier as D

    class _Db:
        calls = 0

        def ht_ft_rows(self, league_id):
            self.calls += 1
            if self.calls == 1:
                return []                     # lega ancora senza dati
            return [{"league_id": None, "ht": "1-1", "ft": "2-2", "n": 300}]

    D._EMPIRICAL_CACHE.clear()
    D._EMPIRICAL_FAILED.clear()
    db = _Db()
    assert D.get_empirical(7, db, now_ts=1000.0) is None
    assert D.get_empirical(7, db, now_ts=1010.0) is None and db.calls == 1   # throttle
    t = D.get_empirical(7, db, now_ts=1000.0 + D._EMPIRICAL_RETRY_S + 1)
    assert t is not None and db.calls == 2                                   # ritentata
    D._EMPIRICAL_CACHE.clear()
    D._EMPIRICAL_FAILED.clear()


# ===========================================================================
# Snapshot non costruibile: la partita non resta MUTA
# ===========================================================================
def test_snapshot_non_costruibile_lo_dichiara():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg())], state_="LIVE_UNCOVERED",
                                 ko=NOW - timedelta(minutes=30))
    p = payload(inplay=True, minute=30, sh=0, sa=0, ko=NOW - timedelta(minutes=30))
    p["open_date"] = None                     # niente calcio d'inizio: snapshot impossibile
    run(db, mk, NOW, [row(p)])
    pay = [pl for k, pl, _ in db.activity if k == "feed_line_missing"]
    assert any(x.get("reason") == "snapshot_non_costruibile" and x.get("critical") for x in pay)


# ===========================================================================
# CERTIFICAZIONE 12/09 — il regolamento usa l'ALIQUOTA FISSATA SULLE RIGHE.
# Prima usava sempre quella CORRENTE dei parametri: cambiando la commissione
# con posizioni aperte, il P&L delle vecchie cambiava di significato.
# Omega e Safe usano da sempre quella della riga.
# ===========================================================================
class _DBComm:
    def __init__(self, rows):
        self._rows = rows
        self.logs = []

    def trades_for_event(self, event_id):
        return list(self._rows)

    def log(self, kind, payload=None, event_id=None):
        self.logs.append((kind, payload or {}, event_id))


def test_regolamento_usa_l_aliquota_della_riga_non_quella_corrente():
    db = _DBComm([{"commission": 0.02}, {"commission": 0.02}])
    out = S._settle_params(db, "E1", {"commission_pct": 5.0})
    assert out["commission_pct"] == pytest.approx(2.0, abs=1e-6)
    assert not db.logs


def test_aliquote_diverse_sulle_righe_si_dichiarano_e_si_tiene_la_corrente():
    db = _DBComm([{"commission": 0.02}, {"commission": 0.05}])
    out = S._settle_params(db, "E1", {"commission_pct": 5.0})
    assert out["commission_pct"] == 5.0
    assert any(k == "settle_commissione_mista" for k, _p, _e in db.logs)


def test_righe_senza_aliquota_non_cambiano_i_parametri():
    db = _DBComm([{"commission": None}, {}])
    out = S._settle_params(db, "E1", {"commission_pct": 5.0})
    assert out["commission_pct"] == 5.0


def test_lettura_delle_righe_fallita_non_blocca_il_regolamento():
    class _KO:
        def trades_for_event(self, event_id):
            raise RuntimeError("db giu'")

        def log(self, *a, **k):
            pass

    out = S._settle_params(_KO(), "E1", {"commission_pct": 5.0})
    assert out["commission_pct"] == 5.0


# ===========================================================================
# OSSERVAZIONE DAL VIVO 12/09 — RESIDUO NON CHIUDIBILE.
# Numeri REALI dal paper: apertura #119 back 3,08 @5,10 su Over 4.5; la quota
# sale a 50 e la size che chiuderebbe la posizione vale 0,31 EUR, sotto il
# minimo Betfair di 2 EUR. Il bot ci riprovava a OGNI ciclo: 64 righe 'error'
# sulla stessa posizione in poche ore, e il residuo restava comunque aperto.
# ===========================================================================
def test_chiusura_sotto_il_minimo_betfair_non_viene_nemmeno_tentata():
    over = E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER,
                 side="back", price=5.10, size=3.08, ref="over_cover-0-2", cycle_no=0)
    over.matched, over.avg_price, over.status = 3.08, 5.10, "open"
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[over], cycle_no=0)
    books = {(E.MARKET_OU45, E.SEL_OVER): E.Book(best_back=48.0, back_size=99.0,
                                                 best_lay=50.0, lay_size=99.0, inplay=True)}
    _cancels, closes = E.force_flat_plan(ctx, books, C.merge_params({"stake": 10}), goals=1)
    assert closes == [], f"tentata una chiusura non eseguibile: {closes}"


def test_chiusura_sopra_il_minimo_viene_regolarmente_pianificata():
    over = E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER,
                 side="back", price=5.10, size=3.08, ref="over_cover-0-2", cycle_no=0)
    over.matched, over.avg_price, over.status = 3.08, 5.10, "open"
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[over], cycle_no=0)
    # quota 5,00: la chiusura vale 3,08*5,10/5,00 = 3,14 EUR -> sopra il minimo
    books = {(E.MARKET_OU45, E.SEL_OVER): E.Book(best_back=4.8, back_size=99.0,
                                                 best_lay=5.0, lay_size=99.0, inplay=True)}
    _cancels, closes = E.force_flat_plan(ctx, books, C.merge_params({"stake": 10}), goals=1)
    assert len(closes) == 1 and closes[0].size >= 2.0


def test_size_chiudibile_e_la_soglia_dichiarata():
    assert E.size_chiudibile(0.01) is False
    assert E.size_chiudibile(0.31) is False
    assert E.size_chiudibile(1.99) is False
    assert E.size_chiudibile(2.00) is True
    assert E.size_chiudibile(None) is False
    assert E.size_chiudibile(float("nan")) is False


# ===========================================================================
# OSSERVAZIONE DAL VIVO 12/09 — COPERTURA SOTTO IL MINIMO = PARTITA SCOPERTA.
# Caso reale Koper v Olimpija: la copertura sull'Over 4.5 serviva a 1,91 EUR
# (sotto il minimo Betfair di 2). Il bot l'ha ritentata 172 volte, tutte
# rifiutate, e la partita e' finita a 4 gol — l'unico esito che perde —
# incassando -16,16 EUR senza essere MAI stata coperta.
# ===========================================================================
def test_copertura_sotto_il_minimo_viene_alzata_al_minimo_piazzabile():
    size, over = E.cover_legal_size(1.91, {"exact_sizes": True})
    assert size == E.IT_BACK_MIN, "una copertura da 1,91 non e' piazzabile: va alzata a 2,00"
    assert over > 0, "l'overshoot deve essere dichiarato al chiamante"


def test_copertura_gia_sopra_il_minimo_resta_esatta():
    size, over = E.cover_legal_size(6.16, {"exact_sizes": True})
    assert size == 6.16 and over == 0.0


def test_copertura_nulla_resta_nulla():
    assert E.cover_legal_size(0.0, {"exact_sizes": True}) == (0.0, 0.0)


def test_la_copertura_si_arrotonda_solo_se_costa_poco():
    """Il comportamento risultante, con il tetto di overshoot gia' esistente.

    Numeri VERI della partita Koper v Olimpija osservata dal vivo:
      · copertura 1,91 EUR (Over a 7,60) -> si alza a 2,00: overshoot 4,7%,
        sotto il tetto (30%) -> SI COPRE, e prima non si copriva affatto;
      · copertura 0,29 EUR (Over a 44,00) -> alzarla a 2,00 costerebbe il 590%
        in piu' -> NON si copre, lo si DICHIARA e si aspetta, invece di
        ritentare un ordine che l'exchange rifiuta a ogni ciclo.
    Pagare 1,71 EUR per coprire un rischio che il mercato prezza 0,29 non e'
    prudenza, e' spreco: il tetto esistente lo impedisce.
    """
    params = C.merge_params({"stake": 10})
    cap = float(params["cover_max_overshoot_pct"])
    size_a, over_a = E.cover_legal_size(1.91, params)
    assert size_a == E.IT_BACK_MIN and over_a <= cap, "una copertura quasi al minimo va arrotondata"
    size_b, over_b = E.cover_legal_size(0.29, params)
    assert size_b == E.IT_BACK_MIN and over_b > cap, "una copertura 7x piu' cara va rifiutata dal tetto"
    size_c, over_c = E.cover_legal_size(6.16, params)
    assert size_c == 6.16 and over_c == 0.0, "sopra il minimo la size resta ESATTA"


# ---------------------------------------------------------------------------
# CERT. 12/09 - il premio al rischio non deve contare due volte i 4 gol
# ---------------------------------------------------------------------------
class TestPremioRischioNonChiudeAnticipo:
    """Sulle 7 uscite in perdita della storia di Mike, sei erano su partite che
    sono finite sotto i 3,5 gol: l'Under avrebbe VINTO. Quattro di quelle sei
    sono state chiuse mentre il mercato dava ancora l'Under FAVORITO (57-66 %).

    Causa: ``premium = base * pct * P(4)`` viene SOTTRATTO dalla soglia, ma il
    caso 4 gol e' gia' uno dei termini di ``ev_hold``. Col 50 % il premio valeva
    1,00 EUR su 10 di capitale e ribaltava la decisione.
    """

    # posizione tipica: Under 3.5 backato + copertura Over 4.5
    PNL = {3: 1.16, 4: -12.04, 5: 2.00}
    DIST = {3: 0.66, 4: 0.20, 5: 0.14}

    @staticmethod
    def _params(pct: float) -> dict:
        return C.merge_params({"loss_exit_risk_premium_pct": pct})

    def test_il_caso_4_gol_e_gia_dentro_il_valore_atteso(self) -> None:
        ev, p4 = E.hold_expectation(self.PNL, self.DIST, None)
        assert p4 == pytest.approx(0.20, abs=1e-9)
        assert ev == pytest.approx(0.66 * 1.16 + 0.20 * -12.04 + 0.14 * 2.00, abs=1e-9)
        # il contributo dei 4 gol pesa gia' -2,41 EUR sull'EV
        assert self.DIST[4] * self.PNL[4] == pytest.approx(-2.408, abs=1e-3)

    def test_col_premio_vecchio_si_chiudeva_un_under_ancora_favorito(self) -> None:
        """cv_net -2,00: col 50 % si chiude, col 10 % si tiene."""
        comune = dict(base=10.0, pnl_by_total=self.PNL, p_total_model=self.DIST,
                      p_total_emp=None, p4_market=None)
        vecchio, _, tv = E.loss_exit_model(cv_net=-2.00, params=self._params(50.0), **comune)
        nuovo, _, tn = E.loss_exit_model(cv_net=-2.00, params=self._params(10.0), **comune)
        assert tv["premium"] == pytest.approx(1.00, abs=1e-2)
        assert tn["premium"] == pytest.approx(0.20, abs=1e-2)
        assert vecchio is True, "col premio al 50% si chiudeva"
        assert nuovo is False, "col premio al 10% si tiene"

    def test_il_default_del_servizio_e_dieci(self) -> None:
        assert C.merge_params({})["loss_exit_risk_premium_pct"] == 10.0

    def test_quando_chiudere_conviene_davvero_si_chiude_lo_stesso(self) -> None:
        """Il premio piu' basso non blocca le uscite giuste: se il prezzo certo
        batte l'EV del tenere si esce comunque."""
        deciso, _, _ = E.loss_exit_model(
            cv_net=+0.50, base=10.0, pnl_by_total=self.PNL, p_total_model=self.DIST,
            p_total_emp=None, p4_market=None, params=self._params(10.0))
        assert deciso is True


# ===========================================================================
# CERT. 12/09 - il modello di Mike era CIECO su tutti gli eventi
# ===========================================================================
class TestLambdaConRipiego:
    """Trovato dal vivo: su 93 eventi Mike il dossier aveva ``lambda_home`` e
    ``lambda_away`` a None, ``source: "none"``, perche' ``fixture_id_for_event``
    cerca la partita in ``live_follow`` e NESSUNO dei 19 eventi vivi era li'
    dentro. Senza lambda non c'e' griglia Poisson, quindi niente
    ``p_total_model``, ``p4_model``, ``hazard_model``, ``cover_gain_pct``:
    l'uscita in perdita decideva su empirico e mercato, e l'attesa intelligente
    della copertura non si e' MAI attivata (``cover_timing`` copre subito a ogni
    dato mancante).
    """
    from Betfair.mike import dossier as D

    VUOTO = {"lambda_home": None, "lambda_away": None, "league_id": None, "source": "none"}
    PIENO = {"lambda_home": 1.31, "lambda_away": 1.05, "league_id": 135, "source": "fixture"}

    def _chiama(self, dossier, payload, **kw):
        base = dict(minute=40, score_home=0, score_away=0)
        base.update(kw)
        return self.D.lambdas_con_ripiego(dossier, payload, **base)

    def test_la_fixture_resta_la_fonte_migliore(self) -> None:
        """Quando il dossier ha i lambda non si tocca nulla: nessun ripiego."""
        lh, la, src = self._chiama(self.PIENO, {"pre_ko": {"home": 2.0, "draw": 3.4, "away": 3.8}})
        assert (lh, la, src) == (1.31, 1.05, "fixture")

    def test_senza_dossier_si_usano_le_quote_pre_KO(self) -> None:
        lh, la, src = self._chiama(self.VUOTO, {"pre_ko": {"home": 2.0, "draw": 3.4, "away": 3.8}})
        assert src == "pre_ko_odds"
        assert lh and la and lh > 0 and la > 0
        assert lh > la, "la favorita di casa deve avere piu' gol attesi"

    def test_senza_niente_resta_cieco_e_lo_dichiara(self) -> None:
        """Mai numeri inventati: senza fonti si torna None, come prima."""
        for payload in (None, {}, {"pre_ko": None}, {"pre_ko": {}}):
            assert self._chiama(self.VUOTO, payload) == (None, None, "none")

    def test_senza_minuto_o_punteggio_non_si_prova_il_mercato_live(self) -> None:
        p = {"pre_ko": None, "ou": [{"line": 3.5, "selections": []}]}
        assert self._chiama(self.VUOTO, p, minute=None) == (None, None, "none")
        assert self._chiama(self.VUOTO, p, score_home=None) == (None, None, "none")

    def test_un_payload_malformato_non_rompe_il_ciclo(self) -> None:
        """L'engine non deve MAI morire per un feed storto."""
        for p in ({"pre_ko": "non un dict"}, {"pre_ko": {"home": "x"}},
                  {"pre_ko": {"home": 0}}, {"ou": "rotto"}):
            lh, la, src = self._chiama(self.VUOTO, p)
            assert (lh, la) == (None, None) and isinstance(src, str)

    def test_la_fonte_finisce_nel_frame_live(self) -> None:
        """``lambda_source`` dice al trader DA DOVE arriva il modello."""
        out = self.D.live_frame(self.VUOTO, minute=40, score_home=0, score_away=0,
                                payload={"pre_ko": {"home": 2.0, "draw": 3.4, "away": 3.8}})
        assert out["lambda_source"] == "pre_ko_odds"
        assert out["p_total_model"] is not None, "col ripiego il modello deve produrre la distribuzione"
        assert out["p4_model"] is not None

    def test_senza_fonti_il_frame_resta_cieco_come_prima(self) -> None:
        out = self.D.live_frame(self.VUOTO, minute=40, score_home=0, score_away=0, payload=None)
        assert out["lambda_source"] == "none"
        assert out["p_total_model"] is None and out["p4_model"] is None


# ===========================================================================
# CERT. 12/09 - il dossier cieco va RITENTATO, non subito per sempre
# ===========================================================================
class TestRitentativoDelDossier:
    """``build_prematch`` girava UNA SOLA VOLTA, alla presa in carico. Se in quel
    momento la fixture non era abbinata, il dossier restava vuoto PER SEMPRE e il
    bot decideva senza modello per tutta la partita. E' cosi' che tutti e 93 gli
    eventi si sono ritrovati con ``source: "none"``."""
    from Betfair.mike import service as S

    VUOTO = {"lambda_home": None, "lambda_away": None, "source": "none"}
    PIENO = {"lambda_home": 1.3, "lambda_away": 1.1, "source": "fixture"}

    def test_un_dossier_gia_risolto_non_si_tocca(self) -> None:
        ev = {"state": "LIVE_COVERED", "dossier": self.PIENO}
        assert self.S.dossier_da_ritentare(ev, now_ts=1e9) is False

    def test_un_dossier_cieco_si_ritenta(self) -> None:
        ev = {"state": "LIVE_COVERED", "dossier": self.VUOTO}
        assert self.S.dossier_da_ritentare(ev, now_ts=1e9) is True

    def test_le_partite_finite_non_si_ritentano(self) -> None:
        for st in ("SETTLED", "ERROR", "SKIPPED"):
            ev = {"state": st, "dossier": self.VUOTO}
            assert self.S.dossier_da_ritentare(ev, now_ts=1e9) is False

    def test_non_si_martella_il_database(self) -> None:
        """Fra due tentativi deve passare almeno la finestra dichiarata."""
        ev = {"state": "WATCH", "dossier": {**self.VUOTO, "retry_ts": 1000.0}}
        assert self.S.dossier_da_ritentare(ev, now_ts=1100.0, ogni=300.0) is False
        assert self.S.dossier_da_ritentare(ev, now_ts=1299.0, ogni=300.0) is False
        assert self.S.dossier_da_ritentare(ev, now_ts=1300.0, ogni=300.0) is True

    def test_un_dossier_assente_o_rotto_si_ritenta(self) -> None:
        for d in (None, "non un dict", {}, {"retry_ts": "x"}):
            assert self.S.dossier_da_ritentare({"state": "WATCH", "dossier": d}, now_ts=1e9) is True

    def test_quando_si_risolve_il_modello_si_accende_e_lo_dichiara(self) -> None:
        class _DB:
            def __init__(self): self.righe = []
            def log(self, kind, payload, eid=None): self.righe.append((kind, payload, eid))

        db = _DB()
        tracked = {"E1": {"state": "LIVE_COVERED", "dossier": dict(self.VUOTO)}}
        risolto = {"lambda_home": 1.42, "lambda_away": 1.08, "fixture_id": 999,
                   "league_id": 135, "source": "fixture"}
        import Betfair.mike.service as MS
        vecchio = MS.D.build_prematch
        MS.D.build_prematch = lambda eid, _db: dict(risolto)
        try:
            n = MS._retry_dossier(db, tracked, now_ts=1e9)
        finally:
            MS.D.build_prematch = vecchio
        assert n == 1
        assert tracked["E1"]["fixture_id"] == 999 and tracked["E1"]["league_id"] == 135
        assert tracked["E1"]["dossier"]["lambda_home"] == 1.42
        assert any(r[0] == "dossier_risolto" for r in db.righe), db.righe

    def test_un_tentativo_fallito_non_ferma_il_ciclo(self) -> None:
        class _DB:
            def log(self, *a, **k): pass

        tracked = {"E1": {"state": "WATCH", "dossier": dict(self.VUOTO)}}
        import Betfair.mike.service as MS
        vecchio = MS.D.build_prematch

        def _esplode(eid, _db):
            raise RuntimeError("database irraggiungibile")

        MS.D.build_prematch = _esplode
        try:
            assert MS._retry_dossier(_DB(), tracked, now_ts=1e9) == 0
        finally:
            MS.D.build_prematch = vecchio
        assert tracked["E1"]["dossier"]["lambda_home"] is None


# ===========================================================================
# CERT. 13/09 - le schede non si aggiornavano in UI: updated_at restava fermo
# ===========================================================================
class TestLaSchedaDiceQuandoEStataScritta:
    """Il servizio tiene in memoria la riga LETTA dal DB, che porta gia' la sua
    ``updated_at``. Con ``setdefault`` quel valore vecchio sopravviveva a ogni
    riscrittura: i dati cambiavano (minuto, stato, prezzi) ma il timestamp no.
    In UI le card sono memoizzate su ``updated_at`` -> restavano ferme.
    Caso vivo: Shatin SA v Kowloon City, stato passato a FLAT 92 secondi prima,
    ``updated_at`` fermo da 5.965 secondi."""

    @staticmethod
    def _cattura(monkeypatch):
        """Intercetta la riga che finirebbe su Supabase, senza toccare il DB."""
        from Betfair.mike import db as D
        visto = {}

        class _Tab:
            def upsert(self, row, on_conflict=None):
                visto["row"] = row
                return self
            def execute(self):
                return type("R", (), {"data": []})()

        class _SB:
            def table(self, _n):
                return _Tab()

        monkeypatch.setattr(D, "_sb", lambda: _SB())
        return D, visto

    def test_una_riga_gia_scritta_riceve_un_timestamp_NUOVO(self, monkeypatch) -> None:
        D, visto = self._cattura(monkeypatch)
        vecchio = "2026-09-13T07:08:00+00:00"
        D.upsert_event({"event_id": "E1", "state": "FLAT", "updated_at": vecchio})
        assert visto["row"]["updated_at"] != vecchio, "il timestamp deve dire ADESSO"
        assert visto["row"]["state"] == "FLAT"

    def test_due_scritture_di_seguito_hanno_timestamp_diversi(self, monkeypatch) -> None:
        """E' il comportamento che fa ridisegnare la card a ogni cambio."""
        import time
        D, visto = self._cattura(monkeypatch)
        ev = {"event_id": "E1", "state": "LIVE_COVERED"}
        D.upsert_event(ev)
        primo = visto["row"]["updated_at"]
        time.sleep(0.01)
        ev["state"] = "FLAT"
        D.upsert_event(ev)
        assert visto["row"]["updated_at"] != primo

    def test_la_riga_passata_dal_chiamante_non_viene_modificata(self, monkeypatch) -> None:
        """``upsert_event`` lavora su una copia: lo stato in memoria del servizio
        non deve ritrovarsi dentro un timestamp che non ha chiesto."""
        D, _ = self._cattura(monkeypatch)
        originale = {"event_id": "E1", "state": "FLAT"}
        D.upsert_event(originale)
        assert "updated_at" not in originale


# ===========================================================================
# CERT. 13/09 - le gambe morte non devono zavorrare la scheda
# ===========================================================================
class TestPotaturaDelleGambeMorte:
    """La scheda dell'evento portava TUTTE le gambe mai create. Il difetto della
    copertura (corretto il 12/09) ne ha lasciate 180 su una sola partita: Koper
    v Olimpija pesava 60 KB, di cui 56 di sole gambe annullate. ``get_mike_state``
    ne aggrega fino a 200 di eventi e arrivava a 7,6 s contro un timeout di 8:
    da li' l'alert «canceling statement due to statement timeout»."""

    @staticmethod
    def _leg(ref, role, status="cancelled", matched=0.0):
        return E.Leg(ref=ref, role=role, market=E.MARKET_OU45, selection=E.SEL_OVER,
                     side="back", price=5.0, size=2.0, status=status, matched=matched)

    def test_il_caso_vero_da_180_gambe(self) -> None:
        legs = [self._leg(f"over_cover-0-{i}", "over_cover") for i in range(180)]
        legs.append(self._leg("under_entry-0-1", "under_entry", "open", 10.0))
        out = E.prune_dead_legs(legs)
        assert len(out) == 6, [l.ref for l in out]
        assert out[-1].ref == "under_entry-0-1"

    def test_i_soldi_non_si_toccano_MAI(self) -> None:
        """Una gamba annullata ma PARZIALMENTE abbinata e' denaro: resta."""
        legs = [self._leg(f"over_cover-0-{i}", "over_cover") for i in range(50)]
        legs.insert(0, self._leg("over_cover-0-x", "over_cover", "cancelled", matched=1.5))
        out = E.prune_dead_legs(legs)
        assert any(l.ref == "over_cover-0-x" for l in out)

    def test_le_gambe_vive_non_si_toccano(self) -> None:
        for stato in ("pending", "open", "settled", E.STATUS_RECONCILE):
            legs = [self._leg(f"c-{i}", "over_cover") for i in range(20)]
            legs.append(self._leg("viva", "over_cover", stato))
            out = E.prune_dead_legs(legs)
            assert any(l.ref == "viva" for l in out), stato

    def test_si_tiene_l_ULTIMO_tentativo_per_ruolo(self) -> None:
        """Chi legge «l'ultimo tentativo» deve continuare a trovarlo."""
        legs = ([self._leg(f"a-{i}", "over_cover") for i in range(30)]
                + [self._leg(f"b-{i}", "under_green") for i in range(30)])
        out = E.prune_dead_legs(legs)
        per_ruolo = {}
        for l in out:
            per_ruolo.setdefault(l.role, []).append(l.ref)
        assert per_ruolo["over_cover"][-1] == "a-29"
        assert per_ruolo["under_green"][-1] == "b-29"
        assert len(per_ruolo["over_cover"]) == 5 and len(per_ruolo["under_green"]) == 5

    def test_l_ordine_relativo_non_cambia(self) -> None:
        legs = [self._leg("x1", "r1", "open", 1.0), self._leg("d1", "r1"),
                self._leg("x2", "r2", "open", 1.0), self._leg("d2", "r2")]
        assert [l.ref for l in E.prune_dead_legs(legs)] == ["x1", "d1", "x2", "d2"]

    def test_poche_gambe_restano_tutte(self) -> None:
        legs = [self._leg(f"c-{i}", "over_cover") for i in range(3)]
        assert len(E.prune_dead_legs(legs)) == 3

    def test_lista_vuota_e_tetto_zero(self) -> None:
        assert E.prune_dead_legs([]) == []
        legs = [self._leg("d", "r"), self._leg("v", "r", "open", 1.0)]
        assert [l.ref for l in E.prune_dead_legs(legs, 0)] == ["v"]

    def test_il_PNL_non_cambia_dopo_la_potatura(self) -> None:
        """La prova che conta: le gambe tolte non valevano nulla."""
        legs = [E.Leg(ref="u", role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                      side="back", price=1.5, size=10.0, status="open", matched=10.0,
                      avg_price=1.5)]
        legs += [self._leg(f"c-{i}", "over_cover") for i in range(100)]
        prima = E.net_pnl_by_total(legs, 0.05)
        dopo = E.net_pnl_by_total(E.prune_dead_legs(legs), 0.05)
        assert prima == dopo


# ===========================================================================
# CERT. 13/09 - prezzo Under al FISCHIO: lo scostamento non era misurabile
# ===========================================================================
class TestPrezzoAlFischioDInizio:
    """Domanda posta e senza risposta: «di quanti tick ci muoviamo fra il nostro
    ingresso pre-match e il prezzo in gioco?». Nessuna fonte lo conservava — il
    primo ordine Under in gioco arriva al 27' nel caso piu' precoce (mediana
    54'), quindi sulle 111 posizioni storiche non c'era UNA osservazione vicina
    al fischio. Ora il prezzo si registra al passaggio in gioco, una volta sola."""

    def test_negativo_vuol_dire_a_nostro_favore(self) -> None:
        """Su un back Under un prezzo che SCENDE avvicina l'ordine di chiusura."""
        assert E.drift_ticks(1.50, 1.45) < 0
        assert E.drift_ticks(1.50, 1.60) > 0
        assert E.drift_ticks(1.50, 1.50) == 0

    def test_conta_i_tick_veri_della_scala_betfair(self) -> None:
        """Fra 1,50 e 1,45 ci sono 5 tick (passo 0,01 sotto 2,00)."""
        assert E.drift_ticks(1.50, 1.45) == -5
        assert E.drift_ticks(1.50, 1.60) == 10

    def test_dati_mancanti_o_assurdi_non_inventano_un_numero(self) -> None:
        for a, b in ((None, 1.5), (1.5, None), (None, None), (1.0, 1.5),
                     (1.5, 1.0), (0, 1.5), ("x", 1.5), (1.5, "y")):
            assert E.drift_ticks(a, b) is None, (a, b)

    def test_il_prezzo_del_fischio_si_scrive_UNA_volta_sola(self) -> None:
        """Al 10' o al 40' il campo NON si aggiorna: altrimenti non sarebbe piu'
        il prezzo del fischio."""
        import inspect
        src = inspect.getsource(E._decide_prematch)
        assert "ctx.ko_price_under is None" in src, \
            "manca la guardia: il prezzo verrebbe sovrascritto a ogni giro in gioco"

    def test_il_campo_sopravvive_al_salvataggio(self) -> None:
        """Se non e' nei campi persistiti, al riavvio del servizio si perde."""
        from Betfair.mike import service as S
        assert "ko_price_under" in S._CTX_FIELDS
