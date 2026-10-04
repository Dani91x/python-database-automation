"""01/10/2026 - RUNNER_MINIMI_CHIUSURE: i minimi .it valgono per OGNI ordine del runner.

Difetto (money-critical, tutti i bot): ``live_order_build.min_stake_rules`` esentava dai
minimi gli ordini ``reduces_liability=True`` (chiusure, green-up, hedge). Ipotesi FALSA:
Betfair .it non ha eccezioni per chi riduce l'esposizione; il 01/10 una banca di chiusura
da 0,43 @18 di Mike e' stata rifiutata ``INVALID_BET_SIZE`` 21 volte. In piu' la punta
era legalizzata PER DIFETTO ai 0,50 (residuo scoperto fino a 0,49), mentre l'API accetta
il centesimo (punta 7,47 accettata dall'app Betfair, stessa API).

04/10/2026 - CORRETTO: la "punta 7,47 accettata" era un ordine dell'UTENTE dal sito, non
del bot via API. Regola dell'utente: punta diretta da 1,00 in su SOLO a multipli di 0,50
(per difetto, residuo dichiarato). I test della punta al centesimo e dell'equivalente
7,31 sono stati riscritti (elenco nel referto AUDIT_2026-10-04/MINIMI_PUNTE_E_MIKE_CHIUSURA.md).

Cosa certifica (testo del 01/10, numeri aggiornati nei test):
  * i numeri di oggi: banca Over 0,43 @18 -> equivalente punta Under 7,31 @1,06 (tick in
    su: 1,05 sarebbe un limite peggiore del chiesto), equivalenza economica +-0,01 su
    entrambi gli esiti; nel motore l'ordine mandato e' l'equivalente, il diario lo dice,
    gli eventi tornano al bot nei termini del CHIESTO;
  * punta 7,47 accettata al centesimo;
  * banca 0,30: su un mercato a due esiti -> equivalente; senza equivalente -> impossibile
    (sotto 1,00 il place-and-trim non si tenta: regola del coordinatore dalle fonti .it);
    la quota di parcheggio di una banca piccola supera INVALID_PROFIT_RATIO;
  * punta 0,70 senza equivalente -> place-and-trim (parcheggio 1,00, finale >= 0,50);
  * importo sotto 1,00 senza equivalente -> rifiuto ``SOTTO_MINIMO_NON_PIAZZABILE``, mai
    un ordine;
  * ``reduces_liability=True`` NON esenta piu';
  * ripiego ai 0,50 SOLO dopo un ``INVALID_BET_SIZE`` reale e UNA sola volta; una taglia
    rifiutata non si ritenta identica.

Finti: il motore e il canale sono quelli VERI (fixture ``amb`` di
``test_motore_ordini_2026_09_24``: LocalChannel vero, client e strategie VERI di flumine,
ordini flumine VERI); il market_book ha le chiavi snake_case di betfairlightweight; la
risposta di placeOrders e' una ``responses.place_response`` con ``status``/``error_code``
come ``PlaceOrderInstructionReports``. Nessuna rete, nessun login, nessun ordine reale.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from flumine import BaseStrategy

from Betfair.stream import live_order_build as LB
from Betfair.stream import live_order_worker as LOW
from Betfair.stream import motore_ordini as MO
from Betfair.stream.trading import submin as S
from Betfair.stream.tests.test_motore_ordini_2026_09_24 import (  # noqa: F401 - fixture
    _ack,
    _cmd,
    _manda,
    amb,
)

OVER, UNDER = 47972, 47973
_STRAT = BaseStrategy(market_filter={}, name="minimi_test")


# ===========================================================================
# Regole pure (live_order_build)
# ===========================================================================
def test_punta_7_47_parte_a_7_00_col_residuo_dichiarato():
    """04/10/2026 (regola delle punte dell'utente; SOSTITUISCE il test del 01/10
    ``test_punta_al_centesimo_7_47_accettata``, che pretendeva la punta al centesimo
    sulla prova sbagliata di un ordine del SITO): da 1,00 in su la punta parte a
    multiplo di 0,50 per DIFETTO e il resto e' dichiarato."""
    v = LB.min_stake_rules("it", "back", 1.03, 7.47)
    assert v.valid and v.legalized_size == 7.00 and v.residuo == 0.47
    b = LB.build_order(SimpleNamespace(market_id="1.1"), strategy=_STRAT, selection_id=UNDER,
                       handicap=0.0, side="back", order_type="LIMIT", price=1.03, size=7.47,
                       liability=None, persistence="LAPSE", time_in_force=None,
                       min_fill_size=None, jurisdiction="it", max_stake=None,
                       customer_order_ref="awlq1")
    assert b.size == 7.00 and b.order.order_type.size == 7.00 and b.residuo == 0.47
    assert "residuo 0.47 NON piazzato" in b.note


def test_reduces_liability_non_esenta_piu():
    for lato, prezzo, size in (("lay", 18.0, 0.43), ("back", 3.0, 0.70), ("lay", 2.0, 0.99)):
        con = LB.min_stake_rules("it", lato, prezzo, size, reduces_liability=True)
        senza = LB.min_stake_rules("it", lato, prezzo, size)
        assert con == senza and con.valid is False
        assert con.reason.startswith(LB.SOTTO_MINIMO_NON_PIAZZABILE)
    with pytest.raises(ValueError, match=LB.SOTTO_MINIMO_NON_PIAZZABILE):
        LB.build_order(SimpleNamespace(market_id="1.1"), strategy=_STRAT, selection_id=OVER,
                       handicap=0.0, side="lay", order_type="LIMIT", price=18.0, size=0.43,
                       liability=None, persistence="LAPSE", time_in_force=None,
                       min_fill_size=None, jurisdiction="it", max_stake=None,
                       customer_order_ref="awlq2", reduces_liability=True)


def test_minimi_condivisi():
    from Betfair.stream.trading import minimi_it as MI
    # minimi definitivi .it (01/10/2026): diretto 1,00 / finale del trim 0,50 / mai sotto
    assert MI.IT_MIN_BACK == MI.IT_MIN_LAY == 1.00
    assert MI.SUBMIN_IMPORTO_FINALE_MIN == MI.IT_FLOOR_LEGGE == 0.50
    assert LB.IT_BACK_MIN_STAKE == MI.IT_MIN_BACK
    assert LB.IT_LAY_MIN_SIZE == MI.IT_MIN_LAY
    assert LB.SUBMIN_IMPORTO_FINALE_MIN == 0.50
    assert S.place_min_size("it", "lay") == LB.IT_LAY_MIN_SIZE
    from Betfair.omega import omega_market as OMK
    from Betfair.safe_strategy import execution as X
    assert OMK.SUBMIN_MIN_LAY == LB.IT_LAY_MIN_SIZE
    assert OMK.SUBMIN_MIN_BACK == LB.IT_BACK_MIN_STAKE
    assert X._min_size_live("lay") == LB.IT_LAY_MIN_SIZE


def test_numeri_di_oggi_equivalente_e_scarti():
    eq = LB.equivalente_lato_opposto("lay", 18.0, 0.43)
    assert eq.side == "back" and eq.size == 7.31
    assert eq.price_esatta == pytest.approx(18 / 17, abs=1e-6)
    assert eq.price == 1.06                    # tick IN SU: mai un limite peggiore
    # equivalenza economica (tutto abbinato al limite), +-0,01 su entrambi gli esiti
    over_vince_chiesto, under_vince_chiesto = -0.43 * 17, +0.43
    over_vince_eq, under_vince_eq = -7.31, 7.31 * (1.06 - 1.0)
    assert abs(over_vince_eq - over_vince_chiesto) <= 0.01
    assert abs(under_vince_eq - under_vince_chiesto) <= 0.01
    assert eq.scarto_se_vince_chiesta == pytest.approx(over_vince_eq - over_vince_chiesto,
                                                       abs=1e-4)
    assert eq.scarto_se_vince_altra == pytest.approx(under_vince_eq - under_vince_chiesto,
                                                     abs=1e-4)
    # 1,05 sarebbe stato peggiore del chiesto (equivale a bancare Over a 21)
    assert 1.05 / 0.05 > 18.0
    # 04/10/2026: la punta equivalente 7,31 NON e' un multiplo di 0,50: partirebbe solo
    # a 7,00, cioe' non equivalente. Il verdetto non la usa (0,43 < 0,50: impossibile)
    v = LB.verdetto_minimi("it", "lay", 18.0, 0.43, altra_selezione=(UNDER, 0.0))
    assert v.esito == LB.VERDETTO_IMPOSSIBILE and "non multiplo di 0.50" in v.motivo
    # con importi la cui punta equivalente e' un multiplo (banca 0,25 @19 -> punta
    # 4,50 @ 19/18 = 1,0556 -> tick IN SU 1,06) l'equivalente resta la via
    eq2 = LB.equivalente_lato_opposto("lay", 19.0, 0.25)
    assert (eq2.side, eq2.size, eq2.price) == ("back", 4.50, 1.06)
    v2 = LB.verdetto_minimi("it", "lay", 19.0, 0.25, altra_selezione=(UNDER, 0.0))
    assert v2.esito == LB.VERDETTO_EQUIVALENTE and v2.altra_selezione == (UNDER, 0.0)
    assert v2.equivalente == eq2 and v2.size == 4.50


def test_equivalente_tick_mai_peggiore_anche_quando_il_piu_vicino_e_sotto():
    # banca 0,30 @12 -> quota esatta 12/11 = 1,0909: il tick piu' vicino (1,09) sarebbe
    # una punta a un limite PEGGIORE del chiesto (= bancare a 12,11): si va a 1,10
    eq = LB.equivalente_lato_opposto("lay", 12.0, 0.30)
    assert eq.price == 1.10 and eq.size == 3.30
    assert min(eq.scarto_se_vince_chiesta, eq.scarto_se_vince_altra) >= -0.01


def test_equivalente_di_una_punta_e_una_banca_col_tick_in_giu():
    eq = LB.equivalente_lato_opposto("back", 6.0, 0.80)
    assert eq.side == "lay" and eq.size == 4.00 and eq.price == 1.20
    assert eq.scarto_se_vince_chiesta == pytest.approx(0.0, abs=1e-9)
    assert eq.scarto_se_vince_altra == pytest.approx(0.0, abs=1e-9)
    eq2 = LB.equivalente_lato_opposto("back", 3.07, 0.90)      # 3.07/2.07 = 1.4831
    assert eq2.price == 1.48                                      # tick IN GIU' per la banca
    assert min(eq2.scarto_se_vince_chiesta, eq2.scarto_se_vince_altra) >= -0.01


def test_banca_030_due_esiti_equivalente_altrimenti_impossibile():
    # 04/10/2026: l'equivalente (punta 5,10) non e' un multiplo di 0,50 -> non si usa;
    # con 0,30 @21 la punta equivalente e' 6,00 @1,05: si usa
    v2 = LB.verdetto_minimi("it", "lay", 18.0, 0.30, altra_selezione=(UNDER, 0.0))
    assert v2.esito == LB.VERDETTO_IMPOSSIBILE and "non multiplo" in v2.motivo
    v2b = LB.verdetto_minimi("it", "lay", 21.0, 0.30, altra_selezione=(UNDER, 0.0))
    assert v2b.esito == LB.VERDETTO_EQUIVALENTE and v2b.equivalente.size == 6.00
    v3 = LB.verdetto_minimi("it", "lay", 18.0, 0.30)
    assert v3.esito == LB.VERDETTO_IMPOSSIBILE and v3.size is None
    assert v3.motivo.startswith(LB.SOTTO_MINIMO_NON_PIAZZABILE)
    assert "0,50 non si tenta mai" in v3.motivo and "trader" in v3.motivo
    # 0,60 senza equivalente: place-and-trim (finale >= 0,50, parcheggio 1,00)
    v4 = LB.verdetto_minimi("it", "lay", 18.0, 0.60)
    assert v4.esito == LB.VERDETTO_SUBMIN


def test_punta_sotto_un_euro_senza_equivalente_va_al_place_and_trim():
    assert LB.verdetto_minimi("it", "back", 3.0, 1.50).esito == LB.VERDETTO_DIRETTO
    v = LB.verdetto_minimi("it", "back", 3.0, 0.70)
    assert v.esito == LB.VERDETTO_SUBMIN and v.size == 0.70
    assert "bet delay" in v.motivo
    # sotto 0,50 (floor di legge): impossibile
    v2 = LB.verdetto_minimi("it", "back", 3.0, 0.49)
    assert v2.esito == LB.VERDETTO_IMPOSSIBILE
    # esecutore senza place-and-trim (tennis): impossibile anche a 0,70
    v3 = LB.verdetto_minimi("it", "back", 3.0, 0.70, submin_disponibile=False)
    assert v3.esito == LB.VERDETTO_IMPOSSIBILE


def test_equivalente_anch_esso_sotto_il_minimo_non_si_usa():
    # back 0,80 @1,30 -> banca 0,24 @4,33: sotto la banca minima -> place-and-trim
    v = LB.verdetto_minimi("it", "back", 1.30, 0.80, altra_selezione=(UNDER, 0.0))
    assert v.esito == LB.VERDETTO_SUBMIN
    assert "anch'esso sotto il minimo" in v.motivo


def test_riporta_abbinato_all_originale():
    assert LB.riporta_abbinato_all_originale("lay", 18.0, 0.43, 7.31, 7.31) == (0.43, 18.0)
    ab, q = LB.riporta_abbinato_all_originale("lay", 18.0, 0.43, 7.31, 3.66)
    assert ab == 0.22 and ab * (q - 1.0) == pytest.approx(3.66, abs=1e-3)  # liability esatta
    assert LB.riporta_abbinato_all_originale("lay", 18.0, 0.43, 7.31, 0.0) == (0.0, None)


def test_ripiego_ai_050_puro():
    assert LB.size_ripiego_punta(7.47) == 7.00
    assert LB.size_ripiego_punta(2.20) == 2.00
    assert LB.size_ripiego_punta(1.30) == 1.00
    assert LB.size_ripiego_punta(7.50) is None          # gia' multiplo: niente ripiego
    assert LB.size_ripiego_punta(0.90) is None          # sotto il minimo: niente ripiego
    assert LB.punta_da_sorvegliare_per_ripiego("back", 7.47) is True
    assert LB.punta_da_sorvegliare_per_ripiego("lay", 7.47) is False


def test_parcheggio_della_banca_supera_invalid_profit_ratio():
    assert S.quota_parcheggio_lontano("lay", 0.30) == 1.03
    assert S.quota_parcheggio_lontano("lay", 0.43) == 1.02
    assert S.quota_parcheggio_lontano("lay", 0.80) == 1.01
    assert S.quota_parcheggio_lontano("back", 1.50) == 1000.0
    for t in (0.30, 0.43, 0.80, 0.95):
        q = S.quota_parcheggio_lontano("lay", t)
        assert t * (q - 1.0) >= S.LIABILITY_MIN_RESIDUO_LAY - 1e-9
    p = S.pianifica_submin(side="lay", target_price=18.0, target_size=0.30, jurisdiction="it")
    assert p.park_price == 1.03 and p.park_size == LB.IT_LAY_MIN_SIZE
    # parcheggio lontano che si abbinerebbe subito: rifiuto, nessun ordine
    p2 = S.pianifica_submin(side="lay", target_price=18.0, target_size=0.30, jurisdiction="it",
                            best_back=17.0, best_lay=1.02)
    assert p2.rifiuto and p2.rifiuto.startswith("SUBMIN_PARCHEGGIO_ABBINABILE")


def test_regola_d_ingresso_della_macchina():
    with pytest.raises(ValueError, match=LB.SOTTO_MINIMO_NON_PIAZZABILE):
        S.verifica_importo_finale("lay", 0.49)
    S.verifica_importo_finale("back", 0.50)


# ===========================================================================
# Worker: chiusure di greenup/cash-out e place della coda
# ===========================================================================
class _MercatoSpia:
    def __init__(self) -> None:
        self.market_id = "1.1"
        self.placed: List[Any] = []

    def place_order(self, order: Any, **_k: Any) -> bool:
        self.placed.append(order)
        return True


def test_chiusura_live_sotto_minimo_mai_un_place_diretto(monkeypatch):
    chiamate: List[Dict[str, Any]] = []

    def _finto(*_a: Any, **kw: Any) -> Any:
        chiamate.append(kw)
        return SimpleNamespace(step=SimpleNamespace(value="done")), None

    monkeypatch.setattr(LOW, "_place_sub_minimum", _finto)
    monkeypatch.setattr(LOW, "_jurisdiction", lambda: "it")
    monkeypatch.setattr(LOW, "_rate_guard", lambda: None)
    m = _MercatoSpia()
    ordine, prezzo, size = LOW._costruisci_chiusura(
        m, strategy=_STRAT, selection_id=10, handicap=0.0, side="back", price=3.0,
        size=0.70, persistence="LAPSE", cust_ref="awlq9", mode="live")
    assert ordine is None and size == 0.70          # non costruito: Betfair lo rifiuterebbe
    stato = LOW._place_closing_leg(
        None, m, order=ordine, strategy=_STRAT, market_id="1.1", selection_id=10,
        handicap=0.0, side="back", price=prezzo, size=size, cust_ref="awlq9",
        what="greenup", mode="live", params={})
    assert stato is not None and len(chiamate) == 1 and chiamate[0]["size"] == 0.70
    assert m.placed == []                            # nessun place diretto sotto il minimo


def test_chiusura_live_opt_out_rifiuto_esplicito(monkeypatch):
    monkeypatch.setattr(LOW, "_place_sub_minimum",
                        lambda *_a, **_k: pytest.fail("opt-out: niente place-and-trim"))
    monkeypatch.setattr(LOW, "_jurisdiction", lambda: "it")
    m = _MercatoSpia()
    with pytest.raises(ValueError, match=LB.SOTTO_MINIMO_NON_PIAZZABILE):
        LOW._place_closing_leg(
            None, m, order=None, strategy=_STRAT, market_id="1.1", selection_id=10,
            handicap=0.0, side="back", price=3.0, size=0.70, cust_ref="awlq10",
            what="greenup", mode="live", params={"allow_sub_minimum": False})
    assert m.placed == []


# ===========================================================================
# Motore del canale (VERO): equivalente, eventi riportati, rifiuti, ripiego 0,50
# ===========================================================================
def _due_esiti(market: Any) -> None:
    market.market_book = SimpleNamespace(
        status="OPEN", inplay=True, bet_delay=5, complete=True,
        runners=[SimpleNamespace(selection_id=OVER, handicap=0.0),
                 SimpleNamespace(selection_id=UNDER, handicap=0.0)])


def _riga_specchio(cust: str, **kw: Any) -> Dict[str, Any]:
    r = {k: None for k in MO.CHIAVI_SPECCHIO}
    r.update({"client_order_ref": cust, "mode": "live", "market_id": "1.234",
              "handicap": 0.0, "order_type": "LIMIT", "persistence": "LAPSE"})
    for k in MO._CHIAVI_ZERO:
        r[k] = 0.0
    r.update(kw)
    return r


@pytest.fixture()
def traduzione_mike(monkeypatch):
    """02/10/2026 (RUNNER_MINIMI_CORREZIONI, punto 11): la traduzione nell'equivalente vale
    solo per gli attori di ``minimi_it.ATTORI_CON_TRADUZIONE`` (oggi nessuno). Questi
    test collaudano la MACCHINA della traduzione: abilitano 'mike' SOLO per la prova."""
    from Betfair.stream.trading import minimi_it as MI

    monkeypatch.setattr(MI, "ATTORI_CON_TRADUZIONE", frozenset({"mike"}))


def test_motore_banca_025_mandata_come_punta_450_e_riportata_al_bot(amb, traduzione_mike):
    """04/10/2026: numeri cambiati (era banca 0,43 @18 -> punta 7,31 @1,06). La punta
    equivalente deve essere un multiplo di 0,50 (regola delle punte dell'utente),
    altrimenti il verdetto non la usa: banca 0,25 @19 -> punta 4,50 @1,06."""
    _due_esiti(amb.market)
    ws = amb.ch.collega("mike")
    _manda(amb, ws, _cmd("mike", 1, mode="live", selection_id=OVER, side="LAY",
                         price=19.0, size=0.25, reduces_liability=True))
    assert _ack(amb, ws)["accettato"] is True
    assert len(amb.market.calls) == 1
    ordine, _ref, client = amb.market.calls[0]
    assert client is amb.reale
    assert ordine.selection_id == UNDER and ordine.side == "BACK"
    assert ordine.order_type.price == 1.06 and ordine.order_type.size == 4.50
    assert ordine.context.get("reduces_liability") is True       # informazione, resta
    # diario: la traduzione con chiesto e mandato, PRIMA della riga 'ordine'
    righe = amb.diario.leggi([amb.diario._giorno()])
    tipi = [r["tipo"] for r in righe]
    assert "tradotto" in tipi and tipi.index("tradotto") < tipi.index("ordine")
    tr = [r for r in righe if r["tipo"] == "tradotto"][0]
    assert tr["originale"] == {"selection_id": OVER, "handicap": 0.0, "side": "lay",
                               "price": 19.0, "size": 0.25}
    assert tr["mandato"] == {"selection_id": UNDER, "handicap": 0.0, "side": "back",
                             "price": 1.06, "size": 4.50}
    # evento 'inviato': nei termini del CHIESTO
    ev = amb.ch.per_ws(ws, "order")[-1]["d"]
    assert ev["selection_id"] == OVER and ev["side"] == "lay"
    assert ev["price"] == 19.0 and ev["size"] == 0.25
    assert ev["riga_mandata"]["selection_id"] == UNDER and ev["riga_mandata"]["size"] == 4.50
    cust = ev["client_order_ref"]
    # specchio: punta Under abbinata 4,50 @1,06 -> il bot vede banca Over 0,25 @19
    amb.motore._su_riga_specchio(_riga_specchio(
        cust, selection_id=UNDER, side="back", price=1.06, size=4.50, size_matched=4.50,
        average_price_matched=1.06, size_remaining=0.0, status="EXECUTION_COMPLETE",
        bet_id="99"))
    ev = amb.ch.per_ws(ws, "order")[-1]["d"]
    assert ev["fase"] == "abbinato"
    assert ev["selection_id"] == OVER and ev["side"] == "lay" and ev["size"] == 0.25
    assert ev["size_matched"] == 0.25 and ev["average_price_matched"] == pytest.approx(19.0)
    assert ev["size_remaining"] == 0.0
    assert ev["tradotto"]["mandato"]["size"] == 4.50
    assert ev["riga_mandata"]["size_matched"] == 4.50


def test_motore_banca_043_la_punta_equivalente_7_31_non_e_piu_mandata(amb, traduzione_mike):
    """04/10/2026: i numeri di Ashdod (banca 0,43 @18 -> punta 7,31) col verdetto nuovo:
    7,31 non e' un multiplo di 0,50, l'equivalente non parte e la banca 0,43 (< 0,50)
    e' un rifiuto esplicito, MAI un ordine verso Betfair."""
    _due_esiti(amb.market)
    ws = amb.ch.collega("mike")
    _manda(amb, ws, _cmd("mike", 1, mode="live", selection_id=OVER, side="LAY",
                         price=18.0, size=0.43, reduces_liability=True))
    ack = _ack(amb, ws)
    assert ack["accettato"] is False and ack["motivo"].startswith(MO.M_SOTTO_MINIMO)
    assert "non multiplo di 0.50" in ack["motivo"]
    assert amb.market.calls == []


def test_motore_sotto_minimo_senza_vie_rifiuto_esplicito_mai_rest(amb):
    # mercato NON a due esiti (nessun market_book): banca 0,43 -> impossibile
    ws = amb.ch.collega("mike")
    _manda(amb, ws, _cmd("mike", 2, mode="live", side="LAY", price=18.0, size=0.43,
                         reduces_liability=True))
    ack = _ack(amb, ws)
    assert ack["accettato"] is False and ack["motivo"].startswith(MO.M_SOTTO_MINIMO)
    assert "trader" in ack["motivo"]
    assert amb.market.calls == []


def test_motore_punta_070_senza_equivalente_va_al_place_and_trim(amb):
    amb.market.borsa = True
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd("safe", 3, mode="live", price=3.0, size=0.70,
                         reduces_liability=True))
    assert _ack(amb, ws)["accettato"] is True
    ordine = amb.market.calls[0][0]
    assert ordine.order_type.size == 1.00 and ordine.order_type.price == 1000.0
    assert amb.motore._submin


def _rifiuta_betfair(ordine: Any, codice: str = "INVALID_BET_SIZE") -> None:
    """Come ``BetfairExecution.execute_place`` su FAILURE: risposta registrata,
    residuo azzerato, ordine completato (``order.execution_complete``)."""
    ordine.responses.placed(SimpleNamespace(status="FAILURE", error_code=codice,
                                            bet_id=None, order_status=None))
    ordine.execution_complete()


def test_motore_punta_7_47_parte_7_00_prima_dell_invio_e_nessun_ripiego_dopo(amb):
    """04/10/2026 (regola delle punte dell'utente; SOSTITUISCE
    ``test_motore_ripiego_050_solo_dopo_invalid_bet_size_e_una_volta``, che mandava
    7,47 al centesimo e ripiegava ai 0,50 SOLO dopo il rifiuto vero): la punta parte
    GIA' a 7,00 col residuo 0,47 dichiarato in ogni evento (``punta_050``). Se Betfair
    rifiutasse anche 7,00 (gia' multiplo): nessun ripiego, rifiuto dichiarato, la
    taglia rifiutata non si ritenta identica."""
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd("safe", 4, mode="live", price=1.03, size=7.47))
    assert _ack(amb, ws)["accettato"] is True
    assert [c[0].order_type.size for c in amb.market.calls] == [7.00]   # mai 7,47
    primo = amb.market.calls[0][0]
    ev = amb.ch.per_ws(ws, "order")[-1]["d"]
    cust1 = ev["client_order_ref"]
    assert ev["ref"] == "safe-t4" and ev["fase"] == "inviato" and ev["size"] == 7.00
    assert ev["punta_050"]["chiesto"] == 7.47 and ev["punta_050"]["piazzato"] == 7.00
    assert ev["punta_050"]["residuo"] == 0.47
    assert amb.motore.avanza_sorvegliati() == 0 and len(amb.market.calls) == 1
    _rifiuta_betfair(primo)
    amb.motore._su_riga_specchio(_riga_specchio(
        cust1, selection_id=47972, side="back", price=1.03, size=7.00,
        status="EXECUTION_COMPLETE"))
    assert amb.motore.avanza_sorvegliati() == 0          # 7,00 e' gia' multiplo
    assert len(amb.market.calls) == 1
    ev = amb.ch.per_ws(ws, "order")[-1]["d"]
    assert ev["fase"] == "rifiutato" and ev["errore_betfair"] == "INVALID_BET_SIZE"
    assert ev["ripiego_050"]["eseguito"] is False
    assert ev["punta_050"]["residuo"] == 0.47             # la dichiarazione resta
    # la stessa taglia (7,47 -> 7,00) non si ritenta identica: rifiuto PRIMA dell'invio
    _manda(amb, ws, _cmd("safe", 5, mode="live", price=1.03, size=7.47))
    ack = _ack(amb, ws)
    assert ack["accettato"] is False and ack["motivo"].startswith(MO.M_SOTTO_MINIMO)
    assert "non si ritenta identico" in ack["motivo"]
    assert len(amb.market.calls) == 1


def test_motore_nessun_ripiego_senza_invalid_bet_size(amb):
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd("safe", 6, mode="live", price=1.03, size=7.47))
    primo = amb.market.calls[0][0]
    _rifiuta_betfair(primo, codice="BET_TAKEN_OR_LAPSED")
    assert amb.motore.avanza_sorvegliati() == 0
    assert len(amb.market.calls) == 1
    assert amb.motore._sorvegliati == {}
    # nessuna taglia ricordata: lo stesso importo si puo' mandare di nuovo
    _manda(amb, ws, _cmd("safe", 7, mode="live", price=1.03, size=7.47))
    assert _ack(amb, ws)["accettato"] is True and len(amb.market.calls) == 2


def test_motore_aggancio_ripete_le_guardie_sull_ordine_chiesto(amb, traduzione_mike):
    """Idempotenza: ``_controlla`` due volte sullo stesso piano (aggancio al volo) riparte
    dall'ordine CHIESTO, mai dalla traduzione del giro prima."""
    _due_esiti(amb.market)
    # 04/10/2026: numeri con la punta equivalente multipla di 0,50 (era 0,43 @18 -> 7,31)
    piano = MO.valida_comando("mike", _cmd("mike", 8, mode="live", selection_id=OVER,
                                           side="LAY", price=19.0, size=0.25,
                                           reduces_liability=True))
    amb.motore._controlla(piano, piano["creato_ms"])
    assert piano["riga"]["selection_id"] == UNDER and piano["riga"]["size"] == 4.50
    amb.motore._controlla(piano, piano["creato_ms"])
    assert piano["riga"]["selection_id"] == UNDER and piano["riga"]["size"] == 4.50
    assert piano["tradotto"]["originale"]["size"] == 0.25


def test_motore_aggancio_punta_050_riparte_dal_chiesto(amb):
    """04/10/2026: anche la punta arrotondata ai 0,50 e' idempotente sull'aggancio:
    ``_controlla`` due volte riparte da 7,47 chiesto, mai da 7,00 del giro prima."""
    piano = MO.valida_comando("safe", _cmd("safe", 9, mode="live", price=1.03, size=7.47))
    amb.motore._controlla(piano, piano["creato_ms"])
    assert piano["riga"]["size"] == 7.00 and piano["punta_050"]["chiesto"] == 7.47
    amb.motore._controlla(piano, piano["creato_ms"])
    assert piano["riga"]["size"] == 7.00 and piano["punta_050"]["chiesto"] == 7.47
    assert piano["minimi_originale"]["size"] == 7.47
