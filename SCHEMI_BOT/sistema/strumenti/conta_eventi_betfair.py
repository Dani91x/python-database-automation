import re, glob, os, collections, sys
D=sys.argv[1]
PAT=re.compile(r"(?:Order|Market)Stream: \d+\]: SUCCESS|cert login \.it OK|certlogin SUCCESS|FEED_RIPIEGO_REST|FEED_RIENTRO_STREAM|keepAlive sessione|Updated marketCatalogue|Created marketCatalogue|cleared orders found|Client update account details|saldo riletto dopo [a-z]+|MarketStream: \d+\]: \d+ added|sottoscrizione a caldo")
def norm(s): return re.sub(r"Stream: \d+", "Stream: X", re.sub(r"\]: \d+ added", "]: N added", s))
for titolo, lo, hi in (("intera sessione 14:25-15:16 UTC", "", "9"), ("finestra 5 min 15:11:40-15:16:40 UTC", "2026-10-02T15:11:40", "2026-10-02T15:16:40")):
    print(f"\n### Eventi Betfair visibili nei log ({titolo})")
    for f in sorted(glob.glob(os.path.join(D,"*.log"))):
        c=collections.Counter()
        for line in open(f,encoding="utf-8",errors="replace"):
            ts=line[:24]
            if not (lo<=ts<hi): continue
            for m in PAT.findall(line): c[norm(m)]+=1
        if c:
            print("== "+os.path.basename(f).split("_")[0])
            for k,v in c.most_common(): print(f"   {v:5d}  {k}")
