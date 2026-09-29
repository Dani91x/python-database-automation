# Piano delle modifiche a Mike (29/09/2026)

Questo documento raccoglie, punto per punto, cio' che l'utente decide su Mike durante la revisione
con la guida (`SCHEMI_BOT/mike/GUIDA_MIKE.html`).

**Regola dell'utente (29/09): NESSUNA modifica al codice parte finche' la revisione non e' finita.
Alla fine si fa il riepilogo, l'utente lo approva, e SOLO ALLORA si parte.** Fino ad allora questo
file si aggiorna e basta.

Per ogni punto: cosa vuole l'utente, cosa fa il codice oggi, cosa va cambiato, cosa resta da
chiarire. I riferimenti al codice servono a chi fara' la modifica.

Stato: **IN RACCOLTA** (nessuna modifica eseguita).

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

### Da chiarire con l'utente
1. **L'ultimo ingresso** (la puntata da 10 EUR a 10 minuti dal fischio, fatta oggi solo dopo una
   chiusura in profitto): resta? Con la banca che non si ritira piu', a 10 minuti dal fischio Mike
   puo' essere gia' piatto (giro chiuso) oppure in posizione con la banca in attesa.
2. **Nuovi giri negli ultimi 10 minuti**: oggi Mike non apre giri nuovi da 10 minuti prima del
   fischio. Resta cosi', o i giri continuano fino al fischio?
3. **Il veto sull'Under 3,5**: non potendo piu' chiudere in perdita, a cosa serve? Solo a non
   entrare (blocca gli ingressi nuovi), oppure si spegne del tutto?
4. **La modalita' «al mercato» della banca** (Mike aspetta che il prezzo scenda di 2 tick e poi
   banca al volo), oggi spenta: si toglie o resta come opzione?
5. **Al fischio, con la banca non abbinata**: Mike entra in gioco con l'Under 3,5 aperto. Cosa deve
   fare da li' lo si decide nel punto «dal fischio d'inizio» (oggi: nuova banca 2 tick sotto per 3
   minuti, poi copertura Over 4,5).

---

## Registro delle decisioni

| # | Data | Decisione dell'utente | Stato |
|---|---|---|---|
| 1 | 29/09 | Pre-partita: banca a 2 tick sotto SUBITO dopo l'ingresso, sempre, poi niente altro; 60 s e nuovo giro se abbinata, fino a 10 giri; se non abbinata resta li' | confermata, da implementare (M1.1) |
| 2 | 29/09 | La banca di chiusura resta li' fino al fischio d'inizio | confermata, da implementare (M2.1) |
| 3 | 29/09 | Nel pre-partita Mike non chiude MAI in perdita | confermata, da implementare (M2.2) |
| 4 | 29/09 | La banca di chiusura e' LAPSE: la parte non abbinata la cancella Betfair al passaggio in gioco | confermata; il codice fa gia' cosi'; da aggiungere la lettura di cio' che resta al fischio (M2.3) |
