"""Sezione 2 (riepilogo) - grafo degli import di PRODUZIONE aggregato per cartella.

Parte da uscite/s02_archi.tsv (importatore -> importato, solo file di produzione/strumenti) e s02_moduli.tsv.
Raggruppa i file in 'cartelle' (Betfair/stream/<sottocartella> a due livelli sotto stream; Betfair/<cartella>;
radice per i *.py di radice; altre cartelle di radice) e produce:
  1. per cartella: file, righe, import interni (archi dentro la cartella), import in uscita verso altre cartelle,
     import in entrata da altre cartelle (da produzione), n. file mai importati da produzione;
  2. i 40 archi cartella->cartella piu' pesanti (numero di coppie file->file);
  3. cicli fra cartelle (coppie A<->B con archi in entrambe le direzioni).
Uscite: uscite/s07_cartelle.txt, uscite/s07_archi_cartelle.tsv
Uso: python s07_cartelle_import.py
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comune as c  # noqa: E402

PROD = {"py_codice_Betfair", "py_codice_radice", "py_codice_cartelle_radice"}


def gruppo(rel: str) -> str:
    p = rel.split("/")
    if len(p) == 1:
        return "<radice>"
    if p[0] == "Betfair":
        if len(p) == 2:
            return "Betfair/*.py"
        if p[1] == "stream" and len(p) > 3:
            return "Betfair/stream/" + p[2]
        if p[1] == "stream":
            return "Betfair/stream/*.py"
        return "Betfair/" + p[1]
    return p[0]


def main() -> int:
    mod = {}
    for r in (c.USCITE / "s02_moduli.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        x = r.split("\t")
        mod[x[0]] = (x[2], int(x[3]))
    prod = {f for f, (ct, _) in mod.items() if ct in PROD}
    archi = [tuple(r.split("\t")) for r in (c.USCITE / "s02_archi.tsv").read_text(encoding="utf-8").splitlines()[1:]]
    archi_prod = [(a, b) for a, b in archi if a in prod and b in prod]
    righe_g = collections.Counter()
    file_g = collections.Counter()
    for f in prod:
        g = gruppo(f)
        righe_g[g] += mod[f][1]
        file_g[g] += 1
    interni = collections.Counter()
    uscita = collections.Counter()
    entrata = collections.Counter()
    pesi: dict[tuple[str, str], int] = collections.Counter()
    importati = set()
    for a, b in archi_prod:
        ga, gb = gruppo(a), gruppo(b)
        importati.add(b)
        if ga == gb:
            interni[ga] += 1
        else:
            uscita[ga] += 1
            entrata[gb] += 1
            pesi[(ga, gb)] += 1
    mai = collections.Counter(gruppo(f) for f in prod if f not in importati and not f.endswith("__init__.py"))
    out = ["== PER CARTELLA (solo file di produzione py_codice_*; archi = coppie file->file) ==",
           f"{'cartella':<34}{'file':>5}{'righe':>8}{'archi_interni':>14}{'verso_altre':>12}{'da_altre':>10}{'file_mai_importati_da_prod':>28}"]
    for g, nr in sorted(righe_g.items(), key=lambda x: -x[1]):
        out.append(f"{g:<34}{file_g[g]:>5}{nr:>8}{interni[g]:>14}{uscita[g]:>12}{entrata[g]:>10}{mai[g]:>28}")
    out.append("")
    out.append("== I 40 ARCHI cartella -> cartella PIU PESANTI (n. coppie file->file) ==")
    tsv = ["da\ta\tcoppie_file"]
    for (a, b), n in sorted(pesi.items(), key=lambda x: -x[1]):
        tsv.append(f"{a}\t{b}\t{n}")
    for (a, b), n in sorted(pesi.items(), key=lambda x: -x[1])[:40]:
        out.append(f"  {a:<34} -> {b:<34}{n:>5}")
    out.append("")
    out.append("== CICLI fra cartelle (archi in entrambe le direzioni) ==")
    visti = set()
    for (a, b), n in sorted(pesi.items(), key=lambda x: -x[1]):
        if (b, a) in pesi and (b, a) not in visti and a != b:
            visti.add((a, b))
            out.append(f"  {a} <-> {b}: {n} / {pesi[(b, a)]}")
    c.scrivi("s07_cartelle.txt", "\n".join(out) + "\n")
    c.scrivi("s07_archi_cartelle.tsv", "\n".join(tsv) + "\n")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
