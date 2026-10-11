"""Falsificazione dei test M-1 (registratore ordini): ogni mutazione DEVE far
diventare rosso il test indicato; dopo ogni mutazione il file torna con sha256
identico (controllato qui e stampato).

Uso (dalla radice del repo):  python ARCHITETTURA_2026-10/mappa/m1_mutazioni.py [radice]
Esce con 0 solo se TUTTE le mutazioni sono rosse e tutti i ripristini identici.
Prima e dopo: ``git status`` pulito sui file elencati.
"""
import hashlib
import os
import subprocess
import sys

RADICE = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
T = "Betfair/monitor/tests/test_registratore_ordini_2026_10_11.py"
RO = "Betfair/monitor/registratore_ordini.py"
AO = "Betfair/monitor/analisi_ordini.py"

MUT = [
    ("M1 aggancio auth tolto", "Betfair/stream/auth.py",
     "    if _ro.attivo(): _ro.aggancia_api_client(client)", "    if False: _ro.aggancia_api_client(client)",
     "test_acceso_rest_bflw_registra or test_acceso_stream_ordini_flumine"),
    ("M2 aggancio client nostro tolto", "Betfair/client.py",
     "        if _ro.attivo() and _ro.metodo_soldi(method):", "        if False and _ro.metodo_soldi(method):",
     "test_acceso_rest_nostro_registra"),
    ("M3 aggancio tempi_ordine tolto", "Betfair/stream/tempi_ordine.py",
     "        if _ro.attivo(): _ro.decisione(order, voce)", "        if False: _ro.decisione(order, voce)",
     "test_acceso_decisione"),
    ("M4 interruttore acceso di serie", RO,
     'return (os.environ.get(ENV) or "0").strip() == "1"', 'return (os.environ.get(ENV) or "1").strip() != "0"',
     "test_spento"),
    ("M5 metti_record propaga", RO,
     '            _avvisa("metti_record", "record %s non accodato: %s", rec.get("k"), str(ex)[:160])',
     '            raise',
     "test_metti_non_solleva_mai"),
    ("M6 metti_stream propaga", RO,
     '            _avvisa("metti_stream", "riga dello stream non accodata: %s", str(ex)[:160])',
     '            raise',
     "test_metti_non_solleva_mai"),
    ("M7 orologio non protetto", RO,
     "    try:\n        return adesso_us()\n    except Exception as ex:  # noqa: BLE001\n        _avvisa(\"orologio\"",
     "    try:\n        return adesso_us()\n    except ZeroDivisionError as ex:  # noqa: BLE001\n        _avvisa(\"orologio\"",
     "test_eccezioni_del_registratore"),
    ("M8 potatura spenta", RO,
     "        self._ultima_potatura = time.monotonic()\n        try:\n            base = self.cartella()",
     "        self._ultima_potatura = time.monotonic()\n        return\n        try:\n            base = self.cartella()",
     "test_tetto"),
    ("M9 pulizia dei segreti tolta", RO,
     '                riga = riga.replace(s, "***")', '                pass',
     "test_acceso_rest_bflw_registra"),
    ("M10 tee anche sugli stream dei prezzi", RO,
     "        stream = originale(*args, **kwargs)\n        try:\n",
     "        stream = originale(*args, **kwargs)\n        _monta_tee(stream, {}, ())\n        try:\n",
     "test_acceso_stream_dei_prezzi"),
    ("M11 coda senza tetto", RO,
     "        if len(self._coda) >= CODA_MAX:", "        if False:",
     "test_coda_piena"),
    ("M12 niente rotazione", RO,
     "        if self._fh is None or giorno != self._giorno:", "        if self._fh is None:",
     "test_rotazione"),
    ("M13 pytest non spegne", RO,
     'return "PYTEST_CURRENT_TEST" in os.environ and not _consenti_in_test', "return False",
     "test_acceso_ma_banco_o_pytest"),
    ("M14 ocm-prima-della-risposta col segno sbagliato", AO,
     "                if dr < 0:", "                if dr > 0:",
     "test_analisi_giornata"),
    ("M15 ordini con riferimenti presi per sito", AO,
     "            if not o.rfo and not o.rfs:", "            if True:",
     "test_analisi_giornata"),
    ("M16 copie fra processi non riconosciute", AO,
     "                    if chiave in o.chiavi_viste:", "                    if False:",
     "test_analisi_giornata"),
    ("M17 silenzi non visti", AO,
     "                if prec is not None and ep - prec > soglia_us:", "                if False:",
     "test_analisi_giornata"),
    ("M18 file senza chiusura detto pulito", AO,
     '"fine_pulita": bool(ch),', '"fine_pulita": True,',
     "test_analisi_giornata"),
    ("M19 gzip tronco non tollerato", AO,
     "        except zlib.error:\n            troncato = True\n            break\n        if not d.eof:\n            troncato = True",
     "        except zlib.error:\n            troncato = True\n            break\n        if not d.eof:\n            raise EOFError('tronco')",
     "test_analisi_righe_perse"),
    ("M20 tee senza on_data originale (stream rotto)", RO,
     "            return originale(raw_data)\n", "            return None\n",
     "test_acceso_stream_esiti_identici or test_acceso_stream_ordini_flumine"),
    ("M21 tee dello stream senza protezione", RO,
     '                _avvisa("tee", "tee dello stream ordini KO: %s", str(ex)[:160])',
     '                raise',
     "test_eccezioni_del_registratore"),
    ("M22 registra_rest senza protezione", RO,
     '        _avvisa("rest", "chiamata %s non registrata: %s", method, str(ex)[:160])',
     '        raise',
     "test_eccezioni_del_registratore or test_metti_non_solleva_mai"),
    ("M23 sottoscrizione senza protezione", RO,
     '                        _avvisa("sub", "tee dello stream ordini non montato: %s", str(ex)[:160])',
     '                        raise',
     "test_eccezioni_del_registratore"),
    ("M24 decisione senza protezione", RO,
     '        _avvisa("decisione", "decisione non registrata: %s", str(ex)[:160])',
     '        raise',
     "test_metti_non_solleva_mai"),
    ("M25 potatura del file vivo di un altro processo", RO,
     "                    if mt > recente:", "                    if False:",
     "test_tetto_non_pota"),
]


def sha(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


esito = 0
for nome, rel, vecchio, nuovo, sel in MUT:
    p = RADICE + "/" + rel
    with open(p, "rb") as fh:
        orig = fh.read()
    h0 = hashlib.sha256(orig).hexdigest()
    testo = orig.decode("utf-8")
    if testo.count(vecchio) != 1:
        print("%-48s ERRORE: testo da mutare trovato %d volte" % (nome, testo.count(vecchio)))
        esito = 1
        continue
    try:
        with open(p, "wb") as fh:
            fh.write(testo.replace(vecchio, nuovo).encode("utf-8"))
        r = subprocess.run([sys.executable, "-m", "pytest", T, "-q", "-p", "no:cacheprovider",
                            "-k", sel], cwd=RADICE, capture_output=True, text=True, timeout=600)
        ultima = [x for x in r.stdout.strip().splitlines() if x.strip()][-1]
        rosso = r.returncode != 0
    finally:
        with open(p, "wb") as fh:
            fh.write(orig)
    h1 = sha(p)
    print("%-48s %s  [%s]  ripristino sha256 %s" % (
        nome, "ROSSO" if rosso else "VERDE (!!)", ultima[:70], "identico" if h0 == h1 else "DIVERSO"))
    if not rosso or h0 != h1:
        esito = 1
sys.exit(esito)
