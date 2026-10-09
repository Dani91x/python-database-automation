# Ordine definitivo della catena notturna (09/10/2026)

Cantiere: worktree `C:\Users\Admin\Desktop\PYTHON DATABASE\wt-ordine`, ramo `cantiere-ordine-catena`
(da master `a38a7eb6`). Delegato Opus. Niente commit, niente push, nessun workflow lanciato,
DB non toccato, checkout principale non toccato, `.github/scripts/passa_testimone.sh` non toccato
(nell'indice resta LF).

Nota sul percorso: il primo brief chiedeva Daily -> Retrain -> Post-Cal -> Leagues -> Today -> ...;
a lavoro in corso il coordinatore ha mandato l'ordine aggiornato qui sotto, che lo sostituisce. I
file sono stati rimessi come su master e rifatti da zero con l'ordine nuovo. Del primo giro restano
solo i test che servono anche ora: coppie lette dai file veri, commenti allineati, input passati
all'anello giusto.

## 1. Ordine e motivo

```
1 Daily Yesterday Backfill -> 2 Leagues Mapping -> 3 Today Predictions Backfill
-> 4 Predictions Results Backfill -> 5 Hazard Atlas -> 6 Seasons Catchup
-> 7 Retrain ML -> 8 ML Post-Calibration -> 9 Weekly Poisson Calibration (solo lunedi')
```

Motivo (tabelle verificate dal coordinatore; io ho ricontrollato le prime due):
- Today legge `api_coverage_by_season` (`Prediction/today_predictions_backfill.py`,
  `predictions_coverage_true` / `odds_coverage_true`) e il mapper la scrive (`leagues_mapper.py`,
  `.upsert(chunk)`).
- Hazard e Catchup leggono i dati del Daily.
- Il Retrain allena anche sulle partite chiuse dal Catchup.
- Weekly Poisson legge gli esiti scritti da Results.

Staffette (`PROSSIMO_ANELLO`), prima -> ora:

| anello | prima (master) | ora |
|---|---|---|
| Daily | `retrain_models.yml` | `leagues_mapper.yml` |
| Leagues Mapping | `seasons_catchup.yml` | `today_predictions_backfill.yml` |
| Today | `hazard_atlas.yml` | `predictions_results_backfill.yml` |
| Results | `weekly_poisson_calibration.yml` | `hazard_atlas.yml` |
| Hazard | `leagues_mapper.yml` | `seasons_catchup.yml` |
| Catchup | `predictions_results_backfill.yml` | `retrain_models.yml` |
| Retrain | `ml_calibration.yml` | `ml_calibration.yml` (invariata) |
| Post-Cal | `today_predictions_backfill.yml` | `weekly_poisson_calibration.yml` |
| Weekly | (ultimo) | (ultimo) |

## 2. Input fra anelli

**(a) `monte_ok`.** Il Daily lo calcola ancora con `MONTE_OK: ${{ needs.run-backfill.result == 'success' }}`.
Adesso lo dichiarano tutti e 9 gli anelli, come stringa con default `"true"`. Fa eccezione il
Retrain, che tiene la sua dichiarazione di prima (`choice` `true`/`false`, default `"true"`). Non
l'ho cambiata in stringa: accetta gli stessi valori e il test esistente sul Retrain resta com'e'.
Ogni staffetta lo inoltra:
`MONTE_OK: ${{ inputs.monte_ok || 'true' }}` + `passa_testimone.sh "$PROSSIMO_ANELLO" monte_ok="$MONTE_OK"`.
Ho usato una variabile env invece di `${{ }}` dentro `run:`, come gia' fa il Daily: niente
espressioni nel testo della shell. Il Retrain lo legge come prima
(`plan.if: inputs.monte_ok != 'false'`) e lo inoltra anche lui, a Post-Cal e poi a Weekly, che lo
dichiarano senza usarlo. Senza questo, Retrain e Post-Cal risponderebbero 422 a un input non
dichiarato. Il rilancio automatico del Retrain passa ancora `monte_ok=true`: rilancia solo se il
plan ha girato, quindi `monte_ok` non era `false`. Il Daily dichiara `monte_ok` come gli altri, ma
non lo usa: l'orologio pg_cron gli passa solo `catena`.

Chiavi passate, controllate leggendo i YAML veri:

| anello | passa a | chiavi (oltre a `catena=true`) | dichiarate dal prossimo |
|---|---|---|---|
| Daily | Leagues | `monte_ok` (dal risultato del job) | si' |
| Leagues | Today | `monte_ok` | si' (`date` default vuoto) |
| Today | Results | `monte_ok` | si' (`date`, `leagues` default vuoti) |
| Results | Hazard | `monte_ok` | si' |
| Hazard | Catchup | `monte_ok` | si' |
| Catchup | Retrain | `monte_ok` | si' |
| Retrain | Post-Cal | `retrain_eseguito`, `monte_ok` | si' |
| Post-Cal | Weekly | `monte_ok` | si' |

Nessun input e' obbligatorio senza default. Il numero di input per workflow resta sotto 10
(Retrain 9, invariato).

**(b) Riserva del Catchup.** Ho controllato chi chiama API-Football dopo il Catchup, seguendo con
uno script AST tutti gli import locali, anche indiretti, degli script che ogni workflow lancia:
- `cloud_retrain_shard.py`, `retrain_all_leagues.py` (lanciato con subprocess), `training_planner.py`,
  `compute_ml_post_calibration.py`, `generate_dynamic_cal.py`, `update_poisson_calibration.py`:
  **nessun** `api_client` / `api_quota`.
- **Eccezione da sapere: `generate_dc_rho.py` (Weekly Poisson) importa `api_client` in modo
  indiretto.** Fa `from Prediction.today_predictions_backfill import DC_RHO, ...` e quel modulo
  importa `APIFootballClient`. Pero' si limita a importare la classe: il client si crea solo in
  `run_for_date` (r. 2404), che `generate_dc_rho` non chiama. In piu' Retrain, Post-Cal e Weekly
  non hanno `API_FOOTBALL_KEY` nell'env. Conclusione: dopo il Catchup **nessuna chiamata** ad
  API-Football. L'affermazione "non importano api_client" e' vera per Retrain e Post-Cal, non alla
  lettera per Weekly.
- Results (`Prediction/predictions_results_backfill.py` e i 5 script additivi): nessun client
  API-Football fra gli import. Pero' il workflow gli passa ancora `API_FOOTBALL_KEY` nell'env
  (r. 86): non lo usa, l'ho lasciato com'e' (passo di esecuzione, fuori dal mio perimetro).

Quindi:
- `seasons_catchup.yml`: `CATCHUP_RISERVA_PER: ${{ inputs.catena == 'true' && 'nessuna' || '' }}`,
  con il commento aggiornato.
- `seasons_catchup.py`: toccata solo `riserva_da_catena`, piu' la costante
  `RISERVA_PER_NESSUNA = "nessuna"` accanto a `RISERVA_PER_ENV`, e la docstring aggiornata:
  - `nessuna` (anche con spazi intorno) -> `(residua, "...: riserva solo residua 300")`, senza
    AVVISO;
  - `nessuna` insieme ad altre voci (`nessuna,x.yml`, `nessuna,nessuna`) -> riserva piena con
    AVVISO;
  - refusi (`nesuna`, `Nessuna`, `NESSUNA`, `nessuna=0`) -> riserva piena con AVVISO, perche' non
    passano la regex delle voci;
  - assente o vuota -> piena, come prima.
  Effetto nella catena: la riserva passa da 1300 a **300**, cioe' 1000 chiamate in piu' per il
  Catchup.

**(c)** `retrain_eseguito` da Retrain a Post-Cal e' invariato. `ml_calibration.yml` lo usa come prima.

## 3. Diff per file

Tutti i file: CRLF conservati nella copia di lavoro (`core.autocrlf=true`, indice LF), 0 LF nudi,
0 righe aggiunte non ASCII.

**In tutti e 9 i workflow:**
- Il blocco "Catena notturna IN FILA" sotto `on:` ha l'ordine nuovo (3 righe) piu' 4 righe di
  motivo (tabelle e `monte_ok`; "Dopo il Catchup nessuno chiama API-Football").
- Input `monte_ok` aggiunto subito dopo `catena`. Fa eccezione il Retrain, che lo aveva gia'.

Per file:
- `daily_yesterday_backfill.yml`: il commento della staffetta dice che `monte_ok` viene inoltrato
  fino al Retrain (7o anello). Nome del passo e `PROSSIMO_ANELLO` -> `leagues_mapper.yml`.
- `leagues_mapper.yml`: commento di testa "SECONDO anello (lo lancia il Daily), PRIMA di Today".
  Staffetta -> `today_predictions_backfill.yml`, con inoltro di `monte_ok`.
- `today_predictions_backfill.yml`: "TERZO anello: lo lancia Leagues Mapping ... dopo che il mapper
  ha aggiornato i flag". Staffetta -> `predictions_results_backfill.yml`, con inoltro.
- `predictions_results_backfill.yml`: "QUARTO anello: lo lancia Today Predictions". Il commento
  del gate dice "solo un annullamento ferma la catena" (prima citava il vecchio cron di Weekly).
  Staffetta -> `hazard_atlas.yml`, con inoltro.
- `hazard_atlas.yml`: "QUINTO anello: lo lancia Predictions Results". Staffetta ->
  `seasons_catchup.yml`, con inoltro. Nome del workflow non cambiato (D6).
- `seasons_catchup.yml`:
  - r. 6: la catena storica e' marcata "(dal 25/09 al 09/10; ordine attuale sotto)";
  - commento di testa: "SESTO anello: lo lancia Hazard Atlas", con la riserva spiegata (prima
    Daily/Today/Results, dopo nessuno che chiami API-Football);
  - `CATCHUP_RISERVA_PER` = `'nessuna'` nella catena;
  - staffetta -> `retrain_models.yml`, con inoltro.
- `retrain_models.yml`: commento "SETTIMO anello ... lo lancia Seasons Catchup ... monte_ok
  inoltrato da ogni anello, cosi' allena anche sulle partite chiuse dal Catchup". La staffetta
  aggiunge `MONTE_OK` e `monte_ok="$MONTE_OK"` dopo `retrain_eseguito`. `PROSSIMO_ANELLO`
  invariato.
- `ml_calibration.yml`: "OTTAVO anello". Staffetta -> `weekly_poisson_calibration.yml`, con
  inoltro.
- `weekly_poisson_calibration.yml`: "lo lancia ML Post-Calibration". Solo l'input in piu', nessuna
  staffetta.

`migrations/orologio_action_notturne_2026-10-09.sql`:
- nota in testa, nuova: cambia solo l'ordine di `_orologio_catena()` e del commento. Ri-applicare
  e' **facoltativo**: la verifica delle 07:30 cerca la run di oggi di ognuno dei 9 anelli
  (`FOREACH ... LOOP`, una ricerca per file) e **non dipende dall'ordine**, che cambia solo l'ordine
  dei nomi nel testo dell'allarme. Il file e' idempotente;
- commento della catena con l'ordine nuovo;
- elenco `ARRAY[...]` nell'ordine nuovo (stessi 9 nomi).

`seasons_catchup.py`, `test_riserva_dinamica_2026_09_25.py`: vedi par. 2(b). I test nuovi sono
`test_riserva_per_nessuna_solo_residua` e `test_riserva_per_nessuna_refusi_riserva_piena_con_avviso`.

`tools/test_catena_action_2026_10_09.py`:
- `CATENA` nell'ordine nuovo, col motivo nel commento;
- nuovo `test_ordine_definitivo_coppie_e_dipendenze`: le 9 coppie scritte una per una e lette dai
  `PROSSIMO_ANELLO` veri, piu' la dipendenza mapper -> Today presente nel codice;
- nuovo `test_commenti_dell_ordine_allineati`: le 3 righe d'ordine nuove ci sono nei 9 workflow e
  nella migrazione, 4 frammenti dell'ordine vecchio non ci sono in nessuno;
- nuovo `test_input_passati_arrivano_all_anello_giusto`: chiavi esatte per anello, ognuna
  dichiarata dal prossimo;
- nuovo `test_monte_ok_inoltrato_fino_al_retrain`: tutti e 9 dichiarano `monte_ok` con default
  `true`; il Daily lo calcola dal job; ogni anello fra Daily e Retrain lo inoltra con
  `inputs.monte_ok`; il cammino Daily -> Retrain coincide con la catena; `plan.if` del Retrain;
- `test_catchup_riserva_solo_per_results...` sostituito da `test_catchup_riserva_nessuna_nella_catena`:
  `'nessuna'` nella catena, dopo il Catchup solo Retrain, Post-Cal e Weekly, nessuno dei tre con
  `API_FOOTBALL_KEY`, e `riserva_da_catena('nessuna')` uguale alla residua.

`AUDIT_2026-10-09/orologio_action/REFERTO.md`: nota in testa, diagramma del par. 1 (in ASCII),
tabella degli orari, frase su Today e Results.

## 4. Orari attesi (durate del referto, partenza 00:12 UTC)

| # | Anello | mediana | max | fine cumulata (mediana) | fine cumulata (max) |
|---|---|---|---|---|---|
| 1 | Daily Yesterday Backfill | 10 | 32 | 00:22 | 00:44 |
| 2 | Leagues Mapping | 2 | ~2 | 00:24 | 00:46 |
| 3 | **Today Predictions Backfill** | 67 | 410 | **01:31 UTC (03:31 it.)** | 07:36 |
| 4 | **Predictions Results Backfill** | 73 | 113 | **02:44 UTC (04:44 it.)** | 09:29 |
| 5 | Hazard Atlas | 2 | 8 | 02:46 | 09:37 |
| 6 | Seasons Catchup | 38 | 118 | 03:24 | 11:35 |
| 7 | Retrain ML | 16 | 264 | 03:40 | 15:59 |
| 8 | ML Post-Calibration | 1 | ~1 | 03:41 | 16:00 |
| 9 | Weekly Poisson (lunedi') | 18 | n.d. | 03:59 | ~16:18 |

- Today: mediana +79 min (prima +94).
- Results: mediana +152 min = 02:44 UTC, come indicato dal coordinatore.
- Fine della catena: invariata (03:41 UTC, 03:59 il lunedi').
- Ogni passaggio di testimone costa 0,5-1 min: e' una stima, non e' nella tabella.
- Il p90 di Today non e' stato ricalcolato: non ho le durate al p90 per anello.

## 5. Test

- Test nuovo sui file **vecchi**. In una cartella dello scratchpad ho messo la copia di master
  `a38a7eb6` di workflow, script, migrazione, Today, mapper, `seasons_catchup.py` e `api_quota.py`,
  con il test nuovo: **7 failed, 19 passed** (`una_linea`, `ordine_definitivo_coppie`, `commenti`,
  `input_passati`, `monte_ok_inoltrato`, `elenco_sql`, `catchup_riserva_nessuna`).
- Test sui file **nuovi**: `tools/test_catena_action_2026_10_09.py` **26 passed**.
- `test_riserva_dinamica_2026_09_25.py`: **27 passed** (25 + 2).
- Insieme: catena, `test_catchup_*.py` (6 file), riserva, `test_backfill_automatico_2026_09_25.py`,
  `test_atlante_v4_collegato_2026_09_25.py` e `test_genera_atlante_scrittura_ritentativi_2026_09_28.py`:
  **252 passed**.
- `actionlint 1.7.12 -shellcheck=` sui 10 workflow: **0 errori** (exit 0).

## 6. Falsificazione: 23 mutazioni su 23 rosse

Metodo: ogni mutazione va sul file vero, poi girano i due file di test, poi il file torna ai byte
originali. Gli sha256 dei 14 file del diff sono identici prima e dopo, e `git status --short` e'
identico.

| Mutazione | Test rossi |
|---|---|
| G1 Daily -> Retrain (vecchio) | `una_linea`, `coppie`, `monte_ok_inoltrato` |
| G2 Mapper -> Catchup (vecchio) | `una_linea`, `coppie`, `monte_ok_inoltrato` |
| G3 Today -> Hazard (salta Results) | `una_linea`, `coppie`, `monte_ok_inoltrato` |
| G4 Results -> Weekly (vecchio) | `una_linea`, `coppie`, `monte_ok_inoltrato` |
| G5 Hazard -> Mapper (ciclo) | `una_linea`, `coppie`, `monte_ok_inoltrato` |
| G6 Catchup -> Results (vecchio) | `una_linea`, `coppie`, `monte_ok_inoltrato` |
| G7 Post-Cal -> Today (vecchio) | `una_linea`, `coppie` |
| G8 SQL: Retrain secondo | `elenco_sql` |
| G9 SQL: Results e Hazard scambiati | `elenco_sql` |
| G10 Hazard non inoltra `monte_ok` | `input_passati`, `monte_ok_inoltrato` |
| G11 Catchup inoltra `monte_ok` fisso `'true'` | `monte_ok_inoltrato` |
| G12 Today senza input `monte_ok` | `input_passati`, `monte_ok_inoltrato` |
| G13 Mapper: `monte_ok` default `false` | `monte_ok_inoltrato` |
| G14 Retrain non passa `retrain_eseguito` | `input_passati` |
| G15 Weekly senza input `monte_ok` | `input_passati`, `monte_ok_inoltrato` |
| G16 Catchup riserva ancora per Results | `catchup_riserva_nessuna` |
| G17 Catchup `'nessuna'` anche a mano | `catchup_riserva_nessuna` |
| G18 `riserva_da_catena`: `nessuna` = piena | `catchup_riserva_nessuna`, `riserva_per_nessuna_solo_residua` |
| G19 `nessuna` con altre voci accettata | `riserva_per_nessuna_refusi...` |
| G20 parola riservata maiuscola | `catchup_riserva_nessuna`, `solo_residua`, `refusi` |
| G21 commento vecchio in Results | `commenti` |
| G22 commento vecchio nella migrazione | `commenti` |
| G23 `API_FOOTBALL_KEY` nel Retrain | `catchup_riserva_nessuna` |

Nel primo giro una mutazione era rimasta verde: il Retrain passava l'input sbagliato al prossimo
anello e nessun test se ne accorgeva. E' chiusa da `test_input_passati_arrivano_all_anello_giusto`.

## 7. Non verificato

- **Niente e' stato provato dal vivo**: nessun workflow lanciato, nessun DB. La catena di prova in
  corso su GitHub gira con l'ordine di master, il nuovo vale dal push. Il push va fatto a catena
  di prova finita: un anello vecchio che lancia un anello nuovo funziona (gli input in piu' hanno
  un default), ma il contrario darebbe 422 (`monte_ok` non dichiarato).
- La migrazione non e' stata analizzata con `pglast` in questo cantiere: il modulo non e' nel
  `.venv` e nessun Python locale lo ha. Cambiano solo l'ordine dei letterali dell'ARRAY e dei
  commenti; la sintassi era stata verificata nella prima consegna.
- `riserva_da_catena` e' provata con unit test. `main()` del Catchup con `nessuna` non e' stato
  eseguito per intero (servono DB e API). La prima notte va letta nel log la riga
  `[CATCHUP] CATCHUP_RISERVA_PER=nessuna: ... riserva solo residua 300`.
- Il controllo degli import e' statico (AST, import locali). Un import dinamico per stringa non
  si vedrebbe. Ho cercato `importlib`, `__import__` e `runpy` negli script a valle: nessuno.
  Unico `subprocess`: `cloud_retrain_shard` -> `retrain_all_leagues.py`, controllato.
- Le tabelle lette e scritte da Results, Hazard, Catchup, Retrain e Weekly sono quelle dichiarate
  dal coordinatore. Io ho riletto solo `api_coverage_by_season` (Today legge, mapper scrive) e gli
  import di API-Football.
- Se un anello in mezzo fallisce, la staffetta passa comunque (regola della prima consegna).
  `monte_ok` resta quello del Daily: un Catchup fallito non ferma il Retrain. Non cambiato.
- La suite `Betfair/` completa non e' stata rilanciata.
- Il lavoro dell'altro delegato (file Python dei workflow e passi di esecuzione) non l'ho visto.
  Le mie righe toccano blocchi di testa, input, passi della staffetta e, in un solo passo di
  esecuzione, `CATCHUP_RISERVA_PER` del Catchup, piu' il suo commento. Li' e' possibile un
  conflitto all'unione.

## 8. Blocco per `CRONOSTORIA.md`

```
### Checkpoint - ordine DEFINITIVO della catena notturna (09/10/2026, delegato Opus, worktree wt-ordine)
- Ordine (coordinatore, sulle tabelle lette/scritte): Daily -> Leagues Mapping -> Today ->
  Results -> Hazard -> Catchup -> Retrain -> Post-Cal -> Weekly Poisson (lunedi').
  Staffette cambiate: tutte tranne Retrain->Post-Cal.
- monte_ok (esito del Daily) dichiarato in tutti i 9 anelli (stringa, default true; il Retrain
  tiene la sua choice) e inoltrato da ogni staffetta fino al Retrain (e oltre, a Post-Cal e Weekly).
- Catchup: CATCHUP_RISERVA_PER='nessuna' nella catena -> riserva sola residua 300 (prima 1300);
  seasons_catchup.riserva_da_catena: 'nessuna' = residua, mista o refuso = piena con AVVISO.
  Dopo il Catchup nessuna chiamata ad API-Football (verificato con AST; generate_dc_rho importa
  api_client indirettamente ma non crea il client e Weekly non ha la chiave).
- Migrazione: solo l'ordine di _orologio_catena() + nota; ri-applicare FACOLTATIVO.
- Orari (mediane): Today 01:31 UTC (03:31 it.), Results 02:44 UTC, fine 03:41 (lunedi' 03:59).
- Test: catena 26/26 (file vecchi: 7 rossi); riserva 27/27; insieme 252 passed; actionlint 0;
  falsificazione 23/23 rosse.
- Referti: AUDIT_2026-10-09/orologio_action/ORDINE_DEFINITIVO.md (+ REFERTO.md aggiornato).
- Ripresa: revisione del coordinatore su wt-ordine; unione con l'altro delegato (possibile
  conflitto su CATCHUP_RISERVA_PER in seasons_catchup.yml); commit su percorsi espliciti; push
  SOLO a catena di prova finita.
```
