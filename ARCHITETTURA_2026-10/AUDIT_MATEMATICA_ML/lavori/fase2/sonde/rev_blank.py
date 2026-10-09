# Sonda di revisione (sola lettura): per le citazioni file:riga delle righe "[cert. fase 2]" di 00-06,
# segnala quelle che puntano a riga vuota o oltre la fine del file.
import re, sys, os, collections
R = sys.argv[1]
AU = R + "/ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML/"
files = [l.strip() for l in sys.stdin]
by = collections.defaultdict(list)
for f in files: by[os.path.basename(f)].append(f)
pat = re.compile(r"`?([A-Za-z0-9_\-/]+\.(?:py|ts|tsx|sql|yml|sh|md)):(\d+)(?:-(\d+))?")
seen = set(); out = []
for name in ["00_INVENTARIO_MATEMATICO.md","01_CATENA_POISSON.md","02_CATENA_ML.md","03_COMPONENTI_MATEMATICI.md","04_FLUSSO_FINO_AL_CONSUMATORE.md","05_ERRORI_DI_PROGETTAZIONE.md","06_PIANO_MIGLIORAMENTI.md","07_RIEPILOGO_PER_L_UTENTE.md","DECISIONI_PER_L_UTENTE.md"]:
    for i, line in enumerate(open(AU + name, encoding="utf-8", errors="replace"), 1):
        for m in pat.finditer(line):
            fn, a, b = m.group(1), int(m.group(2)), m.group(3)
            if fn == "CRONOSTORIA.md": continue
            c = by.get(os.path.basename(fn), [])
            c = [x for x in c if x.endswith(fn)]
            if len(c) != 1: continue
            key = (c[0], a)
            if key in seen: continue
            seen.add(key)
            try: L = open(R + "/" + c[0], encoding="utf-8", errors="replace").read().split("\n")
            except Exception: continue
            if a > len(L): out.append((name, i, c[0], a, "OLTRE FINE (len %d)" % len(L)))
            elif not L[a-1].strip(): out.append((name, i, c[0], a, "RIGA VUOTA"))
for o in out: print(*o)
print("citazioni uniche controllate:", len(seen), "anomale:", len(out))
