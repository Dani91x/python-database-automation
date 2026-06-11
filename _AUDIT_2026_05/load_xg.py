"""READ-ONLY: carica expected_goals per fixture/squadra e li mappa home/away. Cache pickle."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from db_client import get_supabase_client
from dataload import get_league_data

c = get_supabase_client()
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
PAGE = 1000


def load_xg_league(league_id: int) -> pd.DataFrame:
    """Ritorna df fixture_id, xg_home, xg_away."""
    rows, start = [], 0
    while True:
        resp = c.table("match_team_stats").select("fixture_id,team_id,value_numeric") \
            .eq("league_id", league_id).eq("stat_type", "expected_goals") \
            .range(start, start + PAGE - 1).execute()
        d = resp.data or []
        rows.extend(d)
        if len(d) < PAGE:
            break
        start += PAGE
    if not rows:
        return pd.DataFrame(columns=["fixture_id", "xg_home", "xg_away"])
    xg = pd.DataFrame(rows)
    xg["value_numeric"] = pd.to_numeric(xg["value_numeric"], errors="coerce")
    # mappa con matches per sapere chi e' home/away
    m, _ = get_league_data(league_id)
    mm = m[["fixture_id", "home_team_id", "away_team_id"]]
    xg = xg.merge(mm, on="fixture_id", how="inner")
    xg["side"] = "other"
    xg.loc[xg["team_id"] == xg["home_team_id"], "side"] = "home"
    xg.loc[xg["team_id"] == xg["away_team_id"], "side"] = "away"
    piv = xg[xg["side"].isin(["home", "away"])].pivot_table(
        index="fixture_id", columns="side", values="value_numeric", aggfunc="first")
    piv = piv.rename(columns={"home": "xg_home", "away": "xg_away"}).reset_index()
    return piv


if __name__ == "__main__":
    import glob
    leagues = sorted(int(os.path.basename(f).split("_")[1].split(".")[0])
                     for f in glob.glob(os.path.join(CACHE, "matches_*.pkl")))
    for lid in leagues:
        x = load_xg_league(lid)
        x.to_pickle(os.path.join(CACHE, f"xg_{lid}.pkl"))
        cov = x[["xg_home", "xg_away"]].notna().all(axis=1).sum() if not x.empty else 0
        print(f"lega {lid}: {len(x)} fixture con xG (completi home+away: {cov})", flush=True)
    print("DONE")
