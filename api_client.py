# api_client.py
import time
import requests
from typing import Any, Dict, Optional
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, API_FOOTBALL_KEY
from logger import log_api_call

API_BASE = "https://v3.football.api-sports.io"

def _int_o_none(valore: Any) -> Optional[int]:
    try:
        return int(str(valore).strip())
    except (TypeError, ValueError):
        return None


class APIFootballClient:
    def __init__(self):
        self.base_url = API_BASE
        # 25/09/2026 - quota: richieste HTTP fatte da QUESTO client (ogni tentativo,
        # retry compresi: API-Football conta le richieste, non le "chiamate logiche")
        # e ultimi header di quota giornaliera letti dalla risposta. Letti da
        # api_quota.GestoreQuota; la firma di call() non cambia.
        self.richieste_http = 0
        self.ultimo_ratelimit: Optional[Dict[str, Any]] = None
        self.session = requests.Session()
        self.session.headers.update({
            "x-apisports-key": API_FOOTBALL_KEY,
            "Accept": "application/json"
        })

    def call(self, endpoint: str, params: Optional[Dict[str, Any]] = None, max_retries: int = 3) -> Dict[str, Any]:
        """
        Chiamata robusta con:
        - gestione retry
        - exponential backoff
        - gestione 429 con Retry-After
        - protezione contro JSON vuoti o troncati
        - logging di ogni tentativo su DB Supabase nella tabella api_call_log
        """
        method = "GET"
        start_time = None
        attempt = 0
        retry_done = 0

        while True:
            attempt += 1
            if start_time is None:
                start_time = time.time()

            try:
                self.richieste_http += 1
                resp = self.session.get(self.base_url + endpoint, params=params, timeout=30)
                http_status = resp.status_code
                self._leggi_header_quota(resp, endpoint)
                duration_ms = int((time.time() - start_time) * 1000)

                # Rate limit 429
                if http_status == 429:
                    retry_after = int(resp.headers.get("Retry-After", "5"))
                    print(f"[API] 429 Rate Limited → attendo {retry_after}s prima di retry...")
                    retry_done += 1
                    log_api_call(method, endpoint, params, "rate_limited", http_status, "429 Retry-After", duration_ms, 0, retry_done)
                    time.sleep(retry_after)
                    retry_done += 1
                    if attempt > max_retries:
                        return {}
                    continue

                # Errori HTTP non 2xx
                if not resp.ok:
                    error_message = resp.text[:200]
                    print(f"[API] HTTP Error {http_status} → retry {attempt}/{max_retries}")
                    log_api_call(method, endpoint, params, "error", http_status, error_message, duration_ms, 0, retry_done)
                    if attempt < max_retries:
                        wait = 2 ** attempt
                        print(f"[API] Attendo {wait}s (backoff) e ritento...")
                        time.sleep(wait)
                        continue
                    return {}

                # Parsing JSON (potenzialmente rotto)
                try:
                    data = resp.json()
                except ValueError as e:
                    print(f"[API] JSON malformato o troncato → retry {attempt}/{max_retries}")
                    error_message = str(e)
                    log_api_call(method, endpoint, params, "invalid_json", http_status, error_message, duration_ms, 0, retry_done)
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)
                        continue
                    return {}

                # Protezione JSON vuoti/incompleti
                if not data:
                    print(f"[API] JSON vuoto/incompleto da endpoint: {endpoint}")
                    log_api_call(method, endpoint, params, "empty", http_status, "JSON input vuoto o response null", duration_ms, 0, retry_done)
                    return {}

                # Size risposta
                response_size = len(resp.text)

                # Logga successo finale
                log_api_call(method, endpoint, params, "success", http_status, None, duration_ms, response_size, retry_done)

                return data

            except requests.RequestException as e:
                duration_ms = 0 if start_time is None else int((time.time() - start_time) * 1000)
                print(f"[API] Network error → retry {attempt}/{max_retries}: {e}")
                log_api_call(method, endpoint, params, "network_error", None, str(e)[:200], duration_ms, 0, retry_done)
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    retry_done += 1
                    continue
                return {}

    def _leggi_header_quota(self, resp: Any, endpoint: str) -> None:
        """Header di quota GIORNALIERA di API-Football (x-ratelimit-requests-*).
        Non solleva mai: un header assente o strano non deve fermare la chiamata."""
        try:
            headers = getattr(resp, "headers", None) or {}
            limite = _int_o_none(headers.get("x-ratelimit-requests-limit"))
            rimaste = _int_o_none(headers.get("x-ratelimit-requests-remaining"))
            if limite is None or rimaste is None:
                return
            self.ultimo_ratelimit = {"limit_day": limite, "remaining": rimaste,
                                     "at": time.time(), "endpoint": endpoint}
            # Log a campione (1a richiesta e poi ogni 50) o sempre sotto 500 rimaste.
            if self.richieste_http % 50 == 1 or rimaste < 500:
                print(f"[API] quota giornaliera: {limite - rimaste}/{limite} usate, rimaste {rimaste} ({endpoint})")
        except Exception as e:  # pragma: no cover - difensivo
            print(f"[API] header di quota non leggibili: {e}")

    def get_leagues(self):
        """ Wrapper diretto per chiamare /leagues """
        return self.call("/leagues")
