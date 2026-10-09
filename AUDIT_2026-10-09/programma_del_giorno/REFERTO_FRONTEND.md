# Programma del giorno (/board) — referto del delegato FRONTEND (09/10/2026)

Ordine dell'utente del 09/10, identico per calcio e tennis. Lavoro contro
`CONTRATTO.md` (backend in parallelo), poi allineato ai payload VERI consegnati dal
backend (ramo `worktree-agent-abb4efd85c1b43214`, commit `0f956d08`,
`esempio_payload_{calcio,tennis}.json`). Dominio toccato: solo `frontend/` e
`AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/canaleFinto.mjs`. Nessun file `Betfair/`.

## 1. Cosa fa la pagina adesso

| richiesta | come |
|---|---|
| 1. design system v2 | classi `ds-v2-*` esistenti (tabbar/tab, `ds-v2-tabella`/`ds-v2-riga`, chip `--paper/--live/--fermo`, `ds-v2-quota--back/--lay`, `ds-v2-campo`, `ds-v2-strip--*`, `ds-v2-board-*`); 13 regole nuove `ds-v2-board-*`/`ds-v2-box-ordine` in `index.css` subito dopo il blocco «PAGINA 2», tutte sotto `[data-shell="v2"]`, nessun colore nuovo, nessun carattere < 10 px (guardie `cssVeste`/`cssGuscio` verdi). Col guscio spento la pagina resta coerente (schermata `board.off…`). |
| 2. punteggio e minuto | `row.score` (contratto §1): calcio minuto (`INT` se `ht`), gol, rossi solo se > 0; tennis `Set a–b · Game c–d · punti` + «● batte <giocatore>». Solo partite in gioco; in gioco senza punteggio = «—», mai 0–0. Uno `score` di un altro sport si scarta (calcio e tennis non si mischiano). |
| 3. liquidità | «ABBINATI» del mercato mostrato (`fmtMoney`, migliaia col punto: `1.843.210 €`), barra relativa al mercato più scambiato della lista (`ui/progress`, `role=progressbar` con `aria-valuenow`), importo disponibile sotto ogni quota (`back_size`/`lay_size`). Assente = «—» / «liquidità non nota», mai 0. |
| 4. menù del mercato | `<select>` col design system, globale per scheda; voci da `market_types` (nomi italiani del backend), MATCH_ODDS sempre primo, sul calcio filtro difensivo di tutto ciò che contiene `CORRECT_SCORE`/`HALF_TIME_SCORE`; raggruppate con `lib/market-categories`. `market_types` ASSENTE = «tipi non ancora letti»: solo Match Odds + nota. Tipo ≠ MATCH_ODDS: richiesta `board_mercato {market_type}` subito, ogni 30 s e a ogni riconnessione; mai per MATCH_ODDS; righe del push `board_mercato` di QUEL tipo unite per `event_id` al board. «Caricamento…» fino al primo push; `ok:false` mostrato per intero, nessuna insistenza oltre il rinnovo dei 30 s. Scelta ricordata per scheda (`sessionStorage`). |
| 5. box quote che piazzano | clic su BACK/LAY → `PlaceConfirmDialog` sotto la riga, quota modificabile (± un tick Betfair), importo vuoto (nessuno stake inventato), conferma → `localOrderApi(sport, dbApi)` col comando `{action:'place', mode, market_id, selection_id, handicap, side, order_type:'LIMIT', price, persistence:'LAPSE', size}`; guardia anti-doppio-invio; modalità SEMPRE del runner; ignota/OFF/freno/cambiata col box aperto/mercato sospeso = conferma spenta con la ragione scritta. Durante l'invio: «Invio in corso (aggancio della partita se non è già seguita)…»; esito in toast e in una riga persistente, rifiuti del backend per intero. Fuori dall'app (senza token) la pagina dice che gli ordini vanno sulla coda DB, che non aggancia le partite non seguite. |
| 6. Statistiche | `AzioniPartita` con origine `board`: calcio `/dashboard?fixture=<fixture_id>&from=board` (spento con la ragione senza `fixture_id`); tennis → Tennis Terminal sulla partita (le statistiche stanno lì, colonna destra aperta di serie). |
| 7. Trading | `AzioniPartita.apriTrading`: calcio `followMission` poi `/segui-live?event=<id>&from=board`; tennis `/tennis/terminal?event&market&name=Match Odds&from=board&p1&p2`. Ritorno: «Torna al Programma» riapre la scheda sport e riporta in vista la partita (riga accesa 2 s). |

Connessioni: **nessuna nuova**. La pagina usa i due singleton `getLocalChannel('calcio'|'tennis')` che apriva già (pallini di stato); un test lo verifica (`FintoWs.tutti` = solo `:47331` e `:47332`) e una falsificazione (M42) lo fa diventare rosso.

## 2. Componenti riusati (file:riga)

- `lib/localChannel.ts:302` `getLocalChannel` (singleton), `:162` `request`, `:134` `puoComandare`
- `lib/localTransport.ts:433` `localOrderApi` (canale con token → `order`, altrimenti dbApi), `:571` `useLocalStatus`
- `pages/SeguiLive.tsx:68` `CALCIO_DB_ORDER_API` (solo **esportata**, nessuna copia); `components/tennis/TennisLadderColumn.tsx:60` `TENNIS_ORDER_API`
- `lib/runnerCanale.ts:179` `leggiModoOrdiniCanale`, `:198` `leggiModoDalNow`, `:58` `MODO_CANALE_VALIDO_S`
- `components/live/PlaceConfirmDialog.tsx:69` (esteso, vedi §3); comando e guardia come `components/live/LadderView.tsx:1813` (`submit`) e `:1909` (`execute`)
- `lib/liveOrders.ts:761` `LIVE_ORDER_STATUS_LABEL` (stato nel toast, come `LiveTradingPanel`)
- `lib/matchClock.ts:12` `countdownToOff`, `:29` `formatMinute`, `:36` `formatScore`
- `lib/format.ts:57` `fmtMoney` (esteso), `:71` `fmtOdds`, `:167` `fmtTime` (Roma)
- `lib/matching.ts:81/95/114/121` `roundToTick`/`isValidTick`/`tickUp`/`tickDown`
- `lib/market-categories.ts:8` `CATEGORIES`, `:38` `groupByCategory`
- `lib/mike.ts:822` `marketStatusMeta` (SOSPESO/CHIUSO in italiano)
- `components/ui/progress.tsx:11` `Progress` (barra di liquidità)
- `components/controlroom/AzioniPartita.tsx:87` (esteso) con `components/BetfairMediaButtons.tsx:39` dentro (video/stats Betfair tenuti)
- `lib/ritorno.ts:69` `salvaRitorno`, `:185` `schedaDiRitorno`, `:197` `useRitornoAlPunto`, `:180` `origineRitorno`; pagine di arrivo invariate: `pages/Dashboard.tsx:41`, `pages/SeguiLive.tsx:987`, `pages/TennisTerminal.tsx:38` leggono già l'origine dal `from`

## 3. Estensioni (props/opzioni OPZIONALI: chi non le usa non cambia)

- `PlaceConfirmDialog`: `prezzoModificabile` (quota nel box, valida solo 1,01–1000 e su un tick Betfair, altrimenti spenta col motivo: mai arrotondare in silenzio), `mode: null` (modalità ignota: chip «NON NOTA», nessun colore inventato), `bloccato` (ragione scritta, conferma spenta, anche da tastiera), `inline` (sotto la riga), `contesto`; `onConfirm(amount, price)`. Il ladder la usa come prima (36 test di `LadderView` verdi).
- `AzioniPartita`: tipo d'ingresso ristretto ai campi letti (`PartitaAzioni`, una `PartitaGiornata` lo soddisfa), prop `statisticheTennis` (di serie false: la Control Room resta identica). **Difetto latente corretto**: un tennis senza `marketId` cadeva nel ramo calcio (`followMission`, seguito CALCIO scritto per una partita di tennis); ora si ferma e dice «manca il mercato Match Odds».
- `lib/ritorno.ts`: origine `board` (`/board`, «Torna al Programma», testid `torna-board`).
- `lib/format.ts`: `fmtMoney(…, { migliaia: true })` (di serie false).
- `pages/SeguiLive.tsx`: `export` su `CALCIO_DB_ORDER_API` (una parola).

## 4. Componenti nuovi e perché non esistevano

- `components/board/boardDati.ts` — forme dei push `board`/`board_mercato` e regole pure (lettura difensiva, filtro correct score, unione per evento, barra relativa, modo applicato). Il tabellone è l'unico consumatore di quei push; prima la forma stava dentro `Board.tsx`.
- `components/board/useBoardCanale.ts` — sottoscrizioni ai topic del canale esistente + la richiesta `board_mercato` rinnovata, con una **memoria per sport** (un solo insieme di sottoscrizioni per sport, come lo store di `localTransport`): senza, cambiando scheda si perdevano il tabellone e il `modo_ordini` (che arriva solo al cambio) — difetto visto nelle anteprime e coperto da test (M44/M45). Le quote del mercato scelto NON si tengono in memoria (una quota vecchia mostrata come viva è peggio di un «caricamento»).

## 5. Test e falsificazioni

- Nuovi: `pages/Board.test.tsx` (31 test, canale VERO con WebSocket finto che parla la busta di `local_channel.py`; finti con le chiavi del contratto e del runner, più i due payload VERI del backend copiati tali e quali), `components/board/boardDati.test.ts` (7), `lib/ritorno.pagine.test.tsx` (+4), `pages/TennisTerminal.test.tsx` (+1: «Torna al Programma» → `/board`), `lib/format.test.ts` (+1).
- **Falsificazione: 45 mutazioni, 45 rosse** (ognuna rompe una regola, si lanciano i test che la coprono, si ripristina; sorgenti verificati identici dopo il giro). Elenco: correct score non filtrati; richiesta per MATCH_ODDS; niente rinnovo; push di un altro tipo accettato; modo ignoto = PAPER; OFF = PAPER; freno ignorato; `now` senza scadenza; `hello.mode` (tetto) preso come modo; cambio di modo col box aperto ignorato; handicap sempre 0; modo cablato paper; niente anti-doppio-invio; quota fuori tick accettata; quota corretta ignorata; blocco ignorato dal box; importo assente scritto 0; barra sulla somma; punteggio di altro sport accettato; rossi a zero mostrati; intervallo ignorato; battuta invertita; origine di ritorno non passata; statistiche tennis spente; scheda di ritorno ignorata; partita non riportata in vista; caduta del canale che non azzera; rifiuto della richiesta taciuto; rifiuto del backend taciuto; scelta del mercato non ricordata; dbApi dello sport sbagliato; tennis senza mercato nel ramo calcio; Statistiche tennis senza la prop; origine board assente; migliaia ignorate; importo vuoto accettato; quota fuori limiti; attesa senza dire l'aggancio; ripiego DB taciuto; tipi assenti taciuti; richiesta che insiste; **una connessione nuova dalla pagina**; memoria per montaggio; memoria della scheda non aperta non avviata; «caricamento» col rifiuto. Un test (M19, punteggio di altro sport) passava a vuoto al primo giro: rafforzato, ora rosso.
- Suite intera, `tsc`, build: vedi §8.

## 6. Fotografie (`src/fotografia`)

Cambiano SOLO `snapshot/board.off.json` e `snapshot/board.v2.json` (ordine dell'utente): titolo `Programma di oggi` → `Programma del giorno`, intestazione «Programma del giorno», sottotitolo nuovo. Nella fotografia i canali sono spenti, quindi il resto è il riquadro «canale non attivo», invariato. Nessun `*.guscio.json` cambiato, nessun'altra pagina cambiata (le altre 27 fotografie verdi senza aggiornamento).

## 7. Schermate (anteprima, guscio v2, 1600 px, canale finto)

`AUDIT_2026-10-09/programma_del_giorno/schermate/`:
`board.v2.1600.intera.png` (calcio), `board.tennis.v2.1600.intera.png`, `board.calcio.over-under-25.v2.1600.intera.png` (menù), `board.box-ordine.v2.1600.png` e `board.box-ordine.off.1600.png` (box aperto, 10 €), `board.off.1600.intera.png` (guscio spento), `board.ritorno-tennis.v2.1600.png` (ritorno dal Tennis Terminal: scheda tennis riaperta, partita accesa). Riguardate una per una; corretti in corsa: colonna dell'orario a larghezza fissa (guscio spento), nome del mercato nel box. Giro vero verificato nel browser: Board → Trading/Statistiche → «Torna al Programma» → Board, scheda giusta e riga accesa per Segui live (calcio) e Tennis Terminal (Statistiche e Trading). `canaleFinto.mjs`: chiavi del payload vero (score, fixture_id, bet_delay, updated_ms, back/lay_size, market_types in italiano, ordine casa/ospite/«The Draw», handicap 0.0), hello con `modo_ordini`, risposta e push `board_mercato`; un solo `onClose` per route (Playwright ne tiene uno).

## 8. Esito delle verifiche

Rilanciate di persona sul codice finale (dopo la falsificazione, sorgenti verificati
identici al backup), da `frontend/`:
- `npx vitest run` (suite INTERA): **371 file verdi, 10 saltati; 5529 test verdi, 51 saltati, 0 rossi** (prima del lavoro: 5484 verdi);
- `npx tsc -p tsconfig.app.json --noEmit`: **0 errori** (nessun `@ts-ignore`/`any` aggiunto);
- `npm run build`: **riuscita** (solo l'avviso preesistente sulla dimensione del bundle);
- fotografie: 28 test verdi, aggiornate solo quelle di `board` (vedi §6).

## 9. Divergenze dal contratto e osservazioni (scelta la via più prudente)

1. **`hello.mode` NON è il modo ordini**: è il TETTO del `.env` (`runner.py set_hello(mode=…)`, `tennis_runner.py`), la scelta dalla UI può essere più bassa, anche OFF. La pagina usa solo `modo_ordini` (topic o `hello.modo_ordini`, pubblicato al cambio da entrambi i runner) e il `now.state.order_mode` del calcio se fresco (≤ 15 s); se c'è solo il tetto, modalità «NON NOTA» e conferma spenta.
2. **Freno**: il `modo_ordini` del calcio porta `kill_switch`; se `true` la conferma è spenta («Freno d'emergenza tirato»). Il tennis non lo dichiara: decide il backend e il rifiuto si mostra.
3. **Quota del box**: oltre a 1,01–1000 deve stare su un tick Betfair (il server arrotonderebbe; si preferisce non cambiare un prezzo in silenzio). Pulsanti ± un tick.
4. **`persistence: 'LAPSE'`**, il default del ladder (contratto: «come il ladder»).
5. **Eventi senza il mercato scelto** non si mostrano (come la coupon Betfair) e si contano in una nota; mercati di eventi fuori dal programma non si mostrano (non hanno orario né nome) e si contano.
6. **Statistiche tennis**: stesso indirizzo di Trading (il terminal apre la colonna statistiche di serie).
7. **«Segui live»** della riga è ora quello di `AzioniPartita` (registra l'intero evento, definizione dell'utente del 14/09) al posto del vecchio (tennis: solo `followTennisEvent`; calcio: link a /segui-live). Sul tabellone non sappiamo se la partita registri già (`registra=null`): il pulsante dice «Segui live»; ripremerlo su una partita già registrata è innocuo (RPC idempotenti).
8. **Dashboard**: il «Torna» (anche quello della Control Room, già prima) compare solo in modalità dettaglio, cioè quando la partita del `fixture` si carica; nell'anteprima non ci sono dati della fixture e il pulsante non si vede. Comportamento preesistente, non toccato: la Dashboard legge l'origine dallo stesso `origineRitorno` (Dashboard.tsx:41,143) e il test unitario copre `board`.
9. **`ui/progress.tsx` non passa `value` alla radice Radix** (manca `aria-valuenow` ovunque): preesistente, non toccato il componente base; la pagina passa `aria-valuenow` come già fa `DayBar`.
10. **Ritorno dopo un ricaricamento dell'app**: nel giro vero (navigazione interna) le righe ci sono subito (memoria per sport). Se l'app viene ricaricata da capo, le righe arrivano al giro successivo del worker (`LIVE_BOARD_POLL_SEC`, 10 s) e solo allora la partita torna in vista (il punto vale 15 min).
11. Ordine delle selezioni del Match Odds: quello del backend (casa, ospite, «The Draw»), nomi delle selezioni come arrivano (inglesi): nessuna traduzione inventata.
