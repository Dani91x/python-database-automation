# AUDIT — «Posso scegliere PAPER o LIVE dalla UI, per ogni bot?» (2026-09-24)

Audit in sola lettura, worktree `agent-a1d65f13a5df1990a`, allineato a `master` con
`git merge --ff-only` (nessuna modifica). Nessun processo lanciato, nessun `.env`
letto/eseguito, nessuna query al DB: solo lettura statica del codice.

Metodo: per ogni soggetto ho cercato (a) la colonna/env che DECIDE la modalita', (b) il
codice UI che la scrive, (c) il punto in cui il servizio Python la RILEGGE, (d) un
eventuale env/costante che possa scavalcarla, (e) i test che dimostrano il cablaggio,
(f) il comportamento all'avvio dell'app.

---

## (a) Tabella compatta

| Soggetto | Dove si decide | Controllo UI | Letto a caldo | Scavalcato da env | Test e2e |
|---|---|---|---|---|---|
| **Omega** | `omega_control.mode` (col.) | **SI** — pagina Omega + Control Room (2 vie, stessa RPC) | **SI**, ogni `run_once` | **NO** | Parziale (contratto/mock, non capo-a-capo reale) |
| **Mike** | `mike_control.mode` (col.) | **SI** — Control Room | **SI**, ogni `run_once` | **NO** | Parziale (contratto/mock) |
| **Safe base/esatto/punta** | `safe_strategy_control.mode` (tetto) + `params.strategy_modes[x]` | **SI** — Control Room | **SI**, ogni `run_once` | **NO** | Parziale (contratto/mock) |
| **Safe tennis** | idem, chiave `strategy_modes.tennis` | **SI** — Control Room + gesto "solo tennis" | **SI** | **NO** | Parziale (contratto/mock) |
| **Safe model** (opportunita' ML) | `strategy_modes.model` | **NO** — nessun pulsante, per progetto | **SI** (legge la mappa, ma nessuno la scrive a 'live') | — | Nessuno (niente da testare) |
| **Safe manual** (ordini a mano dentro Safe) | `strategy_modes.manual` | **NO** — nessun pulsante | **SI** | — | Nessuno |
| **4 bot tennis (interruttore di servizio)** | `tennis_bot_service_control` (mode per bot) | **SI** — Control Room | **SI**, poll continuo | env `TENNIS_LIVE_ORDER_MODE` (gate di processo, vedi sotto) | Parziale (contratto/mock) |
| **4 bot tennis (per partita)** | `tennis_bot_control.dry_run` (bool, per evento+bot) | **SI** — pannello per-partita con checkbox + doppia conferma | **SI** | env `TENNIS_LIVE_ORDER_MODE=OFF` forza `dry_run=True` sempre (fail-safe) | **NESSUNO trovato** per il componente |
| **Trading manuale desktop (ladder/board)** | env `LIVE_ORDER_MODE` (OFF/PAPER/LIVE) | **NO** — solo un badge in sola lettura | **SI** (rilegge l'env a ogni ciclo) | **E' l'unica fonte**: non c'e' UI da scavalcare | Nessuno (niente UI da testare) |
| **Control Room (plancia)** | aggrega le righe sopra | **SI** — `PannelloBot.tsx` monta tutti gli interruttori tranne trading manuale e Safe model/manual | — | — | Discreto (component test sul doppio consenso) |

---

## (b) Reperti, per soggetto, con file:riga

### 1. Omega — OK, con una riserva sui test
- Colonna: `Betfair/omega/omega_db.py:49-58` (`read_control`/update su `omega_control`).
- Letta a ogni giro: `Betfair/omega/omega_service.py:6593` (`control = db.read_control()`
  dentro `run_once`, nessuna cache); uso: `omega_service.py:1607,2056` (`mode =
  control.get("mode","paper")`).
- UI (due vie, stessa verita'):
  - Pagina dedicata `frontend/src/pages/Omega.tsx:147` (`mode = control?.mode ?? 'paper'`),
    `:286` (`activateOmega(mode,...)`), `:375-386` (conferma esplicita per passare a
    live, doppio pulsante).
  - Control Room: `frontend/src/lib/interruttori.ts:604` (`avviaBot` → `activateOmega`),
    `:696` (`cambiaModalitaServizio` → `updateOmegaParams({mode})`, non tocca `status`).
  - RPC: `frontend/src/lib/omega.ts:1201-1227` (`omega_activate`/`omega_update_params`).
  - SQL: `migrations/omega_activate_conserva_params_2026-09-16.sql:40-65` — `UPDATE
    omega_control SET mode=p_mode, params=coalesce(p_params,params)`, owner-only
    (`betfair_live_is_owner()`), `p_mode` validato IN ('paper','live').
- Env che scavalca: **nessuno**. Unico `OMEGA_*` trovato è `OMEGA_LOCAL_WS_PORT`
  (`omega_service.py:7065`, porta del canale locale, non la modalita').
- Avvio app: `Betfair/omega/omega_service.py:6560-6587 ferma_al_nuovo_avvio` — a un
  avvio VERO (`APP_BOOT_ID` diverso/assente) Omega va a `status='stopped', mode='paper'`
  esplicitamente (commento riga 6564-6567: "NON passa da omega_activate... qui si usa
  set_control, che tocca solo le colonne passate"). **La modalita' NON resta quella
  dell'ultima scelta**: torna a paper. Solo un riavvio di PROCESSO con lo stesso
  `APP_BOOT_ID` (crash/watchdog) lascia lo stato intatto.
- Test: `Betfair/omega/test_omega_ui_contratto_2026_09_11.py` (canali/RPC dichiarati),
  `Betfair/omega/test_omega_avvio_app_2026_09_16.py` (avvio forza paper),
  `frontend/src/pages/Omega.certificazione.test.tsx`,
  `frontend/src/lib/interruttori.test.ts` (mock di `activateOmega`/`stopOmega`/
  `updateOmegaParams`, verifica CHE COSA viene chiamato). **REPERTO (lieve)**: sono
  tutti test "a contratto" (mock del client RPC lato JS, mock di `db` lato Python):
  non ho trovato un test che attraversi le due meta' insieme (RPC Supabase reale →
  riga scritta → `read_control()` che la rilegge). E' il pattern dichiarato del repo
  (RPC + servizio testati separatamente), non un buco nascosto, ma non è "e2e" in
  senso stretto.

### 2. Mike — stesso schema di Omega
- Colonna: `Betfair/mike/db.py:33` (`T_CONTROL = "mike_control"`), `:59 read_control`.
- Letta a ogni giro: `Betfair/mike/service.py:2439` (`control = db.read_control()` in
  `run_once`), `:2446` (`mode = str(control.get("mode") or "paper")`), uso a `:3778`.
- UI: Control Room via `frontend/src/lib/interruttori.ts:599` (`activateMike`),
  `:700` (`updateMikeParams(..., modalita)`); RPC `frontend/src/lib/mike.ts:1855-1869`
  (`mike_activate`/`mike_update_params`).
- Env che scavalca: **nessuno** (`MIKE_LOCAL_WS_PORT` a `service.py:4305` è solo il
  canale, non la modalita').
- Avvio app: `Betfair/mike/service.py:2401-2429 ferma_al_nuovo_avvio` (stesso schema:
  `status='stopped', mode='paper'`), chiamata a `:4751,4760`. Stessa nota di Omega:
  **la modalita' NON sopravvive a un avvio vero**.
- Test: `Betfair/mike/test_mike_contratto_db_2026_09_14.py`,
  `test_mike_allineamento_ui_2026_09_15.py`, `test_mike_certificazione_ui_2026_09_11.py`,
  `test_mike_contratto_ordini_2026_09_15.py` + gli stessi test frontend condivisi
  (`interruttori.test.ts`, `PannelloBot.test.tsx`). Stessa riserva di Omega (test a
  contratto, non capo-a-capo).

### 3. Safe calcio (base/esatto/punta) e Safe tennis — OK, con un difetto di progetto dichiarato per model/manual
- Colonne: `safe_strategy_control.mode` (il TETTO del servizio) **e**
  `params.strategy_modes[strategia]` (CON CHE SOLDI, per-strategia) — vanno d'accordo
  in due: "Live solo se scritto in tutti e due" (`frontend/src/lib/interruttori.ts:16-20`).
  Lato Python: `Betfair/safe_strategy/bot_service.py:67` (`_STRATEGIES = ("base",
  "esatto","punta","tennis","model","manual")`), `:84` default `strategy_modes={}`,
  `:308 normalize_strategy_modes`, `:356` risoluzione mode-per-strategia.
- Letta a ogni giro: `bot_service.py:7692` (`control = db.read_control()` in `run_once`).
- UI (base/esatto/punta/tennis): Control Room via `interruttori.ts:236-268
  (paramsAccensioni, scrive SEMPRE la mappa `strategy_modes` INTERA — mai un parziale)`,
  `:585-645` (`conCambio`/`accendi`/`spegni`/`cambiaModalita` → `scriviSafe` →
  `activateSafe`/`updateSafeParams`, RPC `safe_activate`/`safe_update_params`). SQL:
  `migrations/safe_strategy_bot.sql:171-199` — `UPDATE safe_strategy_control SET
  mode=p_mode, params=coalesce(p_params,params)`, owner-only, `p_mode` validato.
  `coalesce` sul JSONB è una SOSTITUZIONE INTERA della colonna quando `p_params` è
  passato (e lo è sempre da `paramsAccensioni`): nessuna eredita' silenziosa.
- Safe tennis: stessa infrastruttura, chiave `strategy_modes.tennis`, interruttore
  `'safe-tennis'` (`interruttori.ts:68`), più il gesto particolare "solo tennis"
  dichiarato per nome (`interruttori.ts:32-36`, `frontend/src/components/controlroom/
  comandiBot.ts:91-134`) usato dalla Control Room in modalita' "solo tennis"
  (`frontend/src/pages/ControlRoom.tsx:543-580`).
- **REPERTO — Safe model e Safe manual NON hanno interruttore, per progetto dichiarato**:
  `interruttori.ts:58-64` — "`model` e `manual` non hanno un interruttore... ma vanno
  NOMINATE quando si scrive la mappa: una chiave assente vuol dire 'eredita il mode del
  servizio'". Ogni scrittura le RISCRIVE esplicitamente con il loro valore PRECEDENTE
  (`interruttori.ts:260-264`, opzione di default `'conserva'`) — quindi tecnicamente non
  "ereditano" mai in silenzio — ma **non esiste NESSUN pulsante, in nessuna pagina, che
  possa portarle a 'live'**: l'unico modo di farlo oggi è una scrittura diretta sul DB,
  fuori dalla UI. Confermato lato Python: `bot_service.py:6365` ("eredita': senza
  `strategy_modes.model='live'` si resta in paper"); lato UI:
  `frontend/src/components/safestrategy/BotParamsSheet.tsx:251` ("oggi in paper finché
  `strategy_modes.model` resta paper"). Per l'utente che vuole operare SOLO dalla UI:
  su queste due sotto-modalita' **oggi non può farlo affatto** (nemmeno restare in
  paper è una scelta sua: è l'unico stato raggiungibile dalla UI).
- Avvio app: `bot_service.py:7645-7672 ferma_al_nuovo_avvio` + `:7591-7613
  strategy_modes_a_paper` — a un avvio vero, `status='stopped'` **e TUTTE le voci di
  `strategy_modes` (comprese model/manual) tornano a 'paper'**. Stesso schema fail-closed
  di Omega/Mike.
- Test: `Betfair/safe_strategy/test_allineamento_ui_2026_09_15.py`,
  `test_avvio_app_2026_09_16.py`, più `interruttori.test.ts`/`PannelloBot.test.tsx` lato
  frontend (coprono base/esatto/punta/tennis). **Nessun test per model/manual** — coerente
  (non c'è un pulsante da testare), ma vuol dire che nessuna suite oggi certifica che
  quelle due chiavi restino davvero "congelate" se in futuro qualcuno aggiunge un
  pulsante per sbaglio altrove.

### 4. I 4 bot tennis (scalper/pro/flb/swing) — due livelli, uno dei due senza test di componente
- Livello 1 — interruttore di SERVIZIO (per bot, non per partita):
  `Betfair/stream/tennis_live/tennis_bot_service.py:361-410 riconcilia_interruttori`
  legge `db.list_tennis_bot_services()` (mode desiderata) a ogni giro del ponte. UI:
  `interruttori.ts:595-597` (`activateTennisBotService`), `:691-693`
  (`updateTennisBotService({mode})`, non tocca `status`).
- Livello 2 — riga PER (evento, bot): `tennis_bot_control.dry_run` (bool). Quando
  l'interruttore di servizio è "acceso" e in modalita' `live`, il ponte arma
  AUTOMATICAMENTE ogni nuovo evento seguito con **`dry_run=True` comunque**
  (`tennis_bot_service.py:391-397`, commento: "in LIVE `dry_run` resta True finché
  l'utente non lo toglie a mano — prudenza sui soldi veri"). Per avere ordini REALI su
  una singola partita serve un secondo gesto esplicito dal pannello per-partita:
  `frontend/src/components/tennis/TennisBotPanel.tsx:117` (`dryRun` di default =
  `orderMode!=='PAPER'`, quindi parte comunque protetto), `:240` (checkbox), `:498-513`
  (`handleArm`, conferma `window.confirm` quando `!dryRun && orderMode==='LIVE'`), RPC
  `tennis_bot_arm` (`frontend/src/lib/tennis.ts:778-794`). Questo è un design di
  sicurezza voluto (doppia conferma), non un difetto — ma va detto chiaramente
  all'utente: **scegliere "live" sull'interruttore di servizio NON basta**, va
  confermato partita per partita dal pannello dedicato.
- Env aggiuntivo: `TENNIS_LIVE_ORDER_MODE` (`Betfair/stream/tennis_live/
  tennis_live_order_worker.py:52`, `tennis_runner.py:112`) — stesso schema del
  `LIVE_ORDER_MODE` del trading manuale: gate di PROCESSO (OFF/PAPER/LIVE), letto
  dall'env, **senza controllo UI**. Effetto fail-safe (buono): se questo env è OFF, il
  bot è FORZATO in `dry_run=True` A PRESCINDERE dal DB (`tennis_runner.py:565-588`,
  "KILL-SWITCH DI MODALITA'"). Quindi non è scavalcato nella direzione pericolosa (non
  può forzare live), ma resta un pezzo di "con che soldi" che l'utente non può governare
  dalla UI.
- **REPERTO — nessun test di componente per il pannello per-partita**: ho cercato
  `TennisBotPanel.test.tsx` e non esiste (`frontend/src/components/tennis/` ha solo
  `TennisBotServiceParamsSheet.test.tsx`, che copre i parametri, non l'armamento). Il
  livello 1 (interruttore di servizio) è testato in `interruttori.test.ts` (mock di
  `activateTennisBotService`) e in `Betfair/stream/tennis_live/tests/
  test_ponte_interruttori_2026_09_17.py` (verifica `riconcilia_interruttori`/`dry_run`
  lato Python). Il livello 2 (checkbox + doppia conferma nel componente React) **non ha
  un test dedicato**: nessuna prova automatica che il click sulla checkbox, il
  `window.confirm`, e la chiamata a `armTennisBot` siano davvero cablati come il
  commento dice.
- Avvio app: `tennis_bot_service.py:50-113 ferma_bot_al_nuovo_avvio` (righe ATTIVE per
  evento+bot → `stopped`) e (dal riferimento a riga `413` in poi)
  `ferma_interruttori_al_nuovo_avvio` per l'interruttore di servizio. **Non verificato
  a fondo**: non ho controllato se, oltre allo `status`, anche il campo `mode`
  dell'interruttore di servizio viene esplicitamente riportato a 'paper' a un avvio
  vero (per Omega/Mike/Safe l'ho verificato riga per riga; per il livello-1 tennis ho
  solo visto lo `status` andare a `stopped` nella funzione letta — da confermare prima
  di dire "identico agli altri tre").

### 5. Trading manuale dal desktop (ladder/board) — REPERTO GRAVE: nessuna UI, solo `.env`
- Modalita' decisa **esclusivamente** da `LIVE_ORDER_MODE` (env, valori OFF/PAPER/LIVE):
  `Betfair/stream/config_stream.py:190` (costante d'avvio) e `:234-242`
  (`live_order_mode()`, rilegge `os.getenv` ad OGNI chiamata — commento onesto: "un
  DOWNGRADE di sicurezza deve avere effetto senza riavviare il runner"). Stessa
  funzione duplicata/fallback in `Betfair/stream/live_order_worker.py:89-103`.
- **Non esiste nessun controllo UI per cambiarlo.** L'unico posto dove il frontend
  tocca `mode` è PER SINGOLO ORDINE (`frontend/src/lib/liveOrders.ts:20,29`, tipo
  `LiveOrderMode`, mandato dentro ogni comando `place`/`cancel`/`replace`/ecc.), ma
  quella riga può essere eseguita SOLO se il gate di PROCESSO lo permette:
  `_servable_modes()` (`live_order_worker.py:133-145`) — processo OFF → nessuna riga
  eseguita; processo PAPER → solo righe `'paper'` (una riga `'live'` finisce in errore
  `live_client_assente`, fail-closed: `live_order_worker.py:184-193`); processo LIVE →
  entrambe. Quello che la UI mostra (`frontend/src/pages/MarketWatch.tsx:202-213`,
  badge `ModeBadge` in `frontend/src/components/live/LiveTradingPanel.tsx:60-68`) è
  **SOLO IN LETTURA**: legge `nowBy[id].state.order_mode`, che è scritto dal runner
  stesso (`Betfair/stream/runner.py:296`, `"order_mode": live_order_mode()`) — un
  termometro, non un interruttore.
- Per cambiare la modalita' del trading manuale oggi serve editare la variabile
  d'ambiente `LIVE_ORDER_MODE` (file `.env` del processo) — **esattamente il caso che
  l'utente vuole evitare** ("voglio operare dalla UI, non dal codice"). Non è
  scavalcata da nulla perché non c'è nient'altro: è l'unica fonte, e non è raggiungibile
  dalla UI.
- Kill-switch/tetto correlati, stesso schema (solo env, nessuna UI):
  `LIVE_KILL_SWITCH` (`config_stream.py:223,245-...`), `LIVE_MAX_STAKE_PER_ORDER`
  (`config_stream.py:217-220`).
- Avvio app: `LIVE_ORDER_MODE` non è una riga di controllo DB, quindi `avvio_app.py`
  non lo tocca. Il suo valore all'avvio è quello scritto nel file `.env` del processo:
  **non "resta l'ultima scelta dalla UI"**, perché non esiste una scelta dalla UI —
  resta semplicemente quello che c'è scritto nel file finché qualcuno non lo cambia a
  mano.
- Test: nessuno lato UI (niente da testare). Lato Python ci sono test sul comportamento
  fail-closed di `_servable_modes`/`_client_for_mode` (verificarli con nome esatto non
  fatto in questo audit — da fare se serve la prova puntuale).

### 6. Control Room — la plancia unificata esiste ed è ben costruita, ma non copre tutto
- `frontend/src/pages/ControlRoom.tsx:55,543` monta `PannelloBot` con `righe`, `comandi`
  (da `frontend/src/components/controlroom/comandiBot.ts`, che avvolge
  `interruttori.ts` più l'eccezione "solo tennis"). Un interruttore per Omega, Mike,
  le 4 strategie di Safe (base/esatto/punta/tennis) e i 4 bot tennis di servizio — con
  doppia conferma per passare a live e un "FERMA TUTTI" senza conferma
  (`frontend/src/components/controlroom/PannelloBot.tsx:18-30`, commento di progetto).
- **NON copre**: il trading manuale (ladder/board, `LIVE_ORDER_MODE`), Safe model, Safe
  manual, e il livello-2 per-partita dei bot tennis (quello vive nella scheda della
  singola partita, `TennisBotPanel.tsx`, non nella Control Room).
- `frontend/src/components/controlroom/useControlRoom.ts` (hook dati, 1382+ righe)
  aggrega stato/battiti/P&L per la vista ma non introduce una seconda verita' sulla
  modalita': legge dagli stessi `control` che i servizi scrivono.

---

## (c) Proposta minima — «tutto dalla UI, niente dal codice»

Per soggetto, senza implementare nulla:

- **Trading manuale (priorita' massima)**: portare `LIVE_ORDER_MODE` (e idealmente
  `LIVE_KILL_SWITCH`) da env a una riga di controllo DB (es. `betfair_live_order_control`
  singleton), con una RPC owner-only `set_live_order_mode('off'|'paper'|'live')` e un
  interruttore nella Control Room (o nel pannello ladder) identico agli altri, PIÙ un
  pulsante "FERMA" per il kill-switch. Il codice del worker cambia pochissimo:
  `live_order_mode()` già rilegge "qualcosa" ad ogni ciclo — basterebbe farla leggere dal
  DB invece che da `os.getenv`, mantenendo l'env come fallback di sicurezza a `OFF` se il
  DB non risponde (stesso principio fail-closed già in uso altrove).
- **Safe model / Safe manual**: decidere con l'utente se questi due percorsi vadano MAI
  esposti alla UI (oggi sono `paper` per costruzione e la squadra li ha lasciati così di
  proposito, vedi §17/09 nel CRONOSTORIA). Se la risposta è sì, aggiungere due righe
  all'elenco `STRATEGIE_MANUALE`/`INTERRUTTORI` con lo stesso schema delle altre quattro
  (nessuna logica nuova, solo due nomi in più nelle liste che già esistono).
- **4 bot tennis, livello per-partita**: nessun cambiamento di funzione — serve solo un
  test di componente (`TennisBotPanel.test.tsx`) che dimostri il cablaggio checkbox →
  `armTennisBot` → RPC, sul modello di `PannelloBot.test.tsx`. Non è un buco di
  funzionalità, è un buco di prova.
- **Omega/Mike/Safe (base/esatto/punta/tennis)**: nessuna proposta — il meccanismo
  esiste, è scritto una volta sola (`interruttori.ts`) e riusato ovunque, letto a caldo
  dai servizi, e riportato a paper ad ogni avvio vero dell'app. L'unico miglioramento
  utile sarebbe un test end-to-end reale (RPC Supabase vera in un DB di test → riga letta
  dal servizio Python vero) per chiudere la riserva del punto (b.1).

---

## Cosa NON ho potuto verificare (da riprendere)

1. **4 bot tennis, avvio app**: non ho confermato riga per riga se, oltre allo `status`,
   anche il campo `mode` dell'interruttore di SERVIZIO (livello 1,
   `tennis_bot_service_control`) viene esplicitamente riportato a `'paper'` a un avvio
   vero, come confermato invece per Omega/Mike/Safe. La funzione `ferma_bot_al_nuovo_avvio`
   (livello 2, per evento) tocca solo lo `status`. Da leggere:
   `Betfair/stream/tennis_live/tennis_bot_service.py` righe successive alla 413
   (`ferma_interruttori_al_nuovo_avvio`), non lette per intero in questo giro.
2. **Nome esatto dei test Python** sul comportamento fail-closed di
   `_servable_modes`/`_client_for_mode` in `live_order_worker.py`: ho visto la logica,
   non ho cercato il file di test che la esercita (se esiste, non ho controllato la sua
   falsificazione).
3. **RPC `mike_activate`**: non ho trovato il file di migrazione SQL corrispondente con
   una ricerca testuale diretta (potrebbe avere un nome diverso o essere in un file non
   cercato con lo stesso pattern usato per Omega/Safe); il comportamento è comunque
   confermato lato TypeScript (`frontend/src/lib/mike.ts:1855-1869`) e lato Python
   (`mike/service.py`, lettura fresca), solo la SQL esatta resta da individuare per
   completezza.
4. Non ho eseguito nessuna suite di test (audit statico, come da mandato): le
   affermazioni sul "che cosa i test coprono" si basano sulla lettura dei file di test,
   non su un'esecuzione con falsificazione mia.
5. Non ho verificato la UI di **SafeStrategy.tsx** (pagina dedicata, come Omega.tsx) per
   un eventuale secondo percorso di attivazione parallelo a `interruttori.ts` — ho
   verificato solo che monta `PannelloBot`.
