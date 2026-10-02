"""FALSIFICAZIONE del verificatore (02/10): mutazioni NUOVE, in direzioni che il
delegato del 01/10 non ha provato, piu' quelle delle correzioni del 02/10
(decisioni 12/13, stessa selezione, codice asincrono, L1, banco ottimista,
punto 25, R1). Ogni mutazione rimette un comportamento sbagliato in UN file,
lancia i test, scrive quanti diventano rossi; il file si ripristina SEMPRE dalla
copia e alla fine si controllano le impronte di tutti i file toccati.

Uso (dalla radice del worktree):
    python AUDIT_2026-10-02/MIKE_CHIUSURA_INTEGRATA_falsifica.py
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENG = "Betfair/mike/engine.py"
SRV = "Betfair/mike/service.py"
CER = "Betfair/mike/certificazione.py"
MBA = "Betfair/stream/backtest/minimi_banco.py"
BCO = "Betfair/stream/backtest/banco_comune.py"
CFA = "Betfair/stream/backtest/certifica.py"
SYN = "Betfair/mike/tools/synth_mike.py"

TEST = ["Betfair/mike/tests/test_mike_chiusura_copertura_2026_10_01.py",
        "Betfair/mike/tests/test_mike_chiusura_integrata_2026_10_02.py",
        "Betfair/mike/tests/test_mike_p5_copertura_banca_2026_09_29.py",
        "Betfair/mike/tests/test_mike_p5_4b_2026_09_29.py",
        "Betfair/mike/tests/test_mike_p5_4c_2026_09_29.py",
        "Betfair/mike/tests/test_mike_p5_banco_2026_09_29.py",
        "Betfair/mike/tests/test_mike_audit_2026_09_12.py",
        "Betfair/mike/tests/test_mike_riga_assente_e_arresto_2026_10_02.py",
        "Betfair/stream/tests/test_banco_minimi_it_2026_10_02.py"]

MUTAZIONI = [
    # --- direzioni nuove sul lavoro del delegato --------------------------------
    ("N1 la guardia lascia passare una BANCA da 0,99", ENG,
     "    if s >= minimo_listino(side) - 0.0005:\n        return VIA_DIRETTA",
     "    if s >= minimo_listino(side) - 0.0105:\n        return VIA_DIRETTA"),
    ("N2 FLAT dichiarato con residuo (ogni residuo creduto non chiudibile)", ENG,
     "    if residuo_non_chiudibile(ctx, snap, params, c):\n        return d\n"
     "    return _dichiara_residuo(ctx, d, snap, params, c, None, stato=\"LIVE_CLOSING\")",
     "    if True:\n        return d\n"
     "    return _dichiara_residuo(ctx, d, snap, params, c, None, stato=\"LIVE_CLOSING\")"),
    ("N3 rientro dopo un residuo dichiarato (decisione 13 tolta)", ENG,
     "    upd[\"reentry_allowed\"] = False\n    upd[\"reentry_done\"] = True\n",
     ""),
    ("N4 equivalente al prezzo sbagliato (lati del libro scambiati)", ENG,
     "    alt = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=bk.best_back,\n"
     "                          best_lay_price=bk.best_lay, fraction=1.0,",
     "    alt = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=bk.best_lay,\n"
     "                          best_lay_price=bk.best_back, fraction=1.0,"),
    ("N5 secondo CRITICAL sulla STESSA proposta (episodio rotto)", ENG,
     "    if prima is not None and prima.get(\"residuo_scoperto\") and prima.get(\"sostanza\") == sostanza:\n"
     "        return prima, False\n    stessa = prima is not None and prima.get(\"chiave\") == chiave",
     "    stessa = False"),
    # --- stessa selezione / decisione 12 ------------------------------------
    ("N6 chiusura sull'ALTRA selezione di serie (banca Over sopra il minimo)", ENG,
     "    if size_chiudibile(plan.size, \"lay\") and not _banca_di_apertura(legs, key[0]):",
     "    if size_chiudibile(plan.size, \"lay\"):"),
    ("N7 proposta del residuo: prima l'altra selezione", ENG,
     "            if _banca_di_apertura(ctx.legs, key[0]):\n                candidati.insert(0, eq)",
     "            if False:\n                candidati.insert(0, eq)"),
    ("N8 cash out col valore della banca anche quando parte la punta", ENG,
     "                locked = float(min(alt[1].expected_if_win, alt[1].expected_if_lose))",
     "                locked = float(min(plan.expected_if_win, plan.expected_if_lose))"),
    # --- servizio, certificazione -------------------------------------------
    ("N9 codice del rifiuto ignorato sulla strada asincrona del runner", SRV,
     "            codice_runner = str(e.get(\"error_code\") or \"\") or None",
     "            codice_runner = None"),
    ("N10 L1 non guarda la punta d'apertura sotto 0,50", CER,
     "             or _punta_sotto_floor(a, params)]", "             ]"),
    # --- banco ottimista ------------------------------------------------------
    ("N11 exchange del banco senza regola (ATTIVO di serie spento)", MBA,
     "ATTIVO = True\n", "ATTIVO = False\n"),
    ("N12 replace del banco senza il floor 0,50", MBA,
     "                    if ATTIVO and sotto_minimo(size, SOSTITUZIONE,",
     "                    if False and sotto_minimo(size, SOSTITUZIONE,"),
    ("N13 REST del banco senza la guardia del vero", BCO,
     "        if not self._place_and_trim_in_corso:\n            # 02/10 (banco ottimista)",
     "        if False:\n            # 02/10 (banco ottimista)"),
    ("N14 il controllo BANCO-SOTTO-MINIMO non scrive la violazione", CFA,
     "        if fuori and not any(getattr(v, \"codice\", \"\") == MB.CODICE_CONTROLLO",
     "        if False and not any(getattr(v, \"codice\", \"\") == MB.CODICE_CONTROLLO"),
    ("N15 sintetica di Ashdod con i livelli vecchi nel libro", SYN,
     "        self.azzera_livelli = bool(azzera_livelli)", "        self.azzera_livelli = False"),
    # --- punto 25 e R1 ----------------------------------------------------------
    ("P1 riga assente: si annulla senza rileggere il mercato via REST", SRV,
     "        if absent_closed:\n            stato_rest = _stato_rest_riga_assente(",
     "        if False:\n            stato_rest = _stato_rest_riga_assente("),
    ("P2 riga assente: mercato APERTO trattato come chiuso", SRV,
     "            if stato_rest == _REST_APERTO:\n                absent_closed = False",
     "            if stato_rest == _REST_APERTO:\n                absent_closed = True"),
    ("P3 riga assente: la rilettura REST non ha il ritmo (una per giro)", SRV,
     "    if prec is not None and now_ts - float(prec) < _RIGA_ASSENTE_REST_S:",
     "    if False:"),
    ("R1a arresto senza annullo degli ordini vivi", SRV,
     "            if leg.is_live and float(leg.size or 0.0) > float(leg.matched or 0.0) + 1e-9:",
     "            if False:"),
    ("R1b arresto senza CRITICAL sulle posizioni abbinate", SRV,
     "        if aperte:\n            esito[\"posizioni\"].append(",
     "        if False:\n            esito[\"posizioni\"].append("),
    ("R1c arresto senza tetto di tempo", SRV,
     "                if orologio() - t0 >= tetto_s:",
     "                if False:"),
    ("R1d main senza l'arresto ordinato degli ordini", SRV,
     "            if not args.once and not args.dry:\n                arresto_con_ordini(",
     "            if False:\n                arresto_con_ordini("),
]


def impronta(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    copie, prima = {}, {}
    cartella = tempfile.mkdtemp(prefix="falsifica_integrata_")
    for rel in sorted({m[1] for m in MUTAZIONI}):
        p = os.path.join(RADICE, rel)
        copie[rel] = os.path.join(cartella, rel.replace("/", "__"))
        shutil.copyfile(p, copie[rel])
        prima[rel] = impronta(p)
    esiti = []
    try:
        scelte = [m for m in MUTAZIONI if not sys.argv[1:] or m[0].split()[0] in sys.argv[1:]]
        for nome, rel, vecchio, nuovo in scelte:
            sorgente = open(copie[rel], encoding="utf-8").read()
            if sorgente.count(vecchio) != 1:
                esiti.append((nome, "MUTAZIONE NON APPLICABILE (testo trovato %d volte)"
                              % sorgente.count(vecchio), []))
                continue
            with open(os.path.join(RADICE, rel), "w", encoding="utf-8", newline="") as fh:
                fh.write(sorgente.replace(vecchio, nuovo))
            r = subprocess.run([sys.executable, "-m", "pytest", *TEST, "-q", "-p",
                                "no:cacheprovider", "-rf"], cwd=RADICE,
                               capture_output=True, text=True)
            coda = [l for l in r.stdout.splitlines() if l.startswith("FAILED")]
            righe = [l for l in r.stdout.splitlines()
                     if (" passed" in l or " failed" in l) and " in " in l]
            esiti.append((nome, righe[-1] if righe else (r.stdout[-300:] + r.stderr[-300:]),
                          coda))
            shutil.copyfile(copie[rel], os.path.join(RADICE, rel))
    finally:
        for rel, c in copie.items():
            shutil.copyfile(c, os.path.join(RADICE, rel))
    for rel in copie:
        assert impronta(os.path.join(RADICE, rel)) == prima[rel], "RIPRISTINO FALLITO " + rel
    rosse = 0
    for nome, sommario, coda in esiti:
        print("=" * 100)
        print(nome)
        print("   ", sommario)
        for f in coda:
            print("      ", f)
        rosse += 1 if " failed" in sommario else 0
    print("=" * 100)
    print("mutazioni rosse: %d su %d; file ripristinati, impronte identiche" % (rosse, len(esiti)))


if __name__ == "__main__":
    main()
