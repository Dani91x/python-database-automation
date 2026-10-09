"""W1-G2 - cache degli algoritmi del cloud (tappa T7) contro le funzioni di OGGI, che sono l'arbitro.

Arbitri importati (mai copiati): ``Betfair/omega/omega_db.py`` (``ht_ft_transitions``,
``minute_transitions``), ``Betfair/omega/omega_service.py`` (``_empirical_table``, ``_minute_table``:
le cache dei bot con la scadenza di 6 h), ``Betfair/mike/db.py`` (``fixture_id_for_event``,
``fixture_lambdas``, ``fixture_analysis``, ``ht_ft_rows``), ``Betfair/mike/dossier.py``
(``build_prematch``, ``get_empirical``: la cache di Mike senza scadenza),
``Betfair/stream/db.get_fixture_prematch_lambdas``, ``omega_empirical.minute_bucket``.

Il cloud e' un PostgREST finto DIETRO il client supabase VERO (``httpx.MockTransport``), con la
semantica delle RPC di ``migrations/omega_models_v4.sql:50-104`` (righe globali league_id=0 + righe
della lega) e il ``built_at`` del pg_cron delle 04:00 UTC. Nessuna rete, nessun DB vero.
"""
from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs

import httpx
import pytest
import supabase
from supabase import ClientOptions

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

import db_client  # noqa: E402
from Betfair.mike import db as mike_db  # noqa: E402
from Betfair.mike import dossier  # noqa: E402
from Betfair.nucleo.dati import cache_cloud as K  # noqa: E402
from Betfair.nucleo.dati.cloud import ClienteCloud  # noqa: E402
from Betfair.omega import omega_db, omega_empirical, omega_service  # noqa: E402
from Betfair.stream import db as stream_db  # noqa: E402

CORPO_57014 = {"code": "57014", "details": None, "hint": None,
               "message": "canceling statement due to statement timeout"}
CORPO_PGRST202 = {"code": "PGRST202", "details": None, "hint": None,
                  "message": "Could not find the function in the schema cache"}
HTML_520 = b"<!DOCTYPE html><html><head><title>supabase.co | 520: Web server is returning an unknown error</title>"
PARAMS = {"model_empirical": "veto"}
LEGHE = (39, 135, 61)


def _istante(testo: str) -> float:
    return datetime.fromisoformat(testo).replace(tzinfo=timezone.utc).timestamp()


# ---------------------------------------------------------------------------
# Il cloud finto: tabelle empiriche per costruzione notturna + tabelle del dossier
# ---------------------------------------------------------------------------
def _punteggi() -> List[str]:
    return [f"{h}-{a}" for h in range(4) for a in range(4)]


def costruisci_notte(seme: int, built_at: str) -> Dict[str, Any]:
    """Una ricostruzione del pg_cron: righe {league_id, ht, ft, n} e {league_id, bucket, score,
    target, result, n} per il globale (0) e le leghe, con i tipi delle migrazioni."""
    rnd = random.Random(seme)
    ht, minuti = [], []
    for lega in (0,) + LEGHE:
        for h in _punteggi()[:8]:
            for f in _punteggi():
                if rnd.random() < 0.5:
                    ht.append({"league_id": lega, "ht": h, "ft": f, "n": rnd.randint(1, 900 if lega == 0 else 60)})
        for target, bucket in (("ft", K.BUCKET_FT), ("ht", K.BUCKET_HT)):
            for b in bucket:
                for s in _punteggi()[:5]:
                    for r in _punteggi()[:6]:
                        if rnd.random() < 0.3:
                            minuti.append({"league_id": lega, "bucket": b, "score": s, "target": target,
                                           "result": r, "n": rnd.randint(1, 500)})
    return {"ht": ht, "minuti": minuti, "built_at": built_at}


TACTICAL_OK = {"lambda_home": 1.45, "lambda_away": 1.05}
ANALISI_1 = {"inputs": {"dc_rho": -0.09, "lambda_home": 1.3, "lambda_away": 1.1},
             "markets_calibrated": {"over_3_5": {"True": 0.21}}, "markets": {"over_3_5": {"True": 0.25}}}
ANALISI_2 = {"inputs": {"lambda_home": 1.2, "lambda_away": 0.9}, "markets": {"over_3_5": {"True": 0.31}}}
FIXTURE = {
    101: {"fixture_id": 101, "league_id": 39, "tactical_engine_json": TACTICAL_OK, "db_json_analisi": ANALISI_1,
          "home_team_id": 40, "away_team_id": 50},
    102: {"fixture_id": 102, "league_id": 135, "tactical_engine_json": json.dumps(TACTICAL_OK),
          "db_json_analisi": ANALISI_2, "home_team_id": None, "away_team_id": 7},
    103: {"fixture_id": 103, "league_id": 61, "tactical_engine_json": None, "db_json_analisi": ANALISI_1,
          "home_team_id": 1, "away_team_id": 2},
    104: {"fixture_id": 104, "league_id": 39, "tactical_engine_json": {"lambda_home": 0, "lambda_away": 1.2},
          "db_json_analisi": {"inputs": {"lambda_home": -1, "lambda_away": 1}}, "home_team_id": 3, "away_team_id": 4},
    106: {"fixture_id": 106, "league_id": None, "tactical_engine_json": {"lambda_home": "x", "lambda_away": 1.0},
          "db_json_analisi": json.dumps({"inputs": {"lambda_home": 2.0, "lambda_away": 0.7, "dc_rho": -0.2}}),
          "home_team_id": 9, "away_team_id": 8},
    107: {"fixture_id": 107, "league_id": 39, "tactical_engine_json": "{non json", "db_json_analisi": None,
          "home_team_id": None, "away_team_id": None},
    108: {"fixture_id": 108, "league_id": 135, "tactical_engine_json": {"lambda_home": 1.7},
          "db_json_analisi": {"inputs": "non un dict", "markets": {"over_3_5": {"False": 0.6}}},
          "home_team_id": 11, "away_team_id": 12},
}
LIVE_FOLLOW = {"ev1": 101, "ev2": None, "ev4": 104, "ev5": 105, "ev7": "abc", "ev8": 108}
OMEGA_EVENTS = {"ev2": 102, "ev3": 103, "ev6": None, "ev7": 107, "ev9": 106}
EVENTI = ("ev1", "ev2", "ev3", "ev4", "ev5", "ev6", "ev7", "ev8", "ev9", "ev10")


class CloudFinto:
    """PostgREST finto con la semantica delle RPC v4 e i filtri eq/in/limit/order/select."""

    def __init__(self) -> None:
        self.notte = costruisci_notte(1, "2026-10-09T04:00:00.170000+00:00")
        self.richieste: List[Tuple[str, str, str, Any]] = []
        self.rifiuta_tutto = False
        self.errori: Dict[Tuple[str, str], Any] = {}          # (metodo, rotta) -> azione fissa
        self.errore_minuti: Set[Tuple[int, str]] = set()      # (bucket, target) che rispondono 404
        self.risposta_rpc: Dict[str, Any] = {}                # rpc -> corpo forzato
        self.tabelle: Dict[str, List[Dict[str, Any]]] = {
            "live_follow": [{"event_id": e, "fixture_id": f, "status": "STREAMING"} for e, f in LIVE_FOLLOW.items()],
            "omega_events": [{"event_id": e, "fixture_id": f, "home": "A"} for e, f in OMEGA_EVENTS.items()],
            "fixture_predictions": list(FIXTURE.values()),
        }

    def trasporto(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.gestisci)

    def conta(self) -> int:
        return len(self.richieste)

    def gestisci(self, req: httpx.Request) -> httpx.Response:
        rotta = req.url.path.replace("/rest/v1", "")
        corpo = json.loads(req.content) if req.content else None
        self.richieste.append((req.method, rotta, req.url.query.decode(), corpo))
        if self.rifiuta_tutto:
            raise httpx.ConnectError("[Errno 111] Connection refused", request=req)
        if (req.method, rotta) in self.errori:
            return self.errori[(req.method, rotta)](req)
        if rotta.startswith("/rpc/"):
            return self._rpc(rotta[5:], corpo or {})
        return self._select(rotta.strip("/"), {k: v[0] for k, v in parse_qs(req.url.query.decode()).items()})

    def _rpc(self, nome: str, a: Dict[str, Any]) -> httpx.Response:
        if nome in self.risposta_rpc:
            return httpx.Response(200, content=json.dumps(self.risposta_rpc[nome]).encode(),
                                  headers={"content-type": "application/json"})
        lega = a.get("p_league_id")
        dentro = lambda r: r["league_id"] == 0 or (lega is not None and lega != 0 and r["league_id"] == lega)  # noqa: E731
        if nome == "get_omega_ht_ft":
            return httpx.Response(200, json=[r for r in self.notte["ht"] if dentro(r)])
        if nome == "get_omega_minute_ft":
            if (a["p_bucket"], a["p_target"]) in self.errore_minuti:
                return httpx.Response(404, json=CORPO_PGRST202)
            return httpx.Response(200, json=[r for r in self.notte["minuti"] if dentro(r)
                                             and r["bucket"] == a["p_bucket"] and r["target"] == a["p_target"]])
        return httpx.Response(404, json=CORPO_PGRST202)

    def _select(self, tabella: str, q: Dict[str, str]) -> httpx.Response:
        if tabella == "omega_ht_ft_transitions":
            return httpx.Response(200, json=[{"built_at": self.notte["built_at"]}])
        righe = list(self.tabelle.get(tabella, []))
        for col, cond in q.items():
            if col in ("select", "limit", "order"):
                continue
            op, _, val = cond.partition(".")
            if op == "eq":
                righe = [r for r in righe if str(r.get(col)) == val]
            elif op == "in":
                valori = {v.strip('"') for v in val.strip("()").split(",")}
                righe = [r for r in righe if str(r.get(col)) in valori]
        if "limit" in q:
            righe = righe[:int(q["limit"])]
        colonne = q.get("select", "*")
        if colonne != "*":
            righe = [{c: r.get(c) for c in colonne.split(",")} for r in righe]
        return httpx.Response(200, json=righe)


@pytest.fixture
def cloud(monkeypatch):
    srv = CloudFinto()

    def crea(_url: str, _key: str, options: Any = None) -> Any:
        return supabase.create_client("https://abc.supabase.co", "x" * 40,
                                      options=ClientOptions(httpx_client=httpx.Client(transport=srv.trasporto())))
    monkeypatch.setattr(db_client, "create_client", crea)
    monkeypatch.setattr(db_client._time, "sleep", lambda _s: None)
    db_client._TLS.client = None            # ripristinato da Betfair/conftest.py
    db_client._STATO_RETE.update({"guasti_di_fila": 0})
    monkeypatch.setattr(omega_service, "_EMPIRICAL_CACHE", {})
    monkeypatch.setattr(omega_service, "_MINUTE_CACHE", {})
    monkeypatch.setattr(dossier, "_EMPIRICAL_CACHE", {})
    monkeypatch.setattr(dossier, "_EMPIRICAL_FAILED", {})
    yield srv
    db_client._STATO_RETE.update({"guasti_di_fila": 0})


def _cliente() -> ClienteCloud:
    return ClienteCloud("bot", dormi=lambda _s: None, casuale=lambda: 0.5)


def _replica(**kw: Any) -> K.ReplicaEmpirica:
    return K.ReplicaEmpirica(K.SorgenteOmega(_cliente()), **kw)


def _tabella(t: Any) -> Any:
    return None if t is None else {k: v for k, v in vars(t).items()}


# ---------------------------------------------------------------------------
# 1. Costanti di oggi
# ---------------------------------------------------------------------------
def test_bucket_e_scadenze_sono_quelli_dei_bot():
    assert set(K.BUCKET_FT) == {omega_empirical.minute_bucket(m, half=False) for m in range(0, 200)}
    assert set(K.BUCKET_HT) == {omega_empirical.minute_bucket(m, half=True) for m in range(0, 200)}
    assert K.SCADENZA_OMEGA_S == omega_service.EMPIRICAL_CACHE_TTL_S == 6 * 3600
    assert K.SCADENZA_MIKE_S is None and dossier._EMPIRICAL_RETRY_S == 600.0


# ---------------------------------------------------------------------------
# 2. Le RPC: stessi argomenti e stessi ritorni di omega_db
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("lega", [None, 0, 39, 135, 999])
def test_sorgente_uguale_a_omega_db_righe_e_argomenti(cloud, lega):
    s = K.SorgenteOmega(_cliente())
    assert s.ht_ft(lega) == omega_db.ht_ft_transitions(lega)
    for target, bucket in (("ft", K.BUCKET_FT), ("ht", K.BUCKET_HT)):
        for b in bucket:
            assert s.minuti(lega, b, target) == omega_db.minute_transitions(lega, b, target), (lega, b, target)
    corpi = [r[3] for r in cloud.richieste]
    assert corpi[0::2] == corpi[1::2]                                      # argomenti identici, coppia per coppia


@pytest.mark.parametrize("caso", ["lista_vuota", "null", "oggetto", "404", "57014", "520_persistente"])
def test_sorgente_uguale_a_omega_db_sui_casi_limite(cloud, caso):
    rotte = ("/rpc/get_omega_ht_ft", "/rpc/get_omega_minute_ft")
    for nome in ("get_omega_ht_ft", "get_omega_minute_ft"):
        if caso in ("lista_vuota", "null", "oggetto"):
            cloud.risposta_rpc[nome] = {"lista_vuota": [], "null": None, "oggetto": {"league_id": 0}}[caso]
    azione = {"404": lambda _r: httpx.Response(404, json=CORPO_PGRST202),
              "57014": lambda _r: httpx.Response(500, json=CORPO_57014),
              "520_persistente": lambda _r: httpx.Response(520, content=HTML_520,
                                                           headers={"content-type": "text/html"})}.get(caso)
    if azione:
        for r in rotte:
            cloud.errori[("POST", r)] = azione
    s = K.SorgenteOmega(_cliente())
    for lega in (None, 39):
        db_client._STATO_RETE["guasti_di_fila"] = 0
        atteso = omega_db.ht_ft_transitions(lega)
        assert s.ht_ft(lega) == atteso
        assert s.minuti(lega, 45, "ft") == omega_db.minute_transitions(lega, 45, "ft")
        assert atteso == ([] if caso in ("lista_vuota", "null", "oggetto") else None)


# ---------------------------------------------------------------------------
# 3. La replica: righe identiche alla RPC, zero rete nel ciclo
# ---------------------------------------------------------------------------
def test_replica_uguale_alla_rpc_per_ogni_lega_e_bucket(cloud):
    r = _replica(ripiego_sincrono=False)
    for lega in (None, 0) + LEGHE:
        esito = r.prefetch_lega(lega)
        assert esito == K.EsitoPrefetch(1 + len(K.BUCKET_FT) + len(K.BUCKET_HT), 0)
    prima = cloud.conta()
    risposte = {}
    for lega in (None, 0) + LEGHE:
        risposte[("ht", lega)] = r.ht_ft_transitions(lega)
        assert r.ht_ft_rows(lega) == risposte[("ht", lega)]
        for target, bucket in (("ft", K.BUCKET_FT), ("ht", K.BUCKET_HT)):
            for b in bucket:
                risposte[(lega, b, target)] = r.minute_transitions(lega, b, target)
    assert cloud.conta() == prima                                         # zero richieste dal ciclo
    for chiave, righe in risposte.items():
        if chiave[0] == "ht":
            assert righe == omega_db.ht_ft_transitions(chiave[1]), chiave
        else:
            assert righe == omega_db.minute_transitions(*chiave), chiave
    righe = r.ht_ft_transitions(39)
    righe[0]["n"] = -1                                                    # la copia non tocca la memoria
    assert r.ht_ft_transitions(39)[0]["n"] != -1


def test_bot_identici_con_la_replica_al_posto_della_rpc(cloud, monkeypatch):
    """omega_service._empirical_table/_minute_table e dossier.get_empirical, con la replica come
    ``db``, costruiscono le STESSE tabelle che con omega_db/mike.db (due processi: due cache)."""
    r = _replica(ripiego_sincrono=False)
    for lega in LEGHE + (None,):
        r.prefetch_lega(lega)
    cache_vecchio: Dict[str, Dict] = {"e": {}, "m": {}}
    cache_nuovo: Dict[str, Dict] = {"e": {}, "m": {}}

    def con(cache: Dict[str, Dict]) -> None:
        monkeypatch.setattr(omega_service, "_EMPIRICAL_CACHE", cache["e"])
        monkeypatch.setattr(omega_service, "_MINUTE_CACHE", cache["m"])

    for lega in LEGHE + (None,):
        con(cache_vecchio)
        v_e = _tabella(omega_service._empirical_table(omega_db, lega, PARAMS))
        v_m = [_tabella(omega_service._minute_table(omega_db, lega, m, h, PARAMS)) for m in (0, 33, 47, 88) for h in (False, True)]
        con(cache_nuovo)
        n_e = _tabella(omega_service._empirical_table(r, lega, PARAMS))
        n_m = [_tabella(omega_service._minute_table(r, lega, m, h, PARAMS)) for m in (0, 33, 47, 88) for h in (False, True)]
        assert v_e == n_e and v_e is not None
        assert v_m == n_m
    # Mike: una cache per processo (``dossier._EMPIRICAL_CACHE``), quindi due giri separati
    monkeypatch.setattr(dossier, "_EMPIRICAL_CACHE", {})
    vecchio = {lega: _tabella(dossier.get_empirical(lega, mike_db, now_ts=1.0)) for lega in LEGHE}
    monkeypatch.setattr(dossier, "_EMPIRICAL_CACHE", {})
    nuovo = {lega: _tabella(dossier.get_empirical(lega, r, now_ts=1.0)) for lega in LEGHE}
    assert vecchio == nuovo and all(v is not None for v in vecchio.values())


def test_rilettura_dopo_la_ricostruzione_delle_04_utc_e_scadenze_di_oggi(cloud, monkeypatch):
    """Il caso del rischio di T7: prefetch alle 03:00, pg_cron alle 04:00, sorveglianza alle 05:00.
    Omega (6 h) rilegge alle 09:01 e deve vedere la notte NUOVA come con la RPC; Mike (mai) resta
    sulla vecchia come oggi. Controllo negativo: una replica che non rilegge dopo built_at da'
    righe diverse dalla RPC (e' la falsificazione «cache senza scadenza»)."""
    adesso = [_istante("2026-10-10T03:00:00")]
    monkeypatch.setattr(omega_service, "time", SimpleNamespace(time=lambda: adesso[0]))
    r = _replica(ripiego_sincrono=False)
    ferma = _replica(ripiego_sincrono=False)                 # non chiama mai controlla_ricostruzione
    assert r.controlla_ricostruzione() is False              # prima lettura di built_at: nessuna "ricostruzione"
    for x in (r, ferma):
        x.prefetch_lega(39)
    cache = {"v": ({}, {}), "n": ({}, {})}

    def tabelle(db: Any, quale: str) -> Tuple[Any, Any]:
        monkeypatch.setattr(omega_service, "_EMPIRICAL_CACHE", cache[quale][0])
        monkeypatch.setattr(omega_service, "_MINUTE_CACHE", cache[quale][1])
        return (_tabella(omega_service._empirical_table(db, 39, PARAMS)),
                _tabella(omega_service._minute_table(db, 39, 62, False, PARAMS)))

    notte_a = tabelle(omega_db, "v")
    assert tabelle(r, "n") == notte_a
    mike_a = {"v": _tabella(dossier.get_empirical(39, mike_db, now_ts=adesso[0]))}
    monkeypatch.setattr(dossier, "_EMPIRICAL_CACHE", {})
    mike_a["n"] = _tabella(dossier.get_empirical(39, r, now_ts=adesso[0]))
    cache_mike_n = dict(dossier._EMPIRICAL_CACHE)
    assert mike_a["v"] == mike_a["n"]

    cloud.notte = costruisci_notte(2, "2026-10-10T04:00:00.170000+00:00")   # il pg_cron delle 04:00
    adesso[0] = _istante("2026-10-10T05:00:00")
    assert r.controlla_ricostruzione() is True
    assert r.statistiche()["ricostruzioni"] == 1
    assert tabelle(omega_db, "v") == tabelle(r, "n") == notte_a          # Omega: dentro le 6 h, vecchia
    adesso[0] = _istante("2026-10-10T09:01:00")                          # 6 h e 1 minuto dopo
    notte_b = tabelle(omega_db, "v")
    assert notte_b != notte_a
    assert tabelle(r, "n") == notte_b                                    # la replica e' la notte NUOVA
    cache["f"] = ({}, {})
    monkeypatch.setattr(omega_service, "_EMPIRICAL_CACHE", cache["f"][0])
    monkeypatch.setattr(omega_service, "_MINUTE_CACHE", cache["f"][1])
    assert _tabella(omega_service._empirical_table(ferma, 39, PARAMS)) != notte_b[0]   # controllo negativo
    # Mike: la cache del processo non scade mai (U-53): vecchia notte con la RPC e con la replica
    assert _tabella(dossier.get_empirical(39, mike_db, now_ts=adesso[0])) == mike_a["v"]
    monkeypatch.setattr(dossier, "_EMPIRICAL_CACHE", cache_mike_n)
    assert _tabella(dossier.get_empirical(39, r, now_ts=adesso[0])) == mike_a["n"] == mike_a["v"]


def test_rete_che_rifiuta_tutto_la_replica_e_il_dossier_rispondono_uguali(cloud):
    r = _replica(ripiego_sincrono=True)
    d = K.DossierPrematch(_cliente(), replica=r, ripiego=mike_db)
    for lega in LEGHE:
        r.prefetch_lega(lega)
    d.precarica(EVENTI)
    prima_ht = {lega: r.ht_ft_transitions(lega) for lega in LEGHE}
    prima_dossier = {ev: dossier.build_prematch(ev, d) for ev in EVENTI}
    cloud.rifiuta_tutto = True
    n = cloud.conta()
    assert {lega: r.ht_ft_transitions(lega) for lega in LEGHE} == prima_ht
    assert {ev: dossier.build_prematch(ev, d) for ev in EVENTI} == prima_dossier
    assert cloud.conta() == n                                              # nessuna richiesta nel ciclo


def test_mancato_prefetch_ripiego_o_none_e_errori_mai_in_cache(cloud):
    cloud.errore_minuti.add((45, "ft"))
    r = _replica(ripiego_sincrono=False)
    esito = r.prefetch_lega(39)
    assert esito.errori == 1
    assert r.minute_transitions(39, 45, "ft") is None                     # errore: non in cache, None come oggi
    assert r.ht_ft_transitions(999) is None                               # lega mai preparata
    assert r._coda.qsize() == 1                                           # ... e il prefetch e' chiesto
    cloud.errore_minuti.clear()
    con_ripiego = _replica(ripiego_sincrono=True)
    assert con_ripiego.ht_ft_transitions(999) == omega_db.ht_ft_transitions(999)
    assert con_ripiego.statistiche()["ripieghi"] == 1
    n = cloud.conta()
    con_ripiego.ht_ft_transitions(999)                                    # ora e' in memoria
    assert cloud.conta() == n


def test_thread_di_prefetch_e_sorveglianza_avvia_e_ferma(cloud):
    r = _replica(ripiego_sincrono=False, intervallo_sorveglianza_s=0.05)
    r.richiedi_prefetch(39)
    r.richiedi_prefetch(None)
    r.avvia()
    try:
        assert r.vivo()
        fine = time.monotonic() + 10
        while r.statistiche()["chiavi"] < 2 * 28 and time.monotonic() < fine:
            time.sleep(0.02)
        assert r.statistiche()["chiavi"] == 2 * 28
        cloud.notte = costruisci_notte(3, "2026-10-11T04:00:00.170000+00:00")
        while r.statistiche()["ricostruzioni"] < 1 and time.monotonic() < fine:
            time.sleep(0.02)
        assert r.statistiche()["built_at"] == "2026-10-11T04:00:00.170000+00:00"
    finally:
        r.ferma()
    assert not r.vivo()
    assert r.ht_ft_transitions(39) == omega_db.ht_ft_transitions(39)


# ---------------------------------------------------------------------------
# 4. Il dossier di Mike
# ---------------------------------------------------------------------------
RIGHE_LAMBDA = list(FIXTURE.values()) + [
    {"fixture_id": 1, "league_id": 2, "tactical_engine_json": {"lambda_home": "1.5", "lambda_away": "0.5"},
     "db_json_analisi": None, "home_team_id": 1, "away_team_id": 2},
    {"fixture_id": 2, "league_id": 2, "tactical_engine_json": {"lambda_home": None, "lambda_away": 2},
     "db_json_analisi": {"inputs": {"lambda_home": 0.01, "lambda_away": 3}}},
    {"fixture_id": 3, "league_id": 2, "tactical_engine_json": [], "db_json_analisi": "[]"},
    {"fixture_id": 4, "tactical_engine_json": {"lambda_home": True, "lambda_away": 1.0}},
    {"fixture_id": 5, "league_id": 7, "tactical_engine_json": "null", "db_json_analisi": {"inputs": None}},
]


@pytest.mark.parametrize("riga", RIGHE_LAMBDA, ids=lambda r: str(r["fixture_id"]))
def test_lambdas_da_riga_uguale_a_get_fixture_prematch_lambdas(cloud, riga):
    cloud.tabelle["fixture_predictions"] = [riga]
    for con_squadre in (True, False):
        atteso = stream_db.get_fixture_prematch_lambdas(riga["fixture_id"], con_squadre=con_squadre)
        assert K.lambdas_da_riga(riga, con_squadre=con_squadre) == atteso, (riga, con_squadre)


def test_dossier_uguale_a_mike_db_per_ogni_evento(cloud):
    d = K.DossierPrematch(_cliente(), ripiego=None)
    assert d.precarica(EVENTI) == len(EVENTI)
    n = cloud.conta()
    for ev in EVENTI:
        fid = mike_db.fixture_id_for_event(ev)
        assert d.fixture_id_for_event(ev) == fid, ev
        assert d.fixture_lambdas(fid) == mike_db.fixture_lambdas(fid), ev
        assert d.fixture_analysis(fid) == mike_db.fixture_analysis(fid), ev
    assert d.statistiche()["ripieghi"] == 0
    n_vecchio = cloud.conta() - n
    for ev in EVENTI:                                                     # le chiavi del contratto T7
        v, nn = dossier.build_prematch(ev, mike_db), dossier.build_prematch(ev, d)
        assert v == nn, ev
        assert {k: v[k] for k in ("lambda_home", "lambda_away", "rho", "p4_pre", "p_under35_cal")} == \
               {k: nn[k] for k in ("lambda_home", "lambda_away", "rho", "p4_pre", "p_under35_cal")}
    # il caso pieno c'e' davvero (non solo None == None)
    assert dossier.build_prematch("ev1", d)["p4_pre"] is not None
    assert dossier.build_prematch("ev1", d)["p_under35_fonte"] == "calibrated"
    assert dossier.build_prematch("ev2", d)["p_under35_fonte"] == "raw"
    assert n_vecchio >= 2 * len(EVENTI)                                   # oggi: >= 2 letture a evento
    assert d.statistiche()["letture_rete"] == 3                           # domani: 3 letture per tutti


def test_dossier_errori_mai_in_memoria_e_scadenza_oraria(cloud):
    cloud.errori[("GET", "/omega_events")] = lambda _r: httpx.Response(503, json={
        "code": "PGRST002", "details": None, "hint": None, "message": "schema cache"})
    adesso = [1000.0]
    d = K.DossierPrematch(_cliente(), ripiego=mike_db, orologio=lambda: adesso[0])
    d.precarica(EVENTI)
    st = d.statistiche()
    assert st["errori"] == 1
    # solo gli eventi risolti da live_follow entrano; gli altri vanno al ripiego (= oggi)
    del cloud.errori[("GET", "/omega_events")]
    for ev in EVENTI:
        assert d.fixture_id_for_event(ev) == mike_db.fixture_id_for_event(ev), ev
    assert d.statistiche()["ripieghi"] >= 1
    adesso[0] += K.SCADENZA_DOSSIER_S                                    # un'ora dopo: scaduto
    prima = d.statistiche()["ripieghi"]
    assert d.fixture_id_for_event("ev1") == 101
    assert d.statistiche()["ripieghi"] == prima + 1
