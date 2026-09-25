"""league_orchestrator: tolto il refresh della MV a fine corsa (25/09/2026, ordine utente).

Prima: backfill_full_league chiamava refresh_coverage_mv() a fine corsa (non
dry-run), che faceva rpc("refresh_api_coverage_by_season_v2_mv", {}). Quella
RPC va in timeout 57014 e nessuno nel repo legge quella MV (unico riferimento
era proprio questa chiamata). Rimossi la funzione e la chiamata; resta un
commento di 2 righe su dove si potrebbe riprendere in futuro (migrazione).

Riusa l'infrastruttura finta gia' certificata in
test_backfill_automatico_2026_09_25.py (FintoDB/FintoServer/FintoClient/
coverage/quota_per): niente DB/rete vera, stessi finti col contratto del vero
client supabase-py (table/rpc).
"""
from __future__ import annotations

import io
import os
import sys
from contextlib import redirect_stdout

import pytest

os.environ["SUPABASE_URL"] = "http://127.0.0.1:9"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "x"
os.environ["SUPABASE_KEY"] = "x"
os.environ["API_FOOTBALL_KEY"] = "x"

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import league_orchestrator as lo  # noqa: E402
import per_fixture_backfill as pfb  # noqa: E402
import fixtures_backfill  # noqa: E402
import season_gaps as sg  # noqa: E402
import season_aggregates as sa  # noqa: E402
import test_backfill_automatico_2026_09_25 as tba  # noqa: E402


@pytest.fixture
def mondo(monkeypatch):
    db = tba.FintoDB()
    server = tba.FintoServer()
    monkeypatch.setattr(pfb, "get_supabase", lambda: db)
    monkeypatch.setattr(pfb.time, "sleep", lambda s: None)
    monkeypatch.setattr(fixtures_backfill, "get_supabase_client", lambda: db)
    monkeypatch.setattr(fixtures_backfill, "APIFootballClient", lambda: tba.FintoClient(server))
    monkeypatch.setattr(fixtures_backfill.time, "sleep", lambda s: None)
    monkeypatch.setattr(lo, "get_supabase", lambda: db)
    monkeypatch.setattr(sg, "_oggi", lambda: tba.OGGI)
    monkeypatch.setattr(sa, "adesso", lambda: db.adesso)
    return db, server


def test_league_orchestrator_non_ha_piu_refresh_coverage_mv():
    """Guardia strutturale: la funzione e' stata tolta."""
    assert not hasattr(lo, "refresh_coverage_mv")


def _nomi_rpc(db: "tba.FintoDB") -> list:
    return [nome for nome, _params in db.rpc_chiamate]


def test_backfill_full_league_stagione_finita_non_chiama_refresh_mv(mondo):
    """Stagione passata, gia' piena -> zero chiamate API. Tra le RPC legittime del
    flusso (season_detail_gaps/season_gaps_summary/season_aggregates_summary, per
    calcolare lo stato) NON deve piu' comparire refresh_api_coverage_by_season_v2_mv
    (prima: chiamata sempre a fine corsa non-dry-run, anche senza nulla da fare)."""
    db, server = mondo
    db.t["api_coverage_by_season"].append(tba.coverage(135, 2024, current=False, fine="2025-05-25"))
    db.partita(21, 135, 2024, giorni_fa=400)
    for tab in tba.TABELLE:
        db.dettaglio(tab, 21, 135, 2024)
    q = tba.quota_per(db, server, tba.FintoClient(server))

    lo.backfill_full_league(135, sb=db, quota=q, client=tba.FintoClient(server), oggi=tba.OGGI,
                            stampa=lambda s: None)

    assert server.chiamate == []
    assert "refresh_api_coverage_by_season_v2_mv" not in _nomi_rpc(db)


def test_backfill_full_league_con_lavoro_vero_non_chiama_refresh_mv(mondo):
    """Stagione con buchi reali (lavoro fatto, chiamate API vere) -> ancora nessuna
    RPC di refresh a fine corsa: non deve scattare nemmeno quando la corsa e' 'piena'
    (era proprio quel caso, il piu' frequente, a far scattare il timeout 57014)."""
    db, server = mondo
    db.t["api_coverage_by_season"].append(tba.coverage(135, 2026))
    for fid in (11, 12):
        db.partita(fid, 135, 2026)
    server.fixtures_stagione[(135, 2026)] = [
        tba.fixture_api(11, 135, 2026), tba.fixture_api(12, 135, 2026),
    ]
    client = tba.FintoClient(server)
    q = tba.quota_per(db, server, client)
    out = io.StringIO()
    with redirect_stdout(out):
        r = lo.backfill_full_league(135, sb=db, quota=q, client=client, oggi=tba.OGGI)

    assert r["chiamate"] > 0            # ha davvero lavorato (non e' un giro a vuoto)
    assert "refresh_api_coverage_by_season_v2_mv" not in _nomi_rpc(db)
