# Sonda SOLA LETTURA (30/09): il giro del board come nel RUNNER, cioe' con
# flumine importato nel processo (flumine/__init__.py sostituisce
# bettingresources.RunnerBookEX con la classe "pigra" che lascia i livelli
# come dizionari). Argomento "senza" = stesso giro senza flumine (controllo).
import sys, os
sys.path.insert(0, os.getcwd())
if "senza" not in sys.argv:
    import flumine  # noqa: F401 - e' LA differenza col processo del runner
from betfairlightweight.resources import bettingresources
from Betfair.stream.auth import build_client
from Betfair.stream import board_worker as bw

print("RunnerBookEX in uso:", bettingresources.RunnerBookEX.__module__)
c = build_client(login=True)
bw._refresh_catalogue(c, "1")
metas = {m["market_id"]: m for m in bw._STATE["markets"]}
rows = bw._poll_books_rest(c, metas)
vuote = [r for r in rows.values() if all(s["back"] is None and s["lay"] is None for s in r["selections"])]
print("righe REST", len(rows), "senza quote", len(vuote))
b = c.betting.list_market_book(market_ids=list(metas)[:1],
                               price_projection={"priceData": ["EX_BEST_OFFERS"]})[0]
print("forma del livello:", type(b.runners[0].ex).__name__, repr(b.runners[0].ex.available_to_back[:1]))
