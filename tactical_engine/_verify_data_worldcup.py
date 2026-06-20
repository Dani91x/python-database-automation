"""Cond.3 - Verifica completezza/correttezza matematica dei dati World Cup (lega 1).
Read-only. NON modifica nulla. Stampa un certificato dei dati."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collections import Counter
from db_client import get_supabase_client

LEAGUE_ID = 1
PLAYED = ("FT", "AET", "PEN")

def main() -> int:
    sb = get_supabase_client()
    rows = sb.table("matches").select(
        "fixture_id,season_year,fixture_date,status_short,"
        "home_team_id,home_team_name,away_team_id,away_team_name,"
        "goals_home,goals_away,halftime_home,halftime_away,"
        "fulltime_home,fulltime_away,venue_city"
    ).eq("league_id", LEAGUE_ID).execute().data

    played = [r for r in rows if r["status_short"] in PLAYED]
    print(f"=== CERTIFICATO DATI WORLD CUP (lega {LEAGUE_ID}) ===")
    print(f"righe totali: {len(rows)} | giocate (FT/AET/PEN): {len(played)}")
    print("per stagione:", dict(sorted(Counter(r["season_year"] for r in played).items())))

    problems = []
    def check(name, bad):
        n = len(bad)
        print(f"  [{'OK ' if n == 0 else 'FAIL'}] {name}: {n} anomalie")
        if n:
            problems.append((name, n, bad[:5]))

    check("fixture_id univoci", [fid for fid, c in Counter(r["fixture_id"] for r in played).items() if c > 1])
    check("goals_home non-null", [r["fixture_id"] for r in played if r["goals_home"] is None])
    check("goals_away non-null", [r["fixture_id"] for r in played if r["goals_away"] is None])
    check("halftime_home non-null", [r["fixture_id"] for r in played if r["halftime_home"] is None])
    check("halftime_away non-null", [r["fixture_id"] for r in played if r["halftime_away"] is None])
    check("fixture_date presente", [r["fixture_id"] for r in played if not r["fixture_date"]])
    check("team_id casa/trasferta presenti", [r["fixture_id"] for r in played if not r["home_team_id"] or not r["away_team_id"]])
    check("gol >= 0", [r["fixture_id"] for r in played
                       if (r["goals_home"] or 0) < 0 or (r["goals_away"] or 0) < 0])
    # HT <= FT (coerenza matematica: gol primo tempo non possono superare i totali)
    check("HT <= FT (casa)", [r["fixture_id"] for r in played
                              if r["halftime_home"] is not None and r["goals_home"] is not None
                              and r["halftime_home"] > r["goals_home"]])
    check("HT <= FT (trasferta)", [r["fixture_id"] for r in played
                                   if r["halftime_away"] is not None and r["goals_away"] is not None
                                   and r["halftime_away"] > r["goals_away"]])
    # SCORELINE REGOLAMENTARE = fulltime (90') con fallback su goals.
    # Per le partite AET/PEN, goals include i supplementari: NON usiamo goals ma fulltime.
    # Quindi una differenza goals!=fulltime e' ATTESA e SOLO per AET/PEN.
    check("fulltime presente (90')", [r["fixture_id"] for r in played
                                      if r["fulltime_home"] is None or r["fulltime_away"] is None])
    # Anomalia VERA: goals!=fulltime in una partita NON andata ai supplementari/rigori
    check("goals==fulltime nei match FT puri", [r["fixture_id"] for r in played
                                                if r["status_short"] == "FT"
                                                and r["fulltime_home"] is not None and r["goals_home"] is not None
                                                and (r["fulltime_home"] != r["goals_home"]
                                                     or r["fulltime_away"] != r["goals_away"])])
    check("home != away (no self-match)", [r["fixture_id"] for r in played if r["home_team_id"] == r["away_team_id"]])

    teams = set()
    for r in played:
        teams.add((r["home_team_id"], r["home_team_name"]))
        teams.add((r["away_team_id"], r["away_team_name"]))
    print(f"\nsquadre distinte: {len(teams)}")
    # distribuzione partite per squadra (per capire la sparsita')
    tc = Counter()
    for r in played:
        tc[r["home_team_name"]] += 1
        tc[r["away_team_name"]] += 1
    pc = sorted(tc.values())
    print(f"partite/squadra: min={pc[0]} mediana={pc[len(pc)//2]} max={pc[-1]} (media={sum(pc)/len(pc):.1f})")
    print("top5 per #partite:", [f'{n}:{c}' for n, c in tc.most_common(5)])

    # statistiche gol (sanity matematica)
    gh = [r["goals_home"] for r in played if r["goals_home"] is not None]
    ga = [r["goals_away"] for r in played if r["goals_away"] is not None]
    print(f"\nmedia gol casa: {sum(gh)/len(gh):.3f} | media gol trasferta: {sum(ga)/len(ga):.3f}")
    print(f"max gol casa: {max(gh)} | max gol trasferta: {max(ga)}")
    print("campo neutro atteso -> media casa ~ media trasferta (h dovrebbe ~0)")

    print("\n" + ("=== CERTIFICATO: DATI VALIDI ===" if not problems
                  else f"=== CERTIFICATO: {len(problems)} PROBLEMI -> {[p[0] for p in problems]} ==="))
    return 0 if not problems else 1

if __name__ == "__main__":
    raise SystemExit(main())
