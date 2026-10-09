# Orologio notturno delle action: referto (09/10/2026)

Cantiere: worktree `C:\Users\Admin\Desktop\PYTHON DATABASE\wt-orologio`, ramo `cantiere-orologio-notturno`
(da master `3bc6a698`). Niente commit, niente push, nessun workflow lanciato, DB non toccato.

## 0. Cosa cambia rispetto al brief (da leggere per primo)

**La catena NON puo' essere fatta con `workflow_run`.** La documentazione di GitHub
(*Events that trigger workflows*, sezione `workflow_run`) dice testualmente:

> "You can't use `workflow_run` to chain together more than three levels of workflows. For example,
> if you attempt to trigger five workflows (named `B` to `F`) to run sequentially after an initial
> workflow `A` has run (that is: `A` -> `B` -> `C` -> `D` -> `E` -> `F`), workflows `E` and `F` will not be run."

Con il Daily come `A`, partirebbero solo Retrain, Post-Calibration e Today Predictions. Hazard Atlas
e tutti gli anelli dopo **non partirebbero mai**, senza errori. Oggi la catena era lunga al massimo
2 livelli (Daily -> Leagues Mapping -> Catchup), per questo funzionava.

**Soluzione adottata: la "staffetta".** Ogni anello finisce con un job `passa-testimone` che lancia
il successivo con `workflow_dispatch` usando il `GITHUB_TOKEN` della run
(`.github/scripts/passa_testimone.sh`). Fonte (*Automatic token authentication / GITHUB_TOKEN*):

> "events triggered by the `GITHUB_TOKEN` will not create a new workflow run, with the following
> exceptions: `workflow_dispatch` and `repository_dispatch` events always create workflow runs."

E' lo stesso meccanismo che il Retrain usa gia' per rilanciarsi da solo (job `rechain`). Il resto
del brief e' rispettato: pg_cron lancia solo il primo anello, nessun cron GitHub, la regola
"parte se a monte NON e' stato annullato" (retrain: solo dopo un Daily `success`) e una catena in
fila, senza gruppi di concurrency condivisi.

In piu', rispetto al brief: ogni anello ha l'input `catena` (`false` di default). **Un lancio a
mano non trascina gli anelli a valle**, a meno di scegliere `catena=true`.

## 1. Progetto

```
pg_cron 00:12 UTC ──> lancia_action('daily_yesterday_backfill.yml')   [guardia: lanci_action]
                         │ POST /actions/workflows/daily_yesterday_backfill.yml/dispatches
                         │ {"ref":"master","inputs":{"catena":"true"}}
                         v
 1 Daily ─pt─> 2 Retrain ─pt─> 3 Post-Cal ─pt─> 4 Today ─pt─> 5 Hazard ─pt─> 6 Leagues
   ─pt─> 7 Catchup ─pt─> 8 Results ─pt─> 9 Weekly Poisson (calibra solo il lunedi')
 (pt = job passa-testimone: gh workflow run <prossimo> -f catena=true [...])

pg_cron 00:15 UTC ──> verifica_lancio_action()   -> live_alerts ACTION_NON_PARTITA se non 204/200
pg_cron 07:30 UTC ──> verifica_catena_notturna() -> GET /actions/runs?created=>=oggi&per_page=100
pg_cron 07:33 UTC ──> leggi_verifica_catena()    -> live_alerts CATENA_NOTTURNA_INCOMPLETA
```

Regole della staffetta, uguali in ogni anello (`if: ${{ !cancelled() && inputs.catena == 'true' }}`,
`needs:` = tutti gli altri job del workflow):
- un anello fallito passa comunque il testimone. E' come prima: Hazard e Leagues giravano anche col
  Daily fallito, e Today, Results e Poisson avevano cron indipendenti;
- un anello **annullato** a mano non passa il testimone e la catena si ferma;
- Retrain: il training parte solo con `monte_ok=true`, che il Daily passa quando
  `needs.run-backfill.result == 'success'` (stessa regola di `workflow_run.conclusion == 'success'`).
  Il gate "lavoro vero" del planner resta com'e';
- Post-Calibration: `retrain_eseguito=false` arriva quando il `plan` del Retrain e' stato saltato:
  il job `assemble` e' skipped, come prima. **Il lunedi' (UTC) nella catena** gira comunque e in
  modalita' **FULL** (job `giorno` + `FULL_SETTIMANALE`, decisione D3); negli altri giorni e'
  incrementale come oggi; a mano e' FULL solo con `completa=true`;
- Seasons Catchup: nella catena `CATCHUP_RISERVA_PER=predictions_results_backfill.yml`, quindi
  la quota API resta riservata SOLO per Predictions Results, che gira dopo (D1); lanciato a mano
  la variabile e' vuota e la riserva e' piena;
- Weekly Poisson: il job `giorno` legge `date -u +%u`. Dentro la catena `calibrate` gira solo il
  lunedi'; negli altri giorni e' skipped, con avviso nel riepilogo. Lanciato a mano
  (`catena=false`) gira sempre.

**Mai due lanci (dove e' garantito):**
- pg_cron: la PK `(giorno, workflow_file)` di `public.lanci_action` +
  `INSERT ... ON CONFLICT DO NOTHING`. Se la riga del giorno esiste gia', non parte nessuna chiamata
  (anche se il job viene eseguito due volte o lanciato a mano);
- staffetta: un solo `gh workflow run`. Se fallisce, dopo 90 s chiede a GitHub se una run del
  prossimo anello e' stata creata dopo l'inizio del passo. Se c'e', non rilancia; se non c'e', fa un
  solo nuovo tentativo; se lo stato non si legge, non rilancia (run rossa, catena ferma, allarme alle
  07:30);
- Retrain che si rilancia da solo (auto-chain): `rilanciato=true` viene scritto **prima** di
  `gh workflow run retrain_models.yml ...`. La run che si rilancia **non** passa il testimone; lo
  passa l'ultima run del giro, che eredita `catena`. Post-Calibration e gli anelli dopo partono
  **una volta sola**. Oggi invece `ml_calibration` partiva a ogni completamento del retrain:
  Post-Calibration girava N volte, ma niente a valle si raddoppiava, perche' Post-Calibration non
  aveva anelli a valle.

**Perche' la fila e' garantita senza un gruppo di concurrency condiviso:** un anello parte solo
quando il precedente ha finito tutti i suoi job (`needs:` = tutti i job). Il lavoro sul DB e' quindi
sempre uno alla volta. Ogni workflow tiene il suo gruppo, con `cancel-in-progress: false`. Un gruppo
condiviso sarebbe dannoso. Docs *Control workflow concurrency*: "By default, any existing `pending`
job or workflow in the same concurrency group will be canceled and the new queued job or workflow
will take its place." Con un gruppo solo, un lancio a mano o il rilancio del Retrain cancellerebbe un
anello in attesa. A Weekly Poisson, che non aveva un gruppo, ne ho aggiunto uno
(`weekly-poisson-calibration`, `cancel-in-progress: false`).

## 2. Orari attesi

Partenza alle 00:12 UTC (02:12 ora italiana d'estate, 01:12 d'inverno). Durate misurate (ultime 299
corse) **con 4-5 action in parallelo sul DB**: in fila ci aspettiamo tempi minori. Ogni passaggio di
testimone costa circa 0,5-1 min (stima mia, non misurata).

| # | Anello | mediana | max | fine cumulata (mediana) | fine cumulata (max) |
|---|---|---|---|---|---|
| 1 | Daily Yesterday Backfill | 10 | 32 | 00:22 | 00:44 |
| 2 | Retrain ML | 16 | 264 | 00:38 | 05:08 |
| 3 | ML Post-Calibration | 1 | (n.d., ~1) | 00:39 | 05:09 |
| 4 | **Today Predictions Backfill** | 67 | 410 | **01:46 UTC (03:46 it.)** | 11:59 |
| 5 | Hazard Atlas | 2 | 8 | 01:48 | 12:07 |
| 6 | Leagues Mapping | 2 | (n.d., ~2) | 01:50 | 12:09 |
| 7 | Seasons Catchup | 38 | 118 | 02:28 | 14:07 |
| 8 | Predictions Results Backfill | 73 | 113 | 03:41 | 16:00 |
| 9 | Weekly Poisson (lunedi') | 18 | n.d. | 03:59 | ~16:18 |

Today Predictions secondo il coordinatore: **mediana +94 min = 01:46 UTC**, **p90 +388 min =
06:40 UTC = 08:40 italiane**: pronte prima delle 09:00 anche al p90. I tempi lunghi di Today
Predictions (207-410 min) sono stati misurati con 4 action in parallelo sul DB; in fila ci
aspettiamo meno. Il "max" della tabella somma i peggiori casi, che non sono mai capitati insieme. Un
Retrain che si rilancia (fino a 8 giri da 240 min) puo' spostare tutto di ore: e' raro, ma va
dichiarato.

## 3. Diff per file

| File | Cosa |
|---|---|
| `.github/scripts/passa_testimone.sh` (nuovo) | staffetta: `gh workflow run <prossimo> --ref $GITHUB_REF_NAME -f catena=true [k=v]`, controllo anti-doppio e un solo ritentativo |
| `daily_yesterday_backfill.yml` | tolto `cron '12 1 * * *'`; input `catena`; job `passa-testimone` (r. 72-90) -> `retrain_models.yml` con `monte_ok` |
| `retrain_models.yml` | tolti `workflow_run` (Daily) e il fallback `cron "19 8 * * *"`; input `catena`, `monte_ok`; `plan.if` (r. 117) = `inputs.monte_ok != 'false'` (non cita piu' `schedule`); `rechain` con output `rilanciato` (r. 342), scritto prima del rilancio (r. 398), il rilancio eredita `catena`; `passa-testimone` (r. 412-431) -> `ml_calibration.yml`, non quando la run si e' rilanciata; corretta una descrizione che parlava di "cron" |
| `ml_calibration.yml` | tolti `workflow_run` e `cron "14 5 * * *"`; input `catena`, `retrain_eseguito`, `completa`; job `giorno` (r. 61-77, `date -u +%u`); `assemble` con `needs: giorno` e `if` (r. 91) = retrain non saltato OPPURE lunedi' nella catena; `FULL_SETTIMANALE` (r. 117) e `--full` se `completa=true` o lunedi' nella catena (r. 121); `passa-testimone` (r. 133: `needs: [giorno, assemble]`) -> `today_predictions_backfill.yml` |
| `today_predictions_backfill.yml` | tolto `cron '18 2 * * *'`; input `catena`; `passa-testimone` -> `hazard_atlas.yml` |
| `hazard_atlas.yml` | tolto `workflow_run` (Daily); input `catena`; tolto `if` (la regola "mai dopo un annullamento" ora sta nella staffetta); `passa-testimone` -> `leagues_mapper.yml` |
| `leagues_mapper.yml` | tolti `workflow_run` e il cron mensile `'12 0 1 * *'`; input `catena`; tolto `if`; `passa-testimone` -> `seasons_catchup.yml` |
| `seasons_catchup.yml` | tolti `workflow_run` (mapper) e `cron '47 13 * * *'`; input `catena`; tolto `if`; `CATCHUP_RISERVA_PER` (r. 100) = Results solo con `catena == 'true'`, altrimenti vuota; `passa-testimone` -> `predictions_results_backfill.yml` (la staffetta ha i suoi permessi `actions: write`, i permessi del workflow restano quelli) |
| `seasons_catchup.py` | D1, diff riga per riga nel par. 3.1 |
| `test_riserva_dinamica_2026_09_25.py` | D1: 4 test adattati + 9 nuovi (par. 4) |
| `predictions_results_backfill.yml` | tolto `cron '23 3 * * *'`; input `catena`; `passa-testimone` -> `weekly_poisson_calibration.yml` (passa anche se il gate "errori nascosti" rende la run rossa) |
| `weekly_poisson_calibration.yml` | tolto `cron '27 3 * * 1'`; input `catena`; `concurrency` nuova; job `giorno` (r. 32) e `calibrate.if` (r. 54) |
| `validate_models.yml` | **non toccato**: ha solo `workflow_dispatch`, nessun cron |
| `migrations/orologio_action_notturne_2026-10-09.sql` (nuovo) | tabella `lanci_action` (r. 100), aiuti (r. 121-170), `lancia_action` (r. 178), `verifica_lancio_action` (r. 255), `verifica_catena_notturna` (r. 339), `leggi_verifica_catena` (r. 389), revoke, 4 job pg_cron idempotenti (r. 506-529) |
| `tools/test_catena_action_2026_10_09.py` (nuovo) | 22 test |

Firma di pg_net verificata sul sorgente al tag `v0.19.5` (`sql/pg_net.sql` di
github.com/supabase/pg_net; gli aggiornamenti 0.19.1-0.19.5 non cambiano le firme; 0.19.3 rende solo
`headers` NULLable nella coda):
`net.http_post(url text, body jsonb default '{}', params jsonb default '{}', headers jsonb default
'{"Content-Type": "application/json"}', timeout_milliseconds int default 5000) returns bigint`;
`net.http_get(url text, params jsonb, headers jsonb, timeout_milliseconds int default 5000)`;
risposte in `net._http_response(id, status_code, content_type, headers, content, timed_out,
error_msg, created)`, conservate 6 ore (docs Supabase *pg_net*). Attenzione: la pagina Supabase dice
timeout di default 2000 ms, il sorgente 0.19.5 dice 5000. Io passo un timeout esplicito: 20000 ms
per il POST, 30000 per il GET. Siccome le intestazioni personalizzate sostituiscono quelle di
default, `Content-Type` e' scritto a mano.

Dispatch GitHub: senza `return_run_details` risponde 204, con `return_run_details=true` risponde 200
(GitHub Changelog del 19/02/2026, "Workflow dispatch API now returns run IDs"). La verifica accetta
entrambi.

### 3.1 `seasons_catchup.py`, diff riga per riga (righe del file nuovo)

- **r. 66-67**: l'import da `api_quota` aggiunge `leggi_riserva` e `leggi_riserva_residua` (gia'
  esistenti, non toccati).
- **r. 91-94** (nuove): costante `RISERVA_PER_ENV = "CATCHUP_RISERVA_PER"` con il commento.
- **r. 193-197**: docstring di `orario_cron`. Codice invariato: sui workflow veri, che non hanno piu'
  cron, ritorna None, quindi `action_completate_oggi` ritorna None. `main()` non le usa piu'.
- **r. 267-303** (nuove): `riserva_da_catena(env) -> (riserva, nota)`:
  - `CATCHUP_RISERVA_PER` assente, vuota o solo spazi/virgole: riserva **piena**
    (`API_FOOTBALL_RISERVA_GIORNALIERA`, 3000);
  - voci `file.yml` oppure `file.yml=N`, separate da virgole: riserva = residua
    (`API_FOOTBALL_RISERVA_RESIDUA`, 300) + somma delle voci. Una voce senza `=N` vale
    `ceil(piena / 3)` = 1000, cioe' la parte di un'action nella piena, che e' dimensionata per
    Daily, Today e Results. Il totale non supera mai la piena;
  - voce non valida: riserva piena con `AVVISO` (un refuso non abbassa mai la riserva).
- **r. 1227-1232** (`main`): prima `GestoreQuota(..., action_completate=concorrenza.action_completate_oggi)`,
  che leggeva gli orari dei cron; ora `riserva, nota = riserva_da_catena()`, stampa
  `[CATCHUP] <nota>` e `GestoreQuota(..., riserva=riserva)` (riserva fissa per la run).
  `ControlloConcorrenza` resta per l'attesa delle action concorrenti.

Effetto nella catena: riserva da 3000 a **1300** (300 + 1000 per Results), cioe' +1700 chiamate
disponibili al catchup. Le chiamate di Daily e Today sono gia' nel contatore `current` della quota.
Decisione su `''`: **vuota = piena**. Lanciato a mano (`catena=false`) il workflow passa proprio la
stringa vuota, e un lancio a mano non sa chi deve ancora girare.

## 4. Test e falsificazione

- `python -m pytest tools/test_catena_action_2026_10_09.py -q -p no:cacheprovider`: **22 passed**
  (+2 per D1 e D3: `test_post_calibration_full_il_lunedi_nella_catena`,
  `test_catchup_riserva_solo_per_results_nella_catena`; `test_post_calibration_salta...` aggiornato
  al nuovo `if`).
- `test_catchup_*.py`: **103 passed** (come il riferimento). `test_riserva_dinamica_2026_09_25.py`:
  **25 passed**. I 4 test che erano rossi sono stati adattati:
  - `test_cron_letti_dai_workflow_veri` diventa `test_workflow_veri_senza_cron_orario_none` (sui file
    veri `orario_cron` = None) + `test_cron_letti_dai_yaml_di_prova`;
  - gli altri 3 provano la logica di `action_completate_oggi` con YAML di prova che contengono i
    vecchi cron, letti dall'`orario_cron` VERO (sottoclasse che cambia solo la cartella);
  - 9 test nuovi su `riserva_da_catena`: assente, vuota (`''`, spazi, `,`), solo Results = 1300,
    `=N` e somma, tetto alla piena, voci non valide, piena e residua da env, `GestoreQuota` con
    riserva 1300 (margine 7500-5000-1300), `main` usa `riserva_da_catena` e non piu'
    `action_completate`.
- Tutti insieme (catena + `test_catchup_*` + riserva + backfill_automatico + 2 test dell'atlante):
  **246 passed**.
  - (1) nessun `schedule` e nessuna riga `cron:` viva in nessun workflow;
  - (2) la catena e' UNA linea: un successore e un predecessore al piu', testa = Daily, nessun ciclo,
    ordine = i 9 nell'ordine deciso; nessun `workflow_run` rimasto;
  - (3) ogni anello ha `workflow_dispatch` con `catena` (default `false`, opzione `true`);
  - (4) il prossimo anello esiste; la staffetta ha `!cancelled()`, `catena=='true'`, `needs` = tutti i
    job e `actions: write`, e usa `PROSSIMO_ANELLO`; l'eventuale `workflow_run` futuro deve citare
    nomi veri; l'elenco SQL `_orologio_catena()` coincide con la catena;
  - regole: concurrency per workflow con `cancel-in-progress: false` e gruppi distinti;
    retrain/`monte_ok`/`rilanciato` scritto prima del rilancio; Post-Cal/`retrain_eseguito`; Poisson
    il lunedi'; nessun `if` che citi `schedule` o `workflow_run`;
  - (5) migrazione: esattamente 4 `cron.schedule` (Daily + 3 verifiche, con orari e comandi
    esatti); `lancia_action` chiamata solo per il Daily; unschedule idempotente; guardia
    PK + `ON CONFLICT`; niente stringhe tipo token (`ghp_`, `github_pat_`, ...); file nuovi ASCII;
  - lo script della staffetta, eseguito con bash e un `gh` finto (stampa un intero come
    `--jq .total_count` del vero): lancio riuscito = 1 chiamata con `catena=true`; fallito ma run
    creata = nessun secondo lancio; fallito e run assente = un solo ritentativo (mai 3); stato
    illeggibile = nessun ritentativo, exit 1.
- **Falsificazione: 33 mutazioni su 33 rosse** (20 della prima consegna, con M18 aggiornata al nuovo
  `if`, + 13 di D1 e D3). Ogni mutazione e' stata ripristinata con lo sha256
  identico, e `git status` e' invariato prima e dopo:

| Mutazione | Test rosso |
|---|---|
| M1 cron rimesso nel Daily | `test_nessun_schedule...` |
| M2 Hazard salta un anello | `test_catena_una_linea...` |
| M3 ordine vecchio (Post-Cal -> Hazard) | `test_catena_una_linea...` |
| M4 `workflow_run` rimesso nel mapper | `test_nessun_workflow_run...` |
| M5 Today senza input `catena` | `test_ogni_anello_ha_dispatch...` |
| M6 staffetta del Catchup con `always()` | `test_prossimo_anello_esiste...` |
| M7 Retrain: `gh` prima di `rilanciato` | `test_retrain_regola...` |
| M8 Retrain allena anche col Daily fallito | `test_retrain_regola...` |
| M9 Retrain passa il testimone anche se si e' rilanciato | `test_retrain_regola...` |
| M10 pg_cron lancia anche Today | `test_migrazione_pg_cron...` |
| M11 token nel file SQL | `test_nessun_segreto...` |
| M12 ordine della catena vecchio nell'SQL | `test_elenco_sql...` |
| M13 script: rilancia senza controllare | `test_staffetta_fallita_ma_run_creata...` |
| M14 script: rilancia con stato illeggibile | `test_staffetta_stato_illeggibile...` |
| M15 script: senza `catena=true` | `test_staffetta_lancio_riuscito...` |
| M16 Poisson ogni giorno in catena | `test_weekly_poisson...` |
| M17 Results `cancel-in-progress: true` | `test_concurrency...` |
| M18 Post-Cal senza `if` (nuovo `if`) | `test_post_calibration...` |
| M19 Daily: `monte_ok` sempre true | `test_retrain_regola...` |
| M20 staffetta del Retrain senza `train` in `needs` | `test_prossimo_anello_esiste...` |
| N1 assente o vuota = residua invece di piena | `test_riserva_per_assente`, `..._vuota` |
| N2 parte per action = piena intera | `test_riserva_per_solo_results` |
| N3 senza tetto alla piena | `test_riserva_per_mai_sopra_la_piena` |
| N4 voce non valida = residua | `test_riserva_per_voce_non_valida...` |
| N5 residua dimenticata | `test_riserva_per_solo_results` |
| N6 `main` torna ad `action_completate` | `test_main_prende_la_riserva...` |
| N7 piena fissa a 3000, env ignorata | `test_riserva_per_segue_piena_e_residua_da_env` |
| N8 Results riservato anche a mano | `test_catchup_riserva_solo_per_results...` |
| N9 il lunedi' non va FULL | `test_post_calibration_full...` |
| N10 domenica invece di lunedi' | `test_post_calibration_full...` |
| N11 `if` vecchio (lunedi' saltato se retrain saltato) | `test_post_calibration_salta...` |
| N12 staffetta di Post-Cal non aspetta `giorno` | `test_prossimo_anello_esiste...` |
| N13 FULL settimanale anche fuori catena | `test_post_calibration_full...` |

- `actionlint 1.7.12` (release ufficiale rhysd/actionlint, scaricata nello scratchpad, `-shellcheck=`)
  sui 10 workflow: **0 errori**, come su master. Falsificato: `inputs.monte_okx` e
  `needs.rechain.outputs.rilanciatox` vengono segnalati (exit 1).
- SQL: analisi sintattica con `pglast` 8.5 (libpg_query) dei 23 statement e dei 7 corpi plpgsql:
  **0 errori**. Falsificato: un `IF` senza `END IF` viene segnalato. E' solo sintassi: la semantica
  (nomi di colonne, `cron.job`, `vault`) non e' verificata, vedi par. 6.
- Test esistenti: `test_atlante_v4_collegato` + `test_genera_atlante_scrittura_ritentativi`: 52
  passed; `test_backfill_automatico` e `test_catchup_*`: verdi; `test_riserva_dinamica`: verde
  (D1 risolto).

## 5. Istruzioni per l'utente

1. **Token**: GitHub -> Settings -> Developer settings -> Fine-grained tokens -> Generate. Solo il repo
   `python-database-automation`; Repository permissions -> **Actions: Read and write**; scadenza la
   piu' lunga ammessa (segnarsi la data).
2. **Vault**, nell'SQL editor di Supabase, a mano, mai nel repo:
   `select vault.create_secret('<TOKEN>', 'github_actions_dispatch', 'lancio notturno delle action');`
3. **Migrazione**: applicare `migrations/orologio_action_notturne_2026-10-09.sql`. In fondo stampa i 4
   job `orologio_*`.
4. **Ordine con il push**: i workflow nuovi devono essere su `master` **prima** delle 00:12 UTC della
   notte in cui la migrazione e' attiva. Se pg_cron lancia il Daily vecchio (senza input `catena`),
   GitHub risponde 422 ("Unexpected inputs"): allarme `ACTION_NON_PARTITA` alle 00:15, nessun danno.
   I cron vecchi pero' tacciono solo dopo il push.
5. **La mattina**:
   - `select * from public.lanci_action order by giorno desc, chiesto_at desc limit 20;`
     `esito_http` 204 = GitHub ha accettato il Daily. Nella riga `verifica_catena`: `esito_http` 200 e
     `errore` vuoto = 9 anelli ok; altrimenti `errore` contiene l'elenco.
   - `select id, level, code, message, created_at from public.live_alerts where code in ('ACTION_NON_PARTITA','CATENA_NOTTURNA_INCOMPLETA') order by created_at desc limit 20;`
     Gli avvisi compaiono anche nel banner dell'app (Realtime su `live_alerts`).
   - `select j.jobname, d.status, d.return_message, d.start_time from cron.job_run_details d join cron.job j on j.jobid = d.jobid where j.jobname like 'orologio%' order by d.start_time desc limit 20;`
6. **Lanci a mano** (da GitHub, Actions -> workflow -> Run workflow):
   - `catena=false` (default): gira **solo** quel workflow, gli anelli a valle non partono;
   - `catena=true`: quel workflow e **tutti gli anelli dopo**. In particolare, il Daily lanciato a mano
     con `catena=true` rifa' **tutta** la catena. Va fatto solo se quella notte la catena non e'
     partita o si e' fermata: la guardia di `lanci_action` protegge solo i lanci di pg_cron, non quelli
     a mano. Per riprendere una catena fermata all'anello N, lanciare N con `catena=true`;
   - il Retrain a mano ha in piu' `monte_ok` (lasciare `true`); Post-Calibration ha `retrain_eseguito`
     (lasciare `true`) e `completa` (`true` = modalita' FULL).
7. **Togliere l'orologio**: `select cron.unschedule(jobname) from cron.job where jobname like 'orologio%';`
8. **Token scaduto**: `select vault.update_secret((select id from vault.secrets where name='github_actions_dispatch'), '<NUOVO>');`

## 6. Cosa NON ho verificato

- **Niente e' stato provato dal vivo**: niente DB, niente lanci su GitHub. La prima prova vera e' la
  notte del primo giorno dopo push + migrazione. La mattina vanno lette `lanci_action`, `live_alerts`
  e la pagina Actions.
- La semantica dell'SQL su Postgres vero: `#variable_conflict use_column` in `lancia_action`, il nome
  del vincolo `lanci_action_pkey`, i permessi del proprietario su `vault.decrypted_secrets`, `net.*`,
  `cron.job`, e l'inserimento in `live_alerts` sotto RLS (il proprietario, `postgres`, salta la RLS
  perche' non e' FORCE). Ho controllato solo la sintassi.
- Che il campo `path` delle run nell'API sia `.github/workflows/<file>.yml`. Lo tolgo dopo una
  eventuale `@ref` con `split_part`, ma non l'ho osservato su questo repo.
- Che una catena di 8 `workflow_dispatch` consecutivi fatti con `GITHUB_TOKEN` non abbia un limite
  di profondita'. La documentazione non ne cita (il limite di 3 vale per `workflow_run`); il Retrain
  lo fa gia' fino a 8 volte, ma non ho letto da GitHub se ha mai superato 1 giro: il brief vieta di
  toccare GitHub.
- Che un job andato in **timeout** (`timeout-minutes`) lasci `cancelled()` falso, quindi che la
  staffetta passi comunque. Atteso, ma non verificato; nel caso peggiore la catena si ferma e la
  verifica delle 07:30 lo segnala.
- Che i file `GITHUB_OUTPUT` di uno step fallito vengano letti, cioe' che `rilanciato=true` resti
  valido se `gh workflow run` del Retrain fallisce. Nel caso peggiore il testimone passa e il
  rilancio non c'era, quindi niente doppio.
- Il permesso esatto del token fine-grained per dispatch e lettura delle run: "Actions: Read and
  write" viene dalla prassi, la pagina REST scaricata non mostrava il riquadro dei permessi.
- Che i lanci `workflow_dispatch` via API non subiscano il ritardo dello scheduler di GitHub (quello
  vale per `schedule:`): e' atteso, non misurato.
- `main()` del Catchup con la riserva nuova non e' stato eseguito per intero: richiede DB e API.
  Ho verificato il collegamento leggendo il sorgente (test `test_main_prende_la_riserva...`) e il
  comportamento con `GestoreQuota(riserva=1300)` reale e finti. La riga
  `[CATCHUP] riserva per le action che devono ancora girare oggi (...) = 1300` va letta nel log
  della prima notte.
- Quante chiamate API usa davvero Predictions Results (la parte di 1000 e' derivata, D1).
- La suite `Betfair/` completa non e' stata rilanciata. Non tocco codice Python di produzione; i
  test che leggono i workflow sono stati rilanciati (par. 4).

## 7. Decisioni aperte (per l'utente / il coordinatore)

- **D1 - RISOLTO (indicazione del coordinatore)**: riserva del Catchup da `CATCHUP_RISERVA_PER`
  (par. 3.1). Nella catena: 1300 = 300 + 1000 per Results. **Da confermare**: la parte di 1000 per
  Results e' **derivata** (3000 / 3), non misurata. `api_call_log` non registra quale workflow ha
  fatto la chiamata, per cui la misura si fa per finestra oraria della run di Results. Se serve un
  valore diverso basta scriverlo nel workflow (`predictions_results_backfill.yml=N`), senza toccare
  il codice.
- **D2 - DECISO dall'utente: NESSUNA finestra di giorno per il Catchup** (di giorno l'app e' accesa).
  La seconda finestra delle 13:47 UTC resta tolta; il Catchup gira una volta per notte, nella catena.
- **D3 - RISOLTO (indicazione del coordinatore)**: Post-Calibration FULL una volta a settimana dentro la
  catena, il lunedi' (giorno UTC del runner), anche se il retrain a monte e' stato saltato; negli altri
  giorni incrementale come prima; a mano FULL con `completa=true`.
- **D4 - fallback del Retrain alle 08:19 UTC e cron mensile del Mapper tolti**: con la staffetta non
  servono (un passaggio fallito lascia la run rossa e scatta l'allarme delle 07:30).
- **D5 - nessun taglio orario** (decisione dell'utente): con le mediane la catena finisce verso le
  03:41 UTC (03:59 il lunedi'); sommando i massimi verso le 16:00 UTC, con l'app accesa ma un solo
  lavoro per volta sul DB.
- **D6 - nome di Hazard Atlas**: e' rimasto "Hazard Atlas (notturno, dopo il Daily)", ma ora gira
  dopo Today Predictions. Non l'ho rinominato: e' citato in AUDIT e test; il file e' quello che conta
  per la staffetta.
- **D7 - token nella coda di pg_net**: l'intestazione `Authorization` resta qualche secondo in
  `net.http_request_queue` (tabella unlogged, schema `net`, non esposta ad anon/authenticated) finche'
  il worker la manda. E' il funzionamento standard di pg_net; il token non viene mai scritto nelle
  nostre tabelle.

## 8. Blocco per `CRONOSTORIA.md` (da incollare a cura del coordinatore)

```
### Checkpoint - orologio notturno delle action (09/10/2026, delegato Opus, worktree wt-orologio)
- Reperto: la catena con workflow_run NON puo' superare 3 livelli (docs GitHub): Hazard e
  successivi non sarebbero mai partiti. Adottata la STAFFETTA: job passa-testimone in ogni anello
  (workflow_dispatch con GITHUB_TOKEN, .github/scripts/passa_testimone.sh), input catena (false a
  mano, true da pg_cron e dalla staffetta).
- Catena: Daily -> Retrain -> Post-Cal -> Today -> Hazard -> Leagues -> Catchup -> Results ->
  Weekly Poisson (solo lunedi'). Nessun cron GitHub nel repo (9 workflow toccati, validate_models no).
- Migrazione DA APPLICARE (utente, dopo token nel Vault e DOPO il push dei workflow):
  migrations/orologio_action_notturne_2026-10-09.sql: lanci_action (guardia), lancia_action,
  verifica_lancio_action (00:15), verifica_catena_notturna (07:30) + leggi_verifica_catena (07:33),
  pg_cron orologio_daily 00:12 UTC.
- Test: tools/test_catena_action_2026_10_09.py 22/22; test_catchup_*.py 103/103;
  test_riserva_dinamica 25/25; insieme 246 passed; falsificazione 33/33 rosse, ripristino sha
  identico; actionlint 0 errori; pglast 0 errori di sintassi SQL.
- D1: riserva del Catchup da CATCHUP_RISERVA_PER (seasons_catchup.riserva_da_catena; nella catena
  1300 = 300 + 1000 per Results, la parte 1000 e' derivata da 3000/3: da misurare). D2: deciso,
  nessuna finestra di giorno. D3: Post-Cal FULL il lunedi' nella catena.
- APERTO: misura della quota di Results (parte di 1000 derivata); D5 nessun taglio orario.
- Ripresa: revisione del coordinatore sul worktree; poi commit su percorsi espliciti, push,
  token + Vault + migrazione; la mattina dopo leggere lanci_action e live_alerts.
```
