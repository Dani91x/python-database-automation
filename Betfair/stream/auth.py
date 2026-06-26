"""Costruzione dell'APIClient betfairlightweight (cert login .it).

Riusa le credenziali già in config.py (stesse del client REST esistente).
betfairlightweight gestisce locale='italy' → endpoint identitysso-cert.betfair.it.
"""
from __future__ import annotations

import logging
from typing import Optional

import betfairlightweight

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

    client = betfairlightweight.APIClient(
        username=BETFAIR_USERNAME,
        password=BETFAIR_PASSWORD,
        app_key=BETFAIR_APP_KEY,
        locale="italy",  # → identitysso-cert.betfair.it
        cert_files=(BETFAIR_CERT_FILE, BETFAIR_KEY_FILE),
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


def safe_logout(client: Optional[betfairlightweight.APIClient]) -> None:
    if client is None:
        return
    try:
        client.logout()
    except Exception as e:  # noqa: BLE001
        logger.debug("[stream-auth] logout ignorato: %s", e)
