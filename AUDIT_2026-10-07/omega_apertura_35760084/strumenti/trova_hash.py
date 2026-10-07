import hashlib, subprocess, sys
W = "/home/user/python-database-automation/.claude/worktrees/agent-aadcd5199a17dae8b"
def g(*a):
    return subprocess.run(["git", *a], cwd=W, capture_output=True).stdout
commits = g("log", "--first-parent", "--format=%h %ad", "--date=format:%m-%d_%H:%M", "6cffd4d7").decode().split("\n")[:450]
files = ["Betfair/omega/omega_service.py", "Betfair/omega/certificazione.py"]
for riga in commits:
    if not riga: continue
    c, d = riga.split()
    datas = [g("show", f"{c}:{f}") for f in files]
    h1 = hashlib.sha1(b"".join(datas)).hexdigest()[:12]
    h2 = hashlib.sha1(b"".join(x.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n") for x in datas)).hexdigest()[:12]
    if "676085" in (h1 + h2):
        print("MATCH", c, d, h1, h2)
print("fine")
