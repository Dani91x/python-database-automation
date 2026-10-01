# Piano di integrazione del redesign (01/10/2026)

Stato: **proposta**. Nessun file del progetto è stato toccato. Il prototipo (`prototipo/`, pubblicato come
artefatto) è una pagina HTML a sé con dati finti: serve a decidere. Questo documento dice come portarlo nell'app
senza rompere né far regredire nulla. Ogni passo si spegne con un interruttore e si verifica con gli strumenti che
il progetto usa già (vitest, `tsc -p tsconfig.app.json --noEmit`, `npm run build`, controllo visivo dell'exe).

Principi, nell'ordine in cui contano:

1. **Zero cambi al backend.** Nessuna RPC nuova, nessuna tabella nuova, nessuna migrazione, nessun canale locale
   nuovo. La sidebar e la testata globale leggono solo dati che le pagine già leggono (tabella in fondo, §E).
2. **Zero cambi di logica nelle pagine.** Hook, chiamate, testi, `data-testid`, ordine dei blocchi restano. Il
   redesign cambia classi CSS, contenitori e spaziature.
3. **Nessuna funzionalità nuova.** La sidebar porta a rotte che esistono; la testata globale mostra stati che
   la Control Room e le pagine bot già mostrano. Niente command palette (pattern 8 della ricerca, scartato:
   sarebbe una funzione nuova).
4. **Reversibile a ogni passo** con una variabile d'ambiente e una chiave locale.

---

## A. Il guscio (sidebar + testata) avvolge le rotte esistenti

Oggi `App.tsx` elenca le rotte una per una, ognuna dentro `<ProtectedRoute>`, e ogni pagina disegna la propria
testata (7 stili diversi, inventario E §3.1). Il guscio si inserisce come **layout route** di React Router v6, senza
toccare le pagine:

```tsx
// App.tsx (unico punto toccato in questa fase)
<Route element={<ProtectedRoute><AppShell /></ProtectedRoute>}>   // AppShell rende <Outlet/>
  <Route path="/board" element={<Board />} />
  <Route path="/control-room" element={<ControlRoom />} />
  … tutte le rotte protette di oggi, invariate …
</Route>
<Route path="/ladder-popout" element={<ProtectedRoute><LadderPopout /></ProtectedRoute>} />  // FUORI dal guscio
<Route path="/" element={<LandingPage />} />  … pubbliche FUORI dal guscio
```

- **`AppShell`** (file nuovo, `components/shell/AppShell.tsx`): griglia `sidebar | contenuto`. La sidebar ha i
  gruppi del prototipo: Programma del giorno, Control Room, Calcio (Cruscotto partite, Omega, Safe Strategy,
  Mike, Segui live · Scalper, Storico calcio), Tennis (Dashboard tennis, Tennis Terminal, Bot tennis → Terminal,
  Safe Strategy · Tennis → `/safe-strategy` tab tennis, Storico tennis), Trading (Multi-ladder, Market watch,
  Live P&L, Watchlist), Analisi (Match replay, Analytics, Report personale, Trade journal), Account (Scelta sport,
  Esci). Il filtro Tutti/Calcio/Tennis della sidebar nasconde solo voci di menu: nessun dato cambia.
- **Il contenuto scorre in un suo contenitore** (`overflow-y:auto` sotto la testata globale alta 56 px): così le
  testate `sticky top-0` delle pagine (23 nel codice) restano attaccate al bordo alto del contenitore e non vanno
  sotto la testata globale. Le pagine non si toccano.
- **Fuori dal guscio**: `/ladder-popout` (finestra 560×860 senza navigazione, come oggi), landing, check-email,
  reset-password, 404.
- **Le testate di oggi** restano nel DOM. In fase 1 convivono (doppio brand, accettabile per una settimana di
  prova). In fase 2 i soli pezzi di navigazione doppi (link «AI TERMINAL», bottoni «‹ Dashboard», «Cambia sport»,
  «Watchlist», «Report», «Analytics» delle navbar inline e di `TennisNav`) prendono l'attributo
  `data-nav-legacy`; il guscio li nasconde con `[data-shell="v2"] [data-nav-legacy]{display:none}`. **I comandi
  non si nascondono mai**: in `BotHeader` resta tutto (stato, salute, Storico, PAPER/LIVE, Parametri, Avvia/Ferma);
  in Control Room la `Testata` resta intera perché è contenuto, non navigazione. jsdom non applica i fogli di stile,
  quindi gli elementi nascosti restano trovabili dai test.

### Testata globale (sola lettura)

Tre indicatori, tutti da fonti già lette altrove, nessun comando:

| Indicatore | Fonte già esistente | Comportamento se la fonte manca |
|---|---|---|
| Runner ⚽ / 🎾 + «Canali n/8» con elenco 47331-47338 | `useLocalStatus(sport)` di `lib/localTransport.ts` (lo usa già il Board) | pallino grigio + «spento»; mai verde finto |
| «Ordini: n LIVE · m PROVA» con elenco per bot | stato dei bot già letto da `useControlRoom` / `statoBotCanale` (`*_stato` 47333-47338) | «modalità non letta» ambra, come il `ModeBanner` della Control Room (fail-closed) |
| Saldo CONTO + esposizione + occhio | `SaldoBetfairCard` (topic `account` + `betfair_live_account`), stessa preferenza `cr-saldo-nascosto` | «—» + «saldo non letto» |

La modalità PAPER/LIVE **non si cambia dalla testata**: si cambia solo dentro ogni bot con `ModeToggle` +
`LiveConfirmDialog`, come oggi. Per non moltiplicare letture e connessioni, la testata legge da un provider unico
montato una sola volta nel guscio (stesso schema di `SafeStrategyProvider`), riusando gli hook esistenti; nessun
socket in più rispetto a quelli che l'app apre già.

Prima schermata: l'exe apre già `/board` (`desktop/main.js`). Nel guscio `/board` diventa la prima voce della
sidebar, quindi raggiungibile da ogni pagina (oggi nessun link ci porta, E §1.1). Il redirect dopo il login resta
`/select-sport` finché l'utente non decide altrimenti: cambiarlo è una decisione sua.

---

## B. Token e componenti: cosa si ritocca e cosa no

**I token non cambiano.** `tailwind.config.js` e `:root` di `index.css` restano identici (tavola in
`INVENTARIO_FUNZIONALITA.md`). Il prototipo usa gli stessi valori HSL e gli stessi font Sora/Inter.

Si **aggiungono** in `index.css`, dentro `@layer components`, poche classi nuove con prefisso, senza ridefinire
quelle esistenti:

| Classe nuova | Sostituisce visivamente | Note |
|---|---|---|
| `.ds-panel` | `glass-card` dove serve meno vetro | `glass-card` resta per chi la usa |
| `.ds-kpi`, `.ds-chip`, `.ds-mk` (marchio fonte) | tile e pillole sparse | colori dai token e da `sky/rose/emerald/amber/orange/teal` già in uso |
| `.ds-strip-live / -paper / -warn` | banner modalità | rosso = soldi veri, verde = prova (un solo verde per PAPER) |
| `.ds-tabular` | `font-mono tabular-nums` sulle cifre | Inter con `tabular-nums` al posto del monospace di sistema |

**Componenti `ui/*` (shadcn)**

| Si ritoccano (solo classi di default) | Perché |
|---|---|
| `tabs.tsx` | linguetta con sottolineatura primary, come nel prototipo |
| `card.tsx` | bordo `--border`, raggio `--radius`, ombra più leggera |
| `badge.tsx` | altezza 20 px, maiuscolo spaziato |
| `button.tsx` | varianti invariate; altezze 24/30 px nelle aree dense tramite `size` già esistente |
| `sheet.tsx` | larghezza 440 px per i fogli parametri |

| NON si toccano | Perché |
|---|---|
| `dialog.tsx`, `form.tsx`, `input.tsx`, `label.tsx`, `checkbox.tsx`, `accordion.tsx`, `tooltip.tsx`, `sonner.tsx`, `progress.tsx`, `skeleton.tsx` | comportamento e accessibilità (focus, `aria-*`) usati dai test e dalle conferme LIVE |

**Componenti di dominio**: `components/trading/*` (BotHeader, ModeBanner, DayBar, StatTile, KpiRow,
DailyCalendar, EquityCard, PerformancePanel, EventPnlTable, ParamsSheetBase, ActivityFeed, StatoOrdine, ExitBadge)
cambiano solo le stringhe `className`. Restano sotto `designGuard.test.ts`: nessun `toFixed` su denaro, nessun
stato in inglese, `rose` per il LAY, P&L con `pnlClass` e segno. Due incoerenze trovate nell'inventario si
correggono **solo se l'utente lo approva**: `pink` → `rose` nelle tre schede della Control Room (A §5.2) e il colore
unico di PAPER nei pannelli live (C §12).

---

## C. Control Room: solo classi e contenitori

Vincolo dell'utente: **resta esattamente così, solo variante di design.** Il prototipo ha gli stessi blocchi nello
stesso ordine (`A_CONTROL_ROOM.md` §0). In produzione:

- nessun cambio a `useControlRoom.ts`, `useTennisVivo`, `useSeguiOrdini`, `usePrezzoAlMs`, `useChiusuraAlMs`,
  `useCashOutPartita`, alle librerie `lib/controlRoom*.ts` e alle conferme a due tempi (400 ms, 10 s);
- nessun testo cambiato (i test cercano `getByText` su `Nessuna uscita da decidere`, `vivo, in attesa`,
  `in streaming`, `mai avviato`, `ACCESO MA MUTO`, `RIPIEGO REST (stream fermo)`, `1 partita con posizione LIVE`,
  `Omega oggi non ha ancora girato…`, `'punta'`, `'banca'`, `'SCATTATO'`, `'assente'` e altri: A §4);
- nessun `data-testid` rinominato o spostato fuori dal suo blocco. Da preservare in blocco: `cr-testata`,
  `cr-soldi-veri`, `cr-freni`, `cr-runner*`, `cr-bots`, `cr-bot-*`, `cr-feed*`, `cr-banner-modalita`,
  `cr-obiettivo*`, `cr-giornata*`, `day-bar-*`, `cr-composizione*`, `cr-prova-*`, `cr-saldo*`, `cr-riga-storico`,
  `cr-split-sport`, `cr-sport-*`, `cr-filtro-*`, `cr-pannello-bot*`, `cr-ferma-tutti`, `cr-ordini-reali*`,
  `cr-freno*`, `cr-capacita*`, `cr-proposte-flusso*`, `cr-tab-*`, `cr-elenco-*`, `cr-partita`, `cr-pre-match`,
  `cr-op-*`, `cr-mike*`, `cr-cashout-*`, `cr-chiuse*`, `cr-chiusa*`, `cr-nastro*`, `cr-proposta*`,
  `cr-omega-*`, `cr-opportunita*`, `cr-opp-*`, `cr-catena*`, `page-footer` (elenco completo A §4.1);
- `cr-riga-paper` deve restare **assente** (un test lo verifica);
- le due colonne di decisione restano sempre visibili; sotto 1360 px si impilano accanto alle tab invece che sotto
  (nel codice oggi `xl:contents`): è un cambio di sola griglia;
- la `Testata` sticky resta `sticky top-0` dentro il contenitore che scorre (§A), quindi non cambia posizione nel DOM.

Test interessati: `pages/ControlRoom.test.tsx` (137 casi) + 73 file in `components/controlroom/**`. Usano quasi solo
`getByTestId`; nessuno usa `toBeVisible` (verificato: 0 file in `src` lo usano), quindi spostare classi non li tocca.

---

## D. Ordine di adozione a fasi, ognuna reversibile

Interruttore unico: `VITE_UI_SHELL` (`off` | `v2`, default `off`) letto al build, più una chiave locale
`ui.shell` = `v2|off` per provarlo sull'exe senza ricompilare la UI (la chiave vince se presente). Con `off` l'app
è identica a oggi, byte per byte nelle pagine.

| Fase | Contenuto | File toccati | Come si torna indietro |
|---|---|---|---|
| 0 | classi `.ds-*` in `index.css` (nessuno le usa ancora) | `index.css` | rimuovere il blocco |
| 1 | `AppShell` + layout route + testata globale in sola lettura | `App.tsx`, `components/shell/*` (nuovi) | `ui.shell=off` |
| 2 | `data-nav-legacy` sui link di navigazione doppi | 7 testate: Board, Dashboard, Analytics, Watchlist, ReportPersonale, SeguiLive, MatchReplay, `TennisNav`, top bar di MarketWatch/LivePnl/TradeJournal/MultiLadder, brand di `BotHeader` | attributo innocuo con `off` |
| 3 | Programma del giorno (`Board.tsx`): righe in tabella densa, tab con conteggio | solo `className` di `Board.tsx` | ripristino file |
| 4 | Control Room: classi e griglie (§C) | `ControlRoom.tsx` e `components/controlroom/*` solo `className` | ripristino file; i test non cambiano |
| 5 | pagine bot (Omega, Safe, Mike) e `components/trading/*` | solo `className` | ripristino file |
| 6 | tennis (`TennisMatchesList`, `TennisTerminal`, `TennisBotPanel`) e live (`SeguiLive`, `LadderView`, pannelli) | solo `className` | ripristino file |
| 7 | storici, report, journal, watchlist, replay, analytics, dashboard | solo `className` | ripristino file |

Ogni fase è un commit a sé con percorsi espliciti (mai `git add -A`), verificata da chi non l'ha scritta.

---

## E. Backend: nessun cambio. Cosa alimenta ogni schermata

| Schermata | RPC / tabelle / canali già esistenti |
|---|---|
| Testata globale | `useLocalStatus` (47331-47338), push `*_stato`, topic `account`, `betfair_live_account` |
| Programma del giorno | canali 47331/47332 topic `board`; RPC `tennis_follow_event` |
| Control Room | `useControlRoom` (`safe_strategy_scan/status`, `get_omega_state/trades/events/proposte/missions`, `get_safe_state/daily`, `get_mike_state`, `get_tennis_follows`, `get_live_follows`, `get_tennis_bot_services/daily/orders_today`, `get_scalper_control_room`, `get_live_orders_account_open`, `betfair_live_account`, `betfair_live_risk_state`, `betfair_live_heartbeat`, `get_live_settings`, `get_posizioni_chiuse_giornata`), canali 47331-47338 |
| Omega | `get_omega_state`, `get_omega_trades`, `omega_activate/stop/update_params/request`, missioni, `get_scalper_state`, `get_omega_daily/day_trades`, canale 47334 |
| Safe Strategy | `get_safe_state/trades/activity/aggregates`, `safe_activate/stop/update_params/request/request_approve`, `safe_strategy_opportunities`, scanner, `get_safe_daily/day_trades`, canale 47335 |
| Mike | `get_mike_state`, `get_mike_trades`, `mike_activate/stop/update_params/request`, `get_mike_daily/day_trades`, canale 47333 |
| Segui live (+ scalper) | `get_live_follows`, `live_now`, `live_ladder`, `live_signals`, `live_alerts`, `get_live_orders/positions/positions_event`, `request_betfair_live_order`, `get_live_risk_rules`, `request_live_risk_rule`, `get_live_xhedge`, `get_live_settings`, `set_live_kill_switch`, `get_live_audit`, `get_scalper_state`, `scalper_activate/stop`, canale 47331 |
| Tennis / Terminal | `get_tennis_fixtures`, `tennis_markets`, `tennis_live_now`, `tennis_live_ladder`, `get_tennis_follows`, `tennis_follow_event`, `tennis_set_follow_record`, `get_tennis_bots_state`, `tennis_bot_arm/disarm`, `request_tennis_live_order`, `get_tennis_live_orders/positions`, canali 47332/47337 |
| Multi-ladder, Ladder pop-out | `get_live_follows`, `live_now`, `tennis_live_now`, ladder 47331/47332 |
| Market watch | `get_live_follows`, `get_live_positions_event`, `get_tennis_follows`, `get_tennis_live_positions_all`, comando `cashout_event` |
| Live P&L | `get_live_settled`, `betfair_live_risk_state`, `get_live_positions_all`, `get_tennis_live_positions_all` |
| Storico calcio / tennis | `get_omega_daily`, `get_safe_daily`, `get_mike_daily`, `get_storico_stake`, `get_*_day_trades` |
| Trade journal | `get_live_journal`, `get_live_settled`, `set_live_journal_note` |
| Report personale | `get_personal_report`, `get_personal_trades`, `get_cash_movements`, `settle_personal_trade`, `add_personal_trade`, `reset_personal_report`, `get_betfair_fixtures` |
| Watchlist | `get_watchlist`, `set_watchlist_decision`, `set_watchlist_follow_live`, `delete_from_watchlist`, `request_betfair_order`, `get_betfair_orders`, `request_betfair_refresh` |
| Match replay | `list_replays`, `get_replay_meta`, `get_replay_frames` |
| Analytics | `get_analytics*`, `get_decisions*`, `list/save/delete/run_strategy`, `backtest_strategy`, `request_backtest`, `list_backtest_runs/results`, `get_direction_report*` |
| Cruscotto partite | `fixture_predictions`, `get_betfair_fixtures`, `add_to_watchlist`, `get_market_frequency`, `get_market_delays`, `get_league_seasons`, `get_poisson_calibration_eta`, `get_direction`, `get_direction_eta`, `get_betfair_direction_odds`, `get_betfair_full_odds` |
| Scelta sport, accesso | Supabase auth, `leads` |

Nessuna di queste cambia firma. La testata globale non aggiunge chiamate: legge dal provider che riusa le
sottoscrizioni esistenti (§A). Da misurare prima e dopo (regola dell'utente 30/09): numero di connessioni WS aperte
e chiamate REST al minuto con l'exe acceso, a schermo fermo sulla Control Room.

---

## F. Rischi e come si misurano

| Rischio | Misura | Soglia per procedere |
|---|---|---|
| Un test smette di trovare un elemento | `npx vitest run` completo (319 file di test oggi) | stesso numero di test verdi di prima, nessuno saltato |
| Errori di tipo | `npx tsc -p tsconfig.app.json --noEmit` | 0 errori (come dal 17/09), mai `@ts-ignore` |
| Build dell'exe | `npm run build` (l'exe ricostruisce `dist` all'avvio) | build verde; l'utente riavvia l'app quando vuole, mai con posizioni live aperte |
| La guardia di design si rompe | `designGuard.test.ts`, `zeroPerAssente.test.ts` | verdi senza nuove eccezioni |
| Sticky e sovrapposizioni (testata globale sopra le testate delle pagine) | controllo visivo a 1280, 1600 e 1920 px di Control Room, Segui live, Terminal tennis, Mike | nessun elemento coperto, nessuno scroll orizzontale a 1280 |
| Più letture o connessioni per la testata globale | conteggio WS e REST/min prima e dopo | uguale |
| Regressione della Control Room | confronto a vista con screenshot di oggi blocco per blocco (stesso ordine, stessi testi) | identico salvo stile |
| Prima schermata | avvio exe → `/board` dentro il guscio | si apre il Programma del giorno |
| Ritorno indietro | `ui.shell=off` sull'exe acceso | app identica a oggi senza rebuild |

Non verificato da questo lavoro: non ho eseguito vitest, tsc né build (lavoro in sola lettura); il numero 319 è il
conteggio dei file `*.test.ts(x)`, non dei casi.
