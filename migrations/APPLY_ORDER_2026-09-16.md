# Ordine di applicazione — 16/09/2026 (sera), da applicare il 17/09

Revisione statica + riscontro sul DB reale (SOLA LETTURA: nessuna scrittura, nessuna RPC
che modifica dati, nessun `git`/codice toccato). Stesso metodo di
`migrations/APPLY_ORDER_2026-09-11.md`: dollar-quoting contato a mano, firme confrontate
testualmente contro TUTTI i `migrations/*.sql` precedenti, colonne confrontate con i
`CREATE TABLE`/`ALTER TABLE` sorgente, chiamanti cercati con grep in `Betfair/` e
`frontend/src`, riscontro con una sonda REST/RPC sola-lettura sul DB reale
(`sonda_migrazioni.py`, script dell'utente, più una sonda aggiuntiva mia per
`get_safe_aggregates(p_mode)` e `safe_strategy_control.params.stake`).

## Precondizione verificata sul DB reale (17/09, prima di applicare nulla)

- **Nessuna delle sei migrazioni è applicata**:
  - `omega_trades/safe_strategy_trades/mike_trades` → `size_requested` assente su tutte e
    tre (42703).
  - `omega_eventi_chiusi_dall_utente()` → PGRST202 (assente); `omega_events.stato_utente`
    → 42703 (assente).
  - `get_omega_proposte()` → PGRST202; tabella `omega_requests` → PGRST205 (assente).
  - `safe_strategy_control.params.stake` = `{"laySize": 2, "backSize": 3}`, **senza**
    `per_strategia`.
  - `safe_strategy_requests` con `kind='cashout_event'` → nessuna riga (il CHECK attuale
    la rifiuterebbe comunque).
  - Non verificabile in sola lettura: il corpo vivo di `omega_activate` e di
    `safe_request` (PostgREST non espone il sorgente delle funzioni via REST). Per
    `safe_request` ho un riscontro **indiretto ma solido** (vedi Migrazione 3).
- **Le migrazioni dell'11–13/09 risultano applicate**: `get_omega_aggregates()` risponde
  con le chiavi di `omega_models_v6.sql` (nessun blocco `auto`, come atteso prima di
  oggi); `get_safe_aggregates()` **e** `get_safe_aggregates(p_mode:'live')` rispondono
  entrambe con `mode`/`realized_live_total`/`realized_paper_total` → questo è il modo in
  cui ho confermato che **`safe_strategy_paper_live_2026-09-13.sql` è viva sul DB**, il
  prerequisito del problema trovato nella Migrazione 3 sotto.

## Ordine da applicare (quello dell'handoff, confermato corretto)

1. `migrations/omega_activate_conserva_params_2026-09-16.sql`
2. `migrations/trades_consapevolezza_ordine_2026-09-16.sql`
3. `migrations/safe_cash_out_globale_e_cap_automatico_2026-09-16.sql` — **DA CORREGGERE
   prima di applicare** (vedi sotto: regressione reale, non ipotetica)
4. `migrations/omega_chiuso_dall_utente_2026-09-16.sql`
5. `migrations/omega_proposte_uscita_2026-09-16.sql`
6. `migrations/safe_strategy_stake_per_strategia_2026-09-16.sql` (facoltativa)

**Le sei sono fra loro indipendenti**: ciascuna tocca oggetti che le altre cinque non
toccano (rispettivamente: `omega_control`/`omega_activate` · 3 colonne su tre tabelle
trade · `safe_strategy_requests`/`safe_request` · `omega_events`+`omega_aggregates_sql`/
`get_omega_aggregates` · la nuova `omega_requests`+3 funzioni nuove ·
`safe_strategy_control.params` dati). Nessuna crea un overload ambiguo con un'altra delle
sei. L'ordine 1→6 dell'handoff può restare tale quale; l'unico problema reale non è di
**ordine** ma di **contenuto** della migrazione 3 (si presenta anche applicandola per
prima o per ultima: il difetto è nel file, non nella sequenza).

---

### 1. `omega_activate_conserva_params_2026-09-16.sql` — **OK**

**Fa**: `omega_activate(text,numeric,jsonb)` — stessa identica firma di
`omega_bot.sql:117` e `omega_daily_v2.sql:53` (nessun `DROP` necessario) — cambia UNA
riga: `params = coalesce(p_params, params)` al posto di
`coalesce(p_params, '{}'::jsonb)`. `REVOKE/GRANT` identici a prima. `SECURITY DEFINER` +
`search_path` presenti, owner-only.

**Verificato**:
- Firma testualmente identica in tutte e tre le occorrenze (`omega_bot.sql`,
  `omega_daily_v2.sql`, questo file).
- Chiamante: `frontend/src/lib/omega.ts:1183` (`activateOmega`) passa sempre
  `p_mode`/`p_daily_goal`/`p_params` — nomi coincidenti. Il frontend non chiama mai
  `omega_activate` senza parametri (`ParametriOmegaIgnoti` in
  `frontend/src/lib/interruttori.ts:341-350` lo impedisce), quindi il comportamento
  visibile non cambia OGGI — la correzione chiude il varco per chi non passa dal
  frontend (un altro client, un futuro script).
- `Betfair/tests/test_contratto_activate_params_2026_09_16.py` è un test di contratto
  già in repo che legge il sorgente SQL e falliforebbe se questa migrazione (o una
  successiva) tornasse ad azzerare: l'ho fatto eseguire concettualmente a mano
  (rilettura riga per riga) e la condizione che verifica (`params = coalesce(p_params,
  params)`, niente `'{}'`) è soddisfatta da questo file.
- Nota non bloccante: il commento in `frontend/src/lib/interruttori.ts:341` («omega_activate
  fa coalesce(p_params, '{}'::jsonb): SOVRASCRIVE sempre») descrive il comportamento
  VECCHIO e resta nel codice dopo questa migrazione — è solo un commento, non cambia
  comportamento, ma vale la pena aggiornarlo quando si tocca quel file.

**Verifica dopo l'applicazione**:
```sql
select proname, pg_get_functiondef(oid) ilike '%coalesce(p_params, params)%'
  from pg_proc where proname = 'omega_activate';               -- deve dare true
select count(*) from pg_proc where proname = 'omega_activate';  -- 1 (nessun overload)
```

---

### 2. `trades_consapevolezza_ordine_2026-09-16.sql` — **OK**

**Fa**: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (5 colonne: `size_requested`,
`size_matched`, `size_remaining`, `avg_price_matched`, `betfair_updated_at`) su
`omega_trades`, `safe_strategy_trades`, `mike_trades`. Nessuna RPC toccata, nessun CHECK,
nessuna colonna esistente modificata. `BEGIN`/`COMMIT` espliciti (le tre `ALTER` sono
atomiche insieme).

**Verificato**:
- Le tre tabelle esistono (`omega_bot.sql`, `safe_strategy_bot.sql`, `mike_bot.sql`).
- **Il codice è già DIFENSIVO su entrambi i lati**, quindi il rischio è basso in ENTRAMBI
  gli stati:
  - `Betfair/safe_strategy/execution.py:268-323` — `aggiorna_trade()` (usata anche da
    Omega e Mike, vedi sotto) prova a scrivere le 5 colonne nuove, e se Postgres risponde
    con un errore di schema (42703/PGRST204/"does not exist"/"schema cache") lo intercetta
    (`_errore_di_colonna`), marca `db._colonne_consapevolezza_assenti = True` UNA volta,
    e ripete l'`UPDATE` senza le colonne nuove. Non applicata → nessun crash, solo un
    warning di log e i dati restano nel solo `meta` JSONB.
  - Chiamanti confermati con grep: `Betfair/omega/omega_service.py:1490` (`X.aggiorna_trade`,
    import pigro di `Betfair.safe_strategy.execution as X`), `Betfair/mike/service.py:692,
    1217,1646,3748,3756` (stesso `X.aggiorna_trade`). Tutti e tre i bot passano dallo
    STESSO punto unico.
  - Nomi di chiave verificati uno per uno con grep (`size_requested`, `size_matched`,
    `size_remaining`, `avg_price_matched`, `betfair_updated_at`) contro le colonne della
    migrazione: identici.
- Le RPC di lettura (`get_omega_trades`, `get_safe_state`/`get_safe_trades`,
  `get_mike_state`/`get_mike_trades`) usano `to_jsonb(t.*)`/`SELECT *`: le colonne nuove
  arrivano alla UI senza toccare quelle RPC (verificato che nessuna delle RPC elenchi le
  colonne esplicitamente in modo da escluderle).

**Verifica dopo l'applicazione**:
```sql
SELECT table_name, column_name FROM information_schema.columns
 WHERE table_schema='public'
   AND table_name IN ('omega_trades','safe_strategy_trades','mike_trades')
   AND column_name IN ('size_requested','size_matched','size_remaining',
                       'avg_price_matched','betfair_updated_at')
 ORDER BY table_name, column_name;                       -- 15 righe attese
```

---

### 3. `safe_cash_out_globale_e_cap_automatico_2026-09-16.sql` — **CORRETTA il 17/09** (era: DA CORREGGERE — `safe_request` riparte testualmente dal corpo del 13/09, barriera `v_req_mode`/`v_ctrl_mode` reintegrata, falsificata rossa/verde da `Betfair/tests/test_contratto_safe_request_barriera_2026_09_17.py`)

**Fa**: (a) allarga il CHECK `safe_strategy_requests_kind_check` da
`('place','cashout','cancel')` a `('place','cashout','cancel','cashout_event',
'riprendi_evento')` — insieme vecchio ⊂ insieme nuovo, nessun rischio sulle righe
esistenti; (b) ridefinisce `safe_request(text,jsonb)` (firma invariata, nessun `DROP`
necessario) per accettare e validare i due `kind` nuovi; (c) dichiara esplicitamente,
con motivazione, di NON toccare `get_safe_aggregates` (i cap restano quelli "completi",
più prudenti, finché quella RPC non viene rifatta a parte).

**IL DIFETTO — regressione reale, non ipotetica.** `safe_request` è stata già
ridefinita da `migrations/safe_strategy_paper_live_2026-09-13.sql:731-833`, **applicata
e viva sul DB oggi** (confermato in sola lettura: `get_safe_aggregates(p_mode:'live')`
risponde). Quella versione aggiunge una barriera che qui sparisce silenziosamente:

- dichiara `v_req_mode text; v_ctrl_mode text;`, legge
  `select lower(btrim(c.mode)) into v_ctrl_mode from safe_strategy_control c where c.id=1`,
  imposta `v_req_mode` per ciascun `kind` (obbligatorio su `place`, opzionale su
  `cashout`/`cancel`), e **PRIMA dell'INSERT** rifiuta con
  `'modalità non corrispondente: la richiesta è in %, la sezione è in %...'` se
  `v_ctrl_mode IS NOT NULL AND v_req_mode IS NOT NULL AND v_req_mode <> v_ctrl_mode`.
- La versione di QUESTO file (righe 50-130) non dichiara mai `v_req_mode`/`v_ctrl_mode`,
  non legge `safe_strategy_control`, e non ha nessuna barriera equivalente: l'unico
  controllo di modalità rimasto è `coalesce(v_payload->>'mode','paper') NOT IN
  ('paper','live')` (riga 92-93), che valida solo che il **valore** sia uno dei due
  ammessi, non che **coincida** con la modalità attiva della sezione.

Applicando questo file oggi, `CREATE OR REPLACE` sostituisce l'intero corpo:
**la barriera del 13/09 sparisce dal DB**, senza che il file lo dichiari da nessuna
parte (il suo commento in testa parla solo dei due `kind` nuovi e del CHECK).

**Impatto reale, misurato sul codice Python** (non solo teorico):
- Per `kind='place'`: `Betfair/safe_strategy/bot_service.py:2047` (`_request_place`)
  controlla ANCORA `control_mode` a runtime e rifiuta se non combacia — quindi un
  piazzamento con modalità sbagliata viene comunque bloccato, solo **un ciclo dopo**
  invece che all'inserimento. Nessun rischio economico diretto, solo un peggioramento
  della UX (errore ritardato invece che immediato) rispetto a oggi.
- Per `kind='cashout'`/`'cancel'`: **non esiste alcun controllo equivalente in Python**
  — grep su `_request_cashout` (bot_service.py:2205) e `_request_cancel`
  (bot_service.py:2534) conferma che nessuno dei due legge/confronta `control_mode`
  (il parametro `control_mode` in `process_requests` viene passato SOLO al ramo
  `place`, bot_service.py:1953-1955). Con la barriera SQL rimossa, una richiesta di
  cash-out/cancel che dichiara nel payload una `mode` non coincidente con la sezione
  attiva non viene più intercettata da nessuno dei due strati. Operativamente il danno
  è limitato (`cashout`/`cancel` agiscono sul `trade_id` reale, che porta con sé la
  propria modalità: non si chiude/annulla il trade "sbagliato"), ma è comunque una
  protezione di coerenza (client con stato vecchio) che sparisce senza che nessuno lo
  sappia — esattamente il tipo di regressione silenziosa che questa revisione deve far
  emergere PRIMA di un'applicazione a mano.

**Correzione proposta (non applicata da me)**: in
`migrations/safe_cash_out_globale_e_cap_automatico_2026-09-16.sql`, dentro la
`CREATE OR REPLACE FUNCTION public.safe_request` (righe 50-130):
1. aggiungere alla `DECLARE` (dopo riga 60): `v_req_mode text; v_ctrl_mode text;`
2. dopo il controllo `p_kind NOT IN (...)` (riga 65-67) aggiungere la lettura:
   `SELECT lower(btrim(c.mode)) INTO v_ctrl_mode FROM public.safe_strategy_control c WHERE c.id = 1;`
3. nel ramo `place` (dopo la riga 94 `IF coalesce(v_payload->>'mode','paper') NOT IN
   ('paper','live') THEN ...`), impostare `v_req_mode := coalesce(nullif(lower(btrim(
   v_payload->>'mode')), ''), 'paper');` (invece del solo controllo di validità)
4. nei rami `cashout`/`cancel`, riportare le due righe di
   `safe_strategy_paper_live_2026-09-13.sql:775-778` e `:809-812` che impostano
   `v_req_mode := nullif(lower(btrim(v_payload->>'mode')), '');` con validazione
5. prima dell'`INSERT INTO public.safe_strategy_requests` (riga 125), reinserire la
   barriera di `safe_strategy_paper_live_2026-09-13.sql:817-824`:
   `IF v_ctrl_mode IS NOT NULL AND v_req_mode IS NOT NULL AND v_req_mode <> v_ctrl_mode THEN RAISE EXCEPTION ...`
6. lasciare `cashout_event`/`riprendi_evento` FUORI dalla barriera (il loro payload è
   dichiaratamente solo `event_id`, nessun campo `mode`: non c'è nulla da confrontare).

Fino a quando questa correzione non è fatta, **consiglio di applicare la migrazione lo
stesso** (il CHECK e i due `kind` nuovi servono ai due bottoni della Control Room), ma di
segnalarlo esplicitamente all'utente come debito aperto, non come sorpresa scoperta dopo.

**Nota non bloccante**: il file non tocca `get_safe_aggregates` e lo dichiara
esplicitamente (righe 134-162) — corretto, è una scelta consapevole, non un difetto.

**Verifica dopo l'applicazione**:
```sql
select conname, pg_get_constraintdef(oid) from pg_constraint
 where conrelid = 'public.safe_strategy_requests'::regclass
   and conname = 'safe_strategy_requests_kind_check';
 -- atteso: kind = ANY (ARRAY['place','cashout','cancel','cashout_event','riprendi_evento'])
select count(*) from pg_proc where proname = 'safe_request';   -- 1
-- verifica la REGRESSIONE (se non corretta): un client che chiama safe_request con un
-- payload place e mode diverso dalla sezione attiva NON deve più fallire subito — se
-- questo select ritorna un id invece di un errore, la barriera è sparita:
-- select public.safe_request('place', '{"event_id":"x","market_id":"x","market_type":"x",
--   "selection_id":1,"side":"back","price":2.0,"size":1,"mode":"live"}'::jsonb);
-- (NON lanciarla su produzione: scriverebbe una riga reale in coda richieste — è
-- indicata solo come verifica concettuale della firma, non da eseguire davvero.)
```

---

### 4. `omega_chiuso_dall_utente_2026-09-16.sql` — **OK**

**Fa**: `ALTER TABLE omega_events ADD COLUMN IF NOT EXISTS stato_utente JSONB` + indice
parziale; `omega_evento_riprendi(text)` nuova; `omega_eventi_chiusi_dall_utente()` nuova;
`omega_aggregates_sql(boolean)` NUOVA firma (overload per numero di argomenti, nessuna
ambiguità con l'`omega_aggregates_sql()` a zero argomenti); `omega_aggregates_sql()` a
zero argomenti ridefinita come wrapper (`SELECT public.omega_aggregates_sql(false)`) —
**verificato riga per riga che il corpo della versione booleana con `p_solo_auto=false`
sia byte-per-byte identico al corpo di `omega_models_v6.sql:68-171`** (stesso CTE `d`,
`raw`, `t`, `live`, stesso `jsonb_build_object` con le stesse 16 chiavi), tranne la
clausola `WHERE NOT p_solo_auto OR coalesce(p.origin, o.origin, 'auto') <> 'manual'`
aggiunta nella CTE `raw` — quindi `omega_aggregates_sql()` continua a rispondere
ESATTAMENTE come oggi; `get_omega_aggregates()` (firma invariata) ora aggiunge la sola
chiave `'auto'` in più — un `||` che AGGIUNGE, non toglie nulla.

**Verificato**:
- Prerequisiti dichiarati (`omega_manual.sql`, `omega_daily_v2.sql`, `omega_models_v6.sql`)
  tutti confermati applicati (sonda: `get_omega_aggregates()` risponde con le 16 chiavi
  di `omega_models_v6.sql`, nessun blocco `auto` — coerente con "non ancora applicata").
- `omega_events` esiste (`omega_manual.sql:39`); `omega_activity` esiste
  (`omega_bot.sql:73`, colonne `kind`/`payload` coincidenti con l'`INSERT` di
  `omega_evento_riprendi`).
- Lato Python: `Betfair/omega/omega_db.py:378-453` legge/scrive `omega_events.stato_utente`
  **direttamente via tabella** (non via RPC) con lo stesso nome colonna
  (`STATO_UTENTE_COL = "stato_utente"`), e già oggi (migrazione non applicata) fallisce in
  modo dichiarato (`_avvisa_una_volta`, un warning solo, mai un crash) — difensivo in
  entrambi gli stati. La chiave `chiuso_dall_utente` dentro il JSON, controllata da
  Python (`omega_db.py:441`: `st.get("chiuso_dall_utente")`) e dalla RPC (riga 118:
  `e.stato_utente ->> 'chiuso_dall_utente' IN ('true','t')`), coincide.
- `Betfair/omega/omega_db.py:691-733` legge `get_omega_aggregates()` e cerca la chiave
  `'auto'`: se assente (migrazione non applicata) ricade sul calcolo Python
  (`_esistono_manuali_che_contano` + scansione), esattamente come dichiarato nel
  commento della migrazione (righe 14-20).
- Chiamanti frontend: `frontend/src/lib/omega.ts:1263` (`omega_eventi_chiusi_dall_utente`,
  nessun argomento — coincide) e `:1286` (`omega_evento_riprendi`, argomento
  `p_event_id` — coincide col nome del parametro).

**Verifica dopo l'applicazione**:
```sql
select jsonb_pretty(public.get_omega_aggregates());   -- deve avere la chiave 'auto'
select column_name from information_schema.columns
 where table_name='omega_events' and column_name='stato_utente';  -- 1 riga
select count(*) from pg_proc where proname = 'omega_aggregates_sql';  -- 2 (0-arg + boolean)
select public.omega_eventi_chiusi_dall_utente();      -- '[]' se nessuno stato scritto
```

---

### 5. `omega_proposte_uscita_2026-09-16.sql` — **CORRETTA il 17/09** (era: OK, con 2 note — nota 2 risolta: `ALTER TABLE public.omega_requests ENABLE ROW LEVEL SECURITY;` aggiunta subito dopo la `CREATE TABLE`, falsificata rossa/verde da `Betfair/tests/test_contratto_safe_request_barriera_2026_09_17.py`)

**Fa**: `CREATE TABLE IF NOT EXISTS omega_requests` (nuova, nessun conflitto di nome),
CHECK su `status` (tabella nuova, nessuna riga preesistente da rispettare), indice unico
parziale `uq_omega_requests_proposta_viva` su `(payload->>'trade_id')` filtrato
`WHERE status='proposed'`; `omega_request_approve(bigint)`, `omega_request_ignore(bigint,
text DEFAULT NULL)`, `get_omega_proposte()` — tutte e tre nuove, nessun conflitto di
nome/firma con nessun'altra migrazione (grep su tutto `migrations/*.sql`: zero altre
occorrenze).

**Verificato**:
- `betfair_live_is_owner()` esiste ed è usata ovunque (funzione condivisa già in
  produzione).
- Chiamanti frontend: `frontend/src/lib/omegaProposte.ts:143` (`get_omega_proposte`,
  nessun argomento), `:172` (`omega_request_approve`, `p_id`), `:182`
  (`omega_request_ignore`, `p_id`+`p_reason`) — nomi coincidenti.
- `frontend/src/components/controlroom/SchedaChiusuraOmega.tsx` e
  `useControlRoom.ts:385-411` gestiscono l'errore PGRST202 in modo dichiarato
  ("migrazione ... non applicata") — non applicata oggi non rompe nulla, mostra solo un
  messaggio nella Control Room invece della scheda.
- **NOTA 1 — la funzionalità è "inerte" lato backend**: ho cercato in TUTTO
  `Betfair/omega/*.py` (incluso `omega_engine.py`, `omega_v3.py`,
  `omega_service.py`) e **nessun codice Python scrive righe in `omega_requests` né
  legge `status='pending'` da quella tabella**. Coerente con l'handoff (§8.3.6: "v3 in
  ombra... da costruire: raccordo v3 in omega_service.py"): la migrazione prepara
  un'infrastruttura che oggi non ha ancora un produttore né un consumatore lato
  servizio. Applicarla oggi è sicuro (nessun comportamento cambia finché
  `omega_service.py` non viene collegato) ma non ha ancora effetto pratico sulle uscite
  automatiche di Omega — solo il frontend, già pronto, smette di mostrare l'errore.
- **NOTA 2 — RLS non abilitata**: a differenza di TUTTE le tabelle sorelle
  (`safe_strategy_requests`, `safe_strategy_control`, `safe_strategy_trades`,
  `safe_strategy_activity`, `safe_strategy_opportunities`, tutte con
  `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` nei rispettivi file), `omega_requests` NON
  ha `ENABLE ROW LEVEL SECURITY`. Oggi non è sfruttabile (il file fa
  `REVOKE ALL ... FROM anon, authenticated` subito dopo, quindi quei ruoli non hanno
  nessun privilegio sulla tabella a prescindere dall'RLS, e `service_role` in Supabase
  bypassa comunque l'RLS), ma è una deviazione dal pattern di difesa-in-profondità usato
  ovunque altrove: se in futuro qualcuno aggiungesse un GRANT a `authenticated` su questa
  tabella (per errore o per una nuova funzionalità) senza accorgersi che manca l'RLS,
  quel ruolo vedrebbe TUTTE le righe. Correzione suggerita (non applicata):
  `ALTER TABLE public.omega_requests ENABLE ROW LEVEL SECURITY;` subito dopo la
  `CREATE TABLE` (riga 38).

**Verifica dopo l'applicazione**:
```sql
select public.get_omega_proposte();                    -- '[]' se non ci sono proposte
select relrowsecurity from pg_class where relname = 'omega_requests';  -- oggi: false (nota 2)
select indexname from pg_indexes where indexname = 'uq_omega_requests_proposta_viva';
```

---

### 6. `safe_strategy_stake_per_strategia_2026-09-16.sql` (facoltativa) — **OK**

**Fa**: un blocco `DO $$` (non DDL: scrive DATI) che legge
`safe_strategy_control.params.stake`, e se manca `per_strategia` la scrive derivando
`tennis`/`punta` da `backSize` e `base`/`esatto` da `laySize` — **solo le chiavi
mancanti**, mai sovrascrive un valore già presente. Nessuna colonna, RPC o CHECK toccati.

**Verificato**:
- Stato reale oggi: `stake = {"laySize": 2, "backSize": 3}` (confermato in sola
  lettura), **senza** `per_strategia` → la migrazione scriverebbe
  `per_strategia: {"tennis": 3, "punta": 3, "base": 2, "esatto": 2}`, esattamente
  l'esempio dichiarato nel file (righe 98-100).
- `Betfair/safe_strategy/engine.py:405-426` (`stake_di_strategia`) legge
  `stake.per_strategia[variant]` PRIMA, e solo se assente ricade su
  `laySize`/`backSize` — stessa logica di fallback dichiarata dal commento della
  migrazione (righe 15-19).
- Nomi delle quattro varianti (`base`, `esatto`, `punta`, `tennis`) confermati identici a
  `VARIANT_META` (`engine.py:273-286`) e a `_stake_per_strategia` (righe 387-401), che
  scarta silenziosamente qualunque chiave non fra queste quattro — coerente, nessun
  rischio di chiave "orfana".
- Idempotenza: il blocco confronta `v_per` con `coalesce(v_stake->'per_strategia',
  '{}'::jsonb)` e se sono uguali esce senza scrivere (`RAISE NOTICE` + `RETURN`) — una
  seconda esecuzione è un no-op reale, non solo "non fa danni".

**Verifica dopo l'applicazione**:
```sql
select params -> 'stake' from public.safe_strategy_control where id = 1;
-- atteso: {"laySize": 2, "backSize": 3,
--          "per_strategia": {"base": 2, "esatto": 2, "punta": 3, "tennis": 3}}
```

---

## Avvertenze

- **La migrazione 3 ha una regressione reale e va corretta o segnalata esplicitamente
  prima di applicarla** (vedi sopra): toglie dal DB una barriera di sicurezza
  paper/live già viva da `safe_strategy_paper_live_2026-09-13.sql`. Non è un problema
  di ORDINE fra le sei migrazioni odierne (si presenta comunque, in qualunque posizione
  la si metta) — è un difetto nel contenuto del file. Il piazzamento (`place`) resta
  comunque protetto un ciclo dopo da `bot_service.py:2047`; `cashout`/`cancel` restano
  SENZA alcun controllo di coerenza di modalità (impatto economico diretto limitato,
  perché entrambi operano sul `trade_id` reale, ma la protezione di coerenza sparisce
  senza che il file lo dichiari).
- **Migrazione 5**: applicarla oggi è sicuro ma non attiva ancora nessuna proposta di
  uscita automatica di Omega — manca il collegamento in `omega_service.py` (lavoro
  dichiarato "da costruire" nell'handoff). Non aspettarsi che Omega inizi a proporre
  chiusure subito dopo l'applicazione.
- **Nessuna delle sei chiama `NOTIFY pgrst, 'reload schema'`** — come nessuna delle sei
  migrazioni precedenti (11-13/09) già applicate con successo: il progetto Supabase ha
  il trigger di evento DDL che avvisa PostgREST da solo. Non l'ho potuto verificare
  direttamente (richiederebbe accesso agli event trigger, non esposto via REST), ma è
  coerente con il fatto che le sei migrazioni di prima si sono attivate senza quel
  passo esplicito.
- **Colonne/RPC non applicate non rompono nulla oggi**: le migrazioni 1, 2, 4 e 5 sono
  scritte con fallback difensivi già presenti nel codice Python E nel frontend (verificato
  con grep punto per punto sopra) — l'assenza della migrazione degrada, non rompe. La 3
  invece, se non applicata, blocca con un errore chiaro (`kind non valido`) i due
  bottoni nuovi della Control Room («Cash out globale», «Riprendi»): comportamento
  atteso e già coperto da un test frontend
  (`CashOutPartita.test.tsx:121-129`, che si aspetta proprio quel messaggio).
- Nessuna delle sei tocca dati esistenti in modo distruttivo: zero `DELETE`, `TRUNCATE`,
  `DROP TABLE`, `DROP COLUMN` in tutte e sei.

## Esito revisione statica per file

| File | Esito | Nota |
|---|---|---|
| `omega_activate_conserva_params_2026-09-16.sql` | **OK** | Firma identica a `omega_bot.sql`/`omega_daily_v2.sql`; contract test già in repo lo verifica. |
| `trades_consapevolezza_ordine_2026-09-16.sql` | **OK** | Solo `ADD COLUMN IF NOT EXISTS`; codice già difensivo su entrambi i lati (con/senza migrazione). |
| `safe_cash_out_globale_e_cap_automatico_2026-09-16.sql` | **DA CORREGGERE** | `safe_request` perde la barriera paper/live introdotta da `safe_strategy_paper_live_2026-09-13.sql` (già viva sul DB). Correzione proposta sopra, riga per riga. |
| `omega_chiuso_dall_utente_2026-09-16.sql` | **OK** | `omega_aggregates_sql()` a zero argomenti resta byte-identica nel calcolo; `get_omega_aggregates()` aggiunge SOLO la chiave `auto`. |
| `omega_proposte_uscita_2026-09-16.sql` | **OK con 2 note** | (1) nessun codice backend produce/consuma ancora `omega_requests` — sicura ma inerte; (2) manca `ENABLE ROW LEVEL SECURITY` sulla tabella nuova (le sorelle Safe ce l'hanno tutte). |
| `safe_strategy_stake_per_strategia_2026-09-16.sql` (facoltativa) | **OK** | DO block idempotente, verificato contro i valori REALI oggi sul DB (`laySize:2, backSize:3`) e contro il fallback di `engine.py`. |

## Parser SQL locale

Non ho cercato `pglast`/`sqlglot` nel `.venv`: la revisione è manuale, come in
`APPLY_ORDER_2026-09-11.md` (conteggio dollar-quote, confronto testuale delle firme,
riscontro colonne, riscontro con lo stato reale del DB via sonda sola-lettura). Il corpo
vivo di `omega_activate` e `safe_request` non è leggibile via PostgREST: la conferma
sulla migrazione 3 si basa sul comportamento osservabile (`get_safe_aggregates(p_mode)`
risponde → `safe_strategy_paper_live_2026-09-13.sql` è applicata → la sua versione di
`safe_request` con la barriera è quella oggi viva) e sul confronto testuale fra i due
file `.sql`, non su una lettura diretta del `pg_proc` vivo (non esposta via REST/RPC di
sola lettura senza una funzione dedicata che qui non esiste).

---

### 7. `storico_sport_2026-09-17.sql` — **OK con note** (revisione statica del 17/09, riscontro sonda indipendente)

**Fa**: (1) `DROP FUNCTION IF EXISTS public.get_omega_daily(date,date)` e
`public.get_omega_day_trades(date)` — le firme SENZA `p_mode` oggi vive — poi
`CREATE OR REPLACE` con `p_mode text DEFAULT NULL` in coda; (2) nuova
`get_storico_stake(p_bot,p_from,p_to,p_sport,p_mode)`, additiva, per l'importo
PIAZZATO di giornata (base del ROI, non esposto da `trading_daily_history`).
Nessun `DELETE`/`TRUNCATE`/`DROP TABLE`/`DROP COLUMN`.

**Verificato**:
- **Firme oggi vive confermate con una sonda indipendente** (stesso modello di
  `sonda_migrazioni.py`, sola lettura, sul DB reale del 17/09):
  `get_omega_daily(p_from,p_to)` → 200 (risponde); `get_omega_daily(p_from,p_to,p_mode)`
  → 404 PGRST202; `get_omega_day_trades(p_day)` → 200; `get_omega_day_trades(p_day,p_mode)`
  → 404 PGRST202; `get_storico_stake(...)` → 404 PGRST202 (non esiste ancora). Coincide
  con quanto dichiarato nell'intestazione del file e con l'ordine dei `DROP` (righe 80-81):
  firme esatte, nessun rischio di overload ambiguo 42725.
- **(a) Corpo di `get_omega_daily` vs l'ultima definizione viva** (catena confermata via
  `APPLY_ORDER_2026-09-11.md` §precondizione: `omega_daily_v2.sql` →
  `omega_models_v4.sql`, quest'ultima l'ULTIMA `CREATE OR REPLACE` di
  `get_omega_daily` prima di oggi; nessuna delle migrazioni successive — v5, v6,
  Mike, Safe — la ritocca) — **NON è byte-identico a parte il filtro `mode`**:
  `omega_models_v4.sql:109-151` aveva riscritto il merge dell'obiettivo storicizzato
  in modo SET-BASED (un solo `SELECT jsonb_agg(...) ... LEFT JOIN omega_daily_goal`,
  con lo scopo dichiarato nell'intestazione dello stesso file al punto 4: «niente loop
  plpgsql riga per riga»). `storico_sport_2026-09-17.sql:136-149` torna invece al
  vecchio LOOP `FOR v_row IN SELECT * FROM jsonb_array_elements(v_rows) LOOP ... END LOOP`
  di `omega_daily_v2.sql:497-509` (la versione PRIMA di `omega_models_v4.sql`), con
  `v_mode`/il filtro `format('t.mode = %L', v_mode)` e `jsonb_build_object('mode', v_mode)`
  aggiunti dentro il loop. Il file è stato evidentemente scritto ripartendo dalla base
  di `omega_daily_v2.sql` e non da `omega_models_v4.sql` (l'ultima davvero viva).
  **Nessun difetto di correttezza**: l'ordine delle righe è preservato (i `jsonb`
  mantengono l'ordine di inserimento di `trading_daily_history`, il loop le scorre
  nello stesso ordine), le chiavi in uscita (`goal`, `goal_pct`, `goal_snapshot`) sono
  calcolate con la stessa logica — ma è una **regressione di prestazioni silenziosa e
  non dichiarata**: annulla il lavoro di `omega_models_v4.sql` punto 4 senza dirlo da
  nessuna parte nel commento del file (che parla solo del filtro `mode`). Su
  ~100 righe/giorno il costo è trascurabile oggi, ma è esattamente il tipo di deriva
  che fa perdere un ottimizzazione già fatta al prossimo `CREATE OR REPLACE`.
  **Correzione proposta (non applicata)**: in `storico_sport_2026-09-17.sql`, sostituire
  il blocco `FOR v_row IN ... END LOOP` (righe 136-149) con la versione set-based di
  `omega_models_v4.sql:135-146` (`SELECT coalesce(jsonb_agg(CASE WHEN g.goal IS NOT NULL
  THEN r.elem || jsonb_build_object(...) ELSE r.elem || jsonb_build_object('goal_snapshot',
  false) END ORDER BY r.ord), '[]'::jsonb) INTO v_out FROM jsonb_array_elements(v_rows)
  WITH ORDINALITY AS r(elem, ord) LEFT JOIN public.omega_daily_goal g ON g.day =
  (r.elem->>'day')::date`), aggiungendo `|| jsonb_build_object('mode', v_mode)` a
  ENTRAMBI i rami del `CASE` (non nel `ELSE` soltanto) per portare a casa anche il
  campo `mode` riga per riga.
- **`get_omega_day_trades` (righe 161-185) è invece byte-identico** a
  `omega_daily_v2.sql:516-526` (l'unica `CREATE OR REPLACE` esistente per questa
  funzione, mai ritoccata da `omega_models_v4/v5/v6`), con il solo filtro
  `format('o.mode = %L', v_mode)` aggiunto e propagato a `trading_day_trades`. **Alias
  corretto**: `o`, non `t` — coerente con `trading_day_trades` (che usa `FROM
  public.%I o`, sia nella versione di `daily_history.sql` sia in quella oggi viva di
  `mike_history_v2.sql:270-323`) e con il commento del file stesso (righe 180-181) che
  cita esplicitamente il bug alias `t`/`o` del 14/09 (`mike_storico_per_modalita_fix_alias`).
  Nessuna riga aggiuntiva `mode` nel loop qui: non serve, `trading_day_trades` fa
  `to_jsonb(o.*)` e la colonna `mode` di `omega_trades` viaggia già da sola.
- **(b) `DROP FUNCTION IF EXISTS`**: firme esatte (`date,date` e `date`), confermate
  dalla sonda come le uniche oggi vive → nessun overload ambiguo 42725 dopo
  l'applicazione.
- **(b) Frontend — grep in `frontend/src`**: la pagina NUOVA (`/storico/*`,
  `lib/storicoSport.ts:175,460`) chiama `fetchOmegaDailyPerModo`/
  `fetchOmegaDayTradesPerModo` (`lib/dailyHistory.ts:283-306`), che passano SEMPRE
  `p_mode` e hanno un ripiego dichiarato (`modoAttendibile: false`) se la RPC risponde
  con la firma vecchia — pronta per dopo la migrazione. **Ma `pages/Omega.tsx:789-790`
  (tab «Storico» di Omega) usa ancora `fetchOmegaDaily`/`fetchOmegaDayTrades`
  (`lib/dailyHistory.ts:216-220,247-251`), la firma A DUE/UN ARGOMENTO senza `p_mode`.**
  Verificato con la sonda indipendente (punto sopra) che dopo l'applicazione questa
  chiamata **non fallisce** (grazie al `DEFAULT NULL` sulla nuova firma) e **non
  restituisce dati mescolati**: per disegno (uguale a Mike/Safe) restituisce SOLO la
  modalità CORRENTE di `omega_control.mode`, mai la somma di paper+live. Non è quindi
  né «un errore chiaro» né «dati mescolati»: è un **filtro silenzioso** — la tab
  «Storico» di `Omega.tsx` oggi mostra tutte le righe (bug che questa migrazione
  chiude), dopo mostrerà solo quelle della modalità attiva ORA, senza dirlo a schermo
  (nessuna etichetta `mode` renderizzata in quella tab) e senza che un cambio di
  modalità nel passato smetta di sparire silenziosamente dalla vista. Non è un difetto
  di QUESTO file (il comportamento è quello dichiarato e voluto, coerente con
  Mike/Safe), ma un residuo da segnalare: `Omega.tsx` andrebbe migrato a
  `fetchOmegaDailyPerModo`/`fetchOmegaDayTradesPerModo` quando si tocca quel file.
- **(c) `get_storico_stake` — whitelist e SQL dinamico**: `v_table` è scelto da un
  `CASE v_bot WHEN 'omega' THEN 'omega_trades' WHEN 'safe' THEN 'safe_strategy_trades'
  WHEN 'mike' THEN 'mike_trades' ELSE NULL END` (mai testo utente diretto), passato con
  `format(%I, v_table)`; `v_where` costruito SOLO con `format(' AND t.mode = %L', v_mode)`
  / `format(' AND t.sport = %L', v_sport)` dopo aver validato `v_mode IN ('paper','live')`
  e `v_sport IN ('calcio','tennis')` — nessuna concatenazione di testo utente, nessuna
  iniezione possibile. **Whitelist tabelle coerente** con quella di
  `trading_daily_history` (oggi vivo da `mike_history_v2.sql:70`: `omega_trades`,
  `safe_strategy_trades`, `mike_trades`).
- **(c) `is_placed` — confrontato riga per riga con il motore condiviso**: il predicato
  di `storico_sport_2026-09-17.sql:277-279` (`t.bet_id IS NOT NULL OR
  (t.meta->>'flumine_client_ref') IS NOT NULL OR t.meta->>'reason' =
  'place_exception_reconciling'`) è **testualmente identico** a quello di
  `mike_history_v2.sql:104-106` (il motore `trading_daily_history` oggi vivo, che
  include il caso «pending in riconciliazione» aggiunto l'11/09) — non a quello più
  vecchio e più povero di `omega_daily_v2.sql`/`daily_history.sql` (che non
  conoscevano ancora `place_exception_reconciling`). Confrontato anche contro il
  filtro `omega_trades` reale: la tabella NON ha colonna `sport` (verificato nel
  `CREATE TABLE` di `omega_bot.sql:38-64`, nessuna `ALTER ADD COLUMN sport`
  successiva) — il file lo gestisce correttamente (righe 242-251: chiedere uno sport
  diverso da 'calcio' a Omega ritorna `[]` invece di un 42703, e altrimenti azzera il
  filtro perché per Omega è sempre 'calcio').
- **(c) clamp 400 giorni — nota non bloccante**: `get_storico_stake` (righe 258-262)
  restringe silenziosamente `v_from := v_to - 400` se l'intervallo supera 400 giorni,
  MA — a differenza di `trading_daily_history` (oggi vivo da `mike_history_v2.sql`,
  che aggiunge `window_clamped`/`window_from`/`window_note` su ogni riga quando
  applica il clamp) — non lo dichiara in nessun campo della risposta. Non e' un errore
  (rispetta comunque M-17: si restringe, non si solleva un'eccezione), ma è
  un'incoerenza con il pattern di trasparenza usato dalle funzioni sorelle. Correzione
  suggerita (non applicata): aggiungere `'window_clamped'` all'oggetto di ritorno
  quando `v_from` è stato spostato.
- **(d) dollar-quoting bilanciato**: 6× `$$` (3 corpi di funzione), 4× `$e$` (2 coppie,
  righe 126-127), 2× `$q$` (1 coppia, righe 271/300) — tutti bilanciati, nessun `$$`
  accidentale dentro le stringhe/regex del file.
- **(d) alias**: `t` in `get_omega_daily` (righe 128, commento 121-123) coerente con
  `trading_daily_history` oggi vivo; `o` in `get_omega_day_trades` (riga 182, commento
  180-181) coerente con `trading_day_trades`; `t` nel corpo self-contained di
  `get_storico_stake` (righe 265-300) usato in modo consistente, nessuna funzione
  condivisa richiamata con un alias sbagliato.
- **(d) tipi di ritorno**: `RETURNS jsonb` su tutte e tre le funzioni, invariato per le
  due ridefinite; `SECURITY DEFINER SET search_path = public, pg_temp` e
  `REVOKE ALL ... FROM public, anon` / `GRANT EXECUTE ... TO authenticated, service_role`
  presenti e coerenti con le funzioni sorelle su tutte e tre.
- **(e) confronto con `mike_storico_per_modalita_2026-09-14.sql`** (il modello
  dichiarato dallo stesso file di oggi): stesso alfabeto — `p_mode DEFAULT NULL` →
  modalità CORRENTE del bot se non esplicita, validazione `IN ('paper','live')`,
  messaggio d'errore con il `p_mode` originale (non normalizzato), `mode` scritto su
  ogni riga in uscita. L'unica differenza di forma è come viene ricostruito il campo
  `goal`: Mike lo rimuove sempre e lo rimette a `NULL` (`v_row - 'goal' ||
  jsonb_build_object('goal', NULL, 'mode', v_mode)`, perché Mike non ha mai un
  obiettivo), Omega lo tocca solo quando trova uno snapshot storico (perché Omega un
  obiettivo CE L'HA, corrente o storicizzato) — differenza legittima, dettata dal
  dominio, non un'incoerenza.

**Verifica dopo l'applicazione**:
```sql
-- firme: nessun overload ambiguo
select count(*) from pg_proc where proname = 'get_omega_daily';       -- 1
select count(*) from pg_proc where proname = 'get_omega_day_trades';  -- 1
select count(*) from pg_proc where proname = 'get_storico_stake';     -- 1

-- paper e live non devono mai coincidere per caso (17/09: live deve essere 0)
select jsonb_array_length(public.get_omega_daily(NULL, NULL, 'paper')) AS giorni_paper,
       jsonb_array_length(public.get_omega_daily(NULL, NULL, 'live'))  AS giorni_live;

-- ogni riga dichiara la modalità
select public.get_omega_daily(current_date - 5, current_date, 'paper') -> 0 -> 'mode';

-- il chiamante vecchio (Omega.tsx) non deve fallire, ma restituisce SOLO la modalità
-- corrente: confrontare con omega_control.mode per verificare che non stia mescolando
select public.get_omega_daily(current_date - 5, current_date);   -- niente più p_mode: OK, non errore
select mode from public.omega_control where id = 1;               -- deve combaciare col filtro implicito

select public.get_storico_stake('safe', current_date - 30, current_date, 'tennis', 'live');
select public.get_storico_stake('safe', current_date - 30, current_date, 'tennis', 'paper');
-- le due somme non devono mai coincidere con la somma SENZA p_mode
```

**Cosa non ho potuto verificare in sola lettura**: il corpo vivo esatto di
`trading_daily_history`/`trading_day_trades` non è leggibile via PostgREST (stesso
limite di `APPLY_ORDER_2026-09-11.md`) — mi sono affidato al confronto testuale con
`mike_history_v2.sql` (l'ultima `CREATE OR REPLACE` in ordine di applicazione secondo
`APPLY_ORDER_2026-09-11.md`, mai ridefinita dopo) e al comportamento osservato con la
sonda. Non ho potuto contare le righe reali `omega_trades.mode='live'` (0 attese, come
dichiarato dal file) perché non è stata fatta una query diretta sulla tabella in questa
revisione — solo sulle RPC. Non ho verificato `omega_trades.phase`/`origin`/
`closes_trade_id`/`liability` da zero: mi affido alla verifica già fatta e pushata in
`APPLY_ORDER_2026-09-11.md` (mai contraddetta da migrazioni successive).

| File | Esito | Nota |
|---|---|---|
| `storico_sport_2026-09-17.sql` | **OK con note** | `get_omega_day_trades` e `get_storico_stake` corretti; `get_omega_daily` funzionalmente corretto ma ha reintrodotto senza dichiararlo il loop plpgsql riga-per-riga che `omega_models_v4.sql` aveva eliminato (correzione proposta sopra); `get_storico_stake` clampa la finestra a 400gg senza dichiararlo in uscita (nota non bloccante); `pages/Omega.tsx` resta sulla firma vecchia (non rompe, ma perde silenziosamente la vista sulle altre modalità). |
