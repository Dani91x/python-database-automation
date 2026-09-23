"""Falsificazione dei test "Omega legge lo scanner dal canale" (23/09/2026).

Ogni mutazione cambia UNA riga del codice VERO di ``omega_service.py`` e i test
di ``Betfair/omega/tests/test_omega_legge_canale_2026_09_23.py`` devono
diventare ROSSI. Il file sul disco NON viene mai toccato: il sorgente mutato
viene eseguito come modulo ``Betfair.omega.omega_service`` in un sottoprocesso
(prima di ogni import di Omega) e li' gira pytest. Controllo: senza mutazione
la stessa procedura deve dare VERDE. L'md5 del file si stampa prima e dopo.

    python -m Betfair.omega.tools.falsifica_canale_scan_2026_09_23
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import types
from pathlib import Path

RADICE = Path(__file__).resolve().parents[3]
FILE = RADICE / "Betfair" / "omega" / "omega_service.py"
TEST = "Betfair/omega/tests/test_omega_legge_canale_2026_09_23.py"
NOME = "Betfair.omega.omega_service"

# (sigla, descrizione, testo originale, testo mutato)
MUTAZIONI = [
    ("M1", "il canale AGGIUNGE una partita che il DB non ha",
     "    if not isinstance(dal_db, dict):\n        return dal_db, False\n",
     "    if not isinstance(dal_db, dict):\n        return dal_canale, dal_canale is not None\n"),
    ("M2", "la riga del canale vince SEMPRE (niente piu_recente/odds_ts_ms)",
     "    righe, dal_c = CS.fondi([dal_db], {str(event_id): dal_canale})\n",
     "    righe, dal_c = [dal_canale], 1\n"),
    ("M3", "l'interruttore non si guarda (client presente = acceso)",
     "    if not _SV.acceso(ENV_LEGGE_CANALE):\n        return None\n    from Betfair.safe_strategy",
     "    if False:\n        return None\n    from Betfair.safe_strategy"),
    ("M4", "soglia del canale muto 1 ora invece di MAX_ETA_CONTESTO_S",
     "righe_recenti(float(CS.MAX_ETA_CONTESTO_S))",
     "righe_recenti(3600.0)"),
    ("M5", "nessun riallineamento col DB ogni 10 s",
     "if dal_canale is not None and letto_a is not None and (ora - letto_a) < _RISINC_DB_S:",
     "if dal_canale is not None and letto_a is not None:"),
    ("M6", "il canale non toglie letture DB (si rilegge a ogni scadenza)",
     "if dal_canale is not None and letto_a is not None and (ora - letto_a) < _RISINC_DB_S:",
     "if False and dal_canale is not None:"),
    ("M7", "fonte sempre 'db' anche quando vince il canale",
     '    _conta_fonte_scan("canale" if dal_c else "db")\n',
     '    _conta_fonte_scan("db")\n'),
    ("M8", "fonte_scan scritta anche a interruttore spento",
     "    fonte = fonte_scan_del_giro()\n    if fonte is not None:\n",
     "    fonte = fonte_scan_del_giro() or 'db'\n    if fonte is not None:\n"),
    ("M9", "run_once non riazzera i conti della fonte",
     "    _ULTIMI_PARAMS = params\n    # 23/09: i conti della fonte del feed ripartono a ogni giro (vuoti e\n"
     "    # inutilizzati a interruttore ``OMEGA_LEGGE_CANALE`` spento).\n    _CACHE_FONTE_SCAN.clear()\n",
     "    _ULTIMI_PARAMS = params\n"),
    ("M10", "svuota_le_cache non svuota la memoria del canale",
     "            memoria.azzera()\n",
     "            pass\n"),
    ("M11", "tetto dei giri a 2 s (30/min) invece di 5 s",
     "GIRO_MINIMO_CANALE_S = 5.0\n",
     "GIRO_MINIMO_CANALE_S = 2.0\n"),
    ("M12", "il tetto dal .env puo' scendere sotto 5 s",
     "    return max(GIRO_MINIMO_CANALE_S, v)\n",
     "    return v\n"),
    ("M13", "ogni riga sveglia il ciclo, anche di partite non seguite",
     "evento=_SvegliaDalCanale(), interessa=_evento_seguito)",
     "evento=_SvegliaDalCanale(), interessa=lambda _e: True)"),
    ("M14", "la dormita ignora il client del canale (resta time.sleep)",
     "    if _ASCOLTO_SCAN is None and not _sveglia_dal_client_scan():\n",
     "    if _ASCOLTO_SCAN is None:\n"),
    ("M15", "la sveglia del client ignora l'interruttore",
     '    return _CLIENT_SCAN.get("client") is not None and _SV.acceso(ENV_LEGGE_CANALE)\n',
     '    return _CLIENT_SCAN.get("client") is not None\n'),
    ("M16", "AscoltoScan di F5 parte anche col client del canale (doppia connessione)",
     "    if not _SV.acceso(ENV_LEGGE_CANALE):\n        try:\n            ascolto = _SV.AscoltoScan(",
     "    if True:\n        try:\n            ascolto = _SV.AscoltoScan("),
    ("M17", "il client del canale non sveglia il ciclo (evento assente)",
     "evento=_SvegliaDalCanale(), interessa=_evento_seguito)",
     "evento=None, interessa=_evento_seguito)"),
    ("M18", "la riga del canale salta le guardie (hard_max_age ignorato)",
     "        if payload is not None and hard_max_age is not None:\n",
     "        if False:\n"),
]


def _md5() -> str:
    return hashlib.md5(FILE.read_bytes()).hexdigest()


def _figlio(sigla: str) -> int:
    """Nel sottoprocesso: installa il modulo (mutato o no) e lancia pytest."""
    import Betfair.omega
    import pytest

    sorgente = FILE.read_text(encoding="utf-8")
    if sigla != "M0":
        _, _, prima, dopo = next(m for m in MUTAZIONI if m[0] == sigla)
        if sorgente.count(prima) != 1:
            print("ANCORA NON UNICA/ASSENTE per", sigla, sorgente.count(prima))
            return 99
        sorgente = sorgente.replace(prima, dopo)
    mod = types.ModuleType(NOME)
    mod.__file__ = str(FILE)
    mod.__package__ = "Betfair.omega"
    sys.modules[NOME] = mod
    exec(compile(sorgente, str(FILE), "exec"), mod.__dict__)  # noqa: S102
    Betfair.omega.omega_service = mod
    return int(pytest.main([TEST, "-q", "-p", "no:cacheprovider", "-x", "--no-header"]))


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--figlio":
        return _figlio(sys.argv[2])
    md5_prima = _md5()
    print("md5 omega_service.py prima:", md5_prima)
    esiti = []
    for sigla, descr in [("M0", "CONTROLLO senza mutazione")] + [(m[0], m[1]) for m in MUTAZIONI]:
        rc = subprocess.run([sys.executable, "-m", "Betfair.omega.tools.falsifica_canale_scan_2026_09_23",
                             "--figlio", sigla], cwd=str(RADICE), capture_output=True,
                            text=True).returncode
        if sigla == "M0":
            esito = "VERDE" if rc == 0 else "ROSSO(!)"
        elif rc == 99:
            esito = "ANCORA NON TROVATA(!)"
        else:
            esito = "ROSSA" if rc != 0 else "VERDE(!) - il test non la vede"
        esiti.append((sigla, esito))
        print("%-4s %-28s %s" % (sigla, esito, descr))
    md5_dopo = _md5()
    print("md5 omega_service.py dopo: ", md5_dopo, "(invariato)" if md5_dopo == md5_prima else "(CAMBIATO!)")
    ok = esiti[0][1] == "VERDE" and all(e == "ROSSA" for _, e in esiti[1:]) and md5_dopo == md5_prima
    print("FALSIFICAZIONE:", "%d su %d ROSSE" % (sum(e == "ROSSA" for _, e in esiti[1:]), len(MUTAZIONI)),
          "- OK" if ok else "- NON OK")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
