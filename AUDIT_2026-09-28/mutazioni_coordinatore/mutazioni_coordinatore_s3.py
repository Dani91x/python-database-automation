"""Mutazioni del COORDINATORE sul cantiere S3 (attribuzione UF2 nel banco,
falso CRITICAL, resto sotto 0,05).

Ogni mutazione rompe UN punto del codice corretto: i test devono diventare
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
BANCO = "Betfair/stream/backtest/uscite_manuali.py"
SCALPER = "Betfair/stream/scalper/scalper_bot.py"
TEST = ["Betfair/stream/tests", "Betfair/stream/tennis_scalper/tests", "-k",
        "cantiere_s3 or banco or uscite or cantiere_u or cantiere_s_scalper"]

MUT: List[Tuple[str, str, bytes, bytes]] = [
    ("U1 la finestra non si chiude alla firma successiva", BANCO,
     b"        scelti = [o for o in ordini if str(getattr(o, \"id\", \"\")) in pend[\"congelati\"]\n                  and (fino is None or str(getattr(o, \"id\", \"\")) in fino)]",
     b"        scelti = [o for o in ordini if str(getattr(o, \"id\", \"\")) in pend[\"congelati\"]]"),
    ("U2 uscita superata giudicata su abbinato e residuo", BANCO,
     b"            if pend.get(\"superata_da\"):",
     b"            if False:"),
    ("U3 la firma di un'altra selezione chiude la finestra", BANCO,
     b"                    and str(prec.get(\"selection_id\")) == str(proposta.get(\"selection_id\"))):",
     b"                    and True):"),
    ("U4 la firma di un altro mercato chiude la finestra", BANCO,
     b"                    and str(prec.get(\"market_id\")) == str(proposta.get(\"market_id\"))",
     b"                    and True"),
    ("U5 il rimpiazzo di un'uscita precedente contato nella nuova", BANCO,
     b"                and not self._rimpiazzo_di_prima(o, pend[\"ids_prima\"])}",
     b"                and True}"),
    ("U6 uscita superata: passa qualunque importo", BANCO,
     b"                                (_f(getattr(getattr(o, \"order_type\", None), \"size\", 0.0))\n                                 or 0.0)",
     b"                                (pend[\"size\"] / max(1, len([x for x in uscita if not e_parcheggio(x)])))"),
    ("C1 scalper: CRITICAL anche durante la pausa fra due sequenze", SCALPER,
     b"                  and self._chiusura_bloccata(net_win, net_lose, best_back, best_lay)):",
     b"                  and True):"),
    ("C2 scalper: resto sotto 0,05 aspetta il tetto per sempre", SCALPER,
     b"        if self.exact_exits and not self.dry_run and size >= 0.05 and \\",
     b"        if self.exact_exits and not self.dry_run and \\"),
    ("C3 scalper: CRITICAL mai con prezzi assenti", SCALPER,
     b"        if base is None:\n            return True\n        g = compute_green(net_win, net_lose, get_nearest_price(base))\n        if g is None:\n            return True",
     b"        if base is None:\n            return False\n        g = compute_green(net_win, net_lose, get_nearest_price(base))\n        if g is None:\n            return True"),
]


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def suite() -> Tuple[bool, str]:
    r = subprocess.run([PY, "-m", "pytest", *TEST, "-q", "-p", "no:cacheprovider", "-x"],
                       capture_output=True, text=True, timeout=900)
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
            print("%-62s ANCORA NON UNICA (%d)" % (nome, n), flush=True)
            vive += 1
            continue
        try:
            p.write_bytes(orig.replace(a, d))
            verde, coda = suite()
        finally:
            p.write_bytes(orig)
        assert md5(p.read_bytes()) == md5(orig)
        errore = "error" in coda and "failed" not in coda
        print("%-62s %s  %s" % (nome, "SOPRAVVISSUTA" if verde else
                                ("ERRORE DI RACCOLTA" if errore else "rossa"), coda), flush=True)
        vive += 1 if (verde or errore) else 0
    print("mutazioni sopravvissute o non valide: %d su %d" % (vive, len(MUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
