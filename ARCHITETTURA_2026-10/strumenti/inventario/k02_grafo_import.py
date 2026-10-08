"""K02 - grafo degli import dei file Python tracciati e moduli mai importati.

Sola lettura. Usa `ast` sui file tracciati (nessun codice viene eseguito).
Per ogni modulo .py tracciato calcola: righe, importatori NON test, importatori test, se ha
`if __name__ == "__main__"`, se il suo nome compare in file non-Python (bat/ps1/yml/json/js/md...).
Uscite (uscite/):
  k02_moduli.tsv            una riga per modulo
  k02_import_dinamici.txt   importlib / __import__ / import_module / runpy / stringhe "python -m ..."
Uso: python k02_grafo_import.py
"""
from __future__ import annotations

import ast
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comune as c  # noqa: E402


def nome_modulo(rel: str) -> str:
    """Nome puntato del modulo (il percorso con / sostituito da .)."""
    p = rel[:-3]
    if p.endswith("/__init__"):
        p = p[: -len("/__init__")]
    return p.replace("/", ".")


def main() -> int:
    tracciati = c.file_tracciati()
    py = [f for f in tracciati if f.endswith(".py")]
    mod_di_file = {f: nome_modulo(f) for f in py}
    file_di_mod = {m: f for f, m in mod_di_file.items()}

    importatori: dict[str, set[str]] = collections.defaultdict(set)
    ha_main: dict[str, bool] = {}
    righe: dict[str, int] = {}
    dinamici: list[str] = []
    testi: dict[str, str] = {}

    def prefisso_noto(cand: str) -> str | None:
        while cand:
            if cand in file_di_mod:
                return cand
            if "." not in cand:
                return None
            cand = cand.rsplit(".", 1)[0]
        return None

    def risolvi(nome: str, da: str) -> list[str]:
        """Moduli tracciati a cui puo' riferirsi `nome` importato dal file `da`."""
        r = prefisso_noto(nome)
        if r:
            return [r]
        # import "locale": script lanciato con la propria cartella in sys.path
        m_da = mod_di_file[da]
        cartella = m_da.rsplit(".", 1)[0] if "." in m_da else ""
        if da.endswith("/__init__.py"):
            cartella = m_da
        if cartella:
            r = prefisso_noto(f"{cartella}.{nome}")
            if r:
                return [r]
        return []

    for f in py:
        d = c.leggi_bytes(f)
        if d is None:
            continue
        righe[f] = c.righe_wc(d)
        t = d.decode("utf-8-sig", errors="replace")  # BOM: senza utf-8-sig 16 file davano falsi SyntaxError
        testi[f] = t
        try:
            albero = ast.parse(t)
        except SyntaxError:
            dinamici.append(f"{f}: SYNTAXERROR")
            continue
        ha_main[f] = bool(re.search(r"__name__\s*==\s*['\"]__main__['\"]", t))
        m_f = mod_di_file[f]
        pacchetto = m_f.rsplit(".", 1)[0] if "." in m_f else ""
        if f.endswith("/__init__.py"):
            pacchetto = m_f
        for n in ast.walk(albero):
            if isinstance(n, ast.Import):
                for a in n.names:
                    for m in risolvi(a.name, f):
                        importatori[m].add(f)
            elif isinstance(n, ast.ImportFrom):
                if n.level:
                    parti = pacchetto.split(".") if pacchetto else []
                    if n.level > 1:
                        parti = parti[: len(parti) - (n.level - 1)]
                    base = ".".join(parti + ([n.module] if n.module else []))
                else:
                    base = n.module or ""
                if base:
                    for m in risolvi(base, f):
                        importatori[m].add(f)
                    for a in n.names:
                        sub = f"{base}.{a.name}"
                        r = risolvi(sub, f)
                        for m in r:
                            importatori[m].add(f)
                else:
                    for a in n.names:
                        for m in risolvi(a.name, f):
                            importatori[m].add(f)
            elif isinstance(n, ast.Call):
                fn = n.func
                nome_f = ""
                if isinstance(fn, ast.Name):
                    nome_f = fn.id
                elif isinstance(fn, ast.Attribute):
                    nome_f = fn.attr
                if nome_f in ("import_module", "__import__", "spec_from_file_location", "run_module", "run_path", "find_spec"):
                    dinamici.append(f"{f}:{n.lineno}: chiamata {nome_f}(...)")

    # riferimenti non-py: nome file o modulo nei file di avvio / documenti vivi
    non_py_testi: dict[str, str] = {}
    estensioni = (".bat", ".ps1", ".yml", ".yaml", ".json", ".js", ".ts", ".tsx", ".cmd", ".sh", ".toml", ".cfg", ".txt", ".md", ".sql")
    for f in tracciati:
        if f.endswith(".py"):
            continue
        if Path(f).suffix.lower() not in estensioni:
            continue
        if f.startswith(("AUDIT_", "_AUDIT_", "ARCHITETTURA_2026-10/")) or f.endswith("package-lock.json"):
            continue
        t = c.leggi_testo(f)
        if t is not None and len(t) < 5_000_000:
            non_py_testi[f] = t

    # indice dei riferimenti: per ogni file non-py, i nomi "xxx.py" e i nomi puntati citati
    tok_file: dict[str, set[str]] = collections.defaultdict(set)
    tok_mod: dict[str, set[str]] = collections.defaultdict(set)
    pat_py = re.compile(r"[\w][\w.-]*\.py")
    pat_dot = re.compile(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+")
    for g, t in non_py_testi.items():
        for x in pat_py.findall(t):
            tok_file[x.rsplit("/", 1)[-1]].add(g)
        for x in pat_dot.findall(t):
            tok_mod[x].add(g)
    righe_out = ["modulo	file	righe	test	n_imp_non_test	n_imp_test	has_main	riferito_da_non_py"]
    for f in py:
        m = mod_di_file[f]
        imp = importatori.get(m, set()) - {f}
        non_test = [x for x in imp if not c.e_test_py(x)]
        test = [x for x in imp if c.e_test_py(x)]
        nome_file = f.rsplit("/", 1)[-1]
        rif: set[str] = set()
        if nome_file != "__init__.py":
            rif |= tok_file.get(nome_file, set())
            if "." in m:
                rif |= tok_mod.get(m, set())
        rif_l = sorted(rif)
        righe_out.append("	".join([
            m, f, str(righe.get(f, 0)), "1" if c.e_test_py(f) else "0", str(len(non_test)), str(len(test)),
            "1" if ha_main.get(f) else "0", ";".join(rif_l[:6]) + (f";+{len(rif_l) - 6}" if len(rif_l) > 6 else ""),
        ]))
    c.scrivi("k02_moduli.tsv", "\n".join(righe_out) + "\n")

    # stringhe con nome di modulo (python -m X, "-m", import_module su stringa)
    pat_m = re.compile(r"""(?:["']-m["']\s*,\s*["']([\w.]+)["']|python(?:\.exe)?\s+-m\s+([\w.]+)|import_module\(\s*f?["']([\w.{}]+)["'])""")
    for f, t in list(testi.items()) + list(non_py_testi.items()):
        if f.startswith(("AUDIT_", "_AUDIT_")):
            continue
        for i, riga in enumerate(t.splitlines(), 1):
            for mm in pat_m.finditer(riga):
                dinamici.append(f"{f}:{i}: stringa-modulo {mm.group(1) or mm.group(2) or mm.group(3)}")
    c.scrivi("k02_import_dinamici.txt", "\n".join(dinamici) + "\n")
    print("moduli", len(py), "dinamici", len(dinamici))
    return 0


if __name__ == "__main__":
    sys.exit(main())
