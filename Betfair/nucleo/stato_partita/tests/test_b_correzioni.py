"""W1-B - correzioni dopo la revisione indipendente di ``be3cf075``.

Ogni test riproduce un difetto trovato dal revisore (o una mutazione sopravvissuta)
e prova la correzione; i nomi dei punti sono quelli della richiesta del
coordinatore (1-8). I finti: ``FonteInMemoria`` restituisce buste con la forma di
``adattatori/lettura.py``; i book "rotti" o sintetici hanno SOLO le chiavi che il
codice legge (``market_id``, ``inplay``, ``status``, ``market_definition``).
"""
from __future__ import annotations

import datetime as dt
import decimal
import logging
import threading
import time
import types
from typing import Any, Dict, List, Mapping, Sequence

import pytest

from Betfair.nucleo.stato_partita import calcolo as C
from Betfair.nucleo.stato_partita import servizio as S
from Betfair.nucleo.stato_partita.adattatori.lettura import lettura
from Betfair.nucleo.stato_partita.freschezza import ETA_ASSENTE
from Betfair.nucleo.stato_partita.tests.test_b_servizio import FonteInMemoria, T0, _busta_riga
from Betfair.stream import flusso_prezzi as FP
from Betfair.stream.tennis_scalper.tennis_score import parse_tennis_scores


def _tennis(eid: str, ph: str = "15", pa: str = "0", gh: int = 1, ga: int = 1) -> Dict[str, Any]:
    return {"eventId": eid, "status": "InPlay", "matchStatus": "InPlay",
            "score": {"home": {"score": ph, "games": gh, "sets": 0, "isServing": True},
                      "away": {"score": pa, "games": ga, "sets": 0, "isServing": False}}}


def _busta_tennis(eid: str, grezzi: Any) -> Mapping[str, Any]:
    return lettura(fonte="ips_diretto", trasporto="http", sport="tennis", grezzi=grezzi)


def _srv(ora: List[float]) -> "tuple[S.ServizioStatoPartita, FonteInMemoria, List[Any]]":
    fonte = FonteInMemoria()
    srv = S.ServizioStatoPartita(fonte, orologio_s=lambda: ora[0])
    eventi: List[Any] = []
    srv.iscrivi_eventi(eventi.append)
    return srv, fonte, eventi


# ---------------------------------------------------------------------------
# 2. una partita rotta non ferma le altre
# ---------------------------------------------------------------------------
RECORD_ROTTI = [[{"eventId": "2", "score": "1-0"}], [{"eventId": "2", "score": [1, 0]}]]


@pytest.mark.parametrize("grezzi", RECORD_ROTTI)
def test_tennis_malformato_vale_nessun_punteggio_come_il_runner(grezzi: Any) -> None:
    """Il parser di oggi SOLLEVA su ``score`` stringa o lista; il worker del
    runner tennis lo chiama in un try/except e lascia ``ts=None``: idem qui."""
    with pytest.raises(AttributeError):
        parse_tennis_scores(grezzi, "2")
    ora = [T0]
    srv, fonte, eventi = _srv(ora)
    srv.segui(["1", "2"])
    fonte.buste["1"] = _busta_riga("1", minuto=10, gol=(0, 0))
    fonte.buste["2"] = _busta_tennis("2", grezzi)
    srv.aggiorna()
    assert srv.stato("1").minuto == 10 and srv.stato("2").set_game is None
    assert sorted(e.event_id for e in eventi if isinstance(e, S.StatoCambiato)) == ["1", "2"]


def test_calcolo_che_solleva_non_perde_gli_eventi_delle_altre(monkeypatch: pytest.MonkeyPatch,
                                                              caplog: pytest.LogCaptureFixture) -> None:
    """Guardia del servizio: tolta la guardia del parser (il calcolo della 2
    solleva davvero), la 1 e la 3 arrivano lo stesso, il guasto e' nel log al
    piu' una volta al minuto per partita."""
    monkeypatch.setattr(C, "punteggio_tennis",
                        lambda grezzi, eid: parse_tennis_scores(list(grezzi), eid))
    ora = [T0]
    srv, fonte, eventi = _srv(ora)
    srv.segui(["1", "2", "3"])
    fonte.buste["1"] = _busta_riga("1", minuto=10, gol=(0, 0))
    fonte.buste["2"] = _busta_tennis("2", RECORD_ROTTI[0])
    fonte.buste["3"] = _busta_riga("3", minuto=20, gol=(1, 0))
    with caplog.at_level(logging.WARNING):
        srv.aggiorna()
        assert sorted(e.event_id for e in eventi) == ["1", "3"]   # il primo giro consegna 1 e 3
        ora[0] = T0 + 10
        srv.aggiorna()
        ora[0] = T0 + 71
        srv.aggiorna()
    assert {e.event_id for e in eventi} == {"1", "3"}
    assert srv.stato("2") is None and srv.errori_calcolo == 3
    assert caplog.text.count("partita 2 non calcolabile") == 2      # T0 e T0+71, non T0+10
    fonte.buste["2"] = _busta_tennis("2", [_tennis("2")])
    srv.aggiorna()
    assert srv.stato("2").set_game is not None


# ---------------------------------------------------------------------------
# 3. eta' oneste quando la fonte tace
# ---------------------------------------------------------------------------
def test_eta_crescono_quando_la_fonte_tace() -> None:
    ora = [T0]
    srv, fonte, _ = _srv(ora)
    srv.segui(["7"])
    fonte.buste["7"] = _busta_riga("7", minuto=10, gol=(0, 0), eta_s=1.0)
    srv.aggiorna()
    assert srv.stato("7").eta.riga_s == pytest.approx(1.0)
    fonte.buste.clear()
    ora[0] = T0 + 600
    srv.aggiorna()
    st = srv.stato("7")
    assert st.minuto == 10                                      # calcio: resta l'ultimo valore...
    assert st.eta.riga_s == pytest.approx(601.0)                # ...ma vecchio di 601 s
    assert st.eta.punteggio_s == pytest.approx(604.0)
    assert srv.istante_dato_s("7") == T0
    # il verdetto del flusso invecchia anche lui: il calcolo dello scanner ha 600 s
    assert st.prezzi_vivi.vivo is False and st.prezzi_vivi.motivo == FP.MOTIVO_SCANNER_BLOCCATO
    assert srv.stato_a("7", T0).eta.riga_s == pytest.approx(1.0)


def test_diretto_senza_riga_eta_none_ma_istante_esposto() -> None:
    ora = [T0]
    srv, fonte, _ = _srv(ora)
    srv.segui(["7"])
    fonte.buste["7"] = lettura(fonte="ips_diretto", trasporto="http", sport="calcio",
                               grezzo={"timeElapsed": 30, "matchStatus": "KickOff"})
    srv.aggiorna()
    fonte.buste.clear()
    ora[0] = T0 + 300
    srv.aggiorna()
    st = srv.stato("7")
    assert st.eta == ETA_ASSENTE and st.minuto == 30           # come score_age_sec: None
    assert ora[0] - srv.istante_dato_s("7") == pytest.approx(300.0)


def test_tennis_fonte_muta_toglie_il_punteggio_come_oggi() -> None:
    """Runner tennis: feed in errore -> ``strat.score = None``. Qui: set_game None,
    un solo StatoCambiato, e poi silenzio finche' non torna il dato."""
    ora = [T0]
    srv, fonte, eventi = _srv(ora)
    srv.segui(["2"])
    fonte.buste["2"] = _busta_tennis("2", [_tennis("2")])
    srv.aggiorna()
    fonte.buste.clear()
    srv.aggiorna()
    srv.aggiorna()
    st = srv.stato("2")
    assert st.set_game is None and st.eta == ETA_ASSENTE and st.prezzi_vivi is FP.NON_NOTO
    assert [type(e).__name__ for e in eventi] == ["StatoCambiato", "StatoCambiato"]
    fonte.buste["2"] = _busta_tennis("2", [_tennis("2", "30")])
    srv.aggiorna()
    assert C.chiave_tennis(srv.stato("2").set_game) == parse_tennis_scores([_tennis("2", "30")], "2").key()


# ---------------------------------------------------------------------------
# 4. fase dal ripiego API-Football
# ---------------------------------------------------------------------------
def _api(short: str, el: Any) -> Dict[str, Any]:
    return {"fixture": {"status": {"short": short, "elapsed": el}}, "goals": {"home": 1, "away": 0}}


def test_passaggio_al_ripiego_non_inventa_fasi() -> None:
    """IPS all'intervallo -> ripiego (HT al 45': fase DEDOTTA '1t', come Omega
    oggi) -> IPS ripresa: UNA FaseCambiata intervallo -> 2t, fra fasi LETTE;
    nessuna 'intervallo -> 1t' mai avvenuta."""
    ora = [T0]
    srv, fonte, eventi = _srv(ora)
    srv.segui(["7"])
    fonte.buste["7"] = lettura(fonte="ips_scanner", trasporto="db", sport="calcio",
                               grezzo={"timeElapsed": 45, "matchStatus": "FirstHalfEnd"})
    srv.aggiorna()
    fonte.buste["7"] = lettura(fonte="api_football", trasporto="http", sport="calcio",
                               grezzo=_api("HT", 45), origine="api_football")
    srv.aggiorna()
    st = srv.stato("7")
    assert (st.fase, C.fase_dedotta(st), st.fonte) == ("1t", True, "api_football")
    fonte.buste["7"] = lettura(fonte="ips_scanner", trasporto="db", sport="calcio",
                               grezzo={"timeElapsed": 47, "matchStatus": "SecondHalfKickOff"})
    srv.aggiorna()
    fasi = [(e.prima, e.dopo) for e in eventi if isinstance(e, S.FaseCambiata)]
    assert fasi == [("intervallo", "2t")]


def test_servizio_con_busta_api_football() -> None:
    ora = [T0]
    srv, fonte, eventi = _srv(ora)
    srv.segui(["7"])
    fonte.buste["7"] = lettura(fonte="api_football", trasporto="http", sport="calcio",
                               grezzo=_api("2H", 60), origine="api_football")
    srv.aggiorna()
    st = srv.stato("7")
    assert (st.fonte, st.minuto, st.gol, st.fase, st.tempo) == ("api_football", 60, (1, 0), "2t", None)
    assert C.fase_dedotta(st) is True
    assert [type(e).__name__ for e in eventi] == ["StatoCambiato"]     # nessuna FaseCambiata
    assert st.eta == ETA_ASSENTE and st.prezzi_vivi is FP.NON_NOTO


# ---------------------------------------------------------------------------
# 5. "in gioco": regola del runner quando il book e' osservato
# ---------------------------------------------------------------------------
def _md_vera() -> Dict[str, Any]:
    """Il ``marketDefinition`` VERO del primo messaggio della registrazione 35760084."""
    import gzip
    import json
    import os

    radice = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    path = os.path.join(radice, "registrazioni_banco", "35760084", "35760084.raw.jsonl.gz")
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.loads(fh.readline())["mc"][0]["marketDefinition"]


def _libro(mid: str, inplay: bool, status: str, market_time: Any = "-") -> Any:
    """Un ``MarketBook`` VERO di betfairlightweight, costruito dal suo dict con la
    ``MarketDefinition`` VERA della registrazione. ``market_time`` diverso da "-"
    sostituisce il valore gia' letto (per i bordi che una registrazione non ha)."""
    from betfairlightweight.resources.bettingresources import MarketBook
    from betfairlightweight.resources.streamingresources import MarketDefinition

    md = MarketDefinition(**dict(_md_vera(), status=status, inPlay=inplay))
    libro = MarketBook(marketId=mid, inplay=inplay, status=status, runners=[],
                       market_definition=md)
    if market_time != "-":
        libro.market_definition.market_time = market_time
    return libro


def test_in_gioco_segue_il_book_quando_osservato() -> None:
    ora = [T0]
    srv, fonte, _ = _srv(ora)
    srv.segui(["7"])
    b = _busta_riga("7", minuto=90, gol=(1, 0), status="SecondHalfKickOff")
    # ramo feed di FonteIpsRunner: riga + grezzo; la riga dice ancora inplay=True
    fonte.buste["7"] = lettura(fonte="ips_scanner", trasporto="db", sport="calcio", riga=b["riga"],
                               grezzo=b["riga"]["payload"]["score_raw"], scanner_s=2.0)
    srv.aggiorna()
    assert srv.stato("7").in_gioco is True                     # nessun book: la riga
    srv.osserva_book("7", _libro("1.1", True, "CLOSED"))
    srv.aggiorna()
    assert srv.stato("7").in_gioco is False                    # runner.py:358-363
    srv.osserva_book("7", _libro("1.2", True, "OPEN"))
    srv.aggiorna()
    assert srv.stato("7").in_gioco is True                     # basta UN mercato in gioco


# ---------------------------------------------------------------------------
# 6. ciclo di vita e concorrenza
# ---------------------------------------------------------------------------
class FonteLenta:
    nome = "lenta"

    def __init__(self) -> None:
        self.dentro = threading.Event()
        self.rilascia = threading.Event()
        self.chiamate = 0

    def leggi(self, ids: Sequence[str]) -> Mapping[str, Mapping[str, Any]]:
        self.chiamate += 1
        self.dentro.set()
        self.rilascia.wait(10)
        return {}


def _vivi(nome: str) -> int:
    return sum(1 for t in threading.enumerate() if t.name == nome and t.is_alive())


def test_ferma_scaduto_poi_avvia_non_rianima_il_vecchio() -> None:
    fonte = FonteLenta()
    srv = S.ServizioStatoPartita(fonte, nome="b-ciclo-lento")
    srv.segui(["1"])
    srv.avvia(periodo_s=0.05)
    assert fonte.dentro.wait(5)
    assert srv.ferma(attesa_s=0.1) is False                    # ancora dentro leggi()
    srv.avvia(periodo_s=30.0)
    fonte.rilascia.set()
    limite = time.monotonic() + 5
    while _vivi("b-ciclo-lento") > 1 and time.monotonic() < limite:
        time.sleep(0.02)
    assert _vivi("b-ciclo-lento") == 1                         # il vecchio e' uscito
    assert srv.ferma() is True and _vivi("b-ciclo-lento") == 0


def test_riavvio_dopo_ferma() -> None:
    fonte = FonteInMemoria()
    srv = S.ServizioStatoPartita(fonte, nome="b-riavvio")
    srv.segui(["7"])
    fonte.buste["7"] = _busta_riga("7", minuto=10, gol=(0, 0))
    for _ in range(2):
        letture = fonte.letture
        srv.avvia(periodo_s=30.0)
        limite = time.monotonic() + 5
        while fonte.letture == letture and time.monotonic() < limite:
            time.sleep(0.01)
        assert fonte.letture > letture and srv.vivo
        assert srv.ferma() is True and not srv.vivo and _vivi("b-riavvio") == 0


def test_avvia_concorrenti_un_solo_thread() -> None:
    fonte = FonteInMemoria()
    srv = S.ServizioStatoPartita(fonte, nome="b-avvia-insieme")
    porta = threading.Barrier(8)

    def parti() -> None:
        porta.wait()
        srv.avvia(periodo_s=30.0)

    ts = [threading.Thread(target=parti) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(5)
    assert _vivi("b-avvia-insieme") == 1
    srv.ferma()
    assert _vivi("b-avvia-insieme") == 0


class _ServizioCheSiFerma(S.ServizioStatoPartita):
    """Il primo giro si ferma PRIMA di consegnare (prelazione simulata)."""

    def __init__(self, *a: Any, **k: Any) -> None:
        super().__init__(*a, **k)
        self.n = 0
        self.primo_fermo = threading.Event()

    def _consegna(self, cbs: Any, cose: Any) -> None:
        self.n += 1
        if self.n == 1 and cose:
            self.primo_fermo.set()
            time.sleep(0.5)
        super()._consegna(cbs, cose)


def test_due_giri_concorrenti_consegnano_in_ordine() -> None:
    fonte = FonteInMemoria()
    srv = _ServizioCheSiFerma(fonte, orologio_s=lambda: T0)
    srv.segui(["7"])
    visti: List[int] = []
    srv.iscrivi(lambda st: visti.append(st.minuto))
    fonte.buste["7"] = _busta_riga("7", minuto=10, gol=(0, 0))
    t1 = threading.Thread(target=srv.aggiorna)
    t1.start()
    assert srv.primo_fermo.wait(5)
    fonte.buste["7"] = _busta_riga("7", minuto=11, gol=(0, 0))
    srv.aggiorna()
    t1.join(5)
    assert visti == [10, 11] and srv.stato("7").minuto == 11


def test_segui_iscrivi_aggiorna_concorrenti() -> None:
    fonte = FonteInMemoria()
    srv = S.ServizioStatoPartita(fonte, orologio_s=lambda: T0)
    errori: List[BaseException] = []
    stop = threading.Event()
    for i in range(20):
        fonte.buste[str(i)] = _busta_riga(str(i), minuto=10 + i % 5, gol=(0, 0))

    def segui() -> None:
        k = 0
        while not stop.is_set():
            srv.segui([str(i) for i in range(k % 20, k % 20 + 8)])
            k += 1

    def iscrivi() -> None:
        while not stop.is_set():
            a = srv.iscrivi(lambda s: None)
            b = srv.iscrivi_eventi(lambda s: None)
            a()
            b()

    def gira() -> None:
        while not stop.is_set():
            srv.aggiorna()
            for i in range(20):
                srv.stato(str(i))

    def protetto(f: Any) -> Any:
        def corpo() -> None:
            try:
                f()
            except BaseException as ex:  # noqa: BLE001 - il test raccoglie e poi asserisce
                errori.append(ex)
        return corpo

    ts = [threading.Thread(target=protetto(f)) for f in (segui, segui, iscrivi, gira, gira)]
    for t in ts:
        t.start()
    time.sleep(1.5)
    stop.set()
    for t in ts:
        t.join(5)
    assert not errori, errori
    assert srv.errori_calcolo == 0 and srv.giri > 0


def test_nessuna_ripresa_senza_prova() -> None:
    """Flusso fermo sulla riga, poi la fonte passa al diretto (niente riga):
    l'esito e' "non noto" (vivo=True, noto=False) -> nessun FlussoRipreso."""
    ora = [T0]
    srv, fonte, eventi = _srv(ora)
    srv.segui(["7"])
    fonte.buste["7"] = _busta_riga("7", minuto=10, gol=(0, 0), vivo=False)
    srv.aggiorna()
    raw = fonte.buste["7"]["riga"]["payload"]["score_raw"]
    fonte.buste["7"] = lettura(fonte="ips_diretto", trasporto="http", sport="calcio", grezzo=raw)
    srv.aggiorna()
    assert not any(isinstance(e, S.FlussoRipreso) for e in eventi)
    fonte.buste["7"] = _busta_riga("7", minuto=10, gol=(0, 0), vivo=True)
    srv.aggiorna()                     # ultimo NOTO era fermo, ora vivo NOTO: ripresa (con prova)
    fonte.buste["7"] = _busta_riga("7", minuto=10, gol=(0, 0), vivo=False)
    srv.aggiorna()
    fonte.buste["7"] = lettura(fonte="ips_diretto", trasporto="http", sport="calcio", grezzo=raw)
    srv.aggiorna()                     # fermo -> non noto: niente
    fonte.buste["7"] = _busta_riga("7", minuto=10, gol=(0, 0), vivo=False)
    srv.aggiorna()                     # ancora fermo (l'ultimo noto era fermo): niente
    nomi = [type(e).__name__ for e in eventi if not isinstance(e, S.StatoCambiato)]
    assert nomi == ["FlussoRipreso", "FlussoInterrotto"]


# ---------------------------------------------------------------------------
# 7. buchi dei test dalle mutazioni sopravvissute del revisore
# ---------------------------------------------------------------------------
def test_rigori_e_supplementari_sono_supplementari() -> None:
    for status in ("PenaltyShootout", "ExtraTimeFirstHalf", "ExtraTimeHalfTime", "ExtraTimeSecondHalf"):
        st = C.stato_calcio_da_grezzo("1", {"timeElapsed": 110, "matchStatus": status},
                                      fonte="ips_diretto", eta=ETA_ASSENTE, prezzi_vivi=FP.NON_NOTO)
        assert st.fase == "supplementari", status


def _riga_con(minuto: int, **extra: Any) -> Mapping[str, Any]:
    b = _busta_riga("7", minuto=minuto, gol=(0, 0))
    raw = b["riga"]["payload"]["score_raw"]
    raw["score"]["home"].update(extra)
    if "numberOfRedCards" in extra:
        b["riga"]["payload"]["red_home"] = extra["numberOfRedCards"]
    return lettura(fonte="ips_scanner", trasporto="db", sport="calcio", riga=b["riga"],
                   grezzo=raw, scanner_s=2.0, stato_scanner=b["stato_scanner"])


@pytest.mark.parametrize("campo", ["numberOfRedCards", "numberOfCorners", "numberOfYellowCards"])
def test_cambia_solo_rossi_corner_o_gialli_e_lo_stato_cambia(campo: str) -> None:
    ora = [T0]
    srv, fonte, eventi = _srv(ora)
    srv.segui(["7"])
    fonte.buste["7"] = _riga_con(30, **{campo: 0})
    srv.aggiorna()
    fonte.buste["7"] = _riga_con(30, **{campo: 1})
    srv.aggiorna()
    assert [type(e).__name__ for e in eventi] == ["StatoCambiato", "StatoCambiato"]


def test_ogni_punto_del_tennis_e_un_cambio() -> None:
    ora = [T0]
    srv, fonte, eventi = _srv(ora)
    srv.segui(["2"])
    punti = [("0", "0"), ("15", "0"), ("15", "15"), ("30", "15"), ("40", "15")]
    for ph, pa in punti:
        fonte.buste["2"] = _busta_tennis("2", [_tennis("2", ph, pa)])
        srv.aggiorna()
        srv.aggiorna()                                         # stesso punto: nessun cambio
    cambi = [e for e in eventi if isinstance(e, S.StatoCambiato)]
    assert len(cambi) == len(punti)
    assert [c.dopo.set_game.punto for c in cambi] == punti
    assert srv.stato("2").sport == "tennis" and srv.stato("2").fonte == "ips_diretto"


def test_ko_arrotondato_non_troncato() -> None:
    ko = dt.datetime(2026, 6, 30, 16, 0, 0, 600, tzinfo=dt.timezone.utc)    # 0,6 ms
    libro = _libro("1.1", False, "OPEN", ko)
    grezzo = C.ko_epoch_ms(libro)
    assert grezzo == ko.timestamp() * 1000.0
    assert C.ko_ms_intero(grezzo) == int(ko.timestamp() * 1000) + 1
    assert C.ko_ms_intero(1782835200122.9998) == 1782835200123


def test_ko_casi_strani_come_le_4_copie() -> None:
    from Betfair.stream.scalper.media_under_bot import MediaUnderStrategy
    from Betfair.stream.scalper.scalper_bot import ScalperStrategy
    from Betfair.stream.scalper.sniper_bot import SniperStrategy
    from Betfair.stream.tennis_scalper.tennis_scalper_bot import TennisScalperStrategy

    casi = [dt.datetime(1, 1, 1), dt.datetime(9999, 12, 31, 23, 59, 59),
            dt.datetime(2026, 6, 30, 16, 0, tzinfo=dt.timezone(dt.timedelta(hours=2))),
            dt.datetime(2026, 6, 30, 16, 0, 0, 123456, tzinfo=dt.timezone.utc),
            dt.date(2026, 6, 30), 1782837600, 1782837600.0, float("nan"), decimal.Decimal(5)]
    for i, mt in enumerate(casi):
        libro = _libro(f"1.{i}", False, "OPEN", mt)
        nuovo = C.ko_epoch_ms(libro)
        for cls in (ScalperStrategy, SniperStrategy, TennisScalperStrategy):
            assert cls._ko_epoch_ms(types.SimpleNamespace(_ko_ms={}), libro) == nuovo, repr(mt)
        assert MediaUnderStrategy._ko_epoch_ms(types.SimpleNamespace(_ko_ms=None), libro) == nuovo


def test_segui_pota_la_cache_del_ko() -> None:
    ora = [T0]
    srv, _, _ = _srv(ora)
    srv.segui(["7", "8"])
    for eid, mid in (("7", "1.1"), ("7", "1.2"), ("8", "1.3")):
        srv.osserva_book(eid, _libro(mid, False, "OPEN"))
    assert len(srv._ko) == 3
    srv.segui(["8"])
    assert len(srv._ko) == 1


# ---------------------------------------------------------------------------
# 8. divergenza dichiarata: record con soli secondi
# ---------------------------------------------------------------------------
def test_divergenza_record_con_soli_secondi() -> None:
    """DIVERGENZA PER L'UTENTE: lo scanner calcola ``minute`` sul record INTERO
    (25' da ``timeElapsedSeconds`` 1500) ma pubblica uno ``score_raw`` SENZA i
    secondi (``strip_volatile_state``): chi legge la riga vede 25, chi riparsa lo
    ``score_raw`` (runner sul feed) vede None."""
    from Betfair.safe_strategy import scanner
    from Betfair.stream.scores.betfair_inplay import parse_score_dict

    raw = {"timeElapsedSeconds": 1500, "matchStatus": "FirstHalf"}
    spogliato = scanner.strip_volatile_state(raw)
    riga = {"event_id": "1", "payload": {"minute": parse_score_dict("1", raw).minute,
                                         "score_raw": spogliato, "inplay": True}}
    dalla_riga = C.stato_calcio_da_riga(riga, eta=ETA_ASSENTE, prezzi_vivi=FP.NON_NOTO)
    dal_feed = C.stato_calcio_da_grezzo("1", spogliato, fonte="ips_scanner", eta=ETA_ASSENTE,
                                        prezzi_vivi=FP.NON_NOTO)
    assert (dalla_riga.minuto, dal_feed.minuto) == (25, None)
    assert dal_feed.minuto == parse_score_dict("1", spogliato).minute
