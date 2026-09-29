# Piano delle modifiche a Mike (29/09/2026)

Questo documento raccoglie, punto per punto, cio' che l'utente decide su Mike durante la revisione
con la guida (`SCHEMI_BOT/mike/GUIDA_MIKE.html`).

**Regola dell'utente (29/09): NESSUNA modifica al codice parte finche' la revisione non e' finita.
Alla fine si fa il riepilogo, l'utente lo approva, e SOLO ALLORA si parte.** Fino ad allora questo
file si aggiorna e basta.

Per ogni punto: cosa vuole l'utente, cosa fa il codice oggi, cosa va cambiato, cosa resta da
chiarire. I riferimenti al codice servono a chi fara' la modifica.

Stato: **IN RACCOLTA** (nessuna modifica eseguita). Pre-partita: CHIUSO e confermato dall'utente il 29/09. Prossimo capitolo: dal fischio d'inizio.

---

## Punto 1 - Pre-partita: il giro punta e banca

Fase: partita NON in gioco. Rischio quasi nullo: prima del fischio non ci sono gol ne' sospensioni.

### Cosa vuole l'utente (parole sue, 29/09)
1. Quando Mike entra in posizione sull'Under 3,5 **deve piazzare IMMEDIATAMENTE la banca a 2 tick
   sotto il nostro prezzo**.
2. Poi **non fa altro**, finche':
   - **a)** il prezzo tocca la banca: il profitto e' chiuso, matematico, senza fare nulla. Dopo 60
     secondi Mike rientra in posizione con la stessa logica, fino a un massimo di 10 giri;
   - **b)** il prezzo va contro di noi e la banca non viene toccata: **non fa altro, la lascia li'**.
3. Mike lavora sulle partite a 1 ora dall'inizio (per non bloccare troppo capitale, per ora).

### Cosa fa il codice oggi
| Cosa | Oggi | Uguale a cio' che vuole l'utente? |
|---|---|---|
| Ingresso: punta Under 3,5, 10 EUR al miglior prezzo | si' (`stake` 10) | si' |
| Banca a 2 tick sotto il prezzo medio d'ingresso, appoggiata | si' (`pre_green_ticks` 2, `pre_exit_mode` resting) | si' |
| Importo della banca calcolato per spalmare il profitto sui due esiti | si' (10,00 a 1,50 -> banca 10,14 a 1,48: +0,13 / +0,14) | si' |
| La banca parte SUBITO dopo l'ingresso | **solo con le uscite su automatiche**. Con le uscite manuali (impostazione di serie) e' una PROPOSTA da firmare | **NO** |
| Banca abbinata: giro chiuso, 60 secondi di pausa, nuovo giro | si' (`pre_reentry_cooldown_s` 60) | si' |
| Massimo 10 giri per partita | si' (`pre_max_cycles` 10) | si' |
| Finestra: da 1 ora prima del fischio | si' (`entry_hours_before_ko` 1,0) | si' |
| Banca non toccata: Mike la lascia li' e non fa altro | si', **fino a 10 minuti dal fischio**. Da li' in poi oggi fa altre cose (vedi «Da chiarire») | **in parte** |

### Cosa va cambiato
- **M1.1 - La banca di green del pre-partita parte sempre da sola.** Non passa piu' dal cancello
  delle uscite manuali: appena l'ingresso e' abbinato, la banca a 2 tick sotto viene appoggiata, con
  l'interruttore su manuale o su automatico. Restano governate dall'interruttore le altre uscite
  (da confermare una per una nei punti successivi).
  - Per il tecnico: `under_green` esce da `USCITE_DISCREZIONALI` / `categoria_uscita` per il ramo
    appoggiato del pre-partita (`Betfair/mike/engine.py:2225`, `2252-2263`, `gate_uscite` 2337);
    banco: i controlli UM1-UM4 e UF1-UF3 di Mike vanno riallineati; UI: `PropostaUscitaMike` non deve
    piu' mostrare la proposta «green_pre».

### Gia' uguale, da NON toccare
Importo 10 EUR, 2 tick, 60 secondi, 10 giri, 1 ora, banca appoggiata. Sono i valori di oggi.

### Conseguenze da sapere (non sono modifiche)
- L'ingresso e' «tutto o niente»: se al miglior prezzo non ci sono 10 EUR, Mike non entra e riprova.
- Se i prezzi non sono vivi, Mike non manda nessun ordine, banca compresa (regola permanente
  dell'utente del 28/09): la banca parte al primo giro con prezzi vivi.
- La banca appoggiata cade al fischio d'inizio (e' un ordine che non resta in gioco).
- Prima di ogni ingresso passano 13 controlli (guida, capitolo 2).

---

## Punto 2 - Pre-partita: gli ultimi 10 minuti e la banca fino al fischio

### Cosa vuole l'utente (parole sue, 29/09)
1. La banca di chiusura **resta li' fino al fischio d'inizio**.
2. Nel pre-partita Mike **non chiude MAI in perdita**: «non ha senso».
3. La banca di chiusura e' in modalita' **LAPSE**: resta a mercato solo fino al cambio di stato.
   All'inizio della partita Betfair cancella gli ordini non abbinati.

### Verifica sulla documentazione ufficiale Betfair (fatta il 29/09)
- Betting Type Definitions, campo `persistenceType`: «What to do with the order at turn-in-play».
- placeOrders, «Placing a 'Keep' Bet»: «To place a bet that will be kept once a market turns
  in-play (if unmatched), you must include [...] "persistenceType": "PERSIST". The bet will then
  be placed automatically into the in-play market at the start of the event.» Quindi l'ordine
  resta in gioco SOLO se e' PERSIST; con LAPSE la parte non abbinata viene cancellata al passaggio
  in gioco.
- L'ordine riporta quanto e' stato cancellato cosi' nel campo `sizeLapsed` («The current amount of
  this bet that was lapsed»).
- Il passaggio in gioco e' un cambio di versione del mercato («The version increments whenever
  the market status changes, for example, turning in-play, or suspended when a goal is scored»).
- NON letta per intero: la pagina «Betting Enums» con la riga dell'enum LAPSE (la pagina si
  scarica troncata). La definizione sopra viene dalle due pagine lette.
- Conferma dal codice: la banca appoggiata di Mike parte GIA' oggi come LAPSE e senza «tutto o
  niente» (`Betfair/omega/omega_market.py:735`, chiamata con `fill_or_kill=False` da
  `Betfair/mike/service.py:1976`). Su questo non c'e' niente da cambiare.

### Cosa fa il codice oggi a 10 minuti dal fischio
| Situazione | Oggi | Cosa vuole l'utente |
|---|---|---|
| Giro in profitto | ritira la banca, chiude al prezzo di mercato, poi piazza l'ultimo ingresso | la banca resta li' |
| Giro in perdita | ritira la banca e tiene la posizione fino al fischio | la banca resta li' |
| Giro in perdita e veto sull'Under 3,5 | ritira la banca e CHIUDE IN PERDITA al mercato | mai chiudere in perdita |

### Cosa va cambiato
- **M2.1 - A 10 minuti dal fischio la banca NON si ritira.** Resta appoggiata a 2 tick sotto fino
  al fischio; al passaggio in gioco la cancella Betfair (LAPSE). Mike non la ritira e non la
  sostituisce con una chiusura al mercato.
  - Per il tecnico: ramo `PRE_OPEN` a `>= KO - pre_last_entry_min` in `_decide_prematch`
    (`Betfair/mike/engine.py:2628` e seguenti; schede 9-11 dell'inventario B); stato `HOLD`.
- **M2.2 - Nel pre-partita nessuna chiusura in perdita, mai.** Il veto sull'Under 3,5 non puo'
  piu' chiudere la posizione prima del fischio.
  - Per il tecnico: ramo del veto in `_decide_prematch` (`engine.py:2722-2739`),
    `valuta_veto_under35` 2601, parametro `veto_p_under35_cal` (oggi acceso).
- **M2.3 - Al fischio Mike deve LEGGERE cosa e' rimasto**: la parte della banca abbinata prima del
  fischio e la parte cancellata da Betfair (`sizeLapsed`), e ripartire dalla posizione vera.
  Da verificare nel replay (scenario con banca abbinata in parte al fischio).

### Risposte dell'utente (29/09, pomeriggio)
1. **L'ultimo ingresso: RESTA COSI'.**
2. **Nuovi giri negli ultimi 10 minuti: RESTA COSI'** (Mike non apre giri nuovi da 10 minuti prima
   del fischio).
3. **Il veto sull'Under 3,5**: la domanda era posta male. Vale la regola dell'utente: nel
   pre-partita non si chiude mai in perdita. Quindi il veto NON chiude piu' niente (M2.2); il
   resto del veto resta com'e' oggi.
4. **La modalita' «al mercato» della banca**: per l'utente riguarda il live. Si riprende nel
   capitolo del gioco, non qui.

### Documentazione Betfair: dove sta
L'utente ha ricordato che la documentazione e' NEL REPO: `Betfair/Betfair_api_documentation.pdf`
(62 pagine, guida ufficiale) e `docs/BETFAIR_BEST_PRACTICES_2026-07.md`. Si cerca PRIMA li'. Letta
il 29/09: il PDF contiene gli esempi di ordini con `"persistenceType": "LAPSE"` (pag. 47, 54, 55)
ma non la frase che descrive cosa succede al passaggio in gioco; quella frase viene dalle pagine
ufficiali in rete citate sopra (stessa fonte, stesso editore).

### Una conseguenza da confermare (unica domanda rimasta sul pre-partita)
Oggi l'ultimo ingresso parte SOLO dopo la chiusura al prezzo di mercato che Mike fa a 10 minuti
dal fischio quando e' in profitto. Con la banca che resta li' fino al fischio (M2.1) quella
chiusura non esiste piu': lasciando tutto il resto «cosi'», l'ultimo ingresso non scatterebbe
piu'. Da confermare con l'utente: l'ultimo ingresso sparisce, oppure parte quando a 10 minuti dal
fischio Mike e' piatto.

### DECISIONE dell'utente sull'ultimo ingresso (29/09, pomeriggio) - sostituisce la domanda sopra
Parole sue: «L'ultimo ingresso e' da intendersi cosi': Mike ha posizioni aperte per quella
specifica partita? NO: entriamo. SI': nessun altro ingresso, piazziamo il lay fino al fischio di
inizio. Quando inizia la partita, Mike si trovera' con SOLO l'Under 3,5 abbinato.»

In chiaro, a 10 minuti dal fischio:
| Mike su quella partita | Cosa fa |
|---|---|
| NON ha una posizione aperta (e' piatto) | ULTIMO INGRESSO: punta Under 3,5 e appoggia subito la banca a 2 tick sotto, LAPSE, che resta fino al fischio |
| HA una posizione aperta (con la banca in attesa) | nessun altro ingresso; la banca resta li' fino al fischio |

Al fischio: la banca non abbinata la cancella Betfair (LAPSE) e Mike entra in gioco con SOLO
l'Under 3,5 abbinato. Se invece la banca e' stata abbinata prima del fischio, Mike entra in gioco
piatto, col profitto del giro chiuso.

- **M2.4 - L'ultimo ingresso non dipende piu' dalla chiusura al mercato.** Parte a 10 minuti dal
  fischio se e solo se Mike e' piatto su quella partita, ed e' un ingresso come gli altri: punta
  piu' banca a 2 tick sotto in LAPSE.
  - Per il tecnico: oggi l'ultimo ingresso (`under_last`) nasce in `_after_final_green`
    (`Betfair/mike/engine.py:2858-2931`) solo dopo la chiusura «finale» abbinata, e porta
    `persistence="PERSIST"` sulla riga (l'ordine vero parte comunque LAPSE + tutto o niente:
    `Betfair/safe_strategy/execution.py:514`, `Betfair/omega/omega_market.py:735-746`). Il ramo
    «a 10 minuti gia' piatto: niente ultimo ingresso» e' la scheda 9 dell'inventario B. Vanno
    rivisti gli stati `PRE_GREEN_PENDING` (finale), `PRE_LAST_ENTRY_PENDING`, `HOLD` e il ritiro del
    residuo dopo il fischio (`_late_persist_cancel`, `cancel_unmatched_after_ko_s`).

CONFERMATO dall'utente (29/09):
- l'ultimo ingresso passa dagli stessi controlli d'ingresso degli altri giri. Parole sue: «OVVIO,
  le logiche e i filtri di ingresso devono restare! Qui stiamo solo ottimizzando la strategia, non
  i gate e i parametri»;
- l'ultimo ingresso si valuta al segno dei 10 minuti; dopo, nessun altro ingresso fino al fischio
  (anche se la banca viene abbinata negli ultimi 10 minuti);
- al fischio Mike VERIFICA se la banca si e' abbinata (profitto chiuso) oppure no (resta solo
  l'Under 3,5): e' la modifica M2.3.

**REGOLA GENERALE DI QUESTA REVISIONE (utente, 29/09): si cambia la condotta della strategia, NON
i controlli d'ingresso ne' i parametri.** Tutti i 13 controlli d'ingresso e i valori dei parametri
restano quelli di oggi, salvo ordine esplicito.

### Rimandato al capitolo «dal fischio d'inizio»
- La modalita' «al mercato» della banca.
- Cosa fa Mike se al fischio la banca non e' stata abbinata e l'Under 3,5 e' aperto (oggi: nuova
  banca 2 tick sotto per 3 minuti, poi copertura Over 4,5).

---

## Registro delle decisioni

| # | Data | Decisione dell'utente | Stato |
|---|---|---|---|
| 1 | 29/09 | Pre-partita: banca a 2 tick sotto SUBITO dopo l'ingresso, sempre, poi niente altro; 60 s e nuovo giro se abbinata, fino a 10 giri; se non abbinata resta li' | confermata, da implementare (M1.1) |
| 2 | 29/09 | La banca di chiusura resta li' fino al fischio d'inizio | confermata, da implementare (M2.1) |
| 3 | 29/09 | Nel pre-partita Mike non chiude MAI in perdita | confermata, da implementare (M2.2) |
| 4 | 29/09 | La banca di chiusura e' LAPSE: la parte non abbinata la cancella Betfair al passaggio in gioco | confermata; il codice fa gia' cosi'; da aggiungere la lettura di cio' che resta al fischio (M2.3) |
| 5 | 29/09 | Niente giri nuovi negli ultimi 10 minuti prima del fischio | confermata; gia' cosi' |
| 6 | 29/09 | Ultimo ingresso: a 10 minuti dal fischio, se Mike NON ha posizione su quella partita entra (punta + banca a 2 tick sotto); se ce l'ha, nessun altro ingresso. Al fischio Mike ha solo l'Under 3,5 abbinato | confermata, da implementare (M2.4) |
| 7 | 29/09 | La posizione in perdita nel pre-partita si porta in live, non si chiude | confermata, da implementare (M2.2) |
| 8 | 29/09 | Dal fischio: banca a 2 tick sotto per 3 minuti; se abbinata piatto; gol nei 3 minuti = seconda puntata da 5 EUR al miglior prezzo | confermata; gia' cosi' |
| 9 | 29/09 | La copertura diventa BANCA Under 4,5 (non piu' punta Over 4,5): stessa strategia, stesso margine del 20 %, importo = perdita Under 3,5 x 1,2 / 0,95 (lettura A) | confermata, da implementare (M3.1, M3.2, M3.3) |
| 10 | 29/09 | Caso A (3 minuti senza gol): prima ritira la banca sull'Under 3,5, poi copre sulla posizione rimasta | confermata; gia' cosi' |
| 11 | 29/09 | Caso B (gol nei 3 minuti): seconda puntata 5 EUR, poi copertura in due tranche (2 minuti dal gol, poi 3 minuti dopo) | confermata; gia' cosi' |
| 12 | 29/09 | Cash out in profitto: soglia 5 % confermata; parte SEMPRE da solo («se c'e' possibilita' di chiudere senza rischi deve farlo da solo») | confermata, da implementare (M4.1) |
| 13 | 29/09 | TUTTE le uscite in profitto partono da sole (pre-partita, fischio, cash out 5 %, cash out intelligente, green del rientro) | confermata, da implementare (M1.1, M4.1-M4.4) |
| 14 | 29/09 | Cash out intelligente: resta com'e' | confermata |
| 15 | 29/09 | Mike deve sempre sapere lo stato di ogni suo ordine (abbinato, chiuso, registrato) | regola permanente, criterio di accettazione di ogni modifica |
| 16 | 29/09 | Uscita in perdita: resta una proposta da firmare, esattamente com'e' ora («decido io») | confermata; nessuna modifica |
| 17 | 29/09 | Per annullare la copertura Mike BANCA l'Over 4,5 invece di puntare l'Under 4,5 (stesso risultato, importo sempre accettato) | confermata, da implementare (M3.3) |
| 18 | 29/09 | Tetto di perdita della partita: si toglie | confermata, da implementare (M4.5) |
| 19 | 29/09 | Riprezzo di una chiusura ferma: RESTA a 10 secondi, 20 tentativi (la proposta dei 20 secondi e' stata ritirata dall'utente) | nessuna modifica; M4.6 annullata |
| 20 | 29/09 | Rientro sull'Under 4,5: si fa con 1 o 2 gol (non piu' solo con 1); tutte le altre condizioni invariate | confermata, da implementare (M6.1) |
| 21 | 29/09 | Mike deve sapere sempre se una sua banca e' abbinata o no, e se una sospensione ha cancellato un suo ordine LAPSE | regola permanente; correzioni M6.2-M6.3 |
| 22 | 29/09 | Le cifre della proposta si aggiornano in tempo reale; fra clic e ordine si accetta il movimento del mercato; dopo la chiusura la scheda dice che e' stata fatta e che non resta esposizione | confermata, da implementare (M7.1, M7.2) |

---

## Punto 3 - Dal fischio d'inizio: uscita al fischio, seconda puntata, copertura

Fase: partita IN GIOCO, Mike ha l'Under 3,5 abbinato.

### Cosa vuole l'utente (29/09, pomeriggio)
| Passo | Oggi | Decisione dell'utente |
|---|---|---|
| 1. Al fischio Mike appoggia una banca a 2 tick sotto il prezzo medio e la tiene 3 minuti | si' | **resta cosi'** |
| 2. Banca abbinata: piatto, profitto chiuso | si' | **resta cosi'** |
| 3. Gol in quei 3 minuti: ritira la banca e punta altri 5 EUR sull'Under 3,5, una volta sola | si' | **resta cosi'**; la puntata va «al miglior prezzo disponibile, cosi' alziamo la quota media» (e' gia' cosi': miglior prezzo back) |
| 4. Passati i 3 minuti senza abbinamento: copertura | oggi PUNTA Over 4,5 | **DA CAMBIARE: BANCA Under 4,5** |

### La modifica sulla copertura (parole dell'utente)
«Invece che OVER 4.5 BACK (abbiamo i problemi di puntata per i limiti di Betfair), DEVE FARE LAY
UNDER 4.5, andando a calcolare l'importo del BACK UNDER 3.5 con 20% di margine in piu'. MASSIMA
ATTENZIONE A QUESTO PUNTO. LA STRATEGIA NON CAMBIA, CAMBIAMO SOLO IL MERCATO PER POTER PIAZZARE
GLI IMPORTI CORRETTI SENZA LIMITI DI BETFAIR.»

### Perche' e' la stessa scommessa
Puntare Over 4,5 e bancare Under 4,5 sono la stessa posizione sullo stesso mercato (Over/Under
4,5): in entrambi i casi si incassa se i gol sono 5 o piu' e si paga se sono 4 o meno. Cambia solo
come si scrive l'ordine:

| | Punta Over 4,5 (oggi) | Banca Under 4,5 (nuovo) |
|---|---|---|
| Quota d'esempio | 6,60 | 1,18 (e' la stessa quota vista dall'altro lato: 6,60 / 5,60 = 1,1786) |
| Importo dell'ordine | 2,26 EUR | 12,63 EUR |
| Quanto si rischia (si paga con 0-4 gol) | 2,26 EUR | 12,63 x 0,18 = 2,27 EUR |
| Quanto si incassa con 5+ gol, tolta la commissione del 5 % | 2,26 x 5,60 x 0,95 = 12,02 | 12,63 x 0,95 = 12,00 |
| Limiti di Betfair sull'importo | minimo 2,00 EUR e passi da 0,50: 2,26 non e' piazzabile diretto, sotto 2,00 serve il «piazza e riduci» | l'importo e' 5-6 volte piu' grande: il minimo non e' piu' un problema |

### Il conto, con la posizione d'esempio (punta Under 3,5 10,00 EUR a 1,50)
- Regola di oggi, che NON cambia: la copertura deve incassare, con 5 o piu' gol, 1,2 volte cio'
  che si perde sull'Under 3,5 (il «20 % di margine in piu'», parametro `cover_profit_factor` 1,2),
  al netto della commissione. Perdita sull'Under 3,5 = 10,00. Obiettivo = 12,00 netti.
- Banca Under 4,5: importo = 12,00 / 0,95 = **12,63 EUR**.
- **Proprieta' nuova e comoda: l'importo della banca NON dipende dalla quota.** Con la puntata
  sull'Over l'importo cambiava a ogni movimento di quota; con la banca sull'Under 4,5 l'importo e'
  sempre «perdita dell'Under 3,5 x 1,2 / 0,95». La quota decide solo quanto si rischia:
  a 1,17 si rischiano 2,15 EUR, a 1,18 2,27, a 1,19 2,40.
- Risultato finale, uguale a oggi:

| Gol finali | Under 3,5 (punta 10 a 1,50) | Under 4,5 (banca 12,63 a 1,18) | Totale | Oggi con Over 4,5 |
|---|---|---|---|---|
| 0-3 | +4,75 | -2,27 | **+2,48** | +2,49 |
| 4 | -10,00 | -2,27 | **-12,27** | -12,26 |
| 5 o piu' | -10,00 | +12,00 | **+2,00** | +2,02 |

### UNA domanda sul conto (da confermare)
L'utente ha detto: «l'importo del BACK UNDER 3.5 con 20 % di margine in piu'».
- Lettura A (la strategia resta identica al centesimo): importo = 10 x 1,2 / 0,95 = **12,63**; con
  5+ gol il totale e' +2,00 come oggi.
- Lettura B (alla lettera): importo = 10 x 1,2 = **12,00**; con 5+ gol si incassano 11,40 netti e
  il totale scende a +1,40.
Proposta del coordinatore: lettura A, perche' «la strategia non cambia».

**DECISIONE DELL'UTENTE (29/09): lettura A.** Importo della banca = perdita dell'Under 3,5 x 1,2 /
(1 - commissione), meno cio' che e' gia' coperto, per la frazione della tranche. E' la formula di
oggi (`cover_residual`), scritta per la banca.

### Cosa va cambiato
- **M3.1 - La copertura diventa BANCA Under 4,5** al posto di PUNTA Over 4,5. Stesso mercato,
  stesso momento, stesse condizioni (quando si copre e quando no, attesa dopo un gol, tranche dopo
  la seconda puntata, massimo 2 gol, freno dopo 3 rifiuti), stesso obiettivo (1,2 volte la perdita
  dell'Under 3,5, netto di commissione, meno cio' che e' gia' coperto).
- **M3.2 - Il cuscinetto sul prezzo si rovescia.** Oggi l'ordine sull'Over parte con un limite 2
  tick SOTTO il miglior prezzo per non morire durante il ritardo di piazzamento. Per una banca il
  limite va 2 tick SOPRA il miglior prezzo lay (si accetta di rischiare un po' di piu' per essere
  abbinati); Betfair abbina comunque al miglior prezzo disponibile.
- **M3.3 - Anche la chiusura della copertura si rovescia.** Oggi per chiudere la copertura Mike
  BANCA l'Over 4,5; dopo dovra' PUNTARE l'Under 4,5.

### Punti di MASSIMA ATTENZIONE (da verificare uno per uno prima e durante l'implementazione)
1. **Importi legali**: nel codice i limiti (minimo 2,00 EUR, passi da 0,50) valgono per le PUNTATE
   (`IT_BACK_MIN`, `IT_BACK_STEP`, `needs_submin` in `Betfair/mike/engine.py:67-68, 509`); per le
   BANCATE il codice non ne applica. Da confermare sulla documentazione del repo e sul campo che
   una bancata da 12,63 EUR parta diretta.
2. **La chiusura della copertura torna a essere una PUNTATA** (M3.3): li' i limiti di Betfair
   valgono di nuovo (12,63 non e' un multiplo di 0,50: 12,50 diretti + 0,13 col «piazza e riduci»).
   Il problema dei limiti sparisce in apertura, non in chiusura.
3. **Il rientro usa lo stesso mercato e la stessa selezione** (punta Under 4,5, poi banca Under
   4,5). Copertura e rientro si sommano sulla stessa selezione: i conti della posizione, la regola
   «una sola banca a mercato» e il giudizio delle uscite vanno provati con i due insieme.
4. **Ruoli e database**: la copertura oggi si chiama `over_cover` (punta, selezione Over). Una
   gamba nuova (banca, selezione Under del mercato 4,5) richiede di aggiornare i ruoli ammessi nel
   database (vincolo CHECK: il 13-14/09 un ruolo nuovo non ammesso ha fatto rifiutare le scritture
   per 12 giorni), il regolamento, la pagina e il banco di replay. Migrazione SQL scritta dal
   delegato e APPLICATA DALL'UTENTE.
5. **Liquidita'**: va misurata sulle registrazioni la quantita' disponibile da bancare sull'Under
   4,5 nei minuti in cui Mike copre, contro i 12-13 EUR che servono.
6. **Passo di quota**: a quota 1,18 un tick vale 0,01, cioe' circa 0,13 EUR di rischio in piu' o in
   meno su 12,63; sull'Over a 6,60 un tick vale 0,20.
7. **Paper specchio del live** e **certificazione sul replay** (15 scenari di Mike, piu' lo scenario
   delle coperture sui due trasporti) prima di qualunque uso.

### Per il tecnico
Copertura: `_decide_uncovered` (`engine.py:3273`), `_decide_cover_pending` 3425, `frazione_copertura`
3240, `cover_residual` 426, `cover_matched_value` 446 (gia' calcolato sul mercato intero a 5 gol),
`cover_place_price` 1687, `_mai_sovracopertura` 1972, `_freno_copertura` 2023, `_close_actions`
1754, `settle_legs_by_market` 1265; ruoli in `engine.py:46-52`; servizio `execute_place`.

### Chiarimenti sul punto 3, confermati dall'utente (29/09): «A: ok, B: ok»
**Caso A - passano 3 minuti, nessun gol, banca sull'Under 3,5 non abbinata.** Resta com'e' oggi:
1. Mike RITIRA la banca a 2 tick sotto sull'Under 3,5;
2. al giro dopo legge la posizione vera rimasta abbinata;
3. copre su quella posizione (con M3.1: banca Under 4,5). Banca abbinata per intero nel frattempo =
   piatto, niente copertura; abbinata in parte = copre solo il residuo.
   DA PROVARE NEL REPLAY: banca abbinata mentre il ritiro e' in corso.

**Caso B - gol nei primi 3 minuti.** Resta com'e' oggi:
1. Mike ritira la banca sull'Under 3,5;
2. a mercato riaperto punta 5 EUR (50 % dello stake) sull'Under 3,5 al miglior prezzo, e riprova a
   ogni giro fino a 2 minuti dal gol;
3. puntata abbinata: posizione 15 EUR (esempio: 10 a 1,50 + 5 a 1,95 = media 1,65), copertura in
   DUE tranche: la prima (meta') 2 minuti dopo il gol, la seconda (il resto, ricalcolato) 3 minuti
   dopo la prima. Con M3.1: banca Under 4,5 totale 15 x 1,2 / 0,95 = 18,95 EUR, prima tranche 9,47;
4. puntata non abbinata entro 2 minuti: si ritira e si copre in una volta la posizione da 10 EUR;
5. dopo la seconda puntata Mike NON rimette la banca a 2 tick sotto sull'Under 3,5.

---

## Punto 4 - Posizione coperta: le uscite

Fase: partita in gioco, Under 3,5 abbinato e copertura abbinata.

### PRINCIPIO dell'utente (29/09): «se c'e' possibilita' di chiudere SENZA RISCHI deve farlo da solo»
Una chiusura che blocca un PROFITTO non aspetta la firma: parte da sola, anche con le uscite in
manuale.

### Passo 1 - Cash out in profitto a soglia fissa
| Cosa | Oggi | Decisione dell'utente |
|---|---|---|
| Soglia: profitto netto, chiudendo tutto adesso, almeno il 5 % del capitale impegnato (`cashout_profit_pct` 5) | si' | **resta 5 %** |
| Come chiude: banca l'Under 3,5 e chiude la copertura, al miglior prezzo | si' | resta |
| In manuale | proposta da firmare | **DA CAMBIARE: chiude da solo** |

- **M4.1 - Il cash out in profitto parte sempre da solo**, con l'interruttore su manuale o su
  automatico.
  - Per il tecnico: ramo «profit» di `_decide_covered` (`Betfair/mike/engine.py:3527-3539`),
    `categoria_uscita` «chiusura» (`engine.py:2252`), `gate_uscite` 2337: la categoria «chiusura»
    oggi copre sia il profitto sia la perdita, va divisa per motivo di chiusura.
- **Attenzione (legata a M3.1)**: il «capitale impegnato» oggi somma le PUNTATE a rischio (Under +
  Over + rientro). Con la copertura come banca va contato il RISCHIO della banca (12,63 x 0,18 =
  2,27 nell'esempio): stessa cifra di prima, calcolo da adattare (`invested`, `engine.py:700`).
- Esempio: capitale 12,27, soglia 0,61; al 40' sullo 0-0 con Under 3,5 a 1,20 e Under 4,5 a 1,05:
  chiusura Under 3,5 circa +2,38 netti, chiusura copertura circa -1,56, totale circa +0,81: chiude.

### REGOLA GENERALE dell'utente sulle uscite (29/09)
Parole sue: «TUTTO QUELLO CHE SONO USCITE IN PROFITTO, MIKE PUO' FARLE DA SOLO COME DA INDICAZIONI E
DA PROGETTAZIONE».
Quindi partono SEMPRE da sole, con l'interruttore su manuale o su automatico, tutte le chiusure che
bloccano un profitto:
| Uscita in profitto | Oggi in manuale | Dopo |
|---|---|---|
| Banca di green del pre-partita (2 tick sotto) | proposta | da sola (M1.1) |
| Banca a 2 tick sotto al fischio d'inizio | proposta | da sola (M4.2) |
| Cash out in profitto al 5 % | proposta | da solo (M4.1) |
| Cash out intelligente (profitto di almeno il 2 %) | proposta | da solo (M4.3) |
| Banca di green del rientro sull'Under 4,5 | proposta | da sola (M4.4) |

- **M4.2, M4.3, M4.4**: come M4.1, le uscite in profitto escono dal cancello delle uscite manuali.
- L'interruttore manuale/automatico resta e governa cio' che NON e' un'uscita in profitto (le
  uscite in perdita: da decidere nel passo 3).
- Il pulsante resta su ogni bot, di serie su manuale (regola permanente dell'utente): cambia solo
  che cosa governa in Mike.

### Passo 2 - Cash out intelligente
Resta com'e' (tre condizioni: 3 o piu' gol; profitto a meno di 2 punti dalla soglia in fase calda;
il modello dice che aspettare vale meno che chiudere; mai sotto il 2 % del capitale impegnato) e
parte da solo (M4.3).

### Passo 3 - Uscita in perdita
DECISIONE dell'utente (29/09): «la teniamo come proposta, esattamente com'e' ora, decido io».
- Resta tutto com'e': si valuta all'intervallo o fra il 46' e l'85', con 3 o 4 gol; confronto fra
  «chiudo adesso» e «tengo fino alla fine» col modello (margine di prudenza 10 % per la probabilita'
  del quarto gol); senza modello, regola fissa del 25 %.
- Resta una PROPOSTA da firmare (urgente). Se l'utente non firma, Mike non chiude.
- Nessuna modifica. E' l'unica famiglia di uscite che resta governata dalla firma dell'utente.
- Ancora da decidere (non chiesto all'utente in questo passo): una rete automatica di perdita
  quando l'utente non risponde. Oggi l'unica e' il tetto al 100 % del capitale impegnato (passo 4).

### Passo 4 - Tetto di perdita della partita
DECISIONE dell'utente (29/09): «toglilo».
- Oggi: se la perdita, chiudendo tutto adesso, raggiunge il 100 % del capitale impegnato
  (`event_loss_cap_pct` 100), Mike chiude tutto da solo, anche in manuale. Con la copertura in
  piedi la perdita massima e' proprio il 100 % e ci si arriva solo a partita finita con 4 gol
  esatti: in pratica non scatta quasi mai.
- **M4.5 - Il tetto di perdita della partita si toglie.** Mike non chiude mai in perdita da solo:
  l'unica chiusura in perdita e' quella proposta e firmata dall'utente (passo 3).
  - Per il tecnico: ramo «loss_cap» di `_decide_covered` (`Betfair/mike/engine.py:3579-3583`),
    parametro `event_loss_cap_pct` (0 = spento), e i punti in cui il tetto fa decadere una
    proposta (`gate_uscite`). Da decidere in implementazione se togliere il ramo o portare il
    parametro a 0 di serie: il risultato per l'utente e' lo stesso.
- CONSEGUENZA scritta all'utente: dopo questa modifica, in gioco, nessuna chiusura in perdita parte
  senza la sua firma.

### Passo 5 - Come Mike esegue una chiusura
DECISIONE FINALE dell'utente (29/09): «Lasciamo a 10 secondi, ignora la modifica precedente».
**M4.6 e' ANNULLATA: il riprezzo resta a 10 secondi, nessuna modifica.** (Prima aveva detto «alzerei
il riprezzo a 20 secondi»; ha cambiato idea dopo aver saputo che lo stesso parametro governa anche
il riprezzo della copertura. Il testo qui sotto resta solo come memoria.)
- Resta com'e': un ordine di chiusura per ogni selezione aperta, al miglior prezzo; niente chiusura
  su una selezione gia' decisa dai gol; residuo sotto 1 centesimo al regolamento; massimo 20
  tentativi (`close_max_attempts` 20), poi Mike resta in attesa dell'abbinamento.
- **M4.6 - Il riprezzo di una chiusura ferma passa da 10 a 20 secondi** (`close_retry_s` da 10 a
  20). E' un cambio di PARAMETRO ordinato dall'utente.
  - Per il tecnico: valore di serie in `Betfair/mike/config.py`; va aggiornato anche il valore
    salvato nel database dei parametri di Mike (lo cambia l'utente dall'app, oppure migrazione), il
    pannello dei parametri e la tabella `12_tutti_i_parametri` della guida. Verificare quali rami
    leggono `close_retry_s` (chiusura in gioco, chiusura manuale, riprezzo della copertura) e dire
    all'utente se il nuovo valore tocca anche quelli.
- Conseguenza: con 20 tentativi a 20 secondi, una chiusura che non si abbina viene riprezzata per
  circa 6-7 minuti invece di 3-4.

### PRINCIPIO dell'utente sugli ordini (29/09)
Parole sue: «MIKE deve assicurarsi che tutti gli ordini da lui gestiti siano abbinati, chiusi,
loggati. DEVE ESSERE SEMPRE AL CORRENTE DI QUELLO CHE SUCCEDE, SPECIALMENTE PER GLI ORDINI».
E' la regola permanente «consapevolezza degli ordini». Ogni modifica di questo piano va provata
anche su questo: per ogni ordine nuovo (banca Under 4,5 di copertura, punta Under 4,5 di chiusura,
ultimo ingresso, banche che restano fino al fischio) Mike deve sapere se e' abbinato, abbinato in
parte, in coda, cancellato da Betfair, rifiutato o a esito ignoto, e scriverlo nel registro.
Criteri di accettazione: controlli di condotta del banco (K5, K6, S1-S4, UF1-UF3) a 0 violazioni.

---

## Punto 5 - Importi e cash out: cosa dice la documentazione (verifica del 29/09)

Richiesta dell'utente: «controlla attentamente nella documentazione come funziona il cash out,
dato che dal sito di Betfair appare e sia back che lay permettono di chiudere qualsiasi importo».

### Fonti lette
| Fonte | Dove | Cosa dice |
|---|---|---|
| Betfair, assistenza sviluppatori, «Is 'Cashout' available via the Betfair API?» | in rete (support.developer.betfair.com, articolo 115003887431) | «The 'Cashout' functionality isn't available via the API as an operation.» |
| Betfair, «Betting On Italian Exchange», regole dell'Exchange italiano | in rete (documentazione ufficiale, pagina 2687808) | «The stake for each back offer is a minimum of 200 Euro Cents and can only be incremented in multiples of 50 Euro Cents.» e «Any lay offers placed by the customer, must be placed in such a way as to ensure that the stake for any corresponding back offer amounts to a minimum of 50 Euro Cents.» e «placeOrders request containing both back and lay bets in the same order will be rejected.» |
| Betfair, placeOrders | in rete (pagina 2687496) | «Please note that additional bet sizing rules apply to bets placed into the Italian Exchange.» |
| NEL REPO: `Betfair/stream/trading/PLACE_AND_TRIM_INDAGINE_2026-09-17.md`, par. 8 | ordini REALI del 17/09 sul listino italiano, in gioco | PUNTA 2,25 piazzata diretta: RIFIUTATA (importo non multiplo di 0,50); PUNTA 1,21: rifiutata 171 volte; BANCA 2,25 diretta: ACCETTATA; BANCA 1,21: ACCETTATA; bancate da 0,50 e 0,01 messe a mano dal sito: abbinate |
| NEL REPO: `Betfair/Betfair_api_documentation.pdf` | 62 pagine | non parla di cash out ne' delle regole italiane (rimanda a una documentazione separata per Spagna e Italia) |

### Cosa se ne ricava
1. **Il pulsante Cash Out esiste solo sul sito.** Per un programma non c'e' un comando «cash out»:
   Mike deve piazzare da solo gli ordini che chiudono la posizione.
2. **I limiti di importo valgono per le PUNTATE, non per le BANCATE.** Puntata: minimo 2,00 EUR e
   solo multipli di 0,50. Bancata: minimo 0,50 EUR, poi al centesimo. Confermato dalla regola
   ufficiale e dai nostri ordini veri.
3. **In un mercato a due esiti (Under / Over) puntare un esito equivale a bancare l'altro.** Quindi
   ogni chiusura si puo' scrivere come BANCATA, scegliendo la selezione giusta:

| Cosa serve | Scritto come puntata (con i limiti) | Scritto come bancata (senza i limiti) |
|---|---|---|
| Coprire l'Under 3,5 | punta Over 4,5 | **banca Under 4,5** (decisione M3.1) |
| Chiudere l'Under 3,5 | - | banca Under 3,5 (e' gia' cosi') |
| Chiudere la copertura | punta Under 4,5 | **banca Over 4,5** |

   Esempio, copertura banca Under 4,5 12,63 a 1,18, da chiudere con l'Under 4,5 sceso a 1,05:
   puntando l'Under 4,5 servono 14,19 EUR (non multiplo di 0,50: non parte diretta); bancando
   l'Over 4,5 servono 0,71 EUR a quota 21. Il risultato bloccato e' lo stesso (-1,56).
4. **Resta un caso scoperto:** quando la bancata equivalente scende sotto 0,50 EUR (esempio: Under
   4,5 a 1,02, bancata Over 4,5 da 0,28) e la puntata non e' multiplo di 0,50. Li' resta solo il
   «piazza e riduci» passivo di oggi.

### DECISIONE dell'utente (29/09): «ok»
Casistica: quando Mike, dopo essersi coperto bancando l'Under 4,5, deve chiudere tutta la
posizione (cash out in profitto, uscita in perdita firmata, tetto di perdita) e deve quindi
annullare anche la copertura.
- **M3.3 (riscritta) - Mike annulla la copertura BANCANDO l'Over 4,5** invece di puntare l'Under
  4,5: risultato identico, ma la bancata e' accettata a qualsiasi cifra da 0,50 EUR in su, mentre
  la puntata e' rifiutata se non e' un multiplo di 0,50.
- Se la bancata equivalente e' sotto 0,50 EUR: si usa la puntata se l'importo e' un multiplo di
  0,50 da almeno 2,00; altrimenti il «piazza e riduci» di oggi.

### Proposta piu' ampia del coordinatore (NON decisa: l'utente ha approvato solo la casistica sopra)
- **M5.1 - Ogni ordine di Mike si scrive dal lato in cui l'importo e' piazzabile.** Prima scelta la
  bancata (sull'esito giusto); se la bancata e' sotto 0,50 EUR, la puntata se e' un multiplo di
  0,50 da almeno 2,00; solo in ultimo il «piazza e riduci». La strategia non cambia: cambia solo
  come si scrive l'ordine.
- Da verificare prima: liquidita' sul lato scelto (la bancata sull'Over 4,5 a quota alta pesca da
  chi punta l'Over a quota alta), e il conto della posizione quando sullo stesso mercato ci sono
  ordini sulle due selezioni.
- NON verificato: se una bancata sotto 0,50 EUR passa dall'API (dal sito 0,01 e' passata; dall'API
  i tre tentativi del 17/09 sono caduti per un altro motivo e non sono conclusivi).

---

## Punto 6 - Piatto e rientro sull'Under 4,5

### Cosa vuole l'utente (29/09)
«Il rientro deve cambiare solo una condizione: il numero di gol NON ESATTAMENTE 1, ma 1-2 gol, il
resto delle condizioni resta invariato. MIKE DEVE MONITORARE OVVIAMENTE GLI ORDINI: se il lay non
si abbina deve saperlo; in live ci possono essere sospensioni che cancellano i nostri ordini LAPSE,
ovviamente deve saperlo.»

### Cosa resta com'e' oggi
Un solo rientro per partita; solo dopo una chiusura in profitto; mai dopo una chiusura fatta a mano
dall'utente; entro il 45'; quota dell'Under 4,5 piu' alta della quota del primo ingresso; liquidita'
di almeno 10 EUR; prezzi vivi e mercato aperto; puntata 10 EUR al miglior prezzo; banca a 2 tick
sotto (che parte da sola: M4.4) e resta sul mercato fino a fine partita; se Betfair la cancella
per una sospensione, Mike la rimette alla riapertura.

### Cosa va cambiato
- **M6.1 - Il rientro si fa con 1 o 2 gol segnati** (oggi: esattamente 1).
  - Per il tecnico: `reentry_max_goals` oggi vale 1 con limiti 0-1 (`Betfair/mike/config.py:296`):
    portare il valore di serie a 2 e il limite massimo ad almeno 2; il minimo di 1 gol e' scritto
    nel codice (`engine.py:3690-3692`, «gol < 1») e resta. E' un cambio di PARAMETRO ordinato
    dall'utente: va aggiornato anche il valore salvato nel database, il pannello e la guida.
- **M6.2 - In live Mike deve poter rileggere un suo ordine per numero di scommessa.** Oggi, in live,
  se una banca appoggiata non abbinata sparisce dagli ordini correnti (per esempio cancellata da
  Betfair a una sospensione), Mike non riesce a sapere com'e' finita: la segna «esito ignoto» e la
  manda in riconciliazione (`Betfair/mike/service.py:2491-2496`: cerca `order_state_by_bet_id`, che
  lo sportello di produzione `_RealMarket` non ha). Nel banco di replay invece quella lettura
  esiste: il replay prova una strada che la produzione non ha. DIFETTO contro la regola
  dell'utente, da correggere.
- **M6.3 - La sospensione va letta dal mercato GIUSTO.** Oggi Mike legge la sospensione solo dal
  mercato Under 3,5, anche per la banca del rientro che sta sull'Under 4,5
  (`Betfair/mike/service.py:2881-2882`). Con la copertura e la sua chiusura sul mercato 4,5 (M3.1,
  M3.3) conta ancora di piu'. DIFETTO, da correggere.
- Criterio di accettazione: scenario di replay con sospensione per gol mentre la banca del rientro
  e' appoggiata, e scenario con la banca della copertura/chiusura sul mercato 4,5: Mike deve dire
  «cancellata da Betfair» (non «esito ignoto») e rimetterla alla riapertura.

---

## Punto 7 - La proposta, la firma e l'esito della chiusura

### Cosa vuole l'utente (29/09)
«LE FIRME DEVONO AGGIORNARSI IN TEMPO REALE, gia' detto mille volte. Ovviamente se in quel
frangente, dal click all'ordine, succede qualcosa non possiamo fare nulla. MA mi deve essere
restituita dalla scheda il fatto che il cash out sia effettivamente stato fatto e che su
quell'evento non abbiamo altra esposizione.»

### Decisioni
| Cosa | Decisione |
|---|---|
| Le cifre della proposta | si aggiornano IN TEMPO REALE, finche' la proposta e' a video |
| Fra il clic e l'ordine il mercato si muove | si accetta: Mike esegue ai prezzi di quel momento. NESSUN blocco sull'importo, nessun margine |
| Dopo la chiusura | la scheda deve dire che la chiusura e' stata FATTA davvero e che sulla partita NON resta esposizione |

### Cosa fa il codice oggi
- La proposta mostra gia' due cifre: «chiudendo ora» e «alla decisione», piu' l'eta' della
  decisione. Le cifre le calcola il bot a ogni giro; l'app le rilegge a ogni notifica in tempo
  reale (raggruppate entro 1,5 secondi) e comunque ogni 15 secondi.
- Col feed fermo o ignoto il pulsante «approva uscita» e' spento.
- Dopo il clic la scheda scrive solo «approvazione inviata: parte al prossimo giro del bot».

### Cosa va cambiato
- **M7.1 - Cifre della proposta vive.** La cifra «chiudendo ora» deve seguire i prezzi col canale
  al millisecondo (via principale; la rilettura ogni 15 secondi resta solo come ripiego), con
  l'eta' del dato a video. DA MISURARE prima: il ritardo vero di oggi fra prezzo e cifra a video.
- **M7.2 - L'esito della chiusura torna nella scheda.** Dopo ogni chiusura (firmata dall'utente O
  partita da sola) la scheda mostra, in quest'ordine: «chiusura in corso» con gli ordini e quanto e'
  abbinato; poi «CHIUSA: risultato bloccato X,XX EUR - nessuna esposizione residua su questa
  partita»; oppure «NON COMPLETA: resta esposizione di X,XX EUR su <selezione>, tentativo n di 20».
  L'assenza di esposizione si dichiara sui conti degli ordini ABBINATI (riletti da Betfair), non
  sulla convinzione del bot.
- **M7.3 - Nessun controllo sull'importo alla firma** (resta com'e'): scritto qui perche' sia una
  scelta e non una dimenticanza.
- Per il tecnico: `frontend/src/components/controlroom/PropostaUscitaMike.tsx`, `SchedaMike.tsx`,
  `trovaEsitoUscita.ts`, `certezzaChiusura.ts`, `pages/Mike.tsx`; bot: `gate_uscite`
  (`Betfair/mike/engine.py:2337`), pubblicazione delle proposte, `_decide_closing` 3606.
