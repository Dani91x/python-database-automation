"""registrazione.py - la fonte del banco: i sidecar dei punteggi (comparto B).

``FonteRegistrazione`` (fonte ``registrazione``) legge il sidecar di una
registrazione con la funzione VERA del banco comune
(``banco_comune.carica_punteggi``, ``Betfair/stream/backtest/banco_comune.py:3040``):
``<id>.scores.jsonl`` (calcio, righe ``{"ts_ms", "payload"}``) o
``<id>.score.jsonl`` (tennis, righe ``{"t", "score"}``), ordinati per istante.
Restituisce, per l'istante di mercato in cui il banco si trova
(``posiziona``), l'ULTIMO record con ``ts_ms <= adesso - ritardo``: la stessa
regola di ``_replay_evento`` (``bisect_right`` su ``ts_ms`` meno
``ritardo_punteggi_s``, ``banco_comune.py:3235``). Il ritardo di produzione
dell'IPS e' gia' dentro ``ts_ms`` (istante di ricezione del runner): di serie
non se ne aggiunge un altro (docstring del banco, PSB par. 6.1).

Il record entra nello stato COME LO LEGGE IL BANCO: il grezzo va al parser IPS
(``parse_score_dict``), anche quando la riga del sidecar era un ripiego
API-Football (``origine`` lo dice: la riga ha ``fixture`` e ``goals``). E' la
lettura di oggi del banco; la divergenza con ``live_now`` (che per quelle righe
aveva il minuto di API-Football) e' nel referto.

File aperti SOLO in ``apri()``; nessun thread; nessuna rete.
"""
from __future__ import annotations

from bisect import bisect_right
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from Betfair.nucleo.comuni import Sport
from Betfair.nucleo.stato_partita.adattatori.lettura import lettura


def origine_record(record: Mapping[str, Any]) -> str:
    """``api_football`` se il record e' una entry di ``/fixtures`` (chiavi
    ``fixture`` e ``goals``), altrimenti ``ips``. Etichetta, non un valore."""
    return "api_football" if ("fixture" in record and "goals" in record) else "ips"


class FonteRegistrazione:
    """Il sidecar di UNA registrazione, scorso col tempo di mercato."""

    nome = "registrazione"

    def __init__(self, cartella: str, event_id: str, *, sport: Sport = "calcio",
                 ritardo_s: float = 0.0) -> None:
        self.cartella = str(cartella)
        self.event_id = str(event_id)
        self.sport: Sport = sport
        self.ritardo_s = float(ritardo_s)
        self.record: List[Tuple[int, Dict[str, Any]]] = []
        self._ts: List[int] = []
        self._adesso_ms: Optional[int] = None
        self.aperta = False

    def apri(self) -> int:
        """Carica il sidecar (``carica_punteggi`` del banco). Torna i record letti."""
        from Betfair.stream.backtest.banco_comune import carica_punteggi

        self.record = carica_punteggi(self.cartella, self.event_id, self.sport)
        self._ts = [t for t, _ in self.record]
        self.aperta = True
        return len(self.record)

    def chiudi(self) -> None:
        self.record = []
        self._ts = []
        self.aperta = False

    def posiziona(self, adesso_ms: int) -> None:
        """L'istante di mercato del banco (``publish_time`` del tick)."""
        self._adesso_ms = int(adesso_ms)

    def indice(self) -> int:
        """Quanti record sono gia' arrivati all'istante corrente."""
        if self._adesso_ms is None:
            return 0
        return bisect_right(self._ts, int(self._adesso_ms - self.ritardo_s * 1000.0))

    def leggi(self, event_ids: Sequence[str]) -> Mapping[str, Mapping[str, Any]]:
        if self.event_id not in {str(e) for e in event_ids}:
            return {}
        i = self.indice()
        if i <= 0:
            return {}
        ts_ms, rec = self.record[i - 1]
        if self.sport == "tennis":
            return {self.event_id: lettura(fonte="registrazione", trasporto="file", sport="tennis",
                                           grezzi=[rec], istante_ms=ts_ms)}
        return {self.event_id: lettura(fonte="registrazione", trasporto="file", sport="calcio",
                                       grezzo=rec, istante_ms=ts_ms, origine=origine_record(rec))}
