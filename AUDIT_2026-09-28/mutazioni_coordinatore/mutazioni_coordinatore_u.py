"""Mutazioni del COORDINATORE sul cantiere U (proposte a 0,00 dei bot tennis).

Ogni mutazione rompe UNA riga del codice corretto: i test devono diventare
rossi. Il file si ripristina dalla copia in memoria e si controlla l'hash.
Si lancia dalla radice del worktree di verifica.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

PY = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.venv\Scripts\python.exe"
D = "Betfair/stream/tennis_scalper/"
TEST = [D + "tests", "Betfair/stream/tests/test_banco_uscite_manuali_n3_2026_09_28.py",
        "Betfair/stream/tests/test_banco_uscite_dichiarate_n3_2026_09_28.py"]

MUT: List[Tuple[str, str, bytes, bytes]] = [
    ("M1 soglia del centesimo tolta", D + "tennis_scalper_bot.py",
     b"    if importo < 0.01:", b"    if importo < 0.0:"),
    ("M2 pro: residuo di nuovo scambiato per posizione", D + "tennis_pro_bot.py",
     b'        if (b + l) <= _EPS or self._niente_da_chiudere(b, ba, l, la, d, trade["side"]):',
     b"        if (b + l) <= _EPS:"),
    ("M3 pro: proposta con importo della chiusura TOTALE", D + "tennis_pro_bot.py",
     b"        g = green_piazzabile(nw, nl, prezzo, frazione)",
     b"        g = green_piazzabile(nw, nl, prezzo, 1.0)"),
    ("M4 pro: l'ordine manda un importo diverso dalla proposta", D + "tennis_pro_bot.py",
     b"        o = self._place(market, sel, gp[0], get_nearest_price(price), gp[1],",
     b"        o = self._place(market, sel, gp[0], get_nearest_price(price), gp[1] + 0.01,"),
    ("M5 pro: proposta a zero rinasce (nessun rifiuto)", D + "tennis_pro_bot.py",
     b"        if g is None:\n            return False\n        proposta = proposta_di(",
     b"        if g is None:\n            g = (lato, 0.0, 0.0)\n        proposta = proposta_di("),
    ("M6 swing: residuo di nuovo scambiato per posizione", D + "tennis_swing_bot.py",
     b"        if (b+l) <= _EPS or vuota:", b"        if (b+l) <= _EPS:"),
    ("M7 swing: proposta a zero rinasce", D + "tennis_swing_bot.py",
     b"        g = green_piazzabile(nw, nl, px)\n        if g is None:",
     b"        g = green_piazzabile(nw, nl, px) or (side, 0.0, 0.0)\n        if g is None:"),
    ("M8 flb: residuo di nuovo scambiato per posizione", D + "tennis_flb_bot.py",
     b"        if (b + l) <= _EPS or vuota:", b"        if (b + l) <= _EPS:"),
    ("M9 flb: cancel perso inventato dal residuo", D + "tennis_flb_bot.py",
     b"            if (b + l) > _EPS and not vuota:", b"            if (b + l) > _EPS:"),
    ("M10 flb: green a zero rinasce", D + "tennis_flb_bot.py",
     b"            vuole_green = g0 is not None and self.cancello_uscite.lascia_uscire(",
     b"            g0 = g0 or ('BACK', 0.0, 0.0)\n            vuole_green = self.cancello_uscite.lascia_uscire("),
    ("M11 banco UM2: lo zero torna un numero presente", "Betfair/stream/backtest/uscite_manuali.py",
     b"            if float(size) <= 0.0:", b"            if float(size) < 0.0:"),
    ("M12 pro: prezzo di uscita del lato sbagliato", D + "tennis_pro_bot.py",
     b'        px = d.get("bl") if lato_trade == "BACK" else d.get("bb")',
     b'        px = d.get("bb") if lato_trade == "BACK" else d.get("bl")'),
]


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def suite() -> Tuple[bool, str]:
    r = subprocess.run([PY, "-m", "pytest", *TEST, "-q", "-p", "no:cacheprovider", "-x"],
                       capture_output=True, text=True, timeout=600)
    coda = [x for x in (r.stdout or "").splitlines() if x.strip()][-1:]
    return r.returncode == 0, (coda[0] if coda else "?")


def main() -> int:
    ok, coda = suite()
    print("BASE (senza mutazioni): %s  %s" % ("VERDE" if ok else "ROSSA", coda), flush=True)
    if not ok:
        return 2
    vive = 0
    for nome, percorso, prima, dopo in MUT:
        p = Path(percorso)
        orig = p.read_bytes()
        crlf = b"\r\n" in orig
        a = prima.replace(b"\n", b"\r\n") if crlf else prima
        d = dopo.replace(b"\n", b"\r\n") if crlf else dopo
        n = orig.count(a)
        if n != 1:
            print("%-58s ANCORA NON UNICA (%d)" % (nome, n), flush=True)
            vive += 1
            continue
        try:
            p.write_bytes(orig.replace(a, d))
            verde, coda = suite()
        finally:
            p.write_bytes(orig)
        assert md5(p.read_bytes()) == md5(orig)
        print("%-58s %s  %s" % (nome, "SOPRAVVISSUTA" if verde else "rossa", coda), flush=True)
        vive += 1 if verde else 0
    print("mutazioni sopravvissute o non applicate: %d su %d" % (vive, len(MUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
