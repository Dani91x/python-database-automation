"""api_football.py - il ripiego esterno del calcio e il circuito (comparto B).

``FonteApiFootball`` (fonte ``api_football``)
  Il provider di oggi (``ApiFootballProvider``, ``scores/api_football.py:57``)
  dietro il contratto ``FonteStato``: stesso ``fixture_id``, stessa chiamata
  ``/fixtures?id=`` con i ritenti di ``api_client``, stesso log su
  ``api_call_log``. Senza ``fixture_id`` e' inerte (nessuna chiamata).

``FonteCircuitoCalcio``
  Il circuito primario/ripiego del runner calcio: UN ``ScorePoller`` di oggi
  (``scores/poller.py:24``) per evento, con primario la strada del runner
  (``adattatori/ips.FonteIpsRunner``) e ripiego API-Football. La politica e'
  quella di oggi, invariata (decisione U-10 non presa): dopo UN fallimento del
  primario si prova gia' il ripiego (``poller.py:81-82``), il circuito si apre
  dopo ``threshold`` fallimenti e ritenta il primario ogni
  ``retry_primary_sec``. Cambia solo che la fonte di ogni lettura dice la verita'
  (``ips_scanner`` / ``ips_diretto`` / ``api_football``).

Import innocuo: ``api_client`` legge ``.env`` all'import (``config.py``): si
importa solo quando si costruisce un provider vero (``provider_api_football``).
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from Betfair.nucleo.stato_partita.adattatori.ips import FonteIpsRunner, LogRaro
from Betfair.nucleo.stato_partita.adattatori.lettura import lettura
from Betfair.stream.scores.poller import ScorePoller

logger = logging.getLogger(__name__)


def provider_api_football(fixture_id: Optional[int]) -> Any:
    """L'``ApiFootballProvider`` di oggi (import al primo uso: legge ``.env``)."""
    from Betfair.stream.scores.api_football import ApiFootballProvider

    return ApiFootballProvider(fixture_id=fixture_id)


class FonteApiFootball:
    """Un provider API-Football (uno per evento, come nel runner)."""

    nome = "api_football"

    def __init__(self, provider: Any) -> None:
        self.provider = provider

    def leggi(self, event_ids: Sequence[str]) -> Mapping[str, Mapping[str, Any]]:
        out: Dict[str, Mapping[str, Any]] = {}
        for eid in event_ids:
            snap = self.provider.get_score(str(eid))
            if snap is not None:
                out[str(eid)] = lettura(fonte="api_football", trasporto="http", sport="calcio",
                                        grezzo=snap.payload, origine="api_football")
        return out


class _PrimarioComeProvider:
    """``FonteIpsRunner`` vista come ``ScoreProvider`` dal ``ScorePoller`` di oggi:
    ``get_score`` torna lo snapshot di ``parse_score_dict`` (come
    ``ScanFeedScoreProvider``) e ricorda la busta per l'evento."""

    name = "scan_feed"

    def __init__(self, fonte: FonteIpsRunner) -> None:
        self.fonte = fonte
        self.ultima: Dict[str, Dict[str, Any]] = {}

    def get_score(self, event_id: str) -> Any:
        from Betfair.stream.scores.betfair_inplay import parse_score_dict

        let = self.fonte.leggi_uno(str(event_id))
        if let is None:
            self.ultima.pop(str(event_id), None)
            return None
        self.ultima[str(event_id)] = let
        return parse_score_dict(str(event_id), dict(let["grezzo"]))

    def healthcheck(self) -> bool:
        return bool(getattr(self.fonte.diretto, "healthcheck", lambda: True)())


class FonteCircuitoCalcio:
    """Primario (feed o IPS diretto) con ripiego API-Football, per evento."""

    nome = "circuito_calcio"

    def __init__(self, primario: FonteIpsRunner,
                 ripiego_per_evento: Callable[[str], Any], *,
                 threshold: int = 3, retry_primary_sec: float = 120.0,
                 clock: Optional[Callable[[], float]] = None) -> None:
        self._primario = _PrimarioComeProvider(primario)
        self._ripiego_per_evento = ripiego_per_evento
        self._threshold = int(threshold)
        self._retry = float(retry_primary_sec)
        self._clock = clock
        self.pollers: Dict[str, ScorePoller] = {}
        self.log_raro = LogRaro()

    def poller(self, event_id: str) -> ScorePoller:
        eid = str(event_id)
        p = self.pollers.get(eid)
        if p is None:
            kw: Dict[str, Any] = {"threshold": self._threshold, "retry_primary_sec": self._retry}
            if self._clock is not None:
                kw["clock"] = self._clock
            p = ScorePoller(self._primario, self._ripiego_per_evento(eid), **kw)
            self.pollers[eid] = p
        return p

    def leggi(self, event_ids: Sequence[str]) -> Mapping[str, Mapping[str, Any]]:
        out: Dict[str, Mapping[str, Any]] = {}
        for eid in (str(e) for e in event_ids):
            poller = self.poller(eid)
            try:
                snap = poller.poll(eid)
            except Exception as ex:  # noqa: BLE001 - come ``score_worker``: si salta l'evento
                self.log_raro.avvisa(self.nome, eid, ex)
                continue
            if snap is None:
                continue
            if poller.current_source == self._primario.name and eid in self._primario.ultima:
                out[eid] = self._primario.ultima[eid]
            else:
                out[eid] = lettura(fonte="api_football", trasporto="http", sport="calcio",
                                   grezzo=snap.payload, origine="api_football")
        return out
