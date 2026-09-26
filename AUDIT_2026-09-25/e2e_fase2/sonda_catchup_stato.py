"""sonda_catchup_stato.py - 7.4.1 (migrazione applicata), 7.4.2 (RPC senza timeout),
7.4.6 (nessuna lega-stagione 'a meta': completed con buchi_aperti>0). SOLA LETTURA."""
from __future__ import annotations
import sys, time
sys.path.insert(0, ".")
from db_client import get_supabase_client

sb = get_supabase_client()

print("=== 7.4.1: funzioni presenti ===")
r = sb.table("pg_available?").select("*").limit(0).execute if False else None
# information_schema.routines non e' esposto via PostgREST: verifichiamo chiamando le RPC stesse
for nome, args in [
    ("season_detail_gaps", {"p_league_id": 0, "p_season_year": 0, "p_fixture_ids": None}),
    ("season_gaps_summary", {"p_league_ids": [0], "p_season_years": [0]}),
]:
    try:
        sb.rpc(nome, args).execute()
        print(f"  {nome}: OK (richiamabile)")
    except Exception as e:
        print(f"  {nome}: ERRORE {e}")

print("\n=== 7.4.2: RPC senza timeout (lega 135 stagione 2026) ===")
t0 = time.time()
resp = sb.rpc("season_detail_gaps", {"p_league_id": 135, "p_season_year": 2026, "p_fixture_ids": None}).execute()
print(f"  risposta in {time.time()-t0:.2f}s, righe={len(resp.data or [])}")

print("\n=== 7.4.6: season_backfill_state 'a meta' (completed con buchi_aperti>0) ===")
resp = sb.table("season_backfill_state").select(
    "league_id,season_year,status,updated_at,stats_json").order("updated_at", desc=True).limit(500).execute()
righe = resp.data or []
print(f"  righe lette (ultime 500 per updated_at): {len(righe)}")
sospette = []
for r in righe:
    sj = r.get("stats_json") or {}
    buchi = sj.get("buchi_aperti")
    if r.get("status") == "completed" and buchi not in (None, 0, "0"):
        sospette.append(r)
print(f"  'completed' con buchi_aperti>0: {len(sospette)}")
for r in sospette[:20]:
    print("   ", r["league_id"], r["season_year"], r.get("stats_json"))

print("\n=== distribuzione status (ultime 500) ===")
from collections import Counter
print(" ", Counter(r.get("status") for r in righe))

print("\n=== 7.4.6 (scan completo, non solo ultime 500): tutte le righe status='completed' ===")
resp = sb.table("season_backfill_state").select(
    "league_id,season_year,status,updated_at,stats_json", count="exact") \
    .eq("status", "completed").limit(2000).execute()
tot = resp.count
righe = resp.data or []
print(f"  totale righe status='completed' (count esatto): {tot}, lette: {len(righe)}")
sospette2 = []
for r in righe:
    sj = r.get("stats_json") or {}
    buchi = sj.get("buchi_aperti")
    if buchi not in (None, 0, "0"):
        sospette2.append(r)
print(f"  di queste, con buchi_aperti>0: {len(sospette2)}")
for r in sospette2[:20]:
    print("   ", r["league_id"], r["season_year"], r.get("stats_json"))

print("\n=== totale righe season_backfill_state ===")
resp2 = sb.table("season_backfill_state").select("league_id", count="exact").limit(1).execute()
print("  totale:", resp2.count)
