import sys, json
from Betfair.stream.tennis_live import tennis_runner as TR
from Betfair.stream.tennis_live.tools import replay_bot as RB
righe = []
_orig = TR._instantiate_bot
def _spia(bot, ctrl, market_id, catalogo, sink, *a, **kw):
    def sink2(kind, payload):
        p = dict(payload or {})
        chiavi = ("side","price","size","reason","motivo","step","note","state","status","bet_id","order_id","ms","esito","stato","target_price","park_price")
        righe.append((str(kind), json.dumps({k: p.get(k) for k in chiavi if k in p}, sort_keys=True, default=str)[:170]))
        return sink(kind, payload)
    return _orig(bot, ctrl, market_id, catalogo, sink2, *a, **kw)
TR._instantiate_bot = _spia
r = RB.certifica_scenario("35790089", data_dir=sys.argv[1], scenario="gate-aperto", bot="tennis_flb")
print("azioni nel referto:", r.azioni, "| attivita' catturate:", len(righe))
for i, (k, s) in enumerate(righe, 1):
    print(f"{i:3d} {k:28s} {s}")
