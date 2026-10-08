"""Sezione 2 (controllo dei candidati morti) - ricerca per NOME del modulo (parola intera) nei file tracciati.

s02 (AST) trova gli import risolti; questo script e' la controprova per stringa: per ogni modulo dei gruppi A (nessun
riferimento) e B (solo __main__ o stringa) di uscite/s02_morti.txt cerca lo stem del file come parola intera in tutti i
file tracciati di CODICE E LANCIO (py, js, ts, tsx, yml, bat, ps1, sh, toml), esclusi: il file stesso, i test, le
cartelle AUDIT_*/SCHEMI_BOT/_AUDIT_*/ARCHITETTURA_*. Esito:
  ZERO     = nessuna citazione: morto certo (salvo avvio da riga di comando a mano)
  CITATO   = almeno una citazione (file:riga, prime 3): da leggere a mano, probabilmente testo/commento/omonimia
Uscita: uscite/s08_morti_verifica.tsv, uscite/s08_morti_verifica.txt
Uso: python s08_morti_verifica.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comune as c  # noqa: E402
from s01_righe import categoria  # noqa: E402

EST = (".py", ".js", ".ts", ".tsx", ".yml", ".yaml", ".bat", ".ps1", ".sh", ".toml", ".mjs")
ESCLUSI = re.compile(r"^(AUDIT_|_AUDIT_|SCHEMI_BOT/|ARCHITETTURA_2026-10/)")
NL = chr(10)


def main() -> int:
    righe = (c.USCITE / "s02_morti.txt").read_text(encoding="utf-8").splitlines()
    gruppo = ""
    cand: list[tuple[str, str]] = []
    for l in righe:
        if l.startswith("== A_"):
            gruppo = "A"
        elif l.startswith("== B_"):
            gruppo = "B"
        elif l.startswith("== C_") or l.startswith("== D_"):
            gruppo = ""
        elif gruppo and l.startswith("  "):
            f = l.strip().split("  (")[0]
            cand.append((gruppo, f))
    testi = {}
    for rel in c.file_tracciati():
        if rel.endswith(EST) and not ESCLUSI.match(rel) and categoria(rel) != "py_test":
            t = c.leggi_testo(rel)
            if t is not None:
                testi[rel] = t.splitlines()
    out = ["gruppo\tmodulo\tesito\tn_citazioni\tprime_citazioni"]
    zero = {"A": 0, "B": 0}
    cit = {"A": 0, "B": 0}
    for g, f in cand:
        stem = Path(f).stem
        if stem == "__init__":
            continue
        rx = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(stem) + r"(?![A-Za-z0-9_])")
        hits = []
        for rel, ls in testi.items():
            if rel == f:
                continue
            for i, l in enumerate(ls, 1):
                if rx.search(l):
                    hits.append(rel + ":" + str(i))
        esito = "ZERO" if not hits else "CITATO"
        (zero if esito == "ZERO" else cit)[g] += 1
        out.append("\t".join([g, f, esito, str(len(hits)), "; ".join(hits[:3])]))
    c.scrivi("s08_morti_verifica.tsv", NL.join(out) + NL)
    r = ["gruppo A (nessun riferimento secondo s02): ZERO citazioni per stringa=%d, CITATO=%d" % (zero["A"], cit["A"]),
         "gruppo B (solo __main__ o stringa): ZERO=%d, CITATO=%d" % (zero["B"], cit["B"]), ""]
    r.append("-- gruppo A con ZERO citazioni (morti certi):")
    for l in out[1:]:
        x = l.split("\t")
        if x[0] == "A" and x[2] == "ZERO":
            r.append("   " + x[1])
    r.append("-- gruppo A CITATI (da leggere):")
    for l in out[1:]:
        x = l.split("\t")
        if x[0] == "A" and x[2] == "CITATO":
            r.append("   %s  [%s]  %s" % (x[1], x[3], x[4][:150]))
    r.append("-- gruppo B con ZERO citazioni (script con __main__ mai richiamati da nessuno):")
    for l in out[1:]:
        x = l.split("\t")
        if x[0] == "B" and x[2] == "ZERO":
            r.append("   " + x[1])
    c.scrivi("s08_morti_verifica.txt", NL.join(r) + NL)
    print(NL.join(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
