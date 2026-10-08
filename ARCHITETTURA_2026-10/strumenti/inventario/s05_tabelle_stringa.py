"""Sezione 3 (controllo) - per ogni tabella DEFINITA nei .sql di migrations/ e sql/ ma senza chiamata `.table()` letterale (s03),
cerca il nome come PAROLA INTERA in tutto il codice di produzione (py), frontend/src non test, desktop e workflow: riga non commento.
Cosi' si distinguono le tabelle davvero morte da quelle toccate con costanti, REST diretto, SQL dentro RPC o liste di nomi.
E per le tabelle USATE ma non definite nei .sql tracciati: se il nome compare in DOCUMENTAZIONE_DATABASE.md.
Uso: python s05_tabelle_stringa.py   (legge uscite/s03_matrice_tabelle.tsv, s03_definizioni.tsv)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comune as c  # noqa: E402
from s01_righe import categoria  # noqa: E402

CAT_OK = {"py_codice_Betfair", "py_codice_radice", "py_codice_cartelle_radice", "frontend_codice", "desktop_codice"}


def main() -> int:
    mat = [r.split("\t") for r in (c.USCITE / "s03_matrice_tabelle.tsv").read_text(encoding="utf-8").splitlines()]
    head, righe = mat[0], mat[1:]
    ix = {h: i for i, h in enumerate(head)}
    usate = {r[0] for r in righe if int(r[ix["n_prod"]]) + int(r[ix["n_frontend"]]) > 0}
    defs = [r.split("	") for r in (c.USCITE / "s03_definizioni.tsv").read_text(encoding="utf-8").splitlines()[1:]]
    mai_usate = sorted({d[1] for d in defs if d[0] == "table" and d[1] not in usate})
    non_def = [r[0] for r in righe if r[ix["definita_in"]] == "-" and not r[0].startswith("<") and int(r[ix["n_prod"]]) + int(r[ix["n_frontend"]]) > 0]
    testi = {}
    for rel in c.file_tracciati():
        if categoria(rel) in CAT_OK or rel.startswith(".github/workflows/"):
            t = c.leggi_testo(rel)
            if t is not None:
                testi[rel] = t.splitlines()
    out = ["tabella\tstato\tn_righe_non_commento\tprime_citazioni"]
    riep = []
    for nome in mai_usate:
        rx = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(nome) + r"(?![A-Za-z0-9_])")
        hits = []
        for rel, ls in testi.items():
            for i, l in enumerate(ls, 1):
                if l.lstrip().startswith(("#", "//", "*", "--")):
                    continue
                if rx.search(l):
                    hits.append(f"{rel}:{i}")
        stato = "RIFERITA_PER_STRINGA" if hits else "NESSUN_RIFERIMENTO_IN_PRODUZIONE"
        out.append(f"{nome}\t{stato}\t{len(hits)}\t{'; '.join(hits[:4])}")
        riep.append((stato, nome, len(hits), hits[:3]))
    doc = (c.RADICE / "DOCUMENTAZIONE_DATABASE.md").read_text(encoding="utf-8", errors="replace") if (c.RADICE / "DOCUMENTAZIONE_DATABASE.md").exists() else ""
    out.append("")
    out.append("tabella_usata_non_definita_nei_sql_tracciati\tnominata_in_DOCUMENTAZIONE_DATABASE.md")
    for nome in non_def:
        out.append(f"{nome}\t{'si' if re.search(r'(?<![A-Za-z0-9_])' + re.escape(nome) + r'(?![A-Za-z0-9_])', doc) else 'no'}")
    c.scrivi("s05_tabelle_stringa.tsv", "\n".join(out) + "\n")
    print(f"definite e senza .table() letterale: {len(mai_usate)}")
    print("  riferite per stringa:", sum(1 for x in riep if x[0] == "RIFERITA_PER_STRINGA"))
    print("  nessun riferimento in produzione:", [x[1] for x in riep if x[0] != "RIFERITA_PER_STRINGA"])
    for x in riep:
        if x[0] == "RIFERITA_PER_STRINGA":
            print(f"   {x[1]:<40}{x[2]:>4}  {', '.join(x[3])}")
    print("usate e non definite:", len(non_def), "di cui nominate in DOCUMENTAZIONE_DATABASE.md:",
          sum(1 for n in non_def if re.search(r'(?<![A-Za-z0-9_])' + re.escape(n) + r'(?![A-Za-z0-9_])', doc)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
