"""G1 - estrae dalle migrazioni SQL tracciate (migrations/, sql/) tabelle, funzioni RPC, chiavi e indici unici.

Solo libreria standard, sola lettura. Scrive SOLO in ARCHITETTURA_2026-10/strumenti/dati_g1/uscite/.
Rieseguibile: python ARCHITETTURA_2026-10/strumenti/dati_g1/estrai_schema.py
Uscite: sql_tabelle.tsv (tabella, file, riga), sql_funzioni.tsv (funzione, file, riga),
        sql_unici.tsv (tabella, tipo, definizione, file, riga), sql_righe.txt (conteggio righe)
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

RADICE = Path(__file__).resolve().parents[3]
USCITE = Path(__file__).resolve().parent / "uscite"
USCITE.mkdir(parents=True, exist_ok=True)

RE_T = re.compile(r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?\"?([a-z_0-9]+)\"?", re.I)
RE_F = re.compile(r"create\s+(?:or\s+replace\s+)?function\s+(?:public\.)?\"?([a-z_0-9]+)\"?\s*\(", re.I)
RE_UI = re.compile(r"create\s+unique\s+index\s+(?:if\s+not\s+exists\s+)?\"?([a-z_0-9]+)\"?\s+on\s+(?:public\.)?\"?([a-z_0-9]+)\"?\s*(?:using\s+\w+\s*)?\(([^)]*)\)", re.I)
RE_PK = re.compile(r"primary\s+key\s*\(([^)]*)\)", re.I)
RE_UQ = re.compile(r"unique\s*\(([^)]*)\)", re.I)


def main() -> None:
    o = subprocess.run(["git", "ls-files", "-z", "migrations", "sql"], cwd=RADICE, capture_output=True, check=True)
    files = [p for p in o.stdout.decode("utf-8", "replace").split("\0") if p.endswith(".sql")]
    tot = 0
    tab, fun, uni = [], [], []
    for f in files:
        t = (RADICE / f).read_text("utf-8", errors="replace")
        tot += t.count("\n")
        # una passata per tabella: si tiene la tabella corrente per attribuire pk/unique in linea
        corrente = None
        for n, riga in enumerate(t.split("\n"), 1):
            m = RE_T.search(riga)
            if m:
                corrente = m.group(1)
                tab.append(f"{corrente}\t{f}\t{n}")
            m = RE_F.search(riga)
            if m:
                fun.append(f"{m.group(1)}\t{f}\t{n}")
            m = RE_UI.search(riga)
            if m:
                uni.append(f"{m.group(2)}\tunique_index\t{m.group(3).strip()}\t{f}\t{n}")
            m = RE_PK.search(riga)
            if m and corrente:
                uni.append(f"{corrente}\tprimary_key\t{m.group(1).strip()}\t{f}\t{n}")
            m = RE_UQ.search(riga)
            if m and corrente:
                uni.append(f"{corrente}\tunique\t{m.group(1).strip()}\t{f}\t{n}")
            if re.search(r"\bprimary\s+key\b", riga, re.I) and not RE_PK.search(riga) and corrente:
                uni.append(f"{corrente}\tprimary_key_colonna\t{riga.strip()[:80]}\t{f}\t{n}")
            if ";" in riga and not riga.strip().startswith("--") and re.search(r"\)\s*;\s*$", riga):
                corrente = None if corrente and RE_T.search(riga) is None and False else corrente
    (USCITE / "sql_tabelle.tsv").write_text("\n".join(tab) + "\n", encoding="utf-8")
    (USCITE / "sql_funzioni.tsv").write_text("\n".join(fun) + "\n", encoding="utf-8")
    (USCITE / "sql_unici.tsv").write_text("\n".join(uni) + "\n", encoding="utf-8")
    (USCITE / "sql_righe.txt").write_text(f"file_sql={len(files)} righe={tot}\n", encoding="utf-8")
    print(len(files), tot, len(tab), len(fun), len(uni))


if __name__ == "__main__":
    main()
