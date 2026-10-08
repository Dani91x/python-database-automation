"""Spiega ogni frame diverso fra la fixture (curator prima di 9e86c3a) e la rigenerata
(curator di oggi): righe curate prima/dopo, inclusione, righe aggiunte e loro natura.
Solo lettura del repo; i file temporanei stanno in una cartella temporanea."""
import importlib.util, sys, os, json, tempfile
R = sys.argv[1]; vecchio = sys.argv[2]
spec = importlib.util.spec_from_file_location("g", os.path.join(R, "tools/replay_barra_fixture.py"))
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
sc = importlib.util.spec_from_file_location("curator_vecchio", vecchio)
cv = importlib.util.module_from_spec(sc); sc.loader.exec_module(cv)


def chiave(r):
    return (r["market_id"], r["ts"], r["status"], r["inplay"], json.dumps(r["ladder"], sort_keys=True))


for ev in sys.argv[3:]:
    _, mm = g.righe_punteggio(ev)
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "l.jsonl")
        cat = g.libri_dallo_stream(ev, p)
        prima = cv.curate_event(p, ev, cadence_sec=10.0, timeline=mm or None)
        dopo = g.curate_event(p, ev, cadence_sec=10.0, timeline=mm or None)
    kp = [chiave(r) for r in prima]; kd = [chiave(r) for r in dopo]
    sp, sd = set(kp), set(kd)
    print(f"== {ev}: righe curate prima {len(prima)} dopo {len(dopo)}; prima contenute in dopo: {sp <= sd}; tolte {len(sp - sd)}; aggiunte {len(sd - sp)}")
    agg = [r for r in dopo if chiave(r) not in sp]
    # ogni riga aggiunta: lo stato precedente del suo mercato nelle righe di DOPO
    ultimo = {}
    for r in dopo:
        if chiave(r) not in sp:
            prev = ultimo.get(r["market_id"])
            mt = cat.get(r["market_id"], {}).get("market_type")
            print(f"   + {r['ts']} {r['market_id']} {mt} {prev} -> {(r['status'], r['inplay'])}")
        ultimo[r["market_id"]] = (r["status"], r["inplay"])
    # quali frame del campionamento cambiano
    fp, mp = g.campiona_come_la_pagina([dict(r) for r in prima], len(cat))
    fd, md = g.campiona_come_la_pagina([dict(r) for r in dopo], len(cat))
    tp = {(f["market_id"], f["ts"]) for f in fp}; td = {(f["market_id"], f["ts"]) for f in fd}
    print(f"   frame campionati prima {len(fp)} dopo {len(fd)}; meta prima {mp} dopo {md}")
    for x in sorted(td - tp):
        print("   frame nuovo:", x, cat.get(x[0], {}).get("market_type"))
    for x in sorted(tp - td):
        print("   frame uscito:", x, cat.get(x[0], {}).get("market_type"))
