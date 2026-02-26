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
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        res = self.supabase.from_("fixture_predictions").select("*").gte("fixture_date", today).lt("fixture_date", tomorrow).execute()
        db_fixtures = res.data or []

        # 4. Aggiorna foglio Prediction (Tutte)
        self._sync_all_predictions(db_fixtures)
        
        # 5. Aggiorna foglio Match Eventi (Debug/Internal)
        if event_list:
            self._update_match_events_sheet(event_list, db_fixtures)
        
        # 6. Aggiorna foglio Segnali (La Magia)
        if event_list:
            self._update_signals_sheet(event_list, db_fixtures)

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
        # ... [metodo esistente invariato, usato per debug interno] ...
        logger.info("Generazione foglio Match Eventi...")
        # ... logic ...
        pass # Mantengo il corpo esistente ma aggiungo il nuovo metodo sotto

    def _update_signals_sheet(self, bf_events, db_fixtures):
        logger.info("Generazione foglio 'Segnali' (Market Map)...")
        header = [
            "Data Evento", "Event ID", "Nome Evento (Betfair)", 
            "Nome Evento (API-Football)", "Fixture ID", "League Name",
            "Advice", "HT %", "Elite?",
            "N. Dati Casa", "N. Dati Trasf", 
            "xG C", "xG T",
            "Avg Gol Lega", "Avg Gol Casa", "Avg Gol Trasf",
            "Lmb Casa", "Lmb Trasf", "Lmb 1H",
            "H %", "Quota H", "Edge H", 
            "D %", "Quota D", "Edge D", 
            "A %", "Quota A", "Edge A",
            "1H Over 0.5 %", "Quota 1H", "Edge 1H", 
            "BTTS %", "Quota BTTS", "Edge BTTS", 
            "O2.5 %", "Quota O2.5", "Edge O2.5"
        ]
        
        # 1. Ordina eventi Betfair cronologicamente
        bf_events_sorted = sorted(bf_events, key=lambda x: x.get("open_date", ""))
        
        rows = []
        match_count = 0
        
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

        # 3. Generazione righe
        logger.info("Fase 3: Generazione righe del report...")
        for bf_e in bf_events_sorted:
            # Dati Betfair
            dt = datetime.strptime(bf_e["open_date"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.UTC)
            dt_ita = dt.astimezone(pytz.timezone("Europe/Rome")).strftime("%Y-%m-%d %H:%M")
            
            # Recupera match pre-identificato
            match_data = bf_e_map.get(bf_e["id"])
            
            if match_data:
                bf_e, matched_db = match_data
                match_count += 1
                api_event_name = f"{matched_db['home_team_name']} v {matched_db['away_team_name']}"
                
                # Estrazione Statistiche dal DB
                advice = matched_db.get("advice", "")
                
                # Probabilità da db_json_analisi o dai campi flat
                analysis = matched_db.get("db_json_analisi") or {}
                markets = analysis.get("markets", {})
                inputs = analysis.get("inputs", {})
                
                ht_prob = markets.get("first_half_over_0_5", {}).get("True")
                if ht_prob is None: # Fallback a ht_predictions
                    ht_pred = matched_db.get("ht_predictions") or {}
                    ht_prob = ht_pred.get("hybrid_prob")
                
                btts_prob = markets.get("btts", {}).get("True")
                o25_prob = markets.get("over_2_5", {}).get("True")
                
                # 1X2 probabilities
                h_p = markets.get("1x2", {}).get("H") or matched_db.get("percent_home")
                d_p = markets.get("1x2", {}).get("D") or matched_db.get("percent_draw")
                a_p = markets.get("1x2", {}).get("A") or matched_db.get("percent_away")
                
                is_elite = (matched_db.get("ht_predictions") or {}).get("is_elite", False)
                
                # --- Integrazione Quote Betfair ---
                # Recupera le quote dalla cache pre-caricata
                odds = odds_cache.get(bf_e["id"], {})

                def fmt_p(val):
                    if val is None: return ""
                    if val > 1: return f"{val:.1f}%"
                    return f"{val*100:.1f}%"

                def fmt_v(val, decimals=2):
                    if val is None: return ""
                    return round(val, decimals)
                
                def fmt_q(val):
                    if val is None: return ""
                    return val

                def calc_edge(prob, quota):
                    if prob is None or quota is None: return None
                    # Se prob è 65% (0.65) e quota è 2.0 -> (0.65 * 2.0) - 1 = 0.30 (+30%)
                    # In caso il DB abbia prob > 1 (es. 65), lo normalizziamo
                    p = prob / 100.0 if prob > 1 else prob
                    edge = (p * quota) - 1
                    return edge

                def fmt_edge(edge):
                    if edge is None: return ""
                    return f"{edge*100:+.1f}%"

                row = [
                    dt_ita, bf_e["id"], bf_e["name"], api_event_name, 
                    matched_db["fixture_id"], matched_db["league_name"],
                    advice, fmt_p(ht_prob), "SÌ" if is_elite else "",
                    # Deep Stats
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
                    # Probabilities & Odds & Edges
                    fmt_p(h_p), fmt_q(odds.get("H")), fmt_edge(calc_edge(h_p, odds.get("H"))),
                    fmt_p(d_p), fmt_q(odds.get("D")), fmt_edge(calc_edge(d_p, odds.get("D"))),
                    fmt_p(a_p), fmt_q(odds.get("A")), fmt_edge(calc_edge(a_p, odds.get("A"))),
                    fmt_p(ht_prob), fmt_q(odds.get("HT05")), fmt_edge(calc_edge(ht_prob, odds.get("HT05"))),
                    fmt_p(btts_prob), fmt_q(odds.get("BTTS")), fmt_edge(calc_edge(btts_prob, odds.get("BTTS"))),
                    fmt_p(o25_prob), fmt_q(odds.get("O25")), fmt_edge(calc_edge(o25_prob, odds.get("O25")))
                ]
            else:
                row = [dt_ita, bf_e["id"], bf_e["name"]] + [""] * (len(header) - 3)
            
            rows.append(row)

        try:
            ws = self._get_or_create_worksheet("Segnali")
            ws.clear()
            ws.append_row(header, value_input_option="RAW")
            ws.format("1:1", {"textFormat": {"bold": True}})
            ws.format("A:Z", {"horizontalAlignment": "CENTER"})
            
            if rows:
                ws.append_rows(rows, value_input_option="RAW")
            
            # Masterpiece Formatting
            self._format_signals_sheet(ws, len(header))
            
            logger.info(f"Aggiornato foglio 'Segnali': {match_count}/{len(bf_events)} match accoppiati con statistiche.")
        except Exception as err:
            logger.error(f"Errore aggiornamento foglio Segnali: {err}")

    def _prefetch_odds_for_events(self, event_ids):
        """
        Recupera le quote per una lista di eventi in modalità batch (massima efficienza).
        """
        all_results = {} # event_id -> {H, D, A, HT05, BTTS, O25}
        market_types = ['MATCH_ODDS', 'BOTH_TEAMS_TO_SCORE', 'OVER_UNDER_25', 'FIRST_HALF_GOALS_05']
        
        try:
            # 1. Recupera catalogo mercati per TUTTI gli eventi in un colpo solo
            logger.debug(f"Richiesta catalogo per {len(event_ids)} eventi...")
            cats = self.bf.list_market_catalogue(
                event_ids=event_ids,
                market_types=market_types,
                max_results=250 # Betfair limite max
            )
            
            if not cats:
                return all_results

            # Mappatura market_id -> metadata
            market_map = {} # market_id -> {event_id, market_name, runners_cat}
            market_ids = []
            
            for c in cats:
                mid = c['marketId']
                market_ids.append(mid)
                market_map[mid] = {
                    "event_id": c['event']['id'],
                    "market_name": c['marketName'],
                    "runners_cat": c.get('runners', [])
                }

            # 2. Recupera quote in batch (limite Betfair di solito 40 market per chiamata)
            # Suddividiamo market_ids in chunk da 40
            chunk_size = 40
            all_books = []
            for i in range(0, len(market_ids), chunk_size):
                chunk = market_ids[i:i + chunk_size]
                logger.debug(f"Fetching market book batch {i//chunk_size + 1} ({len(chunk)} mercati)...")
                books = self.bf.list_market_book(market_ids=chunk)
                if books:
                    all_books.extend(books)

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
                    all_results[eid] = {"H": None, "D": None, "A": None, "HT05": None, "BTTS": None, "O25": None}

                def get_best_back(selection_id):
                    r_book = runners_book.get(selection_id)
                    if not r_book: return None
                    back = r_book.get('ex', {}).get('availableToBack', [])
                    return back[0].get('price') if back else None

                if mname == "Match Odds":
                    if len(runners_cat) >= 3:
                        all_results[eid]["H"] = get_best_back(runners_cat[0]['selectionId'])
                        all_results[eid]["A"] = get_best_back(runners_cat[1]['selectionId'])
                        all_results[eid]["D"] = get_best_back(runners_cat[2]['selectionId'])
                elif mname == "Both teams to Score?":
                    if len(runners_cat) >= 1:
                        all_results[eid]["BTTS"] = get_best_back(runners_cat[0]['selectionId'])
                elif mname == "Over/Under 2.5 Goals":
                    if len(runners_cat) >= 2:
                        all_results[eid]["O25"] = get_best_back(runners_cat[1]['selectionId'])
                elif mname == "First Half Goals 0.5":
                    if len(runners_cat) >= 2:
                        all_results[eid]["HT05"] = get_best_back(runners_cat[1]['selectionId'])

        except Exception as e:
            logger.error(f"Errore critico nel prefetch delle quote: {e}")
            
        return all_results

    def _format_signals_sheet(self, ws, num_cols):
        """
        Applica una formattazione professionale "Masterpiece" al foglio Segnali.
        """
        try:
            # 1. Header (Dark Blue, White, Bold, Frozen)
            header_range = "A1:AF1"
            ws.format(header_range, {
                "backgroundColor": {"red": 0.0, "green": 0.13, "blue": 0.28}, # #002147
                "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, "bold": True, "fontSize": 10},
                "horizontalAlignment": "CENTER"
            })
            ws.freeze(rows=1)

            # 2. Raggruppamento Colonne (Colori di sfondo per gruppi logici)
            # Identità (A-F): Grigio chiaro professionale
            ws.format("A2:F200", {"backgroundColor": {"red": 0.96, "green": 0.96, "blue": 0.96}})
            
            # AI Intelligence (G-I): Verde acqua leggero
            ws.format("G2:I200", {"backgroundColor": {"red": 0.92, "green": 0.97, "blue": 0.94}})
            
            # Statistiche Profonde (J-S): Blu cielo leggero
            ws.format("J2:S200", {"backgroundColor": {"red": 0.91, "green": 0.94, "blue": 1.0}})
            
            # Mercati (T-AK): Alternanza per leggibilità
            # Match Odds (T-AB): Giallino
            ws.format("T2:AB200", {"backgroundColor": {"red": 1.0, "green": 0.98, "blue": 0.9}})
            
            # 3. Formattazione Numerica e Allineamento
            ws.format("A2:B200", {"horizontalAlignment": "CENTER"})
            ws.format("E2:F200", {"horizontalAlignment": "CENTER"})
            ws.format("G2:AK200", {"horizontalAlignment": "CENTER"})
            
            # Advice Bold
            ws.format("G2:G200", {"textFormat": {"bold": True}})
            
            # Quotas Bold
            quota_ranges = ["U2:U200", "X2:X200", "AA2:AA200", "AD2:AD200", "AG2:AG200", "AJ2:AJ200"]
            for qr in quota_ranges:
                ws.format(qr, {"textFormat": {"bold": True}})

            # 4. Conditional Formatting (Heatmap per Edge)
            sheet_id = ws.id
            edge_cols_indices = [21, 24, 27, 30, 33, 36] # V, Y, AB, AE, AH, AK (0-indexed)
            
            requests = []
            for col_idx in edge_cols_indices:
                requests.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 200, "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1}],
                            "booleanRule": {
                                "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "+"}]},
                                "format": {"backgroundColor": {"red": 0.8, "green": 1.0, "blue": 0.8}, "textFormat": {"bold": True}}
                            }
                        },
                        "index": 0
                    }
                })
            
            if requests:
                self.sh.batch_update({"requests": requests})

            # 5. Dimensionamento automatico
            ws.columns_auto_resize(0, num_cols - 1)
            
            logger.info("Formattazione 'Masterpiece' applicata con successo.")
        except Exception as e:
            logger.warning(f"Errore durante la formattazione grafica: {e}")

    def _fetch_odds_for_event(self, event_id):
        # [Manteniamo per ora per retrocompatibilità o debug, ma useremo _prefetch_odds_for_events]
        pass

    def _find_match(self, bf_e, db_fixtures, dt_utc):
        """Helper per trovare il match nel DB (estratto da _update_match_events_sheet)"""
        if " v " not in bf_e["name"]:
            return None
            
        bf_home, bf_away = bf_e["name"].split(" v ", 1)
        
        # Filtro temporale (+/- 60 min)
        candidates = [
            f for f in db_fixtures 
            if abs((datetime.fromisoformat(f["fixture_date"].replace('Z', '+00:00')) - dt_utc).total_seconds()) < 3600
        ]
        
        bf_home_clean = self.name_map.get(bf_home, bf_home)
        bf_away_clean = self.name_map.get(bf_away, bf_away)
        n_bf_home = self.normalize_name(bf_home_clean)
        n_bf_away = self.normalize_name(bf_away_clean)

        best_score = 0
        best_candidate = None
        
        for f in candidates:
            db_home = f["home_team_name"]
            db_away = f["away_team_name"]
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
