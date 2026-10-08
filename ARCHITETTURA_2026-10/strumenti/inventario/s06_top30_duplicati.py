"""Sezione 4 (raffinamento) - le 30 funzioni duplicate piu' pesanti in produzione, con giudizio per copia.

Parte da uscite/s04_dettaglio_copie.tsv (prodotto da s04_duplicati.py). Per ogni nome di funzione con
>= 3 copie in produzione: righe totali, quante copie stanno in un gruppo con altre (IDENTICA = rapporto 1.00
con il capogruppo, QUASI = 0.90-0.99) e quante sono DIVERSE (gruppo da sole, rapporto < 0.90 con tutti i capigruppo).
'Righe recuperabili' = righe delle copie non capogruppo dei gruppi con >= 2 membri (stima per difetto: una
sola copia condivisa basterebbe). Nomi di metodo generici (__init__, main, ...) separati: sono omonimie.
Uso: python s06_top30_duplicati.py   (solo libreria standard, sola lettura)
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comune as c  # noqa: E402

OMONIMI = {"__init__", "main", "__getattr__", "__str__", "__repr__", "run", "stato", "avvia", "ferma", "azzera", "log"}


def main() -> int:
    righe = (c.USCITE / "s04_dettaglio_copie.tsv").read_text(encoding="utf-8").splitlines()[1:]
    per_nome: dict[str, list[tuple]] = collections.defaultdict(list)
    for r in righe:
        nome, file, riga, lung, classe, cat, gruppo, rap = r.split("\t")
        per_nome[nome].append((file, int(riga), int(lung), classe, int(gruppo), float(rap)))
    out = []
    for nome, lst in per_nome.items():
        if len(lst) < 3:
            continue
        gruppi: dict[int, list[tuple]] = collections.defaultdict(list)
        for x in lst:
            gruppi[x[4]].append(x)
        ident = quasi = diverse = ricup = 0
        for g in gruppi.values():
            if len(g) == 1:
                diverse += 1
                continue
            for x in g[1:]:
                ricup += x[2]
                if x[5] >= 0.9999:
                    ident += 1
                else:
                    quasi += 1
            # il capogruppo conta come 'ripetuta' ma non e' recuperabile
        in_gruppi = sum(len(g) for g in gruppi.values() if len(g) > 1)
        tot = sum(x[2] for x in lst)
        esempi = ", ".join(f"{x[0]}:{x[1]}" for x in lst[:3])
        out.append((nome, len(lst), len({x[0] for x in lst}), tot, in_gruppi, ident, quasi, diverse, ricup, len(gruppi), esempi))
    out.sort(key=lambda x: -x[3])
    t = ["nome\tcopie\tfile\trighe_totali\tcopie_in_gruppi_>=2\tcopie_identiche_al_capogruppo\tcopie_quasi(>=0.90)\tcopie_diverse(singole)\trighe_recuperabili\tn_gruppi\tprime_3_copie"]
    for x in out:
        t.append("\t".join(map(str, x)))
    c.scrivi("s06_top_duplicati.tsv", "\n".join(t) + "\n")
    r = []
    r.append("== TOP 30 per righe totali (esclusi metodi omonimi generici) ==")
    r.append(f"{'nome':<28}{'copie':>6}{'file':>5}{'righe':>7}{'ident':>6}{'quasi':>6}{'div':>5}{'recup':>7}  giudizio")
    n = 0
    for x in out:
        if x[0] in OMONIMI:
            continue
        n += 1
        if n > 30:
            break
        g = "IDENTICHE" if x[7] == 0 and x[6] == 0 and x[5] >= 1 else ("IDENTICHE/QUASI" if x[7] == 0 else ("DIVERSE" if x[4] == 0 else "MISTE"))
        r.append(f"{x[0]:<28}{x[1]:>6}{x[2]:>5}{x[3]:>7}{x[5]:>6}{x[6]:>6}{x[7]:>5}{x[8]:>7}  {g}")
    r.append("")
    r.append("== omonimie generiche (non sono duplicati da fondere per costruzione) ==")
    for x in out:
        if x[0] in OMONIMI:
            r.append(f"{x[0]:<28}{x[1]:>6}{x[2]:>5}{x[3]:>7}{x[5]:>6}{x[6]:>6}{x[7]:>5}{x[8]:>7}")
    r.append("")
    tot_ricup = sum(x[8] for x in out if x[0] not in OMONIMI)
    r.append(f"righe recuperabili per copie identiche/quasi (esclusi omonimi): {tot_ricup} su {len(out)} nomi con >= 3 copie")
    c.scrivi("s06_top_duplicati.txt", "\n".join(r) + "\n")
    print("\n".join(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
