# Riepilogo dei lavori del 28 e 29 settembre 2026

Scritto per l'utente, in parole semplici. Il dettaglio tecnico sta in `CRONOSTORIA.md` e nei referti
in `AUDIT_2026-09-28/`. Stato del codice: ramo `master`, pushato su GitHub.

## 1. Cosa vuol dire «certificato» in questo documento

Tre gradini, dal piu' debole al piu' forte:

1. **Test**: il codice passa i test automatici, e io ho rotto apposta il codice in piu' punti per
   controllare che i test se ne accorgano.
2. **Replay**: il bot vero ha rigiocato una partita registrata, ordine per ordine, e i controlli di
   condotta non hanno trovato violazioni. E' il gradino che chiamo «certificato».
3. **Paper dal vivo**: l'app accesa su partite vere con soldi finti. **Non e' ancora stato fatto per
   nessuna delle modifiche di questi due giorni.** E' la prova di oggi.

Un replay che finisce «OK» ma in cui il bot non ha fatto nessuna azione non prova niente: lo segno
come «non provato».

## 2. Stato bot per bot

| Bot | Replay | Si puo' accendere in paper |
|---|---|---|
| Mike | 15 scenari, 0 violazioni | si' |
| Omega | 13 scenari, 0 violazioni, stesso esito sui due trasporti | si' |
| Safe base, esatto, punta | 14 scenari ciascuno, 0 violazioni, stesso esito sui due trasporti | si' |
| Safe tennis | 14 scenari, 0 violazioni, stesso esito sui due trasporti | si' |
| Tennis pro | 6 scenari, 0 violazioni (anche in manuale e con firma) | si' |
| Tennis FLB | 6 scenari, 0 violazioni | si' |
| Scalper tennis | 6 scenari, 0 violazioni | si' |
| Tennis swing | 6 scenari «OK» ma 0 azioni | NO: non provato |
| Sniper | 2 scenari «OK» ma 0 azioni | NO: non provato |
| Scalper calcio | FALLITO: al fischio resta una posizione da 4,44 EUR e il bot la crede chiusa | NO |

## 3. Le migliorie, una per una

Per ognuna: cosa succedeva prima, cosa succede adesso, fino a quale gradino e' verificata.

### Soldi e ordini

| Miglioria | Prima | Adesso | Verificata |
|---|---|---|---|
| Pulsante uscite manuali/automatiche su OGNI bot | Solo Omega, Mike e Safe avevano qualcosa; tennis e scalper chiudevano da soli; dopo un riavvio la scelta non tornava a manuale | Ogni bot ha lo stesso pulsante; di serie e a ogni avvio e' su manuale; in manuale ogni uscita e' una proposta coi numeri che approvi tu | Replay, tranne scalper calcio e sniper |
| Una firma vale solo per cio' che hai visto | Una firma restava valida 2 minuti anche se la proposta spariva: poteva eseguire un'uscita diversa (approvavi uno stop a -1,88 e chiudeva a -6,50; approvavi un profitto e chiudeva in perdita) | La firma cade con la proposta, scade dopo 120 secondi, vale una volta sola | Test (li ho scritti io, erano rossi) e replay |
| Mike in paper sul motore vero | In paper Mike usava un simulatore suo, diverso dal live | Gli ordini paper passano dallo stesso motore del live | Replay |
| Freno delle coperture di Mike | Sul motore nuovo i rifiuti non venivano contati: la copertura rifiutata veniva riproposta senza fine (8 ordini invece di 2) | Il freno conta anche quei rifiuti e scatta | Replay |
| Freno generale sulle aperture paper di Mike | A freno tirato un'apertura paper partiva lo stesso verso il motore | Si ferma prima, come in live; le chiusure passano | Test e replay |
| Esito ignoto mai dato per annullato (Mike) | Se il motore rispondeva «errore» la gamba veniva data per annullata, ma l'ordine poteva esistere | Resta in riconciliazione finche' non c'e' un esito certo | Test e replay |
| Ordine orfano nel motore | Se il ritiro falliva, il motore abbandonava: poteva restare a mercato un ordine da 2,00 EUR senza nessuno a seguirlo | Ritenta finche' l'ordine e' confermato chiuso | Test e replay |
| Rifiuto non dovuto al mercato (Mike) | Un'apertura rifiutata per modo ordini spento o freno veniva riproposta a ogni giro: 254 righe di errore in una partita | Si dice una volta e riparte quando la causa sparisce | Test e replay |
| Chiusure esatte al centesimo nel tennis | Le coperture venivano gonfiate al gradino da 0,50 (2,02 diventava 2,50) | Importo esatto: parte diretta piu' resto con «piazza e riduci» | Replay su pro, FLB, scalper tennis |
| Tennis pro: chiusura al centesimo | Si dichiarava chiuso con fino a 2 centesimi di sbilancio | Continua a governare la posizione se un centesimo la sistema | Replay |
| Aperture tennis sotto il minimo | Venivano rifiutate | Portate al minimo accettato (2,00 back, 0,50 lay) e dichiarate nell'evento | Replay |
| Safe e Omega specchio del live | Col motore non raggiungibile il paper si inventava l'abbinamento | Senza motore l'ordine non e' eseguito, lo dice, e riparte quando il motore torna senza bruciare la partita | Replay |
| Omega: numeri separati per modalita' | Stop giornaliero e tetti sommavano soldi veri e finti | Ogni modalita' legge solo i suoi | Test e replay |
| Green-up di Omega | Dopo un green-up completo lo stato restava «in attesa» | Passa a «fatto» | Test |

### Dati e prezzi

| Miglioria | Prima | Adesso | Verificata |
|---|---|---|---|
| Flusso dei prezzi interrotto | I bot guardavano l'eta' della riga: se il punteggio si aggiornava i prezzi vecchi sembravano freschi | Se i prezzi non arrivano nessun bot apre; chiusure e protezioni usano la lettura di riserva; se manca anche quella, avviso critico ogni minuto | Test e replay (il replay non simula ancora un'interruzione vera) |
| Stream muto di runner e scalper | Nessun segnale | Il bot sa che lo stream tace; banner rosso su ladder e Segui Live; un tuo ordine di apertura appoggiato viene ritirato | Test |
| Partite terminate non piu' seguite | Restavano in elenco | Escono da sole, con doppia conferma e controllo dei soldi | Test |
| Capacita' dei mercati | Una connessione, circa 50 partite | Fino a 3 connessioni, circa 150 partite | Test |

### App, database, pagine

| Miglioria | Prima | Adesso | Verificata |
|---|---|---|---|
| Spegnimento ordinato dell'app | I processi venivano uccisi | Ogni servizio si ferma da solo; lo scalper chiude le posizioni prima di uscire | Test |
| Sorveglianza dei processi | Non tutti venivano riavviati se cadevano | Tutti | Test |
| Ogni bot e' indipendente | Avviare Safe tennis spegneva Safe calcio | Accendere un bot tocca solo quello | Test |
| Aggiornamento dati (errore 57014) | Andava in timeout | Lavora a blocchi che si adattano | Test, migrazione applicata |
| Atlante (errore HTTP 500) | Falliva su un salvataggio da 14 MB | Funzione dedicata | Test, migrazione applicata |
| Dati sporchi nel database | Righe rimaste appese | Ripulite | Verificato sul DB: 0 residui |
| Pagine | Giorno sbagliato, importi non in euro | Giorno di Roma, euro | Test |
| Test indipendenti dal PC | 111 test fallivano per via del file di configurazione | Non dipendono piu' da quello | Test |

## 4. Cosa NON e' certificato

- **Scalper calcio**: replay fallito, causa in ricerca.
- **Sniper e tennis swing**: nel replay non fanno mai un'azione, quindi non sono provati. Servono
  registrazioni in cui entrano.
- **11 campi delle pagine** che esistono solo con una partita in diretta.
- **146 controlli «dal vivo»** del registro: si possono fare solo con l'app accesa.
- **Flusso interrotto**: provato coi test, non ancora con un'interruzione simulata dentro il replay.
- **Mike, scenario coperture**: i due trasporti differiscono per una riga, per un limite del banco di
  replay (inietta il rifiuto solo su una strada).
- **Test mancanti** (il codice l'ho letto ed e' corretto, ma nessun test lo protegge): collegamento
  dell'arresto nel programma principale; nuovo tentativo di ritiro dell'ordine nel motore.
- **Tutto cio' che e' paper dal vivo**: e' la prova di oggi.

## 5. Errori miei in questi due giorni

- Ho integrato una consegna senza replay: e' entrata una regressione sullo scalper tennis (16.613
  azioni invece di 228), poi corretta.
- Avevo certificato il passaggio di Mike al motore con un solo scenario: ne servivano 15.
- Ho lanciato troppi lavori insieme e il PC ha esaurito la memoria nella notte.
- Ho letto come difetto del codice un problema del mio ambiente di replay.
- Ho scritto orari stimati invece di leggerli dall'orologio.
- Le copie di sicurezza che ho fatto contengono copie avviabili dei file `.bat`: oggi ne hai
  lanciata una al posto dell'originale.

## 6. Decisioni che aspettano te

- Mike, ultimo ingresso: ordine che resta valido in gioco (Costituzione) oppure «tutto o niente»
  (codice di oggi).
- Tetto di 3 connessioni di mercato: per salire serve una richiesta a Betfair.
- In manuale, se non rispondi, stop e tempo massimo non scattano: vuoi una rete automatica?
- Tennis pro: proposte firmate con importo di chiusura 0,00, da indagare.
- Atlante e 4 difetti minori del report giornaliero.
