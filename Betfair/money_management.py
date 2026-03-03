"""
=============================================================================
  QUANT FUND — Money Management Engine v2.0
  Sistema di Money Management a Slot Paralleli Dinamici con:
  - Edge Scanner Multi-Mercato (6 mercati)
  - Confidence-Adjusted Edge Score (Edge × √Prob)
  - Kelly Criterion Frazionato (configurabile)
  - Risoluzione Risultati automatica dal DB
  - Report "Ven-Dom" su Google Sheets
  - Dashboard Professionale su Google Sheets
=============================================================================
"""

import json
import os
import math
import logging
import time as time_module
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
DEFAULT_MIN_EDGE_PCT = 2.0       # A/B Test: lowered to collect more data (era 8%)
DEFAULT_MIN_PROB_PCT = 30.0      # A/B Test: lowered to allow more signals (era 58%)
DEFAULT_KELLY_FRACTION = 0.15    # Conservativo (era 0.25)
DEFAULT_MAX_STAKE_PCT = 2.0      # Max 2% bankroll per slot (era 3%)
DEFAULT_MIN_MATCHES_USED = 2     # A/B Test: lowered from 5
DEFAULT_COMMISSION_PCT = 5.0  # Commissione Betfair sulle vincite (%)

STATE_FILE = os.path.join(os.path.dirname(__file__), "money_management_state.json")

MARKET_MAP = {
    # --- A/B Test: tutti i min_edge a 2.0 per raccogliere dati ---
    "H":       {"label": "Home Win",      "json_path": ("markets", "1x2", "H"),                      "ai_path": ("target_1x2", "H"), "cal_key": "H", "min_edge": 2.0},
    "D":       {"label": "Pareggio",      "json_path": ("markets", "1x2", "D"),                      "ai_path": ("target_1x2", "D"), "cal_key": "D", "min_edge": 2.0},
    "A":       {"label": "Away Win",      "json_path": ("markets", "1x2", "A"),                      "ai_path": ("target_1x2", "A"), "cal_key": "A", "min_edge": 2.0},
    "O25":     {"label": "Over 2.5",      "json_path": ("markets", "over_2_5", "True"),              "ai_path": ("target_over_2_5", "True"), "cal_key": "O25", "min_edge": 2.0},
    "U25":     {"label": "Under 2.5",     "json_path": ("markets", "over_2_5", "False"),             "ai_path": ("target_over_2_5", "False"), "cal_key": "U25", "min_edge": 2.0},
    "BTTS":    {"label": "BTTS Sì",       "json_path": ("markets", "btts", "True"),                  "ai_path": ("target_btts", "True"), "cal_key": "BTTS", "min_edge": 2.0},
    "BTTS_NO": {"label": "BTTS No",       "json_path": ("markets", "btts", "False"),                 "ai_path": ("target_btts", "False"), "cal_key": "BTTS_NO", "min_edge": 2.0},
    "HT05":    {"label": "1H Over 0.5",   "json_path": ("markets", "first_half_over_0_5", "True"),   "ai_path": ("target_ht_over_0_5", "True"), "cal_key": "HT05", "min_edge": 2.0},
}

# ---------------------------------------------------------------------------
#  MARKET MAP per ML — usa probabilità AI direttamente (no calibrazione Poisson)
#  Copre gli stessi mercati con odds disponibili su Betfair.
# ---------------------------------------------------------------------------
ML_MARKET_MAP = {
    # --- A/B Test: tutti a 2.0 per catturare più segnali ---
    "H":       {"label": "Home Win (ML)",   "ai_path": ("target_1x2", "H"),                     "odds_key": "H",    "min_edge": 2.0},
    "D":       {"label": "Pareggio (ML)",   "ai_path": ("target_1x2", "D"),                     "odds_key": "D",    "min_edge": 2.0},
    "A":       {"label": "Away Win (ML)",   "ai_path": ("target_1x2", "A"),                     "odds_key": "A",    "min_edge": 2.0},
    "O25":     {"label": "Over 2.5 (ML)",   "ai_path": ("target_over_2_5", "True"),              "odds_key": "O25",  "min_edge": 2.0},
    "U25":     {"label": "Under 2.5 (ML)",  "ai_path": ("target_over_2_5", "False"),             "odds_key": "U25",  "min_edge": 2.0},
    "BTTS":    {"label": "BTTS Sì (ML)",    "ai_path": ("target_btts", "True"),                  "odds_key": "BTTS", "min_edge": 2.0},
    "BTTS_NO": {"label": "BTTS No (ML)",    "ai_path": ("target_btts", "False"),                 "odds_key": "BTTS_NO","min_edge": 2.0},
    "HT05":    {"label": "1H Over 0.5 (ML)","ai_path": ("target_ht_over_0_5", "True"),           "odds_key": "HT05", "min_edge": 2.0},
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
                logger.info(f"Config caricata dal foglio: {config}")
        except Exception as e:
            logger.info(f"Config da foglio non disponibile, uso default: {e}")
        return config

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
    def scan_best_market(self, analysis_data, odds_data, inputs_data=None, ai_data=None):
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

            # Usa l'edge minimo specifico del mercato se definito, altrimenti usa il default
            market_min_edge = market_info.get("min_edge", self.config["min_edge_pct"]) / 100.0

            # === CALIBRAZIONE: corregge la probabilità con dati storici ===
            cal_key = market_info.get("cal_key", market_key)
            prob_raw = prob
            prob = self._apply_calibration(prob, cal_key)

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
    def scan_best_market_ml(self, ai_data, odds_data):
        """Edge scanner basato SOLO su probabilità ML.
        Non usa calibrazione Poisson né filtro concordanza."""
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

            score = edge * math.sqrt(prob)
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

    @staticmethod
    def _apply_calibration(prob, cal_key):
        """Applica correzione calibrazione bin-level alla probabilità.
        Basata su 24,787 match storici — corregge bias sistematici del modello Poisson."""
        cal = CALIBRATION_TABLE.get(cal_key)
        if cal is None:
            return prob
        bin_idx = min(int(prob * 10), 9)
        correction = cal.get(bin_idx, 1.0)
        corrected = prob * correction
        return max(0.01, min(corrected, 0.99))

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
    def calculate_kelly_stake(self, prob, odds, use_ml_bankroll=False):
        bankroll = self.state.get("ml_bankroll", 1000.0) if use_ml_bankroll else self.state["bankroll"]
        kelly_frac = self.config["kelly_fraction"]
        max_pct = self.config["max_stake_pct"] / 100.0

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

            # ===================== POISSON TRACK =====================
            pois_skip = (sig_fid is not None and int(sig_fid) in existing_pois)
            if pois_skip:
                signal["slot_id"] = "⊘ SKIP"
                signal["stake"] = ""
                signal["selected_market"] = ""
                signal["edge_pct"] = ""
                signal["score"] = ""
            else:
                scan = self.scan_best_market(analysis_markets, odds, inputs, ai_data=ai_markets)
                if scan.get("market") is not None:
                    prob = scan["prob"]
                    stake = self.calculate_kelly_stake(prob, scan["odds"])
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
                ml_scan = self.scan_best_market_ml(ai_markets, odds)
                if ml_scan.get("market") is not None:
                    ml_prob = ml_scan["prob"]
                    ml_stake = self.calculate_kelly_stake(ml_prob, ml_scan["odds"], use_ml_bankroll=True)
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
        """Genera il foglio 'Report Ven Dom' — Dashboard professionale A/B Test.
        Layout verticale: KPI Scorecard → Sezione Poisson → Sezione ML."""
        logger.info("📋 Generazione Report Dashboard A/B Test...")

        try:
            history = self._load_history()

            try:
                ws = self.sh.worksheet("Report Ven Dom")
                _sheets_retry(ws.clear)
            except gspread.exceptions.WorksheetNotFound:
                ws = self.sh.add_worksheet(title="Report Ven Dom", rows=2000, cols=14)

            sheet_id = ws.id
            all_data = []
            format_requests = []
            COLS = 14

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

            # Colors
            DARK_BG = {"red": 0.08, "green": 0.08, "blue": 0.14}
            WHITE = {"red": 1, "green": 1, "blue": 1}
            POIS_BG = {"red": 0.12, "green": 0.32, "blue": 0.18}
            POIS_LIGHT = {"red": 0.9, "green": 0.96, "blue": 0.9}
            ML_BG = {"red": 0.22, "green": 0.12, "blue": 0.38}
            ML_LIGHT = {"red": 0.93, "green": 0.9, "blue": 0.97}
            HEADER_BG = {"red": 0.2, "green": 0.2, "blue": 0.25}
            WIN_BG = {"red": 0.85, "green": 0.95, "blue": 0.85}
            LOSS_BG = {"red": 0.97, "green": 0.87, "blue": 0.87}
            PEND_BG = {"red": 0.96, "green": 0.96, "blue": 0.96}
            GREEN_TXT = {"red": 0.1, "green": 0.55, "blue": 0.1}
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
                wr = f"{won/played*100:.1f}%" if played > 0 else "N/A"
                yld = f"{pnl/staked*100:.2f}%" if staked > 0 else "N/A"
                return {"pnl": pnl, "staked": staked, "won": won, "lost": lost, "pending": pending,
                        "total": len(slots), "played": played, "wr": wr, "yield": yld,
                        "bankroll": bankroll_start + pnl}

            pois_st = calc_stats(all_pois_slots, self.config["bankroll"])
            ml_st = calc_stats(all_ml_slots, 1000.0)

            # ═══════════ TITLE ═══════════
            r = add_row(["📊 DASHBOARD A/B TEST — POISSON vs ML"])
            add_merge(r)
            add_fmt(r, r, {"backgroundColor": DARK_BG,
                "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 16},
                "horizontalAlignment": "CENTER"})

            add_row([""])

            # ═══════════ KPI SCORECARD ═══════════
            r = add_row(["", "📈 POISSON", "", "", "", "", "", "🤖 MACHINE LEARNING"])
            add_merge(r, 1, 7)
            add_merge(r, 7, 14)
            add_fmt(r, r, {"backgroundColor": POIS_BG,
                "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 13},
                "horizontalAlignment": "CENTER"}, 1, 7)
            add_fmt(r, r, {"backgroundColor": ML_BG,
                "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 13},
                "horizontalAlignment": "CENTER"}, 7, 14)
            add_fmt(r, r, {"backgroundColor": DARK_BG}, 0, 1)

            kpi_labels = ["", "Bankroll", "P&L", "Win Rate", "Yield", "Eventi", "Pend.",
                          "Bankroll", "P&L", "Win Rate", "Yield", "Eventi", "Pend.", ""]
            r = add_row(kpi_labels)
            add_fmt(r, r, {"textFormat": {"bold": True, "fontSize": 9,
                "foregroundColor": {"red": 0.4, "green": 0.4, "blue": 0.4}},
                "horizontalAlignment": "CENTER",
                "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95}})

            pois_pnl_c = GREEN_TXT if pois_st["pnl"] >= 0 else RED_TXT
            ml_pnl_c = GREEN_TXT if ml_st["pnl"] >= 0 else RED_TXT
            kpi_vals = ["",
                f"€{pois_st['bankroll']:.2f}", f"€{pois_st['pnl']:+.2f}",
                pois_st["wr"], pois_st["yield"], pois_st["total"], pois_st["pending"],
                f"€{ml_st['bankroll']:.2f}", f"€{ml_st['pnl']:+.2f}",
                ml_st["wr"], ml_st["yield"], ml_st["total"], ml_st["pending"], ""]
            r = add_row(kpi_vals)
            add_fmt(r, r, {"textFormat": {"bold": True, "fontSize": 12}, "horizontalAlignment": "CENTER"})
            add_fmt(r, r, {"textFormat": {"bold": True, "fontSize": 14, "foregroundColor": pois_pnl_c}}, 2, 3)
            add_fmt(r, r, {"textFormat": {"bold": True, "fontSize": 14, "foregroundColor": ml_pnl_c}}, 8, 9)

            r = add_row(["", f"Giorni: {len(daily_dates)}", "",
                f"V:{pois_st['won']} P:{pois_st['lost']}", "", "", "",
                f"Giorni: {len(daily_dates)}", "",
                f"V:{ml_st['won']} P:{ml_st['lost']}"])
            add_fmt(r, r, {"textFormat": {"fontSize": 9,
                "foregroundColor": {"red": 0.5, "green": 0.5, "blue": 0.5}},
                "horizontalAlignment": "CENTER"})

            add_row([""])

            # ═══════════ HELPER: render section ═══════════
            def render_section(label, bg_color, light_bg, slots_key, bankroll_start):
                r = add_row([f"  {label}"])
                add_merge(r)
                add_fmt(r, r, {"backgroundColor": bg_color,
                    "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 13},
                    "horizontalAlignment": "CENTER"})

                running_pnl = 0.0
                for day in sorted(history, key=lambda d: d["date"]):
                    slots = day.get(slots_key, [])
                    if not slots:
                        continue
                    date_str = day["date"]

                    r = add_row([f"� {date_str}  —  {len(slots)} selezioni"])
                    add_merge(r)
                    add_fmt(r, r, {"backgroundColor": HEADER_BG,
                        "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 10},
                        "horizontalAlignment": "LEFT"})

                    hdrs = ["#", "Evento", "Mercato", "Prob", "Quota", "Edge",
                            "Score", "Stake €", "Risultato", "P&L €", "Cassa"]
                    r = add_row(hdrs)
                    add_fmt(r, r, {"backgroundColor": light_bg,
                        "textFormat": {"bold": True, "fontSize": 9}, "horizontalAlignment": "CENTER"})

                    first_data = len(all_data)
                    for s in slots:
                        s_pnl = s.get("pnl", 0)
                        is_pend = s.get("result") == "PENDING"
                        if not is_pend:
                            running_pnl += s_pnl
                        rv = [
                            s.get("slot_id", ""), s.get("event_name", ""),
                            s.get("market_label", ""), f"{s.get('prob', 0)*100:.0f}%",
                            s.get("odds", ""), f"{s.get('edge', 0)*100:+.1f}%",
                            f"{s.get('score', 0):.3f}", f"€{s.get('stake', 0):.2f}",
                            s.get("result", "PENDING"),
                            f"€{s_pnl:+.2f}" if not is_pend else "—",
                            f"€{bankroll_start + running_pnl:.2f}" if not is_pend else "—",
                        ]
                        ri = add_row(rv)
                        res_str = str(s.get("result", ""))
                        if "VINTO" in res_str:
                            add_fmt(ri, ri, {"backgroundColor": WIN_BG}, 0, COLS)
                        elif "PERSO" in res_str:
                            add_fmt(ri, ri, {"backgroundColor": LOSS_BG}, 0, COLS)
                        else:
                            add_fmt(ri, ri, {"backgroundColor": PEND_BG}, 0, COLS)

                    last_data = len(all_data) - 1
                    if last_data >= first_data:
                        add_fmt(first_data, last_data, {
                            "horizontalAlignment": "CENTER", "textFormat": {"fontSize": 9}})

                    d_pnl = sum(s.get("pnl", 0) for s in slots if s.get("result") != "PENDING")
                    d_stk = sum(s.get("stake", 0) for s in slots if s.get("result") != "PENDING")
                    d_won = sum(1 for s in slots if "VINTO" in str(s.get("result", "")))
                    d_played = sum(1 for s in slots if s.get("result") != "PENDING")
                    d_wr = f"{d_won/d_played*100:.0f}%" if d_played > 0 else "—"
                    sr = ["", f"TOTALE {date_str}", "", "", "", "", "",
                          f"€{d_stk:.2f}", d_wr, f"€{d_pnl:+.2f}",
                          f"€{bankroll_start + running_pnl:.2f}"]
                    r = add_row(sr)
                    c = GREEN_TXT if d_pnl >= 0 else RED_TXT
                    add_fmt(r, r, {"backgroundColor": light_bg,
                        "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": c},
                        "horizontalAlignment": "CENTER"})

                add_row([""])

            # ═══════════ RENDER ═══════════
            render_section("📈 SEZIONE POISSON — Analisi Statistica", POIS_BG, POIS_LIGHT, "slots", self.config["bankroll"])
            render_section("🤖 SEZIONE ML — Machine Learning", ML_BG, ML_LIGHT, "ml_slots", 1000.0)

            # ═══════════ CONCORDANCES ═══════════
            n_conc = 0
            conc_details = []
            for day in history:
                p_by_f = {int(s.get("fixture_id", 0)): s for s in day.get("slots", []) if s.get("fixture_id")}
                m_by_f = {int(s.get("fixture_id", 0)): s for s in day.get("ml_slots", []) if s.get("fixture_id")}
                for fid in p_by_f:
                    if fid in m_by_f and p_by_f[fid].get("market") == m_by_f[fid].get("market"):
                        n_conc += 1
                        conc_details.append(f"{p_by_f[fid].get('event_name','?')} → {p_by_f[fid].get('market_label','?')}")

            if n_conc > 0:
                r = add_row([f"🤝 CONCORDANZE: {n_conc} selezioni identiche Poisson + ML"])
                add_merge(r)
                add_fmt(r, r, {"backgroundColor": {"red": 1.0, "green": 0.95, "blue": 0.7},
                    "textFormat": {"bold": True, "fontSize": 11}, "horizontalAlignment": "CENTER"})
                for detail in conc_details[:10]:
                    r = add_row([f"  → {detail}"])
                    add_merge(r)
                    add_fmt(r, r, {"backgroundColor": {"red": 1.0, "green": 0.97, "blue": 0.85},
                        "textFormat": {"fontSize": 9}, "horizontalAlignment": "LEFT"})

            # ═══════════ WRITE ═══════════
            if all_data:
                _sheets_retry(ws.update, f"A1:N{len(all_data)}", all_data)
                time_module.sleep(2)
            if format_requests:
                _sheets_retry(self.sh.batch_update, {"requests": format_requests})
                time_module.sleep(1)

            _sheets_retry(ws.freeze, rows=1)
            _sheets_retry(ws.columns_auto_resize, 0, COLS - 1)

            logger.info(f"✅ Dashboard A/B: {len(all_pois_slots)} Poisson + {len(all_ml_slots)} ML, {n_conc} concordanze.")
        except Exception as e:
            logger.error(f"Errore Dashboard A/B: {e}", exc_info=True)


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

            # Righe slot (da riga 12 in poi)
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

