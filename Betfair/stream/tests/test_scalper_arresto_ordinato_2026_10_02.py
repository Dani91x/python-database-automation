"""SCALPER: ARRESTO ORDINATO (02/10/2026) - punto 26 dell'elenco dell'utente.

Difetto: all'arresto (eccezione nel ciclo, Ctrl+C/segnale) la sessione usciva
con ``sys.exit`` senza togliere gli ordini vivi; anche lo stop dall'app e il
freno, dopo 30 s di force-flat non riuscito, spegnevano flumine lasciando gli
ordini rimasti sull'exchange. Ora prima di uscire: annullo degli ordini NON
abbinati (tempo massimo), posizioni abbinate solo dichiarate (diario + CRITICAL
"posizione lasciata a mercato per arresto", mai chiuse di iniziativa), poi
l'uscita. Paper e live: stesso codice (annullo via flumine); il ripiego REST
per bet_id solo in live, mai market-wide.

Finti con i campi veri di flumine: ``order.status`` e' l'Enum ``OrderStatus``
vero, ``size_matched``, ``average_price_matched``, ``side`` 'BACK'/'LAY',
``bet_id``, ``market_id``, ``selection_id``; il client REST risponde come
betfairlightweight (``list_current_orders(...).orders[].bet_id``). ASCII-only.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from flumine.order.order import OrderStatus

from Betfair.stream.scalper import scalper_session as SS


# ================================================================ finti
class _Order:
    def __init__(self, bet_id, status, market_id="1.10", side="BACK", matched=0.0, price=2.0,
                 selection_id=11):
        self.bet_id = bet_id
        self.status = status
        self.market_id = market_id
        self.selection_id = selection_id
        self.side = side
        self.size_matched = matched
        self.average_price_matched = price if matched else 0.0


class _Market:
    """``Market`` di flumine: ``blotter`` iterabile e ``cancel_order(order)``.
    ``efficace`` = il simulatore/exchange esegue davvero l'annullo."""

    def __init__(self, market_id, ordini, efficace=True):
        self.market_id = market_id
        self.blotter = list(ordini)
        self.efficace = efficace
        self.annullati: list = []

    def cancel_order(self, order, size_reduction=None, force=False):
        self.annullati.append(order.bet_id)
        if self.efficace:
            order.status = OrderStatus.EXECUTION_COMPLETE
        return True


def _framework(*mercati):
    return SimpleNamespace(markets=list(mercati))


class _Betting:
    def __init__(self, sul_conto):
        self.sul_conto = list(sul_conto)
        self.annullati: list = []
        self.market_wide: list = []

    def list_current_orders(self, market_ids=None):
        return SimpleNamespace(orders=[SimpleNamespace(bet_id=b) for b in self.sul_conto])

    def cancel_orders(self, market_id=None, instructions=None):
        if instructions is None:
            self.market_wide.append(market_id)
        else:
            self.annullati.extend(i["betId"] for i in instructions)


class _Tab:
    def __init__(self, db):
        self.db = db

    def insert(self, riga):
        self.db.avvisi.append(riga)
        return self

    def execute(self):
        return SimpleNamespace(data=[])


class _Db:
    def __init__(self):
        self.log_righe: list = []
        self.avvisi: list = []
        self.sb = SimpleNamespace(table=lambda nome: _Tab(self))

    def log(self, ev, kind, payload):
        self.log_righe.append((ev, kind, payload))


class _Orologio:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def dormi(self, s):
        self.t += s


def _mercato_tipico(efficace=True):
    return _Market("1.10", [
        _Order("B1", OrderStatus.EXECUTABLE),
        _Order("B2", OrderStatus.PENDING),
        _Order("B3", OrderStatus.EXECUTION_COMPLETE, matched=4.0, side="BACK", price=2.0),
    ], efficace=efficace)


# ================================================================ annullo
@pytest.mark.parametrize("paper", [True, False])
def test_arresto_annulla_gli_ordini_vivi_via_flumine_paper_e_live(paper):
    m = _mercato_tipico()
    betting = _Betting(["B1", "B2"])
    esito = SS.annulla_ordini_vivi_all_arresto(
        _framework(m), SimpleNamespace(betting=betting), paper, flumine_vivo=True)
    assert m.annullati == ["B1", "B2"]                  # mai l'ordine abbinato
    assert esito["vivi_prima"] == 2 and esito["vivi_dopo"] == 0
    assert esito["rest"] is None and betting.annullati == []


def test_arresto_live_flumine_morto_ripiego_rest_mirato_mai_market_wide():
    m = _mercato_tipico()
    betting = _Betting(["B1", "B2", "ALTRO_PROCESSO"])
    esito = SS.annulla_ordini_vivi_all_arresto(
        _framework(m), SimpleNamespace(betting=betting), False, flumine_vivo=False)
    assert m.annullati == []
    assert sorted(betting.annullati) == ["B1", "B2"]
    assert betting.market_wide == []
    assert esito["rest"]["ok"] == ["1.10"]


def test_arresto_paper_flumine_morto_nessun_rest_sul_conto_vero():
    m = _mercato_tipico()
    betting = _Betting(["B1", "B2"])
    esito = SS.annulla_ordini_vivi_all_arresto(
        _framework(m), SimpleNamespace(betting=betting), True, flumine_vivo=False)
    assert betting.annullati == [] and betting.market_wide == []
    assert esito["vivi_dopo"] == 2


def test_arresto_annullo_con_tempo_massimo_poi_ripiego_live():
    m = _mercato_tipico(efficace=False)                 # l'annullo non arriva
    betting = _Betting(["B1", "B2"])
    oro = _Orologio()
    esito = SS.annulla_ordini_vivi_all_arresto(
        _framework(m), SimpleNamespace(betting=betting), False, flumine_vivo=True,
        timeout_s=3.0, ora=oro, dormi=oro.dormi)
    assert 3.0 <= oro.t <= 3.5                          # mai oltre il tempo massimo
    assert sorted(betting.annullati) == ["B1", "B2"]


def test_arresto_senza_ordini_vivi_nessuna_chiamata():
    m = _Market("1.10", [_Order("B3", OrderStatus.EXECUTION_COMPLETE)])
    betting = _Betting([])
    esito = SS.annulla_ordini_vivi_all_arresto(
        _framework(m), SimpleNamespace(betting=betting), False, flumine_vivo=True)
    assert m.annullati == [] and betting.annullati == []
    assert esito["vivi_dopo"] == 0


# ================================================================ diario + CRITICAL
@pytest.mark.parametrize("causa", sorted(SS.CAUSE_ARRESTO))
def test_posizione_abbinata_lasciata_a_mercato_critical_mai_chiusa(causa):
    m = _mercato_tipico()
    db = _Db()
    SS.chiudi_all_arresto(db, "E1", _framework(m), None, True, causa, flumine_vivo=True)
    assert len(db.avvisi) == 1
    a = db.avvisi[0]
    assert a["level"] == "CRITICAL" and a["code"] == SS.CODICE_ARRESTO
    assert "posizione lasciata a mercato per arresto" in a["message"]
    assert a["event_id"] == "E1"
    # la posizione NON si chiude: nessun ordine nuovo, solo gli annulli dei vivi
    assert m.annullati == ["B1", "B2"]
    assert db.log_righe and db.log_righe[0][1] == "error"


def test_arresto_piatto_senza_ordini_nessun_critical():
    m = _Market("1.10", [_Order("B1", OrderStatus.EXECUTABLE)])
    db = _Db()
    SS.chiudi_all_arresto(db, "E1", _framework(m), None, False, "stop_app", flumine_vivo=True)
    assert db.avvisi == []
    assert db.log_righe[0][1] == "info"


def test_ordini_rimasti_vivi_in_paper_critical():
    m = _Market("1.10", [_Order("B1", OrderStatus.EXECUTABLE)], efficace=False)
    db = _Db()
    oro = _Orologio()
    SS.chiudi_all_arresto(db, "E1", _framework(m), None, True, "errore_fatale",
                          flumine_vivo=True, timeout_s=1.0, ora=oro, dormi=oro.dormi)
    assert len(db.avvisi) == 1 and "ordini ancora vivi" in db.avvisi[0]["message"]


def test_chiudi_all_arresto_non_solleva_mai():
    class _DbRotto(_Db):
        def log(self, *a, **k):
            raise RuntimeError("rete")
    SS.chiudi_all_arresto(_DbRotto(), "E1", object(), None, True, "segnale", flumine_vivo=False)


# ================================================================ cablaggio
def test_l_eccezione_del_ciclo_passa_dall_uscita_ordinata():
    """La via 1625-1631 (except esterno) prende anche KeyboardInterrupt/segnali
    (prima: nessun handler) e passa da ``_uscita_su_eccezione``."""
    src = inspect.getsource(SS.run_session)
    coda = src[src.rindex("except (Exception, KeyboardInterrupt) as exc"):]
    assert "_uscita_su_eccezione(db, ev, exc, framework, trading, session_paper, runner, flush)" in coda
    assert "sys.exit" not in coda


class _DbSessione(_Db):
    def __init__(self):
        super().__init__()
        self.ordine: list = []

    def set_control(self, ev, **campi):
        self.ordine.append(("set_control", campi.get("status")))

    def log(self, ev, kind, payload):
        super().log(ev, kind, payload)
        self.ordine.append(("log", payload.get("msg", "")[:40]))


@pytest.mark.parametrize("exc,causa", [(RuntimeError("boom"), "errore_fatale"),
                                       (KeyboardInterrupt("segnale 15"), "segnale")])
def test_uscita_su_eccezione_annulla_prima_dello_stato_e_di_sys_exit(exc, causa):
    m = _mercato_tipico()
    db = _DbSessione()
    runner = SimpleNamespace(is_alive=lambda: True)
    with pytest.raises(SystemExit) as fine:
        SS._uscita_su_eccezione(db, "E1", exc, _framework(m), None, True, runner, lambda: None)
    assert fine.value.code == 1
    assert m.annullati == ["B1", "B2"]                       # ordini vivi annullati
    assert db.ordine[0][0] == "log" and db.ordine[0][1].startswith("arresto")
    assert ("set_control", "error") in db.ordine
    assert db.ordine.index(("set_control", "error")) > 0     # lo stato DOPO l'annullo
    assert f"[{causa}]" in db.avvisi[0]["message"]          # CRITICAL della posizione


def test_uscita_su_eccezione_senza_framework_nessun_annullo():
    db = _DbSessione()
    with pytest.raises(SystemExit):
        SS._uscita_su_eccezione(db, "E1", RuntimeError("prima di flumine"), None, None, True,
                                None, lambda: None)
    assert db.avvisi == [] and db.ordine[0] == ("set_control", "error")


def test_stop_dall_app_e_freno_passano_dall_arresto_prima_di_spegnere_flumine():
    src = inspect.getsource(SS.run_session)
    assert "causa_arresto = (\"freno\"" in src
    i_chiudi = src.index("elif causa_arresto in CAUSE_ARRESTO:")
    assert i_chiudi < src.index("framework.handler_queue.put(TerminationEvent(framework))")


def test_segnale_di_arresto_diventa_keyboardinterrupt():
    with pytest.raises(KeyboardInterrupt):
        SS._al_segnale(15, None)
    import signal
    nomi = [n for n in ("SIGTERM", "SIGBREAK") if hasattr(signal, n)]
    vecchi = {n: signal.getsignal(getattr(signal, n)) for n in nomi}
    try:
        fatti = SS.installa_segnali_di_arresto()
        assert int(signal.SIGTERM) in fatti
        assert signal.getsignal(signal.SIGTERM) is SS._al_segnale
    finally:
        for n, h in vecchi.items():
            signal.signal(getattr(signal, n), h)


# ================================================================ R2: supervisore
class _SessioneFinta:
    """``Popen`` finto di una sessione: esce da sola al secondo ``esce_a_s``
    (tempo del supervisore) oppure, se ``esce_al_segnale``, appena riceve il
    segnale di arresto. Registra segnale e terminate con l'istante."""

    def __init__(self, orologio, esce_a_s=None, esce_al_segnale=False):
        self.orologio = orologio
        self.esce_a_s = esce_a_s
        self.esce_al_segnale = esce_al_segnale
        self.segnale_a = None
        self.terminata_a = None

    def poll(self):
        t = self.orologio["t"]
        if self.esce_a_s is not None and t >= self.esce_a_s:
            return 0
        if self.esce_al_segnale and self.segnale_a is not None:
            return 1
        return None

    def send_signal(self, sig):
        self.segnale_a = self.orologio["t"]

    def terminate(self):
        self.terminata_a = self.orologio["t"]


def _attendi(children, orologio):
    from Betfair.stream.scalper import scalper_service as SV

    SV.attendi_e_termina_flat(children, now=lambda: orologio["t"],
                              sleep=lambda s: orologio.__setitem__("t", orologio["t"] + s))


def test_supervisore_non_termina_una_sessione_che_impiega_95_s():
    orologio = {"t": 0.0}
    lenta = _SessioneFinta(orologio, esce_a_s=95.0)
    children = {"E1": lenta}
    _attendi(children, orologio)
    assert lenta.terminata_a is None and lenta.segnale_a is None
    assert children == {}


def test_supervisore_che_non_risponde_segnale_poi_terminate_dopo_il_tetto():
    from Betfair.stream.scalper import scalper_service as SV

    orologio = {"t": 0.0}
    muta = _SessioneFinta(orologio)
    _attendi({"E1": muta}, orologio)
    assert muta.segnale_a >= SS.TEMPO_MASSIMO_ARRESTO_S                  # mai prima del tetto
    assert muta.terminata_a >= muta.segnale_a + SV._attesa_dopo_segnale_s()
    assert muta.terminata_a <= SV.tempo_supervisore_arresto_s() + 4.0


def test_supervisore_sessione_che_esce_al_segnale_non_viene_terminata():
    orologio = {"t": 0.0}
    s = _SessioneFinta(orologio, esce_al_segnale=True)
    children = {"E1": s}
    _attendi(children, orologio)
    assert s.segnale_a is not None and s.terminata_a is None and children == {}


def test_tetto_della_sessione_dalle_sue_costanti():
    """Il tetto copre battito + flat di OGNI strategia + annullo; ogni
    ``_all_flat(timeout_s=X)`` di run_session usa X == FLAT_ATTESA_S e
    ``_all_flat`` aspetta il maker piu' le strategie di ``(sniper, theta)``."""
    import re

    assert SS.TEMPO_MASSIMO_ARRESTO_S >= (SS.HEARTBEAT_S + SS.STRATEGIE_MAX * SS.FLAT_ATTESA_S
                                          + SS.ARRESTO_ANNULLO_TIMEOUT_S)
    src = inspect.getsource(SS.run_session)
    attese = [float(x) for x in re.findall(r"_all_flat\(timeout_s=([0-9.]+)\)", src)]
    assert attese and all(a == SS.FLAT_ATTESA_S for a in attese)
    assert "for extra in (sniper, theta):" in src and SS.STRATEGIE_MAX == 1 + 2


def test_main_js_concede_allo_scalper_almeno_il_tempo_del_supervisore():
    import os
    import re

    from Betfair.stream.scalper import scalper_service as SV

    radice = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    with open(os.path.join(radice, "desktop", "main.js"), encoding="utf-8") as f:
        js = f.read()
    m = re.search(r"if \(label === 'scalper-service'\) return ([0-9_]+);", js)
    assert m, "shutdownGraceMs('scalper-service') non trovato in main.js"
    grazia_s = int(m.group(1).replace("_", "")) / 1000.0
    assert grazia_s >= SV.tempo_supervisore_arresto_s() + 10.0


def test_la_sessione_nasce_nel_suo_gruppo_di_processi(monkeypatch):
    import subprocess

    from Betfair.stream.scalper import scalper_service as SV

    visti = {}
    monkeypatch.setattr(SV.subprocess, "Popen", lambda *a, **kw: visti.update(kw) or "p")
    SV._spawn("E1")
    assert visti.get("creationflags") == getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


# ================================================================ R3: fine vita
def test_fine_vita_annulla_e_dichiara_partita_finita_no():
    src = inspect.getsource(SS.run_session)
    assert "causa_arresto = \"fine_vita\"" in src
    assert "causa_arresto = \"partita_finita\"" in src
    assert "fine_vita" in SS.CAUSE_ARRESTO
    assert "partita_finita" not in SS.CAUSE_ARRESTO      # mercato CLOSED: niente da annullare
    # il ramo fine vita imposta la causa DOPO il controllo dell'orario di vita
    i_vita = src.index("time.time() > ko_ts + _life_s")
    assert src.index("causa_arresto = \"fine_vita\"", i_vita) > i_vita


def test_fine_vita_posizione_lasciata_critical():
    m = _mercato_tipico()
    db = _Db()
    SS.chiudi_all_arresto(db, "E1", _framework(m), None, False, "fine_vita", flumine_vivo=True)
    assert m.annullati == ["B1", "B2"]
    assert db.avvisi and "[fine_vita]" in db.avvisi[0]["message"]


def test_partita_finita_mercato_closed_nessun_ordine_da_annullare():
    """A partita finita il mercato e' CLOSED (regolato): flumine lo marca
    ``closed`` e Betfair non tiene ordini vivi; ``partita_finita`` lo
    riconosce e la sessione esce senza annullo (``CAUSE_ARRESTO``)."""
    closed = SimpleNamespace(closed=True, market_book=SimpleNamespace(status="CLOSED"))
    fw = SimpleNamespace(markets=SimpleNamespace(markets={"1.MO": closed}))
    assert SS.partita_finita(fw, "1.MO", ["1.MO"]) is True
    assert "partita_finita" not in SS.CAUSE_ARRESTO
