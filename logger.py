# logger.py
import atexit
import threading
from typing import Any, Dict, List, Optional

from db_client import get_supabase_client

# ------------------------------------------------------------------
# Buffer in-memory per api_call_log.
#
# I record sono IDENTICI a prima (stesse chiavi, stessi valori, stesso
# schema): cambia solo QUANDO vengono scritti — a blocchi di
# _FLUSH_EVERY record (1 INSERT batch invece di 1 INSERT per chiamata).
# Flush finale garantito via atexit + flush_api_log() esplicito.
#
# Trade-off accettato: se il processo crasha duro (kill/crash) si
# perdono al massimo gli ultimi _FLUSH_EVERY record non ancora
# flushati. api_call_log e' telemetria non-critica, quindi ok.
# ------------------------------------------------------------------
_FLUSH_EVERY = 50
_buffer: List[Dict[str, Any]] = []
_buffer_lock = threading.Lock()


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

    Il record viene bufferizzato in memoria e scritto a blocchi
    (vedi commento in testa al modulo); firma e record invariati.
    """
    try:
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

        with _buffer_lock:
            _buffer.append(record)
            should_flush = len(_buffer) >= _FLUSH_EVERY

        if should_flush:
            flush_api_log()
    except Exception as e:
        # Il logging NON deve rompere il programma principale
        print(f"[LOGGER] Errore nel log di api_call_log: {e}")


def flush_api_log() -> None:
    """
    Scrive su DB tutti i record bufferizzati (INSERT batch).
    NON solleva MAI eccezioni verso il chiamante (logging non-critico).
    In caso di errore sul batch, fallback riga-per-riga cosi' un
    singolo record problematico non fa perdere gli altri (stesso
    comportamento dell'INSERT singolo storico).
    """
    try:
        with _buffer_lock:
            if not _buffer:
                return
            records = _buffer[:]
            _buffer.clear()

        supabase = get_supabase_client()
        try:
            supabase.table("api_call_log").insert(records).execute()
        except Exception as batch_err:
            print(f"[LOGGER] Insert batch api_call_log fallito ({batch_err}); fallback riga-per-riga.")
            for rec in records:
                try:
                    supabase.table("api_call_log").insert(rec).execute()
                except Exception as e:
                    # Il logging NON deve rompere il programma principale
                    print(f"[LOGGER] Errore nel log di api_call_log: {e}")
    except Exception as e:
        print(f"[LOGGER] Errore nel flush di api_call_log: {e}")


# Flush finale garantito all'uscita del processo (exit normale).
atexit.register(flush_api_log)
