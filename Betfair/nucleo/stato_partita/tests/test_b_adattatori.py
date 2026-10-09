"""W1-B - gli adattatori ``FonteStato`` contro il codice di oggi.

Oggetti VERI: ``ScanRowCache`` (col ``fetch``/``fetch_status`` che dichiara per
i test), ``ScanFeedScoreProvider``, ``BetfairInPlayProvider`` su un
``betfairlightweight.APIClient`` vero (si sostituisce SOLO
``in_play_service.get_scores``, la chiamata di rete, con record IPS VERI dei
sidecar), ``ScorePoller``, ``ApiFootballProvider`` su un ``APIFootballClient``
vero (sostituita solo ``call``, con entry API-Football VERE dei sidecar),
``ClientScan``/``CacheScan`` del canale (messaggi passati da ``incassa``),
``carica_punteggi`` del banco.

Falsificazione (3) della scheda B par. 5: togliere lo "scanner vivo" dalla
regola del runner -> ``test_zero_a_zero_fermo_con_scanner_vivo_resta_sul_feed``
rosso.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple

import betfairlightweight
import pytest

from Betfair.nucleo.stato_partita.adattatori.api_football import (FonteApiFootball,
                                                                  FonteCircuitoCalcio)
from Betfair.nucleo.stato_partita.adattatori.canale import FonteCanale
from Betfair.nucleo.stato_partita.adattatori.ips import FonteIpsRunner, FonteIpsScanner
from Betfair.nucleo.stato_partita.adattatori.ips_tennis import FonteIpsTennisRunner
from Betfair.nucleo.stato_partita.adattatori.lettura import CHIAVI
from Betfair.nucleo.stato_partita.adattatori.registrazione import FonteRegistrazione
from Betfair.stream.scores import scan_feed as SF
from Betfair.stream.scores.betfair_inplay import BetfairInPlayProvider, parse_score_dict
from Betfair.stream.scores.poller import ScorePoller

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
REGISTRAZIONI = os.path.join(RADICE, "registrazioni_banco")
EID = "35760084"
T0 = 1_782_837_600.0


def _iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).isoformat()


def _sidecar(event_id: str = EID) -> List[Dict[str, Any]]:
    path = os.path.join(REGISTRAZIONI, event_id, f"{event_id}.scores.jsonl.gz")
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(r) for r in fh if r.strip()]


@pytest.fixture(scope="module")
def record_ips() -> List[Dict[str, Any]]:
    """Record IPS VERI (righe ``betfair`` del sidecar di 35760084)."""
    return [r["payload"] for r in _sidecar() if r["source"] == "betfair"]


@pytest.fixture(autouse=True)
def _canale_spento(monkeypatch: pytest.MonkeyPatch) -> None:
    # PUNTEGGI_CANALE spento: la cache di oggi istruzione per istruzione
    monkeypatch.delenv("PUNTEGGI_CANALE", raising=False)
    monkeypatch.setattr(time, "time", lambda: T0)


def _cache(righe: List[Dict[str, Any]], stato: Optional[Dict[str, Any]] = None) -> SF.ScanRowCache:
    return SF.ScanRowCache(ttl_sec=0.0, fetch=lambda ids: [r for r in righe if r["event_id"] in ids],
                           fetch_status=lambda: stato)


def _riga(raw: Optional[Dict[str, Any]], eta_s: float, eid: str = EID) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"minute": (raw or {}).get("timeElapsed"), "inplay": True}
    if raw is not None:
        payload["score_raw"] = raw
    return {"event_id": eid, "sport": "calcio", "updated_at": _iso(T0 - eta_s), "payload": payload}


def _stato_scanner(eta_s: Optional[float]) -> Optional[Dict[str, Any]]:
    if eta_s is None:
        return None
    return {"id": "scanner", "updated_at": _iso(T0 - eta_s),
            "payload": {"flusso": {"calcolato_ms": int((T0 - eta_s) * 1000), "eventi_fermi": {}}}}


def _client_con(risposta: Any) -> Tuple[Any, List[Any]]:
    """Un ``APIClient`` VERO; solo la chiamata di rete risponde da registrazione."""
    client = betfairlightweight.APIClient("utente", "segreto", app_key="chiave")
    chiamate: List[Any] = []

    def get_scores(event_ids: Any, lightweight: Any = None, **kw: Any) -> Any:
        chiamate.append((event_ids, lightweight))
        if isinstance(risposta, Exception):
            raise risposta
        return risposta

    client.in_play_service.get_scores = get_scores  # type: ignore[method-assign]
    return client, chiamate


# ---------------------------------------------------------------------------
# FonteIpsScanner: righe come sono
# ---------------------------------------------------------------------------
def test_fonte_scanner_da_le_righe_senza_filtro(record_ips: List[Dict[str, Any]]) -> None:
    righe = [_riga(record_ips[10], 5.0), _riga(record_ips[20], 400.0, eid="2")]
    stato = _stato_scanner(4.0)
    cache = _cache(righe, stato)
    letture = FonteIpsScanner(cache).leggi([EID, "2", "3"])
    assert set(letture) == {EID, "2"}                      # 400 s: la riga c'e' (la soglia e' del bot)
    for eid, let in letture.items():
        assert tuple(let) == CHIAVI
        assert let["fonte"] == "ips_scanner" and let["trasporto"] == "db"
        assert let["riga"] == next(r for r in righe if r["event_id"] == eid)
        assert let["scanner_s"] == cache.scanner_age_sec() == pytest.approx(4.0, abs=1e-6)
        assert let["stato_scanner"] == stato["payload"]
    assert FonteIpsScanner(cache).leggi([]) == {}


# ---------------------------------------------------------------------------
# FonteIpsRunner: la regola del runner, parita' con ScanFeedScoreProvider
# ---------------------------------------------------------------------------
GRIGLIA = [(eta, scan, con_raw) for eta in (1.0, 14.0, 16.0, 100.0, 179.0, 181.0, 400.0)
           for scan in (None, 5.0, 30.0, 31.0) for con_raw in (True, False)]


@pytest.mark.parametrize("eta_riga,eta_scanner,con_raw", GRIGLIA)
def test_runner_sceglie_come_scan_feed(record_ips: List[Dict[str, Any]], eta_riga: float,
                                       eta_scanner: Optional[float], con_raw: bool) -> None:
    raw_feed = record_ips[30]
    raw_diretto = record_ips[60]
    righe = [_riga(raw_feed if con_raw else None, eta_riga)]
    client_v, chiamate_v = _client_con([raw_diretto])
    vecchio = SF.ScanFeedScoreProvider(BetfairInPlayProvider(client_v),
                                       cache=_cache(righe, _stato_scanner(eta_scanner)))
    snap = vecchio.get_score(EID)
    client_n, chiamate_n = _client_con([raw_diretto])
    nuovo = FonteIpsRunner(BetfairInPlayProvider(client_n),
                           cache=_cache(righe, _stato_scanner(eta_scanner)))
    let = nuovo.leggi([EID])[EID]
    dal_feed = vecchio.feed_hits == 1
    assert (let["fonte"] == "ips_scanner") is dal_feed
    assert (nuovo.dal_feed, nuovo.diretti) == (vecchio.feed_hits, vecchio.direct_calls)
    assert chiamate_n == chiamate_v
    assert let["grezzo"] == snap.payload
    rifatto = parse_score_dict(EID, let["grezzo"])
    assert (rifatto.minute, rifatto.score_home, rifatto.score_away) == \
        (snap.minute, snap.score_home, snap.score_away)
    if not dal_feed:
        assert let["fonte"] == "ips_diretto" and let["trasporto"] == "http"


def test_zero_a_zero_fermo_con_scanner_vivo_resta_sul_feed(record_ips: List[Dict[str, Any]]) -> None:
    """Falsificazione (3): 0-0 fermo, riga vecchia di 100 s (write-on-change:
    nulla e' cambiato) ma scanner vivo (battito di 5 s fa) -> il feed vale,
    nessuna chiamata diretta. Scanner morto (60 s) -> chiamata diretta."""
    raw = dict(record_ips[3])
    righe = [_riga(raw, 100.0)]
    client, chiamate = _client_con([record_ips[4]])
    vivo = FonteIpsRunner(BetfairInPlayProvider(client), cache=_cache(righe, _stato_scanner(5.0)))
    let = vivo.leggi([EID])[EID]
    assert let["fonte"] == "ips_scanner" and chiamate == []
    assert let["scanner_s"] == pytest.approx(5.0, abs=1e-6)
    morto = FonteIpsRunner(BetfairInPlayProvider(client), cache=_cache(righe, _stato_scanner(60.0)))
    assert morto.leggi([EID])[EID]["fonte"] == "ips_diretto" and len(chiamate) == 1


def test_runner_senza_nessun_dato_non_inventa(record_ips: List[Dict[str, Any]]) -> None:
    client, _ = _client_con([])
    fonte = FonteIpsRunner(BetfairInPlayProvider(client), cache=_cache([]))
    assert fonte.leggi([EID]) == {}
    client_ko, _ = _client_con(RuntimeError("IPS giu'"))
    assert FonteIpsRunner(BetfairInPlayProvider(client_ko), cache=_cache([])).leggi([EID]) == {}


# ---------------------------------------------------------------------------
# tennis
# ---------------------------------------------------------------------------
def _tennis(eid: str, ph: str = "40", pa: str = "15") -> Dict[str, Any]:
    return {"eventId": eid, "status": "InPlay", "matchStatus": "InPlay",
            "score": {"home": {"score": ph, "games": 4, "sets": 1, "isServing": False},
                      "away": {"score": pa, "games": 4, "sets": 0, "isServing": True}}}


def test_tennis_feed_diretto_errore() -> None:
    eid = "35790084"
    riga = {"event_id": eid, "sport": "tennis", "updated_at": _iso(T0 - 2.0),
            "payload": {"score_raw": _tennis(eid), "inplay": True}}
    client, chiamate = _client_con([_tennis(eid, "0", "15")])
    fonte = FonteIpsTennisRunner(client, cache=_cache([riga]))
    let = fonte.leggi([eid])[eid]
    assert let["fonte"] == "ips_scanner" and let["grezzi"] == [riga["payload"]["score_raw"]]
    assert chiamate == []
    stantia = dict(riga, updated_at=_iso(T0 - 200.0))
    fonte2 = FonteIpsTennisRunner(client, cache=_cache([stantia]))
    let2 = fonte2.leggi([eid])[eid]
    assert let2["fonte"] == "ips_diretto" and let2["grezzi"] == [_tennis(eid, "0", "15")]
    assert chiamate == [([int(eid)], True)]                # id numerico, lightweight
    client_ko, _ = _client_con(RuntimeError("IPS giu'"))
    fonte3 = FonteIpsTennisRunner(client_ko, cache=_cache([]))
    assert fonte3.leggi([eid]) == {} and fonte3.errori == 1
    client_s, chiamate_s = _client_con([])
    FonteIpsTennisRunner(client_s, cache=_cache([])).leggi(["abc"])
    assert chiamate_s == [(["abc"], True)]                 # id non numerico: com'e'


# ---------------------------------------------------------------------------
# API-Football e il circuito (U-10: politica invariata)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def entry_api() -> List[Dict[str, Any]]:
    """Entry API-Football VERE (righe di ripiego dei due sidecar)."""
    out = [r["payload"] for ev in ("35760084", "35797769") for r in _sidecar(ev)
           if r["source"] == "api_football"]
    assert len(out) == 13
    return out


def _api_provider(fixture_id: Optional[int], risposte: List[Any]) -> Any:
    from api_client import APIFootballClient

    from Betfair.stream.scores.api_football import ApiFootballProvider

    client = APIFootballClient()
    coda = list(risposte)
    client.call = lambda endpoint, params=None, max_retries=3: coda.pop(0) if coda else {}  # type: ignore[method-assign]
    return ApiFootballProvider(fixture_id=fixture_id, client=client)


def test_fonte_api_football(entry_api: List[Dict[str, Any]]) -> None:
    entry = entry_api[2]                                    # 1H, minuto 1
    fonte = FonteApiFootball(_api_provider(1515877, [{"response": [entry]}]))
    let = fonte.leggi([EID])[EID]
    assert let["fonte"] == "api_football" and let["origine"] == "api_football"
    assert let["grezzo"] == entry
    assert FonteApiFootball(_api_provider(None, [{"response": [entry]}])).leggi([EID]) == {}


def test_circuito_identico_al_poller_di_oggi(record_ips: List[Dict[str, Any]],
                                             entry_api: List[Dict[str, Any]]) -> None:
    """Stessa sequenza al poller di oggi (``ScanFeedScoreProvider`` +
    ``ApiFootballProvider``) e al circuito nuovo: stesse risposte, stessa
    sorgente, stesso circuito aperto/chiuso, stesso ``fallback_count``."""
    ora = [0.0]
    esiti = ["ok", "ko", "ko", "ko", "ko", "ok", "ko", "ok", "ok"]
    passi = [0.0, 1.0, 1.0, 1.0, 1.0, 130.0, 1.0, 1.0, 1.0]
    risposte_api = [{"response": [entry_api[2]]}] * len(esiti)

    def costruisci(nuovo: bool) -> Tuple[Any, Any, List[Any]]:
        righe: List[Dict[str, Any]] = []
        client, chiamate = _client_con([])
        diretto = BetfairInPlayProvider(client)
        cache = _cache(righe, None)
        if nuovo:
            fonte = FonteCircuitoCalcio(FonteIpsRunner(diretto, cache=cache),
                                        lambda eid: _api_provider(1515877, list(risposte_api)),
                                        threshold=3, retry_primary_sec=120.0, clock=lambda: ora[0])
            return fonte, righe, chiamate
        poller = ScorePoller(SF.ScanFeedScoreProvider(diretto, cache=cache),
                             _api_provider(1515877, list(risposte_api)),
                             threshold=3, retry_primary_sec=120.0, clock=lambda: ora[0])
        return poller, righe, chiamate

    vecchio, righe_v, _ = costruisci(False)
    nuovo, righe_n, _ = costruisci(True)
    for i, (esito, passo) in enumerate(zip(esiti, passi)):
        ora[0] += passo
        righe_v.clear()
        righe_n.clear()
        if esito == "ok":
            righe_v.append(_riga(record_ips[i], 1.0))
            righe_n.append(_riga(record_ips[i], 1.0))
        snap = vecchio.poll(EID)
        let = nuovo.leggi([EID]).get(EID)
        pn = nuovo.pollers[EID]
        assert (pn.circuit_open, pn.fallback_count, pn.current_source) == \
            (vecchio.circuit_open, vecchio.fallback_count, vecchio.current_source), i
        assert (let is None) == (snap is None)
        if snap is not None:
            atteso = "api_football" if vecchio.current_source == "api_football" else "ips_scanner"
            assert let["fonte"] == atteso
            assert let["grezzo"] == snap.payload
    assert vecchio.fallback_count > 0 and vecchio.circuit_open is False


# ---------------------------------------------------------------------------
# registrazione (banco)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def cartella_banco(tmp_path_factory: pytest.TempPathFactory) -> str:
    base = tmp_path_factory.mktemp("live_raw")
    for ev in ("35760084", "35797769"):
        dst = base / ev
        dst.mkdir()
        src = os.path.join(REGISTRAZIONI, ev, f"{ev}.scores.jsonl.gz")
        with gzip.open(src, "rb") as a, open(dst / f"{ev}.scores.jsonl", "wb") as b:
            shutil.copyfileobj(a, b)
    return str(base)


def test_registrazione_scorre_come_il_banco(cartella_banco: str) -> None:
    from Betfair.stream.backtest.banco_comune import carica_punteggi

    for ev, attese, ripieghi in (("35760084", 96, 3), ("35797769", 124, 10)):
        fonte = FonteRegistrazione(cartella_banco, ev)
        assert fonte.leggi([ev]) == {}                      # non aperta: niente
        assert fonte.apri() == attese
        assert fonte.record == carica_punteggi(cartella_banco, ev, "calcio")
        origini = []
        for i, (ts, rec) in enumerate(fonte.record):
            fonte.posiziona(ts)
            let = fonte.leggi([ev])[ev]
            assert let["grezzo"] is rec and let["istante_ms"] == ts and fonte.indice() == i + 1
            assert let["fonte"] == "registrazione" and let["trasporto"] == "file"
            origini.append(let["origine"])
        assert origini.count("api_football") == ripieghi
        primo = fonte.record[0][0]
        fonte.posiziona(primo - 1)
        assert fonte.leggi([ev]) == {}
        fonte.ritardo_s = 2.0
        fonte.posiziona(primo + 1999)
        assert fonte.leggi([ev]) == {}                      # ritardo aggiunto dichiarato
        fonte.posiziona(primo + 2000)
        assert fonte.leggi([ev])[ev]["istante_ms"] == primo
        assert fonte.leggi(["altro"]) == {}
        fonte.chiudi()
        assert fonte.leggi([ev]) == {}


def test_registrazione_tennis(tmp_path: Any) -> None:
    """Formato del registratore tennis (``{"t", "score"}``, ``tennis_recorder``)."""
    eid = "35790084"
    (tmp_path / eid).mkdir()
    righe = [{"t": 1_783_000_000.5, "score": _tennis(eid, "15", "0")},
             {"t": 1_783_000_010.0, "score": _tennis(eid, "30", "0")}]
    with open(tmp_path / eid / f"{eid}.score.jsonl", "w", encoding="utf-8") as fh:
        fh.write("\n".join(json.dumps(r) for r in righe) + "\n")
    fonte = FonteRegistrazione(str(tmp_path), eid, sport="tennis")
    assert fonte.apri() == 2
    fonte.posiziona(1_783_000_005_000)
    let = fonte.leggi([eid])[eid]
    assert let["sport"] == "tennis" and let["grezzi"] == [righe[0]["score"]]
    assert let["istante_ms"] == 1_783_000_000_500


# ---------------------------------------------------------------------------
# canale 47336
# ---------------------------------------------------------------------------
def test_canale_righe_battito_e_stato() -> None:
    from Betfair.safe_strategy import canale_scan as CS

    lettore = CS.ClientScan(CS.porta_scan(), CS.CacheScan())   # mai avviato: nessun socket
    riga = {"event_id": EID, "sport": "calcio", "updated_at": _iso(T0 - 1.0),
            "payload": {"minute": 12, "odds_ts_ms": int(T0 * 1000)}}
    assert lettore.incassa(json.dumps({"t": CS.TOPIC_SCAN["calcio"], "d": riga})) is True
    stato = {"flusso": {"calcolato_ms": int(T0 * 1000), "eventi_fermi": {}}}
    lettore.incassa(json.dumps({"t": CS.TOPIC_SCANNER_STATO, "d": stato}))
    fonte = FonteCanale(lettore)
    let = fonte.leggi([EID, "2"])
    assert set(let) == {EID}
    assert let[EID]["riga"] == riga and let[EID]["trasporto"] == "canale"
    assert let[EID]["scanner_s"] is None                   # scollegato: battito che non vale
    assert let[EID]["stato_scanner"] == stato
    lettore.collegato = True
    assert fonte.leggi([EID])[EID]["scanner_s"] is not None
    assert lettore._thread is None
