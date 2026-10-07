"""Caricamento e import del Replay Tennis: idempotenza, mercati per cartella, isolamento dal calcio.

Client Supabase FINTO in memoria con la stessa catena di chiamate di supabase-py
usata dal codice (``table().select().eq().limit().execute()``, ``upsert(rows,
on_conflict=...)``, ``insert``, ``update().eq()``, ``delete().in_()``) e
risposte con ``.data`` come le vere. Le chiavi uniche dell'upsert sono quelle
della migrazione ``replay_tennis_2026-10-07.sql``.
"""
from __future__ import annotations

import itertools
import json
from typing import Any, Dict, List, Optional

import pytest

import Betfair.stream.db as db
from Betfair.stream.tennis_replay import caricamento as car
from Betfair.stream.tennis_replay import convertitore as cv
from Betfair.stream.tennis_replay import importa as imp
from Betfair.stream.tennis_replay.tests import dati_tennis as dt


class _Resp:
    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.data = data


class _Q:
    def __init__(self, fake: "FintoSupabase", nome: str) -> None:
        self.f, self.nome = fake, nome
        self.modo: Optional[str] = None
        self.filtri: Dict[str, Any] = {}
        self.lim: Optional[int] = None
        self.inn: Optional[tuple] = None
        self.dati: Any = None
        self.conflitto: Optional[str] = None

    def select(self, *c: str) -> "_Q":
        # come PostgREST: tornano SOLO le colonne chieste ("a,b" in una stringa)
        self.modo = "select"
        self.colonne = [x.strip() for x in ",".join(c).split(",") if x.strip()]
        return self

    def delete(self) -> "_Q":
        self.modo = "delete"; return self

    def insert(self, righe: Any) -> "_Q":
        self.modo, self.dati = "insert", righe; return self

    def upsert(self, righe: Any, on_conflict: str = "") -> "_Q":
        self.modo, self.dati, self.conflitto = "upsert", righe, on_conflict; return self

    def update(self, campi: Dict[str, Any]) -> "_Q":
        self.modo, self.dati = "update", campi; return self

    def eq(self, c: str, v: Any) -> "_Q":
        self.filtri[c] = v; return self

    def limit(self, n: int) -> "_Q":
        self.lim = n; return self

    def in_(self, c: str, vs: List[Any]) -> "_Q":
        self.inn = (c, set(vs)); return self

    def _ok(self, r: Dict[str, Any]) -> bool:
        return all(r.get(k) == v for k, v in self.filtri.items())

    def execute(self) -> _Resp:
        t = self.f.tabelle.setdefault(self.nome, [])
        self.f.chiamate.append((self.nome, self.modo))
        if self.modo == "select":
            rows = [{k: r.get(k) for k in self.colonne} if self.colonne != ["*"] else dict(r)
                    for r in t if self._ok(r)]
            return _Resp(rows[: self.lim] if self.lim else rows)
        if self.modo == "insert":
            for r in (self.dati if isinstance(self.dati, list) else [self.dati]):
                t.append(dict(r, id=next(self.f.ids)))
            return _Resp([])
        if self.modo == "upsert":
            chiavi = [k.strip() for k in self.conflitto.split(",")]
            for r in (self.dati if isinstance(self.dati, list) else [self.dati]):
                esistente = next((x for x in t if all(x.get(k) == r.get(k) for k in chiavi)), None)
                if esistente is None:
                    t.append(dict(r, id=next(self.f.ids)))
                else:
                    esistente.update(r)
            return _Resp([])
        if self.modo == "update":
            for r in t:
                if self._ok(r):
                    r.update(self.dati)
            return _Resp([])
        if self.modo == "delete":
            c, vs = self.inn
            t[:] = [r for r in t if r.get(c) not in vs]
            return _Resp([])
        raise AssertionError(self.modo)


class FintoSupabase:
    def __init__(self) -> None:
        self.tabelle: Dict[str, List[Dict[str, Any]]] = {}
        self.chiamate: List[tuple] = []
        self.ids = itertools.count(1)

    def table(self, nome: str) -> _Q:
        return _Q(self, nome)


@pytest.fixture()
def finto(monkeypatch) -> FintoSupabase:
    f = FintoSupabase()
    monkeypatch.setattr(db, "get_supabase_client", lambda: f)
    monkeypatch.setattr(car, "get_supabase_client", lambda: f)
    return f


@pytest.fixture()
def cartelle(tmp_path):
    p = dt.partita_costruita()
    dt.scrivi(tmp_path / "20260707" / "35999999", "35999999.raw.jsonl", p["a"])
    dt.scrivi(tmp_path / "setbetting_20260707" / "35999999", "35999999.raw.jsonl", p["b"])
    score = {"t": 1783427297.0, "score": {"eventTypeId": 2, "eventId": 35999999, "score": {
        "home": {"name": "Uno", "score": "15", "games": "1", "sets": "0", "gameSequence": [], "isServing": True, "serviceBreaks": 0},
        "away": {"name": "Due", "score": "0", "games": "0", "sets": "0", "gameSequence": [], "isServing": False, "serviceBreaks": 0}},
        "currentSet": 1, "currentGame": 2}}
    (tmp_path / "20260707" / "35999999" / "35999999.score.jsonl").write_text(json.dumps(score) + "\n", encoding="utf-8")
    (tmp_path / "20260707" / "_names.json").write_text(json.dumps({"35999999": {"101": "Uno", "202": "Due"}}), encoding="utf-8")
    return tmp_path


def _conta(f: FintoSupabase, t: str, **filtri: Any) -> int:
    return sum(1 for r in f.tabelle.get(t, []) if all(r.get(k) == v for k, v in filtri.items()))


def test_trova_registrazioni_unisce_la_stessa_partita_da_due_cartelle(cartelle) -> None:
    trovate = imp.trova_registrazioni([str(cartelle)])
    assert list(trovate) == ["35999999"]
    assert len(trovate["35999999"]["raw"]) == 2 and len(trovate["35999999"]["score"]) == 1


def test_carica_due_volte_nessuna_riga_doppia(finto, cartelle) -> None:
    voce = imp.trova_registrazioni([str(cartelle)])["35999999"]
    rt = imp.converti_registrazione("35999999", voce, usa_db=False)
    car.carica_replay(rt)
    prima = {t: len(r) for t, r in finto.tabelle.items()}
    car.carica_replay(rt)
    assert {t: len(r) for t, r in finto.tabelle.items()} == prima
    assert prima == {car.T_EVENTI: 1, car.T_MERCATI: 3, car.T_SNAPSHOT: len(rt.snapshot), car.T_PUNTEGGIO: 1}
    ev = finto.tabelle[car.T_EVENTI][0]
    assert (ev["n_markets"], ev["n_snapshots"], ev["n_score"]) == (3, len(rt.snapshot), 1)
    assert (ev["player1_name"], ev["player2_name"], ev["valuta"], ev["fonte"]) == ("Uno", "Due", "GBP", "import")
    # calcio e tennis non si mischiano: nessuna tabella del calcio toccata
    assert all(t.startswith("tennis_replay_") for t, _m in finto.chiamate)


def test_cartella_per_cartella_un_mercato_non_cancella_gli_altri(finto, cartelle) -> None:
    a = cv.converti_evento([cartelle / "20260707" / "35999999" / "35999999.raw.jsonl"],
                           [cartelle / "20260707" / "35999999" / "35999999.score.jsonl"])
    b = cv.converti_evento([cartelle / "setbetting_20260707" / "35999999" / "35999999.raw.jsonl"])
    car.carica_replay(a)
    car.carica_replay(b)
    car.carica_replay(b)  # rilancio della sola cartella B
    assert _conta(finto, car.T_SNAPSHOT, market_id=dt.MO) == 5
    assert _conta(finto, car.T_SNAPSHOT, market_id=dt.TG) == 2
    assert _conta(finto, car.T_SNAPSHOT, market_id=dt.SB) == 2
    assert _conta(finto, car.T_PUNTEGGIO) == 1          # B senza sidecar non cancella il punteggio
    ev = finto.tabelle[car.T_EVENTI][0]
    assert (ev["n_markets"], ev["n_snapshots"], ev["n_score"]) == (3, 9, 1)


def test_fonte_non_valida_rifiutata(finto, cartelle) -> None:
    voce = imp.trova_registrazioni([str(cartelle)])["35999999"]
    rt = imp.converti_registrazione("35999999", voce, usa_db=False)
    with pytest.raises(ValueError):
        car.carica_replay(rt, fonte="calcio")
    assert finto.chiamate == []


def test_main_prova_non_tocca_il_db(cartelle, monkeypatch, capsys) -> None:
    def vietato():
        raise AssertionError("--prova non deve toccare il DB")

    monkeypatch.setattr(db, "get_supabase_client", vietato)
    monkeypatch.setattr(car, "get_supabase_client", vietato)
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", vietato)
    assert imp.main([str(cartelle), "--prova"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]["event_id"] == "35999999"
    assert sorted(t for t, _m, _n in out[0]["mercati"]) == ["MATCH_ODDS", "SET_BETTING", "TOTAL_GAMES"]


def test_main_scrive_e_una_partita_rotta_non_ferma_le_altre(finto, cartelle, monkeypatch, capsys) -> None:
    rotta = cartelle / "rotte" / "123"
    rotta.mkdir(parents=True)
    (rotta / "123.raw.jsonl").write_text("{non json\n", encoding="utf-8")
    monkeypatch.setattr(imp, "anagrafica_dal_db", lambda ev: ({"competition_name": "ATP Prova"}, {}, {}))
    assert imp.main([str(cartelle)]) == 2
    out = json.loads(capsys.readouterr().out)
    per = {o["event_id"]: o for o in out}
    assert "errore" in per["123"]
    assert per["35999999"]["n_markets"] == 3
    assert finto.tabelle[car.T_EVENTI][0]["competition_name"] == "ATP Prova"


def test_anagrafica_dal_db_legge_solo_tabelle_tennis(monkeypatch) -> None:
    f = FintoSupabase()
    f.tabelle["tennis_live_follow"] = [{"event_id": "35999999", "competition_name": "ATP Prova",
                                        "player1_name": "Uno", "player2_name": "Due", "open_date": None}]
    f.tabelle["tennis_markets"] = [{"event_id": "35999999", "market_id": dt.MO, "competition_name": "X",
                                    "open_date": "2026-07-07T10:30:00+00:00",
                                    "player1": {"selection_id": 101, "name": "Uno Catalogo"},
                                    "player2": {"selection_id": 202, "name": "Due Catalogo"},
                                    "full_odds": [{"market_id": dt.SB, "market": "Set Betting", "market_type": "SET_BETTING",
                                                   "runners": [{"selection": "2 - 0", "selection_id": 401},
                                                               {"selection": "?", "selection_id": 402}]}]}]
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: f)
    meta, nomi, nomi_mercato = imp.anagrafica_dal_db("35999999")
    assert meta == {"competition_name": "ATP Prova", "player1_name": "Uno", "player2_name": "Due",
                    "open_date": "2026-07-07T10:30:00+00:00"}
    assert nomi == {dt.MO: {"101": "Uno Catalogo", "202": "Due Catalogo"}, dt.SB: {"401": "2 - 0"}}
    assert nomi_mercato == {dt.SB: "Set Betting"}
    assert {t for t, m in f.chiamate} == {"tennis_live_follow", "tennis_markets"}
    assert all(m == "select" for _t, m in f.chiamate)
