"""Sezione 4 (raffinamento) - file quasi-copia: per coppie di file, funzioni/metodi con lo STESSO nome (anche dentro classi
diverse) e somiglianza del corpo (difflib sul testo normalizzato: senza commenti e righe vuote).

Coppie analizzate (solo lettura, AST):
  - il trio dello scalper: Betfair/stream/scalper/scalper_bot.py, Betfair/stream/tennis_scalper/tennis_scalper_bot.py,
    laboratorio/scalper_lab/scalper_bot_base.py
  - i moduli DB dei bot: Betfair/stream/db.py, Betfair/safe_strategy/bot_db.py, Betfair/omega/omega_db.py, Betfair/mike/db.py,
    Betfair/stream/tennis_live/tennis_db.py, Betfair/safe_strategy/db.py
Per coppia: funzioni in comune per nome; identiche; simili (>= 0.90); diverse; delle diverse quante hanno la STESSA STRUTTURA
(>= 0.90 dopo aver mascherato le stringhe letterali: stesso codice con altre tabelle/chiavi) e le righe relative.
'Righe gemelle' = righe (lato A) delle funzioni identiche o simili.
Uscita: uscite/s09_gemelli_file.txt, uscite/s09_gemelli_file.tsv
Uso: python s09_gemelli_file.py
"""
from __future__ import annotations

import ast
import difflib
import itertools
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comune as c  # noqa: E402

GRUPPI = {
    "scalper": ["Betfair/stream/scalper/scalper_bot.py", "Betfair/stream/tennis_scalper/tennis_scalper_bot.py",
                "laboratorio/scalper_lab/scalper_bot_base.py"],
    "db": ["Betfair/stream/db.py", "Betfair/safe_strategy/bot_db.py", "Betfair/omega/omega_db.py", "Betfair/mike/db.py",
           "Betfair/stream/tennis_live/tennis_db.py", "Betfair/safe_strategy/db.py"],
}
NL = chr(10)
TAB = chr(9)
RE_STR = re.compile(r"\"[^\"]*\"|'[^']*'")


def masca(righe: list[str]) -> list[str]:
    return [RE_STR.sub("S", r) for r in righe]


def normalizza(seg: str) -> list[str]:
    out = []
    for r in seg.splitlines():
        s = r.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def funzioni(rel: str) -> dict[str, tuple[int, int, list[str]]]:
    t = c.leggi_testo(rel) or ""
    alb = ast.parse(t)
    righe = t.splitlines()
    res: dict[str, tuple[int, int, list[str]]] = {}
    for n in ast.walk(alb):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seg = NL.join(righe[n.lineno - 1:n.end_lineno])
            nome = n.name
            if nome in res and n.end_lineno - n.lineno + 1 <= res[nome][1]:
                continue  # stesso nome due volte nello stesso file: tengo la piu' lunga
            res[nome] = (n.lineno, n.end_lineno - n.lineno + 1, normalizza(seg))
    return res


def rapporto(x: list[str], y: list[str]) -> float:
    if len(x) * len(y) > 4_000_000:
        return 0.0
    return difflib.SequenceMatcher(None, x, y, autojunk=False).ratio()


def main() -> int:
    out = []
    tsv = [TAB.join(["gruppo", "file_a", "file_b", "funzioni_a", "funzioni_b", "in_comune_per_nome", "identiche", "simili_090",
                     "diverse", "righe_gemelle_lato_a", "righe_tot_a", "diverse_stessa_struttura", "righe_struttura_lato_a"])]
    for g, files in GRUPPI.items():
        fn = {f: funzioni(f) for f in files}
        righe_tot = {f: (c.leggi_testo(f) or "").count(NL) for f in files}
        out.append("== gruppo %s ==" % g)
        for a, b in itertools.combinations(files, 2):
            comuni = sorted(set(fn[a]) & set(fn[b]))
            ident = simili = diverse = gem = strutt = gem_s = 0
            for nome in comuni:
                la, ra = fn[a][nome][1], fn[a][nome][2]
                rb = fn[b][nome][2]
                if ra == rb:
                    ident += 1
                    gem += la
                elif rapporto(ra, rb) >= 0.90:
                    simili += 1
                    gem += la
                else:
                    diverse += 1
                    if rapporto(masca(ra), masca(rb)) >= 0.90:
                        strutt += 1
                        gem_s += la
            if len(comuni) <= 2:
                continue  # coppie senza funzioni in comune (solo _now_iso/_sb): non interessano
            out.append("  %s (%d funz., %d righe)  vs  %s (%d funz., %d righe): %d nomi in comune, %d identiche, %d simili>=0.90, %d diverse; "
                       "righe gemelle lato A = %d (%.1f%% del file A); delle diverse %d hanno la STESSA STRUTTURA (stringhe mascherate), %d righe lato A" % (
                           a, len(fn[a]), righe_tot[a], b, len(fn[b]), righe_tot[b], len(comuni), ident, simili, diverse, gem,
                           100.0 * gem / max(1, righe_tot[a]), strutt, gem_s))
            tsv.append(TAB.join(map(str, [g, a, b, len(fn[a]), len(fn[b]), len(comuni), ident, simili, diverse, gem, righe_tot[a], strutt, gem_s])))
        out.append("")
    c.scrivi("s09_gemelli_file.txt", NL.join(out) + NL)
    c.scrivi("s09_gemelli_file.tsv", NL.join(tsv) + NL)
    print(NL.join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
