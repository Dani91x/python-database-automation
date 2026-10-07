"""Convertitore del Replay Tennis (07/10/2026): raw tennis -> righe delle tabelle.

Tre confronti per ogni libro ricostruito, frame per frame:
  * con FLUMINE (``FlumineHistoricalGeneratorStream`` + ``HistoricListener``,
    il lettore storico del banco): stessa ricostruzione da un'altra strada;
  * con un ORACOLO scritto qui dalle regole dello schema ufficiale dello Stream API
    (``ESASwaggerSchema.json``: "img = replace existing prices", "0 vol is remove"),
    indipendente da betfairlightweight;
  * col SIDECAR del punteggio (set, game, punti, servizio).
Poi la partita costruita a piu' mercati (formato vero dello stream) per i
mercati che la registrazione vera non ha.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest

from Betfair.stream.curator import ladder_db_format
from Betfair.stream.recorder import serialize_book
from Betfair.stream.tennis_replay import convertitore as cv
from Betfair.stream.tennis_replay.tests import dati_tennis as dt

PROF = 10


# ---------------------------------------------------------------------------
# oracolo indipendente: le regole dello schema, a mano
# ---------------------------------------------------------------------------
class Oracolo:
    # ``tv`` mai visto = 0: e' la convenzione della cache di betfairlightweight
    # (volume scambiato iniziale nullo); ``ltp`` mai visto = None.
    def __init__(self) -> None:
        self.m: Dict[str, Dict[str, Any]] = {}

    def applica(self, msg: Dict[str, Any]) -> List[str]:
        toccati: List[str] = []
        for ch in msg.get("mc") or []:
            mid = ch["id"]
            if ch.get("img") or mid not in self.m:
                self.m[mid] = {"runners": {}, "status": None, "inplay": None, "pt": None}
            st = self.m[mid]
            md = ch.get("marketDefinition")
            if md:
                st["status"] = md.get("status")
                st["inplay"] = bool(md.get("inPlay"))
                for r in md.get("runners") or []:
                    st["runners"].setdefault(r["id"], {"atb": {}, "atl": {}, "trd": {}, "ltp": None, "tv": 0})
            for rc in ch.get("rc") or []:
                r = st["runners"].setdefault(rc["id"], {"atb": {}, "atl": {}, "trd": {}, "ltp": None, "tv": 0})
                for k in ("atb", "atl", "trd"):
                    for p, s in rc.get(k) or []:
                        if s == 0:
                            r[k].pop(p, None)
                        else:
                            r[k][p] = s
                if "ltp" in rc:
                    r["ltp"] = rc["ltp"]
                if "tv" in rc:
                    r["tv"] = rc["tv"]
            st["pt"] = msg["pt"]
            if mid not in toccati:
                toccati.append(mid)
        return toccati

    def libro(self, mid: str) -> Dict[str, Any]:
        st = self.m[mid]
        runners = {}
        for sid, r in st["runners"].items():
            e: Dict[str, Any] = {
                "b": [[float(p), float(s)] for p, s in sorted(r["atb"].items(), key=lambda x: -x[0])[:PROF]],
                "l": [[float(p), float(s)] for p, s in sorted(r["atl"].items())[:PROF]],
                "ltp": r["ltp"], "tv": r["tv"],
            }
            trd = [[float(p), float(s)] for p, s in sorted(r["trd"].items())]
            if trd:
                e["trd"] = trd
            runners[str(sid)] = e
        return {"market_id": mid, "pt": st["pt"], "status": st["status"], "inplay": st["inplay"], "runners": runners}


def _confronta_con_oracolo(righe: List[str], record: List[Dict[str, Any]]) -> int:
    orc = Oracolo()
    attesi: List[Dict[str, Any]] = []
    for riga in righe:
        msg = json.loads(riga)
        for mid in orc.applica(msg):
            attesi.append(orc.libro(mid))
    assert len(attesi) == len(record)
    for i, (a, r) in enumerate(zip(attesi, record)):
        assert r["market_id"] == a["market_id"], i
        assert r["pt"] == a["pt"], i
        assert r["status"] == a["status"], (i, r["status"], a["status"])
        assert r["inplay"] == a["inplay"], i
        for sid, e in a["runners"].items():
            got = r["runners"][sid]
            assert got["b"] == e["b"], (i, sid, "back")
            assert got["l"] == e["l"], (i, sid, "lay")
            assert got.get("trd", []) == e.get("trd", []), (i, sid, "trd")
            assert got["ltp"] == e["ltp"], (i, sid, "ltp")
            assert got["tv"] == e["tv"], (i, sid, "tv")
    return len(attesi)


# ---------------------------------------------------------------------------
# registrazione VERA
# ---------------------------------------------------------------------------
CART = dt.cartella_vera()
vera = pytest.mark.skipif(CART is None, reason="registrazione vera 35790089 assente su questo disco")


@pytest.fixture(scope="module")
def replay_vero() -> cv.ReplayTennis:
    assert CART is not None
    return cv.converti_evento([CART / f"{dt.EVENTO_VERO}.raw.jsonl"], [CART / f"{dt.EVENTO_VERO}.score.jsonl"])


@vera
def test_vera_libri_identici_all_oracolo_dello_schema() -> None:
    righe = [r for r in (CART / f"{dt.EVENTO_VERO}.raw.jsonl").read_text(encoding="utf-8").splitlines() if r.strip()]
    dec = cv.decodifica_raw(righe)
    assert dec.righe_lette == 5217 and dec.righe_scartate == 0
    assert _confronta_con_oracolo(righe, dec.record) == 5217


@vera
def test_vera_libri_identici_a_flumine() -> None:
    from flumine.streams.historicalstream import FlumineHistoricalGeneratorStream, HistoricListener

    path = str(CART / f"{dt.EVENTO_VERO}.raw.jsonl")
    righe = [r for r in open(path, encoding="utf-8") if r.strip()]
    gen = FlumineHistoricalGeneratorStream(
        file_path=path, listener=HistoricListener(max_latency=None), operation="marketSubscription", unique_id=0,
    ).get_generator()()
    nostri = cv.decodifica_raw(path).record
    k = 0
    for riga, libri in zip(righe, gen):
        ids = [c["id"] for c in json.loads(riga)["mc"]]
        for mb in libri:
            if mb.market_id in ids:
                atteso = serialize_book(mb, PROF)
                assert nostri[k] == atteso, k
                k += 1
    assert k == len(nostri) == 5217


@vera
def test_vera_catalogo_evento_e_buchi(replay_vero: cv.ReplayTennis) -> None:
    r = replay_vero
    assert r.evento["event_id"] == dt.EVENTO_VERO
    assert r.evento["player1_name"] == "Marcelo Tomas Barrios V"
    assert r.evento["player2_name"] == "Ilia Simakin"
    assert r.evento["open_date"] == "2026-07-07T10:30:00+00:00"
    assert len(r.mercati) == 1
    m = r.mercati[0]
    assert (m["market_id"], m["market_type"], m["market_name"], m["bet_delay"]) == (
        dt.MERCATO_VERO, "MATCH_ODDS", "Match Odds", 3)
    assert [(s["selection_id"], s["sort_priority"], s["status"]) for s in m["selections"]] == [
        (9633138, 1, "LOSER"), (35635727, 2, "WINNER")]
    # MATCH_ODDS senza catalogo: nomi IPS per sortPriority (p1 = home)
    assert [s["name"] for s in m["selections"]] == ["Marcelo Tomas Barrios V", "Ilia Simakin"]
    assert m["settled_ts"] == "2026-07-07T13:58:58.535000+00:00"
    assert m["n_updates"] == len(r.snapshot) == r.diagnostica["snapshot"]
    assert len(r.diagnostica["buchi"]) == 5  # i 5 buchi dichiarati della registrazione


@vera
def test_vera_snapshot_curati_vengono_dai_libri(replay_vero: cv.ReplayTennis) -> None:
    righe = (CART / f"{dt.EVENTO_VERO}.raw.jsonl").read_text(encoding="utf-8").splitlines()
    per_pt: Dict[Any, List[Dict[str, Any]]] = {}
    for rec in cv.decodifica_raw(righe).record:
        per_pt.setdefault(cv.ms_a_iso(rec["pt"]), []).append(rec)
    assert replay_vero.snapshot[0]["ts"] == "2026-07-07T12:28:16.127000+00:00"
    for s in replay_vero.snapshot:
        assert set(s) == {"event_id", "market_id", "ts", "inplay", "status", "ladder"}
        candidati = per_pt[s["ts"]]
        assert any(ladder_db_format(c["runners"]) == s["ladder"] and c["status"] == s["status"]
                   and c["inplay"] == s["inplay"] for c in candidati)
        assert "valuta" not in s["ladder"]  # GBP storiche: converte il frontend
    # l'ultimo stato registrato e' la chiusura
    assert replay_vero.snapshot[-1]["status"] == "CLOSED"


@vera
def test_vera_punteggio_come_il_sidecar(replay_vero: cv.ReplayTennis) -> None:
    grezzi = [json.loads(x) for x in (CART / f"{dt.EVENTO_VERO}.score.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(replay_vero.punteggio) == len(grezzi) == 104
    for riga, g in zip(replay_vero.punteggio, grezzi):
        h, a = g["score"]["score"]["home"], g["score"]["score"]["away"]
        s = riga["score"]
        assert riga["ts"] == cv.ms_a_iso(g["t"] * 1000.0)
        assert (s["sets"]["p1"], s["sets"]["p2"]) == (int(h["sets"]), int(a["sets"]))
        assert (s["games"]["p1"], s["games"]["p2"]) == (int(h["games"]), int(a["games"]))
        assert (s["points"]["p1"], s["points"]["p2"]) == (h["score"], a["score"])
        assert s["server"] == (1 if h["isServing"] else 2 if a["isServing"] else None)
        assert s["game_sequence"] == {"p1": h["gameSequence"], "p2": a["gameSequence"]}


@vera
def test_vera_eventi_della_barra(replay_vero: cv.ReplayTennis) -> None:
    eventi = [(p["ts"][11:19], p["event_types"]) for p in replay_vero.punteggio if p["event_types"]]
    # verificati a mano sul sidecar: 5-6 con Barrios al servizio -> Simakin breakka e
    # chiude il 2o set 7-5; nel 3o set break 2-4, 3-4, 3-5, 4-5; tie-break sul 6-6;
    # Simakin vince il tie-break (nessun break) e la partita
    assert eventi == [
        ("12:35:48", ["BREAK", "SET_END", "SET_START"]),
        ("13:13:05", ["BREAK"]),
        ("13:16:30", ["BREAK"]),
        ("13:26:32", ["BREAK"]),
        ("13:30:51", ["BREAK"]),
        ("13:44:27", ["TIEBREAK_START"]),
        ("13:58:21", ["SET_END", "MATCH_END"]),
    ]
    finale = replay_vero.punteggio[-1]["score"]
    assert finale["set_summary"] == "6-4 5-7 6-7" and finale["status"] == "Finished"


# ---------------------------------------------------------------------------
# partita COSTRUITA a piu' mercati (formato vero)
# ---------------------------------------------------------------------------
@pytest.fixture()
def costruita(tmp_path):
    p = dt.partita_costruita()
    fa = dt.scrivi(tmp_path / "match_odds" / "35999999", "35999999.raw.jsonl", p["a"])
    fb = dt.scrivi(tmp_path / "setbetting" / "35999999", "35999999.raw.jsonl", p["b"])
    return p, fa, fb


def test_costruita_libri_identici_all_oracolo(costruita) -> None:
    p, _fa, _fb = costruita
    for righe in (p["a"], p["b"]):
        assert _confronta_con_oracolo(righe, cv.decodifica_raw(righe).record) > 0


def test_costruita_tutti_i_mercati_da_due_file(costruita) -> None:
    _p, fa, fb = costruita
    nomi = {"*": {"101": "Giocatore Uno", "202": "Giocatore Due"},
            dt.SB: {"401": "2 - 0", "402": "2 - 1", "403": "1 - 2", "404": "0 - 2"}}
    r = cv.converti_evento([fa, fb], nomi=nomi, meta={"competition_name": "ATP Prova"})
    tipi = [m["market_type"] for m in r.mercati]
    assert tipi[0] == "MATCH_ODDS" and sorted(tipi) == ["MATCH_ODDS", "SET_BETTING", "TOTAL_GAMES"]
    assert [m["sort_priority"] for m in r.mercati] == [1, 2, 3]
    per = {m["market_type"]: m for m in r.mercati}
    assert per["SET_BETTING"]["market_name"] == "Set Betting"
    assert per["TOTAL_GAMES"]["market_name"] == "Totale game"
    assert [s["name"] for s in per["SET_BETTING"]["selections"]] == ["2 - 0", "2 - 1", "1 - 2", "0 - 2"]
    assert [s["name"] for s in per["TOTAL_GAMES"]["selections"]] == ["#301", "#302"]  # nessun nome: dichiarato
    mo = per["MATCH_ODDS"]
    assert [(s["name"], s["status"]) for s in mo["selections"]] == [("Giocatore Uno", "LOSER"), ("Giocatore Due", "WINNER")]
    assert mo["settled_ts"] == cv.ms_a_iso(1783427296000 + 20000)
    assert per["SET_BETTING"]["settled_ts"] is None
    assert r.evento["player1_name"] == "Giocatore Uno" and r.evento["competition_name"] == "ATP Prova"
    # snapshot per mercato: MO = immagine, delta best, sospeso, riaperto, chiuso
    # (il cambio solo di profondita' a +1800 ms NON e' conservato: regola del calcio)
    snap_mo = [s for s in r.snapshot if s["market_id"] == dt.MO]
    assert [s["status"] for s in snap_mo] == ["OPEN", "OPEN", "SUSPENDED", "OPEN", "CLOSED"]
    assert snap_mo[1]["ladder"]["101"]["back"] == [[1.19, 789.92]]       # 1.2 tolto (size 0)
    assert snap_mo[1]["ladder"]["101"]["trd"] == [[1.21, 30.0], [1.22, 12.81]]
    assert snap_mo[1]["ladder"]["101"]["ltp"] == 1.21
    snap_tg = [s for s in r.snapshot if s["market_id"] == dt.TG]
    assert snap_tg[-1]["ladder"]["301"]["back"] == [[1.88, 50.0]]
    snap_sb = [s for s in r.snapshot if s["market_id"] == dt.SB]
    assert len(snap_sb) == 2 and snap_sb[-1]["ladder"]["404"]["back"] == [[2.6, 8.0], [2.5, 5.0]]
    # ordine cronologico unico fra i due file
    assert [s["ts"] for s in r.snapshot] == sorted(s["ts"] for s in r.snapshot)
    assert {m["market_id"]: m["n_updates"] for m in r.mercati} == {dt.MO: 5, dt.SB: 2, dt.TG: 2}


def test_costruita_doppione_dello_stesso_file_entra_una_volta(costruita) -> None:
    _p, fa, _fb = costruita
    una = cv.converti_evento([fa])
    due = cv.converti_evento([fa, fa])
    assert due.snapshot == una.snapshot
    assert due.diagnostica["libri"] == una.diagnostica["libri"]  # i libri doppi non entrano


def test_righe_corrotte_e_non_mcm_contate_e_saltate() -> None:
    p = dt.partita_costruita()
    righe = ["", "{rotto", json.dumps({"op": "mcm", "clk": "x", "pt": 1, "ct": "HEARTBEAT"}),
             json.dumps({"op": "status", "statusCode": "SUCCESS"})] + p["a"]
    dec = cv.decodifica_raw(righe)
    assert dec.righe_scartate == 3 and dec.righe_lette == 3 + len(p["a"])
    assert len(dec.record) == len(cv.decodifica_raw(p["a"]).record)


def test_senza_marketdefinition_event_id_obbligatorio() -> None:
    righe = [json.dumps({"op": "mcm", "clk": "x", "pt": 1, "mc": [{"id": "1.5", "rc": [{"id": 1, "ltp": 2.0}]}]})]
    with pytest.raises(ValueError):
        cv.converti_evento([righe])
    r = cv.converti_evento([righe], event_id="77")
    assert r.evento["event_id"] == "77"


def test_raw_senza_libri_rifiutato() -> None:
    with pytest.raises(ValueError):
        cv.converti_evento([["{rotto", json.dumps({"op": "status"})]], event_id="1")


def test_nomi_da_cache(tmp_path) -> None:
    (tmp_path / "_names.json").write_text(json.dumps({"35999999": {"101": "Uno", "202": "Due"}}), encoding="utf-8")
    assert cv.nomi_da_cache(str(tmp_path), "35999999") == {"*": {"101": "Uno", "202": "Due"}}
    assert cv.nomi_da_cache(str(tmp_path), "1") == {}
    assert cv.nomi_da_cache(str(tmp_path / "manca"), "1") == {}


# ---------------------------------------------------------------------------
# eventi di gioco (funzione pura)
# ---------------------------------------------------------------------------
def _st(sets=(0, 0), games=(0, 0), server: Optional[int] = 1, tiebreak=False, seq=([], []),
        current_set: Optional[int] = 1, status: Optional[str] = None) -> Dict[str, Any]:
    return {"sets": {"p1": sets[0], "p2": sets[1]}, "games": {"p1": games[0], "p2": games[1]},
            "server": server, "tiebreak": tiebreak,
            "game_sequence": {"p1": list(seq[0]), "p2": list(seq[1])},
            "current_set": current_set, "status": status}


def test_eventi_prima_riga_nessun_evento() -> None:
    assert cv.eventi_tennis(None, _st(games=(5, 5))) == []


def test_eventi_tenuta_e_break() -> None:
    assert cv.eventi_tennis(_st(games=(2, 2), server=1), _st(games=(3, 2), server=2)) == []
    assert cv.eventi_tennis(_st(games=(2, 2), server=1), _st(games=(2, 3), server=2)) == ["BREAK"]
    assert cv.eventi_tennis(_st(games=(2, 2), server=None), _st(games=(2, 3), server=2)) == []


def test_eventi_set_chiuso_col_break_e_nuovo_set() -> None:
    prev = _st(sets=(1, 0), games=(5, 6), server=1, seq=(["6"], ["4"]), current_set=2)
    cur = _st(sets=(1, 1), games=(0, 0), server=2, seq=(["6", "5"], ["4", "7"]), current_set=3)
    assert cv.eventi_tennis(prev, cur) == ["BREAK", "SET_END", "SET_START"]


def test_eventi_tie_break_vinto_non_e_break_e_fine_partita() -> None:
    prev = _st(sets=(1, 1), games=(6, 6), server=1, tiebreak=True, seq=(["6", "5"], ["4", "7"]), current_set=3)
    cur = _st(sets=(1, 2), games=(6, 7), server=1, seq=(["6", "5"], ["4", "7"]), current_set=None, status="Finished")
    assert cv.eventi_tennis(prev, cur) == ["SET_END", "MATCH_END"]
    assert cv.eventi_tennis(_st(games=(5, 6)), _st(games=(6, 6), tiebreak=True)) == ["TIEBREAK_START"]


def test_eventi_salto_di_registrazione_nessun_break_inventato() -> None:
    assert cv.eventi_tennis(_st(games=(2, 2), server=1), _st(games=(3, 3), server=1)) == ["SALTO"]
    prev = _st(sets=(1, 0), games=(3, 4), server=1, seq=(["6"], ["4"]), current_set=2)
    cur = _st(sets=(1, 1), games=(0, 0), server=1, seq=(["6", "4"], ["4", "6"]), current_set=3)
    assert cv.eventi_tennis(prev, cur) == ["SALTO", "SET_END", "SET_START"]
    assert cv.eventi_tennis(_st(games=(3, 3)), _st(games=(2, 3))) == ["SALTO"]


def test_nome_mercato() -> None:
    assert cv.nome_mercato("MATCH_ODDS") == "Match Odds"
    assert cv.nome_mercato("SET_BETTING") == "Set Betting"
    assert cv.nome_mercato("FIRST_SET_SCORE") == "First Set Score"
    assert cv.nome_mercato(None) == "Mercato"
