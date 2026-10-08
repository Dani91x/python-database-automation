"""Strumento di misura H: gli scenari dichiarati da ogni adattatore (lettura via AST, nessun import).

Uso: python -I ARCHITETTURA_2026-10/strumenti/h_scenari_per_bot.py
Per ogni file di replay estrae il dizionario `SCENARI_DESCRITTI` (chiavi stringa, o costanti
SCENARIO_* risolte nello stesso file) e stampa numero e nomi; poi la matrice scenario x bot.
ASCII-only; commenti in italiano.
"""
import ast

FILE = {
    "mike": "Betfair/mike/tools/replay_registrazioni.py",
    "omega": "Betfair/omega/tools/replay_registrazioni.py",
    "safe": "Betfair/safe_strategy/tools/replay_registrazioni.py",
    "safe_tennis": "Betfair/safe_strategy/tools/replay_tennis.py",
    "scalper": "Betfair/stream/scalper/tools/replay_registrazioni.py",
    "tennis": "Betfair/stream/tennis_live/tools/replay_bot.py",
}


def chiavi(percorso):
    sorgente = open(percorso, encoding="utf-8").read()
    albero = ast.parse(sorgente)
    costanti = {}
    for n in albero.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            if isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
                costanti[n.targets[0].id] = n.value.value
    trovate = None
    for n in albero.body:
        bersaglio = None
        valore = None
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            bersaglio, valore = n.target.id, n.value
        elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            bersaglio, valore = n.targets[0].id, n.value
        if bersaglio == "SCENARI_DESCRITTI" and valore is not None:
            trovate = (n.lineno, valore)
    if trovate is None:
        return None, []
    riga, valore = trovate
    nomi = []
    if isinstance(valore, ast.Dict):
        for k in valore.keys:
            if isinstance(k, ast.Constant):
                nomi.append(str(k.value))
            elif isinstance(k, ast.Name):
                nomi.append(costanti.get(k.id, "<%s>" % k.id))
            elif k is None:
                nomi.append("<**espansione>")
            else:
                nomi.append("<%s>" % ast.unparse(k))
    else:
        nomi.append("<non un dict letterale: %s>" % type(valore).__name__)
    return riga, nomi


if __name__ == "__main__":
    tutti = {}
    for bot, f in FILE.items():
        riga, nomi = chiavi(f)
        tutti[bot] = nomi
        print("%-12s %s:%s  %d scenari" % (bot, f, riga, len(nomi)))
        print("   " + ", ".join(nomi))
    print()
    nomi_unici = sorted({n for v in tutti.values() for n in v})
    print("scenari distinti: %d; presenti in >=2 adattatori:" % len(nomi_unici))
    for n in nomi_unici:
        dove = [b for b, v in tutti.items() if n in v]
        if len(dove) >= 2:
            print("   %-34s %s" % (n, ",".join(dove)))
