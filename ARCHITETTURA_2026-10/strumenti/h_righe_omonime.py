"""Strumento di misura H: righe dentro funzioni/classi con lo STESSO nome in >=2 file di replay (o di controlli).

Uso (sola lettura): python -I ARCHITETTURA_2026-10/strumenti/h_righe_omonime.py
Stampa, per ogni gruppo, le righe totali, quelle in nomi omonimi e il totale dei file.
ASCII-only; commenti in italiano.
"""
import ast
from collections import defaultdict

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


def livello_zero(percorso):
    """nome -> righe (def/class di primo livello)."""
    src = open(percorso, encoding="utf-8").read()
    out = {}
    for n in ast.parse(src).body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[n.name] = n.end_lineno - n.lineno + 1
    return out, len(src.splitlines())


def gruppo(titolo, files):
    dati = {k: livello_zero(v) for k, v in files.items()}
    presenza = defaultdict(int)
    for k, (f, _) in dati.items():
        for nome in f:
            presenza[nome] += 1
    print("=== " + titolo)
    tot_file = tot_om = 0
    for k, (f, n) in dati.items():
        om = sum(r for nome, r in f.items() if presenza[nome] >= 2)
        print("  %-12s file %5d righe | in nomi omonimi (>=2 file) %5d" % (k, n, om))
        tot_file += n
        tot_om += om
    print("  TOTALE       file %5d righe | in nomi omonimi %5d (%.1f%%)" % (tot_file, tot_om, 100.0 * tot_om / tot_file))


gruppo("ADATTATORI DI REPLAY", REPLAY)
gruppo("MODULI DI CONTROLLI", CONTROLLI)
