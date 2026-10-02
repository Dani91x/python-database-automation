import re, sys, glob, os, collections
from datetime import datetime, timedelta
D = sys.argv[1]
END = datetime.fromisoformat(sys.argv[2])  # UTC naive
RX = re.compile(r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)Z .*HTTP Request: (\w+) https://[^/]+/rest/v1/([^?" ]+)')
for f in sorted(glob.glob(os.path.join(D, '*.log'))):
    name = os.path.basename(f).split('_')[0]
    w = {60: collections.Counter(), 300: collections.Counter()}
    tot = collections.Counter(); first = last = None
    for line in open(f, encoding='utf-8', errors='replace'):
        m = RX.match(line)
        if not m: continue
        t = datetime.fromisoformat(m.group(1)[:23])
        key = f"{m.group(2)} {m.group(3)}"
        tot[key] += 1; first = first or t; last = t
        for s in w:
            if END - timedelta(seconds=s) <= t < END: w[s][key] += 1
    print(f"\n### {name}  (righe HTTP totali {sum(tot.values())}, dal {first} al {last} UTC)")
    for s in (60, 300):
        c = w[s]; n = sum(c.values())
        print(f"-- finestra {s}s fino a {END} UTC: {n} chiamate ({n*60/s:.0f}/min)")
        for k, v in c.most_common(): print(f"   {v:5d}  {k}")
    if not w[300] and tot:
        mins = max((last-first).total_seconds()/60, 1/60)
        print(f"-- (fuori finestra) intera sessione: {sum(tot.values())} in {mins:.1f} min")
        for k, v in tot.most_common(): print(f"   {v:5d}  {k}")
