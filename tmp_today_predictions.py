"""
Clean, complete predictions for EVERY today's fixture and EVERY market.
Real team names from the Segnali sheet, network retries, all markets shown.
Output: console + tmp_today_predictions.md (readable report).
"""
from __future__ import annotations

import os
import sys
import json
import time
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "Ai Engine"))
os.environ["MODEL_CACHE_TTL_HOURS"] = "0"

import config
import gspread

# 1. Names from the sheet
gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_FILE)
vals = gc.open_by_key(config.SPREADSHEET_ID).worksheet("Segnali").get_all_values()
hdr = vals[0]
ix = {h: i for i, h in enumerate(hdr)}
sheet = {}
for r in vals[1:]:
    c = ix["Fixture ID"]
    if len(r) > c and r[c].strip().isdigit():
        fid = int(r[c])
        name = (r[ix["Nome Evento (API-Football)"]] or r[ix["Nome Evento (Betfair)"]]).strip()
        sheet[fid] = {"name": name, "league": r[ix["League Name"]], "data": r[ix["Data Evento"]]}

rows = json.load(open(os.path.join(ROOT, "tmp_today_fixtures.json")))
leagues = sorted({r["league_id"] for r in rows if r.get("league_id")})
dl = os.path.join(ROOT, "Ai Engine", "models_cache", "downloaded")
for lid in leagues:
    d = os.path.join(dl, f"league_{lid}")
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)

from ai_engine.predict_fixture import predict_fixture

LABELS = [
    ("target_1x2", "1X2"), ("target_over_0_5", "Over 0.5"), ("target_over_1_5", "Over 1.5"),
    ("target_over_2_5", "Over 2.5"), ("target_over_3_5", "Over 3.5"), ("target_btts", "BTTS"),
    ("target_ht_over_0_5", "HT Over 0.5"),
]
FIN = {"FT", "AET", "PEN"}


def predict_retry(fid, tries=5):
    last = ""
    for k in range(tries):
        try:
            return predict_fixture(fid, store=False)
        except Exception as e:
            last = str(e)
            if any(s in last for s in ("getaddrinfo", "Temporary", "Connection", "timed out", "Max retries")):
                time.sleep(3 * (k + 1))
                continue
            return {"__error__": last[:160]}
    return {"__error__": f"network retries exhausted: {last[:100]}"}


def market_line(t: dict, key: str) -> str | None:
    if key not in t:
        return None
    p = t[key]
    if key == "target_1x2":
        fav = max(p, key=p.get)
        favn = {"H": "Casa", "D": "Pareggio", "A": "Trasferta"}[fav]
        return f"1X2 -> Casa {p.get('H',0)*100:.0f}% | Pareggio {p.get('D',0)*100:.0f}% | Trasferta {p.get('A',0)*100:.0f}%   (favorito: {favn})"
    lbl = dict(LABELS)[key]
    return f"{lbl}: {p.get('True',0)*100:.0f}% si"


report = []
for r in rows:
    fid = r["fid"]
    meta = sheet.get(fid, {})
    out = predict_retry(fid)
    rec = {"fid": fid, "name": meta.get("name", f"fixture {fid}"), "league": meta.get("league", "?"),
           "league_id": r.get("league_id"), "status": r.get("live_status"),
           "finished": r.get("finished"), "gh": r.get("live_gh"), "ga": r.get("live_ga")}
    if "__error__" in out:
        rec["error"] = out["__error__"]
    else:
        rec["targets"] = out.get("targets", {})
        rec["n_signals"] = len(out.get("bet_signals", []))
    report.append(rec)

json.dump(report, open(os.path.join(ROOT, "tmp_today_predictions.json"), "w"), indent=2, default=str)

# ---------- build readable report ----------
lines = []
def emit(s=""):
    lines.append(s)
    print(s)

def status_label(x):
    if x["finished"]:
        return f"FINITA {x['gh']}-{x['ga']}"
    return {"NS": "da giocare", "1H": "in corso (1T)", "2H": "in corso (2T)", "HT": "intervallo", "CANC": "ANNULLATA"}.get(x["status"], x["status"] or "?")

emit("# PREVISIONI MODELLO — partite di oggi (2026-06-09), tutti i mercati\n")
order = sorted(report, key=lambda x: (0 if x.get("finished") else (1 if x.get("status") in ("1H","2H","HT") else 2)))
done_ml = 0
for x in order:
    if x.get("error") or not x.get("targets"):
        emit(f"## {x['name']}  ({x['league']})  — [{status_label(x)}]")
        emit(f"   (nessuna previsione: {x.get('error','modello non disponibile per questa lega')})")
        emit("")
        continue
    done_ml += 1
    emit(f"## {x['name']}  ({x['league']}, league_id {x['league_id']})  — [{status_label(x)}]")
    t = x["targets"]
    for key, _ in LABELS:
        ln = market_line(t, key)
        if ln:
            emit("   " + ln)
    # show any other markets present (non-priority)
    extra = [k for k in t if k not in dict(LABELS)]
    for k in extra:
        p = t[k]
        if isinstance(p, dict):
            top = max(p, key=p.get)
            emit(f"   {k.replace('target_','')}: {top} {p[top]*100:.0f}%")
    if x["finished"]:
        gh, ga = int(x["gh"]), int(x["ga"])
        real = "Casa" if gh > ga else ("Trasferta" if gh < ga else "Pareggio")
        emit(f"   >> RISULTATO REALE {gh}-{ga} (esito 1X2: {real}, totale gol: {gh+ga})")
    emit("")

emit("-" * 60)
emit(f"Partite con previsione: {done_ml}/{len(report)}")
emit("NOTA: EV/scommesse non calcolati dove mancano le quote nel DB; qui mostro le PROBABILITA' del modello per ogni mercato.")

open(os.path.join(ROOT, "tmp_today_predictions.md"), "w", encoding="utf-8").write("\n".join(lines))
print("\nsaved tmp_today_predictions.md")
