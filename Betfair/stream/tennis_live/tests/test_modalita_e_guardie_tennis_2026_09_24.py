# -*- coding: utf-8 -*-
"""T1 e T2 del 24/09/2026 - modalita' del bot tennis e guardie del runner tennis.

T1: un bot acceso in PAPER con il runner in LIVE andava sul client REALE (il ponte
scriveva ``dry_run = mode == 'live'`` e la riga non portava la modalita').
T2: nel tennis mancavano kill-switch e guardia d'avvio (``Guardia("tennis")`` mai
armata, comandi del 47332 senza rifiuto a runner in ripresa).

I finti parlano come il vero:
  * il framework e' un ``Flumine`` VERO con client ``BetfairClient`` VERI (reale e
    paper affiancato) e ``Market`` VERO: il piazzamento passa per
    ``Market.place_order`` -> ``Transaction`` -> trading control -> order package.
    L'UNICA cosa sostituita e' ``process_order_package`` (il punto in cui flumine
    manderebbe il pacchetto all'esecuzione): qui si REGISTRA il pacchetto, con il
    suo client, e non parte niente verso Betfair;
  * il bot e' la classe VERA ``TennisFLBStrategy`` istanziata da
    ``tennis_runner._instantiate_bot``; solo il suo ``process_market_book`` e'
    sostituito da uno che fa quello che fanno i 4 bot quando decidono di entrare
    (gate su ``self.dry_run``, poi ``market.place_order(order)`` senza client);
  * canale: ``LocalChannel``/``LocalRequest`` VERI, ``respond`` registrato;
  * DB: finti con le firme e le chiavi di ``tennis_db``.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import types
from typing import Any, Dict, List, Optional

import betfairlightweight
import pytest
from betfairlightweight.filters import streaming_market_data_filter
from flumine import Flumine
from flumine import config as flumine_config
from flumine.markets.market import Market
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade

from Betfair.stream import avvio_app as AA
from Betfair.stream import live_order_worker as LOW
from Betfair.stream import local_channel as LC
from Betfair.stream.tennis_live import guardie_tennis as GT
from Betfair.stream.tennis_live import tennis_bot_service as S
from Betfair.stream.tennis_live import tennis_db as TDB
from Betfair.stream.tennis_live import tennis_live_order_worker as W
from Betfair.stream.tennis_live import tennis_runner as TR
from Betfair.stream.tennis_scalper.tennis_flb_bot import TennisFLBStrategy

MID = "1.100"
EV = "35794049"
SEL = 47972


# ===========================================================================
# impalcatura
# ===========================================================================
@pytest.fixture(autouse=True)
def _stato_pulito(monkeypatch):
    """Stato di processo a nuovo e kill-switch SPENTO di serie (niente .env)."""
    GT.azzera_per_i_test()
    monkeypatch.setattr(flumine_config, "place_latency", flumine_config.place_latency)
    monkeypatch.setattr(LOW, "_kill_switch", lambda: False)
    monkeypatch.setattr(LOW, "_db_kill_switch", lambda: False)
    monkeypatch.setattr(W, "_LOCAL_SEEN", {})
    yield
    GT.azzera_per_i_test()


def _book() -> Any:
    return types.SimpleNamespace(
        market_id=MID, publish_time=1_700_000_000_000, bet_delay=0, version=1,
        status="OPEN", inplay=True, runners=[], number_of_active_runners=2,
        number_of_winners=1,
        market_definition=types.SimpleNamespace(event_id=EV, event_type_id="2",
                                                market_type="MATCH_ODDS",
                                                country_code="IT", venue=None,
                                                race_type=None, market_time=None),
    )


def _quadro(runner_mode: str, con_paper: bool = True) -> Dict[str, Any]:
    """Il framework come lo costruisce ``tennis_runner.setup_and_run``: client
    della modalita' di processo, in LIVE il paper affiancato, i due trading
    control T1/T2. ``process_order_package`` registra invece di eseguire."""
    api = betfairlightweight.APIClient("utente", "pwd", app_key="chiave")
    client, _abilitati = TR.build_order_client(api, runner_mode)
    fw = Flumine(client=client)
    paper = None
    if runner_mode == "LIVE" and con_paper:
        paper = GT.build_client_paper_affiancato(api)
        fw.add_client(paper)
    fw.add_trading_control(GT.ControlloModalitaBotTennis)
    fw.add_trading_control(GT.ControlloKillSwitchTennis)
    pacchi: List[Any] = []
    fw.process_order_package = lambda pacchetto: pacchi.append(pacchetto)
    mercato = Market(fw, MID, _book())
    fw.markets.add_market(MID, mercato)
    return {"fw": fw, "client": client, "paper": paper, "mercato": mercato,
            "pacchi": pacchi}


def _entra(self: Any, market: Any, market_book: Any) -> None:
    """Quello che fanno i 4 bot quando entrano: gate su ``dry_run``, poi
    ``market.place_order(order)`` SENZA client (tennis_flb_bot.py:190)."""
    if self.dry_run:
        self._esito_place = None
        return
    trade = Trade(market_id=market.market_id, selection_id=SEL, handicap=0.0,
                  strategy=self)
    ordine = trade.create_order(side="BACK",
                                order_type=LimitOrder(price=2.0, size=2.0))
    self._ordine = ordine
    self._esito_place = market.place_order(ordine)


@pytest.fixture
def bot_che_entra(monkeypatch):
    monkeypatch.setattr(TennisFLBStrategy, "process_market_book", _entra)


def _arma(control: Dict[str, Any], runner_mode: str, paper: Any = None) -> Any:
    df = streaming_market_data_filter(fields=["EX_BEST_OFFERS"], ladder_levels=3)
    base = {"event_id": EV, "bot_key": "tennis_flb", "status": "running",
            "stake": 2, "params": {}, "stats": None}
    base.update(control)
    return TR._instantiate_bot("tennis_flb", base, MID, {}, lambda *a, **k: None,
                               df, runner_mode, market_ids=[MID], client_paper=paper)


def _gira(q: Dict[str, Any], bot: Any) -> None:
    bot.process_market_book(q["mercato"], q["mercato"].market_book)


# ===========================================================================
# (a) bot PAPER + runner LIVE -> nessun ordine reale, client paper, attivita'
# ===========================================================================
def test_a_bot_paper_su_runner_live_va_sul_client_simulato(bot_che_entra, monkeypatch):
    q = _quadro("LIVE")
    bot = _arma({"mode": "paper", "dry_run": False}, "LIVE", paper=q["paper"])
    assert bot._tennis_modalita_esecuzione == "PAPER"
    _gira(q, bot)
    assert bot._esito_place is True
    assert len(q["pacchi"]) == 1
    pacchetto = q["pacchi"][0]
    assert pacchetto.client is q["paper"]
    assert pacchetto.client.paper_trade is True
    assert all(p.client is not q["client"] for p in q["pacchi"])
    assert q["client"].paper_trade is False          # il reale c'e', ma non e' usato
    # la riga di attivita' lo DICE
    scritte: List[tuple] = []
    monkeypatch.setattr(TDB, "write_tennis_bot_activity",
                        lambda ev, bk, kind, payload: scritte.append((ev, bk, kind, payload)))
    TR._scrivi_attivita_modalita(EV, "tennis_flb", bot, "LIVE")
    assert len(scritte) == 1
    ev, bk, kind, payload = scritte[0]
    assert (ev, bk, kind) == (EV, "tennis_flb", "modalita")
    assert payload["modalita_bot"] == "paper"
    assert payload["runner"] == "LIVE"
    assert payload["esecuzione"] == "simulata"
    assert "simulato" in payload["client"]


def test_a_bot_paper_senza_client_paper_nasce_in_dry_run(bot_che_entra):
    """Fail-closed: runner LIVE senza client simulato a disposizione -> il bot
    paper non piazza NULLA (mai un ordine 'paper' sul client reale)."""
    q = _quadro("LIVE", con_paper=False)
    bot = _arma({"mode": "paper", "dry_run": False}, "LIVE", paper=None)
    assert bot.dry_run is True
    _gira(q, bot)
    assert q["pacchi"] == []
    assert TR.descrivi_esecuzione_bot(bot, "LIVE")["esecuzione"] == "nessun ordine (dry-run)"


def test_a_seconda_rete_bot_paper_sul_client_reale_rifiutato(bot_che_entra):
    """Se l'instradamento mancasse (bot paper che piazza sul client di default,
    cioe' il REALE), il trading control lo rifiuta DENTRO flumine."""
    q = _quadro("LIVE")
    bot = _arma({"mode": "paper", "dry_run": False}, "LIVE", paper=q["paper"])
    # si scavalca l'ombra per istanza e si chiama il metodo della classe
    TennisFLBStrategy.process_market_book(bot, q["mercato"], q["mercato"].market_book)
    assert bot._esito_place is False
    assert q["pacchi"] == []
    assert "TENNIS_MODALITA_BOT" in str(getattr(bot._ordine, "violation_msg", ""))


# ===========================================================================
# (b) bot LIVE + runner LIVE + dry_run esplicito False -> client reale
# ===========================================================================
def test_b_bot_live_con_dry_run_falso_esplicito_va_sul_reale(bot_che_entra):
    q = _quadro("LIVE")
    bot = _arma({"mode": "live", "dry_run": False}, "LIVE", paper=q["paper"])
    assert bot._tennis_modalita_esecuzione == "LIVE"
    assert bot.dry_run is False
    _gira(q, bot)
    assert len(q["pacchi"]) == 1
    assert q["pacchi"][0].client is q["client"]
    assert q["pacchi"][0].client.paper_trade is False
    assert TR.descrivi_esecuzione_bot(bot, "LIVE")["esecuzione"] == "reale"


@pytest.mark.parametrize("dry", ["assente", None, 0, "false", True])
def test_b_bot_live_senza_false_esplicito_resta_in_dry_run(bot_che_entra, dry):
    """Il reale e' un GESTO: solo il booleano False toglie il dry-run. Prima
    ``bool(None)`` era gia' "reale"."""
    q = _quadro("LIVE")
    control: Dict[str, Any] = {"mode": "live"}
    if dry != "assente":
        control["dry_run"] = dry
    bot = _arma(control, "LIVE", paper=q["paper"])
    assert bot.dry_run is True
    _gira(q, bot)
    assert q["pacchi"] == []


def test_b_bot_live_su_runner_paper_resta_simulato(bot_che_entra):
    """Il runner PAPER non ha un client reale: un bot dichiarato live esegue
    simulato (nessuna promozione possibile)."""
    q = _quadro("PAPER")
    bot = _arma({"mode": "live", "dry_run": False}, "PAPER")
    assert bot._tennis_modalita_esecuzione == "PAPER"
    _gira(q, bot)
    assert len(q["pacchi"]) == 1
    assert q["pacchi"][0].client.paper_trade is True


# ===========================================================================
# (c) riga senza mode -> simulato
# ===========================================================================
@pytest.mark.parametrize("mode", ["assente", None, "", "LIVE ", "boh", "Paper"])
def test_c_riga_senza_mode_valida_e_simulata(bot_che_entra, mode):
    q = _quadro("LIVE")
    control: Dict[str, Any] = {"dry_run": False}
    if mode != "assente":
        control["mode"] = mode
    bot = _arma(control, "LIVE", paper=q["paper"])
    atteso_live = str(mode or "").strip().lower() == "live"
    _gira(q, bot)
    assert len(q["pacchi"]) == 1
    if atteso_live:
        # 'LIVE ' con spazi e maiuscole e' una dichiarazione esplicita di live
        assert q["pacchi"][0].client is q["client"]
    else:
        assert q["pacchi"][0].client is q["paper"]


def test_c_modalita_esecuzione_tabella():
    tab = {
        ("OFF", None): "OFF", ("OFF", "live"): "OFF",
        ("PAPER", None): "PAPER", ("PAPER", "live"): "PAPER", ("PAPER", "paper"): "PAPER",
        ("LIVE", None): "PAPER", ("LIVE", "paper"): "PAPER", ("LIVE", "live"): "LIVE",
        ("boh", "live"): "OFF",
    }
    for (runner, mode), atteso in tab.items():
        assert GT.modalita_esecuzione_bot({"mode": mode}, runner) == atteso, (runner, mode)
    assert GT.modalita_esecuzione_bot(None, "LIVE") == "PAPER"


# ===========================================================================
# (d) kill-switch attivo -> passano solo le chiusure
# ===========================================================================
def test_d_kill_switch_ferma_l_apertura_di_un_bot(bot_che_entra, monkeypatch):
    monkeypatch.setattr(LOW, "_kill_switch", lambda: True)
    q = _quadro("LIVE")
    bot = _arma({"mode": "live", "dry_run": False}, "LIVE", paper=q["paper"])
    _gira(q, bot)
    assert bot._esito_place is False
    assert q["pacchi"] == []
    assert "TENNIS_KILL_SWITCH" in str(getattr(bot._ordine, "violation_msg", ""))


def test_d_kill_switch_dal_db_ferma_anche_il_paper(bot_che_entra, monkeypatch):
    """Stesso freno del calcio: il kill-switch vale per ogni riga, paper compreso."""
    monkeypatch.setattr(LOW, "_db_kill_switch", lambda: True)
    q = _quadro("LIVE")
    bot = _arma({"mode": "paper", "dry_run": False}, "LIVE", paper=q["paper"])
    _gira(q, bot)
    assert bot._esito_place is False
    assert q["pacchi"] == []


def test_d_kill_switch_lascia_passare_una_chiusura_dichiarata(monkeypatch):
    monkeypatch.setattr(LOW, "_kill_switch", lambda: True)
    q = _quadro("LIVE")
    bot = _arma({"mode": "live", "dry_run": False}, "LIVE", paper=q["paper"])
    trade = Trade(market_id=MID, selection_id=SEL, handicap=0.0, strategy=bot)
    ordine = trade.create_order(side="LAY", order_type=LimitOrder(price=2.0, size=2.0))
    ordine.context["reduces_liability"] = True
    assert q["mercato"].place_order(ordine) is True
    assert len(q["pacchi"]) == 1


class _BlotterFinto:
    """Parla come ``flumine.markets.blotter.Blotter.market_exposure``."""

    def __init__(self, prima: Optional[float], dopo: Optional[float]):
        self.prima, self.dopo = prima, dopo

    def market_exposure(self, strategy, market_book, exclusion=None, new_order=None):
        v = self.dopo if new_order is not None else self.prima
        if v is None:
            raise ValueError("esposizione non calcolabile")
        return v


def _fw_con_blotter(blotter: Any) -> Any:
    mercato = types.SimpleNamespace(blotter=blotter, market_book=_book())
    return types.SimpleNamespace(markets=types.SimpleNamespace(markets={MID: mercato}))


def _ordine_finto(context=None):
    return types.SimpleNamespace(market_id=MID, context=context or {},
                                 trade=types.SimpleNamespace(strategy=object()))


@pytest.mark.parametrize("prima,dopo,atteso", [
    (-10.0, -2.0, True),     # la copertura riduce la perdita worst-case
    (-10.0, -10.0, True),    # non la aumenta: passa
    (-10.0, -12.0, False),   # la aumenta: apertura
    (0.0, -2.0, False),      # posizione piatta: un nuovo ordine apre
    (None, -2.0, False),     # non calcolabile: fail-closed
    (-10.0, None, False),
])
def test_d_chiusura_si_riconosce_dalla_perdita_worst_case(prima, dopo, atteso):
    fw = _fw_con_blotter(_BlotterFinto(prima, dopo))
    assert GT.ordine_riduce_il_rischio(fw, _ordine_finto()) is atteso


def test_d_mercato_sconosciuto_non_e_una_chiusura():
    fw = types.SimpleNamespace(markets=types.SimpleNamespace(markets={}))
    assert GT.ordine_riduce_il_rischio(fw, _ordine_finto()) is False


class _DbCoda:
    """Le firme di ``tennis_db`` usate dal worker della coda desktop."""

    def __init__(self, righe):
        self.righe = list(righe)
        self.errori: List[tuple] = []
        self.fatte: List[tuple] = []
        self.letture = 0

    def list_pending_tennis_orders(self, limit=5):
        self.letture += 1
        out, self.righe = self.righe[:limit], self.righe[limit:]
        return out

    def claim_tennis_order(self, rid):
        return True

    def write_tennis_order_done(self, rid, result):
        self.fatte.append((rid, result))

    def write_tennis_order_error(self, rid, result):
        self.errori.append((rid, result))

    def get_tennis_client(self):
        return object()


def _riga_coda(rid, action, mode="live", **extra):
    payload = {"action": action, "mode": mode, "market_id": MID, "selection_id": SEL}
    payload.update(extra)
    return {"id": rid, "client_ref": f"ref-{rid}", "payload": payload,
            "status": "pending", "result": None, "error": None,
            "created_at": "2026-09-24T10:00:00+00:00", "processed_at": None}


@pytest.fixture
def worker_finto(monkeypatch):
    """Il worker della coda con DB e dispatch finti; canale VERO."""
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "LIVE")
    monkeypatch.setattr(GT, "aggiorna_impostazioni", lambda sb, forza=False: None)
    monkeypatch.setattr(W, "_last_db_queue_poll", 0.0)
    eseguiti: List[tuple] = []
    monkeypatch.setattr(W, "_dispatch",
                        lambda fl, sess, cmd, ref: eseguiti.append((cmd["action"], ref))
                        or {"ok": True, "action": cmd["action"], "mode": cmd["mode"]})
    monkeypatch.setattr(W, "_reconcile_tracked", lambda sess, fl: None)
    monkeypatch.setattr(W, "_mirror_order", lambda *a, **k: None)
    ch = LC.LocalChannel(59997, "tennis")
    risposte: List[tuple] = []
    monkeypatch.setattr(ch, "respond",
                        lambda req, ok, data=None, error=None:
                        risposte.append((req.msg_id, ok, error)))
    monkeypatch.setattr(LC, "get_channel", lambda: ch)
    return {"eseguiti": eseguiti, "ch": ch, "risposte": risposte}


def _richiesta(msg_id, action, mode="live", metodo="order", **extra):
    params = {"action": action, "mode": mode, "client_ref": f"loc-{msg_id}",
              "market_id": MID, "selection_id": SEL}
    params.update(extra)
    return LC.LocalRequest(ws=None, msg_id=msg_id, method=metodo, params=params)


def test_d_kill_switch_coda_desktop_solo_chiusure(worker_finto, monkeypatch):
    monkeypatch.setattr(LOW, "_kill_switch", lambda: True)
    db = _DbCoda([_riga_coda(1, "place", side="BACK", price=2.0, size=2.0),
                  _riga_coda(2, "cancel", bet_id="B-1"),
                  _riga_coda(3, "greenup"),
                  _riga_coda(4, "replace", bet_id="B-2", new_price=2.2)])
    monkeypatch.setattr(W, "tennis_db", db)
    W.tennis_live_order_worker({}, object(), types.SimpleNamespace())
    azioni = [a for a, _ in worker_finto["eseguiti"]]
    assert azioni == ["cancel", "greenup"]
    rifiutate = {rid: res["error"] for rid, res in db.errori}
    assert set(rifiutate) == {1, 4}
    assert all("kill-switch ATTIVO" in e for e in rifiutate.values())


def test_d_kill_switch_canale_locale_solo_chiusure(worker_finto, monkeypatch):
    monkeypatch.setattr(LOW, "_db_kill_switch", lambda: True)
    monkeypatch.setattr(W, "tennis_db", _DbCoda([]))
    ch = worker_finto["ch"]
    ch._requests.put_nowait(_richiesta(1, "place", side="BACK", price=2.0, size=2.0))
    ch._requests.put_nowait(_richiesta(2, "cancel", bet_id="B-1"))
    W.tennis_live_order_worker({}, object(), types.SimpleNamespace())
    per_id = {m: (ok, err) for m, ok, err in worker_finto["risposte"]}
    assert per_id[1][0] is False and "kill-switch ATTIVO" in per_id[1][1]
    assert per_id[2][0] is True
    assert [a for a, _ in worker_finto["eseguiti"]] == ["cancel"]


# ===========================================================================
# (e) guardia armata -> comandi 47332 rifiutati subito, nessun accumulo
# ===========================================================================
def test_e_guardia_armata_rifiuta_subito_e_non_accumula(worker_finto, monkeypatch):
    db = _DbCoda([_riga_coda(9, "place", side="BACK", price=2.0, size=2.0)])
    monkeypatch.setattr(W, "tennis_db", db)
    esito_ripresa = {"ok": False}

    def _ripresa(db=None):  # firma di ripresa_all_avvio
        if esito_ripresa["ok"]:
            GT.GUARDIA_RUNNER.fatto = True
        return esito_ripresa["ok"]
    monkeypatch.setattr(GT, "ripresa_all_avvio", _ripresa)
    GT.arma_guardia_runner()
    ch = worker_finto["ch"]
    for r in (_richiesta(1, "place", side="BACK", price=2.0, size=2.0),
              _richiesta(2, "cancel", bet_id="B-1"),
              _richiesta(3, "greenup"),
              _richiesta(4, "replace", bet_id="B-2", new_price=2.2),
              _richiesta(5, None, metodo="snapshot")):
        ch._requests.put_nowait(r)
    W.tennis_live_order_worker({}, object(), types.SimpleNamespace())
    assert ch._requests.qsize() == 0                         # niente resta in RAM
    per_id = {m: (ok, err) for m, ok, err in worker_finto["risposte"]}
    assert set(per_id) == {1, 2, 3, 4, 5}                   # tutti risposti SUBITO
    for mid in (1, 3, 4, 5):
        assert per_id[mid][0] is False
        assert per_id[mid][1] == GT.MOTIVO_GUARDIA_LOCALE
    assert per_id[2][0] is True                              # l'annullo passa
    assert worker_finto["eseguiti"] and worker_finto["eseguiti"][0][0] == "cancel"
    assert db.letture == 0                                   # la coda DB non si tocca
    # la ripresa riesce: al giro dopo NESSUN comando vecchio parte
    esito_ripresa["ok"] = True
    GT._RIPRESA_STATO["ultimo"] = -1e18
    prima = list(worker_finto["eseguiti"])
    monkeypatch.setattr(W, "_last_db_queue_poll", 0.0)
    W.tennis_live_order_worker({}, object(), types.SimpleNamespace())
    nuovi = worker_finto["eseguiti"][len(prima):]
    assert [a for a, _ in nuovi] == ["place"]               # solo la riga DB fresca
    assert db.letture == 1


class _DbRipresa:
    """Le firme di ``tennis_db`` che la ripresa del runner usa."""

    def __init__(self, righe=None, rompi: Optional[str] = None):
        self.righe = list(righe or [])
        self.rompi = rompi
        self.stati: List[tuple] = []

    def list_tennis_bot_controls(self, event_id=None, statuses=None):
        if self.rompi == "lettura":
            raise ConnectionError("Server disconnected")
        return [dict(r) for r in self.righe]

    def set_tennis_bot_status(self, event_id, bot_key, status, **kw):
        if self.rompi == "scrittura":
            raise ConnectionError("Server disconnected")
        self.stati.append((event_id, bot_key, status))

    def write_tennis_bot_activity(self, event_id, bot_key, kind, payload):
        pass

    def fail_stale_pending_tennis_orders(self, max_age_sec=120.0):
        if self.rompi == "coda":
            raise ConnectionError("Server disconnected")
        return 2

    def chiudi_specchio_paper_orfano(self):
        if self.rompi == "specchio":
            raise ConnectionError("Server disconnected")
        return (3, 1)


def _riga_bot_vecchia():
    return {"event_id": EV, "bot_key": "tennis_flb", "status": "running",
            "mode": "live", "dry_run": False, "stake": 2, "params": {},
            "stats": {"boot_id": "avvio-di-ieri"}}


@pytest.mark.parametrize("rompi", ["lettura", "scrittura", "coda", "specchio"])
def test_e_ripresa_del_runner_fallita_tiene_la_guardia(rompi, monkeypatch):
    monkeypatch.setenv("APP_BOOT_ID", "avvio-di-oggi")
    GT.arma_guardia_runner()
    assert GT.ripresa_all_avvio(_DbRipresa([_riga_bot_vecchia()], rompi=rompi)) is False
    assert GT.GUARDIA_RUNNER.blocca_aperture is True


def test_e_ripresa_del_runner_riuscita_disarma_e_ferma_i_bot_vecchi(monkeypatch):
    monkeypatch.setenv("APP_BOOT_ID", "avvio-di-oggi")
    GT.arma_guardia_runner()
    db = _DbRipresa([_riga_bot_vecchia()])
    assert GT.ripresa_all_avvio(db) is True
    assert GT.GUARDIA_RUNNER.blocca_aperture is False
    assert db.stati == [(EV, "tennis_flb", "stopped")]


def test_e_guardia_ferma_il_restart_per_armare_un_bot(monkeypatch):
    """A guardia armata un bot richiesto NON provoca il restart che lo armerebbe."""
    richieste: List[str] = []
    monkeypatch.setattr(TR, "_request_restart",
                        lambda fl, sess, motivo: richieste.append(motivo) or True)
    monkeypatch.setattr(TR, "_desired_controls",
                        lambda ev: {"tennis_flb": {"status": "requested"}})
    monkeypatch.setattr(TR, "_stopping_controls", lambda ev: {})
    monkeypatch.setattr(GT, "ripresa_all_avvio", lambda db=None: False)
    sess = types.SimpleNamespace(market_meta={EV: {"market_id": MID}}, hosted={},
                                 stopping_deadline={})
    GT.arma_guardia_runner()
    TR.bot_control_worker({}, object(), sess)
    assert richieste == []
    GT.azzera_per_i_test()                                   # guardia spenta
    TR.bot_control_worker({}, object(), sess)
    assert richieste == ["arm/disarm bot"]


# ===========================================================================
# (f) parita': bot paper + runner PAPER identico a oggi
# ===========================================================================
_CONTROLLI_PARITA = ({}, {"mode": "paper"}, {"mode": "live"}, {"mode": None})


@pytest.mark.parametrize("bot_key", sorted(TR._BOT_REGISTRY))
def test_f_runner_paper_ignora_la_modalita_della_riga(bot_key):
    """In un runner PAPER la riga non cambia NIENTE: stessi params, stesso
    dry_run, nessun instradamento (il solo client e' quello simulato)."""
    df = streaming_market_data_filter(fields=["EX_BEST_OFFERS"], ladder_levels=3)
    impronte = []
    for extra in _CONTROLLI_PARITA:
        control = {"stake": 2.0, "dry_run": False, "params": {}, **extra}
        bot = TR._instantiate_bot(bot_key, control, MID, {"A": 1, "B": 2},
                                  lambda *a, **k: None, df, "PAPER",
                                  market_ids=[MID])
        assert "process_market_book" not in vars(bot)          # nessuna ombra
        assert bot._tennis_modalita_esecuzione == "PAPER"
        impronte.append((bot.dry_run, getattr(bot, "size_step", None),
                         getattr(bot, "live_min_bet", None),
                         bot.max_selection_exposure, bot.max_order_exposure))
    assert len(set(impronte)) == 1
    assert impronte[0][0] is False                              # visibile sul ladder
    assert impronte[0][1] in (0.0, None) and impronte[0][2] in (0.0, None)


def test_f_un_giro_in_paper_usa_il_solo_client_simulato(bot_che_entra):
    q = _quadro("PAPER")
    bot = _arma({"dry_run": False}, "PAPER")
    _gira(q, bot)
    assert len(q["pacchi"]) == 1
    assert q["pacchi"][0].client is q["client"]
    assert q["client"].paper_trade is True


def test_f_specchio_scrive_la_modalita_del_bot():
    """Paper e live mai sommati: gli ordini di un bot paper in un runner LIVE
    vanno sotto 'paper'; la capture (desktop) resta alla modalita' di build."""
    sess = types.SimpleNamespace(order_mode="LIVE")
    bot_paper = types.SimpleNamespace(_tennis_modalita_esecuzione="PAPER")
    bot_live = types.SimpleNamespace(_tennis_modalita_esecuzione="LIVE")
    capture = types.SimpleNamespace()
    assert W._modo_strategia(bot_paper, sess) == "paper"
    assert W._modo_strategia(bot_live, sess) == "live"
    assert W._modo_strategia(capture, sess) == "live"


# ===========================================================================
# ponte: la modalita' viaggia esplicita, guardia del ponte
# ===========================================================================
class _DbPonte:
    """Parla come ``tennis_db`` per il ponte (stesse firme e chiavi)."""

    def __init__(self, servizi, controls=None, scrittura_servizio_ok=True):
        self._servizi = servizi
        self._controls = list(controls or [])
        self.armati: List[Dict[str, Any]] = []
        self.stati: List[tuple] = []
        self.servizio_scritto: List[Dict[str, Any]] = []
        self.ok = scrittura_servizio_ok
        self._servizio_assente_detto = False

    def list_tennis_bot_services(self):
        return self._servizi

    def list_tennis_bot_controls(self, event_id=None, statuses=None):
        return [dict(r) for r in self._controls]

    def upsert_tennis_bot_control(self, row):
        self.armati.append(dict(row))

    def set_tennis_bot_status(self, event_id, bot_key, status, **kw):
        self.stati.append((event_id, bot_key, status))

    def write_tennis_bot_activity(self, event_id, bot_key, kind, payload):
        pass

    def set_tennis_bot_service_state(self, bot_key, **kw):
        self.servizio_scritto.append({"bot_key": bot_key, **kw})
        return self.ok


def _interruttore(mode="paper", status="running", stats=None):
    return {"bot_key": "tennis_flb", "status": status, "mode": mode, "stake": 3,
            "params": {}, "stats": stats, "error": None, "started_at": None,
            "stopped_at": None, "heartbeat_at": None, "updated_at": None}


@pytest.fixture
def ponte(monkeypatch):
    g = AA.Guardia("tennis")
    monkeypatch.setattr(S, "_GUARDIA_AVVIO", g)
    monkeypatch.setattr(S, "_followed_event_ids", lambda: {EV})
    return g


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_ponte_scrive_la_modalita_esplicita(ponte, mode):
    db = _DbPonte([_interruttore(mode=mode)])
    S.riconcilia_interruttori(db)
    assert db.armati[0]["mode"] == mode
    assert db.armati[0]["dry_run"] is (mode == "live")


def test_ponte_a_guardia_armata_non_arma(ponte):
    ponte.attiva = True
    db = _DbPonte([_interruttore(mode="live")])
    esito = S.riconcilia_interruttori(db)
    assert db.armati == []
    assert esito["armati"] == 0
    assert "guardia d'avvio" in db.servizio_scritto[0]["stats"]["motivo_blocco"]


def test_ponte_a_guardia_armata_ferma_comunque(ponte):
    ponte.attiva = True
    db = _DbPonte([_interruttore(status="stopped")],
                  controls=[{"event_id": EV, "bot_key": "tennis_flb", "status": "running"}])
    S.riconcilia_interruttori(db)
    assert db.stati == [(EV, "tennis_flb", "stopping")]


def test_ripresa_ponte_ferma_anche_gli_interruttori(ponte, monkeypatch):
    monkeypatch.setenv("APP_BOOT_ID", "avvio-di-oggi")
    S.arma_guardia_ponte()
    db = _DbPonte([_interruttore(mode="live", stats={"boot_id": "ieri"})])
    assert S.ripresa_ponte(db) is True
    assert ponte.blocca_aperture is False
    assert db.servizio_scritto[0]["status"] == "stopped"


def test_ripresa_ponte_con_interruttore_non_scritto_resta_armata(ponte, monkeypatch):
    monkeypatch.setenv("APP_BOOT_ID", "avvio-di-oggi")
    S.arma_guardia_ponte()
    db = _DbPonte([_interruttore(stats={"boot_id": "ieri"})], scrittura_servizio_ok=False)
    assert S.ripresa_ponte(db) is False
    assert ponte.blocca_aperture is True


def test_ripresa_ponte_db_muto_resta_armata_tabella_assente_no(ponte, monkeypatch):
    monkeypatch.setenv("APP_BOOT_ID", "avvio-di-oggi")
    S.arma_guardia_ponte()
    db = _DbPonte(None)
    assert S.ripresa_ponte(db) is False                   # DB muto: non verificato
    db._servizio_assente_detto = True                     # migrazione non applicata
    assert S.ripresa_ponte(db) is True


def test_fermo_d_avvio_con_una_scrittura_fallita_non_e_fatto(ponte, monkeypatch):
    monkeypatch.setenv("APP_BOOT_ID", "avvio-di-oggi")
    S.arma_guardia_ponte()
    S.ferma_bot_al_nuovo_avvio(db=_DbRipresa([_riga_bot_vecchia()], rompi="scrittura"))
    assert S.ESITO_ULTIMO_FERMO["riuscito"] is False
    assert ponte.blocca_aperture is True


# ===========================================================================
# tennis_db: la riga senza colonna `mode` (migrazione non applicata) = paper
# ===========================================================================
class _Esegui:
    def __init__(self, fn):
        self.execute = fn


class _SbFinto:
    """``sb.table(nome).upsert(payload, on_conflict=...).execute()``."""

    def __init__(self, errore: Optional[str]):
        self.errore = errore
        self.scritte: List[Dict[str, Any]] = []

    def table(self, nome):
        sb = self

        class _T:
            def upsert(self, payload, on_conflict=None):
                def _run():
                    if sb.errore and "mode" in payload:
                        raise Exception(sb.errore)
                    sb.scritte.append(dict(payload))
                    return types.SimpleNamespace(data=[dict(payload)])
                return _Esegui(_run)
        return _T()


def test_db_senza_colonna_mode_scrive_la_riga_senza_mode(monkeypatch):
    sb = _SbFinto("{'code': 'PGRST204', 'message': \"Could not find the 'mode' "
                  "column of 'tennis_bot_control' in the schema cache\"}")
    monkeypatch.setattr(TDB, "get_tennis_client", lambda: sb)
    TDB.upsert_tennis_bot_control({"event_id": EV, "bot_key": "tennis_flb",
                                   "status": "requested", "mode": "live",
                                   "dry_run": True, "stake": 2, "params": {}})
    assert len(sb.scritte) == 1 and "mode" not in sb.scritte[0]
    assert GT.modalita_riga(sb.scritte[0]) == "paper"


class _Query:
    """Costruttore PostgREST finto: registra update/eq/in_/lt come il vero."""

    def __init__(self, sb, tabella):
        self.sb, self.tabella = sb, tabella
        self.filtri: List[tuple] = []
        self.campi: Dict[str, Any] = {}

    def update(self, campi):
        self.campi = dict(campi)
        return self

    def eq(self, k, v):
        self.filtri.append(("eq", k, v))
        return self

    def in_(self, k, v):
        self.filtri.append(("in", k, tuple(v)))
        return self

    def lt(self, k, v):
        self.filtri.append(("lt", k, "<cutoff>"))
        return self

    def execute(self):
        self.sb.eseguite.append((self.tabella, self.campi, tuple(self.filtri)))
        return types.SimpleNamespace(data=[{"id": 1}])


class _SbRipresa:
    def __init__(self):
        self.eseguite: List[tuple] = []

    def table(self, nome):
        return _Query(self, nome)


def test_db_specchio_orfano_tocca_solo_il_paper(monkeypatch):
    sb = _SbRipresa()
    monkeypatch.setattr(TDB, "get_tennis_client", lambda: sb)
    assert TDB.chiudi_specchio_paper_orfano() == (1, 1)
    ordini, posizioni = sb.eseguite
    assert ordini[0] == "tennis_live_orders" and ordini[1]["status"] == "VOIDED"
    assert ("eq", "mode", "paper") in ordini[2]
    assert ("in", "status", ("PENDING", "CANCELLING", "UPDATING", "REPLACING",
                             "EXECUTABLE")) in ordini[2]
    assert posizioni[0] == "tennis_live_positions"
    assert ("eq", "mode", "paper") in posizioni[2]
    assert posizioni[1]["selection_exposure"] == 0.0


def test_db_richieste_stantie_in_error(monkeypatch):
    sb = _SbRipresa()
    monkeypatch.setattr(TDB, "get_tennis_client", lambda: sb)
    assert TDB.fail_stale_pending_tennis_orders(120.0) == 2
    stati = {f[2] for _, _, filtri in sb.eseguite for f in filtri if f[1] == "status"}
    assert stati == {"pending", "processing"}
    assert all(t == "tennis_live_order_queue" for t, _, _ in sb.eseguite)
    assert all(c["status"] == "error" for _, c, _ in sb.eseguite)
    assert all(("lt", "created_at", "<cutoff>") in filtri for _, _, filtri in sb.eseguite)


def test_mercato_con_client_sovrascrive_il_client_del_chiamante():
    """Un bot paper non puo' scegliersi il client reale nemmeno passandolo."""
    ricevuti: List[Any] = []
    mercato = types.SimpleNamespace(
        market_id=MID,
        place_order=lambda order, **kw: ricevuti.append(kw.get("client")) or True)
    vista = GT.MercatoConClient(mercato, "CLIENT_PAPER")
    assert vista.place_order(object(), client="CLIENT_REALE") is True
    assert vista.place_order(object()) is True
    assert ricevuti == ["CLIENT_PAPER", "CLIENT_PAPER"]
    assert vista.market_id == MID                     # il resto passa invariato


def test_db_altro_errore_non_si_maschera(monkeypatch):
    sb = _SbFinto("Server disconnected")
    monkeypatch.setattr(TDB, "get_tennis_client", lambda: sb)
    with pytest.raises(Exception):
        TDB.upsert_tennis_bot_control({"event_id": EV, "bot_key": "tennis_flb",
                                       "mode": "paper"})
    assert sb.scritte == []
