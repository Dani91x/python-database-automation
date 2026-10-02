"""Le righe diverse fra due referti (normalizzati come `confronta_referti.py`),
mostrate PEZZO PER PEZZO (separatore ' | ') per vedere dove differiscono.
Uso: python diff_righe.py PRIMA.txt DOPO.txt"""
import importlib.util
import os
import sys

qui = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("cr", os.path.join(qui, "confronta_referti.py"))
sys_argv = sys.argv
sys.argv = [sys_argv[0], sys_argv[1], sys_argv[1]]
cr = importlib.util.module_from_spec(spec)
import contextlib, io  # noqa: E401
with contextlib.redirect_stdout(io.StringIO()):
    spec.loader.exec_module(cr)
a, b = cr.norma(sys_argv[1]), cr.norma(sys_argv[2])
for i, (x, y) in enumerate(zip(a, b)):
    if x != y:
        pa, pb = x.split(" | "), y.split(" | ")
        print(f"riga {i + 1}:")
        for j in range(max(len(pa), len(pb))):
            u = pa[j] if j < len(pa) else "<assente>"
            v = pb[j] if j < len(pb) else "<assente>"
            if u != v:
                print(f"  pezzo {j}:\n    PRIMA {u}\n    DOPO  {v}")
