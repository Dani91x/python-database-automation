"""Misura del codice GEMELLO fra lo scalper calcio e lo scalper tennis (scheda E4).

Uso (sola lettura, nessun import del codice di produzione):
    python ARCHITETTURA_2026-10/strumenti/e4_gemelli_tennis.py

Cosa misura, per ogni coppia di file (calcio, tennis):
  * righe totali (wc -l) e righe "di codice" (senza vuote e senza commenti da solo);
  * percentuale gemella a livello di file: somma dei blocchi uguali trovati da
    difflib.SequenceMatcher sulle righe di codice normalizzate (strip), divisa per le
    righe di codice di OGNI file (quindi due percentuali);
  * per ogni funzione con LO STESSO NOME nei due file: righe di codice di entrambe e
    rapporto difflib.ratio() (2*M/T) sulle righe di codice del corpo.
Le righe di codice non contano docstring e commenti # (sono testo, non logica), ma la
normalizzazione e' volutamente elementare e dichiarata qui: nessuna altra pulizia.
ASCII-only, nessuna scrittura su disco: stampa a video.
"""
from __future__ import annotations

import ast
import difflib
import os
import sys
from typing import Dict, List, Tuple

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

COPPIE: List[Tuple[str, str]] = [
    ("Betfair/stream/scalper/scalper_bot.py",
     "Betfair/stream/tennis_scalper/tennis_scalper_bot.py"),
    ("Betfair/stream/scalper/auto_mode.py",
     "Betfair/stream/tennis_live/auto_mode.py"),
    ("Betfair/stream/scalper/scalper_service.py",
     "Betfair/stream/tennis_live/tennis_bot_service.py"),
    ("Betfair/stream/scalper/scalper_session.py",
     "Betfair/stream/tennis_live/tennis_bot_service.py"),
    ("Betfair/stream/scalper/scalper_session.py",
     "Betfair/stream/tennis_live/tennis_live_order_worker.py"),
]


def leggi(percorso: str) -> List[str]:
    with open(os.path.join(RADICE, percorso), encoding="utf-8") as f:
        return f.read().split("\n")


def righe_di_codice(righe: List[str]) -> List[str]:
    """Righe non vuote e non solo-commento, strip; docstring escluse dall'AST."""
    escluse = set()
    try:
        albero = ast.parse("\n".join(righe))
    except SyntaxError:
        albero = None
    if albero is not None:
        for nodo in ast.walk(albero):
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                corpo = getattr(nodo, "body", [])
                if corpo and isinstance(corpo[0], ast.Expr) and isinstance(
                        getattr(corpo[0], "value", None), ast.Constant) and isinstance(
                        corpo[0].value.value, str):
                    for n in range(corpo[0].lineno, corpo[0].end_lineno + 1):
                        escluse.add(n)
    out = []
    for i, r in enumerate(righe, start=1):
        s = r.strip()
        if not s or s.startswith("#") or i in escluse:
            continue
        out.append(s)
    return out


def funzioni(percorso: str) -> Dict[str, Tuple[int, int, List[str]]]:
    """nome qualificato -> (riga inizio, riga fine, righe di codice del corpo)."""
    righe = leggi(percorso)
    albero = ast.parse("\n".join(righe))
    out: Dict[str, Tuple[int, int, List[str]]] = {}

    def visita(nodo, prefisso: str) -> None:
        for fig in ast.iter_child_nodes(nodo):
            if isinstance(fig, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # il nome di classe diverso (ScalperStrategy / TennisScalperStrategy)
                # non conta: si confrontano i metodi per nome semplice
                nome = prefisso + fig.name
                corpo = righe[fig.lineno - 1: fig.end_lineno]
                out[nome] = (fig.lineno, fig.end_lineno, righe_di_codice(corpo))
                visita(fig, nome + ".")
            elif isinstance(fig, ast.ClassDef):
                visita(fig, prefisso)

    visita(albero, "")
    return out


def similitudine(a: List[str], b: List[str]) -> Tuple[int, float, float, float]:
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    uguali = sum(bl.size for bl in sm.get_matching_blocks())
    return (uguali, uguali / max(1, len(a)), uguali / max(1, len(b)), sm.ratio())


def main() -> None:
    for pa, pb in COPPIE:
        ra, rb = leggi(pa), leggi(pb)
        ca, cb = righe_di_codice(ra), righe_di_codice(rb)
        n, pa_, pb_, rt = similitudine(ca, cb)
        print("=" * 100)
        print("A = %s : %d righe (wc -l ~ %d), %d di codice" % (pa, len(ra) - 1, len(ra) - 1, len(ca)))
        print("B = %s : %d righe (wc -l ~ %d), %d di codice" % (pb, len(rb) - 1, len(rb) - 1, len(cb)))
        print("righe di codice uguali (blocchi difflib): %d  -> %.1f%% di A, %.1f%% di B, ratio %.3f"
              % (n, 100 * pa_, 100 * pb_, rt))
        if pa.endswith("scalper_bot.py"):
            fa, fb = funzioni(pa), funzioni(pb)
            comuni = sorted(set(fa) & set(fb), key=lambda k: fa[k][0])
            print("funzioni con lo stesso nome: %d (A ne ha %d, B ne ha %d)"
                  % (len(comuni), len(fa), len(fb)))
            print("%-46s %12s %12s %6s %9s" % ("funzione", "A righe(cod)", "B righe(cod)", "ratio", "A:riga B:riga"))
            tot_a = tot_b = pes = 0.0
            for k in comuni:
                a0, a1, ca2 = fa[k]
                b0, b1, cb2 = fb[k]
                ratio = difflib.SequenceMatcher(None, ca2, cb2, autojunk=False).ratio()
                tot_a += len(ca2)
                tot_b += len(cb2)
                pes += ratio * (len(ca2) + len(cb2)) / 2.0
                print("%-46s %12d %12d %6.2f %5d:%-5d" % (k[:46], len(ca2), len(cb2), ratio, a0, b0))
            print("-- somma righe(cod) delle funzioni omonime: A=%d B=%d; ratio medio pesato %.3f"
                  % (tot_a, tot_b, pes / max(1.0, (tot_a + tot_b) / 2.0)))
            solo_a = [k for k in fa if k not in fb]
            solo_b = [k for k in fb if k not in fa]
            print("solo in A (calcio):", ", ".join("%s(%d)" % (k, fa[k][0]) for k in solo_a))
            print("solo in B (tennis):", ", ".join("%s(%d)" % (k, fb[k][0]) for k in solo_b))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
