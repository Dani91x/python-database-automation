# Diagnosi GitHub Actions al 04/10/2026 (ore 09:45 UTC) - SOLA LETTURA

Delegato Sonnet 5.5. Nessun rilancio, nessun push/commit, nessun file tracciato toccato, DB solo `SELECT` leggeri.
Periodo: 20/09 - 04/10/2026 (14 giorni + oggi), fonte `gh run list --limit 500` (180 run) e `gh run view --log(-failed)`.
Lettura tabella: `s`=schedule, `r`=workflow_run, `d`=workflow_dispatch; `ok/KO/skip/can`; numero = minuti da startedAt a updatedAt.

## 0. Risposta breve (senza addolcire)

1. **Il 57014 (timeout Supabase) di 20-24/09 e' davvero sparito** da Retrain, Today, Results: 0 occorrenze di `statement timeout` nelle run verdi del 02-04/10 (Today 37109100272 e 36985187944, Results 37112481621, Retrain 37103519100). Results 10/10 verdi dal 25/09, Today senza KO dal 24/09, Retrain senza KO dal 22/09 (ultimo KO 21/09).
2. **Ma le action NON sono "tutte a posto"**: dal 25/09 sono nati componenti nuovi e i rossi vecchi sono stati SOSTITUITI da rossi nuovi:
   - **Monthly Leagues Mapping**: 3 KO consecutivi (02, 03, 04/10). Causa: Supabase risponde 522/520 (Cloudflare) in modo transitorio MA il nostro codice non ha nessun ritentativo = difetto nostro.
   - **Seasons Catchup**: 7 KO su 21 (33%). 5 su 7 sono un exit code 1 "dichiarato" (la regola `BUCO VECCHIO` colora di rosso uno stato atteso); 2 su 7 (26-27/09) erano 57014 vero, gia' corretto il 28/09 (nessun timeout dopo).
   - **Hazard Atlas**: 1 KO (28/09, HTTP 500 Supabase in scrittura, nessun ritentativo).
3. **Dati**: per i fallimenti di 02-04/10 i dati che contano (risultati di ieri, previsioni di oggi, esiti fino al 02/10, modelli, atlante) sono popolati. Mancano SOLO: l'aggiornamento dei flag coverage del mapper nei giorni 02 e 03/10 (recuperati in blocco il 04/10: 79 righe, meno 1 UPDATE perso su lega 353) e il progresso dei buchi storici (Catchup), fermo da 10 giorni (vedi sezione 3, C2). Gli esiti del 03/10 e le previsioni di oggi sono in attesa/in corso (Results 04/10 non ancora creato, Today in corso).
4. **"Monthly" gira ogni giorno per scelta documentata del 25/09** (commit `f015204`, commento in testa a `leagues_mapper.yml`), non per errore.

## 1. Tabella run per giorno (20/09 - 04/10)

| Giorno | Today | MLCal | Retrain | Catchup | Monthly | Hazard | Daily | Results | Weekly |
|---|---|---|---|---|---|---|---|---|---|
| 09-20 | s:ok:25m | s:ok:1m<br>r:ok:0m<br>r:ok:0m | r:KO:243m<br>d:ok:54m<br>s:ok:0m | - | - | - | s:ok:32m | s:ok:55m | - |
| 09-21 | s:ok:48m | r:ok:0m<br>s:ok:1m<br>r:ok:0m | r:KO:248m<br>d:KO:33m<br>d:KO:40m<br>d:KO:14m<br>d:ok:13m<br>s:ok:0m | - | - | - | s:ok:18m | s:ok:66m | s:ok:21m |
| 09-22 | s:ok:34m | r:ok:0m<br>s:ok:1m<br>r:ok:0m | r:ok:56m<br>s:ok:0m | - | - | - | s:ok:4m | s:ok:52m | - |
| 09-23 | d:ok:41m<br>s:can:3m<br>d:KO:244m<br>d:ok:410m | r:ok:0m<br>s:ok:0m<br>r:ok:0m<br>r:ok:0m | r:ok:83m<br>d:ok:78m<br>s:ok:0m | - | - | - | s:ok:6m | d:KO:20m<br>s:KO:34m<br>d:KO:112m | - |
| 09-24 | s:ok:33m | r:ok:0m<br>s:ok:1m<br>r:ok:0m | r:ok:66m<br>s:ok:0m | - | - | - | s:ok:4m | s:KO:105m<br>d:KO:62m<br>d:KO:113m<br>d:ok:68m | - |
| 09-25 | s:ok:98m | r:ok:0m<br>r:ok:0m<br>s:ok:1m<br>r:ok:0m | r:skip:0m<br>r:skip:0m<br>s:ok:10m | d:ok:34m<br>s:ok:3m | - | - | s:KO:0m | s:ok:56m | - |
| 09-26 | s:ok:207m | r:ok:0m<br>s:ok:1m<br>r:ok:0m | r:ok:54m<br>s:ok:0m | r:ok:3m<br>s:KO:2m | r:ok:1m | r:ok:0m | s:ok:13m | s:ok:76m | - |
| 09-27 | s:ok:170m | s:ok:1m<br>r:ok:0m<br>r:ok:0m | r:ok:264m<br>d:ok:62m<br>s:ok:0m | r:ok:96m<br>s:KO:1m | r:ok:1m | r:ok:1m | s:ok:29m | s:ok:87m | - |
| 09-28 | s:ok:29m | r:ok:0m<br>s:ok:0m<br>r:ok:0m | r:ok:174m<br>s:ok:0m | r:ok:38m<br>s:ok:35m | r:ok:1m | r:KO:0m | s:ok:29m | s:ok:93m | s:ok:14m |
| 09-29 | s:ok:70m | r:ok:0m<br>s:ok:0m<br>r:ok:0m | r:ok:47m<br>s:ok:0m | r:ok:48m<br>r:ok:3m<br>s:KO:43m | r:ok:0m | r:ok:1m | s:ok:5m | s:ok:92m | - |
| 09-30 | s:ok:67m | r:ok:0m<br>s:ok:0m<br>r:ok:0m | r:ok:67m<br>s:ok:0m | r:ok:7m<br>s:ok:42m | r:ok:1m | r:ok:0m | s:ok:8m | s:ok:92m | - |
| 10-01 | s:ok:50m | r:ok:0m<br>r:ok:0m<br>s:ok:0m<br>r:ok:0m | r:ok:0m<br>d:ok:66m<br>s:ok:0m | r:KO:47m<br>r:ok:6m<br>s:ok:21m | s:ok:1m<br>r:ok:1m | r:ok:4m | s:ok:10m | s:ok:73m | - |
| 10-02 | s:ok:107m | r:ok:0m<br>s:ok:0m<br>r:ok:0m | r:ok:101m<br>s:ok:0m | r:ok:54m<br>s:KO:50m | r:KO:1m | r:ok:1m | s:ok:6m | s:ok:72m | - |
| 10-03 | s:ok:228m | r:ok:0m<br>s:ok:0m<br>r:ok:0m | r:ok:116m<br>d:ok:20m<br>s:ok:0m | r:ok:95m<br>s:KO:41m | r:KO:1m | r:ok:1m | s:ok:11m | s:ok:87m | - |
| 10-04 | s:IN CORSO | r:ok:0m | r:ok:2m<br>d:IN CORSO | r:KO:95m | r:KO:1m | r:ok:1m | s:ok:31m | - | - |

Note: Retrain 25/09 due run `skip` (Daily KO allora per il job atlante dentro il Daily, causa corretta il 25/09). Today 23/09: 1 `can` (annullata a mano dall'utente, CRONOSTORIA 23/09) + 1 KO di dispatch di verifica. `validate_models.yml`: solo dispatch, 0 run nel periodo (atteso). Weekly: lunedi 21 e 28/09 ok; prossimo lunedi 05/10. Run con "0m" di Retrain/MLCal = nessun lavoro (planner vuoto), esito atteso.

**Giorni in cui un workflow atteso NON e' partito**: nessuno. Daily 15/15; Today 15/15 (oggi in corso); Results 14/15 (oggi non ancora creato alle 09:45 UTC: cron 03:23 UTC, ritardo dello scheduler); Hazard dal 26/09, Monthly giornaliero dal 26/09, Catchup dal 25/09: una run al giorno ciascuno. Ritardo cron osservato: Daily parte tra le 05:52 e le 07:08 UTC invece delle 01:12 (4-6 h), Today tra 07:32 e 09:03 invece delle 02:18, Results 08:34-10:16 invece delle 03:23 (scheduler GitHub, causa esterna gia' documentata in `AUDIT_2026-09-25/ACTIONS_DIAGNOSI_E_FIX.md` par. 5).

## 2. Tassi di fallimento (20/09 - 04/10)

| Workflow | run | success | failure | skipped/cancelled | in corso | tasso fallimento |
|---|---|---|---|---|---|---|
| Today | 18 | 15 | 1 | 1 | 1 | 1/16 = 6% |
| MLCal | 46 | 46 | 0 | 0 | 0 | 0/46 = 0% |
| Retrain | 40 | 32 | 5 | 2 | 1 | 5/37 = 14% |
| Catchup | 21 | 14 | 7 | 0 | 0 | 7/21 = 33% |
| Monthly | 10 | 7 | 3 | 0 | 0 | 3/10 = 30% |
| Hazard | 9 | 8 | 1 | 0 | 0 | 1/9 = 11% |
| Daily | 15 | 14 | 1 | 0 | 0 | 1/15 = 7% |
| Results | 19 | 13 | 6 | 0 | 0 | 6/19 = 32% |
| Weekly | 2 | 2 | 0 | 0 | 0 | 0/2 = 0% |
| TOTALE | 180 | 151 | 24 | 3 | 2 | 24/175 |

Ultimi 7 giorni (28/09-04/10): 9 KO = Catchup 5, Monthly 3, Hazard 1. Daily, Today, Results, Retrain, MLCal, Weekly: 0 KO.

## 3. Cause radice di OGNI fallimento

### C1. Monthly Leagues Mapping, 02/03/04-10 (run 36976589187, 37103519105, 37185344834). Limite esterno transitorio + NOSTRO difetto (nessun ritentativo)
- 02/10 e 03/10: `RuntimeError: lettura api_coverage_by_season fallita (offset 0): {'message': 'JSON could not be generated', 'code': 522, ... '<!DOCTYPE html>...` (522 = Cloudflare "connection timed out" davanti a Supabase REST), alle 06:34-07:04 UTC, cioe' nei minuti in cui parte il Retrain dello stesso Daily. Il 03/10 anche `[LOGGER] Insert batch api_call_log fallito ({'message': 'Could not query the database for the schema cache. Retrying.', 'code': 'PGRST002'`.
- Codice: `leagues_mapper.py:54-55` (`get_existing_coverage_rows`: una sola `.execute()` per pagina, `except Exception` -> `raise RuntimeError`, zero retry), propagato da `:212` e `:337`, `SystemExit` a `:339`.
- 04/10: la lettura e' riuscita (Inserite 5, Aggiornate 74, Invariate 8677) ma `Errore UPDATE lega 353 stagione 2026 NON previsto: {'message': 'JSON could not be generated', 'code': 520 ...` -> `Update con errori: 1` -> `LEAGUES MAPPER FALLITO: 1 batch in errore NON previsto (vedi log).` (`leagues_mapper.py:301-302`, `:316`, `:339`). Verificato sul DB: lega 353/2026 ha ancora `updated_at` 25/09 e `fixtures_lineups=false`.

### C2. Seasons Catchup 29/09, 01/10, 02/10, 03/10, 04/10 (36615357543, 36821373801, 37049359939, 37141249749, 37185437609). Exit code "dichiarato" che colora di rosso un esito atteso
- Riga errore: ogni run finisce con `BUCO VECCHIO: lega <id> stagione 2026 aperto da N gg (> 3) con budget disponibile: API vuota su K partite-tabella (in attesa del 2o tentativo); flag coverage False (non richieste): match_player_stats,match_team_stats` (o `errore API ripetuto su 1 partite-tabella; ... match_odds`), poi `##[error]Process completed with exit code 1.`. Casi: 29/09 lega 667 (9 partite-tabella); 01/10 lega 10 (69); 02/10 lega 344 (errore API ripetuto, match_odds); 03/10 leghe 129, 250, 255; 04/10 lega 129 (8).
- Codice: `seasons_catchup.py:895-899` (aggiunge a `falliti` ogni lega-stagione aperta da piu' di `BACKFILL_BUCHI_MAX_GIORNI`=3 e non rimasta in coda), stampa a `:940-941`, uscita `:949` `return 1 if (ris.errori or falliti or degradate_persistenti) else 0`. Intento in docstring `:30-33`.
- Perche' e' un falso allarme: le cause stampate sono stati attesi: (a) l'API ha risposto vuoto (`in_attesa`, "l'API non ha il dato", `season_gaps.py:18`), (b) flag coverage False quindi tabelle NON richieste (non e' recuperabile da noi), (c) 5xx ripetuto di API-Football. Ogni giorno l'elenco cambia lega: la regola colora di rosso la lega "capitata" quel giorno, non un guasto.
- 04/10 in piu': `Chiamate fatte stanotte: 0 ... Fermato per: action concorrente in_progress: today_predictions_backfill.yml`. Ha atteso `retrain_models.yml` 90 min (`[CATCHUP] ATTESA: action concorrente in_progress: retrain_models.yml (atteso 12/90 min...`) perche' il Retrain si auto-rilancia (C6); poi e' partito Today (08:31) e si e' fermato: 95 min di runner, 0 lavoro, rosso per il solo `BUCO VECCHIO` lega 129.
- Avanzamento reale dei buchi storici: `BUCHI APERTI` 1297 (29/09), 1290 (01/10), 1283 (02/10), 1278 (03/10), 1287 (04/10), ~156-178k chiamate stimate: il debito NON converge (4-6k chiamate/notte, ma numero quasi piatto). Non e' perdita di dati nuovi, e' il recupero dello storico non finito.

### C3. Seasons Catchup 26/09 e 27/09 (36258896621, 36338805869). NOSTRO, 57014 vero. CORRETTO il 28/09
- `postgrest.exceptions.APIError: {'message': 'canceling statement due to statement timeout', 'code': '57014'` da `season_gaps.py:237 riepilogo_lacune` (RPC a blocchi, chiamata da `seasons_catchup.py:590`).
- Fix: commit `0ffc3c6` ("il riepilogo dei buchi non muore piu' per timeout 57014") e `49dea7e` (blocco adattivo). Prova: log 29/09-04/10 senza `statement timeout` e senza righe `DEGRADAT*`.

### C4. Hazard Atlas 28/09 (36390445058). Esterno transitorio (Supabase 500) + nessun ritentativo nel salvataggio
- `urllib.error.HTTPError: HTTP Error 500: Internal Server Error` da `genera_atlante.py:1133 main -> :918 salva -> :943 salva_versione -> :912 _req`. La versione del 28/09 non e' stata scritta: sul DB `hazard_atlas` ha id 2,4,5,6,7,8,9 (manca id 3 = 28/09). Nessuna perdita di dati: il 29/09 l'atlante e' incrementale dalla filigrana. Se oggi esiste un ritentativo: NON verificato (test `test_genera_atlante_scrittura_ritentativi_2026_09_28.py` presente, non eseguito).

### C5. Fallimenti vecchi, tutti con causa gia' corretta
- Retrain 20/09 e 21/09 (35494758357, 35568831478, 35589926333, 35592896432, 35596470375): `canceling statement due to statement timeout` (`[ERROR] league 140/71/141: {'code': '57014'`). Sparito dal 22/09.
- Today 23/09 (35837269470): dispatch di verifica/recupero `Uscita con codice 1: 106 anomalie non recuperate su 2026-09-19`; il dispatch successivo 35837336690 e' verde.
- Results 23/09 e 24/09 (35837906029, 35838543385, 35844019126, 35976004167, 36002968576, 36011159941): `Step 'enrich' con esito 'failure'` e/o `'bets'`; sotto, `RuntimeError: lettura analytics_signals lega 929 (offset 0, blocco 100) fallita dopo 5 tentativi: ... 57014`, `lettura matches lega 667 ... 57014`, `canceling statement due to lock timeout 55P03`, `duplicate key ... book_odds_cache_pkey`. Corretto con la migrazione RPC del 24/09 e rilancio verde 36030163506 (24/09 16:50).
- Daily 25/09 (36101390338): `urllib.error.HTTPError: HTTP Error 404` in `genera_atlante.py:585 leggi_stato_db` (tabelle atlante non ancora migrate, job atlante allora nel Daily). Corretto con `hazard_atlas.yml` separato.

### C6. Chi lancia il Retrain `workflow_dispatch` di oggi (37185450088)
- Non e' una persona: e' il job `rechain` del Retrain stesso: `retrain_models.yml:371 gh workflow run retrain_models.yml -f chain_depth="$NEXT"` con `actions: write` (`:321`), `MAX_CHAIN=8` (`:340`). Il run 37185344829 (workflow_run, 07:17) ha allenato per 1 minuto; il suo `rechain` (07:19:22-07:19:55) ha trovato leghe rimaste e ha ridispatchato. Previsto dal progetto, ed e' la ragione per cui il Catchup trova sempre il Retrain "in corso".

## 4. I dati sono stati popolati lo stesso? (SELECT di sola lettura, progetto dqbwaocvlzbxfrpacsac)

Query ESATTE:

Q1 (Daily: risultati di ieri in `matches`)
```sql
select (fixture_date at time zone 'UTC')::date d, count(*) n,
 count(*) filter (where status_short in ('FT','AET','PEN')) finiti,
 count(*) filter (where status_short in ('NS','TBD')) ns,
 max(updated_at) ult_upd
from matches where fixture_date >= '2026-09-26' and fixture_date < '2026-10-06' group by 1 order by 1;
```
Q2 (Today + Results: `fixture_predictions`)
```sql
select (fixture_date at time zone 'UTC')::date d, count(*) n,
 count(*) filter (where error_message is not null) con_errore,
 count(*) filter (where model_predictions_json is not null) con_modelli,
 count(*) filter (where tactical_engine_json is not null) con_tattico,
 count(*) filter (where evaluated_at is not null) valutate,
 count(*) filter (where result_status_short in ('FT','AET','PEN')) con_risultato,
 count(*) filter (where raw_json_odds is not null) con_quote, max(updated_at) ult_upd
from fixture_predictions where fixture_date >= '2026-09-26' and fixture_date < '2026-10-06' group by 1 order by 1;
```
Q3 (dettaglio per partita finita)
```sql
select (m.fixture_date at time zone 'UTC')::date d, count(*) finiti,
 count(*) filter (where exists (select 1 from match_events e where e.fixture_id=m.fixture_id)) con_eventi,
 count(*) filter (where exists (select 1 from match_lineups e where e.fixture_id=m.fixture_id)) con_formazioni,
 count(*) filter (where exists (select 1 from match_team_stats e where e.fixture_id=m.fixture_id)) con_stat_squadra,
 count(*) filter (where exists (select 1 from match_player_stats e where e.fixture_id=m.fixture_id)) con_stat_giocatori,
 count(*) filter (where exists (select 1 from match_odds e where e.fixture_id=m.fixture_id)) con_quote
from matches m where m.fixture_date >= '2026-09-26' and m.fixture_date < '2026-10-04'
 and m.status_short in ('FT','AET','PEN') group by 1 order by 1;
```
Q4 (Monthly: coverage) `select updated_at::date d, count(*) from api_coverage_by_season where updated_at >= '2026-09-24' group by 1 order by 1;` e lo stesso con `inserted_at`.
Q5 (Retrain) `select trained_at::date d, count(*) modelli, count(distinct league_id) leghe, count(*) filter (where calibration_cells is not null) con_celle from ai_model_registry where trained_at >= '2026-09-24' group by 1 order by 1;`
Q6 (MLCal) `select generated_at::date d, count(*) righe, max(generated_at) ult, min(min_n) from ml_post_calibration where generated_at >= '2026-09-24' group by 1 order by 1;`
Q7 (Hazard) `select updated_at::date d, count(*), max(updated_at) from hazard_atlas_leghe where updated_at >= '2026-09-24' group by 1 order by 1;` e `select id, generated_at, n_leghe, n_partite from hazard_atlas order by generated_at desc limit 10;`
Q8 (Results non valutate) `select (p.fixture_date at time zone 'UTC')::date d, count(*) non_valutate, count(*) filter (where m.fixture_id is null) senza_match, count(*) filter (where m.status_short in ('FT','AET','PEN')) match_finito_ma_non_valutata from fixture_predictions p left join matches m on m.fixture_id=p.fixture_id where p.fixture_date >= '2026-09-26' and p.fixture_date < '2026-10-03' and p.evaluated_at is null group by 1 order by 1;`

Risultati (giorno della PARTITA):

| Giorno | matches totale / finiti / NS | previsioni n / con modelli / valutate | Esito |
|---|---|---|---|
| 28/09 | 88 / 88 / 0 | 84 / 82 / 82 | popolato |
| 29/09 | 175 / 175 / 0 | 175 / 167 / 169 | popolato |
| 30/09 | 205 / 204 / 1 | 201 / 192 / 197 | popolato |
| 01/10 | 116 / 116 / 0 | 124 / 113 / 113 | popolato |
| **02/10** | 327 / 326 / 1 (agg. 03/10 06:24) | 308 / 289 / 289 (le 19 non valutate sono tutte `senza_match`: non in `matches`) | **popolato** |
| **03/10** | 1248 / 1197 / 51 (agg. 04/10 06:47) | 1287 / 1263 / **0** (1190 hanno un match finito) | Daily ok; **esiti PENDENTI**: li scrive il Results di oggi (non ancora creato alle 09:45 UTC) |
| **04/10 (oggi)** | 71 NS (normale: le finite arrivano domani) | 793 / 620 / 0, `con_tattico`=0, ult_upd 09:43 | **Today IN CORSO e parziale** (run 37189192827 dalle 08:31, step "Run script" in corso): da completare, non e' un guasto |

Dettaglio Q3: 02/10 326 finite = 212 eventi, 35 formazioni, 34 stat squadra, 32 stat giocatori, 171 quote; 03/10 1197 finite = 707, 88, 79, 70, 583. Le percentuali basse sono i limiti di coverage delle leghe minori, uguali ai giorni 26/09-01/10 (es. 29/09: 160/175 eventi, 41 formazioni), quindi nessuna anomalia specifica di 02-04/10. I 51 NS del 03/10 sono partite non passate a FT (probabili rinviate): stesso pattern dei giorni precedenti (15 il 26/09, 3 il 27/09), non legato ai fallimenti.

Per workflow:
- **Daily** (risultati di ieri): popolato ogni giorno 26/09-04/10 (ult_upd tra 06:24 e 07:09 UTC del giorno dopo). Il 04/10: 1197 finite del 03/10.
- **Today** (previsioni di oggi): popolato ogni giorno, 0 `error_message`; oggi parziale perche' in corso.
- **Results**: 02/10 completo; 03/10 pendente. Residuo storico piccolo: 4 (26/09), 3 (27/09), 2 (29/09), 4 (01/10) previsioni con match finito ma non valutate (motivo non indagato).
- **Monthly (coverage)**: righe aggiornate per giorno: 25/09 1462 (primo giro), 26/09 16, 27/09 39, 28/09 24, 29/09 28, 30/09 96, 01/10 22, **02/10 0, 03/10 0**, 04/10 79 (74 agg. + 5 ins., 1 UPDATE perso: lega 353). Quindi i flag coverage delle stagioni vive sono stati vecchi di 2 giorni; i nuovi sono entrati il 04/10.
- **Seasons Catchup**: lavora (4.262, 4.344, 5.897, 4.626 chiamate nelle notti 29/09-03/10) ma BUCHI APERTI ~1.280-1.300 lega-stagioni e ~156k chiamate, non diminuiscono; il 04/10 0 chiamate.
- **Retrain**: modelli scritti ogni giorno: 02/10 165 (8 leghe), 03/10 330 (16), 04/10 742 (36 leghe, ancora in corso); `calibration_cells` presente quasi ovunque (02/10: 163/165, 30/09: 146/161).
- **ML Calibration**: `ml_post_calibration` 940 righe con `generated_at` 03/10 13:24 (la tabella e' sovrascritta). La run del 04/10 07:19 ha detto "Nessuna lega riaddestrata dall'ultima calibrazione: niente da fare" perche' i modelli di oggi (742) li sta scrivendo il Retrain in corso; scattera' un'altra run al suo termine. Non e' un guasto.
- **Hazard**: `hazard_atlas_leghe` aggiornata ogni giorno (157 leghe il 04/10); versioni `hazard_atlas`: 04/10 id 9 (265 leghe, 311.448 partite), 03/10 id 8, 02/10 id 7, 01/10 id 6, 30/09 id 5, 29/09 id 4, **28/09 mancante (id 3, KO)**, 27/09 id 2.
- **Weekly Poisson**: 21/09 e 28/09 ok (scrive nel repo con commit, non nel DB); prossimo 05/10.

## 5. "Monthly Leagues Mapping": perche' gira ogni giorno

- `leagues_mapper.yml:9-11`: `on: workflow_run: workflows: ["Daily Yesterday Backfill"], types: [completed]`, in aggiunta a `schedule: '12 0 1 * *'`. Introdotto dal commit `f015204` ("DB sempre aggiornato e senza buchi", 25/09/2026 11:38 +02:00). Commento in testa al file: "il nome resta (lo usano seasons_catchup.yml e AUDIT_2026-09-25/misure_action.py) ma ora gira anche OGNI GIORNO, in coda al Daily".
- Storia dei run (`gh run list --workflow leagues_mapper.yml`): schedule mensile 01/03, 01/04, 01/05, 01/06, 01/07, 01/08, 01/09 (tutte success) -> nessuna run dal 01/09 al 25/09 -> dal 26/09 una run `workflow_run` al giorno (il 01/10 anche la schedule mensile, 05:44, ritardata). Scelta documentata (CRONOSTORIA 25/09 e `AUDIT_2026-09-25/ACTIONS_DIAGNOSI_E_FIX.md` par. 6: i flag coverage delle stagioni 2026 restavano False per sempre perche' il mapper non aggiornava mai le righe esistenti).
- Cosa fa di utile ogni giorno: 1 chiamata API `/leagues`; UPDATE di flag coverage (`fixtures_events/lineups/statistics`, `odds`, ...), `current`, `season_start/end` delle stagioni vive (04/10: 74 aggiornate, es. "lega 18 stagione 2026: fixtures_statistics_fixtures False -> True"); INSERT di leghe/stagioni nuove (5). Il Daily usa questi flag (`per_fixture_backfill.get_coverage_for_season`) per decidere quali tabelle scaricare.
- Riferimenti per nome (da aggiornare insieme in caso di rinomina): `seasons_catchup.yml:21` `workflows: ["Monthly Leagues Mapping"]` (**l'unico funzionale**) e il commento `:6`; `AUDIT_2026-09-25/misure_action.py:16` (dizionario di misura); commenti in `hazard_atlas.yml:31` e `Betfair/stream/tests/test_genera_atlante_scrittura_ritentativi_2026_09_28.py:8`. Altre occorrenze solo in copie: `.claude/worktrees/*`, `_checkpoint_2026-09-28/` (non produzione).
- Proposta: cambiare SOLO `name:` (riga 1) in, es., `Leagues Mapping (giornaliero, dopo il Daily)` e, nello STESSO commit, `seasons_catchup.yml:21` (e `:6`), `misure_action.py:16`, i due commenti. Rischio: se `seasons_catchup.yml:21` non viene aggiornato, il Catchup non parte piu' dal workflow_run e nessuno lo segnala (resta il cron 13:47 UTC). Il file resta `leagues_mapper.yml`, la storia delle run resta unita (GitHub identifica il workflow dal path). Verifica: `gh workflow list` dopo il push e prima run `workflow_run` del Catchup. Variante a rischio zero: non toccare `name:`, aggiungere solo `run-name:`.

## 6. Confronto con cio' che fu dichiarato "risolto" (23/09 e 25/09)

| Causa | Dichiarata | Stato al 04/10 | Prova |
|---|---|---|---|
| 57014 su Retrain | risolta 23/09 | **davvero sparita** | ultimo KO 21/09; 0 `statement timeout` nel log 37103519100 |
| 57014 su Today | risolta 23/09 | **sparita** | Today verde dal 24/09; 0 `statement timeout` in 37109100272, 36985187944 |
| 57014/lock su Results (enrich/bets) | "risolta" 23/09, **NON lo era**: KO ancora 23/09 (3) e 24/09 (3) | **risolta dal 24/09 sera** | Results 10/10 verdi 25/09-03/10, 0 timeout |
| Daily rosso per job atlante (404) | risolto 25/09 | sparito; ma l'atlante ha avuto un 500 il 28/09 (nuovo, C4) | 36101390338 vs 36390445058 |
| Retrain saltato se il Daily e' rosso | risolto 25/09 | sparito | Retrain eseguito ogni giorno 26/09-04/10 |
| Mapper silenzioso (vuoto) | reso rumoroso 25/09 | **rumoroso, ma rosso 3 giorni su 3 recenti** per i 52x senza retry | C1 |
| Catchup 57014 (componente nuovo) | non esisteva | KO 26-27/09, corretto 28/09 | C3 |
| Catchup exit 1 "buco vecchio" | disegno 25/09 | **causa NUOVA di rosso**, 5 KO | C2 |
| Cron GitHub in ritardo 4-6 h | causa esterna, non corretta | **ancora presente** | tabella sez. 1 |

Giudizio: "tutti i problemi risolti" era vero SOLO per le cause 57014 del 20-24/09 e per Results lo e' diventato il 24/09 sera, non il 23. I rossi di oggi sono cause NUOVE nate dal 25/09 con i componenti nuovi (Monthly giornaliero, Catchup, Hazard separato), non coperte dalla verifica di allora.

## 7. Piano di correzione "una volta per tutte" (SOLO PROPOSTA, nessun codice applicato)

**Priorita 1 - Monthly (C1): ritentativi nel mapper.**
- Minima: in `leagues_mapper.py` avvolgere la lettura paginata (`:41-56`) e l'UPDATE (`:296-302`) in un ritentativo (5 tentativi, 2/4/8/16 s, solo per 5xx/52x/`PGRST002`/`57014`/timeout di rete; mai per 4xx), copiando il modello gia' presente in Results/Retrain/Today. Un UPDATE che alla fine fallisce stampa `::warning::` e viene ricalcolato il giorno dopo (idempotente: il mapper ricalcola ogni volta la differenza); exit 1 solo se la lettura fallisce dopo tutti i tentativi o se gli UPDATE persi superano una soglia.
- Rischio: basso; stessi dati, nessuna chiamata API in piu' (`/leagues` si chiama una volta).
- Verifica senza cambiare i dati: test con finto PostgREST che risponde 522 due volte poi 200 (modello `AUDIT_2026-09-25/prova_preflight_atlante.py`); falsificazione (togliere il retry -> test rosso); confronto del referto (Aggiornate/Inserite/Invariate) con quello del 04/10.
- Rilancio: **da fare con il permesso dell'utente** - dispatch di Monthly, atteso `Update con errori: 0`.

**Priorita 2 - Catchup (C2): non colorare di rosso gli stati dichiarati.**
- Minima: `seasons_catchup.py:949` far dipendere l'exit dalle sole cause vere (`ris.errori`, `degradate_persistenti`). `falliti` (BUCO VECCHIO con causa `in_attesa`/vuoto API/flag False/5xx API) diventano `::warning::` e riga di referto. Prudente: rosso solo se il buco vecchio non ha una causa dichiarata, oppure e' aperto da oltre N giorni (es. 14) con tentativi falliti.
- Rischio: si perde un segnale se un buco si blocca davvero; compensare con contatore di invecchiamento. Dati: invariati (nessuna chiamata API/DB in piu' o in meno).
- Verifica: test mirato sul caso "buco vecchio" (exit 0 + warning), falsificazione rimettendo `falliti` nell'exit; ripetere sui log salvati di 36615357543 e 37141249749. Rilancio: dispatch del Catchup **solo con permesso** (consuma 4-6k chiamate API-Football).
- Spreco di runner: il Catchup agganciato al Monthly aspetta fino a 90 min il Retrain (che si auto-rilancia). Opzioni: (a) togliere il trigger `workflow_run` del Catchup e tenere il solo cron 13:47 UTC (reale ~18:00-19:00, quando Today/Results sono finiti: i run del 02 e 03/10 hanno lavorato proprio cosi'); (b) lasciare. Nessun effetto sui dati. Decisione dell'utente.
- Analisi separata (decisione dell'utente): perche' i ~1.280 buchi storici non calano da 10 giorni (query su `season_backfill_state.stats_json`).

**Priorita 3 - Hazard (C4):** ritentativo nel salvataggio versione (`genera_atlante.py:912 _req` / `:943 salva_versione`), 5 tentativi su 5xx, con controllo di idempotenza (rileggere l'ultima versione prima di riprovare, per non scrivere due volte se la risposta si e' persa). Verifica: finto PostgREST 500 poi 201; payload dell'atlante identico (`n_partite`, filigrana) a una generazione senza errori. Rilancio con permesso (dispatch dell'atlante).

**Priorita 4 - Nome "Monthly":** vedi sezione 5.

**Priorita 5 - Osservabilita (nessun impatto sui dati):** un riepilogo di salute a fine catena che distingua "dato mancante" da "dato popolato ma exit atteso" (Q1-Q7 sopra), gia' nel piano h24 del 02/10.

Non correggibili da noi: ritardo cron GitHub (4-6 h) e disponibilita' Supabase (522/520/500): si mitigano con retry e catene `workflow_run`.

Rilanci che servirebbero (TUTTI vietati oggi, da fare con il permesso dell'utente): Monthly (dopo il retry), Catchup (dopo la modifica dell'exit), Hazard (dopo il retry); opzionale Results del 03/10 solo se oltre le 11:00 UTC non fosse ancora partito.

## 8. Cosa NON ho potuto verificare

- Results di oggi (04/10) non ancora creato dallo scheduler alle 09:45 UTC: gli esiti del 03/10 (1190 previsioni con match finito) sono ancora da scrivere; da rileggere con Q2/Q8 a fine run.
- Today 04/10 e Retrain dispatch 37185450088 erano in corso: esito finale e completezza dei dati di oggi non verificabili ora.
- Se i 51 NS del 03/10 (e gli "NS dopo la partita" precedenti) sono rinviate: servirebbe l'API (non chiamata).
- Dettagli (eventi, formazioni, statistiche) confrontati solo con i giorni precedenti, non con il flag coverage lega per lega ne' con l'API.
- Perche' il numero dei buchi del Catchup resta piatto: non analizzato (serve `season_backfill_state`).
- Il motivo di 13 casi "match finito ma previsione non valutata" (26/09, 27/09, 29/09, 01/10).
- Se `genera_atlante.py` ha oggi un ritentativo sul salvataggio versione (test del 28/09 presente, non eseguito: vietato lanciare script).
- Ricerca di `statement timeout` fatta solo su: Today 02-03/10, Results 02-03/10, Daily 04/10, Retrain 03/10, Catchup 02/10 e sui log dei KO; non su tutte le run verdi.
- Orari "reali" dei cron: dedotti dai `createdAt` delle run.
