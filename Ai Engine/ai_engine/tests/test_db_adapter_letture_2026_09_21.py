"""Letture di db_adapter: equivalenza dei dati, ordine deterministico, retry.

Nessun accesso al database: il finto parla come il vero (stesse colonne e tipi di
match_odds e fixture_predictions, APIError di postgrest con le chiavi
message/code/hint/details). Nessun modulo della libreria standard viene mutato:
si inietta un attributo sul modulo di produzione.

Cosa si dimostra:
- le righe lette dopo il fix sono LE STESSE di prima (stesso insieme, senza
  duplicati ne' buchi), anche con pagine piccole;
- con un DB che riordina le righe tra una pagina e l'altra (nessun ORDER BY) la
  paginazione a offset perde e duplica righe: con l'ordine deterministico no,
  su match_odds come su fixture_predictions / matches / standings;
- un 57014 alla pagina N non fa perdere nulla (pagina dimezzata + ritentativo) e
  la pagina ridotta vale anche per i blocchi successivi;
- un 57014 persistente PROPAGA, come una risposta senza corpo (data=None);
- un errore logico non viene ritentato;
- il client scartato viene chiuso prima di essere buttato.
"""
from __future__ import annotations

import os
import sys
import threading
import types
from collections import Counter
from datetime import date
from typing import Any, Dict, List, Optional

import pytest

# -- import di db_adapter senza toccare il DB --------------------------------
_AI_ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _AI_ENGINE_DIR not in sys.path:
    sys.path.insert(0, _AI_ENGINE_DIR)

if "db_client" not in sys.modules:
    _stub = types.ModuleType("db_client")
    _stub._TLS = threading.local()

    def _no_db():  # pragma: no cover - deve restare non chiamata
        raise AssertionError("il test non deve aprire un client Supabase")

    _stub.get_supabase_client = _no_db
    sys.modules["db_client"] = _stub

from postgrest.exceptions import APIError  # noqa: E402  (vero errore di produzione)

from ai_engine import db_adapter  # noqa: E402

MARKETS = [
    "Match Winner",
    "Goals Over/Under",
    "Both Teams Score",
    "Over/Under",
    "Goals Over Under",
]
ALTRI_MERCATI = ["Asian Handicap", "HT/FT Double", "Corners Over Under"]
ODDS_COLUMNS = "fixture_id,market_name,label,odd_value,snapshot_time"


def timeout_error() -> APIError:
    """APIError identico a quello che arriva da PostgREST sul timeout di 8 s."""
    return APIError({
        "message": "canceling statement due to statement timeout",
        "code": "57014",
        "hint": None,
        "details": None,
    })


def errore_logico() -> APIError:
    return APIError({
        "message": "column match_odds.pippo does not exist",
        "code": "42703",
        "hint": None,
        "details": None,
    })


# -- finto PostgREST ---------------------------------------------------------

class FakeResponse:
    def __init__(self, data: Optional[List[Dict[str, Any]]]) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, server: "FakeServer", table: str) -> None:
        self._server = server
        self._table = table
        self._columns: List[str] = []
        self._filters: List[tuple] = []
        self._order: List[str] = []
        self._start = 0
        self._end = 0

    def select(self, columns: str) -> "FakeQuery":
        self._columns = [c.strip() for c in columns.split(",") if c.strip()]
        return self

    def eq(self, col: str, val: Any) -> "FakeQuery":
        self._filters.append(("eq", col, val))
        return self

    def gte(self, col: str, val: Any) -> "FakeQuery":
        self._filters.append(("gte", col, val))
        return self

    def lt(self, col: str, val: Any) -> "FakeQuery":
        self._filters.append(("lt", col, val))
        return self

    def in_(self, col: str, val: Any) -> "FakeQuery":
        self._filters.append(("in", col, list(val)))
        return self

    def order(self, column: str, desc: bool = False) -> "FakeQuery":
        assert desc is False, "il codice deve ordinare solo in salita"
        self._order.append(column)
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        self._start, self._end = start, end
        return self

    def execute(self) -> FakeResponse:
        return self._server.execute(self)


class FakePostgrest:
    """Sottooggetto .postgrest del client vero: qui serve solo aclose()."""

    def __init__(self, owner: "FakeServer") -> None:
        self._owner = owner

    def aclose(self) -> None:  # in postgrest 2.28 e' sincrona
        self._owner.chiusure += 1


class FakeServer:
    """Finto PostgREST: filtra, ordina, pagina e puo' fallire a comando."""

    def __init__(
        self,
        rows: List[Dict[str, Any]],
        instabile: bool = False,
        guasti: Optional[Dict[int, List[BaseException]]] = None,
        guasto_sempre: Optional[BaseException] = None,
        risposta_vuota_a: Optional[List[int]] = None,
    ) -> None:
        self.rows = rows
        self.instabile = instabile
        # guasti: {indice_richiesta (0-based): [errori da sollevare]}
        self.guasti = {k: list(v) for k, v in (guasti or {}).items()}
        self.guasto_sempre = guasto_sempre
        # indici di richiesta in cui PostgREST risponde senza corpo (data=None)
        self.risposta_vuota_a = set(risposta_vuota_a or [])
        self.richieste: List[Dict[str, Any]] = []
        self.chiusure = 0
        self.postgrest = FakePostgrest(self)

    # il client finto: sb.table(...)
    def table(self, table: str) -> FakeQuery:
        return FakeQuery(self, table)

    def execute(self, q: FakeQuery) -> FakeResponse:
        idx = len(self.richieste)
        self.richieste.append({
            "table": q._table,
            "filters": list(q._filters),
            "order": list(q._order),
            "start": q._start,
            "end": q._end,
            "page": q._end - q._start + 1,
        })
        if self.guasto_sempre is not None:
            raise self.guasto_sempre
        pendenti = self.guasti.get(idx)
        if pendenti:
            raise pendenti.pop(0)
        if idx in self.risposta_vuota_a:
            return FakeResponse(None)

        righe = [r for r in self.rows if self._passa(r, q._filters)]
        if q._order:
            righe.sort(key=lambda r: tuple(r[c] for c in q._order))
        elif self.instabile:
            # Nessun ORDER BY: il DB e' libero di cambiare ordine tra una pagina
            # e l'altra (piani diversi, scritture concorrenti). Qui si ruota di
            # una posizione a ogni richiesta.
            k = (idx + 1) % max(len(righe), 1)
            righe = righe[k:] + righe[:k]
        fetta = righe[q._start : q._end + 1]
        return FakeResponse([{col: r[col] for col in q._columns} for r in fetta])

    @staticmethod
    def _passa(row: Dict[str, Any], filters: List[tuple]) -> bool:
        for op, col, val in filters:
            v = row.get(col)
            if op == "eq" and v != val:
                return False
            if op == "in" and v not in val:
                return False
            if op == "gte" and not (v >= val):
                return False
            if op == "lt" and not (v < val):
                return False
        return True


# -- generatori di righe (chiavi e tipi identici al vero) --------------------

def genera_odds(n_fixture: int = 45, per_fixture: int = 17, primo_id: int = 9_000_000,
                primo_fixture: int = 1_391_941) -> List[Dict[str, Any]]:
    """Righe match_odds con colonne e tipi identici al vero."""
    rows: List[Dict[str, Any]] = []
    rid = primo_id
    for i in range(n_fixture):
        fid = primo_fixture + i
        for j in range(per_fixture):
            mercato = (MARKETS + ALTRI_MERCATI)[j % (len(MARKETS) + len(ALTRI_MERCATI))]
            rows.append({
                "id": rid,                      # bigint
                "fixture_id": fid,              # integer
                "market_name": mercato,         # text
                "label": ["Home", "Draw", "Away", "Over 2.5", "Under 2.5"][j % 5],
                "odd_value": round(1.5 + (j % 7) * 0.37, 2),  # numeric -> float
                "snapshot_time": f"2025-08-{(i % 28) + 1:02d}T18:{j % 60:02d}:00+00:00",
            })
            rid += 1
    return rows


FP_COLUMNS = (
    "fixture_id,league_id,league_name,season_year,fixture_date,home_team_id,home_team_name,"
    "away_team_id,away_team_name,status,goals_home_line,goals_away_line,under_over_line,"
    "percent_home,percent_draw,percent_away,win_or_draw,advice,winner_team_id,winner_name,"
    "raw_json_odds,raw_json"
)


def genera_fixture_predictions(n: int = 2500, giorno: str = "2026-09-20") -> List[Dict[str, Any]]:
    """Righe fixture_predictions come le restituisce PostgREST (un solo giorno)."""
    rows: List[Dict[str, Any]] = []
    for i in range(n):
        rows.append({
            "fixture_id": 1_500_000 + i,
            "league_id": 39 + (i % 120),
            "league_name": "Premier League",
            "season_year": 2026,
            "fixture_date": f"{giorno}T{(i % 24):02d}:{(i % 60):02d}:00+00:00",
            "home_team_id": 33 + (i % 500),
            "home_team_name": "Home FC",
            "away_team_id": 34 + (i % 500),
            "away_team_name": "Away FC",
            "status": "NS",
            "goals_home_line": None,
            "goals_away_line": None,
            "under_over_line": "-2.5",
            "percent_home": "45%",
            "percent_draw": "25%",
            "percent_away": "30%",
            "win_or_draw": False,
            "advice": "Double chance : Home or draw",
            "winner_team_id": None,
            "winner_name": None,
            "raw_json_odds": None,
            "raw_json": None,
        })
    return rows


def genera_matches(n: int = 1200, league_id: int = 141, season_year: int = 2025) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for i in range(n):
        rows.append({
            "id": 700_000 + i,
            "fixture_id": 1_391_000 + i,
            "league_id": league_id,
            "season_year": season_year,
            "fixture_date": f"2025-08-{(i % 28) + 1:02d}T18:00:00+00:00",
            "home_team_id": 500 + (i % 20),
            "home_team_name": "Home FC",
            "away_team_id": 520 + (i % 20),
            "away_team_name": "Away FC",
            "goals_home": i % 4,
            "goals_away": (i + 1) % 3,
        })
    return rows


def genera_standings(n: int = 2200, league_id: int = 141, season_year: int = 2025) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for i in range(n):
        rows.append({
            "id": 300_000 + i,
            "league_id": league_id,
            "season_year": season_year,
            "team_id": 500 + i,
            "team_name": "Team",
            "rank": (i % 20) + 1,
            "played": 38,
            "win": 20,
            "draw": 9,
            "lose": 9,
            "goals_for": 60,
            "goals_against": 40,
            "goals_diff": 20,
            "points": 69,
            "form": "WWDLW",
            "standing_group": None,
            "description": None,
        })
    return rows


def attesi(rows: List[Dict[str, Any]], fixture_ids: List[int]) -> Counter:
    return Counter(
        (r["fixture_id"], r["market_name"], r["label"], r["odd_value"], r["snapshot_time"])
        for r in rows
        if r["fixture_id"] in set(fixture_ids) and r["market_name"] in set(MARKETS)
    )


def come_multiset(righe: List[Dict[str, Any]]) -> Counter:
    return Counter(
        (r["fixture_id"], r["market_name"], r["label"], r["odd_value"], r["snapshot_time"])
        for r in righe
    )


def chiavi(righe: List[Dict[str, Any]], chiave: str) -> Counter:
    return Counter(r[chiave] for r in righe)


def lettura_vecchia(server: FakeServer, fixture_ids: List[int]) -> List[Dict[str, Any]]:
    """Il metodo di PRIMA: blocchi da 200 fixture, pagine da 200, nessun ORDER BY."""
    out: List[Dict[str, Any]] = []
    for i in range(0, len(fixture_ids), 200):
        chunk = fixture_ids[i : i + 200]
        offset = 0
        while True:
            q = (
                server.table("match_odds")
                .select(ODDS_COLUMNS)
                .in_("fixture_id", chunk)
                .in_("market_name", MARKETS)
                .range(offset, offset + 200 - 1)
            )
            data = q.execute().data
            out.extend(data)
            if len(data) < 200:
                break
            offset += 200
    return out


def lettura_vecchia_tabella(server: FakeServer, table: str, columns: str,
                            filters: List[tuple], page_size: int = 1000) -> List[Dict[str, Any]]:
    """Paginazione a offset SENZA ordine, come prima del fix."""
    out: List[Dict[str, Any]] = []
    offset = 0
    while True:
        q = server.table(table).select(columns)
        for op, col, val in filters:
            q = {"eq": q.eq, "gte": q.gte, "lt": q.lt, "in": q.in_}[op](col, val)
        data = q.range(offset, offset + page_size - 1).execute().data
        out.extend(data)
        if len(data) < page_size:
            break
        offset += page_size
    return out


@pytest.fixture(autouse=True)
def _ambiente_pulito(monkeypatch):
    """Niente attese vere e nessuna pagina "appresa" che passi da un test all'altro."""
    monkeypatch.setattr(db_adapter, "_time", types.SimpleNamespace(sleep=lambda _s: None))
    db_adapter._azzera_pagine_apprese()
    yield
    db_adapter._azzera_pagine_apprese()


def _collega(monkeypatch, server: FakeServer) -> None:
    monkeypatch.setattr(db_adapter, "get_supabase_client", lambda: server)


# -- match_odds --------------------------------------------------------------

def test_match_odds_blocchi_piccoli_e_ordine_deterministico(monkeypatch):
    rows = genera_odds()
    server = FakeServer(rows)
    _collega(monkeypatch, server)
    fixture_ids = sorted({r["fixture_id"] for r in rows})

    db_adapter.fetch_related_by_fixture_ids(
        "match_odds", fixture_ids, ODDS_COLUMNS,
        extra_filters=[("in", "market_name", MARKETS)],
    )

    assert server.richieste, "nessuna lettura eseguita"
    for req in server.richieste:
        fixture_filter = [f for f in req["filters"] if f[0] == "in" and f[1] == "fixture_id"]
        assert fixture_filter, "il filtro per fixture_id deve esserci"
        assert len(fixture_filter[0][2]) <= 20, "blocco di fixture troppo grande"
        assert req["order"] == ["fixture_id", "id"], "manca l'ordine deterministico"
        assert req["page"] <= 1000


def test_match_odds_senza_filtro_mercati_blocco_ancora_piu_piccolo(monkeypatch):
    """Senza filtro le righe per fixture sono ~11x: l'offset deve restare basso."""
    rows = genera_odds(n_fixture=30)
    server = FakeServer(rows)
    _collega(monkeypatch, server)
    fixture_ids = sorted({r["fixture_id"] for r in rows})

    db_adapter.fetch_related_by_fixture_ids("match_odds", fixture_ids, ODDS_COLUMNS)

    for req in server.richieste:
        blocco = [f for f in req["filters"] if f[0] == "in" and f[1] == "fixture_id"][0][2]
        assert len(blocco) <= 5, "senza filtro sui mercati il blocco deve essere piu' piccolo"


def test_equivalenza_vecchia_nuova_lettura_stesso_insieme(monkeypatch):
    rows = genera_odds()
    fixture_ids = sorted({r["fixture_id"] for r in rows})

    server_vecchio = FakeServer(rows)
    vecchie = lettura_vecchia(server_vecchio, fixture_ids)

    server_nuovo = FakeServer(rows)
    _collega(monkeypatch, server_nuovo)
    nuove = db_adapter.fetch_related_by_fixture_ids(
        "match_odds", fixture_ids, ODDS_COLUMNS,
        extra_filters=[("in", "market_name", MARKETS)],
    )

    atteso = attesi(rows, fixture_ids)
    assert come_multiset(vecchie) == atteso
    assert come_multiset(nuove) == atteso, "la nuova lettura non torna lo stesso insieme"
    assert set(nuove[0].keys()) == set(ODDS_COLUMNS.split(",")), "colonne cambiate"


@pytest.mark.parametrize("page_size", [1, 3, 7, 50, 1000])
def test_pagine_piccole_niente_buchi_ne_duplicati(monkeypatch, page_size):
    rows = genera_odds(n_fixture=25)
    fixture_ids = sorted({r["fixture_id"] for r in rows})
    server = FakeServer(rows)
    _collega(monkeypatch, server)

    nuove = db_adapter.fetch_related_by_fixture_ids(
        "match_odds", fixture_ids, ODDS_COLUMNS,
        extra_filters=[("in", "market_name", MARKETS)],
        page_size=page_size,
    )
    assert come_multiset(nuove) == attesi(rows, fixture_ids)


def test_ordine_instabile_il_vecchio_perde_righe_il_nuovo_no(monkeypatch):
    """Con un DB che riordina tra le pagine, l'offset SENZA ordine perde righe."""
    rows = genera_odds(n_fixture=25)
    fixture_ids = sorted({r["fixture_id"] for r in rows})

    perse = lettura_vecchia(FakeServer(rows, instabile=True), fixture_ids)
    assert come_multiset(perse) != attesi(rows, fixture_ids), (
        "il finto instabile deve far sbagliare la lettura senza ORDER BY"
    )

    server = FakeServer(rows, instabile=True)
    _collega(monkeypatch, server)
    nuove = db_adapter.fetch_related_by_fixture_ids(
        "match_odds", fixture_ids, ODDS_COLUMNS,
        extra_filters=[("in", "market_name", MARKETS)],
        page_size=7,
    )
    assert come_multiset(nuove) == attesi(rows, fixture_ids)


# -- le altre tabelle paginate ----------------------------------------------

def test_fixture_predictions_del_giorno_ordine_e_nessuna_perdita(monkeypatch):
    """2500 fixture in un giorno: senza ordine si perdono e si duplicano righe."""
    rows = genera_fixture_predictions(2500)
    filtri = [("gte", "fixture_date", "2026-09-20T00:00:00"),
              ("lt", "fixture_date", "2026-09-21T00:00:00")]

    vecchie = lettura_vecchia_tabella(
        FakeServer(rows, instabile=True), "fixture_predictions", FP_COLUMNS, filtri)
    assert chiavi(vecchie, "fixture_id") != chiavi(rows, "fixture_id"), (
        "senza ORDER BY la paginazione instabile deve sbagliare"
    )

    server = FakeServer(rows, instabile=True)
    _collega(monkeypatch, server)
    nuove = db_adapter.fetch_fixtures_for_date(date(2026, 9, 20))

    assert chiavi(nuove, "fixture_id") == chiavi(rows, "fixture_id")
    assert all(r["order"] == ["fixture_id"] for r in server.richieste)


def test_matches_per_lega_stagione_ordine_e_nessuna_perdita(monkeypatch):
    rows = genera_matches(1200)
    filtri = [("eq", "league_id", 141), ("eq", "season_year", 2025)]
    colonne = ("fixture_id,league_id,season_year,fixture_date,home_team_id,home_team_name,"
               "away_team_id,away_team_name,goals_home,goals_away")

    vecchie = lettura_vecchia_tabella(
        FakeServer(rows, instabile=True), "matches", colonne, filtri)
    assert chiavi(vecchie, "fixture_id") != chiavi(rows, "fixture_id")

    server = FakeServer(rows, instabile=True)
    _collega(monkeypatch, server)
    nuove = db_adapter.fetch_matches_for_league_seasons([(141, 2025)])

    assert chiavi(nuove, "fixture_id") == chiavi(rows, "fixture_id")
    assert all(r["order"] == ["fixture_id"] for r in server.richieste)


def test_standings_ordine_e_nessuna_perdita(monkeypatch):
    rows = genera_standings(2200)
    colonne = ("league_id,season_year,team_id,team_name,rank,played,win,draw,lose,"
               "goals_for,goals_against,goals_diff,points,form,standing_group,description")
    filtri = [("eq", "league_id", 141), ("eq", "season_year", 2025)]

    vecchie = lettura_vecchia_tabella(
        FakeServer(rows, instabile=True), "standings", colonne, filtri)
    assert chiavi(vecchie, "team_id") != chiavi(rows, "team_id")

    server = FakeServer(rows, instabile=True)
    _collega(monkeypatch, server)
    nuove = db_adapter.fetch_standings_by_league_seasons([(141, 2025)])

    assert chiavi(nuove, "team_id") == chiavi(rows, "team_id")
    assert all(r["order"] == ["id"] for r in server.richieste)


def _righe_eventi() -> List[Dict[str, Any]]:
    return [
        {"id": 1, "fixture_id": 1391941, "team_id": 529, "event_type": "Goal",
         "detail": "Normal Goal", "minute": 12},
        {"id": 2, "fixture_id": 1391942, "team_id": 530, "event_type": "Card",
         "detail": "Yellow Card", "minute": 40},
    ]


def test_match_events_ordine_deterministico_blocchi_invariati(monkeypatch):
    """match_events: blocchi/pagine come prima (1000), in piu' l'ordine stabile."""
    server = FakeServer(_righe_eventi())
    _collega(monkeypatch, server)

    out = db_adapter.fetch_related_by_fixture_ids(
        "match_events", [1391941, 1391942], "fixture_id,team_id,event_type,detail,minute",
    )
    assert len(out) == 2
    assert server.richieste[0]["order"] == ["fixture_id", "id"]
    assert server.richieste[0]["page"] == 1000
    assert len(server.richieste[0]["filters"][0][2]) == 2


def test_tabella_non_elencata_resta_senza_ordine(monkeypatch):
    """Una tabella fuori dall'elenco non riceve ORDER BY: comportamento di prima."""
    server = FakeServer(_righe_eventi())
    _collega(monkeypatch, server)

    db_adapter.fetch_related_by_fixture_ids(
        "match_lineups", [1391941, 1391942], "fixture_id,team_id",
    )
    assert server.richieste[0]["order"] == []


# -- errori, ritentativi, pagina appresa -------------------------------------

def test_57014_alla_pagina_n_recupera_tutto(monkeypatch):
    rows = genera_odds(n_fixture=25)
    fixture_ids = sorted({r["fixture_id"] for r in rows})
    # timeout alla terza richiesta (una pagina in mezzo, non la prima)
    server = FakeServer(rows, guasti={2: [timeout_error()]})
    _collega(monkeypatch, server)

    nuove = db_adapter.fetch_related_by_fixture_ids(
        "match_odds", fixture_ids, ODDS_COLUMNS,
        extra_filters=[("in", "market_name", MARKETS)],
        page_size=200,
    )

    assert come_multiset(nuove) == attesi(rows, fixture_ids), "righe perse dopo il 57014"
    pagine = [r["page"] for r in server.richieste]
    assert min(pagine) < 200, "sul 57014 la pagina deve essere dimezzata"
    assert len(server.richieste) > 3, "il ritentativo non e' avvenuto"


def test_pagina_ridotta_vale_anche_per_i_blocchi_successivi(monkeypatch):
    """Dopo un timeout la pagina resta piccola: niente timeout a ogni blocco."""
    rows = genera_odds(n_fixture=60)
    fixture_ids = sorted({r["fixture_id"] for r in rows})
    server = FakeServer(rows, guasti={0: [timeout_error()]})
    _collega(monkeypatch, server)

    nuove = db_adapter.fetch_related_by_fixture_ids(
        "match_odds", fixture_ids, ODDS_COLUMNS,
        extra_filters=[("in", "market_name", MARKETS)],
        page_size=400,
    )
    assert come_multiset(nuove) == attesi(rows, fixture_ids)
    # il primo blocco scende a 200; i blocchi dopo NON devono ripartire da 400
    assert max(r["page"] for r in server.richieste[1:]) == 200
    assert db_adapter._PAGINA_APPRESA["match_odds"] == 200


def test_57014_persistente_propaga(monkeypatch):
    rows = genera_odds(n_fixture=5)
    fixture_ids = sorted({r["fixture_id"] for r in rows})
    server = FakeServer(rows, guasto_sempre=timeout_error())
    _collega(monkeypatch, server)

    with pytest.raises(APIError) as exc:
        db_adapter.fetch_related_by_fixture_ids(
            "match_odds", fixture_ids, ODDS_COLUMNS,
            extra_filters=[("in", "market_name", MARKETS)],
        )
    assert exc.value.code == "57014"
    assert len(server.richieste) == db_adapter._MAX_RETRIES, "tentativi diversi dal previsto"


def test_risposta_senza_dati_ritenta_e_poi_propaga(monkeypatch):
    """data=None non e' 'fine dei dati': si ritenta e, se insiste, si solleva."""
    rows = genera_odds(n_fixture=5)
    fixture_ids = sorted({r["fixture_id"] for r in rows})
    server = FakeServer(rows, risposta_vuota_a=list(range(50)))
    _collega(monkeypatch, server)

    with pytest.raises(db_adapter.RispostaSenzaDati):
        db_adapter.fetch_related_by_fixture_ids(
            "match_odds", fixture_ids, ODDS_COLUMNS,
            extra_filters=[("in", "market_name", MARKETS)],
        )
    assert len(server.richieste) == db_adapter._MAX_RETRIES


def test_risposta_senza_dati_una_volta_sola_recupera_tutto(monkeypatch):
    rows = genera_odds(n_fixture=5)
    fixture_ids = sorted({r["fixture_id"] for r in rows})
    server = FakeServer(rows, risposta_vuota_a=[0])
    _collega(monkeypatch, server)

    nuove = db_adapter.fetch_related_by_fixture_ids(
        "match_odds", fixture_ids, ODDS_COLUMNS,
        extra_filters=[("in", "market_name", MARKETS)],
    )
    assert come_multiset(nuove) == attesi(rows, fixture_ids)


def test_lista_vuota_e_fine_dei_dati(monkeypatch):
    """Nessuna riga per quelle fixture: si esce subito, senza ritentativi."""
    server = FakeServer(genera_odds(n_fixture=2))
    _collega(monkeypatch, server)

    out = db_adapter.fetch_related_by_fixture_ids(
        "match_odds", [999_999_1, 999_999_2], ODDS_COLUMNS,
        extra_filters=[("in", "market_name", MARKETS)],
    )
    assert out == []
    assert len(server.richieste) == 1


def test_errore_logico_non_viene_ritentato(monkeypatch):
    rows = genera_odds(n_fixture=5)
    fixture_ids = sorted({r["fixture_id"] for r in rows})
    server = FakeServer(rows, guasto_sempre=errore_logico())
    _collega(monkeypatch, server)

    with pytest.raises(APIError) as exc:
        db_adapter.fetch_related_by_fixture_ids("match_odds", fixture_ids, ODDS_COLUMNS)
    assert exc.value.code == "42703"
    assert len(server.richieste) == 1, "un errore logico non si ritenta"


def test_errore_di_rete_transitorio_viene_ritentato(monkeypatch):
    class ReadTimeout(Exception):
        """Stesso nome della classe httpx usata da supabase-py."""

    rows = genera_odds(n_fixture=5)
    fixture_ids = sorted({r["fixture_id"] for r in rows})
    server = FakeServer(rows, guasti={0: [ReadTimeout("timed out")]})
    _collega(monkeypatch, server)

    nuove = db_adapter.fetch_related_by_fixture_ids(
        "match_odds", fixture_ids, ODDS_COLUMNS,
        extra_filters=[("in", "market_name", MARKETS)],
    )
    assert come_multiset(nuove) == attesi(rows, fixture_ids)


def test_il_client_scartato_viene_chiuso(monkeypatch):
    """Prima di buttare il client del thread se ne chiudono le connessioni."""
    class ReadTimeout(Exception):
        pass

    rows = genera_odds(n_fixture=3)
    fixture_ids = sorted({r["fixture_id"] for r in rows})
    server = FakeServer(rows, guasti={0: [ReadTimeout("timed out")]})
    _collega(monkeypatch, server)
    tls = threading.local()
    tls.client = server
    monkeypatch.setattr(db_adapter._db_client, "_TLS", tls, raising=False)

    db_adapter.fetch_related_by_fixture_ids(
        "match_odds", fixture_ids, ODDS_COLUMNS,
        extra_filters=[("in", "market_name", MARKETS)],
    )
    assert server.chiusure == 1, "il client vecchio non e' stato chiuso"
    assert getattr(tls, "client", None) is None, "il client vecchio non e' stato scartato"
