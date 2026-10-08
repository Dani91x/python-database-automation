"""Cantiere 14 (08/10): da dove viene il nome di un giocatore, e un reimport che lo MIGLIORA.

Caso vero 35790089: "Marcelo Tomas Barrios V" e' il nome del punteggio IPS, troncato. Qui:
  * ogni selezione porta ``name_source`` (catalogo | marketdef | ips | id) e l'evento
    ``diagnostica["nomi_fonte"]``;
  * ``_names.json`` col formato esteso (``_mercati``) e il formato piatto di sempre;
  * un reimport sostituisce un nome solo con una fonte MIGLIORE (mai il contrario), anche con
    ``--solo-nomi`` che non tocca snapshot e punteggio;
  * i nomi si leggono anche dalle tabelle ``tennis_live_*`` (formati prodotti dal codice vero
    del runner: ``_now_selections``, ``build_ladder_payload``).
Supabase FINTO = quello del test di caricamento (stessa catena di chiamate, risposte con ``.data``).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

import Betfair.stream.db as db
from Betfair.stream.tennis_live import tennis_runner as TR
from Betfair.stream.tennis_replay import caricamento as car
from Betfair.stream.tennis_replay import convertitore as cv
from Betfair.stream.tennis_replay import importa as imp
from Betfair.stream.tennis_replay.tests import dati_tennis as dt
from Betfair.stream.tennis_replay.tests.test_caricamento_importa_2026_10_07 import FintoSupabase

EV = "35999999"


def _score(home: str, away: str) -> Dict[str, Any]:
    return {"t": 1783427297.0, "score": {"eventTypeId": 2, "eventId": 35999999, "score": {
        "home": {"name": home, "score": "15", "games": "1", "sets": "0", "gameSequence": [], "isServing": True, "serviceBreaks": 0},
        "away": {"name": away, "score": "0", "games": "0", "sets": "0", "gameSequence": [], "isServing": False, "serviceBreaks": 0}},
        "currentSet": 1, "currentGame": 2}}


def _raw_con(righe: List[str], runner_names: Dict[int, str] | None = None, event_name: str | None = None) -> List[str]:
    """Le righe del raw con ``name`` sui runner e/o ``eventName`` nella marketDefinition (campi dei
    file storici Betfair, accettati da betfairlightweight: ``MarketDefinitionRunner.name`` e
    ``MarketDefinition.eventName``, "historic data only")."""
    out = []
    for r in righe:
        m = json.loads(r)
        for c in m["mc"]:
            md = c.get("marketDefinition")
            if not md:
                continue
            if event_name:
                md["eventName"] = event_name
            for rr in md["runners"]:
                if runner_names and rr["id"] in runner_names:
                    rr["name"] = runner_names[rr["id"]]
        out.append(json.dumps(m, separators=(",", ":")))
    return out


def _conv(raw_a, *, score=None, nomi=None, meta=None, extra=()):
    return cv.converti_evento([raw_a, *extra], [[json.dumps(score)]] if score else [],
                              event_id=EV, nomi=nomi, meta=meta)


def _sel(rt, market_id):
    return {s["selection_id"]: s for m in rt.mercati if m["market_id"] == market_id for s in m["selections"]}


@pytest.fixture()
def p():
    return dt.partita_costruita()


# ===========================================================================
# 1) la fonte di ogni nome
# ===========================================================================
def test_fonte_catalogo_vince_su_tutto(p):
    rt = _conv(_raw_con(p["a"], {101: "Dalla MarketDef"}), score=_score("Uno Ips", "Due Ips"),
               nomi={"*": {"101": "Uno Catalogo", "202": "Due Catalogo"}})
    s = _sel(rt, dt.MO)
    assert (s[101]["name"], s[101]["name_source"]) == ("Uno Catalogo", "catalogo")
    assert (s[202]["name"], s[202]["name_source"]) == ("Due Catalogo", "catalogo")
    assert rt.diagnostica["nomi_fonte"] == {"player1_name": "catalogo", "player2_name": "catalogo"}


def test_fonte_marketdef_poi_ips_poi_id(p):
    # solo il runner 101 ha il nome nella marketDefinition: 202 ripiega sull'IPS; i mercati senza nome restano #id
    rt = _conv(_raw_con(p["a"], {101: "Dalla MarketDef"}), score=_score("Uno Ips", "Due Ips"), extra=[p["b"]])
    s = _sel(rt, dt.MO)
    assert (s[101]["name"], s[101]["name_source"]) == ("Dalla MarketDef", "marketdef")
    assert (s[202]["name"], s[202]["name_source"]) == ("Due Ips", "ips")
    assert rt.diagnostica["nomi_fonte"] == {"player1_name": "marketdef", "player2_name": "ips"}
    for sel in _sel(rt, dt.SB).values():
        assert sel["name"].startswith("#") and sel["name_source"] == "id"


def test_caso_35790089_solo_nome_ips_e_dichiarato_ips(p):
    """Senza catalogo ne' _names.json il nome e' quello dell'IPS e DEVE dirsi IPS (la pagina lo segnala)."""
    rt = _conv(p["a"], score=_score("Marcelo Tomas Barrios V", "Ilia Simakin"))
    assert rt.evento["player1_name"] == "Marcelo Tomas Barrios V"
    assert rt.diagnostica["nomi_fonte"] == {"player1_name": "ips", "player2_name": "ips"}
    assert {x["name_source"] for x in _sel(rt, dt.MO).values()} == {"ips"}


def test_nome_evento_dei_file_storici_e_fonte_evento(p):
    rt = _conv(_raw_con(p["a"], None, event_name="Barrios Vera v Simakin"))
    assert (rt.evento["player1_name"], rt.evento["player2_name"]) == ("Barrios Vera", "Simakin")
    assert rt.diagnostica["nomi_fonte"] == {"player1_name": "evento", "player2_name": "evento"}


def test_anagrafica_del_chiamante_vale_catalogo(p):
    rt = _conv(p["a"], score=_score("Uno Ips", "Due Ips"),
               meta={"player1_name": "Uno Dal DB", "player2_name": "Due Dal DB", "competition_name": "ATP"})
    assert (rt.evento["player1_name"], rt.diagnostica["nomi_fonte"]["player1_name"]) == ("Uno Dal DB", "catalogo")
    assert rt.evento["competition_name"] == "ATP"
    # un solo giocatore dato dal chiamante: l'altro conserva la sua fonte
    rt2 = _conv(p["a"], score=_score("Uno Ips", "Due Ips"), meta={"player1_name": "Uno Dal DB"})
    assert rt2.diagnostica["nomi_fonte"] == {"player1_name": "catalogo", "player2_name": "ips"}


def test_nessun_nome_nessuna_fonte_dichiarata(p):
    rt = _conv(p["a"])
    assert (rt.evento["player1_name"], rt.evento["player2_name"]) == ("", "")
    assert rt.diagnostica["nomi_fonte"] == {}


def test_la_chiave_per_mercato_vince_su_quella_per_evento(p):
    rt = _conv(p["a"], nomi={"*": {"101": "Dal Piatto"}, dt.MO: {"101": "Dal Mercato"}})
    assert _sel(rt, dt.MO)[101]["name"] == "Dal Mercato"


def test_il_resto_delle_selezioni_e_invariato(p):
    """name_source e' l'UNICA chiave in piu': id, ordine, stato ed esiti sono quelli di prima."""
    rt = _conv(p["a"], score=_score("U", "D"))
    for m in rt.mercati:
        for s in m["selections"]:
            assert set(s) == {"selection_id", "name", "name_source", "sort_priority", "status"}
    assert [s["status"] for s in rt.mercati[0]["selections"]] == ["LOSER", "WINNER"]


# ===========================================================================
# 2) _names.json: formato piatto + _mercati
# ===========================================================================
def test_nomi_da_cache_formato_esteso_e_piatto(tmp_path):
    (tmp_path / "_names.json").write_text(json.dumps({
        EV: {"101": "Uno", "202": "Due"},
        "_mercati": {EV: {dt.MO: {"101": "Uno", "202": "Due"}, dt.SB: {"401": "2 - 0"}}, "altro": {"1.9": {"1": "X"}}},
    }), encoding="utf-8")
    assert cv.nomi_da_cache(str(tmp_path), EV) == {"*": {"101": "Uno", "202": "Due"},
                                                   dt.MO: {"101": "Uno", "202": "Due"}, dt.SB: {"401": "2 - 0"}}
    assert cv.nomi_da_cache(str(tmp_path), "altro") == {"1.9": {"1": "X"}}
    assert cv.nomi_da_cache(str(tmp_path), "nessuno") == {}


def test_nomi_da_cache_non_si_fida_di_cio_che_non_e_un_nome(tmp_path):
    """Il formato annidato per evento->mercato->selezione messo al posto di quello piatto non produce nomi-spazzatura."""
    (tmp_path / "_names.json").write_text(json.dumps({EV: {dt.MO: {"101": "Uno"}, "202": "Due", "303": None, "404": ""},
                                                      "_mercati": [1, 2]}), encoding="utf-8")
    assert cv.nomi_da_cache(str(tmp_path), EV) == {"*": {"202": "Due"}}
    (tmp_path / "_names.json").write_text("[1, 2]", encoding="utf-8")
    assert cv.nomi_da_cache(str(tmp_path), EV) == {}


def test_importa_dal_file_esteso_nomi_di_tutti_i_mercati(tmp_path, p):
    dt.scrivi(tmp_path / "20260707" / EV, f"{EV}.raw.jsonl", p["a"] + p["b"])
    (tmp_path / "20260707" / "_names.json").write_text(json.dumps({"_mercati": {EV: {
        dt.MO: {"101": "Uno Completo", "202": "Due Completo"}, dt.SB: {"401": "A 2-0", "402": "A 2-1", "403": "B 2-1", "404": "B 2-0"}}}}),
        encoding="utf-8")
    rt = imp.converti_registrazione(EV, imp.trova_registrazioni([str(tmp_path)])[EV], usa_db=False)
    assert [s["name"] for s in _sel(rt, dt.SB).values()] == ["A 2-0", "A 2-1", "B 2-1", "B 2-0"]
    assert [s["name"] for s in _sel(rt, dt.MO).values()] == ["Uno Completo", "Due Completo"]
    assert (rt.evento["player1_name"], rt.diagnostica["nomi_fonte"]["player1_name"]) == ("Uno Completo", "catalogo")


# ===========================================================================
# 3) la regola del nome migliore (funzioni pure)
# ===========================================================================
def _s(sid, name, src=None, status="ACTIVE"):
    d = {"selection_id": sid, "name": name, "sort_priority": 1, "status": status}
    if src:
        d["name_source"] = src
    return d


def test_rango_selezione():
    r = cv.rango_selezione
    assert r(None) == -1
    assert r(_s(1, "#1", "id")) == r(_s(1, "")) == r(_s(1, "#9")) == 0
    assert r(_s(1, "X", "ips")) == 1 and r(_s(1, "X")) == 1           # senza fonte (righe di prima): come l'IPS
    assert r(_s(1, "X", "marketdef")) == r(_s(1, "X", "evento")) == 2
    assert r(_s(1, "X", "catalogo")) == 3
    assert r(_s(1, "X", "fonte-sconosciuta")) == 1


def test_migliora_selezioni_regole():
    ex = [_s(1, "Nome Intero", "catalogo", "ACTIVE"), _s(2, "Troncato", "ips"), _s(3, "Vecchio senza fonte")]
    nuove = [_s(1, "Troncato 1", "ips", "WINNER"), _s(2, "Intero 2", "catalogo", "LOSER"), _s(3, "#3", "id")]
    out = {s["selection_id"]: s for s in cv.migliora_selezioni(ex, nuove)}
    assert (out[1]["name"], out[1]["name_source"], out[1]["status"]) == ("Nome Intero", "catalogo", "WINNER")  # resta; esito nuovo
    assert (out[2]["name"], out[2]["name_source"]) == ("Intero 2", "catalogo")                                  # sale
    assert out[3]["name"] == "Vecchio senza fonte" and "name_source" not in out[3]                              # id non declassa
    # a parita' vince il nuovo; nessun esistente: il nuovo cosi' com'e'
    assert cv.migliora_selezioni([_s(1, "A", "ips")], [_s(1, "B", "ips")])[0]["name"] == "B"
    assert cv.migliora_selezioni(None, nuove) == nuove
    assert cv.migliora_selezioni(nuove, nuove) == nuove               # idempotente


# ===========================================================================
# 4) il reimport: sale, non scende, conteggi invariati
# ===========================================================================
@pytest.fixture()
def finto(monkeypatch) -> FintoSupabase:
    f = FintoSupabase()
    monkeypatch.setattr(db, "get_supabase_client", lambda: f)
    monkeypatch.setattr(car, "get_supabase_client", lambda: f)
    return f


@pytest.fixture()
def cartella(tmp_path, p):
    dt.scrivi(tmp_path / "20260707" / EV, f"{EV}.raw.jsonl", p["a"])
    dt.scrivi(tmp_path / "setbetting_20260707" / EV, f"{EV}.raw.jsonl", p["b"])
    (tmp_path / "20260707" / EV / f"{EV}.score.jsonl").write_text(
        json.dumps(_score("Uno Troncato", "Due Troncato")) + "\n", encoding="utf-8")
    return tmp_path


def _rt(cartella, usa_nomi: bool):
    f = cartella / "20260707" / "_names.json"
    if usa_nomi:
        f.write_text(json.dumps({EV: {"101": "Uno Completo", "202": "Due Completo"}}), encoding="utf-8")
    elif f.exists():
        f.unlink()
    return imp.converti_registrazione(EV, imp.trova_registrazioni([str(cartella)])[EV], usa_db=False)


def _stato(finto):
    ev = finto.tabelle[car.T_EVENTI][0]
    mo = next(m for m in finto.tabelle[car.T_MERCATI] if m["market_type"] == "MATCH_ODDS")
    return ev["player1_name"], ev["player2_name"], [s["name"] for s in mo["selections"]], ev["diagnostica"]["nomi_fonte"]


def test_il_nome_sale_con_una_fonte_migliore_e_non_ridiscende(finto, cartella):
    senza, con = _rt(cartella, False), _rt(cartella, True)
    car.carica_replay(senza)
    assert _stato(finto)[:3] == ("Uno Troncato", "Due Troncato", ["Uno Troncato", "Due Troncato"])
    assert _stato(finto)[3] == {"player1_name": "ips", "player2_name": "ips"}
    car.carica_replay(con)
    assert _stato(finto)[:3] == ("Uno Completo", "Due Completo", ["Uno Completo", "Due Completo"])
    assert _stato(finto)[3] == {"player1_name": "catalogo", "player2_name": "catalogo"}
    car.carica_replay(senza)                                            # un PC senza _names.json
    assert _stato(finto)[:3] == ("Uno Completo", "Due Completo", ["Uno Completo", "Due Completo"])
    assert _stato(finto)[3] == {"player1_name": "catalogo", "player2_name": "catalogo"}


def test_conteggi_identici_con_e_senza_nomi_e_a_ogni_giro(finto, cartella):
    """Reimport di una cartella con ``_names.json`` e di una senza: eventi/mercati/snapshot/punteggi invariati."""
    visti = set()
    for usa in (False, True, False, True, True):
        rt = _rt(cartella, usa)
        car.carica_replay(rt)
        visti.add(tuple(len(finto.tabelle[t]) for t in (car.T_EVENTI, car.T_MERCATI, car.T_SNAPSHOT, car.T_PUNTEGGIO)))
        ev = finto.tabelle[car.T_EVENTI][0]
        assert (ev["n_markets"], ev["n_snapshots"], ev["n_score"]) == (3, 9, 1)
    assert visti == {(1, 3, 9, 1)}


def test_righe_di_prima_senza_fonte_salgono_con_il_catalogo(finto, cartella):
    """Una partita caricata PRIMA del cantiere (nomi senza name_source, diagnostica senza nomi_fonte)."""
    car.carica_replay(_rt(cartella, False))
    for m in finto.tabelle[car.T_MERCATI]:
        for s in m["selections"]:
            s.pop("name_source")
    finto.tabelle[car.T_EVENTI][0]["diagnostica"].pop("nomi_fonte")
    car.carica_replay(_rt(cartella, False))                             # stessa fonte IPS: nessun cambio
    assert _stato(finto)[:3] == ("Uno Troncato", "Due Troncato", ["Uno Troncato", "Due Troncato"])
    car.carica_replay(_rt(cartella, True))                              # catalogo: sale
    assert _stato(finto)[:3] == ("Uno Completo", "Due Completo", ["Uno Completo", "Due Completo"])


def test_aggiorna_nomi_non_tocca_snapshot_punteggio_e_conteggi(finto, cartella):
    car.carica_replay(_rt(cartella, False))
    id_snap = [r["id"] for r in finto.tabelle[car.T_SNAPSHOT]]
    id_punt = [r["id"] for r in finto.tabelle[car.T_PUNTEGGIO]]
    conteggi = {k: finto.tabelle[car.T_EVENTI][0][k] for k in ("n_markets", "n_snapshots", "n_score", "ts_min", "ts_max", "raw_files")}
    n_chiamate = len(finto.chiamate)
    esito = car.aggiorna_nomi(_rt(cartella, True))
    nuove = finto.chiamate[n_chiamate:]
    assert esito["aggiornato"] is True and esito["mercati_aggiornati"] == 3
    assert not [c for c in nuove if c[0] in (car.T_SNAPSHOT, car.T_PUNTEGGIO)]          # nemmeno una chiamata
    assert not [c for c in nuove if c[1] in ("insert", "delete", "upsert")]              # solo select e update
    assert [r["id"] for r in finto.tabelle[car.T_SNAPSHOT]] == id_snap
    assert [r["id"] for r in finto.tabelle[car.T_PUNTEGGIO]] == id_punt
    assert {k: finto.tabelle[car.T_EVENTI][0][k] for k in conteggi} == conteggi
    assert _stato(finto)[:3] == ("Uno Completo", "Due Completo", ["Uno Completo", "Due Completo"])
    assert finto.tabelle[car.T_EVENTI][0]["diagnostica"]["righe_raw"] > 0               # il resto della diagnostica resta


def test_aggiorna_nomi_non_declassa_e_non_crea(finto, cartella):
    # partita non caricata: non fa nulla, non crea nulla
    esito = car.aggiorna_nomi(_rt(cartella, True))
    assert esito["aggiornato"] is False and finto.tabelle.get(car.T_EVENTI, []) == []
    assert [c for c in finto.chiamate if c[1] != "select"] == []
    # caricata col catalogo: un aggiornamento da fonte peggiore non cambia i nomi
    car.carica_replay(_rt(cartella, True))
    car.aggiorna_nomi(_rt(cartella, False))
    assert _stato(finto)[:3] == ("Uno Completo", "Due Completo", ["Uno Completo", "Due Completo"])
    # un mercato non ancora nel DB non viene creato dall'aggiornamento
    finto.tabelle[car.T_MERCATI][:] = [m for m in finto.tabelle[car.T_MERCATI] if m["market_type"] == "MATCH_ODDS"]
    esito = car.aggiorna_nomi(_rt(cartella, True))
    assert esito["mercati_aggiornati"] == 1 and len(finto.tabelle[car.T_MERCATI]) == 1


def test_main_solo_nomi(finto, cartella, monkeypatch, capsys):
    monkeypatch.setattr(imp, "anagrafica_dal_db", lambda ev: ({}, {}, {}))
    (cartella / "20260707" / "_names.json").unlink(missing_ok=True)
    assert imp.main([str(cartella)]) == 0
    capsys.readouterr()
    id_snap = [r["id"] for r in finto.tabelle[car.T_SNAPSHOT]]
    (cartella / "20260707" / "_names.json").write_text(json.dumps({EV: {"101": "Uno Completo", "202": "Due Completo"}}), encoding="utf-8")
    n = len(finto.chiamate)
    assert imp.main([str(cartella), "--solo-nomi"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]["aggiornato"] is True and out[0]["giocatori"] == {"player1_name": "Uno Completo", "player2_name": "Due Completo"}
    assert not [c for c in finto.chiamate[n:] if c[0] in (car.T_SNAPSHOT, car.T_PUNTEGGIO)]
    assert [r["id"] for r in finto.tabelle[car.T_SNAPSHOT]] == id_snap
    assert _stato(finto)[:2] == ("Uno Completo", "Due Completo")


def test_main_solo_nomi_e_prova_si_escludono(cartella, capsys):
    with pytest.raises(SystemExit) as e:
        imp.main([str(cartella), "--solo-nomi", "--prova"])
    assert e.value.code == 2


# ===========================================================================
# 5) i nomi dalle tabelle tennis_live_* (formati prodotti dal codice vero del runner)
# ===========================================================================
def _book_vero() -> Dict[str, Any]:
    """Un book serializzato (``serialize_book``: ``runners`` con ``b``/``l``/``ltp``/``tv``/``trd``)."""
    return {"market_id": dt.MO, "status": "OPEN", "inplay": True, "pt": 1783427296000, "runners": {
        "101": {"b": [[1.2, 467.98]], "l": [[1.21, 46.97]], "ltp": 1.22, "tv": 471.56, "trd": [[1.22, 12.81]]},
        "202": {"b": [[5.6, 10.17]], "l": [[6.0, 88.81]], "ltp": 6.0, "tv": 132.39, "trd": [[6.0, 4.47]]}}}


def _riga_now(nomi: Dict[str, str]) -> Dict[str, Any]:
    state = {"markets": [{"market_id": dt.MO, "market_type": "MATCH_ODDS", "market_name": "Match Odds", "status": "OPEN",
                          "selections": TR._now_selections(_book_vero(), nomi)}], "order_mode": "paper", "updated_ms": 1}
    return {"event_id": EV, "state": state}


def _riga_ladder(nomi: Dict[str, str]) -> Dict[str, Any]:
    return {"event_id": EV, "market_id": dt.MO, "ladder": TR.build_ladder_payload(_book_vero(), nomi)}


def _db_finto(monkeypatch, f: FintoSupabase) -> None:
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: f)


def test_nomi_dalla_tabella_now_quando_il_match_odds_non_e_in_tennis_markets(monkeypatch):
    f = FintoSupabase()
    f.tabelle["tennis_live_now"] = [_riga_now({"101": "Uno Dal Runner", "202": "Due Dal Runner"})]
    _db_finto(monkeypatch, f)
    meta, nomi, nomi_mercato = imp.anagrafica_dal_db(EV)
    assert nomi == {dt.MO: {"101": "Uno Dal Runner", "202": "Due Dal Runner"}}
    assert {t for t, _m in f.chiamate} == {"tennis_live_follow", "tennis_markets", "tennis_live_now", "tennis_live_ladder"}
    assert all(m == "select" for _t, m in f.chiamate)                 # SOLA LETTURA


def test_nomi_dalla_tabella_ladder_se_manca_now(monkeypatch):
    f = FintoSupabase()
    f.tabelle["tennis_live_ladder"] = [_riga_ladder({"101": "Uno Dalla Ladder", "202": "Due Dalla Ladder"})]
    _db_finto(monkeypatch, f)
    assert imp.anagrafica_dal_db(EV)[1] == {dt.MO: {"101": "Uno Dalla Ladder", "202": "Due Dalla Ladder"}}


def test_nomi_nulli_o_segnaposto_non_sono_nomi(monkeypatch):
    f = FintoSupabase()
    f.tabelle["tennis_live_now"] = [_riga_now({"101": "Vero"})]        # il 202 non ha nome: `name: None` come nel runner
    f.tabelle["tennis_live_ladder"] = [_riga_ladder({"101": "?", "202": ""})]
    _db_finto(monkeypatch, f)
    assert imp.anagrafica_dal_db(EV)[1] == {dt.MO: {"101": "Vero"}}
    # il segnaposto "?" e il nome vuoto da soli (nessuna altra fonte) non producono nomi
    f2 = FintoSupabase()
    f2.tabelle["tennis_live_ladder"] = [_riga_ladder({"101": "?", "202": ""})]
    _db_finto(monkeypatch, f2)
    assert imp.anagrafica_dal_db(EV)[1] == {}


def test_tennis_markets_vince_e_se_ha_il_match_odds_le_tabelle_live_non_si_leggono(monkeypatch):
    f = FintoSupabase()
    f.tabelle["tennis_markets"] = [{"event_id": EV, "market_id": dt.MO, "competition_name": "X", "open_date": None,
                                    "player1": {"selection_id": 101, "name": "Uno Catalogo"},
                                    "player2": {"selection_id": 202, "name": "Due Catalogo"}, "full_odds": []}]
    f.tabelle["tennis_live_now"] = [_riga_now({"101": "Uno Dal Runner", "202": "Due Dal Runner"})]
    _db_finto(monkeypatch, f)
    assert imp.anagrafica_dal_db(EV)[1] == {dt.MO: {"101": "Uno Catalogo", "202": "Due Catalogo"}}
    assert {t for t, _m in f.chiamate} == {"tennis_live_follow", "tennis_markets"}   # come prima del cantiere


def test_tennis_markets_senza_match_odds_completa_dalle_tabelle_live_senza_sovrascrivere(monkeypatch):
    f = FintoSupabase()
    f.tabelle["tennis_markets"] = [{"event_id": EV, "market_id": dt.MO, "competition_name": "X", "open_date": None,
                                    "player1": {"selection_id": 101, "name": "Uno Catalogo"}, "player2": {}, "full_odds": []}]
    f.tabelle["tennis_live_now"] = [_riga_now({"101": "Uno Dal Runner", "202": "Due Dal Runner"})]
    _db_finto(monkeypatch, f)
    # il MO e' in `nomi` (un solo giocatore): niente tabelle live, come prima
    assert imp.anagrafica_dal_db(EV)[1] == {dt.MO: {"101": "Uno Catalogo"}}


def test_errore_di_lettura_delle_tabelle_live_non_blocca_l_import(monkeypatch):
    class Rotto(FintoSupabase):
        def table(self, nome):
            if nome.startswith("tennis_live_") and nome != "tennis_live_follow":
                raise RuntimeError("relation does not exist")
            return super().table(nome)

    _db_finto(monkeypatch, Rotto())
    assert imp.anagrafica_dal_db(EV) == ({}, {}, {})
