"""Mike legge le righe dello scanner dal canale locale 47336 (23/09).

Nessuna rete, nessun DB vero, nessun socket: il client e' il ``ClientScan`` di
Safe (importato), il suo thread non parte (``avvia`` neutralizzato) e i
messaggi entrano da ``ClientScan.incassa`` con la forma VERA del canale
(``{"t": "scan_calcio", "d": riga}``, ``local_channel.publish``). Le righe
hanno le STESSE chiavi di ``db.fetch_scan_rows`` (event_id, sport, payload,
updated_at) piu' ``payload.odds_ts_ms`` come le pubblica lo scanner.

I cinque punti del brief:
  (1) interruttore spento -> chiamate al finto DB IDENTICHE a quelle di prima;
  (2) acceso + canale fresco -> nessuna lettura della scan, decisioni
      identiche a quelle prese con le stesse righe dal DB;
  (3) canale muto -> ripiego sul DB;
  (4) il canale riprende -> si torna al canale;
  (5) vince la riga piu' fresca (a parita' il DB).

File ASCII-only (console Windows cp1252).
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Dict, List

import pytest

from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_feed import payload, row
from Betfair.mike.tests.test_mike_service import NOW, FakeDB, FakeMarket
from Betfair.safe_strategy import canale_scan as CS

ENV = "MIKE_LEGGE_CANALE"


# --------------------------------------------------------------------- aiuti
class Traccia:
    """Proxy del finto DB: registra OGNI chiamata (nome + argomenti)."""

    def __init__(self, db: Any) -> None:
        self._db = db
        self.chiamate: List[tuple] = []

    def __getattr__(self, nome: str) -> Any:
        valore = getattr(self._db, nome)
        if not callable(valore):
            return valore

        def chiama(*a: Any, **k: Any) -> Any:
            self.chiamate.append((nome, repr(a), repr(sorted(k.items()))))
            return valore(*a, **k)
        return chiama

    def conta(self, nome: str) -> int:
        return sum(1 for c in self.chiamate if c[0] == nome)


def _riga(p: Dict[str, Any], updated, odds_ts: bool = True) -> Dict[str, Any]:
    r = row(dict(p), updated)
    if odds_ts:
        r["payload"]["odds_ts_ms"] = int(updated.timestamp() * 1000)
    return r


def _spingi(riga: Dict[str, Any]) -> bool:
    """Un messaggio del canale con la forma di ``local_channel.publish``."""
    client = S._CANALE_FEED["client"]
    return client.incassa(json.dumps({"t": "scan_calcio", "d": riga}, default=str))


ENV_SVEGLIA = S._SV.ENV_MIKE_SVEGLIA


@pytest.fixture
def canale(monkeypatch):
    """Interruttore ACCESO e client avviato con ``avvia_client_scan`` (il
    thread del socket neutralizzato).

    ``MIKE_SVEGLIA_CANALE`` e' FORZATO spento: il file ``.env`` alla radice
    del repo lo tiene a ``1`` per il servizio vero, e senza questa riga il
    client di questo fixture (23/09, fusione) partirebbe ANCHE con la sveglia
    agganciata - questo fixture vuole la SOLA lettura, come il suo nome dice.
    """
    monkeypatch.setenv(ENV, "1")
    monkeypatch.delenv(ENV_SVEGLIA, raising=False)
    monkeypatch.setattr(CS.ClientScan, "avvia", lambda self: None)
    S.azzera_canale_scan()
    assert S.avvia_client_scan() is True
    yield S._CANALE_FEED
    S.azzera_canale_scan()


def _giro(db: Any, mk: Any, quando) -> Dict[str, Any]:
    return S.run_once(db=db, market=mk, now=quando, atlas=None)


def _esito(db: FakeDB) -> tuple:
    """Tutto cio' che Mike ha DECISO, senza gli istanti di scrittura."""
    eventi = {k: {kk: vv for kk, vv in v.items() if kk not in ("updated_at",)}
              for k, v in db.events.items()}
    return (repr(eventi), repr(db.trades), repr(db.kinds()))


# =============================================== (1) spento: chiamate identiche
def _vecchia_lettura(db: Any, params: Dict[str, Any], now_ts: float):
    """Le istruzioni di PRIMA (service.py a 09e0dd0), copiate alla lettera."""
    ttl_feed = float(params.get("feed_cache_s") or 0.0)
    if S._CACHE_FEED.fresco(now_ts, ttl_feed):
        rows = S._CACHE_FEED.valore
    else:
        rows = S._CACHE_FEED.metti(list(db.fetch_scan_rows() or []), now_ts)
    return rows, "db"


def _sequenza(db_finto: FakeDB) -> tuple:
    db = Traccia(db_finto)
    mk = FakeMarket()
    passi = [(0, payload()), (2, payload()), (4, payload()),
             (7, payload(u35=(1.47, 1.48, 30.0, 25.0))), (9, payload())]
    esiti = []
    for sec, p in passi:
        quando = NOW + timedelta(seconds=sec)
        db_finto.scan_rows = [_riga(p, quando)]
        esiti.append(_giro(db, mk, quando))
    return db.chiamate, _esito(db_finto), [sorted(e["stats"]) for e in esiti]


@pytest.mark.parametrize("valore", [None, "0", "", "no", "false"])
def test_1_interruttore_spento_chiamate_identiche_a_prima(monkeypatch, valore):
    params = {"stake": 10, "pre_exit_mode": "taker", "feed_cache_s": 4.0}
    # PRIMA: il ciclo con la lettura di prima
    with monkeypatch.context() as m:
        m.delenv(ENV, raising=False)
        m.setattr(S, "_righe_del_feed", _vecchia_lettura)
        S.svuota_le_cache()
        prima = _sequenza(FakeDB(params=dict(params)))
    # DOPO: il codice di oggi, interruttore spento (assente o valore non acceso)
    if valore is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, valore)
    S.svuota_le_cache()
    assert S.avvia_client_scan() is False
    dopo = _sequenza(FakeDB(params=dict(params)))
    assert dopo[0] == prima[0], "le chiamate al DB sono cambiate a interruttore spento"
    assert dopo[1] == prima[1]
    assert dopo[2] == prima[2]
    # con la cache del feed attiva la sequenza legge meno di un giro su uno:
    # la traccia sta davvero misurando la cadenza
    assert 1 < sum(1 for c in dopo[0] if c[0] == "fetch_scan_rows") < 5
    assert all("fonte_scan" not in k for k in dopo[2])


def test_1b_client_rimasto_in_memoria_ma_interruttore_spento_legge_come_prima(
        monkeypatch, canale):
    """Il client c'e' e ha righe fresche, ma l'interruttore viene spento: si
    legge il DB a ogni giro come prima, e il canale non entra."""
    quando = NOW
    _spingi(_riga(payload(u35=(1.47, 1.48, 30.0, 25.0)), quando + timedelta(seconds=1)))
    monkeypatch.delenv(ENV, raising=False)
    db_finto = FakeDB(params={"stake": 10})
    db = Traccia(db_finto)
    for i in range(3):
        db_finto.scan_rows = [_riga(payload(), quando)]
        righe, fonte = S._righe_del_feed(db, {"feed_cache_s": 0.0}, quando.timestamp() + i)
        assert fonte == "db"
        assert righe[0]["payload"]["ou"][0]["selections"][0]["lay"] == 1.52
    assert db.conta("fetch_scan_rows") == 3


# ======================== (2) acceso + canale fresco: niente letture, stesse decisioni
def test_2_canale_fresco_nessuna_lettura_scan_e_decisioni_identiche(monkeypatch, canale):
    params = {"stake": 10, "pre_exit_mode": "taker"}
    r0 = _riga(payload(), NOW)
    r1 = _riga(payload(u35=(1.47, 1.48, 30.0, 25.0)), NOW + timedelta(seconds=3))
    istanti = [NOW, NOW + timedelta(seconds=2), NOW + timedelta(seconds=4)]

    # RIFERIMENTO: interruttore spento, le stesse righe arrivano dal DB
    with monkeypatch.context() as m:
        m.delenv(ENV, raising=False)
        S._CACHE_FEED.svuota()
        rif = FakeDB(params=dict(params))
        rif_db = Traccia(rif)
        mk = FakeMarket()
        for quando, riga in zip(istanti, (r0, r0, r1)):
            rif.scan_rows = [json.loads(json.dumps(riga))]
            _giro(rif_db, mk, quando)
        assert rif_db.conta("fetch_scan_rows") == 3
    atteso = _esito(rif)
    # il riferimento DECIDE davvero qualcosa sul prezzo nuovo: il green taker
    assert any(t.get("strategy") == "under_green" for t in rif.trades)
    assert rif.events["E1"]["state"] == "PRE_GREEN_PENDING"

    # CANALE: il DB resta fermo a r0, il prezzo nuovo arriva SOLO dal canale
    S.svuota_le_cache()
    assert S.avvia_client_scan() is True
    db_finto = FakeDB(params=dict(params))
    db_finto.scan_rows = [json.loads(json.dumps(r0))]
    db = Traccia(db_finto)
    mk = FakeMarket()
    assert _spingi(r0)
    res1 = _giro(db, mk, istanti[0])
    assert db.conta("fetch_scan_rows") == 1      # la LISTA si legge una volta
    assert res1["stats"]["fonte_scan"] == "db"  # a parita' vince il DB
    _giro(db, mk, istanti[1])
    assert _spingi(r1)
    res3 = _giro(db, mk, istanti[2])
    assert db.conta("fetch_scan_rows") == 1, "letta la scan dal DB con il canale sano"
    assert res3["stats"]["fonte_scan"] == "canale"
    assert res3["stats"]["righe_dal_canale"] == 1
    assert _esito(db_finto) == atteso


# =================================================== (3) canale muto: ripiego DB
def test_3_canale_muto_ricade_sul_database(canale):
    db_finto = FakeDB(params={"stake": 10})
    db = Traccia(db_finto)
    t0 = NOW
    # una riga del canale VECCHIA (oltre FEED_FRESH_S): il canale tace
    _spingi(_riga(payload(u35=(1.40, 1.41, 30.0, 25.0)), t0 - timedelta(seconds=30)))
    db_finto.scan_rows = [_riga(payload(), t0 - timedelta(seconds=40))]
    for i in range(3):
        righe, fonte = S._righe_del_feed(db, {"feed_cache_s": 0.0}, t0.timestamp() + i)
        assert fonte == "db"
        assert righe[0]["payload"]["ou"][0]["selections"][0]["lay"] == 1.52
    assert db.conta("fetch_scan_rows") == 3


def test_3b_canale_mai_arrivato_niente_cadenza_di_oggi(canale):
    db_finto = FakeDB(params={"stake": 10})
    db = Traccia(db_finto)
    db_finto.scan_rows = [_riga(payload(), NOW)]
    for i in range(6):
        S._righe_del_feed(db, {"feed_cache_s": 4.0}, NOW.timestamp() + i)
    # 0..5 s con feed_cache_s=4: letture a 0 e a 4, come oggi
    assert db.conta("fetch_scan_rows") == 2


# ============================================ (4) il canale riprende: si torna li'
def test_4_il_canale_riprende_e_si_torna_al_canale(canale):
    db_finto = FakeDB(params={"stake": 10})
    db = Traccia(db_finto)
    t0 = NOW.timestamp()
    db_finto.scan_rows = [_riga(payload(), NOW)]
    p = {"feed_cache_s": 0.0}
    # muto: ogni giro legge il DB
    for i in range(2):
        assert S._righe_del_feed(db, p, t0 + i)[1] == "db"
    assert db.conta("fetch_scan_rows") == 2
    # riprende: riga fresca e piu' recente
    _spingi(_riga(payload(u35=(1.47, 1.48, 30.0, 25.0)), NOW + timedelta(seconds=2)))
    righe, fonte = S._righe_del_feed(db, p, t0 + 2.5)
    assert fonte == "canale"
    assert righe[0]["payload"]["ou"][0]["selections"][0]["lay"] == 1.48
    assert db.conta("fetch_scan_rows") == 2      # nessuna lettura in piu'
    # entro il riallineamento niente DB (23/09 M-1: la riga del canale conta
    # finche' ha al piu' 5 s, ``CS.MAX_ETA_CONTESTO_S`` come Omega)
    assert S._righe_del_feed(db, p, t0 + 6.5)[1] == "canale"
    assert db.conta("fetch_scan_rows") == 2
    # passato il riallineamento (10 s dall'ultima lettura) la lista si rilegge
    S._righe_del_feed(db, p, t0 + 11.5)
    assert db.conta("fetch_scan_rows") == 3
    # il canale torna muto (riga oltre 5 s): cadenza di oggi, di nuovo DB
    righe, fonte = S._righe_del_feed(db, p, t0 + 30)
    assert fonte == "db" and db.conta("fetch_scan_rows") == 4
    assert righe[0]["payload"]["ou"][0]["selections"][0]["lay"] == 1.52


# ================================================== (5) vince la riga piu' fresca
@pytest.mark.parametrize("delta_canale,odds_ts,attesa", [
    (+2, True, "canale"),    # canale piu' recente: vince il canale
    (0, True, "db"),         # parita': vince il DB
    (-2, True, "db"),        # DB piu' recente: vince il DB
    (+2, False, "db"),       # senza odds_ts_ms la riga del canale non sposta niente
])
def test_5_vince_la_riga_piu_fresca(canale, delta_canale, odds_ts, attesa):
    db_finto = FakeDB(params={"stake": 10})
    t_db = NOW
    db_finto.scan_rows = [_riga(payload(), t_db)]
    _spingi(_riga(payload(u35=(1.47, 1.48, 30.0, 25.0)),
                  t_db + timedelta(seconds=delta_canale), odds_ts=odds_ts))
    righe, fonte = S._righe_del_feed(db_finto, {"feed_cache_s": 0.0},
                                     t_db.timestamp() + 3)
    lay = righe[0]["payload"]["ou"][0]["selections"][0]["lay"]
    assert fonte == attesa
    assert lay == (1.48 if attesa == "canale" else 1.52)


def test_5b_il_canale_non_aggiunge_partite(canale):
    db_finto = FakeDB(params={"stake": 10})
    db_finto.scan_rows = [_riga(payload(), NOW)]
    altra = _riga(payload(), NOW + timedelta(seconds=2))
    altra["event_id"] = "E2"
    _spingi(altra)
    righe, _ = S._righe_del_feed(db_finto, {"feed_cache_s": 0.0}, NOW.timestamp() + 3)
    assert [r["event_id"] for r in righe] == ["E1"]


# ================================================================ contorno
def test_riallineamento_uguale_a_quello_di_safe():
    from Betfair.safe_strategy import bot_service as B
    assert S._RISINC_FEED_S == B._RISINC_DB_S


def test_azzeramenti_dimenticano_il_client(canale):
    assert S._CANALE_FEED["avviato"] is True
    S.svuota_le_cache()
    assert S._CANALE_FEED == {"client": None, "cache": None, "avviato": False,
                              "fonte": "db", "dal_canale": 0}
    assert S.avvia_client_scan() is True
    assert "_CANALE_FEED" in S.azzera_cache_di_processo()
    assert S._CANALE_FEED["avviato"] is False
    # a interruttore spento l'elenco dell'azzeramento resta quello di prima
    assert "_CANALE_FEED" not in S.azzera_cache_di_processo()


def test_la_sveglia_resta_quella_di_prima(canale):
    """Il client delle righe non porta la sveglia: e' ``MIKE_SVEGLIA_CANALE``."""
    client = S._CANALE_FEED["client"]
    assert client.evento is None and client.interessa is None


# ============================== (F5xF6, 23/09) fusione righe + sveglia sul 47336
# Con MIKE_SVEGLIA_CANALE ANCHE acceso, avvia_client_scan() diventa l'UNICO
# client verso il canale 47336 (regola dell'utente: una fonte, un client):
# porta le righe in cache come sempre E alza _SVEGLIA con lo STESSO filtro
# (_evento_seguito) e gli STESSI contatori di AscoltoScan. _avvia_sveglia()
# allora non apre il suo client separato: lo si dimostra sostituendo
# AscoltoScan con un finto che si conterebbe se venisse istanziato.
class _AscoltoFinto:
    """Sostituisce ``_SV.AscoltoScan``: se ``_avvia_sveglia()`` lo istanzia
    (caso NON fuso) il test lo scopre in ``creati``, senza aprire un socket."""

    creati: List["_AscoltoFinto"] = []

    def __init__(self, sveglia: Any, interessa: Any,
                topic: Any = (), nome: str = "mike") -> None:
        self.sveglia = sveglia
        self.interessa = interessa
        self.topic = topic
        self.nome = nome
        self.url = "ws://finto"
        type(self).creati.append(self)

    def avvia(self) -> bool:
        return True


@pytest.fixture
def _ascolto_finto(monkeypatch):
    monkeypatch.setattr(S._SV, "AscoltoScan", _AscoltoFinto)
    _AscoltoFinto.creati = []
    yield _AscoltoFinto
    _AscoltoFinto.creati = []


@pytest.fixture
def canale_e_sveglia(monkeypatch, _ascolto_finto):
    """Entrambi gli interruttori accesi: il caso della fusione."""
    monkeypatch.setenv(ENV, "1")
    monkeypatch.setenv(ENV_SVEGLIA, "1")
    monkeypatch.setattr(CS.ClientScan, "avvia", lambda self: None)
    S.azzera_canale_scan()
    S._SVEGLIA.azzera()
    S._ASCOLTO_SCAN = None
    S._avvia_sveglia()
    assert S.avvia_client_scan() is True
    yield S._CANALE_FEED
    S.azzera_canale_scan()
    S._SVEGLIA.azzera()
    S._ASCOLTO_SCAN = None


def test_un_solo_client_quando_entrambi_accesi(canale_e_sveglia, _ascolto_finto):
    """(1) del brief: entrambi accesi -> un solo client, non due."""
    assert S._ASCOLTO_SCAN is None, "un secondo client su 47336: vietato"
    assert _ascolto_finto.creati == [], (
        "AscoltoScan e' stato istanziato: due client sullo stesso canale 47336")
    client = S._CANALE_FEED["client"]
    assert client.evento is not None
    assert client.interessa is S._evento_seguito


def test_fuso_sveglia_su_seguita_non_su_altra_righe_in_cache(canale_e_sveglia):
    """(1) del brief: sveglia SOLO sulla partita seguita, righe di entrambe
    in cache."""
    S._CACHE_EVENTI.clear()
    S._CACHE_EVENTI["E1"] = {}      # E1 e' la partita che Mike segue
    quando = NOW

    altra = _riga(payload(), quando)
    altra["event_id"] = "E2"        # non seguita
    assert _spingi(altra)
    stats = S._SVEGLIA.statistiche()
    assert stats["sveglie"] == 0, "una riga non seguita ha svegliato Mike"
    assert S._CANALE_FEED["cache"].riga("E2") is not None, "riga non entrata in cache"

    seguita = _riga(payload(), quando + timedelta(seconds=1))  # event_id "E1"
    assert _spingi(seguita)
    stats = S._SVEGLIA.statistiche()
    assert stats["sveglie"] == 1 and stats["da_scan"] == 1
    assert S._CANALE_FEED["cache"].riga("E1") is not None
    assert S._CANALE_FEED["client"].svegliate == 1

    stato = S.statistiche_sveglia()
    assert stato is not None and stato["sveglie"] == 1
    assert stato["canale"]["svegliate"] == 1


def test_dormi_o_sveglia_usa_attendi_nel_caso_fuso(monkeypatch, canale_e_sveglia):
    """Falsificazione 'sveglia persa': senza il fixup di ``_dormi_o_sveglia``
    (che guardava solo ``_ASCOLTO_SCAN``) questo test va rosso, perche' il
    caso fuso lascia ``_ASCOLTO_SCAN`` a ``None``."""
    chiamate: List[str] = []
    monkeypatch.setattr(S._SVEGLIA, "attendi",
                        lambda *a, **k: chiamate.append("attendi") or "cadenza")
    monkeypatch.setattr(S.time, "sleep", lambda s: chiamate.append("sleep"))
    S._dormi_o_sveglia(0.01, {})
    assert chiamate == ["attendi"], "il ciclo fuso non si sveglia piu': dorme e basta"


def test_solo_sveglia_apre_ascolto_scan_come_prima(monkeypatch, _ascolto_finto):
    """(2) del brief: solo MIKE_SVEGLIA_CANALE -> come oggi (AscoltoScan)."""
    monkeypatch.delenv(ENV, raising=False)
    monkeypatch.setenv(ENV_SVEGLIA, "1")
    S.azzera_canale_scan()
    S._ASCOLTO_SCAN = None
    try:
        S._avvia_sveglia()
        assert isinstance(S._ASCOLTO_SCAN, _AscoltoFinto)
        assert _ascolto_finto.creati == [S._ASCOLTO_SCAN]
        assert S.avvia_client_scan() is False
        assert S._CANALE_FEED["client"] is None
    finally:
        S._ASCOLTO_SCAN = None
        S.azzera_canale_scan()


def test_entrambi_spenti_nessun_client(monkeypatch, _ascolto_finto):
    """(2) del brief: entrambi spenti -> nessun client, nessuna sveglia."""
    monkeypatch.delenv(ENV, raising=False)
    monkeypatch.delenv(ENV_SVEGLIA, raising=False)
    S.azzera_canale_scan()
    S._ASCOLTO_SCAN = None
    S._avvia_sveglia()
    assert S._ASCOLTO_SCAN is None
    assert _ascolto_finto.creati == []
    assert S.avvia_client_scan() is False
    assert S._CANALE_FEED["client"] is None


def test_azzera_canale_scan_toglie_anche_la_sveglia_fusa(canale_e_sveglia):
    """(3) del brief: l'azzeramento copre il nuovo stato fuso."""
    assert S._client_scan_alza_sveglia() is True
    S.azzera_canale_scan()
    assert S._client_scan_alza_sveglia() is False
    assert S.statistiche_sveglia() is None


def test_svuota_le_cache_toglie_anche_la_sveglia_fusa(canale_e_sveglia):
    """(3) del brief: idem passando da ``svuota_le_cache`` (usato dai test e
    dal riallineamento)."""
    assert S._client_scan_alza_sveglia() is True
    S.svuota_le_cache()
    assert S._client_scan_alza_sveglia() is False
