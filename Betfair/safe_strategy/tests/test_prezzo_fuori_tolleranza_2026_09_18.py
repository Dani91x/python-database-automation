# -*- coding: utf-8 -*-
"""``proposte_opportunita.prezzo_fuori_tolleranza`` — bordi (18/09/2026,
secondo giro).

BUCO TROVATO dal coordinatore: la mutazione «prezzo attuale non valido ->
FAIL-OPEN (``return False`` invece di ``return True``)» girava con 206 test
verdi, NESSUNO rosso. La funzione pura non aveva test propri sui bordi — i
test di ``test_combos_anomalie_proposte_2026_09_18.py`` la esercitano sempre
con prezzi VALIDI (dentro o fuori tolleranza), mai con ``None``/bool/stringa/
``<=1.0``/lato invalido. Questo file chiude quel buco: un test per OGNI ramo
di guardia (fail-closed) e per il confine esatto della soglia (``>``, non
``>=``).

ASCII-only nel codice, commenti in italiano.
"""
from __future__ import annotations

import math

import pytest

from Betfair.safe_strategy.proposte_opportunita import (
    SLIPPAGE_PCT_DEFAULT, prezzo_fuori_tolleranza,
)


# ===========================================================================
# 1. PREZZO DI DECISIONE non valido -> SEMPRE fuori tolleranza (fail-closed)
# ===========================================================================
@pytest.mark.parametrize("prezzo_decisione", [
    None, True, False, "2.2", [2.2], {}, 1.0, 0.5, -1.0, 0,
])
def test_prezzo_decisione_non_valido_e_sempre_fuori_tolleranza(prezzo_decisione):
    assert prezzo_fuori_tolleranza(prezzo_decisione, 2.2, "back") is True


# ===========================================================================
# 2. PREZZO ATTUALE non valido -> SEMPRE fuori tolleranza (fail-closed)
#
# QUESTO e' il ramo che la mutazione B del coordinatore ha reso FAIL-OPEN
# (``return False``): nessuno dei test di ieri lo esercitava con un valore
# invalido, solo con prezzi VERI (dentro o fuori soglia). Da qui in poi e'
# coperto punto per punto.
# ===========================================================================
@pytest.mark.parametrize("prezzo_attuale", [
    None, True, False, "2.2", [2.2], {}, 1.0, 0.5, -1.0, 0,
])
def test_prezzo_attuale_non_valido_e_sempre_fuori_tolleranza(prezzo_attuale):
    assert prezzo_fuori_tolleranza(2.2, prezzo_attuale, "back") is True


# ===========================================================================
# 3. LATO non valido -> SEMPRE fuori tolleranza
# ===========================================================================
@pytest.mark.parametrize("side", [None, "", "BACK", "Lay", "back ", "back/lay", 0, "punta"])
def test_side_non_valido_e_sempre_fuori_tolleranza(side):
    assert prezzo_fuori_tolleranza(2.2, 2.2, side) is True


# ===========================================================================
# 4. IL CONFINE ESATTO DELLA SOGLIA — «>» non «>=»: allo scostamento
# ESATTAMENTE uguale alla soglia la proposta resta approvabile (False); un
# soffio oltre, non piu' (True). Valori scelti (100.0/102.0/98.0) perche' il
# calcolo in virgola mobile da' un risultato ESATTO (2.0), non un residuo
# tipo 2.0000000000000018: una soglia costruita con numeri qualunque
# rischierebbe un falso rosso per un problema di arrotondamento, non di logica.
# ===========================================================================
def test_scostamento_esattamente_alla_soglia_back_resta_approvabile():
    # back: prezzo SALITO del 2% esatto (100 -> 102, soglia 2%)
    assert abs(102.0 - 100.0) / 100.0 * 100.0 == 2.0   # premessa: nessun residuo float
    assert prezzo_fuori_tolleranza(100.0, 102.0, "back", soglia_pct=2.0) is False


def test_scostamento_un_soffio_oltre_la_soglia_back_non_e_piu_approvabile():
    assert prezzo_fuori_tolleranza(100.0, 102.01, "back", soglia_pct=2.0) is True


def test_scostamento_esattamente_alla_soglia_lay_resta_approvabile():
    # lay: prezzo SCESO del 2% esatto (100 -> 98, soglia 2%) — la funzione
    # giudica solo l'AMPIEZZA dello scostamento, non il verso (docstring).
    assert abs(98.0 - 100.0) / 100.0 * 100.0 == 2.0
    assert prezzo_fuori_tolleranza(100.0, 98.0, "lay", soglia_pct=2.0) is False


def test_scostamento_un_soffio_oltre_la_soglia_lay_non_e_piu_approvabile():
    assert prezzo_fuori_tolleranza(100.0, 97.99, "lay", soglia_pct=2.0) is True


def test_scostamento_nella_direzione_opposta_al_verso_atteso_conta_lo_stesso():
    """La funzione non guarda il verso (e' un'APERTURA, non una chiusura:
    docstring, righe 253-260): un back il cui prezzo SCENDE di piu' del 2 %
    e' fuori tolleranza esattamente come uno che sale."""
    assert prezzo_fuori_tolleranza(100.0, 97.99, "back", soglia_pct=2.0) is True
    assert prezzo_fuori_tolleranza(100.0, 98.0, "back", soglia_pct=2.0) is False


def test_soglia_personalizzata_non_quella_di_default():
    assert SLIPPAGE_PCT_DEFAULT == 2.0
    # con una soglia dello 0,5 %, uno scostamento del 2 % e' ben oltre
    assert prezzo_fuori_tolleranza(100.0, 102.0, "back", soglia_pct=0.5) is True
    # e uno scostamento nullo e' sempre dentro, qualunque sia la soglia
    assert prezzo_fuori_tolleranza(100.0, 100.0, "back", soglia_pct=0.5) is False


def test_prezzo_identico_non_e_mai_fuori_tolleranza():
    assert prezzo_fuori_tolleranza(2.2, 2.2, "back") is False
    assert prezzo_fuori_tolleranza(2.2, 2.2, "lay") is False


def test_default_e_2_punto_0_per_cento():
    """La firma della funzione usa ``SLIPPAGE_PCT_DEFAULT`` come default: se
    qualcuno lo cambia in ``proposte_opportunita.py`` senza aggiornare la
    chiamata, questo test lo nota (non e' un valore ridigitato qui)."""
    assert prezzo_fuori_tolleranza(100.0, 102.0, "back") is False   # 2.0% esatto, default
    assert prezzo_fuori_tolleranza(100.0, 102.01, "back") is True   # un soffio oltre il default


# ===========================================================================
# 5. VALORI NON FINITI (nan, +inf, -inf) — ORDINE DEL COORDINATORE, 3o giro.
#
# REPERTO (2o giro): ``nan`` supera SIA ``isinstance(x,(int,float))`` (nan e'
# un float) SIA ``x<=1.0`` (per IEEE 754 OGNI confronto con nan e' falso,
# compreso ``nan<=1.0``): la guardia di prima (``isinstance``+``<=1.0``) non
# lo intercettava, e la funzione tornava ``False`` (approvabile) su un prezzo
# nan — riprodotto anche dal coordinatore. ``+inf``/``-inf`` invece SONO
# intercettati dal controllo ``<=1.0`` di prima (``inf<=1.0`` e' falso ma
# ``-inf<=1.0`` e' vero): il coordinatore ha verificato ``inf`` -> True,
# quindi solo ``nan`` (in entrambe le direzioni) e ``-inf`` come DECISIONE
# (mai controllato prima) erano il buco vero. Con ``math.isfinite()`` (che
# esclude nan E i due infiniti in un colpo solo) TUTTI i casi sotto sono
# fail-closed, senza distinguere quale forma di "non finito" sia.
# ===========================================================================
def test_prezzo_decisione_nan_e_sempre_fuori_tolleranza():
    assert prezzo_fuori_tolleranza(float("nan"), 2.2, "back") is True
    assert prezzo_fuori_tolleranza(float("nan"), 2.2, "lay") is True


def test_prezzo_attuale_nan_e_sempre_fuori_tolleranza():
    """Il caso riprodotto dal coordinatore: ``prezzo_fuori_tolleranza(3.0,
    nan, 'back')`` tornava ``False`` (approvabile) prima del fix."""
    assert prezzo_fuori_tolleranza(3.0, float("nan"), "back") is True
    assert prezzo_fuori_tolleranza(3.0, float("nan"), "lay") is True


def test_entrambi_i_prezzi_nan_e_sempre_fuori_tolleranza():
    assert prezzo_fuori_tolleranza(float("nan"), float("nan"), "back") is True


@pytest.mark.parametrize("segno", [1, -1])
def test_prezzo_decisione_infinito_e_sempre_fuori_tolleranza(segno):
    assert prezzo_fuori_tolleranza(segno * math.inf, 2.2, "back") is True
    assert prezzo_fuori_tolleranza(segno * math.inf, 2.2, "lay") is True


@pytest.mark.parametrize("segno", [1, -1])
def test_prezzo_attuale_infinito_e_sempre_fuori_tolleranza(segno):
    assert prezzo_fuori_tolleranza(3.0, segno * math.inf, "back") is True
    assert prezzo_fuori_tolleranza(3.0, segno * math.inf, "lay") is True


def test_valori_finiti_normali_non_sono_toccati_dal_fix():
    """Il fix (``math.isfinite``) non deve stringere la tolleranza sui
    prezzi VERI: gli stessi confini di prima (§4) restano identici."""
    assert prezzo_fuori_tolleranza(100.0, 102.0, "back", soglia_pct=2.0) is False
    assert prezzo_fuori_tolleranza(100.0, 102.01, "back", soglia_pct=2.0) is True
