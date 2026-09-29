# E — Schermate e pulsanti di Mike (area utente: quello che si vede e si preme)

## Intervallo letto

**Frontend** (`frontend/src/`), riga per riga dove non altrimenti indicato:
- `pages/Mike.tsx` (intero, 764 righe)
- `components/mike/useMike.ts` (intero, 363 righe)
- `lib/mike.ts` (intero, 2183 righe)
- `components/mike/MikeMatchCard.tsx` (intero, 1161 righe)
- `components/mike/MikeCashOutButton.tsx` (intero, 246 righe)
- `components/mike/MikeParamsSheet.tsx` (intero, 81 righe)
- `components/mike/MikeEventPnlTable.tsx` (intero, 126 righe)
- `components/mike/useMikeClock.ts` (intero, 46 righe)
- `components/trading/ParamsSheetBase.tsx` (intero, 314 righe)
- `components/controlroom/InterruttoreUscite.tsx` (intero)
- `components/controlroom/PropostaUscitaMike.tsx` (intero)
- `components/controlroom/RigaOrdiniReali.tsx` (intero)
- `components/controlroom/RigaFreno.tsx` (intero)
- `components/controlroom/PannelloBot.tsx` (intero, 918 righe)
- `components/controlroom/SchedaMike.tsx` (intero)
- `components/controlroom/BottoneChiudiRiga.tsx` (intero)
- `components/controlroom/chiudiRiga.ts` (intero)
- `components/controlroom/dettaglioRiga.ts` (intero)
- `components/controlroom/PosizioniChiuse.tsx` (intero, 783 righe)
- `components/controlroom/trovaEsitoUscita.ts` (intero)
- `lib/interruttori.ts` (intero, 1332 righe)
- `lib/localChannel.ts` (intero, 351 righe)
- `lib/format.ts` (intero, 193 righe)
- `lib/toasts.ts` (intero)
- `components/trading/LiveConfirmDialog.tsx`, `ModeBanner.tsx`, `ModeToggle.tsx`, `BotHeader.tsx`, `StatTile.tsx`, `DayBar.tsx`, `ServiceHealthChip.tsx`, `PageShell.tsx`, `EquityCard.tsx`, `EmptyState.tsx`, `SectionFilter.tsx`, `ActivityFeed.tsx`, `TradingHistory.tsx`, `StoricoLink.tsx` (interi)
- `App.tsx` (rotta `/mike`), `pages/SelectSport.tsx` (voce Mike)
- `pages/ControlRoom.tsx` — sola lettura mirata sui punti che citano `mike` (righe 1-130, 330-730, 980-1020, 1195-1420) più titoli/import
- `lib/tradeStatus.ts`, `lib/dailyHistory.ts` — lettura mirata (glossario `T`, `EXIT_REASON_TEXT`, `fetchMikeDaily`/`fetchMikeDayTrades`)
- `useControlRoom.ts` (3865 righe) — lettura mirata su tutte le occorrenze di `mike` (via delega, vedi sotto)
- `lib/controlRoom.ts`, `statoBotCanale.ts`, `posizioniChiuse.ts`, `chiuseGiornata.ts`, `certezzaChiusura.ts`, `esitoAbbinamento.ts`, `righeCanale.ts`, `composizioneObiettivo.ts`, `chiusuraUtente.ts`, `statoOrdine.ts`, `ritorno.ts`, `eventGroups.ts`, `useChiusuraAlMs.ts` — letti per intero da un delegato (vedi nota sotto), riportati qui per la parte che tocca Mike

**Nota sul metodo**: la parte segnata "letti da un delegato" è stata prodotta da due agenti di lettura lanciati da me nella stessa sessione, con lo stesso mandato di questo file (sola lettura, riga per riga, citare file:riga), e i loro referti sono stati incrociati con le mie letture dirette dove i perimetri si sovrapponevano (`MikeMatchCard.tsx`, `interruttori.ts`, `PropostaUscitaMike.tsx`, `InterruttoreUscite.tsx`, `localChannel.ts`, `PannelloBot.tsx`, `RigaOrdiniReali.tsx`, `RigaFreno.tsx`, `chiudiRiga.ts`, `BottoneChiudiRiga.tsx`, `SchedaMike.tsx`, `PosizioniChiuse.tsx`): nessuna divergenza trovata fra le due letture.

**Database** (`migrations/`), interi salvo indicazione:
- `mike_bot.sql`, `mike_bot_v2.sql`, `mike_history.sql`, `mike_history_v2.sql`, `mike_aggregati_per_modalita_2026-09-13.sql`, `mike_storico_per_modalita_2026-09-14.sql`, `mike_vincoli_flusso_fischio_2026-09-14.sql`, `uscite_manuali_default_2026-09-25.sql`, `uscite_automatiche_mike_2026-09-25.sql`
- letti a grep mirato su "mike" (righe di contesto lette): `betfair_live_orders_source_bot_2026-09-26.sql`, `posizioni_chiuse_giornata_2026-09-24.sql`, `pnl_betfair_reale_2026-09-24.sql`, `trades_consapevolezza_ordine_2026-09-16.sql`, `storico_esito_a_zero_2026-09-26.sql`, `sanatorie_2026-09-28.sql`, `hazard_atlas_rpc_scrittura_2026-09-28.sql` (non tocca Mike), `sicurezza_db_2026-09-24_BLOCCO_2_rls_e_policy.sql`, `sicurezza_db_2026-09-24_BLOCCO_3_revoke_anon.sql`
- verificato che `uscite_approva_bot_flusso_2026-09-28.sql` **non riguarda Mike** (solo tennis e scalper calcio: Mike ha la sua propria RPC `approva_uscita` dentro `uscite_automatiche_mike_2026-09-25.sql`)
- **non ancora ricevuto** un referto di lettura dedicato e sistematico riga-per-riga di `mike_storico_per_modalita_fix_alias_2026-09-14.sql` e delle policy RLS complete dei blocchi sicurezza (solo grep di conferma): dichiarato in "Non ho letto"
- `Betfair/mike/config.py` (intero, 481 righe) — solo per il confronto UI↔whitelist (l'engine vero, `engine.py`/`service.py`, è fuori dalla mia area)

## Numero di schede: 52

## Elenco componenti/funzioni → scheda che li copre

| Componente / funzione | Scheda |
|---|---|
| `SelectSport.tsx` (voce Mike) | 1 |
| `App.tsx` (rotta `/mike`) | 1 |
| `PageShell` | 2 |
| `BotHeader`, `botStatusWithBeat` | 2 |
| `ServiceHealthChip` | 2 |
| canale locale (badge) | 2 |
| `ModeToggle`, `LiveConfirmDialog` | 3 |
| `ModeBanner` | 4 |
| avviso "partita in altra modalità", avviso `MIKE_LIVE_ENABLED` | 4 |
| `DayBar` | 5 |
| `StatTile` × 7, `KpiRow` | 6 |
| `Tabs`/`TabsList` | 7 |
| `SectionFilter`, sezioni Partite | 8 |
| `MikeMatchCard` — header | 9 |
| `MikeMatchCard` — allarmi | 10 |
| `MikeMatchCard` — quadro modello + istogramma | 11 |
| `MikeMatchCard` — tre linee di quota | 12 |
| `MikeMatchCard` — riga meta | 13 |
| `MikeMatchCard` — tabella posizioni | 14 |
| `MikeMatchCard` — ordini sul book | 15 |
| `MikeMatchCard` — P&L per gol totali / liability / bloccato | 16 |
| `MikeMatchCard` — riquadro cash out (valore/barra/righe) | 17 |
| `MikeCashOutButton` | 18 |
| `MikeFlattenButton` | 19 |
| bottone "Annulla ordini" | 20 |
| bottone "Salta" | 21 |
| bottone "Riprendi" | 22 |
| `PropostaUscitaMike` (pagina Mike) | 23 |
| `MikeEventPnlTable` (Operazioni) + `EquityCard` | 24 |
| `MikeEventPnlTable` (Risultati Pre-Match/Live) | 25 |
| `ActivityFeed` (Attività) | 26 |
| `TradingHistory` (Storico) | 27 |
| `MikeParamsSheet`, `ParamsSheetBase` | 28 |
| tabella parametri completa | 28-bis (non numerata) |
| `PannelloBot` — riga Mike | 29 |
| `RigaOrdiniReali` | 30 |
| `RigaFreno` | 31 |
| `MikeParamsSheet` in Control Room | 32 |
| `SchedaMike` (Control Room) | 33 |
| `PropostaUscitaMike` (Control Room) | 34 |
| `BottoneChiudiRiga`/`chiudiRiga.ts` per Mike | 35 |
| `PosizioniChiuse` — filtro Mike | 36 |
| avviso "Mike: uscita appoggiata SPENTA in live" | 37 |
| indicatore "fonte righe" Mike | 38 |
| `SaldoBetfairCard` (canale mike) | 39 |
| tabella `mike_control` | 40 |
| tabella `mike_events` | 41 |
| tabella `mike_trades` | 42 |
| tabella `mike_activity` | 43 |
| tabella `mike_requests` | 44 |
| `mike_activate` | 45 |
| `mike_stop` | 46 |
| `mike_update_params` | 47 |
| `get_mike_state` | 48 |
| `get_mike_trades` | 49 |
| `mike_request` (incl. `approva_uscita`) | 50 |
| `mike_aggregates_sql` / `get_mike_aggregates` | 51 |
| `get_mike_daily` / `get_mike_day_trades` / `trading_daily_history` / `trading_day_trades` | 52 |

---

## GRUPPO A — La pagina di Mike (`/mike`)

### 1. Come si arriva a Mike
- **Cosa fa**: dal menu "Scegli sport" (`pages/SelectSport.tsx`) c'è una scheda con l'emoji 🎯, titolo "Mike", sottotitolo "Under 3.5 / Over 4.5 · green-up e cash-out · paper-first", colore d'accento teal. Premendola si va alla pagina `/mike`.
- **Quando scatta**: al clic sulla scheda "Mike" nella pagina di scelta sport.
- **Cosa succede dopo**: si apre la pagina `/mike`, protetta da login (`ProtectedRoute`): senza sessione utente non si entra.
- **Numeri**: nessuno.
- **Esempio**: l'utente apre l'app, va su "Scegli sport", clicca "🎯 Mike" e arriva alla pagina del bot.
- **Cosa vede l'utente**: la scheda con emoji, titolo, sottotitolo.
- **Dove**: `frontend/src/pages/SelectSport.tsx:72-79`, `frontend/src/App.tsx:26,190-195`.
- **Paper o live**: nessuna differenza; la modalità si sceglie dentro la pagina di Mike.

### 2. L'intestazione della pagina (header)
- **Cosa fa**: riga fissa in cima allo schermo (resta visibile mentre si scorre) che mostra: link "AI TERMINAL" per tornare alla scelta sport, il simbolo 🎯 e il nome "MIKE" in teal, un'etichetta di stato del bot, un indicatore di salute del servizio, un'etichetta "canale locale" se l'app desktop riceve i dati push, il pulsante "Storico calcio", l'interruttore PAPER/LIVE, il pulsante "Parametri" e il pulsante "Avvia"/"Ferma".
- **Quando scatta**: sempre visibile, si aggiorna da sola.
- **Etichetta di stato del bot**: parole possibili "BOT INATTIVO" (mai avviato), "BOT IN CORSA", "BOT IN ARRESTO", "BOT FERMO", "BOT ERRORE". Se il bot risulta "IN CORSA" ma non manda il battito da più di 45 secondi, l'etichetta diventa rossa **"BOT IN CORSA · SENZA BATTITO"** con la spiegazione "il servizio non batte da {tempo}: riavvia l'app desktop" (o, se non ha mai battuto, "il servizio non ha mai battuto da quando è stato avviato"). Questo stesso avviso compare **due volte** nella stessa riga (anche nel chip di salute accanto): è una ridondanza nota e voluta lasciata così per non rompere un test di un'altra pagina (vedi «Cose strane»).
- **Chip di salute del servizio**: mostra separatamente lo stato del FEED (lo scanner condiviso) e il BATTITO del servizio Mike. Feed: "feed vivo (N s)" (verde) se aggiornato entro 45 secondi, altrimenti "feed FERMO da {tempo}" (rosso) o "feed: nessun dato". Se vivo, accanto compaiono i conteggi partite in-play ⚽ calcio / 🎾 tennis dal feed unico. Battito: "servizio Mike vivo (N s)" (verde) o "servizio Mike: nessun battito da {tempo} — riavvia l'app desktop" (rosso). Badge "⚡ STREAM {n}" (verde) se le quote arrivano in push, o "REST" (ambra) se arrivano dal poll di ripiego. Badge "DRY" (ambra) se il servizio sta solo osservando senza piazzare ordini. Se il feed è fermo, appare la riga "— il feed dello scanner è fermo da {tempo}: riavvia l'app desktop".
- **Badge "canale locale"**: compare SOLO se l'app desktop è connessa al socket `ws://127.0.0.1:47333` (stessa porta usata dalla card "Saldo Betfair" della Control Room, scheda 39): scritta verde "canale locale" col tooltip che spiega che quote, P&L e stato arrivano pushati dal bot sul PC senza passare dal database. Se il socket cade, il badge sparisce e la pagina torna silenziosamente a leggere dal database (niente scompare, solo un po' più vecchio).
- **Cosa succede dopo**: nessuna azione propria oltre ai pulsanti descritti nelle schede 3 e 29.
- **Numeri**: soglia battito servizio morto = **45 secondi** (`SERVICE_STALE_S`); soglia feed fermo = **45.000 ms** (`SCANNER_STALE_MS`, calcolata a parte nella pagina Mike, non dal chip).
- **Esempio**: se il servizio Mike è stato avviato ma il processo Python è bloccato da 2 minuti, il badge di stato diventa rosso "BOT IN CORSA · SENZA BATTITO (2 min)" e il chip ripete "servizio Mike: nessun battito da 2 min — riavvia l'app desktop".
- **Cosa vede l'utente**: la riga descritta sopra, sempre in cima.
- **Dove**: `frontend/src/components/trading/BotHeader.tsx:43-83,85-193`; `components/trading/ServiceHealthChip.tsx` (intero); `pages/Mike.tsx:377-424` (props passate).
- **Paper o live**: nessuna differenza nell'header stesso (la modalità si vede nel toggle, scheda 3).

### 3. L'interruttore PAPER/LIVE e la conferma dei soldi veri
- **Cosa fa**: due pulsanti affiancati "PAPER" (verde quando attivo) e "LIVE" (rosso quando attivo). Passare a LIVE apre sempre una finestra di conferma; passare a PAPER è immediato, senza nessuna domanda.
- **Quando scatta**: al clic su "LIVE" (`ModeToggle`) si apre il dialogo "Passare a LIVE (soldi veri)?" con: un testo introduttivo ("Da questo momento gli ordini del bot Mike usano denaro reale."), un avviso specifico in arancione ("La struttura Under 3.5 / Over 4.5 perde con esattamente 4 gol: il live va attivato solo dopo il GO della certificazione paper (Costituzione §0)."), il pulsante "Annulla" e il pulsante "Sì, passa a LIVE" (rosso).
- **Cosa succede dopo**: confermando, la pagina chiama `bot.setMode('live')` (che scrive `mike_update_params` con `p_mode='live'`, mantenendo i parametri correnti), chiude il dialogo e mostra un toast rosso "🔴 MODALITÀ LIVE — soldi veri". Passando a PAPER: `bot.setMode('paper')` diretto, nessun dialogo, nessun toast di conferma.
- **Nota importante**: il dialogo di Mike **non** usa il meccanismo di "conferma decaduta se le condizioni cambiano mentre il dialogo è aperto" (esiste nel componente condiviso ma Mike non gli passa la chiave `armKey`): se il trader lascia il dialogo aperto e nel frattempo cambia qualcosa, la conferma resta comunque valida.
- **Numeri**: nessun numero (nessun timeout di decadenza per questo dialogo).
- **Esempio**: l'utente preme LIVE, legge l'avviso sui 4 gol, preme "Sì, passa a LIVE": da quel momento il bot lavora con soldi veri finché non si riporta a PAPER.
- **Cosa vede l'utente**: il toggle in alto e il dialogo di conferma.
- **Dove**: `components/trading/ModeToggle.tsx` (intero); `components/trading/LiveConfirmDialog.tsx` (intero); `pages/Mike.tsx:275-283,422,753-760`.
- **Paper o live**: è esattamente il comando che cambia la modalità del bot intero (non della singola partita: una partita già armata in un'altra modalità resta in quella, vedi scheda 4).

### 4. Il banner di modalità e gli avvisi di modalità mista
- **Cosa fa**: subito sotto l'header, un riquadro colorato dice sempre in che modalità sta operando la pagina. Rosso con "MODALITÀ LIVE — il bot piazza ordini con soldi veri." oppure verde con "MODALITÀ PAPER — simulazione fedele: fill solo al prezzo ancora disponibile, betDelay in-play, protezioni identiche al live." Se il bot è in sola osservazione (DRY) appare "DRY: nessun ordine (osservazione)". Se il servizio ha un errore lo scrive qui (⚠ + messaggio). Se le tabelle di Mike non esistono ancora nel database, scrive "tabelle Mike assenti: applica migrations/mike_bot.sql".
- Sotto il banner, due allarmi possibili SOLO su Mike:
  1. **"⚠️ N partita/e sta/stanno operando in PAPER/LIVE"** (rosso): compare quando ci sono partite ancora vive armate nell'ALTRA modalità rispetto al toggle attuale — perché la modalità di una partita si "congela" al momento in cui viene armata e il toggle in alto non la cambia. Se il bot ora è in paper ma ci sono partite armate in live, l'avviso dice esplicitamente "con soldi veri, anche se il bot adesso è in paper" e invita a chiuderle a mano dalle loro schede.
  2. **"Modalità LIVE, ma il processo NON è abilitato a piazzare ordini reali."** (ambra): compare quando la pagina è in LIVE ma il servizio dichiara che l'interruttore di sicurezza `MIKE_LIVE_ENABLED` (variabile d'ambiente) è spento: il bot calcola tutto ma blocca ogni ordine prima che parta.
- **Quando scatta**: sempre visibile; i due avvisi extra solo alle condizioni dette.
- **Cosa succede dopo**: nessuna azione, sono avvisi.
- **Numeri**: nessuno editabile da qui; `MIKE_LIVE_ENABLED` è una variabile d'ambiente (`.env`), non un parametro della UI.
- **Esempio**: il trader passa la pagina a PAPER, ma tre partite avviate mentre era in LIVE continuano a operare con soldi veri: compare "⚠️ 3 partite stanno operando in LIVE... Per fermarle davvero serve chiuderle a mano dalle loro schede."
- **Cosa vede l'utente**: i riquadri descritti, sopra la barra della giornata.
- **Dove**: `components/trading/ModeBanner.tsx` (intero); `pages/Mike.tsx:428-475` (testo esatto, calcolo `partiteAltraModalita` da `stats.eventi_altra_modalita`, `liveAbilitato` da `stats.live_abilitato`).
- **Paper o live**: è precisamente il meccanismo che avvisa quando le due modalità convivono.

### 5. La barra della giornata operativa (DayBar)
- **Cosa fa**: una card sotto il banner con la data della giornata operativa (fuso Europe/Rome), il P&L realizzato oggi (numero grande, verde/rosso), i contatori "partite", "operazioni", "V"/"P" (vinte/perse), "vive" se ci sono partite in gioco, la "Liability aperta" e il "P&L bloccato", e il "totale storico" da sempre.
- Mike **non ha un obiettivo di giornata**: a differenza di Omega, questa card non mostra barra di avanzamento né "resta"/"CENTRATO".
- Nota di significato: "operazioni" per Mike conta i CICLI (apertura + le sue chiusure), non le righe di database, ed è lo stesso numero che si vede nella scheda Operazioni e nello Storico.
- **Quando scatta**: si aggiorna a ogni ricarica dei dati.
- **Cosa succede dopo**: nessuna azione, solo lettura.
- **Numeri**: nessun parametro editabile da qui; i numeri vengono dagli `aggregates` della RPC (`get_mike_state`), con ripiego sul conto lato client se manca la migrazione più recente.
- **Esempio**: "giornata operativa giovedì 10 settembre 2026 (Europe/Rome) · +12,50 € · partite 4 · operazioni 9 · 6V 2P · Liability aperta 3,40 € · P&L bloccato +0,80 € · totale storico +140,20 €".
- **Cosa vede l'utente**: la card descritta, sempre visibile sotto il banner.
- **Dove**: `components/trading/DayBar.tsx` (intero); `pages/Mike.tsx:482-496`.
- **Paper o live**: mostra SOLO la modalità con cui il bot sta girando ora: le righe dell'altra modalità sono escluse e, se ce ne sono, un avviso a parte lo dichiara (scheda 6).

### 6. Le 7 caselle di riepilogo (KPI)
- **Cosa fa**: una riga di 7 riquadri, ciascuno con un'etichetta, un numero grande e una riga di spiegazione sotto:
  1. **Partite seguite ora** (teal): numero totale di partite attive; sotto "{N} prima del fischio · {N} in gioco · {N} con posizione aperta".
  2. **Posizioni aperte**: numero di cicli con capitale ancora esposto; se ce ne sono in verifica su Betfair, sotto in fucsia "{N} in verifica su Betfair", altrimenti "cicli con capitale ancora esposto".
  3. **P&L oggi**: colorato verde/rosso/grigio secondo il segno; se lo stop giornaliero è attivo, sotto in rosa "STOP giornaliero ATTIVO · solo chiusure", altrimenti la data e l'eventuale soglia di stop ("stop a −50,00 €").
  4. **P&L totale**: da sempre, stessa modalità.
  5. **Liability aperta** (tono arancione fisso): sotto, "stimata dalle righe (servizio da riavviare)" in ambra se la fonte non è quella netta del servizio, altrimenti "perdita peggiore sulle posizioni aperte, netta dal servizio"; con eventuale "· di cui N in verifica" e "· dato stantio" se il battito è più vecchio di 60 secondi.
  6. **P&L bloccato**: "—" se nessuna partita ha ancora un risultato bloccato, altrimenti l'importo con segno e sotto "già bloccato su N partita/e · N ancora da decidere" se applicabile.
  7. **Ultimo ciclo**: l'orario dell'ultimo ciclo del servizio (ore:minuti:secondi); se il servizio non batte da oltre 45 secondi, sotto in rosso "servizio senza battito: riavvia l'app desktop", altrimenti "feed aggiornato N s fa" o "feed: nessun dato".
- **Quando scatta**: sempre visibili, aggiornate a ogni ricarica; durante il primo caricamento appaiono come rettangoli grigi animati (skeleton).
- **Cosa succede dopo**: nessuna azione, sono di sola lettura.
- **Numeri**: nessun parametro qui; soglia battito servizio 45 secondi (calcolata localmente nella pagina, non dal chip condiviso); soglia "liability stantia" 60 secondi (calcolata lato database).
- **Esempio**: "Posizioni aperte: 5 · 2 in verifica su Betfair" quando due ordini hanno un esito ancora ignoto su Betfair.
- **Cosa vede l'utente**: la riga di 7 riquadri sotto la barra della giornata.
- **Dove**: `components/trading/StatTile.tsx` (intero); `pages/Mike.tsx:498-565`.
- **Paper o live**: tutti i numeri sono filtrati sulla modalità con cui il bot sta girando.

### 7. Le sei linguette (schede della pagina)
- **Cosa fa**: sotto i KPI, sei linguette con contatore: "⚽ Partite (N)", "📋 Operazioni (N)", "⏱ Risultati Pre-Match (N)", "🔴 Risultati Live (N)", "🧾 Attività", "📅 Storico". Restano appiccicate in cima quando si scorre la pagina (sticky, sotto l'header).
- **Quando scatta**: al clic su una linguetta si mostra il suo contenuto.
- **Cosa succede dopo**: cambia solo la parte visibile della pagina, nessuna richiesta nuova al database (i dati sono già in memoria).
- **Numeri**: nessuno.
- **Esempio**: "📋 Operazioni (12)" indica 12 partite con almeno un'operazione oggi.
- **Cosa vede l'utente**: la barra di linguette.
- **Dove**: `pages/Mike.tsx:567-584`.
- **Paper o live**: ogni linguetta mostra solo la modalità attiva.

### 8. Scheda Partite — le tre sezioni fisse e i filtri
- **Cosa fa**: la prima linguetta elenca le partite seguite da Mike in tre sezioni SEMPRE nello stesso ordine, anche vuote:
  - **⏱ PRE-MATCH (N)** — partite non ancora entrate in gioco, ordinate per calcio d'inizio crescente;
  - **🔴 LIVE (N)** — partite già in gioco (una partita entra qui al fischio e non torna mai più in Pre-match, anche con un buco del feed);
  - **⚠️ DA SISTEMARE (N)** — compare SOLO se ci sono partite in errore o saltate, con il messaggio "partite in errore o saltate: serve una mano".
  - Sopra le sezioni, due pulsanti-filtro "⏱ Pre-match" e "🔴 Live" (con il loro conteggio scritto anche da spenti) permettono di nascondere una sezione: la scelta resta salvata nel browser; non si può nascondere l'ultima sezione visibile.
- Se non c'è nessuna partita seguita, un riquadro dice: "Nessuna partita seguita. Con il bot in corsa, le partite con calcio d'inizio entro {N} ore e le linee 3.5/4.5 nel feed compaiono qui." (N = parametro `entry_hours_before_ko`, scheda 28).
- **Quando scatta**: al clic sui filtri; le sezioni si popolano da sole quando il servizio scrive nuove partite.
- **Cosa succede dopo**: la sezione nascosta sparisce dalla vista (il conteggio resta), la card della partita resta identica.
- **Numeri**: nessuno editabile qui.
- **Esempio**: con 6 partite seguite, 4 non ancora iniziate e 2 in corso: "⏱ PRE-MATCH (4)" e "🔴 LIVE (2)".
- **Cosa vede l'utente**: le tre sezioni con le card delle partite (scheda 9 e seguenti).
- **Dove**: `pages/Mike.tsx:586-651`; `lib/mike.ts::splitMikeEvents,needsAttention,isEventLive,sortEvents` (righe 665-728); `components/trading/SectionFilter.tsx` (intero).
- **Paper o live**: ogni card mostra la modalità della SUA partita (non del toggle della pagina).

## La card di UNA partita (`MikeMatchCard`)

La card ha un'altezza stabile: ogni zona è sempre montata, anche senza dati (scrive "—"), così l'arrivo di una copertura o di un ordine non fa "saltare" le altre zone né le card vicine. Il bordo sinistro cambia colore per fase: teal (pre-match), viola (live), verde (piatta/flat), bianco tenue (regolata), rosso (errore/saltata).

### 9. Intestazione della card (punteggio, fase, freschezza feed)
- **Cosa fa**: mostra il punteggio in grande ("0–1", trattino se assente), le eventuali espulsioni (🟥 casa/trasferta), il nome della partita e la competizione, poi a seconda del momento: in gioco → minuto, gol, "intervallo" ed eventuale risultato del primo tempo; pre-match → orario del calcio d'inizio e un conto alla rovescia ("fra 1h 12m"), oppure "in attesa del fischio" se l'orario è passato ma il feed non dice ancora che si gioca; partita chiusa → orario, gol totali, e la fase in minuscolo. A destra, un'etichetta di FASE (una delle 19, vedi Glossario) e un'etichetta di freschezza del feed di QUESTA partita: "feed N s" verde fino a 5 secondi, ambra fino a 20, "FEED FERMO (N s)" rosso oltre, "FEED: NESSUN DATO" se il servizio non pubblica l'età; su una partita chiusa scrive invece "partita chiusa" (grigio), mai il rosso, per non dare un falso allarme.
- Sotto il titolo, una riga dice in parole semplici che cosa sta facendo il bot ADESSO (es. "posizione abbinata prima del fischio: aspetta il green-up a +N tick"), non solo la sigla della fase.
- **Quando scatta**: si aggiorna da solo quando il servizio riscrive la partita (ogni pochi secondi) e il conto alla rovescia ticca ogni secondo per conto suo, senza far ridisegnare il resto della card.
- **Cosa succede dopo**: nessuna azione, solo lettura.
- **Numeri**: soglie freschezza feed 5 s / 20 s (fisse nel codice, non editabili dalla UI).
- **Esempio**: "0–1 · 34′ · 2 gol" con etichetta "LIVE · SCOPERTO" e badge "feed 3 s" verde.
- **Cosa vede l'utente**: l'intestazione descritta, in cima a ogni card.
- **Dove**: `components/mike/MikeMatchCard.tsx:584-649`; `lib/mike.ts::feedFreshness,etaQuoteS,awaitingKickoff,phaseMeta,MIKE_PHASE_META` (righe 618-810).
- **Paper o live**: badge "SOLDI VERI" separato, vedi scheda 10.

### 10. Gli allarmi della card
- **Cosa fa**: riga sempre presente (anche vuota) con badge d'allarme quando servono:
  - banner rosso "linea {X} assente nel feed: nessuna copertura e nessun cash out possibile" se manca una delle linee;
  - "CHIUSURA IN CORSO" (lampeggiante) se una chiusura manuale è già stata armata dal servizio;
  - "VOID · mercato annullato" oppure "VOID ({linea})" se un mercato è stato annullato (il void è per mercato, non per tutta la partita);
  - "ORDINE IN VERIFICA SU BETFAIR" se c'è un ordine con esito ignoto;
  - "NESSUN RIENTRO" se il rientro sulla partita è stato disabilitato (dopo una chiusura manuale pre-fischio, si riattiva solo con "Riprendi");
  - "SOLDI VERI" se la partita opera in modalità live.
- **Quando scatta**: automaticamente secondo lo stato pubblicato dal servizio.
- **Cosa succede dopo**: nessuna azione diretta; questi badge spengono i bottoni di chiusura con il motivo scritto (schede 18-19).
- **Numeri**: nessuno.
- **Esempio**: una partita con la linea Over 4.5 sparita dal feed mostra il banner rosso e i bottoni Cash out/Flatten si disabilitano con lo stesso motivo.
- **Cosa vede l'utente**: la riga di badge subito sotto l'intestazione.
- **Dove**: `components/mike/MikeMatchCard.tsx:650-684`; `lib/mike.ts::eventFlags,lineLabel,marketLabel`.
- **Paper o live**: il badge "SOLDI VERI" compare solo se `ev.mode === 'live'`.

### 11. Il quadro modello e l'istogramma dei gol
- **Cosa fa**: se la partita ha un modello statistico (gol attesi calcolati), mostra 4 caselle: "P(4 gol) modello" con sotto la fonte dei gol attesi (da partita abbinata / da quote pre-partita / da mercato Over/Under / "MODELLO ASSENTE" in ambra se nessuna); "P(4 gol) mercato" (dalle due quote); in gioco "Hazard gol 3′" (con il dettaglio atlante/modello) o pre-partita "P(Over 4.5) modello"; in gioco "Pressione ×N" (con 🔥 se supera la soglia di "fase calda") o pre-partita "λ casa / trasferta" (gol attesi). Se la lega non ha nessun modello, al posto delle 4 caselle compare UNA riga: "Nessun modello per questa lega: il bot decide con le quote e le soglie fisse." (mai celle vuote con "—" che sembrano rotte).
- Sotto, un istogramma di 9 barre (probabilità di 0-8 gol totali), con la colonna del 4° gol sempre in rosso ("è l'unica casella che perde"); se non c'è nessun dato, una riga sola: "Nessun modello per questa lega: copertura a regola fissa (quote e soglie del mercato)."
- **Quando scatta**: automatico, dai dati del servizio.
- **Cosa succede dopo**: nessuna azione, solo lettura.
- **Numeri**: soglia "fase calda" di pressione = parametro `cashout_smart_pressure_hot`, di serie **1,15** (scheda 28).
- **Esempio**: "P(4 gol) modello 21,3% · MODELLO ASSENTE" quando il bot non ha trovato la partita nel database delle statistiche.
- **Cosa vede l'utente**: la griglia di 4 caselle e le 9 barre.
- **Dove**: `components/mike/MikeMatchCard.tsx:686-733`; `lib/mike.ts::hasModel` (righe 973-980).
- **Paper o live**: nessuna differenza.

### 12. Le tre linee di quota
- **Cosa fa**: tre riquadri sempre presenti — "Under 3.5", "Over 4.5", "Under 4.5 (re-ingresso)" — ciascuno con miglior prezzo BACK e LAY, la size disponibile, una freccetta di variazione rispetto al tick precedente (colore neutro: una quota che sale non è né buona né cattiva in sé), il ritardo scommessa (bet delay) in secondi, e lo stato del mercato tradotto in italiano: "OPEN" non si scrive, "SOSPESO" (ambra), "CHIUSO" (rosso), "NON ATTIVO" (rosso). Su una partita chiusa, l'etichetta cambia in "... ultime quote viste", il riquadro si sbiadisce e la freccetta di variazione sparisce (sono gli ultimi prezzi visti, non quelli di adesso).
- **Quando scatta**: aggiornamento automatico a ogni ciclo del servizio.
- **Cosa succede dopo**: nessuna azione, solo lettura (il tooltip mostra l'id del mercato e della selezione Betfair).
- **Numeri**: nessuno editabile qui.
- **Esempio**: "Under 3.5: 1,52/1,54 · ritardo scommessa 5 s"; "Over 4.5: SOSPESO" in ambra durante una sospensione del mercato.
- **Cosa vede l'utente**: i tre riquadri affiancati.
- **Dove**: `components/mike/MikeMatchCard.tsx:262-305,735-764`; `lib/mike.ts::marketStatusMeta`.
- **Paper o live**: nessuna differenza.

### 13. La riga "meta" (volume, ingresso, al fischio, ciclo)
- **Cosa fa**: una riga con: "Volume mercato" (o "non pubblicato" — il feed manda sempre 0 su questo dato, quindi lo si dichiara invece di mostrare uno zero fuorviante); "ingresso @{quota}" (il primo ingresso Under 3.5 della partita); "al fischio @{quota}" con lo scarto in tick dall'ingresso (verde se negativo = a favore), presente solo se la partita è arrivata in gioco; "ciclo N di M" (con "esauriti" se i cicli chiusi hanno superato il massimo configurato, o "(massimo non configurato)" se il parametro è a 0); se ci sono già cicli chiusi, il loro numero e il P&L che hanno già prodotto; se la partita è regolata, il risultato finale.
- **Quando scatta**: automatico.
- **Cosa succede dopo**: nessuna azione, solo lettura.
- **Numeri**: massimo cicli = parametro `pre_max_cycles`, di serie **10** (scheda 28).
- **Esempio**: "ingresso @1,50 · al fischio @1,48 (−1 tick) · ciclo 2 di 10 · 1 ciclo chiuso +0,14 €".
- **Cosa vede l'utente**: la riga descritta, sotto le tre linee di quota.
- **Dove**: `components/mike/MikeMatchCard.tsx:315-342,766-823`.
- **Paper o live**: nessuna differenza.

### 14. La tabella "Posizioni"
- **Cosa fa**: una riga per selezione ancora aperta, con colonne: Posizione (lato netto BACK/LAY, nome della linea, euro abbinati, ruoli, e — se presenti — "(+X in ingresso sul book)" in ambra o "(X di chiusura appoggiata)" in teal per distinguere un ordine che aumenterebbe l'esposizione da uno che la chiude), Ingresso (quota media di apertura), Quota ora (best back/lay attuali, e a che prezzo chiuderebbe), Δ ingresso (scarto in tick dall'ingresso rispetto al prezzo di chiusura: verde se a favore, rosso se contro, grigio "= 0 tick"), "Se chiudo ora (netto)" (SOLO il numero netto commissione pubblicato dal servizio: se manca scrive "—" col motivo nel tooltip, mai un calcolo fatto dalla pagina). Se non c'è nessuna posizione: "nessuna posizione aperta —".
- Su una partita regolata i prezzi restano congelati all'ultimo dato del feed (non si legge più un book "di adesso").
- **Quando scatta**: automatico, righe aggiunte/tolte quando cambiano le posizioni.
- **Cosa succede dopo**: nessuna azione dalla tabella stessa (le azioni sono i bottoni in fondo alla card, schede 18-22).
- **Numeri**: nessuno editabile qui.
- **Esempio**: "BACK · Under 3.5 · 10,00 € · ingresso 1,50 · ora 1,42/1,44 · chiudo @1,44 · ▼ 4 tick (verde) · Se chiudo ora +0,55 €".
- **Cosa vede l'utente**: la tabella descritta.
- **Dove**: `components/mike/MikeMatchCard.tsx:825-918`; `lib/mike.ts::positionRows,selectionExposure,lockedIfClosed` (righe 1091-1130).
- **Paper o live**: nessuna differenza di calcolo; solo il badge "SOLDI VERI" in alto lo ricorda.

### 15. "Ordini sul book"
- **Cosa fa**: elenca le gambe ancora vive sul book (non abbinate del tutto): lato, ruolo e selezione, lo stato tradotto (in chiaro col contributo chiesto/abbinato/prezzo medio/residuo, la stessa presentazione usata da Omega e Safe), la nota "resta valido in gioco" se l'ordine ha persistenza PERSIST, e la distanza dal miglior prezzo del momento: "al best" (verde), "N tick sopra/sotto il best" (ambra), o "distanza dal best: —" se non calcolabile. Se non c'è nessun ordine sul book: "—".
- **Quando scatta**: automatico.
- **Cosa succede dopo**: nessuna azione dalla riga stessa; per annullarli tutti c'è il bottone "Annulla ordini" (scheda 20).
- **Numeri**: nessuno editabile qui.
- **Esempio**: "LAY · Green-up Under 3.5 (Under 3.5) · SUL BOOK · 2 tick sotto il best".
- **Cosa vede l'utente**: la lista descritta.
- **Dove**: `components/mike/MikeMatchCard.tsx:920-955`; `lib/mike.ts::bookOrders,legStatusLabel,rigaOrdineDaGamba`.
- **Paper o live**: nessuna differenza.

### 16. "A fine gara, per gol totali" e Liability/Bloccato
- **Cosa fa**: una riga di caselle, una per ogni numero di gol totali possibile (0, 1, 2… fino all'ultima scritta "8+"), col P&L netto che risulterebbe con quel numero di gol; la casella del 4° gol è sempre bordata di rosa con il tooltip "i 4 gol: l'unico esito che perde"; il numero di gol attuali della partita è cerchiato. Sotto: su una partita ancora aperta, "Liability aperta" (netta, in arancione) e "P&L bloccato" (colorato secondo il segno, "—" se ancora nulla è bloccato); su una partita chiusa, invece, "rischio chiuso 0,00 €" e l'esito finale.
- **Quando scatta**: automatico.
- **Cosa succede dopo**: nessuna azione, solo lettura.
- **Numeri**: nessuno editabile.
- **Esempio**: "0: +1,30 € · 1: +1,20 € · 2: +0,90 € · 3: +0,40 € · 4: −8,20 € (bordo rosa) · 5+: +2,00 €".
- **Cosa vede l'utente**: la striscia di caselle e la riga sotto.
- **Dove**: `components/mike/MikeMatchCard.tsx:957-998`; `lib/mike.ts::pnlByTotalCells`.
- **Paper o live**: nessuna differenza di calcolo.

### 17. Il riquadro "Se chiudo tutto ora" (cash out) e le tre righe di spiegazione
- **Cosa fa**: mostra il valore netto totale di chiusura immediata di TUTTA la partita (tutte le selezioni insieme), con la percentuale sulla base e la soglia oltre la quale il bot chiude da solo; una barra di avanzamento verso quella soglia (parte da zero: un valore negativo non mostra "un po' di progresso"); un avviso ambra se il book non ha abbastanza liquidità per chiudere tutto al prezzo mostrato; e fino a tre righe di spiegazione in linguaggio semplice quando applicabili:
  - **riga "intelligente"**: che cosa sta valutando il cash out anticipato (es. "min 0,20 € (1,6%) · a un passo dal 5% · fase calda · aspettare vale +0,10 € → chiude (punteggio_caldo)");
  - **riga "uscita a modello"**: se conviene chiudere subito in perdita o tenere, coi numeri che decidono (es. "uscita HT a modello: tenere vale −0,79 € · P(4) 22% · premio 0,53 € → tiene");
  - **riga "copertura: attende quota migliore"**: perché il bot non ha ancora comprato la copertura (es. "risparmio atteso 9,0% · hazard 4,0% · P(4) mercato 12% · al massimo fino al 10′").
- Sotto, l'esito dell'ultima richiesta fatta dalla UI su questa partita, in italiano (mai un codice grezzo): es. "Cash out in corso…", "Cash out rifiutato: feed stantio", "Cash out armato: annullati 2 ordini sul book · chiusura in corso · netto stimato +0,47 €".
- **Quando scatta**: automatico.
- **Cosa succede dopo**: nessuna azione propria; i bottoni sono a fianco (schede 18-22).
- **Numeri**: soglia di chiusura piena = parametro `cashout_profit_pct`, di serie **5%**; profitto minimo del cash-out intelligente = `cashout_smart_min_pct`, di serie **2%**; "a un passo dalla soglia" = `cashout_smart_tolerance_pct`, di serie **2 punti**; fase calda hazard = `cashout_smart_hazard_hot` **0,10**; fase calda pressione = `cashout_smart_pressure_hot` **1,15**; punteggio caldo = `cashout_smart_goals_hot` **3 gol**; margine EV = `cashout_smart_ev_margin_pct` **1 punto**.
- **Esempio**: "Se chiudo tutto ora +0,44 € (3,6% · chiude da solo a 5,0%)" con la barra al 72% del percorso verso la soglia.
- **Cosa vede l'utente**: il riquadro descritto, a sinistra dei bottoni di azione.
- **Dove**: `components/mike/MikeMatchCard.tsx:84-123,1000-1073`; `lib/mike.ts::cashoutBarPct,cashoutPct`.
- **Paper o live**: nessuna differenza di calcolo; la conferma per premere il bottone cambia (schede 18-19).

### 18. Pulsante "Cash out"
- **Cosa fa**: chiude TUTTA la partita in un colpo solo (Mike non accetta cash out parziali: chiude insieme Under 3.5, Over 4.5 ed eventuale re-ingresso). Mostrato solo se c'è almeno una posizione e la partita non è terminale.
- **Quando scatta/è disabilitato**: il bottone si spegne, con il motivo scritto accanto, in quest'ordine di priorità: 1) una chiusura manuale è già in corso; 2) un'altra operazione è in corso; 3) il feed generale (scanner) è fermo; 4) l'età delle quote di questa partita è sconosciuta (il servizio non la pubblica: "nessun ordine al buio"); 5) il feed di questa partita è fermo; 6) manca una linea nel feed; 7) non c'è nessuna posizione aperta.
- Al clic si apre un dialogo che mostra: il P&L netto di chiusura (dal servizio), la percentuale sulla base e la soglia automatica, il dettaglio riga-per-selezione (breakdown), l'esito dell'ultima richiesta se c'è. In modalità LIVE appare la scritta rossa "MODALITÀ LIVE: soldi veri" e serve una **doppia conferma**: il primo clic sul bottone del dialogo lo arma e il testo diventa "Confermi? soldi veri"; l'armamento decade da solo dopo **10 secondi** (o se il netto cambia, o se le condizioni che avevano abilitato il bottone smettono di valere).
- **Cosa succede dopo**: la richiesta scrive `mike_request('cashout', {event_id, bot:'mike', mode})`. Se la richiesta fallisce, il dialogo resta aperto con l'errore: "Cash out NON riuscito: {motivo}. La posizione è ancora aperta — controlla su Betfair prima di riprovare." Se riesce, il dialogo si chiude e più tardi compare l'esito nella riga dedicata (scheda 17): tipicamente "Cash out armato: annullati N ordini sul book · chiusura in corso · netto stimato +X €" — perché per Mike il "cash out riuscito" all'inizio vuol dire solo che il servizio ha annullato gli ordini sul book e guiderà lui la chiusura vera nei cicli successivi.
- **Numeri**: timeout di armamento LIVE = **10.000 ms** (`MIKE_LIVE_ARM_TIMEOUT_MS`).
- **Esempio**: partita in paper, cash out a +0,55 €: un solo clic sul bottone del dialogo basta, nessuna doppia conferma.
- **Cosa vede l'utente**: il bottone "Cash out {importo}" e il dialogo descritto.
- **Dove**: `components/mike/MikeCashOutButton.tsx` (intero, 246 righe); `components/mike/MikeMatchCard.tsx:1075-1090`; RPC `mike_request` (scheda 50).
- **Paper o live**: la doppia conferma con decadenza scatta SOLO in modalità live della partita.

### 19. Pulsante "Chiudi a mercato" (Flatten)
- **Cosa fa**: chiude subito tutta la partita ai prezzi disponibili in quel momento, SENZA guardare nessuna soglia di profitto: è l'azione più pericolosa delle due chiusure, perché può cristallizzare una perdita. Mostrato solo se c'è almeno una posizione e la partita non è terminale.
- **Quando scatta/è disabilitato**: il flatten si può sempre chiedere (chiude comunque, a differenza del cash out non dipende dal fatto che il servizio sappia calcolare il netto): è disabilitato solo se un'operazione è già in corso o per lo stesso motivo scritto dal cash out (feed stantio, linea assente, ecc.).
- Il dialogo dichiara: "Chiusura IMMEDIATA di {partita} ai prezzi disponibili adesso: il servizio annulla gli ordini sul book e chiude tutte le posizioni senza guardare la soglia di profitto. Se il mercato è contro, la perdita diventa definitiva." Mostra il P&L netto di chiusura (o "n/d" con l'avviso "il servizio non sa quanto vale la chiusura adesso: chiuderesti al buio" se mancante). In LIVE, stessa doppia conferma del cash out: primo clic arma, il bottone diventa "Confermi? soldi veri", decade da solo dopo **10 secondi**.
- **Cosa succede dopo**: la richiesta scrive `mike_request('flatten', {event_id, bot:'mike', mode})`. Se fallisce, il dialogo resta aperto con: "Chiusura NON riuscita: {motivo}. La posizione è ancora aperta — controlla su Betfair prima di riprovare."
- **Numeri**: timeout di armamento LIVE = **10.000 ms** (`MIKE_FLATTEN_ARM_TIMEOUT_MS`, una costante separata dal cash out ma con lo stesso valore — vedi «Cose strane»).
- **Esempio**: partita in perdita che il trader vuole chiudere subito invece di aspettare la regola automatica: preme "Chiudi a mercato", legge il netto negativo nel dialogo, conferma.
- **Cosa vede l'utente**: il bottone "Chiudi a mercato" e il dialogo descritto.
- **Dove**: `components/mike/MikeMatchCard.tsx:344-490,1101-1110`; RPC `mike_request` (scheda 50).
- **Paper o live**: doppia conferma solo in modalità live della partita.

### 20. Pulsante "Annulla ordini"
- **Cosa fa**: annulla SOLO gli ordini ancora sul book (le posizioni già abbinate restano). Mostrato solo se ci sono ordini vivi e la partita non è terminale.
- **Quando scatta/è disabilitato**: disabilitato se un'altra operazione è in corso o se una richiesta "cancel" è già in volo per questa partita.
- **Cosa succede dopo**: nessun dialogo, nessuna conferma: al clic parte subito `mike_request('cancel', {event_id, bot:'mike', mode})`.
- **Numeri**: nessuno.
- **Esempio**: un ordine di ingresso resta sul book da un minuto senza abbinarsi: il trader preme "Annulla ordini" per ritirarlo.
- **Cosa vede l'utente**: il bottone "Annulla ordini".
- **Dove**: `components/mike/MikeMatchCard.tsx:1092-1100`.
- **Paper o live**: nessuna conferma extra in nessuna delle due.

### 21. Pulsante "Salta"
- **Cosa fa**: esclude la partita dal lavoro del bot. Mostrato solo se la partita non è terminale, non ha posizioni aperte e non è già "SALTATA".
- **Quando scatta/è disabilitato**: disabilitato se un'operazione è in corso o se una richiesta "skip_event" è già in volo.
- **Cosa succede dopo**: nessun dialogo; al clic parte `mike_request('skip_event', {event_id, bot:'mike', mode})`. La partita passa alla sezione "⚠️ DA SISTEMARE".
- **Numeri**: nessuno.
- **Esempio**: una partita che il trader non vuole seguire (es. squadre poco affidabili): la salta prima che il bot entri.
- **Cosa vede l'utente**: il bottone "Salta".
- **Dove**: `components/mike/MikeMatchCard.tsx:1111-1118`.
- **Paper o live**: nessuna differenza.

### 22. Pulsante "Riprendi"
- **Cosa fa**: rimette in gioco una partita "SALTATA" o in "ERRORE", oppure riabilita il rientro dopo una chiusura manuale pre-fischio ("NESSUN RIENTRO"). È l'unico bottone raggiungibile anche sugli stati terminali di errore.
- **Quando scatta/è disabilitato**: mostrato se lo stato è SKIPPED o ERROR, oppure se `flags.noReentry` è attivo; disabilitato se un'operazione è in corso o se "resume_event" è già in volo.
- **Cosa succede dopo**: nessun dialogo; al clic parte `mike_request('resume_event', {event_id, bot:'mike', mode})`.
- **Numeri**: nessuno.
- **Esempio**: una partita finita in ERRORE per un timeout di rete: il trader preme "Riprendi" per farla ripartire dal ciclo successivo.
- **Cosa vede l'utente**: il bottone "Riprendi" (bordo teal).
- **Dove**: `components/mike/MikeMatchCard.tsx:1119-1126`.
- **Paper o live**: nessuna differenza.

### 23. La proposta di uscita da approvare (uscite manuali)
- **Cosa fa**: quando l'interruttore "Uscite automatiche" di Mike è SPENTO (di serie lo è: vedi scheda 28), il bot non esegue più da solo le uscite discrezionali (green-up, uscita al fischio, cash out, uscita del re-ingresso): scrive la sua proposta nel contesto della partita e questo riquadro la mostra, sotto la card della partita. Mostra: il titolo "Mike vorrebbe uscire: {categoria}" (categorie: green-up pre-partita, uscita al fischio, cash out della posizione, uscita del re-ingresso), con "(in perdita)" se urgente (bordo rosso invece che ambra); il motivo scritto dal bot; gli ordini proposti, uno per riga, col prezzo del momento (dal ladder al millisecondo se disponibile, altrimenti dal feed della partita, dichiarato); la spiegazione "al clic: il bot esce a mercato con la sua macchina d'uscita (prezzi e size di quel momento)..."; due numeri — "chiudendo ora" (il valore live adesso) e "alla decisione" (il valore congelato quando la proposta è nata) — e da quanti secondi è stata decisa; il badge di freschezza del feed.
- **Quando scatta/è disabilitato**: il bottone "approva uscita" è disabilitato se il feed è fermo o sconosciuto ("feed fermo o ignoto: non si approva su prezzi vecchi") o se una richiesta è già in volo.
- **Cosa succede dopo**: **un solo clic, nessuna doppia conferma**. Scrive `requestMike('approva_uscita', {event_id, bot:'mike', mode, chiave, contesto:{prezzo_visto, prezzo_segnale, eta_ms, fonte, market_id, selection_id, clic_ms}})`. Dopo l'invio riuscito compare "approvazione inviata: parte al prossimo giro del bot"; se fallisce, "approvazione non inviata: {motivo}". Se il trader non fa nulla, non c'è un pulsante "rifiuta": l'alternativa scritta a fianco è "oppure chiudi a mano con «Chiudi» di Mike" (che in questa scheda equivale al bottone Flatten/Cash out della card); la proposta sparisce da sola quando il motore la consuma o quando decide diversamente.
- **Numeri**: nessun timeout di conferma (a differenza di cash out/flatten, l'approvazione è a un solo clic).
- **Esempio**: "Mike vorrebbe uscire: cash out della posizione — chiudendo ora +0,42 € · alla decisione +0,44 € · deciso 6 s fa". Il trader preme "approva uscita": l'esecuzione parte al giro successivo del bot.
- **Cosa vede l'utente**: il riquadro ambra (o rosso se urgente) sotto ogni card con una proposta viva.
- **Dove**: `components/controlroom/PropostaUscitaMike.tsx` (intero); `pages/Mike.tsx:342-351` (montaggio: un componente, un comando, nessun secondo percorso); RPC `mike_request` con `p_kind='approva_uscita'` (scheda 50).
- **Paper o live**: la modalità della proposta è quella della partita (`ev.mode`), mai quella del toggle della pagina.

### 24. Scheda Operazioni (tabella + curva di equity)
- **Cosa fa**: una riga per PARTITA con il netto grande e colorato delle sue operazioni di oggi (commissione già tolta); cliccando la riga si apre il dettaglio a cascata: i cicli (ingresso → uscita → quanto ha reso), e dentro ogni ciclo le gambe vere (ora, lato, selezione, size, quota, esito). Le gambe nate da un comando dell'utente (cash out/flatten manuale) hanno il marcatore "manuale". Sotto, la curva di equity della giornata (gradini al momento di regolamento, P&L cumulato), con la scritta "nessun trade ancora regolato oggi — la curva compare al primo incasso" quando è vuota. Se ci sono operazioni dell'altra modalità (paper/live) non mostrate, o se le righe caricate hanno toccato il tetto della RPC (500), un avviso lo dichiara.
- **Quando scatta**: al clic su una partita si apre/chiude il dettaglio.
- **Cosa succede dopo**: cliccando il nome della partita dalla riga si torna alla scheda Partite con la card evidenziata per 2 secondi.
- **Numeri**: tetto di righe della RPC = **500** (`MIKE_TRADES_LIMIT`).
- **Esempio**: "Inter - Milan: +1,84 €" espandibile in "ciclo 1: 1,50 → 1,48, +0,14 €" e poi nella gamba vera "back 10,00 € @1,50, ore 18:32".
- **Cosa vede l'utente**: la tabella descritta più la curva sotto.
- **Dove**: `components/mike/MikeEventPnlTable.tsx` (intero); `pages/Mike.tsx:655-683`; `lib/mike.ts::groupMikeTrades,groupMikeTradesByEvent,mikeEquitySeries`.
- **Paper o live**: solo la modalità attiva sul bot.

### 25. Schede "Risultati Pre-Match" e "Risultati Live"
- **Cosa fa**: la stessa tabella della scheda 24, ma filtrata sui cicli aperti/chiusi PRIMA del fischio (Pre-Match: solo l'ingresso Under 3.5 e la sua uscita a +N tick) oppure DOPO il fischio (Live: tutto quello capitato a partita iniziata — uscita al fischio, seconda puntata, copertura, chiusure). Una partita che ha operato in entrambe le fasi compare in entrambe le schede, con gli euro della sua fase.
- **Quando scatta**: automatico secondo il ruolo della gamba che apre ogni ciclo.
- **Cosa succede dopo**: come la scheda 24 (clic per aprire il dettaglio, link alla card).
- **Numeri**: nessuno.
- **Esempio**: una partita chiusa in profitto pre-match e poi rientrata dopo un gol compare sia in "Risultati Pre-Match" con il primo ciclo, sia in "Risultati Live" col re-ingresso.
- **Cosa vede l'utente**: due tabelle identiche nella forma, filtrate per fase.
- **Dove**: `pages/Mike.tsx:685-720`; `lib/mike.ts::fasePerCiclo,MIKE_RUOLI_APERTURA_PRE,MIKE_RUOLI_APERTURA_LIVE`.
- **Paper o live**: come la scheda 24.

### 26. Scheda Attività
- **Cosa fa**: elenco di tutto quello che il servizio ha fatto, riga per riga, con l'ora al secondo, un'etichetta colorata per tipo (badge rosso per le righe critiche: ordine in verifica, linea assente nel feed, flusso prezzi interrotto, ecc.) e una frase in italiano tradotta dal dato tecnico — mai un codice o un JSON grezzo (tranne, in teoria, per un tipo di evento mai visto prima: vedi «Cose strane»). Filtrabile per partita.
- **Quando scatta**: automatico, si allunga a ogni evento nuovo del servizio.
- **Cosa succede dopo**: nessuna azione, solo lettura.
- **Numeri**: nessuno.
- **Esempio**: "Inter - Milan · ciclo 1 chiuso: 1,50 → 1,48 · P&L bloccato +0,14 €"; "ordine con esito ignoto su Betfair · in verifica" (rosso).
- **Cosa vede l'utente**: la lista scorrevole con i filtri sopra.
- **Dove**: `components/trading/ActivityFeed.tsx` (intero); `pages/Mike.tsx:722-740`; `lib/mike.ts::mikeActivityLine,MIKE_ACTIVITY_KINDS,MIKE_ACTIVITY_EXTRA` (righe 1185-1300, oltre 30 tipi di evento).
- **Paper o live**: mostra tutte le righe della giornata, con l'eventuale badge di modalità sulla singola riga se dichiarata dal servizio.

### 27. Scheda Storico
- **Cosa fa**: un calendario mensile con il P&L di ogni giorno, un pannello con le statistiche del periodo scelto (settimana/mese/eccetera), e il dettaglio del giorno selezionato. Mike NON ha un obiettivo di giornata, quindi il calendario non mostra i pallini di "centrato/non centrato" che ha Omega. Un pulsante "Aggiorna" ricarica a comando. Se una finestra richiesta supera 400 giorni viene ridotta con un avviso.
- Se le migrazioni dello storico non sono applicate, l'errore tecnico "function trading_daily_history(...) is not unique" (o simili) viene tradotto in "storico Mike: applica migrations/mike_history_v2.sql (...)" invece di un codice grezzo.
- **Quando scatta**: al cambio di mese/periodo o al clic su un giorno del calendario.
- **Cosa succede dopo**: se nel dettaglio del giorno c'è una posizione ancora viva, un pulsante riporta alla scheda Partite.
- **Numeri**: tetto finestra storico = **400 giorni**.
- **Esempio**: "Giornata operativa = fuso Europe/Rome · oggi 29 settembre 2026 · P&L realizzato = posizioni PIAZZATE nel giorno (chiusure incluse), anche se si regolano dopo."
- **Cosa vede l'utente**: calendario + pannello + dettaglio giorno.
- **Dove**: `components/trading/TradingHistory.tsx` (intero); `pages/Mike.tsx:742-750`; `lib/mike.ts::mikeHistoryErrorMessage,withMikeHistoryError`; RPC `get_mike_daily`/`get_mike_day_trades` (scheda 52).
- **Paper o live**: mostra solo la modalità CORRENTE del bot (il parametro di filtro modalità della RPC non viene passato esplicitamente dalla pagina di Mike, quindi vale sempre "quella con cui gira ora").

### 28. Il pannello "Parametri Mike"
- **Cosa fa**: un bottone "Parametri" nell'header apre un pannello laterale con TUTTI i parametri di Mike, raggruppati in 8 sezioni, nell'ordine: **Generale**, **Pre-match**, **Dal fischio d'inizio**, **Copertura Over 4.5**, **Cash-out globale**, **Uscite HT / 2T**, **Re-ingresso (gol + 3.5)**, **Rischio**. Ogni gruppo ha una nota introduttiva che spiega COSA governa (es. Rischio: "tetti e stop: sono l'ultima barriera prima dei soldi veri.").
- Ogni campo numerico ha min/max scritti nel suo aiuto; se il valore digitato esce dai limiti, il campo lo riporta dentro e scrive sotto "clampato a {valore} (ammesso {min} … {max})". Un pallino ambra accanto al titolo del pannello e la scritta "modifiche non salvate: premi «Salva parametri» per applicarle al servizio" avvertono quando ci sono modifiche non ancora inviate. Il pannello si riallinea da solo ai valori del server SOLO se l'utente non ha ancora toccato nulla (non si perde mai un editing in corso).
- Il campo "Uscite automatiche" non è una casella di spunta qualunque: è lo stesso interruttore condiviso descritto nella scheda 29 (stesso testo, stessa conferma per passare ad automatiche).
- **Quando scatta**: bottone "Default" riporta la BOZZA ai valori di fabbrica (uguali a quelli del servizio) ma NON salva da solo: serve poi premere "Salva parametri". Il bottone "Salva parametri" applica i parametri al servizio, che li rilegge a ogni ciclo (si applicano "a caldo", senza fermare il bot).
- **Cosa succede dopo**: il salvataggio scrive `mike_update_params(p_params)` (scheda 47); il servizio userà i nuovi valori dal ciclo successivo.
- **Numeri**: vedi la tabella completa più sotto (oltre 100 parametri).
- **Esempio**: si cambia "Stake Under 3.5" da 10 a 15, si preme "Salva parametri": il pallino ambra e la nota scompaiono, il prossimo ingresso userà 15 €.
- **Cosa vede l'utente**: il pannello descritto.
- **Dove**: `components/mike/MikeParamsSheet.tsx` (intero); `components/trading/ParamsSheetBase.tsx` (intero); `lib/mike.ts::MIKE_PARAM_FIELDS,MIKE_PARAM_DEFAULTS,mergeMikeParams` (righe 421-616).
- **Paper o live**: la modalità NON è un parametro di questo pannello — si cambia solo dal toggle in alto (scheda 3), con conferma; lo dice anche il testo in fondo al pannello.

## Elenco completo dei parametri di Mike modificabili dalla UI

Specchio dichiarato di `Betfair/mike/config.py::PARAM_SPEC` (confrontato riga per riga: le **106** chiavi coincidono per nome, tipo e limiti in entrambi i file; `config.BACKEND_ONLY_PARAMS` è vuota, cioè oggi non esiste nessun parametro che il motore usa e la UI non mostra — vedi però la sezione "Cose NON visibili" più sotto per le costanti che non sono affatto parametri).

**Generale**
| chiave | valore di serie | limiti | significato |
|---|---|---|---|
| `stake` | 10,0 € | 0,50–500 | importo LIBERO per gamba dell'ingresso Under 3.5 |
| `commission_pct` | 5 % | 0–20 | aliquota commissione Betfair |
| `entry_hours_before_ko` | 1 ora | 0,25–12 | da quante ore prima del calcio d'inizio il bot lavora la partita |
| `competition_filter` | "" (vuoto = tutte) | testo libero | elenco competizioni ammesse, separate da virgola |
| `decide_min_interval_ms` | 500 ms | 100–5000 | intervallo minimo fra due decisioni sulla stessa partita |
| `feed_max_age_s` | 45 s | 3–180 | età massima della riga del feed per GUARDARE |
| `scanner_alive_max_s` | 75 s | 10–300 | deroga: riga vecchia ma scanner vivo = prezzo comunque valido |
| `book_seen_max_s` | 90 s | 5–600 | oltre questa età un book è trattato come assente |
| `order_max_age_s` | 20 s | 3–120 | soglia stretta per emettere un ordine o chiudere a mano |
| `order_scanner_max_s` | 30 s | 5–120 | oltre l'età sopra, si ordina solo se lo scanner ha battuto da poco |
| `live_resting_enabled` | acceso | on/off | se spento, in LIVE l'uscita torna "a mercato" invece che appoggiata: strategia diversa da quella provata in paper |

**Pre-match**
| chiave | valore di serie | limiti | significato |
|---|---|---|---|
| `pre_enabled` | acceso | on/off | off = nessun ingresso pre-match |
| `pre_entry_price_min` | 1,30 | 1,01–20 | quota minima di ingresso Under 3.5 |
| `pre_entry_price_max` | 3,00 | 1,01–20 | quota massima di ingresso |
| `pre_min_back_size_factor` | 1,0 | 0,5–5 | liquidità minima al best, come multiplo dello stake |
| `pre_max_spread_ticks` | 6 tick | 1–20 | spread massimo back/lay ammesso |
| `pre_green_ticks` | 2 tick | 1–10 | tick del green-up |
| `pre_exit_mode` | resting | resting / taker | resting = lay appoggiata subito; taker = chiude al best quando disponibile |
| `pre_entry_ttl_s` | 60 s | 5–3600 | vita dell'ordine di ingresso non abbinato |
| `pre_max_cycles` | 10 | 0–100 | cicli massimi per partita |
| `pre_reentry_cooldown_s` | 60 s | 0–3600 | pausa dopo un green prima del ciclo successivo |
| `pre_last_entry_min` | 10 min | 1–120 | minuti prima del KO per l'ultimo ingresso |
| `last_entry_persist` | acceso | on/off | l'ultimo ingresso resta valido anche in gioco (PERSIST) |
| `last_entry_ticks_above` | 0 tick | 0–3 | ultimo ingresso N tick sopra il best (0 = taker al best) |
| `veto_p_under35_cal` | acceso | on/off | veto sulla P calibrata dell'Under 3.5 prima di tenere/rientrare all'ultimo ingresso |
| `veto_p_under35_soglia_130` | 0,807 | 0–1 | soglia P minima a quota 1,30 |
| `veto_p_under35_soglia_150` | 0,684 | 0–1 | soglia P minima a quota 1,50 |
| `veto_p_under35_soglia_200` | 0,514 | 0–1 | soglia P minima a quota 2,00 |
| `veto_p_under35_soglia_250` | 0,385 | 0–1 | soglia P minima a quota 2,50 |
| `veto_p_under35_soglia_300` | 0,275 | 0–1 | soglia P minima a quota 3,00 |
| `cancel_unmatched_after_ko_s` | 120 s | 0–900 | annullo del residuo PERSIST dopo il fischio |

**Dal fischio d'inizio**
| chiave | valore di serie | limiti | significato |
|---|---|---|---|
| `ko_green_enabled` | acceso | on/off | prova prima a uscire in profitto al fischio |
| `ko_green_ticks` | 2 tick | 1–10 | uscita a N tick sotto l'ingresso |
| `ko_green_window_s` | 180 s | 0–900 | finestra dell'uscita dal fischio |
| `ko_green_retry_s` | 5 s | 1–60 | **SENZA EFFETTO dal 16/09** (vedi «Cose strane»): il parametro resta salvato ma nessun ramo lo legge più |
| `second_entry_enabled` | acceso | on/off | seconda puntata dopo un gol precoce |
| `second_entry_stake_pct` | 50 % | 0–200 | seconda puntata come % dello stake iniziale |
| `early_goal_cover_delay_s` | 120 s | 0–900 | prima tranche di copertura dopo il gol |
| `early_goal_cover_pct` | 50 % | 0–100 | quota della copertura nella prima tranche |
| `early_goal_cover2_delay_s` | 180 s | 0–900 | seconda tranche dopo l'abbinamento della prima |

**Copertura Over 4.5**
| chiave | valore di serie | limiti | significato |
|---|---|---|---|
| `cover_enabled` | acceso | on/off | off = Under nudo in gioco |
| `cover_profit_factor` | 1,2 | 1–3 | 1,2 = netto +20% dello stake Under con 5+ gol |
| `cover_policy` | auto | auto/immediate/wait | quando coprire |
| `cover_wait_hazard_max` | 0,06 | 0–1 | attende solo se hazard 3′ ≤ questo |
| `cover_wait_max_min` | 10 min | 0–45 | attesa massima |
| `cover_wait_p4_max` | 0,16 | 0–1 | attende solo se P(4) di mercato ≤ questo |
| `cover_good_price` | 7,0 | 1,01–50 | copre subito se la quota Over è già ≥ questo |
| `cover_wait_min_gain_pct` | 8 % | 0–100 | attende solo se il risparmio atteso ≥ questo |
| `cover_wait_step_min` | 5 min | 1–20 | orizzonte su cui si stima il risparmio |
| `cover_postgoal_delay_s` | 45 s | 0–300 | riprezzo dopo un gol |
| `cover_max_goals` | 2 gol | 0–4 | oltre questo numero, nessuna copertura nuova |
| `cover_rounding` | ceil | ceil/floor/nearest | arrotondamento se non si usano importi esatti |
| `cover_max_overshoot_pct` | 30 % | 0–200 | tetto di sovracopertura ammessa |
| `exact_sizes` | acceso | on/off | on = importo esatto al centesimo; off = legalizza al minimo |
| `cover_rifiuti_max` | 3 | 1–20 | rifiuti consecutivi con lo stesso codice prima di fermare la copertura |
| `cover_retry_min_s` | 15 s | 1–300 | attesa minima fra due tentativi di copertura |
| `cover_place_at_ticks` | 2 tick | 0–6 | copertura N tick sotto il best (cuscinetto per farla abbinare davvero) |

**Cash-out globale**
| chiave | valore di serie | limiti | significato |
|---|---|---|---|
| `cashout_profit_pct` | 5 % | 0,5–50 | soglia di chiusura automatica piena |
| `cashout_base` | total | total/under | total = stake Under + copertura; under = solo stake Under |
| `cashout_place_at_ticks` | 0 tick | 0–3 | chiusura N tick oltre il best |
| `cashout_smart_enabled` | acceso | on/off | cash-out intelligente (chiude prima della soglia se conviene) |
| `cashout_smart_min_pct` | 2 % | 0–50 | profitto minimo per chiudere prima del tempo |
| `cashout_smart_tolerance_pct` | 2 punti | 0–50 | "a un passo dalla soglia" |
| `cashout_smart_hazard_hot` | 0,10 | 0–1 | fase calda: soglia hazard |
| `cashout_smart_pressure_hot` | 1,15 | 1–1,25 | fase calda: soglia pressione |
| `cashout_smart_goals_hot` | 3 gol | 0–8 | punteggio caldo |
| `cashout_smart_ev_margin_pct` | 1 punto | 0–50 | margine per chiudere se aspettare vale meno |
| `close_retry_s` | 10 s | 1–600 | riprezzo del residuo di chiusura |
| `close_max_attempts` | 20 | 1–100 | tentativi massimi di chiusura |

**Uscite HT / 2T**
| chiave | valore di serie | limiti | significato |
|---|---|---|---|
| `uscite_automatiche` | **SPENTO** | on/off | acceso = il bot esegue da solo le uscite discrezionali; spento (di serie dal 25/09 sera) = ogni uscita nuova diventa una proposta da approvare (scheda 23); copertura, cap perdita e regolamento restano sempre automatici |
| `ht_loss_exit_enabled` | acceso | on/off | uscita in perdita a fine primo tempo |
| `ht_loss_pct` | 25 % | 0–100 | perdita tollerata (regola fissa di ripiego) |
| `loss_exit_mode` | model | model/fixed | model = decide col confronto valore certo/atteso; fixed = solo regola fissa |
| `loss_exit_risk_premium_pct` | 10 % | 0–300 | premio al rischio sui 4 gol |
| `loss_exit_p4_prudent` | acceso | on/off | usa la stima più pessimista di P(4) fra modello/empirico/mercato |
| `loss_exit_max_pct` | 0 % (spento) | 0–100 | tetto "non cristallizzare oltre" |
| `loss_exit_emp_min_n` | 200 | 20–5000 | casi minimi della tabella empirica HT→FT |
| `ht_loss_goals_min` | 3 gol | 0–8 | gol minimi per cui vale l'uscita HT |
| `ht_loss_goals_max` | 4 gol | 0–8 | gol massimi |
| `h2_loss_exit_enabled` | acceso | on/off | stessa regola nel secondo tempo |
| `h2_loss_pct` | 25 % | 0–100 | perdita tollerata nel 2° tempo |
| `h2_loss_from_min` | 46′ | 45–100 | inizio finestra 2° tempo |
| `h2_loss_to_min` | 85′ | 45–100 | fine finestra |

**Re-ingresso (gol + 3.5)**
| chiave | valore di serie | limiti | significato |
|---|---|---|---|
| `reentry_enabled` | acceso | on/off | re-ingresso su Under 4.5 dopo un gol e una chiusura in profitto |
| `reentry_green_ticks` | 2 tick | 1–10 | green del re-ingresso |
| `reentry_max_goals` | 1 gol | 0–1 | gol massimi per cui vale (1 = linea 4.5, unica nel feed) |
| `reentry_until_min` | 45′ | 0–100 | entro quale minuto vale il re-ingresso |
| `reentry_exit_until_min` | 0 (mai) | 0–100 | chiusura forzata del re-ingresso (0 = resta sul book fino a fine gara) |
| `reentry_price_min_over_entry` | acceso | on/off | rientra solo se la quota supera il primo ingresso |
| `reentry_hold_if_loss` | spento | on/off | vale solo se è impostata una chiusura forzata |

**Rischio**
| chiave | valore di serie | limiti | significato |
|---|---|---|---|
| `settle_confirm_s` | 60 s | 0–600 | intervallo fra due letture del book a mercato chiuso (minimo reale 5 s) |
| `max_open_matches` | 10 | 1–90 | partite con posizione contemporaneamente |
| `daily_loss_stop` | 50 € | 0–100.000 | stop giornaliero (0 = spento) |
| `max_liability_per_match` | 0 € (spento) | 0–100.000 | capitale massimo per partita |
| `event_loss_cap_pct` | 100 % | 0–500 | cap di perdita per partita: oltre, chiusura forzata |
| `skip_log_interval_s` | 300 s | 10–3600 | intervallo minimo fra due righe di log ripetitive |
| `feed_cache_s` | 4 s | 0–30 | ogni quanto si rilegge il feed |
| `events_reload_s` | 60 s | 0–600 | ogni quanto si rilegge tutta la lista delle partite |
| `aggregates_cache_s` | 20 s | 0–300 | ogni quanto si ricalcolano gli aggregati |
| `reconcile_every_s` | 30 s | 0–600 | ogni quanto gira la riparazione gambe↔righe |
| `idle_cycle_s` | 5 s | 1–60 | cadenza del ciclo a riposo (senza partite in gioco) |
| `publish_heartbeat_s` | 5 s | 0–120 | ogni quanto si rinfresca l'ora di pubblicazione di una partita attiva |
| `publish_idle_heartbeat_s` | 60 s | 0–600 | idem per una partita a riposo |
| `events_batch_write` | acceso | on/off | scrive tutte le schede partita in un colpo solo per giro |
| `stats_min_s` | 10 s | 0–300 | ogni quanto si riscrivono le statistiche di testata |
| `heartbeat_min_s` | 20 s | 0–300 | ogni quanto si scrive il battito del servizio |

**`mode` (paper/live) NON è un parametro**: vive in `mike_control.mode` e si cambia solo dal toggle (scheda 3).

---

## GRUPPO B — Mike nella Control Room (`/control-room`)

La Control Room è il "banco" condiviso di tutti i bot. Mike vi compare come una riga nella plancia comandi, come una scheda per partita (sola lettura) e come voce nella lista posizioni chiuse.

### 29. La riga di Mike nella plancia dei bot (PannelloBot)
- **Cosa fa**: una riga con l'etichetta "Mike", lo stato del servizio in parole ("in esecuzione" / "sta fermandosi" / "fermo" / "in errore"), l'etichetta "prova"/"soldi veri" (o "modalità n/d" se non dichiarata), l'età dell'ultimo messaggio dal canale locale, il P&L di oggi nella modalità attiva, l'interruttore delle uscite (identico alla scheda 23/28), il campo "stake Under 3.5" con il suo valore corrente, e i pulsanti di comando.
- Pulsanti quando il bot è SPENTO: "avvia in prova" (un clic, nessuna conferma) e "avvia con soldi veri" (bordo rosso, un clic arma, poi entro **400 ms** il bottone di conferma resta bloccato, poi appare "confermi? ordini reali su Betfair" da premere).
- Pulsanti quando il bot è ACCESO: "ferma" (un clic, nessuna conferma — sotto una nota dice "ferma le aperture, non le uscite": le posizioni aperte restano sorvegliate); se in paper, "passa a soldi veri" con la stessa doppia conferma da 400 ms; se in live, "passa a prova" a un clic, nessuna conferma.
- Mentre un comando è in corso, la riga scrive "comando inviato — in attesa del servizio (tipica ~2 s)" (cadenza tipica del ciclo di Mike) e, oltre **10 secondi** senza conferma, un avviso ambra dice che potrebbe essere lento o che il comando non è arrivato.
- Se il bot è acceso ma non apre nuove posizioni, una riga ambra dichiara il motivo che il servizio scrive (es. tetto partite raggiunto, con il conteggio "N/M").
- Se il bot è stato fermato automaticamente all'avvio dell'app, una riga lo dice: "fermato all'avvio dell'app: attivazione manuale richiesta".
- **Quando scatta**: ai clic descritti.
- **Cosa succede dopo**: ogni comando chiama, secondo il caso, `mike_activate`, `mike_stop`, `mike_update_params` (schede 45-47); dopo la scrittura riuscita il bot viene "svegliato" sul canale locale (porta 47333) per fargli rileggere subito la riga invece di aspettare il prossimo giro.
- **Numeri**: attesa anti-doppio-clic **400 ms**; cadenza tipica dichiarata del ciclo di Mike **2 secondi** (`Betfair/mike/service.py`); "attesa ragionevole" prima dell'avviso di lentezza = 3× la cadenza tipica, minimo **10 secondi**.
- **Esempio**: si preme "avvia con soldi veri": il bottone diventa "confermi? ordini reali su Betfair" per 400 ms disabilitato, poi cliccabile; confermando, il bot passa a `running`/`live`.
- **Cosa vede l'utente**: la riga descritta nella card "Comando dei bot".
- **Dove**: `components/controlroom/PannelloBot.tsx` (intero, righe 489-846 per la riga di un bot); `lib/interruttori.ts::INTERRUTTORI` (riga 146-149, id `'mike'`), `avviaBot,fermaBot,cambiaModalita,cambiaImporto` (righe 860-1013).
- **Paper o live**: la scelta iniziale è del trader; una volta armata una partita, la SUA modalità resta congelata finché non si chiude (vedi scheda 4).

### 30. La riga "Ordini reali" (gate condiviso OFF/PAPER/LIVE)
- **Cosa fa**: NON è specifica di Mike, ma governa anche Mike: un interruttore unico per tutta la piattaforma con tre livelli — OFF (nessun ordine reale da nessun bot), PAPER (ordini simulati), LIVE (ordini reali su Betfair). Mostra il modo EFFETTIVO (il più restrittivo fra il tetto dichiarato dall'ambiente/.env e la scelta fatta qui), da dove arriva il dato (canale del runner calcio o database), chi e quando l'ha cambiato.
- **Quando scatta/è disabilitato**: i pulsanti "off"/"paper" sono a un clic; "live" richiede la doppia conferma (primo clic arma, poi entro 400 ms il bottone resta bloccato, poi "confermi? ordini reali su Betfair"); LIVE è selezionabile solo se il tetto dichiarato dall'ambiente è LIVE, altrimenti il pulsante è disabilitato col motivo scritto.
- **Cosa succede dopo**: scrive la scelta con la RPC owner-only `set_live_order_mode` (letta dalla RPC `get_live_settings`).
- **Numeri**: attesa anti-doppio-clic 400 ms; rilettura di sicurezza ogni **30 secondi**; rilettura forzata dal canale al massimo ogni **2 secondi**.
- **Esempio**: se l'ambiente ha un tetto "PAPER", anche scegliendo "LIVE" qui il modo effettivo resta PAPER e un avviso ambra lo spiega ("il tetto si alza solo dal .env, con il riavvio").
- **Cosa vede l'utente**: la riga "Ordini reali" subito sopra l'elenco dei bot.
- **Dove**: `components/controlroom/RigaOrdiniReali.tsx` (intero, condiviso, non specifico di Mike).
- **Paper o live**: è il tetto sopra ogni singolo bot, Mike compreso.

### 31. La riga "Freno" (kill switch condiviso)
- **Cosa fa**: NON è specifica di Mike, ma lo ferma insieme a tutti gli altri: un freno unico, tirato = nessun bot apre nuove posizioni (né in live né in paper); le chiusure restano sempre servite.
- **Quando scatta/è disabilitato**: "tira il freno" è un solo clic, senza nessuna domanda (un freno d'emergenza con una conferma davanti non sarebbe un freno d'emergenza). "rilascia" richiede DUE conferme in sequenza ("confermi? i bot accesi tornano ad aprire" poi "sì, rilascia il freno"), ciascuna con l'attesa anti-doppio-clic di 400 ms. Se il freno è tirato anche dalla variabile d'ambiente del runner, un avviso dice che da qui non si può togliere.
- **Cosa succede dopo**: scrive con la RPC owner-only `set_live_kill_switch`.
- **Numeri**: attesa anti-doppio-clic 400 ms; rilettura di sicurezza ogni 30 secondi.
- **Esempio**: il trader vede un comportamento anomalo su più bot insieme e preme "tira il freno": tutti i bot, Mike compreso, smettono di aprire nuove posizioni, ma le chiusure in corso proseguono.
- **Cosa vede l'utente**: la riga "Freno" subito sotto "Ordini reali".
- **Dove**: `components/controlroom/RigaFreno.tsx` (intero, condiviso, non specifico di Mike).
- **Paper o live**: vale per entrambe.

### 32. Il pannello parametri di Mike nella Control Room
- **Cosa fa**: lo STESSO componente `MikeParamsSheet` della pagina propria di Mike (scheda 28), montato sulla prima riga di Mike nella plancia: non è una copia, è lo stesso pannello.
- **Quando scatta**: come la scheda 28. Se i parametri di Mike non sono ancora stati letti dalla Control Room, al posto del pannello compare "Parametri non letti — bot Mike" invece di un pannello vuoto che scriverebbe tutto a default.
- **Cosa succede dopo**: salva con `mike_update_params`.
- **Numeri**: gli stessi della scheda 28.
- **Esempio**: identico alla scheda 28.
- **Cosa vede l'utente**: il pulsante "Parametri" sulla riga di Mike.
- **Dove**: `pages/ControlRoom.tsx:400-420` (nome della variabile locale scritto "mibeParams", refuso innocuo — vedi «Cose strane»).
- **Paper o live**: nessuna differenza.

### 33. La card di Mike nella Control Room (sola lettura)
- **Cosa fa**: dentro la card generica di ogni partita, se la partita è seguita anche da Mike, compare un riquadro "Mike — modello e mercato su questa partita" con: badge di freschezza feed (stesse soglie/colori della scheda 9; "partita chiusa" su partita terminale, mai il rosso); P(4 gol esatti) mercato/modello/pre-partita; gol attesi e la loro fonte ("nessuna (bot cieco sul modello)" se assente); quote Under 3.5/Over 4.5 e volume; quota di ingresso, quota al fischio con lo scarto in tick, ciclo/cicli chiusi; responsabilità (liability), P&L bloccato, cash out (con l'avviso "parziale" se il book non copre l'intera chiusura); e infine "se finisce con N gol" per l'intera partita.
- Monta anche la proposta di uscita da approvare (scheda 34) se ce n'è una viva.
- **Questa scheda NON ha bottoni propri di chiusura**: oggi in Control Room nessun comando muove ordini di Mike da qui fuori dalla proposta di uscita — il "Chiudi" generico della riga (scheda 35) resta il solo modo di chiudere manualmente da questa pagina.
- **Quando scatta**: automatico, appare solo nelle linguette "Live" e "Posizioni aperte" del programma condiviso — **non** nella linguetta "Pre-match", dove il modello di Mike non è mostrato.
- **Cosa succede dopo**: nessuna azione propria.
- **Numeri**: nessuno editabile qui.
- **Esempio**: "P(4 gol esatti) mercato 18,0% · modello 15,2% · gol attesi 1,40 · 1,10 (fonte statistiche partita)".
- **Cosa vede l'utente**: il riquadro descritto dentro la card della partita.
- **Dove**: `components/controlroom/SchedaMike.tsx` (intero); `pages/ControlRoom.tsx:1299,1396` (montaggio con `mike={mikeEventi.get(event_id)}`).
- **Paper o live**: nessuna differenza di calcolo.

### 34. La proposta di uscita di Mike, nella Control Room
- **Cosa fa**: lo STESSO componente e lo stesso comando della scheda 23, montato dentro la card di Mike in Control Room (`SchedaMike`).
- **Quando scatta/Cosa succede dopo/Numeri/Esempio**: identici alla scheda 23.
- **Cosa vede l'utente**: il riquadro ambra/rosso, qui dentro la card generica della partita invece che sotto la card dedicata di Mike.
- **Dove**: `components/controlroom/SchedaMike.tsx:115`; `components/controlroom/PropostaUscitaMike.tsx` (stesso file della scheda 23).
- **Paper o live**: come la scheda 23.

### 35. Il bottone "Chiudi" di una riga di Mike, in Control Room
- **Cosa fa**: nelle tabelle di posizioni/operazioni della Control Room, ogni riga di Mike ha un bottone "Chiudi". **Per Mike il bottone chiude l'INTERA PARTITA** (ingresso, copertura, ordini vivi), non la singola riga: è scritto nel tooltip ("Mike chiude l'intera posizione della PARTITA (ciclo: ingresso, copertura, ordini vivi), sull'abbinato, nella modalità della partita").
- **Quando scatta/è disabilitato**: spento, col motivo scritto, se: la riga è già regolata/annullata/errore (nessun bottone, non è una posizione); è una gamba di chiusura ("si chiude con la sua apertura"); la modalità della riga non è dichiarata ("non si chiude alla cieca"); lo stato è "coperta per intero" o "in riconciliazione"; oppure, specifico di Mike, se la partita della riga non è nota ("Mike chiude per partita").
- **Cosa succede dopo**: **nessuna doppia conferma nel bottone stesso**. Al clic scrive `mike_request('cashout', {event_id, trade_id, bot:'mike', mode})`. Accanto al bottone compare la fase: "richiesta inviata" → "presa in carico" (per Mike questa fase resta finché il servizio non ha finito di guidare la chiusura: un `phase:'armed'` per Mike NON conta ancora come "eseguita") → "eseguita" (quando la riga cambia davvero: si copre o si regola) oppure "rifiutata: {motivo}". Oltre **3 minuti** senza un esito finale, la fase forzata diventa "esito ignoto" col messaggio "nessun esito dal bot da 3 minuti: il servizio è acceso? Controlla la riga prima di riprovare".
- **Numeri**: scadenza esito = **180 secondi**.
- **Esempio**: si preme "Chiudi" su una riga Mike: la fase passa a "presa in carico" mentre il bot annulla gli ordini sul book e guida la chiusura nei cicli successivi, poi "eseguita" quando la posizione risulta chiusa.
- **Cosa vede l'utente**: il bottone "Chiudi" e la fase accanto.
- **Dove**: `components/controlroom/chiudiRiga.ts` (intero, righe 97-125,159-162,194-196,257-274); `components/controlroom/BottoneChiudiRiga.tsx` (intero).
- **Paper o live**: la modalità è quella DICHIARATA dalla riga, mai indovinata; un comando non parte se non è dichiarata.

### 36. La scheda "Posizioni chiuse" — Mike
- **Cosa fa**: Mike è uno dei bot filtrabili (pulsante "Mike" fra i filtri), con la sua chiave propria (non si divide per sport come Safe). Le sue posizioni chiuse ereditano tutto il comportamento generico: raggruppamento per giornata di regolamento → bot → partita → ciclo, badge di certezza della chiusura (CHIUSA · CONFERMATA, REGOLATA DAL MERCATO, PARTIALE · ESPOSIZIONE RESIDUA, IN ATTESA DI ABBINAMENTO, CHIUSURA FALLITA · ANCORA APERTA, NON VERIFICABILE), etichetta lato "banca"/"punta", modalità "veri"/"prova", e la fonte di ogni cifra (Betfair / stimato / prova) sempre scritta accanto al numero. È una scheda di **sola lettura**, nessun comando qui.
- **Quando scatta**: al clic sul filtro "Mike" o sfogliando le giornate.
- **Cosa succede dopo**: nessuna azione, si può solo aprire/chiudere il dettaglio di ogni ciclo.
- **Numeri**: soglia oltre la quale le partite partono chiuse per velocità = **40 operazioni**.
- **Esempio**: "Mike · 6 operazioni · 3 partite · +1,84 €".
- **Cosa vede l'utente**: il blocco "Mike" dentro l'elenco, con le sue partite e i suoi cicli sotto.
- **Dove**: `components/controlroom/PosizioniChiuse.tsx` (intero, righe 69-76,462-465 per Mike).
- **Paper o live**: filtro "veri"/"prova" separato in alto, mai sommati.

### 37. L'avviso "Mike: uscita appoggiata SPENTA in live"
- **Cosa fa**: una card arancione con l'icona di allarme che compare quando il parametro `live_resting_enabled` di Mike (scheda 28, gruppo Generale) è SPENTO: "In live l'uscita torna «a mercato»: Mike esegue una strategia diversa da quella provata in paper, e il ciclo che in demo chiude in profitto lì chiude in perdita."
- **Quando scatta**: quando la Control Room legge `live_resting_enabled === false` dai parametri di Mike.
- **Cosa succede dopo**: solo un avviso, nessuna azione; per risolverlo si riaccende il parametro dal pannello (scheda 28/32).
- **Numeri**: nessuno.
- **Esempio**: il trader ha spento "LIVE: uscita appoggiata attiva" per una prova, dimenticandosi di riaccenderlo: la card compare finché resta spento.
- **Cosa vede l'utente**: la card arancione, in Control Room (non nella pagina propria di Mike).
- **Dove**: `pages/ControlRoom.tsx:672-683`; il valore booleano è calcolato in `components/controlroom/useControlRoom.ts` (righe 870-876,3680) come `leggiBool(mike?.control?.params, 'live_resting_enabled')`.
- **Paper o live**: l'avviso riguarda solo il rischio della modalità live.

### 38. L'indicatore "fonte righe" di Mike
- **Cosa fa**: un'etichetta diagnostica che dice se le righe di Mike mostrate in Control Room arrivano dal canale locale (push, più fresco) o dal database (poll), con l'età del dato.
- **Quando scatta**: automatico.
- **Cosa succede dopo**: nessuna azione, solo diagnostica.
- **Numeri**: nessuno.
- **Esempio**: "Mike: canale · 2 s" oppure "Mike: db · 14 s".
- **Cosa vede l'utente**: l'etichetta, in una riga diagnostica della Control Room.
- **Dove**: `pages/ControlRoom.tsx:1005-1016`.
- **Paper o live**: nessuna differenza.

### 39. La card "Saldo Betfair" (canale locale Mike incluso)
- **Cosa fa**: NON è specifica di Mike: mostra il saldo del conto Betfair, aggiornato anche quando Mike piazza o chiude un ordine LIVE, perché il socket locale di Mike (porta 47333) pubblica il topic "account" dopo ogni movimento con soldi veri, insieme a calcio/tennis/Omega/Safe.
- **Quando scatta**: automatico; un pulsante a forma d'occhio permette di nascondere il saldo (preferenza salvata nel browser).
- **Cosa succede dopo**: nessuna azione oltre a nascondere/mostrare.
- **Numeri**: soglia di saldo "stantio" = **120 secondi**.
- **Cosa vede l'utente**: la card del saldo, in Control Room (non nella pagina di Mike).
- **Dove**: `components/controlroom/SaldoBetfairCard.tsx` (riga 31, elenco `CANALI_SALDO` include `'mike'`); `lib/saldoBetfair.ts`.
- **Paper o live**: il saldo reale si muove solo con ordini in modalità live.

---

## GRUPPO C — Le funzioni del database che i pulsanti chiamano

Tutte le funzioni di Mike sono `SECURITY DEFINER` e cominciano leggendo `public.betfair_live_is_owner()`: se chi chiama non è il proprietario, la funzione rifiuta con "non autorizzato (owner-only)". Tutte sono revocate a `public`/`anon` e concesse solo a `authenticated` (la UI, tramite login) e `service_role` (il servizio Python). Nessuna tabella di Mike è leggibile/scrivibile direttamente dal browser: tutto passa da queste funzioni o da una `SELECT` protetta da RLS owner-only.

### 40. La tabella `mike_control`
- **Cosa fa**: un'unica riga (singleton, `id=1`) con lo stato del bot: `status` (idle/running/stopping/stopped/error), `mode` (paper/live), `params` (JSON coi 106 parametri della scheda 28), `stats` (JSON coi numeri di testata), `error`, `started_at`, `stopped_at`, `heartbeat_at`, `updated_at`.
- **Chi la può leggere**: solo `authenticated` proprietario, via RLS (`mike_control_select_owner`, condizione `betfair_live_is_owner()`); realtime attivo (fa parte di `supabase_realtime`).
- **Chi la può scrivere**: nessuno direttamente (RLS senza policy di scrittura, `REVOKE ALL` da `anon`/`authenticated`): si scrive solo tramite le RPC `mike_activate`/`mike_stop`/`mike_update_params` (schede 45-47), eseguite come `service_role` dentro la funzione.
- **Dove**: `migrations/mike_bot.sql:24-41`.

### 41. La tabella `mike_events`
- **Cosa fa**: una riga per ogni partita seguita: identità (`event_id`, `fixture_id`, `event_name`, `competition`, `ko_at`), `mode`, `markets` (id dei mercati Betfair), `state` (uno dei 21 stati), `cycle_no`, `entry_price_initial`, `dossier` (dati del modello statistico), `live` (tutto quello che alimenta la card: quote, P&L, cash out...), `positions` (le gambe), `ctx` (contesto interno, incluse le proposte di uscita), `skipped`, `settled_pnl`, `updated_at`.
- È la sorgente di TUTTO quello che mostrano le schede 9-17, 23, 33-34.
- **Chi la può leggere**: solo il proprietario via RLS; realtime attivo.
- **Chi la può scrivere**: nessuno direttamente da qui: solo il servizio Python, come `service_role` (fuori dalla mia area).
- **Dove**: `migrations/mike_bot.sql:43-74`; vincoli stati/ruoli allargati in `migrations/mike_vincoli_flusso_fischio_2026-09-14.sql`.

### 42. La tabella `mike_trades`
- **Cosa fa**: una riga per ogni gamba/ordine (specchio "append/update"): identità (`event_id`, `event_name`, `sport`), `strategy`/`role` (uno degli 11 ruoli), `cycle_no`, `persistence`, `market_id`/`market_type`/`selection_id`/`selection_name`, `side`, `mode`, `price`/`size`/`liability`/`commission`, `minute_at_entry`/`score_at_entry`, `status` (pending/open/hedged/won/lost/void/error), `pnl` (NETTO commissione), `bet_id`, `placed_at`/`settled_at`, `origin` (auto/manual), `closes_trade_id` (collega una chiusura alla sua apertura), `signal_key`, `meta`. Dalla migrazione del 16/09 porta anche `size_requested`, `size_matched`, `size_remaining`, `avg_price_matched`, `betfair_updated_at` (il "chiesto/abbinato/residuo/medio" mostrato nella tabella Posizioni e negli Ordini sul book, schede 14-15). Dalla migrazione del 24/09 porta anche `pnl_betfair` e `pnl_betfair_settled_at` (il netto REALE regolato da Betfair, separato dal calcolo stimato del bot: è la fonte del badge "Betfair"/"stimato" nella scheda 36).
- È la sorgente delle schede 14, 15, 24, 25, 36.
- **Chi la può leggere**: solo il proprietario via RLS; realtime attivo.
- **Chi la può scrivere**: nessuno direttamente: solo il servizio, come `service_role` (`GRANT SELECT, UPDATE ON TABLE mike_trades TO service_role`; resta chiusa ad `authenticated` per scelta esplicita).
- **Dove**: `migrations/mike_bot.sql:76-122`; `migrations/mike_bot_v2.sql:23-27` (colonna `closes_trade_id`); `migrations/trades_consapevolezza_ordine_2026-09-16.sql:71-84`; `migrations/pnl_betfair_reale_2026-09-24.sql:45,64,93,100`.

### 43. La tabella `mike_activity`
- **Cosa fa**: registro append-only di ogni evento del servizio: `ts`, `event_id`, `kind` (uno dei ~33 tipi della scheda 26), `payload`. È la sorgente della scheda 26.
- **Chi la può leggere**: solo il proprietario via RLS; realtime attivo.
- **Chi la può scrivere**: nessuno direttamente: solo il servizio.
- **Dove**: `migrations/mike_bot.sql:124-134`.

### 44. La tabella `mike_requests`
- **Cosa fa**: la coda dei comandi che la UI manda al bot: `kind` (cashout/flatten/skip_event/resume_event/cancel/approva_uscita), `payload`, `status` (pending/processing/done/rejected/error), `result` (JSON con `code`, `message` in italiano, ed eventuali campi come `phase:'armed'`, `cashout_net`, `cancelled`), `created_at`/`updated_at`. È la sorgente di ciò che leggono le schede 18-23, 35.
- **Chi la può leggere**: solo il proprietario via RLS; realtime attivo. La UI la legge anche direttamente con una `SELECT` (`fetchMikeRequests`), sempre sotto la stessa RLS owner-only.
- **Chi la può scrivere**: nessuno direttamente: SOLO tramite la RPC `mike_request` (scheda 50), che fa l'`INSERT` per conto dell'utente dopo aver controllato il `kind` e l'`event_id`.
- **Dove**: `migrations/mike_bot.sql:136-149`; vincolo `kind` allargato con `approva_uscita` in `migrations/uscite_automatiche_mike_2026-09-25.sql:28-40`; colonna `result` aggiunta in `migrations/mike_bot_v2.sql:25`; stato `'rejected'` aggiunto in `migrations/mike_bot_v2.sql:30-36`.

### 45. `mike_activate(p_mode, p_params)`
- **Cosa fa**: accende il bot. Imposta `status='running'`, `mode=p_mode`, `params = coalesce(p_params, params)` (se non si passano parametri nuovi, quelli attuali RESTANO: non li azzera), `error=NULL`, `started_at=now()`.
- **Quando scatta**: bottone "avvia in prova"/"avvia con soldi veri" (schede 3, 29).
- **Chi la può chiamare**: `authenticated` proprietario, `service_role`; rifiuta se `p_mode` non è "paper"/"live".
- **Cosa restituisce**: la riga intera di `mike_control` aggiornata.
- **Dove**: `migrations/mike_bot.sql:183-203`.
- **Paper o live**: `p_mode` è esattamente la scelta del trader; il default della funzione è "paper" se non specificato, ma la UI passa sempre un valore esplicito.

### 46. `mike_stop()`
- **Cosa fa**: ferma il bot: se era "running" lo porta a "stopping" (il servizio stesso lo porterà poi a "stopped" al giro successivo), altrimenti direttamente a "stopped".
- **Quando scatta**: bottone "Ferma" (schede 3, 29).
- **Chi la può chiamare**: `authenticated` proprietario, `service_role`.
- **Cosa restituisce**: la riga aggiornata di `mike_control`.
- **Dove**: `migrations/mike_bot.sql:205-222`.

### 47. `mike_update_params(p_params, p_mode)`
- **Cosa fa**: aggiorna i parametri e/o la modalità SENZA toccare `status`: è il solo modo di cambiare modalità a bot già acceso senza riaccenderlo. `params = coalesce(p_params, params)`, `mode = coalesce(p_mode, mode)`.
- **Quando scatta**: bottone "Salva parametri" (scheda 28/32), cambio di modalità a bot acceso (scheda 3, "passa a prova"/"passa a soldi veri" quando il servizio già gira), interruttore uscite automatiche (scheda 28/29 — scrive solo la chiave `uscite_automatiche` dentro `params`, tutto il resto passa intatto), cambio dello stake dalla plancia (scheda 29).
- **Chi la può chiamare**: `authenticated` proprietario, `service_role`; rifiuta se `p_mode` non è "paper"/"live"/assente.
- **Cosa restituisce**: la riga aggiornata di `mike_control`.
- **Dove**: `migrations/mike_bot.sql:224-245`.
- **Nota money-critical**: scrivere senza aver prima letto i parametri correnti sostituirebbe TUTTI gli altri con i valori predefiniti — per questo il codice della UI (`lib/interruttori.ts::paramsLetti`) rifiuta di chiamarla se non ha ancora letto una riga di parametri non vuota.

### 48. `get_mike_state()` — l'unica RPC che la pagina legge per tutto
- **Cosa fa**: in un colpo solo restituisce `{control, events, trades, activity, aggregates, requests, day_start, day_by}`: `control` = la riga di `mike_control`; `events` = le partite non terminali + quelle terminali delle ultime 24 ore, ordinate per calcio d'inizio, tetto **200**; `trades` = le righe della giornata operativa (giorno di piazzamento) più tutte le righe ancora vive dei giorni precedenti, ordinate dalla più recente, tetto **500**; `activity` = il registro della giornata operativa, tetto **400**; `requests` = le ultime **50** richieste con esito; `aggregates` = il risultato di `mike_aggregates_sql()`; `day_start` = mezzanotte di Roma di oggi; `day_by` = `'placed'`.
- **Quando scatta**: al primo caricamento della pagina, ogni **15 secondi** come rilettura di sicurezza, e a ogni notifica in tempo reale sulle 5 tabelle di Mike (con un raggruppamento: più notifiche vicine = una sola rilettura, entro **1,5 secondi**; un battito che cambia solo l'ora non fa ricaricare nulla).
- **Chi la può chiamare**: `authenticated` proprietario, `service_role`.
- **Cosa restituisce**: il JSON descritto sopra.
- **Dove**: `migrations/mike_bot.sql:247-284` (prima versione), sostituita da `migrations/mike_bot_v2.sql:149-196` (versione completa con `aggregates`/`requests`/`day_start`/`day_by`).
- **Paper o live**: restituisce le righe di ENTRAMBE le modalità (il filtro per modalità lo applica la pagina, scheda 5-6).

### 49. `get_mike_trades(p_limit)`
- **Cosa fa**: restituisce fino a `p_limit` (di serie 200, la pagina ne chiede fino a 300) righe di `mike_trades`, per uso diagnostico/di ripiego.
- **Quando scatta**: non è la via principale della pagina (che usa `get_mike_state`); resta come funzione di supporto.
- **Chi la può chiamare**: `authenticated` proprietario, `service_role`.
- **Dove**: `migrations/mike_bot.sql:286-302`.

### 50. `mike_request(p_kind, p_payload)`
- **Cosa fa**: accoda UN comando della UI. Controlla che `p_kind` sia uno fra `cashout`, `flatten`, `skip_event`, `resume_event`, `cancel`, `approva_uscita`; che il payload contenga `event_id`; se il tipo è `approva_uscita`, pretende anche `chiave` (la chiave della proposta: senza, rifiuta con "approva_uscita senza chiave della proposta" — non approva mai "qualcosa" al buio). Inserisce la riga in `mike_requests` con `status='pending'`.
- **Quando scatta**: TUTTI i bottoni di azione delle schede 18-23, 35.
- **Chi la può chiamare**: `authenticated` proprietario, `service_role`.
- **Cosa restituisce**: l'id numerico della richiesta appena creata.
- **Dove**: `migrations/mike_bot.sql:304-326` (prima versione, senza `approva_uscita`); allargata in `migrations/uscite_automatiche_mike_2026-09-25.sql:23-69` (aggiunge `approva_uscita` al vincolo `kind` e alla funzione).
- **Paper o live**: la modalità viaggia nel `payload` (scritta dalla UI dalla riga/partita, mai dedotta), il servizio la confronta con quella vera della riga e rifiuta con `richiesta_ambigua` se non combacia.

### 51. `mike_aggregates_sql(p_mode)` / `get_mike_aggregates(p_mode)`
- **Cosa fa**: calcola in una sola scansione i numeri di testata: `realized_total`, `realized_today`, `realized_paper_total`, `realized_live_total` (i realizzati dell'ALTRA modalità, per dichiararli senza nasconderli), `open_count`, `open_liability` (netta dal servizio se disponibile, altrimenti somma delle righe, con `liability_source` dichiarata), `liability_stale` (vero se il battito è più vecchio di **60 secondi**), `won`/`lost`/`won_today`/`lost_today` (per SEGNO del P&L totale del ciclo, non per riga), `cycles_today`, `events_today`, `reconciling`, `day_by`. `p_mode` assente = usa la modalità CORRENTE del bot (mai "tutte": paper e live non si sommano mai).
- **Quando scatta**: chiamata da `get_mike_state()` a ogni caricamento; alimenta le schede 5, 6, 24.
- **Chi la può chiamare**: `mike_aggregates_sql` solo `service_role`; `get_mike_aggregates` (il guscio owner-only) `authenticated` proprietario e `service_role`.
- **Dove**: prima versione senza filtro modalità in `migrations/mike_bot_v2.sql:48-139`; **sostituita** dalla versione filtrata per modalità in `migrations/mike_aggregati_per_modalita_2026-09-13.sql` (l'intero file, 158 righe): la versione senza `p_mike` era un difetto bloccante corretto il 13/09 perché sommava euro veri e simulati.

### 52. Lo storico: `get_mike_daily` / `get_mike_day_trades` (su `trading_daily_history`/`trading_day_trades`)
- **Cosa fa**: il motore condiviso `trading_daily_history`/`trading_day_trades` (usato anche da Omega e Safe) calcola calendario e dettaglio-giorno; `get_mike_daily(p_from,p_to,p_mode)` e `get_mike_day_trades(p_day,p_mode)` lo richiamano con la tabella `mike_trades`, la giornata di attribuzione **PIAZZAMENTO** (non regolamento), e `p_mode` assente = la modalità corrente del bot. Il motore condiviso limita ogni finestra a **400 giorni** (oltre, la ritaglia e lo dichiara con `window_clamped`); considera "piazzata" anche una riga `pending` in riconciliazione (esito ignoto su Betfair, non un errore); conta un ciclo greenato come UNA vittoria, non due righe.
- **Quando scatta**: apertura della scheda Storico (scheda 27) e cambio di mese/giorno/periodo.
- **Chi la può chiamare**: `get_mike_daily`/`get_mike_day_trades` — `authenticated` proprietario, `service_role`; il motore condiviso `trading_daily_history`/`trading_day_trades` — solo `service_role` (mai chiamato direttamente dal browser).
- **Dove**: prima versione (rotta, con firme duplicate che davano l'errore "function ... is not unique") in `migrations/mike_history.sql`; **sostituita** da `migrations/mike_history_v2.sql` (l'intero file, 380 righe: unifica le firme del motore condiviso a 8/4 argomenti, ammette `mike_trades`); poi arricchita con il filtro `p_mode` esplicito da `migrations/mike_storico_per_modalita_2026-09-14.sql` (l'intero file: aggiunge un terzo parametro a entrambe le funzioni, e un quarto ai loro filtri interni — **questa è la versione vigente oggi**, essendo l'ultima nell'ordine cronologico delle migrazioni sullo stesso nome).
- **Nota di ordine**: esiste anche `mike_storico_per_modalita_fix_alias_2026-09-14.sql`, non letto riga per riga in questa sessione: dal commento della versione con filtro esplicito risulta che un bug di alias (`t` invece di `o` in `get_mike_day_trades`) è stato corretto lo stesso giorno; non ho verificato se il fix è dentro il file già letto o in quello a parte — vedi "Non ho letto".

---

## Cosa di Mike NON è visibile o NON è comandabile dalla UI, pur esistendo nel bot

Confrontando `frontend/src/lib/mike.ts::MIKE_PARAM_FIELDS` con `Betfair/mike/config.py::PARAM_SPEC` riga per riga: **le 106 chiavi coincidono esattamente** (stessi nomi, stessi default, stessi limiti) e `config.BACKEND_ONLY_PARAMS` è vuota — oggi non esiste nessun parametro di strategia che il motore usa e la UI non mostra. Restano invisibili dalla UI solo cose che NON sono parametri di strategia:

- **`MIKE_LOCK_PORT`** (env, default **47319**): la porta del lucchetto che garantisce una sola istanza del servizio. Non è nella UI, non è pensata per esserlo.
- **`MIKE_USE_FLUMINE_QUEUE`** (env, default **0**): se il servizio in live usa la coda ordini flumine invece delle chiamate REST dirette. Non editabile dalla UI.
- **`SAFE_PRE_KO_OU_HOURS`** (env, default **1**): non è un parametro di Mike ma dello scanner condiviso; Mike la confronta con il proprio `entry_hours_before_ko` e, se le due non combaciano, scrive un avviso `config_warn` nell'Attività (scheda 26) — ma la env stessa si cambia solo nel `.env`, non da nessun pannello.
- **`CUSTOMER_STRATEGY_REF = "mike"`**: l'etichetta con cui gli ordini live di Mike vengono marcati su Betfair. Costante fissa, non editabile.
- **`EXPECTED_SEL`** (id di selezione attesi Under 3.5=1222344 ecc.): costante puramente documentale, usata solo dai test, mai a runtime né in UI.
- Costanti di cadenza citate dalla Costituzione come "non editabili dalla UI" (`_SETTLE_MAX_WAIT_S`, `db._TOTALS_TTL_S`, `scanner.MIKE_MAX_FOLLOWED`, `_MIKE_FOLLOWED_TTL_S`): non ho potuto verificarle nel codice Python (fuori dalla mia area — le legge chi ha letto `engine.py`/`service.py`), ma **due delle costanti che la Costituzione elencava come "non editabili"** (`_HEARTBEAT_MIN_S`, l'intervallo minimo delle statistiche) **sono oggi invece parametri editabili** (`heartbeat_min_s`, `stats_min_s`, gruppo Rischio): la UI è più ricca di quanto la Costituzione (12/09) documenti — vedi "Differenze dalla Costituzione".

---

## Glossario

- **Ruolo di una gamba** (`role`/`strategy` su `mike_trades`, tradotto da `roleLabel`): `under_entry` = ingresso Under 3.5; `under_green` = green-up (chiusura in profitto) dell'Under 3.5; `under_last` = ultimo ingresso prima del fischio, resta valido in gioco; `under_second` = seconda puntata dopo un gol precoce; `ko_green` = uscita al fischio d'inizio; `over_cover` = copertura sull'Over 4.5; `under_close` = chiusura dell'Under 3.5; `over_close` = chiusura dell'Over 4.5; `reentry` = re-ingresso sull'Under 4.5 dopo un gol; `reentry_green` = green-up del re-ingresso; `manual_close` = chiusura decisa dall'utente (marcata con ✋ nelle tabelle).
- **Fase di un ciclo**: "pre" = aperto e chiuso prima del fischio (ruolo `under_entry`); "live" = tutto il resto (`under_last`, `under_second`, `over_cover`, `reentry` e le loro chiusure).
- **Le 21 fasi della partita** (`state`, badge nella card): WATCH (in attesa) · PRE_ENTRY_PENDING (ingresso in corso) · PRE_OPEN (Under 3.5 aperto) · PRE_GREEN_PENDING (green-up in corso) · HOLD (tiene fino al fischio) · PRE_LAST_ENTRY_PENDING (ultimo ingresso) · IDLE_LIVE (in gioco, nessuna posizione) · LIVE_KO_GREEN (uscita al fischio in corso) · LIVE_SECOND_ENTRY (gol precoce, seconda puntata) · LIVE_UNCOVERED (in gioco, scoperto) · LIVE_COVER_PENDING (copertura in corso) · LIVE_COVERED (in gioco, coperto) · LIVE_CLOSING (chiusura in corso) · FLAT (piatta) · REENTRY_PENDING (re-ingresso in corso) · REENTRY_OPEN (re-ingresso Under 4.5 aperto) · REENTRY_GREEN_PENDING (green del re-ingresso in corso) · SETTLING (in regolamento) · SETTLED (regolata) · ERROR (errore) · SKIPPED (saltata).
- **Cash out / Flatten**: cash out chiude tutta la partita col servizio che prima annulla gli ordini sul book e poi guida la chiusura vera nei cicli successivi ("armato" → poi "eseguito" quando la riga cambia davvero); flatten fa la stessa cosa ma SENZA guardare nessuna soglia di profitto — chiude comunque, anche in perdita.
- **Uscite automatiche / manuali**: interruttore unico per bot (`uscite_automatiche`). Acceso = il bot esegue da solo green-up, uscita al fischio, cash out, uscita in perdita. Spento (di serie) = ogni uscita nuova diventa una PROPOSTA da approvare; le protezioni money-critical (copertura Over 4.5, cap di perdita, regolamento, annulli, riconciliazione) restano SEMPRE automatiche in entrambi i casi.
- **Liability aperta / P&L bloccato**: la Liability è la perdita peggiore possibile sulle posizioni ancora aperte (netta, calcolata dal servizio); il P&L bloccato è il risultato già GARANTITO su una partita, qualunque sia l'esito finale (es. dopo un green-up completo).
- **Ordine "in verifica su Betfair" (`pending_reconcile`)**: un ordine il cui esito reale non si conosce ancora con certezza (per esempio dopo un errore di rete verso Betfair); conta nella liability al caso peggiore finché non si chiarisce, non viene mai trattato come annullato.
- **Canale locale**: il collegamento diretto via WebSocket fra l'app desktop e il servizio Mike (porta **47333**), di sola lettura: porta quote e stato più in fretta del database ma, se cade, la pagina torna semplicemente a leggere dal database (nessun dato sparisce, solo un po' più vecchio).

---

## Differenze dalla Costituzione

`Betfair/mike/COSTITUZIONE_MIKE.md` è datata **12/09/2026** (base `9d09c81`); il codice che ho letto contiene modifiche successive, molte con la loro data nel commento. Elenco solo le differenze che riguardano la mia area (schermate, pulsanti, parametri, database), senza correggerle:

1. **§6 dichiara "72 chiavi" di parametri; il codice attuale ne ha 106.** Sono nate dopo il 12/09: il gruppo intero "Dal fischio d'inizio" (9 chiavi: `ko_green_*`, `second_entry_*`, `early_goal_cover_*`, datate 13/09, specifica §15), il veto sulla P calibrata dell'Under 3.5 (6 chiavi `veto_p_under35_*`, 25/09), `uscite_automatiche` (25/09), i freni sui rifiuti di copertura (`cover_rifiuti_max`, `cover_retry_min_s`, 17/09) e `cover_place_at_ticks` (cert. 12/09 sera), e un gruppo di 15 parametri di cadenza/carico (`scanner_alive_max_s`, `book_seen_max_s`, `order_max_age_s`, `order_scanner_max_s`, `live_resting_enabled`, `feed_cache_s`, `events_reload_s`, `aggregates_cache_s`, `reconcile_every_s`, `idle_cycle_s`, `publish_heartbeat_s`, `publish_idle_heartbeat_s`, `events_batch_write`, `stats_min_s`, `heartbeat_min_s`) che il §6 della Costituzione elenca invece come **"costanti non editabili dalla UI"** (`_HEARTBEAT_MIN_S = 10s`, `db._TOTALS_TTL_S`, ecc. — oggi `heartbeat_min_s` è un parametro con default **20 s**, non più una costante fissa a 10). — `frontend/src/lib/mike.ts:436-554`; `Betfair/mike/config.py:75-379`.
2. **§8 e §13.5 parlano di "19 stati" e "9 ruoli"; oggi sono 21 stati e 11 ruoli.** `LIVE_KO_GREEN`, `LIVE_SECOND_ENTRY` (stati) e `ko_green`, `under_second` (ruoli) sono nati il 13/09 con la specifica §15 del flusso dal fischio d'inizio, dopo la stesura della Costituzione, e il 14/09 il database ha dovuto essere corretto per accettarli (vedi «Cose strane», punto 1). — `migrations/mike_vincoli_flusso_fischio_2026-09-14.sql`; `frontend/src/lib/mike.ts:21-27`.
3. **§8 descrive "5 schede" (Partite, Trade, Attività, Regolate, Storico); oggi sono 6, con nomi diversi.** La scheda "Trade" si chiama oggi "Operazioni"; "Regolate" non esiste più come scheda a sé (era stata tolta già il 13/09 secondo un commento nel codice: ogni partita finisce nei "Risultati" della fase in cui ha operato); al suo posto ci sono DUE schede nuove, "⏱ Risultati Pre-Match" e "🔴 Risultati Live". — `frontend/src/pages/Mike.tsx:578-583`.
4. **§8 dice che il cash out chiude "senza soglia" solo per Flatten; oggi la doppia conferma LIVE decade da sola dopo un tempo preciso (10 secondi) sia per Cash out sia per Flatten**, con due costanti separate identiche (vedi «Cose strane», punto 3) — dettaglio più fine di quanto la Costituzione descriva, non una contraddizione.
5. **§6 non menziona affatto l'interruttore "Uscite automatiche"** (nato il 25/09, tredici giorni dopo la stesura): oggi è un parametro del gruppo "Uscite HT / 2T" e cambia radicalmente il comportamento descritto nelle Fasi 1, 4, 5, 6 del §3 (le uscite discrezionali NON sono più sempre automatiche, come invece dice ancora il §3 e come dichiara esplicitamente superato solo il §14.5-ter per un caso diverso).
6. **§9 elenca i test frontend e la certificazione dati reali con numeri (128+10) fermi al 12/09**: non riletti in questa sessione (fuori area, sola lettura statica del codice), quindi non posso dire se siano ancora quei numeri.

---

## Cose strane

1. **Due vincoli del database non aggiornati per 12 giorni dopo l'introduzione di due stati e due ruoli nuovi.** Il commento in testa a `migrations/mike_vincoli_flusso_fischio_2026-09-14.sql` (che ho letto per intero) racconta che il 13/09 il motore ha imparato gli stati `LIVE_KO_GREEN`/`LIVE_SECOND_ENTRY` e i ruoli `ko_green`/`under_second`, ma il vincolo CHECK di `mike_trades.strategy` e `mike_events.state` non era stato allargato: ogni scrittura con quei valori veniva rifiutata dal database, e — più grave — l'upsert rifiutato non salvava nemmeno `ctx.live_since`, quindi la finestra dell'uscita al fischio non scadeva mai e la partita restava scoperta fino al fischio finale. Il file dice esplicitamente: "su 2000 righe di errore lette dal registro attività, 2000 sono rifiuti di questo vincolo. Il 100%." Non riguarda direttamente un pulsante, ma riguarda la scheda 26 (Attività): quelle righe di errore, oggi corrette, erano il sintomo visibile a schermo di un difetto che durava da 12 giorni.
2. **Il commento sorgente di `veto_p_under35_cal` (frontend) contraddice sia il valore reale sia il commento Python.** In `frontend/src/lib/mike.ts:461-463` il commento del programmatore dice "M1 (25/09, PREPARATO, SPENTO)"; ma il default effettivo del parametro (riga 568 dello stesso file, e `Betfair/mike/config.py:152`) è **acceso** (`true`), e sia l'aiuto mostrato all'utente nel pannello sia il commento Python dicono "ACCESO di default (misura 25/09: migliora)". Il pezzo di commento "PREPARATO, SPENTO" sembra un residuo di una bozza precedente mai aggiornato — il comportamento vero (visibile nel pannello parametri, scheda 28) è quello acceso.
3. **Due costanti identiche per lo stesso timeout, non condivise.** Il tempo di decadenza dell'armamento della doppia conferma LIVE è **10.000 ms** sia per il Cash out (`MikeCashOutButton.tsx:23`, `MIKE_LIVE_ARM_TIMEOUT_MS`) sia per il Flatten (`MikeMatchCard.tsx:354`, `MIKE_FLATTEN_ARM_TIMEOUT_MS`): due costanti separate con lo stesso valore. Oggi non cambia niente per l'utente, ma se in futuro una delle due venisse cambiata senza cambiare l'altra, i due bottoni avrebbero conferme di durata diversa senza che nessuno l'abbia deciso apposta.
4. **`ko_green_retry_s` resta nel pannello parametri (gruppo "Dal fischio d'inizio") ma non ha più nessun effetto dal 16/09.** L'aiuto sotto il campo lo dice esplicitamente ("SENZA EFFETTO dal 16/09: l'uscita al fischio è una lay appoggiata sul book in paper e in live, non viene più ri-presentata a ritmo"), ma il campo resta modificabile: un trader che lo cambia pensando di regolare qualcosa non ottiene nessun effetto reale.
5. **Una riga di attività senza nessuno dei campi previsti mostrerebbe JSON grezzo.** `mikeActivityLine` (default, `frontend/src/lib/mike.ts:1520-1524`) ricade su `reason`/`err`/`note`/`message`/`msg` del pacchetto ricevuto; se un tipo di evento nuovo del servizio non portasse nessuno di questi campi, la scheda Attività (26) mostrerebbe il JSON grezzo troncato a 140 caratteri invece di una frase italiana — non raggiungibile con i tipi di evento oggi elencati, ma raggiungibile se il servizio ne scrivesse uno nuovo senza aggiornare anche questa mappa.
6. **`activateMike(modalita)` non passa mai `params` all'accensione**, diversamente da Omega (che pretende i parametri correnti prima di accendersi, per non azzerare i tetti di rischio). Ho verificato però che `mike_activate` nel database fa `params = coalesce(p_params, params)`: passare `null` CONSERVA i parametri esistenti, non li azzera — quindi non è un difetto, ma è un'asimmetria di stile fra i due bot che vale la pena segnalare.
7. **Il refuso `mibeParams`** (variabile locale in `pages/ControlRoom.tsx:402`, invece di `mikeParams`): innocuo, solo il nome di una variabile.
8. **`chiusuraUtente.ts` (la funzione condivisa "se chiudo io fuori dall'app il bot deve saperlo") copre esplicitamente Omega e Safe ma NON Mike**, per una scelta dichiarata dell'utente il 16/09 sera. Questo NON vuol dire che Mike sia scoperto su questo fronte: la Costituzione (§15.7-ter) descrive un meccanismo equivalente ma proprio del motore Python di Mike (`service._sorveglia_posizione_di_conto`, attività `posizione_di_conto`/`posizione_di_conto_non_letta` nella scheda 26) — sono due implementazioni diverse per lo stesso problema, non un buco.
9. **`cambiaUscite` per Mike non rilegge i parametri "a fresco" dal database prima di scrivere**, a differenza di Safe (che ha un percorso dedicato, `statoSafeFresco`, introdotto il 18/09 proprio per questo motivo). Usa invece l'ultima copia già in memoria nella pagina. Non ho trovato un caso osservato in cui questo abbia causato un problema su Mike, ma è lo stesso rischio strutturale (due clic ravvicinati che si "mangiano" a vicenda) che è stato corretto solo per Safe.
10. **Il testo alternativo dello Storico ("P&L realizzato = trade REGOLATI nel giorno") non può mai comparire per nessun bot**, Mike compreso: la funzione che dovrebbe scegliere fra le due frasi (`attributionOf`) ignora il parametro e restituisce sempre `'placed'`. Non è specifico di Mike ma la scheda Storico di Mike (27) lo eredita.

---

## Non ho capito / non ho letto

- **`mike_storico_per_modalita_fix_alias_2026-09-14.sql`**: non letto riga per riga. So dal commento della migrazione precedente che corregge un bug di alias SQL (`t` al posto di `o`) nello stesso giorno; non ho confermato se il file che ho letto (`mike_storico_per_modalita_2026-09-14.sql`) contenga già la correzione o se serva applicare anche questo file a parte.
- **Le policy RLS complete e i blocchi di sicurezza** (`sicurezza_db_2026-09-24_BLOCCO_1/2/3`): letti solo a grep mirato su "mike" per confermare che le funzioni e le tabelle di Mike sono nell'elenco delle rilocke/policy generali; non ho letto il testo completo di ogni policy.
- **`hazard_atlas_rpc_scrittura_2026-09-28.sql`**: verificato che non tocca nulla di specifico di Mike (una sola menzione generica "Safe/Omega/Mike/UI" in un commento su un timeout condiviso).
- **`Betfair/mike/engine.py` e `Betfair/mike/service.py`**: fuori dalla mia area per mandato esplicito (altri delegati li leggono in parallelo); dove ho citato un comportamento del motore l'ho sempre attribuito a un commento del codice frontend o della Costituzione, mai verificato di persona riga per riga in Python.
- **`frontend/src/components/trading/EventPnlTable.tsx`, `DailyCalendar.tsx`, `PerformancePanel.tsx`, `DayDetail.tsx`, `EquityCurve.tsx`**: i componenti condivisi sotto `MikeEventPnlTable`/`TradingHistory`/`EquityCard` non sono stati letti riga per riga (sono di Omega/Safe/Mike insieme): ho descritto la scheda 24/25/27 dal loro punto d'uso in Mike, non dal loro codice interno.
- **`components/trading/StatoOrdine.tsx`** (`StatoOrdineCompatto`, usato nella scheda 15): non letto riga per riga, solo dal suo punto d'uso.
- **I test e la certificazione automatica** (`tests/test_mike_certificazione_ui_*.py`, `frontend/src/certification/mike.cert.test.tsx`): non eseguiti né letti (fuori mandato: "non eseguire test").
- **Se `mike_storico_per_modalita_fix_alias_2026-09-14.sql` sia già applicato sul database reale**: non verificabile da codice statico (non ho interrogato il database, per mandato).

