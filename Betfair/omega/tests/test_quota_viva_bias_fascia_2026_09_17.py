# -*- coding: utf-8 -*-
"""M1-TER — la quota viva al prezzo del BIAS DI FASCIA sa diventare rossa.

Che cosa si prova, con lo STESSO book sintetico nativo di M1/M1-bis (chiavi
identiche allo stream vero `op`/`pt`/`mc`/`id`/`marketDefinition`/`rc`/`atb`/
`atl`/`trd`/`tv`, parsato dal `HistoricListener` VERO di flumine):

  1. `p_equa` — la devigazione e' quella di `tools/superficie_liability.py`:
     mid normalizzato sui runner ATTIVI, niente devig sotto 6 selezioni prezzate
     sui due lati, book incrociati scartati.
  2. `L*_fascia` — il prezzo di riserva viene dal BIAS MISURATO da M6, non dal
     modello, e sta DENTRO lo spread (sopra il miglior back).
  3. RIPREZZO al bias di fascia — quando il book si muove, `p_equa` cambia,
     `L*_fascia` cambia e la quota lo segue; all'incrocio si prende al tocco.
  4. FALSIFICAZIONE `k_fascia = 1` — con il margine spento la quota SCENDE al
     tocco: i fill salgono e il test che pretende il margine diventa ROSSO.
  5. AMMISSIBILITA' — solo Correct Score, solo le fasce con bias prudente > 1.

Uso: `python -m pytest Betfair/omega/tests/test_quota_viva_bias_fascia_2026_09_17.py -q`
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import pytest

from Betfair.omega.tools import misura_ingresso_passivo as MIP
from Betfair.omega.tests.test_ingresso_passivo_2026_09_17 import (
    BookFinto, _cliente, _StrategiaFinta,
)
from Betfair.omega.tests.test_politica_v4_2026_09_17 import (
    EVENT_ID, MARKET_ID, MercatoFinto, _catalogo, _definizione,
)


def _par(cadenza_s: float = 0.0) -> Dict[str, Any]:
    par = MIP.parametri_v4ter(cadenza_s=cadenza_s)
    assert par["bias_fascia"], "il file di M6 non e' leggibile: la misura non ha margine"
    return par


def _misura(par: Dict[str, Any]) -> Any:
    mis = MIP.MisuraV4Ter(EVENT_ID, catalogo=_catalogo(), esiti={MARKET_ID: None},
                          par=par)
    mis.strategia = _StrategiaFinta()
    mis.cliente = _cliente()
    return mis


def _mondo(mis: Any, nome: str) -> Any:
    return next(m for m in mis.mondi if m.nome == nome)


def _passo(mis: Any, mercato: MercatoFinto, mb: Any, minuto: float,
           punteggio: Tuple[int, int]) -> None:
    mercato.applica(mb)
    mis._su_book(mercato, mb)
    mis._giro_mercato(MARKET_ID, "CORRECT_SCORE", minuto, punteggio)


# Un book con OTTO selezioni prezzate sui due lati (sopra la soglia di devig) e
# con gli SPREAD LARGHI della coda di un Correct Score vero (il miglior back sta
# al 55-60 % del miglior lay: M1 misura 6 tick di spread a quota ~60). La somma
# dei mid vale ~1,03, cioe' l'overround tipico: se il book sintetico non somma a
# circa 1, `p_equa` esce sballata e con lei il prezzo di riserva.
# La cella osservata e' "2 - 2" (selectionId 7).
COPPIE_FISSE = ((2.0, 2.1), (3.6, 3.8), (5.0, 5.4), (22, 30),
                None, (70, 120), (110, 200), (240, 400))


def listino(lay_2_2: float = 75.0, back_2_2: float = 45.0) -> List[Dict[str, Any]]:
    from Betfair.omega.tests.test_politica_v4_2026_09_17 import (
        SEL_0_0, SEL_1_1, SEL_2_0, SEL_2_1, SEL_2_2, SEL_3_1, SEL_3_2, SEL_3_3,
    )

    ids = (SEL_0_0, SEL_1_1, SEL_2_0, SEL_2_1, SEL_2_2, SEL_3_1, SEL_3_2, SEL_3_3)
    size = (400.0, 300.0, 200.0, 100.0, 40.0, 20.0, 10.0, 5.0)
    fuori: List[Dict[str, Any]] = []
    for sid, coppia, sz in zip(ids, COPPIE_FISSE, size):
        b, l = (back_2_2, lay_2_2) if coppia is None else coppia
        fuori.append({"atb": [[b, sz]], "atl": [[l, sz]], "id": sid})
    return fuori


# ---------------------------------------------------------------------------
# 1. p_equa: la devigazione e' quella di superficie_liability
# ---------------------------------------------------------------------------
def test_p_equa_e_la_devigazione_di_superficie_liability() -> None:
    from Betfair.omega.tests.test_politica_v4_2026_09_17 import SEL_2_2

    book = BookFinto(MARKET_ID)
    mb = book.immagine(1_000_000, listino(), _definizione())
    p_eq, diag = MIP.probabilita_eque(mb)
    assert diag["devig_ok"] is True and diag["n_mid"] == 8
    assert sum(p_eq.values()) == pytest.approx(1.0)
    # la formula, riga per riga: mid = 0,5 (1/lay + 1/back), normalizzato
    coppie = [c if c is not None else (45.0, 75.0) for c in COPPIE_FISSE]
    somma = sum(0.5 * (1.0 / l + 1.0 / b) for b, l in coppie)
    assert 1.0 < somma < 1.1, somma            # overround realistico
    atteso = (0.5 * (1.0 / 75.0 + 1.0 / 45.0)) / somma
    assert p_eq[SEL_2_2] == pytest.approx(atteso)


def test_sotto_sei_selezioni_non_si_deviga() -> None:
    """Normalizzare mezzo book inventa probabilita': stessa regola di
    `superficie_liability` e di `misura_k`."""
    book = BookFinto(MARKET_ID)
    mb = book.immagine(1_000_000, listino()[:5], _definizione())
    p_eq, diag = MIP.probabilita_eque(mb)
    assert diag["n_mid"] == 5 and diag["devig_ok"] is False
    assert p_eq == {}


def test_un_book_incrociato_non_e_un_prezzo() -> None:
    from Betfair.omega.tests.test_politica_v4_2026_09_17 import SEL_2_2

    incrociato = listino()
    for riga in incrociato:
        if riga["id"] == SEL_2_2:
            riga["atb"] = [[80, 40.0]]        # back >= lay: stato transitorio
    book = BookFinto(MARKET_ID)
    mb = book.immagine(1_000_000, incrociato, _definizione())
    p_eq, diag = MIP.probabilita_eque(mb)
    assert SEL_2_2 not in p_eq
    assert diag["n_mid"] == 7


# ---------------------------------------------------------------------------
# 2. Il prezzo di riserva viene dal BIAS, e sta dentro lo spread
# ---------------------------------------------------------------------------
def test_il_prezzo_di_riserva_viene_dal_bias_misurato_da_m6() -> None:
    par = _par()
    mis = _misura(par)
    book = BookFinto(MARKET_ID)
    mb = book.immagine(1_000_000, listino(), _definizione())
    cand = mis._candidati(MARKET_ID, "CORRECT_SCORE", 60.0, (0, 0), mb)
    assert cand, "nessuna cella ammissibile"
    c = float(par["commissione"])
    for d in cand:
        # la formula, esattamente: L* = (1-c)/(p_equa * k_fascia) + c
        atteso = (1.0 - c) / (d["p_equa"] * d["k_fascia"]) + c
        assert d["l_stella"] == pytest.approx(atteso)
        # e `k_fascia` e' il numero di M6, non uno scritto qui
        assert d["k_fascia"] == par["bias_fascia"][("CORRECT_SCORE", d["fascia"])]
        assert d["k_fascia"] > 1.0
        # IL PREZZO DI RISERVA STA SEMPRE SOTTO IL TOCCO. Non e' una scelta: con
        # un book normalizzato `p_implicita(best lay) / p_equa` non arriva a 1,11
        # (M6 lo misura a 0,45-0,53), quindi il tocco non offre mai il margine.
        assert d["l_stella"] < d["prezzo_tocco"]
        # e su questo book, con gli spread larghi della coda vera, sta SOPRA il
        # miglior back: e' il margine di manovra di M4M5M6 §6-bis.3
        assert d["l_stella"] > d["prezzo_back"]


def test_il_bias_di_fascia_si_legge_dal_file_versionato_di_m6() -> None:
    bias = MIP.bias_di_fascia()
    assert bias, "file di M6 assente"
    percorso = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(MIP.__file__))),
                            "data", MIP.FILE_M6)
    dati = json.load(open(percorso, encoding="utf-8"))
    atteso = {(r["mercato"], r["fascia"]): r["bias_equo_prudente"]
              for r in dati["righe"] if r.get("bias_equo_prudente") is not None}
    assert bias == atteso
    operabili = {k for k, v in bias.items() if v > 1.0}
    assert operabili == {("CORRECT_SCORE", "0,5-1%"), ("CORRECT_SCORE", "1-2%")}


def test_i_tre_prezzi_sono_quelli_della_misura() -> None:
    from Betfair.omega.tests.test_politica_v4_2026_09_17 import SEL_2_2

    par = _par()
    mis = _misura(par)
    book = BookFinto(MARKET_ID)
    mb = book.immagine(1_000_000, listino(), _definizione())
    cand = {d["selection_id"]: d for d in
            mis._candidati(MARKET_ID, "CORRECT_SCORE", 60.0, (0, 0), mb)}
    d = cand.get(SEL_2_2)
    if d is None:
        pytest.skip("la cella 2 - 2 non e' in una fascia operabile con questo book")
    assert d["prezzi"]["back+1"]["prezzo"] == MIP._tick(45.0, 1)
    assert d["prezzi"]["back+3"]["prezzo"] == MIP._tick(45.0, 3)
    assert d["prezzi"]["riserva"]["prezzo"] == MIP._tick_giu(d["l_stella"])
    for nome, v in d["prezzi"].items():
        assert v["prezzo"] <= 1000.0
        if v["modo"] == "passivo":
            assert v["prezzo"] < d["prezzo_tocco"]
            assert v["prezzo_effettivo"] == v["prezzo"]
        else:
            assert v["prezzo_effettivo"] == d["prezzo_tocco"]


# ---------------------------------------------------------------------------
# 3. IL RIPREZZO al bias di fascia
# ---------------------------------------------------------------------------
def _scenario(mis: Any, prezzi_lay: Tuple[float, ...],
              prezzi_back: Tuple[float, ...]) -> Tuple[Any, Any]:
    """Il book della cella osservata si muove; il resto e' fermo. La quota deve
    seguire `L*_fascia`, che si muove con `p_equa`."""
    book = BookFinto(MARKET_ID)
    mercato = MercatoFinto()
    pt = 1_000_000
    primo = True
    for lay, back in zip(prezzi_lay, prezzi_back):
        for i in range(4):
            costruisci = book.immagine if primo else book.aggiornamento
            mb = costruisci(pt, listino(lay, back), _definizione())
            primo = False
            mercato.applica(mb)
            mis._su_book(mercato, mb)
            if i == 0:
                mis._giro_mercato(MARKET_ID, "CORRECT_SCORE", 60.0, (0, 0))
            pt += 5_000
    return book, mercato


def test_la_quota_segue_il_prezzo_di_riserva_del_bias_e_poi_si_abbina() -> None:
    """Il book si muove -> `p_equa` cambia -> `L*_fascia` cambia -> la quota si
    sposta; poi passa volume SCAMBIATO al nostro prezzo e la quota si abbina."""
    from Betfair.omega.tests.test_politica_v4_2026_09_17 import SEL_2_2

    par = _par()
    mis = _misura(par)
    book, mercato = _scenario(mis, (75.0, 65.0, 60.0), (45.0, 45.0, 45.0))
    mondo = _mondo(mis, "a_riserva")
    prezzi = [q.prezzo_passivo for q in mondo.quote if q.selection_id == SEL_2_2]
    assert len(prezzi) >= 2 and len(set(prezzi)) >= 2, prezzi   # si e' SPOSTATA
    vivo = (mondo.vive.get(MARKET_ID) or {}).get(SEL_2_2)
    assert vivo is not None and vivo.vivo, "nessuna quota viva sulla 2 - 2"
    prezzo = float(vivo.cand.prezzo_passivo)

    # ora passa TRAFFICO al nostro prezzo: e' l'unico modo di abbinarsi passivi
    righe = listino(60.0, 45.0)
    for r in righe:
        if r["id"] == SEL_2_2:
            r["trd"] = [[prezzo, 400.0]]
            r["tv"] = 400.0
    mb = book.aggiornamento(1_200_000, righe, _definizione())
    mercato.applica(mb)
    mis._su_book(mercato, mb)
    assert vivo.cand.abbinato is True, (prezzo, vivo.cand.morte)
    assert vivo.cand.prezzo_ottenuto == pytest.approx(prezzo)


def test_il_margine_al_prezzo_quotato_non_scende_sotto_il_bias_di_fascia() -> None:
    """La variante (a) quota ESATTAMENTE alla riserva: il margine sul prezzo
    quotato deve restare >= `k_fascia`. E' l'invariante che la falsificazione
    qui sotto rompe."""
    from Betfair.omega.tools import misura_k as MK

    par = _par()
    mis = _misura(par)
    _scenario(mis, (75.0, 65.0, 60.0, 55.0), (45.0, 45.0, 45.0, 45.0))
    mondo = _mondo(mis, "a_riserva")
    assert mondo.quote
    for q in mondo.quote:
        if q.modo != "passivo":
            continue
        p_impl = MK.p_implicita(q.prezzo_passivo, par["commissione"])
        assert p_impl is not None
        k_fascia = par["bias_fascia"][("CORRECT_SCORE", q.fascia_psup)]
        assert p_impl / q.p_sup >= k_fascia - 1e-9, (q.nome, q.prezzo_passivo, q.l_stella)


def test_falsificazione_k_fascia_uguale_a_uno_fa_scendere_la_quota_al_tocco() -> None:
    """Con `k_fascia = 1` il margine e' spento: `L*` sale fin dentro il lato
    lay, la quota scende al tocco, i fill salgono. Il test qui sopra (che
    pretende il margine) diventa ROSSO su questi stessi dati."""
    from Betfair.omega.tools import misura_k as MK

    par_vero = _par()
    par_rotto = _par()
    par_rotto["bias_fascia"] = {k: 1.0 for k in par_rotto["bias_fascia"]}
    par_rotto["fasce_operabili"] = par_vero["fasce_operabili"]

    prezzi = ((75.0, 65.0, 60.0, 55.0), (45.0, 45.0, 45.0, 45.0))

    mis_vero = _misura(par_vero)
    _scenario(mis_vero, *prezzi)
    vero = _mondo(mis_vero, "a_riserva")

    # con il bias spento la soglia `k_fascia > 1` escluderebbe tutto: qui si
    # rompe SOLO il margine, lasciando le stesse celle ammissibili
    mis_rotto = MIP.MisuraV4Ter(EVENT_ID, catalogo=_catalogo(),
                                esiti={MARKET_ID: None}, par=par_rotto)
    mis_rotto.strategia = _StrategiaFinta()
    mis_rotto.cliente = _cliente()
    mis_rotto.bias = {k: 1.0 for k in par_vero["bias_fascia"]}
    mis_rotto.par["fasce_operabili"] = par_vero["fasce_operabili"]
    # la guardia "bias non dimostrato" va tolta a mano, se no non quota nulla
    originale = MIP.MisuraV4Ter._candidati

    def senza_guardia(self, market_id, mercato, minuto, punteggio, book):
        self.bias = {k: 1.0000001 for k in par_vero["bias_fascia"]}
        return originale(self, market_id, mercato, minuto, punteggio, book)

    MIP.MisuraV4Ter._candidati = senza_guardia
    try:
        _scenario(mis_rotto, *prezzi)
    finally:
        MIP.MisuraV4Ter._candidati = originale
    rotto = _mondo(mis_rotto, "a_riserva")

    assert vero.quote and rotto.quote
    # 1) con il bias spento la quota e' PIU' ALTA (piu' vicina al lato lay)
    prezzo_vero = max(q.prezzo_passivo for q in vero.quote)
    prezzo_rotto = max(q.prezzo_passivo for q in rotto.quote)
    assert prezzo_rotto > prezzo_vero, (prezzo_vero, prezzo_rotto)
    # 2) e i fill sono di piu' (o almeno non di meno)
    assert sum(1 for q in rotto.quote if q.abbinato) >= \
        sum(1 for q in vero.quote if q.abbinato)
    # 3) l'invariante del margine e' VIOLATA sui dati rotti: il test verde
    #    qui sopra sa quindi diventare rosso
    violazioni = 0
    for q in rotto.quote:
        if q.modo != "passivo":
            continue
        p_impl = MK.p_implicita(q.prezzo_passivo, par_vero["commissione"])
        k_fascia = par_vero["bias_fascia"][("CORRECT_SCORE", q.fascia_psup)]
        if p_impl is not None and p_impl / q.p_sup < k_fascia - 1e-9:
            violazioni += 1
    assert violazioni > 0, "la falsificazione non ha rotto niente"


# ---------------------------------------------------------------------------
# 4. AMMISSIBILITA'
# ---------------------------------------------------------------------------
def test_solo_correct_score_e_solo_le_fasce_col_bias_dimostrato() -> None:
    par = _par()
    mis = _misura(par)
    assert set(mis.mercati.values()) <= {"CORRECT_SCORE"}
    _scenario(mis, (75.0, 65.0, 60.0), (45.0, 45.0, 45.0))
    for mondo in mis.mondi:
        for q in mondo.quote:
            assert q.mercato == "CORRECT_SCORE"
            if mondo.ammissibilita == "m6":
                assert q.fascia_psup in par["fasce_operabili"], q.fascia_psup
            else:
                assert MIP.BANDA_PEQUA_V4TER[0] <= q.p_sup <= MIP.BANDA_PEQUA_V4TER[1]
            # mai il punteggio corrente ne' gli adiacenti
            from Betfair.omega import omega_v3 as V3

            h, a = V3.parse_scoreline(q.nome)
            sh, sa = q.punteggio
            assert h >= sh and a >= sa
            assert (h - sh) + (a - sa) >= par["distanza_minima_gol"]


def test_la_finestra_e_dal_primo_all_ottantacinquesimo() -> None:
    assert MIP.FINESTRA_V4TER == (1, 85)
    assert MIP.MERCATO_V4TER == "CORRECT_SCORE"
    par = _par()
    mis = _misura(par)
    book = BookFinto(MARKET_ID)
    mercato = MercatoFinto()
    _passo(mis, mercato, book.immagine(1_000_000, listino(), _definizione()),
           60.0, (0, 0))
    assert any(m.vive.get(MARKET_ID) for m in mis.mondi)
    _passo(mis, mercato, book.aggiornamento(1_010_000, listino(), _definizione()),
           86.0, (0, 0))
    assert not any(m.vive.get(MARKET_ID) for m in mis.mondi)


def test_il_modello_non_entra_nel_prezzo() -> None:
    """In M1-ter `omega_v3.probabilita_selezioni` non viene chiamata: il prezzo
    e' tutto di mercato. Senza lambda la misura quota lo stesso."""
    par = _par()
    mis = _misura(par)
    assert mis.fonte_lambdas.startswith("non_usato")
    chiamate = {"n": 0}
    from Betfair.omega import omega_v3 as V3

    originale = V3.probabilita_selezioni

    def spia(*a, **kw):
        chiamate["n"] += 1
        return originale(*a, **kw)

    V3.probabilita_selezioni = spia
    try:
        _scenario(mis, (75.0, 65.0, 60.0), (45.0, 45.0, 45.0))
    finally:
        V3.probabilita_selezioni = originale
    assert chiamate["n"] == 0
    assert any(m.quote for m in mis.mondi)


# ---------------------------------------------------------------------------
# 5. LA SELEZIONE AVVERSA — la metrica che decide
# ---------------------------------------------------------------------------
def _quota(event_id: str, sel: int, *, abbinato: bool, esito: bool) -> Any:
    q = MIP.QuotaV4(event_id=event_id, market_id="1.1", selection_id=sel,
                    prezzo_passivo=50.0, variante="t", mercato="CORRECT_SCORE",
                    fascia_psup="1-2%")
    q.abbinato = abbinato
    q.esito_cella = esito
    return q


def test_selezione_avversa_e_il_rapporto_di_due_frequenze() -> None:
    # 4 partite, 4 celle ciascuna; in ogni partita esce 1 cella su 4 (25 %),
    # e l'abbinata e' SEMPRE quella che esce: fattore 4,00
    quote = []
    for ev in ("1", "2", "3", "4"):
        for sel in (1, 2, 3, 4):
            quote.append(_quota(ev, sel, abbinato=(sel == 1), esito=(sel == 1)))
    sa = MIP.selezione_avversa(quote, giri_boot=500)
    assert sa["n_candidati"] == 16 and sa["n_abbinati"] == 4
    assert sa["frequenza_candidati"] == pytest.approx(0.25)
    assert sa["frequenza_abbinati"] == pytest.approx(1.0)
    assert sa["fattore"] == pytest.approx(4.0)
    assert sa["soglia_arresto"] == 1.27


def test_selezione_avversa_senza_selezione_vale_uno() -> None:
    quote = []
    for ev in ("1", "2", "3", "4"):
        for sel in (1, 2, 3, 4):
            # esce la cella 1, ma ci abbiniamo sulla 2: nessuna selezione
            quote.append(_quota(ev, sel, abbinato=(sel in (1, 2)), esito=(sel == 1)))
    sa = MIP.selezione_avversa(quote, giri_boot=500)
    assert sa["fattore"] == pytest.approx(2.0)   # 0,5 su 0,25


def test_una_cella_riquotata_conta_UNA_volta() -> None:
    """Il denominatore sono le CELLE candidate, non le quotazioni: una cella
    riquotata cento volte non e' cento candidate (e' il conto di M1 §7)."""
    quote = [_quota("1", 1, abbinato=True, esito=True)]
    quote += [_quota("1", 2, abbinato=False, esito=False) for _ in range(100)]
    sa = MIP.selezione_avversa(quote, giri_boot=200)
    assert sa["n_candidati"] == 2 and sa["unita"] == "cella"
    per_quota = MIP.selezione_avversa(quote, giri_boot=200, per_cella=False)
    assert per_quota["n_candidati"] == 101 and per_quota["unita"] == "quotazione"
    assert sa["fattore"] != per_quota["fattore"]


def test_l_esito_della_cella_c_e_anche_senza_fill() -> None:
    """Il denominatore della selezione avversa ha bisogno dell'esito delle celle
    NON abbinate: senza, il rapporto varrebbe 1,00 per costruzione."""
    par = _par()
    mis = MIP.MisuraV4Ter(EVENT_ID, catalogo=_catalogo(),
                          esiti={MARKET_ID: 7}, par=par)
    mis.strategia = _StrategiaFinta()
    mis.cliente = _cliente()
    _scenario(mis, (75.0, 65.0, 60.0), (45.0, 45.0, 45.0))
    mis.chiudi()
    quote = [q for m in mis.mondi for q in m.quote]
    assert quote
    assert all(q.esito_cella is not None for q in quote)
    assert any(q.esito_cella for q in quote)          # la 2 - 2 e' la vincente
    assert any(not q.esito_cella for q in quote)
