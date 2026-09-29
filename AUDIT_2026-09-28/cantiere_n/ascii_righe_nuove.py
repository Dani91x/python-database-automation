"""Rende ASCII le righe AGGIUNTE dal cantiere N (diff contro origin/master) nei
file di codice (.py .sql .ts .tsx): virgolette a caporale -> doppi apici,
lineette -> '-', apostrofo tipografico -> ', ellissi -> '...'. Le righe degli
altri non si toccano. Stampa cio' che resta non ASCII."""
import os
import subprocess

WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAPPA = {chr(0xab): chr(34), chr(0xbb): chr(34), chr(0x2014): "-", chr(0x2013): "-",
         chr(0x2019): "'", chr(0x2018): "'", chr(0x2026): "...", chr(0x2032): "'",
         chr(0x201c): chr(34), chr(0x201d): chr(34), chr(0x2192): "->", chr(0xd7): "x",
         chr(0xb7): "-"}
EST = (".py", ".sql", ".ts", ".tsx")


def git(*a):
    return subprocess.run(["git", *a], cwd=WT, capture_output=True, text=True,
                          encoding="utf-8").stdout


def main():
    nomi = [n for n in git("diff", "--name-only", "origin/master").splitlines()
            if n.endswith(EST)]
    nomi += [n for n in git("ls-files", "--others", "--exclude-standard").splitlines()
             if n.endswith(EST)]
    for nome in sorted(set(nomi)):
        path = os.path.join(WT, nome)
        if not os.path.exists(path):
            continue
        diff = git("diff", "-U0", "origin/master", "--", nome)
        if not diff:        # file non tracciato: tutto e' nuovo
            aggiunte = None
        else:
            aggiunte = {r[1:] for r in diff.splitlines() if r.startswith("+") and not r.startswith("+++")}
        with open(path, "r", encoding="utf-8", newline="") as fh:
            righe = fh.read().split("\n")
        cambiate = 0
        for i, r in enumerate(righe):
            nuda = r.rstrip("\r")
            if aggiunte is not None and nuda not in aggiunte:
                continue
            if all(ord(c) < 128 for c in r):
                continue
            nuova = r
            for k, v in MAPPA.items():
                nuova = nuova.replace(k, v)
            if nuova != r:
                righe[i] = nuova
                cambiate += 1
        if cambiate:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write("\n".join(righe))
        resto = [r for r in righe if (aggiunte is None or r.rstrip("\r") in aggiunte)
                 and any(ord(c) > 127 for c in r)]
        if cambiate or resto:
            print(f"{nome}: {cambiate} righe rese ASCII, {len(resto)} ancora non ASCII")
            for r in resto[:3]:
                print("   ", r.strip()[:100].encode("ascii", "backslashreplace").decode())


if __name__ == "__main__":
    main()
