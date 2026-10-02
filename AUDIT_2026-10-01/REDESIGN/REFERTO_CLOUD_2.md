# Referto della sessione cloud 2 — VESTE COMPLETA del redesign (fedele al prototipo, dietro `ui.shell` spento di default)

Mandato: `AUDIT_2026-10-01/REDESIGN/BRIEF_SESSIONE_CLOUD_2_VESTE_COMPLETA.md`. Ramo `redesign/veste-completa` da `master`
(`ebfab2a`). Nessuna fusione, nessun build in produzione, nessun push su `master`.
Letti prima di scrivere codice: brief 2, brief 1 (da `2d8ee70`, il file non è più su master), `REFERTO_CLOUD.md`,
`PIANO_INTEGRAZIONE.md`, `INVENTARIO_FUNZIONALITA.md` + `inventario_parti/*`, prototipo (`index.html`, `js/*.js`).

**Stato: COMPLETATO — tutte le pagine dell'elenco §5 sono vestite, verificate e pushate** (1-13; le pagine fuori
dal guscio — landing, conferma email, reimposta password, 404, Ladder pop-out — restano invariate per costruzione:
vedi righe 9b e 13b). Nessuna fusione su master, nessun build in produzione.

**Passata finale sullo stato definitivo** (`confronto2/strumenti/rigenera_tutto.sh`): tutte le immagini di
`confronto2/` rifatte sul codice finale; prova pixel col guscio spento contro master su 21 schermate × 1280/1600:
`confronto2/off_contro_master_finale.txt` — 26 scatti identici, gli altri 16 diversi SOLO nelle zone dinamiche
già documentate pagina per pagina (pallino REC, età «feed vivo (N s)», strisce animate dei segnali di Safe, dati del
canale finto che arrivano ogni 1,5 s, stella dei preferiti), ognuna verificata con due scatti dello STESSO codice.
Dialoghi e fogli (portali) sopra la cornice: verificati col guscio acceso (foglio parametri di Omega, dialogo
«Svuota Report»).

---

## Come è fatta la veste (metodo, uguale per tutte le pagine)

Tutto lo stile nuovo è in fondo a `frontend/src/index.css`, sezione «VESTE COMPLETA (brief 2», con il vocabolario
in testa (una riga per classe). Ogni selettore è condizionato dal guscio acceso, in una di tre forme:

| forma | uso | perché |
|---|---|---|
| `[data-shell="v2"] .ds-v2-…` | classi di componente aggiunte ai `className` | specificità sopra le utility della pagina |
| `:where([data-shell="v2"]) .<utility>` | **leve globali** (livello 1): `font-mono` → Inter con cifre tabulari; `glass-card` → pannello del prototipo; `text-white/20…/50` → grigio del token `muted-foreground`; `border-white/5…/20` → bordo del token; `bg-black/20…/60` → `--card`; `text-[8px]/[9px]/[9.5px]` → 10 px (minimo per note e fonti) | specificità pari a una utility: le varianti `hover:`/`data-[state]:` delle pagine continuano a vincere; nessuna classe di `components/ui/*` è toccata (guardia) |
| `:where(body:has([data-shell="v2"])) .ds-portale-v2-…` | **solo portali Radix** (fogli parametri, dialoghi): vivono fuori dalla radice del guscio | con guscio spento `body:has(...)` è falso |

Con `ui.shell='off'` nessuna regola della sezione ha effetto (prova pixel sotto). I componenti ricevono **solo
classi in più**: lo verifica `confronto2/strumenti/solo_classi.py` (ogni riga cambiata dei `.tsx` deve differire
da master solo per classi `ds-v2-*`/`ds-portale-v2-*`; unica aggiunta non di classe: la mappa `STATO_V2` di
`PannelloBot.tsx`, che rende come pillola la stessa semantica di `STATO_CLS`).

### Test nuovi (tutti falsificati: difetto rimesso → rosso → ripristino)
- `src/fotografia/uiDefault.test.ts` (brief §7 b): le stringhe letterali (classi di default, varianti cva) di ogni
  file `components/ui/*` contro l'istantanea presa da master alla partenza (`snapshot/ui-default.json`).
- `src/fotografia/cssVeste.test.ts` (brief §7 a, c): ogni selettore della sezione condizionato; la forma dei
  portali solo con classi `.ds-portale-v2-*`; nessun selettore nomina una classe di default di `components/ui/*`;
  ogni `ds-portale-v2-*` usata è definita; **contrasto WCAG** ≥ 4,5:1 (≥ 3:1 se grande) per ogni regola con colore
  di testo, sul fondo dichiarato o sul peggiore dei fondi del prototipo (`background`, `card`, `muted`, `glass`);
  nessun carattere sotto 10 px. (La guardia di prima, `cssGuscio.test.ts`, resta e copre le classi `ds-v2-*`.)

```
uiDefault: card.tsx "rounded-xl …" -> "rounded-2xl …"
  → components/ui/card.tsx: classi di default cambiate            Tests 1 failed | 1 passed
cssVeste: regola .ds-v2-scheda senza [data-shell]
  → selettori che varrebbero anche con ui.shell=off: [ '.ds-v2-scheda' ]   Tests 1 failed | 7 passed
cssVeste: :where(body:has(...)) .ds-v2-scheda (portale con classe non portale)      → 1 failed | 7 passed
cssVeste: :where([data-shell="v2"]) .rounded-md (classe di ui/*)                    → 1 failed | 7 passed
cssVeste: color: hsl(var(--muted-foreground) / 0.5) (contrasto)                     → 1 failed | 7 passed
cssVeste: font-size: 9px                                                             → 1 failed | 7 passed
cssGuscio (già esistente) ha preso un mio refuso: classe ds-v2-cr-impianto-stop usata e non definita → corretto
```

### Anteprima popolata (solo screenshot, mai l'app)
- `frontend/src/anteprima/*Finto.ts`: moduli finti con le STESSE chiavi e tipi del vero (`export *` dal modulo
  vero + override dell'hook), costruiti con le funzioni vere come i test di pagina. Non importati dall'app:
  li usa solo `confronto2/strumenti/server.mjs` con alias Vite esatti. La fotografia (`src/fotografia`) non li
  usa e resta quella di prima.
- Strumenti in `confronto2/strumenti/`: `server.mjs` (porta 5198, `PORTA=` per cambiarla), `scatta.mjs`,
  `interagisci.mjs` (scatto dopo clic: linguette, fogli), `scatta_prototipo.mjs`, `affianca.py`,
  `consegna_pagina.sh` (immagini di consegna), `prova_off_master.sh` + `confronta_png.py` (prova pixel col guscio
  spento contro master), `solo_classi.py`.

---

## Numeri

| | tsc | suite intera | fotografia | build `dist/assets` |
|---|---|---|---|---|
| partenza (`ebfab2a`) | 0 | 314 file / 4829 test verdi (10/50 saltati) | 26/26 | 3.495.574 B |
| pagina 1 Control Room | 0 | 316 / 4839 verdi (+2 file, +10 test), 10/50 saltati | 26/26 identica, nessuna fotografia rigenerata | 3.511.199 B (+0,45 %) |
| pagina 2 Programma del giorno | 0 | 316 / 4839 verdi | 26/26 identica | 3.512.809 B (+0,49 %) |
| pagina 13a Scelta sport | 0 | 316 / 4839 verdi | 26/26 identica | 3.513.770 B (+0,52 %) |
| pagina 3 Segui live + terminal calcio | 0 | 316 / 4839 verdi | 26/26 identica | 3.514.871 B (+0,55 %) |
| pagine 4-6 Mike, Safe Strategy, Omega | 0 | 316 / 4839 verdi | 26/26 identica | 3.517.604 B (+0,63 %) |
| pagine 7-8 Tennis Terminal, Dashboard tennis | 0 | 316 / 4839 verdi | 26/26 identica | 3.518.664 B (+0,66 %) |
| pagine 9-10 Multi-ladder, Ladder pop-out, Market watch, Live P&L (+ Trade journal) | 0 | 316 / 4839 verdi | 26/26 identica | 3.519.789 B (+0,69 %) |
| pagine 11-12 Storici, Report, Watchlist, Match replay, Analytics, Cruscotto | 0 | 316 / 4839 verdi | 26/26 identica | 3.522.982 B (+0,78 %) |

Fotografie `off` e `v2` delle pagine: **mai rigenerate** (le classi non entrano nella fotografia; testi, testid,
comandi, chiamate e WebSocket restano identici, anche col guscio acceso). Nessun test esistente modificato.

---

## Pagine

| # | pagina | componenti ritoccati | stato | classi principali | immagini |
|---|---|---|---|---|---|
| 1 | Control Room `/control-room` | `ControlRoom.tsx` (testata, chip dei bot, feed, linguette del banco), `testata/FasciaSoldiVeri`, `testata/TesseraRunner`, `testata/FasciaStop`, `MarchioSoldi`, `ObiettivoHero` (composizione a 2 colonne, corsia PROVA in tabella tratteggiata), `PannelloBot` (pillole di stato e modalità, bottoni piccoli, conferme armate), `RigaOrdiniReali`, `RigaFreno`, `RigaCapacitaMercati`, `InterruttoreUscite`, `QuoteMercato` (BACK sky / LAY rose in caselle), `SchedaChiusura`, `SchedaChiusuraOmega`, `SchedaPropostaOpportunita` (tessere 2×2, azioni arrotondate, armato rosso pieno), `PosizioniChiuse` (pillole dei filtri), `trading/PageShell` (`flow-root`), `trading/ParamsSheetBase` (foglio parametri) | **fatto** | `ds-v2-cr-*`, `ds-v2-chip--*`, `ds-v2-marchio`, `ds-v2-pulsante--*`, `ds-v2-quota--*`, `ds-v2-pillola`, `ds-v2-tab`, `ds-portale-v2-foglio` + leve globali | `confronto2/control-room.{off,v2}.{1280,1600}.png`, `confronto2/control-room.affianco.png` |

| 2 | Programma del giorno `/board` | `Board.tsx`: linguette come testa di un unico pannello con le righe, orario a colonna fissa, IN-PLAY come pillola, quote BACK/LAY in caselle 46×30 (prototipo `.o`), bottoni piccoli, titolo Sora, contenitore largo; stato vuoto/canale off con `ds-v2-vuoto` | **fatto** | `ds-v2-board-*`, `ds-v2-quota--*`, `ds-v2-pulsante--*`, `ds-v2-titolo` | `confronto2/board.{off,v2}.{1280,1600}.png`, `confronto2/board.affianco.png` (tabellone finto sul canale locale: `CANALE_FINTO=1`, partite del prototipo, `strumenti/canaleFinto.mjs`) |

| 3 | Segui live `/segui-live` e terminal calcio (`/segui-live?event=…`) | `LiveMatchCard` (punteggio grande al centro, pillole), `LadderView` (righe del ladder 19 px invece di 12,5 px, cifre 11,5 px, intestazione 10 px: SOLO tipografia e spaziatura interna), `LiveTradingPanel` (campi 30 px su due colonne); il resto (top bar, banner rischio gol, tab mercati, toolbar, rail posizioni/ordini, segnali, tabellone) prende la veste dalle leve globali e dalla Control Room | **fatto** | `ds-v2-lm-*`, `ds-v2-ladder-riga/testa`, `ds-v2-lt-griglia`, `ds-v2-campo` | `confronto2/segui-live.{off,v2}.{1280,1600}.png`, `confronto2/segui-live-terminal.{off,v2}.{1280,1600}.png`, `confronto2/segui-live.affianco.png`, `confronto2/segui-live-terminal.affianco.png` |
| 4 | Mike `/mike` | `trading/BotHeader` (testata del bot come pannello, nome Sora 20, stato a pillola con i colori di `botStatusMeta`, comandi a destra), `trading/StatTile` (KPI su 4 colonne, valore Sora 20), `Mike.tsx` (linguette sottolineate), `MikeMatchCard` (tessere del modello con cifre 18 px, quote BACK/LAY in caselle); Operazioni, Risultati, Attività e Storico prendono la veste dai componenti condivisi | **fatto** | `ds-v2-botheader*`, `ds-v2-forma-pillola`, `ds-v2-kpi-griglia`, `ds-v2-schede`, `ds-v2-mike-*` | `confronto2/mike.*` |
| 5 | Safe Strategy `/safe-strategy` (calcio e tennis) | `SafeStrategy.tsx` (linguette principali sottolineate, sotto-linguette a segmento), `safestrategy/ParamsSheet` (foglio parametri del portale); Strategie di Safe = `PannelloBot` della Control Room; BotHeader e KPI condivisi | **fatto** | `ds-v2-schede`, `ds-v2-segmento`, `ds-portale-v2-foglio` | `confronto2/safe-strategy.*` |
| 6 | Omega `/omega` | `Omega.tsx` (linguette); BotHeader, KPI, giornata, equity e fogli parametri condivisi | **fatto** | `ds-v2-schede` | `confronto2/omega.*` |
| 7 | Tennis Terminal `/tennis/terminal?event=…` | `TennisTerminal.tsx`: barra della partita come pannello, giocatori Sora 16, stato ordini / SEGUITA / REC come pillole; ladder tennis, bot tennis (Pro, Scalper, FLB, Swing) e Stats/Chart/Depth dai componenti già vestiti | **fatto** | `ds-v2-tt-*`, `ds-v2-chip--*`, `ds-v2-forma-pillola` | `confronto2/tennis-terminal-sinner.*` |
| 8 | Dashboard tennis `/tennis` | `TennisMatchesList`: contenitore largo, titolo Sora 24, righe partita compatte, ora a pillola, «APRI TERMINAL» piccolo | **fatto** | `ds-v2-tn-*`, `ds-v2-titolo`, `ds-v2-pulsante--sm` | `confronto2/tennis.*` |
| 9 | Multi-ladder `/multi-ladder` | barra di pagina e contenitore (`MultiLadder.tsx`); i ladder sono `LadderView` già vestiti (pagina 3) | **fatto** | `ds-v2-barra` | `confronto2/multi-ladder.*` |
| 9b | Ladder pop-out `/ladder-popout` | nessuno | **lasciata invariata (motivo)**: è FUORI dal guscio in entrambi gli stati (brief 1 e 2: finestra senza navigazione), quindi non ha `data-shell="v2"` sopra di sé e nessuna regola della veste la tocca; il ladder dentro è lo stesso `LadderView`. Leggibile a 640×780 come oggi. Per vestirla servirebbe un contenitore `data-shell` attorno alla sola rotta del pop-out in `App.tsx`: non fatto | — | — |
| 10 | Market watch `/market-watch`, Live P&L `/live-pnl` | `MarketWatch.tsx` (righe più ariose, sezioni, pillole di stato), `LivePnl.tsx` (tessere KPI come il resto dell'app, intestazioni di tabella maiuscole); barra e contenitore condivisi | **fatto** | `ds-v2-barra`, `ds-v2-contenitore`, `ds-v2-mw-*`, `ds-v2-kpi*`, `ds-v2-testa-tabella` | `confronto2/market-watch.*`, `confronto2/live-pnl.*` |
| 12a | Trade journal `/trade-journal` (anticipata: stessa barra e stesse tabelle della pagina 10) | `TradeJournal.tsx`: barra, contenitore, intestazione di tabella | **fatto** | `ds-v2-barra`, `ds-v2-contenitore`, `ds-v2-testa-tabella` | `confronto2/trade-journal.*` |
| 11 | Storico calcio `/storico/calcio`, Storico tennis `/storico/tennis` | `StoricoSport.tsx`: testata come pannello (stessa classe del BotHeader), titolo 18 px, filtri a pillole; KPI 5 per riga, tabelle, equity, barre e calendario dai componenti condivisi | **fatto** | `ds-v2-botheader*`, `ds-v2-st-titolo`, `ds-v2-pillola`, `ds-v2-kpi-griglia` | `confronto2/storico-calcio.*`, `confronto2/storico-tennis.*` |
| 12 | Report personale, Watchlist, Match replay, Analytics, Cruscotto partite (`/dashboard`) (Trade journal: vedi 12a) | barra di navigazione delle pagine di oggi compattata (8 pagine, 48 px, anche Board, Segui live, Scelta sport); titoli di scheda come il prototipo; campi 30 px nei moduli (14 file: filtri, order entry, dutching, regole di rischio, schede trade); `ReportPersonale` (KPI e metriche), `Watchlist` (linguette sottolineate, contenitore largo), `MatchReplay` (registrazioni su due colonne), `Analytics` (linguette-bottone sottolineate), `MatchesList` (righe compatte, loghi 20 px, «ANALIZZA» piccolo), gruppi per campionato/torneo compatti | **fatto** | `ds-v2-navbar*`, `ds-v2-scheda-titolo`, `ds-v2-campo`, `ds-v2-schede*`, `ds-v2-tab-bottone*`, `ds-v2-mr-*`, `ds-v2-gruppo*`, `ds-v2-cp-logo`, `ds-v2-rp-metrica` | `confronto2/{report-personale,watchlist,match-replay,analytics,dashboard}.*` |
| 13a | Scelta sport `/select-sport` (fatta prima delle pagine 3-12 mentre i finti di quelle si preparavano: non ha bisogno di dati) | `SelectSport.tsx`: titolo a sinistra Sora 24, 5 carte compatte (padding 18, icona 56, titolo 17 in `foreground`, «Entra» col colore della carta), contenitore largo | **fatto** | `ds-v2-ss-*`, `ds-v2-titolo` | `confronto2/select-sport.{off,v2}.{1280,1600}.png`, `confronto2/select-sport.affianco.png` |
| 13b | Accesso (landing), Conferma email, Reimposta password, 404 | nessuno | **lasciate invariate (motivo)**: sono FUORI dal guscio in entrambi gli stati (brief 1 e 2) e non hanno `data-shell="v2"` sopra di sé; il prototipo `#landing` riproduce la landing di oggi (stessi blocchi e stessa veste). Per vestirle servirebbe un contenitore `data-shell` attorno alle rotte pubbliche in `App.tsx`: non necessario e non fatto, il flusso di login resta intatto | — | — |

### Pagina 2 — Programma del giorno: verifiche
- Prova pixel col guscio spento contro master con tabellone finto, 1280 e 1600, pagina intera: **identiche**.
- Stato «canale off» verificato a vista col guscio acceso (pannello tratteggiato sotto le linguette).
- Non fatto (come nel referto 1): conteggio nelle linguette e riga d'intestazione della tabella del prototipo:
  sarebbero testi nuovi.

### Pagina 3 — Segui live e ladder: verifiche (brief §6, massima prudenza)
- **Aree cliccabili del ladder** (`confronto2/strumenti/misura_ladder.mjs`, Chromium, terminal Inter–Torino, 322
  celle-bottone delle prime righe dei due ladder; guscio spento a 1356 px = larghezza del contenuto del guscio a
  1600 px, così le colonne sono le stesse): **0 celle più piccole in v2**; larghezza invariata (scarto minimo
  0 px: le colonne hanno larghezze fisse in px nel codice), altezza +6,5 px (12,5 → 19 px). Falsificazione: con le
  celle forzate a 8 px di altezza → `piuPiccoleInV2: 322`, scarto −4,5 px → ripristino. Struttura del DOM, ordine
  delle colonne (LAY a sinistra del prezzo, BACK a destra), drag e scroll non toccati; la centratura del ladder
  misura le righe dal DOM (`offsetTop`/`clientHeight`), quindi regge l'altezza nuova. `LadderView.test.tsx`,
  `GridView.test.tsx`, `StandaloneLadder.test.tsx` verdi senza modifiche (suite intera).
- A 1280 px nessuno scroll orizzontale nel terminal (misura di `scatta.mjs`).
- Prova pixel col guscio spento contro master (lista e terminal, 1280 e 1600): differenze solo nelle zone che
  cambiano anche fra due scatti dello STESSO codice (dati del canale finto che arrivano ogni 1,5 s, icone
  animate): stesse zone e stesso ordine di grandezza in `off_ramo` contro `off_ramo2`.
- Il terminal mostra meno righe di ladder per volta nella stessa finestra di 420 px (circa 21 invece di 32):
  conseguenza della riga più alta del prototipo. Da valutare con l'utente.

### Pagine 4-6 — bot calcio: verifiche
- Prova pixel col guscio spento contro master (1280 e 1600, pagina intera): differenze solo nelle zone che cambiano
  anche fra due scatti dello STESSO codice (età «feed vivo (N s)» nella testata del bot, strisce animate delle schede
  segnale di Safe, un pallino animato di Omega).
- Strumenti: i due server di anteprima (master e ramo) condividevano la cache delle dipendenze di Vite e si
  invalidavano a vicenda (pagina bianca, «504 Outdated Optimize Dep»): ora ogni porta ha la sua cache e la prova fa
  un giro di riscaldamento.

### Pagine 7-8 — tennis: verifiche
- Ladder tennis (`misura_ladder.mjs` sul terminal Sinner–Draper): 264 celle-bottone, **0 più piccole**, larghezza
  invariata, altezza +6,5 px.
- Prova pixel col guscio spento contro master: differenze di 130-180 pixel in zone animate (pallino REC, stella dei
  preferiti), uguali fra due scatti dello STESSO codice.
- Correzione di sola grafica: la pillola «PAPER · SIMULATO» del terminal era ambra piena; col guscio acceso è il
  verde unico di PAPER (brief §3.8).

### Pagine 9-10 (+ Trade journal): verifiche
- Prova pixel col guscio spento contro master (Multi-ladder, Ladder pop-out, Market watch, Live P&L, Trade journal;
  1280 e 1600, pagina intera, canale finto acceso): **tutte identiche**.

### Pagine 11-12: verifiche
- Prova pixel col guscio spento contro master (Storico calcio e tennis, Report, Watchlist, Match replay, Analytics,
  Cruscotto, e di nuovo Dashboard tennis; 1280 e 1600, pagina intera): **identiche**, salvo la stella animata della
  Dashboard tennis (già vista alla pagina 8, uguale fra due scatti dello stesso codice).
- Errore mio trovato e corretto prima del commit: aggiungendo `ds-v2-campo` a stringhe di classi concatenate con `+`
  avevo tolto lo spazio finale e incollato la classe alla successiva (`ds-v2-campofocus:outline-none`). Con il guscio
  spento era inerte, ma toglieva la classe di focus anche con `off`: trovato rileggendo il diff, corretto in 10 file
  (`ds-v2-campo ' +`), verificato da `solo_classi.py` e dalla prova pixel.
- Il Cruscotto si vede popolato solo dopo il clic su «Match Betfair» (la vista iniziale legge
  `from('fixture_predictions')` dentro la pagina e il finto del client risponde vuoto); i loghi delle squadre sono
  immagini esterne bloccate nell'anteprima.

### Pagina 13a — Scelta sport: verifiche
- Prova pixel col guscio spento contro master: identiche salvo poche decine di pixel dell'animazione d'ingresso delle
  carte (`framer-motion`), che differiscono allo stesso modo fra due scatti dello stesso codice (già nel referto 1).
- Nota sugli strumenti: con l'orologio fisso di Playwright (`ORA_FISSA`) le animazioni d'ingresso non partono e la
  pagina resta trasparente: per Scelta sport le immagini sono scattate con `ORA_FISSA=0`.

### Pagina 1 — Control Room: dettagli e verifiche
- Testata: col guscio acceso è un pannello dentro i margini (prototipo `header.panel.flat`), velo arancio se un bot
  è in LIVE (colori della pagina); soldi veri in un riquadro tenue; 8 chip dei bot in tessere a griglia (bordo rosso
  per il LIVE); stop di perdita compatto con le modalità come pillole. Ordine del DOM invariato.
- Marchio della fonte uguale al prototipo: CONTO rosso, BOT sky, PROVA verde, STIMA ambra (`data-fonte`, il testo
  resta quello di produzione, es. «CONTO BETFAIR · 3 s fa»).
- Conferme armate (`confermi? sono soldi veri`, `Confermo: soldi veri`, ordini reali LIVE): rosso pieno con
  alone, più vistose di oggi. `Confermo: soldi veri` di Uscite/Opportunità era arancio pieno: ora rosso pieno
  (correzione di sola grafica, elencata sotto).
- Foglio parametri (portale): sopra la cornice (verificato aprendo «Parametri» di Omega), campi 30 px.
- Linguette del banco, schede Pre-match / Live / Posizioni aperte / Posizioni chiuse verificate con clic veri
  (`interagisci.mjs`), nessun errore JS.
- Prova pixel col guscio spento contro master (stessa anteprima popolata, pagina intera, 1280 e 1600):
  identiche salvo un riquadro 16×16 px (il pallino animato di REC), che differisce allo stesso modo fra due scatti
  dello STESSO codice (`confronta_png.py off_ramo off_ramo2` → stesso riquadro) → animazione, non veste.
- Conteggio WebSocket costruiti dalla pagina, guscio spento e acceso: invariato (fotografia, asserzione 0).

---

## Correzioni di sola grafica fatte (ammesse dal brief, solo col guscio acceso)
1. Marchio della fonte con i colori del prototipo in tutte le pagine (CONTO/BOT/PROVA/STIMA).
3. Tennis Terminal: pillola «PAPER · SIMULATO» da ambra al verde unico di PAPER.
2. Bottone armato `Confermo: soldi veri` (Uscite, Opportunità): da arancio pieno a rosso pieno, come le altre
   conferme dei soldi veri (brief §4: «lo stato ARMATO … rosso pieno»).

## Bug e incongruenze trovati (NON corretti)
1. `components/controlroom/PannelloBot.tsx:668-672`: sulla prima riga di Safe («Safe base») compaiono DUE bottoni
   con lo stesso nome «Parametri» (foglio della strategia `parametriRiga` + foglio del bot `parametri`, perché
   `primaDelBot`). È voluto dal codice, ma a schermo i due bottoni sono indistinguibili per nome accessibile e
   testo. Presente uguale col guscio spento. Non toccato (testo).
2. `components/live/ScalperPanel.tsx`: il mojibake è nei TESTI A SCHERMO, non solo nei commenti (24 sequenze;
   visibili nel pannello Scalper del terminal: «pre-match Â· stop automatico al KO», «â€" cicli 5»,
   «â‚¬0.71»). Il brief ammette la correzione solo nei commenti: non corretto, da correggere dal coordinatore.
3. Ereditati dal referto 1 e ancora veri: `npm ci` richiede `--legacy-peer-deps`; testate `sticky` di pagina che
   oggi non restano incollate; `MarketWatch.test.tsx` fragile sotto carico.

## Cosa non ho potuto verificare
- L'exe Electron vero col backend vivo; i font Sora/Inter veri (rete esterna bloccata nelle anteprime: si vede il
  font di ripiego, sia nel prototipo sia nell'app).
- Le schede popolate nella fotografia (la fotografia fissa lo stato «backend vuoto»: gli stati popolati sono
  coperti dai test esistenti e, per la veste, dalle anteprime popolate).
