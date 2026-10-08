"""08/10/2026 sera - D-4 (decisione dell'utente: "esporre").

Lo scenario `gate-aperto` del banco tennis apriva soglie che la scheda della UI
non mostrava. Ora le soglie che il bot LEGGE stanno nel catalogo
(`replay_bot.parametri_modificabili`, da cui nasce `replayBotCatalogo.ts`) e
nella scheda TS (`TENNIS_BOT_REGISTRY`, parita' provata in
`frontend/src/lib/tennisSchedaCatalogo.test.ts`). Le chiavi che il bot NON
legge restano dichiarate fuori catalogo, con la causa.

Qui:
  * le chiavi esposte sono nel catalogo, col default letto dall'ISTANZA VERA
    del bot (`_instantiate_bot`) e uguale al numero di produzione;
  * in `gate-aperto` il catalogo porta il valore dello scenario;
  * le chiavi non lette NON sono nel catalogo;
  * i valori di `gate-aperto` sono quelli di prima (i referti non cambiano);
  * la nota "SCENARIO DICHIARATO" dice il vero sulle chiavi fuori scheda.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import pytest

from Betfair.stream.tennis_live.tools import replay_bot as RB

BOT_TENNIS = ("tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing")

#: chiave -> (default di produzione, valore di gate-aperto), per bot
ESPOSTE = {
    "tennis_scalper": {"warmup_ms": (30000, 0)},
    "tennis_pro": {"min_book_size": (10.0, 0.0), "price_min": (1.08, 1.01)},
    "tennis_flb": {"min_lay_size": (5.0, 0.0)},
    "tennis_swing": {"conf_ticks": (2, 1), "min_matched": (10000.0, 0.0),
                     "price_max": (8.0, 30.0), "price_min": (1.08, 1.01)},
}

#: i valori di `gate-aperto` PRIMA di D-4 (commit d257abea): non devono cambiare
GATE_APERTO_PRIMA = {
    "tennis_scalper": {"min_matched": 0.0, "min_total_matched": 0.0, "min_size": 0.0,
                       "price_min": 1.01, "price_max": 30.0, "min_flow": 0.0,
                       "warmup_ms": 0, "inplay_tick_enabled": True,
                       "runner_filter": "all"},
    "tennis_pro": {"min_matched": 0.0, "min_total_matched": 0.0,
                   "min_book_size": 0.0, "price_min": 1.01, "price_max": 30.0},
    "tennis_flb": {"min_matched": 0.0, "min_total_matched": 0.0,
                   "min_lay_size": 0.0, "lay_max": 1.30},
    "tennis_swing": {"min_matched": 0.0, "min_total_matched": 0.0,
                     "price_min": 1.01, "price_max": 30.0, "zin": 1.0,
                     "er_max": 1.0, "conf_ticks": 1},
}


def _catalogo(bot, scenario="base"):
    return {v["chiave"]: v for v in RB.parametri_modificabili(scenario, bot)}


@pytest.mark.parametrize("bot", BOT_TENNIS)
def test_esposte_nel_catalogo_col_default_di_produzione(bot):
    base = _catalogo(bot, "base")
    aperto = _catalogo(bot, "gate-aperto")
    istanza = RB._bot_dello_scenario(bot, "base")
    for k, (prod, gate) in ESPOSTE[bot].items():
        assert k in base, "%s.%s non esposta" % (bot, k)
        v = base[k]
        # il default e' quello che il bot usa davvero (istanza di produzione)
        assert v["default"] == getattr(istanza, k), (bot, k)
        assert v["default"] == pytest.approx(prod), (bot, k)
        assert aperto[k]["default"] == pytest.approx(gate), (bot, k)
        # i limiti contengono sia la produzione sia lo scenario
        assert v["min"] <= min(prod, gate) and max(prod, gate) <= v["max"], (bot, k)
        assert v["etichetta"].strip() and v["etichetta"].isascii()


@pytest.mark.parametrize("bot", BOT_TENNIS)
def test_le_chiavi_non_lette_non_sono_esposte(bot):
    base = _catalogo(bot, "base")
    istanza = RB._bot_dello_scenario(bot, "base")
    for k, causa in RB.SOGLIE_FUORI_CATALOGO[bot].items():
        assert k not in base, "%s.%s e' fuori catalogo ma esposta" % (bot, k)
        if causa == RB._NON_LETTA:
            assert not hasattr(istanza, k), (bot, k)
    # ogni voce del catalogo e' un attributo che il bot LEGGE (nessuna bugia a schermo)
    for k in base:
        assert hasattr(istanza, k), (bot, k)


def test_fuori_catalogo_solo_le_non_lette_o_invariate():
    assert {b: sorted(d) for b, d in RB.SOGLIE_FUORI_CATALOGO.items()} == {
        "tennis_scalper": ["min_matched", "min_total_matched"],
        "tennis_pro": ["min_total_matched"],
        "tennis_flb": ["min_total_matched"],
        "tennis_swing": ["min_total_matched"],
    }


@pytest.mark.parametrize("bot", BOT_TENNIS)
def test_gate_aperto_non_cambia_valori(bot):
    assert RB.parametri_scenario("gate-aperto", bot) == GATE_APERTO_PRIMA[bot]


def test_nota_dichiarata_dice_il_vero():
    swing = RB.nota_parametri_dichiarati(RB.parametri_scenario("gate-aperto", "tennis_swing"),
                                         "tennis_swing")
    assert swing.startswith("SCENARIO DICHIARATO: cambiati SOLO i parametri ['conf_ticks', ")
    assert ("(numeri che l'utente puo' gia' cambiare dalla UI; fuori dalla scheda "
            "['min_total_matched']: il bot non le legge o lo scenario non ne cambia "
            "il valore)") in swing
    scalper = RB.nota_parametri_dichiarati(RB.parametri_scenario("gate-aperto",
                                                                 "tennis_scalper"),
                                           "tennis_scalper")
    assert "fuori dalla scheda ['min_matched', 'min_total_matched']" in scalper
    # lo stake (parziali) e' un numero della UI: niente "fuori dalla scheda"
    parz = RB.nota_parametri_dichiarati({"stake": 400.0}, "tennis_flb")
    assert parz == ("SCENARIO DICHIARATO: cambiati SOLO i parametri ['stake'] (numeri "
                    "che l'utente puo' gia' cambiare dalla UI). La strategia e' quella "
                    "di produzione.")
    assert RB.nota_parametri_dichiarati({}, "tennis_flb") == "stake"
