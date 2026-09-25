# Backfill automatico delle stagioni: DB sempre aggiornato, senza buchi, dentro la quota (25/09/2026)

Delegato del coordinatore, worktree `agent-a51c4dd9bd46941d6`, base `703a33a`. Niente commit, niente push, niente
`gh workflow run`. **Nessuna scrittura sul DB vero. Nessuna lettura del DB vero.** Unica chiamata esterna vera:
`GET /status` di API-Football **2 volte** (per confermare struttura e gratuita'): entrambe
`{"current": 1076, "limit_day": 7500}`, piano `Pro`, `errors: []`, header `x-ratelimit-requests-remaining: 6424`,
`x-ratelimit-requests-limit: 7500` -> il contatore NON e' salito tra le due: `/status` e' gratuita (conferma anche
dalla documentazione API-Football: "this call does not count against the daily quota").

Ordine dell'utente coperto: (1) DB sempre aggiornato, (2) mai oltre la quota, (3) tutte le leghe, stagione dopo
stagione, anche nuove, (4) consumi calcolati DOPO OGNI lega-stagione, (5) l'orchestratore popola la stagione senza
"casini"; aggiunta: **DB SENZA BUCHI**, referto buchi, fail-loud sui buchi che invecchiano.

---

## 1. Cosa fa ora -> cosa fa dopo (i 5 pezzi)

### 1.1 Mapper (`leagues_mapper.py`, `.github/workflows/leagues_mapper.yml`)

| Prima (703a33a) | Dopo |
|---|---|
| `:15-44` lettura coppie con `.range(0, 9999)`: tetto 10.000 (oggi ~8.700) | `:29-67` `get_existing_coverage_rows`: pagine da 1000 ordinate (`order league_id, season_year` + `range`) fino a pagina parziale; errore -> `RuntimeError` (come prima, mai insieme vuoto) |
| `:131-215` inserisce SOLO coppie nuove, **mai aggiorna** ("Nessuna sovrascrittura") | `:194-320` inserisce le nuove (logica identica: chunk 500, duplicati residui tollerati, nessuna delete) **e AGGIORNA** le righe esistenti "vive" i cui campi differiscono: `season_start/end`, `current`, i 12 flag. Solo i campi cambiati + `updated_at`; **`inserted_at` mai nel payload**. Un `UPDATE ... eq(league_id).eq(season_year)` per riga (non dipende da un vincolo unico su quella coppia) |
| — | `:90-108` finestra "viva": `current=True` secondo API **o** DB (cosi' una stagione finita passa a `current=False`), oppure `season_end >= oggi-30gg`. Motivo: API-Football accende events/lineups/statistics/odds a stagione iniziata e li ritocca nelle settimane finali; oltre un mese i flag non cambiano piu' e riscriverli ogni giorno e' IO inutile |
| riepilogo: nuove / duplicate | riepilogo: inserite / **aggiornate con elenco** `AGGIORNATA lega 135 stagione 2026: fixtures_events False -> True, ...` / invariate |
| cron solo il 1° del mese | `workflow_run` in coda al Daily (ogni giorno, anche se il Daily e' fallito; non se annullato) + cron mensile come rete + dispatch; `concurrency: leagues-mapper, cancel-in-progress: false`; `timeout-minutes: 30`. **Nome del workflow invariato** (`Monthly Leagues Mapping`): lo usano `seasons_catchup.yml` e `misure_action.py` |

### 1.2 Stato derivato dai dati + backfill ripartibile (`season_gaps.py`, `per_fixture_backfill.py`, migrazione)

| Prima | Dopo |
|---|---|
| `per_fixture_backfill.py:149-198` `get_fixtures_from_matches`: TUTTE le fixture della stagione, nessun controllo di cio' che c'e' | `per_fixture_backfill.py:1040-1136` chiama l'API SOLO per le partite FT mancanti e SOLO per gli endpoint con flag True (`Lacune.da_chiamare_per_fixture`, `season_gaps.py:136`) |
| `:206-240` + `:941` delete di TUTTE le tabelle in testa, poi fetch: un errore API **cancellava dati buoni** | `:926-936` `_sostituisci_righe`: delete+insert di UNA tabella SOLO dopo una risposta valida e non vuota |
| `:212-217` `match_odds` non cancellata -> **doppioni** a ogni rilancio | `match_odds` compresa in `_sostituisci_righe` (test `test_match_odds_cancellate_prima_del_reinserimento_niente_doppioni`) |
| `:294-334` `_api_get_*` ritornano `[]` sia su errore sia su vuoto; `errors` di API-Football (quota finita!) = "vuoto" | `:294-307` `_risposta_o_none`: `{}` (errore del client) o `errors` non vuoto -> `None` = **errore**; solo `response: []` valido = **vuoto** |
| vuoti mai ricordati: ogni notte si richiamerebbe l'API per partite che l'API non ha, oppure (Daily) la partita spariva | vuoti ed errori registrati in `fixture_detail_checks` (RPC `record_fixture_detail_checks`) da `process_single_fixture` (`:939-1030`) |
| `league_orchestrator.py:387` `completed` sempre, anche a stagione in corso e con 0 righe | `season_gaps.py:270-275` `calcola_stato`: `completed` SOLO se `season_end < oggi` (e `current=False`), partite FT > 0 e **zero buchi aperti**; altrimenti `in_progress`. `stats_json` v2 (`:278-300`): conteggi per tabella (`da_chiamare`, `errore`, `in_attesa`, `vuoti_definitivi`), `chiamate_stimate`, `buchi_aperti`, **`buco_aperto_dal`** (persistito finche' il buco resta aperto), `ultimo_esito`; `fixtures.matches_count` resta (lo legge `training_planner.py:193-196` nel fallback) |
| `league_orchestrator.py:429` `completed` = barriera per sempre | lo stato NON e' piu' letto come barriera: ogni lancio ricalcola dai dati; un `completed` con buchi viene riaperto (`completed -> in_progress RIAP`) |

Definizione di "mancante" (RPC `season_detail_gaps`, `migrations/season_gaps_2026-09-25.sql`): partita
`status_short in (FT, AET, PEN)` senza NESSUNA riga nella tabella (una 0-0 senza gol ha comunque sostituzioni/cartellini:
"almeno una riga" e' il criterio giusto; se l'API la da' vuota, vedi sotto). Stati:

| stato | quando | si chiama? | e' un buco? |
|---|---|---|---|
| `da_chiamare` | mai interrogata | si' | si' |
| `errore` | ultimo tentativo in errore (HTTP/rete/`errors`) | si' | si' |
| `in_attesa` | 1 risposta vuota da < 2 giorni | **no** (niente richiamate ogni notte) | si' (aperto, visibile) |
| `da_richiamare` | 1 risposta vuota, attesa scaduta | si' (2o e ultimo tentativo) | si' |
| `vuoto_definitivo` | 2 risposte vuote, oppure vuota chiesta >= 7 gg dopo la partita | no | **no**: dichiarato ("l'API non ha il dato") |

Scelta della forma (IO): RPC SQL, non `select=fixture_id` per tabella. Motivo misurabile sullo schema: `match_odds`
~82,4M righe (DOCUMENTAZIONE_DATABASE.md:25), centinaia/migliaia di righe per partita -> una stagione = centinaia di
migliaia di righe restituite a pagine da 1000; la RPC fa una sonda `EXISTS` per (partita, tabella) su indice
`fixture_id` e restituisce <= ~22 righe (una per tabella/stato con l'array degli id): nessun limite di 1000 righe. Non
ho potuto MISURARE l'IO sul DB vero (nessuna lettura consentita): vedi §7.

### 1.3 Gestore della quota (`api_quota.py`, nuovo; `api_client.py`)

Cercato prima: nel repo non esiste nulla (`limit_day`, `/status`, `x-ratelimit`: 0 risultati in `*.py`).

- `api_quota.py:86-103` `leggi_status_api`: `GET /status` con `requests` diretto (non entra in `api_call_log`),
  `errors` non vuoto -> errore anche se `requests` c'e'.
- `:106-134` `conta_log_oggi`: controprova da `api_call_log` con 2 query leggere (max(id) via PK; `count=exact` su
  `id > max-20000 AND created_at >= 00:00 UTC`, range di PK: la tabella ha ~3M righe e nessun indice noto su
  `created_at`). Scrive prima il buffer del logger.
- `:161-196` `GestoreQuota.aggiorna`: fonte 1 `/status`; fonte 2 header `x-ratelimit-*` del client (se < 15 min);
  fonte 3 `api_call_log` **con AVVISO**; nessuna -> `QuotaNonLeggibile` (non si parte). Avvisa se la controprova supera
  il contatore di oltre 50.
- `:202-218` `margine()` = `limit_day - current - riserva` meno le richieste HTTP fatte dal client dall'ultimo
  ricalcolo e le chiamate fisse fatte da altri client (`aggiungi_chiamate_esterne`).
- `api_client.py:19-30,52-55,118-133`: contatore `richieste_http` (ogni tentativo HTTP, retry compresi) e
  `ultimo_ratelimit` dagli header `x-ratelimit-requests-limit/remaining`; log a campione (1a e ogni 50, sempre sotto 500
  rimaste). **Firma di `call` invariata.**
- Controllo PRIMA di ogni lega-stagione (`season_backfill.py:92-107` `decidi`), dentro la lega-stagione prima di
  **ogni partita** (`per_fixture_backfill.py:1092`: mai a meta' partita), ricalcolo DOPO ogni lega-stagione
  (`seasons_catchup.py` dopo `esegui`; `league_orchestrator.py` dopo `esegui`) con la riga di log:
  `lega X stagione Y: chiamate fatte N, contatore API ora C/7500, margine M, prossima costa ~K -> continuo|mi fermo`.

### 1.4 Recupero giornaliero (`seasons_catchup.py`, `.github/workflows/seasons_catchup.yml`, nuovi)

- Pre-controlli fail-loud (exit 2): migrazione applicata (`season_gaps.verifica_migrazione`), quota leggibile.
- Candidati (`seasons_catchup.py:147-172`): TUTTE le stagioni vive con almeno un flag per-partita True e gia' iniziate;
  le passate a rotazione (`CATCHUP_MAX_VERIFICHE_PASSATE`, default 150/notte: prima quelle v2 gia' note con buchi, poi
  le mai verificate dalla piu' recente); le passate con 0 partite in `matches` sono contate e lasciate
  all'orchestratore a mano (vedi §2 e §7).
- Verifica a blocchi di 20 lega-stagioni (RPC `season_gaps_summary`) e scrittura dello stato derivato in blocco.
- Coda (`:175-181`): **P1** stagioni vive delle leghe dei bot = le 21 leghe di
  `Betfair/omega/data/hazard_atlas_v3.json` chiave `by_league` (sola lettura; override `CATCHUP_LEGHE_PRIORITARIE`);
  **P2** altre stagioni vive, piu' mancanze prima; **P3** passate, piu' economiche prima (piu' buchi chiusi per
  chiamata).
- Sulle stagioni vive NON si rifanno `/fixtures` e aggregati (`season_backfill.py:85`): li fa gia' il Daily per le
  leghe che hanno giocato; con centinaia di leghe vive sarebbero 1-6 chiamate fisse sprecate per lega ogni notte. Sulle
  passate si': `/fixtures` (allinea `matches`) + aggregati con flag True.
- Concorrenza: prima di ogni lega-stagione (forzato) e ogni 25 partite (cache 2 min) chiede a GitHub
  (`GET /repos/{repo}/actions/workflows/{file}/runs?status=in_progress|queued`) se Daily / Today / Results sono in
  corso o in coda; se si' si ferma a fine partita, exit 0 dichiarato. Tempo massimo `CATCHUP_MAX_MINUTI` (150).
- Exit: 0 = fatto o fermato per quota/tempo/action concorrente (dichiarato); **1** = lega-stagione in errore (la run
  prosegue con le altre e esce 1 alla fine) **oppure buco aperto > `BACKFILL_BUCHI_MAX_GIORNI` (3) con budget
  disponibile**, con la causa; 2 = pre-controlli.
- Workflow: `workflow_run` su "Monthly Leagues Mapping" `completed` (non se annullato) + cron `47 13 * * *` (reale
  ~18:45 UTC col ritardo mediano: seconda finestra dopo Today/Results e rete di sicurezza) + dispatch;
  `concurrency: seasons-catchup, cancel-in-progress: false`; `permissions: actions: read` (per GITHUB_TOKEN);
  `timeout-minutes: 180` (150 di lavoro + ultima lega-stagione ferma a fine partita + referto).

**REFERTO BUCHI** (sempre, a fine run, `seasons_catchup.py:318-379`): per ogni lega-stagione verificata con buchi
aperti: FT, da chiamare per tabella, in attesa, costo stimato, **aperto da (data e giorni)**; poi chiamate fatte,
lega-stagioni lavorate/rimaste, quota, motivo dello stop, vuoti definitivi dichiarati, passate non ancora verificate e
passate mai caricate; `RINVIATO PER QUOTA/TEMPO` con stima dei giorni; `ERRORE:`; `BUCO VECCHIO:` con la causa
(`errore API ripetuto su N partite-tabella` / `API vuota su N partite-tabella (in attesa del 2o tentativo)` /
`10 partite di fila con tutti gli endpoint in errore` / `partite da chiamare NON tentate nonostante il budget` + i flag
False). Ultima riga: `DB SENZA BUCHI` oppure `BUCHI APERTI: N lega-stagioni, ~K chiamate, il piu' vecchio da G giorni`.

Esempio reale (finti, output del codice di produzione):
```
[CATCHUP] quota all'avvio: contatore API 4475/7500 (fonte /status), riserva action 3000, margine 25
[CATCHUP] candidati: 3 stagioni vive, 1 passate da verificare (non verificate stanotte: 0, passate mai caricate: 0)
[CATCHUP] coda: 4 lega-stagioni con partite da chiamare (P1 1, P2 2, P3 1), ~35 chiamate per-partita
[CATCHUP] P1 lega 135 stagione 2026: costo ~10, margine 25 -> procedo
[CATCHUP] lega 135 stagione 2026: chiamate fatte 10, contatore API ora 4485/7500, margine 15, prossima costa ~15 -> continuo
[CATCHUP] P2 lega 999 stagione 2026: costo ~15, margine 15 -> procedo
[CATCHUP] lega 999 stagione 2026: chiamate fatte 15, contatore API ora 4500/7500, margine 0, prossima costa ~5 -> mi fermo
[CATCHUP] P2 lega 555 stagione 2026: costo ~5, margine 0 -> mi_fermo
==============================================================================================================
REFERTO BUCHI (partite FT senza dati, solo tabelle con flag di coverage True)
  Lega  Stag P     FT  da chiamare ev/fo/sg/ss/qu   att.   costo~  aperto da
   555  2026 2      1     1    1    1    1    1      0        5  2026-09-25 (0 gg)
   135  2024 3      1     1    1    1    1    1      0        5  2026-09-25 (0 gg)
--------------------------------------------------------------------------------------------------------------
Chiamate fatte stanotte: 25. Lega-stagioni lavorate: 2, rimaste in coda: 2. Quota: contatore API 4500/7500 (fonte /status), riserva action 3000, margine 0
Fermato per: quota (NON e' un errore: si riprende al prossimo giro da cio' che manca).
Vuoti definitivi dell'API (non buchi, l'API non ha il dato): 0 partite-tabella.
Stagioni passate non ancora verificate (a rotazione, 4 verificate stanotte): 0; passate con 0 partite in DB (solo orchestratore a mano): 0.
BUCHI APERTI: 2 lega-stagioni, ~10 chiamate, il piu' vecchio da 0 giorni
```

### 1.5 Orchestratore a mano (`league_orchestrator.py`, riscritto sugli stessi mattoni)

| Prima | Dopo |
|---|---|
| `:491-509` solo `input()` | `:219-240` argparse `--league N [--season Y] [--dry-run]`; senza `--league` il prompt interattivo di prima |
| `:402-483` salta i `completed`, rifa' tutto, `completed` sempre, poi `run_past_seasons_backfill` (MV `missing_fixture_coverage_mat` di 135 righe, rifaceva le partite intere) | `:73-189` per ogni stagione: `pianifica` (lacune dai dati) -> decisione di quota -> `esegui` (fixtures + solo mancanti + aggregati) -> ricalcolo quota -> stato derivato. Stagioni senza lavoro: stato scritto, **zero chiamate**. `run_past_seasons_backfill` non e' piu' chiamato (superato dalle lacune; il file resta) |
| — | **`--dry-run`**: nessuna chiamata API (salvo `/status`, gratuita), nessuna scrittura; tabella per stagione (vedi §6); avviso se una stagione viva ha partite FT senza dati e flag False ("lancia `python leagues_mapper.py`") |
| — | console Windows cp1252: gli script vecchi stampano emoji -> `UnicodeEncodeError` DENTRO il lavoro (visto in prova con stdout reindirizzato); `main` riconfigura stdout/stderr con `errors="replace"` (anche `seasons_catchup.main`) |

### 1.6 Daily (`daily_yesterday_backfill.py:255-277`)

**Cosa succedeva (verificato nel codice di `703a33a`)**: una fixture FT di ieri con API vuota su eventi/formazioni ->
`per_fixture_backfill.py:958-969` (map -> 0 righe -> nessun insert, nulla registrato) -> il Daily successivo guarda
solo le partite del giorno prima -> nessuno la rivedeva: **sparita in silenzio**. Peggio: `_api_get_*` (`:294-334`)
trattava gli errori (anche "quota finita") come vuoti, e `delete_existing_for_fixture` (`:941`) cancellava in testa
tutte le tabelle della fixture, quindi un errore API su una fixture gia' parzialmente piena CANCELLAVA dati.

**Dopo**: per ogni gruppo (lega, stagione) una RPC `season_detail_gaps` con `p_fixture_ids` = fixture di ieri ->
solo gli endpoint mancanti (flag True); vuoti/errori registrati -> la fixture resta un buco `in_attesa`, visibile nel
referto, e dopo 2 giorni il catchup la ritenta (test `test_daily_fixture_vuota_non_si_perde_entra_nella_coda_del_catchup`).
Senza migrazione: stesso comportamento di prima + AVVISO esplicito (`test_daily_senza_migrazione_fa_il_lavoro_di_prima_con_avviso`).

---

## 2. Flusso automatico giorno per giorno

Orari reali con il ritardo mediano del cron di GitHub (~5 h, `ACTIONS_DIAGNOSI_E_FIX.md` §1 e §5.3):

1. **Daily** (cron 01:12, reale ~06:00 UTC, 8-30 min): partite di ieri in `matches`, dettagli SOLO mancanti, aggregati.
2. **Mapper** (`workflow_run` a fine Daily, ~1-2 min, 1 chiamata `/leagues`): inserisce leghe/stagioni nuove,
   aggiorna flag/date/current delle stagioni vive.
3. **Catchup** (`workflow_run` a fine mapper, ~06:35 UTC): verifica, coda P1/P2/P3, lavoro dentro la quota, referto.
   Se alle ~07:35 parte Today (o Results ~08:27) si ferma a fine partita e lo dichiara.
4. **Catchup, seconda finestra** (cron 13:47, reale ~18:45 UTC): riprende da cio' che manca con il margine rimasto.
5. Hazard Atlas / Retrain / ML-Calibration: **non toccati**; restano agganciati al Daily come prima.

**Scenario 2027 - stagione nuova di una lega esistente (es. Serie A 2027)**:
- luglio 2027: `/leagues` mostra `135/2027` (`current=True`, flag per-partita spesso False) -> il mapper (giornaliero)
  la INSERISCE il giorno stesso (prima: solo il 1° del mese) e il 2026 passa a `current=False` quando l'API lo dice;
- agosto: API-Football accende events/lineups/statistics/odds -> il mapper del giorno dopo AGGIORNA i flag
  (`AGGIORNATA lega 135 stagione 2027: fixtures_events False -> True, ...`);
- ogni giorno il Daily scrive le partite di ieri e i dettagli mancanti; se nei giorni in cui i flag erano ancora False
  le partite sono state scritte senza dettagli, il catchup le vede (`da_chiamare`), le mette in P1 (135 e' nell'atlante)
  e le recupera dentro la quota;
- la stagione resta `in_progress` fino a `season_end < oggi` e zero buchi; a giugno 2028 diventa `completed` da sola.

**Scenario lega nuova (API-Football aggiunge la lega 1300 a meta' 2027)**:
- il Daily la vede gia' da subito (scrive le partite di TUTTE le leghe del giorno), ma senza riga di coverage i
  dettagli sono saltati (`Nessun coverage per league_id=1300`), come oggi;
- il mapper del giorno stesso inserisce `1300/2027` (e le sue stagioni passate); dalla notte il catchup la trova tra
  le vive, con le partite FT gia' giocate senza dettagli -> P2 -> recuperate;
- le stagioni PASSATE della lega nuova: il catchup le verifica a rotazione (P3) solo se in `matches` ci sono partite;
  se non ci sono partite (mai caricate) serve l'orchestratore a mano (`--league 1300`), vedi §7 (decisione).

---

## 3. Modello di quota

```
margine = limit_day - current - riserva            (letto da /status; ricalcolato DOPO ogni lega-stagione)
riserva = API_FOOTBALL_RISERVA_GIORNALIERA          (default 3000 = p90 misurato ~2.720/giorno delle action + ~10%)
costo(lega-stagione) = sum_partite(endpoint mancanti con flag True) + fisse
fisse = 0 sulle stagioni vive nel catchup; 1 (/fixtures) + n aggregati con flag True altrove
parte se margine >= costo; se costo > (limit_day - riserva) parte "a spezzoni" (si ferma a fine partita quando il
margine finisce, domani riprende); altrimenti si ferma e resta in coda. Dentro: prima di ogni partita margine >= n endpoint.
```

Esempio con i numeri veri di oggi (`/status` delle 2 prove: current 1076, limit_day 7500):
- margine = 7500 - 1076 - 3000 = **3424**;
- Serie A 2026 oggi: 50 partite FT; se i 5 flag fossero True e tutte vuote: 50 x 5 = 250 (+6 fisse con
  l'orchestratore) = **256** -> procede, margine dopo ~3168;
- una stagione intera da 380 partite: CORRENTE 380 x 5 = 1900 + 6 = **1906**; PASSATA 380 x 4 + 6 = **1526** (le
  quote sono fuori finestra API e non si chiamano, R4) -> ci stanno ~1,8 stagioni intere al giorno
  quando le action hanno consumato ~1.000; la capacita' giornaliera piena per il recupero e'
  7500 - 3000 = 4500 chiamate (il Daily delle ~06:00 e' gia' nel `current` quando parte il catchup, Today+Results
  sono coperti dalla riserva: doppia prudenza).
- Reset del contatore: API-Football azzera il giorno alle 00:00 UTC (assunto, coerente con il conteggio per giorno UTC di
  `api_call_log`); non verificato con un cambio di giorno.

---

## 4. Migrazioni e variabili d'ambiente

Ordine (le applica l'utente, SQL Editor):
1. **`migrations/season_gaps_2026-09-25.sql`** (obbligatoria, additiva): tabella `fixture_detail_checks` (+ indice
   lega/stagione, RLS attiva senza policy, revoke anon/authenticated), funzioni `record_fixture_detail_checks(jsonb)`,
   `season_detail_gaps(int, int, int[])`, `season_gaps_summary(int[], int[])` (execute solo `service_role`),
   `notify pgrst, 'reload schema'`, poi un blocco `DO` che **AVVISA** (warning, non modifica) se una tabella di dettaglio
   non ha un indice non parziale che inizia con `fixture_id` (o `matches` su `league_id`).
2. **`migrations/detail_fixture_idx_2026-09-25_SOLO_SE_MANCANO.sql`** SOLO se il punto 1 ha stampato
   `ATTENZIONE: public.<tabella> senza indice utile`: `create index concurrently if not exists ... (fixture_id)`, una riga
   alla volta. Senza quell'indice `match_odds` (~82M righe) verrebbe letta per intero.

Senza migrazione: catchup e orchestratore si FERMANO con `applica migrations/season_gaps_2026-09-25.sql` (exit 2); il
Daily continua come prima e stampa l'avviso.

Variabili d'ambiente nuove (tutte con default; nel workflow del catchup sono esplicite):

| Variabile | Default | Uso |
|---|---|---|
| `API_FOOTBALL_RISERVA_GIORNALIERA` | 3000 | chiamate lasciate alle action giornaliere |
| `API_FOOTBALL_LIMITE_GIORNALIERO` | 7500 | usato SOLO nel fallback `api_call_log` (quando `/status` non risponde) |
| `CATCHUP_MAX_MINUTI` | 150 | nessuna lega-stagione nuova dopo N minuti; stop a fine partita |
| `CATCHUP_MAX_VERIFICHE_PASSATE` | 150 | stagioni passate verificate per notte (rotazione) |
| `BACKFILL_BUCHI_MAX_GIORNI` | 3 | buco aperto oltre N giorni con budget disponibile -> exit 1 |
| `CATCHUP_LEGHE_PRIORITARIE` | (atlante v3, 21 leghe) | override della P1, es. `135,39,140` |
| `CATCHUP_WORKFLOW_ESCLUSIVI` | Daily, Today, Results | file dei workflow con cui non girare insieme |
| `GITHUB_TOKEN` / `GITHUB_REPOSITORY` | dati da GitHub Actions | controllo concorrenza (spento con avviso in locale) |

---

## 5. Modifiche, test, falsificazione

File modificati: `api_client.py`, `per_fixture_backfill.py`, `leagues_mapper.py`, `league_orchestrator.py` (riscritto),
`daily_yesterday_backfill.py`, `.github/workflows/leagues_mapper.yml`, `test_actions_fail_rumoroso_2026_09_25.py`.
File nuovi: `api_quota.py`, `season_gaps.py`, `season_backfill.py`, `seasons_catchup.py`,
`.github/workflows/seasons_catchup.yml`, `migrations/season_gaps_2026-09-25.sql`,
`migrations/detail_fixture_idx_2026-09-25_SOLO_SE_MANCANO.sql`, `test_backfill_automatico_2026_09_25.py`,
`AUDIT_2026-09-25/mutazioni_backfill_automatico.py`, questo referto, `AUDIT_2026-09-25/backfill_automatico.patch`.

`test_actions_fail_rumoroso_2026_09_25.py` (11 test, tutti verdi): il finto `_Query` ora ha `order`, `range` VERO
(slice), `eq`, `update` (il mapper legge a pagine e aggiorna); `test_mapper_db_gia_allineato_esce_pulito` usa una riga
con le colonne vere (quelle che scrive il mapper) e verifica anche 0 update. Motivo: prima il finto aveva solo
`(league_id, season_year)` perche' il mapper non confrontava nulla; con una riga senza flag ogni riga viva risulterebbe
"cambiata".

Suite lanciate (con `SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x API_FOOTBALL_KEY=x`,
`timeout 600`): `python -m pytest test_actions_fail_rumoroso_2026_09_25.py test_backfill_automatico_2026_09_25.py -q
-p no:cacheprovider` -> **48 passed** (11 + 37; erano 41 prima dei reperti R1-R5, §8). Nessun altro test del repo importa i file toccati (grep). `pyflakes`
pulito sui file nuovi; YAML dei due workflow caricato con `yaml.safe_load`; migrazioni parse-ate con il parser vero di
PostgreSQL (`pglast` 8.4 = libpg_query, installato solo nello scratchpad): 18 statement + 3 corpi di funzione SQL + il
blocco `DO` come plpgsql -> OK.

Test richiesti -> test (tutti in `test_backfill_automatico_2026_09_25.py`) -> mutazione che li fa diventare ROSSI
(`python AUDIT_2026-09-25/mutazioni_backfill_automatico.py`, ogni file ripristinato e verificato con sha256):

| Requisito | Test | Mutazione (tutte ROSSE) |
|---|---|---|
| mapper aggiorna flag, non tocca `inserted_at` | `test_mapper_aggiorna_i_flag_...` | M1 `if diff:`->`if False:`; M2 `inserted_at` nel payload |
| mapper: finestra | `test_mapper_non_riscrive_le_stagioni_chiuse_...`, `test_mapper_chiude_current_...` | M3 finestra infinita; M4 `current` del DB ignorato |
| mapper pagina > 10.000 | `test_mapper_pagina_oltre_10000_coppie` (10.500 righe, 11 letture) | M5 una sola pagina |
| partita con eventi non richiesta, FT senza righe richiesta, flag False mai chiamato | `test_lacune_chiama_solo_cio_che_manca_...` | M6 flag False chiamati; M7 tutti gli endpoint |
| vuota registrata, non richiamata, ritentata, poi definitiva | `test_risposta_vuota_registrata_...` | M8 vuoto non registrato; M9 `in_attesa` richiamata |
| errore != vuoto, niente cancellazioni | `test_errore_api_non_e_un_vuoto_...` | M10 `errors` come vuoto; M11 errore che cancella |
| niente doppioni quote | `test_match_odds_cancellate_...` | M12 delete tolta |
| migrazione mancante detta chiaramente | `test_senza_migrazione_il_recupero_si_ferma_...` | M13 riconoscimento spento |
| `completed` solo a stagione finita e senza buchi | `test_stato_completed_solo_...` | M14 senza controllo buchi; M15 senza controllo partite |
| `completed` vecchio riaperto; rilancio = 0 chiamate | `test_orchestratore_riapre_completed_vecchio_...` | M16 fisse sempre; M17 stato sempre completed |
| stagione finita e piena -> completed, 0 chiamate | `test_orchestratore_stagione_finita_e_piena_...` | M18 stato non scritto |
| dry-run: 0 chiamate, 0 scritture | `test_dry_run_non_chiama_l_api_e_non_scrive` | M19 dry-run che esegue |
| riserva da env, default 3000 | `test_quota_riserva_da_env_default_3000` | M20 env ignorata |
| `/status` giu' -> `api_call_log` con avviso | `test_quota_status_giu_fallback_...` | M21 niente fallback |
| entrambi giu' -> non si parte | `test_quota_nessuna_fonte_non_si_parte`, `test_quota_catchup_non_parte_...` (exit 2, 0 chiamate) | M22 parte senza quota |
| `/status` con `errors` non creduto | `test_status_con_errors_...` | M23 |
| header di quota letti, `call` invariata | `test_api_client_legge_gli_header_...` | M24 |
| stop a fine partita | `test_quota_si_ferma_a_fine_partita_mai_a_meta` (2 partite x 5, poi stop) | M25 |
| ordine di priorita', ricalcolo dopo ogni lega-stagione, 0 fisse sulle vive | `test_catchup_ordine_di_priorita_e_db_senza_buchi` | M26 P3+P2+P1; M27 P2 crescente; M28 niente ricalcolo; M38 fisse sulle vive |
| fermo per budget -> exit 0 con riepilogo | `test_catchup_fermo_per_quota_esce_0_con_riepilogo` | M29 stop = errore; M36 referto cieco |
| errore di una lega-stagione -> exit != 0, le altre proseguono | `test_catchup_errore_di_una_lega_stagione_...` | M30 errore ignorato; M39 eccezione non gestita |
| buco vecchio con budget -> exit 1 con causa | `test_catchup_buco_vecchio_con_budget_...` | M31 soglia +100 gg |
| buco vecchio per quota -> exit 0 con stima | `test_catchup_buco_vecchio_per_quota_...` | M32 quota trattata come colpa |
| non girare con Today/Results/Daily | `test_catchup_si_ferma_se_un_action_concorrente_...`, `test_controllo_concorrenza_legge_le_run_di_github` | M33, M34 |
| fonte leghe prioritarie | `test_leghe_prioritarie_dall_atlante_v3` (21 leghe) | M35 |
| Daily: fixture vuota non si perde, entra nel catchup | `test_daily_fixture_vuota_non_si_perde_...` | M8, M37 Daily chiama tutto |
| Daily senza migrazione: lavoro di prima + avviso | `test_daily_senza_migrazione_...` | M40 eccezione; M41 avviso muto |

Esito della corsa completa: **49/49 mutazioni ROSSE** (M1-M41 + M42-M49 dei reperti, §8) (M28 "1 failed, 1 passed": il test sul fermo per quota resta
verde anche senza ricalcolo perche' il margine locale scala le richieste del client; lo prende il test dell'ordine),
ripristino verificato byte per byte. Nota onesta: sotto la mutazione M19 (dry-run che esegue) il codice mutato ha
creato un `APIFootballClient` vero con chiave `x`: richieste verso api-sports.io con chiave finta (non la nostra: nessuna
quota consumata), ~57 s di retry. Solo sotto mutazione.

Finti: le RPC della migrazione sono riprodotte in Python (`FintoDB._gaps`) con la STESSA regola degli stati: i test
provano il codice Python contro quel modello, **non** l'SQL (nessun Postgres locale). L'SQL e' verificato solo
sintatticamente (pglast). Risposte API con busta reale (`get/parameters/errors/results/paging/response`) e struttura
reale di ogni endpoint; `/status` con `response.requests.current/limit_day` identica a quella vista dal vivo.

### "Perche' da domani non ci saranno piu' buchi"

| Causa di buco vista | Pezzo che la elimina | Test che lo prova |
|---|---|---|
| **flag di coverage fermi a False** (135/2026 scritta il 1/7) | mapper giornaliero che AGGIORNA le stagioni vive | `test_mapper_aggiorna_i_flag_...`, `..._chiude_current_...` |
| **`completed` falso** che blocca i rilanci (135/2026 alle 08:13, 135/2025 dal 30/01) | stato derivato dai dati; mai barriera; riapertura automatica | `test_orchestratore_riapre_completed_vecchio_...`, `test_stato_completed_solo_...` |
| **non ripartibilita'** (tutto da capo, quota sprecata, doppioni quote, delete in testa) | solo mancanti, solo flag True, delete per tabella dopo risposta valida | `test_lacune_...`, `test_match_odds_...`, `test_errore_api_...`, rilancio = 0 chiamate |
| **quota** (fermarsi a meta') | controllo prima di ogni lega-stagione e di ogni partita, ricalcolo dopo; stop dichiarato, ripresa da cio' che manca | `test_quota_si_ferma_a_fine_partita_...`, `test_catchup_fermo_per_quota_...`, `..._buco_vecchio_per_quota_...` |
| **API vuota** (fixture persa in silenzio) | `fixture_detail_checks` + stati `in_attesa`/`da_richiamare`/`vuoto_definitivo` + referto | `test_risposta_vuota_...`, `test_daily_fixture_vuota_non_si_perde_...` |
| **errore API scambiato per vuoto** (anche "quota finita") | `_risposta_o_none` + stato `errore` ritentato | `test_errore_api_non_e_un_vuoto_...` |
| **action rossa / buco che invecchia senza che nessuno se ne accorga** | referto buchi ogni notte + exit 1 se un buco > 3 gg con budget, con la causa | `test_catchup_buco_vecchio_con_budget_...`, `..._errore_di_una_lega_stagione_...` |
| **leghe/stagioni nuove arrivate solo il 1° del mese** | mapper giornaliero; il catchup vede da solo le vive nuove | (flusso §2; mapper testato) |
| **tetto 10.000 coppie** | lettura paginata | `test_mapper_pagina_oltre_10000_coppie` |

Buchi che questo lavoro NON chiude da solo (dichiarati, non nascosti): vedi §7 punti 3-5.

---

## 6. Dry-run della 135

Comando (dalla radice del repo, con il `.env` vero; la migrazione deve essere applicata, altrimenti esce 2 con
`NON PARTO: RPC season_detail_gaps assente: applica migrations/season_gaps_2026-09-25.sql`):

```
python league_orchestrator.py --league 135 --dry-run
```

Costo: 1 `/status` (gratuita), 2 letture leggere di `api_call_log`, 1 lettura `api_coverage_by_season` (lega 135),
1 lettura `season_backfill_state` (lega 135), 1 RPC di sonda + 1 RPC `season_detail_gaps` per stagione. Zero scritture.

Output ATTESO (formato; generato dal codice di produzione sui finti costruiti come la 135 di oggi: 2026 con 50 FT e flag
False, 2025 finita con 10 partite senza formazioni e 40 senza quote API (fuori finestra: N.disp), 2024 piena, 2023 mai
caricata; aggiornato dopo i reperti R1-R5):

```
======================================================================================================================
ORCHESTRATORE - DRY-RUN (nessuna chiamata API, nessuna scrittura)  lega 135 (Serie A, Italy)  oggi 2026-09-25 UTC
Quota API-Football: contatore API 1076/7500 (fonte /status), riserva action 3000, margine 3424
Flag = coverage per-partita ev/fo/sg/ss/qu = eventi/formazioni/stat. giocatori/stat. squadra/quote (S=True). Mancano = partite FT da chiamare;
(n) = partite senza righe ma flag False: NON si chiamano (se l'API ha acceso il flag, lo aggiorna il mapper). Att. = vuote in attesa del 2o tentativo; Vuoti = vuote definitive dell'API; N.disp = quote di partite oltre 7 gg (storico API 7 gg: non recuperabili, non si chiamano).
----------------------------------------------------------------------------------------------------------------------
                                                                       --- mancano (partite FT) ---
Stag. Stato DB -> calcolato            Fine       Flag             FT     ev    fo    sg    ss    qu  Att. Vuoti N.disp  Chiam.~  Decisione
2023  (nessuno) -> in_progress         2024-05-26 S S S S S  mai car.      0     0     0     0     0     0     0      0     1526  procederei
2024  (nessuno) -> completed           2025-05-25 S S S S S       380      0     0     0     0     0     0     0      0        0  niente da fare (0 chiamate)
2025  completed -> in_progress RIAP    2026-05-24 S S S S S       380      0    10     0     0     0     0     0     40       16  procederei
2026  completed -> in_progress RIAP    2027-05-30 - - - - -        50   (50)  (50)  (50)  (50)  (50)     0     0      0        0  niente da fare (0 chiamate)
      ATTENZIONE 2026: stagione viva con partite FT senza dati e flag False (events, lineups, player_stats, team_stats, odds): se API-Football li ha accesi, `python leagues_mapper.py` (1 chiamata) li aggiorna e il rilancio li recupera.
----------------------------------------------------------------------------------------------------------------------
Totale chiamate stimate per chiudere tutti i buchi della lega: ~1542. Margine di oggi: 3424. Nulla e' stato chiamato ne' scritto.
```

Sulla 135 vera la riga 2026 mostrera' `(50)` finche' i flag sono False nel DB: e' la prova visiva del difetto 1.
Sequenza consigliata dopo la migrazione: dry-run -> `python leagues_mapper.py` (1 chiamata, aggiorna i flag; l'elenco
`AGGIORNATA ...` mostra cosa cambia) -> dry-run di nuovo (la 2026 passa a numeri veri, ~50 x 5 = 250 chiamate) ->
`python league_orchestrator.py --league 135 --season 2026` se l'utente vuole chiuderla subito (altrimenti lo fa il
catchup della notte, P1).

---

## 7. Non verificato e perche' / decisioni per l'utente

1. **L'SQL non e' stato eseguito** (nessun Postgres locale, nessuna scrittura consentita sul DB vero): solo parsing con il
   parser di PostgreSQL. Da verificare dopo l'applicazione: `select * from season_detail_gaps(135, 2026, null);` e i
   warning del blocco DO sugli indici.
2. **IO reale delle RPC non misurato**: dipende dall'indice su `fixture_id` delle 5 tabelle (non documentato nel repo;
   il Daily fa gia' `select fixture_id ... in (...)` su `match_odds` ogni giorno senza 57014, indizio che l'indice c'e').
   Il blocco DO lo dice all'applicazione. Primo catchup: ~1.000+ stagioni vive in blocchi da 20 (~50 RPC) + 150 passate.
3. **Stagioni passate mai caricate** (0 partite in `matches`): NON entrano nel recupero automatico (contate nel referto,
   "solo orchestratore a mano"). Caricarle tutte = ~migliaia di stagioni x ~1.900 chiamate = anni di quota. Decisione
   dell'utente: quali leghe/stagioni storiche vuole davvero (es. le 1.014 leghe di `training_eligible_leagues.json`).
4. **Un giorno intero saltato dal Daily** (es. Daily rosso): le partite mancano da `matches`, quindi il calcolo delle
   lacune non le vede. Il catchup NON rifa' `/fixtures` sulle stagioni vive (scelta di quota, §1.4); le recupera
   l'orchestratore (1 chiamata `/fixtures` per stagione) o `daily_yesterday_backfill.py --date`. Il Daily ora fallisce
   rumorosamente (703a33a), quindi il giorno perso e' visibile. Se l'utente preferisce, basta passare
   `fisse_su_stagione_viva=True` per la sola P1 (21 x ~6 = ~126 chiamate/notte).
5. **Aggregati (classifiche, marcatori, infortuni)** non hanno un "cosa manca" per partita: si aggiornano quando si
   lavora la stagione (orchestratore, P3) o dal Daily per le leghe che hanno giocato; non sono nel referto buchi.
6. **Retrain / Hazard Atlas** partono anch'essi dopo il Daily e leggono il DB mentre il catchup scrive: il catchup non li
   considera "esclusivi" (default solo Daily/Today/Results come da brief). Se ricompaiono 57014 nel retrain, aggiungere
   `retrain_models.yml` a `CATCHUP_WORKFLOW_ESCLUSIVI`.
7. **Catena `workflow_run`**: Daily -> mapper -> catchup = 2 livelli (limite GitHub 3). Gira solo dal branch di default:
   verificabile solo dopo il merge. Non ho lanciato workflow.
8. Reset del contatore API a 00:00 UTC: assunto, non osservato.
9. `per_fixture_backfill.get_fixtures_from_matches` e `delete_existing_for_fixture` restano nel file ma non sono piu'
   usati dal backfill; `missing_fixtures_backfill.py` resta (usa `process_single_fixture`, compatibile) ma
   l'orchestratore non lo chiama piu'.
10. `injuries_backfill`/`standings_backfill` ecc. creano un loro client: le loro chiamate sono contate come "fisse"
    (1 per aggregato) e riallineate dal ricalcolo `/status` dopo la lega-stagione.

---

## 8. Reperti del coordinatore R1-R5 (corretti il 25/09, stesso worktree)

Chiamate esterne aggiuntive: **1** `GET /odds?fixture=1223598` (Serie A 2024) -> `results: 0`, `errors: []`
(1 chiamata di quota consumata: contatore 1076 -> 1077, `remaining` 6424 -> 6423). Nessuna lettura/scrittura DB.

| Reperto | Correzione (file:riga) | Test nuovo | Mutazione (ROSSA) |
|---|---|---|---|
| **R1** delete delle quote cancellava anche `football_data_csv` | `per_fixture_backfill.py` `_sostituisci_righe`: su `match_odds` la delete ha anche `.eq("snapshot_type", "api_football")`; le altre 4 tabelle restano per `fixture_id` (non hanno colonna di fonte) | `test_r1_sostituzione_quote_non_tocca_le_quote_csv` (3 righe CSV + 1 API: dopo la sostituzione 3 CSV + 1 API) | M42 filtro di fonte tolto |
| **R2** mancava la prova che vuoto/errore NON cancellano | nessun cambio di codice (gia' cosi'); test per ogni tabella | `test_r2_risposta_vuota_o_in_errore_non_cancella_mai_righe_presenti[vuota|errore]` (5 tabelle piene + CSV, API tutta vuota / tutta in errore -> conteggi identici, 0 delete) | M43 delete nel ramo vuoto; M44 delete nel ramo errore |
| **R3** insert parziale = buco invisibile | batch in errore -> esito `parziale` in `fixture_detail_checks`; eccezione nel ramo -> `parziale`; esito pieno -> `ok` che cancella il controllo. SQL: una partita con righe MA controllo `parziale` torna nelle lacune come `errore` (si rifa' delete+insert al giro dopo). Scelta: niente ritentativo immediato (un insert fallito sotto carico, es. 57014, fallirebbe di nuovo; la ripresa e' gia' garantita e visibile nel referto) | `test_r3_insert_parziale_resta_un_buco_e_si_rifa_al_giro_dopo` | M45 `parziale` non registrato |
| **R4a** quale fonte riempie il buco quote | deciso: buco quote = **nessuna quota `api_football`**; le CSV sono un'altra fonte (la RPC filtra `snapshot_type = 'api_football'`) | `test_r4_quote_fuori_finestra_...` (partita recente con sole CSV -> da chiamare) | M46 |
| **R4b** quote fuori finestra | stato nuovo `non_disponibile` (solo `match_odds`, partita di oltre 7 giorni fa): non si chiama, non e' un buco, riga dedicata nel referto ("Quote fuori finestra API ... NON recuperabili") e colonna `N.disp` nel dry-run; stima di una stagione mai caricata passata senza le quote. Finestra = storico quote di API-Football 7 giorni (documentazione via ricerca: "only odds data from the last 7 days can be retrieved"; le pagine della doc ufficiale rispondono 403 ai fetch automatici) + prova reale sopra | `test_r4_quote_fuori_finestra_non_si_chiamano_e_non_sono_buchi`, `test_r4_referto_distingue_quote_non_recuperabili_dai_buchi` | M46 `non_disponibile` chiamato; M47 riga del referto azzerata |
| **R5** Retrain tra le action esclusive | `seasons_catchup.py` `WORKFLOW_ESCLUSIVI_DEFAULT` += `retrain_models.yml`; riga del referto rinominata `RINVIATO (quota/tempo/action concorrente)`; commento del workflow aggiornato | `test_r5_retrain_tra_le_action_esclusive_e_buco_vecchio_per_concorrenza_esce_0` (buco aperto da 5 gg, catchup fermato da Retrain -> exit 0, RINVIATO, nessun BUCO VECCHIO) | M48 retrain tolto; M49 concorrenza trattata come colpa |

Migrazione `season_gaps_2026-09-25.sql` aggiornata (non ancora applicata): esiti `parziale`/`ok`, vincolo sugli esiti
ricreato con `drop constraint if exists` (ripetibile), presenza quote solo `api_football`, stato `non_disponibile`,
classificazione `parziale -> errore`. Riletta con pglast: 20 statement, 3 corpi SQL e il blocco DO OK.
Modello Python delle RPC nei test (`FintoDB._gaps`, `record_fixture_detail_checks`) allineato alla stessa regola.

Suite: `pytest test_actions_fail_rumoroso_2026_09_25.py test_backfill_automatico_2026_09_25.py` -> **48 passed**.
Mutazioni: **49/49 ROSSE** (M12 aggiornata al nuovo bersaglio `q.execute()`), ripristino verificato con sha256.

Patch completa: `AUDIT_2026-09-25/backfill_automatico.patch` (diff dei file tracciati + `--no-index` dei file nuovi).

---

## 9. Aggregati per lega-stagione (seguito 25/09, base `f015204`)

Worktree riallineato: le modifiche locali (identiche a `f015204`: nessuna differenza sui file tracciati e sui file
nuovi) sono state messe da parte con `git stash push -u -m agent-a51c4dd9-backfill-prima-del-rebase-f015204`
(sha `48d753ba`), poi `git merge --ff-only origin/master` -> `f015204`. Delta di questo seguito:
`AUDIT_2026-09-25/backfill_aggregati.patch`. Nessuna lettura/scrittura del DB; nessuna chiamata API.

### 9.1 Diagnosi del fermo di `injuries` (e di tutti gli aggregati)

1. **Il Daily non chiama MAI nessun aggregato** (prima causa, indipendente dai flag).
   `daily_yesterday_backfill.py:310-325` `run_aggregates_for_seasons` legge il coverage con
   `per_fixture_backfill.get_coverage_for_season` (`per_fixture_backfill.py:97-146`), che seleziona e restituisce SOLO
   i 5 flag per-partita (`events, lineups, team_stats, player_stats, odds`). Quindi `coverage.get("standings")`,
   `.get("injuries")`, `.get("top_scorers")`... sono SEMPRE `None`: il ramo non scatta mai, per nessuna lega.
   Prova dal log del Daily di oggi (`gh run view 36101390338 --log`, 3.576 righe del job `run-backfill`): **0** righe con
   `injur`, **0** `/standings per`, **0** `topscorers`/`topassists`/`topyellowcards`; 68 letture di coverage per-partita.
   Gli aggregati si aggiornano quindi SOLO quando l'utente lancia a mano l'orchestratore (es. 135 oggi alle 08:13,
   `standings=True` -> la classifica "aggiornata oggi"); `injuries` 2026 ferma al 03/06 = ultimo lancio manuale sulle 3
   leghe col flag True (31, 71, 952).
2. **Flag fermi** (seconda causa, gia' chiusa dal mapper che aggiorna): `injuries=true` su 3/792 righe 2026 perche' il
   mapper scriveva i flag solo al primo inserimento (`leagues_mapper.py` prima di `f015204`).
3. **Anche col flag giusto** il Daily aggregherebbe solo le stagioni delle partite di ieri: le stagioni vive senza
   partite ieri non si aggiornerebbero.

**Proposta (implementata): li fa il recupero giornaliero, per CADENZA, su TUTTE le stagioni vive**, non il Daily.
Motivo: un solo posto, costo proporzionale al bisogno reale (non 6 chiamate per ogni lega che ha giocato ieri), stop e
quota gia' governati. Il Daily NON e' stato toccato: il suo ramo aggregati resta codice morto (0 chiamate). Decisione
per l'utente: rimuoverlo (consigliato: evita che una "correzione" futura lo riaccenda con +~420 chiamate/giorno doppie)
oppure lasciarlo.

### 9.2 Definizione di "buco" per aggregato (`season_aggregates.py`, misurabile e leggera)

Dati: RPC `season_aggregates_summary` (nuova, `migrations/season_aggregates_2026-09-25.sql`) -> per (lega, stagione) e
per tabella: righe presenti e `ultimo = max(coalesce(updated_at, created_at))`; piu' la data dell'ultima partita FT.
Una aggregazione per tabella filtrata su (league_id, season_year), a blocchi di 150 coppie (<= 900 righe).
Piu' `season_backfill_state.stats_json.aggregati_tentativi[nome] = {at, esito}` (ultimo tentativo del recupero).

| Stato | Regola | Si chiama? | Buco? |
|---|---|---|---|
| `flag_false` | flag di coverage False | no | no, dichiarato nel referto |
| `errore` | ultimo tentativo `errore` (API/delete) o `parziale` (insert a meta') | si' | si' |
| `mancante` | nessuna riga e nessun tentativo riuscito | si' | si' |
| `da_aggiornare` | per cadenza (T = ultimo aggiornamento o ultimo tentativo riuscito): **standings** partite FT dopo T (dopo ogni giornata); **injuries** stagione viva e T > 20 h fa (ogni giorno, 2 finestre del recupero); **top_scorers/top_assists/top_cards** partite FT dopo T e, se viva, T > 7 gg fa (settimanale), se passata una volta dopo l'ultima partita | si' | si' |
| `vuoto_api` | 0 righe, ultimo tentativo `vuoto`, nulla da aggiornare | no | no, dichiarato |
| `ok` | altrimenti | no | no |

Gli aggregati da fare entrano in `Lacune.aperti` (quindi in `completed`, in `buco_aperto_dal`, nel fail-loud dei buchi
vecchi con la causa "aggregati ancora da fare: ...") e nel costo (`Lacune.chiamate_aggregati`).

### 9.3 Idempotenza degli script storici (verificata nel codice)

`standings_backfill.py`, `injuries_backfill.py`, `top_scorers_backfill.py`, `top_assists_backfill.py`,
`top_cards_backfill.py`: delete per (league_id, season_year) + insert -> una riesecuzione normale NON duplica.
**Ma** `delete_existing_*` (`standings_backfill.py:221`, `injuries_backfill.py:191`, `top_scorers_backfill.py:217`,
`top_assists_backfill.py:217`, `top_cards_backfill.py:226`) cattura l'eccezione della delete, la logga e l'insert parte
lo stesso: **una delete fallita (es. 57014) = righe DOPPIE**. Inoltre `fetch_*` restituisce `None` sia su errore sia su
risposta vuota. Il recupero NON usa piu' i loro orchestratori: `season_aggregates.esegui_aggregato` usa le loro
funzioni di MAPPING (colonne vere invariate) con: client condiviso (chiamate contate nella quota), errore != vuoto
(`_risposta_o_none`), delete fallita -> nessun insert (esito `errore`), insert fallito -> `parziale` (rifatto al giro
dopo). Proposta per l'utente: correggere `delete_existing_*` (rilanciare l'eccezione) negli script, usati ancora dalle
CLI manuali; non toccati qui.

### 9.4 Costo API e quota

Chiamate per lega-stagione: standings 1, injuries 1, top_scorers 1, top_assists 1, **top_cards 2**
(`/players/topyellowcards` + `/players/topredcards`) = 6 al massimo. Nel piano: `costo = per-partita + /fixtures (se
serve) + aggregati DA FARE`; prima di ogni aggregato `quota.copre(costo)`; stop pulito. Prima (f015204) gli aggregati
erano stimati "1 per flag True" (top_cards sottostimato di 1) e rifatti tutti a ogni lavoro sulla stagione.

Stima di regime (dati del coordinatore: 792 righe coverage 2026, `standings=true` 453, `injuries=true` 3 oggi;
2025 `injuries=true` 126/998 = 12,6%):
- standings dopo ogni giornata: ~le leghe che hanno giocato dall'ultimo aggiornamento, ~70-150/giorno;
- injuries ogni giorno: ~100 stagioni vive col flag dopo il mapper (12,6% di 792) -> ~100/giorno;
- top_* settimanale con partite nuove: ~453 x 4 / 7 ~ 260/giorno (numero dei flag top_* non misurato: assunto = standings);
- totale di regime ~430-510 chiamate/giorno, dentro la capacita' 4.500 (7.500 - riserva 3.000).

**Primo giorno dopo il mapper aggiornato** (tutto "mancante" o "da_aggiornare"): standings ~453 + injuries ~100 +
top_* ~453 x 4 = 1.812 -> **~2.365 chiamate** per le stagioni 2026 (piu' le 2025 ancora vive, non misurabili senza DB),
in concorrenza con il recupero per-partita nella stessa coda (P1 leghe dei bot prima). Con il margine di oggi (3.424)
ci stanno in un giorno se il per-partita non e' grande; altrimenti si chiude in 2 giorni, dichiarato nel referto
("RINVIATO ... stima giorni"). Nessun rischio di quota: stop prima di ogni aggregato.

### 9.5 Referto e dry-run

- REFERTO BUCHI: sotto ogni lega-stagione con buchi, riga `aggregati da fare: standings=errore(2026-09-20), ...`;
  sezione **AGGREGATI** con i conteggi per stato di ciascun aggregato (`flag_false N` = non chiamato, `vuoto_api N` =
  l'API non ha dati) e la cadenza; il costo della riga include gli aggregati.
- Dry-run dell'orchestratore: per ogni stagione una riga
  `aggregati: standings=da_aggiornare(2026-09-20) ~1  injuries=mancante(-) ~1  top_scorers=... top_cards=mancante(-) ~2`,
  e `Chiam.~` li include. Serve la migrazione nuova anche per il dry-run (senza: exit 2 con il nome del file).

### 9.6 Migrazioni (le applica l'utente, in quest'ordine)

1. `migrations/season_gaps_2026-09-25.sql` (gia' in `f015204`);
2. **`migrations/season_aggregates_2026-09-25.sql`** (nuova, additiva: 1 funzione, avviso se manca l'indice
   (league_id, season_year));
3. `migrations/aggregati_idx_2026-09-25_SOLO_SE_MANCANO.sql` (opzionale, solo se il punto 2 lo chiede).
SQL riletto con il parser di PostgreSQL (pglast); NON eseguito su un Postgres.

### 9.7 Test e falsificazione

Nuovi test (`test_backfill_automatico_2026_09_25.py`, sezione 8; finti: `/standings` e `/injuries` con la struttura
reale, righe aggregati con `created_at/updated_at`, RPC `season_aggregates_summary` riprodotta in Python):

| Requisito | Test | Mutazione (ROSSA) |
|---|---|---|
| aggregato mancante -> in coda e chiamato; rilancio -> 0 chiamate | `test_agg_mancante_va_in_coda_ed_e_chiamato_poi_db_senza_buchi` (6 chiamate, 2 righe classifica, 1 infortunio, top_* vuoti dichiarati, secondo giro 0) | M50 mai chiamati; M51 costo fuori coda; M58 vuoto non ricordato; M60 catchup senza aggregati |
| presente e fresco -> 0 chiamate | `test_agg_presente_e_fresco_zero_chiamate` | M53 classifica sempre da rifare |
| cadenze | `test_agg_cadenza_classifica_dopo_giornata_injuries_giornaliero_top_settimanale` | M54, M55 |
| flag False -> non chiamato e dichiarato | `test_agg_flag_false_non_chiamato_e_dichiarato` | M52 |
| idempotenza; delete fallita -> nessun insert; parziale -> errore | `test_agg_idempotente_nessuna_riga_doppia_e_delete_fallita_non_inserisce` | M56, M61 |
| errore API != vuoto, resta buco nel referto | `test_agg_errore_api_non_e_vuoto_e_resta_buco` | M57 |
| dry-run mostra gli aggregati | `test_agg_dry_run_mostra_gli_aggregati_per_stagione` | M59 |

Suite: `pytest test_actions_fail_rumoroso_2026_09_25.py test_backfill_automatico_2026_09_25.py` -> **55 passed**
(48 + 7 nuovi; i 48 precedenti sono rimasti verdi senza cambiarne le aspettative: i mondi dei vecchi test hanno i flag
aggregati False). Mutazioni: `python AUDIT_2026-09-25/mutazioni_backfill_automatico.py` -> **61/61 ROSSE**
(M16 riallineata al nuovo bersaglio `fisse = 1 if ...`: senza aggregati "fissi" il rilancio resta a 0 chiamate),
ripristino verificato con sha256. SQL nuovo riletto con pglast: 7 statement, corpo della funzione e blocco DO OK.

Non verificato: SQL non eseguito; stima dei costi basata sui numeri del coordinatore (flag top_* 2026 non misurati);
paginazione di `/injuries` per lega+stagione assunta assente (come negli script storici, che fanno 1 chiamata);
la colonna `updated_at` degli aggregati assunta con default `now()` all'insert (lo schema la ha; se fosse sempre NULL
vale `created_at`, gia' gestito con `coalesce`).
