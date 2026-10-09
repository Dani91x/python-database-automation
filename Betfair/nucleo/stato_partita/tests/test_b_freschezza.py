"""W1-B - le tre eta' (``freschezza.py``) contro il codice di oggi.

Arbitri: ``scan_feed.row_age_sec`` (:440), ``ScanFeedScoreProvider.score_age_sec``
(:506) e ``ScanRowCache.scanner_age_sec`` (:324), sulle classi VERE con il
``fetch`` iniettabile che esse stesse dichiarano (``ScanRowCache(fetch=...)``).

Falsificazioni della scheda B par. 5 coperte qui:
  (1) ``Eta.riga_s`` sempre 0       -> ``test_feed_stantio_ha_l_eta_vera`` rosso
  (2) ritardo IPS tolto             -> ``test_punteggio_s_e_score_age_sec`` rosso
  (4) dato assente letto come fresco -> ``test_dato_assente_non_e_zero`` rosso
(la (3), lo scanner vivo, e' in ``test_b_adattatori.py``: la regola e' del runner).
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Any, Dict, List, Optional

import pytest

from Betfair.nucleo.stato_partita import freschezza as F
from Betfair.stream.scores import scan_feed as SF
from Betfair.stream.scores.betfair_inplay import BetfairInPlayProvider

T0 = 1_782_837_600.0          # 30/06/2026 16:40:00 UTC (registrazione 35760084)


def _iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).isoformat()


def _riga(eta_s: float, adesso: float = T0) -> Dict[str, Any]:
    return {"event_id": "35760084", "sport": "calcio", "updated_at": _iso(adesso - eta_s),
            "payload": {"minute": 38, "score_raw": {"timeElapsed": 38}}}


def _provider(righe: List[Dict[str, Any]], stato: Optional[Dict[str, Any]] = None) -> SF.ScanFeedScoreProvider:
    cache = SF.ScanRowCache(ttl_sec=0.0, fetch=lambda ids: list(righe),
                            fetch_status=lambda: stato)
    # il diretto non viene mai chiamato da ``score_age_sec``: nessun client
    return SF.ScanFeedScoreProvider(BetfairInPlayProvider(None), cache=cache)


ETA = [0.0, 0.4, 1.0, 2.5, 14.999, 15.0, 15.001, 29.0, 30.0, 31.0, 179.0, 180.0, 181.0, 3600.0]


@pytest.mark.parametrize("eta_s", ETA)
def test_riga_s_e_row_age_sec(eta_s: float) -> None:
    riga = _riga(eta_s)
    assert F.eta_riga_s(riga, T0) == SF.row_age_sec(riga, T0)
    assert F.eta_riga_s(riga, T0) == pytest.approx(eta_s, abs=1e-6)


@pytest.mark.parametrize("eta_s", ETA)
def test_punteggio_s_e_score_age_sec(eta_s: float, monkeypatch: pytest.MonkeyPatch) -> None:
    """``eta.punteggio_s`` = ``score_age_sec`` dello stesso istante (orologio di
    ``scan_feed`` fermato a ``T0``: ``row_age_sec`` legge ``time.time()``)."""
    riga = _riga(eta_s)
    monkeypatch.setattr(time, "time", lambda: T0)
    vecchio = _provider([riga]).score_age_sec("35760084")
    nuovo = F.eta_punteggio_s(riga, T0)
    assert nuovo == vecchio
    assert nuovo == pytest.approx(eta_s + 3.0, abs=1e-6)
    assert F.calcola_eta(riga, T0).punteggio_s == vecchio


def test_punteggio_s_senza_riga_e_none_come_oggi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "time", lambda: T0)
    assert _provider([]).score_age_sec("35760084") is None
    assert F.eta_punteggio_s(None, T0) is None
    assert F.calcola_eta(None, T0) == F.ETA_ASSENTE


@pytest.mark.parametrize("eta_stato", [0.0, 5.0, 30.0, 31.0, 600.0])
def test_scanner_s_e_scanner_age_sec(eta_stato: float, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "time", lambda: T0)
    stato = {"id": "scanner", "payload": {}, "updated_at": _iso(T0 - eta_stato)}
    vecchio = _provider([], stato)._cache.scanner_age_sec()
    assert F.eta_scanner_da_stato_s(stato, T0) == vecchio == pytest.approx(eta_stato, abs=1e-6)


def test_feed_stantio_ha_l_eta_vera() -> None:
    """Falsificazione (1): una riga ferma da 200 s ha ``riga_s`` 200, oltre il
    tetto di 180 s di ``fresh_payload``; con ``riga_s`` sempre 0 il feed
    stantio sembrerebbe fresco."""
    riga = _riga(200.0)
    eta = F.calcola_eta(riga, T0, scanner_s=5.0)
    assert eta.riga_s == pytest.approx(200.0, abs=1e-6)
    assert eta.riga_s > SF.HARD_MAX_AGE_SEC
    assert SF.fresh_payload(riga, SF.DEFAULT_MAX_AGE_SEC, T0, scanner_age_sec=eta.scanner_s) is None


def test_dato_assente_non_e_zero() -> None:
    """Falsificazione (4) sul comparto B: una riga senza ``updated_at`` (o
    illeggibile) ha eta' None, MAI 0 ("fresca"). La regola di Omega
    ``_is_fresh(None) = True`` (``omega_service.py:62-65``) resta nel file di
    Omega (decisione dell'utente B dec. 2, U-08): qui la si documenta."""
    for riga in ({"payload": {}}, {"updated_at": None}, {"updated_at": "ieri"}):
        eta = F.calcola_eta(riga, T0)
        assert eta.riga_s is None and eta.punteggio_s is None
    from Betfair.omega.omega_service import _is_fresh

    assert _is_fresh(None, dt.datetime.fromtimestamp(T0, tz=dt.timezone.utc)) is True


def test_ritardo_ips_letto_da_scan_feed() -> None:
    assert F.ritardo_ips_s() == SF.IPS_SCORE_LAG_SEC == 3.0


def test_istante_del_sidecar_passa_da_row_age_sec() -> None:
    ts_ms = 1_782_837_947_138
    riga = F.riga_da_istante_ms(ts_ms)
    assert SF.row_age_sec(riga, ts_ms / 1000.0 + 2.0) == pytest.approx(2.0, abs=1e-6)
    assert F.riga_da_istante_ms(None) is None
