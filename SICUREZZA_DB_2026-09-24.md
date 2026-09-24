# SICUREZZA DEL DB - inventario, strategia, ordine di applicazione (24/09/2026)

Ordine dell'utente: "Metti in sicurezza il DB: ci lavoro solo io e solo io devo accedere (io = tutta
l'app e il sistema che abbiamo costruito), nessun altro. Massima attenzione: il progetto deve
continuare a funzionare in ogni sua parte." Piu' il punto 14: "omega_activity deve avere il realtime".

Lavoro in SOLA LETTURA sul codice (delegato Opus). Nessuna query sul DB vero: la fotografia dei grant e'
quella del coordinatore del 23/09 (`GRANT_SNAPSHOT_DB_2026-09-23.md`) piu' il referto
`IMPATTO_SUPABASE_GRANT_2026-10-30.md`. Le migrazioni le applica l'utente dal SQL Editor.

File consegnati:
- `migrations/sicurezza_db_2026-09-24_BLOCCO_1_zero_rischio.sql`
- `migrations/sicurezza_db_2026-09-24_BLOCCO_2_rls_e_policy.sql`
- `migrations/sicurezza_db_2026-09-24_BLOCCO_3_revoke_anon.sql`
- questo documento.

---

## 0. La risposta secca

**Il frontend usa anon senza login? NO.** L'app (web e desktop, stesso bundle) fa il login con
`supabase.auth.signInWithPassword` (`frontend/src/components/landing/AuthSection.tsx:106`), tiene la
sessione con `onAuthStateChange`/`getSession` (`frontend/src/hooks/useAuth.ts:12,21`) e TUTTE le pagine
con dati sono dietro `ProtectedRoute`, che esige sessione valida E email dell'owner
(`frontend/src/components/ProtectedRoute.tsx:22`, `frontend/src/lib/auth-config.ts:6`). Da loggato il
JWT e' `authenticated`. La chiave anon serve SOLO prima del login: al login stesso (GoTrue, `/auth/v1`,
che non passa dai grant di `public`) e al form lead della landing (`leads.insert`,
`AuthSection.tsx:73`, "best-effort": se fallisce la pagina mostra comunque il banner). Le registrazioni
sono chiuse due volte: impostazione Auth + trigger `trg_block_non_owner_signup` su `auth.users`
(`migrations/security_lockdown.sql:38-55`). Quindi: **chiudere anon NON spegne il frontend**, nessun
login nuovo da implementare.

**Chi usa cosa, in una riga:** frontend = `authenticated` (owner); bot Python, runner, servizi, script,
GitHub Actions, edge function `make-daily-post` = `service_role`; edge function `telegram-bot` = `anon`
(e per questo oggi NON vede `fixture_predictions`: e' gia' cieco dal 22/06, non per colpa di questi blocchi).

**I tre reperti di sicurezza veri** (oltre a quelli gia' noti del 23/09):
1. **13+ tabelle storiche senza RLS con anon a pieni poteri** (`match_odds`, `standings`, `injuries`,
   `match_events`, `match_lineups`, `match_player_stats`, `match_team_stats`, `top_scorers`,
   `top_assists`, `top_cards`, `api_call_log`, `season_backfill_state`, `signal_history`, ...): chiunque
   abbia la chiave anon (e' nel bundle pubblico) puo' leggere, modificare e cancellare lo storico che
   alimenta modelli e backtest. Chiuso dal BLOCCO 1.
2. **11 RPC SECURITY DEFINER senza controllo owner e revocate solo a `PUBLIC`**: su Supabase i default
   danno ad anon un grant ESPLICITO sulle funzioni, che `REVOKE ... FROM public` non toglie. Quindi con
   ogni probabilita' anon le esegue. Due SCRIVONO (`upsert_cash_movement`, `upsert_imported_trade`: dati
   personali), le altre leggono (`get_betfair_fixtures`, `get_betfair_odds`, `get_betfair_full_odds`,
   `get_betfair_direction_odds`, `get_direction`, `get_omega_proposte`, `get_cash_movements`,
   `set_trade_time_operative`, `leagues_needing_retrain`). Fonti: `sql/betfair_fixtures_rpc.sql:75-78`,
   `migrations/betfair_full_odds_rpc.sql:68-71`, `migrations/get_direction_rpc.sql:249-250`,
   `migrations/omega_proposte_coda_unica_2026-09-17.sql:285-290`, `migrations/personal_cash_movements.sql:92-95`,
   `migrations/personal_tracking_import.sql:150-181`, `sql/leagues_needing_retrain_rpc.sql:70-71`.
   Chiuse dal BLOCCO 1 (da confermare sul DB con la query P3 della sezione 4). Anche
   `omega_request_approve/ignore` e `safe_request_approve/ignore` sono revocate solo a PUBLIC, ma
   controllano l'owner nel corpo: le chiude il BLOCCO 3.
3. **Viste `v_*` senza `security_invoker`**: girano come proprietario e scavalcano la RLS di
   `engine_signals` (aggregati leggibili da anon). Chiuse dal BLOCCO 1.

---

## 1. Inventario dei client e delle chiavi

| Client | Chiave / ruolo | Prova (file:riga) | Cosa tocca |
|---|---|---|---|
| Frontend web (Vercel) prima del login | `VITE_SUPABASE_ANON_KEY` -> `anon` | `frontend/src/integrations/supabase/client.ts:4,10` | login (GoTrue), `leads.insert` (`components/landing/AuthSection.tsx:73`) |
| Frontend dopo il login | stessa chiave + JWT sessione -> `authenticated` (solo owner) | `AuthSection.tsx:106`, `hooks/useAuth.ts:12,21`, `components/ProtectedRoute.tsx:22`, `lib/auth-config.ts:6` | 24 `.from()` tutti in SELECT su 17 tabelle (sezione 2), 37 sottoscrizioni realtime su 35 tabelle, 132 RPC (tutte SECURITY DEFINER) |
| App desktop (Electron) | nessun client proprio: serve lo stesso bundle su 127.0.0.1:47330 -> come il frontend | `desktop/main.js` (nessun `createClient`/`supabase` in `desktop/*.js`) | come il frontend |
| Processi Python lanciati dall'app (runner calcio/tennis, omega, safe, mike, scalper, tennis bot) | `SUPABASE_SERVICE_ROLE_KEY` -> `service_role` | `db_client.py:5,21`; `Betfair/stream/tennis_live/tennis_db.py:24,54`; `config.py:10` | scrivono e leggono tutto il gruppo B e C, parte del gruppo A |
| Script Python sparsi | `SUPABASE_SERVICE_ROLE_KEY` | `api_client.py:5`, `ventaglio_segnali.py:35`, `valida_motore_poisson.py:25`, `cloud_retrain_shard.py:72`, `admin_reset_password.py:28`, `Betfair/tools/*.py`, `Betfair/safe_strategy/tools/conta_operazioni_live.py:35` e `storia_operazioni.py:31` (fallback su `SUPABASE_KEY`: da non valorizzare con la anon) | gruppo A e analytics |
| GitHub Actions (8 workflow) | `secrets.SUPABASE_SERVICE_ROLE_KEY` (nessuna usa la anon) | `.github/workflows/{daily_yesterday_backfill,leagues_mapper,ml_calibration,predictions_results_backfill,retrain_models,today_predictions_backfill,validate_models,weekly_poisson_calibration}.yml` | gruppo A, `fixture_predictions`, calibrazioni |
| Edge function `make-daily-post` | `SUPABASE_SERVICE_ROLE_KEY` | `Telegram bot/supabase/functions/make-daily-post/index.ts:18-19` | legge `fixture_predictions` (:29), storage bucket `Loghi` (:253,263) |
| Edge function `telegram-bot` | `SUPABASE_ANON_KEY ?? MY_DB_KEY` -> `anon` | `Telegram bot/supabase/functions/telegram-bot/index.ts:35,328,440` | legge `fixture_predictions` (:232,271,356,473): **NEGATO dal 22/06** (`security_lockdown.sql:103`) |
| Banco di certificazione frontend (solo test) | service_role | `frontend/src/certification/realClient.ts:88` | sola lettura nei test |
| Migrazioni | `postgres` dal SQL Editor | `migrations/*.sql`, `sql/*.sql` | proprietario di tabelle e RPC |

Non ci sono `supabase/functions` alla radice ne' altre edge function; nessun codice crea tabelle a runtime.

---

## 2. Inventario degli oggetti di `public`

### 2.1 Chi legge e chi scrive ogni tabella/vista

Gruppi dallo snapshot del 23/09: **A** = grant storici (anon e authenticated FULL), **B** = tabelle
"app" (authenticated SELECT per la UI, anon niente, RLS on), **C** = solo service_role. "service_role
(ops)" = operazioni trovate nel codice Python vicino al nome della tabella (analisi statica, per file).
Le righe della UI sono `file:riga` sotto `frontend/src/`.

| Oggetto | Gruppo | Chi scrive (ruolo) | Bot/Python/Actions che la usano (service_role) | UI (authenticated) | anon oggi | Dopo B1-B3 |
|---|---|---|---|---|---|---|
| `ai_model_registry` | A storico | service_role (delete/insert) | 7 file: Ai Engine/ai_engine/predict_fixture.py, Ai Engine/ai_engine/seriea_model_export.py, Betfair/betfair_report_manager.py, ... | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `api_call_log` | A storico | service_role (insert) | 1 file: logger.py | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `api_coverage_by_season` | A storico | service_role (upsert) | 4 file: Prediction/today_predictions_backfill.py, league_orchestrator.py, leagues_mapper.py, ... | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `engine_signals` | A storico | service_role (upsert) | 4 file: _certify_betfair.py, _certify_direction_report.py, merge_engine_signals.py, ... | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `injuries` | A storico | service_role (delete/insert) | 4 file: daily_yesterday_backfill.py, injuries_backfill.py, league_orchestrator.py, ... | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `league_season_riepilogo_popolamento` | A storico | - (nessun client nel repo) | - | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `match_events` | A storico | service_role | 10 file: Ai Engine/ai_engine/db_adapter.py, Ai Engine/ai_engine/feature_pipeline.py, _AUDIT_2026_05/load_goals.py, ... | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `match_lineups` | A storico | service_role | 2 file: daily_yesterday_backfill.py, per_fixture_backfill.py | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `match_odds` | A storico | service_role (update) | 11 file: Ai Engine/ai_engine/backtest.py, Ai Engine/ai_engine/db_adapter.py, Ai Engine/ai_engine/feature_pipeline.py, ... | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `match_player_stats` | A storico | service_role (delete) | 4 file: Ai Engine/ai_engine/db_adapter.py, Ai Engine/ai_engine/feature_pipeline.py, daily_yesterday_backfill.py, ... | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `match_team_stats` | A storico | service_role (delete) | 12 file: Ai Engine/ai_engine/db_adapter.py, Ai Engine/ai_engine/feature_pipeline.py, Prediction/today_predictions_backfill.py, ... | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `matches` | A storico | service_role (upsert) | 38 file: Ai Engine/ai_engine/db_adapter.py, Betfair/betfair_report_manager.py, Betfair/money_management.py, ... | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `missing_fixture_coverage` | A storico | - (nessun client nel repo) | - | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `ml_post_calibration` | A storico | service_role (delete/upsert) | 2 file: Ai Engine/ai_engine/predict_fixture.py, compute_ml_post_calibration.py | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `model_performance` | A storico | service_role (upsert) | 2 file: _AUDIT_2026_05/probe_data.py, retrain_all_leagues.py | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `poisson_calibration` | A storico | service_role (upsert) | 3 file: generate_dynamic_cal.py, load_poisson_calibration_to_db.py, poisson_calibrator.py | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `season_backfill_state` | A storico | service_role (upsert) | 3 file: league_orchestrator.py, retrain_all_leagues.py, training_planner.py | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `signal_history` | A storico | service_role (upsert) | 2 file: Betfair/money_management.py, _AUDIT_2026_05/probe_data.py | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `standings` | A storico | service_role (delete/insert) | 8 file: Ai Engine/ai_engine/audit_nulls.py, Ai Engine/ai_engine/coverage.py, Ai Engine/ai_engine/db_adapter.py, ... | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `top_assists` | A storico | service_role (delete/insert) | 4 file: daily_yesterday_backfill.py, league_orchestrator.py, leagues_mapper.py, ... | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `top_cards` | A storico | service_role (delete/insert) | 4 file: daily_yesterday_backfill.py, league_orchestrator.py, leagues_mapper.py, ... | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `top_scorers` | A storico | service_role (delete/insert) | 4 file: daily_yesterday_backfill.py, league_orchestrator.py, leagues_mapper.py, ... | no (solo via RPC DEFINER) | FULL | anon nulla; RLS; auth al piu' SELECT owner |
| `fixture_predictions` | A storico | service_role (insert/update/upsert) | 38 file: AGGIORNA_CAMPO_db_json_analisi.py, Ai Engine/ai_engine/audit_nulls.py, Ai Engine/ai_engine/db_adapter.py, ...; make-daily-post (service_role); telegram-bot (anon: NEGATO) | .from components/dashboard/FixtureSelector.tsx:30, components/dashboard/MatchesList.tsx:143, lib/fixtureModels.ts:70 | tutto tranne SELECT | anon nulla; auth SELECT + policy owner |
| `leads` | A storico | anon INSERT (AuthSection.tsx:73) | - | .from components/landing/AuthSection.tsx:73 | INSERT | anon INSERT; auth SELECT+INSERT |
| `v_clv_summary` | vista | - (nessun client nel repo) | - | no (solo via RPC DEFINER) | FULL | anon nulla; security_invoker |
| `v_es_concordance_roi` | vista | - (nessun client nel repo) | - | no (solo via RPC DEFINER) | FULL | anon nulla; security_invoker |
| `v_es_emission_by_engine_market` | vista | - (nessun client nel repo) | - | no (solo via RPC DEFINER) | FULL | anon nulla; security_invoker |
| `v_es_reject_funnel` | vista | - (nessun client nel repo) | - | no (solo via RPC DEFINER) | FULL | anon nulla; security_invoker |
| `v_roi_by_market` | vista | - (nessun client nel repo) | - | no (solo via RPC DEFINER) | FULL | anon nulla; security_invoker |
| `v_roi_by_track` | vista | - (nessun client nel repo) | - | no (solo via RPC DEFINER) | FULL | anon nulla; security_invoker |
| `betfair_live_account` | B app | service_role (upsert) | 1 file: Betfair/stream/db.py | .from lib/liveOrders.ts:913; realtime lib/liveOrders.ts:942 | nessuno | anon nulla; auth SELECT + policy owner |
| `betfair_live_heartbeat` | B app | service_role (upsert) | 4 file: Betfair/mike/db.py, Betfair/omega/omega_db.py, Betfair/safe_strategy/bot_db.py, ... | .from lib/liveOrders.ts:966, lib/safeBot.ts:1999; realtime lib/liveOrders.ts:979 | nessuno | anon nulla; auth SELECT + policy owner |
| `betfair_live_orders` | B app | service_role (delete/upsert) | 6 file: Betfair/mike/db.py, Betfair/omega/omega_db.py, Betfair/safe_strategy/bot_db.py, ... | realtime lib/liveOrders.ts:541 | nessuno | anon nulla; auth SELECT + policy owner |
| `betfair_live_positions` | B app | service_role (delete/upsert) | 1 file: Betfair/stream/db.py | realtime lib/liveOrders.ts:557 | nessuno | anon nulla; auth SELECT + policy owner |
| `betfair_live_risk_state` | B app | service_role (upsert) | 1 file: Betfair/stream/db.py | .from lib/liveOrders.ts:773; realtime lib/liveOrders.ts:787 | nessuno | anon nulla; auth SELECT + policy owner |
| `live_alerts` | B app | service_role (insert) | 3 file: Betfair/stream/db.py, Betfair/stream/live_order_worker.py, Betfair/stream/scalper/scalper_session.py | realtime lib/live.ts:551 | nessuno | anon nulla; auth SELECT + policy owner |
| `live_backtest_requests` | B app | service_role (update) | 1 file: Betfair/stream/db.py | realtime lib/analytics.ts:512 | nessuno | anon nulla; auth SELECT + policy owner |
| `live_follow` | B app | service_role (update/upsert) | 7 file: Betfair/mike/db.py, Betfair/omega/omega_db.py, Betfair/safe_strategy/bot_db.py, ... | .from lib/safeBot.ts:2011; realtime lib/live.ts:57 | nessuno | anon nulla; auth SELECT + policy owner |
| `live_ladder` | B app | service_role (upsert) | 1 file: Betfair/stream/db.py | .from lib/live.ts:490; realtime lib/live.ts:509 | nessuno | anon nulla; auth SELECT + policy owner |
| `live_now` | B app | service_role (upsert) | 7 file: Betfair/mike/service.py, Betfair/omega/omega_db.py, Betfair/omega/omega_engine.py, ... | .from lib/live.ts:117; realtime lib/live.ts:139 | nessuno | anon nulla; auth SELECT + policy owner |
| `live_signals` | B app | service_role (upsert) | 2 file: Betfair/stream/db.py, Betfair/stream/live_order_worker.py | .from lib/live.ts:429; realtime lib/live.ts:446 | nessuno | anon nulla; auth SELECT + policy owner |
| `mike_activity` | B app | service_role | 2 file: Betfair/mike/db.py, Betfair/tools/verifica_75_condizioni_2026_09_13.py | realtime lib/mike.ts:1971 | nessuno | anon nulla; auth SELECT + policy owner |
| `mike_control` | B app | service_role | 1 file: Betfair/mike/db.py | realtime lib/mike.ts:1971 | nessuno | anon nulla; auth SELECT + policy owner |
| `mike_events` | B app | service_role | 4 file: Betfair/mike/db.py, Betfair/safe_strategy/db.py, Betfair/tools/scostamento_fischio_2026_09_13.py, ... | realtime lib/mike.ts:1971 | nessuno | anon nulla; auth SELECT + policy owner |
| `mike_requests` | B app | service_role | 1 file: Betfair/mike/db.py | .from lib/mike.ts:1927; realtime lib/mike.ts:1971 | nessuno | anon nulla; auth SELECT + policy owner |
| `mike_trades` | B app | service_role | 3 file: Betfair/mike/db.py, Betfair/tools/verifica_75_condizioni_2026_09_13.py, Betfair/tools/verifica_pnl_2026_09_12.py | realtime lib/mike.ts:1971 | nessuno | anon nulla; auth SELECT + policy owner |
| `omega_control` | B app | service_role (insert/update) | 2 file: Betfair/omega/omega_db.py, tools/omega_watch.py | realtime lib/omega.ts:1257 | nessuno | anon nulla; auth SELECT + policy owner |
| `omega_events` | B app | service_role (delete/update/upsert) | 3 file: Betfair/mike/db.py, Betfair/omega/omega_db.py, Betfair/safe_strategy/bot_db.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `omega_manual_requests` | B app | service_role (insert/update/upsert) | 1 file: Betfair/omega/omega_db.py | realtime lib/omegaProposte.ts:241 | nessuno | anon nulla; auth SELECT + policy owner |
| `omega_market_snapshot` | B app | service_role (upsert) | 1 file: Betfair/omega/omega_db.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `omega_missions` | B app | service_role (update) | 1 file: Betfair/omega/omega_db.py | realtime lib/omegaMissions.ts:216 | nessuno | anon nulla; auth SELECT + policy owner |
| `omega_trades` | B app | service_role (delete/insert/update) | 3 file: Betfair/omega/omega_db.py, Betfair/tools/verifica_margine_2026_09_12.py, Betfair/tools/verifica_pnl_2026_09_12.py | realtime lib/omega.ts:1258, lib/omegaMissions.ts:217 | nessuno | anon nulla; auth SELECT + policy owner |
| `safe_strategy_activity` | B app | service_role (insert) | 1 file: Betfair/safe_strategy/bot_db.py | .from lib/safeBot.ts:1098; realtime lib/safeBot.ts:1320 | nessuno | anon nulla; auth SELECT + policy owner |
| `safe_strategy_control` | B app | service_role (insert/update) | 1 file: Betfair/safe_strategy/bot_db.py | realtime lib/safeBot.ts:1316 | nessuno | anon nulla; auth SELECT + policy owner |
| `safe_strategy_opportunities` | B app | service_role (delete/upsert) | 1 file: Betfair/safe_strategy/bot_db.py | .from lib/safeBot.ts:1360; realtime lib/safeBot.ts:1374 | nessuno | anon nulla; auth SELECT + policy owner |
| `safe_strategy_requests` | B app | service_role (insert/update) | 1 file: Betfair/safe_strategy/bot_db.py | .from lib/controlRoomProposte.ts:340, lib/safeBot.ts:1301; realtime lib/controlRoomProposte.ts:388, lib/safeBot.ts:1318 | nessuno | anon nulla; auth SELECT + policy owner |
| `safe_strategy_scan` | B app | service_role (delete/upsert) | 4 file: Betfair/mike/db.py, Betfair/safe_strategy/bot_db.py, Betfair/safe_strategy/db.py, ... | .from lib/safeStrategyScan.ts:324; realtime lib/safeStrategyScan.ts:349 | nessuno | anon nulla; auth SELECT + policy owner |
| `safe_strategy_status` | B app | service_role (upsert) | 5 file: Betfair/mike/db.py, Betfair/safe_strategy/bot_db.py, Betfair/safe_strategy/db.py, ... | .from lib/safeStrategyScan.ts:331; realtime lib/safeStrategyScan.ts:374 | nessuno | anon nulla; auth SELECT + policy owner |
| `safe_strategy_trades` | B app | service_role (delete/insert/update) | 2 file: Betfair/safe_strategy/bot_db.py, Betfair/tools/verifica_pnl_2026_09_12.py | realtime lib/safeBot.ts:1317 | nessuno | anon nulla; auth SELECT + policy owner |
| `tennis_bot_activity` | B app | service_role (insert) | 1 file: Betfair/stream/tennis_live/tennis_db.py | realtime lib/tennis.ts:768 | nessuno | anon nulla; auth SELECT + policy owner |
| `tennis_bot_control` | B app | service_role (update/upsert) | 2 file: Betfair/stream/tennis_live/tennis_db.py, Betfair/stream/tennis_live/tennis_runner.py | realtime lib/tennis.ts:763 | nessuno | anon nulla; auth SELECT + policy owner |
| `tennis_live_ladder` | B app | service_role (upsert) | 1 file: Betfair/stream/tennis_live/tennis_db.py | .from lib/tennis.ts:263; realtime lib/tennis.ts:276 | nessuno | anon nulla; auth SELECT + policy owner |
| `tennis_live_now` | B app | service_role (upsert) | 1 file: Betfair/stream/tennis_live/tennis_db.py | .from lib/tennis.ts:209; realtime lib/tennis.ts:243 | nessuno | anon nulla; auth SELECT + policy owner |
| `tennis_live_orders` | B app | service_role (upsert) | 1 file: Betfair/stream/tennis_live/tennis_db.py | realtime lib/tennis.ts:485 | nessuno | anon nulla; auth SELECT + policy owner |
| `tennis_live_positions` | B app | service_role (upsert) | 1 file: Betfair/stream/tennis_live/tennis_db.py | realtime lib/tennis.ts:501 | nessuno | anon nulla; auth SELECT + policy owner |
| `tennis_markets` | B app | service_role (delete/upsert) | 2 file: Betfair/stream/tennis_live/tennis_bot_service.py, betfair_tennis_odds.py | realtime lib/tennis.ts:225 | nessuno | anon nulla; auth SELECT + policy owner |
| `theta_confirm_requests` | B app | service_role (insert/update) | 1 file: Betfair/stream/scalper/scalper_session.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `analytics_bets` | C servizio | service_role | 1 file: _certify_direction.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `analytics_decisions` | C servizio | service_role | 2 file: certify_backtest_strategy.py, merge_engine_signals.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `analytics_prob_staging` | C servizio | - (nessun client nel repo) | - | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `analytics_signals` | C servizio | service_role (update/upsert) | 6 file: _certify_direction_report.py, build_analytics_signals.py, certify_backtest_strategy.py, ... | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `analytics_snap_staging` | C servizio | service_role (delete/upsert) | 1 file: enrich_analytics_snapshots.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `bet_features` | C servizio | service_role | 4 file: _league_eval.py, _stack_eval.py, build_direzione.py, ... | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `betfair_live_audit` | C servizio | service_role (insert) | 2 file: Betfair/stream/daily_stop_worker.py, Betfair/stream/live_order_worker.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `betfair_live_journal` | C servizio | service_role (insert) | 2 file: Betfair/stream/db.py, Betfair/stream/live_order_worker.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `betfair_live_order_requests` | C servizio | service_role (update) | 6 file: Betfair/mike/db.py, Betfair/omega/omega_db.py, Betfair/safe_strategy/bot_db.py, ... | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `betfair_live_risk_rules` | C servizio | service_role | 3 file: Betfair/stream/reconcile_worker.py, Betfair/stream/risk_engine_worker.py, Betfair/stream/runner.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `betfair_live_settings` | C servizio | - (nessun client nel repo) | - | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `betfair_live_settled` | C servizio | service_role (upsert) | 2 file: Betfair/stream/daily_stop_worker.py, Betfair/stream/db.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `betfair_live_xhedge` | C servizio | service_role (upsert) | 2 file: Betfair/stream/risk_engine_worker.py, Betfair/stream/xhedge_worker.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `betfair_market_odds` | C servizio | service_role (delete/insert) | 7 file: Betfair/odds_refresh.py, Betfair/omega/tools/banco_fusione.py, Betfair/omega/tools/m2_pesi.py, ... | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `betfair_order_requests` | C servizio | service_role | 1 file: Betfair/order_worker.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `betfair_refresh_requests` | C servizio | service_role | 1 file: Betfair/refresh_worker.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `book_odds_cache` | C servizio | - (nessun client nel repo) | - | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `direction_pagella` | C servizio | service_role (delete/upsert) | 2 file: _certify_direction.py, build_direzione.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `live_backtest_results` | C servizio | service_role (delete/insert) | 1 file: Betfair/stream/db.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `live_market_snapshots` | C servizio | service_role | 1 file: Betfair/stream/db.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `live_markets` | C servizio | service_role (upsert) | 1 file: Betfair/stream/db.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `live_run_log` | C servizio | service_role (upsert) | 1 file: Betfair/stream/db.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `live_score_timeline` | C servizio | service_role | 1 file: Betfair/stream/db.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `omega_activity` | C servizio | service_role (insert) | 2 file: Betfair/omega/omega_db.py, tools/omega_watch.py | realtime lib/omega.ts:1263 | nessuno | anon nulla; auth SELECT + policy owner |
| `omega_build_jobs` | C servizio | - (nessun client nel repo) | - | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `omega_daily_goal` | C servizio | service_role (upsert) | 1 file: Betfair/omega/omega_db.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `omega_ht_ft_transitions` | C servizio | service_role | 1 file: Betfair/omega/tools/m2_pesi.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `omega_minute_league_counts` | C servizio | service_role | 1 file: Betfair/omega/tools/estrai_transizioni.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `omega_minute_transitions` | C servizio | service_role | 2 file: Betfair/omega/tools/estrai_transizioni.py, Betfair/omega/tools/m2_pesi.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `personal_cash_movements` | C servizio | - (nessun client nel repo) | - | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `personal_trade_legs` | C servizio | - (nessun client nel repo) | - | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `personal_trades` | C servizio | service_role (delete) | 1 file: _certify_personal_report.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `personal_watchlist` | C servizio | service_role | 2 file: Betfair/stream/db.py, Betfair/stream/watchlist.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `scalper_activity` | C servizio | service_role (insert) | 2 file: Betfair/stream/scalper/scalper_service.py, Betfair/stream/scalper/scalper_session.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `scalper_control` | C servizio | service_role (insert/update) | 2 file: Betfair/stream/scalper/scalper_service.py, Betfair/stream/scalper/scalper_session.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `strategies` | C servizio | service_role | 1 file: Betfair/stream/scalper/run_scalper_live.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `tennis_bot_service_control` | C servizio | service_role | 1 file: Betfair/stream/tennis_live/tennis_db.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `tennis_live_follow` | C servizio | service_role (update/upsert) | 1 file: Betfair/stream/tennis_live/tennis_db.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `tennis_live_order_queue` | C servizio | service_role (insert) | 2 file: Betfair/stream/tennis_live/tennis_db.py, Betfair/stream/tennis_live/tennis_live_order_worker.py | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |
| `tennis_refresh_requests` | C servizio | - (nessun client nel repo) | - | no (solo via RPC DEFINER) | nessuno | anon nulla; RLS; auth al piu' SELECT owner |

Note alla tabella:
- `league_season_riepilogo_popolamento`, `missing_fixture_coverage`, `betfair_live_settings`,
  `book_odds_cache`, `omega_build_jobs`, `analytics_prob_staging`, `personal_cash_movements`,
  `personal_trade_legs`, `tennis_refresh_requests`: nessun nome letterale nel Python del repo; sono
  toccate da RPC SECURITY DEFINER (come `postgres`) o da processi non nel repo. Nessuna e' letta dalla UI
  con `.from()`.
- `match_odds` compare in `lib/safeBot.ts` solo come testo, non come `.from()`.
- Le viste `v_*` non sono usate da nessun codice (0 riferimenti Python/TS); `bet_features` e' letta da
  Python (service_role) e dalle RPC analytics (DEFINER).

### 2.2 RPC

- **132 RPC chiamate dal frontend** (grep `supabase.rpc('...` in `frontend/src`, esclusi test): tutte
  definite in `migrations/` o `sql/`, **tutte SECURITY DEFINER** (analisi statica di 172 funzioni; le
  uniche non DEFINER sono gli helper interni `_feat_expr`, `book_odds`, `_prob_bucket`,
  `_tennis_bot_control_json`, `update_updated_at_column`, mai chiamati dalla UI). Girano come `postgres`,
  proprietario delle tabelle: la RLS non le tocca (niente FORCE RLS in nessun blocco).
- **151 delle 167 DEFINER** hanno gia' `REVOKE ... FROM anon` nelle migrazioni; le 16 senza sono le 11
  del reperto 2 + `omega_request_approve/ignore`, `safe_request_approve/ignore` (hanno il controllo
  owner nel corpo) + `block_non_owner_signup` (funzione di trigger).
- **Python** chiama RPC con service_role (es. `request_betfair_live_order`, `get_market_frequency`,
  `upsert_imported_trade`, `upsert_cash_movement`, `leagues_needing_retrain`,
  `refresh_api_coverage_by_season_v2_mv`, `flush_analytics_snap_staging`, `get_*_aggregates`): i blocchi
  danno a service_role EXECUTE esplicito su tutto.
- `betfair_live_is_owner()` (`migrations/betfair_live_order_queue.sql:176-194`): controllo owner usato
  dalle RPC e dalle policy del realtime; authenticated deve poterla eseguire
  (`migrations/realtime_orders_bots.sql:23`): i blocchi lo preservano e lo verificano.

### 2.3 Realtime della UI

35 tabelle sottoscritte con `postgres_changes` (`lib/live.ts`, `lib/liveOrders.ts`, `lib/omega.ts`,
`lib/omegaMissions.ts`, `lib/omegaProposte.ts`, `lib/safeBot.ts`, `lib/safeStrategyScan.ts`,
`lib/controlRoomProposte.ts`, `lib/tennis.ts`, `lib/analytics.ts`, `lib/mike.ts:1971`): 34 del gruppo B
piu' `omega_activity` (gruppo C). Per consegnare righe servono TRE cose: tabella nella publication
`supabase_realtime`, `GRANT SELECT` al ruolo del frontend (authenticated), una policy RLS di SELECT che
lo riguardi. `omega_activity` aveva solo la prima (`migrations/omega_activity_realtime_2026-09-12.sql`)
e ha `REVOKE ALL FROM authenticated` (`migrations/omega_bot.sql:81`): per questo e' muta dal 12/09.
`verifica_b1()` controlla tutte e 35 e segnala come INFO quelle a cui manca qualcosa (difetti preesistenti
da portare all'utente, NON corretti di iniziativa: aggiungerle alla publication aumenta il traffico
realtime).

---

## 3. Strategia: tre blocchi in ordine di rischio

Principi applicati (tutti verificati nel codice, sezione 1-2):
- `service_role` ha BYPASSRLS: bot, runner, action e `make-daily-post` non sentono la RLS. Ogni blocco lo
  controlla (`verifica_b*`) e il BLOCCO 2 si ferma se non e' cosi'.
- Il frontend usa `authenticated` con login owner: si preserva ESATTAMENTE cio' che authenticated puo'
  fare oggi in lettura; si toglie solo cio' che non usa (scritture dirette, BLOCCO 3).
- RLS su tutto `public`, policy per authenticated SOLO in lettura e SOLO owner
  (`USING (public.betfair_live_is_owner())`), mai `FORCE RLS`.
- anon: via tutto tranne `INSERT` su `leads` (landing). Il login non usa i grant.
- Viste con `security_invoker = on`.
- GRANT espliciti a `service_role` su tabelle, sequenze e funzioni (prepara il 30/10).
- Ogni blocco: una transazione (o tutto o niente), idempotente, con **fotografia dei permessi prima**
  (schema privato `sicurezza_bk`, non esposto dalle API) e **rollback automatico**
  `SELECT sicurezza_bk.ripristina('Bn')` che riporta grant, RLS, policy, opzioni delle viste,
  publication e default privileges allo stato fotografato. Verifica: `SELECT * FROM
  sicurezza_bk.verifica_bn()` (sola lettura, nessun KO atteso).

### BLOCCO 1 - "zero rischio" - RISCHIO: nullo per i client del repo; residuo = client esterni con anon
Cosa: omega_activity realtime (RLS, SELECT authenticated, policy owner, publication, sequenza);
anon: via tutto su tabelle/viste/matview tranne INSERT su leads; `security_invoker` sulle viste di
proprieta' di postgres; EXECUTE tolto ad anon/PUBLIC sulle 11 RPC del reperto 2 (chi le esegue oggi -
authenticated, ruoli di sistema - riceve prima un grant esplicito); GRANT ALL a service_role su tabelle e
sequenze.
Perche' i client continuano a funzionare:
- frontend loggato: guadagna solo SELECT su omega_activity; tutto il resto di authenticated e' reso
  esplicito identico (anche se lo avesse via PUBLIC);
- landing: `leads` INSERT resta (grant + policy `leads_anon_insert`);
- login: GoTrue, non toccato;
- Python/Actions/make-daily-post: service_role, solo conferme;
- telegram-bot: gia' cieco, invariato;
- viste: nessun client le legge con anon/authenticated; service_role bypassa la RLS; le RPC DEFINER sono
  del proprietario delle tabelle.
Effetto collaterale atteso: con omega_activity viva, la pagina Omega ricarica `get_omega_state` a ogni
evento (debounce 1,2 s, `pages/Omega.tsx:79,244`) invece di ogni 15 s -> piu' letture DB mentre la pagina
e' aperta (tenerlo presente dopo il 13/09 del budget IO).

### BLOCCO 2 - RLS e policy - RISCHIO: basso
Cosa: guardia bloccante (se il proprietario di una RPC DEFINER non bypasserebbe la RLS di una tabella, o
service_role non ha BYPASSRLS, il blocco si ferma SENZA modifiche); RLS attiva su ogni tabella di public
che non ce l'ha; dove authenticated ha SELECT, policy `<tabella>_select_owner` (solo lettura, solo owner).
Perche' i client continuano a funzionare: le letture dirette della UI sono su tabelle che hanno GIA' RLS e
policy (non cambiano); le 132 RPC sono DEFINER di postgres; service_role bypassa; authenticated perde le
SCRITTURE dirette sulle tabelle che ricevono la RLS (nessun codice le fa: tutti i `.from()` della UI sono
SELECT, tranne `leads` che ha gia' RLS e policy).
Rischio residuo: un proprietario diverso da postgres per tabelle o RPC (la guardia lo intercetta); una
policy preesistente non nel repo su una tabella a cui si accende la RLS (se c'e', la si lascia: in quel
caso il blocco non aggiunge la sua e `verifica_b2` mostra INFO se authenticated vede 0 righe).

### BLOCCO 3 - chiusura finale di anon - RISCHIO: basso-medio (tocca TUTTE le funzioni)
Cosa: EXECUTE via ad anon e PUBLIC su ogni funzione di public (escluse estensioni e le funzioni dei
default/trigger di `leads`), con grant espliciti preservati per authenticated e i ruoli di sistema che le
eseguono oggi, service_role su tutto; sequenze chiuse ad anon (tranne quella di leads: USAGE); anon
ribadito a zero sulle relazioni; **authenticated SOLO LETTURA** (via INSERT/UPDATE/DELETE/TRUNCATE/
REFERENCES/TRIGGER ovunque, tranne INSERT su leads); default privileges di postgres su public senza anon
per gli oggetti futuri. Opzionali commentati: 3.6 chiudere anche i lead della landing (decisione
dell'utente), 3.7 togliere a PUBLIC l'EXECUTE di default sulle funzioni future.
Perche' i client continuano a funzionare: nessun client chiama RPC con anon; authenticated conserva
esattamente le funzioni che esegue oggi (`verifica_b3` controlla una per una le 132 della UI);
betfair_live_is_owner resta ad authenticated (serve alle policy del realtime); le funzioni di trigger non
chiedono EXECUTE a chi inserisce; service_role riceve tutto in modo esplicito.
Rischio residuo: una funzione di proprieta' di un altro ruolo (non toccata, `verifica_b3` la segnala KO);
un ruolo di sistema Supabase che eseguiva una funzione di public SOLO via PUBLIC e che non e' nell'elenco
di `chiudi_funzione` (authenticated, service_role, authenticator, supabase_auth_admin,
supabase_storage_admin, supabase_realtime_admin, supabase_functions_admin, dashboard_user, pgbouncer).

### Ordine di applicazione
1. Prerequisiti della sezione 4 (sola lettura, il coordinatore): se uno fallisce, fermarsi.
2. BLOCCO 1 -> `verifica_b1()` -> prova di ruolo (sezione 6) -> checklist (sezione 7) -> giornata normale.
3. BLOCCO 2 -> `verifica_b2()` -> prova di ruolo -> checklist.
4. BLOCCO 3 -> `verifica_b3()` -> prova di ruolo -> checklist completa (bot in paper, action, Telegram).
Tra un blocco e l'altro almeno un ciclo d'uso reale dell'app. Rollback sempre in ordine inverso
(B3, poi B2, poi B1), ognuno con `BEGIN; SELECT sicurezza_bk.ripristina('Bn'); COMMIT;`.

---

## 4. Prerequisiti (SOLA LETTURA, prima del BLOCCO 1)

```sql
-- P1. proprietari di tabelle e RPC DEFINER di public (atteso: tutto postgres)
SELECT 'tabella' AS tipo, tableowner AS owner, count(*) FROM pg_tables WHERE schemaname = 'public' GROUP BY 2
UNION ALL
SELECT 'rpc definer', pg_get_userbyid(p.proowner), count(*) FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'public' AND p.prosecdef GROUP BY 2;

-- P2. ruoli (atteso: service_role bypassrls = true)
SELECT rolname, rolsuper, rolbypassrls FROM pg_roles
 WHERE rolname IN ('postgres', 'service_role', 'authenticated', 'anon', 'authenticator');

-- P3. funzioni che anon puo' eseguire OGGI (conferma del reperto 2)
SELECT p.oid::regprocedure AS funzione, p.prosecdef AS definer
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'public' AND has_function_privilege('anon', p.oid, 'EXECUTE')
 ORDER BY 1;

-- P4. policy esistenti (quelle del gruppo A non sono nel repo)
SELECT tablename, policyname, cmd, roles, qual, with_check
  FROM pg_policies WHERE schemaname = 'public' ORDER BY 1, 2;

-- P5. leads: trigger, default e sequenza (per le esenzioni del BLOCCO 3)
SELECT tgname, tgfoid::regprocedure FROM pg_trigger WHERE tgrelid = 'public.leads'::regclass AND NOT tgisinternal;
SELECT column_name, column_default, is_identity FROM information_schema.columns
 WHERE table_schema = 'public' AND table_name = 'leads';

-- P6. viste e matview, con proprietario e opzioni; versione del server (security_invoker: PG15+)
SELECT c.oid::regclass, c.relkind, pg_get_userbyid(c.relowner), c.reloptions
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind IN ('v', 'm');
SHOW server_version;

-- P7. il ruolo postgres puo' fare SET ROLE ai ruoli API (serve alla prova di ruolo)
SELECT r.rolname FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid
 WHERE m.member = 'postgres'::regrole AND r.rolname IN ('anon', 'authenticated', 'service_role');
```

**P8. Nessun client ESTERNO usa la chiave anon** (Make, script dimenticati, altri siti). Dashboard
Supabase -> Logs -> API (edge logs), ultimi 7 giorni, filtrare le richieste `/rest/v1/` con ruolo `anon`.
Esempio per il Logs Explorer (i nomi dei campi annidati vanno controllati sullo schema del proprio
progetto):
```sql
select timestamp, r.method, r.path, h.user_agent
  from edge_logs
  cross join unnest(metadata) as m
  cross join unnest(m.request) as r
  cross join unnest(r.headers) as h
  cross join unnest(r.sb) as sb
  cross join unnest(sb.jwt) as jwt
  cross join unnest(jwt.apikey) as ak
  cross join unnest(ak.payload) as pl
 where pl.role = 'anon' and r.path like '/rest/v1/%'
 order by timestamp desc
 limit 200;
```
Atteso: solo `POST /rest/v1/leads` (landing) e le chiamate del bot Telegram su `fixture_predictions`
(gia' negate). Qualunque altra cosa: fermarsi e capire chi e' prima del BLOCCO 1.

---

## 5. Rischi residui e cose che NON si risolvono con SQL

5.1 **Chiave anon nel bundle**: resta pubblica per costruzione (serve al login). Dopo i tre blocchi, con
la sola anon si puo': fare login (serve la password dell'owner), inserire un lead. Nient'altro.

5.2 **La sicurezza si riduce alla password dell'owner**: chi la ha, ha l'app. Consigli (decisione
dell'utente, richiedono lavoro sul frontend): MFA TOTP in Supabase Auth; password lunga e unica; verificare
in Dashboard -> Authentication che "Allow new users to sign up" sia OFF e "anonymous sign-ins" OFF (il
`config.toml` in `Telegram bot/supabase/` e' solo per lo sviluppo locale, non fa fede).

5.3 **Bot Telegram cieco**: `telegram-bot` legge `fixture_predictions` con anon, a cui la SELECT e' negata
dal 22/06. Per farlo funzionare (cambio di codice, con permesso): nelle 3 righe
`Telegram bot/supabase/functions/telegram-bot/index.ts:35,328,440` usare
`Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")` (iniettata da Supabase nelle edge function, resta lato
server; precedente: `make-daily-post/index.ts:18`), poi ridistribuire la function. Verificare anche che il
webhook Telegram sia protetto (secret_token), perche' la function avrebbe poteri pieni.

5.4 **30/10**: da quella data le tabelle NUOVE non ricevono piu' grant di default, nemmeno service_role.
Ogni migrazione nuova deve portare: `ENABLE ROW LEVEL SECURITY`; `REVOKE ALL ... FROM anon, authenticated`;
`GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE ... TO service_role`; `GRANT USAGE, SELECT ON SEQUENCE ...
TO service_role` se c'e' un serial; se la UI la legge: `GRANT SELECT ... TO authenticated` + policy
owner-only; per le funzioni: `REVOKE ALL ON FUNCTION ... FROM PUBLIC, anon` + `GRANT EXECUTE ... TO
authenticated, service_role`. In alternativa, DOPO il 30/10, ripristinare il default solo per service_role
(`ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON
TABLES TO service_role;` e `... GRANT USAGE, SELECT ON SEQUENCES TO service_role;`).

5.5 **Storage**: il bucket `Loghi` e' pubblico (`make-daily-post/index.ts:99`): i file sono leggibili da
chiunque ne conosca l'URL. Non e' nello schema public e non e' toccato dai blocchi; se contiene solo
loghi e' voluto.

5.6 **Chiavi service_role**: sono nel `.env` locale, nei secrets di GitHub e nelle edge function. Chi le
ha scavalca tutto (RLS compresa). Non vanno mai nel frontend (oggi non ci sono: il bundle ha solo la anon).
Due script (`Betfair/safe_strategy/tools/conta_operazioni_live.py:35`, `storia_operazioni.py:31`)
ripiegano su `SUPABASE_KEY` se manca la service: dopo il BLOCCO 3, con una anon in quella variabile non
leggerebbero piu' nulla (nessun danno, solo uno script che non vede dati).

5.7 **Realtime di Omega**: se il canale `omega-live` (`lib/omega.ts:1254-1264`) veniva rifiutato per
intero a causa del binding su `omega_activity` non leggibile, anche `omega_control`/`omega_trades` erano
muti e oggi tutto passava dal poll dei 15 s. Ipotesi NON verificata (servono i log del client realtime):
dopo il BLOCCO 1 vale la pena guardare in console del browser lo stato del canale (`SUBSCRIBED`).

5.8 **GraphQL** (`pg_graphql`): rispetta gli stessi grant; chiudendo anon si chiude anche li'.

---

## 6. Prova di ruolo (SOLA LETTURA, dopo ogni blocco)

Si incolla nel SQL Editor cosi' com'e'. Simula anon, authenticated owner, authenticated NON owner e
service_role con `SET LOCAL ROLE` + claims JWT; legge al massimo una riga per tabella; l'unica scrittura e'
nella tabella TEMPORANEA `_prova`, che sparisce a fine richiesta. Dopo il BLOCCO 3 tutte le righe devono
essere `OK`. Dopo i soli BLOCCHI 1 e 2 la riga `has_table_privilege('public.match_odds','INSERT')` di
authenticated da' `ok:true` (le scritture di authenticated si chiudono nel BLOCCO 3): e' atteso.
`ok:null` al posto di `ok:1` vuol dire tabella vuota, non errore. Se `SET ROLE` e' negato (P7), la prova
non si puo' fare da SQL Editor: resta la checklist.

```sql
-- PROVA DI RUOLO (sola lettura: letture LIMIT 1 e has_*_privilege; l'unica scrittura e'
-- nella tabella TEMPORANEA _prova, che sparisce alla fine della richiesta)
CREATE TEMP TABLE _prova (n int, ruolo text, prova text, atteso text, ottenuto text) ON COMMIT DROP;
DO $prova$
DECLARE
    v_owner text := '{"role":"authenticated","email":"daniele.ritrovato@gmail.com"}';
    v_altro text := '{"role":"authenticated","email":"intruso@example.com"}';
    v_casi  text[] := ARRAY[
        -- ruolo | claims | sql | atteso (prefisso)
        'anon', '{}', 'SELECT 1 FROM public.match_odds LIMIT 1', 'ERR:42501',
        'anon', '{}', 'SELECT 1 FROM public.fixture_predictions LIMIT 1', 'ERR:42501',
        'anon', '{}', 'SELECT 1 FROM public.omega_activity LIMIT 1', 'ERR:42501',
        'anon', '{}', 'SELECT 1 FROM public.leads LIMIT 1', 'ERR:42501',
        'anon', '{}', 'SELECT 1 FROM public.v_es_concordance_roi LIMIT 1', 'ERR:42501',
        'anon', '{}', 'SELECT public.get_betfair_fixtures(current_date)::text', 'ERR:42501',
        'anon', '{}', 'SELECT has_table_privilege(''public.leads'', ''INSERT'')::text', 'ok:true',
        'authenticated', 'OWNER', 'SELECT public.betfair_live_is_owner()::text', 'ok:true',
        'authenticated', 'OWNER', 'SELECT 1 FROM public.fixture_predictions LIMIT 1', 'ok:1',
        'authenticated', 'OWNER', 'SELECT 1 FROM public.omega_activity LIMIT 1', 'ok:1',
        'authenticated', 'OWNER', 'SELECT 1 FROM public.omega_control LIMIT 1', 'ok:1',
        'authenticated', 'OWNER', 'SELECT has_function_privilege(''public.get_omega_state(integer)'', ''EXECUTE'')::text', 'ok:true',
        'authenticated', 'OWNER', 'SELECT has_table_privilege(''public.match_odds'', ''INSERT'')::text', 'ok:false',
        'authenticated', 'ALTRO', 'SELECT public.betfair_live_is_owner()::text', 'ok:false',
        'authenticated', 'ALTRO', 'SELECT count(*)::text FROM (SELECT 1 FROM public.omega_activity LIMIT 1) x', 'ok:0',
        'service_role', '{"role":"service_role"}', 'SELECT 1 FROM public.match_odds LIMIT 1', 'ok:1',
        'service_role', '{"role":"service_role"}', 'SELECT 1 FROM public.omega_activity LIMIT 1', 'ok:1',
        'service_role', '{"role":"service_role"}', 'SELECT has_table_privilege(''public.match_odds'', ''INSERT, UPDATE, DELETE'')::text', 'ok:true'
    ];
    i       int := 1;
    n       int := 0;
    v_claim text;
    v_out   text;
BEGIN
    WHILE i <= array_length(v_casi, 1) LOOP
        n := n + 1;
        v_claim := CASE v_casi[i + 1] WHEN 'OWNER' THEN v_owner WHEN 'ALTRO' THEN v_altro ELSE v_casi[i + 1] END;
        BEGIN
            PERFORM set_config('request.jwt.claims', v_claim, true);
            EXECUTE format('SET LOCAL ROLE %I', v_casi[i]);
            EXECUTE v_casi[i + 2] INTO v_out;
            v_out := 'ok:' || coalesce(v_out, 'null');
            EXECUTE 'RESET ROLE';
        EXCEPTION WHEN others THEN
            v_out := 'ERR:' || SQLSTATE || ' ' || left(SQLERRM, 80);
        END;
        EXECUTE 'RESET ROLE';
        INSERT INTO _prova VALUES (n, v_casi[i], v_casi[i + 2], v_casi[i + 3], v_out);
        i := i + 4;
    END LOOP;
END
$prova$;
SELECT n, ruolo, prova, atteso, ottenuto,
       CASE WHEN ottenuto LIKE atteso || '%' THEN 'OK' ELSE 'KO' END AS esito
  FROM _prova ORDER BY n;
```

---

## 7. Checklist di prova manuale dopo ogni blocco

App (loggato come owner, app desktop avviata dall'utente):
- [ ] Login dalla landing, logout, di nuovo login. Reset password (solo se si vuole provarlo).
- [ ] Da NON loggati: la landing si apre; il form "registrati" mostra il banner "non ancora pronti".
- [ ] Dashboard calcio: lista partite e selettore fixture (leggono `fixture_predictions`).
- [ ] Control Room: si apre, saldo Betfair, heartbeat, proposte Safe (realtime `safe_strategy_requests`).
- [ ] Ladder calcio e tennis: le quote si muovono (canale locale e realtime `live_ladder`/`tennis_live_ladder`).
- [ ] Omega: la pagina carica; con il servizio acceso, gli eventi del log compaiono SUBITO (non dopo 15 s)
      = punto 14; console del browser: canale `omega-live` in `SUBSCRIBED`.
- [ ] Safe, Mike, Tennis: pagine caricate, log di attivita' in tempo reale.
- [ ] Ordine PAPER da ladder (accodamento `request_betfair_live_order`) e annullamento: l'ordine compare e
      sparisce nella griglia ordini (realtime `betfair_live_orders`).
- [ ] Analytics, Direzione, Report personale, Storico calcio/tennis: si aprono e mostrano dati.

Bot e servizi (li accende SOLO l'utente dalla UI):
- [ ] Avvio di un bot in PAPER (es. Omega o Safe): stato "attivo", log in UI, nessun errore di permessi
      nei log del servizio (`permission denied`, `42501`, `row-level security`).
- [ ] Runner calcio/tennis: scrive `live_now`/`live_ladder` (la UI li vede).

GitHub Actions:
- [ ] Un `workflow_dispatch` di una action leggera (es. `ml_calibration` o `leagues_mapper`) termina
      verde, senza `42501`/`permission denied`.

Telegram:
- [ ] Un comando al bot. Atteso: come prima del blocco (oggi non vede le previsioni, vedi 5.3). Se prima
      funzionava e dopo no, rollback del blocco e segnalarlo.

Se qualunque punto fallisce: `BEGIN; SELECT sicurezza_bk.ripristina('Bn'); COMMIT;` per l'ultimo blocco
applicato e referto al coordinatore.

---

## 8. Come sono stati provati i file (banco locale, nessun DB vero)

`_tmp_sicurezza/pgl/prova.mjs` nel worktree del delegato: PGlite (Postgres 17 in WASM) con un "finto
Supabase" (`setup_finto_supabase.sql`: ruoli anon/authenticated/service_role BYPASSRLS, default
privileges di Supabase, `auth.jwt()`, publication `supabase_realtime`, e un campione di oggetti che ricalca
snapshot e migrazioni: tabella A senza RLS, tabella A con RLS senza policy, vista v_es, fixture_predictions
e leads come `security_lockdown.sql` con trigger e default a funzione, omega_control gruppo B,
omega_activity gruppo C, betfair_market_odds, 4 RPC esposte, 1 RPC corretta, 1 helper).
Esiti: B1, B2, B3 applicati DUE volte ciascuno (idempotenza) -> `verifica_b1/2/3` 0 KO; 31 casi di ruolo
tutti come attesi (anon negato ovunque tranne INSERT leads con trigger e default; owner legge
fixture_predictions/omega_activity/omega_control/match_odds ed esegue le RPC; non-owner vede 0 righe;
authenticated non scrive; service_role fa tutto, anche la vista con security_invoker); la prova di ruolo
della sezione 6: 18/18 OK; rollback B3 -> B2 -> B1: stato dei permessi IDENTICO a ogni fotografia (a meno
dei grant espliciti aggiunti a service_role). Falsificazione (5 mutazioni, tutte rosse): INSERT di leads
chiuso -> KO in verifica_b1 + caso di ruolo; senza la policy di omega_activity -> 2 KO + owner vede 0
righe; senza `chiudi_funzione` -> 7 KO + 3 casi; FORCE RLS -> 2 KO in verifica_b2; RPC DEFINER di un
altro proprietario -> il BLOCCO 2 si ferma senza modifiche.
Limiti del banco: in PGlite `postgres` e' superuser (su Supabase no: e' proprietario); non c'e' il server
Realtime (la consegna degli eventi si prova solo sull'app vera, checklist 7); gli oggetti sono un campione.

---

## 9. Cosa NON e' stato verificato (lo verifica il coordinatore, in sola lettura)

- Lo stato vero del DB oltre lo snapshot del 23/09: policy reali del gruppo A, proprietari, funzioni
  eseguibili da anon (P1-P7), versione del server.
- Il ruolo reale delle chiavi: che `SUPABASE_SERVICE_ROLE_KEY` nel `.env` e nei secrets di GitHub sia
  davvero la service (non ho decodificato le chiavi: lettura del `.env` negata dal sistema di permessi).
- I log API (P8): se esiste un client esterno che usa anon.
- Se le 34 tabelle B sottoscritte dalla UI sono tutte nella publication (lo dice `verifica_b1`).
- Il comportamento del SQL Editor di Supabase con `BEGIN/COMMIT` espliciti e con la tabella temporanea
  `ON COMMIT DROP` della prova di ruolo (in PGlite funziona).
- I log del bot Telegram e della edge function.
