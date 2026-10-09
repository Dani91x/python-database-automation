"""lettura.py - la busta comune che ogni adattatore restituisce (comparto B).

``FonteStato.leggi(event_ids)`` (``contratto.py``) torna
``{event_id: Mapping}``: questo modulo fissa le CHIAVI di quel Mapping, uguali
per tutte le fonti, cosi' il servizio non deve sapere da dove arriva il dato:

  fonte          ``FonteStatoPartita``: da DOVE viene davvero il dato
                 (``ips_scanner`` / ``ips_diretto`` / ``api_football`` /
                 ``registrazione``). Oggi ``ScoreSnapshot.source`` dice
                 "betfair" sia per la riga dello scanner sia per la chiamata
                 diretta (scheda B par. 3.7): qui no.
  trasporto      come e' arrivato: ``db`` (SELECT di ``safe_strategy_scan``),
                 ``canale`` (47336), ``http`` (chiamata diretta), ``file``
                 (sidecar della registrazione), ``memoria`` (banco in memoria)
  sport          ``calcio`` | ``tennis``
  riga           la riga dello scanner (``event_id``, ``sport``, ``payload``,
                 ``updated_at``) o None
  grezzo         lo stato grezzo del calcio (stato IPS o entry API-Football) o None
  grezzi         la LISTA di record IPS del tennis (``parse_tennis_scores``) o None
  scanner_s      eta' del battito dello scanner (s) o None
  stato_scanner  il payload dello stato dello scanner (blocco ``flusso``) o None
  istante_ms     istante del dato quando lo dichiara la fonte (sidecar) o None
  origine        ``ips`` | ``api_football``: il fornitore a monte

Solo dati: nessuna logica, nessun import di codice di oggi.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from Betfair.nucleo.comuni import Sport
from Betfair.nucleo.stato_partita.contratto import FonteStatoPartita

CHIAVI = ("fonte", "trasporto", "sport", "riga", "grezzo", "grezzi", "scanner_s",
          "stato_scanner", "istante_ms", "origine")


def lettura(*, fonte: FonteStatoPartita, trasporto: str, sport: Sport,
            riga: Optional[Mapping[str, Any]] = None,
            grezzo: Optional[Mapping[str, Any]] = None,
            grezzi: Optional[Sequence[Mapping[str, Any]]] = None,
            scanner_s: Optional[float] = None,
            stato_scanner: Optional[Mapping[str, Any]] = None,
            istante_ms: Optional[int] = None,
            origine: str = "ips") -> Dict[str, Any]:
    """La busta, sempre con TUTTE le chiavi (assente = None, mai mancante)."""
    return {
        "fonte": fonte, "trasporto": trasporto, "sport": sport, "riga": riga,
        "grezzo": grezzo, "grezzi": list(grezzi) if grezzi is not None else None,
        "scanner_s": scanner_s, "stato_scanner": stato_scanner,
        "istante_ms": istante_ms, "origine": origine,
    }
