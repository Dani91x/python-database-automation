---
description: REGOLE DI SICUREZZA ASSOLUTE — NON VIOLABILI
---

## ⛔ MAI aprire il browser per accedere a file personali dell'utente

- **NON** aprire MAI Google Sheets, Google Drive, o qualsiasi servizio cloud dell'utente via browser
- **NON** tentare MAI di effettuare login in account personali
- **NON** accedere MAI a URL che contengono ID di documenti personali (spreadsheet ID, drive file ID, ecc.)
- I file Google Sheets vengono gestiti SOLO via API (gspread) nel codice Python, MAI via browser
- Questa regola è ASSOLUTA e non ammette eccezioni

## Motivazione
Questi file contengono dati personali e proprietà intellettuale. L'accesso via browser è una violazione della privacy.
