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
DEFAULT_MIN_EDGE_PCT = 5.0
DEFAULT_MIN_PROB_PCT = 55.0
DEFAULT_KELLY_FRACTION = 0.25
DEFAULT_MAX_STAKE_PCT = 3.0
DEFAULT_MIN_MATCHES_USED = 5
DEFAULT_COMMISSION_PCT = 5.0  # Commissione Betfair sulle vincite (%)

STATE_FILE = os.path.join(os.path.dirname(__file__), "money_management_state.json")

MARKET_MAP = {
    "H":    {"label": "Home Win",         "json_path": ("markets", "1x2", "H")},
    "D":    {"label": "Pareggio",         "json_path": ("markets", "1x2", "D")},
    "A":    {"label": "Away Win",         "json_path": ("markets", "1x2", "A")},
    "HT05": {"label": "1H Over 0.5",      "json_path": ("markets", "first_half_over_0_5", "True")},
    "O25":  {"label": "Over 2.5",         "json_path": ("markets", "over_2_5", "True")},
    "BTTS": {"label": "BTTS Sì",          "json_path": ("markets", "btts", "True")},
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
        }

    def _save_state(self):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=4, ensure_ascii=False)

    # ======================================================================
    #  EDGE SCANNER MULTI-MERCATO
    # ======================================================================
    def scan_best_market(self, analysis_data, odds_data, inputs_data=None):
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
            if prob is None:
                continue
            if prob > 1:
                prob = prob / 100.0

            quota = odds_data.get(market_key)
            if quota is None or quota <= 1.01:
                continue

            # Applica commissione Betfair: quota_netta = (quota - 1) * (1 - comm%) + 1
            comm = self.config["commission_pct"] / 100.0
            quota_net = (quota - 1.0) * (1.0 - comm) + 1.0
            edge = (prob * quota_net) - 1.0
            if edge < min_edge or prob < min_prob:
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
            return {"market": None, "reason": f"Nessun mercato con Edge>{self.config['min_edge_pct']}% e Prob>{self.config['min_prob_pct']}%"}

        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]
        best["reason"] = f"{best['label']} (Edge {best['edge']*100:+.1f}%, Prob {best['prob']*100:.0f}%)"
        best["all_candidates"] = len(candidates)
        return best

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
    def calculate_kelly_stake(self, prob, odds):
        bankroll = self.state["bankroll"]
        kelly_frac = self.config["kelly_fraction"]
        max_pct = self.config["max_stake_pct"] / 100.0

        # Applica commissione Betfair alla quota per Kelly
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
        logger.info(f"📊 Processando {len(signals_data)} segnali per il Quant Fund MM...")

        if self.state["total_profit_today"] >= self.state["daily_target"]:
            logger.info("🎯 TARGET GIORNALIERO RAGGIUNTO!")
            return self._enrich_all(signals_data, "🎯 TARGET", 0)
        if self.state["total_profit_today"] <= self.state["stop_loss"]:
            logger.warning("🛑 STOP LOSS RAGGIUNTO!")
            return self._enrich_all(signals_data, "🛑 STOP", 0)

        enriched = []
        slot_counter = len(self.state["slots"])
        accepted = 0
        rejected = 0

        for signal in signals_data:
            analysis_markets = signal.get("analysis_markets", {})
            odds = signal.get("odds_data", {})
            inputs = signal.get("inputs_data", {})

            scan = self.scan_best_market(analysis_markets, odds, inputs)

            if scan.get("market") is None:
                signal["slot_id"] = "⊘ SKIP"
                signal["stake"] = ""
                signal["selected_market"] = ""
                signal["edge_pct"] = ""
                signal["score"] = ""
                signal["reason"] = scan.get("reason", "No Value")
                enriched.append(signal)
                rejected += 1
                continue

            prob = scan["prob"]
            odds_val = scan["odds"]
            stake = self.calculate_kelly_stake(prob, odds_val)

            if stake <= 0:
                signal["slot_id"] = "⊘ SKIP"
                signal["stake"] = ""
                signal["selected_market"] = ""
                signal["edge_pct"] = ""
                signal["score"] = ""
                signal["reason"] = "Kelly negativo"
                enriched.append(signal)
                rejected += 1
                continue

            slot_counter += 1
            slot_id = f"S{slot_counter}"

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

            signal["slot_id"] = slot_id
            signal["stake"] = stake
            signal["selected_market"] = f"{scan['label']} @{scan['odds']}"
            signal["edge_pct"] = f"'{scan['edge']*100:+.1f}%"
            signal["score"] = f"{scan['score']:.3f}"
            signal["reason"] = scan["reason"]
            enriched.append(signal)
            accepted += 1

        logger.info(f"✅ Accettati: {accepted} | ❌ Rifiutati: {rejected} | Totale: {len(signals_data)}")
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
        elif market == "HT05":
            if hth is None or hta is None:
                return False  # Dati HT non disponibili
            return (int(hth) + int(hta)) >= 1
        elif market == "O25":
            return (gh + ga) >= 3
        elif market == "BTTS":
            return gh >= 1 and ga >= 1
        return False

    # ======================================================================
    #  REPORT "VEN-DOM" — Foglio di Riepilogo Multi-Giorno
    # ======================================================================
    def update_report_sheet(self):
        """Genera/aggiorna il foglio 'Report Ven Dom' con tutte le operazioni
        di tutti i giorni, raggruppate per data, con P&L progressivo.
        OTTIMIZZATO: usa batch_update per ridurre le chiamate API."""
        logger.info("📋 Aggiornamento foglio 'Report Ven Dom'...")

        try:
            # Carica lo storico completo (tutti i giorni)
            history = self._load_history()

            try:
                ws = self.sh.worksheet("Report Ven Dom")
                _sheets_retry(ws.clear)
            except gspread.exceptions.WorksheetNotFound:
                ws = self.sh.add_worksheet(title="Report Ven Dom", rows=1500, cols=14)

            sheet_id = ws.id

            # === FASE 1: Prepara TUTTI i dati in una griglia unica ===
            all_data = []  # Lista di righe, ciascuna con 14 colonne
            format_requests = []  # Batch di formattazione

            def add_row(values, row_formats=None):
                """Aggiunge una riga di dati e opzionalmente la formattazione."""
                row_idx = len(all_data)  # 0-indexed
                # Padding a 14 colonne
                padded = list(values) + [""] * (14 - len(values))
                all_data.append(padded[:14])
                return row_idx

            def add_format(row_idx, end_row_idx, fmt, start_col=0, end_col=14):
                """Accumula una richiesta di formattazione."""
                format_requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row_idx,
                            "endRowIndex": end_row_idx + 1,
                            "startColumnIndex": start_col,
                            "endColumnIndex": end_col
                        },
                        "cell": {"userEnteredFormat": fmt},
                        "fields": "userEnteredFormat"
                    }
                })

            def add_merge(row_idx, start_col=0, end_col=14):
                """Accumula una richiesta di merge."""
                format_requests.append({
                    "mergeCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row_idx,
                            "endRowIndex": row_idx + 1,
                            "startColumnIndex": start_col,
                            "endColumnIndex": end_col
                        },
                        "mergeType": "MERGE_ALL"
                    }
                })

            # --- TITOLO --- (riga 0)
            r = add_row(["📊 REPORT OPERATIVO — Test Venerdì-Domenica"])
            add_merge(r)
            add_format(r, r, {
                "backgroundColor": {"red": 0.05, "green": 0.05, "blue": 0.18},
                "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 14},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"
            })

            # --- RIEPILOGO GLOBALE --- (riga 1)
            r = add_row(["📈 RIEPILOGO GLOBALE"])
            add_merge(r)
            add_format(r, r, {
                "backgroundColor": {"red": 0.15, "green": 0.15, "blue": 0.15},
                "textFormat": {"foregroundColor": {"red": 0.9, "green": 0.75, "blue": 0.3}, "bold": True, "fontSize": 11},
                "horizontalAlignment": "CENTER"
            })

            # --- Header riepilogo --- (riga 2)
            summary_headers = [
                "Bankroll Iniziale", "Bankroll Attuale", "P&L Totale",
                "Scommesse Totali", "Vinte", "Perse", "Pendenti",
                "Win Rate", "Yield", "Stake Totale",
                "Giorni Operativi", "", "", ""
            ]
            r = add_row(summary_headers)
            add_format(r, r, {
                "backgroundColor": {"red": 0.85, "green": 0.85, "blue": 0.85},
                "textFormat": {"bold": True, "fontSize": 9},
                "horizontalAlignment": "CENTER"
            })

            # Calcola totali da history
            all_slots = []
            daily_dates = set()
            for day in history:
                daily_dates.add(day["date"])
                all_slots.extend(day.get("slots", []))

            total_pnl = sum(s.get("pnl", 0) for s in all_slots if s.get("result") != "PENDING")
            total_staked = sum(s.get("stake", 0) for s in all_slots if s.get("result") != "PENDING")
            total_won = sum(1 for s in all_slots if "VINTO" in str(s.get("result", "")))
            total_lost = sum(1 for s in all_slots if "PERSO" in str(s.get("result", "")))
            total_pending = sum(1 for s in all_slots if s.get("result") == "PENDING")
            total_played = total_won + total_lost
            bankroll_start = self.config["bankroll"]
            bankroll_now = bankroll_start + total_pnl
            win_rate = f"{(total_won/total_played*100):.1f}%" if total_played > 0 else "N/A"
            yield_pct = f"{(total_pnl/total_staked*100):.2f}%" if total_staked > 0 else "N/A"

            summary_values = [
                f"€{bankroll_start:.2f}", f"€{bankroll_now:.2f}", f"€{total_pnl:+.2f}",
                total_played + total_pending, total_won, total_lost, total_pending,
                win_rate, yield_pct, f"€{total_staked:.2f}",
                len(daily_dates), "", "", ""
            ]
            r = add_row(summary_values)
            add_format(r, r, {
                "horizontalAlignment": "CENTER", "textFormat": {"bold": True, "fontSize": 10}
            })
            # Colore P&L nella cella C
            color = {"red": 0.1, "green": 0.6, "blue": 0.1} if total_pnl >= 0 else {"red": 0.7, "green": 0.1, "blue": 0.1}
            add_format(r, r, {"textFormat": {"foregroundColor": color, "bold": True, "fontSize": 13}}, start_col=2, end_col=3)

            # --- Riga vuota --- (riga 4)
            add_row([""])

            # --- DETTAGLIO OPERAZIONI PER GIORNO ---
            running_pnl = 0.0

            for day in sorted(history, key=lambda d: d["date"]):
                date_str = day["date"]
                slots = day.get("slots", [])

                if not slots:
                    continue

                # Header del giorno
                r = add_row([f"📅 {date_str}"])
                add_merge(r)
                add_format(r, r, {
                    "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.35},
                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 11},
                    "horizontalAlignment": "CENTER"
                })

                # Header colonne
                col_headers = [
                    "Slot", "Evento", "Mercato", "Prob", "Quota",
                    "Edge", "Score", "Stake €", "Risultato", "P&L €",
                    "Cassa Dopo", "Gol Casa", "Gol Trasferta", "HT Total"
                ]
                r = add_row(col_headers)
                add_format(r, r, {
                    "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.92},
                    "textFormat": {"bold": True, "fontSize": 9},
                    "horizontalAlignment": "CENTER"
                })

                # Righe operazioni del giorno
                first_data_row = len(all_data)
                for s in slots:
                    pnl = s.get("pnl", 0)
                    if s.get("result") != "PENDING":
                        running_pnl += pnl
                    cassa_dopo = bankroll_start + running_pnl

                    row = [
                        s.get("slot_id", ""),
                        s.get("event_name", ""),
                        s.get("market_label", ""),
                        f"{s.get('prob', 0)*100:.0f}%",
                        s.get("odds", ""),
                        f"{s.get('edge', 0)*100:+.1f}%",
                        f"{s.get('score', 0):.3f}",
                        f"€{s.get('stake', 0):.2f}",
                        s.get("result", "PENDING"),
                        f"€{pnl:+.2f}" if s.get("result") != "PENDING" else "—",
                        f"€{cassa_dopo:.2f}" if s.get("result") != "PENDING" else "—",
                        s.get("goals_home", "—"),
                        s.get("goals_away", "—"),
                        s.get("ht_total", "—"),
                    ]
                    add_row(row)
                last_data_row = len(all_data) - 1

                if last_data_row >= first_data_row:
                    add_format(first_data_row, last_data_row, {
                        "horizontalAlignment": "CENTER", "textFormat": {"fontSize": 9}
                    })

                # Riga riepilogo giorno
                day_pnl = sum(s.get("pnl", 0) for s in slots if s.get("result") != "PENDING")
                day_staked = sum(s.get("stake", 0) for s in slots if s.get("result") != "PENDING")
                day_won = sum(1 for s in slots if "VINTO" in str(s.get("result", "")))
                day_lost = sum(1 for s in slots if "PERSO" in str(s.get("result", "")))
                day_wr = f"{day_won/(day_won+day_lost)*100:.0f}%" if (day_won + day_lost) > 0 else "N/A"

                summary_row = [
                    "", f"TOTALE {date_str}", "", "", "",
                    "", "", f"€{day_staked:.2f}", day_wr, f"€{day_pnl:+.2f}",
                    f"€{bankroll_start + running_pnl:.2f}", "", "", ""
                ]
                r = add_row(summary_row)
                pnl_color = {"red": 0.1, "green": 0.5, "blue": 0.1} if day_pnl >= 0 else {"red": 0.6, "green": 0.1, "blue": 0.1}
                add_format(r, r, {
                    "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.9},
                    "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": pnl_color},
                    "horizontalAlignment": "CENTER"
                })

                # Riga vuota di separazione
                add_row([""])

            # === FASE 2: Scrivi TUTTI i dati in UNA sola chiamata ===
            if all_data:
                end_cell = f"N{len(all_data)}"
                _sheets_retry(ws.update, f"A1:{end_cell}", all_data)
                time_module.sleep(2)  # Pausa di sicurezza tra data e format

            # === FASE 3: Applica TUTTA la formattazione in UNA sola batch ===
            if format_requests:
                _sheets_retry(self.sh.batch_update, {"requests": format_requests})
                time_module.sleep(1)

            # === FASE 4: Freeze + Auto-resize ===
            _sheets_retry(ws.freeze, rows=1)
            _sheets_retry(ws.columns_auto_resize, 0, 13)

            logger.info(f"✅ Report Ven Dom aggiornato ({len(all_slots)} operazioni su {len(daily_dates)} giorni) — {len(format_requests)} formattazioni in batch.")
        except Exception as e:
            logger.error(f"Errore Report Ven Dom: {e}", exc_info=True)

    # ======================================================================
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
        """Salva gli slot di oggi nello storico multi-giorno.
        Aggiorna il giorno se esiste già, altrimenti lo aggiunge."""
        today = self.state["last_run_date"]
        history = self._load_history()

        # Prepara i dati degli slot di oggi
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

        # Aggiorna o aggiungi il giorno
        found = False
        for day in history:
            if day["date"] == today:
                day["slots"] = today_slots
                found = True
                break
        if not found:
            history.append({"date": today, "slots": today_slots})

        self._save_history(history)
        logger.info(f"Storico aggiornato: {today} con {len(today_slots)} slot.")

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

            # Salva i gol nel record
            gh = int(match.get("goals_home") or 0)
            ga = int(match.get("goals_away") or 0)
            hth = match.get("halftime_home")
            hta = match.get("halftime_away")

            slot["goals_home"] = gh
            slot["goals_away"] = ga
            slot["ht_total"] = (int(hth or 0) + int(hta or 0)) if hth is not None else "—"

            # Crea un fake slot dict per _evaluate_bet_result
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

        if resolved > 0:
            self._save_history(history)
            logger.info(f"✅ Risolti {resolved} risultati dallo storico.")

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

