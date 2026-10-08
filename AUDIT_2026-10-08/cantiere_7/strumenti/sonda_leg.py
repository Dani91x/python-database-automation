"""Sonda (sola lettura): _leg_market e la condizione prima di _v3_select, fra due istanti.
Uso: python3 sonda_leg.py <ev> <sc> <da> <a>"""
import os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.getcwd())
from Betfair.omega.tools import replay_registrazioni as R
from Betfair.omega import omega_service as S
from Betfair.stream.backtest import certifica as C
ev, sc, da, a = sys.argv[1:5]
banco = {}
vi = R.FeedReplay.__init__
def init(self, b):
    banco["b"] = b; vi(self, b)
R.FeedReplay.__init__ = init
def ora():
    return datetime.fromtimestamp(banco["b"].ora, tz=timezone.utc).strftime("%H:%M:%S")
vl = S._leg_market
visti = {}
def lm(market, evx, mt, payload):
    out = vl(market, evx, mt, payload)
    h = ora()
    if da <= h <= a:
        snap = out[1] if out else None
        k = (out is None, getattr(snap, "closed", None), getattr(snap, "inplay", None), getattr(snap, "status", None),
             bool((payload or {}).get("cs")) if payload is not None else "payload None")
        if visti.get("k") != k:
            print(h, "leg_market None" if out is None else "snap", k, flush=True); visti["k"] = k
    return out
S._leg_market = lm
vs = S._scan_event_legs
def sel(**kw):
    h = ora()
    out = vs(**kw)
    if da <= h <= a and visti.get("s") != (len(kw.get("traded_legs") or ()), out[0]):
        visti["s"] = (len(kw.get("traded_legs") or ()), out[0])
        print(h, "scan_event_legs traded_legs", sorted(kw.get("traded_legs") or ()), "->", out, flush=True)
    return out
S._scan_event_legs = sel
with C._freni_da_banco():
    ref = R.certifica_scenario(ev, data_dir="/home/user/python-database-automation/.claude/worktrees/agent-adb756da0c06e837d/_live_raw", scenario=sc)
print("decisioni", ref.decisioni, "azioni", ref.azioni)
