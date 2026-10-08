import re,sys,collections
D='.'
f={k:open(n,encoding='utf-8').read() for k,n in [('04','04_ARCHITETTURA_OBIETTIVO.md'),('05','05_PIANO_DI_MIGRAZIONE.md'),('06','06_RIEPILOGO_PER_L_UTENTE.md'),('08','08_REVISIONE_CRITICA.md')]}
t05=f['05']
i8=t05.index('## 8. DECISIONI'); i9=t05.index('## 9. Cosa ho verificato')
sec8=t05[i8:i9]
defs=re.findall(r'^\s*(?:[-*|]\s*)?\**\s*(?:\|\s*)?\**(U-\d+)\**',sec8,re.M)
ids8=re.findall(r'\bU-(\d+)',sec8)
print('def righe inizianti con U-:',len(defs),'dup:',[k for k,v in collections.Counter(defs).items() if v>1])
allu=set(int(x) for x in ids8)
print('U distinti in 05 sez8:',len(allu),'min',min(allu),'max',max(allu),'mancanti',[i for i in range(1,max(allu)+1) if i not in allu])
for k in ('04','06','08','05'):
    s=set(int(x) for x in re.findall(r'\bU-(\d+)',f[k]))
    print(k,'U citati',len(s),'non in 05 sez8:',sorted(s-allu),'max',max(s) if s else None)
# tappe
t2=set(re.findall(r'^### (T\d+[A-Z]?)\b',t05,re.M))
print('tappe titoli:',sorted(t2,key=lambda x:(int(re.sub(r'\D','',x)),x)))
for k in f:
    s=set(re.findall(r'\bT(\d+)([A-Z]?)\b',f[k]))
    bad=sorted(set('T'+a+b for a,b in s if 'T'+a+b not in t2 and 'T'+a not in t2))
    print(k,'Tnn non esistenti:',bad)
