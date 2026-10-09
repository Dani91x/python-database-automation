import json, numpy as np
D = json.load(open(r"ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML/lavori/sonde/m_dati.json"))
def ll(y,p): p=np.clip(p,1e-12,1-1e-12); return -(y*np.log(p)+(1-y)*np.log(1-p))
for mk,key,keyo,ok in (("O2.5","over_2_5","mlo",("Over 2.5","Under 2.5")),("BTTS","btts","mlb",("Yes","No"))):
    ys=[];pml=[];pq=[];ppr=[];ppc=[]
    for r in D:
        if r["result_home_goals"] is None or not r[keyo]: continue
        oo=r["oou"] if mk=="O2.5" else r["obt"]
        if not oo or not oo.get(ok[0]) or not oo.get(ok[1]): continue
        hg,ag=r["result_home_goals"],r["result_away_goals"]
        ys.append(int(hg+ag>2) if mk=="O2.5" else int(hg>0 and ag>0))
        pml.append(r[keyo]["True"]); a,b=1/oo[ok[0]],1/oo[ok[1]]; pq.append(a/(a+b)); ppr.append(r["m"][key]["True"]); ppc.append(r["mc"][key]["True"])
    ys,pml,pq,ppr,ppc=map(np.array,(ys,pml,pq,ppr,ppc))
    print(mk,"OLS pendenza y~p: raw %.3f cal %.3f ml %.3f quote %.3f"%tuple(np.polyfit(p,ys,1)[0] for p in (ppr,ppc,pml,pq)))
    ws=np.linspace(0,1,21); L=[ll(ys,w*pml+(1-w)*pq).mean() for w in ws]
    print("  miscela ML*w+quote*(1-w): w ottimo %.2f (ll %.4f vs quote %.4f)"%(ws[int(np.argmin(L))],min(L),L[0]))
    L=[ll(ys,w*ppc+(1-w)*pq).mean() for w in ws]; print("  Poisson cal+quote: w ottimo %.2f (ll %.4f)"%(ws[int(np.argmin(L))],min(L)))
# 1X2 logloss
Y=[];M=[];Q=[]
for r in D:
    if r["result_home_goals"] is None or not r["o1x2"] or not r["ml1"]: continue
    o=r["o1x2"]
    if not all(o.get(k) for k in ("Home","Draw","Away")): continue
    hg,ag=r["result_home_goals"],r["result_away_goals"]; Y.append(0 if hg>ag else (1 if hg==ag else 2))
    q=np.array([1/o["Home"],1/o["Draw"],1/o["Away"]]); Q.append(q/q.sum()); M.append([r["ml1"]["H"],r["ml1"]["D"],r["ml1"]["A"]])
Y=np.array(Y);M=np.array(M);Q=np.array(Q); n=len(Y)
f=lambda P:-np.log(np.clip(P[np.arange(n),Y],1e-12,1)).mean()
clim=np.tile(np.bincount(Y,minlength=3)/n,(n,1))
print("1X2 n",n,"logloss ML %.4f clim %.4f quote %.4f"%(f(M),f(clim),f(Q)))
ws=np.linspace(0,1,21); L=[f(w*M+(1-w)*Q) for w in ws]; print("  miscela 1X2 w ottimo %.2f"%ws[int(np.argmin(L))])
