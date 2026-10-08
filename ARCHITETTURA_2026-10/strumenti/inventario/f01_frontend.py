"""Sezione 6 - frontend: rotte (App.tsx), per ogni pagina la chiusura transitiva degli import locali e gli accessi ai dati
(RPC Supabase, tabelle `.from()`, canali locali `getLocalChannel`, realtime, edge functions, fetch, intervalli, localStorage)
con file:riga. Solo frontend/src non-test, file tracciati, sola lettura. Nessuna esecuzione.
Uscite: uscite/f01_rotte.tsv, uscite/f01_accessi_file.tsv, uscite/f01_pagine.txt
Uso: python f01_frontend.py
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comune as c  # noqa: E402

EST = (".ts", ".tsx")
RE_TEST = re.compile(r"\.(test|spec)\.|/__fixtures__/|/test/|^frontend/src/(fotografia|anteprima|certification)/")
RE_IMPORT = re.compile(r"""(?:from|import)\s*\(?\s*['"]([^'"]+)['"]""")
PAT = {
    "rpc": re.compile(r"\.rpc\(\s*['\"`]([A-Za-z0-9_]+)['\"`]"),
    "rpc_dinamica": re.compile(r"\.rpc\(\s*(?!['\"`])([^,)\s][^,)]*)"),
    "tabella": re.compile(r"\.from\(\s*['\"`]([A-Za-z0-9_]+)['\"`]"),
    "canale_locale": re.compile(r"getLocalChannel\(\s*['\"]?([A-Za-z_]+)"),
    "realtime": re.compile(r"\.channel\(|postgres_changes"),
    "edge_function": re.compile(r"functions\.invoke\(\s*['\"`]([A-Za-z0-9_\-]+)"),
    "fetch": re.compile(r"\bfetch\(\s*([`'\"][^`'\"]{0,60})"),
    "intervallo": re.compile(r"(setInterval\(|refetchInterval\s*:\s*[^,\n]{0,25})"),
    "localStorage": re.compile(r"(localStorage|sessionStorage)\.(?:getItem|setItem)\(\s*([^,)]+)"),
    "finestra": re.compile(r"window\.open\(|alphascoreCanale"),
}


def risolvi(da: str, spec: str, tutti: set[str]) -> str | None:
    if spec.startswith("@/"):
        base = "frontend/src/" + spec[2:]
    elif spec.startswith("."):
        parti = da.split("/")[:-1]
        for s in spec.split("/"):
            if s == "..":
                parti.pop()
            elif s != ".":
                parti.append(s)
        base = "/".join(parti)
    else:
        return None
    for cand in (base, base + ".ts", base + ".tsx", base + "/index.ts", base + "/index.tsx"):
        if cand in tutti:
            return cand
    return None


def main() -> int:
    tutti = {p for p in c.file_tracciati() if p.startswith("frontend/src/") and p.endswith(EST)}
    codice = {p for p in tutti if not RE_TEST.search(p)}
    testi = {p: (c.leggi_testo(p) or "") for p in codice}
    righe_f = {p: t.count("\n") for p, t in testi.items()}
    grafo: dict[str, set[str]] = {}
    for p, t in testi.items():
        s = set()
        for m in RE_IMPORT.finditer(t):
            r = risolvi(p, m.group(1), codice)
            if r:
                s.add(r)
        grafo[p] = s
    # accessi diretti per file
    acc: dict[str, list[tuple[str, str, int]]] = collections.defaultdict(list)
    for p, t in testi.items():
        for i, riga in enumerate(t.splitlines(), 1):
            if riga.lstrip().startswith(("//", "*")):
                continue
            for k, rx in PAT.items():
                for m in rx.finditer(riga):
                    nome = (m.group(1) if m.groups() else m.group(0)).strip()[:70]
                    acc[p].append((k, nome, i))
    out = ["file\triga\ttipo\tnome"]
    for p in sorted(acc):
        for k, n, i in acc[p]:
            out.append(f"{p}\t{i}\t{k}\t{n}")
    c.scrivi("f01_accessi_file.tsv", "\n".join(out) + "\n")
    # rotte da App.tsx: albero 'off' (default) = righe prima di RotteGuscioV2? -> si prende il testo intero e si legge <Route path= element=>
    app = testi["frontend/src/App.tsx"]
    imp = {}
    for m in re.finditer(r"import\s+(?:\{([^}]+)\}|(\w+))\s+from\s+['\"]([^'\"]+)['\"]", app):
        r = risolvi("frontend/src/App.tsx", m.group(3), codice)
        for nome in ([x.strip().split(" as ")[-1] for x in m.group(1).split(",")] if m.group(1) else [m.group(2)]):
            imp[nome] = r
    rotte = []
    for m in re.finditer(r"path=\"([^\"]+)\"\s*(?:\n\s*)?element=\{(.*?)\}\s*/?>", app, re.S):
        comp = re.findall(r"<(\w+)", m.group(2))
        rotte.append((m.group(1), comp, app[:m.start()].count("\n") + 1))
    for m in re.finditer(r"<Route path=\"([^\"]+)\" element=\{<(\w+)", app):
        pass
    r_out = ["path\tcomponenti\triga_App.tsx"]
    righe_pag: list[str] = []
    pagine_viste = {}
    # l'albero di DEFAULT (ui.shell off) e' l'ultimo del file (App.tsx:110-296); quello v2 e' il primo (:48-93): vale il numero di riga piu' alto
    for path, comp, riga in sorted(rotte, key=lambda x: -x[2]):
        r_out.append(f"{path}\t{','.join(comp)}\t{riga}")
        for cn in comp:
            f = imp.get(cn)
            if f and f.startswith("frontend/src/pages/") and path not in pagine_viste:
                pagine_viste[path] = (f, riga)
    for m in reversed(list(re.finditer(r"<Route path=\"([^\"]+)\" element=\{<(\w+)\s*/>\}", app))):
        f = imp.get(m.group(2))
        if f and m.group(1) not in pagine_viste:
            pagine_viste[m.group(1)] = (f, app[:m.start()].count("\n") + 1)
    c.scrivi("f01_rotte.tsv", "\n".join(r_out) + "\n")
    # chiusura per pagina
    for path, (f, riga) in sorted(pagine_viste.items()):
        vis = {f}
        coda = [f]
        while coda:
            x = coda.pop()
            for y in grafo.get(x, ()):
                if y not in vis:
                    vis.add(y)
                    coda.append(y)
        # StoricoSport e' nominato con export
        tot = sum(righe_f[v] for v in vis)
        rpcs = collections.OrderedDict()
        tabs = collections.OrderedDict()
        chs = collections.OrderedDict()
        altri = collections.Counter()
        for v in sorted(vis):
            for k, n, i in acc.get(v, []):
                ref = f"{v.replace('frontend/src/', '')}:{i}"
                if k == "rpc":
                    rpcs.setdefault(n, ref)
                elif k == "tabella":
                    tabs.setdefault(n, ref)
                elif k == "canale_locale":
                    chs.setdefault(n, ref)
                else:
                    altri[k] += 1
        righe_pag.append(f"### {path}  -> {f}:1  (App.tsx:{riga})  pagina {righe_f[f]} righe; chiusura import {len(vis)} file, {tot} righe")
        righe_pag.append(f"  RPC ({len(rpcs)}): " + "; ".join(f"{n} [{r}]" for n, r in rpcs.items()))
        righe_pag.append(f"  tabelle .from ({len(tabs)}): " + "; ".join(f"{n} [{r}]" for n, r in tabs.items()))
        righe_pag.append(f"  canali locali ({len(chs)}): " + "; ".join(f"{n} [{r}]" for n, r in chs.items()))
        righe_pag.append("  altro (conteggio occorrenze nella chiusura): " + ", ".join(f"{k}={v}" for k, v in sorted(altri.items())))
    c.scrivi("f01_pagine.txt", "\n".join(righe_pag) + "\n")
    # riepilogo: tabella rotte e accessi per file
    riep = ["== ROTTE (albero di default 'off', App.tsx:110-296) e chiusura degli import ==",
            f"{'rotta':<22}{'pagina':<44}{'righe pag':>10}{'file chiusura':>14}{'righe chiusura':>15}{'RPC':>5}{'tab':>5}{'canali':>8}"]
    for path, (f, riga) in sorted(pagine_viste.items()):
        vis = {f}
        coda = [f]
        while coda:
            x = coda.pop()
            for y in grafo.get(x, ()):
                if y not in vis:
                    vis.add(y)
                    coda.append(y)
        nr = len({n for v in vis for k, n, i in acc.get(v, []) if k == "rpc"})
        nt = len({n for v in vis for k, n, i in acc.get(v, []) if k == "tabella"})
        nc = len({n for v in vis for k, n, i in acc.get(v, []) if k == "canale_locale"})
        riep.append(f"{path:<22}{f.replace('frontend/src/', ''):<44}{righe_f[f]:>10}{len(vis):>14}{sum(righe_f[v] for v in vis):>15}{nr:>5}{nt:>5}{nc:>8}")
    riep.append("")
    riep.append("== ACCESSI AI DATI PER FILE (non test), primi 45 per RPC distinte (un file di lib/ e' il wrapper tipizzato usato dalle pagine) ==")
    righe_acc = []
    for p_, lst in acc.items():
        a = collections.defaultdict(set)
        cnt = collections.Counter()
        for k, n, i in lst:
            a[k].add(n)
            cnt[k] += 1
        righe_acc.append((len(a["rpc"]), p_, len(a["tabella"]), len(a["canale_locale"]), cnt["realtime"], cnt["fetch"], cnt["intervallo"]))
    for nr, p_, nt, nc, rt, ft, iv in sorted(righe_acc, reverse=True)[:45]:
        riep.append(f"{p_.replace('frontend/src/', ''):<58}rpc={nr:>3} tab={nt:>2} canali={nc:>2} realtime={rt:>2} fetch={ft:>2} intervalli={iv:>2}")
    tot_rpc = {n for lst in acc.values() for k, n, i in lst if k == "rpc"}
    tot_tab = {n for lst in acc.values() for k, n, i in lst if k == "tabella"}
    riep.append("")
    riep.append(f"TOTALE frontend/src non test: RPC distinte {len(tot_rpc)}, tabelle .from distinte {len(tot_tab)}, chiamate .rpc non letterali {sum(1 for lst in acc.values() for k, n, i in lst if k == 'rpc_dinamica')}")
    c.scrivi("f01_riepilogo.txt", "\n".join(riep) + "\n")
    # tabella markdown delle rotte (chiusura transitiva degli import = limite SUPERIORE di cio' che la pagina puo' toccare)
    LETTERALI = {"calcio", "tennis", "mike", "omega", "safe", "scanner", "tennis_bot", "scalper"}
    md = ["| rotta | pagina (`App.tsx` riga) | righe pagina | chiusura (file / righe) | RPC | tabelle `.from()` | canali locali (letterali) | realtime / polling |",
          "|---|---|---|---|---|---|---|---|"]
    for path, (f, riga) in sorted(pagine_viste.items()):
        vis = {f}
        coda = [f]
        while coda:
            x = coda.pop()
            for y in grafo.get(x, ()):
                if y not in vis:
                    vis.add(y)
                    coda.append(y)
        rp = {n for v in vis for k, n, i in acc.get(v, []) if k == "rpc"}
        tb = sorted({n for v in vis for k, n, i in acc.get(v, []) if k == "tabella"})
        ch_all = {n for v in vis for k, n, i in acc.get(v, []) if k == "canale_locale"}
        ch = sorted(ch_all & LETTERALI)
        var = " + variabile" if ch_all - LETTERALI else ""
        rt = sum(1 for v in vis for k, n, i in acc.get(v, []) if k == "realtime")
        iv = sum(1 for v in vis for k, n, i in acc.get(v, []) if k == "intervallo")
        md.append("| `%s` | `%s:1` (App.tsx:%d) | %d | %d / %d | %d | %s | %s | %d / %d |" % (
            path, f.replace("frontend/src/", ""), riga, righe_f[f], len(vis), sum(righe_f[v] for v in vis), len(rp),
            ", ".join(tb) if len(tb) <= 6 else "%d (%s ...)" % (len(tb), ", ".join(tb[:4])), (", ".join(ch) + var) or "-", rt, iv))
    c.scrivi("f01_rotte.md", "\n".join(md) + "\n")
    print(len(pagine_viste), "pagine;", len(codice), "file codice;", sum(righe_f.values()), "righe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
