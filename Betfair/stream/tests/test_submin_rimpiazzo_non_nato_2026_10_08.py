"""Decisione D-2 dell'utente (08/10/2026, money-critical): il place-and-trim NON
dichiara completa una chiusura il cui rimpiazzo non e' nato.

Reperto (cantiere 9, D1; traccia `AUDIT_2026-10-08/cantiere_9/traccia_codici_sel58805.txt`
16:52:43-16:52:47): un `replaceOrders` RIFIUTATO da Betfair (parte place, es.
BET_TAKEN_OR_LAPSED) lascia il parcheggio annullato e NESSUN sostituto; flumine
LIVE (`execution/betfairexecution.py`, `execute_replace`, ramo FAILURE del place =
`pass  # todo`) non crea il sostituto e scarta il codice. `advance_submin` passava
REPRICED -> DONE senza guardare: il bot scriveva "submin completato".

Ora: REPRICED -> DONE solo se il sostituto e' nato; replace in volo -> attesa;
replace eseguito senza sostituto -> conferma al giro dopo, poi ABORTED con la riga
"rimpiazzo NON nato (replaceOrders rifiutato; codice non restituito)" e la chiusura
si rifa' (la rifanno i chiamanti, come per il parcheggio morto).

I finti sono gli OGGETTI VERI di flumine (`Trade`, `BetfairOrder`, `LimitOrder`,
client paper di `betfairlightweight`/flumine): stato e importi cambiano SOLO coi
metodi veri (`place`, `executable`, `replace`, `execution_complete`,
`Trade.create_order_replacement`, `SimulatedOrder.size_cancelled`), nello stesso
ordine del codice di flumine che si cita in ogni esito.
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import betfairlightweight
import pytest
from flumine import BaseStrategy, clients
from flumine.order.order import OrderStatus
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade

from Betfair.stream.trading import submin as SM
from Betfair.stream.trading.submin import SubminState, SubminStep, advance_submin

MID = "1.259819674"
SEL = 58805
PARK = 1000.0          # parcheggio BACK lontano (percorso B)
TARGET = 3.65          # quota del rimpiazzo (la chiusura vera)
RESTO = 0.97           # importo sotto minimo della chiusura (traccia del cloud)
T0 = 1_783_702_367_184  # epoch ms (16:52:47.184 del 10/07/2026, il replace della traccia)


# ---------------------------------------------------------------------------
# Oggetti VERI di flumine
# ---------------------------------------------------------------------------
def _client() -> Any:
    api = betfairlightweight.APIClient("u", "p", app_key="k")
    return clients.BetfairClient(api, paper_trade=True)


class Sequenza:
    """Parcheggio BACK 1,00 @1000 tagliato a 0,97 e mandato in replace a 3,65
    (stato REPRICED della macchina): poi uno degli esiti di flumine."""

    def __init__(self, side: str = "BACK", replace_chiesto: bool = True) -> None:
        self.client = _client()
        self.trade = Trade(MID, SEL, 0.0, BaseStrategy(market_filter={}))
        park_price = PARK if side == "BACK" else 1.01
        self.park = self.trade.create_order(
            side, LimitOrder(park_price, 1.00, persistence_type="LAPSE"))
        self.park.update_client(self.client)
        # gradino 1: placeOrders SUCCESS (Transaction.place_order -> place; esito -> bet_id, executable)
        self.park.place(None, None, False)
        self.park.bet_id = "100000000011"
        self.park.executable()
        # gradino 2: cancelOrders con sizeReduction 0,03 (SimulatedOrder.cancel)
        self.park.simulated.size_cancelled += 0.03
        assert self.park.size_remaining == pytest.approx(RESTO)
        # gradino 3: replaceOrders chiesto (BetfairOrder.replace -> REPLACING)
        if replace_chiesto:
            self.park.replace(TARGET)
            assert self.park.status == OrderStatus.REPLACING
        self.side = side
        self.sostituto: Optional[Any] = None

    def stato(self, **kw: Any) -> SubminState:
        return SubminState(step=SubminStep.REPRICED, bet_id=self.park.bet_id,
                           target_size=RESTO, target_price=TARGET, placed_size=1.00,
                           side=self.side.lower(), note="step3 replace -> %s" % TARGET,
                           trim_requested_ms=1, park_price=self.park.order_type.price,
                           serve_replace=True, **kw)

    # --- gli esiti del replace, come li lascia flumine ----------------------
    def _annullo_riuscito(self) -> None:
        # parte cancel del replace: SUCCESS -> order.execution_complete()
        self.park.simulated.size_cancelled += self.park.simulated.size_remaining
        self.park.execution_complete()

    def annullo_eseguito_sostituto_non_ancora(self) -> None:
        """Il thread di esecuzione e' fra `order.execution_complete()` e
        `trade.create_order_replacement(...)` (betfairexecution.py 178-194)."""
        self._annullo_riuscito()

    def sostituto_nasce(self) -> None:
        """Ramo SUCCESS del place (betfairexecution.py 192-209): sostituto nel
        Trade, nel blotter (`place`), `executable()`."""
        nuovo = self.trade.create_order_replacement(
            self.park, TARGET, RESTO, datetime.datetime.now(datetime.timezone.utc))
        nuovo.place(None, None, False)
        nuovo.bet_id = "100000000012"
        nuovo.executable()
        self.sostituto = nuovo

    def replace_riuscito(self) -> None:
        self._annullo_riuscito()
        self.sostituto_nasce()

    def rifiutato_live(self) -> None:
        """Ramo FAILURE del place in LIVE (betfairexecution.py 210-213, `pass  #
        todo`): parcheggio annullato e completo, nessun sostituto, codice perso."""
        self._annullo_riuscito()

    def rifiutato_simulazione(self) -> None:
        """Ramo FAILURE della simulazione di flumine (simulatedexecution.py
        136-159): sostituto creato nel Trade ma MAI piazzato (stato None), il
        parcheggio rimesso `executable()` a residuo zero."""
        self._annullo_riuscito()
        self.trade.create_order_replacement(
            self.park, TARGET, RESTO, datetime.datetime.now(datetime.timezone.utc))
        self.park.executable()

    def rimesso_eseguibile(self) -> None:
        """`BetfairExecution._execution_helper`: errore Betfair senza ritento ->
        `order_package.reset_orders()` -> `order.executable()`: il parcheggio
        resta VIVO a 1000 col suo residuo, nessun sostituto."""
        self.park.executable()

    def ultimo(self) -> Any:
        """Cio' che passano scalper, sniper, scalper tennis e uscite esatte."""
        return self.trade.orders[-1]


class OpsRegistra:
    """`SubminOps` di prova: registra le chiamate (le stesse firme del vero)."""

    def __init__(self, last_order: Any = None) -> None:
        self.calls: List[Tuple[str, Any, Any]] = []
        self.last_order = last_order
        self.max_stake = None

    def place(self, market: Any, *, side: str, price: float, size: float,
              customer_order_ref: str) -> Any:
        raise AssertionError("nessun place dopo il replace")

    def cancel(self, market: Any, order: Any, size_reduction: Optional[float]) -> None:
        self.calls.append(("cancel", order, size_reduction))

    def replace(self, market: Any, order: Any, new_price: float) -> None:
        raise AssertionError("nessun secondo replace")


def _passo(st: SubminState, order: Any, ops: OpsRegistra,
          now_ms: Optional[int] = None) -> SubminState:
    return advance_submin(SimpleNamespace(market_id=MID), st, order=order,
                          jurisdiction="it", customer_order_ref="sc1", ops=ops,
                          now_ms=now_ms)


OSSERVAZIONI = {
    "parcheggio (worker, motore)": lambda s: s.park,
    "ultimo del Trade (scalper, sniper, tennis)": lambda s: s.ultimo(),
}


# ===========================================================================
# (a) replace rifiutato: mai DONE, riga di abort, conferma al giro dopo
# ===========================================================================
@pytest.mark.parametrize("vista", list(OSSERVAZIONI))
@pytest.mark.parametrize("esito", ["rifiutato_live", "rifiutato_simulazione"])
def test_replace_rifiutato_non_va_a_done(esito: str, vista: str) -> None:
    s = Sequenza()
    getattr(s, esito)()
    ops = OpsRegistra()
    st = s.stato()
    st1 = _passo(st, OSSERVAZIONI[vista](s), ops)
    # primo giro: NON done, NON abort (si conferma al giro dopo)
    assert st1.step is SubminStep.REPRICED
    assert st1.giri_senza_sostituto == 1
    st2 = _passo(st1, OSSERVAZIONI[vista](s), ops)
    assert st2.step is SubminStep.ABORTED
    assert st2.note.startswith(SM.NOTA_RIMPIAZZO_NON_NATO)
    assert "rimpiazzo NON nato (replaceOrders rifiutato; codice non restituito)" in st2.note
    assert "la chiusura si rifa'" in st2.note
    assert ops.calls == []          # parcheggio a residuo zero: niente da ritirare
    # terminale: idempotente
    assert _passo(st2, OSSERVAZIONI[vista](s), ops) is st2


@pytest.mark.parametrize("vista", list(OSSERVAZIONI))
def test_replace_rimesso_eseguibile_ritira_il_parcheggio_vivo(vista: str) -> None:
    """Il replace non e' mai arrivato (reset di flumine): il parcheggio e' ancora
    a 1000 col suo residuo. La sequenza si chiude E il parcheggio si ritira: mai
    una gamba lasciata a mercato."""
    s = Sequenza()
    s.rimesso_eseguibile()
    ops = OpsRegistra()
    st = _passo(_passo(s.stato(), OSSERVAZIONI[vista](s), ops), OSSERVAZIONI[vista](s), ops)
    assert st.step is SubminStep.ABORTED
    assert st.note.startswith(SM.NOTA_RIMPIAZZO_NON_NATO)
    assert [(c[0], c[1] is s.park, c[2]) for c in ops.calls] == [("cancel", True, None)]


def test_replace_rifiutato_lay() -> None:
    s = Sequenza(side="LAY")
    s.rifiutato_live()
    ops = OpsRegistra()
    st = _passo(_passo(s.stato(), s.park, ops), s.park, ops)
    assert st.step is SubminStep.ABORTED and ops.calls == []


# ===========================================================================
# (b) replace riuscito: DONE come prima, stato identico a quello di prima
# ===========================================================================
@pytest.mark.parametrize("vista", list(OSSERVAZIONI))
def test_replace_riuscito_done_come_prima(vista: str) -> None:
    s = Sequenza()
    s.replace_riuscito()
    ops = OpsRegistra()
    st = s.stato()
    fatto = _passo(st, OSSERVAZIONI[vista](s), ops)
    assert fatto.step is SubminStep.DONE
    assert fatto.note == "submin completato: ordine sotto-minimo a riposo alla target_price"
    # tutti i campi identici a quelli che dava la versione di prima
    atteso = SubminState(**{**st.__dict__, "step": SubminStep.DONE,
                            "bet_id": OSSERVAZIONI[vista](s).bet_id or st.bet_id,
                            "note": fatto.note})
    assert fatto == atteso
    assert ops.calls == []


def test_sostituto_abbinato_e_completo_e_done() -> None:
    """Il sostituto abbinato per intero (EXECUTION_COMPLETE) e' nato: DONE."""
    s = Sequenza()
    s.replace_riuscito()
    s.sostituto.simulated.size_matched = RESTO
    s.sostituto.execution_complete()
    assert _passo(s.stato(), s.ultimo(), OpsRegistra()).step is SubminStep.DONE


# ===========================================================================
# (c) attese: replace in volo, poi sostituto assente per un giro, poi nato
# ===========================================================================
@pytest.mark.parametrize("vista", list(OSSERVAZIONI))
def test_in_volo_poi_assente_un_giro_poi_nato_nessun_abort(vista: str) -> None:
    s = Sequenza()
    ops = OpsRegistra()
    st = s.stato()
    # replace in volo (REPLACING): si aspetta (sotto il tetto D-2b), nessuna azione
    for i in range(5):
        st = _passo(st, OSSERVAZIONI[vista](s), ops, now_ms=T0 + 1000 * i)
        assert st.step is SubminStep.REPRICED and st.replace_in_volo_ms == T0
    assert ops.calls == []
    # il thread di esecuzione e' a meta': annullo fatto, sostituto non ancora
    s.annullo_eseguito_sostituto_non_ancora()
    st = _passo(st, OSSERVAZIONI[vista](s), ops)
    assert st.step is SubminStep.REPRICED and st.giri_senza_sostituto == 1
    # al giro dopo il sostituto c'e': DONE, nessun abort falso
    s.sostituto_nasce()
    st = _passo(st, OSSERVAZIONI[vista](s), ops)
    assert st.step is SubminStep.DONE
    assert ops.calls == []


def test_conteggio_azzerato_se_il_replace_torna_in_volo() -> None:
    """Un'osservazione senza sostituto seguita da un ordine di nuovo in volo:
    il conteggio riparte da zero (serve una conferma CONSECUTIVA)."""
    s = Sequenza()
    ops = OpsRegistra()
    st = s.stato(giri_senza_sostituto=1)
    st = _passo(st, s.park, ops)            # park REPLACING, prima osservazione
    assert st.step is SubminStep.REPRICED and st.giri_senza_sostituto == 0
    # attesa gia' iniziata (D-2b) e conteggio a 1: anche qui riparte da zero
    st = s.stato(giri_senza_sostituto=1, replace_in_volo_ms=T0)
    st = _passo(st, s.park, ops, now_ms=T0 + 1_000)
    assert st.step is SubminStep.REPRICED and st.giri_senza_sostituto == 0
    assert ops.calls == []


# ===========================================================================
# invarianti: percorso A e ordine non osservato come prima
# ===========================================================================
def test_percorso_a_nessun_replace_done_come_prima() -> None:
    s = Sequenza()
    st = s.stato()
    st.serve_replace = False
    s.rifiutato_live()       # anche con un ordine che non sta alla target
    assert _passo(st, s.park, OpsRegistra()).step is SubminStep.DONE


def test_ordine_non_osservato_come_prima() -> None:
    s = Sequenza()
    assert _passo(s.stato(), None, OpsRegistra()).step is SubminStep.DONE


# ===========================================================================
# (d) parita' per OGNI chiamante: stesso comportamento
# ===========================================================================
def _entry(s: Sequenza, st: SubminState, ops: OpsRegistra) -> Dict[str, Any]:
    return {"state": st, "ops": ops, "order": s.park, "ref": "sc1", "market_id": MID}


def _bot_scalper(eventi: list) -> Tuple[Any, Any, Any]:
    from Betfair.stream.scalper.scalper_bot import ScalperStrategy

    b = ScalperStrategy(market_filter={}, scalper_params={
        "dry_run": False, "stake": 25.0, "uscite_automatiche": True, "exact_exits": True},
        event_sink=lambda k, p: eventi.append((k, dict(p))))
    slot = b._slot(MID, SEL)
    return b, slot, (lambda m: b._drive_submins(m, slot, 0))


def _bot_sniper(eventi: list) -> Tuple[Any, Any, Any]:
    from Betfair.stream.scalper.sniper_bot import SniperStrategy, _Pos

    b = SniperStrategy(market_filter={}, sniper_params={"dry_run": False},
                       event_sink=lambda k, p: eventi.append((k, dict(p))))
    pos = _Pos()
    return b, pos, (lambda m: b._drive_submins(m, pos))


def _bot_tennis(eventi: list) -> Tuple[Any, Any, Any]:
    from Betfair.stream.tennis_scalper.tennis_scalper_bot import TennisScalperStrategy

    b = TennisScalperStrategy(market_filter={}, scalper_params={"dry_run": False},
                              event_sink=lambda k, p: eventi.append((k, dict(p))))
    slot = b._slot(MID, SEL)
    return b, slot, (lambda m: b._drive_submins(m, slot, 0))


BOT = {"scalper": _bot_scalper, "sniper": _bot_sniper, "tennis_scalper": _bot_tennis}


@pytest.mark.parametrize("bot", list(BOT))
def test_parita_bot_replace_rifiutato(bot: str) -> None:
    eventi: List[Tuple[str, Dict[str, Any]]] = []
    _b, contenitore, giro = BOT[bot](eventi)
    s = Sequenza()
    s.rifiutato_live()
    contenitore.submins.append(_entry(s, s.stato(), OpsRegistra(s.park)))
    market = SimpleNamespace(market_id=MID)
    giro(market)
    assert len(contenitore.submins) == 1          # in attesa della conferma
    assert [k for k, _p in eventi] == []
    giro(market)
    assert contenitore.submins == []
    passi = [p.get("step") for k, p in eventi if k == "submin_step"]
    abort = [p for k, p in eventi if k == "submin_abort"]
    assert passi == ["aborted"] and "done" not in passi
    assert len(abort) == 1 and abort[0]["note"].startswith(SM.NOTA_RIMPIAZZO_NON_NATO)
    # la posizione resta APERTA per il bot: il parcheggio annullato e' l'unico
    # ordine della sequenza e non ha abbinato niente (la chiusura si rifa')
    assert sum(float(o.size_matched) for o in s.trade.orders) == 0.0


@pytest.mark.parametrize("bot", list(BOT))
def test_parita_bot_replace_riuscito(bot: str) -> None:
    eventi: List[Tuple[str, Dict[str, Any]]] = []
    _b, contenitore, giro = BOT[bot](eventi)
    s = Sequenza()
    contenitore.submins.append(_entry(s, s.stato(), OpsRegistra(s.park)))
    market = SimpleNamespace(market_id=MID)
    giro(market)                                    # replace in volo: attesa
    assert len(contenitore.submins) == 1 and eventi == []
    s.replace_riuscito()
    giro(market)
    assert contenitore.submins == []
    assert eventi == [("submin_step", {
        "step": "done",
        "note": "submin completato: ordine sotto-minimo a riposo alla target_price"})]
    # il sostituto e' in contabilita' del bot
    seguiti = contenitore.flatten_orders
    assert any(o is s.sostituto for o in seguiti)


def _uscite_esatte(eventi: list) -> Tuple[Any, Any]:
    from Betfair.stream.tennis_scalper import condotta_ordini as CD

    ue = CD.UsciteEsatte(SimpleNamespace(), lambda k, **p: eventi.append((k, p)))
    comp = CD.OrdineComposto("BACK", TARGET, RESTO, SEL, MID)
    return ue, comp


def test_parita_uscite_esatte_tennis() -> None:
    from Betfair.stream.tennis_scalper import condotta_ordini as CD  # noqa: F401

    market = SimpleNamespace(market_id=MID)
    # rifiutato: ABORTED con la riga nuova (non piu' "replace rifiutato" dopo un DONE)
    eventi: list = []
    ue, comp = _uscite_esatte(eventi)
    s = Sequenza()
    s.rifiutato_live()
    comp.sequenza = _entry(s, s.stato(), OpsRegistra(s.park))
    ue.attive.append(comp)
    ue.avanza(market)
    assert comp.in_corso() and eventi == []
    ue.avanza(market)
    assert not comp.in_corso()
    assert comp.sequenza["state"].step is SubminStep.ABORTED
    assert comp.sequenza["state"].note.startswith(SM.NOTA_RIMPIAZZO_NON_NATO)
    assert [p["passo"] for k, p in eventi if k == "uscita_esatta_passo"] == ["aborted"]
    assert [k for k, _p in eventi].count("uscita_esatta_abort") == 1
    # riuscito: done
    eventi2: list = []
    ue2, comp2 = _uscite_esatte(eventi2)
    s2 = Sequenza()
    comp2.sequenza = _entry(s2, s2.stato(), OpsRegistra(s2.park))
    ue2.attive.append(comp2)
    ue2.avanza(market)
    assert comp2.in_corso()
    s2.replace_riuscito()
    ue2.avanza(market)
    assert comp2.sequenza["state"].step is SubminStep.DONE
    assert [p["passo"] for k, p in eventi2 if k == "uscita_esatta_passo"] == ["done"]


def test_parita_worker_coda_e_motore_persistenza_fra_i_giri() -> None:
    """Coda `place_submin` e motore ordini (`_advance_submin_row`): lo stato si
    rilegge dal dizionario persistito a OGNI giro. Il conteggio dei giri senza
    sostituto deve sopravvivere, altrimenti la sequenza aspetterebbe per sempre."""
    from Betfair.stream import live_order_worker as LOW

    s = Sequenza()
    s.rifiutato_live()
    ops = OpsRegistra()
    d = LOW._submin_state_to_dict(s.stato())
    for _ in range(2):
        st = _passo(LOW._submin_state_from_dict(d), s.park, ops)
        d = LOW._submin_state_to_dict(st)
    assert st.step is SubminStep.ABORTED
    assert st.note.startswith(SM.NOTA_RIMPIAZZO_NON_NATO)
    # stato scritto da una versione precedente (senza la chiave): default 0
    vecchio = {k: v for k, v in LOW._submin_state_to_dict(s.stato()).items()
               if k != "giri_senza_sostituto"}
    assert LOW._submin_state_from_dict(vecchio).giri_senza_sostituto == 0


def _sincrono(esito: Optional[str], timeout_sec: float = 60) -> Tuple[Any, Any]:
    """`live_order_worker._place_sub_minimum` (uscite sincrone del worker): la
    macchina vera dall'inizio, con `ops`/`find_order`/`sleep` iniettati.
    `find_order` ritrova il PARCHEGGIO (per bet_id, come `_find_submin_order`);
    il replace chiesto mette il parcheggio in REPLACING col metodo vero, e
    l'esito di flumine arriva al poll successivo."""
    from Betfair.stream import live_order_worker as LOW

    s = Sequenza(replace_chiesto=False)   # parcheggio vivo, gia' tagliato a 0,97

    class Ops(OpsRegistra):
        def place(self, market: Any, *, side: str, price: float, size: float,
                  customer_order_ref: str) -> Any:
            self.last_order = s.park
            return s.park

        def replace(self, market: Any, order: Any, new_price: float) -> None:
            self.calls.append(("replace", order, new_price))
            order.replace(new_price)

    ops = Ops()

    def find_order(order_id: Any, bet_id: Any) -> Any:
        if s.park.status == OrderStatus.REPLACING and esito is not None:
            getattr(s, esito)()
        return s.park

    stato_ord = LOW._place_sub_minimum(
        None, SimpleNamespace(market_id=MID, cancel_order=lambda o: None),
        market_id=MID, strategy=None, selection_id=SEL, handicap=0.0, side="BACK",
        price=TARGET, size=RESTO, cust_ref="awlq1", what="uscita", ops=ops,
        find_order=find_order, sleep=lambda _s: None, timeout_sec=timeout_sec)
    return stato_ord, ops


def test_parita_worker_sincrono_riuscito() -> None:
    (stato, _ordine), ops = _sincrono("replace_riuscito")
    assert stato.step is SubminStep.DONE
    assert [c[0] for c in ops.calls] == ["replace"]


def test_parita_worker_sincrono_rifiutato() -> None:
    with pytest.raises(ValueError) as e:
        _sincrono("rifiutato_live")
    assert SM.NOTA_RIMPIAZZO_NON_NATO in str(e.value)


# ===========================================================================
# D-2b: tetto dell'attesa col replace IN VOLO (_REPLACE_IN_VOLO_TIMEOUT_MS)
# ===========================================================================
class OpsCancelRifiutato(OpsRegistra):
    """Come flumine: il cancel di un ordine REPLACING solleva (OrderUpdateError)."""

    def cancel(self, market: Any, order: Any, size_reduction: Optional[float]) -> None:
        self.calls.append(("cancel", order, size_reduction))
        if order.status == OrderStatus.REPLACING:
            order.cancel(size_reduction)          # metodo vero: solleva


def test_tetto_in_volo_vale_quanto_il_tetto_del_trim() -> None:
    assert SM._REPLACE_IN_VOLO_TIMEOUT_MS == 15_000 == SM._TRIM_TIMEOUT_MS


@pytest.mark.parametrize("vista", list(OSSERVAZIONI))
def test_in_volo_sotto_il_tetto_attesa(vista: str) -> None:
    s = Sequenza()
    ops = OpsRegistra()
    st = _passo(s.stato(), OSSERVAZIONI[vista](s), ops, now_ms=T0)
    st = _passo(st, OSSERVAZIONI[vista](s), ops, now_ms=T0 + 14_999)
    assert st.step is SubminStep.REPRICED and ops.calls == []


@pytest.mark.parametrize("vista", list(OSSERVAZIONI))
def test_in_volo_oltre_il_tetto_abort_e_ritiro(vista: str) -> None:
    s = Sequenza()
    ops = OpsRegistra()
    st = _passo(s.stato(), OSSERVAZIONI[vista](s), ops, now_ms=T0)
    st = _passo(st, OSSERVAZIONI[vista](s), ops, now_ms=T0 + 15_000)
    assert st.step is SubminStep.ABORTED
    assert st.note == ("rimpiazzo in volo da 15000 ms senza esito; sequenza chiusa, "
                       "la chiusura si rifa'")
    assert [(c[0], c[1] is s.park, c[2]) for c in ops.calls] == [("cancel", True, None)]


def test_in_volo_oltre_il_tetto_cancel_rifiutato_da_flumine_abort_comunque() -> None:
    s = Sequenza()
    ops = OpsCancelRifiutato()
    st = _passo(s.stato(), s.park, ops, now_ms=T0)
    st = _passo(st, s.park, ops, now_ms=T0 + 20_000)
    assert st.step is SubminStep.ABORTED and len(ops.calls) == 1
    assert s.park.status == OrderStatus.REPLACING     # flumine non l'ha toccato


@pytest.mark.parametrize("vista", list(OSSERVAZIONI))
def test_sostituto_nato_prima_del_tetto_done(vista: str) -> None:
    s = Sequenza()
    ops = OpsRegistra()
    st = _passo(s.stato(), OSSERVAZIONI[vista](s), ops, now_ms=T0)
    s.replace_riuscito()
    st = _passo(st, OSSERVAZIONI[vista](s), ops, now_ms=T0 + 14_000)
    assert st.step is SubminStep.DONE and ops.calls == []


def test_tetto_in_volo_persistito_fra_i_giri_coda_e_motore() -> None:
    from Betfair.stream import live_order_worker as LOW

    s = Sequenza()
    ops = OpsRegistra()
    d = LOW._submin_state_to_dict(s.stato())
    for t in (T0, T0 + 5_000, T0 + 15_000):
        st = _passo(LOW._submin_state_from_dict(d), s.park, ops, now_ms=t)
        d = LOW._submin_state_to_dict(st)
    assert st.step is SubminStep.ABORTED and st.note.startswith("rimpiazzo in volo da 15000 ms")


@pytest.mark.parametrize("bot", list(BOT))
def test_parita_bot_tetto_in_volo(bot: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """I bot non passano `now_ms`: vale `time.time` (nel replay = orologio di mercato)."""
    orologio = {"s": T0 / 1000.0}
    monkeypatch.setattr(SM.time, "time", lambda: orologio["s"])
    eventi: List[Tuple[str, Dict[str, Any]]] = []
    _b, contenitore, giro = BOT[bot](eventi)
    s = Sequenza()
    contenitore.submins.append(_entry(s, s.stato(), OpsRegistra(s.park)))
    market = SimpleNamespace(market_id=MID)
    giro(market)
    orologio["s"] += 14.0
    giro(market)
    assert len(contenitore.submins) == 1 and eventi == []
    orologio["s"] += 1.0
    giro(market)
    assert contenitore.submins == []
    abort = [p for k, p in eventi if k == "submin_abort"]
    assert len(abort) == 1 and abort[0]["note"].startswith("rimpiazzo in volo da 15000 ms")


def test_worker_sincrono_timeout_piu_stretto_esito_di_prima() -> None:
    """Il worker sincrono ha il SUO tetto (`timeout_sec`, default 20 s dall'inizio
    della sequenza): con un tetto piu' stretto del nostro l'esito e' quello di
    sempre (ritiro + errore "timeout della sequenza place-and-trim")."""
    with pytest.raises(ValueError) as e:
        _sincrono(None, timeout_sec=0.3)
    assert "timeout della sequenza place-and-trim" in str(e.value)
    assert "rimpiazzo in volo" not in str(e.value)


# ===========================================================================
# D-2a: controllo RC3 del banco (`backtest/scavalco_rifiuti.py`), solo banco
# ===========================================================================
def _rc3(operazione: str, tipo: str, codice: str, riga: Optional[Dict[str, Any]]) -> bool:
    """True se RC3 scatta. Il minimo banco dei test del cantiere 9 (`_Banco`)."""
    from Betfair.stream.backtest import scavalco_rifiuti as SR
    from Betfair.stream.tests import test_banco_scavalco_rifiuti_2026_10_08 as TB

    b = TB._Banco(SR.SCENARIO_CODICI)
    o = TB._ordine(b.s, "BACK", 1000.0, 1.0, 0.0, t_ms=TB.T0 + 1)
    b.blotter.append(o)
    b.sv.rifiuti.fatti.append({"tipo": tipo, "codice": codice, "operazione": operazione,
                               "ordine": o, "sostituito": None, "ms": TB.T0 + 1,
                               "chiave": (TB.MID, TB.SEL)})
    if riga is not None:
        b.attivita.append(("submin_abort", riga, TB.T0 + 2))
    codici: List[str] = []
    for _ in range(SR.GIRI_DI_TOLLERANZA + 1):
        codici += b.codici()
    return "RC3" in codici


NOTA_BOT = {"note": SM.NOTA_RIMPIAZZO_NON_NATO + ": nessun ordine alla quota 3.65, "
                    "parcheggio annullato; sequenza chiusa, la chiusura si rifa'",
            "matched": 0.0}


def test_rc3_replace_con_la_riga_rimpiazzo_non_nato_ok() -> None:
    assert _rc3("replaceOrders", "rimpiazzo", "BET_TAKEN_OR_LAPSED", NOTA_BOT) is False


@pytest.mark.parametrize("riga", [None, {"note": "submin completato: ordine sotto-minimo "
                                                   "a riposo alla target_price"}])
def test_rc3_replace_senza_la_riga_resta_ko(riga: Optional[Dict[str, Any]]) -> None:
    assert _rc3("replaceOrders", "rimpiazzo", "BET_TAKEN_OR_LAPSED", riga) is True


def test_rc3_place_la_riga_del_replace_non_basta() -> None:
    """Per placeOrders il codice arriva al bot: RC3 lo pretende come prima."""
    assert _rc3("placeOrders", "parcheggio", "INVALID_PROFIT_RATIO", NOTA_BOT) is True
    assert _rc3("placeOrders", "parcheggio", "INVALID_PROFIT_RATIO",
                {"note": "parcheggio rifiutato da Betfair: INVALID_PROFIT_RATIO"}) is False
