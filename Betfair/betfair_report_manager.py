import gspread
import os
import json
import logging
from datetime import datetime, timedelta
import pytz
from thefuzz import fuzz
import unicodedata

# Import local modules
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from Betfair.client import BetfairClient
from db_client import get_supabase_client

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

    def run_daily_report(self):
        logger.info("Avvio report giornaliero completo...")
        
        # 1. Login Betfair
        self.bf.login_cert()
        
        # 2. Recupera eventi Betfair
        events = self.bf.list_events(event_type_ids=["1"])
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
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        res = self.supabase.from_("fixture_predictions").select("*").gte("fixture_date", today).lt("fixture_date", tomorrow).execute()
        db_fixtures = res.data or []

        # 4. Aggiorna foglio Prediction (Tutte)
        self._sync_all_predictions(db_fixtures)
        
        # 5. Aggiorna foglio Match Eventi (Matching side-by-side)
        if event_list:
            self._update_match_events_sheet(event_list, db_fixtures)
        
        logger.info("Job completato con successo.")

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
            ws.clear()
            ws.append_row(headers, value_input_option="RAW")
            # Formattazione: Grassetto intestazione + Allineamento centrato
            ws.format("1:1", {"textFormat": {"bold": True}})
            ws.format("A:Z", {"horizontalAlignment": "CENTER"})
            
            if rows:
                rows = [[(f"'{val}" if isinstance(val, str) and val.startswith("=") else val) for val in row] for row in rows]
                ws.append_rows(rows, value_input_option="RAW")
            logger.info(f"Aggiornato foglio 'Prediction' con {len(rows)} analisi.")
        except Exception as err:
            logger.error(f"Errore aggiornamento foglio Prediction: {err}")

    def _update_match_events_sheet(self, bf_events, db_fixtures):
        logger.info("Generazione foglio Match Eventi...")
        header = [
            "Event ID", "Nome Evento", "Data Evento", "Paese",
            "fixture_id", "league_id", "league_name", "home_team_name", "away_team_name"
        ]
        
        rows = []
        match_count = 0
        for bf_e in bf_events:
            # Dati Betfair
            dt = datetime.strptime(bf_e["open_date"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.UTC)
            dt_ita = dt.astimezone(pytz.timezone("Europe/Rome")).strftime("%Y-%m-%d %H:%M")
            
            bf_row_base = [bf_e["id"], bf_e["name"], dt_ita, bf_e["country"]]
            
            # Matching logic
            matched_db = None
            if " v " in bf_e["name"]:
                bf_home, bf_away = bf_e["name"].split(" v ", 1)
                
                # Filtro temporale (+/- 60 min)
                candidates = [
                    f for f in db_fixtures 
                    if abs((datetime.fromisoformat(f["fixture_date"].replace('Z', '+00:00')) - dt).total_seconds()) < 3600
                ]
                
                best_score = 0
                best_candidate_name = ""
                
                for f in candidates:
                    db_home = f["home_team_name"]
                    db_away = f["away_team_name"]
                    
                    # Fuzzy matching sui nomi normalizzati - token_set_ratio è più robusto per "Team" vs "Team City"
                    n_bf_home = self.normalize_name(self.name_map.get(bf_home, bf_home))
                    n_bf_away = self.normalize_name(self.name_map.get(bf_away, bf_away))
                    n_db_home = self.normalize_name(db_home)
                    n_db_away = self.normalize_name(db_away)

                    score_home = fuzz.token_set_ratio(n_bf_home, n_db_home)
                    score_away = fuzz.token_set_ratio(n_bf_away, n_db_away)
                    avg_score = (score_home + score_away) / 2
                    
                    if avg_score > best_score:
                        best_score = avg_score
                        best_candidate_name = f"{db_home} v {db_away}"

                    # Entrambe devono essere ragionevolmente alte
                    if score_home >= MATCH_THRESHOLD and score_away >= MATCH_THRESHOLD:
                        matched_db = f
                        break
                
                if not matched_db and best_score > 50:
                    logger.debug(f"[DEBUG] No match for '{bf_e['name']}'. Best: '{best_candidate_name}' ({best_score:.1f}%)")
            
            if matched_db:
                match_count += 1
                db_row = [
                    matched_db["fixture_id"],
                    matched_db["league_id"],
                    matched_db["league_name"],
                    matched_db["home_team_name"],
                    matched_db["away_team_name"]
                ]
            else:
                db_row = ["", "", "", "", ""]
            
            rows.append(bf_row_base + db_row)

        try:
            ws = self.sh.worksheet("Match Eventi")
            ws.clear()
            ws.append_row(header, value_input_option="RAW")
            # Formattazione: Grassetto intestazione + Allineamento centrato
            ws.format("1:1", {"textFormat": {"bold": True}})
            ws.format("A:I", {"horizontalAlignment": "CENTER"})
            
            if rows:
                ws.append_rows(rows, value_input_option="RAW")
            logger.info(f"Aggiornato foglio 'Match Eventi': {match_count}/{len(bf_events)} match accoppiati.")
        except Exception as err:
            logger.error(f"Errore aggiornamento foglio Match Eventi: {err}")

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

            ws.clear()
            ws.append_row(header, value_input_option="RAW")
            # Formattazione: Grassetto intestazione + Allineamento centrato
            ws.format("1:1", {"textFormat": {"bold": True}})
            ws.format("A:E", {"horizontalAlignment": "CENTER"})
            
            if rows:
                # Forza le stringhe che iniziano con = ad essere trattate come testo
                rows = [[(f"'{val}" if isinstance(val, str) and val.startswith("=") else val) for val in row] for row in rows]
                ws.append_rows(rows, value_input_option="RAW")
            logger.info(f"Aggiornato foglio '{config.WORKSHEET_NAME}' con {len(rows)} righe.")
        except Exception as err:
            logger.error(f"Errore aggiornamento foglio Betfair: {err}")

if __name__ == "__main__":
    manager = BetfairReportManager()
    manager.run_daily_report()
