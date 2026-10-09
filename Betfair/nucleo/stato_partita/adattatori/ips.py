"""ips.py - le fonti IPS del calcio (comparto B, ondata 1).

Due adattatori ``FonteStato`` (``contratto.py``), entrambi sul codice di oggi:

``FonteIpsScanner``  (fonte ``ips_scanner``)
  Le righe dello scanner COME SONO, per chi applica da se' la propria regola di
  freschezza (Mike, Omega, Safe: soglie nei loro file, U-08). Legge con la
  cache di processo di oggi (``scan_feed.ScanRowCache.rows_for``: una SELECT
  per tutti gli eventi, fusione col canale se ``PUNTEGGI_CANALE`` e' acceso) e
  dichiara il trasporto vero (``db`` o ``canale``).

``FonteIpsRunner``  (fonte ``ips_scanner`` oppure ``ips_diretto``)
  La politica del runner calcio (``ScanFeedScoreProvider.get_score``,
  ``scan_feed.py:524``): la riga dello scanner se ``fresh_payload`` la dice
  affidabile (15 s, oppure scanner vivo entro 30 s, tetto 180 s) e porta lo
  ``score_raw``; altrimenti la chiamata IPS DIRETTA
  (``BetfairInPlayProvider.get_score``, ``betfair_inplay.py:164``). La regola
  e' ``scan_feed.fresh_payload`` importata; questo modulo la compone come
  ``ScanRowCache.payload_if_fresh`` (righe prima, battito dopo) e dice, per
  ogni evento, QUALE delle due strade ha dato il dato: oggi
  ``ScoreSnapshot.source`` dice "betfair" in entrambi i casi.

COSA NON FA: nessuna soglia nuova, nessun thread, nessuna rete all'import
(``scan_feed`` e ``betfair_inplay`` si importano al primo uso).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Mapping, Optional, Sequence

from Betfair.nucleo.comuni import Sport
from Betfair.nucleo.stato_partita.adattatori.lettura import lettura
from Betfair.stream.flusso_prezzi import Promemoria

logger = logging.getLogger(__name__)

#: al piu' una riga di log al minuto per partita su un errore di lettura
ERRORE_LETTURA_OGNI_S = 60.0


class LogRaro:
    """Una riga di log per partita al piu' ogni ``ogni_s`` (``flusso_prezzi.Promemoria``
    riusata), sull'orologio monotono: un errore che si ripete a ogni giro non
    allaga il log, e non resta muto."""

    def __init__(self, ogni_s: float = ERRORE_LETTURA_OGNI_S,
                 orologio: Any = time.monotonic) -> None:
        self._promemoria = Promemoria(ogni_s)
        self._orologio = orologio

    def avvisa(self, chi: str, event_id: str, ex: BaseException) -> bool:
        if not self._promemoria.dovuto(str(event_id), float(self._orologio())):
            return False
        logger.warning("[stato-partita] %s: lettura della partita %s KO: %s: %s", chi, event_id,
                       type(ex).__name__, str(ex)[:160])
        return True


def _scan_feed() -> Any:
    from Betfair.stream.scores import scan_feed

    return scan_feed


def _trasporto(cache: Any) -> str:
    """``canale`` se la cache di oggi sta leggendo (anche) dal canale 47336."""
    try:
        return "canale" if cache.canale_vivo() else "db"
    except Exception as ex:  # noqa: BLE001 - il trasporto e' un'etichetta, non un dato
        logger.debug("[stato-partita] canale_vivo KO: %s", str(ex)[:120])
        return "db"


class FonteIpsScanner:
    """Righe dello scanner senza filtro di freschezza (le eta' le calcola il servizio)."""

    nome = "ips_scanner"

    def __init__(self, cache: Optional[Any] = None, sport: Sport = "calcio") -> None:
        # ``cache``: una ``ScanRowCache`` (iniettabile nei test e nel banco);
        # None = la cache di processo di oggi (``scan_feed.shared_cache``)
        self._cache = cache
        self.sport: Sport = sport

    @property
    def cache(self) -> Any:
        if self._cache is None:
            self._cache = _scan_feed().shared_cache()
        return self._cache

    def leggi(self, event_ids: Sequence[str]) -> Mapping[str, Mapping[str, Any]]:
        ids = [str(e) for e in event_ids]
        if not ids:
            return {}
        cache = self.cache
        righe = cache.rows_for(ids)
        scanner_s = cache.scanner_age_sec()
        stato = cache.scanner_stato()
        trasporto = _trasporto(cache)
        return {
            eid: lettura(fonte="ips_scanner", trasporto=trasporto, sport=self.sport,
                         riga=righe[eid], scanner_s=scanner_s, stato_scanner=stato)
            for eid in ids if eid in righe
        }


class FonteIpsRunner:
    """La strada del runner calcio: feed fresco, altrimenti IPS diretto."""

    nome = "ips_runner"

    def __init__(self, diretto: Any, *, max_age_sec: Optional[float] = None,
                 cache: Optional[Any] = None) -> None:
        # ``diretto``: un ``BetfairInPlayProvider`` (o qualunque oggetto con
        # ``get_score(event_id) -> ScoreSnapshot | None``)
        self.diretto = diretto
        sf = _scan_feed()
        self.max_age_sec = float(sf.DEFAULT_MAX_AGE_SEC if max_age_sec is None else max_age_sec)
        self._cache = cache
        # contatori con lo stesso significato di ``feed_hits``/``direct_calls``
        self.dal_feed = 0
        self.diretti = 0
        self.errori = 0
        self.log_raro = LogRaro()

    @property
    def cache(self) -> Any:
        if self._cache is None:
            self._cache = _scan_feed().shared_cache()
        return self._cache

    def grezzo_dal_feed(self, event_id: str) -> "tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[float]]":
        """(score_raw, riga, eta' scanner) se la riga e' affidabile per
        ``fresh_payload``, altrimenti (None, riga, eta' scanner). Stesso ordine
        di ``ScanRowCache.payload_if_fresh``: prima le righe, poi il battito."""
        cache = self.cache
        riga = cache.rows_for([str(event_id)]).get(str(event_id))
        scanner_s = cache.scanner_age_sec()
        payload = _scan_feed().fresh_payload(riga, self.max_age_sec, scanner_age_sec=scanner_s)
        grezzo = payload.get("score_raw") if payload else None
        return (grezzo if isinstance(grezzo, dict) else None), riga, scanner_s

    def leggi_uno(self, event_id: str) -> Optional[Dict[str, Any]]:
        eid = str(event_id)
        grezzo, riga, scanner_s = self.grezzo_dal_feed(eid)
        if grezzo is not None:
            self.dal_feed += 1
            return lettura(fonte="ips_scanner", trasporto=_trasporto(self.cache), sport="calcio",
                           riga=riga, grezzo=grezzo, scanner_s=scanner_s)
        self.diretti += 1
        snap = self.diretto.get_score(eid)
        if snap is None:
            return None
        return lettura(fonte="ips_diretto", trasporto="http", sport="calcio",
                       grezzo=snap.payload, scanner_s=scanner_s)

    def leggi(self, event_ids: Sequence[str]) -> Mapping[str, Mapping[str, Any]]:
        """Una partita che solleva (riga, battito, chiamata diretta) non scarta le
        altre: come il ``continue`` di ``score_worker`` (``runner.py:351-353``)."""
        out: Dict[str, Mapping[str, Any]] = {}
        for eid in (str(e) for e in event_ids):
            try:
                let = self.leggi_uno(eid)
            except Exception as ex:  # noqa: BLE001 - una partita rotta non ferma le altre
                self.errori += 1
                self.log_raro.avvisa(self.nome, eid, ex)
                continue
            if let is not None:
                out[eid] = let
        return out
