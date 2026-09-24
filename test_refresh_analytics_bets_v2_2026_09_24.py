"""test_refresh_analytics_bets_v2_2026_09_24.py -- contratto della RPC v2 di
refresh_analytics_bets_range (migrations/refresh_analytics_bets_range_v2_2026-09-24.sql)
e del client refresh_analytics_bets.py.

Nessun Postgres locale: il SQL si verifica come TESTO contro il v1
(migrations/analytics_strategy.sql): stessa firma, stesse aggregazioni, stesse
colonne nello stesso ordine, stessa mappatura delle quote; in piu' i pezzi nuovi
(temp table con PK, statement_timeout/lock_timeout sulla funzione, nessun
fixture_date, un solo sottoselect sui kickoff). L'esecuzione vera e il confronto
riga per riga li fa il coordinatore sul DB (query nel referto).

Il client si verifica con il finto PostgREST di test_actions_pipeline_paginazione
(errori = postgrest.exceptions.APIError col dict reale).
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import refresh_analytics_bets as rab
from test_actions_pipeline_paginazione import FakeDB, api_error, err_57014

_QUI = os.path.dirname(os.path.abspath(__file__))
_V2 = os.path.join(_QUI, "migrations", "refresh_analytics_bets_range_v2_2026-09-24.sql")
_V1 = os.path.join(_QUI, "migrations", "analytics_strategy.sql")


def _leggi(p: str) -> str:
    with open(p, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def _senza_commenti(sql: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", r) for r in sql.split("\n"))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _tra(sql: str, inizio: str, fine: str) -> str:
    i = sql.index(inizio)
    j = sql.index(fine, i + len(inizio))
    return _norm(sql[i:j + len(fine)])


def _funzione(sql: str, nome: str) -> str:
    """Testo di `create or replace function public.<nome>(` fino al `$fn$;` finale."""
    i = sql.index(f"create or replace function public.{nome}(")
    j = sql.index("$fn$;", sql.index("$fn$", sql.index("as $fn$", i) + 7))
    return sql[i:j + 5]


V2 = _senza_commenti(_leggi(_V2))
V1 = _senza_commenti(_leggi(_V1))
SCALARE = _funzione(V2, "refresh_analytics_bets_range")
DIAG = _funzione(V2, "refresh_analytics_bets_range_diag")


# ------------------------------------------------------------------ firma
def test_stessa_firma_e_stesso_tipo_ritornato_del_v1():
    assert "create or replace function public.refresh_analytics_bets_range(p_from date, p_to date)\nreturns integer" in SCALARE
    assert "create or replace function public.refresh_analytics_bets_range(p_from date, p_to date)\nreturns integer" in V1


@pytest.mark.parametrize("corpo", ["SCALARE", "DIAG"])
def test_security_definer_search_path_e_timeout_sulla_funzione(corpo):
    f = globals()[corpo]
    testa = f[:f.index("as $fn$")]
    assert "security definer" in testa
    assert "set search_path = public" in testa
    assert "set statement_timeout = '600s'" in testa
    assert "set lock_timeout = '30s'" in testa
    assert "statement_timeout = 0" not in testa


def test_nessuna_funzione_v2_senza_limite():
    # nessun `statement_timeout = 0` in codice eseguibile del v2
    assert not re.search(r"statement_timeout\s*=\s*0\b", V2)


def test_grant_invariati_e_diag_solo_service_role():
    for riga in ("revoke all on function public.refresh_analytics_bets_range(date, date) from public, anon;",
                 "grant execute on function public.refresh_analytics_bets_range(date, date) to authenticated, service_role;"):
        assert riga in V1 and riga in V2
    assert "grant execute on function public.refresh_analytics_bets_range_diag(date, date) to service_role;" in V2
    assert "revoke all on function public.refresh_analytics_bets_range_diag(date, date) from public, anon, authenticated;" in V2


# ------------------------------------------------------------------ temp table
def test_insieme_fixture_una_volta_in_temp_con_pk_on_commit_drop():
    assert re.search(r"create temp table _rab_fx \(fixture_id bigint primary key\) on commit drop;", DIAG)
    assert "analyze pg_temp._rab_fx;" in DIAG
    # il sottoselect sui kickoff compare UNA sola volta (v1: tre volte)
    assert len(re.findall(r"kickoff >= p_from and s\.kickoff < p_to|kickoff >= p_from and kickoff < p_to", DIAG)) == 1
    assert len(re.findall(r"kickoff >= p_from and kickoff < p_to", V1)) == 3
    # delete, dec e piv usano la temp
    assert "delete from public.analytics_bets b using pg_temp._rab_fx fx where b.fixture_id = fx.fixture_id;" in _norm(DIAG)
    assert "join pg_temp._rab_fx fx on fx.fixture_id = d.fixture_id" in DIAG
    assert "join pg_temp._rab_fx fx on fx.fixture_id = s.fixture_id" in DIAG


def test_temp_drop_if_exists_prima_di_create():
    """Due chiamate nella stessa transazione (diag + scalare dallo SQL editor)
    non devono fallire con 'relation already exists'."""
    for t in ("_rab_fx", "_rab_odds"):
        assert DIAG.index(f"drop table if exists pg_temp.{t};") < DIAG.index(f"create temp table {t}")


# ------------------------------------------------------------------ cache quote
def test_mai_fixture_date_sul_json():
    assert "fixture_date" not in DIAG
    assert "fixture_date" not in SCALARE
    assert "fixture_date" in V1          # il v1 la usava: il test sa distinguere


def test_cache_ricostruita_solo_per_i_fixture_cambiati():
    d = _norm(DIAG)
    assert "delete from public.book_odds_cache c using pg_temp._rab_odds o where c.fixture_id = o.fixture_id;" in d
    assert "from pg_temp._rab_odds o join public.fixture_predictions fp on fp.fixture_id = o.fixture_id" in d
    # impronta: updated_at + dimensione memorizzata (niente lettura del JSON)
    assert "f.fonte_updated_at is distinct from fp.updated_at" in d
    assert "f.fonte_bytes is distinct from pg_column_size(fp.raw_json_odds)" in d
    assert "f.fixture_id is null" in d
    # l'impronta si scrive nella stessa funzione, dopo l'insert della cache
    assert d.index("insert into public.book_odds_cache (") < d.index("insert into public.book_odds_cache_fonte")
    # raw_json_odds letto (unnest) UNA volta: un solo jsonb_array_elements sui bookmaker
    assert d.count("raw_json_odds->'bookmakers'") == 1


def test_mappatura_quote_identica_al_v1():
    a = "cross join lateral jsonb_array_elements(coalesce(bk->'bets','[]'::jsonb)) bet"
    fine = "group by fp.fixture_id, mm.market, mm.selection;"
    assert _tra(DIAG, a, fine).replace("where fp.raw_json_odds is not null and ", "where ") == _tra(V1, a, fine)


# ------------------------------------------------------------------ analytics_bets
def test_select_finale_identico_al_v1():
    a, fine = "select piv.fixture_id, piv.league_id", "left join public.fixture_predictions fp on fp.fixture_id=piv.fixture_id;"
    assert _tra(_norm(DIAG), a, fine) == _tra(_norm(V1), a, fine)


def test_aggregazioni_dec_e_piv_identiche_al_v1():
    for a, fine in (("select d.fixture_id, d.market, d.selection,", "from public.analytics_decisions d"),
                    ("s.fixture_id, max(s.league_id) as league_id", "from public.analytics_signals s")):
        assert _tra(_norm(DIAG), a, fine) == _tra(_norm(V1), a, fine)
    for g in ("group by d.fixture_id, d.market, d.selection", "group by s.fixture_id, s.market, s.selection"):
        assert g in DIAG and g in V1


def test_scalare_ritorna_le_righe_dell_insert_di_analytics_bets():
    s = _norm(SCALARE)
    assert "from public.refresh_analytics_bets_range_diag(p_from, p_to) d where d.fase = 'analytics_bets_insert';" in s
    assert "return coalesce(v_n, 0);" in s
    assert "fase := 'analytics_bets_insert'; righe := v_n;" in _norm(DIAG)


def test_controllo_del_tempo_fra_le_fasi_solleva_57014():
    assert DIAG.count("using errcode = '57014'") >= 2
    assert "v_max constant interval := interval '600 seconds';" in _norm(DIAG)


def test_indice_league_id_id_concurrently():
    sql = _senza_commenti(_leggi(os.path.join(_QUI, "migrations", "analytics_signals_idx_league_id_2026-09-24.sql")))
    assert _norm(sql) == ("create index concurrently if not exists idx_as_league_id_id "
                          "on public.analytics_signals (league_id, id);")


# ------------------------------------------------------------------ client
def test_timeout_client_660_maggiore_del_server():
    assert rab._HTTP_TIMEOUT == 660.0
    assert "set statement_timeout = '600s'" in SCALARE
    assert rab._HTTP_TIMEOUT > 600.0


def test_57014_del_server_non_si_ritenta(capsys):
    db = FakeDB()
    n = {"c": 0}

    def impl(d, p):
        n["c"] += 1
        raise err_57014()

    db.rpc_impl[rab._RPC] = impl
    ok, righe = rab.rinfresca_finestra(db, date(2026, 9, 20), date(2026, 9, 21))
    assert ok is False and righe == 0
    assert n["c"] == 1                                   # UNA chiamata, nessun retry
    assert "statement_timeout del SERVER" in capsys.readouterr().out
    assert rab._timeout_server(err_57014()) and not rab._is_transient(err_57014())


def test_read_timeout_del_client_non_si_ritenta():
    db = FakeDB()
    n = {"c": 0}

    def impl(d, p):
        n["c"] += 1
        raise httpx.ReadTimeout("timed out")

    db.rpc_impl[rab._RPC] = impl
    assert rab.rinfresca_finestra(db, date(2026, 9, 20), date(2026, 9, 21)) == (False, 0)
    assert n["c"] == 1


def test_lock_timeout_55P03_resta_ritentabile():
    db = FakeDB()
    n = {"c": 0}

    def impl(d, p):
        n["c"] += 1
        if n["c"] == 1:
            raise api_error("55P03", "canceling statement due to lock timeout")
        return 9

    db.rpc_impl[rab._RPC] = impl
    assert rab.rinfresca_finestra(db, date(2026, 9, 20), date(2026, 9, 21)) == (True, 9)
    assert n["c"] == 2


def test_main_una_finestra_in_57014_exit_non_zero_e_le_altre_girano(monkeypatch):
    db = FakeDB()
    chiamate = []
    oggi = datetime.now(timezone.utc).date()
    cattiva = (oggi - timedelta(days=1)).isoformat()

    def impl(d, p):
        chiamate.append(p["p_from"])
        if p["p_from"] == cattiva:
            raise err_57014()
        return 4

    db.rpc_impl[rab._RPC] = impl
    monkeypatch.setattr(rab, "get_supabase_client", lambda: db)
    monkeypatch.setattr(rab, "_PAUSA", 0)
    monkeypatch.setattr(sys, "argv", ["refresh_analytics_bets.py", "--days", "3"])
    with pytest.raises(SystemExit) as ex:
        rab.main()
    assert ex.value.code != 0 and cattiva in str(ex.value.code)
    assert len(chiamate) == 5 and chiamate.count(cattiva) == 1   # 5 giorni, nessun retry
    assert db.postgrest.session.timeout.read == 660.0
