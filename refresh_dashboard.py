"""Aggiorna SOLO il foglio 'Report Ven Dom' con i dati correnti senza rieseguire il pipeline."""
import sys, os
root = r"c:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
sys.path.insert(0, root)

import config
import gspread
from Betfair.money_management import SlotManager

gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_FILE)
sh = gc.open_by_key(config.SPREADSHEET_ID)

sm = SlotManager(gc, sh)
print("Aggiornamento dashboard Report Ven Dom...")
sm.update_report_sheet()
print("Dashboard aggiornata!")
