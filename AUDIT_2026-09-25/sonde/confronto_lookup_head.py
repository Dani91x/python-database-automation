"""SONDA (25/09): il nuovo ``hazard_lookup`` (forma corta di
``consulta_atlante``) da' gli STESSI numeri di quello di HEAD sugli atlanti
veri committati (v2 in uso, v3 seme), su ogni lega x bucket x gol x
orizzonte, a livello lega e a livello squadre (coppie di squadre per nome
della stessa lega). Nessun DB. Da lanciare dalla radice del worktree."""
import json
import subprocess
import sys
import types

sys.path.insert(0, ".")
from Betfair.stream.scalper import hazard_atlas as NUOVO  # noqa: E402

src = subprocess.run(["git", "show", "HEAD:Betfair/stream/scalper/hazard_atlas.py"],
                     capture_output=True, text=True, check=True).stdout
VECCHIO = types.ModuleType("hazard_atlas_head")
VECCHIO.__file__ = NUOVO.__file__
exec(compile(src, "hazard_atlas_head", "exec"), VECCHIO.__dict__)

for nome in ("v2", "v3"):
    atl = json.load(open(f"Betfair/omega/data/hazard_atlas_{nome}.json", encoding="utf-8"))
    per_lega = {}
    for t in atl["by_team"].values():
        per_lega.setdefault(str(t["league_id"]), []).append(t["team_name"])
    n = diversi = squadre = 0
    for lid in list(atl["by_league"]) + ["999999", None]:
        nomi = (per_lega.get(str(lid)) or [])[:6]
        coppie = [(None, None)] + [(a, b) for a in nomi[:3] for b in nomi[3:6]]
        for minuto in range(0, 91, 1):
            for gol in range(0, 5):
                for oriz in ("p_goal_next_3min", "p_goal_next_2min"):
                    for h, a in coppie:
                        v = VECCHIO.hazard_lookup(atl, minuto, gol, lid, h, a, oriz)
                        w = NUOVO.hazard_lookup(atl, minuto, gol, lid, h, a, oriz)
                        n += 1
                        squadre += v[1] == "team"
                        if v != w:
                            diversi += 1
                            if diversi <= 5:
                                print("DIVERSO", nome, lid, minuto, gol, oriz, h, a, v, w)
    print(f"{nome}: {n} confronti, livello squadre {squadre}, diversi {diversi}")
