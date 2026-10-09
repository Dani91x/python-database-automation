import json, sys, numpy as np
D=json.load(open(sys.argv[1]))
def slope(ps,ys):
    ps=np.clip(np.array(ps),1e-4,1-1e-4); ys=np.array(ys,float)
    x=np.log(ps/(1-ps)); X=np.c_[np.ones_like(x),x]; b=np.zeros(2)
    for _ in range(60):
        p=1/(1+np.exp(-X@b)); W=p*(1-p); H=X.T@(X*W[:,None]); b+=np.linalg.solve(H,X.T@(ys-p))
    return b[1], np.sqrt(np.linalg.inv(H)[1,1]), len(ps)
def ys(r,mk,sel):
    h,a=r['result_home_goals'],r['result_away_goals']
    return {'H':h>a,'D':h==a,'A':h<a,'o25':h+a>2,'o35':h+a>3,'btts':h>0 and a>0}[sel]
for key in ('m','mc'):
    for mk,sel,s2 in (('1x2','H','H'),('1x2','A','A'),('1x2','D','D'),('over_3_5','True','o35'),('btts','True','btts'),('over_2_5','True','o25')):
        P=[];Y=[]
        for r in D:
            v=((r.get(key) or {}).get(mk) or {}).get(sel)
            if v is None: continue
            P.append(float(v)); Y.append(ys(r,mk,s2))
        b,se,n=slope(P,Y); print(f'{key:3s} {mk:9s} {sel:5s} n={n} pendenza={b:.3f}+-{se:.3f}')
# quote O2.5 slope
P=[];Y=[]
for r in D:
    o=r.get('oou') or {}
    if o.get('Over 2.5',0)>1 and o.get('Under 2.5',0)>1:
        q=1/o['Over 2.5']; u=1/o['Under 2.5']; P.append(q/(q+u)); Y.append(ys(r,'','o25'))
print('quote O2.5', slope(P,Y))
