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


## 1. Righe per file e per cartella (dai file tracciati)

Script: `s01_righe.py` -> `uscite/s01_righe_per_file.tsv` (una riga per file: percorso, categoria, righe, byte) e
`uscite/s01_riepilogo.txt`. Righe = numero di `\n` (come `wc -l`). Categorie decise dallo script (`s01_righe.py:39-86`):
test = `test_*.py`, `*_test.py`, `conftest.py` o cartella `tests/`; strumenti = cartella `tools/`; script audit = `.py` dentro
`AUDIT_*`, `_AUDIT_*`, `SCHEMI_BOT`, `ARCHITETTURA_2026-10`; **generati** = file che dichiarano «FILE GENERATO»/`@generated` nelle
prime 15 righe (oggi uno solo: `frontend/src/lib/replayBotCatalogo.ts`, dichiarato alle righe 2-9 del file stesso, rigenerato da
`python -m Betfair.stream.backtest.applica_bot --catalogo-ts`).

### 1.1 Totali per categoria e macro-categorie

```
== A. TOTALE PER CATEGORIA ==
categoria                       file       righe
altro_dati_json_csv              379     1024505
altro_html                        15      199005
py_test                          591      193411
altro_txt_log                    818      187039
py_codice_Betfair                213      169111
frontend_codice                  426      125573
documenti                        417      123903
altro_patch                       91      118828
frontend_test                    366       73535
frontend_altro                   151       45900
py_strumenti                      76       35486
sql                              179       35244
py_script_audit                  368       33539
py_codice_cartelle_radice        106       25464
py_codice_radice                  88       24803
altro_script_config              111       12663
generati                           1       11099
desktop_altro                      2        5323
desktop_codice                     4        1117
desktop_test                       1          66
altro_binari_pdf_img_pkl         313           0
TOTALE                          4716     2445614
```
```
== A2. MACRO-CATEGORIE (compito §1) ==
macro                                                          file      righe
1 codice Python produzione (Betfair/)                           213     169111
2 codice Python radice (*.py)                                    88      24803
3 codice Python altre cartelle di radice                        106      25464
4 test Python                                                   591     193411
5 strumenti (tools/ e */tools/)                                  76      35486
6 script Python nelle cartelle AUDIT/SCHEMI/ARCHITETTURA        368      33539
7 frontend codice (src, ts/tsx/js/css)                          426     125573
8 frontend test                                                 366      73535
9 frontend altro (config, public, lock, ...)                    151      45900
10 desktop altro (package-lock ecc.)                              2       5323
10 desktop codice (js)                                            4       1117
10 desktop test                                                   1         66
11 SQL                                                          179      35244
12 documenti (.md)                                              417     123903
13 GENERATI (dichiarati nelle prime 15 righe)                     1      11099
14 ALTRO: altro_binari_pdf_img_pkl                              313          0
14 ALTRO: altro_dati_json_csv                                   379    1024505
14 ALTRO: altro_html                                             15     199005
14 ALTRO: altro_patch                                            91     118828
14 ALTRO: altro_script_config                                   111      12663
14 ALTRO: altro_txt_log                                         818     187039
```

### 1.2 Per cartella di radice (tutte le categorie)

```
== B. PER CARTELLA DI RADICE (tutti i file tracciati) ==
cartella                             file      righe  categorie principali (righe)
Betfair                               941     896461  altro_dati_json_csv=479424, py_test=178889, py_codice_Betfair=169111, py_strumenti=34414
AUDIT_2026-09-25                      658     532215  altro_dati_json_csv=454612, altro_txt_log=34273, documenti=16584, py_script_audit=13172
frontend                              946     256463  frontend_codice=125573, frontend_test=73535, frontend_altro=45900, generati=11099
SCHEMI_BOT                             93     228102  altro_html=198708, documenti=19700, altro_dati_json_csv=8051, py_script_audit=1640
<file di radice>                      204     107284  altro_dati_json_csv=36058, py_codice_radice=24803, altro_txt_log=19065, documenti=18673
AUDIT_2026-10-02                      144      83592  altro_patch=53220, altro_txt_log=11391, altro_dati_json_csv=10922, documenti=4753
AUDIT_2026-09-30                      224      57332  altro_patch=36601, altro_txt_log=10411, documenti=7919, py_script_audit=1928
AUDIT_2026-10-07                      182      40024  altro_txt_log=32962, documenti=4278, py_script_audit=2130, altro_patch=533
AUDIT_2026-10-01                      318      37330  altro_patch=18378, altro_txt_log=7742, documenti=6208, altro_script_config=2992
migrations                            175      35013  sql=33835, documenti=884, py_codice_cartelle_radice=294
AUDIT_2026-10-04                      130      31680  altro_txt_log=27755, documenti=2413, py_script_audit=1132, altro_patch=380
market_intelligence                    12      27522  altro_dati_json_csv=25009, py_codice_cartelle_radice=2513
AUDIT_2026-09-28                      183      24728  altro_txt_log=11530, documenti=8148, py_script_audit=4752, altro_script_config=298
Ai Engine                              54      11990  py_codice_cartelle_radice=8845, documenti=1588, py_test=1557
AUDIT_2026-09-29                       71      11653  altro_txt_log=6096, documenti=3178, altro_patch=1419, py_script_audit=960
AUDIT_2026-10-08                       33      10825  altro_txt_log=6005, altro_dati_json_csv=4379, documenti=441
AUDIT_2026-10-05                       52       7781  altro_txt_log=5423, altro_dati_json_csv=1091, documenti=620, py_script_audit=616
Prediction                              8       7172  py_codice_cartelle_radice=3911, py_test=3072, altro_script_config=189
desktop                                 7       6506  desktop_altro=5323, desktop_codice=1117, desktop_test=66
laboratorio                            20       5826  py_codice_cartelle_radice=5356, py_test=245, documenti=225
AUDIT_2026-10-06                       37       4294  altro_txt_log=2895, documenti=483, py_script_audit=463, altro_dati_json_csv=393
_AUDIT_2026_05                        109       3934  altro_dati_json_csv=1963, py_script_audit=1887, documenti=84, altro_binari_pdf_img_pkl=0
Telegram bot                           12       3071  altro_script_config=1790, altro_dati_json_csv=1281, sql=0
tactical_engine                        20       2817  py_codice_cartelle_radice=1515, py_test=1069, py_strumenti=233
AUDIT_2026-09-26                       18       2397  documenti=1272, py_script_audit=921, altro_script_config=111, altro_txt_log=93
AUDIT_2026-09-24                        7       2199  documenti=2199
sql                                     9       1795  py_codice_cartelle_radice=909, sql=886
football_data_scraper                   7       1392  py_codice_cartelle_radice=1392
tools                                   5       1243  py_strumenti=839, altro_script_config=404
.github                                10       1199  altro_script_config=1199
value_engine                           12        859  py_codice_cartelle_radice=729, py_test=130, altro_dati_json_csv=0
ARCHITETTURA_2026-10                    4        561  documenti=350, py_script_audit=211
docs                                    2        276  documenti=276
registrazioni_banco                     7         56  documenti=34, altro_dati_json_csv=22, altro_binari_pdf_img_pkl=0
.agent                                  1         14  documenti=14
.claude                                 1          8  altro_dati_json_csv=8
```

### 1.3 `Betfair/` per sottocartella (solo `.py`)

```
== C. Betfair/ PER SOTTOCARTELLA (solo .py: codice | test | strumenti, righe) ==
cartella                                         codice     test   strum.  file cod.
Betfair/safe_strategy                             34635    39451     7355         26
Betfair/stream                                    25850        0        0         44
Betfair/stream/scalper                            21620        0     4355         32
Betfair/omega                                     20913    27138    11136         15
Betfair/mike                                      17755    28605     3198         10
Betfair/stream/backtest                           13391        0     3640         16
Betfair/stream/tennis_live                        11638    13498     1679         15
Betfair/stream/tennis_scalper                      8943     3797        0         18
Betfair/*.py (radice del pacchetto)                6821      537        0         11
Betfair/stream/trading                             4301        0        0         12
Betfair/stream/engine                              1444        0        0          4
Betfair/stream/scores                               989        0        0          6
Betfair/stream/tennis_replay                        811      853        0          4
Betfair/stream/tests                                  0    63644        0          0
Betfair/stream/tools                                  0        0     1177          0
Betfair/tests                                         0     1366        0          0
Betfair/tools                                         0        0     1874          0
```

### 1.4 I file piu' grandi

```
== D. 25 FILE PIU GRANDI: py_codice_Betfair ==
   11136  Betfair/safe_strategy/bot_service.py
    8936  Betfair/omega/omega_service.py
    7551  Betfair/mike/service.py
    5359  Betfair/mike/engine.py
    3997  Betfair/stream/live_order_worker.py
    3483  Betfair/stream/tennis_live/tennis_runner.py
    3444  Betfair/safe_strategy/service.py
    3397  Betfair/money_management.py
    3315  Betfair/stream/scalper/scalper_bot.py
    3171  Betfair/stream/runner.py
    3093  Betfair/safe_strategy/execution.py
    3046  Betfair/stream/backtest/banco_comune.py
    2974  Betfair/stream/tennis_scalper/tennis_scalper_bot.py
    2637  Betfair/stream/scalper/media_under_bot.py
    2472  Betfair/stream/scalper/certificazione.py
    2434  Betfair/stream/motore_ordini.py
    2303  Betfair/stream/scalper/scalper_session.py
    2254  Betfair/safe_strategy/engine.py
    2160  Betfair/omega/certificazione.py
    2084  Betfair/mike/certificazione.py
    2036  Betfair/safe_strategy/certificazione.py
    1831  Betfair/stream/tennis_live/tennis_live_order_worker.py
    1794  Betfair/omega/omega_market.py
    1778  Betfair/stream/backtest/trasporto_rapido.py
    1737  Betfair/betfair_report_manager.py
```
```
== D. 25 FILE PIU GRANDI: py_codice_radice ==
    1660  master_backtest.py
    1216  per_fixture_backfill.py
    1022  seasons_catchup.py
     679  season_gaps.py
     641  _certify_direction_report.py
     631  retrain_all_leagues.py
     622  calibration_analysis.py
     606  update_poisson_calibration.py
     596  generate_dynamic_cal.py
     583  enrich_analytics_snapshots.py
     542  aggiorna_mm_sheets.py
     511  _certify_personal_report.py
     452  build_analytics_signals.py
     428  import_betfair_operations.py
     410  db_client.py
     406  leagues_mapper.py
     404  top_cards_backfill.py
     404  AGGIORNA_CAMPO_db_json_analisi.py
     396  daily_yesterday_backfill.py
     381  standings_backfill.py
     380  top_scorers_backfill.py
     380  top_assists_backfill.py
     373  cloud_retrain_shard.py
     354  injuries_backfill.py
     350  ventaglio_segnali.py
```
```
== D. 25 FILE PIU GRANDI: frontend_codice ==
    4322  frontend/src/components/controlroom/useControlRoom.ts
    2984  frontend/src/components/live/LadderView.tsx
    2454  frontend/src/lib/mike.ts
    2256  frontend/src/lib/safeBot.ts
    2106  frontend/src/index.css
    1740  frontend/src/pages/ControlRoom.tsx
    1731  frontend/src/lib/safeStrategy.ts
    1705  frontend/src/pages/SafeStrategy.tsx
    1655  frontend/src/lib/omega.ts
    1533  frontend/src/lib/interruttori.ts
    1372  frontend/src/pages/SeguiLive.tsx
    1285  frontend/src/lib/dailyHistory.ts
    1280  frontend/src/pages/MatchReplay.tsx
    1220  frontend/src/lib/controlRoom.ts
    1174  frontend/src/components/mike/MikeMatchCard.tsx
    1129  frontend/src/lib/tennis.ts
    1057  frontend/src/lib/liveOrders.ts
    1053  frontend/src/components/controlroom/PannelloBot.tsx
    1051  frontend/src/lib/posizioniChiuse.ts
     978  frontend/src/lib/replayOperazioni.ts
     975  frontend/src/components/live/ScalperPanel.tsx
     946  frontend/src/components/omega/MissionPanel.tsx
     932  frontend/src/components/safestrategy/BotParamsSheet.tsx
     917  frontend/src/components/controlroom/PosizioniChiuse.tsx
     912  frontend/src/pages/Omega.tsx
```

(Le liste dei 25 file piu' grandi di test, test frontend e strumenti sono in `uscite/s01_riepilogo.txt`, sezioni D.)

### 1.5 Il frontend per cartella

```
== F. frontend/src PER CARTELLA (righe: codice | test | generati; file codice) ==
cartella                       codice     test  generati  file cod.
lib                             45369    28786     11099        148
components/controlroom          17426    16699         0         55
pages                           14042     8757         0         25
components/live                  9831     3589         0         21
components/dashboard             6399      563         0         32
components/safestrategy          5125     3206         0         12
anteprima                        4651        0         0         22
components/trading               4346     3222         0         25
components/omega                 3262     2192         0          6
components/tennis                2549      599         0          7
(src/*)                          2426        0         0          4
components/replay                2268      731         0         15
components/mike                  2148     2066         0          7
components/watchlist             1980        0         0          4
components/ui                     903        0         0         15
components/landing                865        0         0          8
certification                     523     1718         0          6
components/report                 488        0         0          2
components/shell                  473      241         0          5
components/tennis-replay          169       43         0          2
fotografia                        165      865         0          1
components                        124        0         0          2
hooks                              31        0         0          1
integrations                       10        0         0          1
test                                0      258         0          0
```

### 1.6 Cosa contiene la categoria «altro» (1.710.906 righe nel primo giro)

Il primo giro di `s01` metteva in «altro» tutto cio' che non era `.py`, `.sql`, `.md`, frontend o desktop, e contava come righe di
testo anche il PDF (168.866 «righe» del solo `Betfair/Betfair_api_documentation.pdf`, un binario senza NUL nei primi 8 KB) e i `.pkl`.
Corretto: i binari si riconoscono ora anche per estensione (`s01_righe.py:23`). Il blocco vero e' questo (1.542.040 righe, 1.414 file,
+313 file binari a 0 righe):

| Sottocategoria | File | Righe | Cosa sono (fonte: sezione A4 sotto) |
|---|---:|---:|---|
| `altro_dati_json_csv` | 379 | 1.024.505 | JSON pretty-printed: `Betfair/omega/data/hazard_atlas_v2.json` 229.179 + `hazard_atlas_v1.json` 167.313 (gli atlanti di rischio di gol, dati letti dai bot: `Betfair/omega/data/` = 479.424 righe), `AUDIT_2026-09-25` 454.612 (misure e snapshot di plancia), radice 36.058 (`dynamic_cal.json` 26.304 ...), `market_intelligence/cache` 25.009 |
| `altro_html` | 15 | 199.005 | 198.708 sono gli schemi `SCHEMI_BOT/sistema/schemi/*.html` e `ARCHITETTURA_ATTUALE.html` (15.000 righe l'uno circa: SVG incorporati) |
| `altro_txt_log` | 818 | 187.039 | uscite di replay e misure dentro `AUDIT_*` (34.273 in `AUDIT_2026-09-25`), 19.065 righe di `.txt/.log` in radice, 11.398 in `Betfair/` |
| `altro_patch` | 91 | 118.828 | `.patch` dei cantieri, tutti in `AUDIT_*` (53.220 in `AUDIT_2026-10-02`) |
| `altro_script_config` | 111 | 12.663 | `.yml` dei workflow (1.199), `Telegram bot/` (1.790: Edge Functions Deno), `.bat`/`.ps1`, `.mjs` di audit |
| `altro_binari_pdf_img_pkl` | 313 | 0 | png, pdf, pkl, gz (`registrazioni_banco/*.jsonl.gz`) |

Nessuna di queste righe e' codice eseguito dall'app: i JSON di `Betfair/omega/data/` sono dati letti dal codice (atlante hazard),
il resto e' audit, schemi, misure.

```
== A3. FILE GENERATI (categoria 'generati') ==
   11099  frontend/src/lib/replayBotCatalogo.ts
```

### 1.7 Verifica dei numeri di §1 del brief del piano

Esito: 8 confronti su 31 differiscono (nella tabella sotto la colonna «brief» e' il valore del brief, «misurato» quello di `s01`).

```
== E. CONFRONTO CON PAR. 1 DEL BRIEF DEL PIANO (valore del brief | valore misurato | esito) ==
Backend codice (Betfair/ + radice, no test/tools)    brief   271857 | misurato   193914 | DIVERSO (-77943)  file brief 256 | misurati 301
  Betfair/stream/                                    brief    88987 | misurato    88987 | UGUALE
    stream/scalper                                   brief    21620 | misurato    21620 | UGUALE
    stream/tennis_live                               brief    11638 | misurato    11638 | UGUALE
    stream/tennis_scalper                            brief     8943 | misurato     8943 | UGUALE
    stream/backtest                                  brief    13391 | misurato    13391 | UGUALE
    stream/trading                                   brief     4301 | misurato     4301 | UGUALE
  Betfair/omega/                                     brief    37500 | misurato    20913 | DIVERSO (-16587)
  Betfair/safe_strategy/                             brief    34635 | misurato    34635 | UGUALE
  Betfair/mike/                                      brief    17755 | misurato    17755 | UGUALE
  Betfair/*.py (radice del pacchetto)                brief     7358 | misurato     6821 | DIVERSO (-537)
    Betfair/omega/omega_service.py                   brief     8936 | misurato     8936 | UGUALE
    Betfair/safe_strategy/bot_service.py             brief    11136 | misurato    11136 | UGUALE
    Betfair/safe_strategy/service.py                 brief     3444 | misurato     3444 | UGUALE
    Betfair/safe_strategy/execution.py               brief     3093 | misurato     3093 | UGUALE
    Betfair/safe_strategy/engine.py                  brief     2254 | misurato     2254 | UGUALE
    Betfair/mike/service.py                          brief     7551 | misurato     7551 | UGUALE
    Betfair/mike/engine.py                           brief     5359 | misurato     5359 | UGUALE
    Betfair/money_management.py                      brief     3397 | misurato     3397 | UGUALE
    Betfair/betfair_report_manager.py                brief     1737 | misurato     1737 | UGUALE
    frontend/src/lib/replayBotCatalogo.ts            brief    11099 | misurato    11099 | UGUALE
    frontend/src/components/controlroom/useControlRoom.ts brief     4322 | misurato     4322 | UGUALE
RICOSTRUZIONE brief: .py di Betfair/ fuori da dir tests/tools/test: 256 file, 186235 righe (somma componenti del brief 88987+37500+34635+17755+7358 = 186235)
   di cui Betfair/omega/: 55 file, 37500 righe (codice vero 20913 + test_*.py sparsi in omega/ 16587)
   => il totale dichiarato dal brief (271.857) NON e' riproducibile: la somma delle sue componenti e' 186.235
Test Python                                          brief   163079 | misurato   193411 | DIVERSO (+30332)
Strumenti (tools/, */tools/)                         brief    35486 | misurato    35486 | UGUALE
Frontend src codice                                  brief   133686 | misurato   125573 | DIVERSO (-8113)
Frontend test                                        brief    73428 | misurato    73535 | DIVERSO (+107)
Desktop (js, tutti)                                  brief     1183 | misurato     1183 | UGUALE
Desktop (solo codice, senza .test.js)                brief     1183 | misurato     1117 | DIVERSO (-66)
SQL (tutti i .sql)                                   brief    33835 | misurato    35244 | DIVERSO (+1409)
SQL (solo migrations/)                               brief    33835 | misurato    33835 | UGUALE
```

Spiegazioni (ognuna ricavata dai dati, non ipotizzata):

1. **`Betfair/omega/` 37.500 (brief) contro 20.913 (misurato)**: la differenza e' esattamente 16.587 righe = i `test_*.py` che stanno
   dentro `Betfair/omega/` (non in una cartella `tests/`). Il brief ha contato come «codice» ogni `.py` fuori da cartelle
   `tests/`/`tools/`; con quella definizione si ritrova anche `Betfair/*.py` 7.358 = 6.821 + 537 di test nella radice del pacchetto, e i
   256 file del brief (`s01_righe.py`, riga «RICOSTRUZIONE brief»: 256 file, 186.235 righe).
2. **Backend 271.857 (brief)**: la somma delle componenti dichiarate dal brief (88.987 + 37.500 + 34.635 + 17.755 + 7.358) e'
   **186.235**, non 271.857. Con la stessa definizione del brief si ottengono 186.235 righe in 256 file: il totale dichiarato dal brief
   non e' riproducibile (85.622 righe non spiegate). Con la definizione di questo inventario (solo codice, test separati) il backend
   `Betfair/` + radice e' **193.914** righe in 301 file; con le altre cartelle di radice (`Ai Engine`, `laboratorio`, ...) **219.378**
   righe in 407 file.
3. **Test Python 163.079 (brief) contro 193.411**: non riproducibile (`Betfair/` da solo ha 178.889 righe di test, radice 8.319).
   Verosimile che il brief abbia contato su un albero precedente o con un'altra definizione; non c'e' modo di ricostruirlo dai dati.
4. **Frontend codice 133.686 contro 125.573**: il valore del brief e' compatibile con «tutti i `.ts/.tsx` non di test di `frontend/src`»
   = 134.673 (comprende i 11.099 righe GENERATE di `replayBotCatalogo.ts`); la nostra categoria «codice» esclude il generato
   (125.573) e include i `.css/.js` (con generato 136.672). **Frontend test 73.428 = esattamente i `.test/.spec` `.ts/.tsx`**
   (nostro 73.535 comprende `frontend/src/test/setup.ts` 75 e `forzaSupabaseFinto.ts` 32).
5. **Desktop 1.183 = 1.117 (codice) + 66 (`ambiente_runner.test.js`)**: il brief conta anche il test (la riga «Desktop (js, tutti)» e' UGUALE).
6. **SQL 33.835 = solo `migrations/`**; con `sql/` (886 righe di SQL) e gli altri `.sql` tracciati si arriva a 35.244.
7. Tutti i file nominati nel brief (`omega_service.py` 8.936, `bot_service.py` 11.136, `mike/service.py` 7.551, `replayBotCatalogo.ts` 11.099,
   `useControlRoom.ts` 4.322, ...) e le sottocartelle di `stream/` (scalper 21.620, tennis_live 11.638, tennis_scalper 8.943,
   backtest 13.391, trading 4.301) sono UGUALI.
8. «55 tabelle usate dal codice» (brief) non torna: sono 89 (sezione 3).


## 2. Grafo degli import interni

Script: `s02_import.py` (AST su tutti i `.py` tracciati, nessun codice eseguito) -> `uscite/s02_moduli.tsv` (una riga per modulo:
categoria, righe, importatori per tipo, n. importazioni, riferimenti per stringa, `__main__`, librerie esterne),
`s02_archi.tsv` (importatore -> importato, 1.462 archi di produzione/strumenti), `s02_esterni.tsv` (per file e libreria: file:riga della
prima importazione), `s02_morti.txt`; poi `s07_cartelle_import.py` (grafo aggregato per cartella), `s08_morti_verifica.py` (controprova
per stringa), `k02_grafo_import.py` (secondo parere: import dinamici, `uscite/k02_import_dinamici.txt`).

**Correzioni fatte agli script del primo giro** (documentate perche' cambiano i numeri):
(a) `s02` non riconosceva gli import `from ai_engine.x import ...` come interni (la cartella `Ai Engine/` e' nel `sys.path`): 5 moduli
di `Ai Engine/` finivano per errore nel gruppo A dei morti; ora c'e' l'alias (commento in `s02_import.py`, sopra `cat = {...}`).
(b) `k02` decodificava senza BOM e dava 16 falsi `SyntaxError`; ora usa `utf-8-sig` (0 errori, 502 chiamate dinamiche registrate).
(c) `s01` contava come testo i binari senza NUL (PDF): corretto.

### 2.1 Numeri di sintesi e librerie

```
moduli .py tracciati: 1442; non analizzabili (SyntaxError): 0
per categoria: py_test=591, py_script_audit=368, py_codice_Betfair=213, py_codice_cartelle_radice=106, py_codice_radice=88, py_strumenti=76
archi interni (prod+strumenti verso qualsiasi): 1462
import dinamici (import_module/__import__) nel codice: Betfair/omega/omega_service.py=1, Betfair/safe_strategy/bot_service.py=1, Betfair/safe_strategy/tools/replay_registrazioni.py=1, Betfair/stream/backtest/registro_bot.py=2
```
```
== Librerie chiave per categoria di file (n. file che le importano) ==
betfairlightweight   totale   99 file: py_test=61, py_codice_Betfair=26, py_script_audit=6, py_strumenti=5, py_codice_cartelle_radice=1
flumine              totale  163 file: py_test=91, py_codice_Betfair=51, py_codice_cartelle_radice=10, py_strumenti=7, py_script_audit=4
supabase             totale   13 file: py_script_audit=6, py_strumenti=4, py_codice_Betfair=1, py_codice_radice=1, py_codice_cartelle_radice=1
requests             totale   17 file: py_codice_Betfair=5, py_script_audit=4, py_test=4, py_codice_radice=4
httpx                totale   18 file: py_test=10, py_codice_radice=7, py_codice_Betfair=1
websockets           totale   24 file: py_script_audit=11, py_codice_Betfair=7, py_test=5, py_strumenti=1
aiohttp              totale    0 file: 
urllib               totale    0 file: 
socket               totale    0 file: 
websocket            totale    0 file: 
postgrest            totale   12 file: py_test=10, py_codice_Betfair=2
psycopg2             totale    0 file: 
sqlalchemy           totale    0 file:
```

### 2.2 Chi parla con l'esterno in PRODUZIONE (file:riga della prima importazione)

```
== Chi parla con l'esterno: file di PRODUZIONE (py_codice_*) per libreria chiave ==
-- betfairlightweight: 27 file
   Betfair/safe_strategy/service.py:633
   Betfair/safe_strategy/stream.py:149
   Betfair/stream/auth.py:13
   Betfair/stream/backtest/banco_comune.py:1910
   Betfair/stream/backtest/certifica.py:235
   Betfair/stream/board_worker.py:59
   Betfair/stream/raw_listener.py:21
   Betfair/stream/reconcile_worker.py:493
   Betfair/stream/recorder.py:21
   Betfair/stream/runner.py:29
   Betfair/stream/scalper/habitat_scan.py:45
   Betfair/stream/scalper/run_scalper_live.py:84
   Betfair/stream/scalper/scalper_session.py:1326
   Betfair/stream/scores/betfair_inplay.py:16
   Betfair/stream/sottoscrizione_a_caldo.py:67
   Betfair/stream/tennis_live/mercati_registrati.py:45
   Betfair/stream/tennis_live/tennis_recorder.py:43
   Betfair/stream/tennis_live/tennis_runner.py:45
   Betfair/stream/tennis_replay/convertitore.py:40
   Betfair/stream/tennis_scalper/backtest_pro.py:24
   Betfair/stream/tennis_scalper/record_multi.py:30
   Betfair/stream/tennis_scalper/record_tennis.py:21
   Betfair/stream/tennis_scalper/research_data.py:14
   Betfair/stream/tennis_scalper/run_tennis_pro.py:22
   Betfair/stream/tennis_scalper/run_tennis_scalper.py:28
   Betfair/stream/valuta.py:83
   laboratorio/tennis_lab/lab_grid_score.py:100
-- flumine: 61 file
   Betfair/safe_strategy/proposte_opportunita.py:679
   Betfair/stream/backtest/banco_comune.py:1492
   Betfair/stream/backtest/certifica.py:236
   Betfair/stream/backtest/chiusura_parziale.py:441
   Betfair/stream/backtest/minimi_banco.py:172
   Betfair/stream/backtest/porta_banco.py:701
   Betfair/stream/backtest/run_backtest.py:39
   Betfair/stream/backtest/sim_strategy.py:34
   Betfair/stream/backtest/trasporto_rapido.py:1362
   Betfair/stream/client_paper_affiancato.py:13
   Betfair/stream/engine/live_trading_strategy.py:33
   Betfair/stream/frammenti_mercato.py:72
   Betfair/stream/live_order_build.py:39
   Betfair/stream/raw_listener.py:22
   Betfair/stream/recorder.py:22
   Betfair/stream/runner.py:31
   Betfair/stream/saldo_evento.py:238
   Betfair/stream/scalper/certificazione.py:1496
   Betfair/stream/scalper/media_under_bot.py:86
   Betfair/stream/scalper/run_scalper.py:20
   Betfair/stream/scalper/run_scalper_live.py:206
   Betfair/stream/scalper/run_theta.py:33
   Betfair/stream/scalper/scalper_bot.py:55
   Betfair/stream/scalper/scalper_session.py:1325
   Betfair/stream/scalper/sniper_bot.py:34
   Betfair/stream/scalper/theta_bot.py:55
   Betfair/stream/sottoscrizione_a_caldo.py:52
   Betfair/stream/tennis_live/certificazione_bot.py:871
   Betfair/stream/tennis_live/guardie_tennis.py:57
   Betfair/stream/tennis_live/iscrizione_a_caldo.py:263
   Betfair/stream/tennis_live/paper_execution.py:38
   Betfair/stream/tennis_live/tennis_live_order_worker.py:224
   Betfair/stream/tennis_live/tennis_recorder.py:44
   Betfair/stream/tennis_live/tennis_runner.py:49
   Betfair/stream/tennis_scalper/backtest_pro.py:22
   Betfair/stream/tennis_scalper/condotta_ordini.py:234
   Betfair/stream/tennis_scalper/flb_backtest.py:23
   Betfair/stream/tennis_scalper/record_multi.py:31
   Betfair/stream/tennis_scalper/record_tennis.py:20
   Betfair/stream/tennis_scalper/run_tennis_pro.py:20
   Betfair/stream/tennis_scalper/run_tennis_scalper.py:26
   Betfair/stream/tennis_scalper/tennis_flb_bot.py:31
   Betfair/stream/tennis_scalper/tennis_pro_bot.py:37
   Betfair/stream/tennis_scalper/tennis_scalper_bot.py:55
   Betfair/stream/tennis_scalper/tennis_swing_bot.py:16
   Betfair/stream/tennis_scalper/tune_tennis.py:22
   Betfair/stream/trading/controls.py:40
   Betfair/stream/trading/dutching.py:25
   Betfair/stream/trading/greenup.py:49
   Betfair/stream/trading/risk_engine.py:36
   Betfair/stream/valuta.py:316
   laboratorio/scalper_lab/bt_lab.py:31
   laboratorio/scalper_lab/bt_theta.py:23
   laboratorio/scalper_lab/grid_strategy.py:36
   laboratorio/scalper_lab/scalper_bot_base.py:55
   laboratorio/scalper_lab/theta_strategy.py:32
   laboratorio/tennis_lab/lab_grid.py:24
   laboratorio/tennis_lab/lab_grid_score.py:21
   laboratorio/tennis_lab/tennis_lab.py:27
   laboratorio/tennis_lab/tennis_lab_score.py:31
   laboratorio/tennis_lab/validate.py:24
-- supabase: 3 file
   Betfair/stream/tennis_live/tennis_db.py:22
   db_client.py:6
   football_data_scraper/fix_snapshot_time.py:12
-- requests: 9 file
   Betfair/client.py:10
   Betfair/omega/omega_market.py:508
   Betfair/stream/auth.py:14
   Betfair/stream/runner_lifecycle.py:242
   Betfair/stream/tennis_live/paper_execution.py:36
   admin_reset_password.py:17
   api_client.py:3
   api_quota.py:40
   seasons_catchup.py:151
-- httpx: 8 file
   Betfair/stream/runner_lifecycle.py:248
   build_analytics_signals.py:34
   build_direzione.py:16
   db_client.py:52
   enrich_analytics_snapshots.py:76
   leagues_mapper.py:10
   merge_engine_signals.py:28
   refresh_analytics_bets.py:67
-- websockets: 7 file
   Betfair/mike/service.py:6814
   Betfair/safe_strategy/canale_scan.py:407
   Betfair/safe_strategy/porta_ordini.py:535
   Betfair/stream/esiti_ordini_canale.py:229
   Betfair/stream/local_channel.py:292
   Betfair/stream/sveglia_canale.py:250
   Betfair/stream/tennis_live/canale_bot_tennis.py:107
-- aiohttp: 0 file
```

Letture di questa tabella (ogni punto e' un `file:riga` qui sopra):

- **Due client Betfair diversi.** `betfairlightweight` (27 file di produzione) e' la libreria dello STREAM e di tutto il percorso
  flumine (`Betfair/stream/runner.py:29`, `Betfair/stream/tennis_live/tennis_runner.py:45`, `Betfair/safe_strategy/stream.py:149`,
  `Betfair/stream/auth.py:13`, `Betfair/stream/reconcile_worker.py:493`). In parallelo esiste un **client proprio** su `requests`
  (JSON-RPC, login con certificato): `Betfair/client.py:10` (426 righe, importato da 6 file di produzione, tra cui `runner.py`,
  `betfair_report_manager.py`, `odds_refresh.py`, `betfair_full_odds.py`, `betfair_tennis_odds.py`) e `Betfair/omega/omega_market.py:508` (1.794 righe, il client
  «a domanda» importato da Mike, Safe e Omega per gli ordini veri e le quote di ripiego; 69 test lo importano).
  `Betfair/stream/auth.py:13-14` importa entrambe (`betfairlightweight` e `requests`).
- **`flumine`**: 61 file di produzione, ma i processi che lo usano come motore sono pochi: runner calcio (`runner.py:31`), runner tennis
  (`tennis_runner.py:49`), sessione scalper (`scalper_session.py`), il banco (`banco_comune.py`, `porta_banco.py`, `trasporto_rapido.py`) e
  le classi bot in `stream/trading/*` (`controls.py:40`, `dutching.py:25`, `greenup.py:49`, `risk_engine.py:36`).
  Nei file dei tre bot di punta (`mike/`, `omega/`, `safe_strategy/`) l'unico import di `flumine` e' pigro e di utilita'
  (`Betfair/safe_strategy/proposte_opportunita.py:679`, `from flumine.utils import PRICES_FLOAT`, la scala dei prezzi): i loro ordini
  passano dal runner (sezione 5).
- **Un solo client Supabase di produzione** (`db_client.py:6`, `from supabase import create_client`, un client PER THREAD,
  `db_client.py:75`) piu' un SECONDO `create_client` in `Betfair/stream/tennis_live/tennis_db.py:22` (che non passa da
  `db_client`) e uno script (`football_data_scraper/fix_snapshot_time.py:12`). Gli altri accessi al DB importano `db_client`
  (107 file di produzione, il modulo piu' importato del repo) e parlano `postgrest` via la libreria (`Betfair/stream/db.py:19`,
  `Betfair/stream/runner_lifecycle.py:279` importano solo `APIError`). `httpx` in produzione: `db_client.py:52` (timeout del profilo bot)
  e 6 job di pipeline (`enrich_analytics_snapshots.py:76`, `refresh_analytics_bets.py:67`, ...).
- **`requests`** (9 file): login/JSON-RPC Betfair (`Betfair/client.py:10`, `omega_market.py:508`, `auth.py:14`), API-Football
  (`api_client.py:3`, `api_quota.py:40`, `seasons_catchup.py:151`), `runner_lifecycle.py:242`, `tennis_live/paper_execution.py:36`.
- **`websockets`** (7 file) solo per i canali locali: server in `local_channel.py:292`, client in `esiti_ordini_canale.py:229`,
  `sveglia_canale.py:250`, `safe_strategy/canale_scan.py:407`, `safe_strategy/porta_ordini.py:535`,
  `tennis_live/canale_bot_tennis.py:107`, `mike/service.py:6814`.
- Non c'e' nessun `aiohttp`, `psycopg2`, `sqlalchemy`, `urllib` esplicito, `socket` esplicito nelle importazioni rilevate dallo script
  (il lock di istanza usa `socket` da `Betfair/stream/single_instance.py:18`: lo script riporta 0 perche' `socket` e' stdlib e
  non e' classificata come esterna; la riga «socket 0 file» della tabella e' un limite dello script, non un fatto).

### 2.3 Moduli piu' importati e piu' accoppiati (produzione)

```
== Moduli di produzione piu' importati (n. importatori di produzione) ==
  108  db_client  (db_client.py)
   54  Betfair.stream  (Betfair/stream/__init__.py)
   24  Betfair.safe_strategy  (Betfair/safe_strategy/__init__.py)
   22  Betfair.omega  (Betfair/omega/__init__.py)
   21  Betfair.stream.local_channel  (Betfair/stream/local_channel.py)
   21  Betfair.stream.db  (Betfair/stream/db.py)
   19  Betfair.stream.trading.minimi_it  (Betfair/stream/trading/minimi_it.py)
   17  config  (config.py)
   17  Betfair.stream.trading  (Betfair/stream/trading/__init__.py)
   17  Betfair.stream.config_stream  (Betfair/stream/config_stream.py)
   16  Betfair.stream.canale_bot  (Betfair/stream/canale_bot.py)
   15  Betfair.stream.live_order_build  (Betfair/stream/live_order_build.py)
   14  api_client  (api_client.py)
   14  Betfair.stream.auth  (Betfair/stream/auth.py)
   12  Betfair.stream.scalper.scalper_bot  (Betfair/stream/scalper/scalper_bot.py)
   11  Betfair.stream.trading.submin  (Betfair/stream/trading/submin.py)
   11  Betfair.stream.trading.stato_mercato  (Betfair/stream/trading/stato_mercato.py)
   11  Betfair.stream.tennis_scalper.tennis_score  (Betfair/stream/tennis_scalper/tennis_score.py)
   10  Betfair.stream.uscite_proposte  (Betfair/stream/uscite_proposte.py)
   10  Betfair.stream.scalper  (Betfair/stream/scalper/__init__.py)
   10  Betfair.stream.live_order_worker  (Betfair/stream/live_order_worker.py)
   10  Betfair.stream.avvio_app  (Betfair/stream/avvio_app.py)
   10  Betfair.safe_strategy.execution  (Betfair/safe_strategy/execution.py)
   10  Betfair.omega.omega_engine  (Betfair/omega/omega_engine.py)
   10  Ai Engine.ai_engine.db_adapter  (Ai Engine/ai_engine/db_adapter.py)
    9  logger  (logger.py)
    9  Betfair.stream.single_instance  (Betfair/stream/single_instance.py)
    9  Betfair.stream.scalper.hazard_atlas  (Betfair/stream/scalper/hazard_atlas.py)
    9  Betfair.stream.arresto_ordinato  (Betfair/stream/arresto_ordinato.py)
    8  Betfair.stream.trading.controls  (Betfair/stream/trading/controls.py)
```
```
== Moduli di produzione con piu' import interni (accoppiamento in uscita) ==
   42  Betfair/stream/tennis_live/tennis_runner.py  (3483 righe)
   40  Betfair/stream/runner.py  (3171 righe)
   35  Betfair/omega/omega_service.py  (8936 righe)
   30  Betfair/safe_strategy/bot_service.py  (11136 righe)
   25  Betfair/mike/service.py  (7551 righe)
   23  Betfair/stream/backtest/trasporto_rapido.py  (1778 righe)
   22  Betfair/stream/scalper/scalper_session.py  (2303 righe)
   20  Betfair/stream/live_order_worker.py  (3997 righe)
   20  Betfair/safe_strategy/service.py  (3444 righe)
   18  Betfair/safe_strategy/execution.py  (3093 righe)
   15  Betfair/stream/tennis_live/tennis_live_order_worker.py  (1831 righe)
   14  Betfair/stream/tennis_live/tennis_bot_service.py  (1183 righe)
   13  Betfair/stream/tennis_live/guardie_tennis.py  (487 righe)
   13  Betfair/stream/backtest/certifica.py  (1084 righe)
   13  Betfair/stream/backtest/banco_comune.py  (3046 righe)
   12  Betfair/stream/scalper/validazione_hazard/banco.py  (695 righe)
   12  Betfair/stream/scalper/scalper_service.py  (982 righe)
   11  Betfair/omega/omega_market.py  (1794 righe)
   10  Betfair/safe_strategy/opportunity.py  (1103 righe)
    9  seasons_catchup.py  (1022 righe)
    9  Betfair/stream/tennis_live/esecutore_tennis.py  (618 righe)
    9  Betfair/omega/omega_proposte.py  (1235 righe)
    9  Betfair/mike/db.py  (693 righe)
    9  Ai Engine/ai_engine/runner.py  (68 righe)
    9  Ai Engine/ai_engine/predict_fixture.py  (1124 righe)
```

### 2.4 Il grafo per cartella (tabella riassuntiva)

Archi = coppie file->file di produzione (`s07_cartelle_import.py`; dettaglio dei 1.462 archi in `uscite/s02_archi.tsv`, per cartella
in `uscite/s07_archi_cartelle.tsv`).

```
== PER CARTELLA (solo file di produzione py_codice_*; archi = coppie file->file) ==
cartella                           file   righe archi_interni verso_altre  da_altre  file_mai_importati_da_prod
Betfair/safe_strategy                26   34635            53          83        43                           2
Betfair/stream/*.py                  44   25850           101          50       197                           2
<radice>                             88   24803           127          31        69                          63
Betfair/stream/scalper               32   21620            70          42        13                           7
Betfair/omega                        15   20913            34          47        34                           3
Betfair/mike                         10   17755            15          50         2                           1
Betfair/stream/backtest              16   13391            28          66         2                           1
Betfair/stream/tennis_live           15   11638            38          85        12                           1
Betfair/stream/tennis_scalper        18    8943            18          24        28                           7
Ai Engine                            40    8845            51           5        18                          11
Betfair/*.py                         11    6821             8          14        21                           2
laboratorio                          17    5356            15          11         0                           6
Betfair/stream/trading               12    4301             5           4        79                           0
Prediction                            5    3911             1           9         3                           3
market_intelligence                   9    2513            13           7         1                           3
tactical_engine                      12    1515            11           6         2                           6
Betfair/stream/engine                 4    1444             1           9        15                           0
football_data_scraper                 7    1392             5           3         0                           2
Betfair/stream/scores                 6     989             5           5        16                           0
sql                                   5     909             2           3         0                           4
Betfair/stream/tennis_replay          4     811             3           9         3                           0
value_engine                         10     729            16           1         7                           3
migrations                            1     294             0           2         1                           0

== I 40 ARCHI cartella -> cartella PIU PESANTI (n. coppie file->file) ==
  Betfair/stream/tennis_live         -> Betfair/stream/*.py                  56
  Betfair/safe_strategy              -> Betfair/stream/*.py                  35
  Betfair/stream/scalper             -> Betfair/stream/*.py                  22
  Betfair/stream/*.py                -> Betfair/stream/trading               21
  Betfair/stream/backtest            -> Betfair/stream/*.py                  20
  Betfair/safe_strategy              -> Betfair/omega                        17
  Betfair/mike                       -> Betfair/stream/*.py                  16
  Betfair/stream/tennis_live         -> Betfair/stream/tennis_scalper        16
  Betfair/stream/backtest            -> Betfair/safe_strategy                15
  Betfair/stream/tennis_scalper      -> Betfair/stream/*.py                  15
  <radice>                           -> Ai Engine                            15
  Betfair/omega                      -> Betfair/stream/*.py                  14
  Betfair/stream/*.py                -> <radice>                             13
  Betfair/omega                      -> Betfair/safe_strategy                12
  <radice>                           -> Betfair/*.py                         11
  Betfair/mike                       -> Betfair/safe_strategy                10
  Betfair/stream/backtest            -> Betfair/omega                        10
  Betfair/stream/scalper             -> Betfair/stream/trading               10
  Betfair/*.py                       -> <radice>                              9
  Betfair/mike                       -> Betfair/stream/trading                9
  Betfair/safe_strategy              -> Betfair/stream/trading                9
  Betfair/stream/backtest            -> Betfair/stream/tennis_live            9
  Betfair/stream/tennis_scalper      -> Betfair/stream/trading                9
  Betfair/stream/tennis_live         -> Betfair/stream/trading                8
  Betfair/mike                       -> Betfair/omega                         7
  Betfair/stream/*.py                -> Betfair/stream/scores                 7
  Prediction                         -> <radice>                              7
  market_intelligence                -> <radice>                              7
  Betfair/omega                      -> Betfair/stream/trading                6
  Betfair/safe_strategy              -> Betfair/stream/tennis_scalper         6
  Betfair/safe_strategy              -> Betfair/stream/scalper                6
  tactical_engine                    -> <radice>                              6
  Betfair/stream/backtest            -> Betfair/stream/trading                5
  Betfair/stream/engine              -> Betfair/stream/*.py                   5
  Betfair/stream/tennis_replay       -> Betfair/stream/*.py                   5
  laboratorio                        -> Betfair/stream/tennis_scalper         5
  Ai Engine                          -> <radice>                              4
  Betfair/omega                      -> Betfair/stream/scores                 4
  Betfair/safe_strategy              -> <radice>                              4
  Betfair/stream/backtest            -> Betfair/stream/engine                 4

== CICLI fra cartelle (archi in entrambe le direzioni) ==
  Betfair/safe_strategy <-> Betfair/stream/*.py: 35 / 2
  Betfair/stream/*.py <-> Betfair/stream/trading: 21 / 3
  Betfair/safe_strategy <-> Betfair/omega: 17 / 12
  <radice> <-> Ai Engine: 15 / 4
  Betfair/stream/*.py <-> <radice>: 13 / 2
  <radice> <-> Betfair/*.py: 11 / 9
  Betfair/stream/*.py <-> Betfair/stream/scores: 7 / 1
  Prediction <-> <radice>: 7 / 3
  Betfair/safe_strategy <-> Betfair/stream/scalper: 6 / 2
  Betfair/stream/engine <-> Betfair/stream/*.py: 5 / 3
  Betfair/stream/*.py <-> Betfair/*.py: 4 / 1
  Betfair/stream/scores <-> Betfair/safe_strategy: 2 / 1
  Betfair/stream/tennis_live <-> Betfair/stream/tennis_replay: 2 / 1
  Betfair/*.py <-> migrations: 1 / 1
```

Letture:

1. Le dipendenze **non vanno in una sola direzione**: `safe_strategy -> omega` (17 coppie) e `omega -> safe_strategy` (12) sono un ciclo;
   `mike` dipende da `safe_strategy` (10) e da `omega` (7); il banco (`stream/backtest`) dipende da `safe_strategy` (15), `omega` (10), `tennis_live` (9).
   Per sostituire Omega oggi si toccano almeno i file elencati in `s02_archi.tsv` con `omega` come importato: 34 archi in entrata da altre cartelle.
2. `Betfair/stream/*.py` (i 44 file piani, 25.850 righe) e' importato da altre cartelle 197 volte: e' il vero «nucleo» di fatto, ma contiene
   insieme runner, DB (`db.py`), canali, ordini, watchdog; non c'e' un confine fra «nucleo Betfair» e «servizi dei bot».
3. `stream/trading` (4.301 righe, 12 file) e' importato 79 volte da altre cartelle ma importa solo 4 volte verso l'esterno: e' l'unica
   cartella a foglia nel grafo interno (importa pero' `flumine`).
4. La radice (`<radice>`, 88 file) riceve 69 archi da altre cartelle; `db_client.py` da solo e' importato da 107 file di produzione, `config.py` da 17.

### 2.5 Candidati morti: gruppi A-D con la prova

Criterio (da `s02_morti.txt`, riga di testa): modulo di produzione (`py_codice_*`, no `__init__`) che nessun file di PRODUZIONE importa (AST).
A = nessun importatore di nessun tipo, nessun riferimento per stringa in file di codice non-audit, nessun `if __name__ == '__main__'`;
B = nessun importatore ma ha `__main__` o e' nominato per stringa; C = importato solo da test; D = importato solo da strumenti/audit.
La **controprova** (`s08_morti_verifica.py`) cerca il nome del file come parola intera in tutto il codice e nei lanciatori
(py, js, ts, yml, bat, ps1, sh), esclusi audit, test e il file stesso; esito ZERO = nessuna citazione in tutto il repo.

| Gruppo | Moduli | Righe | Esito della controprova |
|---|---:|---:|---|
| A nessun riferimento | 26 | 3.610 | **23 ZERO citazioni = morti certi** (3.419 righe); 3 citati per parola generica (`summary.py`, `trainer.py`, `parse.py`: lo stem e' una parola comune) |
| B solo `__main__` o stringa | 73 | 15.490 | 41 ZERO citazioni (script mai richiamati da nulla, ma lanciabili a mano); 32 citati (workflow, `.bat`, frontend, altri moduli; alcuni per stem generico: `pipeline`, `backfill`, `backtest`, `runner`, `cli`, `calibrate`, `test` danno falsi positivi, p.es. `market_intelligence/pipeline.py` non e' lanciato da nessun workflow) |
| C solo test | 1 | 402 | `Betfair/omega/liquidity_probe.py` (test: `test_liquidity_probe_2026_09_10.py`, `test_omega_matematica_2026_09_12.py`) |
| D solo strumenti/audit | 27 | 21.878 | NON morti: punti d'ingresso lanciati con `-m` (vedi sotto) e moduli del banco |

**Gruppo A, i 23 morti certi** (nome, righe; prova: `uscite/s08_morti_verifica.tsv` colonna `esito=ZERO`; rieseguibile con
`git grep -nw <stem>` sui file di codice):
`Ai Engine/ai_engine/analysis/advanced.py` 90, `Ai Engine/ai_engine/models/voting.py` 21, `Betfair/cleanup_reset.py` 32 (citato solo in
`MANUALE_OPERATIVO.md`, un documento), `_certify_betfair_full.py` 37, `analyze_recovery.py` 283, `analyze_threshold.py` 308,
`calibration_analysis.py` 622, `check_gh.py` 13, `laboratorio/scalper_lab/grid_strategy.py` 485 (nominato solo in documenti e test di contratto),
`refresh_dashboard.py` 20, `report_mm.py` 202, `simulate_recovery_forward.py` 287, `tactical_engine/_check_fixpred.py` 24,
`tactical_engine/_inspect_mismatch.py` 21, `tmp_analysis.py` 188, `tmp_analysis2.py` 139, `tmp_predict_today.py` 117, `tmp_smoke_stack.py` 138,
`tmp_today_predictions.py` 141, `tmp_validate_league.py` 66, `tmp_validate_predict.py` 76, `update_dashboard_only.py` 31,
`value_engine/generate_battery.py` 78. Sono script di analisi o di prova: ultimo commit tra il 18/02 e il 24/06/2026 per 22 su 23 (date da `git log -1` e da `uscite/k03_classifica.tsv`: `advanced.py` e `voting.py` 18/02,
`cleanup_reset.py` 04/03, `_check_fixpred.py` e `_inspect_mismatch.py` 20/06, `generate_battery.py` 17/06, `_certify_betfair_full.py` 24/06); l'eccezione e' `laboratorio/scalper_lab/grid_strategy.py`
(25/09, nominato dal test di contratto `Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py`).

**Gruppo B senza alcuna citazione** (41, script con `__main__`): `Ai Engine/ai_engine/{audit_nulls,bss_monitor,evaluate_holdout,generate_fixture_report}.py`,
`Ai Engine/backtest_ml.py`, `Betfair/stream/tennis_scalper/{record_tennis,tune_tennis}.py`, `Prediction/{analyze_sweet_spot,backfill_historical_analysis}.py`,
`_certify_{betfair,delay_context,direction,personal_report,signal_context}.py`, `_league_eval.py`, `_stack_eval.py`, `admin_reset_password.py`,
`backfill_poisson_calibrated.py`, `certify_backtest_strategy.py`, `cleanup_models.py`, `compress_models.py`, `football_data_scraper/fix_snapshot_time.py`,
`laboratorio/scalper_lab/{bt_theta,exp_families,validate_synth}.py`, `load_poisson_calibration_to_db.py`, `market_intelligence/backtest_audit.py`,
`missing_fixtures_backfill.py`, `reset_ai_models.py`, `sanity_check.py`, `sql/{_build_wc_xlsx_2013,_cert_wc_fetch,_cert_wc_full,_verify_delays_math}.py`,
`tactical_engine/{_verify_data_worldcup,run_worldcup}.py`, `tmp_smoke_{ml_fixes,poisson_fixes}.py`, `tmp_train_today.py`,
`valida_{motore_poisson,ventaglio}.py`. Sono script a riga di comando: non sono dimostrabilmente morti (si lanciano a mano), ma nessun
lanciatore automatico li richiama.

**Gruppo D, perche' NON e' morto** (prova: `uscite/s02_morti.txt`, sezione D, colonna «stringhe»): `Betfair/stream/runner.py` (3.171 righe,
lanciato da `desktop/main.js:419` via watchdog, default `watchdog.py:65`), `watchdog.py` (337), `backtest/worker.py` (102, `main.js:469`),
`scalper/scalper_service.py` (982, `main.js:427`), i job del cloud (`Prediction/predictions_results_backfill.py`, `build_direzione.py`,
`cloud_retrain_shard.py`, `daily_yesterday_backfill.py`, `enrich_analytics_snapshots.py`, `generate_dc_rho.py`, `generate_dynamic_cal.py`,
`leagues_mapper.py`, `merge_engine_signals.py`, `refresh_analytics_bets.py`, `update_poisson_calibration.py`: tutti citati da `.github/workflows/*.yml`) e i
moduli `certificazione.py` del banco (mike 2.084, omega 2.160, safe 2.036, safe_tennis 1.217, scalper 2.472, tennis 1.189 righe), che il
registro del banco importa con `import_module` (`Betfair/stream/backtest/registro_bot.py:66`, `:133`) e quindi l'AST non vede.

**Import dinamici** (che l'AST non vede): `Betfair/omega/omega_service.py:8815` (`__import__`), `Betfair/safe_strategy/bot_service.py:285`,
`Betfair/stream/backtest/registro_bot.py:66,133` (`import_module`), `Betfair/safe_strategy/tools/replay_registrazioni.py:914`;
elenco completo (502 voci tra codice, test e audit) in `uscite/k02_import_dinamici.txt`.

**Limiti noti del metodo**: (1) i moduli importati con `sys.path` fuori dai pacchetti sono risolti solo come fratelli di cartella o per alias
`ai_engine`; (2) un modulo che compare solo in una stringa `-m pacchetto.modulo` e' visto dal controllo per stringa, non dall'AST;
(3) i moduli «importati» da un altro modulo a sua volta morto contano come vivi (non c'e' un calcolo di raggiungibilita' a partire dai
punti d'ingresso): per questo i morti certi sono un limite INFERIORE.


## 3. Accesso al database (Supabase)

Script: `s03_db.py` (Python via AST: `.table(`, `.from_(`, `.rpc(`, `.storage`, REST diretto `rest/v1/`; TypeScript via regex:
`.from(`, `.rpc(`) -> `uscite/s03_chiamate.tsv` (966 chiamate, una riga per chiamata con `file`, `riga`, operazione,
categoria), `s03_matrice_tabelle.tsv`, `s03_matrice_rpc.tsv`, `s03_definizioni.tsv`, `s03_riepilogo.txt`; controllo `s05_tabelle_stringa.py`
(`uscite/s05_tabelle_stringa.tsv`); tabelle markdown `g01_tabelle_md.py` (`uscite/g01_tabelle_db.md`, `g01_rpc.md`).
Limite dichiarato: la lettura/scrittura di una chiamata e' dedotta dal metodo concatenato (`.select/.insert/.upsert/.update/.delete`); dove non si
vede (`.table(x)` passato a una funzione) la chiamata e' in «op?»; i nomi non letterali sono `<dinamico:...>` (6 nomi: `table`, `tabella`, `nome`, `name`, `t`, `MU.TABELLA_ORDINI_CONTO`; i primi due 22 punti,
tutti in helper generici di `Betfair/stream/db.py:564-596`, `Betfair/omega/omega_db.py:181`, `Ai Engine/ai_engine/db_adapter.py:231`,
`football_data_scraper/backfill.py:342`, `season_aggregates.py:229-238`, `Betfair/stream/live_order_worker.py:3288-3291`,
`Betfair/stream/scalper/scalper_session.py:962`).

### 3.1 Chi parla con il DB e quanto: il confronto con il brief

Un solo client di produzione (`db_client.py:75`, uno per thread) piu' uno secondo in `tennis_db.py:22`; 5 moduli DB «per bot» (uno per bot,
con 32-53 chiamate `.table(` ciascuno) piu' chiamate sparse nei servizi. I numeri del brief (§1) tornano tutti tranne uno
(`live_order_worker.py`: brief 18, misurato 17).

```
chiamate trovate: 966
per tipo e chiamante: rest_dinamico/audit=20, rest_dinamico/prod=5, rest_dinamico/strum=2, rest_rpc/prod=1, rest_tabella/audit=2, rest_tabella/prod=1, rest_tabella/test=7, rpc/audit=4, rpc/frontend=164, rpc/prod=53, rpc/strum=2, rpc/test=16, storage/prod=7, table/audit=49, table/frontend=26, table/prod=552, table/strum=30, table/test=25
```
```
== A. `.table(` / `.from_(` PER FILE (produzione + strumenti, ordinati) - da confrontare con il brief ==
   53  Betfair/stream/db.py
   46  Betfair/safe_strategy/bot_db.py
   44  Betfair/omega/omega_db.py
   39  Betfair/stream/tennis_live/tennis_db.py
   32  Betfair/mike/db.py
   20  Betfair/stream/scalper/scalper_session.py
   18  Prediction/today_predictions_backfill.py
   17  Betfair/stream/live_order_worker.py
   16  Betfair/stream/scalper/scalper_service.py
   12  Betfair/safe_strategy/db.py
    9  season_gaps.py
    7  Betfair/betfair_report_manager.py
    7  Betfair/money_management.py
    7  Betfair/order_worker.py
    7  Betfair/stream/auto_follow.py
    7  Betfair/stream/reconcile_worker.py
    7  Betfair/stream/risk_engine_worker.py
    7  tactical_engine/serving.py
    6  market_intelligence/backtest_audit.py
    5  _certify_direction.py
    5  compute_ml_post_calibration.py
    5  enrich_analytics_snapshots.py
    5  per_fixture_backfill.py
    4  Betfair/odds_refresh.py
    4  Betfair/refresh_worker.py
    4  Betfair/stream/tennis_replay/caricamento.py
    4  Prediction/predictions_results_backfill.py
    4  api_quota.py
    4  backfill_poisson_calibrated.py
    4  build_analytics_signals.py
  brief par.1: stream/db.py 53, safe/bot_db.py 46, omega/omega_db.py 44, tennis_db.py 39, mike/db.py 32, scalper_session 20, live_order_worker 18, scalper_service 16, safe/db.py 12
```
```
== B. `.rpc(` per file (produzione) ==
    6  Betfair/omega/omega_db.py
    4  _certify_personal_report.py
    3  Betfair/stream/live_order_worker.py
    3  _certify_direction_report.py
    3  _certify_signal_context.py
    3  import_betfair_operations.py
    3  season_gaps.py
    2  Betfair/mike/db.py
    2  Betfair/safe_strategy/bot_db.py
    2  Betfair/stream/modo_ordini.py
    2  _certify_betfair.py
    2  _certify_betfair_full.py
    2  ventaglio_segnali.py
    1  Betfair/safe_strategy/db.py
    1  Betfair/stream/daily_stop_worker.py
    1  Betfair/stream/risk_engine_worker.py
    1  Betfair/stream/runner.py
    1  Betfair/stream/trading/controls.py
    1  Prediction/predictions_results_backfill.py
    1  _certify_delay_context.py
```

Lettura: i tre moduli DB dei bot di punta (`omega_db.py` 44, `bot_db.py` 46, `mike/db.py` 32) e quello dello stream (`stream/db.py` 53) hanno le
stesse operazioni sulle stesse tabelle «ordini» (scrittura in coda `betfair_live_order_requests`: `mike/db.py:683`, `omega_db.py:674`,
`bot_db.py:1029`; lettura dello specchio `betfair_live_orders`: `mike/db.py:233`, `omega_db.py:687`, `bot_db.py:1040`): vedi 4.3.

### 3.2 Matrice tabella -> file che leggono / scrivono (89 tabelle toccate da produzione o frontend, piu' i nomi dinamici)

Colonne: `definita in` = file `.sql` tracciato che crea la tabella (`migrations`/`sql`) oppure «NON nei .sql tracciati»; `chiamate prod / FE` = n.
di chiamate Python di produzione / TypeScript non di test; `scrive`/`legge` = primi 3 `file:riga` (il numero in `(+N)` e' quanti altri);
`frequenza misurata` = SOLO le tabelle presenti in `SCHEMI_BOT/sistema/MISURE_2026-10-02.md` (finestra 60 s del 02/10/2026, 15:15:40-15:16:40
UTC, chiamate al minuto per servizio; `MISURE:NN` = riga di quel file). Nessun'altra frequenza e' scritta in questo inventario.

| tabella | definita in | chiamate prod / FE | scrive (prod) | legge (prod) | FE legge / scrive | frequenza misurata 02/10 (finestra 60 s) |
|---|---|---|---|---|---|---|
| `fixture_predictions` | NON nei .sql tracciati | 72 / 6 | `AGGIORNA_CAMPO_db_json_analisi.py:178`, `Ai Engine/ai_engine/predict_fixture.py:1087`, `Prediction/backfill_historical_analysis.py:120` (+17) | `AGGIORNA_CAMPO_db_json_analisi.py:134`, `Ai Engine/ai_engine/db_adapter.py:432`, `Ai Engine/ai_engine/serving_batch.py:60` (+49) | `frontend/src/components/dashboard/FixtureSelector.tsx:30`, `frontend/src/components/dashboard/MatchesList.tsx:157` (+4) / - | safe-bot GET 1 (MISURE:142) |
| `matches` | NON nei .sql tracciati | 40 / 0 | `daily_yesterday_backfill.py:75`, `fixtures_backfill.py:135` | `Ai Engine/ai_engine/db_adapter.py:418`, `Betfair/betfair_report_manager.py:1246`, `Betfair/money_management.py:1399` (+35) | - / - | - |
| `betfair_live_order_requests` | migrations | 24 / 0 | `Betfair/mike/db.py:683`, `Betfair/omega/omega_db.py:674`, `Betfair/safe_strategy/bot_db.py:1029` (+9) | `Betfair/mike/db.py:669`, `Betfair/mike/db.py:676`, `Betfair/omega/omega_db.py:648` (+9) | - / - | runner-calcio GET 189 (MISURE:100) |
| `live_follow` | migrations | 23 / 1 | `Betfair/stream/auto_follow.py:402`, `Betfair/stream/auto_follow.py:426`, `Betfair/stream/auto_follow.py:429` (+5) | `Betfair/mike/db.py:651`, `Betfair/omega/omega_db.py:618`, `Betfair/safe_strategy/bot_db.py:989` (+12) | `frontend/src/lib/safeBot.ts:2195` / - | runner-calcio GET 29 (MISURE:103) |
| `safe_strategy_requests` | migrations | 17 / 4 | `Betfair/safe_strategy/bot_db.py:651`, `Betfair/safe_strategy/bot_db.py:659`, `Betfair/safe_strategy/bot_db.py:678` (+9) | `Betfair/safe_strategy/bot_db.py:606`, `Betfair/safe_strategy/bot_db.py:619`, `Betfair/safe_strategy/bot_db.py:632` (+2) | `frontend/src/lib/controlRoomProposte.ts:371`, `frontend/src/lib/safeBot.ts:1418` (+2) / - | safe-bot PATCH 53 (MISURE:133); safe-bot GET 44 (MISURE:134) |
| `betfair_live_orders` | migrations | 15 / 0 | `Betfair/stream/db.py:1139`, `Betfair/stream/db.py:819`, `Betfair/stream/db.py:828` (+2) | `Betfair/mike/db.py:233`, `Betfair/mike/db.py:691`, `Betfair/omega/omega_db.py:687` (+7) | - / - | runner-calcio GET 11 (MISURE:104) |
| `<dinamico:table>` | NON nei .sql tracciati | 14 / 0 | `Betfair/stream/db.py:572`, `Betfair/stream/db.py:596`, `football_data_scraper/backfill.py:342` (+3) | `Ai Engine/ai_engine/db_adapter.py:231`, `Betfair/omega/omega_db.py:181`, `Betfair/stream/db.py:564` (+5) | - / - | - |
| `safe_strategy_trades` | migrations | 14 / 0 | `Betfair/safe_strategy/bot_db.py:102`, `Betfair/safe_strategy/bot_db.py:110`, `Betfair/safe_strategy/bot_db.py:92` | `Betfair/safe_strategy/bot_db.py:122`, `Betfair/safe_strategy/bot_db.py:129`, `Betfair/safe_strategy/bot_db.py:172` (+8) | - / - | safe-bot GET 81 (MISURE:132) |
| `ai_model_registry` | NON nei .sql tracciati | 12 / 0 | `Ai Engine/ai_engine/seriea_model_export.py:686`, `Ai Engine/ai_engine/seriea_model_export.py:689`, `Betfair/betfair_report_manager.py:1299` (+2) ; op?: `cloud_retrain_shard.py:77` | `Ai Engine/ai_engine/predict_fixture.py:512`, `Betfair/betfair_report_manager.py:1224`, `Betfair/betfair_report_manager.py:1319` (+4) | - / - | - |
| `omega_events` | migrations | 11 / 0 | `Betfair/omega/omega_db.py:1017`, `Betfair/omega/omega_db.py:303`, `Betfair/omega/omega_db.py:442` (+4) | `Betfair/omega/omega_db.py:486`, `Betfair/omega/omega_db.py:526`, `Betfair/omega/omega_db.py:564` (+1) | - / - | safe-bot GET 1 (MISURE:141) |
| `safe_strategy_scan` | migrations | 10 / 1 | `Betfair/safe_strategy/db.py:198`, `Betfair/safe_strategy/db.py:213` | `Betfair/mike/db.py:560`, `Betfair/safe_strategy/bot_db.py:961`, `Betfair/safe_strategy/db.py:50` (+5) | `frontend/src/lib/safeStrategyScan.ts:343` / - | scanner POST 68 (MISURE:162); mike GET 14 (MISURE:67); runner-calcio GET 8 (MISURE:106); safe-bot GET 5 (MISURE:139); scanner GET 1 (MISURE:166) |
| `scalper_control` | migrations | 11 / 0 | `Betfair/stream/scalper/scalper_service.py:195`, `Betfair/stream/scalper/scalper_service.py:197`, `Betfair/stream/scalper/scalper_service.py:208` (+2) | `Betfair/stream/scalper/scalper_service.py:147`, `Betfair/stream/scalper/scalper_service.py:214`, `Betfair/stream/scalper/scalper_service.py:75` (+3) | - / - | scalper GET 18 (MISURE:179) |
| `live_now` | migrations | 9 / 1 | `Betfair/stream/db.py:348`, `Betfair/stream/db.py:362`, `Betfair/stream/db.py:528` | `Betfair/omega/omega_db.py:595`, `Betfair/stream/db.py:513`, `Betfair/stream/live_order_worker.py:1105` (+3) | `frontend/src/lib/live.ts:140` / - | - |
| `omega_trades` | migrations | 10 / 0 | `Betfair/omega/omega_db.py:76`, `Betfair/omega/omega_db.py:86`, `Betfair/omega/omega_db.py:94` | `Betfair/omega/omega_db.py:1031`, `Betfair/omega/omega_db.py:253`, `Betfair/omega/omega_db.py:722` (+4) | - / - | omega GET 4 (MISURE:86) |
| `season_backfill_state` | NON nei .sql tracciati | 10 / 0 | `season_gaps.py:522`, `season_gaps.py:531`, `season_gaps.py:559` (+2) | `retrain_all_leagues.py:125`, `season_gaps.py:546`, `season_gaps.py:595` (+2) | - / - | - |
| `tennis_bot_control` | migrations | 10 / 0 | `Betfair/stream/tennis_live/tennis_db.py:214`, `Betfair/stream/tennis_live/tennis_db.py:444`, `Betfair/stream/tennis_live/tennis_db.py:451` (+6) | `Betfair/stream/tennis_live/tennis_db.py:399` | - / - | tennis-bot-svc GET 18 (MISURE:189) |
| `live_alerts` | migrations | 9 / 0 | `Betfair/stream/db.py:697`, `Betfair/stream/live_order_worker.py:1071`, `Betfair/stream/motore_ordini.py:2431` (+6) | - | - / - | - |
| `tennis_live_order_queue` | migrations | 9 / 0 | `Betfair/stream/tennis_live/esecutore_tennis.py:266`, `Betfair/stream/tennis_live/tennis_db.py:549`, `Betfair/stream/tennis_live/tennis_db.py:568` (+4) | `Betfair/stream/tennis_live/tennis_db.py:351`, `Betfair/stream/tennis_live/tennis_db.py:535` | - / - | - |
| `mike_trades` | migrations | 8 / 0 | `Betfair/mike/db.py:176`, `Betfair/mike/db.py:186` | `Betfair/mike/db.py:192`, `Betfair/mike/db.py:202`, `Betfair/mike/db.py:211` (+3) | - / - | mike GET 116 (MISURE:63) |
| `safe_strategy_status` | migrations | 7 / 1 | `Betfair/safe_strategy/db.py:228` | `Betfair/mike/db.py:569`, `Betfair/safe_strategy/bot_db.py:973`, `Betfair/stream/auto_follow.py:466` (+3) | `frontend/src/lib/safeStrategyScan.ts:350` / - | scanner POST 5 (MISURE:165); safe-bot GET 5 (MISURE:138); runner-calcio GET 2 (MISURE:108) |
| `<dinamico:tabella>` | NON nei .sql tracciati | 7 / 0 | `Betfair/stream/db.py:1114` | `Betfair/mike/db.py:230`, `Betfair/mike/db.py:599`, `Betfair/safe_strategy/db.py:473` (+3) | - / - | - |
| `api_coverage_by_season` | NON nei .sql tracciati | 7 / 0 | `leagues_mapper.py:325`, `leagues_mapper.py:350` | `Prediction/today_predictions_backfill.py:754`, `Prediction/today_predictions_backfill.py:796`, `leagues_mapper.py:96` (+2) | - / - | - |
| `betfair_live_risk_rules` | migrations | 7 / 0 | `Betfair/stream/risk_engine_worker.py:189` | `Betfair/stream/reconcile_worker.py:1264`, `Betfair/stream/risk_engine_worker.py:1096`, `Betfair/stream/risk_engine_worker.py:1173` (+3) | - / - | runner-calcio GET 168 (MISURE:101) |
| `betfair_market_odds` | migrations | 7 / 0 | `Betfair/odds_refresh.py:254`, `Betfair/odds_refresh.py:257`, `betfair_full_odds.py:73` (+1) | `Betfair/odds_refresh.py:224`, `Betfair/order_exec.py:161`, `_certify_betfair_full.py:13` | - / - | - |
| `betfair_order_requests` | migrations | 7 / 0 | `Betfair/order_worker.py:106`, `Betfair/order_worker.py:113`, `Betfair/order_worker.py:120` (+2) | `Betfair/order_worker.py:136`, `Betfair/order_worker.py:61` | - / - | - |
| `omega_manual_requests` | migrations | 7 / 0 | `Betfair/omega/omega_db.py:297`, `Betfair/omega/omega_db.py:323`, `Betfair/omega/omega_db.py:394` (+2) | `Betfair/omega/omega_db.py:283`, `Betfair/omega/omega_db.py:373` | - / - | - |
| `tennis_live_now` | migrations | 6 / 1 | `Betfair/stream/tennis_live/tennis_db.py:292`, `Betfair/stream/tennis_live/tennis_db.py:306`, `Betfair/stream/tennis_live/tennis_db.py:313` (+1) | `Betfair/stream/tennis_live/tennis_db.py:198`, `Betfair/stream/tennis_live/tennis_db.py:369` | `frontend/src/lib/tennis.ts:209` / - | - |
| `analytics_signals` | migrations | 6 / 0 | `build_analytics_signals.py:402`, `fix_storico_prob.py:59` | `_certify_direction_report.py:85`, `enrich_analytics_snapshots.py:265`, `enrich_analytics_snapshots.py:485` (+1) | - / - | - |
| `api_call_log` | NON nei .sql tracciati | 6 / 0 | `logger.py:86`, `logger.py:91` | `api_quota.py:144`, `api_quota.py:149`, `api_quota.py:169` (+1) | - / - | - |
| `betfair_live_heartbeat` | migrations | 4 / 2 | `Betfair/stream/db.py:1127` | `Betfair/mike/db.py:657`, `Betfair/omega/omega_db.py:628`, `Betfair/safe_strategy/bot_db.py:997` | `frontend/src/lib/liveOrders.ts:1034`, `frontend/src/lib/safeBot.ts:2183` / - | runner-calcio POST 8 (MISURE:107) |
| `mike_events` | migrations | 6 / 0 | `Betfair/mike/db.py:141`, `Betfair/mike/db.py:164`, `Betfair/mike/db.py:169` | `Betfair/mike/db.py:108`, `Betfair/mike/db.py:117`, `Betfair/safe_strategy/db.py:307` | - / - | mike POST 25 (MISURE:66); scanner GET 6 (MISURE:163); mike GET 1 (MISURE:71) |
| `mike_requests` | migrations | 5 / 1 | `Betfair/mike/db.py:509`, `Betfair/mike/db.py:516` | `Betfair/mike/db.py:463`, `Betfair/mike/db.py:490`, `Betfair/mike/db.py:533` | `frontend/src/lib/mike.ts:2301` / - | mike GET 58 (MISURE:65) |
| `betfair_live_positions` | migrations | 5 / 0 | `Betfair/stream/db.py:1140`, `Betfair/stream/db.py:940`, `Betfair/stream/db.py:945` | `Betfair/stream/db.py:451`, `Betfair/stream/db.py:481` | - / - | - |
| `engine_signals` | migrations | 5 / 0 | `migrations/backfill_engine_signals.py:278` | `_certify_betfair.py:24`, `_certify_direction_report.py:103`, `_certify_direction_report.py:139` (+1) | - / - | - |
| `match_odds` | NON nei .sql tracciati | 5 / 0 | `football_data_scraper/fix_snapshot_time.py:45` | `football_data_scraper/backfill.py:102`, `market_intelligence/backtest_audit.py:124`, `market_intelligence/backtest_audit.py:138` (+1) | - / - | - |
| `ml_post_calibration` | NON nei .sql tracciati | 5 / 0 | `compute_ml_post_calibration.py:244`, `compute_ml_post_calibration.py:259` | `Ai Engine/ai_engine/predict_fixture.py:386`, `compute_ml_post_calibration.py:123`, `compute_ml_post_calibration.py:256` | - / - | - |
| `tennis_live_follow` | migrations | 5 / 0 | `Betfair/stream/tennis_live/tennis_db.py:118`, `Betfair/stream/tennis_live/tennis_db.py:231` | `Betfair/stream/tennis_live/tennis_db.py:240`, `Betfair/stream/tennis_live/tennis_db.py:377`, `Betfair/stream/tennis_replay/importa.py:78` | - / - | runner-tennis GET 28 (MISURE:126); tennis-bot-svc GET 3 (MISURE:192) |
| `bet_features` | migrations | 4 / 0 | - | `_league_eval.py:43`, `_stack_eval.py:42`, `build_direzione.py:79` (+1) | - / - | - |
| `betfair_live_account` | migrations | 3 / 1 | `Betfair/stream/db.py:1004`, `Betfair/stream/db.py:1055`, `Betfair/stream/db.py:1086` | - | `frontend/src/lib/liveOrders.ts:981` / - | runner-calcio POST 2 (MISURE:109) |
| `betfair_refresh_requests` | migrations | 4 / 0 | `Betfair/refresh_worker.py:59`, `Betfair/refresh_worker.py:66`, `Betfair/refresh_worker.py:73` | `Betfair/refresh_worker.py:38` | - / - | - |
| `direction_pagella` | migrations | 4 / 0 | `build_direzione.py:226`, `build_direzione.py:230` | `_certify_direction.py:39`, `build_direzione.py:232` | - / - | - |
| `match_team_stats` | NON nei .sql tracciati | 4 / 0 | - | `football_data_scraper/backfill.py:147`, `market_intelligence/audit.py:83`, `market_intelligence/edge_scorer.py:472` (+1) | - / - | - |
| `safe_strategy_opportunities` | migrations | 3 / 1 | `Betfair/safe_strategy/bot_db.py:879`, `Betfair/safe_strategy/bot_db.py:891`, `Betfair/safe_strategy/bot_db.py:903` | - | `frontend/src/lib/safeBot.ts:1544` / - | safe-bot POST 4 (MISURE:140); safe-bot DELETE 1 (MISURE:143) |
| `scalper_activity` | migrations | 4 / 0 | `Betfair/stream/scalper/scalper_service.py:86`, `Betfair/stream/scalper/scalper_service.py:890`, `Betfair/stream/scalper/scalper_session.py:1270` (+1) | - | - / - | - |
| `tennis_markets` | migrations | 4 / 0 | `betfair_tennis_odds.py:274`, `betfair_tennis_odds.py:278` | `Betfair/stream/tennis_live/tennis_bot_service.py:151`, `Betfair/stream/tennis_replay/importa.py:82` | - / - | tennis-odds DELETE+POST 2+2 in 29,8 min (MISURE:203) |
| `betfair_live_settled` | migrations | 3 / 0 | `Betfair/stream/db.py:963` | `Betfair/stream/daily_stop_worker.py:250`, `Betfair/stream/db.py:425` | - / - | runner-calcio GET 11 (MISURE:105) |
| `live_backtest_requests` | migrations | 3 / 0 | `Betfair/stream/db.py:726`, `Betfair/stream/db.py:741` | `Betfair/stream/db.py:714` | - / - | - |
| `live_signals` | migrations | 2 / 1 | `Betfair/stream/db.py:662` | `Betfair/stream/live_order_worker.py:999` | `frontend/src/lib/live.ts:560` / - | - |
| `match_events` | NON nei .sql tracciati | 3 / 0 | - | `build_analytics_signals.py:376`, `build_inplay_intensity.py:88`, `value_engine/calibrate.py:37` | - / - | - |
| `omega_missions` | migrations | 3 / 0 | `Betfair/omega/omega_db.py:717` | `Betfair/omega/omega_db.py:699`, `Betfair/omega/omega_db.py:708` | - / - | - |
| `poisson_calibration` | migrations | 3 / 0 | `generate_dynamic_cal.py:459`, `load_poisson_calibration_to_db.py:65` | `poisson_calibrator.py:100` | - / - | - |
| `safe_strategy_activity` | migrations | 2 / 1 | `Betfair/safe_strategy/bot_db.py:79` | `Betfair/safe_strategy/bot_db.py:436` | `frontend/src/lib/safeBot.ts:1206` / - | - |
| `tennis_live_orders` | migrations | 3 / 0 | `Betfair/stream/tennis_live/tennis_db.py:604`, `Betfair/stream/tennis_live/tennis_db.py:854` | `Betfair/stream/tennis_live/tennis_db.py:335` | - / - | - |
| `tennis_live_positions` | migrations | 3 / 0 | `Betfair/stream/tennis_live/tennis_db.py:627`, `Betfair/stream/tennis_live/tennis_db.py:863` | `Betfair/stream/tennis_live/tennis_db.py:342` | - / - | - |
| `theta_confirm_requests` | migrations | 3 / 0 | `Betfair/stream/scalper/scalper_session.py:1936`, `Betfair/stream/scalper/scalper_session.py:1958` | `Betfair/stream/scalper/scalper_session.py:1947` | - / - | - |
| `<dinamico:nome>` | NON nei .sql tracciati | 2 / 0 | `season_aggregates.py:229`, `season_aggregates.py:238` | - | - / - | - |
| `analytics_snap_staging` | migrations | 2 / 0 | `enrich_analytics_snapshots.py:293`, `enrich_analytics_snapshots.py:336` | - | - / - | - |
| `betfair_live_audit` | migrations | 2 / 0 | `Betfair/stream/daily_stop_worker.py:391`, `Betfair/stream/live_order_worker.py:922` | - | - / - | - |
| `betfair_live_journal` | migrations | 2 / 0 | `Betfair/stream/db.py:988`, `Betfair/stream/live_order_worker.py:1134` | - | - / - | - |
| `betfair_live_risk_state` | migrations | 1 / 1 | `Betfair/stream/db.py:978` | - | `frontend/src/lib/liveOrders.ts:795` / - | - |
| `betfair_live_xhedge` | migrations | 2 / 0 | `Betfair/stream/xhedge_worker.py:119` | `Betfair/stream/risk_engine_worker.py:1001` | - / - | - |
| `injuries` | NON nei .sql tracciati | 2 / 0 | `injuries_backfill.py:209`, `injuries_backfill.py:259` | - | - / - | - |
| `live_backtest_results` | migrations | 2 / 0 | `Betfair/stream/db.py:758`, `Betfair/stream/db.py:762` | - | - / - | - |
| `live_ladder` | migrations | 1 / 1 | `Betfair/stream/db.py:682` | - | `frontend/src/lib/live.ts:621` / - | - |
| `live_markets` | migrations | 2 / 0 | `Betfair/stream/db.py:314` | `Betfair/stream/db.py:404` | - / - | - |
| `mike_control` | migrations | 2 / 0 | `Betfair/mike/db.py:68` | `Betfair/mike/db.py:60` | - / - | mike GET 58 (MISURE:64); mike PATCH 2 (MISURE:69) |
| `omega_control` | migrations | 2 / 0 | `Betfair/omega/omega_db.py:58` | `Betfair/omega/omega_db.py:50` | - / - | omega GET 1 (MISURE:87) |
| `personal_watchlist` | migrations | 2 / 0 | - | `Betfair/stream/db.py:114`, `Betfair/stream/watchlist.py:29` | - / - | runner-calcio GET 1 (MISURE:110) |
| `safe_strategy_control` | migrations | 2 / 0 | `Betfair/safe_strategy/bot_db.py:74` | `Betfair/safe_strategy/bot_db.py:64` | - / - | safe-bot GET 36 (MISURE:135); safe-bot PATCH 19 (MISURE:137) |
| `scalper_service_control` | migrations | 2 / 0 | `Betfair/stream/scalper/scalper_service.py:102` | `Betfair/stream/scalper/scalper_service.py:94` | - / - | scalper GET 18 (MISURE:181) |
| `signal_history` | migrations | 2 / 0 | `Betfair/money_management.py:2434`, `Betfair/money_management.py:2471` | - | - / - | - |
| `standings` | NON nei .sql tracciati | 2 / 0 | `standings_backfill.py:239`, `standings_backfill.py:289` | - | - / - | - |
| `tennis_bot_service_control` | migrations | 2 / 0 | `Betfair/stream/tennis_live/tennis_db.py:710` | `Betfair/stream/tennis_live/tennis_db.py:662` | - / - | tennis-bot-svc PATCH 12 (MISURE:190); tennis-bot-svc GET 3 (MISURE:191) |
| `tennis_live_ladder` | migrations | 1 / 1 | `Betfair/stream/tennis_live/tennis_db.py:260` | - | `frontend/src/lib/tennis.ts:263` / - | - |
| `tennis_replay_eventi` | migrations | 2 / 0 | `Betfair/stream/tennis_replay/caricamento.py:108`, `Betfair/stream/tennis_replay/caricamento.py:75` | - | - / - | - |
| `tennis_replay_mercati` | migrations | 2 / 0 | `Betfair/stream/tennis_replay/caricamento.py:79` | `Betfair/stream/tennis_replay/caricamento.py:97` | - / - | - |
| `top_assists` | NON nei .sql tracciati | 2 / 0 | `top_assists_backfill.py:235`, `top_assists_backfill.py:285` | - | - / - | - |
| `top_cards` | NON nei .sql tracciati | 2 / 0 | `top_cards_backfill.py:244`, `top_cards_backfill.py:294` | - | - / - | - |
| `top_scorers` | NON nei .sql tracciati | 2 / 0 | `top_scorers_backfill.py:235`, `top_scorers_backfill.py:285` | - | - / - | - |
| `<dinamico:MU.TABELLA_ORDINI_CONTO>` | NON nei .sql tracciati | 1 / 0 | - | `Betfair/stream/scalper/scalper_session.py:962` | - / - | - |
| `<dinamico:name>` | NON nei .sql tracciati | 1 / 0 | - ; op?: `Betfair/stream/live_order_worker.py:3288` | - | - / - | - |
| `<dinamico:t>` | NON nei .sql tracciati | 1 / 0 | `per_fixture_backfill.py:219` | - | - / - | - |
| `analytics_bets` | migrations | 1 / 0 | - | `_certify_direction.py:174` | - / - | - |
| `analytics_decisions` | migrations | 1 / 0 | - | `certify_backtest_strategy.py:103` | - / - | - |
| `fixture_detail_checks` | migrations | 1 / 0 | - | `season_gaps.py:445` | - / - | - |
| `leads` | NON nei .sql tracciati | 0 / 1 | - | - | - / `frontend/src/components/landing/AuthSection.tsx:74` | - |
| `live_run_log` | migrations | 1 / 0 | `Betfair/stream/db.py:644` | - | - / - | - |
| `mike_activity` | migrations | 1 / 0 | `Betfair/mike/db.py:76` | - | - / - | mike POST 2 (MISURE:70) |
| `model_performance` | NON nei .sql tracciati | 1 / 0 | `retrain_all_leagues.py:363` | - | - / - | - |
| `omega_activity` | migrations | 1 / 0 | `Betfair/omega/omega_db.py:63` | - | - / - | - |
| `omega_daily_goal` | migrations | 1 / 0 | `Betfair/omega/omega_db.py:1045` | - | - / - | - |
| `omega_market_snapshot` | migrations | 1 / 0 | `Betfair/omega/omega_db.py:482` | - | - / - | - |
| `personal_trades` | migrations | 1 / 0 | `_certify_personal_report.py:325` | - | - / - | - |
| `replay_bot_esiti` | migrations | 1 / 0 | `Betfair/stream/db.py:752` | - | - / - | - |
| `tennis_bot_activity` | migrations | 1 / 0 | `Betfair/stream/tennis_live/tennis_db.py:518` | - | - / - | - |

### 3.3 RPC (funzioni del database)

170 RPC distinte chiamate da produzione o frontend (`s03_riepilogo.txt`, sezione D); 150 dal frontend (`f01_frontend.py`). Frequenze misurate solo per
5 RPC (`MISURE:102`, `:136`, `:164`, `:68`, `:95`).

| RPC | definita | prod (n) | primo file prod | FE (n) | primo file FE | frequenza misurata |
|---|---|---|---|---|---|---|
| `ack_alert` | migrations | 0 | - | 1 | `frontend/src/lib/live.ts:691` | - |
| `add_personal_trade` | migrations | 1 | `_certify_personal_report.py:359` | 1 | `frontend/src/lib/personalReport.ts:325` | - |
| `add_to_watchlist` | migrations | 0 | - | 1 | `frontend/src/lib/watchlist.ts:110` | - |
| `add_trade_leg` | migrations | 0 | - | 1 | `frontend/src/lib/personalReport.ts:333` | - |
| `backtest_strategy` | migrations | 1 | `certify_backtest_strategy.py:171` | 1 | `frontend/src/lib/analytics.ts:328` | - |
| `betfair_live_is_owner` | migrations | 0 | - | 1 | `frontend/src/certification/realClient.ts:146` | - |
| `bulk_update_prediction_results` | migrations | 1 | `Prediction/predictions_results_backfill.py:671` | 0 | - | - |
| `cancel_live_risk_rule` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:494` | - |
| `delete_from_watchlist` | migrations | 0 | - | 1 | `frontend/src/lib/watchlist.ts:126` | - |
| `delete_strategy` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:346` | - |
| `fetch_missing_fixture_coverage` | NON nei .sql | 1 | `missing_fixtures_backfill.py:47` | 0 | - | - |
| `flush_analytics_snap_staging` | migrations | 1 | `enrich_analytics_snapshots.py:312` | 0 | - | - |
| `get_analytics` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:106` | - |
| `get_analytics_filters` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:81` | - |
| `get_analytics_rows` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:115` | - |
| `get_betfair_direction_odds` | migrations | 1 | `_certify_betfair_full.py:28` | 1 | `frontend/src/lib/betfair.ts:53` | - |
| `get_betfair_fixtures` | migrations | 1 | `_certify_betfair.py:42` | 1 | `frontend/src/lib/betfair.ts:23` | - |
| `get_betfair_full_odds` | migrations | 1 | `_certify_betfair_full.py:21` | 1 | `frontend/src/lib/betfair.ts:44` | - |
| `get_betfair_live_order` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:143` | - |
| `get_betfair_odds` | migrations | 1 | `_certify_betfair.py:59` | 1 | `frontend/src/lib/betfair.ts:32` | - |
| `get_betfair_order_request` | migrations | 0 | - | 1 | `frontend/src/lib/betfair.ts:177` | - |
| `get_betfair_orders` | migrations | 0 | - | 1 | `frontend/src/lib/betfair.ts:238` | - |
| `get_betfair_refresh_request` | migrations | 0 | - | 1 | `frontend/src/lib/betfair.ts:90` | - |
| `get_cash_movements` | migrations | 0 | - | 1 | `frontend/src/lib/personalReport.ts:370` | - |
| `get_decisions` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:180` | - |
| `get_decisions_filters` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:175` | - |
| `get_direction` | migrations | 3 | `_certify_direction.py:207` (+2) | 1 | `frontend/src/lib/direzione.ts:50` | - |
| `get_direction_eta` | migrations | 0 | - | 1 | `frontend/src/lib/direzione.ts:73` | - |
| `get_direction_report` | migrations | 1 | `_certify_direction_report.py:509` | 1 | `frontend/src/lib/reportistiche.ts:140` | - |
| `get_direction_report_fixture` | migrations | 1 | `_certify_direction_report.py:480` | 1 | `frontend/src/lib/reportistiche.ts:180` | - |
| `get_direction_report_matches` | migrations | 1 | `_certify_direction_report.py:518` | 1 | `frontend/src/lib/reportistiche.ts:147` | - |
| `get_league_seasons` | sql | 0 | - | 1 | `frontend/src/lib/marketFrequency.ts:168` | - |
| `get_live_alerts` | migrations | 0 | - | 1 | `frontend/src/lib/live.ts:668` | - |
| `get_live_audit` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:712` | - |
| `get_live_follows` | migrations | 0 | - | 1 | `frontend/src/lib/live.ts:37` | - |
| `get_live_journal` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:915` | - |
| `get_live_orders` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:510` | - |
| `get_live_orders_account_open` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:851` | - |
| `get_live_positions` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:518` | - |
| `get_live_positions_all` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:862` | - |
| `get_live_positions_event` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:869` | - |
| `get_live_risk_rules` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:501` | - |
| `get_live_settings` | migrations | 4 | `Betfair/stream/live_order_worker.py:498` (+3) | 1 | `frontend/src/lib/liveOrders.ts:676` | runner-calcio 123/min (MISURE:102), scalper 18/min (MISURE:180) |
| `get_live_settled` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:769` | - |
| `get_live_xhedge` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:615` | - |
| `get_market_delays` | migrations | 4 | `_certify_signal_context.py:77` (+3) | 1 | `frontend/src/lib/marketDelays.ts:134` | - |
| `get_market_frequency` | sql | 4 | `Betfair/omega/omega_db.py:767` (+3) | 1 | `frontend/src/lib/marketFrequency.ts:154` | - |
| `get_mike_aggregates` | migrations | 1 | `Betfair/mike/db.py:409` | 0 | - | mike 3/min (MISURE:68) |
| `get_mike_daily` | migrations | 0 | - | 1 | `frontend/src/lib/dailyHistory.ts:412` | - |
| `get_mike_day_trades` | migrations | 0 | - | 1 | `frontend/src/lib/dailyHistory.ts:420` | - |
| `get_mike_state` | migrations | 0 | - | 1 | `frontend/src/lib/mike.ts:2248` | - |
| `get_mike_trades` | migrations | 0 | - | 1 | `frontend/src/lib/mike.ts:2268` | - |
| `get_omega_aggregates` | migrations | 1 | `Betfair/omega/omega_db.py:875` | 0 | - | - |
| `get_omega_aggregates_modalita` | migrations | 1 | `Betfair/omega/omega_db.py:823` | 0 | - | omega 4 in 5 min (MISURE:95) |
| `get_omega_daily` | migrations | 0 | - | 3 | `frontend/src/lib/dailyHistory.ts:270` (+2) | - |
| `get_omega_day_trades` | migrations | 0 | - | 3 | `frontend/src/lib/dailyHistory.ts:301` (+2) | - |
| `get_omega_events` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1507` | - |
| `get_omega_ht_ft` | migrations | 1 | `Betfair/omega/omega_db.py:1060` | 0 | - | - |
| `get_omega_manual_requests` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1568` | - |
| `get_omega_market` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1562` | - |
| `get_omega_minute_ft` | migrations | 1 | `Betfair/omega/omega_db.py:1073` | 0 | - | - |
| `get_omega_missions` | migrations | 0 | - | 1 | `frontend/src/lib/omegaMissions.ts:198` | - |
| `get_omega_proposte` | migrations | 0 | - | 1 | `frontend/src/lib/omegaProposte.ts:292` | - |
| `get_omega_state` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1343` | - |
| `get_omega_trades` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1362` | - |
| `get_personal_report` | migrations | 2 | `_certify_personal_report.py:387` (+1) | 1 | `frontend/src/lib/personalReport.ts:388` | - |
| `get_personal_trades` | migrations | 0 | - | 1 | `frontend/src/lib/personalReport.ts:410` | - |
| `get_poisson_calibration_eta` | migrations | 0 | - | 1 | `frontend/src/lib/fixtureModels.ts:89` | - |
| `get_replay` | migrations | 0 | - | 1 | `frontend/src/lib/live.ts:339` | - |
| `get_replay_bot_esito` | migrations | 0 | - | 1 | `frontend/src/lib/replayBot.ts:236` | - |
| `get_replay_meta` | migrations | 0 | - | 2 | `frontend/src/lib/live.ts:433` (+1) | - |
| `get_replay_tennis_meta` | migrations | 0 | - | 1 | `frontend/src/lib/tennisReplay.ts:124` | - |
| `get_safe_activity` | migrations | 0 | - | 1 | `frontend/src/lib/safeBot.ts:1201` | - |
| `get_safe_aggregates` | migrations | 1 | `Betfair/safe_strategy/bot_db.py:336` | 1 | `frontend/src/lib/safeBot.ts:369` | safe-bot 19/min (MISURE:136) |
| `get_safe_daily` | migrations | 0 | - | 1 | `frontend/src/lib/dailyHistory.ts:293` | - |
| `get_safe_day_trades` | migrations | 0 | - | 1 | `frontend/src/lib/dailyHistory.ts:397` | - |
| `get_safe_state` | migrations | 0 | - | 1 | `frontend/src/lib/safeBot.ts:1177` | - |
| `get_safe_trades` | migrations | 0 | - | 1 | `frontend/src/lib/safeBot.ts:1215` | - |
| `get_scalper_control_room` | migrations | 0 | - | 1 | `frontend/src/lib/scalperControlRoom.ts:140` | - |
| `get_scalper_state` | migrations | 0 | - | 1 | `frontend/src/lib/scalper.ts:168` | - |
| `get_storico_stake` | migrations | 0 | - | 1 | `frontend/src/lib/dailyHistory.ts:371` | - |
| `get_tennis_bot_daily` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:1080` | - |
| `get_tennis_bot_orders_today` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:1124` | - |
| `get_tennis_bot_services` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:981` | - |
| `get_tennis_bots_state` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:837` | - |
| `get_tennis_fixtures` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:82` | - |
| `get_tennis_follows` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:168` | - |
| `get_tennis_full_odds` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:108` | - |
| `get_tennis_live_order` | migrations | 0 | - | 2 | `frontend/src/lib/tennis.ts:437` (+1) | - |
| `get_tennis_live_orders` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:506` | - |
| `get_tennis_live_positions` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:517` | - |
| `get_tennis_live_positions_all` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:571` | - |
| `get_tennis_refresh_request` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:129` | - |
| `get_watchlist` | migrations | 0 | - | 1 | `frontend/src/lib/watchlist.ts:117` | - |
| `leagues_needing_retrain` | sql | 1 | `training_planner.py:152` | 0 | - | - |
| `list_backtest_results` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:473` | - |
| `list_backtest_runs` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:463` | - |
| `list_bot_exposures` | migrations | 1 | `Betfair/safe_strategy/db.py:432` | 0 | - | scanner 6/min (MISURE:164) |
| `list_replays` | migrations | 0 | - | 1 | `frontend/src/lib/live.ts:193` | - |
| `list_replays_tennis` | migrations | 0 | - | 1 | `frontend/src/lib/tennisReplay.ts:114` | - |
| `list_strategies` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:334` | - |
| `live_order_mode_avvio` | migrations | 1 | `Betfair/stream/modo_ordini.py:391` | 0 | - | - |
| `mike_activate` | migrations | 0 | - | 1 | `frontend/src/lib/mike.ts:2228` | - |
| `mike_request` | migrations | 0 | - | 1 | `frontend/src/lib/mike.ts:2274` | - |
| `mike_stop` | migrations | 0 | - | 1 | `frontend/src/lib/mike.ts:2234` | - |
| `mike_update_params` | migrations | 0 | - | 1 | `frontend/src/lib/mike.ts:2240` | - |
| `omega_activate` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1317` | - |
| `omega_eventi_chiusi_dall_utente` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1398` | - |
| `omega_evento_riprendi` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1421` | - |
| `omega_mission_activate` | migrations | 0 | - | 1 | `frontend/src/lib/omegaMissions.ts:150` | - |
| `omega_mission_follow` | migrations | 0 | - | 1 | `frontend/src/lib/omegaMissions.ts:174` | - |
| `omega_mission_stop` | migrations | 0 | - | 1 | `frontend/src/lib/omegaMissions.ts:162` | - |
| `omega_request` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1501` | - |
| `omega_request_approve` | migrations | 0 | - | 1 | `frontend/src/lib/omegaProposte.ts:338` | - |
| `omega_request_ignore` | migrations | 0 | - | 1 | `frontend/src/lib/omegaProposte.ts:348` | - |
| `omega_stop` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1325` | - |
| `omega_update_params` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1333` | - |
| `record_fixture_detail_checks` | migrations | 1 | `season_gaps.py:455` | 0 | - | - |
| `refresh_analytics_bets_range` | migrations | 1 | `refresh_analytics_bets.py:197` | 0 | - | - |
| `request_backtest` | migrations | 0 | - | 2 | `frontend/src/lib/analytics.ts:456` (+1) | - |
| `request_betfair_live_order` | migrations | 5 | `Betfair/mike/db.py:663` (+4) | 1 | `frontend/src/lib/liveOrders.ts:133` | - |
| `request_betfair_order` | migrations | 0 | - | 1 | `frontend/src/lib/betfair.ts:167` | - |
| `request_betfair_refresh` | migrations | 0 | - | 1 | `frontend/src/lib/betfair.ts:81` | - |
| `request_live_risk_rule` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:483` | - |
| `request_tennis_live_order` | migrations | 0 | - | 2 | `frontend/src/lib/tennis.ts:422` (+1) | - |
| `request_tennis_refresh` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:123` | - |
| `reset_personal_report` | migrations | 0 | - | 1 | `frontend/src/lib/personalReport.ts:403` | - |
| `rpc` | NON nei .sql | 1 | `ventaglio_segnali.py:66` | 0 | - | - |
| `run_strategy` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:351` | - |
| `run_strategy_rows` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:385` | - |
| `safe_activate` | migrations | 0 | - | 1 | `frontend/src/lib/safeBot.ts:1147` | - |
| `safe_request` | migrations | 0 | - | 1 | `frontend/src/lib/safeBot.ts:1224` | - |
| `safe_request_approve` | migrations | 0 | - | 2 | `frontend/src/lib/controlRoomProposte.ts:400` (+1) | - |
| `safe_request_ignore` | migrations | 0 | - | 1 | `frontend/src/lib/controlRoomProposte.ts:409` | - |
| `safe_stop` | migrations | 0 | - | 1 | `frontend/src/lib/safeBot.ts:1155` | - |
| `safe_update_params` | migrations | 0 | - | 1 | `frontend/src/lib/safeBot.ts:1161` | - |
| `save_strategy` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:340` | - |
| `scalper_activate` | migrations | 0 | - | 1 | `frontend/src/lib/scalper.ts:148` | - |
| `scalper_approva_uscita` | migrations | 0 | - | 1 | `frontend/src/lib/proposteUscite.ts:90` | - |
| `scalper_auto_activate` | migrations | 0 | - | 1 | `frontend/src/lib/scalperControlRoom.ts:166` | - |
| `scalper_auto_stop` | migrations | 0 | - | 1 | `frontend/src/lib/scalperControlRoom.ts:177` | - |
| `scalper_auto_update` | migrations | 0 | - | 1 | `frontend/src/lib/scalperControlRoom.ts:188` | - |
| `scalper_media_attiva_adesso` | migrations | 0 | - | 1 | `frontend/src/lib/mediaUnderAttiva.ts:17` | - |
| `scalper_stop` | migrations | 0 | - | 1 | `frontend/src/lib/scalper.ts:160` | - |
| `scalper_stop_sessione` | migrations | 0 | - | 1 | `frontend/src/lib/scalperControlRoom.ts:298` | - |
| `scalper_uscite_automatiche` | migrations | 0 | - | 1 | `frontend/src/lib/scalperControlRoom.ts:313` | - |
| `season_aggregates_summary` | migrations | 1 | `season_aggregates.py:151` | 0 | - | - |
| `season_detail_gaps` | migrations | 1 | `season_gaps.py:228` | 0 | - | - |
| `season_gaps_summary` | migrations | 1 | `season_gaps.py:345` | 0 | - | - |
| `segui_live_apri_partita` | migrations | 0 | - | 1 | `frontend/src/lib/live.ts:51` | - |
| `set_follow_record` | migrations | 0 | - | 1 | `frontend/src/lib/omegaMissions.ts:190` | - |
| `set_live_journal_note` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:932` | - |
| `set_live_kill_switch` | migrations | 1 | `Betfair/stream/daily_stop_worker.py:363` | 1 | `frontend/src/lib/liveOrders.ts:684` | - |
| `set_live_order_mode` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:693` | - |
| `set_live_settings` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:705` | - |
| `set_trade_time_operative` | migrations | 0 | - | 1 | `frontend/src/lib/personalReport.ts:378` | - |
| `set_watchlist_decision` | migrations | 0 | - | 1 | `frontend/src/lib/watchlist.ts:144` | - |
| `set_watchlist_follow_live` | migrations | 0 | - | 1 | `frontend/src/lib/watchlist.ts:134` | - |
| `settle_personal_trade` | migrations | 1 | `_certify_personal_report.py:361` | 1 | `frontend/src/lib/personalReport.ts:340` | - |
| `tennis_bot_approva_uscita` | migrations | 0 | - | 1 | `frontend/src/lib/proposteUscite.ts:91` | - |
| `tennis_bot_arm` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:876` | - |
| `tennis_bot_disarm` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:889` | - |
| `tennis_bot_service_activate` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:997` | - |
| `tennis_bot_service_set_uscite` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:966` | - |
| `tennis_bot_service_stop` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:1008` | - |
| `tennis_bot_service_update_params` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:1022` | - |
| `tennis_follow_event` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:180` | - |
| `tennis_set_follow_record` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:198` | - |
| `upsert_cash_movement` | migrations | 1 | `import_betfair_operations.py:194` | 0 | - | - |
| `upsert_imported_trade` | migrations | 1 | `import_betfair_operations.py:358` | 0 | - | - |

RPC chiamate ma non definite nei `.sql` tracciati: `fetch_missing_fixture_coverage` (usata dal solo job di pipeline) e il nome letterale `rpc`
(falso positivo di una variabile). 49 funzioni definite nei `.sql` e mai chiamate da produzione o frontend sono elencate in
`uscite/s03_riepilogo.txt` sezione D (molte sono usate da `pg_cron`/altre funzioni: `omega_transitions_*`, `omega_build_minute_transitions_*`,
`refresh_analytics_*`: non verificabile dal repo).

### 3.4 Tabelle definite e mai usate / usate e non definite

```
== C. TABELLE ==
tabelle distinte (nome letterale) usate da codice Python di produzione: 88
tabelle distinte usate dal frontend (src, non test): 17
tabelle distinte usate da prod o frontend: 89   (brief: 55 tabelle usate dal codice)
tabelle distinte usate da QUALSIASI file (anche test/strumenti/audit): 94
nomi non letterali (prod/frontend) da risolvere a mano: 6: <dinamico:MU.TABELLA_ORDINI_CONTO>; <dinamico:name>; <dinamico:nome>; <dinamico:t>; <dinamico:tabella>; <dinamico:table>
oggetti definiti nei .sql tracciati: tabelle 103, viste 7, funzioni 217
  tabelle definite in migrations/ o sql/: 103

-- tabelle USATE da prod/frontend ma NON definite in nessun .sql tracciato (tabelle/viste):
   17: ai_model_registry, api_call_log, api_coverage_by_season, fixture_predictions, injuries, leads, match_events, match_odds, match_team_stats, matches, ml_post_calibration, model_performance, season_backfill_state, standings, top_assists, top_cards, top_scorers

-- tabelle DEFINITE in migrations/sql ma mai usate da prod/frontend (usate solo da test/strumenti/audit o per niente):
   analytics_prob_staging                         test=0 strum=0 audit=0
   analytics_riepilogo_decisioni                  test=0 strum=0 audit=0
   analytics_riepilogo_meta                       test=0 strum=0 audit=0
   analytics_riepilogo_segnali                    test=0 strum=0 audit=0
   betfair_live_settings                          test=0 strum=0 audit=0
   book_odds_cache                                test=0 strum=0 audit=0
   book_odds_cache_fonte                          test=0 strum=0 audit=0
   hazard_atlas                                   test=0 strum=0 audit=1
   hazard_atlas_leghe                             test=0 strum=0 audit=0
   live_market_snapshots                          test=0 strum=0 audit=0
   live_score_timeline                            test=0 strum=0 audit=0
   omega_build_jobs                               test=0 strum=0 audit=0
   omega_ht_ft_transitions                        test=0 strum=0 audit=0
   omega_ht_ft_transitions_pre_ledger             test=0 strum=0 audit=0
   omega_ht_ft_transitions_raw                    test=0 strum=0 audit=0
   omega_minute_league_counts                     test=0 strum=2 audit=0
   omega_minute_league_counts_pre_ledger          test=0 strum=0 audit=0
   omega_minute_transitions                       test=0 strum=1 audit=0
   omega_minute_transitions_pre_ledger            test=0 strum=0 audit=0
   omega_minute_transitions_raw                   test=0 strum=0 audit=0
   omega_requests                                 test=0 strum=0 audit=0
   omega_transitions_league_counts                test=0 strum=0 audit=0
   omega_transitions_ledger                       test=0 strum=0 audit=0
   omega_transitions_runs                         test=0 strum=0 audit=0
   omega_transitions_state                        test=0 strum=0 audit=0
   personal_cash_movements                        test=0 strum=0 audit=0
   personal_trade_legs                            test=0 strum=0 audit=0
   sicurezza_bk                                   test=0 strum=0 audit=0
   strategies                                     test=0 strum=0 audit=0
   tennis_refresh_requests                        test=0 strum=0 audit=0
   tennis_replay_punteggio                        test=0 strum=0 audit=0
   tennis_replay_snapshots                        test=0 strum=0 audit=0
   totale: 32

-- viste definite e mai referenziate da .table()/.from():
   v_clv_summary
   v_es_concordance_roi
   v_es_emission_by_engine_market
   v_es_reject_funnel
   v_roi_by_market
   v_roi_by_track
```

Controprova per stringa (`s05_tabelle_stringa.py`, nome come parola intera in tutto il codice di produzione, frontend e workflow):

- Delle 32 tabelle definite senza `.table()` letterale (`fixture_detail_checks` e' ora usata da `season_gaps.py`, modificato nell'albero di lavoro), **11 sono riferite per stringa** (es. `betfair_live_settings`: nominata nei commenti di
  `Betfair/omega/omega_service.py:2188` e `Betfair/safe_strategy/execution.py:144`, letta davvero dall'RPC `get_live_settings`,
  `Betfair/stream/live_order_worker.py:498`; `hazard_atlas` in
  `Betfair/mike/dossier.py:30` e nel workflow `.github/workflows/hazard_atlas.yml:86-90`; `live_market_snapshots` in `Betfair/stream/curator.py:104`,
  `Betfair/stream/db.py:629`; `live_score_timeline` in `Betfair/stream/db.py:634-635`; `tennis_replay_snapshots`/`tennis_replay_punteggio` in
  `Betfair/stream/tennis_replay/caricamento.py:35-36`; `omega_requests` in `Betfair/omega/certificazione.py:1603`; `book_odds_cache` in
  `refresh_analytics_bets.py:8`; `fixture_detail_checks` in `season_gaps.py:14`; `omega_ht_ft_transitions` in `Betfair/omega/omega_empirical.py:10`;
  `strategies` e' falso positivo: parola comune).
- **21 tabelle senza nessun riferimento in produzione/frontend/workflow**: `analytics_prob_staging`, `analytics_riepilogo_{decisioni,meta,segnali}`,
  `book_odds_cache_fonte`, `omega_build_jobs`, `omega_ht_ft_transitions_{pre_ledger,raw}`, `omega_minute_league_counts`,
  `omega_minute_league_counts_pre_ledger`, `omega_minute_transitions`, `omega_minute_transitions_{pre_ledger,raw}`, `omega_transitions_{league_counts,ledger,runs,state}`,
  `personal_cash_movements`, `personal_trade_legs`, `sicurezza_bk`, `tennis_refresh_requests`. Sono tabelle del «mondo SQL»: compaiono solo in
  piu' file `.sql` (le `omega_*` in 1-3 file, `personal_*` 2-3, `sicurezza_bk` 3): le popolano/leggono funzioni e job del database
  (`omega_transitions_nightly`, `refresh_analytics_riepilogo`, ...). Che il DB le usi ancora **non e' verificabile dal repo** (servirebbe `pg_cron`/`pg_stat_user_tables` in sola lettura).
- **17 tabelle usate e non definite nei `.sql` tracciati**: `ai_model_registry`, `api_call_log`, `api_coverage_by_season`, `fixture_predictions`,
  `injuries`, `leads`, `match_events`, `match_odds`, `match_team_stats`, `matches`, `ml_post_calibration`, `model_performance`,
  `season_backfill_state`, `standings`, `top_assists`, `top_cards`, `top_scorers`. Tutte e 17 sono nominate in `DOCUMENTAZIONE_DATABASE.md`
  (`s05_tabelle_stringa.tsv`, seconda parte): il loro schema vive fuori dalle migrazioni tracciate (create dal pannello Supabase o prima
  dell'uso delle migrazioni). Non c'e' modo di ricostruirle da zero dal repo.
- «55 tabelle usate» (brief): le tabelle toccate da produzione Python sono 88, dal frontend 17, unione 89 (`s03_riepilogo.txt` sezione C).

### 3.5 Frequenze misurate (l'unica fonte di numeri sul carico: `MISURE_2026-10-02.md`)

Condizioni della misura (righe 3-22 del file): registri vivi dell'app, sessione aperta il 02/10/2026 alle 14:25:16 UTC, finestra 60 s
15:15:40-15:16:40 UTC, il brief del piano (§1) la descrive come «solo Mike acceso su 2 partite» (`MISURE_2026-10-02.md` non lo scrive); l'inventario del 02/10 avverte che
Omega era fermo (5/min non rappresentano Omega acceso) e che non c'erano partite tennis ne' sessioni scalper (`INVENTARIO_ARCHITETTURA.md`, «Punti non chiariti» 3-4).

| Servizio | Chiamate/min (60 s) | Media 5 min | Principali (MISURE) |
|---|---:|---:|---|
| runner-calcio | 552 (`MISURE:99`) | 549 (`:111`) | `betfair_live_order_requests` GET 189 (`:100`), `betfair_live_risk_rules` GET 168 (`:101`), RPC `get_live_settings` 123 (`:102`), `live_follow` 29 (`:103`) |
| mike-service | 279 (`:62`) | 268 (`:72`) | `mike_trades` GET 116 (`:63`), `mike_control` GET 58 (`:64`), `mike_requests` GET 58 (`:65`), `mike_events` POST 25 (`:66`) |
| safe-strategy-bot | 269 (`:131`) | 263 (`:144`) | `safe_strategy_trades` GET 81 (`:132`), `safe_strategy_requests` PATCH 53 + GET 44 (`:133-134`), `safe_strategy_control` 36 + 19 (`:135,137`), RPC `get_safe_aggregates` 19 (`:136`) |
| safe-strategy-service (scanner) | 86 (`:161`) | 87 (`:167`) | `safe_strategy_scan` POST 68 (`:162`), `mike_events` GET 6, RPC `list_bot_exposures` 6, `safe_strategy_status` POST 5 |
| scalper-service | 54 (`:178`) | 55 (`:182`) | `scalper_control` 18, `get_live_settings` 18, `scalper_service_control` 18 (`:179-181`) |
| tennis-bot-service | 36 (`:188`) | 43 (`:193`) | `tennis_bot_control` GET 18, `tennis_bot_service_control` PATCH 12 + GET 3 (`:189-191`) |
| runner-tennis | 28 (`:125`) | 29 (`:127`) | `tennis_live_follow` GET 28 (`:126`) |
| omega-service | 5 (`:85`) | 11 (`:88`) | `omega_trades` GET 4 (`:86`) |
| tennis-odds | 0 (4 chiamate in 29,8 min, `:202-204`) | 0 | `tennis_markets` DELETE 2 + POST 2 |
| **Totale** | **1.309** (`:51`) | | circa 22 al secondo |

Il brief del piano riporta «1.400 richieste/min»: la misura citata e' **1.309** (finestra 60 s) e **1.340 solo di Mike su 5 minuti** (`:72`);
il brief arrotonda. «Safe 255/min pur fermo»: la misura e' 269 (60 s) / 263 (5 min) (`:131`, `:144`).

### 3.6 Storage (bucket Supabase)

7 chiamate di produzione a `storage`: modelli ML scaricati da `Ai Engine/ai_engine/predict_fixture.py:83` e
`Betfair/betfair_report_manager.py:1335`, caricati da `Ai Engine/ai_engine/seriea_model_export.py:679` (`create_bucket` `:58`); manutenzione in
`cleanup_models.py:41-64`, `reset_ai_models.py:43-80`. Nessun accesso storage nel percorso Betfair.


## 4. Duplicazioni

Script: `s04_duplicati.py` (funzioni con lo stesso nome in file diversi, confronto con `difflib` sul testo normalizzato: via commenti,
righe vuote, docstring; classi IDENTICHE = testo uguale, QUASI = rapporto >= 0.90, DIVERSE < 0.90; `uscite/s04_*`), `s06_top30_duplicati.py`
(le 30 piu' pesanti, `uscite/s06_top_duplicati.{txt,tsv}`), `s09_gemelli_file.py` (file quasi-copia, `uscite/s09_gemelli_file.{txt,tsv}`).
Per leggere i numeri: **il confronto per NOME misura le funzioni omonime, non la logica ripetuta con nomi diversi**; i file «gemelli» (4.3)
completano il quadro. Altri strumenti gia' nel repo da non rifare: `strumenti/dati_g1/gemelle.py` -> `dati_g1/uscite/gemelle.tsv` (stessa-nome nei
moduli DB), `strumenti/h_gemelli_adattatori.py` (adattatori di replay per bot), `strumenti/e5_gemelli*.py`, `strumenti/D_gemelle_servizi.py`.

### 4.1 Funzioni con >= 3 copie in produzione

```
nomi di funzione con >= 3 copie nel codice di PRODUZIONE: 320
```
```
== nome | copie prod | file | tutte le copie (anche test/strum/audit) | righe totali copie prod | giudizio ==
__init__                       prod=182 file= 93 tutte=1041 righe= 4151  DIVERSE (180 gruppi) (rapporto min 1.00)
main                           prod= 96 file= 96 tutte= 288 righe= 5727  DIVERSE (96 gruppi) (rapporto min 1.00)
_num                           prod= 20 file= 20 tutte=  22 righe=  131  DIVERSE (18 gruppi) (rapporto min 1.00)
process_market_book            prod= 20 file= 20 tutte=  34 righe= 1826  DIVERSE (19 gruppi) (rapporto min 0.91)
check_market_book              prod= 19 file= 19 tutte=  37 righe=  153  DIVERSE (14 gruppi) (rapporto min 0.92)
_now_iso                       prod= 17 file= 17 tutte=  20 righe=   34  IDENTICHE (rapporto min 1.00)
process_closed_market          prod= 17 file= 17 tutte=  20 righe=  380  DIVERSE (15 gruppi) (rapporto min 0.91)
_f                             prod= 16 file= 16 tutte=  26 righe=  103  DIVERSE (10 gruppi) (rapporto min 1.00)
_place                         prod= 16 file= 15 tutte=  23 righe=  829  DIVERSE (16 gruppi) (rapporto min 1.00)
__getattr__                    prod= 14 file= 11 tutte=  32 righe=   59  DIVERSE (14 gruppi) (rapporto min 1.00)
avvia                          prod= 14 file= 12 tutte=  22 righe=  122  DIVERSE (14 gruppi) (rapporto min 1.00)
stato                          prod= 14 file= 11 tutte=  18 righe=  164  DIVERSE (14 gruppi) (rapporto min 1.00)
_emit                          prod= 13 file= 13 tutte=  15 righe=   86  DIVERSE (9 gruppi) (rapporto min 1.00)
_int                           prod= 12 file= 12 tutte=  13 righe=   74  DIVERSE (8 gruppi) (rapporto min 1.00)
azzera                         prod= 12 file= 12 tutte=  12 righe=   80  DIVERSE (11 gruppi) (rapporto min 0.90)
_reg                           prod= 11 file=  7 tutte=  11 righe=   49  DIVERSE (8 gruppi) (rapporto min 1.00)
ferma                          prod= 11 file=  9 tutte=  11 righe=   56  DIVERSE (7 gruppi) (rapporto min 1.00)
elenco_controlli               prod= 10 file= 10 tutte=  10 righe=   52  DIVERSE (8 gruppi) (rapporto min 1.00)
evaluate                       prod= 10 file=  9 tutte=  25 righe=  335  DIVERSE (10 gruppi) (rapporto min 1.00)
place                          prod= 10 file=  9 tutte=  14 righe=  564  DIVERSE (7 gruppi) (rapporto min 1.00)
invia                          prod=  9 file=  6 tutte=  14 righe=  101  DIVERSE (9 gruppi) (rapporto min 1.00)
ask_and_run_cli                prod=  8 file=  8 tutte=   8 righe=  152  DIVERSE (8 gruppi) (rapporto min 1.00)
get_supabase                   prod=  8 file=  8 tutte=   8 righe=   42  DIVERSE (3 gruppi) (rapporto min 0.91)
statistiche                    prod=  8 file=  5 tutte=  11 righe=   41  DIVERSE (7 gruppi) (rapporto min 1.00)
verifica                       prod=  8 file=  8 tutte=  10 righe=  525  DIVERSE (8 gruppi) (rapporto min 1.00)
_controllo                     prod=  7 file=  7 tutte=   8 righe=   89  DIVERSE (6 gruppi) (rapporto min 1.00)
_ko_epoch_ms                   prod=  7 file=  7 tutte=   7 righe=  150  DIVERSE (4 gruppi) (rapporto min 1.00)
_process_once                  prod=  7 file=  7 tutte=   7 righe=  471  DIVERSE (7 gruppi) (rapporto min 1.00)
_validate                      prod=  7 file=  3 tutte=   9 righe=  195  DIVERSE (7 gruppi) (rapporto min 1.00)
acceso                         prod=  7 file=  7 tutte=   8 righe=   33  DIVERSE (6 gruppi) (rapporto min 1.00)
aggiorna                       prod=  7 file=  6 tutte=   7 righe=  155  DIVERSE (7 gruppi) (rapporto min 1.00)
log                            prod=  7 file=  7 tutte=  96 righe=   44  DIVERSE (7 gruppi) (rapporto min 1.00)
run                            prod=  7 file=  7 tutte=  12 righe=  401  DIVERSE (7 gruppi) (rapporto min 1.00)
settled_orders                 prod=  7 file=  7 tutte=   7 righe=   25  DIVERSE (2 gruppi) (rapporto min 1.00)
__str__                        prod=  6 file=  6 tutte=   6 righe=   23  DIVERSE (5 gruppi) (rapporto min 1.00)
_avvia_canale                  prod=  6 file=  6 tutte=   6 righe=  134  DIVERSE (6 gruppi) (rapporto min 1.00)
_cancel_if_live                prod=  6 file=  6 tutte=   6 righe=   70  DIVERSE (5 gruppi) (rapporto min 1.00)
_ciclo                         prod=  6 file=  5 tutte=   9 righe=   68  DIVERSE (6 gruppi) (rapporto min 1.00)
_drive_flatten                 prod=  6 file=  6 tutte=   6 righe=  658  DIVERSE (6 gruppi) (rapporto min 1.00)
_has_live                      prod=  6 file=  6 tutte=   6 righe=   49  DIVERSE (5 gruppi) (rapporto min 1.00)
_manage                        prod=  6 file=  6 tutte=   6 righe= 1014  DIVERSE (6 gruppi) (rapporto min 1.00)
_p                             prod=  6 file=  5 tutte=  14 righe=   44  DIVERSE (6 gruppi) (rapporto min 1.00)
_parse_int                     prod=  6 file=  6 tutte=   6 righe=   95  DIVERSE (2 gruppi) (rapporto min 1.00)
_pubblica_proposte             prod=  6 file=  6 tutte=   6 righe=   43  DIVERSE (5 gruppi) (rapporto min 1.00)
_sleep_backoff                 prod=  6 file=  6 tutte=   6 righe=   21  DIVERSE (3 gruppi) (rapporto min 1.00)
```
```
== i 4 nomi del brief (copie in produzione / in tutto il repo) ==
read_book              produzione=  3 (file 3), test=26, strumenti/audit=1, tutte=30
process_market_book    produzione= 20 (file 20), test=9, strumenti/audit=5, tutte=34
_now_iso               produzione= 17 (file 17), test=3, strumenti/audit=0, tutte=20
log                    produzione=  7 (file 7), test=85, strumenti/audit=4, tutte=96

gruppi di file identici: 35 (vedi s04_file_identici.txt)
```

Il brief del piano (§1) scrive «`read_book` definita 17 volte, `process_market_book` 15, `_now_iso` 17, `log` 18». Misurato in produzione: `read_book`
**3** (file 3; altre 26 nei test), `process_market_book` **20** (20 file), `_now_iso` **17** (17 file, **identiche**: 34 righe in tutto), `log` **7**
(7 file; 96 con test e audit). Le 17 copie di `_now_iso` stanno nei 6 moduli DB (`mike/db.py:52`, `omega_db.py:432`, `bot_db.py:55`, `safe_strategy/db.py:16`, `stream/db.py:40`, `tennis_db.py:79`), in 5 worker
(`order_worker.py:32`, `refresh_worker.py:31`, `live_order_worker.py:650`, `risk_engine_worker.py:43`, `xhedge_worker.py:23`) e in 6 altri file di servizio/scores (`s04_dettaglio_copie.tsv`).
`process_market_book` (20 copie, 1.826 righe) e' il metodo di aggancio che `flumine` impone a ogni `Strategy`: le copie sono 19 gruppi diversi,
quindi **non e' una duplicazione da eliminare**; l'unica coppia quasi-uguale ha 211 righe recuperabili (`s06_top_duplicati.txt`).

### 4.2 Le 30 piu' pesanti per righe totali (esclusi i metodi omonimi generici `main`, `__init__`, `run`, ...)

Colonne: `ident` = copie identiche al capogruppo, `quasi` = copie con rapporto 0.90-0.99, `div` = copie diverse (da sole), `recup` = righe delle
copie non capogruppo di gruppi con >= 2 membri (stima per difetto: una copia condivisa basterebbe).

```
== TOP 30 per righe totali (esclusi metodi omonimi generici) ==
nome                         copie file  righe ident quasi  div  recup  giudizio
process_market_book             20   20   1826     0     1   18    211  MISTE
run_once                         4    4   1160     0     0    4      0  DIVERSE
_manage                          6    6   1014     0     0    6      0  DIVERSE
_place                          16   15    829     0     0   16      0  DIVERSE
_drive_flatten                   6    6    658     0     0    6      0  DIVERSE
place                           10    9    564     3     0    6     12  MISTE
verifica                         8    8    525     0     0    8      0  DIVERSE
_try_enter                       3    3    503     0     2    0    344  IDENTICHE/QUASI
run_for_date                     3    3    499     0     0    3      0  DIVERSE
_process_once                    7    7    471     0     0    7      0  DIVERSE
_manage_maker                    3    3    431     0     1    1    157  MISTE
_place_exact                     4    4    384     0     0    4      0  DIVERSE
process_closed_market           17   17    380     0     2   13     25  MISTE
execute_place                    3    3    353     0     0    3      0  DIVERSE
evaluate                        10    9    335     0     0   10      0  DIVERSE
place_submin_live                4    4    325     0     0    4      0  DIVERSE
_drive_submins                   4    4    306     0     0    4      0  DIVERSE
place_order_live                 4    4    275     0     0    4      0  DIVERSE
run_backfill                     3    3    265     0     0    3      0  DIVERSE
_process_local_requests          3    3    244     0     0    3      0  DIVERSE
_run_one_event                   3    3    239     0     0    3      0  DIVERSE
_un_giro                         4    4    233     0     0    4      0  DIVERSE
_enter_join                      3    3    215     1     1    0    143  IDENTICHE/QUASI
ferma_al_nuovo_avvio             4    4    212     0     0    4      0  DIVERSE
esegui                           3    3    212     0     0    3      0  DIVERSE
fit                              4    3    203     0     0    4      0  DIVERSE
_validate                        7    3    195     0     0    7      0  DIVERSE
write_message                    3    3    193     0     0    3      0  DIVERSE
osserva                          6    6    179     0     0    6      0  DIVERSE
cancel_order_live                3    3    177     0     0    3      0  DIVERSE
```
```
== omonimie generiche (non sono duplicati da fondere per costruzione) ==
main                            96   96   5727     0     0   96      0
__init__                       182   93   4151     2     0  178      6
run                              7    7    401     0     0    7      0
stato                           14   11    164     0     0   14      0
avvia                           14   12    122     0     0   14      0
azzera                          12   12     80     0     1   10     11
__getattr__                     14   11     59     0     0   14      0
ferma                           11    9     56     4     0    5     11
log                              7    7     44     0     0    7      0
__str__                          6    6     23     1     0    4      3
__repr__                         3    3      6     0     0    3      0

righe recuperabili per copie identiche/quasi (esclusi omonimi): 2324 su 320 nomi con >= 3 copie
```

Giudizio: **299 dei 319 nomi con >= 3 copie sono DIVERSI** (stesso nome, corpi diversi: strategie e adattatori per bot); solo 20 nomi hanno
copie identiche o quasi-identiche:

| Nome | Copie | Righe | Giudizio | Dove (prime 3 copie, `s04_dettaglio_copie.tsv`) |
|---|---:|---:|---|---|
| `_now_iso` | 17 | 34 | IDENTICHE | `Betfair/stream/db.py:40`, `Betfair/mike/db.py:52`, `Betfair/omega/omega_db.py:432` ... |
| `per_codice` | 6 | 30 | IDENTICHE | (6 file) |
| `_try_enter` | 3 | 503 | QUASI (0.92-1.00) | `Betfair/stream/scalper/scalper_bot.py:1183`, `Betfair/stream/tennis_scalper/tennis_scalper_bot.py:1256`, `laboratorio/scalper_lab/scalper_bot_base.py:815` |
| `_update_flow` | 3 | 117 | IDENTICHE | `scalper_bot.py:1688`, `tennis_scalper_bot.py:1692`, `scalper_bot_base.py:1209` |
| `_enter_join` | 3 | 215 | QUASI | `scalper_bot.py:1378`, `tennis_scalper_bot.py:1462`, `scalper_bot_base.py:1024` |
| `_flatten` | 3 | 110 | QUASI | `scalper_bot.py:2661`, `tennis_scalper_bot.py:2322`, `scalper_bot_base.py:1655` |
| `_manage_maker` | 3 | 431 | QUASI/DIVERSA (163/157/111 righe) | `scalper_bot.py:1524`, `tennis_scalper_bot.py:1534`, `scalper_bot_base.py:1097` |
| `_matched_position`, `_handle_cancelling`, `_enter_maker` | 3+3+3 | 85+51+101 | QUASI | stesso trio |
| `compute_green`, `micro_price`, `wom_imbalance`, `_long_drift_signed`, `_long_drift`, `_recent_move`, `_flow_sums`, `_line_key`, `_now`, `_tempi_on` | 3 ciascuna | 27-69 | IDENTICHE | stesso trio |
| `enqueue_live_order` | 3 | 15 | IDENTICHE | i 3 moduli DB `bot_db.py`, `omega_db.py`, `mike/db.py` |

### 4.3 File quasi-copia (stesso nome di funzione, corpo uguale o quasi)

```
== gruppo scalper ==
  Betfair/stream/scalper/scalper_bot.py (69 funz., 3315 righe)  vs  Betfair/stream/tennis_scalper/tennis_scalper_bot.py (61 funz., 2974 righe): 49 nomi in comune, 20 identiche, 7 simili>=0.90, 22 diverse; righe gemelle lato A = 806 (24.3% del file A); delle diverse 0 hanno la STESSA STRUTTURA (stringhe mascherate), 0 righe lato A
  Betfair/stream/scalper/scalper_bot.py (69 funz., 3315 righe)  vs  laboratorio/scalper_lab/scalper_bot_base.py (43 funz., 2076 righe): 41 nomi in comune, 22 identiche, 5 simili>=0.90, 14 diverse; righe gemelle lato A = 866 (26.1% del file A); delle diverse 0 hanno la STESSA STRUTTURA (stringhe mascherate), 0 righe lato A
  Betfair/stream/tennis_scalper/tennis_scalper_bot.py (61 funz., 2974 righe)  vs  laboratorio/scalper_lab/scalper_bot_base.py (43 funz., 2076 righe): 42 nomi in comune, 23 identiche, 3 simili>=0.90, 16 diverse; righe gemelle lato A = 649 (21.8% del file A); delle diverse 0 hanno la STESSA STRUTTURA (stringhe mascherate), 0 righe lato A

== gruppo db ==
  Betfair/safe_strategy/bot_db.py (61 funz., 1044 righe)  vs  Betfair/omega/omega_db.py (66 funz., 1081 righe): 28 nomi in comune, 2 identiche, 3 simili>=0.90, 23 diverse; righe gemelle lato A = 29 (2.8% del file A); delle diverse 2 hanno la STESSA STRUTTURA (stringhe mascherate), 25 righe lato A
  Betfair/safe_strategy/bot_db.py (61 funz., 1044 righe)  vs  Betfair/mike/db.py (42 funz., 693 righe): 26 nomi in comune, 3 identiche, 0 simili>=0.90, 23 diverse; righe gemelle lato A = 8 (0.8% del file A); delle diverse 0 hanno la STESSA STRUTTURA (stringhe mascherate), 0 righe lato A
  Betfair/omega/omega_db.py (66 funz., 1081 righe)  vs  Betfair/mike/db.py (42 funz., 693 righe): 22 nomi in comune, 2 identiche, 0 simili>=0.90, 20 diverse; righe gemelle lato A = 4 (0.4% del file A); delle diverse 0 hanno la STESSA STRUTTURA (stringhe mascherate), 0 righe lato A
```

Letture:

1. **Lo scalper calcio e lo scalper tennis sono lo stesso programma per un quarto del codice**: 20 funzioni identiche e 7 quasi-identiche su 49 in comune
   (806 righe di `scalper_bot.py`, 24,3%); in piu' esiste un terzo file, `laboratorio/scalper_lab/scalper_bot_base.py` (2.076 righe, nella cartella
   `laboratorio/` classificata ARCHIVIO in 7), che e' una copia di lavoro del bot di produzione: 22 funzioni identiche a `scalper_bot.py` e 23 a
   `tennis_scalper_bot.py`. Il resto (22 funzioni «diverse» nel confronto calcio/tennis) sono le regole di strategia (soglie, gambe, uscite): vanno lasciate invariate.
2. **I moduli DB dei bot NON sono copie riga per riga.** `bot_db.py`/`omega_db.py` condividono 28 nomi di funzione ma solo 2 sono identiche e 3 quasi
   (29 righe, 2,8%); `bot_db`/`mike/db` 26 nomi, 3 identiche (8 righe); `omega_db`/`mike/db` 22 nomi, 2 identiche. Il brief parla di «5 moduli diversi, uno per bot»:
   e' vero (in 3.1), ma la ripetizione e' di FORMA (stessi nomi `get_trade`, `get_event`, `get_live_order_request`, `get_live_order_mirror`, `enqueue_live_order`,
   `read_control`, `runner_heartbeat`, `live_follow_status` in 3 moduli) piu' che di testo. Dove sono davvero uguali sono funzioni minuscole
   (`_sb` 2 righe in 3 moduli, `_now_iso` 2 righe in 5, `enqueue_live_order` 15 righe in 3). L'unico duplicato grande per testo nel livello DB e'
   `_exec_retry` (`Betfair/stream/db.py:44` 15 righe e `Betfair/stream/tennis_live/tennis_db.py:63` 14 righe, similarita' 0,96: `dati_g1/uscite/gemelle.tsv`).
3. **Conseguenza per il piano**: la riduzione di righe «per fusione» e' reale per i bot scalper (circa 800 righe di funzioni identiche +
   la copia di laboratorio) e per i cinque servizi (nella forma, non nel testo); sul livello DB va misurata con un'altra tecnica (generazione delle
   funzioni di accesso dalle tabelle), non con il confronto di testo.

### 4.4 File identici

`s04_duplicati.py` raggruppa per hash i file tracciati con contenuto identico (>= 30 righe): **35 gruppi**, `uscite/s04_file_identici.txt`.
**Nessun gruppo contiene codice di produzione** (`grep Betfair/` e `*.py` nel file: 0). 24 gruppi sono coppie `frontend/src/fotografia/snapshot/*.off.json` /
`*.v2.json` (le fotografie dell'interfaccia vecchia e del «guscio v2», identiche per costruzione: `frontend/src/fotografia/`); i restanti 11 sono copie in
`AUDIT_*` (es. `AUDIT_2026-09-29/in_attesa_del_via/MIKE_P5_5.md` = `AUDIT_2026-09-30/MIKE_P5_5.md`) e le due copie dei test e2e
`frontend/e2e_fase1/{clientVero.ts,percorsi.e2e.test.tsx}` = `AUDIT_2026-09-25/e2e_fase1/strumenti/` (124 e 1.129 righe).


## 5. Processi e canali locali

Fonti: lettura diretta di `desktop/main.js`, `desktop/ambiente_runner.js`, `desktop/preload.js`, `Betfair/stream/{watchdog,avvio_app,single_instance,
local_channel,canale_bot,ladder_canale,esiti_ordini_canale,sveglia_canale}.py`, `Betfair/stream/tennis_live/canale_bot_tennis.py`,
`Betfair/safe_strategy/{canale_scan,porta_ordini}.py`, `Betfair/{omega,mike}/porta_ordini.py` e le righe di avvio di ogni servizio; porte e
costanti raccolte da `p01_porte.py` (`uscite/p01_porte.tsv`: ogni riga con `47xxx` in codice di produzione/desktop/frontend, con `file:riga` e
tipo definizione/citazione; `p01_porte_riepilogo.txt`); workflow da `.github/workflows/*.yml`. Non ho lanciato nessun processo e non ho
interrogato il sistema operativo: i processi sotto sono quelli che il CODICE avvia, non quelli che oggi girano sul PC.

### 5.1 Chi avvia cosa

**Avvio dell'app** (`desktop/package.json:6` `"main": "bootstrap.js"`; `bootstrap.js` carica sempre `desktop/main.js` del repo; `npm start` = `electron .`).
In `main.js`, nell'ordine di `app.whenReady` (`:899`): `resolveRepoRoot` -> cartella dei registri dei figli (`prepareChildLogs`, `:307`) -> cancella il file
`ARRESTO` di un precedente spegnimento -> `ensureFreshUi()` (`:160`, esegue `npm run build` se `frontend/dist` e' piu' vecchio dei sorgenti) ->
`startStaticServer()` (`:191`, HTTP su `127.0.0.1:47330`, `UI_PORT` `:27`) -> `startRunners()` (`:413`) -> `startBetfairWebSso()` (`:759`) -> `createWindow()`
(`:886`, carica `http://127.0.0.1:47330/board`, `:895`).

Due identificativi nascono UNA volta per avvio dell'app e viaggiano nell'ambiente di tutti i figli (`ambiente_runner.js`, funzione pura
`costruisciEnvRunner`, test `ambiente_runner.test.js`): `APP_BOOT_ID` (`main.js:46`; i servizi si fermano da soli se l'id cambia: «all'avvio nessun bot opera»,
`Betfair/stream/avvio_app.py:54-100`) e `LOCAL_CHANNEL_TOKEN` (`main.js:61`, 32 byte casuali; abilita i comandi `order` sui canali 47331/47332;
alla pagina arriva dal preload, `desktop/preload.js:21`). Cadenze impostate dall'app: `LIVE_ORDER_QUEUE_POLL_SEC=0.15`, `LIVE_LADDER_PUBLISH_SEC=0.3`,
`TENNIS_LADDER_PUBLISH_SEC=0.3`, `TENNIS_ORDER_POLL_SEC=0.15`, `LIVE_RISK_ENGINE_POLL_SEC=0.15` (`ambiente_runner.js:69-75`).

**Processi avviati da `startRunners()`** (`main.js:413-484`; ognuno con `cwd` = radice del repo e il Python di `.venv`, `main.js:353-395`; registro
console + file per figlio, `main.js:307-352`):

| Etichetta | `main.js` | Comando (dopo `python -m Betfair.stream.watchdog`) | Modulo bersaglio (righe) | Lock (socket in ascolto su 127.0.0.1) | Canale WS | Note |
|---|---:|---|---|---|---|---|
| `runner-calcio` | :419 | (nessun argomento: bersaglio di serie `watchdog.py:65`) | `Betfair/stream/runner.py` (3.171) | **47311** (`runner.py:1254`, env `LIVE_RUNNER_LOCK_PORT`) | **47331** (`runner.py:2640`; accetta `order`, `snapshot`) | stream mercati e ordini via flumine; thread: ladder, punteggi, ordini, rischio, xhedge, stop giornaliero, riconciliazione |
| `runner-tennis` | :420 | `-- Betfair.stream.tennis_live.tennis_runner` | `tennis_runner.py` (3.483) | **47312** (`tennis_runner.py:2049`, env `TENNIS_RUNNER_LOCK_PORT`) | **47332** (`tennis_runner.py:3157`) | ospita i 4 bot tennis |
| `scalper-service` | :427 | `-- Betfair.stream.scalper.scalper_service` | `scalper_service.py` (982) | **47314** (`scalper_service.py:855`, env `SCALPER_SVC_LOCK_PORT`) | **47338** sola lettura (`scalper_service.py:607`) | un processo figlio per partita: `scalper_service.py:702-713` (`python -m Betfair.stream.scalper.scalper_session <event_id>`, gruppo di processi proprio) |
| `tennis-bot-service` | :437 | `-- Betfair.stream.tennis_live.tennis_bot_service --bridge-only` | `tennis_bot_service.py` (1.183) | nessuno in modalita' ponte (`:1138`; il ramo con lock 47312 e' `:1104`, solo senza `--bridge-only`) | **47337** sola lettura (`tennis_bot_service.py:258`, `canale_bot.py:135`) | ponte: righe dei 4 bot tennis, nessun login Betfair (`:1138-1160`) |
| `safe-strategy-service` | :443 | `-- Betfair.safe_strategy.service` | `safe_strategy/service.py` (3.444) | **47315** (`service.py:74`, env `SAFE_STRATEGY_LOCK_PORT`) | **47336** sola lettura (`service.py:91`, `:2457`) | lo SCANNER: feed unico quote/punteggi per Mike, Safe, Omega e per il runner calcio |
| `omega-service` | :450 | `-- Betfair.omega.omega_service` | `omega_service.py` (8.936) | **47313** (`omega_service.py:8520`) | **47334** sola lettura (`:8587`) | |
| `safe-strategy-bot` | :456 | `-- Betfair.safe_strategy.bot_service` | `bot_service.py` (11.136) | **47318** (`bot_service.py:139`) | **47335** sola lettura (`:10569`) | |
| `mike-service` | :461 | `-- Betfair.mike.service` | `mike/service.py` (7.551) | **47319** (`mike/config.py:32`, env `MIKE_LOCK_PORT`, `service.py:48`) | **47333** sola lettura (`service.py:6784`) | |
| `backtest-worker` | :469 | `-- Betfair.stream.backtest.worker` | `worker.py` (102) | nessuno (verificato: nessuna `acquire_single_instance_lock` in `worker.py`) | - | legge la coda `live_backtest_requests` ogni 5 s (`worker.py:23`, `DEFAULT_POLL_SEC`); esegue il banco e «Applica bot» di Match Replay |
| `tennis-odds` | :480 (e `setInterval` :483, 30 min) | `betfair_tennis_odds.py` (SENZA watchdog) | `betfair_tennis_odds.py` (322) | **47316** (`betfair_tennis_odds.py:305`) | - | processo breve; se la run precedente e' viva, salta il giro (`main.js:476-478`) |

Sono quindi **9 watchdog + 9 figli** (18 processi Python) piu' i processi brevi e le sessioni scalper, piu' i processi di Electron (main, renderer, GPU:
non contati dal codice). La porta di lock **47317 non e' usata** da nessun modulo; la **47312 compare come default in due moduli** (`tennis_runner.py:2049`
la acquisisce, `tennis_bot_service.py:1104` la prova solo fuori da `--bridge-only`).

**Altri avvii (non fatti dall'app)**:

| Cosa | Dove | Comando | Note |
|---|---|---|---|
| `avvia_omega_service.bat`, `avvia_scalper_service.bat`, `start_backtest_worker.bat`, `stream_api.bat` (runner), `aggiorna_quote_betfair.bat` (HTTP 8787 ordini a mano vecchi), `aggiorna_*.bat`, `importa_ultimi_15_giorni.bat` | radice | `.venv\Scripts\python.exe -m ...` | lancio manuale; il lock di istanza impedisce il doppio avvio con quelli dell'app (`main.js:446-449`). `avvia_omega_service.bat` e `avvia_scalper_service.bat` sono citati come istruzione dalla UI (`frontend/src/components/omega/ManualPanel.tsx:362`, `components/live/HabitatCard.tsx:66`) |
| `start_order_server.py` | radice (56 righe) | `python start_order_server.py` | HTTP `127.0.0.1:8787` (`Betfair/stream/odds_http.py:28`, `ThreadingHTTPServer`, `POST /place-order`) + `order_worker` (coda `betfair_order_requests`) + `refresh_worker`: la strada «ordini a mano vecchi»; non e' avviata dall'app; il runner non ospita l'endpoint (`runner.py:3159`) |
| 10 workflow GitHub Actions | `.github/workflows/*.yml` | cron e `workflow_dispatch` | cloud, non sul PC: vedi sotto |
| `python -m Betfair.stream.backtest.certifica <bot>` | banco | riga di comando | certificazione; non e' un servizio |
| `tools/*.py`, `Betfair/*/tools/*.py` | repo | riga di comando | replay e misure; 76 file, 35.486 righe (sezione 1) |

**I 10 workflow cloud** (cron in UTC; script lanciati; da `grep` di `cron:`/`python`):
`daily_yesterday_backfill.yml` (01:12, `daily_yesterday_backfill.py`), `today_predictions_backfill.yml` (02:18, `-m Prediction.today_predictions_backfill`),
`predictions_results_backfill.yml` (03:23; `-m Prediction.predictions_results_backfill`, `build_analytics_signals.py`, `merge_engine_signals.py`,
`enrich_analytics_snapshots.py`, `refresh_analytics_bets.py`, `build_direzione.py`), `weekly_poisson_calibration.yml` (lunedi' 03:27; `generate_dynamic_cal.py`,
`update_poisson_calibration.py --apply`, `generate_dc_rho.py`), `ml_calibration.yml` (05:14; `compute_ml_post_calibration.py`), `retrain_models.yml` (08:19;
`cloud_retrain_shard.py`, a shard), `seasons_catchup.yml` (13:47; `seasons_catchup.py`), `leagues_mapper.yml` (giorno 1 del mese 00:12; `leagues_mapper.py`),
`hazard_atlas.yml` (dopo il Daily; `-m Betfair.stream.scalper.genera_atlante`), `validate_models.yml` (solo manuale; `validate_walkforward.py`).
Questi lavorano sul DB cloud e producono i dati letti dai bot (previsioni, calibrazioni, atlante hazard): sono la parte del software che gira SENZA il PC.

### 5.2 Supervisione, arresto, riavvio

- **Watchdog** (`Betfair/stream/watchdog.py`, 337 righe): classifica l'uscita del figlio (`classify_exit`, `:73`): codice 0 = pulita (non riaccende), codice 75
  (`runner_lifecycle.py:72`, `EXIT_PLANNED_RESTART`) = ricambio pianificato, riavvio immediato; uscita entro 5 s (`WATCHDOG_LOCK_GRACE_SEC`, `:251`) = un'altra copia e' attiva (lock
  di istanza): il watchdog si ferma (`:307-313`); qualsiasi altro codice = caduta: alert `CRITICAL` in `live_alerts` + Telegram, riavvio con backoff
  `next_backoff` 10 s, 20 s, 40 s ... tetto 300 s (`:93`, `WATCHDOG_BACKOFF_BASE_SEC`/`CAP_SEC` `:249-250`), massimo 5 riavvii/ora (`WATCHDOG_MAX_RESTARTS_PER_HOUR`, `:248`) poi
  «SERVE INTERVENTO MANUALE» e si ferma (`:318-322`). Battito `WATCHDOG_HEARTBEAT_SEC` 30 s (`:252`), scritto solo dal watchdog del runner calcio (`deve_scrivere_battito`, `:122`).
  Il figlio e' lanciato SENZA `env`: eredita l'ambiente (stesso `APP_BOOT_ID` e token dopo un riavvio) (`main.js:36-42` commento; `watchdog.py` `popen(cmd, cwd=...)`).
- **Lock di istanza** (`Betfair/stream/single_instance.py:18`): `bind`+`listen` su `127.0.0.1:<porta>`; porta occupata = `SystemExit` immediato. Sono 8 porte
  (47311-47316, 47318, 47319), una per servizio.
- **Chiusura dell'app** (`main.js:527-575`): scrive il file `ARRESTO` (cartella `APP_ARRESTO_DIR` o `<dati>/_arresto`, `main.js:255-262`; modulo Python
  `Betfair/stream/arresto_ordinato.py:31`), aspetta ciascun servizio in elenco (`ARRESTO_ORDINATO_LABELS`, `:279`: i due runner, omega, safe-service, safe-bot, mike, tennis-bot, scalper) per un tempo
  massimo (`shutdownGraceMs`, `:292-296`: scalper 150 s, omega e safe-bot 45 s, gli altri 25 s), poi `taskkill /PID <pid> /T /F` sui rimasti (`:493`); `app.exit(0)` (`:572`). `tennis-odds` e
  `backtest-worker` non sono attesi. Safe e Omega annullano i loro ordini vivi all'arresto (tetto 10 s dopo il giro: commento `main.js:289-291`, `Betfair/safe_strategy/arresto_bot.py:34`).
- **Orologio e cambio di giorno**: non c'e' un processo «di giornata»; ogni servizio calcola la propria giornata (non verificato in questo inventario: appartiene alle schede dei componenti).

### 5.3 Le linee verso Betfair (chi si autentica e con quale libreria)

Ogni processo fa il proprio accesso (nessuna sessione condivisa tra processi: `INVENTARIO_ARCHITETTURA.md` B-3, confermato dal 02/10 nei registri `MISURE:210-238`: `certlogin SUCCESS`/`cert login .it OK` in
runner-calcio, runner-tennis, safe-service, scalper, mike, omega, tennis-odds). Percorsi di accesso nel codice di OGGI:
(1) `betfairlightweight` per lo stream e il runner flumine (`Betfair/stream/auth.py:13`; 27 file di produzione, sezione 2.2);
(2) client JSON-RPC proprio con `requests` (`Betfair/client.py:10`, usato da `runner.py`, `odds_refresh.py`, `betfair_report_manager.py`, `betfair_tennis_odds.py`) e
`omega_market.py:508` (Mike/Safe/Omega «a domanda»: ordini veri, saldo, quote di ripiego);
(3) **un terzo login nel processo Electron** (`desktop/main.js:759`, SSO web: `certlogin` con le credenziali del `.env`, cookie `ssoid` per le finestre Video/Stats; keep-alive `BETFAIR_KEEPALIVE_MS` 15 min `:589`, ritentativi 30/60/120/300 s `:590`): sola navigazione, nessun ordine.
Flusso stream: il runner calcio, il runner tennis, ogni sessione scalper e lo scanner (fino a 4 linee, `Betfair/safe_strategy/stream.py`) aprono ciascuno il proprio stream (`INVENTARIO_ARCHITETTURA.md` B-4...B-9, non rimisurato).

### 5.4 Canali locali (WebSocket JSON su 127.0.0.1)

Protocollo e sicurezza (`Betfair/stream/local_channel.py`, 767 righe): server `websockets.asyncio.server.serve` (`:292`); messaggi JSON una riga: push
`{"t": topic, "d": payload}`, richieste `{"id", "m": "order"|"snapshot"|"sveglia", "p"}`, risposte `{"id","ok","d"|"e"}` (`:14-18`; il metodo `sveglia` e' gestito a `:404`, prima della coda dei comandi,
e la usa il frontend: `frontend/src/lib/localChannel.ts:338-345`). Bind solo 127.0.0.1; origini ammesse: la UI dell'app (`ORIGINI_APP`, `:68`) piu' `LOCAL_CHANNEL_ORIGINS`;
i comandi che ESEGUONO (`order`) richiedono `?t=<token>` (`:65`, `ENV_TOKEN`); i canali dei bot sono `solo_lettura=True` (`start_channel(porta, sport, solo_lettura)`, `:717`);
i lettori Python si presentano su `/lettore/<topic>` (non contano come desktop collegato, non possono mandare comandi: `esiti_ordini_canale.py` docstring regola 7). I nomi dei
topic stanno in un solo posto (`canale_bot.py:82` `TOPIC`).

| Porta | Produttore (processo, `file:riga`) | Topic principali | Modo | Consumatori (`file:riga`) |
|---|---|---|---|---|
| **47330** | `desktop/main.js:215` (HTTP statico, serve `frontend/dist`) | pagine | HTTP | BrowserWindow `main.js:895`; origine ammessa `local_channel.py:68` |
| **47331** runner calcio | `runner.py:2640` `start_channel(.., "calcio")` | `hello`, `ladder`, `now`, `order`, `position`, `board` (`local_channel.py:14-18`); `battito`, `modo_ordini`, `flusso_stream`, `betfair_live_xhedge`, `account`/`conto` (`canale_bot.py:82-135`, `esiti_ordini_canale.py` `TOPIC_CONTO`); cadenza ladder `LIVE_LADDER_CANALE_MS` 200 ms (`config_stream.py:74`, `ladder_canale.py:60`) | lettura + COMANDI ordine | UI: `frontend/src/lib/localChannel.ts:63` (`calcio`); Safe/Omega/Mike per gli ordini (`safe_strategy/porta_ordini.py:75`, `omega/porta_ordini.py`, `mike/porta_ordini.py`, classe `PortaCanale` `safe_strategy/porta_ordini.py:541`, `/comando/<attore>`); esiti: `ClientEsiti` `esiti_ordini_canale.py:234` (classe `EsitiOrdini` `esiti_ordini_canale.py:421`, creata da Omega `omega_service.py:800`, ciclo di Safe `bot_service.py:10645-10647`, e `ClientEsiti` diretto da Mike `mike/service.py:6818` per il conto, `/lettore/conto`) |
| **47332** runner tennis | `tennis_runner.py:3157` | come sopra per il tennis (`ladder_canale` condiviso: `tennis_runner.py:1461`, `TENNIS_LADDER_CANALE_MS` `:110`) | lettura + COMANDI | UI (`tennis`); Safe tennis (`safe_strategy/porta_ordini.py:76`); il ponte come lettore (`canale_bot_tennis.py:127` `InoltroPosizioni`, `:84` `porta_runner`) |
| **47333** Mike | `mike/service.py:6784`, avvio `:6840` | `mike_posizioni`, `mike_attivita` | solo lettura + `sveglia` | UI `getLocalChannel('mike')` (`components/mike/useMike.ts:292`, `useMikeEventoAlMs.ts:31`) |
| **47334** Omega | `omega_service.py:8587`, avvio `:8599` | `omega_posizioni`, `omega_attivita`, `omega_proposta` | solo lettura + `sveglia` | UI `getLocalChannel('omega')` (`pages/Omega.tsx:233`) |
| **47335** Safe (bot) | `bot_service.py:10569`, avvio `:10583` | `safe_posizioni_calcio`, `safe_posizioni_tennis`, `safe_attivita`, `safe_proposta` | solo lettura + `sveglia` | UI `getLocalChannel('safe')` (`components/safestrategy/useSafeBot.ts:387`) |
| **47336** scanner | `safe_strategy/service.py:91`, avvio `:2457` (`start_channel(.., "safe-scan", solo_lettura=True)`) | `scan_calcio`, `scan_tennis`, `scanner_stato` | solo lettura | `ClientScan` (`safe_strategy/canale_scan.py:312`) in `mike/service.py:7072`, `omega_service.py:760`, `bot_service.py:9541`, `stream/scores/scan_feed.py:138` (runner calcio: punteggi); `AscoltoScan` (sveglia, `sveglia_canale.py:255`) in `mike/service.py:6943`, `omega_service.py:8686`, `canale_bot_tennis.py:351`; UI (`useControlRoom.ts:1514`, `getLocalChannel('scanner')`) |
| **47337** ponte tennis | `tennis_bot_service.py:258` (`canale_bot.py:135`) | `tennis_bot_stato`, `tennis_bot_posizioni`, `tennis_bot_armamento` | solo lettura + `sveglia` | UI `getLocalChannel('tennis_bot')` (`useControlRoom.ts:1750`); il runner tennis ascolta l'armamento (`tennis_runner.py:1723`, `canale_bot_tennis.py:332`) |
| **47338** scalper | `scalper_service.py:607` (`canale_bot.py:142`) | `scalper_stato`, `scalper_sessioni` | solo lettura | UI `getLocalChannel('scalper')` (`useControlRoom.ts:1795`) |

Frontend: i canali sono 8 (`localChannel.ts:50-67`, `LocalSport`), URL `ws://127.0.0.1:<porta>` (`:96`); il client **non ritenta mai** una richiesta (`localChannel.ts` intestazione: «NON reinviare»,
money-critical). `svegliaBot()` (`:338`) manda `sveglia` dopo ogni scrittura riuscita sul DB (Mike 47333, Omega 47334, Safe 47335, bot tennis 47337; lo scalper non ha sveglia, `:326-330`).

Interruttori: i canali dei bot sono accesi/spenti da **variabili d'ambiente** (almeno 23 nomi distinti in produzione: `MIKE_CANALE_POSIZIONI`, `OMEGA_CANALE_POSIZIONI`, `SAFE_CANALE_POSIZIONI`, `SAFE_SCAN_CANALE`,
`TENNIS_BOT_CANALE`, `SCALPER_CANALE`, `ESITI_ORDINI_CANALE`, `PUNTEGGI_CANALE`, `MIKE_LEGGE_CANALE`, `OMEGA_LEGGE_CANALE`, `SAFE_BOT_LEGGE_CANALE`, `*_SVEGLIA_CANALE` x5, `*_ORDINI_VIA_CANALE` x4
(`SAFE_`, `SAFE_TENNIS_`, `OMEGA_`, `MIKE_`), `MOTORE_ORDINI_CANALE`, `CONTROL_SUL_CANALE`, `INTERRUTTORI_CANALE`, `MIKE_CONTO_CANALE`; conteggio da `git grep` sui nomi `*CANALE*`).
Il verso di default NON e' uniforme: `canale_bot.acceso` vale spento se non scritto (`canale_bot.py:159-166`), ma il conto di Mike e' acceso di serie (`mike/service.py:6797-6800`).
Quali siano accesi sul PC dell'utente **non e' stato verificato** (il `.env` non e' stato letto); l'inventario del 02/10 riporta «tutti accesi» (`INVENTARIO_ARCHITETTURA.md` C-21).

Altri canali non WebSocket: **Supabase** (RPC/REST, sezione 3); **file `ARRESTO`** (`arresto_ordinato.py`); **registri dei figli** su file (`prepareChildLogs`, `main.js:307`);
**il DB come coda** (`betfair_live_order_requests`, `live_backtest_requests`, richieste dei bot); nessun `multiprocessing` nel codice di produzione (verificato con `git grep -l "multiprocessing\|Process("` su `*.py` fuori da audit, test e tools: 0 file); le sessioni scalper sono `subprocess.Popen` (`scalper_service.py:702`).


## 6. Frontend: rotte, pagine, pannelli e da dove leggono

Script: `f01_frontend.py` (regex e grafo degli import su `frontend/src` non test: 389 file, 128.405 righe; esclude `fotografia/`, `anteprima/`, `certification/` e i test) ->
`uscite/f01_rotte.tsv`, `f01_rotte.md` (tabella sotto), `f01_pagine.txt` (per ogni pagina, ogni RPC/tabella/canale raggiungibile con `file:riga`), `f01_accessi_file.tsv` (ogni accesso ai dati:
`file`, `riga`, tipo, nome), `f01_riepilogo.txt`. Riscontro con il lavoro del primo giro: `strumenti/dati_J/accessi.tsv` (160 `rpc`, 4 dinamiche, 33 canali) e' coerente con
`f01` (159 `.rpc` letterali + 2 dinamici, 32 `getLocalChannel`): lo uso solo come controllo.

### 6.1 Struttura dell'app

- Ingresso `frontend/src/main.tsx` -> `App.tsx` (`QueryClientProvider` di TanStack Query, `HelmetProvider`, `BrowserRouter`, `SafeStrategyProvider` globale: valuta i segnali Safe anche fuori dalla
  pagina Safe, `App.tsx` intestazione). **Due alberi di rotte con gli stessi percorsi**: l'albero di default (`ui.shell='off'`, `App.tsx:110-296`, ogni pagina avvolta da `ProtectedRoute`) e quello del «guscio v2»
  (`RotteGuscioV2`, `App.tsx:48-93`: layout `ProtectedRoute > AppShell` con sidebar+testata e `<Outlet/>`, `components/shell/{AppShell,Sidebar,TestataGlobale,navigazione}`);
  sceglie `leggiUiShell()` (`frontend/src/lib/uiShell.ts:44`: chiave locale `ui.shell`, poi `VITE_UI_SHELL`, poi `off`; letta una volta, `App.tsx:98`).
  `/ladder-popout`, landing, `check-email`, `reset-password` e 404 sono fuori dal guscio (commento `App.tsx:40-47`). Le 26 rotte sono scritte DUE volte (una per albero): duplicazione da sapere.
- Protezione: `ProtectedRoute` (`components/ProtectedRoute`) su tutte le pagine tranne landing/check-email/reset-password/404 (login via Supabase auth: `components/landing/AuthSection.tsx`, tabella `leads`).
- **Un solo IPC Electron**: `desktop/preload.js:21` espone `window.alphascoreCanale = { token }` (sola lettura). Non ci sono `ipcRenderer`/`ipcMain`; nessuna edge function chiamata (`functions.invoke`: 0), nessun `fetch(` diretto (0),
  5 `window.open` (finestre Video/Stats/ladder staccato: `main.js:854-880` `setWindowOpenHandler`).
- Accesso ai dati (`f01_accessi_file.tsv`, conteggio dei punti di chiamata nei file non test): **159 `.rpc(` letterali (150 RPC distinte) + 2 dinamici**, **26 `.from(` su 17 tabelle**
  (`fixture_predictions` 6, `safe_strategy_requests` 4, `betfair_live_heartbeat` 2, e le altre una volta), **32 `getLocalChannel(`**, **59 punti realtime** (`.channel(`/`postgres_changes`),
  **73 punti di polling** (`setInterval`/`refetchInterval`), 16 `localStorage`.

### 6.2 Le 26 rotte

La colonna «chiusura» e' la chiusura transitiva degli import locali della pagina: e' un **limite superiore** di cio' che la pagina puo' toccare (una pagina che importa un hub come
`lib/live.ts` eredita tutte le sue RPC anche se ne usa una). Esempio: `/tennis` (`TennisDashboard.tsx`, 33 righe) risulta con 48 RPC perche' importa `lib/tennis.ts`; non significa che le chiami tutte.
I conteggi esatti di cio' che una pagina chiama davvero stanno in `f01_pagine.txt` (RPC con `file:riga`).

| rotta | pagina (`App.tsx` riga) | righe pagina | chiusura (file / righe) | RPC | tabelle `.from()` | canali locali (letterali) | realtime / polling |
|---|---|---|---|---|---|---|---|
| `*` | `pages/NotFound.tsx:1` (App.tsx:296) | 20 | 3 / 83 | 0 |  | - | 0 / 0 |
| `/` | `pages/LandingPage.tsx:1` (App.tsx:113) | 47 | 21 / 1541 | 0 | leads | - | 0 / 0 |
| `/analytics` | `pages/Analytics.tsx:1` (App.tsx:149) | 506 | 17 / 3989 | 24 | live_ladder, live_now, live_signals | - | 12 / 0 |
| `/board` | `pages/Board.tsx:1` (App.tsx:182) | 304 | 41 / 14653 | 48 | 8 (betfair_live_account, betfair_live_heartbeat, betfair_live_risk_state, live_ladder ...) |  + variabile | 33 / 5 |
| `/check-email` | `pages/CheckEmail.tsx:1` (App.tsx:114) | 91 | 3 / 154 | 0 |  | - | 0 / 0 |
| `/control-room` | `pages/ControlRoom.tsx:1` (App.tsx:270) | 1740 | 167 / 60168 | 110 | 15 (betfair_live_account, betfair_live_heartbeat, betfair_live_risk_state, live_follow ...) | calcio, mike, scalper, scanner, tennis, tennis_bot + variabile | 57 / 21 |
| `/dashboard` | `pages/Dashboard.tsx:1` (App.tsx:125) | 313 | 50 / 7270 | 20 | fixture_predictions | - | 0 / 0 |
| `/ladder-popout` | `pages/LadderPopout.tsx:1` (App.tsx:222) | 51 | 42 / 15255 | 48 | 8 (betfair_live_account, betfair_live_heartbeat, betfair_live_risk_state, live_ladder ...) |  + variabile | 33 / 5 |
| `/live-pnl` | `pages/LivePnl.tsx:1` (App.tsx:198) | 537 | 24 / 9541 | 48 | 8 (betfair_live_account, betfair_live_heartbeat, betfair_live_risk_state, live_ladder ...) |  + variabile | 33 / 3 |
| `/market-watch` | `pages/MarketWatch.tsx:1` (App.tsx:190) | 504 | 26 / 9663 | 48 | 8 (betfair_live_account, betfair_live_heartbeat, betfair_live_risk_state, live_ladder ...) | calcio, tennis + variabile | 33 / 4 |
| `/match-replay` | `pages/MatchReplay.tsx:1` (App.tsx:230) | 1280 | 84 / 35668 | 50 | 8 (betfair_live_account, betfair_live_heartbeat, betfair_live_risk_state, live_ladder ...) |  + variabile | 33 / 6 |
| `/mike` | `pages/Mike.tsx:1` (App.tsx:262) | 799 | 107 / 38886 | 100 | 15 (betfair_live_account, betfair_live_heartbeat, betfair_live_risk_state, live_follow ...) | mike + variabile | 52 / 9 |
| `/multi-ladder` | `pages/MultiLadder.tsx:1` (App.tsx:214) | 197 | 42 / 15401 | 48 | 8 (betfair_live_account, betfair_live_heartbeat, betfair_live_risk_state, live_ladder ...) |  + variabile | 33 / 5 |
| `/omega` | `pages/Omega.tsx:1` (App.tsx:246) | 912 | 80 / 32322 | 105 | 15 (betfair_live_account, betfair_live_heartbeat, betfair_live_risk_state, live_follow ...) | omega + variabile | 55 / 9 |
| `/report-personale` | `pages/ReportPersonale.tsx:1` (App.tsx:165) | 905 | 12 / 2373 | 17 |  | - | 0 / 0 |
| `/reset-password` | `pages/ResetPassword.tsx:1` (App.tsx:115) | 177 | 7 / 474 | 0 |  | - | 0 / 0 |
| `/safe-strategy` | `pages/SafeStrategy.tsx:1` (App.tsx:254) | 1705 | 122 / 45222 | 100 | 15 (betfair_live_account, betfair_live_heartbeat, betfair_live_risk_state, live_follow ...) | safe + variabile | 52 / 12 |
| `/segui-live` | `pages/SeguiLive.tsx:1` (App.tsx:173) | 1372 | 76 / 24207 | 57 | 8 (betfair_live_account, betfair_live_heartbeat, betfair_live_risk_state, live_ladder ...) | calcio + variabile | 36 / 21 |
| `/select-sport` | `pages/SelectSport.tsx:1` (App.tsx:117) | 211 | 5 / 315 | 0 |  | - | 0 / 0 |
| `/storico/calcio` | `pages/StoricoSport.tsx:1` (App.tsx:281) | 725 | 59 / 26995 | 97 | 15 (betfair_live_account, betfair_live_heartbeat, betfair_live_risk_state, live_follow ...) |  + variabile | 52 / 1 |
| `/storico/tennis` | `pages/StoricoSport.tsx:1` (App.tsx:289) | 725 | 59 / 26995 | 97 | 15 (betfair_live_account, betfair_live_heartbeat, betfair_live_risk_state, live_follow ...) |  + variabile | 52 / 1 |
| `/tennis` | `pages/TennisDashboard.tsx:1` (App.tsx:133) | 33 | 15 / 3975 | 48 | 8 (betfair_live_account, betfair_live_heartbeat, betfair_live_risk_state, live_ladder ...) | - | 33 / 0 |
| `/tennis/replay` | `pages/TennisReplay.tsx:1` (App.tsx:238) | 811 | 90 / 36829 | 52 | 8 (betfair_live_account, betfair_live_heartbeat, betfair_live_risk_state, live_ladder ...) |  + variabile | 33 / 7 |
| `/tennis/terminal` | `pages/TennisTerminal.tsx:1` (App.tsx:141) | 320 | 56 / 18234 | 48 | 8 (betfair_live_account, betfair_live_heartbeat, betfair_live_risk_state, live_ladder ...) |  + variabile | 33 / 10 |
| `/trade-journal` | `pages/TradeJournal.tsx:1` (App.tsx:206) | 328 | 6 / 1547 | 19 | betfair_live_account, betfair_live_heartbeat, betfair_live_risk_state | - | 10 / 0 |
| `/watchlist` | `pages/Watchlist.tsx:1` (App.tsx:157) | 154 | 19 / 4252 | 29 | live_ladder, live_now, live_signals | - | 10 / 1 |

Descrizione delle pagine (prima riga di commento del file della pagina; funzionalita' complete nell'`01_FUNZIONALITA.md`):
`/board` «Programma di oggi» (due tab calcio/tennis alimentate SOLO dai push `board` dei due canali locali, `pages/Board.tsx:1-5`); `/control-room` «IL BANCO DELLA GIORNATA»
(tre bot Omega/Safe/Mike + scalper + tennis in una pagina, `pages/ControlRoom.tsx:1-6`, 1.740 righe + `useControlRoom.ts` 4.322); `/omega` (bot Correct Score LAY, `Omega.tsx:1-5`);
`/safe-strategy` (radar + bot, `SafeStrategy.tsx:1-6`); `/mike` (Under 3.5 / Over 4.5 paper-first, `Mike.tsx:1-6`); `/segui-live` (partite sottoscritte allo stream, dettaglio realtime, `SeguiLive.tsx:1-5`);
`/multi-ladder` (N ladder affiancati, `MultiLadder.tsx:1-4`); `/ladder-popout` (un ladder in finestra staccata, `LadderPopout.tsx:1-6`); `/market-watch` (stile Fairbot, `MarketWatch.tsx:1-3`);
`/live-pnl` (P&L di giornata, fonti `get_live_settled`, `LivePnl.tsx:1-3`); `/trade-journal` (review post-sessione, `TradeJournal.tsx:1-3`); `/report-personale` (KPI, equity, drawdown,
`ReportPersonale.tsx:1-3`); `/watchlist` (Da valutare / Giocate / Scartate, `Watchlist.tsx:1-3`); `/analytics` (pagella per motore e mercato, solo RPC aggregate, `Analytics.tsx:1-3`);
`/dashboard` (calcio: partite del giorno, previsioni ML, ritardi, direzioni, backtest automatico: componenti in `components/dashboard/`); `/tennis`, `/tennis/terminal`, `/tennis/replay`
(«Screen 2», «Screen 3 - Tennis Trading Terminal», «REPLAY TENNIS»); `/match-replay` (Football Trading Simulator, `MatchReplay.tsx:1-5`); `/storico/calcio` e `/storico/tennis`
(`StoricoSport.tsx:1-4`, stessa pagina con parametro sport); `/select-sport`, `/`, `/check-email`, `/reset-password`, `*`.

### 6.3 I moduli «hub» (`frontend/src/lib/`): dove stanno le RPC

Un'unica libreria tipizzata per area (non un client generico): `lib/tennis.ts` 22 RPC, `liveOrders.ts` 19, `analytics.ts` 14, `omega.ts` 11, `safeBot.ts` 9, `betfair.ts` 9, `personalReport.ts` 8, `live.ts` 7,
`dailyHistory.ts` 7, `scalperControlRoom.ts` 6, `mike.ts` 6 (`f01_riepilogo.txt`, seconda sezione). I modelli di stato per bot: `mike.ts` 2.454 righe, `safeBot.ts` 2.256, `safeStrategy.ts` 1.731, `omega.ts` 1.655,
`interruttori.ts` 1.533 (interruttori e modalita' di tutti i bot), `controlRoom.ts` 1.220, piu' `useControlRoom.ts` 4.322 (`components/controlroom/`).
Il trasporto locale: `lib/localChannel.ts` (client WS puro, 8 canali, `:50-67`), `lib/localTransport.ts` (fallback DB, `:84`), `lib/canaleRunner.ts`, `lib/flussoStreamRunner.ts`, `lib/usePosizioniCanale.ts`, `lib/useOrdiniCanale.ts`.
`lib/replayBotCatalogo.ts` (11.099 righe) e' GENERATO (1.1).

```
== ACCESSI AI DATI PER FILE (non test), primi 45 per RPC distinte (un file di lib/ e' il wrapper tipizzato usato dalle pagine) ==
lib/tennis.ts                                             rpc= 22 tab= 2 canali= 0 realtime=13 fetch= 0 intervalli= 0
lib/liveOrders.ts                                         rpc= 19 tab= 3 canali= 0 realtime=10 fetch= 0 intervalli= 0
lib/analytics.ts                                          rpc= 14 tab= 0 canali= 0 realtime= 2 fetch= 0 intervalli= 0
lib/omega.ts                                              rpc= 11 tab= 0 canali= 0 realtime= 4 fetch= 0 intervalli= 0
lib/safeBot.ts                                            rpc=  9 tab= 5 canali= 0 realtime= 7 fetch= 0 intervalli= 0
lib/betfair.ts                                            rpc=  9 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 0
lib/personalReport.ts                                     rpc=  8 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 0
lib/live.ts                                               rpc=  7 tab= 3 canali= 0 realtime=10 fetch= 0 intervalli= 0
lib/dailyHistory.ts                                       rpc=  7 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 0
lib/scalperControlRoom.ts                                 rpc=  6 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 0
lib/mike.ts                                               rpc=  6 tab= 1 canali= 0 realtime= 2 fetch= 0 intervalli= 0
lib/watchlist.ts                                          rpc=  5 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 0
lib/omegaMissions.ts                                      rpc=  5 tab= 0 canali= 0 realtime= 3 fetch= 0 intervalli= 0
lib/scalper.ts                                            rpc=  3 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 0
lib/reportistiche.ts                                      rpc=  3 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 0
lib/omegaProposte.ts                                      rpc=  3 tab= 0 canali= 0 realtime= 2 fetch= 0 intervalli= 0
lib/tennisReplay.ts                                       rpc=  2 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 0
lib/replayBot.ts                                          rpc=  2 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 0
lib/proposteUscite.ts                                     rpc=  2 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 0
lib/marketFrequency.ts                                    rpc=  2 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 0
lib/direzione.ts                                          rpc=  2 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 0
lib/controlRoomProposte.ts                                rpc=  2 tab= 1 canali= 0 realtime= 2 fetch= 0 intervalli= 0
lib/replayVerificaBarraDb.ts                              rpc=  1 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 0
lib/mediaUnderAttiva.ts                                   rpc=  1 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 0
lib/marketDelays.ts                                       rpc=  1 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 0
lib/fixtureModels.ts                                      rpc=  1 tab= 1 canali= 0 realtime= 0 fetch= 0 intervalli= 0
pages/TennisTerminal.tsx                                  rpc=  0 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 1
pages/TennisReplay.tsx                                    rpc=  0 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 1
pages/StoricoSport.tsx                                    rpc=  0 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 1
pages/SeguiLive.tsx                                       rpc=  0 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 5
pages/SafeStrategy.tsx                                    rpc=  0 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 3
pages/Omega.tsx                                           rpc=  0 tab= 0 canali= 1 realtime= 0 fetch= 0 intervalli= 3
pages/Mike.tsx                                            rpc=  0 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 2
pages/MatchReplay.tsx                                     rpc=  0 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 1
pages/MarketWatch.tsx                                     rpc=  0 tab= 0 canali= 2 realtime= 0 fetch= 0 intervalli= 4
pages/LivePnl.tsx                                         rpc=  0 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 3
pages/Dashboard.tsx                                       rpc=  0 tab= 1 canali= 0 realtime= 0 fetch= 0 intervalli= 0
pages/Board.tsx                                           rpc=  0 tab= 0 canali= 1 realtime= 0 fetch= 0 intervalli= 1
lib/usePosizioniCanale.ts                                 rpc=  0 tab= 0 canali= 1 realtime= 0 fetch= 0 intervalli= 0
lib/useOrdiniCanale.ts                                    rpc=  0 tab= 0 canali= 1 realtime= 0 fetch= 0 intervalli= 0
lib/useApplicaBot.ts                                      rpc=  0 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 1
lib/uiShell.ts                                            rpc=  0 tab= 0 canali= 0 realtime= 0 fetch= 0 intervalli= 0
lib/tacticalEngine.ts                                     rpc=  0 tab= 1 canali= 0 realtime= 0 fetch= 0 intervalli= 0
lib/safeStrategyScan.ts                                   rpc=  0 tab= 2 canali= 0 realtime= 4 fetch= 0 intervalli= 0
lib/localTransport.ts                                     rpc=  0 tab= 0 canali= 1 realtime= 0 fetch= 0 intervalli= 1

TOTALE frontend/src non test: RPC distinte 150, tabelle .from distinte 17, chiamate .rpc non letterali 2
```

### 6.4 Pannelli (file piu' grandi in `frontend/src/components/`, >= 380 righe)

Elenco dal tsv di `s01` (non descrive la funzione di ogni pannello: e' compito di `01_FUNZIONALITA.md`): `controlroom/PannelloBot.tsx` 1.053, `live/LadderView.tsx` 2.984 (il ladder, usato da 8 rotte), `mike/MikeMatchCard.tsx` 1.174,
`live/ScalperPanel.tsx` 975, `omega/MissionPanel.tsx` 946, `safestrategy/BotParamsSheet.tsx` 932 (parametri editabili del bot Safe), `controlroom/PosizioniChiuse.tsx` 917, `safestrategy/SafeTradesTable.tsx` 873, `live/RiskRulesPanel.tsx` 764,
`omega/MissionCard.tsx` 723, `watchlist/MultiTradeForm.tsx` 714, `omega/MatchTradesTable.tsx` 709, `tennis/TennisBotPanel.tsx` 685, `watchlist/WatchlistPanel.tsx` 682, `live/XHedgePanel.tsx` 679, `controlroom/SchedaPropostaOpportunita.tsx` 657,
`live/GridView.tsx` 653, `omega/ManualPanel.tsx` 644, `dashboard/DirezioniReport.tsx` 640, `safestrategy/OpportunityGroup.tsx` 637, `tennis/TennisMatchStats.tsx` 633, `live/DutchingPanel.tsx` 617, `live/LiveTradingPanel.tsx` 612,
`controlroom/SchedaPartita.tsx` 607, `dashboard/RitardiPanel.tsx` 598, `dashboard/MarketFrequencyPanel.tsx` 550, `tennis/TennisMatchesList.tsx` 535, `dashboard/MatchesList.tsx` 511, `controlroom/CashOutGlobale.tsx` 489,
`trading/EventPnlTable.tsx` 479, `controlroom/DettaglioRigaView.tsx` 479, `trading/CashOutButton.tsx` 471, `live/LiveControlsPanel.tsx` 463, `dashboard/DirezioneDashboard.tsx` 455, `dashboard/BacktestAutomatico.tsx` 426,
`controlroom/testata/FasciaStop.tsx` 418, `watchlist/TradeForm.tsx` 414, `landing/AuthSection.tsx` 398, `safestrategy/SafeStrategyProvider.tsx` 389.
Cartelle di componenti per righe di codice (sezione 1.5): `controlroom` 17.426 (55 file), `live` 9.831, `dashboard` 6.399, `safestrategy` 5.125, `trading` 4.346 (design system condiviso), `omega` 3.262, `tennis` 2.549, `replay` 2.268, `mike` 2.148, `watchlist` 1.980.

### 6.5 Da dove leggono i bot e la Control Room (percorso del dato)

- **Dal canale locale** (push, senza DB): `/board` (programma del giorno: topic `board`), ladder (`LadderView`, topic `ladder`/`now`), posizioni/ordini (`lib/usePosizioniCanale.ts`, `useOrdiniCanale.ts`),
  freno e ordini reali (`components/controlroom/RigaFreno.tsx:122`, `RigaOrdiniReali.tsx:122`, `RigaCapacitaMercati.tsx:31`: canale `calcio`), righe di Mike/Omega/Safe (`useMike.ts:292`, `Omega.tsx:233`, `useSafeBot.ts:387`),
  scanner (`useControlRoom.ts:1514`, `:1567`), ponte tennis (`:1750`), scalper (`:1795`), conto (`:1923`, `:1937`), tennis vivo (`useTennisVivo.ts:111`), x-hedge (`XHedgePanel.tsx:176`), stream mercato (`FlussoStreamBanner.tsx:16`).
- **Dal DB via RPC** (poll e realtime): tutto lo storico (`dailyHistory.ts`, `posizioniChiuse.ts`), i comandi dei bot (`mike_activate`, `safe_activate`, `omega_activate`, `scalper_activate`, `tennis_bot_arm`: `lib/mike.ts`,
  `safeBot.ts`, `omega.ts`, `scalperControlRoom.ts`, `tennis.ts`), le impostazioni di rischio (`liveOrders.ts`: `get_live_settings`, `set_live_kill_switch`, `set_live_order_mode`), l'analitica.
- **Comandi ordine**: dalla pagina al runner via `LocalChannel.request('order')` con token (`localChannel.ts`), con ripiego sulla coda DB `request_betfair_live_order` (`lib/liveOrders.ts:133`, `lib/localTransport.ts`).
  Il client non ritenta mai (money-critical).


## 7. Cartelle di radice e `*.py` di radice: VIVA / MORTA / ARCHIVIO

Script: `k01_radice.py` (righe, ultimo commit, file su disco non tracciati: `uscite/k01_radice.tsv`) e `k03_classifica_radice.py` (classifica con la prova:
`uscite/k03_classifica.tsv`, `k03_riepilogo.txt`, `k03_cartelle.md`, `k03_file_radice.md`; fonti: `s02_*` per gli import, scansione dei lanciatori automatici
`.github/workflows/*.yml`, `*.bat`/`*.ps1` di radice, `desktop/*.js`, `Betfair/stream/{avvio_app,watchdog}.py`, `package.json`; citazioni nel frontend; `git log` per le date).

**Regola** (scritta nello script, `k03_classifica_radice.py` intestazione):
VIVA = importata da almeno un file di PRODUZIONE esterno alla voce, oppure avviata da un lanciatore automatico (workflow, `.bat`/`.ps1` richiamato da altro, `desktop/main.js`, `avvio_app.py`);
ARCHIVIO = nessuna delle due ma importata da test/strumenti/audit, oppure script con `__main__` lanciabile a mano, oppure citata dalla UI come istruzione di lancio manuale, oppure cartella storica (`AUDIT_*`, `SCHEMI_BOT`, `docs`, `registrazioni_banco`, `migrations`, `sql`);
MORTA = nessun importatore, nessuna citazione, nessun lanciatore, nessun `__main__`; TEST = `test_*.py` di radice.
**Limiti**: una voce importata solo da un'altra voce a sua volta non raggiungibile conta come VIVA (nessun calcolo di raggiungibilita' dai punti d'ingresso); la classificazione dice cosa
il REPO collega, non cosa l'utente lancia a mano sul suo PC.

Elenco completo di tutte le voci (VIVA/ARCHIVIO/MORTA/TEST) in `uscite/k03_riepilogo.txt`. Sintesi: 54 VIVE, 64 ARCHIVIO, 18 MORTE, 1 NON_VERIFICABILE, 20 TEST di radice.

### 7.1 Cartelle di radice

| cartella | file | righe py (prod / tutte) | ultimo commit | importata da (file di produzione esterni) | lanciatore automatico | classe | prova |
|---|---:|---:|---|---:|---|---|---|
| `.agent` | 1 | 0 / 0 | 2026-03-03 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `.claude` | 1 | 0 / 0 | 2026-09-17 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `.github` | 10 | 0 / 0 | 2026-10-04 | 0 | - | **VIVA** | 10 workflow GitHub Actions: sono i lanciatori cloud dei job di calcolo (vedi sezione 7 del documento) |
| `ARCHITETTURA_2026-10` | 4 | 0 / 211 | 2026-10-08 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `AUDIT_2026-09-24` | 7 | 0 / 0 | 2026-09-24 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `AUDIT_2026-09-25` | 658 | 0 / 13286 | 2026-10-04 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `AUDIT_2026-09-26` | 18 | 0 / 921 | 2026-09-26 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `AUDIT_2026-09-28` | 183 | 0 / 4752 | 2026-09-29 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `AUDIT_2026-09-29` | 71 | 0 / 960 | 2026-09-29 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `AUDIT_2026-09-30` | 224 | 0 / 1944 | 2026-09-30 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `AUDIT_2026-10-01` | 318 | 0 / 421 | 2026-10-01 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `AUDIT_2026-10-02` | 144 | 0 / 3306 | 2026-10-02 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `AUDIT_2026-10-04` | 130 | 0 / 1132 | 2026-10-05 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `AUDIT_2026-10-05` | 52 | 0 / 616 | 2026-10-06 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `AUDIT_2026-10-06` | 37 | 0 / 463 | 2026-10-06 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `AUDIT_2026-10-07` | 182 | 0 / 2130 | 2026-10-07 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `AUDIT_2026-10-08` | 33 | 0 / 0 | 2026-10-08 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `Ai Engine` | 54 | 8845 / 10402 | 2026-09-21 | 11 | .github/workflows/retrain_models.yml:222 | **VIVA** | importata da 11 file di produzione esterni (es. Betfair/betfair_report_manager.py); lanciatore .github/workflows/retrain_models.yml:222 |
| `Betfair` | 941 | 169111 / 382414 | 2026-10-08 | 19 | .github/workflows/hazard_atlas.yml:109, .github/workflows/weekly_poisson_calibration.yml:60, aggiorna_modelli.bat:4 | **VIVA** | cuore del prodotto (avviata da desktop/main.js o servita dall'app) |
| `Prediction` | 8 | 3911 / 6983 | 2026-09-26 | 3 | .github/workflows/predictions_results_backfill.yml:78, .github/workflows/today_predictions_backfill.yml:44 | **VIVA** | importata da 3 file di produzione esterni (es. AGGIORNA_CAMPO_db_json_analisi.py); lanciatore .github/workflows/predictions_results_backfill.yml:78; citata dal frontend frontend/src/components/dashboard/HeroMatch.tsx:1 |
| `SCHEMI_BOT` | 93 | 0 / 1640 | 2026-10-02 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `Telegram bot` | 12 | 0 / 0 | 2026-06-22 | 0 | - | **NON_VERIFICABILE** | Edge Functions Supabase in Deno/TypeScript (supabase/functions/telegram-bot, make-daily-post): il codice non e' Python, non e' importato da nulla nel repo; lo stato di deploy e' sul cloud |
| `_AUDIT_2026_05` | 109 | 0 / 1887 | 2026-06-10 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `desktop` | 7 | 0 / 0 | 2026-10-06 | 0 | Betfair/stream/avvio_app.py:11, Betfair/stream/watchdog.py:17 | **VIVA** | cuore del prodotto (avviata da desktop/main.js o servita dall'app) |
| `docs` | 2 | 0 / 0 | 2026-07-17 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `football_data_scraper` | 7 | 1392 / 1392 | 2026-03-13 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `frontend` | 946 | 0 / 0 | 2026-10-08 | 0 | desktop/main.js:174, desktop/package.json:5 | **VIVA** | cuore del prodotto (avviata da desktop/main.js o servita dall'app) |
| `laboratorio` | 20 | 5356 / 5601 | 2026-09-25 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 1 importazioni da test); ha __main__ lanciabile a mano |
| `market_intelligence` | 12 | 2513 / 2513 | 2026-06-10 | 1 | - | **VIVA** | importata da 1 file di produzione esterni (es. Ai Engine/ai_engine/predict_fixture.py) |
| `migrations` | 175 | 294 / 294 | 2026-10-08 | 1 | .github/workflows/hazard_atlas.yml:91 | **ARCHIVIO** | cartella storica o di dati: SQL applicato dall'utente |
| `registrazioni_banco` | 7 | 0 / 0 | 2026-10-05 | 0 | - | **ARCHIVIO** | cartella storica o di dati: audit, schemi, documenti o registrazioni |
| `sql` | 9 | 909 / 909 | 2026-06-19 | 0 | - | **ARCHIVIO** | cartella storica o di dati: SQL applicato dall'utente |
| `tactical_engine` | 20 | 1515 / 2817 | 2026-09-26 | 2 | - | **VIVA** | importata da 2 file di produzione esterni (es. Betfair/stream/engine/live_engine_pro.py); citata dal frontend frontend/src/lib/tacticalEngine.ts:61 |
| `tools` | 5 | 0 / 839 | 2026-10-07 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `value_engine` | 12 | 729 / 859 | 2026-06-17 | 4 | - | **VIVA** | importata da 4 file di produzione esterni (es. Betfair/omega/omega_model.py) |

Note, ognuna con la sua prova:

1. **`value_engine/` e `tactical_engine/` sono nel percorso dei bot, non laboratori.** `Betfair/omega/omega_model.py:261,720-721` importa `value_engine.goal_timing`, `value_engine.devig`,
   `value_engine.poisson_total`; `Betfair/stream/engine/live_engine_pro.py:26,274-275` importa `tactical_engine.dixon_coles` e `value_engine.*`; anche `Betfair/safe_strategy/opportunity.py`
   e `Betfair/stream/engine/live_engine.py` importano `value_engine` (`git grep "from value_engine"`). Sono 729 + 1.515 righe di Python «di produzione» fuori da `Betfair/`.
2. **`Ai Engine/`** (8.845 righe di produzione, 54 file): importata come pacchetto `ai_engine` da 11 file di produzione (es. `Betfair/betfair_report_manager.py:26-27`: `predict_fixture`, `seriea_model_export`) e lanciata dal workflow
   `retrain_models.yml:222`; dopo la correzione dell'alias, 40 file Python, 11 mai importati da produzione (script `__main__`).
3. **`market_intelligence/`** (2.513 righe): VIVA solo perche' `Ai Engine/ai_engine/predict_fixture.py` la importa; **nessun workflow la lancia** (`grep market_intelligence .github/workflows` = 0). `predict_fixture.py` e' a sua volta
   lanciata da `.bat` manuali (`aggiorna_report.bat:21` via `betfair_report_manager.py`): cioe' VIVA ma raggiungibile dal repo solo da un percorso manuale. Contiene 25.009 righe di JSON di cache.
4. **`laboratorio/`** (5.356 righe di produzione-per-categoria, 20 file): ARCHIVIO. Nessun file di produzione la importa; contiene la copia di lavoro dello scalper (`scalper_lab/scalper_bot_base.py`, 4.3) e `tennis_lab/`; importata da 1 importazione di test
   (`s02_moduli.tsv`). Citata dal contratto di strada unica come laboratorio spostato (`AUDIT_2026-09-25/LABORATORIO_SPOSTAMENTO_2026-09-25.md`).
5. **`football_data_scraper/`** (1.392 righe, ultimo commit 13/03/2026): ARCHIVIO, nessun importatore ne' lanciatore; i workflow lo nominano solo per la parola `backfill`.
6. **`Telegram bot/`** (12 file, 3.071 righe, Deno/TypeScript): sono due Edge Functions Supabase (`supabase/functions/telegram-bot/index.ts` 811 righe, `make-daily-post/index.ts`) piu' una migrazione di schema
   (`supabase/migrations/20260220161707_remote_schema.sql`) e una batteria di calcolo (`_calc_validation/`). Il codice Python non la usa (solo `value_engine/generate_battery.py:17` la nomina). **Se sia deployata non e' verificabile dal repo.**
7. **`tools/`** (5 file: `omega_validate_models.py`, `omega_watch.py`, `replay_barra_fixture.py`, `test_replay_barra_fixture.py`, `review/review-control-room.js`): strumenti a riga di comando; `replay_barra_fixture.py` e' citato nei commenti delle fixture del frontend
   (`frontend/src/lib/__fixtures__/replayBarraTutte.ts:8,44`).
8. **`sql/`** (9 file: 886 righe di SQL + 909 di Python `_build_wc_xlsx_2013.py`, `_cert_wc_fetch.py`, ...): ARCHIVIO; i 4 script Python sono del gruppo B senza citazioni (2.5). **`migrations/`**: 175 file, 33.835 righe di SQL, piu' 1 file Python di 294 righe richiamato dal workflow `hazard_atlas.yml:91`; le migrazioni le applica l'utente (`CLAUDE.md`).
9. **Cartelle `AUDIT_*`, `_AUDIT_2026_05`, `SCHEMI_BOT`, `ARCHITETTURA_2026-10`**: sono storia di lavoro (relazioni, sonde, patch, misure, 368 script Python di audit). 1.542.040 righe di «altro» (1.6) vivono quasi tutte qui. `registrazioni_banco/` ha 7 file tracciati (fra cui 2 coppie `.raw/.scores.jsonl.gz` di partite registrate: `35760084`, `35797769`).
10. **Cartelle di radice NON tracciate da git** (esistono sul disco; `git status` le mostra `??`, `k01_radice.tsv` colonna `disco_non_tracciati`): `_checkpoint_2026-09-28/` (58.058 file: cartelle `agent-*` e `ORA_DEL_CHECKPOINT.txt`; natura non indagata), `_validazione_20260711/` (317 file), `_validazione_tennis_1tick_20260710/` (450), `_banco_alms_f3/` (vuota),
    `36006953/` (1 file, `36006953.recmeta.jsonl`), `_live_raw/` (250 file, ignorata da `.gitignore:20`: le registrazioni grezze), `_logs/` (197, ignorata `.gitignore:37`), `_shardlogs/` (6), `.env` (ignorato). Non sono nel repo: non sono ne' vive ne' morte per il codice; sono dati locali.
    **Reperto**: quattro documenti citati dalle istruzioni di progetto o dal brief come riferimento — `ESECUZIONE_LIVE.md`, `SPEC_STRATEGIA_S.md` (`CLAUDE.md`, «Documenti di riferimento»), `SAFE_STRATEGY_DOSSIER.md`, `TENNIS_BOT_DOSSIER.md` — risultano **non tracciati** (`git status` `??`, `git log -- ESECUZIONE_LIVE.md` vuoto): non sono mai stati committati.
    In totale `git status` mostra 164 voci `??` (k01: 85 file/cartelle di radice non tracciati, fra cui `*.log`/`*.json` temporanei e script `_adhoc_*.py`, `_tacticai_*.py`, `test_simple.py`, `verify_mapping.py`).

### 7.2 File di radice (88 `.py`, 11 `.bat`/`.ps1`, 20 test)

| file di radice | righe | ultimo commit | importato da (prod) | lanciatore automatico / citazioni | classe | prova |
|---|---:|---|---:|---|---|---|
| `AGGIORNA_CAMPO_db_json_analisi.py` | 404 | 2026-06-10 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `_certify_betfair.py` | 87 | 2026-06-24 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `_certify_betfair_full.py` | 37 | 2026-06-24 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `_certify_delay_context.py` | 102 | 2026-06-24 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `_certify_direction.py` | 248 | 2026-06-25 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `_certify_direction_report.py` | 641 | 2026-06-25 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `_certify_personal_report.py` | 511 | 2026-06-24 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `_certify_signal_context.py` | 96 | 2026-06-24 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `_league_eval.py` | 100 | 2026-06-24 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `_stack_eval.py` | 118 | 2026-06-24 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `admin_reset_password.py` | 93 | 2026-06-22 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `aggiorna_mm_sheets.py` | 542 | 2026-07-03 | 0 | aggiorna_report.bat:25, aggiorna_report_veloce.bat:21, aggiorna_solo_fogli.bat:14 | **VIVA** | lanciatore aggiorna_report.bat:25 |
| `aggiorna_modelli.bat` | - | 2026-04-02 | - | - | **ARCHIVIO** | script di lancio manuale (nessun lanciatore automatico lo richiama) |
| `aggiorna_quote_betfair.bat` | - | 2026-07-10 | - | - ; UI: frontend/src/lib/betfair.ts:102 | **ARCHIVIO** | citata dalla UI come istruzione di lancio manuale: frontend/src/lib/betfair.ts:102 |
| `aggiorna_report.bat` | - | 2026-06-24 | - | aggiorna_modelli.bat:34 ; UI: frontend/src/components/dashboard/MatchesList.tsx:278 | **VIVA** | lanciatore aggiorna_modelli.bat:34; citata dal frontend frontend/src/components/dashboard/MatchesList.tsx:278 |
| `aggiorna_report_betfair.bat` | - | 2026-07-06 | - | importa_ultimi_15_giorni.bat:12 | **VIVA** | lanciatore importa_ultimi_15_giorni.bat:12 |
| `aggiorna_report_veloce.bat` | - | 2026-07-10 | - | - | **ARCHIVIO** | script di lancio manuale (nessun lanciatore automatico lo richiama) |
| `aggiorna_solo_fogli.bat` | - | 2026-03-30 | - | - | **ARCHIVIO** | script di lancio manuale (nessun lanciatore automatico lo richiama) |
| `aggiorna_solo_fogli.py` | 46 | 2026-03-16 | 0 | aggiorna_solo_fogli.bat:10 | **VIVA** | lanciatore aggiorna_solo_fogli.bat:10 |
| `analytics_market_stats.py` | 307 | 2026-06-22 | 1 | - | **VIVA** | importata da 1 file di produzione esterni (es. enrich_analytics_snapshots.py) |
| `analytics_settlement.py` | 125 | 2026-06-22 | 4 | - | **VIVA** | importata da 4 file di produzione esterni (es. _certify_direction_report.py) |
| `analyze_recovery.py` | 283 | 2026-06-10 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `analyze_threshold.py` | 308 | 2026-06-10 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `api_client.py` | 137 | 2026-09-25 | 14 | - | **VIVA** | importata da 14 file di produzione esterni (es. Betfair/stream/scores/api_football.py) |
| `api_quota.py` | 345 | 2026-09-25 | 2 | - | **VIVA** | importata da 2 file di produzione esterni (es. league_orchestrator.py) |
| `avvia_omega_service.bat` | - | 2026-07-12 | - | - ; UI: frontend/src/components/omega/ManualPanel.tsx:362 | **ARCHIVIO** | citata dalla UI come istruzione di lancio manuale: frontend/src/components/omega/ManualPanel.tsx:362 |
| `avvia_scalper_service.bat` | - | 2026-07-02 | - | - ; UI: frontend/src/components/live/HabitatCard.tsx:66 | **ARCHIVIO** | citata dalla UI come istruzione di lancio manuale: frontend/src/components/live/HabitatCard.tsx:66 |
| `backfill_poisson_calibrated.py` | 209 | 2026-06-22 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `betfair_full_odds.py` | 300 | 2026-07-10 | 0 | aggiorna_report.bat:30 ; UI: frontend/src/components/dashboard/BetfairOddsPanel.tsx:110 | **VIVA** | lanciatore aggiorna_report.bat:30; citata dal frontend frontend/src/components/dashboard/BetfairOddsPanel.tsx:110 |
| `betfair_tennis_odds.py` | 322 | 2026-09-09 | 0 | desktop/main.js:480 | **VIVA** | lanciatore desktop/main.js:480 |
| `build_analytics_signals.py` | 452 | 2026-09-26 | 2 | .github/workflows/predictions_results_backfill.yml:96 | **VIVA** | importata da 2 file di produzione esterni (es. _certify_direction.py); lanciatore .github/workflows/predictions_results_backfill.yml:96 |
| `build_direzione.py` | 238 | 2026-09-21 | 0 | .github/workflows/predictions_results_backfill.yml:163 | **VIVA** | lanciatore .github/workflows/predictions_results_backfill.yml:163 |
| `build_inplay_intensity.py` | 331 | 2026-06-29 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `calibration_analysis.py` | 622 | 2026-06-10 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `certify_backtest_strategy.py` | 202 | 2026-06-23 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `check_gh.py` | 13 | 2026-04-02 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `cleanup_models.py` | 138 | 2026-03-10 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `cloud_retrain_shard.py` | 373 | 2026-09-21 | 0 | .github/workflows/retrain_models.yml:281 | **VIVA** | lanciatore .github/workflows/retrain_models.yml:281 |
| `compress_models.py` | 197 | 2026-03-16 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `compute_ml_post_calibration.py` | 320 | 2026-06-16 | 0 | .github/workflows/ml_calibration.yml:78 | **VIVA** | lanciatore .github/workflows/ml_calibration.yml:78 |
| `config.py` | 58 | 2026-02-25 | 17 | - | **VIVA** | importata da 17 file di produzione esterni (es. Betfair/betfair_report_manager.py) |
| `daily_yesterday_backfill.py` | 396 | 2026-09-25 | 0 | .github/workflows/daily_yesterday_backfill.yml:36 | **VIVA** | lanciatore .github/workflows/daily_yesterday_backfill.yml:36 |
| `db_client.py` | 410 | 2026-09-28 | 108 | - | **VIVA** | importata da 108 file di produzione esterni (es. AGGIORNA_CAMPO_db_json_analisi.py) |
| `db_delete_retry.py` | 53 | 2026-09-25 | 6 | - | **VIVA** | importata da 6 file di produzione esterni (es. injuries_backfill.py) |
| `direzione.py` | 77 | 2026-06-24 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `enrich_analytics_snapshots.py` | 583 | 2026-09-24 | 0 | .github/workflows/predictions_results_backfill.yml:131 | **VIVA** | lanciatore .github/workflows/predictions_results_backfill.yml:131 |
| `fetch_logs.ps1` | - | 2026-04-02 | - | - | **ARCHIVIO** | script di lancio manuale (nessun lanciatore automatico lo richiama) |
| `fetch_summary.ps1` | - | 2026-04-02 | - | - | **ARCHIVIO** | script di lancio manuale (nessun lanciatore automatico lo richiama) |
| `fix_storico_prob.py` | 123 | 2026-06-22 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `fixtures_backfill.py` | 210 | 2026-02-12 | 2 | - | **VIVA** | importata da 2 file di produzione esterni (es. daily_yesterday_backfill.py) |
| `generate_dc_rho.py` | 259 | 2026-09-21 | 0 | .github/workflows/weekly_poisson_calibration.yml:54 | **VIVA** | lanciatore .github/workflows/weekly_poisson_calibration.yml:54 |
| `generate_dynamic_cal.py` | 596 | 2026-09-21 | 0 | .github/workflows/weekly_poisson_calibration.yml:36 | **VIVA** | lanciatore .github/workflows/weekly_poisson_calibration.yml:36 |
| `import_betfair_operations.py` | 428 | 2026-07-06 | 0 | aggiorna_report_betfair.bat:21, importa_ultimi_15_giorni.bat:19 | **VIVA** | lanciatore aggiorna_report_betfair.bat:21 |
| `importa_ultimi_15_giorni.bat` | - | 2026-07-06 | - | - | **ARCHIVIO** | script di lancio manuale (nessun lanciatore automatico lo richiama) |
| `injuries_backfill.py` | 354 | 2026-09-25 | 1 | - | **VIVA** | importata da 1 file di produzione esterni (es. season_aggregates.py) |
| `install_worker_autostart.ps1` | - | 2026-06-28 | - | - | **ARCHIVIO** | script di lancio manuale (nessun lanciatore automatico lo richiama) |
| `league_orchestrator.py` | 262 | 2026-09-25 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 3 importazioni da test); ha __main__ lanciabile a mano |
| `leagues_mapper.py` | 406 | 2026-10-04 | 0 | .github/workflows/leagues_mapper.yml:47 | **VIVA** | lanciatore .github/workflows/leagues_mapper.yml:47 |
| `load_poisson_calibration_to_db.py` | 72 | 2026-06-20 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `logger.py` | 100 | 2026-07-03 | 9 | - | **VIVA** | importata da 9 file di produzione esterni (es. Prediction/today_predictions_backfill.py) |
| `master_backtest.py` | 1660 | 2026-09-21 | 3 | - | **VIVA** | importata da 3 file di produzione esterni (es. generate_dc_rho.py) |
| `merge_engine_signals.py` | 280 | 2026-09-26 | 0 | .github/workflows/predictions_results_backfill.yml:108 | **VIVA** | lanciatore .github/workflows/predictions_results_backfill.yml:108 |
| `missing_fixtures_backfill.py` | 131 | 2026-02-12 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `parse.py` | 12 | 2026-04-02 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `per_fixture_backfill.py` | 1216 | 2026-09-25 | 5 | - | **VIVA** | importata da 5 file di produzione esterni (es. daily_yesterday_backfill.py) |
| `poisson_calibrator.py` | 215 | 2026-06-20 | 2 | - | **VIVA** | importata da 2 file di produzione esterni (es. Prediction/today_predictions_backfill.py) |
| `refresh_analytics_bets.py` | 281 | 2026-09-24 | 0 | .github/workflows/predictions_results_backfill.yml:148 | **VIVA** | lanciatore .github/workflows/predictions_results_backfill.yml:148 |
| `refresh_dashboard.py` | 20 | 2026-03-14 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `report_mm.py` | 202 | 2026-04-02 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `reset_ai_models.py` | 114 | 2026-03-13 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `retrain_all_leagues.py` | 631 | 2026-06-13 | 1 | aggiorna_modelli.bat:28 | **VIVA** | importata da 1 file di produzione esterni (es. cloud_retrain_shard.py); lanciatore aggiorna_modelli.bat:28 |
| `sanity_check.py` | 211 | 2026-03-04 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `season_aggregates.py` | 282 | 2026-09-28 | 3 | - | **VIVA** | importata da 3 file di produzione esterni (es. league_orchestrator.py) |
| `season_backfill.py` | 240 | 2026-09-25 | 2 | - | **VIVA** | importata da 2 file di produzione esterni (es. league_orchestrator.py) |
| `season_gaps.py` | 679 | 2026-09-28 | 6 | - | **VIVA** | importata da 6 file di produzione esterni (es. daily_yesterday_backfill.py) |
| `seasons_catchup.py` | 1022 | 2026-10-04 | 1 | .github/workflows/seasons_catchup.yml:88 | **VIVA** | importata da 1 file di produzione esterni (es. league_orchestrator.py); lanciatore .github/workflows/seasons_catchup.yml:88 |
| `simulate_recovery_forward.py` | 287 | 2026-06-10 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `standings_backfill.py` | 381 | 2026-09-25 | 1 | - | **VIVA** | importata da 1 file di produzione esterni (es. season_aggregates.py) |
| `start_backtest_worker.bat` | - | 2026-06-28 | - | - | **ARCHIVIO** | script di lancio manuale (nessun lanciatore automatico lo richiama) |
| `start_order_server.py` | 56 | 2026-06-29 | 0 | aggiorna_quote_betfair.bat:9 | **VIVA** | lanciatore aggiorna_quote_betfair.bat:9 |
| `stream_api.bat` | - | 2026-07-10 | - | - | **ARCHIVIO** | script di lancio manuale (nessun lanciatore automatico lo richiama) |
| `test.py` | 37 | 2026-03-30 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `test_actions_fail_rumoroso_2026_09_25.py` | 251 | 2026-09-25 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_actions_pipeline_paginazione.py` | 1723 | 2026-09-24 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_analytics_market_stats.py` | 233 | 2026-06-22 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_analytics_settlement.py` | 128 | 2026-06-22 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_backfill_automatico_2026_09_25.py` | 1270 | 2026-09-25 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_build_analytics_signals_kickoff_2026_09_26.py` | 78 | 2026-09-26 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_calibrazione_lettura_db.py` | 906 | 2026-09-21 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_catchup_57014_2026_09_28.py` | 612 | 2026-09-28 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_catchup_attesa_concorrenti_2026_09_26.py` | 123 | 2026-09-26 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_catchup_avviso_buchi_2026_10_04.py` | 192 | 2026-10-04 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_catchup_p4_2026_09_25.py` | 514 | 2026-09-25 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_cloud_retrain_shard_ritentativi_2026_09_21.py` | 385 | 2026-09-21 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_daily_niente_aggregati_2026_09_25.py` | 102 | 2026-09-25 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_delete_ritentativi_2026_09_25.py` | 386 | 2026-09-25 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_leagues_mapper_ritentativi_2026_10_04.py` | 201 | 2026-10-04 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_merge_engine_signals_kickoff_2026_09_26.py` | 97 | 2026-09-26 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_omega_transizioni_notturne_2026_09_25.py` | 507 | 2026-09-25 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_orchestratore_niente_refresh_mv_2026_09_25.py` | 101 | 2026-09-25 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_refresh_analytics_bets_v2_2026_09_24.py` | 247 | 2026-09-24 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `test_riserva_dinamica_2026_09_25.py` | 263 | 2026-09-25 | 0 | - | **TEST** | test pytest di radice (non e' codice di produzione) |
| `tmp_analysis.py` | 188 | 2026-04-02 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `tmp_analysis2.py` | 139 | 2026-04-02 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `tmp_predict_today.py` | 117 | 2026-06-10 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `tmp_smoke_ml_fixes.py` | 196 | 2026-06-10 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `tmp_smoke_poisson_fixes.py` | 148 | 2026-06-11 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `tmp_smoke_stack.py` | 138 | 2026-06-10 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `tmp_today_predictions.py` | 141 | 2026-06-10 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `tmp_train_today.py` | 73 | 2026-06-10 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `tmp_validate_league.py` | 66 | 2026-06-10 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `tmp_validate_predict.py` | 76 | 2026-06-10 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `top_assists_backfill.py` | 380 | 2026-09-25 | 1 | - | **VIVA** | importata da 1 file di produzione esterni (es. season_aggregates.py) |
| `top_cards_backfill.py` | 404 | 2026-09-25 | 1 | - | **VIVA** | importata da 1 file di produzione esterni (es. season_aggregates.py) |
| `top_scorers_backfill.py` | 380 | 2026-09-25 | 1 | - | **VIVA** | importata da 1 file di produzione esterni (es. season_aggregates.py) |
| `training_planner.py` | 293 | 2026-06-19 | 2 | - | **VIVA** | importata da 2 file di produzione esterni (es. cloud_retrain_shard.py) |
| `update_dashboard_only.py` | 31 | 2026-03-13 | 0 | - | **MORTA** | nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__ |
| `update_poisson_calibration.py` | 606 | 2026-09-21 | 0 | .github/workflows/weekly_poisson_calibration.yml:43 | **VIVA** | lanciatore .github/workflows/weekly_poisson_calibration.yml:43 |
| `valida_motore_poisson.py` | 169 | 2026-06-20 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `valida_ventaglio.py` | 179 | 2026-06-20 | 0 | - | **ARCHIVIO** | nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (0 file, 0 importazioni da test); ha __main__ lanciabile a mano |
| `validate_walkforward.py` | 138 | 2026-06-15 | 0 | .github/workflows/validate_models.yml:91 | **VIVA** | lanciatore .github/workflows/validate_models.yml:91 |
| `ventaglio_segnali.py` | 350 | 2026-06-20 | 1 | - | **VIVA** | importata da 1 file di produzione esterni (es. valida_ventaglio.py) |

Letture:

1. **I 54 VIVI di radice sono quasi tutti pipeline del DB cloud**, lanciate dai workflow (`seasons_catchup.py` `seasons_catchup.yml:88`, `daily_yesterday_backfill.py`, `generate_dynamic_cal.py`, ...) o importate da esse
   (`season_aggregates.py`, `standings_backfill.py`, `per_fixture_backfill.py`, `api_client.py` 14 importatori, `db_client.py` 107, `config.py` 17). Nel percorso Betfair vivono solo `db_client.py`, `config.py`, `logger.py`, `api_client.py`
   (punteggi, `Betfair/stream/scores/api_football.py`) e `betfair_tennis_odds.py` (`desktop/main.js:480`).
2. **Relitti del primo software («report manager», fogli Google)**: `betfair_report_manager.py` e `money_management.py` (3.397 righe; `Betfair/`, non radice) sono richiamati da `aggiorna_report.bat:21`, `aggiorna_mm_sheets.py`, `aggiorna_solo_fogli.py` (gspread: 9 file di produzione importano `gspread`, `s02_riepilogo.txt`)
   e dalla UI come istruzione manuale (`frontend/src/components/dashboard/MatchesList.tsx:278`). Non sono avviati dall'app.
3. **18 MORTE (2.717 righe)** e le **41 ARCHIVIO con solo `__main__`**: elenco e prova in 2.5. Le 18 MORTE hanno ultimo commit tra il 13/03 e il 24/06/2026 (`k03_riepilogo.txt`).
4. `start_order_server.py` (56 righe) e' VIVO solo per `aggiorna_quote_betfair.bat:9` (strada «ordini a mano vecchi», 5.1).


## 8. Cosa e' cambiato rispetto a `SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md` (02/10/2026)

Script: `c01_confronto_02_10.py` (`uscite/c01_confronto_0210.txt`, `c01_citazioni_0210.tsv`). Metodo: ognuna delle 277 citazioni `file:riga` dell'inventario del 02/10
viene riletta a `22d19cc` (la base dichiarata dall'inventario, `git show`) e il TESTO di quella riga viene cercato nel file di oggi: stessa riga / spostata (con la nuova riga) / testo cambiato o sparito.
Dal 02/10 sono passati 221 commit (6 il 02/10, 71 il 04/10, 23 il 05/10, 46 il 06/10, 65 il 07/10, 10 l'08/10: `git log --format=%cs 22d19cc..HEAD`).

```
citazioni file:riga distinte nell'inventario del 02/10: 277 in 69 file
  stessa_riga                    149  (53.8%)
  spostata                       124  (44.8%)
  TESTO_CAMBIATO_O_SPARITO         3  (1.1%)
  riga_vuota_a_base                1  (0.4%)

file con piu' citazioni NON piu' al loro posto (spostate o cambiate):
  desktop/main.js                                                tot= 24 stessa=  0 spostata= 22 cambiata/sparita=  2
  Betfair/mike/service.py                                        tot= 17 stessa=  2 spostata= 15 cambiata/sparita=  0
  Betfair/omega/omega_service.py                                 tot= 15 stessa=  0 spostata= 15 cambiata/sparita=  0
  Betfair/stream/runner.py                                       tot= 11 stessa=  2 spostata=  9 cambiata/sparita=  0
  Betfair/safe_strategy/bot_service.py                           tot= 12 stessa=  4 spostata=  8 cambiata/sparita=  0
  Betfair/safe_strategy/execution.py                             tot=  6 stessa=  0 spostata=  6 cambiata/sparita=  0
  Betfair/stream/tennis_live/tennis_runner.py                    tot=  6 stessa=  0 spostata=  6 cambiata/sparita=  0
  Betfair/omega/omega_market.py                                  tot=  7 stessa=  2 spostata=  5 cambiata/sparita=  0
  Betfair/stream/backtest/banco_comune.py                        tot=  6 stessa=  1 spostata=  5 cambiata/sparita=  0
  Betfair/stream/live_order_worker.py                            tot= 10 stessa=  6 spostata=  4 cambiata/sparita=  0
  Betfair/stream/trading/minimi_it.py                            tot=  4 stessa=  0 spostata=  4 cambiata/sparita=  0
  Betfair/order_exec.py                                          tot=  3 stessa=  0 spostata=  3 cambiata/sparita=  0
  Betfair/stream/live_order_build.py                             tot=  3 stessa=  0 spostata=  3 cambiata/sparita=  0
  Betfair/stream/scalper/scalper_service.py                      tot=  7 stessa=  4 spostata=  3 cambiata/sparita=  0
  Betfair/stream/scalper/scalper_session.py                      tot=  3 stessa=  0 spostata=  3 cambiata/sparita=  0
  Betfair/stream/backtest/registro_bot.py                        tot=  2 stessa=  0 spostata=  2 cambiata/sparita=  0
  Betfair/stream/scalper/scalper_bot.py                          tot=  2 stessa=  0 spostata=  1 cambiata/sparita=  1
  Betfair/stream/motore_ordini.py                                tot=  4 stessa=  3 spostata=  1 cambiata/sparita=  0
  Betfair/stream/tennis_live/tennis_bot_service.py               tot=  6 stessa=  5 spostata=  1 cambiata/sparita=  0
  Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py tot=  2 stessa=  1 spostata=  1 cambiata/sparita=  0

git diff --numstat 22d19cc..HEAD: file toccati 873
cartella                                        file   +righe   -righe
SCHEMI_BOT                                        45   199149        0
frontend/src                                     174    46180      381
AUDIT_2026-10-07                                 176    40024        0
AUDIT_2026-10-04                                 130    31680        0
Betfair/stream                                   123    24139      601
dynamic_cal.json                                   1     9084     8476
AUDIT_2026-10-08                                  33    10833        0
AUDIT_2026-10-05                                  52     7783        0
AUDIT_2026-10-06                                  37     4296        0
Betfair/safe_strategy                             17     2792      103
Betfair/omega                                     22     2346      155
Betfair/mike                                      19     1558       70
migrations                                         6      646        0
tools                                              2      572        0
ARCHITETTURA_2026-10                               4      544        0
AUDIT_2026-10-02                                   1      342        0
CRONOSTORIA.md                                     1      306        0
desktop                                            4      178       33
test_leagues_mapper_ritentativi_2026_10_04.py      1      201        0
test_catchup_avviso_buchi_2026_10_04.py            1      192        0
frontend/scripts                                   1      159        0
dc_rho_by_league.json                              1       62       55
PIANO_OTTIMIZZAZIONE_GLOBALE_2026-10-02.md         1      100        0
leagues_mapper.py                                  1       76       15
registrazioni_banco                                3       56        0
seasons_catchup.py                                 1       44        2
Betfair/money_management.py                        1       18       18
.github                                            3       13        9
Betfair/order_exec.py                              1       18        0
AUDIT_2026-09-25                                   1        1        1

name-status 22d19cc..HEAD: A=663, M=210
file Python di produzione AGGIUNTI dopo il 02/10 (8):
  Betfair/stream/backtest/applica_bot.py
  Betfair/stream/backtest/varianti_bot.py
  Betfair/stream/scalper/media_under_bot.py
  Betfair/stream/tennis_live/mercati_registrati.py
  Betfair/stream/tennis_replay/__init__.py
  Betfair/stream/tennis_replay/caricamento.py
  Betfair/stream/tennis_replay/convertitore.py
  Betfair/stream/tennis_replay/importa.py
file Python TOLTI dopo il 02/10 (non audit): 0

commit dopo 22d19cc: 221; data base: 2026-10-02

righe oggi dei file piu' grandi (inventario 02/10 I-1: valori al 02/10 tra parentesi dove noti)
  Betfair/safe_strategy/bot_service.py           02/10 (dichiarato)  10862 | a 22d19cc  10862 | oggi  11136
  Betfair/omega/omega_service.py                 02/10 (dichiarato)   8709 | a 22d19cc   8709 | oggi   8936
  Betfair/mike/service.py                        02/10 (dichiarato)   7496 | a 22d19cc   7496 | oggi   7551
  Betfair/mike/engine.py                         02/10 (dichiarato)   5097 | a 22d19cc   5097 | oggi   5359
  Betfair/stream/live_order_worker.py            02/10 (dichiarato)   3991 | a 22d19cc   3991 | oggi   3997
  Betfair/safe_strategy/service.py               02/10 (dichiarato)   3444 | a 22d19cc   3444 | oggi   3444
```

### 8.1 Che cosa significa

- **Le citazioni dell'inventario del 02/10 sono ancora valide come FATTI nel 98,5% dei casi** (149 alla stessa riga + 124 spostate = 273 su 277), ma il 44,8% non e' piu' al numero di riga indicato:
  `desktop/main.js` ha 22 citazioni su 24 spostate (i lanci dei servizi, citati dall'inventario a `:435-491` (A-2...A-10), oggi stanno a `:419-483`: e' stato **aggiunto il `backtest-worker`** e riscritto l'arresto ordinato), `omega_service.py` 15 su 15, `mike/service.py` 15 su 17.
  Le 3 citazioni il cui testo e' cambiato o sparito sono elencate in `c01_citazioni_0210.tsv` (esito `TESTO_CAMBIATO_O_SPARITO`: 2 in `desktop/main.js`, 1 in `Betfair/stream/scalper/scalper_bot.py`).
  Chi usa `INVENTARIO_ARCHITETTURA.md` deve ritrovare le righe con il TESTO, non col numero.
- **Quello che e' davvero nuovo dal 02/10** (da `git diff --name-status 22d19cc..HEAD`: 663 file aggiunti, 210 modificati, 0 cancellati; per cartella nella tabella sopra):
  1. **8 file Python di produzione nuovi** (nessuno tolto): `Betfair/stream/backtest/applica_bot.py` e `varianti_bot.py` («Applica bot» e varianti sul banco), `Betfair/stream/scalper/media_under_bot.py` (modalita'
     media under, 2.637 righe), `Betfair/stream/tennis_live/mercati_registrati.py`, `Betfair/stream/tennis_replay/{__init__,caricamento,convertitore,importa}.py` (Replay Tennis, 811 righe).
  2. **Un processo in piu' sotto watchdog**: `backtest-worker` (`desktop/main.js:469`, commit del 06/10 «il banco del replay parte con l'app»). L'inventario del 02/10 elencava 8 programmi sotto guardiano (A-2...A-9): oggi sono 9.
  3. **Frontend**: +46.180 righe aggiunte in `frontend/src` (174 file toccati), fra cui il «guscio v2» (`components/shell/`, `lib/uiShell.ts`), il replay professionale, `lib/replayBot.ts`, il catalogo generato `replayBotCatalogo.ts` (11.099 righe),
     `pages/TennisReplay.tsx`, il registro delle operazioni. Il numero di rotte e' 26.
  4. **Banco**: 11 bot registrati come il 02/10 (`registro_bot.py:217-401`: mike, omega, safe_base, safe_esatto, safe_punta, safe_tennis, scalper_calcio, tennis_scalper, tennis_pro, tennis_flb, tennis_swing).
  5. **Righe**: `bot_service.py` 10.862 -> 11.136, `omega_service.py` 8.709 -> 8.936, `mike/service.py` 7.496 -> 7.551, `mike/engine.py` 5.097 -> 5.359, `live_order_worker.py` 3.991 -> 3.997, `safe_strategy/service.py` 3.444 invariato
     (valori «a `22d19cc`» e «oggi» identici ai dichiarati: l'inventario del 02/10 conta giusto).
  6. **Migrazioni**: 6 file, +646 righe di SQL (`migrations/`); **documenti** e audit: `SCHEMI_BOT` +199.149 righe (gli schemi), `AUDIT_2026-10-04..08` +94.000 circa.
- **Che cosa NON e' cambiato** (verificato oggi sul codice): le 8 porte di lock e i 8 canali (A-19, C-4...C-11: sezione 5 di questo documento le conferma tutte, con le stesse porte); il watchdog (backoff 10-300 s, 5/h, codice 75, battito 30 s: `watchdog.py:73-105,248-252`);
  il client Supabase per thread (`db_client.py:75`); il doppio client Betfair (`betfairlightweight` + `requests`); il numero dei file DB «per bot».
- **Punti che l'inventario del 02/10 lasciava aperti** (sezione «Punti non chiariti», 6 punti) e che questo inventario NON chiude: 1 (chiamate Betfair non contate), 2 (Mike con login Betfair: `omega_market.py:508` e `certlogin` nei registri, `MISURE:212-213`, confermato dal codice),
  3-4 (Omega fermo, nessun tennis/scalper nella misura), 5-6 (sessione a domanda e canale all'avvio). Nessuna nuova misura di frequenza e' stata fatta qui (regola del compito).


## 9. Come rieseguire (ogni numero di questo documento)

Tutti gli script stanno in `ARCHITETTURA_2026-10/strumenti/inventario/`, usano solo la libreria standard e `git` in sola lettura, NON importano codice di produzione, NON caricano `.env`,
scrivono SOLO in `strumenti/inventario/uscite/` (nessun file > 1 MB: il piu' grande, `s01_righe_per_file.tsv`, ~350 KB). Interprete: `.venv/Scripts/python.exe` (Python di progetto), dalla radice del repo
o da qualunque cartella (`_comune.py` risale da solo alla radice). Ordine (le dipendenze vanno da sinistra a destra); durate misurate su questo PC l'08/10/2026:

| Ordine | Script | Produce | Sezione | Durata |
|---:|---|---|---|---|
| 1 | `s01_righe.py` | `s01_righe_per_file.tsv`, `s01_riepilogo.txt` | 1, 0 | ~11 s |
| 2 | `s02_import.py` | `s02_moduli.tsv`, `s02_archi.tsv`, `s02_esterni.tsv`, `s02_morti.txt`, `s02_riepilogo.txt` | 2 | ~25 s |
| 3 | `s03_db.py` | `s03_*.tsv`, `s03_riepilogo.txt` | 3 | ~35 s |
| 4 | `s04_duplicati.py` | `s04_*` | 4 | ~40 s |
| 5 | `s05_tabelle_stringa.py` | `s05_tabelle_stringa.tsv` | 3 | ~10 s |
| 6 | `s06_top30_duplicati.py` | `s06_top_duplicati.{txt,tsv}` | 4 | <1 s |
| 7 | `s07_cartelle_import.py` | `s07_cartelle.txt`, `s07_archi_cartelle.tsv` | 2 | <1 s |
| 8 | `s08_morti_verifica.py` | `s08_morti_verifica.{txt,tsv}` | 2 | ~5 s |
| 9 | `s09_gemelli_file.py` | `s09_gemelli_file.{txt,tsv}` | 4 | <1 s |
| 10 | `k01_radice.py` | `k01_radice.tsv` | 7 | ~3 min (scorre il disco) |
| 11 | `k02_grafo_import.py` | `k02_moduli.tsv`, `k02_import_dinamici.txt` | 2 | ~40 s |
| 12 | `k03_classifica_radice.py` | `k03_*` | 7 | ~4 s |
| 13 | `p01_porte.py` | `p01_porte.tsv`, `p01_porte_riepilogo.txt` | 5 | ~5 s |
| 14 | `f01_frontend.py` | `f01_*` | 6 | ~2 s |
| 15 | `c01_confronto_02_10.py` | `c01_*` | 8 | ~11 s |
| 16 | `g01_tabelle_md.py` | `g01_tabelle_db.md`, `g01_rpc.md` | 3 | <1 s |
| 17 | `z_assembla.py` | `ARCHITETTURA_2026-10/00_INVENTARIO.md` (da `parti/*.md` + le uscite) | tutte | <1 s |

Comando tipo: `.venv/Scripts/python.exe ARCHITETTURA_2026-10/strumenti/inventario/s01_righe.py`. `z_assembla.py` e' l'unico che scrive fuori da `uscite/` (scrive il documento);
i segnaposto `sez` e `file` (doppia graffa, vedi la docstring di `z_assembla.py`) dentro `parti/` sono sostituiti con le uscite, il testo a mano resta quello delle parti (i numeri scritti a mano nel testo NON si aggiornano da soli: vanno riletti se il repo cambia).
Il numero di file e di righe dipende da `HEAD`: questo documento e' fotografato a `dfae4541`; con file non committati o con un altro `HEAD` i numeri cambiano (`s01` stampa `HEAD` e lo stato di `git status` in testa).

Script del primo giro riusati/corretti: `s01` (aggiunte categorie, binari per estensione, generati, sezioni A2-A4 e F, ricostruzione del brief), `s02` (alias `ai_engine`, chiave canonica degli importatori), `k02` (BOM),
`k01`, `s03`, `s04` invariati. Script mancanti aggiunti: `s05`-`s09`, `k03`, `p01`, `f01`, `c01`, `g01`, `z_assembla`. Altre misure nella cartella `strumenti/` (non mie): `misure/m*.py` (feed, DB, risorse), `dati_g1/`, `dati_J/`, `h_*`, `e*_gemelli*`.


## 10. Cosa ho verificato di persona / cosa non ho potuto verificare

### 10.1 Verificato

1. **Righe**: confronto indipendente con `wc -l` su 6 voci (sezione 0): tutte identiche a `s01`. HEAD e stato dell'albero (due file modificati da un'altra sessione) dichiarati in testa.
2. **Falsificazione degli script del primo giro** (difetti trovati e corretti, con effetto sui numeri): `s01` contava un PDF e i `.pkl` come testo (168.866 «righe» false nel blocco «altro»); `s02` non risolveva
   `ai_engine.*` (5 moduli di `Ai Engine/` erano falsi «morti», gruppo A 31 -> 26); `k02` aveva 16 falsi `SyntaxError` (BOM); `k03` (nuovo) all'inizio dava `parse.py` «avviato da `main.js`» per la parola `parse` e `test.py` «lanciato dal workflow» per
   `test_seasons`: corretto richiedendo il nome file con estensione; `s08` segnala ancora falsi positivi per stem generici (`pipeline`, `backfill`, ...), dichiarati in 2.5; `s03` dichiarava «33 tabelle mai usate» ma 12 sono toccate per stringa (`s05`).
3. **Controprove incrociate**: `s02` (AST) contro `s08` (stringa) per i morti; `f01` contro `strumenti/dati_J/accessi.tsv` (160 vs 159+2 RPC); `s03` contro `s05` per le tabelle «mai usate»;
   le citazioni dell'inventario del 02/10 contro il codice di oggi (`c01`); i numeri del brief contro `s01` e contro la ricostruzione (la somma delle sue componenti).
4. **Citazioni controllate a mano contro il codice** (letto il file alla riga): `desktop/main.js:413-484` (tutti i `spawnRunner`), `:46`, `:61`, `:292`, `:527-575`, `:759`, `:899`; `desktop/preload.js:21`; `watchdog.py:73-105,248-252,307,318`;
   `single_instance.py:18-35`; `local_channel.py:14-18,65,68,404`; `db_client.py:75`; `Betfair/mike/service.py:6794-6845`; `canale_bot.py:60-166`; `scalper_service.py:702-713`; `tennis_bot_service.py:1104,1136-1160`; `backtest/worker.py:23`;
   `frontend/src/lib/localChannel.ts:50-67,302-345`; `frontend/src/lib/uiShell.ts`; `App.tsx` (due alberi); `MISURE_2026-10-02.md` per ogni numero e riga citati (letto per intero, 253 righe).
5. **Nessuna esecuzione di codice di produzione**, nessun accesso al DB, nessuna chiamata a Betfair; i soli processi lanciati sono i miei script e `git` (un `du` su directory enormi e' stato avviato e subito interrotto dopo il timeout, senza risultati).

### 10.2 NON verificato (e perche')

1. **Cosa gira davvero sul PC** (processi vivi, RAM, CPU, quante finestre/renderer di Electron): non ho interrogato il sistema operativo; la sezione 5 descrive cio' che il codice avvia.
2. **Stato degli interruttori `*_CANALE`** e di ogni variabile `.env` (non letto): il verso di default e' nel codice, il valore reale no (sezione 5.4).
3. **Cosa c'e' sul DB cloud**: se le 21 tabelle senza riferimenti sono ancora popolate da `pg_cron`/funzioni, se le Edge Functions di `Telegram bot/` sono deployate, lo schema delle 17 tabelle non definite nei `.sql`, i vincoli e gli indici. Servirebbero letture `SELECT` su `pg_stat_user_tables`/`cron.job`, fuori dal perimetro di questo compito.
4. **Frequenze nuove**: nessuna misura nuova (regola del compito). Tutte le frequenze citate sono quelle del 02/10, con condizioni dichiarate (Omega fermo, niente tennis/scalper); non descrivono il carico di oggi ne' di una giornata piena.
5. **Chiamate a Betfair**: non contate una per una (nessun contatore nei registri, come gia' il 02/10); le cadenze Betfair dell'inventario del 02/10 (B-4...B-16) non sono state rimisurate.
6. **Raggiungibilita' vera dei moduli**: i gruppi A-D e la classifica di radice usano i collegamenti nel repo, non la raggiungibilita' dai punti d'ingresso; un modulo importato solo da un modulo morto risulta vivo. Gli import dinamici sono registrati (502) ma non risolti uno per uno.
7. **Frontend**: la chiusura degli import e' un limite superiore (una pagina che importa un hub eredita tutte le sue RPC); le RPC realmente chiamate da ogni pagina vanno derivate da `f01_pagine.txt`/`f01_accessi_file.tsv` pagina per pagina; i pannelli (6.4) sono elencati per dimensione, non descritti; le funzionalita' complete sono materia di `01_FUNZIONALITA.md`. `getLocalChannel(sport)` con argomento variabile risulta «variabile».
8. **Matrice DB**: operazione (lettura/scrittura) dedotta dal metodo concatenato; i `.table(x)` con nome non letterale (6 nomi) sono in «op?»; le chiamate DB fatte con SQL grezzo dentro RPC non si vedono; le RPC chiamate solo da trigger/cron non compaiono.
9. **Natura di `_checkpoint_2026-09-28/`** (58.058 file non tracciati) e delle altre cartelle locali non tracciate (7.1 punto 10): elencate, non indagate.
10. **Albero di lavoro non committato** di un'altra sessione (`db_client.py`, `season_gaps.py`): i numeri di quei file e dei loro derivati possono cambiare al commit.
