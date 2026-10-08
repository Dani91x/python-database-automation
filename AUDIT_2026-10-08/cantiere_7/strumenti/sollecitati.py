"""Sollecitazioni dei controlli PER SCENARIO (il referto stampa solo il totale).
Uso, dalla radice dell'albero: python3 sollecitati.py <evento> <sc1,sc2,...> <C1,C2,...>"""
import os
import sys

sys.path.insert(0, os.getcwd())
from Betfair.stream.backtest import certifica as C  # noqa: E402

ev, scenari, controlli = sys.argv[1], sys.argv[2].split(","), sys.argv[3].split(",")
dati = "/home/user/python-database-automation/.claude/worktrees/agent-adb756da0c06e837d/_live_raw"
for sc in scenari:
    r, _mem = C._lavora(("omega", ev, dati, sc, 0, 0))
    print(sc, r.decisioni, r.azioni, {c: int(r.sollecitati.get(c) or 0) for c in controlli},
          flush=True)
