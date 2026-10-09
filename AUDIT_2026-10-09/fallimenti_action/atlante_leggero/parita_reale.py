# Parita' reale: scarica (dalle righe per lega) vs payload intero di prima, sullo stato VERO locale (sola lettura)
import json, hashlib, os, tempfile, copy
from Betfair.stream.scalper import genera_atlante as G, hazard_atlas as HA, hazard_atlas_sync as SY
from Betfair.stream.tests.test_atlante_globale_leggero_2026_10_09 import _db_finto, _righe_leghe, _compatto
MAIN = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\Betfair\omega\data"
stato = json.load(open(MAIN + r"\hazard_atlas_stato.json", encoding="utf-8"))["leghe"]
# ordine come la action: league_id crescente (leggi_stato_db)
stato = {k: stato[k] for k in sorted(stato, key=int)}
seme = json.load(open(HA.ATLAS_V3_PATH, encoding="utf-8"))
GEN = "2026-10-09T07:25:00+00:00"
atlas = G.assembla(copy.deepcopy(stato), generated_at=GEN, watermark=10500510, seme=seme)
atlas["meta"]["run"] = {"conti": {}, "leghe_toccate": [], "richieste_db": 1, "righe_lette": 1, "secondi": 1.0}
prima = _compatto(json.loads(json.dumps(atlas)))
d = tempfile.mkdtemp(); live = os.path.join(d, "live.json")
get = _db_finto([{"id": 14, "generated_at": GEN, "payload": G.payload_globale_leggero(atlas)}], _righe_leghe(stato))
r = SY.sincronizza(url="http://x", key="k", path=live, get=get)
dopo = open(live, "rb").read()
print(r, "leghe", len(stato), "GET leghe", sum(1 for c in get.chiamate if c[0] == "hazard_atlas_leghe"))
print("prima", len(prima), hashlib.sha256(prima).hexdigest())
print("dopo ", len(dopo), hashlib.sha256(dopo).hexdigest(), "byte identici:", prima == dopo,
      "valori uguali:", json.loads(prima) == json.loads(dopo))
