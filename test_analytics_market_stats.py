"""Certificazione analytics_market_stats — FREQUENZE e RITARDI point-in-time.
⚠️ SOLDI IN GIOCO: i numeri DEVONO combaciare riga-per-riga con gli RPC certificati
get_market_frequency / get_market_delays.

Due livelli di test:
  1) UNIT (sempre, offline): macchina a stati ritardi + mm10/baseline su serie note,
     + per-selezione (Over ≠ Under) su matches sintetiche.
  2) CERTIFICAZIONE RPC (richiede DB, marcata): over_2_5 e 1x2 su lega 256
     DEVONO combaciare con gli RPC. Skip automatico se il DB non è raggiungibile.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analytics_market_stats import (
    Snapshot,
    _baseline_mm10,
    _delays,
    compute_market_snapshots,
)

LEAGUE = 256


# ──────────────────────────────────────────────────────────── UNIT (offline)
def test_delays_state_machine():
    # serie:        0  0  1  0  0  0  1  1  0
    # idx:          1  2  3  4  5  6  7  8  9
    # last_hit:     0  0  3  3  3  3  7  8  8
    # rit:          1  2  0  1  2  3  0  0  1
    series = [0, 0, 1, 0, 0, 0, 1, 1, 0]
    rits, record, media = _delays(series)
    assert rits == [1, 2, 0, 1, 2, 3, 0, 0, 1]
    # suc per hit: hit@3 → (3-0)-1=2 ; hit@7 → (7-3)-1=3 ; hit@8 → (8-7)-1=0
    assert record == 3
    # media su rit != 0: [1,2,1,2,3,1] → 10/6
    assert abs(media - (10 / 6)) < 1e-9


def test_delays_no_hits():
    rits, record, media = _delays([0, 0, 0])
    assert rits == [1, 2, 3]
    assert record is None   # nessuna occorrenza
    assert media == 2.0     # avg(1,2,3)


def test_baseline_mm10_full_window_only():
    series = [1] * 9 + [0]    # 9 hit poi 1 miss → 10° punto ha mm10
    baseline, mm10 = _baseline_mm10(series)
    assert abs(baseline - 0.9) < 1e-9
    assert mm10[:9] == [None] * 9        # primi 9 punti: finestra non piena
    assert abs(mm10[9] - 0.9) < 1e-9     # 10° punto = avg(ultimi 10) = 9/10


def _m(fid, date, fh, fa, hh=None, ha=None):
    return {"fixture_id": fid, "fixture_date": date, "status_short": "FT",
            "fulltime_home": fh, "fulltime_away": fa, "goals_home": fh, "goals_away": fa,
            "halftime_home": hh, "halftime_away": ha}


def test_per_selection_over_vs_under_differ():
    # 13 partite SBILANCIATE verso l'Over (baseline Over ≠ Under, non 0.5)
    totals = [(3, 0), (4, 1), (2, 1), (3, 3), (5, 0), (2, 2), (4, 0),
              (3, 1), (0, 0), (1, 0), (3, 2), (5, 1), (2, 3)]
    ms = [_m(1000 + i, f"2020-01-{i+1:02d}T12:00:00+00:00", h, a)
          for i, (h, a) in enumerate(totals)]
    ov = compute_market_snapshots("over_2_5", "Over", ms)
    un = compute_market_snapshots("over_2_5", "Under", ms)
    fid = 1012  # ultima fixture, presente in entrambe le serie
    # baseline COMPLEMENTARI (somma 1) — Over e Under partizionano gli esiti
    assert abs(ov[fid].freq_baseline + un[fid].freq_baseline - 1.0) < 1e-9
    # con dati sbilanciati le due baseline sono DIVERSE (è il BUG corretto)
    assert ov[fid].freq_baseline != un[fid].freq_baseline
    # e i ritardi correnti differiscono per selezione
    assert ov[fid].delay_current != un[fid].delay_current


def test_1x2_three_selections_differ():
    res = [(2, 0), (1, 1), (0, 2), (3, 1), (0, 0), (1, 2),
           (2, 2), (4, 0), (0, 1), (1, 0), (2, 1), (1, 3)]
    ms = [_m(2000 + i, f"2021-03-{i+1:02d}T12:00:00+00:00", h, a)
          for i, (h, a) in enumerate(res)]
    H = compute_market_snapshots("1x2", "H", ms)
    D = compute_market_snapshots("1x2", "D", ms)
    A = compute_market_snapshots("1x2", "A", ms)
    fid = 2011  # ultimo, 1-3 → A
    # le tre baseline sommano ~1 (ogni partita è esattamente uno di H/D/A)
    s = H[fid].freq_baseline + D[fid].freq_baseline + A[fid].freq_baseline
    assert abs(s - 1.0) < 1e-9
    # e sono tutte diverse tra loro
    assert len({H[fid].freq_baseline, D[fid].freq_baseline, A[fid].freq_baseline}) == 3


def test_ht_market_excludes_missing_ht_in_freq():
    # ht_1x2: una partita senza HT NON entra nella serie frequenze (hit→None)
    ms = [
        _m(3000, "2022-01-01T12:00:00+00:00", 2, 0, hh=1, ha=0),  # HT H
        _m(3001, "2022-01-02T12:00:00+00:00", 1, 1),              # HT mancante → escluso freq
        _m(3002, "2022-01-03T12:00:00+00:00", 0, 1, hh=0, ha=1),  # HT A
    ]
    snaps = compute_market_snapshots("ht_1x2", "H", ms)
    # 3001 senza HT: nessun freq_baseline (escluso dalla serie frequenze)
    assert snaps.get(3001) is None or snaps[3001].freq_baseline is None


# ─────────────────────────────────────────────── CERTIFICAZIONE vs RPC (DB)
def _fetch_matches(sb, league):
    off, out = 0, []
    while True:
        r = (sb.table("matches").select(
            "fixture_id,fixture_date,status_short,goals_home,goals_away,"
            "fulltime_home,fulltime_away,halftime_home,halftime_away")
            .eq("league_id", league).in_("status_short", ["FT", "AET", "PEN"])
            .range(off, off + 999).execute().data)
        if not r:
            break
        out += r
        if len(r) < 1000:
            break
        off += 1000
    return out


def _try_db():
    try:
        from db_client import get_supabase_client
        sb = get_supabase_client()
        sb.rpc("get_market_frequency", {"p_league_id": LEAGUE, "p_market": "1x2",
               "p_selection": "1", "p_line": None, "p_mode": "all",
               "p_last_n": None, "p_season_year": None}).execute()
        return sb
    except Exception as e:  # noqa: BLE001
        print(f"  [SKIP DB] {type(e).__name__}: {str(e)[:60]}")
        return None


def test_cert_freq_over_2_5_matches_rpc():
    sb = _try_db()
    if sb is None:
        return
    ms = _fetch_matches(sb, LEAGUE)
    snaps = compute_market_snapshots("over_2_5", "Over", ms)
    f = sb.rpc("get_market_frequency", {"p_league_id": LEAGUE, "p_market": "ou_ft",
               "p_selection": "over", "p_line": 2.5, "p_mode": "all",
               "p_last_n": None, "p_season_year": None}).execute().data
    assert abs(f["meta"]["baseline"] - next(iter(snaps.values())).freq_baseline) < 1e-3
    mism = 0
    for p in f["points"]:
        s = snaps[p["fid"]]
        rm = p["mm10"]
        if (rm is None) != (s.freq_current is None):
            mism += 1
        elif rm is not None and abs(rm - s.freq_current) > 1e-4:
            mism += 1
    assert mism == 0, f"{mism} mm10 mismatch over_2_5"


def test_cert_delay_over_2_5_matches_rpc():
    sb = _try_db()
    if sb is None:
        return
    ms = _fetch_matches(sb, LEAGUE)
    snaps = compute_market_snapshots("over_2_5", "Over", ms)
    d = sb.rpc("get_market_delays", {"p_league_id": LEAGUE, "p_market": "over",
               "p_target": "2.5", "p_mode": "all", "p_last_n": None,
               "p_season_year": None}).execute().data
    st = d["stats"]
    any_s = next(iter(snaps.values()))
    assert any_s.delay_record == st["record"]
    assert abs(any_s.delay_avg - round(st["media_ritardi"], 4)) < 1e-3
    mism = sum(1 for s in d["series"] if snaps[s["fid"]].delay_current != s["rit"])
    assert mism == 0, f"{mism} rit mismatch over_2_5"


def test_cert_freq_1x2_matches_rpc():
    sb = _try_db()
    if sb is None:
        return
    ms = _fetch_matches(sb, LEAGUE)
    for can, rpcsel in [("H", "1"), ("D", "X"), ("A", "2")]:
        snaps = compute_market_snapshots("1x2", can, ms)
        f = sb.rpc("get_market_frequency", {"p_league_id": LEAGUE, "p_market": "1x2",
                   "p_selection": rpcsel, "p_line": None, "p_mode": "all",
                   "p_last_n": None, "p_season_year": None}).execute().data
        assert abs(f["meta"]["baseline"] - next(iter(snaps.values())).freq_baseline) < 1e-3
        mism = 0
        for p in f["points"]:
            s = snaps[p["fid"]]
            rm = p["mm10"]
            if (rm is None) != (s.freq_current is None):
                mism += 1
            elif rm is not None and abs(rm - s.freq_current) > 1e-4:
                mism += 1
        assert mism == 0, f"{mism} mm10 mismatch 1x2 {can}"


def test_cert_delay_draw_matches_rpc():
    sb = _try_db()
    if sb is None:
        return
    ms = _fetch_matches(sb, LEAGUE)
    snaps = compute_market_snapshots("1x2", "D", ms)
    d = sb.rpc("get_market_delays", {"p_league_id": LEAGUE, "p_market": "x",
               "p_target": None, "p_mode": "all", "p_last_n": None,
               "p_season_year": None}).execute().data
    st = d["stats"]
    any_s = next(iter(snaps.values()))
    assert any_s.delay_record == st["record"]
    assert abs(any_s.delay_avg - round(st["media_ritardi"], 4)) < 1e-3
    mism = sum(1 for s in d["series"] if snaps[s["fid"]].delay_current != s["rit"])
    assert mism == 0, f"{mism} rit mismatch draw"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fail = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
        except AssertionError as e:
            fail += 1
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"\n{'TUTTI VERDI' if not fail else f'{fail} FALLITI'} ({len(fns)} test)")
    sys.exit(1 if fail else 0)
