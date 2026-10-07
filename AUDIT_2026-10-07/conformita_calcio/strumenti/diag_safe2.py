"""DIAGNOSTICA in sola lettura (nessun file del repo toccato): lo scenario `base`
di Safe sulla 35797769 dal suo adattatore del banco, con funzioni VERE avvolte
per stampare decisioni d'uscita, proposte e settlement della riga ESATTO."""
import sys
from datetime import datetime, timezone

sys.argv = sys.argv[:1]
from Betfair.safe_strategy import bot_service as BS
from Betfair.safe_strategy import exits as XE
from Betfair.safe_strategy.tools import replay_registrazioni as RR

ev = "35797769"
DATA = "/home/user/python-database-automation/_live_raw"
visti = {"settle": 0, "batch": []}

_settle = BS.settle_open
def settle_open(**kw):
    n = _settle(**kw)
    try:
        rows = list(kw["db"].open_trades() or [])
    except Exception:
        rows = []
    if rows and visti["settle"] % 300 == 0:
        print("SETTLE giro", kw["now"].isoformat()[11:19], "aperte", [(r.get("id"), r.get("status"), r.get("market_id")) for r in rows], "regolate", n)
    visti["settle"] += 1
    visti["ultimo"] = kw["now"].isoformat()
    return n
BS.settle_open = settle_open

_batch = BS._read_markets_batch
def read_batch(market, trades, now_ts):
    out = _batch(market, trades, now_ts)
    sintesi = {k: (getattr(v, "status", None), getattr(v, "closed", None)) for k, v in (out or {}).items()}
    chiave = (tuple(t.get("market_id") for t in trades), tuple(sorted(sintesi.items())))
    if chiave not in visti["batch"]:
        visti["batch"].append(chiave)
        pass
    if trades:
        print("READ_MARKETS", datetime.fromtimestamp(now_ts, timezone.utc).isoformat()[11:19], "todo", [t.get("market_id") for t in trades], "->", sintesi)
    return out
BS._read_markets_batch = read_batch

_decide = XE.decide
ult = {}
def decide(trade, payload, meta, now_ts, params):
    d = _decide(trade, payload, meta, now_ts, params)
    k = (trade.get("id"), None if d is None else (d.kind, d.reason))
    tr = (meta or {}).get(XE.TRACK_KEY) or {}
    if ult.get(trade.get("id")) != k[1]:
        ult[trade.get("id")] = k[1]
        print("DECIDE", datetime.fromtimestamp(now_ts, timezone.utc).isoformat()[11:19], "trade", trade.get("id"), trade.get("strategy"),
              "min", tr.get("minute"), "ultimo", tr.get("last_home"), tr.get("last_away"), "ingresso", tr.get("entry_home"), tr.get("entry_away"),
              "lato", tr.get("side"), "->", None if d is None else (d.kind, d.reason, d.not_before_ts))
    return d
XE.decide = decide

_prop = BS._proponi_chiusura
def proponi(**kw):
    r = _prop(**kw)
    d = kw.get("decision")
    if 0: print("PROPOSTA", kw["now"].isoformat()[11:19], "trade", kw["trade"].get("id"), d.kind, d.reason, "->", r)
    return r
BS._proponi_chiusura = proponi

ref = RR.certifica_scenario(ev, data_dir=DATA, scenario="base")
print("ULTIMO GIRO DI SETTLE", visti.get("ultimo"))
print("NOTE:")
for n in getattr(ref, "note", [])[:12]:
    print("  ", str(n)[:300])
