"""Certificazione analytics_market_stats — FREQUENZE e RITARDI point-in-time.
⚠️ SOLDI IN GIOCO.

FIX LOOK-AHEAD (2026-06-22): compute_market_snapshots ora assegna a ogni partita
lo stato IN ENTRATA (pre-match, dalle partite PRECEDENTI), NON il valore "alla riga"
che includeva l'esito (delay_current era tautologico con hit). La matematica base
(_delays / _baseline_mm10, "alla riga") resta certificata vs gli RPC e alimenta
compute_current_state (forward). Il valore in-entrata della partita i == valore
alla-riga RPC della partita i-1 (SHIFT) == compute_current_state(serie[:i-1]).

Livelli:
  1) UNIT offline: matematica alla-riga (_delays/_baseline_mm10), helper in-entrata,
     no-look-ahead, coerenza con compute_current_state, per-selezione.
  2) CERTIFICAZIONE RPC (DB): lo SHIFT (in-entrata = RPC alla-riga shiftato).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analytics_market_stats import (
    _baseline_mm10, _delays, _freq_in_entrata, _delays_in_entrata,
    compute_market_snapshots, compute_current_state,
)

LEAGUE = 256


# ───────────────────────── UNIT: matematica ALLA-RIGA (base, vs RPC) ─────────
def test_delays_state_machine():
    series = [0, 0, 1, 0, 0, 0, 1, 1, 0]
    rits, record, media = _delays(series)
    assert rits == [1, 2, 0, 1, 2, 3, 0, 0, 1]
    assert record == 3
    assert abs(media - (10 / 6)) < 1e-9


def test_baseline_mm10_full_window_only():
    series = [1] * 9 + [0]
    baseline, mm10 = _baseline_mm10(series)
    assert abs(baseline - 0.9) < 1e-9
    assert mm10[:9] == [None] * 9
    assert abs(mm10[9] - 0.9) < 1e-9


# ───────────────────────── UNIT: helper IN ENTRATA (pre-match) ───────────────
def test_delays_in_entrata_no_lookahead():
    # serie:            0  0  1  0  0  0  1  1  0   (idx 1..9)
    # rit ALLA-RIGA:    1  2  0  1  2  3  0  0  1
    # rit IN ENTRATA:   N  1  2  0  1  2  3  0  0   (= alla-riga shiftato di +1; None al 1°)
    series = [0, 0, 1, 0, 0, 0, 1, 1, 0]
    inn = _delays_in_entrata(series)
    rit_in = [t[0] for t in inn]
    assert rit_in == [None, 1, 2, 0, 1, 2, 3, 0, 0]
    # lo shift è esatto: in-entrata(k) == alla-riga(k-1)
    alla_riga, _, _ = _delays(series)
    for k in range(1, len(series)):
        assert rit_in[k] == alla_riga[k - 1]


def test_freq_in_entrata_shift():
    series = [1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1]   # 11 punti
    inn = _freq_in_entrata(series)
    # baseline in-entrata della 2ª partita = media della 1ª = 1.0
    assert abs(inn[1][0] - 1.0) < 1e-9
    # mm10 in-entrata: serve >=10 partite PRECEDENTI → solo l'11ª (k=11) lo ha
    assert all(t[1] is None for t in inn[:10])      # prime 10: < 10 precedenti
    assert abs(inn[10][1] - sum(series[0:10]) / 10.0) < 1e-9  # media dei 10 precedenti


def _m(fid, date, fh, fa, hh=None, ha=None):
    return {"fixture_id": fid, "fixture_date": date, "status_short": "FT",
            "fulltime_home": fh, "fulltime_away": fa, "goals_home": fh, "goals_away": fa,
            "halftime_home": hh, "halftime_away": ha}


# ───────────────────────── UNIT: NO LOOK-AHEAD nel risultato finale ──────────
def test_snapshot_no_lookahead_vs_outcome():
    # 12 partite, totali noti. Con il fix, delay_current NON deve essere
    # tautologico con l'esito (prima: delay=0 ⟺ over, delay>=1 ⟺ under).
    totals = [(3, 0), (1, 0), (2, 1), (3, 3), (0, 0), (2, 2),
              (4, 0), (1, 1), (0, 1), (3, 2), (2, 0), (1, 2)]
    ms = [_m(100 + i, f"2020-02-{i+1:02d}T12:00:00+00:00", h, a)
          for i, (h, a) in enumerate(totals)]
    snaps = compute_market_snapshots("over_2_5", "Over", ms)
    # esiste almeno una partita con delay_current==0 che NON è Over (impossibile
    # nel vecchio codice tautologico) → prova che il look-ahead è rimosso
    found_break = False
    for i, (h, a) in enumerate(totals):
        fid = 100 + i
        s = snaps.get(fid)
        if s is None or s.delay_current is None:
            continue
        is_over = (h + a) > 2.5
        if (s.delay_current == 0) != is_over:
            found_break = True  # delay_current e esito NON coincidono → no leak
            break
    assert found_break, "delay_current ancora tautologico con l'esito (look-ahead non rimosso)"


def test_snapshot_coerente_con_forward():
    # lo snapshot IN ENTRATA della partita k == compute_current_state(serie[:k-1])
    totals = [(2, 0), (1, 1), (0, 2), (3, 1), (0, 0), (1, 2), (2, 2), (4, 0), (0, 1)]
    ms = [_m(200 + i, f"2021-04-{i+1:02d}T12:00:00+00:00", h, a)
          for i, (h, a) in enumerate(totals)]
    snaps = compute_market_snapshots("over_2_5", "Over", ms)
    for k in range(1, len(ms)):
        fid = 200 + k
        cur = compute_current_state("over_2_5", "Over", ms[:k])  # stato dopo le prime k
        s = snaps.get(fid)
        if s is None:
            continue
        assert s.delay_current == cur.delay_current, f"delay mismatch fid {fid}"
        fc_s = s.freq_current
        fc_c = cur.freq_current
        assert (fc_s is None) == (fc_c is None)
        if fc_s is not None:
            assert abs(fc_s - fc_c) < 1e-9


def test_per_selection_baseline_complementari():
    totals = [(3, 0), (4, 1), (2, 1), (3, 3), (5, 0), (2, 2), (4, 0),
              (3, 1), (0, 0), (1, 0), (3, 2), (5, 1), (2, 3)]
    ms = [_m(1000 + i, f"2020-01-{i+1:02d}T12:00:00+00:00", h, a)
          for i, (h, a) in enumerate(totals)]
    ov = compute_market_snapshots("over_2_5", "Over", ms)
    un = compute_market_snapshots("over_2_5", "Under", ms)
    fid = 1012
    # baseline in-entrata complementari (Over + Under = 1) e diverse (dati sbilanciati)
    assert abs(ov[fid].freq_baseline + un[fid].freq_baseline - 1.0) < 1e-9
    assert ov[fid].freq_baseline != un[fid].freq_baseline


# ─────────────────────────────── CERT vs RPC (DB): lo SHIFT ──────────────────
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


def test_cert_delay_shift_vs_rpc():
    # in-entrata(partita i) == rit ALLA-RIGA RPC(partita i-1); prima partita = None
    sb = _try_db()
    if sb is None:
        return
    ms = _fetch_matches(sb, LEAGUE)
    snaps = compute_market_snapshots("over_2_5", "Over", ms)
    d = sb.rpc("get_market_delays", {"p_league_id": LEAGUE, "p_market": "over",
               "p_target": "2.5", "p_mode": "all", "p_last_n": None,
               "p_season_year": None}).execute().data
    ser = d["series"]
    assert snaps[ser[0]["fid"]].delay_current is None
    mism = sum(1 for i in range(1, len(ser))
               if snaps[ser[i]["fid"]].delay_current != ser[i - 1]["rit"])
    assert mism == 0, f"{mism} shift-rit mismatch over_2_5"


def test_cert_freq_shift_vs_rpc():
    sb = _try_db()
    if sb is None:
        return
    ms = _fetch_matches(sb, LEAGUE)
    snaps = compute_market_snapshots("over_2_5", "Over", ms)
    f = sb.rpc("get_market_frequency", {"p_league_id": LEAGUE, "p_market": "ou_ft",
               "p_selection": "over", "p_line": 2.5, "p_mode": "all",
               "p_last_n": None, "p_season_year": None}).execute().data
    pts = f["points"]
    assert snaps[pts[0]["fid"]].freq_current is None
    mism = 0
    for i in range(1, len(pts)):
        s = snaps[pts[i]["fid"]]
        rm = pts[i - 1]["mm10"]            # mm10 alla-riga della partita PRECEDENTE
        if (rm is None) != (s.freq_current is None):
            mism += 1
        elif rm is not None and abs(rm - s.freq_current) > 1e-4:
            mism += 1
    assert mism == 0, f"{mism} shift-mm10 mismatch over_2_5"


def test_cert_delay_shift_1x2_draw():
    sb = _try_db()
    if sb is None:
        return
    ms = _fetch_matches(sb, LEAGUE)
    snaps = compute_market_snapshots("1x2", "D", ms)
    d = sb.rpc("get_market_delays", {"p_league_id": LEAGUE, "p_market": "x",
               "p_target": None, "p_mode": "all", "p_last_n": None,
               "p_season_year": None}).execute().data
    ser = d["series"]
    assert snaps[ser[0]["fid"]].delay_current is None
    mism = sum(1 for i in range(1, len(ser))
               if snaps[ser[i]["fid"]].delay_current != ser[i - 1]["rit"])
    assert mism == 0, f"{mism} shift-rit mismatch draw"


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
