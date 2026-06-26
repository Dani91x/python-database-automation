"""Costanti di configurazione del sottosistema Stream live.

Tutti i valori sovrascrivibili da .env (prefisso LIVE_). Default conservativi,
coerenti col piano (cadenza ~10s, fallback a 3 fallimenti, archivio solo locale).
"""
from __future__ import annotations

import os

# ----------------------------------------------------------------------------
# Storage locale (source of truth del firehose grezzo, formato nativo Betfair)
# ----------------------------------------------------------------------------
DATA_DIR: str = os.getenv(
    "LIVE_STREAM_DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "_live_raw"),
)

# ----------------------------------------------------------------------------
# Punteggio (poller + circuit breaker)
# ----------------------------------------------------------------------------
SCORE_POLL_SEC: float = float(os.getenv("LIVE_SCORE_POLL_SEC", "5"))
# fallimenti consecutivi del provider primario prima di passare al fallback
FALLBACK_THRESHOLD: int = int(os.getenv("LIVE_FALLBACK_THRESHOLD", "3"))
# ogni quanti secondi ritentare il primario quando il circuito è aperto (half-open)
FALLBACK_RETRY_PRIMARY_SEC: float = float(os.getenv("LIVE_FALLBACK_RETRY_PRIMARY_SEC", "120"))

# ----------------------------------------------------------------------------
# Curazione / upload
# ----------------------------------------------------------------------------
# intervallo minimo (secondi) tra due snapshot conservati per lo STESSO mercato
# (write-on-change con throttle): riduce le righe senza perdere la dinamica.
UPLOAD_CADENCE_SEC: float = float(os.getenv("LIVE_UPLOAD_CADENCE_SEC", "10"))
# dimensione massima del ladder per lato conservata in DB (livelli best offers)
LADDER_DEPTH: int = int(os.getenv("LIVE_LADDER_DEPTH", "3"))
# chunk di righe per upsert (come db_adapter del progetto)
UPLOAD_CHUNK: int = int(os.getenv("LIVE_UPLOAD_CHUNK", "500"))

# ----------------------------------------------------------------------------
# Stream
# ----------------------------------------------------------------------------
# conflazione lato server (ms): 0 = nessuna, gli aggiornamenti arrivano grezzi.
# Tenuto basso per la dinamica; la curazione dirada poi in scrittura DB.
STREAM_CONFLATE_MS: int = int(os.getenv("LIVE_STREAM_CONFLATE_MS", "0"))
# TUTTI i tipi di dato del mercato (registra ogni singola cosa quando è live):
# ladder completo + traded + traded volume + LTP + market definition + starting price.
STREAM_FIELDS: tuple[str, ...] = (
    "EX_ALL_OFFERS",   # ladder completo (tutti i livelli back/lay)
    "EX_TRADED",       # volume scambiato per prezzo
    "EX_TRADED_VOL",   # volume scambiato totale
    "EX_LTP",          # last traded price
    "EX_MARKET_DEF",   # market definition (status, inplay, betDelay, ...)
    "SP_TRADED",       # starting price - matched
    "SP_PROJECTED",    # starting price - proiettato
)

# ----------------------------------------------------------------------------
# Registrazione nativa raw (per FlumineSimulation / Backtest Automatico)
# ----------------------------------------------------------------------------
# Scrive anche il formato nativo Betfair (righe mcm) oltre al JSONL parsato.
# Stessa subscription (tee nel listener) → nessuna connessione/sub aggiuntiva.
RAW_RECORDING: bool = os.getenv("LIVE_RAW_RECORDING", "true").lower() == "true"

# ----------------------------------------------------------------------------
# Motore segnali live (F2)
# ----------------------------------------------------------------------------
SIGNALS_ENABLED: bool = os.getenv("LIVE_SIGNALS_ENABLED", "true").lower() == "true"
BANKROLL: float = float(os.getenv("LIVE_BANKROLL", "100"))
SIGNAL_MIN_EDGE: float = float(os.getenv("LIVE_SIGNAL_MIN_EDGE", "0.03"))
KELLY_FRACTION: float = float(os.getenv("LIVE_KELLY_FRACTION", "0.25"))

# ----------------------------------------------------------------------------
# Sottoscrizione automatica (F3)
# ----------------------------------------------------------------------------
WATCHLIST_POLL_SEC: float = float(os.getenv("LIVE_WATCHLIST_POLL_SEC", "120"))
RESUBSCRIBE_DEBOUNCE_SEC: float = float(os.getenv("LIVE_RESUBSCRIBE_DEBOUNCE_SEC", "20"))
MIN_RESUBSCRIBE_INTERVAL_SEC: float = float(os.getenv("LIVE_MIN_RESUBSCRIBE_INTERVAL_SEC", "60"))

# ----------------------------------------------------------------------------
# Finalize / auto-stop (F4)
# ----------------------------------------------------------------------------
FINALIZE_POLL_SEC: float = float(os.getenv("LIVE_FINALIZE_POLL_SEC", "10"))
# jitter/distanziamento tra upload di eventi che finiscono insieme (anti-stress DB)
FINALIZE_SPACING_SEC: float = float(os.getenv("LIVE_FINALIZE_SPACING_SEC", "8"))

# ----------------------------------------------------------------------------
# Limiti Betfair / multi-match (F5) — NO BAN
# ----------------------------------------------------------------------------
# soglia mercati totali oltre cui AVVISARE (WARN), e tetto oltre cui RIFIUTARE.
SAFE_MARKET_THRESHOLD: int = int(os.getenv("LIVE_SAFE_MARKET_THRESHOLD", "250"))
HARD_MARKET_CAP: int = int(os.getenv("LIVE_HARD_MARKET_CAP", "400"))
BACKOFF_BASE_SEC: float = float(os.getenv("LIVE_BACKOFF_BASE_SEC", "5"))
BACKOFF_MAX_SEC: float = float(os.getenv("LIVE_BACKOFF_MAX_SEC", "300"))

# ----------------------------------------------------------------------------
# Archivio cloud (opzionale, predisposto ma non attivo: scelta utente 2026-06-26)
# ----------------------------------------------------------------------------
ARCHIVE_BUCKET: str = os.getenv("LIVE_ARCHIVE_BUCKET", "")  # vuoto = solo locale
