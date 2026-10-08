"""D_gemelle_servizi.py - strumento di misura usa-e-getta (scheda D, 08/10/2026).

Legge (SOLO in lettura, mai importa) i file dei servizi dei bot, estrae con `ast`
le funzioni di primo livello e i metodi, e:
  1) elenca i nomi presenti in almeno due servizi con la somiglianza difflib del
     corpo (commenti e docstring tolti, spazi normalizzati);
  2) stampa le righe (end_lineno - lineno + 1) di un elenco di funzioni "scheletro".
Uso: python -I D_gemelle_servizi.py gemelle | righe <file.json> | coppie chiaveA:nome=chiaveB:nome ...
ASCII-only, nessuna scrittura.
"""
import ast
import difflib
import io
import itertools
import os
import sys
import tokenize

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FILE = {
    "mike": "Betfair/mike/service.py",
    "omega": "Betfair/omega/omega_service.py",
    "safe": "Betfair/safe_strategy/bot_service.py",
    "scalper_svc": "Betfair/stream/scalper/scalper_service.py",
    "scalper_sess": "Betfair/stream/scalper/scalper_session.py",
    "tennis_svc": "Betfair/stream/tennis_live/tennis_bot_service.py",
    "tennis_run": "Betfair/stream/tennis_live/tennis_runner.py",
    "scanner": "Betfair/safe_strategy/service.py",
}


def carica(chiave):
    p = os.path.join(RADICE, FILE[chiave])
    with open(p, encoding="utf-8") as f:
        testo = f.read()
    return testo, ast.parse(testo)


def funzioni(testo, albero):
    righe = testo.splitlines()
    out = {}
    for nodo in ast.walk(albero):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.setdefault(nodo.name, []).append(nodo)
    return righe, out


def corpo_pulito(righe, nodo):
    """Il sorgente della funzione senza commenti, senza docstring, spazi normalizzati."""
    sorgente = "\n".join(righe[nodo.lineno - 1:nodo.end_lineno])
    # via i commenti con tokenize
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(sorgente + "\n").readline))
        senza = tokenize.untokenize([t for t in toks if t.type != tokenize.COMMENT])
    except (tokenize.TokenError, IndentationError):
        senza = sorgente
    # via la docstring (primo statement stringa)
    try:
        sub = ast.parse("\n".join(l for l in senza.splitlines()))
        f = sub.body[0]
        if f.body and isinstance(f.body[0], ast.Expr) and isinstance(getattr(f.body[0], "value", None), ast.Constant) \
                and isinstance(f.body[0].value.value, str):
            ls = senza.splitlines()
            senza = "\n".join(ls[:f.body[0].lineno - 1] + ls[f.body[0].end_lineno:])
    except SyntaxError:
        pass
    return "\n".join(" ".join(l.split()) for l in senza.splitlines() if l.strip())


def gemelle():
    dati = {}
    for k in FILE:
        t, a = carica(k)
        r, f = funzioni(t, a)
        dati[k] = (r, f)
    nomi = {}
    for k, (r, f) in dati.items():
        for n, nodi in f.items():
            nomi.setdefault(n, []).append(k)
    print("nome | file | righe | somiglianza (difflib, corpo pulito)")
    for n, ks in sorted(nomi.items()):
        if len(ks) < 2:
            continue
        coppie = []
        for a, b in itertools.combinations(ks, 2):
            na = dati[a][1][n][0]
            nb = dati[b][1][n][0]
            ca, cb = corpo_pulito(dati[a][0], na), corpo_pulito(dati[b][0], nb)
            rat = difflib.SequenceMatcher(None, ca, cb, autojunk=False).ratio() if len(ca) < 6000 and len(cb) < 6000 \
                else difflib.SequenceMatcher(None, ca.splitlines(), cb.splitlines(), autojunk=False).ratio()
            coppie.append("%s~%s=%.2f" % (a, b, rat))
        righe = ",".join("%s:%d(%d)" % (k, dati[k][1][n][0].lineno,
                                        dati[k][1][n][0].end_lineno - dati[k][1][n][0].lineno + 1) for k in ks)
        print("%s | %s | %s" % (n, righe, " ".join(coppie)))


def righe_di(elenco):
    """elenco: dict chiave -> lista nomi. Stampa righe per funzione e totale."""
    for k, nomi in elenco.items():
        t, a = carica(k)
        r, f = funzioni(t, a)
        tot = 0
        print("== %s (%s)" % (k, FILE[k]))
        for n in nomi:
            if n not in f:
                print("   %-40s ASSENTE" % n)
                continue
            nd = f[n][0]
            ln = nd.end_lineno - nd.lineno + 1
            tot += ln
            print("   %-40s %5d  (%d-%d)" % (n, ln, nd.lineno, nd.end_lineno))
        print("   TOTALE %d" % tot)


if __name__ == "__main__" and (len(sys.argv) < 2 or sys.argv[1] in ("gemelle", "righe")):
    modo = sys.argv[1] if len(sys.argv) > 1 else "gemelle"
    if modo == "gemelle":
        gemelle()
    else:
        import json
        with open(sys.argv[2], encoding="utf-8") as fh:
            righe_di(json.load(fh))


def coppie(specifiche):
    """specifiche: lista di 'chiaveA:nomeA=chiaveB:nomeB'. Somiglianza e righe."""
    cache = {}
    for sp in specifiche:
        a, b = sp.split("=")
        res = []
        for lato in (a, b):
            k, n = lato.split(":")
            if k not in cache:
                t, ast_ = carica(k)
                cache[k] = funzioni(t, ast_)
            r, f = cache[k]
            if n not in f:
                res.append((lato, None, None))
                continue
            nd = f[n][0]
            res.append((lato, corpo_pulito(r, nd), "%d(%d)" % (nd.lineno, nd.end_lineno - nd.lineno + 1)))
        if res[0][1] is None or res[1][1] is None:
            print("%s: ASSENTE" % sp)
            continue
        rat = difflib.SequenceMatcher(None, res[0][1].splitlines(), res[1][1].splitlines(), autojunk=False).ratio()
        print("%s  righe %s vs %s  somiglianza(righe)=%.2f" % (sp, res[0][2], res[1][2], rat))


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "coppie":
    coppie(sys.argv[2:])
