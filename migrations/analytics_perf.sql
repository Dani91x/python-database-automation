-- ============================================================================
-- ANALYTICS PERF — indici covering + VACUUM/ANALYZE + tuning autovacuum (2026-06-22)
-- ============================================================================
-- OBIETTIVO: rendere il centro di controllo /analytics veloce e POCO STRESSANTE
-- per il DB (I/O-bound), SENZA toccare gli RPC né cambiare i numeri restituiti.
--
-- DIAGNOSI (EXPLAIN ANALYZE su ~50k righe per tabella):
--   • get_analytics group_by=confidence su TUTTE le leghe → Seq Scan di
--     analytics_signals: ~1575 buffer, ~100 ms. Legge 49.7k/50.3k righe.
--   • get_decisions group_by=engine (e filtri per engine) → Seq Scan di
--     analytics_decisions: ~2000 buffer, ~37-50 ms. Gli indici esistenti
--     (engine,market,selection) NON coprono stake/pnl/edge/odds/prob/status/
--     settled/hit → anche usandoli servirebbe un heap-fetch per riga (lento).
--   • PROVA del valore: il group_by=decision_logic usa GIÀ un Index-Only Scan
--     su idx_ad_logic_status → 48 buffer (vs 2039 del seq scan). Stessa idea.
--
-- SOLUZIONE (stessa best-practice di idx_fp_api_full): COVERING INDEX parziali
-- con INCLUDE di tutte le colonne lette dall'aggregazione → INDEX-ONLY SCAN
-- (zero heap-fetch) → meno buffer letti = meno I/O = meno stress, a parità di
-- risultati. Gli indici NON cambiano i numeri: il planner sceglie solo se sono
-- più economici; altrimenti li ignora.
--
-- ⚠️ NOTA: gli Index-Only Scan richiedono una VISIBILITY MAP fresca → VACUUM
-- (sotto) + tuning autovacuum (già impostato in analytics_rpc.sql; qui ribadito
-- e applicato anche ad analytics_decisions).
--
-- Idempotente: CREATE INDEX IF NOT EXISTS + ALTER ... SET. Rilanciabile.
-- TOCCA SOLO indici / vacuum / storage params. NESSUNA modifica a tabelle o RPC.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1) analytics_signals — covering per il broad/confidence scan di get_analytics
-- ----------------------------------------------------------------------------
-- get_analytics e get_analytics_rows scansionano analytics_signals con il
-- predicato fisso  (settled AND hit IS NOT NULL AND prob IS NOT NULL)  e leggono
-- engine, league_id, league_name, season_year, kickoff, market, selection,
-- prob, hit. Un indice PARZIALE su quel predicato, con chiave (engine) — il
-- filtro più comune — e INCLUDE delle altre colonne, copre l'intera lettura:
--   • broad / confidence (nessun filtro engine): index-only scan dell'INTERA
--     popolazione valutata, ma su un indice stretto (no heap, no colonne morte);
--   • filtro per engine: index-only scan ristretto a quel motore.
-- I filtri più selettivi (engine+market+league) restano serviti dall'esistente
-- idx_as_engine_market_league (già ottimale, ~6 buffer); questo è per il broad.
create index if not exists idx_as_eval_cover
    on analytics_signals (engine)
    include (league_id, league_name, season_year, kickoff, market, selection, prob, hit)
    where settled and hit is not null and prob is not null;

-- ----------------------------------------------------------------------------
-- 2) analytics_decisions — covering per get_decisions per engine / broad
-- ----------------------------------------------------------------------------
-- get_decisions legge per ogni riga: decision_logic, status, settled, hit,
-- stake, pnl, edge, odds, prob (+ market/selection per i raggruppamenti
-- selection). Chiave (engine) — filtro/raggruppamento comune e non coperto da
-- index-only oggi — con INCLUDE del resto → index-only scan al posto del seq
-- scan da ~2000 buffer. Per group_by=logic c'è già idx_ad_logic_status.
create index if not exists idx_ad_engine_cover
    on analytics_decisions (engine)
    include (decision_logic, status, settled, hit, stake, pnl, edge, odds, prob, market, selection);

-- ----------------------------------------------------------------------------
-- 3) TUNING autovacuum — soglie basse per tenere fresca la VISIBILITY MAP
--    (gli Index-Only Scan ne dipendono). analytics_signals è già impostata in
--    analytics_rpc.sql; qui idempotente + estesa ad analytics_decisions.
-- ----------------------------------------------------------------------------
alter table analytics_signals   set (autovacuum_vacuum_scale_factor = 0.05, autovacuum_analyze_scale_factor = 0.02);
alter table analytics_decisions set (autovacuum_vacuum_scale_factor = 0.05, autovacuum_analyze_scale_factor = 0.02);

-- ----------------------------------------------------------------------------
-- 4) VACUUM ANALYZE — popola la visibility map (Index-Only Scan = zero heap)
--    e aggiorna le statistiche del planner sui nuovi indici.
--    NB: VACUUM non può girare in un blocco transazionale; eseguito a parte
--    (vedi sotto / lanciato separatamente sul DB).
-- ----------------------------------------------------------------------------
analyze analytics_signals;
analyze analytics_decisions;

-- VACUUM (ANALYZE) va lanciato fuori da una transazione. Comandi (eseguiti sul DB):
--   VACUUM (ANALYZE) analytics_signals;
--   VACUUM (ANALYZE) analytics_decisions;
