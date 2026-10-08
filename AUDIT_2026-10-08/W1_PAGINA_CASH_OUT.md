# W1 - Pagina «Cash Out» (frontend) - referto del delegato (08/10/2026)

Worktree: `/home/user/python-database-automation/.claude/worktrees/agent-a4ac04974b67be6a3`
Punto di partenza: `b5547eb` (il worktree era nato su `8226d76`, 68 commit indietro: portato a
`b5547eb` con `git reset --hard` SUL SOLO ramo del worktree, prima di qualunque modifica).
Nessun commit, nessun `git add`. Perimetro rispettato: solo `frontend/` + questo referto. Nessun file
Python, nessuna migrazione, `LadderView.tsx` e `components/ui/*` non toccati.

## 1. Cosa c'e' adesso

Rotta `/cash-out`, voce «Cash Out» nella sidebar SUBITO sotto «Control Room» (icona esistente
`portafoglio`). Una scatola per partita con TUTTE le gambe aperte:

- testata: icona sport, `NomiPartita`, badge LIVE / PROVA, stato in una parola (`StatoPartitaRiga`
  della scheda «Posizioni aperte», sulle gambe LIVE dei bot), `StatoPill` di `SchedaPartita`
  (minuto e punteggio; tennis set·game), «fra N» in pre-match, `AzioniPartita` (Video | Stats
  Betfair, «Statistiche», Trading, Segui live) col ritorno al Cash Out; tennis: `TennisVivoBar`
  (punto, servizio, tie-break); fuori programma: `BetfairMediaButtons` e la fase dai dati del bot;
- una riga per gamba dei bot = `RigaOperazione` (quota di adesso, «chiudi ora» al ms, `Chiudi` del
  SUO bot = comando di oggi) con il testo che dice quanto chiude (decisione 1) + pulsante «Ladder»;
- posizioni senza riga nella scheda: `RigaPosizioneOrfana` (mai perse);
- una riga per SELEZIONE con ordini fuori dai bot (`vm.ordiniConto`): origine «Sito»/«App», ordini,
  «chiudi ora» con la matematica unica, «Cash out» (solo LIVE, doppia conferma) =
  `sendGreenupFuoriBot`, «Ladder»;
- piede: `CashOutPartita` (Safe, se ha righe vive), `CashOutGlobalePartita` (gambe dei bot, LIVE e
  PROVA separati, «Chiudi tutte le gambe dei bot»), e - solo se ci sono ordini fuori dai bot
  abbinati - «Cash out globale della posizione LIVE: bot + ordini fuori dai bot» con la cifra
  della stessa somma e UN gesto (doppia conferma) che orchestra i comandi esistenti: prima il piano
  di «Chiudi tutte le gambe dei bot» (`pianoChiusuraPartita`, in sequenza, `ChiusuraRigaContext.
  chiudi`), poi un `sendGreenupFuoriBot` per selezione.

Testata della pagina: filtri «⚽ Calcio / 🎾 Tennis» e «Pre-match / Live» con la logica delle tessere
sport della Control Room (`SplitSport.onSeleziona(selezionato === k ? null : k)`: clic sceglie,
secondo clic toglie, nessuno = tutto). Sotto: sezione «In gioco» e sezione «Pre-match».
Riepilogo: N in gioco · M pre-match, «X LIVE · Y prova» (mai un contatore unico), gambe dei bot con
soldi veri. Ordini del conto non letti: lo dice (mai «nessun ordine»).

## 2. File (elenco esatto)

Nuovi:
- `frontend/src/pages/CashOut.tsx` (180 righe): la pagina, UNA chiamata a `useControlRoom()`.
- `frontend/src/components/controlroom/aperte/PosizioniAperte.tsx`: i pezzi della tab «Aperte»
  SPOSTATI da `pages/ControlRoom.tsx` (:1381-1740 di `b5547eb`) + `BOT_CLS`/`LATO_*` (:116-139),
  `SORGENTE_LADDER_RIGHE` (:162), il valore del contesto (:176-186) in `ContestiRigheBanco`
  (Chiusura + OrdiniConto, :786-789/855-856), `registratoriDi` (il `useMemo` di :239-246).
  Verifica: `diff` del blocco spostato contro `git show HEAD:...ControlRoom.tsx` = SOLO `export`
  davanti a 8 dichiarazioni e `ReturnType<typeof useControlRoom>['x']` -> `ControlRoomVM['x']`
  (stesso tipo). testid e markup identici (lo conferma la fotografia `control-room.*.json` identica).
- `frontend/src/components/controlroom/aperte/cashOutPagina.ts`: regole pure (scatole, fase,
  filtri, ordine, testo dei pulsanti, ordini fuori dai bot -> gambe della matematica unica).
- `frontend/src/components/controlroom/aperte/ScatolaCashOut.tsx`: la scatola (composizione).
- `frontend/src/lib/ladderPopout.ts`: URL/nome/finestra identici al bottone «stacca» del LadderView.
- Test: `pages/CashOut.test.tsx` (16), `aperte/cashOutPagina.test.ts` (11),
  `lib/ladderPopout.test.ts` (3), `lib/liveOrders.fuoriBot.test.ts` (3), `lib/ritorno.pagine.test.tsx`
  (5), `components/shell/navigazione.cashOut.test.ts` (3), `controlroom/BottoneChiudiRiga.etichetta.test.tsx`
  (2), + 2 in `pages/ControlRoom.test.tsx`.
- Fotografie nuove: `fotografia/snapshot/cash-out.{off,v2}.json`, `cash-out.{off,v2}.guscio.json`.

Modificati (tutto ADDITIVO, comportamento di serie identico salvo dove scritto):
- `pages/ControlRoom.tsx` (481 righe nel diff, quasi tutte lo spostamento): importa i pezzi spostati; `ContestiRigheBanco` al posto
  dei due Provider; scheda iniziale solo da un punto di ritorno della Control Room
  (`schedaDiRitorno('/control-room')`); `useRitornoAlPunto('/control-room', !vm.caricamento)` al
  posto dell'effetto (vedi §4, difetto trovato); import inutilizzati tolti.
- `components/controlroom/AzioniPartita.tsx`: prop opzionale `ritorno` (di serie Control Room:
  rotta, nome, `from=control-room` identici); usata in `salvaRitorno`, Statistiche, Trading tennis,
  Segui live. NON passata da `SchedaPartita`/`SchedaPreMatch` (la pagina compone `AzioniPartita`
  direttamente): quelle due non cambiano.
- `components/controlroom/BottoneChiudiRiga.tsx`: prop opzionali `etichetta` (di serie «Chiudi») e
  `ambito` (testo accanto e nella conferma live; di serie niente). Richiesta mandata identica.
- `components/controlroom/DettaglioRigaView.tsx`: `RigaOperazione` prop opzionale `chiudi`
  ({etichetta, ambito}) inoltrata al bottone; assente = come prima.
- `components/controlroom/SchedaPartita.tsx`: `export` davanti a `TennisVivoBar` e `StatoPill`.
- `components/controlroom/CashOutGlobale.tsx`: `export` davanti a `motivoPrezziFermi`.
- `components/controlroom/useCashOutPartita.ts`: arg opzionale `gambeExtra` (gambe in piu' nella
  STESSA somma); assente = identico (stesso `useMemo`, stessa lista).
- `components/controlroom/useControlRoom.ts`: campo opzionale `OperazionePartita.koAt` = `kickoff`
  della riga Omega, aggiunto SOLO se presente (spread condizionale: le righe senza kickoff sono
  oggetti identici a prima). Nessuna lettura nuova.
- `lib/liveOrders.ts`: `sendGreenupFuoriBot({marketId, selectionId})` ADDITIVA (contratto W2).
  `sendGreenup`/`buildGreenupParams` invariati (testato).
- `lib/ritorno.ts`: `ORIGINI_RITORNO`, `origineRitorno(from)`, `schedaDiRitorno(rotta)`,
  `useRitornoAlPunto(rotta, pronta)`.
- `pages/Dashboard.tsx`, `pages/SeguiLive.tsx`, `pages/TennisTerminal.tsx`: il «Torna» legge
  l'origine dal `from` (`control-room` = testo, testid `torna-control-room`, title e rotta di prima;
  `cash-out` = «Torna al Cash Out», `torna-cash-out`, `/cash-out`).
- `components/shell/navigazione.ts`: voce `cash-out` dopo `control-room`; `/cash-out` in
  `ROTTE_NEL_GUSCIO`; `CANALI_DELLA_PAGINA['/cash-out']` = gli stessi 8 della Control Room
  (confermato dalla fotografia: con la testata v2 che li interroga, le chiamate/WebSocket di v2 sono
  identiche a off).
- `App.tsx`: `/cash-out` nel ramo v2 (una riga dopo la Control Room) e nel ramo di oggi
  (`ProtectedRoute`).
- Test aggiornati: `AppShell.test.tsx` (voci 24->25, rotte protette 22->23: i numeri del brief
  23->24/21->22 erano gia' saliti di 1 il 07/10 con «Replay tennis»), `fotografia.test.tsx`
  (`PAGINE` + `cash-out`, `LISTA_BIANCA_GUSCIO` + `shell-voce-cash-out`), `designGuard.test.ts`
  (`FILE_GLOSSARIO_LIABILITY` + `pages/CashOut.tsx`, `PosizioniAperte.tsx`, `ScatolaCashOut.tsx`).
  `cssGuscio.test.ts` NON cambiato: la pagina non ha `sticky` (conteggio 21 invariato).
  `codificaSorgenti` e `B2GlossarioAuditCR` verdi senza modifiche.

## 3. Decisioni dell'utente: come sono applicate

1. Pulsante per gamba: Mike, 4 bot tennis, scalper calcio = comando di OGGI (`vm.chiudi` ->
   `chiudiRiga.ts`), il testo lo dice: «Cash out Mike» + «tutte le 3 gambe di Mike» (gambe contate
   fra le righe aperte della scatola nella STESSA modalita'; tennis per partita+mercato «su questo
   mercato»; scalper «ferma la sessione: tutta la sua posizione»). Omega e Safe: «Cash out» + «solo
   questa gamba». Nessun comando nuovo per i bot.
2. Ordini fuori dai bot: righe «Sito» (`source='account'`) / «App» (`source='runner'`), una per
   selezione (il comando chiude per selezione: due ordini sulla stessa selezione = una riga, origini
   unite). `sendGreenupFuoriBot` manda ESATTAMENTE `{action:'greenup', mode:'live', market_id,
   selection_id, handicap:0, params:{esposizione:'fuori_bot'}}` (+ `client_ref` di
   `sendLiveOrderCommand`). Solo LIVE, doppia conferma (inerte 400 ms, cade dopo 10 s).
3. Nessuna lettura nuova: solo i campi di `useControlRoom()` (test sul sorgente: una sola
   `useControlRoom(`, nessun `supabase`/`fetch*`/`subscribe*` nei file della pagina).
4. Pre-partita / fuori programma: fase da `PartitaGiornata.stato`; fuori programma da Mike
   (`ko_at`, `live.inplay`) o dal `kickoff` della riga Omega (`koAt`). Safe e i bot tennis NON
   portano un orario nelle righe in memoria: fuori programma restano in Pre-match «orario non
   dichiarato». Mai una scatola che sparisce.
5. Filtri Pre-match / Live accanto a Calcio / Tennis, stessa logica di selezione.
6. Passaggio di fase: fonte unica `stato`; `chiusa` con mercato non CLOSED = Pre-match col testo GIA'
   esistente di `StatoPill` («non in gioco · orario passato», `SchedaPartita.tsx` ~600: il brief
   citava «fischio passato · non ancora in gioco», ho riusato il testo esistente come chiesto);
   `chiusa` con mercato CLOSED = sezione In gioco con «conclusa» (posizioni da regolare: scelta mia,
   dichiarata). Test: stessa partita, `stato` pre->live, la scatola cambia sezione e non sparisce.

## 4. Difetto trovato e corretto (con test e falsificazione)

`pages/ControlRoom.tsx` (b5547eb :265-279): l'effetto del ritorno al punto esatto chiamava
`setRitornoFatto(true)`, programmava il timer di 80 ms e restituiva `clearTimeout`; essendo
`ritornoFatto` fra le dipendenze, il ri-render immediato eseguiva la pulizia e CANCELLAVA il timer:
lo scorrimento/`portaInVista` non avveniva mai (il punto pero' veniva consumato). In piu' consumava
anche un punto salvato da un'altra pagina. Ora `useRitornoAlPunto` (ref, consuma al timer, solo la
sua rotta). Prova: mutazione M11 (lo schema di prima dentro l'hook) -> il test «la partita torna in
vista» diventa ROSSO. Effetto per l'utente: tornando da Statistiche/Trading la Control Room ora
riporta davvero in vista la partita (prima riapriva solo la scheda).

## 5. Test e comandi (esiti VERI, macchina carica: load 20-24 su 4 CPU, altri cantieri attivi)

- Baseline PRIMA (worktree pulito a b5547eb), `npx vitest run`: **364 file: 2 falliti | 352 passati
  | 10 saltati; 5352 test: 2 falliti | 5299 passati | 51 saltati**, 2275 s. I 2 falliti sono
  preesistenti e non toccati: `lib/replayBarraPunteggio.test.tsx` («Test timed out in 120000ms» sotto
  carico) e `components/dashboard/RitardiPanel.fixb.test.tsx` («periodo DATI MATCH in gg/mm/aaaa»).
- DOPO (worktree con tutte le modifiche), `npx vitest run` intero: **371 file: 361 passati | 10
  saltati, 0 falliti; 5398 test: 5347 passati | 51 saltati, 0 falliti**, 1826 s. 5398 = 5352 + 46
  nuovi (45 nei file nuovi/ControlRoom.test + 1 pagina `cash-out` nella fotografia). I 2 rossi della
  baseline qui sono passati: sono instabili sotto carico (timeout), non legati a questo lavoro.
- `npx tsc -p tsconfig.app.json --noEmit`: **0 errori** (exit 0), test compresi.
- `npm run build`: **ok** (built in 1m 5s; solo l'avviso di sempre sulla dimensione dei chunk).
- Mirati (copia di lavoro): CashOut 16/16, cashOutPagina 11/11, ladderPopout 3/3,
  liveOrders.fuoriBot 3/3, ritorno.pagine 5/5, navigazione.cashOut 3/3, BottoneChiudiRiga.etichetta
  2/2, ControlRoom.test 146/146, designGuard+cssGuscio+codificaSorgenti+B2Glossario+AppShell+ritorno
  61/61.
- Fotografia: `FOTOGRAFIA_AGGIORNA=1 ... -t "cash-out: "` (nuove), poi `FOTOGRAFIA_AGGIORNA=guscio npx
  vitest run src/fotografia/fotografia.test.tsx`: **28/28 verdi**. Diff riletto: cambiano SOLO 22
  `*.v2.guscio.json` (le 21 pagine col guscio + `tennis-terminal-match`) e in ognuna SOLO le 7 righe
  della voce nuova (`"Cash Out"`, `shell-voce-cash-out`, il comando link `/cash-out`): conteggio
  aggregato 22x7 righe aggiunte, 0 tolte. **`control-room.off.json`, `control-room.v2.json` e OGNI
  `*.off.json`/`*.v2.json`/`*.off.guscio.json` esistente: IDENTICI byte per byte** (git status: non
  modificati).

### Falsificazioni (18 mutazioni, tutte ROSSE, ripristino con sha256 verificato)
Script: `scratchpad/w1/falsifica.py` (copia di riserva, mutazione testuale, test mirato, ripristino).
- M1 Mike: gambe contate su tutte le modalita' -> ROSSO (cashOutPagina 1)
- M2 fase: `stato='live'` ignorato -> ROSSO (4: unit + pagina pre->live, filtri)
- M3 fase: `chiusa` non CLOSED messa in gioco -> ROSSO (2)
- M4 partite con soli ordini fuori dai bot non aggiunte -> ROSSO (3)
- M5 payload `esposizione:'fuori_bot'` alterato -> ROSSO (contratto esatto)
- M6 «Cash out» fuori dai bot senza conferma -> ROSSO
- M7 totale col conto che somma la PROVA al LIVE -> ROSSO
- M8 finestra ladder senza nome per mercato -> ROSSO (2)
- M9 `AzioniPartita` col ritorno sempre Control Room -> ROSSO (2)
- M10 ritorno consumato anche se di un'altra pagina -> ROSSO (2, anche ControlRoom.test)
- M11 schema del ritorno di prima (timer cancellato) -> ROSSO
- M12 etichetta del «Chiudi» ignorata -> ROSSO (3)
- M13 filtro: il secondo clic non toglie -> ROSSO
- M14 voce Cash Out non sotto la Control Room -> ROSSO (2, anche AppShell)
- M15 lato degli ordini fuori dai bot invertito -> ROSSO (3)
- M16 `useCashOutPartita` che ignora `gambeExtra` -> ROSSO (2)
- M17 una seconda `useControlRoom()` nella scatola -> ROSSO
- M18 Control Room che riapre la scheda da un punto del Cash Out -> ROSSO

## 6. Cosa NON ho fatto / NON ho potuto verificare

- Il backend del comando fuori dai bot e' del cantiere W2. Il worker di OGGI
  (`Betfair/stream/live_order_worker.py::_greenup`, ~:2222-2330) IGNORA `params.esposizione`: fa il
  green-up dell'esposizione abbinata della `strategy` del runner (gli ordini dell'app dal ladder),
  NON vede gli ordini fatti sul sito. Finche' W2 non e' integrato, «Cash out» su una riga «Sito»
  verrebbe eseguito come green-up degli ordini app di quella selezione (nessun ordine dei bot
  coinvolto: i bot sono altri processi/strategie) o come no-op «posizione piatta». Il pulsante NON e'
  bloccato in attesa di W2: decisione per il coordinatore (vedi §8).
- Prezzi degli ordini fuori dai bot: solo il ladder al ms del canale (`sorgenteLadderAlMs`); non c'e'
  un ripiego dello scanner per quelle selezioni. Mercato non seguito dal runner = «chiudi ora —» e
  pulsante spento col motivo (mai una cifra monca).
- Riepilogo in testata SENZA la somma in euro «se chiudo tutto» di tutte le partite (prototipo):
  richiederebbe di risalire le cifre calcolate dentro ogni scatola (ognuna ha i suoi prezzi al ms).
  Mostro i conteggi; le cifre stanno per scatola (LIVE/PROVA separati).
- Filtro «Live e prova / Solo live / Solo prova» del prototipo NON fatto: la decisione 5 chiede i
  filtri Pre-match/Live accanto a Calcio/Tennis; «Live» qui e' la FASE. Se lo vuoi, si aggiunge.
- `AzioniPartita` intera nella testata (anche «Trading» e «Segui live», non solo Video|Stats e
  Statistiche del prototipo): riuso senza una prop in piu'.
- Fasi fuori programma per Safe e bot tennis: le loro righe in memoria non portano un orario.
- Nessuna prova nell'app desktop (container cloud): niente verifica visiva, niente canali veri.
  `SchedaPartita`/`SchedaPreMatch` intere NON usate nella scatola: troppo diverse dal prototipo
  (metro del target, simboli dei bot, quote) e senza un pulsante per gamba; composte invece i pezzi.
- Codice: i testi a schermo usano «», ·, ′ ed emoji come il resto dei componenti (stile del file);
  la regola «ASCII-only» non e' rispettata alla lettera nei testi UI, come nei file esistenti.

## 7. Parita' paper/live

Nessuna logica di trading toccata. I pulsanti dei bot sono il «Chiudi» di sempre: in PROVA un clic,
in LIVE (o modalita' ignota) conferma; stessa richiesta. Gli ordini fuori dai bot sono solo LIVE.
LIVE e PROVA: `CashOutGlobale` li tiene separati come prima; il totale col conto e' solo LIVE (M7).

## 8. Decisioni per l'utente / per il coordinatore

1. Abilitare il «Cash out» delle righe «Sito»/«App» SOLO dopo l'integrazione del worker W2? Oggi il
   worker ignora `esposizione:'fuori_bot'` (vedi §6). Proposta: integrare W1 e W2 insieme.
2. Partita con mercato CHIUSO e posizioni non regolate: messa in «In gioco» con «conclusa».
   Alternativa: una terza sezione «Da regolare».
3. Filtro LIVE/PROVA del prototipo: aggiungerlo?

## 9. Da controllare dal vivo in paper al prossimo avvio

- Sidebar: «Cash Out» sotto «Control Room»; la pagina mostra le stesse posizioni della tab
  «Posizioni aperte» della Control Room (stesso conteggio «X LIVE · Y prova»).
- Una partita di Mike con 2-3 gambe: UNA scatola, ogni riga «Cash out Mike / tutte le N gambe di
  Mike»; un clic in paper chiude il ciclo (come il «Chiudi» di oggi).
- «Ladder» apre la finestra 560x860 del mercato della gamba.
- «Statistiche» -> Cruscotto con «Torna al Cash Out», che riporta e illumina la partita.
- Control Room: tornando da Statistiche la partita viene riportata in vista (prima no).

## 10. Blocco per la cronostoria

> **W1 - pagina «Cash Out»** (delegato, worktree `agent-a4ac04974b67be6a3`, ora sulla cima di
> `claude/blissful-sagan-hri7o6` = `4b262c4` (W2 compreso), non committato). Nuova rotta `/cash-out`
> sotto la Control Room: una scatola per partita con tutte le gambe (bot + ordini Sito/App), cash
> out per gamba col comando di oggi (il pulsante dice quanto chiude), cash out della posizione
> (bot, e bot+fuori bot LIVE), riepilogo «Se chiudo tutto adesso» LIVE e PROVA mai sommati (dalle
> cifre delle scatole, fail-closed), filtri Calcio/Tennis, Pre-match/Live e Live e prova/Solo
> live/Solo prova, sezioni In gioco / Pre-match con passaggio automatico, testata della scatola
> come il prototipo (Video|Stats + Statistiche, Ladder per riga). Una sola `useControlRoom()`,
> nessuna lettura nuova; pezzi della tab «Aperte» spostati in `aperte/PosizioniAperte.tsx` (codice
> identico). `sendGreenupFuoriBot` col contratto W2 (verificato su `_do_greenup_fuori_bot`).
> Corretto il ritorno al punto della Control Room (timer cancellato da se', mai scorrimento).
> tsc 0, build ok, fotografie: fuori dal Cash Out cambiano solo le 22 `*.v2.guscio.json` per la
> voce nuova, `control-room.*` identiche; 18 + 10 falsificazioni rosse. vitest intero sul ramo:
> 5372 passati / 2 falliti (SafeStrategy.test, instabili sotto carico: 28/28 rilanciato da solo).

## 11. Secondo giro (richiesta del coordinatore, 08/10)

### 11.1 Ramo
`git fetch origin claude/blissful-sagan-hri7o6` + `git merge --ff-only FETCH_HEAD`: **fast-forward
riuscito** da `b5547eb` a `4b262c4` (4 commit: `4d1e0f9` cronostoria, `5cc7103` W2, `f0f14f6`
cantiere 5, `4b262c4` cantiere 12), il lavoro non committato e' rimasto intatto (nessun conflitto:
i commit toccano altri file). Verificato sul worker di W2 (`live_order_worker._do_greenup_fuori_bot`):
accetta `params.esposizione == 'fuori_bot'` (costante `esposizione_fuori_bot.FUORI_BOT`), SOLO
`mode == 'live'`, rifiuta `amount/target_price/place_at_ticks/cancel_unmatched/...`: il payload
di `sendGreenupFuoriBot` (`{action:'greenup', mode:'live', market_id, selection_id, handicap:0,
params:{esposizione:'fuori_bot'}}`) e' conforme. **Il punto aperto 1 (§6, §8.1) e' superato.**

### 11.2 Riepilogo «Se chiudo tutto adesso» (LIVE e PROVA, mai sommati)
- Nessun secondo calcolo: ogni scatola riporta alla pagina la SINTESI della cifra che gia' calcola
  (`useCashOutPartita.ts`: `sintesiCashOut`, `useRiportaSintesi`, riporta solo quando la firma
  cambia; un richiamo nuovo a ogni render non riparte). UNA fonte per scatola: il totale col conto
  (`CashOutPosizioneConto`, bot + fuori dai bot) se ci sono ordini fuori dai bot abbinati,
  altrimenti `CashOutGlobalePartita` (nuova prop OPZIONALE `onSintesi`: assente = identico a prima).
  Scatola smontata (filtri) = esce dal riepilogo.
- Somma per modalita' (`cashOutPagina.totaleModalita`): `ok` = somma al centesimo con l'eta' del
  prezzo piu' vecchio (marchio STIMA / PROVA); `non-calcolabile` se anche UNA scatola con gambe in
  quella modalita' e' non calcolabile: nessuna cifra, i motivi per partita (come `CashOutGlobale`);
  `calcolo` finche' una scatola mostrata non ha riportato; `nessuna` = «—».
- Accanto: gambe aperte e partite per modalita' (`contaPerModalita`: LIVE = gambe non paper dei bot
  + selezioni abbinate fuori dai bot; PROVA = gambe paper; una partita con tutte e due conta in
  tutte e due, mai sommate) e «Partite mostrate: N in gioco · M pre-match».
- Il riepilogo segue i filtri (somma le scatole MOSTRATE): scelta mia, dichiarata nella tessera.

### 11.3 Filtro «Live e prova / Solo live / Solo prova»
Stessa forma e logica dei pulsanti sport (`Filtro`): «Solo live»/«Solo prova» selezione singola,
ri-clic = tutto; in piu' il primo pulsante «Live e prova» (premuto quando niente e' scelto, clic =
tutto). Una partita e' LIVE se ha almeno una gamba non paper o un ordine del conto
(`ScatolaCashOut.live`, stessa regola fail-safe di `raggruppaAperte`), altrimenti PROVA.

### 11.4 Testata della scatola come il prototipo
`AzioniPartita` prop OPZIONALE `soloMediaStatistiche` (di serie `false` = tutti i pulsanti di oggi:
test del default + fotografie della Control Room identiche): con `true` restano Video | Stats Betfair
e «Statistiche»; niente «Trading», «Segui live»/REC e le loro scritte. La scatola la usa; il Ladder
per riga c'era gia'. Tolti di conseguenza `registra`/`registratoreVivo` dalla scatola e
`registratoriDi` (il `useMemo` della Control Room e' tornato com'era a `b5547eb`).

### 11.5 File toccati nel secondo giro
`pages/CashOut.tsx`, `aperte/ScatolaCashOut.tsx`, `aperte/cashOutPagina.ts`,
`aperte/PosizioniAperte.tsx` (tolto `registratoriDi`), `components/controlroom/useCashOutPartita.ts`
(sintesi), `CashOutGlobale.tsx` (prop `onSintesi`), `AzioniPartita.tsx` (prop
`soloMediaStatistiche`), `pages/ControlRoom.tsx` (registratori come prima), test:
`CashOut.test.tsx` (+5: testata, filtro soldi, riepilogo somma esatta, non calcolabile, segue i
filtri), `cashOutPagina.test.ts` (+3), `ritorno.pagine.test.tsx` (+2: default e prop di
`AzioniPartita`), fotografie `cash-out.{off,v2}.json` rigenerate (solo la pagina nuova: filtro
soldi e tessere del riepilogo; `cash-out.*.guscio.json` identiche).
Il riepilogo nel test: E1 sito -0,53 + E2 Omega LIVE +0,37 = **−0,16 €** (uguale alla somma delle
cifre lette nelle due scatole); E3 Omega PROVA solo nella tessera PROVA.

### 11.6 Falsificazioni del secondo giro (`scratchpad/w1/falsifica2.py`, ripristino sha OK)
- N1 somma monca (salta le non calcolabili) -> ROSSO (2)
- N2 il riepilogo legge sempre il LIVE -> ROSSO (4)
- N3 filtro soldi ignorato -> ROSSO (3)
- N4 «Live e prova» mai premuto -> ROSSO
- N5 Trading/Segui live di nuovo nella scatola -> ROSSO (2)
- N6 `AzioniPartita` di serie senza Trading -> ROSSO
- N7 la scatola non riporta la sua cifra -> ROSSO (3)
- N8 la cifra col conto (bot + sito) non riportata -> ROSSO (2)
- N9 gambe paper contate nel live -> ROSSO (2)
- N10 scatola non ancora riportata trattata come vuota -> ROSSO
- NON falsificabile con un test deterministico: le DUE fonti della stessa scatola che riportano
  insieme (gli effetti dei fratelli girano in ordine, vince sempre la seconda): il codice ha una
  sola fonte per costruzione (`conConto`), scritto qui come limite.

### 11.7 Esiti veri (ramo `4b262c4` + lavoro W1, macchina carica)
- `npx tsc -p tsconfig.app.json --noEmit`: **0 errori**.
- `npm run build`: **ok** (built in 47,57 s).
- `npx vitest run` intero: **373 file: 1 fallito | 362 passati | 10 saltati; 5425 test: 2 falliti
  | 5372 passati | 51 saltati**, 2249 s. I 2 falliti: `pages/SafeStrategy.test.tsx` («Piazza»
  combinazione / tennis: «expected spy to be called 2 times, but got 0» = attesa scaduta sotto
  carico); la pagina Safe non importa nessun file toccato da W1; **rilanciato da solo: 28/28
  verdi**. Fotografia intera 28/28 verde nella stessa corsa (tutte le pagine identiche, Control Room
  compresa); CashOut 21/21, ControlRoom 146/146, designGuard 12/12, cssGuscio 3/3.

### 11.8 Cosa cambia nei punti aperti del primo giro
- §6 primo punto e §8.1 (worker W2): superati (11.1).
- §6 riepilogo senza somma, filtro LIVE/PROVA mancante, `AzioniPartita` intera, §8.3: fatti (11.2-11.4).
- Restano: prezzi degli ordini fuori dai bot solo dal ladder al ms; fase delle fuori programma di
  Safe e bot tennis; partita col mercato CLOSED in «In gioco» (§8.2); nessuna prova nell'app desktop.

## Verifica del coordinatore cloud (08/10)
- Diff riletto. Spostamento dei pezzi della scheda «Aperte» FEDELE: confronto automatico del blocco b5547eb:ControlRoom.tsx
  :1381-1745 con `aperte/PosizioniAperte.tsx`: nessuna riga di logica persa o cambiata (solo `export` e il tipo `ControlRoomVM[...]`).
  Modifiche ai componenti condivisi solo ADDITIVE con default invariato (`BottoneChiudiRiga` etichetta/ambito, `RigaOperazione.chiudi`,
  `useCashOutPartita.gambeExtra`, `AzioniPartita.ritorno/soloMediaStatistiche`, `OperazionePartita.koAt` solo se la riga lo porta).
- Applicato sulla cima con W2/C5/C12/C14/C15/C6: `tsc` 0 errori; 96 file di test (CashOut, ControlRoom, fotografia INTERA, shell,
  controlroom, ritorno, ladder, liveOrders, designGuard, Dashboard, SeguiLive, TennisTerminal) 1404/1404 verdi.
- MIE MUTAZIONI: totale live calcolato sulla prova -> 3 rossi; somma monca con una scatola non calcolabile -> 2 rossi; payload senza
  `esposizione` -> 1 rosso; «fischio passato» in gioco -> 2 rossi; Control Room senza Trading/Segui live di serie -> 1 rosso
  (`ritorno.pagine.test.tsx`). Un mio primo mutante (ripiego sull'altra modalita') era EQUIVALENTE: la sintesi porta sempre entrambe.
- Non provato: la pagina a schermo nell'app desktop (da fare sul PC).
