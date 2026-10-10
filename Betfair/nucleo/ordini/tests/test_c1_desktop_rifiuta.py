"""W1-C1 - decisione 3 dell'utente (10/10/2026): la puntata DAL DESKTOP non multipla di
0,50 EUR e' RIFIUTATA dalla porta, col motivo del terminale di oggi; i bot invariati.

La porta (``porta.PortaLocale._minimi``) applica per l'attore ``desktop`` la politica
"rifiuta" di ``minimi.verdetto_desktop`` (parita' gia' provata con
``order_exec.place_order`` in ``test_c1_minimi.py``); qui l'arbitro e' di nuovo
``order_exec.place_order`` VERO (fermato prima del DB, come in ``test_c1_minimi``), e
l'ambiente e' quello dei test di contratto (Betfair finto con le risposte VERE di
betfairlightweight, diario VERO del motore, archivio finto e VERO: ogni test gira due
volte). Nel TENNIS (correzione di parita' del 10/10) l'arbitro e'
``tennis_live_order_worker._do_place`` VERO, il percorso di oggi del ladder tennis del
desktop: niente apertura portata al minimo, testo di rifiuto del worker; la sola
differenza voluta e' la punta non multipla, che il worker tronca e la porta rifiuta
(decisione 3). ASCII-only.
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


# ---------------------------------------------------------------------------
# TENNIS dal desktop (correzione di parita' del 10/10, revisione indipendente):
# oggi il ladder tennis del desktop passa dal canale locale a
# ``tennis_live_order_worker._do_place``, che NON porta l'apertura al minimo
# (sotto il minimo: "stake non valido: ...") e TRONCA la punta (``punta_050``).
# La porta: sotto il minimo come oggi; punta non multipla RIFIUTATA (decisione 3).
# ---------------------------------------------------------------------------
class _MercatoFermo:
    """Il mercato flumine del worker: il primo accesso vuol dire che l'importo ha
    superato le guardie di taglia (``_do_place`` va alla guardia del mercato)."""

    market_id = "1.234"

    def __getattr__(self, _nome: str) -> Any:
        raise _Passato()


def _worker_tennis(monkeypatch: pytest.MonkeyPatch, lato: str, importo: float) -> Optional[str]:
    """Il verdetto di taglia del worker tennis di OGGI (``_do_place`` VERO, fermato alla
    guardia del mercato): None = passa (eventualmente troncato), altrimenti il testo."""
    from Betfair.stream.tennis_live import tennis_live_order_worker as TW

    monkeypatch.delenv("TENNIS_LIVE_JURISDICTION", raising=False)
    monkeypatch.delenv("TENNIS_LIVE_MAX_STAKE_PER_ORDER", raising=False)
    monkeypatch.setattr(TW, "_resolve_market", lambda _f, _m: _MercatoFermo())
    monkeypatch.setattr(TW, "_capture_strategy", lambda _s, _m, _mode: object())
    cmd = {"market_id": "1.234", "selection_id": 1, "side": lato, "price": 2.0,
           "size": importo, "mode": "live", "persistence": "LAPSE"}
    try:
        TW._do_place(None, None, cmd, "local1")
    except _Passato:
        return None
    except ValueError as ex:
        return str(ex)
    raise AssertionError("_do_place non deve arrivare al mercato")


def _tennis(amb: _Ambiente, ref: str, attore: str, lato: str, importo: float) -> Any:
    return amb.porta.invia(_r(ref=f"{attore}-{ref}", attore=attore, sport="tennis", lato=lato,
                              importo=importo, prezzo=2.0, creato_ms=amb.orologio.ms))


def test_desktop_tennis_sotto_minimo_rifiutato_col_testo_del_worker(
        tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    amb = _Ambiente(tmp_path)
    for i, lato in enumerate(("back", "lay")):
        a = _tennis(amb, f"t{i}", "desktop", lato, 0.70)
        assert not a.accettato and a.motivo == _worker_tennis(monkeypatch, lato, 0.70)
        assert a.motivo.startswith("stake non valido: SOTTO_MINIMO_NON_PIAZZABILE: ")
    assert amb.esecutore.ricevute == []


def test_desktop_tennis_2_30_rifiutato_e_2_50_accettato(tmp_path: Any,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    amb = _Ambiente(tmp_path)
    a = _tennis(amb, "t1", "desktop", "back", 2.30)
    # decisione 3 dell'utente: oggi il worker tennis la TRONCA (passa), la porta la rifiuta
    assert _worker_tennis(monkeypatch, "back", 2.30) is None
    assert not a.accettato and a.motivo == "2,30: la punta va a multipli di 0,50, usa 2,00 o 2,50."
    b = _tennis(amb, "t2", "desktop", "back", 2.50)
    assert b.accettato and amb.esecutore.ricevute[-1].importo == 2.5
    ev = list(amb.porta.eventi("desktop", b.seq))[0]
    assert ev.portata_al_minimo is None and ev.punta_050 is None
    assert len(amb.esecutore.ricevute) == 1


def test_bot_tennis_apertura_portata_al_minimo_come_oggi(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    a = _tennis(amb, "t1", "safe", "back", 0.70)
    assert a.accettato and amb.esecutore.ricevute[-1].importo == 1.0
    ev = list(amb.porta.eventi("safe", a.seq))[0]
    assert ev.portata_al_minimo == {"chiesto": 0.7, "piazzato": 1.0}


@pytest.mark.parametrize("lato", ["back", "lay"])
def test_desktop_tennis_parita_col_worker_su_una_griglia(
        tmp_path: Any, monkeypatch: pytest.MonkeyPatch, lato: str) -> None:
    """Desktop tennis dalla porta contro ``_do_place`` VERO: dove il worker rifiuta, la
    porta rifiuta con lo STESSO testo; dove passa intero, la porta passa intero (mai
    portato al minimo); l'unica differenza e' la punta che il worker tronca e la porta
    rifiuta (decisione 3), contata."""
    from Betfair.nucleo.ordini import minimi as MN

    amb = _Ambiente(tmp_path)
    importi = [round(i * 0.01, 2) for i in range(1, 601, 7)] + [0.995, 7.27, 12.345, 2.3]
    decisione_3 = 0
    for i, imp in enumerate(importi):
        oggi = _worker_tennis(monkeypatch, lato, imp)
        a = _tennis(amb, f"g{i}", "desktop", lato, imp)
        if oggi is not None:
            assert not a.accettato and a.motivo == oggi, (lato, imp)
        elif a.accettato:
            assert amb.esecutore.ricevute[-1].importo == imp, (lato, imp)
        else:
            assert a.motivo == MN.verdetto_desktop(lato, imp), (lato, imp)
            assert "multipli di 0,50" in a.motivo and lato == "back"
            decisione_3 += 1
    assert (decisione_3 > 30) == (lato == "back")


def test_il_testo_del_worker_tennis_e_ancora_quello_citato() -> None:
    import inspect

    from Betfair.nucleo.ordini import minimi as MN
    from Betfair.stream.tennis_live import tennis_live_order_worker as TW

    src = inspect.getsource(TW._do_place)
    assert 'raise ValueError(f"stake non valido: {verdict.reason}")' in src
    assert MN.PREFISSO_STAKE_TENNIS == "stake non valido: "
