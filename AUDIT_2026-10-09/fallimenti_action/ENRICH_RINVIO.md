# Enrich freq/ritardi: rinvio dichiarato invece della run rossa (09/10/2026)

Delegato Opus, worktree `wt-enrich`, ramo `cantiere-enrich-rinvio` (da master locale 04e1b9a4).
Niente commit, niente push, nessun workflow lanciato, DB solo in lettura.

## 1. Il fatto e la causa (file:riga sul master 04e1b9a4)

Run 37927426667 (Predictions Results), passo `enrich` (`enrich_analytics_snapshots.py --days 4`),
dal log (`gh run view 37927426667 --log`, righe 595-602):

```
Incrementale (--days 4): 200 leghe con fixture recenti, 649 fixture-target.
  lega 334 ... 252 ... 287 ... 703 riuscite
    [ERR flush lega 850] ReadTimeout: The read operation timed out
    [ERR flush lega 850] abbandono la lega: 3612 righe NON scritte (fetta ridotta a 200)
  lega 850: target 4012 | aggiornate 808
```

Catena della run rossa:

1. **Timeout uguale da tutte e due le parti.** Il client delle action usa il timeout di default
   della libreria: `postgrest/constants.py:6 DEFAULT_POSTGREST_CLIENT_TIMEOUT = 120` (supabase 2.28.0,
   `db_client.py:93-94` crea il client senza opzioni quando `_STATO["timeout"]` e' None, cioe' in
   tutte le action). La RPC ha `statement_timeout=120s` sulla funzione (verificato oggi su
   `pg_proc.proconfig`: `["search_path=public, pg_temp","statement_timeout=120s"]`, impostato da
   `migrations/actions_57014_2026-09-24_DA_INCOLLARE_NELLO_SQL_EDITOR.sql:20`). Client e server
   scadono insieme: vince il client, con un `ReadTimeout` che NON dice se l'UPDATE e' passato.
   Il brief chiedeva di "alzare a 120 s": era GIA' 120 s, ed e' proprio questo il difetto.
   `pg_stat_statements` (service_role, oggi): flush 2471 chiamate, media 436 ms, max 91.831 ms,
   dev. std 3,5 s: la RPC e' normalmente rapida, sotto carico (checkpoint al 30-40 % dei buffer)
   arriva oltre il minuto.
2. **Ritentativi corti.** `enrich_analytics_snapshots.py:310-321` (`_flush_league`): `_RETRY = 5`
   (riga 100), attese `_sleep_backoff` (riga 138-140) = min(8, 0,5 x 2^n) x 0,7-1,3 -> 0,5 / 1 / 2 / 4 s,
   circa 7,5 s di attesa in tutto tra 5 tentativi da 120 s l'uno: il DB non ha tempo di respirare.
3. **Abbandono = "falliti".** `enrich_analytics_snapshots.py:396-404`: la lega e' abbandonata e
   `counters["failed"] += persi` (riga 398) -> riga 572-579 `raise SystemExit("ATTENZIONE: ...")`
   -> exit 1 -> passo `enrich` failure (continue-on-error) -> "Gate errori nascosti"
   (`.github/workflows/predictions_results_backfill.yml:212-228`) rende la run ROSSA.
4. **Perche' nessuna riga `[RETE]`.** La richiesta e' `POST /rest/v1/rpc/flush_analytics_snap_staging`.
   Per il TrasportoResiliente un POST su `/rpc/` e' idempotente SOLO se la RPC e' in
   `RPC_LETTURA_ACTION` (`db_client.py:481-482`); la flush non c'e' (scrive), quindi il ReadTimeout
   (esito "ambiguo", `classifica_eccezione_action`, `db_client.py:498-505`) viene rilanciato subito
   senza log (`db_client.py:539-540`). Non e' l'ordine dei timeout ne' un client diverso: il
   trasporto era montato (`esegui_main_action`, `enrich_analytics_snapshots.py:583-586`) e ha fatto
   la cosa prevista dalla sua regola conservativa. Questa scelta e' anche fissata da un test
   (`test_fallimenti_action_2026_10_09.py:211-221`, flush = "RPC che scrive, mai ritentata dal
   trasporto"): NON l'ho cambiata. A ritentare la flush e' ora lo script, che sa che la RPC e'
   ripetibile (vedi 2.2).
   Nota: tutte le righe del passo hanno lo stesso orario (13:56:43) perche' `print` non svuota il
   buffer: le righe nuove usano `flush=True`.

## 2. Il rimedio (diff spiegato)

File toccati: `enrich_analytics_snapshots.py`, `db_client.py` (+16 righe, solo un'aggiunta),
`.github/workflows/predictions_results_backfill.yml` (gate), `test_actions_pipeline_paginazione.py`
(5 test adeguati alla nuova semantica), `test_enrich_rinvio_2026_10_09.py` (nuovo).

### 2.1 Timeout delle scritture: 150 s, solo nelle scritture di questo script
`_scrittura(sb)` (`enrich_analytics_snapshots.py:342`): durante UNA richiesta di scrittura (upsert
in staging, RPC di flush, DELETE della staging) mette `httpx.Timeout(150, connect=10, pool=10)`
sulla sessione PostgREST del client di questo processo e la rimette com'era subito dopo. Le letture
restano a 120 s; i bot non usano questo script; gli altri script non cambiano. 150 s > 120 s della
RPC: decide il server, che manda un 57014 chiaro (statement interrotto e annullato) invece di un
esito ignoto. Override `ENRICH_TIMEOUT_SCRITTURA_S`. Verificato sul client vero (sola lettura):
`timeout prima 120 / dentro 150.0 / dopo 120`.

### 2.2 Ritentativi: 2-4-8-16-32-60 s, un solo strato
`_scrivi_con_ritentativi` (`enrich_analytics_snapshots.py:369`): 7 tentativi, attese 2, 4, 8, 16, 32,
60 s (jitter +-25 %, circa 2 minuti di respiro al DB) su ogni transitorio: ReadTimeout e ogni
`httpx.TransportError` (GOAWAY = RemoteProtocolError compreso), 57014, 53300, 55P03, 40001, 5xx,
pagine Cloudflare 520-530, PGRST000-003, 08xxx (`_is_transient` ora usa anche
`db_client.classifica_guasto_rete`, `enrich_analytics_snapshots.py:147`). Errore LOGICO (4xx,
vincolo, colonna): `RuntimeError` SUBITO, causa in `__cause__` -> esce dal `main` -> exit 1.
Un solo strato: dentro `_scrittura` vale `db_client.ritentativi_del_chiamante()` (nuovo,
`db_client.py:606`, stesso segnale `_TLS.dentro_ritentativi` che `con_ritentativi` usa dal 09/10):
senza, l'upsert (idempotente per il trasporto) farebbe 7 x 7 = 49 richieste (mutazione M1).
Ripetibilita' della flush: `UPDATE ... FROM staging` + `DELETE` delle chiavi flushate nella stessa
transazione (`migrations/analytics_snap_staging.sql`); rieseguita dopo un esito ignoto trova la
staging gia' vuota per quelle chiavi e aggiorna 0 righe: stato finale identico (puo' solo
sottostimare il conteggio "aggiornate").
Caso peggiore per una lega: 7 x 150 s + ~122 s = circa 19,5 minuti, poi rinvio.

### 2.3 Esito: RINVIATA, separata dai falliti
- `_flush_staging` (`enrich_analytics_snapshots.py:440`): transitorio esaurito in pulizia, upsert o
  flush -> lega RINVIATA in `counters["rinviate"]` (lega, righe, motivo, aggiornate), riga
  `RINVIATA lega 850: N righe, motivo: ...`, fetta dimezzata per le leghe dopo, fetta caricata tolta
  dalla staging (se anche questo non riesce, la toglie la pulizia P2 del giro dopo). Anche una
  LETTURA della lega esaurita (prima "leghe_fallite" -> exit 1) e' ora un rinvio.
- Interruttore: 3 leghe rinviate di fila (`_RINVII_DI_FILA_MAX`, riga 128) = il DB non risponde;
  le restanti si dichiarano rinviate senza tentare (niente 20 minuti x N leghe, niente timeout del
  job a 240 min).
- `_esito_rinvii` (`enrich_analytics_snapshots.py:676`):
  - rinviate <= `ENRICH_SOGLIA_RINVII_PCT` (25 %) delle leghe elaborate e nessuna lega rinviata per
    la 3a run di fila -> `::warning::`, exit 0, passo verde;
  - oltre soglia, o stessa lega rinviata in >= 3 run consecutive -> `::error::` + SystemExit (exit 1);
  - sempre: riepilogo in `GITHUB_STEP_SUMMARY` ("RINVIATE PER DB SOTTO CARICO") e output del passo
    `rinvii=N`, `esito=rinviato|guasto` in `GITHUB_OUTPUT`.
- Stato fra run SENZA tabelle nuove: `public.live_alerts` (colonne vere verificate: level CHECK
  INFO/WARN/CRITICAL, code, message, event_id FK a live_follow -> lasciato NULL):
  - `WARN ENRICH_RINVIO` "lega 850: 3612 righe RINVIATE al prossimo giro, motivo: ...; run
    consecutive con rinvio: 1";
  - `CRITICAL ENRICH_RINVIO_PERSISTENTE` alla 3a run di fila;
  - `INFO ENRICH_RIPRESA` quando una lega rinviata viene scritta per intero (azzera la serie).
  `_storia_rinvii` (riga 606) legge le righe degli ultimi 14 giorni e conta i rinvii consecutivi per
  lega fino alla prima RIPRESA. Se live_alerts non e' leggibile/scrivibile: `::warning::`, mai un crash.
- Leghe rinviate rifatte d'ufficio (riga 799): una lega rinviata nelle run precedenti e non ancora
  ripresa entra nel giro anche se oggi non ha partite nella finestra (vedi 3).
- Modo storico `--league N` (lancio a mano): un rinvio resta exit 1, chi l'ha lanciato deve vederlo.

### 2.4 Gate del workflow
`predictions_results_backfill.yml`, passo "Gate errori nascosti": legge `steps.enrich.outputs.rinvii`
e `.esito`; con rinvii > 0 stampa `::warning::Step 'enrich': N leghe RINVIATE ...`. La regola
"solo success e' buono" e' invariata: rinvio entro soglia = exit 0 = success = run VERDE con
avviso; oltre soglia/persistente/errore logico = failure = run ROSSA.

## 3. Le righe rinviate vengono riprese? (verifica nel codice e sul DB)

- Ogni giro ricalcola e riscrive TUTTE le righe della lega, non solo le fixture recenti:
  `_fetch_signal_targets` (`enrich_analytics_snapshots.py:298`) legge tutti i
  (fixture, market, selection) della lega in analytics_signals; `_build_stage_rows` (riga 510,
  ciclo a riga 521) produce lo snapshot di ogni fixture settlata presente; `_enrich_league` (riga 540)
  passa tutti i fixture della lega alla pulizia (riga 558). La finestra `--days` sceglie solo QUALI
  LEGHE (`_recent_targets`), non quali righe.
- Staging: le chiavi non scritte non restano come residuo (fetta tolta dopo il rinvio; in ogni caso
  la pulizia P2 a inizio lega, riga 473, cancella tutto cio' che e' dei fixture della lega prima del
  primo flush). I valori in analytics_signals non vengono cancellati: le righe non scritte restano
  con il valore del giro precedente (lega 850 oggi: 808 righe aggiornate oggi, 5516 col valore di
  prima, `freq_current` NULL su 0 righe).
- **Il limite che c'era (e che ora e' chiuso):** la lega rientra nel giro solo se ha una partita
  con `kickoff >= now() - 4 giorni`. Lega 850: ultima partita 06/10 17:00 UTC, nessuna futura. Il
  giro di domani la prende solo se parte prima del 10/10 17:00 UTC; dopo, le righe resterebbero
  vecchie fino alla prossima partita della lega. Con il rimedio, da ora una lega rinviata rientra
  d'ufficio al giro dopo tramite `ENRICH_RINVIO` in live_alerts (test
  `test_d_ripresa_azzera_la_serie_e_la_lega_rinviata_si_rifa`, mutazione M9). **Per il rinvio di
  OGGI** (scritto dal codice vecchio, nessuna riga in live_alerts) vale solo la finestra: se il giro
  di domani parte dopo le 17:00 UTC serve un lancio a mano con `leagues=850`.

## 4. Test

Nuovo `test_enrich_rinvio_2026_10_09.py`, 12 test. Finti: client supabase/postgrest/httpx VERO con
`httpx.MockTransport`, TrasportoResiliente montato come in produzione (`esegui_main_action`),
`httpx.ReadTimeout` vero, corpi JSON di PostgREST, colonne vere di matches / analytics_signals /
live_alerts, flush che restituisce l'intero scalare come la RPC.

| Test | Prova |
|---|---|
| a `test_a_read_timeout_due_volte_poi_flush_riuscito` | ReadTimeout x2 poi 200: tutte scritte, 3 POST, attese [2, 4], 0 ritentativi del trasporto, nessun avviso, `rinvii=0` |
| a `test_a_timeout_150s_solo_sulle_scritture` | timeout read 150 s su upsert/flush/delete, mai sulle GET |
| b `test_b_read_timeout_persistente_lega_rinviata_exit_0` | 7 POST, attese 2-4-8-16-32-60, riga RINVIATA, `::warning::`, WARN ENRICH_RINVIO, riepilogo, `esito=rinviato`, altre leghe scritte, staging vuota, trasporto montato |
| b `test_b_upsert_in_timeout_un_solo_strato_di_ritentativi` | upsert in timeout: 7 richieste, non 49 |
| c `test_c_errore_logico_4xx_exit_1_subito` | 400/22P02 sul flush: RuntimeError, 1 richiesta, nessuna lega dopo, nessuna attesa |
| d `test_d_rinvii_oltre_soglia_exit_1` | 1 lega su 2 (50 % > 25 %): SystemExit, `::error::`, `esito=guasto` |
| d `test_d_soglia_da_ambiente` | `ENRICH_SOGLIA_RINVII_PCT=60`: exit 0 |
| d `test_d_stessa_lega_rinviata_3_run_di_fila_exit_1` | 2 rinvii precedenti + oggi (20 % sotto soglia): SystemExit, CRITICAL ENRICH_RINVIO_PERSISTENTE |
| d `test_d_ripresa_azzera_la_serie_e_la_lega_rinviata_si_rifa` | RIPRESA azzera la serie; lega rinviata ieri senza partite in finestra rifatta, INFO ENRICH_RIPRESA |
| e `test_e_run_37927426667_timeout_sulla_850_dopo_altre_riuscite` | leghe 334, 252, 287, 703, 850 (prima fetta scritta, poi ReadTimeout), 506, 776: exit 0, 850 rinviata, tutte le altre scritte anche dopo |
| e `test_e_tre_leghe_rinviate_di_fila_aprono_l_interruttore` | 3 x 7 tentativi poi stop, lega 4 non letta |
| gate `test_gate_del_workflow_distingue_rinviato_da_failure` | il gate legge rinvii/esito e tiene la regola "solo success" |

Adeguati in `test_actions_pipeline_paginazione.py` (nuova semantica ordinata dall'utente):
`test_flush_che_non_riesce_...`, `test_flush_fallito_non_lascia_...`,
`test_pulizia_staging_fallita_...` (righe in `rinviate`, `failed` = 0),
`test_upsert_staging_errore_logico_non_si_ritenta` (ora RuntimeError subito, 1 tentativo),
`test_main_lega_57014_persistente_non_ferma_le_altre_leghe` (la 929 e' RINVIATA; 1 su 2 = oltre
soglia, exit != 0 come prima).

Suite (worktree): tutti i file di test che importano `db_client` o `enrich_analytics_snapshots` +
`test_fallimenti_action_2026_10_09.py` + `test_catchup_*.py` (37 file, esclusi `Ai Engine/`):
**637 passed, 0 failed** (37 s). `Ai Engine/ai_engine/test_dataset_fixed.py` non si raccoglie
nemmeno sul master (importa `fetch_seasons_for_league`, che `db_client` non ha): estraneo.

Prova sul DB vero, sola lettura: `--days 4 --leagues 850 --dry-run` -> "lega 850: 4012 righe da
scrivere" (stesso target della run), `_storia_rinvii` -> `{}` (nessuna riga ENRICH_* oggi).

## 5. Falsificazione (15 mutazioni, tutte ROSSE, ripristino verificato con sha256)

Script `scratchpad/enrich/mutazioni.py`: muta, lancia il file di test, ripristina byte per byte,
verifica l'hash (enrich `95ef1cf72fbe0ad8...`, workflow `6bb300228712cf8d...`, identici prima e dopo).

| Mutazione | Test rosso |
|---|---|
| M1 niente `ritentativi_del_chiamante` | test_b_upsert_in_timeout_un_solo_strato (49 richieste) |
| M2 attese vecchie 0,5-4 s | test_a_read_timeout_due_volte |
| M3 timeout 150 s non applicato | test_a_timeout_150s_solo_sulle_scritture |
| M4 rinvio contato in `failed` | test_a/b (exit 1) |
| M5a sempre oltre soglia | test_b_read_timeout_persistente |
| M5b mai oltre soglia | test_d_rinvii_oltre_soglia_exit_1 |
| M6 persistente a 4 run | test_d_stessa_lega_rinviata_3_run |
| M7 errore logico come transitorio | test_c_errore_logico_4xx |
| M8 RIPRESA non azzera la serie | test_d_ripresa (exit 1 per persistenza falsa) |
| M9 leghe rinviate ieri non rifatte | test_d_ripresa |
| M10 niente interruttore | test_e_tre_leghe_rinviate_di_fila |
| M11 fetta rinviata lasciata in staging | test_b_read_timeout_persistente |
| M12 niente riepilogo del job | test_b_read_timeout_persistente |
| M13 niente avviso live_alerts | test_b_read_timeout_persistente |
| M14 gate senza RINVII_ENRICH | test_gate_del_workflow |
| M15 rinvio sotto soglia chiamato guasto | test_b (exit 1) |

## 6. Non verificato / da sapere

- Nessuna run reale: il comportamento su GitHub (output del passo, avviso del gate, riga in
  live_alerts dal runner) e' provato solo con i finti e il contratto YAML.
- Se il 57014 lato server arrivi davvero prima dei 150 s non l'ho misurato: `pg_stat_statements` non
  registra le query annullate. Se la `SET statement_timeout` della funzione non valesse per la
  chiamata, decide comunque il client a 150 s (ReadTimeout, ritentato e poi rinvio).
- Una rieseguita della flush mentre la precedente e' ancora viva lato server attende i suoi lock:
  stato finale identico, conteggio "aggiornate" possibilmente sottostimato.
- Caso peggiore di durata: ~19,5 min per lega rinviata; con l'interruttore al massimo ~1 h in piu'
  se il DB e' giu'; rinvii sparsi e numerosi potrebbero avvicinare il tetto del job (240 min).
- "aggiornate" > "target" nel log (es. 2332 su 1578): la flush conta le righe di analytics_signals
  (piu' motori per chiave), il target conta le chiavi di staging. Non e' un errore, ma il riepilogo
  confronta grandezze diverse (fuori perimetro, non toccato).
- I banner dell'app mostrano WARN/CRITICAL; la riga INFO ENRICH_RIPRESA forse non compare nel banner.
- Il rinvio di oggi (lega 850) non e' in live_alerts: vedi sezione 3.

## 7. Blocco per CRONOSTORIA

```
- [09/10] Enrich rinvio dichiarato (delegato Opus, wt-enrich, ramo cantiere-enrich-rinvio, NON
  committato). Causa run 37927426667: flush lega 850 in ReadTimeout con client 120 s = timeout RPC
  120 s; 5 tentativi a 0,5-4 s; abbandono contato in "failed" -> exit 1 -> gate rosso; nessun [RETE]
  perche' la RPC di flush non e' idempotente per il TrasportoResiliente (db_client.py:481-482).
  Rimedio: scritture a 150 s solo nell'enrich, ritentativi 2-4-8-16-32-60 s in un solo strato
  (db_client.ritentativi_del_chiamante), lega RINVIATA (contatore separato) con WARN ENRICH_RINVIO
  in live_alerts, exit 0 + ::warning:: entro 25 % (ENRICH_SOGLIA_RINVII_PCT), exit 1 oltre soglia,
  errore logico o 3 run di fila (CRITICAL ENRICH_RINVIO_PERSISTENTE); leghe rinviate rifatte
  d'ufficio al giro dopo; gate del workflow con avviso rinvii. Test 12 nuovi + 5 adeguati;
  suite collegata 637/0; 15 mutazioni tutte rosse. Referto:
  AUDIT_2026-10-09/fallimenti_action/ENRICH_RINVIO.md. Da fare: revisione del coordinatore, commit
  per percorsi espliciti; lega 850 di oggi: se il giro di domani parte dopo 10/10 17:00 UTC,
  lancio a mano con leagues=850.
```
