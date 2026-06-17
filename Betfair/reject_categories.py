"""
reject_categories.py
Classifica il testo del motivo di scarto di un segnale in una CATEGORIA stabile,
usata sia dal backfill storico sia dalla pipeline live per popolare
engine_signals.reject_filter.

Funzione pura, nessun I/O. Le categorie sono pensate per aggregare in v_es_reject_funnel.
"""
from __future__ import annotations
import re

# Categorie canoniche
INSUFFICIENT_DATA   = "insufficient_data"
ODDS_BELOW_FLOOR    = "odds_below_floor"
EDGE_BELOW          = "edge_below_threshold"
PROB_BELOW          = "prob_below_threshold"
EDGE_AND_PROB       = "edge_and_prob"
PROB_BELOW_IMPLIED  = "prob_below_implied"      # ML: prob < implied+margin
MODEL_UNRELIABLE    = "model_unreliable_bss"
SCORE_BELOW_TIER    = "score_below_tier"
BELOW_BEST_NO_STAKE = "below_best_no_stake"      # candidato valido ma stake 0 / non scelto
NO_VALUE            = "no_value"                 # nessun value bet trovato
NO_AI_DATA          = "no_ai_data"
SAFETY_STAKE_ZERO   = "safety_stake_zero"        # filtri di sicurezza azzerano lo stake
OTHER               = "other"


def classify_reject_reason(reason: str | None) -> str:
    """Mappa un testo-motivo nella categoria canonica. Robusto a maiuscole/None."""
    if not reason:
        return OTHER
    r = reason.lower()

    # combinazioni esplicite prima dei singoli
    has_edge = "edge" in r and "min" in r
    has_prob_min = bool(re.search(r"prob\s*\d", r)) and ("min" in r or "implied" in r)

    if "implied" in r and "margin" in r:
        return PROB_BELOW_IMPLIED
    if "dati insufficienti" in r:
        return INSUFFICIENT_DATA
    if "min_odds" in r or ("quota" in r and "min" in r):
        return ODDS_BELOW_FLOOR
    if "bss" in r or "near-random" in r or "near random" in r:
        return MODEL_UNRELIABLE
    if "score" in r and ("min" in r or "tier" in r):
        return SCORE_BELOW_TIER
    if has_edge and has_prob_min:
        return EDGE_AND_PROB
    if has_edge:
        return EDGE_BELOW
    if has_prob_min:
        return PROB_BELOW
    if "nessun dato ai" in r:
        return NO_AI_DATA
    if "nessun value bet" in r or "no_signal" in r or "no signal" in r:
        return NO_VALUE
    if "below best" in r:
        return BELOW_BEST_NO_STAKE
    if "safety" in r:
        return SAFETY_STAKE_ZERO
    return OTHER
