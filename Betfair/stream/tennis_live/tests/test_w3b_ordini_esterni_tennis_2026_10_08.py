# -*- coding: utf-8 -*-
"""W3b (08/10) - I QUATTRO BOT TENNIS SANNO SUBITO DEGLI ORDINI ESTERNI (sito, ladder).

Ordine dell'utente: "quando intervengo io dal sito o dall'app su un'operazione dei
bot, i bot lo sanno e non fanno altro". Le registrazioni tennis stanno sul PC
dell'utente: qui test con oggetti VERI dove esistono.

  * i bot sono le classi VERE istanziate da ``tennis_runner._instantiate_bot``
    (preset, modalita', scoping sul mercato);
  * ``Flumine`` VERO con ``BetfairClient`` VERO (nessun login), il suo
    ``_process_current_orders``; la cache VERA dello stream ordini
    (``OrderBookCache``); gli ordini del bot creati DA FLUMINE dal ref dello stream;
  * l'osservatore VERO (``esiti_ordini_canale.osserva_conto_su_flumine``) montato
    da ``ordini_esterni_tennis.registro_per_framework``;
  * ``_disable_strategy`` e ``_strategy_is_flat`` VERI del runner; il marcatore
    letto dalla funzione VERA del ponte (``chiusura_manuale.chiusi_dall_utente``);
  * paper: ``session.tracked_orders`` con la forma che scrive
    ``tennis_live_order_worker._track_manual`` e un ``BetfairOrder`` VERO
    aggiornato con un ``CurrentOrder`` VERO.
Sostituiti: ``Market.cancel_order`` (confine con la rete: si REGISTRA) e il DB
(firme di ``tennis_db``).

Falsificati: referto ``AUDIT_2026-10-08/W3B_CONSAPEVOLEZZA_FLUMINE.md``. ASCII-only.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import pytest
from betfairlightweight.filters import streaming_market_data_filter

from Betfair.stream.tennis_live import chiusura_manuale as CM
from Betfair.stream.tennis_live import ordini_esterni_tennis as OET
from Betfair.stream.tennis_live import tennis_runner as TR
from Betfair.stream.tennis_scalper import ordini_esterni as OE

MID = "1.300"
ALTRO = "1.301"
EV = "35800777"
SEL, SEL2 = 101, 202
BOTS = ["tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing"]


def _ora() -> int:
    return int(time.time() * 1000)


def _client(paper: bool, utente: str = "u") -> Any:
    from betfairlightweight import APIClient
    from flumine import clients

    return clients.BetfairClient(APIClient(utente, "p", app_key="k"), paper_trade=paper,
                                 order_stream=True)


def _arma(bot: str, mode: str, runner: str, client_paper: Any = None) -> Any:
    df = streaming_market_data_filter(fields=["EX_BEST_OFFERS"], ladder_levels=3)
    control = {"event_id": EV, "bot_key": bot, "status": "running", "stake": 2,
               "params": {}, "stats": None, "mode": mode, "dry_run": False}
    return TR._instantiate_bot(bot, control, MID, {"Alfa Uno": SEL, "Beta Due": SEL2},
                               lambda *a, **k: None, df, runner, market_ids=[MID],
                               client_paper=client_paper)


def _uo(bet_id: str, *, side: str, sm: float, rfo: Any, rfs: Any, stato: str = "EC",
        p: float = 2.0, sr: float = 0.0, sel: int = SEL) -> Dict[str, Any]:
    pd = _ora() + 1
    return {"id": bet_id, "p": p, "s": sm + sr, "side": side, "status": stato, "pt": "L",
            "ot": "L", "pd": pd, "md": pd + 1, "avp": p if sm > 0 else None, "sm": sm,
            "sr": sr, "sl": 0.0, "sc": 0.0, "sv": 0.0, "rfo": rfo, "rfs": rfs}


def _current_orders(uo: List[Dict[str, Any]], market_id: str = MID) -> Any:
    from betfairlightweight.streaming.cache import OrderBookCache

    pt = _ora()
    cache = OrderBookCache(market_id, pt, False)
    cache.update_cache({"id": market_id, "orc": [{"id": SEL, "uo": uo}]}, pt)
    return cache.create_resource(0)


class _Db:
    """Le firme di ``tennis_db`` usate dalla conclusione."""

    def __init__(self) -> None:
        self.stati: List[tuple] = []
        self.attivita: List[tuple] = []

    def set_tennis_bot_status(self, event_id: str, bot_key: str, status: str, *,
                              error: Optional[str] = None,
                              stats: Optional[Dict[str, Any]] = None,
                              heartbeat: bool = False, started: bool = False,
                              stopped: bool = False, mode: Optional[str] = None,
                              dry_run: Optional[bool] = None) -> None:
        self.stati.append((event_id, bot_key, status, stopped, stats))

    def write_tennis_bot_activity(self, event_id: str, bot_key: str, kind: str,
                                  payload: Dict[str, Any]) -> None:
        self.attivita.append((event_id, bot_key, kind, payload))


class _Risposta:
    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.data = data


class _Query:
    """Il builder di supabase-py con filtri veri; ``giu`` = ogni lettura solleva."""

    def __init__(self, sb: "_SbFinto", nome: str) -> None:
        self.sb, self.nome, self.filtri = sb, nome, []

    def select(self, *_a: Any, **_k: Any) -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self.filtri.append((col, {str(val)}))
        return self

    def in_(self, col: str, vals: Any) -> "_Query":
        self.filtri.append((col, {str(v) for v in vals}))
        return self

    def execute(self) -> _Risposta:
        self.sb.letture += 1
        if self.sb.giu:
            raise ConnectionError("DB irraggiungibile")
        return _Risposta([dict(r) for r in self.sb.tabelle.get(self.nome, [])
                          if all(str(r.get(c)) in v for c, v in self.filtri)])


class _SbFinto:
    def __init__(self, tabelle: Any = None, giu: bool = False) -> None:
        self.tabelle = dict(tabelle or {})
        self.giu = giu
        self.letture = 0

    def table(self, nome: str) -> _Query:
        return _Query(self, nome)


class _Runner:
    """Il runner tennis ridotto al necessario: framework, sessione, bot ospitato.
    Il DB della verifica (``tennis_db.get_tennis_client``) e' in memoria: la regola
    di W2 (``_proprietari_bot``) gira VERA sopra."""

    def __init__(self, monkeypatch: Any, bot_key: str, *, runner: str = "LIVE",
                 mode: str = "live", tabelle: Any = None, db_giu: bool = False) -> None:
        from flumine import Flumine
        from flumine.markets.market import Market

        from Betfair.stream.tennis_live import tennis_db as TDB

        self.sb = _SbFinto(tabelle, giu=db_giu)
        monkeypatch.setattr(TDB, "get_tennis_client", lambda: self.sb)
        self.annullati: List[str] = []
        questo = self

        def _cancel(market: Any, order: Any, size_reduction: Any = None,
                    force: bool = False) -> bool:
            questo.annullati.append(str(order.bet_id))
            return True

        monkeypatch.setattr(Market, "cancel_order", _cancel)
        self.client = _client(paper=(runner != "LIVE"))
        self.fw = Flumine(client=self.client)
        self.client_paper = None
        if runner == "LIVE" and mode == "paper":
            self.client_paper = _client(paper=True, utente="u-paper")
            self.fw.add_client(self.client_paper)
        self.session = TR.TennisLiveSession(None)
        self.session.order_mode = runner
        self.session.tracked_orders = {}
        self.session.ordini_esterni = OET.registro_per_framework(self.fw, runner,
                                                                 self.session)
        self.bot_key = bot_key
        self.bot = _arma(bot_key, mode, runner, client_paper=self.client_paper)
        self.fw.add_strategy(self.bot)
        self.session.hosted[(EV, bot_key)] = self.bot
        self.sorv = OET.proteggi_bot(self.session, self.fw, EV, bot_key, self.bot,
                                     disabilita=TR._disable_strategy)
        self.db = _Db()

    def proprio(self, bet_id: str, n: int, *, sm: float, sr: float = 0.0,
                stato: str = "E") -> Dict[str, Any]:
        return _uo(bet_id, side="B", sm=sm, sr=sr, stato=stato,
                   rfo="%s-%d" % (self.bot.name_hash, n), rfs=self.bot.name[:15])

    def stream(self, uo: List[Dict[str, Any]], market_id: str = MID,
               client: Any = None) -> None:
        from flumine.events.events import CurrentOrdersEvent

        co = _current_orders(uo, market_id)
        co.client = client or self.client
        self.fw._process_current_orders(CurrentOrdersEvent([co]))

    def concludi(self) -> List[tuple]:
        return OET.concludi_interventi(self.session, self.fw,
                                       e_flat=TR._strategy_is_flat, db=self.db)

    def verifica(self, bet_id: str) -> Any:
        """Aspetta la verifica del thread della conferma (produzione), poi la
        sveglia nella coda di flumine fa decidere: qui la si esegue come
        ``_process_custom_event`` (``callback(flumine, event)``)."""
        from flumine.events.events import CustomEvent

        conferma = self.session.ordini_esterni.conferma
        fine = time.time() + 5.0
        while time.time() < fine and conferma.esito(bet_id) is None \
                and conferma.errore(bet_id) is None:
            time.sleep(0.01)
        time.sleep(0.02)
        eventi = []
        while not self.fw.handler_queue.empty():
            x = self.fw.handler_queue.get_nowait()
            if isinstance(x, CustomEvent):
                eventi.append(x)
        for e in eventi:
            e.callback(self.fw, e)
        return self.sorv.intervento

    def kinds(self) -> List[str]:
        return [a[2] for a in self.db.attivita]


# ===========================================================================
# LIVE: lo stream ordini del conto
# ===========================================================================
@pytest.mark.parametrize("bot", BOTS)
def test_live_ordine_dal_sito_ferma_il_bot_e_lo_marca(monkeypatch, bot):
    r = _Runner(monkeypatch, bot)
    assert r.sorv is not None and r.sorv.modo == "live"
    assert r.session.ordini_esterni.montato is True
    r.stream([r.proprio("B1", 1, sm=2.0, sr=2.0)])
    assert r.sorv.intervento is None, "gli ordini del bot non sono esterni"
    assert not getattr(r.bot, "_tennis_disabled", False)
    r.stream([r.proprio("B1", 1, sm=2.0, sr=2.0),
              _uo("U1", side="L", sm=3.0, rfo=None, rfs=None)])
    # al messaggio: SOSPESO (verifica sul DB in un thread), non ancora fermo
    assert r.sorv.sospesa(MID, SEL)
    ev = r.verifica("U1")
    assert ev is not None and ev["dove"] == "sito" and ev["market_id"] == MID
    assert ev["latenza_ms"] is not None and 0 <= ev["latenza_ms"] < 5000
    assert ev["verifica"]["esito"] == OE.FUORI_BOT
    # nel thread di flumine: vivi annullati, bot inerte
    assert r.annullati == ["B1"]
    assert getattr(r.bot, "_tennis_disabled", False) is True
    assert r.bot.check_market_book(None, None) is False
    # dal bot_control_worker: riga 'stopped' col marcatore e attivita'
    assert r.concludi() == [(EV, bot)]
    (ev_id, bk, status, stopped, stats), = r.db.stati
    assert (ev_id, bk, status, stopped) == (EV, bot, "stopped", True)
    assert stats[CM.CHIAVE_STATS]["come"] == OET.COME
    assert stats[OE.KIND]["bet_id"] == "U1"
    assert r.kinds() == [OE.KIND_VERIFICA, OE.KIND]
    riga = {"event_id": EV, "bot_key": bot, "status": "stopped", "stats": stats}
    assert CM.chiusi_dall_utente([riga]) == {(EV, bot)}, "il ponte non lo riarma"
    assert r.concludi() == [], "una volta sola"


def test_live_ladder_manuale_dell_app_e_un_intervento(monkeypatch):
    r = _Runner(monkeypatch, "tennis_pro")
    r.stream([_uo("A1", side="B", sm=2.0, rfo="abcdef0123456-5", rfs="tennis")])
    assert r.verifica("A1") is not None and r.sorv.intervento["dove"] == "app"


def _ordine_del_runner(r: _Runner, ref: str, bet_id: str, *, coda: Dict[str, Any],
                       mode: str = "live", source: str = "manual") -> Any:
    """Un ordine piazzato DAL RUNNER per una riga di coda, tracciato come lo
    traccia ``_track_manual`` (chiavi vere, ``coda`` compresa)."""
    from flumine import BaseStrategy
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    class _Cap(BaseStrategy):
        def check_market_book(self, market: Any, market_book: Any) -> bool:  # noqa: ARG002
            return False

    cap = _Cap(market_filter={}, name="_cap_%s" % ref)
    o = Trade(MID, SEL, 0.0, cap).create_order(side="LAY",
                                                order_type=LimitOrder(price=2.0, size=4.0))
    o.bet_id = bet_id
    r.session.tracked_orders[ref] = {
        "order": o, "trade": o.trade, "mode": mode, "event_id": EV, "source": source,
        "gen": 0, "coda": {"client_ref": coda.get("client_ref"), "params": coda.get("params")}}
    return o


def test_live_safe_tennis_dalla_coda_del_runner_nessuno_stop(monkeypatch):
    """Safe tennis dalla coda DB del runner tennis: stesso ref del ladder ('tennis'),
    ma la riga di coda eseguita dal runner dice Safe: in-process, nessun DB."""
    r = _Runner(monkeypatch, "tennis_pro")
    _ordine_del_runner(r, "awtq5", "S5", coda={"client_ref": "safe_tennis-t3",
                                               "params": {"source": "safe_tennis"}})
    r.stream([_uo("S5", side="L", sm=4.0, rfo="abcdef0123456-5", rfs="tennis")])
    assert r.verifica("S5") is None
    assert not r.sorv.sospesa(MID, SEL)
    assert not getattr(r.bot, "_tennis_disabled", False)
    assert r.session.ordini_esterni.conferma.esito("S5").startswith("bot:coda")
    assert r.sb.letture == 0, "riconosciuto in-process: nessuna lettura del DB"
    r.concludi()
    assert r.kinds() == [OE.KIND_VERIFICA, OE.KIND_DI_UN_BOT]


def test_live_ordine_di_un_bot_noto_al_db_nessuno_stop(monkeypatch):
    r = _Runner(monkeypatch, "tennis_pro",
                tabelle={"safe_strategy_trades": [{"bet_id": "S6", "mode": "live"}]})
    r.stream([_uo("S6", side="L", sm=4.0, rfo="abcdef0123456-6", rfs="tennis")])
    assert r.verifica("S6") is None and not r.sorv.sospesa(MID, SEL)
    assert r.session.ordini_esterni.conferma.esito("S6") == "bot:tabella:safe_strategy_trades"


def test_live_db_giu_resta_sospeso_e_lo_scrive(monkeypatch):
    from flumine.exceptions import ControlError
    from flumine.order.orderpackage import OrderPackageType
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    r = _Runner(monkeypatch, "tennis_pro", db_giu=True)
    r.stream([_uo("U1", side="L", sm=3.0, rfo=None, rfs=None)])
    assert r.verifica("U1") is None
    r.sorv.controlla()
    assert r.sorv.sospesa(MID, SEL) and not getattr(r.bot, "_tennis_disabled", False)
    ctrl = [c for c in r.fw.trading_controls if getattr(c, "NAME", "") == "ORDINI_ESTERNI"]
    o = Trade(MID, SEL, 0.0, r.bot).create_order(side="BACK",
                                                  order_type=LimitOrder(price=2.0, size=2.0))
    with pytest.raises(ControlError):
        ctrl[0](o, OrderPackageType.PLACE)
    r.concludi()
    assert r.kinds() == [OE.KIND_VERIFICA, OE.KIND_NON_VERIFICABILE]


@pytest.mark.parametrize("rfs,rfo", [
    ("TennisScalperSt", "1234567890abc-9"),     # un ALTRO bot tennis del runner
    ("safe_tennis", "safe_tennis-t3"),          # Safe tennis dal motore
    ("mike", "mike-t1"),                        # un bot calcio (stesso conto)
])
def test_live_ordini_degli_altri_bot_non_sono_un_intervento(monkeypatch, rfs, rfo):
    r = _Runner(monkeypatch, "tennis_pro")
    r.stream([_uo("X1", side="L", sm=5.0, rfo=rfo, rfs=rfs)])
    assert r.sorv.intervento is None
    assert r.sorv.conti[OE.BOT] == 1


def test_live_ordine_dell_utente_su_un_altro_mercato_nulla_cambia(monkeypatch):
    r = _Runner(monkeypatch, "tennis_pro")
    r.stream([_uo("U1", side="L", sm=3.0, rfo=None, rfs=None)], market_id=ALTRO)
    assert r.sorv.intervento is None
    assert not getattr(r.bot, "_tennis_disabled", False)
    assert r.concludi() == []


def test_live_lo_stream_del_client_paper_non_tocca_il_bot_live(monkeypatch):
    r = _Runner(monkeypatch, "tennis_pro")
    r.stream([_uo("U1", side="L", sm=3.0, rfo=None, rfs=None)], client=_client(paper=True))
    assert r.sorv.intervento is None


def test_live_senza_interruttore_identico_a_prima(monkeypatch):
    monkeypatch.setenv(OE.ENV, "0")
    r = _Runner(monkeypatch, "tennis_pro")
    assert r.session.ordini_esterni is None and r.sorv is None
    assert not getattr(r.fw, "_conto_osservato", False)
    # il gate del bot e' quello di sempre (scoping del runner), nessun involucro
    assert getattr(r.bot, "_ordini_esterni", None) is None


# ===========================================================================
# PAPER: gli ordini manuali SIMULATI del ladder (stesso processo)
# ===========================================================================
def _manuale_paper(r: _Runner, ref: str, *, sm: float, market_id: str = MID,
                   source: str = "manual", mode: str = "paper") -> Any:
    """Un ordine del ladder come lo traccia ``_track_manual``, BetfairOrder VERO
    sotto la capture, aggiornato da un ``CurrentOrder`` VERO."""
    from flumine import BaseStrategy
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    class _Cap(BaseStrategy):
        def check_market_book(self, market: Any, market_book: Any) -> bool:  # noqa: ARG002
            return False

    cap = _Cap(market_filter={}, name="_capture_%s" % ref, max_order_exposure=None,
               max_selection_exposure=None)
    trade = Trade(market_id=market_id, selection_id=SEL, handicap=0.0, strategy=cap)
    o = trade.create_order(side="LAY", order_type=LimitOrder(price=2.0, size=4.0))
    o.bet_id = "P-" + ref
    r.session.tracked_orders[ref] = {"order": o, "trade": trade, "mode": mode,
                                     "event_id": EV, "source": source, "gen": 0}
    _aggiorna(o, sm, market_id)
    return o


def _aggiorna(o: Any, sm: float, market_id: str = MID) -> None:
    co = _current_orders([{"id": o.bet_id, "p": 2.0, "s": 4.0, "side": "L",
                           "status": "E" if sm < 4.0 else "EC", "pt": "L", "ot": "L",
                           "pd": _ora(), "md": _ora(), "avp": 2.0 if sm > 0 else None,
                           "sm": sm, "sr": 4.0 - sm, "sl": 0.0, "sc": 0.0, "sv": 0.0,
                           "rfo": None, "rfs": None}], market_id)
    o.update_current_order(co.orders[0])


@pytest.mark.parametrize("bot", BOTS)
def test_paper_ordine_manuale_simulato_ferma_il_bot_in_prova(monkeypatch, bot):
    r = _Runner(monkeypatch, bot, runner="PAPER", mode="paper")
    assert r.sorv is not None and r.sorv.modo == "paper"
    o = _manuale_paper(r, "awtq11", sm=0.0)
    assert r.sorv.controlla() is None, "non ancora abbinato"
    assert not getattr(r.bot, "_tennis_disabled", False)
    _aggiorna(o, 2.0)
    assert r.sorv.controlla() is not None
    ev = r.sorv.intervento
    assert ev["modo"] == "paper" and ev["fonte"] == OE.FONTE_PAPER and ev["dove"] == "app"
    assert getattr(r.bot, "_tennis_disabled", False) is True
    assert r.concludi() == [(EV, bot)]


def test_paper_ordine_abbinato_e_tolto_dal_tracking_resta_un_intervento(monkeypatch):
    r = _Runner(monkeypatch, "tennis_pro", runner="PAPER", mode="paper")
    o = _manuale_paper(r, "awtq12", sm=0.0)
    assert r.sorv.controlla() is None
    _aggiorna(o, 4.0)
    r.session.tracked_orders.pop("awtq12")     # il worker toglie i terminali
    assert r.sorv.controlla() is not None


def test_paper_ordini_dei_comandi_dei_bot_e_della_modalita_live_non_contano(monkeypatch):
    r = _Runner(monkeypatch, "tennis_pro", runner="PAPER", mode="paper")
    _manuale_paper(r, "safe1", sm=4.0, source="safe_tennis")
    _manuale_paper(r, "live1", sm=4.0, mode="live")
    _manuale_paper(r, "altro", sm=4.0, market_id=ALTRO)
    assert r.sorv.controlla() is None


def test_paper_ordine_di_safe_tennis_dalla_coda_non_e_un_intervento(monkeypatch):
    """In prova la regola di W2 vale in-process: la riga di coda dice Safe."""
    r = _Runner(monkeypatch, "tennis_pro", runner="PAPER", mode="paper")
    _manuale_paper(r, "awtq21", sm=4.0)
    r.session.tracked_orders["awtq21"]["coda"] = {"client_ref": "safe_tennis-t8",
                                                  "params": {"source": "safe_tennis"}}
    assert r.sorv.controlla() is None
    r.session.tracked_orders.pop("awtq21")   # terminale tolto dal worker: resta di Safe
    assert r.sorv.controlla() is None
    _manuale_paper(r, "awtq22", sm=2.0)      # e un ordine VERO del ladder si'
    assert r.sorv.controlla() is not None


def test_bot_paper_in_runner_live_legge_solo_il_paper(monkeypatch):
    """Paper e live mai mescolati: un ordine del sito sullo stream reale non
    ferma il bot in prova; un ordine manuale simulato si'."""
    r = _Runner(monkeypatch, "tennis_pro", runner="LIVE", mode="paper")
    assert r.sorv is not None and r.sorv.modo == "paper"
    r.stream([_uo("U1", side="L", sm=3.0, rfo=None, rfs=None)])
    assert r.sorv.intervento is None
    _manuale_paper(r, "awtq13", sm=2.0)
    assert r.sorv.controlla() is not None


def test_bot_live_non_legge_gli_ordini_manuali_simulati(monkeypatch):
    r = _Runner(monkeypatch, "tennis_pro")
    _manuale_paper(r, "awtq14", sm=4.0)
    assert r.sorv.controlla() is None


def test_bot_in_dry_run_nessuna_sorveglianza(monkeypatch):
    """Bot paper in runner LIVE senza client simulato: dry-run forzato (nessun
    ordine possibile), niente da proteggere, nessun involucro."""
    from flumine import Flumine

    s = TR.TennisLiveSession(None)
    s.order_mode = "LIVE"
    fw = Flumine(client=_client(paper=False))
    s.ordini_esterni = OET.registro_per_framework(fw, "LIVE")
    bot = _arma("tennis_pro", "paper", "LIVE", client_paper=None)
    assert bot.dry_run is True
    assert OET.proteggi_bot(s, fw, EV, "tennis_pro", bot,
                            disabilita=TR._disable_strategy) is None


def test_contratto_runner_monta_registro_e_protezione():
    """Il runner chiama i tre punti: registro alla build, protezione a ogni bot
    ospitato (build e armamento a caldo), conclusione nel bot_control_worker
    PRIMA dell'heartbeat."""
    import inspect

    src_build = inspect.getsource(TR.setup_and_run)
    assert ("session.ordini_esterni = _OET.registro_per_framework(framework, mode, session)"
            in src_build)
    assert src_build.count("_OET.proteggi_bot(") == 1
    assert "_OET.proteggi_bot(" in inspect.getsource(TR._arma_a_caldo)
    src_w = inspect.getsource(TR.bot_control_worker)
    assert src_w.index("_OET.concludi_interventi(") < src_w.index("heartbeat=True")
