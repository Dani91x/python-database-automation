"""W1-B - correzioni dopo la SECONDA revisione (di ``67775f35``).

Punti a-g della richiesta del coordinatore. Le prove del revisore
(``scratchpad/rev_w1b2/exp1-3.py``, mutanti T13/T15/T21/T24) sono qui con nomi
miei, rovesciate: asseriscono il comportamento corretto. Book: ``MarketBook``
VERI di betfairlightweight (``_libro`` di ``test_b_correzioni``).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Mapping, Sequence

import betfairlightweight
import pytest

from Betfair.nucleo.stato_partita import calcolo as C
from Betfair.nucleo.stato_partita import servizio as S
from Betfair.nucleo.stato_partita.adattatori.ips import FonteIpsRunner
from Betfair.nucleo.stato_partita.adattatori.ips_tennis import FonteIpsTennisRunner
from Betfair.nucleo.stato_partita.adattatori.lettura import lettura
from Betfair.nucleo.stato_partita.freschezza import ETA_ASSENTE
from Betfair.nucleo.stato_partita.tests.test_b_correzioni import _api, _libro, _srv, _tennis
from Betfair.nucleo.stato_partita.tests.test_b_servizio import FonteInMemoria, T0, _busta_riga, _iso
from Betfair.stream import flusso_prezzi as FP
from Betfair.stream.scores import scan_feed as SF
from Betfair.stream.scores.betfair_inplay import BetfairInPlayProvider


# ---------------------------------------------------------------------------
# a) le callback non girano mai sotto un lock del servizio
# ---------------------------------------------------------------------------
def test_lock_invertito_fra_iscritto_e_chiamante_non_si_blocca() -> None:
    """exp2 del revisore: l'iscritto prende L; un altro thread tiene L e chiama
    ``aggiorna``. Con le callback sotto ``_giro_lock`` i due thread restavano
    bloccati per sempre; ora finiscono entrambi entro il tempo."""
    serratura = threading.Lock()
    fonte = FonteInMemoria()
    srv = S.ServizioStatoPartita(fonte, orologio_s=lambda: T0)
    srv.segui(["7"])
    fonte.buste["7"] = _busta_riga("7", minuto=10, gol=(0, 0))
    dentro, via = threading.Event(), threading.Event()
    ricevuti: List[int] = []

    def iscritto(st: Any) -> None:
        dentro.set()
        via.wait(5)
        with serratura:
            ricevuti.append(st.minuto)

    srv.iscrivi(iscritto)
    t1 = threading.Thread(target=srv.aggiorna, daemon=True)
    t1.start()
    assert dentro.wait(5)

    def altro() -> None:
        with serratura:
            via.set()
            fonte.buste["7"] = _busta_riga("7", minuto=11, gol=(0, 0))
            srv.aggiorna()

    t2 = threading.Thread(target=altro, daemon=True)
    t2.start()
    t1.join(3)
    t2.join(3)
    assert not t1.is_alive() and not t2.is_alive()
    assert ricevuti == [10, 11]                       # nell'ordine di calcolo


def test_rientranza_consegna_nell_ordine_di_calcolo() -> None:
    """exp1/E3 del revisore: un iscritto chiama ``aggiorna`` dallo STESSO thread
    durante la consegna. Il giro nuovo si accoda: tutti ricevono prima il 10'
    (anche chi viene dopo il rientrante), poi l'11'."""
    fonte = FonteInMemoria()
    srv = S.ServizioStatoPartita(fonte, orologio_s=lambda: T0)
    srv.segui(["7"])
    visti: List[tuple] = []

    def rientrante(st: Any) -> None:
        visti.append(("cb", st.minuto))
        if st.minuto == 10:
            fonte.buste["7"] = _busta_riga("7", minuto=11, gol=(0, 0))
            srv.aggiorna()

    srv.iscrivi(lambda st: visti.append(("a", st.minuto)))
    srv.iscrivi(rientrante)
    srv.iscrivi(lambda st: visti.append(("z", st.minuto)))
    fonte.buste["7"] = _busta_riga("7", minuto=10, gol=(0, 0))
    srv.aggiorna()
    assert visti == [("a", 10), ("cb", 10), ("z", 10), ("a", 11), ("cb", 11), ("z", 11)]
    assert srv.stato("7").minuto == 11


# ---------------------------------------------------------------------------
# b) scanner_s ricalcolato come le altre due eta'
# ---------------------------------------------------------------------------
def test_scanner_s_cresce_col_silenzio() -> None:
    ora = [T0]
    srv, fonte, _ = _srv(ora)
    srv.segui(["7"])
    fonte.buste["7"] = _busta_riga("7", minuto=10, gol=(0, 0))      # scanner_s = 2.0
    srv.aggiorna()
    assert srv.stato("7").eta.scanner_s == pytest.approx(2.0)
    fonte.buste.clear()
    ora[0] = T0 + 600
    srv.aggiorna()
    eta = srv.stato("7").eta
    assert eta.scanner_s == pytest.approx(602.0)
    assert eta.riga_s == pytest.approx(601.0) and eta.punteggio_s == pytest.approx(604.0)


# ---------------------------------------------------------------------------
# c) stato ed eventi concordano anche quando la fonte tace
# ---------------------------------------------------------------------------
def test_flusso_interrotto_al_giro_in_cui_il_verdetto_diventa_fermo() -> None:
    ora = [T0]
    srv, fonte, eventi = _srv(ora)
    srv.segui(["7"])
    fonte.buste["7"] = _busta_riga("7", minuto=10, gol=(0, 0))       # calcolo dello scanner a T0
    srv.aggiorna()
    fonte.buste.clear()
    ora[0] = T0 + 30                                                 # sotto i 45 s: ancora vivo
    srv.aggiorna()
    assert [type(e).__name__ for e in eventi] == ["StatoCambiato"]
    ora[0] = T0 + 60                                                 # oltre: giro dello scanner fermo
    srv.aggiorna()
    assert [type(e).__name__ for e in eventi[1:]] == ["StatoCambiato", "FlussoInterrotto"]
    assert eventi[2].esito.motivo == FP.MOTIVO_SCANNER_BLOCCATO
    assert srv.stato("7").prezzi_vivi.vivo is False                  # stato e eventi concordano
    assert srv.stato("7").minuto == 10                               # il contenuto resta
    ora[0] = T0 + 90
    srv.aggiorna()
    assert len(eventi) == 3                                          # niente di nuovo da dire


# ---------------------------------------------------------------------------
# d) fase dal ripiego: dedotta come Omega, FaseCambiata solo fra fasi lette
# ---------------------------------------------------------------------------
def test_fase_dedotta_non_fa_scattare_fase_cambiata() -> None:
    ora = [T0]
    srv, fonte, eventi = _srv(ora)
    srv.segui(["7"])
    for short, minuto in (("1H", 30), ("HT", 45), ("2H", 46), ("2H", 67), ("FT", 90)):
        fonte.buste["7"] = lettura(fonte="api_football", trasporto="http", sport="calcio",
                                   grezzo=_api(short, minuto), origine="api_football")
        srv.aggiorna()
        assert C.fase_dedotta(srv.stato("7")) is True
    assert [srv.stato("7").fase] == ["2t"]
    assert not any(isinstance(e, S.FaseCambiata) for e in eventi)
    fonte.buste["7"] = lettura(fonte="ips_scanner", trasporto="db", sport="calcio",
                               grezzo={"timeElapsed": 92, "matchStatus": "Finished"})
    srv.aggiorna()                                    # prima fase LETTA: nessun confronto possibile
    assert not any(isinstance(e, S.FaseCambiata) for e in eventi)


# ---------------------------------------------------------------------------
# e) ferma() dal thread del giro
# ---------------------------------------------------------------------------
def test_ferma_dal_thread_del_giro_non_solleva() -> None:
    fonte = FonteInMemoria()
    srv = S.ServizioStatoPartita(fonte, orologio_s=lambda: T0, nome="b-ferma-da-dentro")
    srv.segui(["7"])
    esiti: List[Any] = []
    srv.iscrivi(lambda st: esiti.append(srv.ferma(1.0)))
    fonte.buste["7"] = _busta_riga("7", minuto=10, gol=(0, 0))
    srv.avvia(0.05)
    limite = time.monotonic() + 5
    while (not esiti or srv.vivo or any(t.name == "b-ferma-da-dentro" for t in threading.enumerate())) \
            and time.monotonic() < limite:
        time.sleep(0.02)
    assert esiti == [False] and srv.errori_callback == 0
    assert not any(t.name == "b-ferma-da-dentro" for t in threading.enumerate())


# ---------------------------------------------------------------------------
# f) una partita rotta non scarta il giro delle altre (adattatori)
# ---------------------------------------------------------------------------
class _CacheCheSolleva(SF.ScanRowCache):
    """La ``ScanRowCache`` VERA, con un guasto iniettato su UNA partita."""

    def rows_for(self, event_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        if "2" in [str(e) for e in event_ids]:
            raise RuntimeError("riga illeggibile per la 2")
        return super().rows_for(event_ids)


def _riga(eid: str, minuto: int) -> Dict[str, Any]:
    return {"event_id": eid, "sport": "calcio", "updated_at": _iso(T0 - 1.0),
            "payload": {"minute": minuto, "inplay": True, "score_raw": {"timeElapsed": minuto}}}


def test_runner_una_partita_rotta_non_scarta_le_altre(monkeypatch: pytest.MonkeyPatch,
                                                      caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(time, "time", lambda: T0)
    righe = [_riga("1", 10), _riga("3", 30)]
    cache = _CacheCheSolleva(ttl_sec=0.0, fetch=lambda ids: [r for r in righe if r["event_id"] in ids],
                             fetch_status=lambda: None)
    client = betfairlightweight.APIClient("utente", "segreto", app_key="chiave")
    fonte = FonteIpsRunner(BetfairInPlayProvider(client), cache=cache)
    orologio = [0.0]
    fonte.log_raro._orologio = lambda: orologio[0]
    with caplog.at_level(logging.WARNING):
        for passo in (0.0, 10.0, 71.0):
            orologio[0] = passo
            letture = fonte.leggi(["1", "2", "3"])
            assert set(letture) == {"1", "3"}
    assert fonte.errori == 3
    assert caplog.text.count("lettura della partita 2 KO") == 2      # 0 s e 71 s, non 10 s


def test_tennis_una_partita_rotta_non_scarta_le_altre(caplog: pytest.LogCaptureFixture) -> None:
    client = betfairlightweight.APIClient("utente", "segreto", app_key="chiave")
    client.in_play_service.get_scores = lambda event_ids, lightweight=None: [  # type: ignore[method-assign]
        _tennis(str(event_ids[0]))]
    fonte = FonteIpsTennisRunner(client, cache=SF.ScanRowCache(ttl_sec=0.0, fetch=lambda ids: [],
                                                                fetch_status=lambda: None))
    vero = fonte._feed.grezzo_dal_feed

    def grezzo(eid: str) -> Any:
        if eid == "2":
            raise RuntimeError("feed illeggibile per la 2")
        return vero(eid)

    fonte._feed.grezzo_dal_feed = grezzo  # type: ignore[method-assign]
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            assert set(fonte.leggi(["1", "2", "3"])) == {"1", "3"}
    assert fonte.errori == 3 and caplog.text.count("lettura della partita 2 KO") == 1


# ---------------------------------------------------------------------------
# g) mutanti sopravvissute al revisore: T13, T15, T21, T24
# ---------------------------------------------------------------------------
def test_t13_chi_esce_da_segui_dimentica_fase_e_flusso() -> None:
    ora = [T0]
    srv, fonte, eventi = _srv(ora)
    srv.segui(["7"])
    fonte.buste["7"] = _busta_riga("7", minuto=46, gol=(0, 0), status="FirstHalfEnd", vivo=False)
    srv.aggiorna()                                     # fase letta 'intervallo', flusso noto fermo
    srv.segui([])
    srv.segui(["7"])                                   # ricomincia da zero
    entry = {"fixture": {"status": {"short": "2H", "elapsed": 50}}, "goals": {"home": 0, "away": 0}}
    fonte.buste["7"] = lettura(fonte="api_football", trasporto="http", sport="calcio",
                               grezzo=entry, origine="api_football")
    srv.aggiorna()                                     # fase DEDOTTA, flusso non noto
    fonte.buste["7"] = _busta_riga("7", minuto=50, gol=(0, 0), status="SecondHalfKickOff", vivo=True)
    srv.aggiorna()
    nomi = [type(e).__name__ for e in eventi if not isinstance(e, S.StatoCambiato)]
    assert nomi == []                                  # niente FaseCambiata ne' FlussoRipreso "vecchi"


def test_t15_osserva_book_ignora_le_partite_non_seguite() -> None:
    ora = [T0]
    srv, fonte, _ = _srv(ora)
    srv.segui(["7"])
    srv.osserva_book("8", _libro("1.8", True, "OPEN"))            # 8 non seguita: ignorata
    srv.segui(["7", "8"])
    fonte.buste["8"] = lettura(fonte="ips_diretto", trasporto="http", sport="calcio",
                               grezzo={"timeElapsed": 30, "matchStatus": "KickOff"})
    srv.aggiorna()
    st = srv.stato("8")
    assert st.in_gioco is False and st.ko_ms is None and len(srv._ko) == 0


class _FonteCheCambiaSegui:
    """Durante la lettura la partita 7 esce da ``segui`` (un altro thread)."""

    nome = "cambia-segui"

    def __init__(self, srv_ref: List[Any]) -> None:
        self.srv_ref = srv_ref

    def leggi(self, ids: Sequence[str]) -> Mapping[str, Mapping[str, Any]]:
        self.srv_ref[0].segui(["8"])
        return {e: _busta_riga(e, minuto=10, gol=(0, 0)) for e in ("7", "8")}


def test_t21_chi_esce_da_segui_durante_la_lettura_non_torna() -> None:
    rif: List[Any] = [None]
    srv = S.ServizioStatoPartita(_FonteCheCambiaSegui(rif), orologio_s=lambda: T0)
    rif[0] = srv
    srv.segui(["7", "8"])
    srv.aggiorna()
    assert srv.stato("7") is None and srv.stato("8") is not None


def test_t24_tennis_muto_con_riga_non_conserva_la_lettura_vecchia() -> None:
    ora = [T0]
    srv, fonte, _ = _srv(ora)
    srv.segui(["2"])
    riga = {"event_id": "2", "sport": "tennis", "updated_at": _iso(T0 - 1.0),
            "payload": {"score_raw": _tennis("2"), "inplay": True,
                        "flusso": {"vivo": True, "motivo": None, "dal_ms": 1, "mercati_fermi": []}}}
    fonte.buste["2"] = lettura(fonte="ips_scanner", trasporto="db", sport="tennis", riga=riga,
                               grezzi=[_tennis("2")], scanner_s=1.0)
    srv.aggiorna()
    assert srv.stato("2").eta.riga_s == pytest.approx(1.0)
    fonte.buste.clear()
    ora[0] = T0 + 10
    srv.aggiorna()
    st = srv.stato("2")
    assert st.set_game is None and st.eta == ETA_ASSENTE and st.prezzi_vivi is FP.NON_NOTO
    assert srv.prezzi_vivi("2") is FP.NON_NOTO


class _FonteLentaPoiVeloce:
    """La prima lettura resta ferma finche' il test non la rilascia e torna il
    10'; le successive tornano subito l'11'."""

    nome = "lenta-poi-veloce"

    def __init__(self) -> None:
        self.dentro = threading.Event()
        self.rilascia = threading.Event()
        self.chiamate = 0

    def leggi(self, ids: Sequence[str]) -> Mapping[str, Mapping[str, Any]]:
        self.chiamate += 1
        if self.chiamate == 1:
            self.dentro.set()
            self.rilascia.wait(5)
            return {"7": _busta_riga("7", minuto=10, gol=(0, 0))}
        return {"7": _busta_riga("7", minuto=11, gol=(0, 0))}


def test_giri_serializzati_un_giro_lento_non_sovrascrive_quello_dopo() -> None:
    """Due giri concorrenti: il primo legge piano (10'), il secondo parte dopo
    (11'). Serializzati, il secondo legge dopo il primo: alla fine lo stato e'
    11' e gli iscritti ricevono 10' poi 11'. Senza serializzazione il 10' lento
    sovrascriverebbe l'11' (stato vecchio) e arriverebbe per ultimo."""
    fonte = _FonteLentaPoiVeloce()
    srv = S.ServizioStatoPartita(fonte, orologio_s=lambda: T0)
    srv.segui(["7"])
    visti: List[int] = []
    srv.iscrivi(lambda st: visti.append(st.minuto))
    a = threading.Thread(target=srv.aggiorna)
    a.start()
    assert fonte.dentro.wait(5)
    b = threading.Thread(target=srv.aggiorna)
    b.start()
    time.sleep(0.3)                                   # b, se potesse, avrebbe gia' finito
    fonte.rilascia.set()
    a.join(5)
    b.join(5)
    # (terza revisione) uno stato non ancora consegnato si coalesce col successivo:
    # [10, 11] o [11], mai l'11' seguito da un 10' vecchio
    assert srv.stato("7").minuto == 11 and visti in ([10, 11], [11])
