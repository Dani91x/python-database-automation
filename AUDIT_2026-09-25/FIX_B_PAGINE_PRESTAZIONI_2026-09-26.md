# FIX-B — prestazioni e coerenza pagine (KO 2, 3, 6, 7, 9, 11 + dato sporco) — 26/09/2026

Delegato Opus (sessione B, coordinatore admin-9d), worktree `agent-a9033546b000463cd` su `498ba07`.
**Nessun commit. Nessuna scrittura sul DB vero** (solo SELECT/EXPLAIN via Supabase MCP `execute_sql`,
funzioni STABLE). Nessun riavvio dell'app. Nessun file fuori perimetro toccato. Patch completa:
`AUDIT_2026-09-25/fix_b.patch` (file nuovi inclusi con `git add -N`).

## 0. Esito per voce

| voce | esito | test RED→GREEN | falsificazione |
|---|---|---|---|
| KO2 Analytics (RPC + UI timeout≠vuoto) | **FATTO** (migrazione da applicare) | banco PGlite 701/701; vitest Analytics 4, Decisioni 3, erroreRpc 6 | 9 mutazioni SQL tutte ROSSE; 2 mutazioni UI ROSSE |
| KO3 Studio Ritardi / Stagioni | **FATTO** (migrazione da applicare) | banco PGlite (264 confronti ritardi identici); vitest Ritardi 3, Frequenze 2 | mutazione `distrib` ROSSA (176 KO) |
| KO6 Direzione quota | **FATTO** (solo frontend) | vitest Direzione quota 5 (+ eta 4 invariati) | mutazione ROSSA |
| KO7 ML un verdetto | **FATTO** | vitest ML 2 | mutazione ROSSA |
| KO9 TacticAI esito reale | **FATTO** | pytest 5 (+ test_serving 4, resilienza backfill 68 invariati) | 2 mutazioni ROSSE |
| KO11 rese | **FATTO** | vitest componenti 6 + rese 9 | 2 mutazioni ROSSE |
| Dato sporco kickoff | **FATTO**: SQL proposto NON eseguito + causa a monte corretta (2 scrittori) | pytest 4 + 3 (+ pipeline 68 invariati) | 2 mutazioni ROSSE |

RED dimostrato con il codice di PRIMA (versione HEAD rimessa per un attimo e ripristinata byte-identica, hash
SHA256 uguale): `fix_b_pagine/rosso_frontend.txt` (Analytics 3 rossi, Decisioni 2, ML 2, Direzione 2,
Frequenze 2), Ritardi 3 rossi, KO11 3 rossi, pytest KO9 4 rossi, merger 2 rossi, populator 2 rossi.
Falsificazioni: `fix_b_pagine/falsificazione_banco_sql.txt`, `fix_b_pagine/falsificazione_test.txt`
(ogni mutazione → ROSSO, «ripristino byte-identico: True»). `npx tsc -p tsconfig.app.json --noEmit`: 0 errori.

## 1. KO2 — Analytics › Performance Motori e Decisioni

**Causa (misurata).** Istanza piccola (shared_buffers 256 MB, effective_cache_size 768 MB) e tabelle grandi:
ogni apertura della pagina rileggeva da disco tutte le righe. `analytics_signals` ha il 31,7 % delle pagine
all-visible (2,36 M update da reset statistiche: il job riscrive le righe) → l'indice di copertura
`idx_as_eval_cover` non fa index-only scan. Il timeout del ruolo `authenticated` è 8 s (pg_roles), sotto
carico (fase 3) si superava.

**Tempi PRIMA** (DB vero, 26/09 ~17:50 locali, DB poco carico; «lette» = pagine da disco):

| RPC (chiamata della UI) | prima | fase 3 (sotto carico) |
|---|---|---|
| `get_analytics_filters()` | 4,72 s, 73.322 lette (2 scansioni intere di analytics_signals) | 37,8 s / timeout |
| `get_analytics(p_group_by=>'confidence')` (default pagina) | 3,98 s, 35.635 lette | timeout |
| `get_analytics_rows(p_conf_bin=>60)` (drill) | 2,42 s, 31.534 lette | non raggiunto |
| `get_decisions_filters()` | 3,34 s (5 scansioni) | timeout |
| `get_decisions(...,'logic')` | 1,90 s | timeout |

**Fix** (`migrations/analytics_rpc_veloci_2026-09-26.sql`, idempotente, ASCII):
- tabelle di RIEPILOGO `analytics_riepilogo_segnali` (livello G senza lega: **6.327 righe** misurate; livello
  L con lega: **195.783**), `analytics_riepilogo_decisioni`, `analytics_riepilogo_meta` (filtri pronti +
  orario). RLS senza policy + revoke: le leggono solo le RPC SECURITY DEFINER.
- `refresh_analytics_riepilogo()` (service_role, `statement_timeout 600s` come `refresh_analytics_bets`,
  una transazione, advisory lock, `delete ... where true` per pg-safeupdate) chiamata dal **job esistente**:
  nuovo passo «Riepilogo analytics» in `.github/workflows/predictions_results_backfill.yml` dopo
  build/merge/enrich/bets/pagella, incluso nel gate. Nessun processo nuovo.
- `get_analytics` / `get_decisions`: se i filtri attivi sono dimensioni del riepilogo leggono il riepilogo
  (stesse somme esatte, stessa formula di Wilson, `sum/sum(n)::numeric` = divisione di `avg()`), altrimenti
  (date, prob min/max, ritardo, frequenza, timing) il ramo diretto di prima invariato. Risposta con chiavi in
  più `fonte_dati` ('riepilogo'|'diretta') e `riepilogo_at`; ordine gruppi con spareggio `grp`.
- `get_analytics_filters` / `get_decisions_filters`: dal riepilogo; se assente, calcolo diretto (corpo
  identico spostato in `_analytics_filters_live` / `_decisions_filters_live`).
- `get_analytics_rows`: ogni ramo ordina/limita prima dell'unione + indici parziali `kickoff desc nulls last`.

**Equivalenza** (banco `fix_b_pagine/banco_pglite_analytics_veloci.mjs`, PostgreSQL 17 PGlite; oracolo = le
RPC di prima prese dai file che coincidono col DB vero, md5 dei corpi verificato su `pg_proc`): 23.719
segnali, 1.500 partite, 1.779 decisioni; 6 raggruppamenti × 12 filtri-riepilogo + 5 filtri-diretti,
8 raggruppamenti × 7 filtri decisioni, filtri, drill con offset: **701/701 identici** (testo jsonb). Anche:
riepilogo vecchio dichiarato dopo dati nuovi, refresh lo riallinea, meta assente → ramo diretto,
permessi (authenticated/anon non leggono il riepilogo, refresh solo service_role), migrazione applicata
due volte (idempotenza).

**Tempi DOPO**: le tabelle non esistono sul DB vero (nessuna scrittura) → **non misurabili end-to-end**.
Misurato in sola lettura: aggregazione che il refresh esegue (livello G) 1,91 s una volta al giorno; la
pagina leggerà 6.327 righe (vs 1.196.861) → stima < 0,1 s. Da rimisurare dopo l'applicazione (§8).

**UI** (`pages/Analytics.tsx`, `components/dashboard/DecisionsView.tsx`, `lib/erroreRpc.ts` nuovo): timeout/
errore mostrati come tali («i dati NON sono vuoti»), niente «Nessun segnale settlato / Nessuna decisione»
dopo un errore, niente risultato vecchio a video, errore dei MENU separato («Menu dei filtri non caricati»),
orario del riepilogo a video (ora di Roma).

## 2. KO3 — Studio Ritardi, ritardo della Direzione, Stagioni

**Causa (misurata).** (a) `matches` 2,3 GB mai vacuumata/analizzata dal reset (25 % pagine non all-visible):
lo storico-lega legge pagine sparse — `get_league_seasons(667)` 9.657 pagine lette (1,33 s a DB quieto,
timeout in fase 3). (b) In `get_market_delays` il blocco `distrib` faceva 2 sottoquery correlate per ogni
lunghezza k (O(K×N)): **667 `re 4-4` 'all' = 17,07 s a cache calda** (991.574 pagine temporanee),
`sge 3` 1,51 s (25.536 temporanee).
**Fix** (stessa migrazione): indice parziale di copertura `idx_matches_storico_lega_cover (league_id,
fixture_date, fixture_id) include (...) where status_short in ('FT','AET','PEN')` (stessa condizione delle
3 RPC); autovacuum di matches al 2 %; `distrib` = due GROUP BY + join (stessa firma, stesso output).
**Equivalenza**: DB vero `md5(get_market_delays(667,'sge','3','all'))` = md5 della SELECT nuova
(`20cf91f9…`); PGlite 22 mercati × 3 modi × 4 leghe = **264/264 identici**.
**DOPO** (SELECT equivalente sul DB vero, senza indice): `re 4-4` **17,07 s → 1,16 s**; `sge 3`
1,51 s → 1,39 s (temporanee 25.536 → 4.982). La parte I/O (21.782 pagine heap per 44.534 partite) la
toglie l'indice: **non misurabile senza crearlo** (stima ~550 pagine di indice).
**UI**: `RitardiPanel` e `MarketFrequencyPanel`: timeout dichiarato; «Stagioni non caricate: …» invece del
menu vuoto muto; «Nessuna stagione con partite concluse» se davvero vuoto.

## 3. KO6 — Direzione, fonte della quota (`lib/direzione.ts`, `DirezioneDashboard.tsx`)
`quotaDirezione()`: quota Betfair back migliore della direzione (`get_betfair_direction_odds`) se c'è →
etichetta «Betfair», giudizio di valore; altrimenti la quota di `get_direction` → «quota book», **mai
«valore»**. Regola di valore invariata (banda bassa > 1/quota), cambiata solo la fonte. Caso del referto:
Under 3.5 ora 1.42 Betfair (non 1.36 book). **Non toccata** `get_direction`: sul DB vero il corpo differisce
dal file `migrations/get_direction_rpc.sql` (stessa lunghezza 11.022, md5 `a22eccf8…` vs `67a70e80…`):
la quota di `get_direction` (coalesce odds_betfair, odds_book) resta senza fonte e, nei rari giorni con
`odds_betfair` valorizzata, senza quota Betfair viva viene etichettata «quota book» (prudente).

## 4. KO7 — ML un solo verdetto (`lib/fixtureModels.ts`, `MLPanel.tsx`)
Verità = `targets` (probabilità FINALI calibrate dell'ensemble, le stesse dei segnali:
`Ai Engine/ai_engine/predict_fixture.py` `"targets": results`); `ensemble_agreement` = classi votate dai
4 modelli base NON calibrati (`ensemble_trainer.get_ensemble_agreement`). Il riquadro ora è «Accordo con la
Previsione: N/4 modelli» + voti grezzi etichettati come tali; se la maggioranza grezza diverge c'è una nota
(non un secondo verdetto). Caso A `target_btts`: Previsione «No / Under» 52 %, accordo **1/4**.

## 5. KO9 — TacticAI esito reale (`tactical_engine/serving.py`, `Prediction/today_predictions_backfill.py`)
`run_esiti_reali(target_date)`: stesso job giornaliero, dopo il motore, try separato non-fatale. Partite
finite di [giorno−3, giorno+1): scrive `actual {home_goals, away_goals, outcome 1|X|2}` e
`predicted_correct_1x2` (forma di `generate_predictions.py`) solo se `actual` è NULL e solo la colonna
`tactical_engine_json`. Esito a 90': `fulltime_*`, `goals_*` solo se FT; AET/PEN senza fulltime → non scritto.
`serving.py:187-188` (`_build_payload`) resta `actual: None` per le partite non giocate (corretto).

## 6. KO11 — rese (`lib/rese.ts` nuovo)
Gol previsti NULL → «—» (`PredictionsCard`); `played=0` → «—» invece di NaN (`Last5Card`); minuti NULL =
barra assente, tutti NULL → «Dato per minuto assente» (`GoalsTabs`); date Studio Ritardi gg/mm/aaaa di Roma;
lista del giorno: partite del giorno dopo (ora di Roma) etichettate «27/09 00:00» (`MatchesList`).
**Non cambiato** (decisione dell'utente): il limite inferiore della lista resta `T00:00:00Z`
(`MatchesList.tsx:145`): le partite 00:00–02:00 ora di Roma di oggi sono escluse come prima.

## 7. Dato sporco `analytics_signals.kickoff`
Misura (sola lettura, 60 gg, confronto con `matches.fixture_date`): **255 partite / 14.034 righe**
(90 settled nel futuro), `analytics_decisions` 511 righe. Due cause:
1. `merge_engine_signals.py:155,193` copiava `es["kickoff"]` (istantanea all'emissione,
   `migrations/backfill_engine_signals.py:184`) sopra il kickoff del populator (1499655: 26/09 20:00Z
   invece di 25/09 23:00Z).
2. `build_analytics_signals.py:237` usava `fixture_predictions.fixture_date` = data PROGRAMMATA, che non
   segue i rinvii (13.531 delle 14.034 righe; es. 1506528 fp 11/09, matches 13/09 FT).
Fix a monte: entrambi prendono `matches.fixture_date` (già letta per il settlement), ripiego sulla propria
fonte se la partita manca. SQL diagnostico + correzione in
`migrations/analytics_signals_kickoff_pulizia_2026-09-26.sql` (**NON eseguito**, correzione commentata,
in transazione con verifica). Reperto aperto: `fixture_predictions.fixture_date` non si aggiorna sui rinvii
(chi la scrive: `Prediction/today_predictions_backfill.py`, fuori da questo fix).

## 8. Cosa deve fare l'utente (in ordine)
1. SQL Editor: `migrations/analytics_rpc_veloci_2026-09-26.sql` (minuti: 3 indici, uno su `matches` 1,5 M
   righe che blocca le scritture su matches durante la creazione, + primo riempimento del riepilogo).
   Farlo fuori dall'orario del job (03:23 UTC) e dei bot.
2. Fuori transazione: `VACUUM (ANALYZE) public.matches;` poi `VACUUM (ANALYZE) public.analytics_signals;`.
3. Rimisurare (come service role, sola lettura): `explain (analyze, buffers) select get_analytics_filters();`,
   `get_analytics(p_group_by=>'confidence')`, `get_decisions_filters()`, `get_league_seasons(667)`,
   `get_market_delays(667,'re','4-4','all',null,null)` — obiettivo < 4 s.
4. Dopo il deploy del codice (merge/build): `analytics_signals_kickoff_pulizia_2026-09-26.sql` (diagnosi →
   correzione in transazione) e `select public.refresh_analytics_riepilogo();`.
5. `npm run build` del frontend (non eseguito qui). Il job del giorno dopo chiama da solo il refresh e gli
   esiti TacticAI. **Se la migrazione non è applicata** il passo «Riepilogo analytics» del job fallisce
   (RPC assente) e il gate rende il run rosso: applicarla prima del run successivo.

## 9. Cosa NON ho potuto verificare
- Tempi DOPO reali (tabelle/indici non creati: nessuna scrittura). Misurate solo le SELECT equivalenti.
- Che `set statement_timeout = '600s'` sulla funzione valga via PostgREST (precedente del repo:
  `refresh_analytics_bets`) e che il gateway Supabase non tagli il `curl` prima della fine del refresh.
- Durata/ingombro reale della creazione di `idx_matches_storico_lega_cover` (stima ~150 MB).
- `MatchesList` (etichetta orario) coperto solo dal test della funzione `orarioPartita`, non da un test
  del componente (che legge Supabase).
- Il banco `certification/sessB` non è stato rilanciato (per ordine: legge il DB vero).
- La scelta `matches.fixture_date` come verità dei kickoff è verificata su 7 casi a campione, non su tutte
  le 255 partite.

## 10. File toccati (esatti)
Modificati: `.github/workflows/predictions_results_backfill.yml`, `Prediction/today_predictions_backfill.py`,
`build_analytics_signals.py`, `merge_engine_signals.py`, `tactical_engine/serving.py`,
`frontend/src/pages/Analytics.tsx`, `frontend/src/lib/{analytics,direzione,fixtureModels}.ts`,
`frontend/src/components/dashboard/{DecisionsView,DirezioneDashboard,GoalsTabs,Last5Card,MLPanel,MarketFrequencyPanel,MatchesList,PredictionsCard,RitardiPanel}.tsx`.
Nuovi: `migrations/analytics_rpc_veloci_2026-09-26.sql`, `migrations/analytics_signals_kickoff_pulizia_2026-09-26.sql`,
`frontend/src/lib/{erroreRpc,rese}.ts` (+ `.test.ts`), `frontend/src/pages/Analytics.errori.test.tsx`,
`frontend/src/components/dashboard/{DecisionsView.errori,DirezioneDashboard.quota,MLPanel.verdetto,MarketFrequencyPanel.fixb,RitardiPanel.fixb,rese.KO11}.test.tsx`,
`tactical_engine/tests/test_serving_esito_reale_2026_09_26.py`, `test_merge_engine_signals_kickoff_2026_09_26.py`,
`test_build_analytics_signals_kickoff_2026_09_26.py`, questo referto, `AUDIT_2026-09-25/fix_b.patch`,
`AUDIT_2026-09-25/fix_b_pagine/` (banco PGlite, sonde, script RED/falsificazione, evidenze).
Junction create nel worktree (mancavano): `.venv`, `frontend/node_modules` → togliere con `cmd /c rmdir`.
