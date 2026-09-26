"""Falsificazione dei fix MOTORE ORDINI via canale (26/09). Uso (dalla radice del repo):
    python AUDIT_2026-09-26/falsifica_motore_canale.py
Ogni mutazione rimette il bug, lancia i test nuovi, ripristina e verifica con sha256.
NON interrompere: il ripristino avviene nel finally di ogni mutazione."""
import hashlib
import os
import subprocess
import sys

T = "Betfair/stream/tests/test_motore_ordini_riavvio2_2026_09_26.py"
MUT = [
    ("M1 lato grezzo", "Betfair/stream/motore_ordini.py",
     'riga["side"] = lato.lower()', 'riga["side"] = lato'),
    ("M2 niente source", "Betfair/stream/db.py",
     "riga_db = dict(payload, source=src) if src else payload", "riga_db = payload"),
    ("M3 runner fermo rifiuta", "Betfair/stream/motore_ordini.py",
     'piano["attende_runner"] = True\n                    return',
     'dettaglio += ": aggancio richiesto"'),
    ("M4 rid da 9000000000", "Betfair/stream/live_order_worker.py",
     "    return ms * 1000\n\n\n_LOCAL_RID", "    return 9_000_000_000\n\n\n_LOCAL_RID"),
    ("M5 seq globale", "Betfair/stream/motore_ordini.py",
     "s = self._seq.get(attore, self._base_seq) + 1\n            self._seq[attore] = s",
     "s = self._seq.get('*', self._base_seq) + 1\n            self._seq['*'] = s"),
    ("M6 fase parziale", "Betfair/stream/motore_ordini.py",
     "if size > 0 and sm >= size - 1e-9:", "if False:"),
    ("M7 nessun ripiego source", "Betfair/stream/db.py",
     'if "source" not in riga or _VINCOLO_SOURCE not in str(ex):', "if True:"),
    ("M8 journal grezzo", "Betfair/stream/live_order_worker.py",
     '"side": (request_row.get("side").lower()', '"side": (request_row.get("side")'),
    ("M9 tennis manual fisso", "Betfair/stream/tennis_live/tennis_live_order_worker.py",
     '"source": str(attore) if attore and attore != "desktop" else "manual",',
     '"source": "manual",'),
    ("M10 aggancio 3000", "Betfair/stream/motore_ordini.py",
     "AGGANCIO_MAX_MS_DEFAULT = 10000", "AGGANCIO_MAX_MS_DEFAULT = 3000"),
    ("M11 riduzione case-sensitive", "Betfair/stream/motore_ordini.py",
     'if str(side).upper() == "BACK":', 'if side == "BACK":'),
    ("M12 source anche al desktop", "Betfair/stream/motore_ordini.py",
     'return None if attore == "desktop" else attore', "return attore"),
]
env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x",
           SUPABASE_KEY="x")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


esito = 0
for nome, f, vecchio, nuovo in MUT:
    orig = open(f, "rb").read()
    h0 = sha(f)
    testo = orig.decode("utf-8")
    crlf = "\r\n" in testo
    v, n = (vecchio.replace("\n", "\r\n"), nuovo.replace("\n", "\r\n")) if crlf else (vecchio, nuovo)
    if testo.count(v) != 1:
        print(f"{nome}: ANCORA NON TROVATA ({testo.count(v)})")
        esito = 1
        continue
    try:
        open(f, "wb").write(testo.replace(v, n).encode("utf-8"))
        r = subprocess.run([sys.executable, "-m", "pytest", T, "-q", "-p", "no:cacheprovider",
                            "--no-header"], capture_output=True, text=True, env=env)
        ultima = (r.stdout.strip().splitlines() or ["?"])[-1]
        rosso = r.returncode != 0
        print(f"{nome}: {'ROSSO' if rosso else 'VERDE (!)'} -> {ultima}")
        if not rosso:
            esito = 1
    finally:
        open(f, "wb").write(orig)
        assert sha(f) == h0, f"RIPRISTINO FALLITO {f}"
print("tutti i file ripristinati (sha256 identico)")
sys.exit(esito)
