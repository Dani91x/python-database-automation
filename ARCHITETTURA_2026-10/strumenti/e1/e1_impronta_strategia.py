"""E1: impronta della LOGICA di strategia di Mike (garanzia che non cambi quando si sposta o si riduce il guscio).
Per ogni def/class di primo livello (e metodi) di engine.py, feed.py, dossier.py calcola lo SHA-1 dell'AST SENZA
docstring, commenti e numeri di riga; per config.py fa l'impronta di PARAM_SPEC (chiavi, default, tipo, limiti, scelte).
Uso: python -I e1_impronta_strategia.py [scrivi|confronta] [file.tsv]. Solo lettura statica. ASCII-only."""
import ast, hashlib, sys
FILES = ["Betfair/mike/engine.py", "Betfair/mike/feed.py", "Betfair/mike/dossier.py"]

def senza_doc(nodo):
    for n in ast.walk(nodo):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)) and n.body:
            f = n.body[0]
            if isinstance(f, ast.Expr) and isinstance(getattr(f, "value", None), ast.Constant) and isinstance(f.value.value, str):
                n.body = n.body[1:] or [ast.Pass()]
    return nodo

def impronta(nodo):
    return hashlib.sha1(ast.dump(senza_doc(nodo), include_attributes=False).encode("utf-8")).hexdigest()[:12]

def calcola():
    righe = []
    for f in FILES:
        tree = ast.parse(open(f, encoding="utf-8").read())
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                righe.append((f.split("/")[-1], n.name, impronta(n)))
            elif isinstance(n, (ast.Assign, ast.AnnAssign)):
                tgt = n.targets[0] if isinstance(n, ast.Assign) else n.target
                if isinstance(tgt, ast.Name):
                    righe.append((f.split("/")[-1], tgt.id, impronta(n)))
    tree = ast.parse(open("Betfair/mike/config.py", encoding="utf-8").read())
    for n in tree.body:
        if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "PARAM_SPEC":
            righe.append(("config.py", "PARAM_SPEC", impronta(n)))
            for k, v in zip(n.value.keys, n.value.values):
                righe.append(("config.py", "PARAM:" + k.value, impronta(v)))
    return righe

if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "scrivi"
    path = sys.argv[2] if len(sys.argv) > 2 else "ARCHITETTURA_2026-10/strumenti/e1/e1_impronta_strategia.tsv"
    r = calcola()
    if modo == "scrivi":
        open(path, "w", encoding="utf-8", newline="\n").write("\n".join("\t".join(x) for x in r) + "\n")
        print("scritte", len(r), "impronte in", path)
    else:
        vecchie = {(a, b): c for a, b, c in (l.split("\t") for l in open(path, encoding="utf-8").read().split("\n") if l)}
        nuove = {(a, b): c for a, b, c in r}
        diff = [k for k in set(vecchie) | set(nuove) if vecchie.get(k) != nuove.get(k)]
        print("differenze:", len(diff), sorted(diff)[:20])
        sys.exit(1 if diff else 0)
