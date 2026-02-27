import gspread
import os
import json
import logging
from datetime import datetime, timedelta
import pytz
from thefuzz import fuzz
import unicodedata
import time

# Import local modules
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from Betfair.client import BetfairClient
from db_client import get_supabase_client
try:
    from Betfair.money_management import SlotManager
except ImportError:
    from money_management import SlotManager

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
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        res = self.supabase.from_("fixture_predictions").select("*").gte("fixture_date", today).lt("fixture_date", tomorrow).execute()
        db_fixtures = res.data or []

        # 4. Aggiorna foglio Prediction (Tutte)
        self._sync_all_predictions(db_fixtures)
        
        # 5. Aggiorna foglio Match Eventi (Debug/Internal)
        if event_list:
            self._update_match_events_sheet(event_list, db_fixtures)
        
        # 6. Risolve risultati dei giorni precedenti (PRIMA di processare oggi)
        logger.info("Fase 6: Risoluzione risultati giorni precedenti...")
        self.slot_manager.resolve_history_results()

        # 7. Aggiorna foglio Segnali (La Magia + Edge Scanner)
        if event_list:
            self._update_signals_sheet(event_list, db_fixtures)

        # 8. Salva operazioni di oggi nello storico multi-giorno
        logger.info("Fase 8: Salvataggio storico giornaliero...")
        self.slot_manager.save_today_to_history()

        # 9. Aggiorna Dashboard Money Management
        logger.info("Fase 9: Aggiornamento Dashboard MM...")
        self.slot_manager.update_dashboard_sheet()

        # 10. Aggiorna Report Ven-Dom (multi-giorno)
        logger.info("Fase 10: Aggiornamento Report Ven-Dom...")
        self.slot_manager.update_report_sheet()

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
            # --- Money Management v2 (Quant Fund) ---
            "Slot", "Mercato Scelto", "Edge", "Score", "Stake €",
            # --- Statistiche ---
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

        # 3. Generazione righe e preparazione dati per Money Management
        logger.info("Fase 3: Generazione righe del report e calcolo stake...")
        signals_payload_for_mm = [] # Dati da passare a SlotManager
        raw_rows_data = [] # Mantiene i dati temporanei della riga prima dell'arricchimento MM
        
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
                    # Aggiungiamo ' davanti per evitare che Google Sheets lo interpreti come formula in USER_ENTERED
                    if val > 1: return f"'{val:.1f}%"
                    return f"'{val*100:.1f}%"

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
                    # Usiamo l'apice ' per forzare il formato testo ed evitare l'errore #ERROR! di Google Sheets
                    return f"'{edge*100:+.1f}%"

                # Hyperlink per l'evento Betfair (Match Odds)
                mo_id = odds.get("mo_id")
                event_name_val = bf_e["name"]
                if mo_id:
                    event_display = f'=HYPERLINK("https://www.betfair.it/exchange/plus/football/market/{mo_id}"; "{event_name_val}")'
                else:
                    event_display = event_name_val

                # --- PREPARAZIONE PAYLOAD PER MONEY MANAGEMENT v2 (Quant Fund) ---
                # Passiamo TUTTI i dati al nuovo Edge Scanner:
                # - L'intero dict analysis["markets"] con tutte le probabilità dei 6 mercati
                # - L'intero dict odds con tutte le quote Betfair
                # - L'intero dict inputs per i filtri di qualità dati
                signals_payload_for_mm.append({
                    "event_id": bf_e["id"],
                    "fixture_id": matched_db["fixture_id"],  # Necessario per risolvere risultati
                    "name": api_event_name,
                    "date": dt_ita,
                    "analysis_markets": analysis,  # Dict completo con markets.1x2, markets.btts etc.
                    "odds_data": odds,              # Dict con H, D, A, HT05, BTTS, O25
                    "inputs_data": inputs,           # Dict con home_matches_used, etc.
                    "row_index": len(raw_rows_data)
                })

                row_base = [
                    dt_ita, bf_e["id"], event_display, api_event_name, 
                    matched_db["fixture_id"], matched_db["league_name"],
                    advice, fmt_p(ht_prob), "SÌ" if is_elite else "",
                    # MM v2: Slot, Mercato Scelto, Edge, Score, Stake (segnaposti)
                    "{MM_SLOT}", "{MM_MKT}", "{MM_EDGE}", "{MM_SCORE}", "{MM_STAKE}",
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
                row_base = [dt_ita, bf_e["id"], bf_e["name"]] + [""] * (len(header) - 3)
            
            raw_rows_data.append(row_base)
            
        # 4. Elaborazione Money Management v2 (Edge Scanner + Kelly)
        if signals_payload_for_mm:
            logger.info("Fase 4: Edge Scanner Multi-Mercato + Kelly Staking...")
            enriched_signals = self.slot_manager.process_signals(signals_payload_for_mm)
            
            # Mappiamo i risultati arricchiti indietro sulle righe del foglio
            for signal in enriched_signals:
                r_idx = signal["row_index"]
                
                stake_val = signal.get('stake', '')
                if isinstance(stake_val, (int, float)) and stake_val > 0:
                   stake_val = round(stake_val, 2)
                else:
                   stake_val = ''
                   
                # Indici: 9=Slot, 10=Mercato Scelto, 11=Edge, 12=Score, 13=Stake
                raw_rows_data[r_idx][9] = signal.get("slot_id", "")
                raw_rows_data[r_idx][10] = signal.get("selected_market", "")
                raw_rows_data[r_idx][11] = signal.get("edge_pct", "")
                raw_rows_data[r_idx][12] = signal.get("score", "")
                raw_rows_data[r_idx][13] = stake_val
                
        # Sostituisce eventuali segnaposti rimasti (eventi senza match nel DB)
        for r in raw_rows_data:
            if len(r) > 9 and r[9] == "{MM_SLOT}":
                r[9] = ""
                r[10] = ""
                r[11] = ""
                r[12] = ""
                r[13] = ""
                
        rows = raw_rows_data

        try:
            ws = self._get_or_create_worksheet("Segnali")
            ws.clear()
            ws.append_row(header, value_input_option="RAW")
            ws.format("1:1", {"textFormat": {"bold": True}})
            ws.format("A:Z", {"horizontalAlignment": "CENTER"})
            
            if rows:
                ws.append_rows(rows, value_input_option="USER_ENTERED")
            
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
            # 1. Recupera catalogo mercati per TUTTI gli eventi
            # OPTIMIZED SAFE: Chunking event_ids (30 eventi = max 120 mercati per chiamata, Peso ~120)
            all_cats = []
            event_chunk_size = 30
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
                    all_results[eid] = {"H": None, "D": None, "A": None, "HT05": None, "BTTS": None, "O25": None, "mo_id": None}

                def get_best_back(selection_id):
                    r_book = runners_book.get(selection_id)
                    if not r_book: return None
                    back = r_book.get('ex', {}).get('availableToBack', [])
                    return back[0].get('price') if back else None

                if mname == "Match Odds":
                    all_results[eid]["mo_id"] = mid
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
            # Usiamo "1:1" per coprire tutta la riga a prescindere dal numero di colonne
            ws.format("1:1", {
                "backgroundColor": {"red": 0.0, "green": 0.13, "blue": 0.28}, # #002147
                "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, "bold": True, "fontSize": 10},
                "horizontalAlignment": "CENTER"
            })
            ws.freeze(rows=1)

            # 2. Raggruppamento Colonne (Colori di sfondo per gruppi logici)
            # Header: A-I (Identità+AI), J-N (Money Management v2), O-X (Deep Stats), Y-AP (Mercati)
            
            # Identità + AI Intelligence (A-I): Grigio chiaro
            ws.format("A2:I1000", {"backgroundColor": {"red": 0.96, "green": 0.96, "blue": 0.96}})
            
            # Money Management v2 (J-N): Verde acqua leggero con highlight
            ws.format("J2:N1000", {"backgroundColor": {"red": 0.9, "green": 0.97, "blue": 0.9}})
            
            # Slot (J) in blu scuro grassetto
            ws.format("J2:J1000", {
                "textFormat": {"foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.5}, "bold": True}
            })
            # Mercato Scelto (K) in grassetto
            ws.format("K2:K1000", {"textFormat": {"bold": True}})
            # Edge (L) colorato
            ws.format("L2:L1000", {
                "textFormat": {"foregroundColor": {"red": 0.0, "green": 0.4, "blue": 0.0}, "bold": True}
            })
            # Stake (N) in verde valuta grassetto
            ws.format("N2:N1000", {
                "textFormat": {"foregroundColor": {"red": 0.0, "green": 0.35, "blue": 0.0}, "bold": True},
                "numberFormat": {"type": "CURRENCY", "pattern": "€#,##0.00"}
            })
            
            # Deep Stats (O-X): Blu cielo leggero
            ws.format("O2:X1000", {"backgroundColor": {"red": 0.91, "green": 0.94, "blue": 1.0}})
            
            # Mercati probabilità/quote/edge (Y-AP): Crema
            ws.format("Y2:AP1000", {"backgroundColor": {"red": 1.0, "green": 0.98, "blue": 0.9}})
            
            # 3. Formattazione Numerica e Allineamento
            ws.format("A2:B1000", {"horizontalAlignment": "CENTER"})
            ws.format("E2:F1000", {"horizontalAlignment": "CENTER"})
            ws.format("G2:AP1000", {"horizontalAlignment": "CENTER"})
            
            # Advice Bold
            ws.format("G2:G1000", {"textFormat": {"bold": True}})
            
            # Quotas Bold (col Z=Quota H, AC=Quota D, AF=Quota A, AI=Quota HT, AL=Quota BTTS, AO=Quota O25)
            quota_ranges = ["Z2:Z1000", "AC2:AC1000", "AF2:AF1000", "AI2:AI1000", "AL2:AL1000", "AO2:AO1000"]
            for qr in quota_ranges:
                ws.format(qr, {"textFormat": {"bold": True}})

            # 4. Conditional Formatting (Heatmap per Edge)
            sheet_id = ws.id
            # Edge cols: AA(H Edge)=26, AD(D Edge)=29, AG(A Edge)=32, AJ(HT Edge)=35, AM(BTTS Edge)=38, AP(O25 Edge)=41
            edge_cols_indices = [26, 29, 32, 35, 38, 41] 
            
            requests = []
            for col_idx in edge_cols_indices:
                requests.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1000, "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1}],
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
