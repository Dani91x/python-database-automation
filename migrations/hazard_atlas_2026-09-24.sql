-- =====================================================================
-- ATLANTE HAZARD nel DB (24/09/2026) - DA APPLICARE A CURA DELL'UTENTE
-- =====================================================================
-- Perche': l'atlante (P gol nei prossimi 2'/3' per lega, minuto, gol)
-- deve aggiornarsi DA SOLO man mano che si popolano i dati. La action
-- notturna lo rigenera (Betfair/stream/scalper/genera_atlante.py) e lo
-- scrive QUI; i bot sul PC lo scaricano (hazard_atlas_sync.py) in
-- Betfair/omega/data/hazard_atlas_live.json e lo ricaricano per mtime.
-- Un JSON committato ogni notte non arriverebbe ai bot (il PC non fa
-- git pull da solo) e gonfierebbe la storia git di ~4 MB a notte.
--
-- Due tabelle:
--   hazard_atlas_leghe : lo STATO GREZZO per lega (conteggi additivi +
--                        fixture_id gia' contati): la memoria della
--                        generazione incrementale. Una riga per lega.
--   hazard_atlas       : le VERSIONI assemblate (l'atlante completo nel
--                        formato v1/v2). La action ne tiene 7.
--
-- Sicurezza (coerente col blocco sicurezza del 24/09): RLS accesa e
-- nessuna policy per anon/authenticated; accesso solo con service_role
-- (action e bot). Nessun dato personale.
-- Costo: ~1 riga/notte in hazard_atlas (~4 MB jsonb, 7 tenute = ~30 MB)
-- e ~20-150 righe/notte aggiornate in hazard_atlas_leghe.
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.hazard_atlas_leghe (
    league_id          integer     PRIMARY KEY,
    league_name        text,
    n_fixtures         integer     NOT NULL DEFAULT 0,
    last_fixture_date  date,
    updated_at         timestamptz,
    stato              jsonb       NOT NULL,          -- conteggi grezzi (senza fixture_id)
    fixtures           jsonb       NOT NULL DEFAULT '[]'::jsonb   -- fixture_id gia' contati
);

COMMENT ON TABLE public.hazard_atlas_leghe IS
    'Atlante Hazard: stato grezzo per lega (generazione incrementale, genera_atlante.py)';

CREATE TABLE IF NOT EXISTS public.hazard_atlas (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    generated_at        timestamptz NOT NULL,
    n_leghe             integer     NOT NULL,
    n_partite           integer     NOT NULL,
    watermark_event_id  bigint      NOT NULL DEFAULT 0,  -- ultimo match_events.id letto
    payload             jsonb       NOT NULL,            -- atlante completo (formato v1/v2)
    created_at          timestamptz NOT NULL DEFAULT now()
);

-- il sync dei bot chiede solo "qual e' l'ultima versione?": indice dedicato
CREATE INDEX IF NOT EXISTS hazard_atlas_generated_at_idx
    ON public.hazard_atlas (generated_at DESC);

COMMENT ON TABLE public.hazard_atlas IS
    'Atlante Hazard: versioni assemblate (le ultime 7), lette dai bot via hazard_atlas_sync.py';

ALTER TABLE public.hazard_atlas_leghe ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hazard_atlas       ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.hazard_atlas_leghe FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.hazard_atlas       FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.hazard_atlas_leghe TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.hazard_atlas       TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.hazard_atlas_id_seq TO service_role;

COMMIT;

-- Verifica (sola lettura) dopo l'applicazione:
--   SELECT relname, relrowsecurity FROM pg_class
--    WHERE relname IN ('hazard_atlas', 'hazard_atlas_leghe');
--   SELECT grantee, privilege_type FROM information_schema.role_table_grants
--    WHERE table_name IN ('hazard_atlas', 'hazard_atlas_leghe') ORDER BY 1, 2;
-- Rollback:
--   DROP TABLE IF EXISTS public.hazard_atlas; DROP TABLE IF EXISTS public.hazard_atlas_leghe;
