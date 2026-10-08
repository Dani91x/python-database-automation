"""Sonda in sola lettura (DOPO): cosa vede verdetto_posizione quando ci sono ordini non di Mike."""
import sys, json, atexit
import Betfair.mike.service as M
uscita = sys.argv.pop(1)
casi = []
CONTO = M._CONTO
sep_orig = CONTO.separa_altrui
def sep(sulla_sel, **kw):
    r = sep_orig(sulla_sel, **kw)
    if (r.get("altrui") or r.get("altri_bot") or r.get("ignoti")) and len(casi) < 4:
        casi.append({"tipo": "separa", "altrui": r.get("altrui"), "altri_bot": r.get("altri_bot"),
                     "ignoti": r.get("ignoti"), "righe": sulla_sel})
    return r
CONTO.separa_altrui = sep
vp_orig = M._EO.verdetto_posizione
def vp(**kw):
    r = vp_orig(**kw)
    if kw.get("righe_altrui") and len(casi) < 8:
        casi.append({"tipo": "verdetto", "kw": {k: v for k, v in kw.items()}, "esito": r})
    return r
M._EO.verdetto_posizione = vp
atexit.register(lambda: json.dump(casi, open(uscita, "w"), indent=1, default=str))
from Betfair.stream.backtest import certifica
certifica.main(sys.argv[1:])
