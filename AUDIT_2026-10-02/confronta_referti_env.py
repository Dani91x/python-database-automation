"""Confronta due referti del banco riga per riga, tolte le sole righe dei tempi
(PROCESSO_STANDARD_BOT par. 6.9) e i WARNING di log, e due file di tracce
(``--tracce``) tolto ``durata_s``. Uso:
python AUDIT_2026-10-02/confronta_referti_env.py A.txt B.txt [tracceA.json tracceB.json]
"""
import json
import re
import sys


def righe(p):
    out = []
    for r in open(p, encoding="utf-8", errors="replace").read().splitlines():
        if r.startswith(("WARNING", "INFO")) or "durata" in r or "DURATA" in r:
            continue
        r = re.sub(r"\s\d+\.\d s$", "", r)
        r = re.sub(r"costo del banco sul canale: [0-9.]+ s",
                   "costo del banco sul canale: <tempo> s", r)
        if r.startswith("ambiente del banco"):
            continue   # la riga nuova di testa: confrontata a parte
        out.append(r)
    return out


def tracce(p):
    d = json.load(open(p, encoding="utf-8"))
    for tr in ("coda", "canale"):
        if isinstance(d.get(tr), dict):
            d[tr].pop("durata_s", None)
            d[tr].pop("costo_banco_s", None)
    if isinstance(d.get("parita"), dict):
        d["parita"].pop("durata_s", None)
    return _senza_tempi(d)


def _senza_tempi(x):
    """Toglie ricorsivamente le sole chiavi di TEMPO di macchina (durata, costo
    del banco): i tempi di MERCATO (``t_mercato``, ``scarto_tempi_s``) restano."""
    if isinstance(x, dict):
        return {k: _senza_tempi(v) for k, v in x.items()
                if k not in ("durata_s", "costo_banco_s")}
    if isinstance(x, list):
        return [_senza_tempi(v) for v in x]
    return x


a, b = righe(sys.argv[1]), righe(sys.argv[2])
diverse = [(i, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]
print("righe confrontate: %d / %d | diverse: %d" % (len(a), len(b), len(diverse)))
for i, x, y in diverse[:20]:
    print("  #%d\n   A: %s\n   B: %s" % (i, x, y))
print("REFERTI:", "IDENTICI" if (len(a) == len(b) and not diverse) else "DIVERSI")
if len(sys.argv) > 4:
    ta, tb = tracce(sys.argv[3]), tracce(sys.argv[4])
    print("TRACCE (tolte le durate):", "IDENTICHE" if ta == tb else "DIVERSE")
    if ta != tb:
        for k in ta:
            if ta.get(k) != tb.get(k):
                print("  chiave diversa:", k, str(ta.get(k))[:300], "|", str(tb.get(k))[:300])
