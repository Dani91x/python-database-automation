-- ============================================================================
-- STAGING SNAPSHOT FREQ/RITARDI — scrittura BULK in analytics_signals (2026-06-22)
-- ============================================================================
-- OBIETTIVO: rendere l'enrich freq/ritardi VELOCE e POCO STRESSANTE per il DB.
-- Prima: enrich_analytics_snapshots.py faceva N UPDATE riga-per-riga (46k righe
-- storiche → 46k round-trip → I/O-bound, stressante per Supabase).
-- Ora: il Python carica gli snapshot calcolati (matematica certificata di
-- analytics_market_stats, INVARIATA) in QUESTA tabella di staging via upsert a
-- batch, poi UN SOLO UPDATE ... FROM scopato alla lega scrive tutte le righe in
-- un colpo, infine la staging viene ripulita per lega. 1 UPDATE/lega invece di N.
--
-- IDENTITÀ DEI NUMERI: lo staging NON cambia la matematica. I valori sono gli
-- STESSI che il metodo riga-per-riga avrebbe scritto (certificato nel task): lo
-- staging è solo un canale di trasporto + un JOIN set-based.
--
-- SICUREZZA (repo pubblica, come le altre tabelle analytics): RLS ON + FORCE,
-- nessuna policy, REVOKE da anon/authenticated → la tabella NON è leggibile dal
-- client. Solo la service_role del backend (che bypassa la RLS) la usa. La RPC di
-- flush è SECURITY DEFINER con search_path fisso e input minimale (solo league_id).
--
-- Idempotente: CREATE TABLE/INDEX IF NOT EXISTS + CREATE OR REPLACE FUNCTION.
-- ============================================================================

CREATE TABLE IF NOT EXISTS analytics_snap_staging (
    fixture_id      BIGINT   NOT NULL,
    market          TEXT     NOT NULL,
    selection       TEXT     NOT NULL,
    freq_baseline   NUMERIC,
    freq_current    NUMERIC,
    freq_deviation  NUMERIC,
    delay_current   INTEGER,
    delay_record    INTEGER,
    delay_avg       NUMERIC,
    PRIMARY KEY (fixture_id, market, selection)
);

-- ----------------------------------------------------------------------------
-- SICUREZZA: RLS ON + FORCE, nessuna policy, REVOKE da anon/authenticated.
-- La service_role (enrich) bypassa la RLS; nessun altro ruolo legge/scrive.
-- ----------------------------------------------------------------------------
ALTER TABLE analytics_snap_staging ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_snap_staging FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE analytics_snap_staging FROM anon, authenticated;

-- ----------------------------------------------------------------------------
-- FLUSH BULK — UN SOLO UPDATE ... FROM scopato alla lega, poi pulizia staging.
-- Scrive freq_*/delay_* in analytics_signals per ogni (fixture×market×selection)
-- presente sia in staging sia in analytics_signals della lega. Ritorna il numero
-- di righe aggiornate. Pulisce SOLO le righe di staging della lega (DELETE mirato:
-- consente run concorrenti su leghe diverse senza pestarsi). Match esatto sulle
-- chiavi → identico, riga-per-riga, agli UPDATE puntuali del metodo precedente.
--
-- NOTA: si scopa alla lega tramite il JOIN su analytics_signals.league_id; lo
-- staging contiene solo le righe della lega corrente (il Python lo riempie e poi
-- chiama questa flush prima di passare alla lega successiva). Il DELETE finale usa
-- comunque solo le chiavi presenti per quella lega in analytics_signals.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.flush_analytics_snap_staging(p_league_id BIGINT)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_updated INTEGER;
BEGIN
    UPDATE analytics_signals s
       SET freq_baseline  = st.freq_baseline,
           freq_current   = st.freq_current,
           freq_deviation = st.freq_deviation,
           delay_current  = st.delay_current,
           delay_record   = st.delay_record,
           delay_avg      = st.delay_avg,
           updated_at     = NOW()
      FROM analytics_snap_staging st
     WHERE s.league_id = p_league_id
       AND s.fixture_id = st.fixture_id
       AND s.market     = st.market
       AND s.selection  = st.selection;
    GET DIAGNOSTICS v_updated = ROW_COUNT;

    -- pulizia: rimuove dalla staging SOLO le chiavi di questa lega (quelle che
    -- combaciano con analytics_signals della lega). Le altre (eventuali run
    -- concorrenti su altre leghe) restano intatte.
    DELETE FROM analytics_snap_staging st
     USING analytics_signals s
     WHERE s.league_id = p_league_id
       AND s.fixture_id = st.fixture_id
       AND s.market     = st.market
       AND s.selection  = st.selection;

    RETURN v_updated;
END;
$$;

-- la RPC è SECURITY DEFINER: NON deve essere chiamabile da anon/authenticated
-- (scrive su analytics_signals). Solo service_role.
REVOKE ALL ON FUNCTION public.flush_analytics_snap_staging(BIGINT) FROM anon, authenticated;
