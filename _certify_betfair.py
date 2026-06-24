"""
_certify_betfair.py — certifica get_betfair_fixtures / get_betfair_odds vs engine_signals grezzo.
Uso: python _certify_betfair.py
"""
import sys, datetime as dt
sys.stdout.reconfigure(encoding="utf-8")
from db_client import get_supabase_client
sb = get_supabase_client()

MAP = {  # codice engine_signals -> (mercato canonico, selezione)
    "H": ("1x2", "H"), "D": ("1x2", "D"), "A": ("1x2", "A"),
    "HT_H": ("ht_1x2", "H"), "HT_D": ("ht_1x2", "D"), "HT_A": ("ht_1x2", "A"),
    "O15": ("over_1_5", "Over"), "U15": ("over_1_5", "Under"),
    "O25": ("over_2_5", "Over"), "U25": ("over_2_5", "Under"),
    "O35": ("over_3_5", "Over"), "U35": ("over_3_5", "Under"),
    "BTTS": ("btts", "Yes"), "BTTS_NO": ("btts", "No"),
    "HT05": ("first_half_over_0_5", "Over"), "HT_U05": ("first_half_over_0_5", "Under"),
}


def es_rows(fid=None, run_date=None):
    rows, start = [], 0
    while True:
        q = sb.table("engine_signals").select("fixture_id,run_date,market,odds")
        if fid is not None:
            q = q.eq("fixture_id", fid)
        if run_date is not None:
            q = q.eq("run_date", run_date)
        d = q.order("fixture_id").range(start, start + 999).execute().data
        rows += d
        if len(d) < 1000:
            break
        start += 1000
    return rows


def main():
    oggi = dt.date.today().isoformat()
    mism = 0

    # 1) get_betfair_fixtures: set fixture == distinct engine_signals(run_date) ∩ fixture_predictions
    rpc = sb.rpc("get_betfair_fixtures", {"p_date": oggi}).execute().data
    rpc_set = set(x["fixture_id"] for x in rpc)
    es_fids = set(r["fixture_id"] for r in es_rows(run_date=oggi))
    # quali di questi esistono in fixture_predictions
    fp = set()
    for i in range(0, len(es_fids), 200):
        chunk = list(es_fids)[i:i + 200]
        d = sb.table("fixture_predictions").select("fixture_id").eq("status", "ok").in_("fixture_id", chunk).execute().data
        fp |= set(x["fixture_id"] for x in d)
    oracle_set = es_fids & fp
    if rpc_set != oracle_set:
        print("MISMATCH lista:", "solo_RPC", rpc_set - oracle_set, "solo_oracolo", oracle_set - rpc_set); mism += 1
    print(f"get_betfair_fixtures: RPC {len(rpc_set)} == oracolo {len(oracle_set)} -> {'OK' if rpc_set==oracle_set else 'MISMATCH'}")

    # 2) get_betfair_odds: per un campione di fixture, jsonb == max(odds) per mercato mappato
    sample = list(rpc_set)[:8]
    for fid in sample:
        rpc_o = sb.rpc("get_betfair_odds", {"p_fixture_id": fid}).execute().data
        # oracolo: max odds per codice, mappato
        best = {}
        for r in es_rows(fid=fid):
            if r["odds"] is None:
                continue
            best[r["market"]] = max(best.get(r["market"], -1), float(r["odds"]))
        oracle_o = {}
        for code, odd in best.items():
            if code in MAP:
                mk, sel = MAP[code]
                oracle_o.setdefault(mk, {})[sel] = odd
        # confronto
        ok = True
        keys = set(rpc_o) | set(oracle_o)
        for mk in keys:
            ro, oo = rpc_o.get(mk, {}), oracle_o.get(mk, {})
            sels = set(ro) | set(oo)
            for s in sels:
                if abs(float(ro.get(s, -999)) - float(oo.get(s, -999))) > 1e-9:
                    ok = False; print(f"  MISMATCH {fid} {mk}/{s}: RPC {ro.get(s)} vs oracolo {oo.get(s)}")
        if not ok:
            mism += 1
    print(f"get_betfair_odds: {len(sample)} fixture verificate, mismatch {mism if mism else 0}")
    print("\nESITO:", "✅ CERTIFICATO" if mism == 0 else f"❌ {mism} mismatch")


if __name__ == "__main__":
    main()
