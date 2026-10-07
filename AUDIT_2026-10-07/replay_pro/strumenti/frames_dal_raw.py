"""Frame del replay (forma di get_replay_frames) dalla registrazione RAW, per la
prova a schermo: un frame per mercato ogni <passo> ms con il book (atb/atl a 10
livelli, trd, ltp, tv), stato e in gioco. Argomenti: raw, uscita, passo_ms,
mercati(virgola), [dal_ms], [al_ms]."""
import json
import sys
from datetime import datetime, timezone

raw, uscita, passo = sys.argv[1], sys.argv[2], int(sys.argv[3])
mercati = set(sys.argv[4].split(","))
dal = int(sys.argv[5]) if len(sys.argv) > 5 else 0
al = int(sys.argv[6]) if len(sys.argv) > 6 else 10 ** 15
stato = {}
frames = []
ultimo = {}


def iso(ms):
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def applica(lista, dove):
    for p, s in lista or []:
        if s == 0:
            dove.pop(p, None)
        else:
            dove[p] = s


with open(raw, encoding="utf-8") as fh:
    for riga in fh:
        d = json.loads(riga)
        pt = d.get("pt")
        for mc in d.get("mc") or []:
            mid = str(mc.get("id"))
            if mid not in mercati:
                continue
            st = stato.setdefault(mid, {"runners": {}, "status": "OPEN", "inplay": False})
            if mc.get("img"):
                st["runners"] = {}
            md = mc.get("marketDefinition")
            if md:
                st["status"] = md.get("status")
                st["inplay"] = bool(md.get("inPlay"))
            for rc in mc.get("rc") or []:
                r = st["runners"].setdefault(str(rc["id"]), {"atb": {}, "atl": {}, "trd": {}, "ltp": None, "tv": None})
                applica(rc.get("atb"), r["atb"])
                applica(rc.get("atl"), r["atl"])
                applica(rc.get("trd"), r["trd"])
                if "ltp" in rc:
                    r["ltp"] = rc["ltp"]
                if "tv" in rc:
                    r["tv"] = rc["tv"]
            if pt is None or pt < dal or pt > al:
                continue
            b = pt // passo
            if ultimo.get(mid) == b:
                continue
            ultimo[mid] = b
            ladder = {}
            for sid, r in st["runners"].items():
                ladder[sid] = {
                    "back": sorted(([p, s] for p, s in r["atb"].items()), key=lambda x: -x[0])[:10],
                    "lay": sorted(([p, s] for p, s in r["atl"].items()), key=lambda x: x[0])[:10],
                    "ltp": r["ltp"], "tv": r["tv"],
                    "trd": sorted(([p, s] for p, s in r["trd"].items()), key=lambda x: x[0]),
                }
            frames.append({"market_id": mid, "ts": iso(pt), "minute": None, "inplay": st["inplay"],
                           "status": st["status"], "ladder": ladder})
with open(uscita, "w") as f:
    json.dump(frames, f)
print(len(frames))
