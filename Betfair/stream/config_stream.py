"""Costanti di configurazione del sottosistema Stream live.

Tutti i valori sovrascrivibili da .env (prefisso LIVE_). Default conservativi,
coerenti col piano (cadenza ~10s, fallback a 3 fallimenti, archivio solo locale).
"""
from __future__ import annotations

import os
from typing import Optional

# Carica .env in modo ROBUSTO: alcune costanti qui sotto (es. LIVE_ORDER_MODE,
# BETFAIR_JURISDICTION) sono lette con os.getenv AL MOMENTO DELL'IMPORT. Senza questo,
# il valore nel .env verrebbe visto solo se un altro modulo ha già chiamato load_dotenv
# prima — fragile. Caricandolo qui, "LIVE_ORDER_MODE=PAPER" nel .env è SEMPRE rispettato.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # noqa: BLE001 - dotenv opzionale; l'env reale ha comunque precedenza
    pass

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
# profondità del ladder per lato (livelli best offers) conservata e sottoscritta.
# 10 = massimo best-offers Betfair → matching "taker" realistico anche su stake
# grossi che sfondano più livelli. Il volume tradato per-prezzo (trd) è sempre full.
LADDER_DEPTH: int = int(os.getenv("LIVE_LADDER_DEPTH", "10"))
# chunk di righe per upsert (come db_adapter del progetto)
UPLOAD_CHUNK: int = int(os.getenv("LIVE_UPLOAD_CHUNK", "500"))

# ----------------------------------------------------------------------------
# Ladder LIVE (pubblicazione per-mercato su live_ladder dal ladder_worker)
# ----------------------------------------------------------------------------
# Cadenza (secondi, FLOAT) del BackgroundWorker che pubblica la ladder piena su
# live_ladder. WRITE-ON-CHANGE: anche a cadenza fitta, una ladder immutata NON viene
# riscritta (firma back/lay/trd/ltp) → I/O DB contenuto (incidente Supabase 2026-06-13).
# default 2.0s: equilibrio reattività/I/O. In-play un mercato liquido cambia book quasi ad
# ogni tick → con molti eventi simultanei 1.0s satura le scritture (storia I/O Supabase).
# Abbassa a 1.0 solo con pochi mercati; alza a 3.0+ per molte partite contemporanee.
LADDER_PUBLISH_SEC: float = float(os.getenv("LIVE_LADDER_PUBLISH_SEC", "2.0"))
# Livelli back/lay conservati per selezione nella ladder pubblicata. Default = LADDER_DEPTH
# (stessa profondita' sottoscritta dallo stream): non ha senso pubblicare piu' livelli di
# quelli ricevuti. Il volume tradato per-prezzo (trd) resta sempre FULL.
LADDER_MAX_LEVELS: int = int(os.getenv("LIVE_LADDER_MAX_LEVELS", str(LADDER_DEPTH)))
# Livelli vicino al best usati per il calcolo del Weight of Money (pressione rosa/blu).
LADDER_WOM_LEVELS: int = int(os.getenv("LIVE_LADDER_WOM_LEVELS", "3"))

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
# size minima disponibile al prezzo perché un segnale sia AZIONABILE (controparte reale):
# evita segnali su mercati illiquidi/quote-fantasma, dove l'edge del modello è inaffidabile.
SIGNAL_MIN_LIQUIDITY: float = float(os.getenv("LIVE_SIGNAL_MIN_LIQUIDITY", "50"))

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

# ----------------------------------------------------------------------------
# Live trading ordini — coda comandi + esecuzione (paper/reale) nel runner
# ----------------------------------------------------------------------------
# Modalità di esecuzione ordini del runner (governa la costruzione del client flumine
# in build_order_client e l'attivazione di LiveTradingStrategy + live_order_worker):
#   OFF   = nessun ordine. order_stream=False, paper_trade=False → IDENTICO ad oggi,
#           ZERO regressioni: niente strategia ordini, niente worker coda.
#   PAPER = simulazione su dati di mercato live (paper_trade=True → SimulatedExecution).
#           Soldi FINTI, nessun ordine reale inviato a Betfair.
#   LIVE  = ORDINI REALI sull'Exchange (order_stream=True). SOLDI VERI — money-critical.
# Default OFF: il runner si comporta esattamente come prima finché non si sceglie.
LIVE_ORDER_MODE: str = os.getenv("LIVE_ORDER_MODE", "OFF").strip().upper()

# Giurisdizione del conto Betfair → regole di stake minimo (live_order_build.min_stake_rules).
# 'it' = Italian Exchange (back min EUR2.00 step EUR0.50; lay size min EUR0.50).
BETFAIR_JURISDICTION: str = os.getenv("LIVE_BETFAIR_JURISDICTION", "it").strip().lower()

# Cadenza del BackgroundWorker che svuota la coda ordini (UN passo per giro): basso =
# latenza minima tra comando dal frontend e place/cancel/replace effettivo.
LIVE_ORDER_QUEUE_POLL_SEC: float = float(os.getenv("LIVE_ORDER_QUEUE_POLL_SEC", "1.0"))
# righe pending lette per giro (batch della coda betfair_live_order_requests)
LIVE_ORDER_QUEUE_BATCH: int = int(os.getenv("LIVE_ORDER_QUEUE_BATCH", "5"))

# Conflazione lato server dell'order stream LIVE (ms): 0 = fill grezzi, max reattività
# (lo specchio DB è write-on-change, quindi non stressa il DB anche a 0).
ORDER_STREAM_CONFLATE_MS: int = int(os.getenv("LIVE_ORDER_STREAM_CONFLATE_MS", "0"))
# Latenza simulata (ms) della SimulatedExecution in PAPER: rende il fill paper più
# realistico (Betfair ha sempre un ritardo). Solo PAPER; ignorato in OFF/LIVE.
PAPER_SIMULATED_LATENCY_MS: int = int(os.getenv("LIVE_PAPER_SIMULATED_LATENCY_MS", "120"))

# Tetto di stake per SINGOLO ordine. SCELTA UTENTE 2026-07-01: NESSUN cap di default
# (importi liberi, come nei tool pro). Il cap è OPT-IN: attivo solo se ``LIVE_MAX_STAKE_PER_ORDER``
# è impostato a un numero > 0 nell'env; vuoto/0/assente = nessun limite (None). Resta SEMPRE
# attiva, indipendentemente da questo, la guardia di PAYOUT massimo €10.000 (regola Betfair .it,
# non un cap sullo stake) applicata in live_order_build. Un cap più stretto può comunque essere
# passato per-ordine via ``params.max_stake``.
# NB: costante valutata UNA volta all'import (valore d'avvio); per il valore EFFETTIVO usare
# ``live_max_stake_per_order()`` (rilegge l'env ad ogni chiamata).
_raw_max_stake = os.getenv("LIVE_MAX_STAKE_PER_ORDER", "").strip()
LIVE_MAX_STAKE_PER_ORDER: "Optional[float]" = (
    float(_raw_max_stake) if _raw_max_stake and float(_raw_max_stake) > 0 else None
)
# Kill-switch globale: se true il worker NON processa alcun ordine (freno d'emergenza).
# Anch'esso valutato all'import: per il valore LIVE usare ``live_kill_switch()`` (vedi sotto).
LIVE_KILL_SWITCH: bool = os.getenv("LIVE_KILL_SWITCH", "false").strip().lower() == "true"

# Tetto NATIVO di transazioni/ora del client flumine (controllo MaxTransactionCount,
# registrato di default da flumine in add_client). È una guardia anti-runaway: se per un bug
# il worker tentasse un flusso anomalo di place/cancel/replace, il control rifiuta oltre soglia.
# Default 1000: ben SOTTO la soglia Betfair di 5000 transazioni/ora oltre cui scattano gli
# addebiti per "unmatched bets" sull'Exchange → conservativo per un conto .it piccolo e per il
# trading manuale one-click. Alzabile via env se servisse più throughput (max utile 5000).
LIVE_TRANSACTION_LIMIT: int = int(os.getenv("LIVE_TRANSACTION_LIMIT", "1000"))


def live_order_mode() -> str:
    """Mode operativa (OFF|PAPER|LIVE) RI-LETTA dall'env ad OGNI chiamata (non congelata).

    Money-critical: come il kill-switch, un DOWNGRADE di sicurezza (LIVE→PAPER/OFF) deve
    avere effetto SENZA riavviare il runner. Il worker la rilegge ad ogni ciclo: esportare
    ``LIVE_ORDER_MODE=OFF`` (o PAPER) blocca/declassa i place al giro successivo. La costante
    ``LIVE_ORDER_MODE`` qui sopra resta solo come valore d'avvio. Default OFF = zero ordini.
    """
    return os.getenv("LIVE_ORDER_MODE", "OFF").strip().upper()


def live_kill_switch() -> bool:
    """Kill-switch RI-LETTO dall'env ad OGNI chiamata (non congelato all'import).

    Money-critical: il kill-switch è un freno d'emergenza e DEVE poter essere attivato
    senza riavviare il runner. Il worker lo interroga ad ogni ciclo: basta esportare
    ``LIVE_KILL_SWITCH=true`` nell'ambiente del processo per bloccare ogni place al giro
    successivo. La costante ``LIVE_KILL_SWITCH`` qui sopra resta solo come valore d'avvio.
    """
    return os.getenv("LIVE_KILL_SWITCH", "false").strip().lower() == "true"


def live_max_stake_per_order() -> Optional[float]:
    """Cap di stake per singolo ordine RI-LETTO dall'env ad OGNI chiamata. ``None`` = NESSUN cap.

    SCELTA UTENTE 2026-07-01: default NESSUN limite (importi liberi). Il cap è OPT-IN: si
    attiva solo esportando ``LIVE_MAX_STAKE_PER_ORDER=<n>`` con n>0 (stringe il tetto a
    runtime, senza riavvio). Vuoto/0/non numerico → None (nessun cap). Resta comunque attiva
    la guardia payout €10.000 in live_order_build e l'eventuale ``params.max_stake`` per-ordine.
    """
    raw = os.getenv("LIVE_MAX_STAKE_PER_ORDER", "").strip()
    if not raw:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return val if val > 0 else None


# ----------------------------------------------------------------------------
# Risk engine (Fase 3): worker che monitora prezzi/esposizioni e chiude/copre le
# posizioni secondo regole ARMATE (offset / stop-loss / take-profit / trailing).
# ----------------------------------------------------------------------------
# Cadenza (secondi, FLOAT) del BackgroundWorker risk_engine_worker. Basso = reazione più
# pronta di stop/trailing (ma resta software-side: se il processo cade, gli stop non esistono).
RISK_ENGINE_POLL_SEC: float = float(os.getenv("LIVE_RISK_ENGINE_POLL_SEC", "1.0"))
# righe (regole armate) lette per giro.
RISK_ENGINE_BATCH: int = int(os.getenv("LIVE_RISK_ENGINE_BATCH", "20"))

# ----------------------------------------------------------------------------
# Hedging cross-market (#9): cadenza del worker che calcola l'analisi P&L per-scoreline
# per evento e la scrive in betfair_live_xhedge (sola lettura, display). Lenta: l'analisi
# non deve essere ad alta frequenza.
# ----------------------------------------------------------------------------
XHEDGE_POLL_SEC: float = float(os.getenv("LIVE_XHEDGE_POLL_SEC", "5.0"))

# ----------------------------------------------------------------------------
# E34 — stop giornaliero di conto: cadenza del daily_stop_worker (P&L di giornata
# da settled + MTM blotter; kill-switch automatico oltre daily_loss_limit).
# La soglia vive in betfair_live_settings.daily_loss_limit (runtime, NULL = off).
# ----------------------------------------------------------------------------
DAILY_STOP_POLL_SEC: float = float(os.getenv("LIVE_DAILY_STOP_POLL_SEC", "5.0"))

# ----------------------------------------------------------------------------
# A2/A5 — riconciliazione col conto Betfair + heartbeat runner.
# ----------------------------------------------------------------------------
RECONCILE_POLL_SEC: float = float(os.getenv("LIVE_RECONCILE_POLL_SEC", "30.0"))
HEARTBEAT_SEC: float = float(os.getenv("LIVE_HEARTBEAT_SEC", "10.0"))
