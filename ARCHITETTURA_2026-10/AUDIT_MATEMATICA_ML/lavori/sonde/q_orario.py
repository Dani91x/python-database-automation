"""Sonda Q2: orario delle quote (raw_json_odds->>'update') vs calcio d'inizio e vs generazione della previsione.
Riusa le funzioni di m_misure.py (eseguite fino a 'out = []', senza rilanciare il report) e i dati m_dati.json + q_ts.json.
Sola lettura locale, nessun accesso al DB."""
import os, json, sys
import numpy as np
from collections import Counter
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "m_misure.py"), encoding="utf-8").read().split("\nout = []\n")[0]
G = {"__file__": os.path.join(HERE, "m_misure.py"), "__name__": "m_funcs"}
exec(compile(src, "m_misure_funcs", "exec"), G)
hrs, build, report, MK, parse = G["hrs"], G["build"], G["report"], G["MK"], G["parse"]
TS = {x["fixture_id"]: x for x in json.load(open(os.path.join(HERE, "q_ts.json")))}
D = G["D"]
assert len(TS) == len(D) == 1519 and set(TS) == {r["fixture_id"] for r in D}, "campione diverso da m_dati.json"
out = []
def dist(lab, v):
    v = np.array(v, float)
    if not len(v):
        out.append(f"{lab}: n=0"); return
    out.append(f"{lab}: n={len(v)} min={v.min():.2f} p25={np.percentile(v,25):.2f} med={np.median(v):.2f} p75={np.percentile(v,75):.2f} max={v.max():.2f}")
out.append("# q_orario.py - orario delle quote (raw_json_odds.update) sul campione 21/09-07/10 (n=1519)")
# coerenza timestamp tra le due estrazioni
diff = [r["fixture_id"] for r in D if r.get("p_gen") != TS[r["fixture_id"]]["p_gen"] or r.get("ml_gen") != TS[r["fixture_id"]]["ml_gen"]]
out.append(f"coerenza p_gen/ml_gen tra m_dati.json e q_ts.json: righe diverse={len(diff)}")
nupd = sum(1 for x in TS.values() if not x["upd"])
out.append(f"righe senza 'update' in raw_json_odds: {nupd}")
kick_upd = [hrs(x["upd"], x["fixture_date"]) for x in TS.values() if x["upd"]]
dist("(fixture_date - update) ore [>0 = quote PRIMA del calcio d'inizio]", kick_upd)
out.append(f"  update DOPO il calcio d'inizio: {sum(1 for v in kick_upd if v < 0)}; entro 1h prima: {sum(1 for v in kick_upd if 0 <= v < 1)}; entro 3h prima: {sum(1 for v in kick_upd if 0 <= v < 3)}")
upd_p = [hrs(x["p_gen"], x["upd"]) for x in TS.values() if x["upd"] and x["p_gen"]]
dist("(update - generated_at Poisson) ore [>0 = quote DOPO la previsione]", upd_p)
out.append(f"  update DOPO generated_at Poisson: {sum(1 for v in upd_p if v > 0)} ({100*np.mean(np.array(upd_p)>0):.1f}%); entro 5 min dopo: {sum(1 for v in upd_p if 0 < v <= 5/60)}; piu' di 1h dopo: {sum(1 for v in upd_p if v > 1)}")
upd_m = [hrs(x["ml_gen"], x["upd"]) for x in TS.values() if x["upd"] and x["ml_gen"]]
dist("(update - generated_at ML) ore", upd_m)
out.append(f"  update DOPO generated_at ML: {sum(1 for v in upd_m if v > 0)} su {len(upd_m)}; ML mancante: {sum(1 for x in TS.values() if not x['ml_gen'])}")
age = [hrs(x["upd"], x["created_at"]) for x in TS.values() if x["upd"] and x["created_at"]]
dist("(created_at riga - update) ore", age)
out.append("giorno di update vs giorno di fixture_date (UTC): stesso giorno=%d, update giorno precedente=%d, altro=%d" % (
    sum(1 for x in TS.values() if x["upd"][:10] == x["fixture_date"][:10]),
    sum(1 for x in TS.values() if x["upd"][:10] < x["fixture_date"][:10]),
    sum(1 for x in TS.values() if x["upd"][:10] > x["fixture_date"][:10])))
out.append("orari UTC di 'update' piu' frequenti (ora): " + str(Counter(x["upd"][11:13] for x in TS.values() if x["upd"]).most_common(8)))
out.append("orari UTC di p_gen piu' frequenti (ora): " + str(Counter(x["p_gen"][11:13] for x in TS.values() if x["p_gen"]).most_common(8)))
# fixture_date dell'oggetto odds coincide con fixture_date della riga? (sanita' dell'abbinamento)
mm = sum(1 for x in TS.values() if x["fx_date_odds"] and parse(x["fx_date_odds"]) != parse(x["fixture_date"]))
out.append(f"fixture.date dentro raw_json_odds diversa da fixture_date della riga: {mm}")
# per finestra di data: quanti con update > p_gen
byday = Counter(); tot = Counter()
for x in TS.values():
    d = x["fixture_date"][:10]; tot[d] += 1
    if x["upd"] and x["p_gen"] and hrs(x["p_gen"], x["upd"]) > 0: byday[d] += 1
out.append("update>p_gen per giorno (n_dopo/n): " + ", ".join(f"{d}:{byday[d]}/{tot[d]}" for d in sorted(tot) if byday[d]))

# --- Confronto 1X2 sui sottocampioni "quote disponibili alla previsione"
rows, sk = build("1X2")
for r in rows:
    r["upd"] = TS[r["fid"]]["upd"]
out.append(f"\n## 1X2: righe valide (quote+Poisson)={len(rows)} scartate={dict(sk)}")
def ok_pg(r): return r["upd"] and r["p_gen"] and hrs(r["p_gen"], r["upd"]) <= 0
def ok_ml(r): return ok_pg(r) and r["ml"] is not None and r["ml_gen"] and hrs(r["ml_gen"], r["upd"]) <= 0
S_all = rows
S_pre = [r for r in rows if ok_pg(r)]
S_post = [r for r in rows if r["upd"] and r["p_gen"] and not ok_pg(r)]
S_ml_all = [r for r in rows if r["ml"] is not None]
S_ml_pre = [r for r in rows if ok_ml(r)]
S_pre3 = [r for r in S_pre if hrs(r["upd"], r["kick"]) >= 3]
out.append(f"n: tutte={len(S_all)}  update<=p_gen={len(S_pre)}  update>p_gen={len(S_post)}  con ML={len(S_ml_all)}  con ML e update<=min(p_gen,ml_gen)={len(S_ml_pre)}  update<=p_gen e >=3h prima del kickoff={len(S_pre3)}")
report("1X2", [dict(r, ml=None) for r in S_pre], out, "P: update <= generated_at Poisson (quote disponibili alla previsione), senza ML")
report("1X2", S_ml_pre, out, "PM: con ML, update <= min(p_gen, ml_gen)")
if len(S_post) > 100:
    report("1X2", [dict(r, ml=None) for r in S_post], out, "X: update > generated_at Poisson (controllo)")
else:
    out.append(f"(sottocampione update>p_gen n={len(S_post)}: troppo piccolo per il report, non eseguito)")
if len(S_pre3) > 100 and len(S_pre3) != len(S_pre):
    report("1X2", [dict(r, ml=None) for r in S_pre3], out, "P3: update <= p_gen e >=3h prima del kickoff")
# --- Controllo extra: previsione E quote strettamente PRIMA del calcio d'inizio
pk = sum(1 for x in TS.values() if x["p_gen"] and hrs(x["p_gen"], x["fixture_date"]) < 0)
out.append(f"Poisson generated_at DOPO il calcio d'inizio: {pk} su {len(TS)}")
S_strict = [r for r in S_ml_pre if hrs(r["upd"], r["kick"]) > 0 and hrs(r["p_gen"], r["kick"]) > 0 and hrs(r["ml_gen"], r["kick"]) > 0]
out.append(f"## 1X2 sottocampione STRETTO: quote, Poisson e ML tutti generati prima del kickoff e update<=min(p_gen,ml_gen): n={len(S_strict)}")
report("1X2", S_strict, out, "S: tutto prima del kickoff, quote <= previsioni")
txt = "\n".join(out)
print(txt)
open(os.path.join(HERE, "q_orario_output.txt"), "w", encoding="utf-8").write(txt)
