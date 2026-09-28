"""Falsificazione del CANTIERE T (28/09). Uso, dalla radice del repo:

    .venv/Scripts/python.exe AUDIT_2026-09-28/cantiere_t/falsifica_t.py [filtro]

Ogni mutazione reintroduce un difetto nel codice di produzione; il test indicato
deve diventare ROSSO. Il file si ripristina SEMPRE dalla copia in memoria
(anche su eccezione) e lo sha1 si verifica a fine giro. Gestisce CRLF.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
PY = str(RADICE / ".venv" / "Scripts" / "python.exe")
SCALPER = "Betfair/stream/tennis_scalper/tennis_scalper_bot.py"
PRO = "Betfair/stream/tennis_scalper/tennis_pro_bot.py"
T_PRO = "Betfair/stream/tennis_live/tests/test_cantiere_t_pro_residuo_2026_09_28.py"
T_SCALPER ="Betfair/stream/tennis_live/tests/test_cantiere_t_scalper_sequenze_2026_09_28.py"

# (nome, file, testo originale, testo mutato, test che deve diventare rosso)
MUTAZIONI = [
    ("T1 piatta dichiarata chiusa con un ordine dello slot ancora vivo",
     SCALPER,
     "            if vivi or slot.submins:\n",
     "            if False:  # MUTAZIONE\n",
     T_SCALPER + "::test_piatta_con_un_ordine_dello_slot_vivo_non_si_dichiara_chiusa"),
    ("T2 residuo 'accettato' mentre la sequenza e' appena partita",
     SCALPER,
     "        elif slot.submins:\n            # CANTIERE T (28/09): `_place_exact` torna None",
     "        elif False:  # MUTAZIONE\n            # CANTIERE T (28/09): `_place_exact` torna None",
     T_SCALPER + "::test_chiusura_tutta_sotto_il_minimo_non_dichiara_chiuso_col_parcheggio_vivo"),
    ("T3 anti-cascata sull'orologio del PC",
     SCALPER,
     "        now_ms = int(self._orologio_s() * 1000)\n        rate_ok",
     "        import time as _t\n        now_ms = int(_t.time() * 1000)  # MUTAZIONE\n        rate_ok",
     T_SCALPER + "::test_rinvio_anti_cascata_sull_orologio_del_mercato"),
    ("T4 min_bet_skip a ogni book (niente dedup)",
     SCALPER,
     "        if (slot.status == FLATTENING and main_order is not None) or not rate_ok:\n"
     "            if self._residuo_non_piazzabile_detto(selection_id, side, rest):",
     "        if (slot.status == FLATTENING and main_order is not None) or not rate_ok:\n"
     "            if True:  # MUTAZIONE",
     T_SCALPER + "::test_sequenza_abortita_non_lascia_il_parcheggio_vivo"),
    ("T6 sostituto del rimpiazzo nato dopo il DONE della sequenza non agganciato",
     SCALPER,
     "        for o in list(slot.flatten_orders):\n            tr = getattr(o, \"trade\", None)\n"
     "            for x in list(getattr(tr, \"orders\", None) or []):\n                self._track(slot, x)\n"
     "        if not slot.submins:",
     "        pass  # MUTAZIONE\n        if not slot.submins:",
     T_SCALPER + "::test_chiusura_tutta_sotto_il_minimo_non_dichiara_chiuso_col_parcheggio_vivo"),
    ("T7 sequenza col parcheggio morto prima del taglio resta in corso per sempre",
     SCALPER,
     "            elif (\n                new_state.step in (SubminStep.PLACED, SubminStep.TRIMMED)",
     "            elif False and (  # MUTAZIONE\n                new_state.step in (SubminStep.PLACED, SubminStep.TRIMMED)",
     T_SCALPER + "::test_parcheggio_ritirato_prima_del_taglio_non_blocca_la_sorveglianza"),
    ("T8 parcheggio orfano mai ritirato dal flatten",
     SCALPER,
     "            if (p >= 999.0 or p <= 1.011) and (",
     "            if (p >= 999.0 or p <= 1.011) or (  # MUTAZIONE",
     T_SCALPER + "::test_sequenza_abortita_non_lascia_il_parcheggio_vivo"),
    ("T9 LOCKING chiude il ciclo con un parcheggio ancora PENDING",
     SCALPER,
     "                if any(self._has_live(o) for o in slot.flatten_orders):\n                    return",
     "                if False:  # MUTAZIONE\n                    return",
     T_SCALPER + "::test_locking_non_chiude_il_ciclo_con_un_parcheggio_ancora_pending"),
    ("P1 PRO: FLAT con sbilancio di centesimi riducibile (soglia 0,02 com'era)",
     PRO,
     "            if self._centesimo_migliora(nw, nl, px.get(sel), trade.get(\"side\")):",
     "            if False:  # MUTAZIONE",
     T_PRO + "::test_sbilancio_di_centesimi_riducibile_non_si_dichiara_flat"),
]


def sha1(p: Path) -> str:
    return hashlib.sha1(p.read_bytes()).hexdigest()


def main() -> int:
    filtro = sys.argv[1] if len(sys.argv) > 1 else ""
    esiti = []
    for nome, rel, orig, mut, test in MUTAZIONI:
        if filtro and filtro not in nome:
            continue
        p = RADICE / rel
        raw = p.read_bytes()
        crlf = b"\r\n" in raw
        testo = raw.decode("utf-8")
        o, m = (orig.replace("\n", "\r\n"), mut.replace("\n", "\r\n")) if crlf else (orig, mut)
        n = testo.count(o)
        if n != 1:
            esiti.append((nome, "NON APPLICABILE (%d occorrenze)" % n))
            continue
        prima = sha1(p)
        try:
            p.write_bytes(testo.replace(o, m).encode("utf-8"))
            r = subprocess.run([PY, "-m", "pytest", test, "-q", "-p", "no:cacheprovider", "-x"],
                               cwd=str(RADICE), capture_output=True, text=True, timeout=600)
            esiti.append((nome, "ROSSA" if r.returncode != 0 else "VERDE (test NON falsificato)"))
        finally:
            p.write_bytes(raw)
        assert sha1(p) == prima, "ripristino fallito: " + rel
        assert b"MUTAZIONE" not in p.read_bytes()
    for nome, e in esiti:
        print("%-75s %s" % (nome, e))
    return 0 if all(e == "ROSSA" for _n, e in esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
