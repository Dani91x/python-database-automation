"""Test di Betfair/safe_strategy/combos.py — combinazioni a profitto bloccato."""
from __future__ import annotations

import pytest

from Betfair.safe_strategy.combos import DEFAULT_COMBO_PARAMS, find_combos

OPP_FIELDS = {"market_type", "market_name", "line", "market_id", "selection_id",
              "selection_name", "side", "price", "size_available", "p_model", "p_implied",
              "edge", "ev", "confidence", "rationale", "minute", "score"}
COMBO_FIELDS = {"kind", "combo", "legs", "locked_profit_per_eur", "worst_case_per_eur",
                "best_case_per_eur", "total_stake"}
LEG_FIELDS = {"market_type", "market_id", "selection_id", "selection_name", "side", "price",
              "size_available", "stake_ratio"}


# ---------------------------------------------------------------- helper dati
def _sel(sid, name, back=None, lay=None, back_size=None, lay_size=None, status="ACTIVE"):
    return {"selection_id": sid, "name": name, "runner_status": status,
            "back": back, "lay": lay, "back_size": back_size, "lay_size": lay_size}


def _ou(mid, line, under, over, status="OPEN"):
    n = int(line * 10)
    return {"market_id": mid, "line": line, "status": status, "selections": [
        _sel(n + 1, f"Under {line} Goals", *under),
        _sel(n + 2, f"Over {line} Goals", *over),
    ]}


def _mo(home, draw, away, size=300.0):
    return {"home": {"back": home, "lay": home + 0.04, "back_size": size, "lay_size": size, "selection_id": 11},
            "draw": {"back": draw, "lay": draw + 0.04, "back_size": size, "lay_size": size, "selection_id": 33},
            "away": {"back": away, "lay": away + 0.1, "back_size": size, "lay_size": size, "selection_id": 22}}


def payload(**over) -> dict:
    base = {
        "home": "Nord FC", "away": "Sud FC", "minute": 65,
        "score_home": 1, "score_away": 1,
        "mo_market_id": "1.100", "mo_status": "OPEN",
        "odds": _mo(2.7, 3.0, 3.1),                       # book 102.6%: niente dutch
        "ou": [
            _ou("1.65", 6.5, (1.01, 1.02, 300.0, 200.0), (50.0, 80.0, 20.0, 15.0)),
            _ou("1.75", 7.5, (1.10, 1.12, 120.0, 90.0), (9.0, 12.0, 15.0, 8.0)),
        ],
    }
    base.update(over)
    return base


BOOK = {"under_6_5": 0.995, "under_7_5": 0.999, "over_6_5": 0.005, "over_7_5": 0.001}


def _by(res, combo):
    return [c for c in res if c["combo"] == combo]


def _net(legs_with_stakes, outcomes, comm=0.05):
    """Ricalcolo INDIPENDENTE del saldo netto per esito (commissione per mercato)."""
    out = []
    for h, a in outcomes:
        per_m = {}
        for leg, stake, wins in legs_with_stakes:
            won = wins(h, a)
            if leg["side"] == "back":
                pl = stake * (leg["price"] - 1) if won else -stake
            else:
                pl = -stake * (leg["price"] - 1) if won else stake
            per_m[leg["market_id"]] = per_m.get(leg["market_id"], 0.0) + pl
        out.append(sum(v * (1 - comm) if v > 0 else v for v in per_m.values()))
    return out


# ------------------------------------------------------------------ dutching
def test_dutching_1x2_con_book_97_percento():
    pl = payload(odds=_mo(3.0, 3.2, 3.1), ou=[])   # 1/3 + 1/3.2 + 1/3.1 = 0.968
    res = find_combos(pl, {})
    got = _by(res, "dutch")
    assert len(got) == 1
    c = got[0]
    assert OPP_FIELDS <= set(c) and COMBO_FIELDS <= set(c)
    assert c["kind"] == "combo" and c["market_type"] == "MATCH_ODDS"
    assert len(c["legs"]) == 3 and all(LEG_FIELDS <= set(lg) for lg in c["legs"])
    assert {lg["selection_id"] for lg in c["legs"]} == {11, 33, 22}
    assert all(lg["side"] == "back" and lg["market_id"] == "1.100" for lg in c["legs"])
    assert sum(lg["stake_ratio"] for lg in c["legs"]) == pytest.approx(1.0, abs=1e-6)
    assert c["total_stake"] == pytest.approx(DEFAULT_COMBO_PARAMS["combo_stake"], abs=0.02)
    # profitto uguale qualunque vinca: (1/0.968 - 1) * 0.95 ~ 3.1% netto
    expected = (1.0 / (1 / 3.0 + 1 / 3.2 + 1 / 3.1) - 1.0) * 0.95
    assert c["locked_profit_per_eur"] == pytest.approx(expected, abs=0.004)
    assert c["worst_case_per_eur"] == c["locked_profit_per_eur"]
    assert c["best_case_per_eur"] == pytest.approx(c["worst_case_per_eur"], abs=0.004)
    assert c["ev"] == c["edge"] == c["locked_profit_per_eur"]
    assert "dutching 1X2" in c["rationale"] and "book 96.8" in c["rationale"]
    assert "profitto bloccato" in c["rationale"] and c["rationale"].isascii()
    assert c["minute"] == 65 and c["score"] == "1-1"
    assert c["confidence"] == pytest.approx(DEFAULT_COMBO_PARAMS["conf_single_market"], abs=1e-6)


def test_dutching_verificato_sugli_stake_reali():
    pl = payload(odds=_mo(3.0, 3.2, 3.1), ou=[])
    c = _by(find_combos(pl, {}), "dutch")[0]
    wins = {11: lambda h, a: h > a, 33: lambda h, a: h == a, 22: lambda h, a: a > h}
    legs = [(lg, lg["stake"], wins[lg["selection_id"]]) for lg in c["legs"]]
    outcomes = [(1 + dh, 1 + da) for dh in range(6) for da in range(6)]
    net = _net(legs, outcomes)
    assert min(net) / c["total_stake"] == pytest.approx(c["worst_case_per_eur"], abs=1e-6)
    assert min(net) > 0


def test_nessun_dutching_con_book_sopra_100():
    assert _by(find_combos(payload(ou=[]), {}), "dutch") == []          # 102.6%
    pl = payload(odds=_mo(3.0, 3.0, 3.0), ou=[])                         # esattamente 100%
    assert _by(find_combos(pl, {}), "dutch") == []


def test_dutching_ou_e_btts_due_runner():
    pl = payload(ou=[_ou("1.25", 2.5, (2.2, 2.3, 100.0, 100.0), (2.1, 2.2, 100.0, 100.0))],
                 btts={"market_id": "1.9", "status": "OPEN", "selections": [
                     _sel(1, "Yes", 1.04, 1.05, 60.0, 60.0), _sel(2, "No", 30.0, 40.0, 60.0, 60.0)]})
    res = find_combos(pl, {})
    ou = [c for c in _by(res, "dutch") if c["market_type"] == "OVER_UNDER"]
    assert len(ou) == 1 and ou[0]["locked_profit_per_eur"] > 0.02
    # Gol/NoGol sull'1-1: il "No" e' morto -> un solo runner vivo, niente dutch
    assert not [c for c in res if c["market_type"] == "BOTH_TEAMS_TO_SCORE"]


def test_dutching_correct_score_esclude_celle_morte_e_richiede_completezza():
    cells = {"1 - 1": 4.2, "2 - 1": 6.4, "1 - 2": 8.4, "2 - 2": 10.5, "3 - 1": 12.5,
             "1 - 3": 21.0, "3 - 2": 16.0, "2 - 3": 26.0, "3 - 3": 42.0,
             "Any Other Home Win": 21.0, "Any Other Away Win": 42.0, "Any Other Draw": 100.0}
    sels = [_sel(600 + i, n, b, b + 1, 50.0, 50.0) for i, (n, b) in enumerate(cells.items())]
    dead = [_sel(700, "0 - 0", None, 1000.0, None, 5.0), _sel(701, "1 - 0", None, None, None, None)]
    inv = sum(1 / b for b in cells.values())
    assert inv < 1.0
    pl = payload(ou=[], cs={"market_id": "1.55", "status": "OPEN", "selections": sels + dead})
    got = _by(find_combos(pl, {}), "dutch")
    assert len(got) == 1
    c = got[0]
    assert c["market_type"] == "CORRECT_SCORE" and len(c["legs"]) == 12
    assert not [lg for lg in c["legs"] if lg["selection_name"] in ("0 - 0", "1 - 0")]
    # 12 gambe arrotondate al centesimo su 10 EUR: il lock reale sta sotto quello teorico
    teorico = (1 / inv - 1) * 0.95
    assert 0.0 < teorico - c["locked_profit_per_eur"] < 0.015
    # una cella VIVA (raggiungibile dall'1-1) senza back -> copertura incompleta -> nessun dutch
    sels2 = sels + [_sel(800, "1 - 4", None, None, None, None)]
    pl2 = payload(ou=[], cs={"market_id": "1.55", "status": "OPEN", "selections": sels2 + dead})
    assert _by(find_combos(pl2, {}), "dutch") == []


# ------------------------------------------------------------- under stack
def test_under_stack_esempio_utente():
    res = find_combos(payload(), BOOK)
    got = _by(res, "under_stack")
    assert len(got) == 1
    c = got[0]
    sides = {(lg["selection_name"], lg["side"]) for lg in c["legs"]}
    assert sides == {("Under 7.5 Goals", "back"), ("Under 6.5 Goals", "lay")}
    assert c["worst_case_per_eur"] >= 0.0 and c["locked_profit_per_eur"] == c["worst_case_per_eur"]
    assert c["locked_profit_per_eur"] > 0.02 and c["best_case_per_eur"] > c["locked_profit_per_eur"]
    assert c["confidence"] <= DEFAULT_COMBO_PARAMS["conf_multi_market"]
    assert "profitto bloccato" in c["rationale"] and "Under 7.5" in c["rationale"]
    # ricalcolo indipendente: gol totali <= 6, == 7, >= 8
    wins = {"Under 7.5 Goals": lambda h, a: h + a < 7.5, "Under 6.5 Goals": lambda h, a: h + a < 6.5}
    legs = [(lg, lg["stake"], wins[lg["selection_name"]]) for lg in c["legs"]]
    outcomes = [(1, 1), (3, 3), (4, 3), (3, 4), (5, 3), (6, 6)]
    net = _net(legs, outcomes)
    assert min(net) >= -1e-9
    assert min(net) / c["total_stake"] == pytest.approx(c["worst_case_per_eur"], abs=1e-6)


def test_book_ordina_la_gamba_regalata_per_prima():
    c = _by(find_combos(payload(), BOOK), "under_stack")[0]
    assert c["legs"][0]["selection_name"] == "Under 7.5 Goals" and c["legs"][0]["side"] == "back"
    assert c["selection_name"] == "Under 7.5 Goals" and c["side"] == "back"
    assert c["price"] == 1.10 and c["market_id"] == "1.75" and c["selection_id"] == 76
    assert c["p_model"] == pytest.approx(0.999, abs=1e-6)
    assert c["p_implied"] == pytest.approx(1 / 1.10, abs=1e-6)
    # senza book: p_model = implicita
    c2 = _by(find_combos(payload(), {}), "under_stack")[0]
    assert c2["p_model"] == c2["p_implied"]


def test_nessuna_combo_se_le_quote_non_si_incrociano():
    pl = payload(ou=[
        _ou("1.65", 6.5, (1.01, 1.02, 300.0, 200.0), (50.0, 80.0, 20.0, 15.0)),
        _ou("1.75", 7.5, (1.01, 1.02, 120.0, 90.0), (60.0, 90.0, 15.0, 8.0)),
    ])
    assert find_combos(pl, BOOK) == []


def test_over_stack_e_ou_span():
    # over_stack: back Over 2.5 @3.0 sopra il lay di Over 3.5 @2.5 (assurdo ma bloccabile)
    pl = payload(ou=[
        _ou("1.25", 2.5, (1.5, 1.52, 100.0, 100.0), (3.0, 3.1, 100.0, 100.0)),
        _ou("1.35", 3.5, (1.2, 1.25, 100.0, 100.0), (2.4, 2.5, 100.0, 100.0)),
    ])
    res = find_combos(pl, {})
    ov = _by(res, "over_stack")
    assert len(ov) == 1 and ov[0]["worst_case_per_eur"] >= 0.0
    assert {(lg["selection_name"], lg["side"]) for lg in ov[0]["legs"]} == \
        {("Over 2.5 Goals", "back"), ("Over 3.5 Goals", "lay")}
    # ou_span: back Under 3.5 @1.2 + back Over 2.5 @3.0 -> 1/1.2 + 1/3 = 1.167 > 1: niente
    assert _by(res, "ou_span") == []
    pl2 = payload(ou=[
        _ou("1.25", 2.5, (1.5, 1.52, 100.0, 100.0), (4.0, 4.1, 100.0, 100.0)),
        _ou("1.35", 3.5, (1.2, 1.25, 100.0, 100.0), (2.4, 2.5, 100.0, 100.0)),
    ])
    sp = _by(find_combos(pl2, {}), "ou_span")    # 1/1.2 + 1/4 = 1.083 > 1 ancora niente
    assert sp == []
    pl3 = payload(ou=[
        _ou("1.25", 2.5, (1.5, 1.52, 100.0, 100.0), (8.0, 8.2, 100.0, 100.0)),
        _ou("1.35", 3.5, (1.1, 1.12, 100.0, 100.0), (2.4, 2.5, 100.0, 100.0)),
    ])
    sp = _by(find_combos(pl3, {}), "ou_span")    # 1/1.1 + 1/8 = 1.034 > 1: no
    assert sp == []
    pl4 = payload(ou=[
        _ou("1.25", 2.5, (1.5, 1.52, 100.0, 100.0), (20.0, 22.0, 100.0, 100.0)),
        _ou("1.35", 3.5, (1.05, 1.06, 100.0, 100.0), (2.4, 2.5, 100.0, 100.0)),
    ])
    sp = _by(find_combos(pl4, {}), "ou_span")    # 1/1.05 + 1/20 = 1.002 > 1: no
    assert sp == []
    pl5 = payload(ou=[
        _ou("1.25", 2.5, (1.5, 1.52, 100.0, 100.0), (40.0, 42.0, 100.0, 100.0)),
        _ou("1.35", 3.5, (1.04, 1.05, 100.0, 100.0), (2.4, 2.5, 100.0, 100.0)),
    ])
    sp = _by(find_combos(pl5, {}), "ou_span")    # 1/1.04 + 1/40 = 0.9865 < 1: si'
    assert len(sp) == 1 and sp[0]["worst_case_per_eur"] > 0.0
    assert {(lg["selection_name"], lg["side"]) for lg in sp[0]["legs"]} ==         {("Under 3.5 Goals", "back"), ("Over 2.5 Goals", "back")}
    # con 3 gol esatti vincono ENTRAMBE: caso migliore ben sopra il lock
    assert sp[0]["best_case_per_eur"] > sp[0]["worst_case_per_eur"] + 0.5


# ---------------------------------------------------------------- cs cover
def test_cs_cover_lay_cella_lontana_coperta_dall_over():
    cs = {"market_id": "1.55", "status": "OPEN", "selections": [
        _sel(601, "3 - 3", 25.0, 20.0, 30.0, 30.0),     # lay 20 < back Over 5.5 @30
        _sel(602, "2 - 2", 8.0, 8.5, 30.0, 30.0),       # lay 8.5 > back Over 3.5 @3: no
    ]}
    pl = payload(ou=[
        _ou("1.35", 3.5, (1.4, 1.42, 100.0, 100.0), (3.0, 3.1, 100.0, 100.0)),
        _ou("1.55", 5.5, (1.04, 1.05, 100.0, 100.0), (30.0, 34.0, 100.0, 100.0)),
    ], cs=cs)
    got = _by(find_combos(pl, {}), "cs_cover")
    assert len(got) == 1
    c = got[0]
    assert {(lg["selection_name"], lg["side"]) for lg in c["legs"]} == \
        {("3 - 3", "lay"), ("Over 5.5 Goals", "back")}
    assert c["worst_case_per_eur"] >= 0.0 and c["best_case_per_eur"] > 0.05
    wins = {"3 - 3": lambda h, a: (h, a) == (3, 3), "Over 5.5 Goals": lambda h, a: h + a > 5.5}
    legs = [(lg, lg["stake"], wins[lg["selection_name"]]) for lg in c["legs"]]
    net = _net(legs, [(1, 1), (2, 3), (3, 3), (4, 2), (3, 4), (6, 6)])
    assert min(net) >= -1e-9
    assert "coperto da Over 5.5" in c["rationale"]


# ----------------------------------------------------- size, lock, cap, robustezza
def test_size_gating_per_gamba():
    pl = payload(ou=[
        _ou("1.65", 6.5, (1.01, 1.02, 300.0, 2.0), (50.0, 80.0, 20.0, 15.0)),   # lay_size 2 EUR
        _ou("1.75", 7.5, (1.10, 1.12, 120.0, 90.0), (9.0, 12.0, 15.0, 8.0)),
    ])
    assert _by(find_combos(pl, BOOK), "under_stack") == []
    # con stake totale piu' piccolo e min_size abbassata torna fattibile
    got = _by(find_combos(pl, BOOK, params={"combo_stake": 2.0, "min_size": 1.0}), "under_stack")
    assert len(got) == 1 and all(lg["size_available"] >= lg["stake"] for lg in got[0]["legs"])


def test_min_lock_e_commissione():
    pl = payload(odds=_mo(3.0, 3.2, 3.1), ou=[])
    assert _by(find_combos(pl, {}, params={"min_lock": 0.10}), "dutch") == []
    lordo = _by(find_combos(pl, {}, params={"commission": 0.0}), "dutch")[0]
    netto = _by(find_combos(pl, {}), "dutch")[0]
    assert lordo["locked_profit_per_eur"] > netto["locked_profit_per_eur"] > 0


def test_ordinamento_per_lock_e_cap():
    pl = payload(odds=_mo(3.0, 3.2, 3.1))       # dutch 1X2 + under_stack (+ ou_span)
    res = find_combos(pl, BOOK)
    assert len(res) >= 2
    locks = [c["locked_profit_per_eur"] for c in res]
    assert locks == sorted(locks, reverse=True)
    top = find_combos(pl, BOOK, params={"max_per_event": 1})
    assert len(top) == 1 and top[0]["locked_profit_per_eur"] == locks[0]


def test_linee_gia_decise_non_entrano_nelle_combo():
    # 2-1: la linea 2.5 e' decisa -> nessuna gamba su di essa (e' un'anomalia, non una combo)
    pl = payload(score_home=2, score_away=1, ou=[
        _ou("1.25", 2.5, (None, 1.5, None, 40.0), (1.05, 1.06, 50.0, 50.0)),
        _ou("1.35", 3.5, (1.3, 1.32, 100.0, 100.0), (3.4, 3.5, 100.0, 100.0)),
    ])
    res = find_combos(pl, {})
    assert not [c for c in res for lg in c["legs"] if lg["market_id"] == "1.25"]


def test_nessuna_eccezione_su_blocchi_mancanti_o_rotti():
    assert find_combos({}, {}) == []
    assert find_combos({"minute": None}, None) == []
    rotto = {"ou": None, "cs": "x", "odds": 3, "btts": [], "minute": "abc", "mo_status": "OPEN"}
    assert find_combos(rotto, {}) == []
    rotto2 = {"ou": [{}, None, {"line": "x"}, {"line": 2.5, "status": "OPEN", "selections": None},
                     {"line": 2.5, "status": "OPEN",
                      "selections": [None, {}, {"name": "Under 2.5", "back": "1.5"}]}],
              "cs": {"status": "OPEN", "selections": [{"name": None}, 5, {"name": "1 - 1", "back": 4.0}]},
              "odds": {"home": None, "draw": {}, "away": {"back": True}},
              "btts": {"status": "OPEN", "selections": [{"name": "Yes", "back": float("inf")}]},
              "minute": 70, "score_home": 1, "score_away": 1, "mo_status": "OPEN"}
    assert find_combos(rotto2, {}) == []
    assert find_combos("non un dict", {}) == []
