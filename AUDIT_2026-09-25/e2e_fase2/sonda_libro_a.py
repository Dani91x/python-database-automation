"""sonda_libro_a.py - E2E FASE 2 (26/09), semantica A: riga del feed unico vs LIBRO BETFAIR VERO vs IPS.

SOLA LETTURA, chiamate Betfair DICHIARATE (e registrate nel file d'uscita, una per una):
  * login cert .it (Betfair.stream.auth.build_client) -> una sessione nuova, chiusa a fine sonda
    (logout della SOLA sessione di questa sonda);
  * betting.list_market_book(market_ids=[MATCH_ODDS], price_projection EX_BEST_OFFERS) -> lettura;
  * in_play_service.get_scores(event_ids=[...]) -> lettura (endpoint IPS).
Nessun ordine, nessun metodo di scrittura. Per N partite calcio IN GIOCO del feed x K istanti (ogni S s):
lettura della riga `safe_strategy_scan` (GET PostgREST) e SUBITO dopo libro+IPS; confronto best back/lay
per selezione, minuto e punteggio; eta' dichiarata della riga (updated_at, odds_ts_ms) vs orologio.
Uso: sonda_libro_a.py <N partite> <K istanti> <S secondi>
"""
import json, os, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.getcwd())
import betfairlightweight.filters as F  # noqa: E402
from Betfair.stream import auth as A  # noqa: E402

W = Path(r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
OUT = W / "AUDIT_2026-09-25" / "e2e_fase2"
env = {}
for line in open(W / ".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
URL, KEY = env["SUPABASE_URL"].rstrip("/"), env["SUPABASE_SERVICE_ROLE_KEY"]


def get(path):
    req = urllib.request.Request(URL + "/rest/v1/" + path, method="GET",
                                 headers={"apikey": KEY, "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def iso_ms(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp() * 1000


N, K, S = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3])
chiamate = []
esiti = []
client = A.build_client(login=True)
chiamate.append({"ts": datetime.now(timezone.utc).isoformat(), "chiamata": "login cert (sessione della sonda)"})
try:
    righe = get("safe_strategy_scan?select=event_id,updated_at,payload&sport=eq.calcio&limit=200")
    inplay = [r for r in righe if (r.get("payload") or {}).get("inplay") is True and (r["payload"].get("mo_market_id"))]
    scelte = [r["event_id"] for r in inplay[:N]]
    for k in range(K):
        for ev in scelte:
            r = get(f"safe_strategy_scan?select=event_id,updated_at,payload&event_id=eq.{ev}&limit=1")
            if not r:
                continue
            r = r[0]
            p = r["payload"]
            t_db = time.time() * 1000
            mid = p["mo_market_id"]
            books = client.betting.list_market_book(
                market_ids=[mid], price_projection=F.price_projection(price_data=["EX_BEST_OFFERS"]), lightweight=True)
            t_bf = time.time() * 1000
            chiamate.append({"ts": datetime.now(timezone.utc).isoformat(), "chiamata": f"listMarketBook {mid}"})
            try:
                ips = client.in_play_service.get_scores(event_ids=[int(ev)], lightweight=True)
            except Exception as e:  # endpoint non ufficiale
                ips = [{"errore": repr(e)[:120]}]
            chiamate.append({"ts": datetime.now(timezone.utc).isoformat(), "chiamata": f"IPS get_scores {ev}"})
            libro = {}
            b0 = books[0] if books else {}
            for rn in b0.get("runners", []):
                ex = rn.get("ex") or {}
                atb = ex.get("availableToBack") or []
                atl = ex.get("availableToLay") or []
                libro[rn["selectionId"]] = {"back": atb[0]["price"] if atb else None, "lay": atl[0]["price"] if atl else None,
                                            "back_size": atb[0]["size"] if atb else None, "lay_size": atl[0]["size"] if atl else None}
            confronto = {}
            ok_tutti = True
            for lato in ("home", "draw", "away"):
                o = (p.get("odds") or {}).get(lato) or {}
                sid = o.get("selection_id")
                bf = libro.get(sid) or {}
                uguale = (o.get("back") == bf.get("back")) and (o.get("lay") == bf.get("lay"))
                ok_tutti &= uguale
                confronto[lato] = {"feed": [o.get("back"), o.get("lay")], "betfair": [bf.get("back"), bf.get("lay")], "uguale": uguale}
            ips0 = ips[0] if isinstance(ips, list) and ips else {}
            sc = (ips0.get("score") or {}) if isinstance(ips0, dict) else {}
            ips_score = None
            try:
                ips_score = f"{sc['home']['score']}-{sc['away']['score']}"
            except Exception:
                pass
            esiti.append({
                "istante": k, "event_id": ev, "evento": p.get("event_name"), "market_id": mid,
                "eta_riga_s": round((t_db - iso_ms(r["updated_at"])) / 1000, 2),
                "eta_prezzo_s": round((t_db - float(p.get("odds_ts_ms") or 0)) / 1000, 2) if p.get("odds_ts_ms") else None,
                "ritardo_lettura_betfair_ms": round(t_bf - t_db),
                "mercato_betfair": {"status": b0.get("status"), "inplay": b0.get("inplay"), "betDelay": b0.get("betDelay")},
                "feed_mo_status": p.get("mo_status"), "feed_bet_delay": p.get("bet_delay"),
                "prezzi": confronto, "prezzi_uguali": ok_tutti,
                "punteggio": {"feed": f"{p.get('score_home')}-{p.get('score_away')}", "ips": ips_score,
                              "minuto_feed": p.get("minute"),
                              "ips_timeElapsed": ips0.get("timeElapsed") if isinstance(ips0, dict) else None,
                              "ips_status": ips0.get("matchStatus") if isinstance(ips0, dict) else None},
            })
        if k < K - 1:
            time.sleep(S)
finally:
    try:
        A.safe_logout(client)
        chiamate.append({"ts": datetime.now(timezone.utc).isoformat(), "chiamata": "logout della sessione della sonda"})
    except Exception:
        pass
res = {"quando": datetime.now(timezone.utc).isoformat(), "chiamate_betfair": chiamate, "esiti": esiti,
       "prezzi_uguali": sum(1 for e in esiti if e["prezzi_uguali"]), "su": len(esiti)}
nome = OUT / f"A_libro_{datetime.now(timezone.utc).strftime('%H%M')}Z.json"
nome.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
print(json.dumps({k: res[k] for k in ("quando", "prezzi_uguali", "su")}), nome)
for e in esiti:
    print(e["istante"], e["event_id"], e["evento"], "riga", e["eta_riga_s"], "s prezzo", e["eta_prezzo_s"], "s",
          "uguali" if e["prezzi_uguali"] else json.dumps(e["prezzi"]), "| punteggio", e["punteggio"])
