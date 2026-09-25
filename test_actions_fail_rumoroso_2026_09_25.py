"""Action GitHub: niente piu' "success vuoti" (25/09/2026).

Nessun DB, nessuna rete. Si dimostra che:
- daily_yesterday_backfill: una risposta VUOTA/in errore dell'API /fixtures
  (APIFootballClient.call ritorna {} su QUALUNQUE errore) fa uscire con
  exit != 0 invece di chiudere verde; con fixture vere il flusso resta quello
  di prima (nessuna uscita anticipata).
- leagues_mapper: /leagues vuoto, lettura delle coppie esistenti fallita o
  batch in errore NON previsto -> exit != 0; duplicati residui (gia' tollerati
  dal codice) e "DB gia' allineato" -> uscita pulita.

I finti hanno le STESSE chiavi e gli stessi tipi del vero:
- risposta /fixtures e /leagues di API-Football: {"response": [...]}, con
  fixture {"fixture": {"id", "status": {"short"}}, "league": {"id", "season"}}
  e lega {"league": {"id", "name"}, "country": {"name"}, "seasons": [{"year",
  "start", "end", "current", "coverage": {"fixtures": {...}, ...}}]};
- client supabase-py: table(..).select(..).range(..).execute() -> oggetto con
  .data (lista di dict); table(..).upsert(chunk).execute().
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

import pytest

# Sandbox: mai il DB vero (load_dotenv non sovrascrive variabili gia' presenti).
os.environ["SUPABASE_URL"] = "http://127.0.0.1:9"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "x"
os.environ["SUPABASE_KEY"] = "x"
os.environ["API_FOOTBALL_KEY"] = "x"

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import daily_yesterday_backfill as dyb  # noqa: E402
import leagues_mapper as lm  # noqa: E402


# ---------------------------------------------------------------------------
# finti
# ---------------------------------------------------------------------------
class FintoApi:
    """APIFootballClient: call(endpoint, params) -> dict ({} su errore)."""

    def __init__(self, risposte: Dict[str, Dict[str, Any]]) -> None:
        self.risposte = risposte
        self.chiamate: List[tuple] = []

    def call(self, endpoint: str, params: Optional[Dict[str, Any]] = None,
             max_retries: int = 3) -> Dict[str, Any]:
        self.chiamate.append((endpoint, params))
        return self.risposte.get(endpoint, {})

    def get_leagues(self) -> Dict[str, Any]:
        return self.call("/leagues")


def fixture_api(fid: int, lega: int, stagione: int, stato: str = "FT") -> Dict[str, Any]:
    return {"fixture": {"id": fid, "date": "2026-09-24T19:00:00+00:00",
                        "status": {"short": stato, "long": "Match Finished"}},
            "league": {"id": lega, "season": stagione, "name": "L", "country": "C"},
            "teams": {"home": {"id": 1, "name": "A"}, "away": {"id": 2, "name": "B"}},
            "goals": {"home": 1, "away": 0},
            "score": {"halftime": {"home": 0, "away": 0}}}


def lega_api(lid: int, anni: List[int]) -> Dict[str, Any]:
    return {"league": {"id": lid, "name": f"Lega {lid}", "type": "League"},
            "country": {"name": "Italy", "code": "IT"},
            "seasons": [{"year": a, "start": f"{a}-08-01", "end": f"{a + 1}-05-31",
                         "current": a == anni[-1],
                         "coverage": {"fixtures": {"events": True, "lineups": True,
                                                   "statistics_fixtures": True,
                                                   "statistics_players": False},
                                      "standings": True, "players": True,
                                      "top_scorers": True, "top_assists": True,
                                      "top_cards": True, "injuries": False,
                                      "predictions": True, "odds": True}}
                        for a in anni]}


class _Risposta:
    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.data = data


class _Query:
    def __init__(self, sb: "FintoSupabase", tabella: str) -> None:
        self.sb = sb
        self.tabella = tabella
        self.op = "select"
        self.payload: Any = None

    def select(self, colonne: str) -> "_Query":
        self.op = "select"
        return self

    # 25/09/2026 (backfill automatico): il mapper ora legge a pagine ordinate
    # (order + range veri) e aggiorna le righe vive (update().eq().eq()).
    def order(self, colonna: str, desc: bool = False) -> "_Query":
        return self

    def range(self, a: int, b: int) -> "_Query":
        self.intervallo = (a, b)
        return self

    def upsert(self, righe: List[Dict[str, Any]]) -> "_Query":
        self.op = "upsert"
        self.payload = righe
        return self

    def update(self, payload: Dict[str, Any]) -> "_Query":
        self.op = "update"
        self.payload = payload
        return self

    def eq(self, colonna: str, valore: Any) -> "_Query":
        return self

    def execute(self) -> _Risposta:
        if self.op == "select":
            if self.sb.errore_lettura:
                raise RuntimeError("{'message': 'canceling statement due to statement timeout', 'code': '57014'}")
            a, b = getattr(self, "intervallo", (0, 999))
            return _Risposta(list(self.sb.righe)[a:b + 1])
        if self.sb.errore_upsert:
            raise RuntimeError(self.sb.errore_upsert)
        if self.op == "update":
            self.sb.aggiornate.append(self.payload)
            return _Risposta([])
        self.sb.upsertate.extend(self.payload)
        return _Risposta([])


class FintoSupabase:
    def __init__(self, righe: Optional[List[Dict[str, Any]]] = None) -> None:
        self.righe = righe or []
        self.errore_lettura = False
        self.errore_upsert: Optional[str] = None
        self.upsertate: List[Dict[str, Any]] = []
        self.aggiornate: List[Dict[str, Any]] = []

    def table(self, nome: str) -> _Query:
        assert nome == "api_coverage_by_season"
        return _Query(self, nome)


# ---------------------------------------------------------------------------
# daily_yesterday_backfill
# ---------------------------------------------------------------------------
@pytest.fixture
def daily(monkeypatch):
    stato: Dict[str, Any] = {"upsert_input": None, "per_fixture": None}

    def finto_upsert(fixtures_json):
        stato["upsert_input"] = fixtures_json
        return [{"fixture_id": 10, "league_id": 135, "season_year": 2026}]

    def finto_per_fixture(api, keys):
        stato["per_fixture"] = keys
        return {(135, 2026)}

    monkeypatch.setattr(dyb, "upsert_matches_from_fixtures_finished_only", finto_upsert)
    monkeypatch.setattr(dyb, "run_per_fixture_for_date", finto_per_fixture)
    return stato


@pytest.mark.parametrize("risposta", [{}, {"response": []}, {"response": None}])
def test_daily_api_vuota_o_in_errore_esce_rosso(monkeypatch, daily, risposta):
    monkeypatch.setattr(dyb, "APIFootballClient", lambda: FintoApi({"/fixtures": risposta}))
    with pytest.raises(SystemExit) as ex:
        dyb.run_daily_backfill_for_date("2026-09-24")
    assert ex.value.code not in (0, None)
    assert "2026-09-24" in str(ex.value.code)
    assert daily["upsert_input"] is None          # nulla scritto a valle


def test_daily_con_fixture_vere_fa_il_lavoro_come_prima(monkeypatch, daily):
    api = FintoApi({"/fixtures": {"response": [fixture_api(10, 135, 2026)]}})
    monkeypatch.setattr(dyb, "APIFootballClient", lambda: api)
    dyb.run_daily_backfill_for_date("2026-09-24")    # nessuna eccezione
    assert api.chiamate == [("/fixtures", {"date": "2026-09-24"})]
    assert daily["upsert_input"] == [fixture_api(10, 135, 2026)]
    assert daily["per_fixture"] == [{"fixture_id": 10, "league_id": 135, "season_year": 2026}]


# ---------------------------------------------------------------------------
# leagues_mapper
# ---------------------------------------------------------------------------
def _mapper(monkeypatch, api_leagues: Dict[str, Any], sb: FintoSupabase) -> None:
    monkeypatch.setattr(lm, "APIFootballClient", lambda: FintoApi({"/leagues": api_leagues}))
    monkeypatch.setattr(lm, "get_supabase_client", lambda: sb)
    monkeypatch.setattr(lm.time, "sleep", lambda s: None)


@pytest.mark.parametrize("risposta", [{}, {"response": []}])
def test_mapper_leagues_vuoto_esce_rosso(monkeypatch, risposta):
    sb = FintoSupabase()
    _mapper(monkeypatch, risposta, sb)
    with pytest.raises(SystemExit) as ex:
        lm.run_full_leagues_backfill_mapping()
    assert ex.value.code not in (0, None)
    assert sb.upsertate == []


def test_mapper_lettura_coppie_fallita_esce_rosso_senza_scrivere(monkeypatch):
    sb = FintoSupabase()
    sb.errore_lettura = True
    _mapper(monkeypatch, {"response": [lega_api(135, [2025, 2026])]}, sb)
    with pytest.raises(RuntimeError):
        lm.run_full_leagues_backfill_mapping()
    assert sb.upsertate == []                      # prima: tentava di reinserire TUTTO


def test_mapper_batch_in_errore_non_previsto_esce_rosso(monkeypatch):
    sb = FintoSupabase()
    sb.errore_upsert = "{'message': 'permission denied for table api_coverage_by_season', 'code': '42501'}"
    _mapper(monkeypatch, {"response": [lega_api(135, [2026])]}, sb)
    with pytest.raises(SystemExit) as ex:
        lm.run_full_leagues_backfill_mapping()
    assert ex.value.code not in (0, None)
    assert "1 batch" in str(ex.value.code)


def test_mapper_duplicato_residuo_resta_tollerato(monkeypatch):
    sb = FintoSupabase()
    sb.errore_upsert = "duplicate key value violates unique constraint \"api_coverage_by_season_pkey\""
    _mapper(monkeypatch, {"response": [lega_api(135, [2026])]}, sb)
    lm.run_full_leagues_backfill_mapping()           # nessuna uscita rossa


def test_mapper_inserisce_solo_le_mancanti_ed_esce_pulito(monkeypatch):
    sb = FintoSupabase([{"league_id": 135, "season_year": 2025}])
    _mapper(monkeypatch, {"response": [lega_api(135, [2025, 2026])]}, sb)
    lm.run_full_leagues_backfill_mapping()
    assert [(r["league_id"], r["season_year"]) for r in sb.upsertate] == [(135, 2026)]


def test_mapper_db_gia_allineato_esce_pulito(monkeypatch):
    # 25/09/2026: la riga del DB ha ora le colonne VERE (come le scrive il mapper):
    # "allineato" significa stessi flag/date/current dell'API. Prima il finto aveva
    # solo (league_id, season_year) perche' il mapper non confrontava nulla.
    riga = lm.map_leagues_to_coverage_rows({"response": [lega_api(135, [2026])]})[0]
    sb = FintoSupabase([riga])
    _mapper(monkeypatch, {"response": [lega_api(135, [2026])]}, sb)
    lm.run_full_leagues_backfill_mapping()
    assert sb.upsertate == []
    assert sb.aggiornate == []
