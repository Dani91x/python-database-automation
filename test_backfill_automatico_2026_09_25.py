"""Backfill automatico delle stagioni (25/09/2026): mapper che aggiorna, lacune
derivate dai dati, stato derivato, quota, recupero giornaliero, Daily, orchestratore.

Nessun DB, nessuna rete. I finti parlano come il vero:
- client supabase-py: table(..).select(cols, count=..).eq/gt/gte/in_/order/limit/range
  (..).execute() -> .data (lista di dict con le colonne VERE) e .count; .update/.upsert/
  .insert/.delete; rpc(nome, params).execute() -> .data. Max-rows 1000 per risposta
  (PostgREST su Supabase).
- le RPC della migrazione season_gaps_2026-09-25.sql sono riprodotte in Python con la
  STESSA regola degli stati (FintoDB._gaps): i test verificano il codice Python contro
  quel modello; l'SQL vero e' verificato a parte (parser di PostgreSQL, vedi referto).
- API-Football: risposte {"get","parameters","errors","results","paging","response"}
  con la struttura reale di /fixtures, /fixtures/events, /fixtures/lineups,
  /fixtures/players, /fixtures/statistics, /odds, /leagues, /status
  (response.requests.current/limit_day); errori come {"errors": {...}, "response": []}.
"""
from __future__ import annotations

import copy
import io
import os
import sys
from collections import defaultdict
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pytest

os.environ["SUPABASE_URL"] = "http://127.0.0.1:9"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "x"
os.environ["SUPABASE_KEY"] = "x"
os.environ["API_FOOTBALL_KEY"] = "x"

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api_client  # noqa: E402
import api_quota  # noqa: E402
import daily_yesterday_backfill as dyb  # noqa: E402
import fixtures_backfill  # noqa: E402
import league_orchestrator as lo  # noqa: E402
import leagues_mapper as lm  # noqa: E402
import per_fixture_backfill as pfb  # noqa: E402
import season_aggregates as sa  # noqa: E402
import season_gaps as sg  # noqa: E402
import seasons_catchup as sc  # noqa: E402

OGGI = date(2026, 9, 25)
ADESSO = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
TABELLE = ("match_events", "match_lineups", "match_player_stats", "match_team_stats", "match_odds")
FT = ("FT", "AET", "PEN")


# ===========================================================================
# Finto Supabase
# ===========================================================================
class _Resp:
    def __init__(self, data: Any, count: Optional[int] = None) -> None:
        self.data = data
        self.count = count


def _valore_percorso(riga: Dict[str, Any], percorso: str) -> Any:
    # "stats_json->meta->>version"
    parti = percorso.replace("->>", "->").split("->")
    v: Any = riga.get(parti[0])
    for p in parti[1:]:
        v = v.get(p) if isinstance(v, dict) else None
    if percorso.count("->>") and v is not None and not isinstance(v, str):
        v = str(v)
    return v


class _Q:
    def __init__(self, db: "FintoDB", tabella: str) -> None:
        self.db, self.t = db, tabella
        self.op, self.cols, self.count = "select", "*", None
        self.filtri: List[Tuple[str, str, Any]] = []
        self.ordini: List[Tuple[str, bool]] = []
        self.rng: Optional[Tuple[int, int]] = None
        self.lim: Optional[int] = None
        self.payload: Any = None
        self.on_conflict: Optional[str] = None

    def select(self, cols: str = "*", count: Optional[str] = None) -> "_Q":
        self.op, self.cols, self.count = "select", cols, count
        return self

    def eq(self, c: str, v: Any) -> "_Q":
        self.filtri.append(("eq", c, v))
        return self

    def gt(self, c: str, v: Any) -> "_Q":
        self.filtri.append(("gt", c, v))
        return self

    def gte(self, c: str, v: Any) -> "_Q":
        self.filtri.append(("gte", c, v))
        return self

    def in_(self, c: str, v: List[Any]) -> "_Q":
        self.filtri.append(("in", c, list(v)))
        return self

    def order(self, c: str, desc: bool = False) -> "_Q":
        self.ordini.append((c, desc))
        return self

    def range(self, a: int, b: int) -> "_Q":
        self.rng = (a, b)
        return self

    def limit(self, n: int) -> "_Q":
        self.lim = n
        return self

    def update(self, payload: Dict[str, Any]) -> "_Q":
        self.op, self.payload = "update", payload
        return self

    def upsert(self, righe: Any, on_conflict: Optional[str] = None) -> "_Q":
        self.op, self.payload, self.on_conflict = "upsert", righe, on_conflict
        return self

    def insert(self, righe: Any) -> "_Q":
        self.op, self.payload = "insert", righe
        return self

    def delete(self) -> "_Q":
        self.op = "delete"
        return self

    def _ok(self, r: Dict[str, Any]) -> bool:
        for op, c, v in self.filtri:
            x = r.get(c)
            if op == "eq" and x != v:
                return False
            if op == "gt" and not (x is not None and x > v):
                return False
            if op == "gte" and not (x is not None and str(x) >= str(v)):
                return False
            if op == "in" and x not in v:
                return False
        return True

    def execute(self) -> _Resp:
        db = self.db
        db.richieste.append((self.op, self.t))
        if self.t in db.errori_tabella and self.op in db.errori_tabella[self.t]:
            raise RuntimeError(db.errori_tabella[self.t][self.op])
        righe = db.t[self.t]
        if self.op == "select":
            sel = [r for r in righe if self._ok(r)]
            for c, desc in reversed(self.ordini):
                sel.sort(key=lambda r: (r.get(c) is None, r.get(c)), reverse=desc)
            n = len(sel)
            if self.rng:
                sel = sel[self.rng[0]:self.rng[1] + 1]
            if self.lim is not None:
                sel = sel[:self.lim]
            sel = sel[:db.max_rows]
            if self.cols != "*":
                out = []
                for r in sel:
                    d = {}
                    for col in self.cols.split(","):
                        col = col.strip()
                        if ":" in col:
                            alias, perc = col.split(":", 1)
                            d[alias] = _valore_percorso(r, perc)
                        else:
                            d[col] = copy.deepcopy(r.get(col))
                    out.append(d)
                sel = out
            else:
                sel = copy.deepcopy(sel)
            return _Resp(sel, n if self.count else None)
        db.scritture.append((self.op, self.t, copy.deepcopy(self.payload)))
        if self.op == "update":
            n = 0
            for r in righe:
                if self._ok(r):
                    r.update(copy.deepcopy(self.payload))
                    n += 1
            return _Resp([{}] * n)
        if self.op == "delete":
            via = [r for r in righe if self._ok(r)]
            db.t[self.t] = [r for r in righe if not self._ok(r)]
            return _Resp(via)
        lista = self.payload if isinstance(self.payload, list) else [self.payload]
        for nuova in lista:
            nuova = copy.deepcopy(nuova)
            if self.op == "upsert" and self.on_conflict:
                chiavi = self.on_conflict.split(",")
                trovata = next((r for r in righe if all(r.get(k) == nuova.get(k) for k in chiavi)), None)
                if trovata is not None:
                    trovata.update(nuova)
                    continue
            nuova.setdefault("id", db.nuovo_id())
            if self.op == "insert":                    # default del DB: created_at/updated_at = now()
                nuova.setdefault("created_at", db.adesso.isoformat())
                nuova.setdefault("updated_at", db.adesso.isoformat())
            righe.append(nuova)
        return _Resp(lista)


class _Rpc:
    def __init__(self, db: "FintoDB", nome: str, params: Dict[str, Any]) -> None:
        self.db, self.nome, self.params = db, nome, params

    def execute(self) -> _Resp:
        db = self.db
        db.rpc_chiamate.append((self.nome, copy.deepcopy(self.params)))
        if self.nome in db.rpc_assenti:
            raise RuntimeError("{'code': 'PGRST202', 'message': 'Could not find the function public.%s'}" % self.nome)
        if self.nome == "season_detail_gaps":
            return _Resp(db._gaps(self.params["p_league_id"], self.params["p_season_year"],
                                  self.params.get("p_fixture_ids")))
        if self.nome == "season_gaps_summary":
            out = []
            for lid, sy in zip(self.params["p_league_ids"], self.params["p_season_years"]):
                for r in db._gaps(lid, sy, None):
                    out.append({"league_id": lid, "season_year": sy, "tabella": r["tabella"],
                                "stato": r["stato"], "n": r["n"]})
            return _Resp(out)
        if self.nome == "record_fixture_detail_checks":
            n = 0
            for x in self.params["p_rows"]:
                if x.get("esito") not in ("vuoto", "errore", "parziale", "ok"):
                    continue
                k = (x["fixture_id"], x["tabella"])
                if x["esito"] == "ok":
                    n += 1 if db.checks.pop(k, None) is not None else 0
                    continue
                c = db.checks.get(k)
                if c is None:
                    c = {"fixture_id": x["fixture_id"], "tabella": x["tabella"], "league_id": x["league_id"],
                         "season_year": x["season_year"], "vuoti": 0, "errori": 0,
                         "primo_controllo_at": db.adesso}
                    db.checks[k] = c
                c["esito"] = x["esito"]
                c["vuoti"] += 1 if x["esito"] == "vuoto" else 0
                c["errori"] += 1 if x["esito"] in ("errore", "parziale") else 0
                c["ultimo_controllo_at"] = db.adesso
                n += 1
            return _Resp(n)
        if self.nome == "season_aggregates_summary":
            # modello Python di public.season_aggregates_summary (stessa regola dell'SQL)
            coppie = set(zip(self.params["p_league_ids"], self.params["p_season_years"]))
            out = []
            for tab in ("standings", "injuries", "top_scorers", "top_assists", "top_cards"):
                gruppi: Dict[Tuple[int, int], List[Dict[str, Any]]] = defaultdict(list)
                for r in db.t[tab]:
                    if (r["league_id"], r["season_year"]) in coppie:
                        gruppi[(r["league_id"], r["season_year"])].append(r)
                for (lid, sy), rr in gruppi.items():
                    out.append({"league_id": lid, "season_year": sy, "tabella": tab, "n": len(rr),
                                "ultimo": max(r.get("updated_at") or r.get("created_at") for r in rr)})
            gruppi_ft: Dict[Tuple[int, int], List[str]] = defaultdict(list)
            for m in db.t["matches"]:
                if (m["league_id"], m["season_year"]) in coppie and m["status_short"] in FT:
                    gruppi_ft[(m["league_id"], m["season_year"])].append(m["fixture_date"])
            for (lid, sy), date_ in gruppi_ft.items():
                out.append({"league_id": lid, "season_year": sy, "tabella": "_ft", "n": len(date_),
                            "ultimo": max(date_)})
            return _Resp(out)
        if self.nome == "refresh_api_coverage_by_season_v2_mv":
            return _Resp(None)
        raise AssertionError(f"rpc inattesa {self.nome}")


class FintoDB:
    def __init__(self) -> None:
        self.t: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.checks: Dict[Tuple[int, str], Dict[str, Any]] = {}
        self.richieste: List[Tuple[str, str]] = []
        self.scritture: List[Tuple[str, str, Any]] = []
        self.rpc_chiamate: List[Tuple[str, Dict[str, Any]]] = []
        self.rpc_assenti: set = set()
        self.errori_tabella: Dict[str, Dict[str, str]] = {}
        self.max_rows = 1000
        self.adesso = ADESSO
        self._id = 1000

    def nuovo_id(self) -> int:
        self._id += 1
        return self._id

    def table(self, nome: str) -> _Q:
        return _Q(self, nome)

    def rpc(self, nome: str, params: Dict[str, Any]) -> _Rpc:
        return _Rpc(self, nome, params)

    # modello Python di public.season_detail_gaps (stessa regola dell'SQL)
    def _gaps(self, lid: int, sy: int, fids: Optional[List[int]]) -> List[Dict[str, Any]]:
        tutte = [m for m in self.t["matches"] if m["league_id"] == lid and m["season_year"] == sy
                 and (fids is None or m["fixture_id"] in fids)]
        ft = [m for m in tutte if m["status_short"] in FT]
        out = [{"tabella": "_partite", "stato": "ft", "n": len(ft), "fixture_ids": None},
               {"tabella": "_partite", "stato": "tutte", "n": len(tutte), "fixture_ids": None}]
        gruppi: Dict[Tuple[str, str], List[int]] = defaultdict(list)
        for m in ft:
            fid = m["fixture_id"]
            data_m = datetime.fromisoformat(m["fixture_date"])
            for tab in TABELLE:
                c = self.checks.get((fid, tab))
                presente = any(r["fixture_id"] == fid and (tab != "match_odds"
                                                           or r.get("snapshot_type") == "api_football")
                               for r in self.t[tab])
                if presente and not (c is not None and c["esito"] == "parziale"):
                    continue
                if tab == "match_odds" and data_m < self.adesso - timedelta(days=7):
                    stato = "non_disponibile"
                elif c is None:
                    stato = "da_chiamare"
                elif c["esito"] in ("errore", "parziale"):
                    stato = "errore"
                elif c["vuoti"] >= 2 or c["ultimo_controllo_at"] >= data_m + timedelta(days=7):
                    stato = "vuoto_definitivo"
                elif c["ultimo_controllo_at"] > self.adesso - timedelta(days=2):
                    stato = "in_attesa"
                else:
                    stato = "da_richiamare"
                gruppi[(tab, stato)].append(fid)
        for (tab, stato), ids in sorted(gruppi.items()):
            out.append({"tabella": tab, "stato": stato, "n": len(ids), "fixture_ids": sorted(ids)})
        return out

    # helper per costruire il mondo
    def partita(self, fid: int, lid: int, sy: int, stato: str = "FT", giorni_fa: int = 5) -> None:
        self.t["matches"].append({"id": self.nuovo_id(), "fixture_id": fid, "league_id": lid, "season_year": sy,
                                  "status_short": stato,
                                  "fixture_date": (ADESSO - timedelta(days=giorni_fa)).isoformat()})

    def dettaglio(self, tab: str, fid: int, lid: int, sy: int, fonte: str = "api_football") -> None:
        riga = {"id": self.nuovo_id(), "fixture_id": fid, "league_id": lid, "season_year": sy}
        if tab == "match_odds":                        # colonna vera: due fonti nella stessa tabella
            riga.update({"snapshot_type": fonte, "bookmaker_name": "Pinnacle" if fonte != "api_football" else "Bet365"})
        self.t[tab].append(riga)


def coverage(lid: int, sy: int, *, current: bool = True, fine: str = "2027-05-30", inizio: str = "2026-08-20",
             ev: bool = True, fo: bool = True, sgio: bool = True, ss: bool = True, qu: bool = True,
             aggregati: bool = False) -> Dict[str, Any]:
    return {"id": lid * 10000 + sy, "league_id": lid, "league_name": f"Lega {lid}", "country_name": "Italy",
            "season_year": sy, "season_start": inizio, "season_end": fine, "current": current,
            "fixtures_events": ev, "fixtures_lineups": fo, "fixtures_statistics_fixtures": ss,
            "fixtures_statistics_players": sgio, "standings": aggregati, "players": False,
            "top_scorers": aggregati, "top_assists": aggregati, "top_cards": aggregati,
            "injuries": aggregati, "predictions": False, "odds": qu,
            "inserted_at": "2026-07-01T00:12:00+00:00", "updated_at": "2026-07-01T00:12:00+00:00"}


# ===========================================================================
# Finta API-Football (un "server" con il contatore del giorno, client separati)
# ===========================================================================
def _busta(endpoint: str, params: Any, response: Any, errors: Any = None) -> Dict[str, Any]:
    return {"get": endpoint.lstrip("/"), "parameters": params or {}, "errors": errors or [],
            "results": len(response) if isinstance(response, list) else 1,
            "paging": {"current": 1, "total": 1}, "response": response}


def risposta_dettaglio(endpoint: str, fid: int) -> List[Dict[str, Any]]:
    team = {"id": 489, "name": "AC Milan", "logo": "https://media.api-sports.io/football/teams/489.png"}
    if endpoint == "/fixtures/events":
        return [{"time": {"elapsed": 23, "extra": None}, "team": team,
                 "player": {"id": 1100, "name": "O. Giroud"}, "assist": {"id": None, "name": None},
                 "type": "Goal", "detail": "Normal Goal", "comments": None}]
    if endpoint == "/fixtures/lineups":
        return [{"team": team, "coach": {"id": 9, "name": "S. Pioli", "photo": ""}, "formation": "4-2-3-1",
                 "startXI": [{"player": {"id": 1100, "name": "O. Giroud", "number": 9, "pos": "F", "grid": "4:1"}}],
                 "substitutes": []}]
    if endpoint == "/fixtures/players":
        return [{"team": team, "players": [{"player": {"id": 1100, "name": "O. Giroud", "photo": ""},
                                            "statistics": [{"games": {"minutes": 90, "rating": "7.3"},
                                                            "shots": {"total": 3, "on": 2},
                                                            "goals": {"total": 1, "assists": None},
                                                            "passes": {"total": 20, "key": 1, "accuracy": "80"},
                                                            "cards": {"yellow": 0, "red": 0}}]}]}]
    if endpoint == "/fixtures/statistics":
        return [{"team": team, "statistics": [{"type": "Shots on Goal", "value": 5},
                                              {"type": "Ball Possession", "value": "55%"}]}]
    if endpoint == "/odds":
        return [{"league": {"id": 135, "season": 2026}, "fixture": {"id": fid},
                 "update": "2026-09-20T10:00:00+00:00",
                 "bookmakers": [{"id": 8, "name": "Bet365",
                                 "bets": [{"id": 1, "name": "Match Winner",
                                           "values": [{"value": "Home", "odd": "1.85"}]}]}]}]
    raise AssertionError(endpoint)


class FintoServer:
    def __init__(self, current: int = 1076, limit_day: int = 7500) -> None:
        self.current = current
        self.limit_day = limit_day
        self.chiamate: List[Tuple[str, Dict[str, Any]]] = []
        self.vuote: set = set()              # (endpoint, fixture) con response []
        self.in_errore: set = set()          # (endpoint, fixture) con errors
        self.fixtures_stagione: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        self.status_giu = False
        self.status_chiamate = 0
        # (endpoint aggregato, lega) -> response (struttura reale); default [] = vuoto
        self.aggregati: Dict[Tuple[str, Any], List[Dict[str, Any]]] = {}
        self.errore_aggregati: set = set()

    def rispondi(self, endpoint: str, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        self.current += 1
        self.chiamate.append((endpoint, dict(params or {})))
        fid = (params or {}).get("fixture")
        if (endpoint, fid) in self.in_errore:
            return _busta(endpoint, params, [], {"requests": "You have reached the request limit for the day"})
        if endpoint == "/fixtures":
            k = ((params or {}).get("league"), (params or {}).get("season"))
            return _busta(endpoint, params, self.fixtures_stagione.get(k, []))
        if endpoint in ("/standings", "/players/topscorers", "/players/topassists", "/players/topyellowcards",
                        "/players/topredcards", "/injuries"):
            if (endpoint, (params or {}).get("league")) in self.errore_aggregati:
                return _busta(endpoint, params, [], {"requests": "You have reached the request limit for the day"})
            return _busta(endpoint, params, self.aggregati.get((endpoint, (params or {}).get("league")), []))
        if (endpoint, fid) in self.vuote:
            return _busta(endpoint, params, [])
        return _busta(endpoint, params, risposta_dettaglio(endpoint, fid))

    def http_get_status(self, url: str, headers: Dict[str, str], timeout: int = 15) -> Any:
        self.status_chiamate += 1
        server = self

        class R:
            status_code = 200 if not server.status_giu else 503

            def json(self_inner) -> Dict[str, Any]:
                return {"get": "status", "parameters": [], "errors": [], "results": 1,
                        "paging": {"current": 1, "total": 1},
                        "response": {"account": {"firstname": "D", "lastname": "R", "email": "x"},
                                     "subscription": {"plan": "Pro", "end": "2027-01-01T00:00:00+00:00",
                                                      "active": True},
                                     "requests": {"current": server.current, "limit_day": server.limit_day}}}
        if self.status_giu:
            raise ConnectionError("status irraggiungibile")
        return R()


class FintoClient:
    """Stessa interfaccia di APIFootballClient: call(), richieste_http, ultimo_ratelimit."""

    def __init__(self, server: FintoServer) -> None:
        self.server = server
        self.richieste_http = 0
        self.ultimo_ratelimit: Optional[Dict[str, Any]] = None

    def call(self, endpoint: str, params: Optional[Dict[str, Any]] = None, max_retries: int = 3) -> Dict[str, Any]:
        self.richieste_http += 1
        return self.server.rispondi(endpoint, params)

    def get_leagues(self) -> Dict[str, Any]:
        return self.call("/leagues")


def fixture_api(fid: int, lid: int, sy: int, stato: str = "FT") -> Dict[str, Any]:
    return {"fixture": {"id": fid, "referee": None, "timezone": "UTC",
                        "date": (ADESSO - timedelta(days=5)).isoformat(), "timestamp": 1758000000,
                        "venue": {"id": 907, "name": "San Siro", "city": "Milano"},
                        "status": {"long": "Match Finished", "short": stato, "elapsed": 90}},
            "league": {"id": lid, "name": "Serie A", "country": "Italy", "season": sy, "round": "Regular Season - 4"},
            "teams": {"home": {"id": 489, "name": "AC Milan", "winner": True},
                      "away": {"id": 505, "name": "Inter", "winner": False}},
            "goals": {"home": 1, "away": 0},
            "score": {"halftime": {"home": 1, "away": 0}, "fulltime": {"home": 1, "away": 0},
                      "extratime": {"home": None, "away": None}, "penalty": {"home": None, "away": None}}}


@pytest.fixture
def mondo(monkeypatch):
    db = FintoDB()
    server = FintoServer()
    monkeypatch.setattr(pfb, "get_supabase", lambda: db)
    monkeypatch.setattr(pfb.time, "sleep", lambda s: None)
    monkeypatch.setattr(fixtures_backfill, "get_supabase_client", lambda: db)
    monkeypatch.setattr(fixtures_backfill, "APIFootballClient", lambda: FintoClient(server))
    monkeypatch.setattr(fixtures_backfill.time, "sleep", lambda s: None)
    monkeypatch.setattr(lo, "get_supabase", lambda: db)
    monkeypatch.setattr(sg, "_oggi", lambda: OGGI)
    monkeypatch.setattr(sa, "adesso", lambda: db.adesso)   # ora unica per lo stato degli aggregati
    return db, server


def quota_per(db: FintoDB, server: FintoServer, client: Any = None, riserva: Optional[int] = None,
              env: Optional[Dict[str, str]] = None) -> api_quota.GestoreQuota:
    return api_quota.GestoreQuota(sb=db, api_key="x", client=client, riserva=riserva,
                                  http_get=server.http_get_status, env=env or {}, stampa=lambda s: None)


def chiamate_dettaglio(server: FintoServer) -> List[Tuple[str, Any]]:
    return [(e, p.get("fixture")) for e, p in server.chiamate if e != "/fixtures" and "fixture" in p]


# ===========================================================================
# 1. LEAGUES MAPPER
# ===========================================================================
def lega_api(lid: int, anni: List[int], flag: bool = True, current_ultimo: bool = True) -> Dict[str, Any]:
    return {"league": {"id": lid, "name": f"Lega {lid}", "type": "League", "logo": ""},
            "country": {"name": "Italy", "code": "IT", "flag": ""},
            "seasons": [{"year": a, "start": f"{a}-08-20", "end": f"{a + 1}-05-30",
                         "current": current_ultimo and a == anni[-1],
                         "coverage": {"fixtures": {"events": flag, "lineups": flag,
                                                   "statistics_fixtures": flag, "statistics_players": flag},
                                      "standings": True, "players": True, "top_scorers": True,
                                      "top_assists": True, "top_cards": True, "injuries": flag,
                                      "predictions": True, "odds": flag}} for a in anni]}


def _mapper(monkeypatch, db: FintoDB, leghe: List[Dict[str, Any]]) -> FintoServer:
    server = FintoServer()
    risposta = _busta("/leagues", {}, leghe)
    client = FintoClient(server)
    client.call = lambda endpoint, params=None, max_retries=3: risposta  # type: ignore[assignment]
    monkeypatch.setattr(lm, "APIFootballClient", lambda: client)
    monkeypatch.setattr(lm, "get_supabase_client", lambda: db)
    monkeypatch.setattr(lm.time, "sleep", lambda s: None)
    return server


def test_mapper_aggiorna_i_flag_di_una_riga_esistente_senza_toccare_inserted_at(monkeypatch):
    db = FintoDB()
    riga = coverage(135, 2026, ev=False, fo=False, sgio=False, ss=False, qu=False)
    riga.update({"standings": True, "top_scorers": True, "top_assists": True, "top_cards": True,
                 "injuries": False, "players": True, "predictions": True})
    db.t["api_coverage_by_season"].append(riga)
    _mapper(monkeypatch, db, [lega_api(135, [2026], flag=True)])
    out = io.StringIO()
    with redirect_stdout(out):
        lm.run_full_leagues_backfill_mapping()
    r = db.t["api_coverage_by_season"][0]
    assert (r["fixtures_events"], r["fixtures_lineups"], r["fixtures_statistics_fixtures"],
            r["fixtures_statistics_players"], r["odds"], r["injuries"]) == (True,) * 6
    assert r["inserted_at"] == "2026-07-01T00:12:00+00:00"          # MAI toccato
    assert r["updated_at"] != "2026-07-01T00:12:00+00:00"
    upd = [s for s in db.scritture if s[0] == "update"]
    assert len(upd) == 1 and "inserted_at" not in upd[0][2]
    assert not [s for s in db.scritture if s[0] == "upsert"]          # nessun inserimento
    testo = out.getvalue()
    assert "AGGIORNATA lega 135 stagione 2026: " in testo and "fixtures_events False -> True" in testo
    assert "Aggiornate:                    1" in testo


def test_mapper_non_riscrive_le_stagioni_chiuse_da_oltre_30_giorni(monkeypatch):
    db = FintoDB()
    vecchia = coverage(135, 2020, current=False, fine="2021-05-23", ev=False)
    db.t["api_coverage_by_season"].append(vecchia)
    _mapper(monkeypatch, db, [lega_api(135, [2020], flag=True, current_ultimo=False)])
    lm.run_full_leagues_backfill_mapping()
    assert db.t["api_coverage_by_season"][0]["fixtures_events"] is False
    assert not db.scritture


def test_mapper_chiude_current_quando_la_stagione_finisce(monkeypatch):
    db = FintoDB()
    db.t["api_coverage_by_season"].append(coverage(135, 2025, current=True, fine="2026-05-24"))
    _mapper(monkeypatch, db, [lega_api(135, [2025], flag=True, current_ultimo=False)])
    lm.run_full_leagues_backfill_mapping()
    assert db.t["api_coverage_by_season"][0]["current"] is False


def test_mapper_pagina_oltre_10000_coppie(monkeypatch):
    db = FintoDB()
    for lid in range(1, 10501):                        # 10.500 coppie esistenti, identiche all'API
        db.t["api_coverage_by_season"].append(coverage(lid, 2026, current=False, fine="2020-05-30"))
    api = [lega_api(lid, [2026], current_ultimo=False) for lid in range(10490, 10502)]  # 10501 e' nuova
    for l in api:
        l["seasons"][0]["end"] = "2020-05-30"
    _mapper(monkeypatch, db, api)
    lm.run_full_leagues_backfill_mapping()
    inserite = [r for op, t, p in db.scritture if op == "upsert" for r in p]
    assert [(r["league_id"], r["season_year"]) for r in inserite] == [(10501, 2026)]
    letture = [r for r in db.richieste if r == ("select", "api_coverage_by_season")]
    assert len(letture) == 11                          # 10 pagine piene + 1 parziale


# ===========================================================================
# 2. LACUNE DERIVATE DAI DATI + PER-FIXTURE RIPARTIBILE
# ===========================================================================
def test_lacune_chiama_solo_cio_che_manca_e_solo_endpoint_con_flag_true(mondo):
    db, server = mondo
    # 1: completa; 2: senza nulla; 3: con eventi ma senza il resto; 4: non finita
    for fid in (1, 2, 3):
        db.partita(fid, 135, 2026)
    db.partita(4, 135, 2026, stato="NS")
    for tab in TABELLE:
        db.dettaglio(tab, 1, 135, 2026)
    db.dettaglio("match_events", 3, 135, 2026)
    cov = coverage(135, 2026, qu=False)                 # quote NON coperte
    flags = sg.flag_per_fixture(cov)
    lac = sg.lacune_stagione(db, 135, 2026)
    assert lac.ft_totali == 3 and lac.partite_totali == 4
    assert lac.da_chiamare_per_fixture(flags) == {2: ["events", "lineups", "player_stats", "team_stats"],
                                                  3: ["lineups", "player_stats", "team_stats"]}
    client = FintoClient(server)
    st = pfb.backfill_per_fixture_for_league_season(135, 2026, lacune=lac, coverage=flags, client=client)
    fatte = chiamate_dettaglio(server)
    assert ("/odds", 2) not in fatte and ("/odds", 3) not in fatte      # flag False: mai chiamato
    assert ("/fixtures/events", 3) not in fatte                          # eventi presenti: non richiesti
    assert not [f for f in fatte if f[1] in (1, 4)]                      # completa / non FT
    assert len(fatte) == 7 and st["chiamate"] == 7
    assert sg.lacune_stagione(db, 135, 2026).chiamate_per_fixture(flags) == 0


def test_risposta_vuota_registrata_non_richiamata_poi_ritentata_poi_definitiva(mondo):
    db, server = mondo
    db.partita(7, 135, 2026, giorni_fa=1)
    server.vuote.add(("/odds", 7))
    cov = sg.flag_per_fixture(coverage(135, 2026, ev=False, fo=False, sgio=False, ss=False))
    client = FintoClient(server)
    pfb.backfill_per_fixture_for_league_season(135, 2026, coverage=cov, client=client)
    assert db.checks[(7, "match_odds")]["vuoti"] == 1
    # stessa notte / giorno dopo: in attesa, NON richiamata
    pfb.backfill_per_fixture_for_league_season(135, 2026, coverage=cov, client=client)
    assert client.richieste_http == 1
    lac = sg.lacune_stagione(db, 135, 2026)
    assert lac.in_attesa(cov) == 1 and lac.aperti(cov) == 1              # buco APERTO, non perso
    # dopo 2 giorni: richiamata una volta, poi vuoto definitivo (non e' piu' un buco)
    db.adesso = ADESSO + timedelta(days=2, hours=1)
    pfb.backfill_per_fixture_for_league_season(135, 2026, coverage=cov, client=client)
    assert client.richieste_http == 2 and db.checks[(7, "match_odds")]["vuoti"] == 2
    lac = sg.lacune_stagione(db, 135, 2026)
    assert lac.aperti(cov) == 0 and lac.n("match_odds", ("vuoto_definitivo",)) == 1
    pfb.backfill_per_fixture_for_league_season(135, 2026, coverage=cov, client=client)
    assert client.richieste_http == 2


def test_errore_api_non_e_un_vuoto_e_non_cancella_dati_esistenti(mondo):
    db, server = mondo
    db.partita(8, 135, 2026)
    db.dettaglio("match_events", 8, 135, 2026)
    server.in_errore.add(("/fixtures/events", 8))
    client = FintoClient(server)
    st = pfb.process_single_fixture(client, 8, 135, 2026, sg.flag_per_fixture(coverage(135, 2026)),
                                    endpoints=["events"])
    assert st["esiti"]["events"] == "errore"
    assert db.checks[(8, "match_events")]["esito"] == "errore"
    assert len([r for r in db.t["match_events"] if r["fixture_id"] == 8]) == 1     # non cancellati


def test_match_odds_cancellate_prima_del_reinserimento_niente_doppioni(mondo):
    db, server = mondo
    db.partita(9, 135, 2026)
    client = FintoClient(server)
    cov = sg.flag_per_fixture(coverage(135, 2026))
    pfb.process_single_fixture(client, 9, 135, 2026, cov, endpoints=["odds"])
    pfb.process_single_fixture(client, 9, 135, 2026, cov, endpoints=["odds"])
    assert len([r for r in db.t["match_odds"] if r["fixture_id"] == 9]) == 1


def test_senza_migrazione_il_recupero_si_ferma_con_messaggio_chiaro(mondo):
    db, _ = mondo
    db.rpc_assenti.add("season_detail_gaps")
    with pytest.raises(sg.MigrazioneMancante) as ex:
        sg.verifica_migrazione(db)
    assert "migrations/season_gaps_2026-09-25.sql" in str(ex.value)


# ===========================================================================
# 3. STATO DERIVATO
# ===========================================================================
def test_stato_completed_solo_a_stagione_finita_e_senza_buchi():
    finita = coverage(135, 2025, current=False, fine="2026-05-24")
    in_corso = coverage(135, 2026)
    piena = sg.Lacune(135, 2025, ft_totali=380, conteggi={})
    buca = sg.Lacune(135, 2025, ft_totali=380, conteggi={"match_events": {"da_chiamare": 3}})
    attesa = sg.Lacune(135, 2025, ft_totali=380, conteggi={"match_odds": {"in_attesa": 1}})
    assert sg.calcola_stato(finita, piena, OGGI) == "completed"
    assert sg.calcola_stato(finita, buca, OGGI) == "in_progress"
    assert sg.calcola_stato(finita, attesa, OGGI) == "in_progress"
    assert sg.calcola_stato(in_corso, piena, OGGI) == "in_progress"      # in corso: mai completed
    vuota = sg.Lacune(135, 2025, ft_totali=0, conteggi={})
    assert sg.calcola_stato(finita, vuota, OGGI) == "in_progress"        # 0 partite: non e' "completa"


def test_orchestratore_riapre_completed_vecchio_riempie_e_rilancio_fa_zero_chiamate(mondo, monkeypatch):
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage(135, 2026))
    db.t["season_backfill_state"].append({"id": 1, "league_id": 135, "season_year": 2026, "status": "completed",
                                          "stats_json": {"meta": {"version": "v1"}}})
    for fid in (11, 12):
        db.partita(fid, 135, 2026)
    server.fixtures_stagione[(135, 2026)] = [fixture_api(11, 135, 2026), fixture_api(12, 135, 2026),
                                              fixture_api(13, 135, 2026, "NS")]
    client = FintoClient(server)
    q = quota_per(db, server, client)
    out = io.StringIO()
    with redirect_stdout(out):
        r1 = lo.backfill_full_league(135, sb=db, quota=q, client=client, oggi=OGGI)
    stato = db.t["season_backfill_state"][0]
    assert stato["status"] == "in_progress"                              # riaperta: stagione in corso
    assert stato["stats_json"]["meta"]["version"] == "v2" and stato["stats_json"]["buchi_aperti"] == 0
    assert stato["stats_json"]["fixtures"]["matches_count"] == 3        # letto da training_planner
    assert len(chiamate_dettaglio(server)) == 10 and r1["chiamate"] == 11
    assert "completed -> in_progress RIAP" in out.getvalue()
    n = len(server.chiamate)
    r2 = lo.backfill_full_league(135, sb=db, quota=q, client=client, oggi=OGGI, stampa=lambda s: None)
    assert len(server.chiamate) == n and r2["chiamate"] == 0             # ZERO chiamate al rilancio


def test_orchestratore_stagione_finita_e_piena_diventa_completed(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage(135, 2024, current=False, fine="2025-05-25"))
    db.partita(21, 135, 2024, giorni_fa=400)
    for tab in TABELLE:
        db.dettaglio(tab, 21, 135, 2024)
    q = quota_per(db, server, FintoClient(server))
    lo.backfill_full_league(135, sb=db, quota=q, client=FintoClient(server), oggi=OGGI, stampa=lambda s: None)
    assert db.t["season_backfill_state"][0]["status"] == "completed"
    assert server.chiamate == []


def test_dry_run_non_chiama_l_api_e_non_scrive(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage(135, 2026, ev=False, fo=False, sgio=False, ss=False, qu=False))
    db.t["api_coverage_by_season"].append(coverage(135, 2025, current=False, fine="2026-05-24"))
    db.t["season_backfill_state"].append({"id": 1, "league_id": 135, "season_year": 2026, "status": "completed",
                                          "stats_json": {"meta": {"version": "v1"}}})
    for fid in range(30, 35):
        db.partita(fid, 135, 2026)
        db.partita(fid + 100, 135, 2025, giorni_fa=200)
    q = quota_per(db, server, None)
    out = io.StringIO()
    with redirect_stdout(out):
        lo.backfill_full_league(135, dry_run=True, sb=db, quota=q, oggi=OGGI)
    assert server.chiamate == []                                          # zero chiamate API
    assert server.status_chiamate == 1                                    # solo /status (gratuita)
    assert not [s for s in db.scritture if s[1] != "api_call_log"]        # zero scritture
    testo = out.getvalue()
    assert "DRY-RUN" in testo and "contatore API 1076/7500" in testo and "margine 3424" in testo
    assert "   (5)   (5)   (5)   (5)   (5)" in testo                                               # 2026: 5 partite senza eventi ma flag False
    assert "procederei" in testo and "niente da fare (0 chiamate)" in testo


# ===========================================================================
# 4. QUOTA
# ===========================================================================
def test_quota_riserva_da_env_default_3000():
    assert api_quota.leggi_riserva({}) == 3000
    assert api_quota.leggi_riserva({"API_FOOTBALL_RISERVA_GIORNALIERA": "1000"}) == 1000
    server = FintoServer(current=1076)
    q = api_quota.GestoreQuota(sb=None, api_key="x", http_get=server.http_get_status,
                               env={"API_FOOTBALL_RISERVA_GIORNALIERA": "1000"}, stampa=lambda s: None)
    assert q.aggiorna().margine == 7500 - 1076 - 1000
    q2 = api_quota.GestoreQuota(sb=None, api_key="x", http_get=server.http_get_status, env={}, stampa=lambda s: None)
    assert q2.aggiorna().margine == 7500 - 1076 - 3000


def test_quota_status_giu_fallback_api_call_log_con_avviso():
    db = FintoDB()
    ieri = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    for i in range(1, 51):
        db.t["api_call_log"].append({"id": i, "endpoint": "/fixtures", "created_at": ieri})
    for i in range(51, 51 + 1200):
        db.t["api_call_log"].append({"id": i, "endpoint": "/odds",
                                     "created_at": datetime.now(timezone.utc).isoformat()})
    server = FintoServer()
    server.status_giu = True
    avvisi: List[str] = []
    q = api_quota.GestoreQuota(sb=db, api_key="x", http_get=server.http_get_status, env={}, stampa=avvisi.append)
    st = q.aggiorna()
    assert st.fonte == "api_call_log" and st.current == 1200 and st.limit_day == 7500
    assert any("/status non leggibile" in a for a in avvisi) and any("AVVISO" in a for a in avvisi)


def test_quota_nessuna_fonte_non_si_parte():
    db = FintoDB()
    db.errori_tabella["api_call_log"] = {"select": "{'code': '57014'}"}
    server = FintoServer()
    server.status_giu = True
    q = api_quota.GestoreQuota(sb=db, api_key="x", http_get=server.http_get_status, env={}, stampa=lambda s: None)
    with pytest.raises(api_quota.QuotaNonLeggibile):
        q.aggiorna()


def test_quota_catchup_non_parte_se_quota_illeggibile(mondo, monkeypatch):
    db, server = mondo
    server.status_giu = True
    db.errori_tabella["api_call_log"] = {"select": "timeout"}
    monkeypatch.setattr("db_client.get_supabase_client", lambda: db)
    monkeypatch.setattr(api_client, "APIFootballClient", lambda: FintoClient(server))
    monkeypatch.setattr(api_quota, "leggi_status_api",
                        lambda key, http_get=None, timeout=15: server.http_get_status("u", {}))
    monkeypatch.setattr(sc, "ControlloConcorrenza", lambda: None)
    assert sc.main([]) == 2
    assert server.chiamate == []


def test_status_con_errors_non_e_un_contatore_valido():
    class R:
        status_code = 200

        def json(self):
            # errors non vuoto: il contatore NON va creduto anche se presente
            return {"errors": {"token": "Error/Missing application key."},
                    "response": {"requests": {"current": 0, "limit_day": 7500}}}
    with pytest.raises(RuntimeError):
        api_quota.leggi_status_api("x", lambda *a, **k: R())


def test_api_client_legge_gli_header_di_quota_senza_cambiare_call(monkeypatch):
    class Resp:
        status_code = 200
        ok = True
        text = '{"response": []}'
        headers = {"x-ratelimit-requests-limit": "7500", "x-ratelimit-requests-remaining": "6400"}

        def json(self):
            return {"errors": [], "response": []}
    monkeypatch.setattr(api_client, "log_api_call", lambda *a, **k: None)
    c = api_client.APIFootballClient()
    monkeypatch.setattr(c.session, "get", lambda *a, **k: Resp())
    assert c.call("/odds", params={"fixture": 1}) == {"errors": [], "response": []}
    assert c.richieste_http == 1
    assert c.ultimo_ratelimit["limit_day"] == 7500 and c.ultimo_ratelimit["remaining"] == 6400


def test_quota_si_ferma_a_fine_partita_mai_a_meta(mondo):
    db, server = mondo
    for fid in range(40, 50):
        db.partita(fid, 135, 2026)
    server.current = 7500 - 3000 - 12                    # margine 12 = 2 partite da 5 endpoint (+2 avanzo)
    client = FintoClient(server)
    q = quota_per(db, server, client)
    q.aggiorna()
    st = pfb.backfill_per_fixture_for_league_season(135, 2026, coverage=sg.flag_per_fixture(coverage(135, 2026)),
                                                     client=client, quota=q)
    assert st["fermato_per"] == "quota" and st["fixtures_fatte"] == 2
    per_fixture = defaultdict(int)
    for e, fid in chiamate_dettaglio(server):
        per_fixture[fid] += 1
    assert dict(per_fixture) == {40: 5, 41: 5}           # partite INTERE, nessuna a meta'


# ===========================================================================
# 5. RECUPERO GIORNALIERO (catchup) + REFERTO BUCHI
# ===========================================================================
def _mondo_catchup(db: FintoDB) -> None:
    # P1: 135 (atlante) con 2 partite vuote; P2: 999 con 3 e 555 con 1; P3: 135/2024 con 1
    db.t["api_coverage_by_season"] += [coverage(135, 2026), coverage(999, 2026), coverage(555, 2026),
                                       coverage(135, 2024, current=False, fine="2025-05-25")]
    for fid in (1, 2):
        db.partita(fid, 135, 2026)
    for fid in (3, 4, 5):
        db.partita(fid, 999, 2026)
    db.partita(6, 555, 2026)
    db.partita(7, 135, 2024, giorni_fa=400)


def _catchup(db, server, env=None, concorrenza=None, stampa=None):
    client = FintoClient(server)
    q = quota_per(db, server, client, env=env)
    righe: List[str] = []
    env = {"CATCHUP_LEGHE_PRIORITARIE": "135", **(env or {})}
    ris = sc.esegui_catchup(db, client, q, concorrenza, env=env, oggi=OGGI,
                            stampa=stampa or righe.append)
    return ris, righe, q


def test_catchup_ordine_di_priorita_e_db_senza_buchi(mondo):
    db, server = mondo
    _mondo_catchup(db)
    ris, righe, q = _catchup(db, server)
    ordine = [(p.get("fixture")) for e, p in server.chiamate if e == "/fixtures/events"]
    assert ordine == [1, 2, 3, 4, 5, 6, 7]               # P1 135, P2 999 (3 buchi) poi 555 (1), P3 135/2024
    assert ris.codice == 0 and ris.fatte == [(135, 2026), (999, 2026), (555, 2026), (135, 2024)]
    assert righe[-1] == "DB SENZA BUCHI"
    assert server.status_chiamate == 1 + 4                # ricalcolo DOPO ogni lega-stagione
    # stagioni vive: nessuna chiamata fissa (/fixtures e aggregati li fa il Daily); passata: /fixtures si
    assert [p for e, p in server.chiamate if e == "/fixtures"] == [{"league": 135, "season": 2024}]
    dopo = [r for r in righe if r.startswith("[CATCHUP] lega ")]
    assert len(dopo) == 4 and "contatore API ora" in dopo[0] and "prossima costa ~15" in dopo[0]
    stati = {(r["league_id"], r["season_year"]): r["status"] for r in db.t["season_backfill_state"]}
    assert stati == {(135, 2026): "in_progress", (999, 2026): "in_progress", (555, 2026): "in_progress",
                     (135, 2024): "completed"}


def test_catchup_fermo_per_quota_esce_0_con_riepilogo(mondo):
    db, server = mondo
    _mondo_catchup(db)
    server.current = 7500 - 3000 - 24                    # copre 135/2026 (10, viva: 0 fisse) ma non poi 999 (15)
    ris, righe, q = _catchup(db, server)
    assert ris.codice == 0 and ris.fermato_per == "quota"
    assert ris.fatte == [(135, 2026)] and ris.rimaste == [(999, 2026), (555, 2026), (135, 2024)]
    testo = "\n".join(righe)
    assert "Fermato per: quota" in testo and "rimaste in coda: 3" in testo
    assert righe[-1].startswith("BUCHI APERTI: 3 lega-stagioni, ~24 chiamate")


def test_catchup_errore_di_una_lega_stagione_esce_diverso_da_0(mondo, monkeypatch):
    db, server = mondo
    _mondo_catchup(db)

    vero = sg.lacune_stagione

    def esplode(sb, lid, sy, fixture_ids=None):          # DB che cade sulla lega 999
        if lid == 999:
            raise RuntimeError("{'code': '57014', 'message': 'canceling statement due to statement timeout'}")
        return vero(sb, lid, sy, fixture_ids)
    monkeypatch.setattr(sg, "lacune_stagione", esplode)
    ris, righe, _ = _catchup(db, server)
    assert ris.codice == 1
    assert any(r.startswith("ERRORE: lega 999 stagione 2026: RuntimeError") for r in righe)
    assert (555, 2026) in ris.fatte and (135, 2024) in ris.fatte   # le altre vanno avanti
    assert (999, 2026) in ris.rimaste


def test_catchup_buco_vecchio_con_budget_disponibile_esce_1_con_la_causa(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage(999, 2026))
    db.partita(3, 999, 2026)
    db.t["season_backfill_state"].append({"id": 5, "league_id": 999, "season_year": 2026, "status": "in_progress",
                                          "stats_json": {"meta": {"version": "v2"}, "buco_aperto_dal": "2026-09-20"}})
    server.in_errore.update({(e, 3) for e in ("/fixtures/events", "/fixtures/lineups", "/fixtures/players",
                                              "/fixtures/statistics", "/odds")})
    ris, righe, _ = _catchup(db, server)
    assert ris.codice == 1
    buco = [r for r in righe if r.startswith("BUCO VECCHIO: lega 999 stagione 2026 aperto da 5 gg")]
    assert buco and "errore API ripetuto su 5 partite-tabella" in buco[0]


def test_catchup_buco_vecchio_per_quota_esce_0_con_stima_giorni(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage(999, 2026))
    for fid in (3, 4):
        db.partita(fid, 999, 2026)
    db.t["season_backfill_state"].append({"id": 5, "league_id": 999, "season_year": 2026, "status": "in_progress",
                                          "stats_json": {"meta": {"version": "v2"}, "buco_aperto_dal": "2026-09-10"}})
    server.current = 7500 - 3000 - 3                     # margine 3: non copre nulla
    ris, righe, _ = _catchup(db, server)
    assert ris.codice == 0
    testo = "\n".join(righe)
    assert "RINVIATO (quota/tempo/action concorrente): lega 999 stagione 2026 aperto da 15 gg" in testo
    assert "Stima per chiudere i buchi aperti con la capacita' giornaliera (4500 chiamate): ~1 giorni." in testo
    assert righe[-1] == "BUCHI APERTI: 1 lega-stagioni, ~10 chiamate, il piu' vecchio da 15 giorni"


def test_catchup_si_ferma_se_un_action_concorrente_e_in_corso(mondo):
    db, server = mondo
    _mondo_catchup(db)

    class Conc:
        def in_corso(self, forza=False):
            return "action concorrente in_progress: today_predictions_backfill.yml"
    ris, righe, _ = _catchup(db, server, concorrenza=Conc())
    assert ris.codice == 0 and ris.fatte == [] and "today_predictions" in ris.fermato_per
    assert [c for c in server.chiamate if c[0] != "/status"] == []


def test_controllo_concorrenza_legge_le_run_di_github():
    viste = []

    class R:
        status_code = 200

        def __init__(self, n):
            self.n = n

        def json(self):
            return {"total_count": self.n, "workflow_runs": []}

    def get(url, params=None, headers=None, timeout=15):
        viste.append((url, params["status"]))
        return R(1 if "today_predictions" in url and params["status"] == "in_progress" else 0)
    c = sc.ControlloConcorrenza(env={"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "Dani91x/repo"}, http_get=get)
    assert c.in_corso(forza=True) == "action concorrente in_progress: today_predictions_backfill.yml"
    assert viste[0][0] == "https://api.github.com/repos/Dani91x/repo/actions/workflows/daily_yesterday_backfill.yml/runs"
    senza = sc.ControlloConcorrenza(env={}, http_get=get)
    assert senza.in_corso(forza=True) is None


def test_leghe_prioritarie_dall_atlante_v3():
    leghe = sc.leghe_prioritarie(env={})
    assert len(leghe) == 21 and 135 in leghe and 39 in leghe
    assert sc.leghe_prioritarie(env={"CATCHUP_LEGHE_PRIORITARIE": "1, 2"}) == {1, 2}


# ===========================================================================
# 6. DAILY: fixture di ieri con le stesse funzioni "cosa manca"
# ===========================================================================
def test_daily_fixture_vuota_non_si_perde_entra_nella_coda_del_catchup(mondo, monkeypatch):
    db, server = mondo
    monkeypatch.setattr(dyb, "get_supabase", lambda: db)
    db.t["api_coverage_by_season"].append(coverage(135, 2026))
    db.partita(70, 135, 2026, giorni_fa=1)
    db.partita(71, 135, 2026, giorni_fa=1)
    db.dettaglio("match_events", 71, 135, 2026)            # 71 ha gia' gli eventi
    server.vuote.update({("/fixtures/events", 70), ("/fixtures/lineups", 70)})
    monkeypatch.setattr(dyb, "get_coverage_for_season",
                        lambda l, s: sg.flag_per_fixture(coverage(135, 2026)))
    client = FintoClient(server)
    dyb.run_per_fixture_for_date(client, [{"fixture_id": 70, "league_id": 135, "season_year": 2026},
                                          {"fixture_id": 71, "league_id": 135, "season_year": 2026}])
    assert ("/fixtures/events", 71) not in chiamate_dettaglio(server)  # solo cio' che manca
    assert db.checks[(70, "match_events")]["esito"] == "vuoto"
    # due giorni dopo il catchup la rimette in coda e la ritenta
    db.adesso = ADESSO + timedelta(days=2, hours=1)
    n_prima = len(server.chiamate)
    ris, righe, _ = _catchup(db, server)
    ritentate = [(e, p.get("fixture")) for e, p in server.chiamate[n_prima:] if p.get("fixture") == 70]
    assert ("/fixtures/events", 70) in ritentate and ("/fixtures/lineups", 70) in ritentate
    assert db.checks[(70, "match_events")]["vuoti"] == 2                 # ora vuoto definitivo dichiarato
    assert any("Vuoti definitivi dell'API (non buchi, l'API non ha il dato): 2" in r for r in righe)


def test_daily_senza_migrazione_fa_il_lavoro_di_prima_con_avviso(mondo, monkeypatch, capsys):
    db, server = mondo
    db.rpc_assenti.update({"season_detail_gaps", "record_fixture_detail_checks"})
    monkeypatch.setattr(dyb, "get_supabase", lambda: db)
    monkeypatch.setattr(sg, "_avviso_registro_dato", False)
    monkeypatch.setattr(dyb, "get_coverage_for_season",
                        lambda l, s: sg.flag_per_fixture(coverage(135, 2026)))
    monkeypatch.setattr(dyb.time, "sleep", lambda s: None)
    db.partita(80, 135, 2026, giorni_fa=1)
    server.vuote.add(("/odds", 80))
    dyb.run_per_fixture_for_date(FintoClient(server), [{"fixture_id": 80, "league_id": 135, "season_year": 2026}])
    assert len(chiamate_dettaglio(server)) == 5                          # come prima: tutti gli endpoint
    assert len([r for r in db.t["match_events"] if r["fixture_id"] == 80]) == 1
    assert "migrations/season_gaps_2026-09-25.sql" in capsys.readouterr().out   # avviso chiaro, non silenzio


# ===========================================================================
# 7. REPERTI DEL COORDINATORE (R1-R5)
# ===========================================================================
def test_r1_sostituzione_quote_non_tocca_le_quote_csv(mondo):
    db, server = mondo
    db.partita(90, 135, 2024, giorni_fa=3)
    for _ in range(3):
        db.dettaglio("match_odds", 90, 135, 2024, fonte="football_data_csv")   # quote di chiusura da CSV
    db.dettaglio("match_odds", 90, 135, 2024)                                  # vecchia riga API
    pfb.process_single_fixture(FintoClient(server), 90, 135, 2024,
                               sg.flag_per_fixture(coverage(135, 2024)), endpoints=["odds"])
    fonti = [r["snapshot_type"] for r in db.t["match_odds"] if r["fixture_id"] == 90]
    assert fonti.count("football_data_csv") == 3                     # le CSV sopravvivono
    assert fonti.count("api_football") == 1                          # l'API e' stata sostituita, non duplicata
    delete = [p for op, t, p in db.scritture if op == "delete" and t == "match_odds"]
    assert delete                                                    # la delete c'e' stata (solo sulla fonte API)


@pytest.mark.parametrize("modo", ["vuota", "errore"])
def test_r2_risposta_vuota_o_in_errore_non_cancella_mai_righe_presenti(mondo, modo):
    db, server = mondo
    db.partita(91, 135, 2026, giorni_fa=1)
    for tab in TABELLE:
        db.dettaglio(tab, 91, 135, 2026)
    db.dettaglio("match_odds", 91, 135, 2026, fonte="football_data_csv")
    bersaglio = server.vuote if modo == "vuota" else server.in_errore
    for e in ("/fixtures/events", "/fixtures/lineups", "/fixtures/players", "/fixtures/statistics", "/odds"):
        bersaglio.add((e, 91))
    prima = {tab: len([r for r in db.t[tab] if r["fixture_id"] == 91]) for tab in TABELLE}
    st = pfb.process_single_fixture(FintoClient(server), 91, 135, 2026, sg.flag_per_fixture(coverage(135, 2026)))
    dopo = {tab: len([r for r in db.t[tab] if r["fixture_id"] == 91]) for tab in TABELLE}
    assert dopo == prima                                             # nessuna riga cancellata, per OGNI tabella
    assert not [s for s in db.scritture if s[0] == "delete"]
    assert set(st["esiti"].values()) == {"vuoto" if modo == "vuota" else "errore"}


def test_r3_insert_parziale_resta_un_buco_e_si_rifa_al_giro_dopo(mondo, monkeypatch):
    db, server = mondo
    db.partita(92, 135, 2026, giorni_fa=1)
    cov = sg.flag_per_fixture(coverage(135, 2026, ev=True, fo=False, sgio=False, ss=False, qu=False))
    vero = pfb.insert_rows

    def insert_a_meta(table, rows, batch_size=200):             # primo batch scritto, secondo fallito
        vero(table, rows[:1])
        return 1, 1
    monkeypatch.setattr(pfb, "insert_rows", insert_a_meta)
    client = FintoClient(server)
    pfb.backfill_per_fixture_for_league_season(135, 2026, coverage=cov, client=client)
    assert [r for r in db.t["match_events"] if r["fixture_id"] == 92]          # righe PARZIALI presenti
    lac = sg.lacune_stagione(db, 135, 2026)
    assert lac.da_chiamare_per_fixture(cov) == {92: ["events"]}                # ma il buco e' VISIBILE
    assert lac.errori(cov) == 1
    monkeypatch.setattr(pfb, "insert_rows", vero)
    pfb.backfill_per_fixture_for_league_season(135, 2026, coverage=cov, client=client)
    assert client.richieste_http == 2                                          # rifatta al giro dopo
    assert (92, "match_events") not in db.checks                               # 'ok' cancella il controllo
    assert sg.lacune_stagione(db, 135, 2026).aperti(cov) == 0


def test_r4_quote_fuori_finestra_non_si_chiamano_e_non_sono_buchi(mondo):
    db, server = mondo
    cov = sg.flag_per_fixture(coverage(135, 2026, ev=False, fo=False, sgio=False, ss=False, qu=True))
    db.partita(93, 135, 2026, giorni_fa=30)                      # vecchia: storico quote API 7 gg
    db.partita(94, 135, 2026, giorni_fa=2)                       # recente
    db.partita(95, 135, 2026, giorni_fa=2)                       # recente con sole quote CSV
    db.dettaglio("match_odds", 95, 135, 2026, fonte="football_data_csv")
    lac = sg.lacune_stagione(db, 135, 2026)
    assert lac.non_disponibili(cov) == 1 and lac.aperti(cov) == 2
    assert lac.da_chiamare_per_fixture(cov) == {94: ["odds"], 95: ["odds"]}    # CSV non riempie il buco API
    pfb.backfill_per_fixture_for_league_season(135, 2026, lacune=lac, coverage=cov, client=FintoClient(server))
    assert ("/odds", 93) not in chiamate_dettaglio(server)


def test_r4_referto_distingue_quote_non_recuperabili_dai_buchi(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage(999, 2026, ev=False, fo=False, sgio=False, ss=False))
    db.partita(96, 999, 2026, giorni_fa=20)
    ris, righe, _ = _catchup(db, server)
    assert ris.codice == 0 and server.chiamate == []
    assert any("Quote fuori finestra API" in r and ": 1 partite." in r for r in righe)
    assert righe[-1] == "DB SENZA BUCHI"


def test_r5_retrain_tra_le_action_esclusive_e_buco_vecchio_per_concorrenza_esce_0(mondo):
    assert "retrain_models.yml" in sc.WORKFLOW_ESCLUSIVI_DEFAULT
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage(999, 2026))
    db.partita(3, 999, 2026)
    db.t["season_backfill_state"].append({"id": 5, "league_id": 999, "season_year": 2026, "status": "in_progress",
                                          "stats_json": {"meta": {"version": "v2"}, "buco_aperto_dal": "2026-09-20"}})

    class Conc:
        def in_corso(self, forza=False):
            return "action concorrente in_progress: retrain_models.yml"
    ris, righe, _ = _catchup(db, server, concorrenza=Conc())
    assert ris.codice == 0 and server.chiamate == []
    testo = "\n".join(righe)
    assert "Fermato per: action concorrente in_progress: retrain_models.yml" in testo
    assert "RINVIATO (quota/tempo/action concorrente): lega 999 stagione 2026 aperto da 5 gg" in testo
    assert "BUCO VECCHIO" not in testo


# ===========================================================================
# 8. AGGREGATI per lega-stagione (seguito 25/09)
# ===========================================================================
TOP_ENDPOINTS = ("/players/topscorers", "/players/topassists", "/players/topyellowcards", "/players/topredcards")


def classifica_api(lid: int, sy: int) -> List[Dict[str, Any]]:
    """/standings con la struttura reale (response[].league.standings = lista di gruppi)."""
    def riga(rank, tid, nome, punti):
        return {"rank": rank, "team": {"id": tid, "name": nome, "logo": ""}, "points": punti, "goalsDiff": 3,
                "group": "Serie A", "form": "WWD", "status": "same", "description": None,
                "all": {"played": 4, "win": 3, "draw": 1, "lose": 0, "goals": {"for": 8, "against": 5}},
                "home": {}, "away": {}, "update": "2026-09-24T00:00:00+00:00"}
    return [{"league": {"id": lid, "name": "Serie A", "country": "Italy", "logo": "", "flag": "", "season": sy,
                        "standings": [[riga(1, 489, "AC Milan", 10), riga(2, 505, "Inter", 9)]]}}]


def infortuni_api(lid: int, sy: int) -> List[Dict[str, Any]]:
    return [{"player": {"id": 1100, "name": "O. Giroud", "photo": "", "type": "Missing Fixture",
                        "reason": "Knee Injury"},
             "team": {"id": 489, "name": "AC Milan", "logo": ""},
             "fixture": {"id": 777, "timezone": "UTC", "date": "2026-09-27T18:45:00+00:00", "timestamp": 1790000000},
             "league": {"id": lid, "season": sy, "name": "Serie A", "country": "Italy", "logo": "", "flag": ""}}]


def _stagione_piena(db: FintoDB, lid: int, fid: int, giorni_fa: int = 2) -> None:
    db.partita(fid, lid, 2026, giorni_fa=giorni_fa)
    for tab in TABELLE:
        db.dettaglio(tab, fid, lid, 2026)


def _aggregato_presente(db: FintoDB, tab: str, lid: int, quando: datetime) -> None:
    db.t[tab].append({"id": db.nuovo_id(), "league_id": lid, "season_year": 2026, "team_id": 489,
                      "created_at": quando.isoformat(), "updated_at": quando.isoformat()})


def test_agg_mancante_va_in_coda_ed_e_chiamato_poi_db_senza_buchi(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage(555, 2026, aggregati=True))
    _stagione_piena(db, 555, 60)                                  # per-partita completo: solo aggregati
    server.aggregati[("/standings", 555)] = classifica_api(555, 2026)
    server.aggregati[("/injuries", 555)] = infortuni_api(555, 2026)
    ris, righe, _ = _catchup(db, server)
    chiamati = sorted(e for e, p in server.chiamate)
    assert chiamati == sorted(["/standings", "/injuries", *TOP_ENDPOINTS])      # 6 chiamate = costo
    assert ris.chiamate == 6 and ris.codice == 0
    assert len([r for r in db.t["standings"] if r["league_id"] == 555]) == 2
    assert len([r for r in db.t["injuries"] if r["league_id"] == 555]) == 1
    assert righe[-1] == "DB SENZA BUCHI"                           # top_* vuoti = vuoto_api, dichiarati
    stato = next(r for r in db.t["season_backfill_state"] if r["league_id"] == 555)
    assert stato["stats_json"]["aggregati"]["top_scorers"] == "vuoto_api"
    assert stato["stats_json"]["aggregati_tentativi"]["top_scorers"]["esito"] == "vuoto"
    # giro dopo, stesso giorno: tutto fresco o dichiarato vuoto -> ZERO chiamate
    n = len(server.chiamate)
    _catchup(db, server)
    assert len(server.chiamate) == n


def test_agg_presente_e_fresco_zero_chiamate(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage(555, 2026, aggregati=True))
    _stagione_piena(db, 555, 61, giorni_fa=3)
    for tab in ("standings", "top_scorers", "top_assists", "top_cards"):
        _aggregato_presente(db, tab, 555, ADESSO - timedelta(days=2))   # dopo l'ultima partita (3 gg fa)
    _aggregato_presente(db, "injuries", 555, ADESSO - timedelta(hours=5))  # oggi
    ris, righe, _ = _catchup(db, server)
    assert server.chiamate == [] and ris.chiamate == 0
    assert righe[-1] == "DB SENZA BUCHI"


def test_agg_cadenza_classifica_dopo_giornata_injuries_giornaliero_top_settimanale(mondo):
    db, server = mondo
    riga = coverage(555, 2026, aggregati=True)
    ultimo_ft = (ADESSO - timedelta(days=1)).isoformat()
    info = {"_ft": ultimo_ft,
            "standings": {"n": 20, "ultimo": (ADESSO - timedelta(days=2)).isoformat()},     # prima dell'ultima FT
            "injuries": {"n": 5, "ultimo": (ADESSO - timedelta(hours=30)).isoformat()},     # > 20 h
            "top_scorers": {"n": 20, "ultimo": (ADESSO - timedelta(days=3)).isoformat()},   # < 7 gg: aspetta
            "top_assists": {"n": 20, "ultimo": (ADESSO - timedelta(days=9)).isoformat()},   # > 7 gg e FT nuove
            "top_cards": {"n": 20, "ultimo": (ADESSO - timedelta(hours=2)).isoformat()}}
    agg = sa.calcola(riga, info, {}, True, ADESSO)
    assert {n: a["stato"] for n, a in agg.items()} == {
        "standings": "da_aggiornare", "injuries": "da_aggiornare", "top_scorers": "ok",
        "top_assists": "da_aggiornare", "top_cards": "ok"}
    assert sum(a["costo"] for a in agg.values()) == 3
    passata = sa.calcola(riga, info, {}, False, ADESSO)             # stagione finita: injuries non si rifanno
    assert passata["injuries"]["stato"] == "ok" and passata["top_scorers"]["stato"] == "da_aggiornare"


def test_agg_flag_false_non_chiamato_e_dichiarato(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage(555, 2026, aggregati=False))
    _stagione_piena(db, 555, 62)
    ris, righe, _ = _catchup(db, server)
    assert server.chiamate == []
    assert any(r.startswith("  injuries") and "flag_false 1" in r and "NON chiamato" in r for r in righe)
    assert righe[-1] == "DB SENZA BUCHI"


def test_agg_idempotente_nessuna_riga_doppia_e_delete_fallita_non_inserisce(mondo):
    db, server = mondo
    server.aggregati[("/standings", 555)] = classifica_api(555, 2026)
    client = FintoClient(server)
    assert sa.esegui_aggregato(db, client, "standings", 555, 2026) == "righe"
    assert sa.esegui_aggregato(db, client, "standings", 555, 2026) == "righe"
    assert len(db.t["standings"]) == 2                                 # rieseguito: stesse 2 righe, non 4
    db.errori_tabella["standings"] = {"delete": "{'code': '57014'}"}
    assert sa.esegui_aggregato(db, client, "standings", 555, 2026) == "errore"
    assert len(db.t["standings"]) == 2                                 # delete fallita: NESSUN insert
    db.errori_tabella["standings"] = {"insert": "{'code': '57014'}"}
    assert sa.esegui_aggregato(db, client, "standings", 555, 2026) == "parziale"
    stato = sa.stato_aggregato("standings", True, True, 0, None, None,
                               {"at": ADESSO.isoformat(), "esito": "parziale"}, ADESSO)
    assert stato == "errore"                                          # parziale -> si rifa' al giro dopo


def test_agg_errore_api_non_e_vuoto_e_resta_buco(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage(555, 2026, aggregati=True))
    _stagione_piena(db, 555, 63)
    server.errore_aggregati.add(("/standings", 555))
    ris, righe, _ = _catchup(db, server)
    stato = next(r for r in db.t["season_backfill_state"] if r["league_id"] == 555)
    assert stato["stats_json"]["aggregati_tentativi"]["standings"]["esito"] == "errore"
    assert stato["stats_json"]["aggregati"]["standings"] == "errore"
    assert righe[-1].startswith("BUCHI APERTI: 1 lega-stagioni, ~1 chiamate")
    assert any("aggregati da fare: standings=errore" in r for r in righe)


def test_agg_dry_run_mostra_gli_aggregati_per_stagione(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage(135, 2026, aggregati=True))
    _stagione_piena(db, 135, 64)
    _aggregato_presente(db, "standings", 135, ADESSO - timedelta(days=5))       # prima dell'ultima FT
    out = io.StringIO()
    with redirect_stdout(out):
        lo.backfill_full_league(135, dry_run=True, sb=db, quota=quota_per(db, server, None), oggi=OGGI)
    testo = out.getvalue()
    assert server.chiamate == []
    assert "aggregati: standings=da_aggiornare(2026-09-20) ~1  injuries=mancante(-) ~1" in testo
    assert "top_cards=mancante(-) ~2" in testo
    riga_2026 = next(r for r in testo.splitlines() if r.startswith("2026"))
    assert riga_2026.split()[-2:] == ["6", "procederei"]            # Chiam.~ include gli aggregati (1+1+1+1+2)
