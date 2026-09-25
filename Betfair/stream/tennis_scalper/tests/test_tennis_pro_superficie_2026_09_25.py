"""25/09 - tennis_pro: SUPERFICIE vera per partita + varianti ACCESE di default.

Decisione dell'utente (25/09 h21:30): "Accendili, poi valuteremo come fare, per
ora voglio vedere i bot in azione" e "tutti i bot devono avere gli aiuti e le
migliorie accese di default".

ATTENZIONE: i setup su terra/cemento NON sono certificati sul banco (nessuna
registrazione fuori dall'erba). Questi test verificano che la mappa decida il
ramo giusto e che le varianti partano accese, non che guadagnino.
"""
from __future__ import annotations

import pytest
from betfairlightweight import filters

from Betfair.stream.tennis_scalper import superficie as SUP
from Betfair.stream.tennis_scalper.tennis_pro_bot import TennisProStrategy
from Betfair.stream.tennis_scalper.tennis_score import TennisScore


# ===========================================================================
# 1. la MAPPA torneo -> superficie
# ===========================================================================
@pytest.mark.parametrize("competizione,attesa", [
    # erba
    ("Wimbledon 2026", "grass"),
    ("ATP Halle 2026", "grass"),
    ("Queen's Club Championships", "grass"),
    ("Eastbourne International", "grass"),
    ("ATP 's-Hertogenbosch", "grass"),
    ("Mallorca Championships", "grass"),
    ("WTA Bad Homburg Open", "grass"),
    ("ATP Newport", "grass"),
    # terra
    ("Roland Garros 2026", "clay"),
    ("French Open 2026", "clay"),
    ("ATP Madrid 2026", "clay"),
    ("Internazionali d'Italia - Roma", "clay"),
    ("Monte Carlo Masters", "clay"),
    ("ATP Hamburg", "clay"),
    ("ATP Kitzbuhel", "clay"),
    ("ATP Umag", "clay"),
    ("ATP Gstaad", "clay"),
    ("WTA Stuttgart", "clay"),
    # cemento
    ("US Open 2026", "hard"),
    ("Australian Open 2026", "hard"),
    ("ATP Indian Wells", "hard"),
    ("ATP Miami Open", "hard"),
    ("ATP Cincinnati", "hard"),
    ("WTA Toronto", "hard"),
    ("ATP Shanghai Masters", "hard"),
    ("Rolex Paris Masters", "hard"),
    ("ATP Vienna", "hard"),
    ("ATP Basel", "hard"),
    ("ATP Rotterdam", "hard"),
])
def test_mappa_tornei_sulle_tre_superfici(competizione, attesa):
    r = SUP.risolvi(competizione)
    assert r.superficie == attesa, (competizione, r)
    assert r.fonte == SUP.FONTE_MAPPA
    assert r.competizione == competizione


@pytest.mark.parametrize("competizione,attesa", [
    ("Challenger Genova (Clay)", "clay"),
    ("Challenger Tour - Hard Court - Shenzhen", "hard"),
    ("ITF M25 Monastir (Hard)", "hard"),
    ("Challenger Ilkley (Grass)", "grass"),
    ("Challenger Indoor Ortisei", "hard"),
])
def test_challenger_col_nome_che_dichiara_la_superficie(competizione, attesa):
    r = SUP.risolvi(competizione)
    assert (r.superficie, r.fonte) == (attesa, SUP.FONTE_NOME)


def test_parola_intera_halle_non_scatta_dentro_challenger():
    """'challenger' contiene le lettere di 'halle': a parola intera non e' Halle."""
    r = SUP.risolvi("Challenger Tour")
    assert r.fonte == SUP.FONTE_DEFAULT and r.voce != "Halle"


@pytest.mark.parametrize("competizione", ["ITF M15 Xyz", "Challenger Tour", "Esibizione"])
def test_sconosciuto_da_il_default_dichiarato(competizione):
    r = SUP.risolvi(competizione)
    assert r.superficie == SUP.SUPERFICIE_DEFAULT == "hard"
    assert r.fonte == SUP.FONTE_DEFAULT
    assert r.testo() == "cemento (default: torneo sconosciuto)"


@pytest.mark.parametrize("vuoto", [None, "", "   "])
def test_senza_nome_default_dichiarato(vuoto):
    r = SUP.risolvi(vuoto)
    assert (r.superficie, r.fonte) == ("hard", SUP.FONTE_DEFAULT)
    assert r.testo() == "cemento (default: competizione non nota)"


def test_testo_per_la_ui():
    assert SUP.risolvi("Roland Garros 2026").testo() == "terra (mappa: Roland Garros)"
    assert SUP.risolvi("Wimbledon").testo() == "erba (mappa: Wimbledon)"


def test_come_params_dichiara_sempre_la_fonte():
    p = SUP.risolvi("Roland Garros 2026").come_params()
    assert p == {"surface": "clay", "surface_fonte": "mappa", "surface_voce": "Roland Garros",
                 "surface_torneo": "Roland Garros 2026",
                 "surface_testo": "terra (mappa: Roland Garros)"}
    d = SUP.risolvi(None).come_params()
    assert d["surface_fonte"] == "default" and d["surface"] == "hard"


def test_ogni_voce_della_mappa_e_dato_completo():
    """La mappa e' DATI: ogni voce ha superficie valida, parole e fonte."""
    assert len(SUP.MAPPA_TORNEI) >= 15
    for v in SUP.MAPPA_TORNEI:
        assert v["superficie"] in ("grass", "clay", "hard"), v
        assert v["parole"] and all(isinstance(x, str) and x for x in v["parole"]), v
        assert isinstance(v["fonte"], str) and v["fonte"], v
        assert isinstance(v["voce"], str) and v["voce"], v
    per = SUP.voci_per_superficie()
    assert set(per) == {"grass", "clay", "hard"}


# ===========================================================================
# 2. il BOT: superficie usata, varianti accese di default
# ===========================================================================
def _bot(**params):
    return TennisProStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        pro_params={"stake": 2.0, "dry_run": True, **params},
        name_to_sel={"De Minaur": 111, "Cobolli": 222},
    )


def test_varianti_accese_di_default():
    b = _bot()
    assert (b.trend, b.adapt, b.maker) == (True, True, True)


def test_varianti_spente_solo_con_false_esplicito():
    b = _bot(trend=False, adapt=False, maker=False)
    assert (b.trend, b.adapt, b.maker) == (False, False, False)
    # una sola spenta: le altre restano accese
    b2 = _bot(maker=False)
    assert (b2.trend, b2.adapt, b2.maker) == (True, True, False)


_REV = ("enable_serving_set", "enable_double_break", "enable_compressed_fav")


@pytest.mark.parametrize("sup,attivi", [("grass", False), ("clay", True), ("hard", True)])
def test_setup_lay_reversal_attivi_solo_su_terra_e_cemento(sup, attivi):
    """Variante BASE (varianti spente): i 3 setup di reversione si accendono
    SOLO fuori dall'erba, come ha sempre voluto il bot."""
    b = _bot(surface=sup, trend=False, adapt=False, maker=False)
    assert all(getattr(b, k) is attivi for k in _REV), (sup, [getattr(b, k) for k in _REV])


def test_con_le_varianti_accese_i_setup_di_dominio_girano_anche_su_erba():
    """FATTO DICHIARATO (non una scelta di questo lavoro): nel bot i setup di
    dominio si accendono con `_lay_rev or trend or adapt`. Con le varianti
    accese di default, anche su ERBA serving-for-set/doppio break/favorito
    compresso sono attivi, con la direzione decisa dal regime (adapt)."""
    b = _bot(surface="grass")
    assert all(getattr(b, k) is True for k in _REV)


@pytest.mark.parametrize("sup,chi", [("grass", 111), ("clay", 222), ("hard", 222)])
def test_break_point_lato_dalla_superficie(sup, chi):
    """Erba: BACK di chi serve; terra/cemento: BACK di chi riceve."""
    b = _bot(surface=sup, trend=False, adapt=False, maker=False)
    b.score = TennisScore(event_id="1", server="home", point_home="15", point_away="40",
                          games_home=0, games_away=0, sets_home=0, sets_away=0,
                          home_name="De Minaur", away_name="Cobolli")

    class _M:
        market_id = "1.1"

    px = {111: {"bb": 1.8, "bl": 1.82, "sb": 100.0, "sl": 100.0, "ltp": 1.8},
          222: {"bb": 2.2, "bl": 2.24, "sb": 100.0, "sl": 100.0, "ltp": 2.2}}
    assert b._sig_break_point(_M(), px) is True
    assert b._trade["1.1"]["sel"] == chi


def test_il_bot_dichiara_la_fonte_della_superficie():
    b = _bot(**SUP.risolvi("Roland Garros 2026").come_params())
    assert b.surface == "clay" and b.surface_fonte == "mappa"
    senza = _bot()
    assert senza.surface == "grass"
    assert "default della classe" in senza.surface_fonte
