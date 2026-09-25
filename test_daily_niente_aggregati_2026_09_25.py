"""Daily: il ramo morto degli aggregati e' stato tolto (25/09/2026, ordine utente).

daily_yesterday_backfill.run_aggregates_for_seasons chiamava
backfill_standings_for_league_season/top_*/injuries leggendo
coverage.get("standings") ecc. da get_coverage_for_season
(per_fixture_backfill.py), che pero' ritorna SOLO i 5 flag per-partita
(events, lineups, team_stats, player_stats, odds): coverage.get("standings")
era sempre None -> il ramo non scattava mai (log Daily 25/09: 0 chiamate a
standings/injuries/top_*). Gli aggregati li fa il recupero giornaliero
(seasons_catchup.py + season_aggregates.py, commit 9cbfe76).

Qui si dimostra che l'intero orchestratore run_daily_backfill_for_date, con
una fixture di ieri, non chiama MAI le funzioni di aggregato: i finti sono
messi sul NAMESPACE di daily_yesterday_backfill (non sul modulo origine),
cosi' catturano anche un `from standings_backfill import
backfill_standings_for_league_season` reintrodotto in testa al file - Python
risolve i nomi globali nel __dict__ del modulo a ogni chiamata, non al
momento dell'import.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

# Sandbox: mai il DB vero.
os.environ["SUPABASE_URL"] = "http://127.0.0.1:9"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "x"
os.environ["SUPABASE_KEY"] = "x"
os.environ["API_FOOTBALL_KEY"] = "x"

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import daily_yesterday_backfill as dyb  # noqa: E402


class FintoApi:
    """APIFootballClient: call(endpoint, params) -> dict."""

    def __init__(self, risposte: Dict[str, Dict[str, Any]]) -> None:
        self.risposte = risposte
        self.chiamate: List[tuple] = []

    def call(self, endpoint: str, params: Optional[Dict[str, Any]] = None,
             max_retries: int = 3) -> Dict[str, Any]:
        self.chiamate.append((endpoint, params))
        return self.risposte.get(endpoint, {})


def fixture_api(fid: int, lega: int, stagione: int, stato: str = "FT") -> Dict[str, Any]:
    return {"fixture": {"id": fid, "date": "2026-09-24T19:00:00+00:00",
                        "status": {"short": stato, "long": "Match Finished"}},
            "league": {"id": lega, "season": stagione, "name": "L", "country": "C"},
            "teams": {"home": {"id": 1, "name": "A"}, "away": {"id": 2, "name": "B"}},
            "goals": {"home": 1, "away": 0},
            "score": {"halftime": {"home": 0, "away": 0}}}


AGGREGATI = (
    "backfill_standings_for_league_season",
    "backfill_top_scorers_for_league_season",
    "backfill_top_assists_for_league_season",
    "backfill_top_cards_for_league_season",
    "backfill_injuries_for_league_season",
)


def test_dyb_non_importa_piu_le_funzioni_di_aggregato():
    """Guardia strutturale: gli import in testa al file sono stati tolti."""
    for nome in AGGREGATI + ("run_aggregates_for_seasons",):
        assert not hasattr(dyb, nome), f"{nome} e' tornato in daily_yesterday_backfill.py"


def test_daily_con_fixture_di_ieri_non_chiama_mai_gli_aggregati(monkeypatch):
    chiamate: List[str] = []

    def boom(nome: str):
        def _f(*args: Any, **kwargs: Any) -> None:
            chiamate.append(nome)
            raise AssertionError(f"{nome} chiamata dal Daily: ramo morto reintrodotto")
        return _f

    # Finti piazzati sul NAMESPACE di dyb (raising=False: oggi l'attributo non
    # esiste piu'). Se il ramo morto tornasse (anche come nuovo `from ... import`
    # in testa al file), la chiamata risolverebbe comunque questo nome, perche'
    # Python legge i globali del modulo a runtime, non al momento dell'import.
    for nome in AGGREGATI:
        monkeypatch.setattr(dyb, nome, boom(nome), raising=False)

    api = FintoApi({"/fixtures": {"response": [fixture_api(10, 135, 2026)]}})
    monkeypatch.setattr(dyb, "APIFootballClient", lambda: api)
    monkeypatch.setattr(
        dyb, "upsert_matches_from_fixtures_finished_only",
        lambda fixtures_json: [{"fixture_id": 10, "league_id": 135, "season_year": 2026}],
    )
    monkeypatch.setattr(dyb, "run_per_fixture_for_date", lambda api, keys: {(135, 2026)})

    dyb.run_daily_backfill_for_date("2026-09-24")  # nessuna eccezione

    assert chiamate == []
