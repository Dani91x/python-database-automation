"""controlli.py - i controlli della porta PRIMA dell'invio (W1-C1, 09/10/2026).

Scopo
-----
1. ``ContatoreTransazioni``: il contatore delle transazioni/ORA, UNO PER CONTO, sommato
   su tutti gli attori (revisione critica R13, 04 par. 5.2). Oggi il contatore e' quello
   di flumine (``flumine/controls/clientcontrols.py`` ``MaxTransactionCount``), UNO PER
   CLIENT flumine, cioe' per processo (runner calcio, runner tennis, ogni sessione
   scalper hanno il loro): la somma per conto oggi non esiste. Tetto di oggi:
   ``config_stream.LIVE_TRANSACTION_LIMIT`` (``Betfair/stream/config_stream.py:256-262``,
   default 1000). Regola di conteggio: quella di flumine
   (``flumine/execution/betfairexecution.py``), che e' la regola Betfair (02 par. 3.2):
   un place conta per istruzione a ogni risposta (riuscito o fallito), una
   cancellazione RIUSCITA non conta (piazza+cancella = 1), una cancellazione FALLITA
   conta, un replace conta il nuovo place (+ la cancellazione fallita), un esito senza
   risposta (eccezione, timeout di rete) non e' contato da flumine. Il blocco scatta
   quando il totale dell'ora supera il tetto (``safe``: totale <= tetto), su OGNI
   operazione (flumine valida place, cancel, update e replace), e l'ora e' l'ora UTC
   di calendario, ricontrollata solo prima di un'operazione (come ``_check_hour``).
2. ``controlla``: i freni della porta, nello stesso ordine e con gli stessi codici di
   ``motore_ordini.MotoreOrdini._controlla`` (``Betfair/stream/motore_ordini.py``
   ~1061-1180): eta' del comando, modo della RIGA servibile dal processo, guardia
   d'avvio, blocco del modo effettivo sulle APERTURE, kill-switch (le chiusure passano),
   freschezza dei settings, e in piu' il tetto delle transazioni (oggi nel control
   di flumine, dentro ``market.place_order``).

Entrate: la richiesta, un ``FreniConto`` INIETTATO (kill-switch, modo, settings: nessuna
lettura DB qui), il contatore, l'esito della verifica di riduzione (fatta da chi ha le
esposizioni abbinate: mai creduta dalla richiesta). Uscite: ``EsitoControllo``.

Cosa NON fa: non legge env ne' DB (lo fa l'implementazione di ``FreniConto``; quella
di oggi e' ``FreniDiOggi``, con import pigri del worker); non verifica la riduzione
(``riduce_esposizione`` e' verificata dal motore sulle esposizioni del blotter); non
applica i minimi (``minimi.py``); non sostituisce il tetto per sessione dello scalper
(``max_txn_hour`` 300, solo ingressi: divergenza nel referto).
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, Tuple, Union

from Betfair.nucleo.ordini.adattatore_comando import RichiestaComposta
from Betfair.nucleo.ordini.contratto import RichiestaOrdine

logger = logging.getLogger(__name__)

#: codice del rifiuto per tetto orario, lo stesso NAME del control di flumine
CODICE_TETTO = "MAX_TRANSACTION_COUNT"
#: azioni che CHIUDONO (passano col kill-switch): ``live_order_worker._CLOSING_ACTIONS``
AZIONI_CHIUSURA = frozenset({"cancel", "greenup", "cashout_all", "cashout_event"})
MS_ORA = 3_600_000

Esito = str  # "ok" | "fallito" | "ignoto"


class FreniConto(Protocol):
    """I freni del conto, letti da chi li possiede (env, Control Room, settings in RAM).

    Le firme sono quelle degli agganci che ``MotoreOrdini`` gia' accetta (banco F4):
    ``blocco_apertura`` = ``blocco_modo(mode, azione, params)``, ``eta_settings_s`` =
    ``eta_settings()``."""

    def kill_switch(self) -> bool: ...
    def modo_processo(self) -> str: ...
    def blocco_apertura(self, modo_riga: str, azione: str,
                        params: Mapping[str, Any]) -> Optional[str]: ...
    def eta_settings_s(self) -> float: ...


@dataclass(frozen=True)
class EsitoControllo:
    ammesso: bool
    codice: Optional[str] = None
    motivo: Optional[str] = None


# ---------------------------------------------------------------------------
# il contatore delle transazioni, uno per conto
# ---------------------------------------------------------------------------
def tetto_di_oggi() -> Optional[int]:
    """Il tetto di oggi: ``config_stream.LIVE_TRANSACTION_LIMIT`` (import pigro)."""
    from Betfair.stream import config_stream

    return int(config_stream.LIVE_TRANSACTION_LIMIT)


class ContatoreTransazioni:
    """Transazioni dell'ora corrente PER CONTO, da tutti gli attori. Thread-safe.

    ``orologio_ms``: millisecondi epoch (UTC); l'ora e' ``ms // 3_600_000``."""

    def __init__(self, tetto: Optional[int], orologio_ms: Callable[[], int]) -> None:
        self.tetto = tetto
        self._ora_ms = orologio_ms
        self._lock = threading.Lock()
        self._ora: Optional[int] = None
        self.correnti = 0
        self.correnti_fallite = 0
        self.totali = 0
        self.totali_fallite = 0
        self.per_attore: Dict[str, int] = {}

    def _controlla_ora(self) -> None:
        ora = int(self._ora_ms()) // MS_ORA
        if self._ora is None or ora != self._ora:
            if self._ora is not None:
                logger.info("[porta] transazioni: nuova ora (prima %d + %d fallite)",
                            self.correnti, self.correnti_fallite)
            self._ora = ora
            self.correnti = 0
            self.correnti_fallite = 0

    @property
    def totale_ora(self) -> int:
        return self.correnti + self.correnti_fallite

    def consentito(self) -> bool:
        """Come ``MaxTransactionCount.safe`` dopo ``_check_hour``: totale <= tetto."""
        with self._lock:
            self._controlla_ora()
            if self.tetto is None:
                return True
            if self.totale_ora <= self.tetto:
                return True
            logger.error("[porta] tetto transazioni/ora raggiunto: %d > %d",
                         self.totale_ora, self.tetto)
            return False

    def aggiungi(self, n: int, *, fallite: bool = False, attore: Optional[str] = None) -> None:
        """``add_transaction``: nessun controllo dell'ora qui (come flumine)."""
        with self._lock:
            if fallite:
                self.correnti_fallite += n
                self.totali_fallite += n
            else:
                self.correnti += n
                self.totali += n
            if attore is not None:
                self.per_attore[attore] = self.per_attore.get(attore, 0) + n

    def registra(self, azione: str, esito: Esito, *, n: int = 1,
                 cancellazione_fallita: bool = False, attore: Optional[str] = None) -> None:
        """La regola di conteggio di ``BetfairExecution`` per UN'operazione con esito.

        place: +n a ogni risposta (riuscita o fallita); cancel: solo se fallita (+1
        fallita); replace: +n e, se la sua cancellazione e' fallita, +1 fallita;
        ``ignoto`` (nessuna risposta): nulla, come flumine."""
        if esito == "ignoto":
            return
        if azione == "place":
            self.aggiungi(n, attore=attore)
        elif azione == "cancel":
            if esito == "fallito":
                self.aggiungi(n, fallite=True, attore=attore)
        elif azione == "replace":
            self.aggiungi(n, attore=attore)
            if cancellazione_fallita:
                self.aggiungi(1, fallite=True, attore=attore)
        elif azione == "update":
            if esito == "fallito":
                self.aggiungi(n, fallite=True, attore=attore)
        else:
            raise ValueError(f"azione non conteggiabile: {azione!r}")

    def stato(self) -> Dict[str, Any]:
        """Per la "Salute" (P-13: oggi il contatore non e' in UI)."""
        with self._lock:
            return {"tetto": self.tetto, "ora_corrente": self.correnti,
                    "fallite_ora_corrente": self.correnti_fallite,
                    "totale": self.totali, "fallite_totale": self.totali_fallite,
                    "per_attore": dict(self.per_attore)}


# ---------------------------------------------------------------------------
# i freni, nell'ordine del motore
# ---------------------------------------------------------------------------
def servibili(modo_processo: Optional[str]) -> Tuple[str, ...]:
    """``live_order_worker._servable_modes``: LIVE -> live+paper, PAPER -> paper."""
    m = str(modo_processo or "").strip().upper()
    if m == "LIVE":
        return ("live", "paper")
    if m == "PAPER":
        return ("paper",)
    return ()


def _codici() -> Any:
    from Betfair.stream import motore_ordini

    return motore_ordini


def controlla(r: Union[RichiestaOrdine, RichiestaComposta], freni: FreniConto,
              contatore: Optional[ContatoreTransazioni], *, ricevuto_ms: int,
              max_eta_ms: int, riduzione_verificata: Optional[Callable[[], bool]] = None,
              guardia_armata: Callable[[], bool] = lambda: False,
              max_eta_settings_s: float = 10.0) -> EsitoControllo:
    """I freni prima dell'invio. Ordine e codici di ``MotoreOrdini._controlla``.

    ``riduzione_verificata``: chiamata solo se serve (come ``_verifica`` del motore);
    None = nessuno sa verificare -> una riduzione dichiarata NON e' verificata."""
    M = _codici()
    eta = int(ricevuto_ms) - int(r.creato_ms)
    if eta > int(max_eta_ms):
        return EsitoControllo(False, M.M_ETA, f"{M.M_ETA}: eta' {eta} ms > max_eta_ms {max_eta_ms}")
    if -eta > M.FUTURO_TOLLERATO_MS:
        return EsitoControllo(False, M.M_ETA,
                              f"{M.M_ETA}: creato_ms {-eta} ms nel futuro: orologio incoerente")
    proc = str(freni.modo_processo() or "OFF").upper()
    if r.modo not in servibili(proc):
        return EsitoControllo(False, M.M_MODE,
                              f"{M.M_MODE}: mode '{r.modo}' non servibile dal runner in {proc}")
    # come il motore (``valida_comando``: ``reduces_liability`` vale solo per il place): una
    # riduzione dichiarata su un replace/cancel NON scavalca nulla
    riduce = isinstance(r, RichiestaOrdine) and r.azione == "place" \
        and bool(r.riduce_esposizione)
    verificata: Optional[bool] = None

    def _verifica() -> bool:
        nonlocal verificata
        if verificata is None:
            try:
                verificata = bool(riduzione_verificata()) if riduzione_verificata else False
            except Exception as ex:  # noqa: BLE001 - dubbio = non verificata (motore)
                logger.warning("[porta] verifica della riduzione KO: %s", str(ex)[:160])
                verificata = False
        return verificata

    if guardia_armata() and r.azione != "cancel":
        if not riduce:
            return EsitoControllo(False, M.M_GUARDIA,
                                  f"{M.M_GUARDIA}: ripresa d'avvio non ancora riuscita: passa "
                                  f"solo 'cancel' (o una chiusura verificata)")
        if not _verifica():
            return EsitoControllo(False, M.M_RIDUZIONE,
                                  f"{M.M_RIDUZIONE}: guardia d'avvio armata e riduzione non "
                                  f"verificabile sulle esposizioni del runner")
    chiusura = r.azione in AZIONI_CHIUSURA or (riduce and _verifica())
    blocco = freni.blocco_apertura(r.modo, r.azione,
                                   {"reduces_liability": True} if chiusura else {})
    if blocco:
        return EsitoControllo(False, M.M_MODE, f"{M.M_MODE}: {blocco}")
    if freni.kill_switch() and not chiusura:
        if riduce:
            return EsitoControllo(False, M.M_RIDUZIONE,
                                  f"{M.M_RIDUZIONE}: kill-switch ATTIVO e riduzione non "
                                  f"verificabile sulle esposizioni del runner")
        return EsitoControllo(False, M.M_KILL, f"{M.M_KILL}: kill-switch ATTIVO: solo "
                                               f"chiusure permesse")
    if not chiusura:
        eta_s = float(freni.eta_settings_s())
        if eta_s > max_eta_settings_s:
            return EsitoControllo(False, M.M_SETTINGS,
                                  f"{M.M_SETTINGS}: copia dei settings vecchia di {eta_s:.1f} s "
                                  f"(> {max_eta_settings_s:.1f} s): kill-switch e limiti del DB "
                                  f"non verificabili")
    if contatore is not None and not contatore.consentito():
        return EsitoControllo(False, CODICE_TETTO,
                              f"{CODICE_TETTO}: Max Transaction Count has been reached "
                              f"({contatore.totale_ora}) for current hour")
    return EsitoControllo(True)


class FreniDiOggi:
    """``FreniConto`` sopra le funzioni di OGGI del worker (import pigri, nessuna copia):
    ``_kill_switch() or _db_kill_switch()``, ``_modo_processo()``,
    ``_blocco_apertura_modo``, ``eta_settings_s()``. E' l'aggancio dell'ondata 2: qui non
    e' usato da nessuno."""

    @staticmethod
    def _low() -> Any:
        from Betfair.stream import live_order_worker

        return live_order_worker

    def kill_switch(self) -> bool:
        low = self._low()
        return bool(low._kill_switch() or low._db_kill_switch())

    def modo_processo(self) -> str:
        return str(self._low()._modo_processo())

    def blocco_apertura(self, modo_riga: str, azione: str,
                        params: Mapping[str, Any]) -> Optional[str]:
        return self._low()._blocco_apertura_modo(modo_riga, azione, dict(params))

    def eta_settings_s(self) -> float:
        return float(self._low().eta_settings_s())
