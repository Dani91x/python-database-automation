# Confronto scenario per scenario fra referto di riferimento e referto nuovo.
import re, sys, difflib, collections
ESITO = re.compile(r"^(OK|KO|NE)\s+\d+ \[([^\]]+)\]")
LOG = re.compile(r"^[A-Z]+:[\w.]+:")
ESCLUDI = ("tempo:", "TEMPO TOTALE", "LENTO", "worker:", "MEMORIA:", "comando:")
def blocchi(path):
    b = collections.OrderedDict(); cur = "_intestazione"; b[cur] = []
    for r in open(path, encoding="utf-8", errors="replace"):
        r = r.rstrip("\n")
        m = ESITO.match(r)
        if m:
            cur = m.group(2); b[cur] = []
        s = r.strip()
        if not s or LOG.match(s) or any(s.startswith(e) or e in s[:20] for e in ESCLUDI):
            continue
        if cur == "_intestazione":
            # impronta del codice e percorso delle registrazioni
            r = re.sub(r"codice bot \w+ \(\d+ file\)", "codice bot <impronta>", r)
            r = re.sub(r"registrazioni: (\d+) in \S+", r"registrazioni: \1 in <percorso>", r)
            if re.match(r"^(OK|KO|NE)\s", r) is None and r.startswith("worker"):
                continue
        b[cur].append(r)
    return b
def attesa(r):
    return "save_event_model" in r or "metodi di database chiamati dal servizio e ASSENTI dal banco" in r or ("NON ESERCITABILE" in r and "get_event" in r)
ref, new = blocchi(sys.argv[1]), blocchi(sys.argv[2])
esiti_ref = {k: v[0] for k, v in ref.items() if v and ESITO.match(v[0])}
esiti_new = {k: v[0] for k, v in new.items() if v and ESITO.match(v[0])}
print("scenari rif=%d nuovo=%d" % (len(esiti_ref), len(esiti_new)))
n_att = 0; non_att = []
for k in list(ref) + [k for k in new if k not in ref]:
    a, b = ref.get(k), new.get(k)
    if a is None or b is None:
        non_att.append((k, ["scenario presente solo in " + ("nuovo" if a is None else "riferimento")])); continue
    righe = []
    for op in difflib.unified_diff(a, b, lineterm="", n=0):
        if op.startswith(("---", "+++", "@@")): continue
        if attesa(op[1:]): n_att += 1
        else: righe.append(("PRIMA: " if op[0] == "-" else "DOPO:  ") + op[1:])
    if righe: non_att.append((k, righe))
for k, e in esiti_new.items():
    print(e)
print("ESITI IDENTICI:", esiti_ref == esiti_new)
print("righe differenti ATTESE (save_event_model / get_event):", n_att)
print("blocchi con differenze NON ATTESE:", len(non_att))
for k, rr in non_att:
    print("== [%s]" % k)
    for r in rr: print("   " + r)
