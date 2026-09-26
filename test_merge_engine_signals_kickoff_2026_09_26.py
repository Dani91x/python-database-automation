"""Causa a monte del dato sporco di analytics_signals (FIX-B 26/09/2026, reperto dati
del referto di fase 3 sessione B §10): 25 partite / 546 righe con `kickoff` diverso
dalla data vera della partita, alcune `settled=true` con kickoff FUTURO.

Caso vero, partita 1499655 (DB, sola lettura, 26/09):
  engine_signals.kickoff        = 2026-09-26 20:00Z  (istantanea presa all'emissione del
                                  segnale, run_date 25/09, dalla matches di allora)
  matches.fixture_date          = 2026-09-25 23:00Z  (data vera, partita FT)
  analytics_signals (poisson)   = 15 righe a 26/09 20:00Z scritte da merge_engine_signals
                                  (generated_at '2026-09-25 00:00' = emitted_at del merger),
                                  1 riga a 25/09 23:00Z del populator build_analytics_signals.
merge_engine_signals._build copiava es["kickoff"] (istantanea vecchia) sopra il kickoff
corretto del populator. Ora il kickoff viene dalla partita (matches.fixture_date, gia'
letta per il settlement); l'istantanea di engine_signals resta solo come ripiego.
Finti con le chiavi/tipi delle righe vere di engine_signals e matches.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("SUPABASE_KEY", "x")

import merge_engine_signals as mes  # noqa: E402


def _es(**over) -> dict:
    r = {"signal_uid": "poisson|1499655|O25|2026-09-25", "run_date": "2026-09-25",
         "fixture_id": 1499655, "engine": "poisson", "market": "O25", "market_label": "Over 2.5",
         "status": "PLACED", "prob_calibrated": 0.61, "result": "WON", "league_id": 129,
         "league_name": "Primera Nacional", "season_year": 2026, "home_team": "Casa",
         "away_team": "Ospite", "kickoff": "2026-09-26T20:00:00+00:00",
         "emitted_at": "2026-09-25T00:00:00+00:00", "direction": "back"}
    r.update(over)
    return r


def _match(**over) -> dict:
    m = {"fixture_id": 1499655, "fixture_date": "2026-09-25T23:00:00+00:00", "status_short": "FT",
         "goals_home": 2, "goals_away": 1, "fulltime_home": 2, "fulltime_away": 1,
         "halftime_home": 1, "halftime_away": 0}
    m.update(over)
    return m


def test_kickoff_dalla_partita_non_dall_istantanea_di_engine_signals():
    dec, pred = mes._build(_es(), _match())
    assert pred["kickoff"] == "2026-09-25T23:00:00+00:00"
    assert dec["kickoff"] == "2026-09-25T23:00:00+00:00"
    # e la riga e' settlata sulla partita giusta (niente "settled nel futuro")
    assert pred["settled"] is True and pred["hit"] is True


def test_senza_partita_resta_l_istantanea_di_engine_signals():
    dec, pred = mes._build(_es(), None)
    assert pred["kickoff"] == "2026-09-26T20:00:00+00:00"
    assert dec["kickoff"] == "2026-09-26T20:00:00+00:00"
    assert pred["settled"] is False


def test_partita_senza_data_resta_l_istantanea():
    dec, pred = mes._build(_es(), _match(fixture_date=None))
    assert pred["kickoff"] == "2026-09-26T20:00:00+00:00"


def test_la_lettura_di_matches_porta_la_data_della_partita():
    """_fetch_matches deve leggere fixture_date (prima non la leggeva)."""
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
            assert name == "matches"
            return _Q(self.log)

    db = _DB()
    out = mes._fetch_matches(db, [1499655])
    assert "fixture_date" in [c.strip() for c in db.log[0].split(",")]
    assert out[1499655]["fixture_date"] == "2026-09-25T23:00:00+00:00"
