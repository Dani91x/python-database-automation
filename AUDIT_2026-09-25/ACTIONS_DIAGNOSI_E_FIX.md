# Action GitHub — diagnosi della catena e correzioni (25/09/2026)

Delegato del coordinatore, worktree `agent-a25083f10210d5c55` (base `84cf1e6`). Niente commit, niente push,
niente `gh workflow run`. Letture del DB vero: SOLO tramite i log delle run (`gh run view`).
Strumenti di misura riproducibili in questa cartella: `misure_action.py` (durate e ritardi dai `gh run list`),
`prova_preflight_atlante.py` (prova a secco dello step nuovo contro un finto PostgREST locale),
`falsificazione_2026-09-25.txt` (esito delle 5 mutazioni).

## 0. Risposta breve

1. **Perché il Retrain si salta oggi.** `retrain_models.yml` job `plan`:
   `if: ... || github.event.workflow_run.conclusion == 'success'`. La conclusion guardata è quella dell'INTERA run del
   Daily. Il job accessorio `hazard-atlas` (montato nel Daily dal commit `6070623`) è fallito con 404 (tabelle
   dell'atlante assenti) → run Daily `failure` anche con il backfill verde → `plan` skipped → `train` skipped
   (`needs: plan`) → `rechain` skipped (`needs.plan.outputs.has_work` vuoto) → run Retrain `skipped`.
   Prove: run 36101390338 tentativo 1 (`run-backfill` success 06:06:24→06:09:46, `hazard-atlas` failure
   06:09:51→06:10:01) → Retrain 36101658347 skipped (06:10:04); tentativo 2 = «re-run failed jobs» lanciato da
   `Dani91x` (triggering_actor) alle 07:49:36, `hazard-atlas` di nuovo failure → Retrain 36109661044 skipped (07:49:53),
   tutti e tre i job `skipped`. Il salto è «per progetto» SOLO quando fallisce il backfill; per un job accessorio è un
   difetto → **corretto** (atlante in un workflow suo, §3 M1).
2. **Cosa fa ML Post-Calibration quando il retrain è skipped.** Parte lo stesso (`workflow_run` `completed` scatta
   anche per una run skipped), modalità incrementale: legge tutte le 18.849 righe di `calibration_cells` e conclude
   «Nessuna lega riaddestrata dall'ultima calibrazione: niente da fare.» (log di 36109665353, 07:50:15→07:50:28).
   Non scrive nulla: è un **success vuoto** (innocuo ma fuorviante, e una lettura inutile sul DB) → **corretto**:
   ora la run è dichiaratamente `skipped` se il retrain a monte è skipped (§3 M3).
3. **Today Predictions Backfill `cancelled` il 23/09** (35833741799): annullata a mano dall'utente dopo 3 min perché
   sovrapposta al lancio di verifica 35832211809 (CRONOSTORIA 23/09 h11:15: «run pianificata 35833741799 cancellata
   dall'utente dopo 3 min (sovrapposta: nessun danno, scritture idempotenti)»). Il workflow a quel commit (`16d8d2f`)
   non aveva ancora il gruppo di concorrenza (arrivato con `fbf0414` alle 08:22Z). Categoria (f) manuale, nessun
   difetto aperto.
4. **Predictions Results Backfill di oggi**: alle 08:11 UTC la run pianificata (cron 03:23 UTC) NON era ancora stata
   creata da GitHub (ritardo mediano misurato 5,07 h → attesa ~08:30 UTC). Esito: vedi §8 (ricontrollo finale).
5. **Leagues mapper vs stagione 2026-27**: il mapper INSERISCE solo le coppie (lega, stagione) mancanti e non
   aggiorna MAI una riga esistente → le righe 2026 inserite quando API-Football dava ancora coverage False restano
   False per sempre. Dettaglio e cosa servirebbe in §6 (decisione dell'utente, non toccato nel merito).
6. **Causa esterna strutturale**: il cron di GitHub parte con ~5 h di ritardo mediano (min 0,6 h, max 12 h) su TUTTI
   i workflow. Gli orari distanziati di 1 h nei cron non garantiscono nulla: le run reali si accavallano. Non corretto
   (nessun aggiramento inventato): decisione dell'utente, §5.

## 1. La catena reale

Chiave DB: TUTTI i workflow passano solo `secrets.SUPABASE_URL` + `secrets.SUPABASE_SERVICE_ROLE_KEY` (21 usi; nessun
`SUPABASE_KEY`/anon). Tutti gli script leggono la service_role: `config.py:10` → `db_client.py:21`
(`create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)`), `cloud_retrain_shard.py:72`, `genera_atlante.py:694`,
probe inline di retrain/validate. I blocchi di sicurezza B1-B3 del 24/09 (anon solo `leads:INSERT`) quindi NON
toccano le action (service_role = BYPASSRLS; prova: Daily del 25/09 `run-backfill` verde dopo i blocchi).
Segreti configurati (`gh secret list`): `API_FOOTBALL_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_URL` + `GITHUB_TOKEN`
automatico: **nessun segreto mancante**. Tutti gli 8 workflow sono `active`.

Durate = run verdi al 1° tentativo, non manuali, dal 25/08 (`misure_action.py`). Roma = UTC+2 (CEST).
Ritardo = creazione della run − orario del cron (schedule).

| Workflow | Cron UTC / Roma | Trigger | Job → script | Durata reale (mediana / p90 / max) | Timeout | Ritardo cron mediano |
|---|---|---|---|---|---|---|
| Daily Yesterday Backfill | 01:12 / 03:12 | schedule, dispatch | `run-backfill` → `daily_yesterday_backfill.py` (nessun argomento = ieri) | 7,7 / 26,7 / 32,0 min | default 360 | 4,76 h (min 1,16, max 11,49) |
| **Hazard Atlas (NUOVO file, prima job del Daily)** | — | `workflow_run` Daily `completed` (se non cancelled), dispatch | `hazard-atlas` → prerequisiti + `python -m Betfair.stream.scalper.genera_atlante --stato-db --incrementale --bootstrap-nuove 10 --stagioni-indietro 10 --scrivi-db` | mai riuscito (2 tentativi, 404 in 10 s) | 30 | — |
| Retrain ML Models | 08:19 / 10:19 (fallback) | `workflow_run` Daily `completed` (plan solo se conclusion success), schedule, dispatch; concurrency `retrain-models` | `plan` (planner `training_planner.select_leagues_to_train`) → `train` ×3 shard `cloud_retrain_shard.py --shard-index --total-shards --use-planner --leagues --time-budget-min --parallel-leagues --last-n-seasons` → `rechain` (`gh workflow run retrain_models.yml -f chain_depth`) | 1,0 / 163,7 / 272,5 min (1 min = nessun lavoro) | plan 8, train 330, rechain 8 | 4,99 h |
| ML Post-Calibration | 05:14 / 07:14 (full) | `workflow_run` Retrain `completed` (incrementale), schedule (`--full`), dispatch; concurrency `ml-calibration` | `assemble` → `compute_ml_post_calibration.py --min-n N [--full]` | 0,7 / 1,3 / 1,9 min | 20 | 4,72 h |
| Today Predictions Backfill | 02:18 / 04:18 | schedule, dispatch(`date`); concurrency | `run-predictions` → `python -m Prediction.today_predictions_backfill [--date]` | 66,2 / 139,5 / 253,1 min | default 360 | 5,29 h |
| Predictions Results Backfill | 03:23 / 05:23 | schedule, dispatch(`date`,`leagues`); concurrency | `run-results-backfill` → `python -m Prediction.predictions_results_backfill [--date]`, `build_analytics_signals.py --days`, `merge_engine_signals.py --days`, `enrich_analytics_snapshots.py --days [--leagues]`, `refresh_analytics_bets.py --days`, `build_direzione.py`, gate errori nascosti | 40,9 / 58,5 / 66,0 min | default 360 | 5,07 h |
| Weekly Poisson Calibration | lun 03:27 / 05:27 | schedule, dispatch | `calibrate` → `generate_dynamic_cal.py`, `update_poisson_calibration.py --apply`, `generate_dc_rho.py` (continue-on-error + gate), commit+push su master | 21,2 / 21,2 / 21,5 min | default 360 | 5,72 h |
| Monthly Leagues Mapping | giorno 1, 00:12 / 02:12 | schedule, dispatch | `run-leagues-mapper` → `leagues_mapper.py` | 1,2 min | default 360 | 4,82 h |
| Validate Models | — | solo dispatch; concurrency | `validate` → `validate_walkforward.py --leagues --test-seasons` | (nessuna run recente) | 120 | — |

Argomenti CLI verificati contro gli `argparse` reali: `Prediction/predictions_results_backfill.py:853` (`--date`),
`Prediction/today_predictions_backfill.py:2755` (`--date`), `build_analytics_signals.py:418` (`--days`),
`merge_engine_signals.py:229` (`--days`), `enrich_analytics_snapshots.py:502,505` (`--days`, `--leagues`),
`refresh_analytics_bets.py:229` (`--days`), `compute_ml_post_calibration.py:269-270` (`--min-n`, `--full`),
`cloud_retrain_shard.py:169-202` (tutti i 7 usati esistono), `validate_walkforward.py:124-125`,
`update_poisson_calibration.py:522` (`--apply`), `genera_atlante.py` (`--help` eseguito: tutti gli argomenti usati
esistono), `training_planner.py:168` (`select_leagues_to_train`). File requirements presenti (`requirements.txt`,
`requirements-planner.txt`, `requirements-train.txt`). **Nessuno script o argomento inesistente.**

Orari REALI mediani di partenza (cron + ritardo mediano, UTC): Daily ~05:58 → Retrain `workflow_run` ~06:06 (se c'è
lavoro 1-4,5 h) → Post-Cal incrementale alla fine del retrain; Today ~07:35 (≈66 min); Results ~08:27 (≈41 min);
Post-Cal full ~09:57; Retrain fallback ~13:18. Oggi: Daily 06:06, Today 07:56 (in corso alle 08:11).

## 2. Run non verdi degli ultimi 7 giorni (18-25/09)

| Run | Workflow / evento | Esito | Causa provata | Stato |
|---|---|---|---|---|
| 36101390338 (tent. 1 e 2) | Daily / schedule | failure | job `hazard-atlas`: `urllib.error.HTTPError: HTTP Error 404: Not Found` in `genera_atlante.py:585 leggi_stato_db` → `lettore.tutte("hazard_atlas_leghe", ...)`; `run-backfill` success. Categoria (b) tabella mancante + (d) job accessorio dentro la run che fa da gate | **workflow corretto ora** (M1/M2); **azione esterna**: migrazione `hazard_atlas_2026-09-24.sql` + bootstrap |
| 36101658347, 36109661044 | Retrain / workflow_run | skipped | `plan.if` richiede `workflow_run.conclusion == 'success'`; la run Daily era `failure` solo per l'atlante | **corretto ora** (M1): il Daily ora = solo backfill |
| 36101662570, 36109665353 | Post-Cal / workflow_run | success vuoto | incrementale su retrain skipped: «Nessuna lega riaddestrata…» | **corretto ora** (M3): run skipped dichiarata |
| 35425250583 (19/09), 35494758357 (20/09), 35568831478 (21/09) | Retrain / workflow_run | failure | shard con `[ERROR] league N: {'code': '57014'}` su `match_odds (offset=50600)` (es. 19/09 06:27:57 lega 144; 20/09 07:42:53 lega 40); riepiloghi «✗ Errori: 1/1/4» | (b) DB, risolto da `16d8d2f` (branch fix 57014 del 21/09, db_adapter a ordine deterministico + blocchi + ritentativo di fine shard); verifica 23/09: 7/7 leghe, zero 57014 |
| 35432041277 (19/09), 35589926333, 35592896432, 35596470375 (21/09) | Retrain / dispatch (rechain e manuali) | failure | stessa causa 57014 (35596470375: 1 lega, «✗ Errori: 1») | come sopra |
| 35833741799 (23/09) | Today / schedule | cancelled | annullata a mano dall'utente (sovrapposta al lancio di verifica); log: `Terminate orphan process: pid (2384) (python)` alle 07:52:46 | (f) manuale, nessun difetto |
| 35837269470 (23/09) | Today / dispatch `date=2026-09-19` | failure (voluto) | `ANOMALIA NON RECUPERATA ... 57014` su upsert delle predizioni, riepilogo «ANOMALIE NON RECUPERATE per 2026-09-19: 106», `Uscita con codice 1` | (b) DB sotto 4 job concorrenti lanciati a mano; fail-loud funzionante; blocco upsert 100→25 in `b418c77` |
| 35837906029, 35838543385, 35844019126 (23/09) | Results / dispatch+schedule | failure (gate) | `Esiti step: ... enrich=failure bets=failure`; `RuntimeError: lettura analytics_signals lega 929 (offset 0, blocco 100) fallita dopo 5 tentativi: 57014` | (b), risolti da `1e4b8c3`/`29f50b0` (keyset per lega, bets v2) |
| 35976004167 (24/09) | Results / schedule | failure (gate) | `enrich=failure bets=failure`; `[ERR lega 292/293/653/251/401/164/253/489] lettura fallita` | (b), risolto da `29f50b0` |
| 36002968576 (tent. 2), 36011159941 (24/09) | Results / dispatch | failure (gate) | `enrich=failure` solo per 1 lega («Leghe FALLITE (1)» = 667) | (a/b) risolto da `8d43da0` (keyset `(season_year, fixture_id)`); **verde 36030163506** su `551d7cd` (tutti gli step success) |

Nessun fallimento per dipendenze/versione Python (c) negli ultimi 7 giorni. Il ritardo del cron (e) non ha fatto
fallire run ma causa sovrapposizioni (§5).

## 3. Modifiche (nel worktree, non committate)

**M1 — `.github/workflows/hazard_atlas.yml` (NUOVO)**. Il job `hazard-atlas` esce dal Daily e vive in un workflow
suo: `on: workflow_run: workflows: ["Daily Yesterday Backfill"], types: [completed]` + `workflow_dispatch`;
`if: github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion != 'cancelled'` (= stessa regola
di prima `needs: run-backfill` + `!cancelled()`: dopo il backfill, anche se fallisce, mai se annullato);
`concurrency: hazard-atlas` senza cancellazione; `timeout-minutes: 30`; comando dell'atlante IDENTICO.
Perché un workflow separato e non `continue-on-error: true`: con `continue-on-error` a livello di job la run del
Daily diventa verde anche quando l'atlante fallisce → l'errore sparisce (proprio i «falsi verdi» eliminati il 21/09).
Separato: il retrain guarda solo il backfill, l'atlante fallito resta una run ROSSA visibile col suo nome.
Costo: l'atlante non è più in sequenza PRIMA del retrain ma in parallelo al `plan`/`train` (entrambi partono alla
fine del Daily). L'atlante è incrementale (eventi oltre la filigrana) con tetto 30 min; il carico in parallelo al
retrain è da osservare alla prima notte (§7).
Step nuovo «Prerequisiti»: legge `hazard_atlas_leghe?select=league_id&limit=1` e l'ultima `hazard_atlas`; 404 →
`::error::Tabelle hazard_atlas / hazard_atlas_leghe ASSENTI sul DB: applicare migrations/hazard_atlas_2026-09-24.sql,
poi il bootstrap.`; tabella vuota o senza filigrana → `::error::Atlante mai inizializzato ... lanciare UNA volta il
bootstrap`; altro errore → traceback (rosso). Nessuna modifica a `Betfair/stream/**`.
Prova a secco (`prova_preflight_atlante.py`, finto PostgREST locale): `404 exit=1` messaggio migrazione;
`vuota exit=1` messaggio bootstrap; `ok exit=0 filigrana=123`; `500 exit=1 HTTPError 500`.

**M2 — `.github/workflows/daily_yesterday_backfill.yml`**: righe 33-64 (job `hazard-atlas`) → commento di 5 righe
che rimanda a `hazard_atlas.yml`; righe 8-12 nuove: `concurrency: group: daily-yesterday-backfill,
cancel-in-progress: false` (un lancio a mano non si sovrappone più al pianificato). Ora conclusion del Daily =
esito del solo backfill.

**M3 — `.github/workflows/ml_calibration.yml:42-49`**: job `assemble` con
`if: github.event_name != 'workflow_run' || github.event.workflow_run.conclusion != 'skipped'`. Retrain success o
failure (anche parziale: alcuni shard salvano modelli) → gira come prima; schedule (full) e dispatch invariati.

**M4 — `.github/workflows/retrain_models.yml:98-101`**: solo commento sul `plan.if` (logica invariata).

**M5 — `daily_yesterday_backfill.py:319-327`** (fallimento rumoroso). Prima: `APIFootballClient.call`
(`api_client.py:52,65,77,83,101`) ritorna `{}` su QUALUNQUE errore (HTTP, quota, JSON vuoto, rete) → lista vuota →
ramo «Nessun match FINISHED» → exit 0 VERDE senza scrivere nulla, e il retrain partiva a valle. Dopo: risposta
`/fixtures` vuota → `logger.error(...)` + `raise SystemExit("DAILY BACKFILL FALLITO: nessuna fixture dall'API per
<data>")` (exit 1). Con fixture presenti il flusso è identico (anche il caso «fixture presenti ma nessuna FINISHED»
resta un warning, invariato).

**M6 — `leagues_mapper.py`** (fallimento rumoroso, NESSUNA modifica alla logica di inserimento):
- `:30-34` lettura delle coppie esistenti fallita: prima `return pairs` (insieme VUOTO → tentava di reinserire tutte
  le ~8.700 coppie, errori «duplicate» ignorati, verde); dopo `raise RuntimeError(...)`.
- `upsert_coverage_rows` ora ritorna il numero di batch in errore NON previsto (`batch_errors - duplicate_residui`;
  i duplicati residui restano tollerati come prima); `return 0` nei rami «nessuna riga»/«DB già allineato».
- `run_full_leagues_backfill_mapping` (`:231-238`): `/leagues` vuoto → `SystemExit("LEAGUES MAPPER FALLITO: /leagues
  vuoto o in errore ...")`; batch in errore → `SystemExit("LEAGUES MAPPER FALLITO: N batch in errore NON previsto")`.

**Test nuovi**: `test_actions_fail_rumoroso_2026_09_25.py` (11 test, sandbox `SUPABASE_URL=http://127.0.0.1:9`
impostata DENTRO il file prima degli import, nessuna rete). Finti con chiavi/tipi del vero: risposta API-Football
`{"response": [...]}` con fixture `{"fixture": {"id", "status": {"short"}}, "league": {"id", "season"}, ...}` e lega
`{"league", "country", "seasons": [{"year", "start", "end", "current", "coverage": {"fixtures": {...}, ...}}]}`;
client supabase-py `table().select().range().execute().data` / `table().upsert(chunk).execute()`; il finto API ha la
stessa firma `call(endpoint, params=None, max_retries=3)` e ritorna `{}` come il vero sugli errori.
Esito: `11 passed`.

**Falsificazione** (`falsificazione_2026-09-25.txt`, ogni mutazione applicata al file vero e ripristinata; confronto
byte a byte dopo il ripristino: identico):

| Mutazione | Test rossi |
|---|---|
| M1 `if not fixtures_json:` → `if False:` (daily) | 3 (`test_daily_api_vuota_o_in_errore_esce_rosso[{}/[]/None]`) |
| M2 `raise RuntimeError(...)` → `return pairs` (mapper) | 1 (`test_mapper_lettura_coppie_fallita_esce_rosso_senza_scrivere`) |
| M3 `if errori:` → `if False:` | 1 (`test_mapper_batch_in_errore_non_previsto_esce_rosso`) |
| M4 `if not rows: raise` → `if False: raise` | 2 (`test_mapper_leagues_vuoto_esce_rosso[...]`) |
| M5 `return batch_errors - duplicate_residui` → `return batch_errors` | 1 (`test_mapper_duplicato_residuo_resta_tollerato`) |

YAML: `yaml.safe_load` su tutti i 9 file OK. `actionlint` NON installato sul PC (non eseguito). Lo script inline
dello step «Prerequisiti» è compilato ed eseguito dalla prova a secco.

## 4. Robustezza per il futuro — verifica punto per punto

- Job accessori: l'unico accessorio che poteva trascinare la catena era `hazard-atlas` → separato (M1). Gli step
  additivi di Results sono già `continue-on-error` con gate che rende rosso il run (voluto dal 21/09); lo step rho di
  Poisson idem.
- `workflow_run` a valle: Retrain guarda la conclusion del Daily, che ora = solo backfill (M2). Post-Cal guarda il
  Retrain: salta solo se skipped (M3). Catena `workflow_run` profonda 2 (Daily→Retrain→Post-Cal; Daily→Atlas):
  sotto il limite di GitHub (3).
- `concurrency`: tutte `cancel-in-progress: false`. Nota GitHub: in un gruppo resta UNA sola run in attesa; una
  terza run che arriva mentre una gira e una aspetta ANNULLA quella in attesa. Succede solo con lanci a mano ripetuti
  o con il `rechain` del retrain (che accoda un dispatch mentre il fallback pianificato è in attesa: stessa campagna,
  nessuna perdita). Aggiunto il gruppo al Daily (M2). Nessuna cancellazione per concorrenza negli ultimi 7 giorni.
- Timeout vs durate reali: Retrain train 330 min vs max 272,5 (run intera); Post-Cal 20 vs max 1,9; Atlas 30 (durata
  ignota, bootstrap dichiarato ~3 min); gli altri usano il default 360 min: Today max 253 min (recupero 19/09 a mano:
  4 h 04), Results max 112 min (fallite), Daily max 32 → margine ≥ 1,4×. Non modificati.
- Script che falliscono rumorosamente: Daily (M5) e mapper (M6) corretti; Today/Results/Retrain/atlante già fail-loud
  (registro anomalie, gate, riepilogo shard, `SystemExit("filigrana assente...")`). Post-Cal incrementale «niente da
  fare» è un esito legittimo quando il retrain ha girato senza modelli nuovi (run da 50 s con `has_work=false`).
- Segreti: nessuno mancante (§1).
- Cron: vedi §5 (causa esterna).

## 5. Azioni e decisioni per l'utente (cause esterne, NON aggirate)

1. **Migrazione** `migrations/hazard_atlas_2026-09-24.sql` (in corso secondo il coordinatore) e poi **bootstrap**
   dell'atlante UNA volta (comando nel referto del 24/09, ~3 min). Senza bootstrap la nuova action sarà rossa con
   «Atlante mai inizializzato» (chiaro, e non tocca più il retrain).
2. **Discrepanza in CRONOSTORIA 24/09**: dice «job notturno nel workflow NON montato (patch in scratchpad)… si monta
   dopo migrazione + bootstrap», ma `6070623` lo ha GIÀ montato in `daily_yesterday_backfill.yml` (è ciò che è
   fallito stanotte). Da correggere nella cronostoria.
3. **Ritardo del cron di GitHub** (misura su 30 giorni, tutti i workflow): mediana ~5 h, min 0,6 h, max 12 h. Gli
   orari 01:12 / 02:18 / 03:23 non separano davvero nulla: oggi Today è partita alle 07:56 UTC e Results partirà
   intorno alle 08:30 UTC, sovrapposte (Today dura ~66 min); il retrain, quando ha lavoro, gira 1-4,5 h da ~06:06 e si
   accavalla a entrambe (le 57014 del 19-23/09 sono nate proprio con più job sul DB). Opzioni (decisione dell'utente,
   nessuna applicata): (a) incatenare Today → Results con `workflow_run` (una parte solo quando l'altra ha finito)
   invece di due cron; (b) un avviatore esterno puntuale (`workflow_dispatch` via API da pg_cron/Supabase o da un
   servizio cron) = processo nuovo, serve permesso; (c) lasciare così, ora che gli script reggono il carico (Results
   verde il 24/09 anche con enrich 64 min).
4. **Retrain di oggi**: saltato due volte; lo recupera il fallback pianificato `19 8 * * *` (creazione attesa ~13:20
   UTC col ritardo mediano) oppure un dispatch manuale dopo il merge (vedi §7).
5. **Leagues mapper / coverage 2026** (solo diagnosi, §6).
6. Osservazione NON verificata oltre i log: il Daily del 25/09 ha ricevuto da `/fixtures?date=2026-09-24` solo 95
   fixture (90 FINISHED), contro 1.152 di domenica 20/09 e 205 di martedì 23/09. Può essere il calendario reale o un
   limite del piano API: da controllare con una lettura di `api_call_log`/pannello API-Football.

## 6. Leagues mapper e coverage della stagione 2026 (diagnosi)

- **Cosa fa** (`leagues_mapper.py`): una chiamata `/leagues` (tutte le leghe con tutte le stagioni e i flag di
  coverage) → righe `api_coverage_by_season` → legge le coppie esistenti (`:25-28`, `.range(0, 9999)`) → **inserisce
  SOLO le coppie (league_id, season_year) mancanti** (`:153-155` scarta le esistenti; docstring `:131-135` «Nessuna
  sovrascrittura»). **Quando**: il giorno 1 del mese, cron 00:12 UTC (reale ~05:00 UTC). Ultima run 33471969966
  (01/09): «Già presenti nel DB (skip): 8525 — NUOVE righe da inserire: 172».
- **Perché la coverage 2026 non si aggiorna**: la riga (lega, 2026) viene creata la prima volta che compare (spesso
  a luglio, a stagione non iniziata, quando API-Football ha ancora `events/lineups/statistics/odds = false`). Dopo,
  il mapper la considera «già presente» e non la tocca MAI più: i flag restano False per tutta la stagione anche
  quando API-Football li accende. Prova nei log del Daily di oggi: 42 letture di coverage su 68 con TUTTI i flag
  False (es. `league_id=253, season_year=2026 → {'events': False, ... 'odds': False}`), e 6 gruppi «Nessun coverage
  per league_id=1247/1159/1201/538/25 season=2026, 536 season=2025» (coppie non ancora inserite: arriveranno solo
  il 1° del mese successivo). `per_fixture_backfill.get_coverage_for_season` usa questi flag per decidere quali
  tabelle riempire → eventi/formazioni/statistiche/quote saltati.
- **Cosa servirebbe** (decisione dell'utente, nulla modificato nel merito): aggiornare i flag delle righe esistenti
  almeno per le stagioni `current=true` (upsert con sovrascrittura su (league_id, season_year), oggi escluso per
  scelta di progetto), e/o una cadenza più fitta (settimanale o in coda al Daily) per le stagioni correnti; poi un
  recupero degli eventi/statistiche/quote delle partite 2026 già saltate. Rischio latente: `.range(0, 9999)` legge
  al massimo 10.000 coppie (oggi ~8.700, +~170/mese → soglia in ~8 mesi): oltre, coppie esistenti sembrerebbero
  mancanti.

## 7. Piano di verifica per il coordinatore

Prerequisito: il file nuovo `hazard_atlas.yml` deve essere sul ramo di default (master): i trigger `workflow_run` e il
bottone dispatch valgono solo per i workflow presenti su master.
1. Rileggere il diff (`AUDIT_2026-09-25/actions_fix.patch`) e rilanciare
   `SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x python -m pytest test_actions_fail_rumoroso_2026_09_25.py -q -p no:cacheprovider`
   (atteso 11 verdi) e `python AUDIT_2026-09-25/prova_preflight_atlante.py` (attesi exit 1/1/0/1).
2. Dopo migrazione + bootstrap e merge: **UN solo lancio** `gh workflow run daily_yesterday_backfill.yml` a DB
   quieto (non mentre Today/Results girano). Attesi: Daily `success` con UN solo job (`run-backfill`); partono da sole
   «Retrain ML Models» (`workflow_run`, job `plan` ESEGUITO, log `[GATE] has_work=...`) e «Hazard Atlas» (log
   `[PRE] tabelle presenti, filigrana=N: procedo.` e poi il riepilogo JSON con `leghe_toccate`); a fine retrain parte
   «ML Post-Calibration» (success se il retrain ha girato; `skipped` solo se il retrain è skipped).
3. Controprova del disaccoppiamento (facoltativa): se l'atlante fosse rosso, il Retrain della stessa catena deve
   risultare comunque NON skipped (plan eseguito).
4. Notte successiva: `gh run list --limit 10` → Daily verde, Retrain `workflow_run` con plan eseguito, Hazard Atlas
   verde, Post-Cal coerente; confrontare durata dell'atlante e del retrain in parallelo (DB: nessuna 57014 nei log).
5. Il 1° ottobre: il mapper deve essere verde (o rosso con «LEAGUES MAPPER FALLITO ...» se l'API/DB falliscono).

## 8. Cosa NON ho potuto verificare

- Esecuzione reale su GitHub dei workflow modificati (vietato `gh workflow run`; il file nuovo va prima su master).
- `actionlint`: non installato.
- Durata reale dell'atlante incrementale e carico sul DB in parallelo al retrain: mai riuscito finora.
- Se la migrazione dell'atlante è già applicata e il bootstrap fatto: nessuna lettura del DB vero ammessa.
- Il conteggio basso di fixture del 24/09 (§5.6).
- Esito della run pianificata di oggi di Predictions Results Backfill: vedi risposta finale del delegato
  (ricontrollata all'ultimo momento).

## 9. File

Modificati: `.github/workflows/daily_yesterday_backfill.yml`, `.github/workflows/ml_calibration.yml`,
`.github/workflows/retrain_models.yml`, `daily_yesterday_backfill.py`, `leagues_mapper.py`.
Nuovi: `.github/workflows/hazard_atlas.yml`, `test_actions_fail_rumoroso_2026_09_25.py`,
`AUDIT_2026-09-25/ACTIONS_DIAGNOSI_E_FIX.md`, `AUDIT_2026-09-25/actions_fix.patch`,
`AUDIT_2026-09-25/falsificazione_2026-09-25.txt`, `AUDIT_2026-09-25/misure_action.py`,
`AUDIT_2026-09-25/prova_preflight_atlante.py`.
