"""25/09 - FALSIFICAZIONE lato UI dell'interruttore "uscite automatiche".
Stesso metodo di mutazioni_uscite_automatiche.py (ripristino dalla copia in
memoria, verificato byte per byte), con vitest sul file di test indicato."""
import os
import subprocess
import sys

WT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FE = os.path.join(WT, "frontend")

MUT = [
    ("F1 PannelloBot: il pulsante manda lo stato attuale invece dell'opposto",
     "src/components/controlroom/PannelloBot.tsx",
     "comandi.cambiaUscite!(r.id, !uscite.automatiche)",
     "comandi.cambiaUscite!(r.id, Boolean(uscite.automatiche))",
     "src/components/controlroom/PannelloBotUscite.test.tsx"),
    ("F2 interruttori: il tennis non riallinea il cancelletto storico",
     "src/lib/interruttori.ts",
     "        if (i.strategia === 'tennis') out.tennis_exit_approval = !automatiche;",
     "",
     "src/lib/interruttoriUscite.test.ts"),
    ("F3 interruttori: Omega legge automatico da qualunque valore",
     "src/lib/interruttori.ts",
     "=== 'automatico' };",
     "!== 'x' };",
     "src/lib/interruttoriUscite.test.ts"),
    ("F4 PropostaUscitaMike: approva senza la chiave",
     "src/components/controlroom/PropostaUscitaMike.tsx",
     "mode: ev.mode, chiave: prop.chiave,",
     "mode: ev.mode,",
     "src/components/controlroom/PropostaUscitaMike.test.tsx"),
    ("F5 PropostaUscitaMike: bottone vivo col feed fermo",
     "src/components/controlroom/PropostaUscitaMike.tsx",
     "const spento = fresh.tone === 'stale' || fresh.tone === 'unknown' || inVolo;",
     "const spento = inVolo;",
     "src/components/controlroom/PropostaUscitaMike.test.tsx"),
]

sel = sys.argv[1:]
npx = "npx.cmd" if os.name == "nt" else "npx"
for nome, rel, prima, dopo, test in MUT:
    if sel and not any(nome.startswith(s) for s in sel):
        continue
    path = os.path.join(FE, rel)
    with open(path, encoding="utf-8", newline="") as f:
        orig = f.read()
    if orig.count(prima) != 1:
        print(f"{nome}: ANCORA NON TROVATA ({orig.count(prima)})")
        continue
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(orig.replace(prima, dopo))
        r = subprocess.run([npx, "vitest", "run", test], cwd=FE, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=900)
        righe = [l for l in r.stdout.splitlines() if "Tests" in l]
        print(f"{nome}: {'ROSSO' if r.returncode else 'VERDE (!)'} -> "
              f"{righe[-1].strip() if righe else r.stdout[-300:]}")
    finally:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(orig)
    with open(path, encoding="utf-8", newline="") as f:
        assert f.read() == orig, f"RIPRISTINO FALLITO: {rel}"
print("ripristino verificato byte per byte")
