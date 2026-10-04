"""Misura (sola lettura): dove lo scalper tennis arrotonda una size al multiplo di 0,50
PIU' VICINO (`_place`, ramo `size_step`) e di quanto, scenario per scenario."""
import collections
import os

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
from Betfair.stream.backtest import certifica as CF  # noqa: E402
from Betfair.stream.tennis_scalper import tennis_scalper_bot as TSB  # noqa: E402
from Betfair.stream.tennis_live.tools import replay_bot as RB  # noqa: E402

for k, v in dict(CF.AMBIENTE_DEL_BANCO).items():
    os.environ[k] = str(v)
vero = TSB.TennisScalperStrategy._place
REG = []


def spia(self, market, sel, side, price, size, floor_min=True, slot=None):
    s0 = round(float(size), 2)
    if floor_min and s0 < TSB.MIN_STAKE:
        s0 = TSB.MIN_STAKE
    applica = self.size_step > 0 and (str(side).upper() == "BACK" or floor_min)
    via_esatta = (not floor_min and self.exact_exits and not self.dry_run and slot is not None
                  and not self._size_direct_ok(side, s0))
    if applica and not via_esatta:
        s1 = round(round(s0 / self.size_step) * self.size_step, 2)
        if abs(s1 - s0) > 1e-9:
            REG.append((str(side).upper(), "ingresso" if floor_min else "uscita", s0, s1))
    return vero(self, market, sel, side, price, size, floor_min=floor_min, slot=slot)


TSB.TennisScalperStrategy._place = spia
for sc in ("live", "gate-aperto", "uscite-manuali", "uscite-manuali-firmate",
           "soldi-veri", "soldi-veri-paper", "base", "parziali"):
    REG.clear()
    RB.certifica_scenario("35794049", data_dir="C:/Users/Admin/Desktop/tennis_rec/20260707",
                          scenario=sc, bot="tennis_scalper")
    su = [r for r in REG if r[3] > r[2]]
    giu = [r for r in REG if r[3] < r[2]]
    print("%-24s arrotondati %d | per ECCESSO %d (max +%.2f) %s | per difetto %d"
          % (sc, len(REG), len(su), max([r[3] - r[2] for r in su] or [0.0]),
             collections.Counter((r[0], r[1], r[2], r[3]) for r in su).most_common(6),
             len(giu)))
