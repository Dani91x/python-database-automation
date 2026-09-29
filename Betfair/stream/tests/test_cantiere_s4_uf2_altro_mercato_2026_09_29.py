"""CANTIERE S4 (29/09) - UF2: la firma successiva sulla STESSA selezione di un
ALTRO mercato non chiude la finestra dell'uscita firmata (la posizione e'
mercato + selezione: gli id di selezione si ripetono fra mercati, es. "Under"
di linee OU diverse). Mutazione U4 del coordinatore: il confronto del mercato
sostituito con `True` lasciava verdi i test S3.
"""
from __future__ import annotations

from Betfair.stream.backtest import uscite_manuali as UM
from Betfair.stream.tests.test_banco_uscite_manuali_n3_2026_09_28 import (
    _Strategia,
    _oss,
)
from Betfair.stream.tests.test_cantiere_s3_uf2_attribuzione_2026_09_29 import (
    MID,
    SEL,
    TARGET,
    _esegui,
    _o,
)
from Betfair.stream import uscite_proposte as UP

ALTRO_MID = "1.259819999"
ALTRA = "scalper|%s|%d|e9|target" % (ALTRO_MID, SEL)


def _prop(mid: str, lato: str, size: float, prezzo: float) -> dict:
    return UP.proposta_di(bot="scalper", motivo="target", market_id=mid, selection_id=SEL,
                          lato_ingresso="LAY", prezzo=prezzo, lato_chiusura=lato,
                          size_chiusura=size, se_chiudi=0.5, se_vince=-1.0, se_perde=2.0)


def test_la_firma_della_stessa_selezione_in_un_altro_mercato_non_chiude_la_finestra():
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        c = s.cancello_uscite
        c.lascia_uscire(automatiche=False, chiave=TARGET, now_s=10.0,
                        proposta=_prop(MID, "BACK", 24.42, 4.3))
        c.lascia_uscire(automatiche=False, chiave=ALTRA, now_s=10.2,
                        proposta=_prop(ALTRO_MID, "LAY", 3.0, 1.66))
        o.giro(15_500)
        _esegui(s, o, TARGET, 16.0, _prop(MID, "BACK", 24.42, 4.3))
        _esegui(s, o, ALTRA, 16.5, _prop(ALTRO_MID, "LAY", 3.0, 1.66))
        # gli ordini della target nascono DOPO la firma dell'altro mercato
        s.ordini += [_o("a3", 1.66, 3.0, 3.0, 0.0, side="LAY"),
                     _o("d24", 4.3, 24.0, 24.0, 0.0), _o("d042", 4.3, 0.42, 0.42, 0.0)]
        o.giro(40_000)
        o.giro(60_000, fine=True)
    assert o.violazioni == [], o.violazioni
    assert o.sollecitati["UF2"] == 2
