"""Dettaglio di un profilo: funzioni di un file per tempo proprio, e chi chiama i
built-in piu' cari. Uso: python profilo_dettaglio.py PROFILO.prof FRAMMENTO_FILE"""
import pstats
import sys

st = pstats.Stats(sys.argv[1])
frammento = sys.argv[2]
righe = []
for (f, l, fn), (cc, nc, tt, ct, callers) in st.stats.items():
    if frammento in f.replace("\\", "/"):
        righe.append((tt, ct, nc, f"{l}:{fn}"))
for tt, ct, nc, nome in sorted(righe, reverse=True)[:25]:
    print(f"proprio {tt:7.2f}  cumulato {ct:7.2f}  chiamate {nc:>9}  {nome}")
print()
for chiave in ("{method 'get' of 'dict' objects}", "{built-in method builtins.getattr}",
               "{built-in method builtins.round}", "{built-in method builtins.isinstance}"):
    for (f, l, fn), (cc, nc, tt, ct, callers) in st.stats.items():
        if fn == chiave:
            print(chiave, f"{tt:.2f}")
            top = sorted(callers.items(), key=lambda kv: -kv[1][2])[:8]
            for (cf, cl, cfn), v in top:
                print(f"    {v[2]:6.2f} s  {v[0]:>9}  {cf.replace(chr(92), '/').split('/')[-1]}:{cl}:{cfn}")
