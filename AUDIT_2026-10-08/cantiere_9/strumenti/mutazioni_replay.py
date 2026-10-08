"""Falsificazione A LIVELLO DI REPLAY (PROCESSO par. 6.7): si reintroduce un
difetto nel BOT, si lancia il replay vero dello scenario nuovo su 35797769 e si
leggono le violazioni; poi ripristino e sha256. Una mutazione per volta."""
import hashlib
import os
import shutil
import subprocess
import sys

S = "/tmp/claude-0/-home-user-python-database-automation/d9b4fd9d-aa86-54f8-97b7-ad733bb0c124/scratchpad/c9"
W = "/home/user/python-database-automation/.claude/worktrees/agent-acf5e90f86ae32c4b"
BOT = "Betfair/stream/scalper/scalper_bot.py"

M = [
    ("BF1 niente scavalco (difetto: residuo sotto 0,50 dichiarato, non chiuso)",
     BOT, "ingresso-abbinato-in-parte",
     "        if not self.exact_exits or self.dry_run or slot.submins:\n            return False\n        if abs(net_win - net_lose) <= 0.02:\n            return False\n        if slot.scavalchi >= self._SCAVALCHI_MAX_PER_CICLO:",
     "        return False  # MUTAZIONE BF1\n        if abs(net_win - net_lose) <= 0.02:\n            return False\n        if slot.scavalchi >= self._SCAVALCHI_MAX_PER_CICLO:"),
    ("BF2 scavalco senza la sua attivita'",
     BOT, "ingresso-abbinato-in-parte",
     "        self._emit(\"scavalco\", selection_id=int(sid), side=lato, price=quota,",
     "        self._emit(\"scavalco_MUTATO\", selection_id=int(sid), side=lato, price=quota,"),
    ("BF3 scavalco dimensionato male (punta 0,50: la chiusura resta sotto il floor)",
     "Betfair/stream/scalper/scalper_bot.py", "ingresso-abbinato-in-parte",
     "        return \"BACK\", float(q), float(IT_BACK_MIN_STAKE)\n",
     "        return \"BACK\", float(q), 0.5  # MUTAZIONE BF3\n"),
    ("BF4 rifiuto di taglia ignorato (nessuna riga, nessun freno)",
     BOT, "rifiuti-betfair-codici",
     "            if self._codice_rifiuto(o) != CODICE_TAGLIA:\n                continue\n",
     "            continue  # MUTAZIONE BF4\n"),
]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


os.chdir(W)
scelte = sys.argv[1:]
for nome, f, scenario, vecchio, nuovo in M:
    if scelte and nome.split()[0] not in scelte:
        continue
    prima = sha(f)
    testo = open(f, encoding="utf-8").read()
    if testo.count(vecchio) != 1:
        print("MUTAZIONE %s: testo trovato %d volte, NON eseguita" % (nome, testo.count(vecchio)))
        continue
    copia = f + ".salva_mut"
    shutil.copyfile(f, copia)
    out = os.path.join(S, "mut", "replay_%s.txt" % nome.split()[0])
    try:
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(testo.replace(vecchio, nuovo))
        r = subprocess.run([sys.executable, "-m", "Betfair.stream.backtest.certifica",
                            "scalper_calcio", "35797769", "--scenari", scenario,
                            "--worker", "1", "--data-dir", os.path.join(W, "_live_raw")],
                           capture_output=True, text=True, timeout=3600)
        open(out, "w", encoding="utf-8").write(r.stdout + "\n--- stderr ---\n" + r.stderr[-3000:])
        esito = [l for l in r.stdout.splitlines() if l.startswith(("OK ", "KO ", "NE "))]
        viol = [l.strip() for l in r.stdout.splitlines()
                if l.strip()[:3] in ("SV1", "SV2", "SV3", "SV4", "SV5", "RC1", "RC2", "RC3", "RC4")
                and " x" in l[:12]]
        print("MUTAZIONE %s [%s]: %s | %s" % (nome, scenario, esito[0][:60] if esito else "?",
                                              "; ".join(v[:70] for v in viol) or "nessuna SV/RC"))
    finally:
        shutil.copyfile(copia, f)
        os.remove(copia)
    dopo = sha(f)
    print("  sha256 %s prima %s dopo %s %s" % (f, prima[:16], dopo[:16],
                                             "IDENTICO" if prima == dopo else "DIVERSO!!"))
