"""Storia di un mercato nella registrazione grezza: cambi di status/inPlay e
ultimo messaggio con prezzi. uso: storia_mercato.py <file raw> <market_id> [...]"""
import json, sys
from datetime import datetime, timezone

fn = sys.argv[1]
mids = set(sys.argv[2:])
stato = {}
ultimo_rc = {}
primo_rc_dopo = {}
n_rc = {}
def ts(pt):
    return datetime.fromtimestamp(pt / 1000, tz=timezone.utc).strftime("%H:%M:%S")
with open(fn) as fh:
    for riga in fh:
        try:
            m = json.loads(riga)
        except ValueError:
            continue
        pt = m.get("pt")
        for mc in m.get("mc") or []:
            mid = mc.get("id")
            if mid not in mids:
                continue
            md = mc.get("marketDefinition")
            if md:
                s = (md.get("status"), md.get("inPlay"), md.get("marketType"))
                if stato.get(mid) != s:
                    stato[mid] = s
                    print(ts(pt), mid, "definizione", s)
            if mc.get("rc"):
                n_rc[mid] = n_rc.get(mid, 0) + 1
                ultimo_rc[mid] = pt
for mid in mids:
    print(mid, "messaggi con prezzi:", n_rc.get(mid), "ultimo:", ts(ultimo_rc[mid]) if mid in ultimo_rc else None)
