# Sonda SOLA LETTURA (30/09): stessa chiamata del board_worker su pochi mercati
# di oggi. Una sessione, poche chiamate, nessun logout, nessuna scrittura.
import sys, os, json
sys.path.insert(0, os.getcwd())
from betfairlightweight import filters
from Betfair.stream.auth import build_client
from Betfair.stream import board_worker as bw

c = build_client(login=True)
bw._refresh_catalogue(c, "1")
mk = bw._STATE["markets"]
print("catalogo:", len(mk))
ids = [m["market_id"] for m in mk][-3:]
print("ids", ids)
pp = filters.price_projection(price_data=["EX_BEST_OFFERS"])
print("price_projection serializzato:", pp)
books = c.betting.list_market_book(market_ids=ids, price_projection=pp)
for b in books:
    print("MB", type(b).__name__, b.market_id, b.status, b.inplay, b.total_matched)
    for r in b.runners:
        ex = r.ex
        print("   runner", r.selection_id, "ex type", type(ex).__name__,
              "atb", [(p.price, p.size) for p in (ex.available_to_back or [])][:1] if ex else None,
              "atl", [(p.price, p.size) for p in (ex.available_to_lay or [])][:1] if ex else None,
              "ltp", r.last_price_traded)
metas = {m["market_id"]: m for m in mk if m["market_id"] in ids}
rows = bw._poll_books_rest(c, metas)
print(json.dumps(list(rows.values())[:1], default=str, indent=1))
raw = c.betting.list_market_book(market_ids=ids[:1], price_projection=pp, lightweight=True)
print("RAW", json.dumps(raw, default=str)[:1500])
