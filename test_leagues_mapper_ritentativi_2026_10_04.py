# test_leagues_mapper_ritentativi_2026_10_04.py
# Ritentativi del mapper sugli errori TRANSITORI di Supabase (522/520 Cloudflare,
# PGRST002, 57014, rete): run KO il 02, 03 e 04/10. Il finto client alza la STESSA
# eccezione del vero (postgrest.exceptions.APIError con dict {message, code (int),
# details HTML, hint}, come nei log). Nessuna attesa reale: time.sleep e' intercettato.
from __future__ import annotations

from typing import Any, Dict, List

import httpx
import pytest
from postgrest.exceptions import APIError

import leagues_mapper as lm
from test_actions_fail_rumoroso_2026_09_25 import FintoApi, lega_api


def errore_cf(codice: Any = 522) -> APIError:
    """Come nei log veri: la pagina HTML di Cloudflare dentro l'APIError."""
    return APIError({"message": "JSON could not be generated", "code": codice,
                     "hint": None,
                     "details": "b'<!DOCTYPE html>\\n<html lang=\"en-US\"><head><title>"
                                "supabase.co | 522: Connection timed out</title>'"})


class _Risp:
    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.data = data


class _Q:
    def __init__(self, sb: "Finto", tab: str) -> None:
        self.sb, self.tab, self.op, self.payload, self.filtri = sb, tab, "select", None, []
        self.intervallo = (0, 999)

    def select(self, c): self.op = "select"; return self
    def order(self, c, desc=False): return self
    def range(self, a, b): self.intervallo = (a, b); return self
    def upsert(self, r): self.op = "upsert"; self.payload = r; return self
    def update(self, p): self.op = "update"; self.payload = p; return self
    def eq(self, c, v): self.filtri.append((c, v)); return self

    def execute(self) -> _Risp:
        self.sb.tentativi[self.op] += 1
        coda = self.sb.errori[self.op]
        if coda:
            raise coda.pop(0)
        if self.op == "select":
            a, b = self.intervallo
            return _Risp(list(self.sb.righe)[a:b + 1])
        if self.op == "update":
            self.sb.scritture.append(("update", tuple(self.filtri), dict(self.payload)))
        else:
            self.sb.scritture.append(("upsert", None, list(self.payload)))
        return _Risp([])


class Finto:
    """Finto Supabase: `errori[op]` e' la coda di eccezioni da alzare, una per tentativo."""

    def __init__(self, righe=None, **errori) -> None:
        self.righe = righe or []
        self.errori = {"select": [], "update": [], "upsert": []}
        for k, v in errori.items():
            self.errori[k] = list(v)
        self.tentativi = {"select": 0, "update": 0, "upsert": 0}
        self.scritture: List[Any] = []

    def table(self, nome: str) -> _Q:
        assert nome == "api_coverage_by_season"
        return _Q(self, nome)


@pytest.fixture
def attese(monkeypatch):
    v: List[float] = []
    monkeypatch.setattr(lm.time, "sleep", lambda s: v.append(s))
    return v


def _prepara(monkeypatch, sb: Finto, leghe=None) -> None:
    monkeypatch.setattr(lm, "get_supabase_client", lambda: sb)
    monkeypatch.setattr(lm, "APIFootballClient",
                        lambda: FintoApi({"/leagues": {"response": leghe or [lega_api(135, [2026])]}}))


def _riga_db_vecchia() -> Dict[str, Any]:
    """Riga del DB con flag diversi dall'API: genera un UPDATE."""
    r = dict(lm.map_leagues_to_coverage_rows({"response": [lega_api(135, [2026])]})[0])
    r["fixtures_lineups"] = not r["fixtures_lineups"]
    return r


# ---------------------------------------------------------------- LETTURA
def test_lettura_522_due_volte_poi_ok(monkeypatch, attese):
    sb = Finto([{"league_id": 1, "season_year": 2026}], select=[errore_cf(522), errore_cf(522)])
    monkeypatch.setattr(lm, "get_supabase_client", lambda: sb)
    righe = lm.get_existing_coverage_rows()
    assert list(righe) == [(1, 2026)]
    assert sb.tentativi["select"] == 3
    assert attese == [5, 15]                      # attesa crescente


def test_lettura_cinque_fallimenti_runtime_error_come_oggi(monkeypatch, attese):
    sb = Finto(select=[errore_cf(522)] * 9)
    monkeypatch.setattr(lm, "get_supabase_client", lambda: sb)
    with pytest.raises(RuntimeError, match="lettura api_coverage_by_season fallita"):
        lm.get_existing_coverage_rows()
    assert sb.tentativi["select"] == 5
    assert attese == [5, 15, 45, 90]


def test_lettura_errore_non_transitorio_nessun_ritentativo(monkeypatch, attese):
    sb = Finto(select=[APIError({"message": "permission denied", "code": "42501",
                                 "details": None, "hint": None})])
    monkeypatch.setattr(lm, "get_supabase_client", lambda: sb)
    with pytest.raises(RuntimeError):
        lm.get_existing_coverage_rows()
    assert sb.tentativi["select"] == 1
    assert attese == []


@pytest.mark.parametrize("err", [
    APIError({"message": "Could not query the database for the schema cache. Retrying.",
              "code": "PGRST002", "details": None, "hint": None}),
    APIError({"message": "canceling statement due to statement timeout", "code": "57014",
              "details": None, "hint": None}),
    errore_cf(520), errore_cf("503"),
    httpx.ReadTimeout("timed out"), httpx.ConnectError("boom"),
])
def test_lettura_ritenta_ogni_transitorio(monkeypatch, attese, err):
    sb = Finto([{"league_id": 1, "season_year": 2026}], select=[err])
    monkeypatch.setattr(lm, "get_supabase_client", lambda: sb)
    assert list(lm.get_existing_coverage_rows()) == [(1, 2026)]
    assert sb.tentativi["select"] == 2


# ---------------------------------------------------------------- UPDATE
def test_update_522_due_volte_poi_ok_una_sola_scrittura(monkeypatch, attese):
    sb = Finto([_riga_db_vecchia()], update=[errore_cf(520), errore_cf(522)])
    _prepara(monkeypatch, sb)
    lm.run_full_leagues_backfill_mapping()          # exit 0: nessuna SystemExit
    assert sb.tentativi["update"] == 3
    upd = [s for s in sb.scritture if s[0] == "update"]
    assert len(upd) == 1                            # UNA sola scrittura effettiva
    assert upd[0][1] == (("league_id", 135), ("season_year", 2026))
    assert set(upd[0][2]) == {"fixtures_lineups", "updated_at"}   # solo il diff + updated_at
    assert attese == [5, 15]


def test_update_stessi_dati_con_e_senza_errore(monkeypatch, attese):
    puliti = Finto([_riga_db_vecchia()])
    _prepara(monkeypatch, puliti)
    lm.run_full_leagues_backfill_mapping()
    con_errore = Finto([_riga_db_vecchia()], update=[errore_cf(522)])
    _prepara(monkeypatch, con_errore)
    lm.run_full_leagues_backfill_mapping()
    a, b = puliti.scritture[0], con_errore.scritture[0]
    assert a[0:2] == b[0:2]
    assert {k: v for k, v in a[2].items() if k != "updated_at"} == \
           {k: v for k, v in b[2].items() if k != "updated_at"}


def test_update_cinque_fallimenti_esce_rosso_come_oggi(monkeypatch, attese):
    sb = Finto([_riga_db_vecchia()], update=[errore_cf(520)] * 9)
    _prepara(monkeypatch, sb)
    with pytest.raises(SystemExit) as ex:
        lm.run_full_leagues_backfill_mapping()
    assert "1 batch in errore NON previsto" in str(ex.value.code)
    assert sb.tentativi["update"] == 5
    assert sb.scritture == []


def test_update_errore_non_transitorio_nessun_ritentativo(monkeypatch, attese):
    sb = Finto([_riga_db_vecchia()],
               update=[APIError({"message": "bad", "code": "23514", "details": None, "hint": None})])
    _prepara(monkeypatch, sb)
    with pytest.raises(SystemExit):
        lm.run_full_leagues_backfill_mapping()
    assert sb.tentativi["update"] == 1
    assert attese == []


# ---------------------------------------------------------------- INSERT (upsert)
def test_upsert_520_poi_ok_righe_scritte_una_volta(monkeypatch, attese):
    sb = Finto([], upsert=[errore_cf(520)])
    _prepara(monkeypatch, sb)
    lm.run_full_leagues_backfill_mapping()
    assert sb.tentativi["upsert"] == 2
    ups = [s for s in sb.scritture if s[0] == "upsert"]
    assert len(ups) == 1 and [(r["league_id"], r["season_year"]) for r in ups[0][2]] == [(135, 2026)]


def test_upsert_duplicato_resta_tollerato_senza_ritentativi(monkeypatch, attese):
    sb = Finto([], upsert=[APIError({
        "message": 'duplicate key value violates unique constraint "api_coverage_by_season_pkey"',
        "code": "23505", "details": None, "hint": None})])
    _prepara(monkeypatch, sb)
    lm.run_full_leagues_backfill_mapping()
    assert sb.tentativi["upsert"] == 1
    assert [a for a in attese if a >= 5] == []      # (0,2 s = pausa gia' esistente tra i batch)
