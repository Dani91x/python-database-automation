# Falsificazione del coordinatore lato Python: mutazione, pytest dei due file, ripristino con sha.
import hashlib, io, os, subprocess
R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
OUT = os.path.join(R, "ARCHITETTURA_2026-10", "AUDIT_MATEMATICA_ML", "lavori", "fase2", "suite", "falsifica_py_coord.txt")
W = os.path.join(R, "Betfair", "stream", "live_order_worker.py")
D = os.path.join(R, "Betfair", "stream", "trading", "dutching.py")
CMD = [os.path.join(R, ".venv", "Scripts", "python.exe"), "-m", "pytest", "Betfair/stream/tests/test_dutching.py",
       "Betfair/stream/tests/test_live_order_dutch_cashout.py", "-q", "-p", "no:cacheprovider"]
MUT = [
    ("P1 worker senza il rifiuto variable+lay", W,
     'if side == "lay":\n            raise ValueError("dutch mode=variable: supportato solo per back")', 'if False:\n            raise ValueError("dutch mode=variable: supportato solo per back")'),
    ("P2 rifiuto variable+lay spostato DOPO il calcolo dei prezzi", W,
     '        if side == "lay":\n            raise ValueError("dutch mode=variable: supportato solo per back")\n        triples = [\n            (int(s["selection_id"]), _price_or_raise(s), _f(s.get("weight")) or 1.0)\n            for s in sels_in\n        ]',
     '        triples = [\n            (int(s["selection_id"]), _price_or_raise(s), _f(s.get("weight")) or 1.0)\n            for s in sels_in\n        ]\n        if side == "lay":\n            raise ValueError("dutch mode=variable: supportato solo per back")'),
    ("P3 dutch_variable senza arrotondamento dello stake", D,
     "s = round((total_stake + k * w) / p, 2)", "s = (total_stake + k * w) / p"),
    ("P4 dutch_variable con profitto proporzionale allo stake (formula UI vecchia)", D,
     "k = total_stake * (1.0 - inv_sum) / wp_sum", "k = 0.0"),
]
log = []
for name, f, a, b in MUT:
    orig = io.open(f, encoding="utf-8", newline="").read()
    h0 = hashlib.sha256(orig.encode("utf-8")).hexdigest()
    nl = "\r\n" if "\r\n" in orig else "\n"
    a2, b2 = a.replace("\n", nl), b.replace("\n", nl)
    if orig.count(a2) != 1:
        log.append(f"{name}: SALTATA (occorrenze={orig.count(a2)})"); continue
    try:
        io.open(f, "w", encoding="utf-8", newline="").write(orig.replace(a2, b2, 1))
        p = subprocess.run(CMD, cwd=R, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        last = (p.stdout.strip().splitlines() or [""])[-1]
        log.append(f"{name}: exit={p.returncode} | {last}")
    finally:
        io.open(f, "w", encoding="utf-8", newline="").write(orig)
    ok = hashlib.sha256(open(f, "rb").read()).hexdigest() == h0
    log.append(f"   ripristino {os.path.basename(f)} sha uguale: {ok}")
p = subprocess.run(CMD, cwd=R, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
log.append("dopo il ripristino: " + (p.stdout.strip().splitlines() or [""])[-1])
io.open(OUT, "w", encoding="utf-8").write("\n".join(log) + "\n")
