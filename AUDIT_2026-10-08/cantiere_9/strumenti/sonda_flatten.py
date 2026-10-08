"""Sonda (solo lettura) del flatten dello scalper in una finestra oraria.

Uso, dalla radice del repo:
  python3 AUDIT_2026-10-08/cantiere_9/strumenti/sonda_flatten.py <scenario> <sel> \
      <dalle HH:MM:SS> <alle HH:MM:SS> <out.txt> [evento]
Avvolge (chiamando sempre il vero) `ScalperStrategy._drive_flatten` e
`process_market_book` e scrive, per ogni book della selezione nella finestra:
stato dello slot, posizione abbinata, tentativi, pausa anti-churn, freno della
taglia, ordini vivi o in volo. Il replay e' quello vero (`certifica_scenario`).
"""
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")
from Betfair.stream.scalper import scalper_bot as SB  # noqa: E402
from Betfair.stream.scalper.tools import replay_registrazioni as RR  # noqa: E402

scenario, sel, dalle, alle, out = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
EV = sys.argv[6] if len(sys.argv) > 6 else "35797769"
righe = []


def _t(ms):
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3]


vero_drive = SB.ScalperStrategy._drive_flatten
vero_pmb = SB.ScalperStrategy.process_market_book


def _drive(self, market, slot, best_back, best_lay, now=None):
    t = _t(now) if now else "-"
    if dalle <= t[:8] <= alle and any(
            getattr(o, "selection_id", None) == sel
            for o in (slot.entry, slot.entry_back, slot.entry_lay, slot.close,
                      *slot.flatten_orders) if o is not None):
        nw, nl = self._net_position(slot)
        vivi = [(o.side, o.order_type.size, o.order_type.price, getattr(o.status, "value", o.status))
                for o in slot.flatten_orders if self._vivo_o_in_volo(o)]
        righe.append("%s DRIVE stato=%s nw=%.3f nl=%.3f tries=%d t_last_flat=%s taglia_fino=%s "
                     "submins=%d scavalchi=%d bb=%s bl=%s vivi=%s" % (
                         t, slot.status, nw, nl, slot.flat_tries,
                         _t(slot.t_last_flat) if slot.t_last_flat else None,
                         _t(slot.taglia_ferma_fino_ms) if slot.taglia_ferma_fino_ms else None,
                         len(slot.submins), slot.scavalchi, best_back, best_lay, vivi))
    return vero_drive(self, market, slot, best_back, best_lay, now=now)


def _pmb(self, market, market_book):
    ms = int(getattr(market_book, "publish_time_epoch", 0) or 0)
    t = _t(ms)
    if dalle <= t[:8] <= alle:
        for r in market_book.runners:
            if r.selection_id == sel:
                slot = self._slots.get((market.market_id, sel))
                righe.append("%s BOOK %s stato=%s atb=%s atl=%s" % (
                    t, market.market_id, getattr(slot, "status", None),
                    [(x["price"], x["size"]) for x in (r.ex.available_to_back or [])[:2]],
                    [(x["price"], x["size"]) for x in (r.ex.available_to_lay or [])[:2]]))
    return vero_pmb(self, market, market_book)


SB.ScalperStrategy._drive_flatten = _drive
SB.ScalperStrategy.process_market_book = _pmb

from Betfair.stream.backtest import certifica as CF  # noqa: E402
from Betfair.stream.backtest import minimi_banco as MB  # noqa: E402

MB.REGISTRO.azzera()
with CF._freni_da_banco():
    ref = RR.certifica_scenario(EV, data_dir="_live_raw", scenario=scenario, ogni_ms=0)
open(out, "w", encoding="utf-8").write("\n".join(righe) + "\n")
print("scritto", out, len(righe))
