# Ricerca: come chiudono sotto il minimo i tool che lavorano su betfair.it

Data: 01/10/2026. Sola lettura, nessun file di codice toccato. Completa
`RICERCA_STAKE_MINIMI_BETFAIR.md` sul fronte italiano e non ne ripete il contenuto.

**Metodo.** Ricerca web con query in italiano e in inglese. Le pagine sono state lette con
`curl` (user agent da browser) e i testi estratti a mano. betfair.it, scommesseonline.betfair.it
e support.betfair.it, che WebFetch dava come 403, con `curl` si leggono: le citazioni qui
sotto vengono quindi dalle pagine vere, non dagli estratti del motore di ricerca. I siti
morti li ho letti dall'archivio Wayback Machine e lo dico caso per caso. Per GitHub ho usato
`gh`.

**Affidabilità delle fonti:**
- **[U]** ufficiale (Betfair Italia, ADM, decreto);
- **[M]** manuale o sito del produttore del tool;
- **[C]** comunità (blog di formatori, forum, commenti).

**Il caso.** Una banca Over 4,5 da 0,43 € @18 è stata rifiutata con `INVALID_BET_SIZE`. Una
punta Under 7,47 € @1,03 dall'app è stata accettata.

---

## 0. In breve

1. **Due livelli di minimo, entrambi sopra 0,43 €.**
   - **Livello di legge** (DM 18/03/2013 n. 47, art. 8 [U]): la punta parte da **0,50 €**,
     «in multipli di 50 centesimi». La banca va piazzata in modo che la punta corrispondente
     (cioè la «puntata scommessa» della banca, il `size` dell'API) sia **almeno 0,50 €**.
     Secondo ADM (determina riportata il 23/06/2026) questo decreto è ancora in vigore.
   - **Livello commerciale di Betfair Italia** (Nota informativa di betfair.it, letta oggi
     [U]): *«L'importo minimo della scommesse nello Sport e su Exchange è pari a Euro
     1,00»*. Il blog ufficiale del 30/10/2023 annuncia che anche la banca scende da 2 € a
     1 € [U].
   - La nostra banca da 0,43 € sta sotto **entrambi** i minimi: il rifiuto era inevitabile.
     Nessuna tecnica di riduzione la porta a 0,43 €, perché 0,43 è sotto anche il minimo di
     legge.
2. **Il passo di 0,50 €.** Il decreto lo impone ancora per la punta. La documentazione
   per sviluppatori lo ripete. La comunità italiana lo descriveva nel 2014 («puntate solo
   con multipli di 0,50, mentre le bancate possono essere anche con valori differenti»).
   Ma la punta da 7,47 € di oggi è stata accettata, e **non ho trovato** nessun
   provvedimento ADM né comunicato Betfair che tolga quel passo. Da verificare sullo
   storico del conto.
3. **Quasi nessun tool «professionale» lavora su betfair.it**, a differenza di quanto si
   pensava:
   - **Cymatic**: non funziona (forum ufficiale, 21/10/2021).
   - **Bet Angel**: non funziona (KB del 23/04/2023).
   - **Bf Bot Manager**: non funziona (titolo e estratto della sua KB n. 22; pagina 403).
   - **FairBot Italy**: chiusa. Oggi fairbot.it mostra *«Il servizio di FairBot Italy è
     definitivamente chiuso»*.
   - **Geeks Toy**: nel 2014 prometteva il supporto, ma non ho trovato conferme.
   - **Gruss**: nessuna menzione di .it.
   - **Funzionano** su .it (autorizzati ADM): **Traderline** e **Betting Toolkit**.
4. **Come fanno i tool italiani sotto il minimo.** Unica descrizione trovata per .it:
   Gianluca Landi (bettingexchange.net, pagina del 03/11/2020 aggiornata il 02/06/2026 [C],
   vicino a Traderline).
   - Il software «spezza la scommessa in due ordini». Il ritardo raddoppia: da 5 a 10 s nel
     calcio.
   - **Sotto 0,50 € l'ordine viene rifiutato del tutto**: «non sono nemmeno permessi dalla
     regolamentazione».
   - La soluzione indicata: «**rientra sul mercato** … con altri 2 euro» e poi fai il green
     up. La chiusura diventa così abbastanza grande da superare il minimo.
5. **Chiudere sulla stessa selezione dal lato opposto.** Lo fa Betfair stessa su .it:
   - il Cash Out ufficiale *«potrebbe piazzare una combinazione di scommesse di tipo punta
     e/o banca»* (help center betfair.it, art. 3776 [U]);
   - FairBot sceglie, nei mercati a due esiti, la chiusura più conveniente fra le due
     possibili [M];
   - la comunità italiana insegna l'equivalenza: «puntare 100 € sull'under 2,5 a quota 1,5
     significa esattamente bancare l'over 2,5 con 50 € a quota 3,00» [C].

   Per il nostro caso è la strada giusta: banca Over 0,43 @18 ≡ **punta Under 7,31 €
   @1,0588**, sopra ogni minimo. È proprio quello che l'utente ha fatto a mano con 7,47 €
   @1,03.
6. **Il «parcheggio e riduzione» su .it** ha senso solo se l'importo finale resta
   **≥ 0,50 €**. Le testimonianze .it sono:
   - BACK: parcheggio a quota alta (9,00 nell'esempio);
   - LAY: parcheggio @1,01;
   - poi aumento di 0,50, oppure cancellazione e riprezzo.

   Gli importi ottenibili sono solo 0,50 / 1 / 1,50 €. **Sotto 0,50 € non c'è nessuna
   testimonianza di successo su .it.**

---

## 1. Minimi reali su betfair.it: fonti ufficiali

| Fonte | Data | Cosa dice (citazione) | Affidabilità |
|---|---|---|---|
| **DM 18 marzo 2013, n. 47**, art. 8 c. 1 e 3 (GU n. 107 del 09/05/2013; testo integrale su studiocerbone.com: https://www.studiocerbone.com/decreto-ministeriale-18-marzo-2013-n-47-scommesse-a-distanza/) | 2013, in vigore | «la posta di gioco per ciascuna offerta "puntata" è prescelta dal giocatore da un minimo di 50 centesimi di euro, in multipli di 50 centesimi di euro. Conseguentemente, ciascuna offerta "banco" è effettuata dal giocatore in modo tale che la posta di gioco di un'eventuale offerta "puntata" corrispondente ammonti ad un minimo di 50 centesimi di euro.» c. 3: «Eventuali variazioni della posta di gioco sono effettuate con provvedimento di AAMS. Fermi restando i predetti vincoli, il concessionario ha la facoltà di effettuare abbinamenti parziali, cui conseguono poste di gioco inferiori.» | [U] testo di legge (letto su una copia di studio legale, non sulla GU) |
| Determina ADM sulla fase transitoria, riportata da Italian Gaming News (https://italiangamingexpo.com/2026/06/23/adm-dal-13-novembre-le-nuove-regole-tecniche-per-casino-live-bingo-poker-e-betting-exchange/) e da AGIMEG (https://www.agimeg.it/adm-fase-transitoria-certificazione-giochi-live-scommesse-betting-exchange/) | 23/06/2026 | «Sino all'entrata in vigore del nuovo decreto ministeriale di regolamentazione, resta fermo il riferimento al decreto ministeriale vigente» (exchange). Nuovo protocollo PSID 3.0 e «circuito di gioco» entro il 13/11/2026. | [U] riportato dalla stampa di settore |
| **Nota informativa betfair.it** (https://www.betfair.it/aboutUs/terminiecondizioni/notainformativa/) | letta il 01/10/2026; nessuna data in pagina | «Importo minimo della scommessa — L'importo minimo della scommesse nello Sport e su Exchange è pari a Euro 1,00.» «la vincita massima potenziale… è pari a 50.000 Euro. La stessa vincita massima si applica anche su Exchange.» «Non è consentito piazzare o provare a piazzare scommesse che sfruttano deliberatamente il fatto che Betfair arrotondi al centesimo. Qualunque scommessa che presentasse simili caratteristiche verrà annullata automaticamente.» | [U] contratto |
| Blog ufficiale betfair.it, «anche la bancata minima viene portata a 1€» (https://scommesseonline.betfair.it/bancata-minima-1-euro-301023-369.html) | 30/10/2023 | «Fino ad oggi, quando si bancava, l'importo minimo della nostra scommessa era di 2€, ora… possiamo anche abbassarlo a 1€.» Esempio: banca @10 → «1€ per la scommessa, 9€ come quota di rischio». Quindi il minimo vale sulla **puntata scommessa** della banca, non sulla responsabilità. «l'importo minimo a 1€ nelle scommesse di tipo punta, è già presente su Betfair.» | [U] blog del concessionario (pagina letta per intero) |
| Blog ufficiale betfair.it, «Scommessa minima a 1€ e payout massimo fino a 50.000€» (https://scommesseonline.betfair.it/guida-al-betting/scommessa-minima-1-euro-limite-vincita-50000-euro-080124-369.html) | 17/01/2024 | «stake minimo di 1€» e «aumenti di puntata… con scalini di appena 5 centesimi»; vincita massima da 10.000 a 50.000 €. L'articolo parla soprattutto di Sportsbook (schedine multiple), non è chiaro se il passo di 0,05 valga per l'Exchange. | [U] ma ambiguo sul prodotto |
| Help center support.betfair.it, art. 3791 (https://support.betfair.it/app/answers/detail/a_id/3791/) | letto il 01/10/2026 | «la vincita potenziale massima non può essere superiore a €10.000 (compresa la puntata)». **Contraddice** i 50.000 € della Nota informativa. | [U], incoerente con il contratto |
| Help center, art. 3769 (https://support.betfair.it/app/answers/detail/3769-exchange-come-si-piazza-una-scommessa-scopri-la-scheda-scommessa) e pagina «Informazioni sul betting exchange» (https://www.betfair.it/aboutUs/Informazioni_sul_betting_exchange.html) | letti il 01/10/2026 | Per la banca, «Inserisci l'importo nella 'Puntata scommessa'. Questo rappresenta la tua potenziale vincita». «l'importo che inserisci è la cifra che desideri vincere». Conferma che il minimo si applica al `size` (lo stake del backer). | [U] |
| Pagina vecchia betfair.it «Come scommettere» (https://www.betfair.it/aboutUs/scommesse/scommetere/) | non datata, superata | «L'AAMS prevede che la scommessa minima debba essere di 2 euro… tetto di vincita… 10.000 euro». È lo Sportsbook prima del DM 145/2022. | [U] ma obsoleta |
| DM 1 agosto 2022 n. 145, art. 12 (https://repo.lottomaticagroup.com/intplatform/guida/decreto_ministeriale_1_agosto_2022_n._145.pdf) | 2022 | «La posta unitaria… è stabilita in cinque centesimi di euro e l'importo minimo per ogni ricevuta… non può essere inferiore ad un euro.» Vale per le scommesse a quota fissa (Sportsbook). Il testo **non nomina** l'interazione diretta fra giocatori, cioè l'Exchange. | [U], solo per lo Sportsbook |
| Documentazione per sviluppatori, «Betting On Italian Exchange» | 31/07/2026 (vedi la ricerca precedente) | punta ≥ 2,00 € in multipli di 0,50; banca con punta corrispondente ≥ 0,50 €. | [U] ma in ritardo sul minimo commerciale (dice 2 €, il contratto dice 1 €) |

**Cosa ne ricavo (deduzione, non citazione).**

- La **soglia di legge** è 0,50 € sullo stake del backer, sia per la punta sia per la
  banca.
- Betfair Italia ci aggiunge un **minimo commerciale di 1,00 €**: Nota informativa, più il
  blog del 2023 per la banca.
- Il **passo di 0,50 €** per la punta è scritto nel decreto e nella documentazione per
  sviluppatori. Ma la punta da 7,47 € accettata oggi dimostra che **oggi non viene
  applicato**, almeno all'ordine iniziale. Il provvedimento che lo avrebbe cambiato (art. 8
  c. 3) **non l'ho trovato**.
- Per 0,43 € la conclusione non cambia: è sotto 0,50 e sotto 1,00.

## 2. I tool che dovrebbero «supportare .it»: cosa risulta davvero

| Tool | Supporta .it oggi? | Tecnica sotto il minimo | Fonte |
|---|---|---|---|
| **FairBot (Binteko)** | **No più.** Fino a ottobre 2025 esisteva FairBot Italy (fairbot.it, FAQ: «è necessario essere registrati su Betfair.it»). Oggi http://fairbot.it mostra «Il servizio di FairBot Italy è definitivamente chiuso». La pagina «chiusura-fairbot-italy» è archiviata dal 16/12/2025, ma non è leggibile (pagina anti-bot nell'archivio). | Versione .com: **«"Small Bets" support… below the Betfair minimum»** (FairBot 2.0). «Improved "Green Up All" function for 2-way markets. Now it selects one Greening Up bet which offers the most profitable result from 2 available bets» (FairBot 3.2). «Greening Up on both selections even if bet(s) were placed just on a single selection» (2 esiti, tennis). Il meccanismo interno del sotto-minimo **non è documentato**. Nel changelog italiano (FairBot.it 4.53-4.90, archiviato il 06/10/2025) **nessuna voce** sul minimo. | [M] https://binteko.com/whatsnew/fairbot (pagine 3-7, lette oggi); sito chiuso letto il 01/10/2026; Wayback `web.archive.org/web/20250905120316/https://fairbot.it/faq/` e `.../20251006160431/https://fairbot.it/aggiornamenti/` |
| **Cymatic Trader** | **No.** «Unfortunately Cymatic is still not able to work for residents of Italy… not being actively pursued» | Su .com: «1) Back $5 at 990 2) Request a change to $7.50, Betfair… making a second bet… 3) Cancel the 1st bet 4) Move the 2nd bet» (Gavin, 04/02/2013). Il 05/02/2013 Betfair rifiutava già la creazione di stake sotto 0,50 (INVALID_ODDS). | [M] forum ufficiale: http://www.cymatic.co.uk/forum/topic224.html (04/04/2014, 20/01/2015, 21/10/2021); https://www.cymatic.co.uk/forum/topic19.html |
| **Bf Bot Manager** | **No** (titolo della KB «Does software work with Italian betfair.it exchange?», n. 22; estratto del motore: non funziona) | n/d per .it | [M] https://www.bfbotmanager.com/en/help/knowledge_base/article/22-does-software-work-with-italian-betfair-it-exchange — **403 da curl e da WebFetch: letto solo l'estratto del motore** |
| **Bet Angel** | **No** («It will not work with the Betfair.es and the Betfair.it») | (vedi la ricerca precedente) | [M] KB del 23/04/2023, già citata |
| **Geeks Toy** | **Non verificato.** Il 08/04/2014 lo staff scriveva «We expect to add support for it later this year… before November 1st». Non ho trovato conferme successive. Il sotto-forum italiano esiste ma non tratta il minimo. | (su .com: 2 € @1000 poi riduzione, ricerca precedente) | [M/C] https://geekstoy.com/forum/forum/the-forums/international-forums/italiano/generale-scommesse-e-trading/11768-geeks-toy-per-betfair-it |
| **Gruss Betting Assistant** | **Nessuna menzione di .it** nel manuale (528 pagine, letto per intero con ricerca). Il caso italiano di Gruss nel 2020 (parcheggio @1,10) era un utente su .com. | Opzioni «Lay @ 1000 stake», «Ignore minimum payout when placing below minimum stakes», «batch size for below minimum stake bets». Forum, 14/11/2024: «Betfair now accept below minimum stake bets in one transaction so workaround no longer required». È il Min Bet Payout di .com, **vietato su .it**. | [M] https://www.gruss-software.co.uk/Betting_Assistant/userguide/docs/userguide.pdf ; http://www.gruss1-software.co.uk/forum/viewtopic.php?f=9&t=11521 |
| **Traderline** | **Sì**, «certificata anche da ADM», attiva su .it dal 22/09/2014, nuova versione dal 28/12/2024 | Vedi §3: spezza in due ordini, ritardo doppio, rifiuto sotto 0,50 €, consiglio di «rientrare con altri 2 euro» e chiudere. | [C/M] https://bettingexchange.net/software/traderline (modificata il 01/04/2025); https://bettingexchange.net/video/stake-inferiore-2-euro-software-trading-sportivo-betfair |
| **Betting Toolkit** | **Sì**, «certificato ADM… su Betfair Italia» (annuncio del 24-25/07/2023) | La guida (aggiornata il 03/09/2026) **non parla** del sotto-minimo. Sul cash out: «If you are laying a selection, you may not be able to close your position with a back bet if the current lay odds are 1.01». | [M] https://help.bettingtoolkit.com/knowledge-base/betting-toolkit-user-guide/functions/cash-out-1-31 |
| BetTrader, «Tradingfair», TradeSports, BetPractice, BotBeast, «Betfair Bot Italia» | **Nessuna fonte trovata** su .it o sul minimo | — | — |

## 3. La comunità italiana: tecniche descritte

- **Gianluca Landi, bettingexchange.net**, «Stake inferiore ai 2 euro nei software di
  trading sportivo»
  (https://bettingexchange.net/video/stake-inferiore-2-euro-software-trading-sportivo-betfair).
  Pubblicata il 03/11/2020, modificata il 02/06/2026 (metadati della pagina). [C], formatore
  vicino a Traderline.
  - *«I software spezzano la scommessa in due ordini per inviare a mercato l'importo
    richiesto»*; *«I secondi di delay vengono raddoppiati»* (5 → 10 s nel calcio).
  - Green up: *«guarda sempre l'importo di puntata e bancata, non il profitto realizzato»*.
    Se sei in posizione con 5 € e chiudi per 1,20 € di profitto, *«la bancata supera i 2
    euro»* e passa senza problemi.
  - *«In diversi casi il software non spezza la scommessa, ma la rifiuta del tutto.
    Succede soprattutto con importi sotto i 50 centesimi. Questi importi… non sono nemmeno
    permessi dalla regolamentazione in vigore.»*
  - La soluzione: *«Se il sistema rifiuta l'ordine, rientra sul mercato in puntata o in
    bancata, a seconda della tua posizione, con altri 2 euro. Esegui il green up»*.
  - **Nota mia**: la pagina scrive ancora «Betfair fissa a 2 euro l'importo minimo», mentre
    il contratto attuale dice 1 €.
- **bettingexchange.net**, «Problema stake minimo nel Betfair Exchange»
  (https://bettingexchange.net/problema-stake-minimo-nel-betfair-exchange), senza data,
  lettura via WebFetch. [C]
  - Su .it la punta è ammessa *«solamente con multipli di 0.50 euro»*, la banca no.
  - Chi apre con una banca da importo non multiplo *«può chiudere in puntata solo un multiplo
    di 0.50 e rimanere in posizione… con il rimanente stake inferiore a 0.50 euro»*. La
    causa viene attribuita al *«decreto legge n.47»*: è il DM 47/2013, art. 8.
  - Il residuo sotto 0,50 è descritto come **non chiudibile** sulla stessa selezione.
  - Non viene considerata la chiusura sull'altra selezione.
- **bettingexchange.it**, «Come puntare e bancare 50 centesimi»
  (https://bettingexchange.it/come-puntare-e-bancare-50-centesimi-con-betfair-exchange/),
  commenti dal 04/11/2014 al 27/06/2020. [C]
  - BACK: 2 € a quota non abbinabile (9,00 nell'esempio), poi 2,00 → 2,50: *«avremo… due
    scommesse… una con puntata 2 euro e l'altra con 50 centesimi»*. Si cancella la 2 € e si
    riprezza la 0,50.
  - LAY: *«quota particolarmente bassa, ad esempio 1.01»*.
  - Importi ottenibili: *«50 centesimi, 1 euro o 1,50 euro»*.
  - Commento della redazione, 15/11/2014: *«le puntate solo con multipli di 0,50 mentre le
    bancate possono essere anche con valori differenti»*.
  - Avvertenza di un utente: verificare *«che non vi siano rimaste in attesa di
    abbinamento le giocate da 2€… Rischiereste che si abbinino!»*.
  - Rischio per il conto: domanda del 27/06/2020 senza risposta documentata.
- **Equivalenza fra lati opposti**:
  - tradingsulcalcio.net (https://tradingsulcalcio.net/bancare-vendere-quota, non datata)
    [C]: *«puntare 100 euro sull'under 2,5 a quota 1,5 significa esattamente bancare l'over
    2,5 con 50 euro a quota 3,00!»*;
  - bettingexchangeitalia.com, «Schema riassuntivo»
    (https://bettingexchangeitalia.com/6-schema-riassuntivo/, pubblicata il 14/01/2014,
    modificata il 20/06/2022) [C]: formule di «puntata equivalente» e «bancata
    equivalente».

  Nessuna delle due fonti la propone **esplicitamente** come rimedio al minimo, ma è la
  stessa algebra.
- **Betfair Italia stessa** (help center, art. 3776,
  https://support.betfair.it/app/answers/detail/a_id/3776/, letto oggi) [U]: *«Anche se il
  cliente per utilizzare la funzione "Cash Out" fa clic su un solo pulsante, il sistema
  potrebbe piazzare una combinazione di scommesse di tipo punta e/o banca utilizzando i
  migliori prezzi disponibili»*. È l'unica descrizione ufficiale di come Betfair chiude per
  conto del cliente. Non dice come gestisce gli importi sotto il minimo (**non trovato**).
- **Forum e social**: FinanzaOnline e Infobetting rispondono 403. Non ho trovato thread
  Reddit in italiano sul tema, gruppi pubblici Telegram o Facebook leggibili, né trascrizioni
  YouTube in italiano. L'unico video trovato è quello di Landi, letto tramite la pagina che
  lo accompagna.

## 4. Codice aperto con supporto .it

- **betfairlightweight**
  (https://github.com/betcode-org/betfair/blob/master/betfairlightweight/baseclient.py):
  per `locale="italy"` gestisce solo gli URL (identitysso.betfair.it, api.betfair.it) e il
  timeout di sessione a 20 minuti. **Nessuna regola di minimo italiana.**
  - In `metadata.py`, EUR vale `min_bet_size 1, min_bet_payout 20`.
  - L'unica issue sull'Italia (#249, 25/10/2019) riguarda il login.
- **flumine** (https://github.com/betcode-org/flumine/blob/master/flumine/controls/tradingcontrols.py):
  `_validate_betfair_min_size` rifiuta solo se `size < min_bet_size and price*size <
  min_bet_payout`.
  - Con EUR e Min Bet Payout (vietato su .it) **lascerebbe passare** ordini che .it
    rifiuta. Esempio: LAY 0,43 @50 → payout 21,5 ≥ 20 → accettato da flumine, rifiutato da
    .it.
  - Nessuna issue su Italia, .it o regole italiane (ricerca `gh` vuota).
- **Autosport** (Oleksii-debug), PR #1322 del 21/09/2026
  (https://github.com/Oleksii-debug/Autosport/pull/1322): implementa una guardia .it
  «fail-closed».
  - Regole: punta ≥ 2,00 € in multipli esatti di 0,50; LAY `size` ≥ 0,50 € («the
    corresponding backer's stake / layer potential profit»); niente PAYOUT/BACKERS_PROFIT;
    50 istruzioni; niente BACK e LAY nella stessa richiesta; resa ≤ 10.000 €.
  - Cita le stesse pagine ufficiali (documentazione per sviluppatori, support.betfair.it
    3791 e 3769).
  - **Non fa place-and-trim né equivalenza fra lati: rifiuta e basta.** Non è stato provato
    con denaro vero («REAL_MONEY_EXECUTION=false»).
- **Pickfair-nogui** (bot italiano): nessun riferimento a `INVALID_BET_SIZE` né al minimo
  .it nel codice indicizzato.
- **Non trovato**: alcun progetto aperto che implementi per .it il «parcheggio e
  riduzione» o l'equivalenza di lato.

## 5. Le due tecniche, alla prova delle fonti italiane

### (a) Ordine equivalente sulla stessa selezione, lato opposto

Esempio: «banca Over S@q» equivale a «punta Under S(q−1) @ q/(q−1)».

- **Chi la usa.** Il Cash Out ufficiale di betfair.it la usa implicitamente («combinazione
  di… punta e/o banca», art. 3776). FairBot sceglie fra le due chiusure possibili nei
  mercati a due esiti. Le guide italiane insegnano l'equivalenza.
- **Cosa non ho trovato.** Nessuna fonte italiana la raccomanda **per nome** come rimedio al
  minimo.
- **Perché funziona da rimedio (deduzione).**
  - Il minimo .it pesa sul **`size`**, cioè sullo stake del backer. Una banca piccola a
    quota alta (0,43 @18) diventa una punta grande a quota bassa (7,31 @1,06).
  - Sopra il minimo vale 1 €, quindi basta S ≥ 1/(q−1): con q = 18 già da S ≥ 0,06 €.
  - Un ordine solo, un solo ritardo, nessun parcheggio.
  - È **l'unica via** per S < 0,50 €, perché il «parcheggio e riduzione» non scende sotto
    il minimo di legge (vedi b).

### (b) Parcheggio a quota non abbinabile, poi riduzione

- **Su .it le testimonianze descrivono solo multipli di 0,50** (0,50 / 1 / 1,50 €).
- Quote di parcheggio citate:
  - BACK: 9,00 nell'esempio di bettingexchange.it; 990 / 1000 nei tool .com;
  - LAY: 1,01.
- Limiti:
  - **sotto 0,50 € l'ordine viene rifiutato** (Landi [C], coerente con il DM 47/2013 [U]);
  - il ritardo raddoppia (5 → 10 s);
  - rischio di abbinamento del parcheggio da 2 € se resta in coda (bettingexchange.it).
- Il controllo `INVALID_PROFIT_RATIO` e la clausola della Nota informativa (*«scommesse che
  sfruttano deliberatamente il fatto che Betfair arrotondi al centesimo… annullata
  automaticamente»*) valgono anche su .it.
- **Nessuna testimonianza .it** di una riduzione via API con `sizeReduction` sotto 0,50 €
  (non trovato).

## 6. Raccomandazione per il nostro caso

Le scelte di strategia (prezzo, aggressività) spettano all'utente: qui non le tocco.

1. **Chiusura sotto il minimo in un mercato a due esiti (Over/Under, Match Odds tennis).**
   Va instradata sull'**ordine equivalente sulla stessa selezione dal lato opposto**.
   - Oggi: banca Over 0,43 @18 → punta Under 7,31 € al prezzo del libro di Under.
   - È ciò che fa il Cash Out di Betfair ed è ciò che ha fatto a mano l'utente.
   - Il controllo del minimo va fatto **sul `size` dell'ordine equivalente**, contro
     **1,00 €** (minimo commerciale attuale), non contro 2,00 / 0,50 della documentazione
     per sviluppatori.
2. **Se anche l'equivalente resta sotto 1,00 €.** Il «parcheggio e riduzione» è ammesso solo
   se l'importo finale è **≥ 0,50 €** (soglia di legge). Il parcheggio deve essere almeno
   pari al minimo commerciale (1,00 €; la nostra costante `IT_LAY_MIN_SIZE = 0,50` va
   verificata, perché Betfair potrebbe rifiutare un parcheggio da 0,50). Sotto 0,50 € le
   possibilità sono due, e la scelta spetta all'utente:
   - lasciare il residuo, quantificandolo: è la scelta di Bet Angel («P&L uneven by a few
     pence»);
   - fare come consiglia Landi, cioè **aumentare la posizione di almeno il minimo** e
     chiudere tutto con un ordine sopra soglia. Costa uno spread in più, ed è una modifica
     di strategia.
3. **Mai un ordine diretto sotto il minimo con la speranza di un'eccezione «di chiusura»**:
   nessuna fonte italiana la conferma (vedi il reperto su `live_order_build.py` nella
   ricerca precedente).
4. **Verifica sul conto, in sola lettura** (`listClearedOrders`): esistono punte .it
   abbinate con size non multipla di 0,50 piazzate direttamente? E banche con size tra 0,50
   e 0,99? Il caso 7,47 € suggerisce di sì per la prima domanda. La risposta decide il passo
   e il minimo LAY da usare nel codice.

## 7. Cosa NON ho trovato o non ho potuto verificare

- Il provvedimento ADM (DM 47/2013, art. 8 c. 3) che avrebbe cambiato la posta minima o il
  passo dell'Exchange: non trovato. Non so quindi spiegare con una fonte la punta da 7,47 €
  accettata.
- Se il minimo commerciale di 1 € valga anche per il **trim** via API (cancel parziale), o
  se il trim scenda fino a 0,50: nessuna fonte.
- Come il Cash Out di betfair.it gestisca i residui sotto il minimo: non documentato.
- La pagina di chiusura di FairBot Italy (data e motivo): l'archivio mostra solo la pagina
  anti-bot. Chiusura certa al 20/05/2026 (snapshot), avvenuta probabilmente fra ottobre e
  dicembre 2025 (dedotto dalle date degli snapshot).
- La KB di Bf Bot Manager (403): ho letto solo l'estratto del motore di ricerca.
- Il supporto .it attuale di Geeks Toy: non verificato.
- Documentazione sul sotto-minimo di BetTrader, Tradingfair, TradeSports, BetPractice,
  BotBeast e dei bot Excel/VBA italiani: nulla trovato.
- Forum FinanzaOnline e Infobetting (403), gruppi Telegram e Facebook, Reddit in italiano,
  trascrizioni YouTube: non letti o non trovati.
- La Gazzetta Ufficiale originale del DM 47/2013: letta su una copia (studiocerbone.com),
  non sul sito della GU.
- Fuori perimetro, solo segnalato: le «Regole tecniche» ADM per le concessioni (2024-2025,
  https://www.adm.gov.it/portale/documents/20182/206822607/3.+Regole+Tecniche.pdf)
  scrivono *«Non sono consentiti automatismi che eseguano puntate o sequenze di puntate in
  modo automatico senza esplicita azione di accettazione da parte del giocatore»*. Il
  passaggio sta nel capitolo sulle **applicazioni di gioco del concessionario**. Se e come
  tocchi un client API di terzi su .it **non l'ho verificato**: da far valutare all'utente.
