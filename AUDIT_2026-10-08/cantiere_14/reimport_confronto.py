"""Cantiere 14 - prova di non regressione del reimport (sul cloud, senza DB vero).

Costruisce due cartelle di registrazione finta con i dati del formato vero dello
Stream API (``dati_tennis.partita_costruita``): A con ``_names.json`` completo,
B senza. Le importa con ``importa.converti_registrazione`` + ``carica_replay`` su
un Supabase FINTO in memoria (stesso del test di caricamento), DUE volte ciascuna,
e stampa i conteggi e i nomi delle selezioni. Lo stesso script gira PRIMA e DOPO
la modifica: i conteggi devono essere identici, le righe diverse spiegate.

Uso (dalla radice del worktree):
    python3 AUDIT_2026-10-08/cantiere_14/reimport_confronto.py > out.txt
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import Betfair.stream.db as db  # noqa: E402
from Betfair.stream.tennis_replay import caricamento as car  # noqa: E402
from Betfair.stream.tennis_replay import importa as imp  # noqa: E402
from Betfair.stream.tennis_replay.tests import dati_tennis as dt  # noqa: E402
from Betfair.stream.tennis_replay.tests.test_caricamento_importa_2026_10_07 import FintoSupabase  # noqa: E402

EV = "35999999"
SCORE = {"t": 1783427297.0, "score": {"eventTypeId": 2, "eventId": 35999999, "score": {
    "home": {"name": "Uno Troncato", "score": "15", "games": "1", "sets": "0", "gameSequence": [], "isServing": True, "serviceBreaks": 0},
    "away": {"name": "Due Troncato", "score": "0", "games": "0", "sets": "0", "gameSequence": [], "isServing": False, "serviceBreaks": 0}},
    "currentSet": 1, "currentGame": 2}}


def costruisci(radice: Path, con_nomi: bool) -> None:
    p = dt.partita_costruita()
    dt.scrivi(radice / "20260707" / EV, f"{EV}.raw.jsonl", p["a"])
    dt.scrivi(radice / "setbetting_20260707" / EV, f"{EV}.raw.jsonl", p["b"])
    (radice / "20260707" / EV / f"{EV}.score.jsonl").write_text(json.dumps(SCORE) + "\n", encoding="utf-8")
    if con_nomi:
        (radice / "20260707" / "_names.json").write_text(
            json.dumps({EV: {"101": "Uno Completo", "202": "Due Completo"}}), encoding="utf-8")


def esegui(etichetta: str, con_nomi: bool) -> None:
    f = FintoSupabase()
    db.get_supabase_client = lambda: f          # noqa: E731 - finto locale al processo dello script
    car.get_supabase_client = lambda: f
    with tempfile.TemporaryDirectory() as tmp:
        radice = Path(tmp)
        costruisci(radice, con_nomi)
        voce = imp.trova_registrazioni([str(radice)])[EV]
        for giro in (1, 2):
            rt = imp.converti_registrazione(EV, voce, usa_db=False)
            r = car.carica_replay(rt)
            print(f"[{etichetta}] giro {giro}: riepilogo={json.dumps(r, sort_keys=True)}")
    ev = f.tabelle[car.T_EVENTI][0]
    print(f"[{etichetta}] conteggi: eventi={len(f.tabelle[car.T_EVENTI])} mercati={len(f.tabelle[car.T_MERCATI])} "
          f"snapshot={len(f.tabelle[car.T_SNAPSHOT])} punteggi={len(f.tabelle[car.T_PUNTEGGIO])}")
    print(f"[{etichetta}] evento: n_markets={ev['n_markets']} n_snapshots={ev['n_snapshots']} n_score={ev['n_score']} "
          f"p1={ev['player1_name']!r} p2={ev['player2_name']!r}")
    for m in sorted(f.tabelle[car.T_MERCATI], key=lambda x: x["market_id"]):
        print(f"[{etichetta}] mercato {m['market_id']} {m['market_type']} n_updates={m['n_updates']} "
              f"selezioni={json.dumps(m['selections'], sort_keys=True)}")


def sequenza() -> None:
    """Stessa partita, STESSO DB finto: import senza nomi -> import con nomi -> di nuovo senza.
    Atteso dopo il cantiere 14: il nome migliore sale al secondo giro e NON ridiscende al terzo."""
    f = FintoSupabase()
    db.get_supabase_client = lambda: f          # noqa: E731
    car.get_supabase_client = lambda: f
    with tempfile.TemporaryDirectory() as tmp:
        radice = Path(tmp)
        costruisci(radice, False)
        voce = imp.trova_registrazioni([str(radice)])[EV]
        senza = imp.converti_registrazione(EV, voce, usa_db=False)
        (radice / "20260707" / "_names.json").write_text(
            json.dumps({EV: {"101": "Uno Completo", "202": "Due Completo"}}), encoding="utf-8")
        con = imp.converti_registrazione(EV, voce, usa_db=False)
        for etichetta, rt in (("1 senza nomi", senza), ("2 con nomi", con), ("3 di nuovo senza nomi", senza)):
            car.carica_replay(rt)
            ev = f.tabelle[car.T_EVENTI][0]
            mo = next(m for m in f.tabelle[car.T_MERCATI] if m["market_type"] == "MATCH_ODDS")
            print(f"[sequenza] {etichetta}: p1={ev['player1_name']!r} p2={ev['player2_name']!r} "
                  f"selezioni_MO={[s['name'] for s in mo['selections']]} "
                  f"snapshot={len(f.tabelle[car.T_SNAPSHOT])} mercati={len(f.tabelle[car.T_MERCATI])}")


if __name__ == "__main__":
    esegui("con _names.json", True)
    esegui("senza _names.json", False)
    sequenza()
