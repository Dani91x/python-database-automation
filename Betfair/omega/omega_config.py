"""omega_config — default e whitelist parametri (COSTITUZIONE_OMEGA.md §7).

La whitelist è la barriera di sicurezza backend: solo queste chiavi, con questi
tipi/limiti, vengono applicate dai ``params`` che arrivano dalla UI. Speculare
alla whitelist frontend in ``frontend/src/lib/omega.ts``.
"""
from __future__ import annotations

from typing import Any, Callable

# Obiettivo giornaliero di default (colonna dedicata su omega_control).
DEFAULT_DAILY_GOAL = 250.0

# eventTypeId Betfair per il calcio.
FOOTBALL_EVENT_TYPE_ID = "1"

# customerStrategyRef (<=15 char) che marchia gli ordini Omega su Betfair.
CUSTOMER_STRATEGY_REF = "omega"


# (default, cast, min, max) — min/max None = non vincolato.
_SPEC: dict[str, tuple[Any, Callable[[Any], Any], float | None, float | None]] = {
    "price_min": (20.0, float, 1.01, 1000.0),
    "price_max": (120.0, float, 1.01, 1000.0),
    "entry_minute_min": (30, int, 0, 130),
    "entry_minute_max": (60, int, 0, 130),
    "max_events": (0, int, 0, 1000),
    "commission_pct": (5.0, float, 0.0, 20.0),
    "min_lay_liquidity": (5.0, float, 0.0, 100000.0),
    "min_stake": (0.5, float, 0.5, 1000.0),
    "include_aggregate": (False, bool, None, None),
    "stop_on_goal": (True, bool, None, None),
    "entry_window_source": ("score", str, None, None),  # 'score' (minuto+punteggio da live_now condiviso) | 'clock'
    "poll_interval_s": (20, int, 5, 600),
    "max_liability_per_match": (0.0, float, 0.0, 1_000_000.0),
    "daily_loss_cap": (0.0, float, 0.0, 1_000_000.0),
    "max_open_liability": (0.0, float, 0.0, 10_000_000.0),
}

DEFAULTS: dict[str, Any] = {k: v[0] for k, v in _SPEC.items()}


def _coerce(key: str, raw: Any) -> Any:
    default, cast, lo, hi = _SPEC[key]
    try:
        if cast is bool:
            val = bool(raw) if not isinstance(raw, str) else raw.strip().lower() in ("1", "true", "yes", "on")
        else:
            val = cast(raw)
    except (TypeError, ValueError):
        return default
    if key == "entry_window_source" and val not in ("score", "clock"):
        return default
    if lo is not None and isinstance(val, (int, float)) and val < lo:
        val = lo if cast is float else int(lo)
    if hi is not None and isinstance(val, (int, float)) and val > hi:
        val = hi if cast is float else int(hi)
    return val


def resolve_params(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Applica la whitelist: default + solo le chiavi note, coerce e clamp.

    Chiavi sconosciute vengono ignorate (I5/§7). ``price_min`` non può
    superare ``price_max`` (in tal caso si scambiano).
    """
    out = dict(DEFAULTS)
    if raw:
        for k, v in raw.items():
            if k in _SPEC:
                out[k] = _coerce(k, v)
    if out["price_min"] > out["price_max"]:
        out["price_min"], out["price_max"] = out["price_max"], out["price_min"]
    if out["entry_minute_min"] > out["entry_minute_max"]:
        out["entry_minute_min"], out["entry_minute_max"] = (
            out["entry_minute_max"],
            out["entry_minute_min"],
        )
    return out
