# Sonda SOLA LETTURA (30/09): quali righe del board vengono dal FEED dello
# scanner (safe_strategy_scan, una SELECT) e con quali quote. Una sessione
# Betfair per il catalogo (1 chiamata), nessuna scrittura.
import sys, os, json
sys.path.insert(0, os.getcwd())
from Betfair.stream.auth import build_client
from Betfair.stream import board_worker as bw
from Betfair.stream.scores.scan_feed import fresh_payload, shared_cache

c = build_client(login=True)
bw._refresh_catalogue(c, "1")
metas = {m["market_id"]: m for m in bw._STATE["markets"]}
by_event = {str(m["event_id"]): m for m in metas.values()}
cache = shared_cache()
scan_rows = cache.rows_for(list(by_event.keys()))
age = cache.scanner_age_sec() if scan_rows else None
print("catalogo", len(metas), "righe feed", len(scan_rows), "eta scanner", age)
n_feed = n_vuote = 0
esempio = None
for eid, row in scan_rows.items():
    p = fresh_payload(row, bw._FEED_MAX_AGE_SEC, scanner_age_sec=age)
    if p is None:
        continue
    built = bw.row_from_scan_payload(by_event[eid], p)
    if built is None:
        continue
    n_feed += 1
    if all(s["back"] is None and s["lay"] is None for s in built["selections"]):
        n_vuote += 1
        if esempio is None:
            esempio = (eid, {k: p.get(k) for k in ("mo_market_id", "mo_status", "inplay",
                       "mo_total_matched", "odds", "odds_ts_ms", "odds_vuote_ms")})
print("righe board DAL FEED:", n_feed, "di cui SENZA quote:", n_vuote)
print("esempio payload:", json.dumps(esempio, default=str)[:1200])
