# Misura i byte della POST della versione globale sull'atlante VERO (stato locale, sola lettura)
import json, hashlib, sys, urllib.request
from Betfair.stream.scalper import genera_atlante as G, hazard_atlas as HA
MAIN = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\Betfair\omega\data"
stato = json.load(open(MAIN + r"\hazard_atlas_stato.json", encoding="utf-8"))["leghe"]
seme = json.load(open(HA.ATLAS_V3_PATH, encoding="utf-8"))
atlas = G.assembla(stato, generated_at="2026-10-09T07:25:00+00:00", watermark=10500510, seme=seme)
full = json.dumps(atlas, ensure_ascii=True, separators=(",", ":")).encode()
print("atlante assemblato (file):", len(full), hashlib.sha256(full).hexdigest(), "leghe", len(stato))
for k, v in atlas.items():
    print("  ", k, len(json.dumps(v, separators=(",", ":"))))
corpi = []
class R:
    def __enter__(s): return s
    def __exit__(s, *a): return None
    def read(s): return b"[]"
def urlopen(req, timeout=0):
    corpi.append((req.get_method(), req.full_url.split("/rest/v1/")[1][:40], len(req.data or b""), req.data))
    return R()
urllib.request.urlopen = urlopen
G._Scrittore("http://finto", "k", attese=()).salva_versione(atlas, tieni=7)
for m, p, n, d in corpi:
    print("richiesta", m, p, n)
post = corpi[0][3]
top = json.loads(post)["p_payload"]
print("chiavi p_payload:", sorted(top))
