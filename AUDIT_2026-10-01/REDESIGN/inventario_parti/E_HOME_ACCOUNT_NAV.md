# E - Home (Board), accesso/account, navigazione, app desktop, lib/hooks/RPC

Inventario in SOLA LETTURA del 01/10/2026, estratto dal codice. Tutti i percorsi sono sotto `frontend/src/` salvo diversa indicazione. Nessun file del progetto e' stato modificato.

---------------------------------------------------------------------
## 1. BOARD - `pages/Board.tsx` (304 righe) - «Programma di oggi»

### 1.1 Come l'app desktop arriva a /board
- `desktop/main.js` -> `createWindow()`: `BrowserWindow` 1600x900, sfondo `#0b1220`, titolo «AlphaScore Trading», carica `http://127.0.0.1:47330/board` (UI statica servita da un mini server HTTP interno che serve `frontend/dist`, fallback a `index.html` per le rotte SPA).
- `/board` e' dentro `ProtectedRoute` (App.tsx r.116-123). `ProtectedRoute` (`components/ProtectedRoute.tsx`): durante `loading` mostra spinner centrato (Loader2); se non c'e' sessione Supabase O l'email non e' `isOwnerEmail` (unica ammessa: `daniele.ritrovato@gmail.com`, `lib/auth-config.ts`) fa `<Navigate to="/" replace />` (landing).
- Quindi: sessione Supabase gia' salvata (localStorage dell'origine `127.0.0.1:47330`) -> si vede subito il Board. Nessuna sessione -> landing `/` (login) -> dopo il login `navigate('/select-sport')` (NON torna a /board).
- `LandingPage`: se `user` presente e owner, `navigate('/select-sport', {replace:true})` (di nuovo NON /board).
- **Fatto verificato**: nessun link, pulsante o `navigate` in tutto `frontend/src` punta a `/board` (grep: solo la definizione di rotta in App.tsx e il commento di Board). Il Board e' raggiungibile SOLO all'avvio dell'exe o digitando l'URL; dal Board si esce, ma dalle altre pagine non si torna al Board.
- Browser web (non desktop): la rotta esiste ma i canali locali sono `off` (vedi 1.4), quindi si vede lo stato vuoto «Canale locale ... non attivo».

### 1.2 Struttura, nell'ordine, della pagina
Sfondo `bg-background`, griglia `grid-pattern` fissa (opacity 30%), titolo documento «Programma di oggi | Alpha Score».

1. **Navbar sticky** (altezza 64px, `border-b`, sfondo nero/50 blur):
   - sinistra: link brand «AI **TERMINAL**» (`/dashboard`); a seguire (solo >= md) etichetta con icona calendario «PROGRAMMA» (testo non cliccabile, colore primary).
   - destra, tre bottoni outline: «🛡️ Safe Strategy» (`/safe-strategy`), «Segui Live» (`/segui-live`), «‹ Dashboard» (`/dashboard`, icona ChevronLeft).
   - **Assenti nel Board**: pulsante CONTROL ROOM, email utente, «Esci»/logout, Omega, Mike, Tennis, Watchlist, Report, Analytics, Cambia sport.
2. **Intestazione** (container max-w-5xl): `h1` «Programma di **oggi**» (oggi in colore primary); sottotitolo 11px: «Tabellone in tempo reale dal canale locale del runner (push 'board', nessuna lettura DB).»
3. **Tab sport** (barra con bordo inferiore): due bottoni `aria-pressed`: «⚽ Calcio» e «🎾 Tennis». Tab attiva: bordo inferiore primary, testo bianco, sfondo bianco/6%; inattiva: trasparente, testo muted. Ogni tab ha un **pallino stato canale** (1.5px): verde emerald se canale `connected`, grigio slate se `off`; tooltip «Canale locale connesso» / «Canale locale non attivo». Tab iniziale: Calcio. Il cambio tab rimonta `SportBoard` (`key={sport}`).
4. **Corpo `SportBoard`** (uno degli stati sotto).

Non ci sono filtri, ricerca, ordinamento manuale, raggruppamento per campionato/torneo, paginazione, ne' selezione data: solo le due tab sport. Ordinamento fisso per `open_date` crescente.

### 1.3 Stati del corpo (testi esatti)
Tutti in card scura centrata (`glass-card border-white/10 bg-slate-900 p-8`), testo 11px slate-400:
- **Canale off**: icona Radio grande grigia + «Canale locale {calcio|tennis} non attivo (ws://127.0.0.1:{47331 calcio | 47332 tennis}). Avvia l'app desktop / il runner {sport} per il programma in tempo reale.» Quando il canale passa a `off` il tabellone in memoria viene azzerato (rows=null): mai tabellone vecchio.
- **Canale connesso ma nessun push ancora**: «Canale connesso: in attesa del primo tabellone…»
- **Push ricevuto con lista vuota**: «Nessun evento nel programma di oggi.»
- **Lista**: righe (sotto).

### 1.4 Riga evento (una per evento, `space-y-1.5`)
Contenitore: riquadro bordato `rounded-lg border-white/10 bg-slate-900 px-3 py-2`, flex con wrap, testo 11px. Da sinistra a destra:
1. **Colonna orario** (min 64px): ora d'inizio `HH:MM` (it-IT, mono, tabular) da `open_date`; sotto, uno tra:
   - se `inplay`: «● IN-PLAY» (9px, nero bold, emerald, `animate-pulse`);
   - altrimenti, se esiste countdown: «OFF in {countdown}» (9px mono, amber, tooltip «Countdown all'off»). Formato (`lib/matchClock.countdownToOff`): `Ng HHh` se >= 1 giorno, `H:MM:SS` se >= 1 ora, `MM:SS` altrimenti; nulla se l'orario e' passato. Si aggiorna ogni 1 s (setInterval).
   - orario non valido -> «—».
2. **Colonna evento** (flex-1, min 180px): nome evento (`event_name`, bold, truncate, tooltip nome); sotto riga 9px mono slate-500: `status` del mercato (es. OPEN/SUSPENDED, vuoto se null) + se `total_matched` != null: ` · €{importo arrotondato, separatore it-IT}`.
3. **Quote** (fino a 3 selezioni, `selections.slice(0,3)`): per ogni selezione una cella (min 72px, centrata): nome selezione (10px slate-400, truncate max 90px, tooltip nome) sopra; sotto `back / lay` in mono 11px: back in **sky-300**, separatore « / » slate-600, lay in **rose-300**. Prezzo formattato a 2 decimali, «—» se null o <= 1. Il campo `ltp` arriva nel dato ma NON viene mostrato. Calcio = 1X2 (casa/pareggio/trasferta, tre celle); tennis = testa a testa (due celle). Nomi presi da `selections[].name` cosi come arrivano.
4. **Azione «Segui live»**, diversa per sport:
   - **Tennis**: bottone verde pieno piccolo (h-6, emerald-600) con testo «Segui live» -> chiama `followTennisEvent(event_id, market_id)` (RPC `tennis_follow_event`), tooltip «Registra l'evento al follow tennis (tennis_follow_event): il runner lo prende in carico». Stati: durante la chiamata disabilitato; a successo il testo diventa «✓ Seguito» (resta, nessun ritorno) + toast successo «Evento registrato al follow tennis» (descrizione: nome evento); in errore: toast errore «Follow tennis non riuscito» (descrizione: messaggio o «errore sconosciuto») e il bottone torna cliccabile. Accanto, link bordato «Terminal →» (tooltip «Apri il Tennis Trading Terminal su questo match») verso `/tennis/terminal?event=<id>&market=<id>&name=Match Odds&p1=<sel0>&p2=<sel1>`.
   - **Calcio**: solo link bordato «Segui live →» verso `/segui-live` (NESSUNA registrazione follow dal Board: tooltip «La registrazione del follow calcio non è esposta da questa pagina: apri Segui Live (i follow nascono da watchlist/runner)»). Non passa l'evento.
5. **`BetfairMediaButtons compact`** (`eventId`): pulsante diviso 📺 | 📊 (vedi 2.8).

Nel Board NON ci sono: punteggio, minuto di gioco, stella watchlist, stato dei bot, P&L, linee/capacita', pulsante per aprire la scheda partita (`/dashboard?fixture=`).

### 1.5 Fonte dati e canali locali
- Dati SOLO dal topic **`board`** del canale locale WebSocket del rispettivo sport: `getLocalChannel(sport).subscribe('board', cb)` con payload `{rows: BoardRow[]}`. Nessuna lettura DB per il tabellone (le uniche chiamate Supabase della pagina sono `tennis_follow_event` e, via `useAuth`/ProtectedRoute, la sessione auth).
- Porte (`lib/localChannel.ts` PORTS): calcio **47331**, tennis **47332** (WS `ws://127.0.0.1:<porta>`; con token `?t=` solo sui canali che comandano). Riconnessione con backoff 1 s -> 5 s (+1 s a tentativo). Stato via hook `useLocalStatus(sport)` ('connected'|'off', definito in `lib/localTransport.ts`).
- Forma `BoardRow`: `event_id, event_name, open_date (ISO), market_id, status|null, inplay (bool), total_matched|null, selections[{selection_id, name, back|null, lay|null, ltp|null}]`.
- Produttore lato Python (`Betfair/stream/board_worker.py`, fuori scope UI, solo per capire la cadenza): pubblica `ch.publish("board", {"rows": rows})` a ogni giro (intervallo `BOARD_POLL_SEC` default 10 s nel runner calcio); catalogo del giorno ricaricato ogni 300 s; prezzi dal feed dello scanner Safe Strategy se la riga e' fresca, altrimenti REST di fallback ogni 60 s; non fa nulla se il desktop non e' collegato.
- `lib/matchClock.ts` fornisce il countdown; `lib/tennis.ts` la RPC follow; `components/ui/{button,card}` (shadcn); toast `sonner`.

---------------------------------------------------------------------
## 2. ACCESSO E PAGINE DI SERVIZIO

### 2.1 App.tsx (rotte)
Provider: React Query, HelmetProvider, TooltipProvider, Toaster (sonner), BrowserRouter, `SafeStrategyProvider` (valuta i segnali Safe anche da altre pagine; toast «🛡️ {variante} — {titolo}» con descrizione «{partita} · {contesto} · @quota · abbinabili €...» e azione «Apri» -> `/safe-strategy`, durata 20 s, non mostrato se si e' gia' su /safe-strategy).
Rotte pubbliche: `/` (LandingPage), `/check-email`, `/reset-password`, `*` (NotFound).
Rotte protette (ProtectedRoute): `/select-sport`, `/dashboard`, `/tennis`, `/tennis/terminal`, `/analytics`, `/watchlist`, `/report-personale`, `/segui-live`, `/board`, `/market-watch`, `/live-pnl`, `/trade-journal`, `/multi-ladder`, `/ladder-popout`, `/match-replay`, `/omega`, `/safe-strategy`, `/mike`, `/control-room`, `/storico/calcio`, `/storico/tennis`.

### 2.2 LandingPage (`pages/LandingPage.tsx`, rotta `/`)
Se `loading` non rende nulla. Se utente owner loggato -> redirect `/select-sport`. Blocchi nell'ordine: HeroSection, StatsBar, SystemWorkflow, FeaturesGrid, DashboardPreview, PricingCard, AuthSection, LandingFooter. I bottoni CTA fanno scroll morbido alla sezione auth.

**HeroSection** (`components/landing/HeroSection.tsx`): sezione a tutta altezza nera con immagine di sfondo `/futuristic-football-game-ball.jpg` (opacity 60%) + gradiente nero da sinistra + griglia. Navbar assoluta: logo `/alpha_score_logo_full.png` (alt «Alpha Score», click -> `window.location.href='/'`), a destra (>= md) «Login» (scroll all'auth) e «Register» (**nessun onClick**: bottone inerte). Colonna sinistra: badge «Data-Driven Football Analysis»; titolo «Alpha **Score**» (Score in gradiente primary->emerald); sottotitolo «Non scommettere. **Investi.**» (Investi in secondary); paragrafo «Il primo algoritmo a **3 Livelli** che trasforma le scommesse in asset finanziari. Smetti di giocare d'azzardo. Inizia ad operare con metodo.»; bottoni «INIZIA ORA» (primary, scroll all'auth) e «Accedi alla Dashboard» (ghost, scroll all'auth). Colonna destra vuota (lascia vedere l'immagine).

**StatsBar**: card con 4 statistiche: «50.000+ Pronostici Generati», «87% Accuratezza Media», «120+ Campionati Analizzati», «Real-Time Aggiornamento Dati»; nota «* Valori dimostrativi basati su backtesting storico».

**SystemWorkflow**: titolo «Il Protocollo **Alpha**»; testo «Non ci fidiamo di un solo modello. Processiamo ogni partita attraverso **3 livelli di validazione** prima di darti un consiglio.»; 3 card numerate collegate da frecce: (1) «Livello 1: L'Algoritmo» / «Deep Data Analysis» / «Analisi di 200+ metriche: xG, Poisson, Form State e trend statistici puri.» (blu, icona Database); (2) «Livello 2: La Storia» / «Historical Validation» / «Il database confronta il pronostico con 10 anni di storico: è già successo? Con che esito?» (verde, TrendingUp); (3) «Livello 3: Il verdetto» / «AI Financial Advisor» / «L'AI confronta i dati dell'algoritmo con i dati storici e news in tempo reale come infortuni, meteo, o imprevisti dell'ultimo minuto e ti consiglia le scelte statisticamente più probabili per quello specifico evento.» (viola, Sparkles).

**FeaturesGrid**: titolo «Perché Alpha Score?»; sottotitolo «Non siamo un altro sito di statistiche. Siamo il tuo vantaggio competitivo. Saprai esattamente come affrontare ogni investimento con i dati dalla tua» (la frase e' troncata nel sorgente); 4 card: «Edge Matematico» (Brain; «Algoritmo + Database + Intelligenza Artificiale, nessuna opinione personale solo dati e scelte consapevoli.»), «Copertura Globale» (BarChart3; «1200+ Campionati monitorati H24. Dalla Premier League alla Serie B brasiliana, non ti perdi mai un'occasione di profitto.»), «Gestione del Rischio» (Shield; «Il sistema a 3 livelli filtra i falsi positivi. Non cerchiamo di indovinare tutto, ma di proteggere il tuo capitale nel lungo periodo.»), «Risparmio di Tempo» (Zap; «Da 4 ore di studio a 30 secondi. Tu devi solo decidere l'investimento, a tutta l'analisi complessa ci pensiamo noi.»).

**DashboardPreview**: card con a sinistra «Una Dashboard Completa / Per Ogni Partita» e 6 punti con spunta: «Pronostico AI con advice e percentuali 1X2», «Statistiche dettagliate Home vs Away», «Grafici goals by minute e cards heatmap», «Confronto squadre con matrice comparativa», «Distribuzione Under/Over per soglia», «Head-to-Head e ultimi 5 match». A destra mock: badge HOME / «VS» / badge AWAY; tre riquadri «1 45%», «X 28%», «2 27%»; tre barre di avanzamento (75/60/85%); nota «Preview dimostrativa».

**PricingCard**: badge «PROVA GRATUITA», «€0», «per 7 giorni, poi €9.99/mese», elenco con spunta: «Accesso completo alla dashboard AI», «Pronostici illimitati», «Tutti i campionati», «Aggiornamenti in tempo reale», «Grafici e heatmap interattivi», «Supporto via Telegram»; bottone «Registrati Ora» (scroll all'auth).

**AuthSection** (`id="auth-section"`, card max-w-md): `Tabs` «Registrati» | «Accedi» (tab iniziale: Registrati; la LandingPage non passa `defaultTab`, quindi si apre su **Registrati** anche se l'utente vuole accedere).
- Tab **Registrati**, campi (react-hook-form + zod): Nome * (placeholder «Mario», 1-50), Cognome * («Rossi», 1-50) affiancati; Email * (type email, «mario@email.com», valida, max 255); Telefono * (type tel, «+39 333 1234567», 6-20); Telegram (opzionale) («@username», max 50); Password * («Min. 8 caratteri», min 8); Conferma Password * («Ripeti password», deve coincidere: «Le password non coincidono»); checkbox «Accetto i Termini e Condizioni e la Privacy Policy» (obbligatoria: «Devi accettare i termini»). Messaggi: «Nome obbligatorio», «Cognome obbligatorio», «Email non valida», «Telefono non valido», «Minimo 8 caratteri». Bottone «Inizia la Prova Gratuita» (loading: spinner + «Registrazione...»). Comportamento reale (early access): NON crea alcun account; tenta `insert` best-effort nella tabella `leads` (first_name, last_name, email, phone, telegram_username, source='landing_page'), poi apre sempre il dialogo «non pronti».
- Tab **Accedi**: Email («mario@email.com»), Password («La tua password», messaggio «Password obbligatoria»), link-testo «Password dimenticata?» (allineato a destra), bottone «Accedi» (loading «Accesso...»). Login: se l'email non e' dell'owner -> dialogo «non pronti» senza interrogare Supabase; altrimenti `supabase.auth.signInWithPassword`, toast «Login effettuato» e `navigate('/select-sport')`; errore: toast «Errore Login» («Credenziali non valide o errore di connessione.»). «Password dimenticata?»: se email vuota toast errore «Inserisci la tua email prima di richiedere il reset.»; se non owner -> dialogo non pronti; altrimenti `resetPasswordForEmail(email, {redirectTo: origin + '/reset-password'})`, toast «Email di reset inviata!» («Controlla la tua casella di posta (anche Spam).») o errore «Errore nell'invio dell'email di reset.».
- **Dialogo early access** (icona razzo): titolo «Non siamo ancora pronti», testo «Ti avviseremo quando lo sapremo! Per tutte le info segui le nostre pagine social.», bottone «Ho capito» (testi in `lib/auth-config.ts`).

**LandingFooter**: «© 2025 Alpha Score — Don't bet. Invest.»; tre voci inerti (non sono link, nessun handler): «Privacy Policy», «Termini», «Contatti».

### 2.3 SelectSport (`pages/SelectSport.tsx`, `/select-sport`) - «Scegli lo Sport»
Titolo documento «Scegli lo Sport | Alpha Score». Navbar sticky 64px: «AI **TERMINAL**» (non cliccabile), a destra: email utente (>= md), bottone pieno oro «CONTROL ROOM» (`/control-room`, `data-testid nav-control-room`, aria «Apri la Control Room»), bottone ghost rosso al hover «Esci» (icona LogOut; `supabase.auth.signOut()` poi `navigate('/')`). Corpo: `h1` «Scegli lo **sport**», sottotitolo «Seleziona il terminale operativo su cui vuoi lavorare.» Griglia (1 col mobile, 2 col md, 5 col xl) di 5 grandi card-bottone (animazione di ingresso scaglionata, hover alza di 6px, label aria «Apri sezione {titolo}»), ognuna con riquadro emoji 80x80, titolo, sottotitolo, «Entra →»:
| Card | Emoji | Sottotitolo | Destinazione | Accento |
|---|---|---|---|---|
| Football | ⚽ | Partite del Giorno · motori AI · trading live | `/dashboard` | verde (primary) |
| Tennis | 🎾 | Betfair Exchange · ladder pro · bot trading | `/tennis` | oro (secondary) |
| Omega | Ω | Correct Score · obiettivo €/giorno · set-and-forget | `/omega` | verde |
| Safe Strategy | 🛡️ | Segnali live calcio + tennis · ingresso sempre manuale | `/safe-strategy` | oro |
| Mike | 🎯 | Under 3.5 / Over 4.5 · green-up e cash-out · paper-first | `/mike` | teal |
Piè di pagina: «© {anno} Alpha Score AI. All rights reserved.» Nessun link a Board, Segui Live, Watchlist, Report, Analytics, Match Replay da qui.

### 2.4 CheckEmail (`pages/CheckEmail.tsx`, `/check-email`)
Pagina centrata con griglia e gradiente. Icona busta animata (ping). Titolo «Controlla la tua email»; testo «Ti abbiamo inviato un link di conferma. Clicca sul link per attivare il tuo account.» Tre passi numerati: 1 «Apri la tua casella di posta» / «Cerca l'email di conferma»; 2 «Clicca su "Conferma Email"» / «Si aprirà una pagina di conferma»; 3 «Accedi alla Dashboard» / «Il tuo account è pronto!» Avviso spam: «Non trovi l'email? Controlla la cartella **Spam** o **Promozioni**.» Bottoni: «Torna alla Home» (`/`) e «Non hai ricevuto l'email?» (`/`, stesso effetto). Nota: nessun codice del frontend naviga a `/check-email` (la registrazione e' chiusa): pagina oggi raggiungibile solo digitando l'URL.

### 2.5 ResetPassword (`pages/ResetPassword.tsx`, `/reset-password`)
Destinazione del link email di recovery (il client Supabase elabora il token dall'URL). Stati: **checking** (spinner + «Verifica del link in corso…», max 3 s), **invalid** (titolo «Link non valido o scaduto», avviso «Il link di reset è scaduto o è stato già usato. Richiedine uno nuovo dalla schermata di accesso con "Password dimenticata?".», bottone «Torna al login» -> `/`), **ready** (titolo «Imposta nuova password», «Scegli una nuova password per il tuo account.»). Form: «Nuova password» (placeholder «Min. 8 caratteri», min 8 «Minimo 8 caratteri»), «Conferma password» («Ripeti password», «Le password non coincidono»); bottone «Salva nuova password» (loading «Aggiornamento…»). Successo: `supabase.auth.updateUser({password})`, toast «Password aggiornata!» («Ora puoi accedere con la nuova password.»), poi `navigate('/dashboard')`. Errore: toast «Errore aggiornamento password». Icona chiave in alto.

### 2.6 NotFound (`pages/NotFound.tsx`, `*`)
Pagina centrata: icona triangolo di avviso arancione pulsante, «404» (grande, font orbitron), «La pagina che stai cercando non esiste o è stata spostata.», bottone arancione «Torna alla Home» (`/`).

### 2.7 ProtectedRoute
Vedi 1.1. Spinner a tutto schermo con Loader2 arancione durante il caricamento sessione; reindirizza a `/` senza messaggio se non autorizzato. Hook `useAuth` (`hooks/useAuth.ts`): `{user, session, loading}` da `supabase.auth.onAuthStateChange` + `getSession()`.

### 2.8 BetfairMediaButtons (`components/BetfairMediaButtons.tsx`)
Pulsante unico diviso a meta', bordato, sfondo nero/30: **[📺 Video | 📊 Stats]**. Con `compact` solo le icone (h-6); altrimenti con parola (« Video», « Stats», h-7). Props: `eventId`, `compact`, `className`, `media` ({video: bool|null, viz: bool|null}). Se Betfair dichiara video non disponibile (`media.video===false`) la meta' 📺 resta cliccabile ma opacita' 40% con tooltip «Betfair non offre il video live per questo evento: il popup apre animazione/statistiche»; se `media.video===true` tooltip «Video live Betfair disponibile (stream ufficiale)»; ignoto: «Video live Betfair (stream ufficiale, dove disponibile)». 📊: tooltip «Statistiche partita Betfair (+ Visualizzazione partita: tutte le tab del popup ufficiale)» o, se non disponibile, «Betfair non offre animazione/statistiche per questo evento». Click: `openBetfairPopout(eventId, 'liveVideo'|'matchStats')` -> finestra `https://www.betfair.it/exchange/plus/pop-out-live-stream/<eventId>?feedType=...`, 640x780, nome finestra stabile per evento+feed (un secondo click la riporta davanti); `stopPropagation/preventDefault` (non fa scattare i click della riga). Se il popup e' bloccato: toast «Popup bloccato dal browser» («Consenti i popup per questo sito per aprire video e statistiche Betfair.»). Usato in: Board, TennisMatchesList (riga evento), MarketWatch, LadderPopout (barra minima), altri pannelli live.

---------------------------------------------------------------------
## 3. NAVIGAZIONE ATTUALE (mappa)

### 3.1 Stili di header presenti (non c'e' un menu globale unico)
1. **Navbar «inline» AI TERMINAL** (copiata in ogni pagina): brand «AI **TERMINAL**» a sinistra (link a `/dashboard` salvo diversa indicazione) + etichetta pagina con icona (solo >= md) + bottoni outline a destra. Pagine: Board, Analytics, Watchlist, ReportPersonale, SeguiLive, MatchReplay (link), Dashboard (div cliccabile), SelectSport (brand non cliccabile).
2. **TennisNav** (`components/tennis/TennisNav.tsx`): brand cliccabile -> `/tennis`; etichetta sezione («TENNIS» o «TERMINAL») con icona Activity; opzionale bottone «indietro» (`onBack`, default testo «Torna alle partite»; sul terminal «Torna alla Control Room» se `from=control-room`); a destra: «Cambia sport» (`/select-sport`), «Watchlist» (`/watchlist`), «Report» (`/report-personale`), «Analytics» (`/analytics`), email (>= lg), «Esci» (signOut -> `/`). Usato da TennisDashboard e TennisTerminal (anche nello stato «Nessun match selezionato»). NON ha il pulsante CONTROL ROOM.
3. **BotHeader** (`components/trading/BotHeader.tsx`) per Omega, Safe Strategy, Mike (dentro `PageShell`): brand «AI **TERMINAL**» -> `/select-sport`; nome bot con simbolo (da `BOT_IDENTITY`); badge stato servizio (con «SENZA BATTITO» rosso se heartbeat vecchio); slot `health`, `extra`; a destra: `storico` (StoricoLink compatto), `modeToggle` (ModeToggle PAPER/LIVE), `params` (foglio parametri), bottone Avvia/Ferma (testi `T.start`/`T.stop`, data-testid bot-start/bot-stop). Nessun link a altre pagine oltre brand e Storico.
4. **Testata Control Room** (`pages/ControlRoom.tsx` `Testata`): link «AI Terminal» (11px, uppercase) -> `/dashboard`; «CONTROL ROOM»; data del giorno; fascia soldi veri; freni (stop perdita); Runner calcio e Runner tennis; chip dei bot; feed quote scanner; bottone ricarica. Nessun menu verso le altre pagine (le uscite sono i link dentro le schede, vedi tabella). Bordo/sfondo arancione quando almeno un bot e' LIVE.
5. **Top bar «minimale»** (MarketWatch, LivePnl, TradeJournal, MultiLadder): una riga sticky con link «‹ Terminal» (o «‹ Segui live» in MultiLadder) -> `/segui-live` + titolo pagina con icona.
6. **PageShell/Testata dello Storico** (`pages/StoricoSport.tsx`): link «‹ Control Room» (`/control-room`), titolo «STORICO CALCIO|TENNIS», link «passa al tennis|calcio» (`/storico/<altro>`).
7. **Pagine senza navbar**: LandingPage, CheckEmail, ResetPassword, NotFound, LadderPopout (solo barra minima con nome mercato e BetfairMediaButtons).

### 3.2 Pulsanti/link per pagina (testo -> destinazione)
**/ (Landing)**: Login / INIZIA ORA / Accedi alla Dashboard / Registrati Ora -> scroll alla sezione auth; logo -> `/`; login riuscito -> `/select-sport`; «Password dimenticata?» -> email con link a `/reset-password`.
**/select-sport**: card Football -> `/dashboard`; Tennis -> `/tennis`; Omega -> `/omega`; Safe Strategy -> `/safe-strategy`; Mike -> `/mike`; «CONTROL ROOM» -> `/control-room`; «Esci» -> `/`.
**/board**: brand AI TERMINAL -> `/dashboard`; «🛡️ Safe Strategy» -> `/safe-strategy`; «Segui Live» -> `/segui-live`; «‹ Dashboard» -> `/dashboard`; riga tennis «Terminal →» -> `/tennis/terminal?...`; riga calcio «Segui live →» -> `/segui-live`; (tennis «Segui live» = azione RPC, non navigazione).
**/dashboard** (calcio, Partite del Giorno + dettaglio partita; `?fixture=<id>&from=...`): brand (click) -> torna alla lista (stato interno `viewMode=list`); in modalita' dettaglio: «‹ Torna alle partite» (lista), «‹ Torna a Watchlist» (`/watchlist`, se `from=watchlist`), «‹ Torna a Omega» (`/omega`, se `from=omega`), «‹ Torna alla Control Room» (`/control-room`, se da control-room). Barra a destra sempre: «CONTROL ROOM» (`/control-room`), «Cambia sport» (`/select-sport`), «Watchlist» (`/watchlist`), «Report» (`/report-personale`), «Analytics» (`/analytics`), «Segui Live» (`/segui-live`), «Match Replay» (`/match-replay`), email, «Esci» (-> `/`). Nel codice, oltre ai bottoni a destra, ci sono i bottoni «Torna ...» visibili solo >= md (versione mobile in pagina: «Torna alla lista», «Torna a Watchlist»).
**/tennis** (TennisDashboard, «Tennis · Partite del Giorno»): TennisNav (brand -> `/tennis`, Cambia sport, Watchlist, Report, Analytics, Esci); ogni riga match: «APRI TERMINAL» -> `/tennis/terminal?event=&market=&name=Match Odds&p1=&p2=`.
**/tennis/terminal**: TennisNav con «indietro» («Torna alle partite» -> `/tennis`; «Torna alla Control Room» -> `/control-room` se `from=control-room`); senza parametri: «Nessun match selezionato. Torna alle Partite del Giorno» (link-testo -> `/tennis`).
**/segui-live**: brand -> `/dashboard`; «Market Watch» (su mobile «MW») -> `/market-watch`; «P&L» -> `/live-pnl`; «Journal» -> `/trade-journal`; «Match Replay» -> `/match-replay`; «‹ Dashboard» -> `/dashboard`; condizionali: «‹ Torna a Omega» (`/omega`, se `from=omega`), «‹ Torna alla Control Room» (`/control-room`, se `from=control-room`); tab con link `<a href="/multi-ladder">` «⧉ Multi-ladder» (ricarica piena, non router) -> `/multi-ladder`.
**/market-watch**: «‹ Terminal» -> `/segui-live`; per riga calcio «Apri terminal» -> `/segui-live`; per riga tennis «Apri terminal tennis» -> `/tennis/terminal?...` (o «terminal n/d» se manca il mercato).
**/live-pnl**: «‹ Terminal» -> `/segui-live`. **/trade-journal**: «‹ Terminal» -> `/segui-live`. **/multi-ladder**: «‹ Segui live» -> `/segui-live`. **/ladder-popout**: nessuna navigazione (finestra stacca-ladder aperta da `LadderView` con `window.open('/ladder-popout?...', 'ladder_<marketId>', 'popup=yes,width=560,height=860,...')`).
**/match-replay**: brand -> `/dashboard`; «Segui Live» -> `/segui-live`; «‹ Dashboard» -> `/dashboard`.
**/watchlist**: brand -> `/dashboard`; «Report» -> `/report-personale`; «‹ Dashboard» -> `/dashboard`; (dentro WatchlistPanel) per riga «apri» -> `/dashboard?fixture=<id>&from=watchlist`.
**/report-personale**: brand -> `/dashboard`; «Watchlist» -> `/watchlist`; «‹ Dashboard» -> `/dashboard`.
**/analytics**: brand -> `/dashboard`; «‹ Dashboard» -> `/dashboard`.
**/omega, /safe-strategy, /mike**: BotHeader (brand -> `/select-sport`; Storico calcio -> `/storico/calcio`; Safe: Storico tennis -> `/storico/tennis` quando il tab e' tennis). Omega: dal pannello Missione, azioni per partita -> `/segui-live?event=<id>&from=omega` (dopo `omega_mission_follow`) e `/dashboard?fixture=<id>&from=omega`. Safe: toast globale «Apri» -> `/safe-strategy`.
**/control-room**: brand-link «AI Terminal» -> `/dashboard`; riga «Questa pagina mostra solo la giornata di oggi. I giorni precedenti:» + `StoricoLink` (due pulsanti «Storico calcio» `/storico/calcio` e «Storico tennis» `/storico/tennis`, o uno solo se e' selezionato un solo sport); icona matita nella fascia stop -> `/segui-live` (modifica stop giornaliero); per partita (`AzioniPartita`): «Statistiche» -> `/dashboard?fixture=<id>&from=control-room`; «Trading» -> `/tennis/terminal?event=&market=&name=Match Odds&from=control-room&p1=&p2=` (tennis) oppure, dopo `omega_mission_follow` (idempotente), `/segui-live?event=<id>&from=control-room` (calcio); prima di partire viene salvato un «punto di ritorno» (`lib/ritorno.ts`, sessionStorage, valido 15 min: rotta, scheda, evento, scorrimento) che i pulsanti «Torna alla Control Room» usano per riportare alla stessa scheda/riga.
**/storico/calcio|tennis**: «‹ Control Room» (`/control-room`), «passa al tennis|calcio» (`/storico/<altro>`), in fondo «‹ Torna al banco della giornata» (`/control-room`) e «{icona} Storico {altro sport}».
**/check-email, /reset-password, 404**: tutti verso `/` (reset riuscito -> `/dashboard`).

### 3.3 Matrice «da dove si raggiunge cosa» (solo via pulsanti/link dell'UI)
| Destinazione | Raggiungibile da |
|---|---|
| `/` | Esci (SelectSport, Dashboard, TennisNav), CheckEmail, ResetPassword, NotFound, redirect di ProtectedRoute |
| `/select-sport` | Login riuscito, redirect Landing, Dashboard «Cambia sport», TennisNav «Cambia sport», brand BotHeader (Omega/Safe/Mike) |
| `/dashboard` | SelectSport (Football), brand di Board/Analytics/Watchlist/Report/SeguiLive/MatchReplay/ControlRoom, «‹ Dashboard» (Board, SeguiLive, MatchReplay, Watchlist, Report, Analytics), ResetPassword, deep link `?fixture=` da Watchlist, Omega, Control Room, bot Telegram |
| `/tennis` | SelectSport (Tennis), brand TennisNav, «Torna alle partite» sul terminal |
| `/tennis/terminal` | TennisDashboard «APRI TERMINAL», Board «Terminal →», MarketWatch «Apri terminal tennis», Control Room «Trading» (tennis) |
| `/omega`, `/mike` | SelectSport; Omega anche da «Torna a Omega» (Dashboard, SeguiLive con `from=omega`). Mike: SOLO SelectSport |
| `/safe-strategy` | SelectSport, Board «🛡️ Safe Strategy», toast globale «Apri» |
| `/control-room` | SelectSport e Dashboard (pulsante «CONTROL ROOM»), «Torna alla Control Room» (Dashboard, SeguiLive, TennisTerminal), Storico («Control Room», «Torna al banco della giornata»). NON da Board, TennisNav, BotHeader |
| `/segui-live` | Dashboard, Board (barra e riga calcio), MarketWatch/LivePnl/TradeJournal/MultiLadder (indietro), MatchReplay, Control Room (Trading calcio e matita stop), Omega (Missione) |
| `/market-watch`, `/live-pnl`, `/trade-journal` | SOLO SeguiLive (barra alta) |
| `/multi-ladder` | SOLO SeguiLive (tab «⧉ Multi-ladder») |
| `/match-replay` | Dashboard, SeguiLive |
| `/watchlist` | Dashboard, TennisNav, Report, Dashboard-dettaglio «Torna a Watchlist» |
| `/report-personale` | Dashboard, TennisNav, Watchlist |
| `/analytics` | Dashboard, TennisNav |
| `/storico/calcio|tennis` | Pulsanti StoricoLink in Control Room, Omega, Safe, Mike e PosizioniChiuse; link incrociati fra i due storici |
| `/board` | NESSUN link: solo avvio dell'app desktop (URL iniziale) |
| `/check-email` | NESSUN link (solo URL diretto) |

### 3.4 Anomalie di navigazione osservate (fatti)
- Board non raggiungibile dal resto dell'app; l'avvio desktop apre /board ma dopo un login passa da /select-sport.
- Tre «Home» diverse: brand -> `/dashboard` (la maggior parte), -> `/select-sport` (BotHeader), -> `/tennis` (TennisNav), nessuno -> `/board`.
- CONTROL ROOM come pulsante solo in SelectSport e Dashboard; Mike e le pagine bot non hanno link diretto alle altre sezioni (solo brand -> select-sport).
- Pagine ModeBanner/ModeToggle LIVE/PAPER non presenti nel Board, Dashboard, SelectSport, TennisNav.
- Il brand cliccabile in Dashboard fa solo `setViewMode('list')`, non naviga.
- Hero «Register» e le tre voci del footer sono elementi senza azione.

---------------------------------------------------------------------
## 4. APP DESKTOP ELECTRON (`desktop/`, non esiste `electron/`)

File: `package.json` («alphascore-desktop», productName «AlphaScore Trading», v1.1.0, electron ^33, electron-builder: target win nsis+portable, `appId com.alphascore.trading`, main = `bootstrap.js`), `bootstrap.js` (l'exe carica sempre il `desktop/main.js` VIVO del repo: ogni modifica attiva al riavvio senza ricompilare), `main.js` (~1000 righe), `preload.js`.

- **Menu**: nessun menu applicazione definito (nessun `Menu`/`setApplicationMenu`, nessun tray, nessun `ipcMain`); solo `autoHideMenuBar: true` sulle finestre Betfair. Il menu di default di Electron resta quello del framework.
- **Finestra principale**: 1600x900, fondo `#0b1220`, titolo «AlphaScore Trading», `contextIsolation:true`, `nodeIntegration:false`, preload che espone SOLO `window.alphascoreCanale = {token}` (token di sessione dei canali locali, 64 hex, passato come `--alphascore-canale-token=` agli argomenti; senza token i comandi `order` sul canale sono rifiutati e la UI usa la coda DB).
- **UI servita** da `http://127.0.0.1:47330` (mini server statico su `frontend/dist`); all'avvio `ensureFreshUi()` ricostruisce `dist` con `npm run build` se i sorgenti sono piu' recenti (timeout 10 min; se fallisce, dialogo errore «AlphaScore — build UI fallita» e serve la versione precedente). Se il repo (`.venv` + `frontend/dist`) non si trova: dialogo «AlphaScore Trading — repo non trovato».
- **Finestre secondarie / popout**: `setWindowOpenHandler` della principale: (a) URL `https://*.betfair.(it|com)/` -> finestra Betfair propria (`openBetfairWindow`): 640x780 di default (o `width/height` dalle features), fondo nero, titolo «Betfair», sandbox, menu nascosto, una sola finestra per `frameName` (se esiste la riporta davanti/ripristina), attesa fino a 8 s che l'SSO sia pronto prima di aprirla; (b) URL `http://127.0.0.1:47330/...` (es. **`/ladder-popout`** aperto da LadderView) -> `allow` con le stesse webPreferences della UI (preload+token), cosi' il popout parla anch'esso col canale; (c) altri http(s) -> browser di sistema; (d) altro -> negato.
- **SSO web Betfair** (per video/statistiche gia' loggati): login interattivo (`identitysso.betfair.it/api/login`) con fallback `certlogin`, cookie `ssoid` impostato su `.betfair.it`/`.betfair.com`, keep-alive ogni 15 min, retry 30/60/120/300 s, credenziali da `.env` (BETFAIR_APP_KEY/USERNAME/PASSWORD/CERT_FILE/KEY_FILE/IDENTITY_URL).
- **Processi figli avviati all'apertura** (`startRunners`, python del `.venv`, via `Betfair.stream.watchdog`): `runner-calcio`, `runner-tennis`, `scalper-service`, `tennis-bot-service --bridge-only`, `safe-strategy-service`, `omega-service`, `safe-strategy-bot`, `mike-service`, e `tennis-odds` (`betfair_tennis_odds.py`, ogni 30 minuti, salta il giro se ancora in corso). Env passate ai figli: `APP_BOOT_ID`, `LOCAL_CHANNEL_TOKEN`, `LIVE_ORDER_QUEUE_POLL_SEC=0.15`, `LIVE_LADDER_PUBLISH_SEC=0.3`, `TENNIS_LADDER_PUBLISH_SEC=0.3`, `TENNIS_ORDER_POLL_SEC=0.15`, `LIVE_RISK_ENGINE_POLL_SEC=0.15`, `LIVE_RUNNER_KEEP_ALIVE=1`, `TENNIS_LIVE_ORDER_MODE` (default **PAPER** se non impostata), UTF-8. Log dei figli su `_logs/<label>_<timestamp>.log`, tenuti 7 giorni.
- **Chiusura**: alla chiusura dell'ultima finestra, arresto ordinato: scrive il file `ARRESTO` (cartella `_live_raw/_arresto` o `APP_ARRESTO_DIR`), attende l'uscita volontaria di ogni figlio (25 s; scalper 70 s), poi `taskkill /T /F` sui rimasti. Il file ARRESTO e' cancellato all'avvio.
- **Cosa il desktop NON mostra** in UI: nessuna finestra/tray/notifica nativa con lo stato dei runner; tutto lo stato e' reso dalla UI web (sotto).

### 4.1 Stato dei runner e dei canali locali mostrato in UI
- Porte canali (`lib/localChannel.ts`): **calcio 47331** (runner, comandi+push), **tennis 47332** (runner), **mike 47333**, **omega 47334**, **safe 47335** (bot, sola lettura), **scanner 47336** (`scan_calcio`/`scan_tennis`/`scanner_stato`), **tennis_bot 47337** (`tennis_bot_stato`/`tennis_bot_posizioni`), **scalper 47338** (`scalper_stato`/`scalper_sessioni`). UI statica su 47330 (non e' un canale). Topic dei runner: `hello|ladder|now|order|position|board` (+ `xhedge`, `capacita`, `flusso`...). Protocollo: push `{t, d}`, richiesta `{id, m, p}`, risposta `{id, ok, d, e}`; timeout richieste 10 s; i comandi NON si ritentano mai da soli (esito ignoto: «NON reinviare»).
- **Board**: pallino verde/grigio per tab sport + messaggi di canale off (1.2-1.3).
- **Control Room testata** (la vista principale dello stato): «Runner» (calcio) e «Runner tennis» con fase del runner (`mai avviato`, fasi `FASE_RUNNER`: streaming/idle/altro; colori emerald/oro/arancio; per il tennis «canale spento» se il canale e' off, per il calcio «ignoto» se non letto) + sottoetichetta «canale|db {eta}» e un tetto («live+paper»-tipo) con tooltip; riga «Quote dello scanner» con sorgente e freschezza, riepilogo «Dati: tempo reale» / «dal database per: ...», e, nel `<details>` «dettaglio», le fonti per scanner, stato scanner e righe di Omega/Safe/Mike/Tennis (`canale` o `db` + eta'); chip dei bot (stato servizio, modo, aggiornato, fonte stato); fascia soldi veri (esposizione del conto, rischio live dei bot, scarto); freni (stop perdita del conto e per bot, link matita -> /segui-live); banner di modalita'.
- Altri punti: `FlussoStreamBanner` (stream di mercato interrotto), `FlussoBadge` (prezzi vivi), `ServiceHealthChip`, `runnerHealth.ts` (heartbeat runner), chip in top bar di `LiveTradingPanel`; SeguiLive e MarketWatch/LivePnl usano le porte 47331/47332 per ladder e posizioni.

### 4.2 Modalita' ordini LIVE/PAPER in UI (dove si vede e dove si cambia)
Non esiste un indicatore globale unico fuori dalla Control Room:
- **Control Room**: `ModeBanner` in cima («LIVE — Ordini REALI su Betfair per: <bot> . Tutto il resto opera in prova.» in rosso con `role=alert`; oppure «PAPER — Nessun bot sta usando soldi veri: tutte le operazioni sono simulate sui prezzi live.» in verde; se la modalita' di un bot non e' letta: «... modalita' NON LETTA per: ...» in ambra); la testata diventa arancione con bordo se almeno un bot e' LIVE; ogni chip bot riporta «LIVE» (rosso) / «PAPER» (grigio) / «ultimo modo ...» / «modalità ignota»; tre scomposizioni soldi veri vs «prova» (corsie LIVE/PROVA).
- **Omega, Safe, Mike**: `ModeBanner` + `ModeToggle` nel BotHeader (cambio PAPER/LIVE con `LiveConfirmDialog`) + `ModeBadge` nelle schede; i bot fermi in LIVE restano rossi.
- **Segui Live / pannelli ladder**: modalita' ordini del runner (`set_live_order_mode`, `get_live_settings`), kill switch (`set_live_kill_switch`), `LiveTradingPanel`/`LadderView` con avvisi.
- Desktop: `TENNIS_LIVE_ORDER_MODE` default PAPER nei processi lanciati da `main.js`.
- Board, SelectSport, Dashboard, TennisNav, Landing: NESSUN indicatore di modalita'.

---------------------------------------------------------------------
## 5. `lib/*` E `hooks/*` (una riga ciascuno) + RPC e tabelle

### 5.1 `hooks/`
Solo `hooks/useAuth.ts`: `{user, session, loading}` dalla sessione Supabase (listener auth + getSession). Gli altri hook stanno in `lib/` (`useOrdiniCanale`, `usePosizioniCanale`, `useScanLiveFeed`) e `components/controlroom/` (`useControlRoom`, `useCashOutPartita`, `useChiusuraAlMs`, `usePrezzoAlMs`, `useSeguiOrdini`, `useTennisVivo`), hook `useLocalStatus` in `lib/localTransport.ts`.

### 5.2 `lib/` - file non di test (le fonti dati sono Supabase [RPC/tabelle/Realtime] o canali locali; gli altri sono matematica pura)
**Trasporto e canali locali**
- `localChannel.ts` - client WebSocket ai canali locali (porte 47331-47338), topic, richieste, token di sessione, riconnessione; `svegliaBot()` instrada per bot.
- `localTransport.ts` - adatta il canale locale alle interfacce ladder/ordini con ripiego sul database; hook `useLocalStatus`.
- `canaleRunner.ts` / `usePosizioniCanale.ts` - topic `now` e `position` dei runner (calcio 47331, tennis 47332) sopra il poll DB; hook per le posizioni.
- `ordiniCanale.ts` / `useOrdiniCanale.ts` - topic `order` dei runner come sovrapposizione del poll ordini; hook.
- `runnerCanale.ts` - stato dei runner dal canale locale con ripiego dichiarato sul database.
- `statoBotCanale.ts` - contenuto del push `*_stato` di Omega/Safe/Mike (47333-47335) in sovrapposizione della riga DB.
- `righeCanale.ts` - mappa per riga di Omega/Safe/Mike dai canali (posizioni e proposte).
- `scalperCanale.ts` - scalper calcio dal canale 47338 (`scalper_stato`/`scalper_sessioni`).
- `capacitaMercati.ts` - capacita' mercati del runner calcio e partite escluse (canale 47331).
- `xhedgeCanale.ts` - analisi cross-market `betfair_live_xhedge` dal canale calcio.
- `flussoPrezzi.ts` / `flussoStreamRunner.ts` - i prezzi di una partita / lo stream di mercato del runner sono vivi? (segnale scanner e topic runner).
- `rilettureMirate.ts` - riletture mirate (righe nuove dei bot subito, non al poll dei 30 s).
- `scanEventBuffer.ts` - riduce una raffica di eventi realtime dello scanner in un solo aggiornamento.
- `useScanLiveFeed.ts` - feed live dello scanner Safe (punteggio/minuto/Correct Score) per un insieme di eventi.

**Data layer Supabase (RPC/tabelle)**
- `live.ts` - Segui Live / Match Replay: RPC `get_live_follows`, `get_live_alerts`/`ack_alert`, `list_replays`, `get_replay*`, tabelle `live_now`, `live_ladder`, `live_signals`, `live_follow`, `live_alerts`.
- `liveOrders.ts` - ordini live calcio: coda comandi, posizioni, giornale, regole di rischio, kill switch, modalita' ordini, impostazioni, tabelle `betfair_live_*`.
- `tennis.ts` - tutto il tennis (fixtures, follow, ordini live, posizioni, servizi bot tennis, arm/disarm); tabelle `tennis_live_*`, `tennis_markets`, `tennis_bot_*`.
- `betfair.ts` - partite Betfair del giorno e quote (`get_betfair_*`), richieste ordine/refresh (`request_betfair_*`).
- `omega.ts` / `omegaMissions.ts` / `omegaProposte.ts` / `omegaMatches.ts` - bot Omega: stato, parametri, gambe, missioni per partita, proposte di uscita, una riga per partita.
- `safeBot.ts` / `safeStrategyScan.ts` / `safeStrategy.ts` / `safeExitStatus.ts` - bot Safe, scanner (`safe_strategy_scan/status`), motore puro delle 4 strategie, stato uscita in italiano.
- `mike.ts` / `mikeEsitoChiusura.ts` - bot Mike (Under 3.5 / Over 4.5): RPC `mike_*`, esito di chiusura di una partita.
- `scalper.ts` / `scalperControlRoom.ts` - scalper calcio: pannello e sua vista in Control Room (`scalper_*`).
- `dailyHistory.ts` / `storicoSport.ts` / `chiuseGiornata.ts` / `posizioniChiuse.ts` / `giornataCorsie.ts` / `provaGiornata.ts` - storico per giornata, posizioni chiuse, corsie LIVE/PROVA, «oggi» vs arretrati.
- `controlRoom.ts` / `controlRoomCatena.ts` / `controlRoomProposte.ts` / `proposteUscite.ts` - matematica e proposte della Control Room (catena dei tempi, uscite in attesa del si').
- `analytics.ts` / `reportistiche.ts` - pagina Analytics (pagella motori, strategie salvate, backtest, report Direzioni).
- `personalReport.ts` / `manualeSitoBetfair.ts` / `watchlist.ts` - Report Personale (trade reali), scommesse fuori bot, Watchlist.
- `direzione.ts` / `fixtureModels.ts` / `marketFrequency.ts` / `marketDelays.ts` / `signalContext.ts` / `tacticalEngine.ts` / `etaDato.ts` / `rese.ts` - motori e frequenze della Dashboard calcio (`fixture_predictions`, RPC `get_direction*`, `get_market_*`).

**Matematica / formattazione pura (nessun I/O)**
- `apertoAdesso`, `cashOutPartita`, `certezzaChiusura`, `chiusuraAlMs`, `chiusuraUtente`, `comboPrezzoVivo`, `composizioneConto`, `composizioneObiettivo`, `esitoAbbinamento`, `eventGroups`, `eventPnl`, `fairOverlay`, `fontePnl`, `fonteSoldi`, `interruttori`, `journalStats`, `kellySuggest`, `matching`, `obiettivoEditor`, `opportunitaOrdine`, `orderFlow`, `preGoal`, `riskMath`, `saldoBetfair`, `schedaAlMs`, `statoOrdine`, `tradeStatus`, `valutaProposta`, `vetoCampionati`, `runnerHealth`, `erroreRpc`, `depthFlow`, `matchClock` (countdown/minuto/score), `format`, `toasts`, `utils`.
- Ladder: `ladderMath`, `ladderChart`, `ladderConfig`, `ladderBacktest`, `priceAxis`, `multiLadder`, `trainingLadder`, `workspace`, `servants`, `replay-pnl`.
- Altro: `auth-config` (owner unico `daniele.ritrovato@gmail.com`, testi early access), `betfairMedia` (URL/finestra popout Betfair), `ritorno` (punto di ritorno in sessionStorage), `market-categories`, `sportsLogos` (loghi api-sports), `normalize`/`normalizePrediction`, `mockData` (fallback sviluppo), cartella `opportunities/` (motore opportunita' tier0 arb / tier1 quasi / tier2 micro, fill, snapshot, tradeable).

### 5.3 RPC Supabase chiamate (`.rpc('...')`), per file (pagina d'uso = pagine che importano quel file; per i file in `lib/` usati ovunque la lista e' piu' ampia di cio' che effettivamente chiamano: attribuzione dalle importazioni, non da tracciamento runtime)
Totale 147 nomi distinti (inclusi quelli usati solo da test o certificazione). Per famiglia e file sorgente:
- **`lib/live.ts`** (Segui Live, Match Replay, Control Room): `get_live_follows`, `get_live_alerts`, `ack_alert`, `list_replays`, `get_replay`, `get_replay_meta`, `get_replay_frames`.
- **`lib/liveOrders.ts`** (SeguiLive, LadderView/pannelli, MarketWatch, LivePnl, TradeJournal, MultiLadder, TennisTerminal, ControlRoom): `request_betfair_live_order`, `get_betfair_live_order`, `get_live_orders`, `get_live_orders_account_open`, `get_live_positions`, `get_live_positions_all`, `get_live_positions_event`, `get_live_settled`, `get_live_journal`, `set_live_journal_note`, `get_live_audit`, `get_live_xhedge`, `get_live_risk_rules`, `request_live_risk_rule`, `cancel_live_risk_rule`, `get_live_settings`, `set_live_settings`, `set_live_order_mode`, `set_live_kill_switch`.
- **`lib/tennis.ts`** (TennisDashboard, TennisTerminal, Board [solo `tennis_follow_event`], ControlRoom): `get_tennis_fixtures`, `get_tennis_full_odds`, `get_tennis_follows`, `tennis_follow_event`, `tennis_set_follow_record`, `request_tennis_refresh`, `get_tennis_refresh_request`, `request_tennis_live_order`, `get_tennis_live_order`, `get_tennis_live_orders`, `get_tennis_live_positions`, `get_tennis_live_positions_all`, `get_tennis_bots_state`, `get_tennis_bot_services`, `get_tennis_bot_daily`, `get_tennis_bot_orders_today`, `tennis_bot_arm`, `tennis_bot_disarm`, `tennis_bot_service_activate`, `tennis_bot_service_stop`, `tennis_bot_service_update_params`, `tennis_bot_service_set_uscite`.
- **`lib/betfair.ts`** (Dashboard, Watchlist, ReportPersonale): `get_betfair_fixtures`, `get_betfair_odds`, `get_betfair_full_odds`, `get_betfair_direction_odds`, `request_betfair_order`, `get_betfair_order_request`, `get_betfair_orders`, `request_betfair_refresh`, `get_betfair_refresh_request`.
- **`lib/omega.ts`** (Omega, ControlRoom, Storico): `get_omega_state`, `get_omega_events`, `get_omega_trades`, `get_omega_market`, `get_omega_manual_requests`, `omega_activate`, `omega_stop`, `omega_update_params`, `omega_request`, `omega_evento_riprendi`, `omega_eventi_chiusi_dall_utente`. **`lib/omegaMissions.ts`** (Omega tab Missione, SeguiLive, ControlRoom): `get_omega_missions`, `omega_mission_follow`, `omega_mission_activate`, `omega_mission_stop`, `set_follow_record`. **`lib/omegaProposte.ts`** (ControlRoom): `get_omega_proposte`, `omega_request_approve`, `omega_request_ignore`.
- **`lib/safeBot.ts`** (SafeStrategy, ControlRoom, Storico): `get_safe_state`, `get_safe_trades`, `get_safe_activity`, `get_safe_aggregates`, `safe_activate`, `safe_stop`, `safe_update_params`, `safe_request`, `safe_request_approve`; **`lib/controlRoomProposte.ts`**: `safe_request_approve`, `safe_request_ignore`.
- **`lib/mike.ts`** (Mike, ControlRoom): `get_mike_state`, `get_mike_trades`, `mike_activate`, `mike_stop`, `mike_update_params`, `mike_request`.
- **`lib/scalper.ts`** (SeguiLive, ControlRoom): `get_scalper_state`, `scalper_activate`, `scalper_stop`. **`lib/scalperControlRoom.ts`** (ControlRoom): `get_scalper_control_room`, `scalper_auto_activate`, `scalper_auto_stop`, `scalper_auto_update`, `scalper_stop_sessione`, `scalper_uscite_automatiche`. **`lib/proposteUscite.ts`** (ControlRoom): `scalper_approva_uscita`, `tennis_bot_approva_uscita`.
- **`lib/dailyHistory.ts`** (Storico, schede bot, ControlRoom): `get_omega_daily`, `get_omega_day_trades`, `get_safe_daily`, `get_safe_day_trades`, `get_mike_daily`, `get_mike_day_trades`, `get_storico_stake`.
- **`lib/analytics.ts`** (Analytics): `get_analytics`, `get_analytics_filters`, `get_analytics_rows`, `get_decisions`, `get_decisions_filters`, `list_strategies`, `save_strategy`, `delete_strategy`, `run_strategy`, `run_strategy_rows`, `backtest_strategy`, `request_backtest`, `list_backtest_runs`, `list_backtest_results`. **`lib/reportistiche.ts`** (Analytics): `get_direction_report`, `get_direction_report_fixture`, `get_direction_report_matches`.
- **`lib/personalReport.ts`** (ReportPersonale, Watchlist): `get_personal_report`, `get_personal_trades`, `get_cash_movements`, `add_personal_trade`, `add_trade_leg`, `settle_personal_trade`, `set_trade_time_operative`, `reset_personal_report`. **`lib/watchlist.ts`** (Dashboard, Watchlist): `get_watchlist`, `add_to_watchlist`, `delete_from_watchlist`, `set_watchlist_decision`, `set_watchlist_follow_live`.
- **`lib/direzione.ts`** (Dashboard): `get_direction`, `get_direction_eta`. **`lib/marketFrequency.ts`**: `get_market_frequency`, `get_league_seasons`. **`lib/marketDelays.ts`**: `get_market_delays`. **`lib/fixtureModels.ts`**: `get_poisson_calibration_eta`.
- **`certification/realClient.ts`** (solo certificazione, nessuna pagina): `betfair_live_is_owner`.
**Board**: chiama direttamente una sola RPC, `tennis_follow_event`, e solo dal bottone «Segui live» del tennis.

### 5.4 Tabelle `.from('...')` (letture/scritture/Realtime) e pagine
- `fixture_predictions` - Dashboard (FixtureSelector, MatchesList, modelli, tactical engine).
- `leads` - LandingPage/AuthSection (insert lead).
- `live_now`, `live_ladder`, `live_signals`, `live_follow`, `live_alerts` - Segui Live, Match Replay, MarketWatch, MultiLadder, ControlRoom (`live_follow` anche Omega/Safe/Mike/Storico).
- `betfair_live_account`, `betfair_live_heartbeat`, `betfair_live_risk_state`, `betfair_live_orders`, `betfair_live_positions` - Segui Live e pannelli live, LivePnl, TradeJournal, ControlRoom (heartbeat anche Omega/Safe/Mike/Storico).
- `tennis_live_now`, `tennis_live_ladder`, `tennis_live_orders`, `tennis_live_positions`, `tennis_markets` - TennisDashboard/TennisTerminal/ControlRoom.
- `tennis_bot_control`, `tennis_bot_activity` - ControlRoom, SafeStrategy tab tennis.
- `omega_control`, `omega_trades`, `omega_activity`, `omega_missions`, `omega_manual_requests` - Omega, ControlRoom.
- `safe_strategy_control`, `safe_strategy_trades`, `safe_strategy_activity`, `safe_strategy_opportunities`, `safe_strategy_requests`, `safe_strategy_scan`, `safe_strategy_status` - SafeStrategy, ControlRoom, Storico.
- `mike_requests` - Mike, ControlRoom.
- `live_backtest_requests` - Analytics.
Realtime: sono sottoscritti `postgres_changes` sulle tabelle sopra (grep `table:` in `lib/live.ts`, `liveOrders.ts`, `tennis.ts`, `omega*.ts`, `safeBot.ts`, `safeStrategyScan.ts`, `controlRoomProposte.ts`).
Integrazione client: `integrations/supabase/client.ts` (variabili `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`). Asset pubblici: `public/alpha_score_logo_full.png`, `public/futuristic-football-game-ball.jpg`, `public/vite.svg`.

---------------------------------------------------------------------
## 6. COSA NON HO POTUTO VERIFICARE
- Rendering reale (non ho avviato app/browser): colori e spaziature sono dedotti dalle classi Tailwind; i valori dei token (`primary`, `secondary`, `brand-orange`, `glass-card`, `neon-glow-*`) stanno in `index.css`/`tailwind.config.js` non analizzati qui.
- Contenuto reale dei push `board` a runtime (numero di eventi, se `status` e' sempre valorizzato, orario in fuso): ho letto solo il tipo TypeScript e il produttore `Betfair/stream/board_worker.py`; la cadenza di 10 s e' il default letto dal runner, non misurata.
- Attribuzione pagina->RPC/tabella in 5.3/5.4: calcolata dal grafo degli import, quindi per i file `lib/` molto condivisi la lista delle pagine e' un sovrainsieme; la riga Board (solo `tennis_follow_event`) e' invece verificata dal codice.
- Il dettaglio interno di Dashboard (`MatchesList`, `AnalyticsPanels`), SeguiLive, SafeStrategy, Omega, Mike, ControlRoom e Analytics NON e' inventariato qui (altre parti dell'inventario): sono state lette solo le navbar e i punti di navigazione. In `ModeToggle`/`LiveConfirmDialog`/`LiveTradingPanel` ho confermato l'esistenza ma non letto i testi.
- Etichette `FASE_RUNNER`, `tettoRunner`, parole del chip bot (`paroleImpianto`): letti solo i casi `modoChip`/`statoChip`; i testi completi di `FASE_RUNNER` non sono stati riportati.
- Se esista un build `dist` aggiornato o l'exe in `desktop/release/`: non verificato (nessun avvio).
- `LandingPage` usa `defaultTab="register"` per default perche' non passa la prop: dedotto dal codice (la prop e' opzionale con default «register»).
