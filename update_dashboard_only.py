"""
Script temporaneo: aggiorna SOLO la dashboard Report Ven Dom
senza rieseguire il report intero.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gspread
import config
from Betfair.money_management import SlotManager

# Apri foglio con credenziali corrette
gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_FILE)
sh = gc.open_by_key(config.SPREADSHEET_ID)

# Crea SlotManager (carica config + state esistente)
sm = SlotManager(gc, sh)

# Risolvi eventuali risultati pendenti dallo storico
print("1/3 Risolvo risultati pendenti dallo storico...")
sm.resolve_history_results()

# Aggiorna SOLO la dashboard Report Ven Dom
print("2/3 Aggiornamento Dashboard Report Ven Dom...")
sm.update_report_sheet()

# Aggiorna anche la MM Dashboard
print("3/3 Aggiornamento Dashboard Money Management...")
sm.update_dashboard_sheet()

print("✅ Dashboard aggiornate!")
