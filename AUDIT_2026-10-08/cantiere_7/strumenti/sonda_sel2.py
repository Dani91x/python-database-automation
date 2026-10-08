"""Sonda (sola lettura): cosa vede e decide _v3_select fra due istanti
(fonte dello snapshot, motivo, prezzo del '3 - 3'). Uso: python3 sonda_sel.py <ev> <sc> <da> <a>"""
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
vero = S._v3_select
def sel(**k):
    out = vero(**k)
    h = datetime.fromtimestamp(banco["b"].ora, tz=timezone.utc).strftime("%H:%M:%S")
    if da <= h <= a:
        snap = k.get("snapshot")
        r13 = next((r for r in (getattr(snap, "runners", ()) or ()) if int(getattr(r, "selection_id", -1)) == int(os.environ.get("SEL","13"))), None)
        print(h, "half", k.get("half"), "payload_cs", bool((k.get("payload") or {}).get("cs")),
              "sel:", getattr(r13, "lay_price", None), getattr(r13, "lay_size", None),
              "esito", (out[0].name if out[0] else None), out[2], flush=True)
    return out
S._v3_select = sel
with C._freni_da_banco():
    ref = R.certifica_scenario(ev, data_dir="/home/user/python-database-automation/.claude/worktrees/agent-adb756da0c06e837d/_live_raw", scenario=sc)
print("decisioni", ref.decisioni, "azioni", ref.azioni)
