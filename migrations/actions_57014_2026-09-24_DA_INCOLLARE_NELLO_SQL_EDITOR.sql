-- =============================================================================
-- Blocchi SICURI e MIGLIORATIVI della migrazione actions_57014 (verificati sul DB
-- il 24/09/2026 h07 UTC dal coordinatore, in sola lettura). Da incollare nello
-- SQL Editor di Supabase (progetto dqbwaocvlzbxfrpacsac), UN BLOCCO ALLA VOLTA,
-- con nessuna action in corso (Actions -> nessun run "in_progress").
-- Nessun blocco cambia un valore calcolato: risultati IDENTICI, meno timeout.
-- Il coordinatore NON ha potuto eseguirli (classificatore: cancellazioni di
-- massa e modifiche a risorse condivise sono vietate in modalita' automatica).
-- =============================================================================

-- BLOCCO A: avanzi della tabella di transito (misurato: 67.244 righe, 1.761 fixture).
-- Nessuna perdita: i valori si ricalcolano a ogni run; da ieri il codice pulisce
-- da solo la staging della lega prima di ogni copia (P2), qui si parte puliti.
select count(*) as prima from public.analytics_snap_staging;
delete from public.analytics_snap_staging;
select count(*) as dopo from public.analytics_snap_staging;   -- atteso 0

-- BLOCCO B: timeout proprio di 120 s sulle 3 RPC di scrittura (oggi ereditano
-- gli 8 s del ruolo). Annullamento: ... RESET statement_timeout.
alter function public.flush_analytics_snap_staging(bigint)   set statement_timeout = '120s';
alter function public.bulk_update_prediction_results(jsonb)  set statement_timeout = '120s';
alter function public.leagues_needing_retrain(integer)       set statement_timeout = '120s';
select proname, proconfig from pg_proc
 where proname in ('flush_analytics_snap_staging','bulk_update_prediction_results','leagues_needing_retrain');

-- BLOCCO C (solo il doppione): idx_fixture_predictions_date ha 0 letture ed e'
-- un duplicato di idx_fixture_predictions_fixture_date (3.172 letture).
-- NON toccare league_season (12 letture dal 21/09) ne' i due GIN (decisione tua).
-- Fuori da una transazione, uno alla volta.
drop index concurrently if exists public.idx_fixture_predictions_date;
-- ripristino: create index idx_fixture_predictions_date on public.fixture_predictions using btree (fixture_date);

-- BLOCCO D: statistiche del pianificatore su match_odds (92,5 M righe, ultimo
-- autoanalyze 07/09). Solo a DB scarico (nessuna Retrain/backfill in corso):
-- legge un campione della tabella per qualche minuto, non cambia dati.
analyze public.match_odds;

-- BLOCCO E: NON applicare senza misura. Dopo A, misura del piano della copia su
-- una lega grande (129); crea l'indice SOLO se il piano non usa gia' un Index Scan
-- su idx_as_fixture:
-- explain update public.analytics_signals s set freq_home = st.freq_home
--   from public.analytics_snap_staging st
--  where s.league_id = 129 and s.fixture_id = st.fixture_id
--    and s.market = st.market and s.selection = st.selection;
-- create index concurrently if not exists idx_as_fixture_market_selection
--     on public.analytics_signals (fixture_id, market, selection);
