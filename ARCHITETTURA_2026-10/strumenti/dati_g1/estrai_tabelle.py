"""G1 - estrae da git tutte le chiamate `.table(...)`, `.rpc(...)` (Python) e `.from(...)`/`.rpc(...)` (frontend).

Solo libreria standard, sola lettura sui file tracciati. Scrive SOLO in
ARCHITETTURA_2026-10/strumenti/dati_g1/uscite/. Rieseguibile:
    python ARCHITETTURA_2026-10/strumenti/dati_g1/estrai_tabelle.py
Uscite: chiamate_py.tsv, chiamate_fe.tsv, rpc_py.tsv, rpc_fe.tsv, riepilogo.txt
Colonne py: file, riga, tabella(o simbolo), risolta, operazione, categoria
"""
from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from pathlib import Path

RADICE = Path(__file__).resolve().parents[3]
USCITE = Path(__file__).resolve().parent / "uscite"
USCITE.mkdir(parents=True, exist_ok=True)

OPS = ("select", "insert", "upsert", "update", "delete")
RE_TABLE = re.compile(r"\.table\(\s*([A-Za-z_][A-Za-z_0-9\.]*|[\"'][A-Za-z_0-9]+[\"'])")
RE_RPC_PY = re.compile(r"\.rpc\(\s*([A-Za-z_][A-Za-z_0-9\.]*|[\"'][A-Za-z_0-9]+[\"'])")
RE_CONST = re.compile(r"^([A-Za-z_][A-Za-z_0-9]*)\s*(?::\s*\w+\s*)?=\s*[\"']([a-z_0-9]+)[\"']\s*$", re.M)
RE_FE_FROM = re.compile(r"\.from\(\s*['\"`]([A-Za-z_0-9]+)['\"`]")
RE_FE_RPC = re.compile(r"\.rpc\(\s*['\"`]([A-Za-z_0-9]+)['\"`]")


def tracciati() -> list[str]:
    o = subprocess.run(["git", "ls-files", "-z"], cwd=RADICE, capture_output=True, check=True)
    return [p for p in o.stdout.decode("utf-8", "replace").split("\0") if p]


def e_test(rel: str) -> bool:
    n = rel.rsplit("/", 1)[-1]
    return (n.startswith("test_") or n.endswith("_test.py") or n == "conftest.py"
            or "/tests/" in rel or ".test." in n or "/__fixtures__/" in rel)


def categoria(rel: str) -> str:
    if e_test(rel):
        return "test"
    if rel.startswith(("AUDIT_", "_AUDIT", "_validazione", "_checkpoint", "laboratorio/")):
        return "audit"
    if "/tools/" in rel or rel.startswith("tools/") or "/tools_" in rel:
        return "tool"
    if rel.startswith("Betfair/"):
        return "betfair"
    return "radice_e_motori"


def leggi(rel: str) -> str:
    try:
        return (RADICE / rel).read_text("utf-8", errors="replace")
    except OSError:
        return ""


def main() -> None:
    files = tracciati()
    py = [f for f in files if f.endswith(".py")]
    fe = [f for f in files if f.startswith("frontend/src/") and f.endswith((".ts", ".tsx"))]
    testi = {f: leggi(f) for f in py}
    globali: dict[str, set[str]] = defaultdict(set)
    locali: dict[str, dict[str, str]] = {}
    for f, t in testi.items():
        d = {m.group(1): m.group(2) for m in RE_CONST.finditer(t)}
        locali[f] = d
        for k, v in d.items():
            globali[k].add(v)

    righe_t: list[str] = []
    righe_r: list[str] = []
    for f, t in testi.items():
        cat = categoria(f)
        for m in RE_TABLE.finditer(t):
            sim = m.group(1)
            riga = t.count("\n", 0, m.start()) + 1
            if sim[0] in "\"'":
                nome = sim.strip("\"'")
            else:
                nome = locali[f].get(sim) or (next(iter(globali[sim])) if len(globali.get(sim, ())) == 1 else "?" + sim)
            coda = t[m.end(): m.end() + 700]
            op = "?"
            best = 10 ** 9
            for o in OPS:
                i = coda.find("." + o + "(")
                if 0 <= i < best:
                    best, op = i, o
            righe_t.append(f"{f}\t{riga}\t{sim}\t{nome}\t{op}\t{cat}")
        for m in RE_RPC_PY.finditer(t):
            sim = m.group(1)
            riga = t.count("\n", 0, m.start()) + 1
            if sim[0] in "\"'":
                nome = sim.strip("\"'")
            else:
                nome = locali[f].get(sim) or "?" + sim
            righe_r.append(f"{f}\t{riga}\t{sim}\t{nome}\trpc\t{cat}")

    fe_t: list[str] = []
    fe_r: list[str] = []
    for f in fe:
        t = leggi(f)
        cat = categoria(f)
        for m in RE_FE_FROM.finditer(t):
            riga = t.count("\n", 0, m.start()) + 1
            coda = t[m.end(): m.end() + 700]
            op = "?"
            best = 10 ** 9
            for o in OPS:
                i = coda.find("." + o + "(")
                if 0 <= i < best:
                    best, op = i, o
            fe_t.append(f"{f}\t{riga}\t{m.group(1)}\t{m.group(1)}\t{op}\t{cat}")
        for m in RE_FE_RPC.finditer(t):
            riga = t.count("\n", 0, m.start()) + 1
            fe_r.append(f"{f}\t{riga}\t{m.group(1)}\t{m.group(1)}\trpc\t{cat}")

    (USCITE / "chiamate_py.tsv").write_text("\n".join(righe_t) + "\n", encoding="utf-8")
    (USCITE / "rpc_py.tsv").write_text("\n".join(righe_r) + "\n", encoding="utf-8")
    (USCITE / "chiamate_fe.tsv").write_text("\n".join(fe_t) + "\n", encoding="utf-8")
    (USCITE / "rpc_fe.tsv").write_text("\n".join(fe_r) + "\n", encoding="utf-8")
    print(len(righe_t), len(righe_r), len(fe_t), len(fe_r))


if __name__ == "__main__":
    main()
