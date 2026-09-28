# CANTIERE G — PAGINE: DIFETTI RESIDUI E CAMPI SOLO-LIVE (28/09/2026)

Delegato, worktree `agent-ade46c5c274d06f56`. Perimetro: `frontend/src/**` e i banchi di
test del frontend. Niente Python dei bot, niente scrittura DB (SOLO `SELECT`), niente
`git add`/commit, niente app avviata. Consegna a blocchi: voci 1-5 prima (fatte per
intero, con test e falsificazione), poi 6-7 (verifica parziale, dichiarata sotto).

---

## Voce 1 — Pulsante «avvia» di Safe assente al primo clic

**Causa radice** (`R-E2E-1` / `R-F2-17`, `AUDIT_2026-09-25/E2E_FASE1_ESITI_2026-09-25.md` §
reperti, `AUDIT_2026-09-25/e2e_fase2/E2E_FASE2_Z0_AVVIO...` e
`AUDIT_2026-09-25/E2E_FASE2_BOT_PAPER_2026-09-26.md:156-158`): la plancia legge chi è
acceso da `variants`/`strategy_modes` preferendo sempre gli EFFETTIVI del servizio
(`control.stats.params_effective`) ai parametri appena scritti (`control.params`) —
`frontend/src/components/controlroom/useControlRoom.ts` (funzioni `leggiVarianti` e
`leggiModiStrategia`, invocate nel `useMemo` di `bots`). Gli effettivi li pubblica il
LOOP del servizio (`Betfair/safe_strategy/bot_service.py:9363`,
`db.set_control(stats=..., heartbeat_at=now())`), non la RPC di accensione
(`safe_activate`/`safe_update_params`, che scrive `started_at`/`updated_at` ma MAI
`heartbeat_at`: `migrations/safe_strategy_bot.sql:190-193`). Nella finestra fra
un'accensione e il primo giro successivo del servizio, `stats.params_effective` è ancora
quello della SESSIONE PRECEDENTE (es. dopo un riavvio dell'app): la riga «Safe base»
risultava già accesa secondo un dato stantio e il pulsante «avvia» spariva, finché il
servizio non ripubblicava (misurato: «pochi minuti dopo» nel reperto).

**Correzione**: nuova funzione pura `effettiviStantii(control)` — confronta
`control.started_at` (scritto SOLO dalla RPC di accensione) con `control.heartbeat_at`
(scritto SOLO dal loop): se il battito è assente o più vecchio dell'accensione, gli
effettivi sono dichiarati stantii e `leggiVarianti`/`leggiModiStrategia` (nuovo terzo
parametro opzionale, default `false` = comportamento di sempre) SALTANO la fonte
`effettivi` e leggono solo `control.params`, appena scritto dalla stessa RPC che ha appena
eseguito il comando dell'operatore. Non è un fail-open: quando il battito è più recente
dell'accensione si torna a fidarsi degli effettivi come prima (nessuna regressione sul
comportamento «i normalizzati contano più del grezzo», es. `variants:[]` che per il
servizio vuol dire «tutte e quattro»).

**File toccati**:
- `frontend/src/components/controlroom/useControlRoom.ts` — aggiunta `effettiviStantii`;
  `leggiVarianti`/`leggiModiStrategia` con terzo parametro `effettiviStantiiFlag`; il
  `useMemo` di `bots` lo calcola e lo passa.
- **nuovo** `frontend/src/components/controlroom/useControlRoom.effettiviStantii.test.ts`
  (9 test).

**Test**: `npx vitest run src/components/controlroom/useControlRoom.effettiviStantii.test.ts`
→ **9/9 verdi**, 20 ms. **Falsificazione**: `effettiviStantii` forzata a `return false`
(sempre "non stantii", il comportamento di prima) → **2/9 rossi** (esattamente i due test
che verificano la rilevazione di uno stato stantio); ripristinato, `grep -c MUTAZIONE` = 0,
rilanciato → 9/9 verdi.

**Parità paper/live**: la funzione non distingue paper/live, legge solo i timestamp del
`control`: stesso comportamento nelle due modalità.

---

## Voce 2 — «Avvia in prova» dalla scheda TENNIS di Safe spegneva il calcio

**Causa radice**, con la prova che era un DIFETTO REALE oggi (non solo storico): reperto
CRONOSTORIA sezione 2026-09-26, h11:25 — «con Safe calcio già acceso, "avvia in prova"
dalla scheda tennis riscrive `variants=["tennis"]` e spegne base/esatto/punta»: Safe calcio
è rimasto spento dalle 11:13:19 alle 11:16:16 UTC, finché l'operatore non se n'è accorto e
lo ha riacceso dalla sua scheda. Codice: `frontend/src/components/controlroom/comandiBot.ts`
(funzione `soloTennis` dentro `creaComandiControlRoom`), che chiamava
`accensioniSoloTennis(modalita)` — `{base:null, esatto:null, punta:null, tennis:modalita}` —
SOSTITUENDO sempre le accensioni correnti, invece di aggiungerle.

Nota per il coordinatore, **CONFERMATA dall'utente il 28/09** (testuale): «OGNI BOT DEVE
ESSERE INDIPENDENTE... se decido di accenderne solo 1, parte solo quello... posso
scegliere io quali bot attivare, 1, 2, 3 ecc oppure tutti insieme». Questo chiude la
riserva che avevo scritto qui nella prima consegna: l'ordine del 15/09 («deve partire
solo lui, come ieri») descriveva l'ACCENSIONE del tennis, non uno spegnimento del calcio
come effetto collaterale — «solo lui» = «lui parte», non «lui e basta, gli altri muoiono».
Il comportamento additivo implementato qui è quindi quello giusto, confermato, non più da
riconfermare. Vedi la sezione **«Indipendenza di ogni bot»** più sotto (seconda consegna,
28/09 sera) per l'audit esteso a TUTTI i pulsanti di accensione/spegnimento della Control
Room, con lo stesso principio.

**Correzione**: `soloTennis` in `comandiBot.ts` ora legge le accensioni CORRENTI via
lettura fresca dal database (`sorgenteConRilettura.rileggiSafe()`, lo stesso meccanismo del
REPERTO A del 18/09 già usato da ogni altro comando su Safe), sovrascrive SOLO la voce
`tennis`, e scrive quella mappa — base/esatto/punta, con la LORO modalità corrente
(compreso «live», se lo erano), restano esattamente come sono. Spegnere una variante resta
un gesto esplicito (il pulsante «spegni» di quella riga, invariato). La stessa funzione è
condivisa da `accendi` e dall'escalation a soldi veri (`cambiaModalita('live')`), quindi il
fix copre entrambi i pulsanti della scheda tennis.

`accensioniSoloTennis`/`paramsSoloTennis` (in `soloTennis.ts`) restano nel file per chi le
importa ancora (retrocompatibilità), ma **non sono più nel percorso della Control Room**:
commentate come tali. `differenzeSoloTennis` (l'avviso PRIMA del clic) non annuncia più uno
spegnimento che non avviene più; la nota testuale in `ControlRoom.tsx` è stata riscritta
per dire «AGGIUNGE... senza toccare le strategie di calcio già accese».

**File toccati**:
- `frontend/src/components/controlroom/comandiBot.ts` — `soloTennis` additiva.
- `frontend/src/components/controlroom/soloTennis.ts` — `differenzeSoloTennis` non annuncia
  più lo spegnimento; commenti aggiornati su `accensioniSoloTennis`/`paramsSoloTennis`.
- `frontend/src/pages/ControlRoom.tsx` — testo della `nota` della scheda tennis (righe
  ~613-628): riscritto per dire «AGGIUNGE», non più «spegne». **File già toccato oggi dal
  Cantiere B (3 righe, area `RigaCapacitaMercati`, non toccata da me)**: la mia modifica è
  in un punto diverso (la `nota` del pannello bot), dichiarata qui come da perimetro.
- `frontend/src/components/controlroom/comandiBot.test.ts` — riscritto il test che
  verificava lo spegnimento (`'da li «avvia» accende il tennis e SPEGNE le altre tre'` →
  `'AGGIUNGE il tennis, NON spegne le altre tre gia' accese'`); aggiunto un test per
  l'accensione da uno stato parziale (solo base acceso).
- `frontend/src/components/controlroom/soloTennis.test.ts` — 2 test riscritti (non
  annuncia più lo spegnimento); 1 test aggiunto (tennis non ancora abilitato).
- `frontend/src/pages/ControlRoom.test.tsx` — 1 test riscritto per il nuovo testo della
  nota (`'dice PRIMA del clic che parte solo il tennis'` →
  `'dice PRIMA del clic che AGGIUNGE il tennis... senza spegnere il calcio'`).

**Test**: `npx vitest run src/components/controlroom/comandiBot.test.ts
src/components/controlroom/soloTennis.test.ts src/pages/ControlRoom.test.tsx` →
**148/148 verdi** (12 + 24 + 112), ~72 s. **Falsificazione**: `soloTennis` rimessa al
comportamento sostitutivo (`{base:null,esatto:null,punta:null,tennis:modalita}`) → i 2 test
nuovi/riscritti che verificano la persistenza di base/esatto/punta diventano **rossi**
(`expected ['tennis'] to deeply equal ['base','esatto','punta','tennis']`); ripristinato,
`grep -c MUTAZIONE` = 0, rilanciato → verde.

**Parità paper/live**: il gesto scrive `strategy_modes.tennis` alla modalità richiesta
(paper o live) e non tocca le altre voci in nessuno dei due casi: stesso codice, stessa
RPC (`safe_activate`/`safe_update_params`), unica differenza i soldi.

---

## Voce 3 — Lista partite: esclusa la fascia 00:00-02:00 di Roma, incluse partite di ogni giorno futuro

**Causa radice**, `frontend/src/components/dashboard/MatchesList.tsx` (funzione
`fetchMatches`, ramo non-Betfair): il filtro era
```
.gte('fixture_date', `${today}T00:00:00Z`)
```
**senza limite superiore** (nessun `.lt`) e con `today` = mezzanotte UTC, non di Roma.
Due difetti distinti, confermati:
1. **Nessun confine superiore**: la query tornava TUTTE le partite future, non solo quelle
   di oggi. Prova indipendente (referto `AUDIT_2026-09-25/E2E_FASE3_PAGINE_SESSIONE_B_2026-09-26.md`
   U0008): `count(*) fixture_date>='2026-09-26T00:00:00Z'` = **1186** righe per «oggi» — un
   numero enormemente superiore a una sola giornata di calcio.
2. **Confine di giorno in UTC, non di Roma** (stesso referto, U0011): le partite delle
   22:00-23:59 UTC del giorno prima (= 00:00-01:59 di Roma) restavano FUORI dal filtro
   `>= oggiT00:00:00Z` di oggi, pur essendo — per l'orologio del trader — partite di oggi.

**Correzione**: nuova funzione pura `confiniGiornoRoma(day)` in `frontend/src/lib/rese.ts`
— calcola la mezzanotte di Roma di `day` e del giorno dopo come istanti UTC, con DUE
passate di lettura dell'offset (`Intl.DateTimeFormat` con `timeZoneName:'shortOffset'`,
niente tabelle di date a mano) per essere corretta anche nei due giorni l'anno del cambio
ora legale (dove il giorno di Roma dura 23 o 25 ore, mai esattamente 24). `MatchesList.tsx`
ora usa `giornoRoma(new Date())` (non più `format(new Date(),'yyyy-MM-dd')`, che dipende
dal fuso del sistema operativo) per «oggi», e filtra con
`.gte('fixture_date', inizio).lt('fixture_date', fine)`.

**File toccati**:
- `frontend/src/lib/rese.ts` — nuove `offsetMinutiRoma`, `mezzanotteRomaUTC`,
  `confiniGiornoRoma` (esportata).
- `frontend/src/components/dashboard/MatchesList.tsx` — `today` da `giornoRoma`; query con
  `confiniGiornoRoma` e limite superiore.
- `frontend/src/lib/rese.test.ts` — 5 test nuovi.

**Test**: `npx vitest run src/lib/rese.test.ts` → **14/14 verdi** (9 preesistenti + 5
nuovi), 78-122 ms. **Falsificazione**: `confiniGiornoRoma` sostituita con il vecchio
confine (`{inizio: day+'T00:00:00Z', fine: day+'T23:59:59Z'}`) → **5/5 test nuovi rossi**
(mezzanotte sbagliata, partita delle 00:30 di Roma esclusa, partita del giorno dopo NON
esclusa, durata giorno errata); ripristinato, `grep -c MUTAZIONE` = 0, rilanciato → verde.

**Non verificato** (fuori dal mio perimetro frontend): il ramo Betfair-only di
`MatchesList.tsx` usa `fetchBetfairFixtures(today)` → RPC `get_betfair_fixtures(p_date)`
(`migrations/betfair_fixtures_rpc.sql`), che filtra su `engine_signals.run_date = p_date`
(colonna `date`, non `timestamptz`): non ho verificato se `run_date` è già calcolato sul
giorno di Roma dal lato Python che lo scrive (`engine_signals`) — è SQL/Python, fuori
perimetro. Se non lo fosse, lo stesso difetto (fascia 00:00-02:00) si ripresenterebbe SOLO
nella vista «solo Betfair».

---

## Voce 4 — Match Replay trattava gli importi come sterline

**Causa radice**: dal 26/09 le size dello STREAM sono convertite in EUR alla fonte
(`Betfair/stream/valuta.py`, referto `AUDIT_2026-09-26/FIX_K1_VALUTA_GBP_EUR.md`), con un
marcatore `valuta:'EUR'` scritto dal recorder (`Betfair/stream/recorder.py:82-86`,
`serialize_book`) SOLO se il book è passato dalla conversione. Il referto K1 stesso (§9.1)
dichiarava il rischio residuo: «`frontend/src/lib/matching.ts` (`MIN_STAKE_GBP`) e
`replay-pnl.ts` trattano i file curati come sterline (£)... fuori dal mio perimetro».

**Verifica sul DB (SOLA LETTURA, 28/09, decisiva per la correzione)**: ho letto
`pg_get_functiondef` di `get_replay`/`get_replay_meta`/`get_replay_frames` — tutte e tre
restituiscono la colonna `ladder` (jsonb) di `live_market_snapshots` COSÌ COM'È, senza
scomporla: un domani, se l'importatore scrivesse il marcatore dentro quel jsonb, arriverebbe
al frontend senza bisogno di toccare le RPC. Ho poi interrogato la tabella:
`max(created_at) = '2026-09-22'`, **prima** del fix K1 (26/09). **Conclusione verificata**:
OGGI ogni riga di `live_market_snapshots` è in **GBP**, nessuna porta il marcatore
(l'importatore Python che porta il file curato `.jsonl` in questa tabella non è stato
toccato dal fix K1 — è fuori dal mio perimetro, dichiarato sotto).

**Correzione**: nuove funzioni pure in `frontend/src/lib/live.ts` — `convertiFrameEur`
converte le SIZE di un frame (mai i prezzi, che sono quote, non denaro) da GBP a EUR,
leggendo il marcatore `valuta` dal JSON grezzo (mai dal tipo TS `Ladder`, che non lo
dichiara: la colonna JSONB può portare chiavi che il tipo non conosce). Un frame già
marcato `'EUR'` non viene ri-moltiplicato (idempotente, mai una doppia conversione) e il
marcatore viene comunque tolto dalla mappa (non è una selezione: un consumatore che
iterasse `ladder` per id numerico non deve incontrarlo). `convertiFramesEur` applica la
regola a un elenco. Agganciate nell'UNICO punto in cui i frame del replay entrano
nell'app: `fetchReplay` e `fetchReplayChunked` (dentro `fetchReplayFramesWindow`, prima che
i frame finiscano nell'array) — ogni consumatore a valle (`matching.ts`, `replay-pnl.ts`,
`LadderView`, `opportunities/*`) vede sempre EUR, senza saperlo, stessa filosofia del
middleware backend (converti alla fonte, una volta sola).

Il cambio usato è **IDENTICO** a quello di ripiego del backend
(`Betfair/stream/valuta.py::CAMBIO_RIPIEGO`, 1,164687, EUR/GBP del 23/09/2026): nessuna
registrazione porta il cambio del giorno, quindi ho riusato la STESSA costante documentata
invece di inventarne una nuova, per referti riproducibili fra backend e frontend.

**Bug di etichetta indipendente, corretto anche questo**: `formatGbp` (in `replay-pnl.ts`)
mostrava il simbolo «£» — sbagliato ANCHE PRIMA del fix K1, perché il conto dell'utente è
in EUR (piazza gli stake del replay in euro, mai in sterline): ora mostra «€». Stessa
correzione su 4 file che scrivevano «£» a mano (non tramite `formatGbp`):
`components/replay/MarketPanel.tsx` (stake dropdown/input, titoli «minimo Betfair»),
`TradesPanel.tsx`, `ValidationCard.tsx`, e un commento in `OpportunitaPanel.tsx`; commenti
aggiornati in `matching.ts` (`MIN_STAKE_GBP`, nome invariato per un diff minimo — un solo
punto di chiamata) e `MatchReplay.tsx`.

**File toccati**:
- `frontend/src/lib/live.ts` — `CAMBIO_RIPIEGO_GBP_EUR`, `convertiFrameEur`,
  `convertiFramesEur`, agganciate in `fetchReplay`/`fetchReplayChunked`.
- **nuovo** `frontend/src/lib/live.valutaReplay.test.ts` (6 test).
- `frontend/src/lib/replay-pnl.ts` — `formatGbp` mostra «€».
- **nuovo** `frontend/src/lib/replay-pnl.formatValuta.test.ts` (3 test).
- `frontend/src/lib/matching.ts` — solo commenti (nessuna logica cambiata: il motore di
  matching era già currency-agnostic, lavora su numeri).
- `frontend/src/components/replay/MarketPanel.tsx`, `TradesPanel.tsx`,
  `ValidationCard.tsx`, `OpportunitaPanel.tsx` — «£» → «€».
- `frontend/src/pages/MatchReplay.tsx` — solo commenti.

**Test**: `npx vitest run src/lib/live.valutaReplay.test.ts
src/lib/replay-pnl.formatValuta.test.ts src/lib/matching.test.ts` → **38/38 verdi** (6 + 3 +
29 preesistenti, invariati), ~20 ms i nuovi. **Falsificazione**: `convertiFrameEur` forzata
a `return frame` (nessuna conversione) → **4/6 rossi**; `formatGbp` rimessa a «£» →
**3/3 rossi** i test dedicati (+ 4 assert generiche negli altri file, verificate a mano);
ripristinati entrambi i file, `grep -c MUTAZIONE` = 0 su entrambi, rilanciato → verde.

**Parità paper/live**: la conversione riguarda SOLO il replay storico (dati registrati);
non tocca il codice del live/paper reale, che dal 26/09 riceve già EUR alla fonte
(`Betfair/stream/valuta.py`, fuori dal mio perimetro).

**Non fatto / non verificabile da qui** (dichiarato, non nascosto):
- **Nessuna migrazione SQL scritta**: non serve. Le RPC `get_replay*` passano `ladder`
  intatta; se in futuro l'importatore Python (fuori perimetro) scrivesse il marcatore, il
  mio codice lo leggerebbe senza altre modifiche.
- **Il cambio storico VERO non è recuperabile da qui**: nessuna registrazione porta il
  cambio del giorno (stesso limite dichiarato nel referto K1 §9.2); uso lo stesso ripiego
  fisso del backend, che può differire dal cambio reale di quel giorno di ±1-2%.
- Non ho verificato dal vivo il Match Replay (app spenta, come da vincolo): la correzione è
  provata con test unitari su frame finti (chiavi/tipi identici al vero, marcatore incluso),
  non con un replay reale aperto in UI.

---

## Voce 5 — Live P&L, tabella tennis: filtro Mode

**Verifica sul codice di master (oggi, nel mio worktree)**: il registro
`AUDIT_2026-09-28/CANTIERE_H_REGISTRO_NC.md` (citato dal brief) lo dà ancora aperto dopo
FIX-A del 26/09, ma **ho riletto `frontend/src/pages/LivePnl.tsx` riga per riga e il filtro
Mode risulta CORRETTAMENTE applicato**:
- `tPositions` (righe tennis, DB + overlay canale) → `tPositionsMode` (riga 222-224):
  `tPositions.filter(p => String(p.mode).toLowerCase() === modeF)`;
- `tByEvent` (righe 299-306, la tabella «🎾 Tennis» a video) deriva **esclusivamente** da
  `tPositionsMode ?? []` — MAI da `tPositions` non filtrato.

Confermato dal test **già esistente** `frontend/src/pages/LivePnl.fixA.test.tsx`, caso
`'LIVE: solo le posizioni live, il tennis paper NON compare, realizzato solo live'`:
`npx vitest run src/pages/LivePnl.fixA.test.tsx --reporter=verbose` → **3/3 verdi** (17
sett 2026, 121-780 ms), incluso esattamente questo caso.

**Esito: OK, nessuna correzione necessaria.** L'entrata del registro NC risulta stale
(scritta prima o senza rileggere FIX-A applicato); lo segnalo al coordinatore perché
aggiorni quel registro, ma non è compito mio modificarlo (appartiene al Cantiere H).

**Nessun file toccato per questa voce.**

---

---

## SECONDA CONSEGNA (28/09 sera) — Indipendenza di ogni bot

Ordine dell'utente, testuale: «OGNI BOT DEVE ESSERE INDIPENDENTE, OVVERO, SE DECIDO DI
ACCENDERNE SOLO 1, PARTE SOLO QUELLO, CHE SIA TENNIS O CALCIO, POSSO SCEGLIERE IO QUALI
BOT ATTIVARE, 1, 2, 3 ECC OPPURE TUTTI INSIEME». Audit su TUTTI i comandi di
accensione/spegnimento a schermo (`frontend/src/lib/interruttori.ts` — il motore condiviso
da pannelli dei bot e Control Room, `frontend/src/components/controlroom/comandiBot.ts`).

### Tabella: ogni pulsante, cosa scrive, prova che tocca SOLO il suo bot

| Bot / variante | Pulsante | RPC (file:riga chiamante) | Tabella (file:riga RPC, verificato `pg_get_functiondef`) | Colonna scritta | Isolamento |
|---|---|---|---|---|---|
| **Omega** | avvia/avvia in prova | `activateOmega` (`lib/omega.ts:1278`) | `omega_control` `WHERE id=1` (RPC `omega_activate`) | `status,mode,daily_goal,params,started_at` | **Riga propria**: nessun'altra tabella toccata |
| Omega | ferma | `stopOmega` (`lib/omega.ts:1288`) | `omega_control` `WHERE id=1` (`omega_stop`) | `status,updated_at` | idem |
| **Mike** | avvia/avvia in prova | `activateMike` (`lib/mike.ts:1939`) | `mike_control` `WHERE id=1` (`mike_activate`) | `status,mode,params,started_at` | **Riga propria** |
| Mike | ferma | `stopMike` (`lib/mike.ts:1945`) | `mike_control` `WHERE id=1` (`mike_stop`) | `status,updated_at` | idem |
| **Safe base/esatto/punta/tennis** (+model/manual) | avvia/avvia in prova/ferma | `activateSafe`/`stopSafe`/`updateSafeParams` (`lib/safeBot.ts:1146,1154,1160`) | **`safe_strategy_control` `WHERE id=1` — UNA riga condivisa da TUTTE E SEI** (`safe_activate`/`safe_stop`/`safe_update_params`) | `status,mode,params` (intera colonna: `params.variants[]` = chi apre, `params.strategy_modes{}` = con che soldi) | **NON strutturale**: dipende dal codice frontend, che compone SEMPRE la mappa intera a partire da una lettura FRESCA (`accensioniCorrenti`/`statoSafeFresco`, `interruttori.ts:716-822`), mai da un frammento. Vedi sotto. |
| **Scalper calcio (+ sniper)** | avvia/ferma | `attivaScalperAuto`/`fermaScalperAuto` (`lib/scalperControlRoom.ts:165,176`) | `scalper_service_control` `WHERE id=1` (`scalper_auto_activate/_stop`) | `status,mode,stake,strategia,params` | **Riga propria**, un solo bot (sniper e' una `strategia` dentro la stessa riga, non un bot separato: non ha un pulsante suo) |
| **tennis_scalper / tennis_pro / tennis_flb / tennis_swing** (ciascuno) | avvia/avvia in prova/ferma | `activateTennisBotService`/`stopTennisBotService` (`lib/tennis.ts:992,1006`) | `tennis_bot_service_control` **`WHERE bot_key = p_bot_key`** (`tennis_bot_service_activate/_stop`, verificato: `INSERT ... ON CONFLICT (bot_key) DO UPDATE` e `UPDATE ... WHERE bot_key=p_bot_key`) | `status,mode,stake,params` DELLA SOLA riga con quel `bot_key` | **Riga propria per bot_key**: strutturale, verificato nell'SQL vero |

### Il caso Safe — perche' l'indipendenza NON e' automatica, e come regge

Le 4 strategie del manuale (+ le 2 voci-strumento `model`/`manual`) condividono UNA riga
(`safe_strategy_control`, id=1): `safe_activate`/`safe_update_params` fanno
`params = coalesce(p_params, params)` — chi scrive decide l'INTERA colonna. Un frammento
(es. «scrivo solo `variants:['tennis']`») cancellerebbe le altre. L'indipendenza qui la
garantisce il CODICE FRONTEND:
1. **Lettura fresca prima di scrivere**: `conCambio`/`statoSafeFresco` (path generico,
   pagine dei singoli bot, `interruttori.ts:716-822`) e `sorgenteConRilettura.rileggiSafe`
   (path Control Room, `comandiBot.ts:103-136`, REPERTO A del 18/09) rileggono
   `variants`/`strategy_modes` dal DATABASE appena prima di scrivere, non da uno snapshot
   React potenzialmente vecchio.
2. **Si scrive SOLO la voce del bot toccato**: `paramsAccensioni` (`interruttori.ts:353-385`)
   ricompone la mappa intera preservando ogni voce non toccata con il suo valore CORRENTE.
3. **Voce 2 di questa consegna** ha esteso questa stessa garanzia al gesto della scheda
   tennis (`comandiBot.ts::soloTennis`), che fino a oggi la violava (sostituiva, non
   aggiungeva).

**Prova con test falsificati** (nuovi, in questa consegna):
- `frontend/src/lib/interruttori.test.ts`:
  - *«due accensioni ravvicinate su strategie DIVERSE, in modalita DIVERSE: nessuna
    sovrascrive l'altra»* — accendo base in LIVE poi, subito dopo, esatto in PAPER (path
    generico, quello delle pagine dei singoli bot): entrambe le modalita' restano quelle
    volute. **Falsificato**: `paramsAccensioni` mutata per ignorare `acc` e scrivere
    sempre `'live'` → **11/74 test rossi** (compreso questo), ripristinato,
    `grep -c MUTAZIONE`=0, rilanciato → 74/74 verdi.
  - *«accendere una strategia non riaccende un'altra che l'operatore ha spento apposta»*
    — accendo punta con base gia' accesa, esatto e tennis esplicitamente FUORI da
    `variants`: restano fuori.
- `frontend/src/components/controlroom/comandiBot.test.ts`:
  - *«Safe calcio GIA' acceso, clic "avvia" dalla scheda TENNIS: il calcio non sparisce»*
    — riproduce ESATTAMENTE lo scenario del reperto CRONOSTORIA 26/09 h11:25 (base gia'
    acceso in paper PRIMA del clic tennis), poi un secondo clic ravvicinato dalla scheda
    calcio (accendo esatto): nessuno dei tre si cancella o cambia modalita' a sua insaputa.
    **Falsificato**: `soloTennis` rimessa al comportamento sostitutivo pre-cantiere →
    **rosso** (`expected ['tennis'] to deeply equal ['base','tennis']`), ripristinato,
    `grep -c MUTAZIONE`=0, rilanciato → 13/13 verdi.

**Test**: `npx vitest run src/lib/interruttori.test.ts
src/components/controlroom/comandiBot.test.ts` → **87/87 verdi** (74 + 13, di cui 4 nuovi),
~7 s. `npx tsc -p tsconfig.app.json --noEmit` → **0 errori**.

### File toccati (seconda consegna, punto 1)
- `frontend/src/lib/interruttori.test.ts` — 2 test nuovi (nessuna modifica al codice: il
  path generico era gia' corretto, qui lo si prova esplicitamente per la modalita' e per
  gli spenti).
- `frontend/src/components/controlroom/comandiBot.test.ts` — 1 test nuovo (il codice era
  gia' quello corretto per voce 2, qui si prova lo scenario esatto del reperto).

**Nessuna correzione di codice necessaria in questo punto**: l'audit ha confermato che la
correzione della voce 2 (prima consegna) e il path generico gia' esistente coprono TUTTI
gli scenari richiesti dall'utente. Non ho trovato un secondo caso di violazione oltre a
quello gia' corretto in voce 2.

### Reperto sul BACKEND (Python, NON toccato)

Lettura mirata (non esaustiva: `bot_service.py` supera le 9000 righe) di
`Betfair/safe_strategy/bot_service.py` per ogni uso di `variants`: l'unico effetto che il
cambio di `variants` produce nel motore e' un **gate di appartenenza** — «questa strategia
puo' aprire ORA?» (`bot_service.py:6486`, `if variants and variant not in variants:
continue/skip`) — non ho trovato nessun punto che RESETTI stato di un'ALTRA strategia
(posizioni aperte, contatori, cap) quando `variants` cambia. Lo stesso per
`tennis_bot_service_control` (righe separate per `bot_key`: nessun motivo strutturale per
un bot di leggere la riga di un altro). **Non e' un audit esaustivo del backend** (fuori
dal mio perimetro, e non l'ho fatto grep-per-grep su tutto il file): se il coordinatore
vuole la certezza assoluta, serve un delegato con permesso di leggere (sola lettura)
`Betfair/safe_strategy/bot_service.py` e `Betfair/stream/tennis_live/*` per intero.

---

## Voci 6 e 7 — stato: PARZIALE, aggiornato nella seconda consegna (28/09 sera)

**Non ho completato le voci 6 e 7.** Di seguito cosa ho fatto, cosa no, e perché — per
non dichiarare fatto ciò che non ho controllato riga per riga (§4.8 del brief).

### Il banco `frontend/e2e_fase3_admin26/` — COPIATO, ma non eseguibile dal mio worktree

Come indicato dal coordinatore nella seconda consegna, il banco (74 file: `clientSpecchio.ts`
con le guardie di sola lettura, `comune.ts`, `pagine.fase3.test.tsx`,
`controlroom.fase3.test.tsx`, `Prov.tsx`, `vitest.fase3.config.ts`) è stato **copiato
in sola lettura sull'originale** da `.../python-database-automation/frontend/
e2e_fase3_admin26/` (checkout principale, non tracciato) dentro il mio worktree, con
`cp -r` (74/74 file, nessuna scrittura sull'originale).

**Blocco reale, non aggirabile senza una decisione del coordinatore**: `clientSpecchio.ts`
(riga 17: `const ENV_PATH = resolve(__dirname, '../../.env')`) richiede il file `.env` della
RADICE del repo (chiave `SUPABASE_SERVICE_ROLE_KEY`). Il `.env` è **assente in OGNI
worktree** (verificato: nessuno dei 23 worktree in `.claude/worktrees/` lo ha — è
git-ignorato e non condiviso, per costruzione, non per un mio errore). Copiare una chiave
service-role dentro un worktree di delegato (che puo' essere scartato, mai committato per
regola) mi e' sembrato un rischio da NON prendere di iniziativa: non l'ho fatto. Il banco
resta quindi presente ma INERTE nel mio worktree finché il coordinatore non decide come
procedere (vedi proposta sotto).

### Cosa ho fatto invece (metodo diverso, dichiarato, con dati REALI)

Per un sottoinsieme dei campi ho fatto verifiche EQUIVALENTI ma non identiche a quanto
chiesto: letture dirette del DB in sola lettura (query `SELECT`/`pg_get_functiondef` sul
progetto Supabase `dqbwaocvlzbxfrpacsac`, MAI scrittura) per ottenere righe VERE
`mode='live'` (chiavi e tipi identici, non finte), confrontate con la lettura del codice
della funzione pura che calcola il campo — senza montare la pagina React intera. Dove il
finto è entrato in un test, è la riga REALE (id citato), non un'invenzione.

**Voce 6 (22 campi solo-live), verificato realmente 2 di 22:**
- **U0222** (Mike, «uscita appoggiata SPENTA in live») — vedi sopra (prima consegna):
  DB `mike_control.params.live_resting_enabled` = `null`; `leggiBool` → `null`; banner
  nascosto (confronto stretto `=== false`). **OK.**
- **U0240** (`DettaglioRigaView.tsx:246`, «chiusa da te», sorgente `lib/chiusuraUtente.ts`)
  — riga VERA `safe_strategy_trades.id=335` (`mode='live'`, evento `36093424`,
  `meta.chiuso_dall_utente = {come:'fuori_app', quando:'2026-09-22T13:38:44...', ...}`,
  letta oggi in sola lettura). Nuovo test
  `frontend/src/lib/chiusuraUtente.campoLive.test.ts` (3 test): `marcatoreRiga` legge
  `come='fuori_app'`/`quando` esattamente come nella riga; `statoChiusuraEvento` la
  dichiara chiusa con `fonte:'righe'`; un `event_id` diverso NON risulta chiuso (nessun
  contagio fra partite). **OK** — i due numeri: valore grezzo del `meta` reale vs valore
  letto dalla funzione, identici campo per campo.
- Le altre **20** (U0179-U0181, U0184-U0187, U0193, U0223, U0245, U0255, U0258, U0263,
  U0264, Segui Live U0302, U0312, U0337, U0344): **NON VERIFICATE.** Nota su **U0223**
  («fonti non raggiunte»): il file:riga dell'inventario (`useControlRoom.ts:1320-1325`)
  punta a un'altra logica (`soldiLetti`); la costruzione vera dell'elenco «fonti non
  raggiunte» è probabilmente quella già certificata dal test ESISTENTE
  `useControlRoom.test.tsx` (docblock: «UNA FONTE CHE CADE SI CHIAMA PER NOME», `FONTI_RICARICA`)
  — non l'ho riverificata oggi, la segnalo come probabilmente già coperta, non come fatta da me.

**Voce 7 (14 controlli ad app spenta), verificato realmente 1 di 14 (invariato dalla
prima consegna — nessun tempo aggiuntivo speso qui nella seconda consegna, priorità data
alla voce 6 e al punto 1):**
- **U0226** — vedi sopra: `coperturaControllo`, 17/20 = 85,0%, SQL indipendente vs
  funzione, coincidono. **OK.**
- Le altre **13** (U0134, U0135, U0508, U0230, U0231, U0234, U0238, U0246, U0247, U0248,
  U0250, U0251, U0266): **NON VERIFICATE.**

### Cosa va fatto per completare (proposta al coordinatore)

1. **Il `.env` per il banco**: o il coordinatore lancia lui `controlroom.fase3.test.tsx`/
   `pagine.fase3.test.tsx` (ha accesso al `.env` nel checkout principale) — eventualmente
   con righe finte iniettate in un client-specchio modificato che unisce ai dati veri
   righe sintetiche `mode='live'` per le tabelle che alimentano i 22 campi — oppure
   autorizza esplicitamente la copia del `.env` in UN worktree di delegato dedicato,
   sapendo che e' una chiave service-role.
2. Le **20 + 13 = 33 verifiche ancora mancanti** sono tutte descritte con file:riga
   nell'inventario (`INVENTARIO_CAMPI_UI_2026-09-25.md`) e nel registro
   (`AUDIT_2026-09-28/CANTIERE_H_REGISTRO_NC.md` §8.1): un prossimo delegato può
   ripartire da lì senza re-inventariare. Il metodo «riga VERA `mode='live'` letta in
   sola lettura + funzione pura + ricalcolo indipendente» (usato per U0222/U0226/U0240)
   è riusabile per ogni campo la cui sorgente è una funzione pura testabile fuori da React
   (la maggioranza dell'elenco); solo i campi che dipendono da RENDER effettivo del
   componente (es. presenza/assenza di un elemento a video, non solo il VALORE) richiedono
   davvero il montaggio della pagina, quindi il banco.

---

## Elenco esatto dei file toccati (tutti nel worktree, NON committati)

**Codice (10 file)**:
1. `frontend/src/components/controlroom/useControlRoom.ts`
2. `frontend/src/components/controlroom/comandiBot.ts`
3. `frontend/src/components/controlroom/soloTennis.ts`
4. `frontend/src/pages/ControlRoom.tsx`
5. `frontend/src/lib/rese.ts`
6. `frontend/src/components/dashboard/MatchesList.tsx`
7. `frontend/src/lib/live.ts`
8. `frontend/src/lib/replay-pnl.ts`
9. `frontend/src/lib/matching.ts` (solo commenti)
10. `frontend/src/components/replay/MarketPanel.tsx`,
    `frontend/src/components/replay/TradesPanel.tsx`,
    `frontend/src/components/replay/ValidationCard.tsx`,
    `frontend/src/components/replay/OpportunitaPanel.tsx` (solo testo/commenti, «£»→«€»)
11. `frontend/src/pages/MatchReplay.tsx` (solo commenti)

**Test modificati (4 file)**:
- `frontend/src/components/controlroom/comandiBot.test.ts` (prima + seconda consegna)
- `frontend/src/components/controlroom/soloTennis.test.ts`
- `frontend/src/pages/ControlRoom.test.tsx`
- `frontend/src/lib/interruttori.test.ts` (seconda consegna, 2 test nuovi)

**Test nuovi (5 file)**:
- `frontend/src/components/controlroom/useControlRoom.effettiviStantii.test.ts`
- `frontend/src/lib/live.valutaReplay.test.ts`
- `frontend/src/lib/replay-pnl.formatValuta.test.ts`
- `frontend/src/lib/chiusuraUtente.campoLive.test.ts` (seconda consegna, voce 6, U0240)
- (`frontend/src/lib/rese.test.ts` esteso, non nuovo)

**Banco copiato (sola lettura sull'originale, seconda consegna)**:
`frontend/e2e_fase3_admin26/` (74 file) — presente nel worktree ma INERTE (manca `.env`,
vedi sezione voci 6-7).

**Nessuna migrazione SQL scritta** (nessuna correzione richiedeva RPC/schema nuovi).

**Git**: commit locale `afbbdc8` (prima consegna, 23 file), merge `origin/master`
(`3ddd6f9`, nessun conflitto — i 47 file del merge sono tutti Python/documentazione di
altri cantieri, nessuna sovrapposizione col frontend). Nessun push, nessun `git add -A`.

## Verifica complessiva

- `npx vitest run` sui file toccati/nuovi (prima + seconda consegna) + `ControlRoom.test.tsx`
  + `LivePnl.fixA.test.tsx`/`LivePnl.test.tsx` + `interruttori.test.ts`: **287/287 verdi**
  (215 prima consegna + 87 su comandiBot/interruttori dopo le aggiunte + 3 su
  `chiusuraUtente.campoLive.test.ts`, con qualche sovrapposizione fra i giri), rilanciato
  anche DOPO il merge con `origin/master` (nessuna regressione). Nessun file intero
  rilanciato (rispettato il vincolo carico PC).
- `npx tsc -p tsconfig.app.json --noEmit`: **0 errori**, rilanciato anche dopo il merge.
- 8 falsificazioni totali (6 prima consegna + 2 seconda consegna: `paramsAccensioni`
  mutata su tutte-live → 11/74 rossi in `interruttori.test.ts`; `soloTennis` rimessa
  sostitutiva → rosso sul test del reperto esatto in `comandiBot.test.ts`), ripristino
  verificato con `grep -c MUTAZIONE` = 0 su ogni file mutato.

## Decisioni per l'utente

1. **Voce 2 — CHIUSA.** L'utente ha confermato il 28/09 (testuale, vedi sopra) che
   l'accensione di un bot/variante deve essere sempre additiva: nessuna riserva residua.
2. **Voce 4 — cambio GBP/EUR di ripiego, non quello vero del giorno.** Come per il backend
   (già segnalato nel referto K1), il Match Replay userà un cambio fisso approssimato
   (1,164687) finché nessuno salva il cambio vero nella registrazione. Differenza tipica
   ±1-2% sugli importi di partite registrate prima del 26/09 (tutte, oggi).

## Cosa controllare dal vivo in paper al prossimo avvio dell'app

1. **Voce 1**: subito dopo un riavvio dell'app, accendere Safe (qualunque modalità) e
   verificare che il pulsante «avvia» delle altre strategie compaia SUBITO (non «dopo
   qualche minuto»). Dato atteso: righe corrette immediatamente dopo il clic; dove
   leggerlo: scheda calcio della Control Room, riga «Safe base/esatto/punta».
2. **Voce 2**: con Safe calcio già acceso (es. base in paper), cliccare «avvia in prova»
   dalla scheda tennis. Dato atteso: la riga «Safe base» resta ACCESA (non sparisce); la
   nota sopra il pulsante dice «AGGIUNGE... senza toccare le strategie di calcio». Dove
   leggerlo: scheda tennis della Control Room.
3. **Voce 3**: aprire la lista partite fra le 00:00 e le 02:00 (ora di Roma): verificare
   che compaiano le partite di QUELLA fascia e non quelle del giorno dopo. Dove leggerlo:
   Dashboard, lista partite del giorno.
4. **Voce 4**: aprire un Match Replay su una registrazione qualunque (tutte, oggi, sono
   pre-K1 = GBP convertite): verificare che gli importi (stake, position, cash out) siano
   plausibili in EUR (non ~16% più bassi come sarebbero letti come sterline non convertite)
   e che il simbolo sia «€», non «£». Dove leggerlo: pagina Match Replay, pannello mercato
   e pannello trade.
