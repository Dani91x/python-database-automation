# ARCHITETTURA_2026-10 — Piano di implementazione della nuova architettura (08/10/2026)

Brief: `BRIEF_PIANO_ARCHITETTURA_2026-10-08.md` (par. 9 vale su tutto). Solo documenti: nessun codice di produzione toccato.

| Documento | Contenuto |
|---|---|
| `06_RIEPILOGO_PER_L_UTENTE.md` | **Da leggere per primo**: cosa cambia, cosa resta, tempi, decisioni che servono |
| `00_INVENTARIO.md` | Mappa di oggi generata da script (`strumenti/inventario/`): righe, import, DB, duplicati, processi, UI, cartelle |
| `01_FUNZIONALITA.md` | 970 funzionalita' con `file:riga`, generate dalle schede (`strumenti/f01_assembla_funzionalita.py`) |
| `02_COMPETITOR.md` | Bet Angel, Geeks Toy, Fairbot, Cymatic, Bfexplorer, Traderline, Gruss; limiti API Betfair; flumine; tabella di parita' (63 fonti) |
| `03_SCHEDE_COMPONENTI/` | 15 schede a 7 sezioni: A connessione, B punteggi, C ordini, D runtime, E1 Mike, E2 Omega, E3 Safe+scanner, E4 scalper calcio, E5 tennis, F contabilita', G dati e algoritmi del cloud, H banco, I processi h24, J frontend, K codice morto |
| `04_ARCHITETTURA_OBIETTIVO.md` | Struttura nuova: componenti, contratti tipati, flussi, processi, dati locale/cloud, latenze obiettivo, righe |
| `05_PIANO_DI_MIGRAZIONE.md` | 29 tappe (T0A-T0C, T1-T26) con parita', ombra, interruttore, ritorno; copertura delle 970 voci; 86 decisioni U-01..U-86 |
| `07_MISURE_OGGI.md` | Misure di oggi (feed, ordini, DB, disco, laboratorio SQLite/log) con gli script in `strumenti/misure/` |
| `08_REVISIONE_CRITICA.md` | Revisione avversaria di 04/05/06 contro il brief: 24 rilievi, correzioni applicate |
| `COSTI.md` | Spesa per tappa (tetto 190 USD) |
| `strumenti/verifica/` | Revisione di 415 citazioni, coperture (05 vs 01: 971/971; tabelle in G: 89+6 e 72 RPC), coerenza finale |
