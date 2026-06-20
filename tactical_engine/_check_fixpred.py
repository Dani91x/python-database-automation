"""Verifica: quante fixture WC hanno gia' una riga in fixture_predictions,
e quali colonne sono NOT NULL (per decidere la strategia di upsert)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_client import get_supabase_client
sb = get_supabase_client()

# fixture_id delle partite WC
wc = sb.table("matches").select("fixture_id,status_short").eq("league_id", 1).execute().data
wc_ids = [r["fixture_id"] for r in wc]
print(f"WC fixtures totali: {len(wc_ids)}")

present = set()
for i in range(0, len(wc_ids), 100):
    chunk = wc_ids[i:i+100]
    rows = sb.table("fixture_predictions").select("fixture_id").in_("fixture_id", chunk).execute().data
    present.update(r["fixture_id"] for r in rows)
print(f"WC fixtures con riga in fixture_predictions: {len(present)} / {len(wc_ids)}")
print(f"WC fixtures SENZA riga (servirebbe INSERT): {len(wc_ids) - len(present)}")

# sample row: quali colonne ci sono
sample = sb.table("fixture_predictions").select("*").in_("fixture_id", list(present)[:1]).execute().data
if sample:
    print("\ncolonne fixture_predictions:", sorted(sample[0].keys()))
