# db_client.py
import os
import threading
from typing import Any, Optional

from supabase import create_client, Client, ClientOptions
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

# A1 (fix WinError 10035): client PER-THREAD, non più singleton condiviso.
# Il runner flumine ha molti BackgroundWorker concorrenti (ladder, score, ordini,
# risk, xhedge, daily-stop…): un unico client condiviso significa contesa sullo
# stesso pool di connessioni httpx sincrone — sotto picco in-play su Windows le
# scritture fallivano a raffica con [WinError 10035] (WSAEWOULDBLOCK).
# Un client per thread = ogni worker ha le sue connessioni. I thread del runner
# sono pochi e longevi → nessuna crescita incontrollata di client.
_TLS = threading.local()

# D1 (28/09) - TIMEOUT PostgREST PER I SERVIZI DEI BOT.
# Il default della libreria e' 120 s su ogni fase (connessione, lettura,
# scrittura): con la rete «a buco nero» (pacchetti persi, nessun errore DNS) un
# giro di Safe o di Mike restava appeso fino a due minuti per OGNI chiamata.
# Il database stesso uccide ogni query PostgREST oltre 8 s
# (``statement_timeout=8s`` e ``lock_timeout=8s`` sul ruolo ``authenticator``,
# verificato su ``pg_roles`` il 28/09; nessuna RPC chiamata dai bot alza il
# proprio limite) e il massimo osservato in ``pg_stat_statements`` sulle query
# dei bot e' 6,3 s: una lettura oltre 20 s non e' una query lenta, e' una rete
# morta. Il profilo si accende SOLO nei processi dei bot (``main`` di Safe e
# Mike) con ``usa_timeout_bot()``: runner, backfill, action e script tengono il
# default di sempre, perche' alcune loro RPC alzano il limite a 60-600 s.
BOT_CONNECT_S = 5.0
BOT_LETTURA_S = 20.0

_STATO = {"timeout": None}          # None = default della libreria (120 s)
_LOCK = threading.Lock()


def _secondi_da_env(nome: str, difetto: float) -> float:
    """Override da ambiente: vuoto o non numerico = difetto (mai 0)."""
    raw = (os.environ.get(nome) or "").strip()
    if not raw:
        return difetto
    try:
        v = float(raw)
    except ValueError:
        return difetto
    return v if v > 0 else difetto


def timeout_bot() -> Any:
    """Il ``httpx.Timeout`` del profilo bot (override ``SUPABASE_BOT_CONNECT_S``
    e ``SUPABASE_BOT_LETTURA_S``)."""
    import httpx

    conn = _secondi_da_env("SUPABASE_BOT_CONNECT_S", BOT_CONNECT_S)
    lett = _secondi_da_env("SUPABASE_BOT_LETTURA_S", BOT_LETTURA_S)
    return httpx.Timeout(lett, connect=conn, pool=conn)


def usa_timeout_bot() -> Any:
    """Accende il profilo bot per TUTTO il processo (ogni thread, anche i
    client gia' creati: al prossimo ``get_supabase_client`` si ricreano).
    Ritorna il timeout applicato. Da chiamare all'inizio del ``main`` di un
    servizio bot, mai da un modulo condiviso."""
    t = timeout_bot()
    with _LOCK:
        _STATO["timeout"] = t
    return t


def timeout_corrente() -> Optional[Any]:
    """Il timeout PostgREST in uso nel processo (None = default libreria)."""
    return _STATO["timeout"]


def get_supabase_client() -> Client:
    """Ritorna il client Supabase del THREAD corrente (creato pigramente).

    08/10: il client si RICREA (connessione HTTP/2 nuova) dopo ``rinnova_client()``
    (chiamata da ``con_ritentativi`` su una connessione terminata dal server) e, solo nei
    processi che l'hanno chiesto con ``attiva_rinnovo_connessioni`` (Seasons Catchup),
    ogni ``RINNOVO`` richieste: il server chiude la connessione HTTP/2 dopo 10.000
    richieste (GOAWAY ``last_stream_id:19999``, run 37049359939 e 37141249749)."""
    voluto = _STATO["timeout"]
    client = getattr(_TLS, "client", None)
    if client is not None and getattr(_TLS, "timeout", None) is voluto:
        ogni = _STATO_RETE["rinnovo_ogni"]
        contatore = getattr(_TLS, "contatore", None)
        if not ogni or contatore is None or contatore[0] < ogni:
            return client
        _log_rete.warning("[RETE] client Supabase rinnovato dopo %d richieste (prevenzione GOAWAY "
                          "a 10.000 richieste per connessione HTTP/2)", contatore[0])
        STATISTICHE_RETE["rinnovi_client"] += 1
    if voluto is None:
        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    else:
        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
                               options=ClientOptions(postgrest_client_timeout=voluto))
    try:
        # marca: un client nato qui si risolve SEMPRE nel client corrente del thread
        # (vedi _client_per), cosi' chi lo tiene in una variabile segue i rinnovi
        client._db_client_prod = True  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - oggetti finti nei test
        pass
    _TLS.client = client
    _TLS.timeout = voluto
    _TLS.contatore = _installa_contatore(client) if _STATO_RETE["rinnovo_ogni"] else None
    if resilienza_action_attiva():
        # 09/10: solo nei processi delle action (mai nei bot), vedi TrasportoResiliente
        _installa_trasporto_resiliente(client)
    _aggancia_monitor(client)
    return client


def _aggancia_monitor(client: Any) -> None:
    """09/10 (T0A "Salute"): con ``MONITOR_SALUTE=1`` e il monitor avviato dal main
    del servizio, conta le richieste PostgREST per tabella (hook di httpx). Spento:
    nessun effetto."""
    try:
        from Betfair.monitor import sonde as _mon
    except Exception:  # noqa: BLE001 - fuori dal repo dei bot (action): niente monitor
        return
    if _mon.ATTIVO:
        _mon.aggancia_client_db(client)


# ---------------------------------------------------------------------------
# 08/10/2026 - RESILIENZA DI RETE PostgREST (AUDIT_2026-10-08/action_catchup/REFERTO.md)
# ---------------------------------------------------------------------------
# Un SOLO punto per le chiamate PostgREST della catena Seasons Catchup
# (seasons_catchup, season_gaps, per_fixture_backfill): `esegui_con_retry` e il
# motore `con_ritentativi`. Fallimenti dell'action (1 su 4 run) visti nei log:
#   - HTTP 520 con pagina HTML di Cloudflare (postgrest: APIError code 520,
#     'JSON could not be generated', details = HTML): nessun ritentativo -> traceback;
#   - <ConnectionTerminated error_code:0, last_stream_id:19999>: il server chiude la
#     connessione HTTP/2 dopo 10.000 richieste e httpx solleva RemoteProtocolError
#     sulla richiesta in volo.
# Si ritentano SOLO i guasti di trasporto/gateway (classifica_guasto_rete). Mai i 4xx,
# mai gli errori applicativi, mai il 57014 (statement timeout): quello ha gia' il suo
# meccanismo (R-CATCHUP-2, dimezzamento e "degradata", season_gaps.riepilogo_lacune).
# Non riusa Betfair/stream/net_retry.is_transient: li' il marcatore "timeout" prende
# anche il 57014 ('canceling statement due to statement timeout') e le attese sono da
# bot (0,15 s); toccarlo cambierebbe il comportamento dei bot.
import logging as _logging
import random as _random
import time as _time
from collections import Counter as _Counter
from contextlib import contextmanager as _contextmanager
from typing import Callable, Dict, Sequence, Tuple, TypeVar

_log_rete = _logging.getLogger("db_client")
_T = TypeVar("_T")

#: attese tra un tentativo e il successivo (1 esecuzione + 5 ritentativi, ~62 s in tutto)
ATTESE_RETE_S: Tuple[float, ...] = (2.0, 4.0, 8.0, 16.0, 32.0)
#: dopo tanti guasti PERSISTENTI di fila (nessuna chiamata riuscita in mezzo) si smette di
#: aspettare: un tentativo solo per chiamata finche' una non riesce (niente 62 s x N blocchi)
INTERRUTTORE_DOPO_GUASTI = 2
#: rinnovo preventivo del client (solo se attivato): ben sotto le 10.000 del server
RINNOVO_DEFAULT = 5000
#: motivo di stop scritto da per_fixture_backfill e letto da seasons_catchup
MOTIVO_GUASTO_RETE = "guasto rete/gateway"

_STATO_RETE: Dict[str, Any] = {"rinnovo_ogni": None, "guasti_di_fila": 0}
STATISTICHE_RETE: Dict[str, Any] = {"ritentativi": 0, "riusciti_dopo_ritentativo": 0,
                                    "guasti_persistenti": 0, "rinnovi_client": 0,
                                    "per_classe": _Counter()}

# PostgREST senza database (503/504 con JSON): PGRST000-003. Postgres in avvio/arresto o
# connessioni esaurite (08xxx, 53300, 57P01, 57P03). NON 53100 (disco pieno: non passa
# ritentando, e' un guasto vero che deve uscire).
_CODICI_TRANSITORI = frozenset({"PGRST000", "PGRST001", "PGRST002", "PGRST003",
                                "53300", "57P01", "57P03"})


class GuastoRete(RuntimeError):
    """Guasto di rete/gateway PERSISTENTE: tutti i tentativi falliti con un errore
    transitorio. Chi lo riceve non scrive stati falsi: rinvia la lega-stagione."""

    def __init__(self, classe: str, tentativi: int, etichetta: str, ultimo: BaseException) -> None:
        self.classe = classe
        self.tentativi = tentativi
        self.etichetta = etichetta
        self.ultimo = ultimo
        super().__init__(f"{classe} persistente su {etichetta or 'PostgREST'} dopo {tentativi} "
                         f"tentativi: {descrivi_errore(ultimo)}")


def descrivi_errore(exc: BaseException) -> str:
    """Descrizione CORTA (la pagina HTML di Cloudflare e' lunga 7.800 caratteri)."""
    codice = getattr(exc, "code", None)
    messaggio = getattr(exc, "message", None)
    testo = f"{type(exc).__name__}"
    if codice is not None or messaggio is not None:
        testo += f" code={codice} message={messaggio}"
        dettagli = str(getattr(exc, "details", None) or "")
        i = dettagli.lower().find("<title>")
        if i >= 0:
            j = dettagli.lower().find("</title>", i)
            testo += f" pagina='{dettagli[i + 7:j if j > i else i + 120]}'"
        return testo[:300]
    return f"{testo}: {str(exc)[:200]}"


def _classe_di(exc: BaseException) -> Tuple[bool, Optional[str]]:
    """(decisivo, classe) per UNA eccezione della catena."""
    codice = getattr(exc, "code", None)
    if type(exc).__name__ == "APIError" and hasattr(exc, "details"):
        c = str(codice if codice is not None else "").strip()
        msg = str(getattr(exc, "message", None) or "")
        if c == "57014" or "statement timeout" in msg.lower():
            return True, None                           # R-CATCHUP-2, non qui
        if c.isdigit() and 500 <= int(c) <= 599:
            return True, "gateway"                      # 5xx / 520-524 senza JSON
        dettagli = (str(getattr(exc, "details", None) or "") + msg).lower()
        if "<!doctype html" in dettagli or "<html" in dettagli:
            return True, "gateway"                      # pagina HTML al posto del JSON
        if c in _CODICI_TRANSITORI or c.startswith("08"):
            return True, "gateway"
        return True, None                               # 4xx e applicativi: mai
    try:
        import httpx
    except ImportError:  # pragma: no cover - httpx e' una dipendenza di supabase
        httpx = None  # type: ignore[assignment]
    if httpx is not None:
        if isinstance(exc, httpx.RemoteProtocolError):
            return True, "connessione_terminata"        # GOAWAY/ConnectionTerminated, server disconnesso
        if isinstance(exc, httpx.TimeoutException):
            return True, "timeout_rete"                 # ConnectTimeout/ReadTimeout/WriteTimeout/PoolTimeout
        if isinstance(exc, httpx.NetworkError):
            return True, "connessione"                  # ConnectError/ReadError/WriteError/CloseError
    modulo = type(exc).__module__ or ""
    nome = type(exc).__name__
    if modulo.startswith("h2"):
        return True, "connessione_terminata"            # errori di protocollo HTTP/2 non mappati
    if modulo.startswith("httpcore"):
        if nome == "RemoteProtocolError":
            return True, "connessione_terminata"
        if nome.endswith("Timeout"):
            return True, "timeout_rete"
        if nome in ("ConnectError", "ReadError", "WriteError", "NetworkError"):
            return True, "connessione"
    return False, None


def classifica_guasto_rete(exc: Optional[BaseException]) -> Optional[str]:
    """'gateway' | 'connessione_terminata' | 'timeout_rete' | 'connessione', oppure None
    (da NON ritentare: 4xx, 57014, errori applicativi, qualunque altra cosa)."""
    visti = 0
    corrente = exc
    while corrente is not None and visti < 8:
        decisivo, classe = _classe_di(corrente)
        if decisivo:
            return classe
        succ = corrente.__cause__ if corrente.__cause__ is not None else corrente.__context__
        corrente = succ if succ is not corrente else None
        visti += 1
    return None


def rinnova_client() -> None:
    """Il prossimo get_supabase_client() di questo thread crea un client NUOVO (connessione
    HTTP/2 nuova). Il vecchio non si chiude: chi lo tiene ancora non deve trovarlo chiuso."""
    if getattr(_TLS, "client", None) is not None:
        _TLS.client = None
        STATISTICHE_RETE["rinnovi_client"] += 1


def _installa_contatore(client: Any) -> Optional[list]:
    """Conta le richieste HTTP del client PostgREST (hook di httpx). None se non si puo'."""
    contatore = [0]

    def _conta(_richiesta: Any) -> None:
        contatore[0] += 1
    try:
        client.postgrest.session.event_hooks["request"].append(_conta)
    except Exception:  # noqa: BLE001 - client finti o versioni diverse: niente rinnovo preventivo
        return None
    return contatore


def attiva_rinnovo_connessioni(ogni: Optional[int] = RINNOVO_DEFAULT) -> None:
    """Rinnovo preventivo del client ogni `ogni` richieste, per TUTTO il processo.
    Lo chiama solo il main del Seasons Catchup (i bot non cambiano)."""
    _STATO_RETE["rinnovo_ogni"] = int(ogni) if ogni and int(ogni) > 0 else None
    _TLS.client = None                                   # il prossimo nasce con il contatore


def _client_per(sb: Any) -> Any:
    """Il client da usare ORA: un client nato da get_supabase_client (o un ClientResiliente)
    si risolve nel client corrente del thread, che dopo un rinnovo e' quello nuovo; un
    oggetto qualsiasi (finti dei test, client altrui) resta se stesso."""
    if sb is None or isinstance(sb, ClientResiliente) or getattr(sb, "_db_client_prod", False) is True:
        return get_supabase_client()
    return sb


def con_ritentativi(fn: Callable[[], _T], *, etichetta: str = "",
                    attese: Sequence[float] = ATTESE_RETE_S,
                    dormi: Optional[Callable[[float], Any]] = None,
                    casuale: Optional[Callable[[], float]] = None) -> _T:
    """Esegue `fn` e la RIESEGUE (backoff esponenziale con jitter +-25%) SOLO sui guasti
    transitori di rete/gateway. Errore non transitorio -> risale subito, identico.
    Tutti i tentativi falliti -> GuastoRete (mai un traceback grezzo di httpx/postgrest).
    Su una connessione terminata il client del thread viene ricreato prima di ritentare
    (`fn` deve prendere il client con `_client_per`/`get_supabase_client` a ogni giro)."""
    dormi = dormi or _time.sleep                         # risolto qui: i test patchano time.sleep
    casuale = casuale or _random.random
    if _STATO_RETE["guasti_di_fila"] >= INTERRUTTORE_DOPO_GUASTI:
        attese = ()                                      # interruttore aperto: un tentativo solo
    totale = len(attese) + 1
    for i in range(totale):
        prima = getattr(_TLS, "dentro_ritentativi", False)
        _TLS.dentro_ritentativi = True                   # 09/10: il trasporto non ritenta qui sotto
        try:
            risultato = fn()
        except Exception as e:
            _TLS.dentro_ritentativi = prima
            classe = classifica_guasto_rete(e)
            if classe is None:
                raise
            STATISTICHE_RETE["per_classe"][classe] += 1
            if i + 1 >= totale:
                STATISTICHE_RETE["guasti_persistenti"] += 1
                _STATO_RETE["guasti_di_fila"] += 1
                _log_rete.error("[RETE] %s: %s PERSISTENTE dopo %d tentativi: %s", etichetta or "PostgREST",
                                classe, totale, descrivi_errore(e))
                raise GuastoRete(classe, totale, etichetta, e) from e
            if classe == "connessione_terminata":
                rinnova_client()
            attesa = float(attese[i]) * (0.75 + 0.5 * float(casuale()))
            STATISTICHE_RETE["ritentativi"] += 1
            _log_rete.warning("[RETE] %s: %s (tentativo %d/%d): %s -> ritento tra %.1f s%s",
                              etichetta or "PostgREST", classe, i + 1, totale, descrivi_errore(e), attesa,
                              " con un client NUOVO" if classe == "connessione_terminata" else "")
            dormi(attesa)
            continue
        _TLS.dentro_ritentativi = prima
        if i:
            STATISTICHE_RETE["riusciti_dopo_ritentativo"] += 1
        _STATO_RETE["guasti_di_fila"] = 0
        return risultato
    raise RuntimeError("non raggiungibile")  # pragma: no cover


def esegui_con_retry(query: Any, sb: Any = None, *, etichetta: str = "", **opzioni: Any) -> Any:
    """`.execute()` PostgREST con i ritentativi di `con_ritentativi`.

    query = FABBRICA ``lambda c: c.table(...)...`` (forma da preferire: a ogni tentativo
    il builder si ricostruisce sul client corrente, quindi sul client NUOVO dopo una
    connessione terminata) oppure un builder gia' fatto (si riesegue lo stesso: httpx
    scarta da solo la connessione chiusa). Solo per operazioni IDEMPOTENTI (letture,
    upsert, update, delete, RPC di lettura): un insert o una RPC che incrementa
    contatori va ritentata come unita' (per_fixture_backfill._sostituisci_righe,
    season_gaps.registra_esiti)."""
    if isinstance(query, _Catena):
        return query.execute()                           # ha gia' i suoi ritentativi
    if hasattr(query, "execute"):
        return con_ritentativi(query.execute, etichetta=etichetta, **opzioni)
    return con_ritentativi(lambda: query(_client_per(sb)).execute(), etichetta=etichetta, **opzioni)


# RPC che NON si possono riapplicare alla cieca (incrementano contatori): dal proxy si
# eseguono una volta sola, chi le chiama gestisce l'unita' (season_gaps.registra_esiti).
RPC_NON_IDEMPOTENTI = frozenset({"record_fixture_detail_checks"})


class _Catena:
    """Ricetta di una query PostgREST costruita su un ClientResiliente: registra i passi
    (attributi e chiamate) e all'`.execute()` li RIPETE sul client corrente a ogni
    tentativo. Un `insert` puro o una RPC non idempotente si esegue UNA volta sola."""

    __slots__ = ("_passi",)

    def __init__(self, passi: Tuple[Tuple[Any, ...], ...]) -> None:
        self._passi = passi

    def __getattr__(self, nome: str) -> "_Catena":
        if nome.startswith("__"):
            raise AttributeError(nome)
        return _Catena(self._passi + (("attr", nome),))

    def __call__(self, *args: Any, **kwargs: Any) -> "_Catena":
        return _Catena(self._passi + (("call", args, kwargs),))

    def _costruisci(self, client: Any) -> Any:
        oggetto = client
        for passo in self._passi:
            oggetto = getattr(oggetto, passo[1]) if passo[0] == "attr" else oggetto(*passo[1], **passo[2])
        return oggetto

    def _idempotente(self) -> bool:
        nomi = [p[1] for p in self._passi if p[0] == "attr"]
        if "insert" in nomi:
            return False
        for i, p in enumerate(self._passi[:-1]):
            if p == ("attr", "rpc"):
                succ = self._passi[i + 1]
                if succ[0] == "call" and succ[1] and succ[1][0] in RPC_NON_IDEMPOTENTI:
                    return False
        return True

    def execute(self) -> Any:
        etichetta = ".".join(str(p[1]) if p[0] == "attr" else (str(p[1][0]) if p[1] else "()")
                             for p in self._passi[:3])
        if not self._idempotente():
            return self._costruisci(get_supabase_client()).execute()
        return con_ritentativi(lambda: self._costruisci(get_supabase_client()).execute(), etichetta=etichetta)


class ClientResiliente:
    """Il client Supabase del Seasons Catchup: `table`/`from_`/`rpc`/`schema` restituiscono
    ricette che all'`.execute()` passano da `con_ritentativi`, sempre sul client CORRENTE
    del thread (quindi anche dopo un rinnovo). Copre senza toccarli i moduli della catena
    che ricevono `sb` (season_aggregates, season_backfill, api_quota). Il resto degli
    attributi va al client vero."""

    def __getattr__(self, nome: str) -> Any:
        if nome in ("table", "from_", "rpc", "schema"):
            return _Catena((("attr", nome),))
        if nome.startswith("__"):
            raise AttributeError(nome)
        return getattr(get_supabase_client(), nome)


def riepilogo_rete() -> str:
    """Una riga per il referto e il riepilogo del job."""
    s = STATISTICHE_RETE
    per_classe = ", ".join(f"{k} {v}" for k, v in sorted(s["per_classe"].items())) or "nessuno"
    return (f"ritentativi {s['ritentativi']} (riusciti dopo un ritentativo {s['riusciti_dopo_ritentativo']}), "
            f"guasti persistenti {s['guasti_persistenti']}, client rinnovati {s['rinnovi_client']}; "
            f"errori transitori per classe: {per_classe}")


# ---------------------------------------------------------------------------
# 09/10/2026 - RESILIENZA DI TRASPORTO PER LE ACTION (AUDIT_2026-10-09/fallimenti_action)
# ---------------------------------------------------------------------------
# Nelle ultime 300 run le rosse di Leagues Mapping (02, 03, 04/10), ML Post-Calibration
# (05/10) e Retrain/rechain (09/10) sono TUTTE una pagina HTML di Cloudflare (520/521/522)
# su UNA chiamata PostgREST senza ritentativo. Invece di avvolgere a mano le ~60
# `.execute()` dei 9 workflow, il client PostgREST dei processi delle ACTION ritenta al
# livello del trasporto httpx, con la STESSA politica di `con_ritentativi` (attese
# 2-4-8-16-32 s con jitter, log `[RETE]`, STATISTICHE_RETE, interruttore) piu' UN
# ritentativo lungo (ATTESA_LUNGA_ACTION_S). Si accende SOLO con `attiva_resilienza_action()`
# (lo chiama `esegui_main_action`, il `__main__` degli script delle action) o con
# `DB_RESILIENZA_ACTION=1` nell'ambiente (passi `python - <<PY` dei workflow): i bot non
# lo chiamano mai e restano identici.
#
# Cosa si ritenta (mai il 57014, mai un 4xx, mai un 500 JSON di PostgREST):
#   - richiesta NON consegnata all'origine (ConnectError/ConnectTimeout/PoolTimeout,
#     Cloudflare 521/522/523/525/526/530): sempre, qualunque metodo;
#   - esito AMBIGUO (520/524/502/503/504/527, 500 con pagina HTML, ReadTimeout, connessione
#     terminata): SOLO se la richiesta e' idempotente: GET/HEAD/OPTIONS/PUT/PATCH/DELETE,
#     upsert (Prefer: resolution=...), RPC di sola lettura (RPC_LETTURA_ACTION). Un insert
#     puro o una RPC che scrive non si ripete alla cieca (righe doppie, contatori).
# Persistente: il trasporto restituisce l'ultima risposta (o rilancia l'ultima eccezione),
# lo script fallisce come prima e `esegui_main_action` lo dichiara con una riga chiara.
ENV_RESILIENZA_ACTION = "DB_RESILIENZA_ACTION"
#: dopo le attese brevi, un'attesa lunga (il 09/10 il DB e' rimasto giu' ~26 minuti)
ATTESA_LUNGA_ACTION_S = 120.0
STATUS_NON_CONSEGNATA = frozenset({521, 522, 523, 525, 526, 530})
STATUS_AMBIGUI = frozenset({502, 503, 504, 520, 524, 527})
#: RPC che leggono soltanto (ritentabili anche su esito ambiguo)
RPC_LETTURA_ACTION = frozenset({"season_detail_gaps", "season_gaps_summary",
                                "season_aggregates_summary", "leagues_needing_retrain",
                                "get_direction", "fetch_missing_fixture_coverage"})
_METODI_IDEMPOTENTI = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "PATCH", "DELETE"})


def _attese_action() -> Tuple[float, ...]:
    lunga = _secondi_da_env("DB_RESILIENZA_ATTESA_LUNGA_S", ATTESA_LUNGA_ACTION_S)
    return tuple(ATTESE_RETE_S) + (lunga,)


def resilienza_action_attiva() -> bool:
    if _STATO_RETE.get("resilienza_action"):
        return True
    return (os.environ.get(ENV_RESILIENZA_ACTION) or "").strip().lower() in ("1", "true", "si", "on")


def attiva_resilienza_action() -> None:
    """Accende il trasporto resiliente per TUTTO il processo (il prossimo
    get_supabase_client crea un client nuovo che lo monta). Solo processi delle action."""
    _STATO_RETE["resilienza_action"] = True
    _TLS.client = None


def richiesta_idempotente(request: Any) -> bool:
    """True se rieseguire la richiesta PostgREST non cambia il risultato."""
    metodo = str(getattr(request, "method", "") or "").upper()
    if metodo in _METODI_IDEMPOTENTI:
        return True
    if metodo != "POST":
        return False
    path = str(getattr(getattr(request, "url", None), "path", "") or "")
    if "/rpc/" in path:
        return path.rsplit("/rpc/", 1)[1].strip("/") in RPC_LETTURA_ACTION
    prefer = str(request.headers.get("prefer", "") or "").lower()
    return "resolution=" in prefer                        # upsert (merge/ignore duplicates)


def classifica_risposta_action(status: int, content_type: str) -> Optional[str]:
    """'non_consegnata' | 'ambigua' | None (risposta da restituire cosi' com'e')."""
    if status in STATUS_NON_CONSEGNATA:
        return "non_consegnata"
    if status in STATUS_AMBIGUI:
        return "ambigua"
    if status == 500 and "html" in (content_type or "").lower():
        return "ambigua"                                  # pagina del gateway, non JSON di PostgREST
    return None


def classifica_eccezione_action(exc: BaseException) -> Optional[str]:
    """'non_consegnata' | 'ambigua' | None (da rilanciare subito)."""
    import httpx
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)):
        return "non_consegnata"
    if classifica_guasto_rete(exc) is not None:
        return "ambigua"
    return None


class TrasportoResiliente:
    """Avvolge il trasporto httpx del client PostgREST (``session._transport``) e ritenta i
    guasti di rete/gateway secondo le regole sopra. Le richieste fuori da /rest/v1/
    (storage, auth) passano intatte; dentro `con_ritentativi` (catchup) passa intatto,
    perche' li' ritenta gia' il livello di sopra."""

    def __init__(self, interno: Any, *, attese: Optional[Sequence[float]] = None,
                 dormi: Optional[Callable[[float], Any]] = None,
                 casuale: Optional[Callable[[], float]] = None) -> None:
        self._interno = interno
        self._attese = attese
        self._dormi = dormi
        self._casuale = casuale

    def handle_request(self, request: Any) -> Any:
        path = str(request.url.path or "")
        if "/rest/v1/" not in path or getattr(_TLS, "dentro_ritentativi", False):
            return self._interno.handle_request(request)
        attese = tuple(self._attese) if self._attese is not None else _attese_action()
        if _STATO_RETE["guasti_di_fila"] >= INTERRUTTORE_DOPO_GUASTI:
            attese = ()                                   # interruttore aperto: un tentativo solo
        dormi = self._dormi or _time.sleep
        casuale = self._casuale or _random.random
        idempotente = richiesta_idempotente(request)
        etichetta = f"{request.method} {path.split('/rest/v1/', 1)[1][:60]}"
        totale = len(attese) + 1
        for i in range(totale):
            try:
                risposta = self._interno.handle_request(request)
            except Exception as e:  # noqa: BLE001 - classificata sotto
                tipo = classifica_eccezione_action(e)
                if tipo is None or (tipo == "ambigua" and not idempotente):
                    raise
                classe = classifica_guasto_rete(e) or "connessione"
                descr = descrivi_errore(e)
                if i + 1 >= totale:
                    self._persistente(etichetta, classe, totale, descr)
                    raise
            else:
                tipo = classifica_risposta_action(risposta.status_code,
                                                  risposta.headers.get("content-type", ""))
                if tipo is None or (tipo == "ambigua" and not idempotente):
                    if i:
                        STATISTICHE_RETE["riusciti_dopo_ritentativo"] += 1
                    if tipo is None:
                        _STATO_RETE["guasti_di_fila"] = 0
                    return risposta
                classe = "gateway"
                descr = f"HTTP {risposta.status_code}"
                if i + 1 >= totale:
                    self._persistente(etichetta, classe, totale, descr)
                    return risposta
                risposta.close()
            STATISTICHE_RETE["per_classe"][classe] += 1
            STATISTICHE_RETE["ritentativi"] += 1
            attesa = float(attese[i]) * (0.75 + 0.5 * float(casuale()))
            _log_rete.warning("[RETE] %s: %s %s (tentativo %d/%d): %s -> ritento tra %.1f s",
                              etichetta, classe, tipo, i + 1, totale, descr, attesa)
            dormi(attesa)
        raise RuntimeError("non raggiungibile")  # pragma: no cover

    @staticmethod
    def _persistente(etichetta: str, classe: str, totale: int, descr: str) -> None:
        STATISTICHE_RETE["per_classe"][classe] += 1
        STATISTICHE_RETE["guasti_persistenti"] += 1
        _STATO_RETE["guasti_di_fila"] += 1
        _log_rete.error("[RETE] %s: %s PERSISTENTE dopo %d tentativi: %s", etichetta, classe,
                        totale, descr)

    def close(self) -> None:
        self._interno.close()

    def __enter__(self) -> "TrasportoResiliente":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def _installa_trasporto_resiliente(client: Any) -> bool:
    """Mette TrasportoResiliente sotto il client PostgREST. False se non si puo'."""
    try:
        sessione = client.postgrest.session
        if not isinstance(sessione._transport, TrasportoResiliente):
            sessione._transport = TrasportoResiliente(sessione._transport)
        return True
    except Exception:  # noqa: BLE001 - client finti o versioni diverse
        return False


def azzera_interruttore() -> None:
    """Richiude l'interruttore dei guasti di fila (dopo un'attesa lunga voluta: il
    prossimo tentativo ha di nuovo tutti i ritentativi brevi)."""
    _STATO_RETE["guasti_di_fila"] = 0


@_contextmanager
def ritentativi_del_chiamante():
    """09/10 (AUDIT_2026-10-09/fallimenti_action/ENRICH_RINVIO.md): dentro questo blocco il
    TrasportoResiliente NON ritenta (stesso segnale che usa `con_ritentativi`), perche' a
    ritentare e' il chiamante con la sua politica (attese, fetta, rinvio). Evita il doppio
    strato (7 tentativi del trasporto x N tentativi del chiamante). Fuori dal blocco nulla
    cambia; i bot non montano il trasporto resiliente e non lo usano."""
    prima = getattr(_TLS, "dentro_ritentativi", False)
    _TLS.dentro_ritentativi = True
    try:
        yield
    finally:
        _TLS.dentro_ritentativi = prima


def esegui_main_action(main: Callable[[], _T], nome: str) -> _T:
    """Il `__main__` degli script delle action: accende la resilienza di trasporto ed esegue
    `main`. Un guasto di rete/gateway rimasto dopo tutti i ritentativi diventa UNA riga
    chiara (log, annotazione ::error:: e riepilogo del job) + exit 1; il traceback resta,
    raccolto in un gruppo del log. Ogni altro errore risale identico (traceback normale)."""
    attiva_resilienza_action()
    try:
        return main()
    except Exception as e:  # noqa: BLE001 - classificata sotto
        classe = classifica_guasto_rete(e)
        if classe is None:
            raise
        import sys
        import traceback
        riga = (f"GUASTO DB PERSISTENTE ({classe}) in {nome}: {descrivi_errore(e)} "
                f"- rete PostgREST: {riepilogo_rete()}")
        print("::group::traceback del guasto (dettaglio)", flush=True)
        traceback.print_exc(file=sys.stdout)
        print("::endgroup::", flush=True)
        print(f"::error::{riga}", flush=True)
        print(riga, file=sys.stderr, flush=True)
        percorso = os.environ.get("GITHUB_STEP_SUMMARY")
        if percorso:
            try:
                with open(percorso, "a", encoding="utf-8") as fh:
                    fh.write(f"### GUASTO DB PERSISTENTE\n\n{riga}\n")
            except OSError:
                pass
        raise SystemExit(1) from None
