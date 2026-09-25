# AUDIT5 - TacticAI, paginazione, eta' dei dati, ritardo unico (25/09/2026)

Delegato Opus, worktree isolato su `origin/master` f015204. Perimetro: reperti R1, R2, R5, R7
di `AUDIT_2026-09-24/AUDIT_TAB_DASHBOARD_2026-09-24.md`. Niente commit. `Betfair/**`,
`controlroom/**`, `today_predictions_backfill.py`, workflow e migrazioni esistenti NON toccati.
DB di produzione MAI letto ne' scritto: pytest con `SUPABASE_URL=http://127.0.0.1:9`, vitest con
il client finto forzato da `src/test/setup.ts`, SQL provato su PostgreSQL in memoria (PGlite).

## Riepilogo

| Reperto | Prima | Dopo | Verifica |
|---|---|---|---|
| R1 | partite del giorno lette da `matches` (solo partite finite) -> 34/263 oggi | lette da `fixture_predictions` (tutte), solo UPDATE | pytest (a) + 2 mutanti rossi |
| R2 | storico senza ORDER BY ne' paginazione | keyset su `fixture_id` a pagine da 1000 + ordine (fixture_date, fixture_id) | pytest (b) + 3 mutanti rossi |
| R5 | nessuna tab dichiarava l'eta' | un componente `EtaDato` in Poisson, TacticAI, ML e Direzione; soglie rosse | vitest (c) + 3 mutanti rossi, PGlite |
| R7 | due calcoli diversi (tab = HT mancante 0-0; cruscotto = formule proprie nel browser) | UNA RPC, UNA regola (HT mancante escluso), il cruscotto legge la RPC | PGlite (d) + 3 mutanti SQL rossi, vitest + 3 mutanti rossi |

---

## R1 - TacticAI legge le partite del giorno da `fixture_predictions`

**Prima** (`tactical_engine/serving.py:137-143` di f015204): `matches` filtrata per data e
`status_short NOT IN (FT,AET,PEN)`. `matches` contiene solo partite finite, quindi quasi sempre
0 partite e uscita silenziosa. Numeri del coordinatore: 34/263 oggi, 374/7.977 in 14 giorni (4,7 %).

**Dopo** (`serving.py`, `_load_today` righe 134-145, chiamata a riga 191):
- fonte `fixture_predictions`, colonne `TODAY_COLS` (serving.py:50-58): fixture_id, league_id,
  league_name, season_year, fixture_date, home/away_team_id, home/away_team_name,
  result_status_short. La lettura e' paginata (vedi R2).
- **Filtro "non giocata" equivalente**. NB: in `fixture_predictions` la colonna `status` NON e'
  lo stato della partita: e' lo stato della PREDIZIONE API (`ok/empty/no_coverage/error`,
  `today_predictions_backfill.py:2482,2552,2606,2645`). Lo stato partita e' `result_status_short`,
  scritto a partita finita (`predictions_results_backfill.py:482`), NULL prima. Il filtro diventa
  `result_status_short NULL oppure NOT IN (FT,AET,PEN)`, applicato in Python come prima (un
  `not.in` di PostgREST scarterebbe le righe NULL, cioe' tutte le partite da giocare).
  Filtrare `status='ok'` sarebbe stato sbagliato: TacticAI non dipende dalla predizione API e le
  partite `no_coverage` restano predicibili.
- Scrittura: la riga esiste sempre (e' quella letta), quindi solo UPDATE di `tactical_engine_json`
  (serving.py:242-259). Ramo di esistenza e INSERT tolti; il riepilogo mantiene la chiave
  `inserted` (sempre 0) per non rompere `run_daily.py` e l'aggancio di `today_predictions_backfill.py`,
  che si limitano a stamparlo. Un UPDATE senza effetto resta contato come errore.
- Motore invariato: prior da `matches`, fit, payload identici. Due differenze nel payload, dichiarate:
  `league_name` ora e' valorizzato (prima NULL: `matches` non ha la colonna) e `status` e'
  `result_status_short` (NULL prima del fischio; prima era lo `status_short` di `matches`, es. `NS`).
  Nessun consumatore legge `status` (grep in `frontend/`, `Betfair/stream/db.py:210-251`,
  `build_analytics_signals.py:269`, `get_direction_rpc.sql:61`); il tipo TS e' ora `string | null`
  (`lib/tacticalEngine.ts`).

## R2 - `_load_prior` con ORDER BY totale e paginazione keyset

**Prima** (`serving.py:66-70`): una sola SELECT, niente ORDER BY: ordine arbitrario, e una
paginazione futura avrebbe saltato o duplicato righe. Il taglio a 1000 NON c'era (coordinatore:
max `training.n_matches` = 39.560, zero righe a 1000).

**Dopo**:
- `_leggi_keyset` (serving.py:84-105): per ogni pagina aggiunge `fixture_id > cursore`,
  `ORDER BY fixture_id`, `LIMIT 1000`; esce SOLO a pagina vuota (come `generate_dynamic_cal.py:103-138`):
  se il server tronca (max_rows) non si perde nulla. Usata anche per le partite del giorno (R1).
- **Chiave di paginazione: `fixture_id`, non `(fixture_date, fixture_id)`**. Motivo: `fixture_id` e'
  univoco (`fixtures_backfill.py:135` fa upsert `on_conflict="fixture_id"`), quindi l'ordine e'
  totale e il keyset esatto con un solo `gt`, lo stesso schema gia' in produzione in
  `generate_dynamic_cal.py`/`master_backtest.py`. Un keyset su chiave composta richiede in
  PostgREST un filtro `or=(fixture_date.gt.X,and(fixture_date.eq.X,fixture_id.gt.Y))` con timestamp
  da quotare, mai provato sul PostgREST vero: rischio senza beneficio. L'ordine cronologico
  `(fixture_date, fixture_id)` richiesto e' applicato subito dopo, in Python (serving.py:118-123),
  prima del fit.
- Stesso insieme di righe: stessi filtri di prima (league_id, finestra di 4 emivite).
- **Stessi numeri?** Il fit dipende dall'INSIEME delle partite (squadre indicizzate per id,
  `model.py:72-73`), ma l'ordine delle righe cambia l'ordine delle somme in virgola mobile e
  L-BFGS-B (ftol 1e-8) lo amplifica: **misurato** uno scarto di 1e-4 su una probabilita'
  arrotondata a 4 decimali (`away` 0.1983 -> 0.1982, test
  `test_fit_invariante_all_ordine_delle_righe_entro_la_tolleranza_dell_ottimizzatore`).
  Prima l'ordine era quello fisico della tabella, quindi lo stesso scarto era gia' possibile da
  un run all'altro; ora l'ordine e' fisso e il risultato si ripete identico. Sulle 33-34 partite
  che gia' calcolava ci si aspetta quindi lo stesso numero entro circa 1e-4 (NON verificato sul DB
  vero: query Q-R1c sotto).
- Costo (fino a ~40k righe per lega per run) invariato: ora sono 40 pagine invece di una risposta
  grande. Non ottimizzato di iniziativa (cambierebbe il modello o la finestra).

## R5 - eta' del dato materializzato in ogni tab

Un solo componente `frontend/src/components/dashboard/EtaDato.tsx` ("Etichetta: aggiornato al
gg/mm/aaaa hh:mm (N h fa)"), logica pura in `frontend/src/lib/etaDato.ts`.
Verde entro soglia, ROSSO oltre la soglia o se il dato manca/non e' una data valida (mai "fresco"
per difetto); un orario nel futuro vale eta' 0.

Soglie (etaDato.ts:13-15), motivate:
- previsioni per partita Poisson / TacticAI / ML (`generated_at`): **36 h** = la action gira una
  volta al giorno (02:18 UTC) + 12 h di margine per un run in ritardo; oltre, un run e' saltato.
- calibrazione Poisson settimanale (`poisson_calibration.generated_at`): **8 giorni** = cadenza del
  lunedi' + 1 giorno.
- pagella Direzione: notturna -> **36 h**.
- Il confine esatto (36 h, 8 g) e' ancora verde (test).

Dove:
- **Poisson** (`PoissonPanel.tsx`): previsione (36 h); se calibrato, data della tabella di
  calibrazione settimanale con la stessa catena del calibratore (lega, altrimenti globale
  `league_id=0`, `poisson_calibrator.py`) e la dicitura `(lega)`/`(globale)`, soglia 8 g; piu'
  `calibrated_at` (quando e' stata applicata alla partita) in grigio, informativo.
  NB: `calibrated_at` NON dice l'eta' della tabella (e' l'ora di scrittura, `today_predictions_backfill.py:951`),
  per questo si legge `poisson_calibration.generated_at` tramite RPC.
- **TacticAI** e **ML**: previsione, 36 h (sostituisce la data grigia senza soglia).
- **Direzione** (`DirezioneDashboard.tsx`): pagella (36 h) e quota. `analytics_bets` **non ha una
  colonna di tempo** (`migrations/analytics_strategy.sql:85-129`): l'eta' della quota NON e'
  misurabile e si dichiara solo la presenza ("presenti su X righe di Y (eta non tracciata)", oppure
  in rosso "quota assente per questa partita"). Sulla card del mercato, quota NULL -> "QUOTA
  ASSENTE" in rosso invece del trattino. Aggiungere un timestamp ad `analytics_bets` e' una
  modifica di schema fuori perimetro: da decidere.
- Frequenze e Ritardi: calcolo al volo, mostrano gia' `date_from -> date_to` (referto 24/09): invariati.

Migrazione **nuova, additiva**: `migrations/get_direction_eta_2026-09-25.sql` (NON tocca
`get_direction_rpc.sql` ne' `get_direction`), due funzioni SECURITY DEFINER, STABLE, EXECUTE ad
authenticated e service_role come `get_direction`:
- `get_direction_eta(p_fixture_id)` -> `{fixture_id, pagella_generated_at, quota_righe,
  quota_con_prezzo, quota_eta: null, now}`. La pagella e' `max(generated_at)` delle sole righe
  `engine='poisson'`: sono le uniche che `get_direction` usa per l'affidabilita'
  (`get_direction_rpc.sql:175-180`). La quota conta `coalesce(odds_betfair, odds_book)` come
  `get_direction_rpc.sql:165`.
- `get_poisson_calibration_eta(p_league_id)` -> `{league_id, scope, generated_at, now}`. Via RPC
  perche' dal 24/09 (sicurezza_db BLOCCO 2) la lettura diretta della tabella dal client non e'
  garantita.
Due funzioni nello stesso file (nome file dato dal brief) per non chiedere all'utente una terza
migrazione. Se non sono applicate, le tab lo dicono ("data non disponibile", in rosso) e il resto
funziona come prima (test).

## R7 - il ritardo si calcola in UN posto, con UNA regola

**Prima**: tab Ritardi = `get_market_delays` (`sql/market_delays_rpc.sql:40,136-155`: HT mancante =
0-0 con `coalesce`); cruscotto Direzione = calcolo nel browser dalla serie di frequenza
(`signalContext.ts:40-58`) con formule DIVERSE (media dei gap invece di media dei RIT o quota
oggettiva, record che include la corsa aperta). Due numeri diversi anche sui mercati FT.

**Dopo**:
- `migrations/market_delays_ht_2026-09-25.sql`: `CREATE OR REPLACE` di `get_market_delays` con la
  **stessa firma e gli stessi grant**. Regola: sui mercati che usano il primo tempo (`v_uses_ht`)
  una riga senza `halftime_*` NON e' un evento (outcome NULL, esclusa), come `get_market_frequency`.
  I `coalesce` sono tolti; la guardia esplicita serve anche dove l'aritmetica NULL non basta
  (es. `pf1x`: `NULL AND false = false` avrebbe contato un 0). Meta nuova: `ht_missing_rule =
  'escluse'`, `n_ht_missing`. Mercati FT: identici riga per riga.
- Mercati **aggiunti** (additivi, i 13 del foglio restano): `1`, `2`, `gg`, `ng`, `unpt`, `pt1`,
  `ptx`, `pt2`. Servono perche' il cruscotto ha 7 mercati (16 selezioni) e prima 1X2 casa/trasferta,
  esito 1T, BTTS e Under 1T non avevano un equivalente nella RPC: senza aggiungerli il cruscotto
  avrebbe perso il ritardo su quei mercati.
- `frontend/src/lib/signalContext.ts`: il ritardo NON si calcola piu' nel browser; `delayMap`
  mappa (mercato, direzione) -> (codice RPC, linea) e si chiama `get_market_delays` con `mode='all'`
  (tutto lo storico, come la tab). Si mostrano esattamente `ritardo_attuale`, `record`,
  `media_storica` (etichetta "media") e `rit_vs_media` (il rapporto su cui il cruscotto decide
  "molto in ritardo" >= 1.5), piu' "su N partite (K senza primo tempo, escluse)".
  Se la RPC deployata e' ancora quella vecchia (niente `ht_missing_rule`) sui mercati HT il ritardo
  NON si mostra e compare la nota "da applicare migrations/market_delays_ht_2026-09-25.sql": un
  numero gonfiato dagli 0-0 finti non si mostra. Sui mercati FT (invariati) si mostra.
  La frequenza resta da `get_market_frequency`.
- `RitardiPanel.tsx`: l'avviso "copertura PT bassa" segue la RPC: con la regola nuova dice "le N gare
  senza dato di primo tempo sono ESCLUSE"; con la RPC vecchia resta il testo di prima.
- **Variazione di significato da portare all'utente**: la "media" del cruscotto passa da "media dei
  gap fra uscite" (calcolo locale) a "media storica / quota oggettiva" della tab (n_eventi/n_uscite).
  Differenza tipica circa 1 partita (gap medio = media storica - 1 circa), quindi il rapporto
  attuale/media si abbassa un poco e la soglia 1.5 "molto in ritardo" scatta un po' piu' tardi.
  Soglia NON cambiata (scelta dell'utente se ritoccarla). Il cruscotto non alimenta nessun bot
  (referto 24/09, sez. 6-7).

### `analytics_signals.delay_*` (NON toccato): quanto diverge
`enrich_analytics_snapshots.py` usa `analytics_market_stats.py`, che replica la RPC VECCHIA:
`_hit_delay` fa `ht = (0, 0)` quando manca l'HT sui mercati HT-dipendenti (`ht_1x2`,
`first_half_btts`, `first_half_double_chance`, `ht_ft`, `first_half_over_*`,
`analytics_market_stats.py:48-62,90-101`). Dopo la migrazione:
- mercati FT: stesso numero della RPC (stessa serie, stesse formule: `delay_avg` = `media_ritardi`,
  NON la `media_storica` del cruscotto);
- mercati HT: diverge esattamente come divergeva la RPC vecchia dalla nuova, in misura che cresce
  con le partite senza HT della lega (vedi Q-R7c);
- inoltre `delay_current` e' point-in-time "in entrata" (prima della partita): per le partite del
  giorno coincide con il ritardo corrente della RPC, per le passate no (by design).
Allinearlo = cambiare `_hit_delay` (fuori perimetro, decisione dell'utente).

---

## Test (tutti sui soli file toccati, DB sandbox)

| Comando | Esito |
|---|---|
| `timeout 600 python -m pytest tactical_engine/tests -q -p no:cacheprovider` | **11 passed** (7 test_math + 4 nuovi) |
| `timeout 900 npx vitest run src/lib/etaDato.test.ts src/components/dashboard/EtaDato.test.tsx src/components/dashboard/DirezioneDashboard.eta.test.tsx src/lib/signalContext.test.ts` | **4 file, 36 test passed** |
| `timeout 600 npx tsc -p tsconfig.app.json --noEmit` | **0 errori** |
| `node AUDIT_2026-09-25/verifica_audit5_pglite.mjs` (PGlite 0.5.8, Postgres in WASM) | **VERDE**, 37 controlli |

Test nuovi:
- (a) `tactical_engine/tests/test_serving.py::test_run_for_date_legge_da_fixture_predictions_e_scrive_5_payload`:
  finto client che imita il query builder di postgrest-py e registra ogni query; righe finte con
  le colonne vere di `fixture_predictions` e `matches`; `matches` SENZA partite di oggi (come il
  vero). 5 partite di 2 leghe -> `{"fixtures":5,"updated":5,"inserted":0,"errors":0}`; la partita
  gia' FT e quella di domani non toccate; da `matches` solo letture con `fixture_date < oggi`;
  nessun INSERT, nessun altro campo modificato. Piu' `test_run_for_date_pagina_anche_le_partite_del_giorno`
  (server che tronca a 2 righe).
- (b) `test_load_prior_paginato_stesse_partite_stesso_ordine_e_order_by`: 2.500 righe con kickoff
  simultanei e `fixture_id` non monotono; server che tronca a 1000; stesse partite nello stesso
  ordine con pagina unica e con pagine da 1000; 4 query (1000+1000+500+vuota) tutte con
  `ORDER BY fixture_id`, `LIMIT 1000` e cursore dalla seconda. Il finto, senza ORDER BY,
  restituisce un ordine fisico rimescolato (come un heap).
- (c) `etaDato.test.ts` (soglie e confini), `EtaDato.test.tsx` (verde/rosso/assente),
  `DirezioneDashboard.eta.test.tsx` ("quota assente" sul mercato senza quota, quota mostrata
  dove c'e', intestazione rossa senza righe `analytics_bets`, pagella di 3 ore verde e di 3 giorni
  rossa, RPC di eta' assente -> rosso e pannello funzionante). Finti con le chiavi dell'output jsonb
  di `get_direction` e `get_direction_eta`.
- (d) **Deviazione dichiarata dal brief**: la regola HT vive SOLO nella RPC (e' il senso di "un
  posto solo"), quindi non esiste una funzione TS che la applichi. Il caso richiesto (lega finta, 10
  partite, 2 senza HT -> ritardo calcolato su 8) e' provato sul PostgreSQL vero in memoria con
  la migrazione vera (`verifica_audit5_pglite.mjs`): over 0.5 1T PRIMA 10 eventi / ritardo 2,
  DOPO 8 eventi / ritardo 0 / `n_ht_missing` 2; pf1x e ggst su 8; sei mercati FT identici alla
  versione vecchia (JSON uguale a meno delle 2 chiavi meta nuove); per 13 coppie la serie di
  `get_market_delays` coincide (partite, ordine, esito) con quella di `get_market_frequency`.
  Lato TS `signalContext.test.ts`: `delayMap` sulle 16 selezioni, contratto "ogni codice usato e'
  nella whitelist della migrazione" (legge il file SQL), valori della RPC passati invariati,
  RPC vecchia su mercato HT -> niente ritardo + nota, parametri esatti della chiamata RPC
  (`p_mode 'all'`). Qui il finto e' il client Supabase (`rpc(nome, parametri) -> {data, error}`),
  cosi' `fetchMarketDelays` e' quella vera.

## Falsificazioni (ogni test nuovo visto ROSSO, poi ripristino verificato)

Python, `AUDIT_2026-09-25/mutazioni_audit5_tacticai.py` (riscrive serving.py, lancia i test,
ripristina sempre e controlla l'uguaglianza byte per byte; sha1 di serving.py prima e dopo:
`6883f6e4...` in tutti e due i casi):
```
=== R1_fonte_matches: ROSSO          FAILED test_run_for_date_legge_da_fixture_predictions_e_scrive_5_payload
=== R2_senza_order_by: ROSSO         FAILED test_run_for_date_legge_da_fixture_predictions_e_scrive_5_payload
    (solo il test b: SOLO_TEST=...order_by)  FAILED test_load_prior_paginato_stesse_partite_stesso_ordine_e_order_by
=== R2_esce_su_pagina_corta: ROSSO   FAILED test_run_for_date_pagina_anche_le_partite_del_giorno
=== R2_senza_sort_cronologico: ROSSO FAILED test_load_prior_paginato_stesse_partite_stesso_ordine_e_order_by
=== R1_senza_filtro_giocate: ROSSO   FAILED test_run_for_date_legge_da_fixture_predictions_e_scrive_5_payload
ripristino: serving.py identico all'originale
```
SQL (PGlite, `MUTANTE=...`; lo script si ferma con exit 3 se un mutante non cambia il testo):
```
MUTANTE=coalesce   (HT mancante = 0-0 come prima)  ROSSO 5: n_eventi 10, serie con le 2 partite, ritardo 2, pf1x 9, serie != frequenza
MUTANTE=noguard    (tolta la sola guardia HT)       ROSSO 1: pf1x su 9 eventi (NULL AND false = false)
MUTANTE=eta_quota  (quota non filtrata per partita) ROSSO 2
MUTANTE=eta_engine (pagella anche righe non Poisson) ROSSO 1
```
(Il primo giro di `eta_quota` era VERDE perche' la sostituzione non trovava il testo, maiuscole
diverse: mutante vuoto. Corretto e aggiunto il blocco "mutante NON applicato".)

TypeScript (sed sul file, test, ripristino da copia; sha1 finali uguali agli originali:
etaDato.ts `51d80eea...`, signalContext.ts `32425b94...`, DirezioneDashboard.tsx `512340e8...`):
```
T1 soglia ignorata (sempre fresco)       4 rossi: 2 etaDato, 1 EtaDato, 1 Direzione (pagella 3 giorni)
T2 dato assente trattato come fresco      3 rossi: etaDato, EtaDato, Direzione (RPC eta assente)
T3 quota NULL mostrata come trattino      1 rosso: Direzione "quota assente"
T4 regola HT ignorata (RPC vecchia ok)    1 rosso: delayFromResult RPC vecchia
T5 Under 1T mappato su ovpt               1 rosso: delayMap first_half_over_0_5 Under
T6 ritardo su last_n invece di all        1 rosso: fetchSignalContext parametri RPC
```

## Query SQL per il coordinatore (sola lettura, DB vero)

```sql
-- Q-R7a  PRIMA della migrazione: tab Ritardi (RPC deployata) su 547, over 0.5 1T
select (r->'meta'->>'n_effective')::int n_eventi, r->'meta'->>'ht_coverage_pct' cop_ht,
       r->'stats'->>'ritardo_attuale' rit_attuale, r->'stats'->>'record' record,
       r->'stats'->>'media_ritardi' media_rit, r->'stats'->>'media_storica' media_storica,
       r->'meta'->>'ht_missing_rule' regola, r->'meta'->>'n_ht_missing' n_ht_missing
from (select public.get_market_delays(547,'ovpt','0.5','all',null,null) r) t;

-- Q-R7b  la serie "giusta" (quella di get_market_frequency, HT mancante escluso):
--        eventi e ritardo attuale; DOPO la migrazione Q-R7a deve dare questi n_eventi e rit_attuale
with p as (select (e->>'idx')::int idx, (e->>'out')::int o
           from jsonb_array_elements(public.get_market_frequency(547,'ou_ht','over',0.5,'all',null,null)->'points') e)
select count(*) n_eventi, max(idx) - coalesce(max(idx) filter (where o = 1), 0) rit_attuale from p;

-- Q-R7c  quante partite di 547 la regola esclude (= prima n_eventi - dopo n_eventi)
select count(*) filter (where h is not null and a is not null)                                         n_eventi_prima,
       count(*) filter (where h is not null and a is not null and hh is not null and ha is not null)   n_eventi_dopo,
       count(*) filter (where h is not null and a is not null and (hh is null or ha is null))          n_senza_ht
from (select case when fulltime_home is not null then fulltime_home when status_short='FT' then goals_home end h,
             case when fulltime_away is not null then fulltime_away when status_short='FT' then goals_away end a,
             halftime_home hh, halftime_away ha
      from matches where league_id = 547 and status_short in ('FT','AET','PEN')) s;

-- Q-R7d  DOPO la migrazione: tab e cruscotto devono coincidere (stessa RPC); controllo FT invariato:
--        lanciare PRIMA e DOPO e confrontare (deve essere identico)
select md5((public.get_market_delays(547,'over','2.5','all',null,null) #- '{meta,ht_missing_rule}' #- '{meta,n_ht_missing}')::text);

-- Q-R7e  divergenza di analytics_signals.delay_* (non toccato) sull'ultima partita di 547
select s.kickoff, s.engine, s.delay_current, s.delay_record, s.delay_avg
from analytics_signals s
where s.league_id = 547 and s.market = 'first_half_over_0_5' and s.selection = 'Over'
order by s.kickoff desc limit 3;

-- Q-R1a  DOPO il primo run notturno: copertura TacticAI di oggi (attesa: ~le partite con storico >= 40)
select count(*) tot, count(tactical_engine_json) tactic
from fixture_predictions where fixture_date >= current_date and fixture_date < current_date + 1;

-- Q-R1b  motivo delle partite ancora senza TacticAI: lega con storico < 40 o squadra mai vista
select fp.league_id, count(*) senza_tactic,
       (select count(*) from matches m where m.league_id = fp.league_id and m.status_short in ('FT','AET','PEN')
          and m.fixture_date >= current_date - 2424 and m.fixture_date < current_date) storico_4_emivite
from fixture_predictions fp
where fp.fixture_date >= current_date and fp.fixture_date < current_date + 1 and fp.tactical_engine_json is null
group by fp.league_id order by 2 desc limit 30;

-- Q-R1c  "stessi numeri": salvare PRIMA del run le lambda delle partite gia' calcolate e confrontarle DOPO
--        (atteso: differenze <= ~1e-3 sulle lambda, <= ~1e-4 sulle probabilita')
select fixture_id, tactical_engine_json->>'lambda_home' lh, tactical_engine_json->>'lambda_away' la,
       tactical_engine_json->'training'->>'n_matches' n
from fixture_predictions where fixture_date >= current_date and tactical_engine_json is not null order by 1;

-- Q-R5   dopo get_direction_eta_2026-09-25.sql: le RPC rispondono
select public.get_direction_eta((select fixture_id from fixture_predictions where fixture_date >= current_date limit 1));
select public.get_poisson_calibration_eta(39), public.get_poisson_calibration_eta(0);
```
Nota per Q-R1a: per ricalcolare oggi senza aspettare la notte si puo' lanciare
`python -m tactical_engine.run_daily --date 2026-09-25` (scrive sul DB: lo decide l'utente).

## Migrazioni da applicare (le applica l'utente, SQL Editor)
1. `migrations/market_delays_ht_2026-09-25.sql` - senza di essa il cruscotto NON mostra il ritardo
   sui mercati HT (nota esplicita) e non ha i mercati 1/2/gg/ng/pt*/unpt ("non disponibile"); la
   tab Ritardi resta com'e' oggi.
2. `migrations/get_direction_eta_2026-09-25.sql` - senza di essa Direzione e Poisson mostrano in
   rosso "eta' non disponibile" per pagella/quota/calibrazione; il resto funziona.
R1/R2 (Python) non dipendono da migrazioni: entrano al prossimo run della action (dopo il merge).

## Reperto fuori perimetro (NON toccato, da portare all'utente)
- `tactical_engine`/`dixon_coles`: con lambda alte e rho vicino al bordo (+0.2) la correzione DC
  produce P(0-0) negativa: nel test sintetico `over_0_5 = 1.0005`, `under_0_5 = -0.0005`. La
  guardia `tau <= 1e-9` in `model.py:112-113` vale solo per le celle osservate nel fit, non per la
  previsione. Da verificare sui payload veri: `select count(*) from fixture_predictions where
  (tactical_engine_json->'markets'->>'under_0_5')::numeric < 0;`

## NON VERIFICATO
- Nessun dato del DB vero: copertura dopo il fix, numeri della lega 547, "stessi numeri" sulle
  partite gia' calcolate, eta' reali (query sopra).
- Le migrazioni sono provate su PGlite 0.5.8 (PostgreSQL 17 in WASM) con tabelle ridotte alle
  colonne usate, non sul Supabase vero: grant/ruoli reali, RLS, `statement_timeout` e tempi su
  tabelle grandi (`get_market_delays` mode `all` su leghe da migliaia di partite, come gia' oggi).
- Che le RPC deployate oggi coincidano con i file del repo (`sql/market_delays_rpc.sql`): la
  migrazione parte da quel file.
- Il comportamento del query builder vero di postgrest-py (`.gt().order().limit()` concatenati dopo
  `.gte/.lt`): provato solo col finto che ne imita l'interfaccia; e' lo stesso schema gia' in
  produzione in `generate_dynamic_cal.py`.
- Resa a video (colori, impaginazione, mobile): nessun `npm run build`, app non avviata.
- Durata del run TacticAI su tutte le ~260 partite/giorno (prima ne faceva ~34): piu' leghe ->
  piu' fit; non misurata.
- Stranezza di vitest 3.2 osservata: una funzione di un modulo `vi.mock` con `mockImplementation`
  che lancia fa fallire il test anche se l'errore e' catturato; i test usano percio' il finto del
  client Supabase. Non indagato oltre.
