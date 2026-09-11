"""Test di Betfair/safe_strategy/anomaly.py — quote incoerenti, logica pura."""
from __future__ import annotations

import pytest

from Betfair.safe_strategy.anomaly import DEFAULT_ANOMALY_PARAMS, detect

OPP_FIELDS = {"market_type", "market_name", "line", "market_id", "selection_id",
              "selection_name", "side", "price", "size_available", "p_model", "p_implied",
              "edge", "ev", "confidence", "rationale", "minute", "score"}


# ---------------------------------------------------------------- helper dati
def _sel(sid, name, back=None, lay=None, back_size=None, lay_size=None, status="ACTIVE"):
    return {"selection_id": sid, "name": name, "runner_status": status,
            "back": back, "lay": lay, "back_size": back_size, "lay_size": lay_size}


def _ou(mid, line, under, over, status="OPEN"):
    """under/over = (back, lay, back_size, lay_size)."""
    n = int(line * 10)
    return {"market_id": mid, "line": line, "status": status, "selections": [
        _sel(n + 1, f"Under {line} Goals", *under),
        _sel(n + 2, f"Over {line} Goals", *over),
    ]}


def payload_1_1_65(**over) -> dict:
    """L'esempio dell'utente: 1-1 al 65', Under 6.5 back 1.01/300, Under 7.5 back 1.10/120."""
    base = {
        "home": "Nord FC", "away": "Sud FC", "minute": 65,
        "score_home": 1, "score_away": 1,
        "mo_market_id": "1.100", "mo_status": "OPEN",
        "odds": {
            "home": {"back": 2.7, "lay": 2.74, "back_size": 300.0, "lay_size": 250.0, "selection_id": 11},
            "draw": {"back": 2.1, "lay": 2.12, "back_size": 400.0, "lay_size": 300.0, "selection_id": 33},
            "away": {"back": 6.4, "lay": 6.6, "back_size": 120.0, "lay_size": 90.0, "selection_id": 22},
        },
        "ou": [
            _ou("1.65", 6.5, (1.01, 1.02, 300.0, 200.0), (50.0, 80.0, 20.0, 15.0)),
            _ou("1.75", 7.5, (1.10, 1.12, 120.0, 90.0), (9.0, 12.0, 15.0, 8.0)),
        ],
    }
    base.update(over)
    return base


BOOK_1_1 = {"under_6_5": 0.995, "under_7_5": 0.999, "over_6_5": 0.005, "over_7_5": 0.001,
            "btts_yes": 1.0, "btts_no": 0.0}


def _find(res, name, side):
    return [a for a in res if a["selection_name"] == name and a["side"] == side]


# ------------------------------------------------------------- scala O/U (a)
def test_esempio_utente_under_7_5_back_incoerente():
    res = detect(payload_1_1_65(), BOOK_1_1)
    got = _find(res, "Under 7.5 Goals", "back")
    assert len(got) == 1
    a = got[0]
    assert OPP_FIELDS <= set(a)
    assert a["kind"] == "anomaly" and a["rule"] == "ou_ladder"
    assert a["market_type"] == "OVER_UNDER" and a["line"] == 7.5 and a["market_id"] == "1.75"
    assert a["selection_id"] == 76 and a["price"] == 1.10 and a["size_available"] == 120.0
    assert a["p_model"] == pytest.approx(1 / 1.01, abs=1e-6)     # bound dal vicino
    assert a["p_implied"] == pytest.approx(1 / 1.10, abs=1e-6)
    assert a["gap"] == pytest.approx(0.089, abs=0.001)            # 1.10/1.01 - 1
    assert a["edge"] == pytest.approx(0.081, abs=0.001)           # 1/1.01 - 1/1.10
    assert a["ev"] == pytest.approx((1 / 1.01) * 0.10 * 0.95 - (1 - 1 / 1.01), abs=1e-6)
    assert a["confidence"] == DEFAULT_ANOMALY_PARAMS["conf_ladder"]
    assert a["minute"] == 65 and a["score"] == "1-1"
    assert "Under 7.5 Goals back 1.10" in a["rationale"]
    assert "Under 6.5 a 1.01" in a["rationale"] and "+8.9%" in a["rationale"]
    assert "quota incoerente" in a["rationale"]
    assert a["rationale"].isascii()


def test_book_veto_scarta_il_lay_che_il_modello_da_perdente():
    # il lay di Under 6.5 @1.02 e' "incoerente" col back di Under 7.5 @1.10 solo
    # sulla carta: il modello (P=0.995) dice EV<0 -> vetato. Senza book resta.
    con_book = detect(payload_1_1_65(), BOOK_1_1)
    assert not _find(con_book, "Under 6.5 Goals", "lay")
    senza = detect(payload_1_1_65(), {})
    assert _find(senza, "Under 6.5 Goals", "lay")
    assert _find(senza, "Under 7.5 Goals", "back")
    no_veto = detect(payload_1_1_65(), BOOK_1_1, params={"book_veto": False})
    assert _find(no_veto, "Under 6.5 Goals", "lay")


def test_scala_coerente_nessuna_anomalia():
    pl = payload_1_1_65(ou=[
        _ou("1.65", 6.5, (1.01, 1.02, 300.0, 200.0), (50.0, 80.0, 20.0, 15.0)),
        _ou("1.75", 7.5, (1.02, 1.03, 120.0, 90.0), (60.0, 90.0, 15.0, 8.0)),
    ])
    assert detect(pl, BOOK_1_1) == []


def test_min_gap_parametrico():
    assert detect(payload_1_1_65(), BOOK_1_1, params={"min_gap": 0.20}) == []
    assert detect(payload_1_1_65(), BOOK_1_1, params={"min_gap": 0.05})


def test_scala_over_simmetrica_back_e_lay():
    # Over 6.5 back 50 con Over 7.5 a 9.0: P(Over 6.5) >= P(Over 7.5) -> back Over 6.5 regalato
    res = detect(payload_1_1_65(), {})
    got = _find(res, "Over 6.5 Goals", "back")
    assert len(got) == 1 and got[0]["rule"] == "ou_ladder"
    assert got[0]["p_model"] == pytest.approx(1 / 9.0, abs=1e-6)
    assert "Over 7.5 a 9.00" in got[0]["rationale"]
    # lay Over 7.5 sotto il back di Over 6.5: sopra max_lay_price NON si segnala...
    assert not _find(res, "Over 7.5 Goals", "lay")
    # ...con lay 4.0 (<=5.0) si': P(Over 7.5) <= 1/50
    pl = payload_1_1_65(ou=[
        _ou("1.65", 6.5, (1.01, 1.02, 300.0, 200.0), (50.0, 80.0, 20.0, 15.0)),
        _ou("1.75", 7.5, (1.02, 1.03, 120.0, 90.0), (9.0, 4.0, 15.0, 30.0)),
    ])
    got = _find(detect(pl, {}), "Over 7.5 Goals", "lay")
    assert len(got) == 1
    assert got[0]["p_model"] == pytest.approx(1 / 50.0, abs=1e-6)
    assert got[0]["edge"] == pytest.approx(1 / 4.0 - 1 / 50.0, abs=1e-6)


# ------------------------------------------------------------- decise (b)(d)
def test_linea_decisa_dal_punteggio():
    pl = payload_1_1_65(score_home=2, score_away=1, ou=[
        _ou("1.25", 2.5, (None, 1.5, None, 40.0), (1.05, 1.06, 50.0, 50.0)),
        _ou("1.35", 3.5, (1.3, 1.32, 100.0, 100.0), (3.4, 3.5, 100.0, 100.0)),
    ])
    res = detect(pl, {})
    over = _find(res, "Over 2.5 Goals", "back")
    assert len(over) == 1
    a = over[0]
    assert a["rule"] == "decided" and a["p_model"] == 1.0
    assert a["edge"] == pytest.approx(1 - 1 / 1.05, abs=1e-6)
    assert a["ev"] == pytest.approx(0.05 * 0.95, abs=1e-6)
    assert a["confidence"] == DEFAULT_ANOMALY_PARAMS["conf_decided"]
    assert "gia' deciso (3 gol segnati)" in a["rationale"] and a["score"] == "2-1"
    # l'Under perso si laya a quota bassa con p=0
    under = _find(res, "Under 2.5 Goals", "lay")
    assert len(under) == 1 and under[0]["p_model"] == 0.0
    assert under[0]["ev"] == pytest.approx(0.95, abs=1e-6)
    # la linea 3.5 e' ancora viva: nessuna anomalia
    assert not [a for a in res if a["line"] == 3.5]


def test_linea_decisa_a_1_01_o_sospesa_non_e_anomalia():
    pl = payload_1_1_65(score_home=2, score_away=1, ou=[
        _ou("1.25", 2.5, (None, None, None, None), (1.01, 1.02, 500.0, 50.0)),
    ])
    assert detect(pl, {}) == []
    pl = payload_1_1_65(score_home=2, score_away=1, ou=[
        _ou("1.25", 2.5, (None, None, None, None), (1.10, 1.12, 500.0, 50.0), status="SUSPENDED"),
    ])
    assert detect(pl, {}) == []


def test_btts_deciso_solo_con_entrambe_a_segno():
    btts = {"market_id": "1.9", "status": "OPEN", "selections": [
        _sel(1, "Yes", 1.04, 1.05, 60.0, 60.0), _sel(2, "No", 20.0, 3.0, 10.0, 15.0)]}
    res = detect(payload_1_1_65(btts=btts), {})
    yes = _find(res, "Yes", "back")
    assert len(yes) == 1 and yes[0]["rule"] == "decided" and yes[0]["p_model"] == 1.0
    assert yes[0]["market_type"] == "BOTH_TEAMS_TO_SCORE"
    no = _find(res, "No", "lay")
    assert len(no) == 1 and no[0]["p_model"] == 0.0
    assert not [a for a in detect(payload_1_1_65(btts=btts, score_away=0), {})
                if a["market_type"] == "BOTH_TEAMS_TO_SCORE"]


def test_cella_cs_impossibile_layabile():
    cs = {"market_id": "1.55", "status": "OPEN", "selections": [
        _sel(501, "0 - 0", 1000.0, 3.0, 5.0, 25.0),
        _sel(502, "1 - 1", 4.0, 4.2, 50.0, 50.0),
        _sel(503, "2 - 1", 5.0, 5.2, 50.0, 50.0),
    ]}
    res = detect(payload_1_1_65(cs=cs), {})
    dead = _find(res, "0 - 0", "lay")
    assert len(dead) == 1 and dead[0]["rule"] == "decided" and dead[0]["p_model"] == 0.0
    assert dead[0]["market_type"] == "CORRECT_SCORE" and "impossibile sul 1-1" in dead[0]["rationale"]
    assert not _find(res, "1 - 1", "lay") and not _find(res, "2 - 1", "lay")


# ------------------------------------------------------------- MO vs CS (c)
def _cs_block(cells: dict, **extra) -> dict:
    sels = [_sel(600 + i, name, back, back + 0.5, 40.0, 40.0)
            for i, (name, back) in enumerate(cells.items())]
    return {"market_id": "1.55", "status": "OPEN", "selections": sels, **extra}


def test_mo_vs_cs_segnala_il_lato_a_buon_mercato():
    # CS: casa ~60% de-viggata; 1X2: casa 2.7 -> ~37%: back casa regalato
    cells = {"1 - 0": 6.0, "2 - 0": 8.0, "2 - 1": 6.0, "3 - 1": 12.0, "Any Other Home Win": 10.0,
             "1 - 1": 6.0, "2 - 2": 12.0, "0 - 1": 15.0, "1 - 2": 20.0, "Any Other Away Win": 40.0,
             "Any Other Draw": 50.0}
    pl = payload_1_1_65(cs=_cs_block(cells))
    res = detect(pl, {})
    home = _find(res, "Nord FC", "back")
    assert len(home) == 1
    a = home[0]
    assert a["rule"] == "mo_cs" and a["market_type"] == "MATCH_ODDS" and a["market_id"] == "1.100"
    assert a["selection_id"] == 11 and a["price"] == 2.7
    assert a["p_model"] > a["p_implied"] + DEFAULT_ANOMALY_PARAMS["mo_cs_gap"]
    assert a["confidence"] == DEFAULT_ANOMALY_PARAMS["conf_mo_cs"]
    assert "Risultato esatto implica" in a["rationale"]
    # il pareggio e' invece troppo caro nel 1X2 (2.1 -> 47%) rispetto al CS: lay X
    draw = _find(res, "The Draw", "lay")
    assert len(draw) == 1 and draw[0]["p_model"] < draw[0]["p_implied"]


def test_mo_vs_cs_gate_soglia_runner_e_book():
    cells = {"1 - 0": 6.0, "2 - 0": 8.0, "2 - 1": 6.0, "3 - 1": 12.0, "Any Other Home Win": 10.0,
             "1 - 1": 6.0, "2 - 2": 12.0, "0 - 1": 15.0, "1 - 2": 20.0, "Any Other Away Win": 40.0,
             "Any Other Draw": 50.0}
    pl = payload_1_1_65(cs=_cs_block(cells))
    assert not [a for a in detect(pl, {}, params={"mo_cs_gap": 0.50}) if a["rule"] == "mo_cs"]
    # CS con poche celle prezzate: confronto inaffidabile
    few = payload_1_1_65(cs=_cs_block({"1 - 0": 2.0, "1 - 1": 3.0, "0 - 1": 4.0}))
    assert not [a for a in detect(few, {}) if a["rule"] == "mo_cs"]
    # CS incompleto (somma 1/back fuori range): scartato
    thin = payload_1_1_65(cs=_cs_block({k: v * 3 for k, v in cells.items()}))
    assert not [a for a in detect(thin, {}) if a["rule"] == "mo_cs"]
    # 1X2 sospeso: nulla
    susp = payload_1_1_65(cs=_cs_block(cells), mo_status="SUSPENDED")
    assert not [a for a in detect(susp, {}) if a["rule"] == "mo_cs"]


# ------------------------------------------------------------- HT aperto (e)
def _ht_block():
    return {"market_id": "1.44", "status": "OPEN", "selections": [
        _sel(701, "Nord FC", 1.5, 1.6, 40.0, 40.0),
        _sel(702, "The Draw", 3.0, 3.2, 40.0, 40.0),
        _sel(703, "Sud FC", 6.0, 7.0, 40.0, 40.0),
    ]}


def test_ht_result_aperto_dopo_il_45_con_esito_noto():
    tl = [{"update_id": 1, "type": "GOAL", "minute": 12, "team": "home"},
          {"update_id": 2, "type": "GOAL", "minute": 58, "team": "away"}]
    pl = payload_1_1_65(ht_result=_ht_block(), timeline=tl)
    res = detect(pl, {})
    home = _find(res, "Nord FC", "back")
    # audit 11/09: la regola del 1X2 primo tempo porta la SUA etichetta (prima "decided", codice morto in UI)
    assert len(home) == 1 and home[0]["rule"] == "ht_open" and home[0]["p_model"] == 1.0
    assert home[0]["market_type"] == "HALF_TIME" and "1T finito 1-0" in home[0]["rationale"]
    assert _find(res, "The Draw", "lay") and not _find(res, "Sud FC", "lay")  # 6.0 > max_lay
    # campi espliciti hanno la precedenza
    pl2 = payload_1_1_65(ht_result=_ht_block(), ht_score_home=0, ht_score_away=0)
    assert _find(detect(pl2, {}), "The Draw", "back")


def test_ht_result_senza_timeline_affidabile_o_nel_1t_niente():
    pl = payload_1_1_65(ht_result=_ht_block())
    assert not [a for a in detect(pl, {}) if a["market_type"] == "HALF_TIME"]
    # timeline incompleta (1 gol su 2): non ci si fida
    pl = payload_1_1_65(ht_result=_ht_block(),
                        timeline=[{"type": "GOAL", "minute": 12, "team": "home"}])
    assert not [a for a in detect(pl, {}) if a["market_type"] == "HALF_TIME"]
    # ancora nel primo tempo: mercato legittimamente aperto
    tl = [{"type": "GOAL", "minute": 12, "team": "home"}, {"type": "GOAL", "minute": 20, "team": "away"}]
    pl = payload_1_1_65(ht_result=_ht_block(), timeline=tl, minute=30)
    assert not [a for a in detect(pl, {}) if a["market_type"] == "HALF_TIME"]


# ------------------------------------------------------- size, ordine, cap
def test_size_minima():
    pl = payload_1_1_65(ou=[
        _ou("1.65", 6.5, (1.01, 1.02, 300.0, 200.0), (None, None, None, None)),
        _ou("1.75", 7.5, (1.10, 1.12, 5.0, 90.0), (None, None, None, None)),
    ])
    assert detect(pl, BOOK_1_1) == []
    assert detect(pl, BOOK_1_1, params={"min_size": 5.0})


def test_ordinamento_per_ev_e_cap():
    btts = {"market_id": "1.9", "status": "OPEN", "selections": [
        _sel(1, "Yes", 1.04, 1.05, 60.0, 60.0), _sel(2, "No", 20.0, 3.0, 10.0, 15.0)]}
    res = detect(payload_1_1_65(btts=btts), {})
    assert len(res) >= 3
    evs = [a["ev"] for a in res]
    assert evs == sorted(evs, reverse=True)
    assert len(detect(payload_1_1_65(btts=btts), {}, params={"max_per_event": 2})) == 2
    top = detect(payload_1_1_65(btts=btts), {}, params={"max_per_event": 1})
    assert top[0]["ev"] == evs[0]


def test_nessuna_eccezione_su_blocchi_mancanti_o_rotti():
    assert detect({}, {}) == []
    assert detect({"minute": None, "score_home": None}, None) == []
    rotto = {"ou": None, "cs": "x", "odds": 3, "btts": [], "timeline": "no", "ht_result": 7,
             "minute": "abc", "mo_status": "OPEN"}
    assert detect(rotto, {}) == []
    rotto2 = {"ou": [{}, None, {"line": "x"}, {"line": 2.5, "status": "OPEN", "selections": None},
                     {"line": 2.5, "status": "OPEN", "selections": [None, {}, {"name": "Under 2.5", "back": "1.5"}]}],
              "cs": {"status": "OPEN", "selections": [{"name": None}, 5]},
              "odds": {"home": None, "draw": {}, "away": {"back": True}},
              "btts": {"status": "OPEN", "selections": [{"name": "Yes", "back": float("nan")}]},
              "minute": 70, "score_home": 1, "score_away": 1}
    assert detect(rotto2, {}) == []
    assert detect("non un dict", {}) == []
