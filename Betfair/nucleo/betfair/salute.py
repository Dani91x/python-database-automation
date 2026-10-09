"""Contatori in memoria della sessione e del REST di Betfair (comparto A, T5, W1-A1).

Scopo: dire in ogni momento, senza I/O, come sta la connessione REST di UN
processo: login (riusciti, falliti, frenati), keepAlive (riusciti, falliti),
relogin, esiti per metodo (ok, limite, sessione, rete, permanente), tentativi
ripetuti, attese sul tetto delle 3 concorrenti, latenza per metodo con p50/p99.

Entrate: le chiamate di ``sessione.py`` e ``rest.py`` (``login``, ``keepalive``,
``esito_rest``, ``attesa_tetto``...). Uscite: ``stato()`` (dict, mai il token) e,
se configurato, l'INOLTRO immediato a un oggetto con l'API del modulo Salute di
oggi (``conta(gruppo, chiave, n)`` e ``tratto(nome, ms)``: sia
``Betfair.monitor.registro.Registro`` sia il modulo ``Betfair.monitor.sonde``).

Compatibilita' col modulo Salute (``Betfair/monitor/``, NON modificato): le
latenze usano lo STESSO istogramma a secchi fissi (``registro.Istogramma``,
riusato, non copiato), quindi p50/p99 sono calcolati come nel referto di 24 h.
I gruppi inoltrati hanno nomi PROPRI (``betfair_sessione``, ``betfair_rest_esiti``,
tratti ``a1_rest_ms.<metodo>``) per non sommarsi a quelli che il gancio HTTP del
monitor conta gia' (``betfair_rest``, ``rest_ms.<metodo>``): vedi il referto,
"Aggancio proposto".

Cosa NON fa: non scrive su DB o file, non apre thread, non decide nulla.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Mapping, Optional

from Betfair.monitor.registro import Istogramma

logger = logging.getLogger(__name__)

#: tetto delle chiavi distinte (difesa contro metodi impazziti), come il monitor
MAX_CHIAVI = 200
ALTRO = "_altro"

#: nomi dei gruppi inoltrati al modulo Salute
GRUPPO_SESSIONE = "betfair_sessione"
GRUPPO_ESITI = "betfair_rest_esiti"
PREFISSO_TRATTO = "a1_rest_ms."
TRATTO_ATTESA_TETTO = "a1_attesa_tetto_ms"


class SaluteBetfair:
    """I contatori di sessione e REST di UN processo. Thread-safe.

    ``inoltra_a``: facoltativo, oggetto con ``conta(gruppo, chiave, n)`` e
    ``tratto(nome, ms)`` (il ``Registro`` o il modulo ``sonde`` del monitor). Un
    errore dell'inoltro si logga e non risale mai al chiamante.
    """

    def __init__(self, inoltra_a: Optional[Any] = None) -> None:
        self._lock = threading.Lock()
        self._inoltra = inoltra_a
        self._sessione: Dict[str, int] = {
            "login": 0, "login_falliti": 0, "login_frenati": 0, "ban_login": 0,
            "keepalive": 0, "keepalive_falliti": 0, "relogin": 0,
        }
        self._esiti: Dict[str, Dict[str, int]] = {}
        self._ritenti: Dict[str, int] = {}
        self._latenze: Dict[str, Istogramma] = {}
        self._attesa_tetto = Istogramma()
        self._ultimo_errore: Optional[str] = None

    # ---------------------------------------------------------------- sessione
    def evento_sessione(self, chiave: str) -> None:
        """Una voce di sessione: login, login_falliti, login_frenati, ban_login,
        keepalive, keepalive_falliti, relogin."""
        with self._lock:
            if chiave not in self._sessione:
                raise KeyError(f"voce di sessione sconosciuta: {chiave}")
            self._sessione[chiave] += 1
        self._inoltra_conta(GRUPPO_SESSIONE, chiave)

    # ---------------------------------------------------------------- REST
    def esito_rest(self, metodo: str, classe: str, ms: Optional[float] = None,
                   errore: Optional[str] = None) -> None:
        """Esito di UN tentativo HTTP: ``classe`` = ok | limite | sessione | rete |
        permanente | frenato; ``ms`` = durata del tentativo; ``errore`` = descrizione
        SENZA token (la fa chi chiama)."""
        with self._lock:
            per_metodo = self._esiti.get(metodo)
            if per_metodo is None:
                if len(self._esiti) >= MAX_CHIAVI:
                    metodo = ALTRO
                per_metodo = self._esiti.setdefault(metodo, {})
            per_metodo[classe] = per_metodo.get(classe, 0) + 1
            if ms is not None:
                h = self._latenze.get(metodo)
                if h is None and len(self._latenze) < MAX_CHIAVI:
                    h = self._latenze[metodo] = Istogramma()
                if h is not None:
                    h.aggiungi(float(ms))
            if errore:
                self._ultimo_errore = f"{metodo}: {errore}"
        self._inoltra_conta(GRUPPO_ESITI, f"{metodo} {classe}")
        if ms is not None:
            self._inoltra_tratto(PREFISSO_TRATTO + metodo, float(ms))

    def ritento(self, metodo: str) -> None:
        """Un tentativo RIPETUTO di una lettura (mai di una mutazione)."""
        with self._lock:
            if metodo not in self._ritenti and len(self._ritenti) >= MAX_CHIAVI:
                metodo = ALTRO
            self._ritenti[metodo] = self._ritenti.get(metodo, 0) + 1

    def attesa_tetto(self, ms: float) -> None:
        """Quanto si e' atteso il posto fra le 3 richieste concorrenti del conto."""
        with self._lock:
            self._attesa_tetto.aggiungi(float(ms))
        self._inoltra_tratto(TRATTO_ATTESA_TETTO, float(ms))

    # ---------------------------------------------------------------- lettura
    def stato(self) -> Mapping[str, Any]:
        """Fotografia (non azzera): chiavi stabili, mai il token."""
        with self._lock:
            return {
                "sessione": dict(self._sessione),
                "esiti": {m: dict(sorted(d.items())) for m, d in sorted(self._esiti.items())},
                "ritenti": dict(sorted(self._ritenti.items())),
                "latenze": {m: h.riassunto() for m, h in sorted(self._latenze.items())},
                "attesa_tetto": self._attesa_tetto.riassunto(),
                "ultimo_errore": self._ultimo_errore,
            }

    # ---------------------------------------------------------------- inoltro
    def _inoltra_conta(self, gruppo: str, chiave: str) -> None:
        if self._inoltra is None:
            return
        try:
            self._inoltra.conta(gruppo, chiave, 1)
        except Exception as e:  # noqa: BLE001 - la misura non rompe mai il percorso
            logger.warning("[salute-a1] inoltro conta fallito (%s)", type(e).__name__)

    def _inoltra_tratto(self, nome: str, ms: float) -> None:
        if self._inoltra is None:
            return
        try:
            self._inoltra.tratto(nome, ms)
        except Exception as e:  # noqa: BLE001
            logger.warning("[salute-a1] inoltro tratto fallito (%s)", type(e).__name__)
