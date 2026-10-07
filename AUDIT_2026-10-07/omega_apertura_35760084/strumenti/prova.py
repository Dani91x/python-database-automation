"""Prova un commit: estrae Betfair/ (git archive dal worktree del delegato) e lancia il replay."""
import os, re, subprocess, sys, time
W = "/home/user/python-database-automation/.claude/worktrees/agent-aadcd5199a17dae8b"
SP = "/tmp/claude-0/-home-user-python-database-automation/b81252ef-134e-5437-9162-d213fe1a02bc/scratchpad"
c = sys.argv[1]
evento = sys.argv[2] if len(sys.argv) > 2 else "35760084"
scenari = sys.argv[3] if len(sys.argv) > 3 else "apertura"
dest = os.path.join(SP, "ar", c)
if not os.path.isdir(os.path.join(dest, "Betfair")):
    os.makedirs(dest, exist_ok=True)
    arch = subprocess.run(["git", "archive", c, "Betfair", "tactical_engine", "value_engine", "market_intelligence", ":(glob)*.py", ":(glob)*.json"], cwd=W, capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", dest], input=arch, check=True)
out = os.path.join(SP, f"r_{c}_{evento}_{scenari}.txt")
t0 = time.time()
with open(out, "w") as fh:
    subprocess.run(["timeout", "900", "python3", "-m", "Betfair.stream.backtest.certifica", "omega", evento,
                    "--data-dir", "/home/user/python-database-automation/_live_raw",
                    "--scenari", scenari, "--worker", "1"], cwd=dest, stdout=fh, stderr=subprocess.STDOUT)
testo = open(out).read()
righe = [r for r in testo.splitlines() if re.match(r"^(OK|KO|N/A|NE)\s", r)]
print(c, f"{time.time()-t0:.0f}s")
for r in righe:
    print("  ", r)
if not righe:
    print(testo[-1500:])
