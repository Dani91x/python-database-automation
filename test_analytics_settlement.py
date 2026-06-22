"""Certificazione logica settlement/hit (analytics_settlement). Soldi in gioco."""
from analytics_settlement import ft_score_90, ht_score, hit


def _m(status="FT", fh=None, fa=None, gh=None, ga=None, hh=None, ha=None):
    return {"status_short": status, "fulltime_home": fh, "fulltime_away": fa,
            "goals_home": gh, "goals_away": ga, "halftime_home": hh, "halftime_away": ha}


def test_ft_score_sources():
    assert ft_score_90(_m("FT", fh=2, fa=1)) == (2, 1)            # fulltime primario
    assert ft_score_90(_m("FT", gh=2, ga=1)) == (2, 1)            # fallback goals SOLO per FT
    assert ft_score_90(_m("AET", gh=2, ga=1)) is None            # AET senza fulltime → ignoto
    assert ft_score_90(_m("PEN", gh=2, ga=1)) is None
    assert ft_score_90(_m("AET", fh=2, fa=2)) == (2, 2)          # AET con fulltime (90') ok
    assert ft_score_90(_m("NS", gh=2, ga=1)) is None             # non settlato
    assert ft_score_90(_m("FT")) is None                         # nessun punteggio


def test_ht_score():
    assert ht_score(_m("FT", hh=0, ha=1)) == (0, 1)
    assert ht_score(_m("FT")) is None


# Fixture REALE 1524963: Jackson Boom 0-3 Red River (FT), HT 0-3.
FT = _m("FT", fh=0, fa=3, hh=0, ha=3)
ft, ht = ft_score_90(FT), ht_score(FT)


def test_real_fixture_1524963_fulltime():
    assert ft == (0, 3) and ht == (0, 3)
    # Over/Under totale = 3
    assert hit("over_2_5", "Over", ft, ht) is True      # 3 > 2.5 ✓ (la riga validata)
    assert hit("over_2_5", "Under", ft, ht) is False
    assert hit("over_1_5", "Over", ft, ht) is True      # 3 > 1.5
    assert hit("over_3_5", "Over", ft, ht) is False     # 3 NON > 3.5
    assert hit("over_3_5", "Under", ft, ht) is True
    # 1x2 → Away vince
    assert hit("1x2", "A", ft, ht) is True
    assert hit("1x2", "H", ft, ht) is False
    assert hit("1x2", "D", ft, ht) is False
    # BTTS → 0-3 → solo away segna → No
    assert hit("btts", "Yes", ft, ht) is False
    assert hit("btts", "No", ft, ht) is True


def test_real_fixture_1524963_halftime():
    assert hit("ht_1x2", "A", ft, ht) is True           # HT 0-3 → away
    assert hit("ht_1x2", "H", ft, ht) is False
    assert hit("first_half_over_0_5", "Over", ft, ht) is True   # 3 gol nel 1°T
    assert hit("first_half_over_0_5", "Under", ft, ht) is False


def test_draw_and_boundaries():
    d = _m("FT", fh=1, fa=1, hh=0, ha=0)
    ftd, htd = ft_score_90(d), ht_score(d)
    assert hit("1x2", "D", ftd, htd) is True
    assert hit("over_2_5", "Over", ftd, htd) is False   # 2 NON > 2.5
    assert hit("over_1_5", "Over", ftd, htd) is True    # 2 > 1.5
    assert hit("btts", "Yes", ftd, htd) is True         # 1-1 → entrambe segnano
    assert hit("ht_1x2", "D", ftd, htd) is True         # HT 0-0
    assert hit("first_half_over_0_5", "Over", ftd, htd) is False  # 0 gol 1°T


def test_unsettlable_returns_none():
    # mercato FT senza punteggio → None (mai indovinare)
    assert hit("over_2_5", "Over", None, (0, 0)) is None
    # mercato HT senza punteggio 1°T → None
    assert hit("ht_1x2", "H", (2, 0), None) is None
    assert hit("first_half_over_0_5", "Over", (2, 0), None) is None
    # mercato non gestito
    assert hit("corners_over_9_5", "Over", (2, 0), (1, 0)) is None


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fail = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS {fn.__name__}")
        except AssertionError as e:
            fail += 1; print(f"  FAIL {fn.__name__}: {e}")
    print(f"\n{'TUTTI VERDI' if not fail else f'{fail} FALLITI'} ({len(fns)} test)")
    sys.exit(1 if fail else 0)
