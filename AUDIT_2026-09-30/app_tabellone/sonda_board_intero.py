# Sonda SOLA LETTURA (30/09): il giro INTERO del board (catalogo + feed +
# fallback REST su tutti i mercati, 2 chiamate list_market_book), come nel
# runner. Nessuna scrittura, nessun logout.
import sys, os, json
sys.path.insert(0, os.getcwd())
from Betfair.stream.auth import build_client
from Betfair.stream import board_worker as bw

c = build_client(login=True)
bw._refresh_catalogue(c, "1")
rows = bw._collect_rows(c)
vuote = [r for r in rows if all(s["back"] is None and s["lay"] is None for s in r["selections"])]
print("righe", len(rows), "senza quote", len(vuote))
for r in vuote[:3]:
    print(json.dumps(r, default=str)[:600])
# stesso giro, a pezzi: primo e secondo blocco separati
metas = {m["market_id"]: m for m in bw._STATE["markets"]}
ids = list(metas)
for a, b in ((0, 25), (25, 50)):
    part = {k: metas[k] for k in ids[a:b]}
    rr = bw._poll_books_rest(c, part)
    nv = sum(1 for r in rr.values() if all(s["back"] is None for s in r["selections"]))
    print("blocco", a, b, "mercati", len(part), "righe", len(rr), "senza back", nv)
