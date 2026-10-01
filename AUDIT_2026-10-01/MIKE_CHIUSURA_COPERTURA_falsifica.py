"""FALSIFICAZIONE della correzione del 01/10 (chiusura della copertura).

Ogni mutazione rimette un comportamento VECCHIO (o toglie una guardia nuova) in
``Betfair/mike/engine.py``, lancia i test nuovi e quelli toccati, e scrive
quanti diventano rossi. Il file originale si ripristina SEMPRE dalla copia
(e alla fine si controlla l'impronta). Uso: python .scratch_mike/falsifica.py"""
import hashlib
import os
import shutil
import subprocess
import sys

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(RADICE, "Betfair", "mike", "engine.py")
COPIA = os.path.join(RADICE, ".scratch_mike", "engine_corretto.py")
TEST = ["Betfair/mike/tests/test_mike_chiusura_copertura_2026_10_01.py",
        "Betfair/mike/tests/test_mike_p5_copertura_banca_2026_09_29.py",
        "Betfair/mike/tests/test_mike_p5_4b_2026_09_29.py",
        "Betfair/mike/tests/test_mike_audit_2026_09_12.py",
        "Betfair/mike/tests/test_mike_p5_compensazione_mercato_2026_09_29.py",
        "Betfair/mike/tests/test_mike_engine.py",
        "Betfair/mike/tests/test_mike_flusso_fischio_2026_09_13.py"]

MUTAZIONI = [
    ("M1 ripiego: torna il vincolo del MULTIPLO di 0,50",
     "    if eq is None or not size_chiudibile(eq[1].size, \"back\"):\n        return None\n    return eq",
     "    if eq is None or not size_chiudibile(eq[1].size, \"back\"):\n        return None\n"
     "    s = round(float(eq[1].size), 2)\n"
     "    if abs(round(s / 0.5) * 0.5 - s) > 0.005:\n        return None\n    return eq"),
    ("M2 size_chiudibile/guardia PERMISSIVE: una chiusura sotto il minimo parte (soglia al centesimo)",
     "    if role in CLOSING_ROLES:\n        return VIA_NON_SI_MANDA\n",
     "    if role in CLOSING_ROLES:\n        return VIA_DIRETTA\n"),
    ("M3a RITMO: si ritenta a ogni giro (close_retry_s ignorato dopo un rifiuto)",
     "    if not ultimi:\n        return 0.0\n    return max(0.0, float(params[\"close_retry_s\"]) - (float(snap.now) - max(ultimi)))",
     "    return 0.0"),
    ("M3b RIFIUTO PER TAGLIA ignorato: lo stesso strumento si ripropone (stesso o altro importo)",
     "    if isinstance(r, dict) and any(c in str(r.get(\"motivo\") or \"\").upper()\n"
     "                                   for c in RIFIUTI_PER_TAGLIA):\n        return r\n    return None",
     "    return None"),
    ("M4 CONTROLLO DI PIATTO tolto: FLAT «chiuso (profit)» con residuo",
     "    if d.state != \"FLAT\":\n        return d\n    if not live_open_selections(ctx.legs, snap.goals):",
     "    return d\n    if not live_open_selections(ctx.legs, snap.goals):"),
    ("M5 GUARDIA UNICA tolta: nessun filtro finale sugli ordini sotto minimo",
     "    if not scartate:\n        return d\n    tolte = {id(a) for a in scartate}",
     "    return d\n    tolte = {id(a) for a in scartate}"),
    ("M6 CASH OUT: valore della banca impossibile invece della puntata che parte",
     "                locked = float(min(alt[1].expected_if_win, alt[1].expected_if_lose))",
     "                locked = float(min(plan.expected_if_win, plan.expected_if_lose))"),
    ("M7 la proposta del residuo DECADE nel gate (si toglie e si rimette a ogni giro)",
     "    if isinstance(ctx.uscita_proposta, dict) and ctx.uscita_proposta.get(\"residuo_scoperto\"):\n"
     "        # 01/10: la proposta del RESIDUO SCOPERTO non e' un'uscita della\n"
     "        # strategia: vive finche' il residuo c'e' (``_proposta_residuo_finale``)\n"
     "        return d\n",
     ""),
    ("M8 cancel di chiusura anche quando la chiusura non parte (ordine/annullo prima della guardia)",
     "        if via_ordine(role_map[key], piano.side, piano.size, params) != VIA_DIRETTA:\n            continue\n",
     ""),
    ("M9 MINIMO DELLA BANCA torna 0,50",
     "IT_LAY_MIN = IT_MIN_LAY\n", "IT_LAY_MIN = 0.50\n"),
    ("M16 MINIMO DELLA PUNTA torna 2,00 (costante duplicata invece della fonte unica)",
     "IT_BACK_MIN = IT_MIN_BACK\n", "IT_BACK_MIN = 2.0\n"),
    ("M17 torna il PASSO da 0,50 delle puntate",
     "IT_BACK_STEP = 0.01\n", "IT_BACK_STEP = 0.5\n"),
    ("M18 place-and-trim sotto l'importo finale minimo (0,50) ammesso",
     "    if s < SUBMIN_IMPORTO_FINALE_MIN - 0.0005:\n", "    if False:\n"),
    ("M19 rifiuto del runner SOTTO_MINIMO_NON_PIAZZABILE ignorato",
     "RIFIUTI_PER_TAGLIA = (\"INVALID_BET_SIZE\", \"SOTTO_MINIMO_NON_PIAZZABILE\")",
     "RIFIUTI_PER_TAGLIA = (\"INVALID_BET_SIZE\",)"),
    ("M9b ripiego di nuovo SOLO con la copertura-banca (forma di prima senza puntata equivalente)",
     "    if size_chiudibile(plan.size, \"lay\"):\n        return None\n    eq = puntata_equivalente",
     "    if size_chiudibile(plan.size, \"lay\") or not _banca_di_apertura(legs, key[0]):\n        return None\n    eq = puntata_equivalente"),
    ("M12 BANCA d'apertura sotto 1,00 ammessa (via place-and-trim)",
     "    if str(side or \"\").lower() == \"lay\":\n        # 01/10 (vincolo definitivo)",
     "    if False:\n        # 01/10 (vincolo definitivo)"),
    ("M14 un avviso CRITICAL a ogni cambio dell'ordine proposto (niente episodio)",
     "    nuova = not (stessa and bool((prima or {}).get(\"residuo_scoperto\")))",
     "    nuova = True"),
    ("M15 uscita in perdita con ordini tolti (sotto minimo) passa il cancello senza firma",
     "        cat = \"chiusura\"\n    if cat is None:",
     "        pass\n    if cat is None:"),
    ("M13 proposta senza le scelte dell'utente",
     "             \"esposizioni\": esposizioni, \"alternative\": _alternative_residuo(ordini),",
     "             \"esposizioni\": esposizioni,"),
    ("M10 CHIUDI dell'utente sotto il minimo: torna «prezzi non disponibili», senza proposta",
     "        if any(pl.actionable for pl in cv_m.plans.values()):",
     "        if False:"),
    ("M11 FOK non abbinato trattato come rifiuto definitivo (si dichiara residuo a ogni FOK mancato)",
     "    if isinstance(r, dict) and any(c in str(r.get(\"motivo\") or \"\").upper()\n"
     "                                   for c in RIFIUTI_PER_TAGLIA):\n        return r\n    return None",
     "    if isinstance(r, dict):\n        return r\n    return None"),
]


def impronta(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    shutil.copyfile(ENGINE, COPIA)
    prima = impronta(ENGINE)
    sorgente = open(COPIA, encoding="utf-8").read()
    esiti = []
    try:
        for nome, vecchio, nuovo in MUTAZIONI:
            if sorgente.count(vecchio) != 1:
                esiti.append((nome, "MUTAZIONE NON APPLICABILE (testo trovato %d volte)"
                              % sorgente.count(vecchio)))
                continue
            with open(ENGINE, "w", encoding="utf-8", newline="") as fh:
                fh.write(sorgente.replace(vecchio, nuovo))
            r = subprocess.run([sys.executable, "-m", "pytest", *TEST, "-q", "-p", "no:cacheprovider",
                                "-rf"], cwd=RADICE, capture_output=True, text=True)
            coda = [l for l in r.stdout.splitlines() if l.startswith("FAILED")]
            righe = [l for l in r.stdout.splitlines() if (" passed" in l or " failed" in l) and " in " in l]
            sommario = righe[-1] if righe else (r.stdout[-300:] + r.stderr[-300:])
            esiti.append((nome, sommario, coda))
            shutil.copyfile(COPIA, ENGINE)
    finally:
        shutil.copyfile(COPIA, ENGINE)
    assert impronta(ENGINE) == prima, "RIPRISTINO FALLITO"
    for e in esiti:
        print("=" * 100)
        print(e[0])
        print("   ", e[1])
        for f in (e[2] if len(e) > 2 else []):
            print("      ", f)
    print("=" * 100)
    print("engine.py ripristinato, impronta", prima[:16])


if __name__ == "__main__":
    main()
