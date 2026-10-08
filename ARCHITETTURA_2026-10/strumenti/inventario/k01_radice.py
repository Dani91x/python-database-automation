"""K01 - cartelle e file di radice: righe tracciate, ultimo commit, presenza su disco.

Sola lettura: usa `git ls-files` e `git log -1`. Scrive SOLO uscite/k01_radice.tsv.
Colonne: voce, tipo, file_tracciati, righe_py, righe_py_test, righe_testo_altro, ultimo_commit_data,
ultimo_commit_hash, ultimo_commit_oggetto, file_su_disco_non_tracciati.
Uso: python k01_radice.py
"""
from __future__ import annotations

import collections
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comune as c  # noqa: E402


def main() -> int:
    tracciati = c.file_tracciati()
    voci: dict[str, list[str]] = collections.defaultdict(list)
    for rel in tracciati:
        parti = rel.split("/")
        voci[parti[0]].append(rel)
    righe_out = ["voce\ttipo\tfile_tracciati\trighe_py\trighe_py_test\trighe_testo_altro\tdata\thash\toggetto\tdisco_non_tracciati"]
    for voce in sorted(voci):
        files = voci[voce]
        tipo = "cartella" if any("/" in f for f in files) else "file"
        py = pyt = alt = 0
        for f in files:
            d = c.leggi_bytes(f)
            if d is None or c.e_binario(d):
                continue
            n = c.righe_wc(d)
            if f.endswith(".py"):
                if c.e_test_py(f):
                    pyt += n
                else:
                    py += n
            else:
                alt += n
        log = c.git("log", "-1", "--format=%cs\t%h\t%s", "--", voce).strip()
        data, h, ogg = (log.split("\t", 2) + ["", "", ""])[:3] if log else ("", "", "")
        # file su disco non tracciati (solo per le cartelle)
        extra = ""
        p = c.RADICE / voce
        if p.is_dir():
            tr = set(files)
            n_extra = 0
            for rad, dirs, fn in os.walk(p):
                dirs[:] = [d for d in dirs if d not in ("__pycache__", ".pytest_cache", "node_modules")]
                for nome in fn:
                    rel = (Path(rad) / nome).relative_to(c.RADICE).as_posix()
                    if rel not in tr:
                        n_extra += 1
            extra = str(n_extra)
        righe_out.append("\t".join([voce, tipo, str(len(files)), str(py), str(pyt), str(alt), data, h, ogg.replace("\t", " "), extra]))
    # cartelle presenti su disco ma con 0 file tracciati
    for q in sorted(c.RADICE.iterdir()):
        if q.name in voci or q.name in (".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"):
            continue
        n = sum(len(fn) for _, _, fn in os.walk(q)) if q.is_dir() else 1
        righe_out.append("\t".join([q.name, "NON_TRACCIATA", "0", "0", "0", "0", "", "", "", str(n)]))
    c.scrivi("k01_radice.tsv", "\n".join(righe_out) + "\n")
    print("ok", len(righe_out) - 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
