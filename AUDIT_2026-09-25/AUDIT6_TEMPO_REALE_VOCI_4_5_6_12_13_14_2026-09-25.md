# AUDIT 6 - TEMPO REALE, voci 4, 5, 6, 12 (solo xhedge), 13, 14 (25/09/2026)

Delegato Opus (sessione B). Worktree `agent-a588c29842c66dcc0`. **Base finale: `origin/master` a
`09d9791`** (partito da `fcc99e7`; riallineato su `000d8f6` con conflitto risolto in
`useControlRoom.ts` conservando INTERO il blocco scalper 47338 dell'altra sessione, poi
fast-forward a `09d9791`, che non tocca i miei file). NIENTE commit. Nessun file toccato sotto
`Betfair/omega`, `Betfair/mike`, `Betfair/safe_strategy`, `Betfair/stream/tennis_live`,
`Betfair/stream/scalper`; `runner.py` e `live_order_worker.py` solo letti. Le righe dello
scalper in `useControlRoom.ts` non sono state toccate. Nessun processo nuovo, nessun accesso al DB.

Fonte dell'elenco: `AUDIT_2026-09-24/AUDIT_TEMPO_REALE_2026-09-24.md` par. 3.

Regola applicata ovunque ("overlay sul poll, mai unione", come `lib/righeCanale.ts`):
il poll/realtime del database decide QUALI righe/stati esistono; il canale sovrappone campi di
righe gia' note SOLO se strettamente piu' recente (istante del PRODUTTORE); canale giu' -> si
torna al database; fonte ed eta' dichiarate a video.

---

## Voce 4 - stato / modalita' / interruttori dei bot dal push `*_stato`

**Cosa faceva.** `useControlRoom.ts` usava `safe_stato` e `mike_stato` SOLO come orologio
(`ultimoPush`); il contenuto arrivava al poll dei 30 s (`RICARICA_MS`). Omega usava `stats` del
push, ma solo per obiettivo/realizzato e sostituendo l'oggetto INTERO (le chiavi timbrate sul DB,
es. `fermato_all_avvio_at`, sparivano) e senza confronto di freschezza.

**Cosa fa.** Nuovo modulo puro `frontend/src/lib/statoBotCanale.ts`:
- `leggiPushStato` valida i messaggi VERI: `omega_stato` (`Betfair/omega/omega_service.py:7816`,
  `{stats, last_cycle}`), `safe_stato` (`Betfair/safe_strategy/bot_service.py:9310`, idem),
  `mike_stato` (`Betfair/mike/service.py:4904`, `{control, aggregates, stats, published_ts}`,
  `control` = `select *` di `mike_control` letto a inizio giro, :2621).
- `sovrapponiControl(dbControl, push)`: riga mai letta -> nessuno stato (mai unione); `stats` dal
  push solo se `last_cycle` STRETTAMENTE piu' recente di quello della riga, sovrapposti PER
  CHIAVE (restano le chiavi che il bot aggiunge solo scrivendo: timbro d'avvio,
  `fermato_all_avvio_at`); colonne della riga (solo Mike: status, mode, params...) solo se
  `control.updated_at` del push e' STRETTAMENTE piu' recente di quello letto (a parita' vince il
  DB: un parametro appena salvato dalla pagina non torna indietro per un giro del bot partito
  prima del salvataggio).
- In `useControlRoom.ts`: stato `pushStato` (righe 1060-1075), viste `omega`/`safe`/`mike` con
  la riga di control sovrapposta (tutto il resto della pagina le legge senza sapere la fonte);
  sottoscrizione `*_stato` (righe 1441-1449) che salva il CONTENUTO; alla caduta del canale il
  push si butta (riga 1439). `safe.params_effective` segue gli `stats.params_effective` del push
  (modi per strategia). `StatoBot` ha `fonteStato` ('canale'|'database') ed `etaStatoS`.
- A video: chip del bot in testata (`ControlRoom.tsx`, `data-testid="cr-bot-fonte-<bot>"`):
  "stato canale N s" / "stato db N s".

**Cosa arriva ora al ritmo del bot (non piu' a 30 s):**
- Safe (giro 2 s): motivo del blocco, tetto/esposte, cadenza, `risk` (freni in testata),
  `params_effective` (modi per strategia calcio/tennis), realizzato.
- Mike (giro 1-5 s): status, mode, params (interruttori, `mikeRestingLive`), stats.
- Omega (giro 5-60 s): stats (realizzato, target, eventi chiusi dall'utente, motivo...).

**Cadenza prima/dopo:** contenuto 30 s -> giro del bot (Safe 2 s, Mike 1-5 s, Omega 5-60 s);
poll 30 s invariato come ripiego.

**Cosa manca lato bot (NON toccato: file di strategia):** `omega_stato` e `safe_stato` NON
pubblicano `status`, `mode`, `params` (ne' `updated_at` della riga): modalita' e interruttori di
Omega e Safe restano al poll dei 30 s (piu' la ricarica dopo ogni comando della pagina). Per
chiuderlo basta aggiungere al payload le colonne della riga di control gia' in memoria nel giro:
`Betfair/omega/omega_service.py:7816` (`_pubblica_stato`) e
`Betfair/safe_strategy/bot_service.py:9310` (`_pubblica_stato`), come fa gia' Mike
(`Betfair/mike/service.py:4904`). Il frontend e' gia' pronto: `leggiPushStato` accetta il
`control` solo da Mike; basta estendere la condizione.

## Voce 5 - tennis nella scheda partita dal canale

**Cosa faceva.** `useTennisVivo.ts` leggeva solo il realtime Supabase `tennis_live_now`
(fetch + `subscribeTennisNow`), fonte non dichiarata.

**Cosa fa.** La voce condivisa per evento ascolta ANCHE il topic `now` del runner tennis (47332,
stesso singleton `getLocalChannel`, nessun socket nuovo). Il messaggio e' la STESSA riga di
`tennis_live_now` (`Betfair/stream/tennis_live/tennis_db.py:279-291`, push PRIMA della scrittura
cloud). Fra canale e realtime vince la riga con `updated_at` del produttore STRETTAMENTE piu'
recente (`istanteMicro` di `lib/canaleRunner.ts`, microsecondi); a parita' resta la riga gia'
mostrata (stessa scrittura dall'altra strada, la fonte non "sfarfalla"). Le righe di altre
partite sul topic si ignorano. `TennisVivo.fonte` ('canale'|'database'); in `SchedaPartita.tsx`
accanto all'eta' (`data-testid="cr-tennis-vivo-fonte"`): "canale" / "db".
**Scelta motivata:** `scan_tennis` (47336) NON usato: porta la riga di `safe_strategy_scan`
(altra forma: minuto/punteggio calcio-centrici), tradurla in `TennisLiveNowRow` sarebbe una
seconda formula. Il `now` del 47332 copre le partite SEGUITE dal runner tennis; per le altre resta
il realtime (ripiego dichiarato "db").

**Cadenza prima/dopo:** realtime Supabase (~2 s di scrittura + propagazione cloud) -> push locale
al giro `score_and_now_worker` del runner tennis (`tennis_runner.py:1197,1937`, 2 s) prima della
scrittura cloud; realtime invariato come ripiego.

## Voce 6 - runner calcio/tennis e "Ordini reali OFF/PAPER/LIVE"

**Cosa faceva.** Riga "Runner" = `betfair_live_heartbeat` + conteggio `live_follow` al poll di
30 s, con eta' CONGELATA all'istante della lettura (`runnerStateFrom(..., Date.now())` in
`fetchRunnerState`); runner tennis assente (non ha battito su tabella). "Ordini reali" = RPC
`get_live_settings` ogni 30 s.

**Cosa fa.** Nuovo modulo puro `frontend/src/lib/runnerCanale.ts`.
- Payload VERI letti da `runner.py` (non modificato): `hello` a ogni connessione
  (`local_channel.py:353` = `{sport, mode}`; `runner.py:1798` `set_hello(mode=modo_avvio)`,
  `tennis_runner.py:1790`); battito di fatto = `account` (`reconcile_worker.py:161`, ~20 s, anche
  col runner in attesa: `runner.py:1901`), `ladder` (`runner.py:718`, 200 ms, mercati seguiti),
  `now` (`db.py:294-309`, 5 s per partita seguita; `state` con `order_mode`, `order_mode_tetto`,
  `order_mode_scelto`, `updated_ms`: `runner.py:292-302`), `board`/`order`/`position`.
- `useControlRoom.ts` (blocco "voce 6", riga 1674, dopo il blocco scalper): per 47331 e 47332 raccoglie
  connessione, `hello`, ultimo messaggio e ultimo `ladder`/`now` in un riferimento, fotografato
  una volta al secondo (nessun render per messaggio: la ladder corre a 200 ms).
  `runnerDalCanale`: canale connesso = processo vivo (il socket e' servito dal processo del
  runner), eta' = ultimo messaggio, "in streaming" se `ladder`/`now` da <= 15 s (il silenzio NON
  toglie lo streaming letto dal DB); modalita' del DB se c'e' (`LIVE+PAPER`), altrimenti
  dell'hello. Canale spento: riga del DB con eta'/vivo ricalcolati ADESSO.
- VM: `runner` (calcio, sovrapposto), `fonteRunner`, `runnerTennis` (solo canale; null =
  "canale spento"), `fonteRunnerTennis`. `ControlRoom.tsx`: chip "Runner" e nuovo chip
  "Runner tennis" con fonte ed eta' (`cr-runner-fonte`, `cr-runner-tennis`,
  `cr-runner-tennis-fonte`); la spia REC tennis usa il runner tennis se il canale e' connesso
  (prima usava il runner calcio).
- `RigaOrdiniReali.tsx`: ascolta 47331 (`hello`, `now`). `sovrapponiModoOrdini`: riga mai letta ->
  nessuna sovrapposizione; tetto = `hello.mode` del runner collegato (il SUO .env); effettivo =
  `state.order_mode` del `now` se fresco (<= 15 s) e piu' recente della lettura; se il runner
  dichiara una SCELTA diversa da quella letta -> rilettura RPC SUBITO (al piu' 1 ogni 2 s; chi e
  quando stanno solo sul DB). Fonte ed eta' a video (`cr-ordini-reali-fonte`). Poll 30 s invariato.

**Cadenza prima/dopo:** runner 30 s (eta' ferma) -> 1 s di orologio pagina su notizie del canale
(calcio: account ~20 s, ladder 200 ms, now 5 s); runner tennis: prima assente -> canale.
Ordini reali 30 s -> `now` 5 s (con partite seguite) + rilettura immediata su divergenza.

**Cosa manca lato runner (NON toccati `runner.py`/`live_order_worker.py`, file di un'altra
sessione):**
1. Nessun topic di BATTITO sul canale. Il vivo/in attesa/streaming si deduce da connessione +
   `account` (calcio, ~20 s) + `ladder`/`now`. Il runner TENNIS in attesa non pubblica nulla
   (nessun `account` periodico: `saldo_evento` solo su evento, `tennis_runner.py:1756`), quindi
   la sua eta' cresce pur essendo vivo (il chip dice "vivo" perche' il socket e' connesso, ma
   l'eta' e' quella dell'hello). Proposta: pubblicare `battito` `{ts, mode: heartbeat_mode(),
   streaming: <n follow STREAMING>}` dove oggi si scrive `betfair_live_heartbeat`:
   `runner.py:1089-1098` (`heartbeat_worker`) e `runner.py:1889-1893` (idle); equivalente nel
   runner tennis.
2. Il modo ordini EFFETTIVO e la SCELTA viaggiano solo dentro `now`, cioe' solo con partite
   seguite. Senza partite la riga "Ordini reali" resta al poll 30 s (+ tetto dall'hello).
   Proposta: pubblicare `modo_ordini` (`modo_ordini.stato_corrente()`, `modo_ordini.py:188`) al
   cambio, dove il worker lo registra: `live_order_worker.py:475-496` (`_refresh_settings` ->
   `_mo.registra_settings`).

## Voce 12 - xhedge sul canale (solo xhedge; lo scalper NON e' mio)

**Cosa faceva.** `xhedge_worker.py` scriveva `betfair_live_xhedge` SOLO sul DB; `XHedgePanel`
poll ogni 5 s.

**Cosa fa.**
- `Betfair/stream/canale_bot.py`: topic nuovo `"betfair_live_xhedge"` nella mappa `TOPIC`.
- `Betfair/stream/xhedge_worker.py` (`_process_once`): dopo l'upsert riuscito
  `_cb.pubblica_scritte(_cb.TOPIC["betfair_live_xhedge"], res)`: il messaggio E' la riga
  restituita dalla scrittura (id, event_id, mode, analysis, updated_at) + busta
  (`fonte`, `_seq`, `_pubblicato_ms`). Esce sul canale del processo (runner calcio, 47331); senza
  canale `_invia` non fa nulla; non solleva mai; upsert fallito -> nessun messaggio.
- Frontend: modulo puro `frontend/src/lib/xhedgeCanale.ts` (valida la busta con
  `leggiMessaggioRiga`, chiave (evento, modo), vince solo `updated_at` strettamente piu' recente,
  mai unione, pota al poll nuovo); `XHedgePanel.tsx` si abbona a `getLocalChannel('calcio')`
  topic `betfair_live_xhedge`, mostra "fonte canale/db" (`data-testid="xhedge-fonte"`); la
  guardia money-critical "analisi fresca 30 s" resta identica (stesso `updated_at` del worker).
  Poll 5 s invariato come ripiego.
- **Decisione da confermare (coordinatore):** nessun interruttore `.env` per xhedge (il brief:
  "spento se il canale manca"); la regola 5 di `canale_bot.py` parla di interruttore per processo
  default spento per i BOT. Qui e' dato di sola lettura nel runner; se si vuole l'interruttore, e'
  una riga (`acceso("XHEDGE_CANALE")` attorno a `pubblica_scritte`).

**Cadenza prima/dopo:** UI 5 s di poll (+ fino a 5 s del worker) -> subito dopo la scrittura
(`XHEDGE_POLL_SEC` 5 s del worker, `config_stream.py:289`).

## Voce 13 - pagine fuori dalla Control Room

| pagina / pannello | prima | dopo | nota |
|---|---|---|---|
| SeguiLive - `LiveTradingPanel` (3 s) | ordini+posizioni solo poll | overlay `order` + `position` da 47331 (`useOrdiniCanale`, `usePosizioniCanale`), fonte `ltp-fonte-posizioni` | poll 3 s resta |
| SeguiLive - `TerminalPositionsRail` (4 s) | idem | idem, fonte `rail-fonte-posizioni` | poll 4 s resta |
| SeguiLive - `XHedgePanel` (5 s) | poll | voce 12 | poll 5 s resta |
| SeguiLive - follows (15 s) | poll | INVARIATO | nessun topic: `live_follow` non va sul canale |
| SeguiLive - `RiskRulesPanel` (4 s) | poll | INVARIATO | nessun topic per le regole di rischio |
| SeguiLive - `HabitatCard` (60 s) | poll | INVARIATO | legge `fetchScalperState('habitat')`: scalper, non mio |
| SeguiLive - avviso LAPSE (15 s) | gia' via `localOrders` (snapshot del canale) se connesso | invariato | gia' sul canale |
| SeguiLive - ladder/now/posizioni evento | gia' overlay (23/09) | invariato | - |
| MarketWatch - follows (30 s) | poll | INVARIATO | nessun topic |
| MarketWatch - now/posizioni | gia' overlay | invariato | - |
| LivePnl - posizioni calcio/tennis (15 s) | poll | overlay `position` 47331/47332, fonte `livepnl-fonte-posizioni` | poll 15 s resta |
| LivePnl - settled (30 s) | poll | INVARIATO | nessun topic per i regolati per giornata (`account.pnl_reale_oggi` e' un aggregato diverso) |
| LivePnl - risk state | realtime | invariato | - |

Ordini: nuovo modulo puro `frontend/src/lib/ordiniCanale.ts` + `lib/useOrdiniCanale.ts`, gemelli
di `canaleRunner.ts`/`usePosizioniCanale.ts`: messaggio VERO `order` = `_order_row`
(`Betfair/stream/engine/live_trading_strategy.py:324-347`) + `updated_at` (`db.py:535-552`),
chiave unica (mode, client_order_ref), sovrappone SOLO le colonne che vivono con l'ordine
(bet_id, stato, abbinato/residuo/annullato/decaduto/annullato, prezzo medio, matched_at);
mode e chiave mai toccati. Nessun topic nuovo lato Python oltre a xhedge.

## Voce 14 - igiene

- Commento stantio `ControlRoom.tsx` ("oggi i canali locali sono muti") riscritto: spiega quando
  la fonte e' "canale locale" e quando "database".
- `scanner_stato` ORA SOTTOSCRITTO (`useControlRoom.ts` 1349-1361). Messaggio VERO:
  `Betfair/safe_strategy/service.py:1519` = lo STESSO `payload` che un istante dopo va in
  `safe_strategy_status` (`service.py:1797-1849`, `db.py:182`). `statoScannerDalCanale`: riga mai
  letta -> nulla; sovrappone `payload` con `updated_at` = istante di RICEZIONE (il push non ha un
  istante suo; e' locale, ms) solo se piu' recente della riga. Il realtime `safe_strategy_status`
  resta come ripiego. A video: "stato canale/db" (`cr-fonte-stato-scanner`) accanto all'eta' del
  feed. Motivo della scelta (sottoscrivere invece di dichiarare il solo realtime): l'eta' del
  feed decide se una quota e' "vecchia" (approvabilita' delle chiusure); col canale si aggiorna
  al giro dello scanner senza passare dal cloud.

---

## Test (numeri)

Frontend, file toccati/creati (22 file, **420 test verdi**):
`npx vitest run` su statoBotCanale.test, runnerCanale.test, useControlRoom.statoCanale.test
(nuovi, 13+13+12), useControlRoom.test / .righeCanale / .righeNuove / .scalperCanale (92,
invariati e verdi), pages/ControlRoom.test (112, +6 nuovi), RigaOrdiniReali.test (28) +
RigaOrdiniReali.canale.test (4 nuovi), PannelloBot.test, useTennisVivo.test (invariato) +
useTennisVivo.canale.test (6 nuovi), SchedaPartita.test (+1 asserzione), XHedgePanel.test (22) +
XHedgePanel.canale.test (6 nuovi), LiveTradingPanel.test, TerminalPositionsRail.test,
posizioniCanale.pannelli.test (6 nuovi), LivePnl.test, canaleRunner.test, usePosizioniCanale.test.
I due file sensibili al tempo (RigaOrdiniReali.canale, useControlRoom.statoCanale) rieseguiti 3
volte: 16/16 ogni volta.
`npx tsc -p tsconfig.app.json --noEmit`: **0 errori** (nessun `@ts-ignore`, nessun `any` nuovo).
Pytest (con `SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x`):
`test_xhedge_worker.py` (+4 nuovi) + `test_canale_bot_f3_2026_09_18.py` +
`test_canale_bot_cancellazione_c6c_2026_09_23.py`: **54 passed**.

Finti: ogni finto cita nel suo file di test il produttore vero (file:riga) e ne copia chiavi e
tipi (busta di `canale_bot` compresa per xhedge; righe di control `select *`; `now`/`position`/
`order` come escono da `db.py`/`tennis_db.py`/`_order_row`).
Nota: in `useControlRoom.ts` la lettura dell'`hello` e' protetta da `typeof ch.getHello ===
'function'` perche' alcuni finti storici di altri file di test non hanno `getHello` (il canale vero
si'); non ho toccato quei test (non miei).

## Falsificazioni (tutte ROSSE, poi ripristino da copia di riserva, mai `git checkout`)

Hash di `git diff` prima = dopo = `a447f14d830473cb...` (ripristino byte per byte verificato;
`sha256sum -c` sui 4 moduli nuovi: OK). Output (vitest):

```
F1 voce4 freschezza stats ignorata (statoBotCanale.ts)            ROSSO  3 failed | 22 passed
   x giro NON piu' recente (pari o vecchio): vince il database
   x Mike: versione della riga PARI -> vince il database
   x hook: Safe: un giro NON piu' recente della riga letta non cambia niente
F2 voce4 push ignorato, torna il poll (useControlRoom.ts)         ROSSO  5 failed | 7 passed
   x Safe motivo del blocco / modi per strategia / Mike modalita' e interruttori /
     canale giu' / Omega realizzato per chiave
F3 voce4 unione al posto di mai unione (statoBotCanale.ts)        ROSSO  2 failed | 23 passed
   x riga mai letta: il canale non crea lo stato (puro + hook)
F4 voce5 topic now tennis non ascoltato (useTennisVivo.ts)        ROSSO  3 failed | 3 passed
F5 voce5 freschezza ignorata (useTennisVivo.ts)                   ROSSO  2 failed | 4 passed
   x a parita' la fonte resta; x messaggio piu' vecchio si scarta
F6 voce6 canale del runner ignorato (runnerCanale.ts)             ROSSO  6 failed | 19 passed
F7 voce6 nessuna rilettura chiesta dal canale (RigaOrdiniReali)   ROSSO  1 failed | 3 passed
F8 voce6 now del runner ignorato (RigaOrdiniReali)                ROSSO  1 failed | 3 passed
F9 voce12 vista xhedge senza canale (xhedgeCanale.ts)             ROSSO  2 failed | 4 passed
F10 voce12 unione: riga del canale senza riga del poll            ROSSO  3 failed | 3 passed
F11 voce13 posizioni del canale ignorate nel Rail                 ROSSO  1 failed | 5 passed
F12 voce13 ordini: freschezza ignorata (ordiniCanale.ts)          ROSSO  1 failed | 5 passed
F13 voce13 LivePnl senza canale                                   ROSSO  1 failed | 5 passed
F14 voce14 scanner_stato non sottoscritto                         ROSSO  1 failed | 11 passed
F-PY voce12 topic xhedge non pubblicato (xhedge_worker.py:
     pubblica_scritte -> pass)                                    ROSSO  1 failed | 8 passed
     FAILED test_xhedge_worker.py::test_xhedge_pubblica_la_riga_scritta_sul_canale
```

## NON VERIFICATO

- App viva e canali VERI: nessun processo avviato, nessuna pagina vista, nessuna connessione a
  47331-47337. Che i push arrivino con le chiavi viste nel codice dei produttori e' dedotto dal
  codice (citato file:riga), non osservato.
- `npm run build` non eseguito (vietato dal brief): l'app desktop vedra' le modifiche solo dopo
  build + riavvio da parte dell'utente.
- Il comportamento del `now` calcio quando piu' partite sono seguite con modi ordini diversi (il
  modo e' di PROCESSO, quindi uguale per tutte: dedotto da `runner.py:292-302`).
- Che la CONNESSIONE al 47332 da sola equivalga a "runner tennis vivo" anche a framework fermo
  (il socket vive in un thread del processo): e' la migliore evidenza disponibile senza un topic
  di battito (vedi "cosa manca lato runner").
- Lint (eslint) non eseguito; solo tsc.

## File toccati

Modificati: `Betfair/stream/canale_bot.py`, `Betfair/stream/xhedge_worker.py`,
`Betfair/stream/tests/test_xhedge_worker.py`,
`frontend/src/components/controlroom/useControlRoom.ts`,
`frontend/src/components/controlroom/RigaOrdiniReali.tsx`,
`frontend/src/components/controlroom/useTennisVivo.ts`,
`frontend/src/components/controlroom/SchedaPartita.tsx`,
`frontend/src/components/controlroom/SchedaPartita.test.tsx`,
`frontend/src/components/live/XHedgePanel.tsx`,
`frontend/src/components/live/LiveTradingPanel.tsx`,
`frontend/src/components/live/TerminalPositionsRail.tsx`,
`frontend/src/pages/ControlRoom.tsx`, `frontend/src/pages/ControlRoom.test.tsx`,
`frontend/src/pages/LivePnl.tsx`.
Nuovi: `frontend/src/lib/statoBotCanale.ts` (+ `.test.ts`), `frontend/src/lib/runnerCanale.ts`
(+ `.test.ts`), `frontend/src/lib/xhedgeCanale.ts`, `frontend/src/lib/ordiniCanale.ts`,
`frontend/src/lib/useOrdiniCanale.ts`,
`frontend/src/components/controlroom/useControlRoom.statoCanale.test.tsx`,
`frontend/src/components/controlroom/RigaOrdiniReali.canale.test.tsx`,
`frontend/src/components/controlroom/useTennisVivo.canale.test.ts`,
`frontend/src/components/live/XHedgePanel.canale.test.tsx`,
`frontend/src/components/live/posizioniCanale.pannelli.test.tsx`, questo referto.
Worktree: create le junction `frontend/node_modules` e `.venv` verso il checkout principale
(mancavano); rimuoverle con `cmd /c rmdir` prima di `git worktree remove`.

## Comandi eseguiti (esito)

- `git fetch` + stash con etichetta unica (`agent-a588-voci4-14-wip`, applicato per SHA e poi
  eliminato) + `git merge --ff-only origin/master` (000d8f6) + risoluzione conflitto a mano in
  `useControlRoom.ts` (entrambi i blocchi conservati) + `git merge --ff-only` (09d9791): OK.
- `npx tsc -p tsconfig.app.json --noEmit`: 0 errori (ripetuto dopo ogni gruppo di modifiche).
- `npx vitest run <22 file>`: 420/420 verdi.
- `python -m pytest <3 file> -q -p no:cacheprovider` con env Supabase finte: 54 passed.
- Falsificazioni: 14 frontend + 1 Python, tutte ROSSE, ripristino verificato.
