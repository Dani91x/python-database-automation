"""MOTORE ORDINI nel runner TENNIS + AGGANCIO A COMANDO (F8, 25/09).

Prima: ``SAFE_TENNIS_ORDINI_VIA_CANALE`` doveva restare spenta (il runner tennis
non montava il motore; una partita non seguita non entrava per un ordine di
Safe tennis). Qui si prova, con le classi VERE:

* il motore del calcio (``motore_ordini.MotoreOrdini``) con l'esecutore tennis
  esegue il ``_dispatch`` VERO di ``tennis_live_order_worker`` (capture della
  partita, client della modalita', ``_track_manual``), scrive il diario
  write-ahead con il customerOrderRef VERO, porta FOK e riduzione fino al
  ``LimitOrder``, rifiuta DICHIARANDOLO cio' che il runner tennis non fa;
* lo specchio del worker tennis diventa eventi ``order`` per l'attore;
* ``AgganciaTennis``: piano con priorita' COMANDO, tetto, libro nuovo;
* il runner: la partita di un comando entra a caldo sulla STESSA connessione
  (``_allinea_follow_a_caldo``), senza righe di follow nel DB, e resta
  nel piano finche' il comando e' vivo;
* la ripresa d'avvio non si disarma senza il diario del motore;
* il profilo rapido del banco su una registrazione tennis vera (se presente).

Finti: il DB del runner e' ``_Db`` del test dell'iscrizione a caldo (firme di
``tennis_db``); il canale e' il ``_CanaleBanco`` del banco (stessi nomi di
``LocalChannel``); nessuna rete, nessun DB vero.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List

import pytest

from Betfair.stream import live_order_worker as LOW
from Betfair.stream import motore_ordini as MO
from Betfair.stream.backtest.porta_banco import _CanaleBanco
from Betfair.stream.local_channel import ComandoCanale
from Betfair.stream.tennis_live import esecutore_tennis as ET
from Betfair.stream.tennis_live import guardie_tennis as GT
from Betfair.stream.tennis_live import iscrizione_a_caldo as IAC
from Betfair.stream.tennis_live import tennis_live_order_worker as TW
from Betfair.stream.tennis_live import tennis_runner as TR
from Betfair.stream.tennis_live.tests.test_tennis_iscrizione_a_caldo_2026_09_25 import (  # noqa: F401
    Banco,
    _banco,
    _follow,
    _meta,
    banchi,
    db,
)


# ===========================================================================
# il banco del motore: runner VERO (Banco) + motore con l'esecutore tennis
# ===========================================================================
class Motore:
    def __init__(self, b: Banco, tmp_path: Any, aggancio: Any = None) -> None:
        self.b = b
        self.canale = _CanaleBanco()
        self.motore = ET.costruisci_motore(
            self.canale, cartella_diario=str(tmp_path / "diario"),
            guardia_armata=lambda: False, motivo_guardia_order="g", aggancio=aggancio)
        self.motore.aggancia(b.fw, b.session)
        self._n = 0

    def manda(self, attore: str = "safe_tennis", **d: Any) -> Dict[str, Any]:
        self._n += 1
        base = {"ref": "%s-t%d" % (attore, self._n), "attore": attore, "azione": "place",
                "mode": "paper", "market_id": "1.101", "selection_id": 11, "side": "LAY",
                "price": 2.1, "size": 2.0, "persistence": "LAPSE",
                "strategy_ref": attore, "creato_ms": int(time.time() * 1000),
                "max_eta_ms": 3000, "time_in_force": None, "reduces_liability": False}
        base.update(d)
        c = ComandoCanale(ws=None, attore=attore, token_ok=True, tipo="comando", d=base,
                          ricevuto_ms=int(time.time() * 1000))
        self.motore._gestisci(c)
        return base

    def ack(self, ref: str) -> Dict[str, Any]:
        for m in self.canale.messaggi:
            if m.get("t") == "ack" and (m.get("d") or {}).get("ref") == ref:
                return dict(m["d"])
        return {}

    def fasi(self, ref: str) -> List[str]:
        return [m["d"]["fase"] for m in self.canale.messaggi
                if m.get("t") == "order" and m["d"].get("ref") == ref]

    def diario(self) -> List[Dict[str, Any]]:
        return self.motore.diario.leggi(self.motore._giorni_diario())


@pytest.fixture(autouse=True)
def _latenza_flumine_rimessa():
    """``build_order_client(PAPER)`` scrive ``flumine.config.place_latency`` (di
    PROCESSO): lo si rimette com'era, o i banchi che girano dopo nello stesso
    processo (profilo rapido di Omega) vedono una latenza di 0,6 s."""
    import flumine.config as fconf

    prima = fconf.place_latency
    yield
    fconf.place_latency = prima


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "PAPER")
    monkeypatch.delenv("LIVE_KILL_SWITCH", raising=False)
    monkeypatch.setattr(LOW, "_SETTINGS_TS", time.monotonic())   # settings freschi
    monkeypatch.setattr(TW, "tennis_db", _DbTennisNullo())
    return tmp_path


class _DbTennisNullo:
    """Le firme di ``tennis_db`` che il worker tennis usa nello specchio."""

    def __init__(self) -> None:
        self.righe: List[Dict[str, Any]] = []

    def upsert_tennis_order(self, riga: Dict[str, Any]) -> None:
        self.righe.append(dict(riga))


def _ordine_nel_blotter(b: Banco, mid: str = "1.101") -> List[Any]:
    return list(b.fw.markets.markets[mid].blotter)


# ===========================================================================
# 1. ESECUTORE: il _dispatch VERO del worker tennis
# ===========================================================================
def test_il_motore_tennis_esegue_il_dispatch_del_worker_tennis(db, banchi, ambiente,
                                                               monkeypatch):
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    chiamate = []
    vero = TW._dispatch
    monkeypatch.setattr(TW, "_dispatch", lambda *a, **k: chiamate.append(a) or vero(*a, **k))
    m = Motore(b, ambiente)
    cmd = m.manda()
    assert m.ack(cmd["ref"])["accettato"] is True
    assert len(chiamate) == 1 and chiamate[0][1] is b.session       # sessione del runner
    ordini = _ordine_nel_blotter(b)
    assert len(ordini) == 1
    o = ordini[0]
    # sotto la CAPTURE della partita (come gli ordini del desktop), client paper
    assert o.trade.strategy is b.session.capture["101"]
    assert o.client is b.client
    # tracciato per lo specchio tennis col ref interno awtq<id>
    cust = [k for k in b.session.tracked_orders if k.startswith("awtq")]
    assert len(cust) == 1 and b.session.tracked_orders[cust[0]]["order"] is o
    # diario write-ahead: 'inviato' e poi 'ordine' col customerOrderRef VERO
    righe = m.diario()
    tipi = [r["tipo"] for r in righe]
    assert tipi[:3] == ["inviato", "ordine", "esito"], tipi
    assert righe[1]["cor"] == o.customer_order_ref and righe[1]["ref"] == cmd["ref"]
    assert m.fasi(cmd["ref"]) == ["inviato"]


def test_customer_strategy_ref_dell_attore_e_default_tennis(db, banchi, ambiente,
                                                            monkeypatch):
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    visti = []
    Mercato = type(b.fw.markets.markets["1.101"])
    vero = Mercato.place_order

    def _spia(self, order, *a, **k):
        visti.append(k.get("customer_strategy_ref"))
        return vero(self, order, *a, **k)
    monkeypatch.setattr(Mercato, "place_order", _spia)
    Motore(b, ambiente).manda()
    assert visti == ["safe_tennis"]
    # senza contesto (coda DB / /order del desktop): "tennis" come sempre
    assert TW._strategy_ref() == "tennis"
    assert TW._runner_mode() == "PAPER"


def test_fok_e_riduzione_arrivano_al_limitorder(db, banchi, ambiente):
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    m = Motore(b, ambiente)
    m.manda(time_in_force="FILL_OR_KILL")
    o = _ordine_nel_blotter(b)[-1]
    assert o.order_type.time_in_force == "FILL_OR_KILL"
    # chiusura dichiarata sotto il minimo (BACK 1,50): passa come riduzione
    cmd = m.manda(side="BACK", price=2.0, size=1.5, reduces_liability=True)
    assert m.ack(cmd["ref"])["accettato"] is True
    o2 = _ordine_nel_blotter(b)[-1]
    assert o2 is not o and o2.order_type.size == 1.5
    assert o2.context.get("reduces_liability") is True


def test_sotto_il_minimo_rifiuto_dichiarato_nessun_ordine(db, banchi, ambiente):
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    m = Motore(b, ambiente)
    cmd = m.manda(side="BACK", price=2.0, size=1.5)
    assert m.fasi(cmd["ref"]) == ["rifiutato"]
    esito = [r for r in m.diario() if r["tipo"] == "esito"][-1]
    assert esito["ok"] is False and esito["errore"].startswith("submin_non_percorribile")
    assert _ordine_nel_blotter(b) == []
    assert not m.motore._submin


def test_azioni_fuori_dal_worker_tennis_rifiutate(db, banchi, ambiente):
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    m = Motore(b, ambiente)
    cmd = m.manda(azione="cashout_event")
    assert m.fasi(cmd["ref"]) == ["rifiutato"]
    esito = [r for r in m.diario() if r["tipo"] == "esito"][-1]
    assert esito["errore"].startswith("azione_non_servibile")


def test_ref_senza_prefisso_dell_attore_rifiutato(db, banchi, ambiente):
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    m = Motore(b, ambiente)
    cmd = m.manda(ref="safe-t77")
    assert m.ack("safe-t77")["accettato"] is False
    assert _ordine_nel_blotter(b) == [] and cmd


def test_annullo_mai_cross_mode(db, banchi, ambiente, monkeypatch):
    """Runner LIVE (client reale + paper affiancato): un annullo 'live' non tocca
    un ordine PAPER (regola ``_assert_order_mode`` del calcio)."""
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "LIVE")
    b = _banco(db, banchi, [_follow("101")], mode="LIVE")
    b.book("101")
    m = Motore(b, ambiente)
    m.manda(mode="paper")
    o = _ordine_nel_blotter(b)[-1]
    assert o.client is b.client_paper
    o.bet_id = "777"
    cmd = m.manda(azione="cancel", mode="live", bet_id="777", side=None, price=None,
                  size=None, selection_id=None)
    assert m.fasi(cmd["ref"]) == ["rifiutato"]
    esito = [r for r in m.diario() if r["tipo"] == "esito"][-1]
    assert "cross-mode" in esito["errore"]


def test_order_del_desktop_resta_al_worker_tennis():
    ch = _CanaleBanco()
    ch._richieste.append(object())
    solo = ET.CanaleSoloComandi(ch)
    assert solo.pop_requests() == []
    assert len(ch.pop_requests()) == 1               # il worker la trova ancora
    assert solo.messaggi is ch.messaggi              # il resto passa


def test_specchio_tennis_diventa_evento_order(db, banchi, ambiente):
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    m = Motore(b, ambiente)
    cmd = m.manda()
    TW.aggiungi_osservatore_ordini(m.motore._su_riga_specchio)
    try:
        TW._reconcile_tracked(b.session, b.fw)
    finally:
        TW.rimuovi_osservatore_ordini(m.motore._su_riga_specchio)
    assert m.fasi(cmd["ref"]) == ["inviato", "inviato"]
    ev = [x["d"] for x in m.canale.messaggi if x.get("t") == "order"][-1]
    # la riga dello specchio tennis (chiavi di tennis_live_orders) + protocollo
    riga_db = TW.tennis_db.righe[-1]
    for k, v in riga_db.items():
        assert ev[k] == v, k
    assert {"ref", "seq", "fase", "esito_ms", "updated_at"} <= set(ev)


def test_specchio_senza_osservatori_scrive_come_prima(ambiente):
    class _O:
        bet_id, status, size_matched = "9", type("S", (), {"name": "EXECUTABLE"})(), 0.0
        average_price_matched = size_remaining = size_cancelled = 0.0
        size_lapsed = size_voided = 0.0
        market_id, selection_id, side = "1.1", 11, "BACK"
        order_type = type("T", (), {"price": 2.0, "size": 3.0})()
    TW._mirror_order("paper", "E1", "awtq9000000001", _O(), {"order_type": "LIMIT"})
    riga = TW.tennis_db.righe[-1]
    assert list(riga) == ["mode", "source", "client_order_ref", "request_id", "event_id",
                          "market_id", "selection_id", "handicap", "side", "order_type",
                          "price", "size", "size_matched", "size_remaining",
                          "size_cancelled", "size_lapsed", "size_voided",
                          "average_price_matched", "status", "bet_id", "persistence"]


# ===========================================================================
# 2. AGGANCIO A COMANDO
# ===========================================================================
class _Sessione:
    def __init__(self) -> None:
        self.market_meta: Dict[str, Dict[str, Any]] = {}
        self.hosted: Dict[tuple, Any] = {}


def _aggancio(sessione: Any, *, tetto: int = 180, manuali=(), posizioni=(),
              catalogo: Any = None, fw: Any = None, ora: Any = None):
    allineati = []
    ag = ET.AgganciaTennis(
        sessione, risolvi=catalogo or (lambda mid: {"market_id": mid, "event_id": "E" + mid}),
        allinea=lambda: allineati.append(sorted(sessione.comandi)),
        manuali=lambda: set(manuali), posizioni=lambda ev: ev in set(posizioni),
        tetto=lambda: tetto, orologio=ora or time.monotonic)
    ag.aggancia(fw if fw is not None else object())
    return ag, allineati


def test_aggancio_comando_entra_nel_piano_e_chiede_l_allineamento():
    s = _Sessione()
    ag, allineati = _aggancio(s)
    assert ag.richiedi("1.5") is None
    assert "1.5" in ag.richieste and not s.comandi
    assert ag.giro() is True
    assert s.comandi["E1.5"]["market_id"] == "1.5" and allineati == [["E1.5"]]
    # un secondo comando sullo stesso mercato non richiede di nuovo il catalogo
    assert ag.richiedi("1.5") is None and ag.richieste == {}


def test_aggancio_servibile_solo_con_un_book_nuovo():
    class _M:
        market_book = object()
    mercati = {"1.5": _M()}
    fw = type("F", (), {"markets": type("Ms", (), {"markets": mercati})()})()
    s = _Sessione()
    ag, _ = _aggancio(s, fw=fw)
    assert not ag.servibile("1.5")                        # non seguito
    s.market_meta["E"] = {"market_id": "1.5"}
    s.attesa_libro["1.5"] = id(mercati["1.5"].market_book)
    assert not ag.servibile("1.5")                        # libro di prima
    mercati["1.5"].market_book = object()
    assert ag.servibile("1.5") and "1.5" not in s.attesa_libro


@pytest.mark.parametrize("caso,seguiti,manuali,posizioni,atteso", [
    ("candidata espellibile", {"C": "1.1"}, (), (), None),
    ("a mano mai espulsa", {"M": "1.1"}, ("M",), (), "tetto"),
    ("posizioni mai espulse", {"P": "1.1"}, (), ("P",), "tetto"),
])
def test_aggancio_tetto_pieno(caso, seguiti, manuali, posizioni, atteso):
    s = _Sessione()
    s.market_meta = {ev: {"market_id": mid} for ev, mid in seguiti.items()}
    ag, _ = _aggancio(s, tetto=1, manuali=manuali, posizioni=posizioni)
    no = ag.richiedi("1.9")
    if atteso is None:
        assert no is None, caso
    else:
        assert no is not None and "tetto di 1 mercati pieno" in no, caso
        assert ag.conti["rifiuti_tetto"] == 1 and not ag.richieste


def test_aggancio_comando_recente_protetto_e_niente_giostra_fra_comandi():
    ora = [1000.0]
    s = _Sessione()
    s.market_meta = {"E1": {"market_id": "1.1"}}
    s.comandi = {"E1": {"market_id": "1.1", "ultimo_uso": 1000.0}}
    ag, _ = _aggancio(s, tetto=1, ora=lambda: ora[0])
    # comando appena usato: protetto, e un altro comando (stessa priorita') non lo espelle
    assert ag.richiedi("1.2") is not None
    ora[0] += ET.PROTEZIONE_COMANDO_S + 1
    assert ag.richiedi("1.2") is not None      # pari priorita': niente giostra


def test_catalogo_non_risolto_il_comando_scade_in_aggancio():
    s = _Sessione()
    ag, allineati = _aggancio(s, catalogo=lambda mid: None)
    assert ag.richiedi("1.404") is None
    assert ag.giro() is False and ag.conti["catalogo_ko"] == 1
    assert not s.comandi and allineati == [] and not ag.richieste


def test_follows_con_comandi_ttl_e_follow_del_db_vince(monkeypatch):
    s = _Sessione()
    s.comandi = {"E1": {"market_id": "1.1", "meta": _meta("E1"), "ultimo_uso": 0.0},
                 "E2": {"market_id": "1.2", "meta": _meta("E2"), "ultimo_uso": 5000.0}}
    monkeypatch.setenv("TENNIS_AGGANCIO_COMANDO_TTL_S", "900")
    righe = ET.follows_con_comandi(s, [_follow("E2")], ora=5100.0)
    assert [f["event_id"] for f in righe] == ["E2"]            # E1 scaduto, E2 dal DB
    assert "E1" not in s.comandi
    righe = ET.follows_con_comandi(s, [], ora=5100.0)
    assert righe[0]["origine"] == ET.ORIGINE_COMANDO and righe[0]["_meta"]["market_id"] == "1.E2"
    assert TR._manuale(righe[0]) is False and TR._manuale(_follow("X", origine=None))


def test_piano_comando_sopra_armata_sotto_a_mano():
    assert IAC.PRI_ARMATA < IAC.PRI_COMANDO < IAC.PRI_MANUALE
    piano = IAC.pianifica([IAC.Evento("A", armata=True)],
                          [IAC.Evento("A", armata=True), IAC.Evento("C", comando=True)], 1)
    assert piano.aggiungi == ["C"] and piano.espulsi == ["A"]
    piano = IAC.pianifica([IAC.Evento("M", manuale=True)],
                          [IAC.Evento("M", manuale=True), IAC.Evento("C", comando=True)], 1)
    assert piano.rifiutati == ["C"] and not piano.espulsi


# ===========================================================================
# 3. IL RUNNER: la partita del comando entra a caldo, senza righe di follow
# ===========================================================================
def _comando_nel_runner(b: Banco, ev: str) -> None:
    b.session.comandi[ev] = {"market_id": "1.%s" % ev, "meta": _meta(ev),
                             "ultimo_uso": time.monotonic()}


def test_partita_del_comando_entra_a_caldo_sulla_stessa_connessione(db, banchi):
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    id_prima = b.stream.stream_id
    b.session.ultimi_follows = list(db.list_pending_tennis_follows())
    _comando_nel_runner(b, "303")
    fw_mercato = b.fw.markets.markets.get("1.303")
    TR._allinea_follow_a_caldo(b.fw, b.session, b.session.caldo,
                               ET.follows_con_comandi(b.session, b.session.ultimi_follows))
    assert b.mercati_sottoscritti() == ["1.101", "1.303"]
    assert b.stream.stream_id == id_prima + 1 and not b.session.restart_requested.is_set()
    assert "303" in b.session.market_meta
    assert b.session.attesa_libro["1.303"] == (id(fw_mercato.market_book)
                                               if fw_mercato is not None else None)
    # nessuna riga di follow scritta per il comando
    assert not [x for x in db.follow_stati if x[0] == "303"]
    # il follow_worker non la tratta come "sparita": resta finche' il comando vive
    TR.follow_worker({}, b.fw, b.session)
    assert "303" in b.session.market_meta and "303" not in b.session.follow_assenti_dal
    # l'aggancio del runner la vede servibile solo col book NUOVO
    ag = ET.AgganciaTennis(b.session, risolvi=lambda m: None, allinea=lambda: None)
    ag.aggancia(b.fw)
    b.book("303")
    assert ag.servibile("1.303")


def test_partita_del_comando_scaduta_esce_dopo_la_grazia(db, banchi, monkeypatch):
    b = _banco(db, banchi, [_follow("101")])
    _comando_nel_runner(b, "303")
    b.session.ultimi_follows = list(db.list_pending_tennis_follows())
    TR._allinea_follow_a_caldo(b.fw, b.session, b.session.caldo,
                               ET.follows_con_comandi(b.session, b.session.ultimi_follows))
    assert "303" in b.session.market_meta
    b.session.comandi["303"]["ultimo_uso"] = -1e9            # oltre il TTL
    TR.follow_worker({}, b.fw, b.session)                     # grazia 0 (fixture)
    TR.follow_worker({}, b.fw, b.session)
    assert "303" not in b.session.market_meta
    assert b.mercati_sottoscritti() == ["1.101"]


def test_follow_nuovo_solo_comandi_non_forza_il_restart(db, banchi, monkeypatch):
    """A caldo spento: la partita di un comando chiede la ricostruzione SENZA
    forzare (come un follow automatico), mai force_flat sui bot in posizione."""
    b = _banco(db, banchi, [_follow("101")])
    monkeypatch.setenv(IAC.ENV_INTERRUTTORE, "0")
    _comando_nel_runner(b, "303")
    chiamate = []
    monkeypatch.setattr(TR, "_request_restart",
                        lambda fw, s, motivo, forza=True: chiamate.append(forza))
    TR.follow_worker({}, b.fw, b.session)
    assert chiamate == [False]


def test_ripresa_d_avvio_non_si_disarma_senza_il_diario_del_motore(db, monkeypatch):
    from Betfair.stream.tennis_live import tennis_bot_service as SVC

    class _D:
        def fail_stale_pending_tennis_orders(self, s):
            return 0

        def chiudi_specchio_paper_orfano(self):
            return 0, 0
    monkeypatch.setattr(SVC, "ferma_bot_al_nuovo_avvio", lambda db=None: None)
    monkeypatch.setitem(SVC.ESITO_ULTIMO_FERMO, "riuscito", True)
    GT.arma_guardia_runner()
    GT.imposta_ripresa_motore(lambda: False)
    try:
        assert GT.ripresa_all_avvio(_D()) is False and GT.GUARDIA_RUNNER.blocca_aperture
        GT.imposta_ripresa_motore(lambda: True)
        assert GT.ripresa_all_avvio(_D()) is True and not GT.GUARDIA_RUNNER.blocca_aperture
    finally:
        GT.imposta_ripresa_motore(None)


def test_interruttore_spento_di_serie():
    assert ET.acceso({}) is False
    assert ET.acceso({"MOTORE_ORDINI_CANALE_TENNIS": "1"}) is True
    assert ET.acceso({"MOTORE_ORDINI_CANALE_TENNIS": "true"}) is False


# ===========================================================================
# 4. IL BANCO: profilo rapido su una registrazione tennis VERA (se presente)
# ===========================================================================
_REG = os.path.join(os.path.expanduser("~"), "Desktop", "tennis_rec", "20260707")


@pytest.mark.skipif(not os.path.exists(os.path.join(_REG, "35795993",
                                                    "35795993.raw.jsonl")),
                    reason="registrazione tennis 35795993 assente")
def test_profilo_rapido_safe_tennis_sulla_registrazione_vera(monkeypatch):
    from Betfair.stream.backtest import trasporto_rapido as TRR

    esiti = TRR.esegui_scenari("safe_tennis", "35795993", _REG)
    righe = {e.nome: e for e in esiti}
    assert len(esiti) == 14
    ko = [(e.nome, [c for c in e.controlli if not c[1]], e.errore) for e in esiti
          if not e.ok and not e.na]
    assert not ko, ko
    assert righe["R10 mercato non seguito"].ok and righe["R8 sotto il minimo"].ok
