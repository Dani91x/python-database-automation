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
