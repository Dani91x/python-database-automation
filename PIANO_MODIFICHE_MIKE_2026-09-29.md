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

### Da chiarire con l'utente (pre-partita, prossimi punti)
Oggi, a 10 minuti dal fischio, Mike NON «lascia li'» la banca. Fa una di queste cose:
1. **Se il giro e' in profitto**: ritira la banca e chiude subito al prezzo di mercato (chiusura
   finale), poi piazza l'ultimo ingresso.
2. **Se il giro e' in perdita**: ritira la banca e TIENE la posizione fino al fischio.
3. **Se il giro e' in perdita e il veto sull'Under 3,5 dice «veto»** (acceso di serie): ritira la
   banca e **chiude in perdita** al prezzo di mercato, e non fa l'ultimo ingresso.
4. Esiste una seconda modalita' della banca («al mercato»: Mike aspetta che il prezzo scenda di 2
   tick e poi banca al volo), oggi spenta. Tenerla come opzione o toglierla?

Domande: a 10 minuti dal fischio la banca resta li' fino al fischio? Il veto puo' chiudere in
perdita prima del fischio? L'ultimo ingresso resta?

---

## Registro delle decisioni

| # | Data | Decisione dell'utente | Stato |
|---|---|---|---|
| 1 | 29/09 | Pre-partita: banca a 2 tick sotto SUBITO dopo l'ingresso, sempre, poi niente altro; 60 s e nuovo giro se abbinata, fino a 10 giri; se non abbinata resta li' | confermata, da implementare (M1.1) |
