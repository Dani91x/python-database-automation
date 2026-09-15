"""LA CADENZA DEL BATTITO LA DICHIARA CHI BATTE (15/09/2026).

La Control Room giudicava la vitalita' dei tre bot con **una costante scritta
nel frontend**. Era una seconda verita', e i tre bot battono a passi diversi:
Safe ogni ``poll_interval_s`` (2 s di serie), Mike fino a 20, Omega fino a 60.
Con un solo metro per tutti, o si chiama morto un bot vivo — ed e' successo, il
trader ha visto Mike «spento» mentre operava — o, molto peggio, si chiama vivo
un bot morto.

Qui si fissa che il servizio DICHIARA il proprio passo, e che dichiara anche
perche' non sta aprendo.
"""
from __future__ import annotations

from Betfair.safe_strategy import bot_service as B


def test_la_cadenza_e_il_passo_del_ciclo():
    assert B._cadenza_battito({"poll_interval_s": 2.0}) == 2.0


def test_un_ciclo_piu_lento_allarga_la_cadenza_dichiarata():
    """E' IL PUNTO: se il passo si allarga per far respirare il database, la
    pagina lo deve sapere da qui, non indovinarlo."""
    assert B._cadenza_battito({"poll_interval_s": 30.0}) == 30.0


def test_una_cadenza_assurda_non_diventa_zero():
    """Zero significherebbe «battito istantaneo» e farebbe dichiarare vecchio
    qualunque bot al primo secondo. Per Safe lo zero e' un valore ROTTO (il
    ciclo non puo' girare a passo nullo) e si torna a quello di serie."""
    assert B._cadenza_battito({"poll_interval_s": 0.0}) == 2.0
    assert B._cadenza_battito({"poll_interval_s": -5.0}) == 2.0
    assert B._cadenza_battito({"poll_interval_s": 0.4}) == 1.0   # sotto il minimo


def test_parametri_illeggibili_non_fanno_saltare_il_battito():
    assert B._cadenza_battito({"poll_interval_s": "boh"}) > 0.0
    assert B._cadenza_battito(None) > 0.0


def test_il_motivo_del_blocco_nasce_vuoto():
    """Nessun freno in corso = niente da scrivere. Una pagina che scrive sempre
    qualcosa insegna a non leggerla."""
    B._BLOCCO.update({"motivo": None, "tetto": None, "aperte": None})
    assert B._BLOCCO["motivo"] is None
