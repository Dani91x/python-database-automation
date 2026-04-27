"""
=============================================================================
  QUANT FUND — Money Management Engine v3.0 (Edge Engine)
  Sistema di Money Management a Slot Paralleli Dinamici con:
  - Edge Scanner Multi-Mercato (15 mercati Poisson + 15 ML)
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
import re
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
#  TABELLA DI CALIBRAZIONE — Aggiornata il 2026-04-27 da update_poisson_calibration.py
#  Derivata da 49832 match storici
#  Per ogni mercato e fascia di probabilità: fattore correttivo = WR_reale / Prob_stimata
#  Applicato PRIMA del calcolo dell'edge per usare probabilità realistiche.
# ---------------------------------------------------------------------------
CALIBRATION_TABLE = {
    # 1X2 Home — aggiornato da update_poisson_calibration.py
    "H": {0: 0.305, 1: 0.774, 2: 1.047, 3: 0.995, 4: 1.009, 5: 1.016, 6: 0.999, 7: 1.135, 8: 1.196, 9: 1.0},
    # 1X2 Draw
    "D": {0: 1.0, 1: 0.88, 2: 0.965, 3: 0.962, 4: 1.017, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0, 9: 1.0},
    # 1X2 Away
    "A": {0: 0.643, 1: 1.028, 2: 1.008, 3: 1.009, 4: 1.049, 5: 1.072, 6: 1.01, 7: 1.143, 8: 1.0, 9: 1.0},
    # Over 2.5
    "O25": {0: 2.597, 1: 1.585, 2: 1.269, 3: 1.206, 4: 1.077, 5: 0.993, 6: 0.949, 7: 0.912, 8: 0.851, 9: 1.0},
    # Under 2.5
    "U25": {0: 1.0, 1: 1.729, 2: 1.254, 3: 1.091, 4: 1.008, 5: 0.938, 6: 0.885, 7: 0.906, 8: 0.884, 9: 0.881},
    # BTTS Si
    "BTTS": {0: 1.0, 1: 1.498, 2: 1.273, 3: 1.207, 4: 1.036, 5: 0.964, 6: 0.862, 7: 0.799, 8: 0.845, 9: 1.0},
    # BTTS No
    "BTTS_NO": {0: 1.0, 1: 1.749, 2: 1.557, 3: 1.249, 4: 1.043, 5: 0.971, 6: 0.884, 7: 0.899, 8: 0.908, 9: 1.0},
    # 1H Over 0.5
    "HT05": {0: 1.0, 1: 1.0, 2: 2.719, 3: 1.744, 4: 1.37, 5: 1.173, 6: 1.054, 7: 0.961, 8: 0.888, 9: 0.89},
    # Over 1.5
    "O15": {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.174, 4: 1.159, 5: 1.062, 6: 1.047, 7: 0.974, 8: 0.936, 9: 0.928},
    # Under 1.5
    "U15": {0: 1.871, 1: 1.349, 2: 1.079, 3: 0.909, 4: 0.922, 5: 0.864, 6: 0.901, 7: 1.0, 8: 1.0, 9: 1.0},
    # Over 3.5
    "O35": {0: 1.789, 1: 1.374, 2: 1.131, 3: 0.955, 4: 0.922, 5: 0.834, 6: 0.867, 7: 0.693, 8: 1.0, 9: 1.0},
    # Under 3.5
    "U35": {0: 1.0, 1: 1.0, 2: 1.821, 3: 1.233, 4: 1.196, 5: 1.062, 6: 1.024, 7: 0.957, 8: 0.93, 9: 0.94},
    # HT Casa
    "HT_H": {0: 1.471, 1: 1.243, 2: 1.134, 3: 1.009, 4: 0.993, 5: 0.997, 6: 1.088, 7: 1.0, 8: 1.0, 9: 1.0},
    # HT Pareggio
    "HT_D": {0: 1.0, 1: 1.0, 2: 0.706, 3: 0.914, 4: 0.924, 5: 0.903, 6: 0.883, 7: 1.0, 8: 1.0, 9: 1.0},
    # HT Trasferta
    "HT_A": {0: 1.08, 1: 1.188, 2: 1.07, 3: 1.029, 4: 0.962, 5: 1.192, 6: 1.0, 7: 1.0, 8: 1.0, 9: 1.0},
    # 1H Under 0.5
    "HT_U05": {0: 2.265, 1: 1.595, 2: 1.116, 3: 0.899, 4: 0.782, 5: 0.684, 6: 0.6, 7: 0.351, 8: 1.0, 9: 1.0},
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
                    _cal_raw = json.load(f)
                # Validate expected top-level keys
                _required_keys = {"leagues_covered", "divergence_stats"}
                _missing = _required_keys - set(_cal_raw.keys())
                if _missing:
                    logger.warning(
                        f"⚠️ dynamic_cal.json struttura incompleta — chiavi mancanti: {_missing}. "
                        f"Usa fallback tabella statica. Rigenera con lo script di calibrazione."
                    )
                    self._dynamic_cal = None
                else:
                    self._dynamic_cal = _cal_raw
                    n_leagues = self._dynamic_cal.get("leagues_covered", 0)
                    logger.info(f"📊 Dynamic calibration caricata ({n_leagues} leghe)")
            except json.JSONDecodeError as e:
                logger.warning(
                    f"⚠️ dynamic_cal.json CORROTTO (JSONDecodeError: {e}) — "
                    f"fallback su tabella statica. Elimina il file e rilancialo per rigenerarlo."
                )
                self._dynamic_cal = None
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
                    state.setdefault("ml_bankroll", self.config["bankroll"])
                    state.setdefault("ml_total_profit", 0.0)
                    state.setdefault("ml_total_staked", 0.0)
                    state.setdefault("ml_events_played", 0)
                    state.setdefault("ml_events_won", 0)
                    state.setdefault("ml_events_lost", 0)
                    state.setdefault("ml_slots", {})
                    state.setdefault("rejected_today", [])
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
            # ml_bankroll parte dalla stessa bankroll Poisson per simmetria.
            # Entrambe i track gestiscono capitale equivalente e scalano insieme.
            "ml_bankroll": self.config["bankroll"],
            "ml_total_profit": 0.0,
            "ml_total_staked": 0.0,
            "ml_events_played": 0,
            "ml_events_won": 0,
            "ml_events_lost": 0,
            "ml_slots": {},
            "rejected_today": [],
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

            # Soglie per-mercato da MARKET_MAP; fallback su config globale
            market_min_edge = market_info.get("min_edge", self.config["min_edge_pct"]) / 100.0
            market_min_prob  = market_info.get("min_prob", min_prob)
            market_min_odds  = market_info.get("min_odds", 1.01)

            # === CALIBRAZIONE: corregge la probabilità con dati storici ===
            cal_key = market_info.get("cal_key", market_key)
            prob_raw = prob
            prob, cal_source = self._apply_calibration(prob, cal_key, league_id=league_id)

            quota = odds_data.get(market_key)
            if quota is None or quota < max(1.01, market_min_odds):
                if quota is not None and quota > 1.01 and quota < market_min_odds:
                    if not hasattr(self, "_scan_rejected_candidates"):
                        self._scan_rejected_candidates = []
                    self._scan_rejected_candidates.append({
                        "market": market_key, "label": market_info["label"],
                        "track": "poisson",
                        "reason": f"quota {quota:.2f} < min_odds {market_min_odds:.2f}",
                        "prob": round(prob, 4), "edge": 0.0, "odds": quota,
                    })
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

            if edge < market_min_edge or prob < market_min_prob:
                # Traccia il motivo specifico del rifiuto per analytics
                if not hasattr(self, "_scan_rejected_candidates"):
                    self._scan_rejected_candidates = []
                _rej_reason = []
                if edge < market_min_edge:
                    _rej_reason.append(f"edge {edge*100:+.1f}% < min {market_min_edge*100:.0f}%")
                if prob < market_min_prob:
                    _rej_reason.append(f"prob {prob*100:.0f}% < min {market_min_prob*100:.0f}%")
                self._scan_rejected_candidates.append({
                    "market": market_key,
                    "label": market_info["label"],
                    "track": "poisson",
                    "reason": " & ".join(_rej_reason),
                    "prob": round(prob, 4),
                    "edge": round(edge, 4),
                    "odds": quota,
                })
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
        best["other_candidates"] = candidates[1:]
        return best

    # ======================================================================
    #  EDGE SCANNER ML — Usa SOLO probabilità AI (no Poisson, no calibrazione)
    # ======================================================================
    def scan_best_market_ml(self, ai_data, odds_data, calibration_metrics=None, excluded_markets=None):
        """Edge scanner basato SOLO su probabilità ML.
        Non usa calibrazione Poisson né filtro concordanza.
        Se calibration_metrics è fornito, scarta mercati con BSS < 0.
        excluded_markets: set di market_key già scommessi su questo fixture (skip per evitare duplicati)."""
        if not ai_data:
            return {"market": None, "reason": "Nessun dato AI disponibile"}

        comm = self.config["commission_pct"] / 100.0
        candidates = []

        for market_key, market_info in ML_MARKET_MAP.items():
            # Salta mercati già scommessi su questo fixture (dedup composita per fixture+market)
            if excluded_markets and market_key in excluded_markets:
                continue
            # Estrai probabilità dal dict AI
            prob = self._extract_nested(ai_data, market_info["ai_path"])
            if prob is None:
                continue
            if prob > 1:
                prob = prob / 100.0
            if prob < 0.01 or prob > 0.99:
                continue

            market_min_edge    = market_info.get("min_edge", 5.0) / 100.0
            min_prob_margin    = market_info.get("min_prob_margin", 0.0)
            market_min_odds    = market_info.get("min_odds", 1.01)
            odds_key = market_info.get("odds_key", market_key)
            quota = odds_data.get(odds_key)
            if quota is None or quota < max(1.01, market_min_odds):
                if quota is not None and 1.01 < quota < market_min_odds:
                    if not hasattr(self, "_scan_rejected_candidates"):
                        self._scan_rejected_candidates = []
                    self._scan_rejected_candidates.append({
                        "market": market_key, "label": market_info["label"],
                        "track": "ml",
                        "reason": f"quota {quota:.2f} < min_odds {market_min_odds:.2f}",
                        "prob": round(prob, 4), "edge": 0.0, "odds": quota,
                    })
                continue

            quota_net = (quota - 1.0) * (1.0 - comm) + 1.0
            edge = (prob * quota_net) - 1.0

            # Dynamic min_prob: model must exceed market-implied by min_prob_margin.
            # This adapts automatically to market price (no hardcoded absolute floor).
            implied = (1.0 / quota) * OVERROUND_CORRECTION
            dynamic_min_prob = implied + min_prob_margin
            if prob < dynamic_min_prob:
                if not hasattr(self, "_scan_rejected_candidates"):
                    self._scan_rejected_candidates = []
                self._scan_rejected_candidates.append({
                    "market": market_key, "label": market_info["label"],
                    "track": "ml",
                    "reason": f"prob {prob*100:.1f}% < implied+margin {dynamic_min_prob*100:.1f}% (odds {quota:.2f})",
                    "prob": round(prob, 4), "edge": round(edge, 4), "odds": quota,
                })
                continue

            if edge < market_min_edge:
                if not hasattr(self, "_scan_rejected_candidates"):
                    self._scan_rejected_candidates = []
                self._scan_rejected_candidates.append({
                    "market": market_key,
                    "label": market_info["label"],
                    "track": "ml",
                    "reason": f"edge {edge*100:+.1f}% < min {market_min_edge*100:.0f}%",
                    "prob": round(prob, 4),
                    "edge": round(edge, 4),
                    "odds": quota,
                })
                continue

            # BSS gate: graduated Kelly reduction instead of binary block.
            # BSS already normalised by n_classes so 0.12 = same quality
            # regardless of 2-way or 3-way market.
            #   BSS >= 0.12 → full stake (no reduction)
            #   BSS  0.05–0.12 → stake scaled linearly (0% at 0.12, -58% at 0.05)
            #   BSS < 0.05  → hard block (near-random model)
            BSS_FULL  = 0.12   # above this: no reduction
            BSS_FLOOR = 0.05   # below this: block entirely
            bss_multiplier = 1.0
            if calibration_metrics:
                ai_target = market_info.get("ai_target", "")
                brier = calibration_metrics.get(ai_target, {}).get("brier") if ai_target else None
                n_cls = market_info.get("n_classes", 2)
                if brier is not None:
                    brier_random = (n_cls - 1) / n_cls if n_cls > 1 else 0.5
                    bss = 1.0 - brier / brier_random if brier_random > 0 else None
                    if bss is not None:
                        if bss < BSS_FLOOR:
                            if not hasattr(self, "_scan_rejected_candidates"):
                                self._scan_rejected_candidates = []
                            self._scan_rejected_candidates.append({
                                "market": market_key, "label": market_info["label"],
                                "track": "ml",
                                "reason": f"BSS={bss:.3f} < floor {BSS_FLOOR} — modello near-random",
                                "prob": round(prob, 4), "edge": round(edge, 4), "odds": quota,
                            })
                            continue  # hard block
                        elif bss < BSS_FULL:
                            # Linear scale: 0.0 at BSS_FLOOR → 1.0 at BSS_FULL
                            bss_multiplier = (bss - BSS_FLOOR) / (BSS_FULL - BSS_FLOOR)
                            logger.debug(
                                f"    ⚠️ BSS graduato {market_key}: BSS={bss:.3f} → "
                                f"stake ×{bss_multiplier:.2f}"
                            )

            # Intelligent high-odds filter: score = edge × √prob.
            # High-odds selections (low prob) need proportionally stronger edge
            # to achieve the same score as low-odds selections.  No arbitrary
            # odds cap is imposed — a genuine +10% edge on odds 4.0 still passes.
            score = edge * math.sqrt(prob)

            # Score threshold cresce con la quota: quote alte richiedono
            # un'occasione eccezionale, non basta un edge marginale.
            # Default = ultimo tier (più stringente) per quote fuori scala (>999).
            min_score_for_odds = ML_SCORE_TIERS[-1][1] if ML_SCORE_TIERS else MIN_ML_SCORE_THRESHOLD
            for _max_odds, _min_score in ML_SCORE_TIERS:
                if quota < _max_odds:
                    min_score_for_odds = _min_score
                    break

            if score < min_score_for_odds:
                if not hasattr(self, "_scan_rejected_candidates"):
                    self._scan_rejected_candidates = []
                self._scan_rejected_candidates.append({
                    "market": market_key,
                    "label": market_info["label"],
                    "track": "ml",
                    "reason": (
                        f"score {score:.4f} < min {min_score_for_odds} "
                        f"(odds {quota:.2f} → tier {min_score_for_odds})"
                    ),
                    "prob": round(prob, 4),
                    "edge": round(edge, 4),
                    "odds": quota,
                })
                continue

            candidates.append({
                "market": market_key,
                "label": market_info["label"],
                "prob": round(prob, 4),
                "odds": quota,
                "edge": round(edge, 4),
                "score": round(score, 4),
                "bss_multiplier": round(bss_multiplier, 3),
            })

        if not candidates:
            return {"market": None, "reason": "Nessun Value Bet ML"}

        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]
        best["reason"] = f"{best['label']} (Edge ML {best['edge']*100:+.1f}%, Prob {best['prob']*100:.0f}%)"
        best["all_candidates"] = len(candidates)
        best["other_candidates"] = candidates[1:]
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
        bankroll = self.state.get("ml_bankroll", self.config["bankroll"]) if use_ml_bankroll else self.state["bankroll"]
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
                # Usiamo divergenza diretta (NON abs): blocchiamo solo divergenze POSITIVE
                # estreme (modello molto più ottimista del mercato = potenziale hallucination).
                # Divergenze negative (modello più pessimista) sono già bloccate dal check
                # edge > min_edge — non ha senso bloccarle due volte.
                z_score = divergence / self._divergence_std

                meta["divergence"] = round(divergence, 4)
                meta["z_score"] = round(z_score, 2)

                # Soglie z-score: ML più permissivo perché ha varianza legittima più alta.
                # Poisson z=2.0 → divergenza > 60% bloccata (con σ=0.30 default)
                # ML     z=2.5 → divergenza > 75% bloccata
                if track == "ml":
                    z_thresh = 2.5
                else:
                    z_thresh = 2.0

                if z_score > z_thresh:
                    meta["is_hallucination"] = True
                    meta["safety_vault"] = True
                    logger.info(
                        f"    🚫 HALLUCINATION BLOCKED [{track}]: z={z_score:.2f} > {z_thresh} "
                        f"(div={divergence:+.2f}) → scommessa ANNULLATA (stake=0)"
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
        # ML dedup — chiave composita (fixture_id, market) per permettere più mercati
        # diversi sullo stesso fixture (es. H + O25 sulla stessa partita)
        existing_ml = set()
        for s in self.state.get("ml_slots", {}).values():
            fid = s.get("fixture_id")
            mkt = s.get("market")
            if fid is not None and mkt is not None:
                existing_ml.add((int(fid), mkt))

        enriched = []
        pois_counter = len(self.state["slots"])
        ml_counter = len(self.state.get("ml_slots", {}))
        pois_accepted = 0
        ml_accepted = 0
        # P9: collect concordant (pois_slot_id, ml_slot_id, market) triples
        # inside the loop; boost stakes after the Correlated Kelly reduction.
        _concordances: list = []

        for signal in signals_data:
            # P9: reset per-iteration scan refs so that the concordance check
            # at the end of the loop never reads a stale scan from a prior
            # iteration (which would happen if pois_skip=True and scan was
            # assigned in a previous iteration).
            scan = {}
            ml_scan = {}
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
                # Reset per-signal candidate tracker before scanning
                self._scan_rejected_candidates = []
                scan = self.scan_best_market(analysis_markets, odds, inputs, ai_data=ai_markets, league_id=sig_league_id)
                # Log per-candidate rejections into rejected_today for analytics
                for _crej in getattr(self, "_scan_rejected_candidates", []):
                    self.state["rejected_today"].append({
                        "fixture_id": sig_fid,
                        "event": signal.get("name", ""),
                        "track": _crej.get("track", "poisson"),
                        "market": _crej.get("market", ""),
                        "market_label": _crej.get("label", ""),
                        "reason": _crej.get("reason", ""),
                        "prob": _crej.get("prob"),
                        "edge": _crej.get("edge"),
                        "odds": _crej.get("odds"),
                        "date": self.state["last_run_date"],
                    })
                self._scan_rejected_candidates = []
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
                            "is_best": True,
                            "closing_odds": None,   # Fix 18: populated by update_closing_odds()
                            "clv": None,            # closing_line_value = closing_implied - entry_implied (positive = skill)
                        }
                        # Segnali aggiuntivi validi — stessa logica del BEST, stake reale
                        for _ci, _cand in enumerate(scan.get("other_candidates", []), start=2):
                            _add_sid = f"{slot_id}{chr(96 + _ci)}"  # S1b, S1c, ...
                            _add_stake = self.calculate_kelly_stake(_cand["prob"], _cand["odds"])
                            _add_stake, _add_safety = self._apply_safety_filters(
                                _add_stake, _cand["prob"], _cand["odds"], league_id=sig_league_id
                            )
                            if _add_stake > 0:
                                self.state["slots"][_add_sid] = {
                                    "status": "PENDING",
                                    "event_name": signal.get("name", "?"),
                                    "event_id": signal.get("event_id", "?"),
                                    "fixture_id": signal.get("fixture_id"),
                                    "date": signal.get("date", ""),
                                    "market": _cand["market"],
                                    "market_label": _cand["label"],
                                    "prob": _cand["prob"],
                                    "odds": _cand["odds"],
                                    "edge": _cand["edge"],
                                    "score": _cand["score"],
                                    "stake": _add_stake,
                                    "pnl": 0.0,
                                    "result": "PENDING",
                                    "closing_odds": None,
                                    "clv": None,
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
                    # Fix 17: log rejection reason for analysis
                    self.state["rejected_today"].append({
                        "fixture_id": sig_fid,
                        "event": signal.get("name", ""),
                        "track": "poisson",
                        "reason": scan.get("reason", "no_signal"),
                        "date": self.state["last_run_date"],
                    })

            # ===================== ML TRACK =====================
            # Dedup composita: calcola i mercati già scommessi per questo fixture
            _ml_excluded = (
                {mkt for (fid, mkt) in existing_ml if fid == int(sig_fid)}
                if sig_fid is not None else set()
            )
            self._scan_rejected_candidates = []
            ml_scan = self.scan_best_market_ml(
                ai_markets, odds,
                calibration_metrics=signal.get("calibration_metrics"),
                excluded_markets=_ml_excluded,
            )
            # Controllo post-scan: skip se nessun mercato trovato o già presente
            _ml_market_found = ml_scan.get("market")
            ml_skip = (
                sig_fid is not None and _ml_market_found is not None and
                (int(sig_fid), _ml_market_found) in existing_ml
            )
            if ml_skip or _ml_market_found is None:
                signal["ml_slot_id"] = "⊘ SKIP"
                signal["ml_stake"] = ""
                signal["ml_selected_market"] = ""
                signal["ml_edge_pct"] = ""
                signal["ml_score"] = ""
            else:
                # Log per-candidate ML rejections
                for _crej in getattr(self, "_scan_rejected_candidates", []):
                    self.state["rejected_today"].append({
                        "fixture_id": sig_fid,
                        "event": signal.get("name", ""),
                        "track": "ml",
                        "market": _crej.get("market", ""),
                        "market_label": _crej.get("label", ""),
                        "reason": _crej.get("reason", ""),
                        "prob": _crej.get("prob"),
                        "edge": _crej.get("edge"),
                        "odds": _crej.get("odds"),
                        "date": self.state["last_run_date"],
                    })
                self._scan_rejected_candidates = []
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
                        brier_score=None,        # BSS shrinkage already applied via bss_multiplier below
                        n_classes=ml_n_classes,
                    )

                    # Apply BSS graduated multiplier from scan (already computed)
                    _bss_mult = ml_scan.get("bss_multiplier", 1.0)
                    if _bss_mult < 1.0:
                        ml_stake = round(ml_stake * _bss_mult, 2)

                    # --- Reliability Multiplier (propagated from predict_fixture) ---
                    # alpha = reliability_score (0.0–1.0): penalizza stake quando i dati
                    # sono scarsi (poche partite storiche / copertura feature bassa).
                    # Default 1.0 se il campo non è presente (segnali legacy).
                    _rel_mult = float(signal.get("ml_reliability_multiplier", 1.0))
                    _rel_mult = max(0.0, min(1.0, _rel_mult))  # clamp [0, 1]
                    if _rel_mult < 1.0:
                        old_ml_stake = ml_stake
                        ml_stake = round(ml_stake * _rel_mult, 2)
                        logger.debug(
                            f"    🔬 Reliability [{_rel_mult:.2f}]: ml_stake "
                            f"{old_ml_stake:.2f} → {ml_stake:.2f}"
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
                            "reliability_multiplier": round(_rel_mult, 3),
                            "pnl": 0.0,
                            "result": "PENDING",
                            "is_best": True,
                            "closing_odds": None,   # Fix 18: CLV tracking
                            "clv": None,
                        }
                        # Segnali ML aggiuntivi validi — stake reale con BSS + reliability
                        for _ci, _cand in enumerate(ml_scan.get("other_candidates", []), start=2):
                            _add_ml_sid = f"{ml_slot_id}{chr(96 + _ci)}"  # M1b, M1c, ...
                            _add_market_info = ML_MARKET_MAP.get(_cand["market"], {})
                            _add_n_cls = _add_market_info.get("n_classes", 2)
                            _add_ml_stake = self.calculate_kelly_stake(
                                _cand["prob"], _cand["odds"],
                                use_ml_bankroll=True, brier_score=None, n_classes=_add_n_cls,
                            )
                            _add_bss = _cand.get("bss_multiplier", 1.0)
                            if _add_bss < 1.0:
                                _add_ml_stake = round(_add_ml_stake * _add_bss, 2)
                            if _rel_mult < 1.0:
                                _add_ml_stake = round(_add_ml_stake * _rel_mult, 2)
                            _add_ml_stake, _add_ml_safety = self._apply_safety_filters(
                                _add_ml_stake, _cand["prob"], _cand["odds"],
                                league_id=sig_league_id, track="ml",
                            )
                            if _add_ml_stake > 0:
                                self.state["ml_slots"][_add_ml_sid] = {
                                    "status": "PENDING",
                                    "event_name": signal.get("name", "?"),
                                    "event_id": signal.get("event_id", "?"),
                                    "fixture_id": signal.get("fixture_id"),
                                    "date": signal.get("date", ""),
                                    "market": _cand["market"],
                                    "market_label": _cand["label"],
                                    "prob": _cand["prob"],
                                    "odds": _cand["odds"],
                                    "edge": _cand["edge"],
                                    "score": _cand["score"],
                                    "stake": _add_ml_stake,
                                    "pnl": 0.0,
                                    "result": "PENDING",
                                    "closing_odds": None,
                                    "clv": None,
                                }
                                if sig_fid is not None:
                                    existing_ml.add((int(sig_fid), _cand["market"]))
                        if sig_fid is not None and ml_scan.get("market"):
                            existing_ml.add((int(sig_fid), ml_scan["market"]))
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
                    # Fix 17: log ML rejection reason
                    self.state["rejected_today"].append({
                        "fixture_id": sig_fid,
                        "event": signal.get("name", ""),
                        "track": "ml",
                        "reason": ml_scan.get("reason", "no_signal"),
                        "date": self.state["last_run_date"],
                    })

            # ── P9: Concordance detection ────────────────────────────────────
            # Collect (pois_slot_id, ml_slot_id) pairs where both tracks
            # accepted the same market on the same fixture.  The actual stake
            # boost is applied AFTER the Correlated Kelly loop (below) so that
            # the ×1.5 multiplier is not offset by the subsequent -30% Kelly
            # reduction.  `_pois_accepted` is True only when a real slot was
            # assigned (stake > 0), which implies `scan` was populated and
            # `scan.get("market")` is safe to call.
            _pois_slot_this = signal.get("slot_id")
            _ml_slot_this = signal.get("ml_slot_id")
            _pois_accepted_conc = _pois_slot_this not in (None, "⊘ SKIP", "")
            _ml_accepted_conc = _ml_slot_this not in (None, "⊘ SKIP", "")
            if (
                _pois_accepted_conc
                and _ml_accepted_conc
                and scan.get("market") is not None
                and ml_scan.get("market") is not None
                and scan["market"] == ml_scan["market"]
            ):
                _concordances.append((_pois_slot_this, _ml_slot_this, scan["market"]))

            enriched.append(signal)

        # ── Correlated Kelly adjustment: reduce stake when multiple bets
        #    on the same fixture (e.g. 1x2 + BTTS on same match).
        #    Applied to both Poisson and ML tracks.
        #    Guard _corr_adj: idempotente su multi-run (lo stake non viene
        #    ridotto più di una volta per lo stesso slot).
        for track_key in ("slots", "ml_slots"):
            track_label = "Poisson" if track_key == "slots" else "ML"
            fixture_counts: dict = {}
            for sid, slot in self.state.get(track_key, {}).items():
                fid = slot.get("fixture_id")
                if fid is not None and slot.get("result") == "PENDING":
                    fixture_counts[int(fid)] = fixture_counts.get(int(fid), 0) + 1
            for sid, slot in self.state.get(track_key, {}).items():
                fid = slot.get("fixture_id")
                # Applica SOLO a slot PENDING non ancora aggiustati (idempotenza)
                if (fid is not None
                        and slot.get("result") == "PENDING"
                        and not slot.get("_corr_adj", False)
                        and fixture_counts.get(int(fid), 1) > 1):
                    old_stake = slot["stake"]
                    slot["stake"] = max(round(old_stake * 0.70, 2), 1.0)  # floor €1 Betfair minimum
                    slot["_corr_adj"] = True  # marca: riduzione già applicata
                    logger.info(
                        f"    📉 Correlated Kelly [{track_label}]: {sid} (fixture {fid}) "
                        f"stake {old_stake:.2f} → {slot['stake']:.2f} (-30%)"
                    )

        # ── P9: Concordance boost ────────────────────────────────────────────
        # Applied AFTER Correlated Kelly so the ×1.5 is not offset by the
        # subsequent -30% reduction.  At this point all stakes have already
        # been reduced for multi-bet fixtures; the concordance boost reflects
        # genuine signal strength and should survive that reduction.
        # The boost is capped at max_stake_pct to avoid exceeding the
        # bankroll-management ceiling.
        if _concordances:
            _CONC_MULT = 1.5
            _max_pct = self.config.get("max_stake_pct", 10.0) / 100.0
            for _pois_sid, _ml_sid, _market in _concordances:
                _boosted = False
                if _pois_sid in self.state["slots"]:
                    _slot_p = self.state["slots"][_pois_sid]
                    # Idempotency guard: skip if boost already applied (prevents
                    # ×1.5^N multiplication on repeated process_signals calls).
                    if not _slot_p.get("concordance_boost"):
                        _max_p = round(_max_pct * self.state["bankroll"], 2)
                        _old_p = _slot_p["stake"]
                        _slot_p["stake"] = min(round(_old_p * _CONC_MULT, 2), _max_p)
                        _slot_p["concordance_boost"] = True
                        _boosted = True
                if _ml_sid in self.state.get("ml_slots", {}):
                    _slot_m = self.state["ml_slots"][_ml_sid]
                    if not _slot_m.get("concordance_boost"):
                        _max_m = round(
                            _max_pct * self.state.get("ml_bankroll", self.state["bankroll"]), 2
                        )
                        _old_m = _slot_m["stake"]
                        _slot_m["stake"] = min(round(_old_m * _CONC_MULT, 2), _max_m)
                        _slot_m["concordance_boost"] = True
                        _boosted = True
                if _boosted:
                    logger.info(
                        f"    🎯 Concordanza [{_pois_sid}/{_ml_sid}]: mercato '{_market}' "
                        f"su Poisson+ML → stake ×{_CONC_MULT:.1f}"
                    )

        logger.info(f"✅ Poisson accettati: {pois_accepted} | ML accettati: {ml_accepted} | Totale segnali: {len(signals_data)}")
        # P6: automatic weekly BSS health check (rate-limited to once per 7 days).
        self._auto_bss_check()
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

            # FIX: won=None significa dati HT mancanti → lascia PENDING anziché PERSA
            if won is None:
                logger.warning(f"  {sid}: dati HT mancanti per {slot.get('market')} — slot rimane PENDING")
                continue

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
        elif market == "O15":
            return (gh + ga) >= 2
        elif market == "U15":
            return (gh + ga) < 2
        elif market == "O35":
            return (gh + ga) >= 4
        elif market == "U35":
            return (gh + ga) < 4
        elif market == "BTTS":
            return gh >= 1 and ga >= 1
        elif market == "BTTS_NO":
            return gh == 0 or ga == 0
        elif market == "HT05":
            if hth is None or hta is None:
                return None  # FIX: dati HT mancanti → PENDING, non PERSA
            return (int(hth) + int(hta)) >= 1
        elif market == "HT_U05":
            if hth is None or hta is None:
                return None  # FIX: dati HT mancanti → PENDING, non PERSA
            return (int(hth) + int(hta)) == 0
        elif market == "HT_H":
            if hth is None or hta is None:
                return None  # FIX: dati HT mancanti → PENDING, non PERSA
            return int(hth) > int(hta)
        elif market == "HT_D":
            if hth is None or hta is None:
                return None  # FIX: dati HT mancanti → PENDING, non PERSA
            return int(hth) == int(hta)
        elif market == "HT_A":
            if hth is None or hta is None:
                return None  # FIX: dati HT mancanti → PENDING, non PERSA
            return int(hth) < int(hta)
        logger.warning(f"_evaluate_bet_result: mercato '{market}' non gestito — bet marcata come PERSA")
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
            # FIX: won=None → dati HT mancanti → PENDING
            if won is None:
                logger.warning(f"  ML {sid}: dati HT mancanti per {slot.get('market')} — slot rimane PENDING")
                continue
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
            # Normalizza in-memoria: inferisce is_best e aggiunge "(BEST)" agli slot
            # che non hanno ancora il flag (history salvata con versione precedente del codice).
            # Criterio: slot senza suffisso lettera (S1, M3) = BEST; con lettera (S1b, M3c) = aggiuntivi.
            for _day in history:
                for _s in _day.get("slots", []) + _day.get("ml_slots", []):
                    if not _s.get("is_best"):
                        _sid_base = _s.get("slot_id", "").split(" ")[0]
                        if not re.search(r'[a-z]$', _sid_base):
                            _s["is_best"] = True
                            if "(BEST)" not in _s.get("slot_id", ""):
                                _s["slot_id"] = f"{_s['slot_id']} (BEST)"

            try:
                ws = self.sh.worksheet("Report Ven Dom")
                _sheets_retry(ws.clear)
                # Unmerge tutte le celle unite per un foglio pulito
                old_rows = ws.row_count
                try:
                    _sheets_retry(self.sh.batch_update, {"requests": [
                        {"unmergeCells": {"range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": old_rows, "startColumnIndex": 0, "endColumnIndex": 14}}}
                    ]})
                except Exception:
                    pass  # Se non ci sono merge, ignora
            except gspread.exceptions.WorksheetNotFound:
                ws = self.sh.add_worksheet(title="Report Ven Dom", rows=3000, cols=14)

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
            ml_st = calc_stats(all_ml_slots, self.state.get("ml_bankroll", self.config["bankroll"]))

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
                        row[6] = result_str if is_pend else f"{result_str} €{s_pnl:+.2f}"
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
                        row[13] = result_str if is_pend else f"{result_str} €{s_pnl:+.2f}"

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
                p_by_f = {int(s.get("fixture_id", 0)): s for s in day.get("slots", [])
                          if s.get("fixture_id") and s.get("is_best")}
                m_by_f = {int(s.get("fixture_id", 0)): s for s in day.get("ml_slots", [])
                          if s.get("fixture_id") and s.get("is_best")}
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
            # Margine dinamico: il foglio deve coprire almeno tutti i dati + buffer
            max_rows = max(end_row + 200, ws.row_count)
            
            # Ridimensiona il foglio se necessario
            if ws.row_count < end_row + 10:
                _sheets_retry(ws.resize, rows=max_rows, cols=COLS)
                time_module.sleep(1)
            
            # --- Forza pulizia completa (dati e unioni) da end_row in poi ---
            if end_row < max_rows:
                format_requests.append({
                    "unmergeCells": {
                        "range": {"sheetId": sheet_id, "startRowIndex": end_row, "endRowIndex": max_rows, "startColumnIndex": 0, "endColumnIndex": COLS}
                    }
                })
                # Resetta sfondo e testo a default per le celle non usate
                format_requests.append({
                    "repeatCell": {
                        "range": {"sheetId": sheet_id, "startRowIndex": end_row, "endRowIndex": max_rows, "startColumnIndex": 0, "endColumnIndex": COLS},
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
                # Usa updateCells con stringValue/numberValue per compatibilità locale
                rows_api = []
                for row in all_data:
                    cell_vals = []
                    for val in row:
                        if isinstance(val, (int, float)):
                            cell_vals.append({"userEnteredValue": {"numberValue": float(val)}})
                        else:
                            cell_vals.append({"userEnteredValue": {"stringValue": str(val)}})
                    rows_api.append({"values": cell_vals})
                update_cells_req = {
                    "updateCells": {
                        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": end_row, "startColumnIndex": 0, "endColumnIndex": COLS},
                        "rows": rows_api,
                        "fields": "userEnteredValue"
                    }
                }
                format_requests.insert(0, update_cells_req)
                time_module.sleep(1)
                
            # Azzera i valori dalle righe successive
            if end_row < max_rows:
                 _sheets_retry(ws.batch_clear, [f"A{end_row+1}:N{max_rows}"])
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
            except json.JSONDecodeError as e:
                logger.error(f"mm_history.json corrotto o non valido: {e}")
            except Exception as e:
                logger.error(f"Errore lettura mm_history.json: {e}")
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
            # is_best: usa il flag se presente (slot nuovi), altrimenti inferisce dall'ID.
            # Slot senza suffisso lettera (S1, S2) = BEST; con lettera (S1b, S1c) = aggiuntivi.
            _is_best = s.get("is_best", not bool(re.search(r'[a-z]$', sid)))
            _display_sid = f"{sid} (BEST)" if _is_best else sid
            today_slots.append({
                "slot_id": _display_sid,
                "is_best": _is_best,
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
            # Stessa logica: flag esplicito oppure inferito dall'ID (M1=BEST, M1b=aggiuntivo)
            _is_best = s.get("is_best", not bool(re.search(r'[a-z]$', sid)))
            _display_sid = f"{sid} (BEST)" if _is_best else sid
            today_ml_slots.append({
                "slot_id": _display_sid,
                "is_best": _is_best,
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

        today_rejected = self.state.get("rejected_today", [])

        # Aggiorna o aggiungi il giorno
        found = False
        for day in history:
            if day["date"] == today:
                day["slots"] = today_slots
                day["ml_slots"] = today_ml_slots
                day["rejected"] = today_rejected
                found = True
                break
        if not found:
            history.append({"date": today, "slots": today_slots, "ml_slots": today_ml_slots, "rejected": today_rejected})

        self._save_history(history)
        logger.info(f"Storico aggiornato: {today} — {len(today_slots)} Poisson + {len(today_ml_slots)} ML slots, {len(today_rejected)} rifiutati.")

        # Fix 16: push to Supabase signal_history (best-effort, non-blocking)
        try:
            self._push_slots_to_supabase(today, today_slots, today_ml_slots)
        except Exception as e:
            logger.warning(f"Supabase signal_history sync failed (local JSON OK): {e}")

    @staticmethod
    def _deduplicate_slots(slots):
        """Deduplica una lista di slot per (fixture_id, market).
        Chiave composita per consentire più mercati sulla stessa partita
        (es. H + O25 sulla stessa fixture).
        Per ogni chiave tiene l'entry risolta (VINTO/PERSO) se esiste,
        altrimenti la prima entry PENDING."""
        by_key = {}
        for s in slots:
            fid = s.get("fixture_id")
            mkt = s.get("market", "")
            if fid is None:
                # Slot senza fixture_id: usa slot_id come chiave univoca
                by_key[s.get("slot_id", id(s))] = s
                continue
            key = (int(fid), mkt)
            existing = by_key.get(key)
            if existing is None:
                by_key[key] = s
            else:
                # Preferisci entry risolta su PENDING
                if s.get("result") != "PENDING" and existing.get("result") == "PENDING":
                    by_key[key] = s
        result = list(by_key.values())
        if len(result) < len(slots):
            logger.info(f"🔄 Deduplicati {len(slots) - len(result)} slot duplicati (per fixture+market).")
        return result

    def retroactive_fix_misclassified_results(self):
        """Corregge retroattivamente gli slot PERSO con mercati estesi che
        venivano sempre valutati False (O15, U15, O35, U35, HT_H, HT_D, HT_A).
        Chiamato automaticamente da resolve_history_results.
        Operazione idempotente: non modifica slot già taggati come corretti."""
        AFFECTED = {"O15", "U15", "O35", "U35", "HT_H", "HT_D", "HT_A"}
        history = self._load_history()
        if not history:
            return

        comm = self.config["commission_pct"] / 100.0

        # Raccoglie fixture_id per mercati HT (necessitano halftime dal DB)
        ht_markets = {"HT_H", "HT_D", "HT_A"}
        ht_fixture_ids = set()
        for day in history:
            for slot in day.get("slots", []) + day.get("ml_slots", []):
                if slot.get("market") in ht_markets and "PERSO" in str(slot.get("result", "")):
                    fid = slot.get("fixture_id")
                    if fid and slot.get("goals_home", "—") != "—":
                        ht_fixture_ids.add(int(fid))

        # Fetch halftime data dal DB per mercati HT
        ht_map = {}
        if ht_fixture_ids:
            try:
                sb = get_supabase_client()
                for i in range(0, len(ht_fixture_ids), 200):
                    chunk = list(ht_fixture_ids)[i:i+200]
                    resp = sb.table("matches").select(
                        "fixture_id, halftime_home, halftime_away"
                    ).in_("fixture_id", chunk).execute()
                    for r in (getattr(resp, "data", None) or []):
                        fid = r.get("fixture_id")
                        if fid is not None:
                            ht_map[int(fid)] = r
            except Exception as e:
                logger.warning(f"Retroactive fix: DB fetch halftime failed: {e}")

        corrected = 0
        for day in history:
            for slot in day.get("slots", []) + day.get("ml_slots", []):
                market = slot.get("market", "")
                if market not in AFFECTED:
                    continue
                if "PERSO" not in str(slot.get("result", "")):
                    continue
                # Already tagged as retroactively fixed — skip
                if slot.get("_retrofix"):
                    continue

                gh = slot.get("goals_home")
                ga = slot.get("goals_away")
                if gh is None or gh == "—" or ga is None or ga == "—":
                    continue  # no goal data stored, cannot re-evaluate

                gh = int(gh)
                ga = int(ga)

                # Build a pseudo-match dict for _evaluate_bet_result
                pseudo_match = {"goals_home": gh, "goals_away": ga,
                                "halftime_home": None, "halftime_away": None}
                if market in ht_markets:
                    fid = slot.get("fixture_id")
                    ht_row = ht_map.get(int(fid)) if fid else None
                    if ht_row:
                        pseudo_match["halftime_home"] = ht_row.get("halftime_home")
                        pseudo_match["halftime_away"] = ht_row.get("halftime_away")
                    else:
                        continue  # can't evaluate HT without halftime data

                won = self._evaluate_bet_result(slot, pseudo_match)
                if won:
                    stake = slot.get("stake", 0)
                    profit = stake * (slot.get("odds", 1) - 1) * (1.0 - comm)
                    old_pnl = slot.get("pnl", -stake)
                    slot["result"] = "VINTO ✅"
                    slot["pnl"] = round(profit, 2)
                    slot["_retrofix"] = True
                    corrected += 1
                    logger.info(
                        f"  [RETROFIX] {slot.get('slot_id','?')} {slot.get('event_name','?')} "
                        f"mkt={market} {gh}-{ga} → VINTO (P&L: {old_pnl:+.2f}→{profit:+.2f}€)"
                    )
                else:
                    # Correctly PERSO — tag it so we don't re-check next run
                    slot["_retrofix"] = True

        if corrected > 0:
            self._save_history(history)
            logger.info(f"✅ Retroactive fix completato: {corrected} slot corretti da PERSO→VINTO")
        else:
            logger.info("Retroactive fix: nessuna correzione necessaria")

    def resolve_history_results(self):
        """Risolve i risultati PENDING di TUTTI i giorni nello storico.
        Questo è il metodo chiave: quando lanci lo script sabato mattina,
        risolve automaticamente i risultati di venerdì."""
        # Run retroactive fix for previously misclassified extended ML markets
        self.retroactive_fix_misclassified_results()

        sb = get_supabase_client()
        history = self._load_history()

        if not history:
            logger.info("Nessuno storico da risolvere.")
            return

        # Commissione fissa 5% su vincite — non ricalcolare mai P&L storici.
        # Il P&L viene congelato al momento della risoluzione.

        # Raccoglie tutti i slot PENDING Poisson — key = (fixture_id, slot_id) per evitare
        # sovrascrittura quando ci sono più scommesse sullo stesso fixture (es. H + O25)
        pending_fixtures = {}
        for day in history:
            for slot in day.get("slots", []):
                if slot.get("result") == "PENDING" and slot.get("fixture_id"):
                    key = (int(slot["fixture_id"]), slot.get("slot_id", ""))
                    pending_fixtures[key] = (day, slot)

        if not pending_fixtures:
            logger.info("Nessun risultato PENDING Poisson nello storico — controllo ML...")
            # Non fare return: i slot ML potrebbero avere PENDING anche senza Poisson PENDING

        if pending_fixtures:
            logger.info(f"Risolvo {len(pending_fixtures)} risultati PENDING Poisson dallo storico...")

        # Fetch dal DB — estrae fixture_id univoci dal composite key
        unique_fids = list({fid for fid, _ in pending_fixtures.keys()})
        matches_map = {}
        for i in range(0, len(unique_fids), 200):
            chunk = unique_fids[i:i+200]
            resp = sb.table("matches").select(
                "fixture_id, status_short, goals_home, goals_away, halftime_home, halftime_away"
            ).in_("fixture_id", chunk).execute()
            for r in (getattr(resp, "data", None) or []):
                fid = r.get("fixture_id")
                if fid is not None:
                    matches_map[int(fid)] = r

        resolved = 0
        for (fid, _sid), (day, slot) in pending_fixtures.items():
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
            if won is None:
                logger.warning(f"  {slot.get('slot_id','?')}: dati HT mancanti — rimane PENDING")
                continue
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
        # Key = (fixture_id, slot_id) to avoid overwriting when multiple ML bets on same fixture
        ml_pending = {}
        for day in history:
            for slot in day.get("ml_slots", []):
                if slot.get("result") == "PENDING" and slot.get("fixture_id"):
                    fid = int(slot["fixture_id"])
                    key = (fid, slot.get("slot_id", ""))
                    ml_pending[key] = (day, slot)

        # Fetch any missing ML fixture IDs
        ml_missing = list(set(fid for (fid, _) in ml_pending if fid not in matches_map))
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
        for (fid, _sid), (day, slot) in ml_pending.items():
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
            if won is None:
                logger.warning(f"  ML {slot.get('slot_id','?')}: dati HT mancanti — rimane PENDING")
                continue
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
        if total_resolved > 0:
            self._save_history(history)
            logger.info(f"✅ Risolti {resolved} Poisson + {ml_resolved} ML risultati dallo storico.")
            # Fix 16: sync resolved results to Supabase
            try:
                self._update_resolved_in_supabase(history)
            except Exception as e:
                logger.warning(f"Supabase resolve sync failed (local JSON OK): {e}")

    # ======================================================================
    #  FIX 16: SUPABASE SIGNAL HISTORY SYNC
    # ======================================================================
    def _push_slots_to_supabase(self, today: str, slots: list, ml_slots: list):
        """Upsert today's slots into signal_history table on Supabase.
        Table DDL: see migrations/signal_history.sql
        Non-fatal: caller wraps in try/except."""
        from db_client import get_supabase_client
        sb = get_supabase_client()
        rows = []
        for s in slots:
            fid = s.get("fixture_id")
            if fid is None:
                continue
            _sid_clean = s.get("slot_id", "").replace(" ", "").replace("(", "").replace(")", "")
            rows.append({
                "signal_id":    f"P_{today}_{_sid_clean}",
                "fixture_id":   int(fid),
                "date":         today,
                "track":        "poisson",
                "market":       s.get("market", ""),
                "market_label": s.get("market_label", ""),
                "prob":         s.get("prob"),
                "odds":         s.get("odds"),
                "edge":         s.get("edge"),
                "score":        s.get("score"),
                "stake":        s.get("stake"),
                "result":       s.get("result", "PENDING"),
                "pnl":          s.get("pnl", 0),
                "commission":   5.0,
            })
        for s in ml_slots:
            fid = s.get("fixture_id")
            if fid is None:
                continue
            _sid_clean = s.get("slot_id", "").replace(" ", "").replace("(", "").replace(")", "")
            rows.append({
                "signal_id":    f"M_{today}_{_sid_clean}",
                "fixture_id":   int(fid),
                "date":         today,
                "track":        "ml",
                "market":       s.get("market", ""),
                "market_label": s.get("market_label", ""),
                "prob":         s.get("prob"),
                "odds":         s.get("odds"),
                "edge":         s.get("edge"),
                "score":        s.get("score"),
                "stake":        s.get("stake"),
                "result":       s.get("result", "PENDING"),
                "pnl":          s.get("pnl", 0),
                "commission":   5.0,
                "bss":          s.get("brier_score"),
            })
        if rows:
            sb.table("signal_history").upsert(rows, on_conflict="signal_id").execute()
            logger.info(f"Supabase signal_history: {len(rows)} upserted.")

    def _update_resolved_in_supabase(self, history: list):
        """Update resolved (VINTO/PERSO) records in signal_history."""
        from db_client import get_supabase_client
        sb = get_supabase_client()
        updates = []
        for day in history:
            d = day["date"]
            for s in day.get("slots", []):
                if s.get("result") != "PENDING" and s.get("fixture_id"):
                    _sid_c = s.get("slot_id", "").replace(" ", "").replace("(", "").replace(")", "")
                    updates.append({
                        "signal_id": f"P_{d}_{_sid_c}",
                        "result": s.get("result"),
                        "pnl":    s.get("pnl", 0),
                        "goals_home": s.get("goals_home"),
                        "goals_away": s.get("goals_away"),
                    })
            for s in day.get("ml_slots", []):
                if s.get("result") != "PENDING" and s.get("fixture_id"):
                    _sid_c = s.get("slot_id", "").replace(" ", "").replace("(", "").replace(")", "")
                    updates.append({
                        "signal_id": f"M_{d}_{_sid_c}",
                        "result": s.get("result"),
                        "pnl":    s.get("pnl", 0),
                        "goals_home": s.get("goals_home"),
                        "goals_away": s.get("goals_away"),
                    })
        if updates:
            sb.table("signal_history").upsert(updates, on_conflict="signal_id").execute()
            logger.info(f"Supabase signal_history: {len(updates)} results synced.")

    # ======================================================================
    #  FIX 18: CLV (CLOSING LINE VALUE) TRACKING
    # ======================================================================
    def update_closing_odds(self, live_odds_by_fixture: dict):
        """
        Store closing odds and compute CLV for all PENDING slots.
        Call this ~5 minutes before each fixture's kick-off.

        live_odds_by_fixture: {fixture_id: {"home": odds, "draw": odds, "away": odds, ...}}
        CLV = closing_implied_prob - entry_implied_prob
              Positive CLV = we got a better price than market close (skill signal).
        """
        updated = 0
        COMMISSION = 0.05  # fixed 5%

        for sid, slot in self.state.get("slots", {}).items():
            if slot.get("result") != "PENDING":
                continue
            fid = slot.get("fixture_id")
            if fid is None:
                continue
            closing = live_odds_by_fixture.get(int(fid))
            if not closing:
                continue
            market = slot.get("market")
            closing_odd = closing.get(market)
            if closing_odd and closing_odd > 1.01:
                entry_implied = 1.0 / slot["odds"]
                closing_implied = 1.0 / closing_odd
                # CLV > 0 means we got better than market close (closing_implied > entry_implied
                # means market moved against us after entry, i.e. we got value)
                clv = round(closing_implied - entry_implied, 4)
                slot["closing_odds"] = closing_odd
                slot["clv"] = clv
                updated += 1

        for sid, slot in self.state.get("ml_slots", {}).items():
            if slot.get("result") != "PENDING":
                continue
            fid = slot.get("fixture_id")
            if fid is None:
                continue
            closing = live_odds_by_fixture.get(int(fid))
            if not closing:
                continue
            market = slot.get("market")
            closing_odd = closing.get(market)
            if closing_odd and closing_odd > 1.01:
                entry_implied = 1.0 / slot["odds"]
                closing_implied = 1.0 / closing_odd
                clv = round(closing_implied - entry_implied, 4)
                slot["closing_odds"] = closing_odd
                slot["clv"] = clv
                updated += 1

        if updated > 0:
            self._save_state()
            logger.info(f"CLV aggiornato per {updated} slot aperti.")

    # ======================================================================
    #  FIX 13: BSS MONITOR
    # ======================================================================
    def check_bss_degradation(self, min_samples: int = 20, alert_threshold: float = 0.08):
        """
        Compute production Brier proxy from resolved ML bets in history.
        Compares with MIN_BSS_THRESHOLD (0.12).
        Writes alert to log. Call manually when you want to check model health.

        Returns a dict with metrics for each ML market.
        """
        history = self._load_history()
        by_market: dict = {}

        for day in history:
            for slot in day.get("ml_slots", []):
                result_str = slot.get("result", "PENDING")
                if "VINTO" in result_str:
                    outcome = 1
                elif "PERSO" in result_str:
                    outcome = 0
                else:
                    continue
                prob = slot.get("prob")
                market = slot.get("market", "unknown")
                if prob is None:
                    continue
                if market not in by_market:
                    by_market[market] = {"sq_errors": [], "probs": [], "outcomes": []}
                by_market[market]["sq_errors"].append((prob - outcome) ** 2)
                by_market[market]["probs"].append(prob)
                by_market[market]["outcomes"].append(outcome)

        report = {}
        alerts = []
        for market, data in by_market.items():
            n = len(data["sq_errors"])
            if n < min_samples:
                continue
            avg_brier = sum(data["sq_errors"]) / n
            win_rate = sum(data["outcomes"]) / n
            avg_prob = sum(data["probs"]) / n
            calibration_error = abs(avg_prob - win_rate)
            # Proxy BSS: baseline = (n_classes-1)/n_classes (random classifier).
            # Coerente con la formula usata in scan_best_market_ml e calculate_kelly_stake.
            n_cls_market = ML_MARKET_MAP.get(market, {}).get("n_classes", 2)
            brier_baseline = (n_cls_market - 1) / n_cls_market if n_cls_market > 1 else 0.5
            bss_proxy = 1.0 - (avg_brier / brier_baseline) if brier_baseline > 0 else None

            status = "OK"
            if bss_proxy is not None and bss_proxy < alert_threshold:
                status = "DEGRADED"
                alerts.append(f"{market}: BSS_proxy={bss_proxy:.3f} < {alert_threshold}")

            report[market] = {
                "n": n, "brier": round(avg_brier, 4), "bss_proxy": round(bss_proxy, 3) if bss_proxy is not None else None,
                "win_rate": round(win_rate, 3), "avg_prob": round(avg_prob, 3),
                "calibration_error": round(calibration_error, 3), "status": status,
            }

        if alerts:
            logger.warning(f"🚨 BSS DEGRADATION DETECTED: {' | '.join(alerts)}")
            logger.warning("Action: run ensemble_trainer.py to retrain models.")
        else:
            logger.info(f"✅ BSS monitor: {len(report)} markets checked, all OK.")

        return report

    # ======================================================================
    #  P6: AUTO BSS WEEKLY MONITOR
    # ======================================================================
    def _auto_bss_check(self, interval_days: int = 7, min_samples: int = 20):
        """
        Run check_bss_degradation() automatically once every `interval_days`.

        The last-check date is persisted to bss_monitor_state.json (a file
        separate from the daily-reset money_management_state.json so it
        survives the day-boundary reset).  On degradation the existing
        check_bss_degradation() already emits logger.warning entries; this
        method just ensures the check runs on schedule without manual
        invocation.

        Called at the end of process_signals() so it piggybacks on the normal
        daily operation without requiring a separate cron job.
        """
        monitor_file = os.path.join(os.path.dirname(__file__), "bss_monitor_state.json")
        last_check_str: str | None = None
        if os.path.exists(monitor_file):
            try:
                with open(monitor_file, "r", encoding="utf-8") as _f:
                    last_check_str = json.load(_f).get("last_check")
            except Exception:
                pass

        today = datetime.now().date()
        run_check = True
        if last_check_str:
            try:
                last_check = datetime.strptime(last_check_str, "%Y-%m-%d").date()
                if (today - last_check).days < interval_days:
                    run_check = False
            except ValueError:
                pass

        if not run_check:
            return

        logger.info("🔍 BSS Monitor settimanale: avvio controllo qualità modelli ML...")
        report = None
        try:
            report = self.check_bss_degradation(
                min_samples=min_samples, alert_threshold=0.08
            )
        except Exception as e:
            logger.error(f"Errore BSS auto-check: {e}")
        # Write last_check regardless of whether the check succeeded so that a
        # persistent error (e.g. corrupted history file) does not cause the
        # check to retry on every process_signals call and spam the log.
        try:
            with open(monitor_file, "w", encoding="utf-8") as _f:
                json.dump(
                    {"last_check": today.strftime("%Y-%m-%d"), "last_report": report},
                    _f, indent=2, ensure_ascii=False,
                )
        except Exception as e:
            logger.error(f"Errore scrittura BSS monitor state: {e}")

    # ======================================================================
    #  FIX 20: ANALYTICS SHEET
    # ======================================================================
    def update_analytics_sheet(self):
        """
        Foglio 'Analytics' con distinzione chiara POISSON vs ML:
        - KPI globali affiancati
        - Sezione POISSON (verde): stats + mercati + fasce quota
        - Sezione ML (viola): stats + mercati + BSS + CLV + fasce quota
        - Sezione CONCORDANZE: fixture dove entrambi i track hanno scommesso
        - Sezione SEGNALI SCARTATI: per track, per motivo, dettaglio eventi
        """
        logger.info("📊 Generazione Analytics Sheet (redesign)...")
        try:
            try:
                ws = self.sh.worksheet("Analytics")
                _sheets_retry(ws.clear)
                # Unmerge tutte le celle per evitare residui visivi
                try:
                    _sheets_retry(self.sh.batch_update, {"requests": [
                        {"unmergeCells": {"range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": ws.row_count, "startColumnIndex": 0, "endColumnIndex": 14}}}
                    ]})
                except Exception:
                    pass
            except gspread.exceptions.WorksheetNotFound:
                ws = self.sh.add_worksheet(title="Analytics", rows=2000, cols=14)

            history = self._load_history()
            for _day in history:
                for _s in _day.get("slots", []) + _day.get("ml_slots", []):
                    if not _s.get("is_best"):
                        _sid_base = _s.get("slot_id", "").split(" ")[0]
                        if not re.search(r'[a-z]$', _sid_base):
                            _s["is_best"] = True
                            if "(BEST)" not in _s.get("slot_id", ""):
                                _s["slot_id"] = f"{_s['slot_id']} (BEST)"
            sheet_id = ws.id
            all_data: list = []
            fmt_requests: list = []
            COLS = 14

            def add_row(vals):
                padded = list(vals) + [""] * (COLS - len(vals))
                all_data.append(padded[:COLS])
                return len(all_data) - 1

            # ── colours
            DARK        = {"red": 0.06, "green": 0.06,  "blue": 0.12}
            WHITE       = {"red": 1,    "green": 1,      "blue": 1}
            GOLD        = {"red": 1,    "green": 0.84,   "blue": 0}
            GRAY_HDR    = {"red": 0.82, "green": 0.82,   "blue": 0.85}
            # Poisson — green theme
            P_SECTION   = {"red": 0.05, "green": 0.30,  "blue": 0.10}
            P_SUBHDR    = {"red": 0.13, "green": 0.50,  "blue": 0.18}
            P_HDR       = {"red": 0.80, "green": 0.95,  "blue": 0.82}
            P_ROW_OK    = {"red": 0.88, "green": 0.97,  "blue": 0.88}
            P_ROW_KO    = {"red": 0.99, "green": 0.87,  "blue": 0.87}
            # ML — purple theme
            M_SECTION   = {"red": 0.22, "green": 0.05,  "blue": 0.38}
            M_SUBHDR    = {"red": 0.38, "green": 0.12,  "blue": 0.60}
            M_HDR       = {"red": 0.92, "green": 0.85,  "blue": 0.98}
            M_ROW_OK    = {"red": 0.93, "green": 0.88,  "blue": 0.99}
            M_ROW_KO    = {"red": 0.99, "green": 0.87,  "blue": 0.87}
            # Concordanze — blue
            C_SECTION   = {"red": 0.05, "green": 0.15,  "blue": 0.38}
            C_HDR       = {"red": 0.82, "green": 0.88,  "blue": 0.98}
            # Rejected — dark red
            R_SECTION   = {"red": 0.38, "green": 0.05,  "blue": 0.05}
            R_HDR       = {"red": 0.98, "green": 0.88,  "blue": 0.88}
            # inline colours for text
            G_TEXT      = {"red": 0.05, "green": 0.45,  "blue": 0.05}
            R_TEXT      = {"red": 0.72, "green": 0.08,  "blue": 0.08}
            GRAY_TEXT   = {"red": 0.5,  "green": 0.5,   "blue": 0.5}

            def fmt(r, c1=0, c2=COLS, bg=None, bold=False, color=None, size=10, center=False, italic=False):
                cell_fmt: dict = {}
                if bg:
                    cell_fmt["backgroundColor"] = bg
                tf: dict = {"bold": bold, "fontSize": size}
                if color:
                    tf["foregroundColor"] = color
                if italic:
                    tf["italic"] = True
                cell_fmt["textFormat"] = tf
                if center:
                    cell_fmt["horizontalAlignment"] = "CENTER"
                fmt_requests.append({"repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": r, "endRowIndex": r+1,
                              "startColumnIndex": c1, "endColumnIndex": c2},
                    "cell": {"userEnteredFormat": cell_fmt}, "fields": "userEnteredFormat"}})

            def merge(r, c1=0, c2=COLS):
                fmt_requests.append({"mergeCells": {"range": {"sheetId": sheet_id,
                    "startRowIndex": r, "endRowIndex": r+1,
                    "startColumnIndex": c1, "endColumnIndex": c2},
                    "mergeType": "MERGE_ALL"}})

            # ── helpers ───────────────────────────────────────────────────
            def _resolved(slots):
                return [s for s in slots if s.get("result") not in ("PENDING", None, "")]

            def _won(slots):
                return [s for s in slots if "VINTO" in str(s.get("result", ""))]

            def track_stats(slots):
                res   = _resolved(slots)
                w     = _won(res)
                n     = len(res)
                stk   = sum(s.get("stake", 0) for s in res)
                pnl   = sum(s.get("pnl",   0) for s in res)
                wr    = len(w) / n  if n   else 0
                roi   = pnl  / stk  if stk else 0
                avg_o = sum(s.get("odds", 0) for s in res) / n if n else 0
                return n, len(w), round(pnl, 2), round(stk, 2), wr, roi, round(avg_o, 2)

            def market_breakdown(slots):
                """Returns dict market -> {n, won, pnl, staked}"""
                bm: dict = {}
                for s in _resolved(slots):
                    m = s.get("market_label") or s.get("market") or "?"
                    if m not in bm:
                        bm[m] = {"n": 0, "won": 0, "pnl": 0.0, "staked": 0.0}
                    bm[m]["n"]      += 1
                    bm[m]["staked"] += s.get("stake", 0)
                    bm[m]["pnl"]    += s.get("pnl",   0)
                    if "VINTO" in str(s.get("result", "")):
                        bm[m]["won"] += 1
                return bm

            def odds_bracket_stats(slots):
                BRACKETS = [(1.01,1.5),(1.5,2.0),(2.0,2.5),(2.5,3.0),(3.0,4.0),(4.0,6.0),(6.0,200)]
                rows = []
                for lo, hi in BRACKETS:
                    lbl = f"{lo:.2g}–{hi:.2g}" if hi < 200 else f"{lo:.2g}+"
                    grp = [s for s in _resolved(slots) if lo <= s.get("odds", 0) < hi]
                    if not grp:
                        rows.append((lbl, 0, "—", "—", "—"))
                        continue
                    n  = len(grp)
                    w  = sum(1 for s in grp if "VINTO" in str(s.get("result", "")))
                    p  = sum(s.get("pnl",   0) for s in grp)
                    st = sum(s.get("stake", 0) for s in grp)
                    rows.append((lbl, n, f"{w/n:.1%}", f"€{p:+.2f}", f"{p/st:.2%}" if st else "—"))
                return rows

            # ── collect data ──────────────────────────────────────────────
            pois_slots, ml_slots, all_rejected = [], [], []
            for day in history:
                pois_slots.extend(day.get("slots",    []))
                ml_slots.extend(  day.get("ml_slots", []))
                all_rejected.extend(day.get("rejected", []))

            total_days = len(history)

            # ══════════════════════════════════════════════════════════════
            # TITOLO PRINCIPALE
            # ══════════════════════════════════════════════════════════════
            r = add_row(["📊  ANALYTICS — Performance Storica  |  Poisson vs ML"])
            merge(r)
            fmt(r, bg=DARK, color=GOLD, bold=True, size=14, center=True)
            r = add_row([f"Storico: {total_days} giorni  |  aggiornato da mm_history.json"])
            merge(r)
            fmt(r, bg=DARK, color=GRAY_TEXT, size=9, center=True, italic=True)
            add_row([""])

            # ══════════════════════════════════════════════════════════════
            # KPI GLOBALI affiancati
            # ══════════════════════════════════════════════════════════════
            r = add_row(["📈  KPI GLOBALI"])
            merge(r)
            fmt(r, bg={"red":0.1,"green":0.18,"blue":0.35}, color=WHITE, bold=True, size=12, center=True)

            r = add_row(["", "POISSON", "", "", "", "", "", "ML", "", "", "", "", "", ""])
            fmt(r, bg=GRAY_HDR, bold=True, center=True)
            fmt(r, c1=1, c2=7,  bg=P_HDR, bold=True, center=True)
            fmt(r, c1=7, c2=14, bg=M_HDR, bold=True, center=True)

            r = add_row(["Metrica", "N Bet", "Vinte", "Win Rate", "P&L", "Turnover", "ROI",
                         "N Bet", "Vinte", "Win Rate", "P&L", "Turnover", "ROI", ""])
            fmt(r, bg=GRAY_HDR, bold=True, center=True)

            p_n, p_w, p_pnl, p_stk, p_wr, p_roi, p_ao = track_stats(pois_slots)
            m_n, m_w, m_pnl, m_stk, m_wr, m_roi, m_ao = track_stats(ml_slots)

            r = add_row(["Totale risolti",
                         p_n, p_w, f"{p_wr:.1%}", f"€{p_pnl:+.2f}", f"€{p_stk:.2f}", f"{p_roi:.2%}",
                         m_n, m_w, f"{m_wr:.1%}", f"€{m_pnl:+.2f}", f"€{m_stk:.2f}", f"{m_roi:.2%}", ""])
            fmt(r, center=True)
            fmt(r, c1=4,  c2=5,  color=G_TEXT if p_pnl >= 0 else R_TEXT, bold=True, center=True)
            fmt(r, c1=10, c2=11, color=G_TEXT if m_pnl >= 0 else R_TEXT, bold=True, center=True)

            r = add_row(["Quota media",
                         f"{p_ao:.2f}", "", "", "", "", "",
                         f"{m_ao:.2f}", "", "", "", "", "", ""])
            fmt(r, center=True)
            add_row([""])

            # ══════════════════════════════════════════════════════════════
            # SEZIONE POISSON
            # ══════════════════════════════════════════════════════════════
            r = add_row(["🟢  TRACK POISSON"])
            merge(r)
            fmt(r, bg=P_SECTION, color=WHITE, bold=True, size=13, center=True)

            # -- Poisson mercati
            r = add_row(["  Mercati Poisson"])
            merge(r)
            fmt(r, bg=P_SUBHDR, color=WHITE, bold=True, size=11, center=True)

            r = add_row(["Mercato", "N Bet", "Vinte", "Win Rate", "P&L", "Turnover", "ROI",
                         "", "", "", "", "", "", ""])
            fmt(r, bg=P_HDR, bold=True, center=True)

            p_mkt = market_breakdown(pois_slots)
            if p_mkt:
                for mkt, d in sorted(p_mkt.items(), key=lambda x: -x[1]["pnl"]):
                    wr  = f"{d['won']/d['n']:.1%}"   if d['n']      else "—"
                    roi = f"{d['pnl']/d['staked']:.2%}" if d['staked'] else "—"
                    r = add_row([mkt, d['n'], d['won'], wr, f"€{d['pnl']:+.2f}", f"€{d['staked']:.2f}", roi,
                                 "", "", "", "", "", "", ""])
                    row_bg = P_ROW_OK if d['pnl'] >= 0 else P_ROW_KO
                    fmt(r, bg=row_bg, center=True)
                    fmt(r, c1=4, c2=5, color=G_TEXT if d['pnl'] >= 0 else R_TEXT, bold=True, center=True)
            else:
                r = add_row(["  Nessun dato risolto"])
                fmt(r, color=GRAY_TEXT, italic=True)
            add_row([""])

            # -- Poisson fasce quota
            r = add_row(["  Win Rate per Fascia di Quota — POISSON"])
            merge(r)
            fmt(r, bg=P_SUBHDR, color=WHITE, bold=True, size=11, center=True)

            r = add_row(["Fascia Quota", "N Bet", "Win Rate", "P&L", "ROI",
                         "", "", "", "", "", "", "", "", ""])
            fmt(r, bg=P_HDR, bold=True, center=True)

            for lbl, n, wr, pnl_s, roi_s in odds_bracket_stats(pois_slots):
                r = add_row([lbl, n, wr, pnl_s, roi_s,
                             "", "", "", "", "", "", "", "", ""])
                fmt(r, center=True)
            add_row([""])

            # ══════════════════════════════════════════════════════════════
            # SEZIONE ML
            # ══════════════════════════════════════════════════════════════
            r = add_row(["🟣  TRACK ML"])
            merge(r)
            fmt(r, bg=M_SECTION, color=WHITE, bold=True, size=13, center=True)

            # -- ML mercati + BSS
            r = add_row(["  Mercati ML"])
            merge(r)
            fmt(r, bg=M_SUBHDR, color=WHITE, bold=True, size=11, center=True)

            r = add_row(["Mercato", "N Bet", "Vinte", "Win Rate", "P&L", "Turnover", "ROI",
                         "Brier medio", "BSS proxy", "", "", "", "", ""])
            fmt(r, bg=M_HDR, bold=True, center=True)

            # Build BSS proxy per market from resolved slots
            bss_by_mkt: dict = {}
            for s in _resolved(ml_slots):
                mkey = s.get("market_label") or s.get("market") or "?"
                prob = s.get("prob")
                if prob is None:
                    continue
                outcome = 1 if "VINTO" in str(s.get("result", "")) else 0
                if mkey not in bss_by_mkt:
                    bss_by_mkt[mkey] = {"sq": [], "probs": [], "outcomes": []}
                bss_by_mkt[mkey]["sq"].append((prob - outcome) ** 2)
                bss_by_mkt[mkey]["probs"].append(prob)
                bss_by_mkt[mkey]["outcomes"].append(outcome)

            def _bss(mkt_label):
                d = bss_by_mkt.get(mkt_label)
                if not d or len(d["sq"]) < 5:
                    return "—", "—"
                brier = sum(d["sq"]) / len(d["sq"])
                # Trova il codice mercato dalla label per recuperare n_classes
                n_cls_bss = 2  # default
                for code, info in ML_MARKET_MAP.items():
                    if info.get("label") == mkt_label:
                        n_cls_bss = info.get("n_classes", 2)
                        break
                base = (n_cls_bss - 1) / n_cls_bss if n_cls_bss > 1 else 0.5
                proxy = round(1 - brier / base, 3) if base > 0 else None
                brier_s = f"{brier:.4f}"
                proxy_s = f"{proxy:.3f}" if proxy is not None else "—"
                return brier_s, proxy_s

            m_mkt = market_breakdown(ml_slots)
            if m_mkt:
                for mkt, d in sorted(m_mkt.items(), key=lambda x: -x[1]["pnl"]):
                    wr  = f"{d['won']/d['n']:.1%}"      if d['n']      else "—"
                    roi = f"{d['pnl']/d['staked']:.2%}" if d['staked'] else "—"
                    brier_s, proxy_s = _bss(mkt)
                    r = add_row([mkt, d['n'], d['won'], wr, f"€{d['pnl']:+.2f}", f"€{d['staked']:.2f}", roi,
                                 brier_s, proxy_s, "", "", "", "", ""])
                    row_bg = M_ROW_OK if d['pnl'] >= 0 else M_ROW_KO
                    fmt(r, bg=row_bg, center=True)
                    fmt(r, c1=4, c2=5, color=G_TEXT if d['pnl'] >= 0 else R_TEXT, bold=True, center=True)
            else:
                r = add_row(["  Nessun dato risolto"])
                fmt(r, color=GRAY_TEXT, italic=True)
            add_row([""])

            # -- CLV summary (ML)
            clv_vals = [s.get("clv") for s in _resolved(ml_slots) if s.get("clv") is not None]
            if clv_vals:
                r = add_row(["  CLV — Closing Line Value (ML)"])
                merge(r)
                fmt(r, bg=M_SUBHDR, color=WHITE, bold=True, size=11, center=True)

                r = add_row(["N con CLV", "CLV medio", "CLV StdDev", "Verdetto",
                             "", "", "", "", "", "", "", "", "", ""])
                fmt(r, bg=M_HDR, bold=True, center=True)

                avg_clv  = sum(clv_vals) / len(clv_vals)
                var_clv  = sum((v - avg_clv) ** 2 for v in clv_vals) / len(clv_vals)
                std_clv  = var_clv ** 0.5
                verdict  = "✅ SKILL_SIGNAL" if avg_clv > 0 else "⚠️ NO_EDGE"
                r = add_row([len(clv_vals), f"{avg_clv*100:.3f}%", f"{std_clv*100:.3f}%", verdict,
                             "", "", "", "", "", "", "", "", "", ""])
                fmt(r, center=True)
                clv_color = G_TEXT if avg_clv > 0 else R_TEXT
                fmt(r, c1=1, c2=4, color=clv_color, bold=True, center=True)
                add_row([""])

            # -- ML fasce quota
            r = add_row(["  Win Rate per Fascia di Quota — ML"])
            merge(r)
            fmt(r, bg=M_SUBHDR, color=WHITE, bold=True, size=11, center=True)

            r = add_row(["Fascia Quota", "N Bet", "Win Rate", "P&L", "ROI",
                         "", "", "", "", "", "", "", "", ""])
            fmt(r, bg=M_HDR, bold=True, center=True)

            for lbl, n, wr, pnl_s, roi_s in odds_bracket_stats(ml_slots):
                r = add_row([lbl, n, wr, pnl_s, roi_s,
                             "", "", "", "", "", "", "", "", ""])
                fmt(r, center=True)
            add_row([""])

            # ══════════════════════════════════════════════════════════════
            # CONCORDANZE — stessa logica di Report Ven Dom:
            #   stesso fixture_id E stesso market su entrambi i track
            # ══════════════════════════════════════════════════════════════
            r = add_row(["🔵  CONCORDANZE — Stesso mercato su Poisson e ML"])
            merge(r)
            fmt(r, bg=C_SECTION, color=WHITE, bold=True, size=12, center=True)

            # Build concordance list exactly as Report Ven Dom does
            conc_list_a: list = []
            for day in history:
                p_by_f = {int(s.get("fixture_id", 0)): s for s in day.get("slots", [])
                          if s.get("fixture_id") and s.get("is_best")}
                m_by_f = {int(s.get("fixture_id", 0)): s for s in day.get("ml_slots", [])
                          if s.get("fixture_id") and s.get("is_best")}
                for fid in p_by_f:
                    if fid in m_by_f and p_by_f[fid].get("market") == m_by_f[fid].get("market"):
                        p_s = p_by_f[fid]
                        m_s = m_by_f[fid]
                        conc_list_a.append({"p": p_s, "m": m_s, "date": day.get("date", "")})

            n_conc_a = len(conc_list_a)
            conc_res  = [c for c in conc_list_a if c["p"].get("result") not in ("PENDING", None, "")]

            r = add_row(["N concordanze", "Risolte", "Poisson vinte", "ML vinte",
                         "P&L Poisson", "P&L ML", "P&L Totale",
                         "Win Rate", "", "", "", "", "", ""])
            fmt(r, bg=C_HDR, bold=True, center=True)

            if conc_list_a:
                pc_w   = sum(1 for c in conc_res if "VINTO" in str(c["p"].get("result", "")))
                mc_w   = sum(1 for c in conc_res if "VINTO" in str(c["m"].get("result", "")))
                pc_pnl = sum(c["p"].get("pnl", 0) for c in conc_res)
                mc_pnl = sum(c["m"].get("pnl", 0) for c in conc_res)
                tot    = pc_pnl + mc_pnl
                wr_s   = f"{pc_w/len(conc_res):.1%}" if conc_res else "—"
                r = add_row([n_conc_a, len(conc_res), pc_w, mc_w,
                             f"€{pc_pnl:+.2f}", f"€{mc_pnl:+.2f}", f"€{tot:+.2f}", wr_s,
                             "", "", "", "", "", ""])
                fmt(r, center=True)
                fmt(r, c1=6, c2=7, color=G_TEXT if tot >= 0 else R_TEXT, bold=True, center=True)

                # Detail rows
                add_row([""])
                r = add_row(["Data", "Evento", "Mercato", "Quota P", "Quota ML",
                             "Stake Totale", "Risultato", "P&L Totale",
                             "", "", "", "", "", ""])
                fmt(r, bg=C_HDR, bold=True, center=True)
                for c in conc_list_a:
                    p_s, m_s = c["p"], c["m"]
                    is_pend  = p_s.get("result", "PENDING") == "PENDING"
                    res_str  = "PENDING" if is_pend else str(p_s.get("result", ""))
                    pnl_tot  = (p_s.get("pnl", 0) + m_s.get("pnl", 0)) if not is_pend else 0
                    stk_tot  = p_s.get("stake", 0) + m_s.get("stake", 0)
                    r = add_row([c["date"],
                                 p_s.get("event_name", "?"),
                                 p_s.get("market_label", p_s.get("market", "?")),
                                 p_s.get("odds", ""),
                                 m_s.get("odds", ""),
                                 f"€{stk_tot:.2f}",
                                 res_str,
                                 f"€{pnl_tot:+.2f}" if not is_pend else "—",
                                 "", "", "", "", "", ""])
                    if not is_pend:
                        row_bg = P_ROW_OK if pnl_tot >= 0 else P_ROW_KO
                        fmt(r, bg=row_bg, center=True)
                        fmt(r, c1=7, c2=8, color=G_TEXT if pnl_tot >= 0 else R_TEXT, bold=True, center=True)
                    else:
                        fmt(r, center=True)
            else:
                r = add_row(["  Nessuna concordanza rilevata ancora"])
                fmt(r, color=GRAY_TEXT, italic=True)
            add_row([""])

            # ══════════════════════════════════════════════════════════════
            # SEGNALI SCARTATI
            # ══════════════════════════════════════════════════════════════
            r = add_row(["🚫  SEGNALI SCARTATI"])
            merge(r)
            fmt(r, bg=R_SECTION, color=WHITE, bold=True, size=13, center=True)

            if not all_rejected:
                r = add_row(["  Nessun segnale scartato registrato.",
                             "I dati si accumulano ad ogni esecuzione di pipeline.py (Fix 17).",
                             "", "", "", "", "", "", "", "", "", "", "", ""])
                fmt(r, color=GRAY_TEXT, italic=True)
            else:
                # -- Riepilogo per track
                rej_p = [x for x in all_rejected if x.get("track", "").lower() in ("poisson", "p", "pois")]
                rej_m = [x for x in all_rejected if x.get("track", "").lower() in ("ml", "m")]
                rej_u = [x for x in all_rejected if x not in rej_p and x not in rej_m]

                r = add_row(["Track", "Totale Scartati", "", "", "", "", "", "", "", "", "", "", "", ""])
                fmt(r, bg=R_HDR, bold=True, center=True)

                for lbl, lst in [("Poisson", rej_p), ("ML", rej_m), ("Non classificati", rej_u)]:
                    if lst or lbl != "Non classificati":
                        r = add_row([lbl, len(lst), "", "", "", "", "", "", "", "", "", "", "", ""])
                        fmt(r, center=True)
                r = add_row(["TOTALE", len(all_rejected), "", "", "", "", "", "", "", "", "", "", "", ""])
                fmt(r, bold=True, center=True)
                add_row([""])

                # -- Per motivo × track
                r = add_row(["  Dettaglio: Motivo di Scarto"])
                merge(r)
                fmt(r, bg={"red":0.55,"green":0.12,"blue":0.12}, color=WHITE, bold=True, size=11, center=True)

                r = add_row(["Motivo", "Track", "Conteggio", "% sul totale",
                             "", "", "", "", "", "", "", "", "", ""])
                fmt(r, bg=R_HDR, bold=True, center=True)

                by_reason: dict = {}
                for rej in all_rejected:
                    key = (rej.get("reason", "motivo sconosciuto"), rej.get("track", "?"))
                    by_reason[key] = by_reason.get(key, 0) + 1

                tot_rej = len(all_rejected) or 1
                for (reason, track), count in sorted(by_reason.items(), key=lambda x: -x[1]):
                    pct = f"{count/tot_rej:.1%}"
                    r = add_row([reason, track, count, pct,
                                 "", "", "", "", "", "", "", "", "", ""])
                    fmt(r, center=True)

                # -- Ultimi eventi scartati con dettaglio
                detailed = [x for x in all_rejected if x.get("fixture_id") or x.get("home") or x.get("event")]
                if detailed:
                    add_row([""])
                    r = add_row(["  Ultimi segnali scartati con dettaglio (max 20)"])
                    merge(r)
                    fmt(r, bg={"red":0.55,"green":0.12,"blue":0.12}, color=WHITE, bold=True, size=11, center=True)

                    r = add_row(["Track", "Data", "Evento / Fixture ID", "Motivo",
                                 "", "", "", "", "", "", "", "", "", ""])
                    fmt(r, bg=R_HDR, bold=True, center=True)

                    for rej in detailed[-20:]:
                        if rej.get("event"):
                            event_s = rej["event"]
                        elif rej.get("home"):
                            event_s = rej.get("home", "") + " vs " + rej.get("away", "")
                        else:
                            event_s = str(rej.get("fixture_id", "—"))
                        date_s   = rej.get("date", "—")
                        reason_s = rej.get("reason", "—")
                        track_s  = rej.get("track", "—")
                        r = add_row([track_s, date_s, event_s, reason_s,
                                     "", "", "", "", "", "", "", "", "", ""])
                        fmt(r, center=True)

            add_row([""])
            add_row([""])

            # ══════════════════════════════════════════════════════════════
            # WRITE TO SHEET
            # ══════════════════════════════════════════════════════════════
            end_row = len(all_data)
            col_letter = "N"  # col 14
            
            # Ridimensiona il foglio se necessario
            max_rows = max(end_row + 100, ws.row_count)
            if ws.row_count < end_row + 10:
                _sheets_retry(ws.resize, rows=max_rows, cols=COLS)
                time_module.sleep(1)
            
            # Usa updateCells con stringValue/numberValue per compatibilità locale
            rows_api = []
            for row in all_data:
                cell_vals = []
                for val in row:
                    if isinstance(val, (int, float)):
                        cell_vals.append({"userEnteredValue": {"numberValue": float(val)}})
                    else:
                        cell_vals.append({"userEnteredValue": {"stringValue": str(val)}})
                rows_api.append({"values": cell_vals})
            update_cells_req = {
                "updateCells": {
                    "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": end_row, "startColumnIndex": 0, "endColumnIndex": COLS},
                    "rows": rows_api,
                    "fields": "userEnteredValue"
                }
            }
            fmt_requests.insert(0, update_cells_req)
            time_module.sleep(1)
            
            # Pulisci righe residue
            if end_row < max_rows:
                _sheets_retry(ws.batch_clear, [f"A{end_row+1}:{col_letter}{max_rows}"])
                # Reset formattazione residua
                fmt_requests.append({"unmergeCells": {
                    "range": {"sheetId": sheet_id, "startRowIndex": end_row, "endRowIndex": max_rows, "startColumnIndex": 0, "endColumnIndex": COLS}
                }})
                fmt_requests.append({"repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": end_row, "endRowIndex": max_rows, "startColumnIndex": 0, "endColumnIndex": COLS},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": {"red": 1, "green": 1, "blue": 1},
                        "textFormat": {"foregroundColor": {"red": 0, "green": 0, "blue": 0}, "bold": False, "fontSize": 10}
                    }},
                    "fields": "userEnteredFormat"
                }})
            
            if fmt_requests:
                for i in range(0, len(fmt_requests), 100):
                    _sheets_retry(self.sh.batch_update, {"requests": fmt_requests[i:i+100]})
                    time_module.sleep(0.5)
            _sheets_retry(ws.columns_auto_resize, 0, COLS - 1)
            logger.info(f"✅ Analytics Sheet aggiornato: {end_row} righe, {COLS} colonne.")
        except Exception as e:
            logger.error(f"Errore Analytics Sheet: {e}", exc_info=True)

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
                    n_cls = ML_MARKET_MAP.get(d.get("market", ""), {}).get("n_classes", 2)
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

