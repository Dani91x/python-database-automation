"""Sonda (sola lettura): il verdetto dello scanner sul flusso di UN mercato in
una finestra di tempo di mercato, con l'ultimo book e le conferme. Uso:
    python3 sonda_flusso_ht.py <evento> <scenario> <market_id> <HH:MM:SS da> <HH:MM:SS a>
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.getcwd())
from Betfair.omega.tools import replay_registrazioni as R  # noqa: E402
from Betfair.safe_strategy import service as SV  # noqa: E402
from Betfair.stream.backtest import certifica as C  # noqa: E402

ev, sc, mid, da, a = sys.argv[1:6]
vero = SV.Scanner.flusso_mercato
vero_cs = SV.Scanner._apply_cs_book
righe = []


def hhmmss(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def fm(self, m, soglia, adesso=None):
    out = vero(self, m, soglia, adesso)
    if str(m) == mid:
        t = self._ora()
        if da <= hhmmss(t)[:8] <= a:
            righe.append(("FLUSSO", hhmmss(t), out, self._flusso_ultimo(mid),
                          self.flusso_conferma.get(mid), soglia))
    return out


def cs(self, meta, book, dallo_stream=False):
    if str(meta.get("market_id")) == mid:
        t = self._ora()
        if da <= hhmmss(t)[:8] <= a:
            n = sum(1 for r in (getattr(book, "runners", None) or [])
                    if (getattr(getattr(r, "ex", None), "available_to_back", None) or
                        getattr(getattr(r, "ex", None), "available_to_lay", None)))
            righe.append(("BOOK", hhmmss(t), getattr(book, "status", None), "runner con prezzi", n))
    return vero_cs(self, meta, book, dallo_stream)


SV.Scanner.flusso_mercato = fm
SV.Scanner._apply_cs_book = cs
if len(sys.argv) > 6:
    R.FINESTRE_DI_PRODUZIONE = sys.argv[6] == "1"
with C._freni_da_banco():
    ref = R.certifica_scenario(ev, data_dir=os.path.abspath(os.environ.get("DATI", "_live_raw")),
                               scenario=sc)
print("decisioni", ref.decisioni, "azioni", ref.azioni)
prec = None
for r in righe:
    chiave = (r[0], r[2]) if r[0] == "FLUSSO" else (r[0], r[2], r[4])
    if chiave != prec:
        print(r)
        prec = chiave
