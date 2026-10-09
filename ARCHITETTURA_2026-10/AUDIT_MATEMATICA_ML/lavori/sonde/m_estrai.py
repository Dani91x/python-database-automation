"""Sonda M1: estrae (SOLO SELECT, 8 query a finestre di data) il campione di partite concluse 21/09-07/10
con quote, Poisson grezzo/calibrato, ML servito e timestamp; salva un JSON compatto m_dati.json.
Stesso filtro di a_poisson_vs_quote_db.py (FT, db_json_analisi e raw_json_odds non null), ma con
ordine deterministico per fixture_id e finestre di data (la sonda A usava limit(800) senza order)."""
import sys, json, os
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
from db_client import get_supabase_client
sb = get_supabase_client()
SEL = ("fixture_id,fixture_date,created_at,updated_at,result_home_goals,result_away_goals,raw_json_odds,"
       "m:db_json_analisi->markets,mc:db_json_analisi->markets_calibrated,"
       "p_gen:db_json_analisi->>generated_at,p_cal:db_json_analisi->>calibrated_at,p_model:db_json_analisi->>model,"
       "ml1:model_predictions_json->targets->target_1x2,mlo:model_predictions_json->targets->target_over_2_5,"
       "mlb:model_predictions_json->targets->target_btts,ml_gen:model_predictions_json->>generated_at,"
       "ml_run:model_predictions_json->>run_id")
WIN = [("2026-09-21","2026-09-23"),("2026-09-23","2026-09-25"),("2026-09-25","2026-09-27"),("2026-09-27","2026-09-29"),
       ("2026-09-29","2026-10-01"),("2026-10-01","2026-10-03"),("2026-10-03","2026-10-05"),("2026-10-05","2026-10-08")]
def odds_book(raw):
    """stessa scelta del bookmaker di generate_dynamic_cal._extract_implied_1x2 + mercati OU2.5/BTTS."""
    bms = (raw or {}).get("bookmakers") or []
    if not bms: return None
    bm = next((b for b in bms if "betfair" in str(b.get("name","")).lower()), bms[0])
    return bm
def mk(bm, names):
    for bet in (bm.get("bets") or []):
        if str(bet.get("name","")) in names:
            d = {}
            for v in (bet.get("values") or []):
                try: d[str(v.get("value",""))] = float(v.get("odd",0))
                except (TypeError, ValueError): pass
            return d
    return None
out, stats = [], []
for a, b in WIN:
    r = (sb.table("fixture_predictions").select(SEL).eq("result_status_short","FT")
         .gte("fixture_date",a).lt("fixture_date",b).not_.is_("db_json_analisi","null").not_.is_("raw_json_odds","null")
         .order("fixture_id").limit(1000).execute().data or [])
    stats.append((a, b, len(r)))
    for x in r:
        raw = x.pop("raw_json_odds")
        bm = odds_book(raw)
        x["book"] = bm.get("name") if bm else None
        x["raw_keys"] = sorted(raw.keys()) if isinstance(raw, dict) else None
        if bm:
            x["o1x2"] = mk(bm, ("Match Winner","1X2","Fulltime Result"))
            x["oou"] = mk(bm, ("Goals Over/Under","Over/Under","Goals Over Under"))
            x["obt"] = mk(bm, ("Both Teams Score","BTTS","Both Teams to Score"))
        out.append(x)
print("finestre (da,a,righe):", stats, " totale", len(out))
json.dump(out, open(os.path.join(os.path.dirname(__file__), "m_dati.json"), "w"))
