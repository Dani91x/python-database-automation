"""CANTIERE S3 (29/09) - bot VERI su Flumine vero (client paper, esecuzione
differita di 1 e 4 book), come i test S e S-bis.

1. La riga CRITICAL `flatten_bloccato` (scalper e sniper) esce SOLO quando la
   chiusura e' bloccata davvero: prezzo del lato assente, oppure chiusura
   piazzabile direttamente che non parte (rifiutata). NON durante la pausa
   prevista di 30 s fra due sequenze place-and-trim, quando il resto sotto il
   minimo si chiudera' con la sequenza successiva (falso allarme visto sul
   replay 35797769, sniper: CRITICAL a nw 0,30, poi `sniper_flat`). Il bot fa
   la stessa cosa di prima: ritenta, non accetta residui.
2. Sniper: un ordine in REPLACING (rimpiazzo chiesto, sostituto non ancora nato)
   tiene la posizione: nessuna chiusura nuova sopra di lui (gemello di
   `test_done_non_riparte_con_un_rimpiazzo_in_volo` dello scalper).
"""
from __future__ import annotations

from typing import Any, List, Tuple

from Betfair.stream.tests import test_cantiere_s_bis_sniper_2026_09_29 as SNT
from Betfair.stream.tests import test_cantiere_s_scalper_ko_2026_09_29 as SCT
from Betfair.stream.tests.test_cantiere_s_bis_sniper_2026_09_29 import (  # noqa: F401
    differita,
    esecuzione_differita,
    orologio_mercato,
)


def _critical(righe: List[Tuple[str, Any]]) -> List[Any]:
    return [r for r in righe if r[0] == "flatten_bloccato"]


# ---------------------------------------------------------------- scalper
def test_scalper_nessun_critical_nella_pausa_fra_due_sequenze(differita, orologio_mercato):
    """LAY 0,50 @2,22: la chiusura e' un BACK ~0,50, tutto sotto il minimo:
    place-and-trim. Una sequenza e' appena partita (pausa di 30 s in corso):
    il flatten ritenta a ogni giro (oltre 12 tentativi) e la sequenza dopo
    chiude. Prima usciva un CRITICAL per una pausa prevista."""
    b = SCT._in_flatten("LAY", 2.22, 0.5)
    orologio_mercato["banco"] = b
    slot = b.slot()
    slot.t_last_submin = b.pt                    # pausa di 30 s appena iniziata
    viol: List[str] = []
    for i in range(80):
        differita()
        b.book()
        viol += SCT.invarianti(b, i)
        if slot.status == SCT.SB.DONE:
            # ci si ferma alla chiusura DICHIARATA: un micro-residuo accettato
            # (<= 0,25, regola di strategia) viene poi dimenticato dal reset
            # del ciclo dopo; e' una decisione aperta per l'utente (referto S
            # par. 7), fuori dal perimetro di questo test
            break
    assert viol == [], viol[:3]
    assert slot.status == SCT.SB.DONE, slot.status
    assert slot.flat_tries > 12
    assert _critical(b.righe) == [], _critical(b.righe)
    w, l = SCT.esposizione_vera(b.market, b.strat)
    assert abs(w - l) <= SCT.CERT.tolleranza_slot(slot) + 1e-9, (w, l, slot.status)


def test_scalper_critical_una_volta_a_prezzi_assenti(differita, orologio_mercato):
    """Prezzi del lato di chiusura ASSENTI su una posizione piazzabile (LAY 25):
    la chiusura e' bloccata davvero: UNA riga CRITICAL, lo slot resta in
    chiusura e chiude quando i prezzi tornano."""
    b = SCT._in_flatten("LAY", 2.22, 25.0)
    orologio_mercato["banco"] = b
    slot = b.slot()
    viol = SCT.giri(b, differita, 30, muto_prezzi=True)
    assert viol == [], viol[:3]
    assert len(_critical(b.righe)) == 1, _critical(b.righe)
    assert slot.status == SCT.SB.FLATTENING
    viol = SCT.giri(b, differita, 60)
    assert viol == [], viol[:3]
    assert slot.status in (SCT.SB.IDLE, SCT.SB.DONE)
    # 07/10 (decisione dell'utente "1) b"): il resto sotto 0,50 lasciato dalla
    # chiusura inseguita si chiude con lo scavalco + la chiusura al centesimo
    # (misura: DONE in 8 giri a latenza 1, 17 a latenza 4; prima 5 e 9 ma con
    # 0,18 di residuo dichiarato)
    w, l = SCT.esposizione_vera(b.market, b.strat)
    assert abs(w - l) <= 0.02, (w, l)


# ---------------------------------------------------------------- sniper
def test_sniper_nessun_critical_nella_pausa_fra_due_sequenze(differita, orologio_mercato):
    """BACK Under 0,70 @1,50: chiusura LAY ~0,70 sotto il minimo diretto,
    pausa di 30 s fra due sequenze in corso: niente CRITICAL, la sequenza dopo
    chiude. 04/10 (regola dell'utente): prima BACK 0,40 -> banca 0,40, oggi sotto
    0,50 (residuo dichiarato, nessuna sequenza): la pausa fra sequenze si prova
    con 0,70 (banca fra 0,50 e 1,00 = place-and-trim)."""
    b = SNT._in_chiusura(0.7)
    orologio_mercato["banco"] = b
    pos = b.pos()
    pos.t_last_submin = b.pt
    viol = SNT.giri(b, differita, 80)
    assert viol == [], viol[:3]
    assert pos.flat_tries > 12
    assert _critical(b.righe) == [], _critical(b.righe)
    assert SNT.chiusa(pos)
    w, l = SNT.esposizione_vera(b)
    assert abs(w - l) <= SNT.tolleranza(pos) + 1e-9, (w, l)


def test_sniper_un_rimpiazzo_in_volo_tiene_la_posizione(differita, orologio_mercato):
    """Posizione BACK 2,00 @1,50 in chiusura; la sua chiusura e' un parcheggio
    LAY 2,00 @1,01 il cui RIMPIAZZO a 1,51 e' chiesto e non ancora eseguito
    (stato Replacing): il sostituto nascera' a mercato e chiudera'. Prima
    (Replacing contato come morto) lo sniper piazzava una SECONDA chiusura:
    col sostituto abbinato, posizione ROVESCIATA."""
    b = SNT.BancoSniper()
    orologio_mercato["banco"] = b
    b.book()
    pos = b.pos()
    park = b.strat._place(b.market, SNT.UNDER, "LAY", 1.01, 2.0, floor=False, pos=None)
    assert park is not None
    for _ in range(differita.ritardo):
        differita()
    assert str(park.status.value) == "Executable"
    pos.entries = [b.abbinato("BACK", 1.5, 2.0)]
    b.strat._begin_flatten(b.market, pos)
    b.strat._track(pos, park)
    b.market.replace_order(park, 1.51)            # rimpiazzo IN VOLO
    assert str(park.status.value) == "Replacing"
    rovesciata: List[Any] = []
    viol: List[str] = []
    for i in range(60):
        if i >= 1:
            differita()
        b.book()
        viol += SNT.invarianti(b, i)
        w, l = SNT.esposizione_vera(b)
        # posizione LONG iniziale: una chiusura doppia la rende SHORT
        if l - w > SNT.tolleranza(pos) + 1e-6:
            rovesciata.append((i, round(w, 2), round(l, 2)))
    assert viol == [], viol[:3]
    assert rovesciata == [], rovesciata[:3]
    sost = [o for o in park.trade.orders if o is not park]
    assert sost and float(sost[0].size_matched) > 0, "il sostituto deve chiudere"
    assert SNT.chiusa(pos)


def test_sniper_resto_sotto_5_centesimi_non_resta_in_chiusura_per_sempre(
        differita, orologio_mercato):
    """Under a quota alta (8,0): BACK 0,04 abbinato, sbilancio 0,32 (oltre il
    micro-residuo 0,30), chiusura LAY ~0,04: sotto 0,05 NON avvia mai una
    sequenza (`_place_exact`: `min_bet_skip`), quindi il tetto delle sequenze
    non si raggiunge mai. Prima la ULTIMA SPIAGGIA aspettava quel tetto e la
    posizione restava in chiusura PER SEMPRE; ora il resto si accetta come
    prima di S-bis (dichiarato), senza CRITICAL."""
    b = SNT.BancoSniper()
    orologio_mercato["banco"] = b
    b.ladder[SNT.UNDER] = (8.0, 8.2)
    b.book()
    pos = b.pos()
    pos.entries = [b.abbinato("BACK", 8.0, 0.04)]
    b.strat._begin_flatten(b.market, pos)
    for i in range(40):
        differita()
        b.book()
        if SNT.chiusa(pos):
            break
    assert SNT.chiusa(pos), "la posizione non deve restare in chiusura per sempre"
    assert [r for r in b.righe if r[0] == "sniper_flat_forced"]
    assert _critical(b.righe) == []
