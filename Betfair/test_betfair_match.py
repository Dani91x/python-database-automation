"""
test_betfair_match.py — regressioni MONEY-CRITICAL per il matcher Betfair<->fixture.

Esegui:  python Betfair/test_betfair_match.py   (oppure: pytest Betfair/test_betfair_match.py)

Copre il bug storico (2026-06-25): 4 partite kuwaitiane "Al X" finite tutte sulla
stessa fixture per via del token comune "al". Verifica che ora NON collidano e che
le quote vadano alla partita giusta.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Betfair.betfair_match import resolve_matches, normalize_name, split_event_name


def _ev(i, name, od):
    return {"id": i, "name": name, "openDate": od}


def _fx(fid, h, a, d):
    return {"fixture_id": fid, "home_team_name": h, "away_team_name": a, "fixture_date": d}


def test_kuwait_no_collision():
    """3 eventi kuwaitiani -> 3 fixture DISTINTE e corrette (no collisione su 'al')."""
    events = [
        _ev("e1", "Kuwait SC v Kazma SC", "2026-06-25T19:45:00Z"),
        _ev("e2", "Al Fahaheel FC v Al-Qadsia", "2026-06-25T18:05:00Z"),
        _ev("e3", "Al Salmiyah v Al Arabi Kuwait", "2026-06-25T20:45:00Z"),
    ]
    fixtures = [
        _fx(1553795, "Al Kuwait", "Kazma", "2026-06-25T19:45:00+00:00"),
        _fx(1553794, "Al Fahaheel", "Al Qadsia", "2026-06-25T18:05:00+00:00"),
        _fx(1553796, "Al Salmiyah", "Al Arabi", "2026-06-25T20:45:00+00:00"),
    ]
    matched, unmatched = resolve_matches(events, fixtures)
    got = {m["event"]["id"]: m["fixture"]["fixture_id"] for m in matched}
    assert got == {"e1": 1553795, "e2": 1553794, "e3": 1553796}, got
    fids = [m["fixture"]["fixture_id"] for m in matched]
    assert len(fids) == len(set(fids)), "COLLISIONE!"
    assert not unmatched, unmatched


def test_bogus_kuwait_stays_unmatched():
    """Un evento 'Al X' senza fixture reale NON deve agganciare per forza una 'Al Y'."""
    events = [
        _ev("e1", "Al Fahaheel FC v Al-Qadsia", "2026-06-25T18:05:00Z"),
        _ev("e2", "Al Nasar v Al Jahra", "2026-06-25T18:05:00Z"),  # nessuna fixture corrispondente
    ]
    fixtures = [
        _fx(1553794, "Al Fahaheel", "Al Qadsia", "2026-06-25T18:05:00+00:00"),
    ]
    matched, unmatched = resolve_matches(events, fixtures)
    got = {m["event"]["id"]: m["fixture"]["fixture_id"] for m in matched}
    assert got == {"e1": 1553794}, got
    assert [u["event"]["id"] for u in unmatched] == ["e2"], unmatched


def test_one_fixture_one_event():
    """Due eventi non possono prendere la stessa fixture: solo lo score migliore vince."""
    events = [
        _ev("e1", "Manchester City v Arsenal", "2026-06-25T18:00:00Z"),
        _ev("e2", "Man City v Arsenal FC", "2026-06-25T18:00:00Z"),
    ]
    fixtures = [
        _fx(900, "Manchester City", "Arsenal", "2026-06-25T18:00:00+00:00"),
    ]
    matched, _ = resolve_matches(events, fixtures)
    fids = [m["fixture"]["fixture_id"] for m in matched]
    assert fids.count(900) == 1, "la stessa fixture assegnata 2 volte!"
    assert len(matched) == 1


def test_inverted_home_away():
    """Home/Away invertiti tra Betfair e DB devono comunque agganciare."""
    events = [_ev("e1", "Crvena Zvezda v SKU Amstetten", "2026-06-25T17:30:00Z")]
    fixtures = [_fx(1548707, "FK Crvena Zvezda", "SKU Amstetten", "2026-06-25T17:30:00+00:00")]
    # nota: nel caso reale Betfair aveva "SKU Amstetten v Crvena Zvezda" (invertito)
    events_inv = [_ev("e1", "SKU Amstetten v Crvena Zvezda", "2026-06-25T17:30:00Z")]
    m1, _ = resolve_matches(events, fixtures)
    m2, _ = resolve_matches(events_inv, fixtures)
    assert m1 and m1[0]["fixture"]["fixture_id"] == 1548707
    assert m2 and m2[0]["fixture"]["fixture_id"] == 1548707


def test_time_gate_blocks_wrong_day():
    """Stesso nome ma orario lontano (giorno diverso) NON deve agganciare (gate temporale)."""
    events = [_ev("e1", "Norway v France", "2026-06-26T19:00:00Z")]  # domani
    fixtures = [_fx(111, "Norway", "France", "2026-06-25T19:00:00+00:00")]  # oggi (24h prima)
    matched, unmatched = resolve_matches(events, fixtures)
    assert not matched, "match a 24h di distanza non dovrebbe passare il gate!"
    assert unmatched


def test_normalize_basic():
    assert normalize_name("Manchester City") == normalize_name("City Manchester")
    assert split_event_name("A v B") == ("A", "B")
    assert split_event_name("nessun separatore") is None


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests)-failed}/{len(tests)} test passati.")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run() else 0)
