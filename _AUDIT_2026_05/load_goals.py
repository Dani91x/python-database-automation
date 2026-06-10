"""READ-ONLY: tempi dei gol per fixture (per simulazione in-play). Cache pickle."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from db_client import get_supabase_client
c = get_supabase_client()
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
PAGE = 1000


def load_goals_league(league_id: int) -> pd.DataFrame:
    rows, start = [], 0
    while True:
        resp = c.table("match_events").select("fixture_id,minute,minute_extra,detail,event_type") \
            .eq("league_id", league_id).eq("event_type", "Goal") \
            .range(start, start + PAGE - 1).execute()
        d = resp.data or []
        rows.extend(d)
        if len(d) < PAGE:
            break
        start += PAGE
    if not rows:
        return pd.DataFrame(columns=["fixture_id", "minute"])
    df = pd.DataFrame(rows)
    # escludi rigori sbagliati (non sono gol)
    df = df[df["detail"] != "Missed Penalty"].copy()
    df["minute"] = pd.to_numeric(df["minute"], errors="coerce").fillna(0).astype(int)
    return df[["fixture_id", "minute"]]


if __name__ == "__main__":
    import glob
    leagues = sorted(int(os.path.basename(f).split("_")[1].split(".")[0])
                     for f in glob.glob(os.path.join(CACHE, "matches_*.pkl")))
    for lid in leagues:
        g = load_goals_league(lid)
        g.to_pickle(os.path.join(CACHE, f"goals_{lid}.pkl"))
        nfix = g["fixture_id"].nunique() if not g.empty else 0
        print(f"lega {lid}: {len(g)} gol su {nfix} fixture", flush=True)
    print("DONE")
