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

`omega_models_v5.sql` è indipendente dalla catena Mike/Safe (tocca solo
`omega_*`) e potrebbe stare ovunque nell'elenco; la sequenza sopra è quella
con il minor numero di stati intermedi "a metà" (Mike prima, poi Safe che
lo richiede esplicitamente in testa, poi Omega).

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

## Avvertenze

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
| `migrations/mike_history_v2.sql` | **OK** | Dollar-quoting bilanciato (8× `$$` + 4× `$e$` + 4× `$q$`); **contiene i `DROP FUNCTION IF EXISTS`** mancanti altrove per risolvere l'overload (`trading_daily_history(text,text,text,text,date,date,numeric)` e `trading_day_trades(text,text,date)`), firme esatte verificate contro `daily_history.sql`/`mike_history.sql`; le nuove firme a 8/4 argomenti sono IDENTICHE a quelle già live da `omega_daily_v2.sql`/`omega_models_v4.sql` (stesso ordine/tipo parametri, stesso DEFAULT su `p_day_by`); whitelist tabelle estesa correttamente a `'mike_trades'`; cast `nullif(meta->>'commission_paid','')::numeric` protetto da `nullif`; `get_mike_daily`/`get_mike_day_trades` chiamano SEMPRE tutti gli argomenti → nessuna nuova ambiguità. |

## Parser SQL locale

Non disponibile: `.venv/Scripts/python -c "import pglast"` e
`import sqlglot` falliscono entrambi con `ModuleNotFoundError` (nessuno dei
due package è installato nell'ambiente). Nessuna verifica automatica di
parsing eseguita; la revisione sopra è manuale (conteggio dollar-quote,
confronto testuale delle firme, riscontro colonne su `CREATE TABLE`/`ALTER
TABLE`, riscontro con lo stato reale del DB via sonda).
