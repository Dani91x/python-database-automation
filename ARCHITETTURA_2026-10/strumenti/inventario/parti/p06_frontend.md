## 6. Frontend: rotte, pagine, pannelli e da dove leggono

Script: `f01_frontend.py` (regex e grafo degli import su `frontend/src` non test: 389 file, 128.405 righe; esclude `fotografia/`, `anteprima/`, `certification/` e i test) ->
`uscite/f01_rotte.tsv`, `f01_rotte.md` (tabella sotto), `f01_pagine.txt` (per ogni pagina, ogni RPC/tabella/canale raggiungibile con `file:riga`), `f01_accessi_file.tsv` (ogni accesso ai dati:
`file`, `riga`, tipo, nome), `f01_riepilogo.txt`. Riscontro con il lavoro del primo giro: `strumenti/dati_J/accessi.tsv` (160 `rpc`, 4 dinamiche, 33 canali) e' coerente con
`f01` (159 `.rpc` letterali + 2 dinamici, 32 `getLocalChannel`): lo uso solo come controllo.

### 6.1 Struttura dell'app

- Ingresso `frontend/src/main.tsx` -> `App.tsx` (`QueryClientProvider` di TanStack Query, `HelmetProvider`, `BrowserRouter`, `SafeStrategyProvider` globale: valuta i segnali Safe anche fuori dalla
  pagina Safe, `App.tsx` intestazione). **Due alberi di rotte con gli stessi percorsi**: l'albero di default (`ui.shell='off'`, `App.tsx:110-296`, ogni pagina avvolta da `ProtectedRoute`) e quello del «guscio v2»
  (`RotteGuscioV2`, `App.tsx:48-93`: layout `ProtectedRoute > AppShell` con sidebar+testata e `<Outlet/>`, `components/shell/{AppShell,Sidebar,TestataGlobale,navigazione}`);
  sceglie `leggiUiShell()` (`frontend/src/lib/uiShell.ts:44`: chiave locale `ui.shell`, poi `VITE_UI_SHELL`, poi `off`; letta una volta, `App.tsx:98`).
  `/ladder-popout`, landing, `check-email`, `reset-password` e 404 sono fuori dal guscio (commento `App.tsx:40-47`). Le 26 rotte sono scritte DUE volte (una per albero): duplicazione da sapere.
- Protezione: `ProtectedRoute` (`components/ProtectedRoute`) su tutte le pagine tranne landing/check-email/reset-password/404 (login via Supabase auth: `components/landing/AuthSection.tsx`, tabella `leads`).
- **Un solo IPC Electron**: `desktop/preload.js:21` espone `window.alphascoreCanale = { token }` (sola lettura). Non ci sono `ipcRenderer`/`ipcMain`; nessuna edge function chiamata (`functions.invoke`: 0), nessun `fetch(` diretto (0),
  5 `window.open` (finestre Video/Stats/ladder staccato: `main.js:854-880` `setWindowOpenHandler`).
- Accesso ai dati (`f01_accessi_file.tsv`, conteggio dei punti di chiamata nei file non test): **159 `.rpc(` letterali (150 RPC distinte) + 2 dinamici**, **26 `.from(` su 17 tabelle**
  (`fixture_predictions` 6, `safe_strategy_requests` 4, `betfair_live_heartbeat` 2, e le altre una volta), **32 `getLocalChannel(`**, **59 punti realtime** (`.channel(`/`postgres_changes`),
  **73 punti di polling** (`setInterval`/`refetchInterval`), 16 `localStorage`.

### 6.2 Le 26 rotte

La colonna «chiusura» e' la chiusura transitiva degli import locali della pagina: e' un **limite superiore** di cio' che la pagina puo' toccare (una pagina che importa un hub come
`lib/live.ts` eredita tutte le sue RPC anche se ne usa una). Esempio: `/tennis` (`TennisDashboard.tsx`, 33 righe) risulta con 48 RPC perche' importa `lib/tennis.ts`; non significa che le chiami tutte.
I conteggi esatti di cio' che una pagina chiama davvero stanno in `f01_pagine.txt` (RPC con `file:riga`).

{{file:f01_rotte.md}}

Descrizione delle pagine (prima riga di commento del file della pagina; funzionalita' complete nell'`01_FUNZIONALITA.md`):
`/board` «Programma di oggi» (due tab calcio/tennis alimentate SOLO dai push `board` dei due canali locali, `pages/Board.tsx:1-5`); `/control-room` «IL BANCO DELLA GIORNATA»
(tre bot Omega/Safe/Mike + scalper + tennis in una pagina, `pages/ControlRoom.tsx:1-6`, 1.740 righe + `useControlRoom.ts` 4.322); `/omega` (bot Correct Score LAY, `Omega.tsx:1-5`);
`/safe-strategy` (radar + bot, `SafeStrategy.tsx:1-6`); `/mike` (Under 3.5 / Over 4.5 paper-first, `Mike.tsx:1-6`); `/segui-live` (partite sottoscritte allo stream, dettaglio realtime, `SeguiLive.tsx:1-5`);
`/multi-ladder` (N ladder affiancati, `MultiLadder.tsx:1-4`); `/ladder-popout` (un ladder in finestra staccata, `LadderPopout.tsx:1-6`); `/market-watch` (stile Fairbot, `MarketWatch.tsx:1-3`);
`/live-pnl` (P&L di giornata, fonti `get_live_settled`, `LivePnl.tsx:1-3`); `/trade-journal` (review post-sessione, `TradeJournal.tsx:1-3`); `/report-personale` (KPI, equity, drawdown,
`ReportPersonale.tsx:1-3`); `/watchlist` (Da valutare / Giocate / Scartate, `Watchlist.tsx:1-3`); `/analytics` (pagella per motore e mercato, solo RPC aggregate, `Analytics.tsx:1-3`);
`/dashboard` (calcio: partite del giorno, previsioni ML, ritardi, direzioni, backtest automatico: componenti in `components/dashboard/`); `/tennis`, `/tennis/terminal`, `/tennis/replay`
(«Screen 2», «Screen 3 - Tennis Trading Terminal», «REPLAY TENNIS»); `/match-replay` (Football Trading Simulator, `MatchReplay.tsx:1-5`); `/storico/calcio` e `/storico/tennis`
(`StoricoSport.tsx:1-4`, stessa pagina con parametro sport); `/select-sport`, `/`, `/check-email`, `/reset-password`, `*`.

### 6.3 I moduli «hub» (`frontend/src/lib/`): dove stanno le RPC

Un'unica libreria tipizzata per area (non un client generico): `lib/tennis.ts` 22 RPC, `liveOrders.ts` 19, `analytics.ts` 14, `omega.ts` 11, `safeBot.ts` 9, `betfair.ts` 9, `personalReport.ts` 8, `live.ts` 7,
`dailyHistory.ts` 7, `scalperControlRoom.ts` 6, `mike.ts` 6 (`f01_riepilogo.txt`, seconda sezione). I modelli di stato per bot: `mike.ts` 2.454 righe, `safeBot.ts` 2.256, `safeStrategy.ts` 1.731, `omega.ts` 1.655,
`interruttori.ts` 1.533 (interruttori e modalita' di tutti i bot), `controlRoom.ts` 1.220, piu' `useControlRoom.ts` 4.322 (`components/controlroom/`).
Il trasporto locale: `lib/localChannel.ts` (client WS puro, 8 canali, `:50-67`), `lib/localTransport.ts` (fallback DB, `:84`), `lib/canaleRunner.ts`, `lib/flussoStreamRunner.ts`, `lib/usePosizioniCanale.ts`, `lib/useOrdiniCanale.ts`.
`lib/replayBotCatalogo.ts` (11.099 righe) e' GENERATO (1.1).

{{sez:f01_riepilogo.txt:== ACCESSI AI DATI PER FILE}}

### 6.4 Pannelli (file piu' grandi in `frontend/src/components/`, >= 380 righe)

Elenco dal tsv di `s01` (non descrive la funzione di ogni pannello: e' compito di `01_FUNZIONALITA.md`): `controlroom/PannelloBot.tsx` 1.053, `live/LadderView.tsx` 2.984 (il ladder, usato da 8 rotte), `mike/MikeMatchCard.tsx` 1.174,
`live/ScalperPanel.tsx` 975, `omega/MissionPanel.tsx` 946, `safestrategy/BotParamsSheet.tsx` 932 (parametri editabili del bot Safe), `controlroom/PosizioniChiuse.tsx` 917, `safestrategy/SafeTradesTable.tsx` 873, `live/RiskRulesPanel.tsx` 764,
`omega/MissionCard.tsx` 723, `watchlist/MultiTradeForm.tsx` 714, `omega/MatchTradesTable.tsx` 709, `tennis/TennisBotPanel.tsx` 685, `watchlist/WatchlistPanel.tsx` 682, `live/XHedgePanel.tsx` 679, `controlroom/SchedaPropostaOpportunita.tsx` 657,
`live/GridView.tsx` 653, `omega/ManualPanel.tsx` 644, `dashboard/DirezioniReport.tsx` 640, `safestrategy/OpportunityGroup.tsx` 637, `tennis/TennisMatchStats.tsx` 633, `live/DutchingPanel.tsx` 617, `live/LiveTradingPanel.tsx` 612,
`controlroom/SchedaPartita.tsx` 607, `dashboard/RitardiPanel.tsx` 598, `dashboard/MarketFrequencyPanel.tsx` 550, `tennis/TennisMatchesList.tsx` 535, `dashboard/MatchesList.tsx` 511, `controlroom/CashOutGlobale.tsx` 489,
`trading/EventPnlTable.tsx` 479, `controlroom/DettaglioRigaView.tsx` 479, `trading/CashOutButton.tsx` 471, `live/LiveControlsPanel.tsx` 463, `dashboard/DirezioneDashboard.tsx` 455, `dashboard/BacktestAutomatico.tsx` 426,
`controlroom/testata/FasciaStop.tsx` 418, `watchlist/TradeForm.tsx` 414, `landing/AuthSection.tsx` 398, `safestrategy/SafeStrategyProvider.tsx` 389.
Cartelle di componenti per righe di codice (sezione 1.5): `controlroom` 17.426 (55 file), `live` 9.831, `dashboard` 6.399, `safestrategy` 5.125, `trading` 4.346 (design system condiviso), `omega` 3.262, `tennis` 2.549, `replay` 2.268, `mike` 2.148, `watchlist` 1.980.

### 6.5 Da dove leggono i bot e la Control Room (percorso del dato)

- **Dal canale locale** (push, senza DB): `/board` (programma del giorno: topic `board`), ladder (`LadderView`, topic `ladder`/`now`), posizioni/ordini (`lib/usePosizioniCanale.ts`, `useOrdiniCanale.ts`),
  freno e ordini reali (`components/controlroom/RigaFreno.tsx:122`, `RigaOrdiniReali.tsx:122`, `RigaCapacitaMercati.tsx:31`: canale `calcio`), righe di Mike/Omega/Safe (`useMike.ts:292`, `Omega.tsx:233`, `useSafeBot.ts:387`),
  scanner (`useControlRoom.ts:1514`, `:1567`), ponte tennis (`:1750`), scalper (`:1795`), conto (`:1923`, `:1937`), tennis vivo (`useTennisVivo.ts:111`), x-hedge (`XHedgePanel.tsx:176`), stream mercato (`FlussoStreamBanner.tsx:16`).
- **Dal DB via RPC** (poll e realtime): tutto lo storico (`dailyHistory.ts`, `posizioniChiuse.ts`), i comandi dei bot (`mike_activate`, `safe_activate`, `omega_activate`, `scalper_activate`, `tennis_bot_arm`: `lib/mike.ts`,
  `safeBot.ts`, `omega.ts`, `scalperControlRoom.ts`, `tennis.ts`), le impostazioni di rischio (`liveOrders.ts`: `get_live_settings`, `set_live_kill_switch`, `set_live_order_mode`), l'analitica.
- **Comandi ordine**: dalla pagina al runner via `LocalChannel.request('order')` con token (`localChannel.ts`), con ripiego sulla coda DB `request_betfair_live_order` (`lib/liveOrders.ts:133`, `lib/localTransport.ts`).
  Il client non ritenta mai (money-critical).

