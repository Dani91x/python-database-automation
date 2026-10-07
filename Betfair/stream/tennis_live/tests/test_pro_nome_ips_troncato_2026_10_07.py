"""07/10 (cantiere conformita' tennis) - tennis_pro: il nome IPS TRONCATO.

Sulla registrazione vera 35790089 l'IPS scrive "Marcelo Tomas Barrios V" (23
caratteri). Se il catalogo Betfair porta il nome completo, ne' il nome ne' il
cognome ("v") combaciano: Barrios restava senza selezione e i setup su di lui
(break point da ribattitore, set vinto, doppio break) non scattavano mai.
"""
from betfairlightweight import filters

from Betfair.stream.tennis_scalper.tennis_pro_bot import TennisProStrategy


def _bot(catalogo):
    return TennisProStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        pro_params={"stake": 2.0, "dry_run": True}, name_to_sel=catalogo)


def test_nome_ips_troncato_trova_il_nome_completo_del_catalogo():
    s = _bot({"Marcelo Tomas Barrios Vera": 9633138, "Ilia Simakin": 35635727})
    assert s._lookup_sel("Marcelo Tomas Barrios V") == 9633138
    assert s._lookup_sel("Ilia Simakin") == 35635727


def test_prefisso_ambiguo_non_sceglie():
    s = _bot({"Marcelo Tomas Barrios Vera": 1, "Marcelo Tomas Barrios Verde": 2})
    assert s._lookup_sel("Marcelo Tomas Barrios V") is None


def test_nome_sconosciuto_resta_sconosciuto():
    s = _bot({"Marcelo Tomas Barrios Vera": 9633138, "Ilia Simakin": 35635727})
    assert s._lookup_sel("Carlos Alcaraz") is None
