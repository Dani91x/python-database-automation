"""CANTIERE 9 (08/10) - i guasti e i controlli di `backtest/scavalco_rifiuti.py`.

1. Il guasto dell'INGRESSO ABBINATO IN PARTE e il finto Betfair coi CODICI VERI,
   con oggetti VERI: `FlumineSimulation` + `SimulatedMiddleware` + `MotoreReplay`
   del banco, `MarketBook` di betfairlightweight, `LimitOrder` LAPSE (la scena del
   test del mercato che attraversa). Il bot non c'e': qui si prova il GUASTO.
2. I controlli SV1-SV5 / RC1-RC4 su ordini con le chiavi di flumine (`side`,
   `order_type.price/size`, `size_matched`, `average_price_matched`,
   `size_remaining`, `status` Enum, `date_time_created`, `trade.strategy`) e slot
   con i campi veri di `scalper_bot._Slot` (`status`, `submins`, `entry_*`,
   `close`, `flatten_orders`).
3. Il contratto col banco dello scalper (scenari registrati, paper, Applica bot)
   e col bot (`_SCAVALCHI_MAX_PER_CICLO`, lettura del codice di rifiuto).
ASCII-only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pytest

from Betfair.stream.backtest import banco_comune as B
from Betfair.stream.backtest import scavalco_rifiuti as SR
from Betfair.stream.tests.test_banco_attraversa_2026_10_08 import MID, SEL, T0, _Scena, _book


# ===========================================================================
# 1. IL GUASTO, con flumine vero
# ===========================================================================
def _libro(t: float, tv=()) -> Any:
    # BACK @2,00 si abbina subito (2,00 offerta in punta), LAY @2,02 subito
    return _book(t, atb=[(2.0, 100.0)], atl=[(2.02, 100.0)], tv=tv)


def _scena(guasto: Any, n: int = 40) -> _Scena:
    sc = _Scena(_libro(0), [_libro(t) for t in range(1, n)])
    # tetti di flumine aperti, come nel banco (si certificano i limiti del bot)
    sc.strategia.max_live_trade_count = 1000
    sc.strategia.max_trade_count = 1000
    sc.motore.guasto_chiusure = guasto
    return sc


def _con_scena(guasto: Any, corpo: Any) -> _Scena:
    with B.simulazione_flumine():
        sc = _scena(guasto)
        with sc.q.simulated_datetime:
            sc.q.simulated_datetime(_libro(0).publish_time)
            corpo(sc)
    return sc


def _annulla(sc: _Scena, o: Any) -> None:
    sc.mercato.cancel_order(o)
    sc.motore.attendi_esecuzione(MID)


def test_guasto_ingresso_il_gruppo_abbina_al_piu_029_in_tutto():
    g = SR.GuastoIngressoParziale(ruolo=lambda o: "ingresso")
    esito: Dict[str, Any] = {}

    def corpo(sc: _Scena) -> None:
        back = sc.piazza("BACK", 2.0, 25.0)
        lay = sc.piazza("LAY", 2.02, 25.0)
        esito["back"], esito["lay"] = back, lay
        esito["vivi"] = (back.size_remaining, lay.size_remaining)
        _annulla(sc, back)
        _annulla(sc, lay)
        esito["finiti"] = g.aggiorna(_ms_ora(sc))
        # il guasto e' finito su questa selezione: il mercato torna quello vero
        esito["dopo"] = sc.piazza("BACK", 2.0, 25.0)

    _con_scena(g, corpo)
    back, lay = esito["back"], esito["lay"]
    assert back.size_matched == pytest.approx(0.29)
    assert lay.size_matched == 0.0                 # il tetto e' del GRUPPO
    assert esito["vivi"] == (pytest.approx(24.71), pytest.approx(25.0))
    assert len(esito["finiti"]) == 1
    rec = esito["finiti"][0]
    assert rec["abbinato"] == pytest.approx(0.29)
    lato, imp, _d = rec["chiusura"]
    assert lato == "LAY" and imp == pytest.approx(0.29, abs=0.01) and imp < 0.50
    assert esito["dopo"].size_matched == pytest.approx(25.0)


def test_senza_guasto_lo_stesso_ingresso_abbina_25():
    """Controllo: il mercato della scena abbina davvero 25 (il tetto e' del guasto)."""
    esito: Dict[str, Any] = {}

    def corpo(sc: _Scena) -> None:
        esito["back"] = sc.piazza("BACK", 2.0, 25.0)

    _con_scena(None, corpo)
    assert esito["back"].size_matched == pytest.approx(25.0)


def test_guasto_ingresso_senza_abbinato_si_riarma():
    """Un gruppo morto senza un centesimo abbinato non ha avuto effetto: il
    gruppo dopo e' colpito."""
    g = SR.GuastoIngressoParziale(ruolo=lambda o: "ingresso")
    esito: Dict[str, Any] = {}

    def corpo(sc: _Scena) -> None:
        lontana = sc.piazza("BACK", 3.0, 25.0)          # non si abbina
        _annulla(sc, lontana)
        esito["riarmi"] = (g.aggiorna(_ms_ora(sc)), g.senza_effetto)
        esito["vera"] = sc.piazza("BACK", 2.0, 25.0)

    _con_scena(g, corpo)
    assert esito["riarmi"] == ([], 1)
    assert esito["vera"].size_matched == pytest.approx(0.29)


def test_guasto_ingresso_non_tocca_le_uscite():
    g = SR.GuastoIngressoParziale(ruolo=lambda o: "uscita")
    esito: Dict[str, Any] = {}

    def corpo(sc: _Scena) -> None:
        esito["o"] = sc.piazza("BACK", 2.0, 25.0)

    _con_scena(g, corpo)
    assert esito["o"].size_matched == pytest.approx(25.0)
    assert g.gruppi == {}


def _ms_ora(sc: _Scena) -> int:
    return int(sc.mercato.market_book.publish_time_epoch)


# ---------------------------------------------------------------- codici veri
def test_rifiuto_place_col_codice_vero_e_il_bot_lo_legge():
    from flumine.simulation.utils import SimulatedPlaceResponse

    from Betfair.stream.scalper.scalper_bot import ScalperStrategy

    r = SR.RifiutiConCodice(tipo=lambda o: "scavalco")
    esito: Dict[str, Any] = {}

    def corpo(sc: _Scena) -> None:
        esito["primo"] = sc.piazza("BACK", 2.0, 1.0)
        esito["secondo"] = sc.piazza("BACK", 2.0, 1.0)

    _con_scena(r, corpo)
    o = esito["primo"]
    pr = o.responses.place_response
    assert type(pr) is SimulatedPlaceResponse
    assert (pr.status, pr.error_code) == ("FAILURE", "INVALID_BET_SIZE")
    assert o.size_matched == 0.0 and o.size_remaining == 0.0 and o.bet_id is None
    assert o.status.name == "EXECUTION_COMPLETE"
    # la lettura del BOT (`order.responses.place_response.error_code`)
    assert ScalperStrategy._codice_rifiuto(o) == "INVALID_BET_SIZE"
    # solo il PRIMO del tipo
    assert esito["secondo"].size_matched == pytest.approx(1.0)
    assert [x["codice"] for x in r.fatti] == ["INVALID_BET_SIZE"]
    assert r.fatti[0]["ms"] is not None


def test_la_risposta_ha_le_chiavi_della_risposta_vera_di_place_orders():
    """Il finto parla come il vero: l'oggetto di flumine ha le stesse chiavi della
    `PlaceInstructionReport` di betfairlightweight (tranne l'istruzione eco)."""
    from betfairlightweight.resources.bettingresources import PlaceOrderInstructionReports
    from flumine.simulation.utils import SimulatedPlaceResponse

    vero = PlaceOrderInstructionReports(
        status="FAILURE", errorCode="INVALID_PROFIT_RATIO",
        instruction={"selectionId": 1, "handicap": 0, "side": "LAY", "orderType": "LIMIT",
                     "limitOrder": {"size": 1.0, "price": 1.02, "persistenceType": "LAPSE"}})
    chiavi_vere = {k for k in vars(vero) if not k.startswith("_")} - {"instruction"}
    assert set(vars(SimulatedPlaceResponse("FAILURE"))) == chiavi_vere
    assert vero.error_code == "INVALID_PROFIT_RATIO"


@pytest.mark.parametrize("tipo,codice", [("scavalco", "INVALID_BET_SIZE"),
                                         ("parcheggio", "INVALID_PROFIT_RATIO")])
def test_ogni_tipo_ha_il_suo_codice(tipo, codice):
    r = SR.RifiutiConCodice(tipo=lambda o: tipo)
    esito: Dict[str, Any] = {}

    def corpo(sc: _Scena) -> None:
        esito["o"] = sc.piazza("LAY", 1.02 if tipo == "parcheggio" else 2.02, 1.0)

    _con_scena(r, corpo)
    assert esito["o"].responses.place_response.error_code == codice


def test_rimpiazzo_rifiutato_come_in_produzione():
    """replaceOrders: la cancel del parcheggio riesce, il place del sostituto torna
    BET_TAKEN_OR_LAPSED. Come `BetfairExecution.execute_replace` (sostituto creato
    solo su SUCCESS): nessun sostituto nel Trade ne' nel blotter, parcheggio
    annullato (la cancel non si ritira)."""
    from flumine.order.orderpackage import OrderPackageType

    r = SR.RifiutiConCodice(tipo=lambda o: None)
    esito: Dict[str, Any] = {}

    def corpo(sc: _Scena) -> None:
        park = sc.piazza("LAY", 1.02, 1.0)          # non abbinabile
        assert park.size_remaining == pytest.approx(1.0)
        sc.mercato.replace_order(park, 2.04)
        sc.motore.attendi_esecuzione(MID, tipi=(OrderPackageType.REPLACE,))
        sc.q._process_simulated_orders(sc.mercato)
        esito["park"] = park
        esito["blotter"] = list(sc.mercato.blotter)

    _con_scena(r, corpo)
    park = esito["park"]
    assert park.trade.orders == [park]
    assert park.size_remaining == 0.0 and park.size_cancelled == pytest.approx(1.0)
    assert [o for o in esito["blotter"] if o is not park] == []
    assert [(x["tipo"], x["codice"], x["operazione"]) for x in r.fatti] == [
        ("rimpiazzo", "BET_TAKEN_OR_LAPSED", "replaceOrders")]
    assert r.fatti[0]["ms"] is not None and r.fatti[0]["sostituito"] is park


def test_rimpiazzo_senza_guasto_nasce():
    """Controllo: lo stesso replace, senza guasto, crea il sostituto a 2,04."""
    from flumine.order.orderpackage import OrderPackageType

    esito: Dict[str, Any] = {}

    def corpo(sc: _Scena) -> None:
        park = sc.piazza("LAY", 1.02, 1.0)
        sc.mercato.replace_order(park, 2.04)
        sc.motore.attendi_esecuzione(MID, tipi=(OrderPackageType.REPLACE,))
        esito["park"] = park

    _con_scena(None, corpo)
    tr = esito["park"].trade.orders
    assert len(tr) == 2 and tr[1].order_type.price == 2.04


# ===========================================================================
# 2. I CONTROLLI, su ordini e slot con le chiavi veri
# ===========================================================================
class _Strategia:
    flatten_min_interval_ms = 1500
    event_loss_cap = 1.5

    def __init__(self) -> None:
        self._slots: Dict[Tuple[str, int], Any] = {}


def _ordine(strategia: Any, lato: str, prezzo: float, chiesto: float, abbinato: float,
            vivo: bool = False, t_ms: int = T0, sel: int = SEL) -> Any:
    from flumine.order.order import OrderStatus

    o = SimpleNamespace(
        id="o%d" % id(object()), market_id=MID, selection_id=sel, side=lato,
        order_type=SimpleNamespace(price=prezzo, size=chiesto),
        size_matched=abbinato, average_price_matched=prezzo if abbinato else 0.0,
        size_remaining=round(chiesto - abbinato, 2) if vivo else 0.0,
        status=OrderStatus.EXECUTABLE if vivo else OrderStatus.EXECUTION_COMPLETE,
        # flumine timbra un datetime NAIVE in UTC
        date_time_created=datetime.fromtimestamp(t_ms / 1000.0,
                                                 tz=timezone.utc).replace(tzinfo=None),
        trade=SimpleNamespace(strategy=strategia, orders=[]), notes={})
    o.trade.orders.append(o)
    return o


class _Banco:
    """Il minimo del banco dello scalper che la sorveglianza legge."""

    def __init__(self, scenario: str = SR.SCENARIO_INGRESSO) -> None:
        self.s = _Strategia()
        self.blotter: List[Any] = []
        self.attivita: List[Tuple[str, Dict[str, Any], int]] = []
        # gli ordini che la credenza del bot tiene come INGRESSI (ciclo nuovo)
        self.ingressi: List[Any] = []
        self.sv = SR.Sorveglianza(scenario, strategia=lambda: self.s,
                                  attivita=lambda: self.attivita,
                                  ruolo=lambda o: ("ingresso" if any(o is x for x in self.ingressi)
                                                   else None))
        self.sv.guasto.quadro = SimpleNamespace(markets=SimpleNamespace(
            markets={MID: SimpleNamespace(blotter=self.blotter)}))
        self.slot = SimpleNamespace(status="FLATTENING", submins=[], entry=None,
                                    entry_back=None, entry_lay=None, close=None,
                                    next_entry=None, flatten_orders=[])
        self.s._slots[(MID, SEL)] = self.slot

    def colpo(self, abbinato: float = 0.29) -> Any:
        """Il gruppo d'ingresso: BACK abbinata ``abbinato`` @1,66, morta."""
        o = _ordine(self.s, "BACK", 1.66, 25.0, abbinato)
        self.blotter.append(o)
        g = {"chiave": (MID, SEL), "ordini": [o], "stato": "armato", "inizio_ms": T0}
        self.sv.guasto.gruppi[(MID, SEL)] = g
        return o

    def libri(self, n: int, t_ms: int = T0) -> None:
        for i in range(n):
            self.sv.al_book(MID, t_ms + i)

    def codici(self) -> List[str]:
        return [v[0] for v in self.sv.giro(T0 + 10_000)]

    def fine(self) -> List[str]:
        return [v[0] for v in self.sv.giro(T0 + 20_000, fine=True)]


def _r4(b: _Banco) -> None:
    """Il percorso del reperto R4: punta 1,00 @1,66 poi banca 1,28 @1,67."""
    b.blotter.append(_ordine(b.s, "BACK", 1.66, 1.0, 1.0, t_ms=T0 + 1))
    b.libri(1)
    b.attivita.append(("scavalco", {"selection_id": SEL, "side": "BACK", "price": 1.66,
                                    "size": 1.0}, T0 + 1))
    b.blotter.append(_ordine(b.s, "LAY", 1.67, 1.28, 1.28, t_ms=T0 + 2))
    b.libri(1)


def test_sv_percorso_r4_piatto_nessuna_violazione():
    b = _Banco()
    b.colpo()
    b.libri(2)
    assert b.sv.cicli and b.sv.cicli[0]["sotto_floor"]
    _r4(b)
    b.slot.status = "DONE"
    assert b.codici() == []
    c = b.sv.cicli[0]
    assert c["chiuso"] and len(c["scavalchi"]) == 1 and len(c["chiusure"]) == 1
    assert c["esito"]["differenza"] <= SR.TOLLERANZA_PIATTO
    assert {"SV1", "SV2", "SV3", "SV4"} <= set(b.sv.sollecitati)


def test_sv1_nessuno_scavalco_entro_n_book():
    b = _Banco()
    b.colpo()
    b.libri(SR.LIBRI_SCAVALCO + 2)
    assert "SV1" in b.codici()


def test_sv1_lo_stesso_book_riemesso_non_conta():
    """Reperto dello sviluppo (35797769, 16:51:58.628 -> 16:52:07.219): il motore
    riemette il book del mercato a ogni riga del raw con lo STESSO istante di
    pubblicazione mentre l'orologio del banco avanza coi book degli ALTRI mercati;
    il bot non ha visto niente di nuovo. Venti righe allo stesso istante del
    mercato sono UN book."""
    b = _Banco()
    b.colpo()
    for i in range(20):
        b.sv.al_book(MID, T0 + 500 + 400 * i, T0 + 500)
    assert "SV1" not in b.codici()
    assert b.sv.libri[MID] == 1


def test_sv1_scavalco_abbinato_e_nessuna_chiusura():
    b = _Banco()
    b.colpo()
    b.libri(1)
    b.blotter.append(_ordine(b.s, "BACK", 1.66, 1.0, 1.0, t_ms=T0 + 1))
    b.libri(1)
    # pausa del bot (1,5 s) passata, poi N+2 book senza chiusura
    b.libri(SR.LIBRI_SCAVALCO + 2, t_ms=T0 + 2_000)
    assert "SV1" in b.codici()


def test_ciclo_nuovo_dopo_il_residuo_non_e_uno_scavalco():
    """Reperto della falsificazione BF1 (35797769, sel 22): senza scavalco il bot
    dichiara il residuo e RIPARTE con un ingresso nuovo (LAY 25 @1,64). Quell'ingresso
    non e' uno scavalco (SV4 falso) e chiude il ciclo sorvegliato: SV2 lo giudica
    sugli ordini di PRIMA (0,29 aperti, nessuno scavalco: violazione)."""
    b = _Banco()
    b.colpo()
    b.libri(1)
    b.attivita.append(("residuo_ricordato", {"selection_id": SEL}, T0 + 5))
    nuovo = _ordine(b.s, "LAY", 1.64, 25.0, 0.0, vivo=True, t_ms=T0 + 10)
    b.ingressi.append(nuovo)
    b.blotter.append(nuovo)
    b.libri(1, t_ms=T0 + 10)
    codici = b.codici()
    c = b.sv.cicli[0]
    assert c["chiuso"] and c["taglio"] == T0 + 10 and c["scavalchi"] == []
    assert c["esito"]["differenza"] == pytest.approx(0.29 * 1.66, abs=0.01)
    assert "SV2" in codici and "SV4" not in codici


def test_rc2_gli_ordini_del_ciclo_dopo_non_sono_loop():
    b = _Banco(SR.SCENARIO_CODICI)
    o = _ordine(b.s, "BACK", 1.66, 1.0, 0.0, t_ms=T0 + 1)
    b.blotter.append(o)
    _rifiuto(b, "scavalco", "INVALID_BET_SIZE", o)
    b.codici()
    nuovo = _ordine(b.s, "LAY", 1.64, 25.0, 0.0, vivo=True, t_ms=T0 + 5)
    b.ingressi.append(nuovo)
    b.blotter.append(nuovo)
    b.libri(1, t_ms=T0 + 5)
    for i in range(SR.TETTO_ORDINI_DOPO_RIFIUTO + 1):
        b.blotter.append(_ordine(b.s, "BACK", 1.66, 1.0, 0.0, t_ms=T0 + 6 + i))
    assert "RC2" not in b.codici()


def test_sv2_ciclo_chiuso_non_piatto_e_violazione():
    b = _Banco()
    b.colpo()
    b.libri(1)
    b.slot.status = "DONE"                 # il bot lo dice chiuso con 0,29 aperti
    assert "SV2" in b.codici()


def test_sv2_resto_dichiarato_dopo_tre_scavalchi_non_e_violazione():
    b = _Banco()
    b.colpo()
    b.libri(1)
    for i in range(SR.SCAVALCHI_MAX):
        b.blotter.append(_ordine(b.s, "BACK", 1.66, 1.0, 0.0, t_ms=T0 + 1 + i))
        b.attivita.append(("scavalco", {"selection_id": SEL, "side": "BACK",
                                        "price": 1.66, "size": 1.0}, T0 + 1 + i))
        b.libri(1)
    b.attivita.append(("residuo_ricordato", {"selection_id": SEL}, T0 + 10))
    b.slot.status = "DONE"
    assert b.codici() == []
    assert b.sv.cicli[0]["esito"].get("dichiarato") is True


def test_sv2_resto_dichiarato_prima_del_massimo_resta_violazione():
    b = _Banco()
    b.colpo()
    b.libri(1)
    b.attivita.append(("residuo_ricordato", {"selection_id": SEL}, T0 + 10))
    b.slot.status = "DONE"
    assert "SV2" in b.codici()


def test_sv3_piu_di_tre_scavalchi_e_violazione():
    b = _Banco()
    b.colpo()
    b.libri(1)
    for i in range(SR.SCAVALCHI_MAX + 1):
        b.blotter.append(_ordine(b.s, "BACK", 1.66, 1.0, 0.0, t_ms=T0 + 1 + i))
        b.libri(1)
    assert "SV3" in b.codici()


def test_sv4_scavalco_senza_la_sua_attivita_e_violazione():
    b = _Banco()
    b.colpo()
    b.libri(1)
    b.blotter.append(_ordine(b.s, "BACK", 1.66, 1.0, 1.0, t_ms=T0 + 1))
    b.libri(1)
    b.attivita.append(("scavalco", {"selection_id": SEL, "side": "BACK", "price": 1.67,
                                    "size": 1.0}, T0 + 1))     # quota sbagliata
    codici: List[str] = []
    for _ in range(SR.GIRI_DI_TOLLERANZA + 1):
        codici += b.codici()
    assert "SV4" in codici


@pytest.mark.parametrize("payload,rosso", [
    ({"locked": -1.61, "residui_esclusi": -0.12}, False),
    ({"locked": -1.61}, True),                       # una cifra sola
    ({"locked": -1.20, "residui_esclusi": -0.50}, True),   # sotto il tetto 1,50
])
def test_sv5_loss_cap_due_cifre_e_solo_perdite_vere(payload, rosso):
    b = _Banco()
    b.attivita.append(("loss_cap", payload, T0))
    assert ("SV5" in b.codici()) is rosso
    assert b.sv.loss_cap_visti == 1


# ---------------------------------------------------------------- RC
def _rifiuto(b: _Banco, tipo: str, codice: str, ordine: Any) -> Dict[str, Any]:
    rec = {"tipo": tipo, "codice": codice, "operazione": "placeOrders", "ordine": ordine,
           "sostituito": None, "ms": T0 + 1, "chiave": (MID, SEL)}
    b.sv.rifiuti.fatti.append(rec)
    return rec


def test_rc3_rifiuto_scritto_col_codice():
    b = _Banco(SR.SCENARIO_CODICI)
    o = _ordine(b.s, "BACK", 1.66, 1.0, 0.0, t_ms=T0 + 1)
    b.blotter.append(o)
    _rifiuto(b, "scavalco", "INVALID_BET_SIZE", o)
    b.attivita.append(("rifiuto_taglia", {"msg": "Betfair ha rifiutato l'importo "
                                                 "(INVALID_BET_SIZE)"}, T0 + 2))
    assert "RC3" not in b.codici()


def test_rc3_rifiuto_mai_scritto_e_violazione():
    b = _Banco(SR.SCENARIO_CODICI)
    o = _ordine(b.s, "LAY", 1.02, 1.0, 0.0, t_ms=T0 + 1)
    b.blotter.append(o)
    _rifiuto(b, "parcheggio", "INVALID_PROFIT_RATIO", o)
    b.attivita.append(("submin_abort", {"note": "parcheggio non piu' vivo"}, T0 + 2))
    codici: List[str] = []
    for _ in range(SR.GIRI_DI_TOLLERANZA + 1):
        codici += b.codici()
    assert "RC3" in codici


def test_rc1_sequenza_che_aspetta_il_rifiutato_e_violazione():
    b = _Banco(SR.SCENARIO_CODICI)
    o = _ordine(b.s, "LAY", 1.02, 1.0, 0.0, t_ms=T0 + 1)
    b.blotter.append(o)
    _rifiuto(b, "parcheggio", "INVALID_PROFIT_RATIO", o)
    b.slot.submins.append({"order": o, "state": SimpleNamespace(
        step=SimpleNamespace(value="placed"))})
    codici: List[str] = []
    for _ in range(SR.GIRI_DI_TOLLERANZA + 1):
        codici += b.codici()
    assert "RC1" in codici


def test_rc2_loop_dopo_il_rifiuto():
    b = _Banco(SR.SCENARIO_CODICI)
    o = _ordine(b.s, "BACK", 1.66, 1.0, 0.0, t_ms=T0 + 1)
    b.blotter.append(o)
    _rifiuto(b, "scavalco", "INVALID_BET_SIZE", o)
    b.codici()
    for i in range(SR.TETTO_ORDINI_DOPO_RIFIUTO + 1):
        b.blotter.append(_ordine(b.s, "BACK", 1.66, 1.0, 0.0, t_ms=T0 + 5 + i))
    assert "RC2" in b.codici()


@pytest.mark.parametrize("dichiarato,rosso", [(True, False), (False, True)])
def test_rc4_ciclo_chiuso_non_piatto_dopo_il_rifiuto(dichiarato, rosso):
    b = _Banco(SR.SCENARIO_CODICI)
    entrata = _ordine(b.s, "BACK", 1.66, 25.0, 0.29, t_ms=T0)
    b.blotter.append(entrata)
    o = _ordine(b.s, "BACK", 1.66, 1.0, 0.0, t_ms=T0 + 1)
    b.blotter.append(o)
    b.slot.flatten_orders = [entrata, o]
    _rifiuto(b, "scavalco", "INVALID_BET_SIZE", o)
    b.codici()
    if dichiarato:
        b.attivita.append(("residuo_ricordato", {"selection_id": SEL}, T0 + 5))
    b.slot.status = "DONE"
    assert ("RC4" in b.codici()) is rosso


def test_fine_dice_non_esercitato_senza_colpi():
    b = _Banco(SR.SCENARIO_CODICI)
    b.fine()
    assert len(b.sv.non_esercitato) == 2
    assert "rifiuti del piano MAI eseguiti" in b.sv.non_esercitato[1]


# ===========================================================================
# 3. IL CONTRATTO col banco dello scalper e col bot
# ===========================================================================
def test_scenari_registrati_e_paper_in_prova():
    from Betfair.stream.backtest import applica_bot as AB
    from Betfair.stream.scalper.tools import replay_registrazioni as RR

    for sc in SR.SCENARI:
        assert sc in RR.SCENARI_DESCRITTI
        c = RR.control_della_ui("1", sc)
        assert c["dry_run"] is (sc in SR.SCENARI_PROVA)
        assert c["params"]["uscite_automatiche"] is True
        assert c["params"]["sniper_mode"] is False
        # gli stessi parametri di `base` (lo scenario cambia solo il guasto)
        assert c["params"] == RR.control_della_ui("1", "base")["params"]
        assert sc in AB.SCENARI_SCARTATI["scalper_calcio"]


def test_il_massimo_di_scavalchi_e_quello_del_bot():
    from Betfair.stream.scalper.scalper_bot import ScalperStrategy
    from Betfair.stream.scalper.sniper_bot import SniperStrategy

    assert ScalperStrategy._SCAVALCHI_MAX_PER_CICLO == SR.SCAVALCHI_MAX
    assert SniperStrategy._SCAVALCHI_MAX_PER_CICLO == SR.SCAVALCHI_MAX


def test_tetto_d_ingresso_sotto_il_floor_e_sopra_la_polvere():
    from Betfair.stream.trading.minimi_it import SUBMIN_IMPORTO_FINALE_MIN

    assert 0.05 <= SR.TETTO_INGRESSO < SUBMIN_IMPORTO_FINALE_MIN


def test_impronta_uguale_per_gli_stessi_ordini_e_diversa_per_un_importo():
    s = _Strategia()
    a = [_ordine(s, "BACK", 1.66, 1.0, 1.0), _ordine(s, "LAY", 1.67, 1.28, 1.28)]
    b = [_ordine(s, "LAY", 1.67, 1.28, 1.28), _ordine(s, "BACK", 1.66, 1.0, 1.0)]
    c = [_ordine(s, "BACK", 1.66, 1.0, 1.0), _ordine(s, "LAY", 1.67, 1.27, 1.27)]
    assert SR.impronta_ordini(a) == SR.impronta_ordini(b)
    assert SR.impronta_ordini(a)[0] != SR.impronta_ordini(c)[0]


# ===========================================================================
# 4. IL BOT (correzione dimostrata dal banco, RC3): il parcheggio rifiutato
#    da Betfair si scrive COL CODICE nella riga `submin_abort`
# ===========================================================================
def _parcheggio_morto(codice: Optional[str]) -> Any:
    """Un parcheggio BACK 1,00 @1000 mai nato (FAILURE) o annullato senza codice,
    con le chiavi dell'ordine flumine e della risposta di `placeOrders`."""
    from flumine.order.order import OrderStatus

    risposta = SimpleNamespace(status="FAILURE" if codice else "SUCCESS", error_code=codice)
    return SimpleNamespace(
        id="p1", market_id=MID, selection_id=SEL, side="BACK", bet_id=None,
        order_type=SimpleNamespace(price=1000.0, size=1.0, persistence_type="LAPSE"),
        size_matched=0.0, size_remaining=0.0, size_cancelled=0.0 if codice else 1.0,
        size_lapsed=0.0, average_price_matched=0.0, status=OrderStatus.EXECUTION_COMPLETE,
        responses=SimpleNamespace(place_response=risposta), trade=None)


@pytest.mark.parametrize("codice", ["INVALID_PROFIT_RATIO", None])
def test_scalper_scrive_il_codice_del_parcheggio_rifiutato(codice):
    from Betfair.stream.scalper.scalper_bot import ScalperStrategy, stato_parcheggio
    from Betfair.stream.trading.submin import SubminStep

    eventi: List[Tuple[str, Dict[str, Any]]] = []
    s = ScalperStrategy(market_filter={}, scalper_params={
        "dry_run": False, "stake": 25.0, "uscite_automatiche": True, "exact_exits": True},
        event_sink=lambda k, p: eventi.append((k, p)))
    slot = s._slot(MID, SEL)
    park = _parcheggio_morto(codice)
    stato = stato_parcheggio("BACK", 3.65, 0.97)
    stato.step = SubminStep.PLACED
    slot.submins.append({"state": stato, "ops": SimpleNamespace(last_order=park),
                         "order": park, "ref": "sc1", "market_id": MID})
    s._drive_submins(SimpleNamespace(market_id=MID), slot, T0)
    abort = [p for k, p in eventi if k == "submin_abort"]
    assert len(abort) == 1 and slot.submins == []
    if codice:
        assert "INVALID_PROFIT_RATIO" in abort[0]["note"] and abort[0]["codice"] == codice
    else:
        # senza rifiuto la riga e' quella di prima, identica
        assert abort[0] == {"note": "parcheggio non piu' vivo prima del rimpiazzo: "
                                    "sequenza chiusa, la chiusura si rifa'"}
