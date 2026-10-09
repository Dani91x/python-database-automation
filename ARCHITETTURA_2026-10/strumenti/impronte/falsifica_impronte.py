"""T0C passo 6: FALSIFICAZIONE delle impronte della strategia (rieseguibile).

Per ogni bot, su una COPIA dei suoi file in una cartella temporanea (il
repository non si tocca):
  1. identita' (copia identica)                  -> 0 differenze (verde);
  2. solo commenti e docstring aggiunti           -> 0 differenze (verde: l'impronta
     ignora cio' che non e' logica);
  3. UNA soglia cambiata (il primo numero di una tabella di parametri di primo
     livello DEFAULT/PARAM/SPEC, o la prima costante numerica di primo livello
     se il bot non ne ha): float +0.01, intero +1  -> ROSSO sulla voce giusta;
  4. una CONDIZIONE invertita (il primo ``<`` di una funzione di strategia
     diventa ``<=``)                                -> ROSSO sulla funzione.
Exit code 0 = tutte le attese rispettate.

Uso (dalla radice del repository):
    python -I ARCHITETTURA_2026-10/strumenti/impronte/falsifica_impronte.py
ASCII-only.
"""
import ast
import os
import shutil
import subprocess
import sys
import tempfile

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
import impronta_strategia_bot as IMP  # noqa: E402


def _copia(radice_tmp, files):
    for f in files:
        dst = os.path.join(radice_tmp, f)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(f, dst)


def _confronta(bot, radice_tmp):
    out = subprocess.run([sys.executable, "-I", os.path.join(QUI, "impronta_strategia_bot.py"),
                          "confronta", bot, "--radice", radice_tmp, "--cartella", QUI],
                         capture_output=True, text=True)
    return out.returncode, out.stdout.strip()


def _sostituisci(percorso, riga, col, fine, nuovo):
    righe = open(percorso, encoding="utf-8").read().split("\n")
    r = righe[riga - 1]
    righe[riga - 1] = r[:col] + nuovo + r[fine:]
    open(percorso, "w", encoding="utf-8", newline="\n").write("\n".join(righe))


def _soglia(files):
    """(file, riga, col, fine, nuovo, voce attesa) della prima soglia numerica."""
    for f in files:
        tree = ast.parse(open(f, encoding="utf-8").read())
        for n in tree.body:
            if isinstance(n, (ast.Assign, ast.AnnAssign)):
                nome = IMP._nome_assegnato(n)
                if nome and IMP.RE_TABELLA.search(nome) and isinstance(n.value, ast.Dict):
                    for k, v in zip(n.value.keys, n.value.values):
                        if isinstance(v, ast.Constant) and type(v.value) in (int, float) \
                                and v.lineno == v.end_lineno:
                            nuovo = repr(v.value + (0.01 if isinstance(v.value, float) else 1))
                            return f, v.lineno, v.col_offset, v.end_col_offset, nuovo, \
                                "%s[%s]" % (nome, k.value)
    for f in files:
        tree = ast.parse(open(f, encoding="utf-8").read())
        for n in tree.body:
            if isinstance(n, (ast.Assign, ast.AnnAssign)) and isinstance(n.value, ast.Constant) \
                    and type(n.value.value) in (int, float):
                v = n.value
                nuovo = repr(v.value + (0.01 if isinstance(v.value, float) else 1))
                return f, v.lineno, v.col_offset, v.end_col_offset, nuovo, IMP._nome_assegnato(n)
    return None


def _condizione(files):
    """(file, riga, col, fine, '<=', funzione) del primo ``a < b`` in una funzione."""
    for f in files:
        sorgente = open(f, encoding="utf-8").read().split("\n")
        tree = ast.parse("\n".join(sorgente))
        for n in tree.body:
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for c in ast.walk(n):
                if isinstance(c, ast.Compare) and len(c.ops) == 1 and isinstance(c.ops[0], ast.Lt) \
                        and c.left.end_lineno == c.comparators[0].lineno:
                    riga = sorgente[c.left.end_lineno - 1]
                    a, b = c.left.end_col_offset, c.comparators[0].col_offset
                    tratto = riga[a:b]
                    if tratto.strip() == "<":
                        i = a + tratto.index("<")
                        return f, c.left.end_lineno, i, i + 1, "<=", n.name
    return None


def main():
    esiti = []
    for bot in sorted(IMP.BOT):
        files = list(IMP.BOT[bot]["file"]) + sorted(IMP.BOT[bot]["nomi"])
        with tempfile.TemporaryDirectory() as tmp:
            _copia(tmp, files)
            rc, out = _confronta(bot, tmp)
            esiti.append((bot, "identita'", rc == 0, out))
            # commenti e docstring
            f0 = os.path.join(tmp, files[0])
            testo = open(f0, encoding="utf-8").read()
            open(f0, "w", encoding="utf-8", newline="\n").write(
                '"""docstring aggiunta dalla falsificazione"""\n# commento aggiunto\n' + testo)
            rc, out = _confronta(bot, tmp)
            esiti.append((bot, "commenti e docstring", rc == 0, out))
        with tempfile.TemporaryDirectory() as tmp:
            _copia(tmp, files)
            s = _soglia(files)
            f, riga, col, fine, nuovo, voce = s
            _sostituisci(os.path.join(tmp, f), riga, col, fine, nuovo)
            rc, out = _confronta(bot, tmp)
            esiti.append((bot, "soglia %s:%d -> %s (%s)" % (f, riga, nuovo, voce),
                          rc == 1 and voce in out, out))
        with tempfile.TemporaryDirectory() as tmp:
            _copia(tmp, files)
            c = _condizione(IMP.BOT[bot]["file"])
            f, riga, col, fine, nuovo, fn = c
            _sostituisci(os.path.join(tmp, f), riga, col, fine, nuovo)
            rc, out = _confronta(bot, tmp)
            esiti.append((bot, "condizione %s:%d '<' -> '<=' (%s)" % (f, riga, fn),
                          rc == 1 and ("'%s')" % fn) in out, out))
    ko = 0
    for bot, prova, ok, out in esiti:
        print("%s %-15s %s" % ("OK" if ok else "KO", bot, prova))
        print("      %s" % out[:300])
        ko += 0 if ok else 1
    print("ESITO: %d prove, %d attese NON rispettate" % (len(esiti), ko))
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main())
