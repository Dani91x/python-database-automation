# logger.py
from typing import Any, Dict, Optional
from db_client import get_supabase_client

def log_api_call(
    method: str,
    endpoint: str,
    params: Optional[Dict[str, Any]],
    status: str,
    http_status: Optional[int],
    error_message: Optional[str],
    duration_ms: Optional[int],
    response_size: Optional[int],
    retry_attempts: int,
) -> None:
    """
    Logga una chiamata API nella tabella api_call_log.

    Questa funzione NON deve mai bloccare il flusso principale:
    se il log fallisce, stampa solo l'errore in console.
    """
    try:
        supabase = get_supabase_client()

        record: Dict[str, Any] = {
            "method": method,
            "endpoint": endpoint,
            "params": params,
            "status": status,
            "http_status": http_status,
            "error_message": error_message,
            "duration_ms": duration_ms,
            "response_size": response_size,
            "retry_attempts": retry_attempts,
        }

        supabase.table("api_call_log").insert(record).execute()
    except Exception as e:
        # Il logging NON deve rompere il programma principale
        print(f"[LOGGER] Errore nel log di api_call_log: {e}")
