# CHECKPOINT 17/09/2026 sera — Mike: place-and-trim, freno, stato del mercato

Riferimenti: `CRONOSTORIA.md` «Reperto 25 (h20:15)» e «ORDINI DELL'UTENTE su Mike (h20:25)»;
indagine completa in `Betfair/stream/trading/PLACE_AND_TRIM_INDAGINE_2026-09-17.md`;
contratto del modulo unico in `Betfair/stream/trading/INTERFACES.md` (sezione finale).

Nessun commit. Nessuna scrittura DB. Nessun ordine reale. `.env` non toccato.

---

## 1. Ordine 1 — «Mike in pre-match NON deve operare su Over 4.5»

**Accertato sul DB e sul codice: NON e' successo.** La premessa non trova riscontro.

- Transizione a LIVE: **16:00:59Z** (`HOLD -> LIVE_KO_GREEN`, ~1' dopo il `ko_at`
  16:00:00Z). Alle **16:03:52Z** `LIVE_KO_GREEN -> LIVE_UNCOVERED`, motivo «uscita non
  abbinata in 3': copertura Over 4.5» (esattamente `ko_green_window_s`=180 s).
- Da li' partono le righe `over_cover`: **171** (non 104), tutte `status=error`,
  `live_rifiutato:CANCELLED_NOT_PLACED`, fino alle 16:18:23Z. `minute_at_entry` 2..17 =
  minuto di GIOCO; **nessuna riga `over_cover` con `minute_at_entry=null`** (il marcatore
  pre-match). `mike_control.stopped_at` 16:19:07Z.
- Codice: `Betfair/mike/engine.py:2012-2014` manda TUTTI gli stati `PRE_*` a
  `_decide_prematch`, che non emette mai `over_cover`; l'unico cancello verso il live e'
  `engine.py:2099` `if snap.inplay:`; l'unico punto che emette `over_cover` e'
  `_decide_uncovered`, `engine.py:2801`.
- Costituzione: `COSTITUZIONE_MIKE.md` righe 22-24, 50-52, 99-103, **142 («Fase 3 — Live:
  copertura sull'Over 4.5»)**, 1188-1190 (strada B: finestra scaduta senza gol -> copertura
  piena), 1202-1213 (le due tranche, «dal gol» / «dall'abbinamento della prima»).

**VERDETTO: il codice NON viola la costituzione su questo punto; nessuna modifica fatta.**
Il danno reale non e' stato di fase: e' stato che le 171 coperture sono state RIFIUTATE da
Betfair e la posizione Under 3.5 e' rimasta scoperta ~15 minuti.

**Divergenza da portare all'utente:** `COSTITUZIONE_MIKE.md` riga 11 dice ancora
«paper non ancora certificato [...] live BLOCCATO» (aggiornata al 12/09), mentre l'evento
36077571 del 17/09 e' `mode=live` con soldi veri. Documento e realta' non coincidono.

---

## 2. Ordine 2 — place-and-trim «una volta per tutte» (+ universale)

### La diagnosi

I gradini 1 (parcheggio del minimo) e 2 (taglio con `sizeReduction`) sono passati **171
volte su 171**, con `sizeCancelled` esatto. **Quindi Betfair accetta un ordine ridotto
sotto il minimo che resta a riposo sul book.** Cio' che fallisce e' SOLO il gradino 3, il
`replaceOrders`, che per documentazione e' «a bulk cancel followed by a bulk place»: il
ri-piazzamento passa dalla validazione di piazzamento (minimo, bet delay in-play, stato
del mercato) e un residuo sotto minimo non la supera.

Bet Angel usa **la nostra identica sequenza** e dichiara essa stessa che «cannot guarantee
that bets below the minimum value will enter the market without error», e che in-play
serve il doppio del tempo perche' sono due transazioni; sul forum raccomandano il minimo
ufficiale quando si opera in-play. Non esiste una sequenza magica dei competitor.

### Il difetto nostro che ci ha resi ciechi

`CANCELLED_NOT_PLACED` e' l'`errorCode` **ESTERNO**. Il motivo VERO sta in
`instructionReports[0].placeInstructionReport.errorCode`. Il vecchio codice leggeva solo
l'esterno e buttava via i report annidati: **da 171 rifiuti non abbiamo il codice interno.**

### La soluzione adottata

- **PERCORSO A** («trim in loco», 2 chiamate mutanti): se la quota target NON e'
  abbinabile, si parcheggia il minimo **direttamente alla quota target** e si taglia li'.
  Nessun `replaceOrders` -> `CANCELLED_NOT_PLACED` non puo' accadere.
- **PERCORSO B** (3 chiamate mutanti): quota target abbinabile, oppure book ignoto ->
  parcheggio lontano + replace, **un solo tentativo**, rifiuto dichiarato col codice
  `ESTERNO:INTERNO` e report completo nel log `critical`.

**Il caso di Mike cade nel percorso B**: `engine.py:1525-1542` (`cover_place_price`) piazza
la copertura `cover_place_at_ticks` tick **sotto** il best back, cioe' AGGRESSIVA. Con
importi esatti sotto minimo, in-play, e' la strada che Betfair ci ha rifiutato 171 volte.

**Decisione che spetta all'utente (strategia, non la tocco):**
1. `exact_sizes = false` -> copertura arrotondata a 2,00 EUR, place normale, zero trucchi;
2. copertura **passiva** sotto minimo (percorso A) a quota >= best back: entra meno spesso
   ma all'importo esatto;
3. nessuna copertura quando l'importo e' sotto minimo (fail-closed dichiarato).

---

## 2-bis. Ordine 3 — freno fail-closed sui rifiuti ripetuti (VERIFICATO DA ME)

Costruito da un delegato Opus, **verificato da me**: diff riletto riga per riga, suite
rilanciata, falsificazione rifatta di persona in direzioni che il delegato non aveva
provato.

- `Betfair/mike/config.py`: **`cover_rifiuti_max`** (3, int, 1..20) e **`cover_retry_min_s`**
  (15, int, 1..300). Nessuna soglia di strategia toccata: e' un freno sui RIFIUTI, non un
  tetto sui tentativi di una strategia.
- `Betfair/mike/engine.py`: `MatchCtx.cover_rifiuti` / `cover_mercato`;
  `registra_rifiuto_copertura` (conta **per codice d'errore**, non per prezzo — e' il
  motivo per cui `tentativo_gia_rifiutato` non vedeva i 171: la copertura ricalcola
  prezzo e size a ogni giro), `copertura_bloccata`, `segna_tentativo_copertura`,
  `attesa_ritento_copertura`, `sblocca_copertura`, `copertura_in_corso`,
  `COVER_BLOCCATA = "LIVE_COVER_BLOCKED"`, e la guardia unica `_freno_copertura`
  chiamata in `decide()` **prima** di `_mai_sovracopertura`.
- `Betfair/mike/service.py`: `_CTX_FIELDS` + `cover_rifiuti`/`cover_mercato` (persistenza:
  un riavvio non azzera il conteggio); barriera fail-closed in `execute_place` (seconda
  rete); orologio del ritmo fatto partire **prima** della chiamata; `place_rifiutato` con
  `conteggio`/`max`; attivita' `error` `critical` allo scatto; «Riprendi» dalla UI
  (`resume_event`) sblocca.
- **Il freno NON tocca le uscite**: filtra solo `role == "over_cover"`; uscite, green-up,
  chiusure e cash out passano. Verificato da me con la mutazione «il freno toglie tutto»
  (`kept = []`) → rosso su `test_il_freno_NON_ferma_le_USCITE_ne_le_CHIUSURE`.
- **Nessuna migrazione SQL**: `LIVE_COVER_BLOCKED` vive in `mike_events.ctx` (JSON) e nei
  payload delle attivita', non in `E.STATES` (che ha un `CHECK` sul DB e un contratto con
  il frontend). Lo stato della partita resta `LIVE_UNCOVERED`, che e' la verita' economica.

## 2-ter. Ordine 5 — stato del mercato durante la copertura (VERIFICATO DA ME)

Cosa c'era: `operabile(bk)` era gia' dentro la condizione di `_decide_uncovered`, ma il
motivo era muto («attendo per coprire»), indistinguibile dall'attesa intelligente. **Due
buchi veri**: (a) `_decide_cover_pending` (il riprezzo `cancel`+`place`) **non guardava
affatto** lo stato del mercato — a mercato sospeso il cancel sarebbe partito e il place no,
lasciando la posizione ancora piu' scoperta; (b) `_sorveglia_sospensione` guarda solo
l'OU35 e solo con lay appoggiate vive: la copertura (BACK sull'OU45) non ci entrava mai,
quindi nessuna attivita' di sospensione/riapertura esisteva per la copertura.

Ora: gate esplicito in `_decide_uncovered` con il motivo per nome; gate in
`_decide_cover_pending` (niente riprezzo a mercato non OPEN); `execute_place` dice lo stato
per nome; `_sorveglia_mercato_copertura` (nuovo, gira PRIMA della decisione) scrive **una
riga per TRANSIZIONE**: `mercato_sospeso` `critical` quando si perde l'operabilita',
`mercato_riaperto` quando torna. Stato IGNOTO = non aperto (fail-closed).

## 2-quater. «Il parcheggio non espone mai piu' del cap» (money-critical, 17/09)

Nel percorso A il parcheggio del minimo sta ALLA quota target: per un LAY impegna
`size*(quota-1)` — a quota 95 il minimo BACK (2,00 EUR) impegnerebbe **188,00 EUR** fino al
taglio, contro 0,01 EUR del parcheggio a 1.01. Aggiunti al nucleo `liability_parcheggio` e
`guardia_cap_parcheggio`; `pianifica_submin(max_stake=)` ripiega sul **percorso B** se il
percorso A sfonderebbe il cap, e rifiuta (`SUBMIN_CAP_PARCHEGGIO`, 0 ordini) se nemmeno il
replace e' consentito. Difesa in profondita' negli adattatori: `place_submin_live(max_stake=)`
prima del gradino 1 e `advance_submin` al place con `ops.max_stake`.

## 3. File toccati

| file | cosa |
|---|---|
| `Betfair/stream/trading/submin.py` | NUCLEO UNICO: `PianoSubmin`, `quota_non_abbinabile`, `pianifica_submin`, `esito_istruzione`, `codice_rifiuto`, `marca_submin`; `SubminState` con `park_price`/`serve_replace` (default = comportamento storico); `start_submin(best_back=, best_lay=)`; step1 usa `prezzo_parcheggio`; step3 saltato nel percorso A |
| `Betfair/omega/omega_market.py` | `place_submin_live` riscritta sul nucleo: `_submin_best_prices` (lettura book), piano A/B, report ESTERNO+INTERNO persistiti in `raw.diagnostica`, log `critical` col report intero, **verifica fail-closed su `listCurrentOrders` per betId dopo il taglio**, marca `submin` nel risultato, rifiuto `SUBMIN_NESSUNA_CONTROPARTE` con FOK+quota passiva (0 chiamate mutanti) |
| `Betfair/stream/tests/test_submin_nucleo_2026_09_17.py` | NUOVO, 19 test |
| `Betfair/stream/tests/test_submin_contratto_chiamanti_2026_09_17.py` | NUOVO, 6 test di contratto |
| `Betfair/omega/test_place_and_trim_2026_09_13.py` | finto esteso: `list_market_book`, `listCurrentOrders`, letture separate dai passi mutanti |
| `Betfair/stream/trading/PLACE_AND_TRIM_INDAGINE_2026-09-17.md` | NUOVO: indagine con le fonti |
| `Betfair/stream/trading/INTERFACES.md` | contratto del modulo unico + matrice dei casi |

Firme pubbliche invariate (`best_back`/`best_lay` sono kwargs opzionali): nessun chiamante
fuori dominio e' stato toccato.

## 4. Numeri

- `pytest Betfair/mike -q -p no:cacheprovider` -> **763 passed**.
- `pytest Betfair/omega -q -p no:cacheprovider` -> **1069 passed**.
- `pytest Betfair/mike Betfair/stream/tests -q -p no:cacheprovider` -> **2023 passed**.
- `pytest Betfair/omega Betfair/stream -q -p no:cacheprovider` -> **2552 passed**, 0 falliti.
- `test_submin_nucleo_2026_09_17.py` -> 19 passed; `test_place_and_trim_2026_09_13.py` -> 17 passed.

### Replay del banco (ordine E)

```
python -m Betfair.stream.backtest.certifica mike 35760084 36006953        --scenari copertura-rifiutata,base --worker 2
```
-> **4 partite, 0 violazioni totali**. Controlli nuovi **sollecitati**: **S1 x4578**,
**S2 x44**. I controlli mai sollecitati scendono da 10 a 9 su 35.

Dopo l'aggiunta di S3/S4, `certifica mike 35760084 --scenari copertura-rifiutata`:
**0 violazioni**, **S1 x4578, S3 x4578, S4 x1**.

**Falsificazione di S3 (la mutazione del coordinatore)**: `registra_rifiuto_copertura` ->
`return None` in testa (i rifiuti non si contano, il freno non scatta mai). Prima di S3:
0 violazioni e S1 x0 — il banco dichiarava sano il comportamento del 17/09. Con S3:
**17 violazioni, S3 x17**. Ripristinato e verificato per md5 (`engine.py`
`af09d24914e2fd4a32adc235c6858ea4`, identico a prima della mutazione); replay rilanciato:
**0 violazioni, S3 x4578 sollecitato**.

**Falsificazione del controllo nuovo SUL REPLAY** (non solo a unita'): con
`_freno_copertura` messo a `return d` (il freno non toglie piu' niente),
`certifica mike 35760084 --scenari copertura-rifiutata` -> **964 violazioni, S1 x961**.
Mutazione ripristinata, replay e suite rimessi verdi.

### Falsificazione (provata, poi ripristinato)

1. `if passiva is True:` -> `if False:` (percorso A mai scelto): ROSSI
   `test_percorso_a_quando_la_quota_non_e_abbinabile`, `test_lay_percorso_a`,
   `test_start_submin_percorso_a_parcheggia_alla_quota_target`,
   `test_macchina_percorso_a_non_chiama_mai_replace`.
2. `"place_error_code": pir.get("errorCode")` -> `None` (si torna a leggere solo il codice
   esterno, il bug del reperto 25): ROSSI `test_esito_istruzione_legge_anche_il_report_interno`,
   `test_codice_rifiuto_unisce_esterno_e_interno`.

Dopo ogni mutazione il file e' stato ripristinato e la suite rimessa verde.

---

## 4-bis. Banco: scenario nuovo per Mike (ordine E)

`Betfair/mike/tools/replay_registrazioni.py` — scenario **`copertura-rifiutata`**: Betfair
rifiuta **SEMPRE** (non «i primi N») gli ordini sotto il minimo .it, con il codice vero del
17/09: esterno `CANCELLED_NOT_PLACED`, interno
`placeInstructionReport.errorCode = INVALID_BET_SIZE`. Il filtro e' sulla **size sotto il
minimo**, non sul mercato: colpisce solo la copertura, mentre l'ingresso da 5 EUR e le
uscite passano — e' il caso reale alla lettera. Taratura dello scenario
**due tarature dichiarate** (stessa natura di `cap-stretto`: si stringe per far parlare una
guardia, non si cambia la strategia): `cover_rifiuti_max = 1`, perche' su una registrazione
la copertura si tenta poche volte e col default 3 il freno non scatterebbe; `stake = 3,00`
invece di 10, perche' con 10 EUR di stake la copertura si dimensiona SOPRA il minimo .it e
il caso del 17/09 (copertura SOTTO minimo) non capiterebbe mai. Misurato: con `stake` a 10
il controllo S1 restava a x0 (il referto diceva «non lo so»); con 3,00 va a x4578.

`Betfair/stream/backtest/banco_comune.py` (`MercatoFlumine`), aggiunta minima e additiva:
`guasti["place_rifiuto"] = -1` = rifiuto che **non si consuma**; `rifiuta_market_id`,
`rifiuta_sotto_minimo`, `rifiuto_codice`, `rifiuto_codice_interno`. Il `PlaceResult` del
rifiuto porta ora `error_code` e, col codice interno, gli `instructionReports` nella forma
vera di Betfair (`cancelInstructionReport` SUCCESS + `placeInstructionReport` FAILURE).

`Betfair/mike/certificazione.py` — quattro controlli di condotta NUOVI:
- **S1**: «a freno scattato il bot NON ripropone la copertura» (si solleva quando
  `copertura_bloccata(ctx)`);
- **S2**: «nessun `place` ne' `cancel` di copertura mentre l'Over 4.5 non e' OPEN»;
- **S3**: «dopo `cover_rifiuti_max` coperture RIFIUTATE DAL MERCATO il bot non ne piazza
  altre: il freno deve SCATTARE». Contato dalle **gambe rifiutate**, non da
  `ctx.cover_rifiuti`;
- **S4**: «fra due tentativi di copertura passa almeno `cover_retry_min_s`», misurato sul
  tempo di MERCATO (`snap.now`) e sul `placed_at` delle gambe.

**Perche' S3 esiste (buco trovato dal coordinatore).** S1 guarda «a freno scattato»: se il
CONTATORE dei rifiuti smette di contare, il freno non scatta mai, S1 non ha piu' un caso e
il referto dice «non lo so» — cioe' il bot torna a ritentare all'infinito come il 17/09 e
il banco lo dichiara **sano**. Misurato: con `registra_rifiuto_copertura` neutralizzata
(`return None` in testa) il replay dava **0 violazioni e S1 x0**. Con S3: **17 violazioni**.
S3 e S4 non leggono il contatore del freno, leggono gli ESITI delle gambe: la stessa
mutazione non puo' spegnerli.

## 5. Test DAL VIVO con l'utente (obbligatorio prima di qualunque live)

Niente e' certificato in-play finche' non si vede la risposta vera di Betfair. Procedura,
da fare INSIEME all'utente, con importi minimi:

1. **Partita qualsiasi gia' in gioco**, mercato liquido (Over/Under o Match Odds).
   Annotare `betDelay` da `listMarketBook` (in-play vale 1-12 s).
2. **Prova A (percorso A, quella che deve funzionare).** BACK di **0,05 EUR** a una quota
   **NON abbinabile** (almeno 2-3 tick SOPRA il best back). Attesi: 2 sole chiamate
   mutanti (`placeOrders` 2,00 alla quota target + `cancelOrders sizeReduction 1,95`),
   nessun `replaceOrders`, e l'ordine visibile su Betfair **a 0,05 EUR** alla quota
   scelta. Verificare su `listCurrentOrders` (`sizeRemaining` = 0,05).
   -> se passa, il place-and-trim sotto minimo e' CERTIFICATO in-play per il caso passivo.
3. **Prova B (percorso B, quella che oggi fallisce).** Stesso importo, quota **abbinabile**
   (al best back o sotto). Attesi: `placeOrders` 2,00 @1000 + `cancelOrders` + 
   `replaceOrders`. **Guardare nel log `critical` `[submin] REPLACE RIFIUTATO ... interno=`**:
   e' il codice che ci manca da 171 rifiuti. Annotarlo: e' la diagnosi definitiva
   (`INVALID_BET_SIZE`, `INVALID_PROFIT_RATIO`, `MARKET_SUSPENDED`, ...).
4. **Come si annulla**, sempre: dalla UI di Betfair o con
   `cancel_order_live(bet_id, market_id)` (annullo TOTALE del residuo). Il codice ritira da
   solo il residuo in ogni ramo di errore; se un ritiro fallisce lo scrive come
   `RITIRO FALLITO` a livello `critical` e l'ordine va cercato a mano su Betfair.
5. Rischio massimo dell'intera prova: **2,00 EUR** per tentativo, e solo se il parcheggio
   si abbinasse (non deve: la quota e' non abbinabile).

---

## 6. Cosa NON e' verificato

- **Il comportamento reale di Betfair in-play**: ne' il percorso A (nessun successo
  storico da mostrare) ne' il codice INTERNO dei 171 rifiuti. Serve il test del §5.
- **`_submin_state_to_dict`/`_submin_state_from_dict`** in
  `Betfair/stream/live_order_worker.py:2621-2645` (fuori dal mio dominio) non serializzano
  ancora `park_price` e `serve_replace`. Effetto oggi: uno stato ripreso dopo un riavvio
  torna al percorso B; non e' pericoloso (al gradino 3 l'ordine risulta gia' alla quota
  target e la macchina avanza senza replace), ma **va aggiunto**: due campi in piu' nel
  dict e nel costruttore. **Diff proposto, da applicare a cura di chi possiede quel file:**

```diff
--- a/Betfair/stream/live_order_worker.py
+++ b/Betfair/stream/live_order_worker.py
@@ def _submin_state_to_dict(state: Any) -> Dict[str, Any]:
         "note": state.note,
         "trim_requested_ms": int(getattr(state, "trim_requested_ms", 0) or 0),
+        # 17/09 - nucleo universale del place-and-trim: quota del parcheggio
+        # (percorso A = la quota target, percorso B = 1000/1.01) e se serve il
+        # replace. Senza questi due una ripresa dopo un riavvio tornerebbe
+        # sempre al percorso B.
+        "park_price": float(getattr(state, "park_price", 0.0) or 0.0),
+        "serve_replace": bool(getattr(state, "serve_replace", True)),
     }
@@ def _submin_state_from_dict(d: Dict[str, Any]) -> Any:
         trim_requested_ms=int(d.get("trim_requested_ms") or 0),
+        # default = comportamento storico (parcheggio lontano + replace) per le
+        # righe scritte prima del 17/09.
+        park_price=float(d.get("park_price") or 0.0),
+        serve_replace=bool(d.get("serve_replace", True)),
     )
```
- **Controlli del banco comune (famiglia B8, minimi .it)**: devono violare un ordine sotto
  minimo **solo se NON porta la marca `submin`** (`marca_submin`). Non fatto: e'
  `Betfair/stream/backtest/`, e il delegato tennis ci sta misurando sopra
  (4.087 -> 8.566 violazioni). Contratto scritto in `INTERFACES.md`.
- **Scenario del banco «mercato sospeso durante la copertura»**: NON creato come scenario
  a se'. Il controllo **S2** e' comunque sollecitato x44 sulle registrazioni reali (le
  sospensioni ci sono davvero), quindi il caso e' coperto; uno scenario dedicato che
  FORZA la sospensione resta da fare.
- **Replay su 4 registrazioni**: fatto su **2** (35760084, 36006953) x 2 scenari = 4
  coppie. Le altre due registrazioni citate nella cronostoria (35777617, 35674515) non
  sono state rilanciate oggi.
- **Test di contratto sui chiamanti**: FATTO,
  `Betfair/stream/tests/test_submin_contratto_chiamanti_2026_09_17.py` (6 test): il REST
  deve passare dal nucleo, le firme pubbliche restano compatibili, i 15 chiamanti sono
  censiti (un chiamante nuovo non registrato fa fallire il test), la marca `submin` e'
  completa, i minimi vengono dalla tabella.
- **Freno fail-closed sui rifiuti ripetuti (ordine 3) e consapevolezza SUSPENDED/OPEN/
  CLOSED durante la copertura (ordine 5)**: delegati a un agente Opus su
  `Betfair/mike/service.py`/`config.py`/`engine.py`; al momento della scrittura di questo
  referto il suo lavoro non era ancora rientrato. Da verificare prima di considerarli fatti.
