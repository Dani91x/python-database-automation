"""Profilo cProfile di UN replay del banco, nello stesso processo, con la stessa
strada di `certifica` (`_lavora_cronometrato`, freni del banco, livello WARNING).
Uso (dalla radice del worktree):
  python AUDIT_2026-10-02/profila_scenario.py BOT EVENTO SCENARIO DATA_DIR OUT.prof
"""
import cProfile
import logging
import pstats
import sys
import time

from Betfair.stream.backtest import certifica as C

bot, ev, sc, data_dir, out = sys.argv[1:6]
logging.basicConfig(level=logging.WARNING)
compito = (bot, ev, data_dir, sc, 0, 0, None)
pr = cProfile.Profile()
t0 = time.perf_counter()
pr.enable()
r, _mem, sec = C._lavora_cronometrato(compito)
pr.disable()
print(f"scenario {sc}: tick={r.tick} decisioni={r.decisioni} azioni={r.azioni} "
      f"violazioni={len(r.violazioni)} secondi={sec:.1f} (con profilo)")
pr.dump_stats(out)
st = pstats.Stats(out)
st.sort_stats("tottime").print_stats(35)
st.sort_stats("cumulative").print_stats(60)
