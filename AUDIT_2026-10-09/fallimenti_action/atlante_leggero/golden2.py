# golden calcolati col codice di produzione del checkout indicato in PYTHONPATH (principale = master c4fc5fbf)
import json, hashlib, copy, os, sys, tempfile, datetime as dt, importlib.util
spec = importlib.util.spec_from_file_location("tgl", r"C:\Users\Admin\Desktop\PYTHON DATABASE\wt-atlante\Betfair\stream\tests\test_atlante_globale_leggero_2026_10_09.py")
from Betfair.stream.scalper import genera_atlante as G, atlante_a_domanda as AD, hazard_atlas as HA
print("codice da:", G.__file__)
tgl = importlib.util.module_from_spec(spec); spec.loader.exec_module(tgl)
assert tgl.G is G
st = tgl._stati_finti()
print("leghe", list(st), "h2h 61:", list(st["61"]["h2h"]))
seme = json.load(open(HA.ATLAS_V3_PATH, encoding="utf-8"))
b = tgl._compatto(G.assembla(copy.deepcopy(st), generated_at=tgl.GEN, watermark=tgl.WM, seme=seme))
print("assembla", hashlib.sha256(b).hexdigest())
d = tempfile.mkdtemp()
class P:  # tmp_path minimale
    def __truediv__(s, n): import pathlib; return pathlib.Path(d) / n
print("domanda", hashlib.sha256(tgl._file_domanda(P(), st)).hexdigest())
