"""
aggiorna_solo_fogli.py
Aggiorna i fogli Google senza rilanciare l'intero pipeline Betfair.

Esegue nell'ordine:
  1. retroactive_fix_misclassified_results()  — corregge PERSO sbagliati
  2. resolve_history_results()                — risolve PENDING storici dal DB
  3. update_analytics_sheet()                 — scrive il foglio Analytics
"""
import sys
import os

# Assicura che il root del progetto sia nel path
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import gspread
import config
from Betfair.money_management import SlotManager

print("=" * 55)
print("  AGGIORNA FOGLI GOOGLE")
print("  (retrofix + resolve + analytics)")
print("=" * 55)

print("\nConnessione Google Sheets...")
gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_FILE)
sh = gc.open_by_key(config.SPREADSHEET_ID)
sm = SlotManager(gc, sh)

print("\n[1/3] Correzione retroattiva risultati errati...")
sm.retroactive_fix_misclassified_results()

print("\n[2/3] Risoluzione slot PENDING storici dal DB...")
sm.resolve_history_results()

print("\n[3/4] Aggiornamento foglio 'Report Ven Dom'...")
sm.update_report_sheet()

print("\n[4/4] Aggiornamento foglio Analytics...")
sm.update_analytics_sheet()

print("\n" + "=" * 55)
print("  COMPLETATO!")
print("=" * 55)
