"""W1-C1 - decisione 3 dell'utente (10/10/2026): la puntata DAL DESKTOP non multipla di
0,50 EUR e' RIFIUTATA dalla porta, col motivo del terminale di oggi; i bot invariati.

La porta (``porta.PortaLocale._minimi``) applica per l'attore ``desktop`` la politica
"rifiuta" di ``minimi.verdetto_desktop`` (parita' gia' provata con
``order_exec.place_order`` in ``test_c1_minimi.py``); qui l'arbitro e' di nuovo
``order_exec.place_order`` VERO (fermato prima del DB, come in ``test_c1_minimi``), e
l'ambiente e' quello dei test di contratto (Betfair finto con le risposte VERE di
betfairlightweight, diario VERO del motore, archivio finto e VERO: ogni test gira due
volte). ASCII-only.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest

from Betfair import order_exec as OE
from Betfair.nucleo.ordini import porta as PT
from Betfair.nucleo.ordini.tests.test_c1_minimi import _Passato, _SbFermo
from Betfair.nucleo.ordini.tests.test_c1_porta import (_Ambiente, _r,  # noqa: F401
                                                       archivio_parametrico)
from Betfair.stream import motore_ordini as MO


def _terminale(lato: str, importo: float) -> Optional[str]:
    """Il verdetto del terminale del desktop di OGGI: None = passa, altrimenti il testo
    del suo ``ValueError``."""
    try:
        OE.place_order(1, "btts", "Yes", lato, 2.0, size=importo, sb=_SbFermo())
    except _Passato:
        return None
    except ValueError as ex:
        return str(ex)
    raise AssertionError("order_exec non deve arrivare alla rete")


def _desktop(amb: _Ambiente, ref: str, lato: str, importo: float) -> Any:
    return amb.porta.invia(_r(ref=f"desktop-{ref}", attore="desktop", lato=lato,
                              importo=importo, prezzo=2.0, creato_ms=amb.orologio.ms))


def test_l_attore_desktop_e_quello_del_motore() -> None:
    assert PT.ATTORE_DESKTOP in MO.ATTORI_COMANDO


def test_desktop_2_30_rifiutato_col_motivo_del_terminale(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    a = _desktop(amb, "t1", "back", 2.30)
    assert not a.accettato
    assert a.motivo == "2,30: la punta va a multipli di 0,50, usa 2,00 o 2,50."
    assert a.motivo == _terminale("back", 2.30)
    assert amb.esecutore.ricevute == [] and amb.betfair.chiamate == []
    # rifiuto REGISTRATO come ogni rifiuto dei minimi: stato, diario, dedup del ref
    assert amb.porta.stato("desktop-t1").fase == "rifiutato"
    rifiuti = [x for x in amb.righe_diario() if x.get("tipo") == "rifiuto"]
    assert [x["ack"]["motivo"] for x in rifiuti] == [a.motivo]
    b = _desktop(amb, "t1", "back", 2.30)
    assert (b.accettato, b.seq) == (False, a.seq) and amb.esecutore.ricevute == []


def test_desktop_2_50_accettato_intero(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    a = _desktop(amb, "t1", "back", 2.50)
    assert a.accettato and amb.esecutore.ricevute[-1].importo == 2.5
    ev = list(amb.porta.eventi("desktop", a.seq))[0]
    assert ev.punta_050 is None
    assert amb.betfair.chiamate[-1]["instructions"][0]["limitOrder"]["size"] == 2.5


def test_bot_2_30_tronca_come_oggi(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    a = amb.porta.invia(_r(ref="safe-t1", importo=2.30, prezzo=2.0))
    assert a.accettato and amb.esecutore.ricevute[-1].importo == 2.0
    ev = list(amb.porta.eventi("safe", a.seq))[0]
    assert ev.punta_050 == {"chiesto": 2.3, "piazzato": 2.0, "residuo": 0.3,
                            "motivo": "punta .it diretta solo a multipli di 0,50: "
                                      "arrotondata per difetto, residuo NON piazzato"}


def test_desktop_banca_al_centesimo_e_sotto_minimo_come_il_terminale(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    lay = _desktop(amb, "t1", "lay", 2.30)          # la banca va al centesimo: passa
    assert lay.accettato and amb.esecutore.ricevute[-1].importo == 2.3
    for ref, lato, imp in (("t2", "back", 0.70), ("t3", "lay", 0.70)):
        b = _desktop(amb, ref, lato, imp)
        assert not b.accettato and b.motivo == _terminale(lato, imp)
        assert b.motivo.startswith("stake €0.70 sotto il minimo Betfair .it: ")
    assert len(amb.esecutore.ricevute) == 1


@pytest.mark.parametrize("lato", ["back", "lay"])
def test_desktop_parita_col_terminale_su_una_griglia(tmp_path: Any, lato: str) -> None:
    """Desktop dalla porta = terminale di oggi su 0,01-6,00 e qualche importo strano:
    accettato SE E SOLO SE il terminale lo accetta, motivo identico, importo MAI
    troncato. Gli stessi importi da un bot: mai il rifiuto della punta 0,50."""
    amb = _Ambiente(tmp_path)
    importi = [round(i * 0.01, 2) for i in range(1, 601, 7)] + [7.27, 12.345, 99.995, 2.3]
    rifiuti_050 = 0
    for i, imp in enumerate(importi):
        atteso = _terminale(lato, imp)
        a = _desktop(amb, f"g{i}", lato, imp)
        assert a.accettato == (atteso is None), (lato, imp, a.motivo)
        if atteso is not None:
            assert a.motivo == atteso, (lato, imp)
            rifiuti_050 += "multipli di 0,50" in atteso
        else:
            assert amb.esecutore.ricevute[-1].importo == imp, (lato, imp)
        b = amb.porta.invia(_r(ref=f"safe-g{i}", lato=lato, importo=imp, prezzo=2.0,
                               creato_ms=amb.orologio.ms))
        assert "multipli di 0,50" not in str(b.motivo or "")
    assert (rifiuti_050 > 30) == (lato == "back")
