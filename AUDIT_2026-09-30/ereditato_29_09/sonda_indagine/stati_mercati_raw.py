"""Legge (streaming) le registrazioni GREZZE dello stream e stampa i cambi di
stato (marketDefinition.status) dei mercati OVER_UNDER_*, per capire se Betfair
CHIUDE una linea superata prima della fine della partita."""
import json
import os
import sys
from datetime import datetime, timezone

base = "C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/_live_raw"
eventi = sys.argv[1:] or sorted(os.listdir(base))
for ev in eventi:
    p = os.path.join(base, ev, f"{ev}.raw.jsonl")
    if not os.path.exists(p):
        continue
    tipi = {}
    ultimo = {}
    cambi = []
    ultimo_pt = {}
    with open(p, encoding="utf-8") as f:
        for riga in f:
            if '"mc"' not in riga:
                continue
            try:
                m = json.loads(riga)
            except ValueError:
                continue
            pt = m.get("pt")
            for mc in m.get("mc") or []:
                mid = mc.get("id")
                ultimo_pt[mid] = pt
                md = mc.get("marketDefinition")
                if not md:
                    continue
                tipi[mid] = md.get("marketType")
                st = (md.get("status"), md.get("inPlay"),
                      tuple(sorted((r.get("id"), r.get("status")) for r in md.get("runners") or [])))
                if ultimo.get(mid) != st:
                    ultimo[mid] = st
                    cambi.append((pt, mid, st))
    righe = [(pt, mid, st) for pt, mid, st in cambi if str(tipi.get(mid) or "").startswith("OVER_UNDER")]
    chiusi = [r for r in righe if r[2][0] == "CLOSED"]
    print("==", ev, "mercati OU:", len({r[1] for r in righe}), "chiusure:", len(chiusi))
    for pt, mid, st in righe:
        if st[0] in ("SUSPENDED",) and "-v" not in sys.argv:
            continue
        h = datetime.fromtimestamp(pt / 1000, tz=timezone.utc).strftime("%H:%M:%S")
        print("  ", h, mid, tipi.get(mid), st[0], "inplay", st[1], [s for _i, s in st[2]],
              "ultimo msg", datetime.fromtimestamp((ultimo_pt.get(mid) or 0) / 1000,
                                                   tz=timezone.utc).strftime("%H:%M:%S"))
