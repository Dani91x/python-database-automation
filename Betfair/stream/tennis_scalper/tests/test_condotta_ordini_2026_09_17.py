# -*- coding: utf-8 -*-
"""LA CONDOTTA DEGLI ORDINI — le tre regole comuni ai quattro bot tennis.

Ogni test dimostra la regola E il suo contrario: una regola che non sa dire di
no a un caso e di si' all'altro non e' una regola, e' un caso fortunato
(CLAUDE.md: «un test che non sa diventare rosso non certifica»).

Le regole, con il motivo MISURATO che le ha fatte nascere (referto d'audit
`Betfair/stream/tennis_live/AUDIT_4_BOT_TENNIS_2026-09-17.md`):

  1. `size_legale` — su .it Betfair rifiuta un BACK sotto 2,00 EUR o non
     multiplo di 0,50 e un LAY sotto 0,50: la gamba non parte e la posizione
     resta SCOPERTA. Pro, FLB e Swing non avevano nessuna blindatura.
  2. `FrenoRifiuti` — nel replay del 17/09, con Betfair che rifiutava ogni
     piazzamento, il FLB ha ritentato 8.132 volte e lo scalper 20.534 volte in
     UNA partita.
  3. `sbilancio_selezione` — lo swing ha abbandonato 7,57 EUR su una selezione
     su cui non aveva piu' nessun trade, e il micro-residuo dello scalper non
     era guardato da nessuno una volta riciclato lo slot.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import types

import pytest
from flumine.order.order import OrderStatus

from Betfair.stream.tennis_scalper import condotta_ordini as CD


# ===========================================================================
# 1. la size legale di giurisdizione
# ===========================================================================
def test_fuori_dal_live_la_size_non_si_tocca():
    """In simulazione la granularita' .it non esiste: arrotondare falserebbe il
    confronto fra replay e paper."""
    assert CD.size_legale(0.93, "LAY", live=False) == (0.93, None)
    assert CD.size_legale(2.03, "BACK", live=False) == (2.03, None)


def test_live_ingresso_sotto_il_minimo_non_parte():
    """Un INGRESSO non si gonfia: se non e' legale, non si piazza e si dice
    perche'. Gonfiarlo vorrebbe dire mettere a mercato piu' soldi di quelli che
    l'utente ha acceso."""
    legale, motivo = CD.size_legale(1.50, "BACK", live=True)
    assert legale is None
    assert "minimo" in (motivo or "")


def test_live_ingresso_legale_passa_intatto():
    assert CD.size_legale(2.00, "BACK", live=True) == (2.0, None)
    assert CD.size_legale(0.93, "LAY", live=True) == (0.93, None)


@pytest.mark.parametrize("chiesto,atteso", [
    (0.93, 2.0),    # sotto il minimo BACK -> bumpata al minimo
    (2.00, 2.0),    # gia' legale
    (2.03, 2.5),    # non multipla di 0,50 -> al gradino SOPRA
    (2.50, 2.5),    # gia' multipla: NON deve salire
    (2.60, 3.0),
])
def test_live_copertura_back_si_bumpa_al_gradino_sopra(chiesto, atteso):
    """UNA COPERTURA DEVE PARTIRE: meglio un over-hedge di pochi centesimi che
    una gamba scoperta. Verso il BASSO si tornerebbe sotto la copertura."""
    assert CD.size_legale(chiesto, "BACK", live=True,
                          riduce_liability=True) == (atteso, None)


def test_live_copertura_lay_si_bumpa_al_minimo_di_lato():
    assert CD.size_legale(0.10, "LAY", live=True,
                          riduce_liability=True) == (0.5, None)
    assert CD.size_legale(0.93, "LAY", live=True,
                          riduce_liability=True) == (0.93, None)


def test_size_sotto_il_minimo_tecnico_non_passa_mai():
    legale, motivo = CD.size_legale(0.001, "BACK", live=False)
    assert legale is None and "0,01" in (motivo or "")


# ===========================================================================
# 2. il freno dopo un rifiuto
# ===========================================================================
def test_senza_rifiuti_non_si_frena_niente():
    """LA FALSIFICAZIONE: un freno che blocca anche senza rifiuti spegnerebbe il
    bot su un conto sano."""
    f = CD.FrenoRifiuti()
    assert f.bloccato("1.1", 7, 1000.0) is None


def test_il_backoff_raddoppia_e_conta_il_tempo_di_mercato():
    f = CD.FrenoRifiuti()
    n, attesa = f.registra_rifiuto("1.1", 7, 1000.0)
    assert (n, attesa) == (1, CD.BACKOFF_S[0])
    assert f.bloccato("1.1", 7, 1000.0 + CD.BACKOFF_S[0] - 1) is not None
    # passato il backoff DI MERCATO si riprova
    assert f.bloccato("1.1", 7, 1000.0 + CD.BACKOFF_S[0]) is None
    n2, attesa2 = f.registra_rifiuto("1.1", 7, 1010.0)
    assert (n2, attesa2) == (2, CD.BACKOFF_S[1])
    assert attesa2 > attesa, "il backoff deve CRESCERE, altrimenti non frena"


def test_il_primo_backoff_copre_il_bet_delay_del_tennis():
    """Il betDelay del tennis in gioco e' 5 s (memoria
    `project_validazione_certezza_2026-07-10`): un rifiuto non si ripresenta
    prima che l'esito precedente sia noto."""
    assert CD.BACKOFF_S[0] >= 5.0


def test_il_tetto_ferma_del_tutto_quella_selezione():
    f = CD.FrenoRifiuti(tetto=3)
    for i in range(3):
        f.registra_rifiuto("1.1", 7, 1000.0 + i)
    motivo = f.bloccato("1.1", 7, 1_000_000.0)   # anche molto dopo
    assert motivo is not None and "tetto" in motivo


def test_il_freno_e_per_selezione_non_per_mercato():
    """Un rifiuto su una selezione non deve spegnere l'altra: sono due
    posizioni diverse."""
    f = CD.FrenoRifiuti()
    f.registra_rifiuto("1.1", 7, 1000.0)
    assert f.bloccato("1.1", 7, 1000.0) is not None
    assert f.bloccato("1.1", 8, 1000.0) is None


def test_un_successo_azzera_il_backoff():
    f = CD.FrenoRifiuti()
    f.registra_rifiuto("1.1", 7, 1000.0)
    assert f.bloccato("1.1", 7, 1001.0) is not None
    f.registra_successo("1.1", 7)
    assert f.bloccato("1.1", 7, 1001.0) is None


def test_il_motivo_si_annuncia_una_volta_sola_per_rifiuto():
    """40 rifiuti veri producevano 20.494 righe di attivita': il motivo si dice
    una volta per RIFIUTO, non una per tentativo."""
    f = CD.FrenoRifiuti()
    f.registra_rifiuto("1.1", 7, 1000.0)
    assert f.da_annunciare("1.1", 7) is True
    assert f.da_annunciare("1.1", 7) is False
    f.registra_rifiuto("1.1", 7, 1010.0)      # un rifiuto NUOVO: si ridice
    assert f.da_annunciare("1.1", 7) is True


# ===========================================================================
# 3. lo sbilancio di una selezione, dal blotter
# ===========================================================================
def _ordine(sel, side, matched, avg, stato=OrderStatus.EXECUTION_COMPLETE):
    return types.SimpleNamespace(selection_id=sel, side=side,
                                 size_matched=matched,
                                 average_price_matched=avg, status=stato,
                                 size_remaining=0.0)


class _Blotter:
    def __init__(self, ordini, esplode=False):
        self._o = list(ordini)
        self._esplode = esplode

    def strategy_orders(self, _s):
        if self._esplode:
            raise RuntimeError("blotter non leggibile")
        return list(self._o)


class _Market:
    market_id = "1.1"

    def __init__(self, blotter):
        self.blotter = blotter


def test_posizione_coperta_e_pari():
    """Un lay 2,00 a 1,50 chiuso con un back 2,00 a 1,50: l'esito del mercato
    non cambia piu' il risultato."""
    m = _Market(_Blotter([_ordine(7, "LAY", 2.0, 1.50),
                          _ordine(7, "BACK", 2.0, 1.50)]))
    assert CD.sbilancio_selezione(m, object(), 7) == pytest.approx(0.0, abs=1e-6)


def test_posizione_scoperta_e_sbilanciata():
    """LA FALSIFICAZIONE della precedente: una gamba sola NON e' pari."""
    m = _Market(_Blotter([_ordine(7, "LAY", 2.0, 1.50)]))
    sb = CD.sbilancio_selezione(m, object(), 7)
    assert sb is not None and sb > 0.5


def test_un_blotter_illeggibile_non_e_una_posizione_piatta():
    """Un'esposizione NON letta non e' un'esposizione nulla: e' il difetto che
    faceva dichiarare piatta una posizione ancora aperta."""
    m = _Market(_Blotter([], esplode=True))
    assert CD.sbilancio_selezione(m, object(), 7) is None
    assert CD.piatta(m, object(), 7, tolleranza=1000.0) is False


def test_le_altre_selezioni_non_contano():
    m = _Market(_Blotter([_ordine(8, "LAY", 50.0, 3.00)]))
    assert CD.sbilancio_selezione(m, object(), 7) == pytest.approx(0.0, abs=1e-6)


# ===========================================================================
# 4. lo stato di un ordine, letto come Enum
# ===========================================================================
def test_lo_stato_si_legge_dal_valore_dell_enum():
    o = _ordine(7, "LAY", 0.0, 0.0, stato=OrderStatus.EXECUTABLE)
    assert CD.stato_ordine(o) == "Executable"
    assert CD.ordine_vivo(o) is True


def test_un_ordine_terminale_senza_abbinato_e_un_ingresso_finito():
    """E' il caso della persistenza LAPSE: Betfair uccide l'appoggiato alla
    sospensione, cioe' a ogni punto del tennis. Aspettare il timeout su un
    ordine che non esiste piu' e' cecita'."""
    o = _ordine(7, "LAY", 0.0, 0.0, stato=OrderStatus.EXPIRED)
    assert CD.ingresso_finito(o) is True


def test_un_ordine_vivo_non_e_finito():
    o = _ordine(7, "LAY", 0.0, 0.0, stato=OrderStatus.EXECUTABLE)
    assert CD.ingresso_finito(o) is False


def test_un_ordine_terminale_ma_ABBINATO_non_e_un_ingresso_finito():
    """LA FALSIFICAZIONE che conta di piu': se `ingresso_finito` dicesse si'
    anche a un ordine abbinato, il bot butterebbe via una posizione VERA."""
    o = _ordine(7, "LAY", 2.0, 1.08, stato=OrderStatus.EXECUTION_COMPLETE)
    assert CD.ingresso_finito(o) is False


def test_un_ordine_mai_piazzato_non_e_un_ingresso_finito():
    """`status is None` = `place_order` ha risposto False: lo gestisce il freno
    dei rifiuti, non la scadenza."""
    o = _ordine(7, "LAY", 0.0, 0.0, stato=None)
    assert CD.ingresso_finito(o) is False
    assert CD.ordine_vivo(o) is False


def test_lo_stato_non_si_legge_MAI_come_stringa():
    """`str(OrderStatus.EXECUTABLE)` da' 'OrderStatus.EXECUTABLE': confrontarlo
    con 'Executable' non matcha mai (catalogo §7.10). Questo test si rompe se
    qualcuno tornasse a `str(...)`."""
    assert str(OrderStatus.EXECUTABLE) != CD.stato_ordine(
        _ordine(7, "LAY", 0.0, 0.0, stato=OrderStatus.EXECUTABLE))
    assert CD.STATI_VIVI == {"Pending", "Cancelling", "Updating", "Replacing",
                             "Executable"}
