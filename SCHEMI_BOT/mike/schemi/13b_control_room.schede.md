# Mike - Capitolo 13b: Mike nella Control Room (schede)

Schema: `13b_control_room.html` (sorgente `13b_control_room.workflow.json`).
Prima parte del capitolo: `13a_pagina_di_mike.schede.md` (la pagina propria di Mike, la tabella
completa dei parametri, la scheda «Cosa Mike fa e tu NON vedi», tutti i «Punti da decidere»).
Fonte dei fatti: `SCHEMI_BOT/mike/inventario/E_schermate_e_pulsanti.md` (schede E-n).

**Schede dell'inventario E usate in questo file (numeri):** 29, 30, 31, 32, 33, 34, 35, 36, 37, 38,
39; richiamate: 23, 28, 45, 46, 47, 50 (spiegate per intero in 13a).

Come si legge: ogni riquadro dello schema ha un numero (01-12) scritto in alto. La scheda con lo
stesso numero lo spiega. Le parole fra «» sono i testi che leggi nell'app.

La Control Room e' il banco comune di tutti i bot. Mike ci compare in quattro punti: una riga nella
plancia «Comando dei bot», un riquadro dentro la scheda di ogni partita che segue, il pulsante
«Chiudi» sulle sue righe, e la lista «Posizioni chiuse». **Anche qui l'app scrive e Mike legge al
giro dopo.**

---

## 01 - Ordini reali («OFF, PAPER, LIVE»)

**Cosa fa**
- Un interruttore unico per TUTTI i bot, Mike compreso, con tre posizioni: OFF (nessun ordine vero da
  nessun bot), PAPER (ordini simulati), LIVE (ordini veri su Betfair).
- Mostra il modo EFFETTIVO: il piu' prudente fra il tetto scritto nel file di impostazioni del PC
  (`.env`) e la scelta fatta qui. Dice anche da dove arriva il dato (canale del programma calcio o
  database), chi l'ha cambiato e quando.

**Quando**
- «off» e «paper»: un clic.
- «live»: doppia conferma. Il primo clic arma; per 0,4 secondi il pulsante di conferma resta
  bloccato (contro il doppio clic involontario); poi compare «confermi? ordini reali su Betfair» da
  premere.
- LIVE si puo' scegliere solo se il tetto del `.env` e' LIVE; altrimenti il pulsante e' spento col
  motivo.

**Numeri**
- Blocco contro il doppio clic: 0,4 secondi. Rilettura di sicurezza: ogni 30 secondi. Rilettura
  forzata dal canale: al massimo ogni 2 secondi.

**Esempio con le cifre**
- Il `.env` ha tetto PAPER. Scegli LIVE qui: il modo effettivo resta PAPER e un avviso ambra dice
  «il tetto si alza solo dal .env, con il riavvio». Mike, anche in live, non muove un euro vero.

**Cosa vedi nell'app**
- La riga «Ordini reali» subito sopra l'elenco dei bot.

**Se qualcosa va storto**
- Scrittura fallita: resta il modo di prima.
- Paper o live: e' il tetto sopra ogni bot. Mike in live con questo interruttore su PAPER non fa
  ordini veri.

**Per il tecnico**
- E-30 `components/controlroom/RigaOrdiniReali.tsx` (comune); scrittura `set_live_order_mode`
  (solo proprietario), lettura `get_live_settings`.

---

## 02 - Freno («stop aperture»)

**Cosa fa**
- Un freno unico per tutti i bot. Tirato: nessun bot apre nuove posizioni, ne' in live ne' in paper.
  Le chiusure restano sempre servite.

**Quando**
- «tira il freno»: UN clic, nessuna domanda (un freno d'emergenza non chiede conferme).
- «rilascia»: DUE conferme in fila, «confermi? i bot accesi tornano ad aprire» poi «si', rilascia
  il freno», ciascuna col blocco di 0,4 secondi.
- Se il freno e' tirato anche dal file di impostazioni del programma calcio, un avviso dice che da
  qui non si puo' togliere.

**Numeri**
- Blocco contro il doppio clic: 0,4 secondi. Rilettura di sicurezza: ogni 30 secondi.

**Esempio con le cifre**
- Vedi un comportamento strano su piu' bot insieme e tiri il freno: Mike non apre piu' nessun
  ingresso da 10,00 €, ma la partita coperta che ha in mano continua a essere sorvegliata e chiusa.

**Cosa vedi nell'app**
- La riga «Freno» subito sotto «Ordini reali».

**Se qualcosa va storto**
- Scrittura fallita: il freno resta come prima. Tiralo di nuovo e controlla la riga.
- Paper o live: vale per tutte e due.

**Per il tecnico**
- E-31 `components/controlroom/RigaFreno.tsx` (comune); scrittura `set_live_kill_switch` (solo
  proprietario).

---

## 03 - Riga di Mike («stato, P&L, stake»)

**Cosa fa**
- Nella plancia «Comando dei bot», una riga «Mike» con:
  - stato in parole: «in esecuzione», «sta fermandosi», «fermo», «in errore»;
  - «prova» o «soldi veri» (oppure «modalita' n/d» se non dichiarata);
  - da quanto e' arrivato l'ultimo messaggio dal canale locale;
  - P&L di oggi nella modalita' attiva;
  - l'interruttore delle uscite (riquadro 05);
  - il campo «stake Under 3.5» col valore attuale (si cambia da qui);
  - i pulsanti di comando (riquadro 04) e «Parametri» (riquadro 06).
- Riga ambra se Mike e' acceso ma non apre posizioni nuove, col motivo scritto da Mike (es. tetto
  delle partite raggiunto, «N/M»).
- Riga «fermato all'avvio dell'app: attivazione manuale richiesta» se Mike e' stato fermato
  all'apertura dell'app.

**Quando**
- Sempre visibile; si aggiorna da sola.

**Numeri**
- Tetto delle partite con posizione: parametro, di serie 10.

**Esempio con le cifre**
- «Mike · in esecuzione · prova · 1 s · +2,40 € · stake Under 3.5 10,00 €». Con 10 partite gia'
  aperte su 10: riga ambra «tetto partite raggiunto 10/10».
- Cambi lo stake da 10,00 a 12,00 €: al giro dopo il prossimo ingresso punta 12,00 €.

**Cosa vedi nell'app**
- La riga descritta nella card «Comando dei bot».

**Se qualcosa va storto**
- Se l'app non ha ancora letto i parametri di Mike, non scrive lo stake (scriverlo senza averli
  letti rimetterebbe tutti gli altri ai valori di serie).
- Paper o live: il P&L mostrato e' della sola modalita' attiva.

**Per il tecnico**
- E-29 `components/controlroom/PannelloBot.tsx` (489-846), `lib/interruttori.ts::INTERRUTTORI`
  (146-149, id `'mike'`), `cambiaImporto` → `mike_update_params` (E-47), protezione `paramsLetti`.

---

## 04 - Avvia, Ferma («soldi veri: 2 clic»)

**Cosa fa**
- Mike SPENTO: due pulsanti.
  - «avvia in prova»: un clic, nessuna conferma.
  - «avvia con soldi veri» (bordo rosso): un clic arma; per 0,4 secondi la conferma e' bloccata;
    poi «confermi? ordini reali su Betfair» da premere.
- Mike ACCESO:
  - «ferma»: un clic, nessuna conferma. Nota sotto: «ferma le aperture, non le uscite»: le posizioni
    aperte restano sorvegliate;
  - in prova: «passa a soldi veri», stessa doppia conferma da 0,4 secondi;
  - in live: «passa a prova», un clic, nessuna conferma.
- Mentre il comando viaggia: «comando inviato — in attesa del servizio (tipica ~2 s)». Oltre 10
  secondi senza conferma, un avviso ambra dice che Mike potrebbe essere lento o che il comando non e'
  arrivato.
- Accendere non azzera i parametri: restano quelli salvati. Cambiare modalita' a bot acceso non lo
  riaccende: cambia solo la modalita'.

**Quando**
- Dopo la scrittura riuscita l'app «sveglia» Mike sul canale locale del PC, cosi' rilegge subito
  invece di aspettare il suo giro.

**Numeri**
- Blocco contro il doppio clic: 0,4 secondi. Giro tipico di Mike: 2 secondi. Avviso di lentezza: 3
  volte il giro tipico, minimo 10 secondi.

**Esempio con le cifre**
- Premi «avvia con soldi veri»: il pulsante diventa «confermi? ordini reali su Betfair», bloccato
  per 0,4 secondi, poi premibile. Confermi: Mike e' acceso in live. Il primo ingresso punta 10,00 €
  veri sull'Under 3.5 a 1,50: +4,75 € netti con 0-3 gol, −10,00 € con 4 gol (salvo uscite e
  copertura).

**Cosa vedi nell'app**
- I pulsanti sulla riga di Mike e la scritta di attesa.

**Se qualcosa va storto**
- Nessuna conferma entro 10 secondi: avviso ambra. Controlla la salute di Mike (servizio acceso?).
- Paper o live: una partita gia' armata tiene la SUA modalita' finche' non si chiude, anche se
  cambi la modalita' qui.

**Per il tecnico**
- E-29 `lib/interruttori.ts::avviaBot,fermaBot,cambiaModalita` (860-1013); sveglia sul canale
  `ws://127.0.0.1:47333`.
- E-45 `mike_activate`, E-46 `mike_stop`, E-47 `mike_update_params(p_mode)`.

---

## 05 - Uscite («di serie manuali»)

**Cosa fa**
- Sulla riga di Mike c'e' lo stesso interruttore «Uscite automatiche» della pagina di Mike e del
  pannello Parametri: stesso testo, stessa conferma, stesso effetto (capitolo 13a, riquadro 04).
- Spento (di serie): Mike propone le uscite, tu le approvi (riquadro 09). Acceso: Mike esce da solo.
  Copertura, tetto di perdita e regolamento restano sempre automatici.
- L'app scrive SOLO questo interruttore dentro i parametri: tutti gli altri valori restano intatti.

**Quando**
- Passare ad automatiche chiede conferma. Mike lo legge al giro dopo (di solito 2 secondi; subito se
  l'app lo sveglia sul canale locale).

**Numeri**
- Di serie: spento.

**Esempio con le cifre**
- Accendi le uscite automatiche: la proposta «green-up pre-partita» su 10,00 € a 1,50 non compare
  piu'; al giro dopo Mike fa da solo la banca 2 tick sotto e blocca il profitto.

**Cosa vedi nell'app**
- L'interruttore sulla riga di Mike.

**Se qualcosa va storto**
- L'app scrive partendo dall'ultima copia dei parametri che ha in memoria, senza rileggerla (Safe
  invece la rilegge): vedi 13a, «Punti da decidere» n. 15.
- Paper o live: identico.

**Per il tecnico**
- E-29 / E-28: `components/controlroom/InterruttoreUscite.tsx`, `lib/interruttori.ts::cambiaUscite`
  → `mike_update_params` (chiave `uscite_automatiche`).

---

## 06 - Parametri («stesso pannello»)

**Cosa fa**
- Il pulsante «Parametri» sulla riga di Mike apre LO STESSO pannello della pagina di Mike (capitolo
  13a, riquadro 03): non e' una copia.
- Se la Control Room non ha ancora letto i parametri di Mike, al posto del pannello compare
  «Parametri non letti — bot Mike»: cosi' non si apre un pannello vuoto che salverebbe tutto ai
  valori di serie.

**Quando**
- «Salva parametri»: Mike li usa dal giro dopo, senza fermarsi.

**Numeri**
- Gli stessi 106 parametri (tabella completa in 13a).

**Esempio con le cifre**
- Da qui porti lo stop giornaliero da 50 € a 30 €: dopo −30,00 € nella giornata Mike smette di
  aprire e fa solo chiusure; la casella «P&L oggi» della pagina di Mike scrive «STOP giornaliero
  ATTIVO · solo chiusure».

**Cosa vedi nell'app**
- Il pannello laterale, identico a quello della pagina di Mike.

**Se qualcosa va storto**
- Parametri non letti: pannello non disponibile, niente da salvare per errore.
- Paper o live: nessuna differenza.

**Per il tecnico**
- E-32 `pages/ControlRoom.tsx:400-420` (variabile `mibeParams`, refuso innocuo), componente
  `MikeParamsSheet`; salva con `mike_update_params`.

---

## 07 - Mike legge («al giro dopo»)

**Cosa fa**
- Mike legge al suo giro la riga di stato (acceso, modalita', parametri, uscite) e le richieste in
  coda (approvazioni e «Chiudi»), ed esegue.
- Dopo un comando della plancia l'app lo sveglia sul canale locale: rilegge subito.
- Un'etichetta di diagnostica dice da dove arrivano le righe di Mike mostrate in Control Room: dal
  canale locale (diretto dal PC, piu' fresco) o dal database, con l'eta' del dato.

**Quando**
- Giro tipico: 2 secondi. Dopo una sveglia: subito.

**Numeri**
- Giro tipico 2 secondi; avviso di lentezza dopo 10 secondi.

**Esempio con le cifre**
- «Mike: canale · 2 s» oppure «Mike: db · 14 s».

**Cosa vedi nell'app**
- L'etichetta «fonte righe» nella riga di diagnostica; i risultati sulle schede delle partite.

**Se qualcosa va storto**
- Canale locale caduto: le righe arrivano dal database, un po' piu' vecchie; l'etichetta passa a
  «db».
- Mike fermo: i comandi restano in attesa; dopo 10 secondi avviso ambra sulla riga di Mike.
- Paper o live: identico.

**Per il tecnico**
- E-29 (sveglia, cadenza da `Betfair/mike/service.py`); E-38 `pages/ControlRoom.tsx:1005-1016`.

---

## 08 - Riquadro Mike («modello e cifre»)

**Cosa fa**
- Dentro la scheda di ogni partita seguita anche da Mike compare «Mike — modello e mercato su questa
  partita», in SOLA LETTURA:
  - freschezza del feed (verde fino a 5 s, ambra fino a 20 s, rosso oltre; «partita chiusa» grigio a
    partita finita, mai rosso);
  - probabilita' di esattamente 4 gol: da mercato, da modello, pre-partita;
  - gol attesi e la loro fonte («nessuna (bot cieco sul modello)» se manca);
  - quote Under 3.5 e Over 4.5 e volume;
  - quota d'ingresso, quota al fischio con lo scarto in tick, giri e giri chiusi;
  - liability, P&L bloccato, cash out (con «parziale» se il book non copre tutta la chiusura);
  - «se finisce con N gol», per tutta la partita.
- Monta anche la proposta d'uscita, se c'e' (riquadro 09).
- NON ha pulsanti di chiusura propri: da questa pagina si chiude solo col «Chiudi» della riga
  (riquadro 10).

**Quando**
- Solo nelle linguette «Live» e «Posizioni aperte» della Control Room. NON in «Pre-match».

**Numeri**
- Freschezza: 5 s e 20 s.

**Esempio con le cifre**
- «P(4 gol esatti) mercato 18,0% · modello 15,2% · gol attesi 1,40 · 1,10 (fonte statistiche
  partita)».

**Cosa vedi nell'app**
- Il riquadro dentro la scheda generica della partita.

**Se qualcosa va storto**
- Feed fermo: etichetta rossa. Modello assente: «nessuna (bot cieco sul modello)».
- Paper o live: calcoli identici.

**Per il tecnico**
- E-33 `components/controlroom/SchedaMike.tsx`; montaggio `pages/ControlRoom.tsx:1299,1396`
  (`mike={mikeEventi.get(event_id)}`).

---

## 09 - Proposta uscita («approvi: 1 clic»)

**Cosa fa**
- La STESSA proposta della pagina di Mike (capitolo 13a, riquadro 07), stesso pulsante, stesso
  comando: «Mike vorrebbe uscire: {tipo}», motivo, ordini proposti, «chiudendo ora» e «alla
  decisione», da quanti secondi, freschezza del feed, «approva uscita».
- Qui sta dentro il riquadro di Mike della scheda partita.

**Quando**
- Un clic, nessuna doppia conferma. «approvazione inviata: parte al prossimo giro del bot». La firma
  vale 120 secondi dal clic, per la stessa uscita.

**Numeri**
- Nessun tempo di conferma; firma 120 secondi.

**Esempio con le cifre**
- «Mike vorrebbe uscire: uscita al fischio — chiudendo ora +0,20 € · alla decisione +0,24 € · deciso
  4 s fa». Approvi: al giro dopo Mike banca e blocca circa +0,20 €.

**Cosa vedi nell'app**
- Il riquadro ambra, rosso se l'uscita e' in perdita.

**Se qualcosa va storto**
- Feed fermo o ignoto: pulsante spento («non si approva su prezzi vecchi»). Invio fallito:
  «approvazione non inviata: {motivo}».
- Paper o live: modalita' della partita.

**Per il tecnico**
- E-34 `components/controlroom/SchedaMike.tsx:115`, `PropostaUscitaMike.tsx`; E-50
  `mike_request('approva_uscita',...)`.

---

## 10 - Chiudi riga («tutta la partita»)

**Cosa fa**
- Nelle tabelle di posizioni e operazioni della Control Room ogni riga di Mike ha «Chiudi». **Per
  Mike chiude l'INTERA PARTITA** (ingresso, copertura, ordini vivi), non la sola riga. Il
  suggerimento lo dice: «Mike chiude l'intera posizione della PARTITA (ciclo: ingresso, copertura,
  ordini vivi), sull'abbinato, nella modalita' della partita».
- UN clic, nessuna doppia conferma nel pulsante (anche in live: diverso dalla pagina di Mike, vedi
  «Punti da decidere» n. 2).
- Accanto al pulsante, la fase: «richiesta inviata» → «presa in carico» (resta finche' Mike non ha
  finito di guidare la chiusura: per Mike «armato» non vuol dire ancora eseguito) → «eseguita»
  (quando la riga cambia davvero: coperta o regolata) oppure «rifiutata: {motivo}».

**Quando**
- Pulsante spento, col motivo, se: la riga e' gia' regolata, annullata o in errore (nessun
  pulsante); e' un ordine di chiusura («si chiude con la sua apertura»); la modalita' della riga non
  e' dichiarata («non si chiude alla cieca»); la riga e' «coperta per intero» o «in riconciliazione»;
  la partita della riga non e' nota («Mike chiude per partita»).
- Mike lo legge al giro dopo (di solito 2 secondi).

**Numeri**
- Senza esito finale entro 3 minuti (180 secondi): «esito ignoto» con «nessun esito dal bot da 3
  minuti: il servizio e' acceso? Controlla la riga prima di riprovare».

**Esempio con le cifre**
- Riga Mike «punta Under 3.5 10,00 € @1,50», partita coperta con 3,00 € sull'Over 4.5. Premi
  «Chiudi»: «presa in carico» mentre Mike ritira gli ordini sul book e chiude Under e Over nei giri
  seguenti; poi «eseguita». Se il netto era −1,20 €, quella perdita diventa definitiva (invece di
  rischiare i 4 gol).

**Cosa vedi nell'app**
- Il pulsante «Chiudi» e la fase accanto.

**Se qualcosa va storto**
- Mike spento o lento: dopo 3 minuti «esito ignoto». Non ripremere alla cieca: controlla la riga (e
  Betfair, in live).
- Paper o live: vale la modalita' DICHIARATA dalla riga; se non c'e', il comando non parte.

**Per il tecnico**
- E-35 `components/controlroom/chiudiRiga.ts` (97-125, 159-162, 194-196, 257-274),
  `BottoneChiudiRiga.tsx`; richiesta `mike_request('cashout',{event_id,trade_id,bot:'mike',mode})`
  (E-50); `phase:'armed'` non conta come eseguita.

---

## 11 - Avvisi e saldo («fonte, saldo»)

**Cosa fa**
- **Avviso arancione «Mike: uscita appoggiata SPENTA in live»**: compare quando il parametro «LIVE:
  uscita appoggiata attiva» e' spento. Testo: «In live l'uscita torna «a mercato»: Mike esegue una
  strategia diversa da quella provata in paper, e il ciclo che in demo chiude in profitto li' chiude
  in perdita.» Si risolve riaccendendo il parametro (riquadro 06).
- **Etichetta «fonte righe»**: canale o database, con l'eta' (riquadro 07).
- **Card «Saldo Betfair»** (comune a tutti i bot): il saldo del conto, aggiornato anche quando Mike
  piazza o chiude un ordine live (il canale locale di Mike avvisa dopo ogni movimento con soldi
  veri). Un pulsante a occhio nasconde il saldo; la scelta resta salvata nel browser.
- Tutto in sola lettura; questi avvisi sono SOLO in Control Room, non nella pagina di Mike.

**Quando**
- Automatico.

**Numeri**
- Saldo «stantio» oltre 120 secondi.

**Esempio con le cifre**
- Hai spento «uscita appoggiata» per una prova e te ne sei dimenticato: la card arancione resta
  finche' non lo riaccendi. In live il green-up che in paper chiudeva a +0,14 € (banca appoggiata 2
  tick sotto) viene fatto a mercato e puo' chiudere in perdita.
- Mike chiude in live con +0,42 €: il saldo Betfair si aggiorna subito dopo.

**Cosa vedi nell'app**
- La card arancione, l'etichetta di diagnostica, la card del saldo.

**Se qualcosa va storto**
- Saldo non aggiornato da oltre 120 secondi: segnato come vecchio.
- Paper o live: il saldo vero si muove solo con ordini live; l'avviso sull'uscita appoggiata
  riguarda solo il live.

**Per il tecnico**
- E-37 `pages/ControlRoom.tsx:672-683`, `useControlRoom.ts` (870-876, 3680)
  `leggiBool(mike?.control?.params,'live_resting_enabled')`.
- E-38 `pages/ControlRoom.tsx:1005-1016`.
- E-39 `components/controlroom/SaldoBetfairCard.tsx:31` (`CANALI_SALDO` include `'mike'`),
  `lib/saldoBetfair.ts`, porta 47333.

---

## 12 - Posizioni chiuse («filtro Mike»)

**Cosa fa**
- Nella lista «Posizioni chiuse» c'e' il filtro «Mike» (una voce sola, non divisa per sport).
- Raggruppa: giornata di regolamento → bot → partita → giro.
- Per ogni chiusura un'etichetta di certezza: «CHIUSA · CONFERMATA», «REGOLATA DAL MERCATO»,
  «PARZIALE · ESPOSIZIONE RESIDUA», «IN ATTESA DI ABBINAMENTO», «CHIUSURA FALLITA · ANCORA APERTA»,
  «NON VERIFICABILE».
- Lato «banca»/«punta», modalita' «veri»/«prova», e accanto a ogni cifra la sua fonte: «Betfair»
  (netto vero regolato da Betfair), «stimato» (calcolo di Mike), «prova».
- Sola lettura: nessun comando, si apre e chiude solo il dettaglio di ogni giro.

**Quando**
- Al clic sul filtro «Mike» o sfogliando le giornate.

**Numeri**
- Oltre 40 operazioni le partite partono chiuse, per velocita'.

**Esempio con le cifre**
- «Mike · 6 operazioni · 3 partite · +1,84 €»; dentro, «Inter - Milan · ciclo 1 · CHIUSA ·
  CONFERMATA · +0,14 € Betfair».

**Cosa vedi nell'app**
- Il blocco «Mike» nella lista, con partite e giri sotto.

**Se qualcosa va storto**
- «CHIUSURA FALLITA · ANCORA APERTA»: la posizione e' ancora esposta; va chiusa dalla riga
  (riquadro 10) o controllata su Betfair.
- Paper o live: filtro «veri»/«prova» separato in alto, MAI sommati. Attenzione: qui il giorno e'
  quello del regolamento; nello Storico della pagina di Mike e' quello del piazzamento (13a,
  riquadro 12).

**Per il tecnico**
- E-36 `components/controlroom/PosizioniChiuse.tsx` (69-76, 462-465); fonte `pnl_betfair` di
  `mike_trades` (E-42).

---

## Frecce

- Ordini reali -> Freno: «tetto»: prima il tetto OFF/PAPER/LIVE di tutta la piattaforma.
- Freno -> Riga di Mike: «rilasciato»: col freno tirato Mike non apre nulla.
- Riga di Mike -> Avvia, Ferma: i pulsanti stanno sulla riga.
- Avvia, Ferma -> Mike legge: «acceso»: scrive lo stato, sveglia Mike sul canale locale; lettura
  subito o entro 2 secondi.
- Mike legge -> Posizioni chiuse: «regolata»: a mercato chiuso il giro finisce nella lista.
- Uscite -> Parametri: «stesso»: lo stesso interruttore sta anche nel pannello.
- Uscite -> Mike legge: «scrive»: solo la chiave dell'interruttore; al giro dopo.
- Non disegnata: Parametri -> Mike legge: «Salva parametri», al giro dopo.
- Riga di Mike -> Riquadro Mike: «in gioco»: il riquadro compare nelle linguette Live e Posizioni
  aperte.
- Riquadro Mike -> Proposta uscita: «propone»: con uscite manuali e Mike che vuole uscire.
- Proposta uscita -> Chiudi riga: «oppure»: invece di approvare chiudi tu tutta la partita.
- Chiudi riga -> Mike legge: «scrive»: una richiesta di chiusura in coda; esito entro 3 minuti.
- Non disegnata: Proposta uscita -> Mike legge: «approva uscita», al giro dopo.
- Riquadro Mike -> Avvisi e saldo: «diagnostica»: avvisi di sola lettura.

---

## Punti da decidere

Tutte le differenze dalla Costituzione e le cose strane dell'inventario E sono elencate per intero
in `13a_pagina_di_mike.schede.md`, «Punti da decidere» (n. 1-20). Qui quelle che toccano la Control
Room, piu' due emerse in questo file:

1. (13a n. 13) Refuso «mibeParams» nel codice della Control Room: innocuo.
2. **Chiudi della riga senza doppia conferma, anche in live.** Nella pagina di Mike, Cash out e
   Chiudi a mercato in live chiedono due clic entro 10 secondi; il «Chiudi» della riga in Control
   Room chiude tutta la partita con UN clic. Stesso effetto sui soldi, protezione diversa.
3. (13a n. 15) L'interruttore delle uscite non rilegge i parametri prima di scrivere (Safe si').
4. (13a n. 14) Il controllo comune «se chiudo io fuori dall'app» non copre Mike: Mike ha il suo nel
   motore.
5. **Giorno diverso fra le due liste**: «Posizioni chiuse» raggruppa per giorno di regolamento, lo
   Storico di Mike per giorno di piazzamento. Una partita piazzata alle 23:50 e regolata dopo
   mezzanotte cade in due giorni diversi nelle due viste.
6. (13a n. 5) La Costituzione non nomina l'interruttore «Uscite automatiche», presente anche qui.

---

## Punti non chiariti

- Se la sveglia sul canale locale parta anche dopo «approva uscita» e dopo «Chiudi» (l'inventario la
  cita per i comandi della plancia).
- Il testo esatto della conferma per passare le uscite ad automatiche e se passare a manuali chieda
  conferma: l'inventario dice solo «stessa conferma» del componente comune.
- Cosa fa Mike, lato suo, se non raggiunge database o Betfair: fuori dall'inventario E (capitoli 7 e
  9).

---

## Conto delle schede dell'inventario E

- In questo file: 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39.
- Nel file 13a: 1-28 (con 28-bis), 40-52.
- **Rimaste fuori: nessuna.**
