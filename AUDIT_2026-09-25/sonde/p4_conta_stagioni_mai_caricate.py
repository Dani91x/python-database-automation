"""Conta le stagioni P4 (mai caricate) sul DB vero, CON IL CODICE DI PRODUZIONE (25/09/2026).

Legge solo file JSON gia' scaricati in sola lettura da p4_sonda_get.py:
  c*.json  api_coverage_by_season (colonne vere, 8.742 righe)
  s*.json  season_backfill_state: league_id, season_year, status, versione, mc = stats_json.fixtures.matches_count
  v*.json / w*.json  vista league_season_riepilogo_popolamento (fixtures_in_matches = conteggio vivo in matches;
           solo le pagine che non sono andate in 57014)
e applica seasons_catchup.seleziona_p4 (stessa funzione del catchup) con le leghe dell'atlante e dei modelli ML.
Uso: python AUDIT_2026-09-25/sonde/p4_conta_stagioni_mai_caricate.py <cartella dei json>
"""
import glob
import json
import os
import sys
from collections import Counter
from datetime import date

RADICE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, RADICE)
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("API_FOOTBALL_KEY", "x")
import season_gaps as sg  # noqa: E402
import seasons_catchup as sc  # noqa: E402

cart = sys.argv[1]
OGGI = date(2026, 9, 25)


def carica(pref):
    return [r for f in sorted(glob.glob(os.path.join(cart, pref + "*.json"))) for r in json.load(open(f))]


cov = carica("c")
sta = {(r["league_id"], r["season_year"]): r for r in carica("s")}
vista = {(r["league_id"], r["season_year"]): r["fixtures_in_matches"] for r in carica("v") + carica("w")}
print(f"coverage {len(cov)}, stati {len(sta)}, righe vista con conteggio vivo {len(vista)}")

# 1) affidabilita' di stats_json.fixtures.matches_count contro il conteggio vivo
d = Counter()
for k, n in vista.items():
    s = sta.get(k)
    mc = None if s is None or s.get("mc") is None else int(s["mc"])
    n = int(n or 0)
    if mc is None:
        d["stato assente"] += 1
    elif mc == n:
        d["uguale"] += 1
    elif mc == 0 and n > 0:
        d["stato 0, DB >0"] += 1
    elif mc > 0 and n == 0:
        d["stato >0, DB 0"] += 1
    else:
        d["diverso (entrambi >0)"] += 1
print("stato vs conteggio vivo:", dict(d))

# 2) selezione P4 con il codice di produzione
stati = {k: {"status": s.get("status"),
             "stats_json": {"meta": {"version": s.get("versione")}, "fixtures": {"matches_count": s.get("mc")}}}
         for k, s in sta.items()}
atlante = sc.leghe_prioritarie({})
ml = sc.leghe_modelli_ml()
cand, conti = sc.seleziona_p4(cov, stati, {}, OGGI, atlante, ml, anche_senza_eventi=False)
print(f"atlante {len(atlante)} leghe, modelli ML {len(ml)} leghe")
print(f"P4 (0 partite, eventi True): {len(cand)}; esclusi: {conti}")
for c in cand:
    r = c.row
    print(f"  lega {c.chiave[0]} stagione {c.chiave[1]} fascia {c.fascia} importanza {c.importanza} "
          f"current={r.get('current')} fine={r.get('season_end')} costo~{c.costo}")
print("costo totale stimato:", sum(c.costo for c in cand))
tutte, _ = sc.seleziona_p4(cov, stati, {}, OGGI, atlante, ml, anche_senza_eventi=True)
print(f"con CATCHUP_P4_ANCHE_SENZA_EVENTI=1: {len(tutte)}, costo {sum(c.costo for c in tutte)}")

# 3) cosa resta fuori dalla P4 e perche'
passate = [r for r in cov if sc.passata_per_p4(r, OGGI) and any(sg.flag_per_fixture(r).values())
           and sg.stagione_iniziata(r, OGGI)]
ignote = [r for r in passate if (r["league_id"], r["season_year"]) not in sta]
print(f"stagioni passate per data con almeno un flag: {len(passate)}; senza stato (conteggio ignoto): {len(ignote)}")
v1 = sum(1 for r in passate if (sta.get((r["league_id"], r["season_year"])) or {}).get("versione") == "v1")
print(f"  di cui con stato v1 (mai verificate dal backfill automatico, rotazione 150/notte): {v1}")
zombie = [r for r in cov if sc.current_sospetta(r, OGGI)]
print(f"stagioni 'current' ma finite da oltre 30 gg (da verificare con /leagues): {len(zombie)}; di cui a 0 "
      f"partite secondo lo stato: {[(r['league_id'], r['season_year']) for r in zombie if str((sta.get((r['league_id'], r['season_year'])) or {}).get('mc')) == '0']}")
