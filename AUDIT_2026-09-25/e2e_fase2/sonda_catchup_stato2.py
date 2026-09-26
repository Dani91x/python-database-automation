"""sonda_catchup_stato2.py - 7.4.6 scan COMPLETO (paginato) di season_backfill_state
status='completed': nessuna deve avere buchi_aperti>0 (nessuna lega-stagione 'a meta').
SOLA LETTURA."""
import sys
sys.path.insert(0, ".")
from db_client import get_supabase_client

sb = get_supabase_client()
PAGINA = 1000
offset = 0
tot = 0
sospette = []
while True:
    resp = sb.table("season_backfill_state").select("league_id,season_year,status,stats_json") \
        .eq("status", "completed").range(offset, offset + PAGINA - 1).execute()
    righe = resp.data or []
    tot += len(righe)
    for r in righe:
        sj = r.get("stats_json") or {}
        buchi = sj.get("buchi_aperti")
        if buchi not in (None, 0, "0"):
            sospette.append(r)
    if len(righe) < PAGINA:
        break
    offset += PAGINA

print(f"righe 'completed' scansionate: {tot}")
print(f"con buchi_aperti>0 (a meta'): {len(sospette)}")
for r in sospette[:30]:
    print(" ", r["league_id"], r["season_year"], r.get("stats_json"))
