# Mike - Capitolo 13a: la pagina di Mike, cosa vedi e cosa premi (schede)

Schema: `13a_pagina_di_mike.html` (sorgente `13a_pagina_di_mike.workflow.json`).
Seconda parte del capitolo: `13b_control_room.html` e `13b_control_room.schede.md` (Mike nella
Control Room).
Fonte dei fatti: `SCHEMI_BOT/mike/inventario/E_schermate_e_pulsanti.md` (schede E-n). La durata di
una firma (120 secondi) viene dal capitolo 6 (`06_uscite_manuali_e_automatiche.schede.md`).

**Schede dell'inventario E usate in questo file (numeri):** 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 28-bis (tabella dei parametri), 40,
41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52; piu' «Cose NON visibili», «Glossario», «Differenze
dalla Costituzione», «Cose strane», «Non ho capito / non ho letto».
Le schede 29-39 sono nel file `13b_control_room.schede.md`. Conto completo in coda.

Come si legge: ogni riquadro dello schema ha un numero (01-12) scritto in alto. La scheda con lo
stesso numero lo spiega. Le parole fra «» sono i testi che leggi nell'app.

**La regola di tutto il capitolo: l'app scrive, Mike legge al giro dopo.** Nessun pulsante parla
direttamente con Betfair. Ogni pulsante scrive una riga nel database; Mike la legge al suo giro
successivo (di solito entro 2 secondi) e fa lui l'ordine. Poi lo schermo si riaggiorna da solo.

**Paper o live in questo capitolo:** ogni partita porta la SUA modalita', fissata quando Mike la
arma. I pulsanti di una scheda partita usano la modalita' della partita, mai quella del toggle in
alto. I conti della pagina mostrano solo la modalita' con cui Mike gira adesso: paper e live non si
sommano mai.

---

## 01 - Pagina di Mike («testata, caselle»)

**Cosa fa**
- Dal menu «Scegli sport» premi la scheda «🎯 Mike» (sottotitolo «Under 3.5 / Over 4.5 · green-up e
  cash-out · paper-first», colore verde acqua). Si apre la pagina di Mike. Senza accesso con la tua
  utenza la pagina non si apre.
- In cima c'e' una riga fissa (resta visibile quando scorri). Da sinistra: «AI TERMINAL» (torna alla
  scelta sport), «🎯 MIKE», l'etichetta di stato del bot, la salute del servizio, l'etichetta «canale
  locale», il pulsante «Storico calcio», l'interruttore PAPER/LIVE (riquadro 02), «Parametri»
  (riquadro 03), «Avvia»/«Ferma» (riquadro 05).
- Etichetta di stato del bot, una di queste: «BOT INATTIVO» (mai avviato), «BOT IN CORSA», «BOT IN
  ARRESTO», «BOT FERMO», «BOT ERRORE». Se il bot e' «IN CORSA» ma non da' segni di vita da piu' di
  45 secondi diventa rossa: «BOT IN CORSA · SENZA BATTITO» con «il servizio non batte da {tempo}:
  riavvia l'app desktop» (oppure «il servizio non ha mai battuto da quando e' stato avviato»).
- Salute del servizio, due parti separate:
  - lo scanner (il programma comune che legge tutte le partite): «feed vivo (N s)» verde se
    aggiornato entro 45 secondi; altrimenti «feed FERMO da {tempo}» rosso, o «feed: nessun dato».
    Se vivo, accanto: quante partite in gioco di calcio ⚽ e di tennis 🎾;
  - Mike: «servizio Mike vivo (N s)» verde, oppure «servizio Mike: nessun battito da {tempo} —
    riavvia l'app desktop» rosso.
  - «⚡ STREAM {n}» verde se le quote arrivano in diretta; «REST» ambra se arrivano dalla lettura di
    ripiego; «DRY» ambra se Mike sta solo guardando senza fare ordini.
  - Se lo scanner e' fermo compare la riga «— il feed dello scanner e' fermo da {tempo}: riavvia
    l'app desktop».
- «canale locale» (verde): compare SOLO quando l'app desktop riceve i dati direttamente dal bot sul
  PC, senza passare dal database. Se il collegamento cade, l'etichetta sparisce e la pagina torna a
  leggere dal database: nessun dato sparisce, e' solo un po' piu' vecchio.
- Sotto la riga fissa, un riquadro colorato dice la modalita' (riquadro 02) ed eventuali errori:
  «⚠ {messaggio}» se il servizio ha un errore; «tabelle Mike assenti: applica migrations/mike_bot.sql»
  se il database non ha ancora le tabelle di Mike.
- **Barra della giornata**: data della giornata (ora di Roma), P&L realizzato oggi (grande, verde o
  rosso), «partite», «operazioni» (conta i giri completi: apertura piu' le sue chiusure, non le
  singole righe), «V»/«P» (vinte, perse), «vive» se ci sono partite in gioco, «Liability aperta»,
  «P&L bloccato», «totale storico». Mike non ha un obiettivo di giornata: niente barra di
  avanzamento, niente «CENTRATO».
- **Le 7 caselle**, ognuna con un numero grande e una riga sotto:
  1. «Partite seguite ora»: sotto «N prima del fischio · N in gioco · N con posizione aperta».
  2. «Posizioni aperte»: giri con soldi ancora esposti; sotto «N in verifica su Betfair» (fucsia)
     oppure «cicli con capitale ancora esposto».
  3. «P&L oggi»: verde, rosso o grigio; sotto «STOP giornaliero ATTIVO · solo chiusure» (rosa) se lo
     stop e' scattato, altrimenti la data e la soglia («stop a −50,00 €»).
  4. «P&L totale»: da sempre, stessa modalita'.
  5. «Liability aperta» (arancione): la perdita peggiore possibile sulle posizioni aperte. Sotto:
     «perdita peggiore sulle posizioni aperte, netta dal servizio», oppure in ambra «stimata dalle
     righe (servizio da riavviare)»; piu' «· di cui N in verifica» e «· dato stantio» se il battito
     di Mike e' piu' vecchio di 60 secondi.
  6. «P&L bloccato»: «—» se nessuna partita ha ancora un risultato garantito; altrimenti la cifra e
     «gia' bloccato su N partita/e · N ancora da decidere».
  7. «Ultimo ciclo»: ora dell'ultimo giro di Mike (ore:minuti:secondi); sotto in rosso «servizio
     senza battito: riavvia l'app desktop» oltre 45 secondi, altrimenti «feed aggiornato N s fa».
  Al primo caricamento le caselle sono rettangoli grigi che pulsano.
- **Le sei linguette** (restano in cima quando scorri): «⚽ Partite (N)», «📋 Operazioni (N)», «⏱
  Risultati Pre-Match (N)», «🔴 Risultati Live (N)», «🧾 Attivita'», «📅 Storico». Cambiare
  linguetta non rilegge nulla: i dati sono gia' in memoria.
- **Linguetta Partite**: tre sezioni sempre nello stesso ordine, anche vuote:
  - «⏱ PRE-MATCH (N)»: partite non ancora iniziate, ordinate per ora del fischio;
  - «🔴 LIVE (N)»: partite in gioco. Una partita entra qui al fischio e non torna mai in Pre-match,
    anche se il feed ha un buco;
  - «⚠️ DA SISTEMARE (N)»: solo se ci sono partite in errore o saltate, con «partite in errore o
    saltate: serve una mano».
  - Due pulsanti-filtro «⏱ Pre-match» e «🔴 Live» nascondono una sezione (il conteggio resta
    scritto). La scelta resta salvata nel browser. L'ultima sezione visibile non si nasconde.
  - Nessuna partita: «Nessuna partita seguita. Con il bot in corsa, le partite con calcio d'inizio
    entro {N} ore e le linee 3.5/4.5 nel feed compaiono qui.» (N = parametro «ore prima del
    fischio», di serie 1).
- **Linguetta Attivita'**: tutto quello che Mike ha fatto, una riga per fatto, con l'ora al secondo,
  un'etichetta colorata per tipo (rossa per le righe gravi: ordine in verifica, linea assente nel
  feed, flusso prezzi interrotto) e una frase in italiano. Oltre 30 tipi di fatti. Filtrabile per
  partita.

**Quando**
- Sempre visibile. Si riaggiorna da sola: a ogni novita' nel database (piu' novita' vicine = una sola
  rilettura, entro 1,5 secondi) e comunque ogni 15 secondi. Un battito che cambia solo l'ora non fa
  rileggere nulla.

**Numeri**
- Battito di Mike considerato morto: 45 secondi. Scanner fermo: 45 secondi. Liability «stantia»:
  60 secondi.
- Rilettura di sicurezza: ogni 15 secondi. Raggruppamento delle novita': 1,5 secondi.
- Tetti di cio' che la pagina riceve: 200 partite (non chiuse, piu' quelle chiuse nelle ultime 24
  ore), 500 righe di ordini, 400 righe di Attivita', 50 richieste.

**Esempio con le cifre**
- Barra della giornata: «giovedi' 10 settembre 2026 (Europe/Rome) · +12,50 € · partite 4 ·
  operazioni 9 · 6V 2P · Liability aperta 3,40 € · P&L bloccato +0,80 € · totale storico
  +140,20 €».
- Mike avviato ma bloccato da 2 minuti: etichetta rossa «BOT IN CORSA · SENZA BATTITO (2 min)» e la
  salute ripete «servizio Mike: nessun battito da 2 min — riavvia l'app desktop».
- «Posizioni aperte: 5 · 2 in verifica su Betfair»: due ordini hanno un esito ancora ignoto.
- 6 partite seguite, 4 da iniziare e 2 in corso: «⏱ PRE-MATCH (4)» e «🔴 LIVE (2)».
- Attivita': «Inter - Milan · ciclo 1 chiuso: 1,50 → 1,48 · P&L bloccato +0,14 €».

**Cosa vedi nell'app**
- Tutto quanto sopra, dall'alto in basso: riga fissa, riquadro della modalita', barra della
  giornata, 7 caselle, linguette.

**Se qualcosa va storto**
- Rete o database giu': la pagina resta con gli ultimi dati letti; l'etichetta «canale locale», se
  c'e', continua a portare quote e stato dal PC. La salute diventa rossa quando i dati invecchiano
  oltre 45 secondi.
- L'avviso «senza battito» compare DUE volte nella stessa riga (etichetta e salute): e' voluto
  (vedi «Punti da decidere» n. 17).
- Paper o live: tutti i numeri della barra, delle caselle e delle linguette sono della sola
  modalita' con cui Mike gira ora.

**Per il tecnico**
- E-1 `pages/SelectSport.tsx:72-79`, `App.tsx:26,190-195` (`ProtectedRoute`).
- E-2 `components/trading/BotHeader.tsx:43-193` (`botStatusWithBeat`), `ServiceHealthChip.tsx`,
  `pages/Mike.tsx:377-424`; `SERVICE_STALE_S`=45, `SCANNER_STALE_MS`=45000; socket
  `ws://127.0.0.1:47333`.
- E-4 (banner) `ModeBanner.tsx`, `pages/Mike.tsx:428-475`.
- E-5 `DayBar.tsx`, `pages/Mike.tsx:482-496`; E-6 `StatTile.tsx`, `pages/Mike.tsx:498-565`.
- E-7 `pages/Mike.tsx:567-584`; E-8 `pages/Mike.tsx:586-651`,
  `lib/mike.ts::splitMikeEvents,needsAttention,isEventLive,sortEvents` (665-728), `SectionFilter.tsx`.
- E-26 `ActivityFeed.tsx`, `pages/Mike.tsx:722-740`,
  `lib/mike.ts::mikeActivityLine,MIKE_ACTIVITY_KINDS,MIKE_ACTIVITY_EXTRA` (1185-1300).
- E-43 tabella `mike_activity` (`migrations/mike_bot.sql:124-134`).
- E-48 `get_mike_state()` (`migrations/mike_bot_v2.sql:149-196`): tetti 200/500/400/50.

---

## 02 - Paper o live («live: conferma»)

**Cosa fa**
- Due pulsanti affiancati: «PAPER» (verde quando attivo) e «LIVE» (rosso quando attivo).
- Premi LIVE: si apre la finestra «Passare a LIVE (soldi veri)?» con «Da questo momento gli ordini
  del bot Mike usano denaro reale.», l'avviso arancione «La struttura Under 3.5 / Over 4.5 perde con
  esattamente 4 gol: il live va attivato solo dopo il GO della certificazione paper (Costituzione
  §0).», e i pulsanti «Annulla» e «Si', passa a LIVE» (rosso).
- Confermi: l'app scrive la nuova modalita' (lascia intatti tutti i parametri), chiude la finestra e
  mostra l'avviso rosso «🔴 MODALITA' LIVE — soldi veri».
- Premi PAPER: passa subito, nessuna domanda, nessun avviso.
- Sotto la riga fissa, il riquadro della modalita': rosso «MODALITA' LIVE — il bot piazza ordini con
  soldi veri.» oppure verde «MODALITA' PAPER — simulazione fedele: fill solo al prezzo ancora
  disponibile, betDelay in-play, protezioni identiche al live.»; con Mike che solo guarda, «DRY:
  nessun ordine (osservazione)».
- Due avvisi in piu', solo per Mike:
  1. rosso «⚠️ N partita/e sta/stanno operando in PAPER/LIVE»: ci sono partite ancora vive armate
     nell'ALTRA modalita'. Se Mike ora e' in paper ma ci sono partite armate in live, l'avviso dice
     «con soldi veri, anche se il bot adesso e' in paper» e invita a chiuderle a mano dalle loro
     schede;
  2. ambra «Modalita' LIVE, ma il processo NON e' abilitato a piazzare ordini reali.»: la pagina e'
     in LIVE ma l'interruttore di sicurezza nel file di impostazioni del PC (`.env`) e' spento. Mike
     calcola tutto ma blocca ogni ordine prima che parta.

**Quando**
- Al clic sul pulsante. La modalita' si puo' cambiare a bot acceso o spento.
- La modalita' di una partita si fissa quando Mike la arma. Cambiare il toggle NON cambia le partite
  gia' armate: cambia solo le partite armate da li' in poi.

**Numeri**
- Nessun tempo di scadenza sulla finestra di conferma (a differenza di Cash out e Chiudi).

**Esempio con le cifre**
- Passi la pagina a PAPER, ma 3 partite armate quando eri in LIVE continuano con soldi veri: compare
  «⚠️ 3 partite stanno operando in LIVE... Per fermarle davvero serve chiuderle a mano dalle loro
  schede.» Su una di queste Mike ha 10,00 € puntati sull'Under 3.5 a 1,50: se la partita finisce
  con 3 gol incassi +4,75 € veri (vincita 5,00 € meno 5 % di commissione); con 4 gol perdi 10,00 €
  veri.

**Cosa vedi nell'app**
- Il toggle in alto, la finestra di conferma, il riquadro colorato e i due avvisi.

**Se qualcosa va storto**
- Se lasci la finestra aperta e intanto cambia qualcosa, la conferma resta valida lo stesso (vedi
  «Punti da decidere» n. 18).
- Se la scrittura fallisce (rete giu'), la modalita' non cambia: Mike continua nella vecchia.
- Quando Mike se ne accorge: al giro successivo (di solito entro 2 secondi).
- Paper o live: questo e' esattamente il comando che sceglie fra i due, per tutto il bot.

**Per il tecnico**
- E-3 `ModeToggle.tsx`, `LiveConfirmDialog.tsx` (Mike non passa `armKey`), `pages/Mike.tsx:275-283,
  422,753-760`; `bot.setMode('live')` → `mike_update_params(p_mode='live')`.
- E-4 avvisi: `pages/Mike.tsx:428-475`, `stats.eventi_altra_modalita`, `stats.live_abilitato`
  (variabile d'ambiente `MIKE_LIVE_ENABLED`).
- E-40 `mike_control.mode` (`migrations/mike_bot.sql:24-41`); E-47 `mike_update_params`.

---

## 03 - Parametri («106 valori»)

**Cosa fa**
- «Parametri» nella riga fissa apre un pannello laterale con TUTTI i parametri di Mike, in 8
  gruppi: Generale, Pre-match, Dal fischio d'inizio, Copertura Over 4.5, Cash-out globale, Uscite HT
  / 2T, Re-ingresso (gol + 3.5), Rischio. Ogni gruppo ha una nota che dice cosa governa (Rischio:
  «tetti e stop: sono l'ultima barriera prima dei soldi veri.»).
- Ogni campo ha il minimo e il massimo scritti nel suo aiuto. Se scrivi un valore fuori dai limiti,
  il campo lo riporta dentro e scrive «clampato a {valore} (ammesso {min} … {max})».
- Modifiche non ancora salvate: pallino ambra accanto al titolo e «modifiche non salvate: premi
  «Salva parametri» per applicarle al servizio».
- «Default» rimette i valori di fabbrica nella BOZZA ma non salva: poi serve «Salva parametri».
- «Salva parametri» manda i valori a Mike, che li usa dal giro dopo senza fermarsi.
- Il pannello si riallinea da solo ai valori salvati SOLO se non hai toccato nulla: una modifica in
  corso non si perde mai.
- Il campo «Uscite automatiche» e' l'interruttore del riquadro 04.
- La modalita' paper/live NON e' in questo pannello: si cambia solo dal toggle (riquadro 02). Lo dice
  anche il testo in fondo al pannello.
- La tabella completa dei 106 parametri e' in fondo a questo file («Tabella dei parametri»).

**Quando**
- Al clic su «Salva parametri». Mike li legge al giro successivo (di solito entro 2 secondi).

**Numeri**
- 106 parametri, 8 gruppi. Tutti coincidono per nome, valore di serie e limiti con quelli che il
  motore di Mike usa davvero: non esiste un parametro del motore che il pannello non mostri.

**Esempio con le cifre**
- Cambi «Stake Under 3.5» da 10 a 15 € e premi «Salva parametri»: il pallino ambra sparisce, il
  prossimo ingresso punta 15,00 € invece di 10,00 €. A quota 1,50, con 3 gol l'incasso netto passa
  da +4,75 € a +7,13 €; con 4 gol la perdita passa da −10,00 € a −15,00 €.
- Scrivi 700 nello stake: il campo scrive «clampato a 500 (ammesso 0,5 … 500)».

**Cosa vedi nell'app**
- Il pannello laterale, il pallino ambra, le scritte di limite.

**Se qualcosa va storto**
- Salvataggio fallito (rete giu'): i valori restano nella bozza, Mike continua coi vecchi.
- Rischio di fondo: scrivere i parametri senza averli prima letti rimetterebbe TUTTI gli altri ai
  valori di serie. L'app rifiuta di salvare finche' non ha letto una riga di parametri non vuota.
- Un campo non fa nulla: la pausa fra due tentativi dell'uscita al fischio (vedi «Punti da decidere» n. 10).
- Paper o live: i parametri sono gli stessi per tutte e due le modalita'. «LIVE: uscita appoggiata
  attiva» cambia solo il live (riquadro 11 del capitolo 13b).

**Per il tecnico**
- E-28 `components/mike/MikeParamsSheet.tsx`, `components/trading/ParamsSheetBase.tsx`,
  `lib/mike.ts::MIKE_PARAM_FIELDS,MIKE_PARAM_DEFAULTS,mergeMikeParams` (421-616).
- E-28-bis specchio di `Betfair/mike/config.py::PARAM_SPEC` (106 chiavi), `BACKEND_ONLY_PARAMS`
  vuota.
- E-47 `mike_update_params(p_params,p_mode)` (`migrations/mike_bot.sql:224-245`); protezione
  `lib/interruttori.ts::paramsLetti`.

---

## 04 - Uscite («di serie manuali»)

**Cosa fa**
- Un interruttore unico per Mike: «Uscite automatiche». Di serie e' SPENTO.
- Spento (manuali): Mike non esegue piu' da solo le uscite a sua scelta (green-up prima del fischio,
  uscita al fischio, cash out della posizione, uscita in perdita all'intervallo o nel secondo tempo,
  uscita del re-ingresso). Scrive una proposta e aspetta la tua approvazione (riquadro 07).
- Acceso (automatiche): Mike esegue da solo quelle uscite.
- In tutti e due i casi restano SEMPRE automatiche: copertura Over 4.5, tetto di perdita della
  partita, regolamento a fine partita, ritiro degli ordini, controllo degli ordini in verifica.
- Lo stesso interruttore e' nel pannello Parametri (gruppo «Uscite HT / 2T») e nella riga di Mike in
  Control Room: e' lo stesso, con lo stesso testo.

**Quando**
- Passare ad automatiche chiede una conferma (stessa conferma nei tre punti in cui l'interruttore
  compare). Se anche passare a manuali chieda conferma: non chiarito (vedi «Punti non chiariti»).
- Mike legge il nuovo stato al giro successivo (di solito entro 2 secondi).

**Numeri**
- Di serie: spento (manuali), dal 25/09 sera.

**Esempio con le cifre**
- Interruttore spento. Mike ha puntato 10,00 € sull'Under 3.5 a 1,50 e la quota scende a 1,46: vuole
  fare green-up. Non lo fa: compare la proposta «Mike vorrebbe uscire: green-up pre-partita». Se la
  approvi, esce ai prezzi di quel momento; se non la approvi e la partita finisce 4 gol, perdi
  10,00 €.

**Cosa vedi nell'app**
- L'interruttore nel pannello Parametri; le proposte sotto le schede delle partite.

**Se qualcosa va storto**
- L'app, quando scrive l'interruttore, usa l'ultima copia dei parametri che ha in memoria e non la
  rilegge prima (vedi «Punti da decidere» n. 15).
- Con le uscite manuali e tu lontano dallo schermo, le uscite in perdita non scattano: restano solo
  copertura e tetto di perdita.
- Paper o live: identico.

**Per il tecnico**
- E-23 e E-28: parametro `uscite_automatiche` (default `false`); interruttore condiviso
  `components/controlroom/InterruttoreUscite.tsx`; scrittura `lib/interruttori.ts::cambiaUscite` →
  `mike_update_params` con la sola chiave `uscite_automatiche` (E-47).
- Migrazioni `uscite_manuali_default_2026-09-25.sql`, `uscite_automatiche_mike_2026-09-25.sql`.

---

## 05 - Avvia o Ferma («accende, spegne»)

**Cosa fa**
- «Avvia» accende Mike nella modalita' scelta col toggle (riquadro 02). I parametri gia' salvati
  RESTANO: accendere non li azzera.
- «Ferma» ferma Mike: se era in corsa passa a «BOT IN ARRESTO», e al giro dopo Mike stesso si porta
  a «BOT FERMO». Ferma le aperture, non le uscite: le posizioni aperte restano sorvegliate.
- All'avvio dell'app desktop nessun bot opera: Mike si accende solo quando lo premi tu.

**Quando**
- Al clic. Mike se ne accorge al giro successivo (di solito entro 2 secondi).

**Numeri**
- Nessuno. Dalla pagina di Mike l'accensione non ha una seconda conferma; la doppia conferma per i
  soldi veri e' nel toggle LIVE (riquadro 02) e nella Control Room (capitolo 13b, riquadro 04).

**Esempio con le cifre**
- Toggle su PAPER, premi «Avvia»: l'etichetta passa da «BOT INATTIVO» a «BOT IN CORSA». Un'ora prima
  di Inter - Milan la partita compare in «⏱ PRE-MATCH» e Mike punta 10,00 € finti sull'Under 3.5.
- Premi «Ferma» con una partita coperta aperta: Mike non apre piu' nulla, ma la copertura e le
  chiusure di quella partita continuano.

**Cosa vedi nell'app**
- Il pulsante «Avvia»/«Ferma» e l'etichetta di stato nella riga fissa.

**Se qualcosa va storto**
- Scrittura fallita: lo stato non cambia.
- Mike acceso ma servizio fermo sul PC: etichetta «BOT IN CORSA · SENZA BATTITO»; va riavviata l'app
  desktop.
- Paper o live: la modalita' con cui parte e' quella del toggle.

**Per il tecnico**
- E-45 `mike_activate(p_mode,p_params)` (`migrations/mike_bot.sql:183-203`): `status='running'`,
  `params=coalesce(p_params,params)`; `activateMike` non passa `params`.
- E-46 `mike_stop()` (`migrations/mike_bot.sql:205-222`): `running`→`stopping`, poi `stopped`.
- E-40 tabella `mike_control` (riga unica `id=1`: `status`, `mode`, `params`, `stats`, `error`,
  `heartbeat_at`...). `Betfair/stream/avvio_app.py` (nessun bot all'avvio).

---

## 06 - Scheda partita («quote e cifre»)

**Cosa fa**
Una scheda per partita. Ha sempre la stessa altezza: ogni zona c'e' anche vuota («—»), cosi' non
salta nulla quando arriva un ordine. Il bordo sinistro cambia colore: verde acqua prima del fischio,
viola in gioco, verde a posizione piatta, bianco tenue a partita regolata, rosso in errore o
saltata. Dall'alto in basso:

1. **Testata**: punteggio grande («0–1», trattino se manca), espulsioni (🟥 casa/trasferta), nome e
   competizione. In gioco: minuto, gol, «intervallo», risultato del primo tempo. Prima del fischio:
   ora del fischio e conto alla rovescia («fra 1h 12m»), oppure «in attesa del fischio» se l'ora e'
   passata ma il feed non dice ancora che si gioca. Partita chiusa: ora, gol totali, fase. A destra:
   la FASE (una delle 21, vedi «Le 21 fasi» qui sotto) e la freschezza del feed di QUESTA partita:
   «feed N s» verde fino a 5 secondi, ambra fino a 20, «FEED FERMO (N s)» rosso oltre, «FEED:
   NESSUN DATO» se Mike non pubblica l'eta'; a partita chiusa «partita chiusa» grigio, mai rosso.
   Sotto il titolo, una frase dice cosa sta facendo Mike adesso (es. «posizione abbinata prima del
   fischio: aspetta il green-up a +N tick»).
2. **Allarmi** (riga sempre presente): rosso «linea {X} assente nel feed: nessuna copertura e nessun
   cash out possibile»; «CHIUSURA IN CORSO» lampeggiante; «VOID · mercato annullato» o «VOID
   ({linea})» (l'annullamento vale per un mercato, non per tutta la partita); «ORDINE IN VERIFICA SU
   BETFAIR»; «NESSUN RIENTRO» (dopo una tua chiusura prima del fischio: si toglie con «Riprendi»);
   «SOLDI VERI» se la partita e' in live. Questi allarmi spengono i pulsanti di chiusura col motivo
   scritto.
3. **Quadro del modello**: 4 caselle. «P(4 gol) modello» con la fonte dei gol attesi (da partita
   abbinata / da quote pre-partita / da mercato Over/Under / «MODELLO ASSENTE» ambra); «P(4 gol)
   mercato»; in gioco «Hazard gol 3′» (probabilita' di un gol nei prossimi 3 minuti), prima del
   fischio «P(Over 4.5) modello»; in gioco «Pressione ×N» (con 🔥 oltre la soglia di fase calda),
   prima del fischio «λ casa / trasferta» (gol attesi). Lega senza modello: una riga sola «Nessun
   modello per questa lega: il bot decide con le quote e le soglie fisse.». Sotto, 9 barre: la
   probabilita' di 0, 1, ... 8 gol totali; la barra dei 4 gol sempre rossa («e' l'unica casella che
   perde»); senza dati, «Nessun modello per questa lega: copertura a regola fissa (quote e soglie del
   mercato).».
4. **Tre linee di quota**, sempre presenti: «Under 3.5», «Over 4.5», «Under 4.5 (re-ingresso)». Per
   ciascuna: miglior punta e banca, importo disponibile, freccetta di variazione (colore neutro),
   ritardo di piazzamento in secondi, stato del mercato: aperto non si scrive, «SOSPESO» ambra,
   «CHIUSO» rosso, «NON ATTIVO» rosso. A partita chiusa: «... ultime quote viste», riquadro sbiadito,
   niente freccetta.
5. **Riga dei dati di partita**: «Volume mercato» (oppure «non pubblicato»: il feed manda sempre 0);
   «ingresso @{quota}» (primo ingresso Under 3.5); «al fischio @{quota}» con lo scarto in tick (verde
   se a favore); «ciclo N di M» («esauriti» oltre il massimo, «(massimo non configurato)» se il
   massimo e' 0); giri gia' chiusi e quanto hanno reso; a partita regolata, il risultato finale.
6. **Posizioni**: una riga per selezione aperta: lato netto PUNTA/BANCA, linea, euro abbinati; in
   ambra «(+X in ingresso sul book)» per un ordine che AUMENTEREBBE l'esposizione, in verde acqua «(X
   di chiusura appoggiata)» per uno che la CHIUDE; quota media d'ingresso; quota ora e prezzo a cui
   chiuderebbe; scarto in tick (verde a favore, rosso contro, grigio «= 0 tick»); «Se chiudo ora
   (netto)»: SOLO la cifra netta calcolata da Mike, «—» se manca (motivo nel suggerimento). Nessuna
   posizione: «nessuna posizione aperta —». A partita regolata i prezzi restano fermi all'ultimo dato.
7. **Ordini sul book**: ordini non ancora abbinati del tutto: lato, ruolo, selezione, stato in chiaro
   (chiesto, abbinato, prezzo medio, residuo), «resta valido in gioco» se l'ordine sopravvive al
   fischio, distanza dal miglior prezzo: «al best» verde, «N tick sopra/sotto il best» ambra,
   «distanza dal best: —». Nessun ordine: «—».
8. **A fine gara, per gol totali**: una casella per 0, 1, 2 ... «8+» gol, col P&L netto che
   risulterebbe. La casella dei 4 gol ha il bordo rosa («i 4 gol: l'unico esito che perde»). I gol
   attuali sono cerchiati. Sotto: «Liability aperta» (arancione) e «P&L bloccato»; a partita chiusa
   «rischio chiuso 0,00 €» e l'esito.
9. **«Se chiudo tutto ora»**: il valore netto di chiusura di TUTTA la partita, la percentuale sulla
   base e la soglia oltre cui Mike chiude da solo; una barra verso la soglia (parte da zero: un
   valore negativo non mostra progresso); un avviso ambra se il book non basta a chiudere tutto al
   prezzo mostrato; fino a tre righe di spiegazione:
   - cash out anticipato: es. «min 0,20 € (1,6%) · a un passo dal 5% · fase calda · aspettare vale
     +0,10 € → chiude (punteggio_caldo)»;
   - uscita a modello: es. «uscita HT a modello: tenere vale −0,79 € · P(4) 22% · premio 0,53 € →
     tiene»;
   - copertura in attesa: es. «risparmio atteso 9,0% · hazard 4,0% · P(4) mercato 12% · al massimo
     fino al 10′».
   Sotto, l'esito dell'ultima tua richiesta su questa partita, in italiano (riquadro 08).
10. **Pulsanti** in fondo: riquadri 07, 08, 09.

**Le 21 fasi della partita** (etichetta in testata): in attesa · ingresso in corso · Under 3.5
aperto · green-up in corso · tiene fino al fischio · ultimo ingresso · in gioco senza posizione ·
uscita al fischio in corso · gol precoce, seconda puntata · in gioco scoperto · copertura in corso ·
in gioco coperto · chiusura in corso · piatta · re-ingresso in corso · re-ingresso Under 4.5 aperto
· green del re-ingresso in corso · in regolamento · regolata · errore · saltata.

**I ruoli di un ordine** (nelle tabelle): ingresso Under 3.5; green-up dell'Under 3.5; ultimo
ingresso prima del fischio (resta valido in gioco); seconda puntata dopo un gol precoce; uscita al
fischio; copertura Over 4.5; chiusura Under 3.5; chiusura Over 4.5; re-ingresso Under 4.5; green del
re-ingresso; chiusura decisa da te (segnata ✋).

**Quando**
- Si aggiorna quando Mike riscrive la partita (ogni pochi secondi: 5 secondi per una partita attiva,
  60 per una a riposo). Il conto alla rovescia scorre ogni secondo per conto suo.

**Numeri**
- Freschezza feed della partita: verde fino a 5 s, ambra fino a 20 s, rosso oltre.
- Soglia di fase calda della pressione: 1,15. Soglia di chiusura piena: 5 %. Cash out anticipato:
  minimo 2 %, «a un passo» 2 punti, fase calda hazard 0,10, punteggio caldo 3 gol, margine 1 punto.
- Massimo giri per partita: 10.

**Esempio con le cifre**
- Testata: «0–1 · 34′ · 2 gol», fase «in gioco scoperto», «feed 3 s» verde.
- Posizioni: «PUNTA · Under 3.5 · 10,00 € · ingresso 1,50 · ora 1,42/1,44 · chiudo @1,44 · ▼ 4 tick
  (verde) · Se chiudo ora +0,55 €».
- Ordini sul book: «BANCA · Green-up Under 3.5 (Under 3.5) · SUL BOOK · 2 tick sotto il best».
- Per gol totali: «0: +1,30 € · 1: +1,20 € · 2: +0,90 € · 3: +0,40 € · 4: −8,20 € (bordo rosa) · 5+:
  +2,00 €».
- «Se chiudo tutto ora +0,44 € (3,6% · chiude da solo a 5,0%)», barra al 72 % verso la soglia.
- Riga dati: «ingresso @1,50 · al fischio @1,48 (−1 tick) · ciclo 2 di 10 · 1 ciclo chiuso +0,14 €».

**Cosa vedi nell'app**
- La scheda descritta, nelle sezioni della linguetta Partite (riquadro 01).

**Se qualcosa va storto**
- Feed della partita fermo oltre 20 s: etichetta rossa e pulsanti di chiusura spenti.
- Una linea manca nel feed: banner rosso, niente copertura e niente cash out possibili.
- Ordine con esito ignoto: «ORDINE IN VERIFICA SU BETFAIR»; Mike lo conta nella liability al caso
  peggiore finche' non si chiarisce, non lo tratta mai come annullato.
- Paper o live: calcoli identici; «SOLDI VERI» in rosso ricorda che la partita e' in live.

**Per il tecnico**
- E-9 `MikeMatchCard.tsx:584-649`, `lib/mike.ts::feedFreshness,etaQuoteS,awaitingKickoff,phaseMeta,
  MIKE_PHASE_META` (618-810). E-10 `MikeMatchCard.tsx:650-684`, `eventFlags,lineLabel,marketLabel`.
- E-11 `MikeMatchCard.tsx:686-733`, `hasModel` (973-980). E-12 `MikeMatchCard.tsx:262-305,735-764`,
  `marketStatusMeta`. E-13 `MikeMatchCard.tsx:315-342,766-823`.
- E-14 `MikeMatchCard.tsx:825-918`, `positionRows,selectionExposure,lockedIfClosed` (1091-1130).
- E-15 `MikeMatchCard.tsx:920-955`, `bookOrders,legStatusLabel,rigaOrdineDaGamba`.
- E-16 `MikeMatchCard.tsx:957-998`, `pnlByTotalCells`. E-17 `MikeMatchCard.tsx:84-123,1000-1073`,
  `cashoutBarPct,cashoutPct`.
- E-41 tabella `mike_events` (`migrations/mike_bot.sql:43-74`: `state`, `live`, `positions`, `ctx`,
  `dossier`...); E-42 tabella `mike_trades` (`size_requested/matched/remaining`,
  `avg_price_matched`). Glossario: stati `WATCH`...`SKIPPED`, ruoli `under_entry`...`manual_close`.
- Cadenze: parametri `publish_heartbeat_s`=5, `publish_idle_heartbeat_s`=60.

---

## 07 - Proposta d'uscita («approvi: 1 clic»)

**Cosa fa**
- Con le uscite manuali (riquadro 04), quando Mike vuole uscire compare sotto la scheda della partita
  un riquadro: «Mike vorrebbe uscire: {tipo}» (green-up pre-partita, uscita al fischio, cash out
  della posizione, uscita del re-ingresso), con «(in perdita)» e bordo rosso se l'uscita e' in
  perdita, ambra altrimenti.
- Mostra: il motivo scritto da Mike; gli ordini proposti, uno per riga, col prezzo del momento (dal
  book al millisecondo se c'e', altrimenti dal feed della partita, e lo dice); la frase «al clic: il
  bot esce a mercato con la sua macchina d'uscita (prezzi e size di quel momento)...»; due cifre,
  «chiudendo ora» (il valore di adesso) e «alla decisione» (il valore quando la proposta e' nata);
  da quanti secondi e' stata decisa; la freschezza del feed.
- Pulsante «approva uscita»: UN clic, nessuna doppia conferma, anche in live.
- Non c'e' un pulsante «rifiuta». L'alternativa scritta accanto: «oppure chiudi a mano con «Chiudi»
  di Mike» (sulla pagina di Mike vuol dire Cash out o Chiudi a mercato, riquadro 08).
- La proposta sparisce da sola quando Mike la esegue o quando cambia idea.

**Quando**
- Dopo il clic compare «approvazione inviata: parte al prossimo giro del bot». Mike la esegue al
  giro successivo, ai prezzi di quel momento.
- La firma vale al massimo 120 secondi dal clic e solo per la stessa uscita (capitolo 6).

**Numeri**
- Nessun tempo di conferma. Durata della firma: 120 secondi.

**Esempio con le cifre**
- «Mike vorrebbe uscire: cash out della posizione — chiudendo ora +0,42 € · alla decisione +0,44 € ·
  deciso 6 s fa». Premi «approva uscita»: al giro dopo Mike chiude, e incassi circa +0,42 € qualunque
  sia il risultato finale. Se non premi e la partita finisce 4 gol, la posizione perde.

**Cosa vedi nell'app**
- Il riquadro ambra (rosso se in perdita) sotto ogni scheda con una proposta viva. Lo stesso
  riquadro compare in Control Room (capitolo 13b, riquadro 09).

**Se qualcosa va storto**
- Feed fermo o sconosciuto: pulsante spento con «feed fermo o ignoto: non si approva su prezzi
  vecchi».
- Una richiesta gia' in viaggio: pulsante spento.
- Invio fallito (rete giu'): «approvazione non inviata: {motivo}». Nessun ordine parte.
- Paper o live: vale la modalita' della partita, mai quella del toggle.

**Per il tecnico**
- E-23 `components/controlroom/PropostaUscitaMike.tsx`; montaggio `pages/Mike.tsx:342-351`.
- E-50 `requestMike('approva_uscita', {event_id, bot:'mike', mode, chiave, contesto:{prezzo_visto,
  prezzo_segnale, eta_ms, fonte, market_id, selection_id, clic_ms}})`; senza `chiave` il database
  rifiuta con «approva_uscita senza chiave della proposta».

---

## 08 - Cash out, Chiudi («tutta la partita»)

**Cosa fa**
Due pulsanti, visibili solo se la partita ha almeno una posizione e non e' finita. Tutti e due
chiudono TUTTA la partita insieme (Under 3.5, Over 4.5 ed eventuale re-ingresso): Mike non fa
chiusure parziali.

- **«Cash out {importo}»**: apre una finestra con il netto di chiusura (calcolato da Mike), la
  percentuale sulla base e la soglia automatica, il dettaglio per selezione e l'esito dell'ultima
  richiesta.
- **«Chiudi a mercato»**: chiude subito ai prezzi del momento SENZA guardare nessuna soglia di
  profitto: e' il piu' pericoloso, perche' puo' rendere definitiva una perdita. La finestra dice:
  «Chiusura IMMEDIATA di {partita} ai prezzi disponibili adesso: il servizio annulla gli ordini sul
  book e chiude tutte le posizioni senza guardare la soglia di profitto. Se il mercato e' contro, la
  perdita diventa definitiva.» Mostra il netto, oppure «n/d» con «il servizio non sa quanto vale la
  chiusura adesso: chiuderesti al buio».
- In live, per tutti e due, scritta rossa «MODALITA' LIVE: soldi veri» e DOPPIA conferma: il primo
  clic arma il pulsante, che diventa «Confermi? soldi veri»; l'armamento scade da solo dopo 10
  secondi (o se il netto cambia, o se le condizioni che lo permettevano cadono). In paper basta un
  clic.
- Dopo l'invio riuscito la finestra si chiude. Mike prima annulla gli ordini sul book, poi guida la
  chiusura nei giri successivi. L'esito compare sotto il riquadro «Se chiudo tutto ora» della scheda,
  es. «Cash out in corso…», «Cash out rifiutato: feed stantio», «Cash out armato: annullati 2 ordini
  sul book · chiusura in corso · netto stimato +0,47 €». «Armato» vuol dire: Mike ha preso il
  comando e sta chiudendo, non ancora chiuso.
- In testata compare «CHIUSURA IN CORSO» lampeggiante.

**Quando**
- Cash out spento, col motivo scritto, in quest'ordine: 1) una tua chiusura e' gia' in corso; 2)
  un'altra operazione e' in corso; 3) lo scanner e' fermo; 4) l'eta' delle quote della partita e'
  sconosciuta («nessun ordine al buio»); 5) il feed della partita e' fermo; 6) manca una linea nel
  feed; 7) nessuna posizione aperta.
- Chiudi a mercato si puo' chiedere anche quando Mike non sa calcolare il netto; e' spento solo se
  un'operazione e' in corso o per gli stessi motivi di feed fermo e linea assente.
- Mike lo legge al giro successivo (di solito entro 2 secondi); la chiusura vera puo' richiedere piu'
  giri (riprova il residuo ogni 10 secondi, al massimo 20 tentativi).

**Numeri**
- Scadenza della doppia conferma in live: 10 secondi (Cash out e Chiudi).
- Riprezzo del residuo di chiusura: 10 s; tentativi massimi: 20.

**Esempio con le cifre**
- Paper, Cash out a +0,55 €: un clic nella finestra basta.
- Live, partita in perdita: premi «Chiudi a mercato», leggi «−3,20 €», premi, il pulsante diventa
  «Confermi? soldi veri», lo ripremi entro 10 secondi: Mike chiude e i −3,20 € diventano definitivi
  (invece di rischiare −10,00 € con 4 gol). Se aspetti 11 secondi, il pulsante si disarma e devi
  ricominciare.

**Cosa vedi nell'app**
- I pulsanti in fondo alla scheda, le finestre descritte, l'esito sotto «Se chiudo tutto ora».

**Se qualcosa va storto**
- Invio fallito: la finestra resta aperta con «Cash out NON riuscito: {motivo}. La posizione e'
  ancora aperta — controlla su Betfair prima di riprovare.» (per Chiudi: «Chiusura NON riuscita:
  ...»).
- Modalita' dichiarata diversa da quella vera della partita: Mike rifiuta la richiesta.
- Paper o live: la doppia conferma c'e' solo se la PARTITA e' in live.

**Per il tecnico**
- E-17 esito richieste `MikeMatchCard.tsx:1000-1073`. E-18 `components/mike/MikeCashOutButton.tsx`,
  `MIKE_LIVE_ARM_TIMEOUT_MS`=10000 (riga 23), `MikeMatchCard.tsx:1075-1090`; richiesta
  `mike_request('cashout',{event_id,bot:'mike',mode})`.
- E-19 `MikeMatchCard.tsx:344-490,1101-1110`, `MIKE_FLATTEN_ARM_TIMEOUT_MS`=10000 (riga 354);
  richiesta `mike_request('flatten',...)`. Esito `phase:'armed'`, `cashout_net`, `cancelled`.
- Parametri `close_retry_s`=10, `close_max_attempts`=20. Rifiuto `richiesta_ambigua`.

---

## 09 - Salta, Riprendi («e Annulla ordini»)

**Cosa fa**
- **«Annulla ordini»**: ritira SOLO gli ordini ancora sul book; le posizioni gia' abbinate restano.
  Visibile se ci sono ordini vivi e la partita non e' finita. Nessuna finestra, nessuna conferma.
- **«Salta»**: toglie la partita dal lavoro di Mike. Visibile solo se la partita non e' finita, non ha
  posizioni aperte e non e' gia' saltata. Nessuna conferma. La partita va nella sezione «⚠️ DA
  SISTEMARE».
- **«Riprendi»** (bordo verde acqua): rimette in gioco una partita saltata o in errore, oppure
  riattiva il rientro dopo una tua chiusura prima del fischio («NESSUN RIENTRO»). E' l'unico
  pulsante presente anche su una partita in errore. Nessuna conferma.

**Quando**
- Al clic. Mike lo legge al giro successivo (di solito entro 2 secondi).
- Ogni pulsante e' spento se un'altra operazione e' in corso o se la stessa richiesta e' gia' in
  viaggio per quella partita.

**Numeri**
- Nessuno.

**Esempio con le cifre**
- Un ordine d'ingresso da 10,00 € a 1,50 resta sul book da un minuto senza abbinarsi: premi
  «Annulla ordini», Mike lo ritira; nessun euro esposto.
- Una partita di una lega poco affidabile: premi «Salta» prima che Mike entri; Mike non punta.
- Una partita finita in errore per un problema di rete: premi «Riprendi», riparte dal giro dopo.
- Hai chiuso tu prima del fischio con +0,30 €: compare «NESSUN RIENTRO». Premi «Riprendi» se vuoi
  che Mike torni a puntare su quella partita.

**Cosa vedi nell'app**
- I tre pulsanti in fondo alla scheda; «NESSUN RIENTRO» negli allarmi; la sezione «DA SISTEMARE».

**Se qualcosa va storto**
- Invio fallito: nessun cambiamento, la partita resta com'era.
- Paper o live: nessuna conferma in piu' in nessuna delle due.

**Per il tecnico**
- E-20 `MikeMatchCard.tsx:1092-1100` → `mike_request('cancel',...)`.
- E-21 `MikeMatchCard.tsx:1111-1118` → `mike_request('skip_event',...)`, stato `SKIPPED`.
- E-22 `MikeMatchCard.tsx:1119-1126` → `mike_request('resume_event',...)`; visibile se `SKIPPED`,
  `ERROR` o `flags.noReentry`.

---

## 10 - Richiesta («nel database»)

**Cosa fa**
- Ogni pulsante della scheda partita (approva uscita, Cash out, Chiudi a mercato, Annulla ordini,
  Salta, Riprendi) scrive UNA riga in una coda di richieste nel database, con il tipo, la partita e
  la modalita' della partita.
- Il database controlla che il tipo sia uno dei sei ammessi e che la partita sia indicata; per
  «approva uscita» pretende anche il riferimento della proposta (non si approva mai «qualcosa» al
  buio).
- Ogni richiesta ha uno stato: in attesa, in lavorazione, fatta, rifiutata, errore; e un esito con un
  messaggio in italiano, che la scheda mostra.
- I comandi del bot (Avvia, Ferma, paper/live, Parametri, Uscite) non passano da questa coda:
  scrivono direttamente la riga di stato di Mike (riquadri 02-05). Anche quella si legge al giro
  dopo.
- Nessuno puo' scrivere le tabelle di Mike dal browser: si passa solo da questi comandi, e solo con
  la tua utenza di proprietario.

**Quando**
- Subito al clic.

**Numeri**
- La pagina rilegge le ultime 50 richieste con il loro esito.

**Esempio con le cifre**
- Premi Cash out su Inter - Milan in paper: nasce la richiesta n. 812, tipo cash out, «in attesa».
  Al giro dopo diventa «fatta» con «Cash out armato: annullati 2 ordini sul book · chiusura in corso ·
  netto stimato +0,47 €».

**Cosa vedi nell'app**
- Non vedi la coda: vedi l'esito sotto «Se chiudo tutto ora» della scheda partita.

**Se qualcosa va storto**
- Database non raggiungibile: la richiesta non nasce; il pulsante mostra l'errore (riquadri 07-09).
- Chi non e' il proprietario: «non autorizzato (owner-only)».
- Paper o live: la modalita' viaggia nella richiesta, scritta dalla partita, mai indovinata.

**Per il tecnico**
- E-44 tabella `mike_requests` (`migrations/mike_bot.sql:136-149`; `result` in `mike_bot_v2.sql:25`;
  stato `rejected` in `mike_bot_v2.sql:30-36`; `approva_uscita` in
  `uscite_automatiche_mike_2026-09-25.sql:28-40`); lettura `fetchMikeRequests`.
- E-50 `mike_request(p_kind,p_payload)` (`mike_bot.sql:304-326`, allargata in
  `uscite_automatiche_mike_2026-09-25.sql:23-69`), restituisce l'id.
- Tutte le funzioni `SECURITY DEFINER` con controllo `betfair_live_is_owner()`; revocate a
  `public`/`anon`.

---

## 11 - Mike legge («al giro dopo»)

**Cosa fa**
- Mike, al suo giro successivo, legge la riga di stato (acceso, modalita', parametri, interruttore
  uscite) e le richieste in attesa, ed esegue: fa gli ordini, li ritira, chiude, salta, riprende.
- Poi riscrive le partite, gli ordini, l'attivita', l'esito della richiesta e il suo battito.
- La pagina riceve la novita' e si ridisegna (entro 1,5 secondi dalla novita', o alla rilettura di
  sicurezza ogni 15 secondi). Con il «canale locale» quote, P&L e stato arrivano direttamente dal PC.

**Quando**
- Di solito entro 2 secondi dal clic (cadenza tipica del giro di Mike). Senza partite in gioco, il
  giro a riposo e' di 5 secondi. Dalla Control Room l'app sveglia anche Mike subito dopo la scrittura
  (capitolo 13b, riquadro 07).

**Numeri**
- Giro tipico: 2 secondi. Giro a riposo: 5 secondi. Pagina: 1,5 s dopo una novita', 15 s al massimo.
- Battito di Mike scritto ogni 20 secondi; statistiche di testata ogni 10 secondi; aggregati
  ricalcolati ogni 20 secondi.

**Esempio con le cifre**
- Premi Annulla ordini alle 18:32:10. Alle 18:32:12 Mike ritira l'ordine da 10,00 €; alle 18:32:13
  la sezione «Ordini sul book» della scheda mostra «—».

**Cosa vedi nell'app**
- Il risultato sulla scheda; l'ora dell'ultimo giro nella casella «Ultimo ciclo».

**Se qualcosa va storto**
- Mike spento o bloccato: la richiesta resta «in attesa»; la testata diventa rossa «SENZA BATTITO».
  Dalla pagina di Mike non c'e' un avviso a tempo sulla singola richiesta (in Control Room si': 3
  minuti, capitolo 13b riquadro 10).
- Paper o live: identico.

**Per il tecnico**
- E-48 `get_mike_state()` (rilettura 15 s, raggruppamento 1,5 s, 5 tabelle in tempo reale).
- Cadenza tipica 2 s dichiarata in `components/controlroom/PannelloBot.tsx` da
  `Betfair/mike/service.py`; parametri `idle_cycle_s`=5, `heartbeat_min_s`=20, `stats_min_s`=10,
  `aggregates_cache_s`=20. Il giro e' descritto nel capitolo 9.

---

## 12 - Storico e conti («paper, live a parte»)

**Cosa fa**
- **Linguetta Operazioni**: una riga per partita col netto di oggi (commissione gia' tolta), grande e
  colorato. Clic sulla riga: si aprono i giri (ingresso → uscita → quanto ha reso) e dentro ogni giro
  gli ordini veri (ora, lato, selezione, importo, quota, esito). Gli ordini nati da un tuo comando
  hanno il segno «manuale». Clic sul nome: torni alla scheda della partita, evidenziata per 2
  secondi. Sotto, la curva del guadagno della giornata (un gradino a ogni regolamento), oppure
  «nessun trade ancora regolato oggi — la curva compare al primo incasso». Un avviso dichiara se ci
  sono operazioni dell'altra modalita' non mostrate, o se si e' arrivati al tetto di 500 righe.
- **Linguette Risultati Pre-Match e Risultati Live**: la stessa tabella divisa per fase. Pre-Match:
  i giri aperti e chiusi prima del fischio (ingresso Under 3.5 e sua uscita). Live: tutto quello
  successo a partita iniziata (uscita al fischio, seconda puntata, copertura, chiusure,
  re-ingresso). Una partita che ha lavorato in tutte e due compare in tutte e due, ciascuna coi suoi
  euro.
- **Linguetta Storico**: calendario del mese col P&L di ogni giorno, pannello con le statistiche del
  periodo, dettaglio del giorno scelto. Nessun pallino «centrato» (Mike non ha obiettivo). «Aggiorna»
  rilegge a comando. Se il giorno ha una posizione ancora viva, un pulsante riporta alla linguetta
  Partite. Scritta fissa: «Giornata operativa = fuso Europe/Rome · ... · P&L realizzato = posizioni
  PIAZZATE nel giorno (chiusure incluse), anche se si regolano dopo.»
- Come si conta: un giro chiuso in profitto conta UNA vittoria, non due righe; vinte e perse si
  decidono dal segno del risultato del giro intero. Un ordine in verifica su Betfair conta come
  piazzato, non come errore. Il giorno di un'operazione e' quello in cui e' stata PIAZZATA, non
  quello in cui si e' regolata.
- Tutte queste viste mostrano solo la modalita' con cui Mike gira ORA. I realizzati dell'altra
  modalita' sono calcolati a parte, per dichiararli senza sommarli.

**Quando**
- Operazioni e Risultati: a ogni rilettura della pagina. Storico: all'apertura, al cambio di mese,
  periodo o giorno, e a «Aggiorna».

**Numeri**
- Tetto righe della pagina: 500. Finestra massima dello Storico: 400 giorni (oltre, ridotta con
  avviso). Commissione tolta: 5 % di serie.

**Esempio con le cifre**
- «Inter - Milan: +1,84 €» si apre in «ciclo 1: 1,50 → 1,48, +0,14 €» e poi nell'ordine vero «punta
  10,00 € @1,50, ore 18:32».
- Una partita chiusa in profitto prima del fischio e poi rientrata dopo un gol: in «Risultati
  Pre-Match» col primo giro, in «Risultati Live» col re-ingresso.

**Cosa vedi nell'app**
- Le tre tabelle, la curva, il calendario.

**Se qualcosa va storto**
- Database dello storico non aggiornato: al posto del codice d'errore compare «storico Mike: applica
  migrations/mike_history_v2.sql (...)».
- Il testo alternativo «P&L realizzato = trade REGOLATI nel giorno» non puo' mai comparire (vedi
  «Punti da decidere» n. 16).
- Paper o live: MAI sommati. Per vedere l'altra modalita' bisogna passare il toggle all'altra
  modalita' (lo Storico non ha un filtro suo).

**Per il tecnico**
- E-24 `components/mike/MikeEventPnlTable.tsx`, `EquityCard`, `pages/Mike.tsx:655-683`,
  `lib/mike.ts::groupMikeTrades,groupMikeTradesByEvent,mikeEquitySeries`, `MIKE_TRADES_LIMIT`=500.
- E-25 `pages/Mike.tsx:685-720`, `fasePerCiclo,MIKE_RUOLI_APERTURA_PRE,MIKE_RUOLI_APERTURA_LIVE`.
- E-27 `components/trading/TradingHistory.tsx`, `pages/Mike.tsx:742-750`,
  `mikeHistoryErrorMessage,withMikeHistoryError`.
- E-42 tabella `mike_trades` (`pnl` netto; `pnl_betfair` reale da Betfair, 24/09).
- E-49 `get_mike_trades(p_limit)` (`mike_bot.sql:286-302`): funzione di ripiego, non usata dalla
  pagina.
- E-51 `mike_aggregates_sql(p_mode)`/`get_mike_aggregates` (`mike_aggregati_per_modalita_2026-09-13
  .sql`): `realized_*`, `open_liability`, `liability_source`, `liability_stale` (60 s), `won/lost`.
- E-52 `get_mike_daily(p_from,p_to,p_mode)`/`get_mike_day_trades(p_day,p_mode)` su
  `trading_daily_history`/`trading_day_trades` (`mike_history_v2.sql`,
  `mike_storico_per_modalita_2026-09-14.sql` vigente), `window_clamped`, giorno per `placed`.

---

## Cosa Mike fa e tu NON vedi o NON puoi comandare dall'app

**Cosa fa**
- Tutti i 106 parametri di strategia che Mike usa sono nel pannello: nessuno e' nascosto.
- Restano fuori dall'app, e si cambiano solo nel file di impostazioni del PC (`.env`) con il
  riavvio, oppure non si cambiano affatto:
  1. l'interruttore di sicurezza che permette o vieta a Mike gli ordini veri (lo vedi solo come
     avviso ambra, riquadro 02; non lo comandi);
  2. la porta che garantisce che giri un solo Mike alla volta (di serie 47319);
  3. se in live Mike manda gli ordini tramite la coda ordini di flumine invece che direttamente (di
     serie no);
  4. da quante ore prima del fischio lo scanner comune legge i mercati Over/Under (di serie 1 ora):
     se non combacia con il parametro di Mike «ore prima del fischio», Mike scrive un avviso
     nell'Attivita';
  5. l'etichetta «mike» con cui Betfair marca gli ordini di Mike (fissa);
  6. i numeri di selezione attesi per Under 3.5 e Over 4.5 (usati solo dai test);
  7. alcuni tempi interni che la Costituzione chiama «non modificabili dall'app» (attesa massima del
     regolamento, memoria dei totali, numero massimo di partite seguite dallo scanner): non
     verificati nel codice del motore da chi ha scritto l'inventario.
- Il meccanismo «se chiudo io fuori dall'app, Mike se ne accorge» per Mike sta dentro il motore
  (righe «posizione di conto» nell'Attivita'), non nell'app.

**Quando**
- Sempre: queste cose non hanno un pulsante.

**Numeri**
- Porta di istanza unica 47319; ore dello scanner 1; coda flumine spenta (0).

**Esempio con le cifre**
- Metti LIVE e Avvia, ma l'interruttore di sicurezza nel `.env` e' spento: compare «Modalita' LIVE, ma
  il processo NON e' abilitato a piazzare ordini reali.» e nessun euro vero parte finche' non lo
  accende chi gestisce il PC e riavvia l'app.

**Cosa vedi nell'app**
- Solo l'avviso ambra del punto 1 e l'eventuale avviso nell'Attivita' del punto 4.

**Se qualcosa va storto**
- Un valore del `.env` sbagliato non si corregge dall'app: serve modificarlo e riavviare.

**Per il tecnico**
- `MIKE_LIVE_ENABLED`, `MIKE_LOCK_PORT`=47319, `MIKE_USE_FLUMINE_QUEUE`=0, `SAFE_PRE_KO_OU_HOURS`=1
  (avviso `config_warn`), `CUSTOMER_STRATEGY_REF="mike"`, `EXPECTED_SEL` (Under 3.5=1222344),
  `_SETTLE_MAX_WAIT_S`, `db._TOTALS_TTL_S`, `scanner.MIKE_MAX_FOLLOWED`, `_MIKE_FOLLOWED_TTL_S`;
  `service._sorveglia_posizione_di_conto`. `config.BACKEND_ONLY_PARAMS` vuota.

---

## Tabella dei parametri (tutti i 106, gruppo per gruppo)

Valori di serie e limiti come nel pannello. La colonna «nome interno» serve solo al tecnico.

**Generale**
| cosa regola | di serie | limiti | nome interno |
|---|---|---|---|
| importo di ogni puntata d'ingresso Under 3.5 | 10,00 € | 0,50-500 € | `stake` |
| commissione Betfair | 5 % | 0-20 % | `commission_pct` |
| da quante ore prima del fischio Mike lavora la partita | 1 ora | 0,25-12 ore | `entry_hours_before_ko` |
| competizioni ammesse (vuoto = tutte) | vuoto | testo | `competition_filter` |
| tempo minimo fra due decisioni sulla stessa partita | 500 ms | 100-5000 ms | `decide_min_interval_ms` |
| eta' massima della riga del feed per guardare | 45 s | 3-180 s | `feed_max_age_s` |
| riga vecchia ma scanner vivo: prezzo ancora buono fino a | 75 s | 10-300 s | `scanner_alive_max_s` |
| oltre questa eta' il book conta come assente | 90 s | 5-600 s | `book_seen_max_s` |
| eta' massima per fare un ordine o chiudere a mano | 20 s | 3-120 s | `order_max_age_s` |
| oltre, si ordina solo se lo scanner ha battuto entro | 30 s | 5-120 s | `order_scanner_max_s` |
| LIVE: uscita appoggiata sul book (spento = a mercato, strategia diversa dal paper) | acceso | si'/no | `live_resting_enabled` |

**Pre-match**
| cosa regola | di serie | limiti | nome interno |
|---|---|---|---|
| ingressi prima del fischio | acceso | si'/no | `pre_enabled` |
| quota minima d'ingresso Under 3.5 | 1,30 | 1,01-20 | `pre_entry_price_min` |
| quota massima d'ingresso | 3,00 | 1,01-20 | `pre_entry_price_max` |
| disponibilita' minima al miglior prezzo, in volte lo stake | 1,0 | 0,5-5 | `pre_min_back_size_factor` |
| distanza massima punta/banca | 6 tick | 1-20 | `pre_max_spread_ticks` |
| tick del green-up | 2 tick | 1-10 | `pre_green_ticks` |
| uscita: appoggiata subito sul book oppure al miglior prezzo | appoggiata | appoggiata/al best | `pre_exit_mode` |
| vita dell'ordine d'ingresso non abbinato | 60 s | 5-3600 s | `pre_entry_ttl_s` |
| giri massimi per partita | 10 | 0-100 | `pre_max_cycles` |
| pausa dopo un green prima del giro dopo | 60 s | 0-3600 s | `pre_reentry_cooldown_s` |
| minuti prima del fischio per l'ultimo ingresso | 10 min | 1-120 min | `pre_last_entry_min` |
| l'ultimo ingresso resta valido in gioco | acceso | si'/no | `last_entry_persist` |
| ultimo ingresso N tick sopra il best (0 = al best) | 0 tick | 0-3 | `last_entry_ticks_above` |
| veto sulla probabilita' calibrata dell'Under 3.5 all'ultimo ingresso | acceso | si'/no | `veto_p_under35_cal` |
| probabilita' minima a quota 1,30 | 0,807 | 0-1 | `veto_p_under35_soglia_130` |
| probabilita' minima a quota 1,50 | 0,684 | 0-1 | `veto_p_under35_soglia_150` |
| probabilita' minima a quota 2,00 | 0,514 | 0-1 | `veto_p_under35_soglia_200` |
| probabilita' minima a quota 2,50 | 0,385 | 0-1 | `veto_p_under35_soglia_250` |
| probabilita' minima a quota 3,00 | 0,275 | 0-1 | `veto_p_under35_soglia_300` |
| ritiro del residuo rimasto valido dopo il fischio | 120 s | 0-900 s | `cancel_unmatched_after_ko_s` |

**Dal fischio d'inizio**
| cosa regola | di serie | limiti | nome interno |
|---|---|---|---|
| prova a uscire in profitto al fischio | acceso | si'/no | `ko_green_enabled` |
| uscita N tick sotto l'ingresso | 2 tick | 1-10 | `ko_green_ticks` |
| finestra dell'uscita dal fischio | 180 s | 0-900 s | `ko_green_window_s` |
| SENZA EFFETTO dal 16/09 | 5 s | 1-60 s | `ko_green_retry_s` |
| seconda puntata dopo un gol precoce | acceso | si'/no | `second_entry_enabled` |
| seconda puntata in % dello stake | 50 % | 0-200 % | `second_entry_stake_pct` |
| prima parte di copertura dopo il gol, dopo | 120 s | 0-900 s | `early_goal_cover_delay_s` |
| quota della copertura nella prima parte | 50 % | 0-100 % | `early_goal_cover_pct` |
| seconda parte, dopo l'abbinamento della prima | 180 s | 0-900 s | `early_goal_cover2_delay_s` |

**Copertura Over 4.5**
| cosa regola | di serie | limiti | nome interno |
|---|---|---|---|
| copertura (spento = Under scoperto in gioco) | acceso | si'/no | `cover_enabled` |
| fattore di profitto con 5+ gol (1,2 = +20 % dello stake Under) | 1,2 | 1-3 | `cover_profit_factor` |
| quando coprire | auto | auto/subito/attesa | `cover_policy` |
| attende solo se la probabilita' di gol in 3 minuti e' al massimo | 0,06 | 0-1 | `cover_wait_hazard_max` |
| attesa massima | 10 min | 0-45 min | `cover_wait_max_min` |
| attende solo se la probabilita' di 4 gol di mercato e' al massimo | 0,16 | 0-1 | `cover_wait_p4_max` |
| copre subito se la quota Over e' gia' almeno | 7,0 | 1,01-50 | `cover_good_price` |
| attende solo se il risparmio atteso e' almeno | 8 % | 0-100 % | `cover_wait_min_gain_pct` |
| orizzonte della stima del risparmio | 5 min | 1-20 min | `cover_wait_step_min` |
| riprezzo dopo un gol | 45 s | 0-300 s | `cover_postgoal_delay_s` |
| oltre questi gol nessuna copertura nuova | 2 gol | 0-4 | `cover_max_goals` |
| arrotondamento senza importi esatti | per eccesso | eccesso/difetto/vicino | `cover_rounding` |
| sovracopertura massima | 30 % | 0-200 % | `cover_max_overshoot_pct` |
| importi esatti al centesimo | acceso | si'/no | `exact_sizes` |
| rifiuti uguali di fila prima di fermare la copertura | 3 | 1-20 | `cover_rifiuti_max` |
| attesa minima fra due tentativi | 15 s | 1-300 s | `cover_retry_min_s` |
| copertura N tick sotto il best | 2 tick | 0-6 | `cover_place_at_ticks` |

**Cash-out globale**
| cosa regola | di serie | limiti | nome interno |
|---|---|---|---|
| soglia di chiusura automatica piena | 5 % | 0,5-50 % | `cashout_profit_pct` |
| base: stake Under + copertura, oppure solo stake Under | totale | totale/Under | `cashout_base` |
| chiusura N tick oltre il best | 0 tick | 0-3 | `cashout_place_at_ticks` |
| cash out anticipato | acceso | si'/no | `cashout_smart_enabled` |
| profitto minimo per chiudere prima | 2 % | 0-50 % | `cashout_smart_min_pct` |
| «a un passo dalla soglia» | 2 punti | 0-50 | `cashout_smart_tolerance_pct` |
| fase calda: probabilita' di gol in 3 minuti | 0,10 | 0-1 | `cashout_smart_hazard_hot` |
| fase calda: pressione | 1,15 | 1-1,25 | `cashout_smart_pressure_hot` |
| punteggio caldo | 3 gol | 0-8 | `cashout_smart_goals_hot` |
| margine per chiudere se aspettare vale meno | 1 punto | 0-50 | `cashout_smart_ev_margin_pct` |
| riprezzo del residuo di chiusura | 10 s | 1-600 s | `close_retry_s` |
| tentativi massimi di chiusura | 20 | 1-100 | `close_max_attempts` |

**Uscite HT / 2T**
| cosa regola | di serie | limiti | nome interno |
|---|---|---|---|
| uscite automatiche (spento = proposte da approvare) | SPENTO | si'/no | `uscite_automatiche` |
| uscita in perdita a fine primo tempo | acceso | si'/no | `ht_loss_exit_enabled` |
| perdita tollerata (regola fissa) | 25 % | 0-100 % | `ht_loss_pct` |
| modo: a modello o regola fissa | a modello | modello/fissa | `loss_exit_mode` |
| premio al rischio sui 4 gol | 10 % | 0-300 % | `loss_exit_risk_premium_pct` |
| usa la stima piu' pessimista della probabilita' di 4 gol | acceso | si'/no | `loss_exit_p4_prudent` |
| tetto «non rendere definitivo oltre» (0 = spento) | 0 % | 0-100 % | `loss_exit_max_pct` |
| casi minimi della tabella storica intervallo→fine | 200 | 20-5000 | `loss_exit_emp_min_n` |
| gol minimi per l'uscita all'intervallo | 3 | 0-8 | `ht_loss_goals_min` |
| gol massimi | 4 | 0-8 | `ht_loss_goals_max` |
| stessa regola nel secondo tempo | acceso | si'/no | `h2_loss_exit_enabled` |
| perdita tollerata nel secondo tempo | 25 % | 0-100 % | `h2_loss_pct` |
| inizio finestra secondo tempo | 46′ | 45-100 | `h2_loss_from_min` |
| fine finestra | 85′ | 45-100 | `h2_loss_to_min` |

**Re-ingresso (gol + 3.5)**
| cosa regola | di serie | limiti | nome interno |
|---|---|---|---|
| re-ingresso Under 4.5 dopo un gol e una chiusura in profitto | acceso | si'/no | `reentry_enabled` |
| tick del green del re-ingresso | 2 tick | 1-10 | `reentry_green_ticks` |
| gol massimi per rientrare | 1 | 0-1 | `reentry_max_goals` |
| entro quale minuto | 45′ | 0-100 | `reentry_until_min` |
| chiusura forzata del re-ingresso (0 = mai) | 0 | 0-100 | `reentry_exit_until_min` |
| rientra solo se la quota supera il primo ingresso | acceso | si'/no | `reentry_price_min_over_entry` |
| tiene se in perdita (solo con chiusura forzata) | spento | si'/no | `reentry_hold_if_loss` |

**Rischio**
| cosa regola | di serie | limiti | nome interno |
|---|---|---|---|
| intervallo fra due letture a mercato chiuso (minimo reale 5 s) | 60 s | 0-600 s | `settle_confirm_s` |
| partite con posizione contemporanee | 10 | 1-90 | `max_open_matches` |
| stop giornaliero (0 = spento) | 50 € | 0-100.000 € | `daily_loss_stop` |
| capitale massimo per partita (0 = spento) | 0 € | 0-100.000 € | `max_liability_per_match` |
| tetto di perdita per partita: oltre, chiusura forzata | 100 % | 0-500 % | `event_loss_cap_pct` |
| intervallo minimo fra righe ripetute nell'Attivita' | 300 s | 10-3600 s | `skip_log_interval_s` |
| rilettura del feed | 4 s | 0-30 s | `feed_cache_s` |
| rilettura della lista partite | 60 s | 0-600 s | `events_reload_s` |
| ricalcolo degli aggregati | 20 s | 0-300 s | `aggregates_cache_s` |
| riparazione ordini/righe | 30 s | 0-600 s | `reconcile_every_s` |
| giro a riposo (nessuna partita in gioco) | 5 s | 1-60 s | `idle_cycle_s` |
| ripubblica una partita attiva ogni | 5 s | 0-120 s | `publish_heartbeat_s` |
| ripubblica una partita a riposo ogni | 60 s | 0-600 s | `publish_idle_heartbeat_s` |
| scrive tutte le partite in un colpo per giro | acceso | si'/no | `events_batch_write` |
| riscrive le statistiche di testata ogni | 10 s | 0-300 s | `stats_min_s` |
| scrive il battito ogni | 20 s | 0-300 s | `heartbeat_min_s` |

La modalita' paper/live NON e' un parametro: si cambia solo dal toggle (riquadro 02).

---

## Frecce

- Pagina di Mike -> Paper o live: «scegli»: premi PAPER (subito) o LIVE (conferma).
- Paper o live -> Parametri: «controlli»: apri il pannello prima di accendere.
- Parametri -> Uscite: l'interruttore «Uscite automatiche» e' dentro il pannello.
- Uscite -> Avvia o Ferma: con i valori a posto premi Avvia.
- Avvia o Ferma -> Mike legge: «acceso»: la riga di stato dice acceso; Mike la legge al giro dopo,
  di solito entro 2 secondi.
- Mike legge -> Storico e conti: «regolata»: quando il mercato chiude, il risultato va nei conti
  della sua modalita'.
- Pagina di Mike -> Scheda partita: «Partite»: linguetta Partite, una scheda per partita.
- Scheda partita -> Proposta uscita: «propone»: solo con le uscite manuali e Mike che vuole uscire.
- Proposta uscita -> Cash out, Chiudi: «oppure»: invece di approvare chiudi tu tutta la partita.
- Cash out, Chiudi -> Salta, Riprendi: «no rientro»: dopo una tua chiusura prima del fischio compare
  «NESSUN RIENTRO»; «Riprendi» lo toglie.
- Salta, Riprendi -> Richiesta: «scrive»: OGNI pulsante della scheda (approva, Cash out, Chiudi,
  Annulla ordini, Salta, Riprendi) scrive una richiesta nella coda. Non disegnate per non incrociare
  le linee: Proposta -> Richiesta e Cash out, Chiudi -> Richiesta.
- Richiesta -> Mike legge: «giro dopo»: di solito entro 2 secondi; poi lo schermo si aggiorna entro
  1,5 secondi.
- Non disegnata: Mike legge -> Pagina e Scheda: Mike riscrive partite, ordini, attivita' ed esiti; la
  pagina li mostra (1,5 s dopo, al massimo 15 s).

---

## Punti da decidere

Differenze dalla Costituzione (`Betfair/mike/COSTITUZIONE_MIKE.md`, datata 12/09/2026):

1. **Parametri: la Costituzione ne conta 72, oggi sono 106.** Nati dopo: tutto il gruppo «Dal fischio
   d'inizio» (9, del 13/09), il veto sulla probabilita' dell'Under 3.5 (6, del 25/09), «Uscite
   automatiche» (25/09), i freni sui rifiuti di copertura (17/09), «copertura N tick sotto il best»
   (12/09 sera) e 15 tempi di cadenza e carico che la Costituzione chiama «costanti non modificabili
   dall'app». Esempio: il battito era fisso a 10 s, oggi e' un parametro di serie a 20 s.
2. **Fasi e ruoli: la Costituzione dice 19 fasi e 9 ruoli, oggi sono 21 e 11** («uscita al fischio in
   corso», «gol precoce, seconda puntata»; ruoli «uscita al fischio», «seconda puntata»), nati il
   13/09.
3. **Linguette: la Costituzione ne descrive 5 (Partite, Trade, Attivita', Regolate, Storico), oggi
   sono 6.** «Trade» si chiama «Operazioni»; «Regolate» non c'e' piu'; ci sono «Risultati
   Pre-Match» e «Risultati Live».
4. **Doppia conferma in live: oggi scade da sola dopo 10 secondi per Cash out e per Chiudi a
   mercato.** La Costituzione non lo descrive (dettaglio in piu', non una contraddizione).
5. **La Costituzione non nomina l'interruttore «Uscite automatiche»** (nato il 25/09). Il suo §3 dice
   ancora che le uscite discrezionali sono sempre automatiche: oggi, di serie, sono proposte da
   approvare.
6. **I numeri dei test dell'app e della certificazione (128+10) sono fermi al 12/09**: non ricontati.

Cose strane:

7. **Due controlli del database non aggiornati per 12 giorni** dopo le due fasi e i due ruoli nuovi:
   il database rifiutava quelle scritture, la finestra dell'uscita al fischio non scadeva mai e la
   partita restava scoperta fino alla fine. «Su 2000 righe di errore lette dal registro attivita',
   2000 sono rifiuti di questo vincolo.» Oggi corretto; il sintomo si vedeva nella linguetta
   Attivita'.
8. **Il commento del programmatore sul veto dell'Under 3.5 dice «PREPARATO, SPENTO»**, ma il valore
   vero e l'aiuto nel pannello dicono acceso. Vale acceso: il commento e' un residuo.
9. **Due costanti separate per la scadenza di 10 secondi** di Cash out e Chiudi a mercato: se un
   giorno se ne cambia una sola, i due pulsanti avranno conferme di durata diversa senza che
   nessuno l'abbia deciso.
10. **La «pausa fra due tentativi dell'uscita al fischio» e' nel pannello ma non fa nulla dal 16/09.** L'aiuto lo dice, ma il campo si
    puo' ancora cambiare.
11. **Una riga d'Attivita' di un tipo nuovo, senza i campi previsti, mostrerebbe testo tecnico
    grezzo** (troncato a 140 caratteri) invece di una frase italiana. Oggi non succede con i tipi
    conosciuti.
12. **Accendere Mike non manda i parametri** (Omega li manda). Il database pero' conserva quelli
    esistenti: non e' un difetto, e' un'asimmetria fra i due bot.
13. **Refuso «mibeParams»** in Control Room: innocuo, solo un nome.
14. **Il controllo comune «se chiudo io fuori dall'app» copre Omega e Safe ma non Mike**, per scelta
    tua del 16/09: Mike ha un meccanismo suo nel motore. Due soluzioni diverse per lo stesso
    problema, non un buco.
15. **L'interruttore delle uscite per Mike non rilegge i parametri dal database prima di scrivere**
    (Safe si', dal 18/09). Due clic ravvicinati potrebbero «mangiarsi» a vicenda. Nessun caso visto
    su Mike.
16. **La frase «P&L realizzato = trade REGOLATI nel giorno» non puo' mai comparire** nello Storico:
    la scelta fra le due frasi restituisce sempre «piazzati».

Altri punti emersi nelle schede:

17. L'avviso «senza battito» compare due volte nella stessa riga fissa: lasciato cosi' per non rompere
    un test di un'altra pagina.
18. La conferma LIVE del toggle non decade se nel frattempo cambiano le condizioni (Mike non usa il
    meccanismo di decadenza che il componente comune avrebbe).
19. Il volume del mercato nel feed arriva sempre 0: la scheda scrive «non pubblicato».
20. Lo Storico di Mike non ha un filtro paper/live suo: mostra sempre la modalita' con cui Mike gira
    ora.

---

## Punti non chiariti

- Cosa fa Mike, lato suo, se al giro dopo non raggiunge il database o Betfair: non e' nell'inventario
  E (area schermate); vedi i capitoli 7 e 9.
- Se la pagina di Mike, come la Control Room, «sveglia» Mike sul canale locale dopo ogni clic:
  l'inventario lo dice solo per la Control Room.
- Se la correzione del 14/09 allo Storico (`mike_storico_per_modalita_fix_alias_2026-09-14.sql`) sia
  dentro il file letto o vada applicata a parte, e se sia applicata sul database: non verificato.
- I componenti comuni sotto Operazioni, Storico e curva (tabella, calendario, pannello, dettaglio,
  curva) e lo stato in chiaro degli ordini sul book sono descritti dal punto d'uso, non letti riga
  per riga.
- Le regole di accesso complete del database sono state lette solo in parte (ricerca su «mike»).
- Il testo esatto della conferma per passare le uscite ad automatiche, e se passare a manuali chieda
  conferma: l'inventario dice solo «stessa conferma» del componente comune.

---

## Conto delle 52 schede dell'inventario E

- In questo file (13a): 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21,
  22, 23, 24, 25, 26, 27, 28 (con 28-bis), 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52.
- In `13b_control_room.schede.md`: 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39.
- **Rimaste fuori: nessuna.**
