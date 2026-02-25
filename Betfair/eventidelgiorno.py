import sys
import os
import requests
import json
from datetime import datetime, timedelta
import logging
from logging.handlers import RotatingFileHandler
import pytz
import time
import gspread

# Aggiungi la root del progetto al path per importare config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Configurazione del logging
handler = RotatingFileHandler("betfair_bot.log", maxBytes=5000000, backupCount=5)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[handler, logging.StreamHandler()]
)

# Parametri Betfair
app_key = config.BETFAIR_APP_KEY
username = config.BETFAIR_USERNAME
password = config.BETFAIR_PASSWORD
cert_file = config.BETFAIR_CERT_FILE
key_file = config.BETFAIR_KEY_FILE

# Parametri Google Sheets
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE")

# Classe di autenticazione Betfair
class BetfairAuth:
    def __init__(self, app_key, username, password, cert_file, key_file):
        self.app_key = app_key
        self.username = username
        self.password = password
        self.cert_file = cert_file
        self.key_file = key_file
        self.session_token = None
        self.last_login_time = None

    def login(self):
        url = 'https://identitysso-cert.betfair.it/api/certlogin'
        data = f'username={self.username}&password={self.password}'
        headers = {
            'X-Application': self.app_key,
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        logging.info("Tentativo di login a Betfair...")
        for attempt in range(3):
            try:
                response = requests.post(url, data=data, cert=(self.cert_file, self.key_file), headers=headers)
                if response.status_code == 200:
                    response_data = response.json()
                    if response_data['loginStatus'] == 'SUCCESS':
                        self.session_token = response_data['sessionToken']
                        self.last_login_time = datetime.now(pytz.utc)
                        logging.info("Login effettuato con successo")
                        return self.session_token
                    else:
                        raise Exception(f"Login fallito: {response_data['loginStatus']}")
                else:
                    raise Exception(f"Errore nella richiesta di login: {response.status_code}")
            except Exception as e:
                logging.error(f"Errore di login: {e}, tentativo {attempt + 1} di 3")
                time.sleep(5)
        raise Exception("Impossibile effettuare il login dopo 3 tentativi.")

    def get_session_token(self):
        if not self.session_token or not self.last_login_time or (datetime.now(pytz.utc) - self.last_login_time) > timedelta(minutes=30):
            self.login()
        return self.session_token

# Oggetto di autenticazione Betfair
betfair_auth = BetfairAuth(app_key, username, password, cert_file, key_file)

def get_headers():
    return {
        'X-Application': app_key,
        'X-Authentication': betfair_auth.get_session_token(),
        'Content-Type': 'application/json'
    }

def recupera_eventi_giornata():
    url = 'https://api.betfair.com/exchange/betting/rest/v1.0/listEvents/'
    headers = get_headers()
    now_utc = datetime.now(pytz.utc)
    params = {
        "filter": {
            "eventTypeIds": ["1"],
            "marketStartTime": {
                "from": now_utc.isoformat(),
                "to": (now_utc + timedelta(days=1)).isoformat()
            }
        }
    }
    try:
        response = requests.post(url, headers=headers, json=params)
        return response.json() if response.status_code == 200 else []
    except Exception as e:
        logging.error(f"Errore recuperando eventi: {e}")
        return []

def get_match_odds_market_id(event_id):
    url = 'https://api.betfair.com/exchange/betting/rest/v1.0/listMarketCatalogue/'
    headers = get_headers()
    params = {
        "filter": {
            "eventIds": [event_id],
            "marketTypeCodes": ["MATCH_ODDS"]
        },
        "maxResults": 1
    }
    try:
        response = requests.post(url, headers=headers, json=params)
        if response.status_code == 200:
            data = response.json()
            return data[0]['marketId'] if data else None
    except Exception as e:
        logging.error(f"Errore recuperando marketId: {e}")
    return None

def prepara_dati_per_google_sheets(eventi):
    righe = []
    for evento in eventi:
        event_data = evento.get("event", {})
        event_id = event_data.get('id', 'N/D')
        nome_evento = event_data.get('name', 'N/D')
        data_evento = event_data.get('openDate', 'N/D')
        paese_evento = event_data.get('countryCode', 'N/D')

        market_id = get_match_odds_market_id(event_id)
        market_link = f"https://www.betfair.it/exchange/plus/football/market/{market_id}" if market_id else "N/D"

        righe.append([event_id, nome_evento, data_evento, paese_evento, market_link])

        logging.info(f"Evento: {event_id}, Nome: {nome_evento}, Market ID: {market_id}, Link: {market_link}")

    return righe

def aggiorna_google_sheet(dati):
    try:
        gc = gspread.service_account(filename=GOOGLE_CREDENTIALS_FILE)
        sh = gc.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(WORKSHEET_NAME)

        header = ['Event ID', 'Nome Evento', 'Data Evento', 'Paese', 'Link Mercato']
        ws.clear()
        ws.append_row(header, value_input_option="USER_ENTERED")

        for batch in range(0, len(dati), 100):
            ws.append_rows(dati[batch:batch+100], value_input_option="USER_ENTERED")
            logging.info(f"Aggiunto batch {batch // 100 + 1}")

        logging.info("Dati aggiornati su Google Sheet.")
    except Exception as e:
        logging.error(f"Errore aggiornando Google Sheet: {e}")

def main():
    logging.info("Avvio script Betfair")
    eventi = recupera_eventi_giornata()
    if eventi:
        dati = prepara_dati_per_google_sheets(eventi)
        aggiorna_google_sheet(dati)
    else:
        logging.error("Nessun evento recuperato.")

if __name__ == "__main__":
    main()