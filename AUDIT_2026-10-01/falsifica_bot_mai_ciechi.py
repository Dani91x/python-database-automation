"""Falsificazione delle correzioni «bot mai ciechi» (01/10/2026).

Per ogni mutazione: rimette il comportamento VECCHIO (o rompe la correzione),
lancia i test, stampa i rossi, RIPRISTINA il file byte per byte (finally). Uso:
    .venv/Scripts/python.exe AUDIT_2026-10-01/falsifica_bot_mai_ciechi.py [test ...]
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SC = ROOT / "Betfair/safe_strategy/scanner.py"
SV = ROOT / "Betfair/safe_strategy/service.py"
TESTS = sys.argv[1:] or ["Betfair/safe_strategy/tests/test_attesa_fischio_2026_10_01.py"]
MUT = [
    ("F1 is_monitorable senza attesa del fischio (comportamento vecchio)", SC,
     "        or (bool(visto) and in_post_ko_wait(inplay, mo_status, open_date, now, esposto))\n", ""),
    ("F2 build_rows ignora l'esposizione", SV,
     "esposto=str(eid) in esposti,", "esposto=False,"),
    ("F3 linee Mike fuori dallo stream durante l'attesa", SV,
     "            if not scanner.in_post_ko_wait(ev.get(\"inplay\"), ev.get(\"mo_status\"),\n"
     "                                           meta.get(\"open_date\"), adesso, esposto=True):\n"
     "                continue",
     "            continue"),
    ("F4 pre-KO seguita al tier 2", SV,
     "mike=str(eid) in followed)", "mike=False)"),
    ("F5 attesa che ignora CLOSED", SC,
     "    if inplay or mo_status == \"CLOSED\":\n        return False\n    ko = parse_iso(open_date)\n"
     "    if ko is None:\n        return False\n    passati",
     "    if inplay:\n        return False\n    ko = parse_iso(open_date)\n"
     "    if ko is None:\n        return False\n    passati"),
    ("F6 tetto ignorato (tutte per sempre)", SC,
     "return bool(esposto) or passati <= POST_KO_WAIT_SEC", "return True"),
]
EXTRA = pathlib.Path(__file__).with_name("falsifica_bot_mai_ciechi_extra.py")
if EXTRA.exists():
    ns = {"ROOT": ROOT}
    exec(EXTRA.read_text(encoding="utf-8"), ns)
    MUT = ns.get("MUT_OVERRIDE", MUT) + ns.get("MUT_EXTRA", [])

CRLF = "\r\n"
for nome, f, a, b in MUT:
    orig = f.read_bytes().decode("utf-8")
    if CRLF in orig:
        a, b = a.replace("\n", CRLF), b.replace("\n", CRLF)
    assert orig.count(a) == 1, (nome, orig.count(a))
    try:
        f.write_bytes(orig.replace(a, b).encode("utf-8"))
        r = subprocess.run([str(ROOT / ".venv/Scripts/python.exe"), "-m", "pytest", *TESTS,
                            "-q", "-p", "no:cacheprovider"],
                           cwd=ROOT, capture_output=True, text=True)
        falliti = [ln for ln in r.stdout.splitlines() if ln.startswith("FAILED")]
        print(f"== {nome}: exit={r.returncode} -> {r.stdout.strip().splitlines()[-1]}")
        for ln in falliti:
            print("   ", ln.split(" - ")[0])
    finally:
        f.write_bytes(orig.encode("utf-8"))
print("ripristinato")
