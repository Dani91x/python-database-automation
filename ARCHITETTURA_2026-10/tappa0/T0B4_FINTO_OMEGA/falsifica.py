"""Falsificazione del finto DbMemoriaOmega.aggregates* (T0B punto 4).

Ogni mutazione si applica al file vero, si lancia il test nuovo, si contano i
rossi, si ripristina e si verifica lo sha256 del file.
"""
import hashlib
import os
import re
import subprocess
import sys

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
FILE = RADICE + "/Betfair/omega/tools/replay_registrazioni.py"
TEST = "Betfair/omega/test_omega_finto_aggregati_modalita_2026_10_09.py"

MUTAZIONI = [
    ("M1 il finto accetta mode ma lo ignora (somma paper e live)",
     '        if m in ("paper", "live"):\n            righe = E.righe_della_modalita(righe, m)\n',
     '        if False:\n            righe = E.righe_della_modalita(righe, m)\n'),
    ("M2 firma di prima: aggregates_coppia senza mode",
     "    def aggregates_coppia(self, day_start: Any = None,\n                          mode: Optional[str] = None) -> Any:",
     "    def aggregates_coppia(self, day_start: Any = None, **_k: Any) -> Any:\n        mode = None"),
    ("M3 modalita' non normalizzata (niente strip/lower)",
     '        m = str(mode or "").strip().lower()\n        if m in ("paper", "live"):',
     '        m = str(mode or "")\n        if m in ("paper", "live"):'),
    ("M4 filtro ingenuo per colonna mode (chiusure e righe senza mode perse)",
     "            righe = E.righe_della_modalita(righe, m)\n",
     '            righe = [r for r in righe if r.get("mode") == m]\n'),
    ("M5 modalita' sconosciuta filtra tutto invece di tornare tutte",
     '        m = str(mode or "").strip().lower()\n        if m in ("paper", "live"):',
     '        m = str(mode or "").strip().lower()\n        if m:'),
    ("M6 aggregates torna i numeri del bot invece dei totali di pagina",
     "        return self.aggregates_coppia(day_start, mode=mode)[0]",
     "        return self.aggregates_coppia(day_start, mode=mode)[1]"),
    ("M7 default della firma diverso dal vero (mode='paper')",
     "    def aggregates(self, day_start: Any = None,\n                   mode: Optional[str] = None) -> Dict[str, Any]:",
     "    def aggregates(self, day_start: Any = None,\n                   mode: Optional[str] = \"paper\") -> Dict[str, Any]:"),
    ("M8 aggregates non passa mode alla coppia",
     "        return self.aggregates_coppia(day_start, mode=mode)[0]",
     "        return self.aggregates_coppia(day_start)[0]"),
]


def sha(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    originale = open(FILE, encoding="utf-8").read()
    sha0 = sha(FILE)
    print("sha256 originale", sha0)
    tutto_ok = True
    for nome, vecchio, nuovo in MUTAZIONI:
        assert originale.count(vecchio) == 1, nome
        open(FILE, "w", encoding="utf-8").write(originale.replace(vecchio, nuovo))
        try:
            r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q",
                                "-p", "no:cacheprovider"], cwd=RADICE,
                               capture_output=True, text=True, timeout=600)
            coda = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:]
            m = re.search(r"(\d+) failed", coda)
            rossi = int(m.group(1)) if m else 0
        finally:
            open(FILE, "w", encoding="utf-8").write(originale)
        ripristino = sha(FILE) == sha0
        tutto_ok &= rossi > 0 and ripristino
        print(f"{nome}: rossi={rossi} | {coda} | ripristino sha ok={ripristino}")
    print("sha256 dopo il ripristino", sha(FILE))
    print("ESITO:", "tutte le mutazioni ROSSE, file ripristinato" if tutto_ok else "ATTENZIONE")
    return 0 if tutto_ok else 1


if __name__ == "__main__":
    sys.exit(main())
