"""Ladder sul CANALE locale al tick, DB a 2 s (23/09, ladder_canale.py).

Regola dell'utente: cio' che il trader vede passa dal canale al ms. Il
ladder_worker (calcio e tennis) pubblica sul canale ogni LIVE_LADDER_CANALE_MS
(default 200 ms; 0 = a ogni book nuovo) solo se la firma del book e' cambiata e
solo se il canale ha client; il DB resta a LADDER_PUBLISH_SEC (2 s)
write-on-change, con firma SEPARATA.

I book NON sono scritti a mano: passano dal recorder VERO (MarketRecorderStrategy
del calcio, _Capture del tennis) alimentato da un MarketBook finto con gli stessi
attributi di betfairlightweight (publish_time_epoch, runners[].ex.available_to_*
come PriceSize veri). Le sessioni sono quelle VERE (LiveSession,
TennisLiveSession). Il tempo e' un orologio finto iniettato nello StatoLadder:
nessun sleep, nessuna rete, nessun DB (upsert monkeypatchati), nessun canale
vero (channel_active/publish di local_channel monkeypatchati).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from betfairlightweight.resources.bettingresources import PriceSize

from Betfair.stream import ladder_canale, local_channel, runner
from Betfair.stream.tennis_live import tennis_db, tennis_runner

EID = "35.1"
MID = "1.900"
PT0 = 1_758_600_000_000  # ms epoch del primo book


# ---------------------------------------------------------------------------
# finti con la forma del vero
# ---------------------------------------------------------------------------
def _market_book(pt: int, size_back: float, status: str = "OPEN", mid: str = MID) -> Any:
    """MarketBook con gli attributi che serialize_book legge (betfairlightweight)."""
    runners = [
        SimpleNamespace(
            selection_id=sel, handicap=0.0, status="ACTIVE",
            last_price_traded=2.0, total_matched=100.0,
            ex=SimpleNamespace(
                available_to_back=[PriceSize(2.0, size_back), PriceSize(1.99, 30.0)],
                available_to_lay=[PriceSize(2.02, 40.0)],
                traded_volume=[PriceSize(2.0, 80.0)],
            ),
        )
        for sel in (11, 12)
    ]
    return SimpleNamespace(
        market_id=mid, publish_time_epoch=pt, inplay=True, status=status,
        total_matched=200.0, runners=runners,
        market_definition=SimpleNamespace(market_type="MATCH_ODDS", in_play=True, bet_delay=5),
    )


class _Orologio:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class _Canale:
    """Sostituto di local_channel.channel_active/publish (stesse firme)."""

    def __init__(self, attivo: bool = True) -> None:
        self.attivo = attivo
        self.pubblicati: List[Dict[str, Any]] = []

    def channel_active(self) -> bool:
        return self.attivo

    def publish(self, topic: str, payload: Any) -> None:
        assert topic == "ladder"
        self.pubblicati.append(payload)


@pytest.fixture
def canale(monkeypatch) -> _Canale:
    c = _Canale()
    monkeypatch.setattr(local_channel, "channel_active", c.channel_active)
    monkeypatch.setattr(local_channel, "publish", c.publish)
    return c


def _calcio(tmp_path, monkeypatch, canale_ms: int = 200, db_sec: float = 2.0):
    """LiveSession VERA + recorder VERO; ritorna (sessione, recorder, orologio, scritture DB)."""
    from betfairlightweight.filters import streaming_market_data_filter, streaming_market_filter

    from Betfair.stream.recorder import MarketRecorderStrategy

    rec = MarketRecorderStrategy(
        market_filter=streaming_market_filter(market_ids=[MID]),
        market_data_filter=streaming_market_data_filter(fields=["EX_ALL_OFFERS"], ladder_levels=10),
        context={"data_dir": str(tmp_path), "market_to_event": {MID: EID}, "depth": 10,
                 "record_events": lambda: set()},
    )
    sess = runner.LiveSession()
    sess.recorder = rec
    sess.markets_by_event[EID] = [
        {"market_id": MID, "market_type": "MATCH_ODDS", "market_name": "Esito finale"}]
    sess.selection_names[MID] = {"11": "Casa", "12": "Ospite"}
    orologio = _Orologio()
    sess._stato_ladder = ladder_canale.StatoLadder(db_sec, canale_ms, orologio=orologio)
    db_rows: List[Dict[str, Any]] = []
    monkeypatch.setattr(runner.db, "upsert_live_ladder", lambda row: db_rows.append(dict(row)))
    return sess, rec, orologio, db_rows


def _simula(sess, rec, orologio, *, secondi: float, passo_book: float, cambia: bool,
            worker=runner.ladder_worker) -> None:
    """Book ogni ``passo_book`` s (cambia la size se ``cambia``), worker alla sua cadenza."""
    intervallo = sess._stato_ladder.intervallo_worker()
    t0 = orologio.t
    prossimo_book = t0
    prossimo_worker = t0
    k = 0
    fine = t0 + secondi - 1e-9
    while True:
        t = min(prossimo_book, prossimo_worker)
        if t > fine:
            break
        orologio.t = t
        if prossimo_book <= prossimo_worker:
            size = 50.0 + (k if cambia else 0)
            rec.process_market_book(object(), _market_book(PT0 + int(round((t - 1000.0) * 1000)), size))
            k += 1
            prossimo_book = round(prossimo_book + passo_book, 6)
        else:
            worker({}, None, sess)
            prossimo_worker = round(prossimo_worker + intervallo, 6)


# ---------------------------------------------------------------------------
# cadenze
# ---------------------------------------------------------------------------
def test_book_a_100ms_cadenza_200ms_canale_5_al_s_db_mezzo_al_s(tmp_path, monkeypatch, canale):
    sess, rec, orologio, db_rows = _calcio(tmp_path, monkeypatch, canale_ms=200)
    assert sess._stato_ladder.intervallo_worker() == pytest.approx(0.2)
    _simula(sess, rec, orologio, secondi=10.0, passo_book=0.1, cambia=True)
    # 10 s: 50 giri del worker, ognuno con un book nuovo -> 50 pubblicazioni (5/s)
    assert len(canale.pubblicati) == 50
    # DB: t = 0, 2, 4, 6, 8 -> 5 scritture (0,5/s), write-on-change
    assert len(db_rows) == 5
    # nessuna pubblicazione doppia della stessa versione
    ms = [r["ladder"]["updated_ms"] for r in canale.pubblicati]
    assert ms == sorted(set(ms))


def test_book_fermo_zero_pubblicazioni(tmp_path, monkeypatch, canale):
    sess, rec, orologio, db_rows = _calcio(tmp_path, monkeypatch, canale_ms=200)
    rec.process_market_book(object(), _market_book(PT0, 50.0))
    runner.ladder_worker({}, None, sess)
    assert (len(canale.pubblicati), len(db_rows)) == (1, 1)
    # 20 s di giri a 200 ms con lo STESSO book: niente canale, niente DB
    for _ in range(100):
        orologio.t += 0.2
        runner.ladder_worker({}, None, sess)
    assert (len(canale.pubblicati), len(db_rows)) == (1, 1)
    # book NUOVO (pt nuovo) ma contenuto identico: la firma non cambia -> niente
    for i in range(20):
        orologio.t += 0.2
        rec.process_market_book(object(), _market_book(PT0 + 1000 * (i + 1), 50.0))
        runner.ladder_worker({}, None, sess)
    assert (len(canale.pubblicati), len(db_rows)) == (1, 1)


def test_parametro_zero_una_pubblicazione_per_cambiamento(tmp_path, monkeypatch, canale):
    sess, rec, orologio, db_rows = _calcio(tmp_path, monkeypatch, canale_ms=0)
    assert sess._stato_ladder.intervallo_worker() == pytest.approx(ladder_canale.INTERVALLO_MIN_SEC)
    _simula(sess, rec, orologio, secondi=5.0, passo_book=0.1, cambia=True)
    # 50 book diversi in 5 s, worker ogni 20 ms: UNA pubblicazione per book
    assert len(canale.pubblicati) == 50
    sizes = [r["ladder"]["selections"][0]["back"][0][1] for r in canale.pubblicati]
    assert sizes == [50.0 + k for k in range(50)]
    # il DB resta a 2 s: t = 0, 2, 4
    assert len(db_rows) == 3


def test_updated_ms_e_il_publish_time_del_book(tmp_path, monkeypatch, canale):
    sess, rec, orologio, db_rows = _calcio(tmp_path, monkeypatch)
    rec.process_market_book(object(), _market_book(PT0 + 123, 50.0))
    runner.ladder_worker({}, None, sess)
    assert canale.pubblicati[0]["ladder"]["updated_ms"] == PT0 + 123
    assert db_rows[0]["ladder"]["updated_ms"] == PT0 + 123
    # canale e DB portano la STESSA riga per lo stesso book
    assert canale.pubblicati[0] == db_rows[0]


def test_updated_ms_senza_pt_e_adesso(monkeypatch):
    monkeypatch.setattr(ladder_canale, "_ora_ms", lambda: 777)
    assert ladder_canale.updated_ms_del_book({"runners": {}}) == 777
    assert ladder_canale.updated_ms_del_book({"pt": None}) == 777
    assert ladder_canale.updated_ms_del_book({"pt": 555}) == 555


def test_solo_stato_cambiato_stesso_pt_passa_con_updated_ms_crescente(tmp_path, monkeypatch, canale):
    """process_closed_market marca CLOSED IN PLACE (stesso oggetto, stesso pt): la
    pagina scarta righe con updated_ms non piu' fresco -> deve crescere."""
    sess, rec, orologio, db_rows = _calcio(tmp_path, monkeypatch)
    rec.process_market_book(object(), _market_book(PT0, 50.0))
    runner.ladder_worker({}, None, sess)
    rec.process_closed_market(object(), SimpleNamespace(market_id=MID, status="CLOSED"))
    orologio.t += 0.2
    runner.ladder_worker({}, None, sess)
    assert [r["status"] for r in canale.pubblicati] == ["OPEN", "CLOSED"]
    assert canale.pubblicati[1]["ladder"]["updated_ms"] > canale.pubblicati[0]["ladder"]["updated_ms"]


# ---------------------------------------------------------------------------
# costo senza client, firme separate, riconnessione
# ---------------------------------------------------------------------------
def test_senza_client_nessuna_pubblicazione_e_giro_a_costo_zero(tmp_path, monkeypatch, canale):
    canale.attivo = False
    sess, rec, orologio, db_rows = _calcio(tmp_path, monkeypatch)
    letture = []
    vero = rec.latest_books
    monkeypatch.setattr(rec, "latest_books", lambda: letture.append(1) or vero())
    _simula(sess, rec, orologio, secondi=10.0, passo_book=0.1, cambia=True)
    assert canale.pubblicati == []
    assert len(db_rows) == 5              # il DB resta a 2 s anche senza client
    assert len(letture) == 5              # la cache si legge SOLO nei giri del DB


def test_cambio_nella_finestra_db_arriva_al_db_al_giro_dopo(tmp_path, monkeypatch, canale):
    """Firme separate: il canale non marca il DB come scritto. Prima del 23/09, col
    desktop collegato, un cambio caduto nei 2 s del DB non arrivava mai al DB se
    poi il book restava fermo."""
    sess, rec, orologio, db_rows = _calcio(tmp_path, monkeypatch)
    rec.process_market_book(object(), _market_book(PT0, 50.0))
    runner.ladder_worker({}, None, sess)                 # t=0: canale + DB
    orologio.t += 0.2
    rec.process_market_book(object(), _market_book(PT0 + 200, 99.0))
    runner.ladder_worker({}, None, sess)                 # t=0.2: solo canale
    assert (len(canale.pubblicati), len(db_rows)) == (2, 1)
    for _ in range(9):                                   # book fermo fino a t=2.0
        orologio.t += 0.2
        runner.ladder_worker({}, None, sess)
    assert len(db_rows) == 2
    assert db_rows[1]["ladder"]["selections"][0]["back"][0][1] == 99.0
    assert len(canale.pubblicati) == 2


def test_client_che_si_ricollega_riceve_subito_il_ladder(tmp_path, monkeypatch, canale):
    sess, rec, orologio, db_rows = _calcio(tmp_path, monkeypatch)
    rec.process_market_book(object(), _market_book(PT0, 50.0))
    runner.ladder_worker({}, None, sess)
    canale.attivo = False
    orologio.t += 0.2
    runner.ladder_worker({}, None, sess)
    canale.attivo = True                                 # client nuovo, book fermo
    orologio.t += 0.2
    runner.ladder_worker({}, None, sess)
    assert len(canale.pubblicati) == 2


def test_db_ko_ritenta_al_giro_db_dopo(tmp_path, monkeypatch, canale):
    sess, rec, orologio, _ = _calcio(tmp_path, monkeypatch)
    tentativi: List[int] = []

    def _ko(row: Dict[str, Any]) -> None:
        tentativi.append(1)
        raise RuntimeError("db giu'")
    monkeypatch.setattr(runner.db, "upsert_live_ladder", _ko)
    rec.process_market_book(object(), _market_book(PT0, 50.0))
    for _ in range(11):                                  # t = 0 .. 2.0
        runner.ladder_worker({}, None, sess)
        orologio.t += 0.2
    assert len(tentativi) == 2                           # t=0 e t=2: mai a raffica
    assert sess._last_ladder_sig == {}
    assert len(canale.pubblicati) == 1                   # il canale non dipende dal DB


# ---------------------------------------------------------------------------
# parametro
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("valore,atteso", [
    (None, 200), ("", 200), ("  ", 200), ("abc", 200), ("-5", 200),
    ("0", 0), ("50", 50), ("200", 200), (" 1000 ", 1000),
])
def test_canale_ms_env(monkeypatch, valore, atteso):
    if valore is None:
        monkeypatch.delenv("X_LADDER_CANALE_MS", raising=False)
    else:
        monkeypatch.setenv("X_LADDER_CANALE_MS", valore)
    assert ladder_canale.canale_ms_env("X_LADDER_CANALE_MS", 200) == atteso


def test_default_200ms_se_la_variabile_manca(monkeypatch):
    import importlib

    from Betfair.stream import config_stream
    monkeypatch.delenv("LIVE_LADDER_CANALE_MS", raising=False)
    try:
        ricaricato = importlib.reload(config_stream)
        assert ricaricato.LADDER_CANALE_MS == 200
    finally:
        importlib.reload(config_stream)


def test_il_worker_usa_il_parametro_della_config(tmp_path, monkeypatch, canale):
    sess, rec, orologio, db_rows = _calcio(tmp_path, monkeypatch)
    del sess._stato_ladder                               # come in produzione: creato al 1o giro
    rec.process_market_book(object(), _market_book(PT0, 50.0))
    runner.ladder_worker({}, None, sess)
    st = sess._stato_ladder
    assert st.canale_ms == runner.LADDER_CANALE_MS
    assert st.db_sec == runner.LADDER_PUBLISH_SEC


@pytest.mark.parametrize("canale_ms,db_sec,atteso", [
    (200, 2.0, 0.2), (0, 2.0, 0.02), (5, 2.0, 0.02), (5000, 2.0, 2.0), (50, 2.0, 0.05),
])
def test_intervallo_worker(canale_ms, db_sec, atteso):
    assert ladder_canale.StatoLadder(db_sec, canale_ms).intervallo_worker() == pytest.approx(atteso)


def test_canale_piu_lento_del_db_rispetta_la_sua_cadenza(tmp_path, monkeypatch, canale):
    sess, rec, orologio, db_rows = _calcio(tmp_path, monkeypatch, canale_ms=4000)
    _simula(sess, rec, orologio, secondi=10.0, passo_book=0.1, cambia=True)
    assert len(db_rows) == 5                              # worker a 2 s
    assert len(canale.pubblicati) == 3                    # t = 0, 4, 8


# ---------------------------------------------------------------------------
# tennis: stesso schema, sessione e capture VERE
# ---------------------------------------------------------------------------
def _tennis(monkeypatch, canale_ms: int = 200):
    sess = tennis_runner.TennisLiveSession(trading=None)
    cap = tennis_runner._make_capture(MID, EID)
    sess.capture[EID] = cap
    sess.market_meta[EID] = {"market_id": MID, "market_type": "MATCH_ODDS",
                             "market_name": "Vincente", "selection_names": {"11": "A", "12": "B"}}
    orologio = _Orologio()
    sess._stato_ladder = ladder_canale.StatoLadder(2.0, canale_ms, orologio=orologio)
    db_rows: List[Dict[str, Any]] = []
    monkeypatch.setattr(tennis_db, "upsert_tennis_ladder", lambda row: db_rows.append(dict(row)))
    return sess, cap, orologio, db_rows


def test_tennis_book_a_100ms_canale_5_al_s_db_mezzo_al_s(monkeypatch, canale):
    sess, cap, orologio, db_rows = _tennis(monkeypatch)
    _simula(sess, cap, orologio, secondi=10.0, passo_book=0.1, cambia=True,
            worker=tennis_runner.ladder_worker)
    assert len(canale.pubblicati) == 50
    assert len(db_rows) == 5
    assert canale.pubblicati[0]["ladder"]["updated_ms"] == PT0


def test_tennis_book_fermo_e_senza_client(monkeypatch, canale):
    sess, cap, orologio, db_rows = _tennis(monkeypatch)
    _simula(sess, cap, orologio, secondi=10.0, passo_book=0.1, cambia=False,
            worker=tennis_runner.ladder_worker)
    assert (len(canale.pubblicati), len(db_rows)) == (1, 1)
    canale.attivo = False
    _simula(sess, cap, orologio, secondi=10.0, passo_book=0.1, cambia=True,
            worker=tennis_runner.ladder_worker)
    assert len(canale.pubblicati) == 1


def test_tennis_parametro_zero(monkeypatch, canale):
    sess, cap, orologio, db_rows = _tennis(monkeypatch, canale_ms=0)
    _simula(sess, cap, orologio, secondi=5.0, passo_book=0.1, cambia=True,
            worker=tennis_runner.ladder_worker)
    assert len(canale.pubblicati) == 50
    assert len(db_rows) == 3


def test_tennis_cambio_nella_finestra_db_arriva_al_db_al_giro_dopo(monkeypatch, canale):
    sess, cap, orologio, db_rows = _tennis(monkeypatch)
    cap.process_market_book(object(), _market_book(PT0, 50.0))
    tennis_runner.ladder_worker({}, None, sess)          # t=0: canale + DB
    orologio.t += 0.2
    cap.process_market_book(object(), _market_book(PT0 + 200, 99.0))
    tennis_runner.ladder_worker({}, None, sess)          # t=0.2: solo canale
    assert (len(canale.pubblicati), len(db_rows)) == (2, 1)
    for _ in range(9):                                   # book fermo fino a t=2.0
        orologio.t += 0.2
        tennis_runner.ladder_worker({}, None, sess)
    assert len(db_rows) == 2
    assert db_rows[1]["ladder"]["selections"][0]["back"][0][1] == 99.0


@pytest.mark.parametrize("modulo", [runner, tennis_runner])
def test_worker_registrato_alla_cadenza_del_canale(modulo):
    """Il BackgroundWorker del ladder prende l'intervallo da StatoLadder
    (cadenza del canale), non piu' da LADDER_PUBLISH_SEC."""
    import inspect
    import re
    src = inspect.getsource(modulo)
    assert re.search(r"function=ladder_worker,\s*interval=_lcad\.stato_della_sessione\(\s*"
                     r"session, LADDER_PUBLISH_SEC, LADDER_CANALE_MS\)\.intervallo_worker\(\)", src)
    assert not re.search(r"function=ladder_worker, interval=LADDER_PUBLISH_SEC", src)


def test_tennis_parametro_default():
    assert tennis_runner.LADDER_CANALE_MS == ladder_canale.canale_ms_env("TENNIS_LADDER_CANALE_MS", 200)
