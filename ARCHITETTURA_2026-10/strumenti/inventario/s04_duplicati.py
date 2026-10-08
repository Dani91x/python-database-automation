"""Sezione 4 - duplicazioni: funzioni con lo stesso nome in piu' file (>= 3 copie), confronto testuale
(difflib sulle righe normalizzate) e file tracciati identici (stesso hash).

Normalizzazione: via commenti, righe vuote, docstring iniziale, spazi a fine riga; indentazione
ridotta a quella relativa. Classi: IDENTICHE (testo normalizzato uguale), QUASI (rapporto >= 0.90
con la copia di riferimento), DIVERSE (< 0.90).
Uscite: uscite/s04_funzioni_duplicate.tsv, s04_dettaglio_copie.tsv, s04_file_identici.txt, s04_riepilogo.txt
Uso: python s04_duplicati.py
"""
from __future__ import annotations

import ast
import collections
import difflib
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comune as c  # noqa: E402
from s01_righe import categoria  # noqa: E402

PROD = ("py_codice_Betfair", "py_codice_radice", "py_codice_cartelle_radice")
NOMI_BREVI_DA_SEGNALARE = {"read_book", "process_market_book", "_now_iso", "log"}


def normalizza(segmento: str) -> list[str]:
    righe = []
    for r in segmento.splitlines():
        s = r.strip()
        if not s or s.startswith("#"):
            continue
        righe.append(s)
    # via la docstring iniziale (righe dopo il def fino alla chiusura)
    out = []
    in_doc = False
    visti_def = False
    for i, s in enumerate(righe):
        if not visti_def:
            out.append(s)
            if s.endswith(":") or s.rstrip().endswith("):") or s.endswith(") -> None:"):
                visti_def = True
                if i + 1 < len(righe) and righe[i + 1].startswith(('"""', "'''")):
                    in_doc = True
            continue
        if in_doc:
            if s.endswith(('"""', "'''")) and (len(s) > 3 or out and True):
                in_doc = False
                # la prima riga della docstring gia' saltata: controlla se singola riga
            continue
        out.append(s)
    return out


def main() -> int:
    tracciati = c.file_tracciati()
    py = [p for p in tracciati if p.endswith(".py")]
    cat = {p: categoria(p) for p in py}
    funz: dict[str, list[tuple[str, int, int, list[str], str]]] = collections.defaultdict(list)
    for p in py:
        testo = c.leggi_testo(p)
        if testo is None:
            continue
        try:
            albero = ast.parse(testo)
        except (SyntaxError, ValueError):
            continue
        righe_src = testo.splitlines()
        # classi che contengono ogni funzione (per distinguere metodi)
        padre_classe: dict[ast.AST, str] = {}
        for n in ast.walk(albero):
            if isinstance(n, ast.ClassDef):
                for f in n.body:
                    if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        padre_classe[f] = n.name
        for n in ast.walk(albero):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fine = getattr(n, "end_lineno", n.lineno)
                seg = "\n".join(righe_src[n.lineno - 1: fine])
                funz[n.name].append((p, n.lineno, fine - n.lineno + 1, normalizza(seg), padre_classe.get(n, "")))

    def solo(lst, filtro):
        return [x for x in lst if filtro(cat[x[0]])]

    righe_tsv = ["nome\tcopie_prod\tfile_prod\tcopie_tutte\tcopie_test\tcopie_strum_audit\trighe_totali_copie_prod\tcorpi_distinti\tgruppi_quasi_identici\trapporto_min\tgiudizio"]
    dettaglio = ["nome\tfile\triga\tlunghezza\tclasse\tcategoria\tgruppo\trapporto_con_riferimento"]
    riepilogo: list[str] = []
    candidati = []
    for nome, lst in funz.items():
        lp = solo(lst, lambda ca: ca in PROD)
        if len(lp) >= 3 or nome in NOMI_BREVI_DA_SEGNALARE:
            candidati.append((nome, lp, lst))
    candidati.sort(key=lambda x: (-len(x[1]), x[0]))
    for nome, lp, lst in candidati:
        # raggruppa le copie di produzione per somiglianza con il capogruppo (greedy)
        gruppi: list[list[tuple]] = []
        rapporti: dict[tuple, float] = {}
        for item in lp:
            collocato = False
            for g in gruppi:
                cap = g[0]
                if cap[3] == item[3]:
                    r = 1.0
                else:
                    r = difflib.SequenceMatcher(None, cap[3], item[3], autojunk=False).ratio() if len(cap[3]) * len(item[3]) < 4_000_000 else 0.0
                if r >= 0.90:
                    g.append(item)
                    rapporti[(item[0], item[1])] = r
                    collocato = True
                    break
            if not collocato:
                gruppi.append([item])
                rapporti[(item[0], item[1])] = 1.0
        corpi = {"\n".join(x[3]) for x in lp}
        rmin = min(rapporti.values()) if rapporti else 1.0
        tot = sum(x[2] for x in lp)
        if len(corpi) == 1 and len(lp) > 1:
            giud = "IDENTICHE"
        elif len(gruppi) == 1:
            giud = "QUASI_IDENTICHE"
        else:
            giud = f"DIVERSE ({len(gruppi)} gruppi)"
        righe_tsv.append("\t".join(map(str, [
            nome, len(lp), len({x[0] for x in lp}), len(lst), len(solo(lst, lambda ca: ca == "py_test")),
            len(solo(lst, lambda ca: ca in ("py_strumenti", "py_script_audit"))), tot, len(corpi), len(gruppi), f"{rmin:.2f}", giud])))
        for gi, g in enumerate(gruppi):
            for item in g:
                dettaglio.append("\t".join(map(str, [nome, item[0], item[1], item[2], item[4], cat[item[0]], gi, f"{rapporti[(item[0], item[1])]:.2f}"])))
    c.scrivi("s04_funzioni_duplicate.tsv", "\n".join(righe_tsv) + "\n")
    c.scrivi("s04_dettaglio_copie.tsv", "\n".join(dettaglio) + "\n")

    # file identici
    per_hash: dict[str, list[str]] = collections.defaultdict(list)
    for p in tracciati:
        d = c.leggi_bytes(p)
        if d is None or len(d) < 400 or c.e_binario(d):
            continue
        if d.count(b"\n") < 30:
            continue
        per_hash[hashlib.sha1(d).hexdigest()].append(p)
    ident = [(h, l) for h, l in per_hash.items() if len(l) > 1]
    out_i = [f"gruppi di file tracciati con contenuto identico (>= 30 righe): {len(ident)}"]
    for h, l in sorted(ident, key=lambda x: -len(x[1])):
        n = c.leggi_bytes(l[0]).count(b"\n")
        out_i.append(f"-- {len(l)} copie, {n} righe ciascuna:")
        out_i.extend("     " + x for x in sorted(l))
    c.scrivi("s04_file_identici.txt", "\n".join(out_i) + "\n")

    # riepilogo
    r = []
    r.append(f"nomi di funzione con >= 3 copie nel codice di PRODUZIONE: {sum(1 for _, lp, _ in candidati if len(lp) >= 3)}")
    r.append("")
    r.append("== nome | copie prod | file | tutte le copie (anche test/strum/audit) | righe totali copie prod | giudizio ==")
    for riga in righe_tsv[1:46]:
        x = riga.split("\t")
        r.append(f"{x[0]:<30} prod={x[1]:>3} file={x[2]:>3} tutte={x[3]:>4} righe={x[6]:>5}  {x[10]} (rapporto min {x[9]})")
    r.append("")
    r.append("== i 4 nomi del brief (copie in produzione / in tutto il repo) ==")
    for nome in ("read_book", "process_market_book", "_now_iso", "log"):
        lst = funz.get(nome, [])
        lp = solo(lst, lambda ca: ca in PROD)
        r.append(f"{nome:<22} produzione={len(lp):>3} (file {len({x[0] for x in lp})}), test={len(solo(lst, lambda ca: ca == 'py_test'))}, strumenti/audit={len(solo(lst, lambda ca: ca in ('py_strumenti', 'py_script_audit')))}, tutte={len(lst)}")
    r.append("")
    r.append(f"gruppi di file identici: {len(ident)} (vedi s04_file_identici.txt)")
    c.scrivi("s04_riepilogo.txt", "\n".join(r) + "\n")
    print("\n".join(r[:60]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
