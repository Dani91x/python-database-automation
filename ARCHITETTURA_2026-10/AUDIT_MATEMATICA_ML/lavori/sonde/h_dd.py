# h_: D R4, drawdown SQL (peak = max(equity) sulle righe, senza 0 iniziale) vs TS (peak parte da 0), serie pnl giornaliera [-10,-20]
pnl=[-10,-20]
eq=[];c=0
for p in pnl: c+=p; eq.append(c)
sql=min(e-max(eq[:i+1]) for i,e in enumerate(eq)); ts=0;peak=0
for e in eq: peak=max(peak,e); ts=max(ts,peak-e)
print("equity",eq,"SQL max dd",-sql,"TS max dd",ts)
