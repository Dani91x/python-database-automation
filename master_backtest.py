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
  - Sharpe ratio
  - Calibrazione: prob media predetta vs hit rate reale

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
    # Aggiornato 2026-03-16 da 33,071 match (258,274 campioni)
    "H":       {0: 3.350, 1: 1.217, 2: 0.996, 3: 1.009, 4: 0.982, 5: 0.987, 6: 1.008, 7: 1.001, 8: 0.962, 9: 0.873},
    "D":       {0: 0.717, 1: 0.906, 2: 0.994, 3: 1.022, 4: 0.852, 5: 1.0,   6: 1.0,   7: 1.0,   8: 1.0,   9: 1.0  },
    "A":       {0: 1.656, 1: 1.057, 2: 1.016, 3: 1.020, 4: 0.958, 5: 1.025, 6: 1.019, 7: 0.960, 8: 0.966, 9: 1.0  },
    "O25":     {0: 6.894, 1: 1.437, 2: 1.393, 3: 1.126, 4: 1.039, 5: 0.963, 6: 0.961, 7: 0.965, 8: 0.931, 9: 0.796},
    "U25":     {0: 3.638, 1: 1.351, 2: 1.103, 3: 1.075, 4: 1.041, 5: 0.969, 6: 0.931, 7: 0.863, 8: 0.913, 9: 0.649},
    "BTTS":    {0: 7.159, 1: 1.994, 2: 1.437, 3: 1.194, 4: 1.021, 5: 0.963, 6: 0.886, 7: 0.869, 8: 0.767, 9: 1.0  },
    "BTTS_NO": {0: 1.0,   1: 2.178, 2: 1.364, 3: 1.206, 4: 1.044, 5: 0.983, 6: 0.891, 7: 0.842, 8: 0.795, 9: 0.765},
    "HT05":    {0: 1.0,   1: 4.724, 2: 2.735, 3: 1.950, 4: 1.433, 5: 1.226, 6: 1.040, 7: 0.946, 8: 0.870, 9: 0.813},
    # Mercati estesi — calibrazione neutrale 1.0 (nessun dato storico ancora)
    "O15":     {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0, 9: 1.0},
    "U15":     {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0, 9: 1.0},
    "O35":     {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0, 9: 1.0},
    "U35":     {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0, 9: 1.0},
    "HT_H":    {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0, 9: 1.0},
    "HT_D":    {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0, 9: 1.0},
    "HT_A":    {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0, 9: 1.0},
    "HT_U05":  {0: 22.399, 1: 1.833, 2: 1.246, 3: 0.884, 4: 0.778, 5: 0.659, 6: 0.544, 7: 0.457, 8: 0.411, 9: 0.320},
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


def apply_poisson_calibration(prob: float, market_key: str) -> float:
    """Applica la stessa calibrazione del sistema live (money_management.py).
    Ritorna la prob corretta. Se non c'è tabella per il mercato, ritorna prob invariata."""
    cal_key = POISSON_CAL_KEY.get(market_key)
    if cal_key is None:
        return prob
    table = POISSON_CALIBRATION_TABLE.get(cal_key, {})
    bin_idx = min(int(prob * 10), 9)
    correction = table.get(bin_idx, 1.0)
    return max(0.01, min(prob * correction, 0.99))


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
    """Controlla se l'esito corrisponde a key. None = dati insufficienti."""
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

            # === CALIBRAZIONE POISSON (identica a money_management.py) ===
            model_prob_raw = model_prob
            model_prob = apply_poisson_calibration(model_prob, mkey)

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

            candidate = {
                "track": "Poisson",
                "fixture_id": fid,
                "fixture_date": str(row.get("fixture_date", ""))[:10],
                "league_id": row.get("league_id"),
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
                "stake": round(stake, 2),
                "won": won,
                "pnl": round(pnl, 2),
            }
            if fid not in fixture_candidates:
                fixture_candidates[fid] = []
            fixture_candidates[fid].append(candidate)

    # FIX dedup: per ogni fixture tieni solo il mercato con EV massima (come scan_best_market)
    for fid, candidates in fixture_candidates.items():
        best = max(candidates, key=lambda x: x["ev"])
        results.append(best)

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
    # {target: {cls: {"n": int, "sum_prob": float, "hits": int}}}
    stats: Dict[str, Dict[str, Dict]] = defaultdict(lambda: defaultdict(
        lambda: {"n": 0, "sum_prob": 0.0, "hits": 0}
    ))

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

        fid = row.get("fixture_id")
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

                s = stats[target][cls]
                s["n"] += 1
                s["sum_prob"] += model_prob
                if won:
                    s["hits"] += 1

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
            bss_baseline = 0.5 if cls in ("H", "A", "True", "False") else 0.333
            calibration[target][cls] = {
                "n": n,
                "avg_pred_prob": round(avg_pred, 4),
                "actual_hit_rate": round(hit_rate, 4),
                "bias": round(bias, 4),
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

    # Sharpe normalizzato per stake (ROI per scommessa / std del ROI)
    # FIX: normalizzare per stake evita che scommesse con stake diversi distorcano la std
    roi_per_bet = np.array([b["pnl"] / b["stake"] for b in bets if b["stake"] > 0])
    sharpe = float(np.mean(roi_per_bet) / (np.std(roi_per_bet) + 1e-9))

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
        "sharpe": round(sharpe, 4),
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
    print(f"  Sharpe ratio       : {metrics['sharpe']:>8.3f}")
    print(f"  Edge medio         : {metrics['avg_edge']*100:>+6.2f}%")
    print(f"  Quota media        : {metrics['avg_odds']:>6.2f}x")


def print_market_breakdown(per_market: Dict[str, Dict], top_n: int = 20) -> None:
    if not per_market:
        return
    # Sort by total_pnl desc
    sorted_markets = sorted(per_market.items(), key=lambda x: x[1].get("total_pnl", 0), reverse=True)
    print(f"\n  {'Market':<30} {'N':>5} {'Hit%':>7} {'BE%':>7} {'Δ%':>7} {'ROI%':>7} {'P&L':>9} {'Sharpe':>8}")
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
              f"{m['sharpe']:>7.3f}  {flag}")


def print_calibration(calibration: Dict[str, Dict]) -> None:
    if not calibration:
        return
    print(f"\n  {'Target+Cls':<35} {'N':>5} {'Avg Pred':>9} {'Hit Rate':>9} {'Bias':>8} {'Status'}")
    print(f"  {'─'*35} {'─'*5} {'─'*9} {'─'*9} {'─'*8} {'─'*10}")
    for target, classes in sorted(calibration.items()):
        for cls, s in sorted(classes.items()):
            bias = s["bias"]
            bias_s = f"{bias*100:+.1f}%"
            status = "✅ calibrato" if abs(bias) < 0.05 else (
                "⚠ lieve bias" if abs(bias) < 0.10 else "❌ over/under-pred")
            print(f"  {target}_{cls:<20} {s['n']:>5} "
                  f"{s['avg_pred_prob']*100:>8.1f}% "
                  f"{s['actual_hit_rate']*100:>8.1f}% "
                  f"{bias_s:>8} "
                  f"  {status}")


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
    fieldnames = list(bets[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
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
        lines.append(f"| Sharpe | {poisson_overall['sharpe']:.3f} |")
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
        lines.append(f"| Sharpe | {ml_overall['sharpe']:.3f} |")
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
    if calibration:
        lines.append("| Target | Cls | N | Pred% | Hit% | Bias | Stato |")
        lines.append("|--------|-----|---|-------|------|------|-------|")
        for target, classes in sorted(calibration.items()):
            for cls, s in sorted(classes.items()):
                bias = s["bias"]
                stato = "✅" if abs(bias) < 0.05 else ("⚠️" if abs(bias) < 0.10 else "❌")
                lines.append(f"| {target} | {cls} | {s['n']} | "
                             f"{s['avg_pred_prob']*100:.1f}% | "
                             f"{s['actual_hit_rate']*100:.1f}% | "
                             f"{bias*100:+.1f}% | {stato} |")

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
    for target, classes in calibration.items():
        for cls, s in classes.items():
            if s["n"] >= 20:
                total_bias_abs.append(abs(s["bias"]))
    if total_bias_abs:
        avg_bias = sum(total_bias_abs) / len(total_bias_abs)
        print(f"    Bias medio assoluto: {avg_bias*100:.1f}%")
        if avg_bias < 0.05:
            print("    ✅ Modello ben calibrato (bias < 5%)")
        elif avg_bias < 0.10:
            print("    ⚠️  Lieve miscalibrazione (bias 5-10%) — considera ricalibrazione isotonica")
        else:
            print("    ❌ Miscalibrazione significativa (>10%) — modello deve essere ricalibrato")

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
