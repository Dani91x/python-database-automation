"""
MASTER BACKTEST v1 — Poisson + ML
Analisi completa su dati storici reali dal DB Supabase.

Fonti dati:
  - fixture_predictions.db_json_analisi  → probabilità Poisson
  - fixture_predictions.model_predictions_json → probabilità ML (out-of-sample reali)
  - fixture_predictions.raw_json_odds    → quote Betfair pre-partita
  - matches                              → risultati HT/FT reali

Metriche calcolate per ogni market:
  - N scommesse piazzate
  - Hit rate (% vittorie)
  - Break-even rate richiesta
  - ROI netto (dopo commissione Betfair 5%)
  - P&L su bankroll simulato
  - Max drawdown
  - Edge/Vol ratio (per-bet mean/std — NON uno Sharpe annualizzato)
  - Calibrazione: Brier score, log-loss, reliability buckets, bias (pred vs reale)

Uso:
  python master_backtest.py
  python master_backtest.py --from 2025-01-01
  python master_backtest.py --leagues 39,135,78
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 0 — CONFIGURAZIONE
# Modifica qui per cambiare i parametri della simulazione
# ─────────────────────────────────────────────────────────────────────────────

BANKROLL: float = 1000.0           # bankroll iniziale simulato (€)
KELLY_FRACTION: float = 0.10       # Kelly frazionato (stesso di money_management.py)
MAX_STAKE_PCT: float = 0.02        # max stake = 2% bankroll
MIN_EDGE: float = 0.05             # min EV post-commissione (5%)
BETFAIR_COMMISSION: float = 0.05   # 5% su profitto netto
MIN_PROB_GLOBAL: float = 0.40      # prob minima globale per qualsiasi scommessa

# ── Safety-filter constants — ALLINEATE a money_management.py (Edge Engine v3.0) ──
# Replichiamo i filtri live così che il backtest non gonfi count/volume/PnL:
#   - Hallucination Filter (Z-Score): blocca prob troppo ottimiste vs mercato.
#   - League Trust Score: scala lo stake per affidabilità storica della lega.
OVERROUND_CORRECTION: float = 0.975          # money_management.py:109
DEFAULT_DIVERGENCE_STD: float = 0.3287       # money_management.py:113 (fallback)
POISSON_Z_THRESHOLD: float = 2.0             # money_management.py:837 (track poisson)
USE_DYNAMIC_CAL: bool = True                 # mirror EDGE_ENGINE_FLAGS in money_management.py for the period being backtested
USE_HALLUCINATION_FILTER: bool = True        # mirror EDGE_ENGINE_FLAGS in money_management.py for the period being backtested

# Soglie minime per Poisson (per mercato) — ALLINEATE a money_management.py MARKET_MAP
POISSON_MIN_PROB: Dict[str, float] = {
    "1x2_H":      0.54,   # live: min_prob=0.54
    "1x2_D":      0.35,   # live: min_prob=0.35
    "1x2_A":      0.54,   # live: min_prob=0.54
    "over_2_5":   0.58,   # live: min_prob=0.58
    "under_2_5":  0.54,   # live: min_prob=0.54
    "over_1_5":   0.65,   # live: min_prob=0.65
    "under_1_5":  0.55,   # live: min_prob=0.55
    "over_3_5":   0.40,   # live: min_prob=0.40
    "under_3_5":  0.58,   # live: min_prob=0.58
    "btts_yes":   0.58,   # live: min_prob=0.58
    "btts_no":    0.54,   # live: min_prob=0.54
    "ht_over_0_5": 0.62,
}

# min_edge per mercato Poisson — ALLINEATE a money_management.py MARKET_MAP
POISSON_MIN_EDGE: Dict[str, float] = {
    "1x2_H":      0.06,   # live: 6%
    "1x2_D":      0.07,   # live: 7%
    "1x2_A":      0.06,   # live: 6%
    "over_2_5":   0.07,   # live: 7%
    "under_2_5":  0.05,   # live: 5%
    "over_1_5":   0.06,   # live: 6%
    "under_1_5":  0.06,   # live: 6%
    "over_3_5":   0.06,   # live: 6%
    "under_3_5":  0.05,   # live: 5%
    "btts_yes":   0.08,   # live: 8%
    "btts_no":    0.07,   # live: 7%
    "ht_over_0_5": 0.05,  # live: 5%
}

# Soglie minime per ML (per target)
ML_MIN_PROB: Dict[str, float] = {
    "target_1x2":           0.45,
    "target_over_2_5":      0.55,
    "target_over_1_5":      0.60,
    "target_over_3_5":      0.50,
    "target_over_4_5":      0.50,
    "target_btts":          0.55,
    "target_ht_1x2":        0.45,
    "target_ft_1x2":        0.45,
    "target_clean_sheet_home": 0.55,
    "target_clean_sheet_away": 0.55,
    "target_home_over_0_5": 0.60,
    "target_away_over_0_5": 0.60,
    "target_home_over_1_5": 0.55,
    "target_away_over_1_5": 0.55,
}

# ML Score tiers: score = edge × √prob
ML_SCORE_TIERS: List[Tuple[float, float]] = [
    (2.5,  0.025),
    (4.0,  0.040),
    (6.0,  0.055),
    (999., 0.075),
]

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 0b — CALIBRAZIONE POISSON
# Copia esatta di money_management.py::CALIBRATION_TABLE
# bin_idx = int(prob * 10), capped a 9
# correction_factor = hit_rate_reale / prob_media_nel_bin (derivato da 24k+ match)
# Mercati estesi (O15/U15/O35/U35/HT_*) aggiunti 2026-03-30: calibrazione
# neutrale 1.0 finché update_poisson_calibration.py non accumula dati storici.
# ─────────────────────────────────────────────────────────────────────────────

POISSON_CALIBRATION_TABLE: Dict[str, Dict[int, float]] = {
    # Aggiornato 2026-03-30 da 16,097 match DC (255,247 campioni) — update_poisson_calibration.py
    "H":       {0: 0.358, 1: 0.672, 2: 1.113, 3: 1.046, 4: 1.018, 5: 1.028, 6: 1.017, 7: 1.140, 8: 1.087, 9: 1.0  },
    "D":       {0: 1.0,   1: 0.679, 2: 0.927, 3: 0.960, 4: 0.622, 5: 1.0,   6: 1.0,   7: 1.0,   8: 1.0,   9: 1.0  },
    "A":       {0: 1.183, 1: 0.957, 2: 1.058, 3: 0.982, 4: 0.997, 5: 1.075, 6: 1.148, 7: 1.259, 8: 1.0,   9: 1.0  },
    "O25":     {0: 1.0,   1: 1.620, 2: 1.081, 3: 1.179, 4: 1.017, 5: 0.940, 6: 0.893, 7: 0.920, 8: 0.893, 9: 1.0  },
    "U25":     {0: 1.0,   1: 1.529, 2: 1.227, 3: 1.192, 4: 1.073, 5: 0.986, 6: 0.900, 7: 0.974, 8: 0.875, 9: 1.0  },
    "BTTS":    {0: 1.0,   1: 1.0,   2: 1.207, 3: 1.068, 4: 1.028, 5: 0.929, 6: 0.815, 7: 0.785, 8: 0.882, 9: 1.0  },
    "BTTS_NO": {0: 1.0,   1: 1.566, 2: 1.593, 3: 1.332, 4: 1.086, 5: 0.977, 6: 0.963, 7: 0.924, 8: 1.0,   9: 1.0  },
    "HT05":    {0: 1.0,   1: 1.0,   2: 2.660, 3: 1.744, 4: 1.317, 5: 1.121, 6: 1.047, 7: 0.934, 8: 0.843, 9: 0.860},
    "O15":     {0: 1.0,   1: 1.0,   2: 1.0,   3: 1.115, 4: 1.007, 5: 1.049, 6: 1.025, 7: 0.943, 8: 0.921, 9: 0.944},
    "U15":     {0: 1.682, 1: 1.419, 2: 1.174, 3: 0.952, 4: 0.937, 5: 0.994, 6: 0.934, 7: 1.0,   8: 1.0,   9: 1.0  },
    "O35":     {0: 1.377, 1: 1.334, 2: 1.023, 3: 0.911, 4: 0.801, 5: 0.879, 6: 0.845, 7: 0.815, 8: 1.0,   9: 1.0  },
    "U35":     {0: 1.0,   1: 1.0,   2: 1.458, 3: 1.275, 4: 1.151, 5: 1.156, 6: 1.046, 7: 0.992, 8: 0.937, 9: 0.971},
    "HT_H":    {0: 1.759, 1: 1.268, 2: 1.104, 3: 0.991, 4: 1.009, 5: 1.044, 6: 1.206, 7: 1.0,   8: 1.0,   9: 1.0  },
    "HT_D":    {0: 1.0,   1: 1.0,   2: 0.682, 3: 0.925, 4: 0.957, 5: 0.946, 6: 0.911, 7: 1.0,   8: 1.0,   9: 1.0  },
    "HT_A":    {0: 1.349, 1: 1.140, 2: 1.017, 3: 0.958, 4: 0.983, 5: 1.261, 6: 1.0,   7: 1.0,   8: 1.0,   9: 1.0  },
    "HT_U05":  {0: 2.576, 1: 1.839, 2: 1.197, 3: 0.911, 4: 0.848, 5: 0.729, 6: 0.600, 7: 0.370, 8: 1.0,   9: 1.0  },
}

# Mappa: market key backtest → cal_key nella tabella
POISSON_CAL_KEY: Dict[str, str] = {
    "1x2_H":       "H",
    "1x2_D":       "D",
    "1x2_A":       "A",
    "over_2_5":    "O25",
    "under_2_5":   "U25",
    "over_1_5":    "O15",
    "under_1_5":   "U15",
    "over_3_5":    "O35",
    "under_3_5":   "U35",
    "btts_yes":     "BTTS",
    "btts_no":      "BTTS_NO",
    "ht_over_0_5":  "HT05",
    "ht_under_0_5": "HT_U05",
}


# ── Dynamic calibration (dynamic_cal.json) + Trust scores (league_trust_scores.json) ──
# Caricati una volta all'avvio per replicare ESATTAMENTE la chain del live system
# (money_management.SlotManager._apply_calibration / _apply_safety_filters).
_DYNAMIC_CAL: Optional[Dict[str, Any]] = None
_TRUST_SCORES: Optional[Dict[str, float]] = None
_DIVERGENCE_STD: float = DEFAULT_DIVERGENCE_STD


def load_dynamic_data() -> None:
    """Carica dynamic_cal.json e league_trust_scores.json dalla repo root.
    Replica money_management.SlotManager._load_dynamic_data: stessa validazione di
    struttura (chiavi richieste) e stesso fallback su tabella statica/σ di default."""
    global _DYNAMIC_CAL, _TRUST_SCORES, _DIVERGENCE_STD
    base = os.path.dirname(os.path.abspath(__file__))

    # --- Dynamic Calibration ---
    cal_path = os.path.join(base, "dynamic_cal.json")
    _DYNAMIC_CAL = None
    if os.path.exists(cal_path):
        try:
            with open(cal_path, "r", encoding="utf-8") as f:
                _cal_raw = json.load(f)
            required_keys = {"leagues_covered", "divergence_stats"}
            if required_keys - set(_cal_raw.keys()):
                print("  ⚠️ dynamic_cal.json struttura incompleta — uso tabella statica")
            else:
                _DYNAMIC_CAL = _cal_raw
                ds = _cal_raw.get("divergence_stats", {})
                _DIVERGENCE_STD = ds.get("std", DEFAULT_DIVERGENCE_STD)
                print(f"  📊 dynamic_cal.json caricato "
                      f"({_cal_raw.get('leagues_covered', 0)} leghe, σ={_DIVERGENCE_STD:.4f})")
        except Exception as e:  # noqa: BLE001 — mirror live fallback behaviour
            print(f"  ⚠️ dynamic_cal.json non leggibile ({e}) — uso tabella statica")
            _DYNAMIC_CAL = None
    else:
        print("  📊 dynamic_cal.json non trovato — uso tabella statica")

    # --- League Trust Scores ---
    trust_path = os.path.join(base, "league_trust_scores.json")
    _TRUST_SCORES = None
    if os.path.exists(trust_path):
        try:
            with open(trust_path, "r", encoding="utf-8") as f:
                _TRUST_SCORES = json.load(f).get("scores", {})
            print(f"  📊 league_trust_scores.json caricato ({len(_TRUST_SCORES)} leghe)")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ league_trust_scores.json non leggibile ({e})")
            _TRUST_SCORES = None


def apply_poisson_calibration(
    prob: float, market_key: str, league_id: Optional[int] = None
) -> Tuple[float, str]:
    """Replica ESATTA di money_management.SlotManager._apply_calibration.

    Chain di lookup:
      1. dynamic_cal → by_league[league_id][cal_key][bin]
      2. dynamic_cal → global[cal_key][bin]
      3. POISSON_CALIBRATION_TABLE[cal_key][bin]  (statico, fallback)

    Ritorna (prob_corretta, source). Le chiavi bin nel JSON dinamico possono essere
    int o str → tentiamo entrambe come nel live system.
    """
    cal_key = POISSON_CAL_KEY.get(market_key)
    if cal_key is None:
        return prob, "none"

    bin_idx = min(int(prob * 10), 9)
    correction: Optional[float] = None
    source = "none"

    # --- Livello 1: dinamico per lega ---
    if USE_DYNAMIC_CAL and _DYNAMIC_CAL is not None and league_id is not None:
        league_cal = _DYNAMIC_CAL.get("by_league", {}).get(str(league_id), {})
        market_bins = league_cal.get(cal_key, {})
        corr = market_bins.get(bin_idx, market_bins.get(str(bin_idx)))
        if corr is not None:
            correction = corr
            source = "league"

    # --- Livello 2: dinamico globale ---
    if correction is None and USE_DYNAMIC_CAL and _DYNAMIC_CAL is not None:
        market_bins = _DYNAMIC_CAL.get("global", {}).get(cal_key, {})
        corr = market_bins.get(bin_idx, market_bins.get(str(bin_idx)))
        if corr is not None:
            correction = corr
            source = "global"

    # --- Livello 3: statico (fallback) ---
    if correction is None:
        table = POISSON_CALIBRATION_TABLE.get(cal_key)
        if table is not None:
            correction = table.get(bin_idx, 1.0)
            source = "static"

    if correction is None:
        return prob, source
    return max(0.01, min(prob * correction, 0.99)), source


def apply_poisson_safety_filters(
    stake: float, prob: float, odds: float, league_id: Optional[int] = None
) -> Tuple[float, bool]:
    """Replica money_management.SlotManager._apply_safety_filters per il track Poisson.

    - SIGMA (Hallucination Filter): blocca (stake=0) se z_score > POISSON_Z_THRESHOLD
      con z_score = divergence / σ, divergence = prob / prob_market - 1.
    - OMEGA (Trust Score): scala lo stake per il trust della lega.

    NB: il BSS Kelly Shrink NON si applica al track Poisson nel live system
    (process_signals chiama calculate_kelly_stake senza brier_score) → qui replicato
    di conseguenza. Ritorna (stake_finale, is_hallucination)."""
    if stake <= 0:
        return 0.0, False

    # --- SIGMA: Z-Score Hallucination Filter ---
    if USE_HALLUCINATION_FILTER and odds > 1.01:
        prob_market = (1.0 / odds) * OVERROUND_CORRECTION
        if prob_market > 0.01:
            divergence = (prob / prob_market) - 1.0
            z_score = divergence / _DIVERGENCE_STD
            if z_score > POISSON_Z_THRESHOLD:
                return 0.0, True

    # --- OMEGA: League Trust Score ---
    if _TRUST_SCORES is not None and league_id is not None:
        trust = _TRUST_SCORES.get(str(league_id), 1.0)
        if trust != 1.0:
            stake = stake * trust

    return max(round(stake, 2), 1.0), False


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — MAPPING
# ─────────────────────────────────────────────────────────────────────────────

# raw_json_odds → chiave standardizzata
ODDS_PARSE_MAP: Dict[str, Dict[str, str]] = {
    "Match Winner": {
        "Home": "1x2_H", "Draw": "1x2_D", "Away": "1x2_A",
    },
    "Goals Over/Under": {
        "Over 0.5": "over_0_5", "Under 0.5": "under_0_5",
        "Over 1.5": "over_1_5", "Under 1.5": "under_1_5",
        "Over 2.5": "over_2_5", "Under 2.5": "under_2_5",
        "Over 3.5": "over_3_5", "Under 3.5": "under_3_5",
        "Over 4.5": "over_4_5", "Under 4.5": "under_4_5",
    },
    "Both Teams Score": {
        "Yes": "btts_yes", "No": "btts_no",
    },
    "Goals Over/Under First Half": {
        "Over 0.5": "ht_over_0_5", "Under 0.5": "ht_under_0_5",
        "Over 1.5": "ht_over_1_5", "Under 1.5": "ht_under_1_5",
    },
}

# db_json_analisi.markets → chiave standardizzata
# Nota: HT_H/HT_D/HT_A non sono inclusi — raw_json_odds non contiene odds HT 1X2
POISSON_MARKET_MAP: Dict[str, Tuple[str, str, str]] = {
    # chiave_std: (market_in_json, class_in_json, odds_key)
    "1x2_H":       ("1x2",                 "H",     "1x2_H"),
    "1x2_D":       ("1x2",                 "D",     "1x2_D"),
    "1x2_A":       ("1x2",                 "A",     "1x2_A"),
    "over_2_5":    ("over_2_5",            "True",  "over_2_5"),
    "under_2_5":   ("over_2_5",            "False", "under_2_5"),
    "over_1_5":    ("over_1_5",            "True",  "over_1_5"),
    "under_1_5":   ("over_1_5",            "False", "under_1_5"),
    "over_3_5":    ("over_3_5",            "True",  "over_3_5"),
    "under_3_5":   ("over_3_5",            "False", "under_3_5"),
    "btts_yes":    ("btts",                "True",  "btts_yes"),
    "btts_no":     ("btts",                "False", "btts_no"),
    "ht_over_0_5": ("first_half_over_0_5", "True",  "ht_over_0_5"),
}

# model_predictions_json.targets → (odds_key, result_fn_key)
# NOTA: target_ft_1x2 RIMOSSO — mappa agli stessi odds di target_1x2 → duplicazione.
# Il live system (ML_MARKET_MAP in money_management.py) usa solo target_1x2 per H/D/A.
ML_TARGET_MAP: Dict[str, Dict[str, str]] = {
    "target_1x2":       {"H": "1x2_H",    "D": "1x2_D",    "A": "1x2_A"},
    "target_over_2_5":  {"True": "over_2_5", "False": "under_2_5"},
    "target_over_1_5":  {"True": "over_1_5", "False": "under_1_5"},
    "target_over_3_5":  {"True": "over_3_5", "False": "under_3_5"},
    "target_over_4_5":  {"True": "over_4_5", "False": "under_4_5"},
    "target_btts":      {"True": "btts_yes", "False": "btts_no"},
    "target_ht_1x2":    {},  # nessuna odds disponibile in raw_json_odds
    "target_clean_sheet_home": {},
    "target_clean_sheet_away": {},
    "target_home_over_0_5": {},
    "target_away_over_0_5": {},
    "target_home_over_1_5": {},
    "target_away_over_1_5": {},
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — FUNZIONI CORE
# ─────────────────────────────────────────────────────────────────────────────

def parse_raw_json_odds(raw: Any) -> Dict[str, float]:
    """Converte raw_json_odds API-Football in dict {chiave_std: decimal_odds}."""
    if not isinstance(raw, dict):
        return {}
    odds: Dict[str, float] = {}
    for bookmaker in raw.get("bookmakers", []):
        for bet in bookmaker.get("bets", []):
            name = bet.get("name", "")
            market_map = ODDS_PARSE_MAP.get(name)
            if not market_map:
                continue
            for val in bet.get("values", []):
                label = val.get("value", "")
                odd_str = val.get("odd")
                if not odd_str:
                    continue
                try:
                    odd_f = float(odd_str)
                except (ValueError, TypeError):
                    continue
                if odd_f > 1.01:
                    std_key = market_map.get(label)
                    if std_key and std_key not in odds:
                        odds[std_key] = odd_f
        break  # usa solo il primo bookmaker
    return odds


def check_result(
    h: int, a: int, hh: Optional[int], ha: Optional[int], key: str
) -> Optional[bool]:
    """Controlla se l'esito corrisponde a key. None = dati insufficienti.

    NOTA AET/PEN (faithfulness): h/a derivano da result_home_goals/result_away_goals,
    che in API-Football provengono dal campo `goals` = punteggio FINALE incluso
    l'eventuale tempo supplementare (NON il 90'; il 90' è in score.fulltime).
    Per le partite AET/PEN questi goal possono essere gonfiati dai supplementari
    rispetto a un modello Poisson tarato sui 90 minuti.
    DECISIONE: il backtest mantiene la settlement su `goals` perché è ESATTAMENTE
    ciò che fa il live system (money_management.resolve_results accetta FT/AET/PEN e
    valuta su goals_home/goals_away). Escludere AET/PEN o usare il campo 90' sarebbe
    una modifica di settlement del live → registrata come deferred (strategy-change).
    L'impatto è comunque marginale (AET/PEN ~1% delle fixture, quasi solo coppe)."""
    try:
        if key == "1x2_H":     return h > a
        if key == "1x2_D":     return h == a
        if key == "1x2_A":     return h < a
        if key == "over_0_5":  return h + a > 0
        if key == "over_1_5":  return h + a > 1
        if key == "under_1_5": return h + a <= 1
        if key == "over_2_5":  return h + a > 2
        if key == "under_2_5": return h + a <= 2
        if key == "over_3_5":  return h + a > 3
        if key == "under_3_5": return h + a <= 3
        if key == "over_4_5":  return h + a > 4
        if key == "under_4_5": return h + a <= 4
        if key == "btts_yes":  return h > 0 and a > 0
        if key == "btts_no":   return not (h > 0 and a > 0)
        if key == "ht_over_0_5":
            if hh is None or ha is None: return None
            return hh + ha > 0
        if key == "ht_under_0_5":
            if hh is None or ha is None: return None
            return hh + ha == 0
    except Exception:
        pass
    return None


def ev_after_commission(prob: float, odds: float) -> float:
    """EV netto dopo commissione Betfair."""
    if odds <= 1.0 or prob <= 0.0 or prob >= 1.0:
        return -1.0
    net_profit = (odds - 1.0) * (1.0 - BETFAIR_COMMISSION)
    return prob * net_profit - (1.0 - prob)


def kelly_stake(prob: float, odds: float, bankroll: float) -> float:
    """Calcola stake Kelly frazionato con cap a MAX_STAKE_PCT."""
    if odds <= 1.0 or prob <= 0.0:
        return 0.0
    net_odds = (odds - 1.0) * (1.0 - BETFAIR_COMMISSION)
    kf = (prob * net_odds - (1.0 - prob)) / net_odds
    kf = max(0.0, kf)
    kf *= KELLY_FRACTION
    kf = min(kf, MAX_STAKE_PCT)
    return round(kf * bankroll, 2)


def ml_score_passes(edge: float, odds: float, model_prob: float) -> bool:
    """Applica filtro ML_SCORE_TIERS. score = edge × √model_prob (identico al live)."""
    if edge <= 0:
        return False
    # FIX: usa model_prob (non implied 1/odds) — identico a value_betting.py linea 210
    score = edge * math.sqrt(max(0.0, model_prob))
    for max_odds, min_score in ML_SCORE_TIERS:
        if odds < max_odds:
            return score >= min_score
    return score >= ML_SCORE_TIERS[-1][1]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — DB FETCH
# ─────────────────────────────────────────────────────────────────────────────

def fetch_completed_fixtures(
    date_from: Optional[str] = None,
    league_ids: Optional[List[int]] = None,
) -> List[Dict]:
    """
    Ritorna tutte le fixture completate (FT/AET/PEN) con:
    - db_json_analisi (Poisson)
    - raw_json_odds (opzionale)
    - model_predictions_json (opzionale)
    - risultati reali (goals FT)
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from db_client import get_supabase_client
    sb = get_supabase_client()

    select_cols = (
        "fixture_id,league_id,league_name,fixture_date,"
        "home_team_name,away_team_name,"
        "result_status_short,result_home_goals,result_away_goals,"
        "db_json_analisi,raw_json_odds,model_predictions_json"
    )

    all_rows: List[Dict] = []
    page_size = 1000
    offset = 0

    print("Fetching fixture_predictions (FT/AET/PEN)...")
    while True:
        q = (
            sb.table("fixture_predictions")
            .select(select_cols)
            .in_("result_status_short", ["FT", "AET", "PEN"])
        )
        if date_from:
            q = q.gte("fixture_date", date_from)
        if league_ids:
            q = q.in_("league_id", league_ids)
        q = q.range(offset, offset + page_size - 1)
        resp = q.execute()
        batch = resp.data or []
        all_rows.extend(batch)
        print(f"  {len(all_rows)} righe...", end="\r")
        if len(batch) < page_size:
            break
        offset += page_size

    print(f"\n  Totale: {len(all_rows)} fixture completate")
    return all_rows


def fetch_halftime_results(fixture_ids: List[int]) -> Dict[int, Tuple[int, int]]:
    """Ritorna {fixture_id: (halftime_home, halftime_away)} dalla tabella matches."""
    from db_client import get_supabase_client
    sb = get_supabase_client()

    ht_map: Dict[int, Tuple[int, int]] = {}
    batch_size = 300
    for i in range(0, len(fixture_ids), batch_size):
        batch = fixture_ids[i : i + batch_size]
        resp = sb.table("matches").select(
            "fixture_id,halftime_home,halftime_away"
        ).in_("fixture_id", batch).execute()
        for row in resp.data or []:
            hh = row.get("halftime_home")
            ha = row.get("halftime_away")
            if hh is not None and ha is not None:
                try:
                    ht_map[row["fixture_id"]] = (int(hh), int(ha))
                except (ValueError, TypeError):
                    pass
    print(f"  Halftime data: {len(ht_map)} fixture")
    return ht_map


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — POISSON BACKTEST
# ─────────────────────────────────────────────────────────────────────────────

def run_poisson_backtest(
    rows: List[Dict],
    ht_map: Dict[int, Tuple[int, int]],
) -> List[Dict]:
    """
    Simula il betting Poisson su ogni fixture con raw_json_odds.
    Applica gli stessi filtri del sistema live.
    Ritorna lista di record per ogni scommessa potenzialmente piazzata.
    """
    results: List[Dict] = []
    skipped_no_odds = 0
    skipped_no_analisi = 0
    skipped_no_result = 0
    # FIX: dedup Poisson — il live system piazza UN SOLO mercato per fixture (scan_best_market).
    # Raccogliamo tutti i candidati per fixture, poi teniamo solo il migliore (max EV).
    fixture_candidates: Dict[int, List[Dict]] = {}

    for row in rows:
        fid = row.get("fixture_id")
        analisi = row.get("db_json_analisi")
        raw_odds = row.get("raw_json_odds")
        h = row.get("result_home_goals")
        a = row.get("result_away_goals")

        # Requisiti minimi
        if not analisi or not isinstance(analisi, dict):
            skipped_no_analisi += 1
            continue
        # Filtra solo record DC — il modello vecchio ha probabilità diverse e
        # applicare la calibrazione DC su dati pre-DC produce risultati distorti.
        if analisi.get("model") != "poisson_xg_hybrid_dc":
            skipped_no_analisi += 1
            continue
        if not raw_odds:
            skipped_no_odds += 1
            continue
        if h is None or a is None:
            skipped_no_result += 1
            continue

        try:
            h, a = int(h), int(a)
        except (ValueError, TypeError):
            skipped_no_result += 1
            continue

        # HT data
        hh, ha = ht_map.get(fid, (None, None))

        # Parse odds
        odds_dict = parse_raw_json_odds(raw_odds)
        if not odds_dict:
            skipped_no_odds += 1
            continue

        # Markets Poisson
        markets = analisi.get("markets", {})

        for mkey, (json_market, json_class, odds_key) in POISSON_MARKET_MAP.items():
            # Prendi prob Poisson
            market_data = markets.get(json_market)
            if not isinstance(market_data, dict):
                continue
            model_prob = market_data.get(json_class)
            if model_prob is None:
                continue
            try:
                model_prob = float(model_prob)
            except (ValueError, TypeError):
                continue

            # === CALIBRAZIONE POISSON (chain by_league → global → static, come live) ===
            model_prob_raw = model_prob
            lid = row.get("league_id")
            model_prob, cal_source = apply_poisson_calibration(model_prob, mkey, league_id=lid)

            # Quota di mercato
            decimal_odds = odds_dict.get(odds_key)
            if not decimal_odds or decimal_odds <= 1.01:
                continue

            impl_prob = 1.0 / decimal_odds
            edge = model_prob - impl_prob

            # Filtri (stesso del live system)
            min_p = POISSON_MIN_PROB.get(mkey, MIN_PROB_GLOBAL)
            if model_prob < min_p:
                continue

            ev = ev_after_commission(model_prob, decimal_odds)
            # FIX: min_edge per-mercato (allineato al live system)
            min_edge_mkt = POISSON_MIN_EDGE.get(mkey, MIN_EDGE)
            if ev < min_edge_mkt:
                continue

            # Kelly stake
            stake = kelly_stake(model_prob, decimal_odds, BANKROLL)
            if stake <= 0:
                continue

            # FIX (faithfulness): replica i Safety Filters del live system
            # (Z-Score Hallucination + Trust Score). Senza questo il backtest gonfia
            # count/volume/PnL rispetto a ciò che il live piazzerebbe realmente.
            stake, is_hallucination = apply_poisson_safety_filters(
                stake, model_prob, decimal_odds, league_id=lid
            )
            if stake <= 0 or is_hallucination:
                continue

            # Verifica risultato
            won = check_result(h, a, hh, ha, odds_key)
            if won is None:
                continue  # dati HT mancanti per mercato HT

            # Calcola P&L
            if won:
                gross = stake * (decimal_odds - 1.0)
                pnl = gross * (1.0 - BETFAIR_COMMISSION)
            else:
                pnl = -stake

            # FIX (faithfulness): score = ev_after_commission × √prob — IDENTICO al
            # live scan_best_market (edge live == ev_after_commission qui). Il live
            # ordina i candidati per questo score e prende candidates[0], NON max-EV.
            score = ev * math.sqrt(max(0.0, model_prob))

            candidate = {
                "track": "Poisson",
                "fixture_id": fid,
                "fixture_date": str(row.get("fixture_date", ""))[:10],
                "league_id": lid,
                "home": row.get("home_team_name", ""),
                "away": row.get("away_team_name", ""),
                "result": f"{h}-{a}",
                "market": mkey,
                "model_prob": round(model_prob, 4),
                "model_prob_raw": round(model_prob_raw, 4),
                "implied_prob": round(impl_prob, 4),
                "edge": round(edge, 4),
                "decimal_odds": round(decimal_odds, 3),
                "ev": round(ev, 4),
                "score": round(score, 4),
                "cal_source": cal_source,
                "stake": round(stake, 2),
                "won": won,
                "pnl": round(pnl, 2),
            }
            if fid not in fixture_candidates:
                fixture_candidates[fid] = []
            fixture_candidates[fid].append(candidate)

    # FIX (faithfulness): selezione per-fixture IDENTICA a scan_best_market —
    # ordina per score = ev_after_commission × √prob (== live edge × √prob)
    for fid, candidates in fixture_candidates.items():
        candidates.sort(key=lambda x: x["score"], reverse=True)
        results.append(candidates[0])

    print(f"\n  [Poisson] Skipped: no_analisi={skipped_no_analisi}, "
          f"no_odds={skipped_no_odds}, no_result={skipped_no_result}")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — ML BACKTEST (OUT-OF-SAMPLE, PREDIZIONI REALI)
# ─────────────────────────────────────────────────────────────────────────────

def run_ml_backtest(
    rows: List[Dict],
    ht_map: Dict[int, Tuple[int, int]],
) -> List[Dict]:
    """
    Simula il betting ML su fixture con model_predictions_json + raw_json_odds.
    Questi sono out-of-sample REALI (predizioni fatte prima del match).
    """
    results: List[Dict] = []
    skipped_no_ml = 0
    skipped_no_odds = 0
    skipped_no_result = 0

    for row in rows:
        fid = row.get("fixture_id")
        ml_pred = row.get("model_predictions_json")
        raw_odds = row.get("raw_json_odds")
        h = row.get("result_home_goals")
        a = row.get("result_away_goals")

        if not ml_pred or not isinstance(ml_pred, dict):
            skipped_no_ml += 1
            continue
        if not raw_odds:
            skipped_no_odds += 1
            continue
        if h is None or a is None:
            skipped_no_result += 1
            continue

        try:
            h, a = int(h), int(a)
        except (ValueError, TypeError):
            skipped_no_result += 1
            continue

        hh, ha = ht_map.get(fid, (None, None))
        odds_dict = parse_raw_json_odds(raw_odds)
        if not odds_dict:
            skipped_no_odds += 1
            continue

        # Estrai targets dal JSON ML
        targets = ml_pred.get("targets", ml_pred)  # supporta formato con/senza wrapper

        for target, class_map in ML_TARGET_MAP.items():
            if not class_map:
                continue  # target senza odds disponibili

            target_probs = targets.get(target)
            if not isinstance(target_probs, dict):
                continue

            min_p = ML_MIN_PROB.get(target, MIN_PROB_GLOBAL)

            for cls, odds_key in class_map.items():
                model_prob = target_probs.get(cls) or target_probs.get(str(cls))
                if model_prob is None:
                    continue
                try:
                    model_prob = float(model_prob)
                except (ValueError, TypeError):
                    continue

                decimal_odds = odds_dict.get(odds_key)
                if not decimal_odds or decimal_odds <= 1.01:
                    continue

                impl_prob = 1.0 / decimal_odds
                edge = model_prob - impl_prob

                # Filtri live system
                if model_prob < min_p:
                    continue
                ev = ev_after_commission(model_prob, decimal_odds)
                if ev < MIN_EDGE:
                    continue
                if not ml_score_passes(edge, decimal_odds, model_prob):
                    continue

                stake = kelly_stake(model_prob, decimal_odds, BANKROLL)
                if stake <= 0:
                    continue

                won = check_result(h, a, hh, ha, odds_key)
                if won is None:
                    continue

                if won:
                    gross = stake * (decimal_odds - 1.0)
                    pnl = gross * (1.0 - BETFAIR_COMMISSION)
                else:
                    pnl = -stake

                results.append({
                    "track": "ML",
                    "fixture_id": fid,
                    "fixture_date": str(row.get("fixture_date", ""))[:10],
                    "league_id": row.get("league_id"),
                    "home": row.get("home_team_name", ""),
                    "away": row.get("away_team_name", ""),
                    "result": f"{h}-{a}",
                    "market": f"{target}_{cls}",
                    "model_prob": round(model_prob, 4),
                    "implied_prob": round(impl_prob, 4),
                    "edge": round(edge, 4),
                    "decimal_odds": round(decimal_odds, 3),
                    "ev": round(ev, 4),
                    "stake": round(stake, 2),
                    "won": won,
                    "pnl": round(pnl, 2),
                })

    print(f"\n  [ML OOS] Skipped: no_ml={skipped_no_ml}, "
          f"no_odds={skipped_no_odds}, no_result={skipped_no_result}")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — CALIBRAZIONE ML (senza odds, su tutti i 619 record)
# ─────────────────────────────────────────────────────────────────────────────

def run_ml_calibration(rows: List[Dict]) -> Dict[str, Dict]:
    """
    Analisi di calibrazione ML: per ogni target, confronta prob predetta vs hit rate reale.
    Non richiede odds — usa solo model_predictions_json e risultati reali.
    """
    # FIX (low): accumula anche Brier score (p-y)², log-loss e reliability buckets.
    # bias = hit_rate - avg_pred misura solo la calibrazione media globale: un modello
    # che predice 0.5 ovunque ha bias≈0 ma skill nulla. Brier/log-loss penalizzano la
    # mancanza di discriminazione; le reliability buckets mostrano la calibrazione
    # per fascia di probabilità (pred vs realtà in ciascun bin).
    # {target: {cls: {n, sum_prob, hits, sum_brier, sum_logloss, buckets[10]}}}
    def _new_class_stat() -> Dict[str, Any]:
        return {
            "n": 0, "sum_prob": 0.0, "hits": 0,
            "sum_brier": 0.0, "sum_logloss": 0.0,
            # bucket[i] = {"n", "sum_prob", "hits"} per fascia [i/10, (i+1)/10)
            "buckets": [{"n": 0, "sum_prob": 0.0, "hits": 0} for _ in range(10)],
        }

    stats: Dict[str, Dict[str, Dict]] = defaultdict(lambda: defaultdict(_new_class_stat))
    eps = 1e-15  # clip per log-loss

    for row in rows:
        ml_pred = row.get("model_predictions_json")
        h = row.get("result_home_goals")
        a = row.get("result_away_goals")

        if not ml_pred or not isinstance(ml_pred, dict):
            continue
        if h is None or a is None:
            continue
        try:
            h, a = int(h), int(a)
        except (ValueError, TypeError):
            continue

        hh, ha = None, None  # HT non critico per calibrazione

        targets = ml_pred.get("targets", ml_pred)

        for target, class_map in ML_TARGET_MAP.items():
            target_probs = targets.get(target)
            if not isinstance(target_probs, dict):
                continue

            for cls, odds_key in class_map.items():
                model_prob = target_probs.get(cls)
                if model_prob is None:
                    continue
                try:
                    model_prob = float(model_prob)
                except (ValueError, TypeError):
                    continue

                won = check_result(h, a, hh, ha, odds_key)
                if won is None:
                    continue

                y = 1.0 if won else 0.0
                p = min(max(model_prob, 0.0), 1.0)
                s = stats[target][cls]
                s["n"] += 1
                s["sum_prob"] += p
                if won:
                    s["hits"] += 1
                # Brier: (p - y)²  |  log-loss: -[y·ln p + (1-y)·ln(1-p)]
                s["sum_brier"] += (p - y) ** 2
                p_clip = min(max(p, eps), 1.0 - eps)
                s["sum_logloss"] += -(y * math.log(p_clip) + (1.0 - y) * math.log(1.0 - p_clip))
                # Reliability bucket
                bkt = s["buckets"][min(int(p * 10), 9)]
                bkt["n"] += 1
                bkt["sum_prob"] += p
                if won:
                    bkt["hits"] += 1

    # Calcola calibrazione
    calibration: Dict[str, Dict] = {}
    for target, classes in stats.items():
        calibration[target] = {}
        for cls, s in classes.items():
            n = s["n"]
            if n == 0:
                continue
            avg_pred = s["sum_prob"] / n
            hit_rate = s["hits"] / n
            bias = hit_rate - avg_pred
            brier = s["sum_brier"] / n
            log_loss = s["sum_logloss"] / n
            # BSS normalizzato rispetto al baseline "predici sempre il rate medio".
            # baseline_brier = rate·(1-rate) (varianza di Bernoulli del campione).
            baseline_brier = hit_rate * (1.0 - hit_rate)
            bss = (1.0 - brier / baseline_brier) if baseline_brier > 0 else None
            # Reliability buckets non vuoti: (bin_center_pred, actual, n)
            reliability = []
            for i, bkt in enumerate(s["buckets"]):
                if bkt["n"] > 0:
                    reliability.append({
                        "bin": i,
                        "pred": round(bkt["sum_prob"] / bkt["n"], 4),
                        "actual": round(bkt["hits"] / bkt["n"], 4),
                        "n": bkt["n"],
                    })
            calibration[target][cls] = {
                "n": n,
                "avg_pred_prob": round(avg_pred, 4),
                "actual_hit_rate": round(hit_rate, 4),
                "bias": round(bias, 4),
                "brier": round(brier, 4),
                "log_loss": round(log_loss, 4),
                "bss": round(bss, 4) if bss is not None else None,
                "reliability": reliability,
                "accuracy_top1": round(hit_rate, 4),
            }

    return calibration


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — METRICHE
# ─────────────────────────────────────────────────────────────────────────────

def compute_metrics(bets: List[Dict]) -> Dict[str, Any]:
    """Calcola metriche aggregate su una lista di scommesse."""
    if not bets:
        return {}

    n = len(bets)
    n_won = sum(1 for b in bets if b["won"])
    total_staked = sum(b["stake"] for b in bets)
    total_pnl = sum(b["pnl"] for b in bets)
    roi = total_pnl / total_staked if total_staked > 0 else 0.0
    hit_rate = n_won / n

    # Max drawdown
    cumulative = np.cumsum([b["pnl"] for b in bets])
    peak = np.maximum.accumulate(cumulative)
    drawdown = peak - cumulative
    max_dd = float(drawdown.max()) if len(drawdown) > 0 else 0.0

    # Per-bet edge/vol ratio (NON è uno Sharpe annualizzato/risk-free-adjusted):
    # media del ritorno per-scommessa diviso la sua deviazione standard.
    # Normalizzato per stake così che scommesse con stake diversi non distorcano la std.
    # FIX (low): rinominato da "Sharpe" — è un rapporto unitless per-bet, non un
    # indice di Sharpe finanziario. La chiave "sharpe" è mantenuta come alias per
    # retro-compatibilità con report/CSV esistenti.
    roi_per_bet = np.array([b["pnl"] / b["stake"] for b in bets if b["stake"] > 0])
    edge_vol_ratio = float(np.mean(roi_per_bet) / (np.std(roi_per_bet) + 1e-9))

    # Media prob predetta e implied
    avg_model_prob = sum(b["model_prob"] for b in bets) / n
    avg_implied_prob = sum(b["implied_prob"] for b in bets) / n
    avg_edge = sum(b["edge"] for b in bets) / n
    avg_odds = sum(b["decimal_odds"] for b in bets) / n

    # Break-even rate (tenuto conto commissione Betfair)
    # FIX: formula corretta: BE = 1 / ((odds-1)*(1-comm) + 1)
    # Esempio: odds=2.0, comm=5% → BE = 1/((1)*0.95+1) = 1/1.95 = 51.28%
    breakevens = [1.0 / ((b["decimal_odds"] - 1.0) * (1.0 - BETFAIR_COMMISSION) + 1.0) for b in bets]
    avg_breakeven = sum(breakevens) / n

    return {
        "n_bets": n,
        "n_won": n_won,
        "hit_rate": round(hit_rate, 4),
        "avg_breakeven": round(avg_breakeven, 4),
        "hit_vs_be": round(hit_rate - avg_breakeven, 4),
        "total_staked": round(total_staked, 2),
        "total_pnl": round(total_pnl, 2),
        "roi": round(roi, 4),
        "max_drawdown": round(max_dd, 2),
        "edge_vol_ratio": round(edge_vol_ratio, 4),
        "sharpe": round(edge_vol_ratio, 4),  # alias retro-compatibile (vedi nota sopra)
        "avg_model_prob": round(avg_model_prob, 4),
        "avg_implied_prob": round(avg_implied_prob, 4),
        "avg_edge": round(avg_edge, 4),
        "avg_odds": round(avg_odds, 3),
        "final_bankroll": round(BANKROLL + total_pnl, 2),
    }


def compute_per_market_metrics(bets: List[Dict]) -> Dict[str, Dict]:
    """Raggruppa per market e calcola metriche per ciascuno."""
    by_market: Dict[str, List[Dict]] = defaultdict(list)
    for b in bets:
        by_market[b["market"]].append(b)
    return {market: compute_metrics(market_bets)
            for market, market_bets in sorted(by_market.items())}


def compute_per_league_metrics(bets: List[Dict]) -> Dict[str, Dict]:
    """Raggruppa per league_id e calcola metriche."""
    by_league: Dict[str, List[Dict]] = defaultdict(list)
    for b in bets:
        by_league[str(b.get("league_id", "?"))].append(b)
    return {lg: compute_metrics(lb) for lg, lb in sorted(by_league.items())}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — DISPLAY
# ─────────────────────────────────────────────────────────────────────────────

def _bar(value: float, width: int = 20, min_v: float = -0.5, max_v: float = 0.5) -> str:
    """Barra orizzontale per visualizzare ROI."""
    pct = (value - min_v) / (max_v - min_v)
    pct = max(0.0, min(1.0, pct))
    filled = int(pct * width)
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def print_overall_metrics(metrics: Dict, track: str) -> None:
    if not metrics:
        print(f"  {track}: nessun dato disponibile")
        return
    roi_pct = metrics["roi"] * 100
    roi_sign = "+" if roi_pct >= 0 else ""
    verdict = "✅ PROFITTEVOLE" if roi_pct > 0 else ("⚠️ BREAKEVEN" if roi_pct > -3 else "❌ PERDITA")
    print(f"\n  {track} — {verdict}")
    print(f"  {'─' * 50}")
    print(f"  Scommesse piazzate : {metrics['n_bets']:>6}")
    print(f"  Hit rate           : {metrics['hit_rate']*100:>6.1f}%  (breakeven: {metrics['avg_breakeven']*100:.1f}%)")
    print(f"  Hit vs breakeven   : {metrics['hit_vs_be']*100:>+6.1f}%  {'✅' if metrics['hit_vs_be'] > 0 else '❌'}")
    print(f"  ROI netto          : {roi_sign}{roi_pct:>5.1f}%   {_bar(metrics['roi'])}")
    print(f"  P&L totale         : {metrics['total_pnl']:>+8.2f} €  (staked: {metrics['total_staked']:.2f} €)")
    print(f"  Bankroll finale    : {metrics['final_bankroll']:>8.2f} €  (start: {BANKROLL:.2f} €)")
    print(f"  Max drawdown       : {metrics['max_drawdown']:>8.2f} €")
    print(f"  Edge/Vol ratio     : {metrics['edge_vol_ratio']:>8.3f}  (per-bet, non annualizzato)")
    print(f"  Edge medio         : {metrics['avg_edge']*100:>+6.2f}%")
    print(f"  Quota media        : {metrics['avg_odds']:>6.2f}x")


def print_market_breakdown(per_market: Dict[str, Dict], top_n: int = 20) -> None:
    if not per_market:
        return
    # Sort by total_pnl desc
    sorted_markets = sorted(per_market.items(), key=lambda x: x[1].get("total_pnl", 0), reverse=True)
    print(f"\n  {'Market':<30} {'N':>5} {'Hit%':>7} {'BE%':>7} {'Δ%':>7} {'ROI%':>7} {'P&L':>9} {'Ed/Vol':>8}")
    print(f"  {'─'*30} {'─'*5} {'─'*7} {'─'*7} {'─'*7} {'─'*7} {'─'*9} {'─'*8}")
    for market, m in sorted_markets[:top_n]:
        delta = (m["hit_rate"] - m["avg_breakeven"]) * 100
        delta_s = f"{delta:+.1f}%"
        roi_s = f"{m['roi']*100:+.1f}%"
        pnl_s = f"{m['total_pnl']:+.2f}"
        flag = "✅" if m["roi"] > 0 else ("⚠" if m["roi"] > -0.05 else "❌")
        print(f"  {market:<30} {m['n_bets']:>5} "
              f"{m['hit_rate']*100:>6.1f}% "
              f"{m['avg_breakeven']*100:>6.1f}% "
              f"{delta_s:>7} "
              f"{roi_s:>7} "
              f"{pnl_s:>9} "
              f"{m['edge_vol_ratio']:>7.3f}  {flag}")


def print_calibration(calibration: Dict[str, Dict]) -> None:
    if not calibration:
        return
    print(f"\n  {'Target+Cls':<35} {'N':>5} {'Pred':>7} {'Hit':>7} {'Bias':>7} "
          f"{'Brier':>7} {'LogL':>7} {'BSS':>7} {'Status'}")
    print(f"  {'─'*35} {'─'*5} {'─'*7} {'─'*7} {'─'*7} {'─'*7} {'─'*7} {'─'*7} {'─'*10}")
    for target, classes in sorted(calibration.items()):
        for cls, s in sorted(classes.items()):
            bias = s["bias"]
            bias_s = f"{bias*100:+.1f}%"
            bss = s.get("bss")
            bss_s = f"{bss:+.3f}" if bss is not None else "  n/a"
            # Status ora basato sullo SKILL (BSS), non solo sul bias medio:
            # un modello "0.5 ovunque" ha bias≈0 ma BSS≈0 → nessuna skill.
            if bss is not None and bss <= 0.0:
                status = "❌ no skill (BSS≤0)"
            elif abs(bias) < 0.05:
                status = "✅ calibrato"
            elif abs(bias) < 0.10:
                status = "⚠ lieve bias"
            else:
                status = "❌ over/under-pred"
            print(f"  {target}_{cls:<20} {s['n']:>5} "
                  f"{s['avg_pred_prob']*100:>6.1f}% "
                  f"{s['actual_hit_rate']*100:>6.1f}% "
                  f"{bias_s:>7} "
                  f"{s.get('brier', 0.0):>7.4f} "
                  f"{s.get('log_loss', 0.0):>7.4f} "
                  f"{bss_s:>7}  {status}")


def print_data_quality(rows: List[Dict]) -> None:
    total = len(rows)
    n_analisi = sum(1 for r in rows if r.get("db_json_analisi"))
    n_odds = sum(1 for r in rows if r.get("raw_json_odds"))
    n_ml = sum(1 for r in rows if r.get("model_predictions_json"))
    n_both_poisson = sum(1 for r in rows if r.get("db_json_analisi") and r.get("raw_json_odds"))
    n_both_ml = sum(1 for r in rows if r.get("model_predictions_json") and r.get("raw_json_odds"))

    print(f"\n  {'─'*55}")
    print(f"  Qualità dati (su {total} fixture completate)")
    print(f"  {'─'*55}")
    print(f"  Con Poisson (db_json_analisi)   : {n_analisi:>6}  ({n_analisi/total*100:.1f}%)")
    print(f"  Con quote (raw_json_odds)       : {n_odds:>6}  ({n_odds/total*100:.1f}%)")
    print(f"  Con ML (model_predictions_json) : {n_ml:>6}  ({n_ml/total*100:.1f}%)")
    print(f"  Poisson + Quote [BACKTEST]      : {n_both_poisson:>6}  ({n_both_poisson/total*100:.1f}%)")
    print(f"  ML + Quote [BACKTEST OOS]       : {n_both_ml:>6}  ({n_both_ml/total*100:.1f}%)")
    print(f"  ML senza quote [CALIBRAZIONE]   : {n_ml:>6}  (tutti i 619)")
    print(f"  {'─'*55}")
    print()
    if n_both_poisson < 500:
        print("  ⚠️  ATTENZIONE: campione quote limitato (<500 fixture).")
        print("     I risultati Poisson sono indicativi ma statisticamente fragili.")
    if n_both_ml < 100:
        print("  ⚠️  ATTENZIONE: campione ML OOS molto piccolo (<100 fixture).")
        print("     Aggiungi più date al sistema per risultati affidabili.")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — SAVE RESULTS
# ─────────────────────────────────────────────────────────────────────────────

def save_csv(bets: List[Dict], path: str) -> None:
    if not bets:
        return
    # Union ordinata delle chiavi: i record Poisson e ML hanno campi parzialmente
    # diversi (es. Poisson aggiunge score/cal_source/model_prob_raw). Costruiamo
    # l'unione preservando l'ordine di prima apparizione ed escludiamo i campi extra
    # mancanti senza errori (DictWriter su righe eterogenee).
    fieldnames: List[str] = []
    seen = set()
    for b in bets:
        for k in b.keys():
            if k not in seen:
                seen.add(k)
                fieldnames.append(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(bets)
    print(f"\n  CSV salvato: {path}")


def save_markdown_report(
    poisson_overall: Dict,
    poisson_market: Dict,
    ml_overall: Dict,
    ml_market: Dict,
    calibration: Dict,
    n_rows: int,
    timestamp: str,
    path: str,
) -> None:
    lines: List[str] = []
    lines.append(f"# MASTER BACKTEST REPORT")
    lines.append(f"**Generato**: {timestamp}")
    lines.append(f"**Fixture analizzate**: {n_rows}")
    lines.append(f"**Bankroll simulato**: €{BANKROLL:.0f} | **Kelly**: {KELLY_FRACTION*100:.0f}% | **Max stake**: {MAX_STAKE_PCT*100:.0f}% bankroll")
    lines.append(f"**Min EV**: {MIN_EDGE*100:.0f}% | **Commissione**: {BETFAIR_COMMISSION*100:.0f}%")
    lines.append("")

    # Poisson
    lines.append("## Track Poisson")
    if poisson_overall:
        lines.append(f"| Metrica | Valore |")
        lines.append(f"|---------|--------|")
        lines.append(f"| Scommesse | {poisson_overall['n_bets']} |")
        lines.append(f"| Hit rate | {poisson_overall['hit_rate']*100:.1f}% (BE: {poisson_overall['avg_breakeven']*100:.1f}%) |")
        lines.append(f"| ROI netto | {poisson_overall['roi']*100:+.1f}% |")
        lines.append(f"| P&L | {poisson_overall['total_pnl']:+.2f} € |")
        lines.append(f"| Max drawdown | {poisson_overall['max_drawdown']:.2f} € |")
        lines.append(f"| Edge/Vol ratio (per-bet, non annualizzato) | {poisson_overall['edge_vol_ratio']:.3f} |")
        lines.append(f"| Edge medio | {poisson_overall['avg_edge']*100:+.2f}% |")
        lines.append("")
        lines.append("### Per Market (Poisson)")
        lines.append("| Market | N | Hit% | BE% | ROI% | P&L |")
        lines.append("|--------|---|------|-----|------|-----|")
        for mkt, m in sorted(poisson_market.items(), key=lambda x: x[1].get("total_pnl", 0), reverse=True):
            lines.append(f"| {mkt} | {m['n_bets']} | {m['hit_rate']*100:.1f}% | "
                         f"{m['avg_breakeven']*100:.1f}% | {m['roi']*100:+.1f}% | {m['total_pnl']:+.2f} |")
    else:
        lines.append("_Nessun dato disponibile_")
    lines.append("")

    # ML
    lines.append("## Track ML (Out-of-Sample Reale)")
    if ml_overall:
        lines.append(f"| Metrica | Valore |")
        lines.append(f"|---------|--------|")
        lines.append(f"| Scommesse | {ml_overall['n_bets']} |")
        lines.append(f"| Hit rate | {ml_overall['hit_rate']*100:.1f}% (BE: {ml_overall['avg_breakeven']*100:.1f}%) |")
        lines.append(f"| ROI netto | {ml_overall['roi']*100:+.1f}% |")
        lines.append(f"| P&L | {ml_overall['total_pnl']:+.2f} € |")
        lines.append(f"| Max drawdown | {ml_overall['max_drawdown']:.2f} € |")
        lines.append(f"| Edge/Vol ratio (per-bet, non annualizzato) | {ml_overall['edge_vol_ratio']:.3f} |")
        lines.append("")
        if ml_market:
            lines.append("### Per Market (ML)")
            lines.append("| Market | N | Hit% | BE% | ROI% | P&L |")
            lines.append("|--------|---|------|-----|------|-----|")
            for mkt, m in sorted(ml_market.items(), key=lambda x: x[1].get("total_pnl", 0), reverse=True):
                lines.append(f"| {mkt} | {m['n_bets']} | {m['hit_rate']*100:.1f}% | "
                             f"{m['avg_breakeven']*100:.1f}% | {m['roi']*100:+.1f}% | {m['total_pnl']:+.2f} |")
    else:
        lines.append("_Nessun dato disponibile (serve raw_json_odds + model_predictions_json)_")
    lines.append("")

    # Calibrazione ML
    lines.append("## Calibrazione ML (su tutti i record con predizioni)")
    lines.append("_Brier=(p-y)² (più basso = meglio) · LogLoss (più basso = meglio) · "
                 "BSS=skill vs baseline rate medio (≤0 = nessuna skill)._")
    if calibration:
        lines.append("| Target | Cls | N | Pred% | Hit% | Bias | Brier | LogLoss | BSS | Stato |")
        lines.append("|--------|-----|---|-------|------|------|-------|---------|-----|-------|")
        for target, classes in sorted(calibration.items()):
            for cls, s in sorted(classes.items()):
                bias = s["bias"]
                bss = s.get("bss")
                bss_s = f"{bss:+.3f}" if bss is not None else "n/a"
                if bss is not None and bss <= 0.0:
                    stato = "❌"
                elif abs(bias) < 0.05:
                    stato = "✅"
                elif abs(bias) < 0.10:
                    stato = "⚠️"
                else:
                    stato = "❌"
                lines.append(f"| {target} | {cls} | {s['n']} | "
                             f"{s['avg_pred_prob']*100:.1f}% | "
                             f"{s['actual_hit_rate']*100:.1f}% | "
                             f"{bias*100:+.1f}% | "
                             f"{s.get('brier', 0.0):.4f} | "
                             f"{s.get('log_loss', 0.0):.4f} | "
                             f"{bss_s} | {stato} |")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Report MD salvato: {path}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Master Backtest — Poisson + ML")
    parser.add_argument("--from", dest="date_from", default=None,
                        help="Data minima YYYY-MM-DD (default: tutto lo storico)")
    parser.add_argument("--leagues", default=None,
                        help="League IDs separati da virgola (es: 39,135,78)")
    parser.add_argument("--no-csv", action="store_true", help="Non salvare CSV")
    args = parser.parse_args()

    league_ids = None
    if args.leagues:
        league_ids = [int(x.strip()) for x in args.leagues.split(",")]

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(out_dir, f"backtest_results_{ts}.csv")
    md_path = os.path.join(out_dir, f"backtest_report_{ts}.md")

    # ── 0. CARICA DATI DINAMICI (replica esatta del live system) ──
    print_section("CARICAMENTO CALIBRAZIONE DINAMICA + TRUST SCORES")
    load_dynamic_data()

    # ── 1. FETCH DATI ──
    print_section("FETCH DATI DAL DB")
    rows = fetch_completed_fixtures(date_from=args.date_from, league_ids=league_ids)

    # Fetch HT solo per fixture con raw_json_odds (per mercato ht_over_0_5)
    fids_with_odds = [r["fixture_id"] for r in rows if r.get("raw_json_odds")]
    print(f"Fetching halftime data per {len(fids_with_odds)} fixture con odds...")
    ht_map = fetch_halftime_results(fids_with_odds) if fids_with_odds else {}

    # ── 2. DATA QUALITY ──
    print_section("QUALITÀ DATI")
    print_data_quality(rows)

    # ── 3. POISSON BACKTEST ──
    print_section("BACKTEST POISSON")
    print("  Applico filtri: MIN_EDGE={:.0f}% | Kelly={:.0f}% | Max stake={:.0f}% bankroll".format(
        MIN_EDGE * 100, KELLY_FRACTION * 100, MAX_STAKE_PCT * 100))
    poisson_bets = run_poisson_backtest(rows, ht_map)
    poisson_overall = compute_metrics(poisson_bets)
    poisson_market = compute_per_market_metrics(poisson_bets)
    poisson_league = compute_per_league_metrics(poisson_bets)
    print_overall_metrics(poisson_overall, "POISSON")
    if poisson_market:
        print_section("BREAKDOWN PER MERCATO — POISSON")
        print_market_breakdown(poisson_market)

    # ── 4. ML BACKTEST (OOS REALE) ──
    print_section("BACKTEST ML — OUT-OF-SAMPLE REALE")
    print("  Solo fixture con model_predictions_json + raw_json_odds")
    print("  ⚠  Campione piccolo — quota reale di partite predette dal vivo")
    ml_bets = run_ml_backtest(rows, ht_map)
    ml_overall = compute_metrics(ml_bets)
    ml_market = compute_per_market_metrics(ml_bets)
    ml_league = compute_per_league_metrics(ml_bets)
    print_overall_metrics(ml_overall, "ML (OOS)")
    if ml_market:
        print_section("BREAKDOWN PER MERCATO — ML")
        print_market_breakdown(ml_market)

    # ── 5. CALIBRAZIONE ML ──
    print_section("CALIBRAZIONE ML (senza requisito odds — tutti i 619 record)")
    calibration = run_ml_calibration(rows)
    print_calibration(calibration)

    # ── 6. ANALISI FINALE ──
    print_section("ANALISI FINALE — COSA ASPETTARSI")
    print()
    print("  POISSON:")
    if poisson_overall:
        hr = poisson_overall["hit_rate"]
        be = poisson_overall["avg_breakeven"]
        roi = poisson_overall["roi"]
        print(f"    Hit rate {hr*100:.1f}% vs breakeven {be*100:.1f}%  →  delta = {(hr-be)*100:+.1f}%")
        if roi > 0.03:
            print(f"    ✅ ROI {roi*100:+.1f}%: il modello Poisson mostra edge reale sui dati disponibili.")
            print(f"       Scala il bankroll e mantieni i filtri attuali.")
        elif roi > 0:
            print(f"    ⚠️  ROI {roi*100:+.1f}%: edge marginale. Aumenta MIN_EDGE o MIN_PROB.")
        else:
            print(f"    ❌ ROI {roi*100:+.1f}%: nessun edge. Vedi breakdown per mercato per trovare quelli profittevoli.")
    else:
        print("    Nessun dato — serve raw_json_odds nel DB")

    print()
    print("  ML:")
    if ml_overall and ml_overall.get("n_bets", 0) >= 10:
        hr = ml_overall["hit_rate"]
        be = ml_overall["avg_breakeven"]
        roi = ml_overall["roi"]
        n = ml_overall["n_bets"]
        print(f"    N={n} scommesse OOS | Hit {hr*100:.1f}% vs BE {be*100:.1f}% → delta {(hr-be)*100:+.1f}%")
        if n < 50:
            print(f"    ⚠️  Campione troppo piccolo ({n} bets) per conclusioni statistiche robuste.")
            print(f"       Continua ad accumulare predizioni live prima di giudicare il track ML.")
        if roi > 0:
            print(f"    ✅ ROI {roi*100:+.1f}% — ma verifica dopo almeno 200+ scommesse OOS.")
        else:
            print(f"    ❌ ROI {roi*100:+.1f}% su {n} bet — campione insufficiente per giudizio definitivo.")
    else:
        print("    Campione ML OOS insufficiente per backtest affidabile.")
        print("    Continua a registrare predizioni live con raw_json_odds per almeno 3-6 mesi.")

    print()
    print("  CALIBRAZIONE ML:")
    total_bias_abs = []
    bss_values = []
    for target, classes in calibration.items():
        for cls, s in classes.items():
            if s["n"] >= 20:
                total_bias_abs.append(abs(s["bias"]))
                if s.get("bss") is not None:
                    bss_values.append(s["bss"])
    if total_bias_abs:
        avg_bias = sum(total_bias_abs) / len(total_bias_abs)
        print(f"    Bias medio assoluto: {avg_bias*100:.1f}%")
        if avg_bias < 0.05:
            print("    ✅ Modello ben calibrato (bias < 5%)")
        elif avg_bias < 0.10:
            print("    ⚠️  Lieve miscalibrazione (bias 5-10%) — considera ricalibrazione isotonica")
        else:
            print("    ❌ Miscalibrazione significativa (>10%) — modello deve essere ricalibrato")
    # BSS misura la SKILL (discriminazione), che il bias da solo non cattura:
    # un modello "0.5 ovunque" ha bias≈0 ma BSS≈0.
    if bss_values:
        avg_bss = sum(bss_values) / len(bss_values)
        print(f"    BSS medio (skill): {avg_bss:+.3f}")
        if avg_bss <= 0.0:
            print("    ❌ Nessuna skill predittiva (BSS ≤ 0) — il modello non batte il rate medio")
        elif avg_bss < 0.05:
            print("    ⚠️  Skill molto debole (BSS < 0.05) — al limite del rumore")
        else:
            print("    ✅ Skill predittiva presente (BSS > 0.05)")

    print()
    print("  COSA FARE ADESSO:")
    print("  1. Assicurati che raw_json_odds vengano salvati per OGNI partita live")
    print("     → I backtest Poisson e ML dipendono da questo")
    print("  2. Le quote Betfair nell'odds store devono matchare le quote al momento della predizione")
    print("  3. Dopo 200+ predizioni ML con odds, ri-esegui questo backtest per un giudizio definitivo")
    print("  4. I mercati con ROI Poisson positivo nel breakdown → concentra lì il capitale")
    print()

    # ── 7. SAVE ──
    all_bets = poisson_bets + ml_bets
    if all_bets and not args.no_csv:
        save_csv(all_bets, csv_path)

    save_markdown_report(
        poisson_overall, poisson_market,
        ml_overall, ml_market,
        calibration,
        n_rows=len(rows),
        timestamp=ts,
        path=md_path,
    )

    print()
    print("=" * 78)
    print(f"  BACKTEST COMPLETATO — {len(all_bets)} scommesse totali simulate")
    print("=" * 78)


if __name__ == "__main__":
    main()
