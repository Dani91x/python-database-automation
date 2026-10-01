# Referto della sessione cloud — Redesign «guscio v2» (parità 1:1, interruttore `ui.shell` spento di default)

Mandato: `AUDIT_2026-10-01/REDESIGN/BRIEF_SESSIONE_CLOUD.md`. Ramo `redesign/guscio-v2` da `master` (`2d8ee70`).
Letti prima di scrivere codice: brief, `PIANO_INTEGRAZIONE.md`, `INVENTARIO_FUNZIONALITA.md`, `inventario_parti/A…E`,
`RICERCA_MERCATO.md`, prototipo (`prototipo/index.html`, `js/core.js`, `js/boot.js` e schermate).

**Fase raggiunta: 7 — tutte le fasi 0-7 completate e pushate**, ognuna con commit propri, tsc 0, suite intera
verde, fotografia identica. Le fasi 2-7 sono una veste **prudente** (contenitori, griglie, superfici, linguette,
tabella densa del Programma): non replicano ogni dettaglio del prototipo dentro i componenti (vedi «Cosa resta»).

**Prova di parità visiva con `ui.shell` spento** (la più forte di questo lavoro): l'app di `master` e il codice
finale, entrambi con `off`, scattati uno dopo l'altro in Chromium su 22 schermate × 1280/1600 px: **pixel identici
salvo il riquadro in basso a destra del bottone «Prova la nuova grafica»** (`confronto/off_contro_master.txt`; unica
altra differenza: 46 pixel dell'animazione d'ingresso delle card di Scelta sport, presente anche fra due scatti
dello stesso codice). Tutta la veste nuova vive in regole CSS confinate a `[data-shell="v2"]`.

---

## Numeri a ogni fase

| | tsc (`tsconfig.app.json`) | vitest suite intera | fotografia |
|---|---|---|---|
| partenza (`2d8ee70`) | 0 errori | 310 file / 4764 test verdi, 10 file / 50 test saltati | — |
| fase 0 | 0 errori | 311 file / 4790 verdi (+1 file, +26 test), 10/50 saltati | 26/26, tre giri identici |
| fase 1 | 0 errori | 313 file / 4814 verdi (+2 file, +24 test), 10/50 saltati | 26/26: tutte le `*.off.json` e `*.v2.json` IDENTICHE a quelle della fase 0 (nessun file di pagina riscritto) |
| fase 2 | 0 errori | 314 file / 4816 verdi (+1 file, +2 test: guardia CSS) | 26/26 identica |
| fase 3 | 0 errori | 314 / 4817 (+1 test: guardia sticky) | 26/26 identica |
| fase 4 | 0 errori | 314 / 4817 (vedi nota su `MarketWatch.test.tsx`) | 26/26 identica |
| fase 5 | 0 errori | 314 / 4817 | 26/26 identica |
| fase 6 | 0 errori | 314 / 4817 | 26/26 identica |
| fase 7 | 0 errori | 314 / 4817, `npm run build` verde | 26/26 identica |

Totale test nuovi: 53 (fotografia 26, interruttore 9, guscio 15, guardia CSS 3) = 4817 − 4764. Le fotografie delle
pagine (`*.off.json`, `*.v2.json`) non sono mai state riscritte dalla fase 0.

Nota sulla fase 4: il primo giro della suite intera ha dato 1 rosso in `src/pages/MarketWatch.test.tsx` («paper e live
dello stesso evento…»: letto `live€0.00` invece di `€3.00`) mentre in parallelo giravano gli screenshot. La fase 4 non
tocca `MarketWatch.tsx` (il suo diff da master è la sola classe `ds-v2-non-sticky` della fase 3, con cui la suite era
verde). Il file da solo: 5 giri su 5 verdi; la suite intera rilanciata senza altro carico: 314/4817 verdi, EXIT 0.
Causa: il test asserisce il testo subito dopo `findAllByTestId` (senza `waitFor`), quindi sotto carico può leggere la
riga prima che arrivino le posizioni. Fragilità del test preesistente, NON corretta (regola: nessun test esistente
modificato); il commit della fase 4 era già partito prima della rilettura (errore mio di procedura: da lì la suite gira
senza carico e l'esito si controlla prima del commit).

`npm run build` verde alla fase 1. Nessun test esistente modificato. `designGuard.test.ts` e `zeroPerAssente.test.ts`
verdi senza eccezioni nuove.

Ambiente: `npm ci` fallisce sul conflitto di peer `react@19` / `react-helmet-async@2.0.5` (peer `^18`): installato con
`npm ci --legacy-peer-deps`, stesso lockfile, nessun file modificato (vedi «Incongruenze», n. 1).

---

## Fase 0 — garanzia di parità

File: `frontend/src/fotografia/fotografia.test.tsx`, `frontend/src/fotografia/supabaseFinto.ts`,
`frontend/src/fotografia/snapshot/*.json` (commit `bb2c857`, PRIMA di ogni altra modifica), `frontend/src/index.css`
(classi `.ds-*`, commit `dfe8766`).

Come funziona la fotografia:
- rende il vero `<App/>` (rotte, `ProtectedRoute`, provider) per 26 schermate: le 20 rotte protette, Tennis Terminal anche
  con un match nei parametri, `/ladder-popout`, landing, check-email, reset-password, 404;
- per ogni schermata la rende con `ui.shell='off'` e con `'v2'` e registra nell'ordine del DOM: testi (ogni nodo di
  testo, normalizzato), `data-testid`, comandi (ruolo + nome accessibile + `href`/`disabled`/premuto/selezionato/
  spuntato). Le classi CSS NON entrano: il redesign cambia solo quelle;
- dati: client Supabase finto con la stessa forma delle risposte di supabase-js (`{data,error,count,status,statusText}`):
  `rpc` → `null`, `from().select()` → `[]`, canali realtime muti, sessione dell'owner; canali locali spenti (stub di
  `src/test/setup.ts`); orologio fermo al 01/10/2026 10:00 Europe/Rome;
- regole: (1) `off` identica byte per byte a `snapshot/<pagina>.off.json`; (2) `v2` = `off` sul contenuto delle pagine;
  ciò che il guscio aggiunge vive in elementi `data-shell-chrome`, registrato a parte in `<pagina>.<stato>.guscio.json`
  con **lista bianca esplicita** dei testid (`LISTA_BIANCA_GUSCIO`); (0, aggiunta in fase 1) stesse RPC, tabelle, canali
  realtime e **WebSocket locali** costruiti con guscio acceso e spento;
- aggiornare è una decisione: `FOTOGRAFIA_AGGIORNA=1` (tutto) o `FOTOGRAFIA_AGGIORNA=guscio` (solo `*.guscio.json`).

Limite dichiarato: i finti per pagina dei test esistenti (`pages/*.test.tsx`) non sono riusabili in un solo file
(`vi.mock` vale per file e quei finti si contraddicono): la fotografia fissa lo stato «backend vuoto» di ogni pagina.
Gli stati popolati restano coperti dai 4764 test esistenti, che non sono stati toccati e restano verdi.

Falsificazione della fase 0 (comportamento vecchio rimesso, rosso, ripristino):
```
testo del Board cambiato ("canale locale" -> "canale LOCALE")
  → la fotografia board.off.json e' cambiata                       Tests 1 failed
data-testid "cr-testata" rinominato in "cr-testata-x"
  → la fotografia control-room.off.json e' cambiata                Tests 1 failed
controprova: SOLO className cambiata nel Board (max-w-5xl -> max-w-6xl)
  → Tests 2 passed                                                  (le classi non contano, come deve essere)
```

---

## Fase 1 — guscio

### File toccati
Nuovi:
- `frontend/src/lib/uiShell.ts` (+ `uiShell.test.ts`): l'interruttore. `localStorage['ui.shell']` ∈ {`v2`,`off`} con
  try/catch, ripiego su `VITE_UI_SHELL`, default `off`; la chiave locale vince; valore estraneo = assente.
  `cambiaUiShell(v)` scrive e ricarica; `rottaDopoAccesso()` = `/board` col guscio acceso, `/select-sport` spento.
- `frontend/src/components/shell/navigazione.ts`: voci della sidebar (gruppi del prototipo), rotte del guscio, mappa
  dei canali che ogni pagina apre già.
- `frontend/src/components/shell/AppShell.tsx`: layout route, griglia `sidebar | (testata 56 px + contenuto con scroll
  proprio)`, `data-shell="v2"` sulla radice; sidebar e testata dentro `data-shell-chrome`.
- `frontend/src/components/shell/Sidebar.tsx`: gruppi e voci, comprimibile, filtro Tutti/Calcio/Tennis (solo voci di
  menu), «Esci» = `supabase.auth.signOut()` + `/` come oggi in Scelta sport/Cruscotto/TennisNav.
- `frontend/src/components/shell/TestataGlobale.tsx`: dove sei + stato dei canali (vedi sotto) + «Torna alla grafica
  attuale».
- `frontend/src/components/shell/ProvaNuovaGrafica.tsx`: nell'app attuale, bottone fisso in basso a destra «Prova la
  nuova grafica» (solo sulle 20 rotte interne; non su pubbliche, 404 e pop-out). In basso a destra non c'è altro: i
  toast stanno in alto al centro.
- `frontend/src/components/shell/AppShell.test.tsx` (15 test).

Modificati:
- `frontend/src/App.tsx`: con `off` il ramo `<Routes>` di oggi è **lo stesso testo**, solo racchiuso in un frammento
  con `<ProvaNuovaGrafica/>` accanto; con `v2` il componente `RotteGuscioV2` rende le 20 rotte protette come figlie di
  `<Route element={<ProtectedRoute><AppShell/></ProtectedRoute>}>`; fuori dal guscio `/ladder-popout`, `/`,
  `/check-email`, `/reset-password`, `*`. Lo stato è letto una volta (`useState(leggiUiShell)`): il cambio passa sempre
  da un ricaricamento.
- `frontend/src/index.css`: regola `[data-shell="v2"] [data-nav-legacy]{display:none !important}`.
- `frontend/src/pages/LandingPage.tsx`, `frontend/src/components/landing/AuthSection.tsx`: `navigate('/select-sport')`
  → `navigate(rottaDopoAccesso())`. Con guscio spento la rotta è la stessa stringa di oggi; con guscio acceso
  `/board` (brief, punto 2). Verificato che oggi si atterra su `/select-sport` (login e redirect della landing).
- `data-nav-legacy` (solo attributo) su 24 elementi di pura navigazione: brand «AI TERMINAL» di Board, Analytics,
  Watchlist, Report personale, Segui live, Match replay, BotHeader (→ `/select-sport`), TennisNav (→ `/tennis`);
  «‹ Dashboard» di Board, Analytics, Watchlist, Report personale, Segui live, Match replay; «Report» in Watchlist;
  «Watchlist» in Report personale; «Cambia sport», «Watchlist», «Report», «Analytics» del Cruscotto e di TennisNav.
  Mai su comandi: restano visibili stato, salute, PAPER/LIVE, Parametri, Avvia/Ferma, Storico, KILL, cash out,
  conferme, «Esci» delle testate, «CONTROL ROOM», «Segui Live», «Market Watch», «P&L», «Journal», «Match Replay», i
  «Torna a …». Il brand cliccabile del Cruscotto NON è marcato: non naviga, riporta alla lista (stato interno). La
  `Testata` della Control Room è intera (contenuto, non navigazione).
- `frontend/src/fotografia/fotografia.test.tsx`: conteggio dei WebSocket, lista bianca, modalità `guscio`; nuove
  fotografie della sola cornice `snapshot/*.guscio.json` (le fotografie delle pagine non sono state riscritte).

### Testata globale: cosa c'è e cosa no (dichiarazione)
- **Canali locali**: `useLocalStatus` apre il canale al primo accesso (`getLocalChannel` connette nel costruttore):
  chiedere lo stato di un canale che la pagina non apre aggiungerebbe una connessione. Quindi la testata mostra lo
  stato **solo dei canali che la pagina apre già da sola**, misurati dalla fotografia: Programma del giorno, Market
  watch, Live P&L → runner calcio e tennis; Control Room → tutti e 8; Omega → 47334; Safe → 47335; Mike → 47333. Sulle
  altre pagine l'indicatore non c'è. Pallino grigio = spento, mai verde finto. (Il Tennis Terminal apre 47332 solo
  con un match selezionato: escluso, per non anticiparlo.)
- **Ordini LIVE/PROVA per bot** e **saldo CONTO con esposizione e occhio**: NON presenti. Oggi li legge solo la Control
  Room (`useControlRoom`, `SaldoBetfairCard`) e le pagine dei bot: per averli nel guscio servirebbero letture nuove o
  modifiche agli hook. Restano dove sono, identici (in Control Room `ModeBanner`, chip dei bot, `SaldoBetfairCard`).
- **Etichette LIVE/PROVA/FERMO accanto alle voci della sidebar**: omesse per lo stesso motivo.

### Conteggio WS/REST con guscio acceso e spento
- jsdom (fotografia, 26 schermate): RPC distinte, tabelle, canali realtime Supabase e URL dei WebSocket locali
  costruiti **uguali** in `off` e `v2` per ogni schermata (asserzione 0 del test).
- Chromium headless (Vite con il client finto, 22 schermate × 2 stati × 1280/1600, più 1920 per 4): WebSocket locali
  costruiti dalla pagina, contati avvolgendo `window.WebSocket` dopo 3,5 s a schermo fermo:

| schermata | canali (porte) | WebSocket costruiti off / v2 |
|---|---|---|
| Programma del giorno | 47331, 47332 | 6 / 6 |
| Control Room | 47331-47338 | 16 / 16 |
| Omega / Safe / Mike | 47334 / 47335 / 47333 | 3 / 3 ciascuna |
| Market watch, Live P&L | 47331, 47332 | 6 / 6 |
| Tennis Terminal con match | 47332 | 3 / 3 |
| Ladder pop-out (fuori dal guscio) | 47331 | 3 / 3 |
| tutte le altre | — | 0 / 0 |

  (I numeri oltre il numero di canali sono i tentativi di riconnessione del client, canali rifiutati in anteprima.)
  REST: nell'anteprima nessuna chiamata di rete verso Supabase (client finto); le RPC chieste sono quelle contate in
  jsdom, uguali. Non misurato sull'exe vero con il backend vivo (vedi «Cosa non ho potuto verificare»).

### Falsificazioni della fase 1 (comportamento sbagliato rimesso, rosso, ripristino)
```
interruttore acceso di default ('off' -> 'v2')                       → expected 'v2' to be 'off' (4 rossi)
la chiave locale non vince piu' sulla build                           → expected 'v2' to be 'off'   Tests 1 failed | 8 passed
la testata chiede anche il runner calcio su Omega                     → expected [ 'omega', 'calcio' ] to deeply equal [ 'omega' ]
data-nav-legacy su un comando (Esci di TennisNav)                     → TennisNav.tsx:128 data-nav-legacy su un elemento che non e' navigazione
il guscio perde la rotta /mike                                        → expected 'function RotteGuscioV2() …' to contain '<Route path="/mike" element='
filtro Calcio che non nasconde il tennis                              → expected <div …> to be null
fotografia: WebSocket in piu' su Omega                                → omega: col guscio acceso cambiano le chiamate al backend
fotografia: il guscio scrive un testo FUORI dalla cornice marcata     → mike: col guscio acceso la pagina e' diversa
fotografia: «Prova la nuova grafica» senza data-shell-chrome          → la fotografia watchlist.off.json e' cambiata
```

### Screenshot
(Rifatti sullo stato FINALE della fase 7; `board-con-tabellone.*.png` = Programma col canale finto `CANALE_FINTO=1`.)
`AUDIT_2026-10-01/REDESIGN/confronto/<pagina>.<off|v2>.<1280|1600>.png` per 22 schermate (le 20 interne, Tennis
Terminal con match, Ladder pop-out) e `.1920.png` per Control Room, Segui live, Tennis Terminal con match, Mike.
Rifacibili con `AUDIT_2026-10-01/REDESIGN/confronto/strumenti/` (`node …/server.mjs`, poi
`node scatta.mjs <uscita> [pagine] [larghezze]`); misure in `confronto/misure_1280_1600.json` e `misure_1920.json`.
Resi con Chromium headless su Vite con il client Supabase finto (backend vuoto, canali locali rifiutati), font e
texture esterni bloccati (si vede il font di ripiego). Esito misurato: **nessuno scroll orizzontale** a 1280, 1600 e
1920, né della pagina né del contenitore del guscio; **nessun errore JavaScript** in pagina; il guscio compare su tutte
le 21 schermate interne e mai sul pop-out; «Prova la nuova grafica» compare solo con `off`.

### Checklist dell'inventario (fase 1)
Con la fase 1 nessuna pagina ha cambiato testi, testid, comandi o ordine: la prova è la fotografia (testi, testid e
comandi identici byte per byte, `off` e `v2`, per tutte le 26 schermate) più la suite esistente invariata e verde.
Le uniche differenze dentro le pagine sono l'attributo `data-nav-legacy` (nessun effetto con `off`; con `v2` nasconde
via CSS i soli 24 elementi elencati sopra, che restano nel DOM).

| rotta | blocchi e comandi (inventario) | stato |
|---|---|---|
| `/board` | navbar (brand, Safe Strategy, Segui Live, ‹ Dashboard), titolo, tab ⚽/🎾 con pallino canale, stati del canale, righe | presente, invariato; brand e ‹ Dashboard nascosti col guscio |
| `/control-room` | testata, ModeBanner, Obiettivo/Saldo, Storico, tessere sport, Comando dei bot, uscite, banco, diagnostica, piè | presente, invariato (1172 righe di fotografia identiche) |
| `/dashboard` | lista Partite del Giorno, barra comandi, dettaglio | presente, invariato; Cambia sport/Watchlist/Report/Analytics nascosti col guscio |
| `/omega`, `/safe-strategy`, `/mike` | BotHeader (stato, salute, Storico, PAPER/LIVE, Parametri, Avvia/Ferma), ModeBanner, giornata, KPI, tab | presente, invariato; solo il brand nascosto col guscio |
| `/segui-live` | navbar (Market Watch, P&L, Journal, Match Replay, ‹ Dashboard), lista seguite, terminal | presente, invariato; brand e ‹ Dashboard nascosti col guscio |
| `/multi-ladder`, `/market-watch`, `/live-pnl`, `/trade-journal` | top bar «‹ Terminal / ‹ Segui live», contenuti | presente, invariato (top bar non marcata: non era nell'elenco del brief) |
| `/storico/calcio`, `/storico/tennis` | testata con ‹ Control Room e «passa al …», filtri, KPI, per bot, equity, calendario | presente, invariato |
| `/tennis`, `/tennis/terminal` | TennisNav (brand, Cambia sport, Watchlist, Report, Analytics, email, Esci), contenuti | presente, invariato; brand e 4 bottoni di navigazione nascosti col guscio, email ed Esci visibili |
| `/report-personale`, `/watchlist`, `/analytics`, `/match-replay` | navbar inline, contenuti, dialoghi | presente, invariato; brand, ‹ Dashboard, Report/Watchlist nascosti col guscio |
| `/select-sport` | 5 card, CONTROL ROOM, Esci | presente, invariato (brand non cliccabile: non marcato) |
| `/ladder-popout`, `/`, `/check-email`, `/reset-password`, 404 | — | fuori dal guscio in entrambi gli stati; invariati |

### Correzioni di sola grafica fatte
- Solo col guscio acceso: la radice delle pagine «a tutta altezza» (`min-h-screen` / `h-screen`, figlio diretto del
  contenitore) è alta quanto il contenitore e non quanto la finestra (`index.css`, `.ds-contenuto > .min-h-screen`).
  Senza, Programma del giorno, Scelta sport, Segui live, Market watch, Tennis Terminal scorrevano di 56 px a vuoto
  (misurato in Chromium: `scrollHeight` 800 su 744 → 744 su 744; Scelta sport 752 per contenuto proprio). Con `off`
  nessun effetto (la regola vive solo dentro `.ds-contenuto`).
- Il colore unico di PAPER e `pink`→`rose` sono previsti per le fasi delle pagine e solo se approvati: non fatti.

---

## Fasi 2-7 — veste delle pagine

Regola comune (garantita da `src/fotografia/cssGuscio.test.ts`): le pagine ricevono solo classi `ds-v2-*` e ogni
regola che le nomina sta sotto `[data-shell="v2"]`; ogni classe `ds-v2-*` usata esiste nel foglio. Con `off` sono
inerti (prova pixel sopra). Nessun testo, testid, comando, hook, RPC o ordine di blocchi cambiato (fotografia).

| fase | file | cosa cambia col guscio acceso |
|---|---|---|
| 2 | `pages/Board.tsx` | righe in tabella densa (un pannello, righe separate da linea, hover), linguette ⚽/🎾 con sottolineatura primary, contenitore fino a 1280 px, griglia di sfondo tolta. **Conteggio nelle linguette NON fatto**: sarebbe un testo nuovo e le righe vivono dentro `SportBoard` (servirebbe spostare lo stato: logica). |
| 3 | `pages/ControlRoom.tsx`, `components/trading/PageShell.tsx`, `components/ui/tabs.tsx` + 21 testate | banco come nel prototipo: sopra 1360 px tre colonne (tab, Uscite, Opportunità), fino a 1360 px le due colonne di decisione accanto alle tab impilate, fino a 1100 px in colonna (sempre visibili, ordine DOM invariato); testata e contenitore a tutta larghezza; linguette con sottolineatura primary (nessuno sfondo di significato toccato); **sticky di pagina come oggi** (vedi sotto). |
| 4 | `components/trading/{BotHeader,StatTile,ModeBanner,DayBar,EquityCard,PerformancePanel}.tsx` | BotHeader largo; tessere KPI e pannelli con fondo, bordo, raggio e ombra del prototipo; nessun colore di significato toccato (LIVE rosso, PAPER verde, toni P&L). Omega, Safe, Mike ereditano il contenitore largo da PageShell. |
| 5 | `pages/{TennisDashboard,TennisTerminal,SeguiLive}.tsx`, `components/tennis/{TennisNav,TennisMatchesList}.tsx` | contenitori larghi, griglia di sfondo tolta. LadderView, GridView e i 7 pannelli strumento NON toccati. |
| 6 | `pages/{ReportPersonale,Watchlist,MatchReplay,Analytics,Dashboard,StoricoSport}.tsx` | testate e contenuti a tutta larghezza, griglia di sfondo tolta; Watchlist resta stretta; Market watch, Live P&L, Trade journal hanno già contenitori propri. |
| 7 | `pages/SelectSport.tsx` | testata larga, griglia di sfondo tolta. Le pagine pubbliche e il pop-out restano fuori dal guscio in entrambi gli stati: identiche. |

### Scoperta della fase 3: gli «sticky» di pagina oggi non restano incollati
Nell'app di oggi `html` e `body` hanno `overflow-x: hidden` (`index.css`): il body diventa il contenitore di
scorrimento ma non scorre (scorre il documento), quindi le 21 testate/barre `sticky top-0` di pagina (navbar inline,
BotHeader, TennisNav, testata della Control Room, testata dello Storico, barre di Market watch/Live P&L/Trade journal/
Multi-ladder, TabsList di Omega/Safe/Mike, barre di Segui live e Tennis Terminal) **scorrono via** (misurato in
Chromium: `top` da 0 a −400 dopo 400 px). Dentro il guscio, dove il contenuto scorre in `.ds-contenuto`, si sarebbero
incollate per davvero: la testata della Control Room (~540 px) avrebbe coperto metà schermo. Per non cambiare il
comportamento, quei 21 elementi sono marcati `ds-v2-non-sticky` e nel guscio scorrono via come oggi (misurato:
`top` 56 → −344). Gli sticky interni (intestazioni di tabelle con scroll proprio) non sono toccati. Guardia: ogni
`sticky` di pagina deve avere la marca (falsificata: tolta dal Board → rosso). Il difetto di oggi NON è corretto.

### Falsificazioni delle fasi 2-7
```
regola .ds-v2-riga non confinata a [data-shell=v2]          → regole .ds-v2-* che varrebbero anche con ui.shell=off: [ '.ds-v2-riga' ]
refuso ds-v2-rigaa nel Board                                  → [ 'pages/Board.tsx: ds-v2-rigaa' ]
tolto ds-v2-non-sticky dalla navbar del Board                 → [ 'pages/Board.tsx:232' ]
```

---

## Bug e incongruenze trovati e NON corretti
1. `frontend/package.json`: `react@^19.2.4` con `react-helmet-async@^2.0.5`, che dichiara peer `react ^16.6 || ^17 || ^18`:
   `npm ci` puro fallisce (ERESOLVE); serve `--legacy-peer-deps`. Nessun file toccato.
2. `pages/SafeStrategy.tsx:1459-1464`: la scheda 🎾 Tennis non si può aprire da un indirizzo (nessun parametro d'URL):
   la voce «Safe Strategy · Tennis» porta a `/safe-strategy` e la scheda va scelta a mano. Per aprirla direttamente
   servirebbe una modifica di logica alla pagina: non fatta.
3. `/ladder-popout` senza `market` ed `event` mostra «Parametri mancanti»: la voce «Ladder pop-out» della sidebar apre
   la finestra 560×860 come il bottone «stacca», ma senza un mercato è vuota. Il pop-out utile nasce dal ladder.
4. «Tennis Terminal» e «Bot tennis» portano alla stessa rotta: quando sei lì sono evidenziate tutte e due (come nel
   prototipo, dove «Bot tennis» è una scheda del terminal). Idem «Safe Strategy» e «Safe Strategy · Tennis».
5. `frontend/src/index.css` (`html, body { overflow-x: hidden }`): le 21 testate `sticky top-0` di pagina non restano
   incollate nell'app di oggi (vedi «Scoperta della fase 3»). Nel guscio il comportamento è stato mantenuto uguale.
6. `src/pages/MarketWatch.test.tsx:167-170`: asserzione immediata dopo `findAllByTestId` (senza `waitFor`), fragile sotto
   carico (un rosso visto in fase 4, poi 5/5 e suite verde da sola).
7. Già nell'inventario e ancora veri (non toccati): nessun link a `/board` nell'app attuale (col guscio è la prima voce);
   tre «home» diverse; PAPER in tre colori nei pannelli live; LAY `rose`/`pink`; mojibake in `ScalperPanel.tsx`;
   Trade journal con filtro «tutte»; `FixtureSelector.tsx` non montato.

## Cosa non ho potuto verificare
- L'exe Electron vero (Windows) col backend vivo: non disponibile qui. Il conteggio WS/REST «a schermo fermo sulla
  Control Room con l'exe acceso» va ripetuto dall'utente o dal coordinatore; qui è misurato in jsdom e in Chromium
  headless con dati finti.
- Il primo atterraggio dopo il login reale (Supabase vero) col guscio acceso: verificato solo da test unitario di
  `rottaDopoAccesso()` e dalla lettura del codice.
- I font Sora/Inter negli screenshot (rete esterna bloccata nell'anteprima): le immagini usano il font di ripiego.
- Gli stati popolati delle pagine nella fotografia (vedi limite della fase 0).

## Cosa resta (onestà sul perimetro)
- Le fasi 2-7 sono fatte, ma la veste è prudente: contenitori, griglie, superfici, KPI, linguette, Programma in
  tabella densa, banco della Control Room. Dentro i componenti (ladder, pannelli strumento, schede partita della
  Control Room, tabelle di storici e journal, chip quote back/lay del prototipo) la grafica è quella di oggi.
  Proseguire si fa con lo stesso metodo (classi `ds-v2-*` confinate, fotografia, guardia, prova pixel con `off`).
- Non fatte perché richiedono una decisione dell'utente o una modifica di logica: conteggio nelle linguette del
  Programma; colore unico di PAPER nei pannelli live e `pink`→`rose` (piano §B: «solo se l'utente lo approva»);
  ordini LIVE/PROVA e saldo nella testata (letture nuove); scheda tennis di Safe apribile da URL.

## Checklist finale pagina per pagina (fase 7)
Per ogni rotta dell'inventario: blocchi, comandi, testi e testid **presenti e invariati** (fotografia `off` = fase 0 =
`v2`, byte per byte, 26 schermate); `data-nav-legacy` solo sui 24 elementi di pura navigazione; con `off` pixel
identici a master salvo il bottone «Prova la nuova grafica».

| rotta | dentro il guscio | veste v2 (fase) | parità |
|---|---|---|---|
| `/board` | sì (prima voce) | tabella densa, linguette (2) | presente, invariato |
| `/control-room` | sì | banco 3/2/1 colonne, contenitore largo, linguette, sticky come oggi (3) | presente, invariato |
| `/dashboard` | sì | contenitore largo (6) | presente, invariato |
| `/omega`, `/safe-strategy`, `/mike` | sì | PageShell largo (3), KPI/pannelli/banner (4) | presente, invariato |
| `/segui-live` | sì | contenitore largo (5) | presente, invariato |
| `/multi-ladder`, `/market-watch`, `/live-pnl`, `/trade-journal` | sì | barre sticky come oggi (3) | presente, invariato |
| `/storico/calcio`, `/storico/tennis` | sì | PageShell largo (3), testata larga (6) | presente, invariato |
| `/tennis`, `/tennis/terminal` | sì | contenitori larghi (5) | presente, invariato |
| `/report-personale`, `/watchlist`, `/match-replay`, `/analytics` | sì | contenitori larghi (6) | presente, invariato |
| `/select-sport` | sì | testata larga (7) | presente, invariato |
| `/ladder-popout`, `/`, `/check-email`, `/reset-password`, 404 | no, mai | nessuna | identiche |
