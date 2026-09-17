# -*- coding: utf-8 -*-
"""FALSIFICAZIONE COL METODO DELL'MD5 (usa-e-getta, 17/09).

Per ogni difetto: si rompe UN frammento nel codice VERO, si fa girare il banco
sulla sintetica (scenario `v4`, dove V3 apre davvero due gambe), si guarda quale
controllo diventa rosso, si RIPRISTINA e si verifica l'md5.

Non tocca nessuna registrazione e non scrive niente nel repo oltre al file che
sta rompendo (e che rimette identico).
"""
from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys

RADICE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
PY = sys.executable
DATA = os.environ.get(
    "LIVE_STREAM_DATA_DIR",
    r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\_live_raw")

SERVIZIO = "Betfair/omega/omega_service.py"
MOTORE = "Betfair/omega/omega_v3.py"

# (nome, file, frammento_vero, frammento_rotto, controlli attesi rossi)
PROVE = [
    ("A9 — stake 1,10 invece di 1,00", SERVIZIO,
     '        size = round(float(v3["stake"]), 2)\n',
     '        size = round(float(v3["stake"]) + 0.10, 2)\n',
     ("A9",)),
    # il margine DICHIARATO non e' quello applicato: `k_usato` decuplicato fa
    # sfondare la disuguaglianza `P_nostra * k <= p_implicita`
    ("A10 — il k dichiarato non e' quello applicato", MOTORE,
     "            p_implicita=float(p_imp), k_usato=k, margine=float(margine),\n",
     "            p_implicita=float(p_imp), k_usato=k * 10.0, margine=float(margine),\n",
     ("A10",)),
    # il filtro della DISTANZA spento: il motore puo' bancare il punteggio
    # corrente o una cella a un gol (il difetto del v1, -93,87 EUR il 09/09)
    ("A11 — distanza minima dal punteggio ignorata", MOTORE,
     "            if (sc[0] - sh) + (sc[1] - sa) < int(distanza_minima_gol):\n",
     "            if (sc[0] - sh) + (sc[1] - sa) < 0:\n",
     ("A11",)),
    # il PAVIMENTO di fascia spento: si bancano celle sotto l'1 %
    ("A11 — pavimento `v3_p_min_pct` ignorato", MOTORE,
     "        if p_nostra < float(p_min):\n",
     "        if False and p_nostra < float(p_min):\n",
     ("A11",)),
    # il TETTO DI GAMBA spento in tutti e due i posti (motore + difesa del
    # servizio): una gamba oltre 95 EUR di liability arriva all'ordine
    ("C5 — tetto di gamba ignorato", MOTORE,
     "        if cap_liability_gamba and cap_liability_gamba > 0:\n",
     "        if False and cap_liability_gamba > 0:\n",
     ("C5",)),
    ("K1 — conferma col prezzo CHIESTO invece dell'ABBINATO", SERVIZIO,
     "        final_price = float(res.avg_price_matched or price)\n",
     "        final_price = float(price)\n",
     ("K1",)),
]

# scenario del banco per ogni prova: alcune hanno un caso solo dove il libro lo
# offre (il tetto di gamba morde solo su una quota alta, e il prezzo migliore
# del chiesto capita solo nella deriva del '3 - 3' dopo il 56' — cioe' nello
# scenario legacy, che li' apre)
SCENARIO = {
    "C5 — tetto di gamba ignorato": "v3",
    "K1 — conferma col prezzo CHIESTO invece dell'ABBINATO": "v3",
}

# il tetto di gamba ha anche una DIFESA nel servizio: per far arrivare l'ordine
# oltre il tetto vanno rotti tutti e due i frammenti (la difesa da sola non
# basterebbe a dimostrare niente).
DIFESA_C5 = (
    SERVIZIO,
    "        if cap_gamba > 0 and E.liability_from_lay(size, sel.price) > cap_gamba + 0.011:\n",
    "        if False and cap_gamba > 0:\n")


def md5(percorso: str) -> str:
    with open(os.path.join(RADICE, percorso), "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def scrivi(percorso: str, vecchio: str, nuovo: str) -> None:
    """Sostituisce UN frammento senza toccare nient'altro — nemmeno i fine
    riga: si legge e si scrive in BINARIO, se no la traduzione CRLF/LF
    cambierebbe l'md5 di un file il cui contenuto e' identico, e la prova del
    ripristino non proverebbe piu' niente."""
    p = os.path.join(RADICE, percorso)
    with open(p, "rb") as fh:
        b = fh.read()
    for fine in (b"\r\n", b"\n"):
        v = vecchio.replace("\n", fine.decode()).encode("utf-8")
        n = nuovo.replace("\n", fine.decode()).encode("utf-8")
        if v in b:
            with open(p, "wb") as fh:
                fh.write(b.replace(v, n, 1))
            return
    raise AssertionError(f"frammento non trovato in {percorso}: {vecchio!r}")


def banco(scenario: str = "v4") -> str:
    env = dict(os.environ, LIVE_STREAM_DATA_DIR=DATA, PYTHONIOENCODING="utf-8")
    out = subprocess.run(
        [PY, "-m", "Betfair.stream.backtest.certifica", "omega",
         "_synth_omega_prezzo_migliore", "--scenari", scenario, "--worker", "1"],
        cwd=RADICE, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace")
    return (out.stdout or "") + (out.stderr or "")


def main() -> int:
    prima = {SERVIZIO: md5(SERVIZIO), MOTORE: md5(MOTORE)}
    print("md5 PRIMA:", prima)
    testo = banco()
    print("SANO:", [r for r in testo.splitlines() if r.startswith(("OK ", "KO ", "ESITO", "       "))][:4])
    for nome, percorso, vero, rotto, attesi in PROVE:
        scrivi(percorso, vero, rotto)
        doppio = nome.startswith("C5")
        if doppio:
            scrivi(*DIFESA_C5)
        testo = banco(SCENARIO.get(nome, "v4"))
        righe = [r.strip() for r in testo.splitlines()
                 if r.startswith("      ") and " x" in r and ":" in r
                 and r.strip()[:1].isupper()]
        esito = [r for r in testo.splitlines() if r.startswith("ESITO") or "violazioni totali" in r]
        print("\n=== " + nome)
        print("   accuse:", righe[:6] or "NESSUNA")
        print("   esito :", esito)
        print("   attesi:", attesi)
        # RIPRISTINO
        scrivi(percorso, rotto, vero)
        if doppio:
            scrivi(DIFESA_C5[0], DIFESA_C5[2], DIFESA_C5[1])
        dopo = md5(percorso)
        print("   md5 ripristinato:", dopo == prima[percorso], dopo)
        assert dopo == prima[percorso], "RIPRISTINO FALLITO"
    print("\nmd5 DOPO:", {k: md5(k) for k in prima})
    assert all(md5(k) == v for k, v in prima.items())
    return 0


if __name__ == "__main__":
    sys.exit(main())
