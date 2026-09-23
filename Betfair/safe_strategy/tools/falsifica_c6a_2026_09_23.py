"""Falsificazione di C6 a (giro veloce): un test che non sa diventare rosso
non certifica.

Per ogni mutazione: md5 del file PRIMA, mutazione sul codice VERO, pytest sul
test indicato (deve fallire), ripristino, md5 DOPO. Se un md5 non torna, lo
strumento si ferma: meglio nessun risultato che un file lasciato mutato.
Stesso schema di ``falsifica_f4_2026_09_18.py``.

Uso (dalla radice del repo, nel worktree):
    .venv/Scripts/python.exe -m Betfair.safe_strategy.tools.falsifica_c6a_2026_09_23

Nessuna rete, nessun database, nessun processo dell'app.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

RADICE = Path(__file__).resolve().parents[3]
BOT = RADICE / "Betfair" / "safe_strategy" / "bot_service.py"
TEST = "Betfair/safe_strategy/tests/test_giro_veloce_c6a_2026_09_23.py"

#: (nome, testo_da_cercare, testo_mutato, test_che_deve_diventare_rosso)
MUTAZIONI: List[Tuple[str, str, str, str]] = [
    ("M1 niente contratto di eta' (contesto oltre 5 s usato)",
     "    if eta < 0.0 or eta > float(CS.MAX_ETA_CONTESTO_S):",
     "    if eta < 0.0:",
     "test_contesto_oltre_5_secondi_non_anticipa"),
    ("M2 una novita' anticipa a ogni giro (niente firma)",
     "        nuove = [f for f in nuove if f not in _CORSIA[\"firme\"]]",
     "        nuove = list(nuove)",
     "test_una_novita_anticipa_una_volta_sola"),
    ("M3 nessun tetto agli anticipi al minuto",
     "        if len(recenti) >= int(_ANTICIPI_MAX_AL_MIN):",
     "        if False:",
     "test_tetto_degli_anticipi_al_minuto"),
    ("M4 nessun tetto ai giri veloci al secondo",
     "        if 0.0 <= ora - float(_CORSIA[\"ultimo_mono\"] or 0.0) < passo \\\n"
     "                and _CORSIA[\"ultimo_mono\"]:",
     "        if False:",
     "test_tetto_dei_giri_veloci_al_secondo"),
    ("M5 nessuna coalescenza (la sveglia non si consuma)",
     "        _PREZZO_NUOVO.clear()\n    return run_giro_veloce(now=now)",
     "    return run_giro_veloce(now=now)",
     "test_coalescenza_n_sveglie_un_giro"),
    ("M6 fotografia di un ciclo degradato presa per buona",
     "        utilizzabile = not degradato and not ctx.get(\"unavailable\")",
     "        utilizzabile = True",
     "test_ciclo_degradato_il_veloce_rimanda"),
    ("M7 il residuo di un'uscita inviata valutato dal veloce",
     "    if isinstance(req, dict) and req.get(\"sent\"):\n        return None\n"
     "    copia = copy.deepcopy(trade)",
     "    copia = copy.deepcopy(trade)",
     "test_uscita_gia_inviata_resta_al_lento"),
    ("M8 il veloce legge il database",
     "    candidati = _exit_candidates(foto[\"open_all\"])",
     "    candidati = _exit_candidates(_real_db.open_trades() or foto[\"open_all\"])",
     "test_il_giro_veloce_fa_zero_chiamate_al_database_e_al_mercato"),
    ("M9 la sbirciata della coda perde la sua cadenza",
     "            prossima_sbirciata = time.monotonic() + _SBIRCIATA_S",
     "            prossima_sbirciata = 0.0",
     "test_attesa_col_veloce_non_sbircia_piu_di_oggi"),
    ("M10 fotografia anche a interruttore spento",
     "    if _giro_veloce_acceso():\n        _fotografa_giro_lento(",
     "    if True:\n        _fotografa_giro_lento(",
     "test_interruttore_assente_nessuna_fotografia"),
    ("M11 corsia calda del punteggio tolta",
     "    if visto is not None and punteggio is not None and visto[1] is not None \\\n"
     "            and punteggio != visto[1]:",
     "    if False:",
     "test_corsia_calda_tennis_game_cambiato_anticipa"),
    ("M12 il canale aggiunge partite al veloce (unione)",
     "    righe, _ = CS.fondi(foto.get(\"righe\") or [], fresche or {})",
     "    righe = list(foto.get(\"righe\") or []) + list((fresche or {}).values())",
     "test_il_canale_non_aggiunge_partite_al_veloce"),
    ("M13 il veloce lavora sulla posizione VERA invece che su una copia",
     "    copia = copy.deepcopy(trade)",
     "    copia = trade",
     "test_equivalenza_il_lento_non_cambia_con_giri_veloci_intercalati"),
    ("M14 client con la sveglia del prezzo a interruttore spento",
     "        if _giro_veloce_acceso():\n            sveglia_prezzo = {",
     "        if True:\n            sveglia_prezzo = {",
     "test_interruttore_assente_il_client_non_ha_la_sveglia_del_prezzo"),
    ("M15 l'uscita dovuta non viene mai vista dal veloce",
     "    if decisione is None or now_ts < float(decisione.not_before_ts or 0.0):\n"
     "        return None",
     "    if True:\n        return None",
     "test_uscita_a_tempo_dovuta_anticipa_e_il_lento_la_invia"),
]


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _fine_riga(p: Path) -> str:
    return "\r\n" if b"\r\n" in p.read_bytes() else "\n"


def _leggi(p: Path) -> str:
    return p.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _scrivi(p: Path, testo: str, fine: str) -> None:
    with open(p, "wb") as fh:
        fh.write(testo.replace("\n", fine).encode("utf-8"))


def _pytest(nome_test: str) -> bool:
    """True se il test e' VERDE (cioe' la mutazione NON e' stata catturata)."""
    comando = [sys.executable, "-m", "pytest", TEST, "-q", "-p", "no:cacheprovider"]
    if nome_test:
        comando += ["-k", nome_test]
    res = subprocess.run(comando, cwd=str(RADICE), capture_output=True, text=True)
    return res.returncode == 0


def main() -> int:
    md5_iniziale = _md5(BOT)
    print("md5 di partenza: bot_service.py = %s" % md5_iniziale)
    if not _pytest(""):
        print("FERMO: la suite di C6 a non e' verde di partenza.")
        return 2
    print("Riferimento: la suite di C6 a e' VERDE prima di ogni mutazione.")
    fine = _fine_riga(BOT)
    catturate = 0
    for nome, cerca, sostituisci, test in MUTAZIONI:
        originale = _leggi(BOT)
        if originale.count(cerca) != 1:
            print("\n%s: FERMO, il testo da mutare compare %d volte"
                  % (nome, originale.count(cerca)))
            return 3
        prima = _md5(BOT)
        _scrivi(BOT, originale.replace(cerca, sostituisci, 1), fine)
        try:
            verde = _pytest(test)
        finally:
            _scrivi(BOT, originale, fine)
        dopo = _md5(BOT)
        if dopo != prima:
            print("\n%s: FERMO, md5 non ripristinato (%s -> %s)" % (nome, prima, dopo))
            return 4
        esito = "VERDE (NON catturata!)" if verde else "ROSSO"
        print("\n%s\n  test: %s\n  esito: %s\n  md5 invariato: %s" % (nome, test, esito, dopo))
        if not verde:
            catturate += 1
    print("\n%d mutazioni su %d catturate." % (catturate, len(MUTAZIONI)))
    finale = _md5(BOT)
    print("bot_service.py = %s (%s)" % (finale,
                                        "invariato" if finale == md5_iniziale else "CAMBIATO"))
    if finale != md5_iniziale:
        return 5
    return 0 if catturate == len(MUTAZIONI) else 1


if __name__ == "__main__":
    raise SystemExit(main())
