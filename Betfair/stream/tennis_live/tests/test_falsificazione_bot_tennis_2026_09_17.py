# -*- coding: utf-8 -*-
"""LA FALSIFICAZIONE dei difetti corretti il 17/09 sui quattro bot tennis.

Un test che non sa diventare ROSSO non certifica niente (CLAUDE.md). Qui ogni
difetto corretto viene REINTRODOTTO e il controllo che lo difende deve
accorgersene. Se un giorno qualcuno rimette il difetto e questi test restano
verdi, il difetto e' tornato invisibile — ed e' esattamente il punto 35 del
catalogo (`PROCESSO_STANDARD_BOT.md` §7).

I difetti falsificati, uno per uno:

  1. `res.ok` mai letto (catalogo §7 difetto 2) sui quattro bot: un piazzamento
     RIFIUTATO da un trading control di flumine (`place_order` -> False) non
     deve lasciare il bot con una posizione creduta viva -> controllo K2.
  2. Il P&L di settlement contato DUE volte nel FLB (nessun dedup per ordine):
     `process_closed_market` puo' essere richiamato sullo stesso mercato.
  3. Il GREEN contato senza che nessun ordine di copertura sia partito (FLB).
  4. Il tetto transazioni dello scalper con l'orologio del MURO invece di quello
     del mercato: rompe la parita' replay/paper/live.
  5. La gamba ORFANA dello scalper: se una sola delle due gambe parte, l'altra
     non deve sparire da ogni contabilita'.
  6. I finti che non parlano come il vero (catalogo §7 difetto 27):
     `Market.place_order` ritorna un BOOL.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import types

import pytest

from Betfair.stream.tennis_live import certificazione_bot as CERT
from Betfair.stream.tennis_scalper.tennis_flb_bot import TennisFLBStrategy
from Betfair.stream.tennis_scalper.tennis_pro_bot import TennisProStrategy
from Betfair.stream.tennis_scalper.tennis_scalper_bot import TennisScalperStrategy
from Betfair.stream.tennis_scalper.tennis_swing_bot import TennisSwingStrategy
from flumine.order.order import OrderStatus


# ---------------------------------------------------------------------------
# i finti: parlano come il vero (chiavi, tipi, valori di ritorno)
# ---------------------------------------------------------------------------
class _Blotter:
    def __init__(self, ordini=None):
        self._ordini = list(ordini or [])

    def strategy_orders(self, _s):
        return list(self._ordini)


class _MercatoCheAccetta:
    """`Market.place_order` ritorna True quando l'ordine e' piazzato
    (`flumine/markets/market.py:84-98`)."""

    market_id = "1.1"

    def __init__(self, blotter=None):
        self.blotter = blotter or _Blotter()
        self.piazzati = []
        self.annullati = []

    def place_order(self, o):
        self.piazzati.append(o)
        return True

    def cancel_order(self, o):
        self.annullati.append(o)
        return True


class _MercatoCheRifiuta(_MercatoCheAccetta):
    """Betfair RIFIUTA: `place_order` torna False e l'ordine resta in VIOLATION,
    esattamente come fa `Transaction._validate_controls`
    (`flumine/execution/transaction.py:67-75, 230-242`)."""

    def place_order(self, o):
        try:
            o.violation("rifiuto del test")
        except Exception:  # noqa: BLE001 - firma diversa in versioni vecchie
            pass
        return False


def _strategia(cls, **params):
    chiave = {
        TennisScalperStrategy: "scalper_params",
        TennisProStrategy: "pro_params",
        TennisFLBStrategy: "flb_params",
        TennisSwingStrategy: "swing_params",
    }[cls]
    kw = {chiave: dict(params, dry_run=False),
          "market_filter": {"markets": ["x"]},
          "max_order_exposure": None, "max_selection_exposure": None,
          "max_trade_count": int(1e9), "max_live_trade_count": int(1e9)}
    if cls is TennisProStrategy:
        kw["name_to_sel"] = {}
    return cls(**kw)


# ===========================================================================
# 1. `res.ok` mai letto — il piazzamento rifiutato non e' un piazzamento
# ===========================================================================
@pytest.mark.parametrize("cls", [TennisScalperStrategy, TennisProStrategy,
                                 TennisFLBStrategy, TennisSwingStrategy])
def test_place_rifiutato_non_torna_un_ordine(cls):
    """IL COMPORTAMENTO CORRETTO: `_place` deve tornare None quando
    `market.place_order` risponde False. Prima tornava l'oggetto e il bot lo
    trattava come vivo."""
    s = _strategia(cls)
    m = _MercatoCheRifiuta()
    o = s._place(m, 111, "BACK", 3.0, 2.0)
    assert o is None, (
        "il bot ha creduto piazzato un ordine che `place_order` ha RIFIUTATO: "
        "e' il difetto 2 del catalogo (`res.ok` mai letto)")


@pytest.mark.parametrize("cls", [TennisScalperStrategy, TennisProStrategy,
                                 TennisFLBStrategy, TennisSwingStrategy])
def test_place_accettato_torna_l_ordine(cls):
    """LA FALSIFICAZIONE DELLA FALSIFICAZIONE: il controllo sopra non deve
    rifiutare anche gli ordini BUONI, altrimenti sarebbe verde per il motivo
    sbagliato."""
    s = _strategia(cls)
    m = _MercatoCheAccetta()
    o = s._place(m, 111, "BACK", 3.0, 2.0)
    assert o is not None and m.piazzati, (
        "un piazzamento ACCETTATO deve tornare l'ordine: il controllo sarebbe "
        "verde per il motivo sbagliato")


def test_k2_diventa_rosso_se_il_bot_crede_a_un_ordine_rifiutato():
    """Il controllo K2 del banco deve ACCORGERSENE. Qui si simula il difetto
    REINTRODOTTO: la credenza resta viva e l'ordine e' in VIOLATION."""
    ordine = {"order_id": "o1", "status": OrderStatus.VIOLATION.value,
              "side": "LAY", "selection_id": 7, "market_id": "1.1",
              "size": 2.0, "price": 1.08, "size_matched": 0.0,
              "size_remaining": 0.0, "average_price_matched": 0.0}
    oss = CERT.Osservazione(
        bot="tennis_flb", market_id="1.1", ordini=[ordine],
        credenze=[{"chiave": ("1.1", 7), "stato": "OPEN",
                   "ingressi": [types.SimpleNamespace(id="o1")], "uscite": []}],
    )
    esiti = CERT.verifica(oss)
    assert any(v.codice == "K2" for v in esiti), (
        "K2 non ha visto una posizione viva su un ordine RIFIUTATO: il "
        "controllo non sa diventare rosso e percio' non certifica")


def test_k2_resta_verde_quando_il_bot_lascia_andare_l_ordine_rifiutato():
    """La stessa scena col COMPORTAMENTO CORRETTO: nessuna credenza viva."""
    ordine = {"order_id": "o1", "status": OrderStatus.VIOLATION.value,
              "side": "LAY", "selection_id": 7, "market_id": "1.1",
              "size": 2.0, "price": 1.08, "size_matched": 0.0,
              "size_remaining": 0.0, "average_price_matched": 0.0}
    oss = CERT.Osservazione(bot="tennis_flb", market_id="1.1", ordini=[ordine],
                            credenze=[])
    esiti = CERT.verifica(oss)
    assert not [v for v in esiti if v.codice == "K2"]


# ===========================================================================
# 2. il P&L di settlement contato due volte (FLB)
# ===========================================================================
def _ordine_regolato(oid="o1", profit=1.5):
    return types.SimpleNamespace(
        id=oid, simulated=types.SimpleNamespace(profit=profit),
        selection_id=7, side="LAY", size_matched=2.0,
        average_price_matched=1.08, status=OrderStatus.EXECUTION_COMPLETE,
        size_remaining=0.0)


def test_flb_pnl_non_raddoppia_se_il_mercato_chiude_due_volte():
    s = _strategia(TennisFLBStrategy)
    m = _MercatoCheAccetta(_Blotter([_ordine_regolato(profit=1.5)]))
    s.process_closed_market(m, None)
    primo = s.stats["pnl"]
    s.process_closed_market(m, None)   # flumine puo' richiamarlo
    assert s.stats["pnl"] == primo == 1.5, (
        "il P&L di settlement e' stato contato due volte: e' il numero che "
        "finisce nel pannello e nello storico")


# ===========================================================================
# 3. il GREEN contato senza che nessuna copertura sia partita (FLB)
# ===========================================================================
def test_flb_non_conta_un_green_se_l_hedge_non_e_partito():
    """Posizione SBILANCIATA e nessun ordine di copertura: `stats['greens']`
    non deve crescere e la posizione non deve risultare chiusa."""
    s = _strategia(TennisFLBStrategy, exit_mode="green")
    # un lay abbinato da 2 EUR a 1,08: la posizione NON e' pari
    lay = types.SimpleNamespace(id="e1", selection_id=7, side="LAY",
                                size_matched=2.0, average_price_matched=1.08,
                                status=OrderStatus.EXECUTION_COMPLETE,
                                size_remaining=0.0)
    m = _MercatoCheAccetta(_Blotter([lay]))
    key = ("1.1", 7)
    st = {"state": "OPEN", "entry": 1.08, "order": None, "wait": 0,
          "greened": True, "green_order": None, "green_locked": False,
          "t0": 0}
    s._pos_state[key] = st
    s._manage(m, 7, key, st, bb=1.20, bl=1.22, pt=1000)
    assert s.stats["greens"] == 0, (
        "il bot ha contato un GREEN senza che nessun ordine di copertura fosse "
        "partito: e' una cifra inventata nel pannello")
    assert st.get("greened") is False, (
        "dopo un hedge non partito il bot deve poter riprovare, non "
        "considerarsi coperto")


def test_flb_conta_il_green_quando_la_posizione_e_gia_pari():
    """La falsificazione opposta: se non c'era niente da coprire, il green e'
    davvero concluso e il controllo non deve impedirlo."""
    s = _strategia(TennisFLBStrategy, exit_mode="green")
    lay = types.SimpleNamespace(id="e1", selection_id=7, side="LAY",
                                size_matched=2.0, average_price_matched=1.10,
                                status=OrderStatus.EXECUTION_COMPLETE,
                                size_remaining=0.0)
    back = types.SimpleNamespace(id="g1", selection_id=7, side="BACK",
                                 size_matched=2.0, average_price_matched=1.10,
                                 status=OrderStatus.EXECUTION_COMPLETE,
                                 size_remaining=0.0)
    m = _MercatoCheAccetta(_Blotter([lay, back]))
    key = ("1.1", 7)
    st = {"state": "OPEN", "entry": 1.10, "order": None, "wait": 0,
          "greened": True, "green_order": None, "green_locked": False,
          "t0": 0}
    s._pos_state[key] = st
    s._manage(m, 7, key, st, bb=1.20, bl=1.22, pt=1000)
    assert s.stats["greens"] == 1


# ===========================================================================
# 4. il tetto transazioni con l'orologio del MURO (scalper)
# ===========================================================================
def test_scalper_il_tetto_transazioni_usa_l_orologio_del_mercato():
    """La finestra da un'ora si deve svuotare col TEMPO DI MERCATO: e' cosi' che
    replay, paper e live si comportano allo stesso modo."""
    s = _strategia(TennisScalperStrategy, max_txn_hour=2, stake=2.0)
    m = _MercatoCheAccetta()
    s._now_ms = 1_000_000_000_000                      # t0
    assert s._place(m, 7, "BACK", 3.0, 2.0, floor_min=True) is not None
    assert s._place(m, 7, "BACK", 3.0, 2.0, floor_min=True) is not None
    # il terzo entro l'ora e' tagliato dal tetto
    assert s._place(m, 7, "BACK", 3.0, 2.0, floor_min=True) is None
    # due ore DI MERCATO dopo, la finestra si e' svuotata
    s._now_ms += 2 * 3600 * 1000
    assert s._place(m, 7, "BACK", 3.0, 2.0, floor_min=True) is not None, (
        "la finestra del tetto transazioni non si svuota col tempo di mercato: "
        "in replay e in backtest il tetto scatterebbe e non si riaprirebbe mai")


def test_scalper_orologio_e_quello_del_publish_time():
    s = _strategia(TennisScalperStrategy)
    s._now_ms = 1_700_000_000_000
    assert s._orologio_s() == pytest.approx(1_700_000_000.0)


# ===========================================================================
# 5. la gamba ORFANA dello scalper
# ===========================================================================
def test_scalper_la_gamba_superstite_resta_nella_contabilita():
    """Se una sola delle due gambe parte, l'altra deve restare nello slot e lo
    slot deve andare in DONE, dove la sorveglianza post-DONE la ritenta."""
    from Betfair.stream.tennis_scalper.tennis_scalper_bot import DONE

    s = _strategia(TennisScalperStrategy)
    m = _MercatoCheAccetta()
    slot = s._slot("1.1", 7)
    superstite = types.SimpleNamespace(
        id="b1", selection_id=7, side="BACK", size_matched=0.0,
        size_remaining=2.0, status=OrderStatus.PENDING,
        average_price_matched=0.0)
    s._gamba_orfana(m, slot, superstite, None, "join")
    assert slot.entry_back is superstite, (
        "la gamba superstite e' sparita dalla contabilita' dello slot: nessuno "
        "la vede piu' e nessuno la cancella (posizione NUDA)")
    assert slot.status == DONE, (
        "lo slot deve andare in DONE, dove la sorveglianza post-DONE ritenta il "
        "cancel e riapre il flatten")


# ===========================================================================
# 6. i finti parlano come il vero
# ===========================================================================
def test_il_finto_place_order_ritorna_un_bool_come_il_vero():
    """Il contratto di flumine: `Market.place_order -> bool`. Un finto che
    ritorna None certifica il difetto 2 del catalogo."""
    import inspect

    from flumine.markets.market import Market

    firma = inspect.signature(Market.place_order)
    assert firma.return_annotation is bool, (
        "flumine ha cambiato il contratto di `place_order`: i controlli e i "
        "finti vanno riallineati")
    assert _MercatoCheAccetta().place_order(object()) is True


# ===========================================================================
# 7. K6 e `Cancelling`: l'esenzione non deve diventare una scappatoia
# ===========================================================================
def _oss_con_ordine_vivo(stato):
    """Una posizione DICHIARATA CHIUSA con un ordine ancora vivo sul book."""
    ordine = {"order_id": "o1", "status": stato, "side": "LAY",
              "selection_id": 7, "market_id": "1.1", "size": 2.0,
              "price": 1.08, "size_matched": 0.0, "size_remaining": 2.0,
              "average_price_matched": 0.0}
    return CERT.Osservazione(
        bot="tennis_scalper", market_id="1.1", ordini=[ordine],
        credenze=[{"chiave": ("1.1", 7), "stato": "DONE",
                   "ingressi": [], "uscite": []}])


def test_k6_non_accusa_un_cancel_IN_VOLO():
    """`Cancelling` e' il cancel che il bot HA CHIESTO e che sta viaggiando
    verso Betfair: accusarlo vuol dire accusare il bot di fare la cosa giusta.
    MISURATO sul replay massivo del 17/09: 19 violazioni su 12 partite, TUTTE
    con stato `Cancelling` e tutte transitorie (1-3 giri), con la sorveglianza
    post-DONE dello scalper che ritentava il cancel a ogni book."""
    esiti = CERT.verifica(_oss_con_ordine_vivo("Cancelling"))
    assert not [v for v in esiti if v.codice == "K6"]


@pytest.mark.parametrize("stato", ["Executable", "Pending", "Updating", "Replacing"])
def test_k6_accusa_ancora_un_ordine_che_nessuno_sta_togliendo(stato):
    """LA FALSIFICAZIONE DELL'ESENZIONE: fuori da `Cancelling` un ordine vivo
    sotto una posizione «chiusa» resta una violazione piena. Se questo test
    diventasse verde, l'esenzione si sarebbe mangiata il controllo."""
    esiti = CERT.verifica(_oss_con_ordine_vivo(stato))
    assert [v for v in esiti if v.codice == "K6"], (
        "K6 non vede piu' un residuo NON governato: l'esenzione per "
        "`Cancelling` ha spento il controllo")
