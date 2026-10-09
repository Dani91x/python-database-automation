import json, sys, datetime as dt, numpy as np
from collections import Counter
D=json.load(open(sys.argv[1]))
P=lambda s: dt.datetime.fromisoformat(s.replace('Z','+00:00')) if s else None
# --- M1: post-kickoff
post=[];hrs=Counter();genh=Counter();n=0
for r in D:
    ko=P(r['fixture_date']); g=P(r['p_gen'])
    if not ko or not g: continue
    n+=1
    if g>ko:
        post.append(r); hrs[ko.hour]+=1; genh[g.hour]+=1
print('M1 Poisson post-KO',len(post),'/',n, f'{len(post)/n:.3%}')
print(' ora UTC KO dei post-KO',sorted(hrs.items()))
print(' ora UTC generazione dei post-KO',sorted(genh.items()))
# sotto il nuovo orario: catena parte 00:12 UTC; se Today gira ~01:30 UTC
for cut in (1,2,3):
    c=sum(1 for r in D if P(r['fixture_date']).hour<cut and P(r['fixture_date']).date()==P(r['p_gen']).date())
    print(f' partite con KO prima delle {cut:02d}:00 UTC stesso giorno della generazione:',c)
mlpost=sum(1 for r in D if r.get('ml_gen') and P(r['ml_gen'])>P(r['fixture_date']))
print(' ML post-KO',mlpost,'/',sum(1 for r in D if r.get('ml_gen')))
# fusi: tutti +00:00?
print(' suffissi fixture_date',Counter(r['fixture_date'][-6:] for r in D), 'p_gen',Counter((r['p_gen'] or '')[-6:] for r in D))
# --- MA2: RPS 1X2 Q molt vs Pcal (campione con ML come in M, e senza)
def rps(p,y):
    F=np.cumsum(p)[:2]; O=np.cumsum(y)[:2]; return ((F-O)**2).sum()/2
def vec(d,k):
    try: v=np.array([float(d[x]) for x in k]); return v/v.sum()
    except Exception: return None
for withml in (False,True):
    dq=[];dp=[];dr=[]
    for r in D:
        o=r.get('o1x2') or {}
        if not all(o.get(k,0)>1 for k in ('Home','Draw','Away')): continue
        if withml and not isinstance(r.get('ml1'),dict): continue
        pc=vec((r.get('mc') or {}).get('1x2') or {},['H','D','A']); pr=vec((r.get('m') or {}).get('1x2') or {},['H','D','A'])
        if pc is None or pr is None: continue
        q=1/np.array([o['Home'],o['Draw'],o['Away']]); q/=q.sum()
        h,a=r['result_home_goals'],r['result_away_goals']; y=np.array([h>a,h==a,h<a],float)
        dq.append(rps(q,y)); dp.append(rps(pc,y)); dr.append(rps(pr,y))
    dq,dp,dr=map(np.array,(dq,dp,dr)); d=dp-dq
    rng=np.random.default_rng(1); bs=[d[rng.integers(0,len(d),len(d))].mean() for _ in range(2000)]
    print(f'MA2 withml={withml} n={len(d)} RPS Q={dq.mean():.4f} Pcal={dp.mean():.4f} Pgrezzo={dr.mean():.4f} diff={d.mean():+.4f} IC95=[{np.percentile(bs,2.5):+.4f},{np.percentile(bs,97.5):+.4f}]')
# pre-KO only
# --- M3: pendenza O2.5
def slope(ps,ys):
    x=np.log(ps/(1-ps)); X=np.c_[np.ones_like(x),x]; b=np.zeros(2)
    for _ in range(50):
        p=1/(1+np.exp(-X@b)); W=p*(1-p); H=X.T@(X*W[:,None]); g=X.T@(ys-p); b+=np.linalg.solve(H,g)
    se=np.sqrt(np.diag(np.linalg.inv(H))); return b[1],se[1]
for key in ('m','mc'):
    ps=[];ys=[];ps_all=[];ys_all=[]
    for r in D:
        mm=(r.get(key) or {}).get('over_2_5') or {}
        p=mm.get('True')
        if p is None: continue
        p=min(max(float(p),1e-4),1-1e-4); y=float(r['result_home_goals']+r['result_away_goals']>2)
        ps_all.append(p); ys_all.append(y)
        o=r.get('oou') or {}
        if o.get('Over 2.5',0)>1 and o.get('Under 2.5',0)>1: ps.append(p); ys.append(y)
    for lab,a,b in (('con quote O/U',ps,ys),('tutte',ps_all,ys_all)):
        s,se=slope(np.array(a),np.array(b)); print(f'M3 {key} O2.5 {lab} n={len(a)} pendenza={s:.3f}+-{se:.3f}')
