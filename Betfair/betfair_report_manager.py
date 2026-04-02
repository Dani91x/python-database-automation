import glob
import gspread
import os
import json
import logging
import tempfile
import traceback
from datetime import datetime, timedelta
import pytz
from thefuzz import fuzz
import unicodedata
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import local modules
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Ai Engine"))
import config
from Betfair.client import BetfairClient
from db_client import get_supabase_client

# AI Engine imports
from ai_engine.predict_fixture import predict_fixture
from ai_engine.seriea_model_export import train_and_save_all, upload_and_register, MAX_UPLOAD_MB

try:
    from Betfair.money_management import SlotManager, _sheets_retry
except ImportError:
    from money_management import SlotManager, _sheets_retry

# Logging setup
log_file = os.path.join(os.path.dirname(__file__), "betfair_matcher.log")
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
MAPPING_FILE = os.path.join(os.path.dirname(__file__), "betfair_name_map.json")
MATCH_THRESHOLD = 70  # Score for fuzzy matching

class BetfairReportManager:
    def __init__(self):
        self.bf = BetfairClient()
        self.supabase = get_supabase_client()
        self.name_map = self._load_name_map()
        self.gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_FILE)
        self.sh = self.gc.open_by_key(config.SPREADSHEET_ID)
        self.slot_manager = SlotManager(self.gc, self.sh)
        # Instance-level cache (not class-level) to avoid cross-instance state pollution
        self._trained_leagues_this_run: set = set()

    def _load_name_map(self):
        if os.path.exists(MAPPING_FILE):
            with open(MAPPING_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_name_map(self):
        with open(MAPPING_FILE, "w", encoding="utf-8") as f:
            json.dump(self.name_map, f, indent=4, ensure_ascii=False)

    def normalize_name(self, name):
        """Pulisce il nome della squadra per migliorare il matching."""
        if not name: return ""
        
        # Rimuove accenti
        name = "".join(
            c for c in unicodedata.normalize('NFD', name)
            if unicodedata.category(c) != 'Mn'
        )

        # Lowercase, sostituisce punteggiatura e caratteri speciali
        n = name.lower().replace("-", " ").replace(".", "").replace("&", " and ")
        
        # Parole da rimuovere (prefissi/suffissi/filler comuni)
        to_remove = {
            "fc", "united", "as", "ac", "sc", "cf", "u23", "u20", "u19", 
            "women", "real", "atletico", "de", "sporting", "st", "saint",
            "rn", "mt", "mg", "pr", "sp", "rj", "rs", "go", "ba", "pa", "ce", "pe",
            "sports", "club", "ec", "se", "afc", "utd"
        }
        
        # Mappatura specifica di abbreviazioni/variazioni
        translations = {
            "lp": "la plata",
            "gimnasia": "gimnasia",
            "petersburg": "petrograd", # Esempio
            "vd": "virgin islands",
            "vi": "virgin islands",
        }

        # Tokenizza e pulisce
        words = []
        for w in n.split():
            # Rimuove solo alfanumerici
            w = "".join([c for c in w if c.isalnum()])
            if not w: continue
            
            # Applica traduzioni
            w = translations.get(w, w)
            
            # Aggiunge se non è nelle parole da rimuovere
            if w not in to_remove:
                words.append(w)
        
        # Ordina per gestire inversioni ("City Manchester" vs "Manchester City")
        return " ".join(sorted(words))

    def run_daily_report(self, skip_training: bool = False):
        logger.info("Avvio report giornaliero completo..." + (" [SKIP-TRAINING]" if skip_training else ""))
        
        # Super Conservative: pausa iniziale dopo login (che avviene in __init__ -> BetfairClient)
        # In realtà il login avviene esplicitamente se serve, ma assicuriamoci una pausa
        try:
            self.bf.login_cert()
            logger.info("Attesa di sicurezza post-login (5s)...")
            time.sleep(5.0)
        except Exception as e:
            logger.error(f"Errore critico nel login Betfair: {e}")
            return
        
        
        # 2. Recupera eventi Betfair (solo di oggi)
        # Calcola la fine della giornata odierna in UTC
        now_utc = datetime.now(pytz.UTC)
        end_of_today_utc = now_utc.replace(hour=23, minute=59, second=59, microsecond=0)
        to_date_str = end_of_today_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        logger.info(f"Ricerca eventi Betfair fino a: {to_date_str} UTC")
        events = self.bf.list_events(event_type_ids=["1"], to_date=to_date_str)
        event_list = []
        market_map = {}
        
        if events:
            for e in events:
                event_data = e.get("event", {})
                event_list.append({
                    "id": event_data.get("id"),
                    "name": event_data.get("name"),
                    "open_date": event_data.get("openDate"),
                    "country": event_data.get("countryCode", "N/D")
                })

            event_ids = [e["id"] for e in event_list]
            market_catalogues = self.bf.list_market_catalogue(event_ids=event_ids)
            market_map = {m["event"]["id"]: m["marketId"] for m in market_catalogues}
            
            # Aggiorna foglio Betfair
            self._update_betfair_sheet(event_list, market_map)
        else:
            logger.warning("Nessun evento trovato su Betfair.")

        # 3. Recupera tutte le Prediction dal DB
        logger.info("Recupero tutte le prediction della giornata...")
        today = datetime.now(pytz.UTC).strftime("%Y-%m-%d")
        tomorrow = (datetime.now(pytz.UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
        res = self.supabase.from_("fixture_predictions").select("*").gte("fixture_date", today).lt("fixture_date", tomorrow).execute()
        db_fixtures = res.data or []

        # 3b. PRE-FLIGHT: allena SOLO le leghe di oggi (prima del loop per-fixture)
        # Questo evita training inline bloccante durante la generazione del report.
        if db_fixtures and not skip_training:
            today_league_ids = list({f.get("league_id") for f in db_fixtures if f.get("league_id")})
            logger.info(f"🚀 Pre-flight training: {len(today_league_ids)} leghe rilevate oggi → {today_league_ids}")
            self._preflight_train_leagues(today_league_ids)
        elif db_fixtures and skip_training:
            logger.info("⚡ Pre-flight training SALTATO (--skip-training). Uso solo modelli in cache.")

        # 4. Aggiorna foglio Prediction (Tutte)
        self._sync_all_predictions(db_fixtures)
        time.sleep(3)  # Pausa anti-rate-limit tra fasi Google Sheets
        
        # 5. Aggiorna foglio Match Eventi (Debug/Internal)
        if event_list:
            self._update_match_events_sheet(event_list, db_fixtures)
        
        # 6. Risolve risultati dei giorni precedenti (PRIMA di processare oggi)
        logger.info("Fase 6: Risoluzione risultati giorni precedenti (Poisson + ML)...")
        self.slot_manager.resolve_history_results()
        self.slot_manager.resolve_results()
        self.slot_manager.resolve_ml_results()

        # 7. Aggiorna foglio Segnali (La Magia + Edge Scanner)
        if event_list:
            self._update_signals_sheet(event_list, db_fixtures)
        time.sleep(3)  # Pausa anti-rate-limit

        # 8. Salva operazioni di oggi nello storico multi-giorno
        logger.info("Fase 8: Salvataggio storico giornaliero...")
        self.slot_manager.save_today_to_history()

        # 9. Aggiorna Dashboard Money Management
        logger.info("Fase 9: Aggiornamento Dashboard MM...")
        self.slot_manager.update_dashboard_sheet()
        time.sleep(3)  # Pausa anti-rate-limit

        # 10. Aggiorna Report Ven-Dom (multi-giorno)
        logger.info("Fase 10: Aggiornamento Report Ven-Dom...")
        self.slot_manager.update_report_sheet()
        time.sleep(3)  # Pausa anti-rate-limit

        # 11. Aggiorna foglio Analytics (performance storica Poisson + ML)
        logger.info("Fase 11: Aggiornamento foglio Analytics...")
        self.slot_manager.update_analytics_sheet()

        logger.info("✅ Job completato con successo.")

    def _sync_all_predictions(self, db_fixtures):
        if not db_fixtures:
            logger.warning("Nessuna analisi trovata nel DB per oggi.")
            return

        # Ordinamento cronologico
        fixtures_sorted = sorted(db_fixtures, key=lambda x: x.get("fixture_date", ""))

        # Colonne da escludere (Blacklist)
        blacklist = [
            "raw_json", "flat_summary", "created_at", "updated_at",
            "result_status_short", "result_home_goals", "result_away_goals",
            "result_total_goals", "result_outcome", "hit_winner",
            "hit_win_or_draw", "hit_under_over", "evaluated_at",
            "raw_json_odds", "model_predictions_json", "db_json_analisi",
            "ht_predictions"
        ]

        # Identifica le colonne pulite (Headers)
        sample_row = fixtures_sorted[0]
        headers = [col for col in sample_row.keys() if col not in blacklist]
        
        # Prepara i dati
        rows = []
        for fix in fixtures_sorted:
            row = []
            for col in headers:
                val = fix.get(col)
                if isinstance(val, (dict, list)):
                    val = json.dumps(val, ensure_ascii=False)
                row.append(val)
            rows.append(row)

        try:
            ws = self.sh.worksheet("Prediction")
            _sheets_retry(ws.clear)
            _sheets_retry(ws.append_row, headers, value_input_option="RAW")
            # Formattazione: Grassetto intestazione + Allineamento centrato
            _sheets_retry(ws.format, "1:1", {"textFormat": {"bold": True}})
            _sheets_retry(ws.format, "A:Z", {"horizontalAlignment": "CENTER"})
            
            if rows:
                rows = [[(f"'{val}" if isinstance(val, str) and val.startswith("=") else val) for val in row] for row in rows]
                _sheets_retry(ws.append_rows, rows, value_input_option="RAW")
            logger.info(f"Aggiornato foglio 'Prediction' con {len(rows)} analisi.")
        except Exception as err:
            logger.error(f"Errore aggiornamento foglio Prediction: {err}")

    def _update_match_events_sheet(self, bf_events, db_fixtures):
        """Foglio 'Match Events' — lista grezza degli eventi Betfair con match DB."""
        logger.info("Generazione foglio Match Events...")
        try:
            try:
                ws = self.sh.worksheet("Match Events")
                ws.clear()
            except gspread.exceptions.WorksheetNotFound:
                ws = self.sh.add_worksheet(title="Match Events", rows=500, cols=10)

            header = ["Event ID", "Nome Evento", "Data", "Fixture ID DB",
                      "Home DB", "Away DB", "Status", "Goals H", "Goals A", "Lega ID"]
            rows = [header]
            for ev in (bf_events or []):
                ev_id   = ev.get("event_id", "") or ev.get("id", "")
                ev_name = ev.get("name", "")
                ev_date = ev.get("openDate", "") or ev.get("date", "")
                match   = self._find_match(ev, db_fixtures, None)
                if match:
                    rows.append([
                        str(ev_id), ev_name, str(ev_date),
                        match.get("fixture_id", ""),
                        match.get("home_team_name", ""), match.get("away_team_name", ""),
                        match.get("status_short", ""), match.get("goals_home", ""),
                        match.get("goals_away", ""), match.get("league_id", ""),
                    ])
                else:
                    rows.append([str(ev_id), ev_name, str(ev_date),
                                 "—", "—", "—", "—", "—", "—", "—"])
            if len(rows) > 1:
                ws.update(rows, value_input_option="RAW")
            logger.info(f"Foglio 'Match Events' aggiornato: {len(rows)-1} eventi.")
        except Exception as e:
            logger.error(f"Errore _update_match_events_sheet: {e}")

    def _update_signals_sheet(self, bf_events, db_fixtures):
        logger.info("Generazione foglio 'Segnali' (Market Map) — Layout Poisson + ML Side-by-Side...")

        # =====================================================================
        # HEADER — Organizzato in sezioni logiche:
        # SEZIONE 1:  Identità + Stato Lega (0-9)
        # SEZIONE 2:  Poisson Money Management (10-14)
        # SEZIONE 3:  Poisson Deep Stats (15-24)
        # SEZIONE 4:  Poisson Primary Markets — 6 mercati × 3 col = 18 (25-42)
        # SEZIONE 5:  Poisson Extended Markets — 7 mercati × 3 col = 21 (43-63)
        # SEZIONE 6:  ML Money Management (64-68)
        # SEZIONE 7:  ML Primary Markets — 6 mercati × 3 col = 18 (69-86)
        # SEZIONE 8:  ML Additional Targets — prob only (87-96)
        # SEZIONE 9:  Edge Engine v3.0 Diagnostics (97-99)
        # SEZIONE 10: ML Extended Markets — 7 mercati × 3 col = 21 (100-120)
        # =====================================================================
        header = [
            # --- SEZIONE 1: Identità (0-9) ---
            "Data Evento",                  # 0
            "Event ID",                     # 1
            "Nome Evento (Betfair)",        # 2
            "Nome Evento (API-Football)",   # 3
            "Fixture ID",                   # 4
            "League Name",                  # 5
            "Advice",                       # 6
            "HT % (Poisson)",              # 7
            "Elite?",                       # 8
            "Stato Lega AI",               # 9
            # --- SEZIONE 2: Poisson Money Management (10-14) ---
            "Slot Poisson",                # 10
            "Mercato Poisson",             # 11
            "Edge Poisson",                # 12
            "Score Poisson",               # 13
            "Stake € Poisson",            # 14
            # --- SEZIONE 3: Poisson Deep Stats (15-24) ---
            "N. Dati Casa",                # 15
            "N. Dati Trasf",               # 16
            "xG C",                        # 17
            "xG T",                        # 18
            "Avg Gol Lega",                # 19
            "Avg Gol Casa",                # 20
            "Avg Gol Trasf",               # 21
            "Lmb Casa",                    # 22
            "Lmb Trasf",                   # 23
            "Lmb 1H",                      # 24
            # --- SEZIONE 4: Poisson Primary Markets — Prob, Quota, Edge (25-42) ---
            "H % Pois",     "Quota H",    "Edge H Pois",    # 25-27
            "D % Pois",     "Quota D",    "Edge D Pois",    # 28-30
            "A % Pois",     "Quota A",    "Edge A Pois",    # 31-33
            "1H O0.5 Pois", "Quota 1H",  "Edge 1H Pois",   # 34-36
            "BTTS % Pois",  "Quota BTTS","Edge BTTS Pois",  # 37-39
            "O2.5 % Pois",  "Quota O2.5","Edge O2.5 Pois",  # 40-42
            # --- SEZIONE 5: Poisson Extended — O1.5, U1.5, O3.5, U3.5, HT 1X2 (43-63) ---
            "O1.5 % Pois", "Quota O1.5", "Edge O1.5 Pois",  # 43-45
            "U1.5 % Pois", "Quota U1.5", "Edge U1.5 Pois",  # 46-48
            "O3.5 % Pois", "Quota O3.5", "Edge O3.5 Pois",  # 49-51
            "U3.5 % Pois", "Quota U3.5", "Edge U3.5 Pois",  # 52-54
            "HT H % Pois", "Quota HT H", "Edge HT H Pois",  # 55-57
            "HT D % Pois", "Quota HT D", "Edge HT D Pois",  # 58-60
            "HT A % Pois", "Quota HT A", "Edge HT A Pois",  # 61-63
            # --- SEZIONE 6: ML Money Management (64-68) ---
            "Slot ML",                     # 64
            "Mercato ML",                  # 65
            "Edge ML",                     # 66
            "Score ML",                    # 67
            "Stake € ML",                 # 68
            # --- SEZIONE 7: ML Primary Markets — Prob, Quota, Edge ML (69-86) ---
            "H % AI",       "Quota H",    "Edge H ML",      # 69-71
            "D % AI",       "Quota D",    "Edge D ML",      # 72-74
            "A % AI",       "Quota A",    "Edge A ML",      # 75-77
            "1H O0.5 AI",  "Quota 1H",   "Edge 1H ML",     # 78-80
            "BTTS % AI",   "Quota BTTS", "Edge BTTS ML",    # 81-83
            "O2.5 % AI",   "Quota O2.5", "Edge O2.5 ML",   # 84-86
            # --- SEZIONE 8: ML Additional Targets — prob only (87-96) ---
            "O0.5 % AI",   # 87
            "O1.5 % AI",   # 88
            "O3.5 % AI",   # 89
            "O4.5 % AI",   # 90
            "CS Home AI",  # 91
            "CS Away AI",  # 92
            "HT 1X2 H AI", # 93
            "HT 1X2 D AI", # 94
            "HT 1X2 A AI", # 95
            "Goal 2H AI",  # 96
            # --- SEZIONE 9: Edge Engine v3.0 Diagnostics (97-99) ---
            "🛡️ Safety Vault",  # 97
            "Trust Score",       # 98
            "Edge Originale",    # 99
            # --- SEZIONE 10: ML Extended — O1.5, U1.5, O3.5, U3.5, HT 1X2 (100-120) ---
            "O1.5 % ML", "Quota O1.5", "Edge O1.5 ML",   # 100-102
            "U1.5 % ML", "Quota U1.5", "Edge U1.5 ML",   # 103-105
            "O3.5 % ML", "Quota O3.5", "Edge O3.5 ML",   # 106-108
            "U3.5 % ML", "Quota U3.5", "Edge U3.5 ML",   # 109-111
            "HT H % ML", "Quota HT H", "Edge HT H ML",   # 112-114
            "HT D % ML", "Quota HT D", "Edge HT D ML",   # 115-117
            "HT A % ML", "Quota HT A", "Edge HT A ML",   # 118-120
            # --- SEZIONE 11: Poisson HT Ratio per squadra (121-122) ---
            "HT Ratio Casa",   # 121  ht_ratio_home — frazione gol nel 1T (data-driven)
            "HT Ratio Trasf",  # 122  ht_ratio_away
        ]
        NUM_COLS = len(header)  # 123

        # 1. Ordina eventi Betfair cronologicamente
        bf_events_sorted = sorted(bf_events, key=lambda x: x.get("open_date", ""))
        
        rows = []
        match_count = 0

        # --- Helpers di formattazione (definiti una sola volta, non ad ogni iterazione) ---
        def fmt_p(val):
            if val is None: return ""
            if val > 1: return f"'{val:.1f}%"
            return f"'{val*100:.1f}%"

        def fmt_v(val, decimals=2):
            if val is None: return ""
            return round(val, decimals)

        def fmt_q(val):
            if val is None: return ""
            return val

        def fmt_q_nd(val):
            """Come fmt_q ma mostra 'N.D.' se la quota non è disponibile su Betfair."""
            if val is None: return "N.D."
            return val

        def calc_edge(prob, quota, commission=0.05):
            """EV post-commissione Betfair: p*(odds-1)*(1-comm) - (1-p)"""
            if prob is None or quota is None: return None
            p = prob / 100.0 if prob > 1 else prob
            net_profit = (quota - 1.0) * (1.0 - commission)
            return (p * net_profit) - (1.0 - p)

        def fmt_edge(edge):
            if edge is None: return ""
            return f"'{edge*100:+.1f}%"

        # 1. Pre-identificazione match per prefetch quote
        logger.info("Fase 1: Pre-identificazione match per ottimizzazione API Betfair...")
        matched_events = []
        bf_e_map = {}
        for bf_e in bf_events_sorted:
            dt = datetime.strptime(bf_e["open_date"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.UTC)
            matched_db = self._find_match(bf_e, db_fixtures, dt)
            if matched_db:
                matched_events.append((bf_e, matched_db))
                bf_e_map[bf_e["id"]] = (bf_e, matched_db)

        # 2. Prefetch quote in batch (Efficienza API e Policy Compliance)
        matched_ids = list(bf_e_map.keys())
        odds_cache = {}
        if matched_ids:
            logger.info(f"Fase 2: Prefetching quote per {len(matched_ids)} match...")
            odds_cache = self._prefetch_odds_for_events(matched_ids)

        # 3. Generazione righe e preparazione dati per Money Management
        logger.info("Fase 3: Generazione righe del report e calcolo stake...")
        signals_payload_for_mm = []
        raw_rows_data = []
        
        for bf_e in bf_events_sorted:
            dt = datetime.strptime(bf_e["open_date"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.UTC)
            dt_ita = dt.astimezone(pytz.timezone("Europe/Rome")).strftime("%Y-%m-%d %H:%M")
            
            match_data = bf_e_map.get(bf_e["id"])
            
            if match_data:
                bf_e, matched_db = match_data
                match_count += 1
                api_event_name = f"{matched_db['home_team_name']} v {matched_db['away_team_name']}"
                
                advice = matched_db.get("advice", "")
                analysis = matched_db.get("db_json_analisi") or {}
                markets = analysis.get("markets", {})
                inputs = analysis.get("inputs", {})
                
                ht_prob = markets.get("first_half_over_0_5", {}).get("True")
                if ht_prob is None:
                    ht_pred = matched_db.get("ht_predictions") or {}
                    ht_prob = ht_pred.get("hybrid_prob")
                
                btts_prob = markets.get("btts", {}).get("True")
                o25_prob = markets.get("over_2_5", {}).get("True")
                h_p = markets.get("1x2", {}).get("H") or matched_db.get("percent_home")
                d_p = markets.get("1x2", {}).get("D") or matched_db.get("percent_draw")
                a_p = markets.get("1x2", {}).get("A") or matched_db.get("percent_away")
                is_elite = (matched_db.get("ht_predictions") or {}).get("is_elite", False)
                # Poisson Extended Markets
                pois_o15_prob = markets.get("over_1_5", {}).get("True")
                pois_u15_prob = markets.get("over_1_5", {}).get("False")
                pois_o35_prob = markets.get("over_3_5", {}).get("True")
                pois_u35_prob = markets.get("over_3_5", {}).get("False")
                pois_ht_h = markets.get("ht_1x2", {}).get("H")
                pois_ht_d = markets.get("ht_1x2", {}).get("D")
                pois_ht_a = markets.get("ht_1x2", {}).get("A")
                
                odds = odds_cache.get(bf_e["id"], {})

                # Hyperlink Betfair
                mo_id = odds.get("mo_id")
                event_name_val = bf_e["name"]
                if mo_id:
                    event_display = f'=HYPERLINK("https://www.betfair.it/exchange/plus/football/market/{mo_id}"; "{event_name_val}")'
                else:
                    event_display = event_name_val

                # --- INTEGRAZIONE AI ENGINE ---
                ai_preds, ai_status = self._get_or_train_ai_predictions(
                    matched_db["fixture_id"], matched_db["league_id"], odds
                )
                
                # Estrazione probabilità AI per i 6 mercati primari
                ai_h_p, ai_d_p, ai_a_p = None, None, None
                ai_ht_prob, ai_btts_prob, ai_o25_prob = None, None, None
                # Target addizionali ML
                ai_o05, ai_o15, ai_u15, ai_o35, ai_u35, ai_o45 = None, None, None, None, None, None
                ai_cs_home, ai_cs_away = None, None
                ai_ht_h, ai_ht_d, ai_ht_a = None, None, None
                ai_goal_2h = None
                
                if ai_preds and "targets" in ai_preds:
                    t = ai_preds["targets"]
                    # 1X2
                    ai_h_p = t.get("target_1x2", {}).get("H")
                    ai_d_p = t.get("target_1x2", {}).get("D")
                    ai_a_p = t.get("target_1x2", {}).get("A")
                    # HT Over 0.5 — dal nuovo target dedicato o proxy da HT 1X2
                    ht_o05 = t.get("target_ht_over_0_5", {})
                    if ht_o05:
                        ai_ht_prob = ht_o05.get("True", ht_o05.get(True))
                    else:
                        # Fallback: proxy da HT 1X2 — P(Over 0.5 1H) ≈ 1 − P(Draw HT)
                        ht_1x2 = t.get("target_ht_1x2", {})
                        d_ht = ht_1x2.get("D", ht_1x2.get("Draw"))
                        if d_ht is not None:
                            ai_ht_prob = 1.0 - d_ht
                    # BTTS
                    ai_btts_prob = t.get("target_btts", {}).get("True", t.get("target_btts", {}).get(True))
                    # Over 2.5
                    ov25 = t.get("target_over_2_5", {})
                    ai_o25_prob = ov25.get("True", ov25.get(True, ov25.get("over")))
                    # Additional ML targets
                    ov05 = t.get("target_over_0_5", {})
                    ai_o05 = ov05.get("True", ov05.get(True, ov05.get("over")))
                    ov15 = t.get("target_over_1_5", {})
                    ai_o15 = ov15.get("True", ov15.get(True, ov15.get("over")))
                    ai_u15 = ov15.get("False", ov15.get(False, ov15.get("under")))
                    ov35 = t.get("target_over_3_5", {})
                    ai_o35 = ov35.get("True", ov35.get(True, ov35.get("over")))
                    ai_u35 = ov35.get("False", ov35.get(False, ov35.get("under")))
                    ov45 = t.get("target_over_4_5", {})
                    ai_o45 = ov45.get("True", ov45.get(True, ov45.get("over")))
                    cs_h = t.get("target_clean_sheet_home", {})
                    ai_cs_home = cs_h.get("True", cs_h.get(True))
                    cs_a = t.get("target_clean_sheet_away", {})
                    ai_cs_away = cs_a.get("True", cs_a.get(True))
                    ht1x2 = t.get("target_ht_1x2", {})
                    ai_ht_h = ht1x2.get("H")
                    ai_ht_d = ht1x2.get("D")
                    ai_ht_a = ht1x2.get("A")
                    g2h = t.get("target_goal_in_2h", {})
                    ai_goal_2h = g2h.get("True", g2h.get(True))

                # --- PREPARAZIONE PAYLOAD PER MONEY MANAGEMENT ---
                signals_payload_for_mm.append({
                    "event_id": bf_e["id"],
                    "fixture_id": matched_db["fixture_id"],
                    "league_id": matched_db.get("league_id"),  # Edge Engine v3.0
                    "name": api_event_name,
                    "date": dt_ita,
                    "analysis_markets": analysis,
                    "ai_markets": ai_preds.get("targets", {}) if ai_preds else {},
                    "calibration_metrics": ai_preds.get("calibration_metrics", {}) if ai_preds else {},
                    "ml_reliability_multiplier": float(ai_preds.get("reliability", {}).get("score", 1.0)) if ai_preds else 0.0,
                    "odds_data": odds,
                    "inputs_data": inputs,
                    "row_index": len(raw_rows_data)
                })

                row_base = [
                    # SEZIONE 1: Identità (0-9)
                    dt_ita, bf_e["id"], event_display, api_event_name,
                    matched_db["fixture_id"], matched_db["league_name"],
                    advice, fmt_p(ht_prob), "SÌ" if is_elite else "",
                    ai_status,
                    # SEZIONE 2: Poisson MM segnaposti (10-14)
                    "{MM_SLOT}", "{MM_MKT}", "{MM_EDGE}", "{MM_SCORE}", "{MM_STAKE}",
                    # SEZIONE 3: Poisson Deep Stats (15-24)
                    fmt_v(inputs.get("home_matches_used"), 0),
                    fmt_v(inputs.get("away_matches_used"), 0),
                    fmt_v(inputs.get("home_xg_covered"), 0),
                    fmt_v(inputs.get("away_xg_covered"), 0),
                    fmt_v(inputs.get("league_total_avg")),
                    fmt_v(inputs.get("league_home_avg")),
                    fmt_v(inputs.get("league_away_avg")),
                    fmt_v(inputs.get("lambda_home")),
                    fmt_v(inputs.get("lambda_away")),
                    fmt_v((matched_db.get("ht_predictions") or {}).get("lambda_1h")),
                    # SEZIONE 4: Poisson Primary Markets — Prob, Quota, Edge (25-42)
                    fmt_p(h_p),       fmt_q(odds.get("H")),    fmt_edge(calc_edge(h_p, odds.get("H"))),
                    fmt_p(d_p),       fmt_q(odds.get("D")),    fmt_edge(calc_edge(d_p, odds.get("D"))),
                    fmt_p(a_p),       fmt_q(odds.get("A")),    fmt_edge(calc_edge(a_p, odds.get("A"))),
                    fmt_p(ht_prob),   fmt_q(odds.get("HT05")), fmt_edge(calc_edge(ht_prob, odds.get("HT05"))),
                    fmt_p(btts_prob), fmt_q(odds.get("BTTS")), fmt_edge(calc_edge(btts_prob, odds.get("BTTS"))),
                    fmt_p(o25_prob),  fmt_q(odds.get("O25")),  fmt_edge(calc_edge(o25_prob, odds.get("O25"))),
                    # SEZIONE 5: Poisson Extended — O1.5,U1.5,O3.5,U3.5,HT 1X2 (43-63)
                    fmt_p(pois_o15_prob), fmt_q_nd(odds.get("O15")), fmt_edge(calc_edge(pois_o15_prob, odds.get("O15"))),
                    fmt_p(pois_u15_prob), fmt_q_nd(odds.get("U15")), fmt_edge(calc_edge(pois_u15_prob, odds.get("U15"))),
                    fmt_p(pois_o35_prob), fmt_q_nd(odds.get("O35")), fmt_edge(calc_edge(pois_o35_prob, odds.get("O35"))),
                    fmt_p(pois_u35_prob), fmt_q_nd(odds.get("U35")), fmt_edge(calc_edge(pois_u35_prob, odds.get("U35"))),
                    fmt_p(pois_ht_h),     fmt_q_nd(odds.get("HT_H")),fmt_edge(calc_edge(pois_ht_h, odds.get("HT_H"))),
                    fmt_p(pois_ht_d),     fmt_q_nd(odds.get("HT_D")),fmt_edge(calc_edge(pois_ht_d, odds.get("HT_D"))),
                    fmt_p(pois_ht_a),     fmt_q_nd(odds.get("HT_A")),fmt_edge(calc_edge(pois_ht_a, odds.get("HT_A"))),
                    # SEZIONE 6: ML MM segnaposti (64-68)
                    "{ML_SLOT}", "{ML_MKT}", "{ML_EDGE}", "{ML_SCORE}", "{ML_STAKE}",
                    # SEZIONE 7: ML Primary Markets — Prob, Quota, Edge ML (69-86)
                    fmt_p(ai_h_p),       fmt_q(odds.get("H")),    fmt_edge(calc_edge(ai_h_p, odds.get("H"))),
                    fmt_p(ai_d_p),       fmt_q(odds.get("D")),    fmt_edge(calc_edge(ai_d_p, odds.get("D"))),
                    fmt_p(ai_a_p),       fmt_q(odds.get("A")),    fmt_edge(calc_edge(ai_a_p, odds.get("A"))),
                    fmt_p(ai_ht_prob),   fmt_q(odds.get("HT05")), fmt_edge(calc_edge(ai_ht_prob, odds.get("HT05"))),
                    fmt_p(ai_btts_prob), fmt_q(odds.get("BTTS")), fmt_edge(calc_edge(ai_btts_prob, odds.get("BTTS"))),
                    fmt_p(ai_o25_prob),  fmt_q(odds.get("O25")),  fmt_edge(calc_edge(ai_o25_prob, odds.get("O25"))),
                    # SEZIONE 8: ML Additional Targets — prob only (87-96)
                    fmt_p(ai_o05),
                    fmt_p(ai_o15),
                    fmt_p(ai_o35),
                    fmt_p(ai_o45),
                    fmt_p(ai_cs_home),
                    fmt_p(ai_cs_away),
                    fmt_p(ai_ht_h),
                    fmt_p(ai_ht_d),
                    fmt_p(ai_ht_a),
                    fmt_p(ai_goal_2h),
                    # SEZIONE 9: Edge Engine v3.0 Diagnostics (97-99)
                    "",  # Safety Vault placeholder
                    "",  # Trust Score placeholder
                    "",  # Edge Originale placeholder
                    # SEZIONE 10: ML Extended — O1.5,U1.5,O3.5,U3.5,HT 1X2 (100-120)
                    fmt_p(ai_o15), fmt_q_nd(odds.get("O15")), fmt_edge(calc_edge(ai_o15, odds.get("O15"))),
                    fmt_p(ai_u15), fmt_q_nd(odds.get("U15")), fmt_edge(calc_edge(ai_u15, odds.get("U15"))),
                    fmt_p(ai_o35), fmt_q_nd(odds.get("O35")), fmt_edge(calc_edge(ai_o35, odds.get("O35"))),
                    fmt_p(ai_u35), fmt_q_nd(odds.get("U35")), fmt_edge(calc_edge(ai_u35, odds.get("U35"))),
                    fmt_p(ai_ht_h), fmt_q_nd(odds.get("HT_H")), fmt_edge(calc_edge(ai_ht_h, odds.get("HT_H"))),
                    fmt_p(ai_ht_d), fmt_q_nd(odds.get("HT_D")), fmt_edge(calc_edge(ai_ht_d, odds.get("HT_D"))),
                    fmt_p(ai_ht_a), fmt_q_nd(odds.get("HT_A")), fmt_edge(calc_edge(ai_ht_a, odds.get("HT_A"))),
                    # SEZIONE 11: Poisson HT Ratio per squadra (121-122)
                    fmt_v(inputs.get("ht_ratio_home")),
                    fmt_v(inputs.get("ht_ratio_away")),
                ]
            else:
                row_base = [dt_ita, bf_e["id"], bf_e["name"]] + [""] * (NUM_COLS - 3)  # NUM_COLS include le nuove colonne
            
            raw_rows_data.append(row_base)
            
        # 4. Elaborazione Money Management v2 — DUAL TRACK (Poisson + ML)
        if signals_payload_for_mm:
            logger.info("Fase 4: Edge Scanner Dual Track (Poisson + ML)...")
            enriched_signals = self.slot_manager.process_signals(signals_payload_for_mm)
            
            for signal in enriched_signals:
                r_idx = signal["row_index"]
                
                # --- Poisson track ---
                stake_val = signal.get('stake', '')
                if isinstance(stake_val, (int, float)) and stake_val > 0:
                   stake_val = round(stake_val, 2)
                else:
                   stake_val = ''
                raw_rows_data[r_idx][10] = signal.get("slot_id", "")
                raw_rows_data[r_idx][11] = signal.get("selected_market", "")
                raw_rows_data[r_idx][12] = signal.get("edge_pct", "")
                raw_rows_data[r_idx][13] = signal.get("score", "")
                raw_rows_data[r_idx][14] = stake_val
                
                # --- ML track ---
                ml_stake = signal.get('ml_stake', '')
                if isinstance(ml_stake, (int, float)) and ml_stake > 0:
                   ml_stake = round(ml_stake, 2)
                else:
                   ml_stake = ''
                raw_rows_data[r_idx][64] = signal.get("ml_slot_id", "")
                raw_rows_data[r_idx][65] = signal.get("ml_selected_market", "")
                raw_rows_data[r_idx][66] = signal.get("ml_edge_pct", "")
                raw_rows_data[r_idx][67] = signal.get("ml_score", "")
                raw_rows_data[r_idx][68] = ml_stake

                # --- Edge Engine v3.0 Diagnostics ---
                safety_vault = signal.get("safety_vault", False)
                raw_rows_data[r_idx][97] = "🛡️ ATTIVO" if safety_vault else ""
                trust_score = signal.get("trust_score")
                raw_rows_data[r_idx][98] = f"{trust_score:.2f}" if trust_score is not None else ""
                orig_edge = signal.get("original_edge")
                raw_rows_data[r_idx][99] = f"'{orig_edge*100:+.1f}%" if orig_edge is not None else ""
                
        # Sostituisce segnaposti rimasti
        for r in raw_rows_data:
            if len(r) > 10 and r[10] == "{MM_SLOT}":
                r[10] = ""; r[11] = ""; r[12] = ""; r[13] = ""; r[14] = ""
            if len(r) > 64 and r[64] == "{ML_SLOT}":
                r[64] = ""; r[65] = ""; r[66] = ""; r[67] = ""; r[68] = ""
                
        rows = raw_rows_data

        try:
            ws = self._get_or_create_worksheet("Segnali")
            _sheets_retry(ws.clear)
            _sheets_retry(ws.append_row, header, value_input_option="RAW")
            _sheets_retry(ws.format, "1:1", {"textFormat": {"bold": True}})
            
            if rows:
                _sheets_retry(ws.append_rows, rows, value_input_option="USER_ENTERED")
            
            time.sleep(2)
            self._format_signals_sheet(ws, NUM_COLS)
            
            logger.info(f"Aggiornato foglio 'Segnali': {match_count}/{len(bf_events)} match — Layout Poisson+ML con {NUM_COLS} colonne.")
        except Exception as err:
            logger.error(f"Errore aggiornamento foglio Segnali: {err}")

    def _prefetch_odds_for_events(self, event_ids):
        """
        Recupera le quote per una lista di eventi in modalità batch (massima efficienza).
        """
        all_results = {} # event_id -> {H, D, A, HT05, BTTS, O25}
        market_types = [
            'MATCH_ODDS', 'BOTH_TEAMS_TO_SCORE', 'OVER_UNDER_25', 'FIRST_HALF_GOALS_05',
            'OVER_UNDER_15', 'OVER_UNDER_35', 'HALF_TIME',
        ]
        
        try:
            # 1. Recupera catalogo mercati per TUTTI gli eventi
            # Con 7 market_types, chunk da 25 eventi = max 175 mercati per chiamata (< 200 limit).
            all_cats = []
            event_chunk_size = 25
            for i in range(0, len(event_ids), event_chunk_size):
                chunk = event_ids[i:i + event_chunk_size]
                logger.debug(f"Richiesta catalogo per chunk {i//event_chunk_size + 1} ({len(chunk)} eventi)...")

                try:
                    cats = self.bf.list_market_catalogue(
                        event_ids=chunk,
                        market_types=market_types,
                        max_results=200
                    )
                    if cats:
                        all_cats.extend(cats)
                    
                    # Delay ottimizzato
                    time.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Errore durante list_market_catalogue (chunk {i//event_chunk_size + 1}): {e}")
                    if "TOO_MUCH_DATA" in str(e) or "TOO_MANY_REQUESTS" in str(e):
                        logger.critical("Rilevato errore di limiti API Betfair! Interruzione per sicurezza.")
                        return all_results
            
            if not all_cats:
                return all_results

            # Mappatura market_id -> metadata
            market_map = {} # market_id -> {event_id, market_name, runners_cat}
            market_ids = []
            
            for c in all_cats:
                mid = c['marketId']
                market_ids.append(mid)
                market_map[mid] = {
                    "event_id": c['event']['id'],
                    "market_name": c['marketName'],
                    "runners_cat": c.get('runners', [])
                }

            # 2. Recupera quote in batch (OPTIMIZED SAFE: 30 mercati per chiamata, Peso 150)
            batch_size = 30
            all_books = []
            for i in range(0, len(market_ids), batch_size):
                chunk = market_ids[i:i + batch_size]
                logger.debug(f"Fetching market book batch {i//batch_size + 1} ({len(chunk)} mercati)...")
                
                try:
                    books = self.bf.list_market_book(market_ids=chunk)
                    if books:
                        all_books.extend(books)
                    
                    # Delay ottimizzato
                    time.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Errore durante list_market_book (batch {i//batch_size + 1}): {e}")
                    if "TOO_MUCH_DATA" in str(e) or "TOO_MANY_REQUESTS" in str(e):
                        logger.critical("Rilevato errore di limiti API Betfair! Interruzione per sicurezza.")
                        break


            # 3. Processa i risultati e popola il cache
            for book in all_books:
                mid = book['marketId']
                meta = market_map.get(mid)
                if not meta: continue
                
                eid = meta["event_id"]
                mname = meta["market_name"]
                runners_cat = meta["runners_cat"]
                runners_book = {r['selectionId']: r for r in book.get('runners', [])}
                
                if eid not in all_results:
                    all_results[eid] = {
                        "H": None, "D": None, "A": None,
                        "O25": None, "U25": None,
                        "BTTS": None, "BTTS_NO": None,
                        "HT05": None, "HT_U05": None,
                        "O15": None, "U15": None,
                        "O35": None, "U35": None,
                        "HT_H": None, "HT_D": None, "HT_A": None,
                        "mo_id": None
                    }

                def get_best_back(selection_id):
                    r_book = runners_book.get(selection_id)
                    if not r_book: return None
                    back = r_book.get('ex', {}).get('availableToBack', [])
                    return back[0].get('price') if back else None

                def get_best_back_size(selection_id):
                    """Volume disponibile alla migliore quota back (per liquidity check)."""
                    r_book = runners_book.get(selection_id)
                    if not r_book: return None
                    back = r_book.get('ex', {}).get('availableToBack', [])
                    return back[0].get('size') if back else None

                if mname == "Match Odds":
                    all_results[eid]["mo_id"] = mid
                    if len(runners_cat) >= 3:
                        # Betfair Match Odds sort priority: Home(0=sortPriority1), Away(1=sortPriority2), Draw(2=sortPriority3)
                        # Verificato live con listMarketCatalogue: away è sortPriority=2, draw è sortPriority=3
                        all_results[eid]["H"] = get_best_back(runners_cat[0]['selectionId'])
                        all_results[eid]["A"] = get_best_back(runners_cat[1]['selectionId'])
                        all_results[eid]["D"] = get_best_back(runners_cat[2]['selectionId'])
                        # Liquidity sizes (used by place_orders for minimum-size validation)
                        all_results[eid]["H_size"] = get_best_back_size(runners_cat[0]['selectionId'])
                        all_results[eid]["A_size"] = get_best_back_size(runners_cat[1]['selectionId'])
                        all_results[eid]["D_size"] = get_best_back_size(runners_cat[2]['selectionId'])
                elif mname == "Both teams to Score?":
                    if len(runners_cat) >= 2:
                        all_results[eid]["BTTS"] = get_best_back(runners_cat[0]['selectionId'])
                        all_results[eid]["BTTS_NO"] = get_best_back(runners_cat[1]['selectionId'])
                    elif len(runners_cat) >= 1:
                        all_results[eid]["BTTS"] = get_best_back(runners_cat[0]['selectionId'])
                elif mname == "Over/Under 2.5 Goals":
                    if len(runners_cat) >= 2:
                        all_results[eid]["U25"] = get_best_back(runners_cat[0]['selectionId'])
                        all_results[eid]["O25"] = get_best_back(runners_cat[1]['selectionId'])
                elif mname == "First Half Goals 0.5":
                    if len(runners_cat) >= 2:
                        all_results[eid]["HT_U05"] = get_best_back(runners_cat[0]['selectionId'])
                        all_results[eid]["HT05"] = get_best_back(runners_cat[1]['selectionId'])
                elif mname == "Over/Under 1.5 Goals":
                    if len(runners_cat) >= 2:
                        all_results[eid]["U15"] = get_best_back(runners_cat[0]['selectionId'])
                        all_results[eid]["O15"] = get_best_back(runners_cat[1]['selectionId'])
                elif mname == "Over/Under 3.5 Goals":
                    if len(runners_cat) >= 2:
                        all_results[eid]["U35"] = get_best_back(runners_cat[0]['selectionId'])
                        all_results[eid]["O35"] = get_best_back(runners_cat[1]['selectionId'])
                elif mname == "Half Time":
                    # Betfair runner order: Home(0), Away(1), Draw(2)
                    if len(runners_cat) >= 3:
                        all_results[eid]["HT_H"] = get_best_back(runners_cat[0]['selectionId'])
                        all_results[eid]["HT_A"] = get_best_back(runners_cat[1]['selectionId'])
                        all_results[eid]["HT_D"] = get_best_back(runners_cat[2]['selectionId'])

        except Exception as e:
            logger.error(f"Errore critico nel prefetch delle quote: {e}")
            
        return all_results

    def _format_signals_sheet(self, ws, num_cols):
        """
        Applica formattazione professionale al foglio Segnali — Layout Poisson + ML (121 col).
        Sezioni: Identità(0-9) | Poisson MM(10-14) | Stats(15-24) | Poisson Primary(25-42)
                 | Poisson Extended(43-63) | ML MM(64-68) | ML Primary(69-86)
                 | ML Additional(87-96) | Diagnostics(97-99) | ML Extended(100-120)
        """
        try:
            sheet_id = ws.id

            def _rng(r1, r2, c1, c2):
                return {"sheetId": sheet_id, "startRowIndex": r1, "endRowIndex": r2, "startColumnIndex": c1, "endColumnIndex": c2}

            def _bg(r1, r2, c1, c2, color):
                return {"repeatCell": {"range": _rng(r1, r2, c1, c2), "cell": {"userEnteredFormat": {"backgroundColor": color}}, "fields": "userEnteredFormat.backgroundColor"}}

            def _txt(r1, r2, c1, c2, fmt):
                return {"repeatCell": {"range": _rng(r1, r2, c1, c2), "cell": {"userEnteredFormat": {"textFormat": fmt}}, "fields": "userEnteredFormat.textFormat"}}

            def _align(r1, r2, c1, c2, align):
                return {"repeatCell": {"range": _rng(r1, r2, c1, c2), "cell": {"userEnteredFormat": {"horizontalAlignment": align}}, "fields": "userEnteredFormat.horizontalAlignment"}}

            requests = [
                # === 1. HEADER: Dark Navy + White Bold ===
                {"repeatCell": {"range": _rng(0, 1, 0, num_cols),
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": {"red": 0.0, "green": 0.13, "blue": 0.28},
                        "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 10},
                        "horizontalAlignment": "CENTER"
                    }}, "fields": "userEnteredFormat"}},
                # Freeze header
                {"updateSheetProperties": {"properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}}, "fields": "gridProperties.frozenRowCount"}},

                # === 2. SFONDI PER SEZIONE ===
                # Identità (0-9): Grigio chiaro
                _bg(1, 1000, 0, 10, {"red": 0.95, "green": 0.95, "blue": 0.96}),
                # Poisson MM (10-14): Verde menta
                _bg(1, 1000, 10, 15, {"red": 0.85, "green": 0.95, "blue": 0.87}),
                # Deep Stats (15-24): Blu ghiaccio
                _bg(1, 1000, 15, 25, {"red": 0.88, "green": 0.92, "blue": 1.0}),
                # Poisson Primary (25-42): Crema caldo
                _bg(1, 1000, 25, 43, {"red": 1.0, "green": 0.96, "blue": 0.88}),
                # Poisson Extended (43-63): Verde salvia (distinto dal Primary)
                _bg(1, 1000, 43, 64, {"red": 0.88, "green": 0.96, "blue": 0.88}),
                # ML MM (64-68): Lavanda
                _bg(1, 1000, 64, 69, {"red": 0.91, "green": 0.85, "blue": 0.95}),
                # ML Primary (69-86): Pesca chiaro
                _bg(1, 1000, 69, 87, {"red": 1.0, "green": 0.91, "blue": 0.85}),
                # ML Additional (87-96): Rosa pallido
                _bg(1, 1000, 87, 97, {"red": 0.98, "green": 0.88, "blue": 0.92}),
                # Diagnostics (97-99): Rosso tenue
                _bg(1, 1000, 97, 100, {"red": 1.0, "green": 0.90, "blue": 0.90}),
                # ML Extended (100-120): Turchese chiaro
                _bg(1, 1000, 100, 121, {"red": 0.85, "green": 0.96, "blue": 0.96}),

                # === 3. TEXT FORMAT PER COLONNE SPECIALI ===
                # Poisson Slot (10): Blu scuro grassetto
                _txt(1, 1000, 10, 11, {"foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.5}, "bold": True, "fontSize": 10}),
                # Poisson Mercato (11): Grassetto
                _txt(1, 1000, 11, 12, {"bold": True, "fontSize": 10}),
                # Poisson Edge (12): Verde scuro grassetto
                _txt(1, 1000, 12, 13, {"foregroundColor": {"red": 0.0, "green": 0.35, "blue": 0.0}, "bold": True}),
                # Poisson Score (13): Corsivo
                _txt(1, 1000, 13, 14, {"italic": True}),
                # Poisson Stake (14): Verde valuta grassetto
                _txt(1, 1000, 14, 15, {"foregroundColor": {"red": 0.0, "green": 0.3, "blue": 0.0}, "bold": True, "fontSize": 10}),
                # Advice (6): Grassetto scuro
                _txt(1, 1000, 6, 7, {"bold": True, "foregroundColor": {"red": 0.2, "green": 0.2, "blue": 0.4}}),
                # Stato Lega AI (9): Grassetto
                _txt(1, 1000, 9, 10, {"bold": True}),
                # ML Slot (64): Viola grassetto
                _txt(1, 1000, 64, 65, {"foregroundColor": {"red": 0.4, "green": 0.0, "blue": 0.5}, "bold": True, "fontSize": 10}),
                # ML Mercato (65): Grassetto
                _txt(1, 1000, 65, 66, {"bold": True, "fontSize": 10}),
                # ML Edge (66): Viola scuro grassetto
                _txt(1, 1000, 66, 67, {"foregroundColor": {"red": 0.4, "green": 0.0, "blue": 0.4}, "bold": True}),
                # ML Score (67): Corsivo
                _txt(1, 1000, 67, 68, {"italic": True}),
                # ML Stake (68): Viola valuta grassetto
                _txt(1, 1000, 68, 69, {"foregroundColor": {"red": 0.4, "green": 0.0, "blue": 0.3}, "bold": True, "fontSize": 10}),

                # === 4. ALLINEAMENTO globale ===
                _align(1, 1000, 0, num_cols, "CENTER"),
            ]

            # Quote Bold — Poisson Primary: 26, 29, 32, 35, 38, 41
            for col_idx in [26, 29, 32, 35, 38, 41]:
                requests.append(_txt(1, 1000, col_idx, col_idx + 1, {"bold": True}))

            # Quote Bold — Poisson Extended: O1.5→44, U1.5→47, O3.5→50, U3.5→53, HT_H→56, HT_D→59, HT_A→62
            for col_idx in [44, 47, 50, 53, 56, 59, 62]:
                requests.append(_txt(1, 1000, col_idx, col_idx + 1, {"bold": True}))

            # Quote Bold — ML Primary: H→70, D→73, A→76, HT05→79, BTTS→82, O25→85
            for col_idx in [70, 73, 76, 79, 82, 85]:
                requests.append(_txt(1, 1000, col_idx, col_idx + 1, {"bold": True}))

            # Quote Bold — ML Extended: O1.5→101, U1.5→104, O3.5→107, U3.5→110, HT_H→113, HT_D→116, HT_A→119
            for col_idx in [101, 104, 107, 110, 113, 116, 119]:
                requests.append(_txt(1, 1000, col_idx, col_idx + 1, {"bold": True}))

            # === 5. CONDITIONAL FORMATTING: Edge positivo = verde ===
            # Poisson Primary edge:   27,30,33,36,39,42
            # Poisson Extended edge:  45,48,51,54,57,60,63
            # ML Primary edge:        71,74,77,80,83,86
            # ML Extended edge:       102,105,108,111,114,117,120
            all_edge_cols = [
                27, 30, 33, 36, 39, 42,          # Poisson Primary
                45, 48, 51, 54, 57, 60, 63,       # Poisson Extended
                71, 74, 77, 80, 83, 86,           # ML Primary
                102, 105, 108, 111, 114, 117, 120, # ML Extended
            ]
            for col_idx in all_edge_cols:
                requests.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [_rng(1, 1000, col_idx, col_idx + 1)],
                            "booleanRule": {
                                "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "+"}]},
                                "format": {"backgroundColor": {"red": 0.75, "green": 1.0, "blue": 0.75}, "textFormat": {"foregroundColor": {"red": 0.0, "green": 0.3, "blue": 0.0}, "bold": True}}
                            }
                        },
                        "index": 0
                    }
                })

            # Larghezze fisse per sezione
            def _col_width(c1, c2, px):
                return {"updateDimensionProperties": {
                    "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                              "startIndex": c1, "endIndex": c2},
                    "properties": {"pixelSize": px},
                    "fields": "pixelSize"
                }}
            requests += [
                _col_width(0, 2, 90),    # Data + EventID
                _col_width(2, 4, 160),   # Nomi evento
                _col_width(4, 10, 80),   # Fixture ID, league, advice, ecc.
                _col_width(10, 15, 75),  # Poisson MM
                _col_width(15, 25, 70),  # Deep Stats
                _col_width(25, 43, 72),  # Poisson Primary
                _col_width(43, 64, 72),  # Poisson Extended
                _col_width(64, 69, 75),  # ML MM
                _col_width(69, 121, 72), # ML Markets (Primary + Additional + Diagnostics + Extended)
            ]

            # Esegui batch unico
            _sheets_retry(self.sh.batch_update, {"requests": requests})

            logger.info(f"Formattazione Poisson+ML applicata — {len(requests)} operazioni in batch.")
        except Exception as e:
            logger.warning(f"Errore durante la formattazione grafica: {e}")

    # Costanti di classe
    MODEL_CACHE_TTL_DAYS = 7   # Riuserà modelli locali (league_XXX) se < 7 giorni
    MODEL_RETRAIN_TTL_DAYS = 7  # Riaddestra modelli scaricati da Supabase se > 7 giorni

    def _check_and_invalidate_stale_models(self, league_id: int) -> bool:
        """
        Controlla se i modelli scaricati localmente per questa lega sono scaduti.
        Se scaduti (> MODEL_RETRAIN_TTL_DAYS): cancella i file locali e rimuove
        le entry dal registry Supabase, in modo che predict_fixture() triggeri
        automaticamente il retraining al prossimo tentativo.
        Ritorna True se i modelli erano scaduti e sono stati invalidati.
        """
        cache_dir = os.path.join("Ai Engine", "models_cache", "downloaded", f"league_{league_id}")
        local_models = glob.glob(os.path.join(cache_dir, "ensemble_v2_*.pkl.gz")) if os.path.isdir(cache_dir) else []

        if not local_models:
            return False  # Nessun modello locale: gestito da "No models found" in predict_fixture

        newest_mtime = max(os.path.getmtime(p) for p in local_models)
        age_days = (datetime.now().timestamp() - newest_mtime) / 86400.0

        if age_days < self.MODEL_RETRAIN_TTL_DAYS:
            return False  # Modelli freschi, nessuna azione necessaria

        logger.info(
            f"Modelli League {league_id} scaduti ({age_days:.0f}gg > {self.MODEL_RETRAIN_TTL_DAYS}gg). "
            f"Invalido cache locale e registry Supabase..."
        )

        # 1. Cancella file locali
        for f in local_models:
            try:
                os.remove(f)
            except Exception:
                pass

        # 2. Rimuovi entry dal registry Supabase → predict_fixture → "No models found" → retraining
        try:
            sb = get_supabase_client()
            sb.table("ai_model_registry").delete().eq("league_id", league_id).execute()
            logger.info(f"Registry Supabase pulito per League {league_id}.")
        except Exception as e:
            logger.warning(f"Impossibile pulire registry Supabase per League {league_id}: {e}")

        return True

    def _predownload_models_for_league(self, league_id: int) -> int:
        """
        Scarica in anticipo tutti i modelli dal registry Supabase nella cache locale.
        Eseguito durante il pre-flight così predict_fixture() non deve scaricare on-demand.
        Ritorna il numero di modelli scaricati.
        Usa scrittura atomica (tempfile + os.replace) per evitare file corrotti parziali.
        """
        sb = get_supabase_client()
        bucket = f"ai-models-league-{league_id}"
        out_dir = os.path.join("Ai Engine", "models_cache", "downloaded", f"league_{league_id}")
        os.makedirs(out_dir, exist_ok=True)

        try:
            reg = sb.table("ai_model_registry").select("storage_path").eq("league_id", league_id).execute()
            models = getattr(reg, "data", None) or []
        except Exception as e:
            logger.warning(f"  Pre-download League {league_id}: errore query registry: {e}")
            return 0

        downloaded = 0
        for m in models:
            path = m.get("storage_path", "")
            if not path:
                continue
            local_path = os.path.join(out_dir, os.path.basename(path))
            if os.path.exists(local_path):
                continue  # già in cache
            tmp_path = None
            try:
                res = sb.storage.from_(bucket).download(path)
                # Scrittura atomica: scrivi su temp → rinomina, evita file corrotti parziali
                with tempfile.NamedTemporaryFile(dir=out_dir, delete=False, suffix=".tmp") as tmp:
                    tmp.write(res)
                    tmp_path = tmp.name
                os.replace(tmp_path, local_path)
                tmp_path = None  # rinomina riuscita
                downloaded += 1
            except Exception as e:
                logger.warning(f"  Pre-download League {league_id} — {path}: {e}")
            finally:
                if tmp_path is not None:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

        return downloaded

    def _preflight_train_leagues(self, league_ids: list) -> None:
        """
        Fase pre-flight: controlla e allena in anticipo tutte le leghe necessarie
        per la giornata odierna, in modo che il loop per-fixture sia solo predict (veloce).

        Logica per ogni league_id:
          1. Già processata in questo run → skip
          2. Registry Supabase ha modelli freschi + cache locale fresca → skip
          3. Registry OK ma cache locale assente → PRE-DOWNLOAD ora (fix lazy-download)
          4. Cache locale di training fresca → upload registry
          5. Altrimenti → training completo + upload (parallelo tra leghe)
        """
        total = len(league_ids)
        if total == 0:
            logger.info("Pre-flight: nessuna lega da processare.")
            return

        sb = self.supabase
        lock = threading.Lock()

        def _process_league(args):
            idx, league_id = args
            if not league_id:
                return
            with lock:
                if league_id in self._trained_leagues_this_run:
                    logger.info(f"  [{idx}/{total}] League {league_id}: già processata, skip.")
                    return

            logger.info(f"  [{idx}/{total}] League {league_id}: controllo registry...")

            # 1. Controlla registry Supabase
            try:
                reg_resp = sb.table("ai_model_registry").select("target").eq("league_id", league_id).limit(1).execute()
                registry_has_models = bool(getattr(reg_resp, "data", None))
            except Exception as e:
                logger.warning(f"  [{idx}/{total}] League {league_id}: errore query registry ({e}), procedo con training.")
                registry_has_models = False

            if registry_has_models:
                dl_dir = os.path.join("Ai Engine", "models_cache", "downloaded", f"league_{league_id}")
                local_dl = glob.glob(os.path.join(dl_dir, "ensemble_v2_*.pkl.gz")) if os.path.isdir(dl_dir) else []
                if local_dl:
                    newest = max(os.path.getmtime(p) for p in local_dl)
                    age_days = (datetime.now().timestamp() - newest) / 86400.0
                    if age_days < self.MODEL_RETRAIN_TTL_DAYS:
                        logger.info(f"  [{idx}/{total}] League {league_id}: registry OK + cache locale fresca ({age_days:.1f}gg). Skip.")
                        with lock:
                            self._trained_leagues_this_run.add(league_id)
                        return

                # Registry OK ma file locali assenti/scaduti: pre-scarica ORA (evita download lazy per-fixture)
                logger.info(f"  [{idx}/{total}] League {league_id}: registry OK, pre-download modelli...")
                n = self._predownload_models_for_league(league_id)
                logger.info(f"  [{idx}/{total}] League {league_id}: {n} modelli pre-scaricati. ✅")
                with lock:
                    self._trained_leagues_this_run.add(league_id)
                return

            # 2. Nessun modello in registry: controlla cache locale di training
            self._check_and_invalidate_stale_models(league_id)
            cache_dir = os.path.join("Ai Engine", "models_cache", f"league_{league_id}")
            local_models = glob.glob(os.path.join(cache_dir, "ensemble_v2_*.pkl.gz")) if os.path.isdir(cache_dir) else []

            need_training = True
            if local_models:
                newest = max(os.path.getmtime(p) for p in local_models)
                age_days = (datetime.now().timestamp() - newest) / 86400.0
                if age_days < self.MODEL_CACHE_TTL_DAYS:
                    logger.info(f"  [{idx}/{total}] League {league_id}: cache training fresca ({age_days:.1f}gg). Upload senza retraining...")
                    try:
                        uploaded = 0
                        for model_path in local_models:
                            file_size = os.path.getsize(model_path)
                            if file_size > MAX_UPLOAD_MB * 1024 * 1024:
                                logger.warning(
                                    f"  [{idx}/{total}] League {league_id}: "
                                    f"{os.path.basename(model_path)} troppo grande "
                                    f"({file_size / 1024 / 1024:.1f} MB > {MAX_UPLOAD_MB} MB) — upload saltato."
                                )
                                continue
                            target = os.path.basename(model_path).replace("ensemble_v2_", "").replace(".pkl.gz", "")
                            upload_and_register(model_path, file_size, target, {
                                "league_id": league_id, "model_type": "ensemble_v2",
                                "accuracy": None, "logloss": None, "brier": None,
                                "feature_count": None, "train_rows": None, "trained_range": "cached",
                            })
                            uploaded += 1
                        logger.info(f"  [{idx}/{total}] League {league_id}: {uploaded}/{len(local_models)} modelli caricati.")
                        need_training = False
                    except Exception as e:
                        logger.warning(f"  [{idx}/{total}] League {league_id}: upload fallito ({e}), procedo con training.")

            # 3. Training completo
            if need_training:
                logger.info(f"  [{idx}/{total}] League {league_id}: ⚙️ Training completo (3 stagioni)...")
                try:
                    results = train_and_save_all(league_id, last_n_seasons=3)
                    uploaded = 0
                    for r in results:
                        if r.get("upload_skipped"):
                            logger.warning(
                                f"  [{idx}/{total}] League {league_id}: {r['target']} troppo grande "
                                f"({r.get('file_size', 0) / 1024 / 1024:.1f} MB) — upload saltato."
                            )
                            continue
                        upload_and_register(r["model_path"], r["file_size"], r["target"], r)
                        uploaded += 1
                    logger.info(
                        f"  [{idx}/{total}] League {league_id}: ✅ Training OK "
                        f"({len(results)} target, {uploaded} uploadati)."
                    )
                except Exception as e:
                    logger.warning(f"  [{idx}/{total}] League {league_id}: ⚠️ Training fallito: {e}. Salto lega.")

            with lock:
                self._trained_leagues_this_run.add(league_id)

        # Parallelizzazione per lega: max 4 worker (bilanciamento CPU/RAM/rete)
        # Il training usa ThreadPoolExecutor internamente (sklearn rilascia GIL)
        n_workers = max(1, min(4, total))
        logger.info(f"🚀 Pre-flight: {total} leghe con {n_workers} worker paralleli...")
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            futures = [executor.submit(_process_league, (idx, lid)) for idx, lid in enumerate(league_ids, 1)]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    logger.error(f"Pre-flight worker errore: {exc}")

        logger.info(f"✅ Pre-flight completato: {len(self._trained_leagues_this_run)}/{total} leghe pronte.")

    def _get_or_train_ai_predictions(self, fixture_id, league_id, odds_dict):
        """Helper robusto per predizioni AI. Ritorna (predictions, status_string).
        Con smart caching: se i modelli locali sono freschi (<7gg), li riusa senza riaddestramento.
        Retraining automatico se i modelli scaricati da Supabase sono scaduti (>7gg).
        status = 'OK' | 'LEGA SALTATA PER DATI INSUFFICIENTI' | 'ERRORE AI'"""
        # Invalida modelli scaduti prima di tentare la predizione
        if league_id not in self._trained_leagues_this_run:
            self._check_and_invalidate_stale_models(league_id)

        try:
            preds = predict_fixture(fixture_id, store=True, live_odds=odds_dict)
            return preds, "OK"
        except RuntimeError as e:
            if "No models found" in str(e):
                # Evita di addestrare la stessa lega più volte nella stessa esecuzione
                if league_id in self._trained_leagues_this_run:
                    logger.info(f"League {league_id} già processata in questa esecuzione. Salto.")
                    return None, "LEGA SALTATA PER DATI INSUFFICIENTI"

                logger.info(f"Modelli assenti nel registry per League {league_id}. Controllo cache locale...")
                self._trained_leagues_this_run.add(league_id)

                try:
                    # --- SMART CACHE: controlla se esistono modelli locali freschi ---
                    cache_dir = os.path.join("Ai Engine", "models_cache", f"league_{league_id}")
                    local_models = glob.glob(os.path.join(cache_dir, "ensemble_v2_*.pkl.gz")) if os.path.isdir(cache_dir) else []

                    need_training = True
                    if local_models:
                        # Controlla l'età del modello più recente
                        newest_mtime = max(os.path.getmtime(p) for p in local_models)
                        age_days = (datetime.now().timestamp() - newest_mtime) / 86400.0
                        if age_days < self.MODEL_CACHE_TTL_DAYS:
                            logger.info(f"✅ Cache locale fresca ({age_days:.1f}gg < {self.MODEL_CACHE_TTL_DAYS}gg). "
                                       f"Upload di {len(local_models)} modelli senza riaddestrare.")
                            # Upload modelli locali al registry (molto più veloce del training)
                            uploaded = 0
                            for model_path in local_models:
                                file_size = os.path.getsize(model_path)
                                if file_size > MAX_UPLOAD_MB * 1024 * 1024:
                                    logger.warning(
                                        f"League {league_id}: {os.path.basename(model_path)} troppo grande "
                                        f"({file_size / 1024 / 1024:.1f} MB > {MAX_UPLOAD_MB} MB) — upload saltato."
                                    )
                                    continue
                                target = os.path.basename(model_path).replace("ensemble_v2_", "").replace(".pkl.gz", "")
                                upload_and_register(model_path, file_size, target, {
                                    "league_id": league_id,
                                    "model_type": "ensemble_v2",
                                    "accuracy": None,
                                    "logloss": None,
                                    "brier": None,
                                    "feature_count": None,
                                    "train_rows": None,
                                    "trained_range": "cached",
                                })
                                uploaded += 1
                            logger.info(f"League {league_id}: {uploaded}/{len(local_models)} modelli caricati.")
                            need_training = False
                        else:
                            logger.info(f"⏰ Cache locale scaduta ({age_days:.1f}gg >= {self.MODEL_CACHE_TTL_DAYS}gg). Riaddestrare.")

                    if need_training:
                        logger.info(f"🔧 Training completo League {league_id}...")
                        results = train_and_save_all(league_id, last_n_seasons=3)
                        uploaded = 0
                        for r in results:
                            if r.get("upload_skipped"):
                                logger.warning(
                                    f"League {league_id}: {r['target']} troppo grande "
                                    f"({r.get('file_size', 0) / 1024 / 1024:.1f} MB) — upload saltato."
                                )
                                continue
                            upload_and_register(r["model_path"], r["file_size"], r["target"], r)
                            uploaded += 1
                        logger.info(f"League {league_id}: training OK ({len(results)} target, {uploaded} uploadati).")

                    logger.info(f"League {league_id} pronta. Riprendo predizione.")
                    preds = predict_fixture(fixture_id, store=True, live_odds=odds_dict)
                    return preds, "OK"
                except Exception as ex:
                    logger.warning(f"Dati insufficienti per lega {league_id}: {ex}. Salto AI.")
                    return None, "LEGA SALTATA PER DATI INSUFFICIENTI"
            else:
                logger.warning(f"Errore AI fixture {fixture_id}: {e}\n{traceback.format_exc()}")
                return None, "ERRORE AI"
        except Exception as generic_e:
            logger.warning(f"Errore non gestito AI fixture {fixture_id}: {generic_e}\n{traceback.format_exc()}")
            return None, "ERRORE AI"

    def _fetch_odds_for_event(self, event_id):
        # [Manteniamo per ora per retrocompatibilità o debug, ma useremo _prefetch_odds_for_events]
        pass

    def _find_match(self, bf_e, db_fixtures, dt_utc):
        """Helper per trovare il match nel DB (estratto da _update_match_events_sheet)"""
        if " v " not in bf_e["name"]:
            return None

        bf_home, bf_away = bf_e["name"].split(" v ", 1)

        # Filtro temporale (+/- 60 min); salta il filtro se dt_utc non disponibile
        if dt_utc is not None:
            candidates = []
            for f in db_fixtures:
                fd = f.get("fixture_date")
                if not fd:
                    continue
                try:
                    fdt = datetime.fromisoformat(fd.replace('Z', '+00:00'))
                    if abs((fdt - dt_utc).total_seconds()) < 3600:
                        candidates.append(f)
                except (ValueError, AttributeError):
                    continue
        else:
            candidates = list(db_fixtures)
        
        bf_home_clean = self.name_map.get(bf_home, bf_home)
        bf_away_clean = self.name_map.get(bf_away, bf_away)
        n_bf_home = self.normalize_name(bf_home_clean)
        n_bf_away = self.normalize_name(bf_away_clean)

        best_score = 0
        best_candidate = None
        
        for f in candidates:
            db_home = f.get("home_team_name") or ""
            db_away = f.get("away_team_name") or ""
            if not db_home or not db_away:
                continue
            n_db_home = self.normalize_name(db_home)
            n_db_away = self.normalize_name(db_away)

            # Check direct
            shd = fuzz.token_set_ratio(n_bf_home, n_db_home)
            sad = fuzz.token_set_ratio(n_bf_away, n_db_away)
            avg_d = (shd + sad) / 2

            # Check inverted
            shi = fuzz.token_set_ratio(n_bf_home, n_db_away)
            sai = fuzz.token_set_ratio(n_bf_away, n_db_home)
            avg_i = (shi + sai) / 2

            best_curr = max(avg_d, avg_i)
            if best_curr > best_score:
                best_score = best_curr
                best_candidate = f

            if (shd >= MATCH_THRESHOLD and sad >= MATCH_THRESHOLD) or \
               (shi >= MATCH_THRESHOLD and sai >= MATCH_THRESHOLD):
                return f
        
        if best_candidate and best_score >= 65:
            return best_candidate
            
        return None

    def _get_or_create_worksheet(self, title):
        try:
            return self.sh.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            return self.sh.add_worksheet(title=title, rows=100, cols=20)

    def _update_betfair_sheet(self, events, market_map):
        try:
            ws = self.sh.worksheet(config.WORKSHEET_NAME)
            header = ["Event ID", "Nome Evento", "Data Evento", "Paese", "Link Mercato"]
            rows = []
            for e in events:
                m_id = market_map.get(e["id"])
                link = f"https://www.betfair.it/exchange/plus/football/market/{m_id}" if m_id else ""
                # Formattazione data per leggibilità
                dt = datetime.strptime(e["open_date"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.UTC)
                dt_ita = dt.astimezone(pytz.timezone("Europe/Rome")).strftime("%Y-%m-%d %H:%M")
                
                rows.append([e["id"], e["name"], dt_ita, e["country"] or "", link])

            _sheets_retry(ws.clear)
            _sheets_retry(ws.append_row, header, value_input_option="RAW")
            # Formattazione: Grassetto intestazione + Allineamento centrato
            _sheets_retry(ws.format, "1:1", {"textFormat": {"bold": True}})
            _sheets_retry(ws.format, "A:E", {"horizontalAlignment": "CENTER"})
            
            if rows:
                # Forza le stringhe che iniziano con = ad essere trattate come testo
                rows = [[(f"'{val}" if isinstance(val, str) and val.startswith("=") else val) for val in row] for row in rows]
                _sheets_retry(ws.append_rows, rows, value_input_option="RAW")
            logger.info(f"Aggiornato foglio '{config.WORKSHEET_NAME}' con {len(rows)} righe.")
        except Exception as err:
            logger.error(f"Errore aggiornamento foglio Betfair: {err}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Betfair Report Manager")
    parser.add_argument(
        "--skip-training",
        action="store_true",
        help=(
            "Salta il pre-flight training. Usa solo i modelli già in cache locale. "
            "Le leghe senza modelli avranno predizioni AI assenti ma il report gira subito."
        ),
    )
    args = parser.parse_args()
    manager = BetfairReportManager()
    manager.run_daily_report(skip_training=args.skip_training)
