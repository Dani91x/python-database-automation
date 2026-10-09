"""Contratto del comparto A - connessione Betfair.

Fonte: ``ARCHITETTURA_2026-10/04_ARCHITETTURA_OBIETTIVO.md`` par. 3.2 e scheda
``03_SCHEDE_COMPONENTI/A_CONNESSIONE_BETFAIR.md`` par. 4.1; aggiunta del 09/10
(priorita' dell'utente): lo STREAM DEGLI ORDINI DEL CONTO, senza filtro e in
sola lettura, che porta ogni ordine del conto (app, bot, sito) in tempo reale.

Il book E' quello della libreria (``betfairlightweight.resources.MarketBook``):
nessuna copia nostra. Questo file contiene SOLO tipi e protocolli: nessuna
logica. Si estende solo in modo ADDITIVO e dichiarato nel referto della tappa.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Literal, Mapping, Optional, Protocol, Set, Tuple

NomeProfilo = Literal["runner_calcio", "runner_tennis", "scansione", "scalper_partita"]
StatoFlusso = Literal["vivo", "muto", "assente"]


@dataclass(frozen=True)
class ProfiloFlusso:
    """UN profilo = una politica di sottoscrizione dei prezzi."""

    nome: NomeProfilo
    campi: Tuple[str, ...]              # EX_ALL_OFFERS... (calcio) / EX_BEST_OFFERS (tennis, scanner)
    ladder_levels: int                  # 10 | 1
    conflate_ms: Optional[int]          # None (runner) | 1000 (scanner, decisione U-01)
    heartbeat_ms: Optional[int]         # None (decide Betfair) | 5000 scanner (U-02)
    mercati_per_connessione: int        # 180, mai > 200
    connessioni_max: int                # 3 calcio | 1 tennis | 4 scanner
    riserva_connessioni: int            # 1 (frammenti_mercato.py)
    registra_raw: bool


class Sessione(Protocol):
    """UNA per processo: il custode (oggi ``Betfair/stream/auth.py``)."""

    def client(self) -> Any: ...                      # betfairlightweight.APIClient con sessione valida
    def rinnova_se_serve(self) -> None: ...            # keepAlive entro 20 min (.it), backoff, relogin con freno
    def stato(self) -> Mapping[str, Any]: ...          # login, keepalive, relogin, ultimo errore (per la Salute)


class ClienteRest(Protocol):
    """Il SOLO punto delle chiamate REST: pesi (200 punti), 3 concorrenti per conto, blocchi."""

    def lettura(self, metodo: str, **kwargs: Any) -> Any: ...      # ritentabile (letture)
    def mutazione(self, metodo: str, **kwargs: Any) -> Any: ...    # MAI ritentata (i soldi non si ritentano)


class FlussoMercato(Protocol):
    def imposta_mercati(self, mercati: Iterable[str]) -> Set[str]: ...   # restituisce i "persi"
    def aggiungi_consumatore(self, cb: Callable[[Any], None], *,
                             mercati: Optional[Set[str]] = None) -> None: ...
    def book(self, market_id: str) -> Any: ...                          # MarketBook | None
    def stato(self) -> Mapping[str, object]: ...                        # battito, connessioni, connectionsAvailable
    def stato_flusso(self, market_id: str) -> StatoFlusso: ...


@dataclass(frozen=True)
class OrdineDalConto:
    """Un ordine COME LO DICE BETFAIR sullo stream degli ordini del conto (ocm).

    Chiavi e unita' quelle di Betfair (stream: ``id, p, s, side, status, pt, ot,
    pd, md, sm, sr, sl, sc, sv, avp, rfo, rfs, rc``), tradotte in nomi leggibili.
    Nessuna interpretazione qui: l'attribuzione (chi l'ha fatto) e' del comparto C.
    """

    bet_id: str
    market_id: str
    selection_id: int
    handicap: float
    lato: Literal["back", "lay"]
    prezzo: float
    importo: float
    stato: Literal["EXECUTABLE", "EXECUTION_COMPLETE"]
    persistenza: Optional[str]
    tipo: Optional[str]                     # LIMIT | MARKET_ON_CLOSE | LIMIT_ON_CLOSE
    piazzato_ms: Optional[int]
    abbinato_ms: Optional[int]
    abbinato: float                         # sm
    residuo: float                          # sr
    scaduto: float                          # sl
    annullato: float                        # sc
    annullato_da_betfair: float             # sv (voided)
    prezzo_medio: Optional[float]           # avp
    customer_order_ref: Optional[str]       # rfo
    customer_strategy_ref: Optional[str]    # rfs
    regulator_code: Optional[str]           # rc
    ricevuto_ms: int                        # istante locale di ricezione del messaggio


class FlussoOrdiniConto(Protocol):
    """Stream degli ordini del CONTO, senza filtro di strategia, SOLA LETTURA.

    Non piazza, non annulla, non tocca il flusso ordini filtrato che flumine usa
    per i bot (quello resta com'e'). Con ripresa (initialClk/clk) e backoff.
    """

    def avvia(self) -> None: ...
    def ferma(self) -> None: ...
    def aggiungi_consumatore(self, cb: Callable[[OrdineDalConto], None]) -> None: ...
    def ordini(self, market_id: Optional[str] = None) -> Tuple[OrdineDalConto, ...]: ...
    def stato(self) -> Mapping[str, object]: ...       # vivo/muto, ultimo clk, riconnessioni, eta' ultimo messaggio


class Ladder(Protocol):
    def push_a_ogni_cambio(self, market_id: str) -> None: ...   # guidato dall'evento, minimo 20 ms
    def snapshot(self, market_id: str) -> dict: ...             # STESSO schema JSON `ladder` di oggi

# eventi esposti: book_aggiornato(MarketBook), flusso_muto(id), sessione_rifatta(),
# capacita_cambiata(n), mercato_chiuso(id), ordine_dal_conto(OrdineDalConto)
# eventi consumati: imposta_mercati (auto-follow/follow), ordini_vivi() -> set[str] (da C)
