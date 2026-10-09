"""ips_tennis.py - la fonte IPS del tennis (comparto B, ondata 1).

``FonteIpsTennisRunner`` riproduce la strada del punteggio di
``score_and_now_worker`` del runner tennis
(``Betfair/stream/tennis_live/tennis_runner.py:1631-1653``):
  1. lo stato grezzo dal feed dello scanner se ``fresh_payload`` lo dice
     affidabile (stessa regola del calcio, ``adattatori/ips.FonteIpsRunner``);
  2. altrimenti ``trading.in_play_service.get_scores`` DIRETTO, con l'id
     numerico se e' fatto di sole cifre, ``lightweight=True``;
  3. un errore della chiamata: nessun dato per quell'evento (il worker di oggi
     lascia ``ts=None``), registrato nel log col motivo.
Restituisce la LISTA di record (chiave ``grezzi``): il parser di oggi
(``parse_tennis_scores``) la legge com'e', scegliendo il record dell'evento.

La fonte e' dichiarata per evento: ``ips_scanner`` (feed) o ``ips_diretto``.
Nessuna regola nuova, nessuna rete all'import, nessun thread.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional, Sequence

from Betfair.nucleo.stato_partita.adattatori.ips import FonteIpsRunner, _trasporto
from Betfair.nucleo.stato_partita.adattatori.lettura import lettura

logger = logging.getLogger(__name__)


class _SenzaDiretto:
    """Segnaposto: il ramo diretto del tennis non passa da ``get_score``."""

    @staticmethod
    def get_score(event_id: str) -> None:  # pragma: no cover - mai chiamato
        raise RuntimeError("ramo diretto del tennis: usare trading.in_play_service")


class FonteIpsTennisRunner:
    """Feed fresco dello scanner, altrimenti ``get_scores`` diretto (tennis)."""

    nome = "ips_tennis_runner"

    def __init__(self, trading: Any, *, max_age_sec: Optional[float] = None,
                 cache: Optional[Any] = None) -> None:
        self.trading = trading
        # la regola del feed e' quella del calcio (stessa ``ScanFeedScoreProvider``)
        self._feed = FonteIpsRunner(_SenzaDiretto(), max_age_sec=max_age_sec, cache=cache)
        self.dal_feed = 0
        self.diretti = 0
        self.errori = 0

    def _diretto(self, event_id: str) -> Any:
        return self.trading.in_play_service.get_scores(
            event_ids=[int(event_id)] if str(event_id).isdigit() else [event_id],
            lightweight=True,
        )

    def leggi_uno(self, event_id: str) -> Optional[Dict[str, Any]]:
        eid = str(event_id)
        try:
            grezzo, riga, scanner_s = self._feed.grezzo_dal_feed(eid)
            if grezzo is not None:
                self.dal_feed += 1
                return lettura(fonte="ips_scanner", trasporto=_trasporto(self._feed.cache),
                               sport="tennis", riga=riga, grezzi=[grezzo], scanner_s=scanner_s)
            self.diretti += 1
            grezzi = self._diretto(eid)
        except Exception as ex:  # noqa: BLE001 - il feed non rompe mai chi lo legge
            self.errori += 1
            logger.debug("[stato-partita] punteggio tennis KO %s: %s", eid, str(ex)[:120])
            return None
        return lettura(fonte="ips_diretto", trasporto="http", sport="tennis",
                       grezzi=list(grezzi) if isinstance(grezzi, list) else None,
                       scanner_s=scanner_s)

    def leggi(self, event_ids: Sequence[str]) -> Mapping[str, Mapping[str, Any]]:
        out: Dict[str, Mapping[str, Any]] = {}
        for eid in event_ids:
            let = self.leggi_uno(str(eid))
            if let is not None:
                out[str(eid)] = let
        return out
