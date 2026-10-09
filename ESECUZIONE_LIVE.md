# ESECUZIONE LIVE — specifica unica per Omega, Safe e Mike
**14/09/2026 · coordinatore `admin-30` · vincolante per le tre sessioni**

> **LA REGOLA, e non ha eccezioni.** Dettata dall'utente il 14/09, testualmente:
> *«Le strategie che stiamo testando in demo devono essere le stesse identiche che andranno in live.
> Non modificare le strategie. Le strategie sono progettate così e devono restare così.
> L'unica differenza è live o paper.»*
>
> Fra paper e live può cambiare **soltanto se i soldi sono veri**. Mai **quale ordine** viene piazzato,
> **a che prezzo**, **con che tipo di esecuzione**, **con che tempi**, **con che persistenza**.
> Se per far funzionare il live servisse cambiare un comportamento della strategia, **ci si ferma e si
> scrive al coordinatore**: non lo si decide.

---

## 1 · IL DIFETTO, E LA SUA CAUSA VERA

Mike pre-match è progettato così, e in paper fa esattamente questo:

```
   back Under 3.5 @ 1,50 · 10 €
   → lay 10,14 @ 1,48 APPOGGIATO sul book (−2 tick), lasciato lì
   → si aspetta che qualcuno lo prenda
   → ciclo chiuso PIATTO in profitto su ogni risultato
```

In **live** il bot non fa questo. `Betfair/mike/service.py:722-737` (`_live_exit_override`) forza
`pre_exit_mode='taker'` su qualunque partita live: invece di appoggiare, **attraversa lo spread**.

**Perché quell'interruttore è stato messo — ed è qui la causa vera, non nel codice di Mike:**

> `Betfair/mike/feed.py:284` — il percorso **REST** piazza **comunque FILL_OR_KILL** a prezzo limite.
> Un ordine FILL_OR_KILL **per definizione non può restare sul book**: o si abbina subito per intero,
> o viene annullato. **Su REST un ordine appoggiato non esiste.**

Quindi l'override non è un capriccio: è la conseguenza di aver mandato gli ordini live su un percorso
che **non sa fare** ciò che la strategia richiede. La correzione non è togliere l'override e sperare:
è **mandare gli ordini live sul percorso che sa farlo**, e poi togliere l'override.

## 2 · IL PERCORSO GIUSTO ESISTE GIÀ. NON SE NE COSTRUISCE UNO NUOVO.

`Betfair/stream/` contiene già tutto, scritto e documentato:

| Pezzo | File | Cosa fa |
|---|---|---|
| Runner flumine | `Betfair/stream/runner.py` | processo che tiene la connessione allo stream |
| Coda ordini live | `betfair_live_order_requests` | richieste `place`/`cancel`/`replace`/`place_submin` |
| Worker | `Betfair/stream/live_order_worker.py` | claim atomico `pending→processing`, una sola esecuzione per riga |
| Costruzione ordine | `Betfair/stream/live_order_build.py` | validazione, ultima barriera money-critical |
| Piazzamento | API native del `Market` di flumine | `place_order` / `cancel_order` / `replace_order` |
| **Fill** | **order stream** | *«Il fill (size_matched/avg_price) arriva **ASINCRONO** — LIVE via `order_stream`, PAPER via `SimulatedExecution`»* (docstring del worker) |
| Place-and-trim | `Betfair/stream/trading/submin.py` | qualunque importo fino a 0,01 € |

**Questo è il «canale WS» per gli ordini.** Lo stream di Betfair non serve solo per i prezzi: la
sottoscrizione **ORDER** spinge gli aggiornamenti di abbinamento in millisecondi, invece di scoprirli
interrogando periodicamente. È la via più rapida che abbiamo, ed è già cablata.

> 🔴 **MA IL RUNNER FLUMINE È FERMO DAL 2 SETTEMBRE** (`COSTITUZIONE_MIKE.md` §16.5 punto 4:
> *«Non serve al percorso REST di Mike, ma finché è fermo la coda non è una via di riserva»*).
> **Finché è fermo, nessun bot può piazzare un ordine appoggiato in live.**
> Riaccenderlo è la precondizione numero uno di tutto questo documento.

## 3 · CHE COSA DEVE FARE OGNI BOT IN LIVE

**Regola di instradamento, unica per i tre:**

| Il bot vuole… | Percorso | Perché |
|---|---|---|
| un ordine che **resta sul book** (maker: green-up appoggiato, uscita a −N tick, ingresso a limite) | **coda flumine** | REST è FILL_OR_KILL e non può farlo |
| un ordine che **deve abbinarsi subito o niente** (taker, protezioni, chiusure d'emergenza) | REST **oppure** coda | FILL_OR_KILL qui è corretto, è la semantica voluta |
| qualunque importo **sotto il minimo di giurisdizione** | place-and-trim (`submin`) | già collegato su entrambi dal 13/09 |

**Persistenza: si rispetta quella della strategia, non se ne sceglie una comoda.** Mike la dichiara già
gamba per gamba (`engine.py:128, 273` default `LAPSE`; `PERSIST` sull'ultimo ingresso, `engine.py:1954`).
Il percorso di esecuzione deve **trasportarla**, non sostituirla.

**Ogni bot, in live, deve piazzare lo stesso ordine che piazza in paper**: stesso lato, stesso prezzo,
stessa dimensione, stessa persistenza, stesso momento. L'unica differenza legittima è che in paper si
scrive una riga simulata invece di chiamare Betfair.

## 4 · VELOCITÀ — «gli ordini il più rapidi possibile»

1. **Sapere prima**: il fill arriva dall'**order stream** in push. Nessun polling di
   `listCurrentOrders` per scoprire un abbinamento: il polling resta solo come riconciliazione lenta di
   sicurezza, mai come via principale.
2. **Non pagare la coda due volte**: la richiesta va scritta e presa dal worker senza attese inutili.
   Si misura e si scrive nel registro: **istante della decisione → istante della scrittura in coda →
   istante del claim del worker → istante della risposta di Betfair → istante del fill**. Cinque numeri.
   Senza questi, «rapido» è un'opinione.
3. **Riportare subito**: appena il fill arriva, va spinto sui **canali locali** (47333/47334/47335) così
   la UI lo vede senza aspettare il giro del database. Il canale c'è e funziona: si riusa.
4. **Nessuna chiamata Betfair duplicata.** Regola di piattaforma già in vigore: il feed è unico
   (`scan_feed.py`). Vale anche per gli ordini — un solo percorso, non due in parallelo.

## 5 · CHE COSA DEVE VEDERE IL TRADER (obbligatorio, non opzionale)

Tutto quello che sopra è invisibile va reso visibile. Su **ogni** pagina dei bot e nella **Control Room**:

- **Percorso di esecuzione in uso** per quella partita: `coda (stream)` oppure `REST`. Sono due
  comportamenti diversi e il trader deve sapere quale sta guidando.
- **Stato del runner flumine**: acceso/spento, con l'età dell'ultimo battito. **Se è spento, va detto
  che gli ordini appoggiati non sono disponibili** — e le schede delle strategie che ne dipendono
  devono dichiararlo, non lasciarlo scoprire dai numeri.
- **I cinque tempi** del punto 4, almeno l'ultimo (decisione → fill) sulla riga dell'operazione.
- **Esito onesto**, come già fa `InvestAction.placementOutcome`: parziale è parziale, in coda è in coda,
  deduplicato è deduplicato, ignoto è ignoto. Mai «eseguito» per nessuno di questi quattro.
- **Ordine annullato ≠ errore.** Oggi un annullo legittimo di Mike viene scritto `status='error'`: va
  distinto, altrimenti la tabella accusa il bot di un guasto che non c'è.

## 6 · ORDINE DEI LAVORI

```
 0. RIACCENDERE IL RUNNER FLUMINE            → precondizione di tutto (fermo dal 2/09)
 1. Instradare gli ordini MAKER sulla coda    → Mike (uscita appoggiata), poi Omega (green-up), poi Safe
 2. TOGLIERE `_live_exit_override`            → solo DOPO che 1 è verde e provato sul campo
 3. Onestà del paper: `_resting_filled`       → serve volume scambiato, non il semplice tocco
 4. Strumentare i cinque tempi                → senza misura «rapido» non significa niente
 5. Portare tutto in UI (§5)                  → ciascuno la propria pagina, io la Control Room
```

**Il punto 2 non si fa prima del punto 1.** Togliere l'override senza il percorso che sa appoggiare
significherebbe mandare in live ordini che non si abbinano mai, e sarebbe peggio di adesso.

## 7 · CHE COSA NON SI TOCCA

Prezzi, tick, soglie, minuti, punteggi, cicli, pause, persistenze, condizioni di ingresso e di uscita.
**Nessuna.** Questo documento riguarda **come l'ordine arriva a Betfair**, non che cosa la strategia decide.

E resta in vigore la regola gemella: **niente che protegge può impedire di chiudere.** Un freno, un cap,
un semaforo di freschezza, un runner spento possono fermare un'**apertura**; nessuno di essi può fermare
un'**uscita**.
