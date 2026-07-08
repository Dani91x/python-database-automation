"""Generatore di stream Betfair SINTETICI (formato mcm) a risultato NOTO.

Serve a VALIDARE l'harness: se in un mercato costruito apposta uno scalp DEVE
chiudere a profitto e il backtest lo registra, allora i risultati negativi sui
dati reali sono veri (non bug). Se non lo registra -> bug nell'harness.

Scenari:
  * paradise  : spread 1 tick, volume tradato ENORME su entrambi i touch ->
                il maker riempie ENTRAMBE le gambe e cattura lo spread. Attesi
                molti scalp chiusi e FLAT > 0.
  * reversion : il prezzo sale di N tick e poi RITORNA, con volume ai prezzi
                giusti -> una entry reversion (fade) chiude al take-profit.
  * dead      : spread largo, ZERO volume tradato -> nessuno scalp puo' chiudere
                (controllo negativo: qui scalp DEVE essere 0).

Uso: python -m Betfair.stream.scalper_lab.synth_raw --scenario paradise --out <path>
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List

MARKET_ID = "1.900000001"
EVENT_ID = "99999999"
TARGET = 111       # runner su cui facciamo oscillare il prezzo
R2, R3 = 222, 333  # altri due runner (book statico, il bot non li tocca)

LADDER_STEP_AT_3 = 0.05  # 3.0-4.0 -> 1 tick = 0.05


def _mdef(status: str = "OPEN", inplay: bool = False,
          winner: int | None = None) -> Dict[str, Any]:
    def runner(rid: int) -> Dict[str, Any]:
        st = "WINNER" if (winner is not None and rid == winner) else (
            "LOSER" if winner is not None else "ACTIVE")
        return {"status": st, "sortPriority": 1, "id": rid}
    return {
        "bspMarket": False, "turnInPlayEnabled": True, "persistenceEnabled": True,
        "marketBaseRate": 5, "eventId": EVENT_ID, "eventTypeId": "1",
        "numberOfWinners": 1, "bettingType": "ODDS", "marketType": "MATCH_ODDS",
        "marketTime": "2026-07-07T18:00:00.000Z",
        "suspendTime": "2026-07-07T18:00:00.000Z",
        "bspReconciled": False, "complete": True, "inPlay": inplay,
        "crossMatching": True, "runnersVoidable": False,
        "numberOfActiveRunners": 3, "betDelay": 0, "status": status,
        "runners": [runner(TARGET), runner(R2), runner(R3)],
        "regulators": ["MR_ITA"], "countryCode": "IT", "discountAllowed": True,
        "timezone": "GMT", "openDate": "2026-07-07T18:00:00.000Z",
        "version": 1, "priceLadderDefinition": {"type": "CLASSIC"},
    }


def _static_others() -> List[Dict[str, Any]]:
    # book largo e senza volume: il bot non deve operare su questi runner
    return [
        {"atb": [[5.0, 20.0]], "atl": [[6.0, 20.0]], "id": R2},
        {"atb": [[5.0, 20.0]], "atl": [[6.0, 20.0]], "id": R3},
    ]


def _msg(pt: int, rc: List[Dict[str, Any]], mdef: Dict[str, Any] | None = None,
         img: bool = False) -> str:
    mc: Dict[str, Any] = {"id": MARKET_ID, "rc": rc}
    if mdef is not None:
        mc["marketDefinition"] = mdef
    if img:
        mc["img"] = True
    return json.dumps({"op": "mcm", "pt": pt, "mc": [mc]})


def gen_paradise(steps: int = 400, big: float = 500.0, rest: float = 30.0) -> List[str]:
    """Spread 1 tick (3.00/3.05), volume CUMULATIVO crescente su entrambi i touch.

    trd e' cumulativo (formato Betfair): cresce di ``big`` ad ogni step cosi'
    flumine vede volume NUOVO e riempie gli ordini resting. size in coda (``rest``)
    piccola perche' il fill richiede trd_delta > coda_davanti.
    """
    out: List[str] = []
    t0 = 1_800_000_000_000
    init_rc = [
        {"atb": [[3.00, rest]], "atl": [[3.05, rest]], "id": TARGET},
        *_static_others(),
    ]
    out.append(_msg(t0, init_rc, _mdef("OPEN", False), img=True))
    dt = 2000
    cum300 = cum305 = 0.0
    for i in range(steps):
        t = t0 + (i + 1) * dt
        cum300 += big
        cum305 += big
        rc = [{
            "atb": [[3.00, rest]], "atl": [[3.05, rest]],
            "trd": [[3.00, round(cum300, 2)], [3.05, round(cum305, 2)]],
            "ltp": 3.05, "tv": round(cum300 + cum305, 2), "id": TARGET,
        }]
        out.append(_msg(t, rc))
    # chiusura mercato con vincitore
    tclose = t0 + (steps + 2) * dt
    out.append(_msg(tclose, [{"id": TARGET}], _mdef("SUSPENDED", True)))
    out.append(_msg(tclose + dt, [{"id": TARGET}],
                    _mdef("CLOSED", True, winner=TARGET)))
    return out


def gen_reversion(cycles: int = 60, big: float = 500.0, rest: float = 30.0) -> List[str]:
    """Prezzo oscilla 3.00<->3.10 (2 tick) con volume cumulativo: fade chiude."""
    out: List[str] = []
    t0 = 1_800_000_000_000
    out.append(_msg(t0, [
        {"atb": [[3.00, rest]], "atl": [[3.05, rest]], "id": TARGET},
        *_static_others(),
    ], _mdef("OPEN", False), img=True))
    dt = 2000
    t = t0
    # swing NETTO di ~3 tick su e giu' (3.00 -> 3.15 -> 3.00), preceduto da
    # stabilita' (per fissare il ref del segnale). Volume su tutti i touch.
    stable = [(3.00, 3.05)] * 4
    up = [(3.05, 3.10), (3.10, 3.15), (3.15, 3.20)]
    down = [(3.10, 3.15), (3.05, 3.10), (3.00, 3.05)]
    seq = stable + up + down
    cum: Dict[float, float] = {}
    for c in range(cycles):
        for (bb, bl) in seq:
            t += dt
            cum[bb] = cum.get(bb, 0.0) + big
            cum[bl] = cum.get(bl, 0.0) + big
            rc = [{
                "atb": [[bb, rest]], "atl": [[bl, rest]],
                "trd": [[bb, round(cum[bb], 2)], [bl, round(cum[bl], 2)]],
                "ltp": bl, "tv": round(sum(cum.values()), 2), "id": TARGET,
            }]
            out.append(_msg(t, rc))
    out.append(_msg(t + dt, [{"id": TARGET}], _mdef("SUSPENDED", True)))
    out.append(_msg(t + 2 * dt, [{"id": TARGET}],
                    _mdef("CLOSED", True, winner=TARGET)))
    return out


def gen_dead(steps: int = 200) -> List[str]:
    """Spread largo, ZERO volume: controllo negativo (scalp DEVE = 0)."""
    out: List[str] = []
    t0 = 1_800_000_000_000
    out.append(_msg(t0, [
        {"atb": [[3.00, 20.0]], "atl": [[3.40, 20.0]], "id": TARGET},
        *_static_others(),
    ], _mdef("OPEN", False), img=True))
    dt = 2000
    for i in range(steps):
        t = t0 + (i + 1) * dt
        out.append(_msg(t, [{"atb": [[3.00, 20.0]], "atl": [[3.40, 20.0]],
                             "id": TARGET}]))
    tclose = t0 + (steps + 2) * dt
    out.append(_msg(tclose, [{"id": TARGET}], _mdef("SUSPENDED", True)))
    out.append(_msg(tclose + dt, [{"id": TARGET}],
                    _mdef("CLOSED", True, winner=TARGET)))
    return out


GENERATORS = {"paradise": gen_paradise, "reversion": gen_reversion, "dead": gen_dead}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=list(GENERATORS), required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    lines = GENERATORS[args.scenario]()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"scritto {args.scenario}: {len(lines)} messaggi -> {args.out}")


if __name__ == "__main__":
    main()
