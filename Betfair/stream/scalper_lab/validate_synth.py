"""Valida l'HARNESS con stream sintetici a risultato noto.

Se l'harness e' corretto:
  * paradise  -> il maker chiude molti scalp a profitto (scalp>0, FLAT>0)
  * reversion -> la fade reversion chiude al take-profit (scalp>0)
  * dead      -> nessuno scalp puo' chiudere (scalp==0)  [controllo negativo]

Un fallimento su paradise/reversion = i "no edge" sui dati reali sono SOSPETTI.

Uso: python -m Betfair.stream.scalper_lab.validate_synth
"""
from __future__ import annotations

import os

from Betfair.stream.scalper_lab import bt_lab
from Betfair.stream.scalper_lab.synth_raw import GENERATORS

# gate rilassati: isoliamo il pipeline fill->chiusura->metrica (non i gate)
RELAXED = {
    "stake": 10.0, "min_flow": 0.0, "warmup_ms": 500, "min_size": 1.0,
    "price_min": 1.01, "price_max": 1000.0, "max_spread_ticks": 6,
    "capture_min_ticks": 2, "capture_max_ticks": 20,
    "signal_ticks": 1.0, "max_signal_ticks": 20.0,  # anti-gap fuori dai piedi
    "entry_stop_before_s": 0.0, "flatten_before_s": 0.0, "cooldown_ms": 0,
    "lock_ttl_ms": 3_600_000, "entry_ttl_ms": 3_600_000,
}

SCEN = {
    "paradise":  {"mode": "auto",      "expect": "rt>0 & net>0"},
    "reversion": {"mode": "reversion", "expect": "rt>0"},
    "dead":      {"mode": "auto",      "expect": "0 ordini"},
}


def _gen(scenario: str) -> str:
    ev = f"_synth_{scenario}"
    d = os.path.join(bt_lab.DATA_DIR, ev)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{ev}.raw.jsonl")
    lines = GENERATORS[scenario]()
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return ev


def main() -> None:
    print(f"{'SCENARIO':<12}{'mode':<11}{'rt':>6}{'net':>8}{'naked':>6}"
          f"{'ord':>6}  atteso -> ESITO")
    all_ok = True
    for scen, cfg in SCEN.items():
        ev = _gen(scen)
        params = {**RELAXED, "mode": cfg["mode"]}
        r = bt_lab.run_event(ev, params, inplay=False)
        if "error" in r:
            print(f"{scen:<12}{cfg['mode']:<11}  ERRORE: {r['error']}")
            all_ok = False
            continue
        rt = r["roundtrips"]; net = r["net"]; naked = r["naked_sels"]
        ok = {
            "paradise":  rt > 0 and net > 0,
            "reversion": rt > 0,
            "dead":      rt == 0,   # mercato morto: nessuno scalp puo' chiudere
        }[scen]
        all_ok &= ok
        print(f"{scen:<12}{cfg['mode']:<11}{rt:>6}{net:>8.2f}{naked:>6}"
              f"{r['orders']:>6}  {cfg['expect']:<16} -> "
              f"{'PASS' if ok else 'FAIL'}")
    print(f"\n{'='*50}\nHARNESS {'VALIDATO ✓' if all_ok else 'SOSPETTO ✗ (verifica fill/metrica)'}")


if __name__ == "__main__":
    main()
