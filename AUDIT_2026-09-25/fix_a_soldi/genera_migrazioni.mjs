// FIX-A (26/09/2026) - GENERA le tre migrazioni dai corpi VIVI.
//
// Ogni funzione nuova nasce dal file di migrazione il cui corpo coincide
// BYTE PER BYTE (md5 senza \r) con quello applicato sul DB (verificato in sola
// lettura su pg_proc, vedi referto), con sostituzioni PUNTUALI: ogni
// sostituzione deve trovare il suo testo ESATTAMENTE una volta, altrimenti lo
// script si ferma. Cosi' il diff fra vivo e nuovo e' solo quello dichiarato.
//
// Uso (dalla radice del repo): node AUDIT_2026-09-25/fix_a_soldi/genera_migrazioni.mjs
import { readFileSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const leggi = (p) => readFileSync(join(REPO, p), 'utf8').replace(/\r/g, '');
const tra = (src, da, a) => {
  const i = src.indexOf(da);
  const j = src.indexOf(a, i);
  if (i < 0 || j < 0) throw new Error(`segmento non trovato: ${da.slice(0, 60)}`);
  if (src.indexOf(da, i + 1) >= 0) throw new Error(`segmento NON unico: ${da.slice(0, 60)}`);
  return src.slice(i, j + a.length);
};
const sost = (src, vecchio, nuovo) => {
  const n = src.split(vecchio).length - 1;
  if (n !== 1) throw new Error(`sostituzione trovata ${n} volte (attesa 1): ${vecchio.slice(0, 80)}`);
  return src.replace(vecchio, nuovo);
};

// ---------------------------------------------------------------------------
// A. trading_daily_history: una posizione chiusa a ZERO non e' ne' V ne' P
// ---------------------------------------------------------------------------
{
  const src = leggi('migrations/mike_history_v2.sql');
  let f = tra(src, 'CREATE OR REPLACE FUNCTION public.trading_daily_history(',
    'GRANT EXECUTE ON FUNCTION public.trading_daily_history(text,text,text,text,date,date,numeric,text) TO service_role;');
  f = sost(f,
    "CASE WHEN total_pnl > 0 THEN 'won' WHEN total_pnl < 0 THEN 'lost' ELSE raw_status END AS status",
    "CASE WHEN total_pnl > 0 THEN 'won' WHEN total_pnl < 0 THEN 'lost'\n"
    + "                        -- FIX-A 26/09: a ZERO (scratch) non e' ne' V ne' P; void e ignoto restano com'erano\n"
    + "                        WHEN raw_status = 'void' OR total_pnl IS NULL THEN raw_status\n"
    + "                        ELSE 'scratch' END AS status");
  const testa = `-- ============================================================================
-- STORICO: una posizione chiusa a ZERO non e' una vittoria (FIX-A, 26/09/2026)
-- ============================================================================
-- REPERTO (E2E fase 3 sessione B, U0541): lo Storico di Mike diceva «150V · 91P
-- · 1 void, win rate 62,2 %» mentre il tooltip dichiara «V = posizioni con P&L
-- totale POSITIVO, P = negativo». Le posizioni 527 e 4762 (Mike, paper) hanno
-- P&L totale 0,00 ma riga d'apertura 'won': \`trading_daily_history\` le
-- classificava col segno del P&L e, a ZERO, ricadeva sullo stato GREZZO
-- dell'apertura ('won'). Con la definizione dichiarata: 148V / 91P = 61,9 %.
--
-- CORREZIONE: a P&L totale zero l'esito e' 'scratch' (conta fra le regolate,
-- non fra V/P ne' fra i void). Void e P&L ignoto restano come prima.
-- Tocca TUTTI gli storici che usano il motore comune (Omega, Safe, Mike):
-- stessa definizione, stesso tooltip, in ogni pagina.
--
-- BASE: il corpo e' quello VIVO (md5 senza \\r = e58a42c89c799e25286a65421a63fdff,
-- identico a migrations/mike_history_v2.sql), generato da
-- AUDIT_2026-09-25/fix_a_soldi/genera_migrazioni.mjs con UNA sola sostituzione.
-- IDEMPOTENTE (CREATE OR REPLACE a firma invariata). Nessuna modifica ai dati.
--
-- VERIFICA dopo l'applicazione (Mike paper 01-26/09): won=148, lost=91
--   SELECT sum((r->>'won')::int) v, sum((r->>'lost')::int) p
--     FROM jsonb_array_elements(public.get_mike_daily('2026-09-01','2026-09-26','paper')) r;
-- ============================================================================

`;
  writeFileSync(join(REPO, 'migrations/storico_esito_a_zero_2026-09-26.sql'), testa + f + '\n');
}

// ---------------------------------------------------------------------------
// B. Omega: aggregati PER MODALITA' e partite DISTINTE
// ---------------------------------------------------------------------------
{
  const src = leggi('migrations/omega_chiuso_dall_utente_2026-09-16.sql');
  let f = tra(src, 'CREATE OR REPLACE FUNCTION public.omega_aggregates_sql(p_solo_auto boolean)',
    'GRANT EXECUTE ON FUNCTION public.omega_aggregates_sql(boolean) TO service_role;');
  f = sost(f, 'CREATE OR REPLACE FUNCTION public.omega_aggregates_sql(p_solo_auto boolean)',
    'CREATE OR REPLACE FUNCTION public.omega_aggregates_sql(p_solo_auto boolean, p_mode text)');
  f = sost(f,
    "SELECT (date_trunc('day', now() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome') AS v_day\n",
    "SELECT (date_trunc('day', now() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome') AS v_day,\n"
    + "               -- FIX-A 26/09: NULL/'' = tutte le modalita' (comportamento storico)\n"
    + "               nullif(lower(btrim(coalesce(p_mode, ''))), '') AS v_mode\n");
  f = sost(f,
    "         WHERE NOT p_solo_auto\n            OR coalesce(p.origin, o.origin, 'auto') <> 'manual'\n",
    "         WHERE (NOT p_solo_auto\n            OR coalesce(p.origin, o.origin, 'auto') <> 'manual')\n"
    + "           -- FIX-A 26/09: la modalita' e' quella della POSIZIONE (apertura)\n"
    + "           AND ((SELECT v_mode FROM d) IS NULL\n"
    + "                OR coalesce(p.mode, o.mode) = (SELECT v_mode FROM d))\n");
  f = sost(f,
    "        'matches_traded_today', count(*) FILTER",
    "        -- FIX-A 26/09 (U0426): PARTITE distinte con almeno una posizione piazzata\n"
    + "        -- (matches_traded conta le APERTURE, cioe' le gambe: resta per il servizio)\n"
    + "        'events_traded',   count(DISTINCT t.event_id) FILTER (WHERE t.closes_trade_id IS NULL\n"
    + "                               AND (t.status IN ('open','hedged','won','lost','void') OR (t.status = 'pending' AND t.is_placed))),\n"
    + "        'mode',            d.v_mode,\n"
    + "        'matches_traded_today', count(*) FILTER");
  f = sost(f, '     GROUP BY d.v_day;', '     GROUP BY d.v_day, d.v_mode;');
  f = sost(f, 'REVOKE ALL ON FUNCTION public.omega_aggregates_sql(boolean) FROM public, anon, authenticated;',
    'REVOKE ALL ON FUNCTION public.omega_aggregates_sql(boolean, text) FROM public, anon, authenticated;');
  f = sost(f, 'GRANT EXECUTE ON FUNCTION public.omega_aggregates_sql(boolean) TO service_role;',
    'GRANT EXECUTE ON FUNCTION public.omega_aggregates_sql(boolean, text) TO service_role;');

  const delega = `
-- l'overload del SERVIZIO (boolean) resta la stessa cosa: UN corpo solo, tutte
-- le modalita'. In uscita due chiavi IN PIU' (events_traded, mode=null), nessuna
-- tolta ne' cambiata.
CREATE OR REPLACE FUNCTION public.omega_aggregates_sql(p_solo_auto boolean)
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT public.omega_aggregates_sql(p_solo_auto, NULL::text);
$$;
REVOKE ALL ON FUNCTION public.omega_aggregates_sql(boolean) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_aggregates_sql(boolean) TO service_role;
`;

  const src5 = leggi('migrations/omega_models_v5.sql');
  let g = tra(src5, 'CREATE OR REPLACE FUNCTION public.get_omega_state(',
    'GRANT EXECUTE ON FUNCTION public.get_omega_state(integer) TO authenticated, service_role;');
  g = sost(g, '    v_agg  jsonb;\n', '    v_agg  jsonb;\n    v_by   jsonb;\n');
  g = sost(g, "    v_agg := coalesce(public.omega_aggregates_sql(), '{}'::jsonb);\n",
    "    v_agg := coalesce(public.omega_aggregates_sql(), '{}'::jsonb);\n"
    + "    -- FIX-A 26/09: paper e live SEPARATI (la pagina mostra la modalita' del bot\n"
    + "    -- e, a parte, l'altra se ha qualcosa: mai una somma sotto un'etichetta)\n"
    + "    v_by := jsonb_build_object(\n"
    + "        'paper', coalesce(public.omega_aggregates_sql(false, 'paper'), '{}'::jsonb),\n"
    + "        'live',  coalesce(public.omega_aggregates_sql(false, 'live'),  '{}'::jsonb));\n");
  g = sost(g, "'aggregates', v_agg, ", "'aggregates', v_agg, 'aggregates_by_mode', v_by, ");

  const testa = `-- ============================================================================
-- OMEGA: aggregati PER MODALITA' e partite DISTINTE (FIX-A, 26/09/2026)
-- ============================================================================
-- REPERTI (E2E fase 3 sessione B):
--   * U0419 latente: \`omega_aggregates_sql\` non filtra per \`mode\`: il giorno in
--     cui esistera' una riga live, P&L, liability e contatori della pagina Omega
--     sommeranno euro veri e simulati sotto l'etichetta della modalita' del bot.
--   * U0426: «storico 109 partite» = \`matches_traded\`, che conta le APERTURE
--     (gambe 1T/2T), non le partite (100 distinte).
--
-- CORREZIONE (solo lettura, nessun dato toccato):
--   1. omega_aggregates_sql(boolean, text) - lo STESSO corpo vivo con il filtro
--      della modalita' della POSIZIONE e due chiavi nuove: events_traded (partite
--      distinte) e mode (filtro applicato).
--   2. omega_aggregates_sql(boolean) - quella del SERVIZIO - delega alla nuova
--      con NULL: stessi numeri di prima + le due chiavi nuove (additive).
--   3. get_omega_state(integer) - aggiunge \`aggregates_by_mode\` {paper, live}.
--      \`aggregates\` resta com'era (tutte le modalita') per chi lo legge oggi.
--
-- BASE: corpi VIVI (md5 senza \\r): omega_aggregates_sql(boolean)
-- 6c00a7346cec3efe9e638919b8d6fc2a = migrations/omega_chiuso_dall_utente_2026-09-16.sql;
-- get_omega_state(integer) 5027acf45a32f3814edbd941a61d3cf2 = migrations/omega_models_v5.sql.
-- Generato da AUDIT_2026-09-25/fix_a_soldi/genera_migrazioni.mjs.
-- IDEMPOTENTE: CREATE OR REPLACE; la firma (boolean, text) e' un overload NUOVO
-- senza default (nessuna ambiguita' con (boolean) ne' con ()).
--
-- VERIFICA dopo l'applicazione:
--   SELECT public.get_omega_state()->'aggregates_by_mode'->'paper'->>'events_traded';
--   SELECT (public.get_omega_aggregates() ? 'auto');   -- il servizio: invariato
-- ============================================================================

`;
  writeFileSync(join(REPO, 'migrations/omega_state_per_modalita_2026-09-26.sql'),
    testa + f + '\n' + delega + '\n' + g + '\n');
}

// ---------------------------------------------------------------------------
// C. Live P&L: una posizione su un mercato GIA' REGOLATO non e' aperta
// ---------------------------------------------------------------------------
{
  const src = leggi('migrations/betfair_live_pnl_journal.sql');
  let f = tra(src, 'CREATE OR REPLACE FUNCTION public.get_live_positions_all()', '$$;');
  f = sost(f,
    '      FROM (SELECT * FROM public.betfair_live_positions ORDER BY updated_at DESC LIMIT 2000) p;',
    '      -- FIX-A 26/09: fuori le posizioni di un mercato gia\' REGOLATO nella STESSA\n'
    + '      -- modalita\' (betfair_live_settled): il runner non le cancella alla\n'
    + '      -- regolazione e la pagina le mostrava come aperte, con rischio.\n'
    + '      FROM (SELECT z.* FROM public.betfair_live_positions z\n'
    + '             WHERE NOT EXISTS (SELECT 1 FROM public.betfair_live_settled s\n'
    + '                                WHERE s.market_id = z.market_id AND s.mode = z.mode)\n'
    + '             ORDER BY z.updated_at DESC LIMIT 2000) p;');
  const testa = `-- ============================================================================
-- LIVE P&L: niente posizioni FANTASMA (FIX-A, 26/09/2026)
-- ============================================================================
-- REPERTO (E2E fase 3 sessione B, U0275): /live-pnl mostrava «1 posizioni aperte ·
-- rischio 4,40 €» per la riga betfair_live_positions 14265 (mode live, evento
-- 35797769, mercato 1.259819675, ultimo aggiornamento 10/07/2026 19:29Z) su un
-- mercato REGOLATO il 10/07 19:31Z (betfair_live_settled id 18, live, +105).
-- Il runner scrive le posizioni ma non le toglie alla regolazione.
--
-- CORREZIONE alla SORGENTE della pagina: get_live_positions_all() esclude le
-- righe il cui mercato ha gia' una regolazione nella STESSA modalita'. Nessun
-- dato toccato: la pulizia della riga 14265 e' una PROPOSTA separata
-- (migrations/PROPOSTA_pulizia_posizione_fantasma_14265_2026-09-26.sql), non
-- necessaria per la pagina.
--
-- BASE: corpo VIVO (md5 senza \\r 6a4f83dfdffbc98b540f7263e3b086b1 =
-- migrations/betfair_live_pnl_journal.sql). Generato da
-- AUDIT_2026-09-25/fix_a_soldi/genera_migrazioni.mjs. IDEMPOTENTE.
--
-- VERIFICA: SELECT jsonb_array_length(public.get_live_positions_all()->'rows');
--   (26/09: 3 invece di 4; la riga 14265 non c'e' piu')
-- ============================================================================

`;
  const grant = `
REVOKE ALL    ON FUNCTION public.get_live_positions_all() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_live_positions_all() TO authenticated, service_role;
`;
  writeFileSync(join(REPO, 'migrations/live_positions_senza_mercati_regolati_2026-09-26.sql'),
    testa + f + '\n' + grant);
}
console.log('migrazioni generate');
