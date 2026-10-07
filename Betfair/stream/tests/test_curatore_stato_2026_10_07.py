"""Curatore (calcio e tennis): un CAMBIO DI STATO entra nel replay anche coi best invariati.

Reperto del 07/10 (cantiere Replay Tennis, decisione dell'utente "correggi"): il
curatore conservava una riga solo se cambiavano i best back/lay/ltp o se era
passata la cadenza. La CHIUSURA di un mercato gia' vuoto da sospeso ha i best
invariati (libro vuoto): se arrivava entro 10 s dall'ultima riga, spariva. Sul
calcio vero (35760084, ricostruzione dal raw) 17 mercati su 21 finivano nel replay
SOSPESI invece che CHIUSI.

Dato VERO: ``dati/curatore_chiusura_35760084.jsonl`` = gli ultimi 9 libri del mercato
1.259475526 della 35760084 nel formato del file curato (``recorder.serialize_book``):
OPEN, sospensione, CLOSED 0,99 s dopo l'ultimo sospeso.

Regola corretta: conservare in piu' SOLO i cambi di stato; le righe che la regola
vecchia conservava restano tutte (la cadenza non si sposta).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from Betfair.stream.curator import curate_event, curate_records

DATI = Path(__file__).with_name("dati") / "curatore_chiusura_35760084.jsonl"


def _libri():
    return [json.loads(x) for x in DATI.read_text(encoding="utf-8").splitlines() if x.strip()]


def _book(pt, back, lay, status="OPEN", inplay=False, mid="1.1"):
    return {"market_id": mid, "pt": pt, "status": status, "inplay": inplay, "tv": 100.0,
            "runners": {"11": {"b": [[back, 50.0]] if back else [], "l": [[lay, 50.0]] if lay else [],
                               "ltp": back, "tv": 10.0}}}


def test_calcio_vero_la_chiusura_entra_nel_replay(tmp_path):
    p = os.path.join(tmp_path, "35760084.jsonl")
    with open(p, "w", encoding="utf-8") as fh:
        for b in _libri():
            fh.write(json.dumps(b) + "\n")
    righe = curate_event(p, "35760084", cadence_sec=10)
    # le prime 7 righe sono quelle di sempre (cambi dei best, cadenza); l'ottava e'
    # la chiusura, 0,99 s dopo l'ultimo sospeso: prima spariva
    assert [(r["status"], r["ts"][11:23]) for r in righe] == [
        ("OPEN", "16:08:00.181"), ("OPEN", "16:08:00.702"), ("OPEN", "16:08:00.913"),
        ("SUSPENDED", "16:08:01.306"), ("SUSPENDED", "16:09:06.523"), ("SUSPENDED", "16:09:07.828"),
        ("SUSPENDED", "16:09:09.541"), ("CLOSED", "16:09:10.534")]


def test_solo_i_cambi_di_stato_in_piu_e_la_cadenza_non_si_sposta():
    libri = [
        _book(0, 2.0, 2.02),
        _book(3_000, 2.0, 2.02, status="SUSPENDED"),     # stato cambiato, best uguali: ENTRA
        _book(10_000, 2.0, 2.02, status="SUSPENDED"),    # cadenza dalla riga 0 (regola di sempre): ENTRA
        _book(12_000, 2.0, 2.02, status="SUSPENDED"),    # nulla di nuovo: fuori
        _book(15_000, 2.0, 2.02, status="OPEN", inplay=True),   # stato e inplay: ENTRA
        _book(20_000, 2.0, 2.02, status="OPEN", inplay=True),   # cadenza dalla riga 10_000: ENTRA
    ]
    righe = curate_records(libri, "ev", cadence_sec=10)
    assert [(r["status"], r["inplay"]) for r in righe] == [
        ("OPEN", False), ("SUSPENDED", False), ("SUSPENDED", False), ("OPEN", True), ("OPEN", True)]


def test_inplay_cambiato_coi_best_uguali_entra():
    righe = curate_records([_book(0, 2.0, 2.02), _book(1_000, 2.0, 2.02, inplay=True)], "ev", cadence_sec=10)
    assert [r["inplay"] for r in righe] == [False, True]


def test_stato_per_mercato_non_si_mescola():
    libri = [_book(0, 2.0, 2.02, mid="1.1"), _book(0, 3.0, 3.1, mid="1.2"),
             _book(1_000, 3.0, 3.1, status="SUSPENDED", mid="1.2"),
             _book(2_000, 2.0, 2.02, mid="1.1")]
    righe = curate_records(libri, "ev", cadence_sec=10)
    assert [(r["market_id"], r["status"]) for r in righe] == [("1.1", "OPEN"), ("1.2", "OPEN"), ("1.2", "SUSPENDED")]
