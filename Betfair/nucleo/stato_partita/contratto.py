"""Contratto del comparto B - stato della partita.

Fonte: ``ARCHITETTURA_2026-10/04_ARCHITETTURA_OBIETTIVO.md`` par. 3.3 e scheda
``03_SCHEDE_COMPONENTI/B_PUNTEGGI_STATO_PARTITA.md`` par. 4.2.

Solo tipi e protocolli, nessuna logica. Estensioni solo additive e dichiarate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Literal, Mapping, Optional, Protocol, Sequence, Tuple

from Betfair.nucleo.comuni import Sport

FasePartita = Literal["pre", "1t", "intervallo", "2t", "supplementari", "finita", "sconosciuta"]
FonteStatoPartita = Literal["ips_scanner", "ips_diretto", "api_football", "registrazione"]


@dataclass(frozen=True)
class Eta:
    """Le tre eta' che oggi si confondono (scheda B par. 3.2)."""

    riga_s: Optional[float]
    punteggio_s: Optional[float]        # = riga + ritardo IPS (scan_feed.py)
    scanner_s: Optional[float]


@dataclass(frozen=True)
class TennisSet:
    sets: Tuple[int, int]
    games: Tuple[int, int]
    punto: Tuple[str, str]
    servizio: Optional[Literal["home", "away"]]
    pressione: bool                     # pressures() resta strategia (tennis_score.py)


@dataclass(frozen=True)
class StatoPartita:
    event_id: str
    sport: Sport
    in_gioco: bool
    fase: FasePartita
    minuto: Optional[int]
    tempo: Optional[int]
    gol: Optional[Tuple[int, int]]
    rossi: Optional[Tuple[int, int]]
    corner: Optional[Tuple[int, int]]
    gialli: Optional[Tuple[int, int]]
    set_game: Optional[TennisSet]
    ko_ms: Optional[int]
    fonte: FonteStatoPartita            # la verita' (oggi `source` mente, scheda B par. 3.7)
    eta: Eta
    prezzi_vivi: Any                    # EsitoFlusso di flusso_prezzi.valuta (cond. 11), non separabile
    grezzo: Mapping[str, Any]           # score_raw invariato (audit)


class StatoPartitaService(Protocol):
    def stato(self, event_id: str) -> Optional[StatoPartita]: ...
    def segui(self, event_ids: Iterable[str]) -> None: ...
    def iscrivi(self, cb: Callable[[StatoPartita], None]) -> Callable[[], None]: ...


class FonteStato(Protocol):
    """Adattatore sostituibile (oggi ScoreProvider)."""

    nome: str

    def leggi(self, event_ids: Sequence[str]) -> Mapping[str, Mapping[str, Any]]: ...

# eventi esposti: StatoCambiato(prima, dopo), GolSegnato, FaseCambiata, FlussoInterrotto/Ripreso
