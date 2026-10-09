"""W1-B - parita' di ``calcolo.py`` con il codice di oggi (comparto B).

Arbitri IMPORTATI (mai copiati): ``parse_score_dict`` (betfair_inplay.py:50),
``tempo_da_stato_ips`` (atlante_v4.py:550), ``mission_phase`` e
``minute_from_clock`` (omega_engine.py:866, :932), ``parse_fixture_response``
(api_football.py:34), ``parse_tennis_scores`` e ``TennisScore.key()``
(tennis_score.py:131, :63), le 4 copie di ``_ko_epoch_ms`` (scalper_bot.py:788,
tennis_scalper_bot.py:804, sniper_bot.py:295, media_under_bot.py:1020) chiamate
sui ``MarketBook`` VERI di betfairlightweight ricavati dalle registrazioni.

Ingressi veri: OGNI riga dei sidecar ``.scores.jsonl`` di 35760084 e 35797769
(``registrazioni_banco/``, letti dal .gz: nessun file scritto).
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import types
from typing import Any, Dict, List, Tuple

import pytest

from Betfair.nucleo.stato_partita import calcolo as C
from Betfair.nucleo.stato_partita.contratto import StatoPartita
from Betfair.nucleo.stato_partita.freschezza import ETA_ASSENTE
from Betfair.omega import omega_engine as E
from Betfair.stream import flusso_prezzi as FP
from Betfair.stream.scalper import atlante_v4 as A
from Betfair.stream.scores.api_football import parse_fixture_response
from Betfair.stream.scores.betfair_inplay import parse_score_dict
from Betfair.stream.tennis_scalper.tennis_score import parse_tennis_scores

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
REGISTRAZIONI = os.path.join(RADICE, "registrazioni_banco")
EVENTI = ("35760084", "35797769")
#: righe dei due sidecar (contate dal file: un sidecar diverso fa fallire il test)
RIGHE_ATTESE = {"35760084": 96, "35797769": 124}
ORA = dt.datetime(2026, 6, 30, 16, 30, tzinfo=dt.timezone.utc)


def _righe_sidecar(event_id: str) -> List[Dict[str, Any]]:
    path = os.path.join(REGISTRAZIONI, event_id, f"{event_id}.scores.jsonl.gz")
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(r) for r in fh if r.strip()]


@pytest.fixture(scope="module")
def sidecar() -> List[Tuple[str, Dict[str, Any]]]:
    out: List[Tuple[str, Dict[str, Any]]] = []
    for ev in EVENTI:
        righe = _righe_sidecar(ev)
        assert len(righe) == RIGHE_ATTESE[ev], f"sidecar {ev}: {len(righe)} righe"
        out.extend((ev, r) for r in righe)
    return out


def _stato(ev: str, grezzo: Any) -> Any:
    return C.stato_calcio_da_grezzo(ev, grezzo, fonte="registrazione", eta=ETA_ASSENTE,
                                    prezzi_vivi=FP.NON_NOTO)


# ---------------------------------------------------------------------------
# calcio: OGNI riga dei sidecar
# ---------------------------------------------------------------------------
def test_parita_ogni_riga_dei_sidecar_con_parse_score_dict(sidecar: Any) -> None:
    """minuto/gol/rossi/corner/gialli = ``parse_score_dict`` sul record grezzo
    (come lo legge il banco: ``carica_punteggi`` -> ``apply_score_state``)."""
    uguali = 0
    for ev, riga in sidecar:
        raw = riga["payload"]
        snap = parse_score_dict(ev, raw)
        st = _stato(ev, raw)
        assert st.minuto == snap.minute
        assert st.gol == C.coppia(snap.score_home, snap.score_away)
        assert st.rossi == C.coppia(snap.red_home, snap.red_away)
        assert st.corner == C.coppia(snap.corners_home, snap.corners_away)
        assert st.gialli == C.coppia(snap.yellow_home, snap.yellow_away)
        assert st.grezzo is raw
        if st.gol is not None:
            assert st.gol == (snap.score_home, snap.score_away)
        uguali += 1
    assert uguali == sum(RIGHE_ATTESE.values()) == 220


def test_parita_ogni_riga_tempo_e_fase(sidecar: Any) -> None:
    """tempo = ``tempo_da_stato_ips``; fase (nella lingua di Omega) =
    ``mission_phase(matchStatus, minuto, kickoff=None)`` come ``_ht_ancora_in_gioco``."""
    for ev, riga in sidecar:
        raw = riga["payload"]
        snap = parse_score_dict(ev, raw)
        st = _stato(ev, raw)
        assert st.tempo == A.tempo_da_stato_ips(raw, snap.minute)
        omega = E.mission_phase(status=raw.get("matchStatus"), minute=snap.minute,
                                kickoff=None, now=ORA)
        assert C.fase_come_omega(st.fase) == omega


def test_fase_e_tempo_concordano_su_ogni_riga_dei_sidecar(sidecar: Any) -> None:
    """Sulle registrazioni le due regole di oggi (tempo di Safe/Mike, fase di
    Omega) non divergono mai: 1t/intervallo <-> tempo 1, 2t/supplementari <-> 2.
    La divergenza esiste (vedi ``test_divergenza_kickoff_vecchio``) ma non qui."""
    contate = {"1": 0, "2": 0, "altro": 0}
    for ev, riga in sidecar:
        st = _stato(ev, riga["payload"])
        if st.fase in ("1t", "intervallo"):
            assert st.tempo == 1, (ev, riga["ts"], st.fase, st.tempo)
            contate["1"] += 1
        elif st.fase in ("2t", "supplementari"):
            assert st.tempo == 2, (ev, riga["ts"], st.fase, st.tempo)
            contate["2"] += 1
        else:
            contate["altro"] += 1
    assert contate == {"1": 106, "2": 99, "altro": 15}   # altro: 13 righe di ripiego (pre) + 2 finita


def test_le_righe_registrate_dicono_la_loro_fonte(sidecar: Any) -> None:
    """Il sidecar porta anche i numeri che il runner aveva calcolato
    (``minute``/``score_*``/``stats``): per le righe IPS sono quelli di
    ``parse_score_dict``, per le righe di ripiego quelli di
    ``parse_fixture_response``. Lo stato, letto col parser della SUA fonte, li
    riproduce tutti (fonte che dice la verita')."""
    per_fonte = {"betfair": 0, "api_football": 0}
    for ev, riga in sidecar:
        if riga["source"] == "api_football":
            st = C.stato_calcio_da_api_football(ev, riga["payload"], eta=ETA_ASSENTE,
                                                prezzi_vivi=FP.NON_NOTO)
            ref = parse_fixture_response(ev, {"response": [riga["payload"]]})
            assert st.fonte == "api_football"
            assert ref.minute == riga["minute"] and st.minuto == riga["minute"]
        else:
            st = _stato(ev, riga["payload"])
            assert st.minuto == riga["minute"]
            assert riga["stats"]["corners"]["home"] == (st.corner or (None, None))[0]
            assert riga["stats"]["cards"]["red_away"] == (st.rossi or (None, None))[1]
        gol = st.gol or (None, None)
        assert (gol[0], gol[1]) == (riga["score_home"], riga["score_away"])
        per_fonte[riga["source"]] += 1
    assert per_fonte == {"betfair": 207, "api_football": 13}


def test_divergenza_banco_live_now_sulle_righe_di_ripiego(sidecar: Any) -> None:
    """DIVERGENZA PER L'UTENTE (non scelta): una riga di ripiego API-Football
    del sidecar, nel banco, passa dal parser IPS (minuto None); in ``live_now``
    aveva il minuto di API-Football: 3 righe su 220 (13 di ripiego; le altre
    10 erano 'NS', senza minuto in entrambe le letture)."""
    perse = [(ev, r["minute"]) for ev, r in sidecar
             if r["source"] == "api_football" and r["minute"] is not None
             and _stato(ev, r["payload"]).minuto is None]
    assert perse == [("35760084", 1), ("35797769", 1), ("35797769", 2)]


# ---------------------------------------------------------------------------
# calcio: casi limite (stessi arbitri)
# ---------------------------------------------------------------------------
CASI_LIMITE = [
    {"timeElapsed": 0, "matchStatus": "KickOff",
     "score": {"home": {"score": "0"}, "away": {"score": "0"}}},                       # minuto 0 valido
    {"elapsedRegularTime": 45, "elapsedAddedTime": 2, "matchStatus": "KickOff"},        # recupero 1T
    {"timeElapsedSeconds": 125},                                                       # solo i secondi
    {"timeElapsed": 50, "score": {"fullTime": {"home": 2, "away": 1}}},                # forma fullTime
    {"timeElapsed": 70, "score": {"current": {"home": {"value": 1}, "away": {"goals": 0}}}},
    {"timeElapsed": 88, "elapsedRegularTime": 35, "matchStatus": "KickOff"},           # stato vecchio
    {"timeElapsed": 47, "matchStatus": "FirstHalfEnd"},                                 # intervallo
    {"timeElapsed": 105, "matchStatus": "ExtraTimeFirstHalf"},                          # supplementari
    {"timeElapsed": 120, "matchStatus": "PenaltyShootout"},                             # rigori
    {"timeElapsed": 95, "matchStatus": "Finished", "status": "SecondHalfEnd"},
    {"timeElapsed": 60, "status": "SecondHalfKickOff"},                                 # solo `status`
    {"timeElapsed": "x", "matchStatus": "SecondHalfKickOff"},                           # minuto illeggibile
    {"score": {"home": {"score": "1", "numberOfRedCards": 1}, "away": {"score": None}}},
    {},
]


@pytest.mark.parametrize("raw", CASI_LIMITE)
def test_casi_limite_con_gli_arbitri(raw: Dict[str, Any]) -> None:
    snap = parse_score_dict("1", raw)
    st = _stato("1", raw)
    assert st.minuto == snap.minute
    assert st.gol == C.coppia(snap.score_home, snap.score_away)
    assert st.rossi == C.coppia(snap.red_home, snap.red_away)
    assert st.tempo == A.tempo_da_stato_ips(raw, snap.minute)
    assert C.fase_come_omega(st.fase) == E.mission_phase(
        status=raw.get("matchStatus"), minute=snap.minute, kickoff=None, now=ORA)


def test_supplementari_e_intervallo_hanno_un_nome_proprio() -> None:
    assert _stato("1", {"timeElapsed": 105, "matchStatus": "ExtraTimeFirstHalf"}).fase == "supplementari"
    assert _stato("1", {"timeElapsed": 47, "matchStatus": "FirstHalfEnd"}).fase == "intervallo"
    assert _stato("1", {"timeElapsed": 95, "matchStatus": "Finished"}).fase == "finita"
    assert _stato("1", None).fase == "sconosciuta"
    assert _stato("1", {}).fase == "pre"          # come Omega: niente stato ne' minuto = pre


def test_divergenza_kickoff_vecchio() -> None:
    """DIVERGENZA PER L'UTENTE (scheda B par. 3.3, punti 4 e 6): uno stato
    'KickOff' rimasto vecchio (35833626: timeElapsed 88) per Safe e Mike non e'
    creduto (``_MAX_MINUTO_1T``: tempo None, "non si sa") e per Omega e' fase
    '1t'. Lo stato riporta ENTRAMBI i valori, ciascuno col suo chiamante."""
    raw = {"timeElapsed": 88, "elapsedRegularTime": 35, "matchStatus": "KickOff"}
    st = _stato("1", raw)
    assert st.tempo is None and A.tempo_da_stato_ips(raw, 88) is None
    assert st.fase == "1t"
    assert E.mission_phase(status="KickOff", minute=88, kickoff=None, now=ORA) == "1t"


def test_divergenza_solo_status_senza_matchstatus() -> None:
    """DIVERGENZA: senza ``matchStatus`` Omega guarda solo il minuto, mentre
    ``parse_score_dict`` e ``tempo_da_stato_ips`` ripiegano su ``status``."""
    raw = {"timeElapsed": 47, "status": "FirstHalfEnd"}
    st = _stato("1", raw)
    assert st.tempo == 1                  # atlante: intervallo = tempo 1
    assert st.fase == "2t"                # Omega: minuto 47 senza stato = 2t


def test_riga_dello_scanner_usa_i_numeri_che_i_bot_leggono() -> None:
    """Dalla riga: minuto/gol/rossi del payload (non ricalcolati), tempo =
    ``tempo_da_payload``, in gioco = ``payload.inplay``."""
    raw = {"timeElapsed": 61, "elapsedRegularTime": 61, "matchStatus": "SecondHalfKickOff",
           "score": {"home": {"score": "1", "numberOfCorners": 3, "numberOfYellowCards": 2},
                     "away": {"score": "1", "numberOfCorners": 5, "numberOfYellowCards": 0}}}
    riga = {"event_id": "7", "sport": "calcio", "updated_at": "2026-06-30T16:40:00+00:00",
            "payload": {"minute": 62, "score_home": 1, "score_away": 1, "red_home": 0,
                        "red_away": 1, "score_raw": raw, "inplay": True}}
    st = C.stato_calcio_da_riga(riga, eta=ETA_ASSENTE, prezzi_vivi=FP.NON_NOTO)
    assert (st.minuto, st.gol, st.rossi, st.in_gioco) == (62, (1, 1), (0, 1), True)
    assert st.tempo == A.tempo_da_payload(riga["payload"]) == 2
    assert (st.corner, st.gialli) == ((3, 5), (2, 0))
    assert st.fase == "2t"
    vuota = C.stato_calcio_da_riga({"event_id": "7", "payload": {"inplay": False}},
                                   eta=ETA_ASSENTE, prezzi_vivi=FP.NON_NOTO)
    assert (vuota.fase, vuota.minuto, vuota.gol, vuota.in_gioco) == ("pre", None, None, False)


KO_RIPIEGO = dt.datetime(2026, 6, 30, 16, 0, tzinfo=dt.timezone.utc)


@pytest.mark.parametrize("minuto", [0, 30, 45, 46, 67, 90, 95, None])
@pytest.mark.parametrize("ore_dal_ko", [-1.0, 1.0, 4.0])
def test_api_football_fase_identica_a_mission_phase(minuto: Any, ore_dal_ko: float) -> None:
    """La fase dal ripiego e' quella che Omega calcola OGGI quando il punteggio
    viene dal ripiego senza stato IPS: ``mission_phase(status=None, minute,
    kickoff, now)`` (``omega_service.py:1129-1139`` e ``:1980``). Stessi ingressi,
    stesso valore (nella lingua di Omega); la fase e' DEDOTTA; il tempo resta None."""
    adesso = KO_RIPIEGO + dt.timedelta(hours=ore_dal_ko)
    for short in ("1H", "HT", "2H", "FT", "ET", "P", "AET", "PEN", "PST", "ABD", "NS"):
        entry = {"fixture": {"status": {"short": short, "elapsed": minuto}},
                 "goals": {"home": 2, "away": 0}}
        st = C.stato_calcio_da_api_football(
            "9", entry, eta=ETA_ASSENTE, prezzi_vivi=FP.NON_NOTO,
            ko_ms=C.ko_ms_intero(KO_RIPIEGO.timestamp() * 1000.0), adesso_s=adesso.timestamp())
        ref = parse_fixture_response("9", {"response": [entry]})
        omega = E.mission_phase(status=None, minute=ref.minute, kickoff=KO_RIPIEGO, now=adesso)
        assert C.fase_come_omega(st.fase) == omega, (short, minuto)
        assert C.fase_dedotta(st) is True and st.tempo is None
        assert (st.minuto, st.gol, st.fonte) == (ref.minute, (2, 0), "api_football")
    vuoto = C.stato_calcio_da_api_football("9", None, eta=ETA_ASSENTE, prezzi_vivi=FP.NON_NOTO)
    assert vuoto.fase == "sconosciuta" and C.fase_dedotta(vuoto) is False


def test_le_fasi_ips_sono_lette_non_dedotte() -> None:
    st = _stato("1", {"timeElapsed": 30, "matchStatus": "KickOff"})
    assert C.fase_dedotta(st) is False and type(st) is StatoPartita


def test_minuto_da_orologio_e_quello_di_omega() -> None:
    ko = dt.datetime(2026, 6, 30, 16, 0)
    for minuti in (0, 1, 44, 45, 46, 105, 200):
        adesso = ko + dt.timedelta(minutes=minuti, seconds=59)
        assert C.minuto_da_orologio(ko, adesso) == E.minute_from_clock(ko, adesso) == minuti


# ---------------------------------------------------------------------------
# tennis: casi costruiti dal parser di oggi (le registrazioni tennis le porta il PC)
# ---------------------------------------------------------------------------
def _tennis(eid: str = "35790084", *, ph: Any = "40", pa: Any = "30", gh: Any = 3, ga: Any = 2,
            sh: Any = 0, sa: Any = 1, servizio: str = "home", **extra: Any) -> Dict[str, Any]:
    rec = {"eventId": eid, "status": "InPlay", "matchStatus": "InPlay",
           "score": {"home": {"score": ph, "games": gh, "sets": sh, "name": "A",
                              "isServing": servizio == "home"},
                     "away": {"score": pa, "games": ga, "sets": sa, "name": "B",
                              "isServing": servizio == "away"}}}
    rec.update(extra)
    return rec


CASI_TENNIS = [
    [_tennis()],
    [_tennis(ph="AD", pa="40", servizio="away")],                 # break point
    [_tennis(ph="40", pa="15", gh=5, ga=3)],                       # set point
    [_tennis(ph="6", pa="5", gh=6, ga=6)],                         # tie-break
    [_tennis(ph=None, pa=None, currentPoint="15-30")],             # ripiego currentPoint
    [_tennis(eid="1"), _tennis(eid="35790084", ph="0", pa="15")],  # sceglie l'evento giusto
    [_tennis(eid="999")],                                          # nessuno uguale: il primo
    [{"eventId": "35790084", "score": {}}],                        # pre-match
    [{"eventId": "35790084"}],
]


@pytest.mark.parametrize("grezzi", CASI_TENNIS)
def test_tennis_chiave_e_pressione_uguali_al_parser(grezzi: List[Dict[str, Any]]) -> None:
    ts = parse_tennis_scores(grezzi, "35790084")
    st = C.stato_tennis_da_grezzo("35790084", grezzi, fonte="ips_diretto", eta=ETA_ASSENTE,
                                  prezzi_vivi=FP.NON_NOTO)
    assert ts is not None
    assert C.chiave_tennis(st.set_game) == ts.key()
    assert st.set_game.pressione == ts.point_pressure
    assert st.grezzo is ts.raw
    assert st.sport == "tennis" and st.gol is None and st.minuto is None


def test_tennis_senza_punteggio_resta_senza() -> None:
    for grezzi in ([], None):
        assert parse_tennis_scores(grezzi, "1") is None
        st = C.stato_tennis_da_grezzo("1", grezzi, fonte="ips_diretto", eta=ETA_ASSENTE,
                                      prezzi_vivi=FP.NON_NOTO)
        assert st.set_game is None and st.fase == "sconosciuta"


def test_tennis_dalla_riga_dello_scanner() -> None:
    rec = _tennis(ph="AD", pa="40", servizio="away")
    riga = {"event_id": "35790084", "sport": "tennis", "payload": {"score_raw": rec, "inplay": True}}
    st = C.stato_tennis_da_riga(riga, eta=ETA_ASSENTE, prezzi_vivi=FP.NON_NOTO)
    ts = parse_tennis_scores([rec], "35790084")
    assert C.chiave_tennis(st.set_game) == ts.key() and st.in_gioco is True
    assert st.set_game.pressione is True


# ---------------------------------------------------------------------------
# calcio d'inizio: le 4 copie di produzione sui MarketBook veri
# ---------------------------------------------------------------------------
def _libri_veri(event_id: str, massimo: int) -> List[Any]:
    """``MarketBook`` VERI (betfairlightweight ``StreamListener``) dalla registrazione."""
    from betfairlightweight.streaming import StreamListener

    path = os.path.join(REGISTRAZIONI, event_id, f"{event_id}.raw.jsonl.gz")
    ascolto = StreamListener(max_latency=None, lightweight=False)
    ascolto.register_stream(0, "marketSubscription")
    libri: List[Any] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for i, riga in enumerate(fh):
            if i >= massimo:
                break
            msg = json.loads(riga)
            msg["id"] = 0
            ascolto.on_data(json.dumps(msg))
            ids = [m["id"] for m in msg.get("mc") or []]
            if ids:
                libri.extend(ascolto.stream.snap(market_ids=ids))
    return libri


@pytest.fixture(scope="module")
def libri() -> List[Any]:
    out: List[Any] = []
    for ev in EVENTI:
        out.extend(_libri_veri(ev, 4000))
    return out


def _copie() -> Dict[str, Any]:
    from Betfair.stream.scalper.media_under_bot import MediaUnderStrategy
    from Betfair.stream.scalper.scalper_bot import ScalperStrategy
    from Betfair.stream.scalper.sniper_bot import SniperStrategy
    from Betfair.stream.tennis_scalper.tennis_scalper_bot import TennisScalperStrategy

    return {"scalper": ScalperStrategy._ko_epoch_ms, "tennis": TennisScalperStrategy._ko_epoch_ms,
            "sniper": SniperStrategy._ko_epoch_ms, "media": MediaUnderStrategy._ko_epoch_ms}


def test_ko_identico_alle_4_copie_sui_book_veri(libri: List[Any]) -> None:
    copie = _copie()
    # ``self`` delle copie: SOLO l'attributo che il metodo legge, col tipo vero
    # (``Dict[str, Optional[float]]`` per 1-3, ``Optional[float]`` per 4)
    se = {k: types.SimpleNamespace(_ko_ms={}) for k in ("scalper", "tennis", "sniper")}
    se["media"] = types.SimpleNamespace(_ko_ms=None)
    per_mercato, unico = C.KoPerMercato(), C.KoUnico()
    mercati = set()
    for mb in libri:
        nuovo = per_mercato(mb)
        for k in ("scalper", "tennis", "sniper"):
            assert copie[k](se[k], mb) == nuovo
        assert copie["media"](se["media"], mb) == unico(mb)
        assert C.ko_epoch_ms(mb) == nuovo
        assert nuovo is not None and float(C.ko_ms_intero(nuovo)) == nuovo
        mercati.add(mb.market_id)
    assert len(libri) > 10000 and len(mercati) >= 20


class _Md:
    def __init__(self, market_time: Any) -> None:
        self.market_time = market_time


class _Libro:
    """Solo per i bordi che i book veri non hanno (market_time assente o rotto):
    le DUE chiavi che le copie leggono, ``market_id`` e ``market_definition``."""

    def __init__(self, market_id: str, market_time: Any = None, senza_md: bool = False) -> None:
        self.market_id = market_id
        self.market_definition = None if senza_md else _Md(market_time)


class _Rotto:
    tzinfo = dt.timezone.utc

    def timestamp(self) -> float:
        raise OverflowError("fuori scala")


BORDI = [
    _Libro("1.1", senza_md=True),
    _Libro("1.1", None),
    _Libro("1.1", "2026-06-30T16:00:00Z"),            # stringa: niente timestamp()
    _Libro("1.1", _Rotto()),
    _Libro("1.1", dt.datetime(2026, 6, 30, 16, 0)),    # naive = UTC
    _Libro("1.2", dt.datetime(2026, 6, 30, 18, 0, tzinfo=dt.timezone.utc)),
    _Libro("1.1", dt.datetime(2026, 6, 30, 17, 0, tzinfo=dt.timezone.utc)),  # KO spostato: resta il primo
]


def test_ko_bordi_e_divergenza_della_cache_unica(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le 4 copie sui bordi; DIVERGENZA PER L'UTENTE: con due mercati di KO
    diverso la cache unica di ``media_under`` (4) ridice il primo KO anche per
    il secondo mercato, le altre tre (1-3) no. Fuso del processo NON UTC: un
    ``market_time`` senza fuso deve valere UTC, non l'ora locale."""
    import time as _time

    monkeypatch.setenv("TZ", "Europe/Rome")
    _time.tzset()
    try:
        _bordi_ko()
    finally:
        monkeypatch.undo()
        _time.tzset()


def _bordi_ko() -> None:
    copie = _copie()
    se = {k: types.SimpleNamespace(_ko_ms={}) for k in ("scalper", "tennis", "sniper")}
    se["media"] = types.SimpleNamespace(_ko_ms=None)
    per_mercato, unico = C.KoPerMercato(), C.KoUnico()
    visti = []
    for mb in BORDI:
        v = per_mercato(mb)
        for k in ("scalper", "tennis", "sniper"):
            assert copie[k](se[k], mb) == v
        u = unico(mb)
        assert copie["media"](se["media"], mb) == u
        visti.append((v, u))
    ko16 = dt.datetime(2026, 6, 30, 16, 0, tzinfo=dt.timezone.utc).timestamp() * 1000.0
    ko18 = dt.datetime(2026, 6, 30, 18, 0, tzinfo=dt.timezone.utc).timestamp() * 1000.0
    assert visti[:4] == [(None, None)] * 4
    assert visti[4] == (ko16, ko16)
    assert visti[5] == (ko18, ko16)       # la divergenza: 1-3 dicono 18:00, 4 dice 16:00
    assert visti[6] == (ko16, ko16)       # KO spostato dopo il primo: tutte e 4 restano al primo
    assert C.ko_ms_intero(None) is None
