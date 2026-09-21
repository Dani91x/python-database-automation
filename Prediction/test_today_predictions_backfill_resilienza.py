# Prediction/test_today_predictions_backfill_resilienza.py
"""Resilienza delle scritture di today_predictions_backfill (statement_timeout 57014).

Il run giornaliero moriva a meta': un solo 57014 sull'UPDATE delle odds risaliva
fino a main() e lasciava senza predizioni TUTTE le fixture successive (20/09).
Qui si verifica che:
  1. un 57014 sull'upsert a batch viene recuperato scendendo a blocchi piu'
     piccoli fino alla singola riga, senza perdere nessuna fixture;
  2. un 57014 sull'UPDATE delle odds viene ritentato e va a buon fine;
  3. un fallimento PERMANENTE su una fixture non ferma le altre e lascia una
     traccia esplicita (write_failures) + exit code != 0;
  4. senza errori la sequenza di chiamate al client e' IDENTICA a quella del
     codice originale (git HEAD): nessun cambio di semantica;
  5. gli errori logici (violazioni di vincoli) NON vengono ritentati.

Nessun accesso al DB vero: il client Supabase e' un finto in memoria.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from postgrest.exceptions import APIError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import Prediction.today_predictions_backfill as tpb  # noqa: E402


# ==============================================================
# Finti: identiche chiavi e tipi del vero
# ==============================================================

def api_error(code: str, message: str) -> APIError:
    """APIError di postgrest con le IDENTICHE chiavi del vero."""
    return APIError({"message": message, "code": code, "hint": None, "details": None})


def timeout_57014() -> APIError:
    return api_error("57014", "canceling statement due to statement timeout")


class FakeResponse:
    """Risposta PostgREST: espone .data come il vero (lista di dict)."""

    def __init__(self, data: Optional[List[Dict[str, Any]]]) -> None:
        self.data = data


class FakeQuery:
    """Builder PostgREST finto: ogni metodo ritorna self, execute() registra."""

    def __init__(self, client: "FakeSupabase", table: str) -> None:
        self._c = client
        self._table = table
        self._verb: Optional[str] = None
        self._payload: Any = None
        self._on_conflict: Optional[str] = None
        self._filters: List[Any] = []
        self._columns: Optional[str] = None
        self._single = False
        self._range: Optional[Any] = None

    # --- verbi
    def upsert(self, rows: Any, on_conflict: Optional[str] = None, **_kw: Any) -> "FakeQuery":
        self._verb = "upsert"
        self._payload = rows
        self._on_conflict = on_conflict
        return self

    def update(self, row: Any, **_kw: Any) -> "FakeQuery":
        self._verb = "update"
        self._payload = row
        return self

    def insert(self, rows: Any, **_kw: Any) -> "FakeQuery":
        self._verb = "insert"
        self._payload = rows
        return self

    def select(self, columns: str = "*", **_kw: Any) -> "FakeQuery":
        self._verb = "select"
        self._columns = columns
        return self

    # --- filtri
    def eq(self, col: str, val: Any) -> "FakeQuery":
        self._filters.append(("eq", col, val))
        return self

    def gte(self, col: str, val: Any) -> "FakeQuery":
        self._filters.append(("gte", col, val))
        return self

    def lt(self, col: str, val: Any) -> "FakeQuery":
        self._filters.append(("lt", col, val))
        return self

    def in_(self, col: str, vals: Any) -> "FakeQuery":
        self._filters.append(("in", col, tuple(vals)))
        return self

    def maybe_single(self) -> "FakeQuery":
        self._single = True
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        self._range = (start, end)
        return self

    # --- esecuzione
    def _descr(self) -> Dict[str, Any]:
        payload = self._payload
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = [payload]
        else:
            rows = []
        return {
            "table": self._table,
            "verb": self._verb,
            "on_conflict": self._on_conflict,
            "filters": tuple(self._filters),
            "columns": self._columns,
            "single": self._single,
            "range": self._range,
            # i VALORI variabili (updated_at) restano fuori: si confronta la
            # struttura, non l'istante in cui e' stata costruita la riga.
            "fixture_ids": tuple(r.get("fixture_id") for r in rows),
            "statuses": tuple(r.get("status") for r in rows),
            "row_keys": tuple(tuple(sorted(r.keys())) for r in rows),
        }

    def execute(self) -> Optional[FakeResponse]:
        descr = self._descr()
        exc = None
        if self._c.fail_policy is not None:
            exc = self._c.fail_policy(descr, self._c.attempts)
        self._c.attempts.append(descr)
        if exc is not None:
            self._c.failed.append(descr)
            raise exc
        self._c.executed.append(descr)
        dati = self._c.response_for(descr)
        if self._single and dati is None:
            # postgrest 2.28: maybe_single() su 0 righe ritorna None (l'APIError
            # "The result contains 0 rows" e' catturato dentro il builder).
            return None
        return FakeResponse(dati)


class FakeSupabase:
    """Client Supabase finto: registra tentativi ed esecuzioni riuscite."""

    def __init__(
        self,
        fail_policy: Any = None,
        select_data: Any = None,
        coverage_rows: Optional[Dict[Any, Optional[Dict[str, Any]]]] = None,
    ) -> None:
        self.fail_policy = fail_policy
        self.select_data = select_data if select_data is not None else []
        # {(league_id, season_year): {'predictions': bool, 'odds': bool}} oppure
        # None per "riga assente" (maybe_single -> None, come nel vero postgrest).
        self.coverage_rows = coverage_rows if coverage_rows is not None else {}
        self.attempts: List[Dict[str, Any]] = []   # ogni execute(), anche fallita
        self.executed: List[Dict[str, Any]] = []   # solo le riuscite
        self.failed: List[Dict[str, Any]] = []

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)

    def response_for(self, descr: Dict[str, Any]) -> Any:
        if descr["table"] == "api_coverage_by_season" and descr["verb"] == "select":
            chiave = tuple(v for (op, col, v) in descr["filters"] if op == "eq")
            return self.coverage_rows.get(chiave)
        if descr["verb"] == "select":
            return self.select_data
        if descr["verb"] == "update":
            fid = None
            for op, col, val in descr["filters"]:
                if op == "eq" and col == "fixture_id":
                    fid = val
            # Il vero PostgREST ritorna le righe aggiornate.
            return [{"fixture_id": fid}]
        return [{"fixture_id": f} for f in descr["fixture_ids"]]


# ==============================================================
# Dati finti con le colonne reali di fixture_predictions
# ==============================================================

def prediction_row(fixture_id: int, status: str = "ok") -> Dict[str, Any]:
    """Riga con le IDENTICHE chiavi/tipi prodotte dal loop principale."""
    return {
        "fixture_id": int(fixture_id),
        "league_id": 135,
        "league_name": "Serie A",
        "season_year": 2026,
        "fixture_date": "2026-09-20T18:00:00+00:00",
        "home_team_id": 492,
        "home_team_name": "Napoli",
        "away_team_id": 489,
        "away_team_name": "Milan",
        "status": status,
        "error_message": None,
        "raw_json": {"response": [{"predictions": {"advice": "Double chance"}}]},
        "flat_summary": {"prediction_advice": "Double chance"} if status == "ok" else None,
        "winner_team_id": 492 if status == "ok" else None,
        "winner_name": "Napoli" if status == "ok" else None,
        "winner_comment": None,
        "win_or_draw": True if status == "ok" else None,
        "advice": "Double chance" if status == "ok" else None,
        "percent_home": 45.0 if status == "ok" else None,
        "percent_draw": 30.0 if status == "ok" else None,
        "percent_away": 25.0 if status == "ok" else None,
        "under_over_line": "-1.5" if status == "ok" else None,
        "goals_home_line": "-1.5" if status == "ok" else None,
        "goals_away_line": "-1.5" if status == "ok" else None,
        "updated_at": "2026-09-20T12:00:00+00:00",
    }


def odds_row() -> Dict[str, Any]:
    return {
        "raw_json_odds": {"bookmakers": [{"id": 8, "bets": []}]},
        "updated_at": "2026-09-20T12:00:00+00:00",
    }


def analysis_row() -> Dict[str, Any]:
    return {
        "db_json_analisi": {"model": "poisson_xg_hybrid_dc", "markets": {}},
        "ht_predictions": {"is_elite": False},
        "updated_at": "2026-09-20T12:00:00+00:00",
    }


# ==============================================================
# Fixture comuni
# ==============================================================

@pytest.fixture(autouse=True)
def _ambiente_pulito(monkeypatch):
    """Nessuna attesa reale, registro e budget azzerati a ogni test."""
    monkeypatch.setattr(tpb, "_db_sleep", lambda _s: None)
    tpb._reset_failures()
    tpb._reset_retry_budget()
    yield
    tpb._reset_failures()
    tpb._reset_retry_budget()


def _writer_con_client(monkeypatch, client: FakeSupabase, chunk_size: int = 100):
    monkeypatch.setattr(tpb, "get_supabase_client", lambda: client)
    return tpb._DeferredWriter(chunk_size=chunk_size)


# ==============================================================
# 1) 57014 sul batch -> recupero a blocchi piu' piccoli
# ==============================================================

def test_57014_su_upsert_batch_recupera_scendendo_a_blocchi_piu_piccoli(monkeypatch):
    def policy(descr, _attempts):
        if descr["verb"] == "upsert" and len(descr["fixture_ids"]) > 1:
            return timeout_57014()
        return None

    client = FakeSupabase(fail_policy=policy)
    writer = _writer_con_client(monkeypatch, client)

    ids = [1001, 1002, 1003, 1004, 1005]
    for fid in ids:
        writer.queue_prediction(prediction_row(fid))
    writer.flush()

    scritte = [d for d in client.executed if d["verb"] == "upsert"]
    assert [d["fixture_ids"] for d in scritte] == [(f,) for f in ids], (
        "ogni fixture deve finire sul DB come riga singola"
    )
    assert all(d["on_conflict"] == "fixture_id" for d in scritte)
    assert tpb._RUN_FAILURES == [], "nessuna fixture persa"


def test_57014_su_upsert_batch_usa_i_blocchi_intermedi_non_solo_la_riga_singola(monkeypatch):
    """Il recupero deve DIMEZZARE, non passare subito a riga-per-riga."""
    def policy(descr, _attempts):
        if descr["verb"] == "upsert" and len(descr["fixture_ids"]) > 2:
            return timeout_57014()
        return None

    client = FakeSupabase(fail_policy=policy)
    writer = _writer_con_client(monkeypatch, client)

    ids = list(range(2001, 2009))  # 8 righe
    for fid in ids:
        writer.queue_prediction(prediction_row(fid))
    writer.flush()

    scritte = [d["fixture_ids"] for d in client.executed if d["verb"] == "upsert"]
    # 8 -> (4,4) -> (2,2,2,2): blocchi da 2, nessuna riga singola necessaria.
    assert scritte == [(2001, 2002), (2003, 2004), (2005, 2006), (2007, 2008)]
    assert tpb._RUN_FAILURES == []


def test_57014_transitorio_sul_batch_passa_al_secondo_tentativo(monkeypatch):
    """Un solo 57014: il batch stesso viene ritentato e passa, senza split."""
    stato = {"n": 0}

    def policy(descr, _attempts):
        if descr["verb"] == "upsert" and stato["n"] == 0:
            stato["n"] += 1
            return timeout_57014()
        return None

    client = FakeSupabase(fail_policy=policy)
    writer = _writer_con_client(monkeypatch, client)
    for fid in (3001, 3002, 3003):
        writer.queue_prediction(prediction_row(fid))
    writer.flush()

    scritte = [d["fixture_ids"] for d in client.executed if d["verb"] == "upsert"]
    assert scritte == [(3001, 3002, 3003)], "il batch intero deve ripassare al retry"
    assert len(client.failed) == 1
    assert tpb._RUN_FAILURES == []


# ==============================================================
# 2) 57014 sull'UPDATE delle odds -> ritenta e riesce
# ==============================================================

def test_57014_su_update_odds_viene_ritentato_e_riesce(monkeypatch):
    def policy(descr, attempts):
        if descr["verb"] != "update":
            return None
        if ("eq", "fixture_id", 4002) not in descr["filters"]:
            return None
        precedenti = sum(
            1 for a in attempts
            if a["verb"] == "update" and ("eq", "fixture_id", 4002) in a["filters"]
        )
        return timeout_57014() if precedenti < 2 else None

    client = FakeSupabase(fail_policy=policy)
    writer = _writer_con_client(monkeypatch, client)

    for fid in (4001, 4002, 4003):
        writer.queue_prediction(prediction_row(fid))
        writer.queue_odds(fid, odds_row())
    writer.flush()

    odds_ok = [
        d["filters"] for d in client.executed if d["verb"] == "update"
    ]
    assert odds_ok == [
        (("eq", "fixture_id", 4001),),
        (("eq", "fixture_id", 4002),),
        (("eq", "fixture_id", 4003),),
    ], "tutte e tre le odds devono essere scritte, nell'ordine di accodamento"
    assert len(client.failed) == 2, "due tentativi falliti prima del successo"
    assert tpb._RUN_FAILURES == []


# ==============================================================
# 3) Fallimento permanente: le altre fixture vengono comunque scritte
# ==============================================================

def test_fallimento_permanente_su_odds_non_ferma_le_altre_fixture(monkeypatch):
    def policy(descr, _attempts):
        if descr["verb"] == "update" and ("eq", "fixture_id", 5002) in descr["filters"]:
            return timeout_57014()
        return None

    client = FakeSupabase(fail_policy=policy)
    writer = _writer_con_client(monkeypatch, client)

    ids = [5001, 5002, 5003, 5004]
    for fid in ids:
        writer.queue_prediction(prediction_row(fid))
        writer.queue_odds(fid, odds_row())
    writer.flush()  # NON deve sollevare

    aggiornate = [
        f for d in client.executed if d["verb"] == "update"
        for (op, col, f) in d["filters"] if col == "fixture_id"
    ]
    assert aggiornate == [5001, 5003, 5004], "le altre fixture restano scritte"
    assert [d["fixture_ids"] for d in client.executed if d["verb"] == "upsert"] == [
        (5001, 5002, 5003, 5004)
    ]
    assert len(tpb._RUN_FAILURES) == 1
    guasto = tpb._RUN_FAILURES[0]
    assert guasto["fixture_id"] == 5002
    assert guasto["operation"] == "odds"
    assert "57014" in guasto["error"] or "statement timeout" in guasto["error"]


def test_fallimento_permanente_su_riga_non_ok_non_propaga(monkeypatch):
    """Prima un errore su una riga no_coverage/empty fermava tutto il run."""
    def policy(descr, _attempts):
        if descr["verb"] != "upsert":
            return None
        if 6002 in descr["fixture_ids"]:
            return timeout_57014()
        return None

    client = FakeSupabase(fail_policy=policy)
    writer = _writer_con_client(monkeypatch, client)

    writer.queue_prediction(prediction_row(6001, status="no_coverage"))
    writer.queue_prediction(prediction_row(6002, status="no_coverage"))
    writer.queue_prediction(prediction_row(6003, status="empty"))
    writer.flush()  # NON deve sollevare

    scritte = [f for d in client.executed if d["verb"] == "upsert" for f in d["fixture_ids"]]
    assert 6001 in scritte and 6003 in scritte
    assert 6002 not in scritte
    assert len(tpb._RUN_FAILURES) == 1
    assert tpb._RUN_FAILURES[0]["fixture_id"] == 6002
    assert tpb._RUN_FAILURES[0]["operation"] == "prediction(no_coverage)"


def test_riga_ok_non_scrivibile_viene_riscritta_come_error_e_registrata(monkeypatch):
    """Semantica storica preservata: la riga ok diventa status='error'."""
    def policy(descr, _attempts):
        if descr["verb"] != "upsert":
            return None
        if 7001 in descr["fixture_ids"] and descr["statuses"] == ("ok",):
            return timeout_57014()
        if len(descr["fixture_ids"]) > 1:
            return timeout_57014()
        return None

    client = FakeSupabase(fail_policy=policy)
    writer = _writer_con_client(monkeypatch, client)

    writer.queue_prediction(prediction_row(7001, status="ok"))
    writer.queue_prediction(prediction_row(7002, status="ok"))
    writer.flush()

    scritte = [(d["fixture_ids"], d["statuses"]) for d in client.executed if d["verb"] == "upsert"]
    assert ((7001,), ("error",)) in scritte, "la riga ok fallita va riscritta come error"
    assert ((7002,), ("ok",)) in scritte
    # I dati della predizione sono comunque persi: deve restare visibile.
    assert [g["operation"] for g in tpb._RUN_FAILURES] == ["prediction(ok)"]
    assert tpb._RUN_FAILURES[0]["fixture_id"] == 7001


def test_main_esce_con_codice_1_solo_se_restano_fallimenti(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["today_predictions_backfill.py", "--date", "2026-09-20"])

    # (a) nessun fallimento -> nessuna SystemExit
    monkeypatch.setattr(tpb, "run_for_date", lambda _d: None)
    tpb.main()

    # (b) un fallimento residuo -> exit code 1
    def _run(_d):
        tpb._record_failure(5002, "odds", timeout_57014())

    monkeypatch.setattr(tpb, "run_for_date", _run)
    with pytest.raises(SystemExit) as ex:
        tpb.main()
    assert ex.value.code == 1


def test_riepilogo_elenca_le_fixture_perse(caplog):
    tpb._record_failure(5002, "odds", timeout_57014())
    tpb._record_failure(5009, "prediction(empty)", timeout_57014())
    with caplog.at_level("ERROR"):
        caplog.clear()  # si guardano SOLO le righe del riepilogo
        assert tpb._log_failures_summary("2026-09-20") == 2
    righe = [r.getMessage() for r in caplog.records]
    assert any("ANOMALIE NON RECUPERATE per 2026-09-20: 2" in r for r in righe)
    dettagli = [r.strip() for r in righe if r.strip().startswith("- fixture_id=")]
    assert len(dettagli) == 2, "il riepilogo deve elencare OGNI fixture persa"
    assert dettagli[0].startswith("- fixture_id=5002 operazione=odds")
    assert dettagli[1].startswith("- fixture_id=5009 operazione=prediction(empty)")


# ==============================================================
# 4) Errori logici: nessun retry
# ==============================================================

@pytest.mark.parametrize("code,message", [
    ("23505", 'duplicate key value violates unique constraint "fixture_predictions_pkey"'),
    ("23503", 'insert or update on table violates foreign key constraint'),
    ("42703", 'column "pippo" does not exist'),
    ("PGRST204", "Could not find the 'pippo' column of 'fixture_predictions' in the schema cache"),
])
def test_errori_logici_non_vengono_ritentati(code, message):
    exc = api_error(code, message)
    assert tpb._is_transient_db_error(exc) is False

    chiamate = {"n": 0}

    def fn():
        chiamate["n"] += 1
        raise exc

    with pytest.raises(APIError):
        tpb._db_execute(fn, what="test")
    assert chiamate["n"] == 1, "un errore logico non si ritenta mai"


@pytest.mark.parametrize("exc", [
    api_error("57014", "canceling statement due to statement timeout"),
    api_error("PGRST002", "Could not query the database for the schema cache"),
    api_error("503", "Service Unavailable"),
    api_error("504", "Gateway Timeout"),
])
def test_errori_transitori_vengono_ritentati(exc):
    assert tpb._is_transient_db_error(exc) is True

    chiamate = {"n": 0}

    def fn():
        chiamate["n"] += 1
        if chiamate["n"] < 3:
            raise exc
        return "ok"

    assert tpb._db_execute(fn, what="test") == "ok"
    assert chiamate["n"] == 3


def test_errori_httpx_di_trasporto_sono_transitori():
    class ReadTimeout(Exception):
        pass

    class ConnectError(Exception):
        pass

    assert tpb._is_transient_db_error(ReadTimeout("timed out")) is True
    assert tpb._is_transient_db_error(ConnectError("[Errno 111] Connection refused")) is True


def test_retry_esaurito_solleva_e_non_ingoia():
    chiamate = {"n": 0}

    def fn():
        chiamate["n"] += 1
        raise timeout_57014()

    with pytest.raises(APIError):
        tpb._db_execute(fn, what="test")
    assert chiamate["n"] == tpb._DB_RETRY_ATTEMPTS


# ==============================================================
# 5) Equivalenza col codice originale quando NON ci sono errori
# ==============================================================

def _carica_modulo_originale(tmp_path) -> Any:
    """Importa la versione di today_predictions_backfill presente in git HEAD."""
    sorgente = subprocess.run(
        ["git", "show", "HEAD:Prediction/today_predictions_backfill.py"],
        cwd=str(PROJECT_ROOT), capture_output=True, check=True,
    ).stdout.decode("utf-8")
    percorso = tmp_path / "today_predictions_backfill_originale.py"
    percorso.write_text(sorgente, encoding="utf-8")

    spec = importlib.util.spec_from_file_location("_tpb_originale", str(percorso))
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["_tpb_originale"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _scenario(modulo: Any, client: FakeSupabase) -> None:
    """Stesso identico scenario sul writer del modulo dato."""
    modulo.get_supabase_client = lambda: client  # type: ignore[attr-defined]
    writer = modulo._DeferredWriter(chunk_size=3)
    for fid in (8001, 8002, 8003, 8004, 8005):
        writer.queue_prediction(prediction_row(fid, status="ok" if fid % 2 else "no_coverage"))
        writer.queue_odds(fid, odds_row())
        writer.queue_analysis(fid, analysis_row())
        writer.maybe_flush()
    writer.flush()


def test_senza_errori_la_sequenza_di_chiamate_e_identica_alloriginale(tmp_path, monkeypatch):
    originale = _carica_modulo_originale(tmp_path)
    # Sanita' del confronto: il modulo di HEAD deve essere DAVVERO quello vecchio.
    assert not hasattr(originale._DeferredWriter, "_upsert_rows")
    assert not hasattr(originale, "_db_execute")
    assert hasattr(tpb._DeferredWriter, "_upsert_rows")

    client_orig = FakeSupabase()
    _scenario(originale, client_orig)

    client_nuovo = FakeSupabase()
    monkeypatch.setattr(tpb, "get_supabase_client", lambda: client_nuovo)
    _scenario(tpb, client_nuovo)

    assert client_nuovo.executed == client_orig.executed
    assert client_nuovo.attempts == client_orig.attempts
    assert client_nuovo.failed == [] and client_orig.failed == []
    assert tpb._RUN_FAILURES == []


def test_rilancio_sulla_stessa_data_e_idempotente(monkeypatch):
    """Due flush identici -> stesse scritture (upsert/update, mai insert)."""
    client = FakeSupabase()
    monkeypatch.setattr(tpb, "get_supabase_client", lambda: client)

    for _ in range(2):
        writer = tpb._DeferredWriter(chunk_size=100)
        for fid in (9001, 9002):
            writer.queue_prediction(prediction_row(fid))
            writer.queue_odds(fid, odds_row())
        writer.flush()

    meta = len(client.executed) // 2
    assert client.executed[:meta] == client.executed[meta:]
    assert all(d["verb"] in ("upsert", "update") for d in client.executed)
    assert all(
        d["on_conflict"] == "fixture_id"
        for d in client.executed if d["verb"] == "upsert"
    )


# ==============================================================
# 6) SECONDO GIRO - coverage: nessun 'no_coverage' FALSO
# ==============================================================

def test_coverage_caso_a_riga_presente_si_comporta_come_sempre(monkeypatch):
    """(a) riga presente -> il flag della colonna, e viene memoizzato."""
    client = FakeSupabase(coverage_rows={
        (135, 2026): {"predictions": True, "odds": False},
    })
    monkeypatch.setattr(tpb, "get_supabase_client", lambda: client)

    cache_p: Dict[Any, bool] = {}
    cache_o: Dict[Any, bool] = {}
    assert tpb.predictions_coverage_true(135, 2026, cache_p) is True
    assert tpb.odds_coverage_true(135, 2026, cache_o) is False
    assert cache_p == {(135, 2026): True}
    assert cache_o == {(135, 2026): False}
    # seconda chiamata: nessuna query in piu' (memoizzazione)
    prima = len(client.executed)
    tpb.predictions_coverage_true(135, 2026, cache_p)
    assert len(client.executed) == prima


def test_coverage_caso_b_riga_assente_resta_no_coverage_legittimo(monkeypatch):
    """(b) maybe_single() -> None: copertura davvero mancante, False e cache."""
    client = FakeSupabase(coverage_rows={})  # nessuna riga per (999, 2026)
    monkeypatch.setattr(tpb, "get_supabase_client", lambda: client)

    cache: Dict[Any, bool] = {}
    assert tpb.predictions_coverage_true(999, 2026, cache) is False
    assert cache == {(999, 2026): False}, "l'assenza vera si puo' memoizzare"
    assert tpb._RUN_FAILURES == [], "l'assenza NON e' un'anomalia"


def test_coverage_caso_c_errore_di_lettura_non_diventa_mai_no_coverage(monkeypatch):
    """(c) errore dopo i retry -> CoverageReadError, nessuna memoizzazione."""
    def policy(descr, _attempts):
        if descr["table"] == "api_coverage_by_season":
            return timeout_57014()
        return None

    client = FakeSupabase(fail_policy=policy)
    monkeypatch.setattr(tpb, "get_supabase_client", lambda: client)

    cache: Dict[Any, bool] = {}
    with pytest.raises(tpb.CoverageReadError) as ex:
        tpb.predictions_coverage_true(135, 2026, cache)
    assert ex.value.campo == "predictions"
    assert ex.value.league_id == 135 and ex.value.season_year == 2026
    assert cache == {}, "un errore NON si memoizza come False"
    assert len(client.failed) == tpb._DB_RETRY_ATTEMPTS

    cache_o: Dict[Any, bool] = {}
    with pytest.raises(tpb.CoverageReadError) as ex2:
        tpb.odds_coverage_true(135, 2026, cache_o)
    assert ex2.value.campo == "odds"
    assert cache_o == {}


# ==============================================================
# 7) SECONDO GIRO - run_for_date intero
# ==============================================================

class FakeAPI:
    """APIFootballClient finto: registra le chiamate fatte."""

    def __init__(self) -> None:
        self.calls: List[Any] = []

    def call(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.calls.append((path, tuple(sorted((params or {}).items()))))
        if path == "/predictions":
            return {"response": [{
                "predictions": {
                    "winner": {"id": 492, "name": "Napoli", "comment": None},
                    "win_or_draw": True, "under_over": "-1.5", "advice": "Double chance",
                    "goals": {"home": "-1.5", "away": "-1.5"},
                    "percent": {"home": "45%", "draw": "30%", "away": "25%"},
                },
                "teams": {}, "comparison": {},
            }]}
        if path == "/odds":
            return {"response": [], "paging": {"current": 1, "total": 1}}
        return {"response": []}


def fixture_api(fixture_id: int, league_id: int = 135, season: int = 2026) -> Dict[str, Any]:
    """Fixture nella forma della risposta /fixtures di API-Football."""
    return {
        "fixture": {"id": int(fixture_id), "date": "2026-09-20T18:00:00+00:00"},
        "league": {"id": int(league_id), "name": "Serie A", "season": int(season)},
        "teams": {"home": {"id": 492, "name": "Napoli"},
                  "away": {"id": 489, "name": "Milan"}},
    }


def _stub_motori_finali() -> None:
    """ML e tactical engine parlano col DB vero: qui sono finti."""
    import types
    for nome in ("ai_engine.serving_batch", "tactical_engine.serving"):
        pacchetto = nome.split(".")[0]
        sys.modules.setdefault(pacchetto, types.ModuleType(pacchetto))
        mod = types.ModuleType(nome)
        mod.run_for_date = lambda _d: {"finto": True}  # type: ignore[attr-defined]
        sys.modules[nome] = mod


def _esegui_run_for_date(
    modulo: Any,
    monkeypatch,
    client: FakeSupabase,
    fixtures: List[Dict[str, Any]],
    api: Optional[FakeAPI] = None,
    target: str = "2026-09-20",
) -> FakeAPI:
    """Esegue run_for_date del modulo dato con tutto il contorno finto."""
    _stub_motori_finali()
    api = api or FakeAPI()
    monkeypatch.setattr(modulo, "get_supabase_client", lambda: client)
    monkeypatch.setattr(modulo, "APIFootballClient", lambda *a, **k: api)
    monkeypatch.setattr(modulo, "fetch_fixtures_for_date", lambda _api, _d: fixtures)
    # analisi: modello diverso da poisson_xg_hybrid_dc -> nessuna calibrazione
    monkeypatch.setattr(modulo, "compute_db_json_analisi",
                        lambda *a, **k: ({"model": "finto"}, {"is_elite": False}))
    monkeypatch.setattr(modulo, "flush_api_log", lambda: None)
    if hasattr(modulo, "_db_sleep"):
        monkeypatch.setattr(modulo, "_db_sleep", lambda _s: None)
    modulo.run_for_date(target)
    return api


def _fixture_ids_toccate(client: FakeSupabase) -> set:
    tocc = set()
    for d in client.executed:
        for f in d["fixture_ids"]:
            tocc.add(f)
        for op, col, val in d["filters"]:
            if col == "fixture_id" and op == "eq":
                tocc.add(val)
    return tocc


def test_coverage_illeggibile_non_scrive_nulla_e_le_altre_fixture_proseguono(monkeypatch):
    """La lega 999 ha la coverage rotta: le sue fixture NON vengono toccate."""
    def policy(descr, _attempts):
        if descr["table"] == "api_coverage_by_season" and ("eq", "league_id", 999) in descr["filters"]:
            return timeout_57014()
        return None

    client = FakeSupabase(
        fail_policy=policy,
        coverage_rows={(135, 2026): {"predictions": True, "odds": True}},
    )
    fixtures = [fixture_api(7101, 135), fixture_api(7102, 999), fixture_api(7103, 135)]
    _esegui_run_for_date(tpb, monkeypatch, client, fixtures)

    # nessuna riga di fixture_predictions scritta per 7102, con nessuno status
    for d in client.executed:
        if d["verb"] in ("upsert", "update"):
            assert 7102 not in d["fixture_ids"], "MAI un no_coverage falso"
            for op, col, val in d["filters"]:
                assert not (col == "fixture_id" and val == 7102)

    toccate = _fixture_ids_toccate(client)
    assert 7101 in toccate and 7103 in toccate

    guasti = [g for g in tpb._RUN_FAILURES if g["fixture_id"] == 7102]
    assert len(guasti) == 1 and guasti[0]["operation"] == "coverage-read"


def test_fixture_non_toccata_viene_riprocessata_al_rilancio(monkeypatch):
    """Il prefetch salta SOLO gli status='ok': una fixture mai scritta ritorna."""
    client = FakeSupabase(select_data=[
        {"fixture_id": 7101, "status": "ok", "ht_predictions": {"is_elite": False}},
        {"fixture_id": 7104, "status": "no_coverage", "ht_predictions": None},
        {"fixture_id": 7105, "status": "ok", "ht_predictions": None},
    ])
    monkeypatch.setattr(tpb, "get_supabase_client", lambda: client)

    done = tpb.prefetch_predictions_done([7101, 7102, 7104, 7105])
    assert done == {7101}
    assert 7102 not in done   # mai scritta -> al rilancio viene rielaborata
    assert 7104 not in done   # no_coverage -> rielaborata
    assert 7105 not in done   # ok senza ht_predictions -> rielaborata


def test_coverage_odds_illeggibile_non_azzera_le_quote(monkeypatch):
    """Coverage odds rotta: niente raw_json_odds=NULL, ma la prediction resta."""
    def policy(descr, _attempts):
        if descr["table"] == "api_coverage_by_season" and descr["columns"] == "odds":
            return timeout_57014()
        return None

    client = FakeSupabase(
        fail_policy=policy,
        coverage_rows={(135, 2026): {"predictions": True, "odds": True}},
    )
    _esegui_run_for_date(tpb, monkeypatch, client, [fixture_api(7201, 135)])

    upserts = [d for d in client.executed if d["verb"] == "upsert"]
    assert any(7201 in d["fixture_ids"] and d["statuses"] == ("ok",) for d in upserts), (
        "la predizione, che e' un dato VERO, va comunque scritta"
    )
    odds_scritte = [d for d in client.executed
                    if d["verb"] == "update" and any("raw_json_odds" in k for k in d["row_keys"])]
    assert odds_scritte == [], "nessun raw_json_odds scritto se la coverage e' ignota"
    assert [g["operation"] for g in tpb._RUN_FAILURES] == ["coverage-read-odds"]


def test_analisi_non_calcolata_viene_registrata(monkeypatch):
    """compute_db_json_analisi che esplode: non piu' solo un warning."""
    client = FakeSupabase(coverage_rows={(135, 2026): {"predictions": True, "odds": True}})
    _stub_motori_finali()
    api = FakeAPI()
    monkeypatch.setattr(tpb, "get_supabase_client", lambda: client)
    monkeypatch.setattr(tpb, "APIFootballClient", lambda *a, **k: api)
    monkeypatch.setattr(tpb, "fetch_fixtures_for_date", lambda _a, _d: [fixture_api(7301, 135)])
    monkeypatch.setattr(tpb, "flush_api_log", lambda: None)

    def esplode(*_a, **_k):
        raise ValueError("matrice Poisson degenere")

    monkeypatch.setattr(tpb, "compute_db_json_analisi", esplode)
    tpb.run_for_date("2026-09-20")

    guasti = [g for g in tpb._RUN_FAILURES if g["operation"] == "analisi-calcolo"]
    assert len(guasti) == 1
    assert guasti[0]["fixture_id"] == 7301
    assert "Poisson degenere" in guasti[0]["error"]


def test_calibrazione_fallita_viene_registrata(monkeypatch):
    """Dato scritto NON calibrato: prima non lasciava alcuna traccia."""
    class CalibratoreRotto:
        source = "finto"

        def calibrate_markets(self, _markets, _league_id):
            raise RuntimeError("fattori di calibrazione assenti")

    monkeypatch.setattr(tpb, "_poisson_cal", lambda: CalibratoreRotto())
    row = tpb._build_analysis_row(
        7401,
        {"model": "poisson_xg_hybrid_dc", "markets": {"over_2_5": 0.5}, "league_id": 135},
        {"is_elite": False},
    )
    # il grezzo resta intatto (semantica invariata)
    assert row["db_json_analisi"]["markets"] == {"over_2_5": 0.5}
    assert "markets_calibrated" not in row["db_json_analisi"]
    guasti = [g for g in tpb._RUN_FAILURES if g["operation"] == "calibrazione"]
    assert len(guasti) == 1 and guasti[0]["fixture_id"] == 7401


def test_run_for_date_senza_errori_e_identico_alloriginale(tmp_path, monkeypatch):
    """Equivalenza end-to-end: stessa sequenza DB e stesse chiamate API di HEAD."""
    originale = _carica_modulo_originale(tmp_path)
    assert not hasattr(originale, "CoverageReadError")

    fixtures = [fixture_api(8101, 135), fixture_api(8102, 135),
                fixture_api(8103, 140), fixture_api(8104, 140)]
    coverage = {
        (135, 2026): {"predictions": True, "odds": True},
        (140, 2026): {"predictions": False, "odds": False},
    }

    client_orig = FakeSupabase(coverage_rows=dict(coverage))
    api_orig = _esegui_run_for_date(originale, monkeypatch, client_orig, list(fixtures))

    client_nuovo = FakeSupabase(coverage_rows=dict(coverage))
    api_nuovo = _esegui_run_for_date(tpb, monkeypatch, client_nuovo, list(fixtures))

    assert client_nuovo.executed == client_orig.executed
    assert client_nuovo.attempts == client_orig.attempts
    assert api_nuovo.calls == api_orig.calls
    assert client_nuovo.failed == [] and client_orig.failed == []
    assert tpb._RUN_FAILURES == []
