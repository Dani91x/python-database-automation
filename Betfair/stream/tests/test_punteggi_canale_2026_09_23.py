"""PUNTEGGI_CANALE (23/09): minuto e punteggio dal canale locale dello scanner.

Regola permanente dell'utente (23/09): chi opera live legge dal canale al tick,
il DB e' SOLO il ripiego quando il canale tace, UN SOLO poll dei punteggi per
tutti i consumatori.

Il poll esterno e' gia' unico (lo scanner, IPS in batch ogni 2 s) e la riga di
scan porta gia' minuto/punteggio/``score_raw``: la stessa riga esce sul canale
47336 a ogni cambio. Qui si prova che:

  PRODUTTORE  la riga che lo scanner spinge sul canale porta ESATTAMENTE il
              punteggio e il minuto che ha letto dall'IPS (stesso parser), e un
              gol esce subito, anche dentro il freno del DB;
  CONSUMATORE ``ScanRowCache`` (runner calcio, runner tennis, board, Omega)
              preferisce la riga del canale se piu' recente, ricade al DB alla
              cadenza di oggi se il canale e' muto, il canale non aggiunge mai
              una partita, il DB si rilegge al passo lento SOLO se ogni evento
              e' coperto dal canale;
  INTERRUTTORE spento = traccia IDENTICA alla cache di prima (righe servite,
              select eseguite, select di stato), anche con un canale fresco.

I FINTI: nessuno sul percorso del dato. Lo scanner e' ``service.Scanner`` vero,
il book e' ``MarketBook`` di betfairlightweight, lo stato IPS ha le chiavi
dell'IPS (``timeElapsed``, ``score.home.score``...), il messaggio passa per
``json`` come sul filo e lo incassa ``canale_scan.ClientScan`` vero (senza
socket: ``incassa`` e' il pezzo che la sessione chiama per ogni messaggio).
Finti solo il DB (``fetch``/``fetch_status`` che contano) e il canale del
produttore (che serializza come il vero). File ASCII-only.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

from betfairlightweight.resources.bettingresources import MarketBook

from Betfair.safe_strategy import canale_scan as CS
from Betfair.safe_strategy import scanner as SC
from Betfair.safe_strategy import service
from Betfair.stream.scores import scan_feed as sf
from Betfair.stream.scores.betfair_inplay import parse_score_dict


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    monkeypatch.delenv(sf.ENV_PUNTEGGI_CANALE, raising=False)
    sf.azzera_lettore_canale()
    yield
    sf.azzera_lettore_canale()


def _iso(age_sec: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=age_sec)).isoformat()


def stato_ips(minuto: int, casa: int, ospiti: int, rossi_ospiti: int = 0) -> Dict[str, Any]:
    """Lo stato IPS come lo restituisce ``scoresAndBroadcast``/``get_scores``."""
    return {
        "eventId": 31000001, "timeElapsed": minuto, "timeElapsedSeconds": minuto * 60 + 17,
        "matchStatus": "SecondHalf" if minuto > 45 else "FirstHalf",
        "score": {"home": {"name": "Roma", "score": str(casa), "numberOfRedCards": 0,
                           "numberOfYellowCards": 1, "numberOfCorners": 3},
                  "away": {"name": "Lazio", "score": str(ospiti),
                           "numberOfRedCards": rossi_ospiti, "numberOfYellowCards": 2,
                           "numberOfCorners": 5},
                  "bookingPoints": 40},
    }


# ===========================================================================
# PRODUTTORE: lo scanner vero, un book vero, il canale che serializza
# ===========================================================================
def _runner(sid: int, back, lay) -> dict:
    return {"selectionId": sid, "status": "ACTIVE", "handicap": 0.0,
            "lastPriceTraded": None, "totalMatched": 0.0,
            "ex": {"availableToBack": [{"price": back[0], "size": back[1]}],
                   "availableToLay": [{"price": lay[0], "size": lay[1]}],
                   "tradedVolume": []}}


class _Liv:
    __slots__ = ("price", "size")

    def __init__(self, p, s):
        self.price, self.size = p, s


class _Ex:
    __slots__ = ("available_to_back", "available_to_lay", "traded_volume")

    def __init__(self, atb, atl):
        self.available_to_back = [_Liv(x["price"], x["size"]) for x in atb]
        self.available_to_lay = [_Liv(x["price"], x["size"]) for x in atl]
        self.traded_volume = []


def _book(market_id: str, runners: list, pt_ms: int) -> MarketBook:
    mb = MarketBook(marketId=market_id, status="OPEN", inplay=True, totalMatched=0.0,
                    runners=runners, betDelay=5, publishTime=pt_ms)
    for rb, grezzo in zip(mb.runners, runners):
        rb.ex = _Ex(grezzo["ex"]["availableToBack"], grezzo["ex"]["availableToLay"])
    return mb


PREZZI = [_runner(11, (2.0, 100.0), (2.04, 90.0)), _runner(22, (3.4, 80.0), (3.5, 70.0)),
          _runner(33, (4.0, 60.0), (4.2, 50.0))]


class CanaleProduttore:
    """Il canale come lo usa lo scanner: serializza DENTRO ``publish`` (come
    ``LocalChannel.publish``) e tiene il testo che va sul filo, nel formato del
    protocollo ``{"t": topic, "d": payload}``."""

    def __init__(self) -> None:
        self.filo: List[str] = []

    def publish(self, topic: str, payload: Any) -> None:
        self.filo.append(json.dumps({"t": topic, "d": payload}, default=str))

    def statistiche(self) -> Dict[str, Any]:
        return {"saltati": 0, "saltati_client": 0, "client": 1}


def _scanner_calcio(canale: CanaleProduttore) -> service.Scanner:
    scan = service.Scanner(api_client=None, dry=True, use_stream=False, canale=False)
    inizio = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
    scan.sports["calcio"].metas = {"c1": {
        "event_id": "c1", "market_id": "1.200", "event_name": "Roma v Lazio",
        "open_date": inizio, "competition": "Serie A", "runners": [],
        "sides": {"home": 11, "draw": 22, "away": 33},
    }}
    scan.sports["tennis"].metas = {}
    scan.events["c1"] = {"sport": "calcio", "inplay": True, "mo_status": "OPEN"}
    scan._rebuild_market_index()
    scan.canale = canale
    return scan


def _righe_sul_filo(canale: CanaleProduttore, topic: str) -> List[Dict[str, Any]]:
    out = []
    for testo in canale.filo:
        msg = json.loads(testo)
        if msg["t"] == topic:
            out.append(msg["d"])
    return out


def test_produttore_la_riga_sul_canale_porta_esattamente_il_punteggio_letto():
    """Lo scanner legge uno stato IPS: sul filo, topic ``scan_calcio``, escono
    minuto/punteggio/rossi uguali a cio' che il parser dell'IPS ne ricava, e lo
    ``score_raw`` e' lo stato letto (meno i soli campi al secondo)."""
    canale = CanaleProduttore()
    scan = _scanner_calcio(canale)
    scan._apply_market_book(_book("1.200", PREZZI, 1789000000000), dallo_stream=True)
    stato = stato_ips(63, 2, 1, rossi_ospiti=1)
    assert scan.apply_score_state("c1", stato) is True
    righe_db, _ = scan.build_rows(datetime.now(timezone.utc))

    atteso = parse_score_dict("c1", stato)
    sul_filo = _righe_sul_filo(canale, "scan_calcio")
    assert len(sul_filo) == 1 and len(righe_db) == 1
    p = sul_filo[0]["payload"]
    assert (p["minute"], p["score_home"], p["score_away"]) == (63, 2, 1)
    assert (p["minute"], p["score_home"], p["score_away"]) == (
        atteso.minute, atteso.score_home, atteso.score_away)
    assert (p["red_home"], p["red_away"]) == (atteso.red_home, atteso.red_away) == (0, 1)
    assert p["score_raw"] == SC.strip_volatile_state(stato)
    # e la riga sul filo e' quella che va sul DB, valore per valore
    assert sul_filo[0] == json.loads(json.dumps(righe_db[0], default=str))
    # il consumatore la rilegge con lo STESSO parser del runner: stesso esito
    riletto = parse_score_dict("c1", p["score_raw"])
    assert (riletto.minute, riletto.score_home, riletto.score_away) == (63, 2, 1)


def test_produttore_il_gol_esce_subito_anche_dentro_il_freno_del_db():
    """Un gol cambia la firma CRITICA: esce sul canale e sul DB nello stesso
    istante, senza aspettare i 2,5 s del freno delle quote."""
    canale = CanaleProduttore()
    scan = _scanner_calcio(canale)
    adesso = datetime.now(timezone.utc)
    scan._apply_market_book(_book("1.200", PREZZI, 1789000000000), dallo_stream=True)
    scan.apply_score_state("c1", stato_ips(63, 0, 0))
    scan.build_rows(adesso)
    scan.apply_score_state("c1", stato_ips(63, 1, 0))
    righe_db, _ = scan.build_rows(adesso)
    sul_filo = _righe_sul_filo(canale, "scan_calcio")
    assert len(sul_filo) == 2, "il gol non e' uscito sul canale"
    assert (sul_filo[-1]["payload"]["score_home"], sul_filo[-1]["payload"]["score_away"]) == (1, 0)
    assert len(righe_db) == 1


# ===========================================================================
# CONSUMATORE: ClientScan vero + ScanRowCache
# ===========================================================================
class DbFinto:
    """``safe_strategy_scan``/``safe_strategy_status`` che contano le select.
    Righe con le colonne vere: event_id, sport, payload, updated_at."""

    def __init__(self, righe: List[Dict[str, Any]], battito_eta: Optional[float] = 1.0):
        self.righe = righe
        self.battito_eta = battito_eta
        self.select: List[List[str]] = []
        self.select_stato = 0

    def fetch(self, ids: List[str]) -> List[Dict[str, Any]]:
        self.select.append(list(ids))
        return [dict(r) for r in self.righe if r["event_id"] in ids]

    def fetch_status(self) -> Optional[Dict[str, Any]]:
        self.select_stato += 1
        if self.battito_eta is None:
            return None
        return {"id": "scanner", "payload": {}, "updated_at": _iso(self.battito_eta)}


def riga(eid: str, eta: float, minuto: int, casa: int, ospiti: int,
         odds_ts: Optional[int] = 1789000000000, sport: str = "calcio") -> Dict[str, Any]:
    payload: Dict[str, Any] = {"inplay": True, "minute": minuto, "score_home": casa,
                               "score_away": ospiti,
                               "score_raw": SC.strip_volatile_state(stato_ips(minuto, casa, ospiti))}
    if odds_ts is not None:
        payload["odds_ts_ms"] = odds_ts
    return {"event_id": eid, "sport": sport, "payload": payload, "updated_at": _iso(eta)}


def lettore_vivo(*righe_canale: Dict[str, Any], battito: bool = True) -> CS.ClientScan:
    """Il client VERO, alimentato da messaggi sul formato del filo."""
    cl = CS.ClientScan(47336, CS.CacheScan())
    cl.collegato = True
    if battito:
        cl.incassa(json.dumps({"t": CS.TOPIC_SCANNER_STATO, "d": {"monitored": 1}}))
    for r in righe_canale:
        topic = CS.TOPIC_SCAN[r.get("sport", "calcio")]
        assert cl.incassa(json.dumps({"t": topic, "d": r})) is True
    return cl


class Orologio:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def _cache(db: DbFinto, lettore: Any, orologio: Orologio) -> sf.ScanRowCache:
    return sf.ScanRowCache(ttl_sec=1.0, fetch=db.fetch, fetch_status=db.fetch_status,
                           clock=orologio, canale=lettore)


class _Diretto:
    name = "betfair"

    def __init__(self) -> None:
        self.chiamate = 0

    def get_score(self, event_id: str):
        self.chiamate += 1
        return None

    def get_timeline(self, event_id: str):
        self.chiamate += 1
        return []

    def healthcheck(self) -> bool:
        return True


def test_consumatore_preferisce_il_canale_se_piu_recente(monkeypatch):
    monkeypatch.setenv(sf.ENV_PUNTEGGI_CANALE, "1")
    db = DbFinto([riga("e1", eta=4.0, minuto=62, casa=0, ospiti=0)])
    lettore = lettore_vivo(riga("e1", eta=0.5, minuto=63, casa=1, ospiti=0))
    orologio = Orologio()
    cache = _cache(db, lettore, orologio)
    diretto = _Diretto()
    prov = sf.ScanFeedScoreProvider(diretto, cache=cache)
    snap = prov.get_score("e1")
    assert snap is not None and (snap.minute, snap.score_home, snap.score_away) == (63, 1, 0)
    assert diretto.chiamate == 0 and cache.dal_canale >= 1
    assert cache.canale_vivo() is True


def test_consumatore_a_parita_vince_il_db(monkeypatch):
    """Stessa riga (stesso ``updated_at``) = vince il DB, il libro mastro."""
    monkeypatch.setenv(sf.ENV_PUNTEGGI_CANALE, "1")
    r = riga("e1", eta=2.0, minuto=63, casa=1, ospiti=0)
    db = DbFinto([r])
    lettore = lettore_vivo(dict(r))
    cache = _cache(db, lettore, Orologio())
    out = cache.rows_for(["e1"])
    assert out["e1"] == r and cache.dal_canale == 0


def test_consumatore_riga_del_canale_senza_odds_ts_non_sposta_il_db(monkeypatch):
    """Invariante B11 (``canale_scan.piu_recente``): senza l'istante del prezzo
    la riga del canale non entra, e l'evento NON conta come coperto."""
    monkeypatch.setenv(sf.ENV_PUNTEGGI_CANALE, "1")
    db = DbFinto([riga("e1", eta=4.0, minuto=62, casa=0, ospiti=0)])
    lettore = lettore_vivo(riga("e1", eta=0.5, minuto=63, casa=1, ospiti=0, odds_ts=None))
    orologio = Orologio()
    cache = _cache(db, lettore, orologio)
    assert cache.rows_for(["e1"])["e1"]["payload"]["minute"] == 62
    orologio.t += 1.5
    cache.rows_for(["e1"])
    assert len(db.select) == 2, "evento non coperto: il DB va riletto alla cadenza di oggi"


def test_consumatore_il_canale_non_aggiunge_partite(monkeypatch):
    monkeypatch.setenv(sf.ENV_PUNTEGGI_CANALE, "1")
    db = DbFinto([riga("e1", eta=1.0, minuto=10, casa=0, ospiti=0)])
    lettore = lettore_vivo(riga("e1", eta=0.2, minuto=11, casa=0, ospiti=0),
                           riga("e2", eta=0.2, minuto=30, casa=2, ospiti=2))
    orologio = Orologio()
    cache = _cache(db, lettore, orologio)
    out = cache.rows_for(["e1", "e2"])
    assert "e2" not in out, "il canale ha aggiunto una partita che il DB non elenca"
    # e2 visto dal canale ma non dal DB: il DB torna alla cadenza di oggi
    orologio.t += 1.5
    cache.rows_for(["e1", "e2"])
    assert len(db.select) == 2


def test_consumatore_canale_vivo_e_coperto_il_db_si_rilegge_al_riallineamento(monkeypatch):
    """IL POLL DUPLICATO SPENTO: con il canale vivo e ogni evento coperto la
    select di ``safe_strategy_scan`` passa da 1/s a 1 ogni
    ``RISINC_DB_CANALE_SEC``, e quella di stato non si fa piu'."""
    monkeypatch.setenv(sf.ENV_PUNTEGGI_CANALE, "1")
    db = DbFinto([riga("e1", eta=3.0, minuto=62, casa=0, ospiti=0)])
    lettore = lettore_vivo(riga("e1", eta=0.5, minuto=63, casa=1, ospiti=0))
    orologio = Orologio()
    cache = _cache(db, lettore, orologio)
    prov = sf.ScanFeedScoreProvider(_Diretto(), cache=cache)
    for _ in range(9):                       # 9 s di score_worker, un giro al secondo
        assert prov.get_score("e1").score_home == 1
        orologio.t += 1.0
    assert len(db.select) == 1, db.select
    assert db.select_stato == 0, "lo stato dello scanner va letto dal battito sul canale"
    orologio.t += 1.5                         # oltre i 10 s: riallineamento
    prov.get_score("e1")
    assert len(db.select) == 2


def test_consumatore_riga_identica_al_db_conta_come_coperta(monkeypatch):
    """Dopo un riallineamento la riga del DB e quella del canale sono la
    STESSA (lo scanner spinge lo stesso oggetto che scrive): l'evento resta
    coperto e il DB non torna a 1/s solo perche' nel frattempo non e' cambiato
    niente (0-0 fermo, quote ferme)."""
    monkeypatch.setenv(sf.ENV_PUNTEGGI_CANALE, "1")
    r = riga("e1", eta=2.0, minuto=63, casa=0, ospiti=0)
    db = DbFinto([r])
    lettore = lettore_vivo(dict(r))
    orologio = Orologio()
    cache = _cache(db, lettore, orologio)
    for _ in range(8):
        cache.rows_for(["e1"])
        orologio.t += 1.0
    assert len(db.select) == 1, db.select


def test_consumatore_canale_muto_ricade_al_db_alla_cadenza_di_oggi(monkeypatch):
    """Nessun battito dello scanner sul canale = canale MUTO: si legge il DB
    come oggi (select ogni secondo, stato dal DB), la riga del canale non
    entra, e il diretto resta il ripiego se la riga manca."""
    monkeypatch.setenv(sf.ENV_PUNTEGGI_CANALE, "1")
    db = DbFinto([riga("e1", eta=3.0, minuto=62, casa=0, ospiti=0)])
    lettore = lettore_vivo(riga("e1", eta=0.5, minuto=63, casa=1, ospiti=0), battito=False)
    orologio = Orologio()
    cache = _cache(db, lettore, orologio)
    prov = sf.ScanFeedScoreProvider(_Diretto(), cache=cache)
    for _ in range(3):
        assert prov.get_score("e1").score_home == 0
        orologio.t += 1.0
    assert len(db.select) == 3
    assert db.select_stato >= 1
    assert cache.canale_vivo() is False


def test_consumatore_battito_vecchio_o_socket_caduto_e_muto(monkeypatch):
    monkeypatch.setenv(sf.ENV_PUNTEGGI_CANALE, "1")
    lettore = lettore_vivo()
    assert sf.canale_vivo(lettore) is True
    lettore.stato_mono = time.monotonic() - (sf.SCANNER_ALIVE_MAX_AGE_SEC + 1.0)
    assert sf.canale_vivo(lettore) is False
    lettore.stato_mono = time.monotonic()
    lettore.collegato = False
    assert sf.canale_vivo(lettore) is False


def test_consumatore_eta_dello_scanner_dal_battito_del_canale(monkeypatch):
    monkeypatch.setenv(sf.ENV_PUNTEGGI_CANALE, "1")
    db = DbFinto([], battito_eta=25.0)
    lettore = lettore_vivo()
    cache = _cache(db, lettore, Orologio())
    eta = cache.scanner_age_sec()
    assert eta is not None and eta < 5.0
    assert db.select_stato == 0


def test_consumatore_il_ritorno_del_canale_muto_rimette_la_cadenza_di_oggi(monkeypatch):
    """Canale vivo e coperto (passo lento), poi il battito si ferma: dal giro
    dopo il DB torna a 1/s. Mai restare al passo lento con il canale muto."""
    monkeypatch.setenv(sf.ENV_PUNTEGGI_CANALE, "1")
    db = DbFinto([riga("e1", eta=3.0, minuto=62, casa=0, ospiti=0)])
    lettore = lettore_vivo(riga("e1", eta=0.5, minuto=63, casa=1, ospiti=0))
    orologio = Orologio()
    cache = _cache(db, lettore, orologio)
    cache.rows_for(["e1"])
    orologio.t += 1.5
    cache.rows_for(["e1"])
    assert len(db.select) == 1
    lettore.stato_mono = time.monotonic() - 60.0
    orologio.t += 1.5
    out = cache.rows_for(["e1"])
    assert len(db.select) == 2 and out["e1"]["payload"]["minute"] == 62


# ===========================================================================
# INTERRUTTORE
# ===========================================================================
def _traccia(cache: sf.ScanRowCache, db: DbFinto, orologio: Orologio) -> List[Any]:
    """Una sequenza di giri come quella dello score_worker, con un evento
    nuovo a meta'. Registra cio' che la cache SERVE e cio' che CHIEDE al DB."""
    passi: List[Any] = []
    for i in range(14):
        ids = ["e1"] if i < 5 else ["e1", "e2"]
        out = cache.rows_for(ids)
        passi.append(("righe", json.dumps(out, sort_keys=True, default=str)))
        passi.append(("eta_scanner_nota", cache.scanner_age_sec() is not None))
        passi.append(("select", len(db.select), db.select_stato))
        orologio.t += 0.7
    return passi


@pytest.mark.parametrize("valore", [None, "", "0", "no", "false", "acceso", " "])
def test_interruttore_spento_traccia_identica_anche_con_un_canale_fresco(monkeypatch, valore):
    if valore is None:
        monkeypatch.delenv(sf.ENV_PUNTEGGI_CANALE, raising=False)
    else:
        monkeypatch.setenv(sf.ENV_PUNTEGGI_CANALE, valore)
    righe = [riga("e1", eta=3.0, minuto=62, casa=0, ospiti=0),
             riga("e2", eta=3.0, minuto=20, casa=1, ospiti=1)]
    db_a, db_b = DbFinto(list(righe)), DbFinto(list(righe))
    oa, ob = Orologio(), Orologio()
    senza = sf.ScanRowCache(ttl_sec=1.0, fetch=db_a.fetch, fetch_status=db_a.fetch_status,
                            clock=oa)
    lettore = lettore_vivo(riga("e1", eta=0.1, minuto=70, casa=3, ospiti=0),
                           riga("e2", eta=0.1, minuto=25, casa=1, ospiti=2))
    con = _cache(db_b, lettore, ob)
    assert _traccia(senza, db_a, oa) == _traccia(con, db_b, ob)
    assert con.dal_canale == 0 and con.canale_vivo() is False


def test_interruttore_spento_nessun_lettore_nessun_websockets(monkeypatch):
    """Spento: ``lettore_canale`` non costruisce nulla e la cache di processo
    non lo chiede nemmeno."""
    chiamato = {"n": 0}

    def _non_chiamarmi(*a, **k):
        chiamato["n"] += 1
        raise AssertionError("client costruito a interruttore spento")

    monkeypatch.setattr(CS, "ClientScan", _non_chiamarmi)
    assert sf.lettore_canale() is None
    db = DbFinto([riga("e1", eta=1.0, minuto=1, casa=0, ospiti=0)])
    cache = sf.ScanRowCache(ttl_sec=1.0, fetch=db.fetch, fetch_status=db.fetch_status,
                            clock=Orologio(), canale_auto=True)
    cache.rows_for(["e1"])
    cache.scanner_age_sec()
    assert chiamato["n"] == 0


@pytest.mark.parametrize("valore", ["1", "true", "si", "yes", "TRUE", " Si "])
def test_interruttore_acceso_solo_se_scritto(monkeypatch, valore):
    monkeypatch.setenv(sf.ENV_PUNTEGGI_CANALE, valore)
    assert sf.punteggi_canale_acceso() is True


def test_interruttore_acceso_il_lettore_di_processo_e_uno_solo(monkeypatch):
    monkeypatch.setenv(sf.ENV_PUNTEGGI_CANALE, "1")
    creati: List[Any] = []

    class _ClientSenzaRete(CS.ClientScan):
        def avvia(self) -> None:          # nessun socket nel test
            creati.append(self)

    monkeypatch.setattr(CS, "ClientScan", _ClientSenzaRete)
    a = sf.lettore_canale()
    b = sf.lettore_canale()
    assert a is b and len(creati) == 1
    assert a.porta == CS.porta_scan()


def test_il_lettore_non_solleva_mai_verso_chi_legge(monkeypatch):
    """Un lettore rotto (qualunque eccezione) = canale muto, righe del DB."""
    monkeypatch.setenv(sf.ENV_PUNTEGGI_CANALE, "1")

    class _Rotto:
        def eta_stato_s(self):
            raise RuntimeError("rotto")

    db = DbFinto([riga("e1", eta=1.0, minuto=5, casa=0, ospiti=0)])
    cache = _cache(db, _Rotto(), Orologio())
    assert cache.rows_for(["e1"])["e1"]["payload"]["minute"] == 5
    assert cache.canale_vivo() is False


def test_fusione_rotta_torna_le_righe_del_db(monkeypatch):
    monkeypatch.setenv(sf.ENV_PUNTEGGI_CANALE, "1")
    lettore = lettore_vivo()

    class _CacheRotta:
        def riga(self, eid):
            raise RuntimeError("rotta")

    lettore.cache = _CacheRotta()
    db = DbFinto([riga("e1", eta=1.0, minuto=5, casa=0, ospiti=0)])
    cache = _cache(db, lettore, Orologio())
    assert cache.rows_for(["e1"])["e1"]["payload"]["minute"] == 5


# ===========================================================================
# DAL PRODUTTORE AL CONSUMATORE, sul formato del filo
# ===========================================================================
def test_dal_produttore_al_runner_il_punteggio_arriva_identico(monkeypatch):
    """Scanner vero -> testo sul filo -> ClientScan vero -> ScanRowCache ->
    ScanFeedScoreProvider (il primario del runner calcio): il minuto e il
    punteggio che il runner vede sono quelli che lo scanner ha letto dall'IPS,
    PRIMA che il DB li abbia (la riga del DB e' quella del giro precedente)."""
    monkeypatch.setenv(sf.ENV_PUNTEGGI_CANALE, "1")
    canale = CanaleProduttore()
    scan = _scanner_calcio(canale)
    scan._apply_market_book(_book("1.200", PREZZI, 1789000000000), dallo_stream=True)
    scan.apply_score_state("c1", stato_ips(70, 0, 0))
    righe_db, _ = scan.build_rows(datetime.now(timezone.utc))
    db = DbFinto([json.loads(json.dumps(r, default=str)) for r in righe_db])
    time.sleep(0.01)                             # updated_at strettamente dopo
    scan.apply_score_state("c1", stato_ips(71, 0, 1))
    scan.build_rows(datetime.now(timezone.utc))

    cl = CS.ClientScan(47336, CS.CacheScan())
    cl.collegato = True
    cl.incassa(json.dumps({"t": CS.TOPIC_SCANNER_STATO, "d": {}}))
    for testo in canale.filo:
        cl.incassa(testo)
    cache = _cache(db, cl, Orologio())
    diretto = _Diretto()
    snap = sf.ScanFeedScoreProvider(diretto, cache=cache).get_score("c1")
    assert (snap.minute, snap.score_home, snap.score_away) == (71, 0, 1)
    assert diretto.chiamate == 0
    # a interruttore spento lo stesso runner vede il DB (il giro precedente)
    monkeypatch.setenv(sf.ENV_PUNTEGGI_CANALE, "0")
    cache2 = _cache(db, cl, Orologio())
    snap2 = sf.ScanFeedScoreProvider(_Diretto(), cache=cache2).get_score("c1")
    assert (snap2.minute, snap2.score_home, snap2.score_away) == (70, 0, 0)


def test_il_battito_non_e_una_riga():
    cl = CS.ClientScan(47336, CS.CacheScan())
    assert cl.eta_stato_s() is None
    assert cl.incassa(json.dumps({"t": CS.TOPIC_SCANNER_STATO, "d": {"monitored": 3}})) is False
    assert cl.cache.stato()["righe"] == 0 and cl.cache.scartate == 0
    assert cl.stato_mono > 0
    assert cl.eta_stato_s() is None, "socket non collegato: il battito non dice niente"
    cl.collegato = True
    assert cl.eta_stato_s() is not None and cl.eta_stato_s() < 1.0
