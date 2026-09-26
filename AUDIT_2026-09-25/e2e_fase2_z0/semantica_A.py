"""VERIFICA SEMANTICA A (piano §3-bis/§7.9.1.A) - SOLA LETTURA.

3 partite calcio in gioco del feed, 3 istanti a ~20 s: riga `safe_strategy_scan` (SELECT) vs
libro Betfair REST `listMarketBook` (EX_BEST_OFFERS, sola lettura) vs IPS `get_scores`.
Chiamate Betfair dichiarate: 1 login (sessione PROPRIA), 3 listMarketBook, 3 get_scores, 1 logout
della PROPRIA sessione. Nessun ordine, nessuna scrittura DB. Si lancia dalla radice del checkout
principale (per il .env). Uso: python semantica_A.py <out.json>
"""
import json
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, ".")
from db_client import get_supabase_client  # noqa: E402
from Betfair.stream.auth import build_client, safe_logout  # noqa: E402
from Betfair.stream.scores.betfair_inplay import parse_score_dict  # noqa: E402
import betfairlightweight.filters as F  # noqa: E402


def _ts(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()


def main():
    dest = sys.argv[1]
    sb = get_supabase_client()
    rows = (sb.table("safe_strategy_scan").select("event_id,updated_at,payload")
            .eq("sport", "calcio").execute().data or [])
    ora = time.time()
    cand = [r for r in rows if (r.get("payload") or {}).get("inplay")
            and (r["payload"].get("mo_status") == "OPEN") and ora - _ts(r["updated_at"]) < 10
            and (r["payload"].get("minute") or 0) > 0]
    cand.sort(key=lambda r: -(r["payload"].get("minute") or 0))
    scelte = [r["event_id"] for r in cand[:3]]
    client = build_client(login=True)
    out = {"scelte": scelte, "istanti": [], "chiamate_betfair": {"login": 1, "listMarketBook": 0,
                                                                   "get_scores": 0, "logout": 0}}
    try:
        for k in range(3):
            t_db0 = time.time()
            rr = (sb.table("safe_strategy_scan").select("event_id,updated_at,payload")
                  .in_("event_id", scelte).execute().data or [])
            t_db1 = time.time()
            per = {r["event_id"]: r for r in rr}
            mids = [per[e]["payload"]["mo_market_id"] for e in scelte if e in per]
            t_bf0 = time.time()
            books = client.betting.list_market_book(
                market_ids=mids, price_projection=F.price_projection(price_data=["EX_BEST_OFFERS"]),
                lightweight=True)
            t_bf1 = time.time()
            out["chiamate_betfair"]["listMarketBook"] += 1
            t_ips0 = time.time()
            scores = client.in_play_service.get_scores(event_ids=scelte, lightweight=True) or []
            t_ips1 = time.time()
            out["chiamate_betfair"]["get_scores"] += 1
            bk = {b["marketId"]: b for b in books}
            sc = {str(s.get("eventId")): s for s in scores if isinstance(s, dict)}
            ist = {"k": k, "t_db": [t_db0, t_db1], "t_bf": [t_bf0, t_bf1], "t_ips": [t_ips0, t_ips1],
                   "partite": []}
            for e in scelte:
                r = per.get(e)
                if not r:
                    ist["partite"].append({"event_id": e, "errore": "riga scan assente"})
                    continue
                p = r["payload"]
                b = bk.get(p["mo_market_id"]) or {}
                sel_book = {}
                for run in b.get("runners") or []:
                    ex = run.get("ex") or {}
                    atb = ex.get("availableToBack") or []
                    atl = ex.get("availableToLay") or []
                    sel_book[run["selectionId"]] = {
                        "back": atb[0]["price"] if atb else None, "back_size": atb[0]["size"] if atb else None,
                        "lay": atl[0]["price"] if atl else None, "lay_size": atl[0]["size"] if atl else None}
                confronto = {}
                for lato, o in (p.get("odds") or {}).items():
                    sb_ = sel_book.get(o.get("selection_id")) or {}
                    confronto[lato] = {"scan": {k2: o.get(k2) for k2 in ("back", "lay", "back_size", "lay_size")},
                                       "book": sb_}
                snap = parse_score_dict(e, sc[e]) if e in sc else None
                ist["partite"].append({
                    "event_id": e, "nome": p.get("event_name"), "market_id": p["mo_market_id"],
                    "scan_updated_at": r["updated_at"], "eta_scan_s_a_lettura_book": round(t_bf1 - _ts(r["updated_at"]), 3),
                    "book_status": b.get("status"), "book_inplay": b.get("inplay"),
                    "scan_mo_status": p.get("mo_status"),
                    "confronto_quote": confronto,
                    "scan_minuto": p.get("minute"), "scan_score": [p.get("score_home"), p.get("score_away")],
                    "ips_minuto": getattr(snap, "minute", None) if snap else None,
                    "ips_score": [getattr(snap, "score_home", None), getattr(snap, "score_away", None)] if snap else None,
                    "ips_status": getattr(snap, "status", None) if snap else None,
                })
            out["istanti"].append(ist)
            if k < 2:
                time.sleep(20)
    finally:
        safe_logout(client)
        out["chiamate_betfair"]["logout"] = 1
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)
    for ist in out["istanti"]:
        print("istante", ist["k"], datetime.fromtimestamp(ist["t_bf"][1], tz=timezone.utc).isoformat())
        for pz in ist["partite"]:
            print("  ", pz.get("event_id"), pz.get("nome"), "eta", pz.get("eta_scan_s_a_lettura_book"),
                  "min scan/ips", pz.get("scan_minuto"), pz.get("ips_minuto"),
                  "score scan/ips", pz.get("scan_score"), pz.get("ips_score"), pz.get("book_status"))
            for lato, c in (pz.get("confronto_quote") or {}).items():
                print("      ", lato, "scan", c["scan"]["back"], c["scan"]["lay"], "| book", c["book"].get("back"),
                      c["book"].get("lay"), "| size scan", c["scan"]["back_size"], c["scan"]["lay_size"],
                      "book", c["book"].get("back_size"), c["book"].get("lay_size"))
    print(json.dumps(out["chiamate_betfair"]))


main()
