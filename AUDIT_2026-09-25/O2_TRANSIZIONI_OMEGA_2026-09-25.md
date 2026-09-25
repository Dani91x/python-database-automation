# O2 -- Transizioni di Omega sempre aggiornate (25/09/2026)

Delegato Opus, sessione B. Base `origin/master` `f015204`. Niente commit.
Riga O2 dell'audit 24/09 (`AUDIT_2026-09-24/AUDIT_BOT_DATI_ALGORITMI_2026-09-24.md:293`).

## 1. Cosa faceva

| pezzo | stato al 25/09 (verificato dal coordinatore sul DB vero) |
|---|---|
| `omega_minute_transitions` | 1.072.786 righe, 309 leghe, `built_at` max 11/09 11:16 |
| `omega_ht_ft_transitions` | `built_at` max 11/09 09:53 (ricostruzione totale in una istruzione) |
| `omega_build_jobs` `minute_transitions` | `last_id` 1.620.000, `processed` 939.506, `scanned` 1.068.103, `done` = true |
| pg_cron | attivo, nessun job `omega_*` (il blocco `omega_models_v3.sql:237-256` non e' mai stato schedulato) |

Difetto di fondo: il passo (`omega_models_v3.sql:81`, `omega_models_v4.sql:154`) avanza per
`matches.id` e **somma** (`n = n + EXCLUDED.n`). Le partite entrano in `matches` prima di
giocarsi e diventano FT dopo. Quindi:
- "riapri il job per id > last_id" (la proposta A di `M2_DATI_E_PESI_2026-09-17.md:574`)
  **perde per sempre** le partite gia' scansionate quando non erano finite: 1.556 fra le
  7.688 FT dal 11/09;
- "ripassa i lotti" le **conta due volte**;
- `_reset()` svuota le tabelle lette dai bot per 27 minuti (veto con n parziali).

## 2. Cosa fa (migrazione `migrations/omega_transitions_catchup_2026-09-25.sql`)

| oggetto | ruolo |
|---|---|
| `omega_transitions_ledger` (PK `fixture_id`) | registro: `ht_ft_at`, `minute_at` (= il `target text[]` del brief, come due colonne indicizzabili), `minute_rejects`, `minute_checked_at` |
| `omega_minute_transitions_raw`, `omega_ht_ft_transitions_raw` | conteggi grezzi, tutte le leghe, mai potati; CHECK `n > 0` |
| `omega_transitions_league_counts` | partite contate per lega (0 = tutte) |
| `omega_transitions_state` | cursori, `bootstrap_done_at`, `published_at`, `min_league_matches` |
| `omega_transitions_runs` | referto per giro (il "`omega_build_jobs`-like") |
| `omega_transitions_step(p_lo, p_hi, p_ids, p_retry_hours)` | un lotto: conta cio' che il registro non ha; grezzo + registro + contatori (+ pubblicato se pubblicato) nella stessa transazione |
| `omega_transitions_nightly(p_budget_s, p_dry_run, p_batch, p_hot_days, p_sweep_ids, p_retry_hours)` | fasi A finestra calda / B cursore id / C giro di controllo, fino a fine lavoro o budget |
| `omega_transitions_publish('PUBBLICA', p_min_league_matches)` / `_unpublish('RITORNA')` | pubblicazione una tantum (con copia dell'11/09) e ritorno |
| `omega_transitions_status()`, `_ledger_counts()`, `_compare('pre'|'post')` | letture per la verifica (service_role) |
| `omega_transitions_schedule(bool)` | pg_cron `0 4 * * *`, idempotente, guardia se pg_cron manca; chiamata a fine migrazione |
| vecchi `omega_build_*` | stesse firme, corpo che rifiuta ("dismessa il 25/09") |

Idempotenza: i flag `need_htft`/`need_min` di ogni partita vengono dal registro; il
registro si aggiorna con `coalesce(valore_esistente, nuovo)` nella stessa transazione dei
conteggi; un lucchetto consultivo (`hashtext('omega_transitions')`) serializza giro, passo e
pubblicazione. Rilanciare, anche riportando i cursori a zero, non cambia nessun n (provato,
§5).

Regola "leghe con poche partite -> solo globale", proposta: il grezzo tiene tutte le leghe;
il pubblicato contiene globale + leghe con `n_minute >= min_league_matches` (soglia fissata
alla pubblicazione, 1000 come prima). Le partite contate solo crescono, quindi una lega puo'
solo entrare: quando un passo la porta oltre soglia, viene copiata **per intera** dal grezzo
(`new_leagues` nel referto). Cambiare soglia = ripubblicare. Nessun conteggio grezzo si
cancella mai.

Le RPC `get_omega_minute_ft` e `get_omega_ht_ft` non sono ridefinite (test di contratto).

## 3. Scelta: ricostruzione una tantum (consigliata, implementata) contro stima

| | A. ricostruzione una tantum con registro (IMPLEMENTATA) | B. stima: adottare le tabelle dell'11/09 e marcare "contate" le partite presunte |
|---|---|---|
| cosa | si riconta tutto nel grezzo, a lotti, entro il budget di ogni notte; si pubblica dopo la verifica | registro riempito con "FT con id <= 1.620.000", tabelle lasciate cosi' |
| esattezza | esatta per costruzione: grezzo = costruttore originale da zero (provato riga per riga, §5) | non ricostruibile quali partite fossero FT l'11/09: le 1.556 FT tardive con id vecchio verrebbero marcate contate senza esserlo (perse per sempre); partite allora incoerenti (eventi mancanti) e oggi coerenti idem |
| leghe sotto soglia | grezzo completo per le 876 leghe potate l'11/09 (1.185 in `omega_minute_league_counts`, 309 pubblicate): una lega che supera 1000 si pubblica con tutti i suoi conteggi | le celle delle leghe potate sono state CANCELLATE l'11/09: una lega che supera la soglia verrebbe pubblicata con i soli conteggi post-11/09 (Wilson su n sbagliati) |
| verificabile | si': somma bucket 0 = registro per ogni lega, confronto cella per cella con l'11/09 | no: l'invariante "somma = registro" e' falsa per costruzione, di un errore ignoto |
| costo | una volta ~27-73 min di lavoro DB spalmati su 3-8 notti da 10 min (§4) + pubblicazione | quasi zero |
| rischio per i bot | nessuno fino alla pubblicazione (tabelle dei bot intatte); pubblicazione atomica e reversibile | nessuno subito, errore permanente nei conteggi |

## 4. Carico stimato

Base misurata: l'11/09 il costruttore originale ha impiegato **27 min** per 1.620.000 id
(1.068.103 FT scandite, 939.506 valide). Costo relativo della ricostruzione nuova sugli
stessi dati sintetici, in PGlite (`AUDIT_2026-09-25/O2_misura_costo_pglite_2026-09-25.mjs`,
PC condiviso, misure rumorose): per passo **1,05x** (profilo di 3 passi da 5.000 id),
**1,48x** e **2,70x** (ricostruzione completa di 20.000 partite, due lanci). Il di piu' e'
il registro (una riga per partita FT, ~1,07 M righe) e il grezzo HT->FT per passo.

| | prima notte / ricostruzione | notte normale |
|---|---|---|
| tempo DB totale | 27 x (1,05-2,70) = **28-73 min**, a 600 s per notte = **3-8 notti** (accelerabile a mano) | fase A ~1.200 partite (550 FT/giorno x 10 gg non contate + scartate da ritentare) ~2-5 s; fase C 100.000 id = 20 passi ~20-40 s (11/09: "1-2 s per 5.000 id"). **~30-60 s** |
| righe lette | `matches` 1,62 M per PK a range (una volta); gol di ~1,07 M partite via `idx_match_events_goal_fixture` (come l'11/09) | ~5.500 righe `matches` via indice `fixture_date` + 100.000 per PK (1/16 della tabella); gol di ~1.200 + ~8.000 scartate da ricontrollare (128.597 scartate l'11/09 / 16) |
| righe scritte | registro ~1,07 M; grezzo minuto ~1,1-1,8 M (309 leghe pubblicate + 876 potate + globale; la parte potata non e' misurabile senza DB); grezzo HT->FT ~140 k | registro ~1-10 k upsert; grezzo e pubblicato qualche migliaio di celle ciascuno |
| una tantum alla pubblicazione | DELETE 1,07 M + INSERT ~1,1 M (minuto), 136 k + 140 k (HT->FT), copia dell'11/09 1,2 M righe; poi `VACUUM (ANALYZE)` | - |

La **prova a vuoto** sul DB vero (`nightly(60, true)`) da' la velocita' reale: notti per la
ricostruzione = `max_id / ((id_cursor_to - id_cursor_from) / elapsed_s x 600)`.

Transazione: un giro = una transazione con **una** sola sottotransazione (il blocco che
annulla dry-run ed errori): niente subxact per passo (oltre 64 per transazione degradano gli
snapshot di tutto il DB).

Orario **04:00 UTC** (06:00 Roma): le action di GitHub partono con un ritardo mediano di ~5 h
sul cron (`AUDIT_2026-09-25/ACTIONS_DIAGNOSI_E_FIX.md` §1): Daily mediana reale ~05:58 UTC,
Today ~07:35, Results ~08:27. Alle 04:00 di norma il DB e' fermo. Caso peggiore (ritardo
minimo 0,6 h): Daily 01:48 + p90 26,7 min = finito entro 02:20; Today da 02:54 per 66-253
min puo' sovrapporsi; il lunedi' Poisson (03:27 + ritardo). Betfair alle 06:00 di Roma: calcio
live quasi assente. Conseguenza sul ritardo del dato: le partite di ieri le scrive la Daily
verso le 06:00 UTC, quindi entrano nelle tabelle la notte dopo (ritardo ~1-2 giorni, contro i
14 di oggi). Alternativa se si vuole il dato del giorno stesso: 10:30 UTC, dopo Results
(decisione dell'utente).

## 5. Collaudo eseguito

### 5.1 PostgreSQL vero (PGlite 0.5.8 = PostgreSQL 18.3 in wasm), oracolo = costruttore originale
`node AUDIT_2026-09-25/O2_banco_pglite_2026-09-25.mjs <pglite>/dist/index.js` -> **86 controlli, 0 falliti**.
Schema con i tipi del vero (`matches` con `fixture_id integer UNIQUE`, `fixture_date timestamptz`;
`match_events`), `omega_daily_v2` (HT->FT), `omega_models_v3` intero, RPC di `omega_models_v4`.
Scenario: 1.075 partite "all'11/09" con casi limite (NS, FT senza eventi, AET, HT nullo,
minuto 95, autogol, rigori sbagliati, senza lega, lega piccola 40 < soglia 60), costruzione
ORIGINALE -> poi 40 NS che finiscono (id vecchi, finestra calda), 10 NS che finiscono 45
giorni fa (fuori finestra), 10 eventi tardivi, 120 partite nuove -> migrazione (applicata
due volte). Esiti:
- tabelle dei bot identiche all'11/09 dopo la migrazione, durante la ricostruzione, dopo un dry-run;
- dry-run: 1.121 partite contate e **nulla scritto** (registro 0, grezzo 0, cursore 0), riga di referto presente;
- budget 0: nessun passo, `status = budget`;
- ricostruzione: grezzo minuto = **costruttore originale da zero, riga per riga** (7.102 righe), HT->FT idem;
- secondo giro: 0 contate; **cursori riportati a 0 e ripassata completa: n invariato**;
- confronto `pre`: `cells_lower` 0, `cells_missing` 0, partite globali 941 -> 1.121;
- pubblicazione (rifiutata senza 'PUBBLICA'): pubblicato = originale da zero con la stessa soglia;
  `omega_minute_league_counts` uguale; **RPC `get_omega_minute_ft` (5 casi) e `get_omega_ht_ft` (3 casi) uguali all'originale**;
- notti successive: nuove FT contate, **lega 444 da 40 a 70 partite pubblicata per intero** (`new_leagues` 1),
  rilancio immediato = zero variazioni, scartate ritentate il giorno dopo (15 contate), di nuovo = originale da zero;
- senza indice su `fixture_date`: fase calda saltata e dichiarata, la partita finita tardi presa dal giro di controllo;
- ritorno (`unpublish`) = tabelle dell'11/09; con pubblicazione ritirata il giro non tocca le tabelle dei bot; ripubblicazione = originale;
- pg_cron finto (schema `cron` come il vero, riga in `pg_extension`): un solo job `0 4 * * *` col timeout, vecchio `omega_minute_build` tolto, spegnimento;
- invarianti a ogni fase: somma bucket 0 ft = registro per lega e globale (grezzo), HT->FT idem, contatori = registro, nessuna n <= 0, pubblicato = grezzo cella per cella, nessuna lega sotto soglia pubblicata.

### 5.2 Test Python (`test_omega_transizioni_notturne_2026_09_25.py`, 23 test)
Contratto SQL (14) + script di verifica con finto Supabase (9: chiavi e colonne estratte
dal file SQL, max 1000 righe per risposta, `count="exact"`). Comando:
`SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x python -m pytest test_omega_transizioni_notturne_2026_09_25.py -q -p no:cacheprovider` -> **23 passed**.

### 5.3 Falsificazione
Script temporaneo (cancellato dopo l'uso): per ogni mutazione applica la modifica al file,
lancia pytest e, dove indicato, il banco PGlite; poi ripristina il file e controlla lo sha256
(uguale in tutti i 16 casi). Tutti i ripristini verificati; `git diff HEAD` vuoto.

| mutazione | pytest | banco PGlite |
|---|---|---|
| M1 registro non scritto (`WHERE false` sull'INSERT del registro) | verde al primo giro -> test aggiunto -> **ROSSO** | **ROSSO**, 37 KO (primo: somma bucket 0 != registro) |
| M1b INSERT del registro tolto dal testo | ROSSO | - |
| M2 `cron.unschedule` del job nuovo tolto | ROSSO | ROSSO (la migrazione rilanciata va in errore sul job doppio) |
| M3 registro che sovrascrive `ht_ft_at` | ROSSO | - |
| M4 pubblicato che somma (`p.n + EXCLUDED.n`) | ROSSO | ROSSO, 4 KO (2.161 celle pubblicato != grezzo) |
| M5 `DELETE FROM omega_minute_transitions` nel giro | ROSSO | ROSSO, 7 KO (i bot perdono i numeri dell'11/09) |
| M6 dry-run che non annulla | ROSSO | ROSSO, 3 KO |
| M7 guardia `pg_extension` tolta | ROSSO | ROSSO (errore su `cron.job` senza pg_cron) |
| M8 chiave `pg_cron` di status rinominata | ROSSO | - |
| M9 filtro di coerenza gol/finale tolto | ROSSO | ROSSO, 13 KO (7.760 righe contro 7.637 dell'originale) |
| M10 lega che supera la soglia non copiata | verde al primo giro -> test aggiunto -> **ROSSO** | ROSSO, 4 KO (232 celle ammesse mancanti) |
| T1 script senza paginazione | ROSSO | - |
| T2 confronto per lega cieco | ROSSO | - |
| T3 soglia `>` invece di `>=` (lega a 1000 esatte) | ROSSO | - |
| T4 celle n <= 0 non contate | ROSSO | - |

Dopo le due aggiunte: **23 test, tutti verdi**; banco finale sui file ripristinati: **86/86**.

## 6. Procedura per il coordinatore (dopo che l'utente applica la migrazione)

0. Prima: `SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'matches';`
   Se non c'e' un indice su `(fixture_date)`, lanciare DA SOLO (fuori transazione):
   `create index concurrently if not exists idx_matches_fixture_date_settled on public.matches (fixture_date) where status_short in ('FT','AET','PEN');`
1. L'utente applica `migrations/omega_transitions_catchup_2026-09-25.sql` nell'SQL editor.
   L'ultima riga risponde `schedulato: ... 04:00 UTC` (o `pg_cron non attivo ...`).
   Se non si vuole partire stanotte: `SELECT public.omega_transitions_schedule(false);`.
2. `SELECT public.omega_transitions_status();` -> `state.id_cursor` 0, `published_at` null,
   `cron_jobs` con un solo job, indici true.
3. Prova a vuoto: `SELECT public.omega_transitions_nightly(60, true);` -> `status dry_run`,
   `scanned`, `minute_counted`, `id_cursor_to`, `elapsed_s`: calcolare le notti (§4).
4. `python -m Betfair.omega.tools.verifica_transizioni_2026_09_25` -> registro 0, grezzo 0,
   F con la riga `dry_run=True`. Tabelle dei bot con `built_at` 11/09.
5. Ricostruzione: lasciare il cron (una notte = 600 s) oppure accelerare con
   `SELECT public.omega_transitions_nightly(90);` ripetuto finche' `bootstrap_done = true`.
   Controllo dopo ogni notte: script, sezioni A (grezzo) e F.
6. Ricostruzione finita: `... --confronto pre --salva-impronta pre.json` -> atteso
   `cells_lower=0`, `cells_missing=0` (se > 0 sono partite corrette nei dati dopo l'11/09:
   portarle all'utente prima di pubblicare), `matches_global_new >= 939506`.
7. Rilancio immediato `SELECT public.omega_transitions_nightly(90);` e
   `... --confronta-impronta pre.json` -> atteso `delta_totale=0` (o le sole partite arrivate nel mezzo).
8. Pubblicazione (decisione dell'utente: cambia i numeri letti dai bot):
   `SELECT public.omega_transitions_publish('PUBBLICA');` poi, uno per volta,
   `VACUUM (ANALYZE) public.omega_minute_transitions;` `VACUUM (ANALYZE) public.omega_ht_ft_transitions;`
9. `... --confronto post` + script completo: A pubblicato `leghe diverse 0`, D coerente,
   E `omega_minute_league_counts leghe diverse 0`, C `built_at` di oggi.
10. La notte dopo: F con `status=ok`, `published=True`; `--confronta-impronta` sulla sera prima.
11. Ritorno se serve: `SELECT public.omega_transitions_unpublish('RITORNA');`.
12. Mike vede i numeri nuovi solo al riavvio del suo processo (cache senza scadenza,
    `Betfair/mike/dossier.py:113-141`); Omega entro 6 h (`omega_service.py:104`).
13. Dopo qualche settimana stabile: le tabelle `*_pre_ledger` si possono togliere (DROP a mano).

## 7. NON VERIFICATO (senza DB vero)

- Esecuzione su **Supabase / PostgreSQL 17**: collaudata solo su PGlite = PostgreSQL 18.3 in
  wasm (nessuna funzione solo-18 usata, ma non provato sul 17).
- **pg_cron vero**: provato con uno schema `cron` finto. Non provati: che il comando a due
  istruzioni (`SET statement_timeout = '20min'; SELECT ...`) venga eseguito cosi' da pg_cron
  su Supabase (modalita' libpq o background worker), `cron.job_run_details` reale, fuso di
  pg_cron (atteso GMT), timeout di ruolo di `postgres` su Supabase.
- **Tempi e IO reali**: stime da §4 (rapporto misurato in wasm su PC condiviso, 1,05-2,70x);
  numero di righe del grezzo minuto per le 876 leghe potate; carico del giro di controllo
  (larghezza reale delle righe di `matches`).
- **Piani reali**: uso dell'indice parziale su `fixture_date` nella fase calda (predicato
  `status_short IN ('FT','AET','PEN') AND status_short = 'FT'` scritto apposta), PK a range nei
  passi, nested loop sul registro.
- Esistenza di `idx_matches_fixture_date_settled` sul DB (documentato in
  `sql/leagues_needing_retrain_rpc.sql:84`, non verificato).
- Tipi reali di `matches` (`fixture_date` timestamptz, `fixture_id` unico, `id` bigint): dedotti
  da upsert `on_conflict="fixture_id"` e dalle RPC esistenti.
- Visibilita' delle tabelle nuove in PostgREST senza `NOTIFY pgrst, 'reload schema'` (su
  Supabase di norma automatico).
- Esistenza di correzioni di dati dopo l'11/09 (`cells_lower` > 0 possibile sul vero).
- Lo script di verifica e' provato solo contro il finto (chiavi estratte dall'SQL e confermate
  dal banco PGlite), mai contro PostgREST vero.

## 8. File e comandi

File NUOVI (nessun file esistente modificato: `git diff HEAD` vuoto, base `f015204`):
- `migrations/omega_transitions_catchup_2026-09-25.sql`
- `Betfair/omega/tools/verifica_transizioni_2026_09_25.py`
- `Betfair/omega/TRANSIZIONI_NOTTURNE_2026-09-25.md`
- `test_omega_transizioni_notturne_2026_09_25.py`
- `AUDIT_2026-09-25/O2_banco_pglite_2026-09-25.mjs` (banco su PostgreSQL in wasm, oracolo = costruttore originale)
- `AUDIT_2026-09-25/O2_misura_costo_pglite_2026-09-25.mjs` (costo relativo nuovo/vecchio)
- questo referto

Comandi eseguiti (PGlite installato solo nello scratchpad con `npm install @electric-sql/pglite`):
- `node AUDIT_2026-09-25/O2_banco_pglite_2026-09-25.mjs <pglite>/dist/index.js` -> 86/86 (prima esecuzione 85/86: il
  test della lega che supera la soglia usava una lega gia' sopra soglia nel generatore; corretto il banco con una lega
  dedicata, non la migrazione)
- `node AUDIT_2026-09-25/O2_misura_costo_pglite_2026-09-25.mjs <pglite> 20000` -> rapporti 2,70 e 1,48 (un primo lancio
  da 40.000 partite fermato da me: generatore dei dati quadratico, corretto)
- pytest del solo file nuovo con `SUPABASE_URL=http://127.0.0.1:9` -> 23 passed
- falsificazione: 16 mutazioni, tutte rosse (tabella §5.3), ripristino verificato con sha256
