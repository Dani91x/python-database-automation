-- ============================================================================
-- analytics_signals_kickoff_pulizia_2026-09-26.sql   *** PROPOSTA: NON ESEGUITA ***
-- ============================================================================
-- DATO SPORCO (referto AUDIT_2026-09-25/E2E_FASE3_PAGINE_SESSIONE_B_2026-09-26.md par.10):
-- righe di analytics_signals (e analytics_decisions) con `kickoff` diverso dalla data in
-- cui la partita si e' giocata; alcune `settled=true` con kickoff FUTURO.
--
-- MISURATO sul DB vero il 26/09 (sola lettura, ultimi 60 giorni, confronto con matches):
--   analytics_signals   : 255 partite / 14.034 righe con kickoff <> matches.fixture_date,
--                         90 righe settled con kickoff > now()
--     di cui 13.531 righe dove ANCHE fixture_predictions.fixture_date <> matches.fixture_date
--     (partite RINVIATE: fixture_predictions tiene la data programmata, es. 1506528
--      fp 11/09 17:30Z, matches 13/09 17:30Z FT)
--   analytics_decisions : 511 righe con kickoff <> matches.fixture_date
--   (il referto di fase 3 contava 25 partite / 546 righe confrontando con fixture_predictions)
--
-- CAUSA NEL CODICE (corretta a monte in questo stesso lavoro, file NON ancora in produzione):
--   merge_engine_signals.py:_build  "kickoff": es.get("kickoff")  (ctx riga 155 e
--       prediction riga 193 prima del fix): istantanea di engine_signals presa all'emissione
--       (migrations/backfill_engine_signals.py:184 kickoff=m.get("fixture_date") di allora);
--       se la partita viene spostata, l'upsert per signal_uid SOVRASCRIVE il kickoff del
--       populator con la data vecchia (1499655: 26/09 20:00Z invece di 25/09 23:00Z).
--   build_analytics_signals.py:_rows_for_fixture  "kickoff": fp.get("fixture_date")
--       (riga 237 prima del fix): data PROGRAMMATA di fixture_predictions, non segue i rinvii.
--   FIX: entrambi prendono matches.fixture_date (la riga del settlement, gia' letta) e
--   ripiegano sulla propria fonte solo se la partita non c'e'.
--
-- ORDINE: (1) applicare prima i fix del codice (altrimenti il job successivo rimette le
-- date vecchie); (2) eseguire la DIAGNOSI; (3) la CORREZIONE in una transazione, con il
-- controllo dei conteggi; (4) far girare il job (refresh del riepilogo analytics).
-- Nessuna riga cancellata: si corregge solo `kickoff`. Le righe senza partita in matches
-- non si toccano.
-- ============================================================================

-- ---------------------------------------------------------------- (2) DIAGNOSI
select 'analytics_signals' as tabella,
       count(distinct s.fixture_id) as partite, count(*) as righe,
       count(*) filter (where s.settled and s.kickoff > now()) as settled_nel_futuro,
       count(*) filter (where fp.fixture_date is distinct from m.fixture_date) as rinviate_fp_vecchia
from analytics_signals s
join matches m on m.fixture_id = s.fixture_id
left join fixture_predictions fp on fp.fixture_id = s.fixture_id
where m.fixture_date is not null and s.kickoff is distinct from m.fixture_date
union all
select 'analytics_decisions', count(distinct d.fixture_id), count(*),
       count(*) filter (where d.settled and d.kickoff > now()), null
from analytics_decisions d
join matches m on m.fixture_id = d.fixture_id
where m.fixture_date is not null and d.kickoff is distinct from m.fixture_date;

-- esempi (le 20 partite con piu' righe)
select s.fixture_id, m.status_short, min(s.kickoff) kickoff_min, max(s.kickoff) kickoff_max,
       m.fixture_date as data_giocata, fp.fixture_date as data_programmata, count(*) righe
from analytics_signals s
join matches m on m.fixture_id = s.fixture_id
left join fixture_predictions fp on fp.fixture_id = s.fixture_id
where m.fixture_date is not null and s.kickoff is distinct from m.fixture_date
group by 1, 2, 5, 6 order by righe desc limit 20;

-- ---------------------------------------------------------------- (3) CORREZIONE
-- Da eseguire UNA volta, in transazione. Controllare che i conteggi aggiornati coincidano
-- con la diagnosi prima del COMMIT (altrimenti ROLLBACK).
-- NB: analytics_signals ha ~1 M di righe; l'UPDATE tocca solo quelle sbagliate (join per
-- fixture_id indicizzato). Farlo fuori dall'orario del job (03:23 UTC) e dei bot.
--
-- begin;
-- set local statement_timeout = '15min';
-- update analytics_signals s
--    set kickoff = m.fixture_date, updated_at = now()
--   from matches m
--  where m.fixture_id = s.fixture_id
--    and m.fixture_date is not null
--    and s.kickoff is distinct from m.fixture_date;
-- update analytics_decisions d
--    set kickoff = m.fixture_date, updated_at = now()
--   from matches m
--  where m.fixture_id = d.fixture_id
--    and m.fixture_date is not null
--    and d.kickoff is distinct from m.fixture_date;
-- -- verifica: deve dare 0 e 0
-- select (select count(*) from analytics_signals s join matches m on m.fixture_id = s.fixture_id
--          where m.fixture_date is not null and s.kickoff is distinct from m.fixture_date) as sig_residue,
--        (select count(*) from analytics_decisions d join matches m on m.fixture_id = d.fixture_id
--          where m.fixture_date is not null and d.kickoff is distinct from m.fixture_date) as dec_residue;
-- commit;   -- oppure rollback;
--
-- (4) dopo: select public.refresh_analytics_riepilogo();  (se la migrazione
--     analytics_rpc_veloci_2026-09-26.sql e' applicata; altrimenti lo fa il job)
