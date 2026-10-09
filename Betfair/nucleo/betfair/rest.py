"""Il SOLO punto delle chiamate REST a Betfair (comparto A, T5, W1-A1).

Implementa ``contratto.ClienteRest`` sopra gli endpoint di betfairlightweight
(``client.betting.*``, ``client.account.*``) e la sessione unica del processo
(``sessione.py``). Oggi le chiamate REST passano da tre famiglie con tre
politiche diverse (``Betfair/client.py`` JSON-RPC con 3 tentativi e sleep fino a
8 s; ``odds_refresh._with_client`` / ``omega_market.call`` con un relogin e un
ritento su qualunque errore; ``omega_market.call_mutating`` che non ritenta) e
da cinque ripieghi ``listMarketBook`` a blocchi fissi (25 e 20 mercati).

Qui:
  * ``lettura(metodo, **kwargs)``: ritentabile con la classificazione degli
    errori di oggi (``classifica_errore``): LIMITE (``TOO_MANY_REQUESTS``,
    ``TOO_MUCH_DATA``: ``odds_refresh.LIMIT_MARKERS``) -> stop pulito con
    ``BetfairLimitHit`` (riusata), MAI ritentato; SESSIONE (``auth.e_errore_di_sessione``)
    -> relogin dalla Sessione (freno, una volta per generazione) e ritento;
    PERMANENTE (``ValueError``/``LookupError``, come ``order_exec._call``) -> rilancio;
    RETE/altro -> ritento dopo una pausa, fino a ``PoliticaLettura.tentativi``;
  * ``mutazione(metodo, **kwargs)`` (place/cancel/replace/update): UNA chiamata.
    MAI ripetuta su un errore generico (un timeout puo' nascondere un ordine gia'
    accettato). Come ``omega_market.call_mutating`` (``omega_market.py:89-112``),
    ripetuta UNA volta solo se Betfair dichiara la sessione non valida (la
    richiesta e' stata rifiutata prima di arrivare all'exchange) e il relogin
    riesce; ``rifai_mutazione_su_sessione=False`` toglie anche questa;
  * suddivisione automatica di ``listMarketBook`` e ``listMarketProfitAndLoss``
    in blocchi che non superano 200 punti (``limiti.blocchi_per_peso``) con la
    proiezione chiesta; risultati concatenati nell'ordine dei ``market_ids``;
  * al massimo 3 richieste concorrenti per CONTO sui metodi che si contendono il
    tetto (``limiti.e_metodo_conteso``): semaforo per conto, condiviso da tutti i
    ``ClienteRestBetfair`` del processo sullo stesso conto;
  * ``Connection: keep-alive`` e gzip: sono gli header di betfairlightweight
    (``BaseClient.request_headers``) sulla ``requests.Session`` riusata del client
    (``auth.build_client``); qui non si apre nessuna sessione HTTP nuova.

Entrate: nome del metodo Betfair (``listMarketBook``...) e i parametri di
betfairlightweight (snake_case: ``market_ids``, ``price_projection``,
``lightweight``...). Uscite: cio' che restituisce betfairlightweight (risorse o
dict con ``lightweight=True``); per i metodi suddivisi, la lista concatenata.

Cosa NON fa: non pagina ``listCurrentOrders``/``listClearedOrders`` (resta al
chiamante, come oggi ``client.py:361-425``); non suddivide il catalogo; non
controlla i limiti delle istruzioni d'ordine (porta degli ordini, comparto C);
non coordina il tetto delle 3 concorrenti FRA processi (proposta nel referto).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Literal, Mapping, Optional, Tuple

from . import limiti
from .salute import SaluteBetfair

logger = logging.getLogger(__name__)

ClasseErrore = Literal["limite", "sessione", "rete", "permanente"]

#: metodo Betfair -> (endpoint dell'APIClient, funzione di betfairlightweight)
LETTURE: Mapping[str, Tuple[str, str]] = {
    "listEventTypes": ("betting", "list_event_types"),
    "listCompetitions": ("betting", "list_competitions"),
    "listEvents": ("betting", "list_events"),
    "listMarketCatalogue": ("betting", "list_market_catalogue"),
    "listMarketBook": ("betting", "list_market_book"),
    "listRunnerBook": ("betting", "list_runner_book"),
    "listCurrentOrders": ("betting", "list_current_orders"),
    "listClearedOrders": ("betting", "list_cleared_orders"),
    "listMarketProfitAndLoss": ("betting", "list_market_profit_and_loss"),
    "getAccountFunds": ("account", "get_account_funds"),
    "getAccountDetails": ("account", "get_account_details"),
    "getAccountStatement": ("account", "get_account_statement"),
    "listCurrencyRates": ("account", "list_currency_rates"),
}
MUTAZIONI: Mapping[str, Tuple[str, str]] = {
    "placeOrders": ("betting", "place_orders"),
    "cancelOrders": ("betting", "cancel_orders"),
    "replaceOrders": ("betting", "replace_orders"),
    "updateOrders": ("betting", "update_orders"),
}
if tuple(MUTAZIONI) != limiti.METODI_MUTAZIONE:  # una sola definizione delle mutazioni
    raise RuntimeError("MUTAZIONI di rest.py e METODI_MUTAZIONE di limiti.py divergono")


class CodaContoPiena(RuntimeError):
    """Nessun posto fra le richieste concorrenti del conto entro l'attesa massima."""


@dataclass(frozen=True)
class PoliticaLettura:
    """Quante volte si prova una lettura e quanto si aspetta prima di riprovare
    dopo un errore di RETE (dopo un errore di sessione la pausa e' il relogin).

    Di serie 2 tentativi (uno + un ritento), come ``odds_refresh._with_client`` e
    ``omega_market.call``; ``client.py`` di oggi ne fa 3 con pause 2/4/8 s."""

    tentativi: int = 2
    pause_s: Tuple[float, ...] = (1.0,)

    def pausa(self, ritento: int) -> float:
        if not self.pause_s:
            return 0.0
        return float(self.pause_s[min(ritento - 1, len(self.pause_s) - 1)])


def classifica_errore(exc: BaseException) -> ClasseErrore:
    """La classificazione di OGGI, con le funzioni di oggi (importate):
    limite (``odds_refresh._is_limit``), sessione (``auth.e_errore_di_sessione``),
    permanente (``ValueError``/``LookupError``, ``order_exec._call``), altrimenti rete."""
    from Betfair.odds_refresh import _is_limit
    from Betfair.stream.auth import e_errore_di_sessione

    if isinstance(exc, Exception) and _is_limit(exc):
        return "limite"
    if e_errore_di_sessione(exc):
        return "sessione"
    if isinstance(exc, (ValueError, LookupError)):
        return "permanente"
    return "rete"


def descrivi_errore(exc: BaseException) -> str:
    """Tipo e codice, MAI il testo intero (puo' contenere il token): quella di
    ``auth`` piu' il codice di limite se c'e'."""
    from Betfair.odds_refresh import LIMIT_MARKERS
    from Betfair.stream.auth import _descrivi_errore

    base = _descrivi_errore(exc)
    try:
        testo = str(exc).upper()
    except Exception:  # noqa: BLE001 - __str__ esotici
        testo = ""
    for k in LIMIT_MARKERS:
        if k in testo:
            return f"{base}: {k}"
    return base


# ---------------------------------------------------------------------------
# tetto delle richieste concorrenti per CONTO (stato di processo DICHIARATO)
# ---------------------------------------------------------------------------
_TETTI_PER_CONTO: Dict[str, threading.BoundedSemaphore] = {}
_CAPIENZA_PER_CONTO: Dict[str, int] = {}
_LOCK_TETTI = threading.Lock()


def tetto_del_conto(conto: str, capienza: int = limiti.RICHIESTE_CONCORRENTI_PER_CONTO
                    ) -> threading.BoundedSemaphore:
    """Il semaforo del conto, UNO per processo e per conto.

    :raises ValueError: capienza oltre il limite ufficiale o diversa da quella
        gia' fissata per lo stesso conto."""
    if not 1 <= int(capienza) <= limiti.RICHIESTE_CONCORRENTI_PER_CONTO:
        raise ValueError(f"capienza non valida: {capienza!r}")
    with _LOCK_TETTI:
        sem = _TETTI_PER_CONTO.get(conto)
        if sem is None:
            sem = _TETTI_PER_CONTO[conto] = threading.BoundedSemaphore(int(capienza))
            _CAPIENZA_PER_CONTO[conto] = int(capienza)
        elif _CAPIENZA_PER_CONTO[conto] != int(capienza):
            raise ValueError(f"il conto ha gia' un tetto di {_CAPIENZA_PER_CONTO[conto]}")
        return sem


class ClienteRestBetfair:
    """Il cliente REST unico del processo (vedi la docstring del modulo).

    :param sessione: la ``SessioneBetfair`` (o un oggetto con ``client()``,
        ``generazione``, ``rifai_login(exc, gen)``, ``conto``, ``salute``).
    :param politica: ``PoliticaLettura`` delle letture.
    :param concorrenti_per_conto: capienza del semaforo del conto (<= 3).
    :param attesa_tetto_s: attesa massima di un posto fra le concorrenti.
    :param pausa_tra_blocchi_s: pausa fra i blocchi di una richiesta suddivisa
        (0 di serie; oggi 0,35 s scanner, 0,6 s ``odds_refresh``).
    :param blocco_massimo: {metodo: mercati} per stringere i blocchi (ombra con i
        blocchi di oggi: scanner 25, ``odds_refresh`` 20).
    :param rifai_mutazione_su_sessione: True = parita' con ``call_mutating``.
    :param dormi: ``time.sleep`` (iniettabile); ``orologio``: secondi monotoni.
    """

    def __init__(self, sessione: Any, *, salute: Optional[SaluteBetfair] = None,
                 politica: PoliticaLettura = PoliticaLettura(),
                 concorrenti_per_conto: int = limiti.RICHIESTE_CONCORRENTI_PER_CONTO,
                 attesa_tetto_s: float = 30.0,
                 pausa_tra_blocchi_s: float = 0.0,
                 blocco_massimo: Optional[Mapping[str, int]] = None,
                 rifai_mutazione_su_sessione: bool = True,
                 dormi: Callable[[float], None] = time.sleep,
                 orologio: Callable[[], float] = time.monotonic) -> None:
        if politica.tentativi < 1:
            raise ValueError("la politica deve fare almeno un tentativo")
        self._sessione = sessione
        self.salute: SaluteBetfair = salute or getattr(sessione, "salute", None) or SaluteBetfair()
        self.politica = politica
        self._concorrenti = int(concorrenti_per_conto)
        self._attesa_tetto_s = float(attesa_tetto_s)
        self._pausa_blocchi = float(pausa_tra_blocchi_s)
        self._blocco_massimo = dict(blocco_massimo or {})
        self._rifai_mutazione = bool(rifai_mutazione_su_sessione)
        self._dormi = dormi
        self._orologio = orologio
        self._tetto: Optional[threading.BoundedSemaphore] = None
        # generazione della sessione con cui e' partita l'ULTIMA richiesta di
        # questo thread (letta DOPO ``client()``: il primo uso fa il login)
        self._tls = threading.local()

    # ------------------------------------------------------------ contratto
    def lettura(self, metodo: str, **kwargs: Any) -> Any:
        """Una lettura (ritentabile). ``listMarketBook``/``listMarketProfitAndLoss``
        con ``market_ids`` sono suddivise per peso.

        :raises ValueError: metodo sconosciuto o di mutazione.
        :raises BetfairLimitHit: Betfair ha risposto con un limite (mai ritentato).
        """
        if metodo in MUTAZIONI:
            raise ValueError(f"{metodo} cambia stato sul conto: si chiama con mutazione()")
        if metodo not in LETTURE:
            raise ValueError(f"metodo REST sconosciuto: {metodo}")
        peso = limiti.peso_richiesta(metodo, kwargs)
        if peso is None or "market_ids" not in kwargs:
            return self._lettura_ritentata(metodo, kwargs)
        blocchi = limiti.blocchi_per_peso(kwargs["market_ids"], peso, self._blocco_massimo.get(metodo))
        risultati: List[Any] = []
        for i, blocco in enumerate(blocchi):
            if i and self._pausa_blocchi > 0:
                self._dormi(self._pausa_blocchi)
            parziale = self._lettura_ritentata(metodo, {**kwargs, "market_ids": blocco})
            risultati.extend(parziale or [])
        return risultati

    def mutazione(self, metodo: str, **kwargs: Any) -> Any:
        """Una mutazione (place/cancel/replace/update): MAI ritentata su errore
        generico; ripetuta UNA volta solo dopo un rifiuto di sessione e un
        relogin riuscito (parita' con ``call_mutating``).

        :raises ValueError: metodo che non e' una mutazione.
        """
        if metodo not in MUTAZIONI:
            raise ValueError(f"{metodo} non e' una mutazione")
        try:
            return self._chiama(metodo, kwargs, MUTAZIONI)
        except Exception as e:
            if not self._rifai_mutazione or classifica_errore(e) != "sessione":
                raise
            if not self._sessione.rifai_login(e, self._generazione_usata()):
                raise
            logger.warning("[rest-a1] %s: sessione non valida, relogin fatto: UNA ripetizione "
                           "(la richiesta era stata rifiutata prima dell'exchange)", metodo)
            return self._chiama(metodo, kwargs, MUTAZIONI)

    # ------------------------------------------------------------ interni
    def _lettura_ritentata(self, metodo: str, kwargs: Mapping[str, Any]) -> Any:
        tentativo = 0
        while True:
            tentativo += 1
            try:
                return self._chiama(metodo, kwargs, LETTURE)
            except Exception as e:
                classe = classifica_errore(e)
                if classe == "limite":
                    from Betfair.odds_refresh import BetfairLimitHit

                    raise BetfairLimitHit(descrivi_errore(e)) from e
                if classe == "permanente" or tentativo >= self.politica.tentativi:
                    raise
                if classe == "sessione":
                    if not self._sessione.rifai_login(e, self._generazione_usata()):
                        raise
                else:
                    self._dormi(self.politica.pausa(tentativo))
                self.salute.ritento(metodo)
                logger.warning("[rest-a1] %s: tentativo %d fallito (%s), ritento",
                               metodo, tentativo, descrivi_errore(e))

    def _generazione_usata(self) -> int:
        """La generazione della sessione dell'ultima richiesta di questo thread."""
        return int(getattr(self._tls, "generazione", self._sessione.generazione))

    def _semaforo(self) -> threading.BoundedSemaphore:
        if self._tetto is None:
            self._tetto = tetto_del_conto(self._sessione.conto, self._concorrenti)
        return self._tetto

    def _chiama(self, metodo: str, kwargs: Mapping[str, Any],
                tabella: Mapping[str, Tuple[str, str]]) -> Any:
        """UNA richiesta HTTP: semaforo del conto se conteso, latenza ed esito alla Salute."""
        endpoint, funzione = tabella[metodo]
        client = self._sessione.client()
        self._tls.generazione = self._sessione.generazione
        fn = getattr(getattr(client, endpoint), funzione)
        sem = self._semaforo() if limiti.e_metodo_conteso(metodo, kwargs) else None
        if sem is not None:
            t0 = self._orologio()
            preso = sem.acquire(timeout=self._attesa_tetto_s)
            self.salute.attesa_tetto((self._orologio() - t0) * 1000.0)
            if not preso:
                raise CodaContoPiena(f"{metodo}: nessun posto fra le {self._concorrenti} "
                                     f"richieste concorrenti del conto in {self._attesa_tetto_s:.0f}s")
        try:
            t0 = self._orologio()
            try:
                risultato = fn(**kwargs)
            except Exception as e:
                ms = (self._orologio() - t0) * 1000.0
                self.salute.esito_rest(metodo, classifica_errore(e), ms, descrivi_errore(e))
                raise
            self.salute.esito_rest(metodo, "ok", (self._orologio() - t0) * 1000.0)
            return risultato
        finally:
            if sem is not None:
                sem.release()
