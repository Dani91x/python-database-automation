# REFERTO - Correzione del dutching manuale (reperti A1 + M11 + caso V3), 09/10/2026

Costruito da un delegato Sonnet (referto di lavoro: `lavori/fase2/FIX_DUTCHING_delegato.md`), **riverificato dal
coordinatore**: diff riletto riga per riga, test e suite rilanciati di persona, falsificazione rifatta con mutazioni
proprie (anche in direzioni che il delegato non aveva provato), differenziale UI/server rifatto con un seme diverso.
Nessun commit, nessuna build (`npm run build` resta al coordinatore ad app chiusa), nessun processo lasciato acceso.
Strumento manuale dell'utente: nessun bot usa il dutching variable (Safe usa `dutch_back` solo per le proposte COMBO,
`safe_strategy/combos.py:43,527`, e non e' toccato); nessuna strategia toccata.

## 1. Cosa e' cambiato (diff completo: `lavori/fase2/suite/diff_fix_dutching_COORD.patch`, 613 righe)

| File | Modifica | Perche' |
|---|---|---|
| `Betfair/stream/live_order_worker.py:2914-2919` (+5 righe) | nel ramo `dmode == "variable"`: `if side == "lay": raise ValueError("dutch mode=variable: supportato solo per back")`, PRIMA di risolvere i prezzi e di qualsiasi ordine | A1: `dutch_variable` restituisce sempre `side="back"`; una richiesta LAY diventava ordini BACK. Stesso stile del rifiuto gia' esistente per target+lay. Il `ValueError` risale a `_dispatch` e viene scritto come esito di errore da `_write_error` (`live_order_worker.py:4000-4008`, letto dal coordinatore): zero ordini |
| `frontend/src/components/live/DutchingPanel.tsx` (+146/-13) | (a) opzione "Variable" disabilitata sul lato Lay, avviso visibile e bottone disabilitato se lo stato arriva a variable+lay, blocco anche in `guardBeforeSend`; (b) anteprima del modo variable calcolata con `dutchVariablePlan`, copia della formula del server (profitto proporzionale al peso, `k = T(1-sum 1/p)/sum(w/p)`, `s_i = round((T + k w_i)/p_i, 2)`, totale e profitti arrotondati come in Python), prezzi portati al tick come `get_nearest_price` di flumine, `round(x,2)` di Python riprodotto (pareggi binari esatti al pari) e `sum()` compensata come in Python 3.13; (c) pesi irrealizzabili: messaggio, stake e profitti "—", invio bloccato; (d) se il worker risponde `ok=True` senza gambe piazzate (`legs` assente o vuoto) il pannello mostra "Dutching NON piazzato" invece di "inviato" | M11 e V3 |
| `Betfair/stream/tests/test_live_order_dutch_cashout.py` (+53) | 3 test: variable+lay rifiutato con zero ordini; rifiuto prima del calcolo dei prezzi; variable+back invariato (caratterizzazione: piano 40,51/34,18/25,32, a mercato 40,50/34,00/25,00 per la regola .it dei multipli di 0,50) | |
| `Betfair/stream/tests/test_dutching.py` (+32) | 3 test di caratterizzazione di `dutch_variable` con valori letterali presi dall'esecuzione della funzione vera (fonte dei numeri che l'anteprima deve riprodurre) | |
| `frontend/src/components/live/DutchingPanel.test.tsx` (+202/-2) | 15 test nuovi (13 -> 28): variable disabilitato sul lay, invio bloccato, anteprima = server su casi calcolati con la vera `dutch_variable`, pareggi di arrotondamento, prezzi fuori tick, pesi irrealizzabili, risposta senza gambe | |
| `Betfair/stream/trading/dutching.py` | **non modificato** (`git status` pulito) | la formula del server era giusta; il difetto era nel worker e nella UI |

Semantica di equal e target invariata (nessuna riga dei loro rami toccata nel worker; nella UI il ramo equal usa la formula di prima).

## 2. Test e suite (rilanciati dal coordinatore)

| Comando | Prima della modifica | Dopo |
|---|---|---|
| `pytest Betfair/stream/tests/test_dutching.py Betfair/stream/tests/test_live_order_dutch_cashout.py` | 2 failed, 24 passed (test nuovi rossi, `pytest_dutch_ROSSO_prima_fix.txt`) | **26 passed** (`falsifica_py_coord.txt`, ultima riga) |
| `pytest Betfair/ -q -p no:cacheprovider` (suite intera) | **11477 passed, 11 skipped, 6 xfailed** (`pytest_betfair_PRIMA.txt`, lanciata dal coordinatore prima di ogni modifica) | **11483 passed, 11 skipped, 6 xfailed** (`pytest_betfair_DOPO.txt`): +6 = i test nuovi, **nessun test prima verde diventato rosso** |
| `npx vitest run src/components/live/DutchingPanel.test.tsx` | 13 passed (`vitest_dutching_PRIMA.txt`); con i test nuovi e codice vecchio: 12 failed / 16 passed | **28 passed** (`vitest_dutching_DOPO_coord.txt`) |
| `npx tsc -p tsconfig.app.json --noEmit` | 0 errori (`tsc_PRIMA.txt`) | **0 errori** (`tsc_DOPO_coord.txt`); nessun `@ts-ignore`, nessun `any` nuovo (l'unico `any` del file, `catch (e: any)` a riga 417, e' preesistente e fuori dal diff) |

## 3. Falsificazione (ogni test nuovo sa diventare rosso)

Del delegato: senza la correzione del worker 2 failed (`pytest_dutch_FALSIFICAZIONE_senza_fix.txt`); 7 mutazioni
singole della UI tutte rosse (`vitest_FALSIFICAZIONE*.txt`).

Del coordinatore (script `lavori/fase2/sonde/coord_falsifica_py.py`, `coord_falsifica_ui.py`, `coord_falsifica_ui2.py`;
ogni mutazione applicata da sola, test rilanciati, file ripristinato e controllato con sha256):

| Mutazione | Esito |
|---|---|
| P1 worker senza rifiuto variable+lay | 2 failed, 24 passed (ROSSO) |
| P2 rifiuto spostato dopo il calcolo dei prezzi | 1 failed (ROSSO) |
| P3 `dutch_variable` senza arrotondamento dello stake | 3 failed (ROSSO) |
| P4 `dutch_variable` con k=0 (proporzionale allo stake, la vecchia anteprima) | 5 failed (ROSSO) |
| M1 opzione Variable riabilitata sul Lay | 1 failed (ROSSO) |
| M2 anteprima variable con la formula vecchia | 6 failed (ROSSO) |
| M3 "inviato" anche senza gambe piazzate | 2 failed (ROSSO) |
| M4 bottone riabilitato su variable+lay | 1 failed (ROSSO) |
| M5 (M5b nel file) bottone + `guardBeforeSend` + opzione tolti insieme | 2 failed (ROSSO) |
| M6 arrotondamento ingenuo al posto di `round()` di Python | 1 failed (ROSSO) |
| M7 pesi irrealizzabili: tolta SOLO la clausola di `guardBeforeSend` | 28 passed (VERDE): la clausola e' ridondante, il bottone e' gia' disabilitato da `preview.infeasible`; tolte entrambe -> 1 failed (ROSSO) |

Tutti i ripristini: sha256 identico all'originale; dopo i ripristini 26 passed / 28 passed.
Nota onesta: le clausole di `guardBeforeSend` per variable+lay e per i pesi irrealizzabili sono difese doppie dietro
il bottone disabilitato; da sole non hanno un test che diventi rosso.

Differenziale anteprima TS contro `dutch_variable` Python: delegato 0 divergenze su 20.000 casi casuali (seme 20261009)
e 0 su 99.900 prezzi della griglia dei tick; con `round` ingenuo 748 divergenze, con somma ingenua 2. Coordinatore:
seme diverso (424242), 2/6/10/12 gambe, quote basse 1,01-1,60 fuori tick: **0 divergenze su 20.000 casi** (11.911 piani non
azionabili inclusi; `lavori/fase2/suite/differenziale_coord_seed424242.txt`, prima riga; la seconda parte dello script, sulla
griglia dei tick, non e' stata rieseguita dal coordinatore perche' il file di riferimento del delegato non c'era piu': ENOENT nel file).

## 4. Cio' che resta e non e' stato possibile verificare

- **Esecuzione reale**: non eseguito contro flumine/Betfair (nessun ordine, per regola). Il percorso del `ValueError` fino
  all'esito di errore e' verificato leggendo il codice (`_dispatch` -> `_write_error`, :4000-4008), non eseguito end-to-end.
- **Resa visiva nell'app**: test in jsdom; l'app non e' stata avviata ne' ricompilata (la build la fa il coordinatore ad app chiusa).
- **Residui fuori perimetro** (in `DECISIONI_PER_L_UTENTE.md`, non toccati):
  1. `build_order` porta ogni punta al multiplo di 0,50 per difetto dopo il piano (regola .it decisa dall'utente): a
     mercato vanno 40,50/34,00/25,00 invece di 40,51/34,18/25,32 e il `profit_if_wins` del risultato e' quello del piano,
     non delle punte effettive. Vale per tutti i modi (equal, target, variable). L'anteprima mostra il piano.
  2. Con `pricing` best / in_front / nominated il server risolve il prezzo al momento dell'invio: l'anteprima e' esatta
     solo con i prezzi mostrati (as_given); negli altri casi e' una stima.
  3. `roundToTick` di `frontend/src/lib/matching.ts` differisce da `get_nearest_price` di flumine sui pareggi a mezzo tick
     (37 prezzi, numero del delegato non riverificato dal coordinatore): il pannello ora usa la copia fedele `nearestTickPrice`, ma altri pannelli usano ancora `roundToTick`.
  4. `LiveOrderResult` (`frontend/src/lib/liveOrders.ts`) non dichiara `legs`: il pannello lo legge con un tipo esteso
     locale; aggiungerlo al tipo e' fuori perimetro.
  5. `DutchPlan.actionable` (`dutching.py`) non rifiuta un dutch BACK con profitto minimo negativo (book > 100%): il
     server lo piazza se l'utente conferma (verifica avversaria V2 della fase 1); e' un comportamento, non toccato.
