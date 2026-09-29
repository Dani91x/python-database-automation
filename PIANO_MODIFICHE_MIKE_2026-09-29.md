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
