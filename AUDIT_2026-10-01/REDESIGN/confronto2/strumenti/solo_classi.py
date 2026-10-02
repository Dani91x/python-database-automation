# Controllo del diff dei .tsx contro master: ogni riga cambiata deve differire SOLO per classi ds-v2-*/ds-portale-v2-*.
# Uso, dalla radice del repo: python3 AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/solo_classi.py [base=origin/master]
# Verifica che il diff dei .tsx sia SOLO aggiunta di classi ds-v2-*/ds-portale-v2-* (e mappe STATO_V2)
import subprocess,re,sys
base=sys.argv[1] if len(sys.argv)>1 else 'origin/master'
d=subprocess.run(['git','diff','-U0',base,'--','frontend/src/*.tsx','frontend/src/**/*.tsx'],capture_output=True,text=True).stdout
rem=[];add=[]
for l in d.splitlines():
    if l.startswith('---') or l.startswith('+++'): continue
    if l.startswith('-'): rem.append(l[1:])
    elif l.startswith('+'): add.append(l[1:])
def norm(s):
    s=re.sub(r"\s*\$\{[^}]*ds-v2[^}]*\}","",s)
    s=re.sub(r" ?\b(ds-v2-[a-z0-9-]+|ds-portale-v2-[a-z0-9-]+)\b","",s)
    s=s.replace(" ${STATO_V2[r.stato] ?? ''}","")
    return re.sub(r"\s+"," ",s).strip()
R=[norm(x) for x in rem]; A=[norm(x) for x in add]
extra=[a for a in A if a not in R]
miss=[r for r in R if r not in A]
print('righe tolte',len(rem),'aggiunte',len(add))
print('AGGIUNTE non spiegate da sole classi:'); [print('  +',x[:160]) for x in extra if x]
print('TOLTE non ritrovate:'); [print('  -',x[:160]) for x in miss if x]
