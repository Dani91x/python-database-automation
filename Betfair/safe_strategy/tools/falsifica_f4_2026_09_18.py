"""Falsificazione di F4: un test che non sa diventare rosso non certifica.

Per ogni mutazione: md5 del file PRIMA, mutazione sul codice VERO, pytest sul
test indicato (deve fallire), ripristino, md5 DOPO. Se un md5 non torna, lo
strumento si ferma: meglio nessun risultato che un file lasciato mutato.

Uso (dalla radice del repo, nel worktree):
    .venv/Scripts/python.exe -m Betfair.safe_strategy.tools.falsifica_f4_2026_09_18

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
CANALE = RADICE / "Betfair" / "safe_strategy" / "canale_scan.py"
TEST = "Betfair/safe_strategy/tests/test_canale_scan_f4_2026_09_18.py"

#: (nome, file, testo_da_cercare, testo_mutato, test_che_deve_diventare_rosso)
MUTAZIONI: List[Tuple[str, Path, str, str, str]] = [
    ("M1 a parita' vince il CANALE invece del database", CANALE,
     "    if b > a:\n        return dal_canale",
     "    if b >= a:\n        return dal_canale",
     "test_a_parita_di_updated_at_vince_il_db"),
    ("M2 niente controllo su odds_ts_ms (invariante B11)", CANALE,
     "    if not _numero(_odds_ts_ms(dal_canale)):\n        return dal_db",
     "    if False:\n        return dal_db",
     "test_la_riga_del_canale_senza_odds_ts_ms_perde"),
    ("M3 fusione per UNIONE: il canale aggiunge una partita", CANALE,
     "    righe = [r for r in (righe_db or []) if isinstance(r, dict)]",
     "    righe = [r for r in (righe_db or []) if isinstance(r, dict)]\n"
     "    righe = righe + [r for r in (fresche or {}).values()\n"
     "                     if str(r.get('event_id')) not in\n"
     "                     {str(x.get('event_id')) for x in righe}]",
     "test_il_canale_non_aggiunge_mai_una_partita"),
    ("M4 interruttore col verso di a321 (assente = ACCESO)", CANALE,
     "from Betfair.stream.canale_bot import VALORI_ACCESI, acceso",
     "from Betfair.stream.canale_bot import VALORI_ACCESI\n"
     "import os as _os_m4\n"
     "def acceso(nome):\n"
     "    return (_os_m4.getenv(nome) or '').strip().lower() not in ('0', 'false', 'no')",
     "test_senza_env_scritto_gli_interruttori_sono_spenti"),
    ("M5 nessun minimo fra due giri (ciclo a raffica)", BOT,
     "    passato = time.monotonic() - float(_ULTIMO_GIRO.get(\"mono\") or 0.0)\n"
     "    if 0.0 <= passato < _MIN_GIRO_S:\n"
     "        time.sleep(_MIN_GIRO_S - passato)",
     "    return",
     "test_la_sveglia_anticipa_il_giro_ma_mai_sotto_i_250_ms"),
    ("M6 la sveglia porta parametri d'ordine nella coda", CANALE,
     "        numeri[\"sveglie\"] = int(numeri.get(\"sveglie\", 0)) + 1",
     "        canale._requests.put_nowait(params)\n"
     "        numeri[\"sveglie\"] = int(numeri.get(\"sveglie\", 0)) + 1",
     "test_la_sveglia_alza_l_evento_e_non_porta_nessun_ordine"),
    ("M7 canale stantio: nessun ripiego sul database", BOT,
     "    rileggi = (not acceso) or (not fresche) or scaduto or not _CANALE_SCAN.get(\"righe_db\")",
     "    rileggi = (not acceso) or scaduto or not _CANALE_SCAN.get(\"righe_db\")",
     "test_col_canale_stantio_si_ripiega_sul_database"),
]


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _fine_riga(p: Path) -> str:
    """Il fine riga VERO del file (il repo e' a CRLF, i moduli nuovi anche).

    Senza questo, il ripristino cambierebbe ogni fine riga e l'md5 non
    tornerebbe piu': e' il reperto trovato dal delegato di F0/F1.
    """
    return "\r\n" if b"\r\n" in p.read_bytes() else "\n"


def _leggi(p: Path) -> str:
    """Il testo con fine riga NORMALIZZATO a ``\\n``, cosi' i testi da cercare
    si scrivono in un modo solo."""
    return p.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _scrivi(p: Path, testo: str, fine: str) -> None:
    with open(p, "wb") as fh:
        fh.write(testo.replace("\n", fine).encode("utf-8"))


def _pytest(nome_test: str) -> bool:
    """True se il test e' VERDE (cioe' la mutazione NON e' stata catturata)."""
    res = subprocess.run(
        [sys.executable, "-m", "pytest", TEST, "-k", nome_test, "-q",
         "-p", "no:cacheprovider"],
        cwd=str(RADICE), capture_output=True, text=True)
    return res.returncode == 0


def main() -> int:
    md5_iniziali = {BOT: _md5(BOT), CANALE: _md5(CANALE)}
    print("md5 di partenza:")
    for p, h in md5_iniziali.items():
        print("  %s = %s" % (p.name, h))
    if _pytest(""):
        print("\nRiferimento: la suite di F4 e' VERDE prima di ogni mutazione.")
    else:
        print("\nFERMO: la suite di F4 non e' verde di partenza.")
        return 2
    catturate = 0
    for nome, percorso, cerca, sostituisci, test in MUTAZIONI:
        fine = _fine_riga(percorso)
        originale = _leggi(percorso)
        if cerca not in originale:
            print("\n%s: FERMO, il testo da mutare non c'e' piu' in %s"
                  % (nome, percorso.name))
            return 3
        prima = _md5(percorso)
        _scrivi(percorso, originale.replace(cerca, sostituisci, 1), fine)
        try:
            verde = _pytest(test)
        finally:
            _scrivi(percorso, originale, fine)
        dopo = _md5(percorso)
        if dopo != prima:
            print("\n%s: FERMO, md5 non ripristinato (%s -> %s)" % (nome, prima, dopo))
            return 4
        esito = "VERDE (NON catturata!)" if verde else "ROSSO"
        print("\n%s\n  test: %s\n  esito: %s\n  md5 %s invariato: %s"
              % (nome, test, esito, percorso.name, dopo))
        if not verde:
            catturate += 1
    print("\n%d mutazioni su %d catturate." % (catturate, len(MUTAZIONI)))
    for p, h in md5_iniziali.items():
        attuale = _md5(p)
        print("  %s = %s (%s)" % (p.name, attuale,
                                  "invariato" if attuale == h else "CAMBIATO"))
        if attuale != h:
            return 5
    return 0 if catturate == len(MUTAZIONI) else 1


if __name__ == "__main__":
    raise SystemExit(main())
