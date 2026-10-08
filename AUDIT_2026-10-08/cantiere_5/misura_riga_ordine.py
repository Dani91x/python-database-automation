"""Cantiere 5 - costo del banco tennis per giro: `riga_ordine` + `verifica` PRIMA
(file di b5547eb) e DOPO (worktree), sugli STESSI ordini flumine veri.

Uso (dalla radice del repo):
    git show b5547eb:Betfair/stream/tennis_live/certificazione_bot.py > <tmp>/cb_prima.py
    python AUDIT_2026-10-08/cantiere_5/misura_riga_ordine.py <tmp>/cb_prima.py
"""
import importlib.util
import sys
import time

from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade

import Betfair.stream.tennis_live  # noqa: F401 - il pacchetto per gli import relativi
from Betfair.stream.tennis_live import certificazione_bot as DOPO


def carica_prima(percorso: str):
    spec = importlib.util.spec_from_file_location(
        "Betfair.stream.tennis_live._cb_prima", percorso)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def ordini(n_normali: int = 60, n_catene: int = 20) -> list:
    """Ordini flumine VERI: normali (un ordine per Trade) e catene di place-and-trim
    (parcheggio ridotto + rimpiazzo nello stesso Trade), come nel blotter."""
    out = []
    for i in range(n_normali):
        t = Trade("1.1", 11, 0, None)
        o = t.create_order("BACK" if i % 2 else "LAY", LimitOrder(2.0 + i * 0.02, 2.0))
        o.executable()
        out.append(o)
    for i in range(n_catene):
        t = Trade("1.1", 11, 0, None)
        park = t.create_order("LAY", LimitOrder(1.03, 1.0))
        park.executable()
        park.simulated.size_cancelled = 0.30   # taglio fatto, rimpiazzo dopo
        sost = t.create_order("LAY", LimitOrder(2.10, 0.70))
        sost.executable()
        out += [park, sost]
    return out


def misura(mod, oo, giri: int) -> float:
    t0 = time.perf_counter()
    for _ in range(giri):
        righe = [mod.riga_ordine(o) for o in oo]
        mod.verifica(mod.Osservazione(bot="t", modalita="live", ordini=righe), {})
    return time.perf_counter() - t0


def main() -> None:
    """Il MINIMO di 7 misure alternate (macchina condivisa: il minimo e' la misura
    meno disturbata), su due blotter: realistico (2 catene) e denso (20 catene)."""
    prima = carica_prima(sys.argv[1])
    giri = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    for catene in (2, 20):
        oo = ordini(n_normali=100 - 2 * catene, n_catene=catene)
        for _ in range(2):                   # riscaldamento
            misura(prima, oo, 5)
            misura(DOPO, oo, 5)
        tempi = {"PRIMA": [], "DOPO": []}
        for _ in range(7):
            tempi["PRIMA"].append(misura(prima, oo, giri))
            tempi["DOPO"].append(misura(DOPO, oo, giri))
        p, d = min(tempi["PRIMA"]), min(tempi["DOPO"])
        print("%d ordini (%d catene place-and-trim) x %d giri: PRIMA %.3f ms/giro, "
              "DOPO %.3f ms/giro (%+.1f %%)"
              % (len(oo), catene, giri, p * 1000.0 / giri, d * 1000.0 / giri,
                 (d / p - 1.0) * 100.0))


if __name__ == "__main__":
    main()
