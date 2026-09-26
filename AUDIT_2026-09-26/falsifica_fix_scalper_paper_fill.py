"""Falsificazione dei test del cantiere FIX_SCALPER_E_PAPER_FILL (26/09).

Per ogni mutazione: copia i byte del file, rimette il bug, lancia pytest sul
test nuovo (deve fallire), ripristina i byte e verifica l'uguaglianza. Il
ripristino e' in ``finally``: nessuna mutazione resta nel codice.
"""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
os.chdir(RADICE)
ENV = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x",
           SUPABASE_KEY="x")
T_SCALPER = "Betfair/stream/tests/test_scalper_freno_origine_2026_09_26.py"
T_MIKE = "Betfair/mike/tests/test_mike_paper_fill_al_best_2026_09_26.py"
T_SAFE = "Betfair/safe_strategy/tests/test_paper_fill_al_best_2026_09_26.py"
SVC = "Betfair/stream/scalper/scalper_service.py"
AM = "Betfair/stream/scalper/auto_mode.py"
SS = "Betfair/stream/scalper/scalper_session.py"
MIKE = "Betfair/mike/service.py"
EXE = "Betfair/safe_strategy/execution.py"

MUTAZIONI = [
    ("M1 arma a freno tirato", SVC,
     "    if not freno and not bloccato and not conflitto",
     "    if not bloccato and not conflitto", T_SCALPER),
    ("M2 giro_auto senza freno nel supervisore", SVC,
     "giro_auto(db, stato_auto, righe_attive, time.time(), freno=freno)",
     "giro_auto(db, stato_auto, righe_attive, time.time())", T_SCALPER),
    ("M3 motivo_blocco non conosce il freno", AM,
     "    if freno:\n        return motivo_freno_testo(freno)\n", "", T_SCALPER),
    ("M4 fermata dal freno = chiusa a mano", AM,
     "    if (st == \"stopped\" and fermata_dal_freno(riga)",
     "    if (st == \"stopped\" and False", T_SCALPER),
    ("M5 follow senza origine", SVC,
     "            \"origine\": \"auto\",\n        }", "        }", T_SCALPER),
    ("M6 select senza marcatore", SVC,
     "\"event_id,status,requested_at,dry_run,origine,\"\n"
     "                             \"fermata_dal_freno:stats->fermata_dal_freno\"",
     "\"event_id,status,requested_at,dry_run,origine\"", T_SCALPER),
    ("M7 error finale senza non flat", SS,
     "[non_flat_30s] if non_flat_30s else []", "[]", T_SCALPER),
    ("M8 stats finali senza posizione_non_flat", SS,
     "        out[\"posizione_non_flat\"] = non_flat_30s\n", "        pass\n", T_SCALPER),
    ("M9 micro-residuo non dichiarato (soglia)", SS,
     "    elif res <= SOGLIA_NON_FLAT + 1e-9:", "    elif res < 0:", T_SCALPER),
    ("M10 rilascio del freno aspetta 15 s", SVC,
     "forza or freno_cambiato or", "forza or", T_SCALPER),
    ("M11 sessione non avviata senza marcatore", SS,
     "                   stats={CHIAVE_FERMATA_FRENO: motivo})",
     "                   )", T_SCALPER),
    ("M12 Mike paper senza livello (bug R7)", MIKE,
     "ladder=ladder_paper, client_ref", "ladder=(), client_ref", T_MIKE),
    ("M13 Mike ladder anche in live", MIKE,
     "if mode == \"paper\" and avail_price is not None and avail_size",
     "if avail_price is not None and avail_size", T_MIKE),
    ("M14 execution ignora la ladder in paper", EXE,
     "fill = E.paper_fill(size, best_price=price, lay_ladder=_ladder_tuple(ladder),",
     "fill = E.paper_fill(size, best_price=price, lay_ladder=(),", T_SAFE),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    esiti = []
    scelte = sys.argv[1:]
    for nome, file, vecchio, nuovo, test in MUTAZIONI:
        if scelte and nome.split()[0] not in scelte:
            continue
        p = RADICE / file
        originale = p.read_bytes()
        testo = originale.decode("utf-8")
        if "\r\n" in testo:     # file CRLF: le mutazioni su piu' righe vanno in CRLF
            vecchio = vecchio.replace("\n", "\r\n")
            nuovo = nuovo.replace("\n", "\r\n")
        n = testo.count(vecchio)
        if n != 1:
            esiti.append((nome, "MUTAZIONE NON APPLICABILE (%d occorrenze)" % n))
            continue
        try:
            p.write_bytes(testo.replace(vecchio, nuovo).encode("utf-8"))
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p",
                                "no:cacheprovider", test], env=ENV, capture_output=True,
                               text=True)
            ultima = [l for l in r.stdout.strip().splitlines() if l.strip()][-1:]
            esiti.append((nome, ("ROSSO (ok)" if r.returncode != 0 else "VERDE (!!)")
                          + " | " + (ultima[0] if ultima else "")))
        finally:
            p.write_bytes(originale)
            assert sha(p.read_bytes()) == sha(originale), "RIPRISTINO FALLITO " + file
    for nome, e in esiti:
        print("%-45s %s" % (nome, e))
    print("ripristino verificato (sha256) su tutti i file mutati")
    return 0


if __name__ == "__main__":
    sys.exit(main())
