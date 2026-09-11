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
    # Esecuzione via coda flumine (DEMO=LIVE, §6-bis): 'auto' = coda del runner
    # quando il gate passa (fallback legacy sempre disponibile) | 'rest' = forza
    # il percorso legacy (fill snapshot in paper, place REST FOK in live).
    "execution_mode": ("auto", str, None, None),
    # TTL quasi-FOK del place paper via flumine: senza fill sufficiente entro
    # questo tempo si accoda il cancel del residuo (vedi COSTITUZIONE §6).
    # SOLO PAPER: in live il FOK vero lo esegue Betfair (timeInForce).
    "paper_fill_ttl_s": (45, int, 5, 600),
    # KILL-SWITCH del LIVE via coda flumine (§6-bis LIVE, 2026-07-17): True =
    # il place live passa dalla coda del runner (book streamato + fill
    # dall'order stream, timeInForce=FILL_OR_KILL); False = live legacy puro
    # (place REST FOK diretto + riconciliazione polling), senza log di fallback.
    "omega_live_via_flumine": (True, bool, None, None),
    # hard deadline (s) dell'esito FOK live dallo specchio: oltre, il poll
    # riconcilia via REST (per bet_id) o revoca la richiesta mai presa in
    # carico — mai un pending live zombie.
    "live_fill_deadline_s": (20, int, 5, 300),
    # ---- OMEGA v2 (09/09 sera): 2 gambe per partita, selezione per MODELLO ----
    # 'legs' = HT-CS nel 1T + CS nel 2T sul risultato con probabilità di modello
    # più bassa | 'single' = motore v1 (una gamba CS, quota più alta) kill-switch
    "engine": ("legs", str, None, None),
    "ht_entry_min": (20, int, 0, 45),      # finestra gamba 1T (minuto reale dal feed)
    "ht_entry_max": (40, int, 0, 45),
    "ft_entry_min": (50, int, 45, 130),    # finestra gamba 2T
    "ft_entry_max": (80, int, 45, 130),
    "model_p_max_pct": (2.0, float, 0.01, 50.0),   # P(modello) massima del risultato layato
    "model_min_goal_distance": (2, int, 1, 5),     # gol AGGIUNTIVI minimi dal punteggio corrente
    # P di modello CALIBRATA nella selezione (Betfair/safe_strategy/calibration.py,
    # import guardato): 'auto' = usa il calibratore se c'è | 'off' = P grezza.
    "model_calibration": ("auto", str, None, None),
    "model_calibration_path": ("", str, None, None),   # vuoto = default del calibratore
    # ---- §14 (11/09): seconda gamba SEMPRE coperta, dati capillari ----
    # 'veto' = per la gamba 2T la P usata è max(P modello, P empirica HT→FT dai
    # dati storici, se il punteggio è ancora quello del 45′) | 'off' = solo modello
    "model_empirical": ("veto", str, None, None),
    # minuto massimo d'ingresso 2T entro cui il veto HT→FT si applica (la
    # tabella HT→FT copre tutto il 2° tempo: oltre sovrastimerebbe la P);
    # con la tabella PER MINUTO (§15) il veto vale a ogni minuto, per entrambe le gambe
    "model_empirical_max_minute": (60, int, 45, 90),
    # ---- §15: modello definitivo ----
    # λ impliciti nell'INTERO mercato (scala CS + linee O/U) quando fixture, λ
    # salvati e pre-KO mancano; sempre calcolati per l'audit (cross-check)
    "lambda_market_grid": (True, bool, None, None),
    # selezione con COSTO DI COPERTURA: fra i risultati a P equivalente (entro
    # band_ratio × la più bassa) vince il più economico da coprire subito
    "select_cost_aware": (True, bool, None, None),
    "select_p_band_ratio": (2.0, float, 1.0, 10.0),
    # cartellini gialli dal feed nei tassi residui (moltiplicatori calibrati per lega)
    "model_use_yellow_cards": (True, bool, None, None),
    # fattore di coda (§15): P del modello ≤ 5 % moltiplicata per questo valore
    # (banco di validazione 11/09: 1,1–1,8 secondo minuto e campione → 1,3; usato SOLO
    # se il calibratore condiviso non ha una tabella per la famiglia; 1 = nessuna correzione)
    "model_tail_factor": (1.3, float, 0.5, 5.0),
    # λ dal mercato Over/Under live quando mancano fixture e quote pre-KO
    # (scanner riavviato a partita in corso, lega senza fixture): True = mai
    # una gamba saltata per "no_model_lambdas" se il mercato a gol è in stream
    "lambda_live_fallback": (True, bool, None, None),
    # §16 — incertezza sui λ (coefficiente di variazione della mistura lognormale:
    # 0 = Poisson puro; 0,30 ≈ coda binomiale negativa osservata sui dati)
    "model_lambda_cv": (0.30, float, 0.0, 1.0),
    # §16 — selezione conservativa: P = centro log-pool (modello ∥ mercato) + k·SE;
    # 0 = solo il centro (raccomandato finché il banco non misura la SE)
    "select_k_se": (0.0, float, 0.0, 3.0),
    # §16 — ranking EV: P di dover coprire (costo del green-up) e peso del costo
    "select_p_hedge": (0.5, float, 0.0, 1.0),
    "select_ev_kappa": (1.0, float, 0.0, 5.0),
    # ---- GREEN-UP AUTOMATICO (10/09, §12): la scommessa diventa un trade ----
    "greenup_enabled": (True, bool, None, None),
    "greenup_mode": ("auto", str, None, None),          # 'auto' | 'off'
    "greenup_trigger_distance": (1, int, 0, 3),         # bancato raggiungibile con ≤ N gol → uscita
    "greenup_price_trigger_ratio": (0.5, float, 0.05, 1.0),  # lay ≤ ratio × ingresso → valutazione
    "greenup_settle_delay_s": (30, int, 0, 600),        # assestamento del mercato dopo un gol
    "greenup_hold_max_risk": (0.02, float, 0.0, 1.0),   # P(perdita) ≤ → si tiene
    "greenup_risk_cap": (0.15, float, 0.0, 1.0),        # P(perdita) ≥ → si esce (caso vivo 10/09: 0.12 → tengo)
    "greenup_ev_margin": (0.10, float, 0.0, 1000.0),    # EUR: bloccato ≥ EV(tengo) − margine → esce
    "greenup_take_profit_frac": (0.9, float, 0.1, 1.0), # cash-out blocca ≥ frac dello stake…
    "greenup_take_profit_minute": (80, int, 0, 130),    # …dal minuto → take-profit
    "greenup_retry_s": (20, int, 2, 600),               # cooldown fra tentativi (residuo/errore)
    "greenup_max_attempts": (15, int, 0, 100),          # cap tentativi per posizione
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
    if key == "execution_mode" and val not in ("auto", "rest"):
        return default
    if key == "engine" and val not in ("legs", "single"):
        return default
    if key in ("greenup_mode", "model_calibration") and val not in ("auto", "off"):
        return default
    if key == "model_calibration_path":
        return str(val).strip()
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
    for lo_k, hi_k in (("ht_entry_min", "ht_entry_max"), ("ft_entry_min", "ft_entry_max")):
        if out[lo_k] > out[hi_k]:
            out[lo_k], out[hi_k] = out[hi_k], out[lo_k]
    if out["entry_minute_min"] > out["entry_minute_max"]:
        out["entry_minute_min"], out["entry_minute_max"] = (
            out["entry_minute_max"],
            out["entry_minute_min"],
        )
    # green-up: la soglia di "margine ampio" non può superare il cap di rischio
    if out["greenup_hold_max_risk"] > out["greenup_risk_cap"]:
        out["greenup_hold_max_risk"] = out["greenup_risk_cap"]
    return out
