# AUDIT TAB DASHBOARD (Frequenze, Ritardi, TacticAI, Poisson, ML, Direzione) - 24/09/2026

Audit in SOLA LETTURA. Worktree allineato a master 20a913a (`git merge --ff-only master`).
Nessun DB interrogato, nessuno script eseguito. Le query da far girare al coordinatore sono in fondo (sez. 7).
`STATO_RIPRESA.md` NON esiste nella radice del worktree (verificato con `ls`).

## 0. Dove sono le 6 tab

Pagina `frontend/src/pages/Dashboard.tsx:16,259-260` -> `components/dashboard/AnalyticsPanels.tsx:25-40`:
- Frequenze Mercati -> `MarketFrequencyPanel` (riga 29, solo se leagueId)
- Studio Ritardi -> `RitardiPanel` (riga 32, solo se leagueId)
- Poisson -> `PoissonPanel` (riga 34)
- Tactics AI -> `TacticalEnginePanel` (riga 35)
- Modelli ML -> `MLPanel` (riga 36)
- Direzione -> `DirezioneDashboard` (riga 37)

Tutti i pannelli sono "Sheet" che caricano SOLO all'apertura e al cambio parametri: nessun realtime, nessun
poll, nessuna cache lato client (niente react-query; solo `useState` + contatore di richiesta anti-race).
Riaprire il pannello = rilettura dal DB.

Premessa importante: le tab Frequenze e Ritardi NON leggono `analytics_signals` (le colonne freq_*/delay_* di
quella tabella servono la pagina /analytics, filtri "Frequenza vs baseline" e "Ritardo mercato >=",
`pages/Analytics.tsx:314-325`). Quindi l'enrich rotto NON tocca queste due tab.

---

## 1. FREQUENZE MERCATI

**Fonte.** `lib/marketFrequency.ts:153-164` -> RPC `get_market_frequency(p_league_id, p_market, p_selection,
p_line, p_mode, p_last_n, p_season_year)` definita in `sql/market_frequency_rpc.sql:40-280`; stagioni da
`get_league_seasons` (`sql/market_frequency_rpc.sql:286-316`, `lib/marketFrequency.ts:167-171`).
Fetch in `MarketFrequencyPanel.tsx:117-130` (stagioni) e `:143-177` (serie), solo con pannello aperto.

**Calcolo.** AL VOLO su `matches` (`sql/market_frequency_rpc.sql:111-132`): `league_id = lega`,
`status_short IN ('FT','AET','PEN')`, settlement 90' (fulltime_*, fallback goals_* solo FT). Nessuna
materializzazione.

**Finestra.** Default = ULTIME 300 settlate della lega (`MarketFrequencyPanel.tsx:87-88`, `lib/marketFrequency.ts:160`,
`limit` a `sql/market_frequency_rpc.sql:131`). Selezionabili "Stagioni" e "Tutto lo storico"
(`MarketFrequencyPanel.tsx:310`). Sempre UNA lega sola.

**Chi popola.** `matches` <- `daily_yesterday_backfill.py` (workflow `daily_yesterday_backfill.yml:5`, cron 01:12 UTC,
solo FT/AET/PEN: `daily_yesterday_backfill.py:90-133`).

**Aggiornata oggi?** Si', a condizione che `daily_yesterday_backfill` sia andato (NON verificato: query Q1).
Non dipende dalla action rotta.

**Eta' a video.** Mostra l'intervallo `date_from -> date_to` della serie (`MarketFrequencyPanel.tsx:408-410`,
meta in `sql/market_frequency_rpc.sql:253-254`): la data dell'ultima partita settlata e' visibile (eta' implicita).

**Ai bot.** Omega SI, ma solo INFORMATIVO: `omega_db.market_frequency` (`Betfair/omega/omega_db.py:763-773`, last_n=300,
exact_ft/exact_ht) usato da `omega_advisor.py:14,160,362` (il consulente "non blocca mai nulla", `omega_advisor.py:3-4,24-27`)
e attaccato alla proposta in `omega_service.py:6211,6260`. Mike/Safe/scan_feed/xhedge: NO (grep vuoto).

## 2. STUDIO RITARDI

**Fonte.** `lib/marketDelays.ts:129-138` -> RPC `get_market_delays` (`sql/market_delays_rpc.sql:48-380`).
Fetch in `RitardiPanel.tsx:171-180`.

**Calcolo.** Al volo su `matches` (`sql/market_delays_rpc.sql:123-128`), stessi filtri di status. Riproduzione 1:1 del
foglio Excel: HT mancante = 0-0 (`sql/market_delays_rpc.sql:40,136`).

**Finestra.** Default = TUTTO lo storico della lega (`RitardiPanel.tsx:138`); in alternativa ultime N (500) o stagione.

**Chi popola / aggiornata / eta'.** Come Frequenze (`matches`, 01:12 UTC). Mostra `date_from -> date_to`
(`RitardiPanel.tsx:282`).

**Ai bot.** NESSUNO. Grep di `get_market_delays` in `Betfair/` (esclusi test e tool): zero chiamate. Omega lo cita solo
in documenti/strumenti di analisi (`omega/tools/m2_pesi.py:1430`: "nessun regime di RITARDO").

## 3. POISSON

**Fonte.** `lib/fixtureModels.ts:68-76`: `fixture_predictions.db_json_analisi` per `fixture_id` (una riga). Fetch in
`PoissonPanel.tsx:51-60`. Mostra `markets_calibrated` se presente altrimenti `markets` (`PoissonPanel.tsx:63-64`) con
badge "calibrato/grezzo" (`:147-148`).

**Calcolo.** MATERIALIZZATO: snapshot per partita scritto una volta dalla action `today_predictions_backfill.yml`
(cron 02:18 UTC, `today_predictions_backfill.yml:5,46`) -> `Prediction/today_predictions_backfill.py:1418-1740`
(modello `poisson_xg_hybrid_dc`). La partita gia' fatta viene saltata (`prediction_already_done`, `:983`,
`skipped_existing` `:2422,2460`): il numero NON si ricalcola durante il giorno.

**Finestra (by design).** Forma delle due squadre su ultime 5/10/15 partite pesate 0.5/0.3/0.2
(`today_predictions_backfill.py:1487-1494`). Calibrazione dalla tabella `poisson_calibration` (lettore
`poisson_calibrator.py:100`, applicata a `today_predictions_backfill.py:920-943`), rigenerata SETTIMANALMENTE
(`weekly_poisson_calibration.yml:5`, lunedi' 03:27, `generate_dynamic_cal.py:459`) su tutto lo storico paginato
(`generate_dynamic_cal.py:108-138`). Ultimo aggiornamento 21/09 = lunedi' = regolare.

**Aggiornata oggi?** Si' (fixture_predictions ultimo 08:12 di oggi). Eta' a video: `generated_at` (`PoissonPanel.tsx:96,155`).
NON mostra `calibrated_at` (campo presente nel tipo, `lib/fixtureModels.ts:22`).

**Ai bot.** SI, in DECISIONE:
- catena lambda pre-match `Betfair/stream/db.py:210-251` (`get_fixture_prematch_lambdas`): tactical_engine_json ->
  poi `db_json_analisi.inputs.lambda_*`. Usata da Omega (`omega_service.py:1061-1067`, primo anello della catena
  `_prematch_lambdas` `:1027-1043`), da Safe (via Omega, `safe_strategy/bot_service.py:6091,6259`), da Mike
  (`mike/db.py:514-524` -> `mike/dossier.py:58`) e dal runner segnali (`stream/runner.py:452-458`).
- Mike legge anche `dc_rho` e `markets_calibrated.over_3_5` (`mike/dossier.py:64-72`) per il dossier.
- Omega advisor: probabilita' del punteggio (informativo, `omega_advisor.py:5-11,345-351`).
- Scalper calcio: consenso ML+Poisson 1X2 per il bias (`stream/scalper/bias_resolver.py:80-87,151`,
  `scalper_session.py:405-412`).
Nota: i bot usano le LAMBDA (inputs), non le probabilita' calibrate che la tab mostra.

## 4. TACTICS AI (Tactical Engine GSG)

**Fonte.** `lib/tacticalEngine.ts:57-61`: `fixture_predictions.tactical_engine_json`. Fetch `TacticalEnginePanel.tsx:80-90`,
eta' a video `generated_at` (`:107,170`).

**Chi popola.** Agganciato in coda a `today_predictions_backfill.py:2736-2746` (non fatale, try/except che logga solo
warning) -> `tactical_engine/serving.py:125-220`.

**REPERTO GRAVE (da confermare con Q3/Q4).** `serving.py:137-140` cerca le partite di oggi nella tabella `matches`
con `status_short NOT IN ('FT','AET','PEN')`. Ma l'unico scrittore schedulato di `matches` inserisce SOLO partite
finite (`daily_yesterday_backfill.py:90-133`, "finished_only"). Se `matches` non contiene le partite future, il motore
trova 0 partite e ritorna `{"fixtures": 0}` in silenzio (`serving.py:141-143`). Coerente con la copertura misurata
dal delegato M2 del 17/09: `tactical_engine_json` presente su 962/14.725 = 6,5 % (`Betfair/omega/M2_DATI_E_PESI_2026-09-17.md:58`,
che lo definisce "MANUALE ... nessun workflow schedulato") e 31/405 = 7,7 % (`omega/PROGETTO_OMEGA_V3_2026-09-16.md:106`).

**REPERTO 2 (da confermare con Q4).** `_load_prior` (`serving.py:61-70`) legge lo storico di lega da `matches` SENZA
paginazione e SENZA ORDER BY su una finestra di 4 emivite (4*420/ln2 = circa 2.424 giorni = 6,6 anni). PostgREST
restituisce al massimo `max_rows` righe (default Supabase 1000; il repo ha `max_rows = 1000` in
`Telegram bot/supabase/config.toml:18`, config del progetto vero NON verificata). Una lega da 380 partite/anno ha circa
2.500 righe nella finestra: il fit userebbe ~1000 partite IN ORDINE ARBITRARIO (non le piu' recenti). Il numero usato e'
scritto nel payload (`training.n_matches`, `tactical_engine/serving.py:119`): se il massimo e' 1000 il taglio e' provato.
Stesso difetto (senza paginazione) sulla lettura delle partite del giorno (`serving.py:137-140`).

**Usa tutti i dati?** No (vedi reperti). By design e' una finestra con time-decay.

**Ai bot.** SI, in DECISIONE, come PRIMO anello della catena lambda (`stream/db.py:216-217,235`): Omega, Safe, Mike,
runner. Oggi in pratica quasi sempre assente -> i bot cadono su Poisson (`db_json_analisi.inputs`), poi pre-KO/mercato.

## 5. MODELLI ML

**Fonte.** `lib/fixtureModels.ts:78-86`: `fixture_predictions.model_predictions_json`. Fetch `MLPanel.tsx:44-55`,
eta' `generated_at` (`:107,162`).

**Chi popola.** Stesso run 02:18 UTC, `today_predictions_backfill.py:2718-2733` -> `Ai Engine/ai_engine/serving_batch.py`
-> `predict_fixture.py`. Modelli per lega da `ai_model_registry` (`predict_fixture.py:502-512`) riallenati da
`retrain_models.yml` (cron 08:19, `:55`, gate "almeno una giornata nuova"); post-calibrazione da `ml_post_calibration`
(`predict_fixture.py:373-386,886`) rigenerata da `ml_calibration.yml` (05:14, `compute_ml_post_calibration.py:244`).
Sequenza: le predizioni delle 02:18 di oggi usano modelli di ieri 08:19 e calibrazione di ieri 05:14 (ritardo 1 giorno,
fisiologico). Retrain e calibrazione aggiornati oggi (fatti del coordinatore).

**Finestra (by design).** Feature da `history_df` delle ultime 3 stagioni della lega (`predict_fixture.py:430,456-489`).

**Ai bot.** PARZIALE: solo lo scalper calcio (bias 1X2, `bias_resolver.py:82`). Omega/Safe/Mike NO: l'ML non ha il
Correct Score e non entra nelle lambda (`M2_DATI_E_PESI_2026-09-17.md:68,778`).

## 6. DIREZIONE

**Fonte.** `lib/direzione.ts:48-54` -> RPC `get_direction(p_fixture_id)` (`migrations/get_direction_rpc.sql:38-250`).
Fetch `DirezioneDashboard.tsx:287-300`, piu' quote Betfair `get_betfair_direction_odds` (`lib/betfair.ts:53`) e, al click
su un mercato, contesto freq/ritardo via `get_market_frequency` mode 'all' (`lib/signalContext.ts:60-79`,
`DirezioneDashboard.tsx:85-91`).

**Calcolo.** Misto:
- AL VOLO: probabilita' dei motori dai JSON di `fixture_predictions` (`get_direction_rpc.sql:59-63`), quindi eredita
  lo stato di Poisson/ML/TacticAI (TacticAI quasi sempre assente).
- MATERIALIZZATO: affidabilita' = `direction_pagella` SOLO per engine='poisson' (`get_direction_rpc.sql:170-187`),
  pagella ricostruita ogni notte da `build_direzione.py` (step `pagella`, `predictions_results_backfill.yml:142-149`)
  su TUTTO lo storico settled di `bet_features` (vista su `analytics_bets`, `build_direzione.py:7,79,135`).
- MATERIALIZZATO: quota della direzione da `analytics_bets` (`get_direction_rpc.sql:161-166`), che alimenta
  quota/prob implicita/lift nella card (`DirezioneDashboard.tsx:36-38,150,183,206-219`).

**Aggiornata oggi? PARZIALE.** La pagella gira (ultimo 10:19 di oggi) ma legge `analytics_bets`, che lo step `bets`
non riesce a rinfrescare da 2 giorni: la pagella NON contiene gli esiti dei giorni mancanti, e soprattutto
`analytics_bets` copre [oggi-N, oggi+2) (`refresh_analytics_bets.py:150-156`), quindi per le partite di OGGI e domani la
quota puo' mancare -> card con quota "-" e senza confronto con la prob implicita (query Q6).

**Eta' a video.** NO. `generated_at` della RPC e' `now()` (`get_direction_rpc.sql:206`), non l'eta' della pagella ne'
di analytics_bets; il componente non la mostra comunque (grep `generated_at` vuoto in `DirezioneDashboard.tsx`).

**Ai bot.** NESSUNO. Grep di `get_direction`/`direction_pagella`/`analytics_bets`/`bet_features` in `Betfair/`
(esclusi test/documenti): zero letture. Omega la esclude esplicitamente (`PROGETTO_OMEGA_V3_2026-09-16.md:112`,
`M2_DATI_E_PESI_2026-09-17.md:69,778`).

(Nota: esiste anche il report "Direzioni" in /analytics > Reportistiche, `DirezioniReport.tsx:1-9`, che legge
`analytics_signals` + `engine_signals` via `get_direction_report*` (`migrations/direction_report_rpc.sql:104,129,135`).
Il filtro "solo Betfair" dipende da `engine_signals`, FERMO: dopo il 17/09 quel filtro restituisce vuoto.)

---

## 7. TABELLA tab x bot

| Tab | Omega | Safe | Mike | scalper calcio | scan_feed | xhedge_worker |
|---|---|---|---|---|---|---|
| Frequenze | parziale (solo advisor informativo) | NO | NO | NO | NO | NO |
| Ritardi | NO | NO | NO | NO | NO | NO |
| Poisson | SI (lambda, decisione) | SI (via catena Omega) | SI (lambda + rho + O3.5 cal.) | SI (consenso 1X2) | NO | NO |
| TacticAI | SI in teoria (1o anello lambda), di fatto quasi mai presente | idem | idem | NO | NO | NO |
| ML | NO | NO | NO | SI (consenso 1X2) | NO | NO |
| Direzione | NO | NO | NO | NO | NO | NO |

Tabelle "di analisi" (analytics_signals, analytics_bets, direction_pagella, engine_signals, signal_history,
poisson_calibration, ml_post_calibration) lette dai bot: NESSUNA direttamente. poisson_calibration e
ml_post_calibration arrivano ai bot solo "dentro" i JSON di fixture_predictions (Poisson calibrato; ML calibrato).
I bot SCRIVONO engine_signals/signal_history solo tramite il report locale (vedi R2).

## 8. REPERTI

R1 (GRAVE, da confermare Q3/Q4) - TacticAI quasi mai calcolato: cerca le partite di oggi in `matches`, che contiene solo
partite finite (`tactical_engine/serving.py:137-143` vs `daily_yesterday_backfill.py:90-133`); errore silenzioso
(warning non fatale, `today_predictions_backfill.py:2745-2746`). Conseguenza: tab vuota sulla maggior parte delle partite
e primo anello della catena lambda dei bot quasi sempre saltato. Fix: leggere le partite del giorno da
`fixture_predictions` (come `serving_batch.py:60-62`) - taglia S.

R2 (GRAVE) - `_load_prior` senza paginazione/ORDER BY (`tactical_engine/serving.py:66-70`): fit su un sottoinsieme
arbitrario di al massimo `max_rows` righe. Fix: paginazione keyset come negli altri script - taglia S.

R3 (MEDIO) - `engine_signals` fermo NON per la action: e' alimentato SOLO dal report LOCALE manuale
(`aggiorna_report.bat:21` -> `Betfair/betfair_report_manager.py:239-251` -> `migrations/backfill_engine_signals.py`,
finestra 21 gg, join con `matches`). Dal log locale `Betfair/betfair_matcher.log`: giri il 02/09, 09-11/09, 17/09, 23/09
19:02 ("7410 righe sincronizzate"). Il join con `matches` (solo partite finite) spiega perche' il kickoff massimo resta
indietro (ipotesi, Q7). Non tocca le 6 tab, ma rende vuoti il toggle "solo Betfair" della lista partite della Dashboard
(`MatchesList.tsx:129-133`) e del report Direzioni. Stesso per `signal_history` (`Betfair/money_management.py:2384-2471`,
solo report locale -> 26 righe/7 gg).

R4 (MEDIO) - Direzione parziale per la action rotta: pagella senza gli ultimi giorni e quote mancanti per le partite dei
giorni non rinfrescati (anche oggi/domani) - vedi sez. 6. Nessun avviso a video.

R5 (MEDIO) - Nessuna tab dichiara l'eta' del dato MATERIALIZZATO che usa: Direzione non mostra l'eta' di pagella e
quote; Poisson mostra `generated_at` ma non `calibrated_at` ne' la data della calibrazione settimanale. Frequenze e Ritardi
mostrano la data dell'ultima partita (ok). Taglia S (campo "aggiornato al" + soglia rossa).

R6 (BASSO) - Frequenze apre su "ultime 300" e non su tutto lo storico (`MarketFrequencyPanel.tsx:87-88`): e' una scelta
d'interfaccia, il tutto-storico e' a un click. Da decidere se l'utente vuole "tutto" di default.

R7 (BASSO, divergenza nota e dichiarata) - Ritardo calcolato in DUE modi diversi: tab Ritardi = foglio Excel (HT vuoto =
0-0, `sql/market_delays_rpc.sql:40,136`), cruscotto Direzione = calcolo corretto dalla serie di frequenza
(`lib/signalContext.ts:1-13,44-58`); su leghe con HT mancanti i due numeri differiscono (esempio citato: 547 su over 0.5 1T).
In piu' esiste un TERZO calcolo materializzato (`analytics_signals.delay_*` da `enrich_analytics_snapshots.py`) usato da
/analytics. Duplicazione di calcolo x3.

R8 (BASSO) - Lambda dei bot: i bot usano `inputs.lambda_*` NON calibrate, la tab Poisson mostra probabilita' calibrate:
bot e tab non guardano lo stesso numero. Da portare all'utente, non da cambiare (strategie intoccabili).

R9 (INFO) - L'enrich rotto (10 leghe, 19-25/09) NON tocca le 6 tab: tocca solo /analytics (`analytics_signals.freq_*`,
filtri `pages/Analytics.tsx:314-325`) e, via `analytics_bets`, la Direzione (R4).

### Cosa servirebbe perche' ogni tab "usi tutti i dati e li passi ai bot" (senza implementare)
- Frequenze/Ritardi: gia' al volo su tutto `matches`; per i bot servirebbe una lettura esplicita nel contratto
  (oggi solo advisor informativo Omega) -> decisione utente (strategie intoccabili). S per l'aggancio, decisione L.
- Poisson: gia' passato ai bot. Allineare "cosa vede la tab" e "cosa usa il bot" (R8) o dichiararlo in UI: S.
- TacticAI: R1 + R2: S+S; poi misura della copertura per 7 gg.
- ML: passa solo allo scalper; estenderlo agli altri bot e' una modifica di strategia -> decisione utente.
- Direzione: riparare lo step `bets` (in corso per 57014) e mostrare l'eta' di pagella/quote: M; passarla ai bot:
  decisione utente (L).
- engine_signals/signal_history: spostare la sincronizzazione dal report locale a una action notturna, o dichiararli
  "solo report manuale": M.

## 9. QUERY PER IL COORDINATORE (sola lettura)

```sql
-- Q1 matches aggiornato (ultima partita finita)
select max(fixture_date) as ultima_ft, count(*) filter (where fixture_date >= now() - interval '2 days') as ft_48h
from matches where status_short in ('FT','AET','PEN');

-- Q2 matches contiene partite NON finite di oggi/domani? (se 0 -> R1 confermato)
select status_short, count(*) from matches
where fixture_date >= current_date and fixture_date < current_date + 2 group by 1;

-- Q3 copertura TacticAI per giorno (ultimi 14 gg)
select fixture_date::date d, count(*) tot,
       count(tactical_engine_json) tactic, count(db_json_analisi) poisson, count(model_predictions_json) ml
from fixture_predictions where fixture_date >= current_date - 14 group by 1 order by 1;

-- Q4 taglio a 1000 righe del fit TacticAI (R2)
select max((tactical_engine_json->'training'->>'n_matches')::int) mx,
       count(*) filter (where (tactical_engine_json->'training'->>'n_matches')::int = 1000) a_1000
from fixture_predictions where tactical_engine_json is not null;

-- Q5 eta' pagella e analytics_bets
select max(generated_at) from direction_pagella;
select date_trunc('day', kickoff)::date d, count(*) from analytics_bets
where kickoff >= current_date - 7 and kickoff < current_date + 2 group by 1 order by 1;

-- Q6 partite di oggi senza quota nella Direzione
select count(distinct fp.fixture_id) tot,
       count(distinct fp.fixture_id) filter (where ab.fixture_id is null) senza_analytics_bets
from fixture_predictions fp left join analytics_bets ab on ab.fixture_id = fp.fixture_id
where fp.fixture_date >= current_date and fp.fixture_date < current_date + 1;

-- Q7 engine_signals: emissioni recenti vs kickoff
select max(emitted_at), max(kickoff), count(*) filter (where emitted_at >= now() - interval '7 days') from engine_signals;

-- Q8 RPC deployate uguali ai file del repo (spot check)
select proname, md5(prosrc) from pg_proc where proname in ('get_market_frequency','get_market_delays','get_direction');
```

## 10. NON VERIFICATO
- Nessun dato del DB letto da me: tutte le condizioni "aggiornata oggi" vengono dai fatti del coordinatore o sono ipotesi
  marcate (Q1-Q8).
- Che le RPC deployate coincidano con `sql/*.sql` e `migrations/get_direction_rpc.sql` (Q8).
- Il `max_rows` reale del progetto Supabase (R2).
- I log GitHub della action `today_predictions_backfill` (riga "tactical_engine ... fixtures: 0").
- Se lo scalper calcio sia oggi acceso (solo lui consuma l'ML).
