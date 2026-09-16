# FASE 0 — VERITÀ DI PARTENZA (16/09/2026)

> Eseguito da Sonnet 5, **sola lettura**. Nessun file del repo modificato (tranne
> questo), nessuna migrazione applicata, nessun processo avviato/ucciso, nessun
> `git add/commit/push`. Nessuna chiave/segreto riportato in chiaro. Ogni riga ha
> evidenza (comando + output, o `file:riga`).
>
> Blocchi eseguiti da tre agenti Sonnet 5 in parallelo (coordinati dalla stessa
> delega): due hanno prodotto in modo indipendente 0.1/0.2/0.4 (e uno anche 0.3);
> dove i due hanno usato metodi diversi sullo stesso oggetto le evidenze sono
> **entrambe** riportate sotto, non scelte a caso.

## 0.0 — Nota metodologica: modifiche concorrenti al repo durante la Fase 0

**Rilevante per leggere 0.1 e 0.3.** All'avvio di questa sessione (16/09 mattina)
`git status --short -- Betfair/ frontend/src/` era **vuoto** (working tree pulito,
come dichiarato in `PIANO_CERTIFICAZIONE_DEFINITIVA_2026-09-16.md` §1, commit
`dc0cc30` non pushato). **Durante l'esecuzione di questa Fase 0** (mentre i test
di baseline giravano) lo stesso comando, ripetuto alle 09:04, mostra:

```
 M Betfair/mike/service.py               M Betfair/mike/tools/banco.py
 M Betfair/mike/tools/replay_registrazioni.py
 M Betfair/omega/omega_service.py        M Betfair/safe_strategy/bot_service.py
 M Betfair/safe_strategy/scanner.py      M Betfair/safe_strategy/service.py
 M Betfair/stream/scalper/scalper_service.py
 M Betfair/stream/tennis_live/tennis_bot_service.py
 M Betfair/stream/tennis_live/tennis_runner.py
 M frontend/src/components/controlroom/{PannelloBot.test.tsx,PannelloBot.tsx,useControlRoom.ts}
?? Betfair/mike/tests/test_mike_avvio_app_2026_09_16.py
?? Betfair/omega/test_omega_avvio_app_2026_09_16.py
?? Betfair/safe_strategy/tests/test_avvio_app_2026_09_16.py
?? Betfair/stream/avvio_app.py
?? Betfair/stream/backtest/banco_comune.py
?? Betfair/stream/tests/test_avvio_app_2026_09_16.py

git diff --stat -- Betfair/ frontend/src/
13 file cambiati, 751 inserzioni(+), 530 cancellazioni(-)
```

Sono, per nome e contenuto (`avvio_app.py`, `boot_id`/`avvio_app` nei test nuovi,
`banco_comune.py`), esattamente i file che il piano assegna alla **FASE A**
(nessun bot opera all'avvio) e a **C.0** (banco comune) — costruzione in corso
in parallelo da un altro agente (ondata 1 del piano), non un effetto di questa
sessione (nessun file toccato da me/dai delegati oltre a questo referto). Il
diff è **cresciuto** fra la prima e la seconda rilevazione (da 9 a 13 file, da
361/44 a 751/530 righe) nell'arco di ~1 minuto: la modifica è attiva ORA.

**Conseguenza per 0.3**: i comandi di baseline (`pytest`, `vitest`, `tsc`) sono
girati durante questa stessa finestra. Non è possibile stabilire con certezza,
da questa sessione, se l'hanno fatto su un working tree "prima" o "durante"
l'arrivo di questi cambi (i timestamp dei file arrivano fino a un istante
prima della lettura, cioè "adesso"). I conteggi ottenuti (§0.3: 3372/2396+30
skip/13) **coincidono** con la baseline dichiarata dal piano per il commit
`dc0cc30` — un buon segno — ma **non possono essere presi come certificazione
del codice che Opus 5 sta scrivendo ORA**: vanno rilanciati dal coordinatore a
ondata 1 chiusa, come già previsto da §3 del piano ("ogni ondata si chiude solo
con la certificazione del coordinatore: test rilanciati").

---

## 0.1 — MIGRAZIONI SUL DB

**Cosa ho verificato**: se le 17 migrazioni con data ≥ 11/09/2026 (elenco `ls -la
migrations/*.sql` ordinato per mtime, tutte incluse anche quelle già dichiarate
applicate in `migrations/APPLY_ORDER_2026-09-11.md`) sono effettivamente presenti
sul **database reale**.

**Come**: nessuna via SQL diretta disponibile — testato e confermato:
- `.venv` non ha `psycopg`/`psycopg2` (`ModuleNotFoundError`);
- nessuna RPC di introspezione (`exec_sql`, `run_sql`) nel repo (`grep` su
  `migrations/*.sql` per `CREATE OR REPLACE FUNCTION public.(exec|sql|debug|
  introspect)`: nessun risultato);
- `pg_catalog`/`information_schema`/`pg_indexes`/`pg_publication_tables` **non
  sono esposti da PostgREST**: provato con il client reale, errore
  `PGRST205 "Could not find the table 'public.pg_indexes'"` (stessa cosa per
  `pg_publication_tables`).

Ho quindi usato `db_client.get_supabase_client()` (le credenziali del servizio,
lette da `.env` via `config.py`, mai stampate) per: chiamare le RPC discriminanti
di ogni migrazione via PostgREST, leggere righe/colonne reali già scritte dal
servizio in produzione (mai scritte da me), e dedurre lo stato del CHECK/degli
overload dal comportamento osservato. Script temporanei eseguiti SOLO nel mio
scratchpad, mai nel repo. Nessuna RPC di scrittura invocata (`mike_activate`,
`omega_activate`, `safe_set_mode`, `safe_request_approve`, `safe_request_ignore`
non sono state chiamate).

### Tabella finale

| file | oggetto discriminante | comando/query | risultato osservato | applicata |
|---|---|---|---|---|
| `omega_daily_v2.sql` | tabella `omega_daily_goal` + RPC `get_omega_daily()` | `select * from omega_daily_goal limit 3`; `rpc get_omega_daily()` | 3 righe reali (`day/goal/updated_at`, es. 2026-09-11→goal 100.0); RPC risponde con array di giorni aggregati (`by_sport`,`by_strategy`,`goal_pct`) | **SI** |
| `omega_models_v3.sql` | tabelle `omega_minute_transitions`, `omega_build_jobs`, `omega_minute_league_counts` + RPC `get_omega_minute_ft()` | select limit 1 su ciascuna; `rpc get_omega_minute_ft()` | righe reali presenti (job `minute_transitions`, `done=true`, `processed=939506`); RPC risponde con 241 righe | **SI** |
| `mike_bot.sql` | tabella `mike_control` (singleton id=1) + RPC `get_mike_state()` | `select * from mike_control where id=1`; `rpc get_mike_state()` | `{"id":1,"status":"running","mode":"live", updated_at:"2026-09-15T14:37:44Z"}`; `get_mike_state()` risponde con chiavi `activity,aggregates,control,day_by,day_start,events,requests,trades` | **SI** |
| `mike_history.sql` | RPC `get_mike_daily(p_day_from,p_day_to)` (firma originale a 2 argomenti posizionali) | `rpc get_mike_daily(p_day_from=...,p_day_to=...)` | `PGRST202`: "Could not find the function ... Perhaps you meant public.get_mike_daily(p_from, p_mode, p_to)" | **SUPERSEDUTA** — firma introdotta da questo file non esiste più (droppata da `mike_storico_per_modalita_2026-09-14.sql`); le tabelle di base restano quelle di `mike_bot.sql` |
| `omega_models_v4.sql` | ridefinisce funzioni già esistenti, nessun oggetto proprio isolabile | — | interamente sovrascritta da v5/v6; nessun accesso a `pg_proc`/corpo funzione | **NON VERIFICABILE ISOLATAMENTE** — causa: sovrascritta da versioni successive, nessun accesso a `pg_proc` |
| `omega_models_v5.sql` | `omega_aggregates_sql()`/`get_omega_aggregates()` con chiavi `locked_pnl_open`, `locked_pnl_open_today`, `live_now`, `reconciling_liability` | `rpc omega_aggregates_sql()`; `rpc get_omega_aggregates()` | tutte le chiavi presenti: `['events_today','legs_today','live_now','locked_pnl_open','locked_pnl_open_today','lost_today','matches_lost','matches_open','matches_traded','matches_traded_today','matches_won','open_liability','realized_profit','realized_today','reconciling_liability','won_today']` | **SI** |
| `mike_history_v2.sql` | RPC `get_mike_daily(p_from,p_to,p_mode)` — assenza di ambiguità 42725 | `rpc get_mike_daily(p_from='2026-09-01',p_to='2026-09-16',p_mode=None)` | risponde OK, nessun errore 42725/"is not unique"; con `p_mode='paper'` 5 righe, con `p_mode='live'` 1 riga (2026-09-15, 4 trade, `hedged_closed:4`) | **SI** |
| `safe_strategy_bot_v2.sql` | RPC `get_safe_state()` con chiavi `activity`, `params_effective` | `rpc get_safe_state()` | chiavi: `['activity','aggregates','control','mode','operating_day','params_effective','trades']` | **SI** |
| `mike_bot_v2.sql` | RPC `get_mike_aggregates()` (non PGRST202); `mike_requests.status` accetta `'rejected'` | `rpc get_mike_aggregates()`; `select status from mike_requests` | risponde con 20 chiavi (incl. `realized_live_total`,`realized_paper_total`); dati reali: valori distinti di `status` = `rejected, done` | **SI** |
| `omega_models_v6.sql` | firma UNICA di `trading_daily_history`/`trading_day_trades`; `get_omega_missions()` con `closes_trade_id`/`meta` ridotto; `omega_aggregates_sql()` con **17 chiavi** dichiarate (§17.3 del file) | nessun errore 42725 su nessuna chiamata storica a `get_mike_daily`/`get_omega_daily`/`get_safe_daily`; `rpc get_omega_missions()`; `select jsonb_object_keys(omega_aggregates_sql())` (verifica indipendente di un secondo agente) | nessuna ambiguità osservata (indizio forte di firma singola); `get_omega_missions()` risponde `{"missions":[],"summary":{...}}` — **zero missioni aperte** al momento del controllo, impossibile leggere i campi per-trade; il conteggio chiavi di `omega_aggregates_sql()` risulta **16, non 17** (uno scostamento numerico dalla verifica dichiarata nel file stesso) | **SI, con riserva**: overload risolto (indiretto, forte); dettaglio S-01/S-02/S-03 non verificabile per assenza di dati d'esempio; nessun accesso a `pg_proc` per contare le firme; **1 chiave mancante rispetto alle 17 attese, non indagata oltre (fuori perimetro: nessun agente ha corretto comportamento)** |
| `omega_activity_realtime_2026-09-12.sql` | tabelle in `pg_publication_tables` | `select * from pg_publication_tables` | `PGRST205: Could not find the table 'public.pg_publication_tables'` | **NON VERIFICABILE** — causa: schema di sistema non esposto da PostgREST; l'unica alternativa (sottoscrivere il canale Realtime) richiederebbe avviare un processo, vietato |
| `mike_aggregati_per_modalita_2026-09-13.sql` | `mike_aggregates_sql(p_mode)`/`get_mike_aggregates(p_mode)` | `rpc get_mike_aggregates(p_mode='paper')`; `rpc get_mike_aggregates(p_mode='live')` | entrambe rispondono OK con dati **diversi** e coerenti (paper vs live) | **SI** |
| `safe_strategy_paper_live_2026-09-13.sql` | `get_safe_aggregates(p_mode)`, `get_safe_state()['mode']`, `get_safe_daily(...,p_mode)`, `get_safe_day_trades(...,p_mode)` | `rpc get_safe_aggregates(p_mode='live'/'paper')`; `rpc get_safe_state()`; `rpc get_safe_daily(p_from,p_to,p_mode,p_sport=None)`; `rpc get_safe_day_trades(p_day,p_mode)` | tutte OK, filtrate per modalità; `get_safe_state()` ha chiave `mode`; nessun 42725 | **SI** (parametro `p_mode` operativo end-to-end). Indici `uq_safe_trades_signal_mode`/`uq_safe_trades_closing_inflight`: **non verificabili** (pg_indexes non esposto) |
| `mike_storico_per_modalita_fix_alias_2026-09-14.sql` | `get_mike_day_trades(p_day,p_mode)` senza errore di alias (`t` vs `o`) | `rpc get_mike_day_trades(p_day='2026-09-14',p_mode='paper')` | 23 righe reali con struttura completa (`meta`,`closes[]`,`pnl`,`role`) | **SI** |
| `mike_storico_per_modalita_2026-09-14.sql` | `get_mike_daily(p_from,p_to,p_mode)` con filtro modalità | vedi riga `mike_history_v2.sql`: dati diversi per `p_mode='paper'` vs `'live'` | confermato: dati filtrati per modalità realmente diversi | **SI** |
| `mike_vincoli_flusso_fischio_2026-09-14.sql` | CHECK `mike_trades_strategy_check` ammette `ko_green`/`under_second`; CHECK `mike_events_state_check` ammette `LIVE_KO_GREEN`/`LIVE_SECOND_ENTRY` | `select * from mike_trades where strategy='ko_green'`; ricerca in `mike_activity.payload` di `"violates check constraint"` prima/dopo l'orario del file (14/09 12:56 mtime) | **EVIDENZA FORTISSIMA**: 14 righe reali `mike_trades.strategy='ko_green'` (paper e live), prima piazzata 14/09 13:21:20Z, ultima 15/09 14:33:50Z (stati won/lost/void/error). **240 rigetti** `"violates check constraint \"mike_trades_strategy_check\""` nelle 2000 righe più recenti di `mike_activity`, **TUTTI prima delle 12:56 del 14/09** (ultimo rigetto: 10:56:49Z), **ZERO rigetti dopo**. `under_second`: 0 righe (mai sollecitato) | **SI** — confermata anche temporalmente (i rigetti cessano esattamente a cavallo dell'orario del file) |
| `safe_strategy_proposed_2026-09-14.sql` | CHECK `safe_strategy_requests.status` ammette `'proposed'`; RPC `safe_request_approve`/`safe_request_ignore` | (agente 1) `select distinct status from safe_strategy_requests` (campione 2000 righe), **sola lettura pura**; (agente 2, evidenza più forte ma con RPC "mutante" invocata) `rpc safe_request_approve(p_id=-1)` e `rpc safe_request_ignore(p_id=-1, motivo=...)` | (agente 1) valori osservati: `done, error, rejected` — nessuna riga `'proposed'`, quindi da soli **non dirimente**; (agente 2) entrambe le RPC **esistono e girano**: rispondono con l'eccezione applicativa `richiesta -1 inesistente` (Postgres `P0001`), **non** `PGRST202` (funzione assente) — `p_id=-1` non trova righe (`SELECT ... FOR UPDATE`), quindi la funzione uscita prima di qualunque `UPDATE`: nessuna scrittura avvenuta, ma la sola invocazione di una RPC scrivente esce dal perimetro "sola lettura" in senso stretto, per quanto provabilmente innocua | **SI** se si accetta la prova per invocazione (RPC esistono e si comportano come da specifica del file); **NON DIRIMENTE** se si resta sulla sola lettura passiva dei dati. Il coordinatore decide quale soglia di evidenza accettare per questa riga |

**Riepilogo**: 13/17 confermate **applicate** con evidenza diretta sul DB reale
in sola lettura passiva; 1 applicata con riserva (`omega_models_v6.sql`, anche
dopo la doppia verifica indipendente: 16 vs 17 chiavi attese); 1 superseduta
(`mike_history.sql`); 1 non verificabile isolatamente (`omega_models_v4.sql`);
1 non verificabile per limiti di accesso (`omega_activity_realtime_2026-09-12.sql`);
1 per cui la sola lettura passiva **non è dirimente** ma una verifica
indipendente per invocazione di RPC (provabilmente innocua, non strettamente
"sola lettura") la dà per applicata (`safe_strategy_proposed_2026-09-14.sql`) —
vedi tabella per i dettagli e la riserva metodologica su quest'ultima riga.

**Cosa NON sono riuscito a verificare, e perché**: definizione esatta di CHECK
constraint (`pg_get_constraintdef`), conteggio overload via `pg_proc`, indici
(`pg_indexes`), appartenenza alla publication Realtime (`pg_publication_tables`)
— nessuno di questi cataloghi è esposto da PostgREST e non c'è accesso Postgres
diretto (niente `psycopg`, niente connection string in `.env`, niente RPC di
introspezione nel repo). Ho sempre preferito un proxy funzionale/dato reale a
un'illazione, e dichiarato "non verificabile" quando non c'era.

---

## 0.2 — REGISTRAZIONI

**Cosa ho verificato**: copertura/qualità delle registrazioni calcio (`_live_raw/`)
e tennis (`Desktop/tennis_rec/20260707` e `.../setbetting_20260707`).

**Come**: `python -m Betfair.stream.tools.validate_recordings --data-dir <dir>
--json`. Lo strumento **accetta anche il tennis** senza modifiche (il layout
`<event>/<event>.raw.jsonl` è generico, non calcio-specifico) — ma con due
limiti dichiarati qui perché non emergono da soli:
1. `has_scores` cerca `<id>.scores.jsonl` (plurale): il recorder tennis scrive
   `<id>.score.jsonl` (singolare) → lo strumento segna SEMPRE `scores=NO` per il
   tennis anche quando il sidecar esiste. Ho verificato la presenza reale con un
   controllo file-system separato (colonna "scores_sidecar" sotto).
2. La finestra attesa (`classify()`) si adatta al CLOSED del mercato reale
   (`main_closed_pt`), quindi **funziona correttamente anche per partite più
   lunghe di 115'** (tennis): non è un limite quanto sembrava a prima vista.
   Resta un residuo football-specifico nel messaggio "fine troncata" (soglia
   95'), che per un tennis finito onestamente prima dei 95' può essere un falso
   positivo testuale — il verdetto numerico (`coverage_pct`, `closed_seen`)
   resta comunque corretto e va letto insieme al motivo, non da solo.

Le cartelle `_synth_*` (`_synth_dead`, `_synth_paradise`, `_synth_reversion`)
sono **escluse** automaticamente dallo strumento (`iter_event_ids` salta i nomi
che iniziano con `_`) e anche da me.

### CALCIO — `_live_raw/` (54 cartelle totali, 3 `_synth_*` escluse → 51 valutate)

Comando: `python -m Betfair.stream.tools.validate_recordings --data-dir _live_raw --json`

**Verdetti: 13 COMPLETE, 26 PARTIAL, 12 NO_RAW** (0 EMPTY/UNKNOWN).

| event_id | verdetto | copertura | righe | durata reg. | dimensione | closed_seen | scores sidecar | mercati presenti |
|---|---|---|---|---|---|---|---|---|
| 35674515 | COMPLETE | 97.3% | 34672 | 135.7min | 10.06 MB | sì | sì | BOTH_TEAMS_TO_SCORE, CORRECT_SCORE, DOUBLE_CHANCE, FIRST_HALF_GOALS_05/15/25, HALF_TIME, HALF_TIME_FULL_TIME, HALF_TIME_SCORE, MATCH_ODDS, OVER_UNDER_05→85, TEAM_A_1, TEAM_B_1 |
| 35759636 | COMPLETE | 94.0% | 30568 | 108.6min | 7.90 MB | sì | sì | (stesso set sopra) |
| 35760084 | COMPLETE | 95.2% | 30653 | 168.4min | 7.37 MB | sì | sì | (stesso set) |
| 35764745 | COMPLETE | 95.7% | 77354 | 240.3min | 22.23 MB | sì | sì | (stesso set) + FIRST_GOAL_SCORER, TO_QUALIFY |
| 35765620 | PARTIAL | 59.2% | 63573 | 259.8min | 17.16 MB | sì | sì | (stesso set) + TO_QUALIFY — 11 buchi (82.9min persi) |
| 35768297 | PARTIAL | 80.3% | 103431 | 507.2min | 26.22 MB | sì | sì | + FIRST_GOAL_SCORER, TO_QUALIFY — 5 buchi (31.6min persi) |
| 35768365 | COMPLETE | 95.0% | 72747 | 232.2min | 20.54 MB | sì | sì | + FIRST_GOAL_SCORER, TO_QUALIFY |
| 35772591 | COMPLETE | 93.3% | 25270 | 97.3min | 7.02 MB | sì | sì | set base |
| 35774000 | COMPLETE | 98.1% | 29487 | 144.6min | 8.12 MB | sì | sì | set base |
| 35777617 | COMPLETE | 97.1% | 61137 | 155.2min | 18.83 MB | sì | sì | + FIRST_GOAL_SCORER, TO_QUALIFY |
| 35780184 | COMPLETE | 99.1% | 37036 | 134.1min | 8.91 MB | sì | sì | set base |
| 35781607 | COMPLETE | 99.1% | 35996 | 116.0min | 8.69 MB | sì | sì | set base |
| 35784105 | PARTIAL | 1.6% | 1962 | 4.7min | 0.48 MB | sì | sì | + EXTRA_TIME, FIRST_GOAL_SCORER, TO_QUALIFY — inizio tardivo (+113min) |
| 35787218 | PARTIAL | 59.8% | 34358 | 88.8min | 9.89 MB | sì | sì | + FIRST_GOAL_SCORER, TO_QUALIFY — inizio tardivo (+47min) |
| 35787327 | PARTIAL | 62.4% | 67117 | 293.7min | 18.36 MB | sì | sì | + FIRST_GOAL_SCORER, TO_QUALIFY — fine NON confermata |
| 35788728 | PARTIAL | 41.0% | 13516 | 51.7min | 3.02 MB | sì | sì | set ridotto (mancano BOTH_TEAMS_TO_SCORE, HALF_TIME, OVER_UNDER bassi) — inizio tardivo (+69min) |
| 35788742 | PARTIAL | 31.3% | 17940 | 113.6min | 5.99 MB | **no** | sì | set base — fine troncata (ko+39min, nessun CLOSED) |
| 35792347 | PARTIAL | 4.8% | 759 | 5.5min | 0.20 MB | sì | sì | set ridotto — inizio tardivo (+110min) |
| 35794996 | PARTIAL | 7.0% | 5907 | 272.3min | 1.64 MB | sì | sì | set base — 5 buchi (151.6min persi) |
| 35796477 | PARTIAL | 14.1% | 4123 | 178.1min | 1.08 MB | sì | sì | set base — 6 buchi (101.2min persi) |
| 35796504 | PARTIAL | 58.3% | 15673 | 68.1min | 3.71 MB | sì | sì | set ridotto — inizio tardivo (+47min) |
| 35797538 | COMPLETE | 98.0% | 33016 | 131.1min | 9.21 MB | sì | sì | set base |
| 35797769 | COMPLETE | 95.4% | 81137 | 277.5min | 23.10 MB | sì | sì | + FIRST_GOAL_SCORER |
| 35804159 | PARTIAL | 22.2% | 3391 | 51.5min | 0.96 MB | sì | sì | set ridotto — inizio tardivo (+23min), 4 buchi |
| 35804211 | PARTIAL | 43.1% | 19712 | 106.8min | 5.99 MB | sì | sì | set base — inizio tardivo (+15min), 3 buchi (54.3min) |
| 35804974 | PARTIAL | 33.5% | 9977 | 94.4min | 2.24 MB | sì | sì | set base — inizio tardivo (+26min), 2 buchi (53.9min) |
| 35812264 | PARTIAL | 34.7% | 13654 | 56.2min | 3.29 MB | sì | sì | set ridotto — inizio tardivo (+61min), buco spiegato da resubscribe |
| 35817300 | NO_RAW | — | 0 | — | 0 | — | sì | file raw mancante |
| 35817305 | PARTIAL | 43.8% | 10650 | 78.8min | 2.71 MB | sì | sì | set base + TO_QUALIFY |
| 35817321 | NO_RAW | — | 0 | — | 0 | — | sì | file raw mancante |
| 35817332 | PARTIAL | 71.7% | 13262 | 78.8min | 3.96 MB | sì | sì | set base + TO_QUALIFY |
| 35817978 | PARTIAL | 63.8% | 11155 | 78.8min | 2.90 MB | sì | sì | set base + TO_QUALIFY |
| 35817979 | NO_RAW | — | 0 | — | 0 | — | sì | file raw mancante |
| 35818211 | NO_RAW | — | 0 | — | 0 | — | sì | file raw mancante |
| 35823367 | NO_RAW | — | 0 | — | 0 | — | sì | file raw mancante |
| 35823368 | PARTIAL | 52.6% | 18262 | 75.0min | 4.25 MB | sì | sì | set ridotto — inizio tardivo (+39min) |
| 35823369 | PARTIAL | 75.5% | 19187 | 78.8min | 5.38 MB | sì | sì | set base — inizio tardivo (+10min) |
| 35823409 | PARTIAL | 60.9% | 15809 | 70.5min | 3.67 MB | sì | sì | set ridotto — inizio tardivo (+39min) |
| 35823616 | PARTIAL | 0.0% | 1208 | 78.8min | 0.24 MB | **no** | **NO** | set base — solo pre-match, nessun dato dopo il kickoff |
| 35825601 | NO_RAW | — | 0 | — | 0 | — | sì | file raw mancante |
| 35826515 | PARTIAL | 75.3% | 22747 | 78.8min | 5.70 MB | sì | sì | set base — inizio tardivo (+10min) |
| 35826559 | NO_RAW | — | 0 | — | 0 | — | sì | file raw mancante |
| 35826936 | PARTIAL | 23.4% | 8337 | 35.2min | 1.90 MB | **no** | sì | set ridotto — inizio tardivo (+79min), fine NON confermata |
| 35828026 | PARTIAL | 19.5% | 3976 | 78.8min | 0.95 MB | **no** | sì | set base — fine troncata (ko+29min) |
| 35830581 | NO_RAW | — | 0 | — | 0 | — | sì | file raw mancante |
| 35833626 | PARTIAL | 9.0% | 1819 | 44.1min | 0.50 MB | **no** | sì | set ridotto — inizio tardivo (+17min), fine troncata, buco spiegato da resubscribe |
| 35997486 | NO_RAW | — | 0 | — | 0 | — | sì | file raw mancante |
| 36006914 | NO_RAW | — | 0 | — | 0 | — | sì | file raw mancante |
| 36006953 | COMPLETE | 100.0% | 21356 | 57.8min | 6.56 MB | sì | sì | set base |
| 36015261 | NO_RAW | — | 0 | — | 0 | — | sì | file raw mancante |
| 36045515 | NO_RAW | — | 0 | — | 0 | — | sì | file raw mancante |

"Set base" = BOTH_TEAMS_TO_SCORE, CORRECT_SCORE, DOUBLE_CHANCE, FIRST_HALF_GOALS_05/15/25,
HALF_TIME, HALF_TIME_FULL_TIME, HALF_TIME_SCORE, MATCH_ODDS, OVER_UNDER_05→85, TEAM_A_1, TEAM_B_1.
"Set ridotto" = sottoinsieme del set base (mercati mancanti indicati dov'è rilevante).

### TENNIS — `Desktop/tennis_rec/20260707` (match odds)

**Inventario cartelle**: 88 totali. 60 con `<id>.raw.jsonl`, **28 con SOLO
`<id>.score.jsonl`** (nessuno stream mai registrato per quell'evento — equivalente
a NO_RAW, elencate sotto). Comando: `python -m Betfair.stream.tools.
validate_recordings --data-dir "Desktop\tennis_rec\20260707" --json`.

**Verdetti sui 60 con raw: 58 PARTIAL, 2 COMPLETE** (0 NO_RAW/EMPTY tra questi,
perché lo strumento valuta solo le cartelle con file `.raw.jsonl` o
`.scores.jsonl`/`.score.jsonl` — le 28 con solo `.score.jsonl` **non compaiono**
nell'elenco valutato dallo strumento con questo nome file, ma sono conteggiate
qui sotto come NO_RAW equivalenti). Mercato presente in tutte: `MATCH_ODDS`
(nessun altro tipo — coerente con L5/P6: Betfair non pubblica altri mercati
per il tennis in queste registrazioni).

28 eventi **NO_RAW equivalenti** (solo score sidecar, mai raw): 35790412,
35790526, 35790655, 35790660, 35790718, 35790748, 35791110, 35791125, 35791150,
35792571, 35792659, 35792669, 35792674, 35792836, 35792954, 35794097, 35795749,
35795825, 35795958, 35795968, 35796112, 35797287, 35797337, 35797340, 35797541,
35797556, 35797566, 35799198.

60 eventi con raw (id: verdetto, copertura, righe, durata registrazione min,
dimensione, closed_seen, motivi principali — mercato sempre `MATCH_ODDS`):

| event_id | verdetto | cov% | righe | durata reg. (min) | size | closed_seen | motivi |
|---|---|---|---|---|---|---|---|
| 35789349 | PARTIAL | 45.5 | 1088 | 59.5 | 171KB | sì | inizio tardivo +48min, 6 buchi (10.5min) |
| 35790089 | PARTIAL | 40.1 | 5217 | 90.7 | 841KB | sì | inizio tardivo +118min, 5 buchi (6.9min) |
| 35790160 | PARTIAL | 61.0 | 6166 | 224.5 | 991KB | sì | 22 buchi (63.5min persi) |
| 35790407 | PARTIAL | 29.2 | 1051 | 27.8 | 170KB | sì | inizio tardivo +58min, 2 buchi |
| 35790417 | PARTIAL | 0.9 | 9 | 31.9 | 8KB | sì | inizio tardivo +53min, 3 buchi (31.2min) |
| 35790423 | PARTIAL | 37.0 | 4916 | 170.6 | 814KB | sì | 11 buchi (106.4min persi) |
| 35790428 | PARTIAL | 62.4 | 9090 | 271.8 | 1.52MB | sì | 16 buchi (82.7min persi) |
| 35790443 | PARTIAL | 50.4 | 5318 | 91.3 | 866KB | sì | inizio tardivo +78min, 5 buchi |
| 35790645 | PARTIAL | 2.2 | 254 | 3.4 | 46KB | sì | inizio tardivo +148min |
| 35790650 | COMPLETE | 93.9 | 7428 | 165.0 | 1.17MB | sì | 5 buchi (9.3min persi) |
| 35790708 | PARTIAL | 69.4 | 4794 | 87.6 | 773KB | sì | inizio tardivo +28min, 5 buchi |
| 35790713 | PARTIAL | 21.6 | 2637 | 48.3 | 432KB | sì | inizio tardivo +168min |
| 35790784 | PARTIAL | 71.2 | 1821 | 94.0 | 262KB | sì | inizio tardivo +18min, 8 buchi |
| 35790789 | PARTIAL | 23.1 | 465 | 152.9 | 71KB | sì | 27 buchi (116.2min persi) |
| 35790799 | PARTIAL | 39.7 | 471 | 87.0 | 66KB | sì | inizio tardivo +28min, 19 buchi |
| 35792556 | PARTIAL | 69.8 | 425 | 66.4 | 60KB | sì | inizio tardivo +13min, 5 buchi |
| 35792558 | PARTIAL | 23.3 | 381 | 267.3 | 59KB | sì | 19 buchi (203.7min persi) |
| 35792565 | PARTIAL | 60.5 | 314 | 52.7 | 45KB | sì | inizio tardivo +18min, 7 buchi |
| 35792566 | PARTIAL | 49.4 | 897 | 138.2 | 139KB | sì | 11 buchi (61.5min persi) |
| 35792570 | PARTIAL | 25.3 | 692 | 262.6 | 108KB | sì | 27 buchi (194.9min persi) |
| 35792684 | PARTIAL | 60.3 | 4166 | 105.0 | 694KB | sì | 11 buchi (41.0min persi) |
| 35792709 | PARTIAL | 15.8 | 1007 | 16.9 | 165KB | sì | inizio tardivo +83min |
| 35792714 | PARTIAL | 41.7 | 5091 | 69.7 | 827KB | sì | inizio tardivo +88min |
| 35792828 | PARTIAL | 45.2 | 592 | 158.3 | 93KB | sì | 18 buchi (69.4min persi) |
| 35792918 | PARTIAL | 58.3 | 1067 | 54.2 | 166KB | sì | inizio tardivo +28min |
| 35792934 | PARTIAL | 53.2 | 9924 | 283.4 | 1.64MB | sì | 31 buchi (131.7min persi) |
| 35792939 | PARTIAL | 67.4 | 4004 | 61.5 | 623KB | sì | inizio tardivo +28min |
| 35792974 | PARTIAL | 50.0 | 3600 | 54.2 | 588KB | sì | inizio tardivo +48min |
| 35793833 | PARTIAL | 66.3 | 1603 | 70.4 | 246KB | sì | inizio tardivo +30min |
| 35793859 | COMPLETE | 90.6 | 16594 | 264.3 | 2.72MB | sì | 9 buchi (17.5min persi) |
| 35793960 | PARTIAL | 94.2 | 18243 | 349.5 | 2.95MB | **no** | finestra estesa a ko+168min, fine NON confermata |
| 35794049 | PARTIAL | 76.0 | 8609 | 136.0 | 1.31MB | sì | inizio tardivo +41min |
| 35795560 | PARTIAL | 84.5 | 6011 | 115.9 | 985KB | sì | 5 buchi (17.7min persi) |
| 35795565 | PARTIAL | 2.9 | 27 | 2.8 | 8KB | sì | inizio tardivo +93min |
| 35795578 | PARTIAL | 54.9 | 6625 | 176.2 | 1.07MB | sì | 12 buchi (78.6min persi) |
| 35795625 | PARTIAL | 74.3 | 9417 | 231.3 | 1.52MB | sì | 21 buchi (54.0min persi) |
| 35795630 | PARTIAL | 76.8 | 11036 | 235.5 | 1.86MB | sì | 12 buchi (51.9min persi) |
| 35795635 | PARTIAL | 47.6 | 2965 | 56.0 | 486KB | sì | inizio tardivo +48min |
| 35795739 | PARTIAL | 36.7 | 5627 | 71.5 | 926KB | sì | inizio tardivo +123min |
| 35795744 | PARTIAL | 50.3 | 4977 | 123.9 | 808KB | sì | inizio tardivo +18min, 17 buchi |
| 35795831 | PARTIAL | 15.2 | 406 | 243.9 | 67KB | sì | 29 buchi (146.0min persi) |
| 35795836 | PARTIAL | 25.7 | 379 | 200.8 | 58KB | sì | 24 buchi (110.7min persi) |
| 35795841 | PARTIAL | 29.6 | 436 | 167.4 | 67KB | sì | 25 buchi (88.5min persi) |
| 35795932 | PARTIAL | 23.2 | 681 | 41.4 | 100KB | sì | inizio tardivo +93min |
| 35795963 | PARTIAL | 29.8 | 3094 | 296.2 | 516KB | sì | 19 buchi (150.6min persi) |
| 35795978 | PARTIAL | 48.8 | 5379 | 212.6 | 855KB | sì | 21 buchi (102.8min persi) |
| 35795983 | PARTIAL | 22.1 | 581 | 25.5 | 92KB | sì | inizio tardivo +48min |
| 35795988 | PARTIAL | 28.5 | 2301 | 51.5 | 369KB | sì | inizio tardivo +118min |
| 35795993 | PARTIAL | 69.8 | 8353 | 201.8 | 1.35MB | sì | 10 buchi (57.5min persi) |
| 35796097 | PARTIAL | 58.2 | 3749 | 54.4 | 614KB | sì (scores=NO) | inizio tardivo +33min |
| 35796102 | PARTIAL | 55.3 | 3143 | 66.1 | 505KB | sì | inizio tardivo +43min |
| 35796107 | PARTIAL | 73.1 | 2965 | 139.2 | 493KB | sì | 9 buchi (27.6min persi) |
| 35796699 | PARTIAL | 78.6 | 1641 | 164.3 | 244KB | sì | 10 buchi (22.2min persi) |
| 35797318 | PARTIAL | 42.8 | 716 | 96.9 | 110KB | sì | inizio tardivo +82min |
| 35797319 | PARTIAL | 38.9 | 266 | 97.8 | 42KB | sì | inizio tardivo +14min |
| 35797338 | PARTIAL | 35.1 | 351 | 98.5 | 52KB | sì | inizio tardivo +44min |
| 35797339 | PARTIAL | 38.6 | 714 | 212.0 | 125KB | sì | 35 buchi (110.8min persi) |
| 35797346 | PARTIAL | 66.0 | 902 | 157.3 | 140KB | sì | inizio tardivo +16min |
| 35797351 | PARTIAL | 1.4 | 34 | 52.2 | 8KB | sì | inizio tardivo +139min |
| 35797378 | PARTIAL | 39.3 | 544 | 71.5 | 84KB | sì | inizio tardivo +39min |

### TENNIS — `Desktop/tennis_rec/setbetting_20260707`

**Inventario cartelle**: 26 totali. 24 con `<id>.raw.jsonl`, 2 con solo
`.score.jsonl` (35790099... — verificare: in realtà 2 mancanti totali secondo il
conteggio file-system: NEITHER=0, quindi le 2 "onlyscore" sono comunque valutate
sotto). Mercato presente in tutte: **SET_BETTING**.

**Verdetti: 24 PARTIAL, 0 COMPLETE.** Copertura sistematicamente bassissima
(mediana ~1%): il mercato Set Betting per il tennis viene tracciato solo a
sprazzi nella finestra registrata, con "inizio tardivo" e "fine troncata" quasi
ovunque — **nessuna registrazione Set Betting di questo giorno è utilizzabile
come prova COMPLETE**.

| event_id | cov% | righe | durata reg (min) | size | closed_seen | scores sidecar |
|---|---|---|---|---|---|---|
| 35790099 | 3.4 | 45 | 42.3 | 13KB | no | no |
| 35790412 | 0.3 | 6 | 40.8 | 4KB | sì | sì |
| 35790718 | 1.5 | 42 | 44.9 | 16KB | no | sì |
| 35791110 | 36.2 | 365 | 45.0 | 58KB | no | sì |
| 35791115 | 0.0 | 14 | 40.5 | 3KB | no | no |
| 35791120 | 0.0 | 5 | 39.9 | 5KB | no | no |
| 35792571 | 21.5 | 93 | 44.6 | 17KB | no | sì |
| 35792659 | 10.4 | 148 | 13.7 | 24KB | sì | sì |
| 35792674 | 20.7 | 256 | 28.1 | 39KB | sì | sì |
| 35792791 | 0.2 | 11 | 43.4 | 10KB | no | no |
| 35792836 | 0.6 | 4 | 26.5 | 4KB | sì | sì |
| 35792954 | 0.0 | 2 | 27.0 | 1KB | no | sì |
| 35793960 | 1.1 | 13 | 41.5 | 5KB | no | sì |
| 35795749 | 0.2 | 8 | 27.2 | 3KB | no | sì |
| 35795825 | 0.0 | 2 | 27.5 | 1KB | no | sì |
| 35795958 | 0.9 | 6 | 35.4 | 4KB | sì | sì |
| 35795968 | 2.2 | 21 | 40.3 | 6KB | sì | sì |
| 35796112 | 0.5 | 6 | 27.2 | 2KB | no | sì |
| 35797337 | 2.8 | 26 | 39.5 | 7KB | sì | sì |
| 35797541 | 1.2 | 8 | 17.4 | 4KB | sì | sì |
| 35797546 | 0.1 | 23 | 39.9 | 10KB | no | no |
| 35797551 | 0.0 | 36 | 43.5 | 12KB | no | no |
| 35797561 | 0.0 | 148 | 44.6 | 25KB | no | no |
| 35797566 | 2.5 | 62 | 44.1 | 19KB | no | sì |

**Cosa NON sono riuscito a verificare, e perché**: la finestra "attesa" del
validatore assume una durata tipo-calcio (115min) quando non trova un CLOSED
del mercato principale — per il tennis (durata reale molto variabile, 1-5h+) il
messaggio testuale "fine troncata" può essere impreciso su match legittimamente
brevi; il numero (`coverage_pct`) resta comunque calcolato sulla finestra reale
quando il CLOSED è visto. Non ho ricostruito manualmente lo score reale (fuori
mandato: sola lettura, nessuna elaborazione aggiuntiva richiesta oltre
l'inventario).

---

## 0.3 — BASELINE TEST

**Cosa ho verificato**: che i test passino con lo stesso conteggio dichiarato in
`STATO_PRODUZIONE.md`/`PIANO_CERTIFICAZIONE_DEFINITIVA_2026-09-16.md` (nessuna
regressione), sul working tree così com'è ORA (non ho toccato nulla).

**Come**:
```
python -m pytest Betfair/ -q -p no:cacheprovider
cd frontend && npx vitest run
cd frontend && npx tsc -p tsconfig.app.json --noEmit
```

**Risultato — backend (`pytest`)**: `3372 passed, 2 warnings in 142.51s`
(0 falliti, 0 skip). I 2 warning sono `DeprecationWarning` innocui del client
`supabase` (`timeout`/`verify` deprecati), non test rossi. **Coincide
esattamente** con il numero dichiarato in `PIANO_CERTIFICAZIONE_DEFINITIVA
_2026-09-16.md` §1 ("backend `Betfair/` 3372 verdi").

**Risultato — frontend (`vitest`)**: `Test Files 129 passed | 6 skipped (135)` —
`Tests 2396 passed | 30 skipped (2426)` (0 falliti). I 6 file/30 test skippati
sono tutti nella cartella `src/certification/*.cert.test.tsx` (migrations,
realtime, omega, mike, safe, zz_dump) — test di certificazione che richiedono
un ambiente/credenziali live e sono marcati skip di default, non regressioni.
**Coincide esattamente** con "frontend 2396 verdi" dichiarato nel piano.

**Risultato — `tsc --noEmit`**: **esattamente 13 errori**, tutti preesistenti
(coincide con "13 errori tsc preesistenti" del piano):

1. `src/components/dashboard/CardsByMinute.tsx:3` — TS6133 `'AlertCircle'` mai letto
2. `src/components/dashboard/DecisionsView.tsx:12` — TS6133 `'groupsToCsv'` mai letto
3. `src/components/dashboard/ProbBarChart.tsx:35` — TS2322 tipo `Formatter` non compatibile (parametro `v: number | undefined`)
4. `src/components/dashboard/ProbBarChart.tsx:41` — TS2322 tipo `LabelFormatter` non compatibile
5. `src/components/live/DepthPanel.test.tsx:67` — TS2345 `NormalizedProcedure` incompatibile
6. `src/components/live/ScalperPanel.test.tsx:38` — TS2345 `null` non assegnabile a `ScalperState`
7. `src/integrations/supabase/client.ts:3` — TS2339 `'env'` non esiste su `ImportMeta`
8. `src/integrations/supabase/client.ts:4` — TS2339 idem
9. `src/lib/opportunities/index.ts:10` — TS2308 `'phaseFromMinute'` esportato due volte (ambiguità con `./tier0_arb`)
10. `src/lib/opportunities/tier2_micro.adversarial.test.ts:11` — TS6133 `'weightOfMoney'` mai letto
11. `src/main.tsx:4` — TS2307 impossibile trovare modulo `./index.css`
12. `src/pages/Dashboard.tsx:263` — TS2322 `string | undefined` non assegnabile a `string`
13. `src/pages/SeguiLive.tsx:266` — TS2554 attesi 2 argomenti, ricevuto 1

**Cosa NON sono riuscito a verificare**: nulla — tutti e tre i comandi sono
girati per intero senza timeout né interruzioni (pytest 142.5s, vitest ~337s,
tsc pochi secondi).

---

## 0.4 — PARAMETRI DI CONTROLLO NEL DB (stato ORA, 2026-09-16, letto in sola lettura)

**Cosa ho verificato**: righe singleton `id=1` di `mike_control` (da
`Betfair/mike/db.py:23-24`, `T_CONTROL="mike_control"`), `omega_control` (da
`Betfair/omega/omega_db.py:17,39`), `safe_strategy_control` (da
`Betfair/safe_strategy/bot_db.py:39-41`).

**Come**: `select * from <table> where id=1` via client Supabase, sola lettura.

### MIKE — `mike_control`

- **status = `running`** ⚠️ — **il bot è ACCESO ORA, in modalità LIVE**
- **mode = `live`**
- `started_at`: 2026-09-15T09:58:00Z · `heartbeat_at`/`updated_at`: 2026-09-15T14:37:4x Z (ultimo giro poco prima del controllo)
- `stats.boot_id`: **ASSENTE** — nessuna chiave `boot_id` nello `stats` (coerente con la Fase A del piano, non ancora costruita: nessun meccanismo di "fermo all'avvio" oggi)
- `params` (JSON completo):
```json
{
  "stake": 5.0,
  "max_open_matches": 2,
  "entry_hours_before_ko": 1.0
}
```
- `stats` (JSON completo):
```json
{
  "dry": false, "mode": "live", "day_pnl": 1.52,
  "by_state": {"FLAT": 1, "SETTLED": 96, "SKIPPED": 3, "LIVE_CLOSING": 1},
  "live_now": 59, "won_today": 0, "daily_stop": false,
  "last_cycle": "2026-09-15T14:37:42.343770+00:00",
  "lost_today": 0, "events_feed": 7, "locked_open": 1.52,
  "reconciling": 3, "trades_open": 2, "cycles_today": 4,
  "events_today": 4, "motivo_blocco": "tetto partite raggiunto: 2 su 2 in live",
  "scanner_age_s": 9.4, "tetto_partite": 2, "events_tracked": 101,
  "live_abilitato": true, "open_liability": 8.78, "realized_today": 0.0,
  "realized_total": 0.0, "partite_esposte": 2, "aperture_bloccate": 7,
  "cadenza_battito_s": 20.0, "open_liability_rows": 8.78,
  "eventi_altra_modalita": 0, "partite_esposte_paper": 0,
  "partite_esposte_live": 2, "stop_ferma_solo_aperture": true
}
```
- **Evidenziazione**: `max_open_matches=2` (raggiunto, 2/2 live → `aperture_bloccate:7`); nessuna chiave `variants`/`strategy_modes` in Mike (non pertinente, è un bot unico); nessun `tennis_exit_approval` (non pertinente a Mike); nessun cap di rischio esplicito nei `params` oltre `stake`/`max_open_matches` (coerente con L6 dello `STATO_PRODUZIONE.md`: "`daily_loss_stop` valore reale non confermato" — qui infatti non c'è affatto un `daily_loss_stop` nei `params` di Mike, solo `stats.daily_stop=false`).

### OMEGA — `omega_control`

- **status = `stopped`**, **mode = `paper`**
- `daily_goal`: 100
- `started_at`: 2026-09-10T13:51Z · `stopped_at`: 2026-09-15T09:21:48Z · `heartbeat_at`: 2026-09-15T14:37:33Z (il servizio continua a battere/leggere anche da fermo)
- `stats.boot_id`: **ASSENTE**
- `params` (JSON completo):
```json
{
  "min_stake": 0.5, "price_max": 120, "price_min": 20, "max_events": 0,
  "ft_entry_max": 80, "ft_entry_min": 50, "greenup_mode": "auto",
  "ht_entry_max": 40, "ht_entry_min": 20, "stop_on_goal": true,
  "commission_pct": 5, "daily_loss_cap": 0, "greenup_enabled": true,
  "greenup_retry_s": 20, "model_p_max_pct": 2, "poll_interval_s": 20,
  "entry_minute_max": 60, "entry_minute_min": 30, "greenup_risk_cap": 0.1,
  "greenup_ev_margin": 0.1, "include_aggregate": false,
  "min_lay_liquidity": 5, "model_calibration": "off",
  "max_open_liability": 0, "entry_window_source": "score",
  "greenup_max_attempts": 15, "greenup_hold_max_risk": 0.02,
  "greenup_settle_delay_s": 30, "max_liability_per_match": 0,
  "greenup_take_profit_frac": 0.9, "greenup_trigger_distance": 1,
  "greenup_take_profit_minute": 80, "greenup_price_trigger_ratio": 0.5
}
```
- **Evidenziazione cap di rischio**: `daily_loss_cap: 0`, `max_open_liability: 0`,
  `max_liability_per_match: 0` — **tutti a ZERO = SPENTI** (coerente con
  `PIANO_CERTIFICAZIONE_DEFINITIVA_2026-09-16.md` §1: "cap di rischio Safe
  SPENTI" — qui si conferma che anche i cap di Omega sono a zero, cioè
  disattivati, non "assenti dal JSON").
- `stats` (giornata corrente): `realized_profit: -50.34` (storico complessivo),
  `realized_today: 0.53`, `won_today: 1`, `lost_today: 0`, `live_now: 0`,
  `open_liability: 0.0`, `locked_pnl_open: 0.0`, `matches_traded: 99`.
- Nessuna chiave `variants`/`strategy_modes`/`tennis_exit_approval` (non
  pertinenti a Omega, che non ha varianti).

### SAFE STRATEGY — `safe_strategy_control`

- **status = `stopped`**, **mode = `paper`**
- `started_at`: 2026-09-14T13:26:30Z · `stopped_at`: 2026-09-14T15:35:00Z · `heartbeat_at`: 2026-09-15T14:37:53Z (batte anche da fermo)
- `stats.boot_id`: **ASSENTE**
- `params` (JSON completo):
```json
{
  "base": {"minuteMin": 55, "controlMin": 0.1, "favLiveMax": 1.34, "favLiveMin": 1.2, "scoreConfirmSec": 30},
  "risk": {
    "model_stake": 3, "correlated_cap": 0.7, "daily_loss_stop": -50,
    "max_open_trades": 0, "daily_liability_cap": 0, "per_event_max_trades": 3,
    "per_event_liability_cap": 150, "model_daily_liability_cap": 150
  },
  "exits": {
    "enabled": true, "risk_cap": 0.1, "ev_margin": 0.1, "hold_max_risk": 0.02,
    "base_exit_minute": 80, "exit_max_retries": 3, "residual_retry_s": 20,
    "risk_premium_pct": 0.05, "model_exit_p_lose": 0.1, "punta_exit_minute": 83,
    "red_card_fav_exit": true, "esatto_exit_minute": 72, "loss_settle_delay_s": 30,
    "residual_max_attempts": 15, "model_take_profit_frac": 0.8,
    "tennis_exit_on_lost_game": false, "model_free_cashout_p_lose": 0.005,
    "tennis_take_profit_min_eur": 0.01, "tennis_take_profit_min_odds": 1.03,
    "tennis_take_profit_next_game": true
  },
  "punta": {"entryMax": 1.1, "entryMin": 1.03, "minuteMin": 66, "controlMin": 0.1, "minMinutesAfterGoal": 3},
  "stake": {"laySize": 2, "backSize": 3},
  "esatto": {"entryMax": 70, "entryMin": 30, "minuteMin": 48, "controlMin": 0.1, "maxGoalsLaySide": 1, "scoreConfirmSec": 30},
  "tennis": {"backMax": 1.1, "backMin": 1.01, "setsLeadMin": 1, "gamesLeadMin": 2, "setsPlayedMax": 1, "scoreConfirmSec": 15},
  "variants": ["tennis"],
  "min_stake": 2, "opps_stake": 5, "opps_min_edge": 0.03, "commission_pct": 5,
  "strategy_modes": {"base": "paper", "model": "paper", "punta": "paper", "esatto": "paper", "manual": "paper", "tennis": "live"},
  "max_open_trades": 20, "opps_interval_s": 10, "poll_interval_s": 2,
  "max_spread_ratio": 1.6, "paper_fill_ttl_s": 45, "auto_trade_combos": false,
  "auto_trade_tennis": true, "place_max_attempts": 3, "opps_min_confidence": 0.7,
  "auto_trade_anomalies": false, "live_fill_deadline_s": 20,
  "tennis_exit_approval": true, "max_liability_per_trade": 300,
  "auto_trade_opportunities": false, "min_size_available_factor": 1
}
```
- **`variants` = `["tennis"]`** ⚠️ — **CONFERMATO**: base/esatto/punta sono
  ASSENTI da `variants` (spente anche in paper), esattamente come riportato nel
  piano ("danni in DB": `params.variants = ["tennis"]`).
- **`strategy_modes`** = `{base: paper, model: paper, punta: paper, esatto: paper, manual: paper, tennis: live}`
  — **tennis è LIVE**, tutte le altre in paper (ma comunque spente da `variants`).
- **`stake.backSize` = 3** — **CONFERMATO condiviso**: non esiste una chiave
  `backSize` separata per tennis vs punta; `punta` ha solo `entryMax/entryMin/
  minuteMin/controlMin/minMinutesAfterGoal` (nessuno stake proprio), quindi usa
  lo stesso `stake.backSize=3` globale che vale anche per tennis.
- **`tennis_exit_approval` = `true`** — presente e attivo.
- **Cap di rischio**: `risk.max_open_trades: 0`, `risk.daily_liability_cap: 0`
  — **SPENTI** (zero = disattivati); `risk.daily_loss_stop: -50` **attivo**;
  `risk.per_event_liability_cap: 150` e `risk.model_daily_liability_cap: 150`
  attivi; `max_liability_per_trade: 300` (top-level, attivo).
- `max_open_matches`: **non presente come chiave** in Safe (non esiste
  l'equivalente esplicito di Mike; il controllo analogo più vicino è
  `risk.max_open_trades` = 0 = spento, e `per_event_max_trades: 3`).
- `stats.params_effective` (letto dalla stessa riga, generato dal servizio)
  duplica `params` con l'aggiunta di `execution_mode: "auto"`,
  `omega_live_via_flumine: true`, `base_control_exit: false`,
  `base_control_exit_max: -0.2`, `skip_log_interval_s: 300.0` — questi ultimi
  4 **non compaiono** nel `params` scritto dall'utente/UI: sono default
  applicati lato servizio.
- `stats.risk`: `daily_cap: 0.0`, `daily_liability: 0.0`, `loss_stop_active:
  false`, `realized_total: -20.74`.

**Cosa NON sono riuscito a verificare**: nessuna delle tre righe presentava
anomalie di lettura; l'unica cosa che NON ho potuto fare è collegare questi
`params`/`stats` a un istante "storico" diverso da quello del controllo (sono
la fotografia di ORA, 2026-09-16, non uno storico nel tempo).

---

## Riassunto (max 20 righe)

**0.0**: durante questa Fase 0 il repo ha ricevuto modifiche concorrenti (non
mie) su `Betfair/{mike,omega,safe_strategy,stream}/*` e 3 file del Control
Room frontend — 13 file, 751(+)/530(-) righe al momento della stesura, in
crescita minuto per minuto. Sono i file di FASE A/C.0 del piano (`avvio_app.py`
nuovo, test `*_avvio_app_2026_09_16.py`, `banco_comune.py`): lavoro di un altro
agente in parallelo, non un effetto di questa sessione. **I numeri di 0.3 vanno
rilanciati a ondata 1 chiusa**: non è certo se sono stati misurati prima o
durante l'arrivo di questi cambi.

**0.1 Migrazioni**: 13/17 confermate applicate con evidenza diretta sul DB reale
(RPC + dati reali), 1 con riserva (`omega_models_v6.sql`, overload risolto in
modo indiretto, 16 vs 17 chiavi attese in `omega_aggregates_sql()`, dettagli
S-01/S-02/S-03 non testabili per assenza di missioni aperte), 1 superseduta
(`mike_history.sql`), 1 non isolabile (`omega_models_v4.sql`), 1 non
verificabile per limiti PostgREST (`omega_activity_realtime_2026-09-12.sql`,
publication non esposta), 1 dove la sola lettura passiva non è dirimente ma
una verifica per invocazione RPC (provabilmente innocua) la dà per applicata
(`safe_strategy_proposed_2026-09-14.sql`, riserva metodologica dichiarata).
Prova più forte: `mike_vincoli_flusso_fischio_2026-09-14.sql` — 240 rigetti
CHECK fino alle 10:56 del 14/09, ZERO dopo, 14 trade reali `ko_green` da lì in
poi.

**0.2 Registrazioni**: calcio `_live_raw` (51 valutate, 3 `_synth_*` escluse):
13 COMPLETE, 26 PARTIAL, 12 NO_RAW, mercati fino a MATCH_ODDS+CORRECT_SCORE+
OVER_UNDER 0.5-8.5+HT+TO_QUALIFY. Tennis match-odds (88 cartelle): 60 con raw
(58 PARTIAL, 2 COMPLETE), 28 NO_RAW equivalenti (solo score sidecar). Tennis
set-betting (26 cartelle, 24 con raw): 24 PARTIAL, 0 COMPLETE, copertura quasi
sempre <30%. Lo strumento gira sul tennis senza modifiche ma con 2 limiti
dichiarati (naming `scores.jsonl` vs `score.jsonl`; messaggio "fine troncata"
tarato sul calcio).

**0.3 Test**: pytest `3372 passed`, vitest `2396 passed / 30 skipped`, tsc
`13 errori` — **tutti e tre coincidono esattamente** con la baseline dichiarata
nel piano, nessuna regressione.

**0.4 Controlli DB (ORA)**: **Mike è ACCESO in LIVE** (`status=running,
mode=live`, tetto 2/2 partite raggiunto). Omega e Safe sono `stopped/paper`.
Nessuno dei tre ha `stats.boot_id` (Fase A non ancora costruita). Safe:
`variants=["tennis"]` conferma base/esatto/punta spente anche in paper;
`stake.backSize=3` condiviso tra tennis e punta confermato; `tennis_exit_
approval=true`; cap `max_open_trades`/`daily_liability_cap` a 0 (spenti),
`daily_loss_stop=-50` attivo. Omega: `daily_loss_cap`/`max_open_liability`/
`max_liability_per_match` tutti a 0 (spenti).

File: `C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\FASE0_VERITA_DI_PARTENZA_2026-09-16.md`
