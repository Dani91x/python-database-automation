import json, sys, numpy as np, datetime as dt
D=json.load(open(sys.argv[1]))
P=lambda s: dt.datetime.fromisoformat(s)
rows=[]
for r in D:
    o=r.get('oou') or {}
    if not (o.get('Over 3.5',0)>1 and o.get('Under 3.5',0)>1): continue
    pc=((r.get('mc') or {}).get('over_3_5') or {}).get('True'); pr=((r.get('m') or {}).get('over_3_5') or {}).get('True')
    if pc is None or pr is None: continue
    a=1/o['Over 3.5']; b=1/o['Under 3.5']; q=a/(a+b)
    y=float(r['result_home_goals']+r['result_away_goals']>3)
    pre = P(r['p_gen'])<P(r['fixture_date'])
    rows.append((q,float(pc),float(pr),y,pre))
A=np.array(rows)
def ll(p,y): p=np.clip(p,1e-6,1-1e-6); return -(y*np.log(p)+(1-y)*np.log(1-p))
for lab,M in (('tutte',A),('solo pre-KO',A[A[:,4]==1])):
    q,pc,pr,y=M[:,0],M[:,1],M[:,2],M[:,3]
    lq,lc,lr=ll(q,y),ll(pc,y),ll(pr,y); clim=ll(np.full_like(y,y.mean()),y)
    rng=np.random.default_rng(3); d=lc-lq; bs=[d[rng.integers(0,len(d),len(d))].mean() for _ in range(2000)]
    best=min(((w,ll(w*pc+(1-w)*q,y).mean()) for w in np.linspace(0,1,11)),key=lambda t:t[1])
    print(f'O3.5 {lab} n={len(y)} tasso={y.mean():.3f} LL Q={lq.mean():.4f} Pcal={lc.mean():.4f} Pgrezzo={lr.mean():.4f} clim={clim.mean():.4f} d(Pcal-Q)={d.mean():+.4f} IC95=[{np.percentile(bs,2.5):+.4f},{np.percentile(bs,97.5):+.4f}] w*={best[0]:.1f} LLmix={best[1]:.4f}')
