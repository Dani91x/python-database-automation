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

Riferimenti: referti in `ARCHITETTURA_2026-10/ondata1/W1-*/REFERTO.md` (par. 9 "Divergenze per l'utente").
