import sys, os, time

root_dir = r"c:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
sys.path.append(root_dir)
sys.path.append(os.path.join(root_dir, "Betfair"))

import config
import gspread

gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_FILE)
sh = gc.open_by_key(config.SPREADSHEET_ID)

sheets_to_clear = ["Segnali", "Money Management", "Report Ven Dom"]
for s_name in sheets_to_clear:
    try:
        ws = sh.worksheet(s_name)
        ws.clear()
        print(f"Cleared '{s_name}' on Google Sheets.")
    except Exception as e:
        print(f"Could not clear '{s_name}': {e}")
        
files_to_delete = [
    os.path.join(root_dir, "Betfair", "mm_history.json"),
    os.path.join(root_dir, "Betfair", "money_management_state.json"),
    os.path.join(root_dir, "Betfair", "past_signals.json")
]
for f_path in files_to_delete:
    if os.path.exists(f_path):
        os.remove(f_path)
        print(f"Deleted local file: {f_path}")
        
print("Cleanup done!")
