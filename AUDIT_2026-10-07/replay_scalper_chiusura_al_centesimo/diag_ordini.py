"""Diagnostica in sola lettura: ordini dello scalper calcio per i cicli chiusi."""
import sys
from datetime import datetime, timezone
ev, scen = sys.argv[1], sys.argv[2]
sys.argv = sys.argv[:1]
from Betfair.stream.scalper import scalper_bot as SB


def t(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()[11:19] if ms else "?"


def desc(o):
    ot = getattr(o, "order_type", None)
    return "%s chiesto=%s @%s abb=%s pm=%s rem=%s canc=%s laps=%s st=%s" % (
        getattr(o, "side", None), getattr(ot, "size", None), getattr(ot, "price", None),
        getattr(o, "size_matched", None),
        round(float(getattr(o, "average_price_matched", 0) or 0), 3),
        getattr(o, "size_remaining", None), getattr(o, "size_cancelled", None),
        getattr(o, "size_lapsed", None), getattr(getattr(o, "status", None), "value", None))


_now = {"t": 0}
_pmb = SB.ScalperStrategy.process_market_book


def pmb(self, market, mb):
    try:
        _now["t"] = int(mb.publish_time_epoch)
    except Exception:
        pass
    return _pmb(self, market, mb)


SB.ScalperStrategy.process_market_book = pmb
_occ = SB.ScalperStrategy._on_cycle_closed


def occ(self, slot, locked, kind="cycle", now=None):
    print("CICLO", t(now), "locked", round(locked, 4), kind, "nw/nl",
          [round(x, 4) for x in self._net_position(slot)])
    seen = set()
    for o in [slot.entry, slot.entry_back, slot.entry_lay, slot.close, slot.next_entry] + list(slot.flatten_orders):
        if o is None or id(o) in seen:
            continue
        seen.add(id(o))
        print("    ", desc(o))
    return _occ(self, slot, locked, kind, now)


SB.ScalperStrategy._on_cycle_closed = occ
_em = SB.ScalperStrategy._emit
KINDS = ("place", "close_presize", "scratch", "stop", "min_bet_skip", "submin_start",
         "submin_step", "submin_abort", "flatten_residual", "flatten_residual_forced",
         "loss_cap", "cycle", "flatten_done", "rifiuto_taglia", "place_rifiutato",
         "min_bet_adjust", "residuo_ricordato")


def em(self, kind, **p):
    if kind in KINDS:
        print("EV", t(_now["t"]), kind, {k: p[k] for k in list(p)[:8] if k not in ("market_id", "msg")})
    return _em(self, kind, **p)


SB.ScalperStrategy._emit = em
from Betfair.stream.backtest import certifica as C
C.main(["scalper_calcio", ev, "--data-dir", "/home/user/python-database-automation/_live_raw",
        "--scenari", scen, "--worker", "1"])
