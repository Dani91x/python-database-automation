"""canale.py - la riga dello scanner dal canale locale 47336 (comparto B).

``FonteCanale`` (fonte ``ips_scanner``, trasporto ``canale``) legge le righe
che lo scanner spinge sul canale (topic ``scan_calcio``/``scan_tennis``) dal
client di oggi (``safe_strategy/canale_scan.ClientScan`` con la sua
``CacheScan``), SENZA nessuna SELECT: e' il "niente SELECT" del contratto.

  riga           ``lettore.cache.riga(event_id)`` (copia, come la da' la cache)
  scanner_s      ``lettore.eta_stato_s()``: battito ``scanner_stato`` su QUESTO
                 client; None se mai arrivato o client scollegato
  stato_scanner  ``lettore.stato_payload`` (porta il blocco ``flusso``)

La fonte e' ``ips_scanner``: il dato e' dell'IPS letto dallo scanner, il canale
e' solo il trasporto. Il canale NON aggiunge partite e NON decide quale riga
vince sul DB (``canale_scan.piu_recente``, ``scan_feed._fondi_canale``): chi
vuole la fusione usa ``adattatori/ips.FonteIpsScanner`` con
``PUNTEGGI_CANALE`` acceso. Questo adattatore serve ai processi lettori che
stanno solo sul canale. Il client si avvia e si ferma FUORI di qui (e' di chi
lo possiede): nessun thread aperto da questo modulo.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional, Sequence

from Betfair.nucleo.comuni import Sport
from Betfair.nucleo.stato_partita.adattatori.lettura import lettura

logger = logging.getLogger(__name__)


class FonteCanale:
    """Righe e battito dal client del canale dello scanner."""

    nome = "canale"

    def __init__(self, lettore: Any, sport: Sport = "calcio") -> None:
        self.lettore = lettore
        self.sport: Sport = sport

    def _scanner_s(self) -> Optional[float]:
        try:
            eta = self.lettore.eta_stato_s()
        except Exception as ex:  # noqa: BLE001 - battito ignoto = None, mai zero
            logger.debug("[stato-partita] eta_stato_s KO: %s", str(ex)[:120])
            return None
        return None if eta is None else float(eta)

    def leggi(self, event_ids: Sequence[str]) -> Mapping[str, Mapping[str, Any]]:
        scanner_s = self._scanner_s()
        stato = getattr(self.lettore, "stato_payload", None)
        stato = stato if isinstance(stato, dict) else None
        out: Dict[str, Mapping[str, Any]] = {}
        for eid in (str(e) for e in event_ids):
            riga = self.lettore.cache.riga(eid)
            if isinstance(riga, dict):
                out[eid] = lettura(fonte="ips_scanner", trasporto="canale", sport=self.sport,
                                   riga=riga, scanner_s=scanner_s, stato_scanner=stato)
        return out
