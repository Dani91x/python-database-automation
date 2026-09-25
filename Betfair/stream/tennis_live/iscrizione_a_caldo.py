"""iscrizione_a_caldo.py - ISCRIZIONE e ARMAMENTO A CALDO del runner tennis (25/09).

ORDINE DELL'UTENTE (testuale): «TUTTI I BOT UNA VOLTA ARMATI DEVONO OPERARE SU
TUTTE LE PARTITE IDONEE DA SOLI».

IL BUCO (dichiarato in ``AUDIT_2026-09-25/AUTO_FOLLOW_TUTTI_I_BOT.md`` par. 6):
il ponte (``tennis_bot_service``, auto-mode) scrive i follow ``origine='auto'``,
ma il runner tennis li agganciava SOLO ricostruendo il framework flumine
(``follow_worker`` -> ``_request_restart``), e la ricostruzione si RINVIA finche'
un qualunque bot ha una posizione aperta (il blotter nuovo la renderebbe
orfana). Risultato: mentre i bot lavorano, le partite nuove non venivano ne'
seguite ne' armate.

QUI (tutto sulla STESSA connessione, senza ricostruire niente):

* RISOTTOSCRIZIONE A CALDO (``sottoscrivi``): Betfair Stream API sostituisce la
  sottoscrizione con un nuovo ``marketSubscription`` sulla stessa connessione.
  Si usa ``BetfairStream.subscribe_to_markets`` di betfairlightweight (lo
  stesso che flumine chiama all'avvio, ``MarketStream.run``). 25/09
  UNIFICATO: il meccanismo e' ``Betfair/stream/sottoscrizione_a_caldo.py``,
  lo STESSO di ``auto_follow.SottoscrittoreStream.applica`` del calcio (qui
  restano i nomi di sempre, riesportati). Blotter, posizioni (paper e live),
  ordini vivi e worker restano quelli di prima.
* LAVORO NEL THREAD DI FLUMINE (``esegui_nel_thread_di_flumine``): la
  risottoscrizione e l'``add_strategy`` dei bot nuovi girano DENTRO il ciclo
  principale di flumine (``CustomEvent`` sulla ``handler_queue``), cioe' fra un
  MarketBook e l'altro: mai una strategia aggiunta mentre flumine sta
  iterando le strategie, mai uno ``stream_id`` cambiato a meta' di un book.
* TETTO E PRIORITA' (``pianifica``, puro): una sola connessione di mercato,
  200 mercati per connessione (limite Betfair). Il tennis sottoscrive UN
  mercato per partita (Match Odds), quindi il tetto conta partite = mercati.
  Priorita': POSIZIONI VIVE (mai espulse, mai tolte) > seguita A MANO (mai
  espulsa) > COMANDO di un bot (25/09, F8: l'ordine di Safe tennis su una
  partita non seguita, ``esecutore_tennis.AgganciaTennis``) > partita ARMATA
  (almeno un bot) > candidata. Una partita nuova entra
  se c'e' posto; a tetto pieno espelle la partita meno prioritaria e piu'
  vecchia SOLO se di priorita' STRETTAMENTE piu' bassa (niente giostra fra
  pari) e senza posizioni. Niente di espellibile: rifiuto DICHIARATO (resta in
  attesa, riprova al giro dopo).

Nessun I/O verso il database qui: il runner legge e scrive, questo modulo
decide (pianifica) ed esegue sulla connessione (sottoscrivi).

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

#: limite Betfair: 200 mercati per connessione (accertato 09/09, config_stream).
#: 25/09: UNA definizione per calcio e tennis (``sottoscrizione_a_caldo``).
from ..sottoscrizione_a_caldo import LIMITE_BETFAIR_MERCATI  # noqa: E402

ENV_INTERRUTTORE = "TENNIS_ISCRIZIONE_A_CALDO"
ENV_TETTO = "TENNIS_TETTO_MERCATI"
ENV_GRAZIA_USCITA = "TENNIS_USCITA_GRAZIA_S"
#: stesso margine del calcio (``config_stream.HARD_MARKET_CAP`` = 180), ma con
#: env DEDICATA al tennis (il runner tennis non condivide env col calcio)
TETTO_DEFAULT = 180
#: una partita il cui follow e' sparito esce dallo stream solo dopo questa
#: finestra: il tempo allo specchio ordini (1 s) di scrivere il P&L regolato di
#: un mercato appena chiuso, e nessuna uscita per una lettura del DB a vuoto
GRAZIA_USCITA_DEFAULT_S = 30.0

#: priorita' (piu' alto = piu' importante). Le POSIZIONI non sono un numero:
#: una partita con posizioni e' PROTETTA, mai espulsa ne' tolta.
PRI_IN_USCITA = 0      # follow sparito, in grazia: la prima a lasciare il posto
PRI_CANDIDATA = 1      # follow senza bot armati
PRI_ARMATA = 2         # almeno un bot armato (riga in requested/arming/armed/running)
PRI_COMANDO = 3        # 25/09 (F8): un bot ha mandato un ORDINE su questa partita
PRI_MANUALE = 4        # seguita a mano dall'utente: mai espulsa


def acceso(env: Optional[Dict[str, str]] = None) -> bool:
    """Interruttore ``TENNIS_ISCRIZIONE_A_CALDO``: ACCESO di serie (ordine
    dell'utente). ``0``/``false``/``no``/``off`` lo spegne: il runner torna a
    ricostruire il framework per ogni follow nuovo, come prima."""
    envd = os.environ if env is None else env
    v = str(envd.get(ENV_INTERRUTTORE, "") or "").strip().lower()
    return v not in ("0", "false", "no", "off")


def tetto_mercati(env: Optional[Dict[str, str]] = None) -> int:
    """Il tetto di mercati sulla connessione di mercato del runner tennis.

    ``TENNIS_TETTO_MERCATI`` se leggibile, altrimenti 180; MAI oltre 200 (il
    limite Betfair) e mai sotto 1. Env vuota = default (mai ``??``)."""
    envd = os.environ if env is None else env
    raw = str(envd.get(ENV_TETTO, "") or "").strip()
    base = TETTO_DEFAULT
    if raw:
        try:
            base = int(float(raw))
        except ValueError:
            base = TETTO_DEFAULT
    return max(1, min(base, LIMITE_BETFAIR_MERCATI))


def grazia_uscita_s(env: Optional[Dict[str, str]] = None) -> float:
    envd = os.environ if env is None else env
    raw = str(envd.get(ENV_GRAZIA_USCITA, "") or "").strip()
    if not raw:
        return GRAZIA_USCITA_DEFAULT_S
    try:
        v = float(raw)
    except ValueError:
        return GRAZIA_USCITA_DEFAULT_S
    return v if v >= 0 else GRAZIA_USCITA_DEFAULT_S


# ---------------------------------------------------------------------------
# il piano: tetto e priorita' (puro)
# ---------------------------------------------------------------------------
@dataclass
class Evento:
    event_id: str
    manuale: bool = False
    armata: bool = False
    posizioni: bool = False
    in_uscita: bool = False
    #: 25/09 (F8): chiesta da un COMANDO d'ordine di un bot (aggancio a comando)
    comando: bool = False

    @property
    def priorita(self) -> int:
        if self.in_uscita:
            return PRI_IN_USCITA
        if self.manuale:
            return PRI_MANUALE
        if self.comando:
            return PRI_COMANDO
        if self.armata:
            return PRI_ARMATA
        return PRI_CANDIDATA

    @property
    def espellibile(self) -> bool:
        """Mai una partita con posizioni; mai una seguita a mano (salvo che il
        suo follow sia gia' sparito: allora e' ``in_uscita``)."""
        if self.posizioni:
            return False
        return self.in_uscita or not self.manuale


@dataclass
class Piano:
    #: partite da sottoscrivere (in ordine di priorita')
    aggiungi: List[str] = field(default_factory=list)
    #: partite seguite il cui follow e' sparito da oltre la grazia, senza posizioni
    togli: List[str] = field(default_factory=list)
    #: partite seguite tolte per far posto a una piu' prioritaria
    espulsi: List[str] = field(default_factory=list)
    #: partite nuove che non entrano (tetto pieno, niente di espellibile)
    rifiutati: List[str] = field(default_factory=list)
    #: follow sparito ma posizioni vive: restano finche' non sono flat
    tenuti_per_posizioni: List[str] = field(default_factory=list)

    @property
    def cambia(self) -> bool:
        return bool(self.aggiungi or self.togli or self.espulsi)


def pianifica(seguiti: List[Evento], voluti: List[Evento], tetto: int,
              pronti_a_uscire: Optional[Set[str]] = None) -> Piano:
    """Cosa sottoscrivere e cosa togliere, dentro il tetto.

    ``seguiti``: le partite gia' nello stream, dalla piu' VECCHIA. ``voluti``:
    i follow aperti (PENDING/STREAMING), nell'ordine della lista. Un seguito
    che non e' piu' voluto e' ``in_uscita``: esce (``togli``) se e' in
    ``pronti_a_uscire`` (grazia scaduta) e non ha posizioni; con posizioni
    resta (``tenuti_per_posizioni``). Le nuove entrano per priorita'
    (a mano > armate > candidate, a parita' l'ordine della lista); a tetto
    pieno si espelle la meno prioritaria e piu' vecchia fra le espellibili di
    priorita' STRETTAMENTE piu' bassa. Un tetto abbassato sotto i seguiti non
    espelle nessuno: semplicemente non entra niente di nuovo."""
    pronti = {str(x) for x in (pronti_a_uscire or set())}
    ids_voluti = {v.event_id for v in voluti}
    ids_seguiti = {s.event_id for s in seguiti}
    piano = Piano()
    occupati: List[Evento] = []
    for s in seguiti:
        if s.event_id in ids_voluti:
            occupati.append(s)
            continue
        uscente = Evento(s.event_id, s.manuale, s.armata, s.posizioni, in_uscita=True,
                         comando=s.comando)
        if s.posizioni:
            piano.tenuti_per_posizioni.append(s.event_id)
            occupati.append(uscente)
        elif s.event_id in pronti:
            piano.togli.append(s.event_id)
        else:
            occupati.append(uscente)          # in grazia: occupa, ma cede per primo
    nuovi = [v for v in voluti if v.event_id not in ids_seguiti]
    ordine = {v.event_id: i for i, v in enumerate(nuovi)}
    nuovi.sort(key=lambda v: (-v.priorita, ordine[v.event_id]))
    for n in nuovi:
        if len(occupati) < int(tetto):
            occupati.append(n)
            piano.aggiungi.append(n.event_id)
            continue
        candidati = [(i, e) for i, e in enumerate(occupati)
                     if e.event_id not in piano.aggiungi and e.espellibile
                     and e.priorita < n.priorita]
        if not candidati:
            piano.rifiutati.append(n.event_id)
            continue
        i, vittima = min(candidati, key=lambda ie: (ie[1].priorita, ie[0]))
        occupati.pop(i)
        if vittima.in_uscita:
            piano.togli.append(vittima.event_id)
        else:
            piano.espulsi.append(vittima.event_id)
        occupati.append(n)
        piano.aggiungi.append(n.event_id)
    return piano


# ---------------------------------------------------------------------------
# il lavoro dentro il ciclo di flumine
# ---------------------------------------------------------------------------
class LavoroFlumine:
    """Callback di un ``CustomEvent``: esegue ``fn(framework)`` nel thread
    principale di flumine. Se chi aspetta rinuncia (timeout) prima che parta,
    non parte piu' (``annullato``): mai un lavoro eseguito a insaputa."""

    def __init__(self, fn: Callable[[Any], Any]) -> None:
        self.fn = fn
        self.lock = threading.Lock()
        self.fatto = threading.Event()
        self.annullato = False
        self.esito: Any = None
        self.errore: Optional[BaseException] = None

    def __call__(self, framework: Any, event: Any = None) -> None:  # noqa: ARG002
        with self.lock:
            if self.annullato:
                return
            try:
                self.esito = self.fn(framework)
            except Exception as e:  # noqa: BLE001 - riportato a chi aspetta
                self.errore = e
            finally:
                self.fatto.set()


class TempoScaduto(RuntimeError):
    """Il ciclo di flumine non ha eseguito il lavoro in tempo (annullato)."""


def esegui_nel_thread_di_flumine(framework: Any, fn: Callable[[Any], Any],
                                 timeout: float = 5.0) -> Any:
    """Accoda ``fn`` come ``CustomEvent`` e ne aspetta l'esito (al piu'
    ``timeout`` secondi). Scaduto il tempo il lavoro e' ANNULLATO (se non e'
    ancora partito) e si solleva ``TempoScaduto``: il chiamante riprova al
    giro dopo, niente resta a meta'."""
    from flumine.events.events import CustomEvent

    lavoro = LavoroFlumine(fn)
    framework.handler_queue.put(CustomEvent(None, lavoro))
    if not lavoro.fatto.wait(timeout):
        with lavoro.lock:
            if not lavoro.fatto.is_set():
                lavoro.annullato = True
                raise TempoScaduto("ciclo di flumine non disponibile entro %.1fs" % timeout)
    if lavoro.errore is not None:
        raise lavoro.errore
    return lavoro.esito


# ---------------------------------------------------------------------------
# la risottoscrizione a caldo
# ---------------------------------------------------------------------------
# 25/09 UNIFICAZIONE: nuovo marketSubscription sulla stessa connessione,
# stream_id, filtro canonico, book vecchi scartati = ``sottoscrizione_a_caldo``,
# lo STESSO modulo che usa il calcio (``auto_follow.SottoscrittoreStream``).
# I nomi di sempre restano qui (riesportati): runner e test non cambiano.
from ..sottoscrizione_a_caldo import (  # noqa: E402,F401 - riesportati
    NonPronto,
    filtro_mercati,
    mercati_dello_stream,
    sottoscrivi,
    stream_di_mercato,
)


def aggiungi_strategia_sullo_stream(framework: Any, stream: Any, strat: Any) -> None:
    """``framework.add_strategy`` a framework AVVIATO, garantendo che il bot
    entri nella MarketStream ESISTENTE (flumine la riusa solo a filtro,
    data_filter, timeout e conflate identici). Il filtro del bot si allinea a
    quello dello stream PRIMA dell'aggiunta; se flumine avesse comunque creato
    uno stream nuovo (mai avviato: il bot resterebbe cieco) lo si toglie e si
    solleva: il chiamante segna l'errore, mai un bot armato che non vede."""
    if stream is None:
        raise NonPronto("nessuna MarketStream nel framework")
    if not isinstance(stream, strat.stream_class):
        raise ValueError("stream_class del bot incompatibile con lo stream del runner")
    if strat.market_data_filter != stream.market_data_filter:
        raise ValueError("market_data_filter del bot diverso da quello dello stream")
    strat.market_filter = stream.market_filter
    prima = list(getattr(framework.streams, "_streams", []) or [])
    framework.add_strategy(strat)
    if [s for s in strat.streams] != [stream]:
        nuovi = [s for s in list(getattr(framework.streams, "_streams", []) or [])
                 if s not in prima]
        for s in nuovi:
            try:
                framework.streams._streams.remove(s)
            except ValueError:
                pass
        try:
            framework.strategies._strategies.remove(strat)
        except (AttributeError, ValueError):
            pass
        raise RuntimeError("il bot non e' entrato nello stream unico (stream_ids %s)"
                           % list(getattr(strat, "stream_ids", []) or []))
