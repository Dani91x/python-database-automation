"""FEED UNICO per Omega (09/09 sera): funzioni PURE payload → oggetti Omega.

Nessuna rete/DB. Garanzie money-critical:
  - il CS dal feed porta id/nomi/prezzi/size ESATTI del payload (mai rimappati);
  - runner non ACTIVE (rimosso/vincitore) e mercati CLOSED non producono mai
    uno snapshot (settlement = solo REST);
  - la selezione Omega sul CS del feed è identica a quella sul CS REST;
  - i fake dei test (market/db non reali) NON toccano mai il feed.
"""
from __future__ import annotations

from types import SimpleNamespace

from Betfair.omega import omega_engine as E
from Betfair.omega import omega_service as S


def _payload(status="OPEN", sels=None, inplay=True):
    return {
        "event_name": "Nord v Sud", "inplay": inplay, "minute": 52, "score_home": 1, "score_away": 0,
        "open_date": "2026-09-09T15:00:00+00:00",
        "cs": {
            "market_id": "1.777", "status": status, "inplay": inplay, "total_matched": 500.0,
            "selections": sels if sels is not None else [
                {"selection_id": 1, "name": "1 - 0", "back": 2.9, "lay": 3.0, "back_size": 50, "lay_size": 40, "runner_status": "ACTIVE"},
                {"selection_id": 2, "name": "3 - 0", "back": 90.0, "lay": 110.0, "back_size": 2, "lay_size": 7.5, "runner_status": "ACTIVE"},
                {"selection_id": 3, "name": "0 - 3", "back": 200.0, "lay": 300.0, "back_size": 1, "lay_size": 2, "runner_status": "ACTIVE"},
                {"selection_id": 4, "name": "0 - 0", "back": None, "lay": None, "back_size": None, "lay_size": None, "runner_status": "ACTIVE"},
                {"selection_id": 9, "name": "Any Other Home Win", "back": 40.0, "lay": 44.0, "back_size": 5, "lay_size": 30, "runner_status": "ACTIVE"},
            ],
        },
    }


def test_cs_snapshot_dal_feed_fedele_al_payload():
    out = S.cs_snapshot_from_payload("ev1", _payload())
    assert out is not None
    cs, snap = out
    assert cs.market_id == "1.777" and cs.event_id == "ev1" and cs.event_name == "Nord v Sud"
    assert cs.runner_names == {1: "1 - 0", 2: "3 - 0", 3: "0 - 3", 4: "0 - 0", 9: "Any Other Home Win"}
    assert snap.status == "OPEN" and snap.inplay is True
    assert snap.closed is False and snap.winner_selection_id is None and snap.voided is False
    r2 = next(r for r in snap.runners if r.selection_id == 2)
    assert r2.lay_price == 110.0 and r2.lay_size == 7.5 and r2.back_price == 90.0
    assert r2.lay_ladder == ((110.0, 7.5),)
    r4 = next(r for r in snap.runners if r.selection_id == 4)
    assert r4.lay_price is None and r4.lay_ladder == ()


def test_selezione_omega_identica_su_feed_e_rest():
    _, snap = S.cs_snapshot_from_payload("ev1", _payload())
    sel = E.select_lay_runner(snap.runners, price_min=20, price_max=120,
                              min_liquidity=5, include_aggregate=False)
    assert sel is not None and sel.selection_id == 2 and sel.name == "3 - 0" and sel.price == 110.0
    # 0-3 a 300 è fuori fascia; Any Other escluso di default: identico al percorso REST


def test_cs_feed_mai_settlement_ne_runner_non_attivi():
    assert S.cs_snapshot_from_payload("ev1", _payload(status="CLOSED")) is None
    sels = [{"selection_id": 1, "name": "1 - 0", "lay": 3.0, "lay_size": 40, "runner_status": "WINNER"},
            {"selection_id": 2, "name": "3 - 0", "lay": 110.0, "lay_size": 7.5, "runner_status": "REMOVED"}]
    assert S.cs_snapshot_from_payload("ev1", _payload(sels=sels)) is None   # nessun runner attivo
    assert S.cs_snapshot_from_payload("ev1", {"cs": None}) is None
    assert S.cs_snapshot_from_payload("ev1", {"cs": {"market_id": "1.1", "selections": []}}) is None
    assert S.cs_snapshot_from_payload("ev1", None) is None


def test_score_dal_feed():
    ls = S.score_from_payload("ev1", _payload(), "2026-09-09T15:40:00+00:00")
    assert ls is not None and ls.minute == 52 and ls.score_home == 1 and ls.score_away == 0
    assert ls.inplay is True and ls.updated_at == "2026-09-09T15:40:00+00:00"
    assert S.score_from_payload("ev1", {"minute": None}, None) is None
    assert S.score_from_payload("ev1", None, None) is None


def test_fake_market_non_tocca_il_feed():
    fake = SimpleNamespace()
    assert S._cs_from_feed(fake, "ev1") is None


def test_mission_scores_fallback_diretto_con_fake():
    calls = []

    class _Market:
        def get_inplay_scores(self, ids):
            calls.append(list(ids))
            return {e: SimpleNamespace(minute=1) for e in ids}

    class _Db:
        def log(self, *a, **k):
            pass

    out = S._mission_scores(_Market(), ["a", "b"], _Db())
    assert set(out) == {"a", "b"} and calls == [["a", "b"]]


def test_feed_minute_solo_con_market_reale(monkeypatch):
    assert S._feed_minute(SimpleNamespace(), "ev1") is None
    monkeypatch.setattr(S, "_feed_row", lambda eid: ({"inplay": True, "minute": 14}, "t"))
    assert S._feed_minute(S._real_market, "ev1") == 14
    monkeypatch.setattr(S, "_feed_row", lambda eid: ({"inplay": False, "minute": None}, "t"))
    assert S._feed_minute(S._real_market, "ev1") is None
    monkeypatch.setattr(S, "_feed_row", lambda eid: (None, None))
    assert S._feed_minute(S._real_market, "ev1") is None
