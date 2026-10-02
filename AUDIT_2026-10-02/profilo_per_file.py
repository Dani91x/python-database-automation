"""Tempo PROPRIO (tottime) di un profilo cProfile aggregato per file, e i punti
caldi per tempo cumulato. Uso: python profilo_per_file.py PROFILO.prof [N]"""
import collections
import pstats
import sys


def corto(f):
    f = f.replace("\\", "/")
    for k in ("site-packages/", "agent-a3973176466e94888/", "Lib/"):
        if k in f:
            return f.split(k, 1)[1]
    return f


st = pstats.Stats(sys.argv[1])
n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
agg = collections.Counter()
for (f, l, fn), (cc, nc, tt, ct, callers) in st.stats.items():
    agg[corto(f)] += tt
tot = sum(agg.values())
print(f"TEMPO PROPRIO PER FILE (totale {tot:.1f} s con profilo)")
for f, t in agg.most_common(n):
    print(f"{t:8.2f} {100 * t / tot:5.1f}%  {f}")
