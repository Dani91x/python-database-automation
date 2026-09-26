"""Costruzione dell'APIClient betfairlightweight (cert login .it).

Riusa le credenziali già in config.py (stesse del client REST esistente).
betfairlightweight gestisce locale='italy' → endpoint identitysso-cert.betfair.it.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional, Sequence

import betfairlightweight
import requests

from config import (
    BETFAIR_APP_KEY,
    BETFAIR_CERT_FILE,
    BETFAIR_KEY_FILE,
    BETFAIR_PASSWORD,
    BETFAIR_USERNAME,
)

logger = logging.getLogger(__name__)


class BetfairStreamAuthError(RuntimeError):
    pass


def build_client(login: bool = True) -> betfairlightweight.APIClient:
    """Crea (e opzionalmente logga) un APIClient betfairlightweight per l'exchange .it.

    :param login: se True esegue subito il cert login.
    :raises BetfairStreamAuthError: se mancano credenziali o il login fallisce.
    """
    missing = [
        name
        for name, val in (
            ("BETFAIR_APP_KEY", BETFAIR_APP_KEY),
            ("BETFAIR_USERNAME", BETFAIR_USERNAME),
            ("BETFAIR_PASSWORD", BETFAIR_PASSWORD),
            ("BETFAIR_CERT_FILE", BETFAIR_CERT_FILE),
            ("BETFAIR_KEY_FILE", BETFAIR_KEY_FILE),
        )
        if not val
    ]
    if missing:
        raise BetfairStreamAuthError(
            "Configurazione Betfair incompleta: " + ", ".join(missing)
        )

    # SESSIONE HTTP RIUSATA (keep-alive): senza `session`, betfairlightweight usa
    # il modulo `requests` nudo e apre una connessione TLS NUOVA a ogni chiamata
    # (handshake + ricarica del bundle CA ≈ 0.3s CPU e ~0.5s di latenza per
    # richiesta). Misurato il 09/09: 6 GET IPS = 6 handshake / 2.75s CPU contro
    # 1 handshake / 0.41s con una Session. Vale per TUTTI i processi (runner,
    # scalper, tennis, omega, scanner): list_market_book, get_scores, keep-alive.
    client = betfairlightweight.APIClient(
        username=BETFAIR_USERNAME,
        password=BETFAIR_PASSWORD,
        app_key=BETFAIR_APP_KEY,
        locale="italy",  # → identitysso-cert.betfair.it
        cert_files=(BETFAIR_CERT_FILE, BETFAIR_KEY_FILE),
        session=requests.Session(),
    )

    if login:
        try:
            client.login()
            logger.info("[stream-auth] cert login .it OK (sessione attiva).")
        except Exception as e:  # noqa: BLE001 - vogliamo un messaggio chiaro a monte
            # NON includere il messaggio grezzo: può contenere il body della
            # risposta di Betfair (codici/echo parametri). Dettaglio solo a DEBUG.
            logger.debug("[stream-auth] dettaglio cert login: %s", e)
            raise BetfairStreamAuthError(
                f"Cert login Betfair fallito ({type(e).__name__})"
            ) from e

    return client


def keep_alive(client: betfairlightweight.APIClient) -> None:
    """Rinnova la sessione (da chiamare periodicamente nei run lunghi)."""
    try:
        client.keep_alive()
    except Exception as e:  # noqa: BLE001
        # solo il tipo a WARNING (l'eccezione può contenere il token di sessione)
        logger.debug("[stream-auth] dettaglio keep_alive: %s", e)
        logger.warning("[stream-auth] keep_alive fallito: %s", type(e).__name__)


# ---------------------------------------------------------------------------
# FIX-C (26/09): CUSTODE DELLA SESSIONE - la sessione sopravvive a una caduta
# ---------------------------------------------------------------------------
# Il 26/09 alle 10:41Z la rete e' caduta per ~1 minuto (DNS KO fino alle 10:48Z)
# proprio quando toccava il keepAlive del feed unico. ``keep_alive`` qui sopra
# ingoia l'errore e il chiamante segnava comunque "fatto": il tentativo dopo
# arrivava 900 s piu' tardi, oltre i 20 minuti di vita di una sessione .it
# (``SESSION_TIMEOUT[italy]`` di betfairlightweight; per Betfair le chiamate API
# NON prolungano la sessione, solo keepAlive/login). A quel punto keepAlive
# risponde NO_SESSION per sempre, nessuno rifaceva il login, e REST e stream
# sono rimasti senza sessione per 4 ore.
#
# ``keep_alive`` resta com'e' (lo usano i runner, che non sono di questo
# cantiere): il custode e' un oggetto a parte, con l'orologio iniettabile.
# A regime fa ESATTAMENTE una keepAlive per periodo (nessuna chiamata in piu');
# solo dopo un fallimento ritenta con backoff (15, 30, 60, 60... s) e rifa' il
# login quando la sessione e' certamente morta (errore di sessione dichiarato
# da Betfair, oppure oltre la vita della sessione dall'ultimo rinnovo riuscito).

_ERRORI_DI_SESSIONE = ("INVALID_SESSION_INFORMATION", "NO_SESSION")
_RITENTI_DEFAULT_S = (15.0, 30.0, 60.0)


def e_errore_di_sessione(exc: Optional[BaseException]) -> bool:
    """True se Betfair dice che la SESSIONE non e' valida (non un errore di rete).

    Guarda il testo dell'eccezione e delle sue cause (``APIError`` REST,
    ``KeepAliveError``, ``ListenerError`` dello stream riportano il codice).
    """
    visti = 0
    cur: Optional[BaseException] = exc
    while cur is not None and visti < 6:
        try:
            testo = str(cur).upper()
        except Exception:  # noqa: BLE001 - __str__ esotici
            testo = ""
        if any(k in testo for k in _ERRORI_DI_SESSIONE):
            return True
        cur = cur.__cause__ or cur.__context__
        visti += 1
    return False


def _descrivi_errore(exc: BaseException) -> str:
    """Tipo + codice di sessione se c'e'. MAI il testo intero: le risposte di
    keepAlive/login riportano il token."""
    nome = type(exc).__name__
    interna = getattr(exc, "exception", None)
    if interna is not None:
        nome = f"{nome}({type(interna).__name__})"
    testo = ""
    try:
        testo = str(exc).upper()
    except Exception:  # noqa: BLE001
        pass
    for k in _ERRORI_DI_SESSIONE:
        if k in testo:
            return f"{nome}: {k}"
    if "GETADDRINFO" in testo:
        return f"{nome}: getaddrinfo failed"
    return nome


class CustodeSessione:
    """Tiene viva la sessione Betfair di UN client e la rifa' dopo una caduta.

    ``tick(adesso)`` va chiamato a ogni giro del servizio: non fa nulla finche'
    non e' ora; ``segnala_errore(exc)`` anticipa il rinnovo quando una chiamata
    REST o lo stream riportano un errore di sessione. Non solleva MAI.
    """

    def __init__(
        self,
        client: Any,
        *,
        periodo_s: float = 900.0,
        ritenti_s: Sequence[float] = _RITENTI_DEFAULT_S,
        ora: Optional[Callable[[], float]] = None,
        nome: str = "betfair",
    ) -> None:
        self.client = client
        self.periodo_s = float(periodo_s)
        self.ritenti_s = tuple(float(x) for x in ritenti_s) or _RITENTI_DEFAULT_S
        # orologio letto a ogni chiamata (None = time.monotonic del momento)
        self._ora: Callable[[], float] = ora or (lambda: time.monotonic())
        self.nome = nome
        # vita della sessione sul server (.it: 1200 s), letta al primo rinnovo:
        # COSTRUIRE il custode non tocca il client (il banco di replay crea lo
        # Scanner con un client che vieta qualunque accesso)
        self._vita_s: Optional[float] = None
        adesso = float(self._ora())
        # chi costruisce il custode ha appena fatto il login (build_client)
        self._ultimo_ok = adesso
        self._prossimo = adesso + self.periodo_s
        self._sessione_morta = False
        self.fallimenti = 0
        self.rinnovi = 0
        self.relogin = 0
        self.ultimo_errore: Optional[str] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ interfaccia
    def vita_s(self) -> float:
        """Vita della sessione sul server (betfairlightweight ``session_timeout``,
        .it = 1200 s); 1200 se il client non la dichiara."""
        if self._vita_s is None:
            try:
                self._vita_s = float(getattr(self.client, "session_timeout", 1200) or 1200)
            except Exception:  # noqa: BLE001 - client esotico: vale il .it
                self._vita_s = 1200.0
        return self._vita_s

    def dovuto(self, adesso: Optional[float] = None) -> bool:
        a = float(self._ora() if adesso is None else adesso)
        return a >= self._prossimo

    def segnala_errore(self, exc: BaseException, adesso: Optional[float] = None) -> bool:
        """Un errore di SESSIONE visto altrove: il prossimo ``tick`` rifa' il
        login senza aspettare. Gli errori di rete non cambiano nulla (il
        backoff lo decide il custode). Ritorna True se l'ha preso in carico."""
        if not e_errore_di_sessione(exc):
            return False
        a = float(self._ora() if adesso is None else adesso)
        with self._lock:
            self._sessione_morta = True
            self._prossimo = min(self._prossimo, a)
        return True

    def tick(self, adesso: Optional[float] = None) -> Optional[str]:
        """None = niente da fare; "ok" = keepAlive riuscito; "relogin" =
        sessione rifatta; "ko" = tentativo fallito (si ritenta col backoff)."""
        a = float(self._ora() if adesso is None else adesso)
        with self._lock:
            if a < self._prossimo:
                return None
            # margine del 10%: il login si rifa' PRIMA che keepAlive dica NO_SESSION
            morta = self._sessione_morta or (a - self._ultimo_ok >= self.vita_s() * 0.9)
        if not morta:
            try:
                self.client.keep_alive()
                return self._riuscito(a, relogin=False)
            except Exception as e:  # noqa: BLE001 - mai far cadere il servizio
                if not e_errore_di_sessione(e):
                    return self._fallito(a, e, "keepAlive")
                # NO_SESSION: la sessione e' morta, si va al login subito
        try:
            self.client.login()
            return self._riuscito(a, relogin=True)
        except Exception as e:  # noqa: BLE001
            with self._lock:
                self._sessione_morta = True
            return self._fallito(a, e, "login")

    def stato(self, adesso: Optional[float] = None) -> dict:
        """Per lo stato del servizio: mai il token."""
        a = float(self._ora() if adesso is None else adesso)
        return {
            "eta_ultimo_rinnovo_s": round(a - self._ultimo_ok, 1),
            "prossimo_tra_s": round(max(0.0, self._prossimo - a), 1),
            "fallimenti": self.fallimenti,
            "rinnovi": self.rinnovi,
            "relogin": self.relogin,
            "sessione_da_rifare": self._sessione_morta,
            "ultimo_errore": self.ultimo_errore,
        }

    # ------------------------------------------------------------ interni
    def _riuscito(self, a: float, *, relogin: bool) -> str:
        with self._lock:
            ripresa = self.fallimenti > 0
            self._ultimo_ok = a
            self._prossimo = a + self.periodo_s
            self._sessione_morta = False
            self.fallimenti = 0
            self.ultimo_errore = None
            self.rinnovi += 1
            if relogin:
                self.relogin += 1
        if relogin or ripresa:
            logger.warning("[stream-auth] %s: sessione %s dopo la caduta", self.nome,
                           "RIFATTA (login)" if relogin else "rinnovata")
        return "relogin" if relogin else "ok"

    def _fallito(self, a: float, e: BaseException, cosa: str) -> str:
        with self._lock:
            self.fallimenti += 1
            attesa = self.ritenti_s[min(self.fallimenti - 1, len(self.ritenti_s) - 1)]
            self._prossimo = a + attesa
            self.ultimo_errore = f"{cosa}: {_descrivi_errore(e)}"
        logger.debug("[stream-auth] dettaglio %s: %s", cosa, e)
        logger.warning("[stream-auth] %s: %s fallito (%s), ritento fra %.0fs",
                       self.nome, cosa, self.ultimo_errore, attesa)
        return "ko"


def safe_logout(client: Optional[betfairlightweight.APIClient]) -> None:
    if client is None:
        return
    try:
        client.logout()
    except Exception as e:  # noqa: BLE001
        logger.debug("[stream-auth] logout ignorato: %s", e)
