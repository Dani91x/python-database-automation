"""Mutazioni INDIPENDENTI del coordinatore sulla consegna D2 (28/09/2026).

Si lancia dalla radice del worktree di verifica (origin/master + patch D2).
Per ogni mutazione: copia del file, sostituzione di UNA occorrenza (ancora a
riga singola, CRLF rispettato), test mirati, ripristino dalla copia, md5.
Non va MAI interrotto: il ripristino e' nel finally.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple

PY = sys.executable
RADICE = Path.cwd()
COPIE = Path(__file__).resolve().parent / "copie_mutazioni"
COPIE.mkdir(exist_ok=True)

T_CONDOTTA = [
    "Betfair/stream/tennis_scalper/tests/test_condotta_ordini_2026_09_17.py",
    "Betfair/stream/tennis_live/tests/test_cantiere_d2_chiusure_esatte_2026_09_28.py",
    "Betfair/stream/tennis_live/tests/test_cantiere_d2_minimo_e_specchio_2026_09_28.py",
]
T_BOT = T_CONDOTTA + [
    "Betfair/stream/tennis_scalper/tests/test_tennis_pro.py",
    "Betfair/stream/tennis_scalper/tests/test_tennis_flb.py",
    "Betfair/stream/tennis_scalper/tests/test_tennis_swing.py",
    "Betfair/stream/tennis_scalper/tests/test_reperti_money_critical_2026_09_17.py",
]
T_MOTORE = T_CONDOTTA + [
    "Betfair/stream/tennis_live/tests/test_motore_ordini_tennis_2026_09_25.py",
    "Betfair/stream/tests/test_motore_ordini_2026_09_24.py",
]
T_RUNNER = T_CONDOTTA + [
    "Betfair/stream/tennis_live/tests/test_tennis_audit_runner.py",
    "Betfair/stream/tennis_live/tests/test_tennis_bot_params.py",
    "Betfair/stream/tennis_live/tests/test_paper_execution_gap5.py",
    "Betfair/stream/tennis_live/tests/test_tennis_auto_mode_2026_09_25.py",
]

# (nome, file, vecchio, nuovo, quale occorrenza (0 = prima), test)
MUTAZIONI: List[Tuple[str, str, str, str, int, List[str]]] = [
    ("C1 spezza_esatta: parte diretta per ECCESSO (chiusura gonfiata)",
     "Betfair/stream/tennis_scalper/condotta_ordini.py",
     "diretta = round(math.floor(s / IT_BACK_STEP + 1e-9) * IT_BACK_STEP, 2)",
     "diretta = round(math.ceil(s / IT_BACK_STEP - 1e-9) * IT_BACK_STEP, 2)  # MUTAZIONE",
     0, T_CONDOTTA),
    ("C2 spezza_esatta: il resto si PERDE (chiusura mozzata)",
     "Betfair/stream/tennis_scalper/condotta_ordini.py",
     "return diretta, round(s - diretta, 2)",
     "return diretta, 0.0  # MUTAZIONE",
     0, T_CONDOTTA),
    ("C3 size_legale: la copertura non diretta torna GONFIATA al minimo",
     "Betfair/stream/tennis_scalper/condotta_ordini.py",
     "        return None, (\"copertura %.2f %s non piazzabile direttamente: va per \"",
     "        return max(s, MINIMO_LATO[lato]), None  # MUTAZIONE\n        return None, (\"copertura %.2f %s non piazzabile direttamente: va per \"",
     0, T_CONDOTTA),
    ("C4 OrdineComposto.size_matched conta solo la parte diretta",
     "Betfair/stream/tennis_scalper/condotta_ordini.py",
     "                         for o in self.parti()), 2)",
     "                         for o in self.parti()[:1]), 2)  # MUTAZIONE",
     0, T_BOT),
    ("C5 anti-cascata tolta (sequenza sempre permessa)",
     "Betfair/stream/tennis_scalper/condotta_ordini.py",
     "        avvii = self._avvii.get(chiave) or []",
     "        return True  # MUTAZIONE\n        avvii = self._avvii.get(chiave) or []",
     0, T_CONDOTTA),
    ("C6 annulla non ferma la sequenza (rimpiazzo dopo l'annullo)",
     "Betfair/stream/tennis_scalper/condotta_ordini.py",
     "        if ordine.sequenza is not None and ordine.in_corso():",
     "        if False and ordine.sequenza is not None and ordine.in_corso():  # MUTAZIONE",
     0, T_BOT),
    ("C7 diretta_ok: BACK non multiplo di 0,50 dato per diretto",
     "Betfair/stream/tennis_scalper/condotta_ordini.py",
     "        return s + 1e-9 >= IT_BACK_MIN_STAKE and \\",
     "        return s + 1e-9 >= IT_BACK_MIN_STAKE or \\",
     0, T_CONDOTTA),
    ("M1 motore: anche le CHIUSURE portate al minimo (prima delle due righe)",
     "Betfair/stream/motore_ordini.py",
     "        if azione == \"place\" and not riduce:",
     "        if azione == \"place\":  # MUTAZIONE",
     0, T_MOTORE),
    ("M2 motore: l'apertura sotto il minimo NON viene portata al minimo",
     "Betfair/stream/motore_ordini.py",
     "                if portata > chiesto + 1e-9:",
     "                if False and portata > chiesto + 1e-9:  # MUTAZIONE",
     0, T_MOTORE),
    ("S1 submin: porta_al_minimo gonfia anche sopra il minimo",
     "Betfair/stream/trading/submin.py",
     "    return minimo if s < minimo - _TOL else s",
     "    return minimo if s < minimo - _TOL else round(s + 0.5, 2)  # MUTAZIONE",
     0, T_MOTORE),
    ("P1 bot pro: la copertura non diretta torna sulla strada vecchia",
     "Betfair/stream/tennis_scalper/tennis_pro_bot.py",
     "        if copertura and self.live and not diretta_ok(size, side):",
     "        if False and copertura and self.live and not diretta_ok(size, side):  # MUTAZIONE",
     0, T_BOT),
    ("P2 bot swing: le chiusure esatte non avanzano a ogni book",
     "Betfair/stream/tennis_scalper/tennis_swing_bot.py",
     "        self._esatte.avanza(market)",
     "        pass  # MUTAZIONE",
     0, T_BOT),
    ("P3 bot flb: la copertura non diretta torna sulla strada vecchia",
     "Betfair/stream/tennis_scalper/tennis_flb_bot.py",
     "        if copertura and self.live and not diretta_ok(size, side):",
     "        if False and copertura and self.live and not diretta_ok(size, side):  # MUTAZIONE",
     0, T_BOT),
    ("R1 runner: in PAPER le blindature tornano spente (paper diverso dal live)",
     "Betfair/stream/tennis_live/tennis_runner.py",
     "    if mode_u in (\"LIVE\", \"PAPER\"):",
     "    if mode_u in (\"LIVE\",):  # MUTAZIONE",
     0, T_RUNNER),
    ("R2 runner: chiusure esatte spente",
     "Betfair/stream/tennis_live/tennis_runner.py",
     "        params.setdefault(\"exact_exits\", True)",
     "        params.setdefault(\"exact_exits\", False)  # MUTAZIONE",
     0, T_RUNNER),
    ("R3 runner: in PAPER il restart torna FORZATO dopo la grazia",
     "Betfair/stream/tennis_live/tennis_runner.py",
     "    senza_ordini = modo_ordini not in (\"LIVE\", \"PAPER\")",
     "    senza_ordini = modo_ordini not in (\"LIVE\",)  # MUTAZIONE",
     0, T_RUNNER + ["Betfair/stream/tennis_live/tests/test_modalita_e_guardie_tennis_2026_09_24.py"]),
    ("B1 servizio tennis: il tetto conta anche l'altra modalita'",
     "Betfair/stream/tennis_live/tennis_bot_service.py",
     "                       and _modalita_dichiarata(r) == d[\"mode\"]]",
     "                       ]  # MUTAZIONE",
     0, T_RUNNER),
]


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def sostituisci(testo: bytes, vecchio: str, nuovo: str, quale: int) -> bytes:
    crlf = b"\r\n" in testo
    v = vecchio.encode("utf-8")
    n = nuovo.encode("utf-8")
    if crlf:
        v = v.replace(b"\n", b"\r\n")
        n = n.replace(b"\n", b"\r\n")
    pos = -1
    for _ in range(quale + 1):
        pos = testo.find(v, pos + 1)
        if pos < 0:
            raise LookupError("ancora non trovata")
    return testo[:pos] + n + testo[pos + len(v):]


def main() -> int:
    esiti = []
    for nome, rel, vecchio, nuovo, quale, test in MUTAZIONI:
        f = RADICE / rel
        copia = COPIE / (rel.replace("/", "__") + ".orig")
        shutil.copy2(f, copia)
        prima = md5(f)
        esito = "?"
        t0 = time.time()
        try:
            try:
                f.write_bytes(sostituisci(f.read_bytes(), vecchio, nuovo, quale))
            except LookupError:
                esito = "NON APPLICATA (ancora non trovata)"
                continue
            esistenti = [t for t in test if (RADICE / t).exists()]
            r = subprocess.run(
                [PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *esistenti],
                cwd=str(RADICE), capture_output=True, text=True, errors="replace")
            coda = [x for x in r.stdout.strip().splitlines() if x.strip()][-1:] or [""]
            falliti = [x for x in r.stdout.splitlines() if x.startswith("FAILED") or x.startswith("ERROR")]
            if r.returncode == 0:
                esito = "SOPRAVVISSUTA (test verdi) | " + coda[0]
            else:
                esito = "ROSSA | " + (falliti[0][:150] if falliti else coda[0][:150])
        finally:
            shutil.copy2(copia, f)
            dopo = md5(f)
            ok = "ripristino OK" if dopo == prima else "!!! RIPRISTINO FALLITO !!!"
            esiti.append((nome, esito, ok, time.time() - t0))
            print("%-75s -> %s [%s, %.0f s]" % (nome[:75], esito, ok, time.time() - t0), flush=True)
    sopravvissute = [e for e in esiti if e[1].startswith("SOPRAVVISSUTA")]
    non_appl = [e for e in esiti if e[1].startswith("NON APPLICATA")]
    rotti = [e for e in esiti if "FALLITO" in e[2]]
    print("\nTOTALE %d | rosse %d | SOPRAVVISSUTE %d | non applicate %d | ripristini falliti %d" % (
        len(esiti), len(esiti) - len(sopravvissute) - len(non_appl), len(sopravvissute),
        len(non_appl), len(rotti)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
