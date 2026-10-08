"""Falsificazione dei test del cantiere 7: ogni mutazione reintroduce un difetto,
i test devono diventare ROSSI; poi ripristino con verifica dello sha.
Uso (dalla radice del worktree): python3 falsifica.py
"""
import hashlib
import os
import shutil
import subprocess
import sys

BANCO = "Betfair/stream/backtest/banco_comune.py"
OMEGA = "Betfair/omega/tools/replay_registrazioni.py"
TEST_B = "Betfair/stream/tests/test_banco_scanner_reperti_rb_2026_10_08.py"
TEST_O = "Betfair/omega/tests/test_banco_omega_reperti_rb_2026_10_08.py"
SCRATCH = os.path.dirname(os.path.abspath(__file__))

MUTAZIONI = [
    ("M1 RB-1: il CLOSED torna sotto la conflazione", BANCO,
     "            if (not terminale\n                    and adesso_ms",
     "            if (True  # MUTAZIONE\n                    and adesso_ms"),
    ("M2 RB-1: il CLOSED consegnato a ogni riga (nessuna consegna unica)", BANCO,
     "        if terminale and self._ultimo_stato.get(mid) == STATO_TERMINALE:",
     "        if False:  # MUTAZIONE"),
    ("M3 RB-1: Omega non passa la chiusura allo scanner", OMEGA,
     "            if not self.banco.registra_mercato(market_book):\n                return\n            pt = getattr",
     "            return  # MUTAZIONE\n            pt = getattr"),
    ("M4 RB-2: finestre ignorate (ogni mercato sottoscritto)", BANCO,
     "        if not self.finestre_di_produzione:\n            return True\n        if self._voluti_ora",
     "        if True:  # MUTAZIONE\n            return True\n        if self._voluti_ora"),
    ("M5 RB-2: esposizioni dei bot non dette allo scanner", BANCO,
     "        if self.fonte_esposizioni is not None and (",
     "        if False and (  # MUTAZIONE"),
    ("M6 RB-2: la registrazione conferma anche i mercati non sottoscritti", BANCO,
     "                                   and self.sottoscritto(m)])",
     "                                   ])  # MUTAZIONE"),
    ("M7 RB-2: voluti rifatti a ogni book (cadenza falsa)", BANCO,
     "self._ora_s - self._voluti_ora >= GIRO_SCANNER_S:",
     "self._ora_s - self._voluti_ora >= 0.0:  # MUTAZIONE"),
    ("M8 RB-3: nessun aggancio dell'orologio del flusso", OMEGA,
     "        FP._ora_ms = (lambda: int(float(self.banco.ora) * 1000))  # type: ignore[assignment]",
     "        pass  # MUTAZIONE"),
    ("M9 RB-4: il paper senza porta del runner", OMEGA,
     "    if mode != \"paper\" or TRA.attivo() is not None:",
     "    if True:  # MUTAZIONE"),
    ("M10 RB-5: elenco delle tabelle storiche vuoto", OMEGA,
     "CACHE_TABELLE_STORICHE = (\"_EMPIRICAL_CACHE\", \"_MINUTE_CACHE\")",
     "CACHE_TABELLE_STORICHE = ()  # MUTAZIONE"),
    ("M11 RB-5: AmbienteOmega non azzera le cache all'ingresso", OMEGA,
     "        S.svuota_le_cache()\n        _azzera_cache_di_processo()               # 08/10 (RB-5)\n        return self",
     "        S.svuota_le_cache()\n        return self  # MUTAZIONE"),
    ("M14 RB-5: _LEG_RETRY fuori dall'elenco del banco", OMEGA,
     "    \"_LEG_RETRY\", \"_SKIP_SEEN\", \"_BLIND_CYCLES\"",
     "    \"_SKIP_SEEN\", \"_BLIND_CYCLES\"  # MUTAZIONE"),
    ("M15 RB-5: AmbienteOmega azzera solo con svuota_le_cache (il banco di partenza)", OMEGA,
     "def _azzera_cache_di_processo() -> List[str]:\n    \"\"\"",
     "def _azzera_cache_di_processo() -> List[str]:\n    return []  # MUTAZIONE\n    \"\"\""),
    ("M12 RB-2: esposizioni di Omega con righe regolate", OMEGA,
     "            if str(r.get(\"status\") or \"\") in SDB._STATI_TRADE_ESPOSTI]",
     "            if True]  # MUTAZIONE"),
    ("M13 RB-2: banco di Omega a finestre spente", OMEGA,
     "FINESTRE_DI_PRODUZIONE = True",
     "FINESTRE_DI_PRODUZIONE = False  # MUTAZIONE"),
]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def pytest_rossi():
    r = subprocess.run([sys.executable, "-m", "pytest", TEST_B, TEST_O, "-q",
                        "-p", "no:cacheprovider"], capture_output=True, text=True,
                       timeout=900)
    ultima = [x for x in r.stdout.strip().splitlines() if x.strip()][-1]
    falliti = [x.split("::")[-1].split(" ")[0] for x in r.stdout.splitlines()
               if x.startswith("FAILED")]
    return ultima, falliti


orig = {p: sha(p) for p in (BANCO, OMEGA)}
copie = {}
for p in orig:
    dst = os.path.join(SCRATCH, os.path.basename(p) + ".orig")
    shutil.copyfile(p, dst)
    copie[p] = dst
print("sha di partenza:", {p: h[:16] for p, h in orig.items()})
print("verde di partenza:", pytest_rossi()[0])
for nome, p, vecchio, nuovo in MUTAZIONI:
    s = open(p).read()
    assert s.count(vecchio) == 1, (nome, s.count(vecchio))
    open(p, "w").write(s.replace(vecchio, nuovo))
    try:
        ultima, falliti = pytest_rossi()
    finally:
        shutil.copyfile(copie[p], p)
    assert sha(p) == orig[p], "RIPRISTINO FALLITO " + p
    print(f"{nome}: {ultima}")
    for f in falliti:
        print("      rosso:", f)
print("sha finali:", {p: sha(p)[:16] for p in orig}, "identici:",
      all(sha(p) == h for p, h in orig.items()))
print("MUTAZIONE residue:", sum(open(p).read().count("MUTAZIONE") for p in orig))
print("verde finale:", pytest_rossi()[0])
