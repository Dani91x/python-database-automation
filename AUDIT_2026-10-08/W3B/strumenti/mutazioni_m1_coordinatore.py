"""Le due mutazioni del coordinatore (08/10) su ``ordini_esterni.py``, separate e
insieme: M1 nella ``rivedi`` (esito di un bot trattato come fuori bot), M1b nel
primo punto di decisione di ``valuta_righe`` (esito gia' in cache). Contenuto
salvato, mutazione, test W3b, ripristino; sha verificato."""
import hashlib
import subprocess
import sys

WT = "/home/user/python-database-automation/.claude/worktrees/agent-aa6d8083bb40b34bd"
OE = WT + "/Betfair/stream/tennis_scalper/ordini_esterni.py"
TESTS = ["Betfair/stream/tests/test_w3b_ordini_esterni_scalper_2026_10_08.py",
         "Betfair/stream/tennis_live/tests/test_w3b_ordini_esterni_tennis_2026_10_08.py"]

# (riga attesa, testo vecchio, testo nuovo): la riga distingue i due punti
M1 = ("                esito = self._conferma.esito(bid)\n                if esito == FUORI_BOT:\n                    self._attesa.pop(bid, None)\n",
      "                esito = self._conferma.esito(bid)\n                if esito is not None:  # MUTAZIONE M1\n                    self._attesa.pop(bid, None)\n")
M1B = ("                esito = self._conferma.esito(bid)\n                if esito == FUORI_BOT:\n                    if scatto is None:\n",
       "                esito = self._conferma.esito(bid)\n                if esito is not None:  # MUTAZIONE M1b\n                    if scatto is None:\n")
CASI = {"M1": [M1], "M1b": [M1B], "M1+M1b": [M1, M1B]}


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    sel = sys.argv[1:] or list(CASI)
    for nome in sel:
        orig = open(OE, encoding="utf-8").read()
        h0 = sha(OE)
        testo = orig
        ok = True
        for old, new in CASI[nome]:
            if testo.count(old) != 1:
                print("%s -> NON APPLICABILE (%d)" % (nome, testo.count(old)))
                ok = False
                break
            testo = testo.replace(old, new)
        if not ok:
            continue
        try:
            open(OE, "w", encoding="utf-8").write(testo)
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                "--no-header", *TESTS], cwd=WT, capture_output=True,
                               text=True, timeout=900)
        finally:
            open(OE, "w", encoding="utf-8").write(orig)
        righe = [x for x in r.stdout.splitlines() if x.strip()]
        rossi = [x for x in righe if x.startswith("FAILED")]
        print("%s -> %s | %s | sha %s %s" % (
            nome, "ROSSO" if r.returncode else "VERDE (non catturata)",
            righe[-1] if righe else r.stderr[-200:], h0[:12],
            "ripristinato" if sha(OE) == h0 else "DIVERSO!"))
        for x in rossi:
            print("    " + x)


main()
