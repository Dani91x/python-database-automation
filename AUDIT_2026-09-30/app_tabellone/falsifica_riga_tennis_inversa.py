# Falsificazione (30/09): toglie da residuoTennisSulBook il controllo sugli
# stati terminali e lancia i test della vista: devono diventare ROSSI i test
# Â«non compareÂ». Ripristino dal testo salvato in memoria, sempre (finally).
import pathlib, subprocess

P = pathlib.Path("frontend/src/lib/controlRoom.ts")
orig = P.read_bytes()
RIGA = b"    if (TERMINALI_FLUMINE.has(String(o.status ?? '').toUpperCase())) return false;\n"
testo = orig.replace(b"\r\n", b"\n")
assert RIGA in testo, "punto di mutazione non trovato"
try:
    P.write_bytes(testo.replace(RIGA, b"    void TERMINALI_FLUMINE; return false;\n"))
    r = subprocess.run("npx vitest run src/components/controlroom/useControlRoom.test.tsx -t 30/09",
                       cwd="frontend", shell=True, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    righe = [x for x in r.stdout.splitlines() if ("FAIL" in x or "Tests" in x or "Ã—" in x)]
    print("\n".join(righe[-20:]))
finally:
    P.write_bytes(orig)
print("ripristinato:", P.read_bytes() == orig)

