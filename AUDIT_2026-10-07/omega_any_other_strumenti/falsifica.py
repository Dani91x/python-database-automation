# Falsificazione dei test del cantiere OMEGA ANY OTHER (07/10).
# Ogni mutazione reintroduce un difetto; i test indicati DEVONO diventare rossi.
# Il file originale e' tenuto in memoria e riscritto in un finally.
import subprocess, sys, os

RADICE = "/home/user/python-database-automation/.claude/worktrees/agent-a5fe9c88028ad9ed4"
T = "Betfair/omega/tests/test_v3_any_other_2026_10_07.py"
V3 = "Betfair/omega/omega_v3.py"
EN = "Betfair/omega/omega_engine.py"
CF = "Betfair/omega/omega_config.py"
PRP = "Betfair/omega/omega_proposte.py"

MUTAZIONI = [
    ("M1 aggregato senza regola di distanza (HEAD)", V3,
     "        elif aggregato:\n            dist = distanza_aggregato(",
     "        elif False:  # MUTAZIONE\n            dist = distanza_aggregato("),
    ("M2 distanza da 1 invece che da 0 (il gia' vinto passa)", V3,
     "    for d in range(0, int(limite) + 1):",
     "    for d in range(1, int(limite) + 1):  # MUTAZIONE"),
    ("M3 coda ignorata (griglia troncata e normalizzata)", V3,
     "        if estesa:\n            griglia_agg = estesa",
     "        if False:  # MUTAZIONE\n            griglia_agg = estesa"),
    ("M4 l'aggregato copre anche i punteggi quotati", V3,
     "    if (h, a) in quotate:\n        return False\n    if direzione == \"home\":",
     "    if False:  # MUTAZIONE\n        return False\n    if direzione == \"home\":"),
    ("M5 interruttore spento ignorato", V3,
     "        if aggregato and not includi_aggregati:",
     "        if False:  # MUTAZIONE"),
    ("M6 parametri_v3 sempre acceso", CF,
     "        \"include_aggregate\": bool(_coerce(\"v3_include_aggregate\",",
     "        \"include_aggregate\": True or bool(_coerce(\"v3_include_aggregate\",  # MUTAZIONE"),
    ("M7 raccordo senza coda", EN,
     "mult_rossi=mult, includi_coda=con_aggregati)",
     "mult_rossi=mult, includi_coda=False)  # MUTAZIONE"),
    ("M8 proposte: l'aggregato torna a saltare", PRP,
     "    if laid is None and not V3.e_aggregato(nome):",
     "    if laid is None:  # MUTAZIONE"),
    ("M9 proposte: ripiego [nome] per l'aggregato", PRP,
     "        if not V3.punteggi_quotati(nomi):\n            return []",
     "        if False:  # MUTAZIONE\n            return []"),
    ("M10 traiettoria: aggregato mai calcolato", V3,
     "        elif aggregato:\n            pe = float(probabilita_selezioni(",
     "        elif False:  # MUTAZIONE\n            pe = float(probabilita_selezioni("),
    ("M11 regolamento: unquoted prima della direzione (HEAD)", EN,
     "    return bool(V3.copre(nome, (h, a), quotati))",
     "    return True if 'unquoted' in nome.lower() else bool(V3.copre(nome, (h, a), quotati))  # MUTAZIONE"),
    ("M12 default dell'interruttore spento", CF,
     "    \"v3_include_aggregate\": (True, bool, None, None),",
     "    \"v3_include_aggregate\": (False, bool, None, None),  # MUTAZIONE"),
    ("M13 griglia quotata scritta a mano (0..3) invece che dai runner", V3,
     "    quotate = punteggi_quotati(nomi_mercato if nomi_mercato is not None\n"
     "                               else [str(r.name or \"\") for r in runners])",
     "    quotate = frozenset((h, a) for h in range(4) for a in range(4))  # MUTAZIONE"),
]

risultati = []
for nome, f, vecchio, nuovo in MUTAZIONI:
    p = os.path.join(RADICE, f)
    orig = open(p, encoding="utf-8").read()
    assert orig.count(vecchio) == 1, (nome, orig.count(vecchio))
    try:
        open(p, "w", encoding="utf-8").write(orig.replace(vecchio, nuovo))
        r = subprocess.run([sys.executable, "-m", "pytest", T, "-q", "-p", "no:cacheprovider"],
                           cwd=RADICE, capture_output=True, text=True, timeout=600)
        ultima = [x for x in r.stdout.splitlines() if " passed" in x or " failed" in x]
        rossi = [x.split("::", 1)[1].split(" ")[0] for x in r.stdout.splitlines()
                 if x.startswith("FAILED")]
        risultati.append((nome, r.returncode != 0, ultima[-1] if ultima else r.stdout[-300:],
                          rossi))
    finally:
        open(p, "w", encoding="utf-8").write(orig)

for nome, rosso, riga, rossi in risultati:
    print(("ROSSO " if rosso else "SOPRAVVISSUTA ") + nome + " -> " + riga)
    for x in rossi[:6]:
        print("     " + x)
