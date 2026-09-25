# valori d'oro della griglia V3 PRIMA di O5: HEAD:Betfair/omega/omega_v3.py caricato a parte
import importlib.util
import subprocess
import sys
import tempfile
import os

src = subprocess.run(["git", "show", "HEAD:Betfair/omega/omega_v3.py"], capture_output=True,
                     check=True).stdout
d = tempfile.mkdtemp()
f = os.path.join(d, "v3_head.py")
open(f, "wb").write(src)
spec = importlib.util.spec_from_file_location("v3_head", f)
V = importlib.util.module_from_spec(spec)
sys.modules["v3_head"] = V
spec.loader.exec_module(V)

from Betfair.omega import omega_proposte as PR  # noqa: E402

p0 = PR.parametri_modello()
p = V.Parametri(**{k: getattr(p0, k) for k in V.Parametri.__dataclass_fields__})
print("parametri", p)
STATI = [(60.0, (0, 0), "ft", (1.45, 1.10)), (74.0, (1, 0), "ft", (1.80, 0.95)),
         (30.0, (0, 1), "ht", (1.20, 1.30)), (82.0, (2, 2), "ft", None)]
for m, sc, per, lam in STATI:
    g = V.griglia_finale(minuto=m, punteggio=sc, periodo=per, p=p, lambdas=lam)
    firma = sum(v * (1 + 7 * h + 13 * a) for (h, a), v in g.items())
    ir = V.intensita_residue(minuto=m, punteggio=sc, periodo=per, p=p, lambdas=lam)
    cella = (sc[0] + 1, sc[1] + 1)
    print(repr((m, sc, per, lam)), repr(firma), repr(g.get(cella)), repr(ir))
