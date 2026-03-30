import gspread
import config
gc = gspread.service_account(config.GOOGLE_CREDENTIALS_FILE)
sh = gc.open_by_key(config.SPREADSHEET_ID)

try:
    ws = sh.worksheet('Test Formula')
    ws.clear()
except:
    ws = sh.add_worksheet(title='Test Formula', rows=10, cols=10)

all_data = [
    ["10", "20", "30", "40", ""]
]

requests = [{
    "updateCells": {
        "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 5},
        "rows": [{"values": [
            {"userEnteredValue": {"numberValue": 10.5}},
            {"userEnteredValue": {"numberValue": 20.2}},
            {"userEnteredValue": {"stringValue": "VINTO"}},
            {"userEnteredValue": {"formulaValue": '=SUM(A1:B1)'}},
            {"userEnteredValue": {"formulaValue": '=IF(C1="VINTO", 1, 0)'}},
        ]}],
        "fields": "userEnteredValue"
    }
}]

sh.batch_update({"requests": requests})
print("Written formulas. Reading back...")

import time
time.sleep(2)

print("Values:", ws.row_values(1))
print("Formulas:", ws.get('A1:E1', value_render_option='FORMULA')[0])
