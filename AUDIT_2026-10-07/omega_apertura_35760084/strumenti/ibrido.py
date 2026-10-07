"""Ibrido: albero del commit BASE con i percorsi indicati presi dal commit SOPRA, poi replay.
uso: ibrido.py NOME BASE SOPRA percorso [percorso ...]"""
import os, re, shutil, subprocess, sys, time
W = "/home/user/python-database-automation/.claude/worktrees/agent-aadcd5199a17dae8b"
SP = "/tmp/claude-0/-home-user-python-database-automation/b81252ef-134e-5437-9162-d213fe1a02bc/scratchpad"
nome, base, sopra, *percorsi = sys.argv[1:]
evento = os.environ.get("EVENTO", "35760084")
scenari = os.environ.get("SCENARI", "apertura")
dest = os.path.join(SP, "ib", nome)
if os.path.isdir(dest):
    shutil.rmtree(dest)
os.makedirs(dest)
def estrai(c, paths):
    arch = subprocess.run(["git", "archive", c, *paths], cwd=W, capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", dest], input=arch, check=True)
estrai(base, ["Betfair", "tactical_engine", "value_engine", "market_intelligence", ":(glob)*.py", ":(glob)*.json"])
for p in percorsi:
    # il percorso puo' non esistere nel SOPRA (file nuovo/tolto): gestito
    esiste = subprocess.run(["git", "cat-file", "-e", f"{sopra}:{p}"], cwd=W).returncode == 0
    full = os.path.join(dest, p)
    if os.path.isdir(full):
        shutil.rmtree(full)
    elif os.path.isfile(full):
        os.remove(full)
    if esiste:
        estrai(sopra, [p])
out = os.path.join(SP, f"ib_{nome}_{evento}_{scenari}.txt")
t0 = time.time()
with open(out, "w") as fh:
    subprocess.run(["timeout", "900", "python3", "-m", "Betfair.stream.backtest.certifica", "omega", evento,
                    "--data-dir", "/home/user/python-database-automation/_live_raw",
                    "--scenari", scenari, "--worker", "1"], cwd=dest, stdout=fh, stderr=subprocess.STDOUT)
testo = open(out).read()
righe = [r for r in testo.splitlines() if re.match(r"^(OK|KO|N/A|NE)\s", r)]
print(nome, f"{time.time()-t0:.0f}s")
for r in righe:
    print("  ", r)
if not righe:
    print(testo[-2000:])
