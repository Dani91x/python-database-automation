# BRIEF — PIANO DI IMPLEMENTAZIONE DELLA NUOVA ARCHITETTURA (sessione a crediti API, 08/10/2026)

Autore: coordinatore sul PC (Fable 5.1), su ordine dell'utente. Destinatario: la sessione Claude Code avviata
con la chiave API (budget 200 USD). Lingua: italiano. Regole del repo: `CLAUDE.md`, `BRIEF_STANDARD_DELEGATI.md`.

## 0. L'ordine dell'utente (testuale, e' il metro di tutto)

> «Il codice e' sostanzialmente un casino. Voglio un'architettura vera, fatta da un software engineering vero.
> Se voglio cambiare un componente, al momento devo smontare mezzo software. Dobbiamo rivedere l'intera
> infrastruttura e organizzarla al meglio: tutto il software deve essere organizzato nel miglior modo possibile per
> ottimizzare le risorse e per fare aggiunte o cambi di componenti nel minor tempo possibile. L'app desktop deve
> essere identica a quella dei competitor nel ricevere i dati e comunicare con Betfair.»
> «Il software ha molti moduli e funzionalita': non voglio perderne nessuna. Voglio che sia ottimizzato al meglio
> e, dove possibile, ridurre le righe di codice. La domanda per ogni componente, scandagliando ogni riga e
> risalendo a tutte le funzionalita', e': come possiamo fargli fare la stessa identica cosa con l'80% di righe in meno?»
> «Tutto quello che scrivi deve essere basato sul codice, sui dati e sulla struttura attuale. L'idea e':
> STRUTTURA ATTUALE → STRUTTURA MIGLIORE POSSIBILE OTTIMIZZATA. Priorita' al millisecondo per tutto cio' che
> riguarda Betfair → parita' 1:1 con i competitor.»
> «Questi soldi servono SOLO a scrivere il piano di implementazione, talmente dettagliato che non possiamo sbagliare.»

Conseguenze vincolanti:
- **Niente codice di produzione in questa sessione.** Si producono documenti, inventari, misure, prototipi di
  misura usa-e-getta (in `ARCHITETTURA_2026-10/strumenti/`, mai importati dall'app). Nessuna modifica fuori da
  `ARCHITETTURA_2026-10/`. Nessuna scrittura sul DB (letture in sola lettura ammesse per le misure).
- **Ogni affermazione cita la fonte**: `file:riga`, numero misurato, tabella del DB, documento del competitor.
  Un'affermazione senza fonte non entra nel piano. «Credo», «probabilmente», «di solito» sono vietati.
- **Nessuna funzionalita' persa**: il piano parte dall'inventario COMPLETO di cio' che il software fa oggi;
  ogni funzionalita' ha una riga nel piano con «dove vive oggi → dove vivra' → test di parita'».
- **Il guscio**: la nuova architettura nasce accanto all'app attuale, che resta in produzione; un componente
  nuovo sostituisce il vecchio SOLO con parita' dimostrata (stessi dati, stesse decisioni, stessi ordini, replay
  identici sul banco). Zero regressioni per costruzione.

## 1. Il software com'e' oggi (misurato dal coordinatore l'08/10, `git ls-files` + `wc -l`; rifare e confermare)

| Parte | Righe | Note |
|---|---|---|
| Backend Python, codice (no test, no tools) | 271.857 in 256 file | `Betfair/` + radice |
| di cui `Betfair/stream/` | 88.987 | runner calcio, ordini, scalper 21.620, tennis_live 11.638, tennis_scalper 8.943, backtest 13.391, trading 4.301 |
| di cui `Betfair/omega/` | 37.500 | `omega_service.py` 8.936 |
| di cui `Betfair/safe_strategy/` | 34.635 | `bot_service.py` 11.136, `service.py` 3.444, `execution.py` 3.093, `engine.py` 2.254 |
| di cui `Betfair/mike/` | 17.755 | `service.py` 7.551, `engine.py` 5.359 |
| di cui radice `Betfair/*.py` | 7.358 | `money_management.py` 3.397, `betfair_report_manager.py` 1.737, `client.py`, `order_exec.py`, `order_worker.py`, `refresh_worker.py`, `odds_refresh.py` |
| Test Python | 163.079 | |
| Strumenti e replay (`tools/`, `*/tools/`) | 35.486 | |
| Frontend `frontend/src` codice | 133.686 | `replayBotCatalogo.ts` 11.099 (GENERATO), `useControlRoom.ts` 4.322, `LadderView.tsx` 2.984, `mike.ts` 2.454, `safeBot.ts` 2.256, `ControlRoom.tsx` 1.740, `safeStrategy.ts` 1.731, `SafeStrategy.tsx` 1.705, `omega.ts` 1.655, `interruttori.ts` 1.533, `SeguiLive.tsx` 1.372 |
| Test frontend | 73.428 | |
| Desktop (Electron) | 1.183 | `desktop/main.js` avvia i processi sotto watchdog |
| SQL migrazioni | 33.835 | 55 tabelle usate dal codice |

Indizi di duplicazione (da `grep` sui `def`): `read_book` definita 17 volte, `process_market_book` 15,
`_now_iso` 17, `log` 18. Accesso al DB: 5 moduli diversi, uno per bot (`stream/db.py` 53 chiamate `.table(`,
`safe_strategy/bot_db.py` 46, `omega/omega_db.py` 44, `tennis_live/tennis_db.py` 39, `mike/db.py` 32) piu'
chiamate sparse in `scalper_session.py` 20, `live_order_worker.py` 18, `scalper_service.py` 16, `safe_strategy/db.py` 12.
Carico misurato il 02/10 (`SCHEMI_BOT/sistema/MISURE_2026-10-02.md`): 1.400 richieste/min a Supabase con il solo
Mike acceso su 2 partite (~2 M/giorno), Mike 269/min, Safe 255/min pur fermo.
Cartelle di radice da inventariare (vive / morte / da archiviare): `Ai Engine/`, `Telegram bot/`, `laboratorio/`,
`market_intelligence/`, `tactical_engine/`, `value_engine/`, `Prediction/`, `football_data_scraper/`,
`_validazione_*`, `_checkpoint_*`, `_banco_alms_f3/`, `36006953/`, `sql/`, `docs/`.

Documenti da leggere PRIMA (puntatori, non copie):
- `PIANO_OTTIMIZZAZIONE_GLOBALE_2026-10-02.md` (fasi 0-1-2 gia' decise dall'utente: monitoraggio «Salute»,
  blocchi con memoria propria + DB archivio, indurimento h24) e `SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md`,
  `ARCHITETTURA_ATTUALE.html`, `MISURE_2026-10-02.md`: NON ripartire da zero, questo piano li assorbe.
- `PROCESSO_STANDARD_BOT.md` (§6 copertura del banco, §7 catalogo dei 35 errori), `ESECUZIONE_LIVE.md`,
  `HANDOFF_CONTROL_ROOM.md`, `PROGETTO_PAPER_VIA_FLUMINE_2026-09-16.md`.
- Le costituzioni dei bot: `Betfair/mike/COSTITUZIONE_MIKE.md`, `Betfair/safe_strategy/COSTITUZIONE_SAFE_STRATEGY.md`,
  `Betfair/omega/COSTITUZIONE_OMEGA.md`, `Betfair/stream/scalper/BIBBIA_SCALPER_CALCIO.md`,
  `Betfair/stream/scalper/SPEC_MEDIA_UNDER_2026-10-05.md`, `TENNIS_BOT_DOSSIER.md`, `SPEC_STRATEGIA_S.md`.
- Il metodo del guscio gia' usato per la grafica: `AUDIT_2026-10-01/REDESIGN/{INVENTARIO_FUNZIONALITA,PIANO_INTEGRAZIONE,REFERTO_CLOUD_2}.md`.
- Avvio e processi: `desktop/main.js`, `Betfair/stream/avvio_app.py`, `Betfair/stream/config_stream.py`,
  canali locali `Betfair/stream/{canale_bot,ladder_canale,esiti_ordini_canale,sveglia_canale}.py`,
  `Betfair/stream/tennis_live/canale_bot_tennis.py`, `Betfair/stream/scores/scan_feed.py`.
- Banco comune: `Betfair/stream/backtest/{banco_comune,certifica,registro_bot,applica_bot,varianti_bot}.py`.
- `CRONOSTORIA.md`: ultime 3 sezioni (05-08/10) per lo stato e i cantieri in corso nel cloud
  (`AUDIT_2026-10-08/SPECIFICHE_CANTIERI_CLOUD_2026-10-08.md`): il piano NON deve contraddirli.

## 2. Il metodo: STRUTTURA ATTUALE → STRUTTURA OTTIMIZZATA, componente per componente

Per OGNI componente (elenco iniziale in §3, da completare con l'inventario) si produce una scheda con sette
sezioni, sempre le stesse, nello stesso ordine:

1. **Oggi**: file e righe (`wc -l`), responsabilita' reali lette dal codice (non dai nomi), dipendenze in
   entrata e in uscita (`import`, tabelle del DB lette/scritte con la frequenza misurata, canali locali, processi),
   stato condiviso, orologi, thread.
2. **Funzionalita'** (TUTTE): elenco numerato di cio' che il componente fa per l'utente o per gli altri componenti,
   ricavato riga per riga e dalla UI (pannelli, pulsanti, parametri editabili, allarmi, attivita' scritte). Ogni
   voce con `file:riga`. E' l'inventario che garantisce «nessuna funzionalita' persa».
3. **Difetti strutturali**: duplicazioni (con le righe gemelle negli altri bot), accoppiamenti, lavoro
   ripetuto, attese di rete nel percorso critico, dati copiati, stato in piu' posti.
4. **Domani**: dove vive la funzionalita' nella struttura nuova (§4), con il contratto (interfaccia, tipi, eventi)
   che espone e che consuma. Stima delle righe DOPO e come si arriva al -80%: cosa diventa condiviso, cosa
   sparisce perche' ripetuto, cosa resta perche' e' strategia (la logica di trading NON si semplifica a
   costo di cambiarla: resta identica, al piu' si sposta).
5. **Parita'**: il test o il replay che dimostra «stessa identica cosa»: quale registrazione, quali scenari
   del banco, quali numeri devono coincidere (decisioni, ordini, importi, istanti, P&L), quali fotografie
   della UI. Senza questa sezione la scheda non e' completa.
6. **Migrazione**: i passi per sostituire il vecchio col nuovo nel guscio (interruttore, periodo in parallelo
   «ombra» con confronto automatico, taglio del vecchio), l'ordine rispetto agli altri componenti, i rischi, il
   modo di tornare indietro.
7. **Misure**: numeri prima (oggi) e obiettivo dopo: latenza, richieste al DB al minuto, memoria, CPU, righe.

La domanda guida di ogni scheda e' quella dell'utente: «come fargli fare la stessa identica cosa con l'80% di
righe in meno?». La risposta deve venire dal codice: dove sono le copie, cosa si puo' generare, cosa si puo'
derivare da un contratto, cosa e' gia' in una libreria matura (flumine, betfairlightweight) e oggi e' riscritto.

## 3. I componenti da scandagliare (elenco di partenza, da completare con l'inventario)

A. **Connessione Betfair e cache dei mercati** (`Betfair/client.py`, `Betfair/stream/runner.py`,
   `Betfair/stream/tennis_live/tennis_runner.py`, `tennis_recorder.py`, `mercati_registrati.py`,
   `config_stream.py`, i canali locali; lo scanner `Betfair/stream/scores/scan_feed.py` e il feed unico
   `safe_strategy_scan` che alimenta Mike/Safe/Omega).
B. **Punteggi e stato partita** (IPS, `scores/`, `atlante_v4`, curatore `curator.py`, timeline, ritardi 2-3 s).
C. **Porta degli ordini e riconciliazione** (`Betfair/stream/motore_ordini.py`, `live_order_worker.py`,
   `order_exec.py`, `order_worker.py`, `trading/submin.py`, `live_order_build.py`, specchio `betfair_live_orders`,
   place-and-trim, minimi `.it`, persistenza, bet delay, rifiuti).
D. **Runtime dei bot e contratto** (oggi: 5 servizi monolitici; `registro_bot.py` del banco e' gia' un
   registro: il contratto parte da li').
E. **Strategie**: Mike, Omega, Safe (base/esatto/punta), scalper calcio (maker/sniper/media under),
   tennis (pro/FLB/swing/scalper/safe_tennis): logica da mantenere IDENTICA; schede separate per il loro
   «guscio» (ingressi: book, punteggio, parametri; uscite: decisioni e ordini).
F. **Money management e regolamento** (`money_management.py`, `betfair_report_manager.py`, `regolato_conto.py`,
   P&L reale del conto, giornata operativa).
G. **Dati**: i 5 moduli DB, le 55 tabelle, le RPC, le migrazioni; stato vivo vs archivio vs statistiche;
   proposta SQLite locale (WAL) + postino verso il cloud con coda e ripresa; cosa resta SOLO nel cloud.
H. **Banco di certificazione e replay** (`backtest/`, i `tools/replay_registrazioni.py` per bot, `certifica`,
   `applica_bot`, replay professionale, Replay Tennis, strumento della barra): oggi 5 adattatori per bot;
   il banco va unificato sul contratto D.
I. **Desktop e processi** (`desktop/main.js`, watchdog, `avvio_app.py`, worker del backtest, runner, scanner,
   bot: quanti processi, chi parla con chi, cosa succede a un crash, giorno nuovo, h24).
J. **Frontend**: modello di stato per bot (oggi `mike.ts`, `safeBot.ts`, `omega.ts`, ...), Control Room,
   ladder, Segui live, replay; cosa puo' essere generato dal contratto D; API locale vs RPC Supabase.
K. **Cartelle di radice e codice morto**: inventario vive/morte/archivio con prova (chi le importa, ultimo commit).

## 4. L'architettura obiettivo (ipotesi del coordinatore, DA VERIFICARE e correggere con le schede)

- **Nucleo Betfair in-process, priorita' al millisecondo**: una sola connessione stream per sport (calcio e tennis
  con lo stesso codice, sport come parametro), cache dei mercati in memoria (il `MarketBook` di
  betfairlightweight/flumine, senza copie), orologio di mercato, ladder servito ai consumatori locali senza
  rete, porta unica degli ordini con riconciliazione locale e specchio; stato vivo in SQLite locale (WAL);
  nessuna chiamata di rete fra il messaggio di Betfair e la decisione del bot.
- **Runtime dei bot a plugin** con contratto unico (`osserva(book, stato_partita, orologio) → decisioni`,
  `ordini`, `stato`, `parametri`, `attivita'`), un solo ciclo di vita (pre-match, in gioco, intervallo,
  regolamento), un solo meccanismo di persistenza e riavvio, un solo registro; le 5 copie di servizio/engine/db/
  certificazione diventano una.
- **Dati**: strato unico; locale per lo stato vivo; «postino» asincrono verso Supabase per archivio, statistiche,
  visibilita' remota; il cloud fuori dal percorso critico; le tabelle storiche (quote, eventi, formazioni: 45 GB
  oggi) servite dal cloud per il modello di Mike e le statistiche.
- **UI**: un modello di stato unico per tutti i bot, pannelli e parametri generati dal contratto, Control Room
  e ladder che leggono dal nucleo locale (canale locale esistente), RPC Supabase solo per archivio e replay.
- **Banco**: un adattatore solo, sul contratto; `certifica`/`applica_bot`/replay professionale invariati per l'utente.
- **Processi**: pochi, con supervisore, memoria propria, riavvio senza perdita (h24).

## 5. Parita' 1:1 con i competitor (Bet Angel, Geeks Toy, Fairbot, Cymatic Trader, Bfexplorer, Traderline)

Ricerca su FONTI PUBBLICHE (manuali, documentazione, forum ufficiali, changelog), citate una per una; nessuna
deduzione presentata come fatto. Per ciascun competitor una scheda: architettura desktop (processi, stream,
cache), latenze dichiarate, gestione ordini (one-click, fill-or-kill, tick offset, stop, greening, dutching),
ladder e grafici, bot a regole/automazione, registrazione e replay, storico locale, gestione di rete e
riconnessione, risorse (CPU/RAM dichiarate). Poi la **tabella di parita'**: funzionalita' competitor → c'e' da
noi? dove? → misura nostra vs loro (quando dichiarata) → gap → dove si chiude nel piano. Priorita': tutto cio'
che tocca il percorso Betfair → ladder → ordine, in millisecondi. Misurare le nostre latenze OGGI con strumenti
usa-e-getta sulle registrazioni e, in sola lettura, sui log dell'app (eta' del feed, tempo messaggio → ladder,
tempo decisione → `placeOrders` → risposta): numeri, non aggettivi.

## 6. Consegne (tutte in `ARCHITETTURA_2026-10/`, commit per tappa sul ramo, mai push forzato)

1. `00_INVENTARIO.md` — mappa completa di oggi: ogni modulo (righe, responsabilita', dipendenze, tabelle,
   frequenze), ogni processo, ogni canale, ogni tabella (chi legge, chi scrive, quanto), ogni pagina/pannello
   della UI con le funzionalita' che espone, le cartelle di radice (vive/morte). Generato il piu' possibile da
   strumenti (script in `strumenti/`, rieseguibili) cosi' e' verificabile.
2. `01_FUNZIONALITA.md` — l'elenco numerato di TUTTE le funzionalita' del software (backend e UI), ognuna con
   `file:riga` di oggi. E' la lista contro cui si misura «nessuna persa».
3. `02_COMPETITOR.md` — le schede dei competitor con le fonti e la tabella di parita' (§5), con le nostre misure.
4. `03_SCHEDE_COMPONENTI/` — una scheda per componente (§2, sette sezioni), A…K piu' quelle emerse.
5. `04_ARCHITETTURA_OBIETTIVO.md` — la struttura nuova: componenti, contratti (interfacce con tipi), flussi
   (stream → cache → bot → ordini → specchio → UI), processi, dati (locale/cloud), con schemi (archify o
   mermaid) e le motivazioni, ognuna ancorata alle schede.
6. `05_PIANO_DI_MIGRAZIONE.md` — l'ordine dei passi (tappe piccole, ognuna con parita', interruttore e ritorno
   indietro), le dipendenze fra tappe, le stime (righe toccate, giorni), i rischi e le mitigazioni, cosa fa il
   cloud e cosa il PC, i replay di riferimento da congelare PRIMA di iniziare, i criteri di «fatto» di ogni tappa.
   Prima tappa consigliata: fase 0 del piano del 02/10 (monitoraggio «Salute») + congelamento dei riferimenti.
7. `06_RIEPILOGO_PER_L_UTENTE.md` — 2 pagine per un non tecnico: cosa cambia, cosa resta, quanto ci vuole,
   quali decisioni servono da lui (elenco esplicito).

## 7. Budget e modo di lavorare (200 USD)

- Controllare `/cost` a ogni tappa e scriverlo in `ARCHITETTURA_2026-10/COSTI.md` (tappa → USD).
  Ordine di spesa: inventario con strumenti (poco), schede con delegati **Sonnet** in parallelo per componente
  (modello economico, compiti circoscritti, file da leggere indicati), ricerca competitor con Sonnet; sintesi
  (`04`, `05`) con **Opus**. Se il budget si avvicina a 150 USD: fermarsi, committare, scrivere il punto di
  ripresa in `CRONOSTORIA.md` e avvisare l'utente.
- Delegati: brief con obiettivo, file da leggere, perimetro, formato della scheda, «cita file:riga», «niente
  codice», «riporta cio' che non hai potuto verificare». Il coordinatore della sessione rilegge ogni scheda
  contro il codice prima di accettarla (campione: 3 affermazioni a caso per scheda, verificate a mano).
- Git: lavorare sul ramo `claude/eloquent-franklin-g2nyk5`, SOLO dentro `ARCHITETTURA_2026-10/` e un blocco
  proprio in `CRONOSTORIA.md`; `git fetch` + merge prima di ogni commit; mai `git add -A`; mai rebase.
- Fine: in `CRONOSTORIA.md` il blocco «PIANO DI ARCHITETTURA: PRONTO PER LA REVISIONE» con l'elenco delle
  consegne e le domande aperte per l'utente. Il PC (coordinatore Fable) verifica le schede contro il codice e
  i numeri prima che l'utente decida.

## 8. Cosa NON fare

- Non toccare codice di produzione, test, migrazioni, `.env`, `frontend/`, `desktop/`.
- Non proporre di «riscrivere tutto»: il guscio sostituisce un componente alla volta con parita'.
- Non semplificare una strategia per ridurre righe: la logica di trading e' intoccabile; si riducono gli
  strati attorno (servizio, DB, UI, banco), non le regole.
- Non affermare nulla sui competitor senza fonte pubblica citata.
- Non inventare numeri: ogni misura ha lo strumento che l'ha prodotta, rieseguibile.

## 9. AGGIUNTA DELL'UTENTE (08/10, dopo la prima versione) — vincoli espliciti, testuali

> «Il tutto deve essere organizzato nel miglior modo possibile: facile da editare, cambiare, sostituire; scritto
> chiaramente ogni cosa e cosa fa. Il nostro database cloud alimenta vari algoritmi: quelli ovviamente devono
> restare. Tutto quello che riguarda Betfair deve essere al millisecondo come i competitor. Non voglio un lavoro
> superficiale. Controlla con occhio critico: non fidarti del coordinatore, fidati solo del codice. Se serve un
> SQLite per avere tutto al millisecondo, facciamolo; altrimenti cercate la soluzione ingegneristica migliore in
> assoluto. L'app deve stare accesa h24 e monitorare costantemente sia calcio che tennis. Il database cloud resta
> l'archivio generale.»

Come si applica, punto per punto:

1. **Organizzazione editabile/sostituibile**: ogni componente della struttura nuova ha UNA cartella, UN contratto
   scritto (interfaccia con tipi), UN documento `COSA_FA.md` in testa (scopo, entrate, uscite, dipendenze,
   come si sostituisce, come si prova da solo). Il criterio di accettazione del piano: «per sostituire X tocco
   solo la cartella di X e i suoi test di contratto». Ogni scheda di §2 deve dimostrarlo per il suo componente
   (sezione 4: elenco dei file che si toccano per sostituirlo DOMANI vs OGGI).
2. **Gli algoritmi alimentati dal DB cloud RESTANO**: inventariarli uno per uno con `file:riga`, tabelle lette,
   frequenza e latenza tollerata. Punti di partenza noti (da verificare e completare): modello di Mike
   (`Betfair/mike/dossier.py`: lambda/rho dalle fixture, tabella empirica HT→FT per lega, `ht_ft_transitions`),
   cache empiriche di Omega (`omega_service.py` `_EMPIRICAL_CACHE`/`_MINUTE_CACHE`, `omega_minute_transitions*`),
   segnali e previsioni (`analytics_signals`, `fixture_predictions`, `Prediction/`), statistiche di contorno
   (`standings`, `injuries`, `top_scorers`, `top_cards`, `match_*`), lo scanner `safe_strategy_scan`, il P&L
   reale del conto (`regolato_conto.py`, `betfair_report_manager.py`), lo storico delle giornate. Per ciascuno
   il piano dice: resta sul cloud (letto quando, con che cache locale) / si replica in locale / si precalcola.
   Nessuno di questi si perde o si degrada.
3. **Millisecondo su Betfair, come i competitor**: il percorso stream → cache → decisione → ordine → specchio
   → ladder non attraversa MAI la rete verso il DB. Misurare oggi e fissare obiettivi numerici per tappa.
   Se lo stato vivo richiede un archivio locale, la scelta (SQLite WAL, memoria + log append-only, altro) va
   motivata con numeri (latenza di scrittura, durabilita' al crash, dimensione) e confrontata con cio' che i
   competitor dichiarano. «La soluzione ingegneristica migliore in assoluto» = quella che vince il confronto
   misurato, non quella piu' nota.
4. **h24, calcio e tennis insieme**: il piano include il ciclo della giornata (cambio di giorno, regolamento
   notturno, riconciliazione), la supervisione dei processi (crash, riavvio senza perdita di stato, memoria
   che non cresce), la rete (riconnessione dello stream, sessione Betfair che scade, keep-alive), i limiti
   dell'API Betfair (connessioni, richieste/secondo, mercati per stream), e le misure di risorse per 24 ore
   (CPU, RAM, richieste al cloud/giorno) con obiettivi. Fase 2 del piano del 02/10: assorbirla e dettagliarla.
5. **Il DB cloud e' l'archivio generale**: tutto cio' che oggi vi finisce continua a finirci (nessuna tabella
   persa), ma via postino asincrono con coda, ripresa dopo rete assente, e idempotenza; le letture nel percorso
   critico spariscono. Il piano elenca tabella per tabella: chi scrive oggi → chi scrivera' → ritardo massimo
   accettato → come si verifica che «non manca nulla» (conteggi, controllo notturno).
6. **Occhio critico**: le ipotesi di §4 sono del coordinatore PC e NON sono vincolanti; se il codice o le misure
   dicono altro, il piano lo scrive e propone la soluzione migliore con le prove. Ogni scheda termina con
   «cosa ho verificato di persona / cosa non ho potuto verificare».
7. **Non superficiale**: una scheda senza l'elenco completo delle funzionalita' con `file:riga`, senza i numeri,
   senza il test di parita' e senza la stima delle righe non e' accettata; il coordinatore della sessione la
   rimanda al delegato. Meglio 5 schede complete che 11 superficiali: se il budget non basta, si consegna
   l'inventario completo (00, 01), i competitor (02) e le schede fatte, con l'elenco di quelle mancanti e il
   punto di ripresa.
