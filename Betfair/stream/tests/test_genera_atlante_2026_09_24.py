"""Generatore INCREMENTALE dell'Atlante Hazard + sync dal DB + ricarica dei
consumatori (24/09/2026, ordine dell'utente: "strumento AUTOMATICO che si
aggiorna in base alle leghe e alle partite").

Nessuna rete, nessun DB: il lettore finto risponde come PostgREST (stesse
colonne di ``matches`` e ``match_events``, stessi filtri eq/in/gt, order,
limit) e la paginazione a chiave vera (``LettoreDB.tutte``) gira su di lui.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import pytest

from Betfair.stream.scalper import genera_atlante as G
from Betfair.stream.scalper import hazard_atlas as HA
from Betfair.stream.scalper import hazard_atlas_sync as SY


# ---------------------------------------------------------------- dati finti
def _match(fid: int, lid: int, gh: int, ga: int, *, home: int = 1, away: int = 2,
           season: int = 2025, status: str = "FT", date: str = "2026-09-20T15:00:00+00:00",
           hth: int = 0, hta: int = 0) -> Dict[str, Any]:
    """Riga con le colonne VERE di ``matches`` (quelle che il generatore legge)."""
    return {"fixture_id": fid, "league_id": lid, "season_year": season, "fixture_date": date,
            "status_short": status, "home_team_id": home, "home_team_name": f"T{home}",
            "away_team_id": away, "away_team_name": f"T{away}", "goals_home": gh,
            "goals_away": ga, "halftime_home": hth, "halftime_away": hta}


def _ev(eid: int, fid: int, lid: int, team: int, minute: int, *, detail: str = "Normal Goal",
        etype: str = "Goal", season: int = 2025) -> Dict[str, Any]:
    """Riga con le colonne VERE di ``match_events``."""
    return {"id": eid, "fixture_id": fid, "league_id": lid, "season_year": season,
            "team_id": team, "event_type": etype, "detail": detail, "minute": minute,
            "minute_extra": None}


class LettoreFinto(G.LettoreDB):
    """PostgREST in memoria: filtri eq./in./gt., order=<col>.asc, limit."""

    def __init__(self, tabelle: Dict[str, List[Dict[str, Any]]]) -> None:
        super().__init__("http://finto", "x", pausa=0.0)
        self.tabelle = tabelle
        self.chiamate: List[tuple] = []

    def get(self, table: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
        self.chiamate.append((table, dict(params)))
        rows = list(self.tabelle.get(table, []))
        for k, v in params.items():
            if k in ("select", "order", "limit", "offset"):
                continue
            op, _, val = v.partition(".")
            if op == "eq":
                rows = [r for r in rows if str(r.get(k)) == val]
            elif op == "gt":
                rows = [r for r in rows if r.get(k) is not None and float(r[k]) > float(val)]
            elif op == "in":
                vals = set(val.strip("()").split(","))
                rows = [r for r in rows if str(r.get(k)) in vals]
        if "order" in params:
            col, _, verso = params["order"].partition(".")
            rows.sort(key=lambda r: r.get(col), reverse=verso.startswith("desc"))
        if "limit" in params:
            rows = rows[: int(params["limit"])]
        cols = params.get("select", "*")
        if cols != "*":
            rows = [{c: r.get(c) for c in cols.split(",")} for r in rows]
        self.n_richieste += 1
        return rows


# ------------------------------------------------------ 1) la partita
def test_sequenza_regole_del_v1():
    m = _match(10, 39, 2, 1)
    ev = [_ev(1, 10, 39, 1, 10), _ev(2, 10, 39, 2, 45), _ev(3, 10, 39, 1, 95),
          _ev(4, 10, 39, 1, 30, detail="Missed Penalty")]
    seq, motivo = G.sequenza_partita(m, ev)
    assert motivo == "ok"
    assert seq["goals"] == [[10, "h"], [45, "a"], [90, "h"]]      # 95 -> 90, rigore sbagliato fuori
    assert G.sequenza_partita(_match(11, 39, 2, 0), [_ev(5, 11, 39, 1, 3)])[1] == \
        "gol_diversi_dal_punteggio"
    assert G.sequenza_partita(_match(12, 39, 0, 0, status="AET"), [])[1] == "non_ft"
    # autogol con il team_id del giocatore: i lati non tornano -> si gira l'autogol
    seq, motivo = G.sequenza_partita(_match(13, 39, 1, 0), [_ev(6, 13, 39, 2, 20, detail="Own Goal")])
    assert motivo == "ok" and seq["goals"] == [[20, "h"]]


def test_conteggi_di_una_partita_e_idempotenza():
    st = G.stato_lega_vuoto(39)
    seq, _ = G.sequenza_partita(_match(20, 39, 1, 0), [_ev(1, 20, 39, 1, 10)])
    assert G.aggiungi_partita(st, seq) is True
    # m=0..4 a 0 gol, nessun gol entro 3'
    assert st["cells"]["0-5"]["0"] == [5, 0, 0]
    # m=5..9 a 0 gol: gol al 10' in (m, m+3] per m=7,8,9; in (m, m+2] per m=8,9
    assert st["cells"]["5-10"]["0"] == [5, 3, 2]
    # m=10..14: 1 gol gia' segnato
    assert st["cells"]["10-15"]["1"] == [5, 0, 0]
    assert st["cells"]["85-90"]["1"] == [3, 0, 0]                 # m=85..87
    assert sum(c[0] for b in st["cells"].values() for c in b.values()) == 88
    assert st["side_goals"]["5-10"] == 1                          # gol al 10' -> (5, 10]
    assert st["teams"]["1"]["att"]["5-10"] == 1 and st["teams"]["2"]["def"]["5-10"] == 1
    assert st["h2h"]["1-2"]["ft"] == {"1-0": 1}
    assert G.aggiungi_partita(st, seq) is False                   # mai due volte
    assert st["n_fixtures"] == 1 and st["n_goals"] == 1


# --------------------------------------------------- 2) assemblaggio
def _stato_con(lid: int, partite: List[tuple], base_fid: int) -> Dict[str, Any]:
    st = G.stato_lega_vuoto(lid, f"Lega {lid}")
    for i, (gh, ga, minuti) in enumerate(partite):
        fid = base_fid + i
        ev = [_ev(fid * 10 + j, fid, lid, 1 if j < gh else 2, mi) for j, mi in enumerate(minuti)]
        seq, motivo = G.sequenza_partita(_match(fid, lid, gh, ga), ev)
        assert motivo == "ok"
        G.aggiungi_partita(st, seq)
    return st


def test_assemblaggio_shrinkage_formato_e_lookup():
    a = _stato_con(39, [(1, 0, [10])] * 4, 100)
    b = _stato_con(135, [(0, 1, [70])] * 4, 200)
    atl = G.assembla({"39": a, "135": b}, generated_at="2026-09-24T02:00:00+00:00",
                     watermark=77, min_fixtures_league=1)
    cg = atl["global"]["5-10"]["0"]
    assert cg["n"] == 40 and cg["p_goal_next_3min"] == round(12 / 40, 5)
    cl = atl["by_league"]["39"]["grid"]["5-10"]["0"]
    atteso = (12 + G.K_LEAGUE * (12 / 40)) / (20 + G.K_LEAGUE)
    assert cl["n"] == 20 and cl["p_goal_next_3min"] == round(atteso, 5)
    assert atl["meta"]["generated_at"] == "2026-09-24T02:00:00+00:00"
    assert atl["meta"]["n_fixtures_used"] == 8 and atl["meta"]["watermark_event_id"] == 77
    assert atl["meta"]["per_league"]["39"]["n_fixtures"] == 4
    assert atl["h2h_hint"]["1-2"]["n_meetings"] == 8              # coppia in due leghe: somma
    # il formato e' quello che il lookup dei consumatori legge
    p, src = HA.hazard_lookup(atl, 7, 0, 39)
    assert src == "league" and p == cl["p_goal_next_3min"]
    p, src = HA.hazard_lookup(atl, 7, 0, 999)
    assert src == "global"
    # eta' dichiarata dal meta prodotto
    assert HA.etichetta_atlante(atl).startswith("atlante del 24/09, 8 partite")


def test_lega_sotto_soglia_entra_con_griglia_e_confidenza_dichiarata():
    """25/09 (ordine dell'utente: TUTTE le leghe con dati): prima una lega
    sotto la soglia restava fuori da by_league; ora entra, shrinkata verso il
    globale, e dichiara di non essere affidabile (confidenza bassa)."""
    a = _stato_con(39, [(1, 0, [10])] * 3, 100)
    atl = G.assembla({"39": a}, generated_at="2026-09-24T02:00:00+00:00", min_fixtures_league=300)
    assert "39" in atl["by_league"]
    assert atl["meta"]["per_league"]["39"]["coperta"] is True
    assert atl["meta"]["per_league"]["39"]["affidabile"] is False
    assert atl["by_league"]["39"]["meta"]["confidenza"] == "bassa"


# --------------------------------------------------- 3) incrementale
def _db_base() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "matches": [_match(1, 39, 1, 0), _match(2, 39, 0, 0), _match(3, 71, 2, 0, home=5, away=6)],
        "match_events": [
            _ev(101, 1, 39, 1, 10),
            _ev(102, 2, 39, 1, 50, detail="Yellow Card", etype="Card"),
            _ev(103, 3, 71, 5, 5), _ev(104, 3, 71, 5, 80),
        ],
    }


def test_incrementale_filigrana_leghe_nuove_e_idempotenza():
    db = _db_base()
    L = LettoreFinto(db)
    stati: Dict[str, Any] = {}
    wm, conti, toccate = G.incrementale(L, stati, 100, {}, "2026-09-24T02:00:00+00:00", lotto=2)
    assert wm == 104 and toccate == ["39", "71"]
    assert conti["aggiunte"] == 3                     # anche lo 0-0 (ha eventi, non gol)
    assert stati["71"]["n_fixtures"] == 1 and stati["39"]["n_fixtures"] == 2
    # nessun evento nuovo: niente cambia, filigrana ferma, atlante IDENTICO
    prima = json.dumps(G.assembla(stati, generated_at="g", watermark=wm, min_fixtures_league=1),
                       sort_keys=True)
    wm2, conti2, t2 = G.incrementale(L, stati, wm, {}, "x")
    assert wm2 == 104 and t2 == [] and conti2["aggiunte"] == 0
    dopo = json.dumps(G.assembla(stati, generated_at="g", watermark=wm2, min_fixtures_league=1),
                      sort_keys=True)
    assert dopo == prima
    # arriva un evento TARDIVO della partita 1 (cartellino): la partita si
    # rilegge ma NON si conta due volte
    db["match_events"].append(_ev(105, 1, 39, 2, 60, detail="Yellow Card", etype="Card"))
    wm3, conti3, t3 = G.incrementale(L, stati, wm2, {}, "x")
    assert wm3 == 105 and conti3["gia_contate"] == 1 and conti3["aggiunte"] == 0
    assert stati["39"]["n_fixtures"] == 2
    ancora = json.dumps(G.assembla(stati, generated_at="g", watermark=wm2, min_fixtures_league=1),
                        sort_keys=True)
    assert ancora == prima                     # solo la filigrana e' andata avanti


def test_incrementale_senza_filigrana_si_rifiuta(monkeypatch):
    """Senza filigrana l'incrementale leggerebbe tutti i 10 milioni di eventi:
    la CLI si ferma e chiede il bootstrap."""
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "x")
    with pytest.raises(SystemExit) as ex:
        G.main(["--incrementale"])
    assert "filigrana assente" in str(ex.value)


def test_stato_senza_lista_dei_contati_si_ferma():
    """Fail-closed: uno stato letto dal DB senza la lista dei fixture_id
    contati (colonna non caricata) non deve mai contare di nuovo."""
    L = LettoreFinto(_db_base())
    st = G.stato_lega_vuoto(39)
    st["fixtures"] = None
    with pytest.raises(RuntimeError):
        G.incrementale(L, {"39": st}, 100, {}, "x")


def test_bootstrap_salta_la_stagione_senza_eventi():
    db = {"matches": [_match(i, 39, 1, 0, season=2026) for i in range(1, 11)]
          + [_match(i, 39, 1, 0, season=2025) for i in range(11, 16)],
          "match_events": [_ev(1000 + i, i, 39, 1, 30, season=2025) for i in range(11, 16)]
          + [_ev(2000, 1, 39, 1, 30, season=2026)]}          # 2026: eventi su 1 partita su 10
    stati: Dict[str, Any] = {}
    G.bootstrap(LettoreFinto(db), stati, [39], [2025, 2026], {}, "x")
    assert stati["39"]["n_fixtures"] == 5                    # solo la 2025
    assert stati["39"]["stagioni_scartate"] == {"2026": 0.1}
    assert stati["39"]["n_discarded"]["stagione_senza_eventi"] == 1


# --------------------------------------------------- 4) sync dal DB
def _atlante_valido(gen: str, n: int = 100) -> Dict[str, Any]:
    return {"meta": {"generated_at": gen, "n_fixtures_used": n},
            "global": {"65-70": {"2": {"p_goal_next_3min": 0.1, "n": 10}}},
            "by_league": {"39": {"meta": {}, "grid": {}}}, "by_team": {}, "h2h_hint": {}}


def _get_finto(versioni: List[Dict[str, Any]], errore: bool = False):
    chiamate: List[Dict[str, str]] = []

    def get(url, key, table, params, timeout=30.0):
        chiamate.append(dict(params))
        if errore:
            raise OSError("521")
        assert table == "hazard_atlas"
        if "id" in params:
            vid = int(params["id"].split(".")[1])
            return [{"payload": v["payload"]} for v in versioni if v["id"] == vid]
        ult = sorted(versioni, key=lambda v: v["generated_at"], reverse=True)[:1]
        return [{"id": v["id"], "generated_at": v["generated_at"]} for v in ult]
    get.chiamate = chiamate
    return get


@pytest.fixture()
def cartella(tmp_path, monkeypatch):
    live = tmp_path / "hazard_atlas_live.json"
    v2 = tmp_path / "hazard_atlas_v2.json"
    monkeypatch.setattr(HA, "ATLAS_LIVE_PATH", str(live))
    monkeypatch.setattr(HA, "ATLAS_V2_PATH", str(v2))
    monkeypatch.setattr(HA, "MTIME_CHECK_S", 0.0)
    HA.reset_atlante_condiviso()
    with open(v2, "w", encoding="utf-8") as fh:
        json.dump(_atlante_valido("2026-07-15T14:13:40+00:00", 54009), fh)
    yield live, v2
    HA.reset_atlante_condiviso()


def test_sync_scarica_solo_se_piu_nuovo_e_i_consumatori_ricaricano(cartella):
    live, v2 = cartella
    assert HA.atlante_condiviso()["meta"]["n_fixtures_used"] == 54009     # il v2 committato
    get = _get_finto([{"id": 1, "generated_at": "2026-09-24T02:10:00+00:00",
                       "payload": _atlante_valido("2026-09-24T02:10:00+00:00", 61000)}])
    r = SY.sincronizza(url="http://x", key="k", path=str(live), get=get)
    assert r["esito"] == "aggiornato" and os.path.exists(live)
    assert HA.atlante_condiviso()["meta"]["n_fixtures_used"] == 61000     # ricaricato
    assert not [p for p in os.listdir(os.path.dirname(live)) if ".tmp" in p]
    # stessa versione: una sola GET leggera, nessun download
    get2 = _get_finto([{"id": 1, "generated_at": "2026-09-24T02:10:00+00:00",
                        "payload": _atlante_valido("2026-09-24T02:10:00+00:00", 61000)}])
    r2 = SY.sincronizza(url="http://x", key="k", path=str(live), get=get2)
    assert r2["esito"] == "gia_aggiornato" and len(get2.chiamate) == 1


def test_sync_non_tocca_il_file_su_payload_rotto_o_errore(cartella):
    live, v2 = cartella
    buono = _atlante_valido("2026-09-23T02:00:00+00:00", 60000)
    with open(live, "w", encoding="utf-8") as fh:
        json.dump(buono, fh)
    prima = open(live, encoding="utf-8").read()
    rotto = {"meta": {"generated_at": "2026-09-24T02:00:00+00:00"}, "global": {}, "by_league": {}}
    r = SY.sincronizza(url="http://x", key="k", path=str(live),
                       get=_get_finto([{"id": 2, "generated_at": "2026-09-24T02:00:00+00:00",
                                        "payload": rotto}]))
    assert r["esito"] == "payload_non_valido"
    r = SY.sincronizza(url="http://x", key="k", path=str(live), get=_get_finto([], errore=True))
    assert r["esito"] == "errore"
    assert open(live, encoding="utf-8").read() == prima


def test_sync_spento_di_default(monkeypatch):
    monkeypatch.delenv("HAZARD_ATLAS_SYNC", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    assert SY.avvia_se_abilitato() is False
    assert SY.sincronizza(url="", key="")["esito"] == "config_mancante"


# --------------------------------------------------- 5) consumatori
def test_omega_advisor_segue_l_atlante_condiviso(cartella):
    from Betfair.omega import omega_advisor as A
    live, v2 = cartella
    A.reset_caches()
    try:
        assert A._h2h_atlas() == {}
        nuovo = _atlante_valido("2026-09-24T02:00:00+00:00")
        nuovo["h2h_hint"] = {"10-20": {"n_meetings": 5, "ft_scores_a_b": {"1-0": 5}}}
        with open(live, "w", encoding="utf-8") as fh:
            json.dump(nuovo, fh)
        assert A._h2h_atlas()["10-20"]["n_meetings"] == 5
        # un blocco iniettato a mano (test esistenti) resta quello
        A.reset_caches()
        A._H2H_CACHE = {"1-2": {"n_meetings": 3}}
        assert A._h2h_atlas() == {"1-2": {"n_meetings": 3}}
    finally:
        A.reset_caches()


def test_mike_dossier_legge_l_atlante_condiviso_e_avvisa_una_volta(cartella, monkeypatch, caplog):
    from Betfair.mike import dossier as D
    live, v2 = cartella
    assert D.load_atlas()["meta"]["n_fixtures_used"] == 54009
    os.remove(v2)
    HA.reset_atlante_condiviso()
    D._AVVISATO["assente"] = False
    with caplog.at_level("WARNING", logger="mike.dossier"):
        assert D.load_atlas() is None
        assert D.load_atlas() is None
    assert sum("atlante hazard non caricato" in r.message for r in caplog.records) == 1
