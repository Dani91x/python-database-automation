"""Dati di prova del Replay Tennis.

1. La registrazione VERA (Barrios Vera - Simakin, 07/07/2026, MATCH_ODDS
   1.259745327, 5217 righe raw + 104 righe di punteggio): cercata risalendo dalle
   cartelle del test fino a ``_live_raw_tennis/20260707/35790089`` (checkout
   dell'utente o worktree), oppure in ``TENNIS_REPLAY_PROVA_DIR``. Assente = i
   test che la usano sono SALTATI (dichiarato nel referto).
2. Una partita COSTRUITA con piu' mercati tennis nel formato vero dello Stream
   API (stesse chiavi e tipi: ``op``/``clk``/``pt``/``ct``/``mc``, ``id``,
   ``img``, ``marketDefinition`` con ``eventId``/``eventTypeId``/``marketType``/
   ``betDelay``/``inPlay``/``status``/``runners[{id,sortPriority,status}]``,
   ``rc[{id,atb,atl,trd,ltp,tv}]``, ``tv``), presi dalla riga di immagine della
   registrazione vera. Serve per la parte "tutti i mercati", che la registrazione
   vera (un solo mercato) non puo' provare.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

EVENTO_VERO = "35790089"
MERCATO_VERO = "1.259745327"


def cartella_vera() -> Optional[Path]:
    env = os.getenv("TENNIS_REPLAY_PROVA_DIR")
    if env and (Path(env) / f"{EVENTO_VERO}.raw.jsonl").exists():
        return Path(env)
    for su in Path(__file__).resolve().parents:
        c = su / "_live_raw_tennis" / "20260707" / EVENTO_VERO
        if (c / f"{EVENTO_VERO}.raw.jsonl").exists():
            return c
    return None


def _definizione(tipo: str, runners: List[Dict[str, Any]], *, status: str = "OPEN",
                 in_play: bool = True, version: int = 1) -> Dict[str, Any]:
    return {
        "bspMarket": False, "turnInPlayEnabled": True, "persistenceEnabled": True,
        "marketBaseRate": 5, "eventId": "35999999", "eventTypeId": "2",
        "numberOfWinners": 1, "bettingType": "ODDS", "marketType": tipo,
        "marketTime": "2026-07-07T10:30:00.000Z", "suspendTime": "2026-07-07T10:30:00.000Z",
        "bspReconciled": False, "complete": True, "inPlay": in_play, "crossMatching": True,
        "runnersVoidable": False, "numberOfActiveRunners": len(runners), "betDelay": 3,
        "status": status, "betDelayModels": ["PASSIVE"], "runners": runners,
        "regulators": ["MR_ITA"], "discountAllowed": True, "timezone": "UTC",
        "openDate": "2026-07-07T10:30:00.000Z", "version": version,
        "priceLadderDefinition": {"type": "CLASSIC"},
    }


def _r(sid: int, sp: int, status: str = "ACTIVE") -> Dict[str, Any]:
    return {"status": status, "sortPriority": sp, "id": sid}


def _mcm(pt: int, mc: List[Dict[str, Any]], ct: Optional[str] = None, clk: str = "AAAA") -> str:
    msg: Dict[str, Any] = {"op": "mcm", "clk": clk, "pt": pt}
    if ct:
        msg["ct"] = ct
    msg["mc"] = mc
    return json.dumps(msg, separators=(",", ":"))


MO, SB, TG = "1.900000001", "1.900000002", "1.900000003"


def partita_costruita() -> Dict[str, List[str]]:
    """Due file (come le cartelle MATCH_ODDS e SET_BETTING di ``record_multi``).

    File A: MATCH_ODDS e TOTAL_GAMES; file B: SET_BETTING. Dentro: immagini,
    delta, livelli tolti con size 0, ``trd`` cumulato, sospensione, chiusura con
    WINNER/LOSER.
    """
    t0 = 1783427296000
    a = [
        _mcm(t0, [
            {"id": MO, "img": True, "tv": 600.0,
             "marketDefinition": _definizione("MATCH_ODDS", [_r(101, 1), _r(202, 2)]),
             "rc": [{"atb": [[1.2, 467.98], [1.19, 789.92]], "atl": [[1.21, 46.97], [1.22, 251.92]],
                     "trd": [[1.22, 12.81]], "ltp": 1.22, "tv": 471.56, "id": 101},
                    {"atb": [[5.6, 10.17]], "atl": [[6.0, 88.81]], "trd": [[6.0, 4.47]],
                     "ltp": 6.0, "tv": 132.39, "id": 202}]},
            {"id": TG, "img": True,
             "marketDefinition": _definizione("TOTAL_GAMES", [_r(301, 1), _r(302, 2)]),
             "rc": [{"atb": [[1.9, 20.0]], "atl": [[2.0, 15.0]], "id": 301},
                    {"atb": [[1.95, 12.0]], "atl": [[2.06, 9.0]], "id": 302}]},
        ], ct="SUB_IMAGE"),
        # delta: il best back 1.2 sparisce (size 0) e si scambia a 1.21
        _mcm(t0 + 1500, [{"id": MO, "rc": [{"atb": [[1.2, 0]], "trd": [[1.21, 30.0]],
                                             "ltp": 1.21, "tv": 501.56, "id": 101}]}]),
        # cambio SOLO in profondita' (secondo livello lay): la curazione lo scarta
        _mcm(t0 + 1800, [{"id": MO, "rc": [{"atl": [[1.22, 300.0]], "id": 101}]}]),
        # sospensione del MATCH_ODDS (marketDefinition nuova, stessa forma)
        _mcm(t0 + 5000, [{"id": MO, "marketDefinition": _definizione(
            "MATCH_ODDS", [_r(101, 1), _r(202, 2)], status="SUSPENDED", version=2)}]),
        _mcm(t0 + 9000, [{"id": MO, "marketDefinition": _definizione(
            "MATCH_ODDS", [_r(101, 1), _r(202, 2)], status="OPEN", version=3)},
            {"id": TG, "rc": [{"atb": [[1.9, 0], [1.88, 50.0]], "id": 301}]}]),
        # chiusura con vincitore
        _mcm(t0 + 20000, [{"id": MO, "marketDefinition": _definizione(
            "MATCH_ODDS", [_r(101, 1, "LOSER"), _r(202, 2, "WINNER")], status="CLOSED", version=4)}]),
    ]
    b = [
        _mcm(t0 + 700, [
            {"id": SB, "img": True,
             "marketDefinition": _definizione("SET_BETTING", [_r(401, 1), _r(402, 2), _r(403, 3), _r(404, 4)]),
             "rc": [{"atb": [[3.0, 5.0]], "atl": [[3.5, 2.0]], "id": 401},
                    {"atb": [[4.0, 5.0]], "atl": [[4.6, 2.0]], "id": 402},
                    {"atb": [[6.0, 5.0]], "atl": [[7.0, 2.0]], "id": 403},
                    {"atb": [[2.5, 5.0]], "atl": [[2.7, 2.0]], "id": 404}]},
        ], ct="SUB_IMAGE"),
        _mcm(t0 + 12000, [{"id": SB, "rc": [{"atb": [[2.6, 8.0]], "id": 404}]}]),
    ]
    return {"a": a, "b": b}


def scrivi(cartella: Path, nome: str, righe: List[str]) -> Path:
    cartella.mkdir(parents=True, exist_ok=True)
    p = cartella / nome
    p.write_text("\n".join(righe) + "\n", encoding="utf-8")
    return p
