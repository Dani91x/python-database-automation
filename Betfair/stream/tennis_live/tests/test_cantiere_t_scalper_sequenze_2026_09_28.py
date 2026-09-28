"""CANTIERE T (28/09) - scalper tennis: uscite esatte senza cascata e senza
posizione "chiusa" con un ordine ancora vivo (controllo K6 del banco).

Reperto del coordinatore (replay 35794049, scenari live e gate-aperto, D2
`8ada778`): K6 x10 "la posizione e' dichiarata chiusa ma l'ordine ... e' ancora
'Pending' sul book per 2.0" (il PARCHEGGIO del place-and-trim) e 16.613 azioni
contro 228/245 di prima di D2.

Qui il bot VERO riceve book veri dal Flumine del runner paper (stesso banco di
`test_cantiere_d2_chiusure_via_bot_2026_09_28.py`) e li processa con la sua
`process_market_book`: il test non chiama mai `_drive_submins` ne'
`_drive_flatten`. A OGNI book si verifica l'invariante di K6: se lo slot e'
IDLE o DONE nessun ordine della strategia e' vivo a mercato e nessuna sequenza
e' in corso.
"""
from __future__ import annotations

from typing import Any, List, Tuple

import pytest

from Betfair.stream.tennis_live.tests.test_cantiere_d2_chiusure_esatte_2026_09_28 import (  # noqa: F401
    esecuzione_sincrona,
)
from Betfair.stream.tennis_live.tests.test_cantiere_d2_chiusure_via_bot_2026_09_28 import (
    _netto,
    _nessun_vivo,
)
from Betfair.stream.tennis_live.tests.test_cantiere_t_pro_residuo_2026_09_28 import (  # noqa: F401
    esecuzione_differita,
)
from Betfair.stream.tennis_live.tests.test_tennis_iscrizione_a_caldo_2026_09_25 import (  # noqa: F401
    _banco,
    _control,
    _follow,
    banchi,
    db,
)
from Betfair.stream.tennis_scalper import tennis_scalper_bot as TSB
from Betfair.stream.tennis_scalper import condotta_ordini as CD
from Betfair.stream.tennis_scalper.condotta_ordini import sbilancio_selezione

N_BOOK = 40


@pytest.fixture(params=[1, 4])
def differita(request, esecuzione_differita):
    """Latenza di 1 e di 4 book (bet delay e coda del banco piu' lunghi)."""
    esecuzione_differita.ritardo = request.param
    return esecuzione_differita


def _scalper_in_flatten(db: Any, banchi: Any, size_lay: float) -> Tuple[Any, Any, Any, Any, List]:
    """Scalper tennis del runner paper (uscite esatte dal runner), ingressi
    spenti coi soli numeri della UI, una posizione LAY ABBINATA @2,10 nello
    slot e il flatten avviato come dopo uno stop."""
    ctl = _control("101", "tennis_scalper", status="running")
    ctl["params"] = {"min_size": 1e12, "min_flow": 1e12, "exact_exits": True}
    db.controls = [ctl]
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    strat = b.session.hosted[("101", "tennis_scalper")]
    assert strat.exact_exits is True
    righe: List = []
    strat.event_sink = lambda kind, payload: righe.append((kind, dict(payload)))
    market = b.fw.markets.markets["1.101"]
    o = b.posizione("101", "tennis_scalper", lato="LAY", prezzo=2.10, size=size_lay)
    slot = strat._slot("1.101", 11)
    slot.entry = o
    slot.entry_side = "LAY"
    strat._begin_flatten(slot)
    return b, strat, market, slot, righe


def _giri_con_invariante(b: Any, strat: Any, slot: Any, n: int = N_BOOK,
                         svuota: Any = None) -> List[str]:
    """Book al bot; ritorna le violazioni dell'invariante K6 viste a ogni book.
    ``svuota``: esegue i pacchetti in attesa (latenza di un book)."""
    violazioni: List[str] = []
    for i in range(n):
        if svuota is not None:
            svuota()
        b.book("101")
        market = b.fw.markets.markets["1.101"]
        if strat.check_market_book(market, market.market_book):
            strat.process_market_book(market, market.market_book)
        if slot.status in (TSB.IDLE, TSB.DONE):
            vivi = _nessun_vivo(market, strat)
            if vivi or slot.submins:
                violazioni.append("book %d: stato %s, vivi=%s, sequenze=%d" % (
                    i, slot.status,
                    [(x.side, float(x.order_type.price), float(x.size_remaining))
                     for x in vivi], len(slot.submins)))
            # invariante di K5: la tolleranza e' quella che il bot DICHIARA al
            # banco (`certificazione_bot.credenze`, ciclo chiuso)
            tol = CD.MINIMO_LATO["LAY"] if slot.residual_ok else CD.RESIDUO_ACCETTATO
            sb = sbilancio_selezione(market, strat, 11)
            if sb is None or sb > max(0.011, tol):
                violazioni.append("book %d: stato %s con sbilancio %s oltre %s" % (
                    i, slot.status, sb, tol))
    return violazioni


@pytest.mark.parametrize("size_lay", [1.0, 2.0])
def test_chiusura_tutta_sotto_il_minimo_non_dichiara_chiuso_col_parcheggio_vivo(
        size_lay, db, banchi, differita):
    """LAY 1,00 @2,10: il flatten e' un BACK 1,05 al best-back 2,00, tutto
    sotto il minimo -> tutto col place-and-trim. LAY 2,00: 2,00 diretti, poi
    il resto 0,10 (peggior esito -0,20, dentro la soglia del micro-residuo).
    Prima: `_place_exact` tornava None pur avendo AVVIATO la sequenza,
    `_drive_flatten` accettava il "micro-residuo" e lo slot andava DONE col
    parcheggio da 2,00 ancora vivo (K6)."""
    b, strat, market, slot, _r = _scalper_in_flatten(db, banchi, size_lay)
    viol = _giri_con_invariante(b, strat, slot, svuota=differita)
    assert viol == [], viol[:3]
    # chiusura ESATTA: se vince = se perde al centesimo, niente vivo
    nw, nl = _netto(market, strat)
    assert abs(nw - nl) <= 0.01, (nw, nl)
    assert _nessun_vivo(market, strat) == []
    assert slot.status in (TSB.IDLE, TSB.DONE)
    # il residuo NON e' stato "accettato": e' stato chiuso
    assert slot.residual_ok is False


def test_chiusura_diretta_piu_resto_esatta_e_senza_cascata_di_righe(
        db, banchi, differita):
    """LAY 3,00 @2,10: flatten BACK 3,15 = 3,00 diretti + 0,15 di resto. Il
    resto in FLATTENING e' rimandato (regola anti-cascata, invariata) e poi
    chiuso col place-and-trim. Le righe di attivita' per l'uscita restano
    poche: prima `min_bet_skip` usciva a OGNI book (cascata di azioni)."""
    b, strat, market, slot, righe = _scalper_in_flatten(db, banchi, 3.0)
    viol = _giri_con_invariante(b, strat, slot, n=200, svuota=differita)
    assert viol == [], viol[:3]
    nw, nl = _netto(market, strat)
    assert abs(nw - nl) <= 0.01, (nw, nl)
    assert _nessun_vivo(market, strat) == []
    skip = [r for r in righe if r[0] == "min_bet_skip"]
    assert len(skip) <= 3, (len(skip), skip[:5])
    assert len(righe) <= 40, (len(righe), [k for k, _ in righe][:40])


def test_rinvio_anti_cascata_sull_orologio_del_mercato(db, banchi, esecuzione_sincrona,
                                                      monkeypatch):
    """La pausa di 30 s fra due sequenze si misura sull'orologio del MERCATO
    del bot (`publish_time`), come `UsciteEsatte` di pro/FLB/swing e come il
    tetto transazioni (17/09): mai sull'orologio del PC, che in replay e in
    paper accelerato scorre diversamente dal mercato."""
    b, strat, market, slot, _r = _scalper_in_flatten(db, banchi, 1.0)
    b.book("101")
    m = b.fw.markets.markets["1.101"]
    strat.process_market_book(m, m.market_book)
    assert slot.t_last_submin == strat._now_ms, (slot.t_last_submin, strat._now_ms)


def test_piatta_con_un_ordine_dello_slot_vivo_non_si_dichiara_chiusa(
        db, banchi, differita):
    """Posizione gia' piatta (LAY 1,00 @2,10 + BACK 1,05 @2,00 abbinati) ma nello
    slot resta un ordine VIVO a quota non abbinabile (BACK 2,00 @1000, come il
    parcheggio di una sequenza finita male): prima lo slot andava DONE con
    quell'ordine a mercato (K6). Ora si ritira e si dichiara chiusa dopo."""
    b, strat, market, slot, _r = _scalper_in_flatten(db, banchi, 1.0)
    chiusura = b.posizione("101", "tennis_scalper", lato="BACK", prezzo=2.0, size=1.05)
    slot.flatten_orders.append(chiusura)
    vivo = strat._place(market, 11, "BACK", 1000.0, 2.0, floor_min=False, slot=None)
    assert vivo is not None
    slot.flatten_orders.append(vivo)
    viol = _giri_con_invariante(b, strat, slot, n=10, svuota=differita)
    assert viol == [], viol[:3]
    assert slot.status in (TSB.IDLE, TSB.DONE)
    assert _nessun_vivo(market, strat) == []


def test_parcheggio_ritirato_prima_del_taglio_non_blocca_la_sorveglianza(db, banchi, differita):
    """Il parcheggio di una sequenza viene ritirato da un'altra via prima del
    taglio (sorveglianza LOCKING, fine finestra) e lo slot e' DONE. Prima la
    sequenza restava in PLACED per sempre (`advance_submin` aspetta), lo slot
    DONE saltava la sorveglianza (`if slot.submins: continue`) e la posizione
    restava sbilanciata senza padrone: replay 35794049, K5 x7981."""
    b, strat, market, slot, _r = _scalper_in_flatten(db, banchi, 1.0)
    # un book fa partire la sequenza (parcheggio chiesto); il parcheggio arriva
    # a mercato e, PRIMA che il bot chieda il taglio, lo ritira un'altra via
    b.book("101")
    m = b.fw.markets.markets["1.101"]
    strat.process_market_book(m, m.market_book)
    assert slot.submins, "la sequenza deve essere partita"
    park = slot.submins[0]["order"]
    assert park is not None and float(park.order_type.price) == 1000.0
    for _ in range(differita.ritardo):
        differita()
    assert park.bet_id is not None
    m.cancel_order(park)                       # ritirato da un'altra via
    for _ in range(differita.ritardo):
        differita()
    assert not strat._has_live(park)
    assert str(slot.submins[0]["state"].step.value) == "placed"
    slot.status = TSB.DONE                     # dichiarato chiuso da un altro ramo
    viol = _giri_con_invariante(b, strat, slot, svuota=differita)
    assert viol == [], viol[:3]
    assert not slot.submins
    assert slot.status == TSB.FLATTENING, "la posizione si governa di nuovo"


def test_locking_non_chiude_il_ciclo_con_un_parcheggio_ancora_pending(db, banchi, differita):
    """LOCKING: ingresso BACK 2,00 @2,10 e close LAY 2,00 @2,10 abbinate (ciclo
    pari), ma nello slot resta un parcheggio BACK 2,00 @1000 ancora PENDING (il
    cancel su un ordine senza bet_id fallisce). Prima lo slot andava DONE con
    il parcheggio vivo (K6); ora aspetta che il cancel ritentato lo uccida."""
    b, strat, market, slot, _r = _scalper_in_flatten(db, banchi, 2.0)
    slot.status = TSB.LOCKING
    slot.entry_side = "BACK"
    slot.entry = b.posizione("101", "tennis_scalper", lato="BACK", prezzo=2.10, size=2.0)
    slot.flatten_orders = []
    # la close: il LAY abbinato che pareggia l'ingresso BACK
    slot.close = b.posizione("101", "tennis_scalper", lato="LAY", prezzo=2.10, size=2.0)
    # il LAY 2,00 di `_scalper_in_flatten` resta fuori dallo slot: lo pareggia
    # un BACK 2,00 @2,10 anch'esso fuori (la selezione resta pari)
    b.posizione("101", "tennis_scalper", lato="BACK", prezzo=2.10, size=2.0)
    park = strat._place(market, 11, "BACK", 1000.0, 2.0, floor_min=False, slot=None)
    assert park is not None
    slot.flatten_orders.append(park)
    viol = _giri_con_invariante(b, strat, slot, n=12, svuota=differita)
    assert viol == [], viol[:3]
    assert slot.status in (TSB.IDLE, TSB.DONE)
    assert _nessun_vivo(market, strat) == []


def test_sequenza_abortita_non_lascia_il_parcheggio_vivo(db, banchi, differita,
                                                        monkeypatch):
    """Una sequenza che ABORTISCE dopo aver piazzato il parcheggio (es. taglio
    mai osservato, guardia del rischio) non lascia il parcheggio da 2,00 a
    mercato: il bot lo ritira, poi chiude la posizione. Prima restava vivo e il
    flatten, che salta i parcheggi per design, lo aspettava per sempre."""
    import dataclasses

    from Betfair.stream.trading import submin as SM

    vero = SM.advance_submin
    chiamate = [0]

    def _abortisce_al_secondo_passo(market, state, **kw):
        chiamate[0] += 1
        if chiamate[0] == 2:
            return dataclasses.replace(state, step=SM.SubminStep.ABORTED,
                                       note="ABORT finto del test")
        return vero(market, state, **kw)
    monkeypatch.setattr(SM, "advance_submin", _abortisce_al_secondo_passo)
    b, strat, market, slot, righe = _scalper_in_flatten(db, banchi, 1.0)
    viol = _giri_con_invariante(b, strat, slot, svuota=differita)
    assert viol == [], viol[:3]
    assert chiamate[0] >= 2
    # il flatten ritenta a ogni book e l'anti-cascata lo rimanda: il motivo
    # si scrive UNA volta per importo, non a ogni book (la cascata di azioni
    # del replay). L'importo cambia solo col gradino di aggressivita' del
    # flatten (`cross`, tetto 8): al piu' 9 righe, qualunque sia il numero di book.
    skip = [r for r in righe if r[0] == "min_bet_skip"]
    assert len(skip) <= 9, len(skip)
    assert len({r[1]["size"] for r in skip}) == len(skip)
    park = [x for x in market.blotter.strategy_orders(strat)
            if float(x.order_type.price) == 1000.0]
    assert park and float(park[0].size_remaining) == 0.0
    assert _nessun_vivo(market, strat) == []
    # l'orologio del mercato del banco e' fermo: la sequenza nuova aspetta i
    # 30 s dell'anti-cascata (regola invariata). La posizione resta GOVERNATA
    # (FLATTENING), mai dichiarata chiusa.
    assert slot.status == TSB.FLATTENING
