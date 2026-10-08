# SCHEDA J — FRONTEND (`frontend/src`)

Perimetro: `frontend/src` (917 file tracciati, `git ls-files frontend/src | wc -l`): 426 file di codice = **125.573 righe** (`00_INVENTARIO.md` §1.1, §1.5) + **11.099 righe GENERATE**
(`lib/replayBotCatalogo.ts`) + **73.437 righe di test in 365 file** (strumento `strumenti/J_test_e_polling.py test`). Non inclusi: `frontend/e2e_fase1/` (3 file), `frontend/scripts/` (analisi scalper), `desktop/` (scheda I).
Data: 08/10/2026. Autore: delegato Sonnet. Sola lettura: nessun file toccato fuori da `ARCHITETTURA_2026-10/`.
Strumenti usati (tutti in `ARCHITETTURA_2026-10/strumenti/`, rieseguibili): `misura_frontend_J.py` (primo giro: `dati_J/accessi.tsv`, `dati_J/ancore.tsv`), `J_per_file.py` -> `dati_J/per_file.tsv` (393 file: righe, `data-testid`, bottoni, campi, `setInterval`, RPC, tabelle, canali, prima riga di commento),
`J_test_e_polling.py` -> `dati_J/polling.tsv` (169 righe: ogni `setInterval`/costante `*_MS` con `file:riga`), `J_gemelli_lib.py` (lunghezza dei blocchi gemelli in `lib/{mike,safeBot,omega}.ts`).
Fonti gia' pronte e citate (non rifatte): `00_INVENTARIO.md` §6 (26 rotte, 150 RPC, un solo IPC, canali 47330-47338), schede E1-E5, F, A, D.

---

## 1. OGGI

### 1.1 Numeri (righe di codice non test da `00` §1.5; test: mia misura, `it(`/`test(` a inizio riga)

| cartella | codice | file | test (righe) | test (file / casi) |
|---|---:|---:|---:|---|
| `lib/` | 45.369 | 148 | 28.786 | 154 / 2.504 |
| `components/controlroom` | 17.426 | 55 | 16.699 | 79 / 1.043 |
| `pages/` | 14.042 | 25 | 8.757 | 23 / 406 |
| `components/live` | 9.831 | 21 | 3.598 | 20 / 170 |
| `components/dashboard` | 6.399 | 32 | 563 | 8 / 28 |
| `components/safestrategy` | 5.125 | 12 | 3.206 | 15 / 221 |
| `anteprima/` (NON importata dall'app, vedi 1.7) | 4.651 | 22 | 0 | 0 |
| `components/trading` | 4.346 | 25 | 3.222 | 17 / 243 |
| `components/omega` | 3.262 | 6 | 2.192 | 10 / 129 |
| `components/tennis` | 2.549 | 7 | 599 | 3 / 30 |
| `src/*` (App, main, index.css...) | 2.426 | 4 | 0 | - |
| `components/replay` | 2.268 | 15 | 731 | 5 / 48 |
| `components/mike` | 2.148 | 7 | 2.066 | 13 / 140 |
| `components/watchlist` | 1.980 | 4 | 0 | 0 |
| `components/ui` (shadcn) | 903 | 15 | 0 | 0 |
| `components/landing` | 865 | 8 | 0 | 0 |
| `certification/` (client reale per i test E2E) | 523 | 6 | 1.718 | 10 / 39 |
| `components/report` | 488 | 2 | 0 | 0 |
| `components/shell` (guscio v2) | 473 | 5 | 241 | 1 / 15 |
| `tennis-replay`, `fotografia`, `components/*.tsx`, `hooks`, `integrations`, `test` | 499 | 7 | 1.059 | 7 / 26 |
| **Totale** | **125.573** | **426** | **73.437** | **365 / 5.042** |

Il rapporto test/codice e' 0,58. Aree SENZA alcun test: `watchlist` (1.980 righe, ordini REALI con tetto: `MultiTradeForm.tsx`), `landing`, `report` (`ManualTradeForm`), `ui`, `anteprima`. Suite intera dichiarata verde al 07/10: 5.243 test (`CRONOSTORIA.md`, riga «CANTIERE D (REPLAY TENNIS) FASE 2»: «vitest a blocchi 5243 verdi 0 rossi»).

### 1.2 Struttura dell'app (letta dal codice)

- Ingresso `main.tsx` -> `App.tsx`. **Due alberi di rotte con gli stessi 26 percorsi**: quello di default (`App.tsx:110-296`, ogni pagina in `ProtectedRoute`) e quello del «guscio v2» (`RotteGuscioV2`, `App.tsx:48-93`, `AppShell` con `<Outlet/>`); li sceglie `leggiUiShell()` (`lib/uiShell.ts:44`: chiave locale `ui.shell`, poi `VITE_UI_SHELL`, poi `off`), letta una volta (`App.tsx:98`). Default SPENTO (`CRONOSTORIA.md` 02/10: «Guscio SPENTO di default»).
- `App.tsx:39` crea un `QueryClient` e `App.tsx:100` lo monta (`QueryClientProvider`), ma **`useQuery`/`useMutation`/`refetchInterval` hanno 0 usi** nel codice non test (`grep -rn "useQuery\|useMutation\|refetchInterval" frontend/src`: 0 righe): la libreria di cache e' montata e non usata; TUTTO il caricamento e' scritto a mano con `useEffect` + `setInterval` + `supabase.rpc` (cfr. 1.5). Un solo IPC Electron: `desktop/preload.js:21` espone `window.alphascoreCanale = { token }` (00 §6.1).
- Accessi ai dati (`dati_J/accessi.tsv`, 159 righe `rpc` non test): **159 `.rpc(` (150 RPC distinte) + 2 dinamici, 26 `.from(` su 17 tabelle, 32 `getLocalChannel(`, 59 punti realtime (`postgres_changes`/`.channel(`), 73 `setInterval`/`refetchInterval`, 16 `localStorage`** (00 §6.1; `J_per_file.py`: 73 `setInterval(`, 39 file con realtime). Le chiamate stanno in `lib/` (wrapper tipizzati per area); solo 8 file non test fuori da `lib/` importano il client Supabase (`grep -lE "integrations/supabase/client" components pages`: `dashboard/FixtureSelector`, `dashboard/MatchesList`, `landing/AuthSection`, `shell/Sidebar`, `tennis/TennisNav`, `pages/Dashboard`, `pages/ResetPassword`, `pages/SelectSport`: auth, `fixture_predictions`, `leads`).
- **Scritture dirette su tabella: una sola**, `leads` INSERT (`components/landing/AuthSection.tsx:74`). Le 4 `.from('safe_strategy_requests')` (`lib/safeBot.ts:1418,1467,1486`; `lib/controlRoomProposte.ts:371`) sono tutte `select`. **Ogni comando ai bot e' una RPC** (67 distinte, elenco in 1.6) oppure un messaggio sul canale locale (`LocalChannel.request('order')`, `lib/localChannel.ts`, tetto `LOCAL_REQUEST_TIMEOUT_MS = 10_000` `:73`; il client non ritenta mai: money-critical, 00 §6.5).

### 1.3 Le 26 rotte: da dove leggono, a che cadenza, cosa scrivono

Cadenze = `setInterval`/costanti `*_MS` DELLA PAGINA e dei suoi hook (`dati_J/polling.tsv`); le letture sono RPC salvo dove scritto «canale». Il realtime Supabase (`postgres_changes`) sveglia una rilettura con debounce (`useMike.ts:35` 1,5 s, `useSafeBot.ts:35` 1,2 s, `Omega.tsx:86` 1,2 s).

| rotta | pagina | legge da | cadenza (file:riga) | scrive / comanda |
|---|---|---|---|---|
| `/control-room` | `pages/ControlRoom.tsx:173` + `useControlRoom.ts` | 19 letture in `Promise.allSettled` (`useControlRoom.ts:1378-1401`: scan, scan-status, `get_omega_state`, `get_omega_trades(2000)`, safe/mike/runner, proposte, `get_safe_daily` x2, eventi/missioni Omega, follow tennis/calcio, servizi + giornata x2 + ordini dei 4 bot tennis, scalper) + realtime (22 punti `subscribe`/`postgres_changes` nel solo hook) + 12 `getLocalChannel` (47331-47338) | ricarica **30 s** (`:210,1498`); orologio 1 s (`:234,1902,1991`); esiti approvazioni 1,5 s (`:3276`); esiti chiusura 2 s (`:3774`); freno 30 s (`RigaFreno.tsx:32,143`); ordini reali 30 s (`RigaOrdiniReali.tsx:48,160`, minimo 2 s `:50`); capacita' mercati 30 s (`RigaCapacitaMercati.tsx:46`) | `*_activate/stop/update_params`, `mike_request`, `safe_request(_approve/_ignore)`, `omega_request(_approve/_ignore)`, `scalper_*`, `tennis_bot_*`, `set_live_order_mode`, `set_live_kill_switch`, `set_live_settings`, coda ordini |
| `/omega` | `Omega.tsx:89` | `get_omega_state/trades/events/...`, canale 47334 (`Omega.tsx:233`) | 15 s (`Omega.tsx:274,301`), orologio 5 s (`:292`); tab Missione 10 s (`MissionPanel.tsx:299,333`), MissionCard 15 s (`:230`), Manuale 8 s (`ManualPanel.tsx:210`) | `omega_activate/stop/update_params/request`, missioni, `omega_evento_riprendi` |
| `/safe-strategy` | `SafeStrategy.tsx:102` + `SafeStrategyProvider.tsx:131` | `get_safe_*`, scanner `safe_strategy_scan/status`, `safe_strategy_opportunities`, canale 47335 (`useSafeBot.ts:387`) | 15 s (`useSafeBot.ts:28,251`; `SafeStrategy.tsx:138,607`); provider: backup 30 s (`SafeStrategyProvider.tsx:69,269`), rivalutazione segnali **5 s** nel browser (`:76,301`), flush 400 ms (`:71`) | `safe_activate/stop/update_params/request/request_approve`, `cashOutEvento`, `riprendiEventoSafe` (`safeBot.ts:1241,1247`) |
| `/mike` | `Mike.tsx:74` | `get_mike_state/trades`, canale 47333 (`useMike.ts:292`) | 15 s (`useMike.ts:33,188`; `Mike.tsx:102`), orologio 5 s (`Mike.tsx:95`), orologio unico 1 s (`useMikeClock.ts:19`) | `mike_activate/stop/update_params/request` |
| `/segui-live` | `SeguiLive.tsx:961` (+ `LadderView.tsx:1523`) | `get_live_follows`, `live_now`, `live_ladder`, ordini/posizioni/regole (RPC), ladder dal canale 47331 | 10 s (`SeguiLive.tsx:226`), 15 s (`:283,1012`), 5 s (`:888`), 1 s (`:299`) + pannelli (1.5) | `request_betfair_live_order`, `request_live_risk_rule`, `set_live_*`, `scalper_*`, `segui_live_apri_partita` |
| `/multi-ladder`, `/ladder-popout` | `MultiLadder.tsx:23`, `LadderPopout.tsx:13` -> `StandaloneLadder.tsx:80` | come SeguiLive (ladder + ordini) | come `LadderView` (1.4) | ordini dal ladder |
| `/market-watch` | `MarketWatch.tsx:160` | `get_live_positions_event`, `get_tennis_live_positions_all`, canali 47331/47332 | 30 s (`:180,287`), 10 s (`:226,327`) | cash-out evento |
| `/live-pnl` | `LivePnl.tsx:197` | `get_live_settled`, `betfair_live_risk_state`, posizioni | 30 s (`:238`), 15 s (`:261,274`) | - |
| `/board` | `Board.tsx:222` | SOLO canale 47331/47332 topic `board` | orologio 1 s (`:80`) | `tennis_follow_event` |
| `/tennis` | `TennisDashboard.tsx:13` -> `TennisMatchesList.tsx:149` | `get_tennis_fixtures`, `tennis_markets` | refresh a comando | `request_tennis_refresh`, follow |
| `/tennis/terminal` | `TennisTerminal.tsx:31` | `tennis_live_now`, `get_tennis_bots_state`, canali 47332/47337 | orologio 1 s (`:96`); pannello bot 30 s (`TennisBotPanel.tsx:53,511`) | `tennis_bot_arm/disarm`, `tennis_bot_service_*`, `request_tennis_live_order` |
| `/tennis/replay` | `TennisReplay.tsx:111` | `list_replays_tennis`, `get_replay_tennis_meta` (`tennisReplay.ts`) | riproduzione 1 s / 300 ms (`:86-87`) | `request_backtest` |
| `/match-replay` | `MatchReplay.tsx:105` | `list_replays`, `get_replay_meta`, `get_replay_frames`, `get_replay_bot_esito` | 1 s / 300 ms (`:75-76`) | `request_backtest` (Applica bot) |
| `/storico/calcio`, `/storico/tennis` | `StoricoSport.tsx:70` | `get_*_daily`, `get_*_day_trades`, `get_storico_stake` | giorno operativo 60 s (`:76`) | - |
| `/trade-journal` | `TradeJournal.tsx:82` | `get_live_journal`, `get_live_settled` | nessuna | `set_live_journal_note` |
| `/report-personale` | `ReportPersonale.tsx:528` | `get_personal_report/trades`, `get_cash_movements` | nessuna | `add_personal_trade`, `settle_personal_trade`, `reset_personal_report`, `add_trade_leg` |
| `/watchlist` | `Watchlist.tsx:28` -> `WatchlistPanel.tsx:656` | `get_watchlist`, `get_betfair_orders` | ordini piazzati 3 s / 15 s (`PlacedOrdersPanel.tsx:15-16`), ack 20 s (`WatchlistPanel.tsx:184`) | `request_betfair_order`, `set_watchlist_decision`, `delete_from_watchlist` |
| `/analytics` | `Analytics.tsx:84` | `get_analytics*`, `get_decisions*`, `list_backtest_*` | nessuna | `save/delete/run_strategy`, `request_backtest` |
| `/dashboard` | `Dashboard.tsx:18` | tabella `fixture_predictions` + `get_betfair_*`, `get_direction*`, `get_market_*` | nessuna | `add_to_watchlist` |
| `/select-sport`, `/`, `/check-email`, `/reset-password`, `*` | `SelectSport.tsx:82`, `LandingPage.tsx:15`, `CheckEmail.tsx:6`, `ResetPassword.tsx:28`, `NotFound.tsx:5` | Supabase auth, `leads` | - | `leads` INSERT (`AuthSection.tsx:74`) |

### 1.4 Il trasporto locale e il ladder

- 8 canali WebSocket 127.0.0.1: `calcio` 47331, `tennis` 47332 (runner: comandi + push), `mike` 47333, `omega` 47334, `safe` 47335 (solo push), `scanner` 47336, `tennis_bot` 47337, `scalper` 47338 (`lib/localChannel.ts:50-67`, `PORTS`); riconnessione lineare 1-5 s (`:70-72`). Token di sessione dal preload (`desktop/preload.js:21`).
- **Il ladder oggi**: il runner pubblica il ladder sul canale a **200 ms di serie** (`ladder_worker`, scheda A riga 150: `ladder_canale.py:46,103-105`, `config_stream.py:60,74`): e' un POLLING lato server con push al client. Il browser NON fa polling a 200 ms: `localLadderSource` (`lib/localTransport.ts:126`) serve `fetch` dall'ultimo push in cache e `subscribe` ai push `ladder` filtrati per `market_id` (`:143-153`); se il canale e' `off` o muto oltre `LADDER_MUTO_MS_DEFAULT = 4_000` (`:190`) ripiega sul realtime Supabase `live_ladder`/`tennis_live_ladder` (`lib/live.ts:632`, `tennis.ts:271`), riattaccandosi al canale quando torna (controllo ogni 250-1000 ms `:325,381`). Cache invalidata alla disconnessione: mai un book congelato dato per vivo (`localTransport.ts:11-14`).
- Ordini/posizioni del ladder: push `order`/`position` bucketizzati per `mode` (righe senza `mode` valida scartate, `localTransport.ts:7-8`); ripiego a poll 5 s (`ORDERS_POLL_MS`, `LadderView.tsx:198`) o riconciliazione 10 s con realtime sano (`:199`, `:1800-1808`), debounce 250 ms (`:1782`).

### 1.5 Polling nel dettaglio (`dati_J/polling.tsv`, 169 righe; qui i soli che leggono dati, non gli orologi di sola grafica)

| ambito | periodo | file:riga | cosa rilegge |
|---|---|---|---|
| Control Room | 30 s | `useControlRoom.ts:210,1498` | 19 letture del banco (1.3) = 38 richieste/min ferme |
| Control Room (freno, ordini reali) | 30 s | `RigaFreno.tsx:32,143`; `RigaOrdiniReali.tsx:48,160` | impostazioni di rischio / modalita' ordini |
| Control Room (esiti) | 1,5 s / 2 s | `useControlRoom.ts:3276`; `:3774` | solo mentre c'e' un'approvazione/chiusura in corso (`idsInAttesa`, `daRileggere`) |
| Control Room (segue ordine) | 2 s, max 90 s | `useSeguiOrdini.ts:30,34,135` | esito di un clic |
| `/mike`, `/omega`, `/safe-strategy` | 15 s | `useMike.ts:33`; `Omega.tsx:274,301`; `useSafeBot.ts:28`; `SafeStrategy.tsx:138,607` | stato + trade + aggregati (2-3 timer per pagina) |
| Safe provider | 30 s backup, 5 s rivalutazione | `SafeStrategyProvider.tsx:69,76` | rivaluta in TS i segnali (motore `safeStrategy.ts`) |
| Omega missione/manuale | 8-15 s | `MissionPanel.tsx:299,333`; `MissionCard.tsx:230`; `ManualPanel.tsx:210` | missioni, eventi, richieste |
| Segui live / terminal | 3-15 s | `SeguiLive.tsx:226,283,1012`; `TerminalPositionsRail.tsx:32` (4 s); `LiveTradingPanel.tsx:95` (3 s); `LiveControlsPanel.tsx:57` (4 s); `RiskRulesPanel.tsx:161` (4 s); `ScalperPanel.tsx:67` (4 s); `XHedgePanel.tsx:162` (5 s); `GridView.tsx:61` (5 s); `HabitatCard.tsx:27` (60 s) | ordini, posizioni, regole, impostazioni, x-hedge |
| `/market-watch`, `/live-pnl` | 10-30 s | `MarketWatch.tsx:180,226,287,327`; `LivePnl.tsx:238,261,274` | posizioni e P&L |
| Watchlist | 3 s (ordini in corso) / 15 s | `PlacedOrdersPanel.tsx:15-16` | ordini REALI piazzati |
| Tennis | 30 s | `TennisBotPanel.tsx:53,511` | riconciliazione dei bot |
| Ordine / refresh Betfair | 1-1,5 s fino a 60-90 s | `betfair.ts:77,156`; `liveOrders.ts:118-119` (`LIVE_ORDER_POLL_MS = 1000`) | attesa esito di UN ordine / refresh |
| Allarme di eta' | 10 s | `LiveSignalPanel.tsx:22,100` | battito oltre 30 s |

**Letture/min dalle sole costanti, a pagina ferma** (aritmetica del codice, NON misura): Control Room >= 19 x 2 = **38/min** + freno/ordini reali 2-4/min; `/mike` e `/omega` >= 3 timer da 15 s = 12/min ciascuna; `/safe-strategy` >= 3 x 4 + 2 = 14/min. Non esiste una misura del carico verso Supabase DAL BROWSER: `MISURE_2026-10-02.md` misura solo i servizi Python (1.309 chiamate/min, 00 §3.5). Strumento che la misurerebbe: log delle richieste REST dell'app (net-log di Electron o log API di Supabase) con la Control Room aperta 5 minuti: non scritto.

### 1.6 Comandi che la UI scrive (67 RPC di scrittura su 150, filtro per prefisso su `dati_J/accessi.tsv`; primo `file:riga` di ciascuna)

- **Bot** — Mike: `mike_activate/stop/update_params/request` (`lib/mike.ts:2228,2234,2240,2274`). Safe: `safe_activate/stop/update_params/request` (`safeBot.ts:1147,1155,1161,1224`), `safe_request_approve/ignore` (`controlRoomProposte.ts:400,409`). Omega: `omega_activate/stop/update_params/request` (`omega.ts:1317,1325,1333,1501`), `omega_evento_riprendi` e `omega_eventi_chiusi_dall_utente` (`:1421,1398`), `omega_request_approve/ignore` (`omegaProposte.ts:338,348`), missioni `omega_mission_activate/stop/follow` e `set_follow_record` (`omegaMissions.ts:150,162,174,190`). Scalper: `scalper_activate/stop` (`scalper.ts:148,160`), `scalper_auto_activate/stop/update`, `scalper_stop_sessione`, `scalper_uscite_automatiche` (`scalperControlRoom.ts:166,177,188,298,313`), `scalper_media_attiva_adesso` (`mediaUnderAttiva.ts:17`), `scalper_approva_uscita` e `tennis_bot_approva_uscita` (`proposteUscite.ts:90-91`). Tennis: `tennis_bot_arm/disarm` (`tennis.ts:876,889`), `tennis_bot_service_activate/stop/update_params/set_uscite` (`:997,1008,1022,966`), `tennis_follow_event`, `tennis_set_follow_record` (`:180,198`).
- **Ordini e rischio** — `request_betfair_live_order` (`liveOrders.ts:133`), `request_tennis_live_order` (`tennis.ts:422`), `request_betfair_order` (`betfair.ts:167`), `request_live_risk_rule`, `cancel_live_risk_rule` (`liveOrders.ts:483,494`), `set_live_kill_switch`, `set_live_order_mode`, `set_live_settings` (`:684,693,705`), `set_live_journal_note` (`:932`), `ack_alert` (`live.ts:691`).
- **Archivio e analisi** — `add_personal_trade`, `add_trade_leg`, `settle_personal_trade`, `set_trade_time_operative`, `reset_personal_report` (`personalReport.ts:325,333,340,378,403`), `add_to_watchlist`, `delete_from_watchlist`, `set_watchlist_follow_live`, `set_watchlist_decision` (`watchlist.ts:110,126,134,144`), `save/delete/run_strategy(_rows)`, `request_backtest` (`analytics.ts:340,346,351,385,456`), `request_betfair_refresh`, `request_tennis_refresh`, `segui_live_apri_partita` (`betfair.ts:81`, `tennis.ts:123`, `live.ts:51`).
- **Canale locale** — comandi ordine `LocalChannel.request('order')` con ripiego sulla coda DB (`liveOrders.ts:133`, `localTransport.ts:443-447`).

### 1.7 Cosa e' dentro il numero e non e' l'app

- `anteprima/` (22 file, 4.651 righe): «SOLO PER L'ANTEPRIMA POPOLATA ... Non e' importato dall'app: il server di anteprima (`AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/server.mjs`) sostituisce con un alias Vite l'import» (`anteprima/tennisFinto.ts:1-12`); `git grep anteprima -- frontend/src ':!frontend/src/anteprima'` trova solo la parola «anteprima» nei commenti e nei testi UI. Ha le stesse chiavi e gli stessi tipi del vero (criterio §7.27).
- `lib/replayBotCatalogo.ts` (11.099 righe) e' GENERATO e COMMITTATO (non alla build): intestazione `:1-9` «FILE GENERATO - NON MODIFICARE A MANO. Origine: `Betfair/stream/backtest/applica_bot.py` ... Rigenera: `python -m Betfair.stream.backtest.applica_bot --catalogo-ts > frontend/src/lib/replayBotCatalogo.ts`»; il test `Betfair/stream/tests/test_applica_bot_tutti_2026_10_07.py` e' rosso se non e' allineato al registro del banco. Usato da `ApplicaBotPanel`, `EsitoBotPanel`, `ParametriBotPanel`, `lib/replayBot.ts`, `lib/tennisReplay.ts` (`git grep -ln replayBotCatalogo -- frontend/src`). **E' gia' il precedente di «schema -> UI»** (tipo `CatalogoBot`, `lib/replayBot.ts:55-68`): i parametri del replay arrivano dal registro Python, non sono scritti a mano. Il conteggio 125.573 lo ESCLUDE (00 §1.1).
- Codice morto accertato: `lib/mockData.ts` (264 righe, «Mock data di fallback per development») e `components/dashboard/FixtureSelector.tsx` (136 righe; `INVENTARIO_FUNZIONALITA.md` punto 8: «non montato da nessuna pagina»): `git grep` non trova alcun import dei due.

---

## 2. FUNZIONALITA' (J-001 ... J-101)

Legenda: [UI] visibile (file del pannello), [P] parametro editabile, [CMD] scrive un comando (RPC/canale, elenco in 1.6), [AL] allarme/avviso. Ogni voce raggruppa i pannelli di una stessa funzione; il livello del singolo pulsante/campo e' in `strumenti/dati_J/ancore.tsv` (5.099 righe: `data-testid`, `<Button>`, campi, `export`, `localStorage` con `file:riga`) e `dati_J/per_file.tsv` (per file: 1.138 `data-testid`, 477 `<Button>/<button>`, 299 campi), e a blocchi di pagina, con i testi esatti, in `AUDIT_2026-10-01/REDESIGN/inventario_parti/{A_CONTROL_ROOM,B_BOT_CALCIO,C_TENNIS_E_LIVE,D_STORICI_ANALISI,E_HOME_ACCOUNT_NAV}.md` (2.248 righe, riletto dal coordinatore il 01/10). Le righe `:N` sono quelle della dichiarazione del componente o della costante citata; `:1` = commento di testata del file (descrive lo scopo).

### 2.1 Guscio, accesso, navigazione, home

- J-001 [UI] `components/ProtectedRoute.tsx:10` — accesso riservato all'owner (early access) su tutte le pagine tranne landing, check-email, reset-password, 404.
- J-002 [UI] `App.tsx:110-296` — albero di default delle 26 rotte (`/board`, `/control-room`, `/omega`, `/safe-strategy`, `/mike`, `/segui-live`, `/multi-ladder`, `/ladder-popout`, `/market-watch`, `/live-pnl`, `/trade-journal`, `/report-personale`, `/watchlist`, `/analytics`, `/dashboard`, `/tennis`, `/tennis/terminal`, `/tennis/replay`, `/match-replay`, `/storico/calcio`, `/storico/tennis`, `/select-sport`, `/`, `/check-email`, `/reset-password`, `*`; 00 §6.2).
- J-003 [UI] `App.tsx:48-93` + `components/shell/AppShell.tsx:18` — guscio v2 (sidebar + testata attorno a `<Outlet/>`); fuori dal guscio `/ladder-popout`, landing, check-email, reset-password, 404 (`App.tsx:40-47`).
- J-004 [UI] `shell/Sidebar.tsx:99` + `shell/navigazione.ts:1` — sidebar a gruppi comprimibile, filtro Tutti/Calcio/Tennis (nasconde solo voci di menu).
- J-005 [UI][AL] `shell/TestataGlobale.tsx:61` — testata globale in SOLA lettura (stati dei canali 47331-47338 e conto: `PIANO_INTEGRAZIONE.md` §E); nessun comando.
- J-006 [UI] `shell/ProvaNuovaGrafica.tsx:15` + `lib/uiShell.ts:44` — «Prova la nuova grafica» / «Torna alla grafica attuale» (chiave locale `ui.shell`, ritorno senza ricompilare).
- J-007 [UI] `pages/SelectSport.tsx:82` — scelta sport: 5 card (Football, Tennis, Omega, Safe Strategy, Mike), CONTROL ROOM, Esci.
- J-008 [UI] `pages/LandingPage.tsx:15` + `components/landing/*` (8 file, 865 righe) — landing: hero, statistiche, protocollo, perche', anteprima dashboard, pricing, footer.
- J-009 [UI][CMD] `components/landing/AuthSection.tsx:50` — registrazione/accesso/recupero (schemi di validazione), INSERT su `leads` (`:74`).
- J-010 [UI] `pages/CheckEmail.tsx:6` — pagina di servizio dopo la registrazione.
- J-011 [UI][CMD] `pages/ResetPassword.tsx:28` — destinazione del link di reset password (3 stati).
- J-012 [UI] `pages/NotFound.tsx:5` — 404.
- J-013 [UI] `components/BetfairMediaButtons.tsx:39` — pulsante unico diviso in due metà (Video / Stats) che apre una finestra (5 `window.open`, gestiti da `desktop/main.js:854-880`, 00 §6.1).
- J-014 [UI][CMD] `pages/Board.tsx:222` — «Programma di oggi»: tab calcio/tennis con pallino canale, righe con orario e countdown «OFF in» o IN-PLAY, evento + stato + abbinati, 1X2 / testa a testa back-lay, «Segui live» (tennis: `tennis_follow_event`), «Terminal», Video/Stats; stati canale off / in attesa / vuoto; alimentata SOLO dal topic `board` dei canali 47331/47332.

### 2.2 Control Room (`pages/ControlRoom.tsx:173`, `components/controlroom/` 55 file 17.426 righe, `useControlRoom.ts` 4.323)

- J-015 [UI] `pages/ControlRoom.tsx:173` — «IL BANCO DELLA GIORNATA»: tre bot (Omega, Safe, Mike) + scalper + 4 bot tennis in una pagina; 58 `data-testid` `cr-*`.
- J-016 [UI][AL] `components/trading/ModeBanner.tsx:12` + `ControlRoom.tsx:541` (`cr-banner-modalita-non-lette`) — banner della modalita' e avviso «modalita' non lette».
- J-017 [UI][AL] `ControlRoom.tsx:1013` (`cr-testata`) — testata: identita', chip di ogni bot (`cr-bots:1045`), feed scanner (`cr-feed:1049`), pulsante «ricarica» (`cr-ricarica:1101`).
- J-018 [UI] `controlroom/testata/FasciaSoldiVeri.tsx:47` + `soldiVeri.ts:1` — fascia «SOLDI VERI ADESSO» col saldo nascondibile (chiave locale `CHIAVE_SALDO_NASCOSTO`, `:33,36`).
- J-019 [UI][P][CMD] `controlroom/testata/FasciaStop.tsx:1` + `salvaStop.ts:1` + `stopPerdita.ts:1` — stop di perdita in testata, modificabili dalla testata (contenitore `cr-freni`, `ControlRoom.tsx:1125`; conferma che scade in 10 s `FasciaStop.tsx:70`).
- J-020 [UI][AL] `controlroom/testata/TesseraRunner.tsx:115` — una tessera per runner (calcio, tennis) con stato e porta (`:32`); `testata/paroleImpianto.ts:1` chip dei bot e dell'impianto «in parole da trader».
- J-021 [UI][P][CMD] `controlroom/ObiettivoEditor.tsx:29` + `ObiettivoHero.tsx:92` + `ObiettivoVoci.tsx:1` — zona 1 «L'OBIETTIVO»: modifica in linea dell'obiettivo di giornata, composizione di cio' che lo erode (`lib/composizioneObiettivo.ts:1`, 572 righe), composizione live per bot dal conto (`lib/composizioneConto.ts:1`), corsia PROVA «oggi» contro «arretrati regolati oggi» (`lib/provaGiornata.ts:1`).
- J-022 [UI][AL] `ControlRoom.tsx:639` (`cr-riga-storico`), `:656` (`cr-discordanza`) — riga Storico e allarme di discordanza fra fonti.
- J-023 [UI] `controlroom/SplitSport.tsx:80` — tessere sport LIVE/PROVA con calcio e tennis separati e leggibili.
- J-024 [UI][CMD] `controlroom/PannelloBot.tsx:355` — plancia di comando «un interruttore per ogni bot»: righe da `righeBot.ts:1`, modalita' paper/live, stato servizio, uscite, aggiornato, fonte (`cr-bot-*`, `ControlRoom.tsx:1180-1199`); apertura/chiusura ricordata in `localStorage` (`PannelloBot.tsx:132,144`); conferma a 400 ms (`:568`); stato di tutti gli interruttori in `lib/interruttori.ts:1` (1.533 righe).
- J-025 [UI][P] fogli parametri aperti dalla plancia: `safestrategy/BotParamsSheet.tsx:527`, `mike/MikeParamsSheet.tsx:36`, `omega/OmegaParamsSheet.tsx:57`, `tennis/TennisBotServiceParamsSheet.tsx:60` (importati da `ControlRoom.tsx:104-114`).
- J-026 [UI][CMD] `controlroom/InterruttoreUscite.tsx:68` — interruttore uscite MANUALE/AUTOMATICO, uguale per ogni bot, con conferma per passare ad automatiche (`:26`).
- J-027 [UI][CMD] `controlroom/RigaOrdiniReali.tsx:94` — «ORDINI REALI: OFF / PAPER / LIVE» (`set_live_order_mode`, canale `calcio` `:122`, rilettura 30 s).
- J-028 [UI][CMD][AL] `controlroom/RigaFreno.tsx:93` — freno unico in Control Room (R3, 25/09), orologio 1 s e rilettura 30 s (`:32,137,143`).
- J-029 [UI] `controlroom/RigaCapacitaMercati.tsx:26` — quante partite calcio segue il runner (canale `calcio`, 30 s).
- J-030 [UI][CMD] `controlroom/ProposteUsciteFlusso.tsx:30` + `lib/proposteUscite.ts:1` — uscite da approvare dei bot di flusso (scalper, tennis).
- J-031 [UI][CMD] `controlroom/UsciteColonna.tsx:33` («Uscite — decidi tu»), `OpportunitaColonna.tsx:48` («Opportunita' di modello»), `SchedaChiusura.tsx:85` / `SchedaChiusuraOmega.tsx:60` / `PropostaUscitaMike.tsx:146` / `SchedaPropostaOpportunita.tsx:197` — le schede che decidono un'uscita o un'apertura: approva/ignora (`safe_request_approve/ignore`, `omega_request_approve/ignore`); eta' massima delle quote `SchedaChiusura.tsx:47`; cifra vecchia `PropostaUscitaMike.tsx:33`.
- J-032 [UI] `controlroom/StrisciaEsitoChiusura.tsx:70`, `EsitoAbbinamentoStriscia.tsx:24`, `EsitoChiusuraMike.tsx:27` + `lib/esitoAbbinamento.ts:1` (708 righe), `lib/mikeEsitoChiusura.ts:1`, `useSeguiOrdini.ts:30` — messaggio dopo il clic: «a che prezzo sono entrato, e sono dentro?» (rilettura 2 s, tetto 90 s).
- J-033 [UI][AL] `controlroom/SchedaPartita.tsx:278` (22 testid), `SchedaPreMatch.tsx:77`, `SchedaMike.tsx:76`, `NomiPartita.tsx:32`, `QuoteMercato.tsx:91`, `FlussoBadge.tsx:19`, `MarchioSoldi.tsx:8` — la riga/scheda di una partita: nomi, quote «da trader», dati di modello di Mike, marchio della fonte (paper/live), badge di flusso prezzi interrotto.
- J-034 [UI][CMD] `controlroom/AzioniPartita.tsx:56`, `BottoneChiudiRiga.tsx:76` (conferma 10 s `:29`), `chiudiRiga.ts:1` (esito atteso 180 s `:364`), `useChiusuraAlMs.ts:1`, `usePrezzoAlMs.ts:1` — i pulsanti su ogni scheda e il «Chiudi» cablato per singolo bot, col «se chiudo ora» al ms.
- J-035 [UI][CMD] `controlroom/CashOutGlobale.tsx:430` (armatura 10 s `:35`), `CashOutPartita.tsx:65` («CASH OUT SAFE», «RIPRENDI»), `useCashOutPartita.ts:1`, `lib/cashOutPartita.ts:1` (707 righe) — cash out della partita con i prezzi vivi.
- J-036 [UI] `controlroom/OrdiniContoPartita.tsx:21` + `ordiniConto.ts:1` — ordini del CONTO fuori dai bot, per partita (P14).
- J-037 [UI] `controlroom/PosizioniChiuse.tsx:129` (52 testid) + `lib/posizioniChiuse.ts:1` (1.052 righe) + `lib/certezzaChiusura.ts:1` — Posizioni chiuse vinte e perse, giorno della PARTITA, giudizio «effettivamente chiusa».
- J-038 [UI] `controlroom/DettaglioRigaView.tsx:1` + `dettaglioRiga.ts:1`, `aperte/statoPartitaAperta.ts:1`, `ControlRoom.tsx:1431,1466,1493,1503` — dettaglio di una riga, tab Pre-match / Live / Posizioni aperte (`cr-aperta-*`, `cr-posizioni`, `cr-aperte-live`, `cr-aperte-prova`).
- J-039 [UI][AL] `ControlRoom.tsx:706,715,736,744,770,1149` — «Uscite tennis» (`cr-tennis-uscite`), «altre live» (`cr-tennis-altre-live`), errore comando (`cr-errore-comando`), «Mike resting» (`cr-mike-resting`), errore fonti (`cr-errore`), parametri non letti (`cr-parametri-non-letti`).
- J-040 [UI] `ControlRoom.tsx:871,926,1071-1091` + `lib/controlRoomCatena.ts:1` — diagnostica «Da Betfair al tuo schermo» (`cr-catena`, `cr-fonte-*`).
- J-041 [UI] `controlroom/useTennisVivo.ts:111` + `soloTennis.ts:1` + `tennisAuto.ts:1` — punteggio/statistiche del tennis vivo nella scheda (canale `tennis`, orologio 1 s `:253`), «nella scheda tennis parte solo il tennis, a 3 euro», auto-mode dei 4 bot tennis in parole.
- J-042 Logica della pagina: `lib/controlRoom.ts:1` (1.220 righe, `realizzatoGiornata` `:1073`), `lib/eventGroups.ts:1`, `lib/ritorno.ts:1` (ritorno al punto esatto, validita' 15 min `:56`), `controlroom/comandiBot.ts:1`, `controlroom/righeBot.ts:1`, `useControlRoom.ts:1` (44 `useState`, 28 chiamate `fetch*`, 22 `subscribe`/realtime, 12 `getLocalChannel`).

### 2.3 Design system e pannelli condivisi dei bot (`components/trading/`, 25 file, 4.346 righe)

- J-043 [UI] `trading/PageShell.tsx:10`, `BotHeader.tsx:85` — guscio delle pagine Omega/Safe/Mike e header sticky (stato, salute, Storico, PAPER/LIVE, Parametri, Avvia/Ferma; identita' `BOT_IDENTITY`).
- J-044 [UI][CMD] `trading/ModeToggle.tsx:8`, `LiveConfirmDialog.tsx:22`, `ModeBadge.tsx:19`, `ModeBanner.tsx:12` — interruttore PAPER/LIVE unico, dialogo UNICO di passaggio a soldi veri, badge e banner di modalita'.
- J-045 [UI][AL] `trading/ServiceHealthChip.tsx:64` — chip salute del servizio (stantio oltre `SERVICE_STALE_S`, `:17`).
- J-046 [UI] `trading/DayBar.tsx:87` (19 testid), `StatTile.tsx:32`, `EquityCard.tsx:31`, `EquityCurve.tsx:22`, `BarreGiornaliere.tsx:38`, `DailyCalendar.tsx:91`, `DayDetail.tsx:111`, `PerformancePanel.tsx:119`, `TradingHistory.tsx:58`, `StoricoLink.tsx:51` — giornata operativa, KPI, curva equity, barre, calendario mensile, dettaglio giorno, storico condiviso.
- J-047 [UI] `trading/EventPnlTable.tsx:388` (una tabella delle operazioni per i tre bot), `StatoOrdine.tsx:1` + `lib/statoOrdine.ts:1` (stato ordine uguale per tutti), `ExitBadge.tsx:23`, `ActivityFeed.tsx:54` (attivita' del servizio), `SectionFilter.tsx:92` (sezioni mostrate/nascoste, `localStorage` `:34,45`), `EmptyState.tsx:11`.
- J-048 [UI][CMD] `trading/CashOutButton.tsx:130` — cash out con armatura 10 s (`LIVE_ARM_TIMEOUT_MS`, `:128`).
- J-049 [UI][P] `trading/ParamsSheetBase.tsx:84` — pannello parametri SPEC-DRIVEN: clamp visibile, indicatore di modifiche non salvate, «Salva parametri», «Default»; tipi di campo `number|boolean|select|text|choice|uscite` (`ParamField`). E' usato dai 4 fogli (Mike, Omega, Safe `BotParamsSheet`, servizi tennis): la spec e' scritta a mano per ogni bot.
- J-050 [UI] `lib/tradeStatus.ts:1` — mappe di etichette uniche del design system (895 righe).

### 2.4 Omega (`pages/Omega.tsx:89`, `components/omega` 3.262, `lib/omega.ts` 1.655)

- J-051 [UI] `pages/Omega.tsx:89` — BotHeader, ModeBanner, giornata operativa, partite chiuse da te, 4 KPI, altra modalita', tab Automatico / Missione / Manuale / Storico, foglio Parametri (10 gruppi, `omega.ts:1067`).
- J-052 [UI][CMD] `omega/MissionPanel.tsx:233` + `MissionCard.tsx:167` + `lib/omegaMissions.ts:1` — tab Missione: centro di controllo per partita (attiva, ferma, segui; scheda a 4 righe), poll 10-15 s.
- J-053 [UI][CMD] `omega/ManualPanel.tsx:153` — modalita' manuale: evento -> mercato -> selezione, piazza e cash out (book stantio oltre `MANUAL_BOOK_STALE_S`, `:29`; poll 8 s `:210`).
- J-054 [UI] `omega/MatchTradesTable.tsx:602` + `lib/omegaMatches.ts:1` — tabella delle partite di Omega, una riga per partita (31 testid).
- J-055 [UI][CMD] `omega/PartiteChiuseDallUtente.tsx:41` + `omega.ts:1418` — partite che hai chiuso tu, con «riprendi».
- J-056 [UI][P] `omega/OmegaParamsSheet.tsx:57` + `omega.ts:959-1054` (default), `:1067-1250` (10 gruppi), `:1258` (chiavi), `:1266-1280` (obiettivo obbligatorio, patch) — 87 parametri editabili; l'obiettivo giornaliero senza valore di serie viene rifiutato «campo obbligatorio».
- J-057 [UI][AL] `omega.ts:395-703` — testi italiani di attivita', errori e attese (`OMEGA_ACTIVITY_EXTRA` `:395`, `OMEGA_ERROR_REASON` `:512`, `omegaReasonText` `:578`, `activityLine` `:607`, `OMEGA_WAIT_REASON` `:670`): 126 chiavi che specchiano i 62 `kind` Python (E2).
- J-058 [UI] `omega.ts:757-946,1602,1646` — posizione, hedge, greenup (`positionInfo`, `hedgeInfo`, `greenupInfo`, `greenupBadge`), avvisi di regolamento (`settlementNotifications`), equity (`buildEquitySeries`).
- J-059 [UI][CMD] `lib/omegaProposte.ts:1` — le uscite di Omega diventano proposte da approvare.

### 2.5 Safe Strategy (`pages/SafeStrategy.tsx:102`, `components/safestrategy` 5.125, `lib/safeBot.ts` 2.256, `lib/safeStrategy.ts` 1.731)

- J-060 [UI] `pages/SafeStrategy.tsx:102` — BotHeader, ModeBanner, modalita' divergente, SOLDI VERI, strategie, esecuzione, giornata, 8 KPI + rischio giornaliero, tab Calcio / Tennis (Segnali, Opportunita', Monitor, Trade) / Storico, Attivita', chip strategie.
- J-061 [UI] `safestrategy/SafeStrategyProvider.tsx:131` + `SignalCard.tsx:90` + `MonitorCard.tsx:36` + `variantStyles.ts:1` — il browser RIVALUTA ogni 5 s i segnali delle 4 strategie col motore TS (`:76,301`); card del segnale attivo/scaduto, riga di partita monitorata.
- J-062 [UI][CMD] `safestrategy/OpportunityGroup.tsx:338` (20 testid), `InvestAction.tsx:172` (armatura LIVE 10 s `:79`), `safeBot.ts:1363` — opportunita' per partita e azione «Investi»/approva.
- J-063 [UI][CMD] `safestrategy/SafeTradesTable.tsx:362` (30 testid) + `safeBot.ts:1241,1247,1837,1961` — posizioni in tempo reale: cash out evento, riprendi evento, hedge parziale, libro del trade.
- J-064 [UI][AL] `safestrategy/RiskPanel.tsx:46` + `safeBot.ts:671` — rischio giornaliero (`SafeRiskParams`).
- J-065 [UI][P] `safestrategy/BotParamsSheet.tsx:527` (82 chiavi, E3-028) e `ParamsSheet.tsx:230` (348 righe, fallback senza `safe_strategy_bot_v2.sql`, E3-052); default `EXITS_DEFAULTS` `BotParamsSheet.tsx:88`; `SAFE_BOT_DEFAULTS` `safeBot.ts:701`, `SAFE_RISK_DEFAULTS` `:688`.
- J-066 [UI] `safestrategy/safeActivity.ts:1` — attivita' del servizio in italiano (502 righe).
- J-067 `lib/safeStrategy.ts:218,312,898,1129,1214,1413,1573,1646` — motore puro nel browser: `DEFAULT_PARAMS`, `mergeParams`, `evaluateBase`, `evaluateEsatto`, `evaluatePunta`, `evaluateTennis`, `trackScoreStability`, `reconcileSignals`: gemelli di `engine.py:196-320,381,1227,1329,1426,1567,1744,1907` (E3 riga 252).
- J-068 [AL] `lib/safeBot.ts:1094-1145,2121-2225` — freschezza feed/scanner (`FEED_ROW_STALE_MS` 20 s, `FEED_HARD_MAX_MS` 120 s, `SCANNER_STALE_MS` 45 s, `staleReason`), battito runner (`RUNNER_HB_MAX_AGE_S` `:2121`, `runnerPhase` `:2155`), `executionRoute` `:2225`.
- J-069 `lib/safeStrategyScan.ts:1` (407 righe) + `lib/opportunities/{tier0_arb 680, tier1_quasi 657, tier2_micro 581, validate 337}.ts` — scanner Safe lato UI e detector di opportunita'.

### 2.6 Mike (`pages/Mike.tsx:74`, `components/mike` 2.148, `lib/mike.ts` 2.454)

- J-070 [UI] `pages/Mike.tsx:74` — BotHeader, ModeBanner, allarmi, Giornata, 7 KPI, tab Partite (Pre-match, Live, Da sistemare) / Operazioni / Risultati Pre-Match / Risultati Live / Attivita' / Storico, Cash out e Chiudi a mercato.
- J-071 [UI][CMD] `mike/MikeMatchCard.tsx:1158` (63 testid; armatura flatten 10 s `:355`) + `MikeCashOutButton.tsx:51` (`:23`) — scheda di UNA partita a 11 zone, cash out e chiusura.
- J-072 [UI] `mike/MikeEventPnlTable.tsx:110`, `useMike.ts:1` (poll 15 s `:33`), `useMikeClock.ts:1` (un orologio da 1 s), `useMikeEventoAlMs.ts:1` (scheda al ms, canale 47333).
- J-073 [UI][P] `mike/MikeParamsSheet.tsx:36` (83 righe) + `mike.ts:441-570` (`MIKE_PARAM_FIELDS`), `:571-608` (`MIKE_PARAM_DEFAULTS`), `:612,642` (`mergeMikeParams`, `parametriMikeDaSalvare`) — 107 parametri (0 differenze con `config.py`, E1 riga 316).
- J-074 [UI][AL] `mike.ts:1331-1778,1796,1837,1917,663,797,2370` — testi di attivita' (`MIKE_ACTIVITY_KINDS` `:1331`, `MIKE_ACTIVITY_EXTRA` `:1422`, `mikeActivityLine` `:1493`), motivi (`MIKE_REASON_LABEL` `:1796`), nota di regolamento (`:1837`), esito richiesta (`requestOutcome` `:1917`), fasi (`MIKE_PHASE_META` `:663`), freschezza feed (`:797`), avvisi di regolamento (`detectSettledEvents` `:2370`).

### 2.7 Scalper calcio e Segui live

- J-075 [UI][P][CMD] `live/ScalperPanel.tsx:67` — Scalper Bot (975 righe): modalita' Tradizionale/Direzionale/Entrambe, stake, ARMATO/prova di serie, 10 campi numerici `SCALPER_PARAM_FIELDS` (`lib/scalper.ts:128-139`), missione 2 tick, sniper, theta, media under (`lib/mediaUnder.ts:1`, 466 righe), «ATTIVA ADESSO» (`:696-701`, `:850-854`, `:296-315`; E4-057/E4-080); poll 4 s.
- J-076 [UI] `live/HabitatCard.tsx:27` + `lib/scalperControlRoom.ts:1` (662 righe: sessioni, esposizione, chiusura, P&L del bot) — «Partite adatte oggi» (60 s) e riga scalper in Control Room.
- J-077 [UI] `pages/SeguiLive.tsx:961` — elenco delle partite seguite + HabitatCard; terminal: barra alta (modalita', LOCALE, orologio, P&L giornata, saldo, runner, esposizione, overround, cash-out mercato/evento, KILL), banner rischio gol, tab mercati, rail posizioni/ordini, ladder o grid, 7 strumenti, controlli runner, tabellone, segnali.
- J-078 [UI][CMD] `live/LadderView.tsx:1523` (2.984 righe, 36 `<button>`, 20 campi) — ladder per-mercato: piazza/annulla/green-up, ordini e posizioni (poll 5 s o 10 s con realtime), `PlaceConfirmDialog.tsx:32`, `PriceAxisBar.tsx:16`, `GridView.tsx:156` (grid one-click, stake in `localStorage` `:121,201`), `MiniPriceChart.tsx:19` e `SelectionChartPanel.tsx:80` (candele 15 s), `DepthPanel.tsx:161` (profondita'/WOM).
- J-079 [UI][CMD] `live/LiveTradingPanel.tsx:89` (3 s) + `TerminalPositionsRail.tsx:51` (4 s) — ordini e posizioni del terminal.
- J-080 [UI][P][CMD][AL] `live/LiveControlsPanel.tsx:57` — controlli GLOBALI del runner: kill switch, modalita' ordini, impostazioni (4 s).
- J-081 [UI][P][CMD] `live/RiskRulesPanel.tsx:157` — regole di rischio stile Bet Angel (764 righe, `request_live_risk_rule`/`cancel_live_risk_rule` `liveOrders.ts:483,494`; 4 s).
- J-082 [UI][CMD] `live/XHedgePanel.tsx:162` (5 s, canale `calcio` `:176`) e `live/DutchingPanel.tsx:109` (dati freschi entro 10 s `:68`) — cross-market / cover del correct-score; calcolatore e piazzamento dutching.
- J-083 [UI][AL] `live/LiveAlertBanner.tsx:20` (`ack_alert`), `FlussoStreamBanner.tsx:68` (stream muto), `LiveSignalPanel.tsx:92` (battito oltre 30 s `:22`), `LiveMarketBoard.tsx:118`, `LiveMatchCard.tsx:23` — avvisi di sistema e di flusso, segnali del Motore Live, griglia dei mercati.
- J-084 [UI] `pages/MultiLadder.tsx:23` + `pages/LadderPopout.tsx:13` + `live/StandaloneLadder.tsx:80` + `lib/workspace.ts:1` — fino a 8 ladder affiancati (layout salvato) e ladder in finestra staccata 560x860.
- J-085 [UI][CMD] `pages/MarketWatch.tsx:160` — una riga per evento (stato, MTM live/prova, rischio, cash-out EVENTO solo calcio, apri terminal), sezioni calcio e tennis separate.
- J-086 [UI] `pages/LivePnl.tsx:197` — giorno + modalita' (mai «tutte»), 4 KPI, equity intraday, per mercato / per evento, tennis posizioni aperte.

### 2.8 Tennis (`components/tennis` 2.549, `lib/tennis.ts` 1.129)

- J-087 [UI][CMD] `pages/TennisDashboard.tsx:13` -> `tennis/TennisMatchesList.tsx:149` — Partite del Giorno (Ieri/Oggi/Domani, tornei in accordion, preferiti in `localStorage` `:46,58`, quote, volume, «APRI TERMINAL»; aggiornamento forzato `request_tennis_refresh` `tennis.ts:123`).
- J-088 [UI] `pages/TennisTerminal.tsx:31` — terminal a 3 colonne: header match (punteggio, modalita' runner, SEGUI, REC), `TennisBotPanel.tsx:477`, `TennisLadderColumn.tsx:90`, `TennisMatchStats.tsx:314` (Stats/Chart/Depth, dato stantio oltre 15 s `:38`), `TennisNav.tsx:35`.
- J-089 [UI][P][CMD] `tennis/TennisBotPanel.tsx:477` — le card dei bot tennis (arma/disarma, parametri reali dal registro `TENNIS_BOT_REGISTRY` `tennis.ts:719-848`, equity `TennisBotEquityChart.tsx:55`, attivita'); riconciliazione 30 s.
- J-090 [UI][P][CMD] `tennis/TennisBotServiceParamsSheet.tsx:60` + `tennis.ts:966-1022` — parametri e interruttori dei servizi tennis (attiva, ferma, aggiorna, uscite).
- J-091 [UI] `tennis.ts:1043-1124` — righe giornaliere per bot (`TennisBotDailyRow`) e P&L per bot sommato nel client (U6 di F).
- J-092 [UI][CMD] `pages/TennisReplay.tsx:111` + `tennis-replay/TennisReplayList.tsx:18` + `TennisTimelineSymbols.tsx:45` + `lib/tennisReplay.ts:1` — REPLAY TENNIS (07/10): elenco registrazioni, simboli del tennis nella barra, Applica bot tennis.

### 2.9 Storici, report, replay, watchlist, analisi, dashboard

- J-093 [UI] `pages/StoricoSport.tsx:70` (31 testid) + `lib/storicoSport.ts:1` + `lib/dailyHistory.ts:1` (1.285 righe) — storico di uno sport: SOLDI VERI/PROVA esclusivo, filtri periodo/soldi/bot, 5 KPI, altra modalita' non sommata, «non separabile» (Omega), per bot, equity, barre, calendario, operazioni del giorno.
- J-094 [UI][CMD] `pages/TradeJournal.tsx:82` — journal post-sessione: filtri (mode tutte/paper/live: l'unico punto in cui paper e live stanno nella stessa statistica), tag e nota modificabili (`set_live_journal_note`), statistiche per pattern.
- J-095 [UI][CMD] `pages/ReportPersonale.tsx:528` + `report/ManualTradeForm.tsx:55` + `report/DateRangeFilter.tsx:28` + `lib/personalReport.ts:1` — KPI, equity, underwater, 18 metriche, consigli, calendario, per strategia/lega, Trade a 17 colonne; dialoghi Chiudi trade / Svuota / Inserisci operazione.
- J-096 [UI][CMD] `pages/Watchlist.tsx:28` + `watchlist/WatchlistPanel.tsx:656` + `TradeForm.tsx:67` + `MultiTradeForm.tsx:179` + `PlacedOrdersPanel.tsx:104` — Da valutare / Giocate / Scartate; scheda trade; scheda MULTIPLA che PIAZZA ORDINI REALI con tetto; ordini piazzati (3 s se in corso, 15 s a riposo); 0 test in questa cartella.
- J-097 [UI][AL] `pages/MatchReplay.tsx:105` + `replay/{PlaybackControls:22, TimelineSlider:65, MarketPanel:30, OpportunitaPanel:223, TradesPanel:13, ValidationCard:30, LadderBacktestPanel:33, AvvisoCoerenzaBarra:44}.tsx` + `lib/replayVerificaBarra.ts:1` (557 righe), `lib/trainingLadder.ts:1` — simulatore: selettore per lega/anno, Overall Position, 7 pulsanti di riproduzione, mercati, opportunita', Ladder TRAINING, backtest del ladder, avviso di coerenza della barra.
- J-098 [UI][P][CMD] `replay/ApplicaBotPanel.tsx:73`, `ParametriBotPanel.tsx:131`, `EsitoBotPanel.tsx:50`, `RiepilogoPnlBot.tsx:32`, `RegistroOperazioniBot.tsx:96`, `BotOrdersPanel.tsx:13`, `TrainingTradesPanel.tsx:21` + `lib/replayBot.ts:1`, `lib/replayOperazioni.ts:1` (979 righe), `lib/useApplicaBot.ts:1`, `lib/matching.ts:1` — «Applica bot» per TUTTI i bot (07/10): scelta, parametri dal catalogo generato, esito, P&L, registro delle operazioni, ordini al cursore.
- J-099 [UI][CMD] `pages/Analytics.tsx:84` — 5 tab: Performance Motori, Decisioni (`dashboard/DecisionsTab`, `DecisionsView`), Crea Strategia (`CreateStrategy`: salva/esegui), Reportistiche (`ReportisticheTab`, `DirezioniReport` 641 righe), Backtest Automatico (`BacktestAutomatico.tsx:36`, `request_backtest`).
- J-100 [UI][CMD] `pages/Dashboard.tsx:18` + `components/dashboard/` (32 file, 6.399 righe) — Partite del Giorno e dettaglio: `MatchesList.tsx:57`, `HeroMatch.tsx:13`, `MarketFrequencyPanel.tsx:78`, `RitardiPanel.tsx:133`, `PoissonPanel.tsx:46`, `TacticalEnginePanel.tsx:73`, `MLPanel.tsx:38`, `DirezioneDashboard.tsx:300`, `BetfairOddsPanel.tsx:46`, `PredictionsCard.tsx:13`, `TeamPanel.tsx:18`, `ComparisonSection.tsx:25`, `H2HSection.tsx:5`, carte Last5/Streak/CleanSheet/Penalty/Lineups/CardsByMinute/GoalsTabs; aggiungi alla watchlist (`add_to_watchlist`).
- J-101 [UI] `lib/localChannel.ts:50` + `lib/localTransport.ts:126` + `lib/{usePosizioniCanale,useOrdiniCanale,canaleRunner,flussoStreamRunner,righeCanale,runnerCanale}.ts` — trasporto locale: 8 canali, ladder/ordini/posizioni dal canale con ripiego su Supabase, righe per bot dal canale (`righeCanale.ts:1`, 289 righe, C6b).

Conteggio: **101 voci**; controlli singoli sotto di esse: 1.138 `data-testid`, 477 `<Button>/<button>`, 299 campi (`dati_J/per_file.tsv`). Cinque voci sono logica o trasporto e non pannelli (J-042, J-067, J-068, J-069, J-101).

---

## 3. DIFETTI STRUTTURALI

**3.1 Modello di stato per bot ripetuto 3 volte (misura `J_gemelli_lib.py`, righe per gruppo; `mike.ts` / `safeBot.ts` / `omega.ts`).**

| gruppo gemello | mike | safeBot | omega | righe gemelle (esempi `file:riga`) |
|---|---:|---:|---:|---|
| attiva/ferma/aggiorna | 20 | 27 | 28 | `mike.ts:2227-2246`, `safeBot.ts:1146-1172`, `omega.ts:1314-1341` (stessa forma `supabase.rpc(...)` + `throw new Error(error.message)`) |
| stato + trade (fetch) | 26 | 48 | 26 | `mike.ts:2247-2272`, `safeBot.ts:1173-1220`, `omega.ts:1342-1367` |
| realtime (subscribe) | 25 | 18 | 21 | `mike.ts:2345-2369`, `safeBot.ts:1497-1514`, `omega.ts:1368-1388` |
| esito richiesta (`requestOutcome`, `lastRequestFor`) | 103 | 59 | 0 | `mike.ts:1897-1970`, `safeBot.ts:1616-1681` |
| freschezza feed (`feedFreshness`) | 45 | 52 | 0 | `mike.ts:763-807`, `safeBot.ts:1094-1145` |
| avvisi di regolamento | 29 | 21 | 70 | `mike.ts:2370`, `safeBot.ts:1595`, `omega.ts:1576-1645` |
| serie equity | 21 | 19 | 11 | `mike.ts:2206`, `safeBot.ts:1576`, `omega.ts:1646` |
| riconciliazione (`isReconciling`) | 0 | 20 | 26 | `safeBot.ts:993`, `omega.ts:703` |
| aggregati per modalita' | 27 | 97 | 58 | `safeBot.ts:247-368`, `omega.ts:110-167` |
| tipi Status/Mode/Stats/Control | 30 | 38 | 65 | `mike.ts:16-59`, `safeBot.ts:25-90`, `omega.ts:14-80` |
| tipi Trade/Activity/State | 66 | 74 | 55 | `mike.ts:313-408`, `safeBot.ts:212-336`, `omega.ts:81-194` |
| parametri (spec + default + merge) | 229 | 177 | 516 | `mike.ts:427-655`, `safeBot.ts:624-826`, `omega.ts:194-361,957-1313` |
| **totale** | **621** | **650** | **876** | **2.147 righe** (1.225 senza i parametri) |

Altri gemelli: scalper `lib/scalperControlRoom.ts:1-662` (`StatoSessioneScalper` `:39`, `statoBotScalper` `:362`) e tennis `lib/tennis.ts:650-1124` (`TennisBotDescriptor`, `armTennisBot` `:876`, `TennisBotDailyRow` `:1043`) rifanno la stessa forma con altri nomi; `lib/interruttori.ts` (1.533 righe) e `lib/controlRoom.ts` (1.220) tengono il 4° e 5° modello (modalita'/uscite di tutti i bot, righe della plancia). Tre hook gemelli: `components/mike/useMike.ts` (393), `components/safestrategy/useSafeBot.ts` (428) e la logica di caricamento dentro `pages/Omega.tsx:274-301`.

**3.2 Parametri e valori di serie scritti piu' volte (tabella dalle schede E).**

| bot | parametri | copie a mano | differenze Py/TS misurate | fonte |
|---|---:|---|---|---|
| Mike | 107 | Python `config.py:76-390` (`PARAM_SPEC`) + TS `mike.ts:441-608` + catalogo replay generato | **0** (default, limiti, scelte) | E1 riga 316, 497 |
| Omega | 87 | `omega_config.py` + TS `omega.ts:959-1053` + `:1067-1250` + catalogo replay | **0**; nessun test di contratto che le obblighi | E2 righe 334, 509 |
| Safe | 82 chiavi nel foglio | `engine.py:196-320` / `safeStrategy.ts:218`; `bot_service.py:150-190` / `safeBot.ts:701-749`; `risk.py:37-45` / `safeBot.ts:688-696`; `exits.py:69-92` / `BotParamsSheet.tsx:88`; `merge_params` `engine.py:381` / `safeStrategy.ts:312` | non misurate (prerequisito: test di parita' Py<->TS) | E3-029 |
| Scalper calcio | 10 campi + media under | ctor `scalper_bot.py` / `VALIDATED_PARAMS` `scalper_session.py:42-70` / UI `scalper.ts:106-117` / `mediaUnder.ts:41-62` | **divergono**: `one_green_per_phase` ctor `False` (`scalper_bot.py:692`), `VALIDATED_PARAMS` `False`, UI di serie **`true`** (`scalper.ts:117`) | E4 §3.4 |
| Tennis | 29 su 147 `c.get(` | Python ctor + TS `tennis.ts:719-848` | non misurate; letterali con `_` (`50_000.0`) che un `grep 50000` non trova | E5 riga 329 |
| Replay (tutti i bot) | dal registro | `replayBotCatalogo.ts` GENERATO (test rosso se disallineato) | 0 per costruzione | 1.7 |

Il catalogo del replay dimostra che «schema -> UI» e' gia' realizzabile: l'unico punto in cui la UI NON copia i parametri a mano e' quello generato dal registro Python. Costante nel frontend che duplica una scelta del backend = errore §7.33 di `PROCESSO_STANDARD_BOT.md`: altri esempi `TennisMatchStats.tsx:38` (15 s), `TennisReplay.tsx:89` (10 s), `lib/tennis.ts:122,412` (60 s, 90 s; E5 riga 330), `lib/safeBot.ts:1094-1102` (20/120/45 s).

**3.3 Logica di strategia ricalcolata nel browser (Safe).** `lib/safeStrategy.ts` (1.731 righe) valuta da solo le 4 strategie su snapshot di `lib/live.ts`/`tennis.ts` e produce i segnali del radar (`safeStrategy.ts:1-16`: «MOTORE PURO ... segnali informativi, l'ingresso a mercato e' SEMPRE manuale»); il bot Python ha il suo `engine.py` (2.254 righe) con le stesse funzioni (J-067). Importato da 9 file (`git grep -ln "lib/safeStrategy'"`: `SafeStrategyProvider`, `SignalCard`, `MonitorCard`, `BotParamsSheet`, `ParamsSheet`, `variantStyles`, `safeBot.ts`, `pages/SafeStrategy.tsx`, `anteprima/safeRadarFinto.ts`). Due implementazioni della stessa regola = due verita' possibili sulla stessa schermata.

**3.4 Il P&L si somma/ricompone in 8 punti del client** (F §1.3 U1-U8: `composizioneConto.ts:82-240`, `controlRoom.ts:1073`, `posizioniChiuse.ts:742,582`, `dailyHistory.ts:762` + RPC `get_*_daily`, `LivePnl.tsx`, `eventGroups.ts:82,162` + `scalperControlRoom.ts:565,590` + `tennis.ts:1080,1124` + `useControlRoom.ts:4279`, `mike.ts:1057,1313` + `omega.ts:745` + `safeBot.ts:1063`, `replay-pnl.ts:50,58`): e' la causa dichiarata della discrepanza del 04/10 (tessera -10,75 contro Posizioni chiuse -5,68, F riga 229).

**3.5 Polling a mano e fan-out.** 73 `setInterval` (`J_per_file.py`), di cui 24 sono orologi di sola grafica (`set*(Date.now())`, contati a mano su `polling.tsv`) e 49 rileggono dati o gestiscono scadenze; `QueryClient` montato (`App.tsx:39,100`) e mai usato (0 `useQuery`); la Control Room rilegge 19 sorgenti ogni 30 s, fra cui `fetchOmegaTrades(2000)` = 2.000 righe di trade (`useControlRoom.ts:1380`) e le tabelle di tutti i bot, anche quando nulla e' cambiato (non c'e' revisione/ETag: ogni giro rilegge tutto e rifa' il merge, `useControlRoom.ts:1378-1430`). Stato in piu' posti: 44 `useState` nel solo hook, piu' i tre `useState` di pagina per bot.

**3.6 Testi di attivita' scritti a mano in tre formati** (`mike.ts:1331-1778` 447 righe; `omega.ts:395-703` 309 righe; `safeActivity.ts` 502 righe = **1.258 righe**) che traducono in italiano i `kind` che il backend scrive nel diario (E2: 126 chiavi UI per 62 `kind` Python). Chi aggiunge un `kind` nel servizio deve ricordarsi di aggiungerlo in TS (§6.5: «attivita' (`kind`) scritte per ogni decisione rilevante»).

**3.7 Perimetro sporco.** `anteprima/` 4.651 righe nel conteggio ma fuori dall'app (1.7); `lib/mockData.ts` 264 e `dashboard/FixtureSelector.tsx` 136 senza importatori (1.7); `ParamsSheet.tsx` 348 righe di fallback per una migrazione SQL gia' applicata (E3-052; da confermare); due alberi di rotte con gli stessi percorsi (`App.tsx:48-93` e `:110-296`, 26 rotte scritte due volte).

**3.8 File-hub enormi e senza test di contratto per bot.** `useControlRoom.ts` 4.323, `LadderView.tsx` 2.984, `mike.ts` 2.454, `safeBot.ts` 2.256, `interruttori.ts` 1.533; per sostituire Mike si toccano 92 file non test che nominano «mike» (E1 riga 16: `useControlRoom.ts` 155 menzioni, `ControlRoom.tsx` 50, `interruttori.ts` 28, `cashOutPartita.ts` 27, `controlRoom.ts` 26...). `components/watchlist` (ordini REALI) ha 0 test.

---

## 4. DOMANI

### 4.1 Principi

1. **Un solo modello di stato per bot**, prodotto dal nucleo locale (contratto D) e consumato da UNA funzione `useBot(id)`; nessun `fetchXState/fetchXTrades/subscribeX` per bot.
2. **Pannelli e parametri GENERATI** dal `Plugin.catalogo_parametri()` e dal manifesto del bot (D §4.2): il foglio e' `ParamsSheetBase` (gia' spec-driven, `trading/ParamsSheetBase.tsx:84`) alimentato da un `manifesto.ts` generato come oggi `replayBotCatalogo.ts` (1.7), con test «TS allineato» rosso se diverge.
3. **Control Room, ladder e conto dal nucleo locale a EVENTO**: un topic `banco` (snapshot completo alla connessione + delta a ogni cambio) al posto delle 19 letture ogni 30 s e dei 12 punti di canale sparsi; il ladder resta push (la cadenza di pubblicazione e' decisa lato A: `push_a_ogni_cambio`, scheda A riga 468) senza ripiego Supabase se la scelta D-J4 lo consente.
4. **Supabase solo per archivio e replay**: storico giornate, journal, report personale, analytics, replay, watchlist, landing/auth. Queste pagine usano `useQuery` (gia' installato, 0 usi oggi) invece di `setInterval` a mano.
5. **Cio' che resta specifico per bot e' la VISTA**, non il modello: scheda partita di Mike (`MikeMatchCard.tsx:1158`, 11 zone), missione/manuale di Omega, radar di Safe (segnali, opportunita'), `ScalperPanel.tsx:67`, `TennisBotPanel.tsx:477` e `TennisMatchStats.tsx:314`. Stima della parte specifica che resta: componenti `mike` 2.148 + `omega` 3.262 + `safestrategy` 5.125 + `tennis` 2.549 + `ScalperPanel` 975 = 14.059, piu' le 5 pagine bot 799 + 913 + 1.705 + 321 + 33 = 3.771 -> **~17.800 righe di vista**, di cui i fogli parametri (338 + 933 + 348) sono gia' conteggiati nelle voci di risparmio.

### 4.2 Contratto TypeScript proposto (generato dal contratto D, `Betfair/bots/contratto.py`: stessi nomi)

```ts
// frontend/src/nucleo/contratto.ts  (tipi GENERATI dal Plugin Python; non scritti a mano)
export type BotId = string;                                   // 'mike' | 'omega' | 'safe' | 'scalper_calcio' | 'tennis_pro' | ...
export type Modo = 'paper' | 'live';
export type UsciteModo = 'MANUALE' | 'AUTOMATICO';            // di serie e dopo ogni riavvio MANUALE (cond. 4-bis)
export interface CampoParametro { chiave: string; tipo: 'number'|'boolean'|'select'|'text'|'choice'|'uscite';
  etichetta: string; gruppo: string; hint?: string; serie: unknown; min?: number; max?: number; passo?: number;
  opzioni?: { valore: string; etichetta: string }[] }
export interface ManifestoBot { id: BotId; sport: 'calcio'|'tennis'; etichetta: string; parametri: CampoParametro[];
  fasi: string[]; kind_diario: Record<string, string /* modello di testo italiano */>; uscite_di_serie: UsciteModo }
export interface StatoBot { id: BotId; servizio: { vivo: boolean; battito_ms: number|null; errore: string|null };
  controllo: { acceso: boolean; modo: Modo; uscite: UsciteModo; parametri: Record<string, unknown> };
  giornata: GiornataBot; partite: PartitaBot[]; diario: VoceDiario[]; richieste: RichiestaBot[]; proposte: PropostaUscita[] }
export interface Banco { aggiornato_ms: number; bots: StatoBot[]; conto: ContoBetfair; giornata: Giornata /* F: unica fonte del P&L */;
  freno: Freno; runner: Record<'calcio'|'tennis', StatoRunner>; scanner: StatoScanner }
export type Comando =                                          // l'UNICA porta dei comandi (oggi 67 RPC diverse)
  | { t: 'bot.accendi'; bot: BotId; modo: Modo; parametri?: Record<string, unknown> } | { t: 'bot.ferma'; bot: BotId }
  | { t: 'bot.parametri'; bot: BotId; parametri: Record<string, unknown> } | { t: 'bot.uscite'; bot: BotId; uscite: UsciteModo }
  | { t: 'uscita.approva' | 'uscita.ignora'; bot: BotId; id: string } | { t: 'ordine'; ... } | { t: 'cashout'; ambito: 'partita'|'evento'; ... };
export interface Nucleo {
  banco(): Banco;                                              // ultimo stato noto
  sottoscrivi<T extends 'banco' | `bot:${BotId}` | `ladder:${string}`>(topic: T, cb: (e: EventoDi<T>) => void): () => void;
  comando<C extends Comando>(c: C): Promise<Esito<C>>;         // mai ritentato (money-critical), come `localChannel.ts:73`
  archivio: ArchivioApi;                                       // Supabase: storico, journal, report, analytics, replay (solo letture/scritture d'archivio)
}
```
Eventi esposti: `banco` (snapshot + delta), `bot:<id>`, `ladder:<market>`, `ordine`, `posizione`, `allarme`. Consumati: nessuno (la UI non produce eventi, invia `Comando`).

### 4.3 Dove vive ogni funzionalita' domani

| oggi | domani |
|---|---|
| `lib/{mike,safeBot,omega}.ts` fetch/activate/subscribe/aggregati/regolamento/equity/esito (1.225 righe gemelle) | `nucleo/useBot.ts` + `nucleo/statoBot.ts` (UNA volta, ~700 righe) |
| `MIKE_PARAM_FIELDS`, `OMEGA_PARAM_*`, `SAFE_*_DEFAULTS`, `TENNIS_BOT_REGISTRY`, `SCALPER_PARAM_*`, `MEDIA_UNDER_*`, 4 fogli | `nucleo/manifesti/<bot>.ts` GENERATI + `ParamsSheetBase` (foglio per bot di 20-30 righe: solo gruppi speciali, es. strategie Safe) |
| testi di attivita' `mike.ts:1331-1778`, `omega.ts:395-703`, `safeActivity.ts` | modelli di testo nel manifesto (`kind_diario`) + un renderer; restano solo le eccezioni con logica |
| somme di P&L (8 punti) | `contabilita/` con selettori su `Giornata` (F-050..059, F riga 275) |
| `useControlRoom.ts` (19 letture + 22 subscribe + 12 canali) | `useBanco()` su `Nucleo.sottoscrivi('banco')`; resta la logica di presentazione e dei comandi |
| `localTransport.ts` + fallback realtime ladder/ordini | `nucleo/canale.ts` (ladder/ordini solo dal nucleo; ripiego Supabase solo se D-J4 = «il browser resta supportato») |
| `safeStrategy.ts` (motore nel browser) | la UI legge le valutazioni `monitor` pubblicate dal bot/scanner (E3 passo 2); `safeStrategy.ts` in ombra con confronto automatico, poi tolto (D-J1) |
| `anteprima/` | `tools/anteprima/` fuori da `src/`; riusato come fixture di parita' popolata (5.2) |
| `mockData.ts`, `FixtureSelector.tsx` | eliminati (0 importatori) |
| 26 rotte x 2 alberi | un solo albero se D-J2 = guscio definitivo |

### 4.4 Stima delle righe (calcolo esplicito, codice non test 125.573; le stime non vincolano finche' non esistono, come in D §4.4)

| voce | oggi | domani | calcolo | sovrapposizione con altre schede |
|---|---:|---:|---|---|
| `anteprima/` fuori dall'app | 4.651 | 0 (in `tools/`) | `00` §1.5; non importata (1.7) | - |
| codice morto (`mockData.ts` 264 + `FixtureSelector.tsx` 136) | 400 | 0 | `per_file.tsv`; 0 importatori | - |
| parametri a mano -> generati | 1.758 | 0 | Mike `mike.ts:441-608` 168 + Omega `omega.ts:959-1250` 280 + Safe `safeBot.ts:688-810` 120 + tennis registro `tennis.ts:719-848` 130 + scalper (tabelle `scalper.ts:106-139`, `mediaUnder.ts:41-83`, form) 200 + `BotParamsSheet.tsx` 933 -> ~330 (-600, 82 chiavi da spec) + 3 fogli piccoli 338 -> ~80 (-260) | E1 -168, E2 -290, E3 -300, E4 -200, E5 -130 sono SOTTOINSIEMI: non sommare |
| modello di stato gemello | 995 | 0 | 1.225 righe gemelle (3.1) -> ~700 condivise = -525; hook `useMike` 393 + `useSafeBot` 428 -> `useBot` ~450 = -371; logica di caricamento di `Omega.tsx` -100 (IPOTESI, non misurata) | - |
| testi di attivita' generati | 880 | 0 | 1.258 righe (3.6) x 70 % (IPOTESI di lavoro: restano le eccezioni con logica) | E2 |
| P&L: 8 somme -> `Giornata` | 2.254 | 0 | F §4: 4.654 -> ~2.400 | F riga 300 |
| Control Room da `useBanco` | 1.080 | 0 | 25 % di `useControlRoom.ts` 4.323 (IPOTESI di lavoro; da misurare sottraendo le righe delle funzioni che chiamano `fetch*`/`subscribe*`/`getLocalChannel`: 28+22+12 punti) | - |
| **Sottototale senza decisioni** | | **-12.018** | 125.573 -> **~113.555 (-9,6 %)** | |
| motore Safe nel browser (D-J1) | 1.888 | 0 | `safeStrategy.ts` 1.731 + `safeStrategyScan.ts` 407 -> ~250 | E3 -2.044 (sottoinsieme) |
| albero rotte doppio + interruttore (D-J2) | 250 | 0 | `App.tsx:110-296` 187 + `ProvaNuovaGrafica.tsx` 35 + ~28 `uiShell.ts` (non misurate) | - |
| `ParamsSheet.tsx` fallback (D-J3) | 348 | 0 | E3-052 | E3 |
| **Totale con le 3 decisioni** | | **-14.504** | **~111.069 (-11,6 %)** | |

Il frontend scende poco in percentuale perche' e' soprattutto VISTA (Ladder 2.984, Control Room 17.426, dashboard 6.399, storici, replay): quella resta, come richiede la regola «nessuna funzionalita' persa». Il guadagno vero e' altrove: **le copie da tenere allineate passano da 3-5 a 1** per ogni parametro, per ogni testo di attivita' e per ogni somma di P&L, e i `setInterval` che rileggono dati da ~49 a quelli dell'archivio. I generati (manifesti) crescono come oggi `replayBotCatalogo.ts` (11.099 righe, non contate nel codice) e si rigenerano da `Plugin.catalogo_parametri()`.

Dopo il taglio le righe di test non si stimano: i test dei moduli gemelli (28.786 righe in `lib/`) si fondono con essi; i test nuovi sono di contratto (un test generico per bot, come `test_plugin_contratto.py` di D §4.6).

### 4.5 Confronto §9.1 «per sostituire un bot» (lato UI)

- **OGGI**, sostituire Mike nella UI: `lib/mike.ts`, `lib/interruttori.ts`, `lib/controlRoom.ts`, `lib/dailyHistory.ts`, `lib/composizione{Conto,Obiettivo}.ts`, `lib/provaGiornata.ts`, `controlroom/{PannelloBot,righeBot,chiudiRiga,useControlRoom}`, `ControlRoom.tsx`, `lib/cashOutPartita.ts`, `pages/Mike.tsx`, `components/mike/*` (7), `App.tsx` + `shell/navigazione.ts` (rotta e voce di menu), `replayBotCatalogo.ts` (rigenerato) e le fotografie `control-room.*.json` e `mike.*.json`: **92 file non test nominano «mike»** (E1 riga 16) + 2 fotografie.
- **DOMANI**: solo `frontend/src/bots/<nome>/` (eventuale `Vista.tsx` se la scheda e' specifica) e il suo manifesto generato; registro, plancia, menu, foglio parametri, righe della Control Room, storico e replay si derivano dal manifesto; test di contratto generico.

### 4.6 Cosa e' gia' in una libreria matura e oggi e' riscritto

- **Cache/dedup/refetch dei dati d'archivio**: oggi 73 `setInterval` + `useEffect` scritti a mano; TanStack Query e' GIA' una dipendenza e montata (`App.tsx:1,39,100`), 0 usi (`useQuery`, `staleTime`, `refetchInterval`, `invalidateQueries`).
- **Validazione dei form**: schemi gia' presenti in `landing/AuthSection.tsx` (`SCHEMAS (INVARIATI)`); i fogli parametri ne hanno una propria (`ParamsSheetBase` clamp) — il manifesto generato porta min/max/step.
- **Matching Betfair**: `lib/matching.ts:1` (404 righe, «modello FEDELE del motore di matching di Betfair Exchange») e `trainingLadder.ts` (373) servono la UI di replay; non ho verificato se duplicano `flumine` (il banco usa la simulazione flumine): voce da controllare, non da dare per sicura.
- Nessuna riscrittura di `betfairlightweight` nel frontend (la UI non parla con Betfair: solo Supabase e canale locale).

---

## 5. PARITA'

### 5.1 Cosa esiste (verificato) — vitest e fotografia

- **vitest**: 365 file / 5.042 casi (regex) / 73.437 righe, per area in 1.1; `npx vitest run` a blocchi, ultimo dichiarato 5.243 verdi, tsc 0 (`CRONOSTORIA.md`, cantiere D replay tennis fase 2); in `package.json` `"test": "vitest run"`, `"build": "tsc && vite build"`.
- **fotografia di parita'** (`src/fotografia/`, 4 file di test 1.030 righe con `supabaseFinto.ts`, 99 file JSON di istantanee, 578 KB): rende l'`<App/>` VERA per ogni pagina elencata in `PAGINE` (30 voci in `fotografia.test.tsx`), in entrambi gli stati dell'interruttore `ui.shell`, con Supabase finto deterministico (`supabaseFinto.ts`), canali locali spenti, orologio fermo al 01/10/2026 10:00 Europe/Rome, e registra nell'ordine del DOM: testi, `data-testid`, comandi (ruolo + nome accessibile + `href`/`disabled`/stato). Regole (`fotografia.test.tsx:1-35`): con `off` identica BYTE PER BYTE alla fase 0 (`snapshot/<pagina>.off.json`, commit `bb2c857` PRIMA di ogni altra modifica, `REFERTO_CLOUD.md` riga 55-56); con `v2` il contenuto delle pagine identico a `off`, il guscio solo dentro elementi `data-shell-chrome` con lista bianca di testid. Aggiornare le fotografie e' una DECISIONE (`FOTOGRAFIA_AGGIORNA=1`), non una correzione. Guardie CSS: `cssGuscio.test.ts`, `cssVeste.test.ts` (tutti i selettori sotto `data-shell="v2"`), `uiDefault.test.ts`.
- **Come fu certificato il guscio**: fase 0 con falsificazione (comportamento vecchio rimesso -> rosso -> ripristino; `REFERTO_CLOUD.md` righe 78-83, 163-173: WebSocket in piu' su Omega, testo fuori dalla cornice marcata, «Prova la nuova grafica» senza `data-shell-chrome` -> tutti rossi); fusione `d488490` con suite intera 314 file / 4.829 test e tsc 0 (`CRONOSTORIA.md` riga 18:51 del 01/10); verifica indipendente del coordinatore: diff dei 55 componenti classificato (256 righe = riga vecchia + classi `ds-v2-*`), 175 selettori tutti sotto `data-shell="v2"`, 0 `:root`, suite 316 file / 4.839 test, scatti Edge di 10 pagine a guscio spento identici (`CRONOSTORIA.md` 02/10 10:30-10:54); 38/38 mutazioni sui minori (13:27). Limite dichiarato: la fotografia usa lo stato «backend vuoto» (`fotografia.test.tsx:21-26`): prova struttura, testi e comandi, NON la resa con dati.

### 5.2 Prove da aggiungere per questa trasformazione (stessa identica cosa)

1. **Fotografia POPOLATA** (nuova): lo stesso meccanismo, con stati veri registrati dei bot (sequenze di `StatoBot` ricavate dalle registrazioni del banco: `registrazioni_banco/`, `_live_raw/`, scenari di `Betfair/stream/backtest/`) e i finti di `anteprima/*Finto.ts` (stesse chiavi e tipi del vero) come fixture; per ogni bot e per ogni stato (fermo, pre-partita, in gioco, errore, riconciliazione, uscita proposta, regolato) DOM vecchio == DOM nuovo (testi, testid, comandi). Numeri che devono coincidere: giornata, P&L, importi, etichette di stato, testi di attivita' per ogni `kind` (golden per `kind`: 62 di Omega, i kind di Mike e Safe).
2. **Parametri**: test «TS allineato» come `test_applica_bot_tutti_2026_10_07.py`; confronto per chiave di default/min/max/passo/scelte contro i valori di oggi (0 differenze misurate per Mike e Omega: E1 316, E2 509). Falsificazione: cambiare un default o un limite nel Python -> rosso.
3. **Stato unico**: per ogni push registrato, `StatoBot` nuovo == proiezione dell'attuale `fetchXState` (periodo ombra con confronto automatico, 6).
4. **Banco a evento**: stesso `Banco` del giro da 19 letture (`useControlRoom.ts:1378`) per la stessa registrazione; nessuna differenza di cifra (giornata, saldo, posizioni aperte/chiuse).
5. **Safe**: golden «valutazione per valutazione» di `safeStrategy.ts` contro i `monitor` pubblicati (E3 riga 395), con `genera_oro_banda_strategia.py` esteso.
6. **Non regressione**: `npx vitest run`, `npx tsc -p tsconfig.app.json --noEmit` a 0 errori (CLAUDE.md), nessun `@ts-ignore`/`any` per zittire; fotografie esistenti invariate (0 righe tolte).

Voci di `PROCESSO_STANDARD_BOT.md` coperte: §6.5 «Persistenza e UI (cio' che il trader vede)» (campi chiesto/abbinato/residuo/prezzo medio/stato mostrati, attivita' `kind` per ogni decisione); §6.7 «Scenari e falsificazione» (ogni prova nuova va vista rossa); §6.8 «Referto e riproducibilita'» (fotografie e golden versionati); §7.27 (finti con chiavi/tipi diversi dal vero: i finti di `anteprima/` e `supabaseFinto.ts` devono derivare dal tipo generato), §7.28-7.30 e §7.35 (test che asserisce il sbagliato, passa a vuoto, mutazione non colta, test mai visto rosso: falsificazione obbligatoria), §7.33 (costante nel frontend che duplica una scelta del backend: e' il difetto che la generazione dal manifesto elimina), §7.36 (consapevolezza: la UI non deve mostrare cio' che il bot CREDE diverso da cio' che il conto dice: il confronto `StatoBot` vs ordini del conto resta nel contratto).

---

## 6. MIGRAZIONE

Ordine rispetto agli altri componenti: DOPO il contratto D (Plugin, `catalogo_parametri`, diario) e dopo F (`Giornata`); PRIMA del taglio di Supabase per i dati vivi (G/I). Ogni passo e' uno stato dell'interruttore locale (come `ui.shell`, `lib/uiShell.ts:44`) e si spegne senza ricompilare.

1. **Congelare**: fotografie correnti + NUOVA fotografia popolata (5.2.1) catturate dal codice di oggi PRIMA di toccare (commit a se', come `bb2c857`). Spostare `anteprima/` in `tools/` (nessun cambio all'app) e togliere `mockData.ts`/`FixtureSelector.tsx` (0 importatori; verifica di grep e tsc).
2. **Manifesti generati** (nessun cambio di valore): generatore dal Plugin/registro come `--catalogo-ts`; test «allineato»; periodo OMBRA: il manifesto viene confrontato con `MIKE_PARAM_FIELDS`/`OMEGA_PARAM_*`/`TENNIS_BOT_REGISTRY` esistenti (le differenze oggi sono 0 per Mike e Omega: se compaiono, e' una scoperta, non una correzione). Scalper: la divergenza `one_green_per_phase` si porta all'utente (D-J5), non si risolve da soli.
3. **Fogli parametri dal manifesto**, un bot per volta in ordine di rischio crescente (Mike, tennis, scalper, Omega, Safe) con la fotografia dei fogli (testi, testid, comandi identici); ritorno: file del foglio vecchio ancora presente fino al taglio.
4. **Stato unico**: un adattatore `StatoBot` costruito dai vecchi `fetch*`; le pagine passano a `useBot` una alla volta; in OMBRA i due vengono confrontati a ogni giro (differenza = log, non crash).
5. **Banco a evento**: il nucleo pubblica `banco`; `useBanco` gira in parallelo a `ricarica()` (`useControlRoom.ts:1498`) con confronto automatico; interruttore `ui.banco = nucleo | db`; si spegne il poll 30 s solo dopo N giorni di ombra senza differenze di cifra. Il `ladder` e' gia' push: non cambia.
6. **Contabilita'**: selettori su `Giornata` al posto delle 8 somme (si applica quando F ha pubblicato `Giornata`; F §6 dice «poi il frontend»).
7. **Safe**: solo con D-J1 deciso: UI sui `monitor`, `safeStrategy.ts` in ombra con confronto valutazione per valutazione, poi tolto.
8. **Taglio**: via i vecchi `lib/{mike,safeBot,omega}.ts` gemelli, i fogli a mano, i testi di attivita' duplicati; ultimo, il ripiego Supabase di ladder/ordini (D-J4).

Rischi: (a) le pagine dei bot hanno 2.900-6.900 righe ciascuna con casi limite scritti dopo incidenti (es. `PannelloBot` Safe «strumento, non un bot»; `Mike resting`; `riconciliazione`): il golden per `kind` e per stato li protegge solo se la fixture li contiene; (b) il topic `banco` va sul canale locale: se il nucleo e' giu' la UI oggi si ripiega su Supabase, domani deve mostrare «dato non disponibile» (mai uno stato congelato, come `localTransport.ts:11-14`); (c) l'app desktop la avvia e la riavvia l'utente: ogni build `npm run build` e' sua (CLAUDE.md), mai durante posizioni aperte. Ritorno indietro: interruttori locali per passo + tag git prima di ogni passo (come `pre-guscio-v2-2026-10-01`).

---

## 7. MISURE

| grandezza | oggi (fonte) | domani (obiettivo) | strumento |
|---|---|---|---|
| righe codice non test | 125.573 (+11.099 generate) (`00` §1.5) | ~113.600 (senza decisioni), ~111.100 (con D-J1..J3) | `git ls-files` + `wc -l`, `misura_frontend_J.py` |
| copie di un parametro da tenere allineate | Mike 3 (Py, TS, catalogo replay), Omega 5 (4 a mano + catalogo), Safe 4-6, scalper 3 con valori diversi (E1-E5) | 1 (il Plugin) | `J_gemelli_lib.py` + test «allineato» |
| somme di P&L nel client | 8 (F) | 0 | `grep` delle somme in `contabilita/` |
| `setInterval` che rileggono dati | 49 su 73 (24 orologi grafici) (`polling.tsv`) | solo archivio a richiesta + riconnessione | `J_test_e_polling.py polling` |
| letture REST a Control Room ferma | >= 38/min dalle sole costanti (`useControlRoom.ts:210,1378-1401`) + freno/ordini reali: **NON misurato dal browser** | 0 (push `banco`); archivio solo su azione | log REST dell'app 5 minuti (net-log Electron o API logs Supabase): da scrivere |
| righe trade lette per giro | 2.000 (`fetchOmegaTrades(2000)`) ogni 30 s | 0 (delta) | stesso log |
| latenza clic -> stato visibile | esiti per poll 1,5 s (`:3276`) e 2 s (`:3774`) o realtime con debounce 1,2-1,5 s: NM | un solo evento dal nucleo | marca temporale dal clic all'evento `bot:<id>` (da scrivere, nel banco jsdom con `Nucleo` finto) |
| latenza push ladder | 200 ms di pubblicazione + trasporto locale (A riga 150): NM lato browser | <= 1 intervallo di conflazione (A riga 606) | `a_latenza_ladder.py` (A) |
| memoria/CPU del renderer | NM | non peggiorare | `performance.memory`/Task Manager di Electron: da misurare |
| bundle | `dist/assets` 3.530.025 B (build delle 14:24, `CRONOSTORIA.md` riga «build del frontend aggiornato (14:24, `dist/assets` 3.530.025 B») | <= oggi | `npm run build` (non eseguito qui) |
| test | 365 file / 5.042 casi, 0 rossi | stessi + parita' popolata + contratto per bot | `npx vitest run` |

---

## DECISIONI PER L'UTENTE

- **D-J1 (Safe nel browser)**: eliminare `lib/safeStrategy.ts` (1.731 righe) facendo pubblicare le valutazioni al bot/scanner. Effetto VISIBILE: la UI non valuta piu' da sola i segnali, quindi a bot fermo e senza scanner i segnali non si ricalcolano (E3 riga 432). Le regole non cambiano. Serve il suo OK.
- **D-J2 (guscio v2)**: se la nuova grafica diventa definitiva si toglie l'albero di rotte doppio (`App.tsx:110-296`) e l'interruttore; finche' resta «prova» si tengono entrambi.
- **D-J3 (`ParamsSheet.tsx`, 348 righe)**: fallback per un DB senza `safe_strategy_bot_v2.sql`; se la migrazione e' applicata ovunque si puo' togliere (E3-052).
- **D-J4 (browser senza app desktop)**: il ripiego su Supabase realtime di ladder/ordini (`localTransport.ts` 580 righe, `subscribeLiveLadder` `live.ts:632`) serve solo se l'interfaccia si usa fuori dall'exe. Mantenerlo o dichiarare «solo desktop»?
- **D-J5 (scalper)**: la UI manda `one_green_per_phase: true` (`scalper.ts:117`) mentre ctor e `VALIDATED_PARAMS` dicono `False` (E4 §3.4): nel catalogo unico serve UN valore. Non lo cambio: e' strategia.
- **D-J6**: `anteprima/` (4.651 righe) fuori da `src/` in `tools/` e riusata come fixture di parita': conferma.

## COSA HO VERIFICATO DI PERSONA / COSA NON HO POTUTO VERIFICARE

Verificato rileggendo il codice o misurando: i numeri di 1.1 (script `J_test_e_polling.py test`, `git ls-files`), tutte le righe di `polling.tsv` citate, le 19 letture del giro della Control Room (`useControlRoom.ts:1378-1401`), i 67 RPC di scrittura e la scrittura diretta unica su `leads` (`accessi.tsv`, `grep` di `.insert/.update` nei file non test), l'assenza di `useQuery`/`refetchInterval` (`grep`), il `localLadderSource` (`localTransport.ts:120-175`), le intestazioni di `replayBotCatalogo.ts` e di `anteprima/tennisFinto.ts`, i blocchi gemelli di `mike.ts`/`safeBot.ts`/`omega.ts` (`J_gemelli_lib.py`, lunghezza = distanza fra dichiarazioni a colonna 0, quindi commenti inclusi), l'esistenza di `ParamsSheetBase` e dei 4 fogli che lo usano (`grep -ln`), l'assenza di importatori di `mockData.ts` e `FixtureSelector.tsx` (`git grep`), le righe di dichiarazione dei componenti (ciclo `grep -nE "^export (default )?(function|const) <NomeFile>"`). I numeri delle schede E1-E5, F, A, D sono ripresi dalle schede (non rifatti) e citati per riga.

NON verificato:
1. Il carico REST DAL BROWSER verso Supabase (nessuna misura esiste; solo l'aritmetica delle costanti).
2. Le stime marcate IPOTESI: 70 % dei testi di attivita' generabili (880 righe), 25 % di `useControlRoom.ts` sostituibile (1.080 righe), -100 righe di caricamento in `Omega.tsx`, `lib/uiShell.ts` righe non misurate. Le altre voci sono differenze fra file misurati o stime delle altre schede.
3. L'elenco a livello di singolo pulsante/testo: le 101 voci raggruppano i pannelli con `file:riga` della dichiarazione, ma non ho riletto riga per riga tutti i 394 file; il dettaglio completo di testi e comandi e' nei 5 documenti `inventario_parti/*.md` del 01/10 e in `ancore.tsv`: chi trasforma un pannello deve rileggerlo prima di toccarlo.
4. Se `lib/matching.ts` duplica la simulazione flumine del banco; la resa a schermo (build non eseguita, vitest/tsc non rieseguiti: il brief vieta build/install/suite); la suite verde 5.243 e' quella dichiarata dalla cronostoria, non rieseguita.
5. Il tetto di 55 chiamate di strumenti e' stato superato di poche chiamate per completare la scheda (strumenti e uscite in `strumenti/dati_J/` consentono di rifare ogni numero).

