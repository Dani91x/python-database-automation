import json, numpy as np
D = json.load(open(r"ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML/lavori/sonde/m_dati.json"))
for key in ("over_2_5","btts","over_3_5","over_1_5"):
    for nm,src in (("raw","m"),("cal","mc")):
        ys=[];ps=[]
        for r in D:
            if r["result_home_goals"] is None or not r.get(src) or key not in r[src]: continue
            hg,ag=r["result_home_goals"],r["result_away_goals"]
            y={"over_2_5":hg+ag>2,"btts":hg>0 and ag>0,"over_3_5":hg+ag>3,"over_1_5":hg+ag>1}[key]
            ys.append(int(y)); ps.append(r[src][key]["True"])
        ys=np.array(ys);ps=np.array(ps)
        print(key,nm,"n",len(ys),"min",ps.min().round(3),"max",ps.max().round(3))
        for lo,hi in ((0,.2),(.2,.3),(.3,.4),(.4,.5),(.5,.6),(.6,.7),(.7,.8),(.8,1.01)):
            m=(ps>=lo)&(ps<hi)
            if m.sum()>=15: print("   bin %.1f-%.1f n=%4d pred %.3f obs %.3f"%(lo,hi,m.sum(),ps[m].mean(),ys[m].mean()))
