"""02/10/2026 - RUNNER_MINIMI_CORREZIONI: correzioni dopo la verifica di RUNNER_MINIMI_CHIUSURE.

Decisioni dell'utente: "le chiusure devono funzionare", "paper = specchio della realta'",
nessuna regressione, strategie intoccabili. Cosa certifica (un blocco per punto):

  1. PAPER = LIVE: lo stesso ordine 0,43 @18 produce lo stesso ordine mandato e lo stesso
     evento al bot in paper e in live; ``build_order`` non ha piu' la via simulata;
  2. CODICE DEL RIFIUTO SU OGNI STRADA: ``error_code``/``errore`` nell'evento ``order``
     sulla strada asincrona (aggancio al volo) e sugli errori del dispatch; ``error_code``
     nel ``result`` della riga di coda; il ``motivo`` dell'ack sincrono comincia col codice;
  3. CANCEL E REPLACE SU ORDINE TRADOTTO: cancel totale = cancel del vero; cancel parziale
     convertito (r x fattore) e mai sotto 0,50 o fuori banda; replace = cancel del vero e,
     a cancel confermato, nuovo verdetto alla quota chiesta (mai la quota dell'Over sulla
     punta Under);
  5. MERCATI A 3+ ESITI / runner non ACTIVE / piu' vincitori: mai l'equivalente;
  6. PARCHEGGIO DELLA BANCA nella banda INVALID_PROFIT_RATIO per OGNI residuo 0,50-0,99,
     ordine finale fuori banda = rifiuto dichiarato;
  7. GUARDIE MANCANTI: ``omega_market.place_order_live`` e ``order_exec.place_order`` sui
     minimi di ``minimi_it``;
  9. DOPPIA CHIUSURA: il green-up del runner legge la posizione del MERCATO a due esiti.

Finti: motore, canale, client e ordini flumine VERI (fixture ``amb``); il blotter del
green-up ha la firma di flumine (``get_exposures(strategy, lookup)`` con le chiavi
``matched_profit_if_win``/``matched_profit_if_lose``). Nessuna rete, nessun ordine reale.
"""
from __future__ import annotations

import inspect
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.omega import omega_market as OM
from Betfair.stream import live_order_build as LB
from Betfair.stream import live_order_worker as LOW
from Betfair.stream import motore_ordini as MO
from Betfair.stream.tests.test_auto_follow_2026_09_25 import _auto, _monta, _nuovo_mercato
from Betfair.stream.tests.test_cashout_pro_2026_09_10 import (  # noqa: F401
    _STRAT,
    _fl,
    _Market as _MercatoGreenup,
    _runner,
    _Sb,
)
from Betfair.stream.tests.test_motore_ordini_2026_09_24 import (  # noqa: F401 - fixture
    _ack,
    _cmd,
    _manda,
    amb,
)
from Betfair.stream.trading import submin as S

OVER, UNDER = 47972, 47973


def _due_esiti(market: Any, **runner_kw: Any) -> None:
    market.market_book = SimpleNamespace(
        status="OPEN", inplay=True, bet_delay=5, complete=True,
        runners=[SimpleNamespace(selection_id=OVER, handicap=0.0, **runner_kw),
                 SimpleNamespace(selection_id=UNDER, handicap=0.0)])


def _eventi(amb: Any, ws: Any, ref: str) -> List[Dict[str, Any]]:
    return [p["d"] for p in amb.ch.per_ws(ws, "order") if p["d"].get("ref") == ref]


def _place_tradotto(amb: Any, ws: Any, n: int, mode: str = "live") -> Dict[str, Any]:
    """Banca Over 0,43 @18 tradotta in punta Under 7,31 @1,06 (borsa: bet_id vero)."""
    amb.market.borsa = True
    _due_esiti(amb.market)
    _manda(amb, ws, _cmd("safe", n, mode=mode, selection_id=OVER, side="LAY", price=18.0,
                         size=0.43, reduces_liability=True))
    assert _ack(amb, ws)["accettato"] is True
    ev = _eventi(amb, ws, f"safe-t{n}")[-1]
    assert ev["riga_mandata"]["selection_id"] == UNDER and ev["bet_id"]
    return ev


# ===========================================================================
# 1. paper = specchio del live
# ===========================================================================
def test_p1_stesso_ordine_043_in_paper_e_in_live_stesso_mandato_e_stesso_evento(amb):
    _due_esiti(amb.market)
    ws = amb.ch.collega("mike")
    esiti = {}
    for n, mode in ((1, "paper"), (2, "live")):
        _manda(amb, ws, _cmd("mike", n, mode=mode, selection_id=OVER, side="LAY",
                             price=18.0, size=0.43, reduces_liability=True))
        assert _ack(amb, ws)["accettato"] is True
        ordine, _ref, client = amb.market.calls[-1]
        assert client is (amb.paper if mode == "paper" else amb.reale)
        ev = _eventi(amb, ws, f"mike-t{n}")[-1]
        esiti[mode] = ((ordine.selection_id, ordine.side, ordine.order_type.price,
                        ordine.order_type.size),
                       {k: ev[k] for k in ("selection_id", "side", "price", "size", "fase")},
                       ev["tradotto"]["mandato"])
    assert esiti["paper"] == esiti["live"]
    assert esiti["live"][0] == (UNDER, "BACK", 1.06, 7.31)
    assert esiti["live"][1] == {"selection_id": OVER, "side": "lay", "price": 18.0,
                                "size": 0.43, "fase": "inviato"}


def test_p1_build_order_senza_via_simulata_e_mai_sotto_il_minimo():
    assert "simulato_ammette_sotto_minimo" not in inspect.signature(LB.build_order).parameters
    src = inspect.getsource(LOW._costruisci_chiusura)
    assert "_is_live_mode" not in src and "simulato" not in src.split('"""')[-1]


def test_p1_gamba_di_chiusura_paper_sotto_minimo_mai_costruita_diretta(monkeypatch):
    monkeypatch.setattr(LOW, "_jurisdiction", lambda: "it")
    m = _MercatoGreenup("1.1")
    for mode in ("paper", "live"):
        ordine, prezzo, size = LOW._costruisci_chiusura(
            m, strategy=_STRAT, selection_id=10, handicap=0.0, side="back", price=3.0,
            size=0.30, persistence="LAPSE", cust_ref="awlq1", mode=mode)
        assert ordine is None and size == 0.30
    ordine, _p, size = LOW._costruisci_chiusura(
        m, strategy=_STRAT, selection_id=10, handicap=0.0, side="back", price=3.0,
        size=1.00, persistence="LAPSE", cust_ref="awlq2", mode="paper")
    assert ordine is not None and size == 1.00


# ===========================================================================
# 2. codice del rifiuto su ogni strada
# ===========================================================================
@pytest.mark.parametrize("testo,codice", [
    ("SOTTO_MINIMO_NON_PIAZZABILE: LAY 0.43", "SOTTO_MINIMO_NON_PIAZZABILE"),
    ("greenup: SOTTO_MINIMO_NON_PIAZZABILE: size 0.30", "SOTTO_MINIMO_NON_PIAZZABILE"),
    ("submin_non_percorribile: SOTTO_MINIMO_NON_PIAZZABILE: INVALID_PROFIT_RATIO_PREVISTO",
     "SOTTO_MINIMO_NON_PIAZZABILE"),
    ("kill_switch: attivo", "kill_switch"),
    ("post_place:RuntimeError: x", "post_place"),
    ("greenup: place RIFIUTATO - rate", None),
    ("", None),
])
def test_p2_codice_dal_testo(testo, codice):
    assert MO.codice_errore(testo) == codice


def test_p2_strada_sincrona_ack_col_codice(amb):
    ws = amb.ch.collega("omega")
    _manda(amb, ws, _cmd("omega", 1, mode="live", side="LAY", price=18.0, size=0.43))
    ack = _ack(amb, ws)
    assert ack["accettato"] is False
    assert MO.codice_errore(ack["motivo"]) == "SOTTO_MINIMO_NON_PIAZZABILE"
    assert amb.market.calls == []


def test_p2_strada_asincrona_aggancio_evento_col_codice(amb, monkeypatch):
    """Comando ACCETTATO ``in_aggancio``, guardie rifatte all'arrivo del mercato: il
    rifiuto arriva solo come evento ``order`` (prima: senza nessun codice)."""
    auto = _auto()
    _monta(amb, auto)
    ws = amb.ch.collega("mike")
    _manda(amb, ws, _cmd("mike", 1, mode="live", market_id="1.560", price=3.0, size=5.0))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_IN_AGGANCIO)
    auto.giro()
    m = _nuovo_mercato(amb, "1.560")
    monkeypatch.setattr(LOW, "_kill_switch", lambda: True)   # freno tirato nell'attesa
    assert amb.motore.avanza_aggancio() == 1
    ev = _eventi(amb, ws, "mike-t1")
    assert [e["fase"] for e in ev] == ["rifiutato"]
    assert ev[0]["error_code"] == MO.M_KILL and ev[0]["errore"].startswith(MO.M_KILL)
    assert m.calls == []


def test_p2_strada_asincrona_sotto_minimo_dopo_l_aggancio(amb, monkeypatch):
    """Il verdetto dei minimi rifatto all'aggancio: un rifiuto SOTTO_MINIMO arriva
    nell'evento col suo codice (qui forzato sul secondo giro di ``_applica_minimi``)."""
    auto = _auto()
    _monta(amb, auto)
    ws = amb.ch.collega("mike")
    _manda(amb, ws, _cmd("mike", 1, mode="live", market_id="1.561", price=3.0, size=5.0))
    auto.giro()
    _nuovo_mercato(amb, "1.561")
    vero = amb.motore._applica_minimi

    def _rifiuta(piano: Dict[str, Any]) -> None:
        raise MO.Rifiuto(MO.M_SOTTO_MINIMO, "BACK 5.00 ... residuo da dichiarare al trader")

    monkeypatch.setattr(amb.motore, "_applica_minimi", _rifiuta)
    assert amb.motore.avanza_aggancio() == 1
    monkeypatch.setattr(amb.motore, "_applica_minimi", vero)
    ev = _eventi(amb, ws, "mike-t1")[-1]
    assert ev["fase"] == "rifiutato" and ev["error_code"] == "SOTTO_MINIMO_NON_PIAZZABILE"
    assert "trader" in ev["errore"]


def test_p2_errore_del_dispatch_evento_col_codice(amb, monkeypatch):
    def _rotto(*_a: Any, **_k: Any) -> None:
        raise ValueError("greenup: SOTTO_MINIMO_NON_PIAZZABILE: size 0.30 < minimo 1.00")

    monkeypatch.setattr(LOW, "_dispatch", _rotto)
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd("safe", 1, mode="live", price=3.0, size=5.0))
    ev = _eventi(amb, ws, "safe-t1")[-1]
    assert ev["fase"] == "rifiutato" and ev["error_code"] == "SOTTO_MINIMO_NON_PIAZZABILE"
    assert ev["errore"].startswith("greenup: SOTTO_MINIMO_NON_PIAZZABILE")
    # le chiavi dello specchio restano quelle delle colonne di betfair_live_orders
    assert "error_code" not in MO.CHIAVI_SPECCHIO and set(MO.CHIAVI_SPECCHIO) <= set(ev)


def test_p2_strada_della_coda_result_col_codice():
    righe: List[Any] = []

    class _Q:
        def update(self, p: Any) -> "_Q":
            righe.append(p)
            return self

        def eq(self, *_a: Any) -> "_Q":
            return self

        def insert(self, p: Any) -> "_Q":
            return self

        def execute(self) -> Any:
            return SimpleNamespace(data=[])

    sb = SimpleNamespace(table=lambda _n: _Q())
    row = {"id": 9, "action": "place", "market_id": "1.1", "selection_id": 7, "side": "lay"}
    # il testo e' quello che ``build_order`` solleva per una banca 0,43 (min_stake_rules)
    motivo = LB.min_stake_rules("it", "lay", 18.0, 0.43).reason
    LOW._write_error(sb, 9, row, "live", ValueError(motivo))
    assert righe and righe[0]["status"] == "error"
    assert righe[0]["result"]["error_code"] == "SOTTO_MINIMO_NON_PIAZZABILE"
    assert righe[0]["error"].startswith("SOTTO_MINIMO_NON_PIAZZABILE")


# ===========================================================================
# 3. cancel e replace su un ordine tradotto (canale: Safe, Mike, Omega, desktop)
# ===========================================================================
def test_p3_cancel_totale_annulla_l_ordine_vero(amb):
    ws = amb.ch.collega("safe")
    ev = _place_tradotto(amb, ws, 1)
    vero = amb.market.calls[0][0]
    _manda(amb, ws, _cmd("safe", 2, mode="live", azione="cancel", bet_id=ev["bet_id"]))
    assert _ack(amb, ws)["accettato"] is True
    assert amb.market.calls[-1] == ("cancel", vero, None)
    # anche l'evento del CANCEL e' nei termini del chiesto (mai la punta Under al bot)
    e = _eventi(amb, ws, "safe-t2")[-1]
    assert (e["selection_id"], e["side"], e["price"], e["size"]) == (OVER, "lay", 18.0, 0.43)
    assert e["riga_mandata"]["selection_id"] == UNDER


def test_p3_cancel_parziale_convertito_nei_termini_del_vero(amb):
    ws = amb.ch.collega("safe")
    ev = _place_tradotto(amb, ws, 1)
    vero = amb.market.calls[0][0]
    # il bot riduce di 0,10 la SUA banca Over (0,43 @18): sulla punta Under 7,31 sono
    # 0,10 x 7,31/0,43 = 1,70; resta 5,61 @1,06 (sopra 0,50, in banda)
    _manda(amb, ws, _cmd("safe", 2, mode="live", azione="cancel", bet_id=ev["bet_id"],
                         size_reduction=0.10))
    assert _ack(amb, ws)["accettato"] is True
    assert amb.market.calls[-1] == ("cancel", vero, 1.70)
    assert vero.order_type.size == 5.61


def test_p3_cancel_parziale_che_lascerebbe_sotto_050_rifiutato_col_residuo(amb):
    ws = amb.ch.collega("safe")
    ev = _place_tradotto(amb, ws, 1)
    n = len(amb.market.calls)
    # 0,42 x 17 = 7,14: sulla punta vera resterebbero 0,17 (sotto il floor 0,50)
    _manda(amb, ws, _cmd("safe", 2, mode="live", azione="cancel", bet_id=ev["bet_id"],
                         size_reduction=0.42))
    ack = _ack(amb, ws)
    assert ack["accettato"] is False
    assert ack["motivo"].startswith(MO.M_SOTTO_MINIMO) and "trader" in ack["motivo"]
    assert len(amb.market.calls) == n                 # nessun cancel partito


def test_p3_cancel_su_ordine_non_tradotto_invariato(amb):
    ws = amb.ch.collega("safe")
    amb.market.borsa = True
    _manda(amb, ws, _cmd("safe", 1, mode="live", price=3.0, size=5.0))
    bet = _eventi(amb, ws, "safe-t1")[-1]["bet_id"]
    _manda(amb, ws, _cmd("safe", 2, mode="live", azione="cancel", bet_id=bet,
                         size_reduction=1.0))
    assert amb.market.calls[-1][0] == "cancel" and amb.market.calls[-1][2] == 1.0


def test_p3_replace_su_tradotto_cancel_poi_nuovo_verdetto_mai_la_quota_dell_over(amb):
    ws = amb.ch.collega("safe")
    ev = _place_tradotto(amb, ws, 1)
    vero = amb.market.calls[0][0]
    _manda(amb, ws, _cmd("safe", 2, mode="live", azione="replace", bet_id=ev["bet_id"],
                         new_price=17.0))
    assert _ack(amb, ws)["accettato"] is True
    assert all(c[0] != "replace" for c in amb.market.calls)        # mai un replace del vero
    assert amb.market.calls[-1] == ("cancel", vero, None)
    # cancel confermato (ordine vero terminale): nuovo place della banca Over 0,43 @17,
    # tradotta di nuovo -> punta Under 0,43 x 16 = 6,88 @ 17/16 = 1,0625 -> tick su 1,07
    assert amb.motore.avanza_riprezzi() == 1
    nuovo = amb.market.calls[-1][0]
    assert (nuovo.selection_id, nuovo.side) == (UNDER, "BACK")
    assert (nuovo.order_type.price, nuovo.order_type.size) == (1.07, 6.88)
    e = _eventi(amb, ws, "safe-t2")[-1]
    assert (e["selection_id"], e["side"], e["price"], e["size"]) == (OVER, "lay", 17.0, 0.43)


def test_p3_replace_su_tradotto_non_ripiazza_prima_del_cancel_confermato(amb, monkeypatch):
    ws = amb.ch.collega("safe")
    ev = _place_tradotto(amb, ws, 1)
    # cancel accettato ma l'ordine vero resta vivo (Betfair non ha ancora confermato)
    monkeypatch.setattr(amb.market, "cancel_order",
                        lambda o, size_reduction=None: amb.market.calls.append(
                            ("cancel", o, size_reduction)) or True)
    _manda(amb, ws, _cmd("safe", 2, mode="live", azione="replace", bet_id=ev["bet_id"],
                         new_price=17.0))
    n = len(amb.market.calls)
    assert amb.motore.avanza_riprezzi() == 0 and len(amb.market.calls) == n
    assert amb.motore._riprezzi                     # in attesa, nessun doppio ordine


# ===========================================================================
# 5. l'equivalente solo su due esiti esaustivi
# ===========================================================================
def test_p5_tre_esiti_mai_equivalente(amb):
    amb.market.market_book = SimpleNamespace(
        status="OPEN", inplay=True, bet_delay=5, complete=True,
        runners=[SimpleNamespace(selection_id=s, handicap=0.0) for s in (1, 2, 3)])
    ws = amb.ch.collega("mike")
    _manda(amb, ws, _cmd("mike", 1, mode="live", selection_id=1, side="LAY", price=18.0,
                         size=0.43, reduces_liability=True))
    ack = _ack(amb, ws)
    assert ack["accettato"] is False and ack["motivo"].startswith(MO.M_SOTTO_MINIMO)
    assert amb.market.calls == []


@pytest.mark.parametrize("runner_kw,md", [
    ({"status": "REMOVED"}, None),
    ({}, SimpleNamespace(number_of_winners=2)),
    ({}, SimpleNamespace(number_of_winners=0)),
])
def test_p5_due_runner_ma_non_esaustivi_niente_equivalente(runner_kw, md):
    m = SimpleNamespace()
    _due_esiti(m, **runner_kw)
    m.market_book.market_definition = md
    assert MO.altro_runner_due_esiti(m, OVER) is None


def test_p5_due_esiti_attivi_un_vincitore_equivalente():
    m = SimpleNamespace()
    _due_esiti(m, status="ACTIVE")
    m.market_book.market_definition = SimpleNamespace(number_of_winners=1)
    assert MO.altro_runner_due_esiti(m, OVER) == (UNDER, 0.0)


def test_p5_equivalente_peggiore_oltre_la_tolleranza_mai_usato(monkeypatch):
    """La guardia ``TOLLERANZA_EQUIVALENZA`` (0,01): con il tick "mai peggiore" non
    scatta sui numeri veri (la size al centesimo sposta al piu' 0,005), quindi la si
    prova con un equivalente costruito apposta peggiore di 0,02 (chiude il buco R9
    della verifica del 02/10)."""
    vero = LB.equivalente_lato_opposto

    def _peggiore(side: str, price: float, size: float) -> Any:
        eq = vero(side, price, size)
        return LB.OrdineEquivalente(side=eq.side, price=eq.price, price_esatta=eq.price_esatta,
                                    size=eq.size, scarto_se_vince_chiesta=-0.02,
                                    scarto_se_vince_altra=eq.scarto_se_vince_altra)

    monkeypatch.setattr(LB, "equivalente_lato_opposto", _peggiore)
    v = LB.verdetto_minimi("it", "lay", 18.0, 0.43, altra_selezione=(UNDER, 0.0))
    assert v.esito == LB.VERDETTO_IMPOSSIBILE and "tolleranza" in v.motivo
    monkeypatch.setattr(LB, "equivalente_lato_opposto", vero)
    assert LB.verdetto_minimi("it", "lay", 18.0, 0.43,
                              altra_selezione=(UNDER, 0.0)).esito == LB.VERDETTO_EQUIVALENTE


# ===========================================================================
# 6. parcheggio della banca nella banda INVALID_PROFIT_RATIO
# ===========================================================================
def _banda_indipendente(size: float, price: float) -> bool:
    """Ricalcolo INDIPENDENTE della regola (RICERCA_STAKE_MINIMI_BETFAIR.md par. 2 e 6):
    0,80 <= arrotondato(size*(p-1)) / (size*(p-1)) <= 1,25, al centesimo, sia half-up
    sia half-even."""
    esatto = Decimal(f"{size:.2f}") * (Decimal(repr(price)) - 1)
    for m in (ROUND_HALF_UP, ROUND_HALF_EVEN):
        r = esatto.quantize(Decimal("0.01"), rounding=m)
        if not (Decimal("0.8") <= r / esatto <= Decimal("1.25")):
            return False
    return True


@pytest.mark.parametrize("centesimi", list(range(50, 100)))
def test_p6_parcheggio_lay_in_banda_per_ogni_residuo(centesimi):
    t = centesimi / 100
    q = S.quota_parcheggio_lontano("lay", t)
    assert q is not None and _banda_indipendente(t, q), (t, q)
    # ed e' la quota PIU' BASSA in banda (il parcheggio resta il piu' lontano possibile
    # dal mercato): il tick sotto e' fuori banda oppure sotto 1,01
    sotto = max(p for p in LB.PRICES_FLOAT if p < q - 1e-9) if q > 1.01 else None
    assert sotto is None or not _banda_indipendente(t, sotto)


@pytest.mark.parametrize("size,price,attesa", [
    (0.80, 1.01, True), (0.79, 1.01, False),     # forum per sviluppatori 2020
    (0.01, 1.80, True), (0.01, 1.79, False),
    (1.49, 1.01, False),                         # "rifiutato comunque"
    (0.70, 1.02, False), (0.70, 1.03, True),     # il caso del 01/10 (1+0,008/S)
])
def test_p6_misure_empiriche_spiegate_dalla_banda(size, price, attesa):
    assert S.rendimento_in_banda(size, price) is attesa
    assert _banda_indipendente(size, price) is attesa


def test_p6_ordine_finale_fuori_banda_rifiuto_dichiarato_nessun_ordine():
    # punta 0,50 @1,01: vincita 0,005 -> 0,01 (+100 %): Betfair rifiuterebbe il riprezzo
    p = S.pianifica_submin(side="back", target_price=1.01, target_size=0.50, jurisdiction="it")
    assert p.rifiuto and S.INVALID_PROFIT_RATIO_PREVISTO in p.rifiuto
    assert p.rifiuto.startswith(LB.SOTTO_MINIMO_NON_PIAZZABILE) and "trader" in p.rifiuto
    with pytest.raises(ValueError, match=S.INVALID_PROFIT_RATIO_PREVISTO):
        S.start_submin(side="back", target_price=1.01, target_size=0.50, jurisdiction="it")


def test_p6_parcheggio_070_ora_a_103_non_piu_a_102():
    p = S.pianifica_submin(side="lay", target_price=18.0, target_size=0.70, jurisdiction="it")
    assert p.rifiuto is None and p.park_price == 1.03


# ===========================================================================
# 7. guardie mancanti: REST diretto di omega_market, ordini dell'app (order_exec)
# ===========================================================================
def test_p7_place_order_live_sotto_minimo_rifiuto_certo_prima_della_rete(monkeypatch):
    chiamate: List[Any] = []
    monkeypatch.setattr(OM, "call_mutating", lambda fn: chiamate.append(fn) or (
        _ for _ in ()).throw(RuntimeError("rete")))
    with pytest.raises(OM.PlaceRifiutato) as ei:
        OM.place_order_live(market_id="1.1", selection_id=7, price=18.0, size=0.43,
                            event_id="E", side="lay")
    assert ei.value.error_code == "SOTTO_MINIMO_NON_PIAZZABILE" and chiamate == []
    with pytest.raises(OM.PlaceRifiutato):
        OM.place_order_live(market_id="1.1", selection_id=7, price=3.0, size=0.99,
                            event_id="E", side="back")
    assert chiamate == []
    # al minimo: la guardia lascia passare (si arriva alla rete, qui finta)
    with pytest.raises(RuntimeError, match="rete"):
        OM.place_order_live(market_id="1.1", selection_id=7, price=3.0, size=1.00,
                            event_id="E", side="back")
    assert len(chiamate) == 1


def test_p7_order_exec_usa_i_minimi_it():
    from Betfair import order_exec as OE
    from Betfair.stream.trading.minimi_it import IT_MIN_BACK

    assert OE.MIN_STAKE_EUR == IT_MIN_BACK == 1.00
    with pytest.raises(ValueError, match="sotto il minimo"):
        OE.place_order(1, "btts", "Yes", "back", 3.0, size=0.99, sb=object())
    with pytest.raises(Exception) as ei:          # 1,00 supera la guardia
        OE.place_order(1, "btts", "Yes", "back", 3.0, size=1.00, sb=object())
    assert "sotto il minimo" not in str(ei.value)


# ===========================================================================
# 9. doppia chiusura: green-up del runner sulla posizione del MERCATO a due esiti
# ===========================================================================
def _mercato_chiuso_per_equivalente() -> _MercatoGreenup:
    # punta Over 10 @4 (W=+30, L=-10), chiusa dal motore con la banca Over 40/18 @18
    # tradotta nella punta Under equivalente 2,2222 x 17 @ 18/17 (W=+2,2222, L=-37,7778):
    # piatta per il MERCATO (-7,7778 su entrambi gli esiti), aperta per la sola Over
    return _MercatoGreenup(
        "1.1",
        runners=[_runner(10, 17.5, 18.0), _runner(20, 1.05, 1.06)],
        exposures={10: {"matched_profit_if_win": 30.0, "matched_profit_if_lose": -10.0},
                   20: {"matched_profit_if_win": 2.2222,
                        "matched_profit_if_lose": -37.7778}})


def test_p9_green_up_dopo_chiusura_tradotta_non_rifa_l_hedge():
    market = _mercato_chiuso_per_equivalente()
    row = {"id": 301, "market_id": "1.1", "selection_id": 10, "handicap": 0,
           "action": "greenup", "params": {}}
    LOW._do_greenup(_Sb([row]), _fl(market), row, "paper", _STRAT)
    assert market.placed == []                         # nessuna seconda chiusura
    assert row["status"] == "done" and "MERCATO a due esiti" in row["result"]["detail"]


def test_p9_green_up_mercato_a_due_esiti_senza_chiusura_chiude_davvero():
    market = _mercato_chiuso_per_equivalente()
    market._exp.pop(20)                                # niente chiusura tradotta
    row = {"id": 302, "market_id": "1.1", "selection_id": 10, "handicap": 0,
           "action": "greenup", "params": {}}
    LOW._do_greenup(_Sb([row]), _fl(market), row, "paper", _STRAT)
    assert len(market.placed) == 1 and market.placed[0].side == "LAY"
    assert market.placed[0].order_type.size == pytest.approx(2.22)   # 40 / 18
