"""Strumento di misura H (banco di replay): funzioni gemelle fra gli adattatori per bot.

Uso (sola lettura, nessun import dell'app):
    python -I ARCHITETTURA_2026-10/strumenti/h_gemelli_adattatori.py

Per ogni coppia di file di replay (o di controlli) cerca le funzioni con lo STESSO nome e
ne misura la somiglianza con difflib (rapporto 0..1 sul testo normalizzato: via commenti,
docstring e righe vuote). Stampa anche il numero di funzioni in comune a tutti.
ASCII-only; commenti in italiano.
"""
import ast
import difflib
import itertools
import re
import sys

RADICE = "."
REPLAY = {
    "mike": "Betfair/mike/tools/replay_registrazioni.py",
    "omega": "Betfair/omega/tools/replay_registrazioni.py",
    "safe": "Betfair/safe_strategy/tools/replay_registrazioni.py",
    "safe_tennis": "Betfair/safe_strategy/tools/replay_tennis.py",
    "scalper": "Betfair/stream/scalper/tools/replay_registrazioni.py",
    "tennis": "Betfair/stream/tennis_live/tools/replay_bot.py",
}
CONTROLLI = {
    "mike": "Betfair/mike/certificazione.py",
    "omega": "Betfair/omega/certificazione.py",
    "safe": "Betfair/safe_strategy/certificazione.py",
    "safe_tennis": "Betfair/safe_strategy/certificazione_tennis.py",
    "scalper": "Betfair/stream/scalper/certificazione.py",
    "tennis": "Betfair/stream/tennis_live/certificazione_bot.py",
}


def funzioni(percorso):
    """nome -> (riga_inizio, riga_fine, testo normalizzato) per ogni def/class di primo livello."""
    sorgente = open(percorso, encoding="utf-8").read()
    righe = sorgente.splitlines()
    albero = ast.parse(sorgente)
    out = {}
    for nodo in albero.body:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            fine = nodo.end_lineno
            testo = "\n".join(righe[nodo.lineno - 1:fine])
            # normalizza: toglie commenti, righe vuote, docstring a triplo apice
            testo = re.sub(r'""".*?"""', "", testo, flags=re.S)
            norm = []
            for r in testo.splitlines():
                r = re.sub(r"\s+#.*$", "", r).rstrip()
                if r.strip() and not r.strip().startswith("#"):
                    norm.append(r)
            out[nodo.name] = (nodo.lineno, fine, "\n".join(norm))
    return out


def confronta(gruppo, titolo):
    print("=== " + titolo)
    dati = {k: funzioni(v) for k, v in gruppo.items()}
    for k, d in dati.items():
        tot = sum(f - i + 1 for i, f, _ in d.values())
        print("  %-12s %3d funzioni/classi di primo livello, %5d righe dentro" % (k, len(d), tot))
    comuni_a_tutti = set.intersection(*[set(d) for d in dati.values()])
    print("  nomi presenti in TUTTI i %d file: %s" % (len(dati), sorted(comuni_a_tutti)))
    # per ogni nome presente in almeno 2 file: coppie con somiglianza
    nomi = {}
    for k, d in dati.items():
        for n in d:
            nomi.setdefault(n, []).append(k)
    ripetuti = {n: ks for n, ks in nomi.items() if len(ks) >= 2}
    print("  nomi presenti in >=2 file: %d" % len(ripetuti))
    for n in sorted(ripetuti):
        ks = ripetuti[n]
        for a, b in itertools.combinations(ks, 2):
            ia, fa, ta = dati[a][n]
            ib, fb, tb = dati[b][n]
            rapporto = difflib.SequenceMatcher(None, ta.splitlines(), tb.splitlines()).ratio()
            print("    %-34s %-11s %s:%d-%d (%d r)  <->  %-11s :%d-%d (%d r)  somiglianza=%.2f"
                  % (n, a, "", ia, fa, fa - ia + 1, b, ib, fb, fb - ib + 1, rapporto))


if __name__ == "__main__":
    confronta(REPLAY, "ADATTATORI DI REPLAY")
    confronta(CONTROLLI, "MODULI DI CONTROLLI")
