"""Mutazioni di falsificazione: applica UNA sostituzione esatta a un file (deve
esistere una volta sola), lancia pytest sui test indicati, stampa l'esito, ripristina
il file e ne verifica lo sha256.

Uso: python3 muta.py <file> <nome> <vecchio> <nuovo> <test...>
"""
import hashlib
import subprocess
import sys

f, nome, vecchio, nuovo = sys.argv[1:5]
test = sys.argv[5:]
orig = open(f, encoding="utf-8").read()
sha0 = hashlib.sha256(orig.encode("utf-8")).hexdigest()
assert orig.count(vecchio) == 1, "il testo da mutare compare %d volte" % orig.count(vecchio)
try:
    open(f, "w", encoding="utf-8").write(orig.replace(vecchio, nuovo))
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *test],
                       capture_output=True, text=True, timeout=1800)
    righe = [x for x in r.stdout.splitlines() if x.strip()]
    falliti = [x for x in righe if x.startswith("FAILED")]
    print("%s: %s" % (nome, righe[-1] if righe else r.stderr[-300:]))
    for x in falliti:
        print("   ", x[:200])
finally:
    open(f, "w", encoding="utf-8").write(orig)
sha1 = hashlib.sha256(open(f, encoding="utf-8").read().encode("utf-8")).hexdigest()
print("   ripristino: sha %s %s" % (sha1[:16], "IDENTICO" if sha1 == sha0 else "DIVERSO!"))
