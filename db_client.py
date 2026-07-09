# db_client.py
import threading

from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

# A1 (fix WinError 10035): client PER-THREAD, non più singleton condiviso.
# Il runner flumine ha molti BackgroundWorker concorrenti (ladder, score, ordini,
# risk, xhedge, daily-stop…): un unico client condiviso significa contesa sullo
# stesso pool di connessioni httpx sincrone — sotto picco in-play su Windows le
# scritture fallivano a raffica con [WinError 10035] (WSAEWOULDBLOCK).
# Un client per thread = ogni worker ha le sue connessioni. I thread del runner
# sono pochi e longevi → nessuna crescita incontrollata di client.
_TLS = threading.local()


def get_supabase_client() -> Client:
    """Ritorna il client Supabase del THREAD corrente (creato pigramente)."""
    client = getattr(_TLS, "client", None)
    if client is None:
        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        _TLS.client = client
    return client
