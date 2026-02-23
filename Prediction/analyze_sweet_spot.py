import os
import sys
# Add parent directory to sys.path to find db_client
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_client import get_supabase_client
import pandas as pd

def find_sweet_spot():
    sb = get_supabase_client()
    print("Fetching data...")
    # Fetch data joined with matches results
    query = """
    SELECT 
        (fp.db_json_analisi->'markets'->'first_half_over_0_5'->>'True')::numeric as prob,
        (fp.db_json_analisi->'inputs'->>'lambda_home')::numeric + (fp.db_json_analisi->'inputs'->>'lambda_away')::numeric as lambda_tot,
        (m.halftime_home + m.halftime_away > 0) as goal_ht,
        fp.league_id
    FROM fixture_predictions fp
    JOIN matches m ON fp.fixture_id = m.fixture_id
    WHERE fp.db_json_analisi IS NOT NULL
      AND m.status_short IN ('FT', 'AET', 'PEN')
      AND m.halftime_home IS NOT NULL
    """
    
    # Using a direct select if rpc is not available or failing
    # For speed and reliability in this environment, we'll try to fetch in chunks if needed, 
    # but let's try the rpc first as it's cleaner for join logic.
    try:
        res = sb.table("fixture_predictions").select("db_json_analisi, league_id, fixture_id").not_.is_("db_json_analisi", "null").execute()
        predictions = res.data
        
        # We need the match results too. Let's fetch matches for these fixture_ids
        f_ids = [r['fixture_id'] for r in predictions]
        # Chunked fetch of matches to avoid URL length issues
        match_data = {}
        for i in range(0, len(f_ids), 1000):
            batch_ids = f_ids[i:i+1000]
            m_res = sb.table("matches").select("fixture_id, halftime_home, halftime_away").in_("fixture_id", batch_ids).execute()
            for m in m_res.data:
                if m['halftime_home'] is not None and m['halftime_away'] is not None:
                    match_data[m['fixture_id']] = (m['halftime_home'] + m['halftime_away'] > 0)

        rows = []
        for p in predictions:
            fid = p['fixture_id']
            if fid in match_data:
                analisi = p['db_json_analisi']
                prob = float(analisi.get('markets', {}).get('first_half_over_0_5', {}).get('True', 0))
                l_h = float(analisi.get('inputs', {}).get('lambda_home', 0))
                l_a = float(analisi.get('inputs', {}).get('lambda_away', 0))
                rows.append({
                    'prob': prob,
                    'lambda_tot': l_h + l_a,
                    'goal': match_data[fid],
                    'league_id': p['league_id']
                })
        
        df = pd.DataFrame(rows)
        
        print("\n--- ANALYSIS BY CONFIDENCE (PROB) ---")
        for p_thresh in [0.70, 0.75, 0.80, 0.85, 0.90]:
            sub = df[df['prob'] >= p_thresh]
            if len(sub) > 0:
                print(f"Prob >= {p_thresh:.2f} | Vol: {len(sub)} | SR: {sub['goal'].mean():.2%}")

        print("\n--- ANALYSIS BY LAMBDA (EXPECTED GOALS) ---")
        for l_thresh in [2.0, 2.5, 3.0, 3.5]:
            sub = df[df['lambda_tot'] >= l_thresh]
            if len(sub) > 0:
                print(f"Lambda >= {l_thresh:.2f} | Vol: {len(sub)} | SR: {sub['goal'].mean():.2%}")

        sweet = df[(df['prob'] >= 0.80) & (df['lambda_tot'] >= 2.5)]
        league_stats = sweet.groupby('league_id')['goal'].agg(['count', 'mean']).sort_values('mean', ascending=False)
        top_leagues = league_stats[league_stats['count'] >= 20].head(10)

        import json
        output = {
            "confidenza": [
                {"prob": p_thresh, "vol": len(df[df['prob'] >= p_thresh]), "sr": float(df[df['prob'] >= p_thresh]['goal'].mean())}
                for p_thresh in [0.70, 0.75, 0.80, 0.85, 0.90]
            ],
            "lambda": [
                {"thresh": l_thresh, "vol": len(df[df['lambda_tot'] >= l_thresh]), "sr": float(df[df['lambda_tot'] >= l_thresh]['goal'].mean())}
                for l_thresh in [2.0, 2.5, 3.0, 3.5]
            ],
            "sweet_spot": {
                "volume": len(sweet),
                "sr": float(sweet['goal'].mean()) if len(sweet) > 0 else 0,
                "top_leagues": top_leagues.to_dict('index') if len(sweet) > 0 else {}
            }
        }
        with open("sweet_spot_results.json", "w") as f:
            json.dump(output, f, indent=4)
        print("\nResults saved to sweet_spot_results.json")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    find_sweet_spot()
