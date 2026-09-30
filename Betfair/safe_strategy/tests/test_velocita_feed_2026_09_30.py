"""30/09 - VELOCITA' DEL FEED DEI PUNTEGGI senza una chiamata in piu' al fornitore.

Quattro pezzi, tutti sul codice di produzione:
  (b) finestra del fischio: timeline CONSOLIDATA al posto del poll dei punteggi
      per le partite appena partite e senza punteggio; se il record della
      timeline non porta il punteggio la partita resta nel lotto dei punteggi;
  (c) sveglia del giro punteggi dallo stream (in gioco, OPEN <-> SUSPENDED),
      con il pavimento di 0,5 s fra due giri;
  (e) tetto ``MIKE_MAX_FOLLOWED`` = 80 e potatura: il tetto si confronta solo con
      le partite di Mike IN GIOCO (l'avviso «OLTRE il tetto» ripetuto 10.348
      volte il 30/09 con due sole partite di Mike);
  (d-1) Mike legge lo stato dello scanner dal canale, DB come ripiego.

I record IPS sono la forma VERA: quello dei punteggi e' copiato dalla
registrazione ``_live_raw/35760084/35760084.scores.jsonl`` (KickOff, 0-0), il
record della timeline e' lo stesso con ``updateDetails`` (risorsa
``EventTimeline`` di betfairlightweight, ``inplayserviceresources.py``).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from Betfair.safe_strategy import scanner
from Betfair.safe_strategy import service
from Betfair.safe_strategy.tests.test_incidente_quote_2026_09_17 import book, runner_dict

# --------------------------------------------------------------- record IPS veri
IPS_KICKOFF_0_0: Dict[str, Any] = {
    "eventTypeId": 1, "eventId": 35760084,
    "score": {
        "home": {"name": "Liepajas Metalurgs", "score": "0", "halfTimeScore": "",
                 "fullTimeScore": "", "penaltiesScore": "", "penaltiesSequence": [],
                 "games": "", "sets": "", "numberOfYellowCards": 0, "numberOfRedCards": 0,
                 "numberOfCards": 0, "numberOfCorners": 0, "numberOfCornersFirstHalf": 0,
                 "bookingPoints": 0},
        "away": {"name": "Ogre United", "score": "0", "halfTimeScore": "",
                 "fullTimeScore": "", "penaltiesScore": "", "penaltiesSequence": [],
                 "games": "", "sets": "", "numberOfYellowCards": 0, "numberOfRedCards": 0,
                 "numberOfCards": 0, "numberOfCorners": 0, "numberOfCornersFirstHalf": 0,
                 "bookingPoints": 0},
        "numberOfYellowCards": 0, "numberOfRedCards": 0, "numberOfCards": 0,
        "numberOfCorners": 0, "numberOfCornersFirstHalf": 0, "bookingPoints": 0,
    },
    "timeElapsed": 0, "elapsedRegularTime": 0, "timeElapsedSeconds": 57,
    "fullTimeElapsed": {"hour": 0, "min": 0, "sec": 0},
    "status": "KickOff", "matchStatus": "KickOff",
}

TIMELINE_KICKOFF_0_0: Dict[str, Any] = {
    **{k: v for k, v in IPS_KICKOFF_0_0.items() if k != "matchStatus"},
    "inPlayMatchStatus": "KickOff",
    "updateDetails": [
        {"updateId": 6, "updateType": "KickOff", "type": "KickOff", "matchTime": 1,
         "elapsedRegularTime": 1, "elapsedAddedTime": None, "team": None,
         "teamName": None, "updateTime": "2026-06-30T16:00:40.000Z"},
    ],
}


def timeline_senza_punteggio() -> Dict[str, Any]:
    """Il record della timeline con il blocco ``score`` ANCORA VUOTO (il caso
    da verificare dal vivo: il fornitore puo' pubblicare il KickOff prima del
    punteggio)."""
    rec = dict(TIMELINE_KICKOFF_0_0)
    rec["score"] = {"home": {"name": "Liepajas Metalurgs", "score": ""},
                    "away": {"name": "Ogre United", "score": ""}}
    return rec


# --------------------------------------------------------------- finto IPS
class _InPlay:
    """``client.in_play_service`` finto: risponde con record VERI e conta."""

    def __init__(self, timelines: Optional[List[Dict[str, Any]]] = None,
                 scores: Optional[List[Dict[str, Any]]] = None) -> None:
        self.timelines = timelines or []
        self.scores = scores or []
        self.chiamate: List[tuple] = []

    def get_event_timelines(self, event_ids: List[int], lightweight: bool = True):
        self.chiamate.append(("timelines", tuple(event_ids)))
        return [r for r in self.timelines if int(r["eventId"]) in set(event_ids)]

    def get_scores(self, event_ids: List[int], lightweight: bool = True):
        self.chiamate.append(("scores", tuple(event_ids)))
        return [r for r in self.scores if int(r["eventId"]) in set(event_ids)]


class _Client:
    def __init__(self, inplay: _InPlay) -> None:
        self.in_play_service = inplay


def scanner_calcio(inplay: _InPlay, orologio=None) -> service.Scanner:
    scan = service.Scanner(api_client=_Client(inplay), dry=True, use_stream=False,
                           orologio=orologio)
    meta = {"event_id": "35760084", "market_id": "1.200", "event_name": "Liepajas v Ogre",
            "open_date": "2026-06-30T16:00:00Z", "competition": "Virsliga",
            "runners": [], "sides": {"home": 1, "draw": 2, "away": 3}}
    scan.sports["calcio"].metas = {"35760084": meta}
    scan._rebuild_market_index()
    # il batch dei punteggi passa da ``_ips_batch``: qui lo si incanala sul finto
    scan._ips_batch = lambda chunk: [  # type: ignore[method-assign]
        (str(r["eventId"]), r, None)
        for r in inplay.get_scores([int(e) for e in chunk])
    ]
    return scan


PREZZI = [runner_dict(1, back=(2.0, 50.0), lay=(2.02, 40.0)),
          runner_dict(2, back=(3.4, 20.0), lay=(3.5, 20.0)),
          runner_dict(3, back=(3.8, 20.0), lay=(3.9, 20.0))]


def fischio(scan: service.Scanner) -> None:
    """Pre-partita visto, poi in gioco: e' cosi' che lo stream porta il fischio."""
    scan._apply_market_book(book("1.200", PREZZI, inplay=False), dallo_stream=True)
    scan._apply_market_book(book("1.200", PREZZI, inplay=True), dallo_stream=True)


# ===========================================================================
# (c) sveglia dallo stream
# ===========================================================================
def test_passaggio_in_gioco_segna_istante_e_sveglia():
    ips = _InPlay()
    scan = scanner_calcio(ips)
    scan._apply_market_book(book("1.200", PREZZI, inplay=False), dallo_stream=True)
    assert not scan.sveglia_punteggi.is_set()
    assert "inplay_visto_mono" not in scan.events["35760084"]

    scan._apply_market_book(book("1.200", PREZZI, inplay=True), dallo_stream=True)
    ev = scan.events["35760084"]
    assert scan.sveglia_punteggi.is_set()
    assert isinstance(ev["inplay_visto_mono"], float)
    assert scan.ips_chiamate["sveglie"] == 1
    # l'istante NON si sovrascrive ai book successivi
    visto = ev["inplay_visto_mono"]
    scan.sveglia_punteggi.clear()
    scan._apply_market_book(book("1.200", PREZZI, inplay=True), dallo_stream=True)
    assert ev["inplay_visto_mono"] == visto
    assert not scan.sveglia_punteggi.is_set(), "stesso stato = nessuna sveglia"


def test_istante_in_gioco_sopravvive_a_un_book_stantio():
    """Riconnessione dello stream: un book con ``inplay=False`` seguito da uno
    ``inplay=True`` NON sposta in avanti l'istante del primo in-play (che
    allungherebbe la finestra del fischio e falserebbe la misura)."""
    ips = _InPlay()
    orologio = {"t": 100.0}
    scan = scanner_calcio(ips, orologio=lambda: orologio["t"])
    fischio(scan)
    orologio["t"] = 250.0
    scan._apply_market_book(book("1.200", PREZZI, inplay=False), dallo_stream=True)
    scan._apply_market_book(book("1.200", PREZZI, inplay=True), dallo_stream=True)
    assert scan.events["35760084"]["inplay_visto_mono"] == 100.0


def test_evento_nato_gia_in_gioco_non_e_un_fischio():
    """Riavvio a partita iniziata (revisione 30/09): il primo book e' gia' in
    gioco: niente istante, niente finestra, niente sveglia."""
    ips = _InPlay(timelines=[TIMELINE_KICKOFF_0_0], scores=[IPS_KICKOFF_0_0])
    scan = scanner_calcio(ips)
    scan._apply_market_book(book("1.200", PREZZI, inplay=True), dallo_stream=True)
    assert "inplay_visto_mono" not in scan.events["35760084"]
    assert not scan.sveglia_punteggi.is_set()
    assert scan.finestra_fischio_ids() == []
    scan.poll_scores()
    assert ips.chiamate == [("scores", (35760084,))]


def test_tennis_non_sveglia():
    ips = _InPlay()
    scan = service.Scanner(api_client=_Client(ips), dry=True, use_stream=False)
    scan.sports["tennis"].metas = {"t1": {"event_id": "t1", "market_id": "1.100",
                                          "event_name": "Rossi v Bianchi", "open_date": "2026-06-30T16:00:00Z",
                                          "competition": "ATP", "runners": [], "sides": {"p1": 11, "p2": 22}}}
    scan._rebuild_market_index()
    r = [runner_dict(11, back=(1.5, 10.0), lay=(1.52, 10.0)), runner_dict(22, back=(2.8, 10.0), lay=(2.9, 10.0))]
    scan._apply_market_book(book("1.100", r, inplay=False), dallo_stream=True)
    scan._apply_market_book(book("1.100", r, inplay=True), dallo_stream=True)
    scan._apply_market_book(book("1.100", r, inplay=True, status="SUSPENDED"), dallo_stream=True)
    assert not scan.sveglia_punteggi.is_set()
    assert scan.ips_chiamate["sveglie"] == 0
    assert "inplay_visto_mono" not in scan.events["t1"]


def test_stop_vince_sull_attesa_lunga():
    scan = _ScanFinto()
    w = service.ScoreFeedWorker(scan)  # type: ignore[arg-type]
    w.start()
    time.sleep(0.7)  # oltre il pavimento: il worker e' nell'attesa lunga sulla sveglia
    t0 = time.monotonic()
    w.stop()
    w.join(timeout=3.0)
    assert not w.is_alive() and time.monotonic() - t0 < 0.3


def test_sospensione_e_riapertura_in_gioco_svegliano_una_volta_ciascuna():
    ips = _InPlay()
    scan = scanner_calcio(ips)
    fischio(scan)
    scan.sveglia_punteggi.clear()
    scan._apply_market_book(book("1.200", PREZZI, inplay=True, status="SUSPENDED"),
                            dallo_stream=True)
    assert scan.sveglia_punteggi.is_set()
    scan.sveglia_punteggi.clear()
    scan._apply_market_book(book("1.200", PREZZI, inplay=True, status="SUSPENDED"),
                            dallo_stream=True)
    assert not scan.sveglia_punteggi.is_set(), "sospeso -> sospeso non e' una transizione"
    scan._apply_market_book(book("1.200", PREZZI, inplay=True, status="OPEN"),
                            dallo_stream=True)
    assert scan.sveglia_punteggi.is_set()
    assert scan.ips_chiamate["sveglie"] == 3  # in gioco, sospeso, riaperto


def test_pre_partita_sospeso_non_sveglia():
    """Prima del fischio i mercati si sospendono di continuo: niente sveglia."""
    ips = _InPlay()
    scan = scanner_calcio(ips)
    scan._apply_market_book(book("1.200", PREZZI, inplay=False, status="OPEN"), dallo_stream=True)
    scan._apply_market_book(book("1.200", PREZZI, inplay=False, status="SUSPENDED"), dallo_stream=True)
    scan._apply_market_book(book("1.200", PREZZI, inplay=False, status="OPEN"), dallo_stream=True)
    assert not scan.sveglia_punteggi.is_set()
    assert scan.ips_chiamate["sveglie"] == 0


def test_chiusura_del_mercato_non_sveglia():
    ips = _InPlay()
    scan = scanner_calcio(ips)
    fischio(scan)
    scan.sveglia_punteggi.clear()
    scan._apply_market_book(book("1.200", PREZZI, inplay=True, status="CLOSED"), dallo_stream=True)
    assert not scan.sveglia_punteggi.is_set()


class _ScanFinto:
    """Solo cio' che ``ScoreFeedWorker`` tocca: giri contati, nessuna rete."""

    def __init__(self) -> None:
        self.sveglia_punteggi = threading.Event()
        self.giri: List[float] = []
        self.timelines_ts = time.monotonic()
        self.status_ts = time.monotonic()
        self.written_sig: Dict[str, str] = {}

    def poll_scores(self) -> None:
        self.giri.append(time.monotonic())

    def poll_timelines(self) -> None:  # pragma: no cover - mai entro il periodo
        raise AssertionError("timeline fuori cadenza")

    def publish_status(self, n: int) -> None:  # pragma: no cover
        raise AssertionError("stato fuori cadenza")


def test_worker_riparte_subito_alla_sveglia_ma_non_sotto_il_pavimento():
    scan = _ScanFinto()
    w = service.ScoreFeedWorker(scan)  # type: ignore[arg-type]
    w.start()
    try:
        time.sleep(0.05)
        assert len(scan.giri) == 1, "primo giro subito all'avvio"
        # sveglia subito dopo il primo giro: il secondo giro arriva DOPO il
        # pavimento (0,5 s), non subito e non alla cadenza (2 s)
        scan.sveglia_punteggi.set()
        time.sleep(0.25)
        assert len(scan.giri) == 1, "sotto il pavimento non si riparte"
        time.sleep(0.45)
        assert len(scan.giri) == 2, "alla sveglia si riparte appena passa il pavimento"
        assert 0.45 <= scan.giri[1] - scan.giri[0] <= 0.9
        # senza sveglia: il terzo giro NON arriva prima della cadenza
        time.sleep(0.8)
        assert len(scan.giri) == 2
    finally:
        w.stop()
        w.join(timeout=3.0)
    assert not w.is_alive()


def test_worker_sveglia_dopo_il_pavimento_interrompe_l_attesa():
    """La sveglia arriva quando il pavimento e' GIA' passato: il giro parte
    entro un decimo, non alla cadenza."""
    scan = _ScanFinto()
    w = service.ScoreFeedWorker(scan)  # type: ignore[arg-type]
    w.start()
    try:
        time.sleep(0.9)
        assert len(scan.giri) == 1
        t0 = time.monotonic()
        scan.sveglia_punteggi.set()
        time.sleep(0.15)
        assert len(scan.giri) == 2, "la sveglia deve interrompere l'attesa"
        assert scan.giri[1] - t0 < 0.15
    finally:
        w.stop()
        w.join(timeout=3.0)


def test_worker_respira_almeno_0_2s_dopo_un_giro_lento():
    class _Lento(_ScanFinto):
        def poll_scores(self) -> None:
            super().poll_scores()
            time.sleep(2.1 if len(self.giri) == 1 else 0.0)

    scan = _Lento()
    w = service.ScoreFeedWorker(scan)  # type: ignore[arg-type]
    w.start()
    try:
        time.sleep(2.2)
        assert len(scan.giri) == 1, "dopo un giro piu' lungo del periodo si respira comunque 0,2 s"
        time.sleep(0.3)
        assert len(scan.giri) == 2
        assert scan.giri[1] - scan.giri[0] >= 2.3
    finally:
        w.stop()
        w.join(timeout=3.0)


def test_worker_si_ferma_anche_durante_l_attesa():
    scan = _ScanFinto()
    w = service.ScoreFeedWorker(scan)  # type: ignore[arg-type]
    w.start()
    time.sleep(0.05)
    t0 = time.monotonic()
    w.stop()
    w.join(timeout=3.0)
    assert not w.is_alive()
    assert time.monotonic() - t0 < 1.5, "lo stop deve vincere sull'attesa"


# ===========================================================================
# (b) finestra del fischio: timeline consolidata
# ===========================================================================
def test_finestra_fischio_solo_calcio_in_gioco_senza_punteggio_entro_300s():
    ips = _InPlay()
    orologio = {"t": 1000.0}
    scan = scanner_calcio(ips, orologio=lambda: orologio["t"])
    fischio(scan)
    assert scan.finestra_fischio_ids() == ["35760084"]
    # con il punteggio esce dalla finestra
    scan.events["35760084"]["score_home"] = 0
    assert scan.finestra_fischio_ids() == []
    del scan.events["35760084"]["score_home"]
    # dopo 300 s esce dalla finestra
    orologio["t"] = 1300.5
    assert scan.finestra_fischio_ids() == []
    orologio["t"] = 1299.0
    assert scan.finestra_fischio_ids() == ["35760084"]
    # una partita in gioco vista prima del 30/09 (senza istante) non entra
    scan.events["x"] = {"sport": "calcio", "inplay": True}
    scan.events["tennis"] = {"sport": "tennis", "inplay": True, "inplay_visto_mono": 1299.0}
    assert scan.finestra_fischio_ids() == ["35760084"]


def test_timeline_con_punteggio_riempie_e_toglie_dal_lotto_dei_punteggi():
    ips = _InPlay(timelines=[TIMELINE_KICKOFF_0_0], scores=[IPS_KICKOFF_0_0])
    scan = scanner_calcio(ips)
    fischio(scan)
    scan.poll_scores()
    ev = scan.events["35760084"]
    assert (ev["score_home"], ev["score_away"], ev["minute"]) == (0, 0, 0)
    assert ev["timeline"] and ev["timeline"][0]["type"] == "KickOff"
    assert ev["score_raw"]["status"] == "KickOff"
    assert "updateDetails" not in ev["score_raw"], "la cronologia non entra nello stato grezzo"
    # UNA chiamata sola: la timeline; nessun poll dei punteggi in questo giro
    assert ips.chiamate == [("timelines", (35760084,))]
    assert scan.ips_chiamate["timelines_fischio"] == 1
    assert scan.ips_chiamate["punteggi_dalla_timeline"] == 1
    assert scan.ips_chiamate["scores"] == 0
    # al giro dopo la partita HA il punteggio: fuori dalla finestra, poll normale
    scan.poll_scores()
    assert ips.chiamate[-1] == ("scores", (35760084,))
    assert scan.ips_chiamate["scores"] == 1


def test_timeline_senza_punteggio_lascia_la_partita_al_poll_dei_punteggi():
    ips = _InPlay(timelines=[timeline_senza_punteggio()], scores=[IPS_KICKOFF_0_0])
    scan = scanner_calcio(ips)
    fischio(scan)
    scan.poll_scores()
    ev = scan.events["35760084"]
    # la timeline (senza punteggio) e' comunque entrata; il punteggio viene dai punteggi
    assert ev["timeline"][0]["type"] == "KickOff"
    assert (ev["score_home"], ev["score_away"]) == (0, 0)
    assert ips.chiamate == [("timelines", (35760084,)), ("scores", (35760084,))]
    assert scan.ips_chiamate["punteggi_dalla_timeline"] == 0


def test_timeline_ko_non_ferma_il_giro_dei_punteggi(caplog):
    class _Rotto(_InPlay):
        def get_event_timelines(self, event_ids, lightweight=True):
            raise RuntimeError("503 dal fornitore")

    ips = _Rotto(scores=[IPS_KICKOFF_0_0])
    scan = scanner_calcio(ips)
    fischio(scan)
    with caplog.at_level(logging.WARNING):
        scan.poll_scores()
    assert scan.events["35760084"]["score_home"] == 0
    assert any("eventTimelines (fischio) KO" in r.getMessage() for r in caplog.records)


def test_timeline_non_sovrascrive_un_punteggio_gia_noto():
    """Nella finestra ci si entra solo SENZA punteggio; ma se un record della
    timeline arrivasse per una partita che il punteggio ce l'ha, non lo tocca
    all'indietro: ``applica_timeline_fischio`` passa da ``apply_score_state``
    con lo stesso record, quindi 1-0 dai punteggi non torna 0-0."""
    ips = _InPlay()
    scan = scanner_calcio(ips)
    fischio(scan)
    uno_a_zero = dict(IPS_KICKOFF_0_0)
    uno_a_zero["score"] = {**IPS_KICKOFF_0_0["score"],
                           "home": {**IPS_KICKOFF_0_0["score"]["home"], "score": "1"}}
    scan.apply_score_state("35760084", uno_a_zero)
    assert scan.events["35760084"]["score_home"] == 1
    assert scan.finestra_fischio_ids() == []


def test_primo_punteggio_loggato_con_attesa_e_fonte(caplog):
    ips = _InPlay(timelines=[TIMELINE_KICKOFF_0_0])
    orologio = {"t": 5000.0}
    scan = scanner_calcio(ips, orologio=lambda: orologio["t"])
    fischio(scan)
    orologio["t"] = 5066.0
    with caplog.at_level(logging.INFO):
        scan.poll_scores()
    righe = [r.getMessage() for r in caplog.records if "primo punteggio" in r.getMessage()]
    assert righe == ["[safe-scan] primo punteggio 35760084 dopo 66.0 s dal primo in-play, fonte timeline"]


def test_conto_delle_chiamate_viaggia_sullo_stato():
    ips = _InPlay(timelines=[TIMELINE_KICKOFF_0_0])
    scan = scanner_calcio(ips)
    scan._spingi_stato = lambda payload: None  # type: ignore[method-assign]
    fischio(scan)
    scan.poll_scores()
    catturato: Dict[str, Any] = {}
    scan._spingi_stato = lambda payload: catturato.update(payload)  # type: ignore[method-assign]
    scan.publish_status(0)
    assert catturato["ips"] == {"scores": 0, "timelines": 0, "timelines_fischio": 1,
                                "sveglie": 1, "punteggi_dalla_timeline": 1}


# ===========================================================================
# (e) tetto 80 e potatura
# ===========================================================================
def test_tetto_di_serie_80(monkeypatch):
    monkeypatch.delenv("MIKE_MAX_FOLLOWED", raising=False)
    assert scanner._mike_max_followed() == 80
    monkeypatch.setenv("MIKE_MAX_FOLLOWED", "  ")
    assert scanner._mike_max_followed() == 80
    monkeypatch.setenv("MIKE_MAX_FOLLOWED", "abc")
    assert scanner._mike_max_followed() == 80
    monkeypatch.setenv("MIKE_MAX_FOLLOWED", "120")
    assert scanner._mike_max_followed() == 120


def test_partite_di_mike_non_in_gioco_non_contano_contro_il_tetto(caplog):
    """Il caso del 30/09: due partite di Mike (una pre-partita, una finita in
    attesa di regolamento), nessuna fra i candidati: NESSUN avviso."""
    with caplog.at_level(logging.WARNING):
        out = scanner.select_opp_candidates(["a", "b"], followed=["pre", "finita"],
                                            max_events=1, max_followed=1)
    assert out == ["a"]
    assert not [r for r in caplog.records if "OLTRE il tetto" in r.getMessage()]


def test_avviso_del_tetto_solo_quando_morde_davvero(caplog):
    with caplog.at_level(logging.WARNING):
        out = scanner.select_opp_candidates(["m1", "m2", "m3", "x"], followed=["m1", "m2", "m3", "pre"],
                                            max_events=1, max_followed=2)
    assert out == ["m1", "m2", "m3"]  # m3 entra dal tetto normale (1 posto), x resta fuori
    avvisi = [r.getMessage() for r in caplog.records if "OLTRE il tetto" in r.getMessage()]
    assert len(avvisi) == 1 and avvisi[0].startswith("[scanner] 1 partite seguite da Mike OLTRE il tetto 2")


# ===========================================================================
# (d-1) Mike: stato dello scanner dal canale, DB come ripiego
# ===========================================================================
def _mike_service():
    from Betfair.mike import service as MS
    return MS


class _DbConta:
    def __init__(self, riga: Optional[Dict[str, Any]]) -> None:
        self.riga = riga
        self.letture = 0
        self.log_righe: List[tuple] = []

    def scanner_status(self):
        self.letture += 1
        return self.riga

    def log(self, *a, **k):
        self.log_righe.append(a)


class _ClientCanale:
    """Solo la superficie che Mike legge: ``eta_stato_s`` e ``stato_payload``."""

    def __init__(self, eta: Optional[float], payload: Any) -> None:
        self._eta = eta
        self.stato_payload = payload

    def eta_stato_s(self):
        return self._eta


PAYLOAD_STATO = {"calcio_inplay": 3, "flusso": {"calcolato_ms": 1, "ferme": []}}


def test_mike_legge_lo_stato_dal_canale_senza_toccare_il_db(monkeypatch):
    MS = _mike_service()
    monkeypatch.setitem(MS._CANALE_FEED, "client", _ClientCanale(4.2, PAYLOAD_STATO))
    db = _DbConta({"payload": {"calcio_inplay": 99}, "updated_at": "2026-09-30T10:00:00+00:00"})
    eta = MS._scanner_age(db, now=time.time())
    assert eta == 4.2
    assert db.letture == 0
    assert MS._scanner_stato() == PAYLOAD_STATO
    assert MS._ULTIMO_STATO_SCANNER["fonte"] == "canale"


def test_mike_ripiega_sul_db_se_il_battito_e_vecchio_o_assente(monkeypatch):
    MS = _mike_service()
    riga = {"payload": {"calcio_inplay": 99, "flusso": {}}, "updated_at": "2026-09-30T10:00:00+00:00"}
    for client in (None, _ClientCanale(None, PAYLOAD_STATO), _ClientCanale(31.0, PAYLOAD_STATO),
                   _ClientCanale(2.0, None)):
        monkeypatch.setitem(MS._CANALE_FEED, "client", client)
        db = _DbConta(riga)
        eta = MS._scanner_age(db, now=MS.F.parse_iso_epoch(riga["updated_at"]) + 7.0)
        assert db.letture == 1
        assert eta == 7.0
        assert MS._scanner_stato() == riga["payload"]
        assert MS._ULTIMO_STATO_SCANNER["fonte"] == "db"


def test_mike_canale_al_limite_dei_30s_vale_ancora(monkeypatch):
    MS = _mike_service()
    monkeypatch.setitem(MS._CANALE_FEED, "client", _ClientCanale(30.0, PAYLOAD_STATO))
    db = _DbConta(None)
    assert MS._scanner_age(db, now=time.time()) == 30.0
    assert db.letture == 0


# ===========================================================================
# 30/09 sera: ``flusso.fermi_da_ms`` esatto e stabile; ``odds_seen_ms`` fuori firma
# ===========================================================================
def test_fermi_da_ms_e_l_ultima_conferma_e_resta_stabile():
    orologio = {"t": 1000.0}
    scan = scanner_calcio(_InPlay(), orologio=lambda: orologio["t"])
    # il MATCH_ODDS e una linea O/U: entrambi con prezzi all'istante 1000
    scan.flusso_stream["1.200"] = (True, 1000.0)
    scan.flusso_stream["1.201"] = (True, 1000.0)
    scan.flusso_conferma["1.200"] = 1000.0
    scan.flusso_conferma["1.201"] = 1000.0
    payload = {"inplay": True, "mo_market_id": "1.200",
               "ou": [{"market_id": "1.201", "line": 3.5, "status": "OPEN", "selections": []}]}
    orologio["t"] = 1005.0
    scan.flusso_conferma["1.200"] = 1005.0  # il MATCH_ODDS resta vivo
    blk = scan.flusso_evento("35760084", "calcio", payload)
    assert blk["mercati_fermi"] == [] and blk["fermi_da_ms"] == {}
    # la linea non riceve piu' nulla: oltre la soglia in gioco diventa ferma
    orologio["t"] = 1000.0 + service._flusso.SOGLIA_INPLAY_S["calcio"] + 1.0
    scan.flusso_conferma["1.200"] = orologio["t"]
    blk = scan.flusso_evento("35760084", "calcio", payload)
    assert blk["mercati_fermi"] == ["1.201"]
    assert blk["fermi_da_ms"] == {"1.201": 1000_000}, blk
    # ai giri successivi il valore NON cambia (firma stabile, nessuna riscrittura),
    # anche se l'orologio di parete e quello monotono derivano di qualche ms
    # (in produzione sono due orologi diversi: ricalcolarlo lo farebbe tremare)
    orologio["t"] += 30.0
    scan.flusso_conferma["1.200"] = orologio["t"]
    scan._ora = lambda: orologio["t"] + 0.007  # type: ignore[method-assign]
    blk2 = scan.flusso_evento("35760084", "calcio", payload)
    assert blk2["fermi_da_ms"] == {"1.201": 1000_000}
    assert scanner.payload_signature({"flusso": blk}) == scanner.payload_signature({"flusso": blk2})
    # quando la linea torna viva, esce da entrambi
    scan.flusso_conferma["1.201"] = orologio["t"]
    blk3 = scan.flusso_evento("35760084", "calcio", payload)
    assert blk3["mercati_fermi"] == [] and blk3["fermi_da_ms"] == {}


def test_odds_seen_ms_e_fuori_firma():
    a = {"odds": {"home": {"back": 2.0}}, "odds_seen_ms": 1, "odds_ts_ms": 5}
    b = {"odds": {"home": {"back": 2.0}}, "odds_seen_ms": 2, "odds_ts_ms": 5}
    c = {"odds": {"home": {"back": 2.0}}, "odds_seen_ms": 2, "odds_ts_ms": 6}
    assert scanner.payload_signature(a) == scanner.payload_signature(b)
    assert scanner.payload_signature(b) != scanner.payload_signature(c)


def test_odds_seen_ms_pubblicato_nella_riga():
    ips = _InPlay()
    orologio = {"t": 2000.0}
    scan = scanner_calcio(ips, orologio=lambda: orologio["t"])
    fischio(scan)
    from datetime import datetime, timezone
    rows, _ = scan.build_rows(datetime.now(timezone.utc))
    assert rows and rows[0]["payload"]["odds_seen_ms"] == 2000_000
