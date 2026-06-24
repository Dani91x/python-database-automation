"""
betfair_full_odds.py — fetch ADDITIVO delle quote Betfair COMPLETE (tutti i mercati,
back + lay) per le partite del giorno, in tabella betfair_market_odds.

NON e' il report .bat: NON tocca Google Sheets ne' il Money Management. Fa solo:
login Betfair -> per ogni evento (matchato a una nostra fixture) scarica TUTTI i
mercati + back/lay (EX_BEST_OFFERS, 3 livelli) -> upsert in betfair_market_odds.

Uso:
  python betfair_full_odds.py --filter switzerland   # solo eventi che contengono "switzerland" (test)
  python betfair_full_odds.py                         # tutti gli eventi calcio del giorno matchabili
"""
import sys, re, time, argparse, datetime as dt, unicodedata
sys.stdout.reconfigure(encoding="utf-8")

# --- RISPETTO LIMITI BETFAIR (tassativo: niente ban) ---
# listMarketBook: peso max 200/chiamata, EX_BEST_OFFERS = 5/mercato -> batch 20 = peso 100 (margine 2x).
# Delay 0.6s tra OGNI chiamata (best-practice anti-throttling). Stop immediato sui limiti.
BATCH = 20            # mercati per listMarketBook (peso 100 < 200)
REQ_DELAY = 0.6       # secondi tra chiamate
EVENT_DELAY = 0.4     # secondi extra tra eventi
LIMIT_MARKERS = ("TOO_MANY_REQUESTS", "TOO_MUCH_DATA")


class BetfairLimitHit(RuntimeError):
    pass


def _is_limit(ex) -> bool:
    return any(m in str(ex) for m in LIMIT_MARKERS)


def norm(s: str) -> frozenset:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    drop = {"fc", "cf", "sc", "ac", "as", "if", "sk", "fk", "club", "the", "u23", "u21", "women", "w"}
    return frozenset(t for t in s.split() if t and t not in drop)


def best_levels(arr, n=3):
    return [{"price": x.get("price"), "size": x.get("size")} for x in (arr or [])[:n]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--filter", default="", help="processa solo eventi il cui nome contiene questa stringa")
    args = ap.parse_args()

    from db_client import get_supabase_client
    from Betfair.client import BetfairClient
    sb = get_supabase_client()
    today = dt.date.today().isoformat()
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()

    # mappa fixture del giorno: (norm_home, norm_away) -> (fixture_id, home, away)
    fx = sb.table("fixture_predictions").select("fixture_id,home_team_name,away_team_name") \
        .gte("fixture_date", today + "T00:00:00").lt("fixture_date", tomorrow + "T00:00:00").execute().data
    fmap = {(norm(r["home_team_name"]), norm(r["away_team_name"])): r for r in fx}

    c = BetfairClient(); c.login_cert()
    evs = c.list_events(["1"], days_ahead=2) or []
    if args.filter:
        evs = [e for e in evs if args.filter.lower() in e["event"]["name"].lower()]
    print(f"Eventi Betfair da processare: {len(evs)}")

    written_fixtures = 0
    for e in evs:
        ev = e["event"]; name = ev["name"]; eid = ev["id"]
        if " v " not in name:
            continue
        h, a = name.split(" v ", 1)
        nh, na = norm(h), norm(a)
        match = fmap.get((nh, na))
        if not match:  # fallback: overlap forte dei token
            for (kh, ka), r in fmap.items():
                if len(nh & kh) >= 1 and len(na & ka) >= 1 and (nh & kh) and (na & ka):
                    match = r; break
        if not match:
            print(f"  [skip] '{name}': nessuna fixture corrispondente")
            continue
        fid = match["fixture_id"]

        try:
            cats = c.betting_rpc("SportsAPING/v1.0/listMarketCatalogue",
                                 {"filter": {"eventIds": [eid]}, "maxResults": 1000,
                                  "marketProjection": ["RUNNER_DESCRIPTION"]}) or []
        except Exception as ex:
            if _is_limit(ex):
                raise BetfairLimitHit(str(ex))
            raise
        time.sleep(REQ_DELAY)
        meta = {}
        mids = []
        for m in cats:
            mid = m["marketId"]; mids.append(mid)
            meta[mid] = {"name": m["marketName"],
                         "runners": {r["selectionId"]: (r.get("runnerName", "?"), r.get("sortPriority"))
                                     for r in m.get("runners", [])}}
        books = []
        for i in range(0, len(mids), BATCH):  # peso = BATCH*5 = 100 < 200
            try:
                books += c.list_market_book(mids[i:i + BATCH]) or []
            except Exception as ex:
                if _is_limit(ex):
                    raise BetfairLimitHit(str(ex))
                raise
            time.sleep(REQ_DELAY)

        rows = []
        for b in books:
            mm = meta.get(b["marketId"])
            if not mm:
                continue
            for r in b.get("runners", []):
                rn, sp = mm["runners"].get(r["selectionId"], ("?", None))
                ex = r.get("ex", {})
                rows.append({
                    "fixture_id": fid, "market_name": mm["name"], "selection": rn,
                    "sort_priority": sp, "market_id": b["marketId"], "run_date": today,
                    "back": best_levels(ex.get("availableToBack")),
                    "lay": best_levels(ex.get("availableToLay")),
                })
        if not rows:
            print(f"  [skip] '{name}': nessuna quota")
            continue
        # sostituisci le righe del fixture (idempotente per il giorno)
        sb.table("betfair_market_odds").delete().eq("fixture_id", fid).execute()
        for i in range(0, len(rows), 500):
            sb.table("betfair_market_odds").insert(rows[i:i + 500]).execute()
        written_fixtures += 1
        print(f"  [ok] {name} -> fixture {fid}: {len(rows)} righe ({len(set(x['market_name'] for x in rows))} mercati)")
        time.sleep(EVENT_DELAY)

    print(f"\nFatto. Fixture scritte: {written_fixtures}")


if __name__ == "__main__":
    try:
        main()
    except BetfairLimitHit as ex:
        # mai retry-storm sui limiti: stop pulito (le fixture gia' scritte restano).
        print(f"\n[STOP LIMITE BETFAIR] interrotto per sicurezza (niente ban): {str(ex)[:140]}")
