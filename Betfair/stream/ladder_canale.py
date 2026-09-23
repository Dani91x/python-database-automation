"""ladder_canale.py - cadenza del ladder: CANALE LOCALE al tick, DB a 2 s (23/09).

Regola dell'utente: tutto cio' che il trader vede passa dal canale al ms, come
Bet Angel/Fairbot (refresh 20-200 ms). Fino al 23/09 il ladder_worker girava ogni
``LADDER_PUBLISH_SEC`` (2 s) e pubblicava sul canale solo a quel ritmo: il canale
precedeva il DB ma era lento quanto lui.

Qui vive SOLO la logica pura (nessuna rete, nessun thread) condivisa dal
ladder_worker del calcio (``runner.py``) e da quello del tennis
(``tennis_live/tennis_runner.py``). Lo stesso thread del worker di prima fa due
cose a due cadenze diverse:

  * CANALE: ogni ``canale_ms`` (default 200 ms; 0 = a ogni book nuovo visto dal
    worker, che allora gira ogni ``INTERVALLO_MIN_SEC``) si pubblica il ladder dei
    mercati la cui firma e' cambiata dall'ultima pubblicazione SUL CANALE. Senza
    client collegati il giro del canale non si fa proprio.
  * DB: ogni ``db_sec`` (``LADDER_PUBLISH_SEC`` = 2 s, invariato) si scrive la
    riga dei mercati la cui firma e' cambiata dall'ultima scrittura SUL DB
    (write-on-change di sempre). Le due firme sono SEPARATE: una pubblicazione
    sul canale non marca mai il DB come aggiornato.

Il book e' gia' in RAM di flumine (cache del recorder / della capture): nessuna
chiamata Betfair in piu'. Un book invariato (stesso oggetto, stesso stato) non
viene nemmeno ricostruito: la cache degli oggetti rende il giro a vuoto O(mercati)
con un confronto di identita'.

``updated_ms`` del payload = istante del book di flumine (``pt`` =
``market_book.publish_time_epoch``, ms) se presente, altrimenti l'ora locale;
reso STRETTAMENTE crescente per mercato (la pagina scarta una riga con
``updated_ms`` non piu' fresco: ``piuFresca`` in frontend/src/lib/localTransport.ts),
cosi' un cambio di solo stato (es. CLOSED marcato in place, stesso ``pt``) non
viene scartato. Canale e DB portano lo STESSO payload per la stessa firma.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

# Cadenza minima del worker: sotto 20 ms non si scende mai (Bet Angel/Fairbot
# stanno fra 20 e 200 ms). Vale anche per canale_ms = 0 ("a ogni cambiamento"):
# due book dello stesso mercato arrivati a meno di 20 ms l'uno dall'altro si
# fondono nell'ultimo (stato completo: vince il piu' recente, nessuno perso a
# meta').
INTERVALLO_MIN_SEC = 0.02
# tolleranza sul confronto dei tempi (float, sleep di Windows)
_EPS = 1e-3


def _adesso() -> float:
    """Orologio monotono del worker (sostituibile nei test)."""
    return time.monotonic()


def _ora_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def canale_ms_env(nome: str, default: int = 200) -> int:
    """Parsing robusto della cadenza del canale (ms) da env: vuoto, illeggibile o
    negativo -> ``default``; 0 e' valido ("a ogni cambiamento")."""
    s = (os.getenv(nome) or "").strip()
    if not s:
        return default
    try:
        v = int(float(s))
    except ValueError:
        return default
    return v if v >= 0 else default


def updated_ms_del_book(book: Dict[str, Any]) -> int:
    """Istante del book di flumine (``pt``, ms epoch) se valido, altrimenti adesso."""
    pt = book.get("pt") if isinstance(book, dict) else None
    if isinstance(pt, (int, float)) and not isinstance(pt, bool) and pt > 0:
        return int(pt)
    return _ora_ms()


class StatoLadder:
    """Stato per processo del ladder_worker: cadenze, cache dei payload, firme canale.

    Non tocca la firma del DB: quella resta nella sessione del runner
    (``_last_ladder_sig`` calcio, ``_ladder_sig`` tennis), come prima.
    """

    def __init__(self, db_sec: float, canale_ms: int,
                 orologio: Optional[Callable[[], float]] = None) -> None:
        self.db_sec = float(db_sec) if db_sec and db_sec > 0 else 1.0
        self.canale_ms = int(canale_ms) if canale_ms and canale_ms > 0 else 0
        self.canale_sec = self.canale_ms / 1000.0
        self._orologio = orologio
        self._ultimo_db: Optional[float] = None
        self._ultimo_canale: Optional[float] = None
        self._canale_prima = False
        # market_id -> (book, status, firma, payload)
        self._cache: Dict[str, Tuple[Any, Any, str, Dict[str, Any]]] = {}
        # market_id -> firma dell'ultima pubblicazione sul CANALE
        self._sig_canale: Dict[str, str] = {}

    # ------------------------------------------------------------ cadenze
    def intervallo_worker(self) -> float:
        """Cadenza del BackgroundWorker: la piu' fitta fra canale e DB, mai < 20 ms."""
        return min(self.db_sec, max(self.canale_sec, INTERVALLO_MIN_SEC))

    def _ora(self) -> float:
        return self._orologio() if self._orologio is not None else _adesso()

    def giro(self, canale_attivo: bool) -> Tuple[bool, bool]:
        """(fare_canale, fare_db) per questo giro del worker; aggiorna i tempi.

        Un canale che torna ad avere client (da 0 a >0) riparte da zero: al primo
        giro si ripubblica ogni mercato (il client nuovo non aspetta un cambio).
        """
        ora = self._ora()
        if canale_attivo and not self._canale_prima:
            self._sig_canale.clear()
        self._canale_prima = bool(canale_attivo)
        fare_db = self._ultimo_db is None or ora - self._ultimo_db >= self.db_sec - _EPS
        fare_canale = bool(canale_attivo) and (
            self._ultimo_canale is None or ora - self._ultimo_canale >= self.canale_sec - _EPS)
        if fare_db:
            self._ultimo_db = ora
        if fare_canale:
            self._ultimo_canale = ora
        return fare_canale, fare_db

    # ------------------------------------------------------------ versione del book
    def versione(self, market_id: str, book: Dict[str, Any],
                 costruisci: Callable[[], Tuple[Dict[str, Any], str]]) -> Tuple[str, Dict[str, Any]]:
        """(firma, payload) del book corrente del mercato.

        ``costruisci()`` -> (payload, firma) si chiama SOLO se il book e' un oggetto
        nuovo o ha cambiato stato (il recorder sostituisce il dict a ogni
        aggiornamento; ``process_closed_market`` cambia lo stato in place). Un book
        senza ``pt`` (finti dei test storici) si ricostruisce sempre: la firma
        completa resta l'unico giudice.
        """
        status = book.get("status")
        voce = self._cache.get(market_id)
        if (voce is not None and voce[0] is book and voce[1] == status
                and book.get("pt") is not None):
            return voce[2], voce[3]
        payload, sig = costruisci()
        if voce is not None and voce[2] == sig:
            payload = voce[3]  # stesso contenuto: stessa versione (stesso updated_ms)
        else:
            prec = voce[3].get("updated_ms") if voce is not None else None
            if isinstance(prec, int) and payload.get("updated_ms", 0) <= prec:
                payload["updated_ms"] = prec + 1
        self._cache[market_id] = (book, status, sig, payload)
        return sig, payload

    # ------------------------------------------------------------ firme del canale
    def canale_cambiato(self, market_id: str, sig: str) -> bool:
        return self._sig_canale.get(market_id) != sig

    def segna_canale(self, market_id: str, sig: str) -> None:
        self._sig_canale[market_id] = sig


def stato_della_sessione(session: Any, db_sec: float, canale_ms: int) -> StatoLadder:
    """Lo StatoLadder appeso alla sessione (creato al primo giro)."""
    st = getattr(session, "_stato_ladder", None)
    if st is None:
        st = StatoLadder(db_sec, canale_ms)
        session._stato_ladder = st
    return st
