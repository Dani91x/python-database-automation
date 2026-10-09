import json, numpy as np, datetime as dt
D = json.load(open(r"ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML/lavori/sonde/m_dati.json"))
for r in D:
    if r["ml1"]:
        print("ml1", r["ml1"], "mlo", r["mlo"], "mlb", r["mlb"], "ml_gen", r["ml_gen"], "ml_run", r["ml_run"]); break
def P(s): return dt.datetime.fromisoformat(s.replace("Z","+00:00")) if s else None
# M1: previsioni generate dopo il KO
npo=nml=0; nml_tot=0
for r in D:
    ko=P(r["fixture_date"])
    pg=P(r["p_gen"]) or P(r["created_at"])
    if pg and ko and pg>ko: npo+=1
    if r["ml_gen"]:
        nml_tot+=1
        if P(r["ml_gen"])>ko: nml+=1
print("M1 poisson post-KO", npo, "/", len(D), "ml post-KO", nml, "/", nml_tot)
# serie confrontabili
def ll(y,p): p=np.clip(p,1e-12,1-1e-12); return -(y*np.log(p)+(1-y)*np.log(1-p))
def dv2(o1,o2):
    a,b=1/o1,1/o2; return a/(a+b)
rng=np.random.default_rng(1)
def boot(d,n=2000):
    idx=rng.integers(0,len(d),(n,len(d))); m=d[idx].mean(1); return d.mean(), np.percentile(m,2.5), np.percentile(m,97.5)
for mk,key,keyo,ok in (("O2.5","over_2_5","mlo",("Over 2.5","Under 2.5")),("BTTS","btts","mlb",("Yes","No"))):
    ys=[];pml=[];pq=[];ppr=[];ppc=[]
    for r in D:
        if r["result_home_goals"] is None or not r[keyo]: continue
        oo=r["oou"] if mk=="O2.5" else r["obt"]
        if not oo or not oo.get(ok[0]) or not oo.get(ok[1]): continue
        hg,ag=r["result_home_goals"],r["result_away_goals"]
        y=int(hg+ag>2) if mk=="O2.5" else int(hg>0 and ag>0)
        v=r[keyo]; pm=v.get("True", v.get("Yes")) if isinstance(v,dict) else v
        if pm is None: continue
        ys.append(y);pml.append(pm);pq.append(dv2(oo[ok[0]],oo[ok[1]]));ppr.append(r["m"][key]["True"]);ppc.append(r["mc"][key]["True"])
    ys=np.array(ys);pml=np.array(pml);pq=np.array(pq);ppr=np.array(ppr);ppc=np.array(ppc)
    base=ys.mean(); n=len(ys)
    print(f"\n{mk}: n={n} tasso={base:.3f}")
    for nm,p in (("ML",pml),("quote",pq),("Poisson raw",ppr),("Poisson cal",ppc)):
        print(f"  logloss {nm:12s} {ll(ys,p).mean():.4f}")
    print(f"  logloss clim(in-sample) {ll(ys,np.full(n,base)).mean():.4f}")
    d=ll(ys,pml)-ll(ys,np.full(n,base)); print("  ML - clim", boot(d))
    d=ll(ys,pml)-ll(ys,pq); print("  ML - quote", boot(d))
    d=ll(ys,ppr)-ll(ys,np.full(n,base)); print("  PoissonRaw - clim", boot(d))
    # pendenza logistica: y ~ a + b*logit(p)
    def slope(p):
        x=np.log(np.clip(p,1e-6,1-1e-6)/(1-np.clip(p,1e-6,1-1e-6)))
        b,a=0.0,np.log(base/(1-base))
        for _ in range(100):  # Newton
            z=a+b*x; q=1/(1+np.exp(-z)); w=q*(1-q)
            g=np.array([(ys-q).sum(),((ys-q)*x).sum()]); H=np.array([[w.sum(),(w*x).sum()],[(w*x).sum(),(w*x*x).sum()]])
            st=np.linalg.solve(H,g); a+=st[0]; b+=st[1]
        return b
    print("  pendenza logit raw %.3f cal %.3f ml %.3f quote %.3f"%(slope(ppr),slope(ppc),slope(pml),slope(pq)))
# 1X2 RPS
def rps(p,k): 
    c=np.cumsum(p)[:2]; o=np.cumsum(np.eye(3)[k])[:2]; return ((c-o)**2).sum()/2
R=[];Rc=[];Q=[];ML=[]
for r in D:
    if r["result_home_goals"] is None or not r["o1x2"]: continue
    o=r["o1x2"]
    if not all(o.get(k) for k in ("Home","Draw","Away")): continue
    hg,ag=r["result_home_goals"],r["result_away_goals"]; k=0 if hg>ag else (1 if hg==ag else 2)
    q=np.array([1/o["Home"],1/o["Draw"],1/o["Away"]]); q/=q.sum()
    ph=lambda m:np.array([m["1x2"]["H"],m["1x2"]["D"],m["1x2"]["A"]])
    R.append(rps(ph(r["m"]),k));Rc.append(rps(ph(r["mc"]),k));Q.append(rps(q,k))
    if r["ml1"]: ML.append((rps(np.array([r["ml1"]["H"],r["ml1"]["D"],r["ml1"]["A"]]),k),rps(q,k)))
R,Rc,Q=map(np.array,(R,Rc,Q))
print("\n1X2 n=",len(R),"RPS poisson raw %.4f cal %.4f quote %.4f"%(R.mean(),Rc.mean(),Q.mean()))
print("  raw-quote",boot(R-Q)); print("  cal-quote",boot(Rc-Q)); print("  raw-cal",boot(R-Rc))
if ML: ML=np.array(ML); print("  ML n",len(ML),"RPS ml %.4f quote %.4f diff"%(ML[:,0].mean(),ML[:,1].mean()),boot(ML[:,0]-ML[:,1]))
