"""Quale cache di processo di omega_service passa da `paper` ad `apertura`?
Uso, dalla radice dell'albero (PRIMA): python3 contagio.py <nome_cache|TUTTE|NESSUNA>"""
import os
import sys

sys.path.insert(0, os.getcwd())
from Betfair.omega import omega_service as S  # noqa: E402
from Betfair.stream.backtest import certifica as C  # noqa: E402

dati = "/home/user/python-database-automation/.claude/worktrees/agent-adb756da0c06e837d/_live_raw"
quale = sys.argv[1]
r, _ = C._lavora(("omega", "35760084", dati, "paper", 0, 0))
print("paper", r.decisioni, r.azioni)
nomi = ["_LEG_RETRY", "_LEG_RETRY_DB", "_SKIP_SEEN", "_BLIND_CYCLES", "_MARKET_FIT_CACHE",
        "_LAMBDA_CACHE", "_IDLE_STATS_AT", "_EVENTS_REFRESH_AT", "_REALLY_OVER_CACHE",
        "_DAILY_GOAL_WRITTEN", "_EMPIRICAL_CACHE", "_MINUTE_CACHE"]
for n in nomi:
    print("  dopo paper", n, len(getattr(S, n)))
if quale == "TUTTE":
    for n in nomi:
        getattr(S, n).clear()
elif quale != "NESSUNA":
    getattr(S, quale).clear()
r, _ = C._lavora(("omega", "35760084", dati, "apertura", 0, 0))
print("apertura dopo paper, azzerata:", quale, r.decisioni, r.azioni)
