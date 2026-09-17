# -*- coding: utf-8 -*-
"""M1-BIS — la POLITICA V4 (quota viva) sa diventare rossa.

Che cosa si prova, con lo STESSO book sintetico di M1 (chiavi identiche allo
stream vero: `op`/`pt`/`mc`/`id`/`marketDefinition`/`rc`/`atb`/`atl`/`trd`/`tv`,
parsato dal `HistoricListener` VERO di flumine):

  1. RIPREZZO — senza gol la probabilita' della cella decade, il prezzo di
     riserva `L*` SALE, e la quota lo segue verso l'alto finche' incrocia il
     mercato: li' si abbina. E' il meccanismo di `VISIONE_OMEGA_V4 §2`.
  2. FALSIFICAZIONE del riprezzo — con `RIPREZZO_ATTIVO = False` (la quota
     «appoggiata e dimenticata» di M1) lo STESSO scenario non si abbina: il
     fill all'incrocio dipende davvero dal riprezzo.
  3. RIENTRO DOPO SOSPENSIONE — la sospensione in gioco uccide la quota; alla
     riapertura non si quota per N secondi, e dopo N si riquota sul punteggio
     nuovo.
  4. FALSIFICAZIONE del rientro — azzerando l'attesa si quota dentro il
     riassestamento del book, e il test che pretende il silenzio diventa rosso.
  5. INVARIANTI — il prezzo quotato non supera MAI il prezzo di riserva
     (margine >= k) e il caso peggiore del paniere e' quello della formula.

Uso: `python -m pytest Betfair/omega/tests/test_politica_v4_2026_09_17.py -q`
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import pytest

from Betfair.omega.tools import misura_ingresso_passivo as MIP
from Betfair.omega.tests.test_ingresso_passivo_2026_09_17 import (
    MARKET_DEFINITION, SEL_0_0, SEL_3_3, BookFinto, _cliente, _StrategiaFinta,
)

MARKET_ID = "1.999999999"
EVENT_ID = "99999999"
# i `selectionId` VERI di Betfair (gusci concentrici): 13 = "3 - 3", 1 = "0 - 0",
# 6 = "2 - 1", 12 = "3 - 2". Sono gli id del mercato vero, non numeri inventati.
SEL_2_1 = 6
SEL_3_2 = 12
SEL_1_1 = 3
SEL_2_0 = 5
SEL_2_2 = 7
SEL_3_1 = 11


def _definizione(stato: str = "OPEN", in_play: bool = True) -> Dict[str, Any]:
    md = dict(MARKET_DEFINITION)
    md["status"] = stato
    md["inPlay"] = in_play
    md["runners"] = [
        {"status": "ACTIVE", "sortPriority": i + 1, "id": sid}
        for i, sid in enumerate((SEL_0_0, SEL_1_1, SEL_2_0, SEL_2_1,
                                 SEL_2_2, SEL_3_1, SEL_3_2, SEL_3_3))
    ]
    return md


def _catalogo() -> Any:
    """Il `Catalogo` VERO di `replay_registrazioni`, riempito a mano: stessa
    classe che il replay costruisce dal raw, stessi campi."""
    from Betfair.omega.tools.replay_registrazioni import Catalogo, nome_runner_punteggio

    cat = Catalogo()
    cat.event_id = EVENT_ID
    cat.tipi = {MARKET_ID: "CORRECT_SCORE"}
    cat.nomi = {MARKET_ID: {sid: nome_runner_punteggio(sid)
                            for sid in (SEL_0_0, SEL_1_1, SEL_2_0, SEL_2_1,
                                        SEL_2_2, SEL_3_1, SEL_3_2, SEL_3_3)}}
    cat.definizioni = {MARKET_ID: [(0, "OPEN", True, {})]}
    return cat


class MercatoFinto:
    """Il minimo che `MisuraV4._su_book` legge da un `flumine.markets.Market`:
    `context` (dove il `SimulatedMiddleware` deposita le analitiche) e
    `flumine`. Stessi nomi e stessi tipi del vero; le analitiche sono
    `flumine.markets.middleware.RunnerAnalytics`, la classe VERA."""

    def __init__(self) -> None:
        self.context: Dict[str, Any] = {}
        self.flumine = None
        self._analitiche: Dict[Tuple[int, float], Any] = {}

    def applica(self, market_book: Any) -> None:
        from flumine.markets.middleware import RunnerAnalytics

        for runner in market_book.runners:
            chiave = (int(runner.selection_id), 0.0)
            ra = self._analitiche.get(chiave)
            if ra is None:
                self._analitiche[chiave] = RunnerAnalytics(runner)
            else:
                ra(runner)
        self.context["simulated"] = self._analitiche


def _parametri(cadenza_s: float = 0.0) -> Dict[str, Any]:
    par = MIP.parametri_v4(cadenza_s=cadenza_s)
    return par


def _misura(par: Dict[str, Any], *, lambdas: Tuple[float, float] = (1.35, 1.15)) -> Any:
    cat = _catalogo()
    mis = MIP.MisuraV4(EVENT_ID, catalogo=cat, esiti={MARKET_ID: None}, par=par)
    mis.strategia = _StrategiaFinta()
    mis.cliente = _cliente()
    mis.lambdas = lambdas
    mis.fonte_lambdas = "test"
    return mis


def _mondo(mis: Any, nome: str) -> Any:
    return next(m for m in mis.mondi if m.nome == nome)


def _passo(mis: Any, mercato_finto: MercatoFinto, market_book: Any,
           minuto: float, punteggio: Tuple[int, int]) -> None:
    """Un giro completo: il book entra (matching e vita degli ordini), poi la
    politica decide. E' lo stesso ordine del replay vero."""
    mercato_finto.applica(market_book)
    mis._su_book(mercato_finto, market_book)
    mis._giro_mercato(MARKET_ID, "CORRECT_SCORE", minuto, punteggio)


def _prezzi_quotati(mondo: Any, selection_id: int) -> List[float]:
    return [q.prezzo_passivo for q in mondo.quote if q.selection_id == selection_id]


# ---------------------------------------------------------------------------
# 1. IL RIPREZZO: la quota sale con L* e si abbina all'incrocio
# ---------------------------------------------------------------------------
LISTINO = [
    # (0 - 0) e' il punteggio corrente: escluso per costruzione
    {"atb": [[1.2, 500.0]], "atl": [[1.25, 500.0]], "id": SEL_0_0},
    {"atb": [[5.0, 200.0]], "atl": [[5.4, 200.0]], "id": SEL_1_1},
    {"atb": [[9.0, 120.0]], "atl": [[9.6, 120.0]], "id": SEL_2_0},
    {"atb": [[40, 60.0]], "atl": [[50, 60.0]], "id": SEL_2_1},
    {"atb": [[60, 40.0]], "atl": [[70, 40.0]], "id": SEL_2_2},
    {"atb": [[100, 20.0]], "atl": [[120, 20.0]], "id": SEL_3_1},
    {"atb": [[150, 10.0]], "atl": [[200, 10.0]], "id": SEL_3_2},
    {"atb": [[300, 5.0]], "atl": [[400, 5.0]], "id": SEL_3_3},
]
# minuti del 2T in cui gira la politica. Senza gol, `L*` della cella scelta sale
# (v. `omega_v3`: la griglia residua si svuota) finche' incrocia il mercato.
# Il passo e' fitto perche' la politica annulla a un giro e riquota al giro
# dopo («mai due vivi»): con un passo di 5 minuti l'incrocio verrebbe perso fra
# l'annullo e il nuovo ordine. Nella misura vera la cadenza e' di 10 secondi.
MINUTI_SCENARIO = (46, 50, 55, 58, 60, 61, 62, 63, 65, 67, 70)


def _scenario_riprezzo(mis: Any, variante: str = "A_coda") -> Tuple[Any, Any]:
    """Niente gol, il tempo passa: la quota deve salire e finire sul mercato.

    Il BOOK E' FERMO: si muove solo il modello. Fra un giro di politica e
    l'altro passano piu' book, perche' l'ordine ha bisogno di un book per
    arrivare a mercato (bet delay) e di un altro per essere tolto (annullo):
    e' esattamente la sequenza del replay vero.
    """
    book = BookFinto(MARKET_ID)
    mercato = MercatoFinto()
    mondo = _mondo(mis, variante)
    pt = 1_000_000
    primo = True
    for minuto in MINUTI_SCENARIO:
        for i in range(4):
            costruisci = book.immagine if primo else book.aggiornamento
            mb = costruisci(pt, LISTINO, _definizione())
            primo = False
            mercato.applica(mb)
            mis._su_book(mercato, mb)
            if i == 0:
                mis._giro_mercato(MARKET_ID, "CORRECT_SCORE", float(minuto), (0, 0))
            pt += 5_000
    return mondo, book


def test_la_quota_sale_col_prezzo_di_riserva_e_si_abbina_all_incrocio() -> None:
    par = _parametri()
    mis = _misura(par)
    mondo, _book = _scenario_riprezzo(mis)
    assert mondo.quote, "nessuna quota emessa"
    # 1) su OGNI cella la quota si e' mossa solo VERSO L'ALTO (senza gol L* sale)
    mosse = 0
    for sid in {q.selection_id for q in mondo.quote}:
        prezzi = _prezzi_quotati(mondo, sid)
        assert prezzi == sorted(prezzi), (sid, prezzi)
        if len(prezzi) >= 2 and prezzi[-1] > prezzi[0]:
            mosse += 1
    assert mosse >= 1, [(q.selection_id, q.prezzo_passivo) for q in mondo.quote]
    # 2) e all'INCROCIO col mercato la quota si prende al tocco e si abbina
    abbinate = [q for q in mondo.quote if q.abbinato]
    assert abbinate, "la quota non si e' mai abbinata"
    assert any(q.modo == "tocco" for q in abbinate), [q.modo for q in abbinate]
    for q in abbinate:
        assert q.prezzo_ottenuto is not None
        assert q.prezzo_ottenuto <= q.l_stella + 1e-9


def test_falsificazione_senza_riprezzo_il_fill_all_incrocio_non_avviene(
        monkeypatch: Any) -> None:
    """Con la quota FERMA (`RIPREZZO_ATTIVO = False`, cioe' l'ordine
    «appoggiato e dimenticato» di M1) lo stesso scenario non produce nessun
    abbinamento: il test verde qui sopra sa quindi diventare rosso."""
    monkeypatch.setattr(MIP, "RIPREZZO_ATTIVO", False)
    par = _parametri()
    mis = _misura(par)
    mondo, _book = _scenario_riprezzo(mis)
    assert mondo.quote, "nessuna quota emessa"
    # la quota non si e' mai mossa: una sola per cella, al prezzo del primo giro
    for sid in {q.selection_id for q in mondo.quote}:
        assert len(_prezzi_quotati(mondo, sid)) == 1, _prezzi_quotati(mondo, sid)
    # e senza riprezzo l'incrocio non arriva mai: nessun abbinamento
    assert not [q for q in mondo.quote if q.abbinato]


# ---------------------------------------------------------------------------
# 2. IL RIENTRO DOPO LA SOSPENSIONE
# ---------------------------------------------------------------------------
def _quote_vive(mondo: Any) -> Dict[int, Any]:
    return mondo.vive.get(MARKET_ID) or {}


def test_la_sospensione_uccide_la_quota_e_il_rientro_aspetta_i_20_secondi() -> None:
    par = _parametri()
    mis = _misura(par)
    mondo = _mondo(mis, "A_coda")
    book = BookFinto(MARKET_ID)
    mercato = MercatoFinto()
    listino = LISTINO
    pt = 1_000_000
    mb = book.immagine(pt, listino, _definizione())
    _passo(mis, mercato, mb, 50.0, (0, 0))
    pt += 10_000
    mb = book.aggiornamento(pt, listino, _definizione())
    _passo(mis, mercato, mb, 50.2, (0, 0))
    assert _quote_vive(mondo), "nessuna quota viva prima della sospensione"
    quote_prima = len(mondo.quote)

    # --- SOSPENSIONE (gol/rigore/rosso): la quota e' morta ------------------
    pt += 5_000
    mb = book.aggiornamento(pt, listino, _definizione("SUSPENDED", True))
    _passo(mis, mercato, mb, 51.0, (0, 0))
    assert not _quote_vive(mondo)
    assert any(q.morte == "sospensione" for q in mondo.quote)

    # --- RIAPERTURA: per 20 s non si quota ----------------------------------
    pt += 5_000
    mb = book.aggiornamento(pt, listino, _definizione("OPEN", True))
    _passo(mis, mercato, mb, 51.2, (1, 0))
    assert mis.riprendi_da_ms[MARKET_ID] == pt + 20_000
    assert not _quote_vive(mondo), "quotato dentro il riassestamento del book"
    pt += 10_000
    mb = book.aggiornamento(pt, listino, _definizione("OPEN", True))
    _passo(mis, mercato, mb, 51.4, (1, 0))
    assert not _quote_vive(mondo), "quotato prima dei 20 s"
    assert len(mondo.quote) == quote_prima

    # --- dopo i 20 s si RIENTRA, sul punteggio NUOVO ------------------------
    pt += 15_000
    mb = book.aggiornamento(pt, listino, _definizione("OPEN", True))
    _passo(mis, mercato, mb, 51.8, (1, 0))
    assert _quote_vive(mondo), "nessun rientro dopo il riassestamento"
    assert len(mondo.quote) > quote_prima
    nuova = mondo.quote[-1]
    assert nuova.punteggio == (1, 0)          # ricalcolata sul punteggio nuovo
    # e la cella scelta e' raggiungibile dal punteggio NUOVO, a >= 2 gol
    from Betfair.omega import omega_v3 as V3

    h, a = V3.parse_scoreline(nuova.nome)
    assert h >= 1 and a >= 0 and (h - 1) + (a - 0) >= par["distanza_minima_gol"]


def test_falsificazione_senza_attesa_si_quota_dentro_il_riassestamento() -> None:
    """Con `rientro_dopo_sospensione_s = 0` la quota rientra SUBITO dopo la
    riapertura: il test qui sopra, che pretende il silenzio, diventa rosso."""
    par = _parametri()
    par["rientro_dopo_sospensione_s"] = 0.0
    mis = _misura(par)
    mondo = _mondo(mis, "A_coda")
    book = BookFinto(MARKET_ID)
    mercato = MercatoFinto()
    listino = LISTINO
    pt = 1_000_000
    _passo(mis, mercato, book.immagine(pt, listino, _definizione()), 50.0, (0, 0))
    pt += 5_000
    _passo(mis, mercato,
           book.aggiornamento(pt, listino, _definizione("SUSPENDED", True)), 51.0, (0, 0))
    assert not _quote_vive(mondo)
    pt += 5_000
    _passo(mis, mercato,
           book.aggiornamento(pt, listino, _definizione("OPEN", True)), 51.2, (1, 0))
    assert _quote_vive(mondo), "con attesa zero si deve quotare subito"


# ---------------------------------------------------------------------------
# 3. INVARIANTI DELLA POLITICA
# ---------------------------------------------------------------------------
def test_il_prezzo_quotato_non_supera_mai_il_prezzo_di_riserva() -> None:
    """Il margine e' il cuore della politica: se il prezzo di lay superasse
    `L*`, il margine k scenderebbe sotto la soglia e la quota sarebbe a EV
    peggiore di quanto dichiarato."""
    par = _parametri()
    mis = _misura(par)
    mondo, _book = _scenario_riprezzo(mis)
    assert mondo.quote
    from Betfair.omega.tools import misura_k as MK

    for q in mondo.quote:
        assert q.prezzo_passivo <= q.l_stella + 1e-9, (q.prezzo_passivo, q.l_stella)
        p_impl = MK.p_implicita(q.prezzo_passivo, par["commissione"])
        assert p_impl is not None
        assert p_impl / q.p_sup >= par["k_soglia"] - 1e-9


def test_la_cella_quotata_e_sempre_a_due_gol_di_distanza() -> None:
    par = _parametri()
    mis = _misura(par)
    mondo, _book = _scenario_riprezzo(mis)
    from Betfair.omega import omega_v3 as V3

    for q in mondo.quote:
        h, a = V3.parse_scoreline(q.nome)
        sh, sa = q.punteggio
        assert h >= sh and a >= sa
        assert (h - sh) + (a - sa) >= par["distanza_minima_gol"]


def test_la_variante_di_coda_resta_in_banda_quella_libera_no() -> None:
    """La sensibilita' `_coda` serve proprio a questo: senza banda,
    l'ordinamento per EV/liability (k fisso a 2 -> monotono in 1/(L-1)) esce
    dalla coda e quota le celle piu' probabili."""
    par = _parametri()
    mis = _misura(par)
    _scenario_riprezzo(mis)
    coda = _mondo(mis, "A_coda")
    libera = _mondo(mis, "A")
    assert coda.quote and libera.quote
    assert all(20.0 <= q.prezzo_passivo <= 120.0 for q in coda.quote)
    assert min(q.prezzo_passivo for q in libera.quote) < 20.0


def test_dimensione_a_liability_fissa() -> None:
    par = _parametri()
    mis = _misura(par)
    mondo, _ = _scenario_riprezzo(mis)
    import math as _math

    for q in mondo.quote:
        # `s = liability/(L-1)` arrotondata PER DIFETTO al centesimo, al prezzo
        # a cui si scambia davvero (per un tocco e' il prezzo del book)
        prezzo = float(q.prezzo_tocco if q.modo == "tocco" and q.prezzo_tocco
                       else q.prezzo_passivo)
        atteso = max(0.01, _math.floor(30.0 / (prezzo - 1.0) * 100.0) / 100.0)
        assert q.size == pytest.approx(atteso), (q.nome, q.modo, prezzo, q.size)
        assert q.size * (prezzo - 1.0) <= 30.0 + 1e-6
    uno = _mondo(mis, "A_stake1")
    assert all(q.size == 1.0 for q in uno.quote)


# ---------------------------------------------------------------------------
# 4. IL PANIERE: il caso peggiore e' quello della formula
# ---------------------------------------------------------------------------
def test_caso_peggiore_del_paniere() -> None:
    """`max_j [ s_j (L_j - 1) - somma_{i != j} s_i (1 - c) ]` (visione §4)."""
    c = 0.05
    assert MIP.caso_peggiore([], c) == 0.0
    # una sola cella: e' la liability nuda
    assert MIP.caso_peggiore([(1.0, 100.0)], c) == pytest.approx(99.0)
    # cinque celle a quota 100 con stake 1: 99 - 4 x 0,95 (visione §9.4)
    cinque = [(1.0, 100.0)] * 5
    assert MIP.caso_peggiore(cinque, c) == pytest.approx(99.0 - 4 * 0.95)
    # NON e' la somma delle liability: sono mutuamente esclusive
    assert MIP.caso_peggiore(cinque, c) < 5 * 99.0


def test_il_paniere_non_supera_il_cap_di_caso_peggiore() -> None:
    par = _parametri()
    mis = _misura(par)
    _scenario_riprezzo(mis)
    for nome in ("B3", "B5", "B5_coda"):
        mondo = _mondo(mis, nome)
        posizioni = mondo.esposte(MARKET_ID)
        vive = [(ap.size, ap.cand.prezzo_passivo)
                for ap in (mondo.vive.get(MARKET_ID) or {}).values()]
        assert MIP.caso_peggiore(posizioni + vive, par["commissione"]) \
            <= par["liability_gamba"] + 1e-6


def test_mai_due_ordini_vivi_sulla_stessa_cella() -> None:
    par = _parametri()
    mis = _misura(par)
    _scenario_riprezzo(mis)
    for mondo in mis.mondi:
        for _mid, vive in mondo.vive.items():
            assert len(vive) == len(set(vive.keys()))
            assert len(vive) <= mondo.celle


# ---------------------------------------------------------------------------
# 5. LE FINESTRE, IL MODELLO E LA FONTE DEI LAMBDA
# ---------------------------------------------------------------------------
def test_finestre_larghe_e_modello_di_produzione() -> None:
    par = MIP.parametri_v4()
    assert MIP.FINESTRE_V4["HALF_TIME_SCORE"] == (1, 44)
    assert MIP.FINESTRE_V4["CORRECT_SCORE"] == (46, 89)
    from Betfair.omega import omega_config
    from Betfair.omega.tools.replay_registrazioni import _parametri_v3_dal_banco

    assert par["parametri_modello"] == _parametri_v3_dal_banco()
    assert par["parametri_modello"].modello == "gamma_poisson"
    assert par["distanza_minima_gol"] == omega_config.DEFAULTS["v3_distanza_minima_gol"]
    assert par["commissione"] == omega_config.DEFAULTS["commission_pct"] / 100.0


def test_i_lambda_vengono_dalla_catena_vera_e_senza_di_essi_non_si_quota() -> None:
    """Gradino 3 di `omega_service._prematch_lambdas`: le quote 1X2 pre-KO
    congelate dallo scanner. Senza lambda NON si quota (mai a occhi chiusi)."""
    from Betfair.omega import omega_model as M

    pre_ko = {"home": 1.84, "draw": 3.8, "away": 5.1,
              "captured_at": "2026-07-05T19:36:40.703000+00:00"}
    lam = M.lambdas_from_pre_ko(pre_ko)
    assert lam is not None and lam[0] > lam[1] > 0

    par = _parametri()
    mis = _misura(par)
    mis.lambdas = None
    mis.fonte_lambdas = "assente"
    book = BookFinto(MARKET_ID)
    mercato = MercatoFinto()
    mb = book.immagine(1_000_000, LISTINO, _definizione())
    _passo(mis, mercato, mb, 60.0, (0, 0))
    assert all(not m.quote for m in mis.mondi)

    # e la funzione della catena vera riempie il campo con la fonte dichiarata
    mis._risolvi_lambdas({"pre_ko": pre_ko})
    assert mis.fonte_lambdas == "pre_ko_odds"
    assert mis.lambdas == pytest.approx(lam)


def test_la_fine_finestra_annulla_tutto() -> None:
    par = _parametri()
    mis = _misura(par)
    mondo = _mondo(mis, "A_coda")
    book = BookFinto(MARKET_ID)
    mercato = MercatoFinto()
    listino = LISTINO
    _passo(mis, mercato, book.immagine(1_000_000, listino, _definizione()), 50.0, (0, 0))
    assert _quote_vive(mondo)
    _passo(mis, mercato, book.aggiornamento(1_010_000, listino, _definizione()),
           90.0, (0, 0))
    assert not _quote_vive(mondo)
    assert any(q.morte == "fine_finestra" for q in mondo.quote)
