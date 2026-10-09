"""freschezza.py - SOLO le tre eta' dello stato partita (comparto B, ondata 1).

SCOPO
  Calcolare UNA volta le tre eta' che oggi si confondono (scheda B par. 3.2):
    riga_s       da quanto la riga del feed e' stata (ri)scritta
                 = ``scan_feed.row_age_sec`` (``Betfair/stream/scores/scan_feed.py:440``)
    punteggio_s  quanto e' vecchio davvero il punteggio = riga + ritardo IPS
                 = ``ScanFeedScoreProvider.score_age_sec`` (``scan_feed.py:506``,
                 ``IPS_SCORE_LAG_SEC`` = 3,0 s, ``:67``)
    scanner_s    eta' del battito dello scanner: dalla riga di stato
                 (``safe_strategy_status``, ``ScanRowCache.scanner_age_sec``
                 ``:324``) o dal canale (``ClientScan.eta_stato_s``)

COSA NON FA (contraddizione 4 di 04, decisione U-08)
  Nessuna SOGLIA: 15/20/25/45/90/120/180 s restano nei file di strategia di
  ogni bot (``mike/feed.py``, ``safe_strategy/exits.py``, ``omega_service.py``)
  e nella regola del runner (``scan_feed.fresh_payload``, riusata
  dall'adattatore ``adattatori/ips.py``). Qui si misura, non si giudica.

Dato assente non e' zero (PSB par. 6.2): una riga senza ``updated_at``
leggibile ha eta' None, mai 0.

Import innocuo: ``scan_feed`` (che tira dentro ``betfairlightweight``) si
importa al primo calcolo.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

from Betfair.nucleo.stato_partita.contratto import Eta


def _scan_feed() -> Any:
    from Betfair.stream.scores import scan_feed

    return scan_feed


def ritardo_ips_s() -> float:
    """Il ritardo noto dell'IPS sul campo, letto da ``scan_feed`` (mai copiato)."""
    return float(_scan_feed().IPS_SCORE_LAG_SEC)


def eta_riga_s(riga: Optional[Mapping[str, Any]], adesso_s: Optional[float] = None) -> Optional[float]:
    """Eta' della riga (``row_age_sec`` invariata); None = riga o istante assenti."""
    if not riga:
        return None
    return _scan_feed().row_age_sec(dict(riga), adesso_s)


def eta_punteggio_s(riga: Optional[Mapping[str, Any]], adesso_s: Optional[float] = None) -> Optional[float]:
    """Eta' ONESTA del punteggio: eta' della riga + ritardo IPS (``score_age_sec``).
    None se la riga non c'e' (dato dal diretto: oggi come ``score_age_sec``)."""
    eta = eta_riga_s(riga, adesso_s)
    return None if eta is None else eta + ritardo_ips_s()


def eta_scanner_da_stato_s(riga_stato: Optional[Mapping[str, Any]],
                           adesso_s: Optional[float] = None) -> Optional[float]:
    """Eta' del battito dello scanner dalla riga ``safe_strategy_status`` (stessa
    formula di ``ScanRowCache.scanner_age_sec`` sul ramo del database)."""
    return eta_riga_s(riga_stato, adesso_s)


def riga_da_istante_ms(ts_ms: Optional[int]) -> Optional[dict]:
    """Una riga ``{"updated_at": ISO}`` per un istante in ms (sidecar delle
    registrazioni), cosi' l'eta' passa da ``row_age_sec`` come quella vera."""
    if ts_ms is None:
        return None
    iso = datetime.fromtimestamp(int(ts_ms) / 1000.0, tz=timezone.utc).isoformat()
    return {"updated_at": iso}


def calcola_eta(riga: Optional[Mapping[str, Any]], adesso_s: Optional[float] = None, *,
                scanner_s: Optional[float] = None) -> Eta:
    """Le tre eta' insieme, allo stesso istante ``adesso_s`` (epoch s; None =
    orologio del PC, come oggi)."""
    return Eta(riga_s=eta_riga_s(riga, adesso_s),
               punteggio_s=eta_punteggio_s(riga, adesso_s),
               scanner_s=scanner_s)


#: eta' di nessuna riga (fonte diretta, ripiego esterno): tutto assente
ETA_ASSENTE = Eta(riga_s=None, punteggio_s=None, scanner_s=None)


def orologio_di_sistema() -> Callable[[], float]:
    """L'orologio di oggi (``time.time``), iniettabile nel servizio."""
    return time.time
