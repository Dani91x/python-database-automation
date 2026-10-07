"""Dalla registrazione GREZZA (nessun replay): per i mercati indicati, gli
intervalli in cui il book NON ha un solo prezzo (ladder vuoto su tutti i
runner) e gli intervalli SOSPESO. Lo scanner dichiara un mercato fermo quando
il suo ultimo book non ha prezzi (MOTIVO_SENZA_PREZZI) o non riceve conferme.
uso: ht_vuoto.py <file raw> <market_id> [...]"""
import json, sys
from datetime import datetime, timezone

fn = sys.argv[1]
mids = set(sys.argv[2:])
lad = {m: {} for m in mids}       # mid -> sid -> {"atb": {p: s}, "atl": {p: s}}
stato = {m: None for m in mids}
vuoto_da = {m: None for m in mids}
susp_da = {m: None for m in mids}
inplay_da = None
out = []


def hh(pt):
    return datetime.fromtimestamp(pt / 1000, tz=timezone.utc).strftime("%H:%M:%S")


def ha_prezzi(mid):
    return any(any(s > 0 for s in d["atb"].values()) or any(s > 0 for s in d["atl"].values())
               for d in lad[mid].values())


with open(fn) as fh:
    for riga in fh:
        try:
            msg = json.loads(riga)
        except ValueError:
            continue
        pt = msg.get("pt")
        for mc in msg.get("mc") or []:
            mid = mc.get("id")
            if mid not in mids:
                continue
            if mc.get("img"):
                lad[mid] = {}
            md = mc.get("marketDefinition")
            if md:
                if md.get("inPlay") and inplay_da is None:
                    inplay_da = pt
                st = md.get("status")
                if st != stato[mid]:
                    if st == "SUSPENDED":
                        susp_da[mid] = pt
                    elif stato[mid] == "SUSPENDED" and susp_da[mid] is not None:
                        out.append((mid, "SOSPESO", hh(susp_da[mid]), hh(pt), (pt - susp_da[mid]) / 1000))
                        susp_da[mid] = None
                    stato[mid] = st
            for rc in mc.get("rc") or []:
                d = lad[mid].setdefault(rc["id"], {"atb": {}, "atl": {}})
                for k in ("atb", "atl"):
                    for p, s in rc.get(k) or []:
                        if s == 0:
                            d[k].pop(p, None)
                        else:
                            d[k][p] = s
            pieno = ha_prezzi(mid)
            if not pieno and vuoto_da[mid] is None:
                vuoto_da[mid] = pt
            elif pieno and vuoto_da[mid] is not None:
                out.append((mid, "SENZA PREZZI", hh(vuoto_da[mid]), hh(pt), (pt - vuoto_da[mid]) / 1000))
                vuoto_da[mid] = None
print("in gioco dalle", hh(inplay_da) if inplay_da else None)
for r in out:
    print(*r)
for m in mids:
    if vuoto_da[m] is not None:
        print(m, "SENZA PREZZI dalle", hh(vuoto_da[m]), "fino alla fine")
