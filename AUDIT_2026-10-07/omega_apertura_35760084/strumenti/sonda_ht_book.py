"""Sonda: quali book dell'Half Time Score arrivano allo scanner del banco
(stato e se hanno prezzi), e quali il banco scarta prima (applica_book False).
uso (dalla radice dell'albero): python3 sonda_ht_book.py <evento> <scenario> <market_id HT>"""
import os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.getcwd())
from Betfair.safe_strategy import service as SV
from Betfair.stream.backtest import banco_comune as BC

HT = sys.argv[3]
visti = []
orig_cs = SV.Scanner._apply_cs_book
orig_ab = BC.ScannerReplay.applica_book


def cs(self, meta, book, dallo_stream=False):
    if str(meta.get("market_id")) == HT:
        sel = [r for r in (getattr(book, "runners", None) or [])]
        visti.append(("APPLICATO", datetime.fromtimestamp(self._ora_mono(), tz=timezone.utc).strftime("%H:%M:%S")
                      if hasattr(self, "_ora_mono") else "?", getattr(book, "status", None), len(sel)))
    return orig_cs(self, meta, book, dallo_stream)


def ab(self, market_book):
    ok = orig_ab(self, market_book)
    if str(getattr(market_book, "market_id", "")) == HT and not ok:
        visti.append(("SCARTATO", datetime.fromtimestamp(self._ora_s, tz=timezone.utc).strftime("%H:%M:%S"),
                      getattr(market_book, "status", None),
                      "in market_meta" if HT in self.scan.market_meta else "NON in market_meta"))
    return ok


SV.Scanner._apply_cs_book = cs
BC.ScannerReplay.applica_book = ab
from Betfair.stream.backtest import certifica as C  # noqa: E402
C.main(["omega", sys.argv[1], "--data-dir", "/home/user/python-database-automation/_live_raw",
        "--scenari", sys.argv[2], "--worker", "1"])
print("\n===== SONDA HT =====")
ultimo = None
for v in visti:
    chiave = (v[0], v[2], v[3] if v[0] == "SCARTATO" else (v[3] > 0))
    if chiave != ultimo:
        print(v)
        ultimo = chiave
print("totale eventi:", len(visti), "ultimo:", visti[-1] if visti else None)
