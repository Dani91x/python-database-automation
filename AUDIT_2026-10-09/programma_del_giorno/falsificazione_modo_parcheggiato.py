"""Falsificazione della correzione "modo ordini da parcheggiato": ogni mutazione
rompe una regola nel codice NUOVO, si lanciano i test nuovi, deve uscire ROSSO;
poi si ripristina il sorgente (verificato identico)."""
import hashlib
import os
import subprocess
import sys

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CAL = "Betfair/stream/runner.py"
TEN = "Betfair/stream/tennis_live/tennis_runner.py"
TEST = "Betfair/stream/tests/test_modo_ordini_parcheggiato_2026_10_09.py"

MUTAZIONI = [
    ("M1 calcio: giro d'attesa senza rilettura dei settings", CAL,
     "    _attesa_impostazioni()\n    _board_da_parcheggiato(",
     "    _board_da_parcheggiato("),
    ("M2 calcio: orologio di cadenza diverso da quello del worker", CAL,
     '_LOW._throttled("settings_refresh", 1.0)', '_LOW._throttled("settings_attesa", 1.0)'),
    ("M3 calcio: nessuna cadenza (lettura a ogni giro)", CAL,
     '        if not _LOW._throttled("settings_refresh", 1.0):\n            _LOW._refresh_settings(sb)',
     '        _LOW._refresh_settings(sb)'),
    ("M4 calcio: nessun cancello sul tetto OFF", CAL,
     '        if _LOW._modo_processo() not in ("PAPER", "LIVE"):\n            return  # come il worker: OFF',
     '        if False:\n            return  # come il worker: OFF'),
    ("M5 calcio: eccezione che esce dal ciclo d'attesa", CAL,
     '        logger.warning("[runner] settings da parcheggiato KO: %s", str(ex)[:160])',
     '        raise'),
    ("M6 calcio: dichiarazione d'avvio non riprovata da parcheggiato", CAL,
     '            _dichiara_modo_ordini_all_avvio()  # come _live_order_worker_guardato',
     '            pass'),
    ("M7 calcio: dichiarazione d'avvio anche a guardia armata", CAL,
     '        if not _GUARDIA_AVVIO.blocca_aperture:\n            _dichiara_modo_ordini_all_avvio()',
     '        if True:\n            _dichiara_modo_ordini_all_avvio()'),
    ("M8 tennis: giro d'attesa senza rilettura dei settings", TEN,
     "    _attesa_impostazioni()\n    giro_da_parcheggiato(session, \"2\")",
     "    giro_da_parcheggiato(session, \"2\")"),
    ("M9 tennis: settings riletti DOPO i comandi (decisione col valore vecchio)", TEN,
     "    _attesa_impostazioni()\n    giro_da_parcheggiato(session, \"2\")\n    servi_comandi_da_parcheggiato(session)",
     "    giro_da_parcheggiato(session, \"2\")\n    servi_comandi_da_parcheggiato(session)\n    _attesa_impostazioni()"),
    ("M10 tennis: orologio scavalcato (forza=True)", TEN,
     "_gt.aggiorna_impostazioni(tennis_db.get_tennis_client())",
     "_gt.aggiorna_impostazioni(tennis_db.get_tennis_client(), forza=True)"),
    ("M11 tennis: nessun cancello sul tetto OFF", TEN,
     '        if _runner_mode() not in ("PAPER", "LIVE"):\n            return  # come il worker: OFF',
     '        if False:\n            return  # come il worker: OFF'),
    ("M12 tennis: eccezione che esce dal ciclo d'attesa", TEN,
     '        logger.warning("[tennis-runner] impostazioni da parcheggiato KO: %s", str(e)[:160])',
     '        raise'),
    ("M13 tennis: lettura con la funzione del calcio (pubblica solo sul 47331)", TEN,
     "        _gt.aggiorna_impostazioni(tennis_db.get_tennis_client())",
     "        from .. import live_order_worker as _L\n        _L._refresh_settings(tennis_db.get_tennis_client())"),
]


def _h(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    os.chdir(RADICE)
    esiti = []
    for nome, f, prima, dopo in MUTAZIONI:
        orig = open(f, encoding="utf-8").read()
        h0 = _h(f)
        n = orig.count(prima)
        if n != 1:
            print(f"{nome}: ancora trovata {n} volte -> mutazione NON applicabile")
            esiti.append((nome, "NON APPLICATA"))
            continue
        try:
            open(f, "w", encoding="utf-8").write(orig.replace(prima, dopo))
            r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "-p",
                                "no:cacheprovider"], capture_output=True, text=True)
            righe = [x for x in r.stdout.splitlines() if x.startswith("FAILED")]
            fine = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
            rosso = r.returncode != 0
            esiti.append((nome, "ROSSO" if rosso else "VERDE (!)"))
            print(f"{nome}: {'ROSSO' if rosso else 'VERDE (!)'} - {fine}")
            for x in righe:
                print("    " + x.split("::", 1)[1].split(" - ")[0])
        finally:
            open(f, "w", encoding="utf-8").write(orig)
            assert _h(f) == h0, f"sorgente {f} non ripristinato"
    rossi = sum(1 for _n, e in esiti if e == "ROSSO")
    print(f"\n{rossi}/{len(esiti)} mutazioni ROSSE; sorgenti ripristinati identici")
    return 0 if rossi == len(esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
