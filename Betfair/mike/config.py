"""config — whitelist parametri e costanti del bot Mike (COSTITUZIONE_MIKE.md §3).

La whitelist e' la barriera di sicurezza backend: SOLO queste chiavi, con questi
tipi/limiti/scelte, vengono applicate dai ``params`` che arrivano dalla UI.
Speculare alla whitelist frontend in ``frontend/src/lib/mike.ts``
(``MIKE_PARAM_FIELDS``). ``mode`` (paper|live) NON e' un parametro: vive in
``mike_control.mode`` e non passa mai da qui.

Pattern env: ``os.getenv(X, "").strip() or default`` (mai ``??``/``or`` su None).
"""
from __future__ import annotations

import os
from typing import Any, Callable, Optional

# Codici mercato Betfair delle due linee operate.
OU35 = "OVER_UNDER_35"
OU45 = "OVER_UNDER_45"
FOOTBALL_EVENT_TYPE_ID = "1"

# Selection id ATTESI (Under 3.5 / Over 4.5). Usati SOLO come assert-warn: la
# risoluzione avviene sempre PER NOME dal catalogo (catalogue.group_by_event).
# Nota: sulla linea 4.5 Betfair inverte l'ordine (Under 4.5 = 1222347).
EXPECTED_SEL = {"UNDER_35": 1222344, "OVER_35": 1222345,
                "OVER_45": 1222346, "UNDER_45": 1222347}

# customerStrategyRef (<=15 char) che marchia gli ordini Mike su Betfair.
CUSTOMER_STRATEGY_REF = "mike"

LOCK_PORT_DEFAULT = 47319


# ---------------------------------------------------------------------------
# Env helpers (pattern piattaforma: stringa vuota = assente)
# ---------------------------------------------------------------------------
def env_str(name: str, default: str) -> str:
    return os.getenv(name, "").strip() or default


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return int(default)
    try:
        return int(float(raw))
    except ValueError:
        return int(default)


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return float(default)
    try:
        return float(raw)
    except ValueError:
        return float(default)


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return bool(default)
    return raw in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Whitelist: chiave -> (default, cast, min, max, choices)
# choices != None => valore ammesso solo se in choices (min/max ignorati).
# ---------------------------------------------------------------------------
Spec = tuple[Any, Callable[[Any], Any], Optional[float], Optional[float], Optional[tuple]]

PARAM_SPEC: dict[str, Spec] = {
    # ---- generale ----
    "stake": (10.0, float, 0.50, 500.0, None),   # importo LIBERO (es. 1.23): sotto-minimo via place-and-trim
    "commission_pct": (5.0, float, 0.0, 20.0, None),
    "max_matches": (40, int, 1, 90, None),
    "entry_hours_before_ko": (3.0, float, 0.25, 12.0, None),
    "catalogue_refresh_s": (300, int, 60, 3600, None),
    "min_total_matched": (2000.0, float, 0.0, 1_000_000.0, None),
    "competition_filter": ("", str, None, None, None),
    "decide_min_interval_ms": (500, int, 100, 5000, None),
    "feed_max_age_s": (15.0, float, 3.0, 60.0, None),
    # ---- pre-match ----
    "pre_enabled": (True, bool, None, None, None),
    "pre_entry_price_min": (1.30, float, 1.01, 20.0, None),
    "pre_entry_price_max": (3.00, float, 1.01, 20.0, None),
    "pre_min_back_size_factor": (1.0, float, 0.5, 5.0, None),
    # ore prima del KO i book sono larghi: spread ampio ammesso (l'uscita non
    # attraversa lo spread: la lay viene APPOGGIATA e aspetta che il mercato scenda)
    "pre_max_spread_ticks": (6, int, 1, 20, None),
    "pre_green_ticks": (2, int, 1, 10, None),
    # resting = lay a +N tick appoggiata SUBITO dopo il fill dell'ingresso (profitto
    # spalmato, nessuno spread pagato); taker = chiude al best quando i tick ci sono
    "pre_exit_mode": ("resting", str, None, None, ("resting", "taker")),
    "pre_entry_ttl_s": (60, int, 5, 3600, None),
    "pre_max_cycles": (10, int, 0, 100, None),
    "pre_reentry_cooldown_s": (60, int, 0, 3600, None),
    "pre_last_entry_min": (10, int, 1, 120, None),
    "last_entry_persist": (True, bool, None, None, None),
    "last_entry_ticks_above": (0, int, 0, 3, None),
    "cancel_unmatched_after_ko_s": (120, int, 0, 900, None),
    # ---- copertura live ----
    "cover_enabled": (True, bool, None, None, None),
    "cover_profit_factor": (1.2, float, 1.0, 3.0, None),
    "cover_policy": ("auto", str, None, None, ("auto", "immediate", "wait")),
    "cover_wait_hazard_max": (0.08, float, 0.0, 1.0, None),
    "cover_wait_max_min": (15, int, 0, 45, None),
    "cover_wait_p4_max": (0.16, float, 0.0, 1.0, None),
    "cover_postgoal_delay_s": (45, int, 0, 300, None),
    "cover_max_goals": (2, int, 0, 4, None),
    "cover_rounding": ("ceil", str, None, None, ("ceil", "floor", "nearest")),
    "cover_max_overshoot_pct": (30.0, float, 0.0, 200.0, None),
    # importi ESATTI al centesimo (copertura 3.61, stake 1.23): sotto-minimo / fuori passo via
    # Betfair/stream/trading/submin.py (place-and-trim, come Bet Angel/Fairbot). False = legalizza .it
    "exact_sizes": (True, bool, None, None, None),
    # ---- cash-out globale ----
    "cashout_profit_pct": (5.0, float, 0.5, 50.0, None),
    "cashout_base": ("total", str, None, None, ("total", "under")),
    "cashout_place_at_ticks": (0, int, 0, 3, None),
    "close_retry_s": (10, int, 1, 600, None),
    "close_max_attempts": (20, int, 1, 100, None),
    # ---- uscite HT / 2T con perdita tollerata ----
    "ht_loss_exit_enabled": (True, bool, None, None, None),
    "ht_loss_pct": (25.0, float, 0.0, 100.0, None),
    "ht_loss_goals_min": (2, int, 0, 8, None),
    "ht_loss_goals_max": (4, int, 0, 8, None),
    "h2_loss_exit_enabled": (True, bool, None, None, None),
    "h2_loss_pct": (25.0, float, 0.0, 100.0, None),
    "h2_loss_from_min": (46, int, 45, 100, None),
    "h2_loss_to_min": (85, int, 45, 100, None),
    # ---- re-ingresso Under (gol + 3.5) ----
    "reentry_enabled": (True, bool, None, None, None),
    "reentry_green_ticks": (2, int, 1, 10, None),
    "reentry_max_goals": (1, int, 0, 1, None),
    "reentry_until_min": (45, int, 0, 100, None),
    "reentry_exit_until_min": (80, int, 0, 100, None),
    "reentry_price_min_over_entry": (True, bool, None, None, None),
    "reentry_hold_if_loss": (False, bool, None, None, None),
    "stream_extra_lines": (False, bool, None, None, None),
    # ---- settlement / rischio ----
    "settle_confirm_s": (60, int, 0, 600, None),
    "max_open_matches": (10, int, 1, 90, None),
    "daily_loss_stop": (50.0, float, 0.0, 100_000.0, None),
    "max_liability_per_match": (0.0, float, 0.0, 100_000.0, None),
    "event_loss_cap_pct": (100.0, float, 0.0, 500.0, None),
    "skip_log_interval_s": (300, int, 10, 3600, None),
}

DEFAULTS: dict[str, Any] = {k: v[0] for k, v in PARAM_SPEC.items()}


def _coerce(key: str, raw: Any) -> Any:
    default, cast, lo, hi, choices = PARAM_SPEC[key]
    try:
        if cast is bool:
            if isinstance(raw, str):
                val = raw.strip().lower() in ("1", "true", "yes", "on")
            else:
                val = bool(raw)
        elif cast is str:
            val = str(raw).strip()
        else:
            val = cast(raw)
    except (TypeError, ValueError):
        return default
    if choices is not None:
        return val if val in choices else default
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        if lo is not None and val < lo:
            val = lo if cast is float else int(lo)
        if hi is not None and val > hi:
            val = hi if cast is float else int(hi)
    return val


# coppie (min, max) che devono restare ordinate: se invertite tornano ENTRAMBE
# al default (fail-closed dichiarato, mai una finestra vuota silenziosa)
_ORDERED_PAIRS = (
    ("pre_entry_price_min", "pre_entry_price_max"),
    ("ht_loss_goals_min", "ht_loss_goals_max"),
    ("h2_loss_from_min", "h2_loss_to_min"),
    ("reentry_until_min", "reentry_exit_until_min"),
)


def merge_params(raw: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Default + SOLO le chiavi note, con cast, clamp e scelte. Chiavi ignote scartate.
    Le coppie min/max invertite tornano al default (review F0, MEDIUM #8)."""
    out = dict(DEFAULTS)
    if not raw:
        return out
    for key, value in raw.items():
        if key not in PARAM_SPEC or value is None:
            continue
        out[key] = _coerce(key, value)
    for lo_key, hi_key in _ORDERED_PAIRS:
        if out[lo_key] > out[hi_key]:
            out[lo_key] = DEFAULTS[lo_key]
            out[hi_key] = DEFAULTS[hi_key]
    return out


def commission_rate(params: dict[str, Any]) -> float:
    return float(params.get("commission_pct", DEFAULTS["commission_pct"])) / 100.0
