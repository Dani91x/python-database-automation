"""Verifica del COORDINATORE sulle schede degli schemi (regole di chiarezza).

Per ogni capitolo consegnato controlla:
- che esistano specifica, schema HTML e schede;
- che ci sia una scheda per ogni riquadro dello schema;
- che ogni scheda abbia le sette voci del formato fisso;
- che fuori da «Per il tecnico» non compaiano gergo informatico ne' nomi del codice.
Sola lettura.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List

R = Path(r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\SCHEMI_BOT")
VOCI = ["Cosa fa", "Quando", "Numeri", "Esempio", "Cosa vedi", "Se qualcosa va storto", "Per il tecnico"]
GERGO = ["funzione", "flag", "thread", "callback", "cache", "polling", "payload", "retry",
         "dizionario", "timeout", "buffer", "stringa", "booleano", "parsing", "endpoint"]


def riquadri(spec: Path) -> List[str]:
    d = json.loads(spec.read_text(encoding="utf-8"))
    for chiave in ("nodes", "states", "participants", "components"):
        if chiave in d:
            return [str(n.get("label", n.get("id"))) for n in d[chiave]]
    return []


def schede(testo: str) -> Dict[str, str]:
    """Titolo -> corpo delle sezioni di terzo livello (o secondo se mancano)."""
    pezzi = re.split(r"^#{2,3}\s+(.+)$", testo, flags=re.M)
    out: Dict[str, str] = {}
    for i in range(1, len(pezzi) - 1, 2):
        out[pezzi[i].strip()] = pezzi[i + 1]
    return out


def senza_tecnico(corpo: str) -> str:
    """Il testo che legge l'utente: tolta la voce «Per il tecnico» fino alla voce dopo."""
    return re.split(r"\*\*Per il tecnico", corpo, maxsplit=1)[0]


def main() -> int:
    bot = sys.argv[1] if len(sys.argv) > 1 else "mike"
    cart = R / bot / "schemi"
    capitoli = sorted({p.name.split(".")[0] for p in cart.glob("[0-9]*") if "visual-check" not in p.name})
    totale = 0
    for cap in capitoli:
        spec = [p for p in cart.glob(cap + ".*.json") if "visual-check" not in p.name]
        html = cart / (cap + ".html")
        md = cart / (cap + ".schede.md")
        stato = "spec=%s html=%s schede=%s" % ("si" if spec else "NO", "si" if html.exists() else "NO",
                                               "si" if md.exists() else "NO")
        print("== %s  %s" % (cap, stato))
        if not md.exists():
            continue
        testo = md.read_text(encoding="utf-8", errors="ignore")
        sk = schede(testo)
        rq = riquadri(spec[0]) if spec else []
        di_riquadro = {t: c for t, c in sk.items() if sum(1 for v in VOCI if v.lower() in c.lower()) >= 4}
        print("   riquadri nello schema: %d | schede col formato: %d | righe: %d"
              % (len(rq), len(di_riquadro), testo.count("\n")))
        if rq and len(di_riquadro) < len(rq):
            print("   !! MENO SCHEDE CHE RIQUADRI")
            totale += 1
        for t, c in di_riquadro.items():
            mancano = [v for v in VOCI if v.lower() not in c.lower()]
            if mancano:
                print("   !! scheda «%s»: mancano le voci %s" % (t[:50], mancano))
                totale += 1
            visibile = senza_tecnico(c)
            if not re.search(r"\d", re.split(r"\*\*Esempio", c, maxsplit=1)[-1][:600]):
                print("   !! scheda «%s»: esempio senza cifre" % t[:50])
                totale += 1
            g = sorted({w for w in GERGO if re.search(r"(?<![a-z])%s(?![a-z])" % w, visibile, re.I)})
            nomi = sorted(set(re.findall(r"`([A-Za-z_][A-Za-z0-9_\.]*_[A-Za-z0-9_\.]+)`", visibile)))
            if g:
                print("   ! scheda «%s»: gergo %s" % (t[:50], g))
                totale += 1
            if nomi:
                print("   ! scheda «%s»: nomi del codice nel testo %s" % (t[:50], nomi[:6]))
                totale += 1
        for sez in ("Frecce", "Punti da decidere"):
            if sez.lower() not in testo.lower():
                print("   !! sezione mancante: %s" % sez)
                totale += 1
    print("TOTALE rilievi: %d" % totale)
    return 0


if __name__ == "__main__":
    sys.exit(main())
