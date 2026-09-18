"""Falsificazione dei test di F5/F6 (la sveglia del ciclo).

Un test che non sa diventare rosso non certifica niente. Qui si MUTA il codice
VERO - non una copia, non un doppione - si pretende che la suite diventi ROSSA,
si ripristina e si verifica con md5 che il file sia tornato byte per byte quello
di prima. Se una mutazione resta verde, o se un ripristino non torna, lo
strumento si ferma e lo dice.

Uso:
  .venv/Scripts/python.exe -m Betfair.stream.tools.falsifica_sveglia_f5_f6_2026_09_18

Uscita 0 = tutte le mutazioni catturate e tutti gli md5 identici.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

RADICE = Path(__file__).resolve().parents[3]
SVEGLIA = RADICE / "Betfair" / "stream" / "sveglia_canale.py"
OMEGA = RADICE / "Betfair" / "omega" / "omega_service.py"
MIKE = RADICE / "Betfair" / "mike" / "service.py"
TENNIS = RADICE / "Betfair" / "stream" / "tennis_live" / "tennis_bot_service.py"

TEST_MODULO = "Betfair/stream/tests/test_sveglia_canale_f5_f6_2026_09_18.py"
TEST_BOT = "Betfair/stream/tests/test_sveglia_bot_f5_f6_2026_09_18.py"

#: (nome, file, testo da cercare, testo con cui sostituirlo, test da lanciare)
MUTAZIONI: List[Tuple[str, Path, str, str, str]] = [
    (
        "M1 - via il PAVIMENTO: la sveglia fa ripartire il giro subito",
        SVEGLIA,
        "            if trascorso >= pavimento:",
        "            if True:  # MUTAZIONE M1",
        TEST_MODULO,
    ),
    (
        "M2 - il filtro 'interessa' ignorato: si sveglia per qualunque evento",
        SVEGLIA,
        "            interessa = bool(self._interessa(event_id))",
        "            interessa = True  # MUTAZIONE M2",
        TEST_MODULO,
    ),
    (
        "M3 - il messaggio di sveglia accetta qualunque motivo (anche 'place')",
        SVEGLIA,
        "    return motivo if motivo in MOTIVI_SVEGLIA else None",
        "    return motivo or None  # MUTAZIONE M3",
        TEST_MODULO,
    ),
    (
        "M4 - il client che non si collega SOLLEVA verso il bot",
        SVEGLIA,
        "            except Exception as ex:  # noqa: BLE001 - il canale non ferma mai il bot",
        "            except ZeroDivisionError as ex:  # MUTAZIONE M4",
        TEST_MODULO,
    ),
    (
        "M5 - Omega usa la sveglia anche a interruttore SPENTO",
        OMEGA,
        "    if _ASCOLTO_SCAN is None:\n        time.sleep(pausa)\n        return",
        "    if False:  # MUTAZIONE M5\n        time.sleep(pausa)\n        return",
        TEST_BOT,
    ),
    (
        "M6 - il pavimento di Mike va a zero: giri (e letture) senza tetto",
        MIKE,
        "    return max(1.0, ms / 1000.0 * 2)",
        "    return 0.0  # MUTAZIONE M6",
        TEST_BOT,
    ),
    (
        "M7 - il ponte tennis si aggancia anche a interruttore SPENTO",
        TENNIS,
        "    if not _SV.acceso(_SV.ENV_TENNIS_SVEGLIA):\n        return",
        "    if False:  # MUTAZIONE M7\n        return",
        TEST_BOT,
    ),
    (
        "M8 - Omega apre il client anche a interruttore SPENTO",
        OMEGA,
        "    if not _SV.acceso(_SV.ENV_OMEGA_SVEGLIA):\n        return",
        "    if False:  # MUTAZIONE M8\n        return",
        TEST_BOT,
    ),
    (
        "M9 - Mike apre il client anche a interruttore SPENTO",
        MIKE,
        "    if not _SV.acceso(_SV.ENV_MIKE_SVEGLIA):\n        return",
        "    if False:  # MUTAZIONE M9\n        return",
        TEST_BOT,
    ),
]


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _pytest(percorso: str) -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", percorso, "-q", "-p", "no:cacheprovider"],
        cwd=str(RADICE), capture_output=True, text=True, timeout=900).returncode


def main() -> int:
    guasti: List[str] = []
    for nome, percorso, cerca, metti, test in MUTAZIONI:
        prima_bytes = percorso.read_bytes()
        prima_md5 = _md5(percorso)
        testo = prima_bytes.decode("utf-8")
        cerca_crlf = cerca.replace("\n", "\r\n") if "\r\n" in testo else cerca
        if testo.count(cerca_crlf) != 1:
            guasti.append(f"{nome}: ancora da mutare (occorrenze != 1) in {percorso.name}")
            continue
        mutato = testo.replace(cerca_crlf, metti.replace("\n", "\r\n")
                               if "\r\n" in testo else metti)
        try:
            percorso.write_text(mutato, encoding="utf-8", newline="")
            esito = _pytest(test)
        finally:
            percorso.write_bytes(prima_bytes)
        dopo_md5 = _md5(percorso)
        if dopo_md5 != prima_md5:
            guasti.append(f"{nome}: RIPRISTINO NON IDENTICO ({prima_md5} -> {dopo_md5})")
        if esito == 0:
            guasti.append(f"{nome}: la suite e' rimasta VERDE (il test non falsifica)")
            print(f"[VERDE - GUASTO] {nome}")
        else:
            print(f"[ROSSO - ok]     {nome}   md5 {prima_md5}")
    print("\nmd5 dei file, a fine corsa:")
    for p in (SVEGLIA, OMEGA, MIKE, TENNIS):
        print(f"  {p.name}: {_md5(p)}")
    if guasti:
        print("\nGUASTI:")
        for g in guasti:
            print("  - " + g)
        return 1
    print("\nTutte le mutazioni catturate, tutti gli md5 identici.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
