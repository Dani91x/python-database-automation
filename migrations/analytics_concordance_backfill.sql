-- ============================================================================
-- BACKFILL CONCORDANZA STORICA — n_engines_agree / consensus_prob (2026-06-22)
-- ============================================================================
-- CONCORDANZA = stessa partita + stesso mercato, più motori che indicano la
-- STESSA DIREZIONE. Replica la semantica TOP-PICK del populator forward:
--   • il "pick" di ogni motore su (fixture, market) = la selezione con prob MAX
--     (un motore può avere righe su più selezioni — es. No PLACED + Yes REJECTED —
--      ma la sua direzione è quella a prob più alta);
--   • n_engines_agree(selection) = quanti motori hanno QUELLA selezione come pick;
--   • consensus_prob = media delle prob dei motori concordi;
--   • una selezione che non è il pick di nessun motore → n_engines_agree = 0.
--
-- (Coerente col forward. Per lo storico l'ML era forward-only: il pick è ricavato
--  dalle righe-segnale disponibili in engine_signals — migliore approssimazione.)
--
-- SICUREZZA: tocca SOLO le righe storiche (n_engines_agree IS NULL) → NON
-- sovrascrive mai il top-pick nativo che il populator scrive sul forward.
-- Idempotente. Aggiornamento per chiave primaria s.id → preciso.
-- ============================================================================

with tops as (
    -- pick di ogni motore: la selezione a prob MAX per (fixture, market, engine)
    select distinct on (fixture_id, market, engine)
        fixture_id, market, engine, selection, prob
    from analytics_signals
    where prob is not null
    order by fixture_id, market, engine, prob desc, selection
),
agg as (
    -- per (fixture, market, selection): quanti motori la pickano + prob media
    select fixture_id, market, selection,
           count(*)::int                as n_agree,
           round(avg(prob)::numeric, 4) as cons_prob
    from tops
    group by fixture_id, market, selection
),
targets as (
    -- ogni riga storica con la sua concordanza (0 se non è il pick di nessuno)
    select s.id,
           coalesce(a.n_agree, 0) as n_agree,
           a.cons_prob
    from analytics_signals s
    left join agg a
      on a.fixture_id = s.fixture_id
     and a.market     = s.market
     and a.selection  = s.selection
    where s.n_engines_agree is null
      and s.prob is not null            -- NO_SIGNAL (prob null) resta NULL
)
update analytics_signals s
   set n_engines_agree = t.n_agree,
       consensus_prob  = t.cons_prob
  from targets t
 where s.id = t.id;
