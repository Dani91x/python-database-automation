"""
Certificazione Studio Ritardi — STEP 1: scarica lo storico di league_id=1
(World Cup) replicando ESATTAMENTE la CTE `scope`/`ordered` della RPC
get_market_delays, cosi' l'input del foglio Excel e della RPC e' identico.

Settlement 90' (identico a get_market_frequency / get_market_delays):
  h = fulltime_home se non null, altrimenti goals_home solo se status='FT'
  a = idem per away
  evento valido (riga DATI MATCH) = h e a non null
  ordine cronologico: fixture_date asc, fixture_id asc
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_client import get_supabase_client

LEAGUE_ID = 1
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cert_wc_data.json")


def fetch_all():
    sb = get_supabase_client()
    cols = ("fixture_id,fixture_date,home_team_name,away_team_name,"
            "fulltime_home,fulltime_away,goals_home,goals_away,"
            "halftime_home,halftime_away,status_short,season_year")
    rows = []
    page = 0
    SIZE = 1000
    while True:
        q = (sb.table("matches").select(cols)
             .eq("league_id", LEAGUE_ID)
             .in_("status_short", ["FT", "AET", "PEN"])
             .range(page * SIZE, page * SIZE + SIZE - 1))
        data = q.execute().data
        rows.extend(data)
        if len(data) < SIZE:
            break
        page += 1
    return rows


def settle(rows):
    """Applica settlement 90' + filtro evento valido + ordine cronologico."""
    out = []
    for r in rows:
        fh, fa = r.get("fulltime_home"), r.get("fulltime_away")
        gh, ga = r.get("goals_home"), r.get("goals_away")
        st = r.get("status_short")
        h = fh if fh is not None else (gh if st == "FT" else None)
        a = fa if fa is not None else (ga if st == "FT" else None)
        if h is None or a is None:
            continue  # non e' una riga DATI MATCH
        out.append({
            "fixture_id": r["fixture_id"],
            "fixture_date": r["fixture_date"],
            "home": r["home_team_name"],
            "away": r["away_team_name"],
            "gc": int(h), "ga": int(a),
            "gcfh": None if r.get("halftime_home") is None else int(r["halftime_home"]),
            "gafh": None if r.get("halftime_away") is None else int(r["halftime_away"]),
            "season_year": r.get("season_year"),
        })
    # ordine deterministico identico alla RPC
    out.sort(key=lambda x: (x["fixture_date"], x["fixture_id"]))
    return out


def main():
    raw = fetch_all()
    ev = settle(raw)
    ht = sum(1 for e in ev if e["gcfh"] is not None and e["gafh"] is not None)
    print(f"matches grezze settlate (FT/AET/PEN): {len(raw)}")
    print(f"eventi validi DATI MATCH (h,a non null): {len(ev)}")
    print(f"copertura HT: {ht}/{len(ev)} = {100*ht/len(ev):.1f}%" if ev else "no eventi")
    if ev:
        print(f"intervallo: {ev[0]['fixture_date']}  ->  {ev[-1]['fixture_date']}")
        print("\nprimi 3 eventi:")
        for e in ev[:3]:
            print(f"  #{ev.index(e)+1} {e['fixture_date'][:10]} {e['home']} {e['gc']}-{e['ga']} {e['away']} (PT {e['gcfh']}-{e['gafh']})")
        print("ultimi 3 eventi:")
        for e in ev[-3:]:
            print(f"  {e['fixture_date'][:10]} {e['home']} {e['gc']}-{e['ga']} {e['away']} (PT {e['gcfh']}-{e['gafh']})")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(ev, f, ensure_ascii=False)
    print(f"\nsalvato -> {OUT}")


if __name__ == "__main__":
    main()
