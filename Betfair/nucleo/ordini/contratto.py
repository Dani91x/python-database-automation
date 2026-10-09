"""Contratto del comparto C - porta degli ordini e libro ordini del conto.

Fonte: ``ARCHITETTURA_2026-10/04_ARCHITETTURA_OBIETTIVO.md`` par. 3.4 e scheda
``03_SCHEDE_COMPONENTI/C_PORTA_ORDINI.md`` par. 4.2; aggiunta del 09/10 (priorita'
dell'utente: "sul ladder di Trading vedo TUTTO come un tool professionale"):
``OrdineConto`` con l'ATTRIBUZIONE (chi l'ha fatto) e ``PosizioneMercato`` con
il P&L di mercato "se vince" calcolato su tutti gli ordini.

Solo tipi e protocolli, nessuna logica. Estensioni solo additive e dichiarate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Literal, Mapping, Optional, Protocol, Tuple

from Betfair.nucleo.comuni import Modo, Sport

Azione = Literal["place", "cancel", "replace"]        # greenup/dutch/cashout = compositori sopra la porta
Persistenza = Literal["LAPSE", "PERSIST", "MARKET_ON_CLOSE"]
FaseOrdine = Literal["accettato", "parcheggiato", "ridotto", "parziale", "abbinato",
                     "scaduto", "annullato", "rifiutato", "ignoto"]
# chi ha fatto l'ordine (09/10): i bot per nome, l'utente dall'app, il sito
# Betfair (nessun riferimento nostro), "sconosciuto" se il riferimento c'e' ma
# non e' di nessuno dei nostri
Autore = Literal["desktop", "mike", "omega", "safe", "safe_tennis", "scalper",
                 "tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing",
                 "risk", "sito", "sconosciuto"]


@dataclass(frozen=True)
class RichiestaOrdine:
    """I campi di ``valida_comando`` (motore_ordini.py) + 2 estensioni (piano 04 par. 3.4)."""

    ref: str                        # deterministico dalla riga del bot, <= 32 caratteri (dedup 60 s)
    attore: str                     # "safe" | "omega" | "mike" | "desktop" | "risk" | "scalper" | ...
    sport: Sport
    modo: Modo                      # il modo della RIGA, mai del servizio (PSB par. 7 n.25)
    azione: Azione
    market_id: str
    selection_id: int
    handicap: float = 0.0
    lato: Optional[Literal["back", "lay"]] = None
    prezzo: Optional[float] = None
    importo: Optional[float] = None
    persistenza: Persistenza = "LAPSE"
    time_in_force: Optional[Literal["FILL_OR_KILL"]] = None
    riduce_esposizione: bool = False   # verificata dal motore, mai creduta
    bet_id: Optional[str] = None
    riduzione: Optional[float] = None
    nuovo_prezzo: Optional[float] = None
    creato_ms: int = 0
    origine: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class Ack:
    ref: str
    accettato: bool
    seq: Optional[int]
    motivo: Optional[str]


@dataclass(frozen=True)
class EventoOrdine:
    ref: str
    seq: int
    fase: FaseOrdine
    bet_id: Optional[str]
    abbinato: float
    residuo: float
    prezzo_medio: Optional[float]
    codice_errore: Optional[str]
    esito_ms: Optional[int]
    punta_050: Optional[Mapping[str, Any]] = None
    portata_al_minimo: Optional[Mapping[str, Any]] = None
    tradotto: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class StatoOrdine:
    ref: str
    bet_id: Optional[str]
    fase: FaseOrdine
    abbinato: float
    residuo: float
    prezzo_medio: Optional[float]
    ultimo_seq: int


@dataclass(frozen=True)
class OrdineConto:
    """Un ordine del conto con l'attribuzione (libro ordini del conto, 09/10).

    ``modo`` = 'live' per tutto cio' che arriva da Betfair; gli ordini in PROVA
    non esistono su Betfair e arrivano dai motori paper con ``modo='paper'``:
    mai sommati ai live.
    """

    bet_id: str
    market_id: str
    selection_id: int
    handicap: float
    lato: Literal["back", "lay"]
    prezzo: float
    importo: float
    abbinato: float
    residuo: float
    prezzo_medio: Optional[float]
    stato: str
    autore: Autore
    ref: Optional[str]
    modo: Modo
    aggiornato_ms: int


@dataclass(frozen=True)
class PosizioneMercato:
    """P&L di mercato "se vince" per selezione, su TUTTI gli ordini abbinati del
    mercato (per autore e totale), per modo: paper e live mai sommati."""

    market_id: str
    modo: Modo
    se_vince: Mapping[int, float]                       # selection_id -> P&L se vince quella selezione
    se_vince_per_autore: Mapping[str, Mapping[int, float]]
    abbinato_back: Mapping[int, float]
    abbinato_lay: Mapping[int, float]
    prezzo_medio_back: Mapping[int, Optional[float]]
    prezzo_medio_lay: Mapping[int, Optional[float]]
    esposizione_massima: float                          # la perdita peggiore fra gli esiti (<= 0)


@dataclass(frozen=True)
class PosizioneConto:
    market_id: str
    selection_id: Optional[int]
    modo: Modo
    se_vince: float
    se_perde: float


class PortaOrdini(Protocol):
    def invia(self, r: RichiestaOrdine) -> Ack: ...
    def eventi(self, attore: str, da_seq: int = 0) -> Iterator[EventoOrdine]: ...
    def stato(self, ref: str) -> Optional[StatoOrdine]: ...
    def posizione(self, market_id: str, selection_id: Optional[int] = None) -> PosizioneConto: ...


class Esecutore(Protocol):
    """EsecutoreBetfair (flumine live), EsecutorePaper (SimulatedExecution), EsecutoreBanco."""

    def place(self, r: RichiestaOrdine) -> EventoOrdine: ...
    def cancel(self, r: RichiestaOrdine) -> EventoOrdine: ...
    def replace(self, r: RichiestaOrdine) -> EventoOrdine: ...


class LibroOrdiniConto(Protocol):
    """Tutti gli ordini del conto su un mercato, con l'autore (09/10)."""

    def ordini(self, market_id: str, modo: Optional[Modo] = None) -> Tuple[OrdineConto, ...]: ...
    def posizione(self, market_id: str, modo: Modo) -> PosizioneMercato: ...
