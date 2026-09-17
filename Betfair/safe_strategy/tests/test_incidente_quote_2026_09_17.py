"""INCIDENTE 17/09/2026 - il feed unico senza quote, per ore, con il badge verde.

Cosa era successo (referto: `Betfair/safe_strategy/INCIDENTE_QUOTE_TENNIS_2026-09-17.md`):

1. betfairlightweight, quando il messaggio porta solo ``marketDefinition`` e
   nessun ``rc``, crea i runner DALLA DEFINIZIONE (selection_id e status
   presenti, scalette VUOTE) e pubblica comunque il MarketBook
   (``streaming/cache.py:314-351`` + ``streaming/stream.py:211-215``).
   ``Scanner._apply_market_book`` lo accettava come aggiornamento di quote:
   SOVRASCRIVEVA le quote buone con ``null`` e faceva avanzare ``odds_ts_ms``.
2. Il fallback REST non partiva MAI, perche' "coperto" si decideva sulla salute
   del SOCKET (heartbeat ogni 5 s), non sulla consegna delle quote.
3. La risottoscrizione abbatteva l'UNICA connessione ogni 30 s, per ore.
4. Lo stato taceva (``last_error`` null, badge STREAM verde) e il bot pure.

I FINTI DI QUESTO FILE SONO VERI: ``MarketBook``/``RunnerBook`` di
betfairlightweight, costruiti con le stesse chiavi che la cache dello streaming
produce - ``ex.availableToBack = []`` e' esattamente cio' che arriva su un
messaggio di sola definizione.

Ogni test di questo file e' stato FALSIFICATO: vedi in coda
``test_falsificazione_*``, che rimettono il comportamento vecchio e pretendono
il rosso.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pytest

from betfairlightweight.resources.bettingresources import MarketBook

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import scanner
from Betfair.safe_strategy import service
from Betfair.safe_strategy import stream as ST

RADICE = Path(__file__).resolve().parents[3]

# La funzione VERA della guardia, presa PRIMA di qualunque patch.
_VERO_FLUMINE_CARICATO = service.Scanner.flumine_caricato


@pytest.fixture(autouse=True)
def scanner_senza_flumine(monkeypatch):
    """In QUESTO file `bot_service` (importato in testa) tira dentro flumine, e
    in produzione il processo dello scanner gira senza. Senza questa fixture la
    guardia sarebbe sempre accesa nel processo di pytest e `last_error`
    direbbe "flumine caricato" al posto dell'allarme quote che i test misurano.
    I test della guardia usano `_VERO_FLUMINE_CARICATO`, che la scavalca.
    """
    monkeypatch.setattr(service.Scanner, "flumine_caricato", lambda self: False)


# ===========================================================================
# I FINTI: le classi VERE di betfairlightweight
# ===========================================================================
def runner_dict(sid: int, back=None, lay=None, status: str = "ACTIVE") -> dict:
    """Il runner come lo serializza ``RunnerBookCache``.

    ``back``/``lay`` = (prezzo, size) oppure None. None su entrambi = il runner
    nato dalla DEFINIZIONE: id e stato ci sono, la scaletta e' vuota.
    """
    return {
        "selectionId": int(sid),
        "status": status,
        "handicap": 0.0,
        "lastPriceTraded": None,
        "totalMatched": 0.0,
        "ex": {
            "availableToBack": ([{"price": back[0], "size": back[1]}] if back else []),
            "availableToLay": ([{"price": lay[0], "size": lay[1]}] if lay else []),
            "tradedVolume": [],
        },
    }


class _Livello:
    """Un livello del ladder come lo vede la PRODUZIONE: ``.price`` e ``.size``.

    ATTENZIONE: importare ``flumine`` (lo fa ``bot_service``, importato qui
    sopra) RITOCCA betfairlightweight per tutto il processo -
    ``flumine/__init__.py:13`` sostituisce ``RunnerBookEX`` con una classe che
    lascia i livelli come DIZIONARI. Il processo dello SCANNER non importa
    flumine (test di contratto ``test_lo_scanner_non_importa_flumine``), quindi
    in produzione i livelli hanno ``.price``: se il finto usasse i dizionari di
    flumine, ``price_pair`` leggerebbe None su tutto e questi test
    "passerebbero" misurando il difetto sbagliato.
    E' la stessa ragione per cui il banco comune riespone il ladder
    (``stream/backtest/banco_comune.py``, ``_Livello``/``_VistaEx``).
    """

    __slots__ = ("price", "size")

    def __init__(self, price, size):
        self.price, self.size = price, size


class _Ex:
    """``runner.ex`` nella forma di produzione."""

    __slots__ = ("available_to_back", "available_to_lay", "traded_volume")

    def __init__(self, atb, atl):
        self.available_to_back = [_Livello(l["price"], l["size"]) for l in atb]
        self.available_to_lay = [_Livello(l["price"], l["size"]) for l in atl]
        self.traded_volume = []


def book(market_id: str, runners: list, *, status: str = "OPEN", inplay: bool = True,
         total_matched: float = 0.0) -> MarketBook:
    """Un MarketBook vero, nella forma in cui lo stream lo consegna."""
    mb = MarketBook(marketId=market_id, status=status, inplay=inplay,
                    totalMatched=total_matched, betDelay=0, runners=runners)
    for rb, grezzo in zip(mb.runners, runners):
        rb.ex = _Ex(grezzo["ex"]["availableToBack"], grezzo["ex"]["availableToLay"])
    return mb


def test_i_finti_sono_la_forma_vera_dello_stream():
    """Cintura: se betfairlightweight cambiasse forma, questi test mentirebbero."""
    b = book("1.100", [runner_dict(11, back=(2.5, 100.0)), runner_dict(22)])
    assert b.market_id == "1.100" and b.status == "OPEN" and b.inplay is True
    assert [r.selection_id for r in b.runners] == [11, 22]
    assert b.runners[1].status == "ACTIVE"          # viene dalla DEFINIZIONE
    assert not b.runners[1].ex.available_to_back    # la scaletta e' VUOTA
    assert scanner.price_pair(b.runners[0].ex)["back"] == 2.5
    assert scanner.price_pair(b.runners[1].ex) == {
        "back": None, "lay": None, "back_size": None, "lay_size": None}


def test_lo_scanner_non_importa_flumine():
    """CONTRATTO. ``flumine/__init__.py:13`` sostituisce ``RunnerBookEX`` con la
    sua versione pigra, che lascia i livelli del ladder come DIZIONARI, e
    ``scanner.best_price`` legge ``levels[0].price`` dentro un ``except`` che
    torna None: un import di flumine nel processo dello scanner farebbe
    diventare ``None`` OGNI prezzo, in silenzio e per sempre - cioe' l'incidente
    del 17/09 in forma permanente. La prova del danno e' gia' scritta
    (``stream/tests/test_banco_comune_2026_09_16.py::
    test_il_ladder_di_flumine_e_muto_per_lo_scanner``); qui si vincola la
    condizione che la tiene innocua: il servizio dello scanner non lo importa.
    """
    import subprocess
    import sys

    # PERCORSO VIVO, non il solo import: flumine entrava a RUNTIME, al primo
    # giro che serviva l'Atlante Hazard (`Scanner.opp_model`), ed e' per questo
    # che la mattina - senza calcio in gioco - il feed stava bene. Un test sul
    # solo `import` sarebbe stato verde anche il 17/09.
    codice = (
        "import sys;"
        "from Betfair.safe_strategy.service import Scanner;"
        "s = Scanner(api_client=None, dry=True, use_stream=False);"
        "m = s.opp_model();"
        "print('ATLANTE', m is not None);"
        "print('FLUMINE', 'flumine' in sys.modules);"
        "print('GUARDIA', s.flumine_caricato())"
    )
    res = subprocess.run([sys.executable, "-c", codice], capture_output=True,
                         text=True, cwd=str(RADICE), timeout=300)
    assert res.returncode == 0, res.stderr[-1200:]
    righe = dict(r.split(" ", 1) for r in res.stdout.strip().splitlines()
                 if r.startswith(("ATLANTE", "FLUMINE", "GUARDIA")))
    assert righe.get("ATLANTE") == "True", (
        "l'Atlante non si carica piu': la fix ha rotto il modello opportunita'. " + res.stdout)
    assert righe.get("FLUMINE") == "False", (
        "flumine e' entrato nel processo del feed caricando l'Atlante: e' "
        "l'incidente del 17/09. " + res.stdout)
    assert righe.get("GUARDIA") == "False"


def test_flumine_caricato_legge_davvero_sys_modules():
    """La guardia non e' decorativa: legge `sys.modules`.

    In QUESTO processo flumine c'e' per davvero (lo importa `bot_service`, in
    testa al file): la guardia lo vede. Tolto, non lo vede piu'.
    """
    import unittest.mock as _mock

    scan = scanner_tennis()
    assert "flumine" in sys.modules, "il finto non regge: qui flumine deve esserci"
    assert _VERO_FLUMINE_CARICATO(scan) is True
    with _mock.patch.dict(service.sys.modules):
        del service.sys.modules["flumine"]
        assert _VERO_FLUMINE_CARICATO(scan) is False


def test_guardia_runtime_flumine_denuncia(monkeypatch):
    """Se flumine e' nel processo: WARNING una volta sola, messaggio sempre."""
    scan = scanner_tennis()
    assert scan.controlla_flumine() is None          # guardia spenta: niente
    monkeypatch.setattr(service.Scanner, "flumine_caricato", lambda self: True)
    assert scan.controlla_flumine() == "flumine caricato nel processo del feed"
    assert scan.flumine_detto is True
    assert scan.controlla_flumine() == "flumine caricato nel processo del feed"


def test_flumine_ha_la_precedenza_su_last_error(monkeypatch):
    """E' la CAUSA, non il sintomo: se c'e', lo dice prima delle quote assenti."""
    scan, _ = scanner_per_tick(eta_prezzo_s=None)
    scan.rilevante_da_mono["1.100"] = time.monotonic() - 40.0
    monkeypatch.setattr(service.Scanner, "flumine_caricato", lambda self: True)
    scan.tick()
    assert scan.last_error == "flumine caricato nel processo del feed"


def test_status_riporta_flumine_caricato(monkeypatch):
    scritti: list = []
    monkeypatch.setattr(service.scan_db, "upsert_status", lambda p: scritti.append(p))
    scan = scanner_tennis()
    scan.dry = False
    scan.publish_status(0)
    assert "flumine_caricato" in scritti[-1]
    assert scritti[-1]["flumine_caricato"] == scan.flumine_caricato()


def test_il_finto_parla_la_lingua_della_produzione():
    """Il ladder del finto ha ``.price``/``.size``, come in produzione."""
    b = book("1.100", CON_PREZZI)
    assert scanner.price_pair(b.runners[0].ex) == {
        "back": 1.30, "lay": 1.32, "back_size": 500.0, "lay_size": 400.0}
    assert b.runners[0].ex.available_to_back[0].price == 1.30


# ===========================================================================
# Lo scanner di prova
# ===========================================================================
def scanner_tennis() -> service.Scanner:
    """Uno Scanner con UNA partita di tennis in gioco e il suo MATCH_ODDS."""
    scan = service.Scanner(api_client=None, dry=True, use_stream=False)
    meta = {
        "event_id": "t1", "market_id": "1.100", "event_name": "Rossi v Bianchi",
        "open_date": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
        "competition": "ATP", "runners": [],
        "sides": {"p1": 11, "p2": 22},
    }
    scan.sports["tennis"].metas = {"t1": meta}
    scan.events["t1"] = {"sport": "tennis", "inplay": True, "mo_status": "OPEN"}
    scan._rebuild_market_index()
    return scan


CON_PREZZI = [runner_dict(11, back=(1.30, 500.0), lay=(1.32, 400.0)),
              runner_dict(22, back=(4.00, 120.0), lay=(4.40, 90.0))]
SOLO_DEFINIZIONE = [runner_dict(11), runner_dict(22)]


# ===========================================================================
# 1. un book di sola definizione NON e' un aggiornamento di quote
# ===========================================================================
def test_book_di_sola_definizione_non_cancella_le_quote():
    scan = scanner_tennis()
    scan._apply_market_book(book("1.100", CON_PREZZI), dallo_stream=True)
    buone = dict(scan.events["t1"]["odds"])
    ts = scan.events["t1"]["odds_ts_ms"]
    assert buone["p1"]["back"] == 1.30 and buone["p2"]["lay"] == 4.40

    time.sleep(0.002)
    scan._apply_market_book(book("1.100", SOLO_DEFINIZIONE), dallo_stream=True)

    assert scan.events["t1"]["odds"] == buone, "le quote buone sono state cancellate"
    assert scan.events["t1"]["odds_ts_ms"] == ts, "odds_ts_ms avanzato senza prezzi"
    assert scan.book_vuoti == {"1.100": 1}
    # la DEFINIZIONE si applica comunque: e' l'unica cosa che quel book porta
    assert scan.events["t1"]["mo_status"] == "OPEN"
    assert scan.events["t1"]["inplay"] is True


def test_sequenza_prezzi_definizione_prezzi():
    """La sequenza ESATTA dell'incidente: prezzi -> sola definizione -> prezzi.

    In mezzo le quote non devono mai diventare nulle e ``odds_ts_ms`` non deve
    muoversi; alla ripresa dei prezzi riparte tutto normalmente.
    """
    scan = scanner_tennis()
    scan._apply_market_book(book("1.100", CON_PREZZI), dallo_stream=True)
    ts1 = scan.events["t1"]["odds_ts_ms"]

    for _ in range(5):                       # il blackout dura, i book arrivano
        time.sleep(0.001)
        scan._apply_market_book(book("1.100", SOLO_DEFINIZIONE), dallo_stream=True)
        odds = scan.events["t1"]["odds"]
        assert odds["p1"]["back"] == 1.30 and odds["p2"]["back"] == 4.00
        assert scan.events["t1"]["odds_ts_ms"] == ts1

    assert sum(scan.book_vuoti.values()) == 5
    time.sleep(0.002)
    nuovi = [runner_dict(11, back=(1.25, 500.0), lay=(1.27, 400.0)),
             runner_dict(22, back=(4.50, 120.0), lay=(5.00, 90.0))]
    scan._apply_market_book(book("1.100", nuovi), dallo_stream=True)
    assert scan.events["t1"]["odds"]["p1"]["back"] == 1.25
    assert scan.events["t1"]["odds_ts_ms"] > ts1


def test_book_vuoto_non_fa_avanzare_odds_ts_ms():
    """Solo book vuoti dall'inizio: la riga dice onestamente "quote assenti",
    ma senza un timestamp di prezzo che non le spetta."""
    scan = scanner_tennis()
    for _ in range(3):
        scan._apply_market_book(book("1.100", SOLO_DEFINIZIONE), dallo_stream=True)
    ev = scan.events["t1"]
    assert ev["odds"] == {"p1": {"back": None, "lay": None, "back_size": None,
                                 "lay_size": None, "selection_id": 11, "ltp": None},
                          "p2": {"back": None, "lay": None, "back_size": None,
                                 "lay_size": None, "selection_id": 22, "ltp": None}}
    assert ev.get("odds_ts_ms") is None
    assert ev["odds_vuote_ms"] > 0
    assert sum(scan.book_vuoti.values()) == 3


def test_book_vuoto_non_cancella_il_correct_score_ne_le_linee_a_gol():
    """Stesso difetto su ``_apply_cs_book`` e ``_apply_opp_book``: sono i
    blocchi su cui Omega si copre e su cui Mike esce."""
    scan = scanner_tennis()
    scan.events["e9"] = {"sport": "calcio", "inplay": True, "mo_status": "OPEN"}
    scan.cs_markets["e9"] = {"market_id": "1.CS", "names": {91: "Any Other Home Win"}}
    scan.opp_markets["e9"] = {"1.OU25": {"market_id": "1.OU25",
                                         "market_type": "OVER_UNDER_25", "line": 2.5,
                                         "names": {81: "Over 2.5 Goals"}}}
    scan._rebuild_market_index()

    scan._apply_market_book(book("1.CS", [runner_dict(91, back=(44.0, 3.5))]),
                            dallo_stream=True)
    scan._apply_market_book(book("1.OU25", [runner_dict(81, back=(2.2, 300.0))]),
                            dallo_stream=True)
    cs_buono = dict(scan.events["e9"]["cs"])
    ou_buono = dict(scan.events["e9"]["opp"]["1.OU25"])

    scan._apply_market_book(book("1.CS", [runner_dict(91)]), dallo_stream=True)
    scan._apply_market_book(book("1.OU25", [runner_dict(81)]), dallo_stream=True)

    assert scan.events["e9"]["cs"]["selections"] == cs_buono["selections"]
    assert scan.events["e9"]["cs"]["any_other_home"] == cs_buono["any_other_home"]
    assert scan.events["e9"]["opp"]["1.OU25"]["selections"] == ou_buono["selections"]
    assert scan.events["e9"]["opp"]["1.OU25"]["ts_ms"] == ou_buono["ts_ms"]
    assert scan.book_vuoti == {"1.CS": 1, "1.OU25": 1}


def test_il_rest_non_rende_coperto_un_mercato():
    """Un prezzo preso via REST non deve far credere che lo STREAM funzioni:
    il REST e' il fallback, non la fonte."""
    scan = scanner_tennis()
    scan._apply_market_book(book("1.100", CON_PREZZI))          # REST
    assert "1.100" not in scan.stream_price_mono
    assert "1.100" in scan.price_mono                            # ma le quote ci sono
    scan._apply_market_book(book("1.100", CON_PREZZI), dallo_stream=True)
    assert "1.100" in scan.stream_price_mono


# ===========================================================================
# 2. la copertura si misura sui BOOK, non sugli heartbeat
# ===========================================================================
class PoolFinto:
    """Un pool di stream che dichiara coperti i suoi mercati (shard sano)."""

    def __init__(self, ids, serve: bool = True):
        self.ids = set(ids)
        self.serve = serve
        self.capacity = 720
        self.impostati: list = []

    def set_markets(self, ranked): self.impostati.append(list(ranked))
    def drain(self): return []
    def covered_ids(self): return set(self.ids) if self.serve else set()
    def subscribed_ids(self): return set(self.ids)
    def healthy(self): return True
    def serving(self): return self.serve
    def active_connections(self): return 1
    def stato_shard(self): return [{"i": 0, "subscribed": len(self.ids)}]
    def stop(self): pass


def scanner_per_tick(eta_prezzo_s: Optional[float]) -> "tuple[service.Scanner, list]":
    """Scanner pronto per UN tick, con lo stream che copre 1.100.

    ``eta_prezzo_s`` = da quanti secondi lo stream ha dato l'ultimo prezzo di
    quel mercato; None = non l'ha mai dato.
    """
    scan = scanner_tennis()
    ora = time.monotonic()
    for st in scan.sports.values():
        st.catalogue_ts = ora            # catalogo fresco: nessuna chiamata
        st.books_ts = -1e9               # cadenza del poll gia' scaduta
    scan.scores_ts = ora                 # niente IPS
    scan.timelines_ts = ora
    scan.status_ts = ora
    scan.stream = PoolFinto({"1.100"})
    if eta_prezzo_s is not None:
        scan.stream_price_mono["1.100"] = ora - eta_prezzo_s
        scan.price_mono["1.100"] = ora - eta_prezzo_s
    chiamate: list = []
    scan.poll_books = lambda sport, ids: chiamate.append((sport, list(ids)))  # type: ignore[method-assign]
    return scan, chiamate


def test_mercato_senza_prezzi_torna_al_poll_rest():
    """Shard SANO e sottoscritto, ma nessun book CON PREZZI da 25 s: il tick
    deve mandare quel mercato al poll REST.

    E' il test che il 17/09 non c'era e che avrebbe impedito l'incidente.
    """
    scan, chiamate = scanner_per_tick(eta_prezzo_s=25.0)
    scan.tick()
    assert ("tennis", ["1.100"]) in chiamate
    # a 25 s il REST parte (copertura, 20 s) ma NON c'e' ancora allarme (30 s):
    # il badge segue l'ALLARME, non la semplice scopertura. A 40 s cambia.
    assert scan.last_source == "stream"
    scan.stream_price_mono["1.100"] = scan.price_mono["1.100"] = time.monotonic() - 40.0
    scan.sports["tennis"].books_ts = -1e9
    scan.tick()
    assert scan.last_source == "rest", "il badge deve dire REST quando si ripiega"
    assert scan.mercati_allarme == ["1.100"]


def test_mercato_mai_visto_va_al_rest():
    """Un mercato appena sottoscritto non ha ancora un prezzo: per un giro lo
    copre il REST. Mai un buco dati."""
    scan, chiamate = scanner_per_tick(eta_prezzo_s=None)
    scan.tick()
    assert ("tennis", ["1.100"]) in chiamate


def test_mercato_con_prezzi_recenti_non_spreca_rest():
    """L'altra direzione: se lo stream sta davvero servendo, il REST tace."""
    scan, chiamate = scanner_per_tick(eta_prezzo_s=2.0)
    scan.tick()
    assert chiamate == []
    assert scan.last_source == "stream"


def test_shard_con_soli_heartbeat_non_e_serving(monkeypatch):
    """``healthy()`` (socket) resta vero, ``serving()`` (book) no."""
    shard = ST.StreamShard(client=None, index=0)
    shard._stream = object()
    shard._touch()                                   # un heartbeat, nessun book
    assert shard.healthy() is True
    assert shard.serving() is False                  # nessun book: MAI serving

    shard.queue.put([object()])
    shard._desired = {"1.1"}
    shard._subscribed = {"1.1"}
    assert len(shard.drain()) == 1
    assert shard.serving() is True and shard.books == 1

    # passano 25 s senza un solo book: gli heartbeat continuano
    finto = time.monotonic() + 25.0
    monkeypatch.setattr(ST.time, "monotonic", lambda: finto)
    shard._last_msg_mono = finto - 1.0               # socket vivissimo
    assert shard.healthy() is True
    assert shard.serving() is False


def test_covered_ids_esclude_lo_shard_che_non_consegna():
    pool = ST.MarketStreamPool(client=None, max_conns=1, per_conn=10)
    shard = pool.shards[0]
    shard._stream = object()
    shard._desired = {"1.1"}
    shard._subscribed = {"1.1"}
    shard._touch()
    assert shard.healthy() is True
    assert pool.covered_ids() == set(), "un socket vivo non e' una quota"
    shard.queue.put([object()])
    shard.drain()
    assert pool.covered_ids() == {"1.1"}


def test_run_non_marca_sano_prima_di_ricevere():
    """``_touch()`` prematuro: lo shard si dichiarava sano (e quindi i suoi
    mercati coperti) senza aver ricevuto un solo messaggio."""
    import inspect
    src = inspect.getsource(ST.StreamShard._run)
    assert "self._touch()" not in src, "la salute non si dichiara: si riceve"
    # il listener la marca al PRIMO messaggio vero, e solo li'
    assert "self._touch" in src


# ===========================================================================
# 3. la risottoscrizione non costa la connessione
# ===========================================================================
class StreamFinto:
    """Un BetfairStream finto con le stesse porte che il codice tocca."""

    def __init__(self, vivo: bool = True):
        self._running = vivo
        self._socket = object() if vivo else None
        self.sottoscrizioni: list = []
        self.stop_chiamati = 0

    def subscribe_to_markets(self, market_filter=None, market_data_filter=None,
                             conflate_ms=None, heartbeat_ms=None, **kw):
        self.sottoscrizioni.append({
            "ids": list(market_filter.get("marketIds") or []),
            "conflate_ms": conflate_ms, "heartbeat_ms": heartbeat_ms,
            "fields": list(market_data_filter.get("fields") or []),
        })

    def stop(self):
        self.stop_chiamati += 1
        self._running = False
        self._socket = None


def shard_con_stream(desired, subscribed, vivo=True) -> "tuple[ST.StreamShard, StreamFinto]":
    shard = ST.StreamShard(client=None, index=0)
    st = StreamFinto(vivo)
    shard._stream = st
    shard._desired = set(desired)
    shard._subscribed = set(subscribed)
    shard._last_resub = time.monotonic() - (ST._RESUB_MIN_INTERVAL + 1.0)
    return shard, st


def test_resubscribe_solo_per_mercati_nuovi():
    """Il set perde mercati ma non ne aggiunge: nessuno strappo.

    Era questo a far rifare l'UNICA connessione ogni 30 s per ore, con il
    calcio in gioco (linee O/U, candidati CS/HT, partite di Mike).
    """
    shard, st = shard_con_stream({"1.1"}, {"1.1", "1.2"})
    shard.maybe_resubscribe()
    assert st.sottoscrizioni == [] and st.stop_chiamati == 0
    assert shard._subscribed == {"1.1", "1.2"}


def test_resubscribe_a_caldo_non_abbatte_la_connessione():
    """Un mercato NUOVO va sottoscritto - ma sullo stesso socket vivo."""
    shard, st = shard_con_stream({"1.1", "1.2"}, {"1.1"})
    shard.maybe_resubscribe()
    assert st.stop_chiamati == 0, "la connessione e' stata abbattuta"
    assert len(st.sottoscrizioni) == 1
    sub = st.sottoscrizioni[0]
    assert sub["ids"] == ["1.1", "1.2"]
    # gli stessi identici parametri della prima sottoscrizione
    assert sub["conflate_ms"] == ST._CONFLATE_MS
    assert sub["heartbeat_ms"] == ST._HEARTBEAT_MS
    assert sub["fields"] == ["EX_BEST_OFFERS", "EX_MARKET_DEF"]
    assert shard._subscribed == {"1.1", "1.2"}


def test_resubscribe_su_socket_morto_ricostruisce():
    """Se il socket non e' connesso, ``_send`` aprirebbe e autenticherebbe dal
    thread sbagliato lasciando una connessione MUTA: si ricostruisce."""
    shard, st = shard_con_stream({"1.1", "1.2"}, {"1.1"}, vivo=False)
    shard.maybe_resubscribe()
    assert st.sottoscrizioni == []
    assert st.stop_chiamati == 1          # ripiego: il thread rifa' tutto


def test_resubscribe_rispetta_il_throttle():
    shard, st = shard_con_stream({"1.1", "1.2"}, {"1.1"})
    shard._last_resub = time.monotonic()          # appena fatto
    shard.maybe_resubscribe()
    assert st.sottoscrizioni == [] and st.stop_chiamati == 0


def test_resubscribe_quando_i_mercati_in_piu_sono_tanti():
    """Troppi mercati morti in subscription pesano sul limite per connessione."""
    vecchi = {f"1.{i}" for i in range(ST._RESUB_EXTRA_TOLLERATI + 5)}
    shard, st = shard_con_stream({"1.1"}, vecchi | {"1.1"})
    shard.maybe_resubscribe()
    assert len(st.sottoscrizioni) == 1 and st.stop_chiamati == 0


def test_run_non_pubblica_una_connessione_muta():
    """``self._stream`` va pubblicato DOPO la subscription.

    Prima: ``_kick()`` caduto fra ``create_stream`` e ``start()`` metteva
    ``_running=False``; ``start()`` riapriva e riautenticava il socket SENZA
    rimandare la marketSubscription - viva, autenticata e muta.
    """
    visti: list = []
    ordine: list = []

    class StreamDelRun(StreamFinto):
        """Come il vero: ``start()`` blocca finche' non lo si ferma."""

        def __init__(self, shard):
            super().__init__()
            self._shard = shard

        def start(self):
            ordine.append(("start", self._shard._stream is self))
            self._shard._stop = True                # un solo giro del loop

    class ClientFinto:
        def __init__(self):
            self.shard = None
            padre = self

            class streaming:
                @staticmethod
                def create_stream(listener=None):
                    st = StreamDelRun(padre.shard)
                    ordine.append(("create", padre.shard._stream))
                    visti.append(st)
                    return st

            self.streaming = streaming

    client = ClientFinto()
    shard = ST.StreamShard(client=client, index=0)
    client.shard = shard

    vero_sub = ST.StreamShard._subscribe

    def sub_spia(self, stream, ids):
        ordine.append(("subscribe", self._stream))
        return vero_sub(self, stream, ids)

    ST.StreamShard._subscribe = sub_spia            # type: ignore[assignment]
    try:
        shard._desired = {"1.1"}
        shard._run()
    finally:
        ST.StreamShard._subscribe = vero_sub        # type: ignore[assignment]

    assert ordine[0] == ("create", None)
    assert ordine[1] == ("subscribe", None), \
        "_stream pubblicato PRIMA della subscription: finestra per una connessione muta"
    assert ordine[2] == ("start", True), "start() senza uno stream pubblicato"
    assert visti[0].sottoscrizioni[0]["ids"] == ["1.1"]


# ===========================================================================
# 4. lo stato dice la verita'
# ===========================================================================
def test_status_denuncia_le_quote_assenti(monkeypatch):
    scan, _chiamate = scanner_per_tick(eta_prezzo_s=None)
    ora = time.monotonic()
    # il mercato e' rilevante da 40 s e non ha MAI avuto un prezzo
    scan.rilevante_da_mono["1.100"] = ora - 40.0
    for _ in range(4):
        scan._apply_market_book(book("1.100", SOLO_DEFINIZIONE), dallo_stream=True)
    scan.tick()

    assert scan.mercati_senza_quote == ["1.100"]
    assert scan.last_error and scan.last_error.startswith("quote assenti da ")
    assert "su 1 mercati" in scan.last_error

    scritti: list = []
    monkeypatch.setattr(service.scan_db, "upsert_status", lambda p: scritti.append(p))
    scan.dry = False
    scan.publish_status(1)
    st = scritti[-1]
    assert st["stream_books_vuoti"] == 4
    assert st["stream_mercati_senza_quote"] == ["1.100"]
    assert st["stream_mercati_senza_quote_n"] == 1
    assert st["stream_senza_quote_eta_s"] >= 40.0
    assert st["last_error"] == scan.last_error
    assert st["source"] == "rest"
    assert st["stream_shards"] == [{"i": 0, "subscribed": 1}]


def test_status_tace_quando_le_quote_ci_sono():
    scan, _ = scanner_per_tick(eta_prezzo_s=2.0)
    scan.tick()
    assert scan.mercati_senza_quote == []
    assert scan.last_error is None
    assert scan.allarme_quote() is None


def test_stato_shard_riporta_le_eta():
    shard = ST.StreamShard(client=None, index=3)
    shard._desired = {"1.1", "1.2"}
    shard._subscribed = {"1.1"}
    st = shard.stato()
    assert st["i"] == 3 and st["desired"] == 2 and st["subscribed"] == 1
    assert st["books"] == 0
    assert st["eta_book_s"] is None and st["eta_msg_s"] is None
    assert st["eta_resub_s"] is None
    shard._touch()
    shard.queue.put([object()])
    shard.drain()
    st = shard.stato()
    assert st["books"] == 1
    assert 0.0 <= st["eta_book_s"] < 5.0 and 0.0 <= st["eta_msg_s"] < 5.0


# ===========================================================================
# 5. il bot lo DICE
# ===========================================================================
class DbFinto:
    def __init__(self):
        self.attivita: list = []
        self.opps: list = []

    def log(self, kind, payload):
        self.attivita.append((kind, dict(payload)))

    def upsert_opportunities(self, righe):
        self.opps.extend(righe)


class ModelloTennisFinto:
    def __init__(self):
        self.chiamate = 0

    def evaluate(self, payload, now_ts):
        self.chiamate += 1
        return []


class ModTennisFinto:
    def __init__(self, modello):
        self._m = modello

    def TennisOpportunityModel(self, params):  # noqa: N802 - nome del vero
        return self._m


def riga_tennis(con_prezzi: bool, event_id: str = "2.1") -> dict:
    p1 = ({"selection_id": 11, "back": 1.3, "lay": 1.32, "back_size": 500.0,
           "lay_size": 500.0} if con_prezzi else
          {"selection_id": 11, "back": None, "lay": None, "back_size": None,
           "lay_size": None})
    p2 = ({"selection_id": 12, "back": 4.0, "lay": 4.4, "back_size": 500.0,
           "lay_size": 500.0} if con_prezzi else
          {"selection_id": 12, "back": None, "lay": None, "back_size": None,
           "lay_size": None})
    return {"event_id": event_id, "sport": "tennis",
            "payload": {"event_name": "P1 v P2", "inplay": True, "mo_market_id": "mt",
                        "mo_status": "OPEN", "odds": {"p1": p1, "p2": p2},
                        "sets": {"p1": 1, "p2": 0}, "games": {"p1": 4, "p2": 2}}}


def esegui_opps(db, righe, modello, adesso) -> dict:
    return S.process_opportunities(
        db=db, market=None, rows=righe, params={"opps_interval_s": 0.0},
        model=None, opp_mod=None, mode="paper", now=adesso,
        state={"last_ts": 0.0, "hashes": {}},
        extra={"anomaly": None, "combos": None, "tennis": ModTennisFinto(modello)},
        scanner_ts=adesso.timestamp(), scanner_ts_known=True)


def test_skip_quote_assenti_tennis():
    """La riga c'e', i prezzi no: UN solo skip per evento, e ``evaluate`` non
    viene nemmeno chiamata."""
    S._SKIP_LOG_STATE.clear()
    db, modello = DbFinto(), ModelloTennisFinto()
    t0 = datetime.now(timezone.utc)
    esegui_opps(db, [riga_tennis(False)], modello, t0)
    skip = [p for k, p in db.attivita if k == "skip"]
    assert len(skip) == 1
    assert skip[0]["reason"] == "quote_assenti" and skip[0]["sport"] == "tennis"
    assert skip[0]["event_id"] == "2.1"
    assert modello.chiamate == 0

    # dedup: entro il minuto non si ripete
    esegui_opps(db, [riga_tennis(False)], modello, t0 + timedelta(seconds=30))
    assert len([p for k, p in db.attivita if k == "skip"]) == 1
    # ma dopo il minuto si ridice: un silenzio non e' un'informazione
    esegui_opps(db, [riga_tennis(False)], modello, t0 + timedelta(seconds=61))
    assert len([p for k, p in db.attivita if k == "skip"]) == 2


def test_skip_quote_assenti_non_scatta_con_i_prezzi():
    S._SKIP_LOG_STATE.clear()
    db, modello = DbFinto(), ModelloTennisFinto()
    esegui_opps(db, [riga_tennis(True)], modello, datetime.now(timezone.utc))
    assert [p for k, p in db.attivita if k == "skip"] == []
    assert modello.chiamate == 1


def test_skip_quote_assenti_calcio():
    """Stesso silenzio, altra strada: senza prezzi il cecchino non rivaluta
    nemmeno la riga (gate su ``odds_ts_ms``, congelato dai book vuoti)."""
    S._SKIP_LOG_STATE.clear()
    db = DbFinto()
    riga = {"event_id": "1.1", "sport": "calcio",
            "payload": {"event_name": "Home v Away", "inplay": True, "minute": 30,
                        "odds": {"home": {"back": None, "lay": None},
                                 "draw": {"back": None, "lay": None},
                                 "away": {"back": None, "lay": None}},
                        "ou": [{"market_id": "ou25", "line": 2.5, "selections": [
                            {"selection_id": 47972, "name": "Over 2.5 Goals",
                             "back": None, "lay": None}]}]}}

    class ModelloCalcioFinto:
        def __init__(self): self.chiamate = 0
        def evaluate(self, *a, **kw):
            self.chiamate += 1
            return []

    modello = ModelloCalcioFinto()
    S.process_opportunities(
        db=db, market=None, rows=[riga], params={"opps_interval_s": 0.0},
        model=modello, opp_mod=object(), mode="paper",
        now=datetime.now(timezone.utc), state={"last_ts": 0.0, "hashes": {}},
        extra={"anomaly": None, "combos": None, "tennis": None},
        scanner_ts=0.0, scanner_ts_known=True)
    skip = [p for k, p in db.attivita if k == "skip"]
    assert len(skip) == 1 and skip[0]["reason"] == "quote_assenti"
    assert skip[0]["sport"] == "calcio"
    assert modello.chiamate == 0


def test_ha_quote_riconosce_i_mercati_a_gol():
    """Una partita di calcio puo' avere SOLO i mercati a gol: restringere il
    controllo al 1X2 spegnerebbe il motore su quelle righe."""
    assert S._ha_quote({"odds": {"home": {"back": None}},
                        "ou": [{"selections": [{"back": 2.2}]}]}) is True
    assert S._ha_quote({"odds": {}, "ou": [{"selections": [{"back": None,
                                                            "lay": None}]}]}) is False
    assert S._ha_quote({}) is False
    assert S._ha_quote({"odds": {"p1": {"lay": 1.32}}}) is True


def decisione_uscita() -> "S.XE.ExitDecision":
    """Una ExitDecision con la firma VERA del modulo uscite."""
    return S.XE.ExitDecision(kind="loss", reason="perdita", not_before_ts=0.0)


class DbTrade(DbFinto):
    def update_trade(self, tid, **kw):
        pass


def test_exit_wait_prezzi_non_nel_feed_si_ripete():
    """Prezzi assenti per 3 minuti: almeno 3 ``exit_wait``, non uno solo.

    Il 17/09 ``prezzi_non_nel_feed`` e' stato scritto UNA volta alle 12:47 e poi
    piu' niente, mentre le uscite restavano ferme per ore. Un'attesa che non si
    ripete e' indistinguibile da un'attesa finita.
    """
    db = DbTrade()
    trade = {"id": 7, "meta": {}}
    decisione = decisione_uscita()
    t0 = 1_000_000.0
    for i in range(7):                       # ogni 30 s per 3 minuti
        S._exit_wait(db, trade, trade["meta"], decisione, "prezzi_non_nel_feed",
                     t0 + i * 30.0)
    attese = [p for k, p in db.attivita if k == "exit_wait"]
    assert len(attese) >= 4                  # 0s, 60s, 120s, 180s
    assert all(p["wait"] == "prezzi_non_nel_feed" for p in attese)
    assert attese[0]["ripetuto"] is False and attese[1]["ripetuto"] is True


def test_exit_wait_non_fa_rumore_a_ogni_ciclo():
    """L'altra direzione: dentro il minuto NON si ripete."""
    db = DbTrade()
    trade = {"id": 7, "meta": {}}
    decisione = decisione_uscita()
    for i in range(10):                      # dieci cicli in 20 s
        S._exit_wait(db, trade, trade["meta"], decisione, "prezzi_non_nel_feed",
                     1_000_000.0 + i * 2.0)
    assert len([p for k, p in db.attivita if k == "exit_wait"]) == 1


def test_exit_wait_cambio_motivo_subito():
    db = DbTrade()
    trade = {"id": 7, "meta": {}}
    decisione = decisione_uscita()
    S._exit_wait(db, trade, trade["meta"], decisione, "prezzi_non_nel_feed", 1000.0)
    S._exit_wait(db, trade, trade["meta"], decisione, "mercato_sospeso", 1001.0)
    motivi = [p["wait"] for k, p in db.attivita if k == "exit_wait"]
    assert motivi == ["prezzi_non_nel_feed", "mercato_sospeso"]


# ===========================================================================
# FALSIFICAZIONE - ogni guardia, tolta, deve far diventare rosso il suo test
# ===========================================================================
def test_falsificazione_senza_la_guardia_le_quote_si_cancellano(monkeypatch):
    """Tolta ``has_any_price``, il book di sola definizione torna a cancellare
    le quote e a far avanzare ``odds_ts_ms``: e' l'incidente del 17/09."""
    monkeypatch.setattr(scanner, "has_any_price", lambda *_a, **_kw: True)
    scan = scanner_tennis()
    scan._apply_market_book(book("1.100", CON_PREZZI), dallo_stream=True)
    ts = scan.events["t1"]["odds_ts_ms"]
    time.sleep(0.002)
    scan._apply_market_book(book("1.100", SOLO_DEFINIZIONE), dallo_stream=True)
    assert scan.events["t1"]["odds"]["p1"]["back"] is None   # cancellate
    assert scan.events["t1"]["odds_ts_ms"] > ts              # e dichiarate fresche


def test_falsificazione_copertura_sugli_heartbeat(monkeypatch):
    """Rimessa la copertura sul SOCKET (``covered_ids()`` nudo), il mercato
    senza prezzi resta "coperto" e il poll REST non parte mai."""
    scan, chiamate = scanner_per_tick(eta_prezzo_s=25.0)

    def copertura_vecchia(self, now_mono, rilevanti):
        self.mercati_senza_quote = []
        self.senza_quote_eta_s = 0.0
        return set(self.stream.covered_ids()), []

    monkeypatch.setattr(service.Scanner, "_aggiorna_copertura", copertura_vecchia)
    scan.tick()
    assert chiamate == [], "col vecchio criterio il REST non sarebbe mai partito"


def test_falsificazione_resubscribe_sulla_vecchia_condizione():
    """Con ``desired != _subscribed`` un set che PERDE mercati bastava a
    riaprire la connessione: e' lo strappo ogni 30 s per ore."""
    shard, st = shard_con_stream({"1.1"}, {"1.1", "1.2"})
    desired, subscribed = set(shard._desired), set(shard._subscribed)
    vecchia = desired != subscribed
    assert vecchia is True, "la vecchia condizione avrebbe risottoscritto"
    shard.maybe_resubscribe()
    assert st.stop_chiamati == 0 and st.sottoscrizioni == []


def test_falsificazione_serving_su_healthy(monkeypatch):
    """Se ``serving()`` tornasse a essere ``healthy()``, uno shard con soli
    heartbeat coprirebbe di nuovo tutti i suoi mercati."""
    pool = ST.MarketStreamPool(client=None, max_conns=1, per_conn=10)
    shard = pool.shards[0]
    shard._stream = object()
    shard._desired = {"1.1"}
    shard._subscribed = {"1.1"}
    shard._touch()
    assert pool.covered_ids() == set()
    monkeypatch.setattr(ST.StreamShard, "serving", ST.StreamShard.healthy)
    assert pool.covered_ids() == {"1.1"}


def test_falsificazione_exit_wait_una_volta_sola(monkeypatch):
    """Rimesso l'intervallo a infinito, ``prezzi_non_nel_feed`` torna a
    scriversi una volta sola per tutta la durata del blackout."""
    monkeypatch.setattr(S, "_EXIT_WAIT_RILOG_S", 1e12)
    db = DbTrade()
    trade = {"id": 7, "meta": {}}
    decisione = decisione_uscita()
    for i in range(7):
        S._exit_wait(db, trade, trade["meta"], decisione, "prezzi_non_nel_feed",
                     1_000_000.0 + i * 30.0)
    assert len([p for k, p in db.attivita if k == "exit_wait"]) == 1


def test_falsificazione_skip_senza_la_guardia():
    """Senza il controllo, ``evaluate`` viene chiamata, torna [] e non resta
    NESSUNA traccia del perche' il bot tace."""
    S._SKIP_LOG_STATE.clear()
    db, modello = DbFinto(), ModelloTennisFinto()
    vero = S._ha_quote
    S._ha_quote = lambda payload: True       # type: ignore[assignment]
    try:
        esegui_opps(db, [riga_tennis(False)], modello, datetime.now(timezone.utc))
    finally:
        S._ha_quote = vero                   # type: ignore[assignment]
    assert [p for k, p in db.attivita if k == "skip"] == []
    assert modello.chiamate == 1             # chiamata a vuoto, in silenzio


# ===========================================================================
# ALLARME SOLO SUI MERCATI CORE (decisione del coordinatore, 17/09)
# ---------------------------------------------------------------------------
# La prova dal vivo ha mostrato 74 mercati rilevanti senza quote, quasi tutti
# linee a gol: un allarme che li contasse resterebbe acceso in permanenza, e un
# allarme sempre acceso non e' un allarme. L'ELENCO resta nello stato (e' un
# fatto); l'ALLARME (`last_error`, WARNING, badge REST) e' solo sui CORE.
# ===========================================================================
def scanner_calcio_con_linea_a_gol() -> service.Scanner:
    """Calcio in gioco: MATCH_ODDS (core) + una linea Over/Under (non core)."""
    scan = service.Scanner(api_client=None, dry=True, use_stream=False)
    meta = {
        "event_id": "c1", "market_id": "1.MO", "event_name": "Nord FC v Sud FC",
        "open_date": (datetime.now(timezone.utc) - timedelta(minutes=40)).isoformat(),
        "competition": "Serie Z", "runners": [],
        "sides": {"home": 11, "away": 22, "draw": 33},
    }
    scan.sports["calcio"].metas = {"c1": meta}
    scan.events["c1"] = {"sport": "calcio", "inplay": True, "mo_status": "OPEN",
                         "minute": 30, "score_home": 0, "score_away": 0}
    scan.opp_markets["c1"] = {"1.OU25": {"market_id": "1.OU25",
                                         "market_type": "OVER_UNDER_25", "line": 2.5,
                                         "names": {81: "Over 2.5", 82: "Under 2.5"}}}
    scan._rebuild_market_index()
    ora = time.monotonic()
    for st in scan.sports.values():
        st.catalogue_ts = ora
        st.books_ts = ora            # niente poll REST in questi test
    scan.scores_ts = scan.timelines_ts = scan.status_ts = ora
    scan.cs_catalogue_ts = scan.ht_catalogue_ts = scan.opp_catalogue_ts = ora
    scan.stream = PoolFinto({"1.MO", "1.OU25"})
    return scan


def test_linea_a_gol_senza_prezzi_non_fa_allarme():
    """Una Over/Under illiquida senza NESSUNA offerta: si conta, non urla.

    Il MATCH_ODDS ha le quote dallo stream: il badge resta STREAM.
    """
    scan = scanner_calcio_con_linea_a_gol()
    ora = time.monotonic()
    scan.stream_price_mono["1.MO"] = ora - 1.0      # core servito e fresco
    scan.price_mono["1.MO"] = ora - 1.0
    scan.rilevante_da_mono["1.OU25"] = ora - 300.0  # da 5 minuti senza un prezzo
    scan.tick()

    assert scan.mercati_senza_quote == ["1.OU25"], "il FATTO va detto"
    assert scan.mercati_allarme == [], "una linea a gol vuota non e' un allarme"
    assert scan.last_error is None
    assert scan.last_source == "stream"


def test_match_odds_senza_prezzi_fa_allarme():
    """Lo stesso evento, ma senza quote sul MATCH_ODDS da 35 s: allarme."""
    scan = scanner_calcio_con_linea_a_gol()
    ora = time.monotonic()
    scan.rilevante_da_mono["1.MO"] = ora - 35.0
    scan.rilevante_da_mono["1.OU25"] = ora - 300.0
    scan.tick()

    assert scan.mercati_allarme == ["1.MO"]
    assert set(scan.mercati_senza_quote) == {"1.MO", "1.OU25"}
    assert scan.last_error == "quote assenti da 35s su 1 mercati"
    assert scan.last_source == "rest", "il badge deve dire REST quando si ripiega"


def test_correct_score_senza_prezzi_fa_allarme():
    """CS e HT dei candidati sono CORE: e' su quelli che Omega si copre."""
    scan = scanner_calcio_con_linea_a_gol()
    scan.events["c1"]["minute"] = 35                      # candidato CS (dal 30')
    scan.cs_markets["c1"] = {"market_id": "1.CS", "names": {91: "Any Other Home Win"}}
    scan._rebuild_market_index()
    scan.stream.ids.add("1.CS")
    ora = time.monotonic()
    scan.stream_price_mono["1.MO"] = scan.price_mono["1.MO"] = ora - 1.0
    scan.rilevante_da_mono["1.CS"] = ora - 40.0
    scan.rilevante_da_mono["1.OU25"] = ora - 300.0
    scan.tick()
    assert scan.mercati_allarme == ["1.CS"]
    assert scan.last_error and "su 1 mercati" in scan.last_error


def test_allarme_anche_se_lo_stream_perde_i_prezzi():
    """Condizione (b): il core AVEVA prezzi dallo stream e li ha persi, e il
    REST non lo copre."""
    scan = scanner_calcio_con_linea_a_gol()
    ora = time.monotonic()
    scan.stream_price_mono["1.MO"] = ora - 90.0      # lo stream taceva gia' da 90 s
    scan.price_mono["1.MO"] = ora - 90.0             # e il REST non ha coperto
    scan.rilevante_da_mono["1.OU25"] = ora - 300.0
    scan.tick()
    assert scan.mercati_allarme == ["1.MO"]
    assert scan.last_source == "rest"


def test_falsificazione_allarme_su_tutti_i_mercati(monkeypatch):
    """Se l'allarme tornasse a contare anche le linee a gol, resterebbe acceso
    in permanenza: 74 mercati dal vivo, quasi tutti illiquidi."""
    monkeypatch.setattr(service.Scanner, "_e_core", lambda self, mid: True)
    scan = scanner_calcio_con_linea_a_gol()
    ora = time.monotonic()
    scan.stream_price_mono["1.MO"] = scan.price_mono["1.MO"] = ora - 1.0
    scan.rilevante_da_mono["1.OU25"] = ora - 300.0
    scan.tick()
    assert scan.mercati_allarme == ["1.OU25"]
    assert scan.last_error is not None
    assert scan.last_source == "rest"


# ===========================================================================
# 6. UN MERCATO CHIUSO NON E' UN BUCO DATI (17/09 sera)
# ---------------------------------------------------------------------------
# Reperto dal vivo, ore 17:27: il mercato Half Time Score `1.262446903`,
# CLOSED su Betfair con 0 runner prezzati, e' rimasto 509 s in
# `stream_mercati_allarme` (`last_error` permanente, `source: "rest"`)
# mentre le 11 partite in gioco avevano tutte le quote. La causa: il
# candidato HT/CS si esclude guardando `ev["mo_status"]` (il MATCH_ODDS
# dell'evento, che resta OPEN: la partita continua), non lo stato del SUO
# blocco (`ev["ht"]["status"]`/`ev["cs"]["status"]`), che e' cio' che
# `_apply_cs_book` aggiorna a ogni book, anche vuoto.
# ===========================================================================
def test_mercato_ht_chiuso_esce_da_allarme_e_senza_quote():
    """Un HT gia' in allarme che CHIUDE (fine 1T) deve uscire SUBITO da
    entrambe le liste e dalle mappe di copertura, col MATCH_ODDS ancora OPEN
    (la partita prosegue): `last_error` torna None, il badge torna "stream".
    """
    scan = scanner_calcio_con_linea_a_gol()
    scan.events["c1"]["minute"] = 35                      # candidato HT (15-44)
    scan.ht_markets["c1"] = {"market_id": "1.HT", "names": {91: "0-0"}}
    scan._rebuild_market_index()
    scan.stream.ids.add("1.HT")
    ora = time.monotonic()
    scan.stream_price_mono["1.MO"] = scan.price_mono["1.MO"] = ora - 1.0
    scan.rilevante_da_mono["1.HT"] = ora - 40.0
    scan.rilevante_da_mono["1.OU25"] = ora - 300.0
    scan.tick()
    assert scan.mercati_allarme == ["1.HT"]
    assert scan.last_error and "su 1 mercati" in scan.last_error
    assert scan.last_source == "rest"

    # il mercato HT CHIUDE (fine primo tempo): il MATCH_ODDS resta OPEN,
    # cambia solo lo stato del SUO blocco - esattamente l'incidente del 17/09
    scan.events["c1"]["ht"] = {"status": "CLOSED", "inplay": True}
    scan.tick()

    assert "1.HT" not in scan.mercati_allarme
    assert "1.HT" not in scan.mercati_senza_quote
    assert "1.HT" not in scan.rilevante_da_mono, "la mappa deve svuotarsi subito, non al giro dopo"
    assert scan.last_error is None
    assert scan.last_source == "stream"


def test_mercato_ht_chiuso_dall_inizio_mai_in_allarme():
    """Il mercato nasce gia' CLOSED (mai un prezzo, mai osservato aperto):
    non e' un buco feed, e' un mercato finito."""
    scan = scanner_calcio_con_linea_a_gol()
    scan.events["c1"]["minute"] = 35
    scan.ht_markets["c1"] = {"market_id": "1.HT", "names": {91: "0-0"}}
    scan._rebuild_market_index()
    scan.stream.ids.add("1.HT")
    scan.events["c1"]["ht"] = {"status": "CLOSED", "inplay": True}
    ora = time.monotonic()
    scan.stream_price_mono["1.MO"] = scan.price_mono["1.MO"] = ora - 1.0
    scan.rilevante_da_mono["1.OU25"] = ora - 300.0
    scan.tick()

    assert scan.mercati_allarme == []
    assert "1.HT" not in scan.mercati_senza_quote
    assert scan.last_error is None
    assert scan.last_source == "stream"


def test_ht_esce_dai_rilevanti_quando_finisce_il_candidato():
    """La lista rilevanti che alimenta la copertura: l'HT sparisce da solo
    quando ``is_ht_candidate`` non lo vede piu' (oltre il 45'), a prescindere
    dallo stato del suo blocco."""
    scan = scanner_calcio_con_linea_a_gol()
    scan.events["c1"]["minute"] = 35
    scan.ht_markets["c1"] = {"market_id": "1.HT", "names": {91: "0-0"}}
    scan._rebuild_market_index()
    adesso = datetime.now(timezone.utc)
    assert "1.HT" in scan.relevant_market_ids("calcio", adesso)

    scan.events["c1"]["minute"] = 46                      # 1T finito
    assert "1.HT" not in scan.relevant_market_ids("calcio", adesso)


def test_falsificazione_allarme_su_mercato_chiuso(monkeypatch):
    """Tolta la guardia sullo stato del BLOCCO (``_mercato_attivo`` sempre
    vero, come prima - si guardava solo ``mo_status``), l'HT chiuso resta in
    allarme finche' resta candidato: e' esattamente il falso allarme del
    17/09 sera (509 s, mercato CLOSED, partita ancora OPEN)."""
    monkeypatch.setattr(service.Scanner, "_mercato_attivo", lambda self, mid, now: True)
    scan = scanner_calcio_con_linea_a_gol()
    scan.events["c1"]["minute"] = 35
    scan.ht_markets["c1"] = {"market_id": "1.HT", "names": {91: "0-0"}}
    scan._rebuild_market_index()
    scan.stream.ids.add("1.HT")
    scan.events["c1"]["ht"] = {"status": "CLOSED", "inplay": True}
    ora = time.monotonic()
    scan.stream_price_mono["1.MO"] = scan.price_mono["1.MO"] = ora - 1.0
    scan.rilevante_da_mono["1.HT"] = ora - 40.0
    scan.rilevante_da_mono["1.OU25"] = ora - 300.0
    scan.tick()
    assert scan.mercati_allarme == ["1.HT"], (
        "senza la guardia sullo stato del blocco, un mercato CLOSED resta in allarme")


def test_lo_scanner_legge_il_ladder_a_dizionari():
    """DIFESA IN PROFONDITA' (17/09): il ladder di flumine e' fatto di
    dizionari; leggerlo solo per attributo dava None su OGNI prezzo."""
    class ExFlumine:
        def __init__(self):
            self.available_to_back = [{"price": 3.2, "size": 821.19}]
            self.available_to_lay = [{"price": 3.3, "size": 100.0}]
            self.traded_volume = []

    assert scanner.price_pair(ExFlumine()) == {
        "back": 3.2, "lay": 3.3, "back_size": 821.19, "lay_size": 100.0}
    assert scanner.has_any_price([scanner.price_pair(ExFlumine())]) is True
    # e la forma di produzione continua a leggersi identica
    b = book("1.100", CON_PREZZI)
    assert scanner.price_pair(b.runners[0].ex)["back"] == 1.30
