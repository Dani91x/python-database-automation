# Ordine di applicazione — 11/09/2026 (sera)

Revisione statica (NO esecuzione, NO scrittura sul DB). Parser SQL locale non
disponibile: `.venv` non ha `pglast` né `sqlglot` (`ModuleNotFoundError` per
entrambi). Verifica fatta a mano: dollar-quoting, firme delle funzioni
(`CREATE OR REPLACE` con nomi/tipi identici alle versioni precedenti in
TUTTI i `migrations/*.sql`), `DROP FUNCTION IF EXISTS` con firme esatte,
`RETURNS` invariato, `SECURITY DEFINER` + `SET search_path`, `REVOKE/GRANT`,
`IF NOT EXISTS`, cast da jsonb protetti, colonne confrontate con i
`CREATE TABLE` di `omega_bot.sql` / `safe_strategy_bot.sql` / `mike_bot.sql`
/ `daily_history.sql` (+ tutte le ALTER TABLE successive). Riscontro con la
sonda sul DB reale (stato 11/09 sera, prima di applicare nulla).

## Precondizione verificata sul DB reale

- `omega_daily_v2.sql` e `omega_models_v4.sql` sono **già applicate**:
  - `select public.get_omega_state()` → OK, ritorna `control/aggregates/activity`.
  - `select public.get_omega_daily()` → OK, righe con `goal_snapshot` (true/false)
    e `by_strategy` per `phase` (`ht_cs`/`ft_cs`) → confermano anche
    `omega_missions.sql`/`omega_manual.sql`/`omega_v2.sql`/`omega_cashout.sql`
    /`omega_models_v3.sql` già applicate (prerequisiti dichiarati in testa a
    `omega_models_v5.sql`).
  - `select public.get_mike_daily('2026-09-01','2026-09-11')` → **KO**:
    `function public.trading_daily_history(unknown, unknown, unknown, unknown,
    date, date, unknown) is not unique` (42725). Causa: `mike_history.sql`
    (vecchia, 7/3 argomenti) e `omega_daily_v2.sql`/`omega_models_v4.sql`
    (8/4 argomenti, l'ultimo con DEFAULT) coesistono come **overload** —
    la chiamata a 7 argomenti di `get_mike_daily` è ambigua. Esattamente il
    bug R2 descritto nell'intestazione di `mike_history_v2.sql`.
  - `select public.get_mike_aggregates()` → **KO**: `PGRST202 — Could not
    find the function public.get_mike_aggregates` (non esiste ancora:
    `mike_bot_v2.sql` non applicata).

## Ordine da applicare oggi

1. **`migrations/mike_bot_v2.sql`**
2. **`migrations/mike_history_v2.sql`**
3. **`migrations/safe_strategy_bot_v2.sql`**
4. **`migrations/omega_models_v5.sql`**
5. **`migrations/omega_models_v6.sql`** *(aggiunta 12/09 — certificazione chirurgica Omega)*
6. **`migrations/safe_strategy_paper_live_2026-09-13.sql`** *(aggiunta 13/09 — separazione paper/live di Safe Strategy)*

`omega_models_v5.sql` è indipendente dalla catena Mike/Safe (tocca solo
`omega_*`) e potrebbe stare ovunque nell'elenco; la sequenza sopra è quella
con il minor numero di stati intermedi "a metà" (Mike prima, poi Safe che
lo richiede esplicitamente in testa, poi Omega).
**`safe_strategy_paper_live_2026-09-13.sql` va DOPO `safe_strategy_bot_v2.sql`**
(punto 3): ridefinisce le stesse funzioni aggiungendo il parametro `p_mode`, e
se il v2 venisse applicato dopo rimetterebbe in vita le firme SENZA parametro
ricreando l'overload ambiguo. Rispetto a `omega_models_v6.sql` (punto 5) è
indipendente: tocca solo `safe_*` e non ridefinisce
`trading_daily_history`/`trading_day_trades`, le richiama soltanto.

**`omega_models_v6.sql` va per ULTIMA fra le migrazioni Omega**: la sua verifica finale pretende che
`trading_daily_history` / `trading_day_trades` abbiano UNA sola firma (quella
a 8/4 argomenti di `mike_history_v2.sql`) e solleva un'eccezione con il
rimedio se non è così — applicarla prima del punto 2 fallirebbe di proposito.

---

### 1. `mike_bot_v2.sql`
**Fa**: aggiunge colonne difensive (`closes_trade_id` su `mike_trades`,
`result` su `mike_requests`, entrambe già presenti da `mike_bot.sql` — qui
solo `IF NOT EXISTS`), stato `'rejected'` su `mike_requests.status`, crea
`mike_aggregates_sql()`/`get_mike_aggregates()` (KPI in una sola scansione,
liability NETTA da `mike_events.live->>'liability'` con fallback dichiarato
`liability_source`), e ridefinisce `get_mike_state()` con `requests[]` e
`aggregates` veri.
**Se non applicata**: il servizio Python funziona (fallback), ma
`get_mike_aggregates` resta assente (`PGRST202`, come oggi), i cash-out
rifiutati restano `'error'` invece di `'rejected'`, e `get_mike_state()`
non espone `requests`/KPI di giornata → UI Mike con dati vecchi.
**Verifica**:
```sql
select public.get_mike_aggregates();                 -- deve rispondere (non più PGRST202)
select jsonb_object_keys(public.get_mike_state());    -- deve includere 'requests'
select status, count(*) from public.mike_requests group by status;  -- 'rejected' ammesso
```

### 2. `mike_history_v2.sql`
**Fa**: **DROP** delle firme vecchie a 7/3 argomenti di
`trading_daily_history`/`trading_day_trades` (quelle rimesse da
`mike_history.sql`) e **CREATE OR REPLACE** delle firme a 8/4 argomenti
(stessa base di `omega_daily_v2.sql`/`omega_models_v4.sql`) con la whitelist
tabelle estesa a `'mike_trades'`; aggiunge il clamp a 400 giorni (M-17) e
corregge `hedged_closed`/`commission_paid`; ridefinisce `get_mike_daily`/
`get_mike_day_trades` passando **tutti** gli argomenti con `p_day_by='placed'`.
**Se non applicata**: resta l'overload ambiguo di oggi — `get_mike_daily()`
(e qualunque chiamata a `trading_daily_history`/`trading_day_trades` con
meno di 8/4 argomenti) fallisce con `42725 is not unique`; lo storico di
Mike resta rotto. Applicando SOLO questa senza `mike_bot_v2.sql` non cambia
nulla di negativo (idempotente, non dipende in modo stretto da
`mike_bot_v2.sql`: `closes_trade_id` esiste già da `mike_bot.sql`).
**Verifica**:
```sql
select count(*) from pg_proc where proname = 'trading_daily_history';  -- deve dare 1
select count(*) from pg_proc where proname = 'trading_day_trades';     -- deve dare 1
select public.get_mike_daily('2026-09-01','2026-09-11');               -- niente più 42725
```

### 3. `safe_strategy_bot_v2.sql`
**Fa**: `'rejected'` su `safe_strategy_requests.status`; nuovi indici;
`safe_aggregates_sql()`/`get_safe_aggregates()` (una scansione, liability
RESIDUA post-copertura, `reconciling_liability`, `day_liability` = capitale
impegnato); ridefinisce `get_safe_state()` (aggiunge `activity`,
`params_effective`, `reconciling_liability`, esito per SEGNO del P&L di
posizione) e crea `get_safe_activity()`; `get_safe_daily`/`get_safe_day_trades`
ora passano `p_day_by='placed'` alle funzioni condivise (di cui NON
ridefinisce la logica: la richiama solo).
**Se non applicata**: il servizio tollera (fallback a scansione a pagine),
ma i cash-out rifiutati restano `'error'`, `get_safe_state()` non espone
`activity`/`params_effective`, e KPI/pannello rischio/tab Trade/storico
continuano a usare tre attribuzioni di giornata diverse (C-01 non risolto).
**Perché va dopo `mike_history_v2.sql`**: il file lo dichiara in testa
(punto 7 del suo ordine di applicazione) — `get_safe_daily` chiama
`trading_daily_history` con TUTTI gli argomenti quindi non sarebbe ambigua
comunque, ma se `mike_history_v2.sql` non è ancora applicata l'overload a
7 argomenti resta vivo nel DB (nessun danno diretto a Safe, ma lo stato
del DB è inconsistente con l'intestazione del file — rispettare l'ordine
dichiarato dall'autore).
**Verifica**:
```sql
select public.get_safe_state();                       -- deve avere 'activity' e 'params_effective'
select status, count(*) from public.safe_strategy_requests group by status;  -- 'rejected' ammesso
select public.get_safe_daily('2026-09-01','2026-09-11');
```

### 4. `omega_models_v5.sql`
**Fa**: ridefinisce `omega_aggregates_sql()` (H-02 conta i `pending` in
riconciliazione come piazzati; H-06 liability = 0 a copertura completa con
nuovo `locked_pnl_open`/`locked_pnl_open_today`; H-08 `live_now` = partite
con posizione viva ADESSO) e `get_omega_state()` (M-22 `activity` filtrata
sulla giornata operativa Europe/Rome, non "ultime N righe"; espone
`goal_snapshot`); ricrea gli indici unique parziali `uq_omega_trades_auto_leg`
/ `uq_omega_trades_leg` escludendo `meta->>'leg_failed'='true'` (H-13) e un
indice di supporto.
**Se non applicata**: il servizio funziona comunque (Python ha il proprio
`omega_engine.aggregate_trades` e tollera l'RPC vecchia), ma la UI continua
a non contare il pending in riconciliazione, conta come rischio una perdita
già bloccata (cap di esposizione falsato), l'attività "di oggi" può mostrare
righe di ieri dopo mezzanotte, e una gamba con esito CERTO negativo
(`meta.leg_failed=true`) non si ripiazza (nessun danno economico, solo
occasione persa: l'insert fallisce e il ciclo logga `already_reserved`).
**Verifica**:
```sql
select public.get_omega_state();                       -- 'aggregates' deve avere
                                                         -- locked_pnl_open, live_now,
                                                         -- reconciling_liability
select public.omega_aggregates_sql()->'locked_pnl_open_today';
select indexdef from pg_indexes where indexname = 'uq_omega_trades_auto_leg';
                                                         -- deve escludere leg_failed
```

### 5. `omega_models_v6.sql` (aggiunta 12/09)
**Fa**: ridefinisce `omega_aggregates_sql()` allineandola in due punti residui a
`omega_engine.aggregate_trades` (S-01: `hedged_size` conta solo se NON null;
il bloccato include anche un `pending` piazzato a copertura completa);
ridefinisce `get_omega_missions()` con gli STESSI criteri di rischio dei KPI
(S-02: `hedged`/flumine/riconciliazione contano come vive, le gambe di
chiusura non sommano il loro stake in `open_liability` né in `n_open`;
nuove chiavi `locked_pnl`, `reconciling_liability` per gamba) e manda per ogni
trade un `meta` RIDOTTO al contratto UI + `closes_trade_id`/`settled_at`
(S-03: prima la scheda missione leggeva `meta` che la RPC non mandava);
REVOKE/GRANT espliciti su `get_omega_missions` (S-04); DROP IF EXISTS degli
overload a 7/3 argomenti di `trading_daily_history`/`trading_day_trades` e
**verifica finale** che ne resti ESATTAMENTE una firma (S-05: eccezione con
rimedio, mai uno stato ambiguo silenzioso).
**Se non applicata**: il servizio funziona (Python ha il proprio
`aggregate_trades`), ma il tab Missione mostra rischio/conteggi diversi dalla
barra di giornata e non dice mai «IN VERIFICA SU BETFAIR»; il bloccato di
giornata dell'RPC resta 0 su un pending piazzato a copertura completa.
**Verifica**:
```sql
select jsonb_object_keys(public.omega_aggregates_sql());      -- 17 chiavi (§17.3)
select public.get_omega_missions();                             -- legs.*.trades[].meta e closes_trade_id
select count(*) from pg_proc where proname = 'trading_daily_history';  -- 1
select count(*) from pg_proc where proname = 'trading_day_trades';     -- 1
```

### 6. `safe_strategy_paper_live_2026-09-13.sql` (aggiunta 13/09)
**Fa**: chiude la mescolanza PAPER/LIVE della sezione Safe Strategy trovata
dalla certificazione del 13/09 (la colonna `safe_strategy_trades.mode` esisteva
dal primo giorno e non la leggeva nessuna query).
1. `safe_aggregates_sql` / `get_safe_aggregates` / `get_safe_state` /
   `get_safe_trades` / `get_safe_daily` / `get_safe_day_trades` prendono un
   `p_mode text DEFAULT NULL` (`NULL` = tutte le modalità, cioè il comportamento
   di oggi) e filtrano le righe; le firme PRECEDENTI vengono **droppate** con la
   firma esatta, così la chiamata a zero argomenti non diventa ambigua. Gli
   aggregati espongono in più `mode`, `realized_paper_total`,
   `realized_live_total`.
2. Nuovo indice unico parziale `uq_safe_trades_closing_inflight`
   `(closes_trade_id) WHERE closes_trade_id IS NOT NULL AND status = 'pending'`:
   **una sola chiusura IN VOLO per apertura**. I cash out parziali ripetuti
   restano possibili (le chiusure già fillate sono `'open'`, non `'pending'`).
3. `uq_safe_trades_signal` sostituito da `uq_safe_trades_signal_mode` (stesse
   colonne **più `mode`**): paper e live hanno spazi di idempotenza separati. Il
   nuovo indice è creato PRIMA e il vecchio rimosso DOPO, e solo se il nuovo
   esiste: il nuovo è strettamente più debole del vecchio, quindi non può
   fallire su dati che il vecchio sta già imponendo.
4. `safe_stop()` riporta `control.mode` a `'paper'` (fail-safe: il LIVE non si
   eredita da una sessione precedente).
5. Nuova RPC `safe_set_mode(p_mode text)`: persiste la modalità **anche a bot
   fermo**, owner-only, `SECURITY DEFINER` con `search_path` fissato.
6. `safe_request` rifiuta (in italiano) una richiesta la cui modalità non
   coincide con `safe_strategy_control.mode`.
Chiude con un `DO` di verifica che ogni funzione Safe toccata abbia **una sola**
firma, e avvisa se uno dei due indici unici non è stato creato.
**Se non applicata**: il Python continua a funzionare (le firme vecchie non
accettano `p_mode`, `bot_db.aggregates` se ne accorge e ripiega sulla scansione
Python **già filtrata per modalità**, quindi i cap di rischio sono comunque
separati), ma: la UI continua a sommare euro veri e simulati in «P&L oggi»,
«P&L totale», «liability aperta» e storico; un trade paper su un segnale
continua a impedire lo stesso trade in live; due processi possono ancora creare
due chiusure contemporanee sulla stessa apertura e **invertire** la posizione;
fermando il bot in LIVE la modalità resta `'live'` sul control; a bot fermo la
modalità vive solo nel browser e nessun'altra sessione la conosce.
**Perché va dopo `safe_strategy_bot_v2.sql`**: ridefinisce le stesse funzioni.
Applicata PRIMA, il v2 le riporterebbe alla firma senza `p_mode` e il DB
tornerebbe allo stato di partenza (o, peggio, con l'overload doppio).
**Verifica**:
```sql
select public.get_safe_aggregates();          -- tutte le modalità (come oggi)
select public.get_safe_aggregates('live');    -- SOLO soldi veri
select public.get_safe_aggregates('paper');   -- SOLO simulato
select public.get_safe_state() -> 'mode';     -- null = nessun filtro
select public.safe_set_mode('paper');         -- persiste la modalità a bot fermo
select indexname from pg_indexes where schemaname = 'public'
  and indexname in ('uq_safe_trades_signal_mode','uq_safe_trades_closing_inflight');
                                              -- devono esserci ENTRAMBI
select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
 where n.nspname = 'public' and p.proname = 'get_safe_state';   -- deve dare 1
```

## Avvertenze

- **`safe_strategy_paper_live_2026-09-13.sql` va rieseguito ogni volta che si
  riapplica `safe_strategy_bot_v2.sql`, `safe_strategy_bot.sql`,
  `daily_history.sql` o `omega_daily_v2.sql`**: quei file ricreano
  `get_safe_state()`, `get_safe_aggregates()`, `safe_aggregates_sql()`,
  `get_safe_trades(integer)`, `get_safe_daily(date,date,text)` e
  `get_safe_day_trades(date,text)` **senza** `p_mode`, e si torna all'overload
  ambiguo (42725 «is not unique») più alla mescolanza paper/live. È la stessa
  regola già valida per `trading_daily_history`/`trading_day_trades`.
- Gli altri due file del 12–13/09 presenti in `migrations/`
  (`omega_activity_realtime_2026-09-12.sql`, che aggiunge solo tabelle alla
  publication Realtime, e `mike_aggregati_per_modalita_2026-09-13.sql`, che
  tocca solo le funzioni `mike_*`) **non definiscono nessuna funzione `safe_*`**
  né le funzioni condivise: il loro ordine rispetto al punto 6 è libero.
- **Nessuna delle 4 migrazioni fa DROP/ricrea `trading_daily_history` /
  `trading_day_trades` eccetto `mike_history_v2.sql`.** Se in futuro si
  RIAPPLICA `omega_models_v4.sql` (che ricrea l'8-arg SENZA la whitelist
  `mike_trades` e senza il clamp 400gg), bisogna **riapplicare anche
  `mike_history_v2.sql`** subito dopo — lo dice esplicitamente l'intestazione
  di `mike_history_v2.sql`. Lo stesso vale per `omega_daily_v2.sql`.
- **Non toccare `daily_history.sql` da solo dopo oggi**: rimette in vita la
  firma a 7/3 argomenti e ricrea l'overload ambiguo appena risolto (stesso
  bug di `mike_history.sql`). Se va rieseguita per qualunque motivo,
  rieseguire `mike_history_v2.sql` subito dopo.
- `safe_strategy_bot_v2.sql` NON ridefinisce `trading_daily_history` /
  `trading_day_trades`: dipende dal fatto che a quel punto esista GIÀ la
  sola versione a 8/4 argomenti (punto 2). Se per errore la si applica PRIMA
  di `mike_history_v2.sql`, non rompe nulla di per sé (chiama sempre con
  tutti gli argomenti), ma lascia il DB nello stato ambiguo per Mike più a
  lungo — meglio seguire l'ordine sopra.
- Tutte e 4 le migrazioni sono dichiarate IDEMPOTENTI dagli autori
  (`CREATE OR REPLACE` a firma invariata rispetto alla versione live dopo il
  passo precedente, `IF NOT EXISTS`/`IF EXISTS` su colonne/indici/vincoli) e
  non toccano dati esistenti: rieseguibili senza rischio nell'ordine sopra.
- `get_mike_aggregates()` (in `mike_bot_v2.sql`) è l'unica, tra le nuove RPC
  owner-only equivalenti (`get_omega_aggregates`, `get_safe_aggregates`), a
  **non** contenere il controllo `IF NOT public.betfair_live_is_owner() THEN
  RAISE EXCEPTION ...` nel suo corpo — è concessa a `authenticated` via GRANT
  ma qualunque utente autenticato (non solo l'owner) potrebbe chiamarla e
  leggere KPI/liability di Mike. Non è un problema di sintassi/firma (la
  migrazione applica comunque senza errori) ma una incoerenza di sicurezza
  rispetto al pattern usato ovunque altrove nello stesso file e nelle
  migrazioni gemelle. Correzione suggerita (non applicata):
  `mike_bot_v2.sql:127-134` — aggiungere lo stesso blocco owner-only di
  `get_omega_aggregates` (`omega_daily_v2.sql:176-186`) prima del `RETURN`.

## Esito revisione statica per file

| File | Esito | Note |
|---|---|---|
| `migrations/omega_models_v5.sql` | **OK** | Dollar-quoting bilanciato (4× `$$`); firme `omega_aggregates_sql()` e `get_omega_state(integer)` identiche a `omega_daily_v2.sql`/`omega_models_v4.sql`/`omega_bot.sql`/`omega_cashout.sql`; nessun `DROP FUNCTION` necessario (nessun cambio di tipo/numero argomenti); colonne (`phase`, `origin`, `meta`, `closes_trade_id`, `bet_id`, `liability`, `event_id`, `market_id`, `selection_id`, `side`, `status`, `pnl`, `placed_at`) tutte presenti in `omega_bot.sql`+`omega_v2.sql`+`omega_manual.sql`+`omega_cashout.sql`+`omega_missions.sql`; `SECURITY DEFINER`+`search_path` presenti; `REVOKE/GRANT` coerenti; indici con `IF NOT EXISTS`/`DROP INDEX IF EXISTS` corretti. |
| `migrations/safe_strategy_bot_v2.sql` | **OK** | Dollar-quoting bilanciato (14× `$$` + 4× `$e$`); tutte le firme (`get_safe_daily(date,date,text)`, `get_safe_day_trades(date,text)`, `safe_request(text,jsonb)`, `get_safe_state()`) identiche alle versioni precedenti in `daily_history.sql`/`omega_daily_v2.sql`/`safe_strategy_bot.sql`; `get_safe_aggregates()`/`safe_aggregates_sql()`/`get_safe_activity()` sono nuove (nessun conflitto); colonne di `safe_strategy_trades`/`safe_strategy_requests`/`safe_strategy_activity` tutte verificate contro `safe_strategy_bot.sql`; NON ridefinisce `trading_daily_history`/`trading_day_trades` (corretto: dipende da `mike_history_v2.sql` applicata prima, come dichiarato in testa al file). |
| `migrations/mike_bot_v2.sql` | **OK**, con 1 osservazione | Dollar-quoting bilanciato (8× `$$`); `get_mike_state()` a firma invariata rispetto a `mike_bot.sql`; `mike_aggregates_sql()`/`get_mike_aggregates()` nuove; colonne (`closes_trade_id`, `result`) aggiunte con `IF NOT EXISTS` (già presenti da `mike_bot.sql`, no-op sicuro); CHECK su `mike_requests.status` in DO-block con DROP+ADD, nessun valore esistente fuori whitelist. Osservazione (non bloccante): `get_mike_aggregates()` — righe 127-134 — manca il controllo `betfair_live_is_owner()` presente nelle funzioni gemelle `get_omega_aggregates`/`get_safe_aggregates` (vedi Avvertenze). |
| `migrations/safe_strategy_paper_live_2026-09-13.sql` | **OK** (revisione statica 13/09, NO esecuzione) | Dollar-quoting bilanciato (18× `$$` = 9 corpi di funzione, 6× `$mig$` = 3 blocchi `DO`, 4× `$e$` = 2 coppie dentro `get_safe_daily`); nessun `$$` accidentale dentro le regex `'^-?[0-9]+(\.[0-9]+)?$'`. Overload: ogni funzione è preceduta dal `DROP FUNCTION IF EXISTS` della firma ESATTA precedente (`safe_aggregates_sql()`, `get_safe_aggregates()`, `get_safe_state()`, `get_safe_trades(integer)`, `get_safe_daily(date,date,text)`, `get_safe_day_trades(date,text)`) — verificate una per una contro `safe_strategy_bot.sql`/`safe_strategy_bot_v2.sql`/`daily_history.sql`/`omega_daily_v2.sql`; `safe_stop()`/`safe_request(text,jsonb)` restano a firma INVARIATA (`CREATE OR REPLACE` puro); `safe_set_mode(text)` è nuova. Colonne verificate contro i `CREATE TABLE` di `safe_strategy_bot.sql` (`mode`, `closes_trade_id`, `status`, `pnl`, `liability`, `origin`, `signal_key`, `meta`, `placed_at`, `bet_id`, `strategy`, `sport`, `event_id` su `safe_strategy_trades`; `mode`/`status`/`updated_at` su `safe_strategy_control`). `RETURNS` invariato ovunque (jsonb, bigint). `SECURITY DEFINER` + `SET search_path = public, pg_temp` su tutte; `REVOKE/GRANT` riscritti sulle nuove firme con gli stessi destinatari di prima (`service_role` per `safe_aggregates_sql`, `authenticated, service_role` per le RPC). Nessun `DELETE`/`TRUNCATE`/`DROP TABLE`/`DROP COLUMN`; RLS non toccata. Frammenti SQL passati a `trading_daily_history`/`trading_day_trades` costruiti con `format(%L)` **dopo** la whitelist `('paper','live')`: nessuna iniezione. In `RAISE` usato solo `%` (niente `%I`/`%L`, che PL/pgSQL non interpreta). |
| `migrations/mike_history_v2.sql` | **OK** | Dollar-quoting bilanciato (8× `$$` + 4× `$e$` + 4× `$q$`); **contiene i `DROP FUNCTION IF EXISTS`** mancanti altrove per risolvere l'overload (`trading_daily_history(text,text,text,text,date,date,numeric)` e `trading_day_trades(text,text,date)`), firme esatte verificate contro `daily_history.sql`/`mike_history.sql`; le nuove firme a 8/4 argomenti sono IDENTICHE a quelle già live da `omega_daily_v2.sql`/`omega_models_v4.sql` (stesso ordine/tipo parametri, stesso DEFAULT su `p_day_by`); whitelist tabelle estesa correttamente a `'mike_trades'`; cast `nullif(meta->>'commission_paid','')::numeric` protetto da `nullif`; `get_mike_daily`/`get_mike_day_trades` chiamano SEMPRE tutti gli argomenti → nessuna nuova ambiguità. |

## Parser SQL locale

Non disponibile: `.venv/Scripts/python -c "import pglast"` e
`import sqlglot` falliscono entrambi con `ModuleNotFoundError` (nessuno dei
due package è installato nell'ambiente). Nessuna verifica automatica di
parsing eseguita; la revisione sopra è manuale (conteggio dollar-quote,
confronto testuale delle firme, riscontro colonne su `CREATE TABLE`/`ALTER
TABLE`, riscontro con lo stato reale del DB via sonda).
