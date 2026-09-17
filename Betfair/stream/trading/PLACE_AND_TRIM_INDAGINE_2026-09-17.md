# Place-and-trim: indagine e sequenza definitiva (17/09/2026)

Ordine dell'utente: «il place-and-trim funziona alla perfezione su tutti i competitor
(Bet Angel, Fairbot): va risolto UNA VOLTA PER TUTTE» e «DEVE ESSERE AGGIUSTATO E RESO
UNIVERSALE PER OGNI CASO CHE CI SERVE PRESENTE E FUTURO».

Reperto di partenza: `CRONOSTORIA.md`, «Reperto 25 (h20:15)».

---

## 1. I fatti (non ipotesi)

Evento 36077571 (Bnei Yehuda v Maccabi Herzliya), Mike in LIVE, 17/09:

- Under 3.5 BACK 5,00 EUR @1.44 abbinata (mike_trades #4886).
- Copertura Over 4.5 (BACK 1,21-1,37 EUR @5.4-5.9): **171 righe `over_cover` in `error`**
  (conteggio certificato sul DB dal delegato di lettura; il primo conteggio parziale
  era 104), tutte con `live_rifiutato:CANCELLED_NOT_PLACED`, dalle 16:03:52Z alle
  16:18:23Z, `minute_at_entry` 2..17, stato `LIVE_UNCOVERED` -> `LIVE_COVER_PENDING`.
- **Storico DB: ZERO coperture sotto minimo riuscite in live**, ne' per Mike ne' per Omega.
- Il rifiuto e' sempre al **gradino 3** (il `replaceOrders`): i gradini 1 (parcheggio) e 2
  (taglio con `sizeReduction`) sono sempre andati a buon fine, con `sizeCancelled` esatto.

**Prima conclusione, dedotta dai nostri stessi dati:** Betfair ACCETTA che un ordine
esistente venga ridotto SOTTO il minimo e resti a riposo sul book (il gradino 2 e'
passato 171 volte su 171). Cio' che non passa e' il **RI-PIAZZAMENTO** dentro il
`replaceOrders`.

---

## 2. La sequenza dei competitor

Bet Angel, «place bets below minimum stake» (guida utente e forum ufficiale):

1. `placeOrders` del minimo a quota lontana (tipicamente BACK @1000), sperando che non si
   abbini;
2. si toglie l'eccedenza (cancel parziale);
3. si **sposta** l'importo residuo alla quota voluta.

E' **esattamente la nostra sequenza**. Bet Angel pero' documenta due cose che noi non
avevamo scritto da nessuna parte:

- «it will take twice as long for bets below [il minimo] to reach the market, **this also
  includes the in-play delay** as you're effectively using two transactions to complete
  the process»;
- «Bet Angel **cannot guarantee** that bets below the minimum value will enter the market
  without error or complications as the process to achieve this is complex».

E sul forum, la raccomandazione operativa: **usare il minimo ufficiale quando si opera
in-play**, perche' sotto il minimo il comportamento in-play non e' lo stesso.

Quindi: i competitor NON hanno una sequenza diversa dalla nostra. Hanno la stessa, con la
stessa fragilita', e lo dichiarano.

---

## 3. Semantica del codice di errore, con la fonte

- **Betfair Exchange API, `replaceOrders`** (developer docs):
  «This operation is logically a **bulk cancel followed by a bulk place**. The cancel is
  completed first then the new orders are placed. [...] In the case where the new orders
  cannot be placed **the cancellations will not be rolled back**.»
  Limite: 60 istruzioni per richiesta.
- **`betfairlightweight/enums.py:196`**:
  `CANCELLED_NOT_PLACED = "Bet cancelled but replacement bet was not placed"`.
  E' l'`errorCode` **ESTERNO** del `ReplaceInstructionReport`.
- **In-play**: «In-play markets usually carry a time delay varying from 1-12 seconds [...]
  The amount of delay your placeOrders/**replaceOrders** requests are subject to can be
  determined from the `betDelay` field in `listMarketBook`.»

Conseguenza: il replace **ri-piazza un ordine NUOVO**, che passa dalla validazione di
piazzamento (minimo di giurisdizione, bet delay, stato del mercato, profit ratio). Un
residuo sotto minimo non e' garantito che la superi.

### 3-bis. Il difetto nostro che ci ha resi ciechi

`CANCELLED_NOT_PLACED` dice **cosa** e' successo, non **perche'**. Il perche' sta nei
report ANNIDATI del `ReplaceInstructionReport`:

```
instructionReports[0].errorCode                       -> CANCELLED_NOT_PLACED   (esterno)
instructionReports[0].cancelInstructionReport.status  -> SUCCESS                (il cancel e' passato)
instructionReports[0].placeInstructionReport.errorCode-> IL MOTIVO VERO         (interno)
```

Il nostro `place_submin_live` leggeva **solo** `rir.get("errorCode")` e buttava via
`placeInstructionReport` e `cancelInstructionReport`; non c'era nessun log del report
completo. **Da 171 rifiuti non abbiamo il codice interno.** Questo e' il primo difetto
corretto (vedi §5).

Cause candidate, per codice interno, e cosa fare per ciascuna:

| codice interno | lettura | cosa fare |
|---|---|---|
| `INVALID_BET_SIZE` | il ri-piazzamento e' validato contro il minimo di giurisdizione: il trucco non passa dal replace | **percorso A** (§4): mai piu' un replace sotto minimo |
| `INVALID_PROFIT_RATIO` | restrizione API anti-abuso del minimo (cambio Betfair del 2020) | parcheggio a quota vicina al target, importi che non «guadagnano» dall'arrotondamento |
| `MARKET_SUSPENDED` / `INVALID_MARKET_STATE` | mercato sospeso nel frattempo | attesa e ripresa alla riapertura (ordine 5 dell'utente) |
| `BET_LAPSED_PRICE_IMPROVEMENT`, `BET_TAKEN_OR_LAPSED` | l'ordine non c'era piu' al momento del ri-piazzamento | ri-lettura dell'ordine e rifiuto dichiarato, mai ritento cieco |
| `INSUFFICIENT_FUNDS` | saldo | rifiuto dichiarato, stop |

---

## 4. La sequenza che adottiamo (e perche' funziona)

Il punto che nessuno aveva messo per iscritto: **il replace serve solo se la quota target
e' ABBINABILE**. Se la quota a cui vogliamo stare NON e' abbinabile (ordine passivo,
resta a riposo), allora si puo' parcheggiare **direttamente alla quota target** e tagliare
li': il gradino 3 sparisce.

### PERCORSO A — «trim in loco» (preferito, 2 chiamate mutanti)

Condizione: la quota target NON e' abbinabile
(BACK: `target > best_back`; LAY: `target < best_lay`).

1. `placeOrders` del minimo **ALLA QUOTA TARGET**, `persistenceType: LAPSE`, senza
   `timeInForce` (deve restare a riposo);
2. `cancelOrders` con `sizeReduction = minimo - importo voluto`;
3. verifica **fail-closed** su `listCurrentOrders` per `betId`: residuo <= target.
   Se la lettura non conferma -> ritiro TOTALE e rifiuto dichiarato.

Nessun `replaceOrders` -> `CANCELLED_NOT_PLACED` non puo' proprio accadere. E' il percorso
sostenuto dai nostri dati: il gradino 2 e' quello che Betfair ha sempre accettato.

### PERCORSO B — parcheggio lontano + replace (fallback, 3 chiamate mutanti)

Condizione: la quota target E' abbinabile (ordine aggressivo) **oppure il book non e'
noto** (IGNOTO = conservativo).

E' la sequenza storica. Si prova **UNA volta sola**, si legge il report completo e si
dichiara il rifiuto **col codice interno**. Nessun ritento dentro la funzione.

### Il caso di Mike, detto chiaro

`Betfair/mike/engine.py:1525-1542` (`cover_place_price`) piazza la copertura
`cover_place_at_ticks` tick **SOTTO** il best back: per un BACK una quota piu' bassa e'
**aggressiva**, quindi la copertura di Mike cade nel **percorso B**. Con gli importi esatti
sotto minimo, in-play, quella strada e' quella che Betfair ci ha rifiutato 171 volte.

**Divergenza da portare all'utente (NON decisa qui, la strategia non si tocca):** per
coprire davvero, sotto minimo e in-play, restano tre strade, tutte strategiche:

1. `exact_sizes = false`: la copertura si arrotonda al minimo .it (2,00 EUR) e passa dal
   place normale. Nessun trucco, nessun rifiuto. Costo: si copre piu' del dovuto
   (overshoot, vedi `cover_max_overshoot_pct`).
2. copertura **passiva** sotto minimo (percorso A): si piazza a una quota NON abbinabile
   (>= best back) e si aspetta che il mercato venga da noi. Entra meno spesso, ma entra
   all'importo esatto. E' un cambio del criterio di prezzo: decide l'utente.
3. nessuna copertura quando l'importo e' sotto minimo (fail-closed dichiarato).

---

## 5. Cosa e' stato implementato

Nucleo UNICO in `Betfair/stream/trading/submin.py` (funzioni pure, nessuna rete):

- `quota_non_abbinabile(side, price, best_back=, best_lay=)` -> `True|False|None`
  (`None` = book ignoto = si tratta come «potrebbe abbinarsi»);
- `pianifica_submin(...) -> PianoSubmin` : decide percorso A o B, quota e size del
  parcheggio, `size_reduction`, se serve il replace, **quante chiamate mutanti costa**;
- `esito_istruzione(report)` : normalizza un report Betfair leggendo anche i report
  ANNIDATI (`placeInstructionReport`, `cancelInstructionReport`);
- `codice_rifiuto(esito)` : `"ESTERNO:INTERNO"`, cosi' il codice vero arriva al DB.

Due adattatori, stessa sequenza, nessuna copia:

- **REST**: `Betfair/omega/omega_market.py::place_submin_live` (usato da Mike, Omega,
  Safe via `market.place_submin_live`). Legge il book da solo se il chiamante non passa
  `best_back`/`best_lay`; verifica il taglio su `listCurrentOrders`; logga il report
  completo del replace a livello `critical`.
- **flumine**: `start_submin` / `advance_submin` nello stesso file. `SubminState` porta
  ora `park_price` e `serve_replace`; con `park_price=0.0` (stato persistito da una
  versione precedente) il comportamento e' identico a prima (percorso B).

Fail-closed applicati: parcheggio abbinato -> ritiro + abort senza ritento; taglio non
confermato dal report **o** dalla lettura dell'ordine -> ritiro totale + rifiuto
dichiarato; ritiro fallito -> esito IGNOTO propagato (riconciliazione), mai «annullato».

Fill-or-kill + quota non abbinabile sono incompatibili: si dichiara il rifiuto
(`SUBMIN_NESSUNA_CONTROPARTE`) **prima** di toccare Betfair, zero chiamate mutanti.

---

## 6. Cosa NON e' verificato (e come lo si verifica)

Non abbiamo, e non possiamo avere senza toccare i soldi, la prova del comportamento reale
di Betfair in-play:

- il codice INTERNO dei 171 rifiuti (non lo avevamo salvato);
- se il percorso A in-play regga davvero (nessun successo storico da mostrare).

**Serve il test dedicato dal vivo con l'utente.** Procedura in
`Betfair/mike/CHECKPOINT_2026-09-17_SERA.md`, §«Test dal vivo».
