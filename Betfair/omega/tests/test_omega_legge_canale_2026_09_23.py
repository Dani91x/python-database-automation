"""OMEGA LEGGE LO SCANNER DAL CANALE LOCALE 47336 (23/09/2026).

Regola permanente dell'utente: tutto cio' che opera live legge dal canale
locale al tick; il database e' SOLO il ripiego quando il canale tace.

Che cosa si prova qui (e ogni test e' stato falsificato con una mutazione del
codice vero, vedi il referto):

1. interruttore ``OMEGA_LEGGE_CANALE`` SPENTO -> le chiamate al finto database
   (tre giri di ``run_once``) e al finto feed (quattordici ``_feed_row``) sono
   IDENTICHE alla traccia prodotta sul codice di base PRIMA della modifica;
   acceso con il canale MUTO -> stesso comportamento del database;
2. acceso + righe fresche dal canale -> nessuna lettura del feed dal database
   oltre la prima (la LISTA), righe dal canale, decisioni identiche a quelle
   che il database avrebbe dato con le stesse righe;
3. canale muto oltre ``MAX_ETA_CONTESTO_S`` -> ripiego sul database,
   ``fonte_scan='db'``;
4. canale che riprende -> ``fonte_scan='canale'``;
5. riga del canale piu' vecchia di quella del database -> vince la piu' fresca.

Finti con le chiavi del vero: la riga e' quella della select di
``scan_feed._fetch_rows`` (``event_id``, ``sport``, ``payload``,
``updated_at``) e quella che lo scanner spinge sul canale
(``service.py::_spingi_riga``: le stesse quattro chiavi), dentro il messaggio
``{"t": "scan_calcio", "d": riga}`` che ``ClientScan.incassa`` riceve dal vero
socket. File ASCII-only. Nessuna rete, nessun database, nessun thread.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import pytest

from Betfair.omega import omega_config as C
from Betfair.omega import omega_service as S
from Betfair.omega.tests import traccia_canale_scan_2026_09_23 as T
from Betfair.safe_strategy import canale_scan as CS
from Betfair.stream.scores import scan_feed as SF

ENV = "OMEGA_LEGGE_CANALE"


@pytest.fixture(autouse=True)
def _punteggi_canale_neutro(monkeypatch):
    """B33-3 (coordinatore, 24/09): questo file prova SOLO ``OMEGA_LEGGE_CANALE``
    in isolamento, col client PROPRIO di Omega. Da quando ``avvia_client_scan``
    puo' riusare il client del feed unico (``scan_feed.lettore_canale()``,
    interruttore ``PUNTEGGI_CANALE``), un valore REALE di ``PUNTEGGI_CANALE``
    nell'ambiente (il ``.env`` del checkout principale: ``load_dotenv`` risale
    ai genitori anche da un worktree, vedi ``test_punteggi_canale_2026_09_23.py``
    che si difende allo stesso modo) farebbe riusare un client CONDIVISO al
    posto di quello proprio che questi test costruiscono e osservano -- si
    forza spento e si azzera il lettore di processo, qui e a fine test."""
    monkeypatch.delenv(SF.ENV_PUNTEGGI_CANALE, raising=False)
    SF.azzera_lettore_canale()
    yield
    SF.azzera_lettore_canale()


# ===========================================================================
# aiuti
# ===========================================================================
def _golden() -> dict[str, Any]:
    return json.loads(T.GOLDEN.read_text(encoding="ascii"))


def _messaggio(riga: dict) -> str:
    """Il messaggio del canale come lo manda il produttore (``LocalChannel``)."""
    return json.dumps({"t": "scan_calcio", "d": riga})


class Canale:
    """Il client VERO di Safe (``ClientScan``) non avviato: i messaggi entrano
    da ``incassa``, la stessa funzione che il socket chiama."""

    def __init__(self) -> None:
        self.cache = CS.CacheScan()
        self.client = CS.ClientScan(CS.PORTA_SCAN, self.cache)

    def spingi(self, riga: dict) -> None:
        assert self.client.incassa(_messaggio(riga)), "riga rifiutata dal client"


@pytest.fixture
def canale(monkeypatch):
    """Interruttore ACCESO e un client installato come fa ``avvia_client_scan``."""
    c = Canale()
    monkeypatch.setenv(ENV, "1")
    monkeypatch.setitem(S._CLIENT_SCAN, "client", c.client)
    monkeypatch.setitem(S._CLIENT_SCAN, "cache", c.cache)
    return c


@pytest.fixture
def feed(monkeypatch):
    """``_feed_row`` con le cadenze VERE, un orologio a mano e un finto
    ``ScanRowCache`` che registra le select."""
    for k, v in T.CADENZE_VERE.items():
        monkeypatch.setitem(C.DEFAULTS, k, v)
    S.svuota_le_cache()
    orologio = {"t": 1000.0}
    finta = T.ScanRowCacheRegistra({}, orologio)
    monkeypatch.setattr(SF, "shared_cache", lambda: finta)
    monkeypatch.setattr(S, "_mono", lambda: orologio["t"])
    return finta, orologio


def _select(finta) -> int:
    return sum(1 for r in finta.diario if r[0] == "rows_for")


# ===========================================================================
# (1) INTERRUTTORE SPENTO: la traccia e' quella di prima
# ===========================================================================
@pytest.mark.parametrize("valore", [None, "", "0", "no", "false", "spento"])
def test_1_spento_run_once_chiama_il_db_come_prima(monkeypatch, valore):
    if valore is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, valore)
    assert T.traccia_run_once(S) == _golden()["run_once"]


@pytest.mark.parametrize("valore", [None, "0"])
def test_1_spento_il_feed_chiama_il_db_come_prima(monkeypatch, valore):
    if valore is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, valore)
    assert T.traccia_feed(S, SF) == _golden()["feed"]


def test_1_spento_anche_con_un_client_pieno_di_righe_vincenti(monkeypatch):
    """Il client c'e' e ha righe fresche e piu' recenti di tutte, ma
    l'interruttore e' spento: non conta niente, la traccia e' quella di prima."""
    c = Canale()
    adesso = time.time()
    for eid in ("E1", "E2", "E3", "E4"):
        c.spingi(T.riga_scan(eid, adesso + 5.0, minute=88, odds_ts_ms=1))
    monkeypatch.delenv(ENV, raising=False)
    monkeypatch.setitem(S._CLIENT_SCAN, "client", c.client)
    monkeypatch.setitem(S._CLIENT_SCAN, "cache", c.cache)
    # ``traccia_feed`` chiama ``svuota_le_cache``: la memoria del canale va
    # ripopolata dopo; qui si controlla che, anche PIENA, non entri.
    originale = S.svuota_le_cache

    def svuota_e_ripopola():
        originale()
        for eid in ("E1", "E2", "E3", "E4"):
            c.spingi(T.riga_scan(eid, time.time() + 5.0, minute=88, odds_ts_ms=1))
    monkeypatch.setattr(S, "svuota_le_cache", svuota_e_ripopola)
    assert T.traccia_feed(S, SF) == _golden()["feed"]
    assert S.fonte_scan_del_giro() is None


def test_1_acceso_con_canale_muto_il_feed_e_quello_del_db(canale):
    """Acceso, ma il canale non ha mandato niente: stesse select, stesse righe."""
    assert T.traccia_feed(S, SF) == _golden()["feed"]


def test_1_acceso_con_canale_muto_run_once_scrive_solo_fonte_db(canale):
    """Acceso e muto: le chiamate al DB sono quelle di prima, con DUE sole
    differenze dichiarate dentro la stessa ``set_control`` (zero scritture in
    piu'): ``stats.fonte_scan='db'`` e ``stats.sveglia`` (i contatori della
    sveglia del ciclo, che a interruttore spento valgono ``None``)."""
    dopo = T.traccia_run_once(S)
    prima = _golden()["run_once"]
    assert [c[0] for c in dopo] == [c[0] for c in prima]
    fonti, sveglie = [], []
    for c in dopo:
        if c[0] == "set_control":
            fonti.append(c[2]["stats"].pop("fonte_scan", "ASSENTE"))
            sveglie.append(c[2]["stats"].pop("sveglia", "ASSENTE"))
    for c in prima:
        if c[0] == "set_control":
            assert c[2]["stats"].pop("sveglia") is None
    assert fonti == ["db", "db", "db"]
    assert all(isinstance(s, dict) and s["giro_minimo_s"] == 5.0 for s in sveglie)
    assert dopo == prima


def test_1_spento_nessun_client_si_avvia(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)

    def vietato(*a, **k):
        raise AssertionError("a interruttore spento non si costruisce nessun client")
    monkeypatch.setattr(CS, "ClientScan", vietato)
    monkeypatch.setitem(S._CLIENT_SCAN, "client", None)
    monkeypatch.setitem(S._CLIENT_SCAN, "cache", None)
    assert S.avvia_client_scan() is False
    assert S._CLIENT_SCAN["client"] is None and S._CLIENT_SCAN["cache"] is None
    assert S._canale_scan_attivo() is None


def test_1_acceso_si_avvia_il_client_di_safe_e_si_ferma(monkeypatch):
    """Il client e' ``canale_scan.ClientScan`` (il modulo di Safe), senza
    sveglia propria, sulla porta dello scanner. Nessun thread nel test."""
    monkeypatch.setenv(ENV, "1")
    monkeypatch.setitem(S._CLIENT_SCAN, "client", None)
    monkeypatch.setitem(S._CLIENT_SCAN, "cache", None)
    avviati = []
    monkeypatch.setattr(CS.ClientScan, "avvia", lambda self: avviati.append(self))
    try:
        assert S.avvia_client_scan() is True
        client = S._CLIENT_SCAN["client"]
        assert isinstance(client, CS.ClientScan) and avviati == [client]
        assert client.porta == CS.porta_scan()
        assert isinstance(client.evento, S._SvegliaDalCanale)
        assert client.interessa is S._evento_con_posizione_viva   # B-2 (23/09)
        assert isinstance(S._CLIENT_SCAN["cache"], CS.CacheScan)
        assert S._canale_scan_attivo() is CS
        assert S.avvia_client_scan() is True and len(avviati) == 1   # idempotente
    finally:
        S.ferma_client_scan()
    assert S._CLIENT_SCAN["client"] is None


# ===========================================================================
# (2) ACCESO + CANALE CON RIGHE FRESCHE
# ===========================================================================
def test_2_righe_dal_canale_nessuna_lettura_db_oltre_la_lista(canale, feed):
    finta, orologio = feed
    adesso = time.time()
    finta.righe["E1"] = T.riga_scan("E1", adesso - 3.0, minute=30)
    S._feed_row("E1")                                  # la LISTA: una select
    assert _select(finta) == 1
    for passo in range(1, 10):                         # 9 s, feed_cache_s = 2 s
        orologio["t"] = 1000.0 + passo
        riga = T.riga_scan("E1", time.time(), minute=30 + passo)
        canale.spingi(riga)
        payload, upd = S._feed_row("E1", hard_max_age=S.DECISION_MAX_AGE_S)
        assert payload == riga["payload"] and upd == riga["updated_at"]
    assert _select(finta) == 1, "col canale sano nessuna select della scan"
    assert S.fonte_scan_del_giro() == "canale"
    stats = S._con_fonte_scan({})
    assert stats == {"fonte_scan": "canale"}


def test_2_a_canale_spento_le_stesse_chiamate_leggono_il_db(feed):
    """Il rovescio del precedente (stesso copione, interruttore spento): senza
    canale le select sono una ogni ``feed_cache_s``. E' il numero che il canale
    toglie."""
    finta, orologio = feed
    finta.righe["E1"] = T.riga_scan("E1", time.time() - 3.0, minute=30)
    S._feed_row("E1")
    for passo in range(1, 10):
        orologio["t"] = 1000.0 + passo
        S._feed_row("E1", hard_max_age=S.DECISION_MAX_AGE_S)
    assert _select(finta) == 5


def test_2_riallineamento_col_db_ogni_dieci_secondi(canale, feed):
    finta, orologio = feed
    finta.righe["E1"] = T.riga_scan("E1", time.time() - 3.0)
    S._feed_row("E1")
    for passo in (3, 6, 9, 10, 12, 19, 20):
        orologio["t"] = 1000.0 + passo
        canale.spingi(T.riga_scan("E1", time.time(), minute=40 + passo))
        S._feed_row("E1")
    # letture: t=0 (lista), t=10 (riallineamento), t=20 (riallineamento)
    assert [r[1] for r in finta.diario if r[0] == "rows_for"] == [1000.0, 1010.0, 1020.0]
    assert S._RISINC_DB_S == 10.0


def _cs_payload(minute: int, lay: float) -> dict:
    return {"inplay": True, "minute": minute, "score_home": 1, "score_away": 0,
            "event_name": "Casa v Ospiti", "open_date": "2026-09-23T19:00:00+00:00",
            "odds_ts_ms": 1790000000000,
            "cs": {"market_id": "1.234", "status": "OPEN", "inplay": True,
                   "selections": [
                       {"selection_id": 1, "name": "1 - 0", "lay": lay, "lay_size": 50.0,
                        "back": lay - 0.1, "back_size": 40.0, "runner_status": "ACTIVE"},
                       {"selection_id": 2, "name": "2 - 0", "lay": 8.0, "lay_size": 20.0,
                        "back": 7.6, "back_size": 10.0, "runner_status": "ACTIVE"}]}}


def _decisioni(eid: str) -> list:
    """Le letture del feed che DECIDONO in Omega, col market VERO (il feed e'
    attivo solo li'): book CS, minuto, stato, freschezza per decidere."""
    M = S._real_market
    return [repr(S._cs_from_feed(M, eid, max_age=S.DECISION_MAX_AGE_S)),
            repr(S._cs_from_feed(M, eid)),
            S._feed_minute(M, eid),
            repr(S._feed_state(M, eid)),
            S._feed_prices_fresh(M, eid),
            S._feed_fresh_for_decision(M, eid),
            repr(S._feed_row(eid, hard_max_age=S.DECISION_MAX_AGE_S)[0])]


def test_2_decisioni_identiche_a_quelle_del_db_con_le_stesse_righe(monkeypatch, feed):
    finta, orologio = feed
    adesso = time.time()
    buona = {"event_id": "E7", "sport": "calcio", "payload": _cs_payload(63, 12.5),
             "updated_at": T.iso(adesso - 1.0)}
    # A) la riga BUONA arriva dal DATABASE, interruttore spento
    finta.righe["E7"] = dict(buona)
    dal_db = _decisioni("E7")
    assert dal_db[2] == 63 and "12.5" in dal_db[0]
    # B) il database ha una riga VECCHIA, la stessa riga BUONA arriva dal canale
    S.svuota_le_cache()
    finta.righe["E7"] = {"event_id": "E7", "sport": "calcio",
                         "payload": _cs_payload(61, 30.0),
                         "updated_at": T.iso(adesso - 4.0)}
    c = Canale()
    monkeypatch.setenv(ENV, "1")
    monkeypatch.setitem(S._CLIENT_SCAN, "client", c.client)
    monkeypatch.setitem(S._CLIENT_SCAN, "cache", c.cache)
    S._feed_row("E7")                                  # la lista, dal DB
    c.spingi(dict(buona))
    orologio["t"] += 3.0
    prima = _select(finta)
    dal_canale = _decisioni("E7")
    assert _select(finta) == prima, "le decisioni col canale non leggono il DB"
    assert dal_canale == dal_db


# ===========================================================================
# (3) CANALE MUTO OLTRE LA SOGLIA -> DB ;  (4) CANALE CHE RIPRENDE -> CANALE
# ===========================================================================
def test_3_4_canale_muto_ripiega_sul_db_e_poi_torna_al_canale(canale, feed, monkeypatch):
    finta, orologio = feed
    base = time.time()
    finta.righe["E1"] = T.riga_scan("E1", base - 2.0, minute=20)
    S._feed_row("E1")
    canale.spingi(T.riga_scan("E1", base, minute=21))
    orologio["t"] = 1003.0
    S._CACHE_FONTE_SCAN.clear()
    payload, _ = S._feed_row("E1")
    assert payload["minute"] == 21 and S.fonte_scan_del_giro() == "canale"
    assert _select(finta) == 1

    # (3) il canale tace: la sua ultima riga ha piu' di MAX_ETA_CONTESTO_S
    muto = base + CS.MAX_ETA_CONTESTO_S + 0.5
    monkeypatch.setattr(CS.time, "time", lambda: muto)
    finta.righe["E1"] = T.riga_scan("E1", base - 0.5, minute=20)
    orologio["t"] = 1006.0
    S._CACHE_FONTE_SCAN.clear()
    payload, _ = S._feed_row("E1")
    assert _select(finta) == 2, "canale muto: si torna alla lettura del database"
    assert payload["minute"] == 20
    assert S.fonte_scan_del_giro() == "db"
    assert S._con_fonte_scan({"x": 1}) == {"x": 1, "fonte_scan": "db"}

    # (4) il canale riprende: riga nuova, fresca e piu' recente del DB
    monkeypatch.setattr(CS.time, "time", lambda: muto + 1.0)
    canale.spingi(T.riga_scan("E1", muto + 0.5, minute=27))
    orologio["t"] = 1007.0
    S._CACHE_FONTE_SCAN.clear()
    payload, _ = S._feed_row("E1")
    assert payload["minute"] == 27
    assert S.fonte_scan_del_giro() == "canale"
    assert _select(finta) == 2, "il canale che riprende non costa select"


def test_3_la_soglia_del_muto_e_quella_di_safe():
    assert CS.MAX_ETA_CONTESTO_S == 5.0


# ===========================================================================
# (5) VINCE LA PIU' FRESCA ; il canale non aggiunge partite
# ===========================================================================
def test_5_riga_del_canale_piu_vecchia_vince_il_db(canale, feed):
    finta, orologio = feed
    adesso = time.time()
    canale.spingi(T.riga_scan("E1", adesso - 2.0, minute=50))     # canale: -2 s
    finta.righe["E1"] = T.riga_scan("E1", adesso - 1.0, minute=51)  # DB: -1 s
    payload, upd = S._feed_row("E1")
    assert payload["minute"] == 51 and upd == finta.righe["E1"]["updated_at"]
    assert S.fonte_scan_del_giro() == "db"
    # e dentro la finestra di riallineamento, passata la cache, si rilegge il DB
    orologio["t"] += 3.0
    S._feed_row("E1")
    assert _select(finta) == 2


def test_5_riga_del_canale_piu_fresca_vince_anche_alla_lettura_del_db(canale, feed):
    """La strada del database (prima lettura, o cache scaduta fuori dalla
    finestra di riallineamento): se il canale ha una riga piu' fresca, vince
    quella, e la fonte del giro e' ``canale``."""
    finta, orologio = feed
    adesso = time.time()
    finta.righe["E1"] = T.riga_scan("E1", adesso - 3.0, minute=50)
    canale.spingi(T.riga_scan("E1", adesso - 0.5, minute=52))
    payload, _ = S._feed_row("E1")                  # prima lettura: select + fusione
    assert _select(finta) == 1
    assert payload["minute"] == 52
    assert S.fonte_scan_del_giro() == "canale"
    assert S._CACHE_FONTE_SCAN == {"canale": 1}
    orologio["t"] += S._RISINC_DB_S + 1.0          # fuori dalla finestra: si rilegge
    S._CACHE_FONTE_SCAN.clear()
    payload, _ = S._feed_row("E1")
    assert _select(finta) == 2 and payload["minute"] == 52
    assert S._CACHE_FONTE_SCAN == {"canale": 1}


def test_5_a_parita_di_istante_vince_il_db(canale, feed):
    finta, _ = feed
    adesso = time.time()
    canale.spingi(T.riga_scan("E1", adesso - 1.0, minute=70))
    finta.righe["E1"] = T.riga_scan("E1", adesso - 1.0, minute=69)
    payload, _ = S._feed_row("E1")
    assert payload["minute"] == 69


def test_5_riga_del_canale_senza_odds_ts_ms_non_vince(canale, feed):
    finta, _ = feed
    adesso = time.time()
    canale.spingi(T.riga_scan("E1", adesso - 0.1, minute=80, odds_ts_ms=None))
    finta.righe["E1"] = T.riga_scan("E1", adesso - 3.0, minute=79)
    payload, _ = S._feed_row("E1")
    assert payload["minute"] == 79


def test_5_il_canale_non_aggiunge_una_partita_che_il_db_non_ha(canale, feed):
    finta, orologio = feed
    canale.spingi(T.riga_scan("E9", time.time(), minute=10))
    assert S._feed_row("E9") == (None, None)
    orologio["t"] += 1.0
    assert S._feed_row("E9") == (None, None)


def test_5_la_riga_del_canale_passa_dalle_stesse_guardie(canale, feed):
    """Nessun privilegio: una riga del canale che vince ma e' oltre il tetto
    di decisione viene scartata come qualunque altra (qui: tetto di 0,5 s)."""
    finta, orologio = feed
    adesso = time.time()
    finta.righe["E1"] = T.riga_scan("E1", adesso - 4.0)
    S._feed_row("E1")
    canale.spingi(T.riga_scan("E1", adesso - 2.0, minute=33))
    orologio["t"] += 3.0
    payload, upd = S._feed_row("E1", hard_max_age=0.5)
    assert payload is None and upd == T.iso(adesso - 2.0)


# ===========================================================================
# contratti
# ===========================================================================
def test_svuota_le_cache_svuota_la_memoria_del_canale_non_il_client(canale):
    canale.spingi(T.riga_scan("E1", time.time()))
    S._CACHE_FONTE_SCAN["canale"] = 3
    S.svuota_le_cache()
    assert canale.cache.stato()["righe"] == 0
    assert not S._CACHE_FONTE_SCAN
    assert S._CLIENT_SCAN["client"] is canale.client


def test_run_once_riazzera_i_conti_della_fonte(canale):
    S._CACHE_FONTE_SCAN["canale"] = 5
    diario = T.traccia_run_once(S)
    stats = [c[2]["stats"] for c in diario if c[0] == "set_control"]
    assert stats and all(s.get("fonte_scan") == "db" for s in stats)


def test_il_modulo_del_canale_e_quello_di_safe_importato_non_copiato():
    sorgente = Path(S.__file__).read_text(encoding="utf-8")
    assert "from Betfair.safe_strategy import canale_scan as CS" in sorgente
    for nome in ("class ClientScan", "class CacheScan", "def fondi(", "def piu_recente("):
        assert nome not in sorgente, nome
    assert S.ENV_LEGGE_CANALE == ENV


def test_riallineamento_stesso_numero_di_safe():
    bot = Path(CS.__file__).with_name("bot_service.py").read_text(encoding="utf-8")
    m = re.search(r"^_RISINC_DB_S = ([0-9.]+)", bot, re.MULTILINE)
    assert m and float(m.group(1)) == S._RISINC_DB_S


# ===========================================================================
# ESTENSIONE 1 (coordinatore): stesso book dal CANALE e dal REST -> stesso
# mercato, stesso snapshot, stessi prezzi di uscita
# ===========================================================================
class BetfairRestFinto:
    """Il REST di Betfair per il ramo di ripiego: ``get_event_market_by_type``
    e ``read_market`` come ``omega_market``, con il book nel formato VERO di
    ``listMarketBook`` (``selectionId``, ``status``, ``ex.availableToLay`` /
    ``availableToBack`` con ``price``/``size``) convertito dal convertitore
    VERO ``omega_market._snapshot_from_book``; ``read_book`` e' la stessa
    conversione di ``omega_market.read_book``."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.chiamate: list[str] = []
        cs = payload["cs"]
        self.book = {"marketId": cs["market_id"], "status": cs["status"],
                     "inplay": cs["inplay"], "runners": [
                         {"selectionId": s["selection_id"], "status": s["runner_status"],
                          "ex": {"availableToLay": [{"price": s["lay"], "size": s["lay_size"]}],
                                 "availableToBack": [{"price": s["back"], "size": s["back_size"]}]}}
                         for s in cs["selections"]]}

    def _mercato(self, event_id: str):
        cs = self.payload["cs"]
        return S._real_market.CorrectScoreMarket(
            market_id=cs["market_id"], event_id=str(event_id),
            event_name=self.payload["event_name"],
            market_start_time=S._parse_iso_dt(self.payload["open_date"]),
            runner_names={int(s["selection_id"]): s["name"] for s in cs["selections"]})

    def get_event_market_by_type(self, event_id, name, market_type):
        self.chiamate.append("catalogo")
        return self._mercato(event_id)

    def read_market(self, market):
        self.chiamate.append("read_market")
        return S._real_market._snapshot_from_book(market, self.book)

    def read_book(self, market_id, runner_names):
        self.chiamate.append("read_book")
        runners = []
        for r in self.book["runners"]:
            ex = r["ex"]
            lp, ls, lad = S._real_market._best_lay(ex["availableToLay"])
            bp, bs = S._real_market._best_back(ex["availableToBack"])
            runners.append({"selection_id": r["selectionId"], "name": "?", "status": r["status"],
                            "lay_price": lp, "lay_size": ls, "back_price": bp, "back_size": bs,
                            "lay_ladder": [list(x) for x in lad]})
        return {"market_id": market_id, "status": self.book["status"],
                "inplay": self.book["inplay"], "runners": runners}


def test_estensione_stesso_book_dal_canale_e_dal_rest_stessa_gamba(canale, feed):
    finta, orologio = feed
    adesso = time.time()
    payload = _cs_payload(63, 12.5)
    ev = S._real_market.EventInfo("E7", "Casa v Ospiti", None)
    rest = BetfairRestFinto(payload)
    # ramo REST (nessun feed): catalogo + book da listMarketBook
    dal_rest = S._leg_market(rest, ev, "CORRECT_SCORE", None)
    assert rest.chiamate == ["catalogo", "read_market"]
    # ramo CANALE: la riga dello scanner arriva dal canale (il DB ha la lista)
    finta.righe["E7"] = {"event_id": "E7", "sport": "calcio",
                         "payload": _cs_payload(61, 30.0), "updated_at": T.iso(adesso - 4.0)}
    S._feed_row("E7")
    canale.spingi({"event_id": "E7", "sport": "calcio", "payload": payload,
                   "updated_at": T.iso(adesso - 0.5)})
    orologio["t"] += 3.0
    stato = S._feed_state(S._real_market, "E7")
    assert stato == payload
    rest2 = BetfairRestFinto(payload)
    dal_canale = S._leg_market(rest2, ev, "CORRECT_SCORE", stato)
    assert rest2.chiamate == [], "col book dal canale ZERO chiamate REST"
    assert dal_canale[0] == dal_rest[0]
    assert dal_canale[1] == dal_rest[1]
    assert S.fonte_scan_del_giro() == "canale"


def test_estensione_stessi_prezzi_di_uscita_dal_canale_e_dal_rest(canale, feed):
    finta, orologio = feed
    adesso = time.time()
    payload = _cs_payload(70, 9.0)
    tr = {"event_id": "E7", "market_id": "1.234", "selection_id": 1}
    rest = BetfairRestFinto(payload)
    dal_rest = S._cashout_prices(rest, tr)          # market finto -> REST read_book
    assert rest.chiamate == ["read_book"]
    finta.righe["E7"] = {"event_id": "E7", "sport": "calcio",
                         "payload": _cs_payload(69, 30.0), "updated_at": T.iso(adesso - 4.0)}
    S._feed_row("E7")
    canale.spingi({"event_id": "E7", "sport": "calcio", "payload": payload,
                   "updated_at": T.iso(adesso - 0.5)})
    orologio["t"] += 3.0
    prima = _select(finta)
    dal_canale = S._cashout_prices(S._real_market, tr)   # market vero -> feed (canale)
    assert _select(finta) == prima
    assert {k: dal_canale[k] for k in ("back", "back_size", "lay", "lay_size")} == \
        {k: dal_rest[k] for k in ("back", "back_size", "lay", "lay_size")}
    assert [list(x) for x in dal_canale["lay_ladder"]] == [list(x) for x in dal_rest["lay_ladder"]]


# ===========================================================================
# ESTENSIONE 2 (coordinatore): la SVEGLIA del ciclo sulle righe fresche
# ===========================================================================
class _Orologio:
    def __init__(self, t0: float = 1000.0) -> None:
        self.t = float(t0)
        self.dormite: list[float] = []

    def ora(self) -> float:
        return self.t

    def dormi(self, quanto: float) -> None:
        self.dormite.append(float(quanto))
        self.t += float(quanto)


@pytest.fixture
def sveglia(monkeypatch):
    """Interruttore acceso, client VERO di Safe cablato da ``avvia_client_scan``
    (senza thread), sveglia di Omega con un orologio a mano."""
    from Betfair.stream import sveglia_canale as SV

    monkeypatch.setenv(ENV, "1")
    monkeypatch.delenv(S.ENV_GIRO_MINIMO, raising=False)
    monkeypatch.setitem(S._CLIENT_SCAN, "client", None)
    monkeypatch.setitem(S._CLIENT_SCAN, "cache", None)
    monkeypatch.setattr(CS.ClientScan, "avvia", lambda self: None)
    orol = _Orologio()
    monkeypatch.setattr(S, "_SVEGLIA", SV.Sveglia("omega", ora=orol.ora, dormi=orol.dormi))

    def _vietato(_s):
        raise AssertionError("col canale acceso la dormita non e' piu' time.sleep")
    monkeypatch.setattr(S.time, "sleep", _vietato)
    assert S.avvia_client_scan() is True
    client = S._CLIENT_SCAN["client"]
    # B-2 (23/09): Omega segue E1 ed E2, ma solo E1 ha una POSIZIONE VIVA:
    # solo E1 sveglia il ciclo (E2 e' una candidata, resta a poll_interval_s)
    S._CACHE_FEED_CHIESTO_A["E1"] = 0.0
    S._CACHE_FEED_CHIESTO_A["E2"] = 0.0
    S._ricorda_posizioni_vive("open", [{"event_id": "E1", "status": "open"}])
    yield client, orol
    S.ferma_client_scan()
    S._CACHE_FEED_CHIESTO_A.clear()
    S._CACHE_POSIZIONI_VIVE.clear()


def _msg(eid: str) -> str:
    return _messaggio(T.riga_scan(eid, time.time(), minute=40))


def test_sveglia_riga_fresca_di_partita_seguita_il_giro_riparte_prima_dei_20s(sveglia):
    client, orol = sveglia
    assert client.incassa(_msg("E1"))
    assert client.svegliate == 1
    S._dormi_o_sveglia(20.0, {"poll_interval_s": 20})
    # riparte al pavimento del canale (5 s dall'inizio del giro), non a 20 s
    assert orol.dormite == [5.0]
    assert S._SVEGLIA.statistiche()["usate"] == 1


def test_sveglia_a_riposo_riparte_prima_dei_60s(sveglia):
    client, orol = sveglia
    orol.t += 30.0                               # il giro precedente e' di 30 s fa
    assert client.incassa(_msg("E1"))
    S._dormi_o_sveglia(60.0, {"poll_interval_s": 20, "idle_cycle_s": 60})
    assert orol.dormite == []                    # oltre il pavimento: subito
    assert S._SVEGLIA.statistiche()["usate"] == 1


def test_sveglia_riga_di_partita_non_seguita_nessuna_sveglia(sveglia):
    client, _ = sveglia
    assert client.incassa(_msg("E2"))            # la riga entra nella memoria...
    assert client.svegliate == 0                 # ...ma non sveglia nessuno
    assert S._SVEGLIA.statistiche()["sveglie"] == 0


def test_sveglia_coalescenza_cento_righe_un_giro(sveglia):
    client, orol = sveglia
    for _ in range(100):
        client.incassa(_msg("E1"))
    assert S._SVEGLIA.statistiche()["sveglie"] == 100
    S._dormi_o_sveglia(20.0, {"poll_interval_s": 20})
    assert S._SVEGLIA.statistiche()["usate"] == 1


def test_sveglia_tetto_dodici_giri_al_minuto(sveglia):
    """Una riga fresca prima di OGNI dormita (il caso peggiore: il canale
    parla sempre): in 60 s di orologio i giri sono 12, non uno per tick."""
    client, orol = sveglia
    inizio, giri = orol.t, 0
    while orol.t - inizio < 60.0:
        client.incassa(_msg("E1"))
        S._dormi_o_sveglia(20.0, {"poll_interval_s": 20})
        giri += 1
    assert giri == 12
    assert all(d == pytest.approx(5.0) for d in orol.dormite)


@pytest.mark.parametrize("scritto,atteso", [
    (None, 5.0), ("", 5.0), ("abc", 5.0), ("nan", 5.0), ("1", 5.0), ("0", 5.0),
    ("5", 5.0), ("10", 10.0), ("12.5", 12.5)])
def test_sveglia_il_tetto_si_legge_dal_env_e_non_scende_sotto_5s(monkeypatch, scritto, atteso):
    if scritto is None:
        monkeypatch.delenv(S.ENV_GIRO_MINIMO, raising=False)
    else:
        monkeypatch.setenv(S.ENV_GIRO_MINIMO, scritto)
    assert S.giro_minimo_canale_s() == atteso


def test_sveglia_tetto_dal_env_rispettato(sveglia, monkeypatch):
    client, orol = sveglia
    monkeypatch.setenv(S.ENV_GIRO_MINIMO, "10")
    inizio, giri = orol.t, 0
    while orol.t - inizio < 60.0:
        client.incassa(_msg("E1"))
        S._dormi_o_sveglia(20.0, {"poll_interval_s": 20})
        giri += 1
    assert giri == 6


def test_sveglia_spento_dorme_con_time_sleep_come_oggi(monkeypatch):
    chiamate: list[float] = []
    monkeypatch.delenv(ENV, raising=False)
    monkeypatch.setattr(S.time, "sleep", lambda s: chiamate.append(s))
    monkeypatch.setattr(S, "_ASCOLTO_SCAN", None)
    monkeypatch.setitem(S._CLIENT_SCAN, "client", Canale().client)   # anche con un client
    S._SVEGLIA.alza("scan", minimo_s=0.0)
    try:
        S._dormi_o_sveglia(60.0, {"poll_interval_s": 20})
        assert chiamate == [60.0]
        assert S._SVEGLIA.statistiche()["usate"] == 0
        assert S.statistiche_sveglia() is None
    finally:
        S._SVEGLIA.azzera()


def test_sveglia_col_canale_acceso_ascolto_scan_di_f5_non_parte(monkeypatch):
    """Una connessione sola: con ``OMEGA_LEGGE_CANALE`` la sveglia sulle righe
    la alza il client del canale; l'``AscoltoScan`` di F5 non si costruisce.
    La sveglia dalla UI resta collegata."""
    from Betfair.stream import sveglia_canale as SV

    monkeypatch.setenv(ENV, "1")
    monkeypatch.setenv(SV.ENV_OMEGA_SVEGLIA, "1")
    monkeypatch.setattr(S, "_ASCOLTO_SCAN", None)
    # (un'eccezione qui la ingoierebbe il ``try`` di ``_avvia_sveglia``: si conta)
    costruiti = []
    monkeypatch.setattr(SV, "AscoltoScan", lambda *a, **k: costruiti.append(a))
    registrate = []

    class CanaleUI:
        def set_sveglia(self, cb):
            registrate.append(cb)
    monkeypatch.setattr(S._lc, "get_channel", lambda: CanaleUI())
    S._avvia_sveglia()
    assert costruiti == [], "seconda connessione al canale dello scanner"
    assert S._ASCOLTO_SCAN is None
    assert registrate == [S._su_sveglia_dal_canale]


def test_sveglia_a_canale_spento_f5_resta_quella_di_prima(monkeypatch):
    from Betfair.stream import sveglia_canale as SV

    monkeypatch.delenv(ENV, raising=False)
    monkeypatch.setenv(SV.ENV_OMEGA_SVEGLIA, "1")
    monkeypatch.setattr(S, "_ASCOLTO_SCAN", None)
    costruiti = []

    class AscoltoFinto:
        url = "ws://127.0.0.1:47336"

        def __init__(self, *a, **k):
            costruiti.append((a, k))

        def avvia(self):
            return True
    monkeypatch.setattr(SV, "AscoltoScan", AscoltoFinto)
    monkeypatch.setattr(S._lc, "get_channel", lambda: None)
    S._avvia_sveglia()
    assert len(costruiti) == 1 and isinstance(S._ASCOLTO_SCAN, AscoltoFinto)
