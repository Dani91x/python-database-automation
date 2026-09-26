"""sonda_feed_atlante_73_stato.py - 7.3.2/7.3.3 (e2e fase 2, 26/09): fotografia in SOLA LETTURA
dello stato del motore a domanda dell'atlante v4.
Fonti: DB (GET PostgREST: hazard_atlas_leghe, fixture_predictions) + file locali del motore
(Betfair/omega/data/hazard_atlas_live.json, hazard_atlas_stato.json: SOLO lettura, mai scritti).
Ricalcola in modo indipendente l'ordine di preparazione atteso (ciclo(): leghe osservate nella
finestra [ora-36h, ora+36h] ordinate per primo calcio d'inizio, atlante_a_domanda.py:421-432)
e conta quante leghe con partite IN GIOCO ORA (KO fra ora-2h e ora) hanno gia' il v4.
Uso: python sonda_feed_atlante_73_stato.py  -> stampa JSON e lo accoda a sonda_73_stato.jsonl
"""
import datetime as dt, json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sonda_feed_atlante_db import get

RADICE = Path(__file__).resolve().parents[2]
DATA = RADICE / "Betfair" / "omega" / "data"
ora = time.time()
iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(timespec="seconds")
def ts(s):
    d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).timestamp()

out = {"sonda_utc": iso(ora)}
# 1) DB: righe dell'atlante per lega
st, righe, ms = get("hazard_atlas_leghe?select=league_id,n_fixtures,last_fixture_date,updated_at,"
                    "v4_aff:stato->v4->affidabile,forza_n:stato->v4->forza->n,"
                    "scarti:stato->v4->scarti&order=updated_at.desc&limit=1000")
assert st == 200, righe
out["db_righe"] = len(righe); out["db_ms"] = ms
out["db_ha_v4"] = sum(1 for r in righe if r.get("v4_aff") is not None)
out["db_con_forza"] = sum(1 for r in righe if (r.get("forza_n") or 0) > 0)
out["db_updated_at"] = sorted({r["updated_at"] for r in righe})
out["db_leghe"] = {str(r["league_id"]): {"n": r["n_fixtures"], "ult": r["last_fixture_date"],
                   "forza_n": r.get("forza_n"), "v4_aff": r.get("v4_aff"), "scarti": r.get("scarti")} for r in righe}
# 2) partite osservate (stessa GET del motore) e ordine atteso
lo, hi = iso(ora - 36 * 3600).replace("+00:00", "Z"), iso(ora + 36 * 3600).replace("+00:00", "Z")
st, fp, ms = get(f"fixture_predictions?select=fixture_id,league_id,league_name,fixture_date"
                 f"&fixture_date=gte.{lo}&and=(fixture_date.lt.{hi})&order=fixture_date.asc&limit=3000")
assert st == 200, fp
primo, nomi, inplay = {}, {}, set()
for r in fp:
    if r.get("league_id") is None or r.get("fixture_id") is None: continue
    l = str(r["league_id"]); k = ts(r["fixture_date"])
    primo[l] = min(primo.get(l, k), k); nomi[l] = r.get("league_name")
    if ora - 2 * 3600 <= k <= ora: inplay.add(l)
ordine = sorted(primo, key=lambda l: primo[l])
out["partite_osservate"] = len(fp); out["leghe_osservate"] = len(primo)
out["prime_15_attese"] = [(l, nomi[l], iso(primo[l])) for l in ordine[:15]]
dbset = set(out["db_leghe"])
out["leghe_in_gioco_ora"] = len(inplay)
out["leghe_in_gioco_con_v4_db"] = sorted(inplay & dbset)
out["pos_media_in_ordine_delle_leghe_in_gioco"] = (sum(ordine.index(l) for l in inplay) / len(inplay)) if inplay else None
out["prima_lega_in_gioco_pos"] = min((ordine.index(l) for l in inplay), default=None)
# 3) file locali (sola lettura)
try:
    s = json.loads((DATA / "hazard_atlas_stato.json").read_text(encoding="utf-8"))
    out["stato_file"] = {"mtime_utc": iso(os.path.getmtime(DATA / "hazard_atlas_stato.json")),
                         "leghe": sorted(s["leghe"], key=int), "senza_dati": s.get("senza_dati"),
                         "n_calcolate_ultima_ora": len([t for t in s.get("calcolate_ts", []) if ora - t < 3600]),
                         "in_attesa": len(s.get("in_attesa", {})), "da_scrivere": s.get("da_scrivere"),
                         "ultimo_flush_utc": iso(s["ultimo_flush"]) if s.get("ultimo_flush") else None}
    a = json.loads((DATA / "hazard_atlas_live.json").read_text(encoding="utf-8"))
    m = a.get("meta", {}); v = (a.get("v4") or {}).get("meta", {})
    out["live_file"] = {"mtime_utc": iso(os.path.getmtime(DATA / "hazard_atlas_live.json")),
                        "generated_at": m.get("generated_at"), "n_leagues_in_state": m.get("n_leagues_in_state"),
                        "in_preparazione": len(m.get("leghe_in_preparazione") or []),
                        "v4_n_leghe": v.get("n_leghe"), "v4_affidabili": v.get("n_leghe_affidabili"),
                        "v4_globale_solido": v.get("globale_solido"), "v4_n_partite_aff": v.get("n_partite_affidabili")}
    out["coerenza_file_db"] = sorted(s["leghe"], key=int) == sorted(dbset, key=int)
    out["prime_attese_vs_stato"] = {"attese_prime_10": ordine[:10],
                                    "calcolate_o_senza_dati": sorted(set(s["leghe"]) | set(s.get("senza_dati") or {}), key=int)}
except Exception as e:
    out["file_err"] = repr(e)
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
with open(Path(__file__).resolve().parent / "sonda_73_stato.jsonl", "a", encoding="utf-8") as fh:
    fh.write(json.dumps(out, ensure_ascii=False, default=str) + "\n")
