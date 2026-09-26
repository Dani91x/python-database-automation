"""KO9 del referto di fase 3 (26/09/2026): TacticAI "Esito reale (90')" mai valorizzato.

tactical_engine/serving.py scriveva SEMPRE ``actual: None`` (payload delle partite NON
giocate) e nessun processo di produzione lo aggiornava a partita finita: 233/5.976
payload con l'esito, il blocco "Esito reale (90')" di TacticalEnginePanel non compariva
mai sulle previsioni giornaliere. Ora ``run_esiti_reali`` (stesso job giornaliero,
today_predictions_backfill.py, subito dopo il motore) scrive ``actual`` e
``predicted_correct_1x2`` sui payload delle partite FINITE degli ultimi giorni, con la
stessa forma di tactical_engine/generate_predictions.py:
``{"home_goals": int, "away_goals": int, "outcome": "1"|"X"|"2"}``.

Il client e' il FINTO di test_serving.py (stesse chiavi/tipi del vero): righe di
fixture_predictions (result_status_short, result_home/away_goals, tactical_engine_json)
e di matches (status_short, goals_*, fulltime_*).
"""
from __future__ import annotations

import copy
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tactical_engine import serving  # noqa: E402
from tactical_engine.tests.test_serving import FakeSupabase  # noqa: E402

OGGI = datetime(2026, 9, 26, tzinfo=timezone.utc)


def _payload(home: float, draw: float, away: float) -> dict:
    """Payload come lo scrive serving._build_payload (chiavi usate qui + actual NULL)."""
    return {
        "engine_version": serving.ENGINE_VERSION, "fixture_id": 0, "status": None,
        "markets": {"home": home, "draw": draw, "away": away, "over_2_5": 0.5},
        "top_scores": [{"h": 1, "a": 0, "p": 0.12}],
        "actual": None, "predicted_correct_1x2": None,
    }


def _fp(fid: int, quando: datetime, stato, gh=None, ga=None, payload=None) -> dict:
    p = copy.deepcopy(payload)
    if p is not None:
        p["fixture_id"] = fid
    return {
        "fixture_id": fid, "league_id": 358, "league_name": "First Division", "season_year": 2026,
        "fixture_date": quando.isoformat(), "home_team_id": 1, "home_team_name": "Cobh",
        "away_team_id": 2, "away_team_name": "Athlone", "status": "ok",
        "result_status_short": stato, "result_home_goals": gh, "result_away_goals": ga,
        "tactical_engine_json": p,
    }


def _m(fid: int, stato: str, gh, ga, fh, fa) -> dict:
    return {"fixture_id": fid, "league_id": 358, "status_short": stato,
            "goals_home": gh, "goals_away": ga, "fulltime_home": fh, "fulltime_away": fa,
            "fixture_date": (OGGI - timedelta(days=1)).isoformat()}


def _mondo() -> FakeSupabase:
    ieri = OGGI - timedelta(days=1)
    fp = [
        # A del referto: finita 3-3, previsione 1 (casa 55 %) -> azzeccato = False
        _fp(1492980, ieri + timedelta(hours=18), "FT", 3, 3, _payload(0.5465, 0.25, 0.2035)),
        # finita 2-1 ai supplementari: l'esito a 90' e' fulltime 1-1 (NON goals 2-1)
        _fp(1001, ieri + timedelta(hours=20), "AET", 2, 1, _payload(0.2, 0.5, 0.3)),
        # finita FT ma senza riga in matches: si usa result_* (90' per FT)
        _fp(1002, ieri + timedelta(hours=12), "FT", 0, 2, _payload(0.3, 0.3, 0.4)),
        # finita ma senza payload TacticAI: niente da scrivere
        _fp(1003, ieri + timedelta(hours=14), "FT", 1, 0, None),
        # non ancora giocata: niente
        _fp(1004, OGGI + timedelta(hours=18), None, None, None, _payload(0.4, 0.3, 0.3)),
        # esito gia' scritto: non si riscrive
        _fp(1005, ieri + timedelta(hours=10), "FT", 1, 0, dict(_payload(0.6, 0.2, 0.2),
            actual={"home_goals": 1, "away_goals": 0, "outcome": "1"}, predicted_correct_1x2=True)),
        # PEN senza fulltime in matches: esito a 90' ignoto -> NON si inventa
        _fp(1006, ieri + timedelta(hours=21), "PEN", 3, 3, _payload(0.3, 0.4, 0.3)),
        # fuori finestra (10 giorni fa): non letta
        _fp(1007, OGGI - timedelta(days=10), "FT", 2, 0, _payload(0.5, 0.3, 0.2)),
    ]
    matches = [
        _m(1492980, "FT", 3, 3, 3, 3),
        _m(1001, "AET", 2, 1, 1, 1),
        _m(1003, "FT", 1, 0, 1, 0),
        _m(1006, "PEN", 3, 3, None, None),
        _m(1007, "FT", 2, 0, 2, 0),
    ]
    return FakeSupabase({"fixture_predictions": fp, "matches": matches})


@pytest.fixture(autouse=True)
def _mai_db_vero(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "x")
    monkeypatch.setenv("SUPABASE_KEY", "x")


def _payload_di(db: FakeSupabase, fid: int):
    return next(r for r in db.tables["fixture_predictions"] if r["fixture_id"] == fid)["tactical_engine_json"]


def test_esito_reale_scritto_sulle_partite_finite(monkeypatch):
    db = _mondo()
    monkeypatch.setattr(serving, "get_supabase_client", lambda: db)
    prima_1005 = copy.deepcopy(_payload_di(db, 1005))

    res = serving.run_esiti_reali("2026-09-26")

    a = _payload_di(db, 1492980)
    assert a["actual"] == {"home_goals": 3, "away_goals": 3, "outcome": "X"}
    assert a["predicted_correct_1x2"] is False          # previsto 1 (0.5465), finita X
    # il resto del payload e' intatto
    assert a["markets"]["home"] == 0.5465 and a["top_scores"] == [{"h": 1, "a": 0, "p": 0.12}]
    # AET: esito a 90' da fulltime (1-1 -> X), non dai gol dopo i supplementari
    assert _payload_di(db, 1001)["actual"] == {"home_goals": 1, "away_goals": 1, "outcome": "X"}
    assert _payload_di(db, 1001)["predicted_correct_1x2"] is True
    # FT senza matches: result_* (0-2 -> 2), previsto 2 (0.4)
    assert _payload_di(db, 1002)["actual"] == {"home_goals": 0, "away_goals": 2, "outcome": "2"}
    assert _payload_di(db, 1002)["predicted_correct_1x2"] is True
    # nessun payload inventato, nessuna partita futura toccata, esito gia' presente invariato
    assert _payload_di(db, 1003) is None
    assert _payload_di(db, 1004)["actual"] is None
    assert _payload_di(db, 1005) == prima_1005
    # PEN senza fulltime: esito a 90' ignoto, NON scritto (i gol 3-3 includono i supplementari)
    assert _payload_di(db, 1006)["actual"] is None
    # fuori finestra
    assert _payload_di(db, 1007)["actual"] is None
    assert res == {"finite": 6, "scritti": 3, "gia_presenti": 1, "senza_payload": 1, "senza_esito_90": 1, "errori": 0}


def test_idempotente_secondo_giro_non_scrive(monkeypatch):
    db = _mondo()
    monkeypatch.setattr(serving, "get_supabase_client", lambda: db)
    serving.run_esiti_reali("2026-09-26")
    n_update = sum(1 for q in db.calls if q.update_payload is not None)
    res2 = serving.run_esiti_reali("2026-09-26")
    assert res2["scritti"] == 0 and res2["gia_presenti"] == 4
    assert sum(1 for q in db.calls if q.update_payload is not None) == n_update


def test_scrive_solo_la_colonna_del_motore(monkeypatch):
    db = _mondo()
    monkeypatch.setattr(serving, "get_supabase_client", lambda: db)
    serving.run_esiti_reali("2026-09-26")
    updates = [q for q in db.calls if q.update_payload is not None]
    assert updates and all(set(q.update_payload) == {"tactical_engine_json"} for q in updates)
    assert all(q.table == "fixture_predictions" for q in updates)
    # un UPDATE per fixture_id, filtrato per chiave
    assert all(("eq", "fixture_id", q.filters[0][2]) == q.filters[0] for q in updates)


def test_lettura_paginata_con_server_che_tronca(monkeypatch):
    """La lista delle finite si legge a pagine keyset: con max_rows=2 le vede tutte."""
    db = _mondo()
    db.max_rows = 2
    monkeypatch.setattr(serving, "get_supabase_client", lambda: db)
    res = serving.run_esiti_reali("2026-09-26")
    assert res["finite"] == 6 and res["scritti"] == 3


def test_il_job_giornaliero_chiama_gli_esiti_dopo_il_motore():
    """Aggancio nello STESSO job (today_predictions_backfill.run_for_date), dopo il
    motore TacticAI e in un try separato (non-fatale, non blocca il motore)."""
    percorso = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            "Prediction", "today_predictions_backfill.py")
    src = open(percorso, encoding="utf-8").read()
    i_motore = src.index("_te_res = _tactical_run(target_date)")
    i_esiti = src.index("_tactical_esiti(target_date)")
    assert "from tactical_engine.serving import run_esiti_reali as _tactical_esiti" in src
    assert i_esiti > i_motore
    # try separato: fra il motore e gli esiti c'e' un nuovo "try:"
    assert "try:" in src[i_motore:i_esiti]
