"""Falsificazione: applica UNA mutazione (sostituzione testuale esatta, che deve
comparire una volta sola) a un file, lancia i test indicati, ripristina il file e
verifica lo sha256. Uso:
python3 muta.py <file> <nome> <file_col_testo_vecchio> <file_col_testo_nuovo> <test...>
"""
import hashlib
import os
import shutil
import subprocess
import sys

f, nome, vecchio_p, nuovo_p = sys.argv[1:5]
tests = sys.argv[5:]
vecchio = open(vecchio_p, encoding="utf-8").read()
nuovo = open(nuovo_p, encoding="utf-8").read()


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


prima = sha(f)
testo = open(f, encoding="utf-8").read()
n = testo.count(vecchio)
if n != 1:
    print("MUTAZIONE %s: il testo da mutare compare %d volte, annullata" % (nome, n))
    sys.exit(2)
copia = f + ".salva_mut"
shutil.copyfile(f, copia)
try:
    with open(f, "w", encoding="utf-8") as fh:
        fh.write(testo.replace(vecchio, nuovo))
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"] + tests,
                       capture_output=True, text=True, timeout=3000)
    righe = [l for l in r.stdout.splitlines() if (" passed" in l or " failed" in l
                                                  or " error" in l)]
    print("MUTAZIONE %s: %s" % (nome, righe[-1] if righe else r.stdout[-400:]))
finally:
    shutil.copyfile(copia, f)
    os.remove(copia)
dopo = sha(f)
print("  sha256 prima %s dopo %s %s" % (prima[:16], dopo[:16],
                                       "IDENTICO" if prima == dopo else "DIVERSO!!"))
