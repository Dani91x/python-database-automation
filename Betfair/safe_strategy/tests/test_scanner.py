"""Test della logica PURA dello scanner Safe Strategy (nessuna rete/DB)."""
from datetime import datetime, timedelta, timezone

from Betfair.safe_strategy import scanner


def test_selection_sides_da_sort_priority():
    runners = [
        {"selection_id": 11, "name": "Nord FC", "sort_priority": 1},
        {"selection_id": 22, "name": "Sud FC", "sort_priority": 2},
        {"selection_id": 33, "name": "The Draw", "sort_priority": 3},
    ]
    assert scanner.selection_sides(runners) == {"home": 11, "away": 22, "draw": 33}


def test_selection_sides_fallback_nome_draw():
    runners = [
        {"selection_id": 11, "name": "Nord FC", "sort_priority": 1},
        {"selection_id": 22, "name": "Sud FC", "sort_priority": 2},
        {"selection_id": 33, "name": "The Draw", "sort_priority": None},
    ]
    assert scanner.selection_sides(runners)["draw"] == 33


def test_tennis_sides():
    runners = [
        {"selection_id": 1, "name": "Rossi", "sort_priority": 1},
        {"selection_id": 2, "name": "Bianchi", "sort_priority": 2},
    ]
    assert scanner.tennis_sides(runners) == {"p1": 1, "p2": 2}


def test_split_event_name():
    assert scanner.split_event_name("Udinese v Venezia") == ("Udinese", "Venezia")
    assert scanner.split_event_name("Rossi vs Bianchi") == ("Rossi", "Bianchi")
    assert scanner.split_event_name("SenzaSeparatore") == (None, None)
    assert scanner.split_event_name(None) == (None, None)


def test_is_cs_candidate_finestra_e_gol():
    assert scanner.is_cs_candidate(49, 1, 0) is True
    assert scanner.is_cs_candidate(39, 1, 0) is False    # troppo presto
    assert scanner.is_cs_candidate(61, 1, 0) is False    # troppo tardi
    assert scanner.is_cs_candidate(49, 3, 0) is False    # troppi gol per lato
    assert scanner.is_cs_candidate(None, 1, 0) is False  # dati mancanti
    assert scanner.is_cs_candidate(49, None, 0) is False


def test_pre_ko_window():
    now = datetime.now(timezone.utc)
    dentro = (now + timedelta(minutes=10)).isoformat()
    lontano = (now + timedelta(hours=3)).isoformat()
    passato = (now - timedelta(minutes=1)).isoformat()
    assert scanner.in_pre_ko_window(dentro, now) is True
    assert scanner.in_pre_ko_window(lontano, now) is False
    assert scanner.in_pre_ko_window(passato, now) is False
    assert scanner.in_pre_ko_window(None, now) is False


def test_freeze_pre_ko_congela_al_primo_inplay():
    odds = {"home": {"back": 1.65}, "draw": {"back": 4.0}, "away": {"back": 5.5}}
    ref = scanner.freeze_pre_ko(None, inplay=False, odds=odds)
    assert ref is not None and ref["home"] == 1.65 and "captured_at" in ref
    # pre-KO: si aggiorna (closing line)
    odds2 = {"home": {"back": 1.7}, "draw": {"back": 4.0}, "away": {"back": 5.2}}
    ref2 = scanner.freeze_pre_ko(ref, inplay=False, odds=odds2)
    assert ref2 is not None and ref2["home"] == 1.7
    # in-play: CONGELATO — mai quote live nel riferimento
    odds_live = {"home": {"back": 1.2}, "draw": {"back": 8.0}, "away": {"back": 15.0}}
    assert scanner.freeze_pre_ko(ref2, inplay=True, odds=odds_live) is ref2
    # 1X2 incompleto: il riferimento precedente resta
    assert scanner.freeze_pre_ko(ref2, inplay=False, odds={"home": {"back": None}}) is ref2
    # mai nato pre-KO → resta None anche in-play
    assert scanner.freeze_pre_ko(None, inplay=True, odds=odds_live) is None


def test_cadenze_adattive():
    assert scanner.books_period_calcio(any_inplay=True, any_hot=True) == 10.0
    assert scanner.books_period_calcio(any_inplay=True, any_hot=False) == 20.0
    assert scanner.books_period_calcio(any_inplay=False, any_hot=False) == 60.0
    assert scanner.books_period_tennis(True) == 10.0
    assert scanner.books_period_tennis(False) == 60.0


def test_payload_signature_stabile_e_sensibile():
    p1 = {"a": 1, "b": {"c": [1, 2]}}
    p2 = {"b": {"c": [1, 2]}, "a": 1}       # stesso contenuto, ordine diverso
    p3 = {"a": 1, "b": {"c": [1, 3]}}
    assert scanner.payload_signature(p1) == scanner.payload_signature(p2)
    assert scanner.payload_signature(p1) != scanner.payload_signature(p3)


def test_build_cs_block_riconosce_any_other():
    sels = [
        {"name": "1 - 0", "back": 3.0, "lay": 3.1},
        {"name": "Any Other Home Win", "back": 44.0, "lay": 46.0},
        {"name": "Any Other Away Win", "back": 48.0, "lay": 50.0},
    ]
    blk = scanner.build_cs_block("1.23", "OPEN", sels)
    assert blk is not None
    assert blk["any_other_home"] == {"back": 44.0, "lay": 46.0}
    assert blk["any_other_away"] == {"back": 48.0, "lay": 50.0}
    assert scanner.build_cs_block(None, "OPEN", sels) is None
