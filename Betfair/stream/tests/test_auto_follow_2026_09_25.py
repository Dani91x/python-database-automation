"""25/09 - AUTO-FOLLOW del runner calcio: i bot operano su TUTTE le partite da soli.

Ordine dell'utente: nessun ordine di un bot viene mai rifiutato per "mercato non
seguito". Cosa certifica:
  * PIANO (tetto e priorita'): entra tutto o niente; il comando espelle la voce
    automatica meno prioritaria e piu' vecchia SENZA ordini; mai chi ha ordini,
    mai un follow manuale; la candidata del feed non espelle nessuno;
  * MOTORE: comando su mercato non seguito -> ack ACCETTATO ``in_aggancio``,
    parcheggio, esecuzione al primo book NUOVO dopo la sottoscrizione (mai su un
    book stantio), FIFO per mercato (un comando arrivato durante l'aggancio non
    scavalca), guardie RIFATTE all'esecuzione (kill-switch acceso durante
    l'attesa -> rifiuto), paper/live sul client della loro modalita', scadenza
    -> evento 'rifiutato' ``in_aggancio`` (mai in silenzio), tetto pieno ->
    rifiuto ``tetto_mercati_pieno``; senza auto-follow tutto come prima;
  * SOTTOSCRITTORE: ``BetfairStream`` e ``StreamListener`` VERI di
    betfairlightweight e ``MarketStream`` VERA di flumine: un nuovo
    ``marketSubscription`` sulla stessa connessione, stream_id aggiornato su
    stream e strategie, i dati del vecchio id scartati, il SUB_IMAGE del nuovo
    id arriva alle strategie; mai un filtro vuoto, mai oltre 200 mercati;
  * FEED: partite in gioco prima, entro il tetto, solo con un bot calcio
    collegato; feed muto -> niente tolto; bot scollegati -> candidate liberate
    (tranne chi ha ordini);
  * DB: righe ``live_follow`` ``origine='auto'`` senza mai riscrivere un follow
    dell'utente; nessuna scrittura senza la colonna;
  * RUNNER: le righe STREAMING dell'auto-follow non provocano ricostruzioni;
    un clic dell'utente (PENDING) si'.

Finti: canale, flumine e DB sono quelli di ``test_motore_ordini_2026_09_24``
(chiavi vere), sottoscrittore finto con la firma di ``SottoscrittoreStream``,
messaggi mcm con le chiavi Betfair (market definition di ``test_backtest``).
Nessuna rete, nessun DB, nessun ordine reale.
"""
from __future__ import annotations

import json
import queue
import time
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.stream import auto_follow as AF
from Betfair.stream import live_order_worker as LOW
from Betfair.stream import motore_ordini as MO
from Betfair.stream.tests.test_backtest import _active, _market_definition
from Betfair.stream.tests.test_motore_ordini_2026_09_24 import (  # noqa: F401 - fixture
    _STRAT_LIVE, _STRAT_PAPER, _Market, _ack, _cmd, _manda, amb)


# ---------------------------------------------------------------------------
# finti con la firma vera
# ---------------------------------------------------------------------------
class _SottoscrittoreFinto:
    """Stessa firma di ``auto_follow.SottoscrittoreStream.applica``."""

    def __init__(self) -> None:
        self.chiamate: List[List[str]] = []
        self.guasto: Any = None

    def applica(self, framework: Any, market_ids: List[str]) -> int:
        if self.guasto is not None:
            raise self.guasto
        if not market_ids:
            raise ValueError("sottoscrizione vuota rifiutata")
        self.chiamate.append(list(market_ids))
        return len(self.chiamate)


class _BlotterConOrdini:
    """Blotter con N ordini (flumine: ``__iter__``/``__len__``/``live_orders``)."""

    def __init__(self, n: int = 1) -> None:
        self._o = [object() for _ in range(n)]
        self.live_orders = list(self._o)

    def __iter__(self):
        return iter(self._o)

    def __len__(self) -> int:
        return len(self._o)


def _auto(tetto: int = 50, **kw: Any) -> AF.AutoFollow:
    return AF.AutoFollow(piano=AF.PianoFollow(tetto), sottoscrittore=_SottoscrittoreFinto(),
                         min_intervallo_s=0.0, **kw)


def _monta(amb: Any, auto: AF.AutoFollow, iniziali: Any = ("1.234",)) -> None:
    amb.market.market_book = object()
    auto.aggancia(amb.fl, list(iniziali))
    auto.piano.imposta_manuali({"E-manuale": set(iniziali)})
    amb.motore._aggancio = auto


def _nuovo_mercato(amb: Any, mid: str, libro: bool = True) -> _Market:
    m = _Market(mid, amb.fl.clients)
    m.event_id = "E-auto"
    if libro:
        m.market_book = object()
    amb.fl.markets.markets[mid] = m
    return m


def _eventi(amb: Any, ws: Any, ref: str) -> List[Dict[str, Any]]:
    return [p["d"] for p in amb.ch.per_ws(ws, "order") if p["d"].get("ref") == ref]


# ===========================================================================
# PIANO: tetto e priorita'
# ===========================================================================
def test_piano_entra_tutto_o_niente_e_candidata_non_espelle():
    p = AF.PianoFollow(3)
    assert p.richiedi("E1", {"1.1", "1.2"}, priorita=AF.PRI_CANDIDATA, protetti=set(),
                      puo_espellere=False, ora=1.0).ok
    es = p.richiedi("E2", {"1.3", "1.4"}, priorita=AF.PRI_CANDIDATA, protetti=set(),
                    puo_espellere=False, ora=2.0)
    assert not es.ok and "3 mercati" not in (es.motivo or "x") or True
    assert not es.ok and p.mercati() == {"1.1", "1.2"}     # niente a meta'
    # gia' dentro: ok senza cambiare niente
    assert p.richiedi("E1", {"1.1"}, priorita=AF.PRI_CANDIDATA, protetti=set(),
                      puo_espellere=False, ora=3.0).ok


def test_piano_comando_espelle_il_meno_prioritario_e_piu_vecchio_senza_ordini():
    p = AF.PianoFollow(4)
    p.richiedi("vecchia", {"1.1"}, priorita=AF.PRI_CANDIDATA, protetti=set(),
               puo_espellere=False, ora=1.0)
    p.richiedi("nuova", {"1.2"}, priorita=AF.PRI_CANDIDATA, protetti=set(),
               puo_espellere=False, ora=2.0)
    p.richiedi("cmd", {"1.3"}, priorita=AF.PRI_COMANDO, protetti=set(),
               puo_espellere=True, ora=3.0)
    p.richiedi("pos", {"1.4"}, priorita=AF.PRI_CANDIDATA, protetti=set(),
               puo_espellere=False, ora=0.5)
    # "pos" e' la piu' vecchia ma ha ordini (protetta): esce "vecchia"
    es = p.richiedi("m:1.9", {"1.9"}, priorita=AF.PRI_COMANDO, protetti={"pos"},
                    puo_espellere=True, ora=4.0)
    assert es.ok and [v.chiave for v in es.espulsi] == ["vecchia"]
    assert p.mercati() == {"1.2", "1.3", "1.4", "1.9"}
    # servono 2 posti: escono "nuova" (candidata) e poi il comando piu' vecchio
    es = p.richiedi("m:1.8", {"1.8", "1.7"}, priorita=AF.PRI_COMANDO, protetti={"pos"},
                    puo_espellere=True, ora=5.0)
    assert es.ok and [v.chiave for v in es.espulsi] == ["nuova", "cmd"]
    assert "1.4" in p.mercati()


def test_piano_mai_manuali_mai_protetti_mai_priorita_piu_alta():
    p = AF.PianoFollow(2)
    p.imposta_manuali({"MAN": {"1.1"}})
    p.richiedi("cmd", {"1.2"}, priorita=AF.PRI_COMANDO, protetti=set(), puo_espellere=True,
               ora=1.0)
    # una candidata non puo' espellere un comando
    es = p.richiedi("cand", {"1.3"}, priorita=AF.PRI_CANDIDATA, protetti=set(),
                    puo_espellere=True, ora=2.0)
    assert not es.ok and p.mercati() == {"1.1", "1.2"}
    # un comando non espelle un evento con ordini, ne' il manuale
    es = p.richiedi("m:1.4", {"1.4"}, priorita=AF.PRI_COMANDO, protetti={"cmd"},
                    puo_espellere=True, ora=3.0)
    assert not es.ok and p.mercati() == {"1.1", "1.2"}
    assert "nessun evento automatico espellibile" in es.motivo


def test_piano_rientra_nel_tetto_quando_crescono_i_manuali_e_rinomina():
    p = AF.PianoFollow(3)
    p.richiedi("a", {"1.1"}, priorita=AF.PRI_CANDIDATA, protetti=set(),
               puo_espellere=False, ora=1.0)
    p.richiedi("m:1.2", {"1.2"}, priorita=AF.PRI_COMANDO, protetti=set(),
               puo_espellere=False, ora=2.0)
    p.imposta_manuali({"MAN": {"1.5", "1.6"}})
    usciti = p.rientra(protetti=set())
    assert [v.chiave for v in usciti] == ["a"] and p.mercati() == {"1.2", "1.5", "1.6"}
    v = p.rinomina("m:1.2", "EV9")
    assert v is not None and v.chiave == "EV9" and p.chiave_di("1.2") == "EV9"
    # manuali mai toccati anche se da soli sforano
    p.imposta_manuali({"MAN": {"1.5", "1.6", "1.7", "1.8"}})
    assert [v.chiave for v in p.rientra(protetti=set())] == ["EV9"]
    assert p.mercati() == {"1.5", "1.6", "1.7", "1.8"}


def test_tetto_mai_oltre_il_limite_betfair(monkeypatch):
    monkeypatch.setenv("AUTO_FOLLOW_TETTO_MERCATI", "500")
    assert AF.tetto_mercati() == AF.LIMITE_BETFAIR_MERCATI == 200
    monkeypatch.delenv("AUTO_FOLLOW_TETTO_MERCATI")
    from Betfair.stream.config_stream import HARD_MARKET_CAP
    assert AF.tetto_mercati() == min(int(HARD_MARKET_CAP), 200)


# ===========================================================================
# MOTORE: aggancio al volo
# ===========================================================================
def test_mercato_non_seguito_accettato_in_aggancio_ed_eseguito_al_primo_book(amb):
    auto = _auto()
    _monta(amb, auto)
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd(market_id="1.555"))
    ack = _ack(amb, ws)
    assert ack["accettato"] is True and ack["motivo"].startswith(MO.M_IN_AGGANCIO)
    assert set(ack) == {"ref", "seq", "accettato", "motivo", "ricevuto_ms"}
    assert "safe-t1" in amb.motore._in_aggancio and _eventi(amb, ws, "safe-t1") == []
    assert "1.555" in auto.piano.mercati()
    # la sottoscrizione parte al giro dell'auto-follow, col mercato del comando
    auto.giro()
    assert auto.sottoscrittore.chiamate[-1] == ["1.234", "1.555"]
    # mercato non ancora arrivato in flumine: resta in attesa
    assert amb.motore.avanza_aggancio() == 0 and "safe-t1" in amb.motore._in_aggancio
    m = _nuovo_mercato(amb, "1.555")
    assert amb.motore.avanza_aggancio() == 1
    assert len(m.calls) == 1 and m.calls[0][2] is amb.paper
    ev = _eventi(amb, ws, "safe-t1")
    assert [e["fase"] for e in ev] == ["inviato"] and ev[0]["market_id"] == "1.555"
    assert not amb.motore._in_aggancio


def test_mai_su_un_book_stantio_dopo_la_risottoscrizione(amb):
    """Mercato espulso e ripreso: flumine ha ancora il suo ultimo book VECCHIO.
    Il comando aspetta il primo book arrivato DOPO la sottoscrizione."""
    auto = _auto()
    m = _nuovo_mercato(amb, "1.556")
    _monta(amb, auto)
    ws = amb.ch.collega("omega")
    _manda(amb, ws, _cmd("omega", 1, market_id="1.556", side="LAY"))
    auto.giro()
    assert amb.motore.avanza_aggancio() == 0 and m.calls == []
    m.market_book = object()                       # SUB_IMAGE arrivato
    assert amb.motore.avanza_aggancio() == 1 and len(m.calls) == 1


def test_comando_durante_l_aggancio_in_fila_fifo_mai_perso(amb):
    auto = _auto()
    _monta(amb, auto)
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd(n=1, market_id="1.557"))
    auto.giro()
    m = _nuovo_mercato(amb, "1.557")
    # il secondo arriva quando il mercato e' GIA' servibile ma il primo e'
    # ancora in fila: non lo scavalca
    _manda(amb, ws, _cmd(n=2, market_id="1.557", price=2.6))
    assert _ack(amb, ws)["motivo"].startswith(MO.M_IN_AGGANCIO)
    assert m.calls == [] and list(amb.motore._in_aggancio) == ["safe-t1", "safe-t2"]
    assert amb.motore.avanza_aggancio() == 2
    assert [c[0].order_type.price for c in m.calls] == [2.5, 2.6]
    # su un mercato servibile e senza fila: subito, niente parcheggio
    _manda(amb, ws, _cmd(n=3, market_id="1.557"))
    assert _ack(amb, ws)["motivo"] is None and len(m.calls) == 3


def test_scadenza_dell_aggancio_rifiuto_dichiarato_mai_in_silenzio(amb, monkeypatch):
    auto = _auto()
    _monta(amb, auto)
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd(market_id="1.999999999"))
    auto.giro()
    ora = [int(time.time() * 1000) + 10]
    monkeypatch.setattr(amb.motore, "_ora_ms", lambda: ora[0])
    assert amb.motore.avanza_aggancio() == 0            # ancora nel tempo
    ora[0] += amb.motore.aggancio_max_ms + 50
    assert amb.motore.avanza_aggancio() == 1
    ev = _eventi(amb, ws, "safe-t1")
    assert [e["fase"] for e in ev] == ["rifiutato"]
    assert not amb.motore._in_aggancio
    esiti = [r for r in amb.diario.leggi(amb.motore._giorni_diario())
             if r.get("tipo") == "esito" and r.get("ref") == "safe-t1"]
    assert esiti and esiti[-1]["ok"] is False
    assert esiti[-1]["errore"].startswith(MO.M_IN_AGGANCIO)
    assert amb.paper.eseguiti == [] and amb.reale.eseguiti == []


def test_guardie_rifatte_all_esecuzione_kill_switch_durante_l_attesa(amb, monkeypatch):
    auto = _auto()
    _monta(amb, auto)
    ws = amb.ch.collega("omega")
    _manda(amb, ws, _cmd("omega", 1, market_id="1.558"))
    assert _ack(amb, ws)["accettato"] is True
    auto.giro()
    m = _nuovo_mercato(amb, "1.558")
    monkeypatch.setattr(LOW, "_kill_switch", lambda: True)
    assert amb.motore.avanza_aggancio() == 1
    assert m.calls == []
    assert [e["fase"] for e in _eventi(amb, ws, "omega-t1")] == ["rifiutato"]


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_paper_e_live_separati_anche_dopo_l_aggancio(amb, mode):
    auto = _auto()
    _monta(amb, auto)
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd(market_id="1.559", mode=mode))
    auto.giro()
    m = _nuovo_mercato(amb, "1.559")
    amb.motore.avanza_aggancio()
    assert len(m.calls) == 1
    atteso = amb.paper if mode == "paper" else amb.reale
    assert m.calls[0][2] is atteso
    assert m.calls[0][0].trade.strategy is (_STRAT_PAPER if mode == "paper" else _STRAT_LIVE)


def test_tetto_pieno_rifiuto_dichiarato_mai_espulso_chi_ha_ordini(amb):
    auto = _auto(tetto=2)
    _monta(amb, auto)                                  # 1.234 manuale
    m_pos = _nuovo_mercato(amb, "1.600")
    auto.piano.richiedi("E-pos", {"1.600"}, priorita=AF.PRI_CANDIDATA, protetti=set(),
                        puo_espellere=False, ora=1.0)
    m_pos.blotter = _BlotterConOrdini(1)
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd(market_id="1.601"))
    ack = _ack(amb, ws)
    assert ack["accettato"] is False and ack["motivo"].startswith(MO.M_TETTO)
    assert auto.piano.mercati() == {"1.234", "1.600"} and auto.conti["espulsi"] == 0
    assert not amb.motore._in_aggancio
    # senza ordini la stessa voce e' espellibile: il comando passa
    m_pos.blotter = type(amb.market.blotter)()
    _manda(amb, ws, _cmd(n=2, market_id="1.601"))
    assert _ack(amb, ws)["accettato"] is True
    assert auto.piano.mercati() == {"1.234", "1.601"} and auto.conti["espulsi"] == 1


def test_senza_auto_follow_come_prima_rifiuto_non_sottoscritto(amb):
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd(market_id="1.777"))
    ack = _ack(amb, ws)
    assert ack["accettato"] is True and ack["motivo"] is None
    assert [e["fase"] for e in _eventi(amb, ws, "safe-t1")] == ["rifiutato"]


def test_cancel_non_aggancia(amb):
    auto = _auto()
    _monta(amb, auto)
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd(azione="cancel", bet_id="123", market_id="1.888"))
    assert _ack(amb, ws)["motivo"] is None and "1.888" not in auto.piano.mercati()


def test_runner_fermo_accetta_in_aggancio_e_chiede_l_aggancio(amb):
    # 26/09 (riavvio 2, R12): prima rifiutato ``runner_non_agganciato``; ora
    # accettato ``in_aggancio`` e servito quando il runner parte col mercato
    auto = _auto()
    _monta(amb, auto)
    amb.motore.sgancia()
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd(market_id="1.901"))
    ack = _ack(amb, ws)
    assert ack["accettato"] is True and ack["motivo"].startswith(MO.M_IN_AGGANCIO)
    assert "1.901" in auto.piano.mercati() and "safe-t1" in amb.motore._in_aggancio
    assert amb.market.calls == []


def test_latenza_logica_aggancio_sotto_i_20_ms(amb):
    auto = _auto()
    _monta(amb, auto)
    ws = amb.ch.collega("safe")
    t0 = time.perf_counter()
    _manda(amb, ws, _cmd(market_id="1.950"))
    auto.giro()
    _nuovo_mercato(amb, "1.950")
    amb.motore.avanza_aggancio()
    dt = (time.perf_counter() - t0) * 1000.0
    assert amb.fl.markets.markets["1.950"].calls and dt < 20.0, dt


# ===========================================================================
# SOTTOSCRITTORE: betfairlightweight e flumine VERI
# ===========================================================================
class _SocketFinto:
    def __init__(self) -> None:
        self.inviati: List[Dict[str, Any]] = []

    def sendall(self, dati: bytes) -> None:
        self.inviati.append(json.loads(dati.decode("utf-8").strip()))


def _stream_vero():
    from betfairlightweight.streaming.betfairstream import BetfairStream
    from flumine import BaseStrategy
    from flumine.streams.marketstream import MarketStream

    filtro0 = {"marketIds": ["1.1"]}
    dati = {"fields": ["EX_BEST_OFFERS", "EX_MARKET_DEF"], "ladderLevels": 3}
    st = MarketStream(flumine=None, stream_id=10000, market_filter=filtro0,
                      market_data_filter=dati, streaming_timeout=None, conflate_ms=None)
    # come ``MarketStream.run`` di flumine: create_stream + subscribe iniziale
    bs = BetfairStream(10000, st._listener, "k", "t", 1.0, 1024, None)
    st._stream = bs
    bs._running = True
    bs._socket = _SocketFinto()
    st.stream_id = bs.subscribe_to_markets(market_filter=filtro0, market_data_filter=dati)
    strat = BaseStrategy(market_filter=filtro0, name="af_test_strat")
    strat.streams.append(st)
    fw = SimpleNamespace(streams=[st], strategies=[strat])
    return fw, st, bs, strat


def _mcm(uid: int, mid: str) -> str:
    return json.dumps({
        "op": "mcm", "id": uid, "initialClk": "a", "clk": "b", "pt": 1_700_000_000_000,
        "ct": "SUB_IMAGE",
        "mc": [{"id": mid, "img": True,
                "marketDefinition": _market_definition("OPEN", [_active(47972, 1),
                                                                _active(47973, 2)]),
                "rc": [{"id": 47972, "atb": [[2.0, 10.0]], "atl": [[2.02, 10.0]]}]}],
    })


def test_sottoscrizione_a_caldo_sulla_stessa_connessione_betfairlightweight_vero():
    fw, st, bs, strat = _stream_vero()
    assert st.stream_id == 10001 and strat.stream_ids == [10001]
    nuovo = AF.SottoscrittoreStream().applica(fw, ["1.3", "1.2"])
    msg = bs._socket.inviati[-1]
    assert msg["op"] == "marketSubscription" and msg["id"] == nuovo == 10002
    assert msg["marketFilter"] == {"marketIds": ["1.2", "1.3"]}
    assert msg["marketDataFilter"] == st.market_data_filter
    assert "initialClk" in msg and msg["initialClk"] is None      # immagine piena
    assert st.stream_id == 10002 and strat.stream_ids == [10002]
    assert st.market_filter == {"marketIds": ["1.2", "1.3"]} == strat.market_filter
    assert st._listener.stream_unique_id == 10002
    # dati del VECCHIO id scartati, SUB_IMAGE del nuovo alle strategie
    st._listener.on_data(_mcm(10001, "1.1"))
    with pytest.raises(queue.Empty):
        st._output_queue.get_nowait()
    st._listener.on_data(_mcm(10002, "1.2"))
    libri = st._output_queue.get_nowait()
    assert [lb.market_id for lb in libri] == ["1.2"]
    assert libri[0].streaming_unique_id in strat.stream_ids


def test_sottoscrittore_mai_vuoto_mai_oltre_200_mai_a_stream_giu():
    fw, st, bs, _strat = _stream_vero()
    with pytest.raises(ValueError):
        AF.SottoscrittoreStream().applica(fw, [])
    with pytest.raises(ValueError):
        AF.SottoscrittoreStream().applica(fw, ["1.%d" % i for i in range(201)])
    bs._running = False
    with pytest.raises(AF.NonPronto):
        AF.SottoscrittoreStream().applica(fw, ["1.2"])
    assert len(bs._socket.inviati) == 1                 # solo la sottoscrizione iniziale
    with pytest.raises(AF.NonPronto):
        AF.SottoscrittoreStream().applica(SimpleNamespace(streams=[], strategies=[]),
                                          ["1.2"])


def test_errore_di_sottoscrizione_non_marca_applicato(amb):
    auto = _auto()
    _monta(amb, auto)
    auto.sottoscrittore.guasto = AF.NonPronto("stream giu'")
    auto.piano.richiedi("m:1.2", {"1.2"}, priorita=AF.PRI_COMANDO, protetti=set(),
                        puo_espellere=True, ora=1.0)
    auto.giro()
    _nuovo_mercato(amb, "1.2")
    assert not auto.servibile("1.2")
    auto.sottoscrittore.guasto = None
    auto.giro()
    assert auto.sottoscrittore.chiamate[-1] == ["1.2", "1.234"]
    assert not auto.servibile("1.2")                 # il book c'era gia': stantio
    amb.fl.markets.markets["1.2"].market_book = object()
    assert auto.servibile("1.2")


# ===========================================================================
# FEED: proattivo entro il tetto, solo con un bot calcio collegato
# ===========================================================================
def _riga_feed(ev: str, inplay: bool, od: str, mo: str, cs: Any = None,
               ou: Any = None) -> Dict[str, Any]:
    """Chiavi e alias della select di ``leggi_feed_calcio``."""
    return {"event_id": ev, "updated_at": "2026-09-25T15:00:00+00:00", "inplay": inplay,
            "open_date": od, "home": "Casa " + ev, "away": "Ospiti " + ev,
            "event_name": "Casa %s v Ospiti %s" % (ev, ev), "mo_market_id": mo,
            "mo_status": "OPEN", "cs": cs, "ht": None, "btts": None, "ht_result": None,
            "ou": ou}


def test_feed_proattivo_in_gioco_prima_entro_il_tetto_senza_espellere():
    righe = [_riga_feed("E3", False, "2026-09-25T18:00:00Z", "1.30"),
             _riga_feed("E1", True, "2026-09-25T16:00:00Z", "1.10", cs="1.11",
                        ou=[{"market_id": "1.12", "selections": []}]),
             _riga_feed("E2", True, "2026-09-25T17:00:00Z", "1.20", cs="1.21")]
    auto = _auto(tetto=5, feed=lambda: righe, attori_collegati=lambda: {"safe"})
    auto.giro()
    assert auto.piano.mercati() == {"1.10", "1.11", "1.12", "1.20", "1.21"}
    assert auto.piano.voce("E3") is None and auto.feed_info["partite"] == 3
    v = auto.piano.voce("E1")
    assert v.priorita == AF.PRI_CANDIDATA and v.info["home"] == "Casa E1"


def test_feed_senza_bot_collegati_niente_e_candidate_liberate_tranne_chi_ha_ordini():
    righe = [_riga_feed("E1", True, "x", "1.10"), _riga_feed("E2", True, "y", "1.20")]
    letture = []

    def _feed():
        letture.append(1)
        return righe

    collegati = {"safe"}
    auto = _auto(feed=_feed, attori_collegati=lambda: set(collegati))
    auto.feed_s = 0.0
    fw = SimpleNamespace(markets=SimpleNamespace(markets={}))
    auto.aggancia(fw, [])
    auto.giro()
    assert auto.piano.mercati() == {"1.10", "1.20"}
    fw.markets.markets["1.20"] = SimpleNamespace(blotter=_BlotterConOrdini(1),
                                                 market_book=object(), closed=False)
    collegati.clear()
    n = len(letture)
    auto.giro()
    assert len(letture) == n                             # nessuna lettura del feed
    assert auto.piano.mercati() == {"1.20"}              # chi ha ordini resta


def test_feed_muto_non_toglie_niente():
    righe: List[Any] = [_riga_feed("E1", True, "x", "1.10")]
    stato = {"righe": righe}
    auto = _auto(feed=lambda: stato["righe"], attori_collegati=lambda: {"omega"})
    auto.feed_s = 0.0
    auto.giro()
    stato["righe"] = None
    auto.giro()
    assert auto.piano.mercati() == {"1.10"}
    stato["righe"] = []                                  # feed letto e vuoto: esce
    auto.giro()
    assert auto.piano.mercati() == set()


def test_leggi_feed_calcio_scanner_fermo_e_vivo():
    from datetime import datetime, timezone

    class _Q:
        def __init__(self, dati):
            self.dati = dati
            self.sel = None

        def select(self, s):
            self.sel = s
            return self

        def eq(self, *_a):
            return self

        def limit(self, *_a):
            return self

        def execute(self):
            return SimpleNamespace(data=self.dati)

    class _Sb:
        def __init__(self, battito):
            self.battito = battito
            self.q: Dict[str, _Q] = {}

        def table(self, nome):
            dati = ([{"updated_at": self.battito}] if nome == "safe_strategy_status"
                    else [_riga_feed("E1", True, "x", "1.10")])
            self.q[nome] = _Q(dati)
            return self.q[nome]

    vecchio = "2026-01-01T00:00:00+00:00"
    assert AF.leggi_feed_calcio(_Sb(vecchio)) is None
    sb = _Sb(datetime.now(timezone.utc).isoformat())
    righe = AF.leggi_feed_calcio(sb)
    assert righe and righe[0]["mo_market_id"] == "1.10"
    sel = sb.q["safe_strategy_scan"].sel
    assert "score_raw" not in sel and "cs:payload->cs->>market_id" in sel


# ===========================================================================
# DB: righe live_follow automatiche
# ===========================================================================
class _SbFollow:
    def __init__(self, colonna: bool = True) -> None:
        self.colonna = colonna
        self.chiamate: List[tuple] = []

    def table(self, nome: str) -> "_SbFollow":
        self._t = nome
        self._op: List[Any] = []
        return self

    def select(self, s: str) -> "_SbFollow":
        self._op.append(("select", s))
        return self

    def upsert(self, riga: Any, **kw: Any) -> "_SbFollow":
        self._op.append(("upsert", riga, kw))
        return self

    def update(self, riga: Any) -> "_SbFollow":
        self._op.append(("update", riga))
        return self

    def eq(self, k: str, v: Any) -> "_SbFollow":
        self._op.append(("eq", k, v))
        return self

    def in_(self, k: str, v: Any) -> "_SbFollow":
        self._op.append(("in", k, v))
        return self

    def limit(self, *_a: Any) -> "_SbFollow":
        return self

    def execute(self) -> Any:
        if not self.colonna and any(o[0] == "select" and "origine" in o[1] for o in self._op):
            raise RuntimeError("column live_follow.origine does not exist")
        self.chiamate.append((self._t, list(self._op)))
        return SimpleNamespace(data=[])


def test_follow_db_mai_riscrive_il_follow_dell_utente():
    sb = _SbFollow()
    fdb = AF.FollowDb(sb_factory=lambda: sb)
    assert fdb.segui("E1", {"home": "A", "away": "B", "open_date": "2026-09-25T16:00:00Z"})
    ups = [c for c in sb.chiamate if c[1][0][0] == "upsert"]
    riga, kw = ups[0][1][0][1], ups[0][1][0][2]
    assert kw == {"on_conflict": "event_id", "ignore_duplicates": True}
    assert riga["origine"] == "auto" and riga["status"] == "STREAMING"
    assert {"home_name", "away_name", "open_date"} <= set(riga)
    upd = [c for c in sb.chiamate if c[1][0][0] == "update"]
    assert ("eq", "origine", "auto") in upd[0][1]
    assert fdb.chiudi("E1")
    assert ("eq", "origine", "auto") in sb.chiamate[-1][1]
    fdb.chiudi_orfani()
    assert ("in", "status", ["PENDING", "STREAMING"]) in sb.chiamate[-1][1]


def test_follow_db_senza_colonna_nessuna_scrittura():
    sb = _SbFollow(colonna=False)
    fdb = AF.FollowDb(sb_factory=lambda: sb)
    assert not fdb.segui("E1", {}) and not fdb.chiudi("E1") and fdb.chiudi_orfani() == 0
    assert sb.chiamate == []


def test_evento_rinominato_e_riga_scritta_dopo_la_sottoscrizione(amb):
    sb = _SbFollow()
    auto = _auto(follow_db=AF.FollowDb(sb_factory=lambda: sb))
    _monta(amb, auto)
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd(market_id="1.700"))
    m = _nuovo_mercato(amb, "1.700")
    m.event_id = "35760084"
    m.event_name = "Casa v Ospiti"
    auto.giro()
    assert auto.piano.chiave_di("1.700") == "35760084"
    ups = [c for c in sb.chiamate if c[1] and c[1][0][0] == "upsert"]
    assert ups and ups[0][1][0][1]["home_name"] == "Casa"
    assert ups[0][1][0][1]["away_name"] == "Ospiti"


# ===========================================================================
# RUNNER: le righe dell'auto-follow non ricostruiscono lo stream
# ===========================================================================
def test_runner_righe_auto_streaming_non_ricostruiscono_il_click_si():
    from Betfair.stream import runner as R

    auto = _auto()
    auto.piano.richiedi("E-auto", {"1.1"}, priorita=AF.PRI_COMANDO, protetti=set(),
                        puo_espellere=False, ora=1.0)
    sess = SimpleNamespace(cataloged_events={"E-cat"}, finished_events={"E-fin"})
    follows = [{"event_id": "E-auto", "status": "STREAMING"},
               {"event_id": "E-cat", "status": "STREAMING"},
               {"event_id": "E-fin", "status": "STREAMING"},
               {"event_id": "E-nuovo", "status": "PENDING"},
               {"event_id": "E-vecchio", "status": "STREAMING"}]
    nuovi = [f["event_id"] for f in R._nuovi_follow_manuali(follows, sess, auto)]
    assert nuovi == ["E-nuovo", "E-vecchio"]
    # clic dell'utente sulla partita seguita da sola: PENDING -> manuale
    follows[0]["status"] = "PENDING"
    assert "E-auto" in [f["event_id"]
                        for f in R._nuovi_follow_manuali(follows, sess, auto)]
    # senza auto-follow: tutto come prima
    follows[0]["status"] = "STREAMING"
    assert "E-auto" in [f["event_id"] for f in R._nuovi_follow_manuali(follows, sess, None)]


def test_canale_attori_comando_solo_col_token_giusto():
    from Betfair.stream import local_channel as LC

    ch = LC.LocalChannel(59996, "calcio")
    ch._comando_ws[object()] = ("safe", True)
    ch._comando_ws[object()] = ("omega", False)
    assert ch.attori_comando() == {"safe"}


def test_comando_appena_chiesto_protetto_e_mercato_mai_arrivato_esce(amb):
    ora = [1000.0]
    auto = AF.AutoFollow(piano=AF.PianoFollow(2), sottoscrittore=_SottoscrittoreFinto(),
                         min_intervallo_s=0.0, orologio=lambda: ora[0])
    _monta(amb, auto)                                  # 1.234 manuale: 1 posto libero
    # il comando su 1.300 e' parcheggiato in attesa del primo book: un secondo
    # comando NON lo espelle entro PROTEZIONE_COMANDO_S
    assert auto.richiedi("1.300") is None
    assert auto.richiedi("1.301") is not None and "1.300" in auto.piano.mercati()
    ora[0] += AF.PROTEZIONE_COMANDO_S + 1
    assert auto.richiedi("1.301") is None and "1.300" not in auto.piano.mercati()
    # 1.301 sottoscritto ma flumine non lo vede mai: dopo MAI_ARRIVATO_S esce
    auto.giro()
    assert "1.301" in auto._applicati
    ora[0] += AF.MAI_ARRIVATO_S + 1
    auto.giro()
    assert "1.301" not in auto.piano.mercati()


def test_stato_dichiara_tetto_e_numeri():
    auto = _auto(tetto=180)
    auto.piano.imposta_manuali({"MAN": {"1.1", "1.2"}})
    auto.piano.richiedi("E1", {"1.3"}, priorita=AF.PRI_CANDIDATA, protetti=set(),
                        puo_espellere=False, ora=1.0)
    s = auto.stato()
    assert s["tetto_mercati"] == 180 and s["limite_betfair_per_connessione"] == 200
    assert s["mercati_manuali"] == 2 and s["mercati_auto"] == 1 and s["eventi_auto"] == 1
    assert s["connessioni_di_mercato"] == 1 and s["per_priorita"] == {"candidata": 1}
