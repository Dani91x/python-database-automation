# db_client.py
import threading

from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

_supabase: Client | None = None
_supabase_lock = threading.Lock()

def get_supabase_client() -> Client:
    """Ritorna un client Supabase singleton (thread-safe: il server HTTP del runner
    può chiamarlo da thread concorrenti)."""
    global _supabase
    if _supabase is None:
        with _supabase_lock:
            if _supabase is None:
                _supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _supabase
