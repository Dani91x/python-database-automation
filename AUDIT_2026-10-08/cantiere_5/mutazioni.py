"""Falsificazione del cantiere 5: ogni mutazione si applica, si lanciano i test,
si contano i rossi, si ripristina e si verifica lo sha del file.

Uso (dalla radice del repo): python AUDIT_2026-10-08/cantiere_5/mutazioni.py .
"""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
CD = "Betfair/stream/tennis_scalper/condotta_ordini.py"
SC = "Betfair/stream/tennis_scalper/tennis_scalper_bot.py"
CB = "Betfair/stream/tennis_live/certificazione_bot.py"
TEST = ["Betfair/stream/tennis_live/tests/test_cantiere5_parcheggio_tennis_2026_10_08.py",
        "Betfair/stream/tennis_live/tests/test_scalper_tennis_cp4_parcheggio_2026_10_07.py"]

MUT = [
    ("M1 stato_parcheggio: quota = initial_place_price (condotta di prima, LAY 1,01 fissa)", CD,
     "    park = quota_parcheggio_lontano(lato, float(target))\n    if park is None:\n"
     "        return None\n    return SubminState(",
     "    from ..trading.submin import initial_place_price as _ipp\n    park = _ipp(lato)\n"
     "    if park is None:\n        return None\n    return SubminState("),
    ("M2 stato_parcheggio: importo del parcheggio 2,00 scritto a mano", CD,
     "placed_size=round(float(place_min_size(JURISDICTION_IT, lato)), 2),",
     "placed_size=2.0,"),
    ("M3 scalper flatten: soglia del parcheggio di nuovo 1,011", SC,
     "p <= QUOTA_PARCHEGGIO_LAY_ALTA + 0.001", "p <= 1.011"),
    ("M4 scalper _place_exact: ramo 'nessuna quota sicura' tolto", SC,
     "        if quota_parcheggio_lontano(side.lower(), rest) is None:\n",
     "        if False:\n"),
    ("M5 UsciteEsatte: ramo 'nessuna quota sicura' tolto", CD,
     "        if resto >= 0.01 and stato is None:\n", "        if False:\n"),
    ("M6 banco B11 spento (ritorna sempre None)", CB,
     "def _b11(oss: Osservazione) -> Optional[str]:\n    for r in oss.ordini:",
     "def _b11(oss: Osservazione) -> Optional[str]:\n    return None\n    for r in oss.ordini:"),
    ("M7 banco: riconoscimento del parcheggio LAY solo 1,01 (B8)", CB,
     '_QUOTA_PARCHEGGIO = {"BACK": (CD.QUOTA_PARCHEGGIO_BACK,), "LAY": CD.QUOTE_PARCHEGGIO_LAY}',
     '_QUOTA_PARCHEGGIO = {"BACK": (CD.QUOTA_PARCHEGGIO_BACK,), "LAY": (1.01,)}'),
    ("M8 banco parcheggio_di: resto del parcheggio vivo = size (non size - cancellato)", CB,
     "        residuo = round(size - ridotto, 2)", "        residuo = round(size, 2)"),
    ("M9 banco B11: tolleranza larga (accetta ogni quota vicina)", CB,
     "        if abs(float(pk.get(\"quota\") or 0.0) - float(attesa)) > 1e-9:",
     "        if abs(float(pk.get(\"quota\") or 0.0) - float(attesa)) > 0.05:"),
    ("M10 quote LAY del parcheggio: banda calcolata sul solo resto 0,99 (1,01)", CD,
     "    quote = {quota_parcheggio_lontano(\"lay\", c / 100.0) for c in range(da, a)}",
     "    quote = {quota_parcheggio_lontano(\"lay\", c / 100.0) for c in range(a - 1, a)}"),
]


def sha(p: str) -> str:
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def main() -> None:
    for nome, f, old, new in MUT:
        path = ROOT / f
        orig = path.read_text()
        h0 = sha(f)
        assert orig.count(old) == 1, (nome, orig.count(old))
        path.write_text(orig.replace(old, new))
        try:
            r = subprocess.run([sys.executable, "-m", "pytest", *TEST, "-q",
                                "-p", "no:cacheprovider"],
                               cwd=ROOT, capture_output=True, text=True)
            out = r.stdout.strip().splitlines()
            riass = out[-1] if out else r.stderr[-300:]
            rossi = [ln.split("::", 1)[1].split(" ")[0] for ln in out
                     if ln.startswith("FAILED")]
        finally:
            path.write_text(orig)
        h1 = sha(f)
        print("%s\n   esito: %s\n   rossi: %s\n   ripristino: sha %s %s" % (
            nome, riass, ", ".join(rossi[:12]) + (" ..." if len(rossi) > 12 else ""),
            h1[:16], "IDENTICO" if h1 == h0 else "DIVERSO!"))
        sys.stdout.flush()


if __name__ == "__main__":
    main()
