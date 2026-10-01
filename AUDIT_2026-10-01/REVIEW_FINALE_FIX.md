# Correzioni dei reperti della review finale del 01/10 (R-01, R-02, R-03, R-04, R-09)

Delegato Opus, worktree `agent-ac376ddf476451f47`, base `master` = `ca85331` (il ramo del
worktree era su `951113c`: portato avanti con `git merge --ff-only master`, albero pulito).
Niente commit, niente build. R-05..R-08 e R-10 NON toccati (restano dichiarati).

## Consegna (tutto nel WORKTREE: l'isolamento del worktree rifiuta le scritture nel checkout principale)

- `AUDIT_2026-10-01/REVIEW_FINALE_FIX.patch` = `git diff master` (solo frontend, 16 file).
- `AUDIT_2026-10-01/REVIEW_FINALE_FIX_SQL.diff` = diff unificato della migrazione (R-02).
- `migrations/giornata_di_riferimento_giorno_partita_2026-10-01.sql` = la migrazione GIA'
  corretta (copia del file non tracciato del checkout principale + R-02). Va copiata al suo
  posto nel checkout principale da chi coordina: io non ho potuto scriverci.

## Reperto -> correzione

| Reperto | Correzione | File |
|---|---|---|
| R-01 ALTO | «attribuita al giorno della PARTITA» si scrive SOLO se TUTTE le righe lette del giorno portano `in_day` boolean dal database (stessa regola del ripiego di `summarizeDayTrades` e di `criterioVecchio` di StoricoSport). Righe senza `in_day`: «Giornata NON per partita: il database non manda ancora il giorno della partita (manca il suo aggiornamento), quindi ...» col criterio VERO del bot (Mike = REGOLAMENTO, Omega/Safe = PIAZZAMENTO; nello Storico per sport la frase coi due criteri). Nessuna riga letta: «Criterio della giornata non verificabile: nessuna operazione letta nel giorno scelto ...» (non afferma ne' partita ne' altro come certo). Nessun nome di file SQL. | `lib/dailyHistory.ts` (`statoGiornoDb`, `testoCriterioGiornata`), `components/trading/TradingHistory.tsx` (`history-criterio`), `pages/StoricoSport.tsx` (piede) |
| R-02 MEDIO | `inizio_partita_sql`: `NULLIF(minute_at_entry, 0)` nella CASE (condizione e prodotto). Minuto 0 senza catena -> NULL -> `giorno_da='piazzamento'`, dichiarato. Commenti di testa e della funzione aggiornati («R-02 review 01/10»). | migrazione (vedi sopra) |
| R-03 MEDIO | Conto: `confermaStopConto(live, modo, runnerTennisForseLive) = live || runnerTennisForseLive || modo !== 'paper'` (conferma a meno che la modalita' sia LETTA e PAPER). Il motivo a schermo dice perche': «modalita' del conto non letta (potrebbe essere LIVE)» / «il runner tennis consente ordini veri (o il suo stato non e' letto)...». Runner tennis: `runnerForseLive(vm.runnerTennis)` (TesseraRunner.tsx) con i SOLI dati gia' nella testata (`RunnerState.mode` = LIVE_ORDER_MODE): false solo con tetto letto «solo simulati» o «ordini spenti»; runner non letto o tetto ignoto = forse (fail-closed). Passato con una prop NUOVA `runnerTennisForseLive` che vale solo per la conferma: `qualcheBotLive` e i colori della riga del conto non cambiano. I bot tennis in `vm.bots` erano gia' coperti da `qualcheBotLive`. | `testata/FasciaStop.tsx`, `testata/TesseraRunner.tsx`, `pages/ControlRoom.tsx` (Freni) |
| R-04 BASSO | METÀ DEL REPERTO ERA FALSA: `fmtNum` NON mette i punti delle migliaia (`lib/format.ts::itFixed` = `toFixed` + virgola), quindi il campo si apriva GIÀ con `-12500,00`. `testoIniziale` è rimasta IDENTICA (solo esportata e commentata; un test la tiene ferma: la mutazione «migliaia it-IT» è rossa). Un mio primo tentativo con `toFixed(2).replace` violava `designGuard.test.ts` (2 rossi nella suite intera): annullato. Resta la parte vera: `leggiImporto` accetta i punti delle migliaia: con la virgola decimale (`12.500,00` -> 12500, `-999.999,99`) e, DECISIONE, senza virgola SOLO se ogni punto e' seguito da esattamente 3 cifre e il primo gruppo ha 1-3 cifre (`12.500` -> 12500, `1.000` -> 1000). Non e' ambiguo: un punto con 3 decimali era gia' rifiutato (euro al centesimo); `12.50` e `12.5` restano 12,50 come prima; `12.5000`, `1.2,50`, `12,500`, `12.500.0` restano rifiutati. `testoIniziale` ora esportata (per il test). | `testata/FasciaStop.tsx`, `testata/salvaStop.ts` |
| R-09 | `addDays` nell'unico import da `@/lib/dailyHistory`. | `lib/chiuseGiornata.ts` |

## Test

- `npx tsc -p tsconfig.app.json --noEmit` = 0 errori.
- File toccati + vicini (14 file: StoricoMikeGiornoRegolamento, Omega.storico, StoricoSport,
  tutta `testata/`, chiuseGiornata, dailyHistory, TradingHistory, DayDetail, ControlRoom):
  423/423 verdi. Suite intera `npx vitest run`: 310 file passati / 10 saltati, 4764 test passati /
  50 saltati, 0 falliti (prima: 4748; +16 test nuovi).
- Test NUOVI:
  - R-01: `dailyHistory.test.ts` «statoGiornoDb / testoCriterioGiornata (R-01)» (2 test);
    `StoricoMikeGiornoRegolamento.test.tsx` 3 test «R-01: ...» (Mike senza in_day -> REGOLAMENTO
    + «manca il suo aggiornamento»; Safe senza in_day -> PIAZZAMENTO; nessuna riga -> «non
    verificabile»), piu' il test di prima riscritto con righe del contratto 01/10 (in_day) ->
    frase partita presente; `StoricoSport.test.tsx` B-04: piede col criterio vero con la RPC
    vecchia, frase partita con il contratto nuovo.
  - R-03: `FasciaStop.test.tsx` «R-03 - conferma dello stop del CONTO» (modo null -> conferma col
    motivo; 'paper' letto -> nessuna conferma, scrive; 'live' -> conferma; paper + runner tennis
    forse LIVE -> conferma; tabella della regola); `TesseraRunner.test.tsx` `runnerForseLive`;
    `ControlRoom.test.tsx` cablaggio (conto PAPER, bot PAPER, runner tennis LIVE+PAPER -> conferma).
  - R-04: `salvaStop.test.ts` 2 test (migliaia con virgola; «12.500» senza virgola e i casi
    rifiutati); `FasciaStop.test.tsx` «R-04» (testoIniziale; Safe a 12.500 apre «-12500,00» e
    Salva senza modifiche scrive 12500).
- Test VECCHI cambiati (codificavano il comportamento falso del reperto R-01):
  `StoricoMikeGiornoRegolamento` «la pagina dice il criterio...» (prima fetchDayTrades [] e
  frase partita attesa), `Omega.storico` (giorno senza righe: ora «non verificabile»),
  `StoricoSport` B-01 (piede senza righe del giorno: ora «non verificabile»).
- Finti: righe di `get_mike_day_trades` con le chiavi vere (`riga()` del file) e la riga «RPC di
  prima» ottenuta TOGLIENDO le tre chiavi del 01/10 (`rigaVecchia`), mai con valori inventati;
  riga di `betfair_live_risk_state` con le sue chiavi (`mode` null = colonna senza valore);
  `RunnerState` con `ts, mode, ageS, up, streaming`.

## Falsificazione (script con ripristino verificato byte per byte, rimosso dopo l'uso)

| Mutazione (comportamento vecchio rimesso) | Esito |
|---|---|
| M1 TradingHistory: frase partita sempre | ROSSO 4 (3 R-01 + Omega.storico) |
| M2 StoricoSport piede: frase partita sempre | ROSSO 2 (B-01/R-01, B-04 RPC vecchia) |
| M3 `statoGiornoDb` every -> some | ROSSO 1 |
| M4 testo Mike-solo cade nella frase coi due criteri | ROSSO 1 (dopo aver aggiunto «la pagina di un bot parla solo di quel bot»: al primo giro era VERDE, test rafforzato) |
| M4b Mike dichiarato a PIAZZAMENTO | ROSSO 2 |
| M5 regola vecchia del conto (`live || modo === 'live'`) | ROSSO 4 (modo null, runner tennis, tabella, cablaggio ControlRoom) |
| M6 runner tennis staccato nel cablaggio di ControlRoom | ROSSO 1 |
| M7 `runnerForseLive`: non letto = no | ROSSO 1 |
| M8 `testoIniziale` con le migliaia it-IT (`toLocaleString`) | ROSSO 2 (il «vecchio» `fmtNum` invece passa: era già senza migliaia, vedi R-04) |
| M9 `leggiImporto` senza il ramo migliaia+virgola | ROSSO 1 |
| M10 `leggiImporto` senza il ramo «12.500» | ROSSO 1 |

## R-02: verifica sul database (SOLA LETTURA, solo GET REST con il `.env` del checkout principale)

Righe con `minute_at_entry = 0`, e se il loro evento ha l'inizio nella catena di
`inizio_partita_evento` (stesse fonti e stesso ordine; per Omega prima `t.kickoff`):
- `safe_strategy_trades`: 0 righe (nessuno stato).
- `omega_trades`: 0 righe.
- `mike_trades`: 43 righe = 16 regolate (won/lost/void) + 27 `error`; TUTTE e 43 con l'inizio in
  catena -> la stima dal minuto non si usa mai, nessun numero cambia.
Differenza col conteggio del coordinatore: lui 15 regolate Mike, io 16 (probabile riga regolata
dopo il suo conteggio, o `void` incluso da me): l'esito «tutte in catena» e' lo stesso.

## Non verificato

- La migrazione NON e' stata eseguita (la applica l'utente): `NULLIF(integer, 0) * interval` e'
  PostgreSQL standard ma non provato sul server; nessun test SQL nel repo la copre.
- Non ho potuto scrivere nel checkout principale (patch, referto, migrazione): sono nel
  worktree, vanno copiati.
- Nessuna app, nessun build: solo jsdom. La lunghezza delle frasi nuove nella riga
  `history-criterio` e nel piede non e' vista a schermo.
- Storico TENNIS: per il piede ho considerato solo i bot con dettaglio per riga (Safe tennis);
  i 4 bot tennis non hanno righe nel dettaglio (`senzaDettaglio`) e il loro criterio
  (`get_tennis_bot_daily`, gia' giorno partita dal 30/09 secondo la migrazione) non entra nella
  frase. Sul tennis senza righe Safe il piede dice «non verificabile».
- R-03, runner tennis non connesso al canale (`vm.runnerTennis = null`, frequente se il runner
  tennis non gira): ora lo stop del conto chiede SEMPRE conferma (un clic in piu'), anche in tutto
  PAPER. Scelta fail-closed come per i bot; se l'utente la vuole diversa, la regola sta in
  `runnerForseLive` (una riga).
- Lo stato del criterio in TradingHistory e' quello del GIORNO SCELTO (non «ricordato» fra
  giorni): un giorno senza operazioni dice «non verificabile» anche a migrazione applicata.
