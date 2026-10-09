"""La sessione Betfair di UN processo: un solo custode, un solo login, keepAlive .it (comparto A, T5, W1-A1).

Implementa ``contratto.Sessione``. Oggi ogni processo ha fino a TRE politiche di
sessione sullo stesso conto (``ARCHITETTURA_2026-10/03_SCHEDE_COMPONENTI/A_CONNESSIONE_BETFAIR.md``
par. 1.7 e D6): l'``APIClient`` del custode (``Betfair/stream/auth.py:161-290``,
keepAlive 480 s nel runner, 600 s scalper, 900 s scanner), il ``keep_alive`` di
default di flumine, e la sessione JSON-RPC ``rest`` del runner calcio
(``runner.py:2710-2711``) che NON ha ne' keepAlive ne' relogin (reperto). Qui c'e'
UNA sessione per processo:

  * il client e' quello di oggi: ``auth.build_client(login=False)`` (locale
    ``italy``, certificati, ``requests.Session`` riusata), importato e non copiato;
  * il rinnovo e' quello di oggi: ``auth.CustodeSessione`` (keepAlive a periodo,
    backoff 15/30/60 s, login su errore di sessione o al 90% della vita di 1200 s),
    riusato tale e quale; la Sessione gli passa un client "custodito" il cui
    ``login`` passa dal FRENO e il cui ``keep_alive`` e' contato;
  * il FRENO dei login (nuovo): al massimo N login riusciti e M tentativi al
    minuto PER PROCESSO (di serie 10 e 20: il conto ne ammette 100 al minuto in
    tutto, poi ban di 20 minuti) e, se Betfair risponde
    ``TEMPORARY_BAN_TOO_MANY_REQUESTS``, nessun tentativo per 20 minuti;
  * ``INVALID_SESSION_INFORMATION``/``NO_SESSION`` visti dal REST o dallo stream:
    ``rifai_login(errore, generazione_vista)`` rifa' il login UNA volta anche se
    piu' thread vedono lo stesso errore insieme (contatore di generazione);
  * ``sessione_rifatta``: i consumatori (lo stream) si registrano con
    ``alla_sessione_rifatta(cb)`` e sono chiamati dopo ogni relogin.

Entrate: la fabbrica del client (di serie quella di oggi), l'orologio monotono
(iniettabile), i parametri di periodo/backoff/freno. Uscite: ``client()``
(``betfairlightweight.APIClient`` con sessione valida), ``stato()`` per la
Salute (mai il token), gli eventi ``sessione_rifatta``.

Cosa NON fa: non apre thread finche' non si chiama ``avvia()``; importare il
modulo non legge ``config``/``.env`` (``auth`` si importa dentro i metodi, perche'
``config.py`` chiama ``load_dotenv`` al caricamento); non ricostruisce lo stream
(lo decide chi riceve ``sessione_rifatta``); non coordina i login FRA processi
(proposta nel referto).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import collections
import logging
import threading
import time
from typing import Any, Callable, Deque, Dict, List, Mapping, Optional, Sequence

from . import limiti
from .salute import SaluteBetfair

logger = logging.getLogger(__name__)

#: periodo del keepAlive di serie: quello del runner calcio e tennis di oggi
#: (``LIVE_STREAM_KEEPALIVE_SEC`` = 480, ``runner.py:1324``)
PERIODO_KEEPALIVE_DI_SERIE_S = 480.0
#: quota di serie dei 100 login/minuto del conto per UN processo (10 processi)
TETTO_LOGIN_RIUSCITI_DI_SERIE = limiti.tetto_login_per_processo(10)
TETTO_TENTATIVI_LOGIN_DI_SERIE = 2 * TETTO_LOGIN_RIUSCITI_DI_SERIE


class LoginFrenato(RuntimeError):
    """Il freno ha rifiutato un login (tetto del minuto o ban in corso). Nessuna
    richiesta e' partita verso Betfair."""


def _testo_catena(exc: Optional[BaseException], profondita: int = 6) -> str:
    """Testo maiuscolo dell'eccezione e delle sue cause (per riconoscere i codici)."""
    parti: List[str] = []
    cur = exc
    while cur is not None and len(parti) < profondita:
        try:
            parti.append(str(cur).upper())
        except Exception:  # noqa: BLE001 - __str__ esotici: si salta l'anello
            parti.append("")
        cur = cur.__cause__ or cur.__context__
    return " | ".join(parti)


def e_ban_login(exc: Optional[BaseException]) -> bool:
    """True se Betfair ha risposto al login col ban di 20 minuti."""
    return limiti.CODICE_BAN_LOGIN in _testo_catena(exc)


class FrenoLogin:
    """Tetto dei login di UN processo, con orologio iniettabile. Thread-safe.

    ``verifica`` solleva ``LoginFrenato`` se un login adesso supererebbe il tetto
    dei riusciti o dei tentativi nell'ultimo minuto, o se c'e' un ban in corso.
    """

    def __init__(self, *, tetto_riusciti_al_minuto: int = TETTO_LOGIN_RIUSCITI_DI_SERIE,
                 tetto_tentativi_al_minuto: int = TETTO_TENTATIVI_LOGIN_DI_SERIE,
                 finestra_s: float = 60.0, ban_s: float = float(limiti.DURATA_BAN_LOGIN_S),
                 ora: Optional[Callable[[], float]] = None) -> None:
        if tetto_riusciti_al_minuto < 1 or tetto_tentativi_al_minuto < 1:
            raise ValueError("i tetti del freno devono essere >= 1")
        if tetto_riusciti_al_minuto > limiti.LOGIN_RIUSCITI_AL_MINUTO_PER_CONTO:
            raise ValueError("tetto dei login oltre il limite del conto (100/min)")
        self.tetto_riusciti = int(tetto_riusciti_al_minuto)
        self.tetto_tentativi = int(tetto_tentativi_al_minuto)
        self.finestra_s = float(finestra_s)
        self.ban_s = float(ban_s)
        self._ora: Callable[[], float] = ora or time.monotonic
        self._riusciti: Deque[float] = collections.deque()
        self._tentativi: Deque[float] = collections.deque()
        self._ban_fino: Optional[float] = None
        self.rifiuti = 0
        self._lock = threading.Lock()

    def _pulisci(self, adesso: float) -> None:
        limite = adesso - self.finestra_s
        for coda in (self._riusciti, self._tentativi):
            while coda and coda[0] <= limite:
                coda.popleft()

    def verifica(self, adesso: Optional[float] = None) -> None:
        """Nessun effetto se il login e' permesso; altrimenti ``LoginFrenato``."""
        a = float(self._ora() if adesso is None else adesso)
        with self._lock:
            self._pulisci(a)
            motivo = None
            if self._ban_fino is not None and a < self._ban_fino:
                motivo = f"ban dei login in corso per altri {self._ban_fino - a:.0f}s"
            elif len(self._riusciti) >= self.tetto_riusciti:
                motivo = f"{len(self._riusciti)} login riusciti nell'ultimo minuto (tetto {self.tetto_riusciti})"
            elif len(self._tentativi) >= self.tetto_tentativi:
                motivo = f"{len(self._tentativi)} tentativi di login nell'ultimo minuto (tetto {self.tetto_tentativi})"
            if motivo is None:
                return
            self.rifiuti += 1
        raise LoginFrenato(motivo)

    def registra_tentativo(self, adesso: Optional[float] = None) -> None:
        a = float(self._ora() if adesso is None else adesso)
        with self._lock:
            self._tentativi.append(a)

    def registra_riuscito(self, adesso: Optional[float] = None) -> None:
        a = float(self._ora() if adesso is None else adesso)
        with self._lock:
            self._riusciti.append(a)

    def registra_ban(self, adesso: Optional[float] = None) -> None:
        a = float(self._ora() if adesso is None else adesso)
        with self._lock:
            self._ban_fino = a + self.ban_s

    def stato(self, adesso: Optional[float] = None) -> Dict[str, Any]:
        a = float(self._ora() if adesso is None else adesso)
        with self._lock:
            self._pulisci(a)
            ban = None if self._ban_fino is None or a >= self._ban_fino else round(self._ban_fino - a, 1)
            return {
                "login_ultimo_minuto": len(self._riusciti),
                "tentativi_ultimo_minuto": len(self._tentativi),
                "tetto_riusciti": self.tetto_riusciti,
                "tetto_tentativi": self.tetto_tentativi,
                "ban_per_altri_s": ban,
                "rifiuti": self.rifiuti,
            }


def _fabbrica_di_oggi() -> Any:
    """Il client di oggi, NON loggato: ``auth.build_client(login=False)``."""
    from Betfair.stream import auth  # import pigro: config.py legge .env all'import

    return auth.build_client(login=False)


class _ClientCustodito:
    """Il client come lo vede ``auth.CustodeSessione``: ``keep_alive`` contato,
    ``login`` che passa dal freno. Le eccezioni risalgono GREZZE, cosi' il
    custode le classifica e le descrive come oggi."""

    def __init__(self, sessione: "SessioneBetfair") -> None:
        self._sessione = sessione

    @property
    def session_timeout(self) -> Any:
        return getattr(self._sessione._client, "session_timeout", limiti.VITA_SESSIONE_ITALIA_S)

    def keep_alive(self) -> Any:
        return self._sessione._keep_alive_contato()

    def login(self) -> Any:
        return self._sessione._login_frenato()


class SessioneBetfair:
    """UNA sessione Betfair per processo (vedi la docstring del modulo).

    :param fabbrica_client: callable senza argomenti che crea l'``APIClient`` NON
        loggato (di serie ``auth.build_client(login=False)``).
    :param periodo_keepalive_s: periodo del keepAlive (di serie 480 s).
    :param ritenti_s: backoff dopo un fallimento (None = quello del custode di
        oggi, 15/30/60 s).
    :param freno: ``FrenoLogin`` (None = tetti di serie, stesso orologio).
    :param salute: ``SaluteBetfair`` condivisa col REST (None = nuova).
    :param ora: orologio monotono in secondi (iniettabile nei test).
    """

    def __init__(self, *, fabbrica_client: Optional[Callable[[], Any]] = None,
                 periodo_keepalive_s: float = PERIODO_KEEPALIVE_DI_SERIE_S,
                 ritenti_s: Optional[Sequence[float]] = None,
                 freno: Optional[FrenoLogin] = None,
                 salute: Optional[SaluteBetfair] = None,
                 ora: Optional[Callable[[], float]] = None,
                 nome: str = "betfair") -> None:
        self._fabbrica = fabbrica_client or _fabbrica_di_oggi
        self.periodo_keepalive_s = float(periodo_keepalive_s)
        self._ritenti_s = None if ritenti_s is None else tuple(float(x) for x in ritenti_s)
        self._ora: Callable[[], float] = ora or time.monotonic
        self.freno = freno or FrenoLogin(ora=self._ora)
        self.salute = salute or SaluteBetfair()
        self.nome = nome
        self._client: Any = None
        self._custode: Any = None
        self._custodito = _ClientCustodito(self)
        #: quanti login riusciti dalla nascita (0 = mai loggata)
        self.generazione = 0
        self.ultimo_esito: Optional[str] = None
        self._da_notificare = 0
        self._consumatori: List[Callable[[], None]] = []
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._ferma = threading.Event()

    # ------------------------------------------------------------ contratto
    def client(self) -> Any:
        """L'``APIClient`` con sessione valida; il primo uso fa il login (freno).

        :raises BetfairStreamAuthError: login fallito (come ``build_client``).
        :raises LoginFrenato: il freno ha rifiutato il login.
        """
        with self._lock:
            if self._client is None:
                self._client = self._fabbrica()
            if self.generazione == 0:
                self._primo_login()
            client = self._client
        self._notifica()
        return client

    def rinnova_se_serve(self) -> None:
        """keepAlive se e' ora, backoff dopo un fallimento, relogin con freno."""
        self.rinnova()

    def stato(self) -> Mapping[str, Any]:
        """Per la Salute: mai il token."""
        with self._lock:
            custode = None if self._custode is None else self._custode.stato()
            return {
                "nome": self.nome,
                "connessa": self.generazione > 0,
                "generazione": self.generazione,
                "periodo_keepalive_s": self.periodo_keepalive_s,
                "vita_s": None if self._custode is None else self._custode.vita_s(),
                "ultimo_esito": self.ultimo_esito,
                "custode": custode,
                "freno": self.freno.stato(),
                "contatori": dict(self.salute.stato()["sessione"]),
                "thread_custode": self._thread is not None and self._thread.is_alive(),
            }

    # ------------------------------------------------------------ estensioni
    @property
    def conto(self) -> str:
        """Il conto (username) del client, per il tetto delle concorrenti."""
        with self._lock:
            if self._client is None:
                self._client = self._fabbrica()
            return str(getattr(self._client, "username", "") or "")

    def rinnova(self, adesso: Optional[float] = None) -> Optional[str]:
        """Un giro del custode: None (non e' ora / mai loggata), "ok", "relogin", "ko"."""
        with self._lock:
            if self._custode is None:
                return None
            esito = self._custode.tick(adesso)
            if esito is not None:
                self.ultimo_esito = esito
        self._notifica()
        return esito

    def segnala_errore(self, exc: BaseException) -> bool:
        """Un errore visto altrove (stream): se e' di sessione il prossimo giro
        rifa' il login. True se preso in carico."""
        with self._lock:
            if self._custode is None:
                return False
            return bool(self._custode.segnala_errore(exc))

    def rifai_login(self, exc: BaseException, generazione_vista: int) -> bool:
        """Errore di SESSIONE su una chiamata fatta con la ``generazione_vista``:
        rifa' il login ADESSO (una volta sola anche con piu' thread). True se la
        sessione e' nuova (rifatta ora o da un altro thread nel frattempo)."""
        with self._lock:
            if self._custode is None:
                return False
            if self.generazione != generazione_vista:
                return True
            if not self._custode.segnala_errore(exc):
                return False
            esito = self._custode.tick()
            self.ultimo_esito = esito
        self._notifica()
        return esito == "relogin"

    def alla_sessione_rifatta(self, cb: Callable[[], None]) -> None:
        """Registra un consumatore dell'evento ``sessione_rifatta``."""
        with self._lock:
            self._consumatori.append(cb)

    def avvia(self, intervallo_s: float = 5.0) -> None:
        """Thread del custode: un giro ogni ``intervallo_s`` (finche' ``ferma``)."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._ferma.clear()
            t = threading.Thread(target=self._giro, args=(float(intervallo_s),),
                                 name=f"a1-sessione-{self.nome}", daemon=True)
            self._thread = t
        t.start()

    def ferma(self, attesa_s: float = 5.0) -> None:
        """Ferma il thread del custode (idempotente)."""
        self._ferma.set()
        t = self._thread
        if t is not None:
            t.join(attesa_s)
        with self._lock:
            self._thread = None

    def chiudi(self) -> None:
        """Ferma il custode e fa il logout (best-effort, come ``auth.safe_logout``)."""
        self.ferma()
        with self._lock:
            client, self._client, self._custode = self._client, None, None
            loggata = self.generazione > 0
            self.generazione = 0
        if client is not None and loggata:
            from Betfair.stream import auth

            auth.safe_logout(client)

    # ------------------------------------------------------------ interni
    def _giro(self, intervallo_s: float) -> None:
        while not self._ferma.wait(intervallo_s):
            try:
                self.rinnova()
            except Exception as e:  # noqa: BLE001 - il custode non cade mai
                logger.warning("[sessione-a1] %s: giro del custode fallito (%s)", self.nome, type(e).__name__)

    def _primo_login(self) -> None:
        from Betfair.stream import auth

        try:
            self._login_frenato()
        except LoginFrenato:
            raise
        except Exception as e:  # noqa: BLE001 - stesso messaggio di build_client
            logger.debug("[sessione-a1] dettaglio cert login: %s", e)
            raise auth.BetfairStreamAuthError(f"Cert login Betfair fallito ({type(e).__name__})") from e
        kw: Dict[str, Any] = {"periodo_s": self.periodo_keepalive_s, "ora": self._ora, "nome": self.nome}
        if self._ritenti_s is not None:
            kw["ritenti_s"] = self._ritenti_s
        self._custode = auth.CustodeSessione(self._custodito, **kw)
        logger.info("[sessione-a1] %s: cert login .it OK (sessione attiva).", self.nome)

    def _login_frenato(self) -> Any:
        """UN login che passa dal freno; eccezioni grezze (le descrive il custode)."""
        adesso = float(self._ora())
        try:
            self.freno.verifica(adesso)
        except LoginFrenato as e:
            self.salute.evento_sessione("login_frenati")
            logger.warning("[sessione-a1] %s: login frenato (%s)", self.nome, e)
            raise
        self.freno.registra_tentativo(adesso)
        try:
            esito = self._client.login()
        except Exception as e:
            self.salute.evento_sessione("login_falliti")
            if e_ban_login(e):
                self.freno.registra_ban(adesso)
                self.salute.evento_sessione("ban_login")
                logger.critical("[sessione-a1] %s: Betfair ha bloccato i login per %.0fs",
                                self.nome, self.freno.ban_s)
            raise
        self.freno.registra_riuscito(adesso)
        with self._lock:
            self.generazione += 1
            relogin = self.generazione > 1
            if relogin:
                self._da_notificare += 1
        self.salute.evento_sessione("login")
        if relogin:
            self.salute.evento_sessione("relogin")
        return esito

    def _keep_alive_contato(self) -> Any:
        try:
            esito = self._client.keep_alive()
        except Exception:
            self.salute.evento_sessione("keepalive_falliti")
            raise
        self.salute.evento_sessione("keepalive")
        return esito

    def _notifica(self) -> None:
        """Chiama i consumatori di ``sessione_rifatta`` FUORI dal lucchetto."""
        with self._lock:
            n, self._da_notificare = self._da_notificare, 0
            consumatori = list(self._consumatori)
        for _ in range(n):
            for cb in consumatori:
                try:
                    cb()
                except Exception as e:  # noqa: BLE001 - un consumatore non ferma la sessione
                    logger.warning("[sessione-a1] %s: consumatore di sessione_rifatta fallito (%s)",
                                   self.nome, type(e).__name__)


# ---------------------------------------------------------------------------
# UNA sessione per processo (stato di processo DICHIARATO)
# ---------------------------------------------------------------------------
_SESSIONE_DI_PROCESSO: Optional[SessioneBetfair] = None
_LOCK_PROCESSO = threading.Lock()


def sessione_del_processo(**opzioni: Any) -> SessioneBetfair:
    """La sessione unica del processo, creata al primo uso con ``opzioni`` (gli
    argomenti di ``SessioneBetfair``). Le chiamate successive DEVONO arrivare
    senza opzioni: due configurazioni diverse nello stesso processo sono un
    errore, non si sceglie in silenzio.

    :raises ValueError: opzioni passate quando la sessione esiste gia'.
    """
    global _SESSIONE_DI_PROCESSO  # noqa: PLW0603 - stato di processo dichiarato
    with _LOCK_PROCESSO:
        if _SESSIONE_DI_PROCESSO is None:
            _SESSIONE_DI_PROCESSO = SessioneBetfair(**opzioni)
        elif opzioni:
            raise ValueError("la sessione del processo esiste gia': opzioni non applicabili")
        return _SESSIONE_DI_PROCESSO


def chiudi_sessione_del_processo() -> None:
    """Chiude e toglie la sessione del processo (spegnimento, test)."""
    global _SESSIONE_DI_PROCESSO  # noqa: PLW0603
    with _LOCK_PROCESSO:
        s, _SESSIONE_DI_PROCESSO = _SESSIONE_DI_PROCESSO, None
    if s is not None:
        s.chiudi()
