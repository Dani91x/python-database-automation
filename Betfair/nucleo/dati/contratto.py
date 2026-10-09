"""Contratto del comparto G - dati: archivio locale, postino, cloud, registro.

Fonte: ``ARCHITETTURA_2026-10/04_ARCHITETTURA_OBIETTIVO.md`` par. 3.7 e 6 e scheda
``03_SCHEDE_COMPONENTI/G_DATI_E_ALGORITMI_DEL_CLOUD.md`` par. 4.2-4.5.

Ordini dell'utente (09/10), vincolanti per ogni implementazione:
  * l'archivio locale e' INVISIBILE: l'utente non lo vede, non lo usa, non lo
    configura; si crea, si aggiorna di schema e si mantiene da solo;
  * il database cloud NON perde nessun dato rispetto a oggi: ogni riga che oggi
    arriva nel cloud ci arriva ancora (stessa tabella, stesse colonne), dopo la
    decisione, senza doppioni; se il postino non puo' consegnare, la riga resta
    in coda e si alza un allarme: MAI scartata in silenzio.

Solo tipi e protocolli, nessuna logica. Estensioni solo additive e dichiarate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Mapping, Optional, Protocol, Sequence, Tuple

Natura = Literal["SV", "CMD", "ARC", "STA", "CFG"]
Regime = Literal["stato_denaro", "stato_vivo", "log", "cache", "cloud"]
Operazione = Literal["upsert", "insert", "patch", "delete"]


@dataclass(frozen=True)
class SpecTabella:
    """UNA riga del registro per tabella del cloud (89 + quelle scritte da RPC)."""

    nome: str
    chiave_naturale: Tuple[str, ...]
    natura: Natura
    regime: Regime
    ritardo_max_s: float
    coalesce: bool
    rev_colonna: Optional[str]           # versione monotona per riga (mai indietro)
    dipende_da: Tuple[str, ...]          # tabelle padre delle chiavi esterne
    scrittori_oggi: Tuple[str, ...] = ()  # file:riga di chi la scrive oggi
    scrittore_domani: Optional[str] = None


@dataclass(frozen=True)
class StatoPostino:
    in_coda: int
    eta_max_s: Optional[float]
    per_tabella: Mapping[str, int]
    ultimo_errore: Optional[str]
    offline_da: Optional[datetime]
    dead_letter: int


@dataclass(frozen=True)
class EsitoDrenaggio:
    consegnate: int
    ritentate: int
    dead_letter: int
    errore: Optional[str]


@dataclass(frozen=True)
class RapportoRiconciliazione:
    tabella: str
    da_ts: datetime
    righe_locali: int
    righe_cloud: int
    mancanti_nel_cloud: Tuple[str, ...]
    in_piu_nel_cloud: Tuple[str, ...]
    diverse: Tuple[str, ...]


class Archivio(Protocol):
    """Memoria + SQLite/JSONL sul PC, MAI la rete. Invisibile all'utente."""

    def leggi(self, tabella: str, chiave: Mapping[str, Any]) -> Optional[Mapping[str, Any]]: ...
    def scrivi(self, tabella: str, riga: Mapping[str, Any]) -> None: ...   # + outbox nella STESSA transazione
    def transizione(self, tabella: str, chiave: Mapping[str, Any], da: str, a: str) -> bool: ...


class Cloud(Protocol):
    """UN client, UN timeout per profilo, UNA politica di ritento (db_client.py)."""

    def leggi(self, tabella: str, filtri: Mapping[str, Any], *, cache_s: float = 0.0) -> Sequence[Mapping[str, Any]]: ...
    def rpc(self, nome: str, args: Mapping[str, Any], *, cache_s: float = 0.0) -> Any: ...


class Postino(Protocol):
    def accoda(self, tabella: str, op: Operazione, chiave: Optional[str],
               riga: Mapping[str, Any], *, coalesce: bool = False) -> int: ...
    def stato(self) -> StatoPostino: ...
    def drena(self, max_righe: int = 200) -> EsitoDrenaggio: ...
    def riconcilia(self, tabella: str, da_ts: datetime) -> RapportoRiconciliazione: ...

# eventi esposti: dati.postino_offline(da), dati.dead_letter(tabella, riga, errore),
# dati.riconciliazione(rapporto)
