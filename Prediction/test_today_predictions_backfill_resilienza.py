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

import copy
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
        self._negato = False

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

    @property
    def not_(self) -> "FakeQuery":
        """Come postgrest: nega il filtro SUCCESSIVO."""
        self._negato = True
        return self

    def is_(self, col: str, val: Any) -> "FakeQuery":
        self._filters.append(("not.is" if self._negato else "is", col, val))
        self._negato = False
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

    def _righe_filtrate(self, descr: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Applica i filtri LATO SERVER, come farebbe PostgREST, e proietta le
        colonne richieste. Serve a provare che spostare il predicato dal Python
        al server non cambia l'insieme restituito."""
        righe = list(self.select_data)
        for op, col, val in descr["filters"]:
            if op == "in":
                righe = [r for r in righe if r.get(col) in val]
            elif op == "eq":
                righe = [r for r in righe if r.get(col) == val]
            elif op == "is" and val == "null":
                righe = [r for r in righe if r.get(col) is None]
            elif op == "not.is" and val == "null":
                righe = [r for r in righe if r.get(col) is not None]
        colonne = [c.strip() for c in (descr["columns"] or "*").split(",")]
        if colonne == ["*"]:
            return righe
        return [{c: r.get(c) for c in colonne} for r in righe]

    def response_for(self, descr: Dict[str, Any]) -> Any:
        if descr["table"] == "api_coverage_by_season" and descr["verb"] == "select":
            chiave = tuple(v for (op, col, v) in descr["filters"] if op == "eq")
            return self.coverage_rows.get(chiave)
        if descr["verb"] == "select":
            righe = self._righe_filtrate(descr)
            if descr["single"]:
                return righe[0] if righe else None
            return righe
        if descr["verb"] == "update":
            fid = None
            for op, col, val in descr["filters"]:
                if op == "eq" and col == "fixture_id":
                    fid = val
            # Il vero PostgREST ritorna le righe aggiornate.
            return [{"fixture_id": fid}]
        return [{"fixture_id": f} for f in descr["fixture_ids"]]


# Colonne NOT NULL di fixture_predictions note dal repo
# (migrations/predictions_results_bulk_update_rpc.sql: "non puo' violare NOT
# NULL (es. status)"). Il finto con tabella le fa rispettare come Postgres.
NOT_NULL_FIXTURE_PREDICTIONS = ("fixture_id", "status")


class FakeQueryConTabella(FakeQuery):
    """Come FakeQuery, ma upsert/update su fixture_predictions MODIFICANO una
    tabella in memoria con la semantica di PostgREST + Postgres:

    - upsert (merge-duplicates, on_conflict=fixture_id): riga presente ->
      aggiorna SOLO le colonne del payload; assente -> inserisce la riga;
    - i NOT NULL della riga proposta si controllano PRIMA del conflitto (come
      Postgres in INSERT ... ON CONFLICT): una riga monca e' rifiutata con
      23502 anche se la riga esiste gia';
    - bulk con chiavi diverse fra gli oggetti -> PGRST102 (come PostgREST);
    - update ... eq(fixture_id): aggiorna solo se la riga c'e', ritorna [] se no;
    - una richiesta fallita non scrive nulla (statement atomico).
    """

    def _vincoli(self) -> Optional[APIError]:
        if self._table != "fixture_predictions" or self._verb != "upsert":
            return None
        righe = self._payload if isinstance(self._payload, list) else [self._payload]
        chiavi = {frozenset(r.keys()) for r in righe}
        if len(chiavi) > 1:
            return api_error("PGRST102", "All object keys must match")
        for r in righe:
            for col in NOT_NULL_FIXTURE_PREDICTIONS:
                if r.get(col) is None:
                    return api_error(
                        "23502",
                        'null value in column "%s" of relation "fixture_predictions" '
                        "violates not-null constraint" % col,
                    )
        return None

    def _applica(self) -> List[Dict[str, Any]]:
        tabella = self._c.tabella
        if self._verb == "upsert":
            righe = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for r in righe:
                r = copy.deepcopy(r)
                fid = r["fixture_id"]
                if fid in tabella:
                    tabella[fid].update(r)
                else:
                    tabella[fid] = r
                out.append(copy.deepcopy(tabella[fid]))
            return out
        fid = None
        for op, col, val in self._filters:
            if op == "eq" and col == "fixture_id":
                fid = val
        if fid not in tabella:
            return []
        tabella[fid].update(copy.deepcopy(self._payload))
        return [copy.deepcopy(tabella[fid])]

    def execute(self) -> Optional[FakeResponse]:
        descr = self._descr()
        exc = None
        if self._c.fail_policy is not None:
            exc = self._c.fail_policy(descr, self._c.attempts)
        if exc is None:
            exc = self._vincoli()
        self._c.attempts.append(descr)
        if exc is not None:
            self._c.failed.append(descr)
            raise exc
        self._c.executed.append(descr)
        if self._table == "fixture_predictions" and self._verb in ("upsert", "update"):
            return FakeResponse(self._applica())
        dati = self._c.response_for(descr)
        if self._single and dati is None:
            return None
        return FakeResponse(dati)


class FakeSupabaseConTabella(FakeSupabase):
    """FakeSupabase con lo STATO di fixture_predictions (fixture_id -> riga)."""

    def __init__(self, *args: Any, tabella: Optional[Dict[int, Dict[str, Any]]] = None, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self.tabella: Dict[int, Dict[str, Any]] = copy.deepcopy(tabella) if tabella else {}

    def table(self, name: str) -> FakeQuery:
        return FakeQueryConTabella(self, name)


def _scritture(client: FakeSupabase) -> List[Dict[str, Any]]:
    """Richieste di scrittura su fixture_predictions riuscite."""
    return [d for d in client.executed
            if d["table"] == "fixture_predictions" and d["verb"] in ("upsert", "update", "insert")]


def _ha_colonna(descr: Dict[str, Any], col: str) -> bool:
    return any(col in k for k in descr["row_keys"])


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


def test_dimensione_blocco_iniziale_predizioni_e_25() -> None:
    """Il blocco iniziale dell'upsert delle predizioni e' sceso da 100 a 25
    righe (~5s a 0,2s/riga, sotto lo statement_timeout PostgREST di 8s): un
    blocco da 100 (~20s) andava in 57014 anche a DB poco carico, e persino
    il dimezzamento a 50 restava sopra la soglia (run 35837269470, 23/09).
    25 e' la stessa dimensione gia' scelta per i blocchi uniti delle
    post_ops (_POST_OPS_CHUNK_SIZE). Falsifica: rimettendo il default a 100
    in _DeferredWriter.__init__ questa assert va rossa."""
    assert tpb._DeferredWriter().chunk_size == 25


def test_57014_su_blocco_di_25_dimezza_a_12_e_13(monkeypatch):
    """Il nuovo blocco di partenza (25 righe): un 57014 sul batch intero
    deve dimezzare UNA volta a 12+13 e scrivere le STESSE righe finali,
    senza fixture perse ne' righe singole necessarie."""
    def policy(descr, _attempts):
        if descr["verb"] == "upsert" and len(descr["fixture_ids"]) == 25:
            return timeout_57014()
        return None

    client = FakeSupabaseConTabella(fail_policy=policy)
    writer = _writer_con_client(monkeypatch, client, chunk_size=25)

    ids = list(range(5001, 5026))  # 25 righe
    for fid in ids:
        writer.queue_prediction(prediction_row(fid))
    writer.flush()

    scritte = [d["fixture_ids"] for d in client.executed if d["verb"] == "upsert"]
    assert scritte == [tuple(ids[:12]), tuple(ids[12:])], (
        "25 righe: un 57014 sul blocco intero deve dimezzare a 12+13, non oltre"
    )
    assert tpb._RUN_FAILURES == [], "nessuna fixture persa"
    attese = {fid: prediction_row(fid) for fid in ids}
    assert client.tabella == attese, "stesse righe finali di prediction_row(), nessuna alterata"


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

def test_57014_sulla_scrittura_delle_odds_viene_ritentato_e_riesce(monkeypatch):
    """Le odds viaggiano nell'upsert a blocchi: due 57014, poi passa."""
    def policy(descr, attempts):
        if not _ha_colonna(descr, "raw_json_odds"):
            return None
        precedenti = sum(1 for a in attempts if _ha_colonna(a, "raw_json_odds"))
        return timeout_57014() if precedenti < 2 else None

    client = FakeSupabaseConTabella(fail_policy=policy)
    writer = _writer_con_client(monkeypatch, client)

    for fid in (4001, 4002, 4003):
        writer.queue_prediction(prediction_row(fid))
        writer.queue_odds(fid, odds_row())
    writer.flush()

    for fid in (4001, 4002, 4003):
        assert client.tabella[fid]["raw_json_odds"] == odds_row()["raw_json_odds"], (
            "tutte e tre le odds devono essere scritte"
        )
    assert len(client.failed) == 2, "due tentativi falliti prima del successo"
    assert tpb._RUN_FAILURES == []


def test_57014_su_update_odds_singola_viene_ritentato_e_riesce(monkeypatch):
    """Percorso UPDATE di sempre (fixture senza riga di prediction nel flush)."""
    def policy(descr, attempts):
        if descr["verb"] != "update":
            return None
        precedenti = sum(1 for a in attempts if a["verb"] == "update")
        return timeout_57014() if precedenti < 2 else None

    esistente = prediction_row(4101)
    client = FakeSupabaseConTabella(fail_policy=policy, tabella={4101: esistente})
    writer = _writer_con_client(monkeypatch, client)
    writer.queue_odds(4101, odds_row())
    writer.flush()

    assert [d["filters"] for d in client.executed if d["verb"] == "update"] == [
        (("eq", "fixture_id", 4101),)]
    assert client.tabella[4101]["raw_json_odds"] == odds_row()["raw_json_odds"]
    assert len(client.failed) == 2
    assert tpb._RUN_FAILURES == []


# ==============================================================
# 3) Fallimento permanente: le altre fixture vengono comunque scritte
# ==============================================================

def test_fallimento_permanente_su_odds_non_ferma_le_altre_fixture(monkeypatch):
    def policy(descr, _attempts):
        if not _ha_colonna(descr, "raw_json_odds"):
            return None
        if 5002 in descr["fixture_ids"] or ("eq", "fixture_id", 5002) in descr["filters"]:
            return timeout_57014()
        return None

    client = FakeSupabaseConTabella(fail_policy=policy)
    writer = _writer_con_client(monkeypatch, client)

    ids = [5001, 5002, 5003, 5004]
    for fid in ids:
        writer.queue_prediction(prediction_row(fid))
        writer.queue_odds(fid, odds_row())
    writer.flush()  # NON deve sollevare

    con_odds = sorted(f for f, r in client.tabella.items() if "raw_json_odds" in r)
    assert con_odds == [5001, 5003, 5004], "le altre fixture restano scritte"
    assert client.tabella[5002] == prediction_row(5002), "la prediction resta, le odds no"
    assert [d["fixture_ids"] for d in client.executed
            if d["verb"] == "upsert" and not _ha_colonna(d, "raw_json_odds")] == [
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

# Commit BASE del lavoro (origin/master prima di ogni fix 57014): e' il
# riferimento fisso dell'equivalenza. NON usare HEAD: appena i fix vengono
# committati HEAD diventa il codice nuovo e il confronto non prova piu' nulla.
COMMIT_BASE = "2f1c549"


def _carica_modulo_originale(tmp_path, commit: str = COMMIT_BASE) -> Any:
    """Importa today_predictions_backfill come era nel commit dato."""
    riferimento = "%s:Prediction/today_predictions_backfill.py" % commit
    esito = subprocess.run(
        ["git", "show", riferimento],
        cwd=str(PROJECT_ROOT), capture_output=True,
    )
    if esito.returncode != 0:
        pytest.skip(
            "commit %s non disponibile (clone shallow?): equivalenza NON "
            "verificata. git: %s" % (commit, esito.stderr.decode("utf-8", "replace")[:200])
        )
    sorgente = esito.stdout.decode("utf-8")
    nome = "_tpb_originale_%s" % commit
    percorso = tmp_path / ("today_predictions_backfill_%s.py" % commit)
    percorso.write_text(sorgente, encoding="utf-8")

    spec = importlib.util.spec_from_file_location(nome, str(percorso))
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nome] = modulo
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


def _solo_predizioni(seq: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Le scritture delle righe di prediction (esclusi odds/analisi)."""
    return [d for d in seq if d["verb"] == "upsert"
            and not _ha_colonna(d, "raw_json_odds") and not _ha_colonna(d, "db_json_analisi")]


def test_senza_errori_stesse_righe_finali_dell_originale(tmp_path, monkeypatch):
    """Le predizioni: STESSA sequenza di upsert dell'originale. Odds e
    analisi: cambia il modo (upsert a blocchi al posto di una UPDATE per
    fixture), ma la TABELLA finale e' identica, colonna per colonna."""
    originale = _carica_modulo_originale(tmp_path)
    # Sanita' del confronto: il modulo di HEAD deve essere DAVVERO quello vecchio.
    assert not hasattr(originale._DeferredWriter, "_upsert_rows")
    assert not hasattr(originale, "_db_execute")
    assert hasattr(tpb._DeferredWriter, "_upsert_rows")

    client_orig = FakeSupabaseConTabella()
    _scenario(originale, client_orig)

    client_nuovo = FakeSupabaseConTabella()
    monkeypatch.setattr(tpb, "get_supabase_client", lambda: client_nuovo)
    _scenario(tpb, client_nuovo)

    assert _solo_predizioni(client_nuovo.executed) == _solo_predizioni(client_orig.executed)
    assert client_nuovo.tabella == client_orig.tabella
    assert len(client_orig.tabella) == 5
    assert [d for d in client_nuovo.executed if d["verb"] == "update"] == []
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


def _ferma_orologio(monkeypatch, modulo: Any) -> None:
    """datetime.now() del modulo scandisce un orologio finto che avanza di un
    secondo a ogni lettura: timestamp DISTINTI (un updated_at sbagliato si
    vede) ma riproducibili fra due moduli che leggono l'ora lo stesso numero
    di volte nello stesso ordine."""
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    passi = {"n": 0}

    class _Orologio(_dt):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            passi["n"] += 1
            return _dt(2026, 9, 20, 12, 0, 0, tzinfo=tz or _tz.utc) + _td(seconds=passi["n"])

    monkeypatch.setattr(modulo, "datetime", _Orologio)


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
    # qualunque verbo di scrittura: le odds oggi viaggiano anche in upsert
    odds_scritte = [d for d in client.executed
                    if d["verb"] in ("update", "upsert") and _ha_colonna(d, "raw_json_odds")]
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
    """Equivalenza end-to-end col commit base: stesse chiamate API, stesse
    letture, stessa TABELLA finale (timestamp inclusi)."""
    originale = _carica_modulo_originale(tmp_path)
    assert not hasattr(originale, "CoverageReadError")

    fixtures = [fixture_api(8101, 135), fixture_api(8102, 135),
                fixture_api(8103, 140), fixture_api(8104, 140)]
    coverage = {
        (135, 2026): {"predictions": True, "odds": True},
        (140, 2026): {"predictions": False, "odds": False},
    }

    # Orologio fermo: i timestamp (updated_at) sono calcolati con
    # datetime.now(), cosi' le due tabelle si possono confrontare per intero.
    _ferma_orologio(monkeypatch, originale)
    _ferma_orologio(monkeypatch, tpb)

    client_orig = FakeSupabaseConTabella(coverage_rows=dict(coverage))
    api_orig = _esegui_run_for_date(originale, monkeypatch, client_orig, list(fixtures))

    client_nuovo = FakeSupabaseConTabella(coverage_rows=dict(coverage))
    api_nuovo = _esegui_run_for_date(tpb, monkeypatch, client_nuovo, list(fixtures))

    def _letture(seq: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [d for d in _senza_query_di_prefetch(seq) if d["verb"] == "select"]

    # letture e chiamate API identiche; predizioni con la stessa sequenza;
    # odds e analisi: stesso contenuto finale della tabella, meno richieste.
    assert _letture(client_nuovo.executed) == _letture(client_orig.executed)
    assert _solo_predizioni(client_nuovo.executed) == _solo_predizioni(client_orig.executed)
    assert client_nuovo.tabella == client_orig.tabella
    assert sorted(client_orig.tabella) == [8101, 8102, 8103, 8104]
    assert api_nuovo.calls == api_orig.calls
    assert client_nuovo.failed == [] and client_orig.failed == []
    assert tpb._RUN_FAILURES == []
    assert len(_scritture(client_nuovo)) < len(_scritture(client_orig))


# ==============================================================
# 8) TERZO GIRO
# ==============================================================

def _senza_query_di_prefetch(seq: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Esclude la SELECT di prefetch dal confronto di equivalenza.

    E' l'unica query cambiata DI PROPOSITO (M8: predicato spostato sul server,
    niente piu' ht_predictions in rete). Che l'INSIEME restituito sia lo stesso
    e' provato da test_prefetch_predicato_lato_server_stesso_insieme.
    """
    return [
        d for d in seq
        if not (d["verb"] == "select" and d["table"] == "fixture_predictions"
                and any(op == "in" and col == "fixture_id" for op, col, _v in d["filters"]))
    ]


# ---------- M8: prefetch leggero, stesso insieme ----------

def _prefetch_vecchia_logica(righe: List[Dict[str, Any]], ids: List[int]) -> set:
    """La logica ORIGINALE, applicata in Python (commit base 2f1c549)."""
    done = set()
    for row in righe:
        if row.get("fixture_id") not in ids:
            continue
        if row.get("status") != "ok":
            continue
        if row.get("ht_predictions") is None:
            continue
        done.add(int(row["fixture_id"]))
    return done


RIGHE_PREFETCH = [
    {"fixture_id": 9001, "status": "ok", "ht_predictions": {"is_elite": True}},
    {"fixture_id": 9002, "status": "ok", "ht_predictions": None},
    {"fixture_id": 9003, "status": "no_coverage", "ht_predictions": None},
    {"fixture_id": 9004, "status": "empty", "ht_predictions": {"is_elite": False}},
    {"fixture_id": 9005, "status": "error", "ht_predictions": None},
    {"fixture_id": 9006, "status": "ok", "ht_predictions": {"is_elite": False}},
    # 9007 non ha alcuna riga
]


def test_prefetch_predicato_lato_server_stesso_insieme(monkeypatch):
    """Il predicato spostato sul server deve dare lo STESSO set di prima."""
    ids = [9001, 9002, 9003, 9004, 9005, 9006, 9007]
    client = FakeSupabase(select_data=[dict(r) for r in RIGHE_PREFETCH])
    monkeypatch.setattr(tpb, "get_supabase_client", lambda: client)

    nuovo = tpb.prefetch_predictions_done(ids)
    atteso = _prefetch_vecchia_logica(RIGHE_PREFETCH, ids)
    assert nuovo == atteso == {9001, 9006}


def test_prefetch_non_scarica_piu_il_json_pesante(monkeypatch):
    """M8: si seleziona il solo fixture_id, il predicato lo applica il server."""
    client = FakeSupabase(select_data=[dict(r) for r in RIGHE_PREFETCH])
    monkeypatch.setattr(tpb, "get_supabase_client", lambda: client)
    tpb.prefetch_predictions_done([9001, 9002])

    q = [d for d in client.executed if d["verb"] == "select"][0]
    assert q["columns"] == "fixture_id", "ht_predictions non deve piu' viaggiare in rete"
    assert ("eq", "status", "ok") in q["filters"]
    assert ("not.is", "ht_predictions", "null") in q["filters"]


def test_prefetch_in_errore_resta_fail_open_ma_finisce_nel_registro(monkeypatch):
    """Comportamento invariato (rielabora), ma non piu' ingoiato."""
    def policy(descr, _attempts):
        if descr["verb"] == "select" and descr["table"] == "fixture_predictions":
            return timeout_57014()
        return None

    client = FakeSupabase(fail_policy=policy)
    monkeypatch.setattr(tpb, "get_supabase_client", lambda: client)

    done = tpb.prefetch_predictions_done([9001, 9002, 9003])
    assert done == set(), "fail-open: tutte rielaborate, come prima"
    assert [g["operation"] for g in tpb._RUN_FAILURES] == ["prefetch"]
    assert tpb._RUN_FAILURES[0]["fixture_id"] == "9001..9003"


# ---------- ALTO-5: freni assoluti ----------

def test_57014_permanente_non_martella_il_db_e_registra_tutte_le_righe(monkeypatch):
    """100 righe, 57014 permanente: poche richieste, zero righe perse in silenzio."""
    monkeypatch.setattr(tpb, "_DB_MAX_FAILED_REQUESTS", 12)

    client = FakeSupabase(fail_policy=lambda d, a: timeout_57014() if d["verb"] == "upsert" else None)
    writer = _writer_con_client(monkeypatch, client)

    ids = list(range(9100, 9200))  # 100 righe
    for fid in ids:
        writer.queue_prediction(prediction_row(fid, status="no_coverage"))
    writer.flush()

    richieste = len(client.attempts)
    assert richieste <= 40, "il freno deve fermare il dimezzamento: %s richieste" % richieste
    registrate = {g["fixture_id"] for g in tpb._RUN_FAILURES}
    assert registrate == set(ids), "tutte e 100 devono restare tracciate"


def test_freno_gia_attivo_concede_comunque_un_dimezzamento_al_blocco_nuovo(monkeypatch):
    """Il freno di parete, gia' scattato per un blocco precedente nello
    stesso run, non deve far perdere INTERO un blocco appena arrivato da
    flush() senza avergli dato almeno un dimezzamento (misurato il 23/09,
    run 35837269470: un blocco da 100 dimezzato una volta a 50+50, poi il
    freno bloccava OGNI ulteriore dimezzamento e perdeva l'intero blocco).
    Il blocco intero E i suoi due mezzi devono essere tentati; solo i mezzi,
    gia' dimezzati una volta, si arrendono subito se falliscono anche loro."""
    monkeypatch.setattr(tpb, "_DB_FAILED_REQUESTS", tpb._DB_MAX_FAILED_REQUESTS)  # freno gia' esaurito

    client = FakeSupabase(fail_policy=lambda d, a: timeout_57014() if d["verb"] == "upsert" else None)
    writer = _writer_con_client(monkeypatch, client, chunk_size=25)

    ids = list(range(6001, 6026))  # 25 righe, il nuovo blocco iniziale
    for fid in ids:
        writer.queue_prediction(prediction_row(fid))
    writer.flush()

    assert [d["fixture_ids"] for d in client.executed if d["verb"] == "upsert"] == [], (
        "permanente: nessun upsert riesce"
    )
    tentativi = [d["fixture_ids"] for d in client.attempts if d["verb"] == "upsert"]
    assert tuple(ids) in tentativi, "il blocco intero da 25 deve essere tentato"
    assert tuple(ids[:12]) in tentativi, "la prima meta' (12) deve essere tentata"
    assert tuple(ids[12:]) in tentativi, "la seconda meta' (13) deve essere tentata"
    assert len(tentativi) == 3, "solo il primo dimezzamento: i mezzi non si dimezzano oltre a freno attivo"
    registrate = {g["fixture_id"] for g in tpb._RUN_FAILURES}
    assert registrate == set(ids), "tutte e 25 restano tracciate, nessuna persa in silenzio"


def test_scadenza_di_parete_ferma_i_retry(monkeypatch):
    """Superata la deadline non si ritenta piu', anche con budget di attese intatto."""
    orologio = {"t": 1000.0}
    monkeypatch.setattr(tpb, "_db_monotonic", lambda: orologio["t"])
    monkeypatch.setattr(tpb, "_DB_RETRY_DEADLINE_S", 60.0)
    monkeypatch.setattr(tpb, "_db_sleep", lambda _s: orologio.__setitem__("t", orologio["t"] + 30.0))

    chiamate = {"n": 0}

    def fn():
        chiamate["n"] += 1
        raise timeout_57014()

    with pytest.raises(APIError):
        tpb._db_execute(fn, what="test")
    # 1o fallimento -> arma la deadline (t=1000+60=1060), dorme 30 (t=1030);
    # 2o fallimento -> t=1030 < 1060 quindi ritenta, dorme 30 (t=1060);
    # 3o fallimento -> t=1060 >= 1060: freno, niente altri tentativi.
    assert chiamate["n"] == 3, "la deadline deve tagliare i 6 tentativi a 3"
    assert tpb._db_retry_exhausted() is not None


def test_limite_di_richieste_fallite_blocca_i_retry(monkeypatch):
    monkeypatch.setattr(tpb, "_DB_MAX_FAILED_REQUESTS", 2)
    chiamate = {"n": 0}

    def fn():
        chiamate["n"] += 1
        raise timeout_57014()

    with pytest.raises(APIError):
        tpb._db_execute(fn, what="test")
    assert chiamate["n"] == 2


def test_numero_di_tentativi_letto_a_runtime(monkeypatch):
    """B5: _DB_RETRY_ATTEMPTS regolabile (e quindi falsificabile)."""
    monkeypatch.setattr(tpb, "_DB_RETRY_ATTEMPTS", 2)
    chiamate = {"n": 0}

    def fn():
        chiamate["n"] += 1
        raise timeout_57014()

    with pytest.raises(APIError):
        tpb._db_execute(fn, what="test")
    assert chiamate["n"] == 2


# ---------- ALTO-2: secondo giro sulle post_ops ----------

def test_secondo_giro_recupera_le_odds_che_il_rilancio_non_riprenderebbe(monkeypatch):
    """Le odds falliscono nel flush ma passano al secondo giro: registro pulito."""
    stato = {"fallisci": True}

    def policy(descr, _attempts):
        tocca = 9301 in descr["fixture_ids"] or ("eq", "fixture_id", 9301) in descr["filters"]
        if descr["verb"] in ("update", "upsert") and tocca:
            if _ha_colonna(descr, "raw_json_odds") and stato["fallisci"]:
                return timeout_57014()
        return None

    client = FakeSupabaseConTabella(
        fail_policy=policy,
        coverage_rows={(135, 2026): {"predictions": True, "odds": True}},
    )

    # il secondo giro parte dopo il flush: da li' in poi il DB "guarisce"
    vero_retry = tpb._retry_failed_post_ops

    def retry_con_db_guarito():
        stato["fallisci"] = False
        return vero_retry()

    monkeypatch.setattr(tpb, "_retry_failed_post_ops", retry_con_db_guarito)
    _esegui_run_for_date(tpb, monkeypatch, client, [fixture_api(9301, 135)])

    assert tpb._RUN_FAILURES == [], "il secondo giro deve svuotare il registro"
    odds = [d for d in client.executed if _ha_colonna(d, "raw_json_odds")]
    assert len(odds) == 1 and ("eq", "fixture_id", 9301) in odds[0]["filters"]
    assert "raw_json_odds" in client.tabella[9301]
    assert client.tabella[9301]["db_json_analisi"] == {"model": "finto"}, (
        "l'analisi, caduta sulla UPDATE singola, deve essere scritta subito"
    )


def test_secondo_giro_fallito_lascia_la_voce_da_recuperare_a_mano(monkeypatch, caplog):
    def policy(descr, _attempts):
        if descr["verb"] in ("update", "upsert") and _ha_colonna(descr, "raw_json_odds"):
            return timeout_57014()
        return None

    client = FakeSupabaseConTabella(
        fail_policy=policy,
        coverage_rows={(135, 2026): {"predictions": True, "odds": True}},
    )
    _esegui_run_for_date(tpb, monkeypatch, client, [fixture_api(9302, 135)])

    assert [g["operation"] for g in tpb._RUN_FAILURES] == ["odds"]
    assert tpb._RUN_FAILURES[0]["manuale"] is True

    caplog.clear()
    with caplog.at_level("ERROR"):
        tpb._log_failures_summary("2026-09-20")
    righe = [r.getMessage() for r in caplog.records]
    assert any("DA RECUPERARE A MANO: fixture_id=9302, operazione=odds" in r for r in righe)


def test_secondo_giro_saltato_se_il_freno_e_attivo(monkeypatch):
    """A freno attivo non si ritenta nulla: niente martellamento."""
    tpb._record_failure(9303, "odds", timeout_57014(),
                        payload={"kind": "odds", "row": odds_row()}, manuale=True)
    monkeypatch.setattr(tpb, "_DB_MAX_FAILED_REQUESTS", 0)

    client = FakeSupabase()
    monkeypatch.setattr(tpb, "get_supabase_client", lambda: client)
    assert tpb._retry_failed_post_ops() == 0
    assert client.attempts == [], "nessuna richiesta al DB a freno attivo"
    assert len(tpb._RUN_FAILURES) == 1


# ---------- ALTO-4: eccezioni dell'API non uccidono piu' il run ----------

@pytest.mark.parametrize("coverage,attesa", [
    ({"predictions": False, "odds": True}, "no_coverage"),
    ({"predictions": True, "odds": True}, "ok"),
])
def test_errore_api_sulle_odds_non_uccide_il_run(monkeypatch, coverage, attesa):
    """Ramo no_coverage: l'eccezione dell'API sulle quote non ferma piu' il for."""
    client = FakeSupabase(coverage_rows={(135, 2026): dict(coverage)})

    api = FakeAPI()
    vero_call = api.call

    def call_con_odds_rotte(path, params=None):
        if path == "/odds":
            raise RuntimeError("API-Football 429 Too Many Requests")
        return vero_call(path, params)

    api.call = call_con_odds_rotte  # type: ignore[method-assign]

    fixtures = [fixture_api(9401, 135), fixture_api(9402, 135)]
    if attesa == "no_coverage":
        _esegui_run_for_date(tpb, monkeypatch, client, fixtures, api=api)
        scritte = [f for d in client.executed if d["verb"] == "upsert" for f in d["fixture_ids"]]
        assert 9401 in scritte and 9402 in scritte, "il run deve arrivare in fondo"
        assert [g["operation"] for g in tpb._RUN_FAILURES] == ["odds-fetch", "odds-fetch"]
    else:
        # ramo ok: semantica ESISTENTE invariata (la fixture diventa 'error')
        _esegui_run_for_date(tpb, monkeypatch, client, fixtures, api=api)
        stati = {f: s for d in client.executed if d["verb"] == "upsert"
                 for f, s in zip(d["fixture_ids"], d["statuses"])}
        assert stati.get(9401) == "error" and stati.get(9402) == "error"


def test_errore_api_su_predictions_non_uccide_il_run(monkeypatch):
    """L'eccezione su /predictions diventa una riga status='error', non una morte."""
    client = FakeSupabase(coverage_rows={(135, 2026): {"predictions": True, "odds": True}})

    api = FakeAPI()
    vero_call = api.call

    def call_rotta(path, params=None):
        if path == "/predictions" and params and params.get("fixture") == "9502":
            raise RuntimeError("Connessione API-Football interrotta")
        return vero_call(path, params)

    api.call = call_rotta  # type: ignore[method-assign]

    fixtures = [fixture_api(9501, 135), fixture_api(9502, 135), fixture_api(9503, 135)]
    _esegui_run_for_date(tpb, monkeypatch, client, fixtures, api=api)

    stati = {f: s for d in client.executed if d["verb"] == "upsert"
             for f, s in zip(d["fixture_ids"], d["statuses"])}
    assert stati == {9501: "ok", 9502: "error", 9503: "ok"}, (
        "le fixture dopo quella rotta devono essere comunque predette"
    )
    assert [g["operation"] for g in tpb._RUN_FAILURES] == ["predictions-fetch"]
    assert tpb._RUN_FAILURES[0]["fixture_id"] == 9502


def test_riga_di_errore_da_ctx_ha_le_stesse_chiavi_del_ramo_error():
    """_error_row_from_ctx deve produrre ESATTAMENTE le chiavi del ramo error."""
    ctx = {k: prediction_row(1)[k] for k in tpb._CTX_KEYS}
    riga = tpb._error_row_from_ctx(ctx, "2026-09-20T12:00:00+00:00", ValueError("x"))
    attese = set(tpb._CTX_KEYS) | set(tpb._PROMOTED_NULL_KEYS) | {
        "status", "error_message", "raw_json", "flat_summary", "updated_at"}
    assert set(riga.keys()) == attese
    assert riga["status"] == "error" and riga["raw_json"] is None
    assert all(riga[k] is None for k in tpb._PROMOTED_NULL_KEYS)


# ---------- B2: eccezioni httpx VERE ----------

def test_errori_httpx_veri_sono_transitori():
    """B2: non classi locali omonime, le classi vere di httpx."""
    import httpx

    assert tpb._is_transient_db_error(httpx.ReadTimeout("timed out")) is True
    assert tpb._is_transient_db_error(httpx.ConnectError("connection refused")) is True
    assert tpb._is_transient_db_error(httpx.ConnectTimeout("timed out")) is True
    assert tpb._is_transient_db_error(httpx.PoolTimeout("pool")) is True
    # un errore httpx NON transitorio resta tale
    assert tpb._is_transient_db_error(httpx.InvalidURL("url")) is False


# ---------- B8: il registro non allaga il log ----------

def test_il_registro_non_logga_una_riga_per_ogni_voce_all_infinito(caplog):
    caplog.clear()
    with caplog.at_level("ERROR"):
        for i in range(120):
            tpb._record_failure(10000 + i, "odds", timeout_57014())
    righe = [r.getMessage() for r in caplog.records]
    per_voce = [r for r in righe if r.startswith("ANOMALIA NON RECUPERATA")]
    assert len(per_voce) == tpb._MAX_FAILURE_LOG_LINES, "dopo 50 voci si smette"
    assert any("anomalie accumulate finora: 100" in r for r in righe)

    # ma il riepilogo finale stampa COMUNQUE tutti gli id
    caplog.clear()
    with caplog.at_level("ERROR"):
        assert tpb._log_failures_summary("2026-09-20") == 120
    dettagli = [r for r in [x.getMessage() for x in caplog.records]
                if r.strip().startswith("- fixture_id=")]
    assert len(dettagli) == 120


# ==============================================================
# 9) QUARTO GIRO: odds e analisi a blocchi, stessi dati
# ==============================================================
# Riferimento: il commit subito PRIMA di questo intervento (odds e analisi
# con una UPDATE per fixture). Stesso scenario sui due moduli, tabella finale
# confrontata colonna per colonna, registro delle anomalie confrontato voce
# per voce.
COMMIT_PRIMA_DEI_BLOCCHI = "16d8d2f"


def _prepara_modulo(monkeypatch, modulo: Any, client: FakeSupabase) -> None:
    monkeypatch.setattr(modulo, "get_supabase_client", lambda: client)
    monkeypatch.setattr(modulo, "_db_sleep", lambda _s: None)
    modulo._reset_failures()
    modulo._reset_retry_budget()


def _odds_distinte(fid: int) -> Dict[str, Any]:
    """Riga di odds con valori propri della fixture (chiavi del vero)."""
    return {
        "raw_json_odds": {"fixture": {"id": fid}, "bookmakers": [{"id": 8, "bets": [fid % 7]}]},
        "updated_at": "2026-09-20T12:00:%02d.111111+00:00" % (fid % 60),
    }


def _analisi_distinta(fid: int) -> Dict[str, Any]:
    return {
        "db_json_analisi": {"model": "poisson_xg_hybrid_dc", "markets": {"o25": fid / 1e5}},
        "ht_predictions": {"is_elite": bool(fid % 2)},
        "updated_at": "2026-09-20T12:01:%02d.222222+00:00" % (fid % 60),
    }


_STATI = ("ok", "no_coverage", "empty", "error")


def _scenario_grande(modulo: Any, ids: List[int]) -> None:
    """Il loop del runner in miniatura: prediction -> odds -> analisi per
    fixture, maybe_flush fra una fixture e l'altra, chunk al DEFAULT di
    produzione del modulo passato (cosi' il test resta legato alla vera
    costante: 100 per 'prima', 25 per 'tpb' dopo la riduzione). Alcune
    fixture senza odds (coverage illeggibile), alcune senza analisi (calcolo
    fallito), alcune senza nessuna delle due."""
    writer = modulo._DeferredWriter()
    for i, fid in enumerate(ids):
        writer.maybe_flush()
        riga = prediction_row(fid, status=_STATI[i % 4])
        riga["updated_at"] = "2026-09-20T11:59:%02d.000000+00:00" % (fid % 60)
        writer.queue_prediction(riga)
        if i % 7 != 3:
            writer.queue_odds(fid, _odds_distinte(fid))
        if i % 5 != 2:
            writer.queue_analysis(fid, _analisi_distinta(fid))
    writer.flush()


def _righe_preesistenti(ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """Righe gia' sul DB da un run precedente, con colonne che NESSUNA delle
    scritture di oggi tocca (risultati) e vecchie odds/analisi: le colonne non
    riscritte devono restare intatte, come con la UPDATE."""
    out = {}
    for fid in ids:
        r = prediction_row(fid, status="error")
        r["result_home_goals"] = 2
        r["result_outcome"] = "1"
        r["raw_json_odds"] = {"vecchie": True}
        r["db_json_analisi"] = {"vecchia": True}
        r["ht_predictions"] = {"vecchie": True}
        out[fid] = r
    return out


def _registro(modulo: Any) -> List[Any]:
    return [(v["fixture_id"], v["operation"], v["manuale"], v["payload"])
            for v in modulo._RUN_FAILURES]


def test_post_ops_a_blocchi_stesse_tabelle_e_meno_chiamate(tmp_path, monkeypatch):
    """300 fixture: stessa tabella finale del percorso a UPDATE singole, con
    una frazione delle richieste. Stampa i conteggi (pytest -s)."""
    prima = _carica_modulo_originale(tmp_path, COMMIT_PRIMA_DEI_BLOCCHI)
    assert not hasattr(prima._DeferredWriter, "_write_post_ops"), "riferimento sbagliato"

    ids = list(range(20001, 20301))
    gia_su_db = _righe_preesistenti(ids[::10])

    client_prima = FakeSupabaseConTabella(tabella=gia_su_db)
    _prepara_modulo(monkeypatch, prima, client_prima)
    _scenario_grande(prima, ids)

    client_ora = FakeSupabaseConTabella(tabella=gia_su_db)
    _prepara_modulo(monkeypatch, tpb, client_ora)
    _scenario_grande(tpb, ids)

    assert client_ora.tabella == client_prima.tabella, "stessi dati, riga per riga"
    assert sorted(client_ora.tabella) == ids
    # le colonne che nessuno scrive oggi restano intatte
    for fid in ids[::10]:
        assert client_ora.tabella[fid]["result_home_goals"] == 2

    n_odds = sum(1 for i in range(len(ids)) if i % 7 != 3)
    n_analisi = sum(1 for i in range(len(ids)) if i % 5 != 2)
    w_prima = _scritture(client_prima)
    w_ora = _scritture(client_ora)
    assert len(w_prima) == 3 + n_odds + n_analisi

    # Upsert "puri" delle sole predizioni (colonne senza odds/analisi): uno
    # per flush, quindi 300/chunk_size. 'prima' e' rimasto a 100 (3 flush);
    # 'tpb' e' sceso a 25 (nuovo default produzione, 12 flush). Falsifica:
    # rimettendo 100 come default di _DeferredWriter in today_predictions_
    # backfill.py, pred_pure_ora torna a 3 e questa assert va rossa.
    def _predizioni_pure(scritture: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [d for d in scritture if d["verb"] == "upsert"
                and not _ha_colonna(d, "raw_json_odds")
                and not _ha_colonna(d, "db_json_analisi")]

    pred_pure_prima = _predizioni_pure(w_prima)
    pred_pure_ora = _predizioni_pure(w_ora)
    assert len(pred_pure_prima) == 3, "300 / 100 (default di 'prima') = 3 upsert di predizioni pure"
    assert len(pred_pure_ora) == 12, "300 / 25 (nuovo default di produzione) = 12 upsert di predizioni pure"

    assert [d for d in w_ora if d["verb"] == "update"] == []
    # 12 flush da 25 predizioni: ogni flush sta sotto _POST_OPS_CHUNK_SIZE
    # (25), quindi al piu' 1 blocco di post_ops per gruppo di chiavi x flush
    # (al piu' 3 gruppi di chiavi possibili) + le 12 predizioni pure.
    assert len(w_ora) <= 12 + 3 * 1 * 12, "al piu' 3 gruppi di chiavi x 1 blocco da 25 per flush"
    assert client_ora.failed == [] and client_prima.failed == []
    assert tpb._RUN_FAILURES == [] and prima._RUN_FAILURES == []
    print("\nRICHIESTE DI SCRITTURA per %d fixture: prima %d (upsert %d + update %d), ora %d"
          % (len(ids), len(w_prima),
             sum(1 for d in w_prima if d["verb"] == "upsert"),
             sum(1 for d in w_prima if d["verb"] == "update"), len(w_ora)))


def test_post_ops_riga_assente_nessun_insert_monco(tmp_path, monkeypatch, caplog):
    """Odds/analisi di una fixture SENZA riga di prediction nel flush: resta
    la UPDATE di sempre. Riga assente -> non si scrive nulla (mai un insert
    monco); riga gia' presente -> aggiornata come prima."""
    prima = _carica_modulo_originale(tmp_path, COMMIT_PRIMA_DEI_BLOCCHI)
    gia_su_db = _righe_preesistenti([12002])

    def scenario(modulo: Any) -> None:
        writer = modulo._DeferredWriter(chunk_size=100)
        writer.queue_prediction(prediction_row(12003))
        writer.queue_odds(12003, _odds_distinte(12003))
        for fid in (12001, 12002):
            writer.queue_odds(fid, _odds_distinte(fid))
            writer.queue_analysis(fid, _analisi_distinta(fid))
        writer.flush()

    client_prima = FakeSupabaseConTabella(tabella=gia_su_db)
    _prepara_modulo(monkeypatch, prima, client_prima)
    scenario(prima)

    client_ora = FakeSupabaseConTabella(tabella=gia_su_db)
    _prepara_modulo(monkeypatch, tpb, client_ora)
    with caplog.at_level("WARNING"):
        caplog.clear()
        scenario(tpb)

    assert 12001 not in client_ora.tabella, "nessuna riga monca inserita"
    assert client_ora.tabella == client_prima.tabella
    # nemmeno TENTATO un upsert per le fixture senza riga appena scritta
    tentati = {f for d in client_ora.attempts if d["verb"] == "upsert" for f in d["fixture_ids"]}
    assert tentati == {12003}
    assert client_ora.failed == []
    aggiornate = sorted(val for d in client_ora.executed if d["verb"] == "update"
                        for (op, col, val) in d["filters"] if col == "fixture_id")
    assert aggiornate == [12001, 12001, 12002, 12002]
    avvisi = [r.getMessage() for r in caplog.records]
    assert any("fixture_id=12001 (odds non salvate)" in a for a in avvisi)
    assert any("fixture_id=12001 (dati non salvati)" in a for a in avvisi)
    assert tpb._RUN_FAILURES == []


def test_post_ops_riga_ok_riscritta_come_error_riceve_le_update_di_sempre(tmp_path, monkeypatch):
    """La riga ok che non passa diventa 'error' (semantica storica): le sue
    odds/analisi vanno con la UPDATE di sempre, sulla riga di errore."""
    prima = _carica_modulo_originale(tmp_path, COMMIT_PRIMA_DEI_BLOCCHI)

    def policy(descr, _attempts):
        if descr["verb"] != "upsert" or _ha_colonna(descr, "raw_json_odds") or _ha_colonna(descr, "db_json_analisi"):
            return None
        if 13001 in descr["fixture_ids"] and "ok" in descr["statuses"]:
            return timeout_57014()
        return None

    def scenario(modulo: Any) -> None:
        writer = modulo._DeferredWriter(chunk_size=100)
        for fid in (13001, 13002, 13003):
            writer.queue_prediction(prediction_row(fid))
            writer.queue_odds(fid, _odds_distinte(fid))
            writer.queue_analysis(fid, _analisi_distinta(fid))
        writer.flush()

    client_prima = FakeSupabaseConTabella(fail_policy=policy)
    _prepara_modulo(monkeypatch, prima, client_prima)
    scenario(prima)

    client_ora = FakeSupabaseConTabella(fail_policy=policy)
    _prepara_modulo(monkeypatch, tpb, client_ora)
    scenario(tpb)

    assert client_ora.tabella[13001]["status"] == "error"
    assert client_ora.tabella[13001]["raw_json_odds"] == _odds_distinte(13001)["raw_json_odds"]
    assert client_ora.tabella == client_prima.tabella
    assert _registro(tpb) == _registro(prima)
    aggiornate = sorted(val for d in client_ora.executed if d["verb"] == "update"
                        for (op, col, val) in d["filters"] if col == "fixture_id")
    assert aggiornate == [13001, 13001], "solo la fixture non confermata usa la UPDATE"


def test_57014_sul_blocco_post_ops_dimezza_e_stesse_righe(tmp_path, monkeypatch):
    """57014 sui blocchi di odds/analisi oltre 3 righe: 10 -> 5+5 -> 2+3+2+3."""
    prima = _carica_modulo_originale(tmp_path, COMMIT_PRIMA_DEI_BLOCCHI)
    ids = list(range(14001, 14011))

    def scenario(modulo: Any) -> None:
        writer = modulo._DeferredWriter(chunk_size=100)
        for fid in ids:
            writer.queue_prediction(prediction_row(fid))
            writer.queue_odds(fid, _odds_distinte(fid))
            writer.queue_analysis(fid, _analisi_distinta(fid))
        writer.flush()

    def policy(descr, _attempts):
        if _ha_colonna(descr, "raw_json_odds") and len(descr["fixture_ids"]) > 3:
            return timeout_57014()
        return None

    client_prima = FakeSupabaseConTabella()
    _prepara_modulo(monkeypatch, prima, client_prima)
    scenario(prima)

    client_ora = FakeSupabaseConTabella(fail_policy=policy)
    _prepara_modulo(monkeypatch, tpb, client_ora)
    scenario(tpb)

    blocchi = [d["fixture_ids"] for d in client_ora.executed if _ha_colonna(d, "raw_json_odds")]
    assert blocchi == [tuple(ids[0:2]), tuple(ids[2:5]), tuple(ids[5:7]), tuple(ids[7:10])]
    assert client_ora.tabella == client_prima.tabella
    assert tpb._RUN_FAILURES == []
    assert [d for d in client_ora.executed if d["verb"] == "update"] == []


def test_post_ops_riga_singola_fallita_ricade_sulle_update_e_registro_identico(tmp_path, monkeypatch):
    """Odds di 15002 non scrivibili: il blocco si dimezza fino alla riga,
    la riga ricade sulle UPDATE di sempre. Tabella e registro (operazione,
    manuale, payload del secondo giro) identici al percorso storico."""
    prima = _carica_modulo_originale(tmp_path, COMMIT_PRIMA_DEI_BLOCCHI)
    ids = [15001, 15002, 15003, 15004]

    def policy(descr, _attempts):
        tocca = 15002 in descr["fixture_ids"] or ("eq", "fixture_id", 15002) in descr["filters"]
        if tocca and _ha_colonna(descr, "raw_json_odds"):
            return timeout_57014()
        return None

    def scenario(modulo: Any) -> None:
        writer = modulo._DeferredWriter(chunk_size=100)
        for fid in ids:
            writer.queue_prediction(prediction_row(fid))
            writer.queue_odds(fid, _odds_distinte(fid))
            writer.queue_analysis(fid, _analisi_distinta(fid))
        writer.flush()

    client_prima = FakeSupabaseConTabella(fail_policy=policy)
    _prepara_modulo(monkeypatch, prima, client_prima)
    scenario(prima)

    client_ora = FakeSupabaseConTabella(fail_policy=policy)
    _prepara_modulo(monkeypatch, tpb, client_ora)
    scenario(tpb)

    assert client_ora.tabella == client_prima.tabella
    assert "raw_json_odds" not in client_ora.tabella[15002]
    assert client_ora.tabella[15002]["db_json_analisi"] == _analisi_distinta(15002)["db_json_analisi"]
    assert _registro(tpb) == _registro(prima)
    assert _registro(tpb) == [(15002, "odds", True, {"kind": "odds", "row": _odds_distinte(15002)})]


def test_freno_attivo_sui_blocchi_post_ops_ricade_sulle_update(tmp_path, monkeypatch):
    """Freno DB: niente dimezzamento, le UPDATE di sempre (un tentativo
    ciascuna) registrano le stesse fixture del percorso storico."""
    prima = _carica_modulo_originale(tmp_path, COMMIT_PRIMA_DEI_BLOCCHI)
    ids = list(range(16001, 16013))

    def policy(descr, _attempts):
        if _ha_colonna(descr, "raw_json_odds"):
            return timeout_57014()
        return None

    def scenario(modulo: Any) -> None:
        writer = modulo._DeferredWriter(chunk_size=100)
        for fid in ids:
            writer.queue_prediction(prediction_row(fid))
            writer.queue_odds(fid, _odds_distinte(fid))
            writer.queue_analysis(fid, _analisi_distinta(fid))
        writer.flush()

    for modulo in (prima, tpb):
        monkeypatch.setattr(modulo, "_DB_MAX_FAILED_REQUESTS", 5)

    client_prima = FakeSupabaseConTabella(fail_policy=policy)
    _prepara_modulo(monkeypatch, prima, client_prima)
    scenario(prima)

    client_ora = FakeSupabaseConTabella(fail_policy=policy)
    _prepara_modulo(monkeypatch, tpb, client_ora)
    scenario(tpb)

    assert client_ora.tabella == client_prima.tabella
    assert _registro(tpb) == _registro(prima)
    assert {v[0] for v in _registro(tpb)} == set(ids)
    assert len(client_ora.attempts) <= len(client_prima.attempts) + 5


def test_run_for_date_stessa_tabella_del_percorso_a_update_singole(tmp_path, monkeypatch):
    """End-to-end sul runner vero: stessa tabella finale (timestamp inclusi)
    del commit precedente, stesse chiamate API, meno richieste di scrittura."""
    prima = _carica_modulo_originale(tmp_path, COMMIT_PRIMA_DEI_BLOCCHI)
    _ferma_orologio(monkeypatch, prima)
    _ferma_orologio(monkeypatch, tpb)

    fixtures = [fixture_api(17000 + i, 135 if i % 3 else 140) for i in range(1, 31)]
    coverage = {
        (135, 2026): {"predictions": True, "odds": True},
        (140, 2026): {"predictions": False, "odds": True},
    }
    gia_su_db = _righe_preesistenti([17003, 17010])

    client_prima = FakeSupabaseConTabella(coverage_rows=dict(coverage), tabella=gia_su_db)
    _prepara_modulo(monkeypatch, prima, client_prima)
    api_prima = _esegui_run_for_date(prima, monkeypatch, client_prima, list(fixtures))

    client_ora = FakeSupabaseConTabella(coverage_rows=dict(coverage), tabella=gia_su_db)
    _prepara_modulo(monkeypatch, tpb, client_ora)
    api_ora = _esegui_run_for_date(tpb, monkeypatch, client_ora, list(fixtures))

    assert client_ora.tabella == client_prima.tabella
    assert len(client_ora.tabella) == 30
    assert api_ora.calls == api_prima.calls
    assert tpb._RUN_FAILURES == [] and prima._RUN_FAILURES == []
    assert len(_scritture(client_prima)) == 1 + 30 + 30
    # 30 righe, blocco iniziale ora 25 (prima 100): 2 flush (25 + 5) invece
    # di 1, quindi 2 upsert di predizioni pure + 2 upsert di post_ops uniti
    # (uno per flush, tutti sotto _POST_OPS_CHUNK_SIZE=25) = 4, non piu' <=3.
    assert len(_scritture(client_ora)) <= 4


def test_post_ops_fixture_duplicata_nel_flush_usa_le_update_di_sempre(tmp_path, monkeypatch):
    """Stessa fixture DUE volte nello stesso flush (riga ok, poi riga error).

    queue_prediction lo impedisce flushando prima, quindi il caso si
    costruisce accodando direttamente in _pred_rows: e' la difesa in
    profondita' di _write_post_ops. Postgres rifiuta un upsert che tocca la
    stessa riga due volte (21000): il blocco si dimezza fino alle righe
    singole. La riga ok passa, la riga error NO: sul DB resta la riga ok e le
    UPDATE di odds/analisi si applicano su quella. Se il percorso a blocchi
    accettasse la fixture duplicata, fonderebbe odds/analisi con l'ULTIMA
    riga accodata (la error, mai scritta) e la tabella cambierebbe."""
    prima = _carica_modulo_originale(tmp_path, COMMIT_PRIMA_DEI_BLOCCHI)

    riga_ok = prediction_row(18001, status="ok")
    riga_err = prediction_row(18001, status="error")
    riga_err["error_message"] = "seconda scrittura"
    riga_err["updated_at"] = "2026-09-20T12:30:00.000000+00:00"

    def policy(descr, _attempts):
        if descr["verb"] != "upsert":
            return None
        ids = descr["fixture_ids"]
        if len(ids) != len(set(ids)):
            return api_error("21000", "ON CONFLICT DO UPDATE command cannot affect row a second time")
        # solo la scrittura della riga di prediction 'error' e' rifiutata
        # (non le righe con odds/analisi: cosi' un percorso a blocchi
        # sbagliato scriverebbe davvero la riga error e si vedrebbe)
        solo_pred = not _ha_colonna(descr, "raw_json_odds") and not _ha_colonna(descr, "db_json_analisi")
        if solo_pred and any(f == 18001 and s == "error" for f, s in zip(ids, descr["statuses"])):
            return api_error("23514", "new row violates check constraint")
        return None

    def scenario(modulo: Any) -> None:
        writer = modulo._DeferredWriter(chunk_size=100)
        writer._pred_rows.extend([dict(riga_ok), dict(riga_err), prediction_row(18002)])
        writer._post_ops.extend([
            ("odds", 18001, _odds_distinte(18001)),
            ("analysis", 18001, _analisi_distinta(18001)),
            ("odds", 18002, _odds_distinte(18002)),
            ("analysis", 18002, _analisi_distinta(18002)),
        ])
        writer.flush()

    client_prima = FakeSupabaseConTabella(fail_policy=policy)
    _prepara_modulo(monkeypatch, prima, client_prima)
    scenario(prima)

    client_ora = FakeSupabaseConTabella(fail_policy=policy)
    _prepara_modulo(monkeypatch, tpb, client_ora)
    scenario(tpb)

    assert client_ora.tabella[18001]["status"] == "ok"
    assert client_ora.tabella == client_prima.tabella
    assert _registro(tpb) == _registro(prima)
    # la fixture duplicata non passa MAI dal percorso a blocchi
    unite = [d for d in client_ora.attempts
             if d["verb"] == "upsert" and _ha_colonna(d, "raw_json_odds")]
    assert all(18001 not in d["fixture_ids"] for d in unite)
    assert [d["fixture_ids"] for d in unite] == [(18002,)]
    aggiornate = sorted(val for d in client_ora.executed if d["verb"] == "update"
                        for (op, col, val) in d["filters"] if col == "fixture_id")
    assert aggiornate == [18001, 18001]


def test_il_finto_rifiuta_la_riga_monca_come_postgres():
    """Sanita' del finto: senza status la riga proposta viola il NOT NULL
    anche se la riga esiste (Postgres controlla prima del conflitto)."""
    client = FakeSupabaseConTabella(tabella={1: prediction_row(1)})
    with pytest.raises(APIError) as ex:
        client.table("fixture_predictions").upsert(
            {"fixture_id": 1, **odds_row()}, on_conflict="fixture_id").execute()
    assert ex.value.code == "23502"
    assert client.tabella[1] == prediction_row(1), "richiesta fallita: nulla scritto"
    with pytest.raises(APIError) as ex2:
        client.table("fixture_predictions").upsert(
            [prediction_row(2), {**prediction_row(3), **odds_row()}], on_conflict="fixture_id").execute()
    assert ex2.value.code == "PGRST102"
