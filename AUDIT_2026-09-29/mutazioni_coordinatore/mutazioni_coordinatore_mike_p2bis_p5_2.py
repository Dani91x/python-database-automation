"""Mutazioni del COORDINATORE sui pacchetti P2-bis (punteggio assente) e P5
blocco 2 + 2B (la copertura come BANCA Under 4,5) di Mike.

Ogni mutazione rompe UN punto del codice nuovo: i test devono diventare rossi.
Ripristino da copia in memoria con controllo dell'hash. Si lancia dalla radice
del worktree di verifica. I due test del contratto pannello/config sono rossi
per attesa (il campo del pannello arriva con la patch dell'app): si escludono.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

PY = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.venv\Scripts\python.exe"
ENG = "Betfair/mike/engine.py"
CFG = "Betfair/mike/config.py"
TEST = ["Betfair/mike", "--deselect",
        "Betfair/mike/tests/test_mike_certificazione_ui_2026_09_11.py::test_contratto_parametri_stesse_chiavi_in_ui_e_backend",
        "--deselect",
        "Betfair/mike/tests/test_mike_certificazione_ui_2026_09_11.py::test_contratto_parametri_stessi_clamp_scelte_e_default"]

MUT: List[Tuple[str, str, bytes, bytes]] = [
    # -------------------------------------------------------------- P2-bis
    ("B1 punteggio assente: il cash out intelligente lo tratta da zero gol", ENG,
     b"        tele[\"punteggio_assente\"] = True\n        return False, \"\", tele\n    g = int(goals)",
     b"        goals = 0\n    g = int(goals)"),
    ("B2 punteggio assente: la copertura lo tratta da zero gol", ENG,
     b"    if goals is None:\n        return \"wait\"",
     b"    if goals is None:\n        goals = 0\n    if False:\n        return \"wait\""),
    ("B3 punteggio assente, forma vecchia: la copertura ordinata parte lo stesso", ENG,
     b"    if timing == \"wait\" and ctx.cover_forced and not dopo_gol and snap.goals is not None:\n        timing = \"cover\"\n    x_pieno = None",
     b"    if timing == \"wait\" and ctx.cover_forced and not dopo_gol:\n        timing = \"cover\"\n    x_pieno = None"),
    ("B4 punteggio assente, forma nuova: la banca ordinata parte lo stesso", ENG,
     b"    if timing == \"wait\" and ctx.cover_forced and not dopo_gol and snap.goals is not None:\n        timing = \"cover\"\n    x_pieno = cover_residual_lay(",
     b"    if timing == \"wait\" and ctx.cover_forced and not dopo_gol:\n        timing = \"cover\"\n    x_pieno = cover_residual_lay("),
    # ------------------------------------------------------- P5 blocco 2
    ("N1 importo della banca: senza dividere per (1 - commissione)", ENG,
     b"    return max(0.0, (target - float(already)) / (1.0 - float(commission)))",
     b"    return max(0.0, (target - float(already)))"),
    ("N2 importo della banca: non toglie cio' che e' gia' coperto", ENG,
     b"    return max(0.0, (target - float(already)) / (1.0 - float(commission)))",
     b"    return max(0.0, target / (1.0 - float(commission)))"),
    ("N3 forma sconosciuta = banca", ENG,
     b"    return v if v in (COVER_LAY_U45, COVER_BACK_O45) else COVER_BACK_O45",
     b"    return v if v in (COVER_LAY_U45, COVER_BACK_O45) else COVER_LAY_U45"),
    ("N4 valore di serie gia' sulla banca", CFG,
     b"    \"cover_form\": (\"back_over45\", str, None, None, (\"lay_under45\", \"back_over45\")),",
     b"    \"cover_form\": (\"lay_under45\", str, None, None, (\"lay_under45\", \"back_over45\")),"),
    ("N5 cuscinetto della banca SOTTO il miglior prezzo", ENG,
     b"        cand = float(ticks_away(float(best_lay), +n))",
     b"        cand = float(ticks_away(float(best_lay), -n))"),
    ("N6 la banca esce sull'Over invece che sull'Under", ENG,
     b"    acts.append(_place(\"over_cover\", MARKET_OU45, SEL_UNDER, \"lay\", q_lim, size,",
     b"    acts.append(_place(\"over_cover\", MARKET_OU45, SEL_OVER, \"lay\", q_lim, size,"),
    ("N7 la copertura nuova esce come PUNTATA", ENG,
     b"    acts.append(_place(\"over_cover\", MARKET_OU45, SEL_UNDER, \"lay\", q_lim, size,",
     b"    acts.append(_place(\"over_cover\", MARKET_OU45, SEL_UNDER, \"back\", q_lim, size,"),
    ("N8 liquidita': la banca parte anche se al miglior prezzo non c'e' tutto", ENG,
     b"    if float(bk.lay_size) + _EPS < size:",
     b"    if False:"),
    ("N9 resto sotto 0,50: parte lo stesso un ordine", ENG,
     b"    size, _over = cover_legal_size(x_now, params, side=\"lay\")\n    if size < IT_LAY_MIN - _EPS:",
     b"    size, _over = cover_legal_size(x_now, params, side=\"lay\")\n    if False:"),
    ("N10 tetto per partita: conta l'importo e non il rischio", ENG,
     b"    rischio = size * (float(q_lim) - 1.0)",
     b"    rischio = size"),
    ("N11 tetto per partita ignorato dalla banca", ENG,
     b"    if rischio > room + _EPS:",
     b"    if False:"),
    ("N12 libro Under 4,5 assente: nessuna attesa", ENG,
     b"    if bk is None:\n        return Decision(\"LIVE_UNCOVERED\", acts,\n                        \"copertura: libro Under 4.5 assente, si aspetta\",",
     b"    if False:\n        return Decision(\"LIVE_UNCOVERED\", acts,\n                        \"copertura: libro Under 4.5 assente, si aspetta\","),
    ("N13 mercato Under 4,5 sospeso: la banca parte lo stesso", ENG,
     b"    if not operabile(bk):\n        return Decision(\"LIVE_UNCOVERED\", acts,\n                        \"copertura: mercato Under 4.5 %s, si aspetta la riapertura\"",
     b"    if False:\n        return Decision(\"LIVE_UNCOVERED\", acts,\n                        \"copertura: mercato Under 4.5 %s, si aspetta la riapertura\""),
    ("N14 troppi gol: la banca copre lo stesso", ENG,
     b"    if timing == \"skip\":\n        return Decision(\"LIVE_COVERED\", acts, \"copertura saltata: troppi gol\",\n                        updates={\"cover_skipped\": True, \"cover_stage\": 0, \"cover_forced\": False})\n    if liab <= 0.0:\n        return Decision(\"LIVE_COVERED\", acts, \"nessuna liability Under da coprire\",\n                        updates={\"cover_skipped\": True, \"cover_stage\": 0, \"cover_forced\": False})\n    if bk is None:",
     b"    if False:\n        return Decision(\"LIVE_COVERED\", acts, \"copertura saltata: troppi gol\",\n                        updates={\"cover_skipped\": True, \"cover_stage\": 0, \"cover_forced\": False})\n    if liab <= 0.0:\n        return Decision(\"LIVE_COVERED\", acts, \"nessuna liability Under da coprire\",\n                        updates={\"cover_skipped\": True, \"cover_stage\": 0, \"cover_forced\": False})\n    if bk is None:"),
    ("N15 tranche della banca: minimo piazzabile quello delle puntate", ENG,
     b"        piu_piccola_piazzabile = IT_LAY_MIN",
     b"        pass"),
    ("N16 riprezzo della banca: resto sotto 0,50 rincorso con un secondo ordine", ENG,
     b"    size, _ = cover_legal_size(x, params, side=\"lay\")\n    if size < IT_LAY_MIN - _EPS:",
     b"    size, _ = cover_legal_size(x, params, side=\"lay\")\n    if False:"),
    ("N17 riprezzo della banca a mercato sospeso", ENG,
     b"    if bk is not None and not operabile(bk):\n        return Decision(\"LIVE_COVER_PENDING\", [],\n                        \"copertura: mercato Under 4.5 %s, nessun riprezzo\"",
     b"    if False:\n        return Decision(\"LIVE_COVER_PENDING\", [],\n                        \"copertura: mercato Under 4.5 %s, nessun riprezzo\""),
    ("N18 forma nuova: il riprezzo usa il ramo vecchio (punta Over)", ENG,
     b"            ctx.attempts < int(params[\"close_max_attempts\"]) and \\\n            cover_form(params) == COVER_LAY_U45:",
     b"            ctx.attempts < int(params[\"close_max_attempts\"]) and \\\n            False:"),
    ("N19 piatto del 4,5: tolleranza larga dieci volte", ENG,
     b"    return max(_FLAT_EPS, 0.005 * float(chiusure[-1].fill_price))",
     b"    return max(_FLAT_EPS, 0.05 * float(chiusure[-1].fill_price))"),
    ("N20 piatto del 4,5: nessuna tolleranza di arrotondamento", ENG,
     b"    return max(_FLAT_EPS, 0.005 * float(chiusure[-1].fill_price))",
     b"    return _FLAT_EPS"),
    ("N21 ripiego della chiusura: anche nella forma vecchia", ENG,
     b"    if float(plan.size) >= IT_LAY_MIN - _EPS or not _banca_di_apertura(legs, key[0]):",
     b"    if float(plan.size) >= IT_LAY_MIN - _EPS:"),
    ("N22 ripiego della chiusura: puntata non piazzabile accettata", ENG,
     b"    if s < IT_BACK_MIN - _EPS or abs(round(s / IT_BACK_STEP) * IT_BACK_STEP - s) > 0.005:\n        return None",
     b"    if False:\n        return None"),
    ("N23 ripiego della chiusura mai usato nell'ordine", ENG,
     b"        sel_ordine, piano = cv.ripieghi.get(key, (key[1], plan))",
     b"        sel_ordine, piano = (key[1], plan)"),
    ("N24 una bancata legalizzata come una puntata", ENG,
     b"    if side == \"lay\" or params.get(\"exact_sizes\", True):",
     b"    if params.get(\"exact_sizes\", True):"),
    ("N25 forma nuova ignorata: parte sempre la punta Over", ENG,
     b"    if cover_form(params) == COVER_LAY_U45:\n        # 29/09 (M3.1): copertura come BANCA Under 4,5 (stessi controlli, stesso",
     b"    if False:\n        # 29/09 (M3.1): copertura come BANCA Under 4,5 (stessi controlli, stesso"),
    ("N26 chiusura in riprezzo con la copertura-banca: resta sulla selezione vecchia", ENG,
     b"        if leg.market == MARKET_OU45 and _banca_di_apertura(ctx.legs, MARKET_OU45):",
     b"        if False:"),
]


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def suite() -> Tuple[bool, str]:
    r = subprocess.run([PY, "-m", "pytest", *TEST, "-q", "-p", "no:cacheprovider", "-x"],
                       capture_output=True, text=True, timeout=1800)
    righe = [x for x in (r.stdout or "").splitlines() if x.strip()]
    coda = righe[-1:] or ["?"]
    primo = next((x for x in righe if x.startswith("FAILED") or x.startswith("ERROR")), "")
    return r.returncode == 0, (coda[0] + ("  | " + primo[:150] if primo else ""))


def main() -> int:
    solo = set(sys.argv[1:])
    ok, coda = suite()
    print("BASE (senza mutazioni): %s  %s" % ("VERDE" if ok else "ROSSA", coda), flush=True)
    if not ok:
        return 2
    vive = 0
    fatte = 0
    for nome, f, prima, dopo in MUT:
        if solo and nome.split()[0] not in solo:
            continue
        fatte += 1
        p = Path(f)
        orig = p.read_bytes()
        crlf = b"\r\n" in orig
        a = prima.replace(b"\n", b"\r\n") if crlf else prima
        d = dopo.replace(b"\n", b"\r\n") if crlf else dopo
        n = orig.count(a)
        if n != 1:
            print("%-84s ANCORA NON UNICA (%d)" % (nome, n), flush=True)
            vive += 1
            continue
        try:
            p.write_bytes(orig.replace(a, d))
            verde, coda = suite()
        finally:
            p.write_bytes(orig)
        assert md5(p.read_bytes()) == md5(orig)
        errore = "error" in coda and "failed" not in coda
        print("%-84s %s  %s" % (nome, "SOPRAVVISSUTA" if verde else
                                ("ERRORE DI RACCOLTA" if errore else "rossa"), coda), flush=True)
        vive += 1 if (verde or errore) else 0
    print("mutazioni sopravvissute o non valide: %d su %d" % (vive, fatte))
    return 0


if __name__ == "__main__":
    sys.exit(main())
