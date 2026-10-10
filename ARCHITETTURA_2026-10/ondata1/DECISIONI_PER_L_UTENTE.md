# Ondata 1 - decisioni per l'utente (09/10/2026)

Raccolte dai referti e dalle revisioni indipendenti dei sette comparti. Per ognuna: cosa succede oggi, cosa
farebbe il nuovo, la raccomandazione del coordinatore. Finche' l'utente non decide vale la colonna "oggi" (o la
scelta prudente indicata): nessuna di queste cambia una strategia (soglie, stake, tetti, gambe).

Le divergenze che erano regressioni non sono qui: il coordinatore le ha fatte correggere per parita' con oggi
(ack del ref gia' visto come il motore, ordine spostato dal ladder che resta dell'utente, fase dedotta dal
ripiego come Omega, aggiornamenti mai scartati per l'orologio, nessuna ripresa dello stream con filtro diverso).

| # | Argomento | Oggi | Nuovo / opzioni | Raccomandazione |
|---|---|---|---|---|
| 1 | Login a Betfair (W1-A1) | Ogni processo fa il suo login; fino a 13 processi insieme (8 servizi, job tennis, fino a 4 scalper) | Freno di 10 login/min per processo: con 13 processi il tetto del conto (100/min) non e' garantito. Opzioni: (a) sessione UNICA dell'app, (b) 7 login/min per processo | **(a) sessione unica** (piano 04 par. 8.5): un login, un keepAlive, nessun rischio di ban. Fino all'ondata 2: (b) |
| 2 | Attesa dopo un login fallito (W1-A1) | `segnala_errore` scavalca l'attesa, il relogin chiesto dal REST no | Identico a oggi | **Uniformare**: anche `segnala_errore` rispetta l'attesa di 15/30/60 s (evita tempeste di login) |
| 3 | Punta non multipla di 0,50 EUR dal desktop (W1-C1) | Il terminale del desktop la rifiuta; il motore la tronca | La porta sa fare entrambe | **Rifiutare** per il desktop (l'utente vede l'errore, nessun importo cambiato di nascosto); i bot restano come oggi |
| 4 | Fase della partita dal ripiego API-Football (W1-B) | Omega la deduce dal minuto | Uguale a Omega, marcata "dedotta" | **Tenere come oggi** (strategie intoccabili) |
| 5 | Mercati a vincitore unico per il P&L "se vince" (W1-C2) | Il ladder mostra solo il "se vince" per selezione | Elenco chiuso: MATCH_ODDS, CORRECT_SCORE, HALF_TIME, HALF_TIME_SCORE, BOTH_TEAMS_TO_SCORE, OVER_UNDER_*, FIRST_HALF_GOALS_*; fuori elenco senza numberOfWinners: niente "se vince", stima prudente | **Approvare l'elenco** (si allarga solo con un mercato provato) |
| 6 | Un ordine col solo riferimento manuale e nessuna prova (W1-C2) | Considerato dell'utente | "Da confermare": niente comandi dal ladder finche' una prova non arriva (riga di coda, ack del desktop, tabelle dei bot) | **Da confermare** (un bot o il risk usano lo stesso riferimento: cancellarlo per errore e' peggio) |
| 7 | Una porta ordini per archivio locale (W1-C1/G1) | - | L'archivio ha un lucchetto per cartella | **Calcio e tennis su cartelle diverse** (non si mischiano, come sempre) |
| 8 | Ultima connessione libera a Betfair (W1-A2) | - | Lo stream ordini apre anche con 1 sola connessione libera; un frammento del calcio ripiega con pausa di 300 s, lo scanner su REST | **Si'**: vedere tutti gli ordini sul ladder e' la priorita' (in attesa del referto della terza revisione) |
| 9 | Riga illeggibile verso il cloud (W1-G1) | Persa con un warning | Messa da parte in locale, ritentata da sola, archiviata dopo N tentativi | **Si'** (migliore: nessun dato perso) |
| 10 | Ritardo dei dati del cloud (W1-G2) | Lettura ogni volta | Mike: un dossier aggiornato puo' arrivare fino a 5 min dopo (resta la lettura diretta di riserva); Omega: dopo la ricostruzione notturna fino a 5 min di tabelle vecchie | **Si'**, con la lettura diretta di riserva di Mike sempre accesa |
| 11 | Due script batch senza chiave di conflitto (W1-G2) | Ritentati dal trasporto del vecchio client | Nel client nuovo non sarebbero ritentati | **Lasciarli sul client di oggi** (nessun cambio) |
| 12 | Cadenza del ladder (W1-A2) | 200 ms | Il nuovo sa scendere a 20 ms (CPU misurata: +0,15% di un core con una partita, -7% con dieci) | **Decidere dopo l'ombra**: di serie restano 200 ms |
| 13 | Connessioni a Betfair in LIVE (W1-A2, terza revisione) | Ogni processo flumine LIVE (runner calcio, tennis, ogni scalper) apre gia' il suo stream ordini: caso peggiore 10 su 10 | Lo stream ordini del conto AGGIUNTO e basta: 11 su 10 (non entra). SOSTITUENDO gli stream ordini di flumine all'aggancio: 9 su 10 | **Sostituire** all'ondata 2: un solo stream ordini per l'app (e' anche cio' che porta tutti gli ordini sul ladder). Mai aggiunto senza sostituire |

Riferimenti: referti in `ARCHITETTURA_2026-10/ondata1/W1-*/REFERTO.md` (par. 9 "Divergenze per l'utente").

## Risposte dell'utente (10/10/2026) - VINCOLANTI per l'ondata 2

| # | Decisione | Cosa significa per il codice |
|---|---|---|
| 1 | **Si'**: una sola sessione per tutta l'app | Il custode di W1-A1 e' l'unico punto di login/keepAlive del processo dell'app; i servizi non fanno piu' login propri all'aggancio |
| 2 | **Si'**, e «sempre una sola connessione» | Anche `segnala_errore` rispetta l'attesa dopo un login fallito (da allineare in W1-A1 all'aggancio) |
| 3 | **Si'**: puntata dal desktop non multipla di 0,50 rifiutata | La porta usa `minimi.verdetto_desktop` (politica "rifiuta") per l'attore desktop; i bot invariati |
| 4 | **Si'**: fase dedotta dal minuto come Omega | Gia' cosi' in W1-B |
| 5 | **Tutti i mercati**: il "se vince" sul ladder per ogni mercato | Da cambiare in W1-C2: il "se vince" per selezione si calcola su ogni mercato, come i competitor; per i mercati a piu' vincitori o con handicap il numero resta mostrato con l'indicazione che e' per selezione (non e' un esito unico del mercato). Lavoro da fare all'inizio dell'ondata 2 |
| 6 | **Si'**: ordine col solo riferimento manuale = "da confermare" | Gia' cosi' in W1-C2 |
| 7 | **Si'**: calcio e tennis su cartelle diverse | All'aggancio |
| 8 | **No**: lo stream si usa dove possibile, la REST e' SOLO di riserva, come i competitor | Il problema dello slot nasce perche' oggi ogni processo apre le sue connessioni. All'aggancio: UN gestore dei flussi per tutta l'app (W1-A2 `GestoreFlussi`, 200 mercati per connessione) piu' UNO stream ordini; i servizi non aprono piu' stream propri. Con 10 connessioni = fino a 2.000 mercati in streaming: lo slot non manca piu' e nessun flusso ripiega sulla REST se non per guasto |
| 9 | **Si'**: riga illeggibile messa da parte e ritentata | Gia' cosi' in W1-G1 |
| 10 | **Tutta l'app in tempo reale per Betfair; il cloud solo come backup; il resto sul DB locale** | Nessun dato Betfair passa dal cloud (gia' cosi' nel disegno: stream -> app -> DB locale -> postino verso il cloud). Per i dati che il cloud CALCOLA (analisi pre-partita di Mike, tabelle di Omega) l'attesa fissa di 5 minuti va sostituita da un aggiornamento appena il cloud ricalcola (sentinella gia' presente in W1-G2), all'aggancio |
| 11 | **Si'**: i due script batch restano come oggi | Nessun cambio |
| 12 | **Massima velocita'** del ladder | Cadenza di serie 20 ms (W1-A2 la supporta); in ombra si misura la CPU vera del processo |
| 13 | **Un solo flusso ordini** per tutta l'app | All'aggancio lo stream ordini del conto (W1-A2) SOSTITUISCE quelli che flumine apre in ogni processo; mai aggiunto |
