"""I chiamati di una funzione in un profilo. Uso: python profilo_chiamati.py PROFILO.prof NOME_FUNZIONE [FRAMMENTO_FILE]"""
import sys
import pstats

st = pstats.Stats(sys.argv[1])
nome = sys.argv[2]
fr = sys.argv[3] if len(sys.argv) > 3 else ""
for (f, l, fn), v in st.stats.items():
    if fn == nome and fr in f.replace("\\", "/"):
        print(f"== {f.replace(chr(92), '/').split('/')[-1]}:{l}:{fn} cumulato {v[3]:.2f}")
        figli = []
        for (f2, l2, fn2), v2 in st.stats.items():
            if (f, l, fn) in v2[4]:
                c = v2[4][(f, l, fn)]
                figli.append((c[3], c[2], c[0], f"{f2.replace(chr(92), '/').split('/')[-1]}:{l2}:{fn2}"))
        for ct, tt, nc, n in sorted(figli, reverse=True)[:20]:
            print(f"   cumulato {ct:7.2f} proprio {tt:6.2f} chiamate {nc:>8}  {n}")
