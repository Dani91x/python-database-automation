"""Falsificazione del blocco 2 di P5 (copertura banca Under 4,5, M3.1-M3.5, e
tolleranza del piatto sul 4,5). Ripristino da copia in memoria + hash.
Uso: python AUDIT_2026-09-29/mike_p5/falsifica_mike_p5_2.py
"""
import hashlib
import os
import subprocess
import sys

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENG = os.path.join(RADICE, "Betfair", "mike", "engine.py")
TEST = ["Betfair/mike/tests/test_mike_p5_copertura_banca_2026_09_29.py",
        "Betfair/mike/tests/test_mike_p5_compensazione_mercato_2026_09_29.py"]

MUTAZIONI = [
    ("B1 importo con la formula della puntata", ENG,
     "    x_pieno = cover_residual_lay(liab, c, float(params[\"cover_profit_factor\"]), already)\n    frazione, split_declassato",
     "    x_pieno = cover_residual(liab, 1.0 / (1.18 - 1.0) + 1.0, c, float(params[\"cover_profit_factor\"]), already)  # MUTAZIONE\n    frazione, split_declassato"),
    ("B2 importo lordo di commissione (lettura B)", ENG,
     "    return max(0.0, (target - float(already)) / (1.0 - float(commission)))",
     "    return max(0.0, (target - float(already)))  # MUTAZIONE"),
    ("B3 cuscinetto col segno sbagliato", ENG,
     "        cand = float(ticks_away(float(best_lay), +n))",
     "        cand = float(ticks_away(float(best_lay), -n))  # MUTAZIONE"),
    ("B4 gia' coperto ignorato (A = 0)", ENG,
     "    liab = under_liability(ctx.legs)\n    already = cover_matched_value(ctx.legs, c)\n    bk = snap.book(MARKET_OU45, SEL_UNDER)",
     "    liab = under_liability(ctx.legs)\n    already = 0.0  # MUTAZIONE\n    bk = snap.book(MARKET_OU45, SEL_UNDER)"),
    ("B5 M3.5 tolta: resto sotto 0,50 rincorso", ENG,
     "    size, _over = cover_legal_size(x_now, params, side=\"lay\")\n    if size < IT_LAY_MIN - _EPS:",
     "    size, _over = cover_legal_size(x_now, params, side=\"lay\")\n    if False:  # MUTAZIONE"),
    ("B6 M3.5 tolta nel riprezzo", ENG,
     "    size, _ = cover_legal_size(x, params, side=\"lay\")\n    if size < IT_LAY_MIN - _EPS:",
     "    size, _ = cover_legal_size(x, params, side=\"lay\")\n    if False:  # MUTAZIONE"),
    ("B7 libro Under assente non controllato", ENG,
     "    if bk is None:\n        return Decision(\"LIVE_UNCOVERED\", acts,\n                        \"copertura: libro Under 4.5 assente, si aspetta\",",
     "    if False:  # MUTAZIONE\n        return Decision(\"LIVE_UNCOVERED\", acts,\n                        \"copertura: libro Under 4.5 assente, si aspetta\","),
    ("B8 liquidita' non controllata", ENG,
     "    if float(bk.lay_size) + _EPS < size:",
     "    if False:  # MUTAZIONE"),
    ("B9 tetto sull'importo invece che sul rischio", ENG,
     "    rischio = size * (float(q_lim) - 1.0)\n",
     "    rischio = size  # MUTAZIONE\n"),
    ("B10 ramo banca mai scelto", ENG,
     "    if cover_form(params) == COVER_LAY_U45:\n        # 29/09 (M3.1): copertura come BANCA",
     "    if False:  # MUTAZIONE\n        # 29/09 (M3.1): copertura come BANCA"),
    ("B11 ripiego sotto 0,50 ignorato in _close_actions", ENG,
     "        sel_ordine, piano = cv.ripieghi.get(key, (key[1], plan))",
     "        sel_ordine, piano = (key[1], plan)  # MUTAZIONE"),
    ("B12 ripiego senza il controllo del multiplo di 0,50", ENG,
     "    if s < IT_BACK_MIN - _EPS or abs(round(s / IT_BACK_STEP) * IT_BACK_STEP - s) > 0.005:",
     "    if s < IT_BACK_MIN - _EPS:  # MUTAZIONE"),
    ("B13 piatto allargato a 0,05 x p", ENG,
     "    return max(_FLAT_EPS, 0.005 * float(chiusure[-1].fill_price))",
     "    return max(_FLAT_EPS, 0.05 * float(chiusure[-1].fill_price))  # MUTAZIONE"),
    ("B14 piatto ristretto al centesimo (difetto di prima)", ENG,
     "    return max(_FLAT_EPS, 0.005 * float(chiusure[-1].fill_price))",
     "    return _FLAT_EPS  # MUTAZIONE"),
    ("B15 banca legalizzata come una puntata", ENG,
     "    if side == \"lay\" or params.get(\"exact_sizes\", True):",
     "    if params.get(\"exact_sizes\", True):  # MUTAZIONE"),
    ("Q5 chiave a due selezioni sempre Under (mutazione del coordinatore)", ENG,
     "    return (MARKET_OU45, SEL_UNDER if (w - l) > 0 else SEL_OVER)",
     "    return (MARKET_OU45, SEL_UNDER)  # MUTAZIONE"),
    ("B16 riprezzo della chiusura sulla selezione della gamba", ENG,
     "        if leg.market == MARKET_OU45 and _banca_di_apertura(ctx.legs, MARKET_OU45):",
     "        if False:  # MUTAZIONE"),
]


def h(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    py = sys.executable
    env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_KEY="x",
               SUPABASE_SERVICE_ROLE_KEY="x")
    originali = {p: open(p, "rb").read() for p in sorted({m[1] for m in MUTAZIONI} | {ENG})}
    hash0 = {p: h(p) for p in originali}
    esiti = []
    try:
        for nome, file, vecchio, nuovo in MUTAZIONI:
            testo = originali[file].decode("utf-8")
            if "\r\n" in testo:
                vecchio = vecchio.replace("\n", "\r\n")
                nuovo = nuovo.replace("\n", "\r\n")
            if testo.count(vecchio) != 1:
                esiti.append((nome, "MUTAZIONE NON APPLICABILE (%d occorrenze)" % testo.count(vecchio)))
                continue
            with open(file, "wb") as f:
                f.write(testo.replace(vecchio, nuovo).encode("utf-8"))
            r = subprocess.run([py, "-m", "pytest", *TEST, "-q", "-p", "no:cacheprovider"],
                               cwd=RADICE, env=env, capture_output=True, text=True)
            coda = [x for x in r.stdout.splitlines() if " passed" in x or " failed" in x]
            rossi = [x.split("::")[-1] for x in r.stdout.splitlines() if x.startswith("FAILED")]
            esiti.append((nome, ("ROSSO " if r.returncode else "VERDE (!) ") + (coda[-1] if coda else r.stdout[-300:]), rossi))
            with open(file, "wb") as f:
                f.write(originali[file])
    finally:
        for p, b in originali.items():
            with open(p, "wb") as f:
                f.write(b)
    for p in originali:
        assert h(p) == hash0[p], "RIPRISTINO FALLITO " + p
        assert b"MUTAZIONE" not in open(p, "rb").read(), "MUTAZIONE RIMASTA " + p
    for e in esiti:
        print(" | ".join(str(x) for x in e))
    print("ripristino verificato: hash identici, nessuna MUTAZIONE nei file")


if __name__ == "__main__":
    main()
