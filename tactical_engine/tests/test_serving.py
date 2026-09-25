"""Test del serving del Tactical Engine (reperti R1 e R2, 25/09/2026).

R1: le partite del giorno si leggono da `fixture_predictions` (non da `matches`, che
    contiene solo partite finite): su 5 partite di 2 leghe si scrivono 5 payload.
R2: `_load_prior` legge lo storico a pagine keyset con ORDER BY su una chiave
    univoca: stesso insieme e stesso ordine con e senza paginazione.

Il client Supabase e' un FINTO che imita il query builder di postgrest-py
(select/eq/lt/gte/gt/order/limit/update/execute -> oggetto con `.data`) e REGISTRA
ogni query. Le righe finte hanno le stesse chiavi e gli stessi tipi del vero:
  - fixture_predictions: fixture_id, league_id, league_name, season_year,
    fixture_date (ISO str), home/away_team_id (int), home/away_team_name (str),
    status (stato della PREDIZIONE API), result_status_short (NULL pre-partita),
    tactical_engine_json;
  - matches: fixture_id, league_id, fixture_date, status_short, home/away_team_id,
    goals_*, halftime_*, fulltime_* (int o None).
Senza `.order()` il finto restituisce le righe in un ordine "fisico" rimescolato,
come PostgreSQL senza ORDER BY: e' cio' che rende rossa una paginazione senza ordine.
Il finto puo' anche troncare ogni risposta a `max_rows` righe, come PostgREST.
"""
from __future__ import annotations

import os
import random
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tactical_engine import serving  # noqa: E402

# ---------------------------------------------------------------- finto client


class _Query:
    def __init__(self, db: "FakeSupabase", table: str) -> None:
        self.db = db
        self.table = table
        self.cols: Optional[str] = None
        self.filters: List[tuple] = []
        self.order_col: Optional[str] = None
        self.limit_n: Optional[int] = None
        self.update_payload: Optional[dict] = None

    # --- builder ---
    def select(self, cols: str) -> "_Query":
        self.cols = cols
        return self

    def update(self, payload: dict) -> "_Query":
        self.update_payload = payload
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self.filters.append(("eq", col, val))
        return self

    def lt(self, col: str, val: Any) -> "_Query":
        self.filters.append(("lt", col, val))
        return self

    def gte(self, col: str, val: Any) -> "_Query":
        self.filters.append(("gte", col, val))
        return self

    def gt(self, col: str, val: Any) -> "_Query":
        self.filters.append(("gt", col, val))
        return self

    def order(self, col: str, desc: bool = False) -> "_Query":
        assert not desc, "il finto supporta solo ORDER BY ascendente"
        self.order_col = col
        return self

    def limit(self, n: int) -> "_Query":
        self.limit_n = n
        return self

    # --- esecuzione ---
    def _match(self, r: dict) -> bool:
        for op, col, val in self.filters:
            v = r.get(col)
            if col == "fixture_date":
                # confronto temporale vero (le stringhe ISO con offset diversi non
                # si confrontano lessicograficamente)
                v = serving.parse_iso(v) if v else None
                val = serving.parse_iso(val)
            if v is None:
                return False
            if op == "eq" and not v == val:
                return False
            if op == "lt" and not v < val:
                return False
            if op == "gte" and not v >= val:
                return False
            if op == "gt" and not v > val:
                return False
        return True

    def execute(self) -> SimpleNamespace:
        self.db.calls.append(self)
        rows = self.db.tables[self.table]
        if self.update_payload is not None:
            hit = [r for r in rows if self._match(r)]
            for r in hit:
                r.update(self.update_payload)
            return SimpleNamespace(data=[dict(r) for r in hit])
        # ordine "fisico": fisso per tabella ma rimescolato (heap senza ORDER BY)
        out = [r for r in self.db.physical(self.table) if self._match(r)]
        if self.order_col is not None:
            out.sort(key=lambda r: r[self.order_col])
        if self.limit_n is not None:
            out = out[: self.limit_n]
        if self.db.max_rows is not None:
            out = out[: self.db.max_rows]
        cols = [c.strip() for c in (self.cols or "").split(",") if c.strip()]
        return SimpleNamespace(data=[{c: r.get(c) for c in cols} for r in out])


class FakeSupabase:
    def __init__(self, tables: Dict[str, List[dict]], max_rows: Optional[int] = None, seed: int = 7) -> None:
        self.tables = tables
        self.max_rows = max_rows
        self.calls: List[_Query] = []
        self._phys: Dict[str, List[dict]] = {}
        self._seed = seed

    def physical(self, table: str) -> List[dict]:
        if table not in self._phys:
            rows = list(self.tables[table])
            random.Random(self._seed).shuffle(rows)
            self._phys[table] = rows
        return self._phys[table]

    def table(self, name: str) -> _Query:
        return _Query(self, name)


# ---------------------------------------------------------------- dati finti

TODAY = datetime(2026, 9, 25, tzinfo=timezone.utc)


def _match_row(fid: int, league: int, when: datetime, home: int, away: int,
               gh: int, ga: int, hh: Optional[int], ha: Optional[int]) -> dict:
    return {
        "fixture_id": fid, "league_id": league, "fixture_date": when.isoformat(),
        "status_short": "FT", "home_team_id": home, "away_team_id": away,
        "goals_home": gh, "goals_away": ga,
        "halftime_home": hh, "halftime_away": ha,
        "fulltime_home": gh, "fulltime_away": ga,
    }


def _storico_lega(league: int, teams: List[int], n_giornate: int, fid0: int, rng: random.Random) -> List[dict]:
    """Storico FT di una lega: ogni giornata tutte le coppie (casa/trasferta
    alternate), punteggi pseudo-casuali ripetibili; alcune partite senza HT."""
    rows = []
    fid = fid0
    for g in range(n_giornate):
        when = TODAY - timedelta(days=7 * (n_giornate - g))
        for i, h in enumerate(teams):
            for a in teams[i + 1:]:
                home, away = (h, a) if g % 2 == 0 else (a, h)
                gh, ga = rng.randint(0, 4), rng.randint(0, 3)
                hh = min(gh, rng.randint(0, 2))
                ha = min(ga, rng.randint(0, 1))
                if fid % 11 == 0:
                    hh = ha = None
                rows.append(_match_row(fid, league, when, home, away, gh, ga, hh, ha))
                fid += 1
    return rows


def _fp_row(fid: int, league: int, name: str, when: datetime, home: int, away: int,
            result_status: Optional[str] = None) -> dict:
    return {
        "fixture_id": fid, "league_id": league, "league_name": name, "season_year": 2026,
        "fixture_date": when.isoformat(), "home_team_id": home, "home_team_name": f"T{home}",
        "away_team_id": away, "away_team_name": f"T{away}",
        "status": "no_coverage", "result_status_short": result_status,
        "tactical_engine_json": None,
    }


def _mondo() -> FakeSupabase:
    rng = random.Random(2026)
    l1_teams = [101, 102, 103, 104, 105, 106]
    l2_teams = [201, 202, 203, 204, 205]
    matches = _storico_lega(39, l1_teams, 8, 1_000_000, rng) + _storico_lega(135, l2_teams, 9, 2_000_000, rng)
    # NB realistico: `matches` NON contiene le partite di oggi (solo finite).
    fp = [
        _fp_row(9001, 39, "Premier League", TODAY + timedelta(hours=12), 101, 102),
        _fp_row(9002, 39, "Premier League", TODAY + timedelta(hours=14), 103, 104),
        _fp_row(9003, 39, "Premier League", TODAY + timedelta(hours=16), 105, 106),
        _fp_row(9004, 135, "Serie A", TODAY + timedelta(hours=18), 201, 202),
        _fp_row(9005, 135, "Serie A", TODAY + timedelta(hours=20, minutes=45), 203, 204),
        # gia' finita (result_status_short FT): esclusa come prima
        _fp_row(9006, 135, "Serie A", TODAY + timedelta(hours=1), 204, 205, result_status="FT"),
        # di domani: fuori finestra
        _fp_row(9007, 39, "Premier League", TODAY + timedelta(days=1, hours=12), 101, 103),
    ]
    return FakeSupabase({"matches": matches, "fixture_predictions": fp})


@pytest.fixture(autouse=True)
def _mai_db_vero(monkeypatch):
    # Difesa in profondita': se un test dimenticasse il finto, il client vero
    # punterebbe a una porta chiusa (mai al DB di produzione).
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "x")
    monkeypatch.setenv("SUPABASE_KEY", "x")


# ---------------------------------------------------------------- R1


def test_run_for_date_legge_da_fixture_predictions_e_scrive_5_payload(monkeypatch):
    db = _mondo()
    monkeypatch.setattr(serving, "get_supabase_client", lambda: db)

    res = serving.run_for_date("2026-09-25")

    # la lista delle partite del giorno viene da fixture_predictions ...
    letture_fp = [q for q in db.calls if q.table == "fixture_predictions" and q.update_payload is None]
    assert letture_fp, "le partite del giorno devono venire da fixture_predictions"
    assert all(q.cols == serving.TODAY_COLS for q in letture_fp)
    # ... e da `matches` si legge SOLO lo storico precedente alla giornata
    for q in (q for q in db.calls if q.table == "matches"):
        assert ("lt", "fixture_date", TODAY.isoformat()) in q.filters, q.filters
        assert not any(op == "gte" and col == "fixture_date" and val == TODAY.isoformat()
                       for op, col, val in q.filters), "matches letta per le partite di oggi"

    # 5 partite non giocate di oggi su 2 leghe -> 5 payload, tutti UPDATE
    assert res == {"fixtures": 5, "updated": 5, "inserted": 0, "errors": 0}
    scritte = {r["fixture_id"]: r["tactical_engine_json"]
               for r in db.tables["fixture_predictions"] if r["tactical_engine_json"]}
    assert sorted(scritte) == [9001, 9002, 9003, 9004, 9005]
    assert {p["league_id"] for p in scritte.values()} == {39, 135}
    # payload: nome lega ora presente (fixture_predictions ha league_name), stato
    # partita = result_status_short (NULL prima del fischio)
    p = scritte[9004]
    assert p["league_name"] == "Serie A" and p["status"] is None
    assert p["home_name"] == "T201" and p["away_name"] == "T202"
    assert p["date"] == (TODAY + timedelta(hours=18)).isoformat()
    assert abs(sum(p["markets"][k] for k in ("home", "draw", "away")) - 1.0) < 1e-3
    # nessun INSERT: le righe in tabella restano 7, nessun altro campo toccato
    assert len(db.tables["fixture_predictions"]) == 7
    assert all(r["status"] == "no_coverage" for r in db.tables["fixture_predictions"])
    for fid in (9006, 9007):
        riga = next(r for r in db.tables["fixture_predictions"] if r["fixture_id"] == fid)
        assert riga["tactical_engine_json"] is None


def test_run_for_date_pagina_anche_le_partite_del_giorno(monkeypatch):
    """Con il server che tronca a 2 righe la lettura delle partite del giorno deve
    comunque vederle tutte (keyset, uscita solo a pagina vuota)."""
    db = _mondo()
    db.max_rows = 2
    monkeypatch.setattr(serving, "get_supabase_client", lambda: db)
    today = serving._load_today(db, TODAY, TODAY + timedelta(days=1))
    assert sorted(r["fixture_id"] for r in today) == [9001, 9002, 9003, 9004, 9005]


# ---------------------------------------------------------------- R2


def _storico_grande(n: int) -> List[dict]:
    rng = random.Random(11)
    rows = []
    for i in range(n):
        # kickoff a gruppi di 5 simultanei (tiebreaker fixture_id necessario) e
        # fixture_id NON monotono con la data (come nel vero: id API-Football)
        when = TODAY - timedelta(days=1 + (i // 5))
        fid = 5_000_000 + ((i * 7919) % 100_003)
        rows.append(_match_row(fid, 39, when, 100 + (i % 20), 100 + ((i + 7) % 20),
                               rng.randint(0, 4), rng.randint(0, 4), rng.randint(0, 2), rng.randint(0, 2)))
    return rows


def _chiave(m: serving.MatchScoreline) -> tuple:
    return (m.home_id, m.away_id, m.home_goals, m.away_goals)


def test_load_prior_paginato_stesse_partite_stesso_ordine_e_order_by():
    righe = _storico_grande(2500)
    finestra = TODAY - timedelta(days=4.0 * serving.HALF_LIFE_CLUB / 0.6931471805599453)
    attese = sorted((r for r in righe if serving.parse_iso(r["fixture_date"]) >= finestra),
                    key=lambda r: (r["fixture_date"], r["fixture_id"]))
    assert len(attese) == 2500  # tutto dentro la finestra delle 4 emivite

    # riferimento SENZA paginazione: una sola pagina che contiene tutto
    db_tutto = FakeSupabase({"matches": [dict(r) for r in righe]})
    ft_ref, d_ref, ht_ref, hd_ref = serving._load_prior(db_tutto, 39, TODAY, page_size=10_000_000)

    # paginato: pagine da 1000 (default) e server che tronca a 1000 (max_rows)
    db_pag = FakeSupabase({"matches": [dict(r) for r in righe]}, max_rows=1000)
    ft, d, ht, hd = serving._load_prior(db_pag, 39, TODAY)

    assert len(ft) == len(ft_ref) == 2500
    assert [_chiave(m) for m in ft] == [_chiave(m) for m in ft_ref]
    assert d == d_ref and [_chiave(m) for m in ht] == [_chiave(m) for m in ht_ref] and hd == hd_ref
    # ordine cronologico deterministico (fixture_date, fixture_id)
    assert [_chiave(m) for m in ft] == [(r["home_team_id"], r["away_team_id"], r["goals_home"], r["goals_away"])
                                        for r in attese]
    assert d == sorted(d)

    # ogni pagina chiesta con ORDER BY sulla chiave univoca, LIMIT 1000 e cursore
    pagine = [q for q in db_pag.calls if q.table == "matches"]
    assert len(pagine) == 4  # 1000 + 1000 + 500 + pagina vuota
    assert all(q.order_col == "fixture_id" and q.limit_n == 1000 for q in pagine)
    assert [f for f in pagine[0].filters if f[0] == "gt"] == []
    assert all(any(f[0] == "gt" and f[1] == "fixture_id" for f in q.filters) for q in pagine[1:])


def test_fit_invariante_all_ordine_delle_righe_entro_la_tolleranza_dell_ottimizzatore():
    """Il fit dipende dall'INSIEME delle partite; l'ordine delle righe cambia solo
    l'ordine delle somme in virgola mobile, che L-BFGS-B (ftol 1e-8) amplifica fino
    a ~1e-4 sulle probabilita' arrotondate a 4 decimali. MISURATO: con l'ordine
    rimescolato 'away' passa da 0.1983 a 0.1982. Prima del 25/09 l'ordine era quello
    fisico della tabella (arbitrario): lo stesso scarto era gia' possibile fra due
    run; ora l'ordine e' fisso (fixture_date, fixture_id) e il risultato ripetibile."""
    from tactical_engine.model import DixonColesModel

    rng = random.Random(5)
    righe = _storico_lega(39, [101, 102, 103, 104, 105, 106], 8, 1_000_000, rng)
    ft = [serving.MatchScoreline(r["home_team_id"], r["away_team_id"], r["goals_home"], r["goals_away"])
          for r in righe]
    dd = [serving.parse_iso(r["fixture_date"]) for r in righe]
    perm = list(range(len(ft)))
    random.Random(99).shuffle(perm)

    def _pred(ms, ds):
        m = DixonColesModel(max_goals=10, half_life_days=serving.HALF_LIFE_CLUB, ridge=serving.RIDGE)
        m.fit(ms, dates=ds, ref_date=TODAY, fit_home_adv=True)
        p = m.predict(101, 102)
        return round(p["lambda_home"], 3), round(p["lambda_away"], 3), serving._round_markets(p["markets"])

    a = _pred(ft, dd)
    b = _pred([ft[i] for i in perm], [dd[i] for i in perm])
    assert abs(a[0] - b[0]) <= 2e-3 and abs(a[1] - b[1]) <= 2e-3
    assert a[2].keys() == b[2].keys()
    assert max(abs(a[2][k] - b[2][k]) for k in a[2]) <= 3e-4
    # stesso ordine -> stesso risultato, bit per bit (riproducibilita')
    assert _pred(ft, dd) == a
