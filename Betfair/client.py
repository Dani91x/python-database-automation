# Betfair/client.py
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests

from config import (
    BETFAIR_APP_KEY,
    BETFAIR_USERNAME,
    BETFAIR_PASSWORD,
    BETFAIR_CERT_FILE,
    BETFAIR_KEY_FILE,
    BETFAIR_IDENTITY_URL,
)

logger = logging.getLogger(__name__)


class BetfairAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class BetfairAuthSession:
    session_token: str
    login_status: str


class BetfairClient:
    """
    Betfair (Italia) - Client minimale e robusto:
    1) Login non-interactive via certificato (certlogin .it)
    2) Chiamate Betting API via JSON-RPC con X-Application + X-Authentication

    Riferimenti doc ufficiale (headers + endpoints JSON-RPC): :contentReference[oaicite:1]{index=1}
    """

    # Betting API JSON-RPC endpoint (Global Exchange)
    BETTING_RPC_URL = "https://api.betfair.com/exchange/betting/json-rpc/v1"

    def __init__(
        self,
        app_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        cert_file: Optional[str] = None,
        key_file: Optional[str] = None,
        identity_url: Optional[str] = None,
        timeout: int = 30,
    ):
        self.app_key = (app_key or BETFAIR_APP_KEY or "").strip()
        self.username = (username or BETFAIR_USERNAME or "").strip()
        self.password = (password or BETFAIR_PASSWORD or "").strip()
        self.cert_file = (cert_file or BETFAIR_CERT_FILE or "").strip()
        self.key_file = (key_file or BETFAIR_KEY_FILE or "").strip()
        self.identity_url = (identity_url or BETFAIR_IDENTITY_URL or "").strip()
        self.timeout = timeout

        self._http = requests.Session()
        self._session_token: Optional[str] = None

        self._validate()

    def _validate(self) -> None:
        missing = []
        if not self.app_key:
            missing.append("BETFAIR_APP_KEY")
        if not self.username:
            missing.append("BETFAIR_USERNAME")
        if not self.password:
            missing.append("BETFAIR_PASSWORD")
        if not self.cert_file:
            missing.append("BETFAIR_CERT_FILE")
        if not self.key_file:
            missing.append("BETFAIR_KEY_FILE")
        if not self.identity_url:
            missing.append("BETFAIR_IDENTITY_URL")
        if missing:
            raise BetfairAuthError("Configurazione Betfair incompleta: " + ", ".join(missing))

    @property
    def session_token(self) -> Optional[str]:
        return self._session_token

    # =========================
    # AUTH (cert login IT)
    # =========================
    def login_cert(self, max_retries: int = 3) -> BetfairAuthSession:
        """
        Login non-interactive via certificato su endpoint .it:
        - POST x-www-form-urlencoded: username, password
        - Header: X-Application, Accept, Content-Type
        - TLS client cert: cert=(cert_file, key_file)

        Se loginStatus == SUCCESS, salva sessionToken in memoria.
        """
        headers = {
            "X-Application": self.app_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        data = {"username": self.username, "password": self.password}
        cert: Tuple[str, str] = (self.cert_file, self.key_file)

        last_err: Optional[str] = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = self._http.post(
                    self.identity_url,
                    headers=headers,
                    data=data,
                    cert=cert,
                    timeout=self.timeout,
                )

                if not resp.ok:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:250]}"
                    logger.warning("[Betfair] certlogin KO (%s/%s): %s", attempt, max_retries, last_err)
                    time.sleep(2 ** attempt)
                    continue

                try:
                    payload = resp.json()
                except ValueError:
                    last_err = f"Risposta non JSON: {resp.text[:250]}"
                    logger.warning("[Betfair] certlogin non-JSON (%s/%s): %s", attempt, max_retries, last_err)
                    time.sleep(2 ** attempt)
                    continue

                login_status = str(payload.get("loginStatus") or "").upper()
                session_token = payload.get("sessionToken")

                if login_status != "SUCCESS" or not session_token:
                    safe_payload = {k: payload.get(k) for k in ("loginStatus", "error", "errorDescription")}
                    last_err = f"Login non SUCCESS: {safe_payload}"
                    logger.warning("[Betfair] certlogin non SUCCESS (%s/%s): %s", attempt, max_retries, last_err)
                    time.sleep(2 ** attempt)
                    continue

                self._session_token = str(session_token)
                logger.info("[Betfair] certlogin SUCCESS: sessionToken acquisito.")
                return BetfairAuthSession(session_token=self._session_token, login_status=login_status)

            except requests.RequestException as e:
                last_err = f"Network error: {e}"
                logger.warning("[Betfair] certlogin network (%s/%s): %s", attempt, max_retries, last_err)
                time.sleep(2 ** attempt)

        raise BetfairAuthError(f"Login Betfair cert fallito dopo {max_retries} tentativi. Ultimo errore: {last_err}")

    def logout_local(self) -> None:
        """
        Reset locale del token in memoria.
        (Logout SSO remoto si può implementare più avanti se necessario.)
        """
        self._session_token = None

    # =========================
    # BETTING API (JSON-RPC)
    # =========================
    def _betting_headers(self) -> Dict[str, str]:
        if not self._session_token:
            raise BetfairAuthError("Nessun session_token. Esegui prima login_cert().")

        return {
            "X-Application": self.app_key,
            "X-Authentication": self._session_token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def betting_rpc(
        self,
        method: str,
        params: Dict[str, Any],
        request_id: int = 1,
        max_retries: int = 3,
    ) -> Any:
        """
        Chiamata JSON-RPC alla Betting API.
        method es: "SportsAPING/v1.0/listEventTypes"
        """
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": request_id,
        }

        last_err: Optional[str] = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = self._http.post(
                    self.BETTING_RPC_URL,
                    headers=self._betting_headers(),
                    data=json.dumps(payload),
                    timeout=self.timeout,
                )

                if not resp.ok:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:250]}"
                    logger.warning("[Betfair] betting_rpc KO (%s/%s): %s", attempt, max_retries, last_err)
                    time.sleep(2 ** attempt)
                    continue

                data = resp.json()

                # JSON-RPC error object
                if isinstance(data, dict) and data.get("error"):
                    last_err = f"RPC error: {data.get('error')}"
                    logger.warning("[Betfair] betting_rpc error (%s/%s): %s", attempt, max_retries, last_err)
                    time.sleep(2 ** attempt)
                    continue

                return data.get("result") if isinstance(data, dict) else data

            except requests.RequestException as e:
                last_err = f"Network error: {e}"
                logger.warning("[Betfair] betting_rpc network (%s/%s): %s", attempt, max_retries, last_err)
                time.sleep(2 ** attempt)
            except ValueError as e:
                last_err = f"Invalid JSON: {e}"
                logger.warning("[Betfair] betting_rpc invalid JSON (%s/%s): %s", attempt, max_retries, last_err)
                time.sleep(2 ** attempt)

        raise RuntimeError(f"Betting RPC failed after {max_retries} retries. Last error: {last_err}")

    # =========================
    # CONVENIENCE METHODS
    # =========================
    def list_events(self, event_type_ids: list[str], days_ahead: int = 1) -> Any:
        """
        Ritorna la lista degli eventi (partite) per i prossimi X giorni.
        """
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        end_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 86400 * days_ahead))

        params = {
            "filter": {
                "eventTypeIds": event_type_ids,
                "marketStartTime": {"from": now_utc, "to": end_utc},
            }
        }
        return self.betting_rpc(method="SportsAPING/v1.0/listEvents", params=params)

    def list_market_catalogue(
        self,
        event_ids: list[str],
        market_types: list[str] = ["MATCH_ODDS"],
        max_results: int = 200,
    ) -> Any:
        """
        Ritorna i cataloghi dei mercati per una lista di eventi.
        Supporta il batching naturale dell'API (più eventIds).
        """
        params = {
            "filter": {
                "eventIds": event_ids,
                "marketTypeCodes": market_types,
            },
            "maxResults": max_results,
            "marketProjection": ["MARKET_START_TIME", "EVENT"],
        }
        return self.betting_rpc(method="SportsAPING/v1.0/listMarketCatalogue", params=params)

    def list_market_book(
        self,
        market_ids: list[str],
        price_projection: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Ritorna i dati reali (quote) per una lista di mercati.
        """
        if price_projection is None:
            price_projection = {
                "priceData": ["EX_BEST_OFFERS"],
                "virtualise": "true"
            }

        params = {
            "marketIds": market_ids,
            "priceProjection": price_projection,
        }
        return self.betting_rpc(method="SportsAPING/v1.0/listMarketBook", params=params)
