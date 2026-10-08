"""Sezione 3 - accesso al DB: chiamate .table/.rpc/.from_ (Python via AST, TypeScript via regex),
REST diretto (`rest/v1/<tabella>`), matrice tabella -> file che leggono/scrivono, confronto con le
definizioni in migrations/ e sql/ (e con ogni altro .sql tracciato, separato).

Sola lettura dei file tracciati. Uscite in uscite/:
  s03_chiamate.tsv, s03_matrice_tabelle.tsv, s03_matrice_rpc.tsv, s03_definizioni.tsv, s03_riepilogo.txt
Uso: python s03_db.py
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

LETTURA = {"select"}
SCRITTURA = {"insert", "upsert", "update", "delete"}
OPS = LETTURA | SCRITTURA


def tipo_chiamante(rel: str, cat: str) -> str:
    """prod / test / strum / audit / frontend / desktop."""
    if cat in ("py_codice_Betfair", "py_codice_radice", "py_codice_cartelle_radice"):
        return "prod"
    if cat == "py_test" or cat == "frontend_test" or cat == "desktop_test":
        return "test"
    if cat == "py_strumenti":
        return "strum"
    if cat == "py_script_audit":
        return "audit"
    if cat == "frontend_codice":
        return "frontend"
    return "altro"


def costanti_modulo(albero: ast.AST) -> dict[str, str]:
    """NOME = "stringa" a livello di modulo o di classe (per risolvere .table(NOME))."""
    cost: dict[str, str] = {}
    for n in ast.walk(albero):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    cost[t.id] = n.value.value
                elif isinstance(t, ast.Attribute):
                    cost[t.attr] = n.value.value
    return cost


def analizza_py(rel: str, testo: str, cat: str, out: list[tuple]) -> None:
    try:
        albero = ast.parse(testo)
    except (SyntaxError, ValueError):
        return
    padre: dict[ast.AST, ast.AST] = {}
    funz_di: dict[ast.AST, ast.AST] = {}
    for n in ast.walk(albero):
        for f in ast.iter_child_nodes(n):
            padre[f] = n
    cost = costanti_modulo(albero)

    def funzione_contenitore(n: ast.AST) -> ast.AST:
        while n in padre:
            n = padre[n]
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return n
        return albero

    def catena_ops(chiamata: ast.Call) -> list[str]:
        ops: list[str] = []
        cur: ast.AST = chiamata
        while True:
            p = padre.get(cur)
            if isinstance(p, ast.Attribute) and p.value is cur:
                pp = padre.get(p)
                ops.append(p.attr)
                if isinstance(pp, ast.Call) and pp.func is p:
                    cur = pp
                    continue
            break
        if not any(o in OPS for o in ops):
            # query builder messo in variabile: cerca i metodi chiamati sulla variabile nella funzione
            p = padre.get(cur)
            nome_var = None
            if isinstance(p, ast.Assign) and len(p.targets) == 1 and isinstance(p.targets[0], ast.Name):
                nome_var = p.targets[0].id
            if nome_var:
                for n in ast.walk(funzione_contenitore(cur)):
                    if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == nome_var and n.attr in OPS:
                        ops.append(n.attr)
            elif isinstance(p, ast.Return):
                ops.append("(ritorna_il_builder)")
        return ops

    def nome_arg(a: ast.AST) -> str:
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            return a.value
        if isinstance(a, ast.Name) and a.id in cost:
            return cost[a.id]
        if isinstance(a, ast.Attribute) and a.attr in cost:
            return cost[a.attr]
        try:
            return "<dinamico:" + ast.unparse(a)[:40] + ">"
        except Exception:
            return "<dinamico>"

    for n in ast.walk(albero):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Attribute) and f.attr in ("table", "rpc", "from_") and n.args:
            tipo = f.attr
            if tipo == "from_" and isinstance(f.value, ast.Attribute) and f.value.attr == "storage":
                tipo = "storage"
            elif tipo == "from_":
                tipo = "table"  # supabase .from_(tabella)
            nome = nome_arg(n.args[0])
            ops = catena_ops(n) if tipo == "table" else []
            op = ",".join(sorted({o for o in ops if o in OPS or o.startswith("(")})) or "?"
            out.append((rel, n.lineno, tipo, nome, op, cat, "py"))
        elif isinstance(f, ast.Name) and f.id == "_rpc" and rel == "ventaglio_segnali.py" and n.args:
            out.append((rel, n.lineno, "rpc", nome_arg(n.args[0]), "", cat, "py"))
    # REST diretto (urllib/httpx con rest/v1/<tabella>)
    for i, riga in enumerate(testo.splitlines(), 1):
        for m in re.finditer(r"rest/v1/(?:rpc/)?([A-Za-z_][A-Za-z0-9_]*)", riga):
            tipo = "rest_rpc" if "rest/v1/rpc/" in riga[m.start():m.end() + 1] else "rest_tabella"
            out.append((rel, i, tipo, m.group(1), "", cat, "py"))
        if re.search(r"rest/v1/(\{|\"\s*\+|'\s*\+)", riga):
            out.append((rel, i, "rest_dinamico", "<percorso costruito a runtime>", "", cat, "py"))


RX_FROM = re.compile(r"\.from\(\s*[\"'`]([A-Za-z_][A-Za-z0-9_]*)[\"'`]\s*\)")
RX_RPC = re.compile(r"\.rpc\(\s*[\"'`]([A-Za-z_][A-Za-z0-9_]*)[\"'`]")
RX_RPC_DIN = re.compile(r"\.rpc\(\s*[^\"'`\s]")
RX_OP = re.compile(r"\.(select|insert|upsert|update|delete)\(")


def analizza_ts(rel: str, testo: str, cat: str, out: list[tuple]) -> None:
    for m in RX_FROM.finditer(testo):
        riga = testo.count("\n", 0, m.start()) + 1
        coda = testo[m.end(): m.end() + 500]
        mo = RX_OP.search(coda)
        # il primo metodo di operazione della catena; ferma al prossimo .from( per non sconfinare
        stop = RX_FROM.search(coda)
        if mo and stop and stop.start() < mo.start():
            mo = None
        out.append((rel, riga, "table", m.group(1), mo.group(1) if mo else "?", cat, "ts"))
    for m in RX_RPC.finditer(testo):
        riga = testo.count("\n", 0, m.start()) + 1
        out.append((rel, riga, "rpc", m.group(1), "", cat, "ts"))
    for m in RX_RPC_DIN.finditer(testo):
        riga = testo.count("\n", 0, m.start()) + 1
        out.append((rel, riga, "rpc", "<dinamico>", "", cat, "ts"))


RX_DEF = re.compile(r"^\s*create\s+(?:or\s+replace\s+)?(?:unlogged\s+)?(table|view|materialized\s+view|function)\s+(?:if\s+not\s+exists\s+)?(?:public\.)?\"?([A-Za-z_][A-Za-z0-9_]*)\"?", re.I)
RX_DROP = re.compile(r"^\s*drop\s+(table|view|materialized\s+view|function)\s+(?:if\s+exists\s+)?(?:public\.)?\"?([A-Za-z_][A-Za-z0-9_]*)\"?", re.I)


def main() -> int:
    tracciati = c.file_tracciati()
    out: list[tuple] = []
    for rel in tracciati:
        ext = Path(rel).suffix.lower()
        if ext not in (".py", ".ts", ".tsx", ".js"):
            continue
        if ext == ".js" and not rel.startswith("desktop/"):
            continue
        testo = c.leggi_testo(rel)
        if testo is None:
            continue
        cat = categoria(rel)
        if ext == ".py":
            analizza_py(rel, testo, cat, out)
        elif rel.startswith("frontend/src/") or rel.startswith("desktop/"):
            analizza_ts(rel, testo, cat, out)
    out.sort()
    c.scrivi("s03_chiamate.tsv", "file\triga\ttipo\tnome\toperazione\tcategoria\tlinguaggio\n" + "\n".join("\t".join(map(str, x)) for x in out) + "\n")

    # --- definizioni nei .sql
    defs: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    drops: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    for rel in tracciati:
        if not rel.endswith(".sql"):
            continue
        testo = c.leggi_testo(rel)
        if testo is None:
            continue
        origine = "migrations" if rel.startswith("migrations/") else ("sql" if rel.startswith("sql/") else "altro_sql")
        for i, riga in enumerate(testo.splitlines(), 1):
            m = RX_DEF.match(riga)
            if m:
                kind = re.sub(r"\s+", "_", m.group(1).lower())
                defs[(kind, m.group(2).lower())].append(f"{origine}:{rel}:{i}")
            m = RX_DROP.match(riga)
            if m:
                kind = re.sub(r"\s+", "_", m.group(1).lower())
                drops[(kind, m.group(2).lower())].append(f"{origine}:{rel}:{i}")
    rd = ["kind\tnome\tn_create\tn_drop\tprima_definizione\tfonti_origine"]
    for (kind, nome), lst in sorted(defs.items()):
        orig = sorted({x.split(":")[0] for x in lst})
        rd.append(f"{kind}\t{nome}\t{len(lst)}\t{len(drops.get((kind, nome), []))}\t{lst[0].split(':', 1)[1]}\t{','.join(orig)}")
    c.scrivi("s03_definizioni.tsv", "\n".join(rd) + "\n")

    # --- matrici
    tab: dict[str, dict] = collections.defaultdict(lambda: {"r": collections.defaultdict(set), "w": collections.defaultdict(set),
                                                           "q": collections.defaultdict(set), "n": collections.Counter()})
    rpc: dict[str, dict] = collections.defaultdict(lambda: {"f": collections.defaultdict(set), "n": collections.Counter()})
    for rel, riga, tipo, nome, op, cat, ling in out:
        tc = tipo_chiamante(rel, cat)
        if tipo in ("table", "rest_tabella"):
            e = tab[nome]
            e["n"][tc] += 1
            ops = set(op.split(",")) if op else set()
            ref = f"{rel}:{riga}"
            if ops & SCRITTURA:
                e["w"][tc].add(ref)
            if ops & LETTURA or tipo == "rest_tabella":
                e["r"][tc].add(ref)
            if not (ops & OPS):
                e["q"][tc].add(ref)
        elif tipo in ("rpc", "rest_rpc"):
            rpc[nome]["n"][tc] += 1
            rpc[nome]["f"][tc].add(f"{rel}:{riga}")

    def lista(d: dict, k: str, lim: int = 4) -> str:
        lst = sorted(d.get(k, set()))
        extra = f" (+{len(lst) - lim})" if len(lst) > lim else ""
        return "; ".join(lst[:lim]) + extra

    rt = ["tabella\tdefinita_in\tn_prod\tn_frontend\tn_test\tn_strum\tn_audit\tprod_legge\tprod_scrive\tprod_op_non_determinata\tfrontend_legge\tfrontend_scrive"]
    for nome in sorted(tab):
        e = tab[nome]
        dd = defs.get(("table", nome)) or defs.get(("view", nome)) or defs.get(("materialized_view", nome)) or []
        rt.append("\t".join([
            nome, (dd[0].split(":", 1)[0] if dd else "-"), str(e["n"]["prod"]), str(e["n"]["frontend"]), str(e["n"]["test"]),
            str(e["n"]["strum"]), str(e["n"]["audit"]), lista(e["r"], "prod"), lista(e["w"], "prod"), lista(e["q"], "prod", 2),
            lista(e["r"], "frontend", 3), lista(e["w"], "frontend", 3)]))
    c.scrivi("s03_matrice_tabelle.tsv", "\n".join(rt) + "\n")
    rr = ["rpc\tdefinita_in\tn_prod\tn_frontend\tn_test\tn_strum\tn_audit\tfile_prod\tfile_frontend"]
    for nome in sorted(rpc):
        e = rpc[nome]
        dd = defs.get(("function", nome)) or []
        rr.append("\t".join([nome, (dd[0].split(":", 1)[0] if dd else "-"), str(e["n"]["prod"]), str(e["n"]["frontend"]),
                             str(e["n"]["test"]), str(e["n"]["strum"]), str(e["n"]["audit"]), lista(e["f"], "prod", 3), lista(e["f"], "frontend", 3)]))
    c.scrivi("s03_matrice_rpc.tsv", "\n".join(rr) + "\n")

    # --- riepilogo
    r: list[str] = []
    r.append(f"chiamate trovate: {len(out)}")
    kk = collections.Counter((x[2], tipo_chiamante(x[0], x[5])) for x in out)
    r.append("per tipo e chiamante: " + ", ".join(f"{k[0]}/{k[1]}={v}" for k, v in sorted(kk.items())))
    r.append("")
    r.append("== A. `.table(` / `.from_(` PER FILE (produzione + strumenti, ordinati) - da confrontare con il brief ==")
    per_file = collections.Counter()
    for rel, riga, tipo, nome, op, cat, ling in out:
        if tipo == "table" and ling == "py" and tipo_chiamante(rel, cat) in ("prod",):
            per_file[rel] += 1
    for rel, n in per_file.most_common(30):
        r.append(f"{n:>5}  {rel}")
    r.append("  brief par.1: stream/db.py 53, safe/bot_db.py 46, omega/omega_db.py 44, tennis_db.py 39, mike/db.py 32, scalper_session 20, live_order_worker 18, scalper_service 16, safe/db.py 12")
    r.append("")
    r.append("== B. `.rpc(` per file (produzione) ==")
    pf = collections.Counter()
    for rel, riga, tipo, nome, op, cat, ling in out:
        if tipo in ("rpc", "rest_rpc") and tipo_chiamante(rel, cat) == "prod":
            pf[rel] += 1
    for rel, n in pf.most_common(20):
        r.append(f"{n:>5}  {rel}")
    r.append("")
    usate_prod = {n for n, e in tab.items() if e["n"]["prod"] or e["n"]["frontend"]}
    usate_py_prod = {n for n, e in tab.items() if e["n"]["prod"]}
    usate_fe = {n for n, e in tab.items() if e["n"]["frontend"]}
    usate_qualsiasi = set(tab)
    nomi_veri = lambda s: {x for x in s if not x.startswith("<")}
    r.append("== C. TABELLE ==")
    r.append(f"tabelle distinte (nome letterale) usate da codice Python di produzione: {len(nomi_veri(usate_py_prod))}")
    r.append(f"tabelle distinte usate dal frontend (src, non test): {len(nomi_veri(usate_fe))}")
    r.append(f"tabelle distinte usate da prod o frontend: {len(nomi_veri(usate_prod))}   (brief: 55 tabelle usate dal codice)")
    r.append(f"tabelle distinte usate da QUALSIASI file (anche test/strumenti/audit): {len(nomi_veri(usate_qualsiasi))}")
    dinam = sorted({n for n in tab if n.startswith('<') and (tab[n]['n']['prod'] or tab[n]['n']['frontend'])})
    r.append(f"nomi non letterali (prod/frontend) da risolvere a mano: {len(dinam)}: " + "; ".join(dinam[:25]))
    def_tab = {n for (k, n) in defs if k in ("table",)}
    def_viste = {n for (k, n) in defs if k in ("view", "materialized_view")}
    def_funz = {n for (k, n) in defs if k == "function"}
    r.append(f"oggetti definiti nei .sql tracciati: tabelle {len(def_tab)}, viste {len(def_viste)}, funzioni {len(def_funz)}")
    in_migr = {n for (k, n), l in defs.items() if k == "table" and any(x.startswith(("migrations:", "sql:")) for x in l)}
    r.append(f"  tabelle definite in migrations/ o sql/: {len(in_migr)}")
    r.append("")
    r.append("-- tabelle USATE da prod/frontend ma NON definite in nessun .sql tracciato (tabelle/viste):")
    non_def = sorted(n for n in nomi_veri(usate_prod) if n not in def_tab and n not in def_viste)
    r.append(f"   {len(non_def)}: " + ", ".join(non_def))
    r.append("")
    r.append("-- tabelle DEFINITE in migrations/sql ma mai usate da prod/frontend (usate solo da test/strumenti/audit o per niente):")
    mai = sorted(n for n in in_migr if n not in usate_prod)
    for n in mai:
        e = tab.get(n)
        r.append(f"   {n:<46} test={e['n']['test'] if e else 0} strum={e['n']['strum'] if e else 0} audit={e['n']['audit'] if e else 0}")
    r.append(f"   totale: {len(mai)}")
    r.append("")
    r.append("-- viste definite e mai referenziate da .table()/.from():")
    for n in sorted(def_viste):
        if n not in usate_qualsiasi:
            r.append(f"   {n}")
    r.append("")
    usate_rpc_prod = {n for n, e in rpc.items() if e["n"]["prod"] or e["n"]["frontend"]}
    r.append("== D. RPC ==")
    r.append(f"RPC distinte chiamate da prod/frontend: {len(nomi_veri(usate_rpc_prod))}; da qualsiasi file: {len(nomi_veri(set(rpc)))}")
    r.append("-- RPC chiamate da prod/frontend ma non definite come funzione nei .sql tracciati:")
    r.append("   " + ", ".join(sorted(n for n in nomi_veri(usate_rpc_prod) if n not in def_funz)))
    r.append("-- funzioni definite nei .sql ma mai chiamate da prod/frontend (possibile uso da trigger/cron/altre funzioni):")
    mai_f = sorted(n for n in def_funz if n not in usate_rpc_prod)
    r.append(f"   {len(mai_f)}: " + ", ".join(mai_f[:80]) + (" ..." if len(mai_f) > 80 else ""))
    r.append("")
    r.append("== E. TABELLE PIU' TOCCATE DA PRODUZIONE (n. chiamate prod | frontend) ==")
    for n, e in sorted(tab.items(), key=lambda x: -(x[1]['n']['prod'] + x[1]['n']['frontend']))[:45]:
        r.append(f"{e['n']['prod']:>4} | {e['n']['frontend']:>3}  {n}")
    c.scrivi("s03_riepilogo.txt", "\n".join(r) + "\n")
    print("\n".join(r[:40]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
