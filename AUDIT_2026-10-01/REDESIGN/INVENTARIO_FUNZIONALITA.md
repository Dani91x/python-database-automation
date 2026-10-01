# Inventario delle funzionalità in produzione (01/10/2026)

Sola lettura del codice `frontend/src` (nessun file del progetto modificato). Questo file è l'indice: il dettaglio
blocco per blocco, con i testi esatti, i comandi, gli stati, le fonti dati e i `data-testid`, è nelle cinque parti
scritte dai delegati e rilette dal coordinatore del lavoro:

| Parte | File | Pagine coperte |
|---|---|---|
| A | `inventario_parti/A_CONTROL_ROOM.md` | `/control-room` e tutti i componenti `components/controlroom/**` |
| B | `inventario_parti/B_BOT_CALCIO.md` | `/omega`, `/safe-strategy` (calcio + tennis), `/mike`, scalper calcio, componenti `components/trading/*` |
| C | `inventario_parti/C_TENNIS_E_LIVE.md` | `/tennis`, `/tennis/terminal` (4 bot tennis), `/segui-live`, `/multi-ladder`, `/ladder-popout`, `/market-watch`, `/live-pnl`, LadderView/GridView e i 7 pannelli strumento |
| D | `inventario_parti/D_STORICI_ANALISI.md` | `/storico/calcio`, `/storico/tennis`, `/trade-journal`, `/report-personale`, `/watchlist`, `/match-replay`, `/analytics`, `/dashboard` |
| E | `inventario_parti/E_HOME_ACCOUNT_NAV.md` | `/board`, `/select-sport`, `/` (landing), `/check-email`, `/reset-password`, 404, navigazione attuale, app desktop, elenco `lib/*`, 147 RPC e 33 tabelle |

## Design system (estratto da `tailwind.config.js` e `index.css`, da NON cambiare)

| Token | Valore | Uso |
|---|---|---|
| `--background` | `0 0% 0%` | nero puro |
| `--card` | `160 15% 4%` | superfici |
| `--muted` | `160 10% 8%` | fondi secondari |
| `--popover` | `160 15% 3%` | dialoghi |
| `--foreground` | `150 20% 95%` | testo |
| `--muted-foreground` | `155 15% 50%` | testo secondario |
| `--primary` | `155 84% 42%` | verde smeraldo (Omega, azioni, home) |
| `--secondary` | `45 93% 55%` | oro (Safe, obiettivo, target, LTP) |
| `--accent` | `145 72% 50%` | verde chiaro |
| `--destructive` | `0 84% 60%` | rosso |
| `--win / --draw / --loss` | `145 80% 42%` / `45 90% 50%` / `0 80% 55%` | esiti |
| `--glass` / `--glass-border` | `160 15% 10%` / `160 10% 22%` | `glass-card` |
| `--border` / `--input` / `--ring` | `160 10% 18%` / `160 10% 15%` / `155 84% 42%` | bordi, campi |
| `--radius` | `0.75rem` | raggio |

Font: `@import` Google Fonts **Sora** (400/600/700/800) e **Inter** (300-700). `.font-display` e `.font-heading`
sono rimappati su Sora in `index.css` (i nomi Orbitron/Rajdhani in `tailwind.config.js` restano solo come alias).
Colori semantici di `components/trading/DESIGN_SYSTEM.md` §4: BACK `sky`, LAY `rose`, favorevole `emerald`,
sfavorevole `red`, chiusura `teal`, attesa `amber`, liability `orange-400`, obiettivo `secondary`; accenti bot:
Omega `primary`, Safe `secondary`, Mike `teal-300`. Componenti `components/ui/*` (shadcn): accordion, badge,
button, card, checkbox, dialog, form, input, label, progress, sheet, skeleton, sonner, tabs, tooltip.

## Mappa pagine → contenuto → schermata del prototipo

Ogni rotta di `App.tsx` ha una schermata nel prototipo con lo stesso identificativo (`#rotta` nell'URL dell'artefatto).

| Rotta | Sport | Blocchi principali (in ordine) | Fonti dati principali | Prototipo |
|---|---|---|---|---|
| `/board` (prima schermata dell'exe) | calcio + tennis | titolo «Programma di oggi», tab ⚽/🎾 con pallino canale, righe: orario + countdown «OFF in» o IN-PLAY, evento + stato + abbinati, 1X2 / testa a testa back-lay, «Segui live» (tennis: RPC; calcio: link), «Terminal →», Video/Stats; stati canale off / in attesa / vuoto | canali locali 47331/47332 topic `board`; RPC `tennis_follow_event` | `#board` |
| `/control-room` | entrambi | testata (identità, soldi veri, stop perdita, runner, 8 chip bot, feed scanner, ricarica) · ModeBanner · Obiettivo (editor, giornata, composizione, corsia PROVA) + Saldo · riga Storico · Discordanza · tessere sport LIVE/PROVA · Comando dei bot (ordini reali, freno, mercati, BOT CALCIO / BOT TENNIS) · Uscite da approvare · Errore comando · Mike resting · Errore fonti · Banco [Pre-match / Live / Posizioni aperte / Posizioni chiuse | Uscite — decidi tu | Opportunità di modello] · Diagnostica «Da Betfair al tuo schermo» · piè | `useControlRoom` (19 letture ogni 30 s + realtime), canali 47331-47338, `betfair_live_account`, ecc. (A §3) | `#control-room` |
| `/dashboard` | calcio | lista Partite del Giorno (Match Betfair, filtro campionato, accordion, Watchlist) · dettaglio: HeroMatch, 7 pannelli (Frequenze, Ritardi, Poisson, Tactical, ML, Direzione, Quote Betfair), PredictionsCard, 2 TeamPanel, Confronto, H2H | `fixture_predictions`, RPC `get_betfair_*`, `get_direction*`, `get_market_*` | `#dashboard` |
| `/omega` | calcio | BotHeader · ModeBanner · Giornata operativa · Partite chiuse da te · 4 KPI · altra modalità · tab Automatico / Missione / Manuale / Storico · foglio Parametri Omega (10 gruppi) | `get_omega_state`, `get_omega_trades`, missioni, canale 47334 | `#omega` |
| `/safe-strategy` | calcio + tennis | BotHeader · ModeBanner · modalità divergente · SOLDI VERI · Strategie di Safe · esecuzione · Giornata · 8 KPI + Rischio giornaliero · altra modalità · tab ⚽ Calcio / 🎾 Tennis (Segnali, Opportunità, Monitor, Trade) / Storico · Attività · chip strategie | `get_safe_*`, scanner `safe_strategy_scan/status`, `safe_strategy_opportunities` | `#safe-strategy` |
| `/mike` | calcio | BotHeader · ModeBanner · allarmi · Giornata · 7 KPI · tab Partite (Pre-match, Live, Da sistemare; scheda a 11 zone) / Operazioni / Risultati Pre-Match / Risultati Live / Attività / Storico · Cash out e Chiudi a mercato | `get_mike_state`, `get_mike_trades`, canale 47333 | `#mike` |
| scalper calcio | calcio | nessuna pagina propria: riga Scalp in Omega/Missione, strumento Scalper in Segui live, HabitatCard, riga Scalper calcio in Control Room | `get_scalper_state`, `get_scalper_control_room`, canale 47338 | dentro `#segui-live`, `#omega`, `#control-room` |
| `/segui-live` | calcio | lista seguite + HabitatCard · terminal: top bar (modalità, LOCALE, orologio, P&L giornata, saldo, runner, esposizione, overround, cash-out mercato/evento, KILL) · banner rischio gol · tab mercati · rail posizioni/ordini · ladder/grid · 7 strumenti · Controlli runner · tabellone · segnali | `get_live_follows`, `live_now`, `live_ladder`, canale 47331, `betfair_live_*` | `#segui-live` |
| `/tennis` | tennis | Partite del Giorno (Ieri/Oggi/Domani, accordion tornei, preferiti, quote, Volume, APRI TERMINAL) | `get_tennis_fixtures`, `tennis_markets` | `#tennis` |
| `/tennis/terminal` | tennis | header match (punteggio, modalità runner, SEGUI, REC) · Bot Tennis (4 card con parametri reali, arma/disarma) + equity + attività · ladder tennis · Stats / Chart / Depth | `tennis_live_now`, `get_tennis_bots_state`, canale 47332/47337 | `#tennis-terminal` |
| `/multi-ladder` | entrambi | fino a 8 ladder affiancati, picker eventi/mercati | `get_live_follows`, `live_now` | `#multi-ladder` |
| `/ladder-popout` | entrambi | finestra 560×860 con un solo ladder | come StandaloneLadder | `#ladder-popout` |
| `/market-watch` | entrambi (sezioni separate) | righe per evento: stato, MTM live/prova, Rischio live/prova, Cash-out EVENTO (solo calcio), Apri terminal | `get_live_positions_event`, `get_tennis_live_positions_all` | `#market-watch` |
| `/live-pnl` | entrambi | Giorno + Mode (mai «tutte») · 4 KPI · Equity intraday · Per mercato / Per evento · Tennis posizioni aperte | `get_live_settled`, `betfair_live_risk_state` | `#live-pnl` |
| `/storico/calcio`, `/storico/tennis` | uno per pagina | testata con SOLDI VERI / PROVA esclusivo · filtri periodo/soldi/bot · 5 KPI · altra modalità non sommata · non separabile (Omega) · Per bot · Non compaiono · equity · barre · calendario · operazioni del giorno | `get_*_daily`, `get_*_day_trades`, `get_storico_stake` | `#storico-calcio`, `#storico-tennis` |
| `/trade-journal` | calcio | filtri (mode tutte/paper/live, azione, origine, tag, solo oggi) · tabella con tag/nota modificabili · statistiche per pattern | `get_live_journal`, `get_live_settled`, `set_live_journal_note` | `#trade-journal` |
| `/report-personale` | calcio | filtri · cassa · 6 KPI · equity · underwater · 18 metriche · consigli · calendario · per strategia/lega · Trade (17 colonne) · dialoghi Chiudi trade / Svuota / Inserisci operazione | `get_personal_report`, `get_personal_trades`, `get_cash_movements` | `#report-personale` |
| `/watchlist` | calcio | tab Da valutare / Giocate / Scartate · card con azioni (statistiche, quote, Segui live, ordini piazzati, snapshot) · dialoghi Scarta, Elimina, Scheda Trade, Scheda Trade multipla (ordini REALI con cap) | `get_watchlist`, `request_betfair_order`, `get_betfair_orders` | `#watchlist` |
| `/match-replay` | calcio | selettore replay per lega/anno · simulatore: Overall Position, partita, controlli + velocità + timeline, tab mercati, Opportunità, Ladder TRAINING, Backtest | `list_replays`, `get_replay_meta`, `get_replay_frames` | `#match-replay` |
| `/analytics` | calcio | 5 tab: Performance Motori, Decisioni, Crea Strategia, Reportistiche, Backtest Automatico | `get_analytics*`, `get_decisions*`, `backtest_strategy`, `request_backtest` | `#analytics` |
| `/select-sport` | — | 5 card (Football, Tennis, Omega, Safe Strategy, Mike), CONTROL ROOM, Esci | auth | `#select-sport` |
| `/` landing | — | Hero, Stats, Protocollo Alpha, Perché, Dashboard preview, Pricing, Registrati/Accedi, footer | `leads`, auth | `#landing` |
| `/check-email`, `/reset-password`, `*` | — | pagine di servizio (reset con 3 stati) | auth | `#check-email`, `#reset-password`, `#notfound` |

## Fatti rilevati durante l'inventario (da portare all'utente, NON corretti)

1. Nessun link dell'app porta a `/board`: il Programma del giorno si vede solo all'avvio dell'exe; dopo il login si
   va a `/select-sport` (E §1.1). Il redesign lo rende raggiungibile dalla sidebar.
2. Sette stili di testata diversi e tre «home» (brand → `/dashboard`, `/select-sport`, `/tennis`) (E §3.4).
3. PAPER ha tre colori diversi nei pannelli live (ambra, azzurro, verde) (C §12); il prototipo usa un solo colore
   per PAPER (verde, come ModeBanner e ModeToggle).
4. Il rosa di LAY è `rose` in alcuni componenti e `pink` in altri (A §5.2).
5. `ScalperPanel.tsx` contiene caratteri a doppia codifica (mojibake) nel sorgente (B §6, C §12).
6. `DESIGN_SYSTEM.md` è in ritardo sui tab di Omega e Mike (B, avvertenza iniziale).
7. Il Trade journal permette il filtro «tutte» che mette paper e live nella stessa vista statistica (D §2).
8. `FixtureSelector.tsx` non è montato da nessuna pagina (D §9).
