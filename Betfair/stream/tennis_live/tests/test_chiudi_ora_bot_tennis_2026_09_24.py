# -*- coding: utf-8 -*-
"""D3 (24/09/2026) - il "CHIUDI ORA" dei QUATTRO bot tennis.

Il percorso sotto prova e' quello di produzione, pezzo per pezzo:
  riga `chiudi_bot` su `tennis_live_order_queue` -> `tennis_live_order_worker`
  (VERO) -> `chiusura_manuale.gestisci_riga` -> il bot (classe VERA, istanziata
  da `tennis_runner._instantiate_bot`) esce con la SUA macchina d'uscita ->
  `tennis_runner.bot_control_worker` (VERO) -> `chiusura_manuale.avanza` ->
  bot disabilitato, riga `stopped` col marcatore, esito sulla coda.

I finti parlano come il vero:
  * `_Mercato.place_order(order, market_version=None, execute=True, force=False,
    client=None) -> bool` e `cancel_order(order, size_reduction=None,
    force=False)` hanno la firma di `flumine.markets.market.Market`; gli ordini
    che il bot piazza sono `BetfairOrder` VERI (Trade.create_order), portati a
    `Executable` con `placing()/executable()` e riempiti come li riempie lo
    stream ordini di Betfair (`responses.current_order` con `size_matched`,
    `size_remaining`, `average_price_matched`, poi `execution_complete()`);
  * l'ordine d'ingresso gia' a mercato ha gli attributi dell'Order flumine
    (`selection_id`, `side`, `size_matched`, `average_price_matched`,
    `size_remaining`, `status` = `OrderStatus` Enum, `order_type.price/size`);
  * `_Blotter.get_exposures(strategy, lookup)` torna le chiavi di
    `flumine.markets.blotter.Blotter.get_exposures`
    (`matched_profit_if_win`, `matched_profit_if_lose`);
  * il DB ha le firme di `tennis_db`.

I quattro test parametrici (x4 bot):
  1. richiesta -> uscita manuale -> UNA chiusura sull'ABBINATO (mai il chiesto)
     -> bot fermo, riga `stopped` col marcatore, esito "eseguita", nessun
     rientro;
  2. richiesta ambigua (modalita', mercato, bot) -> rifiutata, bot intatto;
  3. bot GIA' in uscita -> nessun secondo ordine, e una richiesta doppia non
     produce un secondo comando;
  4. paper/live della riga rispettato (bot live: si chiude solo in live; bot
     paper in runner LIVE: si chiude in paper, sul client simulato).

FALSIFICAZIONE (24/09, patch salvata, `git checkout -- file` + `git apply
--include=file`): vedi il referto del delegato.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import datetime as _dt
import types
from typing import Any, Dict, List, Optional

import betfairlightweight
import pytest
from betfairlightweight.filters import streaming_market_data_filter
from flumine.order.order import OrderStatus

from Betfair.stream import live_order_worker as LOW
from Betfair.stream import local_channel as LC
from Betfair.stream.tennis_live import chiusura_manuale as CM
from Betfair.stream.tennis_live import guardie_tennis as GT
from Betfair.stream.tennis_live import tennis_bot_service as S
from Betfair.stream.tennis_live import tennis_live_order_worker as W
from Betfair.stream.tennis_live import tennis_runner as TR
from Betfair.stream.tennis_scalper import condotta_ordini as CD
from Betfair.stream.tennis_scalper import tennis_pro_bot as PRO
from Betfair.stream.tennis_scalper import tennis_scalper_bot as SC
from Betfair.stream.tennis_scalper.tennis_score import TennisScore

MID = "1.200"
EV = "35800001"
SEL = 101
SEL2 = 202
BOTS = ["tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing"]
T0 = 1_760_000_000_000     # ms, orologio del mercato

# prezzi del book: SEL si chiude a 1.98 (back) / 2.02 (lay)
BB, BL = 1.98, 2.02


# ===========================================================================
# i finti
# ===========================================================================
_VIVI = (OrderStatus.PENDING, OrderStatus.EXECUTABLE, OrderStatus.CANCELLING,
         OrderStatus.UPDATING, OrderStatus.REPLACING)


class _Blotter:
    def __init__(self) -> None:
        self.ordini: List[Any] = []

    def strategy_orders(self, strategy: Any) -> List[Any]:
        return list(self.ordini)

    def get_exposures(self, strategy: Any, lookup: Any) -> Dict[str, float]:
        _mid, sel, _h = lookup
        vince = perde = 0.0
        for o in self.ordini:
            if int(getattr(o, "selection_id", 0) or 0) != int(sel):
                continue
            s = float(o.size_matched or 0.0)
            p = float(o.average_price_matched or 0.0)
            if s <= 0 or p <= 0:
                continue
            if str(o.side).upper() == "BACK":
                vince += s * (p - 1.0)
                perde -= s
            else:
                vince -= s * (p - 1.0)
                perde += s
        return {"matched_profit_if_win": vince, "matched_profit_if_lose": perde}


class _Mercato:
    """Firma di `flumine.markets.market.Market` su place/cancel."""

    def __init__(self) -> None:
        self.market_id = MID
        self.blotter = _Blotter()
        self.piazzati: List[Any] = []
        self.client_usati: List[Any] = []
        self.annullati: List[Any] = []
        self.closed = False

    def place_order(self, order: Any, market_version: Any = None, execute: bool = True,
                    force: bool = False, client: Any = None) -> bool:
        order.placing()
        order.executable()
        self.piazzati.append(order)
        self.client_usati.append(client)
        self.blotter.ordini.append(order)
        return True

    def cancel_order(self, order: Any, size_reduction: Any = None,
                     force: bool = False) -> None:
        self.annullati.append(order)
        if order is None or getattr(order, "status", None) not in _VIVI:
            return
        # Betfair conferma l'annullo: il residuo sparisce, l'abbinato resta
        if isinstance(order, types.SimpleNamespace):
            order.size_remaining = 0.0
            order.status = OrderStatus.EXECUTION_COMPLETE
        else:
            order.responses.current_order = types.SimpleNamespace(
                size_matched=order.size_matched, size_remaining=0.0,
                average_price_matched=order.average_price_matched)
            order.execution_complete()


def _riempi(order: Any) -> None:
    """Il fill come lo riporta lo stream ordini di Betfair."""
    order.responses.current_order = types.SimpleNamespace(
        size_matched=float(order.order_type.size), size_remaining=0.0,
        average_price_matched=float(order.order_type.price))
    order.execution_complete()


def _ordine_a_mercato(oid: str, side: str, prezzo: float, chiesto: float,
                      abbinato: float, vivo: bool = True) -> Any:
    return types.SimpleNamespace(
        id=oid, bet_id="B" + oid, market_id=MID, selection_id=SEL, handicap=0.0,
        side=side, size_matched=abbinato,
        average_price_matched=prezzo if abbinato else 0.0,
        size_remaining=(chiesto - abbinato) if vivo else 0.0,
        status=OrderStatus.EXECUTABLE if vivo else OrderStatus.EXECUTION_COMPLETE,
        order_type=types.SimpleNamespace(price=prezzo, size=chiesto))


def _runner(sel: int, bb: float, bl: float) -> Any:
    return types.SimpleNamespace(
        selection_id=sel, status="ACTIVE", handicap=0.0, last_price_traded=bb,
        ex=types.SimpleNamespace(available_to_back=[{"price": bb, "size": 500.0}],
                                 available_to_lay=[{"price": bl, "size": 500.0}],
                                 traded_volume=[]))


def _libro(ms: int, bb: float = BB, bl: float = BL) -> Any:
    return types.SimpleNamespace(
        market_id=MID, status="OPEN", inplay=True, total_matched=1e7,
        publish_time_epoch=ms,
        publish_time=_dt.datetime.fromtimestamp(ms / 1000.0, tz=_dt.timezone.utc),
        runners=[_runner(SEL, bb, bl), _runner(SEL2, 1.95, 1.97)],
        number_of_active_runners=2,
        market_definition=types.SimpleNamespace(market_time=None,
                                                market_type="MATCH_ODDS"))


class _Db:
    """Le firme di `tennis_db` che coda, runner e ponte usano."""

    def __init__(self, bot: str) -> None:
        self.bot = bot
        self.righe_coda: List[Dict[str, Any]] = []
        self.fatte: List[tuple] = []
        self.errori: List[tuple] = []
        self.stati: List[tuple] = []
        self.attivita: List[tuple] = []
        self.stato_riga = "running"

    # coda
    def list_pending_tennis_orders(self, limit: int = 5) -> List[Dict[str, Any]]:
        out, self.righe_coda = self.righe_coda[:limit], self.righe_coda[limit:]
        return out

    def claim_tennis_order(self, rid: Any) -> bool:
        return True

    def write_tennis_order_done(self, rid: Any, result: Dict[str, Any]) -> None:
        self.fatte.append((rid, result))

    def write_tennis_order_error(self, rid: Any, result: Dict[str, Any]) -> None:
        self.errori.append((rid, result))

    def get_tennis_client(self) -> Any:
        return object()

    # runner
    def list_tennis_bot_controls(self, event_id: Any = None,
                                 statuses: Any = None) -> List[Dict[str, Any]]:
        if statuses and self.stato_riga not in statuses:
            return []
        return [{"event_id": EV, "bot_key": self.bot, "status": self.stato_riga}]

    def set_tennis_bot_status(self, event_id: Any, bot_key: Any, status: str,
                              **kw: Any) -> None:
        self.stato_riga = status
        self.stati.append((event_id, bot_key, status, kw))

    def write_tennis_bot_activity(self, event_id: Any, bot_key: Any, kind: str,
                                  payload: Dict[str, Any]) -> None:
        self.attivita.append((event_id, bot_key, kind, dict(payload)))


def _riga_chiudi(rid: int, bot: str, mode: str = "paper", market_id: str = MID,
                 event_id: str = EV) -> Dict[str, Any]:
    payload = {"action": "chiudi_bot", "bot": bot, "event_id": event_id,
               "market_id": market_id, "mode": mode, "trade_id": 9000 + rid,
               "client_ref": "ref-%d" % rid}
    return {"id": rid, "client_ref": "ref-%d" % rid, "payload": payload,
            "status": "pending", "result": None, "error": None,
            "created_at": "2026-09-24T10:00:00+00:00", "processed_at": None}


# ===========================================================================
# impalcatura
# ===========================================================================
@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    GT.azzera_per_i_test()
    monkeypatch.setattr(LOW, "_kill_switch", lambda: False)
    monkeypatch.setattr(LOW, "_db_kill_switch", lambda: False)
    monkeypatch.setattr(GT, "aggiorna_impostazioni", lambda sb, forza=False: None)
    monkeypatch.setattr(LC, "get_channel", lambda: None)
    monkeypatch.setattr(W, "_reconcile_tracked", lambda sess, fl: None)
    yield
    GT.azzera_per_i_test()


# gli stessi gate che il banco apre in `gate-aperto` (numeri della UI): senza,
# lo scalper col preset non entra in gioco e non esisterebbe un ingresso da
# vedere nel controllo "nessun rientro"
_PARAMS = {
    "tennis_scalper": {"min_size": 0.0, "price_min": 1.01, "price_max": 30.0,
                       "min_flow": 0.0, "warmup_ms": 0, "inplay_tick_enabled": True,
                       "runner_filter": "all"},
    "tennis_pro": {},
    "tennis_flb": {},
    "tennis_swing": {},
}


def _arma(bot: str, mode: str = "paper", runner: str = "PAPER",
          client_paper: Any = None) -> Any:
    df = streaming_market_data_filter(fields=["EX_BEST_OFFERS"], ladder_levels=3)
    control = {"event_id": EV, "bot_key": bot, "status": "running", "stake": 2,
               "params": dict(_PARAMS[bot]), "stats": None, "mode": mode,
               "dry_run": False}
    return TR._instantiate_bot(bot, control, MID, {"Alfa Uno": SEL, "Beta Due": SEL2},
                               lambda *a, **k: None, df, runner, market_ids=[MID],
                               client_paper=client_paper)


def _semina_aperta(bot: str, strat: Any, m: _Mercato) -> Any:
    """Una posizione APERTA come la lascia l'ingresso del bot: chiesti 4,00,
    abbinati 2,00, residuo 2,00 ancora vivo."""
    lato = "LAY" if bot == "tennis_flb" else "BACK"
    ing = _ordine_a_mercato("ing1", lato, 2.0, 4.0, 2.0, vivo=True)
    m.blotter.ordini.append(ing)
    if bot == "tennis_scalper":
        slot = strat._slot(MID, SEL)
        slot.status = SC.QUOTING
        slot.entry = ing
        slot.entry_side = "BACK"
        slot.t_quote = T0
        slot.ref_price = 2.0
        slot.inplay_cycle = True
    elif bot == "tennis_pro":
        strat._trade[MID] = {
            "state": PRO.OPEN, "sel": SEL, "side": "BACK", "entry": 2.0,
            "target": 1.9, "stop": 2.1, "kind": "break_point", "staged_done": False,
            "staged_order": None, "order": ing, "wait": 0, "t_open": T0,
            "entry_games": None}
    elif bot == "tennis_flb":
        strat._pos_state[(MID, SEL)] = {"state": "OPEN", "entry": 2.0, "order": ing,
                                        "wait": 0, "greened": False, "t0": T0}
    else:
        strat._tr[MID] = {"sel": SEL, "side": "BACK", "etk": 50, "anchor": 45.0,
                          "order": ing, "held": 0, "wait": 0, "px": 2.0, "t0": T0}
    return ing


def _semina_in_uscita(bot: str, strat: Any, m: _Mercato) -> Any:
    """Il bot sta GIA' uscendo da solo: ingresso abbinato 2,00 e la SUA
    copertura intera in volo (viva a mercato)."""
    lato = "LAY" if bot == "tennis_flb" else "BACK"
    lato_cop = "BACK" if lato == "LAY" else "LAY"
    ing = _ordine_a_mercato("ing1", lato, 2.0, 2.0, 2.0, vivo=False)
    prezzo_cop = BB if lato_cop == "BACK" else BL
    # la copertura INTERA dell'abbinato (2,00 a 2,00): 4 / prezzo
    cop = _ordine_a_mercato("cop1", lato_cop, prezzo_cop, round(4.0 / prezzo_cop, 2),
                            0.0, vivo=True)
    m.blotter.ordini.extend([ing, cop])
    if bot == "tennis_scalper":
        strat.force_flat = True
        slot = strat._slot(MID, SEL)
        slot.status = SC.FLATTENING
        slot.entry = ing
        slot.entry_side = "BACK"
        slot.flatten_orders = [cop]
        slot.inplay_cycle = True
    elif bot == "tennis_pro":
        strat._trade[MID] = {
            "state": PRO.CLOSING, "sel": SEL, "side": "BACK", "entry": 2.0,
            "target": 1.9, "stop": 2.1, "kind": "break_point", "staged_done": False,
            "staged_order": None, "order": ing, "wait": 0, "t_open": T0,
            "entry_games": None, "close_order": cop, "t_close": T0,
            "close_wait": 0, "booked": 0.0}
    elif bot == "tennis_flb":
        strat._pos_state[(MID, SEL)] = {
            "state": "OPEN", "entry": 2.0, "order": ing, "wait": 0, "greened": True,
            "green_order": cop, "green_locked": False, "green_price": BB,
            "green_fr": 1.0, "green_est": 0.0, "t0": T0}
    else:
        strat._tr[MID] = {"sel": SEL, "side": "BACK", "etk": 50, "anchor": 45.0,
                          "order": ing, "held": 0, "wait": 0, "px": 2.0, "t0": T0,
                          "closing": True, "close_order": cop, "close_wait": 0,
                          "t_close": T0, "locked": 0.0}
    return cop


def _quadro(bot: str, strat: Any, m: _Mercato, ordine_mode: str = "PAPER") -> Any:
    session = TR.TennisLiveSession(trading=object())
    session.market_meta = {EV: {"market_id": MID}}
    session.hosted = {(EV, bot): strat}
    session.order_mode = ordine_mode
    fl = types.SimpleNamespace(markets=[m])
    return session, fl


def _gira_coda(monkeypatch, db: _Db, session: Any, runner: str = "PAPER") -> None:
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", runner)
    monkeypatch.setattr(W, "tennis_db", db)
    monkeypatch.setattr(W, "_last_db_queue_poll", 0.0)
    W.tennis_live_order_worker({}, types.SimpleNamespace(), session)


def _gira_runner(monkeypatch, db: _Db, session: Any, fl: Any) -> None:
    monkeypatch.setattr(TR, "tennis_db", db)
    TR.bot_control_worker({}, fl, session)


def _chiusura_attesa(bot: str) -> tuple:
    """(lato, prezzo, size) della chiusura dell'ABBINATO (2,00 a 2,00) al touch."""
    if bot == "tennis_flb":           # LAY abbinato -> BACK a bb
        return "BACK", BB, round(4.0 / BB, 2)
    return "LAY", BL, round(4.0 / BL, 2)   # BACK abbinato -> LAY a bl


_PORTA_INGRESSO = {
    # il metodo che il bot chiama SOLO quando valuta un ingresso nuovo
    "tennis_scalper": "_try_enter",
    "tennis_pro": "_sig_break_point",
    "tennis_swing": "_favourite",
}


def _spia_ingressi(bot: str, strat: Any) -> List[Any]:
    """Conta i tentativi d'ingresso. Per il FLB e' il `_place` di un'apertura
    (copertura=False) su un book col favorito estremo (best-lay <= lay_max)."""
    chiamate: List[Any] = []
    if bot == "tennis_flb":
        orig = strat._place

        def _spia(market, sel, side, price, size, *, copertura=False):
            if not copertura:
                chiamate.append((sel, side, price, size))
            return orig(market, sel, side, price, size, copertura=copertura)
        strat._place = _spia
        return chiamate
    nome = _PORTA_INGRESSO[bot]
    orig = getattr(strat, nome)

    def _spia2(*a, **k):
        chiamate.append(a)
        return orig(*a, **k)
    setattr(strat, nome, _spia2)
    if bot == "tennis_pro":
        # il PRO valuta i segnali solo con un punteggio e su un punto NUOVO
        strat.score = TennisScore(event_id=EV, sets_home=0, sets_away=0,
                                  games_home=1, games_away=1, point_home="15",
                                  point_away="0", server="home",
                                  home_name="Alfa Uno", away_name="Beta Due")
    return chiamate


def _libro_ingresso(bot: str, ms: int) -> Any:
    if bot == "tennis_flb":
        return _libro(ms, bb=1.04, bl=1.05)   # favorito estremo: il FLB entrerebbe
    return _libro(ms)


# ===========================================================================
# 1. richiesta -> uscita manuale -> una chiusura sull'abbinato -> stop
# ===========================================================================
@pytest.mark.parametrize("bot", BOTS)
def test_chiudi_ora_chiude_l_abbinato_una_volta_e_ferma_il_bot(bot, monkeypatch):
    strat = _arma(bot)
    m = _Mercato()
    ing = _semina_aperta(bot, strat, m)
    session, fl = _quadro(bot, strat, m)
    db = _Db(bot)
    db.righe_coda = [_riga_chiudi(1, bot)]

    # (a) la coda: presa in carico, la riga resta `processing` (nessun esito)
    _gira_coda(monkeypatch, db, session)
    assert db.fatte == [] and db.errori == []
    assert strat.uscita_manuale_chiesta is True
    assert CM.in_chiusura(session, (EV, bot))

    # (b) il bot al primo book: annulla il residuo vivo e chiude l'ABBINATO
    strat.process_market_book(m, _libro(T0 + 1_000))
    assert strat.uscita_manuale["esito"] == CD.ESITO_USCITA_AVVIATA
    assert strat.uscita_manuale["motivo"] == CD.MOTIVO_USCITA_MANUALE
    assert ing in m.annullati, "il residuo vivo dell'ingresso non e' stato annullato"
    assert len(m.piazzati) == 1, "una sola chiusura, non %d" % len(m.piazzati)
    chiusura = m.piazzati[0]
    lato, prezzo, size = _chiusura_attesa(bot)
    assert chiusura.side == lato
    assert chiusura.order_type.price == pytest.approx(prezzo)
    # sull'ABBINATO (2,00), mai sul chiesto (4,00: sarebbe il doppio)
    assert chiusura.order_type.size == pytest.approx(size, abs=0.011)

    # (c) il runner: la chiusura e' in volo -> nessun esito, bot ancora vivo
    _gira_runner(monkeypatch, db, session, fl)
    assert not getattr(strat, "_tennis_disabled", False)
    assert db.fatte == []

    # (d) la chiusura si abbina; il bot lo vede e chiude la sua memoria
    _riempi(chiusura)
    strat.process_market_book(m, _libro(T0 + 2_000))
    strat.process_market_book(m, _libro(T0 + 3_000))
    assert len(m.piazzati) == 1, "dopo la chiusura il bot ha piazzato ancora"
    assert strat.uscita_manuale_finita() is True

    # (e) NESSUN RIENTRO: anche su un book da ingresso il bot non valuta niente
    spia = _spia_ingressi(bot, strat)
    for i in range(3):
        strat.process_market_book(m, _libro_ingresso(bot, T0 + 4_000 + i * 1_000))
    assert spia == [], "il bot ha rivalutato un ingresso dopo il chiudi ora"
    assert len(m.piazzati) == 1

    # (f) il runner conclude: bot disabilitato, riga ferma col marcatore, esito
    _gira_runner(monkeypatch, db, session, fl)
    assert strat._tennis_disabled is True
    assert not CM.in_chiusura(session, (EV, bot))
    fermate = [s for s in db.stati if s[2] == "stopped"]
    assert len(fermate) == 1
    marcatore = fermate[0][3]["stats"][CM.CHIAVE_STATS]
    assert marcatore["esito"] == CD.ESITO_USCITA_AVVIATA and marcatore["flat"] is True
    assert [rid for rid, _ in db.fatte] == [1] and db.errori == []
    esito = db.fatte[0][1]
    assert esito["ok"] is True and esito["esito"] == CD.ESITO_USCITA_AVVIATA
    assert esito["mode"] == "paper" and esito["bot"] == bot
    assert "eseguita" in esito["message"]

    # (g) il ponte NON lo riarma su quella partita (interruttore acceso)
    assert (EV, bot) in CM.chiusi_dall_utente(
        [{"event_id": EV, "bot_key": bot, "status": "stopped",
          "stats": fermate[0][3]["stats"]}])


# ===========================================================================
# 2. richiesta ambigua -> rifiutata, bot intatto
# ===========================================================================
@pytest.mark.parametrize("bot", BOTS)
def test_chiudi_ora_richiesta_ambigua_rifiutata(bot, monkeypatch):
    strat = _arma(bot)
    m = _Mercato()
    _semina_aperta(bot, strat, m)
    session, _fl = _quadro(bot, strat, m)
    altro = next(b for b in BOTS if b != bot)
    db = _Db(bot)
    db.righe_coda = [
        _riga_chiudi(11, bot, mode="live"),              # modalita' diversa
        _riga_chiudi(12, bot, market_id="1.999"),        # mercato diverso
        _riga_chiudi(13, altro),                          # bot non ospitato
        _riga_chiudi(14, bot, event_id="99999999"),      # partita diversa
    ]
    _gira_coda(monkeypatch, db, session)
    per_rid = {rid: res for rid, res in db.errori}
    assert set(per_rid) == {11, 12, 13, 14} and db.fatte == []
    assert per_rid[11]["error"] == "richiesta_ambigua"
    assert "paper e live non si mischiano" in per_rid[11]["message"]
    assert per_rid[12]["error"] == "richiesta_ambigua"
    assert per_rid[13]["error"] == "bot_non_ospitato"
    assert per_rid[14]["error"] == "bot_non_ospitato"
    assert all(r["message"].startswith("rifiutato") for r in per_rid.values())
    # il bot non ha ricevuto nessun comando: al book dopo gira la SUA strategia
    # di sempre, senza nessuna uscita manuale
    assert strat.uscita_manuale_chiesta is False
    assert not CM.in_chiusura(session, (EV, bot))
    strat.process_market_book(m, _libro(T0 + 1_000))
    assert strat.uscita_manuale is None


# ===========================================================================
# 3. gia' in uscita -> nessun secondo ordine (e nessun secondo comando)
# ===========================================================================
@pytest.mark.parametrize("bot", BOTS)
def test_chiudi_ora_gia_in_uscita_nessun_secondo_ordine(bot, monkeypatch):
    strat = _arma(bot)
    m = _Mercato()
    cop = _semina_in_uscita(bot, strat, m)
    session, fl = _quadro(bot, strat, m)
    db = _Db(bot)
    db.righe_coda = [_riga_chiudi(21, bot), _riga_chiudi(22, bot)]   # anche doppia
    _gira_coda(monkeypatch, db, session)
    assert db.fatte == [] and db.errori == []
    # la richiesta doppia e' registrata come tale, senza un secondo comando
    assert session.chiusure_manuali[(EV, bot)].get("doppie") == [22]

    for i in range(3):
        strat.process_market_book(m, _libro(T0 + 1_000 + i * 500))
    assert strat.uscita_manuale["esito"] == CD.ESITO_GIA_IN_USCITA
    assert m.piazzati == [], "il bot gia' in uscita ha piazzato un SECONDO ordine"
    assert cop not in m.annullati, "la copertura in volo e' stata annullata"

    # la copertura del bot si abbina: la chiusura finisce, esito a entrambe
    _riempi_ns(cop)
    strat.process_market_book(m, _libro(T0 + 3_000))
    strat.process_market_book(m, _libro(T0 + 3_500))
    assert m.piazzati == []
    _gira_runner(monkeypatch, db, session, fl)
    assert strat._tennis_disabled is True
    assert sorted(rid for rid, _ in db.fatte) == [21, 22] and db.errori == []
    for _rid, res in db.fatte:
        assert res["esito"] == CD.ESITO_GIA_IN_USCITA
        assert "gia' in uscita" in res["message"]


def _blotter_illeggibile(flumine: Any, strat: Any) -> bool:
    """`_strategy_is_flat` quando il blotter non si legge: solleva (avanza lo
    tratta come NON flat, fail-safe)."""
    raise RuntimeError("blotter illeggibile")


@pytest.mark.parametrize("caso", ["residuo", "blotter_illeggibile"])
def test_chiudi_ora_posizione_non_pari_dopo_la_grazia_e_error_mai_stopped(caso, monkeypatch):
    """Il bot ha FINITO la sua uscita ma il blotter NON e' pari (residuo fra 1 e
    2 centesimi: il PRO lo chiama pari a 0,02, il runner no a 0,01) oppure non
    si legge. Prima della grazia di 45 s non si conclude; dopo, la riga va a
    `error` col messaggio che lo DICE - mai uno `stopped` bugiardo."""
    bot = "tennis_pro"
    strat = _arma(bot)
    m = _Mercato()
    _semina_aperta(bot, strat, m)
    session, fl = _quadro(bot, strat, m)
    db = _Db(bot)
    cmd = CM.comando_da_riga(_riga_chiudi(51, bot))
    assert CM.prendi_in_carico(session, 51, cmd, db=db, adesso=1000.0) is None
    strat.process_market_book(m, _libro(T0 + 1_000))
    assert len(m.piazzati) == 1
    chiusura = m.piazzati[0]
    abbinata = 1.98 if caso == "blotter_illeggibile" else 1.99   # 1.99: residuo 0,0198
    chiusura.responses.current_order = types.SimpleNamespace(
        size_matched=abbinata, size_remaining=0.0,
        average_price_matched=float(chiusura.order_type.price))
    chiusura.execution_complete()
    strat.process_market_book(m, _libro(T0 + 2_000))
    assert strat.uscita_manuale_finita() is True
    e_flat = _blotter_illeggibile if caso == "blotter_illeggibile" else TR._strategy_is_flat
    if caso == "residuo":
        assert TR._strategy_is_flat(fl, strat) is False
    kw = dict(e_flat=e_flat, disabilita=TR._disable_strategy, db=db)
    # dentro la grazia: niente di concluso, nessuno stato scritto
    assert CM.avanza(fl, session, adesso=1010.0, **kw) == []
    assert CM.avanza(fl, session, adesso=1010.0 + CM.GRAZIA_FLAT_S - 1, **kw) == []
    assert db.stati == [] and db.fatte == []
    # oltre la grazia: conclusa, ma DICHIARATA non pari
    assert CM.avanza(fl, session, adesso=1010.0 + CM.GRAZIA_FLAT_S + 1, **kw) == [(EV, bot)]
    stati = [s[2] for s in db.stati]
    assert stati == ["error"], "posizione NON pari dichiarata %s" % stati
    kw_riga = db.stati[0][3]
    assert "NON e' pari" in (kw_riga.get("error") or "")
    assert kw_riga["stats"][CM.CHIAVE_STATS]["flat"] is False
    assert [rid for rid, _ in db.fatte] == [51]
    assert "ATTENZIONE" in db.fatte[0][1]["message"]
    assert db.fatte[0][1]["flat"] is False
    assert strat._tennis_disabled is True


def _riempi_ns(o: Any) -> None:
    o.size_matched = float(o.order_type.size)
    o.average_price_matched = float(o.order_type.price)
    o.size_remaining = 0.0
    o.status = OrderStatus.EXECUTION_COMPLETE


# ===========================================================================
# 4. paper/live della riga rispettato
# ===========================================================================
@pytest.mark.parametrize("bot", BOTS)
def test_chiudi_ora_rispetta_la_modalita_della_riga(bot, monkeypatch):
    # (a) bot LIVE (runner LIVE, riga live, dry_run tolto): una richiesta
    # 'paper' NON lo tocca; la 'live' si'
    strat = _arma(bot, mode="live", runner="LIVE")
    assert strat._tennis_modalita_esecuzione == "LIVE"
    m = _Mercato()
    _semina_aperta(bot, strat, m)
    session, _fl = _quadro(bot, strat, m, ordine_mode="LIVE")
    db = _Db(bot)
    db.righe_coda = [_riga_chiudi(31, bot, mode="paper")]
    _gira_coda(monkeypatch, db, session, runner="LIVE")
    assert [rid for rid, _ in db.errori] == [31]
    assert db.errori[0][1]["error"] == "richiesta_ambigua"
    assert strat.uscita_manuale_chiesta is False
    db.righe_coda = [_riga_chiudi(32, bot, mode="live")]
    _gira_coda(monkeypatch, db, session, runner="LIVE")
    assert [rid for rid, _ in db.errori] == [31] and db.fatte == []
    assert strat.uscita_manuale_chiesta is True

    # (b) bot PAPER in un runner LIVE: la riga 'paper' NON e' scartata come
    # "cross-mode" dal worker; la 'live' e' ambigua; la chiusura va sul client
    # SIMULATO affiancato, mai su quello reale
    api = betfairlightweight.APIClient("utente", "pwd", app_key="chiave")
    paper = GT.build_client_paper_affiancato(api)
    strat2 = _arma(bot, mode="paper", runner="LIVE", client_paper=paper)
    assert strat2._tennis_modalita_esecuzione == "PAPER"
    m2 = _Mercato()
    _semina_aperta(bot, strat2, m2)
    session2, _fl2 = _quadro(bot, strat2, m2, ordine_mode="LIVE")
    db2 = _Db(bot)
    db2.righe_coda = [_riga_chiudi(41, bot, mode="live"), _riga_chiudi(42, bot, mode="paper")]
    _gira_coda(monkeypatch, db2, session2, runner="LIVE")
    assert [rid for rid, _ in db2.errori] == [41]
    assert db2.errori[0][1]["error"] == "richiesta_ambigua"
    assert strat2.uscita_manuale_chiesta is True
    strat2.process_market_book(m2, _libro(T0 + 1_000))
    assert len(m2.piazzati) == 1
    assert m2.client_usati == [paper], "la chiusura di un bot paper non e' andata sul client simulato"


# ===========================================================================
# il controllo di condotta del banco: B9 (chiudi ora) sa diventare rosso
# ===========================================================================
from Betfair.stream.tennis_live import certificazione_bot as CERT   # noqa: E402


def _riga_oss(oid: str, side: str, status: str, sel: int = SEL) -> Dict[str, Any]:
    return {"order_id": oid, "status": status, "side": side, "selection_id": sel,
            "market_id": MID, "size": 1.98, "price": BL, "size_matched": 0.0,
            "size_remaining": 1.98, "average_price_matched": 0.0}


def _oss_manuale(ordini, esito=CD.ESITO_USCITA_AVVIATA, dopo=(), ingressi=()) -> Any:
    return CERT.Osservazione(bot="tennis_pro", scenario="chiudi-ora", market_id=MID,
                             ordini=list(ordini), manuale_chiesta=True,
                             manuale_esito=esito, ordini_dopo_manuale=set(dopo),
                             ids_ingresso=set(ingressi))


def test_chiudi_ora_b9_registrato_e_sollecitato_solo_col_comando():
    assert "B9" in {c for c, _ in CERT.elenco_controlli()}
    soll: Dict[str, int] = {}
    CERT.verifica(CERT.Osservazione(bot="tennis_pro", market_id=MID), soll)
    assert soll.get("B9", 0) == 0          # senza comando: nessun caso
    CERT.verifica(_oss_manuale([]), soll)
    assert soll.get("B9", 0) == 1


def test_chiudi_ora_b9_verde_con_una_sola_chiusura():
    esiti = CERT.verifica(_oss_manuale([_riga_oss("c1", "LAY", "Executable")], dopo={"c1"}))
    assert not [v for v in esiti if v.codice == "B9"]


def test_chiudi_ora_b9_rosso_su_rientro_doppia_uscita_e_ordine_senza_posizione():
    rientro = _oss_manuale([_riga_oss("e2", "BACK", "Executable")], dopo={"e2"},
                           ingressi={"e2"})
    assert any(v.codice == "B9" and "rientro" in v.dettaglio for v in CERT.verifica(rientro))
    doppia = _oss_manuale([_riga_oss("c1", "LAY", "Executable"),
                           _riga_oss("c2", "LAY", "Executable")], dopo={"c1", "c2"})
    assert any(v.codice == "B9" and "DOPPIA" in v.dettaglio for v in CERT.verifica(doppia))
    # un annullo in volo NON e' una seconda uscita decisa dal bot
    in_annullo = _oss_manuale([_riga_oss("c1", "LAY", "Cancelling"),
                               _riga_oss("c2", "LAY", "Executable")], dopo={"c1", "c2"})
    assert not [v for v in CERT.verifica(in_annullo) if v.codice == "B9"]
    niente = _oss_manuale([_riga_oss("c1", "LAY", "Executable")], dopo={"c1"},
                          esito=CD.ESITO_NESSUNA_POSIZIONE)
    assert any(v.codice == "B9" and "nessuna posizione" in v.dettaglio
               for v in CERT.verifica(niente))


@pytest.mark.parametrize("bot", BOTS)
def test_chiudi_ora_il_ponte_del_banco_usa_la_via_di_produzione(bot):
    """Il `_Ponte` del replay nello scenario `chiudi-ora` (senza replay: un
    mercato finto e tre giri): clic a meta' partita via `prendi_in_carico`,
    chiusura del bot, `avanza` alla cadenza del bot_control_worker, B9 verde."""
    from Betfair.stream.tennis_live.tools import replay_bot as RB

    strat = _arma(bot)
    m = _Mercato()
    _semina_aperta(bot, strat, m)
    ref = CERT.Referto(event_id=EV, bot=bot, scenario=RB.SCENARIO_CHIUDI_ORA)
    ponte = RB._Ponte(strat=strat, bot_key=bot, event_id=EV, market_id=MID,
                      scenario=RB.SCENARIO_CHIUDI_ORA, punteggi=[], referto=ref,
                      quadro=types.SimpleNamespace(markets=[m]), modalita="PAPER",
                      stake=2.0, cap=None, attivita=[], rifiuta=None, ogni_ms=0)
    ponte.imposta_finestra(T0, T0 + 20_000)
    ponte._forse_chiudi_ora(m, T0 + 5_000)          # prima di meta': niente
    assert strat.uscita_manuale_chiesta is False
    ponte._forse_chiudi_ora(m, T0 + 10_000)         # il clic
    assert strat.uscita_manuale_chiesta is True
    libro = _libro(T0 + 10_000)
    strat.process_market_book(m, libro)
    ponte.giro(m, libro, 0)
    assert len(m.piazzati) == 1
    _riempi(m.piazzati[0])
    for i in range(1, 4):
        lb = _libro(T0 + 10_000 + i * 1_000)
        strat.process_market_book(m, lb)
        ponte.giro(m, lb, 0)
    ponte._forse_chiudi_ora(m, T0 + 14_000)         # avanza (>= 3 s dopo)
    assert strat._tennis_disabled is True
    assert ref.sollecitati.get("B9", 0) >= 1
    assert not [v for v in ref.violazioni if v.codice == "B9"]
    assert any("CHIUDI ORA concluso" in n for n in ref.note)


def test_chiudi_ora_scenario_del_banco_dichiarato():
    from Betfair.stream.tennis_live.tools import replay_bot as RB

    assert RB.SCENARIO_CHIUDI_ORA in RB.SCENARI_DESCRITTI
    # stessi gate di `gate-aperto` (numeri della UI), nessuna strategia toccata
    for bot in BOTS:
        assert RB.parametri_scenario(RB.SCENARIO_CHIUDI_ORA, bot) == \
            RB.parametri_scenario("gate-aperto", bot)


# ===========================================================================
# il PONTE non riarma una (partita, bot) chiusa dall'utente
# ===========================================================================
class _DbPonte:
    def __init__(self, righe: List[Dict[str, Any]]) -> None:
        self.righe = righe
        self.armati: List[Dict[str, Any]] = []

    def list_tennis_bot_services(self) -> List[Dict[str, Any]]:
        return [{"bot_key": b, "status": "running", "mode": "paper", "stake": 2,
                 "params": {}, "stats": {}} for b in ("tennis_pro", "tennis_flb")]

    def list_tennis_bot_controls(self, event_id: Any = None,
                                 statuses: Any = None) -> List[Dict[str, Any]]:
        out = [dict(r) for r in self.righe
               if (event_id is None or r["event_id"] == event_id)
               and (not statuses or r["status"] in statuses)]
        return out

    def upsert_tennis_bot_control(self, row: Dict[str, Any]) -> None:
        self.armati.append(dict(row))

    def set_tennis_bot_status(self, event_id: Any, bot_key: Any, status: str, **kw: Any) -> None:
        pass

    def set_tennis_bot_service_state(self, bot_key: Any, **kw: Any) -> bool:
        return True


def test_chiudi_ora_il_ponte_non_riarma_la_partita_chiusa(monkeypatch):
    monkeypatch.setattr(S, "_followed_event_ids", lambda: {EV})
    marcata = {"event_id": EV, "bot_key": "tennis_pro", "status": "stopped",
               "stats": {CM.CHIAVE_STATS: {"richiesta": 1, "esito": "uscita_avviata"}}}
    semplice = {"event_id": EV, "bot_key": "tennis_flb", "status": "stopped",
                "stats": {"pnl": 0.0}}
    db = _DbPonte([marcata, semplice])
    r = S.riconcilia_interruttori(db=db)
    armati = {(a["event_id"], a["bot_key"]) for a in db.armati}
    assert (EV, "tennis_pro") not in armati, "il ponte ha riarmato un bot chiuso dall'utente"
    assert (EV, "tennis_flb") in armati          # una riga ferma NORMALE si riarma
    assert r["armati"] == 1
