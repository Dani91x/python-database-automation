"""Quante righe di scan produce lo SCANNER VERO su una registrazione di calcio.

E' la misura che risponde alla domanda del rischio R6 sul lato calcio: le due
chiavi nuove (`odds_pt_ms`, `bet_delay`) entrano nella firma del write-on-change
- fanno CRESCERE il numero di righe scritte? `odds_pt_ms` si muove solo insieme
a `odds`, quindi no; `bet_delay` viene dalla definizione, quindi dovrebbe stare
fermo. "Dovrebbe" non basta: qui si conta.

Sola lettura: nessun database, nessun Betfair, nessun ordine. Legge la
registrazione e chiama il banco comune.
"""
from __future__ import annotations

import os
import sys

from Betfair.stream.backtest import banco_comune as B

EVENTO = sys.argv[1] if len(sys.argv) > 1 else "35833626"
CARTELLA = sys.argv[2] if len(sys.argv) > 2 else "_live_raw"
OGNI_MS = int(sys.argv[3]) if len(sys.argv) > 3 else 5000

# GUARDIA FAIL-LOUD (18/09, avviso del coordinatore). In un worktree `_live_raw`
# NON esiste: le registrazioni non sono tracciate da git. Un replay che non
# trova il `.raw.jsonl` non si lamenta - va avanti con zero tick e stampa numeri
# che sembrano buoni ("0 righe, nessuna differenza"), cioe' il peggior esito
# possibile: una misura che dice "tutto uguale" perche' non ha misurato niente.
# Meglio fermarsi subito e dire dove si stava guardando.
_RAW = os.path.join(CARTELLA, EVENTO, f"{EVENTO}.raw.jsonl")
if not os.path.isfile(_RAW):
    raise SystemExit(
        f"REGISTRAZIONE ASSENTE: {_RAW}\n"
        f"In un worktree `_live_raw` non c'e' (non e' tracciata da git). Passa la\n"
        f"cartella del checkout principale come secondo argomento, per esempio:\n"
        f'  ... {EVENTO} "C:/Users/Admin/Desktop/PYTHON DATABASE/'
        f'python-database-automation/_live_raw"\n'
        f"Senza registrazione questa sonda NON misura niente e non va usata.")

conti = {"righe": 0}
chiavi: set = set()
con_pt = {"n": 0}
con_bd = {"n": 0}
valori_bd: set = set()


def raccogli(**args) -> None:
    riga = args.get("row")
    if not riga:
        return
    conti["righe"] += 1
    p = riga.get("payload") or {}
    chiavi.update(p.keys())
    if p.get("odds_pt_ms") is not None:
        con_pt["n"] += 1
    if p.get("bet_delay") is not None:
        con_bd["n"] += 1
        valori_bd.add(p.get("bet_delay"))


esito = B.replay_evento(event_id=EVENTO, cartella=CARTELLA, servizio=raccogli,
                        sport="calcio", ogni_ms=OGNI_MS)
print(f"EVENTO {EVENTO}")
print(f"RIGHE_DI_SCAN {conti['righe']}")
print(f"CON_ODDS_PT_MS {con_pt['n']}")
print(f"CON_BET_DELAY {con_bd['n']}")
print(f"VALORI_BET_DELAY {sorted(valori_bd)}")
print(f"CHIAVI {len(chiavi)} {sorted(chiavi)}")
