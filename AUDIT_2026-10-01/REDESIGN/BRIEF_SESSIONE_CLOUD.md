# Brief per la sessione cloud — Redesign «guscio v2», parità 1:1

Sei l'esecutore (sessione cloud) del coordinatore admin-01 sul repo `Dani91x/python-database-automation`
(ramo `master`, commit di partenza `fc5afbd` o successivo). Lingua: italiano in tutto (commit, PR, commenti,
testi a schermo). L'app è un software desktop (Electron) di trading sportivo su Betfair con bot calcio e
tennis; frontend React 18 + TypeScript + Vite + Tailwind + shadcn in `frontend/`; backend Python e Supabase
che NON toccherai mai.

## Mandato
Realizzare il REDESIGN GRAFICO dell'intera app («guscio v2») con PARITÀ 1:1 di funzionalità rispetto a oggi:
stessi percorsi, stessi comandi, stessi testi, stessi dati, stessi identificativi dei test; cambia SOLO la
veste grafica. Il design approvato dall'utente è il prototipo in `AUDIT_2026-10-01/REDESIGN/prototipo/`
(index.html + js/*.js, dati finti) e il piano è `AUDIT_2026-10-01/REDESIGN/PIANO_INTEGRAZIONE.md`.
L'inventario di ogni pagina, blocco, comando, testo e testid è in
`AUDIT_2026-10-01/REDESIGN/INVENTARIO_FUNZIONALITA.md` e `inventario_parti/*.md`: è l'elenco di controllo,
da spuntare pagina per pagina. Leggi tutto questo PRIMA di scrivere una riga.

## Ordini tassativi dell'utente (testuali)
«La nuova versione deve funzionare nello stesso identico modo e senza nessuna regressione; ci abbiamo messo
mesi; non voglio errori nascosti o perdite di dati nascoste. Il nuovo design deve includere ogni singola
funzionalità senza omettere nulla. Devo poter tornare alla vecchia app con un click. Lavorate sul guscio
usando esattamente le stesse identiche funzionalità e percorsi di ora, semplicemente con una veste grafica
nuova. Nessuna modifica a codice, bot e logiche di sistema: qui facciamo solo la parte di design.»

Regole che ne derivano:
- VIETATO toccare: qualunque file Python, SQL, `migrations/`, `desktop/`, hook React (`use*.ts`), librerie di
  logica (`frontend/src/lib/**` salvo l'aggiunta di UN modulo nuovo per l'interruttore), chiamate
  RPC/Supabase, canali locali, testi a schermo esistenti, `data-testid` esistenti, ordine dei blocchi nelle
  pagine, conferme a due tempi, numeri e formattazioni. Nessuna RPC nuova, nessuna lettura in più.
- Bug o incongruenze che incontri: NON correggerli; elencali nel referto (file:riga, cosa, perché). Uniche
  correzioni ammesse: di sola grafica (es. il colore di PAPER che oggi varia fra pannelli, LAY ora `rose` ora
  `pink`), e vanno elencate anch'esse.
- Il guscio nuovo nasce SPENTO di default: l'app resta identica a oggi finché l'utente non lo accende.

## Architettura (decisa dal coordinatore, non negoziabile)
1. **Interruttore `ui.shell`**: modulo nuovo `frontend/src/lib/uiShell.ts` che legge/scrive
   `localStorage['ui.shell']` ∈ {'v2','off'} (try/catch, default 'off'), con ripiego alla variabile di build
   `VITE_UI_SHELL` ('v2'|'off', default 'off'); la chiave locale vince. Due comandi visibili, un clic
   ciascuno, che scrivono la chiave e ricaricano la pagina: nella testata del guscio nuovo «Torna alla grafica
   attuale»; nell'app attuale un piccolo bottone discreto «Prova la nuova grafica» nello stesso punto in ogni
   pagina (accanto al brand nelle testate esistenti, o un elemento fisso in basso a destra se è l'unico modo di
   non toccare le pagine). Nessun altro stato persistito.
2. **AppShell come layout route** di React Router v6 in `frontend/src/App.tsx`: con `ui.shell='v2'` le rotte
   protette (`/board`, `/control-room`, `/dashboard`, `/omega`, `/safe-strategy`, `/mike`, `/segui-live`,
   `/multi-ladder`, `/market-watch`, `/live-pnl`, `/storico/calcio`, `/storico/tennis`, `/tennis`,
   `/tennis/terminal`, `/trade-journal`, `/report-personale`, `/watchlist`, `/analytics`, `/match-replay`,
   `/select-sport`) vengono rese dentro `<AppShell><Outlet/></AppShell>`; con `'off'` l'albero delle rotte è
   ESATTAMENTE quello di oggi. Fuori dal guscio sempre: `/ladder-popout` (finestra 560×860), landing `/`,
   `/check-email`, `/reset-password`, 404. Prima schermata dopo il login col guscio acceso: `/board`
   (Programma del giorno); verifica come oggi si atterra su `/select-sport` e NON cambiare quel comportamento
   con guscio spento.
3. **Sidebar** (componenti nuovi in `frontend/src/components/shell/`): gruppi e voci come nel prototipo
   (Programma del giorno; Control Room; Calcio: Cruscotto partite, Omega, Safe Strategy, Mike, Segui live ·
   Scalper, Storico calcio; Tennis: Dashboard tennis, Tennis Terminal, Bot tennis, Safe Strategy · Tennis,
   Storico tennis; Trading: Multi-ladder, Ladder pop-out, Market watch, Live P&L, Watchlist; Analisi: Match
   replay, Analytics, Report personale, Trade journal; Account: Scelta sport, Esci), comprimibile, filtro
   Tutti/Calcio/Tennis che nasconde solo voci di menu. Ogni voce porta a una rotta ESISTENTE (le voci «Bot
   tennis» e «Safe Strategy · Tennis» portano dove il prototipo e l'inventario indicano: Terminal tennis e tab
   tennis di Safe). Etichette di stato dei bot accanto alle voci (LIVE/PROVA/FERMO) SOLO se il dato è già
   disponibile in un provider/contesto esistente senza letture nuove; altrimenti ometti e dillo.
4. **Testata globale in sola lettura**: runner calcio/tennis, canali locali, ordini LIVE/PROVA, saldo CONTO
   con esposizione e occhio: SOLO da dati già letti da hook/provider esistenti (vedi §E del piano); se per
   averli nel guscio servirebbe una lettura nuova, NON farla: metti l'indicatore solo dove il dato esiste già
   (es. dentro Control Room) e dichiaralo. Conta le chiamate: con guscio acceso e spento il numero di
   connessioni WebSocket e di chiamate REST a schermo fermo deve essere uguale.
5. **Le testate delle pagine di oggi restano nel DOM**. Per evitare la doppia navigazione aggiungi
   l'attributo `data-nav-legacy` SOLO agli elementi di pura navigazione duplicati (link al brand, bottoni
   «Dashboard», «Cambia sport», «Watchlist», «Report», «Analytics» delle navbar inline e di `TennisNav`) e
   nascondili via CSS quando `[data-shell="v2"]`; MAI nascondere comandi (stato, salute, PAPER/LIVE,
   Parametri, Avvia/Ferma, Storico, KILL, cash out, conferme). I test jsdom non applicano i CSS: gli elementi
   restano trovabili.
6. **Stile**: token e font di `frontend/src/index.css` e `tailwind.config.js` (nessun colore nuovo; Sora
   titoli, Inter testo, numeri tabulari), classi `.ds-*` nuove in `index.css` usate dal guscio e, nelle fasi
   successive, dalle pagine SOLO via `className` e contenitori. Contenuto in un contenitore con scroll proprio
   sotto la testata globale (56 px) così gli `sticky top-0` delle pagine restano corretti; nessuno scroll
   orizzontale a 1280 px; verifica 1280/1600/1920.
7. **Control Room**: stessi blocchi, stesso ordine, stessi testi e testid; solo classi e griglie (§C del
   piano, elenco dei testid da preservare). `cr-riga-paper` deve restare ASSENTE (un test lo verifica).
   Nessun cambio a `useControlRoom.ts` e agli altri hook.

## Fasi (nell'ordine; ogni fase = commit separati + push; PR in bozza aperta dopo la fase 1 e aggiornata a ogni fase)
- **Fase 0 — garanzia di parità**: (a) classi `.ds-*` in `index.css` non ancora usate; (b) il TEST
  «FOTOGRAFIA»: `frontend/src/fotografia/fotografia.test.tsx` che rende OGNI pagina protetta con finti
  deterministici (riusa i finti già presenti nei test di ciascuna pagina: `pages/*.test.tsx`; stesse chiavi e
  tipi del vero) in ENTRAMBI gli stati dell'interruttore e scrive, per pagina, l'elenco ordinato di: testi
  visibili (textContent dei nodi foglia, normalizzati), `data-testid`, bottoni/link/input (ruolo + nome
  accessibile + href/disabled), in `frontend/src/fotografia/snapshot/<pagina>.<stato>.json`. Il test fallisce
  se la fotografia con `off` cambia rispetto a quella salvata alla fase 0 (parità byte per byte con oggi) e
  se, con `v2`, l'insieme di testid/comandi/testi delle PAGINE (escluso ciò che il guscio aggiunge, elencato in
  una lista bianca esplicita) differisce da quello con `off`. Committa le fotografie di partenza PRIMA di
  qualunque altra modifica: sono la prova.
- **Fase 1 — guscio**: `uiShell.ts`, `AppShell`, sidebar, testata globale, interruttori a un clic, layout
  route in `App.tsx`, `data-nav-legacy`. Con `off` l'app è identica (fotografia identica); con `v2` solo la
  cornice cambia.
- **Fase 2 — Programma del giorno** (`pages/Board.tsx`): righe in tabella densa e tab con conteggio come nel
  prototipo; solo `className`.
- **Fase 3 — Control Room**: §C del piano.
- **Fase 4 — pagine bot** (Omega, Safe Strategy, Mike) e `components/trading/*`: solo `className`.
- **Fase 5 — tennis e live** (TennisMatchesList, TennisTerminal, TennisBotPanel, SeguiLive, LadderView e
  pannelli, Multi-ladder, Ladder pop-out).
- **Fase 6 — storici, Market watch, Live P&L, Trade journal, Report personale, Watchlist, Match replay,
  Analytics, Cruscotto partite (Dashboard)**.
- **Fase 7 — account** (Scelta sport, Accesso, Conferma email, Reimposta password, 404) e rifinitura;
  checklist finale pagina per pagina contro l'inventario.
Se il budget o il tempo finiscono prima della fase 7, FERMATI a fine fase con tutto pushato e la PR
aggiornata: un lavoro parziale ma pulito vale, uno a metà no. Dichiara nel referto a che fase sei arrivato.

## Ambiente e verifiche
- `cd frontend && npm ci` (usa il lockfile). Comandi: `npx tsc -p tsconfig.app.json --noEmit` (deve dare 0
  errori: regola di casa dal 17/09, mai `@ts-ignore`/`any` per zittire), `npx vitest run` (suite intera, oggi
  310 file / 4764 test verdi, 10/50 saltati; circa 7 minuti), `npm run build`. Esistono guardie:
  `designGuard.test.ts`, `zeroPerAssente.test.ts` e altri: devono restare verdi senza eccezioni nuove.
- A OGNI fase: tsc 0; suite intera verde con lo stesso numero di test di prima + i nuovi; fotografia `off`
  identica; nessun test esistente modificato (se uno DEVE cambiare, motivo scritto nel test e nel referto, e
  deve essere un cambio di sola struttura DOM mai di testo/testid); FALSIFICAZIONE dei test nuovi (rimetti il
  comportamento vecchio, mostra il rosso, ripristina; output nel referto).
- Screenshot: prova a rendere l'app con un browser headless (Playwright/Chromium se installabile, oppure
  `vite preview` + chromium headless) con i finti della fotografia o con dati finti, a 1280 e 1600 px, per
  ogni pagina in `off` e in `v2`; salvali in `AUDIT_2026-10-01/REDESIGN/confronto/<pagina>.<stato>.<larghezza>.png`
  e linkali nella PR. Se non ci riesci, dillo chiaramente: l'utente verificherà a occhio con l'interruttore.
- Mai `git add -A`: aggiungi i percorsi espliciti. Commit in italiano, uno per unità di lavoro, messaggi che
  dicono cosa e come verificato. Ramo: `redesign/guscio-v2` da `master`. Push dopo ogni fase. PR verso
  `master` in bozza, titolo «Redesign guscio v2 — parità 1:1, interruttore ui.shell (spento di default)»,
  corpo = referto aggiornato.
- `.env` non c'è e non serve: nessun accesso al database. Non inventare dati veri.

## Referto (nel corpo della PR e in `AUDIT_2026-10-01/REDESIGN/REFERTO_CLOUD.md`)
Per ogni fase: file toccati; checklist dell'inventario spuntata pagina per pagina (ogni blocco e comando:
«presente, invariato»); numeri di tsc, suite, fotografia; falsificazioni con output; screenshot; conteggio
WS/REST con guscio acceso/spento; elenco delle correzioni di sola grafica fatte; ELENCO DEI BUG E DELLE
INCONGRUENZE TROVATI E NON CORRETTI; «cosa non ho potuto verificare». Scrivi la verità: un «non verificato»
dichiarato vale più di un «fatto» non provato. Il coordinatore rileggerà il diff riga per riga, rilancerà
suite e fotografia e proverà mutazioni prima di qualunque fusione.
