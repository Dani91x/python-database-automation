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
    """Ritorna il client Supabase del THREAD corrente (creato pigramente)."""
    voluto = _STATO["timeout"]
    client = getattr(_TLS, "client", None)
    if client is not None and getattr(_TLS, "timeout", None) is voluto:
        return client
    if voluto is None:
        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    else:
        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
                               options=ClientOptions(postgrest_client_timeout=voluto))
    _TLS.client = client
    _TLS.timeout = voluto
    return client
