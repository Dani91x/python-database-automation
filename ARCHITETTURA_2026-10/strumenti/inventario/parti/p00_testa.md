# 00 - INVENTARIO: la mappa completa del software di OGGI

Data: 08/10/2026. Autore: delegato Sonnet (ripresa del primo giro interrotto). Base: HEAD `dfae4541` del ramo
`claude/eloquent-franklin-g2nyk5` (221 commit sopra la base `22d19cc` dell'inventario del 02/10).
Metodo: ogni numero esce da uno script rieseguibile in `ARCHITETTURA_2026-10/strumenti/inventario/` (sezione 9,
«come rieseguire»); le uscite grezze stanno in `strumenti/inventario/uscite/` (nessuna supera 1 MB). Questo file e'
ASSEMBLATO da `strumenti/inventario/z_assembla.py` con le parti in `strumenti/inventario/parti/`: i blocchi in carattere
fisso e le tabelle grandi sono copiati dalle uscite degli script, il testo e' scritto a mano e cita la fonte.
**Stato dell'albero misurato**: HEAD `dfae4541` piu' due file modificati e NON committati da un'altra sessione (`db_client.py` +326 righe, `season_gaps.py`; `git status`), che spostano alcuni numeri rispetto a HEAD puro: radice 24.318 -> 24.803 righe, `.table(` di produzione 549 -> 552, tabelle usate 88 -> 89, archi 1.461 -> 1.462 (i numeri di questo file sono quelli dell'albero cosi' com'era alle ~15:30; rieseguire gli script dopo il commit di quei due file li allinea a HEAD). Nessun codice di produzione e' stato eseguito; nessuna chiamata a Betfair; il DB non e' stato toccato.

## 0. RIEPILOGO (una pagina)

**Dimensione.** 4.716 file tracciati (`git ls-files`), 2.445.614 righe di testo (324 file binari non contati).
Righe contate come `wc -l` (controllo indipendente su 5 voci con `wc -l`: `omega_service.py` 8.936,
`replayBotCatalogo.ts` 11.099, `desktop/main.js` 951, `stream/trading` 4.301, `tennis_scalper` 8.943,
`migrations/*.sql` 33.835: tutti identici a s01).

| Parte | File | Righe | Note (fonte: `s01_riepilogo.txt`) |
|---|---:|---:|---|
| Python di produzione, `Betfair/` | 213 | 169.111 | `stream/` (con sottocartelle) 88.987, `safe_strategy` 34.635, `omega` 20.913, `mike` 17.755, radice del pacchetto 6.821 |
| Python di produzione, radice (`*.py`) | 88 | 24.803 | pipeline dati, ML, backfill, report; 63 dei 88 non sono importati da altri file di produzione (molti sono punti d'ingresso dei workflow o dei `.bat`) |
| Python di produzione, altre cartelle | 106 | 25.464 | `Ai Engine` 8.845, `laboratorio` 5.356, `Prediction` 3.911, `market_intelligence` 2.513, ... |
| **Python di produzione, totale** | **407** | **219.378** | |
| Test Python | 591 | 193.411 | 63.644 solo in `Betfair/stream/tests` |
| Strumenti (`tools/`, `*/tools/`) | 76 | 35.486 | replay per bot, misure, verifiche |
| Script Python nelle cartelle AUDIT/SCHEMI/ARCHITETTURA | 368 | 33.539 | sonde usa-e-getta, non codice di prodotto |
| Frontend codice (`frontend/src`, ts/tsx/js/css) | 426 | 125.573 | +11.099 GENERATI (`replayBotCatalogo.ts`) = 136.672 |
| Frontend test | 366 | 73.535 | |
| Frontend altro (config, public, lock, ...) | 151 | 45.900 | |
| Desktop (Electron) | 7 | 6.506 | codice js 1.117 + test 66 + `package-lock.json` 5.287 |
| SQL | 179 | 35.244 | di cui `migrations/` 33.835 |
| Documenti `.md` | 417 | 123.903 | |
| Dati, html, patch, log, config (il vecchio blocco «altro») | 1.414 (+313 binari) | 1.542.040 | spiegato in 1.6: json 1.024.505, html 199.005, txt/log 187.039, patch 118.828, script/config 12.663 |

**Scostamenti dal brief del piano (§1 del brief)**: 8 confronti su 31 non tornano; il piu' grave e' il totale backend
(271.857 nel brief contro 193.914 per `Betfair/`+radice con la stessa definizione di «codice»; la somma delle
componenti dichiarate dal brief e' 186.235, quindi il totale dichiarato non e' riproducibile). Dettaglio in 1.7.
Gli indizi di duplicazione del brief non tornano come scritti: `read_book` ha 3 definizioni in produzione (26 nei test),
non 17; `process_market_book` 20 (non 15); `_now_iso` 17 (identiche: vero); `log` 7 in produzione (96 con test).

**Grafo degli import** (`s02`, `s07`, `s08`): 1.442 moduli `.py`, 1.462 archi interni di produzione/strumenti.
Cicli fra cartelle: `safe_strategy <-> omega` (17 e 12 coppie di file), `safe_strategy <-> stream` (35 e 2),
`stream <-> trading` (21 e 3). `Betfair/stream/backtest` importa 15 file da `safe_strategy`, 10 da `omega`, 9 da `tennis_live`.
Candidati morti dopo la controprova per stringa: 23 moduli (circa 3.400 righe) con ZERO riferimenti in tutto il repo
(esclusi audit e test); altri 41 script con `__main__` mai richiamati da nulla. Il gruppo D (27 moduli, 21.878 righe) NON e'
morto: e' fatto di punti d'ingresso lanciati con `-m` (`runner`, `watchdog`, `worker`, `scalper_service`, i job dei workflow)
e dei moduli `certificazione.py` del banco.

**Database** (`s03`, `s05`, `g01`): 966 chiamate `.table()/.rpc()/storage/REST` trovate (552 `.table()` di produzione Python,
164 `.rpc()` del frontend, 53 `.rpc()` di produzione). Tabelle toccate da produzione o frontend: **89** (88 da Python di produzione, 17 dal frontend) (brief: 55); 103
tabelle definite in `migrations/`+`sql/`; 17 usate e non definite nei `.sql` tracciati (tutte nominate in
`DOCUMENTAZIONE_DATABASE.md`); 32 definite senza `.table()` letterale, di cui 21 senza alcun riferimento in produzione
(vivono nel mondo SQL: cron e funzioni). RPC distinte: 170 (frontend 150). Frequenze: solo quelle di
`SCHEMI_BOT/sistema/MISURE_2026-10-02.md` (1.309 chiamate/min totali nella finestra 60 s, riga 51).

**Processi**: `desktop/main.js:413-484` avvia 9 servizi Python SOTTO watchdog (fino a 18 processi Python: 9 watchdog + 9
figli) + il job `betfair_tennis_odds.py` ogni 30 minuti (senza watchdog) + 1 processo figlio per ogni sessione scalper
(`scalper_service.py:702`); un server HTTP statico su 47330. **Porte locali**: 8 porte di lock (47311-47316, 47318, 47319; la 47317 non e' usata da nessuno
e la 47312 compare come default in due moduli), 8 canali WebSocket (47331-47338), 1 HTTP UI (47330), 1 HTTP ordini a mano vecchio
(8787, non acceso dall'app).

**Frontend**: 26 rotte (App.tsx), 389 file di codice analizzati, 150 RPC distinte, 17 tabelle via `.from()`, 0 `fetch()` diretti,
0 edge function invocate, 32 punti `getLocalChannel`, 59 punti realtime, 73 punti di polling; l'unico IPC Electron e' il token dei
canali (`desktop/preload.js:21`).

**Radice**: 54 voci VIVE, 64 ARCHIVIO, 18 MORTE, 1 non verificabile (`Telegram bot`: Edge Function Supabase), 20 test di radice.
Le MORTE sono 2.717 righe di Python.

**Rispetto al 02/10**: 221 commit; il 54% delle 277 citazioni `file:riga` di `INVENTARIO_ARCHITETTURA.md` e' ancora alla stessa
riga, il 45% e' spostato, 3 sono cambiate; 8 file Python di produzione aggiunti (banco `applica_bot`/`varianti_bot`, Replay
Tennis, Media Under), nessuno tolto.

