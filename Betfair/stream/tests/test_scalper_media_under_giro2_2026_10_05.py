"""MEDIA UNDER, secondo giro (05/10/2026): i buchi dei test trovati dal revisore.

Spec: ``Betfair/stream/scalper/SPEC_MEDIA_UNDER_GIRO2_2026-10-05.md`` par.2.1.
Stesso banco dei test del primo giro (``banco_media_under.BancoMedia``: flumine
VERO col client paper della sessione, strategia VERA, book nativi di Betfair,
esecuzione differita di 1 e 4 book, minimi .it del banco).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

from typing import Any, List

import pytest

from Betfair.stream.backtest import minimi_banco as MB
from Betfair.stream.scalper import media_under_bot as MU
from Betfair.stream.tennis_live.tests.test_cantiere_t_pro_residuo_2026_09_28 import (  # noqa: F401
    esecuzione_differita,
)
from Betfair.stream.tests.banco_media_under import BancoMedia, giri


@pytest.fixture(params=[1, 4])
def differita(request, esecuzione_differita):
    """Esecuzione dei pacchetti di flumine differita di 1 e di 4 book."""
    esecuzione_differita.ritardo = request.param
    return esecuzione_differita


@pytest.fixture
def exchange_it():
    with MB.minimi_it_su_flumine() as registro:
        yield registro


def _banche(b: BancoMedia) -> List[Any]:
    return [o for o in b.ordini() if MU._lato(o) == "LAY"]


def _punte(b: BancoMedia) -> List[Any]:
    return [o for o in b.ordini() if MU._lato(o) == "BACK"]


# ===========================================================================
# 2.1 a) quota salita MENO di N tick dall'ultimo ingresso: la banca resta
# ===========================================================================
def test_quota_su_di_meno_di_n_tick_la_banca_resta_ferma(differita, exchange_it):
    """Punta 10 @1,50, banca 10,14 @1,48. La quota sale di UN tick (1,51) e ci
    resta 40 book: nessun annullo, nessun ordine nuovo, sempre la stessa banca
    viva, stato IN_POSIZIONE a ogni book (N tick di rientro = 2)."""
    b = BancoMedia()
    viol = giri(b, differita, 70)
    assert viol == [], viol[:3]
    banca = b.vivi("LAY")[0]
    n_ordini = len(b.ordini())
    annulli = len(b.kinds("media_annullo"))
    b.ladder[b.under] = (1.51, 1.52)
    for i in range(40):
        viol += giri(b, differita, 1)
        assert b.strat.stato == MU.IN_POSIZIONE, (i, b.strat.stato)
        assert b.vivi("LAY") == [banca], i
    assert viol == [], viol[:3]
    assert len(b.kinds("media_annullo")) == annulli
    assert len(b.ordini()) == n_ordini
    assert b.kinds("media_rientro") == []
    assert float(banca.size_remaining) == pytest.approx(10.14)


# ===========================================================================
# 2.1 b) punta abbinata in due tempi: la banca si riallinea alla posizione vera
# ===========================================================================
def test_punta_abbinata_in_due_tempi_la_banca_si_riallinea(differita, exchange_it):
    """Rientro a 1,52 (punta 10,00) con solo 4 sul book a quel prezzo: si
    abbina 4, la banca va sulla posizione di quel momento (10 @1,50 + 4 @1,52).
    Poi gli scambi a 1,52 abbinano il resto: la banca vecchia si annulla, si
    aspetta che sia morta, la nuova e' per la posizione vera (20 puntati). Mai
    due banche vive insieme (invarianti del banco a ogni book)."""
    b = BancoMedia()
    viol = giri(b, differita, 70)
    b.taglie[(b.under, 1.52)] = 4.0
    b.ladder[b.under] = (1.52, 1.53)
    for _i in range(30):
        viol += giri(b, differita, 1, flusso=0.0)
        punte = _punte(b)
        if len(punte) == 2 and float(punte[1].size_matched) > 0 and len(_banche(b)) == 2 \
                and MU.eseguibile(_banche(b)[1]):
            break
    assert viol == [], viol[:3]
    punta = _punte(b)[1]
    assert (float(punta.order_type.price), float(punta.order_type.size)) == (1.52, 10.0)
    assert float(punta.size_matched) == pytest.approx(4.0)
    prima = _banche(b)[1]
    pos_parziale = MU.posizione_da_ordini([o for o in b.ordini() if o is not prima])
    assert float(prima.order_type.price) == 1.50
    assert float(prima.order_type.size) == pytest.approx(
        MU.al_centesimo(MU.banca_esatta(pos_parziale, 1.50)))
    # gli scambi a 1,52 abbinano il resto della punta
    b.scambia(b.under, 1.52, 2000)
    viol += giri(b, differita, 12, flusso=0.0)
    assert viol == [], viol[:3]
    assert float(punta.size_matched) == pytest.approx(10.0)
    assert not MU.vivo_o_in_volo(prima)
    assert float(prima.size_matched) == 0.0
    riallinea = [p for p in b.kinds("media_annullo")
                 if str(p.get("motivo", "")).startswith("banca da riallineare")]
    assert len(riallinea) == 1
    vive = b.vivi("LAY")
    pos = b.posizione()
    assert pos.puntato == pytest.approx(20.0)
    assert [(float(o.order_type.price), float(o.size_remaining)) for o in vive] == [
        (1.50, MU.al_centesimo(MU.banca_esatta(pos, 1.50)))]
    assert float(vive[0].order_type.size) == pytest.approx(20.13)
