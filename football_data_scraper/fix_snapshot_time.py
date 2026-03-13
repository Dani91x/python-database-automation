"""
Fix snapshot_time for all football_data_csv records in match_odds.
Updates directly by fixture_id batches — no SELECT on match_odds needed.
"""
import sys
import os
import logging
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

LEAGUE_IDS = [39, 40, 41, 42, 43, 61, 62, 78, 79, 88, 94, 135, 136, 140, 144, 179, 180, 197, 203]
BATCH_SIZE = 50  # fixture_ids per UPDATE call


def fix_league(sb, league_id: int):
    # 1. Fetch fixture_id → fixture_date from matches (small table, always works)
    log.info(f"[{league_id}] Fetching fixture dates...")
    r = sb.table("matches").select("fixture_id,fixture_date").eq("league_id", league_id).execute()
    if not r.data:
        log.info(f"[{league_id}] No fixtures, skipping.")
        return 0

    # Group fixture_ids by date (same date → same snapshot_time)
    date_to_fids = defaultdict(list)
    for row in r.data:
        fdate = row.get("fixture_date")
        if fdate:
            date_str = str(fdate)[:10]  # YYYY-MM-DD
            snap_time = date_str + "T12:00:00+00:00"
            date_to_fids[snap_time].append(row["fixture_id"])

    log.info(f"[{league_id}] {len(r.data)} fixtures across {len(date_to_fids)} distinct dates.")

    # 2. For each date, UPDATE match_odds in batches of BATCH_SIZE fixture_ids
    updated_batches = 0
    for snap_time, fids in date_to_fids.items():
        for i in range(0, len(fids), BATCH_SIZE):
            batch = fids[i:i + BATCH_SIZE]
            sb.table("match_odds") \
                .update({"snapshot_time": snap_time}) \
                .in_("fixture_id", batch) \
                .eq("snapshot_type", "football_data_csv") \
                .is_("snapshot_time", "null") \
                .execute()
            updated_batches += 1

    log.info(f"[{league_id}] Done. {updated_batches} UPDATE calls issued.")
    return updated_batches


def main():
    sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    for lid in LEAGUE_IDS:
        fix_league(sb, lid)
    log.info("=== Completato ===")


if __name__ == "__main__":
    main()
