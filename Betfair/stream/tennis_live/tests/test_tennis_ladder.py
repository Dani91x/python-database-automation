"""Test della costruzione ladder JSON tennis da un MarketBook serializzato (sintetico)."""

from Betfair.stream.tennis_live.tennis_runner import (
    build_ladder_payload,
    build_ladder_selection,
    compute_wom,
    ladder_signature,
)


def _book():
    """Shape identica a recorder.serialize_book (b/l/ltp/tv/trd per runner)."""
    return {
        "market_id": "1.234",
        "status": "OPEN",
        "inplay": True,
        "tv": 100.0,
        "runners": {
            "111": {
                "b": [[2.0, 50.0], [1.99, 20.0]],
                "l": [[2.02, 30.0], [2.04, 10.0]],
                "ltp": 2.0,
                "tv": 60.0,
                "trd": [[2.0, 60.0]],
            },
            "222": {
                "b": [[1.9, 40.0]],
                "l": [[1.95, 25.0]],
                "ltp": 1.92,
                "tv": 40.0,
            },
        },
    }


def test_compute_wom_sums_to_100():
    wom = compute_wom([[2.0, 50.0], [1.99, 20.0]], [[2.02, 30.0], [2.04, 10.0]])
    assert wom["back_pct"] + wom["lay_pct"] == 100.0
    assert wom["back_pct"] == 63.6  # 70 / (70+40)


def test_compute_wom_empty_no_div_zero():
    assert compute_wom([], []) == {"back_pct": 0.0, "lay_pct": 0.0}


def test_build_selection_levels_and_name():
    sel = build_ladder_selection("111", _book()["runners"]["111"], "Player A")
    assert sel["selection_id"] == 111
    assert sel["name"] == "Player A"
    assert sel["ltp"] == 2.0
    assert sel["back"] == [[2.0, 50.0], [1.99, 20.0]]
    assert sel["lay"] == [[2.02, 30.0], [2.04, 10.0]]
    assert sel["trd"] == [[2.0, 60.0]]
    assert isinstance(sel["back"][0][0], float)


def test_build_selection_missing_trd_is_empty():
    sel = build_ladder_selection("222", _book()["runners"]["222"], "Player B")
    assert sel["trd"] == []
    assert sel["back"] == [[1.9, 40.0]]


def test_build_ladder_payload_shape():
    names = {"111": "Player A", "222": "Player B"}
    payload = build_ladder_payload(_book(), names)
    assert set(payload.keys()) == {"updated_ms", "selections"}
    assert len(payload["selections"]) == 2
    ids = {s["selection_id"] for s in payload["selections"]}
    assert ids == {111, 222}
    assert isinstance(payload["updated_ms"], int)


def test_ladder_signature_is_order_independent():
    names = {"111": "Player A", "222": "Player B"}
    book = _book()
    p1 = build_ladder_payload(book, names)
    # ricostruisci con runner in ordine inverso → stessa firma (sort per selection_id)
    reordered = {
        "market_id": book["market_id"],
        "status": "OPEN",
        "runners": {"222": book["runners"]["222"], "111": book["runners"]["111"]},
    }
    p2 = build_ladder_payload(reordered, names)
    assert ladder_signature(p1["selections"]) == ladder_signature(p2["selections"])


def test_ladder_signature_changes_on_price_move():
    names = {"111": "Player A", "222": "Player B"}
    base = build_ladder_payload(_book(), names)
    moved = _book()
    moved["runners"]["111"]["b"] = [[2.5, 50.0]]
    moved_payload = build_ladder_payload(moved, names)
    assert ladder_signature(base["selections"]) != ladder_signature(moved_payload["selections"])
