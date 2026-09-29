"""CANTIERE J, SECONDA CONSEGNA (28/09/2026): i punti che la verifica del
coordinatore ha trovato scoperti.

1. Safe: il veto deve guardare il MERCATO della decisione, non solo il
   MATCH_ODDS, nei TRE punti che decidono sui prezzi: apertura automatica
   (``scan_and_place``), uscita automatica (``_process_exit_one``), cash-out
   chiesto dall'utente (``_request_cashout``). Scenario: linea (o Correct Score)
   col flusso fermo, MATCH_ODDS vivo.
2. Omega ``_feed_fresh_for_decision`` e ``_feed_prices_fresh``; Safe
   ``_process_exit_one`` col giro dello scanner bloccato (``scanner_stato``).
3. DATO ASSENTE: una riga SENZA la chiave ``flusso`` mentre lo STATO dello
   scanner la porta (scanner nuovo) NON e' viva; ogni riga e ogni stato dello
   scanner nuovo portano la chiave; lo scanner vecchio (stato senza chiave) si
   DICE una volta.

Le righe sono prodotte dallo SCANNER VERO (``build_rows``), i book sono
``MarketBook`` di betfairlightweight: stessi finti del primo file del cantiere.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from Betfair.safe_strategy import bot_service as BS
from Betfair.safe_strategy import exits as XE
from Betfair.safe_strategy import service
from Betfair.safe_strategy.tests.test_flusso_interrotto_cantiere_j_2026_09_28 import (
    MO, OU35, OU45, CacheFinta, Orologio, book, giro, scanner_calcio,
)
from Betfair.stream import flusso_prezzi as FP


def _riga_linee_ferme_mo_vivo() -> "tuple[dict, dict, float]":
    """(riga con le linee FERME e il MATCH_ODDS vivo, riga tutta viva, ora)."""
    ck = Orologio()
    scan = scanner_calcio(ck, con_linee=True)
    tab: Dict[str, dict] = {}
    scan._apply_market_book(book("1.35", OU35))
    scan._apply_market_book(book("1.45", OU45))
    scan._apply_market_book(book("1.200", MO))
    giro(scan, tab)
    viva = dict(tab["c1"])
    ck.t += 50.0
    scan._apply_market_book(book("1.200", MO))
    scan.events["c1"]["minute"] = 21
    giro(scan, tab)
    ferma = dict(tab["c1"])
    assert ferma["payload"]["flusso"]["vivo"] is True
    assert ferma["payload"]["flusso"]["mercati_fermi"] == ["1.35", "1.45"]
    return ferma, viva, ck.t


@pytest.fixture(autouse=True)
def _cache_pulite():
    BS._SKIP_LOG_STATE.clear()
    BS._SCANNER_TS_CACHE.update({"cycle_ts": None, "value": None, "stato": None})
    BS._FLUSSO_ANNUNCIATO.clear()
    FP._NON_NOTO_AVVISATO.clear()
    yield
    BS._SCANNER_TS_CACHE.update({"cycle_ts": None, "value": None, "stato": None})
    FP._NON_NOTO_AVVISATO.clear()


# ===========================================================================
# 1a. APERTURA AUTOMATICA: il mercato del SEGNALE
# ===========================================================================
class DbSegnali:
    """Le porte di ``BotDB`` che ``scan_and_place`` usa senza posizioni vive
    (stesso schema di ``test_due_motori_tennis_2026_09_17.DbFinto``)."""

    def __init__(self) -> None:
        self.attivita: List[tuple] = []
        self.trades: List[dict] = []

    def log(self, kind, payload):
        self.attivita.append((kind, dict(payload)))

    def open_trades(self):
        return []

    def aggregates(self, mode=None):
        return {}

    def scanner_status(self):
        return None

    def insert_trade(self, row):
        self.trades.append({**row, "id": len(self.trades) + 1})
        return len(self.trades)

    def update_trade(self, *_a, **_k):
        pass


class EngineUnSegnale:
    def __init__(self, segnale: dict) -> None:
        self.segnale = segnale

    def evaluate(self, rows):
        return [self.segnale]


def _segnale_sulla_linea(ora: float) -> dict:
    """Un segnale con le chiavi che ``bot_service._sig`` legge, sul mercato
    1.35 (la linea ferma): e' la forma del segnale ESATTO su un mercato che NON
    e' il MATCH_ODDS."""
    return {"key": "c1:esatto:home:0-0", "event_id": "c1", "variant": "esatto",
            "sport": "calcio", "side": "lay", "market_id": "1.35",
            "market_type": "OVER_UNDER_35", "selection_id": 1222344,
            "selection_name": "Under 3.5 Goals", "price": 1.52, "size": 2.0,
            "event_name": "Roma v Lazio", "minute": 21, "score": "0-0",
            "headline": "test", "checks": {}, "first_seen_ts": ora,
            "size_available": 500.0}


def _scan_and_place(riga: dict, ora: float, monkeypatch) -> DbSegnali:
    monkeypatch.setattr(BS, "_execute", lambda **kw: type("E", (), {"status": "open"})())
    db = DbSegnali()
    now = datetime.fromtimestamp(ora, tz=timezone.utc)
    BS.scan_and_place(db=db, market=None, engine=EngineUnSegnale(_segnale_sulla_linea(ora)),
                      rows=[riga], params={"variants": ["esatto"], "max_open_trades": 0,
                                           "max_liability_per_trade": 0.0,
                                           "min_size_available_factor": 0.0,
                                           "commission_pct": 5.0, "max_spread_ratio": 1.6},
                      mode="paper", now=now, scanner_ts=ora, scanner_ts_known=True)
    return db


def _skip_flusso(db: DbSegnali) -> List[dict]:
    return [p for k, p in db.attivita
            if k == "skip" and str(p.get("reason") or "").startswith("flusso_interrotto")]


def test_apertura_esatto_linea_ferma_mo_vivo_non_apre(monkeypatch):
    ferma, _viva, ora = _riga_linee_ferme_mo_vivo()
    db = _scan_and_place(ferma, ora, monkeypatch)
    assert db.trades == []
    motivi = _skip_flusso(db)
    assert motivi and motivi[0]["reason"] == "flusso_interrotto:" + FP.MOTIVO_MERCATO_FERMO


def test_apertura_esatto_linea_viva_nessun_veto_del_flusso(monkeypatch):
    _ferma, viva, ora = _riga_linee_ferme_mo_vivo()
    db = _scan_and_place(viva, ora - 50.0, monkeypatch)
    assert _skip_flusso(db) == []


# ===========================================================================
# 1b. USCITA AUTOMATICA: il mercato del TRADE
# ===========================================================================
class DbUscite:
    def __init__(self) -> None:
        self.attivita: List[tuple] = []

    def log(self, kind, payload):
        self.attivita.append((kind, dict(payload)))

    def update_trade(self, *_a, **_k):
        pass

    def get_trade(self, _tid):
        return None


def _trade_sulla_linea() -> dict:
    return {"id": 41, "status": "open", "origin": "auto", "mode": "paper",
            "strategy": "base", "sport": "calcio", "event_id": "c1",
            "market_id": "1.35", "market_type": "OVER_UNDER_35",
            "selection_id": 1222344, "side": "lay", "price": 1.52, "size": 2.0,
            "meta": {}}


def _uscita(riga: dict, ora: float, monkeypatch, stato: Optional[dict] = None) -> DbUscite:
    monkeypatch.setattr(XE, "decide", lambda *a, **k: XE.ExitDecision("time", "test", 0.0))
    BS._SCANNER_TS_CACHE["stato"] = stato
    db = DbUscite()
    BS._process_exit_one(db=db, market=None, trade=_trade_sulla_linea(), row=riga,
                         params={}, xp=XE.merge_exit_params(None),
                         now=datetime.fromtimestamp(ora, tz=timezone.utc),
                         now_ts=ora, scanner_ts=ora)
    return db


def _attese(db: DbUscite) -> List[str]:
    return [str(p.get("wait")) for k, p in db.attivita if k == "exit_wait"]


def test_uscita_linea_ferma_mo_vivo_non_esce(monkeypatch):
    ferma, _viva, ora = _riga_linee_ferme_mo_vivo()
    db = _uscita(ferma, ora, monkeypatch)
    assert _attese(db) == ["flusso_interrotto:" + FP.MOTIVO_MERCATO_FERMO]


def test_uscita_giro_scanner_bloccato_non_esce(monkeypatch):
    """La riga e' viva e giovane, ma il giro dello scanner e' fermo da oltre
    ``STATO_CALCOLO_MAX_S``: nessun prezzo e' confermato."""
    _ferma, viva, ora = _riga_linee_ferme_mo_vivo()
    ora_viva = ora - 50.0
    stato = {"flusso": {"calcolato_ms": int((ora_viva - FP.STATO_CALCOLO_MAX_S - 5) * 1000),
                        "eventi_fermi": {}, "eventi_fermi_n": 0}}
    db = _uscita(viva, ora_viva, monkeypatch, stato)
    assert _attese(db) == ["flusso_interrotto:" + FP.MOTIVO_SCANNER_BLOCCATO]


def test_uscita_linea_viva_nessuna_attesa_di_flusso(monkeypatch):
    _ferma, viva, ora = _riga_linee_ferme_mo_vivo()
    db = _uscita(viva, ora - 50.0, monkeypatch)
    assert not [w for w in _attese(db) if w.startswith("flusso_interrotto")]


# ===========================================================================
# 1c. CASH-OUT DELL'UTENTE: il mercato del TRADE
# ===========================================================================
class DbCashout:
    def __init__(self, trade: dict) -> None:
        self.trade = trade
        self.attivita: List[tuple] = []

    def get_trade(self, tid):
        return dict(self.trade) if int(tid) == int(self.trade["id"]) else None

    def log(self, kind, payload):
        self.attivita.append((kind, dict(payload)))

    def update_trade(self, *_a, **_k):
        pass


def test_cashout_linea_ferma_mo_vivo_non_usa_il_feed(monkeypatch):
    """Il feed della linea e' fermo: i prezzi NON vengono dal feed. Il book REST
    (qui illeggibile) e' l'unica altra fonte: si rifiuta, mai una chiusura su
    prezzi fermi."""
    ferma, _viva, ora = _riga_linee_ferme_mo_vivo()
    letti: List[Any] = []
    monkeypatch.setattr(BS, "_book_prices", lambda **kw: letti.append(kw) or None)
    db = DbCashout(_trade_sulla_linea())
    res = BS._request_cashout(db=db, market=None, rows_by_event={"c1": ferma},
                              payload={"trade_id": 41}, params={},
                              now=datetime.fromtimestamp(ora, tz=timezone.utc))
    assert res.get("rejected") == "quote non disponibili", res
    assert letti, "doveva provare il book REST"


# ===========================================================================
# 2. OMEGA: decisione e prezzi di chiusura
# ===========================================================================
def _omega(monkeypatch, riga: dict, stato: Optional[dict] = None):
    from Betfair.omega import omega_service as OS

    cache = CacheFinta({"c1": riga}, stato)
    monkeypatch.setattr(OS._scan_feed, "shared_cache", lambda: cache)
    for d in (OS._CACHE_FEED_RIGHE, OS._CACHE_FEED_LETTO_A, OS._CACHE_FEED_CHIESTO_A,
              OS._CACHE_SCANNER):
        d.clear()
    monkeypatch.setattr(OS, "_canale_scan_attivo", lambda: None)
    return OS


def _riga_cs(ferma_cs: bool) -> dict:
    """Riga con il blocco Correct Score: CS fermo (MO vivo) o tutto vivo."""
    from Betfair.safe_strategy.tests.test_flusso_interrotto_cantiere_j_2026_09_28 import runner_dict

    ck = Orologio()
    scan = scanner_calcio(ck)
    scan.cs_markets["c1"] = {"market_id": "1.CS", "names": {1: "0 - 0", 2: "1 - 0"}}
    scan._rebuild_market_index()
    cs = [runner_dict(1, (8.0, 50.0), (8.4, 40.0)), runner_dict(2, (6.0, 50.0), (6.2, 40.0))]
    scan._apply_market_book(book("1.CS", cs))
    scan._apply_market_book(book("1.200", MO))
    tab: Dict[str, dict] = {}
    giro(scan, tab)
    if ferma_cs:
        ck.t += 50.0
        scan._apply_market_book(book("1.200", MO))
        scan.events["c1"]["minute"] = 25
        giro(scan, tab)
        assert tab["c1"]["payload"]["flusso"]["mercati_fermi"] == ["1.CS"]
    return dict(tab["c1"], updated_at=datetime.now(timezone.utc).isoformat())


def test_omega_decisione_e_prezzi_col_cs_fermo(monkeypatch):
    OS = _omega(monkeypatch, _riga_cs(True))
    assert OS._feed_fresh_for_decision(OS._real_market, "c1") is False
    assert OS._feed_prices_fresh(OS._real_market, "c1") is False
    assert OS._cs_from_feed(OS._real_market, "c1") is None


def test_omega_decisione_e_prezzi_col_cs_vivo(monkeypatch):
    OS = _omega(monkeypatch, _riga_cs(False))
    assert OS._feed_fresh_for_decision(OS._real_market, "c1") is True
    assert OS._feed_prices_fresh(OS._real_market, "c1") is True
    assert OS._cs_from_feed(OS._real_market, "c1") is not None


def test_omega_giro_scanner_bloccato(monkeypatch):
    import time as _t

    stato = {"flusso": {"calcolato_ms": int((_t.time() - FP.STATO_CALCOLO_MAX_S - 5) * 1000),
                        "eventi_fermi": {}}}
    OS = _omega(monkeypatch, _riga_cs(False), stato)
    assert OS._feed_fresh_for_decision(OS._real_market, "c1") is False
    assert OS._feed_prices_fresh(OS._real_market, "c1") is False


# ===========================================================================
# 3. DATO ASSENTE
# ===========================================================================
def test_ogni_riga_e_ogni_stato_dello_scanner_nuovo_portano_la_chiave(monkeypatch):
    """(a) calcio in gioco, calcio senza prezzi, tennis; riga scritta e riga
    frenata (sul canale): tutte con ``flusso``. E lo stato, anche PRIMA del
    primo giro, porta la chiave."""
    ck = Orologio()
    scan = scanner_calcio(ck)
    visti: List[dict] = []

    class Canale:
        def publish(self, topic, riga):
            visti.append(riga)

        def statistiche(self):
            return {}

    scan.canale = Canale()
    stati: List[dict] = []
    monkeypatch.setattr(scan, "_spingi_stato", lambda p: stati.append(p))
    scan.publish_status(0)                               # prima del primo giro
    assert "flusso" in stati[-1]
    assert FP.valuta_stato(stati[-1], "c1").vivo is False  # nessun calcolo = nessuna conferma
    scan.sports["tennis"].metas = {"t1": {
        "event_id": "t1", "market_id": "1.100", "event_name": "Rossi v Bianchi",
        "open_date": scan.sports["calcio"].metas["c1"]["open_date"], "competition": "ATP",
        "runners": [], "sides": {"p1": 11, "p2": 22}}}
    scan.events["t1"] = {"sport": "tennis", "inplay": True, "mo_status": "OPEN"}
    scan._rebuild_market_index()
    tab: Dict[str, dict] = {}
    giro(scan, tab)                                      # calcio e tennis mai prezzati
    scan._apply_market_book(book("1.200", MO))
    giro(scan, tab)                                      # calcio frenato: esce sul canale
    ck.t += 60.0
    giro(scan, tab)
    assert visti and all("flusso" in r["payload"] for r in visti)
    assert set(tab) == {"c1", "t1"}
    assert all("flusso" in r["payload"] for r in tab.values())
    scan.publish_status(2)
    assert "flusso" in stati[-1] and stati[-1]["flusso"]["calcolato_ms"] > 0


def test_una_sola_via_di_scrittura_delle_righe():
    """(a) Le righe vanno sul DB SOLO da ``publish`` e nascono SOLO in
    ``build_rows``, dove la chiave si scrive prima della firma."""
    src = inspect.getsource(service.Scanner)
    assert src.count("upsert_scan_rows(") == 1
    assert "def publish(" in src and "rows, wanted = self.build_rows(now)" in src
    corpo = inspect.getsource(service.Scanner.build_rows)
    assert corpo.index("payload[_flusso.CHIAVE]") < corpo.index("payload_signature(payload)")
    assert corpo.count('"updated_at": self._ora_iso()') == 1


def test_riga_senza_chiave_con_scanner_nuovo_non_e_viva():
    """(b) Lo STATO dice che lo scanner e' quello nuovo (porta ``flusso``): una
    riga senza la chiave non e' dello scanner nuovo, quindi NON e' viva."""
    import time as _t

    stato = {"flusso": {"calcolato_ms": int(_t.time() * 1000), "eventi_fermi": {}}}
    riga = {"event_id": "c1", "updated_at": datetime.now(timezone.utc).isoformat(),
            "payload": {"mo_market_id": "1.200", "odds": {}}}
    es = FP.valuta(riga["payload"], stato, "c1")
    assert es.vivo is False and es.motivo == FP.MOTIVO_NON_DICHIARATO
    assert FP.valuta(riga["payload"], stato, None, ["1.200"]).vivo is False
    assert XE.feed_is_fresh(riga, _t.time(), scanner_ts=_t.time(), scanner_stato=stato) is False
    # scanner VECCHIO (stato senza chiave): non noto, nessun veto nuovo
    assert FP.valuta(riga["payload"], {"source": "stream"}, "c1").noto is False


def test_scanner_vecchio_si_dice_una_volta_safe():
    """(c) Safe: lo stato letto dallo scanner non porta ``flusso`` = scanner
    vecchio: UN'attivita' critica ``flusso_non_dichiarato`` per processo."""
    class Db:
        def __init__(self):
            self.attivita = []

        def scanner_status(self):
            return {"payload": {"source": "stream"}, "updated_at": datetime.now(timezone.utc).isoformat()}

        def log(self, kind, payload):
            self.attivita.append((kind, payload))

    db = Db()
    for i in range(5):
        BS._scanner_ts(db, 1000.0 + i)
    kinds = [k for k, _ in db.attivita]
    assert kinds == ["flusso_non_dichiarato"]
    assert db.attivita[0][1].get("critical") is True


def test_scanner_vecchio_si_dice_una_volta_mike():
    from Betfair.mike import service as MS

    class Db:
        def __init__(self):
            self.attivita = []

        def scanner_status(self):
            return {"payload": {"source": "stream"}, "updated_at": datetime.now(timezone.utc).isoformat()}

        def log(self, kind, payload, event_id=None):
            self.attivita.append((kind, payload))

    db = Db()
    for _ in range(5):
        MS._scanner_age(db, datetime.now(timezone.utc).timestamp())
    assert [k for k, _ in db.attivita] == ["flusso_non_dichiarato"]


def test_scanner_nuovo_nessun_avviso():
    import time as _t

    class Db:
        def __init__(self):
            self.attivita = []

        def scanner_status(self):
            return {"payload": {"flusso": {"calcolato_ms": int(_t.time() * 1000)}},
                    "updated_at": datetime.now(timezone.utc).isoformat()}

        def log(self, kind, payload, event_id=None):
            self.attivita.append((kind, payload))

    db = Db()
    BS._scanner_ts(db, 1.0)
    assert db.attivita == []
