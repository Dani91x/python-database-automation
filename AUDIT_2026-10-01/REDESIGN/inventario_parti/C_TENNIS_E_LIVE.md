# INVENTARIO C — TENNIS e LIVE / LADDER (sola lettura, 01/10/2026)

Fonte: lettura integrale dei file sotto `frontend/src/` (pagine, `components/tennis/*`, `components/live/*`, `lib/tennis.ts`, `lib/localTransport.ts`, `lib/workspace.ts`, `lib/multiLadder.ts`). Niente e' stato eseguito, nessun file del progetto modificato. Le etichette sono copiate TESTUALMENTE dal sorgente (maiuscole, punteggiatura, simboli). Dove il testo e' un tooltip (`title=`) lo si dice. Cio' che non ho potuto verificare e' in fondo (sezione 12).

Convenzioni usate qui sotto:
- "sky" = azzurro (BACK), "rose/pink" = rosa (LAY), "amber" = oro/ambra (selezione attiva, LTP, stake, PAPER/avviso), "emerald" = verde (OK, in corso, profitto), "red" = rosso (LIVE, errore, perdita), "violet/purple" = viola (cash-out, P&L per livello, fair/EV).
- Tema globale (index.css): sfondo nero `--background: 0 0% 0%`, `--primary` verde smeraldo `155 84% 42%`, `--secondary` oro `45 93% 55%`, `--foreground 150 20% 95%`, `--muted-foreground 155 15% 50%`. Font: `font-display` = Orbitron (titoli/brand), `font-heading` = Rajdhani, `font-sans` = Inter. Classi custom: `glass-card` (card vetro con bordo e gradiente verde tenue), `grid-pattern` (griglia di sfondo fissa a opacita' 20-30%).
- Brand nella barra: "AI TERMINAL" = `AI ` + `<span text-primary>TERMINAL</span>` (font-display black, tracking-tighter).
- Lingua UI: italiano. `<title>` delle pagine: "Tennis · Partite del Giorno | Alpha Score", "{p1} vs {p2} · Terminal Tennis | Alpha Score", "Segui Live | Alpha Score", "Market Watch | Alpha Score", "P&L di giornata | Alpha Score", "Multi-ladder", "Ladder · {marketName}".

## 0. MAPPA ROTTE (App.tsx, tutte dentro `<ProtectedRoute>`)

| Rotta | Componente | Sport | Note |
|---|---|---|---|
| `/tennis` | `TennisDashboard` | tennis | Partite del Giorno |
| `/tennis/terminal?event=&market=&name=&p1=&p2=[&from=control-room]` | `TennisTerminal` | tennis | terminal a 3 colonne |
| `/segui-live[?event=<id>&from=omega\|control-room]` | `SeguiLive` | calcio | lista partite seguite + terminal |
| `/multi-ladder` | `MultiLadder` | calcio+tennis | N ladder affiancati |
| `/ladder-popout?sport=&market=&event=&name=&eventName=&p1=&p2=` | `LadderPopout` | calcio/tennis | finestra 560x860 |
| `/market-watch` | `MarketWatch` | calcio + tennis (due sezioni) | |
| `/live-pnl` | `LivePnl` | calcio (settled) + tennis (solo posizioni) | |
| `/board`, `/trade-journal`, `/match-replay`, `/control-room`, `/omega`, `/dashboard` | altre pagine | fuori perimetro, ma linkate da SeguiLive/Terminal |

I 4 BOT TENNIS si comandano (accendere/spegnere come SERVIZIO, parametri, modalita') dalla **Control Room** (`PannelloBot`, gruppo "BOT TENNIS (4)"); si armano PER EVENTO dal **pannello bot della colonna sinistra del Terminal Tennis** (`TennisBotPanel`). Vedi sezioni 1.4 e 1.9.

---

# PARTE I — TENNIS

## 1. TennisDashboard (`pages/TennisDashboard.tsx`, 28 righe) — `/tennis`

**Scopo**: "SCREEN 2 — Tennis: Partite del Giorno". Match del giorno da Betfair Exchange (eventTypeId=2), raggruppati per torneo in accordion, ordinati per orario, quote moneyline P1/P2 back/lay, volume matchato, stato pre-match/in corso, stella preferiti.
**Sport**: tennis. **Nessuna logica propria**: monta `TennisNav` + `TennisMatchesList`.

**Struttura (ordine di render)**
1. Contenitore `min-h-screen bg-background relative pb-24`, overlay fisso `grid-pattern opacity-30` (pointer-events-none).
2. `<TennisNav sectionLabel="TENNIS" />` (sticky top).
3. `<main class="container mx-auto px-4 lg:px-6 py-8 max-w-7xl">` -> `<TennisMatchesList />` (a sua volta `max-w-5xl mx-auto px-4`).
4. Footer: bordo alto, centrato, `© {anno} Alpha Score AI. All rights reserved.`

### 1.1 TennisNav (`components/tennis/TennisNav.tsx`) — barra condivisa Tennis (dashboard e terminal)
`<nav role="navigation" aria-label="Tennis navigation">` sticky `top-0 z-50`, `bg-black/50 backdrop-blur-xl border-b border-white/5`, contenitore `h-16 px-6` diviso sinistra/destra.

Sinistra:
- Brand cliccabile "AI **TERMINAL**" -> naviga a `/tennis`.
- (md+) `sectionLabel` (default "TENNIS"; sul terminal "TERMINAL") con icona `Activity`, maiuscolo, colore `primary/80`.
- Se `onBack` presente (solo sul terminal): bottone outline (md+) con `ChevronLeft` + `backLabel` (default "Torna alle partite"; da Control Room: "Torna alla Control Room").

Destra (tutti `Button variant=outline size=sm`, solo icona sotto md, testo da md):
| Etichetta | aria-label | Icona | Colore | Destinazione |
|---|---|---|---|---|
| Cambia sport | "Cambia sport" | LayoutGrid | secondary (oro) | `/select-sport` |
| Watchlist | "Watchlist" | Bookmark | amber-300 | `/watchlist` |
| Report | "Report Personale" | Wallet | primary | `/report-personale` |
| Analytics | "Analytics" | BarChart3 | primary | `/analytics` |
Poi (lg+) l'email utente (`useAuth().user.email`, testo xs muted) e il bottone ghost "Esci" (icona LogOut, hover rosso) -> `supabase.auth.signOut()` poi `navigate('/')`.

### 1.2 TennisMatchesList (`components/tennis/TennisMatchesList.tsx`, 501 righe)
**Fonte dati**: RPC `get_tennis_fixtures(p_date)` (via `fetchTennisFixtures`) + realtime `postgres_changes` su tabella `tennis_markets` (`subscribeTennisMarkets`, ricarica silenziosa con debounce 500 ms, la lista gia' mostrata NON si azzera su errore). Preferiti: `localStorage['tennis.favorites']` (Set di event_id, nessun backend).

Blocchi in ordine:
1. **Header** (flex colonna su mobile / riga md):
   - `h1` "Partite del Giorno" + `.` verde (`text-primary`) (font-display black 2xl/4xl).
   - sotto: "Tennis · {dateLabel}" dove dateLabel = `toLocaleDateString('it-IT', {weekday:'long', day:'numeric', month:'long'})` (capitalize).
   - a destra: **selettore data** a pillole in `bg-black/40 border-white/10 rounded-xl`: **"Ieri" / "Oggi" / "Domani"** (attivo `bg-primary/20 text-primary`; default Oggi); badge (md+) "{rows.length} Match".
2. **Stati**:
   - *Loading*: 3 card scheletro (`Skeleton`): icona torneo 40px + 2 righe + 2 righe-partita con scheletri.
   - *Errore*: card rossa (`border-red-500/30 bg-red-500/5`) icona `Activity` rossa, titolo "Errore di caricamento", testo errore in mono rosso.
   - *Vuoto*: icona `Trophy` grande opaca, titolo "Nessun match di tennis", testo "Non ci sono partite di tennis per {ieri|oggi|domani}. Prova un altro giorno."
3. **Accordion multiplo** (controllato; al cambio dati si apre solo il PRIMO gruppo). Gruppi = `competition_name` (fallback "Altri tornei"; chiave `competition_id::name`), ordinati alfabeticamente (locale it), dentro il gruppo per `open_date` crescente. Animazione framer-motion (opacity/y, stagger 0.05 s per gruppo).
   - **Trigger del gruppo** (card vetro, rounded-xl, aperto = bordo `primary/30` e rounded-b-none): quadratino 40px con icona `Trophy` (primary/60); colonna con nome torneo (bold, 1 riga) e sotto, in maiuscolo piccolissimo: `{competition_region + ' · ' se presente}{count} partita|partite`; a destra `Badge` secondary `primary/10` con il numero.
   - **Contenuto**: per ogni partita una riga `p-3 md:p-4 rounded-lg bg-white/5 border-white/5 hover:bg-white/10`:
     a) **Sinistra (shrink-0)**: bottone **stella** (aria-label "Aggiungi ai preferiti" / "Rimuovi dai preferiti"; `aria-pressed`; piena `amber-300 fill` se preferito, altrimenti muted); riquadro 48px con icona `Clock` e orario `HH:mm` (it-IT, "--:--" se non valido); **StatusBadge**: se `inplay` -> pillola verde `IN CORSO` con puntino pulsante (ping), altrimenti pillola grigia `PRE-MATCH`.
     b) **Centro**: `{nome P1 (right-aligned, "Giocatore 1" fallback)}` + `PlayerOdds` + `VS` + `PlayerOdds` + `{nome P2 ("Giocatore 2")}`. `PlayerOdds` = 2 celle prezzo 54x44: **BACK** `bg-sky-500/15 border-sky-500/30 text-sky-300`, **LAY** `bg-rose-500/15 border-rose-500/30 text-rose-300`; ciascuna mostra prezzo `toFixed(2)` mono bold + sotto la size abbreviata (`€{n}` o `€{x.x}k` da 1000); se manca: `—` su sfondo spento. Si usa il PRIMO livello (best) di `back[]`/`lay[]`.
     c) **Destra**: "Volume" (label maiuscola xs) + valore ambra mono (`€{x}` / `€{x.x}k` / `—`) = `total_matched`; bottone **"APRI TERMINAL"** (primary, icona `ArrowRight`; sotto sm solo freccia) -> `/tennis/terminal?event={event_id}&market={market_id}&name=Match%20Odds&p1={enc}&p2={enc}`.
     d) **Sotto-riga** (bordo sopra): "{n} mercati" (`markets.length`), "evt {event_id}", "mkt {market_id}" (mono xs), a destra `BetfairMediaButtons compact eventId` (vedi 1.5).

Dato in ingresso per riga (`TennisFixtureRow`): event_id, market_id (Match Odds), competition_id/name/region, open_date ISO, inplay, status (OPEN|SUSPENDED|CLOSED), player1/player2 {selection_id,name,sort_priority,back[],lay[],ltp}, total_matched, markets[] {market_id,market_type,market_name,total_matched}, captured_at.

### 1.3 TennisTerminal (`pages/TennisTerminal.tsx`, 304 righe) — `/tennis/terminal`
**Scopo**: "SCREEN 3 — Tennis Trading Terminal (fullscreen, 3 colonne)". SINISTRA bot (tutti armabili in contemporanea) + equity; CENTRO ladder market-depth + ordini manuali/bot; DESTRA Match Stats / Chart / Depth. Dati SOLO da Supabase Realtime su tabelle `tennis_*` (nessuna chiamata a Betfair dal browser) + canale locale `ws://127.0.0.1:47332` quando connesso.

Parametri URL: `event`, `market`, `name` (default "Match Odds"), `p1` (default "Giocatore 1"), `p2` ("Giocatore 2"), `from=control-room` (se presente il bottone indietro porta a `/control-room`, altrimenti `/tennis`).

**Stato "nessun match"** (manca event o market): sfondo+grid, `TennisNav sectionLabel="TERMINAL"`, centrato: "Nessun match selezionato. Torna alle **Partite del Giorno**." (la parola e' un link-bottone sottolineato primary verso `/tennis`).

**Struttura (ordine di render)**
1. Overlay `grid-pattern opacity-20`.
2. `TennisNav sectionLabel="TERMINAL"` con `onBack` (label "Torna alle partite" oppure "Torna alla Control Room").
3. **Header match compatto** — sticky `top-16 z-40`, `bg-black/40 backdrop-blur-xl`, altezza `h-12`, riga flex gap-3 text-sm, nell'ordine:
   - `{p1} vs {p2}` (display black, il "vs" in `text-white/30`).
   - `· {marketName}` (mono xs muted).
   - **Punteggio live** (solo se `inplay` e c'e' `set_summary`): `{set_summary}` + (se punti) ` · {p1}–{p2}` verde `emerald-300` mono black (title "Punteggio set (tennis_live_now) · game: p1–p2").
   - **Countdown** (solo se NON inplay e `open_date` noto): `OFF in {countdown}` ambra `amber-300` (title "Countdown all'inizio del match (open_date)").
   - **Badge modalita' ordini del runner** (`state.order_mode`, default OFF):
     * `LIVE · REALE` = `bg-red-500 text-white` (title "Runner in LIVE: gli ordini sono REALI (soldi veri).")
     * `PAPER · SIMULATO` = `bg-amber-500 text-black` (title "Runner in PAPER: ordini SIMULATI, visibili sul ladder come dal vivo.")
     * `ORDINI OFF` = `bg-slate-700 text-slate-300` (title "Runner ordini SPENTO: nessun ordine possibile, nemmeno simulato. Imposta TENNIS_LIVE_ORDER_MODE=PAPER e riavvia il runner tennis.")
   - **Segui**: se `seguita===true` (follow PENDING/STREAMING) pillola `SEGUITA` (`bg-emerald-700`, title "Partita seguita dal runner tennis: ladder e punteggio in arrivo."). Altrimenti bottone `SEGUI` (`bg-sky-700 hover:bg-sky-600`; mentre in corso `SEGUI…` e opaco/cursor-wait; title "Segui questa partita: il runner tennis apre lo stream e pubblica ladder e punteggio."). Se `seguita===false` e nessun errore: testo ambra mono "partita non seguita: premi «Segui» per ladder e punteggio". Se errore: "SEGUI KO" rosso (title = messaggio).
   - **Toggle REC** (registrazione per-partita): bottone `aria-pressed`, `REC` (sfondo `slate-800`, puntino rosso) / `REC ON` (`bg-red-600` puntino bianco pulsante) / `REC…` durante la chiamata; title: errore / "Registrazione ATTIVA: il runner salva il raw nativo (.raw.jsonl + .score.jsonl) di questa partita. Clic per fermare." / "Registra questa partita: raw nativo su file per backtest/lab (scelta per-partita). Clic per avviare." Accanto "REC KO" rosso se errore. Il runner rilegge il flag ogni ~5 s.
   - A destra (`ml-auto`): `BetfairMediaButtons compact` + "event {eventId} · market {marketId}" (mono 10px muted).
4. **Griglia 3 colonne**: `grid grid-cols-1 xl:grid-cols-[340px_minmax(0,1fr)_360px] gap-3 items-start` (sotto xl impilate), `px-3 lg:px-4 py-3`:
   - **Sinistra 340px**: `TennisBotPanel` (sez. 1.4).
   - **Centro fluido**: `TennisLadderColumn` (sez. 1.6).
   - **Destra 360px** (`space-y-2`): barra tab `Stats` | `Chart` | `Depth` (bottoni con `aria-pressed`; attivo = bordo sotto `amber-400`, testo bianco, `bg-white/[0.06]`) e sotto il pannello attivo:
     * `Stats` -> `TennisMatchStats` (sez. 1.7)
     * `Chart` -> `SelectionChartPanel` (marketId, `ladderSource=sorgenteLadderAlMs('tennis')`, **bucket default 5 s**)
     * `Depth` -> `DepthPanel` (marketId, stessa sorgente)
   - Ogni colonna ha `key` = `{bot|ladder|stats}:{eventId}:{marketId}` (rimontaggio pulito al cambio partita).

**Fonti dati**: `fetchTennisNow(eventId)` (SELECT `tennis_live_now` per event_id) + `subscribeTennisNow` (realtime su `tennis_live_now`, filtro event_id); `fetchTennisFollows()` -> RPC `get_tennis_follows` (da cui `open_date`, `record`, `status`); RPC `tennis_follow_event(p_event_id,p_market_id)`; RPC `tennis_set_follow_record(p_event_id,p_record)`.

### 1.4 TennisBotPanel (`components/tennis/TennisBotPanel.tsx`, 655 righe) — colonna sinistra
**Scopo**: elenca i 4 bot tennis del registro `TENNIS_BOT_REGISTRY`. Ogni bot = card INDIPENDENTE armabile/disarmabile per l'evento corrente; piu' bot armati insieme sullo stesso evento. Sotto le card: equity chart aggregata + feed attivita'.

**I 4 BOT TENNIS (nomi esatti, chiavi, fase, accento, stake di default)**
| key | name (UI) | etichetta fase | accento | Stake default | breve (testo `short`) |
|---|---|---|---|---|---|
| `tennis_scalper` | **Tennis Scalper** | `pre + in-play` (phase `both`) | `primary` (verde) | 5 | "Missione tick pre-match: 1 tick di profitto prima del via, poi stop. Maker micro-scalp sul favorito (gamba in-play OFF: bocciata dal backtest di validazione)." |
| `tennis_pro` | **Tennis Pro** | `in-play` | `secondary` (oro) | 5 | "Direzionale score-driven: break point, serving-for-set, doppio break, favorito compresso." |
| `tennis_flb` | **Tennis FLB** | `in-play` | `cyan` | 5 | "Lay del favorito estremo (favourite-longshot bias), liability minima, exit green/hold/hybrid." |
| `tennis_swing` | **Tennis Swing** | `in-play` | `magenta` (fuchsia) | 5 | "Maker fade degli estremi del favorito: z-score robusto + Efficiency-Ratio + RSI." |
Nella Control Room gli stessi 4 si chiamano `BOT_LABEL`: "Scalper", "Pro", "FLB", "Swing" (etichetta interruttore: "Scalper tennis", "Pro tennis", "FLB tennis", "Swing tennis"), sigle scheda partita: Sc / Pr / Fl / Sw, colori testo amber-300 / amber-200 / orange-300 / yellow-300.

**PARAMETRI per bot (etichetta, step, min, max, default, hint tooltip)** — i campi `select` con `bool` sono inviati come booleano ('on'->true).
- **Tennis Scalper** (default = preset live `TENNIS_PARAMS` del runner; la UI vince sul setdefault del runner):
  - `scalp_ticks` "Tick profitto" step1 min1 max5 def **1** — "target chiusura per ciclo"
  - `stop_ticks` "Tick stop" 1/1/8 def **3** — "tick avversi che innescano lo stop (preset validato: 3)"
  - `signal_ticks` "Tick segnale" 1/1/10 def **1** — "ampiezza deviazione per entrare"
  - `min_flow` "Flusso min €/lato" 1/0/500 def **2** — "gate volume stampato (preset validato: 2)"
  - `min_size` "Size min ai best €" 1/0/2000 def **5** — "liquidità minima sul touch"
  - `price_min` "Quota min" 0.1/1.01/5 def **1.2** — "sotto: code lente"
  - `price_max` "Quota max" 0.1/1.5/20 def **6** — "sopra: tick larghi"
  - `one_tick_per_phase` "Missione 1 tick/fase" select on/off def **on** (bool) — "1 tick di profitto pre-match, poi stop automatico (stato "Concluso"). off = scalping continuo"
  - `inplay_tick_enabled` "Gamba in-play (sperimentale)" select off/on def **off** (bool) — "⚠️ BOCCIATA dal backtest di validazione (1 verde/34 match, coda −13€/ciclo): tenere OFF salvo test su match ultra-liquidi"
  - `runner_filter` "Runner operato" select [`favorite`="solo favorito", `all`="entrambi"] def **favorite** — "favorito = best-back più basso al momento della quotazione; evita la doppia esposizione correlata sui 2 runner"
- **Tennis Pro** (la SUPERFICIE non si sceglie: la decide il runner dal nome del torneo, v. blocco superficie sotto):
  - `bp_target_ticks` "Break: tick target" 1/2/40 def **5** — "obiettivo su break point"
  - `bp_stop_ticks` "Break: tick stop" 1/1/30 def **3** — "stop su break point"
  - `fade_target_ticks` "Fade: tick target" 1/2/40 def **4** — "obiettivo fade over-reaction"
  - `min_matched` "Matched min €" step5000 0/500000 def **50000** — "liquidità minima mercato"
  - `price_max` "Quota max" 0.1/1.1/10 def **3.6** — "non entrare sopra questa quota"
  - `trend` "Trend-following" select on/off def **on** — hint: "FLIPPA i setup di dominio (serving-for-set, doppio break, set transition, favorito compresso) da LAY di reversione a BACK trend-following: cavalca il dominante invece di puntare sul rientro. ACCESO di default (decisione utente 25/09); mai certificato sul banco fuori dall'erba."
  - `adapt` "Direzione adattiva" select on/off def **on** — "sceglie la DIREZIONE dei setup di dominio dal regime di prezzo live (Efficiency Ratio di Kaufman): trend -> BACK del dominante, range -> LAY, regime neutro -> nessun ingresso. Con on ignora il flag trend. " + stessa coda "ACCESO di default (decisione utente 25/09); mai certificato sul banco fuori dall'erba."
  - `maker` "Ingresso maker" select on/off def **on** — "entra passivo a maker_offset tick dal best (fill non garantito). " + stessa coda "ACCESO di default…"
- **Tennis FLB**:
  - `lay_max` "Lay max (quota)" 0.01/1.01/1.5 def **1.1** — "lay solo sotto questa quota"
  - `green_ticks` "Tick green" 1/1/20 def **8** — "green a questo profitto"
  - `green_frac` "Frazione green" 0.1/0.1/1 def **0.5** — "quota di posizione da chiudere"
  - `rearm_mult` "Rearm mult" 0.05/1/2 def **1.1** — "riarmo dopo movimento"
  - `min_matched` "Matched min €" 5000/0/500000 def **10000** — "liquidità minima mercato"
  - `exit_mode` "Uscita" select [`hybrid`,`hold`,`green`] def **hybrid** — "hold = preset col miglior backtest (direzionale, locked può restare <0); hybrid = green parziale"
- **Tennis Swing**:
  - `N` "Finestra N" 5/10/120 def **40** — "lookback tick-index"
  - `zin` "Z ingresso" 0.1/1/4 def **2.0** — "soglia z per entrare"
  - `er_max` "ER max" 0.05/0.1/0.9 def **0.4** — "gate regime (Efficiency Ratio)"
  - `stop_ticks` "Tick stop" 1/2/30 def **8** — "stop di protezione"
  - `tmax` "T max (s)" 10/20/300 def **90** — "time-stop posizione"

**STATI del bot** (`TENNIS_BOT_STATUS_LABEL`; `Badge`):
| status | testo badge | colore |
|---|---|---|
| idle | Inattivo | bianco/10, testo bianco/50 |
| requested | Richiesto | amber-400/20, amber-300 |
| arming | Armamento… | amber |
| armed | Armato | amber |
| running | Operativo | emerald-500/20, emerald-300, puntino pulsante |
| stopping | Arresto… | amber |
| stopped | Fermato | grigio |
| done | Concluso | grigio |
| error | Errore | red-500/20, red-300 |
"Attivo" (mostra DISARMA e blocca i campi) = requested/arming/armed/running/stopping.

**Struttura del pannello (ordine di render)**
1. **Intestazione colonna**: icona `Bot` primary + "**Bot Tennis**" (display black); a destra `Badge` verde "⚡ {n} armat{o|i}" se n>0, altrimenti testo "nessun bot armato".
2. Se caricamento e nessun controllo: riquadro con spinner "Caricamento bot…". Altrimenti le 4 card (`space-y-2.5`) nell'ordine del registro: Scalper, Pro, FLB, Swing.
3. **Card di un bot** (`rounded-xl border bg-white/[0.04] p-3 space-y-3`; se attivo bordo e anello nel colore accento):
   a) **Testata**: puntino colore accento, **nome bot** (display black sm), micro-pillola fase (`pre-match` | `in-play` | `pre + in-play`, maiuscolo, colore accento); sotto la riga `short` (11px, bianco/45). A destra: badge stato; se attivo e `control.dry_run` -> "dry-run" (9px bold maiuscolo ambra); se attivo e c'e' `heartbeat_at` -> "agg. {s}s fa" (mono 9px; **rosso bold** se status running e >30 s).
   b) **Errore del controllo** (se `control.error`): se inizia con `[ATTESA]` -> riquadro AMBRA con icona `Clock` e testo senza prefisso (motivo d'attesa benigno); altrimenti riquadro ROSSO con `AlertTriangle` + testo.
   c) **Solo `tennis_pro`** — riquadro `data-testid="tennis-pro-superficie"`: "superficie: {testo}" dove testo = `{erba|terra|cemento} ({fonte}: {voce})` oppure "{nome} (fonte non dichiarata)" (ROSSO bold); se la riga non l'ha ancora scritta: "superficie: la decide il runner all'armamento, dal nome del torneo" (grigio). Fonte `default` = sfondo ambra. Mappa nomi: grass=erba, clay=terra, hard=cemento. title = "torneo: {torneo}".
   d) **Riga controlli**:
      - "**Stake €**" + input numerico 80px (min 1, max 500, step 1; clamp 1-500; disabilitato se attivo/occupato).
      - Checkbox **"Dry-run (solo log: nessun ordine, nemmeno simulato)"** (testo ambra semibold se spuntato). Disabilitata se attivo, occupato o runner OFF. Default: dry-run ON se runner LIVE/OFF; in PAPER default OFF (cosi' i bot piazzano ordini simulati). Passando a LIVE o OFF il default torna SEMPRE a ON e azzera la scelta; in PAPER la scelta esplicita dell'utente non viene sovrascritta.
      - Avvisi condizionali (se non attivo): `!dryRun && LIVE` -> "ORDINI REALI" (rosso, icona `ShieldAlert`); `!dryRun && PAPER` -> "ORDINI SIMULATI · visibili sul ladder" (ambra, icona `Zap`); `runner OFF` -> "runner OFF: dry-run forzato, nessun ordine possibile" (slate, icona `AlertTriangle`).
   e) **Parametri espandibili**: bottone-riga "▶/▼ Parametri ({n})" a sinistra e (se non attivo) a destra "↺ default" (ripristina i default del registro). Aperto: griglia 2 colonne con per ogni campo: etichetta + icona `Info` (tooltip con `hint`, max 220px) e input numerico (step/min/max, clamp al blur; invalido -> default) oppure `<select>` per i campi a scelta.
   f) **Badge missione "1 tick per fase"** (se `stats.greens_prematch` o `greens_inplay` definiti): due pillole "Tick pre-match ✓|…" e "Tick in-play ✓|…" (verde se >=1, altrimenti grigio).
   g) **Statistiche live** (solo se attivo): griglia 3 colonne di tile con label maiuscola 8px e valore: "Cicli" (`cycles`), "Scalp" (`scalps`+`roundtrips`), "Scratch", "Stop", "P&L bloccato € (lordo)" (2 decimali, accento; title "P&L LORDO: commissione Betfair (4,5-5%) NON detratta"), "P&L settl. € (lordo)" (solo se `pnl_settled` definito; title "P&L LORDO dei soli cicli regolati: commissione NON detratta"), "P&L aperto €".
   h) **Bottone grande ARMA/DISARMA** (w-full, disabilitato se occupato o status stopping): occupato = spinner; attivo = rosso "■ DISARMA"; altrimenti verde "⏻ ARMA (dry-run)" | "ARMA ORDINI REALI" (LIVE, !dry) | "ARMA SIMULATO" (PAPER, !dry).
4. **Equity chart** (`TennisBotEquityChart`, sez. 1.4.1).
5. **Card "Attività"** (icona `Activity` + "Attività"): lista `max-h-44` scroll di righe mono 10px: `{HH:MM:SS}` (it-IT 24h) + **nome bot** (colore accento) + `kind` + `JSON.stringify(payload)`; colore `kind`: rosso bold per `error`/`flusso_interrotto`, verde bold per `cycle`/`scalp`, ambra per `stop`, grigio altrimenti. Vuoto: "Nessuna attività ancora…".

**COMANDI del pannello**
- ARMA: se `!dryRun && orderMode==='LIVE'` -> `window.confirm("⚠️ ARMARE \"{nome bot}\" CON ORDINI REALI?\n\nIl bot piazzerà scommesse REALI su Betfair in autonomia (stake €{stake}).\nConfermi?")`. Poi RPC `tennis_bot_arm(p_event_id,p_bot_key,p_dry_run,p_stake,p_params)`. Toast: "{nome} ARMATO (dry-run · nessun ordine)" | "{nome} ARMATO · ORDINI REALI" | "{nome} ARMATO · SIMULATO (visibile sul ladder)"; errore "Armamento fallito: {msg}".
- DISARMA: RPC `tennis_bot_disarm(p_event_id,p_bot_key)`; toast "{nome}: disarmo richiesto — chiusura flat in corso" con descrizione 'Stato "stopped" quando la posizione è verificata flat; se resta aperta comparirà un errore.'; errore "Disarmo fallito: {msg}". Il runner scrive `stopped` SOLO a flat verificato.
- Anti doppio-click per bot (`inflight` ref).

**Fonti dati del pannello**: RPC `get_tennis_bots_state(p_event_id,p_activity_limit=60)` -> `{controls[], activity[]}`; realtime `postgres_changes` su `tennis_bot_control` e `tennis_bot_activity` (filtro `event_id`) con debounce 200 ms -> ricarica; riconciliazione lenta ogni 30 s; clock 1 s per "agg. Xs fa".

#### 1.4.1 TennisBotEquityChart (`TennisBotEquityChart.tsx`)
Card `rounded-xl border-white/10 bg-white/5 p-3`: testata icona `TrendingUp` (verde/rossa secondo segno) + "**Equity bot (live)**"; a destra (se ci sono campioni) `€{total}` (verde/rosso, mono black) e "bloccato (lordo) **€{locked}**" (title "P&L LORDO: commissione Betfair (4,5-5%) NON detratta"). Grafico `h-40` (Recharts): finche' <2 campioni riquadro tratteggiato "In attesa di operatività dei bot…". Con dati: AreaChart serie `total` (= Σ pnl_locked + pnl_open, verde `#34d399` se >=0 altrimenti rosso `#f87171`, gradiente), linea tratteggiata ambra `locked` (Σ pnl_locked), griglia orizzontale, riga 0 tratteggiata, asse X orario HH:MM:SS, asse Y `€{n}`, tooltip "Equity" / "Bloccato". Serie rolling max 120 campioni (aggiunge un punto solo quando cambia l'aggregato). Dati: `controls[].stats` dal pannello (nessuna query propria).

### 1.5 BetfairMediaButtons (usato in lista, terminal, SeguiLive, popout, multi-ladder, market watch)
Pulsante unico diviso in due meta' (bordo `white/10`, `bg-black/30`, arrotondato): **📺 Video** | **📊 Stats** (compact = solo emoji, `h-6 px-1.5 text-[11px]`; pieno = `📺 Video` / `📊 Stats`, `h-7 px-2.5 text-xs`). aria-label "Apri video live Betfair" e "Apri statistiche e visualizzazione partita Betfair"; aprono il popup ufficiale Betfair per evento (video = `liveVideo`, stats = `matchStats`). Se `media.video===false`/`viz===false` la meta' e' attenuata (opacity-40) col motivo nel tooltip; se il popup e' bloccato toast "Popup bloccato dal browser" ("Consenti i popup per questo sito per aprire video e statistiche Betfair."). `stopPropagation` sui click.

### 1.6 TennisLadderColumn (`components/tennis/TennisLadderColumn.tsx`) — colonna centrale
Card `glass-card border-white/10 rounded-2xl` flex colonna.
1. **Header** (`bg-white/[0.03]`): icona `Layers` primary + `marketName` (heading bold sm, troncato); a destra micro-pillole 10px bold: se canale locale connesso `⚡ LOCALE` (`bg-emerald-500/20 text-emerald-300`, title "Canale LOCALE attivo (ws://127.0.0.1:47332): ladder e ordini direttamente dal runner tennis sul PC — latenza ~0. Se cade, fallback automatico al DB."); `{p1}` su **sky** (`bg-sky-500/15 text-sky-200`), "vs", `{p2}` su **rose** (`bg-rose-500/15 text-rose-200`).
2. **Banner OFF** (se order_mode OFF): "Ordini OFF — il runner tennis non accetta ordini (nemmeno simulati) e il ladder non mostra ordini/posizioni. Per la DEMO: imposta TENNIS_LIVE_ORDER_MODE=PAPER e riavvia il runner." (slate, bold 10px).
3. **Toggle vista centrale** `Ladder` | `Grid` (aria-pressed; attivo `bg-amber-400 text-black`; title Ladder "Vista ladder classica (colonne prezzo)" / Grid "Vista GRID one-click: righe = selezioni, 3 best back + 3 best lay cliccabili"). Persistito per evento in localStorage via `workspace` (`loadLayout(eventId).centerView`).
4. **Corpo**: `GridView` (sez. 3.2) oppure `LadderView` (sez. 3.1) con: `sport="tennis"`, `orderMode`, `ladderSource=sorgenteLadderAlMs('tennis')`, `orderApi` = locale (se canale connesso) o `TENNIS_ORDER_API`, `enableDragMove`, `fallbackSelections` (dal mercato in `tennis_live_now.state.markets`), `popout={sport:'tennis',eventId,eventName:'{p1} — {p2}',p1,p2}`, `multiSlot={...}`.
5. **Legenda** in fondo (`bg-black/30`, 9px muted, icona `Info`): "Gli ordini in overlay (colonne **B**/**L**) includono sia i tuoi ordini manuali sia quelli dei bot tennis. Trascina un ordine su un altro livello per spostarlo (annulla e ripiazza)." (B in sky, L in rose).

`TENNIS_ORDER_API` (comandi): `send` -> RPC `request_tennis_live_order(p)` + polling `get_tennis_live_order(p_id)` ogni 1 s fino a 90 s (3 tentativi di accodamento con `client_ref` UUID idempotente; su timeout errore "Esito comando tennis non confermato (timeout): NON reinviare, verifica la lista ordini."); `fetchOrders` -> RPC `get_tennis_live_orders(p_market_id,p_mode)`; `fetchPositions` -> RPC `get_tennis_live_positions(p_market_id,p_mode)`; `subscribeOrders/Positions` -> realtime su `tennis_live_orders` / `tennis_live_positions` (filtro market_id); `greenup` -> azione `'greenup'` sulla stessa coda (`fraction`, `targetPrice`, `cancelUnmatched`, validati da `buildGreenupParams`). **Nota**: il tennis NON offre `armRule` ne' `supportsFok` -> nel LadderView la toolbar armata mostra solo "Scala" e "Servants" (niente Entry/Offset/Stop/Chase/FoK). Esiste inoltre l'azione di coda `chiudi_bot` (bot, event_id, market_id, mode, trade_id?) usata dalla Control Room ("CHIUDI ORA" di un bot tennis).

### 1.7 TennisMatchStats (`components/tennis/TennisMatchStats.tsx`, 544 righe) — colonna destra, tab "Stats"
Dati: SELECT `tennis_live_now` per evento + realtime (stesso hook della pagina). `p1` = home (sortPriority 1), `p2` = away. Freschezza: oltre 15 s in-play il dato e' "vecchio" (rosso). Punto-per-punto: ultimi 40, piu' recente in cima.
Blocchi in ordine (colonna `gap-3`):
1. **Header**: icona `TrendingUp` + `Match Stats` (maiuscolo, display black) a sinistra; a destra badge di stato mutuamente esclusivi: `SOSPESO` (outline ambra, se status SUSPENDED) / `IN CORSO` (`primary/15`, puntino ping) / `PRE-MATCH` (outline grigio); piu' `TIE-BREAK` (outline secondary) se tiebreak.
2. **Scoreboard** (Card `bg-white/[0.02]`): riga intestazione colonne (9px maiuscolo): *[spazio]* · **Giocatore** · **Set** · **Set-by-set** (sm+) · **Gm** · **Pt**. Per ogni giocatore (`ScoreRow`): pallino servizio (`Circle`, pieno secondary con glow se serve, altrimenti `white/15`); nome (troncato); **set vinti** grandi (secondary, font-mono black lg); **celle game per-set** (`game_sequence`, il set corrente `bg-primary/20 text-primary ring`, set vinto bianco, perso spento); **game del set corrente**; **punto corrente** (Betfair-style 0/15/30/40/A o numero tie-break; primary se serve). La riga del giocatore in testa (set, poi game) ha `bg-primary/[0.06]`. Sotto: `set_summary` (es. "6-4 3-6 2-1", mono 10px) a sinistra e a destra icona orologio + "agg. {s}s fa" / "agg. {m}m {s}s fa" / "agg. —" (rosso bold se stantio; title "sorgente: {source}").
   *Senza punteggio*: card centrata con P1 / "vs" / P2 e testo "Caricamento punteggio…" | "Errore: {msg}" | "In attesa dei dati punteggio (inizio match)…".
3. **Pressione** (solo se break/set/game point): icona `Zap` ambra + badge `BREAK POINT` (ambra), `SET POINT` (rosso), `GAME POINT` (outline).
4. **Win Probability** (solo se `win_prob_p1` noto): card con titolo maiuscolo "Win Probability" + icona `Trophy`; percentuali `{p1}%` (primary) e `{p2}%` (secondary); barra 2 segmenti (primary | secondary, transizione 500 ms); sotto i due nomi giocatore.
5. **Break servizio** (se c'e' punteggio): "Break servizio" + `{p1} {n}` · `{p2} {n}` (numeri primary/secondary, mono).
6. **Punto per punto** (Card): titolo maiuscolo "Punto per punto" + contatore; lista `max-h-64` scroll; riga `PointRow`: `S{set}·G{game}` (mono 10px), pallino vincitore (primary=P1, secondary=P2), nome vincitore, tag (`BREAK` ambra / `SET` rosso / `GAME` grigio, max 3), `sv{1|2}` (title "servizio"), `score_after` (mono, a destra). Vuoto: "Nessun dettaglio punto-per-punto disponibile".

### 1.8 TennisBotServiceParamsSheet (`components/tennis/TennisBotServiceParamsSheet.tsx`) — foglio parametri del SERVIZIO
Montato dalla **Control Room** (non dal terminal): un foglio per ciascuno dei 4 bot, nella riga del bot (`PannelloBot` -> `parametriRiga`), stesso componente generico `ParamsSheetBase` (Sheet laterale destro, `sm:max-w-md`, scroll).
- Trigger: bottone outline sm con icona `Settings` + testo **"Parametri"** (+ "•" ambra se modifiche non salvate); `data-testid="cr-tennis-params-trigger-{botKey}"` (es. `cr-tennis-params-trigger-tennis_pro`).
- Contenuto (`data-testid="params-sheet"`): titolo `Parametri {nome bot}` (es. "Parametri Tennis Pro"); descrizione "Sono gli STESSI parametri che il bot Python legge per ogni evento che arma (verificati chiave per chiave contro il codice del bot). Salvando qui si cambia il servizio: gli eventi gia' armati li rileggono al giro successivo."; un solo gruppo (`data-testid="params-group"`) intitolato col nome del bot, con nota = testo `short` del bot, e i campi del registro (stesse chiavi/min/max/step/opzioni di 1.4). Piede: se i parametri non sono letti: "parametri non ancora letti dal servizio: qui sotto ci sono i default del registro, non necessariamente quelli in uso." (ambra).
- Test-id dei pulsanti: salva `params-save`, ripristina default `params-reset`, esito `params-esito` (`data-esito=ok|errore`, `role=status`), avviso clamp `params-clamped`, avviso modifiche `params-dirty`, scelte `params-choice`.
- Salvataggio: RPC `tennis_bot_service_update_params(p_bot_key,p_mode=null,p_stake=null,p_params=<intera colonna>)` partendo SEMPRE dai parametri correnti (non perde chiavi sconosciute); i select bool 'on'/'off' <-> boolean.

### 1.9 Interruttore del servizio dei 4 bot (Control Room, per completezza)
Fuori dal perimetro dei file elencati ma e' "dove si vedono" i bot: `pages/ControlRoom.tsx` + `components/controlroom/PannelloBot.tsx`. Gruppo accordion **"BOT TENNIS (4)"** (puntini di stato per riga; "soldi veri" rosso / "prova" grigio; "oggi LIVE {€}" / "prova {€}"; icona anomalia). Ogni riga: etichetta ("Scalper tennis", "Pro tennis", "FLB tennis", "Swing tennis"), badge stato, modalita', eta' messaggio, nota, P&L oggi, `Parametri`, pulsanti **"ferma"**, **"passa a prova"**, **"passa a soldi veri"** -> **"confermi? sono soldi veri"**, **"avvia in prova"**, **"avvia con soldi veri"** -> **"confermi? ordini reali su Betfair"**; testata "Comando dei bot" con **"Ferma tutti"** (tooltip "ferma le aperture di tutti i bot. Non chiude nessuna posizione."); banner "{n} con soldi veri"; piede "Fermare spegne le aperture: le posizioni già a mercato restano sorvegliate e le puoi chiudere da qui." RPC del servizio: `get_tennis_bot_services`, `tennis_bot_service_activate(p_bot_key,p_mode,p_stake,p_params)` (mode OBBLIGATORIA 'paper'|'live', mai ereditata), `tennis_bot_service_stop(p_bot_key)` (porta a 'stopping', lo 'stopped' lo scrive il runner), `tennis_bot_service_update_params`, `tennis_bot_service_set_uscite(p_bot_key,p_automatiche)` (uscite manuali di default), `get_tennis_bot_daily(p_from,p_to,p_mode,p_bot)`, `get_tennis_bot_orders_today(p_mode)`. Stati servizio: `stopped|running|stopping|error`, modalita' `paper|live`. Canale locale dei 4 bot: `ws://127.0.0.1:47337` (topic `tennis_bot_stato`, `tennis_bot_posizioni`). Dal pulsante "Trading" della scheda partita (Control Room) si arriva a `/tennis/terminal?...&from=control-room` e a `/segui-live?event=...&from=control-room`.

---

# PARTE II — LIVE / LADDER (calcio, con ladder condiviso col tennis)

## 2. SeguiLive (`pages/SeguiLive.tsx`, ~1300 righe) — `/segui-live`

**Scopo**: lista delle partite di calcio sottoscritte allo stream Betfair (`get_live_follows`, refetch ogni 15 s come backup) e, cliccando una card, **terminal di trading realtime** (stesso page, nessuna nuova rotta). **Sport**: calcio (il tennis ha il suo terminal).
**Deep-link**: `?event=<id>&from=omega` (mostra "Torna a Omega" -> `/omega`; auto-seleziona la partita appena compare il follow) oppure `?event=<id>&from=control-room` (mostra "Torna alla Control Room" `data-testid="torna-control-room"`, title "torna alla Control Room, alla scheda e alla partita da cui sei partito", -> `/control-room`).

### 2.1 Chrome di pagina (ordine di render)
1. Sfondo `min-h-screen bg-background pb-24` + `grid-pattern opacity-30`.
2. **Nav sticky** (`bg-black/50 backdrop-blur-xl`, `h-16 px-6`): sinistra brand link "AI **TERMINAL**" -> `/dashboard`, poi (md+) icona `Radio` + "SEGUI LIVE" (primary, heading bold). Destra, bottoni outline sm: **"Market Watch"** (su mobile "MW") -> `/market-watch`; **"P&L"** -> `/live-pnl`; **"Journal"** -> `/trade-journal`; **"Match Replay"** (icona `History`, colore secondary) -> `/match-replay`; **"Dashboard"** (icona `ChevronLeft`) -> `/dashboard`.
3. `<main class="container ... py-8">` larghezza `max-w-6xl` (lista) o `max-w-[1800px]` (dettaglio).
4. **`LiveAlertBanner`** (sez. 4.9) in cima.
5. **Titolo**: `h1` "Segui **Live**" (Live in primary) + testo "Partite sottoscritte allo stream Betfair. Clic su una partita per le quote in tempo reale." A destra bottoni: *Torna a Omega* / *Torna alla Control Room* (condizionali); se una partita e' selezionata: **REC / Registra** (icona `CircleDot`, rosso pulsante se attivo; title attivo "Registrazione ATTIVA: la partita sarà caricata nel Match Replay a fine gara — clic per spegnere", spento "Registra la partita per intero (raw + Match Replay a fine gara)"; toast on "Registrazione attivata" / "La partita viene registrata per intero e a fine gara caricata nel Match Replay.", toast off "Registrazione disattivata" / "Streaming e trading proseguono; niente raw né upload nel Replay.", errore "Toggle registrazione fallito"); **"Tutte le partite"** (icona `ChevronLeft`, deseleziona).
6. Se arrivati da deep-link e follow non ancora in lista: `AttachProgress stage=1`.
7. Errore lista: card rossa con `AlertTriangle` + messaggio.
8. Corpo: *Loading* = 4 scheletri `h-24`; *dettaglio* (se selezionata); *nessuna partita* = `HabitatCard` + card "Nessuna partita in streaming." (icona `Radio` grande opaca); *lista* = `HabitatCard` + griglia `lg:grid-cols-2` di `LiveMatchCard`.
9. Footer `© {anno} Alpha Score AI. All rights reserved.`

**Fonti (pagina)**: RPC `get_live_follows`; realtime `live_follow` (per evento, durante l'aggancio) e `live_now` (SELECT + `postgres_changes`, filtro event_id); canale locale calcio `ws://127.0.0.1:47331` topic `now` (merge "il piu' recente vince" per `updated_at`); RPC `set_follow_record` (REC, via `omegaMissions.setFollowRecord`).

### 2.2 LiveMatchCard (`components/live/LiveMatchCard.tsx`) — card partita
`Card glass-card p-4 cursor-pointer` (selezionata: `ring-1 ring-primary/60`). Riga 1: lega (`league_name` o "Lega sconosciuta", 11px maiuscolo muted) | a destra: pillola origine `data-testid="origine-follow"` **"auto"** (sky, title "Seguita DA SOLA dal runner per i bot (solo stream e ordini): "Segui live" per il terminale completo") o **"manuale"** (grigia, title "Seguita a mano ("Segui live")"); badge stato (`LIVE_STATUS_LABEL`): **In attesa** (PENDING grigio) / **In streaming** (STREAMING primary pulsante + icona Radio) / **Chiusa** e **Caricata** (CLOSED/UPLOADED secondary) / **Errore** (ERROR rosso). Riga 2: `{home}` (emerald-400 bold) + `{sh} - {sa}` (display black; "vs" se nessun punteggio) + `{away}` (amber-400 bold); se in-play col minuto: pillola primary `{minute}'`. Riga 3 (10px muted): `live_status` o ("In gioco" / "Pre-match") | "fonte: {score_source}". Se ERROR con dettaglio: riga rossa con `error_detail`.

### 2.3 AttachProgress (progresso di aggancio)
`Card glass-card border-secondary/30 p-4`: 3 passi in riga: **"Richiesta registrata"**, **"Aggancio stream (runner)"**, **"Primo dato ladder"** (fatto = verde con check; attivo = secondary con spinner, rosso con `AlertTriangle` se errore; futuro = cerchietto numerato). Sotto: errore "Errore dal runner: {msg}" oppure "Il ladder si aggancia da solo appena arriva il primo dato (di norma pochi secondi). Se resta fermo a lungo: verifica che il runner sia acceso (chip ♥ runner in top bar)" + (stage 2) " oppure c'è un'**esposizione aperta su un'altra partita** (ordini vivi o regole di rischio armate): per sicurezza il runner NON riaggancia lo stream finché non è flat — controlla il pannello Alert (avviso NEW_MATCHES)." Mostrato per PENDING (stage 2), STREAMING (stage 3), ERROR (con `error_detail`), finche' `live_now` non ha mercati.

### 2.4 Dettaglio partita (selezionata) — ordine di render
1. `LiveMatchCard` selezionata (`selected`).
2. Riga destra: `BetfairMediaButtons` (pieno).
3. Se `detailLoading` senza dati: 4 scheletri `h-40` (griglia 2 col).
4. `AttachProgress` (se `live_now` senza mercati e follow PENDING/STREAMING/ERROR).
5. **`LiveTradingSection`** (se ci sono mercati) — il terminal (2.5).
6. **Overview** (`grid lg:grid-cols-3`): `LiveMarketBoard` (col-span 2, sez. 4.8) + `LiveSignalPanel` (col-span 1, sez. 4.10).

### 2.5 LiveTradingSection — "COCKPIT MULTI-MERCATO stile Bet Angel"
Props: `markets` (da `live_now.state.markets`), `orderMode`, `eventName` = "{home} vs {away}", `eventId`, `updatedAt`, `clock{openDate,minute,scoreHome,scoreAway,inplay}`. Il mercato attivo di default = Match Odds (`market_type==='MATCH_ODDS'` o nome /match odds/i), poi ricordato per-evento nel workspace (localStorage `workspace:{eventId}`: pannelli, `activeMarketId`, `columnsProfile`, `centerView`). Modalita' (`off|paper|live`) da `live_now.state.order_mode`, fail-safe OFF.

**Ordine di render**
1. **`FlussoStreamBanner sport="calcio"`** (sez. 4.7).
2. **TOP BAR sticky** (`top-16 z-40`, `rounded-xl border bg-black/80 backdrop-blur-xl px-3 py-2`, riga flex wrap), elementi nell'ordine (ciascuno condizionale):
   - **Badge modalita'** (`TerminalModeBadge`): LIVE = `🔴 LIVE — SOLDI VERI` (`bg-red-600 text-white`, pulsante); PAPER = `PAPER` (`bg-sky-500/20 text-sky-300`); OFF = `OFF` (`bg-white/10 text-white/60`).
   - Chip `⚡ LOCALE` (se canale 47331 connesso; `bg-emerald-500/20 text-emerald-300`; title "Canale LOCALE attivo (ws://127.0.0.1:47331): ladder, quote e ordini direttamente dal runner sul PC — latenza ~0. Se cade, fallback automatico al DB.").
   - **Orologio**: in-play -> `{minute}' · {score}` (verde, mono, title "Minuto di gioco e punteggio (live_now)"); pre-match -> `OFF in {countdown}` (ambra, title "Countdown all'off (open_date)").
   - **Warning LAPSE** pre-kickoff (resting con persistenza LAPSE che decadranno al passaggio in-play; poll 15 s solo pre-match con modalita' attiva): `⚠ {n} LAPSE decadono all'off` ambra; **rosso lampeggiante sotto i 5 minuti**; title con la spiegazione (Keep/PERSIST o Take SP).
   - **P&L di giornata** (da `betfair_live_risk_state`, realtime): `{🛑 STOP }oggi {+|−}€{x.xx}` (rosso se stop scattato, rosa se negativo, verde se positivo; title con settled + MTM e "stop a −€{limite}" / "stop giornaliero spento" / "⚠ stima worst-case").
   - **Saldo conto**: `saldo €{available}` (da `betfair_live_account`, mono bianco; title con exposure e orario).
   - **Heartbeat runner** (tre stati, mai finto verde): `♥ runner` (+`+wd` se watchdog attivo; verde) / `runner n/d` (grigio, stato sconosciuto) / `⚠ RUNNER GIÙ {s}s` (rosso, pulsante, title "Ultimo heartbeat {s}s fa: runner GIÙ o appeso — stop/regole armate NON esistono più!").
   - **Esposizione evento**: `exp evento €{x}` (ambra, se >0).
   - **Over-round**: `{back%} / {lay%}` (Σ1/quota back in **sky**, lay in **rose**; solo se tutte le selezioni hanno prezzo).
   - **Freschezza**: `agg. {s}s fa` (muted) oppure `⚠ DATI VECCHI {s}s` (rosa bold se >15 s) / `dati: n/d`.
   - spaziatore, poi **bottoni emergenza** (h-7):
     * **"Cash-out MERCATO{ (±€x.xx ⚠)}"** — `bg-amber-500 text-black font-black`, icona `Banknote` / spinner; disabilitato se OFF o occupato. Hotkey G.
     * **"Cash-out EVENTO{ (±€x.xx ⚠)}"** — `bg-rose-600 text-white`, icona `ShieldAlert`. Hotkey X.
     * **"KILL"** — outline rosso (title "KILL-SWITCH GLOBALE del runner: blocca le APERTURE (le chiusure restano possibili) — hotkey Esc").
     * se mode != off: cerchietto **"?"** con tooltip "Scorciatoie tastiera:\nG = cash-out mercato attivo\nX = cash-out intero evento\nEsc = kill-switch globale\n(attive solo in PAPER/LIVE, non mentre digiti)".
   Il numero tra parentesi e' l'MTM bloccabile ORA (posizioni dello specchio, poll 10 s + canale locale, valutate ai prezzi di `live_now`; "⚠" se alcune posizioni senza prezzo).
3. **Banner PRE-GOAL** (solo in-play, dal modello `live_signals`, fresco e sopra soglia): riquadro ambra (livello `amber`) o rosso (`red`): `⚠ RISCHIO GOL: P(gol ≤{N}') ≈ {p}%` + ` · modello al {m}'` (title con spiegazione hazard) | bottone **"Copri ora{ (€)}"** (ambra o rosso, icona `ShieldAlert`) = stesso cash-out EVENTO con le stesse conferme.
4. **TAB multi-mercato**: un bottone per mercato (`market_name || market_type || market_id`; attivo: bordo sotto `primary`, `bg-white/[0.06]`) + a destra link **"⧉ Multi-ladder"** (title "Workspace Multi-ladder: N ladder affiancati anche di eventi/sport diversi", ambra) -> `/multi-ladder`. Hotkey PageUp/PageDown = mercato prec./succ.
5. **GRIGLIA 3 ZONE** `grid xl:grid-cols-[290px_minmax(0,1fr)_400px] gap-3` (sotto xl: ladder in alto, rail, strumenti), ogni componente con `key={market_id}` (rimonta al cambio tab):
   - **Sinistra 290px**: `TerminalPositionsRail` (sez. 4.5).
   - **Centro**: toggle `Ladder` | `Grid` (come tennis; persistito nel workspace) + `LadderView` (con `signals`, `popout`, `multiSlot`, `fallbackSelections`) o `GridView`; `ladderSource = sorgenteLadderAlMs('calcio')`; `orderApi = localOrders` se canale connesso altrimenti default DB.
   - **Destra 400px**: **7 tab strumento** (uno alla volta; ricordato per evento in `localStorage['live.terminal.tool.{eventId}']`; default **Trading**): **Trading** | **Dutching** | **Risk** | **X-Hedge** | **Scalper** | **Chart** | **Depth** -> rispettivamente `LiveTradingPanel`, `DutchingPanel` (con `updatedAt`), `RiskRulesPanel`, `XHedgePanel` (per evento), `ScalperPanel` (`key=eventId`), `SelectionChartPanel` (bucket default 15 s), `DepthPanel`.
6. **Controlli runner · limiti · audit** (`<details>` chiuso di default, `rounded-xl border bg-black/30`): summary "▸ Controlli runner · limiti · audit" (10px maiuscolo, freccia ruota 90 gradi da aperto) -> `LiveControlsPanel` (sez. 4.4).

**Cash-out — flussi e conferme (money-critical)**
- MERCATO: se mode off toast.error "Runner in OFF: cash-out non disponibile. Avvia in PAPER o LIVE."; conferma sempre (anche paper): `CASH-OUT {REALE (soldi veri)|SIMULATO (paper)} del SOLO mercato "{nome}"?\nAppiattisce TUTTE le selezioni con esposizione aperta di QUESTO mercato.` -> `sendCashoutAll` (azione coda). Toast "Cash-out MERCATO inviato" / "Cash-out mercato rifiutato" / "Errore cash-out mercato".
- EVENTO: conferma `CASH-OUT {REALE|SIMULATO (paper)} dell'INTERO EVENTO "{nome}"?\nAppiattisce TUTTE le selezioni con esposizione aperta su TUTTI i mercati dell'evento (non solo quello attivo).{ SOLDI VERI.}`; in LIVE seconda conferma "Conferma DEFINITIVA: green-up REALE di TUTTI i mercati dell'evento. Procedere?". Toast "Cash-out EVENTO inviato" / "Cash-out evento rifiutato" / "Errore cash-out evento".
- KILL: `confirm("KILL-SWITCH: blocca immediatamente ogni invio ordini del runner. Attivare?")` -> `set_live_kill_switch(true)`; toast.warning "Kill-switch ATTIVATO" / "Invio ordini bloccato.".
- Guardia anti doppio invio a livello di ref (vale anche per hotkey).

**Scorciatoie da tastiera (livello pagina)** — attive solo in PAPER/LIVE, ignorate in input/textarea/select/contenteditable e con Ctrl/Meta/Alt: **G** = cash-out mercato, **X** = cash-out evento, **Esc** = kill-switch, **PageUp/PageDown** = tab mercato precedente/successivo. (Per le altre vedi LadderView 3.1.)

**Fonti dati (terminal)**: `live_now.state.markets[]` (market_id, market_type, market_name, status, selections[{selection_id,name,back,lay,ltp}]) e `order_mode`; RPC `get_live_positions_event(p_event_id)` (poll 10 s) + push `position` canale 47331; `betfair_live_risk_state` (SELECT + realtime); `betfair_live_account` (SELECT + realtime); `betfair_live_heartbeat` (SELECT + realtime; ok/stale/unknown); `live_signals` (SELECT + realtime, per chip Kelly, EV, pre-goal); RPC `get_live_orders(p_market_id)` ogni 15 s (conteggio LAPSE).

---

## 3. LadderView e GridView (nucleo del trading; condivisi calcio/tennis/multi/popout)

### 3.1 LadderView (`components/live/LadderView.tsx`, ~2750 righe)
**Scopo**: ladder per-mercato fedele a Bet Angel/Geeks Toy/Betting Toolkit: profondita' back/lay, scala tick con prezzo al centro, LTP evidenziato, volume tradato per livello, TUOI ordini non abbinati sui livelli, WOM, P&L-per-livello (greening), PIQ, EV, one-click, drag-to-move, strumenti armati, macro.

**Props principali**: `marketId`, `marketName`, `orderMode` (OFF|PAPER|LIVE), `handicap=0`, `sport` ('calcio'|'tennis'; sceglie il profilo colonne persistito), `fallbackSelections`, `ladderSource` (DI), `orderApi` (DI), `enableDragMove=true`, `popout`, `multiSlot`, `signals` (live_signals, solo calcio), `flussoRunner=true`.

**Colonne per selezione (ordine di DEFAULT "layout v2": lato LAY a SINISTRA del prezzo, BACK a DESTRA)**
- Calcio: `my_lay · avail_lay · price · avail_back · my_back · pnl · ev · trd · piq` (9). Tennis: stesse senza `ev` (8). `wom` e' nell'header selezione, non e' colonna. `price` e' fissa (non nascondibile). Profilo per-sport salvato in localStorage (`ladderConfig`).
- Intestazioni brevi (8px maiuscolo) e larghezze: `L` (my_lay, 34px, rose, title "I tuoi LAY non abbinati (clic per annullare)") · `Lay` (avail_lay, 56px, rose) · `Prezzo` (50px) · `Back` (avail_back, 56px, sky) · `B` (my_back, 34px, sky, title "I tuoi BACK non abbinati (clic per annullare)") · `P&L` (50px, purple, title "P&L se chiudi a questo prezzo") · `EV` (54px, violet, title F38 "EV a questo prezzo secondo il FAIR del motore (netta commissione). B = value BACK, L = value LAY; vuoto = nessun valore a quel livello.") · `Trd` (42px, title "Volume tradato a questo prezzo") · `PIQ` (34px, title "PIQ: coda STIMATA (piqAhead + volume tradato)").
- Etichette nel selettore colonne (`COLUMN_LABELS`): Mio LAY, Banco BACK, Quota, Banco LAY, Mio BACK, P&L, TRD, PIQ, WOM, EV.
- **Colori**: BACK = sky (`bg-sky-500/15 text-sky-200`, hover `/30`), LAY = rose (`bg-rose-500/15 text-rose-200`); best back/lay = anello inset sky/rose 1px; riga **LTP** = `bg-amber-400/25 text-amber-100` + anello ambra; riga best (non LTP) `bg-white/[0.06]`; riga **FAIR** = bordo interno viola; P&L>0 emerald, <0 rose, 0 viola; volume tradato = barra ambra `amber-400/15` + numero `amber-200/80`; mio ordine = pillola `bg-rose-500/20`/`bg-sky-500/20` con hover barrato; flash direzionale 260 ms (verde `rgba(52,211,153,.30)` se la disponibilita' sale, rosso `rgba(244,63,94,.30)` se scende) sulle celle e `pulse` sul LTP (0.40).

**Struttura del blocco `LadderView` (Card `glass-card`, ordine di render)**
1. **`FlussoStreamBanner`** (solo calcio/tennis, se `flussoRunner`).
2. **Header mercato** (`px-3 py-2.5 bg-white/[0.03]`): icona `Layers` ambra + nome mercato (`marketName || row.market_name || market_type || marketId`) + **badge modalita'** (`🔴 LIVE` rosso / `PAPER` verde / `OFF` grigio) + (se status != OPEN) badge **`Chiuso`** (grigio) o **`Sospeso`** (rosso). A destra, wrap, nell'ordine:
   - **Stake**: label "Stake" + preset **2 · 5 · 10 · 25** (attivo `bg-amber-400 text-black`) + input custom € (w-14; bordo **rosso** se invalido -> title "Stake non valido: i clic di piazzamento sono bloccati", altrimenti "Stake custom (€)"; placeholder "€").
   - (se mode != off) **Persist**: `Keep` | `Lapse` (default) | `Take SP` (tooltip: "Keep: l'ordine RESTA a mercato al passaggio in-play (PERSIST)" / "Lapse: l'ordine DECADE al passaggio in-play (LAPSE, default)" / "Take SP: l'ordine va allo Starting Price (MARKET_ON_CLOSE)"; contenitore title "Cosa fa l'ordine al passaggio in-play").
   - (se mode != off) **Stake / Liab**: due bottoni `Stake` | `Liab` (attivo `bg-rose-300 text-black`; title "LAY: interpreta l'importo come puntata (Stake) o come responsabilità (Liab). I BACK non cambiano.").
   - (se mode != off) icona tastiera con tooltip hotkey: "Hotkey (sul ladder puntato dal mouse):\nB = BACK al livello · L = LAY al livello · C = annulla ordini al livello\n↑/↓ = vista su/giù di 1 tick · Spazio = ricentra sul prezzo\n+/− = stake ±0,50€ · S = prossimo preset\nG = cash-out mercato · X = cash-out evento · Esc = kill-switch (dal terminal)".
   - se `multiSlot`: icona `Layers` "Aggiungi al Multi-ladder" (title "Aggiungi questo mercato al workspace Multi-ladder (N ladder affiancati, anche di eventi diversi)"; messaggi: "✓ Aggiunto al Multi-ladder ({n} ladder) — apri /multi-ladder." / "✗ Già nel Multi-ladder (o workspace pieno).").
   - se `popout`: icona `ExternalLink` "Stacca" (title "Stacca questo ladder in una finestra dedicata (multi-monitor)") -> `window.open('/ladder-popout?sport=&market=&event=&name=&eventName=&p1=&p2=', 'ladder_{marketId}', 'popup=yes,width=560,height=860,...')`.
   - (se mode != off) **`⚡ 1-CLICK`** (toggle; spento = bordo rosso/ambra; ARMATO = pieno rosso (LIVE) / ambra (PAPER) pulsante). All'attivazione `window.confirm`: LIVE "1-CLICK REALE: ogni clic su BACK/LAY o sui tuoi ordini piazzerà/annullerà un ordine con SOLDI VERI SENZA ulteriore conferma. Attivare?"; PAPER "1-CLICK SIMULATO (paper): ogni clic piazzerà/annullerà un ordine SIMULATO senza ulteriore conferma — identico al vivo, ma senza soldi veri. Attivare?". L'armamento si azzera a ogni cambio di modalita'.
   - **Colonne** (icona `Settings2` + "Colonne"): popover (w-56) "Colonne · {sport}" con **Reset** (icona `RotateCcw`, "Ripristina layout predefinito"), una riga per colonna: checkbox "Mostra colonna {label}" (Quota "(fissa)" e disabilitata), frecce su/giu' ("Sposta {label} su/giù").
3. **TOOLBAR ARMATA** (solo se mode != off; `bg-black/40`, 10px). Ogni strumento = bottone toggle + (dove serve) input numerico; **se `orderApi.armRule` assente (tennis) questi non compaiono**:
   - **Entry** (icona `Target`, `bg-amber-400` attivo) — C23 stop-entry: il click ARMA un ingresso condizionale al prezzo cliccato.
   - **Offset** [n tick 1-50] + checkbox **green** (default 3 tick, greening on) — C20 take-profit a N tick armato al fill. `bg-emerald-400` attivo.
   - **Stop** [n tick 1-50] + checkbox **trail** (default 5 tick) — C21 stop-loss / trailing; con Offset (e trailing spento) = BRACKET OCO (C26). `bg-red-400` attivo.
   - **Chase** (icona `Repeat`) [n tick 0-20] — C25 re-quote a N tick dal best. `bg-sky-400`.
   - **FoK** (icona `Timer`) [s 1-600] "s" — C22, solo se `supportsFok` (calcio). `bg-purple-400`.
   - **Scala** [N ordini 2-10] "×" [passo tick 1-10] "t" — C24, N ordini scaglionati (back verso quote piu' alte, lay verso piu' basse); non combina Offset/Stop. Presente anche nel tennis.
   - **Servants** (icona `Wand2`, "Servants ({n})") a destra — C27 macro 1-9.
   Con Entry attivo gli altri sono disabilitati. Banner promemoria: "STOP-ENTRY ARMATO: il click ARMA un ingresso condizionale al livello cliccato (non piazza subito). Gli altri strumenti (Offset/Stop/Chase/FoK/Scala) sono IGNORATI finché Entry è attivo."
4. **Pannello Servants** (se aperto): elenco macro salvate (label `servantLabel`, cestino) oppure "Nessuna macro: costruiscine una qui sotto, poi richiamala col suo numero sulla selezione puntata."; builder: Slot (1-9, "(sovrascrive)"), nome, tipo step (`place` | `green-up` (solo se greenup supportato) | `annulla lato`), lato BACK/LAY, prezzo (`al best` | `all'LTP` | `± tick dal best` + n -20..20), stake (`stake corrente` | `stake fisso €`), "+ step" (max 6), sequenza con "×", **"Salva macro {slot}"**. Eseguite con i tasti **1-9** sulla selezione puntata.
5. **Banner armamento 1-click**: LIVE "1-CLICK REALE ATTIVO — ogni clic piazza/annulla con SOLDI VERI senza conferma." (rosso) / PAPER "1-CLICK SIMULATO ATTIVO — ogni clic piazza/annulla un ordine paper senza conferma." (ambra).
6. **`PlaceConfirmDialog`** (overlay assoluto sulla card) per i PLACE non armati (sez. 4.6). Per gli altri intent (annulla, annulla lato, sposta, green-up, chiudi qui, macro, stop-entry, scala) **barra di conferma** (`bg-red-500/15` LIVE / `bg-amber-500/15` PAPER): "🛡 Confermi {etichetta intent} ({REALE|SIMULATO})?" + bottoni **"✓ Conferma"** e **"✕ Annulla"**. **Scade dopo 6 s** (`CONFIRM_TTL_MS`): messaggio "✗ Conferma scaduta (mercato mosso): riclicca il prezzo per ripetere."
   Etichette intent: `BACK|LAY {€x.xx | resp. €x.xx} @ {prezzo} · {Keep|Lapse|Take SP} · {sel}` (+ ` +[offset 3t green · stop 5t · chase 0t · FoK 5s]`); `SCALA {n}× BACK|LAY … @ p1/p2/…`; `STOP-ENTRY {lato} €{x} quando LTP {≥|≤} {prezzo} · {sel}`; `MACRO {…}`; `Annulla {n} ordine/i {LATO }@ {prezzo} · {sel}`; `Annulla TUTTI i {n} ordini {LATO} · {sel}`; `Sposta {LATO} €{x} → {prezzo} (cancel→replace) · {sel}`; `Chiudi @ {prezzo} (greening al livello) · {sel}`; `Cash-out {pct% }· {sel}`.
7. **Avvisi**: se overlay ordini/posizioni stantio (>15 s) o in errore: "⚠ Ordini/posizioni NON aggiornati (ultimo ok {hh:mm:ss}) — {errore}" (rosa). **Esito ultimo comando** (riga colorata): pending (grigio, spinner) `{etichetta}…`; ok (verde) `✓ {etichetta} — {detail|stato X}`; errore (rosso) `✗ {etichetta}: {errore}`.
8. **Selettore selezione** (solo se >3 selezioni, es. Correct Score): riga di bottoni-pillola con i nomi (attivo `bg-primary text-black`); si mostra UN ladder per volta. Con <=3 selezioni i ladder sono AFFIANCATI (scroll orizzontale, ognuno `min-w-[348px]`; per il Match Odds del calcio sono 3: Home, Away, The Draw; per il tennis 2).
9. **Ladder di UNA selezione** (`SelectionLadder`, card `rounded-xl border bg-black/40`):
   a) **Header selezione**: nome (heading bold) | a destra chip **Kelly** `K€{stake}` (sky se BACK / pink se LAY; title con side, stake, prob, fair, edge; un click imposta lo stake, MAI invia ordini; solo calcio con segnale fresco) + "Matched **€{tv}**".
   b) Riga controlli: **WOM bar** ("WOM" + barra sky/rose + freccia + "{n}%"; title "Weight of Money: pressione vicino al best"); bottoni vista: **Auto-center** (icona `Crosshair`, ambra se attivo; title "Auto-center ATTIVO: la vista segue il LTP a ogni update. Clic per navigare liberamente." / "Auto-center SPENTO: vista libera (frecce/price bar/scroll). Clic per riagganciare il LTP."), **Price bar** (icona `Ruler`; title "Price bar navigabile 1.01–1000 (heat = concentrazione del denaro); trascina per scorrere il ladder"), **Mini-chart** (icona `LineChart`; title "Mini-chart candele del prezzo (LTP) della selezione"); se ha posizione e si puo' operare: **slider cash-out parziale** 10-100% step 5 (aria-label "frazione cash-out", accent viola, "{pct}%"; title "Frazione di cash-out (parziale)"); bottone **"Cash-out {pct%|€P&L bloccabile}"** (viola `bg-purple-500/15`; title abilitato: "Cash-out COMPLETO al miglior prezzo: annulla i resting della selezione, poi hedge dalle esposizioni reali (A3)." / parziale "Cash-out {pct}% al miglior prezzo (hedge dalle esposizioni reali). I resting NON vengono toccati." / disabilitato "Cash-out: richiede una posizione aperta e mercato operabile"). Il P&L mostrato = `lockedPnlAt` al best OPPOSTO (lay se win>lose, altrimenti back).
   c) **Intestazione colonne** (vedi sopra); `L✕{n}` / `B✕{n}` cliccabili = **annulla TUTTI gli ordini di quel lato** (title "Annulla TUTTI i {n} ordini {LATO} di {sel} (un click)") quando ce ne sono e si puo' cancellare (anche con mercato SOSPESO).
   d) **Corpo** (`max-h-[420px]` scroll, opacita' 60% se Chiuso/Sospeso): finestra fino a **42 righe** (`MAX_ROWS`), prezzo alto in cima, centrata sul LTP (auto-center) o su centro manuale (scala tick pura 1.01-1000 anche dove il book e' vuoto). A sinistra opzionale **PriceAxisBar** (sez. 4.12), a destra opzionale **MiniPriceChart** (4.11). Vuoto: "Profondità non ancora disponibile.".
      Comportamenti di cella:
      * `avail_back` / `avail_lay`: **click = place al prezzo di quella riga** (title abilitato `BACK €{stake} @ {prezzo}` / `LAY €{stake} @ {prezzo}` / in liability `LAY resp. €{stake} @ {prezzo}`; OFF: "Back (sola lettura: modalità OFF)" / "Lay (sola lettura: modalità OFF)"). Con mercato non OPEN o mode OFF il click evidenzia soltanto il livello (anello ambra).
      * `price`: click = **ricentra** sul prezzo corrente (title "Ultimo prezzo tradato (LTP) · clic = ricentra" / "Clic = ricentra il ladder sul prezzo corrente"; sul tick FAIR: "FAIR del motore: {x} (prob {p}%) · ").
      * `my_lay` / `my_back`: pillola con la size residua; **click = annulla** (title "Annulla i tuoi LAY a questo prezzo"); se drag abilitato: **trascina su un altro livello = sposta** (cancel poi replace, mai un singolo replace; title "Trascina per SPOSTARE (cancel→replace) · clic per annullare i tuoi LAY|BACK"); riga di destinazione evidenziata con anello verde `emerald-400/70`. La size ripiazzata e' quella REALMENTE annullata (letta dall'esito del cancel o dallo specchio), mai piu' del drag; la persistenza dell'ordine origine e' conservata.
      * `pnl`: valore se chiudi a quel prezzo (viola; `−` unicode); **click = "greening column"** (chiude TUTTA la posizione a QUEL prezzo, l'ordine puo' restare sul book; title "Chiudi QUI: blocca {€x} chiudendo a {prezzo} (l'ordine può restare sul book)").
      * `trd`: barra proporzionale + numero (k oltre 1000). `piq`: `~{n}` coda stimata (title "Coda STIMATA davanti al tuo ordine · statica ~X · con volume tradato ~Y"). `ev`: `B{n}`/`L{n}` o `·`.
      * Formato prezzi: `>=100` 0 decimali, altrimenti 2; size `k` oltre 1000.
   e) **Footer selezione**: "Stake|Resp." `€{stake}` (ambra mono bold) e, se c'e' posizione, "Net **{€}** (sky se >0, rose se <0)" e "Exp **{€}**" (title "Net = stake netto della selezione (positivo: posizione da BACK; negativo: da LAY) · Exp = esposizione (peggior perdita) della selezione").
10. **Footer ladder** (9px muted): sinistra = OFF "Sola lettura (modalità OFF) · per operare avvia il runner in PAPER/LIVE"; LIVE "Clic = ordine REALE con conferma e proiezione P&L" / armato "1-click REALE attivo"; PAPER "Clic = ordine simulato con conferma e proiezione P&L (specchio del vivo)" / armato "1-click SIMULATO attivo"; destra "Aggiornato: {hh:mm:ss}{ (canale|DB)}".
11. Stati iniziali: "Caricamento ladder…" (spinner) finche' la prima riga; "Ladder non disponibile: il runner non sta pubblicando la profondità per questo mercato." se nessuna selezione.

**Stati condizionali del ladder**
- OFF: sola lettura (celle cliccabili ma niente ordini; niente Persist/Liab/1-CLICK/toolbar/hotkey).
- PAPER/LIVE: stesso flusso (regola specchio): conferma con popup (importo editabile + proiezione) a meno di 1-click armato; cambia solo REALE/SIMULATO e i colori (rosso LIVE / ambra PAPER).
- Mercato OPEN: place+cancel; **SUSPENDED**: solo cancel (place bloccato, badge Sospeso, corpo al 60%); **CLOSED**: niente (badge Chiuso).
- Stake custom invalido: tutti i place/scala/stop-entry bloccati ("✗ Stake non valido: correggi l'importo prima di piazzare.").

**Hotkey del ladder** (sul ladder sotto il cursore; solo PAPER/LIVE; mai in input/select, con Ctrl/Meta/Alt, o con barra di conferma aperta): **B** = BACK al livello puntato, **L** = LAY al livello puntato, **C** = annulla gli ordini a quel livello, **↑/↓** = sposta la vista di 1 tick (passa a navigazione manuale), **Spazio** = ricentra sul prezzo, **+ / −** = stake ±0,50 (arrotondato a 0,01; min 0,50), **S** = prossimo preset (2→5→10→25), **1-9** = macro (servants) sulla selezione puntata (lo stake "corrente" e' congelato al momento). G/X/Esc/PageUp/PageDown restano alla pagina. Le hotkey sono sospese se la finestra scivola sotto un cursore fermo (nessun ordine a un prezzo "vecchio").

**Fonti dati LadderView**: `ladderSource.fetch/subscribe` -> default calcio: SELECT `live_ladder` + realtime `live_ladder` (market_id); tennis: `tennis_live_ladder`; con canale locale: `sorgenteLadderAlMs` (push `ladder` su 47331/47332 come via principale, tabella DB come ripiego se il canale e' assente o muto >4 s; indicatore "(canale|DB)"). Ordini/posizioni overlay: `orderApi.fetchOrders/fetchPositions` (calcio RPC `get_live_orders(p_market_id)` e `get_live_positions(p_market_id)`; tennis RPC `get_tennis_live_orders|positions(p_market_id,p_mode)`), realtime `betfair_live_orders` / `betfair_live_positions` (tennis `tennis_live_orders|positions`), con riconciliazione ogni 10 s (5 s se i canali realtime non sono tutti SUBSCRIBED), debounce 250 ms. Comandi: RPC `request_betfair_live_order(p)` + poll `get_betfair_live_order(p_id)` (calcio) / `request_tennis_live_order` + `get_tennis_live_order` (tennis); regole: RPC `request_live_risk_rule(p)`. Azioni di coda usate: `place`, `place_submin`, `cancel`, `replace`, `greenup`, `cashout_all`/`cashout_event`, regole `offset|stop_loss|take_profit|trailing_stop|bracket|stop_entry|chase|auto_hedge`.

### 3.2 GridView (`components/live/GridView.tsx`, 618 righe) — vista "Grid one-click"
Card `border-slate-800 bg-slate-950/60 p-2`.
1. **Header**: nome mercato; badge modalita' (`off · sola lettura` grigio / `paper` verde / `live` rosso); badge stato mercato se != OPEN (ambra); (se mode != off) bottone **"🔓 armato"** (toggle 1-click; title "Attiva il 1-click REALE|SIMULATO (paper) (i clic piazzeranno SENZA conferma)" / attivo "1-click ... ATTIVO: ogni clic piazza senza conferma. Clicca per disattivare."; confirm all'attivazione "1-CLICK REALE: ogni clic su una cella della griglia piazzerà un ordine con SOLDI VERI SENZA ulteriore conferma. Attivare?" / "1-CLICK SIMULATO (paper): ogni clic su una cella piazzerà un ordine SIMULATO senza ulteriore conferma — identico al vivo, ma senza soldi veri. Attivare?"), pillola pulsante **"ARMATO"** (rossa LIVE / ambra PAPER).
2. **Barra di conferma sticky** (non armato; scade 6 s): `Ordine {REALE|SIMULATO}: {BACK|LAY} €{x} @ {prezzo} su {sel}` (+ ` — responsabilità €{x}` per i LAY) + **"CONFERMA REALE" / "CONFERMA SIMULATA"** + **"Annulla"**.
3. **Esito**: verde `✓ {BACK|LAY €x @ p · sel} — bet {id}`; errore ROSSO `✗ …: {errore}` (role=alert); pending grigio. Errori specifici: "✗ Conferma scaduta (mercato mosso): riclicca il prezzo per ripetere.", "✗ Stake non valido: correggi l'importo della riga prima di piazzare.", "✗ Mercato {STATO}: ordine NON inviato. Riclicca quando riapre."
4. **Tabella** (loading "Caricamento griglia…", vuota "Nessun dato ladder per questo mercato."). Colonne: **Selezione** | **P&L** | **LTP** (sparkline) | **Lay** (3 celle, in rosa `text-pink-400`) | **Back** (3 celle, sky `text-sky-400`) | **Stake**. 
   - Cella Selezione: nome (max 150px) + `LTP {prezzo}` (lampeggia verde/rosa 260 ms in base alla direzione).
   - P&L: due righe `matched_if_win` / `matched_if_lose` con segno (`+€x.xx`/`−€x.xx`, emerald/rose/slate) o `—`.
   - LTP: micro-sparkline SVG 60x16 della storia LTP (max 120 punti), `—` se <2 punti.
   - **Layout v2**: celle LAY = [3° livello, 2°, best] (best adiacente al centro), celle BACK = [best, 2°, 3°]. Ogni cella `h-9`: prezzo bold + size (10px); LAY `bg-pink-950/60 hover:bg-pink-900/60`, BACK `bg-sky-950/60 hover:bg-sky-900/60`; livello mancante `—`. In OFF le celle NON sono bottoni (opacity 70%); disabilitate se mercato non OPEN o stake invalido o occupato. Title: `BACK|LAY €{stake} @ {prezzo} · {sel}` / "— sola lettura" / "— stake non valido".
   - **Stake** per riga: input numerico w-14 (min 0.5, step 0.5, default **2**), persistito per sport in `localStorage['gridStake:{sport}']`; bordo rosso se invalido; disabilitato in OFF.
   - Piede: **book%** lay (ambra se >100) e back (ambra se <100) = Σ100/best (`—` se manca un best).
   Ordine inviato: LIMIT esplicito al prezzo della cella, persistenza LAPSE. Posizioni: poll 5 s + push; guardia anti-doppio-invio.
Fonti: `ladderSource` (come LadderView), `orderApi.send/fetchPositions/subscribePositions`.

---

## 4. PANNELLI DEL TERMINAL (`components/live/*`)

Tutti i pannelli a "card larga" (Trading, Dutching, Risk, X-Hedge, Controlli) condividono lo stesso scheletro: `glass-card rounded-2xl border border-white/10 bg-black/40 p-4 md:p-5 space-y-5`, titolo `h3 font-display font-black text-lg` con icona ambra, **ModeBadge** accanto al titolo, e (tranne Controlli/Scalper) il bottone **"Blocco pannello ON|OFF"** (icona `ShieldAlert`; ON = `bg-red-600 text-white`; title "Blocca SOLO gli invii di questo pannello (il Kill-switch GLOBALE del runner è nei Controlli)"; per Risk "Blocca SOLO l'arming da questo pannello…"). In modalita' OFF compare il riquadro "Runner in **OFF**: … disabilitato…" e il `fieldset` e' disabilitato.
**ModeBadge** (identico in tutti): LIVE = `🔴 LIVE REALE` (`bg-red-600 text-white` pulsante); PAPER = `PAPER` (`bg-amber-400 text-black`); OFF = `OFF` (secondary). Nota: qui PAPER e' AMBRA, mentre nel top-bar del terminal e' sky e nel ladder verde (incoerenza di stile esistente, vedi sez. 12).
Etichette dei campi: `text-[10px] uppercase tracking-wider text-muted-foreground`; select: `bg-black/60 border-white/10 rounded-lg px-3 py-2 text-sm`.
**Conferma LIVE one-shot**: nei pannelli di invio, in LIVE compare una checkbox rossa obbligatoria che si azzera dopo ogni invio riuscito o ambiguo (timeout/eccezione).

### 4.1 LiveTradingPanel (tab "Trading") — order entry classico + blotter
Titolo **"Live Trading"** + ModeBadge; sottotitolo `{eventName · marketName} · mercato {marketId}` (mono). A destra "Blocco pannello", e bottone ghost refresh (icona `RefreshCw`, spinner se carica).
**Order entry** (griglia 2/4 colonne):
- **Selezione** (select `{nome} (#{id})`, o input numerico `selection_id`), **Handicap** (step 0.25, def 0), **Lato** (`Back (punta)` | `Lay (banca)`), **Prezzo (quota)** (1.01-1000, placeholder "es. 2.10"), **Size (€)** / **Liability (€)** (placeholder "es. 2.00"), **Importo come** (`Size` | `Liability (solo lay)`; abilitato solo per Lay), **Persistenza** (`LAPSE (decade in-play)` | `PERSIST (resta)` | `MARKET_ON_CLOSE`; disabilitata con submin, title "Non supportata dal place-and-trim (ignorata dal worker)"), **Cap max stake (€)** (def 10).
- Opzioni: checkbox **Fill-or-Kill** (+ campo "min fill" se spuntata; disabilitata con submin), checkbox **"Place-and-trim (sotto-minimo)"** (title "Place-and-trim: piazza al minimo e riduce alla size target (sotto-minimo)"; quando attiva azzera FoK/persistenza e mostra "il flusso sotto-minimo usa solo lato/prezzo/size: FoK e persistenza non si applicano").
- Info lay: "Lay: size €{x} · responsabilità €{y} (stima; il server arrotonda al tick e legalizza .it)".
- Piede: LIVE = checkbox rossa "Confermo ordine REALE (soldi veri)"; altrimenti "Modalità PAPER: nessun denaro reale."; bottone **"Piazza Back"** (`bg-sky-500`) / **"Piazza Lay"** (`bg-rose-500`) / **"Place-and-trim"**.
- Toast: "Ordine inviato" / "Place-and-trim avviato" (descrizione: bet id · stato · "abbinato €x" · "step n"); "Comando rifiutato"; "Errore comando". Validazioni: "Seleziona la selezione (selection_id).", "Prezzo non valido (1.01–1000).", "Size|Liability non valida.", "Modalità OFF: il runner non accetta ordini (LIVE_ORDER_MODE=OFF).", 'Spunta "Confermo ordine REALE" prima di inviare in LIVE.'
**Lista ordini** "Ordini ({n})": colonne **Selezione · Lato · Prezzo · Size · Abbinato · Stato · Azioni**; Lato `Back` sky / `Lay` rose; Abbinato `{size} @{prezzo medio}` verde; **Stato** = `LIVE_ORDER_STATUS_LABEL`: `PENDING`="In invio" (ambra), `EXECUTABLE`="Sul book" (sky), `EXECUTION_COMPLETE`="Completato" (verde), `EXPIRED`="Scaduto" (grigio), `VIOLATION`="Rifiutato" (rosso). Azioni (solo EXECUTABLE): matita **Replace** (title "Replace (nuovo prezzo)"; `window.prompt("Nuovo prezzo per bet {id} (1.01–1000):")`) e **X** Cancel (title "Cancel"). Vuoto "Nessun ordine su questo mercato."
**Posizioni / P&L** "Posizioni / P&L ({n})" + etichetta fonte `data-testid="ltp-fonte-posizioni"` (`canale`|`db`) + "● LIVE" pulsante (poll ogni 3 s): colonne **Selezione · Se vince · Se perde · Worst win · Worst lose · Esposizione · Netto**; riga totale **"Totale mercato"** con "P&L mercato {worst} / {best} worst / best", esposizione, netto. Vuoto "Nessuna esposizione su questo mercato."
Fonti: RPC `get_live_orders`/`get_live_positions` (poll 3 s) + push canale `order`/`position` (47331); comandi via `request_betfair_live_order`.

### 4.2 DutchingPanel (tab "Dutching")
Titolo **"Dutching"** (icona `Layers`); sottotitolo `{evento · }{Punta più esiti (dutch)|Banca più esiti (bookmaking)} · mercato {id}`.
**Parametri** (griglia 4 col): **Lato** (`Back (dutch)` | `Lay (bookmaking)`), **Modalità** (`Equal (profitto pari)` | `Variable (peso)` | `Target (profitto obiettivo — solo Back)`; Target disabilitato sul Lay), **Puntata totale (€)** (def 10) oppure **Profitto obiettivo (€)** (def 5, in modalita' Target), **Persistenza** (`LAPSE (decade in-play)` | `PERSIST (resta)` | `MARKET_ON_CLOSE`), **Prezzo** (`Come impostato` | `Best price live` | `Un tick davanti` | `Nominato`), **Prezzo nominato** (1.01-1000, placeholder "es. 2.50", solo se Nominato).
**Selezioni** "Selezioni ({n} attive · min 2)": tabella con checkbox, **Selezione**, **Quota (back|lay)** (input modificabile, default best), **Peso** (solo Variable, placeholder "1"), **Stake**, **Se vince** (back) / **Responsabilità** (lay). Di default sono spuntate le prime 2 selezioni.
**Anteprima live**: "Book % (overround)" in grande (verde se favorevole: back <100, lay >100; rosa altrimenti) + "favorevole (< 100)" / "sfavorevole (≥ 100)" / "imposta ≥2 quote valide"; a destra "Puntata totale|Profitto obiettivo €x · stake sommati €y", "Profitto se vince €x" (o intervallo min … max in Variable) o "Responsabilità totale €x", nota "stima UI — il server piazza {ai prezzi impostati|al best price live|un tick davanti al best|al prezzo nominato}, ricalcola a profitto pareggiato e arrotonda al tick".
**Invio**: LIVE = checkbox rossa "Confermo dutching REALE (soldi veri)"; altrimenti "Modalità PAPER: nessun denaro reale." / "Modalità OFF."; avviso "⚠ Quote stantie (snapshot > 10s): piazzamento bloccato finché il book non si aggiorna."; bottone **"Piazza Dutch ({n})"** (sky) / **"Piazza Bookmaking ({n})"** (rose). Guardie: stale >10 s, Lay+Target rifiutato ("Modalità Target non disponibile sul lato Lay (il worker la rifiuta): usa Equal/Variable."), "Seleziona almeno 2 selezioni con quota valida.", "Profitto obiettivo non valido (> 0).", "Puntata totale non valida.", "Prezzo nominato non valido (> 1)." Toast "Dutching inviato" ("{n} gambe · book x% · stato") / "Dutching rifiutato" / "Errore dutching". Azione di coda `dutch`.
Fonte: nessuna query propria; `selections` (con back/lay/ltp da `live_now`) e `updatedAt` dalla pagina.

### 4.3 RiskRulesPanel (tab "Risk") — "Automazione Rischio"
Titolo **"Automazione Rischio"** (icona `Crosshair`); sottotitolo "offset · stop-loss · take-profit · trailing · bracket (OCO) — mercato {id}"; "Blocco pannello" + refresh. **Avviso fisso ambra**: "Stop/offset **SOFTWARE-SIDE**: se il runner si ferma **NON sono attivi**. Nessuna protezione lato Betfair — servono runner e connessione vivi."
**Form di arming**: **Selezione** (select `{nome} (#{id})`), **Handicap**, **Tipo regola** (`Offset (presa profitto)` | `Stop-loss` | `Take-profit` | `Trailing-stop` | `Bracket (Offset + Stop OCO)`), **Lato ingresso** (`Back (punta)` | `Lay (banca)`), **Prezzo ingresso** (`*` se obbligatorio, altrimenti "(opz.)"), **Size ingresso (€, opz.)**, **Unità parametro** (`Tick` | `Percentuale (%)` | `Importo P&L (€)` — ammesse per tipo), **Tick|Percentuale (%)|Importo (€)** (per Bracket: "Offset (tick)" / "Offset (%)"), per Bracket **"Stop (tick) *"/"Stop (%) *"** + nota "distanza AVVERSA della gamba stop (OCO)", **Persistenza**, **Attivazione (timing)** (`Immediata (arma subito)` | `Al fill (attende l'ingresso)`), per Stop-loss/Bracket **"Piazza a (tick oltre)"** + nota "a quanti tick oltre chiude, per fill sicuro", **"Al calcio d'inizio (in-play)"** (`Mantieni` | `Annulla` | `Ricalcola (rebaseline)`); se Bracket o timing al fill: **"Ordine d'ingresso (entry_bet_id) *"** (placeholder "es. 3.11223344 (bet id Betfair)") + nota "attende il fill dell'ingresso, niente gamba nuda"; per Offset/Bracket checkbox **"Greening (chiudi pareggiando il profitto su tutte le uscite)"**.
**Anteprima**: riga `Anteprima {Back|Lay} {testo}` es. "target offset a 2.04 (3 tick di profitto)" / "stop scatta a 2.20 (5 tick contro)" / "chiude quando il P&L ≥ €x" + "(stima; il server è autoritativo)"; placeholder "inserisci prezzo/valore per l'anteprima…".
**Arma**: LIVE = checkbox "Confermo regola REALE (soldi veri)"; bottone **"Arma {nome regola}"** (sky per Back, rose per Lay). Errori: "gamba STOP obbligatoria per il bracket…", "entry_bet_id obbligatorio per bracket / timing "al fill"…", "Prezzo d'ingresso non valido (1.01–1000): obbligatorio per questa regola.". Toast "Regola armata" / "Errore arming regola".
**Lista "Regole attive ({n})"** (poll 4 s, mostra ENTRAMBE le modalita'): colonne **Selezione · Tipo (+ badge LIVE rosso / PAPER ambra) · Lato · Ingresso · Parametri · Stato · Azioni**; stati `Armata` (sky) / `Scattata` (ambra) / `Annullata` (grigio) / `Completata` (verde) / `Errore` (rosso); azione **"✕ Disarma"** (solo se armata; in LIVE `confirm("Disarmare la regola #{id}?\n\nATTENZIONE: il disarmo rimuove SOLO la protezione automatica — l'eventuale posizione reale resta APERTA e SENZA stop/uscita. …")`). Tipi aggiuntivi mostrati in lista: `Stop-entry (ingresso condizionale)`, `Chase (insegui il best)`, `Auto-hedge (floor worst-case)`. Vuoto "Nessuna regola su questo mercato."
Fonti: RPC `get_live_risk_rules(p_market_id)` (poll 4 s), `request_live_risk_rule(p)`, `cancel_live_risk_rule(p_id)`.

### 4.4 LiveControlsPanel — "Controlli Runner" (dentro il `<details>` di SeguiLive)
Titolo **"Controlli Runner"** (icona `SlidersHorizontal`) + chip "Globale"; "Kill-switch, limiti operativi e registro eventi — validi per **tutti** i mercati." + refresh.
- **Kill-switch** (bottone largo): disattivo = grigio, icona verde, "Kill-switch disattivato — runner operativo" / "Clic per bloccare immediatamente le aperture (globale); chiusure e cancel restano permessi." + pillola `OFF`; attivo = rosso pulsante "🔴 KILL-SWITCH ATTIVO — aperture rifiutate, chiusure permesse" / "Il runner rifiuta le APERTURE; cancel e chiusure (green-up/cash-out) passano. ⚠ Gli stop/offset SOFTWARE NON scattano finché è attivo." + pillola `ATTIVO`. Disattivare chiede `confirm("Disattivare il KILL-SWITCH globale?\nIl runner tornerà a processare gli ordini.")`. Toast "Kill-switch ATTIVATO" / "Kill-switch disattivato".
- **P&L giornata ({giorno})** (se presente): `{totale}` + "settled {x} · MTM {y}{ · ⚠ stima worst-case}" + a destra "🛑 STOP GIORNALIERO SCATTATO — solo chiusure" / "stop a −€{x}" / "stop giornaliero spento".
- **Limiti & velocità** (griglia 4): "Max esposizione / selezione (€)", "Max ordini / min", "Poll ordini (s)", "Poll rischio (s)", "Stop giornaliero (€ perdita max)" (placeholder "spento"), "Max esposizione / evento (€)", "Max esposizione / campionato (€)" (placeholder "nessun limite"/"default"); nota "Le velocità (poll) si applicano al **RIAVVIO** del runner (come LIVE_ORDER_MODE). Campo vuoto = nessun limite."; bottone **"Salva"** (ambra, icona `Save`); riga "Attivi: esposizione €x · ordini n/min · poll ordini Ns · poll rischio Ns"; toast "Impostazioni salvate" ("Le velocità di poll si applicano al riavvio del runner."). Validazione: ogni valore presente deve essere >0.
- **Registro eventi ({n})** + "● LIVE" (poll 4 s): tabella max-h-80 sticky header: **Ora · Modo · Azione · Mercato / sel. · Lato · Prezzo · Size · Stato · Errore**; stato colorato (DONE/OK/EXECUTION_COMPLETE verde, ERROR/VIOLATION/REJECTED rosso, PENDING/PROCESSING/EXECUTABLE ambra). Errore del registro: "⚠ Registro eventi NON aggiornato: {msg}". Vuoto "Nessun evento registrato."
Fonti: RPC `get_live_settings`, `set_live_settings(p)`, `set_live_kill_switch(p_on)`, `get_live_audit(p_limit=50)`, `betfair_live_risk_state` (SELECT + realtime).

### 4.5 TerminalPositionsRail — colonna SINISTRA del terminal calcio ("My Bets")
Due card (`space-y-3`):
1. (se errore/stantio) banner rosa "⚠ Dati NON aggiornati (ultimo ok hh:mm:ss) — {errore}"; (se cancel fallito) "⚠ Annullamento NON riuscito: {errore} — verifica gli ordini (potrebbe essere ancora sul book)."
2. **"Posizioni · P&L"** (icona `Wallet` ambra, maiuscolo 10px) + a destra etichetta fonte `data-testid="rail-fonte-posizioni"` (`canale` | `db (poll 4 s)`). Tabella: **Selezione · Vince · Perde · Esp.** (title "P&L se la selezione VINCE" / "P&L se la selezione PERDE" / "Esposizione worst-case"); valori con segno (`+x.xx`), emerald/rose/grigio; mostra solo posizioni con esposizione o P&L ≠ 0. Vuoto "Nessuna posizione aperta sul mercato."
3. **"Ordini ({n} attivi)"** (icona `ListOrdered`): righe ordine non abbinato: pillola `BACK` (sky) / `LAY` (rose) + selezione + `{residuo}@{prezzo}` (title "residuo ANCORA VIVO sul book @ prezzo chiesto") + **X** per annullare (aria-label "Annulla ordine {lato} su {sel}", title "Annulla l'ordine (via coda comandi)"; in LIVE `confirm("Annullare l'ordine REALE {LATO} {size}@{prezzo} su "{sel}"?")`); righe abbinate (opacita' 75%): pillola + selezione + `✓ {size}@{prezzo medio}` (title "size abbinata @ prezzo MEDIO dichiarato da Betfair (mai il prezzo chiesto al suo posto)"; `—` se assente: mai "0,00"). Vuoto "Nessun ordine sul mercato."
Fonti: RPC `get_live_orders`/`get_live_positions` (poll 4 s, filtrate per `mode`), push canale `order`/`position`, comando `cancel` via coda.

### 4.6 PlaceConfirmDialog — popup di conferma PLACE (overlay assoluto dentro la card del ladder)
`role=dialog aria-modal` "Conferma ordine {BACK|LAY} {sel}", Esc = annulla. Box `max-w-sm` bordo rosso (LIVE) / ambra (PAPER). Riga titolo: `🛡 {BACK(sky)|LAY(rose)} @ {prezzo} {sel}` + pillola **`REALE`** (rossa) / **`SIMULATO`** (ambra). Campo **"Importo (€)"** (o **"Responsabilità (€)"** per LAY in liability) input numerico autofocus+select, Invio = conferma, bordo rosso se invalido. Due riquadri: **"Se vince"** / **"Se perde"** (`+€x`/`−€x`, verde/rosso, `—` se invalido); riga "Responsabilità: **€x**" e, per lay in liability, "Size: **€x**"; se armati strumenti "Protezioni: {offset 3t green · stop 5t · FoK 5s}". Bottoni **"✓ Conferma REALE"** (rosso) / **"✓ Conferma simulato"** (ambra) e **"✕ Annulla"**. Piede: LIVE "Ordine con SOLDI VERI: verrà inviato a Betfair alla conferma." / PAPER "Ordine simulato (paper): identico al vivo, ma senza soldi veri."

### 4.7 FlussoStreamBanner (`FlussoStreamBanner.tsx`, J2 28/09)
Barra a larghezza piena montata sopra top-bar e ladder: sorgente topic `flusso_stream` del canale del runner (calcio 47331, tennis 47332), ricalcolata ogni 2 s. Due stati (altrimenti non rende nulla):
- **interrotto** (`data-testid="flusso-stream-runner"`, `data-stato="interrotto"`, `role=alert`): `border-red-500/70 bg-red-600/25 text-red-100 animate-pulse`, maiuscolo bold 11px: "⚠ FLUSSO INTERROTTO{ da N s}{ (motivo)}: prezzi FERMI, non sono quelli di Betfair adesso. Nessuna apertura su questi prezzi; riconnessione automatica in corso."
- **non noto** (`data-stato="non_noto"`, `role=status`): ambra `bg-amber-600/20`: "⚠ stato dello stream NON NOTO (canale locale del runner non raggiungibile): i prezzi mostrati potrebbero essere fermi" (canale locale giu').

### 4.8 LiveMarketBoard — "tabellone" (overview sotto il terminal)
- Riga "Aggiornato: {hh:mm:ss}" (allineata a destra, 10px).
- **Tab categoria** (pillole `shrink-0`, attivo `bg-primary text-black`; ciascuna con contatore): **Match Odds · Over/Under · Correct Score · First Half · BTTS · Squadre/Altri** (solo quelle presenti; categorizzazione condivisa col Match Replay).
- Griglia `md:grid-cols-2` di **MarketCard**: card `glass-card` con banner `Chiuso` (grigio) o `Sospeso` (rosso, maiuscolo) sopra; intestazione `{market_name}` + `{market_type}` (maiuscolo) + toggle **`Ladder`** / **`Griglia`** (icone `BarChart3`/`LayoutGrid`; title "Apri la ladder (profondità + trade)" / "Torna alla griglia"; attivo `bg-amber-400 text-black`) che sostituisce la card con un `LadderView` a tutta riga (`md:col-span-2`). Tabella: **Selezione · Back · Lay · LTP**; celle **Back** `bg-blue-500/15 text-blue-200`, **Lay** `bg-pink-500/15 text-pink-200` (prezzo 2 decimali o `—`), LTP muted. Contenuto al 50% di opacita' se chiuso/sospeso.
- Vuoto: "Nessun mercato live disponibile per questa partita al momento."

### 4.9 LiveAlertBanner
Pila di avvisi non gestiti in cima alla pagina (nulla se vuoto): riga `rounded-lg border px-4 py-2.5 text-sm`; **INFO** (`border-white/15 bg-white/[0.06]`), **WARN** (ambra), **CRITICAL** (rosso); contenuto `{LIVELLO}` (maiuscolo bold 10px) + `[codice]` + messaggio + bottone X (aria-label "Ignora avviso"; rimozione ottimistica, se l'ack fallisce l'avviso ricompare). Fonti: RPC `get_live_alerts`, `ack_alert(p_id)`, realtime `live_alerts`.

### 4.10 LiveSignalPanel — "Segnali Motore Live"
Card `glass-card`; testata icona `Cpu` primary + "**Segnali Motore Live**" e a destra l'orario `hh:mm:ss` dell'ultimo segnale oppure "⚠ **motore fermo**" (ambra) se l'heartbeat di `live_now` e' >30 s. Stati: scheletri (3 righe) / "Motore live fermo: nessun segnale fresco da mostrare." (icona `AlertTriangle`) / "Nessun segnale azionabile al momento{ (n in HOLD o su mercati chiusi)}." Con dati: per mercato un riquadro (`rounded-lg border bg-black/30`) con nome mercato + tipo; per riga segnale: nome selezione + **chip direzione** `BACK` (primary, icona `TrendingUp`) / `LAY` (secondary, `TrendingDown`) (HOLD e mercati CLOSED sono nascosti), **barra confidenza** 0-100% (colore secondo direzione), a destra "fair {x} · mkt {y}", "edge **+x.x%**" (verde/rosso), "Kelly **£x.xx**". Piede "{n} segnali nascosti (HOLD o mercati chiusi)". Fonti: SELECT `live_signals` per evento + realtime.

### 4.11 MiniPriceChart (dentro il ladder, bottone `LineChart`)
Pannello a destra del corpo ladder, larghezza fissa 96 px, altezza = 420: candele da 15 s (max 40 = ~10 minuti), emerald-400 se chiusura >= apertura, rose-400 altrimenti, linea tratteggiata ambra sull'ultimo prezzo + etichetta del prezzo; tooltip per candela "{ora} · O h L C". Finche' <2 candele: testo ruotato "raccolgo prezzi…" (title "Il mini-chart si popola con lo storico prezzi da quando il ladder è aperto").

### 4.12 PriceAxisBar (dentro il ladder, bottone `Ruler`)
Barra verticale 16 px a SINISTRA del corpo, scala **1.01-1000** (tutti i tick), 70 zone "heat" (ambra, intensita' ~ concentrazione del denaro back+lay+trade), marker orizzontale ambra sul centro corrente; `role=slider` aria-label "Navigazione prezzo del ladder"; clic/trascina = naviga il ladder (auto-center spento). Title "Scala prezzi 1.01–1000 · heat = dove si concentra il denaro · clic/trascina per scorrere il ladder".

### 4.13 XHedgePanel (tab "X-Hedge") — analisi cross-market dell'evento
Titolo **"X-Hedge (cross-market)"** (icona `Grid3x3`) + ModeBadge; sottotitolo "Copertura sull'intero evento {eventId}{ · N posizioni}{ · agg. hh:mm:ss}" + `data-testid="xhedge-fonte"` " · fonte canale|db" (title "da dove arriva l'analisi: canale del runner (47331, subito dopo la scrittura) o database (poll di ripiego)"). Nota "Analisi cross-market + copertura **1-click** (F39): il bottone "Copri" appare solo con gli ID esatti della gamba Correct Score dal runner, analisi fresca e matrice completa. In LIVE serve la conferma esplicita; FoK 10s se non si abbina."
- Avvisi: errore; **"⚠ Matrice INCOMPLETA: {n} ordine/i matched non modellabili (es. "Any Other" del Correct Score) sono ESCLUSI dai P&L mostrati. Non usare il suggerimento di copertura senza verificare quelle posizioni."** (ambra); "Nessuna analisi x-hedge disponibile per questo evento."
- **Riepilogo** (3 tile): **Peggiore** (icona `TrendingDown` rosa) `{€}` + "risultato {h-a}"; **Medio** (`Sigma`) + "su {n} risultati"; **Migliore** (`TrendingUp` verde) + "risultato {h-a}". Valori verdi se >=0, rosa se <0.
- **Matrice** "P&L per risultato esatto (Casa ↓ / Ospite →)": tabella heatmap (intestazione "C↓ / O→"; celle P&L con tono verde `emerald-500/10..40` / rosso `rose-500/10..40` in 3 intensita'; title "{h}-{a}: {€}").
- **Suggerimento copertura** (box ambra se actionable): "**BACK** Correct Score {h-a} €{size} @ {quota}" + "Peggiore {€} → {nuovo worst} · migliore {€}"; se 1-click disponibile: (LIVE) checkbox "Confermo la copertura con DENARO REALE (one-shot)" + bottone **"Copri (1-click)"** (ambra; disabilitato se analisi stantia >30 s, matrice incompleta o manca conferma; title con "FoK software 10s…"), avviso "analisi stantia — refresh in corso"; altrimenti "⚠️ ID selezione CS non disponibili (riga pre-deploy o scoreline fuori catalogo): piazza manualmente sul mercato Correct Score." / "Modalità OFF: piazza manualmente sul mercato Correct Score."; se non utile: "Nessuna copertura utile al momento.". Importi sotto €2: flusso `place_submin`; altrimenti `place` con `fok_ttl_sec: 10`. Toast "Copertura inviata" / "Copertura RIFIUTATA" / "Matrice INCOMPLETA" / "Suggerimento stantio" / "Conferma REALE richiesta".
- **Auto-hedge** (box viola, solo se PAPER/LIVE e c'e' mercato CS): "Auto-hedge (mantieni il worst-case scoreline)"; se armato: "🛡 ATTIVO: worst-case ≥ −€{floor}{ · coperture n/3}" + "runner attivo richiesto" + **"Disarma"**; altrimenti campi "Perdita worst-case max [es. 20] €", "Max stake/copertura [nessun cap] €", (LIVE) checkbox "Confermo: le coperture verranno piazzate con DENARO REALE senza ulteriore conferma", bottone **"Arma auto-hedge"** (viola) + "copre da solo via coda ordini · mai su matrice incompleta"; regola in errore "⚠ Regola #{id} in ERRORE: …". Toast "Auto-hedge ARMATO" ("Mantiene il worst-case scoreline ≥ −€x (max 3 coperture, cooldown 60s)…") / "Auto-hedge NON armato" / "Auto-hedge disarmato".
Fonti: RPC `get_live_xhedge(p_event_id)` (poll 5 s) + push canale `betfair_live_xhedge` (47331); `get_live_risk_rules`, `request_live_risk_rule` (`auto_hedge`), `cancel_live_risk_rule`, comando `place|place_submin` via coda.

### 4.14 ScalperPanel (tab "Scalper") — Scalper Bot per EVENTO (calcio)
NB: nel sorgente le stringhe contengono caratteri doppiamente codificati (mojibake: "â€¦", "â‚¬", "Ã€", emoji rotte); qui sono riportate nella forma attesa.
Card `rounded-xl border bg-white/5 p-4`. Intestazione: icona `Bot` verde + "**Scalper Bot**" + "pre-match · stop automatico al KO"; a destra badge stato + "servizio ✓" (verde) / "servizio assente?" (rosso; solo se running e heartbeat >30 s) + "ARMATO — nessun ordine" (ambra, se dry_run attivo). Avviso persistente (3 fallimenti): "⚠ Stato scalper NON aggiornato: {msg} — i dati mostrati potrebbero essere vecchi."
**Stati** (`STATUS_STYLE`): `RICHIESTO` (sky), `ARMAMENTO…` (sky), `ARMATO (in attesa)` (ambra), `OPERATIVO` (verde), `CHIUSURA…` (ambra), `FERMATO` (grigio), `COMPLETATO (KO)` (grigio), `ERRORE` (rosso).
- Non attivo: bottone **"▶ Attiva Scalper Bot"** (verde, largo) -> form:
  * 3 card modalita' (selezionata `border-emerald-400`): **Tradizionale** — "Maker neutro validato: cattura lo spread dai due lati" · **Direzionale** — "Solo il lato indicato dai motori (serve consenso ML+Poisson)" · **Entrambe** — "Maker neutro + direzione sulle selezioni con consenso".
  * **Stake €** (2-500, def 25); checkbox **"DEMO · PAPER (ordini SIMULATI, ciclo completo — mai soldi veri)"** (def ON); checkbox **"Missione Tick Pre-Match: al primo ciclo verde il bot smette di aprire (validato: 5/6 eventi col tick in 3-27 min, zero eventi rossi)."** (def ON); checkbox **"⚠️ Gamba INTERVALLO (HT, sperimentale)…"** (def OFF; esclusiva con Sniper/Theta); checkbox **"🎯 SNIPER in-play (S16): 1 tick sull'Under al momento letto dal book (cadenza+coda+spread), poi stop. Backtest: +0.99€/14 eventi, worst −0.49. In DEMO piazza ordini simulati (paper flumine). Alternativo alla gamba HT. ACCESO di default (decisione utente 25/09): si spegne qui, per questa sessione."** (def ON) + **Stake sniper €** (2-100, def 10) + checkbox **"🔫 CACCIA MULTI-LINEA: …"** (def OFF); checkbox **"🔬 THETA in-play (sperimentale): …"** (def OFF; esclusiva) + **Stake theta €** (def 25), **Preset** (`🎯 cecchino (3 step)` | `classico (C7)` | `overshoot (C17)`), **Max colpi** (placeholder 10), **Tetto perdita €** (placeholder 5); se !dry-run: "ORDINI REALI" rosso.
  * **Parametri (default validati in backtest)** (`<details>`): griglia di input numerici (label + hint in tooltip): "Tick di profitto" (1-5, def 1), "Tick di stop" (1-5, def 1), "Flusso min €/lato (90s)" (0-500, def 10), "Size min ai best €" (0-2000, def 300), "Quota min" (1.01-5, def 1.5), "Quota max" (1.5-20, def 4.6), "Stop ingressi (s pre-KO)" (60-1800, def 420), "Chiusura forzata (s pre-KO)" (30-900, def 180), "Target profitto €" (0-50, def 1; "col cricchetto: raggiunto, i profitti sono protetti (0=off)"), "Tetto perdita €" (0-20, def 1.5; "al tocco: chiude tutto (force-flat). 0=off"); link "Ripristina i default validati".
  * Bottoni **"Attiva in PAPER (simulato)"** / **"Attiva ORDINI REALI"** (verde, icona `ShieldCheck`) e **"Annulla"**. Gate: con THETA e !dry-run toast "THETA solo PAPER: non validato out-of-sample (verdetto S4). Riattiva "Solo ARMATO (nessun ordine reale)" per armarlo."; con ordini reali `confirm("⚠️ ATTIVARE LO SCALPER CON ORDINI REALI su "{evento}"?\n\nIl bot piazzerà scommesse REALI su Betfair in autonomia (stake €{stake}).\n…Confermi?")`. Toast "Scalper ATTIVATO in PAPER (ordini simulati) — {evento}" / "Attivazione fallita: {msg}".
- Attivo: riga modalita' (badge) + "stake €{n}" + errore; box **Motori** (solo Direzionale/Entrambe): "consenso: {direzione}" / "nessun consenso → neutro", "edge x.x%", motivi `• …`; **tile statistiche** (grid 3/6): "Ordini (sim)|Ordini", "Cicli", "Catture", "Scratch", "Stop", "P&L bloccato (lordo)" (title "P&L LORDO: commissione Betfair (4,5-5%) NON detratta"), "P&L settlato (lordo)"; **missione**: "Tick pre-match ✓|—", "Tick intervallo ✓|—", "P&L pre-match", "P&L intervallo"; **theta** (viola): "Theta colpi/verdi/scratch/dry-fire", "P&L theta (lordo)", "Theta settl. (lordo)"; **feed attivita'** (max-h-40, "Nessuna attività ancora…"); bottone destructive **"Ferma lo scalper (chiude flat)"** (toast "Stop richiesto: chiusura flat in corso… se una posizione resta aperta comparirà un errore").
- Ultima sessione (stopped/done/error): "Ultima sessione: **{stato}** — cicli n, catture n, P&L bloccato (lordo) €x, settlato (lordo) €y — {errore}".
Fonti: RPC `get_scalper_state(p_event_id,p_activity_limit=40)` (poll 4 s), `scalper_activate(p_event_id,p_mode,p_dry_run,p_stake,p_params)`, `scalper_stop(p_event_id)`.

### 4.15 SelectionChartPanel (tab "Chart") — candele + volume + VWAP per selezione
Contenitore `rounded-md border border-slate-800 bg-slate-900/50`. Header: **select "Selezione"** (aria-label) + gruppo **Timeframe** (aria-label "Timeframe"): **5s · 15s · 30s · 1m · 5m** (attivo `bg-slate-700`; default 15 s calcio, **5 s tennis**). Riga "Aggiornato: hh:mm:ss{ (canale|DB)}" (9px). Finche' <2 candele: "raccolgo prezzi… (campioni dal vivo da quando il pannello è aperto)". Con dati: SVG candele (max 48; emerald-500 su / rose-500 giu'; stoppini), linea **VWAP** ambra 2px, griglia + 3 tick puliti sull'asse Y destro (mono), crosshair tratteggiato con snap, **pannello volume** separato (h-12, barre slate-500), tooltip: ora · "O {} · H {} · L {} · C {}" · "Vol € {}" · "VWAP {}". aria-label "Candele prezzo della selezione con VWAP" / "Volume tradato per candela". Storia solo da quando il pannello e' aperto (buffer in memoria). Fonti: `ladderSource` (come LadderView).

### 4.16 DepthPanel (tab "Depth" / "Profondità totale")
Intestazione "**Profondità totale**" + selettore finestra **10s · 30s (def) · 60s** (title "finestra del delta flusso"). Per selezione una card: nome | "book {x}% back · {y}% lay" / "book vuoto"; due barre di depth cumulata (segmenti per livello con gap 2px, title "@{prezzo}: €{size} (cum €{cum})") **BACK** (sky `bg-sky-500/70`) e **LAY** (pink `bg-pink-500/70`) con totali `€n`; riga "Flusso {N}s" con `back ±€x` / `lay ±€x` (verde/rosa; `—` se storia insufficiente); **alert order-flow** (indizi, mai prove): "🎭 possibile muro finto {BACK|LAY} @ {prezzo}: −€x non consumati" (fucsia), "⚖ shift WOM {+|−}Npp in 30s (pressione BACK|LAY)" (ambra), "⚡ picco volume: €x nell'ultimo minuto ({k×}|da fermo)" (arancio). Vuoto "nessun book disponibile". Nota "Flusso calcolato client-side dai sample del ladder da quando il pannello è aperto."

### 4.17 StandaloneLadder — ladder autosufficiente (popout e multi-ladder)
Dato `{sport,eventId,marketId,...}`: **tennis** -> monta `TennisLadderColumn`; **calcio** -> legge `live_now` (SELECT + realtime, DELETE -> modalita' OFF) per `order_mode`, nome mercato, selezioni fallback e monta `LadderView sport="calcio"` con `ladderSource=sorgenteLadderAlMs('calcio')`, `popout`, `multiSlot`. **Fail-safe**: senza stato live la modalita' resta OFF, MAI derivata dall'URL.

### 4.18 HabitatCard — "Partite adatte allo scalper" (lista di Segui Live)
Card `rounded-xl border bg-white/5 p-3`, poll 60 s su RPC `get_scalper_state('habitat',1)` (ultimo `habitat_scan`). Stati: "Habitat scan…" (spinner) / "Habitat scan non disponibile: avvia il servizio scalper (avvia_scalper_service.bat) — la classifica appare qui da sola." / lista. Testata: icona `Target` verde + "**Partite adatte allo scalper**" + "scan {hh:mm:ss}". Se nessun GO: "Nessun habitat GO nelle prossime ore — meglio non forzare." Righe GO (verde): evento, "KO {hh:mm} · €{tv} scambiati · best €{depth} · spread {n}tk · osc {n}", badge **"GO {score}"**; in coda "Scartate: {evento (verdetto)} · …" (max 4).

---

# PARTE III — PAGINE DI SUPPORTO LIVE

## 5. MultiLadder (`pages/MultiLadder.tsx`, 187 righe) — `/multi-ladder`
**Scopo**: workspace libero con N ladder affiancati (anche di mercati/eventi/SPORT diversi); layout persistito in `localStorage['multiLadder:slots']`. **Cap `MAX_SLOTS` = 8**; id slot deterministico `{sport}:{marketId}` (niente duplicati).
**Struttura**
1. **Top bar sticky** (`px-3 py-2 bg-black/80 backdrop-blur`, riga flex): link `← Segui live` (muted, 11px) -> `/segui-live`; icona `Layers` ambra + "**Multi-ladder**" + contatore `{n}/8`; spaziatore; bottone **"+ Aggiungi ladder"** (ambra, `border-amber-400/40 bg-amber-400/10`; disabilitato a 8 slot con title "Massimo 8 ladder", altrimenti "Aggiungi il ladder di un mercato (eventi calcio seguiti)").
2. **Picker** (se aperto; card `glass-card m-3 p-3`): testo "Eventi calcio seguiti (i mercati **tennis** si aggiungono dal Trading Terminal tennis col bottone [icona Layers])."; stato "Carico gli eventi seguiti…" (spinner) / "Nessun evento seguito attivo."; pillole evento `{home} — {away}` (solo follow PENDING/STREAMING; selezionato `bg-primary text-black`); dopo il clic: "Carico i mercati…" poi bottoni mercato `+ {market_name}` (gia' presente: `✓ {nome}`, disabilitato, title "Già nel workspace"; altrimenti title "Aggiungi {nome}"); "Nessun mercato pubblicato per l'evento."
3. **Griglia ladder**: workspace vuoto -> "Workspace vuoto. Usa **Aggiungi ladder** qui sopra, oppure il bottone [icona Layers] su un ladder di Segui live / Tennis terminal."; altrimenti `flex flex-wrap gap-3`, ogni slot `min-w-[400px] max-w-[560px] flex-1`: riga titolo `🎾|⚽ {eventName||eventId}` (title "{evento} · {mercato}") + `BetfairMediaButtons compact` + **X** (title "Rimuovi dal workspace") e sotto `StandaloneLadder` (tennis -> `TennisLadderColumn`; calcio -> `LadderView`).
**Fonti**: RPC `get_live_follows`; SELECT `live_now` per evento (mercati); per ogni slot le fonti di `StandaloneLadder` (live_now/tennis_live_now, ladder, ordini). Modalita' ordini risolta per-evento, fail-safe OFF.

## 6. LadderPopout (`pages/LadderPopout.tsx`, 49 righe) — `/ladder-popout`
**Scopo**: finestra dedicata a UN ladder (multi-monitor). Parametri: `sport` (def `calcio`), `market`, `event`, `name`, `eventName`, `p1`, `p2`. Aperta da `window.open(..., 'popup=yes,width=560,height=860,resizable=yes,scrollbars=yes')`.
**Struttura**: `min-h-screen bg-background p-2`; se mancano `market`/`event`: "Parametri mancanti: servono `market` ed `event`." (centrato muted); altrimenti barra minima (`px-1 pb-1`): `{eventName||marketName}` (11px muted, troncato) a sinistra e `BetfairMediaButtons compact` a destra; poi `StandaloneLadder` (sez. 4.17). Nessuna nav.

## 7. MarketWatch (`pages/MarketWatch.tsx`, 475 righe) — `/market-watch`
**Scopo**: Market Watch multi-evento stile Fairbot: una riga per evento seguito con stato, P&L MTM, esposizione worst-case e (solo calcio) cash-out EVENTO. **Due sezioni separate** (regola d'oro: tennis e calcio non condividono mai dati).
**Struttura**
1. **Top bar sticky**: link `← Terminal` -> `/segui-live`; icona `Eye` ambra + "**Market Watch**"; a destra "modalità ordini: **{OFF|PAPER|LIVE}**" (LIVE rosso, PAPER sky, OFF grigio; modalita' = `order_mode` del primo evento calcio attivo che la pubblica, fail-safe off).
2. Contenitore `p-3 space-y-4 max-w-[1400px]`.
3. **Sezione "⚽ Calcio"** (h2): "Carico gli eventi seguiti…" / "Nessun evento calcio seguito."; per ogni follow PENDING/STREAMING (refetch 30 s) una `Card glass-card px-3 py-2` flex wrap:
   - **Nome**: `{home} – {away}` (12px bold) + lega (`league_name` o `—`, 10px muted).
   - **Badge stato**: se in-play `LIVE {minuto}' · {sh}–{sa}` (verde `bg-emerald-500/15`); `SOSPESO` (rosso) se un mercato e' SUSPENDED; altrimenti countdown (grigio) `tra {n}m` / `tra {h}h {m}m` / `in avvio` / data `gg/mm hh:mm`.
   - **MTM** (w-28, title "P&L MTM se si greenasse ORA ai prezzi correnti"): "MTM" + `MtmDueModi` (`data-testid="mw-mtm-modi"`): righe separate `live` (rosso, `mw-mtm-live`) e `prova` (grigio, `mw-mtm-paper`), mai sommate; valore `+€x.xx`/`−€x.xx` verde/rosso, `—` se nessuna posizione, `…` se non caricate, **⚠** ambra se ci sono posizioni senza prezzo (title "{n} posizioni non valutabili (prezzo mancante)").
   - **Rischio** (w-32, title "Esposizione worst-case aggregata (Σ selection_exposure), soldi veri e prova separati"): "Rischio" + `RischioDueModi` (`mw-rischio-modi`): `live €x` (`mw-rischio-live`) e `prova €x` (`mw-rischio-paper`).
   - **"Cash-out EVENTO"** (ambra; disabilitato se OFF, manca mercato o altro cash-out in corso; title OFF "Modalità ordini OFF: nessun comando possibile" / "Nessun mercato pubblicato per l'evento" / "Cash-out di TUTTI i mercati dell'evento ({MODO})"); conferme: `confirm('Cash-out EVENTO su "{evento}" ({MODO}): appiattisce TUTTI i mercati dell'evento. Confermi?')` e in LIVE `confirm('⚠️ MODALITÀ LIVE — SOLDI VERI. Confermi il cash-out TOTALE dell'evento "{evento}"?')`; esito sotto la riga: "Cash-out accodato ✓" (verde) / "Errore: …" (rosso).
   - link **"Apri terminal"** (sky) -> `/segui-live`; `BetfairMediaButtons compact`.
4. **Sezione "🎾 Tennis"**: "Carico i match tennis seguiti…" / "Nessun match tennis seguito."; per ogni follow tennis: nome `{player1} vs {player2}` + `competition_name`; badge: **`FINITA{ · set_summary}`** (grigio, `data-testid="mw-tennis-finita"`, quando stato IPS finito/`closed` o Match Odds CLOSED) / **`LIVE{ · set_summary}`** (verde, `mw-tennis-live`) / countdown; stesse celle **MTM** e **Rischio** (da `get_tennis_live_positions_all`); al posto del cash-out un trattino `—` (title "Cash-out non disponibile: il worker tennis non supporta il cash-out" — capability gating); link **"Apri terminal tennis"** -> `/tennis/terminal?event=&market=&name=&p1=&p2=` (o "terminal n/d" se non c'e' mercato); `BetfairMediaButtons compact`.
**Fonti**: calcio RPC `get_live_follows` (30 s), SELECT+realtime `live_now` per evento, push canale 47331 `now` e `position` ("il piu' recente vince"), RPC `get_live_positions_event` per evento (poll 10 s), comando `cashout_event` (coda). Tennis RPC `get_tennis_follows` (30 s), SELECT+realtime `tennis_live_now`, push canale 47332 `now`/`position`, RPC `get_tennis_live_positions_all` (poll 10 s).

## 8. LivePnl (`pages/LivePnl.tsx`, 500 righe) — `/live-pnl`
**Scopo**: P&L di giornata con fonti tracciabili. Una modalita' alla volta (paper | live, mai "tutte"); il MTM/totale esiste solo per OGGI.
**Struttura**
1. **Top bar sticky**: `← Terminal` -> `/segui-live`; icona `TrendingUp` ambra + "**P&L di giornata**"; spaziatore; campo **"Giorno"** (`input type=date`, default oggi locale); select **"Mode"** (`paper` | `live`; di serie la modalita' del runner dal risk state, poi live).
2. **Riga KPI** (4 tile `Card` `min-w-[160px] flex-1`, label 11px + valore `text-2xl` tabular):
   - **"P&L realizzato"** — Σ profit dei mercati regolati nel giorno e nel mode (verde/rosso; title "Σ profit dei mercati regolati ({n} mercati, fonte get_live_settled)"; `…` in caricamento).
   - **"MTM aperto ({mode runner})"** (+ " ⚠" se il mode del runner e' diverso dal filtro) — `risk.open_mtm` solo oggi, altrimenti `—`; sotto: `data-testid="livepnl-posizioni"` "{n} posizioni aperte · rischio €x ({mode})" + `data-testid="livepnl-fonte-posizioni"` " · fonte canale|db (poll 15 s)".
   - **"Totale giornata ({mode runner})"** — `risk.total` solo oggi.
   - **"Stop giornaliero"** — `€{limite}` o `—`; sotto pillola rossa pulsante **"SCATTATO"** o "non scattato".
3. **Card "Equity intraday"** — "Equity intraday (P&L realizzato cumulato{ · punto ambra = totale con MTM})": SVG a GRADINI 760x220 (verde se ultimo cumulato >=0, rosso altrimenti; area al 10%; linea dello zero tratteggiata; griglia; 3 tick Y a destra in `±€x`; 3 tick X orari; cerchio ambra = totale con MTM; crosshair + tooltip "hh:mm · ±€x"); vuoto "nessun mercato regolato nella giornata"; caricamento "Carico i mercati regolati…".
4. **Due card affiancate** (`md:grid-cols-2`): **"Per mercato"** (tabella **Mercato · Evento · P&L · Fonte · Ora**; Fonte = pillola **`simulato`** sky / **`reale`** rossa; ordinate per ora decrescente; vuoto "Nessun mercato regolato.") e **"Per evento"** (**Evento · Mercati · P&L**, ordinate per profitto).
5. **Card "🎾 Tennis (posizioni aperte)"**: avviso ambra "il settled tennis non è ancora storicizzato — qui SOLO le esposizioni aperte (get_tennis_live_positions_all)"; tabella **Evento · Posizioni · Σ esposizione · Σ net** (per evento, filtrata sul mode); "Carico le posizioni tennis…" / "Nessuna posizione tennis aperta."
Note di colore: profitto `text-emerald-400`, perdita `text-red-400`, importi formattati `+€x.xx` / `−€x.xx`.
**Fonti**: RPC `get_live_settled(p_from,p_to)` (poll 30 s), `betfair_live_risk_state` (SELECT + realtime), RPC `get_live_positions_all` (poll 15 s) + RPC `get_tennis_live_positions_all` (poll 15 s) con sovrapposizione dei push `position` dei canali 47331/47332.

---

# PARTE IV — TRASVERSALE

## 9. FONTI DATI (riepilogo per blocco)

**Canali locali WebSocket** (app desktop, `lib/localChannel.ts`, token di sessione `?t=` solo sui canali che comandano; fuori dall'app il canale e' di sola lettura e gli ordini vanno sulla coda DB; riconnessione con backoff 1-5 s; richieste con timeout 10 s). Porte: calcio **47331**, tennis **47332** (comandi + push), mike 47333, omega 47334, safe 47335 (solo push), scanner 47336, **tennis_bot 47337**, scalper 47338. Topic push usati da queste pagine: `hello` (modalita'), `ladder`, `now` (riga `live_now`/`tennis_live_now`), `order`, `position`, `flusso_stream`, `betfair_live_xhedge`, `board` (Board, fuori perimetro), `tennis_bot_stato` / `tennis_bot_posizioni` (47337). Politica: canale = via principale al tick, DB = ripiego automatico (ladder: se canale assente o muto >4 s; cache invalidata alla caduta, mai un book congelato spacciato per vivo). Chip UI "⚡ LOCALE" quando connesso.

| Blocco UI | Fonte |
|---|---|
| Tennis: lista partite | RPC `get_tennis_fixtures`; realtime `tennis_markets` |
| Tennis: stato/ punteggio/ order_mode | `tennis_live_now` (SELECT + realtime) + push `now` 47332 |
| Tennis: ladder | `tennis_live_ladder` (SELECT + realtime) + push `ladder` 47332 |
| Tennis: ordini/posizioni | RPC `get_tennis_live_orders/positions`, realtime `tennis_live_orders/positions`, push `order/position`; comandi RPC `request_tennis_live_order` + `get_tennis_live_order` |
| Tennis: follow / REC | RPC `get_tennis_follows`, `tennis_follow_event`, `tennis_set_follow_record` |
| Tennis: bot per evento | RPC `get_tennis_bots_state`, `tennis_bot_arm`, `tennis_bot_disarm`; realtime `tennis_bot_control` / `tennis_bot_activity` |
| Tennis: bot come servizio | RPC `get_tennis_bot_services`, `tennis_bot_service_activate/stop/update_params/set_uscite`, `get_tennis_bot_daily`, `get_tennis_bot_orders_today`; canale 47337 |
| Tennis: refresh quote on-demand (lib) | RPC `request_tennis_refresh`, `get_tennis_refresh_request`, `get_tennis_full_odds` |
| Calcio: lista seguiti | RPC `get_live_follows`; realtime `live_follow`; REC `set_follow_record` |
| Calcio: mercati/quote/ order_mode/ minuto/ score | `live_now` (SELECT + realtime) + push `now` 47331 |
| Calcio: ladder | `live_ladder` (SELECT + realtime) + push `ladder` 47331 |
| Calcio: ordini/posizioni | RPC `get_live_orders/positions/positions_event/positions_all`, realtime `betfair_live_orders/positions`, push `order/position`; comandi RPC `request_betfair_live_order` + `get_betfair_live_order` |
| Calcio: segnali | `live_signals` (SELECT + realtime) |
| Calcio: regole di rischio | RPC `get_live_risk_rules`, `request_live_risk_rule`, `cancel_live_risk_rule` |
| Calcio: X-Hedge | RPC `get_live_xhedge`; push `betfair_live_xhedge` |
| Calcio: controlli runner | RPC `get_live_settings`, `set_live_settings`, `set_live_kill_switch`, `set_live_order_mode`, `get_live_audit` |
| Calcio: P&L giornata / stop | `betfair_live_risk_state` (SELECT + realtime); RPC `get_live_settled` |
| Calcio: saldo / battito | `betfair_live_account`, `betfair_live_heartbeat` (SELECT + realtime) |
| Calcio: alert | RPC `get_live_alerts`, `ack_alert`; realtime `live_alerts` |
| Calcio: scalper / habitat | RPC `get_scalper_state`, `scalper_activate`, `scalper_stop` |
| Journal / replay (link) | `get_live_journal`, `set_live_journal_note`, `list_replays`, `get_replay`… (pagine fuori perimetro) |
| Preferenze solo-browser | localStorage: `tennis.favorites`, `workspace:{eventId}` (centerView, mercato attivo, pannelli), `live.terminal.tool.{eventId}`, `multiLadder:slots`, `gridStake:{sport}`, profilo colonne per-sport (`ladderConfig`), macro `servants` |

## 10. SCORCIATOIE DA TASTIERA (riepilogo)
Default (`lib/workspace.ts`, `DEFAULT_KEYBINDINGS`): `b` BACK preset · `l` LAY preset · `c` annulla sotto il cursore · `g` green-up/cash-out mercato · `x` cash-out evento · `↑`/`↓` vista 1 tick · `+`/`-` stake ± · `s` prossimo preset · `Spazio` ricentra · `PageUp`/`PageDown` mercato prec./succ. · `Esc` kill-switch · `1`-`9` macro (servants). Gestione: B, L, C, frecce, +/-, S, Spazio, 1-9 nel **LadderView** (sul ladder puntato dal mouse); G, X, Esc, PageUp/PageDown nella **pagina SeguiLive** (`LiveTradingSection`). Non attive in modalita' OFF, mai dentro input/textarea/select/contenteditable, mai con Ctrl/Meta/Alt; B/L/C/frecce/Spazio/+/-/S/1-9 sono sospese con barra/popup di conferma aperti. Nota: il terminal TENNIS non monta la gestione G/X/Esc/PageUp-Down (le tiene la pagina SeguiLive), quindi nel tennis valgono solo le hotkey del ladder.

## 11. DATA-TESTID DA PRESERVARE (elenco completo trovato nei file in perimetro)
| data-testid | Dove |
|---|---|
| `tennis-pro-superficie` | TennisBotPanel, card Tennis Pro |
| `cr-tennis-params-trigger-{botKey}` | TennisBotServiceParamsSheet (default; sovrascrivibile da prop) |
| `params-sheet`, `params-group` (+`data-group`), `params-choice`, `params-clamped` (+`data-field`), `params-dirty`, `params-save`, `params-reset`, `params-esito` (+`data-esito`) | ParamsSheetBase (foglio parametri bot) |
| `torna-control-room` | SeguiLive, bottone "Torna alla Control Room" |
| `origine-follow` | LiveMatchCard, pillola auto/manuale |
| `flusso-stream-runner` (+`data-stato=interrotto|non_noto`) | FlussoStreamBanner |
| `ltp-fonte-posizioni` | LiveTradingPanel (fonte canale/db) |
| `rail-fonte-posizioni` | TerminalPositionsRail |
| `xhedge-fonte` | XHedgePanel |
| `mw-mtm-modi`, `mw-mtm-live`, `mw-mtm-paper`, `mw-rischio-modi`, `mw-rischio-live`, `mw-rischio-paper`, `mw-tennis-finita`, `mw-tennis-live` | MarketWatch |
| `livepnl-posizioni`, `livepnl-fonte-posizioni` | LivePnl |
| (Control Room, per i bot tennis) `cr-bot-riga-{id}`, `cr-bot-stato-{id}`, `cr-bot-modalita-{id}`, `cr-bot-pnl-{id}`, `cr-ferma-{id}`, `cr-a-paper-{id}`, `cr-a-live-{id}`, `cr-conferma-live-{id}`, `cr-avvia-paper-{id}`, `cr-avvia-live-{id}`, `cr-conferma-avvio-live-{id}`, `cr-ferma-tutti`, `cr-pannello-bot`, `cr-pannello-bot-gruppo-tennis` | PannelloBot (fuori perimetro, citati per i 4 bot) |
Nota: i pulsanti dei ladder/griglia e delle pagine tennis NON hanno `data-testid`: si identificano per `aria-label` / `aria-pressed` / testo (es. aria-label "Aggiungi ai preferiti", "Cambia sport", "Watchlist", "Report Personale", "Analytics", "Logout", "frazione cash-out", "Configura colonne del ladder", "tick offset", "tick stop", "tick chase", "secondi FoK", "numero ordini scala", "passo tick scala", "slot macro", "nome macro", "Selezione", "Timeframe", "Navigazione prezzo del ladder", "Ignora avviso", "Floor auto-hedge (euro)", "Max stake per copertura (euro)"). I test esistenti (`*.test.tsx`) usano queste chiavi.

## 12. COSA NON HO POTUTO VERIFICARE / PUNTI DI ATTENZIONE
1. **Nessun rendering reale**: non ho avviato l'app ne' guardato le pagine; tutto e' ricavato dal sorgente. Colori `bg-*/NN` sono le classi Tailwind del sorgente, non i valori calcolati dal tema.
2. **Mojibake in `ScalperPanel.tsx`**: il file e' salvato con doppia codifica UTF-8 (byte `c3 a2 e2 80 a6` al posto di "…", ecc.). A video le etichette del pannello Scalper appaiono corrotte ("Stake â‚¬", "ARMAMENTOâ€¦", "Attivazione…", emoji rotte, "Ã " al posto di "à"). In questo inventario sono riportate nella forma voluta. Da correggere in fase di ridisegno/implementazione (e' un difetto reale del sorgente, non dell'inventario).
3. **Incoerenza cromatica PAPER** gia' presente: PAPER = ambra nei pannelli a card larga (Trading/Dutching/Risk/X-Hedge, ModeBadge) e nel terminal tennis (`PAPER · SIMULATO`), sky nel top-bar di SeguiLive (`PAPER`), verde nel ladder e nella griglia (badge `PAPER`/`paper`). Il prototipo dovrebbe scegliere UN colore; non l'ho cambiato.
4. **Incoerenza stile**: `GridView`, `SelectionChartPanel` usano la palette `slate-*` (non `white/..`) e il tema scuro "slate"; gli altri pannelli usano `glass-card` + `white/10`.
5. **Funzioni non lette**: i corpi di `lib/ladderMath` (`lockedPnlAt`, `placeProjection`, `piqAhead`, `windowAround`, `flashDir`, `nextPreset`), `lib/priceAxis`, `lib/ladderChart`, `lib/kellySuggest`, `lib/fairOverlay` (formato di `fmtEvAt`: nel LadderView l'EV appare come `B…`/`L…`), `lib/matchClock` (formato esatto di `countdownToOff`/`formatMinute`/`formatScore`), `lib/preGoal` (soglie dei livelli `amber`/`red`) e `lib/eventPnl` non sono stati letti per intero: i numeri/formati che producono sono descritti solo come usati dalla UI.
6. **`ParamsSheetBase`** (foglio laterale usato dai 4 bot tennis nella Control Room) l'ho letto solo per le sezioni con testo/test-id; ho verificato titolo, descrizione, trigger "Parametri", pulsanti, ma non il testo esatto di `T.salva`/`T.resetParams` (costanti di traduzione): vedi `components/trading/ParamsSheetBase.tsx` e il modulo `T`.
7. **Control Room (`PannelloBot`, `ControlRoom`)**: inclusa solo per localizzare i 4 bot; non e' stata inventariata a fondo (non e' nel perimetro). Il numero di righe/stati mostrati li' (modalita', arretrati, "fermato all'avvio dell'app: attivazione manuale richiesta", `InterruttoreUscite`) va preso dall'inventario della Control Room.
8. **Pagine fuori perimetro raggiungibili** da questi schermi: `/board`, `/trade-journal`, `/match-replay`, `/control-room`, `/omega`, `/dashboard`, `/select-sport`, `/watchlist`, `/report-personale`, `/analytics`: non lette.
9. **Righe `LadderView`**: i numeri di riga del task (1301 per SeguiLive) non coincidono col file (~1245-1300 con CRLF); ho letto il file per intero, non cio' che sta oltre il footer `export default LadderView`.
10. **Tennis: bot "armato per evento" vs "servizio"**: nel terminal l'armatura e' per evento (`tennis_bot_arm`); lo stesso bot ha anche l'interruttore di SERVIZIO nella Control Room. Le due viste usano la stessa chiave `bot_key` ma tabelle diverse (`tennis_bot_control` per evento, `tennis_bot_service_control` per servizio): migrazione `tennis_bot_service_control_2026-09-17.sql` (citata nei commenti) non verificata come applicata.
11. **Chart tennis**: `TennisTerminal` imposta bucket 5 s ma nel pannello non c'e' etichetta "tennis": non c'e' nessuna differenza visiva per lo sport, solo il bucket iniziale.
12. **Nessuna scorciatoia G/X/Esc nel terminal tennis**: verificato leggendo `TennisTerminal`/`TennisLadderColumn` (non montano il listener); le hotkey del ladder (B/L/C/frecce…) funzionano invece anche sul tennis.

---

# RIASSUNTO PER IL PROTOTIPO (cosa serve disegnare)
- **Tennis Dashboard**: nav tennis + header "Partite del Giorno ." + pillole Ieri/Oggi/Domani + accordion tornei con righe match (stella, ora, IN CORSO/PRE-MATCH, 2x[back sky | lay rose], volume, "APRI TERMINAL").
- **Tennis Terminal**: header compatto (score, OFF in, badge ordini, SEGUI/SEGUITA, REC) + 3 colonne 340/fluida/360: 4 card bot (Scalper/Pro/FLB/Swing con stake, dry-run, parametri, ARMA/DISARMA, stats) + equity + attivita'; ladder (Ladder|Grid, B/L overlay, drag-to-move) ; tab Stats/Chart/Depth.
- **Segui Live (calcio)**: lista card partita -> terminal con top bar sticky (modalita', LOCALE, orologio, P&L giorno, saldo, runner, exp, over-round, agg., Cash-out MERCATO/EVENTO, KILL), tab mercati, 3 zone 290/fluida/400 (rail posizioni+ordini | ladder/grid | 7 tab strumenti), controlli runner collassabili, tabellone mercati + segnali motore.
- **Multi-ladder / Popout / Market Watch / Live P&L**: come sezioni 5-8.
