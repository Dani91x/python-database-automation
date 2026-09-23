"""23/09 - M-1 (revisore B): Mike, rilettura del feed e copertura del canale.

Difetto: ``_righe_del_feed`` rileggeva il DB al passo lento (10 s) appena la
memoria del canale aveva UNA riga fresca qualsiasi, anche di TENNIS
(``ClientScan`` riceve entrambi i topic): una partita di calcio non arrivata
sul canale restava fino a 10 s invece di ``feed_cache_s``. E le righe del canale
valevano fino a 20 s (``FEED_FRESH_S``), Omega fino a 5 s.

Correzione: passo lento solo se OGNI partita della lista (righe del DB) ha una
riga fresca del canale che la copre (``odds_ts_ms`` numerico, recente almeno
quanto il DB), come Omega e ``ScanRowCache``; eta' massima delle righe del
canale ``CS.MAX_ETA_CONTESTO_S`` (5 s).

La sonda del revisore (``test_mike_ttl_allungato_da_righe_non_sue``, verde =
difetto) e' qui INVERTITA. Finti: ``CacheScan`` VERA, righe con le chiavi di
``safe_strategy_scan`` (event_id, sport, payload con odds_ts_ms, updated_at),
DB con la firma di ``mike/db.fetch_scan_rows``.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from Betfair.mike import service as S
from Betfair.safe_strategy import canale_scan as CS


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _riga(eid: str, ts: float, sport: str = "calcio", odds: bool = True) -> dict:
    payload = {"inplay": True, "minute": 30}
    if odds:
        payload["odds_ts_ms"] = int(ts * 1000)
    return {"event_id": eid, "sport": sport, "payload": payload, "updated_at": _iso(ts)}


class _Db:
    def __init__(self, righe):
        self.righe = righe
        self.letture = 0

    def fetch_scan_rows(self):
        self.letture += 1
        return [dict(r) for r in self.righe]


@pytest.fixture
def canale(monkeypatch):
    monkeypatch.setenv("MIKE_LEGGE_CANALE", "1")
    S.svuota_le_cache()
    S.azzera_canale_scan()
    cache = CS.CacheScan()
    S._CANALE_FEED.update({"cache": cache, "avviato": True, "client": None})
    yield cache
    S.azzera_canale_scan()
    S.svuota_le_cache()


P = {"feed_cache_s": 4}


def test_righe_solo_tennis_non_allungano_la_rilettura_del_calcio(canale):
    now = time.time()
    canale.aggiorna(_riga("TENNIS1", now, sport="tennis"))
    db = _Db([_riga("CALCIO1", now)])
    S._righe_del_feed(db, P, now)
    assert db.letture == 1
    S._righe_del_feed(db, P, now + 4.5)            # oltre feed_cache_s: si rilegge
    assert db.letture == 2


def test_tutte_le_partite_coperte_passo_lento(canale):
    now = time.time()
    db = _Db([_riga("C1", now), _riga("C2", now)])
    S._righe_del_feed(db, P, now)
    assert db.letture == 1
    for i, t in enumerate((now + 2.0, now + 4.5, now + 8.0)):
        canale.aggiorna(_riga("C1", t))
        canale.aggiorna(_riga("C2", t))
        S._righe_del_feed(db, P, t + 0.5)
    assert db.letture == 1                         # coperte: niente DB entro 10 s
    canale.aggiorna(_riga("C1", now + 10.0))
    canale.aggiorna(_riga("C2", now + 10.0))
    S._righe_del_feed(db, P, now + 10.5)           # riallineamento a 10 s
    assert db.letture == 2


def test_una_partita_non_coperta_cadenza_di_oggi(canale):
    now = time.time()
    db = _Db([_riga("C1", now), _riga("C2", now)])
    S._righe_del_feed(db, P, now)
    canale.aggiorna(_riga("C1", now + 4.0))        # C2 non arriva dal canale
    S._righe_del_feed(db, P, now + 4.5)
    assert db.letture == 2


def test_riga_del_canale_senza_odds_ts_non_copre(canale):
    now = time.time()
    db = _Db([_riga("C1", now)])
    S._righe_del_feed(db, P, now)
    canale.aggiorna(_riga("C1", now + 4.0, odds=False))
    S._righe_del_feed(db, P, now + 4.5)
    assert db.letture == 2


def test_riga_del_canale_piu_vecchia_di_5s_non_entra(canale):
    now = time.time()
    db = _Db([_riga("C1", now - 30.0)])
    canale.aggiorna(_riga("C1", now - 6.0))        # piu' recente del DB, ma di 6 s fa
    righe, fonte = S._righe_del_feed(db, {"feed_cache_s": 0.0}, now)
    assert fonte == "db"
    assert righe[0]["updated_at"] == _iso(now - 30.0)
    canale.aggiorna(_riga("C1", now - 4.0))        # 4 s: entra
    righe, fonte = S._righe_del_feed(db, {"feed_cache_s": 0.0}, now)
    assert fonte == "canale"


def test_lista_vuota_non_coperta(canale):
    now = time.time()
    canale.aggiorna(_riga("C1", now))
    db = _Db([])
    S._righe_del_feed(db, P, now)
    S._righe_del_feed(db, P, now + 4.5)
    assert db.letture == 2


def test_canale_copre_tutte_unita():
    now = time.time()
    db = [_riga("A", now), _riga("B", now)]
    assert S._canale_copre_tutte(db, {"A": _riga("A", now), "B": _riga("B", now + 1)})
    assert not S._canale_copre_tutte(db, {"A": _riga("A", now)})
    assert not S._canale_copre_tutte(db, {"A": _riga("A", now), "B": _riga("B", now - 1)})
    assert not S._canale_copre_tutte(None, {"A": _riga("A", now)})
