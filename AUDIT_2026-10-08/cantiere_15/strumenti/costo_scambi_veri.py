"""Quanto costa `banco_comune.scambi_veri` in un replay vero (chiamate e secondi CPU)
e quanto costa `_mercato_che_attraversa` in tutto. Sola misura: avvolge le due
funzioni con un cronometro di processo (time.process_time).

Uso: python3 costo_scambi_veri.py <scenario> [evento]
"""
import sys
import time

sys.path.insert(0, ".")
from Betfair.stream.backtest import banco_comune as B  # noqa: E402
from Betfair.stream.backtest import certifica as CF  # noqa: E402
from Betfair.stream.backtest import minimi_banco as MB  # noqa: E402
from Betfair.stream.scalper.tools import replay_registrazioni as RR  # noqa: E402

scenario = sys.argv[1]
ev = sys.argv[2] if len(sys.argv) > 2 else "35797769"
conta = {"sv_n": 0, "sv_s": 0.0, "mca_n": 0, "mca_s": 0.0}
orig_sv = B.scambi_veri
orig_mca = B.MotoreReplay._mercato_che_attraversa


def _sv(*a, **k):
    t = time.process_time()
    try:
        return orig_sv(*a, **k)
    finally:
        conta["sv_n"] += 1
        conta["sv_s"] += time.process_time() - t


def _mca(self, *a, **k):
    t = time.process_time()
    try:
        return orig_mca(self, *a, **k)
    finally:
        conta["mca_n"] += 1
        conta["mca_s"] += time.process_time() - t


B.scambi_veri = _sv
B.MotoreReplay._mercato_che_attraversa = _mca
MB.REGISTRO.azzera()
t0 = time.process_time()
with CF._freni_da_banco():
    ref = RR.certifica_scenario(ev, data_dir="_live_raw", scenario=scenario, ogni_ms=0)
tot = time.process_time() - t0
print("scenario %s: CPU totale %.1f s; _mercato_che_attraversa %d chiamate %.2f s; "
      "scambi_veri %d chiamate %.3f s (%.2f%% del replay)"
      % (scenario, tot, conta["mca_n"], conta["mca_s"], conta["sv_n"], conta["sv_s"],
         100.0 * conta["sv_s"] / tot if tot else 0.0))
