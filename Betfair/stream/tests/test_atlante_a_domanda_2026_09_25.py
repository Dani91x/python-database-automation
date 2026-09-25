"""Atlante Hazard A DOMANDA e per TUTTE le leghe con dati (25/09/2026, ordine
dell'utente: "leggero e adattabile in base alle PARTITE LIVE [...] deve
aggiornarsi man mano che le partite e le stagioni avanzano [...] non deve
pesare sul DB").

Nessuna rete, nessun DB. ``DBFinto`` risponde come PostgREST (filtri eq/in/
gt/gte/lt, ``and=(...)``, booleani ``eq.true``, order, limit, select) sulle
tabelle con le colonne VERE: ``fixture_predictions`` (quelle di
``omega_db.fixtures_for_window``), ``api_coverage_by_season``
(``leagues_mapper``), ``matches`` (``G.COLONNE_MATCH``), ``match_events``
(``G.COLONNE_GOL``), ``hazard_atlas_leghe`` (``migrations/hazard_atlas_2026-09-24.sql``).
Lo scrittore e' il VERO ``_Scrittore`` con la sola ``_req`` finta (le righe
POSTate si guardano col formato che andrebbe al DB).
"""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any, Dict, List, Optional

import pytest

from Betfair.stream.scalper import atlante_a_domanda as AD
from Betfair.stream.scalper import genera_atlante as G
from Betfair.stream.scalper import hazard_atlas as HA

T0 = dt.datetime(2026, 9, 25, 12, 0, tzinfo=dt.timezone.utc).timestamp()


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()


# ------------------------------------------------------------ righe finte
def _fp(fid: int, lid: int, ko: float, home: int = 1, away: int = 2) -> Dict[str, Any]:
    """Riga di ``fixture_predictions`` (colonne lette da fixtures_for_window)."""
    return {"fixture_id": fid, "league_id": lid, "home_team_id": home, "away_team_id": away,
            "fixture_date": _iso(ko), "home_team_name": f"T{home}", "away_team_name": f"T{away}"}


def _cov(lid: int, anno: int, eventi: bool) -> Dict[str, Any]:
    """Riga di ``api_coverage_by_season`` (colonne di leagues_mapper)."""
    return {"league_id": lid, "league_name": f"Lega {lid}", "country_name": "X",
            "season_year": anno, "season_start": f"{anno}-08-01", "season_end": f"{anno + 1}-05-31",
            "current": False, "fixtures_events": eventi, "fixtures_lineups": eventi,
            "fixtures_statistics_fixtures": False, "fixtures_statistics_players": False,
            "standings": True, "players": False, "top_scorers": False, "top_assists": False,
            "top_cards": False, "injuries": False, "predictions": True, "odds": False}


def _match(fid: int, lid: int, anno: int, gh: int, ga: int, *, home: int = 1, away: int = 2,
           status: str = "FT", data: str = "2025-10-01T15:00:00+00:00", extra: Any = None) -> Dict[str, Any]:
    return {"fixture_id": fid, "league_id": lid, "season_year": anno, "fixture_date": data,
            "status_short": status, "home_team_id": home, "home_team_name": f"T{home}",
            "away_team_id": away, "away_team_name": f"T{away}", "goals_home": gh,
            "goals_away": ga, "halftime_home": 0, "halftime_away": 0,
            # 25/09 sera: raw_json (API-Football), da cui PostgREST estrae
            # fixture.status.extra (``G.COLONNE_MATCH``)
            "raw_json": {"fixture": {"id": fid, "status": {"long": "Match Finished", "short": status,
                                                           "elapsed": 90, "extra": extra}}}}


def _ev(eid: int, fid: int, lid: int, anno: int, team: int, minute: int, *,
        etype: str = "Goal", detail: str = "Normal Goal", extra: Any = None) -> Dict[str, Any]:
    return {"id": eid, "fixture_id": fid, "league_id": lid, "season_year": anno,
            "team_id": team, "event_type": etype, "detail": detail, "minute": minute,
            "minute_extra": extra}


# --------------------------------------------------------- PostgREST finto
def _val(x: Any) -> Any:
    if isinstance(x, bool):
        return str(x).lower()
    return x


def _cmp(a: Any, b: str) -> Optional[int]:
    if a is None:
        return None
    for conv in (lambda v: dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")), float):
        try:
            x, y = conv(a), conv(b)
            return (x > y) - (x < y)
        except (TypeError, ValueError):
            continue
    return (str(a) > b) - (str(a) < b)


def _filtra(rows: List[Dict[str, Any]], col: str, espr: str) -> List[Dict[str, Any]]:
    op, _, val = espr.partition(".")
    if op == "eq":
        return [r for r in rows if str(_val(r.get(col))) == val]
    if op == "in":
        vals = set(val.strip("()").split(","))
        return [r for r in rows if str(r.get(col)) in vals]
    ops = {"gt": lambda c: c == 1, "gte": lambda c: c >= 0, "lt": lambda c: c == -1}
    return [r for r in rows if _cmp(r.get(col), val) is not None and ops[op](_cmp(r.get(col), val))]


def seleziona(r: Dict[str, Any], cols: str) -> Dict[str, Any]:
    """``select`` come PostgREST: colonna semplice, oppure ``alias:col->a->b``
    (cammino JSON dentro una colonna jsonb; null se manca un pezzo)."""
    out: Dict[str, Any] = {}
    for c in cols.split(","):
        if ":" in c:
            alias, cammino = c.split(":", 1)
            parti = cammino.split("->")
            v: Any = r.get(parti[0])
            for k in parti[1:]:
                v = v.get(k) if isinstance(v, dict) else None
            out[alias] = v
        else:
            out[c] = r.get(c)
    return out


class DBFinto(G.LettoreDB):
    def __init__(self, tabelle: Dict[str, List[Dict[str, Any]]]) -> None:
        super().__init__("http://finto", "x", pausa=0.0)
        self.tabelle = tabelle
        self.chiamate: List[tuple] = []

    def get(self, table: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
        self.chiamate.append((table, dict(params)))
        rows = [dict(r) for r in self.tabelle.get(table, [])]
        for k, v in params.items():
            if k in ("select", "order", "limit", "offset"):
                continue
            if k == "and":
                for parte in v.strip("()").split(","):
                    col, _, espr = parte.partition(".")
                    rows = _filtra(rows, col, espr)
                continue
            rows = _filtra(rows, k, v)
        if "order" in params:
            col, _, verso = params["order"].partition(".")
            rows.sort(key=lambda r: str(r.get(col)) if col == "fixture_date" else r.get(col),
                      reverse=verso.startswith("desc"))
        if "limit" in params:
            rows = rows[: int(params["limit"])]
        cols = params.get("select", "*")
        if cols != "*":
            rows = [seleziona(r, cols) for r in rows]
        self.n_richieste += 1
        self.n_righe += len(rows)
        return rows

    def chiamate_a(self, table: str) -> List[Dict[str, str]]:
        return [p for t, p in self.chiamate if t == table]


class ScrittoreFinto(G._Scrittore):
    """Il VERO _Scrittore: solo la HTTP e' finta (upsert su ``hazard_atlas_leghe``)."""

    def __init__(self, db: DBFinto) -> None:
        super().__init__("http://finto", "x")
        self.db = db
        self.post: List[tuple] = []

    def _req(self, metodo: str, path: str, corpo: Any = None, prefer: str = "") -> None:
        self.post.append((metodo, path, corpo, prefer))
        if metodo == "POST" and path.startswith("hazard_atlas_leghe"):
            tab = self.db.tabelle.setdefault("hazard_atlas_leghe", [])
            for riga in corpo:
                tab[:] = [r for r in tab if r["league_id"] != riga["league_id"]]
                tab.append(json.loads(json.dumps(riga)))


def _storico(lid: int, anni: List[int], per_anno: int, base_fid: int, base_eid: int
             ) -> Dict[str, List[Dict[str, Any]]]:
    """Partite FT 1-0 (gol al 30') per ciascuna stagione, eventi completi."""
    m, e = [], []
    fid, eid = base_fid, base_eid
    for anno in anni:
        for _ in range(per_anno):
            m.append(_match(fid, lid, anno, 1, 0))
            e.append(_ev(eid, fid, lid, anno, 1, 30))
            fid += 1
            eid += 1
    return {"matches": m, "match_events": e}


@pytest.fixture()
def cartella(tmp_path):
    seme = {"meta": {"name": "hazard_atlas_v3", "generated_at": "2026-09-24T19:00:00+00:00",
                     "n_fixtures_used": 53187,
                     "shrinkage": {"K_league_fixture_minutes": 1500.0}},
            "global": {b: {k: {"p_goal_next_3min": 0.1, "p_goal_next_2min": 0.07, "n": 90000}
                           for k in G.GOAL_KEYS} for b in G.BUCKETS},
            "by_league": {"39": {"meta": {"league_name": "Premier League", "n_fixtures": 3799,
                                          "side_rate_per_bucket": {b: 0.07 for b in G.BUCKETS}},
                                 "grid": {b: {k: {"p_goal_next_3min": 0.11, "p_goal_next_2min": 0.08,
                                                  "n": 20000} for k in G.GOAL_KEYS}
                                          for b in G.BUCKETS}}},
            "by_team": {}, "h2h_hint": {}}
    p_seme = tmp_path / "seme.json"
    p_seme.write_text(json.dumps(seme), encoding="utf-8")
    return {"live": str(tmp_path / "live.json"), "stato": str(tmp_path / "stato.json"),
            "seme": str(p_seme)}


def _motore(db: DBFinto, cartella: Dict[str, str], ora: List[float], *, scrittore: Any = None,
            **par: float) -> AD.MotoreAtlante:
    parametri = {"pausa_lega_s": 0.0}
    parametri.update(par)
    return AD.MotoreAtlante(db, scrittore=scrittore, path_live=cartella["live"],
                            path_stato=cartella["stato"], path_seme=cartella["seme"],
                            parametri=parametri, orologio=lambda: ora[0], sleep=lambda s: None)


def _db_lega_900() -> Dict[str, List[Dict[str, Any]]]:
    st = _storico(900, [2023, 2024, 2025], 4, 1000, 50000)
    return {"fixture_predictions": [_fp(7001, 900, T0 + 3600)],
            "api_coverage_by_season": [_cov(900, 2023, False), _cov(900, 2024, True),
                                       _cov(900, 2025, True), _cov(900, 2026, False)],
            "matches": st["matches"], "match_events": st["match_events"]}


def _leggi(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------ 1) lega nuova: UNA volta sola
def test_lega_nuova_calcolata_una_volta_sola_e_seconda_comparsa_senza_richieste(cartella):
    db = DBFinto(_db_lega_900())
    scr = ScrittoreFinto(db)
    ora = [T0]
    m = _motore(db, cartella, ora, scrittore=scr)
    r = m.ciclo()
    assert r["preparate"] == {"900": "calcolata"}
    st = m.leghe["900"]
    # le stagioni SENZA eventi in coverage non si scaricano nemmeno
    anni_letti = {p.get("season_year") for p in db.chiamate_a("matches")}
    assert anni_letti == {"eq.2024", "eq.2025"}
    # i gol si leggono per fixture_id (indice), mai per lega/stagione su match_events
    ev = db.chiamate_a("match_events")
    assert ev and all("season_year" not in p and "league_id" not in p for p in ev)
    assert all(p["fixture_id"].startswith("in.(") and p["event_type"] == "eq.Goal" for p in ev)
    assert st["n_fixtures"] == 8 and st["stagioni_acquisite"] == [2024, 2025]
    # salvata su hazard_atlas_leghe con le colonne della migrazione
    riga = db.tabelle["hazard_atlas_leghe"][0]
    assert set(riga) == {"league_id", "league_name", "n_fixtures", "last_fixture_date",
                         "updated_at", "stato", "fixtures"}
    assert riga["league_id"] == 900 and len(riga["fixtures"]) == 8
    # nel file live: la lega c'e', con n e confidenza
    atl = _leggi(cartella["live"])
    assert atl["by_league"]["900"]["meta"]["n_fixtures"] == 8
    assert atl["by_league"]["900"]["meta"]["confidenza"] == "bassa"
    assert atl["meta"]["leghe_in_preparazione"] == []
    # SECONDA comparsa (10' dopo): solo la GET delle partite osservate
    n0 = len(db.chiamate)
    ora[0] = T0 + 600
    m.ciclo()
    nuove = [t for t, _ in db.chiamate[n0:]]
    assert nuove == ["fixture_predictions"]
    # RIAVVIO del PC: lo stato locale basta, nessuna richiesta per la lega
    n1 = len(db.chiamate)
    m2 = _motore(db, cartella, ora, scrittore=scr)
    ora[0] = T0 + 1200
    m2.ciclo()
    assert [t for t, _ in db.chiamate[n1:]] == ["fixture_predictions"]
    assert m2.leghe["900"]["n_fixtures"] == 8


def test_lega_gia_sul_db_si_adotta_con_una_sola_get(cartella):
    db = DBFinto(_db_lega_900())
    ora = [T0]
    _motore(db, cartella, ora, scrittore=ScrittoreFinto(db)).ciclo()
    os.remove(cartella["stato"])                         # altro PC / file perso
    n0 = len(db.chiamate)
    m = _motore(db, cartella, ora)
    r = m.ciclo()
    assert r["preparate"] == {"900": "db"}
    tavole = [t for t, _ in db.chiamate[n0:]]
    assert "matches" not in tavole and "match_events" not in tavole
    assert tavole.count("hazard_atlas_leghe") == 1
    assert m.leghe["900"]["n_fixtures"] == 8 and len(m.leghe["900"]["fixtures"]) == 8


# ----------------------------------------- 2) incrementale: solo il nuovo
def test_incrementale_legge_solo_le_partite_nuove_e_aspetta_gli_eventi(cartella):
    db = DBFinto(_db_lega_900())
    ora = [T0]
    m = _motore(db, cartella, ora)
    m.ciclo()
    assert m.leghe["900"]["n_fixtures"] == 8
    # tre partite della lega finite ieri sera: 2-0 con eventi, 1-0 SENZA
    # eventi (backfill non ancora passato), 0-0 senza nessun evento
    # (stagione 2025: eventi dichiarati in coverage)
    ko = T0 - 5 * 3600
    db.tabelle["fixture_predictions"] += [_fp(8001, 900, ko), _fp(8002, 900, ko), _fp(8003, 900, ko)]
    db.tabelle["matches"] += [_match(8001, 900, 2025, 2, 0), _match(8002, 900, 2025, 1, 0),
                              _match(8003, 900, 2025, 0, 0)]
    db.tabelle["match_events"] += [_ev(90001, 8001, 900, 2025, 1, 10), _ev(90002, 8001, 900, 2025, 1, 80)]
    n0 = len(db.chiamate)
    ora[0] = T0 + 600
    r = m.ciclo()
    lette = db.chiamate[n0:]
    # nessuna rilettura di stagione: SOLO per fixture_id
    assert all("season_year" not in p for t, p in lette if t in ("matches", "match_events"))
    assert [p["fixture_id"] for t, p in lette if t == "matches"] == ["in.(8001,8002,8003)"]
    assert r["incrementale"]["aggiunte"] == 1 and r["incrementale"]["in_attesa"] == 2
    assert m.leghe["900"]["n_fixtures"] == 9
    # arrivano gli eventi: il 1-0 e lo 0-0 (un cartellino) si contano, la 8001 no (gia' contata)
    db.tabelle["match_events"] += [_ev(90003, 8002, 900, 2025, 1, 55),
                                   _ev(90004, 8003, 900, 2025, 2, 40, etype="Card", detail="Yellow Card")]
    # 10' dopo: le partite in attesa NON si rileggono (si riprova ogni 60')
    n1 = len(db.chiamate)
    ora[0] = T0 + 1200
    m.ciclo()
    assert [t for t, _ in db.chiamate[n1:]] == ["fixture_predictions"]
    # passata l'ora: si riprovano e si contano
    n1 = len(db.chiamate)
    ora[0] = T0 + 600 + 3601
    r = m.ciclo()
    assert [p["fixture_id"] for t, p in db.chiamate[n1:] if t == "matches"] == ["in.(8002,8003)"]
    assert r["incrementale"]["aggiunte"] == 2 and m.leghe["900"]["n_fixtures"] == 11
    # giro dopo: nulla di nuovo, nessuna lettura di partite
    n2 = len(db.chiamate)
    ora[0] = T0 + 600 + 7300
    m.ciclo()
    assert [t for t, _ in db.chiamate[n2:]] == ["fixture_predictions"]


def test_scrittura_su_db_a_blocchi_non_a_ogni_partita(cartella):
    """La lega appena calcolata va sul DB subito; gli aggiornamenti delle
    partite finite si accumulano e partono insieme ogni scrivi_db_ogni_h."""
    db = DBFinto(_db_lega_900())
    scr = ScrittoreFinto(db)
    ora = [T0]
    m = _motore(db, cartella, ora, scrittore=scr, scrivi_db_ogni_h=6)
    m.ciclo()
    post = [p for p in scr.post if p[0] == "POST"]
    assert len(post) == 1                                    # la lega calcolata
    ko = T0 - 5 * 3600
    db.tabelle["fixture_predictions"].append(_fp(8201, 900, ko))
    db.tabelle["matches"].append(_match(8201, 900, 2025, 1, 0))
    db.tabelle["match_events"].append(_ev(92001, 8201, 900, 2025, 1, 12))
    ora[0] = T0 + 600
    m.ciclo()
    assert m.leghe["900"]["n_fixtures"] == 9
    assert len([p for p in scr.post if p[0] == "POST"]) == 1   # accumulata, non scritta
    assert m.da_scrivere == {"900"}
    ora[0] = T0 + 6 * 3600 + 1
    m.ciclo()
    post = [p for p in scr.post if p[0] == "POST"]
    assert len(post) == 2 and post[-1][2][0]["n_fixtures"] == 9
    assert db.tabelle["hazard_atlas_leghe"][0]["n_fixtures"] == 9 and m.da_scrivere == set()


def test_partita_di_stagione_senza_eventi_in_coverage_si_chiude_subito(cartella):
    """Stagione 2026 con fixtures_events=false (il reperto del 24/09): una
    partita finita senza eventi NON resta in attesa (si chiude subito, zero
    riletture); una partita osservata che ``matches`` non ha ancora si aspetta."""
    db = DBFinto(_db_lega_900())
    ora = [T0]
    m = _motore(db, cartella, ora)
    m.ciclo()
    ko = T0 - 5 * 3600
    db.tabelle["fixture_predictions"] += [_fp(8101, 900, ko), _fp(8102, 900, ko)]
    db.tabelle["matches"].append(_match(8101, 900, 2026, 2, 1))          # nessun evento: coverage 2026 false
    ora[0] = T0 + 600
    r = m.ciclo()
    assert r["incrementale"]["chiuse"] == 1 and r["incrementale"]["in_attesa"] == 1
    assert "8101" in m.chiuse and "8102" in m.in_attesa
    assert m.leghe["900"]["n_fixtures"] == 8
    # oltre l'ora: si rilegge SOLO quella che mancava in matches
    n0 = len(db.chiamate)
    ora[0] = T0 + 600 + 3601
    m.ciclo()
    assert [p["fixture_id"] for t, p in db.chiamate[n0:] if t == "matches"] == ["in.(8102)"]


# ------------------------------------------------ 3) tetto per ciclo/ora
def test_tetto_per_ciclo_e_per_ora_e_leghe_in_preparazione(cartella):
    tab: Dict[str, List[Dict[str, Any]]] = {"fixture_predictions": [], "api_coverage_by_season": [],
                                            "matches": [], "match_events": []}
    for i, lid in enumerate((901, 902, 903, 904, 905)):
        tab["fixture_predictions"].append(_fp(7100 + i, lid, T0 + 600 * (i + 1)))
        tab["api_coverage_by_season"].append(_cov(lid, 2025, True))
        st = _storico(lid, [2025], 2, 10000 * (i + 1), 100000 * (i + 1))
        tab["matches"] += st["matches"]
        tab["match_events"] += st["match_events"]
    db = DBFinto(tab)
    ora = [T0]
    m = _motore(db, cartella, ora, tetto_ciclo=2, tetto_ora=3)
    r = m.ciclo()
    assert sorted(r["preparate"]) == ["901", "902"]         # prima chi gioca prima
    assert _leggi(cartella["live"])["meta"]["leghe_in_preparazione"] == [903, 904, 905]
    ora[0] = T0 + 600
    r = m.ciclo()
    assert sorted(r["preparate"]) == ["903"]                # tetto orario: 3
    ora[0] = T0 + 3700
    r = m.ciclo()
    assert sorted(r["preparate"]) == ["904", "905"]
    assert _leggi(cartella["live"])["meta"]["leghe_in_preparazione"] == []


# --------------------------------------------- 4) stagione nuova acquisita
def test_stagione_nuova_in_coverage_acquisita_senza_intervento(cartella):
    db = DBFinto(_db_lega_900())
    ora = [T0]
    m = _motore(db, cartella, ora, ricontrollo_stagioni_h=24)
    m.ciclo()
    assert m.leghe["900"]["stagioni_acquisite"] == [2024, 2025]
    # la coverage 2026 diventa fixtures_events=true e le partite ci sono
    for r in db.tabelle["api_coverage_by_season"]:
        if r["season_year"] == 2026:
            r["fixtures_events"] = True
    st = _storico(900, [2026], 3, 3000, 70000)
    db.tabelle["matches"] += st["matches"]
    db.tabelle["match_events"] += st["match_events"]
    # prima del ricontrollo (1 h dopo) nulla
    ora[0] = T0 + 3600
    m.ciclo()
    assert m.leghe["900"]["stagioni_acquisite"] == [2024, 2025]
    n0 = len(db.chiamate)
    ora[0] = T0 + 25 * 3600
    db.tabelle["fixture_predictions"] = [_fp(7002, 900, ora[0] + 3600)]
    r = m.ciclo()
    assert r["stagioni_nuove"] == {"900": [2026]}
    assert {p.get("season_year") for t, p in db.chiamate[n0:] if t == "matches"} == {"eq.2026"}
    assert m.leghe["900"]["stagioni_acquisite"] == [2024, 2025, 2026]
    assert m.leghe["900"]["n_fixtures"] == 11


def test_stagioni_con_eventi_legge_solo_le_true():
    db = DBFinto({"api_coverage_by_season": [_cov(5, 2020, True), _cov(5, 2021, False),
                                             _cov(6, 2022, True)]})
    assert G.stagioni_con_eventi(db, [5, 6, 7]) == {"5": [2020], "6": [2022], "7": []}
    assert len(db.chiamate) == 1
    # il filtro sta sul SERVER: le righe false non viaggiano nemmeno
    assert db.chiamate[0][1]["fixtures_events"] == "eq.true"
    assert db.chiamate[0][1]["select"] == "league_id,season_year,fixtures_events"


# ------------------------------------ 5) lookup per la partita osservata
def test_lookup_partita_osservata_livello_n_confidenza_eta(cartella):
    db = DBFinto(_db_lega_900())
    db.tabelle["fixture_predictions"].append(_fp(7009, 950, T0 + 7200))
    db.tabelle["api_coverage_by_season"].append(_cov(950, 2025, True))
    ora = [T0]
    m = _motore(db, cartella, ora, tetto_ciclo=1)
    m.ciclo()
    atl = _leggi(cartella["live"])
    c = HA.consulta_atlante(atl, 31, 1, 900, adesso=dt.datetime(2026, 9, 25, 13, tzinfo=dt.timezone.utc))
    assert c["livello"] == "lega" and c["fonte"] == "league"
    assert c["n"] == atl["by_league"]["900"]["grid"]["30-35"]["1"]["n"]
    assert c["confidenza"] == "bassa" and c["lega"]["n_partite"] == 8
    assert c["eta_giorni"] == pytest.approx(1 / 24, abs=0.01)
    assert c["nota"].startswith("storico lega 900 (lega, 8 partite)")
    assert "n=" in c["nota"] and "confidenza bassa" in c["nota"]
    # stessa probabilita' della forma storica
    assert HA.hazard_lookup(atl, 31, 1, 900) == (c["p"], "league")
    # la seconda lega e' in preparazione (tetto 1): globale, e lo dice
    c2 = HA.consulta_atlante(atl, 31, 1, 950)
    assert c2["livello"] == "globale" and c2["lega"]["in_preparazione"] is True
    assert "in preparazione" in c2["nota"]
    # stato vuoto su una lega del seme (Premier): dal seme, dichiarato
    c3 = HA.consulta_atlante(atl, 31, 1, 39)
    assert c3["livello"] == "lega" and c3["lega"]["da_seme"] is True and "dal seme" in c3["nota"]
    # il globale e' quello del seme finche' le leghe affidabili non bastano
    assert atl["meta"]["globale"]["fonte"] == "seme"


def test_consulta_squadre_per_id_e_solo_su_lega_affidabile():
    sr = {b: 0.07 for b in G.BUCKETS}
    cella = {"p_goal_next_3min": 0.10, "p_goal_next_2min": 0.07, "n": 5000}
    squadra = {"att_goals_per_match_by_bucket": {b: 0.14 for b in G.BUCKETS},
               "def_goals_per_match_by_bucket": {b: 0.07 for b in G.BUCKETS}}
    atl = {"meta": {"generated_at": "2026-09-25T02:00:00+00:00", "n_fixtures_used": 1000,
                    "min_fixtures_league": 300},
           "global": {"30-35": {"1": dict(cella)}},
           "by_league": {
               "10": {"meta": {"league_name": "A", "n_fixtures": 900, "affidabile": True,
                               "confidenza": "alta", "side_rate_per_bucket": sr},
                      "grid": {"30-35": {"1": dict(cella)}}},
               "11": {"meta": {"league_name": "B", "n_fixtures": 50, "affidabile": False,
                               "confidenza": "bassa", "side_rate_per_bucket": sr},
                      "grid": {"30-35": {"1": dict(cella)}}}},
           "by_team": {"1": dict(squadra, team_name="Uno", league_id=10, n_matches=40),
                       "2": dict(squadra, team_name="Due", league_id=10, n_matches=40)}}
    c = HA.consulta_atlante(atl, 31, 1, 10, home_id=1, away_id=2)
    assert c["livello"] == "squadra+lega"
    assert c["p"] == pytest.approx(1 - (1 - 0.10) ** 2.0)
    c = HA.consulta_atlante(atl, 31, 1, 11, home_id=1, away_id=2)
    assert c["livello"] == "lega" and c["confidenza"] == "bassa"   # lega non affidabile
    # per nome: omonimi in due leghe -> vince quella della partita, altrimenti nessuna
    atl["by_team"]["3"] = dict(squadra, team_name="Uno", league_id=12, n_matches=40)
    assert HA.consulta_atlante(atl, 31, 1, 10, home_team="Uno", away_team="Due")["livello"] == \
        "squadra+lega"
    atl["by_team"]["4"] = dict(squadra, team_name="Due", league_id=13, n_matches=40)
    atl["by_team"]["2"]["league_id"] = 14
    assert HA.consulta_atlante(atl, 31, 1, 10, home_team="Uno", away_team="Due")["livello"] == "lega"


# ---------------------------------------------- 6) metodo invariato
def _stato_con(lid: int, n: int, base_fid: int, minuto: int, home: int = 1, away: int = 2
               ) -> Dict[str, Any]:
    st = G.stato_lega_vuoto(lid, f"Lega {lid}")
    for i in range(n):
        fid = base_fid + i
        seq, motivo = G.sequenza_partita(_match(fid, lid, 2025, 1, 0, home=home, away=away),
                                         [_ev(fid * 10, fid, lid, 2025, home, minuto)])
        assert motivo == "ok"
        G.aggiungi_partita(st, seq)
    return st


def test_lega_affidabile_identica_con_o_senza_le_leghe_piccole():
    """La lega "Premier" (affidabile) e il globale NON cambiano quando nello
    stato entrano leghe piccole: stessa griglia, stesso side_rate, stessi
    profili squadra. La piccola entra shrinkata verso il globale."""
    grande = _stato_con(39, 12, 100, 10)                  # squadre 1 e 2 (>= 10 partite)
    piccola = _stato_con(77, 2, 900, 70, home=5, away=6)
    solo = G.assembla({"39": json.loads(json.dumps(grande))}, generated_at="g", min_fixtures_league=12)
    tutte = G.assembla({"39": json.loads(json.dumps(grande)), "77": piccola}, generated_at="g",
                       min_fixtures_league=12)
    assert tutte["global"] == solo["global"]
    assert tutte["by_league"]["39"] == solo["by_league"]["39"]
    assert tutte["by_team"]["1"] == solo["by_team"]["1"]
    cella = tutte["by_league"]["77"]["grid"]["5-10"]["0"]
    gp = tutte["global"]["5-10"]["0"]["p_goal_next_3min"]
    n, s3, _ = piccola["cells"]["5-10"]["0"]
    assert cella["p_goal_next_3min"] == round((s3 + G.K_LEAGUE * gp) / (n + G.K_LEAGUE), 5)
    assert cella["n"] == n and cella["conf"] == "bassa"
    assert tutte["by_league"]["77"]["meta"]["affidabile"] is False


def test_confidenze_dalle_soglie_dichiarate():
    k = G.K_LEAGUE
    assert G.confidenza_cella(int(k)) == "alta"
    assert G.confidenza_cella(int(k) - 1) == "media"
    assert G.confidenza_cella(int(k / 4)) == "media"
    assert G.confidenza_cella(int(k / 4) - 1) == "bassa"
    assert G.confidenza_lega(300) == "alta" and G.confidenza_lega(299) == "media"
    assert G.confidenza_lega(100) == "media" and G.confidenza_lega(99) == "bassa"


# ------------------------------------------- 7) rete notturna
def test_incrementale_notturno_solo_leghe_in_stato():
    db = DBFinto({"match_events": [_ev(11, 1, 900, 2025, 1, 10), _ev(12, 2, 555, 2025, 1, 20)],
                  "matches": [_match(1, 900, 2025, 1, 0), _match(2, 555, 2025, 1, 0)]})
    stati = {"900": G.stato_lega_vuoto(900)}
    wm, c, t = G.incrementale(db, stati, 10, {}, "x", solo_leghe_in_stato=True)
    assert wm == 12 and t == ["900"] and "555" not in stati
    assert [p["fixture_id"] for tb, p in db.chiamate if tb == "matches"] == ["in.(1)"]
    assert stati["900"]["n_fixtures"] == 1


def test_cli_senza_filigrana_parte_da_ora_invece_di_fermarsi(monkeypatch):
    db = DBFinto({"match_events": [_ev(500, 1, 900, 2025, 1, 10)], "matches": [],
                  "hazard_atlas_leghe": [], "hazard_atlas": []})
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "x")
    monkeypatch.setattr(G, "LettoreDB", lambda url, key, **kw: db)
    assert G.main(["--stato-db", "--incrementale", "--solo-leghe-in-stato",
                   "--filigrana-da-ora-se-assente"]) == 0
    ultima = [p for t, p in db.chiamate if t == "match_events" and p.get("order") == "id.desc"]
    assert ultima and ultima[0]["limit"] == "1"
