"""Spezza un referto di certifica nelle sezioni degli scenari (dalla riga di
esito alla riga `tempo:`) e confronta ciascuna con il referto dello scenario
girato DA SOLO in un processo nuovo. Uso: sezioni.py referto_tutti dir_solo"""
import sys, re, os
LOG = re.compile(r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL):[\w.]+:")
def sezioni(testo, solo=False):
    out, cur, nome = {}, None, None
    for r in testo.splitlines():
        if LOG.match(r): continue
        m = re.match(r"^(OK|KO|\?\?|--|!!|XX)?\s*(\d+)(?: \[([^\]]+)\])?\s+tick=", r)
        if m:
            nome = m.group(3) or "_solo"; cur = out.setdefault(nome, [])
            r = re.sub(r"^(\S+\s+\d+)(?: \[[^\]]+\])?", r"\1", r)
        if cur is not None:
            if r.lstrip().startswith("tempo:"): cur = None; continue
            cur.append(r)
    return out
tutti = sezioni(open(sys.argv[1]).read())
ko = 0
for sc, righe in tutti.items():
    p = os.path.join(sys.argv[2], sc + ".txt")
    solo = sezioni(open(p).read()).get("_solo")
    stato = "IDENTICO" if solo == righe else "DIVERSO"
    if solo != righe: ko += 1
    print(f"{stato:9} {sc} ({len(righe)} righe)")
print("scenari diversi:", ko, "su", len(tutti))
