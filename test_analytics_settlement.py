"""Certificazione logica settlement/hit (analytics_settlement). Soldi in gioco.
Copre OGNI mercato e OGNI selezione su punteggi noti."""
from analytics_settlement import ft_score_90, ht_score, hit


def _m(status="FT", fh=None, fa=None, gh=None, ga=None, hh=None, ha=None):
    return {"status_short": status, "fulltime_home": fh, "fulltime_away": fa,
            "goals_home": gh, "goals_away": ga, "halftime_home": hh, "halftime_away": ha}


# ---------------------------------------------------------------- settlement
def test_ft_score_sources():
    assert ft_score_90(_m("FT", fh=2, fa=1)) == (2, 1)
    assert ft_score_90(_m("FT", gh=2, ga=1)) == (2, 1)        # fallback goals SOLO per FT
    assert ft_score_90(_m("AET", gh=2, ga=1)) is None        # AET senza fulltime → ignoto
    assert ft_score_90(_m("PEN", gh=2, ga=1)) is None
    assert ft_score_90(_m("AET", fh=2, fa=2)) == (2, 2)      # AET con fulltime (90') ok
    assert ft_score_90(_m("NS", gh=2, ga=1)) is None
    assert ft_score_90(_m("FT")) is None


def test_ht_score():
    assert ht_score(_m("FT", hh=0, ha=1)) == (0, 1)
    assert ht_score(_m("FT")) is None


# ---- Fixture REALE 1524963: 0-3 FT, 0-3 HT (gia' validato in produzione) ----
def test_real_fixture_0_3():
    ft, ht = (0, 3), (0, 3)
    assert hit("over_2_5", "Over", ft, ht) is True
    assert hit("over_3_5", "Over", ft, ht) is False
    assert hit("over_3_5", "Under", ft, ht) is True
    assert hit("1x2", "A", ft, ht) is True and hit("1x2", "H", ft, ht) is False
    assert hit("btts", "No", ft, ht) is True and hit("btts", "Yes", ft, ht) is False
    assert hit("ht_1x2", "A", ft, ht) is True
    assert hit("first_half_over_0_5", "Over", ft, ht) is True


# ---- FT(2,1) HT(1,0): home win, copre Over/home/away/dc/ht_ft ----
FT21, HT10 = (2, 1), (1, 0)


def test_over_totali():
    assert hit("over_0_5", "Over", FT21, HT10) is True       # 3>0.5
    assert hit("over_0_5", "Under", FT21, HT10) is False
    assert hit("over_4_5", "Over", FT21, HT10) is False      # 3>4.5 no
    assert hit("over_4_5", "Under", FT21, HT10) is True
    assert hit("over_2_5", "Over", FT21, HT10) is True       # 3>2.5
    assert hit("over_3_5", "Over", FT21, HT10) is False


def test_over_casa_trasferta():
    assert hit("home_over_1_5", "Over", FT21, HT10) is True   # casa 2>1.5
    assert hit("home_over_2_5", "Over", FT21, HT10) is False  # 2>2.5 no
    assert hit("home_over_0_5", "Over", FT21, HT10) is True
    assert hit("away_over_0_5", "Over", FT21, HT10) is True   # trasferta 1>0.5
    assert hit("away_over_1_5", "Over", FT21, HT10) is False  # 1>1.5 no
    assert hit("away_over_1_5", "Under", FT21, HT10) is True


def test_double_chance():
    # esito H → 1X True, 12 True, X2 False
    assert hit("double_chance", "1X", FT21, HT10) is True
    assert hit("double_chance", "12", FT21, HT10) is True
    assert hit("double_chance", "X2", FT21, HT10) is False
    # HT esito H → 1X True
    assert hit("first_half_double_chance", "1X", FT21, HT10) is True
    assert hit("first_half_double_chance", "X2", FT21, HT10) is False


def test_ht_ft_combo():
    # HT H, FT H → 'H_H' vince, gli altri no
    assert hit("ht_ft", "H_H", FT21, HT10) is True
    assert hit("ht_ft", "H_A", FT21, HT10) is False
    assert hit("ht_ft", "D_H", FT21, HT10) is False
    assert hit("ht_ft", "A_A", FT21, HT10) is False


def test_first_half_markets():
    assert hit("first_half_over_0_5", "Over", FT21, HT10) is True    # HT 1>0.5
    assert hit("first_half_over_1_5", "Over", FT21, HT10) is False   # 1>1.5 no
    assert hit("first_half_btts", "Yes", FT21, HT10) is False        # HT 1-0
    assert hit("first_half_btts", "No", FT21, HT10) is True


# ---- FT(2,0) HT(1,0): clean sheet casa ----
def test_clean_sheet():
    ft, ht = (2, 0), (1, 0)
    assert hit("clean_sheet_home", "Yes", ft, ht) is True    # trasferta 0 gol
    assert hit("clean_sheet_home", "No", ft, ht) is False
    assert hit("clean_sheet_away", "Yes", ft, ht) is False   # casa ha segnato
    assert hit("clean_sheet_away", "No", ft, ht) is True
    assert hit("btts", "Yes", ft, ht) is False and hit("btts", "No", ft, ht) is True
    # clean sheet trasferta su 0-2
    assert hit("clean_sheet_away", "Yes", (0, 2), (0, 1)) is True


# ---- Pareggio 1-1 HT 0-0 ----
def test_pareggio():
    ft, ht = (1, 1), (0, 0)
    assert hit("1x2", "D", ft, ht) is True
    assert hit("double_chance", "1X", ft, ht) is True and hit("double_chance", "X2", ft, ht) is True
    assert hit("double_chance", "12", ft, ht) is False       # esito D non in {H,A}
    assert hit("btts", "Yes", ft, ht) is True
    assert hit("ht_ft", "D_D", ft, ht) is True
    assert hit("clean_sheet_home", "Yes", ft, ht) is False    # entrambe segnano


def test_unsettlable_returns_none():
    assert hit("over_2_5", "Over", None, (0, 0)) is None         # FT mancante
    assert hit("ht_1x2", "H", (2, 0), None) is None             # HT mancante
    assert hit("ht_ft", "H_H", (2, 0), None) is None            # serve HT+FT
    assert hit("first_half_over_1_5", "Over", (2, 0), None) is None
    assert hit("corners_over_9_5", "Over", (2, 0), (1, 0)) is None  # non gestito
    assert hit("double_chance", "ZZ", (2, 0), (1, 0)) is None   # selezione invalida


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
