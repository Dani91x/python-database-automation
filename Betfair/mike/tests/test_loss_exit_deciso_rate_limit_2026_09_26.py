"""26/09 R-F2-21: `loss_exit_deciso` in mike_activity UNA volta per decisione, non a ogni giro.
Falsificazione: rimettere il `db.log` incondizionato -> il secondo test diventa rosso."""
import inspect

import Betfair.mike.service as S


def test_firma_ignora_i_numeri_che_cambiano_a_ogni_tick():
    a = {"window": "2T", "mode": "fixed", "motivo": "regola fissa", "pct": 30, "cv_net": -1.2, "minuto": 61}
    b = {**a, "cv_net": -1.4, "minuto": 62}
    c = {**a, "motivo": "altra regola"}
    assert S._firma_loss_exit_deciso(a) == S._firma_loss_exit_deciso(b)
    assert S._firma_loss_exit_deciso(a) != S._firma_loss_exit_deciso(c)
    assert S._firma_loss_exit_deciso("x") == "x"


def test_il_ramo_di_attivita_scrive_solo_al_cambio_di_decisione():
    src = inspect.getsource(S)
    i = src.index('elif k == "loss_exit_deciso":')
    blocco = src[i:i + 900]
    assert "_firma_loss_exit_deciso(v)" in blocco
    assert 'extra.get("last_loss_exit_deciso_firma")' in blocco
    assert 'extra["last_loss_exit_deciso_firma"] = firma' in blocco
    # il log e' DENTRO la condizione sulla firma, non incondizionato
    assert blocco.index("if firma !=") < blocco.index("db.log(k, v")
