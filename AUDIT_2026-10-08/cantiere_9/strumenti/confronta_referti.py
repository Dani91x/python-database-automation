"""Confronto PRIMA/DOPO di due referti di `certifica`, esclusi tempi, hash, percorsi
e identificativi di processo. Uso:
  python3 confronta_referti.py <prima.txt> <dopo.txt> [scenario,scenario...]
Con l'elenco degli scenari si confrontano SOLO i blocchi di quegli scenari (il DOPO
ha in piu' gli scenari nuovi del cantiere 9)."""
import difflib
import re
import sys

ESCLUSE = ("tempo:", "TEMPO TOTALE", "LENTO", "codice bot", "comando:", "BOT: ",
           "real\t", "user\t", "sys\t", "SCENARI:")


def _norm(r: str) -> str:
    r = re.sub(r"\d{12,}", "<ID>", r)
    r = re.sub(r"/[^ ]*_live_raw", "<RAW>", r)
    return r


def blocchi(righe, scelti):
    """Le righe dei blocchi degli scenari scelti (dalla riga OK/KO/NE alla prossima)."""
    out, dentro = [], False
    for r in righe:
        m = re.match(r"^(OK|KO|NE)\s+\d+ \[([^\]]+)\]", r)
        if m:
            dentro = (scelti is None) or (m.group(2) in scelti)
        elif r.startswith(("ESITO", "COPERTURA", "?? MAI", "TEMPO")):
            dentro = False
        if dentro:
            out.append(r)
    return out


def leggi(p, scelti):
    righe = [l.rstrip("\n") for l in open(p, encoding="utf-8")]
    righe = [_norm(l) for l in righe if not any(e in l for e in ESCLUSE)]
    return blocchi(righe, scelti) if scelti is not None else righe


scelti = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None
a, b = leggi(sys.argv[1], scelti), leggi(sys.argv[2], scelti)
d = list(difflib.unified_diff(a, b, "PRIMA", "DOPO", n=0, lineterm=""))
print("\n".join(d) if d else "IDENTICI (esclusi tempi, hash, percorsi, id di processo)")
