"""CANTIERE 15 (08/10) - scalper CALCIO: FILL SIMULTANEI su piu' gambe.

Ordine dell'utente (08/10): «il bot deve reggere fill simultanei su piu' gambe
(nella realta' succede): verificare che la condotta non vada allo scoperto quando
due chiusure si abbinano nello stesso istante». Reperto: 35797769, 17:00:06.704,
le DUE gambe del maker sulla sel 22 (BACK 25 @1,66 e LAY 25 @1,65) abbinate nello
stesso book (li' per un artefatto del banco, la rivalutazione di cambio: vedi
`test_banco_rivalutazione_cambio_2026_10_08.py`; ma nella realta' due gambe
possono abbinarsi nello stesso messaggio).

Il bot VERO (``ScalperStrategy`` coi ``VALIDATED_PARAMS`` della sessione) dentro
un ``Flumine`` VERO col client paper della sessione, book VERI (mcm ->
``StreamListener``), esecuzione dei pacchetti DIFFERITA di 1 e di 4 book: e' il
banco del cantiere S (`test_cantiere_s_scalper_ko_2026_09_29.py`), riusato com'e'.
Gli abbinamenti li fa flumine (coda e volume scambiato del book), mai a mano.

A ogni book: gli invarianti del banco (K5/K6 a slot chiuso, B2 in gioco) e in piu'
MAI SOVRACOPERTURA: dopo il fill simultaneo il netto della selezione non cambia
mai segno oltre la tolleranza dichiarata dal bot (una chiusura doppia rovescerebbe
la posizione). ASCII-only.
"""
from __future__ import annotations

from typing import Any, List

import pytest

from Betfair.stream.scalper import certificazione as CERT
from Betfair.stream.scalper import scalper_bot as SB
from Betfair.stream.tests.test_cantiere_s_scalper_ko_2026_09_29 import (  # noqa: F401
    KO_MS,
    SEL,
    Banco,
    differita,
    esecuzione_differita,
    esposizione_vera,
    invarianti,
    orologio_mercato,
    residuo_dichiarato_ok,
    vivi,
)

PB, PL = 2.22, 2.20          # le due quote del maker (dentro lo spread 2,20/2,22)
STAKE = 25.0


def _primo_fill_ms(o: Any) -> Any:
    m = list(getattr(getattr(o, "simulated", None), "matched", None) or [])
    return m[0][0] if m else None


def _maker_a_riposo(b: Banco, differita: Any) -> Any:
    """Le due gambe del maker piazzate DAL BOT (``_place``) e lo slot in QUOTING2
    come lo lascia ``_enter_maker``; nessuno scambio finche' non sono a riposo."""
    b.senza_scambi.add(SEL)
    b.book()
    slot = b.slot()
    ob = b.strat._place(b.market, SEL, "BACK", PB, STAKE)
    ol = b.strat._place(b.market, SEL, "LAY", PL, STAKE)
    assert ob is not None and ol is not None
    slot.status = SB.QUOTING2
    slot.entry_back, slot.entry_lay = ob, ol
    slot.t_quote = b.pt
    slot.ref_price = (PB + PL) / 2.0
    for _ in range(6):
        differita()
        b.book()
    assert SB.ScalperStrategy._has_live(ob) and SB.ScalperStrategy._has_live(ol)
    assert float(ob.size_matched) == 0.0 and float(ol.size_matched) == 0.0
    return slot


def _segui(b: Banco, differita: Any, n: int, segno0: float) -> List[str]:
    """``n`` book con gli invarianti del banco e il controllo di sovracopertura."""
    viol: List[str] = []
    for i in range(n):
        differita()
        b.book()
        viol += invarianti(b, i)
        w, l = esposizione_vera(b.market, b.strat)
        tol = CERT.tolleranza_slot(b.slot())
        if (w - l) * segno0 < -(tol + 1e-6):
            viol.append("book %d SOVRACOPERTURA: netto %.2f (w %.2f, l %.2f) di segno "
                        "opposto alla posizione aperta dal fill simultaneo, tolleranza %.2f"
                        % (i, w - l, w, l, tol))
    return viol


def _fine_pulita(b: Banco) -> None:
    # nessuna riconciliazione d'emergenza: il bot non si e' mai creduto chiuso con
    # la posizione aperta (il monitor DONE l'avrebbe "guarita" dopo: CRITICAL)
    assert not [k for k, _p in b.righe if k in ("ledger_divergence", "recon_freeze")], \
        [r for r in b.righe if r[0] in ("ledger_divergence", "recon_freeze")]
    slot = b.slot()
    w, l = esposizione_vera(b.market, b.strat)
    assert residuo_dichiarato_ok(b, w, l), (w, l, b.righe[-12:])
    assert vivi(b.market, b.strat) == [], [(o.side, o.order_type.price, o.size_remaining)
                                           for o in vivi(b.market, b.strat)]
    assert not slot.submins
    assert slot.status in (SB.IDLE, SB.DONE), slot.status


@pytest.mark.parametrize("lay_scambiato", [200.0, 110.0], ids=["intere", "lay-in-parte"])
def test_due_gambe_del_maker_abbinate_nello_stesso_book(lay_scambiato, differita,
                                                        orologio_mercato):
    """Le DUE gambe del maker si abbinano nello STESSO book (intere, oppure la LAY
    solo in parte). Il bot ritira i residui, chiude il netto (green-up, scavalco e
    chiusura al centesimo se serve) e torna libero: mai uno slot chiuso con
    l'esposizione aperta, mai un ordine vivo a slot chiuso, mai la posizione
    rovesciata da una chiusura di troppo."""
    b = Banco()
    orologio_mercato["banco"] = b
    b.pt = KO_MS - 3_000_000          # lontano dal fischio: niente finestre pre-KO
    slot = _maker_a_riposo(b, differita)
    ob, ol = slot.entry_back, slot.entry_lay
    # UN book con lo scambio alle due quote: flumine abbina tutte e due le gambe
    b.senza_scambi.discard(SEL)
    tv = b.trd.setdefault(SEL, {})
    tv[PB] = tv.get(PB, 0.0) + 200.0
    tv[PL] = tv.get(PL, 0.0) + lay_scambiato
    differita()
    b.book()
    assert float(ob.size_matched) > 0 and float(ol.size_matched) > 0
    assert _primo_fill_ms(ob) == _primo_fill_ms(ol), "precondizione: stesso book"
    if lay_scambiato < 200.0:
        assert float(ol.size_matched) < STAKE, "precondizione: LAY abbinata in parte"
    w0, l0 = esposizione_vera(b.market, b.strat)
    assert abs(w0 - l0) > 0.02, "precondizione: posizione da chiudere"
    # gli invarianti valgono gia' sul book del fill simultaneo
    viol = invarianti(b, -1)
    viol += _segui(b, differita, 200, 1.0 if w0 > l0 else -1.0)
    assert viol == [], viol[:3]
    _fine_pulita(b)


def test_close_e_aggiunta_della_predimensione_abbinate_nello_stesso_book(differita,
                                                                       orologio_mercato):
    """Due CHIUSURE dello stesso ciclo abbinate nello stesso istante: entra la
    BACK del maker, la LAY opposta diventa la close e la pre-dimensione le affianca
    un'AGGIUNTA alla stessa quota (banca diretta al centesimo, close ridotta di
    1,00). Uno scambio a 2,20 le abbina insieme: il ciclo chiude piatto (verde
    simmetrico) e nessuna chiusura in piu' parte dopo."""
    b = Banco()
    orologio_mercato["banco"] = b
    b.pt = KO_MS - 3_000_000
    slot = _maker_a_riposo(b, differita)
    b.senza_scambi.discard(SEL)
    tv = b.trd.setdefault(SEL, {})
    tv[PB] = tv.get(PB, 0.0) + 200.0
    tv[PL] = tv.get(PL, 0.0) - 20.0           # il book aggiunge 20: a 2,20 nessuno scambio
    differita()
    b.book()
    b.senza_scambi.add(SEL)
    for _ in range(8):                        # LOCKING + pre-dimensione a riposo
        differita()
        b.book()
    assert slot.status == SB.LOCKING, slot.status
    chiusure = [o for o in b.market.blotter.strategy_orders(b.strat)
                if o.side == "LAY" and float(o.order_type.price) == PL
                and SB.ScalperStrategy._has_live(o)]
    assert len(chiusure) == 2, "precondizione: close + aggiunta vive alla stessa quota"
    b.senza_scambi.discard(SEL)
    tv[PL] = tv.get(PL, 0.0) + 400.0
    tv[PB] = tv.get(PB, 0.0) - 20.0
    differita()
    b.book()
    assert all(float(o.size_matched) > 0 for o in chiusure)
    assert len({_primo_fill_ms(o) for o in chiusure}) == 1, "precondizione: stesso book"
    viol = invarianti(b, -1)
    viol += _segui(b, differita, 120, 1.0)
    assert viol == [], viol[:3]
    _fine_pulita(b)
    w, l = esposizione_vera(b.market, b.strat)
    assert abs(w - l) <= 0.02 + 1e-9, (w, l)
