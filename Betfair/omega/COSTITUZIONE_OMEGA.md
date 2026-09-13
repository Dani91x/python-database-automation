# ⟶ COSTITUZIONE DEL BOT «OMEGA» ⟵
### Fonte unica di verità. Ogni riga di codice di Omega deve essere conforme a questo documento.
### v3.0 — 11/09/2026 sera (§17, commit `9d09c81`) · Betfair Exchange (.it)
### Correct Score LAY a **DUE GAMBE** per partita · **green-up automatico** · PAPER (live bloccato)

> Storia delle versioni: **v1.0** 12/07 (una gamba, quota più alta, set-and-forget) → **v2.0**
> 09/09 (§11: due gambe, selezione per **probabilità di modello**) → **v2.1** 10/09 (§12:
> green-up automatico — Omega non è più una scommessa ma un **trade**) → **v2.2** 11/09 giorno
> (§§14-15: giornata operativa = giorno di piazzamento, modello definitivo) → **v3.0** 11/09 sera
> (§16 certificazione capillare, §16.7 seconda passata, **§17 audit applicato + contratto UI**).
> Le sezioni sono **datate e mai cancellate**: dove una regola è stata superata, la riga porta un
> rimando alla sezione che la supera.

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

> ⚠️ **Superato il 09/09 (§11) e il 10/09 (§12).** Oggi Omega piazza **DUE** gambe per partita
> (1T sull'Half Time Score, 2T sul Correct Score) scegliendo il risultato con la **probabilità di
> modello più bassa** — mai «la quota più alta» — e **non aspetta più il settlement**: ogni gamba
> viene **chiusa a mercato** (green-up) appena il rischio diventa reale, oppure TENUTA se il
> modello dice che uscire butta valore atteso. «Set-and-forget» vale ancora per l'**utente**
> (nessuna azione richiesta dopo lo START), non per il bot.

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

> ⚠️ **Superato l'11/09 (§14.1)**: la giornata di una posizione è il giorno Europe/Rome in cui
> la sua **APERTURA** è stata piazzata (le gambe di chiusura ereditano il giorno del padre), e
> `R` = P&L delle posizioni **piazzate** oggi e già regolate. Dall'11/09 sera (§17.2, review H1)
> le **guardie** (stop-loss giornaliero, target dinamico, stop sull'obiettivo) non usano `R` ma
> `realized_effective` = `R` + `min(0, locked_pnl_open_today)`: una perdita già **bloccata** da
> una copertura completa è denaro perso anche se si incassa al fischio finale.

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
   > ⚠️ **Superato il 09/09 (§11) e l'11/09 (§15.2/§15.4)**: la quota più alta è la regola del
   > motore **v1** (`params.engine='single'`, kill-switch). Il motore di default `legs` ordina
   > per **probabilità del modello** — `max`(P calibrata o con fattore di coda, P empirica per
   > minuto) — e, fra i candidati a P equivalente, per **costo di copertura**.
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

> ⚠️ `entry_minute_min`/`entry_minute_max` valgono SOLO per il motore **v1**. Nel motore di
> default `legs` (§11) le finestre sono `ht_entry_min/max` (20′–40′) per la gamba 1T e
> `ft_entry_min/max` (50′–80′) per la 2T, sempre sul **minuto REALE** del feed unico — mai
> sull'orologio, che al 60′ di kickoff+minuti mette una partita ancora al 45′ (§16.1 HIGH-1).

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

> ⚠️ **Superato il 10/09 (§12)**: fra `open` e il settlement c'è ora il **green-up automatico**.
> Una gamba coperta passa a `hedged` e la copertura è una **riga nuova** con `closes_trade_id`; il
> settlement nettizza la coppia con la commissione sul netto (`safe_strategy.execution`), e dall'
> 11/09 sera lo fa **per POSIZIONE** (`meta.position_pnl`/`position_result`, §17.1 M-04). Il
> settlement REST resta l'autorità ultima (I3).

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
in `lib/omega.ts` ↔ backend `omega_config.resolve_params`). Elenco **COMPLETO e allineato alla
`_SPEC` reale** di `Betfair/omega/omega_config.py` (52 chiavi, verificato l'11/09 sera — la
tabella parziale a 18 righe delle versioni precedenti è **superata**). I gruppi sono quelli del
pannello UI (`frontend/src/lib/omega.ts:OMEGA_PARAM_GROUPS`): **ogni** chiave della whitelist ha
un campo, e un test lo impedisce di dimenticarlo nelle due direzioni, con gli **stessi** clamp e
le stesse unità (`test_omega_ui_contratto_2026_09_11.py::TestWhitelistParametri`). L'obiettivo
giornaliero (`__daily_goal` nel pannello) NON è un `params`: va sulla colonna dedicata
`omega_control.daily_goal`.

| gruppo nel pannello UI | chiave | default | unità · limiti (clamp del servizio) | significato |
|---|---|---:|---|---|
| Selezione e finestre | `engine` | `legs` | `legs` \| `single` | motore: due gambe per partita (v2, §11) \| una gamba CS (v1, kill-switch) |
| Selezione e finestre | `price_min` | 20 | quota · 1,01…1000 | quota lay minima |
| Selezione e finestre | `price_max` | 120 | quota · 1,01…1000 | quota lay massima («non 600») |
| Selezione e finestre | `ht_entry_min` | 20 | minuto · 0…45 | finestra gamba 1T (Half Time Score), minuto REALE dal feed |
| Selezione e finestre | `ht_entry_max` | 40 | minuto · 0…45 | niente 1T dopo questo minuto |
| Selezione e finestre | `ft_entry_min` | 50 | minuto · 45…130 | finestra gamba 2T (Correct Score) |
| Selezione e finestre | `ft_entry_max` | 80 | minuto · 45…130 | niente 2T dopo questo minuto |
| Selezione e finestre | `model_p_max_pct` | 2.0 | **punti %** · 0,01…50 | P(modello) massima del risultato layato |
| Selezione e finestre | `model_min_goal_distance` | 2 | gol · 1…5 | gol AGGIUNTIVI minimi dal punteggio corrente |
| Selezione e finestre | `max_events` | 0 | partite/giorno · 0…1000 | tetto **PARTITE** (non gambe, §17.2 M1); 0 = illimitato |
| Selezione e finestre | `min_lay_liquidity` | 5.0 | € · 0…100 000 | size lay minima disponibile al best |
| Selezione e finestre | `min_stake` | 0.50 | € · 0,50…1000 | stake lay minimo Betfair .it |
| Selezione e finestre | `include_aggregate` | false | bool | includere i runner «Any Other …» |
| Selezione e finestre | `entry_window_source` | `score` | `score` \| `clock` | minuto+punteggio dal feed condiviso \| orologio da `marketStartTime` |
| Motore v1 (una gamba) | `entry_minute_min` | 30 | minuto · 0…130 | **solo** con `engine='single'` |
| Motore v1 (una gamba) | `entry_minute_max` | 60 | minuto · 0…130 | **solo** con `engine='single'` |
| Modello e probabilità | `model_calibration` | **`off`** | `off` \| `auto` | calibratore condiviso sulla P del modello. **OFF di default**: è addestrato sulla Safe Strategy, non su Omega (§16.7 2P-F-03); la coda la corregge `model_tail_factor` |
| Modello e probabilità | `model_calibration_path` | `""` | testo | vuoto = percorso di default del calibratore |
| Modello e probabilità | `model_empirical` | `veto` | `veto` \| `off` | P usata = max(modello, dato empirico) — si banca solo se raro per ENTRAMBE le viste |
| Modello e probabilità | `model_empirical_max_minute` | 60 | minuto · 45…90 | minuto entro cui vale il veto HT→FT (§14.2); con la tabella per minuto (§15.2) il veto vale sempre |
| Modello e probabilità | `model_tail_factor` | 1.3 | fattore · 0,5…5 | correzione **continua** della coda del Poisson (banco §15.3/§16.5) |
| Modello e probabilità | `model_lambda_cv` | 0.30 | cv · 0…1 | incertezza sui λ (mistura lognormale ≈ coda binomiale negativa); 0 = Poisson puro |
| Modello e probabilità | `model_use_yellow_cards` | true | bool | cartellini gialli del feed nei tassi residui (§15.5) |
| Modello e probabilità | `lambda_market_grid` | true | bool | λ impliciti nell'INTERO mercato (scala CS + linee O/U, §15.1) |
| Modello e probabilità | `lambda_live_fallback` | true | bool | λ dal mercato Over/Under live quando mancano fixture e pre-KO (§14.2) |
| Modello e probabilità | `select_cost_aware` | true | bool | a P equivalente vince il risultato più economico da coprire (§15.4) |
| Modello e probabilità | `select_p_band_ratio` | 2.0 | × la P più bassa · 1…10 | ampiezza della banda di «P equivalente» |
| Modello e probabilità | `select_k_se` | 0.0 | k·SE · 0…3 | P conservativa = centro log-pool + k·SE; 0 = solo il centro (§16.3) |
| Modello e probabilità | `select_p_hedge` | 0.5 | frazione · 0…1 | P di dover coprire, nel ranking per EV |
| Modello e probabilità | `select_ev_kappa` | 1.0 | peso · 0…5 | peso del costo di copertura nel ranking per EV |
| Green-up automatico | `greenup_enabled` | true | bool | uscita a mercato attiva (§12) |
| Green-up automatico | `greenup_mode` | `auto` | `auto` \| `off` | interruttore del green-up automatico |
| Green-up automatico | `greenup_trigger_distance` | 1 | gol · 0…3 | il bancato è raggiungibile con ≤ N gol → si valuta l'uscita |
| Green-up automatico | `greenup_price_trigger_ratio` | 0.5 | frazione dell'ingresso · 0,05…1 | lay ≤ ratio × prezzo d'ingresso → si valuta l'uscita |
| Green-up automatico | `greenup_settle_delay_s` | 30 | secondi · 0…600 | attesa dopo un gol (mercato sospeso, quote che si riallineano) |
| Green-up automatico | `greenup_hold_max_risk` | 0.02 | **frazione 0-1** · 0…1 | P(perdita) ≤ → si TIENE (clampato a `greenup_risk_cap`) |
| Green-up automatico | `greenup_risk_cap` | **0.15** | **frazione 0-1** · 0…1 | P(perdita) ≥ → si ESCE comunque |
| Green-up automatico | `greenup_ev_margin` | **0.10** | **EURO** (non una frazione) · 0…1000 | bloccato ≥ EV(tengo) − margine → si esce |
| Green-up automatico | `greenup_take_profit_frac` | 0.9 | frazione · 0,1…1 | il cash-out blocca ≥ questa quota dello stake… |
| Green-up automatico | `greenup_take_profit_minute` | 80 | minuto · 0…130 | …e da questo minuto → take-profit |
| Green-up automatico | `greenup_retry_s` | 20 | secondi · 2…600 | cooldown fra tentativi (residuo o errore) |
| Green-up automatico | `greenup_max_attempts` | 15 | · 0…100 | cap tentativi per posizione (poi `failed` + cooldown 5′, §16.1 H6) |
| Protezioni e cap | `commission_pct` | 5.0 | % · 0…20 | commissione Betfair, **fissata sul trade** al piazzamento (§17.1 L-02) |
| Protezioni e cap | `max_liability_per_match` | 0 | € · 0…1 000 000 | cap liability **PER GAMBA** (1T e 2T si sommano, §16.7); 0 = OFF |
| Protezioni e cap | `daily_loss_cap` | 0 | € · 0…1 000 000 | stop-loss giornaliero su `realized_effective`; 0 = OFF |
| Protezioni e cap | `max_open_liability` | 0 | € · 0…10 000 000 | cap su `open_liability_effective`; 0 = OFF |
| Protezioni e cap | `stop_on_goal` | true | bool | stop ai NUOVI ingressi a obiettivo raggiunto |
| Esecuzione | `poll_interval_s` | 20 | secondi · 5…600 | cadenza del loop |
| Esecuzione | `execution_mode` | `auto` | `auto` \| `rest` | coda flumine quando il gate passa \| forza il percorso legacy (§6-bis) |
| Esecuzione | `paper_fill_ttl_s` | 45 | secondi · 5…600 | TTL quasi-FOK del place paper via coda. **SOLO paper** |
| Esecuzione | `omega_live_via_flumine` | true | bool | kill-switch del LIVE via coda (`FILL_OR_KILL` vero di Betfair) |
| Esecuzione | `live_fill_deadline_s` | 20 | secondi · 5…300 | hard deadline dell'esito FOK live dallo specchio (mai zombie) |

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
- **Frontend**: `frontend/src/lib/omega.ts` (client RPC + tipi + whitelist + vocabolari),
  route `/omega` (App.tsx), card in `SelectSport`, pagina fullscreen `pages/Omega.tsx`.
  > ⚠️ **Superato l'11/09 sera (§17.8)**: la pagina non è più «equity + lista trade + popup
  > incassi» ma la **struttura unica** delle tre sezioni di trading, normata da
  > `frontend/src/components/trading/DESIGN_SYSTEM.md`: `PageShell` → `BotHeader` (battito del
  > servizio, salute del feed, PAPER/LIVE) → `ModeBanner` → `DayBar` → `KpiRow` → tab sticky
  > `🎯 Missione · ⚙️ Automatico · ✋ Manuale · 📅 Storico`, con fondamenta pure condivise
  > (`lib/format.ts`, `lib/tradeStatus.ts`, `lib/toasts.ts`) e componenti in
  > `components/trading/`.

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

> **Aggiornamento 11/09 sera (§17).** Il tab «🎯 Missione» vive dentro la struttura unica di
> pagina (§17.8) e usa i **vocabolari condivisi**: gli stati delle gambe non sono più in inglese
> (`hedged`/`error` non sono «in gioco», audit M-07), la giornata è Europe/Rome e l'obiettivo ha
> UNA sola formula (audit M-08). La selezione delle gambe è quella per **modello** di §11/§15 —
> non più lo stake fisso di 1 € sulla quota più alta della v1.

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

> **Aggiornamento 10/09 (§12) e 11/09 sera (§17).** La coda pesante è **tagliata** dal green-up:
> la perdita massima di una gamba è il **costo della copertura** al prezzo corrente, non la
> liability. In cambio il rischio ha ora **TRE** numeri da mostrare, non uno, e la dashboard li
> mostra tutti e tre (§17.8): **Liability aperta** (rischio VIVO — zero a copertura completa),
> **P&L bloccato** (perdita o utile già fatti e non ancora incassati) e **In verifica su Betfair**
> (ordini reali a esito IGNOTO). E le **guardie** non guardano i numeri della vetrina ma quelli
> effettivi, `realized_effective` e `open_liability_effective` (§17.2 review H1): il rischio
> nascosto più pericoloso non è la liability, è **una perdita già bloccata che nessun cap conta**.

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

> **Stato all'11/09/2026 sera (§17).** Tutti i punti sono soddisfatti tranne l'ultimo, che resta
> un gate aperto **per scelta**: `omega_engine`/`omega_model` puri e testati (**453 pytest** su
> `Betfair/omega`, **1254** sui tre bot), migrazioni idempotenti (`omega_bot` → `omega_v2` →
> `omega_manual` → `omega_missions` → `omega_cashout` → `daily_history` → `omega_daily_v2` →
> `omega_models_v3`/`v4` **verificate applicate** sul DB reale; **`omega_models_v5.sql` da
> applicare**, §17.9), servizio in PAPER end-to-end su eventi reali, frontend con **1642 test
> vitest** più **26/26** di certificazione sui **dati reali**, review multiple (§16, §16.7,
> §17.2), nessun `print()` nel runtime. **LIVE ancora BLOCCATO** (§16.6, §17.9).

---

_«Omega piazza una scommessa e aspetta. La disciplina è nel non fare altro.»_

## 11. OMEGA v2 — due gambe per partita, selezione PER MODELLO (2026-09-09 sera)

**Decisione dell'utente.** Per OGNI partita in programma due operazioni: una nel
primo tempo e una nel secondo, sul risultato esatto con la **probabilità più bassa
di verificarsi secondo i nostri dati** — mai "la quota più alta", che da sola non
vuol dire nulla. Il target per partita è minuscolo e cala al crescere delle partite;
una perdita si **spalma** sulle partite residue (il target residuo sale).

**Gambe.** `ht_cs` = HALF TIME SCORE, ingresso nel 1T tra `ht_entry_min` e
`ht_entry_max` (default 20′–40′), si regola al 45′. `ft_cs` = CORRECT SCORE, ingresso
nel 2T tra `ft_entry_min` e `ft_entry_max` (default 50′–80′), si regola al 90′.
Fase e minuto vengono dal FEED unico dello scanner (stato IPS + minuto reale), mai
dall'orologio. Target di gamba = metà di (G−R)/M; l'intero se la 1T è mancata
(`omega_model.leg_target`). Idempotenza per gamba: unique `(event_id, phase)`
sull'automatico (`migrations/omega_v2.sql`); i trade v1 senza gamba chiudono l'evento.

**Modello (`omega_model.py`, puro).** λ pre-match per squadra dalla fixture abbinata
(`fixture_predictions`, tactical_engine/Poisson xG-DC) o, in mancanza, dalle quote 1X2
pre-KO congelate dallo scanner (devig + split). λ residui live da
`live_engine.inplay_residual_rates` (CDF reale del tempo residuo per lega, stato di
gioco, rossi). Griglia Poisson + Dixon-Coles (ρ per lega) sui gol residui traslata sul
punteggio corrente; orizzonte 45′ per la gamba HT. Selezione: runner ACTIVE con lay in
`[price_min, price_max]`, liquidità ≥ max(min, size necessaria), ≥ `model_min_goal_distance`
gol dal punteggio corrente, `P_modello ≤ model_p_max_pct` e `P_modello < 1/quota`
(il mercato lo sovraprezza): vince la P più bassa, poi il prezzo più basso. Senza λ
non si entra mai ("no_model_lambdas"). Il blocco di audit (P modello, P implicita,
λ, fonte, stato) è salvato in `trade.meta.model` e nelle suggestion delle missioni.

**Motore.** `params.engine`: `legs` (default, v2) | `single` (v1, kill-switch).
Missioni: stessa selezione per modello, HT e FT dal feed. UI: ogni trade mostra gamba,
minuto/punteggio all'ingresso e minuto/punteggio LIVE dal feed.

**Perché è solo migliorativo rispetto al v1.** Il v1 automatico non aveva né distanza
minima dal punteggio né modello: il 09/09 ha layato il punteggio CORRENTE (0-3 @22 sul
0-3, 1-0 @23 sull'1-0) — una perdita da 93,87 € su 16 trade. Il v2 esclude per
costruzione punteggio corrente e adiacenti e chiede che il modello dia il risultato
sotto la probabilità implicita.

## 12. GREEN-UP AUTOMATICO — la scommessa diventa un trade (2026-09-10)

**Decisione dell'utente (09/09 sera).** Omega non lascia MAI una gamba "a sé stessa":
ogni lay aperto (automatico o manuale, paper o live allo stesso modo) viene **chiuso a
mercato** — gamba back opposta sulla stessa selezione via lo strato condiviso
`safe_strategy.execution.close_trade` (lo stesso del cash-out manuale: riga di chiusura
con `closes_trade_id`, apertura `hedged` a residuo nullo, settlement nettizzato in
coppia) — appena il rischio diventa reale. Vince spesso poco, **perde poco** invece
dell'intera liability: la coda pesante (§9) si taglia.

**Trigger (`omega_service.process_auto_greenup`, ogni ciclo, ANCHE a bot fermo).**
1. **GOL** — il risultato bancato è raggiungibile con ≤ `greenup_trigger_distance` gol
   (default 1, su entrambi gli assi: 1-1 con bancato 1-2).
2. **QUOTA** — il lay della selezione è sceso sotto `greenup_price_trigger_ratio` (0.5) ×
   prezzo d'ingresso: il mercato la crede molto più probabile.
3. **TAKE-PROFIT** — dal minuto `greenup_take_profit_minute` (80) se il cash-out blocca
   ≥ `greenup_take_profit_frac` (0.9) dello stake → si incassa (kind `profit`) e si libera
   la liability per la gamba successiva.

**UNA decisione per tutti i trigger (`_greenup_decide`, regole di `exits.decide_time_exit`).**
ESCO se: il bancato È il punteggio corrente (distanza 0: il lay sta perdendo dal vivo —
incondizionato); oppure P&L bloccato ≥ 0; oppure `P(perdita) ≥ greenup_risk_cap` (0.15);
oppure bloccato ≥ EV(tengo) − `greenup_ev_margin` (0.10 €), con
EV(tengo) = (1−p)·stake − p·liability. Altrimenti TENGO (`greenup_hold`) e rivaluto a ogni
ciclo: ogni nuovo gol o mossa di prezzo rilancia la decisione. Caso vivo del 10/09 (trade 70:
lay 1-2 @55, stake 2.16, liability 116.64; 1-1 al 28′, p 0.12, back 4.90 → bloccato −22.1,
EV(tengo) −12.1): la vecchia regola "gol = esco" buttava 10 € di valore atteso → ora TENGO;
a p 0.16 o sull'1-2 reale → ESCO. Senza modello, riserva = P implicita dal back del feed.

**P(perdita)** = probabilità che il risultato bancato sia quello FINALE da qui: lo STESSO
modello della selezione (`omega_model.score_probs`, λ pre-match → residui live → griglia,
orizzonte 45′ per la gamba HT). Bancato ormai irraggiungibile → nessuna azione (il lay non
può più perdere). Gamba HT oltre il 45′ → la regola il settlement.

**Esecuzione.** Dopo un gol si aspetta `greenup_settle_delay_s` (30 s: mercato sospeso,
quote che si riallineano). Stato e prezzi dal FEED UNICO (mai righe stantie; mercato non
OPEN → `greenup_wait`); REST solo a rischio già reale. Fill cappato dalla liquidità →
RESIDUO ritentato con cooldown `greenup_retry_s` (20 s) fino a `greenup_max_attempts` (15),
poi `failed` + log `greenup_failed` (e `error`). Mai un secondo invio con una chiusura
`pending` (marker `meta.greenup` scritto PRIMA dell'ordine; `hedge_pending_ids` blocca).

**Contratto UI delle uscite (11/09, vocabolario CHIUSO condiviso con la Safe Strategy —
`safe_strategy.exits.ui_exit_kind`).** Ogni gamba di chiusura scritta dal servizio porta
`meta.exit_kind` ∈ `greenup` | `manual` | `profit` | `loss` | `time` | `red_card` |
`forced` | `other` ed `exit_reason` (testo breve italiano), su apertura E chiusura, più
`meta.exit_profit` (bool). Regola deterministica:
- `greenup` SOLO se la chiusura è INTEGRALE **e** il P&L bloccato è ≥ 0 (green-up vero);
- `loss` se la chiusura blocca una PERDITA (un green-up in perdita **non** è un green-up:
  il badge "CHIUSO IN GREEN-UP" su una perdita sarebbe una bugia al trader);
- `profit` se la regola è di profitto ma la chiusura è parziale o il bloccato è ignoto;
- `manual` per il cash out richiesto dall'operatore (`(parziale)` nel motivo quando
  `fraction`/`amount` o la liquidità lasciano un residuo).
Quale regola ha deciso l'uscita resta in `meta.greenup.kind` (`profit`|`loss`).

**Stato del green-up sulla riga (UNA struttura, `meta.greenup`).** `state` ∈ `pending`
(inviata, residuo da coprire) | `done` (coperta del tutto) | `hold` (TENGO) | `failed`
(tentativi esauriti: posizione SCOPERTA, `next_retry_at`) | `blind` (nessun feed) |
`residual_dropped` (residuo non copribile o non più necessario), con `reason` (italiano),
`at`, `attempts`, `p_lose`, `ev`. Un kind di attività per ogni caso: `greenup`,
`greenup_hold`, `greenup_wait`, `greenup_failed`, `greenup_blind`,
`greenup_residual_dropped`, `cashout_manual`.

**Stato della copertura (UN solo writer: `safe_strategy.execution.apply_hedge_state`).**
`meta.hedge` = {`fraction`, `remaining_liability`, `hedged_size`, `residual_size`,
`complete`} e `meta.hedging` = una gamba di chiusura è IN VOLO.

Log `greenup` con trigger, minuto, punteggio, bancato, P(perdita) e fonte, P&L bloccato,
back, size, `exit_kind` e `state`.

**Il rischio dopo la copertura (11/09).** A copertura COMPLETA la liability aperta è ZERO
(la perdita bloccata è già fatta, non può peggiorare) e il P&L bloccato va a
`locked_pnl_open` / `locked_pnl_open_today`. Ma le GUARDIE non lo perdono di vista: lo
stop-loss giornaliero e il target dinamico lavorano su
R efficace = `realized_today` + min(0, `locked_pnl_open_today`), e il cap
`max_open_liability` su `open_liability` + max(0, −`locked_pnl_open`). Una perdita
bloccata è denaro perso anche se si incassa al fischio finale: mai anticipare un utile,
sempre anticipare una perdita.

**Parametri (§7, whitelist `omega_config`).** `greenup_enabled` (True), `greenup_mode`
(`auto`|`off`), `greenup_trigger_distance` 1, `greenup_price_trigger_ratio` 0.5,
`greenup_settle_delay_s` 30, `greenup_hold_max_risk` 0.02, `greenup_risk_cap` 0.15,
`greenup_ev_margin` 0.10, `greenup_take_profit_frac` 0.9, `greenup_take_profit_minute` 80,
`greenup_retry_s` 20, `greenup_max_attempts` 15. **Calibrazione della selezione**:
`model_calibration` (`auto`|`off`, **default `off`** dall'11/09 sera — §16.7 2P-F-03 e §7) e
`model_calibration_path`: se esiste
`safe_strategy/calibration.py` (`Calibrator.load(path)` / `.apply(p, family, minute)`,
famiglie `cs`/`hts`) la selezione usa la P CALIBRATA; import guardato, `p_model_raw` e
`p_model` entrambi nel blocco di audit.

**Perché.** Il 09/09 il v1 ha perso 93,87 € perché ogni gamba andava al settlement con
tutta la liability. Con l'uscita a mercato la perdita massima di una gamba è il costo del
green-up al prezzo corrente (tipicamente una frazione dello stake), non la liability.

## 13. GIORNATA 10/09/2026 — cash out, calibrazione, green-up, storico: stato e spunti

Riferimento incrociato: `Betfair/safe_strategy/COSTITUZIONE_SAFE_STRATEGY.md` (layer
condiviso `execution.py`, cash out, calibrazione, uscite a modello, dashboard).

### 13.1 Cosa è stato fatto oggi su Omega
- **Certificazione liquidità (mattina, richiesta del 09/09)**: lato LAY ok su evidenza
  (37/37 trade del 09/09 senza riduzioni; best-lay ≥23 € su 19 selezioni in fascia 20–120);
  lato BACK (green-up) NON certificabile senza dati; tutti i fill paper del 09/09 erano
  istantanei (`paper_fill_fallback: follow_assente`, niente bet delay). La sonda
  `liquidity_probe.py` è SOLO report (il registratore è stato rimosso su ordine dell'utente:
  mai processi/registratori nuovi senza permesso; i dati vengono dalle registrazioni REC).
- **Cash out** (`omega_manual_requests` kind `cashout`, `omega_cashout.sql`): gamba di
  chiusura con `closes_trade_id`, status `hedged`, parziali ripetibili, settlement a coppia
  con commissione sul netto (`execution.settle_group`); indici univoci esclusi per le
  chiusure; aggregati (`get_omega_state`, `aggregate_trades`) senza le gambe di chiusura.
  Verificato dal vivo in paper: lay 2@6,6 → parziale 1 € (−6,6 peggiore) → totale (−0,35
  bloccato) → settlement −11,20 +4,60 +6,25 = −0,35.
- **Green-up automatico** (§12): trigger gol (distanza ≤1), prezzo (lay ≤ 50% dell'entrata),
  take-profit (≥90% del massimo dall'80'); decisione UNICA a valore atteso
  (`exits.decide_time_exit`): locked ≥ 0 → esci; p_lose ≥ 15% → esci; locked ≥ EV(hold) −
  0,10 → esci; altrimenti TIENI e rivaluta; distanza 0 → esci sempre. Caso vivo trade 70:
  lay 1-2 1T @55 (stake 2,16, liability 116,64), 1-1 al 28', p_lose 12%, back 4,90 →
  chiuso a −22,10 con la regola vecchia (rischio > 10%); con la regola nuova → HOLD
  (EV hold −12,10 > −22,10). Questo è il costo strutturale di Omega: uscire da un lay a 55
  costa dieci vincite.
- **Selezione calibrata**: `select_by_model` usa la probabilità calibrata
  (`safe_strategy/calibration.py`, famiglie cs/hts) quando `model_calibration='auto'`;
  audit con `p_model_raw` e `calibrated`.
- **Storico per giorno** (`daily_history.sql`, tab "Storico" con calendario, statistiche,
  dettaglio giornata; missione giornaliera esplicita "obiettivo di oggi / realizzato / resta"
  che riparte da 0 ogni giorno operativo Europe/Rome). Nota: `goal` storico = daily_goal
  corrente (manca lo snapshot per giorno).
- **Tabella trade**: colonna Selezione + Lato LAY/BACK, gambe di chiusura attaccate
  all'apertura ("↳ Green-up di #70 · BACK 24,24 € @4,90"), stato "CHIUSO IN GREEN-UP",
  P&L bloccato, motivo, tooltip. Non verificata a occhio (browser agente bloccato su
  127.0.0.1): l'utente la giudica ancora illeggibile → da rifare (vedi Safe §6).
  **Superato l'11/09 sera (§17.8)**: rifatta — una riga per **PARTITA**, stati in italiano dal
  vocabolario condiviso, badge green-up per **stato**, quote LIVE con freschezza, «se chiudo ora»
  netto, cash out sul **residuo**. E il badge «CHIUSO IN GREEN-UP» non è più incondizionato: vale
  SOLO per una chiusura **integrale** con bloccato ≥ 0 (§17.2 review H3).
- Settlement di ieri: 11 trade regolati all'avvio (tutti vinti, +53,44), P&L realizzato
  oggi contabilizzato per giorno di settlement (§2).

### 13.2 Parametri aggiunti (omega_config)
`greenup_enabled` (true), `greenup_mode` (auto|off), `greenup_trigger_distance` (1),
`greenup_price_trigger_ratio` (0,5), `greenup_settle_delay_s` (30), `greenup_hold_max_risk`
(0,02), `greenup_risk_cap` (0,15), `greenup_ev_margin` (0,10), `greenup_take_profit_frac`
(0,9), `greenup_take_profit_minute` (80), `greenup_retry_s` (20), `greenup_max_attempts`
(15), `model_calibration` (auto|off), `model_calibration_path`.

### 13.3 Verità sul rischio (aggiornata)
- Bancare a 20–120 per target di 2–8 € significa che OGNI uscita di protezione costa
  5–20 vincite. Il green-up limita la coda (mai più −116) ma sposta il problema: il
  P&L medio per partita resta ≈ 0 al lordo, negativo con le uscite.
- Il backtest del modello in-play (Safe §5.1) mostra che i LAY su esiti "impossibili"
  sono la famiglia peggiore (ottimismo del modello dal 60' in poi). Omega è esattamente
  quella famiglia: la probabilità calibrata è ora usata nella selezione, ma va validata.

### 13.4 Spunti per il livello successivo (domani)
1. **Uscite**: rivedere loss/profit strategia per strategia (Safe §3) e per Omega decidere se
   il green-up a distanza 1 va sempre valutato a EV (oggi sì) o se l'utente preferisce la
   protezione dura; uscita a scala su libri sottili; attesa post-gol adattiva.
2. **Ingresso**: pesare il costo atteso del green-up già alla selezione (prezzo del back
   del risultato bancato e liquidità sul lato back) — scegliere il risultato "meno probabile
   E più economico da coprire", non solo il meno probabile.
3. **Fedeltà paper**: bet delay 5 s e ricontrollo size; follow automatico degli eventi
   tradati per passare dalla coda flumine (fill simulati sul book vero).
4. **Dashboard**: una riga per posizione con timeline (ingresso → gol → green-up → esito),
   linguaggio del manuale, spiegazione a un click di ogni decisione automatica.
5. **Storico**: snapshot giornaliero dell'obiettivo; confronto obiettivo/realizzato per
   settimana; per-fase (1T/2T) e per lega.
6. **Certificazione liquidità lato back**: dalle registrazioni REC (report della sonda).
7. **Live**: mai prima di giorni di paper con green-up e settlement verificati.

Commit del 10/09: 99fbff8, 5fd3fae (master). Migrazioni applicate: betfair_live_cashout_v3,
omega_cashout, safe_strategy_bot, daily_history.

## 14. GIORNATA = PARTITE DEL GIORNO, DUE GAMBE SEMPRE, RISULTATI REALI (11/09/2026)

Decisione dell'utente (11/09 mattina, "sistemiamo strumento per strumento, partiamo da
Omega"): (1) la barra di avanzamento è GIORNALIERA e ogni giorno il P&L riparte da 0
**in base alle partite di quella specifica giornata**, lo storico tiene traccia giorno
per giorno; (2) per OGNI partita DUE trade, uno nel 1T e uno nel 2T, obiettivo della
partita diviso in due selezioni, la seconda scelta in base al risultato del 1T con tutti
i dati disponibili; (3) tabella dei trade con il risultato REALE di fine 1T e fine 2T su
ogni riga, tutte le informazioni delle due gambe, P&L in rosso/verde, chiusure evidenziate.

### 14.1 Giornata operativa = giorno di PIAZZAMENTO della posizione
- Prima: `R` di oggi = P&L dei trade **regolati** oggi (§2). Difetto visto l'11/09 alle
  08:25: 11 gambe del 10/09 sera regolate al riavvio del mattino → +23,08 € sulla barra di
  oggi, senza nessuna partita di oggi.
- Ora: la giornata di una posizione è il giorno Europe/Rome in cui la sua **apertura** è
  stata piazzata; le gambe di chiusura ereditano il giorno dell'apertura che chiudono.
  `R` = P&L delle posizioni piazzate oggi e già regolate. Vale in `omega_engine.
  aggregate_trades`, nella RPC `get_omega_state` e nello storico (`get_omega_daily` /
  `get_omega_day_trades` con attribuzione `'placed'`; Safe Strategy resta `'settled'`).
- **Obiettivo storicizzato**: tabella `omega_daily_goal` (giorno → obiettivo), scritta da
  `omega_activate` / `omega_update_params` e dal servizio a ogni ciclo (snapshot
  idempotente). Lo storico mostra l'obiettivo che valeva quel giorno (`goal_snapshot`).
- Dashboard: card "Obiettivo giornaliero" con partite/operazioni di oggi; KPI
  "Operazioni oggi" (V/P/vive); tabella "Partite di oggi" (+ vive di giorni precedenti,
  marcate `prec.`) con toggle "mostra tutte"; le giornate passate vivono nello Storico.

### 14.2 Due gambe SEMPRE — perché il 10/09 la 2T non è mai partita
- Log del 10/09: **746 skip `ft_cs · no_model_lambdas`** su 12 partite (e 58 sulla 1T):
  la catena λ era fixture → quote 1X2 pre-KO del feed; lo scanner riavviato a partita in
  corso (o agganciata dopo il calcio d'inizio) non ha più `pre_ko`, la lega minore non ha
  fixture, la cache di processo non sopravvive ai riavvii → gamba 2T sempre saltata.
- **Catena λ (`_prematch_lambdas`)**: 1. fixture abbinata (tactical_engine / Poisson
  xG-DC) → 2. λ **persistiti sull'evento** (`omega_events.model`, migrazione) → 3. quote
  1X2 pre-KO congelate → 4. λ salvati nel blocco di audit di un trade precedente dello
  stesso evento (la 1T porta `meta.model.lambda_pre`) → 5. **mercato OVER/UNDER live**
  (`omega_model.lambdas_from_live_ou`: P(over) de-viggata della linea più vicina a gol
  attuali + 2,5 → λ residuo Poisson → "λ pre-match equivalente" con gli stessi
  moltiplicatori live del modello; split casa/trasferta 0,54/0,46; fonte `live_ou`, log
  `model_lambda_live`). Ogni λ non da fixture viene persistito sull'evento. Senza nulla →
  skip `no_model_lambdas` come prima (mai a occhi chiusi). Param `lambda_live_fallback`.
- **Target di gamba = (G − R) / gambe ancora piazzabili** (`omega_engine.legs_remaining`:
  2 per partita non toccata, 1 se una gamba è fatta o la sua finestra è passata; il cap
  `max_events` limita solo le partite NUOVE — la seconda gamba di una partita già in
  posizione si fa SEMPRE, anche a cap raggiunto). Prima era metà di (G−R)/partite con un conteggio che ignorava le gambe già
  fatte. Stats: `legs_remaining`, `target_leg`, `target_match` (= 2 × gamba).
- **Selezione 2T con i DATI (seconda opinione)**: tabella `omega_ht_ft_transitions`
  (migrazione: da `matches`, punteggio al 45′ → finale, per lega e globale; RPC
  `get_omega_ht_ft`) letta una volta per lega (`omega_empirical.EmpiricalTable`, shrinkage
  Bayesiano verso il globale, K=200). Quando il punteggio all'ingresso 2T è ancora quello
  del 45′ (`halfTimeScore` del feed IPS) la P usata per filtro e ordinamento è
  **max(P modello calibrata, P empirica)**: si banca un risultato solo se è raro per
  ENTRAMBE le viste (il backtest del 10/09 dice che il modello è ottimista dal 60′). Con
  gol già nel 2T, o tabella assente, resta il solo modello. La tabella copre TUTTO il
  2° tempo: il confronto con `p_max` e con la P implicita è onesto solo a inizio ripresa
  → il veto si applica fino a `model_empirical_max_minute` (default 60′), oltre resta il
  modello (audit `fuori_finestra`). Audit in `meta.model`: `p_data`, `p_selected`,
  `empirical`, `empirical_n`, `ht_score`, `empirical_note`. Param `model_empirical`
  (`veto`|`off`), `model_empirical_max_minute`.

### 14.3 Risultati reali e tabella per partita
- `meta.runners` (nomi dei runner a punteggio esatto) salvato al piazzamento: al
  settlement il WINNER del Half Time Score È il risultato del 1T, quello del Correct Score
  È il finale → `meta.result_ht` / `meta.result_ft` (`_stamp_market_result`, autorevole
  quanto il P&L, I3). Ogni ciclo, anche a bot fermo, `track_event_results` legge il feed
  unico (`halfTimeScore`/`fullTimeScore` IPS; all'intervallo il corrente È il 1T, a partita
  finita è il finale) e completa i risultati su tutte le aperture della partita. Mai
  sovrascritti, mai dedotti a partita in corso.
- UI (`components/omega/MatchTradesTable.tsx`, logica pura `lib/omegaMatches.ts`): UNA
  riga = UNA partita — Ora/KO · Partita (punteggio live) · **1° tempo** (LAY risultato
  @quota, stake, rischio, ingresso min·punteggio, P modello, stato, P&L gamba, motivo
  dell'uscita, chiusure `↳ Green-up BACK 24,24 € @4,90` evidenziate sotto la gamba, cash
  out) · **Risultato 1T** (reale, rosso se il bancato è uscito) · **2° tempo** (idem) ·
  **Risultato 2T** · **P&L partita** (regolato / bloccato / in corso, verde-rosso, con il
  rischio ancora aperto). Stessa tabella nel dettaglio giorno dello Storico.

### 14.4 Migrazione e parametri
`migrations/omega_daily_v2.sql` (da applicare in Supabase DOPO daily_history.sql e
omega_cashout.sql): `omega_daily_goal` + snapshot nelle RPC, `get_omega_state` per
giornata di piazzamento (+ `legs_today`, `events_today`, `won_today`, `lost_today`,
`goal_today`), `trading_daily_history`/`trading_day_trades` con `p_day_by`, `get_omega_daily`
con obiettivo per giorno, `omega_events.model`, `omega_ht_ft_transitions` + `get_omega_ht_ft`. La
costruzione della tabella HT→FT è un PASSO SEPARATO (legge ~1,4 M partite):
`SELECT public.omega_build_ht_ft_transitions();` una volta, dopo la migrazione. Il codice è tollerante alla migrazione non applicata
(nessun crash: tabella empirica = off, λ non persistiti, storico per giorno di
regolazione, obiettivo corrente). Parametri nuovi in `omega_config`: `model_empirical`
(`veto`), `lambda_live_fallback` (true). Test: `test_omega_giornata_gambe_2026_09_11.py`
(15), `lib/omegaMatches.test.ts` (9), pagina/DayDetail aggiornati.

> **Stato 11/09 sera**: `omega_daily_v2.sql` e `omega_models_v3.sql` sono **verificate APPLICATE**
> sul DB reale (sonda in `migrations/APPLY_ORDER_2026-09-11.md`: `get_omega_state` risponde e
> `get_omega_daily` porta `goal_snapshot` e `by_strategy` per `phase`). L'unica migrazione Omega
> ancora da applicare è **`omega_models_v5.sql`** (§17.9).

### 14.4-bis Costo a runtime (verificato 11/09)
- Nulla di pesante gira nel ciclo: gli aggregati li calcola il DB in UNA query
  (`get_omega_aggregates` → `omega_aggregates_sql`, tabella `omega_trades` ~100
  righe/giorno, join su PK, indici `placed`/`status`/`event_id`); il servizio non legge
  più tutta la tabella a pagine (fallback legacy solo senza migrazione).
- La tabella HT→FT si costruisce UNA volta (`omega_build_ht_ft_transitions`: una sola
  passata su `matches`, 4 colonne intere, GROUPING SETS; il `set_config` del timeout dentro la funzione NON agisce sullo statement in corso: lanciarla con `SET statement_timeout = '15min';` nello stesso script) e a
  runtime si legge per chiave primaria (poche centinaia di righe per lega, cache per
  processo). Il servizio non tocca mai `matches`.
- Letture del feed: invariate (una SELECT per ciclo sul feed unico); risultati reali:
  una SELECT per ciclo sulle posizioni delle ultime 36 h (indice `placed_at`), scritture
  solo quando un risultato è nuovo.

### 14.5 Ancora aperto
Fedeltà paper (bet delay 5 s), certificazione liquidità lato back dalle registrazioni REC,
uscite loss/profit strategia per strategia (Safe §3), i sei edge del piano 250 (Safe §11).

## 15. MODELLO DEFINITIVO — mercato intero, dati per minuto, validazione, costo di copertura (11/09/2026 pomeriggio)

Richiesta dell'utente: "è la soluzione migliore? hai considerato altri modelli, che siamo
in live, ogni cosa che migliora il sistema?" → tutti e cinque i punti implementati.

### 15.1 λ impliciti nell'INTERO mercato (`omega_model.lambdas_from_market_grid`)
Dalla scala completa del Correct Score (probabilità de-viggate mid back/lay,
normalizzate su tutte le selezioni, aggregati inclusi) e da tutte le linee Over/Under
aperte si cercano i λ residui (casa, trasferta) la cui griglia di Poisson riproduce
meglio il mercato (griglia log-spaziata 28×28 + raffinamento locale; ~0,2 s, una volta
per evento). Riportati a "pre-match equivalenti" coi moltiplicatori live del modello.
Catena λ ora: fixture → λ persistiti → pre-KO → hint dal trade 1T → **mercato intero**
(`market_grid`, log `model_lambda_market`) → singola linea O/U (`live_ou`). Quando la λ
usata non viene dal mercato, il fit di mercato è comunque scritto nell'audit
(`lambda_market`, `market_fit_loss`) come cross-check.

### 15.2 Tabella PER MINUTO dai gol con minuto (`omega_empirical.MinuteTable`)
Migrazione `omega_models_v3.sql`: tabella `omega_minute_transitions` (lega/globale ×
bucket 5′ × punteggio × target ft|ht × risultato × n) costruita da `matches` +
`match_events` (solo partite i cui gol ricostruiti coincidono col finale; autogol alla
squadra che ne beneficia; gol al 90′+recupero solo nel finale). Costruzione = passo
separato (incrementale, §15.6: `_schedule()` con pg_cron o `_run(90)` a mano). A runtime: RPC
`get_omega_minute_ft(lega, bucket, target)` (poche centinaia di righe, PK), cache per
processo. Nella selezione ha la precedenza sul veto HT→FT (§14) e vale per ENTRAMBE le
gambe: `p_selected = max(P modello, P empirica per minuto)`. Audit `empirical_source`
(`minute`), `empirical_bucket`.

### 15.3 Banco di validazione (`omega_validate.py`, `tools/omega_validate_models.py`)
Metriche pure: log-loss/Brier, tabella di affidabilità per fascia di P, log-loss
multiclasse sui risultati esatti e **calibrazione della coda** (risultati con P ≤ 2 %:
usciti/previsti — il numero che decide se il lay è a valore atteso ≥ 0). Lo strumento
confronta sullo storico (campione con gol a minuto, training/test separati) Poisson con λ
di lega, Poisson+calibratore, Poisson+fattore di coda, tabella per minuto e miscele.
Rapporto `Betfair/omega/reports/validazione_modelli_2026-09-11.md`.
**Risultati 11/09**: la coda del Poisson è SOTTOSTIMATA (usciti/previsti 1,5 al 25′ sul
45′; 1,1–1,2 al 60′/70′ sul finale su 627 partite di test; 1,7–1,8 sul campione da 267).
La miscela modello+dati ha sempre log-loss migliore e coda più calibrata.
**Bug trovato dal banco**: le famiglie del calibratore condiviso erano `cs`/`hts` (nomi
inesistenti) → la calibrazione della selezione era un no-op silenzioso; ora `cs_cell`/
`hts_cell` (tabelle reali dai 60.911 campioni registrati: nella fascia bassa il CS esce
1,7–2,2× la P dichiarata, l'HT ≈ 1×). Sullo storico il calibratore rende la coda del
finale PRUDENTE (usciti/previsti 0,6) e non basta al 45′ (1,6); il fattore di coda
`model_tail_factor` (1,3) dà 0,94–1,02. Regola live: P usata = **max**(calibrata, grezza ×
fattore) — un lay solo se il risultato è raro secondo entrambe (le perdite valgono
20–50 vincite: la prudenza sulla coda costa poche occasioni, l'ottimismo costa giorni).

### 15.4 Selezione con COSTO DI COPERTURA (`omega_model.rank_by_cover_cost`)
A quote fair l'EV della scommessa è ≈ 0: decide quanto costa uscire. Fra i candidati a
P equivalente (entro `select_p_band_ratio` = 2 × la più bassa) vince quello coprbile e
più economico da coprire subito (`cover_cost` = size·(lay/back − 1), liquidità back
sufficiente), poi liquidità back, poi liability minore. Audit `cover_cost`, `back_price`,
`back_size`, `cost_aware`. Param `select_cost_aware` (true).

### 15.5 Segnali live
Cartellini gialli dal feed IPS nello stato live (`LiveState.yellow_*`) → moltiplicatori
già calibrati per lega di `live_engine` (prima mai passati). Corner/pressione: il
moltiplicatore resta 1 — non esistono dati storici di corner per minuto per calibrarlo e
le 26–40 registrazioni sono troppo poche; si accende solo dopo una calibrazione
sulle registrazioni REC (banco di validazione riusabile), mai a occhio.

### 15.6 Migrazione e passi
`migrations/omega_models_v3.sql` (dopo omega_daily_v2), poi `omega_models_v4.sql` (§16.4: un passo manuale risponde `busy` se pg_cron sta lavorando). Costruzione INCREMENTALE (l'SQL
editor ha un timeout del gateway di ~2 min): `SELECT public.omega_build_minute_transitions_schedule();`
(pg_cron: un passo al minuto, si ferma da solo) oppure a mano `SELECT
public.omega_build_minute_transitions_run(90);` finché `done = true`; progresso in
`omega_build_jobs`; da capo con `_reset()`. Senza: tabella per minuto off → veto HT→FT e
modello. Parametri nuovi: `lambda_market_grid`, `select_cost_aware`,
`select_p_band_ratio`, `model_use_yellow_cards`, `model_tail_factor`. Test:
`test_omega_modello_definitivo_2026_09_11.py`.

## 16. CERTIFICAZIONE CAPILLARE — matematica, logica, dati, motore (11/09/2026 sera)

Richiesta dell'utente: "rianalizza a fondo ogni riga di codice di Omega, certificazione
capillare della matematica e della logica, stato dell'arte, se manca qualcosa implementalo".
Metodo: quattro revisioni indipendenti per area (logica del servizio, matematica del
modello, SQL/dati, motore dei soldi) su OGNI riga, poi una seconda passata di test mentali
sul codice corretto. Ogni correzione ha un test (`test_omega_certificazione_2026_09_11.py`
+ aggiornamenti dei test storici). Suite: 823 verdi (omega + safe_strategy).

### 16.1 Difetti trovati e corretti (per gravità)

**CRITICI (avrebbero fatto perdere soldi in live)**
- C1 `customerOrderRef` PER EVENTO (`omega-<event_id>`): con due gambe per partita Betfair
  rifiuta il secondo ordine (DUPLICATE_CUSTOMER_ORDER_REF) e la riconciliazione del pending
  poteva agganciare l'ordine della gamba sbagliata. Ora ref PER GAMBA `omega-t<id>`
  (`omega_engine.customer_ref_for`), riconciliazione con lista di candidati (nuovo + storici
  per compatibilità; una gamba di CHIUSURA non matcha mai il ref dell'apertura).
- C3 letture PostgREST troncate a 1000 righe in silenzio (`traded_legs`, `traded_event_ids`,
  `closing_trades_for`): dopo ~10 giorni l'idempotenza per gamba si sarebbe rotta. Ora
  `_select_all` paginato per id.
- HIGH-3 settlement: chi ha chiusure lo diceva solo il marker nel meta; un crash fra invio
  del back e scrittura del meta regolava l'apertura da sola e la chiusura orfana con
  commissione DOPPIA. Ora le chiusure si leggono dal DB (`_ids_with_closings`) e la chiusura
  orfana si netta col padre (`settle_orphan_closing`).
- H1 `place_order_live` passava dal retry generico: un timeout dopo un ordine accettato
  → secondo ordine. Ora `call_mutating` (nessun retry, salvo errore di sessione PRIMA
  dell'invio).
- H2 eventi con trade MANUALI non erano più esclusi dall'automatico (v2 aveva perso il
  filtro §8): `manual_event_ids()` + esclusione in `run_once`; se la lettura fallisce,
  nessun ingresso.

**ALTI**
- HIGH-1 `legs_remaining` usava l'orologio (kickoff+minuti) senza intervallo: al 60′ di
  orologio la partita è al 45′ → gambe residue sbagliate → target per gamba sbagliato. Ora
  minuto REALE dal feed quando c'è (`minute_of`), altrimenti orologio corretto di 15′;
  0 gambe = 0 (nessun floor a 1 che nascondeva un obiettivo irraggiungibile).
- HIGH-2 `round_to_tick` arrotondava SEMPRE verso il basso: 49,9 → 48, 99 → 95 (un tick
  peggiore per il lay). Ora tick più vicino; `tick_up`/`tick_down` espliciti.
- HIGH-4 `apply_liability_cap` con `round` poteva superare il cap di un centesimo → `floor`.
- H4/M9 freschezza: la selezione accettava punteggi vecchi fino a 180 s e un book "fermo"
  bypassato dallo scanner vivo. Ora per DECIDERE: riga del feed ≤ 25 s (`DECISION_MAX_AGE_S`),
  punteggio ≤ 30 s (`SELECT_SCORE_MAX_AGE_S`); per statistiche/stime resta 180 s.
- H5/F16 fit del mercato intero ricalcolato per ogni candidato a ogni ciclo (~0,2 s l'uno):
  cache per (evento, 5′, punteggio) `_market_fit_cached`.
- H6 green-up `failed` era TERMINALE: una posizione con liability viva restava scoperta per
  sempre. Ora cooldown 5′ (`GREENUP_FAILED_COOLDOWN_S`), `logger.critical`, nuovo giro.
- H7 posizione viva senza feed: silenzio. Ora `greenup_blind` (log + CRITICAL) al 3° ciclo.
- F1/F2 il green-up decideva con la P GREZZA del modello mentre l'ingresso usa quella
  calibrata/con fattore di coda; e nel recupero (≥ 88′, ≥ 43′ per HT) il modello può dire
  0,1 % dove il mercato dice 67 %: ora `model_p` + tetto alla P implicita del back.
- F3 Poisson puro sottostima la coda (validazione: usciti/previsti 1,1–1,8): mistura
  lognormale sui λ (cv = `model_lambda_cv` 0,30, 5 nodi di Gauss-Hermite, θ comune) ≈ coda
  binomiale negativa; cv = 0 ridà il Poisson esatto.
- F4 fattore di coda a gradino (×1,3 sotto il 5 %, ×1 sopra: discontinuità e ranking
  distorto) → continuo `f = 1 + (f0−1)·p_max/(p_max+p)`.
- F5 gate di valore ignorava la commissione: ora `p < (1−c)/(L−c)` (≡ Kelly φ* > 0) e
  ranking per EV atteso con costo di copertura (`rank_by_ev`, `select_p_hedge`,
  `select_ev_kappa`).
- F7 λ pre-KO dall'1X2 con split fisso → bisezione esatta (`split_lambdas_1x2`).
- F8 dati empirici: shrinkage K 200 → 500 e limite superiore di Wilson (`p_upper`, z 1,64)
  al posto della stima puntuale: un lay solo se il risultato è raro anche nel caso
  sfavorevole dei dati; `MIN_GLOBAL_N` 200.
- F9/F10 recupero: `live_engine` ora ha 5′ di recupero (`INJURY_TIME_MIN`) e 3′ per il 1T.
- F11 fit del mercato: bracket [1/lay, 1/back] (χ² per bracket, microprice), aggregati
  casa/trasferta/pareggio nel fit, `None` sul bordo della griglia (fit non identificato).
- F12 O/U live: clamp nello spazio dei residui (0,005–3,5), non su λ pre-match.
- F13/F14 calibratore: famiglie `cs_cell`/`hts_cell` e caricamento dal path di default.

**MEDI**
- M1 `max_events` contava le GAMBE (due per partita): ora `events_today` (partite).
- M2 lettori DB: `None` su errore (mai `[]` in cache come "tabella vuota").
- M3 cache λ senza TTL: fonti di ripiego scadono dopo 15′ (una fixture abbinata dopo, un
  mercato più informativo); la fixture resta per processo.
- M4 il green-up chiamava la catena λ senza stato/parametri (niente O/U, niente mercato).
- M5 reconcile sovrascriveva il meta (`{"reconciled": …}`): perso il blocco modello e i
  runner → fuso.
- M6/M7 settlement: una `listMarketBook` per posizione → batch di 40 (`read_markets`);
  mercato sparito su posizione con chiusure → stessa macchina delle aperture nude.
- MED-3 EV del tenere al LORDO della commissione: bias verso HOLD esattamente pari a
  `greenup_ev_margin` → netto.
- MED-4 `locked_pnl` su hedge PARZIALE era il caso peggiore spacciato per bloccato → `None`
  + `worst_case`/`best_case` espliciti; UI "0 bloccato" solo a copertura completa.
- MED-5 `residual_liability` (meta `if_win`) nella liability aperta degli aggregati.
- MED-9 fill paper camminava la scala oltre il prezzo limite → `limit_price`.
- M10 `reconcile_pending`/`settle_open` non protetti in `run_once`: un DB KO spegneva
  anche il green-up → try/except per fase.
- M11 residuo di un'uscita: se il bancato è diventato irraggiungibile non si copre più.
- M12 log skip ripetuti (746 righe identiche il 10/09) → una riga per chiave ogni 10′.
- L1 backoff (0/0,5/2 s) nella conferma DB; L5 senza accessor delle chiusure non si regola.
- VOID: `results_from_payload` non deduce mai un finale da partite sospese/abbandonate.
- Gambe in `error` contano come trattate (`traded_legs`): allineato all'unique del DB —
  prima il servizio ci riprovava ogni 5 s e il DB rifiutava l'insert.

### 16.2 Decisioni prese e motivate (NON sono difetti)
- L'unique `uq_omega_trades_auto_leg` NON esclude lo stato `error`: una gamba automatica
  andata in errore (ordine reale a esito ignoto) non deve MAI essere ripiazzata. È la rete
  di sicurezza del live.
- Uscite (back di green-up) in FILL_OR_KILL con `minFillSize`: non verificato su Betfair
  reale (certificazione liquidità §13 ancora parziale) → resta FOK semplice; il residuo si
  ritenta con cooldown.
- `get_omega_aggregates` calcola "oggi" in SQL (Europe/Rome) come `day_start_utc` del
  servizio: identici salvo il secondo esatto di mezzanotte, non vale un parametro in più.
- Corner/pressione restano a moltiplicatore 1 (nessun dato per calibrare, §15.5).

### 16.3 Parametri nuovi (`omega_config`)
`model_lambda_cv` (0,30; 0 = Poisson puro), `select_k_se` (0: centro del log-pool
modello∥mercato; > 0 = P conservativa + k·SE), `select_p_hedge` (0,5), `select_ev_kappa`
(1,0). Tutti clampati.

### 16.4 Migrazione `omega_models_v4.sql` (idempotente — **verificata APPLICATA** l'11/09 sera)
Grant espliciti a `service_role`; indici parziali su `omega_trades` (posizioni aperte,
regolate, manuali, gambe); lookup empirici come due range sulla PK (UNION ALL);
`get_omega_daily` set-based; liability aperta residua e vinte/perse per segno negli aggregati e nello storico (§16.7); costruzione per minuto con `FOR UPDATE NOWAIT` (un passo
manuale risponde `busy` invece di restare appeso dietro a pg_cron), tabelle temporanee
`pg_temp.*`, `max_id` aggiornato a ogni passo. Nessuna ricostruzione necessaria: la tabella
per minuto (939.506 partite, 1.072.786 righe) resta valida.

### 16.5 Banco di validazione aggiornato
`tools/omega_validate_models.py`: modello `poisson_cv` (mistura), IC 90 % bootstrap per
PARTITA sul rapporto usciti/previsti, e metrica `lay` = la SOLA selezione che Omega farebbe
(risultato meno probabile con 1/120 ≤ P ≤ 3 %). Rapporto in `Betfair/omega/reports/`.
Esito (1.184 partite, test 474): sulla selezione che Omega farebbe, il Poisson puro esce
1,12× al 25′, 1,83× al 60′, 0,94× al 70′ il previsto (IC 90 % larghi: 5–9 uscite); il
modello di produzione (mistura cv 0,30 + fattore di coda 1,3) sta a 0,64 / 0,71 / 0,72:
PRUDENTE, com'è giusto per un lay (una perdita vale 20–50 vincite). Il calibratore
condiviso da solo (0,0 al 60′: nessuna uscita su 4,4 previste) è ancora più prudente ma
troppo poco campionato per fidarsi. Da ripetere a ogni settimana di paper con le partite
REALI tradate (banco riusabile), non solo sullo storico.

### 16.6 Cosa resta fuori (con motivo) — stato dell'arte non ancora implementato
- Catena di Markov con hazard per minuto (atlante `hazard_atlas_v2.json`): stessa
  informazione del Poisson non omogeneo già usato (`goal_timing`), guadagno atteso sulla
  coda < 5 % relativo, costo alto → dopo che il banco misura un beneficio.
- Aggiornamento bayesiano dei λ in gara (prior fixture ∥ mercato): parzialmente coperto
  da `probs_alt` + `select_k_se` (k = 0 finché il banco non stima la SE).
- Kelly frazionario sul bankroll: il sizing è per OBIETTIVO (§3); il gate di valore è già
  Kelly > 0; un cap Kelly diventa utile solo con bankroll dichiarato in UI.
- Calibrazione isotonica per famiglia: servono più campioni in coda (oggi 1.566 partite).
- Live: BLOCCATO finché la certificazione della liquidità (§13) non è completa e il paper
  non ha almeno alcuni giorni con le correzioni di oggi.

### 16.7 SECONDA PASSATA — test mentali sul codice corretto (11/09 sera, tardi)
Richiesta: "seconda passata di approfondimento su tutte le logiche, test mentali e di
ragionamento, certifica ogni funzionalità". Quattro nuove review sul codice GIÀ corretto
(ingresso, uscita/regolazione, matematica, dati/UI/operatività). Suite: 823 verdi.

**Trovato e corretto**
- 2P-F1 (CRITICO) place LIVE con eccezione DOPO l'invio → riga `error` mai più guardata: un
  lay reale vivo e invisibile (no settlement, no green-up, liability cieca). Ora la riserva
  resta `pending` con `place_exception_reconciling` (+ CRITICAL) e `reconcile_pending` la
  risolve contro Betfair per `omega-t<id>`; conta come gamba occupata finché non è libera.
- 2P-F1-bis (ALTO) `placeOrders` con `status TIMEOUT` (o nessun report) = esito IGNOTO per
  Betfair, trattato come rifiuto → un secondo back di green-up 20 s dopo → posizione
  invertita. Ora `place_order_live` SOLLEVA → riga pending in riconciliazione.
- 2P-F3 (ALTO) esito CERTO negativo (FOK ucciso, `MARKET_SUSPENDED`, paper senza fill)
  bruciava la gamba per tutta la partita (riga `error` nell'unique). Ora la riserva si
  CANCELLA e la gamba si ritenta: max 3 volte, ≥ 30 s di distanza (`_leg_retry_allowed`,
  budget in memoria per evento/gamba, in `_place_one` per entrambi i motori).
- 2P-F2 (ALTO) mercato `SUSPENDED` nel feed (gol appena visto, quote congelate) non fermava
  l'ingresso automatico: paper "a risultato noto", live rifiuto certo. Ora skip
  `market_suspended`.
- 2P-F2-uscita (ALTO) `complete` con `<` HEDGE_EPS: un residuo di 0,01 € da arrotondamento
  (5 % dei fill integrali) lasciava l'apertura `open` per sempre, con tentativi a vuoto
  ogni 20 s e CRITICAL falsi. Ora `<=` o esposizioni uguali (< 5 cent); un residuo non
  copribile (sotto la size minima) viene chiuso (`residual_dropped`), mai ritentato.
- 2P-F3-uscita (ALTO) `niente_da_chiudere` (manca il back al momento dell'uscita) era
  TERMINALE (`sent`): posizione esclusa per sempre dal green-up con liability piena. Ora
  senza prezzo opposto si ASPETTA (`prezzo_opposto_non_disponibile`) e `niente_da_chiudere`
  non consuma tentativi.
- 2P-F4-uscita (MEDIO) il green-up leggeva il feed senza tetto d'età (riga ferma + scanner
  vivo = "affidabile"): ora `GREENUP_MAX_AGE_S` 90 s, oltre = cieco (allarme).
- 2P-F5-uscita (MEDIO) chiusura orfana con una sorella già regolata: netto senza la sorella
  (±0,6–0,8 €). Ora `settle_orphan_closing(siblings=…)`.
- 2P-F6 (BASSO) ordine `cleared` con `size_settled` 0 confermava la riserva con la size
  riservata → `free`. 2P-F7 (BASSO) errore REST su un blocco di `listMarketBook` era "mercato
  sparito" → il blocco resta fuori dalla risposta.
- 2P-F4 (MEDIO) filtro di liquidità e ranking EV con la size DA TARGET invece di quella
  CAPPATA dalla liability (skip falsi `no_runner_by_model` dopo una perdita): ora
  `liability_cap` in `select_by_model`/`rank_by_ev`.
- 2P-F5 (MEDIO) un evento rotto (REST KO, payload malformato) fermava lo scan di tutti:
  ora `_scan_event_legs` per evento con `try/except` e log `scan_event_failed`.
- 2P-F6/F8 (BASSI) stesso tetto 25 s per riga del feed e punteggio; book del feed usato
  solo se fresco; log dedup per `insufficient_liquidity`/`max_open_liability`/
  `no_live_state`/`goal_stop`; cache empiriche con TTL 6 h.
- 2P-F-01 (ALTO, matematica) shrinkage→Wilson con i K=500 pseudo-conteggi come osservazioni
  certe: lega con 10 casi e 0 uscite dava 0,52 % contro 1,33 % del globale (anti-
  conservativo proprio sulle leghe minori). Ora `shrunk_upper`: K limitato a n_globale,
  larghezza di Wilson sulla varianza della media pesata → 1,26 %.
- 2P-F-02 (MEDIO, matematica) λ pre-KO con T fisso 2,6: il pareggio dell'1X2 identifica T
  (1,5/4,2/6,5 → 3,05; 1,05/15/40 → 4,5), la coda era sottostimata fino a 2,7×. Ora
  `total_goals_from_1x2` (bisezione annidata sul pareggio).
- 2P-F-03 (MEDIO) il calibratore condiviso è addestrato sulla P del modello opportunità
  della Safe Strategy, non su Omega: `model_calibration` OFF di default (la coda è corretta
  dal fattore continuo validato); famiglia dedicata quando ci saranno stati Omega.
- 2P-HIGH-1 (dati) `open_liability` della RPC sommava la liability PIENA anche dopo la
  copertura (cap `max_open_liability` che scattava presto, KPI diverso dalla tabella):
  ora residua (`if_win`) come `omega_engine.residual_liability`. 2P-MEDIUM-1: vinte/perse
  per SEGNO del P&L totale della posizione (apertura +2 con chiusura −24 era "vinta") in
  `omega_aggregates_sql` e `trading_daily_history` (vale anche per la Safe Strategy).
- 2P-MEDIUM-2 letture del servizio finestrate a 3 giorni e riusate fra scan e stats
  (prima 4 scansioni intere di `omega_trades` per ciclo, illimitate nel tempo).
- 2P-MEDIUM-3 (UI) copertura PARZIALE invisibile: ora stato `partial` con caso peggiore/
  migliore, stake coperto e rischio residuo (`if_win`). 2P-MEDIUM-4 heartbeat anche a bot
  fermo. LOW: aggregati ("Any Other…") senza "bancato non uscito", contratto `calibrated`
  booleano, 2000 trade in "mostra tutte", `updated_at` nello snapshot obiettivo.

**Lasciato (con motivo)**
- `max_liability_per_match` è PER GAMBA (1T e 2T possono sommarsi): semantica documentata,
  il cap giornaliero `max_open_liability` copre il totale.
- Fit di mercato e inversione O/U con Poisson puro mentre la griglia usa cv 0,30: la media
  è conservata, la coda risulta un po' più prudente (direzione giusta), rifinitura futura.
- `lambdas_from_market_grid` senza soglia sulla loss: incide solo con `select_k_se` > 0
  (default 0); soglia da tarare sui fit reali prima di attivarlo.
- Convenzione del minuto (cdf[m] vs cdf[m−1], ~0,5 % dei gol): da verificare sul feed IPS.
- Card "partite/operazioni" vs riepilogo tabella con una posizione di ieri viva: due
  definizioni diverse e volute (piazzate oggi vs mostrate).

## 17. CERTIFICAZIONE 11/09 sera — audit applicato, review, CONTRATTO UI (pushato `9d09c81`)

Richiesta dell'utente: applicare **per intero** l'indagine
`Betfair/AUDIT_2026-09-11_omega_safe_mike.md` (quattro revisioni indipendenti — Mike completo,
residui Omega+Safe, contratti servizio↔UI, uniformità di design — più verifiche dirette sui dati
reali del DB), poi rivedere il lavoro con **nuove review sul codice già corretto** e certificarlo
con **dati reali**. Un solo commit per i tre bot: **`9d09c81`** su master (base `1b6b151`).

Numeri delle suite (verificati, non a memoria): **Omega 453** test
(`.venv/Scripts/python -m pytest Betfair/omega -q --collect-only` → `453 tests collected`),
**tre bot 1254** (`Betfair/omega Betfair/safe_strategy Betfair/mike`; era 941 — commit message),
**frontend 1642 vitest** (era 1122) più **certificazione su dati reali 26/26**. I test NUOVI di
Omega sono 93: `test_omega_audit_2026_09_11.py` (69), `test_omega_ui_contratto_2026_09_11.py` (15),
`test_omega_cashout_feed_fermo_2026_09_11.py` (9).

> **INVARIANTE NUOVO — I9: il contratto servizio↔UI è CODICE, non buona volontà.**
> Ogni chiave della whitelist, ogni `kind` di attività, ogni `exit_kind` e ogni stato del
> green-up vive in **UN solo vocabolario**, e un test legge i SORGENTI di entrambe le parti
> (Python e TypeScript) per impedirne la deriva: `test_omega_ui_contratto_2026_09_11.py`.
> Corollario: **ogni numero mostrato al trader ha UNA provenienza dichiarata** — la RPC, oppure
> una stima del client che si dichiara stima. È la classe di errori che l'audit ha trovato più
> volte (default divergenti, badge su un `exit_kind` che nessuno scriveva, `kind` senza
> etichetta): nessuno rompe un test unitario, tutti mentono al trader.

### 17.1 Audit → fix, item per item

| item | cosa diceva l'audit | fix | dove (file:funzione) |
|---|---|---|---|
| **R3 / H-09** | `upsert_daily_goal` falliva SEMPRE con un `NameError` inghiottito (manca l'import di `datetime` a livello di modulo): lo snapshot dell'obiettivo non veniva mai scritto dal servizio | import a livello di modulo; lo snapshot scrive `{day, goal, updated_at}` una volta per giorno/valore | `omega_db.py` (import di testa) → `omega_db.upsert_daily_goal`; scrittore `omega_service._snapshot_daily_goal` (`_DAILY_GOAL_WRITTEN`) |
| **H-02** | un `pending` in riconciliazione (ordine reale a esito IGNOTO) era un normale «IN CORSO» e spariva dalla liability della RPC: il KPI ignorava un lay reale forse vivo | predicati PURI + liability esposta a parte + marker leggibile sulla riga | `omega_engine.is_reconciling`, `omega_engine.is_placed`, `omega_engine.aggregate_trades` (`reconciling_liability`); `meta.reconciling=True` + `reconciling_since` in `omega_service._place_one` (ramo eccezione) e `_manual_place`; `migrations/omega_models_v5.sql:omega_aggregates_sql` |
| **H-04** | green-up FALLITO, CIECO, residuo abbandonato, TENGO: invisibili sulla riga (chiavi lette da nessuno) | **UNA** struttura `meta.greenup` a **6 stati** + un `kind` di attività per ogni caso | `omega_service.GREENUP_STATES`, `_greenup_state_fields`, `_greenup_blind`, `_greenup_clear_blind`, `_greenup_hold`, `_greenup_residual_dropped`, `_greenup_send`; UI `lib/omega.ts:greenupBadge` |
| **H-06** | «Liability aperta» contava come rischio una PERDITA già BLOCCATA a copertura completa | a copertura COMPLETA il rischio è **0**; il bloccato va su chiavi proprie | `omega_engine.hedge_complete`, `locked_open_pnl`, `residual_liability`, `aggregate_trades` (`locked_pnl_open`, `locked_pnl_open_today`); `omega_models_v5.sql:omega_aggregates_sql` |
| **H-08** | due «operazioni oggi» e due V/P nella stessa card (KPI dalla RPC, riepilogo ricalcolato dal client); `won_today`/`lost_today` mai letti; equity «giornata» con i regolati di ieri | la giornata la dice **UNA** fonte: gli aggregati. Nuovo `live_now`; `control.stats` porta le STESSE chiavi della RPC; la UI non ricalcola più nulla | `omega_engine.aggregate_trades`; `omega_models_v5.sql` (`live_now`); `omega_service.run_once` / `_idle_stats`; `frontend/src/pages/Omega.tsx` (KPI solo dalla RPC) |
| **H-10** | `goal_snapshot=false` perso dal client: un obiettivo di RIPIEGO veniva giudicato come storico (calendario ●/○ e «centrato» falsi) | flag esplicito nella RPC e confronto `=== true` in UI; le righe senza snapshot NON entrano nel tasso di centratura | `omega_models_v5.sql:get_omega_state`; `frontend/src/lib/dailyHistory.ts:normalizeDailyRow` e `goalHitRate`; `DailyCalendar` (`goal-not-historized`) |
| **H-12** | paper via coda flumine: un ERRORE della coda diventava un **fill pieno** al prezzo della riserva (paper ≠ live, fill «a risultato noto») | `_flumine_fallback_confirm` **RIMOSSO**: quei casi sono NO-FILL espliciti, con la gamba ritentabile | `omega_service._flumine_no_fill_error` (nota di cancellazione nel sorgente), chiamata da `_poll_one_flumine_trade` / `_recover_flumine_orphan` |
| **H-13** | il budget di retry di gamba (3× a ≥30 s) NON copriva il percorso flumine (il default): un FOK ucciso bruciava la gamba per tutta la partita | marker `meta.leg_failed` sugli esiti **CERTI** negativi (nessun ordine reale esiste): `traded_legs`/`traded_event_ids` lo saltano e l'unique lo esclude | `omega_service._leg_note_certain_failure`, `_leg_retry_allowed`, `_leg_certain_failure`, `_flumine_no_fill_error`; `omega_db.traded_legs`, `traded_event_ids`; `omega_models_v5.sql` (`uq_omega_trades_auto_leg`, `uq_omega_trades_leg`) |
| **M-11** | se il `delete` della riserva falliva, in paper la riserva senza fill veniva **confermata** dal reconcile | il marker di fallimento si scrive **PRIMA** del delete: il reconcile trova una gamba già decisa e la marca `error`, non la conferma | `omega_service._leg_certain_failure`; lettura in `omega_service.reconcile_pending` |
| **M-12** | i λ di ripiego persistiti sull'evento annullavano il TTL di 15′ (una fixture abbinata dopo, o un mercato più informativo, non entravano più) | timbro del TTL sul persistito; scaduto si ritenta la catena e il ripiego stantio si usa solo come **ultima risorsa, marcata** | `omega_service._saved_event_lambdas`, `_prematch_lambdas` |
| **M-13** | posizione `open` su un mercato che non si chiude MAI: nessun allarme | allarme **una volta per riga** (`meta.stale_open_alerted`), anche sulle `hedged` (review M2) | `omega_service._alert_stale_open`, chiamato da `settle_open` e `_settle_hedged` |
| **M-14** | `reconcile_pending` azione `error` **sovrascriveva** il meta (persi il blocco modello e i runner) | il meta si **fonde**, non si sostituisce | `omega_service.reconcile_pending` (rami `paper_no_fill` e `reconcile_orphan_old`) |
| **M-19** | il cash out manuale diceva solo «Chiusura», mai «Cash out» | `exit_kind='manual'` + `exit_reason` su **apertura E chiusura**, con `(parziale)` quando resta un residuo | `omega_service._manual_cashout` + `_greenup_stamp_closing`; log `cashout_manual`; UI sotto-riga «Cash out» |
| **M-22** | l'attività «di oggi» erano le ultime 60 righe filtrate lato client | la RPC filtra sulla **giornata operativa Europe/Rome** e dichiara quante righe restano fuori | `omega_models_v5.sql:get_omega_state` (`activity`, `activity_more`, `activity_day`, indice `idx_omega_activity_ts`); UI «carica altre» |
| **H-01** | `exit_kind:'greenup'` **non esisteva** nei backend (scrivevano `profit`/`loss`): il badge «CHIUSO IN GREEN-UP» e la sotto-riga «Green-up» erano codice morto e i test certificavano un contratto **inventato** | vocabolario CHIUSO **condiviso** con la Safe Strategy; il backend è l'unico a decidere | `safe_strategy/exits.py:EXIT_KINDS` e `ui_exit_kind`; usati da `omega_service._greenup_send` e `_manual_cashout`; test `test_ogni_exit_kind_ha_un_badge` |
| **M-04** | settlement **per gamba**: l'apertura di un green-up chiuso in utile appariva «PERSO», con doppio toast | settlement **per POSIZIONE** (apertura + chiusure nettate insieme) e risultato di posizione su ogni riga | `safe_strategy/execution.py:settle_position`, `settle_group`, `settle_row`, `position_result`; chiamato da `omega_service._settle_hedged`; UI `omega-position-result` |
| **M-05** | una gamba `error` era contata e restava «in corso per sempre» | riga **TERMINALE**: `meta.error_final` + `meta.error_at`, fuori da ogni contatore di vivo | `omega_service._flumine_no_fill_error`, `_leg_certain_failure`, `reconcile_pending`; conteggi in `omega_engine.aggregate_trades` |
| **M-06** | copertura parziale senza via manuale; anteprima del cash out sull'esposizione **piena** | `meta.hedge` con frazione e residuo; la UI mostra «COPERTA x %» e il cash out chiude **solo il residuo** | `safe_strategy/execution.py:apply_hedge_state` (+ `hedge_state`, `hedge_fraction`, `remaining_liability`); UI `CashOutButton`, `omega-residual-note` |
| **L-01** | `meta.hedging` era **letto ma mai scritto** | scritto dall'unico writer dello stato di copertura | `safe_strategy/execution.py:apply_hedge_state` |
| **L-02** | ore in tabella senza fuso; commissione della tabella presa dal **parametro corrente** e non dal trade | `meta.commission` **fissata sulla riga** all'apertura e sulla gamba di chiusura; ore sempre Europe/Rome | `omega_service._place_one`, `_greenup_stamp_closing`; `safe_strategy/execution.py:close_trade`; UI `lib/format.ts:fmtTime` |
| **L-03** | «Eventi oggi» e «Target» restavano i valori dell'ultimo ciclo attivo con il bot fermo | `stats` a bot fermo: eventi/target/gambe a **ZERO** e `bot_running:false`, soldi veri e freschi, riscritte al più ogni 60 s | `omega_service._idle_stats`, `_idle_stats_due`, `IDLE_STATS_EVERY_S` |
| **L-04** | (item **Safe Strategy**, non Omega: «prec.» fuorviante, `hedged` contate come vive, chiusure orfane oltre 200 righe) | in Omega l'equivalente era già risolto dalla tabella per PARTITA: `prec.` sulle posizioni vive di giorni precedenti, `hedged` mai «vive», fino a 2000 righe in «mostra tutte» | `frontend/src/lib/omegaMatches.ts`, `components/omega/MatchTradesTable.tsx` |
| **L-05** | nel green-up i cartellini gialli non arrivavano al modello; la cache del fit di mercato memorizzava gli errori | gialli passati anche al green-up; un errore TRANSITORIO non entra in cache | `omega_service._greenup_one` / `_state_for_model`; `_market_fit_cached` |
| **L-06** | log mancanti (conferma paper, `open→hedged`, residuo abbandonato), `list_trades` non paginata, fasi 2-3 di `run_once` non protette, motore v1 senza dedup, `_LEG_RETRY` senza spurgo | pacchetto completo: `list_trades` **paginata** e ordinata per istante, `try/except` **per fase** in `run_once`, dedup anche nel motore v1, spurgo di `_LEG_RETRY` **per età** (mai un `clear()` che regala tentativi), i tre log aggiunti | `omega_db.list_trades` (+ `_select_all`, `_ts_key`); `omega_service.run_once`, `scan_and_place`, `_leg_note_certain_failure`, `reconcile_pending`, `_settle_hedged`, `_greenup_residual_dropped` |
| **M-10** (backend) | `model_use_yellow_cards` era **inerte** | il parametro spegne davvero i gialli nei tassi residui | `omega_service._state_for_model` |
| **H-07** | default UI ≠ servizio (`model_calibration:'auto'` contro `'off'`, `greenup_risk_cap` 0,10 contro 0,15) e «Salva» scriveva l'**intero** oggetto → riaccendeva il calibratore | default della UI allineati alla `_SPEC` **da test**, e «Salva» invia una **patch** | `frontend/src/lib/omega.ts:OMEGA_PARAM_DEFAULTS` / `omegaParamsPatch`; test `test_default_della_ui_uguali_a_quelli_del_servizio`, `test_clamp_e_unita_uguali` |
| **M-01 / M-02 / M-03** (UI) | 30+ `kind` senza etichetta (badge grigio con la chiave inglese, anche se `critical`); `activityLine` leggeva chiavi che il backend non scrive; etichette green-up scambiate | mappa completa `kind → etichetta italiana`, con `critical` dichiarato; riga costruita dai campi REALI del payload | `frontend/src/lib/omega.ts:OMEGA_ACTIVITY_EXTRA` + `lib/tradeStatus.ts:ACTIVITY_BASE`; test `test_ogni_kind_loggato_e_mappato_in_italiano` |
| **M-07 / M-08** (UI) | MissionCard mostrava `hedged`/`error` come «in gioco» con badge inglese; MissionPanel usava il giorno locale del browser e una seconda formula dell'obiettivo | stati dal vocabolario condiviso; giornata **Europe/Rome** e una sola formula | `components/omega/MissionCard.tsx`, `MissionPanel.tsx` |
| **M-09** (UI) | clamp e unità della UI divergenti dalla `_SPEC` (`greenup_ev_margin` in EUR etichettato «0-1») | `min`/`max` della UI **uguali** ai clamp del servizio, unità dichiarate, clamp **visibile** | `lib/omega.ts:OMEGA_PARAM_GROUPS`; `components/trading/ParamsSheetBase.tsx:clampField` |
| **M-17 / M-18 / H-11** (storico) | finestra > 400 giorni → errore; DayDetail sommava righe attribuite dal calendario a un altro giorno | finestra clampata a 400 giorni con banner; il dettaglio somma **solo** gli attribuiti | `components/trading/TradingHistory.tsx` (`MAX_HISTORY_DAYS`), `lib/dailyHistory.ts:summarizeDayTrades`, `DayDetail.tsx` |
| **§5 DESIGN** (20 mancanze) | formati monetari misti, quote con punto, stati in inglese, etichette divergenti, Omega senza banner modalità né salute del servizio, tre pannelli parametri diversi… | **design system unico** delle tre sezioni, con documento normativo e due test-guardia | `frontend/src/components/trading/DESIGN_SYSTEM.md`; `lib/format.ts`, `lib/tradeStatus.ts`, `lib/toasts.ts`; `components/trading/*`; `designGuard.test.ts` (statico sui sorgenti) e `designSystem.test.tsx` |

### 17.2 Le review indipendenti SUL CODICE GIÀ CORRETTO

Dopo l'audit sono state fatte nuove review (ingresso, uscita, matematica, dati/UI) sul codice
appena modificato. Ogni finding ha un test in `test_omega_audit_2026_09_11.py`
(`test_rev_*`).

**ALTI**
- **H1 — la perdita BLOCCATA era invisibile alle guardie.** Con `residual_liability = 0` a
  copertura completa (H-06) il rischio spariva dal KPI **e dalle decisioni**: dieci green-up
  chiusi a −22 € davano `realized_today = 0`, lo stop-loss giornaliero non scattava mai e il cap
  `max_open_liability` si liberava a ogni uscita — il bot si riesponeva coi soldi appena persi.
  Ora le guardie lavorano su due grandezze dedicate:
  `realized_effective = realized_today + min(0, locked_pnl_open_today)` e
  `open_liability_effective = open_liability + max(0, −locked_pnl_open)` — **mai anticipare un
  utile, sempre anticipare una perdita** (un bloccato positivo NON si somma).
  `omega_engine.realized_effective` / `open_liability_effective`, usate da
  `omega_service.scan_and_place_legs`, `scan_and_place`, `_size_and_place`, `run_once`.
  Test: `test_rev_h1_*` (incluso «bloccato di ieri non tocca lo stop di oggi»).
- **H2 — due writer di `meta.hedge`/`meta.hedging`** con semantiche diverse: due UPDATE per ciclo
  per sempre e un `hedging` che oscillava. `_stamp_hedge_meta` è stato **RIMOSSO**: writer unico e
  **idempotente** `safe_strategy/execution.py:apply_hedge_state` (nota di cancellazione nel
  sorgente di `omega_service.py`). Test `test_rev_h2_un_solo_writer_dello_stato_hedge`,
  `test_rev_h2_stato_hedge_idempotente_nessuna_scrittura_a_vuoto`.
- **H3 — `exit_kind='greenup'` anche su una chiusura in PERDITA.** Il badge «CHIUSO IN GREEN-UP»
  su −22 € è una bugia al trader. Ora `greenup` **solo** se la chiusura è INTEGRALE **e** il P&L
  bloccato è ≥ 0; altrimenti `loss` (perdita bloccata) o `profit` (regola di profitto ma chiusura
  parziale / bloccato ignoto). `safe_strategy/exits.py:ui_exit_kind`, applicato in
  `omega_service._greenup_send`. Test `test_rev_h3_chiusura_in_perdita_e_exit_kind_loss`,
  `test_rev_h3_take_profit_integrale_e_greenup_vero`.
- **H4 — il budget dei tentativi di gamba stava SOLO in memoria di processo.** Dopo l'esclusione
  di `meta.leg_failed` dall'unique (v5) un riavvio del servizio azzerava il contatore e la stessa
  gamba poteva essere ritentata all'infinito. Ora il budget viene **anche dal DB**:
  `omega_db.failed_legs` (query FILTRATA su `meta->>leg_failed`, indice
  `idx_omega_trades_leg_failed`), caricata una volta per ciclo da `omega_service.load_failed_legs`;
  `_leg_attempts` prende il **massimo** fra DB e memoria — **mai la somma**: sono due viste dello
  STESSO fallimento. Test `test_rev_h4_*`.

**MEDI**
- **M1** cap `max_events` contato sulle **gambe** invece che sulle partite distinte →
  `events_today` (`omega_service.scan_and_place_legs`).
- **M2** l'allarme «mercato che non si chiude mai» valeva solo sulle posizioni nude: anche una
  `hedged` deve allarmare (il P&L bloccato si incassa solo al settlement) →
  `_settle_hedged` → `_alert_stale_open`.
- **M3** sul cash out **parziale** `locked_pnl` è `None` (non c'è nulla di bloccato) e
  `exit_profit` risultava sempre `False`: ora il segno viene dal valore **pianificato**
  (`planned_lock`) o dal **caso peggiore** (`worst_case`) — `omega_service._manual_cashout`.
- **M4** parziale non riconosciuto quando l'utente chiede TUTTO ma la **liquidità** cappa il fill:
  ora `partial` anche con `residual_size > HEDGE_EPS` (`_manual_cashout`).
- **M5** `_leg_certain_failure` **sostituiva** la colonna `meta` (persi `model`, `runners`,
  `requested_size`): ora merge col meta corrente (o rilettura via `get_trade`).
- **M6** a bot fermo erano una RPC + una UPDATE **ogni 5 s per ore**: ora
  `_idle_stats_due` (`IDLE_STATS_EVERY_S = 60`, o subito al cambio di stato).
- **M7** uscendo dallo stato CIECO lo stato tornava sempre `pending`: una posizione già chiusa o
  con residuo abbandonato risultava «in copertura» per il resto della partita. Ora
  `_greenup_clear_blind` **ricostruisce dai fatti** `failed` / `residual_dropped` / `done` /
  `pending` / `hold`, o cancella del tutto la chiave.
- **M8** i rami d'uscita di `run_once` facevano `return` **prima** del `set_control`: proprio nel
  caso da coprire la UI dava il servizio per morto e mostrava i numeri dell'ultimo ciclo buono.
  Ora `_degraded_heartbeat` scrive heartbeat + stats con `degraded=<motivo>`
  (`traded_ids_failed`, `aggregates_failed`, `manual_ids_failed`, `mission_ids_failed`) e la UI
  mostra «⚠ CICLO DEGRADATO».
- **M12** 746 righe di skip identiche in un giorno → `_log_dedup` applicato **anche** al motore v1.
- **M13** `closing_trades_for` con URL troppo lunga / troncata → blocchi di 200 id
  (`omega_db.closing_trades_for`).

**BASSI**
- **L1** il secondo unique parziale (`uq_omega_trades_leg`) bloccava comunque la gamba bruciata
  (una riga con `leg_failed` può essere `error` **oppure**, se il delete è fallito, ancora
  `pending`): ora porta la **stessa** esclusione `meta->>'leg_failed' <> 'true'`
  (`omega_models_v5.sql`).
- **L2** `list_trades` ordinava per **stringa** (`…Z` contro `…+00:00`, fusi diversi, riga senza
  data in testa) → `omega_db._ts_key`, righe senza data **in coda**.
- **L3/L4** il fallback senza RPC non esponeva le stesse chiavi: ora senza `day_start` i campi
  `_today` cadono sul CUMULATO e l'insieme delle chiavi è **sempre lo stesso**
  (`omega_engine.aggregate_trades`).
- **L5** (a) una riga `error` con `settled_at` sembrava **regolata** in ogni finestra «regolati»:
  ora scrive `meta.error_at`, **non** `settled_at`; (b) `_settle_hedged` senza l'accessor
  `closing_trades_for` regolava una posizione coperta **come se fosse nuda** → `return 0`.

> Nota di lettura del codice: due marker omonimi nei sorgenti appartengono a review
> **precedenti** (§16), non a questa tornata: «review M9/H4» sul tetto duro
> `DECISION_MAX_AGE_S`, e «§8, review H2» sull'esclusione degli eventi manuali.

### 17.3 CONTRATTO UI — `get_omega_state(p_activity_limit)`

Definita in `migrations/omega_models_v5.sql`. Owner-only (`betfair_live_is_owner()`),
`REVOKE ALL FROM public, anon` + `GRANT EXECUTE TO authenticated, service_role`.
Limite attività clampato a **1…300** (default 50). **Sette** chiavi di primo livello:

| chiave | contenuto |
|---|---|
| `control` | la riga singleton `omega_control` intera: `id`, `status`, `mode`, `daily_goal`, `params`, `stats`, `error`, `started_at`, `stopped_at`, `heartbeat_at`, `updated_at`, `created_at` |
| `aggregates` | `omega_aggregates_sql()` (sotto) |
| `activity` | righe `omega_activity` (`id`, `ts`, `kind`, `payload`) con `ts ≥` mezzanotte **Europe/Rome**, `ORDER BY ts DESC LIMIT` (M-22) |
| `activity_more` | quante righe **di oggi** restano fuori dal limite → bottone «carica altre» |
| `activity_day` | la data (Europe/Rome) a cui `activity` si riferisce |
| `goal_today` | obiettivo del giorno: `omega_daily_goal.goal` se esiste, altrimenti `omega_control.daily_goal` |
| `goal_snapshot` | `true` **solo** se `goal_today` è lo snapshot storicizzato (H-10); `false` = ripiego dichiarato |

**`omega_aggregates_sql()`** (owner-only via `get_omega_aggregates()`; grant diretto solo a
`service_role`) — **17 chiavi**, e sono le SOLE che decidono la giornata (H-08):

| chiave | significato |
|---|---|
| `realized_profit` | P&L realizzato CUMULATIVO a vita (aperture + chiusure) |
| `realized_today` | realizzato attribuito a oggi per il giorno di **PIAZZAMENTO dell'apertura** (§14: le chiusure ereditano il giorno del padre) |
| `open_liability` | rischio **VIVO**: 0 a copertura completa, `max(0, −if_win)` a copertura parziale, liability piena se nuda; nessun filtro di giorno |
| `locked_pnl_open` | P&L **già bloccato** sulle posizioni vive a copertura COMPLETA: non è più rischio e non è ancora realizzato (H-06) |
| `locked_pnl_open_today` | la quota di `locked_pnl_open` delle posizioni **piazzate oggi**: è quella che pesa su stop-loss e target (review H1) |
| `reconciling_liability` | quanto di `open_liability` è un ordine reale a esito **IGNOTO** (H-02): sottoinsieme informativo, già incluso |
| `matches_traded` / `matches_traded_today` | posizioni (aperture) con esito o vive, totali / di oggi |
| `legs_today` | **gambe** di oggi (esclusi `error` e le riserve mai piazzate) |
| `events_today` | **PARTITE** distinte di oggi — il cap `max_events` è per partita (review M1) |
| `matches_open` | posizioni vive adesso |
| `live_now` | **partite** distinte con una posizione viva ADESSO, senza giorno: il rischio vivo non ha giorno (H-08) |
| `matches_won` / `matches_lost` | esito per **SEGNO** del P&L di POSIZIONE (apertura + chiusure), non per `status` |
| `won_today` / `lost_today` | gli stessi, sulle posizioni piazzate oggi |

Criteri condivisi fra SQL e Python (`omega_engine`): `is_placed` = `bet_id` **o**
`meta.flumine_client_ref` **o** `reconciling`; `reconciling` = `meta.reconciling` **o**
`meta.reason = 'place_exception_reconciling'`; `hedge_complete` = `meta.locked_pnl` numerico **e**
`meta.residual_size ≤ 0,01`. Le letture dal `meta` sono difensive (regex numerica): un valore
scritto a mano non fa fallire l'RPC. Il percorso PURO `omega_engine.aggregate_trades` produce le
stesse 17 chiavi più `settled_count`, `total_count`, `events_traded`, ed è il **fallback** quando
l'RPC non c'è.

### 17.4 CONTRATTO UI — le chiavi `meta` di un trade

**Uscite (vocabolario CHIUSO, `safe_strategy/exits.py:EXIT_KINDS`)**:
`greenup | profit | loss | time | red_card | forced | manual | other`. Le decide
`exits.ui_exit_kind(kind, locked=…, manual=…, forced=…, integral=…)` — `manual` per il cash out
dell'operatore; `forced` per le uscite obbligatorie; `greenup` **solo** se regola di profitto
**+** chiusura INTEGRALE **+** bloccato ≥ 0; `loss`/`red_card` sé stessi; tutto il resto `other`.
Su apertura **E** chiusura stanno `meta.exit_kind`, `meta.exit_reason` (testo breve italiano) e
`meta.exit_profit` (bool). La REGOLA che ha deciso resta in `meta.greenup.kind` (`profit|loss`).

**`meta.greenup`** (UNA struttura, H-04) — blocco di stato da
`omega_service._greenup_state_fields`: `state`, `reason` (italiano, ≤180), `at`, `next_retry_at`,
`attempts`, `p_lose`, `ev`. `state` ∈ **`pending`** (uscita inviata, residuo da coprire) ·
**`done`** (coperta del tutto) · **`hold`** (TENGO) · **`failed`** (tentativi esauriti: posizione
SCOPERTA, con `next_retry_at`) · **`blind`** (nessun feed) · **`residual_dropped`** (residuo non
copribile o non più necessario). Chiavi operative conservate: `trigger`, `kind`, `ts`, `minute`,
`score`, `laid_score`, `sent`, `failed`, `failed_ts`, `rounds`, `last_attempt_ts`,
`closing_trade_id`, `price`, `size`, `residual_after`, `pending_fill`, `residual_dropped`, `note`,
`why`, `p_source`, `locked_pnl`, `last_error`, `detail`, `exit_kind`.

**`meta.greenup_hold`** (decisione «tengo» per la UI): `trigger`, `reason`, `p_lose`, `p_source`,
`locked_pnl`, `ev_hold`, `minute`, `score`, `laid_score`, `ts`. Riscritta al cambio di motivo o al
più ogni 30 s; **rimossa** quando l'uscita viene inviata.

**`meta.hedge`** e **`meta.hedging`** — UN solo writer: `safe_strategy/execution.py:apply_hedge_state`
(review H2). `hedge` = `{fraction, remaining_liability, hedged_size, residual_size, complete}`;
`hedging = true` significa **una gamba di chiusura È IN VOLO** — e in quel caso il rischio da
mostrare resta la liability **PIENA** (nulla è ancora coperto). Insieme scrive `hedged_size`,
`residual_size`, `locked_pnl` (**solo** a copertura completa, altrimenti `None`), `worst_case`,
`best_case`, `if_win`, `if_lose`, `hedge_pending_ids`, `closing_ids`, `closing_trade_id`,
`closing_status`, `hedge_synced_at`.

**Riconciliazione**: `meta.reconciling = true` + `meta.reconciling_since` (ISO) — ordine reale a
esito IGNOTO: conta come piazzato, come liability e come gamba occupata finché la
riconciliazione non decide (H-02).

**Esito CERTO negativo**: `meta.leg_failed = true` (nessun ordine reale è mai esistito: FOK
ucciso, paper senza fill, richiesta di coda mai creata) + `meta.error_final = true` +
`meta.error_at` (+ `no_fill_at` sul percorso flumine). **Le righe `error` NON hanno più
`settled_at`** (review L5): una riga in errore non è una regolazione e non deve comparire come
tale in nessuna finestra «regolati» — `settled_at` sopravvive solo nel settlement vero
(`omega_service.settle_open`) e nel void di un mercato sparito (`_maybe_void_orphan`).
Eccezione dichiarata: lo strato condiviso `execution.close_trade` lo scrive ancora su una **gamba
di chiusura** andata in errore (convenzione Safe).

**Commissione**: `meta.commission` **fissata sulla riga** al piazzamento e ricopiata sulla gamba
di chiusura (L-02): la tabella non usa più il parametro corrente.

**Settlement per POSIZIONE** (M-04): `meta.position_id`, `meta.position_pnl`,
`meta.position_result` ∈ `won | lost | flat | void` (`execution.position_result`; `void` lo scrive
`settle_position` su mercato annullato), scritti con **merge** sulla riga corrente per non
perdere `hedge`/`exit_*`.

**Altre chiavi** già in uso e confermate: `phase` (`reserved` / `flumine_wait`),
`requested_size`, `runners` (nomi dei runner a punteggio esatto), `model` (blocco di audit del
modello), `result_ht` / `result_ft` (risultati REALI, idempotenti: mai sovrascritti),
`flumine_client_ref` / `flumine_request_id` / `flumine_enqueued_at`, `fill`
(`paper_at_price` / `flumine_paper` / `flumine_live`), `below_min_stake`, `market_gone_since`,
`orphan_alerted`, `stale_open_alerted`, `cashout` / `cashout_at`, `closes_trade_id`,
`exit_track` (tracciamento gol/rossi dello strato uscite).

### 17.5 CONTRATTO UI — i `kind` di attività (elenco COMPLETO)

Scrittore unico `omega_db.log(kind, payload)`; anti-rumore `omega_service._log_dedup` (una riga
per chiave ogni 10′). **Ogni** kind ha un'etichetta italiana esplicita in
`frontend/src/lib/omega.ts:OMEGA_ACTIVITY_EXTRA` (o in `lib/tradeStatus.ts:ACTIVITY_BASE`), con
`critical: true` dove il trader **deve** accorgersene — e un test lo impedisce di dimenticarlo.

**Ingressi e piazzamento** — `place` (event_id, trade_id, runner, price, size, liability, target,
minute, mode) · `skip` (event_id, reason, + leg/minute/score/trade_id/attempt/max/avail/
impegnato/liability/cap/err) · `size_reduced` (event_id, requested, available, size) ·
`goal_stop` (realized, goal) · `loss_stop` (realized, cap) · `confirm_failed` (event_id,
trade_id, bet_id, size, price, liability, mode, critical) · `place_reconciling` (event_id,
trade_id, critical, liability, price, size, leg, err; manuale: + origin, side) ·
`place_exception` (trade_id, mode, err) · `manual_place` (trade_id, event_id, side, price, size,
mode, flumine_request_id) · `manual_place_exception` (trade_id, event_id, err) ·
`paper_fill_fallback` / `live_fok_fallback` (event_id, trade_id, reason).

**Coda flumine** — `flumine_enqueue` (trade_id, event_id, request_id, price, size, mode) ·
`flumine_fill` (trade_id, event_id, size, price, mode, request_id) · `flumine_no_fill` (trade_id,
event_id, reason, leg, attempt, max, max_attempts, mode) · `flumine_cancel` (trade_id, bet_id,
cancel_request_id) · `flumine_cancel_timeout` (trade_id, request_id) · `flumine_recovered`
(trade_id, request_id) · `flumine_live_freed` (trade_id, event_id, reason) ·
`flumine_live_orphan` (trade_id, event_id, request_id, bet_id) · `flumine_poll_error` (trade_id,
err).

**Riconciliazione e sorveglianza** — `reconciled_open` (trade_id, event_id, bet_id) ·
`reconciled_free` (trade_id, event_id) · `reconciled_paper` (trade_id, event_id, price, size) ·
`reconciled_error` (trade_id, event_id, reason) · `reconcile_error` (reason | trade_id, err) ·
`orphan_live_alert` (trade_id, event_id, market_id, bet_id) · `stale_open_alert` (trade_id,
event_id, market_id, critical, hours, liability, mode).

**Green-up e chiusure** — `greenup` (trade_id, event_id, trigger, minute, score, laid_score,
distance, p_lose, p_source, locked_pnl, ev_hold, decision, back_price, lay_price, entry_price,
side, price, size, closing_trade_id, exit_kind, kind, state, exit_reason, why, pending_fill,
attempt, residual_before, residual_after, hedged_size, mode) · `greenup_hold` (… msg, p_lose,
p_source, locked_pnl, ev_hold, decision, hold_profit, loss_if_lose, back_price, lay_price) ·
`greenup_wait` (trade_id, event_id, trigger, wait) · `greenup_retry` (reason, trade_id, event_id,
trigger, attempts, err, detail, residual) · `greenup_failed` (trade_id, event_id, attempts,
residual, critical, state, liability, next_retry_at, retry_in_s, last_error) ·
`greenup_residual_dropped` (trade_id, event_id, state, reason, residual, trigger, attempts) ·
`greenup_blind` (trade_id, event_id, liability, cycles, critical, state) · `cashout` (trade_id,
closing_trade_id, side, price, size, locked_pnl, planned_lock, hedged_size, residual_size, mode,
status) · `cashout_manual` (trade_id, event_id, closing_trade_id, exit_kind, exit_reason,
fraction, amount, partial, price, size, locked_pnl, planned_lock, residual_size, mode) ·
`cashout_error` (trade_id, closing_trade_id, reason).

**Regolamento** — `settle` (trade_id, event_id, status, pnl, runner; dallo strato condiviso anche
closes_trade_id, position_id, position_pnl, position_result, selection) · `hedged` (trade_id,
event_id, locked_pnl, hedged_size, legs, runner) · `settle_hedged` (trade_id, event_id, status,
pnl, legs, runner) · `settle_position` (trade_id, event_id, position_pnl, position_result, legs,
commission) · `settle_wait` (trade_id, reason, pending_closing_ids) · `settle_orphan` (trade_id,
event_id, reason, mode) · `settle_orphan_closing` (trade_id, parent_id, pnl) · `settle_error`
(trade_id | reason, err).

**Modello, missioni, ciclo** — `model_lambda_market` / `model_lambda_live` (event_id, minute,
score, lambda_pre, + fit o dati live) · `mission_scores_error` (err) · `mission_error` (event_id,
err) · `error` (reason, err, + event_id/trade_id/attempts/residual/critical/retry_in_s) ·
`stop` (payload vuoto).

I `reason` dei kind `skip`/`error` sono anch'essi un vocabolario: `already_reserved`,
`aggregates_failed`, `book_error`, `catalogue_error`, `closings_read_failed`, `cycle_exception`,
`fetch_failed`, `flumine_poll_failed`, `greenup_attempts_exhausted`, `greenup_candidates_failed`,
`greenup_failed`, `greenup_phase_failed`, `hedged_read_failed`, `insufficient_liquidity`,
`list_events_failed`, `live_not_matched`, `manual_failed`, `manual_ids_failed`,
`max_open_liability`, `mission_ids_failed`, `missions_failed`, `no_correct_score_market`,
`no_legs_remaining`, `no_live_state`, `no_market`, `no_runner_in_range`, `no_model_lambdas`,
`market_suspended`, `place_exception_reconciling`, `reconcile_orphan_old`,
`reconcile_phase_failed`, `request_missing`, `reserve_no_id`, `results_phase_failed`,
`results_read_failed`, `scan_event_failed`, `scan_phase_failed`, `settle_phase_failed`,
`target_zero_goal_reached`, `traded_ids_failed`.

### 17.6 CONTRATTO UI — `omega_control.stats`

Scritte da `omega_service.run_once` (bot vivo) e `omega_service._idle_stats` (bot fermo), con
`_degraded_heartbeat` che aggiunge `degraded`. Sono la **fotografia** del servizio e portano le
STESSE chiavi degli aggregati (H-08): `events_total`, `matches_traded`, `matches_traded_today`,
`matches_open`, `realized_profit`, `realized_today`, `open_liability`, `locked_pnl_open`,
`locked_pnl_open_today`, **`realized_effective`**, **`open_liability_effective`**,
`reconciling_liability`, `legs_today`, `events_today`, `won_today`, `lost_today`, `live_now`,
`matches_remaining`, `legs_remaining`, `target_match`, `target_leg`, `goal`, `goal_pct`,
**`bot_running`**, `last_cycle` (+ **`degraded`** solo nel battito degradato, con
`bot_running=true`).

A bot fermo `_idle_stats` azzera `events_total`, `matches_remaining`, `legs_remaining`,
`target_match`, `target_leg` e mette `bot_running=false` (L-03) tenendo veri e freschi i numeri
dei SOLDI (settlement e green-up girano comunque): **la UI non mostra più per ore i numeri di un
bot che non stava lavorando.** `realized_effective` e `open_liability_effective` non esistono nel
SQL: sono i numeri che il bot **USA** per decidere e arrivano alla UI solo da qui.

### 17.7 Cash out manuale — tetto DURO di 20 s sul feed

`CASHOUT_FEED_MAX_AGE_S = 20.0` (`omega_service.py`) è lo **stesso** numero che spegne il bottone
in dashboard (`MatchTradesTable.FEED_STALE_S`), e un test certifica la parità
(`test_omega_cashout_feed_fermo_2026_09_11.py`). Sequenza in
`omega_service._cashout_prices`:

1. riga del FEED UNICO solo se **≤ 20 s** (`_cs_from_feed(..., max_age=CASHOUT_FEED_MAX_AGE_S)` →
   `_feed_row(hard_max_age=…)`): tetto **duro**, nessun bypass «scanner vivo» — un book fermo da
   25 s non è un book;
2. altrimenti **book REST** (`market.read_book`), valido solo se il mercato è `OPEN`;
3. nulla di leggibile → `_manual_cashout` ritorna **`{"error": "prezzi_non_disponibili"}`**:
   nessuna riga di chiusura, nessun log `cashout_manual`. Lo stesso motivo lo riusa il green-up
   automatico (`_greenup_wait`).

Il cash out eseguito scrive `exit_kind = 'manual'` ed `exit_reason =
«Cash out manuale richiesto dall'operatore»` su **apertura** (`db.update_trade`) **e** su gamba di
chiusura (`_greenup_stamp_closing`), con **«(parziale)»** nel motivo quando `fraction < 1`,
`amount` è indicato **oppure** la liquidità ha lasciato un residuo (review M4). Il segno
(`exit_profit`) viene da `locked_pnl` → `planned_lock` → `worst_case` (review M3): sul parziale
non si spaccia un caso peggiore per «bloccato».

### 17.8 La dashboard `/omega` come è ORA

> Supera la descrizione del §8 («equity curve, barra obiettivo, lista trade live, popup incassi,
> pannello parametri, START/STOP») e le note del §13.1 sulla tabella «illeggibile».
> Documento **normativo**: `frontend/src/components/trading/DESIGN_SYSTEM.md` — le tre sezioni
> (Omega, Safe Strategy, Mike) hanno la stessa struttura, le stesse parole, gli stessi formati.
> Regola d'oro: *lo stesso concetto ha sempre la stessa parola, lo stesso colore e lo stesso
> formato*. Due test-guardia: `designGuard.test.ts` (statico: legge i sorgenti e vieta formatter
> locali, `toFixed`, `€${…}`, stati in inglese, mappe di etichette duplicate, i sinonimi
> «Capitale a rischio»/«Cash-out») e `designSystem.test.tsx` (rendering di tutti i condivisi).

**Struttura unica di pagina** (`pages/Omega.tsx`):
`PageShell` → `BotHeader` (sticky, misura `navH`) → `ModeBanner` → `DayBar` → `KpiRow`/`StatTile`
→ `Tabs` con `TabsList` **sticky** a `top: navH` → footer. Tab, naming ed emoji sono parte del
contratto: **`🎯 Missione · ⚙️ Automatico · ✋ Manuale · 📅 Storico`**.

- **BotHeader**: link «AI TERMINAL» → `/select-sport`, simbolo `Ω` + nome, badge di stato
  (`INATTIVO / IN CORSA / IN ARRESTO / FERMO / ERRORE`), `ServiceHealthChip`, `ModeToggle`
  (`aria-pressed`), pannello parametri, `Avvia`/`Ferma`. Badge **«IN CORSA · SENZA BATTITO»**
  (rosso) quando lo stato è `running` ma `heartbeat_at` è più vecchio di **45 s** o assente, con
  il rimedio nel `title` («il servizio non batte da …: riavvia l'app desktop»). Il chip di salute
  mostra feed (`feed vivo (3 s)` / `feed FERMO da …` / `feed: nessun dato`, soglia 45 s), battito
  del servizio, `⚡ STREAM n` / `REST`, e **«⚠ CICLO DEGRADATO: <motivo>»** da `stats.degraded`
  (review M8) — un ciclo degradato non è un servizio morto, e si distingue.
- **ModeBanner**: `MODALITÀ PAPER` (verde) — «simulazione fedele: coda, liquidità, betDelay e
  protezioni identiche al live, nessun denaro reale»; `MODALITÀ LIVE` (rosso, `role="alert"`) —
  «Omega piazza **lay reali** sul Correct Score con **soldi veri**». Il passaggio a LIVE passa
  SEMPRE da `LiveConfirmDialog` («Passare a LIVE (soldi veri)?») che cita il §9.
- **DayBar** «Giornata operativa» (Europe/Rome): `Obiettivo di oggi` · `partite` (`events_today`)
  · `operazioni` (`legs_today`) · `nV nP` (`won_today`/`lost_today`) · `n vive` (`live_now`) ·
  `realizzato oggi` (`realized_today`) · `resta` **oppure** `obiettivo CENTRATO (… oltre)` ·
  `Liability aperta` · `P&L bloccato`. Barra con `role="progressbar"`. La nota dichiara la
  provenienza: «numeri dalla RPC (giornata Europe/Rome)…» con `goal_snapshot=true`, altrimenti
  «obiettivo non ancora storicizzato per oggi: è quello corrente del servizio» (H-10).
- **KPI (solo dalla RPC, H-08)**: `P&L oggi` · `Target / operazione` (da `stats`, con
  «bot fermo: nessun target in corso» quando `bot_running=false`) · `Eventi in finestra` ·
  `Operazioni oggi` (con V/P/vive nel sottotitolo) · `Liability aperta` · `P&L bloccato` ·
  `In verifica su Betfair` (rosso se > 0).
- **Tabella partite** (`components/omega/MatchTradesTable.tsx`, logica pura
  `lib/omegaMatches.ts`): **UNA riga = UNA partita**, colonne
  `Ora` (Roma, `prec.` per le vive di giorni precedenti) · `Partita` (punteggio LIVE + freschezza
  del feed) · `1° tempo` · `Risultato 1T` · `2° tempo` · `Risultato 2T` · `P&L partita`
  (`regolato` / `n/m decise` / `bloccato` / `in corso`, `· rischio …`, `· di cui … in verifica`).
  Ogni cella di gamba porta lato (BACK `sky` / LAY `rose`), runner bancato @quota d'ingresso,
  stake, **rischio** (il residuo, se la copertura è parziale), minuto e punteggio d'ingresso,
  **P(perdita)** del modello con la P implicita del mercato accanto (e nel tooltip grezza vs
  calibrata, fonte dei λ, dati storici, costo di copertura), e — se la partita è viva — la riga
  **quote LIVE** (`ora LAY … / BACK …`), la **freschezza** (`feed 3 s` / **`FEED FERMO da 45 s`**
  / **`FEED ASSENTE`**, tetto **20 s**) e **«se chiudo ora … netti»** calcolato con la
  commissione **fissata sulla riga** (L-02), oppure «chiusura non disponibile».
  Le gambe di chiusura sono annidate sotto l'apertura (`↳ Green-up · BACK 24,24 € @4,90` /
  `↳ Cash out` / `↳ Chiusura a mercato`, badge `parziale` se la liquidità ha cappato il fill).
  Il risultato reale dice **`bancato USCITO`** (rosso) o **`bancato non uscito`** (verde), e per
  gli aggregati «Any Other…» non dice nulla.
- **Stati in italiano** (una sola mappa, `lib/tradeStatus.ts`; precedenza esito certo > terminale
  > riconciliazione > stato DB): **IN CORSO** (`pending`) · **APERTO** (`open`) · **CHIUSO**
  (`hedged` senza `exit_kind`) · **VINTO** · **PERSO** · **VOID** · **ERRORE** (anche per uno
  stato ignoto: mai una cella muta) · **IN VERIFICA SU BETFAIR** (`pending` + `meta.reconciling`,
  H-02) · **ERRORE (definitivo)** (`meta.error_final` / `leg_failed` / `error_at`, con
  «nessun ordine reale · <motivo> · ERRORE alle HH:MM» — l'istante viene da `meta.error_at`, non
  da `settled_at`). Sovrascritture sulle chiusure: **CHIUSO IN GREEN-UP** (`exit_kind='greenup'`)
  · **CASH OUT MANUALE** (`manual`) · **CHIUSO IN PERDITA** (`loss`) · **CHIUSO IN UTILE**
  (`profit`) · **CHIUSO A MERCATO** (solo `time|forced|red_card|other`: **mai inventato** senza
  `exit_kind`) · **`COPERTA 40 % (restano 120,00 €)`** sulla copertura parziale (M-06).
  Più il riquadro `posizione in utile / in perdita / in pari …` dal P&L di POSIZIONE (M-04).
- **Badge green-up** per i 6 stati (`lib/omega.ts:greenupBadge`): `GREEN-UP in attesa` ·
  `TENGO · P(perdita) 12,0 % · EV −12,10 €` · `GREEN-UP fallito, ritento alle 21:07` ·
  `GREEN-UP CIECO (senza feed)` · `residuo abbandonato` · `GREEN-UP fatto`, con motivo,
  tentativi e ora nel tooltip.
- **Cash out** (`components/trading/CashOutButton.tsx`): solo su una gamba LAY `open`/`pending`
  non in riconciliazione e non terminale; l'esposizione è il **RESIDUO** se la copertura è
  parziale («residuo scoperto …: il cash out chiude SOLO quello»); **spento** se il feed è fermo
  («un cash out su prezzi vecchi si esegue a un prezzo che non hai visto»); frazioni rapide e
  importo libero; in LIVE serve un **secondo click** entro 10 s, che decade a ogni cambio di
  prezzo o importo.
- **Attività del servizio**: `ActivityFeed` con le etichette italiane del §17.5, righe `critical`
  in rosso e marcate, filtro per partita (`aria-pressed`), ora di Roma, vuoto dichiarato
  («nessuna attività oggi»), e **«carica altre (n)»** da `activity_more` (+120 righe per volta);
  la card dichiara `· giornata <data>` da `activity_day`.
- **Manuale** (`components/omega/ManualPanel.tsx`, ora **testato**: 19 test in
  `ManualPanel.test.tsx`): quattro passi (evento → mercato → quote → ordine) con guardie
  money-critical **certificate dai test** — il payload porta il `selection_id` REALE del runner
  scelto (mai l'indice di riga), `size` **XOR** `target`, conferma obbligatoria in LIVE, bottone
  **spento** con book più vecchio di 20 s, «Liability aperta ≈» solo in LAY, esiti della coda in
  italiano (`IN CODA / IN CORSO / ESEGUITA / FALLITA`, e «STATO SCONOSCIUTO» dichiarato).
- **Parametri** (`components/trading/ParamsSheetBase.tsx`, spec-driven): i valori mostrati sono
  quelli **del SERVIZIO** (`control.params`), lo sheet non sovrascrive l'editing in corso, i
  fuori-range sono **clampati e dichiarati** (`clampato a 100 (ammesso 0,50 … 100)`), un solo
  bottone `Salva parametri` più `Default`. **«Salva» invia una PATCH**
  (`lib/omega.ts:omegaParamsPatch`): parte dai parametri del servizio e aggiunge solo ciò che
  l'utente ha davvero cambiato — un default della UI non può più sovrascrivere il valore vivo
  (H-07). L'obiettivo (`__daily_goal`) va sulla colonna dedicata `omega_control.daily_goal`, non
  nei `params`.
- **Storico** (`components/trading/TradingHistory.tsx`, `variant="omega"`): attribuzione per
  giorno di **PIAZZAMENTO** per tutti i bot (`lib/dailyHistory.ts:attributionOf` → sempre
  `'placed'`), finestra clampata a **400 giorni**, calendario con `● centrato / ○ mancato /
  · obiettivo non storicizzato` (H-10: `goal_snapshot` **rispettato**, le righe senza snapshot non
  entrano nel tasso di centratura), dettaglio giorno che somma **solo** i trade attribuiti a quel
  giorno (M-18/H-11) e riusa la **stessa** tabella per partita.

**Fallback dichiarati senza `omega_models_v5.sql`** (la UI funziona, e dice che sta stimando):
`P&L bloccato` e `In verifica su Betfair` si stimano dalle righe caricate con la nota
«stimato dal client dalle righe caricate (applica omega_models_v5.sql per il valore dal DB)»;
`goal_snapshot` è forzato a `false` e la DayBar dice «obiettivo non ancora storicizzato»;
l'attività è filtrata lato client con la nota «filtro di giornata lato client (migrazione v5 non
applicata)»; «carica altre» non compare; `live_now` cade su `matches_open`. Ogni KPI ha la catena
`aggregates.X ?? stats.X`. Certificato da `pages/Omega.certificazione.test.tsx` §7 e da
`src/certification/migrations.cert.test.ts`.

### 17.9 Stato operativo e passi da fare

1. **Migrazione da applicare a mano** (Supabase SQL editor): **`migrations/omega_models_v5.sql`**,
   ultima nell'ordine dichiarato in **`migrations/APPLY_ORDER_2026-09-11.md`** —
   `mike_bot_v2.sql` → `mike_history_v2.sql` → `safe_strategy_bot_v2.sql` → `omega_models_v5.sql`.
   È indipendente dalla catena Mike/Safe (tocca solo `omega_*`) ma quell'ordine è quello con il
   minor numero di stati intermedi. Idempotente. Verifica:
   `select public.get_omega_state();` deve avere `locked_pnl_open`, `live_now`,
   `reconciling_liability` in `aggregates`; `select indexdef from pg_indexes where indexname =
   'uq_omega_trades_auto_leg';` deve escludere `leg_failed`.
   ⚠️ Se in futuro si riapplica `omega_models_v4.sql`, `omega_daily_v2.sql` o
   `daily_history.sql`, **rieseguire subito `mike_history_v2.sql`**: rimettono in vita la firma a
   7/3 argomenti di `trading_daily_history`/`trading_day_trades` e ricreano l'overload ambiguo
   (bug R2).
2. **Riavviare i servizi** e **riavviare l'app desktop** (l'exe è l'avviatore del `main.js` vivo:
   mai ricompilare). I servizi toccati sono `omega_service`, il servizio Safe Strategy e quello
   di Mike; lo scanner del feed unico non cambia.
3. **LIVE ancora BLOCCATO** (§16.6): serve la certificazione della liquidità lato **back**
   (§13.1, ancora parziale) e alcuni giorni di paper con le correzioni di oggi. I due gate del §I2
   restano intatti.
4. **Certificazione ripetibile sui DATI REALI**: `cd frontend && npx vitest run --config
   vitest.cert.config.ts` — monta `/omega`, `/safe-strategy` e `/mike` sul DB reale (letture SOLO,
   service role), cattura `console.error`/`warn` come KO, e verifica anche quali RPC esistono e
   quali campi rispondono (`src/certification/migrations.cert.test.ts`). Esito dell'11/09 sera:
   **26/26**. I file `*.cert.test.*` si **auto-saltano** fuori da quella config, così `npm test`
   non interroga mai il DB reale.

### 17.10 Ancora aperto (con motivo)

- **`locked_pnl_open_today` troncato a intero nel percorso RPC.** In `omega_db.aggregates` la
  tupla dei campi «in euro» è `("realized_profit", "realized_today", "open_liability",
  "locked_pnl_open", "reconciling_liability")`: `locked_pnl_open_today` **non c'è** e passa da
  `int(v)` → una perdita bloccata oggi di −0,80 € diventa 0. Effetto diretto su
  `realized_effective` (review H1) e quindi su stop-loss e target quando il bloccato è sotto
  l'euro. Il percorso PURO (`omega_engine.aggregate_trades`, fallback senza RPC) è corretto.
  **Fix di una riga, da fare prima del live.**
- Il docstring di `omega_service._flumine_no_fill_error` cita ancora `settled_at` fra i campi
  scritti: il codice sotto scrive `meta.error_at` e NON `settled_at` (review L5). Commento da
  allineare.
- `DESIGN_SYSTEM.md` è indietro sul codice in due punti: dice ancora «DA RICONCILIARE» dove il
  codice usa **IN VERIFICA SU BETFAIR**, e dichiara i tre pannelli parametri «non ancora
  migrati» mentre Omega usa già `ParamsSheetBase`.
- Fedeltà paper (bet delay 5 s), certificazione liquidità lato back dalle registrazioni REC,
  calibratore con una famiglia alimentata dagli stati REC/paper di **Omega** (§16.7 2P-F-03),
  e i punti già elencati in §14.5 / §16.6.

---

## 18. CHIUSURE, PUNTI APERTI E CONSIGLI (12/09/2026 sera, pushato `cda8e20` + `b267497`)

Analisi completa in `Betfair/CHIUSURE_2026-09-12.md`. Qui restano le **regole** e le
**decisioni aperte**: quello che è scritto qui vale più di ogni parametro.

### 18.1 La regola che manca in ogni manuale: chiudere a mercato è NEUTRO

Verificato su quattro chiusure vere: ognuna ha bloccato **esattamente** l'EV al prezzo di
quel momento (scarto 0,00 €; una a −0,54 € = lo spread).

| Caso | P mercato | P modello | EV mercato | bloccato |
|---|---|---|---|---|
| trade 70 FK Teleoptik | 20,4 % | 12,0 % | −22,08 | −22,08 |
| trade 84 VJS v Inter 2 | 67,1 % | 8,5 % | −9,23 | −9,23 |
| trade 88 Lazio-Milan | 30,3 % | 20,7 % | −7,62 | −8,16 |

**Ne segue una legge**: una chiusura distrugge valore SOLO se il modello batte il mercato.
Ogni cifra di «valore recuperato» vale a quella condizione, mai in assoluto. Chi scrive
report su questo bot deve dichiararlo, altrimenti sta vendendo una certezza che non ha.

### 18.2 Le due correzioni alle chiusure (norme, non parametri)

1. **Una quota vale come probabilità solo se è un prezzo VERO.** Il tetto di fine gara
   accetta la quota implicita solo con liquidità reale (`omega_model.quote_p`, ≥ 2 €) e
   dentro `greenup_market_floor_max_ratio` (default 3×) rispetto al modello. A distanza 0
   il tetto vale SEMPRE (il bancato è già sul tabellone: è il modello a essere rotto);
   col bancato irraggiungibile non vale MAI (nessuna quota inventa un rischio che non c'è).
   Caso che l'ha motivata: trade 84, back 1,49 = 67,1 % su un risultato che richiedeva un
   gol nel recupero, book a un lato solo, modello 8,5 %. Costo: −9,23 €.
   **Prova dal vivo (12/09, 22:10)**: Zaglebie-Katowice 96′, mercato 11,6 % contro modello
   0,13 % con 7,73 € dietro e nessun lato lay → quota SCARTATA, posizione tenuta, lay
   **vincente +1,32 €**. Stessa situazione del trade 84, esito opposto.
2. **`risk_cap` non chiude più a QUALUNQUE prezzo.** Su un lay la liability è già impegnata
   all'ingresso: chiudere non riduce il rischio preso, trasforma una distribuzione in una
   perdita certa. Sopra il tetto si esce solo a un prezzo che vale almeno
   `EV(tengo) − ev_margin − premio`, col premio limitato a `risk_premium_pct` della
   liability (default 5 %). `risk_premium_pct = 1` ripristina il vecchio tetto secco.
   Il controllo del rischio vero sta nel DIMENSIONAMENTO all'ingresso e nel
   `daily_loss_cap`, mai in una chiusura in perdita a mercato.

### 18.3 Punti aperti

1. **Il margine NON è dimostrato, e con questo profilo non è dimostrabile.**
   Margine mediano dichiarato dal modello: **0,49 punti percentuali**, cioè **+0,23 €** per
   scommessa, contro una deviazione standard di **12,06 €**. Rumore/segnale **53 a 1**:
   servono circa **10.700 scommesse** per distinguerlo dal caso al 95 %.
2. **Il campione non distingue margine da fortuna.** v2 (dal 09/09): 62 aperture, **2**
   perdite contro 1,36 attese (P = 0,84), liability media **221,53 €** contro una vincita
   media di **3,24 €**. **Una sola perdita in più cancella 68 vincite.**
3. **La calibrazione modello-contro-mercato non è misurabile**: su 25 aperture col blocco
   `meta.model` registrato, **zero** hanno perso. Senza eventi positivi il confronto è vuoto
   (il Brier premia chi prevede la probabilità più bassa, non chi ci prende). Strumento
   rieseguibile: `python -m Betfair.tools.verifica_margine_2026_09_12` — **dichiara** quando
   i dati non bastano invece di produrre un numero che sembra una risposta.
4. Migrazione `omega_models_v6.sql` ancora da applicare.

### 18.4 Consigli (in ordine di valore)

1. **Abbassare la quota di lay: `price_max` da 120 a ~40.** È il consiglio più forte.
   L'EV per scommessa **non cambia di un centesimo**: cambia solo la varianza.

   | Quota | Liability | EV/scommessa | Scommesse per dimostrarlo |
   |---|---|---|---|
   | 10 | 19,26 | +0,67 | **248** |
   | 30 | 62,06 | +0,67 | 781 |
   | 60 | 126,26 | +0,67 | 1.580 |
   | **110 (oggi)** | **233,26** | +0,67 | **2.911** |

   La quota alta non aggiunge margine: aggiunge varianza, e con essa il tempo e i soldi che
   servono per accorgersi di essere in torto.
2. **`greenup_risk_cap` da 0,10 al default 0,15.** Il valore stretto serviva quando il tetto
   chiudeva a qualunque prezzo; ora produce solo chiusure premature. Caso vero del 12/09:
   Gremio-Vasco, P(perdita) 12,7 %, chiuso pagando **1,08 €** sopra l'EV del tenere. A 0,13
   e a 0,15 la stessa posizione si tiene. Si cambia dal pannello, senza riavvio.
3. **Pretendere un margine minimo per entrare.** `select_k_se = 0` significa nessun margine
   di sicurezza richiesto: il bot banca qualunque selezione nella finestra 20-120. Senza
   selezione non c'è margine, si paga solo lo spread.

---

## 19. USCITE — IL TEMPO ENTRA NELLA DECISIONE (13/09/2026)

Revisione chiesta dopo aver constatato che i **tre soli green-up della storia del
bot** avevano chiuso in perdita altrettante posizioni che poi hanno **VINTO**.
Le due regole che lo causavano avevano lo stesso difetto di fondo: decidevano
senza guardare quanto tempo restava da giocare.

### 19.1 Via l'uscita incondizionata quando il bancato esce

**Prima**: se il punteggio bancato compariva sul tabellone, il bot chiudeva
subito, «perché il lay sta perdendo dal vivo», senza guardare il minuto.

**È sbagliato.** A distanza 0 il lay perde SOLO se la partita finisce esatta
così, e basta **un gol qualsiasi, di chiunque**, per vincerla. Il modello lo sa
già e lo misura — bancato 3-1 sul 3-1:

| Minuto | P(finisce 3-1) | P(arriva un altro gol) |
|---|---|---|
| 48′ | 24,5 % | **75,5 %** |
| 65′ | 39,2 % | 60,8 % |
| 85′ | 70,1 % | 29,9 % |

Chiudere al 48′ significava cristallizzare una perdita su una posizione con **tre
probabilità su quattro di vincere**.

**Ora** decide la stessa regola di valore atteso degli altri casi:
`_greenup_p_lose` calcola P(il punteggio resti questo) e il prezzo dice quanto
costa uscire. Tardi, quando quella P sale e uscire costa poco, la stessa regola
esce da sola — senza bisogno di una scorciatoia.

### 19.2 Il premio per uscire scala col tempo già giocato

Sopra `greenup_risk_cap` il bot **vuole** uscire e accetta di pagare un premio
per comprare la certezza (§18.2). Ma comprare certezza al 28′ non vale quanto
comprarla all'85′: nel primo caso resta un'ora per rientrare, nel secondo no.
Con un premio fisso i due momenti erano trattati allo stesso modo.

**Ora** `premio = liability × risk_premium_pct × frazione di gamba già giocata`.
A inizio gara il premio è zero: non si paga nulla per uscire, perché il tempo
lavora per noi. A fine gara è pieno, come prima.

**L'orizzonte è quello della GAMBA, non della partita**: 45′ per la gamba HT,
90′ per la FT. Difetto trovato nei test mentali e corretto prima del rilascio:
col 90′ per entrambe, al 40′ di primo tempo il bot avrebbe creduto di avere
mezza partita davanti mentre gli restavano cinque minuti.

`time_factor` ha default **1.0** (premio pieno = comportamento storico), quindi
Safe Strategy e ogni altro chiamante della funzione condivisa
`exits.decide_time_exit` restano identici finché non lo passano.

### 19.3 Effetto sui casi veri

Coi parametri vivi del DB (tetto 0,10 · premio 5 %):

| Caso | Minuto | P(perdita) | Prima | Ora |
|---|---|---|---|---|
| trade 70 FK Teleoptik | 28′ | 12,0 % | uscito −22,08 | **TIENE** |
| trade 84 VJS v Inter 2 | 91′ | 8,5 % | uscito −9,23 | **TIENE** |
| trade 88 Lazio-Milan | 67′ | 20,7 % | uscito −8,16 | **TIENE** |
| Gremio-Vasco (12/09) | 83′ | 12,7 % | uscito −14,31 | esce |

Le tre uscite storiche, tutte su posizioni poi vincenti, ora non avverrebbero.
Gremio-Vasco continua a uscire ed è difendibile: all'83′ non c'è più tempo.

### 19.4 Cosa NON è cambiato (verificato)

- **Distanza ≥ 2**: il bot non guarda nemmeno la posizione
  (`greenup_trigger_distance` = 1). Due gol di vantaggio = nessuna valutazione.
- **Bancato irraggiungibile**: nessuna azione, si incassa il payout pieno.
- **Take-profit**: dall'80′, se chiudendo si blocca ≥ 90 % dell'incasso, si
  incassa. L'ordine pareggia il risultato su entrambi gli esiti e la liquidità è
  verificata prima di piazzarlo (senza dato certo non si chiude).
- **Uscite in profitto** (`locked ≥ 0`): escono sempre e subito, a qualunque
  minuto. Il premio non le tocca.
- **Modello cieco** (P non stimabile): si tiene, mai cristallizzare una perdita
  su un dato che non c'è.

### 19.5 Rischio residuo, dichiarato

Tenere invece di chiudere significa che, quando il modello sbaglia, si paga la
**liability intera**. Oggi non c'è nessun freno a valle: `daily_loss_cap`,
`max_open_liability`, `max_liability_per_match` e `max_events` sono **tutti a
zero, cioè disattivati**. Con le uscite più caute di §19.1-19.2 quel freno
diventa più importante di prima, non meno.

## 20. IL SOFTWARE DEVE LASCIAR RESPIRARE IL DATABASE (13/09/2026)

### 20.1 Cosa è successo

Il 13/09 il progetto Supabase è andato **giù**: HTTP 503 `PGRST002` su tutto,
letture per **chiave primaria a 37 secondi**, e per rialzarlo è servito un
**restart del progetto**. Non era una query scritta male: era il **budget di IO
su disco esaurito** (`supabase.com/docs/guides/troubleshooting/exhaust-disk-io`).
Quando quel budget finisce l'istanza viene **strozzata**: i tempi esplodono,
l'autovacuum salta, e da lì in poi peggiora da sola.

Il contributo di Omega, misurato sul log delle **21:37** con l'app accesa — in
**due secondi**:

```
GET safe_strategy_scan?select=event_id,sport,payload,updated_at
    &event_id=in.(34 id)                                         x2
GET safe_strategy_status?select=id,payload,updated_at&id=eq.scanner    x2
```

cioè **una lettura del feed al secondo** con 34 id in URL, più lo stato dello
scanner allo stesso ritmo. Non perché il ciclo girasse ogni secondo — gira ogni
`poll_interval_s` — ma perché **dentro** un ciclo la riga del feed viene chiesta
decine di volte (punteggio, freschezza, book, una per gamba, una per green-up,
una per missione) e la cache condivisa dello scanner scade **ogni secondo**.
Trenta domande alla stessa riga dentro lo stesso ciclo sono trenta risposte
**identiche** pagate trenta volte.

### 20.2 La regola

> **Non si chiede al database una cosa che il database non ha ancora avuto il
> tempo di cambiare.**

Non è un'ottimizzazione: è una **condizione di produzione**. E per Omega non è
nemmeno una questione di comodità — Omega bloccata non è Omega lenta: è **una
posizione aperta a quota 75 che resta senza nessuno che la guarda**.

### 20.3 Come è implementata

Nove parametri (`omega_config._SPEC`), tutti regolabili, tutti a **zero =
comportamento di prima**. Nessuno tocca la logica di trading: cambiano solo
*ogni quanto* si rilegge.

| parametro | default | cosa governa | perché è sicuro |
|---|---:|---|---|
| `feed_cache_s` | 2 s | righe di `safe_strategy_scan` | è l'unica lettura che decide un **ordine**, quindi ha la cache **più corta di tutte**. Si mette in cache la **riga grezza**: il verdetto di freschezza (`fresh_payload`, `row_age_sec`) si ricalcola a ogni chiamata sull'`updated_at` della riga, mai su quando l'abbiamo letta |
| `scanner_status_cache_s` | 10 s | heartbeat dello scanner | il valore in cache viene **invecchiato** del tempo passato: l'età che ne esce è esatta al secondo. Un heartbeat *nuovo* si vede con ritardo, cioè si crede lo scanner più morto di quanto sia → **fail-safe** |
| `aggregates_cache_s` | 20 s | RPC `aggregates` (2 per giro) | governa stop giornaliero, cap di perdita e testata: non è una decisione al secondo. Dopo un piazzamento / settlement / green-up / azione manuale si **forza** il ricalcolo |
| `sets_cache_s` | 30 s | `traded_legs`, `traded_event_ids`, `failed_legs` | li scrive **questo stesso processo**: fra una rilettura e l'altra la copia in memoria *è* la verità, e lo scan ci scrive dentro la gamba appena piazzata (write-through, mai una copia) |
| `results_every_s` | 60 s | `positions_for_results` (timbro 1T/2T) | rete di sicurezza contabile, non un passaggio del flusso; il settlement completa comunque dal WINNER |
| `missions_every_s` | 5 s | `active_missions` + `trades_for_event` per missione | territorio dell'utente, che **legge**: non è un loop di trading |
| `events_refresh_s` | 1800 s | `refresh_events` | era una costante nel codice |
| `idle_stats_s` | 60 s | stats a bot fermo | era una costante nel codice |
| `idle_cycle_s` | 60 s | ritmo del ciclo **a vuoto** | il ciclo pieno serve solo quando qualcosa si muove da solo: posizione aperta, riconciliazione in sospeso, gamba ancora piazzabile oggi, missione seguita dall'utente (`_c_e_fretta`) |

Il loop non rilegge più `omega_control` due volte per giro (`run_once` lo legge
già, `_ULTIMI_PARAMS` basta a decidere quanto aspettare), e `process_missions`
riceve il control invece di rileggerlo.

### 20.4 Il risultato, misurato

Scenario del log: 34 partite in-play, una posizione aperta, una missione attiva.

| regime | prima | dopo | fattore |
|---|---:|---:|---:|
| giornata piena, `poll_interval_s` = 20 | 126 letture/min | 71 | **1,8×** |
| `poll_interval_s` = 5 (minimo) | 303 | 185 | **1,6×** |
| notte (niente aperto, niente partite) | 45 | 14 | **3,2×** |
| **solo il feed** (le due select del log) | 75 | 27 | **2,8×** |

Sul feed *misurato in produzione* (≈60 + ≈60 letture/min) il fattore è **≈4,4×**.

### 20.5 Obblighi per chi tocca il codice

1. **Ogni nuova lettura periodica deve avere il suo parametro di cadenza.** Una
   `select` dentro un ciclo senza una cadenza dichiarata è un difetto.
2. **Le cache sono variabili di modulo**: `Betfair/omega/conftest.py` (fixture
   autouse) le azzera *e spegne le cadenze* in tutta la suite — quasi tutti i
   test simulano più cicli nello **stesso istante** e con le cache accese
   misurerebbero la cache invece del comportamento. Chi vuole provare le cache
   lo fa **apposta**: `test_omega_respiro_db_2026_09_13.py`.
3. **Mai in cache una scrittura**, né una lettura che decide un ordine senza un
   criterio di freschezza **sul dato stesso**.
4. **Mai in cache le righe dei trade.** Fra la fase di settlement e quella di
   green-up, *dentro lo stesso giro*, quelle righe cambiano: una copia vecchia
   farebbe mandare un ordine di chiusura su una posizione appena regolata.
5. **Mai in cache le guardie dell'utente** (`mission_event_ids`,
   `manual_event_ids`): le scrive la UI, cioè un altro processo, e allargare la
   finestra vuol dire un secondo lay su una partita già esposta.
6. Se una lettura fallisce ma una copia in memoria c'è, **si continua con
   quella** (`_insieme_cached`): una posizione aperta non può restare senza
   nessuno che la guardi perché una `select` è andata in timeout.
7. `svuota_le_cache()` esiste per forzare un riallineamento immediato.

### 20.6 Resta da fare

- Le **righe dei trade** (`open_trades` ×2, `list_trades('pending')` ×2,
  `hedged_trades`, `closing_trades_for` per giro) restano la voce più pesante a
  `poll_interval_s` basso: ~72 letture/min a poll 5 s. Farle respirare richiede
  un'**invalidazione su scrittura** vera (le fasi che regolano e chiudono
  scrivono *fra* le due letture), non un TTL.
- I nove parametri **non sono ancora nel pannello** (`frontend/src/lib/omega.ts`):
  il blocco è pronto, l'esenzione temporanea è in
  `test_omega_ui_contratto_2026_09_11.py::_IN_ATTESA_DI_PANNELLO` e si spegne da
  sola appena la UI li dichiara.

### 20.7 Aggiornamento di fine serata (13/09)

**Il pannello esiste.** I nove parametri del respiro sono stati aggiunti a
`frontend/src/lib/omega.ts` (interfaccia, default e gruppo *«Respiro del
database»*), e `_IN_ATTESA_DI_PANNELLO` è stata **svuotata**: il contratto
UI ↔ servizio è di nuovo pieno. Quella esenzione deve restare vuota — una chiave
che il servizio onora e che il trader non può toccare è un parametro che di fatto
non esiste.

**Un difetto del contratto stesso, corretto.** `test_default_della_ui_uguali_a_quelli_del_servizio`
leggeva `C.DEFAULTS`, che è un dizionario **mutabile** e che il `conftest` azzera
per spegnere le cadenze durante i test. Il contratto pretendeva quindi dalla UI
gli **zeri della suite** invece dei default veri del servizio: avrebbe certificato
una pagina sbagliata. Ora legge `_SPEC`, cioè i default **dichiarati**.

### 20.8 Le chiusure e il flag `reduces_liability` — chi lo mette

Dal 13/09 il worker della coda tratta diversamente una gamba che **riduce** una
posizione: `params.reduces_liability = True` le fa saltare il minimo di
giurisdizione e il passo da 0,50 € sulle size BACK, e la esenta dal kill-switch
del live. Senza quel flag una chiusura sotto i 2,00 € finisce in **errore** e la
liability resta esposta fino al regolamento — che è esattamente ciò che il
manuale vieta («si esce subito e si accetta»).

**Omega è coperto per costruzione, e non deve dichiarare niente.** La catena è:

```
omega_service._manual_cashout  →  safe_strategy.execution.close_trade
                               →  meta["cashout"] = True
                               →  execution.enqueue_place  →  params.reduces_liability
```

`_flumine_enqueue_place` (l'unica via di accodamento di Omega) costruisce sempre
`action: "place"` per delle **APERTURE**: i suoi quattro punti di chiamata sono i
due ingressi automatici e i due manuali, e il payload del manuale
(`selection_id`, `side`, `price`, `size`…) non contiene `closes_trade_id`. È
corretto che non marchi nulla.

> **Obbligo per chi tocca il codice.** Le chiusure di Omega passano da
> `close_trade`, che marca la gamba. **Chi aprisse un'altra via di chiusura — una
> che non passa da `close_trade` — deve mettere `params.reduces_liability` da
> sé.** Non si eredita: si dichiara.

Per completezza, due cose che Omega **non** fa e che quindi non lo espongono al
punto aperto §7-quater della certificazione di Safe Strategy (sequenza
`place_submin` di coda lasciata a riposo, senza ritiro del residuo): Omega non
accoda **mai** `place_submin` — in tutto `Betfair/omega/*.py` la parola compare
solo in `omega_market.py`, cioè il percorso REST, che è già FILL_OR_KILL — e non
piazza importi sotto il minimo per via di coda.
