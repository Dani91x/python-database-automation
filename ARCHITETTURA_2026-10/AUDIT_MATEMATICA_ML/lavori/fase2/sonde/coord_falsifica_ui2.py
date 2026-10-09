# Seconda passata: mutazioni combinate (le guardie sono doppie: bottone disabilitato + guardBeforeSend).
import hashlib, io, os, subprocess
R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
F = os.path.join(R, "frontend", "src", "components", "live", "DutchingPanel.tsx")
OUT = os.path.join(R, "ARCHITETTURA_2026-10", "AUDIT_MATEMATICA_ML", "lavori", "fase2", "suite", "falsifica_ui_coord2.txt")
orig = io.open(F, encoding="utf-8", newline="").read()
NL = "\r\n" if "\r\n" in orig else "\n"
B_VAR = "|| (side === 'lay' && calcMode === 'variable')" + NL
G_VAR = "if (side === 'lay' && calcMode === 'variable') {"
B_INF = "|| preview.infeasible != null" + NL
G_INF = "if (preview.infeasible) return preview.infeasible;"
OPT = "<option value=\"variable\" disabled={side === 'lay'}>"
MUT = [
    ("M4 solo bottone variable+lay riabilitato", [(B_VAR, "")]),
    ("M5 bottone + guardBeforeSend variable+lay tolti", [(B_VAR, ""), (G_VAR, "if (false) {")]),
    ("M5b bottone + guard + opzione (tutto il blocco UI variable+lay)", [(B_VAR, ""), (G_VAR, "if (false) {"), (OPT, "<option value=\"variable\">")]),
    ("M7 bottone + guard pesi irrealizzabili tolti", [(B_INF, ""), (G_INF, "if (false) return preview.infeasible;")]),
]
h0 = hashlib.sha256(orig.encode("utf-8")).hexdigest()
log = [f"fine riga: {'CRLF' if NL == chr(13)+chr(10) else 'LF'}"]
try:
    for name, reps in MUT:
        src = orig; ok = True
        for a, b in reps:
            if src.count(a) != 1:
                log.append(f"{name}: SALTATA ({a!r} occorrenze={src.count(a)})"); ok = False; break
            src = src.replace(a, b, 1)
        if not ok:
            continue
        io.open(F, "w", encoding="utf-8", newline="").write(src)
        p = subprocess.run("npx vitest run src/components/live/DutchingPanel.test.tsx", cwd=os.path.join(R, "frontend"),
                           shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=400)
        t = [l for l in (p.stdout + p.stderr).splitlines() if "Tests" in l]
        log.append(f"{name}: exit={p.returncode} {t[-1].strip() if t else ''}")
        io.open(F, "w", encoding="utf-8", newline="").write(orig)
finally:
    io.open(F, "w", encoding="utf-8", newline="").write(orig)
log.append("ripristino sha uguale: " + str(hashlib.sha256(open(F, 'rb').read()).hexdigest() == hashlib.sha256(orig.encode('utf-8')).hexdigest()))
io.open(OUT, "w", encoding="utf-8").write("\n".join(log) + "\n")
