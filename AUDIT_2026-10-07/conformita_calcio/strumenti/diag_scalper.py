"""DIAGNOSTICA in sola lettura: scenario dello scalper calcio dal suo adattatore del
banco, con `_on_cycle_closed` e `_emit` VERI avvolti per stampare ogni ciclo chiuso
(fase, locked, tipo) e gli eventi (missione, target, loss cap, residuo).
uso: diag_scalper.py <evento> <scenario>"""
import sys
from datetime import datetime, timezone

ev, scen = sys.argv[1], sys.argv[2]
sys.argv = sys.argv[:1]
from Betfair.stream.scalper import scalper_bot as SB
from Betfair.stream.scalper import sniper_bot as SN
from Betfair.stream.scalper.tools import replay_registrazioni as RR

def t(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()[11:19] if ms else "?"

_occ = SB.ScalperStrategy._on_cycle_closed
def occ(self, slot, locked, kind="cycle", now=None):
    print("CICLO", t(now), "fase", "inplay" if slot.inplay_cycle else "prematch", "locked", round(locked, 4), kind,
          "greens", self.stats.get("greens_prematch"), self.stats.get("greens_inplay"))
    return _occ(self, slot, locked, kind, now)
SB.ScalperStrategy._on_cycle_closed = occ

INTERESSANTI = {"mission", "loss_cap", "target_raggiunto", "residuo_ricordato", "force_flat",
                "sniper_fire", "sniper_green", "sniper_timeout", "sniper_flat", "sniper_stop",
                "sniper_mission_done", "sniper_lines", "flatten", "ko_flat"}
_em = SB.ScalperStrategy._emit
def em(self, kind, **p):
    if kind in INTERESSANTI or "flat" in kind:
        print("EVENTO", kind, {k: p[k] for k in list(p)[:8]})
    return _em(self, kind, **p)
SB.ScalperStrategy._emit = em
_em2 = SN.SniperStrategy._emit
def em2(self, kind, **p):
    print("SNIPER", kind, {k: p[k] for k in list(p)[:10]})
    return _em2(self, kind, **p)
SN.SniperStrategy._emit = em2

from Betfair.stream.backtest import certifica as C
C.main(["scalper_calcio", ev, "--data-dir", "/home/user/python-database-automation/_live_raw", "--scenari", scen, "--worker", "1"])
