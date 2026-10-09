"""Falsificazione a livello di banco (test cert per tick). Uso: python mutazioni_cert.py <radice>"""
import hashlib
import os
import subprocess
import sys

R = sys.argv[1]
B = "Betfair/nucleo/stato_partita/"
NODO = B + "tests/test_b_parita_banco.py::test_parita_per_tick_sullo_scanner_vero[%s]"
MUT = [
    ("cert: ritardo IPS tolto", B + "freschezza.py",
     "    return None if eta is None else eta + ritardo_ips_s()",
     "    return None if eta is None else eta", "35760084"),
    ("cert: stato dello scanner ignorato nel flusso", B + "servizio.py",
     '                          let.get("stato_scanner"), event_id, mercati, adesso_ms)',
     '                          None, event_id, mercati, adesso_ms)', "35797769"),
    ("cert: minuto della riga ricalcolato dallo score_raw", B + "calcolo.py",
     '    minuto = _intero_o_none(payload.get("minute"))',
     '    minuto = _intero_o_none((payload.get("score_raw") or {}).get("timeElapsed"))', "35760084"),
]


def sha(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


for nome, rel, vecchio, nuovo, ev in MUT:
    path = os.path.join(R, rel)
    prima = sha(path)
    with open(path, "rb") as fh:
        orig = fh.read()
    t = orig.decode()
    assert t.count(vecchio) == 1, nome
    with open(path, "wb") as fh:
        fh.write(t.replace(vecchio, nuovo).encode())
    try:
        res = subprocess.run([sys.executable, "-m", "pytest", NODO % ev, "-q", "-p", "no:cacheprovider"],
                             cwd=R, capture_output=True, text=True, timeout=900)
    finally:
        with open(path, "wb") as fh:
            fh.write(orig)
    ultima = (res.stdout.strip().splitlines() or ["?"])[-1]
    print(f"{'ROSSO' if res.returncode else 'VERDE!'}  {nome} [{ev}] [{ultima}] sha256 {'uguale' if sha(path) == prima else 'DIVERSO'}")
