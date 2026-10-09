import numpy as np
rng=np.random.default_rng(7)
def ece_bin(y,p,nb=10):
    # 2 classi: come _ece_score (media ECE sulle due classi)
    tot=0
    for yy,pp in ((y,p),(1-y,1-p)):
        e=0;n=len(yy)
        edges=np.linspace(0,1,nb+1)
        for i in range(nb):
            m=(pp>=edges[0])&(pp<=edges[1]) if i==0 else (pp>edges[i])&(pp<=edges[i+1])
            if m.sum(): e+=m.sum()*abs(yy[m].mean()-pp[m].mean())
        tot+=e/n
    return tot/2
# 1) predittore costante = tasso base: BSS (formula del gate, brier sommato sulle 2 classi)
for base in (0.5,0.6,0.673,0.70,0.74,0.80):
    b=2*base*(1-base); print("tasso %.3f  BSS costante = %.3f  passa(>=0.12)=%s"%(base,1-b/0.5,1-b/0.5>=0.12))
# 2) modello perfettamente calibrato, p ~ Beta, n holdout: quota con ECE>0.10 e dispersione Brier
for n in (20,40,87,110,170,400):
    f=0;bs=[]
    for _ in range(4000):
        p=rng.beta(2.5,2.5,n)*0.8+0.1  # probabilita' vere
        y=(rng.random(n)<p).astype(float)
        f+=ece_bin(y,p)>0.10; bs.append(2*np.mean((p-y)**2))
    bs=np.array(bs); print("n=%3d ECE>0.10 nel %.0f%% (modello perfetto) ; Brier sd %.3f (p5-p95 %.3f-%.3f)"%(n,100*f/4000,bs.std(),*np.percentile(bs,[5,95])))
