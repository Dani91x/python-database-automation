# Falsificazione del coordinatore sul pannello Dutching: una mutazione alla volta, vitest, ripristino.
# Ogni mutazione toglie un pezzo della correzione: i test devono diventare ROSSI.
import hashlib
import io
import os
import subprocess
import sys

R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
F = os.path.join(R, "frontend", "src", "components", "live", "DutchingPanel.tsx")
OUT = os.path.join(R, "ARCHITETTURA_2026-10", "AUDIT_MATEMATICA_ML", "lavori", "fase2", "suite", "falsifica_ui_coord.txt")

MUT = [
    ("M1 variable abilitato sul lay",
     "<option value=\"variable\" disabled={side === 'lay'}>",
     "<option value=\"variable\">"),
    ("M2 anteprima variable con la formula vecchia (stake ~ peso/quota)",
     "const variable = calcMode === 'variable' && validRaws.length > 0",
     "const variable = false && validRaws.length > 0"),
    ("M3 V3 tolto: ok senza legs = inviato",
     "if (res.ok && !(Array.isArray(placedLegs) && placedLegs.length > 0)) {",
     "if (false && res.ok && !(Array.isArray(placedLegs) && placedLegs.length > 0)) {"),
    ("M4 bottone non disabilitato su variable+lay",
     "|| (side === 'lay' && calcMode === 'variable')\n",
     "\n"),
    ("M5 guardBeforeSend senza il blocco variable+lay (insieme a M4)",
     "if (side === 'lay' && calcMode === 'variable') {\n            return",
     "if (false) {\n            return"),
    ("M6 arrotondamento ingenuo al posto di round() di Python",
     "return Number(x.toFixed(2)); // toFixed",
     "return Math.round(x * 100) / 100; // toFixed"),
    ("M7 pesi irrealizzabili non bloccano l'invio",
     "if (preview.infeasible) return preview.infeasible;",
     "if (false) return preview.infeasible;"),
]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


orig = io.open(F, encoding="utf-8", newline="").read()
h0 = sha(F)
log = []
try:
    for name, a, b in MUT:
        src = orig
        if name.startswith("M5"):
            src = src.replace("|| (side === 'lay' && calcMode === 'variable')\n", "\n", 1)
        n = src.count(a)
        if n != 1:
            log.append(f"{name}: SALTATA (occorrenze={n})")
            continue
        io.open(F, "w", encoding="utf-8", newline="").write(src.replace(a, b, 1))
        p = subprocess.run("npx vitest run src/components/live/DutchingPanel.test.tsx",
                           cwd=os.path.join(R, "frontend"), shell=True, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=400)
        tail = [l for l in (p.stdout + p.stderr).splitlines() if "Tests" in l]
        log.append(f"{name}: exit={p.returncode} {tail[-1].strip() if tail else ''}")
        io.open(F, "w", encoding="utf-8", newline="").write(orig)
finally:
    io.open(F, "w", encoding="utf-8", newline="").write(orig)
log.append(f"ripristino: sha uguale all'originale = {sha(F) == h0}")
io.open(OUT, "w", encoding="utf-8").write("\n".join(log) + "\n")
print("\n".join(log))
