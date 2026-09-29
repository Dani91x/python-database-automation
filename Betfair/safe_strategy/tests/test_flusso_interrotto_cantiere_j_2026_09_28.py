"""CANTIERE J (28/09/2026) - FLUSSO DATI INTERROTTO: I BOT DEVONO SAPERLO.

Decisione dell'utente: se i PREZZI di una partita non sono vivi, nessun bot apre
e nessun bot chiude a mercato su quella partita basandosi su quei prezzi; un
punteggio che si aggiorna non rende "fresco" un prezzo fermo.

I finti di questo file sono VERI dove conta:
  * lo SCANNER e' quello di produzione (``safe_strategy.service.Scanner``), con
    l'orologio iniettabile del banco di replay; le righe che i bot leggono sono
    quelle che ``build_rows`` produce, non dizionari scritti a mano;
  * i book sono ``MarketBook`` di betfairlightweight (stessa forma dello stream e
    del REST: vedi ``test_canale_scanner_al_ms_2026_09_18``);
  * le funzioni di freschezza dei bot sono quelle di produzione: Safe
    ``exits.feed_is_fresh`` e ``bot_service._stale_reason``, Mike
    ``feed.snapshot_from_row``, Omega ``_feed_prices_fresh`` /
    ``_feed_fresh_for_decision`` / ``_cs_from_feed``.
Nessuna rete, nessun DB.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest
from betfairlightweight.resources.bettingresources import MarketBook

from Betfair.safe_strategy import exits as XE
from Betfair.safe_strategy import service
from Betfair.safe_strategy import stream as SS
from Betfair.stream import flusso_prezzi as FP


# ===========================================================================
# finti veri
# ===========================================================================
def runner_dict(sid: int, back=None, lay=None) -> dict:
    return {"selectionId": int(sid), "status": "ACTIVE", "handicap": 0.0,
            "lastPriceTraded": None, "totalMatched": 0.0,
            "ex": {"availableToBack": ([{"price": back[0], "size": back[1]}] if back else []),
                   "availableToLay": ([{"price": lay[0], "size": lay[1]}] if lay else []),
                   "tradedVolume": []}}


class _Livello:
    __slots__ = ("price", "size")

    def __init__(self, price, size):
        self.price, self.size = price, size


class _Ex:
    __slots__ = ("available_to_back", "available_to_lay", "traded_volume")

    def __init__(self, atb, atl):
        self.available_to_back = [_Livello(l["price"], l["size"]) for l in atb]
        self.available_to_lay = [_Livello(l["price"], l["size"]) for l in atl]
        self.traded_volume = []


def book(market_id: str, runners: list, *, status: str = "OPEN", inplay: bool = True) -> MarketBook:
    mb = MarketBook(marketId=market_id, status=status, inplay=inplay, totalMatched=0.0,
                    runners=runners, betDelay=5)
    for rb, grezzo in zip(mb.runners, runners):
        rb.ex = _Ex(grezzo["ex"]["availableToBack"], grezzo["ex"]["availableToLay"])
    return mb


MO = [runner_dict(11, (1.80, 500.0), (1.82, 400.0)), runner_dict(22, (3.60, 200.0), (3.70, 150.0)),
      runner_dict(33, (5.00, 100.0), (5.20, 90.0))]
MO_VUOTO = [runner_dict(11), runner_dict(22), runner_dict(33)]
OU35 = [runner_dict(1222344, (1.50, 30.0), (1.52, 25.0)), runner_dict(1222345, (2.60, 20.0), (2.70, 15.0))]
OU45 = [runner_dict(1222347, (1.18, 50.0), (1.19, 40.0)), runner_dict(1222346, (6.0, 12.0), (6.4, 9.0))]


class Orologio:
    """L'orologio iniettabile dello scanner (lo stesso del banco): epoch secondi."""

    def __init__(self) -> None:
        self.t = time.time()

    def __call__(self) -> float:
        return self.t


def scanner_calcio(orologio: Orologio, con_linee: bool = False) -> service.Scanner:
    scan = service.Scanner(api_client=None, dry=True, use_stream=False, canale=False,
                           orologio=orologio)
    scan._mike_followed = lambda *a, **k: []          # niente DB
    inizio = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    scan.sports["calcio"].metas = {"c1": {
        "event_id": "c1", "market_id": "1.200", "event_name": "Roma v Lazio",
        "open_date": inizio, "competition": "Serie A", "runners": [],
        "sides": {"home": 11, "draw": 22, "away": 33},
    }}
    scan.events["c1"] = {"sport": "calcio", "inplay": True, "mo_status": "OPEN",
                         "minute": 20, "score_home": 0, "score_away": 0}
    if con_linee:
        scan.opp_markets["c1"] = {
            "1.35": {"market_id": "1.35", "market_type": "OVER_UNDER_35", "line": 3.5,
                     "names": {1222344: "Under 3.5 Goals", 1222345: "Over 3.5 Goals"}},
            "1.45": {"market_id": "1.45", "market_type": "OVER_UNDER_45", "line": 4.5,
                     "names": {1222347: "Under 4.5 Goals", 1222346: "Over 4.5 Goals"}},
        }
        scan.opp_full_eids.add("c1")
    scan._rebuild_market_index()
    return scan


def giro(scan: service.Scanner, tabella: Dict[str, dict]) -> List[dict]:
    """Un giro di pubblicazione come in produzione (``build_rows`` vera): le
    righe scritte finiscono nella tabella che i bot leggono."""
    rows, _ = scan.build_rows(datetime.now(timezone.utc))
    for r in rows:
        tabella[r["event_id"]] = r
    return rows


def adesso_ts(row: dict) -> float:
    return XE.parse_ts(row["updated_at"])


# ===========================================================================
# 1. LO SCENARIO ESATTO DEL 26/09: punteggio vivo, prezzi fermi da ore
# ===========================================================================
def test_26_09_punteggio_che_cambia_prezzi_fermi_da_ore_il_bot_non_opera():
    """Stream caduto e REST senza sessione: nessun book per ore, ma la riga si
    riscrive a ogni cambio di punteggio/minuto (``updated_at`` fresco). Prima del
    cantiere J ``feed_is_fresh`` diceva SI' (riga di pochi secondi). Adesso: dopo
    la soglia il blocco ``flusso`` dice fermo e nessun bot la usa."""
    ck = Orologio()
    scan = scanner_calcio(ck)
    tab: Dict[str, dict] = {}
    scan._apply_market_book(book("1.200", MO))          # ultimo prezzo: poi il buio
    giro(scan, tab)
    assert tab["c1"]["payload"]["flusso"]["vivo"] is True
    assert XE.feed_is_fresh(tab["c1"], ck.t, scanner_ts=ck.t) is True
    riscritte = 0
    for passo in range(1, 3 * 60 * 2 + 1):             # 3 ore, un passo ogni 30 s
        ck.t += 30.0
        ev = scan.events["c1"]
        ev["minute"] = 20 + passo                       # il punteggio VIVE (IPS)
        if passo % 40 == 0:
            ev["score_home"] = int(ev.get("score_home") or 0) + 1
        riscritte += len(giro(scan, tab))
        riga = tab["c1"]
        assert ck.t - adesso_ts(riga) < 1.0             # la riga e' "giovane"
        if passo >= 2:                                 # oltre i 45 s della soglia in gioco
            blk = riga["payload"]["flusso"]
            assert blk["vivo"] is False and blk["motivo"] == FP.MOTIVO_INTERROTTO
            # SAFE: anche con lo scanner che batte, niente aperture ne' uscite
            assert XE.feed_is_fresh(riga, ck.t, scanner_ts=ck.t) is False
            assert FP.valuta_riga(riga["payload"]).vivo is False
    assert riscritte >= 300                             # la riga si e' riscritta davvero
    # le quote nella riga sono ancora quelle di tre ore fa: e' il PREZZO MORTO
    assert tab["c1"]["payload"]["odds"]["home"]["back"] == 1.80


def test_26_09_rientro_dei_prezzi_riaccende_il_flusso_con_una_sola_riscrittura():
    ck = Orologio()
    scan = scanner_calcio(ck)
    tab: Dict[str, dict] = {}
    scan._apply_market_book(book("1.200", MO))
    giro(scan, tab)
    ck.t += 60.0
    assert len(giro(scan, tab)) == 1                    # passaggio a fermo: UNA riga
    assert tab["c1"]["payload"]["flusso"]["vivo"] is False
    dal_fermo = tab["c1"]["payload"]["flusso"]["dal_ms"]
    for _ in range(20):                                 # fermo e basta: zero riscritture
        ck.t += 5.0
        assert giro(scan, tab) == []
    assert tab["c1"]["payload"]["flusso"]["dal_ms"] == dal_fermo
    scan._apply_market_book(book("1.200", MO))          # il REST risponde: stesso prezzo
    assert len(giro(scan, tab)) == 1                    # passaggio a vivo: UNA riga
    assert tab["c1"]["payload"]["flusso"]["vivo"] is True
    assert XE.feed_is_fresh(tab["c1"], ck.t, scanner_ts=ck.t) is True


# ===========================================================================
# 2. MERCATO FERMO (dato vivo, invariato) != FLUSSO INTERROTTO
# ===========================================================================
class PoolConferme:
    """Il pool dello stream come lo interroga lo scanner (``conferme_flusso``):
    connessione con subscription da ``sub_da`` e ultimo messaggio (heartbeat
    compreso) a ``ultimo``, oppure latente (status 503) o morta."""

    def __init__(self, ids, sub_da: float) -> None:
        self.ids = set(ids)
        self.sub_da = sub_da
        self.ultimo: Optional[float] = None
        self.latente = False

    def conferme_flusso(self):
        if self.latente:
            return [], set(self.ids)
        if self.ultimo is None:
            return [], set()
        return [(set(self.ids), self.ultimo, self.sub_da)], set()


def test_mercato_fermo_con_heartbeat_vivi_resta_vivo_per_dieci_minuti():
    ck = Orologio()
    scan = scanner_calcio(ck)
    pool = PoolConferme(["1.200"], sub_da=ck.t - 1.0)
    scan.stream = pool                                   # solo per le conferme
    scan._apply_market_book(book("1.200", MO), dallo_stream=True)
    tab: Dict[str, dict] = {}
    for _ in range(120):                                 # 10 minuti, nessun cambio di prezzo
        ck.t += 5.0
        pool.ultimo = ck.t                               # heartbeat ogni 5 s
        scan._conferme_dallo_stream()
        giro(scan, tab)
        assert scan.flusso_evento("c1", "calcio", tab["c1"]["payload"])["vivo"] is True
    assert tab["c1"]["payload"]["flusso"]["vivo"] is True


def test_senza_heartbeat_lo_stesso_mercato_fermo_diventa_interrotto():
    ck = Orologio()
    scan = scanner_calcio(ck)
    pool = PoolConferme(["1.200"], sub_da=ck.t - 1.0)
    scan.stream = pool
    scan._apply_market_book(book("1.200", MO), dallo_stream=True)
    ck.t += 46.0                                         # nessun messaggio sulla connessione
    scan._conferme_dallo_stream()
    vivo, motivo = scan.flusso_mercato("1.200", 45.0)
    assert (vivo, motivo) == (False, FP.MOTIVO_INTERROTTO)


def test_heartbeat_di_una_connessione_nuova_non_conferma_un_book_della_vecchia():
    """Il book e' arrivato PRIMA della subscription attuale (connessione rifatta):
    la cache di prima non e' l'immagine di questa connessione (17/09: viva e muta)."""
    ck = Orologio()
    scan = scanner_calcio(ck)
    scan._apply_market_book(book("1.200", MO), dallo_stream=True)
    pool = PoolConferme(["1.200"], sub_da=ck.t + 10.0)
    scan.stream = pool
    ck.t += 60.0
    pool.ultimo = ck.t
    scan._conferme_dallo_stream()
    assert scan.flusso_mercato("1.200", 45.0) == (False, FP.MOTIVO_INTERROTTO)


def test_stream_latente_503_non_conferma():
    ck = Orologio()
    scan = scanner_calcio(ck)
    pool = PoolConferme(["1.200"], sub_da=ck.t - 1.0)
    scan.stream = pool
    scan._apply_market_book(book("1.200", MO), dallo_stream=True)
    pool.latente = True
    scan._conferme_dallo_stream()
    ck.t += 2.0
    assert scan.flusso_mercato("1.200", 45.0) == (False, FP.MOTIVO_LATENTE)
    # ma un book REST fresco (il ripiego) basta
    scan._apply_market_book(book("1.200", MO))
    assert scan.flusso_mercato("1.200", 45.0) == (True, None)


def test_ripiego_rest_a_cadenza_20s_resta_vivo():
    ck = Orologio()
    scan = scanner_calcio(ck)
    tab: Dict[str, dict] = {}
    for _ in range(30):
        scan._apply_market_book(book("1.200", MO))      # poll REST, prezzo invariato
        ck.t += 20.0
        giro(scan, tab)
        assert tab["c1"]["payload"]["flusso"]["vivo"] is True


def test_book_senza_prezzi_non_e_un_prezzo_operabile():
    ck = Orologio()
    scan = scanner_calcio(ck)
    tab: Dict[str, dict] = {}
    scan._apply_market_book(book("1.200", MO))
    scan._apply_market_book(book("1.200", MO_VUOTO))
    giro(scan, tab)
    blk = tab["c1"]["payload"]["flusso"]
    assert blk["vivo"] is False and blk["motivo"] == FP.MOTIVO_SENZA_PREZZI
    # le quote vecchie restano nella riga, ma nessun bot le usa
    assert tab["c1"]["payload"]["odds"]["home"]["back"] == 1.80
    assert XE.feed_is_fresh(tab["c1"], ck.t, scanner_ts=ck.t) is False


# ===========================================================================
# 3. PER MERCATO: una linea ferma con il MATCH_ODDS vivo
# ===========================================================================
def test_linea_ferma_con_match_odds_vivo_va_in_mercati_fermi():
    ck = Orologio()
    scan = scanner_calcio(ck, con_linee=True)
    tab: Dict[str, dict] = {}
    scan._apply_market_book(book("1.35", OU35))
    scan._apply_market_book(book("1.45", OU45))
    ck.t += 50.0                                         # le linee tacciono
    scan._apply_market_book(book("1.200", MO))           # il MATCH_ODDS vive
    giro(scan, tab)
    p = tab["c1"]["payload"]
    assert p["flusso"]["vivo"] is True
    assert p["flusso"]["mercati_fermi"] == ["1.35", "1.45"]
    assert FP.valuta_riga(p).vivo is True               # per il MATCH_ODDS
    es = FP.valuta_riga(p, ["1.35"])
    assert es.vivo is False and es.motivo == FP.MOTIVO_MERCATO_FERMO
    # Safe su un trade della linea: niente uscita a mercato
    assert XE.feed_is_fresh(tab["c1"], ck.t, scanner_ts=ck.t, market_id="1.35") is False
    assert XE.feed_is_fresh(tab["c1"], ck.t, scanner_ts=ck.t, market_id="1.200") is True
    # Safe, ingresso automatico: il mercato del SEGNALE conta (ESATTO sul CS)
    from Betfair.safe_strategy import bot_service as BS
    BS._SCANNER_TS_CACHE["stato"] = None
    assert BS._row_is_fresh(tab["c1"], ck.t, ck.t, market_id="1.35") is False
    assert BS._row_is_fresh(tab["c1"], ck.t, ck.t) is True
    assert BS._stale_reason(tab["c1"], "1.35") == "flusso_interrotto:" + FP.MOTIVO_MERCATO_FERMO


# ===========================================================================
# 4. LO STATO DELLO SCANNER: giro bloccato
# ===========================================================================
def test_stato_porta_il_flusso_e_il_giro_bloccato_ferma_tutti():
    ck = Orologio()
    scan = scanner_calcio(ck)
    tab: Dict[str, dict] = {}
    scan._apply_market_book(book("1.200", MO))
    giro(scan, tab)
    ck.t += 60.0
    giro(scan, tab)
    ist = dict(scan.flusso_istantanea)
    assert ist["eventi_fermi"] == {"c1": FP.MOTIVO_INTERROTTO}
    assert ist["eventi_fermi_n"] == 1
    stato = {"flusso": ist}
    adesso_ms = int(ck.t * 1000)
    assert FP.valuta_stato(stato, "c1", adesso_ms).motivo == FP.MOTIVO_INTERROTTO
    # prezzi di nuovo vivi, poi il giro dello scanner si BLOCCA (il battito lo
    # scrive un altro thread e resta fresco): la riga resta "viva" ma lo stato no
    scan._apply_market_book(book("1.200", MO))
    giro(scan, tab)
    stato = {"flusso": dict(scan.flusso_istantanea)}
    assert XE.feed_is_fresh(tab["c1"], ck.t, scanner_ts=ck.t, scanner_stato=stato) is True
    ck.t += FP.STATO_CALCOLO_MAX_S + 1.0
    es = FP.valuta_stato(stato, "c1", int(ck.t * 1000))
    assert es.vivo is False and es.motivo == FP.MOTIVO_SCANNER_BLOCCATO
    riga = dict(tab["c1"], updated_at=datetime.fromtimestamp(ck.t, tz=timezone.utc).isoformat())
    assert XE.feed_is_fresh(riga, ck.t, scanner_ts=ck.t, scanner_stato=stato) is False


def test_publish_status_porta_il_blocco_flusso(monkeypatch):
    ck = Orologio()
    scan = scanner_calcio(ck)
    scan._apply_market_book(book("1.200", MO))
    giro(scan, {})
    visti: List[dict] = []
    monkeypatch.setattr(scan, "_spingi_stato", lambda p: visti.append(p))
    scan.publish_status(1)                               # dry: nessuna scrittura
    assert visti and visti[-1]["flusso"]["eventi_fermi_n"] == 0
    assert isinstance(visti[-1]["flusso"]["calcolato_ms"], int)


# ===========================================================================
# 5. IO: a regime il flusso non aggiunge scritture
# ===========================================================================
def test_a_regime_nessuna_riscrittura_in_piu():
    ck = Orologio()
    scan = scanner_calcio(ck)
    pool = PoolConferme(["1.200"], sub_da=ck.t - 1.0)
    scan.stream = pool
    scan._apply_market_book(book("1.200", MO), dallo_stream=True)
    tab: Dict[str, dict] = {}
    assert len(giro(scan, tab)) == 1
    scritte = 0
    for _ in range(600):                                 # 10 minuti a giri da 1 s
        ck.t += 1.0
        pool.ultimo = ck.t
        scan._conferme_dallo_stream()
        scritte += len(giro(scan, tab))
    assert scritte == 0


def test_il_passaggio_a_fermo_salta_il_freno_di_scrittura():
    """Il freno per evento (2,5 s) vale per le QUOTE; un passaggio vivo/fermo e'
    un fatto critico: la riga esce subito (sul DB e sul canale)."""
    ck = Orologio()
    scan = scanner_calcio(ck)
    tab: Dict[str, dict] = {}
    scan._apply_market_book(book("1.200", MO))
    assert len(giro(scan, tab)) == 1
    ck.t += 1.0                                          # dentro il freno di 2,5 s
    scan._apply_market_book(book("1.200", MO_VUOTO))     # le quote spariscono
    rows = giro(scan, tab)
    assert len(rows) == 1
    assert rows[0]["payload"]["flusso"]["vivo"] is False


def test_banco_la_registrazione_che_scorre_conferma_come_gli_heartbeat():
    """Nel banco di replay non ci sono heartbeat: la registrazione che scorre e'
    lo stream vivo (``ScannerReplay.pubblica`` -> ``conferma_flusso``). Senza, un
    mercato fermo diventerebbe "interrotto" nel replay e non in produzione."""
    from Betfair.stream.backtest.banco_comune import ScannerReplay

    banco = ScannerReplay(sport="calcio", conflate_ms=0)
    t0 = time.time()
    banco.imposta_ora(t0)
    scan = banco.scan
    scan._mike_followed = lambda *a, **k: []
    scan.sports["calcio"].metas = {"c1": {
        "event_id": "c1", "market_id": "1.200", "event_name": "Roma v Lazio",
        "open_date": (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(),
        "competition": None, "runners": [], "sides": {"home": 11, "draw": 22, "away": 33},
    }}
    scan.events["c1"] = {"sport": "calcio", "inplay": True, "mo_status": "OPEN", "minute": 20,
                         "score_home": 0, "score_away": 0}
    scan._rebuild_market_index()
    banco.mercati_visti["1.200"] = "MATCH_ODDS"
    assert banco.applica_book(book("1.200", MO)) is True
    for passo in range(1, 121):                          # 10 minuti di mercato fermo
        banco.imposta_ora(t0 + 5.0 * passo)
        banco.pubblica()
        assert banco.riga("c1")["payload"]["flusso"]["vivo"] is True


# ===========================================================================
# 6. RIGHE SENZA IL BLOCCO (scanner precedente): nessun veto nuovo
# ===========================================================================
def test_riga_senza_flusso_non_cambia_la_condotta_di_prima():
    now = time.time()
    riga = {"event_id": "c1", "updated_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "payload": {"mo_market_id": "1.200", "odds": {}}}
    assert FP.valuta_riga(riga["payload"]).noto is False
    assert XE.feed_is_fresh(riga, now, scanner_ts=now) is True


# ===========================================================================
# 7. LO SHARD DELLO STREAM: chi conferma e chi no
# ===========================================================================
class _ListenerFinto:
    """``StreamListener`` di betfairlightweight: ``status`` e' quello dell'ultimo
    messaggio (``listener.py:135``: ``self.status = data.get("status")``)."""

    def __init__(self, status=None) -> None:
        self.status = status


def test_shard_conferma_solo_se_connesso_vivo_e_non_latente():
    sh = SS.StreamShard(client=None, index=0)
    assert sh.conferma_flusso() is None                  # nessuna connessione
    sh._stream = object()
    sh._connesso_mono = time.monotonic() - 10.0
    sh._last_msg_mono = time.monotonic() - 2.0
    sh._listener = _ListenerFinto(None)
    c = sh.conferma_flusso()
    assert c is not None and c[1] == sh._connesso_mono
    sh._listener = _ListenerFinto(503)
    assert sh.conferma_flusso() is None and sh.latente() is True
    sh._listener = _ListenerFinto(None)
    sh._last_msg_mono = time.monotonic() - (SS._FLUSSO_SOCKET_MAX_S + 1.0)
    assert sh.conferma_flusso() is None                  # socket muto oltre 3 heartbeat
    stato = sh.stato()
    assert stato["latente"] is False and stato["conferma"] is False


# ===========================================================================
# 8. MIKE: le linee ferme spariscono dalla decisione, ordine non fresco
# ===========================================================================
def test_mike_linea_ferma_via_dal_book_e_order_fresh_falso():
    from Betfair.mike import config as MC
    from Betfair.mike import engine as ME
    from Betfair.mike import feed as MF

    ck = Orologio()
    scan = scanner_calcio(ck, con_linee=True)
    tab: Dict[str, dict] = {}
    scan._apply_market_book(book("1.35", OU35))
    scan._apply_market_book(book("1.45", OU45))
    scan._apply_market_book(book("1.200", MO))
    giro(scan, tab)
    riga = tab["c1"]
    info = MF.event_info("c1", riga["payload"])
    assert info.complete
    params = MC.merge_params(None)
    snap = MF.snapshot_from_row(riga, info, now=ck.t, params=params, scanner_age_s=1.0)
    assert snap.order_fresh is True and snap.book(ME.MARKET_OU35, ME.SEL_UNDER) is not None
    # 26/09: le linee tacciono, la riga si riscrive per il minuto
    ck.t += 50.0
    scan._apply_market_book(book("1.200", MO))
    scan.events["c1"]["minute"] = 21
    giro(scan, tab)
    riga = tab["c1"]
    assert ck.t - adesso_ts(riga) < 1.0
    snap = MF.snapshot_from_row(riga, info, now=ck.t, params=params, scanner_age_s=1.0)
    assert snap.order_fresh is False and snap.feed_fresh is False
    assert snap.book(ME.MARKET_OU35, ME.SEL_UNDER) is None
    assert snap.book(ME.MARKET_OU45, ME.SEL_OVER) is None
    es = MF.flusso_esito(riga, None, ck.t)
    assert es.vivo is False and set(es.mercati) == {"1.35", "1.45"}
    # event_info NON filtra: gli id servono per annullare ordini vivi
    assert MF.event_info("c1", riga["payload"]).markets == {"OU35": "1.35", "OU45": "1.45"}


def test_mike_giro_scanner_bloccato_nessun_book():
    from Betfair.mike import config as MC
    from Betfair.mike import engine as ME
    from Betfair.mike import feed as MF

    ck = Orologio()
    scan = scanner_calcio(ck, con_linee=True)
    tab: Dict[str, dict] = {}
    scan._apply_market_book(book("1.35", OU35))
    scan._apply_market_book(book("1.45", OU45))
    giro(scan, tab)
    stato = {"flusso": dict(scan.flusso_istantanea)}
    riga = tab["c1"]
    info = MF.event_info("c1", riga["payload"])
    ck.t += FP.STATO_CALCOLO_MAX_S + 5.0
    snap = MF.snapshot_from_row(riga, info, now=ck.t, params=MC.merge_params(None),
                                scanner_age_s=1.0, scanner_stato=stato)
    assert snap.order_fresh is False
    assert snap.book(ME.MARKET_OU35, ME.SEL_UNDER) is None


# ===========================================================================
# 9. SAFE: il motivo dichiarato nell'attivita'
# ===========================================================================
def test_safe_motivo_flusso_interrotto(monkeypatch):
    from Betfair.safe_strategy import bot_service as BS

    ck = Orologio()
    scan = scanner_calcio(ck)
    tab: Dict[str, dict] = {}
    scan._apply_market_book(book("1.200", MO))
    giro(scan, tab)
    ck.t += 60.0
    scan.events["c1"]["minute"] = 22
    giro(scan, tab)
    monkeypatch.setitem(BS._SCANNER_TS_CACHE, "stato", None)
    assert BS._stale_reason(tab["c1"]) == "flusso_interrotto:" + FP.MOTIVO_INTERROTTO
    assert BS._row_is_fresh(tab["c1"], ck.t, ck.t) is False
    assert BS._stale_reason(None) == "feed_assente"


class DbCombo:
    """Le porte di ``BotDB`` che ``_unwind_combo`` usa (stesse firme)."""

    def __init__(self, leg: dict) -> None:
        self.leg = leg
        self.righe: List[tuple] = []

    def get_trade(self, tid: int):
        return dict(self.leg) if int(tid) == int(self.leg["id"]) else None

    def log(self, kind: str, payload: dict) -> None:
        self.righe.append((kind, payload))

    def update_trade(self, tid: int, **kw: Any) -> None:
        pass


def _riga_ferma_e_viva():
    ck = Orologio()
    scan = scanner_calcio(ck)
    tab: Dict[str, dict] = {}
    scan._apply_market_book(book("1.200", MO))
    giro(scan, tab)
    viva = dict(tab["c1"])
    ck.t += 60.0
    scan.events["c1"]["minute"] = 24
    giro(scan, tab)
    return viva, dict(tab["c1"])


def test_safe_combo_incompleta_non_chiude_a_mercato_col_flusso_fermo(monkeypatch):
    from Betfair.safe_strategy import bot_service as BS

    viva, ferma = _riga_ferma_e_viva()
    leg = {"id": 7, "status": "open", "origin": "auto", "mode": "paper", "event_id": "c1",
           "market_id": "1.200", "market_type": "MATCH_ODDS", "selection_id": 11,
           "side": "BACK", "price": 1.9, "size": 2.0}
    chiusure: List[Any] = []
    monkeypatch.setattr(BS, "_close_combo_siblings", lambda **kw: chiusure.append(kw) or True)
    monkeypatch.setattr(BS, "_mercato_non_operabile", lambda *a, **k: None)
    monkeypatch.setitem(BS._SCANNER_TS_CACHE, "stato", None)
    BS._FLUSSO_ANNUNCIATO.clear()
    db = DbCombo(leg)
    n = BS._unwind_combo(db=db, market=None, ids=[7], rows_by_event={"c1": ferma}, event_id="c1",
                         params={}, now=datetime.now(timezone.utc))
    assert n == 0 and chiusure == []
    assert db.righe and db.righe[0][0] == "exit_wait"
    assert db.righe[0][1]["wait"].startswith("flusso_interrotto:")
    # prezzi vivi: la chiusura parte
    n = BS._unwind_combo(db=db, market=None, ids=[7], rows_by_event={"c1": viva}, event_id="c1",
                         params={}, now=datetime.now(timezone.utc))
    assert n == 1 and len(chiusure) == 1


# ===========================================================================
# 10. OMEGA: i prezzi del feed non si usano (si va al book REST o si aspetta)
# ===========================================================================
class CacheFinta:
    """``scan_feed.ScanRowCache`` come la usa Omega: ``rows_for``,
    ``scanner_age_sec``, ``scanner_stato`` (stesse firme)."""

    def __init__(self, righe: Dict[str, dict], stato: Optional[dict] = None) -> None:
        self.righe = righe
        self.stato = stato

    def rows_for(self, ids):
        return {i: self.righe[i] for i in ids if i in self.righe}

    def scanner_age_sec(self):
        return 1.0

    def scanner_stato(self):
        return self.stato


def _omega_con_riga(monkeypatch, riga: dict, stato: Optional[dict] = None):
    from Betfair.omega import omega_service as OS

    cache = CacheFinta({"c1": riga}, stato)
    monkeypatch.setattr(OS._scan_feed, "shared_cache", lambda: cache)
    for d in (OS._CACHE_FEED_RIGHE, OS._CACHE_FEED_LETTO_A, OS._CACHE_FEED_CHIESTO_A, OS._CACHE_SCANNER):
        d.clear()
    monkeypatch.setattr(OS, "_canale_scan_attivo", lambda: None)
    return OS


def test_omega_flusso_fermo_niente_prezzi_dal_feed(monkeypatch):
    ck = Orologio()
    scan = scanner_calcio(ck)
    tab: Dict[str, dict] = {}
    scan._apply_market_book(book("1.200", MO))
    giro(scan, tab)
    ck.t += 60.0
    scan.events["c1"]["minute"] = 23
    giro(scan, tab)
    riga = dict(tab["c1"], updated_at=datetime.now(timezone.utc).isoformat())
    OS = _omega_con_riga(monkeypatch, riga)
    assert OS._flusso_feed("c1").vivo is False
    assert OS._feed_prices_fresh(OS._real_market, "c1") is False
    assert OS._feed_fresh_for_decision(OS._real_market, "c1") is False
    assert OS._cs_from_feed(OS._real_market, "c1") is None


def test_omega_flusso_vivo_prezzi_dal_feed(monkeypatch):
    ck = Orologio()
    scan = scanner_calcio(ck)
    tab: Dict[str, dict] = {}
    scan._apply_market_book(book("1.200", MO))
    giro(scan, tab)
    riga = dict(tab["c1"], updated_at=datetime.now(timezone.utc).isoformat())
    OS = _omega_con_riga(monkeypatch, riga)
    assert OS._flusso_feed("c1").vivo is True
    assert OS._feed_prices_fresh(OS._real_market, "c1") is True
    assert OS._feed_fresh_for_decision(OS._real_market, "c1") is True
