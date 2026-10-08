"""Sezione 2 - grafo degli import Python interni, moduli non importati, librerie esterne per file.

Legge solo i file .py tracciati (git ls-files) con `ast`; non esegue e non importa nulla.
Uscite (in uscite/):
  s02_moduli.tsv      una riga per modulo .py: categoria, righe, n. importatori per tipo, importa (n.),
                      riferimenti per stringa, main, esterni, primi importatori
  s02_archi.tsv       archi interni  importatore -> importato  (solo codice di produzione e strumenti)
  s02_esterni.tsv     per file e per libreria esterna: file:riga della prima importazione
  s02_morti.txt       candidati morti con la prova (comandi rieseguibili)
  s02_riepilogo.txt   numeri di sintesi
Uso: python s02_import.py
"""
from __future__ import annotations

import ast
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comune as c  # noqa: E402
from s01_righe import categoria  # noqa: E402

STDLIB = set(sys.stdlib_module_names)
LIBS_CHIAVE = ("betfairlightweight", "flumine", "supabase", "requests", "httpx", "websockets", "aiohttp",
               "urllib", "socket", "websocket", "postgrest", "psycopg2", "sqlalchemy")
EXT_CODICE = (".py", ".js", ".ts", ".tsx", ".bat", ".ps1", ".sh", ".yml", ".yaml", ".json", ".cmd", ".toml", ".cfg", ".txt")
DIR_AUDIT = re.compile(r"^(AUDIT_|_AUDIT_|SCHEMI_BOT|ARCHITETTURA_2026-10)")


def nome_modulo(rel: str) -> str:
    p = rel[:-3].split("/")
    if p[-1] == "__init__":
        p = p[:-1]
    return ".".join(p)


def main() -> int:
    tracciati = c.file_tracciati()
    py = [p for p in tracciati if p.endswith(".py")]
    mod_di_file = {p: nome_modulo(p) for p in py}
    file_di_mod: dict[str, str] = {}
    for p, m in mod_di_file.items():
        file_di_mod.setdefault(m, p)
    # CORREZIONE (08/10, delegato inventario): "Ai Engine/ai_engine/x.py" si importa come `ai_engine.x` (la cartella
    # "Ai Engine" e' nel sys.path, vedi i file stessi): senza questo alias gli import interni del pacchetto risultavano
    # "esterni" e meta' dei suoi moduli finivano nel gruppo A dei morti per errore.
    for m_, f_ in list(file_di_mod.items()):
        if m_.startswith("Ai Engine."):
            file_di_mod.setdefault(m_[len("Ai Engine."):], f_)
    cat = {p: categoria(p) for p in py}
    # moduli radice (file .py in radice): importabili con nome semplice
    radice_nomi = {m for p, m in mod_di_file.items() if "/" not in p}

    info: dict[str, dict] = {}
    errori_parse: list[str] = []
    for p in py:
        testo = c.leggi_testo(p)
        if testo is None:
            continue
        righe = testo.count("\n")
        try:
            albero = ast.parse(testo)
        except (SyntaxError, ValueError) as e:  # file non analizzabile
            errori_parse.append(f"{p}: {e}")
            info[p] = {"righe": righe, "interni": set(), "esterni": {}, "main": False, "stringhe": set(), "dinamici": 0}
            continue
        mod = mod_di_file[p]
        e_pkg = p.endswith("/__init__.py")
        pkg = mod.split(".") if e_pkg else mod.split(".")[:-1]
        cartella = p.rsplit("/", 1)[0] if "/" in p else ""
        interni: set[str] = set()
        esterni: dict[str, int] = {}
        stringhe: set[str] = set()
        dinamici = 0
        main_guard = "__main__" in testo and re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]", testo) is not None

        def risolvi(nome: str) -> str | None:
            """Ritorna il nome di modulo interno corrispondente (o None)."""
            if nome in file_di_mod:
                return nome
            # import da script con la sua cartella in sys.path: fratello nella stessa cartella
            if cartella:
                cand = (cartella.replace("/", ".") + "." + nome)
                if cand in file_di_mod:
                    return cand
            return None

        def registra(nome_completo: str, riga: int, livello_assoluto: bool = True) -> None:
            primo = nome_completo.split(".")[0]
            r = risolvi(nome_completo)
            if r is not None:
                interni.add(r)
                return
            # prefisso piu' lungo che e' un modulo interno
            parti = nome_completo.split(".")
            for i in range(len(parti) - 1, 0, -1):
                r = risolvi(".".join(parti[:i]))
                if r is not None:
                    interni.add(r)
                    return
            if risolvi(primo) is not None:
                interni.add(risolvi(primo))  # type: ignore[arg-type]
                return
            if primo in STDLIB or primo == "__future__":
                return
            esterni.setdefault(primo, riga)

        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Import):
                for a in nodo.names:
                    registra(a.name, nodo.lineno)
            elif isinstance(nodo, ast.ImportFrom):
                if nodo.level:
                    base = pkg[: len(pkg) - (nodo.level - 1)] if nodo.level - 1 <= len(pkg) else []
                    prefisso = ".".join(base + ([nodo.module] if nodo.module else []))
                else:
                    prefisso = nodo.module or ""
                if not prefisso:
                    continue
                registra(prefisso, nodo.lineno)
                for a in nodo.names:
                    sotto = prefisso + "." + a.name
                    if sotto in file_di_mod:
                        interni.add(sotto)
                    elif risolvi(sotto):
                        interni.add(risolvi(sotto))  # type: ignore[arg-type]
            elif isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
                v = nodo.value
                if len(v) < 200 and re.fullmatch(r"(?:Betfair|[A-Za-z_]\w*)(?:\.\w+)+", v):
                    # stringa che sembra un nome di modulo dotted (es. "-m Betfair.stream.runner" o patch())
                    if v in file_di_mod or any(v.startswith(m + ".") for m in ()):
                        stringhe.add(v)
                for m in re.findall(r"\bBetfair(?:\.\w+)+", v) if len(v) < 400 else []:
                    stringhe.add(m)
            elif isinstance(nodo, ast.Call):
                f = nodo.func
                nm = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
                if nm in ("import_module", "__import__"):
                    dinamici += 1
        interni.discard(mod)
        info[p] = {"righe": righe, "interni": interni, "esterni": esterni, "main": main_guard,
                   "stringhe": stringhe, "dinamici": dinamici}

    # importatori
    importatori: dict[str, set[str]] = collections.defaultdict(set)  # modulo -> file importatori
    for p, d in info.items():
        for m in d["interni"]:
            if m in file_di_mod:
                importatori[mod_di_file[file_di_mod[m]]].add(p)  # chiave = nome canonico del modulo (alias compresi)
    # un pacchetto e' "importato" se un suo sottomodulo e' importato? No: lo tengo separato.
    # riferimenti per stringa nei file di codice non di audit (py non test, js, bat, ps1, yml, json...)
    testi_ref: dict[str, str] = {}
    for p in tracciati:
        if p.endswith(EXT_CODICE) and not DIR_AUDIT.match(p):
            t = c.leggi_testo(p)
            if t is not None and len(t) < 3_000_000:
                testi_ref[p] = t

    def rif_stringa(modulo: str, file_proprio: str) -> list[str]:
        trovati: list[str] = []
        nome_file = file_proprio.rsplit("/", 1)[-1]
        for q, t in testi_ref.items():
            if q == file_proprio:
                continue
            if "." in modulo and modulo in t:
                trovati.append(q)
            elif "." not in modulo and nome_file != "__init__.py" and (nome_file in t or f"-m {modulo}" in t):
                trovati.append(q)
            elif "." in modulo and nome_file != "__init__.py" and file_proprio in t:
                trovati.append(q)
        return trovati

    # tabella moduli
    out = ["file\tmodulo\tcategoria\trighe\timp_prod\timp_test\timp_strum\timp_audit\tn_importa\tn_rif_stringa\tmain\testerni\tprimi_importatori"]
    riepilogo_ref: dict[str, list[str]] = {}
    for p in sorted(info):
        d = info[p]
        m = mod_di_file[p]
        imp = importatori.get(m, set())
        k = collections.Counter()
        for q in imp:
            cq = cat.get(q, "?")
            if cq in ("py_test",):
                k["test"] += 1
            elif cq == "py_strumenti":
                k["strum"] += 1
            elif cq == "py_script_audit":
                k["audit"] += 1
            else:
                k["prod"] += 1
        refs: list[str] = []
        if cat[p] in ("py_codice_Betfair", "py_codice_radice", "py_codice_cartelle_radice") and k["prod"] == 0:
            refs = rif_stringa(m, p)
        riepilogo_ref[p] = refs
        out.append("\t".join(map(str, [
            p, m, cat[p], d["righe"], k["prod"], k["test"], k["strum"], k["audit"], len(d["interni"]),
            len(refs) if cat[p].startswith("py_codice") and k["prod"] == 0 else "-",
            "si" if d["main"] else "no", ",".join(sorted(d["esterni"])),
            ";".join(sorted(imp)[:6]),
        ])))
    c.scrivi("s02_moduli.tsv", "\n".join(out) + "\n")

    # archi (importatore -> importato) per codice di produzione e strumenti
    archi = ["importatore\timportato"]
    for p in sorted(info):
        if cat[p] in ("py_test", "py_script_audit"):
            continue
        for m in sorted(info[p]["interni"]):
            if m in file_di_mod:
                archi.append(f"{p}\t{file_di_mod[m]}")
    c.scrivi("s02_archi.tsv", "\n".join(archi) + "\n")

    # esterni
    ext = ["file\tcategoria\tlibreria\triga_prima_importazione"]
    per_lib: dict[str, list[tuple[str, str, int]]] = collections.defaultdict(list)
    for p in sorted(info):
        for lib, riga in sorted(info[p]["esterni"].items()):
            ext.append(f"{p}\t{cat[p]}\t{lib}\t{riga}")
            per_lib[lib].append((p, cat[p], riga))
    c.scrivi("s02_esterni.tsv", "\n".join(ext) + "\n")

    # morti
    morti: list[str] = []
    prod_cat = ("py_codice_Betfair", "py_codice_radice", "py_codice_cartelle_radice")
    gruppi: dict[str, list[str]] = {"A_nessun_riferimento": [], "B_solo_main_o_stringa": [], "C_solo_test": [], "D_solo_strumenti_audit": []}
    for p in sorted(info):
        if cat[p] not in prod_cat or p.endswith("__init__.py"):
            continue
        m = mod_di_file[p]
        imp = importatori.get(m, set())
        prod = [q for q in imp if cat[q] not in ("py_test", "py_strumenti", "py_script_audit")]
        if prod:
            continue
        test = [q for q in imp if cat[q] == "py_test"]
        altri = [q for q in imp if cat[q] in ("py_strumenti", "py_script_audit")]
        refs = riepilogo_ref.get(p, [])
        riga = f"{p}  ({info[p]['righe']} righe)"
        if not imp and not refs and not info[p]["main"]:
            gruppi["A_nessun_riferimento"].append(riga)
        elif not imp and (refs or info[p]["main"]):
            extra = f"main={'si' if info[p]['main'] else 'no'}; riferimenti per stringa: {', '.join(sorted(refs)[:5]) or 'nessuno'}"
            gruppi["B_solo_main_o_stringa"].append(f"{riga}  [{extra}]")
        elif test and not altri and not refs:
            gruppi["C_solo_test"].append(f"{riga}  [test: {', '.join(sorted(test)[:3])}{' ...' if len(test) > 3 else ''}] main={'si' if info[p]['main'] else 'no'}")
        else:
            gruppi["D_solo_strumenti_audit"].append(
                f"{riga}  [strumenti/audit: {', '.join(sorted(altri)[:3])}; test: {len(test)}; stringhe: {', '.join(sorted(refs)[:3]) or '-'}] main={'si' if info[p]['main'] else 'no'}")
    morti.append("Criterio: modulo di codice di produzione (py_codice_*, no __init__) che nessun file di PRODUZIONE importa (AST).")
    morti.append("A = nessun importatore di nessun tipo, nessun riferimento per stringa in file di codice non-audit, nessun `if __name__ == '__main__'`.")
    morti.append("B = nessun importatore ma ha `__main__` o e' nominato per stringa (avviato come script/processo: NON morto per forza).")
    morti.append("C = importato solo da test; D = importato solo da strumenti/script di audit (o stringhe).")
    morti.append("Prova rieseguibile: `grep -rn '<nome_modulo>' --include=*.py --include=*.js --include=*.bat .` e s02_moduli.tsv (colonne imp_*).")
    morti.append("")
    for g, lst in gruppi.items():
        tot_righe = sum(int(re.search(r"[(](\d+) righe", x).group(1)) for x in lst)
        morti.append(f"== {g}: {len(lst)} moduli, {tot_righe} righe ==")
        morti.extend("  " + x for x in lst)
        morti.append("")
    c.scrivi("s02_morti.txt", "\n".join(morti) + "\n")

    # riepilogo
    r: list[str] = []
    r.append(f"moduli .py tracciati: {len(py)}; non analizzabili (SyntaxError): {len(errori_parse)}")
    for e in errori_parse[:10]:
        r.append("   " + e)
    nc = collections.Counter(cat.values())
    r.append("per categoria: " + ", ".join(f"{k}={v}" for k, v in nc.most_common()))
    n_archi_prod = len(archi) - 1
    r.append(f"archi interni (prod+strumenti verso qualsiasi): {n_archi_prod}")
    r.append(f"import dinamici (import_module/__import__) nel codice: " + ", ".join(
        f"{p}={d['dinamici']}" for p, d in sorted(info.items()) if d["dinamici"] and cat[p] not in ('py_test', 'py_script_audit')))
    r.append("")
    r.append("== Gruppi candidati morti (moduli di produzione) ==")
    for g, lst in gruppi.items():
        r.append(f"{g}: {len(lst)} moduli")
    r.append("")
    r.append("== Librerie chiave per categoria di file (n. file che le importano) ==")
    for lib in LIBS_CHIAVE:
        righe_l = per_lib.get(lib, [])
        kk = collections.Counter(x[1] for x in righe_l)
        r.append(f"{lib:<20} totale {len(righe_l):>4} file: " + ", ".join(f"{a}={b}" for a, b in kk.most_common()))
    r.append("")
    r.append("== Chi parla con l'esterno: file di PRODUZIONE (py_codice_*) per libreria chiave ==")
    for lib in ("betfairlightweight", "flumine", "supabase", "requests", "httpx", "websockets", "aiohttp"):
        lst = sorted(x for x in per_lib.get(lib, []) if x[1].startswith("py_codice"))
        r.append(f"-- {lib}: {len(lst)} file")
        for p, ca, riga in lst:
            r.append(f"   {p}:{riga}")
    r.append("")
    r.append("== Altre librerie esterne (non stdlib) nel codice di produzione: n. file ==")
    conteggio_ext: dict[str, int] = collections.Counter()
    for lib, lst in per_lib.items():
        conteggio_ext[lib] = sum(1 for x in lst if x[1].startswith("py_codice"))
    for lib, n in sorted(conteggio_ext.items(), key=lambda x: -x[1]):
        if n:
            r.append(f"   {lib:<28}{n:>4}")
    r.append("")
    r.append("== Moduli di produzione piu' importati (n. importatori di produzione) ==")
    top = sorted(((len([q for q in importatori[m] if cat[q] not in ('py_test', 'py_strumenti', 'py_script_audit')]), m) for m in importatori
                  if cat.get(file_di_mod.get(m, ''), '').startswith('py_codice')), reverse=True)[:30]
    for n, m in top:
        r.append(f"{n:>5}  {m}  ({file_di_mod[m]})")
    r.append("")
    r.append("== Moduli di produzione con piu' import interni (accoppiamento in uscita) ==")
    top2 = sorted(((len(info[p]['interni']), p) for p in info if cat[p].startswith('py_codice')), reverse=True)[:25]
    for n, p in top2:
        r.append(f"{n:>5}  {p}  ({info[p]['righe']} righe)")
    c.scrivi("s02_riepilogo.txt", "\n".join(r) + "\n")
    print("\n".join(r[:16]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
