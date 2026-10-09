-- =====================================================================
-- ATLANTE HAZARD: riga globale LEGGERA (09/10/2026) - DA APPLICARE A CURA
-- DELL'UTENTE (SQL editor del pannello Supabase). Nessun DROP, nessuno
-- schema cambiato: solo i dati delle versioni gia' in tabella.
-- =====================================================================
-- Referto: AUDIT_2026-10-09/fallimenti_action/ATLANTE_GLOBALE_LEGGERO.md
-- (indagine: AUDIT_2026-10-09/fallimenti_action/INDAGINE_ATLANTE_24MB.md).
--
-- Decisione dell'utente: "sul database dobbiamo scrivere il piu' leggero
-- possibile; se alcuni dati non servono non c'e' bisogno di scrivere; non
-- voglio dati vecchi; nessuna perdita di dati o qualita'".
--
-- Dal codice del 09/10 (genera_atlante.payload_globale_leggero) la action
-- scrive in public.hazard_atlas.payload SOLO 'meta' e 'global' (~0,13 MB
-- invece di ~24 MB). by_league, by_team, h2h_hint e v4 sono DERIVATI dallo
-- stato per lega (public.hazard_atlas_leghe, che NON si tocca: e' la fonte)
-- e nessun processo li legge dalla riga globale: il PC assembla il suo file
-- da hazard_atlas_leghe (modo 'domanda'; dal 09/10 anche il modo 'scarica'
-- di hazard_atlas_sync.py). La action rilegge della riga globale solo
-- watermark_event_id (colonna, intatta).
--
-- Questa migrazione porta allo stesso formato le versioni gia' in tabella
-- (7 righe, ~4,5-6,7 MB l'una su disco, 52 MB la tabella misurata il 09/10):
-- tiene nel payload solo 'meta' e 'global'. Colonne (generated_at, n_leghe,
-- n_partite, watermark_event_id) intatte.
--
-- IDEMPOTENTE: tocca solo le righe che hanno nel payload chiavi diverse da
-- 'meta' e 'global'; rilanciata non cambia nulla (0 righe).
--
-- Nessuna perdita di dati: i blocchi tolti sono funzione pura di
-- hazard_atlas_leghe + seme v3 (genera_atlante.assembla) e si riassemblano
-- quando servono (lo fa hazard_atlas_sync.py in modo 'scarica').
--
-- Quando applicarla: fuori dalla finestra notturna delle action (non fra le
-- 06:30 e le 09:30 UTC), per non sovrapporsi alla scrittura dell'atlante.
--
-- SPAZIO SU DISCO: l'UPDATE riscrive le righe; i vecchi valori TOAST (~40 MB)
-- diventano tuple morte che il VACUUM AUTOMATICO (autovacuum) rende
-- riutilizzabili da solo, senza fare nulla. Se si vuole forzarlo subito, dal
-- SQL editor del pannello, DA SOLO (non dentro BEGIN/COMMIT):
--     VACUUM (VERBOSE, ANALYZE) public.hazard_atlas;
-- Il VACUUM normale non blocca letture/scritture ma non restituisce lo spazio
-- al sistema operativo (lo riusa la tabella). Restituirlo richiede
--     VACUUM FULL public.hazard_atlas;
-- che riscrive la tabella con un lock esclusivo (7 righe leggere: pochi
-- istanti); NON e' in questa migrazione, e' una scelta dell'utente.
-- =====================================================================

BEGIN;

-- 7 righe da ~24 MB di testo JSON ciascuna: margine sul limite di 2 min.
SET LOCAL statement_timeout = '300s';

UPDATE public.hazard_atlas
   SET payload = jsonb_build_object('meta', payload -> 'meta')
                 || CASE WHEN payload ? 'global'
                         THEN jsonb_build_object('global', payload -> 'global')
                         ELSE '{}'::jsonb END
 WHERE (payload - 'meta' - 'global') <> '{}'::jsonb;

COMMIT;

-- Verifica (sola lettura) dopo l'applicazione:
--   SELECT id, generated_at, pg_column_size(payload) AS byte_su_disco,
--          (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(payload) k) AS chiavi
--     FROM public.hazard_atlas ORDER BY generated_at DESC;
--   -- atteso: chiavi = {global,meta} su ogni riga, ~0,1-0,2 MB a riga
--   SELECT pg_size_pretty(pg_total_relation_size('public.hazard_atlas'));
--   -- scende dopo il vacuum (automatico o forzato, vedi sopra)
-- Rollback: non serve per i bot (nessuno legge quei blocchi dalla riga
-- globale); se servisse un atlante intero, lo riassembla dalle righe per lega
-- hazard_atlas_sync.sincronizza (modo 'scarica') o
-- `python -m Betfair.stream.scalper.genera_atlante --stato-db --json <file>
--  --seme Betfair/omega/data/hazard_atlas_v3.json` (sola lettura del DB: senza
-- --scrivi-db non scrive nulla).
