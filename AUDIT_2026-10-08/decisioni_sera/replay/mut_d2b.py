"""Mutazioni D-2b (tetto del replace in volo) e D-2a (RC3 del banco): ogni
mutazione si applica, si lanciano i test nuovi, si ripristina dalla copia e si
verifica lo sha256."""
import hashlib
import os
import shutil
import subprocess

WT = r"C:\Users\Admin\Desktop\PYTHON DATABASE\wt-d2"
PY = os.path.join(WT, ".venv", "Scripts", "python.exe")
TEST = "Betfair/stream/tests/test_submin_rimpiazzo_non_nato_2026_10_08.py"
SM = os.path.join(WT, "Betfair", "stream", "trading", "submin.py")
LOW = os.path.join(WT, "Betfair", "stream", "live_order_worker.py")
SR = os.path.join(WT, "Betfair", "stream", "backtest", "scavalco_rifiuti.py")
CRLF = b"\r\n"


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


MUT = [
    ("B1 nessun tetto all'attesa in volo", SM,
     b"_REPLACE_IN_VOLO_TIMEOUT_MS = 15_000", b"_REPLACE_IN_VOLO_TIMEOUT_MS = 10 ** 12"),
    ("B2 tetto 20 s invece di 15 s", SM,
     b"_REPLACE_IN_VOLO_TIMEOUT_MS = 15_000", b"_REPLACE_IN_VOLO_TIMEOUT_MS = 20_000"),
    ("B3 abort subito col replace in volo (attesa spenta)", SM,
     b"                    if in_volo < _REPLACE_IN_VOLO_TIMEOUT_MS:", b"                    if False:"),
    ("B4 prima osservazione non registrata", SM,
     b"                    if state.replace_in_volo_ms <= 0:", b"                    if False:"),
    ("B5 ordine in volo non ritirato allo scadere", SM,
     b"vivo = _is_executable(o) or _status_name(o) in _STATI_IN_VOLO",
     b"vivo = _is_executable(o)"),
    ("B6 errore del cancel non assorbito (abort perso)", SM,
     b"except Exception:  # noqa: BLE001 - best effort, l'abort resta",
     b"except ZeroDivisionError:  # noqa: BLE001 - best effort"),
    ("B7 worker: inizio dell'attesa NON persistito", LOW,
     b'        "replace_in_volo_ms": int(getattr(state, "replace_in_volo_ms", 0) or 0),' + CRLF, b""),
    ("B8 worker: inizio dell'attesa NON riletto", LOW,
     b'        replace_in_volo_ms=int(d.get("replace_in_volo_ms") or 0),' + CRLF, b""),
    ("A1 RC3: la riga del replace vale anche per place/cancel", SR,
     b'                if rec.get("operazione") == "replaceOrders":', b'                if True:'),
    ("A2 RC3: la riga del replace non vale (solo il codice)", SR,
     b'                    ammessi.append(NOTA_RIMPIAZZO_NON_NATO)', b'                    pass'),
]

righe = []
for nome, path, a, b in MUT:
    orig = open(path, "rb").read()
    h0 = sha(path)
    bak = path + ".bak_mut"
    shutil.copyfile(path, bak)
    try:
        assert orig.count(a) == 1, (nome, orig.count(a))
        open(path, "wb").write(orig.replace(a, b))
        r = subprocess.run([PY, "-m", "pytest", TEST, "-q", "-p", "no:cacheprovider", "--no-header"],
                           cwd=WT, capture_output=True, text=True)
        ult = [l for l in r.stdout.splitlines() if l.strip()][-1]
        rossi = [l.split(" ")[1] for l in r.stdout.splitlines() if l.startswith("FAILED")]
    finally:
        shutil.copyfile(bak, path)
        os.remove(bak)
    h1 = sha(path)
    righe.append("%s | %s | ripristino %s (%s)" % (nome, ult, "IDENTICO" if h0 == h1 else "DIVERSO!", h1[:16]))
    righe.append("    rossi: " + ", ".join(x.split("::")[-1] for x in rossi))
print("\n".join(righe))
