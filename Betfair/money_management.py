"""
=============================================================================
  QUANT FUND — Money Management Engine v3.0 (Edge Engine)
  Sistema di Money Management a Slot Paralleli Dinamici con:
  - Edge Scanner Multi-Mercato (6 mercati)
  - Confidence-Adjusted Edge Score (Edge × √Prob)
  - Kelly Criterion Frazionato (configurabile)
  - Risoluzione Risultati automatica dal DB
  - Report "Ven-Dom" su Google Sheets
  - Dashboard Professionale su Google Sheets
  --- v3.0 ---
  - Calibrazione Poisson Dinamica (rolling window per lega + globale)
  - Hallucination Filter (Z-Score Protection)
  - League Trust Score (Pressure Regulator)
  - Feature Flags per attivazione/disattivazione indipendente
============================================================================="""

import json
import os
import math
import logging
import time as time_module
import tempfile
from datetime import datetime, timedelta, timezone
import gspread

# Import condizionale per gspread_formatting
try:
    from gspread_formatting import DataValidationRule, BooleanCondition, set_data_validation_for_cell_range
    HAS_FORMATTING = True
except ImportError:
    HAS_FORMATTING = False

# Import DB client
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_client import get_supabase_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  COSTANTI DI DEFAULT
# ---------------------------------------------------------------------------
DEFAULT_BANKROLL = 1000.0
DEFAULT_DAILY_TARGET = 150.0
DEFAULT_STOP_LOSS_PCT = 10.0
# At 5% Betfair commission, a raw EV below ~5.26% yields negative expected
# profit.  We require at least 5% edge (post-margin) so every accepted bet
# has a genuine positive expectation even after the exchange cut.
DEFAULT_MIN_EDGE_PCT = 5.0       # Minimum edge % to place a bet (covers 5% commission)
DEFAULT_MIN_PROB_PCT = 50.0      # Minimum model probability (avoids high-variance long shots)
DEFAULT_KELLY_FRACTION = 0.10    # Conservative fractional Kelly — validated BSS required before raising
DEFAULT_MAX_STAKE_PCT = 2.0      # Max 2% bankroll per slot
DEFAULT_MIN_MATCHES_USED = 5     # Minimum historical matches for reliable form features
DEFAULT_COMMISSION_PCT = 5.0     # Betfair commission on net winnings (%)

STATE_FILE = os.path.join(os.path.dirname(__file__), "money_management_state.json")

# ---------------------------------------------------------------------------
#  EDGE ENGINE v3.0 — Feature Flags
#  Ogni componente può essere attivato/disattivato indipendentemente.
# ---------------------------------------------------------------------------
EDGE_ENGINE_FLAGS = {
    "use_dynamic_cal": True,           # Alpha: Calibrazione Dinamica
    "use_hallucination_filter": True,  # Sigma: Z-Score Hallucination Filter
    "use_trust_score": True,           # Omega: League Trust Score
}

# ---------------------------------------------------------------------------
#  FILTRO INTELLIGENTE QUOTE ALTE (ML Track)
#  score = edge × √prob  —  penalizza naturalmente le quote alte senza cap
#  arbitrari.  Una quota 4.0 (prob ~0.25) richiede un edge proporzionalmente
#  più alto rispetto a una quota 2.0 (prob ~0.50) per ottenere lo stesso score.
#  Esempio:
#    odds 2.0, edge 5%  → score = 0.035  → PASSA
#    odds 4.0, edge 5%  → score = 0.025  → PASSA (esattamente al limite)
#    odds 4.0, edge 4%  → score = 0.020  → SCARTATO
#    odds 4.0, edge 10% → score = 0.050  → PASSA (segnale genuinamente forte)
#    odds 6.0, edge 15% → score = 0.061  → PASSA (edge reale su quota alta)
# ---------------------------------------------------------------------------
MIN_ML_SCORE_THRESHOLD: float = 0.025

# Correzione overround Betfair (~2.5%) per calcolo prob_market
OVERROUND_CORRECTION = 0.975
# Z-Score σ di fallback (usata se dynamic_cal.json non contiene divergence_stats)
DEFAULT_DIVERGENCE_STD = 0.30

MARKET_MAP = {
    # min_edge is the minimum edge % required AFTER Betfair commission (5%).
    # Previously set to 2% for an A/B data-collection experiment — but at 5%
    # commission, a 2% edge is guaranteed to lose money.  Restored to 5%.
    "H":       {"label": "Home Win",      "json_path": ("markets", "1x2", "H"),                      "ai_path": ("target_1x2", "H"), "cal_key": "H", "min_edge": 5.0},
    "D":       {"label": "Pareggio",      "json_path": ("markets", "1x2", "D"),                      "ai_path": ("target_1x2", "D"), "cal_key": "D", "min_edge": 5.0},
    "A":       {"label": "Away Win",      "json_path": ("markets", "1x2", "A"),                      "ai_path": ("target_1x2", "A"), "cal_key": "A", "min_edge": 5.0},
    "O25":     {"label": "Over 2.5",      "json_path": ("markets", "over_2_5", "True"),              "ai_path": ("target_over_2_5", "True"), "cal_key": "O25", "min_edge": 5.0},
    "U25":     {"label": "Under 2.5",     "json_path": ("markets", "over_2_5", "False"),             "ai_path": ("target_over_2_5", "False"), "cal_key": "U25", "min_edge": 5.0},
    "BTTS":    {"label": "BTTS Sì",       "json_path": ("markets", "btts", "True"),                  "ai_path": ("target_btts", "True"), "cal_key": "BTTS", "min_edge": 5.0},
    "BTTS_NO": {"label": "BTTS No",       "json_path": ("markets", "btts", "False"),                 "ai_path": ("target_btts", "False"), "cal_key": "BTTS_NO", "min_edge": 5.0},
    "HT05":    {"label": "1H Over 0.5",   "json_path": ("markets", "first_half_over_0_5", "True"),   "ai_path": ("target_ht_over_0_5", "True"), "cal_key": "HT05", "min_edge": 5.0},
}

# ---------------------------------------------------------------------------
#  MARKET MAP per ML — usa probabilità AI direttamente (no calibrazione Poisson)
#  Copre gli stessi mercati con odds disponibili su Betfair.
#
#  ai_target : nome del target nel payload del modello (usato per leggere
#              il Brier score e applicare il Kelly Shrinkage basato su BSS).
#  n_classes : numero di classi del modello corrispondente (2=binario, 3=1x2).
#              Serve per normalizzare il BSS: brier_random=(n_classes-1)/n_classes.
#  min_edge  : ripristinato a 5.0 (era stato abbassato a 2.0 per A/B Test;
#              con modelli a Brier ~random il 2% era indistinguibile dal rumore).
# ---------------------------------------------------------------------------
ML_MARKET_MAP = {
    "H":       {"label": "Home Win (ML)",    "ai_path": ("target_1x2", "H"),           "odds_key": "H",       "min_edge": 5.0, "ai_target": "target_1x2",       "n_classes": 3},
    "D":       {"label": "Pareggio (ML)",    "ai_path": ("target_1x2", "D"),           "odds_key": "D",       "min_edge": 5.0, "ai_target": "target_1x2",       "n_classes": 3},
    "A":       {"label": "Away Win (ML)",    "ai_path": ("target_1x2", "A"),           "odds_key": "A",       "min_edge": 5.0, "ai_target": "target_1x2",       "n_classes": 3},
    "O25":     {"label": "Over 2.5 (ML)",    "ai_path": ("target_over_2_5", "True"),   "odds_key": "O25",     "min_edge": 5.0, "ai_target": "target_over_2_5",  "n_classes": 2},
    "U25":     {"label": "Under 2.5 (ML)",   "ai_path": ("target_over_2_5", "False"),  "odds_key": "U25",     "min_edge": 5.0, "ai_target": "target_over_2_5",  "n_classes": 2},
    "BTTS":    {"label": "BTTS Sì (ML)",     "ai_path": ("target_btts", "True"),       "odds_key": "BTTS",    "min_edge": 5.0, "ai_target": "target_btts",      "n_classes": 2},
    "BTTS_NO": {"label": "BTTS No (ML)",     "ai_path": ("target_btts", "False"),      "odds_key": "BTTS_NO", "min_edge": 5.0, "ai_target": "target_btts",      "n_classes": 2},
    "HT05":    {"label": "1H Over 0.5 (ML)", "ai_path": ("target_ht_over_0_5", "True"),"odds_key": "HT05",   "min_edge": 5.0, "ai_target": "target_ht_over_0_5","n_classes": 2},
    # Extended markets — Betfair odds now fetched via OVER_UNDER_15/35 and HALF_TIME
    "O15":     {"label": "Over 1.5 (ML)",    "ai_path": ("target_over_1_5", "True"),   "odds_key": "O15",    "min_edge": 5.0, "ai_target": "target_over_1_5",   "n_classes": 2},
    "U15":     {"label": "Under 1.5 (ML)",   "ai_path": ("target_over_1_5", "False"),  "odds_key": "U15",    "min_edge": 5.0, "ai_target": "target_over_1_5",   "n_classes": 2},
    "O35":     {"label": "Over 3.5 (ML)",    "ai_path": ("target_over_3_5", "True"),   "odds_key": "O35",    "min_edge": 5.0, "ai_target": "target_over_3_5",   "n_classes": 2},
    "U35":     {"label": "Under 3.5 (ML)",   "ai_path": ("target_over_3_5", "False"),  "odds_key": "U35",    "min_edge": 5.0, "ai_target": "target_over_3_5",   "n_classes": 2},
    "HT_H":    {"label": "HT Home (ML)",     "ai_path": ("target_ht_1x2", "H"),        "odds_key": "HT_H",   "min_edge": 5.0, "ai_target": "target_ht_1x2",    "n_classes": 3},
    "HT_D":    {"label": "HT Draw (ML)",     "ai_path": ("target_ht_1x2", "D"),        "odds_key": "HT_D",   "min_edge": 5.0, "ai_target": "target_ht_1x2",    "n_classes": 3},
    "HT_A":    {"label": "HT Away (ML)",     "ai_path": ("target_ht_1x2", "A"),        "odds_key": "HT_A",   "min_edge": 5.0, "ai_target": "target_ht_1x2",    "n_classes": 3},
}

# ---------------------------------------------------------------------------
#  TABELLA DI CALIBRAZIONE — Derivata da 24,787 match storici
#  Per ogni mercato e fascia di probabilità: fattore correttivo = WR_reale / Prob_stimata
#  Applicato PRIMA del calcolo dell'edge per usare probabilità realistiche.
# ---------------------------------------------------------------------------
CALIBRATION_TABLE = {
    # 1X2 Home — ben calibrato (bias ±1pp)
    "H": {0: 2.234, 1: 1.013, 2: 1.056, 3: 1.005, 4: 1.004, 5: 1.033, 6: 1.015, 7: 0.937, 8: 0.998, 9: 1.017},
    # 1X2 Draw
    "D": {0: 0.685, 1: 0.917, 2: 0.975, 3: 1.019, 4: 0.793, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0, 9: 0.661},
    # 1X2 Away
    "A": {0: 1.638, 1: 0.956, 2: 0.994, 3: 1.018, 4: 0.961, 5: 1.012, 6: 1.083, 7: 1.100, 8: 1.082, 9: 0.613},
    # Over 2.5 — sovrastima alle alte prob
    "O25": {0: 5.616, 1: 1.630, 2: 1.288, 3: 1.150, 4: 1.027, 5: 0.969, 6: 0.961, 7: 0.971, 8: 0.935, 9: 0.845},
    # Under 2.5
    "U25": {0: 3.238, 1: 1.342, 2: 1.077, 3: 1.074, 4: 1.037, 5: 0.978, 6: 0.917, 7: 0.900, 8: 0.874, 9: 0.709},
    # BTTS Sì — FORTE sovrastima (80%+: corr 0.63)
    "BTTS": {0: 4.542, 1: 1.061, 2: 1.268, 3: 1.201, 4: 1.026, 5: 0.941, 6: 0.886, 7: 0.821, 8: 0.635, 9: 0.572},
    # BTTS No — sottostimato (yield +62% nel backtest)
    "BTTS_NO": {0: 5.708, 1: 2.966, 2: 1.504, 3: 1.208, 4: 1.071, 5: 0.978, 6: 0.888, 7: 0.904, 8: 0.987, 9: 0.865},
    # 1H Over 0.5 — calibrazione rotta: il modello non funziona bene
    "HT05": {0: 1.0, 1: 4.564, 2: 2.667, 3: 1.877, 4: 1.451, 5: 1.251, 6: 1.059, 7: 0.922, 8: 0.860, 9: 0.727},
    # 1H Under 0.5 — calibrazione rotta
    "HT_U05": {0: 22.399, 1: 1.833, 2: 1.246, 3: 0.884, 4: 0.778, 5: 0.659, 6: 0.544, 7: 0.457, 8: 0.411, 9: 0.320},
}

# ---------------------------------------------------------------------------
#  HELPER: Google Sheets call con retry su 429/500/503 (Rate Limit & Server Errors)
# ---------------------------------------------------------------------------
def _sheets_retry(func, *args, max_retries=5, **kwargs):
    """Esegue una chiamata Google Sheets con retry automatico su errore 429/500/503.
    Usa exponential backoff: 5s, 10s, 20s, 40s, 80s."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            err_str = str(e)
            is_retryable = any(code in err_str for code in ("429", "500", "503"))
            if is_retryable and attempt < max_retries - 1:
                wait = 5 * (2 ** attempt)  # 5, 10, 20, 40, 80
                logger.warning(f"Sheets API error ({err_str[:80]}), attendo {wait}s (tentativo {attempt+1}/{max_retries})...")
                time_module.sleep(wait)
            else:
                raise
        except Exception as e:
            # Catch anche errori di rete/timeout
            if attempt < max_retries - 1:
                wait = 5 * (2 ** attempt)
                logger.warning(f"Sheets error generico ({type(e).__name__}: {str(e)[:60]}), retry in {wait}s...")
                time_module.sleep(wait)
            else:
                raise
    return None


class SlotManager:
    """Gestore centrale del Money Management — Quant Fund Edition"""

    def __init__(self, gc, sh):
        self.gc = gc
        self.sh = sh
        self.config = self._load_config_from_sheet()
        self.state = self._load_state()
        self._load_dynamic_data()
        self._last_kelly_meta = {}  # metadati dell'ultimo calcolo per diagnostica

    # ======================================================================
    #  CONFIGURAZIONE
    # ======================================================================
    def _load_config_from_sheet(self):
        config = {
            "bankroll":         DEFAULT_BANKROLL,
            "daily_target":     DEFAULT_DAILY_TARGET,
            "stop_loss_pct":    DEFAULT_STOP_LOSS_PCT,
            "min_edge_pct":     DEFAULT_MIN_EDGE_PCT,
            "min_prob_pct":     DEFAULT_MIN_PROB_PCT,
            "kelly_fraction":   DEFAULT_KELLY_FRACTION,
            "max_stake_pct":    DEFAULT_MAX_STAKE_PCT,
            "min_matches_used": DEFAULT_MIN_MATCHES_USED,
            "commission_pct":   DEFAULT_COMMISSION_PCT,
        }
        try:
            ws = self.sh.worksheet("Money Management")
            vals = ws.row_values(4)
            if vals and len(vals) >= 8:
                def _sf(v, default):
                    try: return float(str(v).replace("€","").replace("%","").replace(",",".").strip())
                    except: return default
                config["bankroll"]         = _sf(vals[0], DEFAULT_BANKROLL)
                config["daily_target"]     = _sf(vals[1], DEFAULT_DAILY_TARGET)
                config["stop_loss_pct"]    = _sf(vals[2], DEFAULT_STOP_LOSS_PCT)
                config["min_edge_pct"]     = _sf(vals[3], DEFAULT_MIN_EDGE_PCT)
                config["min_prob_pct"]     = _sf(vals[4], DEFAULT_MIN_PROB_PCT)
                config["kelly_fraction"]   = _sf(vals[5], DEFAULT_KELLY_FRACTION)
                config["max_stake_pct"]    = _sf(vals[6], DEFAULT_MAX_STAKE_PCT)
                config["min_matches_used"] = int(_sf(vals[7], DEFAULT_MIN_MATCHES_USED))
                # Colonna K (indice 10): Commissione Betfair
                if len(vals) >= 11:
                    config["commission_pct"] = _sf(vals[10], DEFAULT_COMMISSION_PCT)
                # Feature flags (colonne aggiuntive se presenti)
                # Colonna L=11: use_dynamic_cal, M=12: use_hallucination_filter, N=13: use_trust_score
                if len(vals) >= 14:
                    for idx, flag_name in [(11, "use_dynamic_cal"), (12, "use_hallucination_filter"), (13, "use_trust_score")]:
                        flag_val = str(vals[idx]).strip().upper() if idx < len(vals) and vals[idx] else ""
                        if flag_val in ("TRUE", "1", "SÌ", "SI", "YES"):
                            EDGE_ENGINE_FLAGS[flag_name] = True
                        elif flag_val in ("FALSE", "0", "NO"):
                            EDGE_ENGINE_FLAGS[flag_name] = False
                        # Se vuoto, mantiene il default
                logger.info(f"Config caricata dal foglio: {config}")
                logger.info(f"Edge Engine Flags: {EDGE_ENGINE_FLAGS}")
        except Exception as e:
            logger.info(f"Config da foglio non disponibile, uso default: {e}")
        return config

    # ======================================================================
    #  CARICAMENTO DATI DINAMICI (Edge Engine v3.0)
    # ======================================================================
    def _load_dynamic_data(self):
        """Carica dynamic_cal.json e league_trust_scores.json all'avvio."""
        base = os.path.dirname(os.path.dirname(__file__))

        # --- Dynamic Calibration ---
        cal_path = os.path.join(base, "dynamic_cal.json")
        self._dynamic_cal = None
        if os.path.exists(cal_path):
            try:
                with open(cal_path, "r", encoding="utf-8") as f:
                    self._dynamic_cal = json.load(f)
                n_leagues = self._dynamic_cal.get("leagues_covered", 0)
                logger.info(f"📊 Dynamic calibration caricata ({n_leagues} leghe)")
            except Exception as e:
                logger.warning(f"⚠️ Errore lettura dynamic_cal.json: {e} — fallback su tabella statica")
                self._dynamic_cal = None
        else:
            logger.info("📊 dynamic_cal.json non trovato — fallback su tabella statica")

        # --- League Trust Scores ---
        trust_path = os.path.join(base, "league_trust_scores.json")
        self._trust_scores = None
        if os.path.exists(trust_path):
            try:
                with open(trust_path, "r", encoding="utf-8") as f:
                    self._trust_scores = json.load(f)
                n_scores = len(self._trust_scores.get("scores", {}))
                logger.info(f"📊 Trust scores caricati ({n_scores} leghe)")
            except Exception as e:
                logger.warning(f"⚠️ Errore lettura league_trust_scores.json: {e}")
                self._trust_scores = None
        else:
            logger.info("📊 league_trust_scores.json non trovato — nessun trust adjustment")

        # --- Divergence σ (per Z-Score) ---
        self._divergence_std = DEFAULT_DIVERGENCE_STD
        if self._dynamic_cal and "divergence_stats" in self._dynamic_cal:
            ds = self._dynamic_cal["divergence_stats"]
            self._divergence_std = ds.get("std", DEFAULT_DIVERGENCE_STD)
            logger.info(f"📊 Divergence σ = {self._divergence_std:.4f} (da {ds.get('n_samples', 0)} campioni)")

    # ======================================================================
    #  STATO GIORNALIERO
    # ======================================================================
    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    state = json.load(f)
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    if state.get("last_run_date") != today_str:
                        logger.info("Nuovo giorno → reset stato MM.")
                        return self._create_default_state()
                    # Ensure ML fields exist (backward compat)
                    state.setdefault("ml_bankroll", 1000.0)
                    state.setdefault("ml_total_profit", 0.0)
                    state.setdefault("ml_total_staked", 0.0)
                    state.setdefault("ml_events_played", 0)
                    state.setdefault("ml_events_won", 0)
                    state.setdefault("ml_events_lost", 0)
                    state.setdefault("ml_slots", {})
                    return state
            except Exception as e:
                logger.error(f"Errore lettura {STATE_FILE}: {e}")
        return self._create_default_state()

    def _create_default_state(self):
        return {
            "last_run_date": datetime.now().strftime("%Y-%m-%d"),
            "bankroll": self.config["bankroll"],
            "daily_target": self.config["daily_target"],
            "stop_loss": -(self.config["bankroll"] * self.config["stop_loss_pct"] / 100.0),
            "total_profit_today": 0.0,
            "total_staked_today": 0.0,
            "events_played": 0,
            "events_won": 0,
            "events_lost": 0,
            "slots": {},
            # --- ML Tracking (separato) ---
            "ml_bankroll": 1000.0,
            "ml_total_profit": 0.0,
            "ml_total_staked": 0.0,
            "ml_events_played": 0,
            "ml_events_won": 0,
            "ml_events_lost": 0,
            "ml_slots": {},
        }

    def _save_state(self):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=4, ensure_ascii=False)

    # ======================================================================
    #  EDGE SCANNER MULTI-MERCATO
    # ======================================================================
    def scan_best_market(self, analysis_data, odds_data, inputs_data=None, ai_data=None, league_id=None):
        min_edge = self.config["min_edge_pct"] / 100.0
        min_prob = self.config["min_prob_pct"] / 100.0
        min_matches = self.config["min_matches_used"]

        if inputs_data:
            h_used = inputs_data.get("home_matches_used", 0) or 0
            a_used = inputs_data.get("away_matches_used", 0) or 0
            if h_used < min_matches or a_used < min_matches:
                return {"market": None, "reason": f"Dati insufficienti (H:{h_used} A:{a_used})"}

        candidates = []
        for market_key, market_info in MARKET_MAP.items():
            prob = self._extract_nested(analysis_data, market_info["json_path"])
            ai_prob = self._extract_nested(ai_data or {}, market_info["ai_path"])
            
            if prob is None:
                continue
            if prob > 1:
                prob = prob / 100.0

            # Edge minimo controllato dal foglio Money Management (riga 4, col D)
            market_min_edge = self.config["min_edge_pct"] / 100.0

            # === CALIBRAZIONE: corregge la probabilità con dati storici ===
            cal_key = market_info.get("cal_key", market_key)
            prob_raw = prob
            prob, cal_source = self._apply_calibration(prob, cal_key, league_id=league_id)

            quota = odds_data.get(market_key)
            if quota is None or quota <= 1.01:
                continue

            # Applica commissione Betfair: quota_netta = (quota - 1) * (1 - comm%) + 1
            comm = self.config["commission_pct"] / 100.0
            quota_net = (quota - 1.0) * (1.0 - comm) + 1.0
            edge = (prob * quota_net) - 1.0
            
            # AI edge — solo informativo, NON blocca (A/B test indipendente)
            ai_edge = None
            if ai_prob is not None:
                if ai_prob > 1:
                    ai_prob = ai_prob / 100.0
                ai_edge = (ai_prob * quota_net) - 1.0
            
            if edge < market_min_edge or prob < min_prob:
                continue

            # Score basato SOLO su Poisson (indipendente da AI)
            score = edge * math.sqrt(prob)
            
            candidates.append({
                "market": market_key,
                "label": market_info["label"],
                "prob": round(prob, 4),
                "prob_raw": round(prob_raw, 4),
                "odds": quota,
                "edge": round(edge, 4),
                "ai_edge": round(ai_edge, 4) if ai_edge is not None else None,
                "score": round(score, 4),
                "cal_source": cal_source,
            })

        if not candidates:
            return {"market": None, "reason": f"Nessun Value Bet Concorde ({self.config['min_edge_pct']}% Edge Minimo Poisson)"}

        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]
        
        ai_edge_str = f"| AI Edge {best['ai_edge']*100:+.1f}%" if best.get("ai_edge") is not None else "(No AI)"
        best["reason"] = f"{best['label']} (Poisson Edge {best['edge']*100:+.1f}% {ai_edge_str}, Prob {best['prob']*100:.0f}%)"
        best["all_candidates"] = len(candidates)
        return best

    # ======================================================================
    #  EDGE SCANNER ML — Usa SOLO probabilità AI (no Poisson, no calibrazione)
    # ======================================================================
    def scan_best_market_ml(self, ai_data, odds_data, calibration_metrics=None):
        """Edge scanner basato SOLO su probabilità ML.
        Non usa calibrazione Poisson né filtro concordanza.
        Se calibration_metrics è fornito, scarta mercati con BSS < 0."""
        if not ai_data:
            return {"market": None, "reason": "Nessun dato AI disponibile"}

        comm = self.config["commission_pct"] / 100.0
        candidates = []

        for market_key, market_info in ML_MARKET_MAP.items():
            # Estrai probabilità dal dict AI
            prob = self._extract_nested(ai_data, market_info["ai_path"])
            if prob is None:
                continue
            if prob > 1:
                prob = prob / 100.0
            if prob < 0.01 or prob > 0.99:
                continue

            market_min_edge = market_info.get("min_edge", 5.0) / 100.0
            odds_key = market_info.get("odds_key", market_key)
            quota = odds_data.get(odds_key)
            if quota is None or quota <= 1.01:
                continue

            quota_net = (quota - 1.0) * (1.0 - comm) + 1.0
            edge = (prob * quota_net) - 1.0

            if edge < market_min_edge:
                continue

            # BSS gate: skip models below MIN_BSS_THRESHOLD (consistent
            # with confidence_gate.py MIN_BSS=0.12).  Was "bss < 0" which
            # allowed near-random models to bet.
            MIN_BSS_THRESHOLD = 0.12
            if calibration_metrics:
                ai_target = market_info.get("ai_target", "")
                brier = calibration_metrics.get(ai_target, {}).get("brier") if ai_target else None
                n_cls = market_info.get("n_classes", 2)
                if brier is not None:
                    brier_random = (n_cls - 1) / n_cls if n_cls > 1 else 0.5
                    bss = 1.0 - brier / brier_random if brier_random > 0 else None
                    if bss is not None and bss < MIN_BSS_THRESHOLD:
                        continue  # model below quality threshold, skip

            # Intelligent high-odds filter: score = edge × √prob.
            # High-odds selections (low prob) need proportionally stronger edge
            # to achieve the same score as low-odds selections.  No arbitrary
            # odds cap is imposed — a genuine +10% edge on odds 4.0 still passes.
            score = edge * math.sqrt(prob)
            if score < MIN_ML_SCORE_THRESHOLD:
                continue

            candidates.append({
                "market": market_key,
                "label": market_info["label"],
                "prob": round(prob, 4),
                "odds": quota,
                "edge": round(edge, 4),
                "score": round(score, 4),
            })

        if not candidates:
            return {"market": None, "reason": "Nessun Value Bet ML"}

        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]
        best["reason"] = f"{best['label']} (Edge ML {best['edge']*100:+.1f}%, Prob {best['prob']*100:.0f}%)"
        best["all_candidates"] = len(candidates)
        return best

    def _apply_calibration(self, prob, cal_key, league_id=None):
        """Applica correzione calibrazione con chain di lookup:
        1. dynamic_cal → by_league[league_id][cal_key][bin] (se disponibile)
        2. dynamic_cal → global[cal_key][bin]
        3. CALIBRATION_TABLE[cal_key][bin] (statico, fallback)
        Ritorna (prob_corretta, source) dove source indica quale livello è stato usato."""
        bin_idx = min(int(prob * 10), 9)
        correction = None
        source = "none"

        # --- Livello 1: Dinamico per lega ---
        if (EDGE_ENGINE_FLAGS.get("use_dynamic_cal", False)
                and self._dynamic_cal is not None and league_id is not None):
            league_cal = self._dynamic_cal.get("by_league", {}).get(str(league_id), {})
            market_bins = league_cal.get(cal_key, {})
            # I bin nel JSON dinamico hanno chiavi come interi (o stringhe)
            corr = market_bins.get(bin_idx, market_bins.get(str(bin_idx)))
            if corr is not None:
                correction = corr
                source = "league"

        # --- Livello 2: Dinamico globale ---
        if correction is None and EDGE_ENGINE_FLAGS.get("use_dynamic_cal", False) and self._dynamic_cal is not None:
            global_cal = self._dynamic_cal.get("global", {})
            market_bins = global_cal.get(cal_key, {})
            corr = market_bins.get(bin_idx, market_bins.get(str(bin_idx)))
            if corr is not None:
                correction = corr
                source = "global"

        # --- Livello 3: Statico (fallback) ---
        if correction is None:
            cal = CALIBRATION_TABLE.get(cal_key)
            if cal is not None:
                correction = cal.get(bin_idx, 1.0)
                source = "static"

        if correction is None:
            return prob, source

        corrected = prob * correction
        return max(0.01, min(corrected, 0.99)), source

    def _extract_nested(self, data, path):
        current = data
        for key in path:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        return current

    # ======================================================================
    #  CALCOLO STAKE — Kelly Criterion Frazionato
    # ======================================================================
    def calculate_kelly_stake(self, prob, odds, use_ml_bankroll=False,
                              brier_score=None, n_classes=2):
        """
        Calcola lo stake via Kelly Criterion frazionato.

        Se brier_score è fornito, applica il BSS-based Kelly Shrinkage:
            brier_random = (n_classes - 1) / n_classes
            BSS          = 1 - brier_score / brier_random   (clipped in [0, 1])
            kelly_frac   = kelly_frac_config × √BSS

        √BSS: la radice quadrata fornisce una scalatura graduale — un BSS di 0.0
        azzera completamente il Kelly (modello random = nessuna scommessa),
        mentre un BSS di 1.0 lascia il Kelly invariato.  Un BSS di 0.10 (soglia
        minima) riduce il Kelly di circa il 68%, contenendo l'esposizione sui
        modelli al limite dell'accettabilità.
        """
        bankroll = self.state.get("ml_bankroll", 1000.0) if use_ml_bankroll else self.state["bankroll"]
        kelly_frac = self.config["kelly_fraction"]
        max_pct = self.config["max_stake_pct"] / 100.0

        # BSS-based Kelly Shrinkage (active only when brier_score is provided)
        if brier_score is not None:
            brier_random = (n_classes - 1) / n_classes if n_classes > 1 else 0.5
            if brier_random > 0:
                bss = 1.0 - (brier_score / brier_random)
                bss = max(0.0, min(bss, 1.0))
                kelly_frac = kelly_frac * math.sqrt(bss)

        comm = self.config["commission_pct"] / 100.0
        odds_net = (odds - 1.0) * (1.0 - comm) + 1.0
        b = odds_net - 1.0
        p = prob
        q = 1.0 - p
        kelly_full = (b * p - q) / b if b > 0 else 0

        if kelly_full <= 0:
            return 0.0

        stake = bankroll * kelly_full * kelly_frac
        max_stake = bankroll * max_pct
        stake = min(stake, max_stake)
        stake = max(round(stake, 2), 1.0)
        return stake

    # ======================================================================
    #  SAFETY FILTERS — Edge Engine v3.0
    #  Applicati DOPO il calcolo Kelly, a livello di signal processing.
    # ======================================================================
    def _apply_safety_filters(self, stake, prob, odds, league_id=None, track="poisson"):
        """Applica Hallucination Filter (Sigma) e Trust Score (Omega) allo stake.
        track: "poisson" or "ml" — ML uses wider thresholds (different distribution).
        Ritorna (stake_finale, metadata_dict)."""
        meta = {
            "is_hallucination": False,
            "z_score": None,
            "divergence": None,
            "trust_score": 1.0,
            "safety_vault": False,
            "original_stake": stake,
        }

        if stake <= 0:
            return 0.0, meta

        # --- SIGMA: Hallucination Filter (Z-Score) ---
        if EDGE_ENGINE_FLAGS.get("use_hallucination_filter", False) and odds > 1.01:
            prob_market = (1.0 / odds) * OVERROUND_CORRECTION
            if prob_market > 0.01:
                divergence = (prob / prob_market) - 1.0
                z_score = abs(divergence) / self._divergence_std

                meta["divergence"] = round(divergence, 4)
                meta["z_score"] = round(z_score, 2)

                # ML track uses wider thresholds — ML probability distributions
                # diverge from market more than Poisson (different model family).
                if track == "ml":
                    div_thresh = 0.45
                    z_thresh = 2.5
                else:
                    div_thresh = 0.30
                    z_thresh = 2.0

                if divergence > div_thresh or z_score > z_thresh:
                    meta["is_hallucination"] = True
                    meta["safety_vault"] = True
                    logger.info(
                        f"    🚫 HALLUCINATION BLOCKED [{track}]: div={divergence:+.2f}, z={z_score:.2f} "
                        f"(thresh: div>{div_thresh}, z>{z_thresh}) → scommessa ANNULLATA (stake=0)"
                    )
                    return 0.0, meta

        # --- OMEGA: League Trust Score ---
        if EDGE_ENGINE_FLAGS.get("use_trust_score", False) and self._trust_scores is not None and league_id is not None:
            scores = self._trust_scores.get("scores", {})
            trust = scores.get(str(league_id), 1.0)  # default 1.0 se non trovata
            meta["trust_score"] = round(trust, 2)
            if trust != 1.0:
                stake = stake * trust
                logger.info(f"    📊 Trust Score lega {league_id}: {trust:.2f} → stake €{stake:.2f}")

        stake = max(round(stake, 2), 1.0)  # minimo €1
        return stake, meta

    # ======================================================================
    #  PROCESSAMENTO SEGNALI
    # ======================================================================
    def process_signals(self, signals_data):
        """Dual Track: processa segnali per Poisson E ML indipendentemente."""
        logger.info(f"📊 Processando {len(signals_data)} segnali — DUAL TRACK (Poisson + ML)...")

        if self.state["total_profit_today"] >= self.state["daily_target"]:
            logger.info("🎯 TARGET GIORNALIERO RAGGIUNTO!")
            return self._enrich_all(signals_data, "🎯 TARGET", 0)
        if self.state["total_profit_today"] <= self.state["stop_loss"]:
            logger.warning("🛑 STOP LOSS RAGGIUNTO!")
            return self._enrich_all(signals_data, "🛑 STOP", 0)

        # Poisson dedup
        existing_pois = set()
        for s in self.state["slots"].values():
            fid = s.get("fixture_id")
            if fid is not None:
                existing_pois.add(int(fid))
        # ML dedup
        existing_ml = set()
        for s in self.state.get("ml_slots", {}).values():
            fid = s.get("fixture_id")
            if fid is not None:
                existing_ml.add(int(fid))

        enriched = []
        pois_counter = len(self.state["slots"])
        ml_counter = len(self.state.get("ml_slots", {}))
        pois_accepted = 0
        ml_accepted = 0

        for signal in signals_data:
            sig_fid = signal.get("fixture_id")
            analysis_markets = signal.get("analysis_markets", {})
            ai_markets = signal.get("ai_markets", {})
            odds = signal.get("odds_data", {})
            inputs = signal.get("inputs_data", {})
            # Extracted here so it is available to both Poisson and ML tracks.
            sig_league_id = signal.get("league_id")

            # ===================== POISSON TRACK =====================
            pois_skip = (sig_fid is not None and int(sig_fid) in existing_pois)
            if pois_skip:
                signal["slot_id"] = "⊘ SKIP"
                signal["stake"] = ""
                signal["selected_market"] = ""
                signal["edge_pct"] = ""
                signal["score"] = ""
            else:
                scan = self.scan_best_market(analysis_markets, odds, inputs, ai_data=ai_markets, league_id=sig_league_id)
                if scan.get("market") is not None:
                    prob = scan["prob"]
                    stake = self.calculate_kelly_stake(prob, scan["odds"])
                    # Applica Safety Filters (Hallucination + Trust)
                    stake, safety_meta = self._apply_safety_filters(stake, prob, scan["odds"], league_id=sig_league_id)
                    cal_source = scan.get("cal_source", "static")
                    logger.info(
                        f"    Calibrazione: {cal_source} | Trust: {safety_meta['trust_score']} | "
                        f"Safety Vault: {'Attivo' if safety_meta['safety_vault'] else 'Inattivo'}"
                    )
                    if stake > 0:
                        pois_counter += 1
                        slot_id = f"S{pois_counter}"
                        self.state["slots"][slot_id] = {
                            "status": "PENDING",
                            "event_name": signal.get("name", "?"),
                            "event_id": signal.get("event_id", "?"),
                            "fixture_id": signal.get("fixture_id"),
                            "date": signal.get("date", ""),
                            "market": scan["market"],
                            "market_label": scan["label"],
                            "prob": scan["prob"],
                            "odds": scan["odds"],
                            "edge": scan["edge"],
                            "score": scan["score"],
                            "stake": stake,
                            "pnl": 0.0,
                            "result": "PENDING",
                        }
                        if sig_fid is not None:
                            existing_pois.add(int(sig_fid))
                        signal["slot_id"] = slot_id
                        signal["stake"] = stake
                        signal["selected_market"] = f"{scan['label']} @{scan['odds']}"
                        signal["edge_pct"] = f"'{scan['edge']*100:+.1f}%"
                        signal["score"] = f"{scan['score']:.3f}"
                        # Edge Engine v3.0 diagnostics
                        signal["cal_source"] = cal_source
                        signal["trust_score"] = safety_meta["trust_score"]
                        signal["safety_vault"] = safety_meta["safety_vault"]
                        signal["original_edge"] = scan["edge"]  # edge prima dei filtri
                        signal["z_score"] = safety_meta.get("z_score")
                        pois_accepted += 1
                    else:
                        signal["slot_id"] = "⊘ SKIP"
                        signal["stake"] = ""
                        signal["selected_market"] = ""
                        signal["edge_pct"] = ""
                        signal["score"] = ""
                else:
                    signal["slot_id"] = "⊘ SKIP"
                    signal["stake"] = ""
                    signal["selected_market"] = ""
                    signal["edge_pct"] = ""
                    signal["score"] = ""

            # ===================== ML TRACK =====================
            ml_skip = (sig_fid is not None and int(sig_fid) in existing_ml)
            if ml_skip:
                signal["ml_slot_id"] = "⊘ SKIP"
                signal["ml_stake"] = ""
                signal["ml_selected_market"] = ""
                signal["ml_edge_pct"] = ""
                signal["ml_score"] = ""
            else:
                ml_scan = self.scan_best_market_ml(ai_markets, odds, calibration_metrics=signal.get("calibration_metrics"))
                if ml_scan.get("market") is not None:
                    ml_prob = ml_scan["prob"]
                    ml_market_key = ml_scan.get("market", "")

                    # --- BSS-based Kelly Shrinkage ---
                    # Attempt to read the Brier score for the winning market from
                    # calibration_metrics if the orchestrator passes them in the
                    # signal dict.  Gracefully falls back to no shrinkage (None).
                    _cal_metrics = signal.get("calibration_metrics", {})
                    _ai_target = ML_MARKET_MAP.get(ml_market_key, {}).get("ai_target", "")
                    ml_brier_score = (
                        _cal_metrics.get(_ai_target, {}).get("brier")
                        if _ai_target else None
                    )
                    ml_n_classes = ML_MARKET_MAP.get(ml_market_key, {}).get("n_classes", 2)

                    ml_stake = self.calculate_kelly_stake(
                        ml_prob, ml_scan["odds"],
                        use_ml_bankroll=True,
                        brier_score=ml_brier_score,
                        n_classes=ml_n_classes,
                    )

                    # --- Safety Filters (previously ABSENT from ML track) ---
                    # Apply the same Hallucination Filter + Trust Score that the
                    # Poisson track applies.  If the signal is hallucinatory the
                    # filter returns stake=0 (hard block).
                    ml_stake, ml_safety_meta = self._apply_safety_filters(
                        ml_stake, ml_prob, ml_scan["odds"], league_id=sig_league_id,
                        track="ml",
                    )

                    if ml_stake > 0:
                        ml_counter += 1
                        ml_slot_id = f"M{ml_counter}"
                        if "ml_slots" not in self.state:
                            self.state["ml_slots"] = {}
                        self.state["ml_slots"][ml_slot_id] = {
                            "status": "PENDING",
                            "event_name": signal.get("name", "?"),
                            "event_id": signal.get("event_id", "?"),
                            "fixture_id": signal.get("fixture_id"),
                            "date": signal.get("date", ""),
                            "market": ml_scan["market"],
                            "market_label": ml_scan["label"],
                            "prob": ml_scan["prob"],
                            "odds": ml_scan["odds"],
                            "edge": ml_scan["edge"],
                            "score": ml_scan["score"],
                            "stake": ml_stake,
                            "z_score": ml_safety_meta.get("z_score"),
                            "trust_score": ml_safety_meta.get("trust_score", 1.0),
                            "brier_score": ml_brier_score,
                            "pnl": 0.0,
                            "result": "PENDING",
                        }
                        if sig_fid is not None:
                            existing_ml.add(int(sig_fid))
                        signal["ml_slot_id"] = ml_slot_id
                        signal["ml_stake"] = ml_stake
                        signal["ml_selected_market"] = f"{ml_scan['label']} @{ml_scan['odds']}"
                        signal["ml_edge_pct"] = f"'{ml_scan['edge']*100:+.1f}%"
                        signal["ml_score"] = f"{ml_scan['score']:.3f}"
                        signal["ml_z_score"] = ml_safety_meta.get("z_score")
                        signal["ml_trust_score"] = ml_safety_meta.get("trust_score", 1.0)
                        ml_accepted += 1
                    else:
                        signal["ml_slot_id"] = "⊘ SKIP"
                        signal["ml_stake"] = ""
                        signal["ml_selected_market"] = ""
                        signal["ml_edge_pct"] = ""
                        signal["ml_score"] = ""
                else:
                    signal["ml_slot_id"] = "⊘ SKIP"
                    signal["ml_stake"] = ""
                    signal["ml_selected_market"] = ""
                    signal["ml_edge_pct"] = ""
                    signal["ml_score"] = ""

            enriched.append(signal)

        # ── Correlated Kelly adjustment: reduce stake when multiple bets
        #    on the same fixture (e.g. 1x2 + BTTS on same match).
        ml_fixture_counts: dict = {}
        for sid, slot in self.state.get("ml_slots", {}).items():
            fid = slot.get("fixture_id")
            if fid is not None and slot.get("result") == "PENDING":
                ml_fixture_counts[int(fid)] = ml_fixture_counts.get(int(fid), 0) + 1
        for sid, slot in self.state.get("ml_slots", {}).items():
            fid = slot.get("fixture_id")
            if fid is not None and ml_fixture_counts.get(int(fid), 1) > 1:
                old_stake = slot["stake"]
                slot["stake"] = round(old_stake * 0.70, 2)
                logger.info(
                    f"    📉 Correlated Kelly: {sid} (fixture {fid}) "
                    f"stake {old_stake:.2f} → {slot['stake']:.2f} (-30%)"
                )

        logger.info(f"✅ Poisson accettati: {pois_accepted} | ML accettati: {ml_accepted} | Totale segnali: {len(signals_data)}")
        self._save_state()
        return enriched

    def _enrich_all(self, signals, slot_msg, stake):
        for s in signals:
            s["slot_id"] = slot_msg
            s["stake"] = stake
            s["selected_market"] = ""
            s["edge_pct"] = ""
            s["score"] = ""
            s["reason"] = slot_msg
            # ML fields
            s["ml_slot_id"] = slot_msg
            s["ml_stake"] = stake
            s["ml_selected_market"] = ""
            s["ml_edge_pct"] = ""
            s["ml_score"] = ""
        return signals

    # ======================================================================
    #  RISOLUZIONE RISULTATI DAL DATABASE
    # ======================================================================
    def resolve_results(self):
        """Controlla il DB per risolvere gli slot PENDING con risultati reali."""
        # === Ricalibra P&L degli slot GIÀ risolti con commissione attuale ===
        comm = self.config["commission_pct"] / 100.0
        recalibrated = 0
        pnl_adjustment = 0.0
        for sid, slot in self.state["slots"].items():
            if "VINTO" in str(slot.get("result", "")):
                stake = slot.get("stake", 0)
                odds = slot.get("odds", 1)
                correct_pnl = round(stake * (odds - 1) * (1.0 - comm), 2)
                if slot.get("pnl") != correct_pnl:
                    old_pnl = slot.get("pnl", 0)
                    slot["pnl"] = correct_pnl
                    pnl_adjustment += (correct_pnl - old_pnl)
                    recalibrated += 1
        if recalibrated > 0:
            self.state["total_profit_today"] += pnl_adjustment
            self._save_state()
            logger.info(f"📐 Ricalibrati {recalibrated} P&L state con commissione {self.config['commission_pct']}% (adj: {pnl_adjustment:+.2f}€).")

        sb = get_supabase_client()
        pending = {sid: s for sid, s in self.state["slots"].items() if s["result"] == "PENDING"}

        if not pending:
            logger.info("Nessuno slot PENDING da risolvere.")
            return

        # Raccoglie i fixture_id da controllare
        fixture_ids = []
        for sid, slot in pending.items():
            fid = slot.get("fixture_id")
            if fid:
                fixture_ids.append(int(fid))

        if not fixture_ids:
            logger.info("Nessun fixture_id nei slot PENDING.")
            return

        # Fetch match results dal DB (a chunk da 200)
        matches_map = {}
        for i in range(0, len(fixture_ids), 200):
            chunk = fixture_ids[i:i+200]
            resp = sb.table("matches").select(
                "fixture_id, status_short, goals_home, goals_away, halftime_home, halftime_away"
            ).in_("fixture_id", chunk).execute()
            for r in (getattr(resp, "data", None) or []):
                fid = r.get("fixture_id")
                if fid is not None:
                    matches_map[int(fid)] = r

        resolved_count = 0
        for sid, slot in pending.items():
            fid = slot.get("fixture_id")
            if not fid:
                continue

            match = matches_map.get(int(fid))
            if not match:
                continue

            status = str(match.get("status_short") or "").upper()
            if status not in ("FT", "AET", "PEN"):
                continue  # Partita non ancora finita

            # Determina se abbiamo vinto o perso
            won = self._evaluate_bet_result(slot, match)
            stake = slot["stake"]

            if won:
                comm = self.config["commission_pct"] / 100.0
                profit = stake * (slot["odds"] - 1) * (1.0 - comm)
                slot["result"] = "VINTO ✅"
                slot["pnl"] = round(profit, 2)
                self.state["events_won"] += 1
            else:
                slot["result"] = "PERSO ❌"
                slot["pnl"] = round(-stake, 2)
                self.state["events_lost"] += 1

            slot["status"] = "RESOLVED"
            self.state["events_played"] += 1
            self.state["total_profit_today"] += slot["pnl"]
            self.state["total_staked_today"] += stake
            resolved_count += 1

            logger.info(f"  {sid}: {slot['event_name']} → {slot['result']} (P&L: {slot['pnl']:+.2f}€)")

        if resolved_count > 0:
            self._save_state()
            logger.info(f"Risolti {resolved_count} slot. P&L totale oggi: {self.state['total_profit_today']:+.2f}€")

    def _evaluate_bet_result(self, slot, match):
        """Determina se la scommessa è stata vinta in base al mercato e al risultato."""
        market = slot["market"]
        gh = int(match.get("goals_home") or 0)
        ga = int(match.get("goals_away") or 0)
        hth = match.get("halftime_home")
        hta = match.get("halftime_away")

        if market == "H":
            return gh > ga
        elif market == "D":
            return gh == ga
        elif market == "A":
            return gh < ga
        elif market == "O25":
            return (gh + ga) >= 3
        elif market == "U25":
            return (gh + ga) < 3
        elif market == "BTTS":
            return gh >= 1 and ga >= 1
        elif market == "BTTS_NO":
            return gh == 0 or ga == 0
        elif market == "HT05":
            if hth is None or hta is None:
                return False
            return (int(hth) + int(hta)) >= 1
        elif market == "HT_U05":
            if hth is None or hta is None:
                return False
            return (int(hth) + int(hta)) == 0
        return False

    def resolve_ml_results(self):
        """Risolve gli ml_slots PENDING con risultati reali dal DB."""
        sb = get_supabase_client()
        ml_slots = self.state.get("ml_slots", {})
        pending = {sid: s for sid, s in ml_slots.items() if s.get("result") == "PENDING"}
        if not pending:
            logger.info("Nessun ml_slot PENDING da risolvere.")
            return

        fixture_ids = [int(s["fixture_id"]) for s in pending.values() if s.get("fixture_id")]
        if not fixture_ids:
            return

        matches_map = {}
        for i in range(0, len(fixture_ids), 200):
            chunk = fixture_ids[i:i+200]
            resp = sb.table("matches").select(
                "fixture_id, status_short, goals_home, goals_away, halftime_home, halftime_away"
            ).in_("fixture_id", chunk).execute()
            for r in (getattr(resp, "data", None) or []):
                fid = r.get("fixture_id")
                if fid is not None:
                    matches_map[int(fid)] = r

        comm = self.config["commission_pct"] / 100.0
        resolved = 0
        for sid, slot in pending.items():
            fid = slot.get("fixture_id")
            if not fid:
                continue
            match = matches_map.get(int(fid))
            if not match:
                continue
            status = str(match.get("status_short") or "").upper()
            if status not in ("FT", "AET", "PEN"):
                continue

            won = self._evaluate_bet_result(slot, match)
            stake = slot["stake"]
            if won:
                profit = stake * (slot["odds"] - 1) * (1.0 - comm)
                slot["result"] = "VINTO ✅"
                slot["pnl"] = round(profit, 2)
                self.state["ml_events_won"] = self.state.get("ml_events_won", 0) + 1
            else:
                slot["result"] = "PERSO ❌"
                slot["pnl"] = round(-stake, 2)
                self.state["ml_events_lost"] = self.state.get("ml_events_lost", 0) + 1

            slot["status"] = "RESOLVED"
            self.state["ml_events_played"] = self.state.get("ml_events_played", 0) + 1
            self.state["ml_total_profit"] = self.state.get("ml_total_profit", 0) + slot["pnl"]
            self.state["ml_total_staked"] = self.state.get("ml_total_staked", 0) + stake
            self.state["ml_bankroll"] = self.state.get("ml_bankroll", 1000.0) + slot["pnl"]
            resolved += 1
            logger.info(f"  ML {sid}: {slot['event_name']} → {slot['result']} (P&L: {slot['pnl']:+.2f}€)")

        if resolved > 0:
            self._save_state()
            logger.info(f"ML Risolti {resolved} slot. ML Bankroll: €{self.state.get('ml_bankroll', 1000.0):.2f}")

    # ======================================================================
    #  REPORT "VEN-DOM" — A/B Test Poisson vs ML
    # ======================================================================
    def update_report_sheet(self):
        """Genera il foglio 'Report Ven Dom' — Dashboard Edge Engine v3.0.
        Layout side-by-side: Poisson LEFT (A-G) | ML RIGHT (H-N)."""
        logger.info("📋 Generazione Report Dashboard v3.0...")

        try:
            history = self._load_history()

            try:
                ws = self.sh.worksheet("Report Ven Dom")
                _sheets_retry(ws.clear)
                # Unmerge tutte le celle unite per un foglio pulito
                try:
                    _sheets_retry(self.sh.batch_update, {"requests": [
                        {"unmergeCells": {"range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 2000, "startColumnIndex": 0, "endColumnIndex": 14}}}
                    ]})
                except Exception:
                    pass  # Se non ci sono merge, ignora
            except gspread.exceptions.WorksheetNotFound:
                ws = self.sh.add_worksheet(title="Report Ven Dom", rows=2000, cols=14)

            sheet_id = ws.id
            all_data = []
            format_requests = []
            COLS = 14

            # --- Helper ---
            def add_row(values):
                row_idx = len(all_data)
                padded = list(values) + [""] * (COLS - len(values))
                all_data.append(padded[:COLS])
                return row_idx

            def add_fmt(row_idx, end_row, fmt, c1=0, c2=COLS):
                format_requests.append({"repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": row_idx, "endRowIndex": end_row + 1, "startColumnIndex": c1, "endColumnIndex": c2},
                    "cell": {"userEnteredFormat": fmt}, "fields": "userEnteredFormat"}})

            def add_merge(row_idx, c1=0, c2=COLS):
                format_requests.append({"mergeCells": {
                    "range": {"sheetId": sheet_id, "startRowIndex": row_idx, "endRowIndex": row_idx + 1, "startColumnIndex": c1, "endColumnIndex": c2},
                    "mergeType": "MERGE_ALL"}})

            # --- Colors ---
            DARK_BG = {"red": 0.06, "green": 0.06, "blue": 0.12}
            WHITE = {"red": 1, "green": 1, "blue": 1}
            GOLD = {"red": 1, "green": 0.84, "blue": 0}
            POIS_BG = {"red": 0.1, "green": 0.3, "blue": 0.15}
            POIS_HEADER = {"red": 0.85, "green": 0.93, "blue": 0.85}
            POIS_LIGHT = {"red": 0.93, "green": 0.97, "blue": 0.93}
            ML_BG = {"red": 0.2, "green": 0.1, "blue": 0.35}
            ML_HEADER = {"red": 0.88, "green": 0.85, "blue": 0.95}
            ML_LIGHT = {"red": 0.95, "green": 0.93, "blue": 0.98}
            STATS_BG = {"red": 0.95, "green": 0.95, "blue": 0.95}
            WIN_BG = {"red": 0.85, "green": 0.95, "blue": 0.85}
            LOSS_BG = {"red": 0.97, "green": 0.87, "blue": 0.87}
            PEND_BG = {"red": 0.96, "green": 0.96, "blue": 0.96}
            GREEN_TXT = {"red": 0.05, "green": 0.5, "blue": 0.05}
            RED_TXT = {"red": 0.7, "green": 0.1, "blue": 0.1}

            # --- Aggregate stats ---
            all_pois_slots = []
            all_ml_slots = []
            daily_dates = set()
            for day in history:
                daily_dates.add(day["date"])
                all_pois_slots.extend(day.get("slots", []))
                all_ml_slots.extend(day.get("ml_slots", []))

            def calc_stats(slots, bankroll_start):
                pnl = sum(s.get("pnl", 0) for s in slots if s.get("result") != "PENDING")
                staked = sum(s.get("stake", 0) for s in slots if s.get("result") != "PENDING")
                won = sum(1 for s in slots if "VINTO" in str(s.get("result", "")))
                lost = sum(1 for s in slots if "PERSO" in str(s.get("result", "")))
                pending = sum(1 for s in slots if s.get("result") == "PENDING")
                played = won + lost
                wr = f"{won/played*100:.1f}%" if played > 0 else "—"
                yld = f"{pnl/staked*100:.2f}%" if staked > 0 else "—"
                return {"pnl": pnl, "staked": staked, "won": won, "lost": lost, "pending": pending,
                        "total": len(slots), "played": played, "wr": wr, "yield": yld,
                        "bankroll": bankroll_start + pnl}

            pois_st = calc_stats(all_pois_slots, self.config["bankroll"])
            ml_st = calc_stats(all_ml_slots, 1000.0)

            # ═══════════════════════════════════════════════════════════════
            # ROW 1: TITOLO (merge full width)
            # ═══════════════════════════════════════════════════════════════
            r = add_row(["📊 EDGE ENGINE v3.0 — POISSON vs ML"])
            add_merge(r, 0, COLS)
            add_fmt(r, r, {"backgroundColor": DARK_BG,
                "textFormat": {"foregroundColor": GOLD, "bold": True, "fontSize": 16},
                "horizontalAlignment": "CENTER"})

            # ═══════════════════════════════════════════════════════════════
            # ROW 2-3: SEZIONE KPI — Poisson LEFT (A-G) | ML RIGHT (H-N)
            # ═══════════════════════════════════════════════════════════════
            # Headers
            r = add_row(["📈 POISSON", "", "", "", "", "", "",
                         "🤖 MACHINE LEARNING", "", "", "", "", "", ""])
            add_merge(r, 0, 7)
            add_merge(r, 7, 14)
            add_fmt(r, r, {"backgroundColor": POIS_BG,
                "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 13},
                "horizontalAlignment": "CENTER"}, 0, 7)
            add_fmt(r, r, {"backgroundColor": ML_BG,
                "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 13},
                "horizontalAlignment": "CENTER"}, 7, 14)

            # KPI Labels
            r = add_row(["P&L", "Yield", "Win Rate", "Vinte", "Perse", "Pend.", "Giorni",
                         "P&L", "Yield", "Win Rate", "Vinte", "Perse", "Pend.", "Giorni"])
            add_fmt(r, r, {"backgroundColor": STATS_BG,
                "textFormat": {"bold": True, "fontSize": 9, "foregroundColor": {"red": 0.3, "green": 0.3, "blue": 0.3}},
                "horizontalAlignment": "CENTER"})

            # KPI Values
            pois_pnl_c = GREEN_TXT if pois_st["pnl"] >= 0 else RED_TXT
            ml_pnl_c = GREEN_TXT if ml_st["pnl"] >= 0 else RED_TXT
            r = add_row([
                f"€{pois_st['pnl']:+.2f}", pois_st["yield"], pois_st["wr"],
                pois_st["won"], pois_st["lost"], pois_st["pending"], len(daily_dates),
                f"€{ml_st['pnl']:+.2f}", ml_st["yield"], ml_st["wr"],
                ml_st["won"], ml_st["lost"], ml_st["pending"], len(daily_dates),
            ])
            add_fmt(r, r, {"textFormat": {"bold": True, "fontSize": 11}, "horizontalAlignment": "CENTER"})
            add_fmt(r, r, {"textFormat": {"bold": True, "fontSize": 14, "foregroundColor": pois_pnl_c}}, 0, 1)
            add_fmt(r, r, {"textFormat": {"bold": True, "fontSize": 14, "foregroundColor": ml_pnl_c}}, 7, 8)
            add_fmt(r, r, {"backgroundColor": POIS_LIGHT}, 0, 7)
            add_fmt(r, r, {"backgroundColor": ML_LIGHT}, 7, 14)

            # Separator
            add_row([""])

            # ═══════════════════════════════════════════════════════════════
            # DAILY SECTIONS — Side by side: Poisson in cols A-G, ML in cols H-N
            # ═══════════════════════════════════════════════════════════════
            sorted_days = sorted(history, key=lambda d: d["date"])

            for day in sorted_days:
                pois_slots = day.get("slots", [])
                ml_slots = day.get("ml_slots", [])
                if not pois_slots and not ml_slots:
                    continue

                date_str = day["date"]
                p_count = len(pois_slots)
                m_count = len(ml_slots)
                max_count = max(p_count, m_count)

                # --- Date header ---
                r = add_row([f"📅 {date_str} — {p_count} Poisson", "", "", "", "", "", "",
                             f"📅 {date_str} — {m_count} ML"])
                add_merge(r, 0, 7)
                add_merge(r, 7, 14)
                add_fmt(r, r, {"backgroundColor": POIS_BG,
                    "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 10},
                    "horizontalAlignment": "CENTER"}, 0, 7)
                add_fmt(r, r, {"backgroundColor": ML_BG,
                    "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 10},
                    "horizontalAlignment": "CENTER"}, 7, 14)

                # --- Column headers ---
                r = add_row(["#", "Evento", "Mercato", "Quota", "Edge", "Stake", "Risultato",
                             "#", "Evento", "Mercato", "Quota", "Edge", "Stake", "Risultato"])
                add_fmt(r, r, {"backgroundColor": POIS_HEADER,
                    "textFormat": {"bold": True, "fontSize": 9}, "horizontalAlignment": "CENTER"}, 0, 7)
                add_fmt(r, r, {"backgroundColor": ML_HEADER,
                    "textFormat": {"bold": True, "fontSize": 9}, "horizontalAlignment": "CENTER"}, 7, 14)

                # --- Data rows (parallel: Poisson LEFT, ML RIGHT) ---
                first_data = len(all_data)
                for i in range(max_count):
                    row = [""] * COLS
                    # Poisson (cols 0-6)
                    if i < p_count:
                        s = pois_slots[i]
                        s_pnl = s.get("pnl", 0)
                        is_pend = s.get("result") == "PENDING"
                        result_str = s.get("result", "PENDING")
                        if is_pend:
                            result_str = "PENDING"
                        row[0] = s.get("slot_id", "")
                        row[1] = s.get("event_name", "")
                        row[2] = s.get("market_label", "")
                        row[3] = s.get("odds", "")
                        row[4] = f"{s.get('edge', 0)*100:+.1f}%"
                        row[5] = f"€{s.get('stake', 0):.2f}"
                        row[6] = f"{result_str} {f'€{s_pnl:+.2f}' if not is_pend else ''}"
                    # ML (cols 7-13)
                    if i < m_count:
                        s = ml_slots[i]
                        s_pnl = s.get("pnl", 0)
                        is_pend = s.get("result") == "PENDING"
                        result_str = s.get("result", "PENDING")
                        if is_pend:
                            result_str = "PENDING"
                        row[7] = s.get("slot_id", "")
                        row[8] = s.get("event_name", "")
                        row[9] = s.get("market_label", "")
                        row[10] = s.get("odds", "")
                        row[11] = f"{s.get('edge', 0)*100:+.1f}%"
                        row[12] = f"€{s.get('stake', 0):.2f}"
                        row[13] = f"{result_str} {f'€{s_pnl:+.2f}' if not is_pend else ''}"

                    ri = add_row(row)

                    # Poisson row coloring
                    if i < p_count:
                        res = str(pois_slots[i].get("result", ""))
                        if "VINTO" in res:
                            add_fmt(ri, ri, {"backgroundColor": WIN_BG}, 0, 7)
                        elif "PERSO" in res:
                            add_fmt(ri, ri, {"backgroundColor": LOSS_BG}, 0, 7)
                        else:
                            add_fmt(ri, ri, {"backgroundColor": PEND_BG}, 0, 7)
                    # ML row coloring
                    if i < m_count:
                        res = str(ml_slots[i].get("result", ""))
                        if "VINTO" in res:
                            add_fmt(ri, ri, {"backgroundColor": WIN_BG}, 7, 14)
                        elif "PERSO" in res:
                            add_fmt(ri, ri, {"backgroundColor": LOSS_BG}, 7, 14)
                        else:
                            add_fmt(ri, ri, {"backgroundColor": ML_LIGHT}, 7, 14)

                last_data = len(all_data) - 1
                if last_data >= first_data:
                    add_fmt(first_data, last_data, {
                        "horizontalAlignment": "CENTER", "textFormat": {"fontSize": 9}})

                # --- Daily totals row ---
                def day_totals(slots):
                    d_pnl = sum(s.get("pnl", 0) for s in slots if s.get("result") != "PENDING")
                    d_stk = sum(s.get("stake", 0) for s in slots if s.get("result") != "PENDING")
                    d_won = sum(1 for s in slots if "VINTO" in str(s.get("result", "")))
                    d_played = sum(1 for s in slots if s.get("result") != "PENDING")
                    d_wr = f"{d_won/d_played*100:.0f}%" if d_played > 0 else "—"
                    return d_pnl, d_stk, d_wr

                p_pnl, p_stk, p_wr = day_totals(pois_slots)
                m_pnl, m_stk, m_wr = day_totals(ml_slots)

                r = add_row([
                    "", f"TOTALE", p_wr, "", "", f"€{p_stk:.2f}", f"€{p_pnl:+.2f}",
                    "", f"TOTALE", m_wr, "", "", f"€{m_stk:.2f}", f"€{m_pnl:+.2f}",
                ])
                p_c = GREEN_TXT if p_pnl >= 0 else RED_TXT
                m_c = GREEN_TXT if m_pnl >= 0 else RED_TXT
                add_fmt(r, r, {"backgroundColor": POIS_HEADER,
                    "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": p_c},
                    "horizontalAlignment": "CENTER"}, 0, 7)
                add_fmt(r, r, {"backgroundColor": ML_HEADER,
                    "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": m_c},
                    "horizontalAlignment": "CENTER"}, 7, 14)

                # Separator between days
                add_row([""])

            # ═══════════════════════════════════════════════════════════════
            # CONCORDANCES — Bottom section
            # ═══════════════════════════════════════════════════════════════
            n_conc = 0
            conc_list = []
            for day in history:
                p_by_f = {int(s.get("fixture_id", 0)): s for s in day.get("slots", []) if s.get("fixture_id")}
                m_by_f = {int(s.get("fixture_id", 0)): s for s in day.get("ml_slots", []) if s.get("fixture_id")}
                for fid in p_by_f:
                    if fid in m_by_f and p_by_f[fid].get("market") == m_by_f[fid].get("market"):
                        n_conc += 1
                        p_slot = p_by_f[fid]
                        m_slot = m_by_f[fid]
                        
                        stake_tot = p_slot.get("stake", 0) + m_slot.get("stake", 0)
                        
                        is_pend = p_slot.get("result", "PENDING") == "PENDING"
                        if is_pend:
                            res_str = "PENDING"
                            pnl_tot = 0
                        else:
                            res_str = str(p_slot.get("result", ""))
                            pnl_tot = p_slot.get("pnl", 0) + m_slot.get("pnl", 0)
                        
                        conc_list.append({
                            "date": day["date"],
                            "event": p_slot.get("event_name", "?"),
                            "market": p_slot.get("market_label", "?"),
                            "odds": p_slot.get("odds", ""),
                            "stake_tot": stake_tot,
                            "result": res_str,
                            "pnl_tot": pnl_tot,
                            "is_pend": is_pend
                        })

            if n_conc > 0:
                add_row([""])
                r = add_row([f"🤝 CONCORDANZE: {n_conc} selezioni identiche Poisson + ML"])
                add_merge(r, 0, COLS)
                CONC_TITLE_BG = {"red": 1.0, "green": 0.93, "blue": 0.6}
                add_fmt(r, r, {"backgroundColor": CONC_TITLE_BG, "textFormat": {"bold": True, "fontSize": 12}, "horizontalAlignment": "CENTER"})
                
                r = add_row(["Data", "", "Evento", "", "Mercato", "", "Quota", "", "Stake Totale", "", "Risultato", "", "P&L Totale", ""])
                for i in range(0, 14, 2): add_merge(r, i, i+2)
                CONC_HEADER_BG = {"red": 1.0, "green": 0.88, "blue": 0.4}
                add_fmt(r, r, {"backgroundColor": CONC_HEADER_BG, "textFormat": {"bold": True, "fontSize": 10}, "horizontalAlignment": "CENTER"})
                
                conc_pnl_tot = 0
                conc_stake_tot = 0
                conc_won = 0
                conc_played = 0

                for c in conc_list:
                    r = add_row([
                        c["date"], "",
                        c["event"], "",
                        c["market"], "",
                        c["odds"], "",
                        f"€{c['stake_tot']:.2f}", "",
                        c["result"], "",
                        f"€{c['pnl_tot']:+.2f}" if not c['is_pend'] else "", ""
                    ])
                    for i in range(0, 14, 2): add_merge(r, i, i+2)
                    
                    if not c['is_pend']:
                        conc_pnl_tot += c["pnl_tot"]
                        conc_stake_tot += c["stake_tot"]
                        conc_played += 1
                        if "VINTO" in c["result"]:
                            conc_won += 1
                    
                    if "VINTO" in c["result"]:
                        add_fmt(r, r, {"backgroundColor": WIN_BG}, 0, COLS)
                    elif "PERSO" in c["result"]:
                        add_fmt(r, r, {"backgroundColor": LOSS_BG}, 0, COLS)
                    else:
                        add_fmt(r, r, {"backgroundColor": {"red": 1.0, "green": 0.97, "blue": 0.85}}, 0, COLS)
                
                conc_wr = f"{(conc_won/conc_played)*100:.1f}%" if conc_played > 0 else "—"
                r = add_row(["", "", "TOTALE CONCORDANZE", "", conc_wr, "", "", "", f"€{conc_stake_tot:.2f}", "", "", "", f"€{conc_pnl_tot:+.2f}", ""])
                add_merge(r, 0, 2)
                for i in range(2, 14, 2): add_merge(r, i, i+2)
                
                c_pnl_color = GREEN_TXT if conc_pnl_tot >= 0 else RED_TXT
                add_fmt(r, r, {"backgroundColor": CONC_HEADER_BG, "textFormat": {"bold": True, "fontSize": 11, "foregroundColor": {"red": 0.3, "green": 0.3, "blue": 0.3}}, "horizontalAlignment": "CENTER"}, 0, 12)
                add_fmt(r, r, {"backgroundColor": CONC_HEADER_BG, "textFormat": {"bold": True, "fontSize": 11, "foregroundColor": c_pnl_color}, "horizontalAlignment": "CENTER"}, 12, 14)

            # ═══════════════════════════════════════════════════════════════
            # WRITE E CLEANUP RESIDUI
            # ═══════════════════════════════════════════════════════════════
            end_row = len(all_data)
            
            # --- Forza pulizia completa (dati e unioni) da end_row in poi ---
            # Questo garantisce che non ci siano "rimanenze" dei giorni precedenti
            # o della vecchia impaginazione dalla riga 92 in giù (esempio).
            if end_row < 2000:
                format_requests.append({
                    "unmergeCells": {
                        "range": {"sheetId": sheet_id, "startRowIndex": end_row, "endRowIndex": 2000, "startColumnIndex": 0, "endColumnIndex": COLS}
                    }
                })
                # Resetta sfondo e testo a default per le celle non usate
                format_requests.append({
                    "repeatCell": {
                        "range": {"sheetId": sheet_id, "startRowIndex": end_row, "endRowIndex": 2000, "startColumnIndex": 0, "endColumnIndex": COLS},
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 1, "green": 1, "blue": 1},
                                "textFormat": {"foregroundColor": {"red": 0, "green": 0, "blue": 0}, "bold": False, "fontSize": 10}
                            }
                        },
                        "fields": "userEnteredFormat"
                    }
                })

            if all_data:
                _sheets_retry(ws.update, f"A1:N{end_row}", all_data)
                time_module.sleep(2)
                
            # Azzera i valori dalle righe successive
            if end_row < 2000:
                 empty_chunk = [[""] * COLS] * (2000 - end_row)
                 # Usare update così massivo può essere lento, quindi usiamo batch_clear
                 _sheets_retry(ws.batch_clear, [f"A{end_row+1}:N2000"])
                 time_module.sleep(1)

            if format_requests:
                # Batch in chunks of 100 to avoid API limits
                for i in range(0, len(format_requests), 100):
                    chunk = format_requests[i:i+100]
                    _sheets_retry(self.sh.batch_update, {"requests": chunk})
                    time_module.sleep(1)

            _sheets_retry(ws.freeze, rows=1)
            _sheets_retry(ws.columns_auto_resize, 0, COLS - 1)

            logger.info(f"✅ Dashboard v3.0: {len(all_pois_slots)} Poisson + {len(all_ml_slots)} ML, {n_conc} concordanze.")
        except Exception as e:
            logger.error(f"Errore Dashboard v3.0: {e}", exc_info=True)


    #  HISTORY — Persistenza multi-giorno
    # ======================================================================
    def _load_history(self):
        """Carica lo storico multi-giorno da file JSON."""
        history_file = os.path.join(os.path.dirname(__file__), "mm_history.json")
        if os.path.exists(history_file):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return []

    def _save_history(self, history):
        history_file = os.path.join(os.path.dirname(__file__), "mm_history.json")
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4, ensure_ascii=False)

    def save_today_to_history(self):
        """Salva gli slot Poisson + ML di oggi nello storico multi-giorno.
        Deduplica per fixture_id."""
        today = self.state["last_run_date"]
        history = self._load_history()

        # Poisson slots
        today_slots = []
        for sid, s in sorted(self.state["slots"].items()):
            today_slots.append({
                "slot_id": sid,
                "event_name": s.get("event_name", ""),
                "fixture_id": s.get("fixture_id"),
                "market": s.get("market", ""),
                "market_label": s.get("market_label", ""),
                "prob": s.get("prob", 0),
                "odds": s.get("odds", 0),
                "edge": s.get("edge", 0),
                "score": s.get("score", 0),
                "stake": s.get("stake", 0),
                "result": s.get("result", "PENDING"),
                "pnl": s.get("pnl", 0),
                "goals_home": s.get("goals_home", "—"),
                "goals_away": s.get("goals_away", "—"),
                "ht_total": s.get("ht_total", "—"),
            })
        today_slots = self._deduplicate_slots(today_slots)

        # ML slots
        today_ml_slots = []
        for sid, s in sorted(self.state.get("ml_slots", {}).items()):
            today_ml_slots.append({
                "slot_id": sid,
                "event_name": s.get("event_name", ""),
                "fixture_id": s.get("fixture_id"),
                "market": s.get("market", ""),
                "market_label": s.get("market_label", ""),
                "prob": s.get("prob", 0),
                "odds": s.get("odds", 0),
                "edge": s.get("edge", 0),
                "score": s.get("score", 0),
                "stake": s.get("stake", 0),
                "result": s.get("result", "PENDING"),
                "pnl": s.get("pnl", 0),
                "goals_home": s.get("goals_home", "—"),
                "goals_away": s.get("goals_away", "—"),
                "ht_total": s.get("ht_total", "—"),
            })
        today_ml_slots = self._deduplicate_slots(today_ml_slots)

        # Aggiorna o aggiungi il giorno
        found = False
        for day in history:
            if day["date"] == today:
                day["slots"] = today_slots
                day["ml_slots"] = today_ml_slots
                found = True
                break
        if not found:
            history.append({"date": today, "slots": today_slots, "ml_slots": today_ml_slots})

        self._save_history(history)
        logger.info(f"Storico aggiornato: {today} — {len(today_slots)} Poisson + {len(today_ml_slots)} ML slots.")

    @staticmethod
    def _deduplicate_slots(slots):
        """Deduplica una lista di slot per fixture_id.
        Per ogni fixture_id tiene l'entry risolta (VINTO/PERSO) se esiste,
        altrimenti la prima entry PENDING."""
        by_fid = {}
        for s in slots:
            fid = s.get("fixture_id")
            if fid is None:
                # Slot senza fixture_id: tieni sempre
                by_fid[id(s)] = s
                continue
            fid = int(fid)
            existing = by_fid.get(fid)
            if existing is None:
                by_fid[fid] = s
            else:
                # Preferisci entry risolta su PENDING
                if s.get("result") != "PENDING" and existing.get("result") == "PENDING":
                    by_fid[fid] = s
        result = list(by_fid.values())
        if len(result) < len(slots):
            logger.info(f"🔄 Deduplicati {len(slots) - len(result)} slot duplicati (per fixture_id).")
        return result

    def resolve_history_results(self):
        """Risolve i risultati PENDING di TUTTI i giorni nello storico.
        Questo è il metodo chiave: quando lanci lo script sabato mattina,
        risolve automaticamente i risultati di venerdì."""
        sb = get_supabase_client()
        history = self._load_history()

        if not history:
            logger.info("Nessuno storico da risolvere.")
            return

        # === Ricalibra P&L storico con commissione attuale ===
        comm = self.config["commission_pct"] / 100.0
        recalibrated = 0
        for day in history:
            for slot in day.get("slots", []):
                if "VINTO" in str(slot.get("result", "")):
                    stake = slot.get("stake", 0)
                    odds = slot.get("odds", 1)
                    correct_pnl = round(stake * (odds - 1) * (1.0 - comm), 2)
                    if slot.get("pnl") != correct_pnl:
                        slot["pnl"] = correct_pnl
                        recalibrated += 1
        if recalibrated > 0:
            logger.info(f"📐 Ricalibrati {recalibrated} P&L storici con commissione {self.config['commission_pct']}%.")

        # Raccoglie tutti i fixture_id PENDING
        pending_fixtures = {}
        for day in history:
            for slot in day.get("slots", []):
                if slot.get("result") == "PENDING" and slot.get("fixture_id"):
                    pending_fixtures[int(slot["fixture_id"])] = (day, slot)

        if not pending_fixtures:
            if recalibrated > 0:
                self._save_history(history)
            logger.info("Nessun risultato PENDING nello storico.")
            return

        logger.info(f"Risolvo {len(pending_fixtures)} risultati PENDING dallo storico...")

        # Fetch dal DB
        ids = list(pending_fixtures.keys())
        matches_map = {}
        for i in range(0, len(ids), 200):
            chunk = ids[i:i+200]
            resp = sb.table("matches").select(
                "fixture_id, status_short, goals_home, goals_away, halftime_home, halftime_away"
            ).in_("fixture_id", chunk).execute()
            for r in (getattr(resp, "data", None) or []):
                fid = r.get("fixture_id")
                if fid is not None:
                    matches_map[int(fid)] = r

        resolved = 0
        for fid, (day, slot) in pending_fixtures.items():
            match = matches_map.get(fid)
            if not match:
                continue

            status = str(match.get("status_short") or "").upper()
            if status not in ("FT", "AET", "PEN"):
                continue

            gh = int(match.get("goals_home") or 0)
            ga = int(match.get("goals_away") or 0)
            hth = match.get("halftime_home")
            hta = match.get("halftime_away")

            slot["goals_home"] = gh
            slot["goals_away"] = ga
            slot["ht_total"] = (int(hth or 0) + int(hta or 0)) if hth is not None else "—"

            won = self._evaluate_bet_result(slot, match)
            stake = slot["stake"]

            if won:
                comm = self.config["commission_pct"] / 100.0
                profit = stake * (slot["odds"] - 1) * (1.0 - comm)
                slot["result"] = "VINTO ✅"
                slot["pnl"] = round(profit, 2)
            else:
                slot["result"] = "PERSO ❌"
                slot["pnl"] = round(-stake, 2)

            resolved += 1
            logger.info(f"  {slot['slot_id']}: {slot['event_name']} → {slot['result']} ({slot['pnl']:+.2f}€)")

        # === Risolvi anche ML SLOTS nello storico ===
        ml_pending = {}
        for day in history:
            for slot in day.get("ml_slots", []):
                if slot.get("result") == "PENDING" and slot.get("fixture_id"):
                    fid = int(slot["fixture_id"])
                    ml_pending[fid] = (day, slot)
                    if fid not in matches_map:
                        # Need to fetch
                        pass

        # Fetch any missing ML fixture IDs
        ml_missing = [fid for fid in ml_pending if fid not in matches_map]
        if ml_missing:
            for i in range(0, len(ml_missing), 200):
                chunk = ml_missing[i:i+200]
                resp = sb.table("matches").select(
                    "fixture_id, status_short, goals_home, goals_away, halftime_home, halftime_away"
                ).in_("fixture_id", chunk).execute()
                for r in (getattr(resp, "data", None) or []):
                    fid = r.get("fixture_id")
                    if fid is not None:
                        matches_map[int(fid)] = r

        ml_resolved = 0
        for fid, (day, slot) in ml_pending.items():
            match = matches_map.get(fid)
            if not match:
                continue
            status = str(match.get("status_short") or "").upper()
            if status not in ("FT", "AET", "PEN"):
                continue

            slot["goals_home"] = int(match.get("goals_home") or 0)
            slot["goals_away"] = int(match.get("goals_away") or 0)
            hth = match.get("halftime_home")
            hta = match.get("halftime_away")
            slot["ht_total"] = (int(hth or 0) + int(hta or 0)) if hth is not None else "—"

            won = self._evaluate_bet_result(slot, match)
            stake = slot["stake"]
            if won:
                comm = self.config["commission_pct"] / 100.0
                profit = stake * (slot["odds"] - 1) * (1.0 - comm)
                slot["result"] = "VINTO ✅"
                slot["pnl"] = round(profit, 2)
            else:
                slot["result"] = "PERSO ❌"
                slot["pnl"] = round(-stake, 2)

            ml_resolved += 1
            logger.info(f"  ML {slot['slot_id']}: {slot['event_name']} → {slot['result']} ({slot['pnl']:+.2f}€)")

        total_resolved = resolved + ml_resolved
        if total_resolved > 0 or recalibrated > 0:
            self._save_history(history)
            logger.info(f"✅ Risolti {resolved} Poisson + {ml_resolved} ML risultati dallo storico.")

    # ======================================================================
    #  DASHBOARD GOOGLE SHEETS
    # ======================================================================
    def update_dashboard_sheet(self):
        """Dashboard Money Management — OTTIMIZZATO con batch_update."""
        logger.info("🎨 Generazione Dashboard Money Management...")
        try:
            try:
                ws = self.sh.worksheet("Money Management")
                _sheets_retry(ws.clear)
            except gspread.exceptions.WorksheetNotFound:
                ws = self.sh.add_worksheet(title="Money Management", rows=1500, cols=20)

            sheet_id = ws.id

            # === Calcola tutti i dati ===
            global_status = "🟢 OPERATIVO"
            if self.state["total_profit_today"] >= self.state["daily_target"]:
                global_status = "🎯 TARGET"
            elif self.state["total_profit_today"] <= self.state["stop_loss"]:
                global_status = "🛑 STOP"

            tp = self.state["events_played"]
            won = self.state["events_won"]
            lost = self.state["events_lost"]
            turn = self.state["total_staked_today"]
            prf = self.state["total_profit_today"]
            wr = f"{(won/tp*100):.1f}%" if tp > 0 else "N/A"
            yl = f"{(prf/turn*100):.2f}%" if turn > 0 else "N/A"

            # === FASE 1: Prepara griglia dati completa ===
            all_data = [
                # Riga 1: Titolo
                ["🏦 QUANT FUND — MONEY MANAGEMENT ENGINE v2.0"] + [""] * 10,
                # Riga 2: Sottotitolo config
                ["⚙️ PARAMETRI CONFIGURABILI (modifica i valori in riga 4)"] + [""] * 10,
                # Riga 3: Header config
                ["Bankroll (€)", "Target (€)", "StopLoss (%)", "Edge Min (%)", "Prob Min (%)", "Kelly Frac", "Max Stake (%)", "Min Match", "Modalità", "Stato", "Comm. BF (%)"],
                # Riga 4: Valori config
                [self.config["bankroll"], self.config["daily_target"], self.config["stop_loss_pct"],
                 self.config["min_edge_pct"], self.config["min_prob_pct"], self.config["kelly_fraction"],
                 self.config["max_stake_pct"], self.config["min_matches_used"], "PAPER TRADING", global_status, self.config["commission_pct"]],
                # Riga 5: vuota
                [""] * 11,
                # Riga 6: Titolo P&L
                ["📊 P&L GIORNALIERO"] + [""] * 10,
                # Riga 7: Header P&L
                ["Data", "Bankroll", "P&L Oggi", "Turnover", "Bet", "Vinte", "Perse", "Win Rate", "Yield", "Dist. Target", ""],
                # Riga 8: Valori P&L
                [self.state["last_run_date"], f"€{self.state['bankroll']+prf:.2f}", f"€{prf:+.2f}", f"€{turn:.2f}", tp, won, lost, wr, yl, f"€{self.config['daily_target']-prf:.2f}", ""],
                # Riga 9: vuota
                [""] * 11,
                # Riga 10: Titolo Operazioni
                ["🎰 OPERAZIONI"] + [""] * 10,
                # Riga 11: Header slot
                ["Slot", "Evento", "Mercato", "Prob", "Quota", "Edge", "Score", "Stake €", "Risultato", "P&L €", ""],
            ]

            # Righe slot Poisson (da riga 12 in poi)
            slots = self.state.get("slots", {})
            slot_rows = []
            for sid, d in sorted(slots.items()):
                slot_rows.append([
                    sid, d.get("event_name",""), d.get("market_label",""),
                    f"{d.get('prob',0)*100:.0f}%", d.get("odds",""),
                    f"{d.get('edge',0)*100:+.1f}%", f"{d.get('score',0):.3f}",
                    f"€{d.get('stake',0):.2f}", d.get("result","PENDING"), f"€{d.get('pnl',0):+.2f}"
                ])
            all_data.extend(slot_rows)

            # Sezione ML Track
            ml_slots = self.state.get("ml_slots", {})
            if ml_slots:
                ml_pnl = sum(s.get("pnl", 0) for s in ml_slots.values())
                ml_staked = sum(s.get("stake", 0) for s in ml_slots.values() if s.get("result") != "PENDING")
                ml_won = sum(1 for s in ml_slots.values() if "VINTO" in str(s.get("result", "")))
                ml_lost = sum(1 for s in ml_slots.values() if "PERSO" in str(s.get("result", "")))
                all_data.append([""] * 11)
                all_data.append([f"🤖 ML TRACK — P&L: €{ml_pnl:+.2f} | Bet: {len(ml_slots)} | Vinte: {ml_won} | Perse: {ml_lost}"] + [""] * 10)
                all_data.append(["Slot", "Evento", "Mercato", "Prob", "Quota", "Edge", "Score", "Stake €", "Risultato", "P&L €", "BSS"])
                for sid, d in sorted(ml_slots.items()):
                    brier = d.get("brier_score")
                    n_cls = 2
                    bss_str = ""
                    if brier is not None:
                        brier_random = (n_cls - 1) / n_cls
                        bss = 1.0 - brier / brier_random if brier_random > 0 else None
                        bss_str = f"{bss:.3f}" if bss is not None else ""
                    all_data.append([
                        sid, d.get("event_name",""), d.get("market_label",""),
                        f"{d.get('prob',0)*100:.0f}%", d.get("odds",""),
                        f"{d.get('edge',0)*100:+.1f}%", f"{d.get('score',0):.3f}",
                        f"€{d.get('stake',0):.2f}", d.get("result","PENDING"), f"€{d.get('pnl',0):+.2f}", bss_str
                    ])

            # === FASE 2: Scrivi TUTTI i dati in UNA chiamata ===
            end_row = len(all_data)
            _sheets_retry(ws.update, f"A1:K{end_row}", all_data)
            time_module.sleep(2)

            # === FASE 3: Prepara TUTTA la formattazione batch ===
            pc = {"red": 0.1, "green": 0.6, "blue": 0.1} if prf >= 0 else {"red": 0.7, "green": 0.1, "blue": 0.1}

            fmt_requests = [
                # Riga 1: Titolo
                {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 11}, "mergeType": "MERGE_ALL"}},
                {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 11},
                    "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.05, "green": 0.05, "blue": 0.18}, "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 14}, "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"}}, "fields": "userEnteredFormat"}},
                # Riga 2: Config titolo
                {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 0, "endColumnIndex": 11}, "mergeType": "MERGE_ALL"}},
                {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 0, "endColumnIndex": 11},
                    "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.15, "green": 0.15, "blue": 0.15}, "textFormat": {"foregroundColor": {"red": 0.9, "green": 0.75, "blue": 0.3}, "bold": True, "fontSize": 11}, "horizontalAlignment": "CENTER"}}, "fields": "userEnteredFormat"}},
                # Riga 3: Config header
                {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 2, "endRowIndex": 3, "startColumnIndex": 0, "endColumnIndex": 11},
                    "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.85, "green": 0.85, "blue": 0.85}, "textFormat": {"bold": True, "fontSize": 9}, "horizontalAlignment": "CENTER"}}, "fields": "userEnteredFormat"}},
                # Riga 4: Config valori
                {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 3, "endRowIndex": 4, "startColumnIndex": 0, "endColumnIndex": 11},
                    "cell": {"userEnteredFormat": {"backgroundColor": {"red": 1, "green": 1, "blue": 0.9}, "textFormat": {"bold": True, "fontSize": 10}, "horizontalAlignment": "CENTER"}}, "fields": "userEnteredFormat"}},
                # Riga 6: P&L titolo
                {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 5, "endRowIndex": 6, "startColumnIndex": 0, "endColumnIndex": 11}, "mergeType": "MERGE_ALL"}},
                {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 5, "endRowIndex": 6, "startColumnIndex": 0, "endColumnIndex": 11},
                    "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.1, "green": 0.1, "blue": 0.3}, "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 11}, "horizontalAlignment": "CENTER"}}, "fields": "userEnteredFormat"}},
                # Riga 7: P&L header
                {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 6, "endRowIndex": 7, "startColumnIndex": 0, "endColumnIndex": 11},
                    "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}, "textFormat": {"bold": True, "fontSize": 9}, "horizontalAlignment": "CENTER"}}, "fields": "userEnteredFormat"}},
                # Riga 8: P&L valori
                {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 7, "endRowIndex": 8, "startColumnIndex": 0, "endColumnIndex": 11},
                    "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER", "textFormat": {"bold": True}}}, "fields": "userEnteredFormat"}},
                # Riga 8 colonna C: colore P&L
                {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 7, "endRowIndex": 8, "startColumnIndex": 2, "endColumnIndex": 3},
                    "cell": {"userEnteredFormat": {"textFormat": {"foregroundColor": pc, "bold": True, "fontSize": 12}}}, "fields": "userEnteredFormat"}},
                # Riga 10: Operazioni titolo
                {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 9, "endRowIndex": 10, "startColumnIndex": 0, "endColumnIndex": 11}, "mergeType": "MERGE_ALL"}},
                {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 9, "endRowIndex": 10, "startColumnIndex": 0, "endColumnIndex": 11},
                    "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2}, "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 11}, "horizontalAlignment": "CENTER"}}, "fields": "userEnteredFormat"}},
                # Riga 11: Slot header
                {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 10, "endRowIndex": 11, "startColumnIndex": 0, "endColumnIndex": 11},
                    "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.85, "green": 0.85, "blue": 0.88}, "textFormat": {"bold": True, "fontSize": 9}, "horizontalAlignment": "CENTER"}}, "fields": "userEnteredFormat"}},
            ]

            # Formattazione righe dati slot
            if slot_rows:
                fmt_requests.append({
                    "repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 11, "endRowIndex": 11 + len(slot_rows), "startColumnIndex": 0, "endColumnIndex": 11},
                        "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER", "textFormat": {"fontSize": 9}}}, "fields": "userEnteredFormat"}
                })

            # Freeze
            fmt_requests.append({
                "updateSheetProperties": {
                    "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                    "fields": "gridProperties.frozenRowCount"
                }
            })

            _sheets_retry(self.sh.batch_update, {"requests": fmt_requests})
            time_module.sleep(1)

            # Auto-resize (non disponibile come batch)
            _sheets_retry(ws.columns_auto_resize, 0, 10)

            # DROPDOWNS (chiamate separate, ma con retry)
            if HAS_FORMATTING:
                try:
                    time_module.sleep(1)
                    set_data_validation_for_cell_range(ws, "F4", DataValidationRule(BooleanCondition("ONE_OF_LIST", ["0.25", "0.33", "0.50"]), showCustomUi=True))
                    set_data_validation_for_cell_range(ws, "D4", DataValidationRule(BooleanCondition("ONE_OF_LIST", ["3", "5", "7", "10", "15"]), showCustomUi=True))
                    set_data_validation_for_cell_range(ws, "E4", DataValidationRule(BooleanCondition("ONE_OF_LIST", ["50", "55", "60", "65", "70"]), showCustomUi=True))
                    set_data_validation_for_cell_range(ws, "I4", DataValidationRule(BooleanCondition("ONE_OF_LIST", ["PAPER TRADING", "LIVE"]), showCustomUi=True))
                    # Dropdown per Commissione Betfair (colonna K)
                    set_data_validation_for_cell_range(ws, "K4", DataValidationRule(BooleanCondition("ONE_OF_LIST", ["0", "2", "3", "4", "5", "6", "7", "8"]), showCustomUi=True))
                    logger.info("Menu a tendina OK.")
                except Exception as e:
                    logger.warning(f"Dropdown falliti: {e}")

            logger.info(f"✅ Dashboard OK: {len(slot_rows)} operazioni — {len(fmt_requests)} formattazioni in batch.")
        except Exception as e:
            logger.error(f"Errore dashboard: {e}", exc_info=True)

