# ⟶ COSTITUZIONE DEL BOT «OMEGA» ⟵
### Fonte unica di verità. Ogni riga di codice di Omega deve essere conforme a questo documento.
### v1.0 — 2026-07-12 · Betfair Exchange (.it) · Correct Score LAY · Set-and-forget

---

## 0. Cos'è Omega (in una frase)

Omega è un bot **set-and-forget** che ogni giorno conta le partite di calcio in
programma su Betfair, divide un **obiettivo giornaliero** (default €250) per il
numero di partite per ricavare il **profit-target per singola partita**, e su
**ogni** partita — quando entra nella sua **fascia oraria/minuto** — piazza **un
solo LAY** sul mercato **CORRECT SCORE**, scegliendo il risultato esatto **meno
probabile** con **quota entro un range configurabile** (non 600).

> Omega non fa scalping né trading continuo. Piazza **un ordine per match** e
> attende il **settlement del mercato Betfair** (verità ultima). Nessun'altra
> azione richiesta all'utente dopo lo START.

---

## 1. Principi non negoziabili (INVARIANTI)

1. **I1 — Un solo trade per match.** Per ogni `event_id` Omega piazza **al più un
   LAY** nella vita del bot. Idempotenza a più livelli, con pattern
   **RESERVE-FIRST**: (a) prima di piazzare si INSERISCE una riga `pending` in
   `omega_trades` — l'**unique index su `event_id`** fa da lock, anche
   cross-processo e **oltre** i 60s di de-dup Betfair; (b) solo dopo la riserva si
   esegue l'ordine (PAPER/LIVE) e si aggiorna la riga a `open` (fill) o `error`
   (nessun ordine reale attivo); (c) `customerRef` deterministico `omega-<event_id>`;
   (d) single-instance lock di processo (socket 127.0.0.1:47313). Così un ordine
   LIVE **non può mai raddoppiarsi né restare orfano**.
2. **I2 — PAPER prima, LIVE dopo.** Il default è **PAPER** (soldi finti su prezzi
   live reali). Esistono **due gate indipendenti**, entrambi espliciti e con
   conferma UI: (a) l'AUTOMATICO piazza ordini reali solo se `omega_control.mode
   = 'live'` (toggle globale); (b) il MANUALE solo se la singola richiesta ha
   `mode='live'` (scelta per-ordine con dialog "SOLDI VERI"). Nessun percorso
   arriva al LIVE per default o per fallback.
3. **I3 — Betfair è la verità.** Il P&L di un trade è determinato dal
   **settlement del mercato** (runner `WINNER`/`LOSER`), non da stime interne. Il
   settlement scatta SOLO quando ogni runner ha uno stato terminale
   (`WINNER/LOSER/REMOVED`): un `CLOSED` non ancora finalizzato viene ritentato,
   mai regolato a `void` per errore. Dopo un ordine LIVE la conferma DB è
   **robusta** (retry) e, se fallisce, si logga CRITICAL con il `bet_id`. Mai
   dedurre un incasso da un ordine non ancora regolato.
   ✅ **RICONCILIAZIONE (LIVE-ready)**: a ogni ciclo `reconcile_pending` riallinea i
   `pending` orfani con la realtà — PAPER: conferma; LIVE: interroga Betfair
   (`listCurrentOrders`/`listClearedOrders`, `customerStrategyRef='omega'`) e apre
   col fill reale / attende (non ancora matchato) / libera (mai piazzato, recente)
   / marca error (vecchio, per non rischiare un doppio). Un ordine reale non può
   mai restare non tracciato: Omega è pronto sia in PAPER sia in LIVE.
4. **I4 — Nessun ricalcolo retroattivo del passato.** Il target per-match si
   ricalcola **solo in avanti** sui match ancora da piazzare; i trade già
   piazzati non si toccano.
5. **I5 — Owner-only.** Ogni RPC verso il DB passa da `betfair_live_is_owner()`.
   Le tabelle `omega_*` sono in RLS, `REVOKE ALL` da `anon/authenticated`.
6. **I6 — Fallimento sicuro.** Qualsiasi errore su un match (mercato assente,
   book vuoto, liquidità insufficiente, API down) **salta quel match** e prosegue;
   non blocca il bot né duplica ordini. Ogni salto è loggato in `omega_activity`.
7. **I7 — Idempotenza di stato.** Il servizio è un loop stateless-ricostruibile:
   riavviato, ricostruisce lo stato da `omega_control` + `omega_trades` senza
   ripiazzare nulla (I1).
8. **I8 — Trasparenza del rischio.** La dashboard mostra sempre la **liability
   aperta totale** e l'esposizione a coda. Omega non nasconde mai il rischio del
   «raccogliere spiccioli davanti al treno» (vedi §9).

---

## 2. La matematica (esatta)

Sia:
- `G` = obiettivo giornaliero (default **250 €**),
- `R` = profit **realizzato** finora oggi (somma P&L dei trade **settled**),
- `M` = numero di match **ancora eleggibili e non piazzati** (incluso quello corrente),
- `c` = commissione Betfair (default **0.05**),
- `O` = quota lay scelta per il match,
- `P` = profit-target per il match corrente.

**Target dinamico per match:**
```
P = (G − R) / max(M, 1)
```
Se `stop_on_goal = true` (default) e `R ≥ G` → Omega **non piazza più** (obiettivo
raggiunto). `P` è vincolato a `P ≥ 0`.

**Giornata operativa (definizione di "oggi")**: il giorno solare **Europe/Rome**
(`omega_engine.day_start_utc`). `R` = P&L dei trade **regolati oggi**
(`settled_at ≥ mezzanotte locale`); i contatori "per giorno" (`max_events`,
`daily_loss_cap`, `stop_on_goal`) usano i trade **piazzati/regolati oggi**. A
mezzanotte il conteggio riparte da solo — senza questo scoping i contatori
sarebbero cumulativi a vita e, dal 2° giorno in profitto, `stop_on_goal`
bloccherebbe il bot per sempre. La **liability aperta** resta invece SEMPRE
totale: il rischio vivo non ha giorno. Il cumulato storico resta visibile in
dashboard accanto al P&L di oggi.

**Sizing del LAY** (backer stake `s` = ciò che incassi se il risultato NON esce):
```
s          = P / (1 − c)          # incasso netto commissione = P
liability   = s · (O − 1)          # ciò che perdi se il risultato ESCE
profit_win  = s · (1 − c)  = P     # per costruzione
profit_lose = − liability
```
Vincoli:
- `s ≥ min_stake` (LAY .it minimo **€0.50**). Se `s < min_stake` → `s = min_stake`
  (il profit supererà leggermente `P`).
- `s` arrotondato a `stake_rounding` (default 0.01); `O` arrotondata al **tick**
  valido Betfair (`round_to_tick`).
- Se `max_liability_per_match > 0` e `liability > cap` → si riduce `s` finché
  `liability ≤ cap` (il profit resterà **sotto** `P`; loggato). Default **off**.

---

## 3. Selezione del risultato esatto (score selection)

Per il mercato `CORRECT_SCORE` del match, tra i runner con `availableToLay`:

1. **Filtra per quota**: tieni solo i runner con miglior quota lay `O` tale che
   `price_min ≤ O ≤ price_max` (default **[20, 120]**).
2. **Filtra liquidità**: `availableToLay.size ≥ min_lay_liquidity` (default **5 €**).
3. **Filtra tipologia**: solo scoreline numeriche `H - A` se `include_aggregate =
   false` (default). Gli aggregati «Any Other …» sono esclusi di default.
4. **Scegli il meno probabile**: tra i superstiti, prendi quello con **quota lay
   più ALTA** (probabilità minima). Tie-break: liquidità maggiore, poi liability
   minore.
5. Se nessun runner supera i filtri → **salta il match** (I6), logga `skip`.

> Nota: il mercato Correct Score si ri-prezza da solo con il punteggio live e
> **sospende i punteggi diventati impossibili** (es. a 2-0 il runner "1-0" sparisce):
> la regola «quota più alta nel range» si adatta automaticamente senza che Omega
> debba conoscere il punteggio. Il feed punteggio (§5) serve solo al **gating del
> minuto** e alla telemetria, non alla selezione.

---

## 4. Finestra di ingresso (timing)

Omega piazza su un match **solo** quando è nella sua fascia in corso, così da non
immobilizzare liquidità su partite che partono tra ore.

Un match è **eleggibile** quando **tutte** valgono:
- il suo mercato `CORRECT_SCORE` è **OPEN** e **in-play** (`inplay = true`);
- il **minuto** ∈ `[entry_minute_min, entry_minute_max]` (default **[30, 60]**),
  dove il minuto viene da:
  - `entry_window_source = 'score'` (default): minuto del feed punteggio (§5);
  - `entry_window_source = 'clock'`: minuti trascorsi da `marketStartTime`
    (fallback quando il feed non è disponibile);
- non è già stato piazzato (I1);
- `marketStartTime` cade **oggi** (universo giornaliero);
- se `max_events > 0`: numero di match già piazzati `< max_events`.

L'universo giornaliero si ottiene con `list_events(["1"], from=now−12h, to=fine
giornata)` per includere anche i match **già iniziati** (il loro `marketStartTime`
è nel passato).

---

## 5. Minuto+punteggio live — CONDIVISI dal runner calcio (via `live_now`)

Omega **NON apre una seconda sessione Betfair** per il punteggio: legge minuto e
punteggio dalla tabella **condivisa `live_now`** (scritta dal runner calcio ogni
~5s tramite `ScorePoller`/`BetfairInPlayProvider`), ESATTAMENTE come lo scalper
(`scalper_session.py:451-514`). Pura lettura Supabase (`omega_db.read_live_now`),
join diretto per `event_id` Betfair (stesso spazio ID → nessun matching). Usato per:
- gating del minuto (§4) quando `entry_window_source='score'` (default);
- telemetria: `score_at_entry`, `minute_at_entry` salvati sul trade;
- (non usato per la selezione — vedi §3).

**Guardia freschezza** (che lo scalper NON ha): se `live_now.updated_at` è più
vecchio di `SCORE_MAX_AGE_S` (180s), il dato è considerato congelato → Omega
degrada al `clock`. **Copertura**: `live_now` contiene una riga solo per gli
eventi SEGUITI dal runner (`live_follow` ← `personal_watchlist`); per i match non
seguiti Omega usa il `clock` (`marketStartTime`), senza mai fermarsi (I6).

---

## 6. Ciclo di vita di un trade

```
(match entra in finestra) → SELECT score → SIZE → PLACE lay
   PAPER: fill simulato al best-lay live, size ≤ liquidità disponibile
   LIVE : client.place_orders(side=LAY, customerRef=omega-<event_id>)
→ status = 'open' (liability impegnata)
→ (fine match) settlement del mercato CORRECT_SCORE:
   runner nostro = WINNER → status='lost',  pnl = −liability
   runner nostro = LOSER  → status='won',   pnl = +s·(1−c)
   mercato VOID/abbandonato → status='void', pnl = 0
→ scrittura su omega_trades + omega_activity + aggiornamento stats/equity
```

- **PAPER fill model**: si assume il match al **best lay price** live per una size
  ≤ `availableToLay.size` a quel prezzo. Se la size target eccede la liquidità al
  best, si cammina la ladder (prezzi lay peggiori) o si riduce la size (loggato
  `size_reduced` in `omega_activity`, con `requested_size` pre-taglio nel meta).
  Modello onesto per la validazione; il LIVE userà i fill reali riconciliati.
- **LIVE = `FILL_OR_KILL`**: l'istruzione reale usa `timeInForce: FILL_OR_KILL`
  (immediato-o-annullato). La parte non matchata subito viene **cancellata da
  Betfair**: mai un residuo vivo sul book che, matchando più tardi, sfuggirebbe
  alla contabilità (la riga sarebbe già `open` con size congelata).
- **customerOrderRef**: AUTO = `omega-<event_id>` (unico per I1); MANUALE =
  `omega-m<trade_id>` (**per-gamba**, derivabile dalla riga): due ordini manuali
  sullo stesso evento non condividono mai il ref → la riconciliazione non può
  confondere due ordini reali distinti.
- **Settlement PAPER**: si polla il market book della CS finché `status='CLOSED'`,
  poi si leggono gli stati runner (`WINNER`/`LOSER`). Autorevole quanto il LIVE.

### 6-bis. Esecuzione via flumine — DEMO = LIVE (v1 PAPER 2026-07-16, v2 LIVE 2026-07-17)

Quando possibile, il fill PAPER non è più istantaneo su snapshot ma passa dal
**runner calcio** (flumine `paper_trade=True`: SimulatedExecution su stream
reale — coda al prezzo, liquidità consumata, betDelay), riusando la coda
ESISTENTE `betfair_live_order_requests` (contratto di `live_order_worker`, che
NON viene toccato: omega è un normale client della coda, come il frontend).

- **Gate** `_flumine_gate(event_id, mode)` (unificato paper/live; il wrapper
  storico `_flumine_paper_gate` resta solo-paper) — True SOLO se **tutte**:
  `execution_mode='auto'`; evento in `live_follow` con status `STREAMING`;
  runner vivo (heartbeat `betfair_live_heartbeat.ts` fresco ≤90s) e in order
  mode **uguale al mode del trade** (`PAPER` per i trade paper, `LIVE` per i
  live — mai cross-mode); per il LIVE anche kill-switch
  `omega_live_via_flumine` acceso e contratto di revoca presente.
  FAIL-CLOSED: qualunque dubbio → percorso legacy.
- **Flusso**: riserva `pending` (reserve-first INVARIATO, I1) → enqueue `place`
  (`client_ref='omega-t<trade_id>'`, idempotente sulla coda) → la riserva resta
  `pending` con `meta.flumine_request_id` → il poll di ciclo
  (`poll_flumine_paper`, ~20s) legge la riga di coda e lo specchio
  `betfair_live_orders` (`client_order_ref='awlq<request_id>'`) e conferma con
  **size/prezzo medio REALI simulati** (`_confirm_open_trade`, robusta).
- **TTL quasi-FOK** (`paper_fill_ttl_s`, default 45s) — **deviazione consapevole**
  dal `FILL_OR_KILL` nativo del LIVE: la coda non offre un FoK atomico
  end-to-end in paper, quindi l'ordine simulato lavora il book fino al TTL;
  scaduto, si accoda il `cancel` del residuo e si confermano SOLO i € realmente
  matchati (qualunque `matched>0` è contabilizzato — **mai posizioni nude**;
  sotto `min_stake` la riga porta la nota `below_min_stake`); nessun fill →
  riserva liberata a `error` (`flumine_no_fill`, stessa semantica di
  `paper_no_fill`). La finestra di esposizione non contabilizzata è quindi al
  più TTL+grace, e sempre su soldi finti.
- **FALLBACK SEMPRE DISPONIBILE**: gate KO in qualunque punto (runner giù,
  evento non seguito, mode mismatch, enqueue/coda in errore, specchio muto oltre
  TTL+grace) → percorso legacy INVARIATO (`E.paper_fill` automatico /
  `paper_at_price` manuale, o conferma coi dati della riserva se l'ordine era
  già accodato) con log esplicito `paper_fill_fallback`. Il sistema non resta
  MAI bloccato per l'assenza del runner. `execution_mode='rest'` forza il
  legacy senza log di fallback (scelta esplicita, non un degrado).
- **LIVE via coda (v2, 2026-07-17)** — anche il place LIVE passa dalla coda del
  runner quando il gate live passa, per avere **book streamato** e **fill
  confermati dall'order stream in tempo reale**, PRESERVANDO la semantica FOK:
  - **FOK VERO**: la richiesta accodata porta `time_in_force='FILL_OR_KILL'`
    (colonna già prevista dalla coda, passata da `live_order_worker` a
    `build_order` → Betfair). È **Betfair** a uccidere il residuo non matchato:
    NIENTE TTL software che lavora il book coi soldi veri (il TTL quasi-FOK
    resta SOLO paper). Persistence irrilevante col FOK.
  - **INVARIANTE SUPREMO**: il `mode` della richiesta accodata deriva SOLO dal
    mode del trade (doppia guardia: gate + whitelist in `_flumine_enqueue_place`,
    protetta da test) — un trade paper non produce MAI una richiesta `live`,
    né viceversa; lo specchio è letto SOLO con il mode del trade.
  - **Conferma**: dal MIRROR `betfair_live_orders` (order stream): stato
    terminale con `matched>0` → riserva a `open` col prezzo medio REALE
    (`meta.fill='flumine_live'`); terminale con `matched=0` (FOK ucciso) →
    trade fallito **esattamente come il FOK legacy** (`error`,
    `flumine_live_fok_*`); richiesta rifiutata dal worker prima del place →
    `error` (`flumine_live_request_error`), deciso **solo oltre la hard
    deadline** (allo specchio è dato tutto il tempo di smentire). Contratto
    col worker (17/07): un fallimento DOPO il dispatch dell'ordine porta il
    prefisso **`post_place:`** sul messaggio d'errore della riga coda — per
    quei casi la riserva NON viene mai liberata (l'ordine reale può esistere):
    si va nel ramo "esito ignoto" (alert CRITICAL + pending in verifica)
    finché lo specchio non porta la verità.
  - **Hard deadline** (`live_fill_deadline_s`, default 20s) — mai zombie:
    oltre, con `bet_id` noto si riconcilia via REST
    (`order_state_by_bet_id`: listCurrentOrders/listClearedOrders per betId —
    l'ordine del runner NON porta il ref `omega-*` né la strategy `omega`,
    il betId è l'unica chiave certa); richiesta rimasta `pending` (runner giù)
    → **REVOCA atomica** pending→error (speculare al claim: il runner tornato
    vivo non piazza un ordine stantio) e riserva a `error`; esito davvero
    ignoto → alert CRITICAL una volta e la riserva resta `pending` in verifica
    (conta come viva in aggregati/missione) — MAI esiti inventati sui soldi
    veri, MAI il fallback "conferma coi dati della riserva" (quello è solo
    paper).
  - **Kill-switch** `omega_live_via_flumine` (default **True**): a `False` il
    live torna al **legacy puro** (place REST FOK diretto + riconciliazione
    polling), senza log di fallback. Con gate KO (runner giù, evento non
    seguito, enqueue fallito e MAI creato) → stesso REST legacy + log
    `live_fok_fallback` (mai bloccati). Enqueue con **esito ignoto** (rete giù
    dopo l'insert idempotente) → NESSUN place REST (rischio doppio ordine
    reale): riserva pending col marker, recovery del poll per client_ref
    (adozione o `free`).
  - I pending LIVE con marker flumine sono ESCLUSI da `reconcile_pending` (il
    reconcile REST per ref li darebbe per mai piazzati) e contano negli
    aggregati/liability come i paper (F2: `meta.flumine_client_ref`).
  **Settlement INVARIATO**: REST resta autoritativo (§6), anche per i trade
  riempiti via flumine.
- **keepAlive proattivo** (§8): il loop di servizio chiama
  `omega_market.keep_alive()` ~ogni 600s — il retry reattivo con re-login di
  `call()` resta SOLO rete di sicurezza (il place LIVE non è idempotente oltre
  i 60s di de-dup Betfair: mai arrivare al place con la sessione scaduta).
- Limiti noti dichiarati: durante la finestra `pending` la liability riservata
  entra in `open_liability` SOLO col marker flumine o il `bet_id` (I8/F2); in
  paper il `cancel` richiede il `bet_id` simulato dallo specchio — se non
  arriva, il poll risolve comunque alla hard deadline (TTL+60s) col miglior
  dato disponibile.

---

## 7. Parametri configurabili dalla UI

Colonne dedicate su `omega_control`: `daily_goal`, `mode` (`paper|live`),
`status`, più `params JSONB` con **whitelist doppia** (frontend `OMEGA_PARAM_*`
in `lib/omega.ts` ↔ backend `omega_config.resolve_params`). Chiavi e default:

| chiave | default | significato |
|---|---:|---|
| `price_min` | 20 | quota lay minima |
| `price_max` | 120 | quota lay massima ("non 600") |
| `entry_minute_min` | 30 | minuto minimo d'ingresso |
| `entry_minute_max` | 60 | minuto massimo d'ingresso |
| `max_events` | 0 | tetto match/giorno (0 = illimitato) |
| `commission_pct` | 5.0 | commissione Betfair |
| `min_lay_liquidity` | 5 | size lay minima al best |
| `min_stake` | 0.50 | stake lay minimo .it |
| `include_aggregate` | false | includere runner "Any Other …" |
| `stop_on_goal` | true | stop nuovi ingressi a obiettivo raggiunto |
| `entry_window_source` | "score" | `score` (minuto+punteggio da `live_now` CONDIVISO col runner, guardia freschezza; fallback clock per match non seguiti) \| `clock` (minuto da `marketStartTime`) |
| `poll_interval_s` | 20 | cadenza del loop |
| `max_liability_per_match` | 0 | cap liability/match (0 = off) |
| `daily_loss_cap` | 0 | stop-loss giornaliero (0 = off) |
| `max_open_liability` | 0 | cap liability aperta totale (0 = off) |
| `execution_mode` | "auto" | esecuzione via coda flumine (§6-bis, paper E live): `auto` (coda se il gate passa, fallback legacy) \| `rest` (forza il percorso legacy: fill snapshot in paper, place REST FOK in live) |
| `paper_fill_ttl_s` | 45 | TTL quasi-FOK del place paper via flumine: senza fill entro il TTL → cancel del residuo, conferma dei soli € matchati. SOLO paper |
| `omega_live_via_flumine` | true | kill-switch del LIVE via coda flumine (§6-bis v2): `false` = live legacy puro (REST FOK diretto), senza log di fallback |
| `live_fill_deadline_s` | 20 | hard deadline dell'esito FOK live dallo specchio: oltre → riconciliazione REST per bet_id / revoca della richiesta mai presa in carico (mai zombie) |

> Scelta utente 11/07: **set-and-forget senza limiti** → i tre cap
> (`max_liability_per_match`, `daily_loss_cap`, `max_open_liability`) sono
> **presenti ma default OFF (=0)**; l'utente li accende quando vuole (punto 5 del
> goal). Quando `> 0` sono **realmente applicati** nel loop:
> `max_liability_per_match` riduce la size; `max_open_liability` blocca l'ingresso
> se la liability aperta lo supererebbe; `daily_loss_cap` ferma i **nuovi** ingressi
> quando il P&L realizzato scende sotto `−cap` (i trade aperti si regolano comunque).
> La commissione è **fissata sul trade al piazzamento**: cambiarla a caldo non
> altera il P&L dei trade già aperti.

---

## 8. Architettura & DB (DB-as-bus, come scalper/tennis)

```
UI React (/omega)  ──RPC owner-only──►  Supabase (omega_control, omega_trades, omega_activity)
      ▲  realtime/polling                         ▲  service_role
      └───────────────────────────────  omega_service.py (loop locale)
                                          ├─ omega_market.py  (Betfair REST: events/catalogue/book/place)
                                          ├─ omega_engine.py  (LOGICA PURA: selezione/sizing/target/
                                          │                    settlement/fill PAPER/riconciliazione) ← TESTATA
                                          └─ omega_db.py      (I/O Supabase)
```
- **Backend**: `Betfair/omega/` — supervisore singolo (una `omega_control`
  "singleton", non per-evento). Riusa `odds_refresh.get_shared_client()`
  (sessione Betfair condivisa), `db_client.get_supabase_client()`,
  `live_order_build.{lay_size_from_liability, min_stake_rules}`, `scores/`.
  Nota: il fill PAPER (`paper_fill`) vive in `omega_engine` (non esiste un
  modulo `omega_paper` separato).
- **Convivenza AUTO ↔ MANUALE sullo stesso evento**: il manuale può piazzare su
  un evento già toccato dall'automatico (unique per-gamba); il contrario NO —
  un evento toccato dal MANUALE è **escluso dall'automatico** (scelta di
  sicurezza: evita che bot e utente accumulino esposizione doppia sullo stesso
  match; coerente con gli aggregati origin-agnostici che contano il P&L manuale
  dentro `R`).
- **DB**: `migrations/omega_bot.sql` — `omega_control` (singleton) + `omega_trades`
  (mirror append/update) + `omega_activity` (log) + RPC `omega_activate` /
  `omega_stop` / `omega_update_params` / `get_omega_state` / `get_omega_trades`.
  `omega_control` e `omega_trades` in **realtime publication** per la dashboard.
- **Frontend**: `frontend/src/lib/omega.ts` (client RPC + tipi + whitelist),
  route `/omega` (App.tsx), card in `SelectSport`, pagina fullscreen
  `pages/Omega.tsx` (equity curve, barra obiettivo, lista trade live, popup incassi
  via `sonner`, pannello parametri, START/STOP + toggle PAPER/LIVE).

**Avvio locale**: `python -m Betfair.omega.omega_service`
(+ `.bat` dedicato e voce in `desktop/main.js`).

---

## 8-bis. MISSIONI — centro di controllo per partita (2026-07-15)

Il tab **MISSIONE** di `/omega` è la modalità SUPERVISIONATA: l'utente attiva una
missione su una partita con un target €, e il sistema **propone** — mai piazza da
solo. Ogni ordine parte da un click (coda `omega_manual_requests` con `phase`).

- **Fasi**: `pre → 1t → ht (intervallo) → 2t → finita`, rilevate dall'endpoint
  in-play pubblico Betfair (`ips.betfair.com/inplayservice`, GET **senza sessione**
  → coerente con §5: nessun secondo login; parser condiviso col runner). Fallback:
  minuto → kickoff (futuro=pre; +3h senza dati=finita) → fase precedente.
- **Gambe**: `ht_cs` = lay Correct Score **PRIMO TEMPO** (`HALF_TIME_SCORE`),
  proposta in pre/1T; `ft_cs` = lay Correct Score generale, proposta
  ALL'INTERVALLO; `scalp` = back `Under X.5` con linea = gol+2.5 (fallback linea
  sopra), runner scelto **PER NOME** (mai per posizione). Stake default: €1 fisso
  per le gambe CS, importo esplicito per lo scalp.
- **Verità degli id (money-critical)**: ogni suggerimento porta market_id +
  selection_id + runner_name **dallo stesso catalogo** (mai rimappati); la UI
  piazza ESATTAMENTE quegli id e mostra il nome nel dialog di conferma.
- **Guardia**: un evento con missione attiva è territorio dell'utente — il loop
  automatico lo salta SEMPRE; se la lettura delle missioni fallisce, l'automatico
  NON piazza nulla in quel ciclo (fail-safe, mai esposizione doppia).
- **Gamba pre-match**: bottone scalper (`scalper_activate`, `dry_run=true` in v1)
  previa `omega_mission_follow` (inserisce in `live_follow` solo se assente);
  P&L letto da `scalper_control.stats.pnl_locked`.
- Il P&L per gamba NON è duplicato: si calcola da `omega_trades.phase` +
  scalper stats nella RPC `get_omega_missions`. Auto-chiusura a partita finita
  con tutte le gambe regolate. DB: `migrations/omega_missions.sql`.
- **CONSULENTE DATI** (`omega_advisor.py`, 2026-07-15): le suggestion CS portano
  un blocco `advisor` PURAMENTE INFORMATIVO — `{poisson_prob, freq_league, h2h,
  matched_fixture_id, sources}` — dai NOSTRI dati (Poisson interno da
  `fixture_predictions.db_json_analisi`, frequenza lega via RPC
  `get_market_frequency`, H2H da `hazard_atlas_v2.h2h_hint`). Matching evento→
  fixture col matcher money-critical `betfair_match.py`; se non affidabile →
  `advisor: null` DICHIARATO, mai un match forzato. Best-effort con cache per
  evento (budget ~1s); qualunque errore → null, la proposta esce comunque.
  MONEY-CRITICAL: l'advisor non deriva MAI market_id/selection_id/prezzi;
  la UI lo mostra in piccolo sotto la proposta, bottoni e payload INTOCCATI.

---

## 9. Onestà sul rischio (da mostrare, non nascondere — I8)

La strategia LAY su risultato esatto **poco probabile** è, a quote **fair**,
**EV ≈ 0** (leggermente negativo per commissione + overround): non esiste edge
meccanico (coerente con le ricerche precedenti del progetto). Profilo:
- vinci `≈ P` con probabilità alta (~98–99% per match);
- perdi `≈ liability` (grande, es. €300–500/match a quota 100) con probabilità
  bassa (~1–2%).

**Conseguenza**: la maggior parte dei giorni chiude **+€250**, ma la varianza è a
**coda pesante** — un singolo risultato che colpisce può bruciare **giorni o
settimane** di profitti. Omega implementa **fedelmente** questa strategia perché
richiesta, ma la dashboard espone sempre **liability aperta** e **drawdown**, e i
tre cap del §7 sono a un click di distanza. Questa sezione è parte della
Costituzione: nessuna versione di Omega può rimuoverla o mascherare il rischio.

---

## 10. Definition of Done

- [ ] `omega_engine` puro con **test pytest** (selezione, sizing, target dinamico,
      settlement, idempotenza, finestra) verdi, ≥80% copertura del modulo.
- [ ] Migrazione `omega_bot.sql` idempotente (tabelle + 5 RPC owner-only + realtime).
- [ ] `omega_service` gira in **PAPER** end-to-end su eventi reali senza errori,
      piazza ≤1 trade/match, aggiorna stato/equity, regola il P&L al settlement.
- [ ] Frontend: card Omega → `/omega` fullscreen; equity real-time, barra
      obiettivo, lista trade, popup incassi, pannello parametri, START/STOP,
      toggle PAPER/LIVE. Test vitest della pagina + `lib/omega.ts` verdi.
- [ ] `npm run build` (tsc) e `pytest` verdi. Nessun `print()` nel codice runtime
      (usare `logging`).
- [ ] **Review approfondita finale** (punto 6 del goal): code-review + security +
      verifica manuale del flusso PAPER.
- [ ] LIVE **non** attivato senza semaforo esplicito dell'utente.

---

_«Omega piazza una scommessa e aspetta. La disciplina è nel non fare altro.»_
