-- ============================================================================
-- live_ladder.sql — ladder LIVE per-mercato (Betting Toolkit / Bet Angel / Geeks Toy)
-- Step 1 (pipeline dati ladder, SOLA LETTURA): il runner pubblica QUI la ladder
-- PIENA di ogni mercato sottoscritto, costruita dai soli dati dello stream Betfair
-- GIA' sottoscritto (recorder.latest_books) → ZERO chiamate API aggiuntive.
--
-- Una riga per (event_id, market_id), aggiornata in modalita' WRITE-ON-CHANGE dal
-- ladder_worker (firma su back/lay/trd/ltp): nessuna scrittura se il book non e'
-- cambiato. Carico I/O contenuto (incidente I/O Supabase 2026-06-13): la pagina
-- ladder sottoscrive QUESTA tabella via Supabase Realtime, filtrando per market_id.
--
-- ladder JSONB:
--   { updated_ms,
--     selections: [
--       { selection_id, name, ltp, tv,
--         back: [[price,size], ...],   -- disponibile al BACK (best first)
--         lay:  [[price,size], ...],   -- disponibile al LAY  (best first)
--         trd:  [[price,vol],  ...],   -- volume tradato per-prezzo (EUR)
--         wom:  { back_pct, lay_pct }  -- weight of money vicino al best (~3 livelli)
--       }, ...
--     ]
--   }
--
-- Convenzioni progetto (come live_stream.sql / live_signals.sql):
--   schema public, snake_case, *_at TIMESTAMPTZ default now(), RLS ON,
--   REVOKE ALL FROM anon, authenticated. Accesso dati SOLO via RPC SECURITY
--   DEFINER — ECCEZIONE: live_ladder ha una policy SELECT per 'authenticated'
--   perche' Supabase Realtime richiede il privilegio di lettura sul ruolo che
--   sottoscrive (pattern identico a live_now / live_signals). MAI ad anon.
--   NON usiamo FORCE RLS → il backend (service_role) bypassa la RLS.
--   Tutto IDEMPOTENTE: CREATE TABLE/INDEX IF NOT EXISTS, CREATE/DROP POLICY.
-- ============================================================================

------------------------------------------------------------------------------
-- live_ladder — ladder corrente di UN mercato (1 riga per event_id+market_id).
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.live_ladder (
    id           BIGSERIAL PRIMARY KEY,
    -- NOT NULL obbligatorio: l'indice UNIQUE (event_id, market_id) arbitra l'ON CONFLICT
    -- e in Postgres i NULL sono DISTINTI → con colonne nullable l'upsert duplicherebbe
    -- silenziosamente le righe. FK a live_follow: pulizia automatica (no ladder orfane)
    -- quando l'evento viene rimosso; il runner registra live_follow PRIMA di sottoscrivere.
    event_id     TEXT NOT NULL REFERENCES public.live_follow(event_id) ON DELETE CASCADE,
    market_id    TEXT NOT NULL,
    market_type  TEXT,                                  -- MATCH_ODDS, OVER_UNDER_25, ...
    market_name  TEXT,                                  -- etichetta leggibile
    status       TEXT,                                  -- OPEN|SUSPENDED|CLOSED
    ladder       JSONB NOT NULL,                        -- vedi header per la forma
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Chiave UNICA per ladder: (event_id, market_id) — NON parziale, cosi' l'upsert
-- (on_conflict='event_id,market_id') puo' usarla come arbitro. Un indice PARZIALE
-- NON e' utilizzabile da ON CONFLICT (PostgREST/Postgres → errore 42P10) e la
-- ladder non verrebbe mai scritta.
CREATE UNIQUE INDEX IF NOT EXISTS idx_live_ladder_event_market
    ON public.live_ladder (event_id, market_id);
-- la pagina ladder sottoscrive/filtra per market_id → indice dedicato.
CREATE INDEX IF NOT EXISTS idx_live_ladder_market
    ON public.live_ladder (market_id);

-- ============================================================================
-- RLS + lockdown — coerente con live_stream.sql / live_signals.sql.
-- Default: nessun accesso diretto da anon/authenticated; il backend (service_role)
-- bypassa la RLS. ECCEZIONE: SELECT per 'authenticated' (owner loggato) richiesta
-- da Supabase Realtime, MAI ad anon.
-- ============================================================================
ALTER TABLE public.live_ladder ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.live_ladder FROM anon, authenticated;
-- difesa in profondita': niente USAGE/SELECT sulla sequenza BIGSERIAL ad anon/auth
REVOKE ALL ON SEQUENCE public.live_ladder_id_seq FROM anon, authenticated;

DROP POLICY IF EXISTS live_ladder_select_authenticated ON public.live_ladder;
CREATE POLICY live_ladder_select_authenticated ON public.live_ladder
    FOR SELECT TO authenticated
    USING (true);

GRANT SELECT ON TABLE public.live_ladder TO authenticated;
REVOKE SELECT ON TABLE public.live_ladder FROM anon;

-- Abilita la replica Realtime sulla tabella live_ladder (idempotente).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime'
          AND schemaname = 'public'
          AND tablename = 'live_ladder'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.live_ladder;
    END IF;
END;
$$;
