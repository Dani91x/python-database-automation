# Brief 2 per la sessione cloud — VESTE COMPLETA del redesign «guscio v2», fedele al prototipo

Sei l'esecutore (sessione cloud, modello Opus) del coordinatore admin-01 sul repo `Dani91x/python-database-automation`,
ramo di partenza `master` al commit `bc74611` o successivo. Lingua: italiano in tutto (commit, PR, referto, commenti,
testi). Leggi PER INTERO, prima di scrivere una riga: questo file; `BRIEF_SESSIONE_CLOUD.md` (primo mandato: vale
ancora tutto, salvo dove questo file dice diversamente); `REFERTO_CLOUD.md` (tuo referto della prima sessione, con i
limiti dichiarati); `PIANO_INTEGRAZIONE.md`; `INVENTARIO_FUNZIONALITA.md` + `inventario_parti/*.md`;
`RICERCA_MERCATO.md`; il prototipo `prototipo/index.html` + `prototipo/js/*.js` (è il DESIGN APPROVATO dall'utente);
`frontend/src/fotografia/*` (il test di parità, tuo); `frontend/src/index.css` (token e classi `.ds-v2-*`).

## 0. Il contesto in tre righe
La prima sessione ha consegnato la CORNICE (interruttore `ui.shell` spento di default, `AppShell`, sidebar, testata
globale, test fotografia, tabella del Programma, contenitori della Control Room): verificata dal coordinatore e fusa su
master (314 file / 4829 test verdi; parità con interruttore spento provata). L'utente l'ha vista e ha detto: «il design
mi sembra quello attuale». Ha ragione: le fasi 4-7 hanno cambiato solo contenitori esterni (62 righe). L'INTERNO di
ogni pagina è ancora quello di oggi. Questo mandato è la VESTE INTERNA, completa, fedele al prototipo.

## 1. Ordini dell'utente (testuali) e cosa comportano
- «Voglio il design completo. La sessione lavorerà finché non ha finito.» → tutte le pagine dell'elenco §5, fino in fondo.
- «Sempre in sicurezza: dobbiamo poter tornare alla versione base.» → tutto dietro `ui.shell`, SPENTO di default; con
  interruttore spento l'app è quella di oggi byte per byte (fotografia `off` identica, mai rigenerata).
- «Non omettere nulla, non voglio regressioni di nessun tipo.» → parità 1:1 di funzionalità: stessi testi, stessi
  `data-testid`, stessi comandi, stesso ordine dei blocchi, stessi dati, stesse chiamate, stesse conferme.
- «Domani mattina controlleremo noi e faremo noi la fusione.» → NESSUNA fusione su master, nessun build, nessun
  push su master: solo il ramo `redesign/veste-completa` e la pull request in bozza.

## 2. Criterio di accettazione (cosa vuol dire «fedele al prototipo»)
Affiancando lo screenshot di una pagina col guscio ACCESO e la schermata corrispondente del prototipo, un trader deve
riconoscere lo STESSO design: gerarchia tipografica, densità, tessere KPI, tabelle, chip di stato, schede, colori
semantici, spaziature. Non deve riconoscere «la pagina di oggi dentro una cornice». Regole di conflitto:
- Differenza di CONTENUTO fra prototipo e produzione (dati finti contro veri, testi, numero di righe, blocchi che
  oggi esistono e nel prototipo no o viceversa): vale la PRODUZIONE. Non si inventa nulla, non si toglie nulla.
- Differenza di VESTE (come si vede un blocco che esiste in entrambi): vale il PROTOTIPO.
- Un blocco che oggi esiste e nel prototipo manca: resta, e prende la veste coerente con i blocchi simili del prototipo.
- Un blocco che nel prototipo esiste e oggi non esiste: NON si aggiunge (sarebbe una funzione nuova): si segnala.

## 3. Regole TASSATIVE (divieti)
1. VIETATO toccare: file Python, SQL, `migrations/`, `desktop/`, hook React (`use*.ts`, `use*.tsx`),
   `frontend/src/lib/**` (eccetto `uiShell.ts` e `navigazione.ts`, già tuoi), chiamate RPC/Supabase, canali locali,
   `package.json`, `package-lock.json`, `vite.config.*`, `tsconfig*`, `tailwind.config.js` (i token restano quelli).
2. VIETATO cambiare: testi a schermo (compresi `title`/tooltip, `aria-label`, `placeholder`, testi dei bottoni, delle
   conferme, dei badge), `data-testid`, nomi accessibili, ordine dei blocchi e dei comandi, conferme a due tempi
   (400 ms, 10 s, armature dei bottoni «Chiudi»/«KILL»/«tira il freno»), numeri e formattazioni (`fmtMoney`, cifre,
   segni, unità), chiavi di `localStorage` (l'unica tua è `ui.shell`), rotte.
3. VIETATO cambiare l'ASPETTO DI DEFAULT dei componenti base `frontend/src/components/ui/*` (shadcn): li usano le
   pagine con guscio spento. Una variante nuova si aggiunge SOLO come classe `.ds-v2-*` applicata dal contesto, o
   come selettore sotto `[data-shell="v2"]`; mai modificando le classi di default del componente.
4. VIETATO rimuovere o rinominare classi Tailwind che i test interrogano come SEMANTICA: `text-red-400`,
   `text-orange-400`, `text-emerald-400`, `text-red-300`, `text-slate-400`, `text-white/50`, `font-bold`,
   `font-display`, `text-base`, `ring-primary` (elenco dai test: `grep -rhoE "toHaveClass|querySelector" src/**/*.test.*`).
   Puoi AGGIUNGERE classi `.ds-v2-*` accanto, mai togliere quelle.
5. VIETATO aggiungere dipendenze, librerie, font esterni nuovi, immagini, SVG inline pesanti. Niente JavaScript nuovo
   per lo stile: solo CSS e `className`. Niente stato nuovo nei componenti per ragioni di stile (niente `useState`
   aggiunti), niente `useEffect` nuovi, niente `window.*` nuovi.
6. VIETATO modificare i test esistenti. Se un test esistente diventa rosso, hai rotto qualcosa: torna indietro.
   (Unica eccezione documentata: test che asseriscono una classe di stile pura e non semantica; in quel caso NON
   cambiare il test, cambia la tua scelta di stile.)
7. VIETATO rigenerare le fotografie `off` (`src/fotografia/snapshot/*.off.json`, `*.off.guscio.json`). Se cambiano,
   hai rotto la parità: torna indietro. Le fotografie `v2`/`v2.guscio` si rigenerano solo per classi e cornice, e il
   diff va letto e spiegato nel referto (SOLO classi; mai testi, testid, comandi, chiamate).
8. Bug e incongruenze incontrati: si SEGNALANO nel referto (file:riga, cosa, perché), non si correggono. Eccezioni
   ammesse e da elencare: PAPER di un solo colore ovunque (verde del token `paper`, come il prototipo), LAY `rose`
   unico, BACK `sky` unico, mojibake nei commenti (non nei testi a schermo). Nient'altro.
9. Mai `git add -A`, mai `--force`, mai push su `master`, mai merge di `master` nel tuo ramo senza che il coordinatore
   lo chieda (stanotte master non cambia).

## 4. Come si fa la veste senza toccare la logica (metodo)
1. **Tutto lo stile nuovo è condizionato dal guscio**: selettori sotto `[data-shell="v2"]` in `index.css`
   (classi `.ds-v2-*`), più `className` aggiunte nei componenti. Con guscio spento nessuna regola `.ds-v2-*` ha
   effetto perché non esiste selettore senza `[data-shell="v2"]`. `cssGuscio.test.ts` lo verifica: tienilo verde ed
   ESTENDILO (ogni classe `.ds-v2-*` usata nel codice è definita; ogni regola `.ds-v2-*` nel CSS sta sotto
   `[data-shell="v2"]`; nessuna regola sotto `[data-shell="v2"]` modifica un selettore di `components/ui`).
2. **Un vocabolario di classi riusate ovunque**, così la veste è coerente e il CSS resta piccolo (indicativamente):
   `.ds-v2-pagina`, `.ds-v2-intesta` (testata di pagina), `.ds-v2-kpi` + `.ds-v2-kpi-k/v/nota` (tessera KPI),
   `.ds-v2-tabella` + `.ds-v2-th/td/riga` (tabella densa, numeri tabulari a destra), `.ds-v2-chip` +
   `.ds-v2-chip--live/paper/fermo/errore/attesa` (chip di stato), `.ds-v2-marchio` + `--conto/bot/prova/stima`
   (marchio della fonte dei soldi), `.ds-v2-scheda` (card), `.ds-v2-strip` (barra strumenti), `.ds-v2-tabbar` +
   `.ds-v2-tab`, `.ds-v2-ladder*` (colori e tipografia del ladder: vedi §6), `.ds-v2-pulsante--primario/secondario/
   pericolo/armato` (lo stato ARMATO delle conferme deve restare vistosissimo: rosso pieno, come oggi o più),
   `.ds-v2-vuoto` (stato vuoto), `.ds-v2-nota` (note piccole con la fonte), `.ds-v2-num` (numero tabulare).
   Mantieni l'elenco in testa a `index.css` con una riga di commento per classe.
3. **Tipografia**: Sora per i titoli (`font-display`), Inter per il testo, numeri con `font-variant-numeric:
   tabular-nums` OVUNQUE ci sia una cifra (soldi, quote, percentuali, conteggi). Dimensioni come il prototipo, con
   questi minimi non negoziabili (leggibilità da trader): cifre dei soldi e delle quote ≥ 12 px; testi ≥ 11 px;
   note e fonti ≥ 10 px; contrasto testo/sfondo ≥ 4,5:1 per i testi normali e ≥ 3:1 per i grandi (verifica con una
   funzione di contrasto nel test di CSS o a mano sui token).
4. **Colori semantici uniformi** (token di `index.css`, nessun colore nuovo): profitto/perdita, BACK `sky`/LAY `rose`
   come l'exchange, PAPER di UN colore, LIVE col suo, FERMO/ERRORE/IN ARRESTO con i colori di `botStatusMeta`
   (non cambiarne la semantica, solo la resa), marchio della fonte (CONTO/BOT/PROVA/STIMA) con lo stesso stile in
   tutte le pagine. Soldi veri e prova MAI nello stesso colore o nella stessa tessera: regola di casa.
5. **Densità e layout**: griglie e spaziature come il prototipo; la finestra desktop è 1600×900 di default (vedi
   `desktop/main.js`), quindi: tutto leggibile a 1600 px senza scroll orizzontale; funzionante a 1280 px (nessuno
   scroll orizzontale, colonne che si impilano) e a 1920 px (nessuno spazio sprecato). Contenuto nel contenitore con
   scroll proprio sotto la testata globale (56 px); le testate di pagina NON si incollano (come oggi: vedi il tuo
   referto); nessun elemento coperto dalla testata globale o dalla sidebar; z-index dei menu, dei fogli parametri,
   dei dialoghi e dei toast SOPRA la cornice (verifica aprendo un foglio parametri e un dialogo col guscio acceso).
6. **Stati**: hover, focus visibile (tastiera), disabled, loading/skeleton, vuoto, errore: tutti con la veste nuova e
   tutti ancora distinguibili. Le conferme armate (bottoni che aspettano il secondo clic) devono essere PIÙ evidenti
   di oggi, mai meno. Le righe cliccabili devono restare cliccabili con la stessa area (vedi §6 ladder).
7. **Icone**: puoi cambiare l'icona (lucide) di un elemento SOLO se il nome accessibile e il testo non cambiano; mai
   togliere un'icona che è l'unico contenuto di un bottone con `aria-label` (resta l'`aria-label`).
8. **Tema**: solo scuro (è il tema dell'app). Nessun tema chiaro.
9. **Prestazioni**: nessuna dipendenza, nessun JS; `npm run build` deve riuscire e la dimensione di `dist/assets`
   non deve crescere oltre il 5% rispetto a master (`du -sb dist/assets` prima e dopo, scrivilo nel referto).

## 5. Elenco delle pagine, in ORDINE DI PRIORITÀ (lavoro parziale = le prime prima), con i riferimenti del prototipo
Per ogni pagina: (a) leggi la schermata del prototipo nel file js indicato; (b) elenca i componenti di produzione che
la compongono (dall'inventario e dal codice); (c) applica la veste componente per componente; (d) verifica (§7);
(e) screenshot + immagine affiancata; (f) commit + push + PR aggiornata; (g) riga di referto. Poi la pagina dopo.
1. **Control Room** `/control-room` — prototipo `js/s_controlroom.js` (+ `trading.js` per DayBar/calendario,
   `params.js` per i fogli parametri). Blocchi, nell'ordine di oggi (non cambiarlo): testata con identità e data;
   fascia SOLDI VERI (esposizione conto, disponibile, rischio secondo i bot, ordini fuori dai bot, posizione live);
   tessere Runner CALCIO/TENNIS; stop di perdita giornaliera (riga per stop, cifra modificabile sul posto, conferma
   armata); chip degli 8 bot; riga «Quote dello scanner / Dati»; ModeBanner; Obiettivo di oggi (DayBar con
   `enfasi`, composizione, corsia PROVA); riga Storico; tessere sport LIVE/PROVA; Comando dei bot (ordini reali,
   freno, mercati, righe per bot con parametri, uscite, stake); proposte di uscita; schede partita (pre-match e live:
   linee O/U, esiti, cash out di partita, Mike, azioni); posizioni aperte LIVE/PROVA con stato; posizioni chiuse
   (giornata, filtri, raggruppamento, controprova); glossario e reperti; piè di pagina. Fogli parametri (Omega, Safe,
   Mike, scalper, 4 bot tennis): veste del prototipo `params.js`, stessi campi e testi.
2. **Programma del giorno** `/board` — `js/s_home.js`: rifinisci tabella, tab con pallino canale, countdown, badge
   in-play, quote back/lay, azioni; stati «canale off / in attesa / vuoto» con la veste `.ds-v2-vuoto`.
3. **Segui live** `/segui-live` e terminal calcio — `js/s_live.js` + `js/ladder.js` + `js/trading.js`: lista seguite,
   HabitatCard, top bar del terminal (modalità, orologio, P&L, saldo, runner, esposizione, overround, cash-out,
   KILL), banner rischio gol, tab mercati, ladder (vedi §6), stake preimpostati, Keep/Lapse/Take SP, 1-CLICK con
   conferma, toolbar degli strumenti armabili, conferma ordine «Se vince / Se perde», scalper.
4. **Mike** `/mike` — `js/s_calcio.js` (parte Mike): BotHeader, ModeBanner, allarmi, Giornata, 7 KPI, tab Partite
   (scheda a 11 zone), Operazioni, Risultati, Attività, Storico, cash out, foglio parametri.
5. **Safe Strategy** `/safe-strategy` (calcio e tennis) — `js/s_calcio.js` (parte Safe): BotHeader, modalità,
   SOLDI VERI, strategie, esecuzione, Giornata, KPI e rischio, tab calcio/tennis con le 4 sotto-tab, storico.
6. **Omega** `/omega` — `js/s_calcio.js` (parte Omega): BotHeader, Giornata, partite chiuse, KPI, tab Automatico/
   Missione/Manuale/Storico, foglio parametri a 10 gruppi.
7. **Tennis terminal** `/tennis/terminal` — `js/s_tennis.js` + `ladder.js`: header match, 4 bot con parametri reali,
   equity e attività, ladder tennis, Stats/Chart/Depth.
8. **Dashboard tennis** `/tennis` — `js/s_tennis.js`: partite del giorno (ieri/oggi/domani), tornei, preferiti, quote.
9. **Multi-ladder** `/multi-ladder`, **Ladder pop-out** `/ladder-popout` (finestra 640×780: tutto leggibile lì) —
   `js/s_live.js`, `ladder.js`.
10. **Market watch** `/market-watch`, **Live P&L** `/live-pnl` — `js/s_live.js`.
11. **Storico calcio** `/storico/calcio` e **Storico tennis** `/storico/tennis` — `js/s_storici.js`: testata con
    SOLDI VERI/PROVA esclusivo, filtri, KPI, per bot, equity, P&L per giornata, calendario, operazioni del giorno.
12. **Trade journal**, **Report personale**, **Watchlist**, **Match replay**, **Analytics**, **Cruscotto partite**
    (`/dashboard`) — `js/s_analisi.js`, `js/s_storici.js`.
13. **Scelta sport**, **Accesso** (landing), **Conferma email**, **Reimposta password**, **404** — `js/s_account.js`.
    La landing resta FUORI dal guscio: la sua veste cambia solo se è coerente con la sidebar/testata del guscio una
    volta dentro; non cambiare il flusso di login.

## 6. Il ladder e gli elementi con interazione fine (massima prudenza)
Ladder, griglie di prezzi, bottoni di stake, 1-CLICK, cash out, KILL: cambiano SOLO colori, tipografia, bordi,
spaziature INTERNE alle celle. NON cambiano: struttura del DOM, dimensione e posizione delle aree cliccabili
(verifica che i test del ladder e di `LadderView` restino verdi senza modifiche), ordine delle colonne (layout v2:
LAY a sinistra del prezzo, BACK a destra, come oggi), gestione del drag/scroll, le classi che i test cercano.
Per queste parti fai PRIMA uno screenshot `off` e `v2` e misura con un controllo automatico (Chromium) che i
`getBoundingClientRect` delle celle cliccabili del ladder siano uguali o più grandi in `v2` rispetto a `off`:
scrivilo nel referto.

## 7. Verifiche OBBLIGATORIE a ogni pagina (non a fine lavoro)
- `npx tsc -p tsconfig.app.json --noEmit` → 0 errori.
- `npx vitest run src/fotografia` → verde SENZA rigenerare le `off`; le `v2` rigenerate solo per classi (diff spiegato).
- `npx vitest run` suite intera → verde con lo stesso conteggio di partenza (314 file / 4829 test) + i tuoi test
  nuovi; NESSUN test esistente modificato. Attenzione: la fotografia sotto carico fotografa stati di caricamento e dà
  falsi rossi: lanciala a macchina scarica (mai in parallelo a Chromium o ad altre suite); se vedi un rosso
  «fotografia cambiata» ripeti a macchina scarica prima di concludere.
- `npm run build` verde; `du -sb dist/assets` entro +5% rispetto a master.
- Screenshot Chromium a 1280 e 1600 px, `off` e `v2`, in `AUDIT_2026-10-01/REDESIGN/confronto2/<pagina>.<stato>.<w>.png`,
  più l'immagine affiancata `confronto2/<pagina>.affianco.png` = prototipo (schermata corrispondente resa dal
  `prototipo/index.html#<id>`) | pagina `v2`. Per gli screenshot usa finti POPOLATI (dati realistici come nel
  prototipo: partite, quote, posizioni, P&L) in un harness SEPARATO dalla fotografia (`src/fotografia/supabaseFinto.ts`
  resta quello, perché la fotografia deve restare identica); l'harness popolato vive sotto `src/anteprima/` ed è
  usato solo dagli screenshot, mai dall'app.
- Test nuovi con FALSIFICAZIONE (rimetti il comportamento sbagliato → rosso → ripristino; output nel referto):
  (a) `cssGuscio.test.ts` esteso (§4.1); (b) un test che, per ogni file di `components/ui/*`, confronta le classi di
  default con quelle di master (snapshot delle stringhe `className`/`cva` dei componenti ui, salvato alla partenza):
  rosso se un default cambia; (c) un test di contrasto sui token usati dalle classi `.ds-v2-*` per testo e sfondo
  (soglie §4.3); (d) il controllo delle aree cliccabili del ladder (§6), anche solo come script ripetibile con output
  nel referto se non è integrabile in vitest.
- Conteggio delle chiamate: con guscio acceso e spento il numero di WebSocket locali e di RPC chieste da ogni pagina
  (già misurato dalla fotografia) deve restare UGUALE.

## 8. Consegna e referto
- Ramo `redesign/veste-completa` da `master` (`bc74611`+). Commit per PAGINA (o per blocco grande della Control
  Room), in italiano, percorsi espliciti (mai `git add -A`), messaggio che dice: pagina, componenti ritoccati, numeri
  di tsc/suite/fotografia. Push dopo OGNI commit. Pull request in bozza verso `master` aperta dopo la prima pagina e
  aggiornata a ogni push, titolo «Redesign veste completa — fedele al prototipo, dietro ui.shell (spento di default)».
- Referto `AUDIT_2026-10-01/REDESIGN/REFERTO_CLOUD_2.md` (anche nel corpo della PR), aggiornato a ogni pagina:
  tabella «pagina → componente → stato (fatto / lasciato: motivo) → classi usate → screenshot»; numeri di tsc, suite,
  fotografia, dimensione del build; falsificazioni con output; diff delle fotografie `v2` spiegato; bug e
  incongruenze SEGNALATI; correzioni di sola grafica ammesse elencate; «cosa non ho potuto verificare» (es. l'exe
  vero col backend vivo, i font veri se la rete è bloccata). Scrivi la verità: un «non fatto» dichiarato vale più di
  un «fatto» non provato: il coordinatore rileggerà il diff riga per riga, rilancerà suite e fotografia a macchina
  scarica e confronterà le immagini affiancate col prototipo prima di proporre all'utente la fusione.
- Lavora finché l'elenco §5 è completo. Se il credito o il tempo finiscono prima, fermati a fine pagina con tutto
  pushato e il referto aggiornato, e dichiara a che pagina sei arrivato: un lavoro parziale pulito vale, uno a metà no.
- Nessun build in produzione, nessun riavvio, nessuna modifica a `master`, nessun merge: domani mattina il
  coordinatore e l'utente verificano e fondono.
