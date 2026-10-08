"""Sezione 8 - cosa e' cambiato rispetto a SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md (02/10, base codice 22d19cc).

1) Per ogni citazione `file:riga` dell'inventario del 02/10: il testo di quella riga a 22d19cc (git show) viene cercato nel file
   di oggi (HEAD): stessa riga / spostata (nuova riga) / testo sparito / file sparito. Misura quanti 'fatti' dell'inventario sono
   ancora al loro posto.
2) git diff --numstat 22d19cc..HEAD aggregato per cartella (file aggiunti, tolti, righe +/-), solo file tracciati.
3) Righe di oggi dei file piu' grandi citati in I-1 dell'inventario del 02/10.
Uso: python c01_confronto_02_10.py  (solo git in lettura)
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comune as c  # noqa: E402

BASE = "22d19cc"
DOC = "SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md"


def git_show(rev: str, rel: str) -> list[str] | None:
    try:
        return c.git("show", f"{rev}:{rel}").splitlines()
    except Exception:
        return None


def main() -> int:
    testo = (c.RADICE / DOC).read_text(encoding="utf-8")
    cit = set()
    for m in re.finditer(r"`([A-Za-z0-9_./\-]+\.(?:py|js|ts|tsx)):(\d+)`", testo):
        cit.add((m.group(1), int(m.group(2))))
    cache_base: dict[str, list[str] | None] = {}
    cache_head: dict[str, list[str] | None] = {}
    esiti = collections.Counter()
    righe = ["file\triga_02_10\tesito\triga_oggi\ttesto_02_10"]
    per_file: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for f, n in sorted(cit):
        if f not in cache_base:
            cache_base[f] = git_show(BASE, f)
            cache_head[f] = git_show("HEAD", f)
        b, h = cache_base[f], cache_head[f]
        if b is None:
            e, nuova, t = "base_non_trovata", "", ""
        elif h is None:
            e, nuova, t = "FILE_SPARITO", "", ""
        elif n > len(b):
            e, nuova, t = "riga_oltre_fine_a_base", "", ""
        else:
            t = b[n - 1].strip()
            if not t:
                e, nuova = "riga_vuota_a_base", ""
            elif n <= len(h) and h[n - 1].strip() == t:
                e, nuova = "stessa_riga", str(n)
            else:
                pos = [i + 1 for i, x in enumerate(h) if x.strip() == t]
                if pos:
                    e, nuova = "spostata", str(min(pos, key=lambda p: abs(p - n)))
                else:
                    e, nuova = "TESTO_CAMBIATO_O_SPARITO", ""
        esiti[e] += 1
        per_file[f][e] += 1
        righe.append(f"{f}\t{n}\t{e}\t{nuova}\t{t[:90]}")
    c.scrivi("c01_citazioni_0210.tsv", "\n".join(righe) + "\n")

    out = []
    out.append(f"citazioni file:riga distinte nell'inventario del 02/10: {len(cit)} in {len(cache_base)} file")
    for e, k in esiti.most_common():
        out.append(f"  {e:<28}{k:>6}  ({100 * k / len(cit):.1f}%)")
    out.append("")
    out.append("file con piu' citazioni NON piu' al loro posto (spostate o cambiate):")
    brutti = sorted(per_file.items(), key=lambda x: -(sum(x[1].values()) - x[1]["stessa_riga"]))[:20]
    for f, cn in brutti:
        out.append(f"  {f:<62} tot={sum(cn.values()):>3} stessa={cn['stessa_riga']:>3} spostata={cn['spostata']:>3} cambiata/sparita={cn['TESTO_CAMBIATO_O_SPARITO']:>3}")
    out.append("")
    # numstat per cartella
    ns = c.git("diff", "--numstat", f"{BASE}..HEAD").splitlines()
    agg: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0, 0])
    for r_ in ns:
        a, d, p = r_.split("\t", 2)
        if a == "-":
            continue
        k = "/".join(p.split("/")[:2]) if p.startswith(("Betfair/", "frontend/")) else p.split("/")[0]
        agg[k][0] += 1
        agg[k][1] += int(a)
        agg[k][2] += int(d)
    out.append(f"git diff --numstat {BASE}..HEAD: file toccati {len(ns)}")
    out.append(f"{'cartella':<46}{'file':>6}{'+righe':>9}{'-righe':>9}")
    for k, (nf, a, d) in sorted(agg.items(), key=lambda x: -(x[1][1] + x[1][2]))[:30]:
        out.append(f"{k:<46}{nf:>6}{a:>9}{d:>9}")
    out.append("")
    ns2 = c.git("diff", "--name-status", f"{BASE}..HEAD").splitlines()
    st = collections.Counter(x.split("\t")[0][0] for x in ns2)
    out.append(f"name-status {BASE}..HEAD: " + ", ".join(f"{k}={v}" for k, v in sorted(st.items())))
    nuovi_prod = [x.split("\t")[1] for x in ns2 if x.startswith("A") and x.split("\t")[1].endswith(".py")
                  and x.split("\t")[1].startswith("Betfair/") and "/tests/" not in x and "/tools/" not in x and "/test_" not in x]
    out.append(f"file Python di produzione AGGIUNTI dopo il 02/10 ({len(nuovi_prod)}):")
    for p in nuovi_prod:
        out.append(f"  {p}")
    tolti_prod = [x.split("\t")[1] for x in ns2 if x.startswith("D") and x.split("\t")[1].endswith(".py")
                  and not x.split("\t")[1].startswith(("AUDIT", "_AUDIT"))]
    out.append(f"file Python TOLTI dopo il 02/10 (non audit): {len(tolti_prod)}")
    for p in tolti_prod[:20]:
        out.append(f"  {p}")
    out.append("")
    out.append(f"commit dopo {BASE}: " + c.git("rev-list", "--count", f"{BASE}..HEAD").strip() + "; data base: " + c.git("log", "-1", "--format=%cs", BASE).strip())
    out.append("")
    out.append("righe oggi dei file piu' grandi (inventario 02/10 I-1: valori al 02/10 tra parentesi dove noti)")
    note = {"Betfair/safe_strategy/bot_service.py": 10862, "Betfair/omega/omega_service.py": 8709, "Betfair/mike/service.py": 7496,
            "Betfair/mike/engine.py": 5097, "Betfair/stream/live_order_worker.py": 3991, "Betfair/safe_strategy/service.py": 3444}
    for f, v in note.items():
        b = git_show(BASE, f)
        h = git_show("HEAD", f)
        out.append(f"  {f:<46} 02/10 (dichiarato) {v:>6} | a {BASE} {len(b) if b else '-':>6} | oggi {len(h) if h else '-':>6}")
    c.scrivi("c01_confronto_0210.txt", "\n".join(out) + "\n")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
