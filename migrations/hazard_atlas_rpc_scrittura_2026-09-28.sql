-- =====================================================================
-- ATLANTE HAZARD: RPC dedicata per la scrittura della versione globale
-- (28/09/2026, R-28-2) - DA APPLICARE A CURA DELL'UTENTE
-- =====================================================================
-- Causa (referto AUDIT_2026-09-28/CANTIERE_F_HAZARD_ATLAS_500.md): la action
-- notturna dell'Atlante Hazard e' andata HTTP 500 (run 36390445058, 28/09
-- 07:13Z) sull'UNICA POST che scrive la riga globale hazard_atlas.payload.
-- Misure a DB (sola lettura):
--   * la riga manda un corpo TESTO JSON, non la dimensione compressa su
--     disco: id=2 (27/09, 188 leghe) = 14.465.171 byte; id=1 (26/09, 21
--     leghe) = 1.961.888 byte -> ~75 KB/lega in piu' (crescita marginale
--     reale, misurata dal coordinatore, non stimata);
--   * `matches` ha 1.244 league_id distinti: solo 185 sono nello stato di
--     hazard_atlas_leghe oggi -> il payload e' destinato a crescere ancora;
--   * pg_roles.rolconfig: authenticator ha statement_timeout=8s; la doc
--     Supabase (https://supabase.com/docs/guides/database/postgres/timeouts)
--     conferma "service_role: none (defaults to the authenticator role's 8s
--     timeout if unset)" -> le chiamate service_role di PostgREST ereditano
--     lo stesso limite di 8 s;
--   * error-code map di PostgREST (57* -> 500): uno statement_timeout
--     (57014) sul lato Postgres esce come HTTP 500 lato client, spiegando il
--     traceback della run fallita.
-- Con la sola POST diretta, quando la riga sara' abbastanza grande da non
-- stare mai sotto 8 s la scrittura fallira' SEMPRE, con qualunque numero di
-- ritentativi (codice gia' corretto in genera_atlante.py, ma i ritentativi
-- coprono solo il carico passeggero, non la dimensione strutturale).
--
-- Questa RPC alza il timeout SOLO per questa scrittura (pattern ufficiale
-- Supabase, "Function level": SET statement_timeout sulla funzione), senza
-- toccare il limite di tutto il progetto (niente ALTER ROLE: cambierebbe
-- l'8 s anche per Safe/Omega/Mike/UI, che devono restare veloci). Permesso
-- SOLO a service_role (stessa politica RLS/GRANT di hazard_atlas_2026-09-24).
--
-- genera_atlante.py (_Scrittore._scrivi_riga) chiama PRIMA questa RPC
-- (POST /rest/v1/rpc/hazard_atlas_salva_versione); se non esiste ancora
-- (42883/PGRST202 -> 404, migrazione non applicata) ripiega SUBITO sulla
-- POST diretta su hazard_atlas (stessi ritentativi di oggi): il codice puo'
-- andare su master PRIMA che questa migrazione sia applicata, senza run
-- rosse nel frattempo.
--
-- Timeout scelto: 120 s (ordine di grandezza sotto il timeout socket del
-- client, 300 s in genera_atlante.py; ben sopra i pochi secondi che la
-- scrittura richiede oggi anche sotto carico). Da alzare con
-- ALTER FUNCTION ... SET statement_timeout TO 'Xs' se il payload continua
-- a crescere (vedi proposta di ridurre cosa si scrive, par. 3 del referto: col
-- modo di default dell'atlante a domanda, hazard_atlas.payload non lo legge
-- nessuno oggi, vedi hazard_atlas_sync.py:85-96,129-135,188).
-- =====================================================================

BEGIN;

CREATE OR REPLACE FUNCTION public.hazard_atlas_salva_versione(
    p_generated_at       timestamptz,
    p_n_leghe            integer,
    p_n_partite          integer,
    p_watermark_event_id bigint,
    p_payload            jsonb
) RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET statement_timeout TO '120s'
AS $$
DECLARE
    v_id bigint;
BEGIN
    INSERT INTO public.hazard_atlas
        (generated_at, n_leghe, n_partite, watermark_event_id, payload)
    VALUES
        (p_generated_at, p_n_leghe, p_n_partite, p_watermark_event_id, p_payload)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION public.hazard_atlas_salva_versione(timestamptz, integer, integer, bigint, jsonb) IS
    'R-28-2: scrive la riga globale hazard_atlas con statement_timeout=120s dedicato '
    '(authenticator/service_role sono a 8s). Solo service_role. genera_atlante.py la usa '
    'con ripiego sulla POST diretta se non esiste ancora.';

REVOKE ALL ON FUNCTION public.hazard_atlas_salva_versione(timestamptz, integer, integer, bigint, jsonb)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hazard_atlas_salva_versione(timestamptz, integer, integer, bigint, jsonb)
    TO service_role;

COMMIT;

-- Dopo l'applicazione, PostgREST deve ricaricare lo schema per "vedere" la RPC:
NOTIFY pgrst, 'reload schema';

-- Verifica (sola lettura) dopo l'applicazione:
--   SELECT proname, prosecdef, proconfig FROM pg_proc
--    WHERE proname = 'hazard_atlas_salva_versione';           -- proconfig deve contenere statement_timeout=120s
--   SELECT grantee, privilege_type FROM information_schema.routine_privileges
--    WHERE routine_name = 'hazard_atlas_salva_versione';       -- solo service_role
-- Prova (sola lettura, non scrive): la action notturna la user'a' al prossimo
-- run; per una prova manuale sicura serve una chiamata scrivente (fuori dal
-- perimetro di questo delegato, vedi referto).
-- Rollback:
--   DROP FUNCTION IF EXISTS public.hazard_atlas_salva_versione(timestamptz, integer, integer, bigint, jsonb);
--   NOTIFY pgrst, 'reload schema';
