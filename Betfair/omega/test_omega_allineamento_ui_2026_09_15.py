"""LA CADENZA DEL BATTITO LA DICHIARA CHI BATTE (15/09/2026).

Vedi il gemello in ``Betfair/safe_strategy/tests`` e in ``Betfair/mike/tests``:
la Control Room giudicava la vitalita' dei tre bot con una costante scritta nel
frontend, mentre i tre battono a passi diversi. Omega e' il piu' lento, e a
vuoto rallenta ancora: e' proprio il caso in cui un metro unico sbaglia.
"""
from __future__ import annotations

from Betfair.omega import omega_service as S


def test_a_regime_vale_il_passo_del_ciclo_piu_lento():
    """Fra i due vince sempre il piu' lento: il battito non puo' arrivare prima
    del giro che lo scrive."""
    assert S._cadenza_battito({"poll_interval_s": 20, "idle_cycle_s": 60.0}) == 60.0


def test_senza_rallentamento_a_vuoto_vale_il_poll():
    """``idle_cycle_s = 0`` e' una SCELTA («non rallentare a vuoto»), non un
    valore mancante: scambiarla per «assente» dichiarerebbe 60 s al posto di 45
    e terrebbe per vivo un bot morto da un quarto di minuto."""
    assert S._cadenza_battito({"poll_interval_s": 45, "idle_cycle_s": 0.0}) == 45.0


def test_allargare_il_ciclo_allarga_la_cadenza_dichiarata():
    """E' IL PUNTO: il 13/09 questi passi sono stati allargati per far respirare
    il database. Se la pagina misurasse col metro vecchio chiamerebbe morto un
    bot vivo."""
    assert S._cadenza_battito({"poll_interval_s": 20, "idle_cycle_s": 300.0}) == 300.0


def test_valori_assurdi_non_azzerano_il_battito():
    """Un battito non puo' essere «istantaneo»: qualunque bot risulterebbe
    vecchio dopo un secondo. ``poll_interval_s`` non puo' valere zero (il minimo
    di configurazione e' 5), quindi li' uno zero e' un valore rotto e si torna
    al difetto; ``idle_cycle_s`` a zero e' invece legittimo."""
    assert S._cadenza_battito({"poll_interval_s": 0, "idle_cycle_s": 0}) == 20.0
    assert S._cadenza_battito({"poll_interval_s": -3, "idle_cycle_s": 0}) == 20.0


def test_parametri_illeggibili_o_assenti_non_fanno_saltare_niente():
    assert S._cadenza_battito(None) == 60.0
    assert S._cadenza_battito({"poll_interval_s": "boh", "idle_cycle_s": None}) == 60.0
