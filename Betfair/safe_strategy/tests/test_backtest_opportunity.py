"""Test del backtest opportunita' (tools/backtest_opportunity.py) e della cache
compatta (tools/validate_opportunity.build_event_cache) su dati SINTETICI."""
from __future__ import annotations

import gzip
import json
import os

import pytest

from Betfair.safe_strategy import calibration as CAL
from Betfair.safe_strategy.opportunity import OpportunityModel
from Betfair.safe_strategy.tools import backtest_opportunity as B
from Betfair.safe_strategy.tools import validate_opportunity as V

PRE_KO = {"home": 2.0, "draw": 3.4, "away": 4.0}
MID_OU = "1.45"
MID_MO = "1.10"
UNDER, OVER = 1222347, 1222346          # sort 1 = Under, 2 = Over (OVER_UNDER_45)
T0 = 1_782_000_000_000


def _markets():
    return {
        MID_MO: {"type": "MATCH_ODDS", "line": None,
                 "runners": [[11, 1, "Nord FC", "home"], [22, 2, "Sud FC", "away"], [33, 3, "The Draw", "draw"]]},
        MID_OU: {"type": "OVER_UNDER_45", "line": 4.5,
                 "runners": [[UNDER, 1, "Under 4.5 Goals", "under_4_5"], [OVER, 2, "Over 4.5 Goals", "over_4_5"]]},
    }


def _book(under_back=(1.05, 30.0), over_lay=(1.06, 40.0), status="OPEN"):
    """Book di un'istantanea: 0-0 all'85' con Under 4.5 back @1.05 e Over lay @1.06.
    Il MATCH_ODDS resta SOSPESO (nessun segnale 1X2: il test isola l'Over/Under)."""
    return {
        MID_MO: ["SUSPENDED", T0, {"11": [[[1.9, 100.0]], [[1.95, 100.0]]],
                              "22": [[[4.0, 50.0]], [[4.2, 50.0]]],
                              "33": [[[3.4, 80.0]], [[3.5, 80.0]]]}],
        MID_OU: [status, T0, {str(UNDER): [[list(under_back)], [[1.07, 20.0]]],
                              str(OVER): [[[12.0, 5.0]], [list(over_lay)]]}],
    }


def _cache(event_id: str, *, delayed_book, winners, final=(0, 0)):
    return {
        "version": 1, "event_id": event_id, "home": "Nord FC", "away": "Sud FC",
        "pre_ko": dict(PRE_KO), "final": list(final), "final_minute": 90, "ht": [0, 0],
        "goals": [], "markets": _markets(), "winners": winners, "step_s": 10, "delay_s": 5,
        "snapshots": [
            {"ts": T0, "minute": 85, "sh": 0, "sa": 0, "rh": 0, "ra": 0,
             "books": _book(), "delayed": delayed_book},
            # stessa situazione 10 s dopo: NON deve generare una seconda scommessa
            {"ts": T0 + 10_000, "minute": 85, "sh": 0, "sa": 0, "rh": 0, "ra": 0,
             "books": _book(), "delayed": delayed_book},
        ],
    }


@pytest.fixture()
def two_events(tmp_path):
    """Evento A: book invariato dopo il delay (abbinata). Evento B: prezzo
    peggiorato e size sparita dopo il delay (NON abbinata)."""
    a = _cache("A", delayed_book=_book(), winners={MID_OU: [UNDER], MID_MO: [33]})
    b = _cache("B", delayed_book=_book(under_back=(1.04, 30.0), over_lay=(1.08, 40.0)),
               winners={MID_OU: [UNDER], MID_MO: [33]})
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    for c in (a, b):
        with gzip.open(V.cache_path(str(cache_dir), c["event_id"]), "wt", encoding="utf-8") as fh:
            json.dump(c, fh)
    return str(cache_dir), a, b


# ------------------------------------------------------------- mattoni
def test_available_size_e_settle():
    lad = [[1.05, 10.0], [1.04, 20.0], [1.03, 30.0]]
    assert B.available_size(lad, "back", 1.05) == 10.0
    assert B.available_size(lad, "back", 1.04) == 30.0
    assert B.available_size(lad, "back", 1.06) == 0.0
    lay = [[1.06, 40.0], [1.07, 10.0]]
    assert B.available_size(lay, "lay", 1.06) == 40.0
    assert B.available_size(lay, "lay", 1.07) == 50.0
    assert B.available_size(lay, "lay", 1.05) == 0.0
    assert B.settle("back", 1.05, 5.0, 1) == pytest.approx(0.25)
    assert B.settle("back", 1.05, 5.0, 0) == -5.0
    assert B.settle("lay", 1.06, 5.0, 0) == 5.0
    assert B.settle("lay", 1.06, 5.0, 1) == pytest.approx(-0.30)
    assert B.settle("back", 1.05, 5.0, None) == 0.0


def test_max_drawdown():
    assert B.max_drawdown([1, -3, 2, -4, 5]) == 5.0
    assert B.max_drawdown([1, 2, 3]) == 0.0
    assert B.max_drawdown([]) == 0.0


# ------------------------------------------------------------- simulazione
def test_simulate_event_abbinata_delay_dedupe_e_commissione(two_events):
    _dir, a, b = two_events
    model = OpportunityModel(calibration="off")
    bets_a = B.simulate_event(a, model, stake=5.0)
    # due segnali (back Under, lay Over) ENTRAMBI abbinati; nessun duplicato dalla 2a istantanea
    assert {(x.side, x.selection_id) for x in bets_a} == {("back", UNDER), ("lay", OVER)}
    assert all(x.placed and x.matched and x.reason == "abbinata" for x in bets_a)
    assert all(x.outcome == (1 if x.selection_id == UNDER else 0) for x in bets_a)
    assert sum(x.pnl_gross for x in bets_a) == pytest.approx(0.25 + 5.0)
    assert all(x.family == "ou_line" and x.lambda_source == "pre_ko" for x in bets_a)
    # commissione 5% sul NETTO del mercato (5.25), ripartita sulle vincenti
    net = B.net_pnl(bets_a, 0.05)
    assert sum(net.values()) == pytest.approx(5.25 * 0.95)

    bets_b = B.simulate_event(b, model, stake=5.0)
    assert len(bets_b) == 2 and all(x.placed and not x.matched for x in bets_b)
    assert all("dopo il delay" in x.reason for x in bets_b)
    assert all(x.pnl_gross == 0.0 for x in bets_b)


def test_simulate_event_size_insufficiente_e_mercato_sospeso(two_events):
    _dir, a, _b = two_events
    model = OpportunityModel(calibration="off")
    # stake sopra la size al segnale (30): non piazzabile
    bets = B.simulate_event(a, model, stake=45.0)   # sopra le size al segnale (30 e 40)
    assert bets and all(not x.placed and not x.matched for x in bets)
    # mercato SUSPENDED dopo il delay: non abbinata
    a2 = json.loads(json.dumps(a))
    for s in a2["snapshots"]:
        s["delayed"] = _book(status="SUSPENDED")
    bets2 = B.simulate_event(a2, model, stake=5.0)
    assert bets2 and all(x.placed and not x.matched and "SUSPENDED" in x.reason for x in bets2)


def test_run_backtest_e_report(two_events, tmp_path):
    cache_dir, _a, _b = two_events
    paths = V.cached_events(cache_dir)
    assert len(paths) == 2
    res = B.run_backtest(paths, modes=("raw",), stake=5.0, commission=0.05,
                         calibration_path=str(tmp_path / "nessuna.json"), log=False)
    tot = res["modes"]["raw"]["summary"]["total"]
    assert tot["n_signals"] == 4 and tot["n_placed"] == 4 and tot["n_matched"] == 2
    assert tot["matched_pct"] == 50.0
    assert tot["staked"] == 10.0
    assert tot["pnl"] == pytest.approx(5.25 * 0.95)
    assert tot["roi"] == pytest.approx(100.0 * 5.25 * 0.95 / 10.0)
    assert tot["hit_rate"] == 100.0 and tot["max_dd"] == 0.0
    fams = res["modes"]["raw"]["summary"]["families"]
    assert set(fams) == {"ou_line/back", "ou_line/lay"}
    assert res["modes"]["raw"]["summary"]["events"]["B"]["n_matched"] == 0
    md = B.render_report(res)
    assert md.isascii() and "| raw |" in md and "| B | Nord FC v Sud FC |" in md

    # CLI: scrive il report e non fallisce sui flag
    report = tmp_path / "r.md"
    rc = B.main(["--cache-dir", cache_dir, "--raw", "--report", str(report),
                 "--calibration", str(tmp_path / "nessuna.json")])
    assert rc == 0 and report.is_file() and "Sintesi" in report.read_text(encoding="utf-8")


def test_run_backtest_modalita_calibrated_e_cv(two_events, tmp_path):
    cache_dir, _a, _b = two_events
    paths = V.cached_events(cache_dir)
    # tabella che schiaccia le P alte sotto la soglia di back: in 'calibrated'
    # il back Under sparisce, il lay Over resta
    tables = {f"ou_line|{CAL.bucket_of(85)}": {
        "n": 500, "applied": True, "bins": [], "knots": [[0.5, 0.3], [0.9999, 0.80]]}}
    cal_path = tmp_path / "cal.json"
    CAL.Calibrator({"version": 1, "tables": tables, "meta": {}}).save(str(cal_path))
    res = B.run_backtest(paths, modes=("raw", "calibrated", "cv"), stake=5.0,
                         calibration_path=str(cal_path), log=False)
    raw = res["modes"]["raw"]["summary"]["total"]
    cal = res["modes"]["calibrated"]["summary"]["total"]
    assert raw["n_signals"] == 4 and cal["n_signals"] == 2
    assert all(b.side == "lay" for b in res["modes"]["calibrated"]["bets"])
    # cv: con 2 eventi sintetici le tabelle restano sotto min_n -> identita' = raw
    cv = res["modes"]["cv"]["summary"]["total"]
    assert cv["n_signals"] == raw["n_signals"] and cv["pnl"] == pytest.approx(raw["pnl"])


# ------------------------------------------------------------- cache dai file grezzi
def _write_raw_event(root, eid="777"):
    d = root / eid
    d.mkdir()
    md_mo = {"marketType": "MATCH_ODDS", "inPlay": False, "status": "OPEN",
             "runners": [{"id": 11, "sortPriority": 1, "status": "ACTIVE"},
                         {"id": 22, "sortPriority": 2, "status": "ACTIVE"},
                         {"id": 33, "sortPriority": 3, "status": "ACTIVE"}]}
    md_ou = {"marketType": "OVER_UNDER_45", "inPlay": False, "status": "OPEN",
             "runners": [{"id": UNDER, "sortPriority": 1, "status": "ACTIVE"},
                         {"id": OVER, "sortPriority": 2, "status": "ACTIVE"}]}
    raw = [
        {"op": "mcm", "pt": T0 - 60_000, "mc": [
            {"id": MID_MO, "marketDefinition": md_mo,
             "rc": [{"id": 11, "atb": [[2.0, 50]]}, {"id": 22, "atb": [[4.0, 50]]}, {"id": 33, "atb": [[3.4, 50]]}]},
            {"id": MID_OU, "marketDefinition": md_ou}]},
        {"op": "mcm", "pt": T0, "mc": [{"id": MID_MO, "marketDefinition": {**md_mo, "inPlay": True}}]},
        {"op": "mcm", "pt": T0 + 100_000, "mc": [
            {"id": MID_OU, "marketDefinition": {**md_ou, "status": "CLOSED", "runners": [
                {"id": UNDER, "sortPriority": 1, "status": "WINNER"},
                {"id": OVER, "sortPriority": 2, "status": "LOSER"}]}},
            {"id": MID_MO, "marketDefinition": {**md_mo, "status": "CLOSED", "runners": [
                {"id": 11, "sortPriority": 1, "status": "LOSER"},
                {"id": 22, "sortPriority": 2, "status": "LOSER"},
                {"id": 33, "sortPriority": 3, "status": "WINNER"}]}}]},
    ]
    (d / f"{eid}.raw.jsonl").write_text("\n".join(json.dumps(r) for r in raw) + "\n", encoding="utf-8")

    def rec(pt, mid, runners, inplay=True, status="OPEN"):
        return {"market_id": mid, "pt": pt, "status": status, "inplay": inplay, "tv": 0, "runners": runners}

    ou_runners = {str(UNDER): {"b": [[1.05, 30.0]], "l": [[1.07, 20.0]], "ltp": 1.05, "tv": 0},
                  str(OVER): {"b": [[12.0, 5.0]], "l": [[1.06, 40.0]], "ltp": None, "tv": 0}}
    mo_runners = {"11": {"b": [[1.9, 100.0]], "l": [[1.95, 100.0]]}, "22": {"b": [[4.0, 50.0]], "l": [[4.2, 50.0]]},
                  "33": {"b": [[3.4, 80.0]], "l": [[3.5, 80.0]]}}
    stream = [
        rec(T0 - 30_000, MID_MO, mo_runners, inplay=False),
        rec(T0, MID_MO, mo_runners),                      # kickoff: prima istantanea
        rec(T0 + 1_000, MID_OU, ou_runners),
        rec(T0 + 7_000, MID_OU, {str(UNDER): {"b": [[1.04, 30.0]], "l": [[1.07, 20.0]]}}),  # peggiora a +7s
        rec(T0 + 12_000, MID_OU, ou_runners),             # torna @1.05 prima dell'istantanea a +10s? no: +12s
        rec(T0 + 21_000, MID_MO, mo_runners),
        rec(T0 + 31_000, MID_MO, mo_runners, status="CLOSED"),
    ]
    (d / f"{eid}.jsonl").write_text("\n".join(json.dumps(r) for r in stream) + "\n", encoding="utf-8")
    scores = [
        {"ts_ms": T0 - 1000, "minute": 0, "score_home": 0, "score_away": 0,
         "payload": {"score": {"home": {"name": "Nord FC", "numberOfRedCards": 0},
                               "away": {"name": "Sud FC", "numberOfRedCards": 0}}}},
        {"ts_ms": T0 + 5_000, "minute": 85, "score_home": 0, "score_away": 0,
         "payload": {"score": {"home": {"name": "Nord FC", "numberOfRedCards": 1},
                               "away": {"name": "Sud FC", "numberOfRedCards": 0}}}},
        {"ts_ms": T0 + 25_000, "minute": 90, "score_home": 0, "score_away": 0,
         "payload": {"score": {"home": {"name": "Nord FC", "numberOfRedCards": 1},
                               "away": {"name": "Sud FC", "numberOfRedCards": 0}}}},
    ]
    (d / f"{eid}.scores.jsonl").write_text("\n".join(json.dumps(r) for r in scores) + "\n", encoding="utf-8")
    return eid


def test_build_event_cache_da_file_grezzi(tmp_path):
    root = tmp_path / "raw"
    root.mkdir()
    eid = _write_raw_event(root)
    cache_dir = str(tmp_path / "cache")
    path = V.build_event_cache(str(root), eid, cache_dir, step_s=10.0, delay_s=5.0)
    assert path and os.path.isfile(path)
    c = V.load_event_cache(path)
    assert c["event_id"] == eid and c["home"] == "Nord FC" and c["away"] == "Sud FC"
    assert c["pre_ko"] == {"home": 2.0, "away": 4.0, "draw": 3.4}
    assert c["final"] == [0, 0] and c["final_minute"] == 90
    assert c["winners"] == {MID_OU: [UNDER], MID_MO: [33]}
    mk = c["markets"]
    assert mk[MID_OU]["type"] == "OVER_UNDER_45" and mk[MID_OU]["line"] == 4.5
    assert [r[2] for r in mk[MID_OU]["runners"]] == ["Under 4.5 Goals", "Over 4.5 Goals"]
    assert [r[3] for r in mk[MID_OU]["runners"]] == ["under_4_5", "over_4_5"]
    assert [r[2] for r in mk[MID_MO]["runners"]] == ["Nord FC", "Sud FC", "The Draw"]
    # istantanee ogni 10 s dal kickoff (T0, +10, +20, +30): la prima ha solo il MO
    ts = [s["ts"] for s in c["snapshots"]]
    assert ts == [T0, T0 + 10_000, T0 + 20_000, T0 + 30_000]
    s1 = c["snapshots"][1]
    assert s1["minute"] == 85 and s1["rh"] == 1 and s1["ra"] == 0
    assert s1["books"][MID_OU][2][str(UNDER)][0] == [[1.04, 30.0]]   # stato a +10s (peggiorato a +7s)
    assert s1["delayed"][MID_OU][2][str(UNDER)][0] == [[1.05, 30.0]]  # a +15s e' tornato @1.05
    s0 = c["snapshots"][0]
    assert MID_OU not in s0["books"] and s0["delayed"][MID_OU][2][str(UNDER)][0] == [[1.05, 30.0]]
    # payload nella forma del feed
    pl = V.snapshot_payload(c, s1)
    assert pl["inplay"] and pl["minute"] == 85 and pl["red_home"] == 1
    assert pl["odds"]["home"]["back"] == 1.9 and pl["mo_market_id"] == MID_MO and pl["mo_status"] == "OPEN"
    assert pl["ou"][0]["line"] == 4.5 and pl["ou"][0]["market_type"] == "OVER_UNDER_45"
    assert pl["ou"][0]["selections"][0] == {
        "selection_id": UNDER, "name": "Under 4.5 Goals", "runner_status": "ACTIVE",
        "back": 1.04, "lay": 1.07, "back_size": 30.0, "lay_size": 20.0}
    assert pl["ht_result"] is None and pl["btts"] is None
    assert V.market_outcome(c, MID_OU, UNDER) == 1 and V.market_outcome(c, MID_OU, OVER) == 0
    assert V.market_outcome(c, "1.999", UNDER) is None
    # cache riusata (nessuna ricostruzione) e lista
    assert V.build_event_cache(str(root), eid, cache_dir) == path
    assert V.cached_events(cache_dir) == [path]
    # campioni di calibrazione: un campione per minuto, esito dal WINNER
    samples = V.calibration_samples(c, lambdas=(1.3, 1.1))
    fams = {s.family for s in samples}
    assert fams == {"mo", "ou_line"}
    under = [s for s in samples if s.family == "ou_line" and s.outcome == 1]
    assert under and all(s.p_model > 0.9 for s in under)
    assert {s.minute for s in samples} == {0, 85, 90}


def test_build_event_cache_senza_stream_o_punteggi(tmp_path):
    root = tmp_path / "raw"
    (root / "1").mkdir(parents=True)
    assert V.build_event_cache(str(root), "1", str(tmp_path / "c")) is None


def test_selection_name_e_prob_key():
    assert V.selection_name("OVER_UNDER_25", 47972, 1, "A", "B") == "Under 2.5 Goals"
    assert V.prob_key_for("OVER_UNDER_25", 47973, 2) == "over_2_5"
    assert V.selection_name("BOTH_TEAMS_TO_SCORE", 30246, 1, "A", "B") == "Yes"
    assert V.prob_key_for("BOTH_TEAMS_TO_SCORE", 30247, 2) == "btts_no"
    assert V.selection_name("CORRECT_SCORE", 6, 10, "A", "B") == "2 - 1"
    assert V.prob_key_for("CORRECT_SCORE", 6, 10) == "cs_2_1"
    assert V.selection_name("CORRECT_SCORE", 9063254, 17, "A", "B") == "Any Other Home Win"
    assert V.prob_key_for("CORRECT_SCORE", 9063254, 17) == "cs_any_other_home"
    assert V.prob_key_for("CORRECT_SCORE", 123456, 19) == "cs_any_other_draw"
    assert V.selection_name("HALF_TIME_SCORE", 4506345, 10, "A", "B") == "Any Unquoted"
    assert V.prob_key_for("HALF_TIME_SCORE", 4, 7) == "hts_0_1"
    assert V.selection_name("HALF_TIME", 5, 3, "A", "B") == "The Draw"
    assert V.prob_key_for("HALF_TIME", 5, 2) == "ht_away"
    assert V.prob_key_for("DOUBLE_CHANCE", 1, 1) is None


# Soglie storiche per i test di meccanica (in produzione: lay spenti, back >=95%, edge 3%).
import pytest as _pytest
from Betfair.safe_strategy import opportunity as _opp_mod


@_pytest.fixture(autouse=True)
def _legacy_thresholds(monkeypatch):
    for k, v in {"min_edge": 0.02, "min_prob_back": 0.85, "max_prob_lay": 0.15}.items():
        monkeypatch.setitem(_opp_mod.DEFAULT_OPP_PARAMS, k, v)
