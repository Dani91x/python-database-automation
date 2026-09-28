"""Cantiere B (28/09): la connessione di mercato del runner calcio a FRAMMENTI.

Ordine dell'utente: «non possiamo lasciare eventi "fuori", noi lavoriamo sul
volume». Il 26/09 il runner era saturo a 180 mercati su UNA connessione e 24
partite idonee del feed restavano fuori in silenzio.

Qui, con flumine VERO (``Flumine`` + ``BetfairClient`` costruiti senza rete) e
``BetfairStream`` VERO di betfairlightweight su un socket finto che registra
gli invii, si prova che:

1. le strategie degli ordini RIUSANO lo stream del recorder (prima: 2
   ``MarketStream`` = 2 connessioni con gli stessi mercati);
2. oltre ``per_conn`` mercati si apre un frammento (connessione) in piu', a
   caldo, agganciato a TUTTE le strategie;
3. un mercato non cambia mai frammento finche' il frammento e' vivo; si
   risottoscrive solo il frammento che cambia; un frammento in piu' vuoto si
   chiude; il frammento 0 non resta mai vuoto;
4. capacita' esaurita = eccezione dichiarata, nulla cambiato; rifiuto Betfair
   (``MAX_CONNECTION_LIMIT_EXCEEDED``) = frammento chiuso, mercati "persi"
   ritornati, capacita' ridotta per la pausa; riserva di connessioni rispettata;
5. un frammento muto (gli altri vivi) viene chiuso e i suoi mercati ripiazzati;
   tutti muti = nessuna azione (decide il controllo di stallo del runner);
6. un frammento chiuso non si riconnette piu' (``run`` senza retry infinito);
7. l'auto-follow segue TUTTE le partite del feed quando la capacita' c'e' e,
   quando non c'e', le partite fuori sono DICHIARATE con il motivo nello stato;
8. il runner usa tutto questo (cablaggio sul sorgente vero) e il budget del
   catalogo e' la capacita' dei frammenti.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List

import pytest
import betfairlightweight
from betfairlightweight.filters import streaming_market_data_filter, streaming_market_filter
from betfairlightweight.streaming.betfairstream import BetfairStream
from flumine import Flumine, clients
from flumine.streams.marketstream import MarketStream

from Betfair.stream import auto_follow as AF
from Betfair.stream import frammenti_mercato as FR
from Betfair.stream import sottoscrizione_a_caldo as SC
from Betfair.stream.engine.live_trading_strategy import LiveTradingStrategy
from Betfair.stream.recorder import MarketRecorderStrategy


# ---------------------------------------------------------------------------
# finti che parlano come il vero
# ---------------------------------------------------------------------------
class _Socket:
    """Socket finto: registra i messaggi inviati (come li manda bflw)."""

    def __init__(self) -> None:
        self.inviati: List[Dict[str, Any]] = []

        self.chiuso = False

    def sendall(self, dati: bytes) -> None:
        self.inviati.append(json.loads(dati.decode("utf-8").strip()))

    # come il socket vero: ``BetfairStream.stop`` chiama shutdown e close
    def shutdown(self, _how: int) -> None:
        self.chiuso = True

    def close(self) -> None:
        self.chiuso = True


def _status(ok: bool, disponibili: Any = None, codice: str = "") -> str:
    """Messaggio ``status`` di Betfair come arriva sul socket (Exchange Stream API)."""
    d: Dict[str, Any] = {"op": "status", "id": 1, "statusCode": "SUCCESS" if ok else "FAILURE",
                         "connectionClosed": not ok}
    if disponibili is not None:
        d["connectionsAvailable"] = disponibili
    if not ok:
        d["errorCode"] = codice
        d["errorMessage"] = "finto"
        d["connectionId"] = "002-000000000000-000000"
    return json.dumps(d)


def _collega(stream: Any, disponibili: Any = 8) -> BetfairStream:
    """Collega la MarketStream a un BetfairStream VERO su socket finto, come fa
    ``MarketStream.run`` (create_stream + subscribe_to_markets), e fa arrivare
    lo status SUCCESS dell'autenticazione."""
    bs = BetfairStream(stream.stream_id, stream._listener, "k", "t", 1.0, 1024, None)
    bs._running = True
    bs._socket = _Socket()
    stream._stream = bs
    stream.stream_id = bs.subscribe_to_markets(
        market_filter=stream.market_filter, market_data_filter=stream.market_data_filter,
        conflate_ms=stream.conflate_ms)
    stream._listener.on_data(_status(True, disponibili))
    return bs


def _framework(ids: List[str]):
    """Il framework come in ``runner.setup_and_run`` (PAPER): recorder con
    ``FrammentoMarketStream`` + strategia degli ordini con lo stream condiviso."""
    api = betfairlightweight.APIClient("u", "p", app_key="k", lightweight=False)
    fw = Flumine(client=clients.BetfairClient(api, order_stream=True, paper_trade=True,
                                              min_bet_validation=False))
    rec = MarketRecorderStrategy(
        market_filter=streaming_market_filter(market_ids=ids),
        market_data_filter=streaming_market_data_filter(
            fields=["EX_ALL_OFFERS", "EX_TRADED", "EX_TRADED_VOL", "EX_LTP", "EX_MARKET_DEF",
                    "SP_TRADED", "SP_PROJECTED"], ladder_levels=10),
        conflate_ms=None, stream_class=FR.FrammentoMarketStream,
        context={"data_dir": ".", "market_to_event": {}, "market_type_by_id": {},
                 "event_markets": {}, "depth": 10, "record_events": lambda: None})
    fw.add_strategy(rec)
    live = LiveTradingStrategy(**FR.kwargs_stream_condiviso(rec), session=None, mode="paper")
    fw.add_strategy(live)
    return fw, rec, live


def _market_streams(fw: Any) -> List[Any]:
    return [s for s in fw.streams if isinstance(s, MarketStream)]


class _Orologio:
    def __init__(self) -> None:
        self.t = time.monotonic()

    def __call__(self) -> float:
        return self.t


def _gestore(per_conn: int = 180, max_conn: int = 3, riserva: int = 1):
    orologio = _Orologio()
    avviati: List[Any] = []

    def avvia(s: Any) -> None:            # al posto di Thread.start: niente rete
        avviati.append(s)
        _collega(s)
    g = FR.GestoreFrammenti(per_conn=per_conn, max_conn=max_conn, riserva=riserva,
                            orologio=orologio, avvia_stream=avvia)
    return g, orologio, avviati


def _ids(a: int, b: int) -> List[str]:
    return ["1.%06d" % i for i in range(a, b)]


def _dove(fw: Any) -> Dict[str, int]:
    out = {}
    for s in FR.GestoreFrammenti.frammenti(fw):
        for m in SC.mercati_dello_stream(s):
            out[m] = s.stream_id // 10000
    return out


# ---------------------------------------------------------------------------
# 1. una connessione in meno: le strategie degli ordini riusano lo stream
# ---------------------------------------------------------------------------
def test_strategie_ordini_riusano_lo_stream_del_recorder():
    fw, rec, live = _framework(["1.1", "1.2"])
    ms = _market_streams(fw)
    assert len(ms) == 1, "flumine ha aperto %d connessioni di mercato" % len(ms)
    assert isinstance(ms[0], FR.FrammentoMarketStream)
    assert rec.streams == live.streams == ms


def test_il_vecchio_modo_apriva_due_connessioni():
    """Controllo NEGATIVO (il difetto): col solo market_filter la strategia
    ha il market_data_filter di serie di flumine -> seconda MarketStream."""
    fw, rec, _live = _framework(["1.1"])
    vecchia = LiveTradingStrategy(market_filter=rec.market_filter, session=None,
                                  mode="paper", name="vecchio_modo")
    fw.add_strategy(vecchia)
    assert len(_market_streams(fw)) == 2


# ---------------------------------------------------------------------------
# 2-3. piano puro
# ---------------------------------------------------------------------------
def test_pianifica_riempie_poi_apre():
    p = FR.pianifica([set(_ids(0, 170))], _ids(0, 400), per_conn=180, max_conn=3)
    assert len(p.bersagli[0]) == 180 and set(_ids(0, 170)) <= p.bersagli[0]
    assert [len(x) for x in p.nuovi] == [180, 40] and not p.fuori


def test_pianifica_mai_spostare_un_mercato():
    attuali = [set(_ids(0, 180)), set(_ids(180, 250))]
    voluti = set(_ids(0, 250)) - set(_ids(0, 10)) | set(_ids(1000, 1030))
    p = FR.pianifica(attuali, voluti, per_conn=180, max_conn=3)
    for i, a in enumerate(attuali):
        assert (a & voluti) <= p.bersagli[i]
    assert set().union(*p.bersagli) == voluti and not p.nuovi and not p.fuori


def test_pianifica_capacita_esaurita_e_frammenti_vuoti():
    p = FR.pianifica([set(_ids(0, 5))], _ids(0, 400), per_conn=180, max_conn=2)
    assert len(p.fuori) == 40
    # frammento in piu' senza mercati voluti: bersaglio vuoto (= chiudere);
    # frammento 0 senza mercati voluti: tiene quelli di prima (mai vuoto)
    p = FR.pianifica([set(_ids(0, 5)), set(_ids(5, 9))], _ids(5, 9), per_conn=180, max_conn=3)
    assert p.bersagli == [set(_ids(0, 5)), set(_ids(5, 9))]
    p = FR.pianifica([set(_ids(0, 5)), set(_ids(5, 9))], _ids(0, 5), per_conn=180, max_conn=3)
    assert p.bersagli[1] == set()
    p = FR.pianifica([set(_ids(0, 5))], ["1.999999"], per_conn=180, max_conn=3)
    assert p.bersagli[0] == {"1.999999"}
    p = FR.pianifica([set(_ids(0, 5)), {"1.999999"}], ["1.999999"], per_conn=180, max_conn=3)
    assert p.bersagli[0] == set(_ids(0, 5))


def test_primo_frammento_prima_i_manuali():
    manuali = _ids(500, 520)
    out = FR.primo_frammento(_ids(0, 300) + manuali, manuali, 180)
    assert len(out) == 180 and out[:20] == sorted(manuali)


# ---------------------------------------------------------------------------
# 2-3. gestore su flumine vero
# ---------------------------------------------------------------------------
def test_oltre_il_tetto_si_apre_un_frammento_agganciato_a_tutte_le_strategie():
    fw, rec, live = _framework(_ids(0, 180))
    _collega(_market_streams(fw)[0])
    g, _o, avviati = _gestore()
    assert g.applica(fw, _ids(0, 250)) == 2
    fr = FR.GestoreFrammenti.frammenti(fw)
    assert len(fr) == 2 and len(avviati) == 1 and isinstance(fr[1], FR.FrammentoMarketStream)
    assert SC.mercati_dello_stream(fr[0]) == _ids(0, 180)       # frammento 0 intatto
    assert SC.mercati_dello_stream(fr[1]) == _ids(180, 250)
    assert fr[0]._stream._socket.inviati[-1]["marketFilter"]["marketIds"] == _ids(0, 180)
    assert len(fr[0]._stream._socket.inviati) == 1               # nessuna risottoscrizione
    assert fr[1]._stream._socket.inviati[-1]["marketFilter"] == {"marketIds": _ids(180, 250)}
    for strat in (rec, live):                                    # book e chiusure a tutti
        assert strat.streams == fr
        assert set(strat.stream_ids) == {fr[0].stream_id, fr[1].stream_id}
        assert strat.market_filter == [fr[0].market_filter, fr[1].market_filter]
    assert fr[1].market_data_filter == fr[0].market_data_filter
    assert fr[1].stream_id // 10000 != fr[0].stream_id // 10000   # id di flumine distinto
    st = g.stato(fw)
    assert st["connessioni_di_mercato"] == 2 and st["capacita_mercati"] == 540


def test_nessun_mercato_cambia_frammento_e_solo_chi_cambia_si_risottoscrive():
    fw, _rec, _live = _framework(_ids(0, 180))
    _collega(_market_streams(fw)[0])
    g, _o, _a = _gestore()
    g.applica(fw, _ids(0, 250))
    prima = _dove(fw)
    fr = FR.GestoreFrammenti.frammenti(fw)
    n0 = len(fr[0]._stream._socket.inviati)
    n1 = len(fr[1]._stream._socket.inviati)
    # esce un mercato del frammento 1, ne entra uno nuovo: tocca SOLO il frammento 1?
    # no: il nuovo riempie il primo frammento con posto -> il frammento 1 (0 e' pieno)
    voluti = set(_ids(0, 250)) - {_ids(200, 201)[0]} | {"1.900000"}
    g.applica(fw, sorted(voluti))
    dopo = _dove(fw)
    for m in voluti & set(prima):
        assert dopo[m] == prima[m], "il mercato %s ha cambiato frammento" % m
    assert len(fr[0]._stream._socket.inviati) == n0
    assert len(fr[1]._stream._socket.inviati) == n1 + 1
    assert dopo["1.900000"] == prima[_ids(180, 181)[0]]


def test_frammento_in_piu_vuoto_si_chiude_il_primo_mai_vuoto():
    fw, rec, live = _framework(_ids(0, 180))
    _collega(_market_streams(fw)[0])
    g, _o, _a = _gestore()
    g.applica(fw, _ids(0, 250))
    secondo = FR.GestoreFrammenti.frammenti(fw)[1]
    g.applica(fw, _ids(0, 100))
    fr = FR.GestoreFrammenti.frammenti(fw)
    assert fr == [_market_streams(fw)[0]] and secondo.chiuso
    assert secondo not in list(fw.streams) and secondo not in rec.streams + live.streams
    assert SC.mercati_dello_stream(fr[0]) == _ids(0, 100)


def test_capacita_esaurita_eccezione_dichiarata_nulla_cambia():
    fw, _rec, _live = _framework(_ids(0, 180))
    _collega(_market_streams(fw)[0])
    g, _o, avviati = _gestore(max_conn=1)
    with pytest.raises(FR.CapacitaInsufficiente):
        g.applica(fw, _ids(0, 181))
    assert len(FR.GestoreFrammenti.frammenti(fw)) == 1 and not avviati
    assert len(_market_streams(fw)[0]._stream._socket.inviati) == 1
    assert issubclass(FR.CapacitaInsufficiente, SC.NonPronto)


def test_frammento_non_connesso_non_si_tocca_gli_altri_si():
    fw, _rec, _live = _framework(_ids(0, 180))
    bs0 = _collega(_market_streams(fw)[0])
    g, _o, _a = _gestore()
    g.applica(fw, _ids(0, 250))
    fr = FR.GestoreFrammenti.frammenti(fw)
    fr[1]._stream._running = False           # in riconnessione
    with pytest.raises(SC.NonPronto):
        g.applica(fw, _ids(0, 179) + _ids(180, 240))   # cambiano entrambi
    assert SC.mercati_dello_stream(fr[0]) == _ids(0, 179)
    assert SC.mercati_dello_stream(fr[1]) == _ids(180, 250)
    assert len(bs0._socket.inviati) == 2


# ---------------------------------------------------------------------------
# 4-5. rifiuti, riserva, muti
# ---------------------------------------------------------------------------
def test_rifiuto_betfair_chiude_il_frammento_e_riduce_la_capacita():
    fw, _rec, _live = _framework(_ids(0, 180))
    _collega(_market_streams(fw)[0])
    orologio = _Orologio()

    def avvia_rifiutato(s: Any) -> None:         # Betfair nega la connessione
        s._listener.on_data(_status(False, codice="MAX_CONNECTION_LIMIT_EXCEEDED"))
    g = FR.GestoreFrammenti(per_conn=180, max_conn=3, riserva=0, orologio=orologio,
                            avvia_stream=avvia_rifiutato)
    g.applica(fw, _ids(0, 250))
    nuovo = FR.GestoreFrammenti.frammenti(fw)[1]
    assert g.capacita(fw) == 540
    persi = g.manutenzione(fw)
    assert persi == set(_ids(180, 250)) and nuovo.chiuso
    assert g.capacita(fw) == 180                 # pausa: solo quelli aperti
    st = g.stato(fw)
    assert st["ultimo_rifiuto"] == "MAX_CONNECTION_LIMIT_EXCEEDED"
    assert st["in_pausa_dopo_rifiuto"] and "rifiutato" in st["motivo_limite"]
    orologio.t += FR.PAUSA_RIFIUTO_S + 1
    assert g.capacita(fw) == 540                 # dopo la pausa si riprova


def test_connessione_senza_autenticazione_con_la_rete_viva_e_un_rifiuto():
    fw, _rec, _live = _framework(_ids(0, 180))
    _collega(_market_streams(fw)[0])
    orologio = _Orologio()
    g = FR.GestoreFrammenti(per_conn=180, max_conn=3, orologio=orologio,
                            avvia_stream=lambda s: None)     # nessuna risposta
    g.applica(fw, _ids(0, 200))
    assert g.manutenzione(fw) == set()           # entro l'attesa: niente
    orologio.t += FR.ATTESA_APERTURA_S + 1
    _market_streams(fw)[0]._listener.ultimo_msg_mono = orologio.t   # frammento 0 vivo
    assert g.manutenzione(fw) == set(_ids(180, 200))


def test_rete_giu_nessun_frammento_si_chiude():
    fw, _rec, _live = _framework(_ids(0, 180))
    _collega(_market_streams(fw)[0])
    orologio = _Orologio()
    g = FR.GestoreFrammenti(per_conn=180, max_conn=3, orologio=orologio,
                            avvia_stream=lambda s: None)
    g.applica(fw, _ids(0, 200))
    orologio.t += FR.MUTO_S * 3                  # tutti muti: e' la rete
    assert g.manutenzione(fw) == set()
    assert len(FR.GestoreFrammenti.frammenti(fw)) == 2


def test_riserva_di_connessioni_per_gli_altri_processi():
    fw, _rec, _live = _framework(_ids(0, 180))
    base = _market_streams(fw)[0]
    _collega(base, disponibili=1)                # Betfair: ne resta 1
    g, _o, avviati = _gestore(riserva=1)
    assert g.capacita(fw) == 180
    with pytest.raises(FR.CapacitaInsufficiente):
        g.applica(fw, _ids(0, 200))
    assert not avviati and "riserva" in g.stato(fw)["motivo_limite"]
    base._listener.on_data(_status(True, 0))     # lo 0 va tenuto (bflw lo perde)
    assert base._listener.connessioni_disponibili == 0
    assert base._listener.connections_available == 1       # il difetto di bflw
    base._listener.on_data(_status(True, 5))
    assert g.capacita(fw) == 540


def test_frammento_muto_con_gli_altri_vivi_si_chiude_e_si_ripiazza():
    fw, _rec, _live = _framework(_ids(0, 180))
    _collega(_market_streams(fw)[0])
    g, orologio, _a = _gestore()
    g.applica(fw, _ids(0, 250))
    fr = FR.GestoreFrammenti.frammenti(fw)
    orologio.t += FR.MUTO_S + 5
    fr[0]._listener.ultimo_msg_mono = orologio.t          # heartbeat freschi
    fr[1]._listener.ultimo_msg_mono = orologio.t - FR.MUTO_S - 5
    persi = g.manutenzione(fw)
    assert persi == set(_ids(180, 250)) and fr[1].chiuso
    assert g.stato(fw)["conti"]["muti"] == 1
    assert g.capacita(fw) == 540                 # un muto non e' un rifiuto
    g.applica(fw, _ids(0, 250))                  # ripiazzati su una connessione nuova
    nuovi = FR.GestoreFrammenti.frammenti(fw)
    assert len(nuovi) == 2 and nuovi[1] is not fr[1]
    assert SC.mercati_dello_stream(nuovi[1]) == _ids(180, 250)


def test_listener_misura_la_sua_connessione():
    fw, _rec, _live = _framework(["1.1"])
    li = _market_streams(fw)[0]._listener
    assert li.ultimo_msg_mono == 0.0 and not li.autenticato_una_volta
    li.on_data(json.dumps({"op": "mcm", "id": 5, "clk": "A", "pt": 1, "ct": "HEARTBEAT"}))
    assert li.ultimo_msg_mono > 0 and li.ultimo_dato_mono == 0.0
    li.on_data(_status(False, codice="TOO_MANY_REQUESTS"))
    assert li.ultimo_errore == "TOO_MANY_REQUESTS" and not li.autenticato
    li.on_data(_status(True, 7))
    assert li.autenticato and li.ultimo_errore is None and li.connessioni_disponibili == 7


# ---------------------------------------------------------------------------
# 6. un frammento chiuso non si riconnette piu'
# ---------------------------------------------------------------------------
def test_frammento_chiuso_non_si_riconnette(monkeypatch):
    fw, _rec, _live = _framework(["1.1"])
    s = _market_streams(fw)[0]
    tentativi = []

    def run_ko(self: Any) -> None:
        tentativi.append(time.monotonic())
        raise ConnectionError("rete giu'")
    monkeypatch.setattr(FR, "_RUN_MARKETSTREAM", run_ko)
    t = threading.Thread(target=s.run, daemon=True)
    t.start()
    time.sleep(0.2)
    s.stop()
    t.join(2.0)
    assert not t.is_alive(), "il frammento chiuso continua a riconnettersi"
    assert len(tentativi) == 1


def test_frammento_in_errore_si_riconnette_finche_aperto(monkeypatch):
    fw, _rec, _live = _framework(["1.1"])
    s = _market_streams(fw)[0]
    tentativi = []

    def run_ko_poi_ok(self: Any) -> None:
        tentativi.append(1)
        if len(tentativi) < 3:
            raise ConnectionError("rete giu'")
    monkeypatch.setattr(FR, "_RUN_MARKETSTREAM", run_ko_poi_ok)
    s._pausa.wait = lambda _t: True               # niente attese reali
    s.run()
    assert len(tentativi) == 3 and s.riconnessioni == 2 and not s.chiuso


# ---------------------------------------------------------------------------
# 7. l'auto-follow: tutte le partite dentro, o fuori DICHIARATE
# ---------------------------------------------------------------------------
def _feed(n: int, mercati: int = 4) -> List[Dict[str, Any]]:
    """Righe del feed (``leggi_feed_calcio``: chiavi e tipi del vero)."""
    righe = []
    for i in range(n):
        base = 1000 * (i + 1)
        riga = {"event_id": str(35000000 + i), "updated_at": "2026-09-26T15:00:00+00:00",
                "inplay": i < 30, "open_date": "2026-09-26T%02d:00:00.000Z" % (13 + i // 20),
                "home": "Casa%d" % i, "away": "Ospite%d" % i, "event_name": None,
                "mo_market_id": "1.%d" % (base + 1), "mo_status": "OPEN",
                "cs": "1.%d" % (base + 2), "ht": "1.%d" % (base + 3), "btts": None,
                "ht_result": None, "ou": []}
        if mercati > 3:
            riga["ou"] = [{"market_id": "1.%d" % (base + 4), "line": 2.5}]
        righe.append(riga)
    return righe


def _auto(fw: Any, g: Any, righe: List[Dict[str, Any]]):
    pubblicati: List[Dict[str, Any]] = []
    af = AF.AutoFollow(piano=AF.PianoFollow(g.capacita(None)), sottoscrittore=g,
                       feed=lambda: righe, attori_collegati=lambda: ["omega"],
                       pubblica=pubblicati.append, feed_s=0.001, min_intervallo_s=0.0)
    af.aggancia(fw, SC.mercati_dello_stream(_market_streams(fw)[0]))
    return af, pubblicati


def test_auto_follow_segue_tutte_le_67_partite_del_26_09():
    fw, _rec, _live = _framework(["1.1"])
    _collega(_market_streams(fw)[0])
    g, _o, _a = _gestore()
    righe = _feed(67)                            # 67 partite x 4 = 268 mercati
    af, pubblicati = _auto(fw, g, righe)
    af.giro()
    s = af.stato()
    assert s["eventi_auto"] == 67 and s["partite_fuori_n"] == 0
    assert s["mercati_sottoscritti"] == 268 == s["mercati_seguiti"]
    assert s["connessioni_di_mercato"] == 2 and s["tetto_mercati"] == 540
    tutti = set()
    for st in FR.GestoreFrammenti.frammenti(fw):
        tutti |= set(SC.mercati_dello_stream(st))
    assert tutti >= {m for r in righe for m in AF.mercati_della_riga(r)}
    assert pubblicati and pubblicati[-1]["frammenti"]["connessioni_di_mercato"] == 2


def test_auto_follow_capacita_esaurita_fuori_dichiarate_col_motivo():
    fw, _rec, _live = _framework(["1.1"])
    _collega(_market_streams(fw)[0])
    g, _o, _a = _gestore(max_conn=1)
    righe = _feed(67)
    af, pubblicati = _auto(fw, g, righe)
    af.giro()
    s = af.stato()
    assert s["eventi_auto"] == 45 and s["partite_fuori_n"] == 22   # 45 x 4 = 180
    fuori = {x["event_id"] for x in s["partite_fuori"]}
    dentro = {r["event_id"] for r in AF.partite_dal_feed(righe)[:45]}
    assert not (fuori & dentro)                  # criterio: in gioco, poi orario
    assert all("capacita' esaurita" in x["motivo"] for x in s["partite_fuori"])
    assert all(x["nome"] for x in s["partite_fuori"])
    assert pubblicati[-1]["partite_fuori_n"] == 22 and s["criterio_fuori"]


def test_auto_follow_rifiuto_betfair_rientra_e_dichiara():
    fw, _rec, _live = _framework(["1.1"])
    _collega(_market_streams(fw)[0])
    orologio = _Orologio()
    rifiuta = {"si": False}

    def avvia(s: Any) -> None:
        if rifiuta["si"]:
            s._listener.on_data(_status(False, codice="MAX_CONNECTION_LIMIT_EXCEEDED"))
        else:
            _collega(s)
    g = FR.GestoreFrammenti(per_conn=180, max_conn=3, riserva=0, orologio=orologio,
                            avvia_stream=avvia)
    righe = _feed(67)
    af, _p = _auto(fw, g, righe)
    rifiuta["si"] = True
    af.giro()                                    # apre il 2o frammento: Betfair lo nega
    af.giro()                                    # manutenzione: chiuso, capacita' 180
    s = af.stato()
    assert s["tetto_mercati"] == 180 and s["connessioni_di_mercato"] == 1
    assert s["mercati_seguiti"] <= 180 and s["mercati_sottoscritti"] <= 180
    assert s["partite_fuori_n"] == 67 - s["eventi_auto"] > 0
    assert s["frammenti"]["ultimo_rifiuto"] == "MAX_CONNECTION_LIMIT_EXCEEDED"
    # dopo la pausa Betfair concede: rientrano tutte
    rifiuta["si"] = False
    orologio.t += FR.PAUSA_RIFIUTO_S + 1
    af.giro()
    af.giro()
    s = af.stato()
    assert s["eventi_auto"] == 67 and s["partite_fuori_n"] == 0
    assert s["connessioni_di_mercato"] == 2


def test_auto_follow_frammento_muto_i_suoi_mercati_tornano_su_una_connessione_nuova():
    fw, _rec, _live = _framework(["1.1"])
    _collega(_market_streams(fw)[0])
    g, orologio, avviati = _gestore()
    righe = _feed(67)
    af, _p = _auto(fw, g, righe)
    af.giro()
    fr = FR.GestoreFrammenti.frammenti(fw)
    assert len(fr) == 2
    suoi = set(SC.mercati_dello_stream(fr[1]))
    orologio.t += FR.MUTO_S + 5
    fr[0]._listener.ultimo_msg_mono = orologio.t
    fr[1]._listener.ultimo_msg_mono = orologio.t - FR.MUTO_S - 5
    af.giro()
    nuovi = FR.GestoreFrammenti.frammenti(fw)
    assert fr[1].chiuso and len(nuovi) == 2 and nuovi[1] is not fr[1] and len(avviati) == 2
    assert set(SC.mercati_dello_stream(nuovi[1])) == suoi
    s = af.stato()
    assert s["mercati_sottoscritti"] == 268 and s["partite_fuori_n"] == 0


def test_auto_follow_capacita_ridotta_non_espelle_le_posizioni(monkeypatch):
    fw, _rec, _live = _framework(["1.1"])
    _collega(_market_streams(fw)[0])
    g, _o, _a = _gestore()
    righe = _feed(67)
    af, _p = _auto(fw, g, righe)
    af.giro()
    con_ordini = {r["event_id"] for r in AF.partite_dal_feed(righe)[-5:]}  # le ultime
    monkeypatch.setattr(af, "_protetti", lambda: set(con_ordini))
    g.max_conn = 1                              # capacita' che scende (es. rifiuto)
    af._frammenti()
    for ev in con_ordini:
        assert af.segue_auto(ev), "una partita con ordini e' stata espulsa"
    assert len(af.piano.mercati()) <= 180
    assert af.stato()["partite_fuori_n"] > 0


def _chiavi(d: Any, pre: str = "") -> Dict[str, str]:
    """Chiave -> tipo JSON, ricorsivo nei dict (le liste: il primo elemento)."""
    out: Dict[str, str] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out[pre + k] = type(v).__name__ if v is not None else "null"
            out.update(_chiavi(v, pre + k + "."))
    elif isinstance(d, list) and d and isinstance(d[0], dict):
        out.update(_chiavi(d[0], pre + "[]."))
    return out


def test_fixture_ui_ha_le_chiavi_vere():
    """La UI (``frontend/src/lib/capacitaMercati.ts``) si prova sulla fixture
    ``autoFollowFinti.json``: deve avere le chiavi e i tipi dello stato VERO."""
    import os

    radice = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    with open(os.path.join(radice, "frontend", "src", "lib", "__fixtures__",
                           "autoFollowFinti.json"), encoding="utf-8") as fh:
        finti = json.load(fh)
    fw, _rec, _live = _framework(["1.1"])
    _collega(_market_streams(fw)[0])
    g, _o, _a = _gestore(max_conn=1)
    af, pubblicati = _auto(fw, g, _feed(50))
    af.giro()
    vero = json.loads(json.dumps(pubblicati[-1], default=str))
    finto = finti["capacita_esaurita"]
    ignora = {"feed.ts"}                          # valori, non chiavi della UI
    kv, kf = _chiavi(vero), _chiavi(finto)
    assert set(kv) - ignora == set(kf) - ignora
    for k in ("partite_fuori_n", "tetto_mercati", "mercati_seguiti", "connessioni_di_mercato",
              "partite_fuori.[].event_id", "partite_fuori.[].nome", "partite_fuori.[].motivo",
              "partite_fuori.[].dal", "frammenti.motivo_limite", "frammenti.capacita_mercati",
              "frammenti.connessioni_disponibili_betfair", "frammenti.frammenti.[].connesso",
              "criterio_fuori", "feed.partite", "eventi_auto"):
        assert kv[k] == kf[k], k


# ---------------------------------------------------------------------------
# 8. cablaggio nel runner
# ---------------------------------------------------------------------------
def test_cablaggio_runner():
    import inspect

    from Betfair.stream import runner as R
    src = inspect.getsource(R.setup_and_run)
    assert src.count("**_FR.kwargs_stream_condiviso(recorder)") == 2
    assert "stream_class=_FR.FrammentoMarketStream" in src
    assert "auto.aggancia(framework, mercati_frammento0)" in src
    assert "market_filter=streaming_market_filter(market_ids=mercati_frammento0)" in src
    costr = inspect.getsource(R._costruisci_auto_follow)
    assert "sottoscrittore=gestore" in costr and "_FR.GestoreFrammenti.da_ambiente()" in costr
    assert "cap = _capacita_mercati()" in inspect.getsource(R._catalog_events)


def test_budget_del_catalogo_e_la_capacita_dei_frammenti(monkeypatch):
    from Betfair.stream import runner as R
    monkeypatch.setitem(R._MOTORE, "auto", None)
    assert R._capacita_mercati() == R.HARD_MARKET_CAP
    g, _o, _a = _gestore()
    af = AF.AutoFollow(piano=AF.PianoFollow(g.capacita(None)), sottoscrittore=g)
    monkeypatch.setitem(R._MOTORE, "auto", af)
    assert R._capacita_mercati() == 540


def test_da_ambiente(monkeypatch):
    monkeypatch.setenv("RUNNER_CALCIO_STREAM_CONNS", "")
    monkeypatch.delenv("RUNNER_CALCIO_STREAM_RISERVA", raising=False)
    g = FR.GestoreFrammenti.da_ambiente()
    assert g.max_conn == FR.DEFAULT_MAX_CONNESSIONI and g.riserva == FR.DEFAULT_RISERVA
    assert g.per_conn == AF.tetto_mercati() <= 200
    monkeypatch.setenv("RUNNER_CALCIO_STREAM_CONNS", "99")
    assert FR.GestoreFrammenti.da_ambiente().max_conn == 10
    monkeypatch.setenv("RUNNER_CALCIO_STREAM_CONNS", "x")
    assert FR.GestoreFrammenti.da_ambiente().max_conn == FR.DEFAULT_MAX_CONNESSIONI


# ---------------------------------------------------------------------------
# 9. (coordinatore, punto 1) ricostruzione: i mercati con SOLDI nel frammento 0
# ---------------------------------------------------------------------------
def _ordine_nel_blotter(fw: Any, strategia: Any, market_id: str) -> None:
    """Un ordine VERO di flumine (Trade + LimitOrder) nel blotter VERO del mercato."""
    from flumine.markets.market import Market
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    m = fw.markets.markets.get(market_id)
    if m is None:
        m = Market(fw, market_id, None)
        fw.markets.add_market(market_id, m)
    trade = Trade(market_id=market_id, selection_id=19, handicap=0, strategy=strategia)
    ordine = trade.create_order(side="BACK", order_type=LimitOrder(price=2.0, size=2.0))
    m.blotter[ordine.customer_order_ref] = ordine


def test_ricostruzione_mercati_con_soldi_davanti_nel_frammento0(monkeypatch):
    """200+ mercati; tre partite AUTOMATICHE con soldi e market_id ALTO (una con
    ordine nel blotter del framework precedente, una con un comando in volo, una
    nello specchio) + 60 manuali: i tre sono nel frammento 0, davanti."""
    from Betfair.stream import runner as R

    monkeypatch.setattr(R.db, "insert_alert", lambda *a, **k: None)
    vecchio, _rec, live = _framework(["1.1"])
    _ordine_nel_blotter(vecchio, live, "1.999999")
    prec = FR.mercati_con_ordini(vecchio)
    assert prec == {"1.999999"}
    g, _o, _a = _gestore()
    af = AF.AutoFollow(piano=AF.PianoFollow(g.capacita(None)), sottoscrittore=g)
    manuali = _ids(0, 60)
    af.imposta_manuali({"30000001": manuali})
    for i, r in enumerate(_feed(40)):                     # 160 mercati automatici
        af.piano.richiedi(r["event_id"], AF.mercati_della_riga(r), priorita=AF.PRI_CANDIDATA,
                          protetti=set(), puo_espellere=False, ora=0.0)
    for ev, mid in (("34000001", "1.999999"), ("34000002", "1.999997")):   # prime da espellere
        af.piano.richiedi(ev, {mid}, priorita=AF.PRI_CANDIDATA, protetti=set(),
                          puo_espellere=False, ora=0.0)
    af.richiedi("1.999998", event_id="35999998")          # comando di un bot in volo
    candidati = sorted(set(manuali) | set(af.mercati_da_sottoscrivere()))
    assert len(candidati) > 200
    soldi, fonti = R._mercati_con_soldi(prec, af, candidati,
                                        specchio=lambda ids: {"1.999997"} & set(ids))
    assert soldi == {"1.999999", "1.999998", "1.999997"}
    assert fonti == {"blotter_precedente": 1, "auto_follow": 1, "specchio_db": 1}
    ids0 = R._frammento0(candidati, manuali, af, soldi, fonti)
    assert len(ids0) == 180
    assert ids0[:3] == sorted(soldi)                      # davanti a tutto
    assert ids0[3:63] == sorted(manuali)                  # poi i manuali
    assert g.costruzione["con_soldi"] == 3 and g.costruzione["oltre_frammento0"] == 0
    # le voci con soldi sono protette: una capacita' che scende non le espelle
    # (capacita' = 60 manuali + i 3 mercati con soldi: TUTTE le altre voci
    # automatiche escono, quelle con soldi restano)
    af.imposta_con_soldi(soldi)
    af.piano.tetto = 63
    af.rientra_nel_tetto()
    for ev in ("34000001", "35999998", "34000002"):
        assert af.segue_auto(ev), ev
    assert af.piano.mercati() == set(manuali) | soldi


def test_soldi_oltre_un_frammento_dichiarati(monkeypatch):
    from Betfair.stream import runner as R

    allarmi: List[Any] = []
    monkeypatch.setattr(R.db, "insert_alert", lambda *a, **k: allarmi.append(a))
    g, _o, _a = _gestore()
    af = AF.AutoFollow(piano=AF.PianoFollow(g.capacita(None)), sottoscrittore=g)
    soldi = set(_ids(0, 200))
    ids0 = R._frammento0(_ids(0, 300), [], af, soldi, {"specchio_db": 200})
    assert set(ids0) <= soldi and len(ids0) == 180
    assert g.costruzione["oltre_frammento0"] == 20
    assert g.stato(None)["costruzione"]["oltre_frammento0"] == 20
    assert allarmi and allarmi[0][0] == "CRITICAL" and allarmi[0][1] == "SOLDI_OLTRE_FRAMMENTO0"


class _Query:
    """Catena PostgREST finta: ``table().select().in_().execute().data``."""

    def __init__(self, righe: Dict[str, List[Dict[str, Any]]], tabella: str) -> None:
        self.righe, self.tabella = righe, tabella
        self.ids: Any = None

    def select(self, _c: str) -> "_Query":
        return self

    def in_(self, col: str, ids: List[str]) -> "_Query":
        assert col == "market_id"
        self.ids = set(ids)
        return self

    def execute(self) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(data=[r for r in self.righe[self.tabella]
                                     if r["market_id"] in self.ids])


def test_specchio_ordini_e_posizioni(monkeypatch):
    """Righe con le chiavi e i valori dello specchio VERO (``_order_row`` e
    ``_position_row`` di LiveTradingStrategy: status = nome di OrderStatus).
    Merge A+B: le regole sono quelle di ``db.soldi_sull_evento`` (cantiere A):
    ordine VIVO, posizione aperta (non pareggiata) e non regolata."""
    from types import SimpleNamespace

    from Betfair.stream import db as DB
    from Betfair.stream import runner as R

    righe = {
        "betfair_live_orders": [
            {"mode": "paper", "market_id": "1.10", "status": "EXECUTABLE"},
            {"mode": "live", "market_id": "1.11", "status": "EXECUTION_COMPLETE"},
            {"mode": "live", "market_id": "1.13", "status": "LAPSED"},
        ],
        "betfair_live_positions": [
            {"mode": "live", "market_id": "1.14", "matched_if_win": -5.0, "matched_if_lose": 3.2,
             "unmatched_back_exposure": 0.0, "unmatched_lay_exposure": 0.0},
            {"mode": "live", "market_id": "1.15", "matched_if_win": 1.5, "matched_if_lose": 1.5,
             "unmatched_back_exposure": 0.0, "unmatched_lay_exposure": 0.0},   # pareggiata
            {"mode": "paper", "market_id": "1.16", "matched_if_win": 4.0, "matched_if_lose": -2.0,
             "unmatched_back_exposure": 0.0, "unmatched_lay_exposure": 0.0},   # regolata
            {"mode": "live", "market_id": "1.17", "matched_if_win": 0.0, "matched_if_lose": 0.0,
             "unmatched_back_exposure": 2.0, "unmatched_lay_exposure": 0.0},   # non abbinato
        ],
        "betfair_live_settled": [{"mode": "paper", "market_id": "1.16"}],
    }
    monkeypatch.setattr(DB, "get_supabase_client",
                        lambda: SimpleNamespace(table=lambda t: _Query(righe, t)))
    out = R._mercati_con_soldi_dallo_specchio(["1.%d" % i for i in range(10, 18)])
    assert out == {"1.10", "1.14", "1.17"}

    def rotto():
        raise ConnectionError("DB giu'")
    monkeypatch.setattr(DB, "get_supabase_client", rotto)
    assert R._mercati_con_soldi_dallo_specchio(["1.10"]) == set()


def test_una_regola_sola_per_i_soldi_a_e_b(monkeypatch):
    """A (``soldi_sull_evento``) e B (``mercati_con_soldi``) passano dalla
    STESSA funzione per le posizioni aperte non regolate."""
    from Betfair.stream import db as DB

    chiamate: List[Any] = []
    vero = DB._posizioni_aperte_non_regolate

    def spia(sb: Any, righe: Any) -> Any:
        chiamate.append(len(righe))
        return vero(sb, righe)
    monkeypatch.setattr(DB, "_posizioni_aperte_non_regolate", spia)
    from types import SimpleNamespace

    vuoto = {"betfair_live_orders": [], "betfair_live_positions": [],
             "betfair_live_settled": [], "betfair_live_order_requests": []}

    class _Q(_Query):
        def eq(self, _c: str, _v: Any) -> "_Q":
            return self

        def in_(self, _c: str, _v: Any) -> "_Q":
            return self

        def execute(self) -> Any:
            return SimpleNamespace(data=list(self.righe[self.tabella]))
    monkeypatch.setattr(DB, "get_supabase_client",
                        lambda: SimpleNamespace(table=lambda t: _Q(vuoto, t)))
    assert DB.mercati_con_soldi(["1.1"]) == set()
    assert DB.soldi_sull_evento("35000001", ["1.1"]) is None
    assert len(chiamate) == 2


def test_sgancio_ricorda_le_voci_con_ordini():
    fw, _rec, live = _framework(["1.1"])
    g, _o, _a = _gestore()
    af = AF.AutoFollow(piano=AF.PianoFollow(g.capacita(None)), sottoscrittore=g)
    af.piano.richiedi("35000001", {"1.500"}, priorita=AF.PRI_CANDIDATA, protetti=set(),
                      puo_espellere=False, ora=0.0)
    af.aggancia(fw, ["1.1"])
    _ordine_nel_blotter(fw, live, "1.500")
    af.sgancia()
    assert "1.500" in af.mercati_da_proteggere()


def test_cablaggio_ricostruzione_con_soldi():
    import inspect

    from Betfair.stream import runner as R
    src = inspect.getsource(R.setup_and_run)
    assert "mercati_con_ordini_prec = _FR.mercati_con_ordini(framework)" in src
    i_soldi = src.index("auto.imposta_con_soldi(con_soldi)")
    assert i_soldi < src.index("auto.rientra_nel_tetto()")
    # merge A+B: i manuali davanti sono quelli VIVI (cantiere A)
    assert ("mercati_frammento0 = _frammento0(market_ids, "
            "mercati_manuali_da_sottoscrivere(session),") in src
    assert "market_ids = mercati_manuali_da_sottoscrivere(session)" in src


# ---------------------------------------------------------------------------
# 10. (coordinatore, punto 3) concorrenza e R-B1 sulle chiusure
# ---------------------------------------------------------------------------
def test_chiusura_di_un_frammento_non_rompe_chi_sta_leggendo():
    """``strategy.stream_ids`` e' una list comprehension su ``strategy.streams``
    (flumine ``strategy.py:238-242``) eseguita dal thread principale. Un
    ``remove`` sul posto durante quella lettura fa SALTARE l'elemento dopo:
    un book o una chiusura di un frammento sano persi. Qui: la lettura e' a
    meta' (due elementi consumati) quando il frammento 0 si chiude."""
    fw, rec, _live = _framework(_ids(0, 180))
    _collega(_market_streams(fw)[0])
    g, _o, _a = _gestore()
    g.applica(fw, _ids(0, 540))
    fr = FR.GestoreFrammenti.frammenti(fw)
    assert len(fr) == 3
    lettura = iter(rec.streams)
    visti = [next(lettura), next(lettura)]
    g._chiudi(fw, fr[0], "prova di concorrenza")
    visti += list(lettura)
    assert visti == fr, "la lettura in corso ha perso un frammento sano"
    # ``Streams.__iter__`` = ``iter(self._streams)`` (streams.py:321-322)
    prima = list(fw.streams)
    it_fw = iter(fw.streams)
    primo = next(it_fw)
    g._chiudi(fw, fr[1], "prova di concorrenza")
    assert [primo] + list(it_fw) == prima, "l'iterazione in corso ha perso uno stream"
    assert fr[2] in rec.streams and fr[1] not in rec.streams and fr[1] not in list(fw.streams)


def _chiudi_mercato(fw: Any, stream: Any, market_id: str) -> int:
    """Fa arrivare sul frammento la chiusura del mercato come la manda Betfair
    (``marketDefinition.status = CLOSED``) e la processa come il ciclo di
    flumine: ``_process_market_books`` -> ``CloseMarketEvent`` in coda ->
    ``_process_close_market``. Ritorna quante chiusure sono state processate."""
    import queue as _q

    from flumine.events.events import MarketBookEvent

    li = stream._listener
    d = dict(json.loads(json.dumps(_DEF)), status="OPEN")
    li.on_data(json.dumps({"op": "mcm", "id": stream.stream_id, "initialClk": "I",
                           "clk": "C1", "pt": int(time.time() * 1000), "ct": "SUB_IMAGE",
                           "mc": [{"id": market_id, "marketDefinition": d, "img": True,
                                   "rc": [{"atb": [[1.26, 8.54]], "id": 19}]}]}))
    d = dict(d, status="CLOSED", complete=True)
    li.on_data(json.dumps({"op": "mcm", "id": stream.stream_id, "clk": "C2",
                           "pt": int(time.time() * 1000) + 1,
                           "mc": [{"id": market_id, "marketDefinition": d}]}))
    libri = li.snap(market_ids=[market_id])
    fw._process_market_books(MarketBookEvent(libri))
    n = 0
    while True:
        try:
            ev = fw.handler_queue.get_nowait()
        except _q.Empty:
            return n
        if type(ev).__name__ == "CloseMarketEvent":
            fw._process_close_market(ev)
            n += 1


_DEF = {
    "bspMarket": False, "turnInPlayEnabled": True, "persistenceEnabled": True,
    "marketBaseRate": 5, "eventId": "35784105", "eventTypeId": "1", "numberOfWinners": 1,
    "bettingType": "ODDS", "marketType": "MATCH_ODDS", "marketTime": "2026-07-06T19:00:00.000Z",
    "suspendTime": "2026-07-06T19:00:00.000Z", "bspReconciled": False, "complete": True,
    "inPlay": True, "crossMatching": True, "runnersVoidable": False,
    "numberOfActiveRunners": 3, "betDelay": 5, "status": "OPEN", "betDelayModels": ["PASSIVE"],
    "runners": [{"status": "ACTIVE", "sortPriority": 1, "id": 19},
                {"status": "ACTIVE", "sortPriority": 2, "id": 22},
                {"status": "ACTIVE", "sortPriority": 3, "id": 58805}],
    "regulators": ["MR_ITA"], "discountAllowed": True, "timezone": "GMT",
    "openDate": "2026-07-06T19:00:00.000Z", "version": 7484715449,
    "priceLadderDefinition": {"type": "CLASSIC"},
}


def _conta_chiusure(monkeypatch, strategia: Any) -> List[str]:
    viste: List[str] = []
    originale = strategia.process_closed_market

    def spia(market: Any, market_book: Any) -> None:
        viste.append(market.market_id)
        originale(market, market_book)
    monkeypatch.setattr(strategia, "process_closed_market", spia)
    return viste


@pytest.mark.parametrize("modo", ["live", "paper"])
def test_rb1_chiusura_di_un_mercato_agganciato_a_caldo_arriva_una_volta(monkeypatch, modo):
    """Dopo la correzione: il mercato agganciato a caldo (frammento in piu')
    che si chiude arriva a ``process_closed_market`` della LiveTradingStrategy
    UNA volta; flumine processa UNA chiusura; il settled (upsert per
    ``(mode, market_id)``) e' scritto una volta."""
    from Betfair.stream.engine import live_trading_strategy as LTS

    scritti: List[Dict[str, Any]] = []
    monkeypatch.setattr(LTS, "_db", lambda: type("D", (), {
        "upsert_live_settled": staticmethod(lambda r: scritti.append(r))}))
    fw, _rec, live = _framework(_ids(0, 180))
    live.mode = modo
    _collega(_market_streams(fw)[0])
    g, _o, _a = _gestore()
    g.applica(fw, _ids(0, 180) + ["1.259691614"])
    nuovo = FR.GestoreFrammenti.frammenti(fw)[1]
    viste = _conta_chiusure(monkeypatch, live)
    _ordine_nel_blotter(fw, live, "1.259691614")
    ordine = list(fw.markets.markets["1.259691614"].blotter)[0]
    # profitto del simulato (proprieta' calcolata di flumine): 1,50 per la prova
    monkeypatch.setattr(type(ordine.simulated), "profit", property(lambda _s: 1.5))
    assert _chiudi_mercato(fw, nuovo, "1.259691614") == 1
    assert viste == ["1.259691614"]
    if modo == "paper":
        assert len(scritti) == 1 and scritti[0]["market_id"] == "1.259691614"
        assert scritti[0]["mode"] == "paper"
    else:
        assert scritti == []          # live: il realizzato viene dai cleared orders


def test_rb1_il_vecchio_modo_non_vedeva_la_chiusura(monkeypatch):
    """Controllo NEGATIVO: con la strategia degli ordini sulla SECONDA
    connessione (il modo di prima) la chiusura del mercato agganciato a caldo
    non le arriva mai."""
    fw, rec, _live = _framework(_ids(0, 180))
    vecchia = LiveTradingStrategy(market_filter=rec.market_filter, session=None, mode="paper",
                                  name="vecchio_modo_chiusure")
    fw.add_strategy(vecchia)
    base = [s for s in _market_streams(fw) if s in rec.streams][0]
    _collega(base)
    for s in _market_streams(fw):
        if s is not base:
            _collega(s)
    g, _o, _a = _gestore()
    # il gestore vede la seconda MarketStream come un frammento: la si esclude
    # simulando il vecchio SottoscrittoreStream (solo lo stream del recorder)
    SC.sottoscrivi(fw, base, _ids(0, 180) + ["1.259691614"])
    viste = _conta_chiusure(monkeypatch, vecchia)
    assert _chiudi_mercato(fw, base, "1.259691614") == 1
    assert viste == []
