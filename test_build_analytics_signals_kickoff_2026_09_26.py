"""Stessa causa del dato sporco di analytics_signals, lato POPULATOR (FIX-B 26/09/2026).

Sul DB vero (sola lettura, 26/09) nelle ultime 60 giornate 14.034 righe / 255 partite
hanno kickoff diverso da matches.fixture_date; 13.531 di queste perche'
fixture_predictions.fixture_date e' la data PROGRAMMATA e non segue i rinvii, mentre
matches.fixture_date (riga del risultato) e' la data in cui la partita si e' giocata.
Esempio: 1506528 fixture_predictions 11/09 17:30Z, matches 13/09 17:30Z FT.
build_analytics_signals usava fp.fixture_date; merge_engine_signals l'istantanea di
engine_signals: due scrittori, due date diverse per la stessa partita. Ora entrambi
prendono la data dalla partita (matches, gia' letta per il settlement) e ripiegano
sulla propria fonte solo se la partita non c'e'.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("SUPABASE_KEY", "x")

import build_analytics_signals as bas  # noqa: E402


def _fp() -> dict:
    return {"fixture_id": 1506528, "league_id": 203, "league_name": "Super Lig", "season_year": 2026,
            "fixture_date": "2026-09-11T17:30:00+00:00", "home_team_name": "Casa", "away_team_name": "Ospite",
            "db_json_analisi": {"markets_calibrated": {"1x2": {"H": 0.5, "D": 0.3, "A": 0.2}}},
            "model_predictions_json": None, "tactical_engine_json": None}


def _match(**over) -> dict:
    m = {"fixture_id": 1506528, "fixture_date": "2026-09-13T17:30:00+00:00", "status_short": "FT",
         "goals_home": 2, "goals_away": 0, "fulltime_home": 2, "fulltime_away": 0,
         "halftime_home": 1, "halftime_away": 0}
    m.update(over)
    return m


def test_kickoff_dalla_partita_giocata_non_dalla_data_programmata():
    righe = bas._rows_for_fixture(_fp(), _match())
    assert righe, "il finto deve produrre righe"
    assert {r["kickoff"] for r in righe} == {"2026-09-13T17:30:00+00:00"}


def test_senza_partita_resta_la_data_di_fixture_predictions():
    righe = bas._rows_for_fixture(_fp(), None)
    assert righe and {r["kickoff"] for r in righe} == {"2026-09-11T17:30:00+00:00"}


def test_la_lettura_di_matches_porta_la_data_della_partita():
    class _Q:
        def __init__(self, log):
            self.log = log

        def select(self, cols):
            self.log.append(cols)
            return self

        def in_(self, col, vals):
            return self

        def execute(self):
            from types import SimpleNamespace
            return SimpleNamespace(data=[_match()])

    class _DB:
        def __init__(self):
            self.log = []

        def table(self, name):
            return _Q(self.log)

    db = _DB()
    out = bas._fetch_matches(db, [1506528])
    assert "fixture_date" in [c.strip() for c in db.log[0].split(",")]
    assert out[1506528]["fixture_date"] == "2026-09-13T17:30:00+00:00"
