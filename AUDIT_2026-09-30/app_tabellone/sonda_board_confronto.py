# Sonda SOLA LETTURA (30/09): nello STESSO istante confronta, per le righe del
# board del runner (canale locale, lettore) rimaste senza quote:
#   1) la riga del feed scanner su DB (safe_strategy_scan, SELECT);
#   2) list_market_book con la stessa chiamata del board_worker.
import asyncio, json, sys, os
sys.path.insert(0, os.getcwd())
import websockets
from betfairlightweight import filters
from Betfair.stream.auth import build_client
from Betfair.stream.scores.scan_feed import _fetch_rows


async def leggi_board():
    async with websockets.connect("ws://127.0.0.1:47331/lettore/board", max_size=None) as ws:
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), 30))
            if msg.get("t") == "board":
                return msg["d"]["rows"]

rows = asyncio.run(leggi_board())
vuote = [r for r in rows if all(s.get("back") is None and s.get("lay") is None
                                for s in r.get("selections") or [])]
print("board runner: righe", len(rows), "senza quote", len(vuote))
eids = [str(r["event_id"]) for r in vuote]
db = {str(r.get("event_id")): r for r in _fetch_rows(eids)}
print("di queste, con riga su safe_strategy_scan:", len(db))
for r in vuote[:3]:
    d = db.get(str(r["event_id"]))
    p = (d or {}).get("payload") or {}
    print("EV", r["event_id"], r["event_name"], "| riga DB:", bool(d), "updated_at", (d or {}).get("updated_at"),
          "| mo_market_id", p.get("mo_market_id"), "odds", json.dumps(p.get("odds"))[:300],
          "odds_ts_ms", p.get("odds_ts_ms"), "odds_vuote_ms", p.get("odds_vuote_ms"))
c = build_client(login=True)
ids = [r["market_id"] for r in vuote[:5]]
books = c.betting.list_market_book(market_ids=ids, price_projection=filters.price_projection(price_data=["EX_BEST_OFFERS"]))
for b in books:
    print("REST", b.market_id, b.status, [(r.selection_id, r.ex.available_to_back[0].price if r.ex.available_to_back else None) for r in b.runners])
