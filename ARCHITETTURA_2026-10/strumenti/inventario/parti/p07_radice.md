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

{{file:k03_cartelle.md}}

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

{{file:k03_file_radice.md}}

Letture:

1. **I 54 VIVI di radice sono quasi tutti pipeline del DB cloud**, lanciate dai workflow (`seasons_catchup.py` `seasons_catchup.yml:88`, `daily_yesterday_backfill.py`, `generate_dynamic_cal.py`, ...) o importate da esse
   (`season_aggregates.py`, `standings_backfill.py`, `per_fixture_backfill.py`, `api_client.py` 14 importatori, `db_client.py` 107, `config.py` 17). Nel percorso Betfair vivono solo `db_client.py`, `config.py`, `logger.py`, `api_client.py`
   (punteggi, `Betfair/stream/scores/api_football.py`) e `betfair_tennis_odds.py` (`desktop/main.js:480`).
2. **Relitti del primo software («report manager», fogli Google)**: `betfair_report_manager.py` e `money_management.py` (3.397 righe; `Betfair/`, non radice) sono richiamati da `aggiorna_report.bat:21`, `aggiorna_mm_sheets.py`, `aggiorna_solo_fogli.py` (gspread: 9 file di produzione importano `gspread`, `s02_riepilogo.txt`)
   e dalla UI come istruzione manuale (`frontend/src/components/dashboard/MatchesList.tsx:278`). Non sono avviati dall'app.
3. **18 MORTE (2.717 righe)** e le **41 ARCHIVIO con solo `__main__`**: elenco e prova in 2.5. Le 18 MORTE hanno ultimo commit tra il 13/03 e il 24/06/2026 (`k03_riepilogo.txt`).
4. `start_order_server.py` (56 righe) e' VIVO solo per `aggiorna_quote_betfair.bat:9` (strada «ordini a mano vecchi», 5.1).

