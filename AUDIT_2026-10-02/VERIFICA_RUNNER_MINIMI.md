# VERIFICA_RUNNER_MINIMI: revisione indipendente di `RUNNER_MINIMI_CHIUSURE.patch` (02/10/2026)

Revisore: delegato Opus, worktree `agent-a0274ee823e0cae47`, ramo locale `verifica-runner`.
Lavoro in sola revisione: nessuna correzione al codice, nessun commit su master, nessun
push, nessun ordine vero, nessun replay. Le strategie non sono state toccate.

Artefatti miei, in questa cartella:
- `falsifica_revisore_runner_minimi.py`: 15 mutazioni.
- `sonda_calcoli_runner_minimi.py`: i calcoli a mano e la banda del parcheggio.

## 0. Verdetto in breve

**INTEGRABILE CON CORREZIONI.** Elenco completo al §10.

- Il cuore della patch è giusto e regge alla falsificazione:
  - niente più esenzione `reduces_liability`;
  - punta al centesimo;
  - verdetto diretto → equivalente → trim ≥ 0,50 → rifiuto;
  - riporto al bot nei termini del chiesto;
  - ripiego unico.
- I tre calcoli a mano tornano al centesimo con il codice.
- Prima del live restano tre difetti:
  - **il paper non è lo specchio del live** sulle gambe di greenup/cash-out;
  - **il codice del rifiuto non arriva al bot** sulla strada asincrona (aggancio) e sugli
    errori del dispatch;
  - **cancel e replace su un ordine tradotto** non vengono convertiti.
- Ci sono poi un test indebolito e un commento falso, più alcune incoerenze di testo.
- Il modello «1 + 0,008/S» per il parcheggio LAY è debole: per 17 residui su 50 (fra 0,63 e
  0,79) la liability arrotondata esce dalla banda −20 %/+25 %. È un modello non verificato.

## 1. Esito dell'apply

- `git diff aa5749a master --stat`: 33 file, tutti sotto `AUDIT_*` o in `CRONOSTORIA.md`.
  Nessun file sotto `Betfair/`: la base è equivalente, confermato.
- `git apply --3way AUDIT_2026-10-01/RUNNER_MINIMI_CHIUSURE.patch` sul file del checkout
  **fallisce in blocco** (`patch does not apply` su tutti i 41 file). Il motivo: con
  `core.autocrlf=true` il `.patch` è scritto CRLF nel worktree, e un hunk CRLF non combacia.
- Con la copia LF dall'indice (`git show HEAD:AUDIT_2026-10-01/RUNNER_MINIMI_CHIUSURE.patch`)
  l'apply è **pulito su tutti i file**: «Applied patch … cleanly».
  - Commit locale: `42984d2` sul ramo `verifica-runner`.
  - `falsifica_runner_minimi.py` è identico a quello già committato.
  - **Nota per l'integrazione**: applicare dalla copia dell'indice, non dal file del checkout.
- La patch tocca **41 file** sotto `Betfair/` (39 modificati e 2 nuovi: `minimi_it.py` e il
  file di test), più il file AUDIT già presente. Il referto parla di «39 file»: discrepanza
  solo di conteggio.

## 2. Revisione riga per riga del codice di produzione

| file | prima | ora | conforme? |
|---|---|---|---|
| `stream/trading/minimi_it.py` (nuovo) | — | contiene `IT_MIN_BACK=IT_MIN_LAY=1,00`, `IT_FLOOR_LEGGE=0,50`, `SUBMIN_IMPORTO_FINALE_MIN=0,50`, `SOTTO_MINIMO_NON_PIAZZABILE`, `IT_PASSO_PUNTA_RIPIEGO=0,50` | **SÌ**. `IT_PASSO_PUNTA_RIPIEGO` serve solo al ripiego (vedi 2e) |
| `stream/live_order_build.py` `min_stake_rules` | `reduces_liability` → `valid` per qualunque size; punta con floor ai 0,50 | `del reduces_liability`; `legal = round(size,2)`; sotto 1,00 il motivo comincia con `SOTTO_MINIMO_NON_PIAZZABILE` | **SÌ** |
| `live_order_build.equivalente_lato_opposto` / `verdetto_minimi` / `riporta_abbinato_all_originale` | — | formula esatta; equivalente BACK col tick in su, LAY col tick in giù; tolleranza 0,01; vincita massima; ordine diretto → equivalente → submin (≥ 0,50) → impossibile | **SÌ** (calcoli al §3) |
| `live_order_build.build_order` | esenzione via `reduces_liability` | nessuna esenzione; nuovo `simulato_ammette_sotto_minimo` | **NO in parte**: il flag riapre il sotto-minimo diretto in PAPER (2-P1) |
| `stream/motore_ordini.py` `_applica_minimi` | solo aperture, solo trim | ogni place passa dal verdetto; `_ripristina_minimi` in testa a `_controlla` (idempotente); rifiuto `M_SOTTO_MINIMO` | **SÌ** sulla via sincrona. Il codice però non arriva al bot sull'aggancio (2d) |
| `motore_ordini._riporta_tradotto` / `_emetti` | — | gli eventi tornano nei termini del chiesto, con `riga_mandata` | **SÌ** per place e fill. **NO** per cancel e replace del bot sull'ordine tradotto (§8, reperto 5) |
| `motore_ordini` sorveglianza (`_sorveglia`, `_emetti_specchio`, `avanza_sorvegliati`, `_ripiega`, `_ricorda_taglia`) | — | un solo ripiego ai 0,50 dopo un `INVALID_BET_SIZE` vero, solo in live; taglia `(mode, lato, size)` mai ritentata | **SÌ** (2e). Nota: la chiave della taglia è globale, vale per tutti i mercati |
| `motore_ordini.altro_runner_due_esiti` | — | `len(market_book.runners)==2` | **SÌ**, ma fragile e NON coperto dai test (mutazione R8) |
| `stream/live_order_worker.py` `_place_closing_leg` / `_costruisci_chiusura` | place diretto con esenzione, trim solo dopo un rifiuto dei control | in LIVE sotto il minimo: trim deciso prima dell'invio; opt-out → rifiuto esplicito | **SÌ in live**. **NO in paper**: diretto anche sotto 0,50 (2-P1). Nel greenup non c'è l'equivalente, per scelta motivata |
| `live_order_worker._place_sub_minimum` / `_start_submin` | — | `verifica_importo_finale` (≥ 0,50) | **SÌ** |
| `live_order_worker._sub_minimum_floor` | docstring «BACK 2,00 / LAY 0,50» | invariata: il valore viene da `place_min_size`, cioè 1,00 | testo **stantio** (LOW) |
| `stream/trading/submin.py` | parcheggio LAY a 1,01 | `quota_parcheggio_lontano` = `1+0,008/S` al tick in su; rifiuto `SUBMIN_PARCHEGGIO_ABBINABILE`; `verifica_importo_finale` | **SÌ** nella sostanza. Il modello della banda è debole (2c) |
| `safe_strategy/execution.py` | chiusure esenti; `_min_size_live` 2,00 / 0,50 a mano | minimi da `minimi_it`; chiusura sotto il minimo → `place_submin` (coda) o `place_submin_live` (REST); sotto 0,50 fuori canale → rifiuto certo, uguale in paper e in live; sul canale decide il motore | **SÌ**. Fuori canale manca l'equivalente (2-P2) |
| `omega/omega_market.py` | `SUBMIN_MIN_*` 2,00 / 0,50 fissi | `SUBMIN_MIN_*` da `minimi_it`; `place_submin_live` → `PlaceRifiutato(SOTTO_MINIMO_NON_PIAZZABILE)` sotto 0,50 | **SÌ**. `SUBMIN_PARK_PRICE_*` restano costanti morte (LOW) |
| `stream/config_stream.py` | commento | il commento dice «back min EUR2.00 al centesimo» | **FALSO**: è 1,00 (LOW) |
| `stream/backtest/trasporto_rapido.py` | R8 con 1,50 sotto il minimo 2,00 | R8 con 0,70 sotto il minimo 1,00; tennis portato al minimo 1,00 | **SÌ**, solo numeri del listino, stessi controlli |

Altre incoerenze di testo (LOW):
- `live_order_build.py`, commento in testa: «place-and-trim solo con parcheggio e importo
  finale >= 1,00». È falso, il finale è ≥ 0,50.
- `submin.advance_submin`, commento: «importo finale >= 1,00». Stesso errore.
- `SubminState.placed_size`, commento: «€2 .it BACK / €0,50 LAY».
- `porta_al_minimo_apertura`, docstring: 200 / 50 centesimi.

### 2a. Grep di TUTTE le vie di invio (`place_orders`, `.place_order(`, `place_order_live`, `place_submin_live`, `PlaceInstruction`)

| via | file:riga | guardia dei minimi dopo la patch |
|---|---|---|
| motore del canale (Omega/Safe/Mike via runner) | `motore_ordini._applica_minimi` (r. ~1104) → `LOW._dispatch` | verdetto completo, paper = live |
| coda DB `place` | `live_order_worker._do_place` (r. ~1449) → `build_order` | solleva prima dell'invio, paper e live |
| coda DB `place_submin` | `live_order_worker._start_submin` (r. ~2980) | `verifica_importo_finale` ≥ 0,50 |
| greenup / cash-out (worker) | `_do_greenup`, `_flatten_market` → `_costruisci_chiusura` / `_place_closing_leg` | LIVE: trim o rifiuto. **PAPER: diretto anche sotto 0,50** |
| cash-out, gamba di APERTURA | `_flatten_market` (r. ~2686) | sotto il minimo la gamba è SALTATA (invariato) |
| macchina submin (place del parcheggio) | `live_order_worker.py:1268` `market.place_order` | parcheggio = minimo 1,00 |
| Safe REST | `safe_strategy/execution.py:924` → `omega_market.place_order_live` / `place_submin_live` | `place_order_live` riceve solo size ≥ `_min_size_live` (1,00) |
| Omega REST automatico/manuale | `omega/omega_service.py:5514` → `place_order_live` | `place_order_live` (`omega_market.py:696`) **non ha nessun controllo dei minimi**. Il manuale di Omega usa `min_stake` dei parametri, non il listino. Fuori dal perimetro della patch |
| Omega REST place-and-trim | `omega_market.place_submin_live` (r. 956/1007) | `verifica_importo_finale` |
| Mike REST | `mike/service.py:2147` `market.place_order_live` | nessuna guardia del runner; la guardia sta nella patch di Mike |
| ordini dell'app (watchlist) | `Betfair/order_exec.py:315` | `MIN_STAKE_EUR = 2.0` (r. 32): **duplicato non portato su `minimi_it`**. Troppo severo, non pericoloso |
| scalper / sniper / tennis | `scalper_bot.py:2462`, `sniper_bot.py:1027`, `tennis_*_bot.py` (`MIN_STAKE = 2.0`) | fuori perimetro (reperto 1 del delegato) |
| client simulato di flumine | `runner.py:2112/2133/2143/2171` | `min_bet_validation=False`: il simulatore accetta tutto, la barriera è solo nostra |

Esito del grep: nessuna via del perimetro (motore, coda, Safe, Omega place-and-trim) manda in
LIVE un ordine diretto sotto 1,00. In PAPER passa ancora un diretto sotto il minimo, anche
sotto 0,50: sono le gambe greenup/cash-out del worker (2-P1).

Fuori perimetro restano scoperti:
- `omega_market.place_order_live`, usato da Omega/Mike e senza guardia;
- `order_exec.MIN_STAKE_EUR`;
- `mike/engine.py:67-71`, coperto dalla patch di Mike;
- `safe_strategy/bot_service.py:866` `_CANALE_MIN_STAKE = DEFAULT_PARAMS.min_stake (2.0)`:
  è un parametro di strategia, non del listino; da guardare con l'utente;
- `omega_model.MARKET_QUOTE_MIN_SIZE = 2.0`.

### 2b. Tre calcoli a mano (sonda `sonda_calcoli_runner_minimi.py`, eseguita)

1. **Banca Over 0,43 @18, 2 esiti.**
   - Quota esatta 18/17 = 1,058824. Tick in su 1,06, tick in giù 1,05. Size 0,43·17 = **7,31**.
   - Scarti: se vince Over −7,31+7,31 = **+0,0000**; se vince Under 7,31·0,06−0,43 = **+0,0086**.
   - Con 1,05 lo scarto sarebbe **−0,0645**: un limite peggiore, scartato.
   - Il codice dà `back 7.31 @1.06, scarti 0.0 / 0.0086`: **identico**.
   - Su 3+ esiti il codice dà `impossibile` (0,43 < 0,50), con il residuo dichiarato.
   - Direzione giusta per il bot: una banca a 18 «o meno» equivale a una punta a 1,0588 «o
     più». Il tick in su non peggiora mai il limite. Prezzo: l'equivalente si abbina solo se
     l'Under offre ≥ 1,06, cioè come un Over a ≤ 17,67 (reperto 4).
2. **Punta 0,80 @1,50.**
   - Equivalente: banca 0,40 @3,0 (3,0 è già un tick). È sotto 1,00, quindi non si usa.
   - Il codice dà `submin`. Piano: parcheggio BACK 1,00 @1000, riduzione 0,20 → finale 0,80,
     poi rimpiazzo a 1,50.
   - Scarti a mano 0 / 0.
   - Variante banca 0,80 @1,50: equivalente punta 0,40 @3,0, sotto il minimo → `submin` con
     parcheggio LAY 1,00 @**1,01** (1+0,008/0,80 = 1,01), liability residua 0,008 → 0,01
     (+25 %, al bordo della banda).
3. **2,00 @1,05.** Diretto su entrambi i lati: il codice dà `diretto 2.0`. Equivalente
   teorico: banca/punta 0,10 @21,0, scarti 0/0. Non viene usato perché il diretto ha la
   precedenza.

### 2c. Parcheggio del place-and-trim

- **BACK** a 1000. Non abbinabile salvo un book a 1000; la riduzione non ha problemi di
  profit-ratio (la vincita è centinaia di euro).
- **LAY** a `1+0,008/S` al tick in su (0,30 → 1,03; 0,43 → 1,02; 0,80 → 1,01). La guardia
  `SUBMIN_PARCHEGGIO_ABBINABILE` rifiuta se il book mostra già quella quota (`best_lay ≤ park`).
  Con il book ignoto non rifiuta: comportamento invariato, «fail-closed» solo a dirlo.
- **Banda INVALID_PROFIT_RATIO**: il criterio «liability ≥ 0,008» è solo un limite inferiore.
  Se Betfair confronta la liability arrotondata al centesimo con quella esatta (−20 %/+25 %):
  - con i residui da **0,63 a 0,79** il parcheggio sta a 1,02 e la liability arrotondata
    devia da −20,6 % a +33,3 %: **17 residui su 50 fuori banda** (tabella della sonda);
  - il caso del referto «0,60 → 1,02» è dentro la banda (−16,7 %); 0,70 → 1,02 dà −28,6 %.
  - Oggi in quei casi il cancel parziale verrebbe rifiutato `INVALID_PROFIT_RATIO`. La
    macchina tratta già il rifiuto (ABORTED / cancel completo, invariato), quindi niente
    gamba lasciata a mercato oltre al parcheggio da 1,00, che viene annullato.
  - Giudizio: **MEDIUM, NON VERIFICATO**. Non so quale grandezza confronti Betfair. Da
    provare dal vivo, o scegliendo la quota che tiene `round(L)` nella banda.
- **Parcheggio abbinato per errore**: `advance_submin` porta la macchina in ABORTED senza
  ritentare (invariato dalla patch). Il bot resta con 1,00 abbinato alla quota di parcheggio.
- **Cancel fallito**: timeout del taglio, poi cancel completo e ABORTED (invariato).
  `INVALID_PROFIT_RATIO` sul cancel porta allo stesso esito.
- **Importo finale ≥ 0,50**: verificato da `verifica_importo_finale` in tutti gli ingressi
  reali (motore via `verdetto_minimi`, coda `_start_submin`, worker `_place_sub_minimum`,
  Omega `place_submin_live`). Le mutazioni M8, R10 e R11 lo confermano.

### 2d. Il rifiuto `SOTTO_MINIMO_NON_PIAZZABILE` arriva al bot?

| strada | arriva? | prova |
|---|---|---|
| canale, sincrona (`_controlla` → `Rifiuto`) | **SÌ**, nell'`ack.motivo` (`"SOTTO_MINIMO_NON_PIAZZABILE: …residuo…trader…"`) | `motore_ordini.py:941-942` → `_rifiuta_registrato`; test `test_motore_sotto_minimo_senza_vie_rifiuto_esplicito_mai_rest` |
| canale, **aggancio al volo** (comando accettato, poi guardie rifatte) | **NO** | `motore_ordini.py:1433-1445`: `errore = str(r)` → `_esegui(errore_forzato=…)` → `:1309` `raise ValueError` → `:1349` `_emetti(…, riga_specchio_da_esito(...))`. `riga_specchio_da_esito` (`:538`) costruisce SOLO le chiavi `CHIAVI_SPECCHIO` (`:153`), senza errore né motivo. L'evento `order` ha `fase:"rifiutato"` e **nessun codice** |
| canale, errore del dispatch (es. `build_order` che solleva dentro l'esecutore) | **NO**, stessa riga `:1349` | come sopra |
| canale, `INVALID_BET_SIZE` vero di Betfair | in parte: `errore_betfair:"INVALID_BET_SIZE"` + `ripiego_050.motivo` (`:1854`), non il codice `SOTTO_MINIMO_NON_PIAZZABILE` | test `test_motore_ripiego_050_...` |
| Safe fuori canale | **SÌ**: `PlaceOutcome.error_code` + log `place_rifiutato critical` | `execution.py:814-825` |
| Omega REST | **SÌ**: `PlaceRifiutato(error_code=…)` | `omega_market.py:1007-1009` |
| worker coda / greenup | come `error` della riga (testo con il codice) | `live_order_worker.py:2144-2148` |

**Il delegato di Mike ha ragione** sulla strada asincrona: l'evento del runner non porta
codici (file e righe sopra). Correzione proposta: aggiungere `extra={"errore": errore}`
(o `codice`) all'`_emetti` di `_esegui` quando `ok` è False. È piccola e va nel perimetro del
runner. Nessun bot (Safe, Omega) consuma oggi il codice `SOTTO_MINIMO_NON_PIAZZABILE`: il
grep lo trova solo nei produttori. Mike lo legge dal testo del motivo (patch di Mike).

### 2e. Ripiego dopo un INVALID_BET_SIZE vero

- **Una sola volta**:
  - `piano["ripiego_050"]` blocca il secondo ripiego;
  - la taglia rifiutata va in `_taglie_rifiutate`;
  - il ripiego rifiutato viene emesso «rifiutato» senza un terzo tentativo.
  Il test lo prova e le mutazioni M5/M6 lo confermano.
- **Mai la stessa taglia**: chiave `(mode, lato, size)`, controllata in `_applica_minimi`
  prima dell'invio.
- **Solo live**: `sorveglia = mode=="live" and action=="place"`.
- **Solo dopo il rifiuto vero**: `responses.place_response.error_code`, il campo vero di
  flumine (`baseexecution._order_logger` → `responses.placed(instruction_report)`;
  betfairlightweight `PlaceOrderInstructionReports.error_code`).
- **Divergenza da portare all'utente**: le regole dicono «NESSUN passo di 0,50». Il ripiego
  reintroduce il passo DOPO un rifiuto e lascia un residuo dichiarato (0,47 su 7,47). È
  difensivo e oggi teorico, perché la punta 7,47 è stata accettata. Ma va approvato
  esplicitamente, perché è «una gamba lasciata parzialmente» (feedback 01/10).
- La chiave della taglia è **globale** (tutti i mercati, tutte le selezioni, fino a 500
  voci). È corretta se `INVALID_BET_SIZE` dipende solo dall'importo, come dicono gli enum di
  Betfair («invalid for your currency or your regulator»).

### 2f. Diario: «chiesto» e «mandato»

- **Comando** (`inviato`, `parametri` = chiesto): presente.
- **Traduzione**: riga `tradotto` con originale e mandato, PRIMA della riga `ordine` (testata).
  Se la traduzione non si può scrivere, niente ordine (`M_DIARIO`).
- **Ripiego**: riga `inviato` con `canale:"ripiego_050"`.
- **Rifiuto di taglia**: riga `rifiuto_taglia` scritta con `durevole=False`. Accettabile,
  perché nessun ordine parte.
- **Safe**: log `place_rifiutato` con size chiesta e residuo.
- **Esito: SÌ.**

### 2g. Costanti cambiate (nessuna di strategia)

Costanti del listino o nuove:
- `IT_BACK_MIN_STAKE` 2,00 → 1,00 (alias);
- `IT_LAY_MIN_SIZE` 0,50 → 1,00;
- `IT_BACK_STEP` 0,50 → 0,50, ora usato solo per il ripiego;
- `SUBMIN_ABS_MIN_SIZE` 0,01, spostato da `submin` a `live_order_build`;
- nuove: `TOLLERANZA_EQUIVALENZA` 0,01, `SORVEGLIANZA_TAGLIA_S` 20,
  `MAX_TAGLIE_RIFIUTATE` 500, `LIABILITY_MIN_RESIDUO_LAY` 0,008.

Costanti di Safe e Omega:
- Safe `_min_size_live` 2,00 / 0,50 → 1,00 / 1,00;
- Omega `SUBMIN_MIN_BACK` 2,00 → 1,00, `SUBMIN_MIN_LAY` 0,50 → 1,00.

Nessuna soglia, quota, timing o stake di strategia è stato cambiato: il diff di
`omega_service`, `bot_service` e `mike/engine` è vuoto.

Una condotta è cambiata **come effetto** delle regole:
- una chiusura Safe sotto il minimo sulla coda/REST passa al place-and-trim e **perde il
  FOK** (test D5/D8 della mia classificazione);
- un'apertura sotto il minimo fra 1,00 e 2,00 ora va diretta, senza trim.
Sono effetti delle regole, non modifiche di strategia, ma l'utente va informato.

**P1 (MEDIUM-HIGH): il paper non è lo specchio del live.**
- Dove: `build_order(simulato_ammette_sotto_minimo=not live)` in `_costruisci_chiusura`.
- In paper le gambe greenup/cash-out sotto il minimo, **anche sotto 0,50** (il take-profit
  Omega ≈ 0,28), sono eseguite DIRETTE.
- In live le stesse diventano place-and-trim, o un rifiuto sotto 0,50.
- È il catalogo §7 n. 14 («paper più generoso del live»). Safe fuori canale rifiuta invece
  sotto 0,50 «uguale in paper e in live»: il repo è incoerente con se stesso.
- Correzione minima: in paper, sotto 0,50, lo stesso rifiuto del live. Fra 0,50 e 1,00
  almeno dichiarare la differenza.

**P2 (MEDIUM): fuori canale non c'è l'equivalente.**
- Su coda e REST (Safe) e nel greenup del worker non si prova l'equivalente.
- Esempio: una chiusura Safe di 0,43 su Over/Under via coda è RIFIUTATA, mentre via canale
  sarebbe l'equivalente 7,31 @1,06.
- Contrasta con l'ordine del verdetto «per ogni ordine». È motivato per il greenup (il
  follow-through rilegge la stessa selezione), non per la coda di Safe.
- Va deciso con l'utente.

## 3. Test: classificazione dei test riallineati

Classificazione fatta da un sotto-agente in sola lettura. Ho verificato di persona D4, D7, gli
xfail e la manopola.

- **Conteggio**: 111 funzioni `def test_` toccate, contro i 121 dichiarati. La differenza sta
  nei parametri: test_place_and_trim 7 funzioni contro 15 dichiarati, tennis
  minimo_e_specchio 6 contro 10, condotta_ordini 4 contro 12. Il totale dei parametri supera
  121. Nessun file ha un assert tolto senza sostituto o un `==` diventato `>=`.
- **A (solo numeri del listino)**: circa 80 funzioni. Importi sotto il minimo 1,20-1,50 →
  0,70-0,76; parcheggio 2,00 → 1,00; riduzioni ricalcolate; punta al centesimo; tennis «al
  minimo» 1,00.
- **B (manopola `SAFE_MIN_SIZE_LIVE=0.01`)**: 9 test (Safe bot_service ×3, Safe
  test_audit `test_rev_m3`, Omega omega_audit ×3, omega_greenup ×2). Giudizio:
  - Nei 5 test Omega la manopola **nasconde una condotta che in live è RIFIUTATA**: il
    take-profit a ~0,28 viene asserito come `greenup done`.
  - Nei test di Safe trasforma un place-and-trim in un place diretto.
  - È onesto solo se dichiarato. Manca un test gemello con la manopola spenta che asserisca
    il rifiuto e il residuo dichiarato (reperto 3).
  - La manopola non è impostata nel `.env` del principale (verificato: 0 occorrenze).
- **C (xfail)**: 8 test, conteggio confermato dall'esecuzione. Tutti
  `@pytest.mark.xfail(strict=False, reason=XFAIL_REPERTO_1)` **senza `raises=`**. Non stretti:
  - un XPASS non fa fallire la suite;
  - qualunque eccezione viene mascherata, anche un errore di fixture.
  Sono motivati (resto sotto 0,50 impossibile per legge) e messi sul singolo test o
  parametro, non sul modulo. Raccomandazione: `strict=True, raises=AssertionError`.
  Incoerenza: `test_spezza_esatta` con 2,02 → (2,00 + 0,02) e 3,15 → (3,00 + 0,15) resta
  VERDE con la condotta vecchia (passo 0,50 e resto sotto 0,50, `condotta_ordini.diretta_ok`
  e `spezza_esatta` non toccati). Stessa causa: una sola riga in xfail.
- **D (condotta/sequenza/assert cambiati)**: 21 casi. Tutti riconducibili alle regole
  nuove, tranne:
  - **D4 INDEBOLITO** (verificato): `test_safe_kill_switch_rest_o1::test_kill_attivo_anche_il_sotto_minimo_si_ferma`.
    La size passa da 0,73 a **1,73**, che è SOPRA il minimo 1,00. Il test non esercita più
    il sotto-minimo, e il commento aggiunto è **falso** due volte: dice «1,73 sotto il
    minimo» e «sotto 1,00 rifiuto già SOTTO_MINIMO» (0,73 va al trim REST). Doveva restare
    0,73.
  - **D7 copertura persa** (verificato): `test_audit::test_rev_c2_il_minimo_2_euro_non_blocca_le_chiusure`.
    Le chiusure restano 1,40, ora sopra il minimo: il nome del test è falso e il caso
    «chiusura sotto il minimo non bloccata» non è più provato qui.
  - **D17/D18**: il prezzo di parcheggio nei test passa da 1,01 a 1,03/1,04. Non è un numero
    del listino ma la regola nuova `1+0,008/S`, cioè una condotta del motore e non della
    strategia. Va bene, ma va detto all'utente.
  - **D5/D8**: la chiusura sotto il minimo sulla coda perde il FOK (vedi §2g).
  - **D12**: un finto `SimpleNamespace(step=done)` al posto dello `SubminState` vero. Chiavi
    minime: da allineare al vero.
- Nessun test cambiato per far passare un comportamento di strategia diverso.

## 4. Tabella caso → test (21 test nuovi più i riallineati)

| caso | test |
|---|---|
| (a) nessun place diretto sotto 1,00 (motore) | `test_motore_sotto_minimo_senza_vie_rifiuto_esplicito_mai_rest`, `test_motore_punta_070_..._place_and_trim` |
| (a) worker, chiusura live | `test_chiusura_live_sotto_minimo_mai_un_place_diretto`, `test_chiusura_live_opt_out_rifiuto_esplicito` |
| (a) Safe / Omega fuori canale | riallineati `test_audit::test_m31_*`, `test_execution`, `test_p_blocco3`, `test_place_and_trim::test_cinque_centesimi_mai_tentati` |
| (a) **paper** | **SCOPERTO** per il greenup/cash-out paper. Il motore in paper è coperto in modo indiretto dai test submin paper (mutazione R5 rossa) |
| (b) equivalenza, numeri di oggi | `test_numeri_di_oggi_equivalente_e_scarti`, `test_equivalente_tick_mai_peggiore...`, `test_equivalente_di_una_punta_e_una_banca_col_tick_in_giu`, `test_banca_030_due_esiti...`, `test_equivalente_anch_esso_sotto_il_minimo_non_si_usa`, `test_motore_banca_043_mandata_come_punta_731...` |
| (b) **mercato a 3+ esiti con book presente** | **SCOPERTO** (mutazione R8 sopravvive, vedi §6) |
| (c) parcheggio, quota e abbinabilità | `test_parcheggio_della_banca_supera_invalid_profit_ratio`, `test_submin*`. **Banda di arrotondamento non testata** |
| (c) finale ≥ 0,50 | `test_regola_d_ingresso_della_macchina`, `test_motore_ordini::test_place_and_trim_non_percorribile...[0,49]` |
| (d) rifiuto con residuo, sincrono | `test_motore_sotto_minimo_senza_vie...` (verifica «trader» nel motivo) |
| (d) rifiuto sulla strada asincrona | **SCOPERTO** (e difettoso, §2d) |
| (e) ripiego unico, taglia non ritentata | `test_motore_ripiego_050_solo_dopo_invalid_bet_size_e_una_volta`, `test_motore_nessun_ripiego_senza_invalid_bet_size`, `test_ripiego_ai_050_puro` |
| (f) diario `tradotto` prima di `ordine` | `test_motore_banca_043...` |
| idempotenza dell'aggancio | `test_motore_aggancio_ripete_le_guardie_sull_ordine_chiesto` |
| riporto degli abbinati | `test_riporta_abbinato_all_originale`, `test_motore_banca_043...` |
| cancel / replace su ordine tradotto | **SCOPERTO** |

## 5. Esecuzione dei test mirati (numeri esatti)

Avvertenza d'ambiente: **nel worktree** i test leggono il `.env` del checkout principale
(directory padre), e alcuni test Safe diventano rossi per ragioni d'ambiente. Esempio:
`test_l4_la_guardia_combo...` da solo è rosso nel worktree (16 s), verde in un export
isolato, sia di base sia patchato. Per questo i numeri buoni li ho presi su **export isolati**
(`git archive` di `HEAD` e `HEAD~1` in una cartella temporanea), confrontando base e patch.

| set | patchato | base `HEAD~1` | durata |
|---|---|---|---|
| 21 test nuovi (worktree) | **21 passed** | — | 2,4 s (24 s con l'avvio) |
| 33 file di test toccati più quello nuovo (worktree) | 1153 passed, 1 failed (`test_l14_ttl...`, d'ambiente o d'ordine), 8 xfailed | — | 111,6 s |
| stessi file, export isolato | **1149 passed, 3 failed, 2 skipped, 8 xfailed** | **1125 passed, 3 failed, 2 skipped** | 40-88 s / 59 s |
| i 3 rossi | `test_audit::test_l14_ttl_della_cache_lambda`, `test_cert::test_i_due_motori_hanno_esattamente_gli_stessi_numeri`, `test_cert::test_parita_default_dello_stake_fra_i_due_motori` | **gli STESSI 3 sulla base** | preesistenti, dipendenti dall'ordine |
| `test_audit_2026_09_11.py` da solo, export | 70 passed | 70 passed | 18 s |
| 117 file di test NON toccati che importano motore/submin/build/worker/Safe execution/Omega market | **2444 passed, 8 failed, 20 skipped** | **2444 passed, 8 failed, 20 skipped**, gli stessi 8 | 130 s / 115 s |
| gli 8 rossi | migrazioni SQL e finti del frontend (file non esportati: `migrations/`, `frontend/`) | identici | d'ambiente dell'export |

Conclusione: la patch non introduce nessun rosso nei test mirati. La differenza di +24 verdi
e +8 xfail corrisponde ai 21 test nuovi più i parametri aggiunti. Non ho lanciato la suite
intera né replay, come richiesto.

## 6. Falsificazione

**Le 8 del delegato**, rilanciate da me in un export isolato: **8/8 ROSSE**, ripristino a 21
passed.

| | mutazione | esito |
|---|---|---|
| M1 | esenzione `reduces_liability` rimessa | ROSSO (1) |
| M2 | floor della punta a 0,50 | ROSSO (3) |
| M3 | tick dell'equivalente al più vicino | ROSSO (1) |
| M4 | eventi non riportati al chiesto | ROSSO (1) |
| M5 | nessun ripiego | ROSSO (1) |
| M6 | taglia ritentata identica | ROSSO (1) |
| M7 | floor del trim tolto dal verdetto | ROSSO (3) |
| M8 | regola d'ingresso della macchina tolta | ROSSO (1) |

Nota: le 8 del delegato valutano solo il file nuovo.

**Le mie 15**: `falsifica_revisore_runner_minimi.py`, set di 12 file, 527 test; la base
dell'export è verde. Ripristino byte per byte.

| | mutazione | esito | test che la vede |
|---|---|---|---|
| R1 | equivalente BANCA col tick in su (limite peggiore) | ROSSO (1) | `test_equivalente_di_una_punta_e_una_banca_col_tick_in_giu` |
| R2 | parcheggio abbinabile ammesso (guardia tolta) | ROSSO (1) | `test_parcheggio_della_banca_supera_invalid_profit_ratio` |
| R3 | parcheggio LAY sempre a 1,01 | ROSSO (4) | nuovo + `test_submin` ×2 + nucleo |
| R4 | rifiuto senza il residuo dichiarato | ROSSO (2) | `test_banca_030_...`, `test_motore_sotto_minimo_...` |
| R5 | paper: il motore salta i minimi (0,99 diretto) | ROSSO (13) | `test_motore_ordini_2026_09_24` place-and-trim paper |
| R6 | `IT_MIN_LAY` = 0,50 | ROSSO (12) | `test_p_blocco3`, `test_cashout_pro`, ... |
| R7 | `IT_MIN_BACK` = 2,00 | ROSSO (24) | |
| **R8** | **equivalente anche su mercati a 3+ esiti** (`len != 2` → `< 2`) | **VERDE: SOPRAVVIVE** | nessuno. **Buco di copertura**: nessun test con un `market_book` a 3 runner. Un difetto qui manderebbe su un Match Odds calcio a 3 esiti un «equivalente» SBAGLIATO (soldi) |
| R9 | tolleranza dell'equivalenza a 1,00 EUR | VERDE: sopravvive | nessuno. Benigno: con il tick «mai peggiore» e la size al centesimo lo scarto peggiore è ≥ −0,005, quindi il ramo è una guardia difensiva oggi irraggiungibile. Un test diretto andrebbe comunque aggiunto |
| R10 | Safe fuori canale: rifiuto certo sotto 0,50 tolto | ROSSO (1) | `test_audit::test_m31_in_paper_qualsiasi_importo_si_abbina` |
| R11 | Omega REST: regola d'ingresso tolta | ROSSO (2) | `test_place_and_trim::test_cinque_centesimi_mai_tentati`, ... |
| R12 | worker: chiusura live sotto il minimo di nuovo diretta | ROSSO (5) | `test_cashout_pro::test_closing_leg_ripiega_sul_submin_solo_in_live`, ... |
| R13 | Safe: chiusure di nuovo esenti fuori canale | ROSSO (3) | `test_audit::test_m31_*`, `test_execution` |
| R14 | quota media non riportata al chiesto | ROSSO (1) | `test_motore_banca_043_...` |
| R15 | chiave della taglia senza il modo | ROSSO (1) | `test_motore_ripiego_050_...` |

Esito: 13 rosse, 2 sopravvissute. R8 è un **buco vero**, R9 è benigno.

Ripristino: i 7 file mutati sono stati confrontati byte per byte con l'export originale e
sono **identici**. Il giro di ripristino ha dato un rosso:
`test_motore_ordini_2026_09_24::test_latenza_logica_comando_place_sotto_20_ms` (p95 38,6 ms
contro 20). Questo test misura il TEMPO.

Sonda `sonda_latenza_motore.py`, base e patch alternate 4 volte:

| | p50 | p95 | max |
|---|---|---|---|
| base | 2,0-2,8 ms | 2,4-4,0 ms | 18-22 ms |
| patch | 1,2-3,1 ms | 1,4-6,2 ms | 13-34 ms |

Tutti verdi: il rosso è carico della macchina condivisa, non una regressione. Il costo del
verdetto è al più +1 ms sul p50.

## 7. Reperti aperti del delegato, con giudizio

1. **Bot fuori perimetro** (scalper, sniper, scalper tennis, uscite esatte tennis):
   confermato. `condotta_ordini.diretta_ok` / `spezza_esatta` impongono ancora il passo 0,50,
   e i test 2,02 / 3,15 restano verdi. I `MIN_STAKE = 2.0` dei bot tennis/sniper sono
   duplicati. Resta aperto, non mio.
2. **Mike con costanti duplicate**: risolto dalla patch di Mike (§9).
3. **Reperto 3, divergenza di strategia.**
   - *Take-profit di Omega a 1000 (≈ 0,28 €)*:
     - Oggi nel codice patchato, sul canale (CS a 3+ esiti), è `Rifiuto(SOTTO_MINIMO_NON_PIAZZABILE)`
       con l'ack e il residuo nel motivo; fuori canale e su REST è `PlaceRifiutato` /
       `PlaceOutcome error`, e nessun ordine parte.
     - **Se passa dal greenup del worker**: in LIVE la gamba va a `_place_sub_minimum` →
       `verifica_importo_finale` solleva → riga `error`. In PAPER viene eseguita diretta (P1).
     - In live: la banca 5 @55 resta aperta fino al regolamento, con il P&L non bloccato
       (rischio pieno della liability 270 €).
     - **NON VERIFICATO** cosa faccia Omega dopo il rifiuto (ritenta a ogni giro? CRITICAL e
       proposta all'utente?): nessun consumatore del codice nel grep.
   - *Residui di Safe sotto 0,50*: sono rifiuti certi, con log `critical` e residuo
     dichiarato. Fra 0,50 e 1,00 vanno al trim (senza FOK). In live il residuo resta aperto.
     Nessuna «proposta» automatica all'utente.
   - Le due domande per l'utente del delegato sono corrette e vanno poste.
4. **Equivalente non abbinato con prezzi virtuali**: confermato dal calcolo, perché il tick
   in su richiede Under ≥ 1,06 (cioè Over ≤ 17,67). Con FOK il bot vede «scaduto» e ripete
   la sua logica. In live il rischio è una chiusura che non parte mentre l'Over a 18 era
   disponibile. È il prezzo di «mai un limite peggiore»: va bene, ma va DETTO all'utente.
5. **Cancel con `size_reduction` sull'ordine tradotto**: confermato, ed è **più grave di
   quanto scritto**. Anche `replace` (`new_price`) non viene convertito.
   - Il bot ha il `bet_id` VERO (la riga riportata lo conserva). Un `replace` a 17 «in
     termini Over» sposterebbe la punta Under a 17. Un `cancel size_reduction 0,20` ridurrebbe
     7,31 di 0,20 invece che di 3,40.
   - Safe `porta_ordini` espone `cancel`/`replace` sul canale (`porta_ordini.py:89,226,291`).
   - Il motore deve rifiutare cancel parziale e replace su un ordine tradotto, oppure
     convertirli. **HIGH prima di mandare chiusure appoggiate (non FOK) via canale.**
6. **LiveExposureControl per selezione**: plausibile, non verificato.
   - In più: dopo un equivalente le esposizioni **per selezione** del blotter non sono piatte
     (Over aperto, Under opposto), anche se economicamente lo sono.
   - Il greenup del worker e ogni bot che ricalcola la «posizione» dal blotter per selezione
     possono rifare la chiusura: è una **doppia chiusura**.
   - Il delegato l'ha evitato solo nel greenup. Va verificato sui bot (Mike controlla il
     piatto). **NON VERIFICATO.**
7. **Gambe greenup/cash-out in PAPER dirette sotto il minimo**: confermato e **non
   accettabile** come lasciato (P1).

## 8. Interazione con `MIKE_CHIUSURA_COPERTURA.patch` (base `ebfab2a`)

- `git apply --3way --check` (copia LF), sopra il ramo con il runner patchato:
  - 13 file applicati **puliti** (mike, frontend);
  - 2 file nuovi;
  - **un solo conflitto: `Betfair/stream/trading/minimi_it.py`** (aggiunto da entrambe).
- Nessun altro file in comune: la patch di Mike non tocca `live_order_build`, `execution`,
  `motore_ordini` né `test_mike_d1ter_submin_fok_parita` (toccato dal runner).
- Confronto di `minimi_it.py`:
  - **Mike**: `IT_MIN_BACK=1.00`, `IT_MIN_LAY=1.00`, `IT_FLOOR_LEGGE=0.50`,
    `SUBMIN_IMPORTO_FINALE_MIN=0.50`.
  - **Runner**: gli stessi quattro con gli stessi valori, più `IT_PASSO_PUNTA_RIPIEGO` e
    `SOTTO_MINIMO_NON_PIAZZABILE`.
  - Mike importa solo `IT_MIN_BACK`, `IT_MIN_LAY` e `SUBMIN_IMPORTO_FINALE_MIN`, e il suo
    test legge `IT_FLOOR_LEGGE`: tutti presenti nella versione del runner.
  - **Compatibili: tenere la versione del runner** (superinsieme).
  - Mike scrive la stringa `"SOTTO_MINIMO_NON_PIAZZABILE"` a mano (`RIFIUTI_PER_TAGLIA`):
    potrebbe importarla da `minimi_it`.
- Interazione funzionale:
  - Mike riconosce `SOTTO_MINIMO_NON_PIAZZABILE` solo nel testo del motivo. Sul canale
    arriva nell'ack sincrono, **non** nell'evento dell'aggancio (§2d).
  - Mike manda ora la punta equivalente da sé (≥ 1,00), quindi il motore non traduce: nessuna
    doppia traduzione.
  - La via REST di Mike (`service.py:2147`) non passa dal runner.

## 9. Reperti nuovi del revisore (non visti dal delegato)

1. **P1 (MEDIUM-HIGH)**: in PAPER il greenup/cash-out è diretto anche sotto 0,50, quindi il
   paper non è lo specchio del live (§2g).
2. **HIGH, condizionato**: cancel parziale e `replace` sull'ordine tradotto non convertiti,
   con il `bet_id` vero in mano al bot (§7.5).
3. **MEDIUM**: il codice del rifiuto non arriva al bot sulla strada asincrona e sugli errori
   del dispatch (`motore_ordini.py:1309/1349/1433-1445`, §2d).
4. **MEDIUM, non verificato**: con il parcheggio LAY `1+0,008/S`, per i residui 0,63-0,79 la
   liability arrotondata sta fuori dalla banda −20 %/+25 % (§2c).
5. **MEDIUM**: niente equivalente su coda/REST di Safe, quindi rifiuti sotto 0,50 su mercati
   a 2 esiti che via canale passerebbero (P2).
6. **MEDIUM**: rischio di doppia chiusura dopo un equivalente, per i bot che leggono
   l'esposizione per selezione (§7.6).
7. **LOW**: test D4 indebolito, con commento falso; D7 con nome falso; xfail non stretti;
   `test_spezza_esatta` 2,02 / 3,15 verdi con la condotta vecchia.
8. **LOW**: commenti e docstring stantii o falsi:
   - `config_stream.py` «back min EUR2.00»;
   - testa di `live_order_build` «finale >= 1,00»;
   - `submin.advance_submin` «>= 1,00»;
   - `_sub_minimum_floor` «2,00 / 0,50»;
   - `SubminState.placed_size`;
   - `porta_al_minimo_apertura`.
9. **LOW**: duplicati del listino fuori dal perimetro: `order_exec.MIN_STAKE_EUR=2.0`,
   `omega_model.MARKET_QUOTE_MIN_SIZE=2.0`, costanti morte `SUBMIN_PARK_PRICE_*`.
   `omega_market.place_order_live` è senza guardia dei minimi.
10. **LOW**: `altro_runner_due_esiti` decide «2 esiti» dal numero di runner del book, senza
    `number_of_winners`. Gli handicap asiatici a quarti non sono verificati.
12. **MEDIUM, buco di copertura (R8)**: nessun test prova che su un mercato a 3+ runner
    (Match Odds calcio, Risultato Esatto) l'equivalente NON si usi. La mutazione sopravvive.
13. **Ambiente**: `test_latenza_logica_comando_place_sotto_20_ms` è un test di tempo,
    instabile sotto carico (un rosso su 10 giri, uguale su base e patch).
11. **Ambiente**: nel worktree i test leggono il `.env` del principale e alcuni test Safe
    risultano rossi. È un rosso falso, non della patch, ma l'affermazione del delegato
    «`test_l4` rosso da solo anche su master» vale solo in quell'ambiente: in un export
    isolato è verde su base e patch.

## 10. Giudizio finale: **INTEGRABILE CON CORREZIONI**

Da correggere prima dell'integrazione (piccole, nel perimetro del runner):
1. Paper = live per le gambe greenup/cash-out: almeno il rifiuto sotto 0,50 anche in paper
   (`_costruisci_chiusura` / `simulato_ammette_sotto_minimo`), con un test.
2. Codice e motivo del rifiuto nell'evento `order` della strada asincrona (`_esegui`, `extra`
   con l'errore), con un test d'aggancio.
3. Motore: rifiutare (o convertire) `cancel` con `size_reduction` e `replace` su un ordine
   TRADOTTO, con un test.
4. Test: ripristinare D4 a 0,73 e correggere il commento; correggere D7 (chiusura sotto 1,00);
   xfail `strict=True, raises=AssertionError`; un test con un `market_book` a 3 runner
   (mutazione R8); un test gemello senza manopola per il take-profit di Omega (rifiuto e
   residuo dichiarato).
5. Commenti stantii o falsi (§9.8).

Da decidere con l'utente (non bloccano il codice, bloccano il live):
- il ripiego col passo 0,50 dopo `INVALID_BET_SIZE`, che lascia un residuo;
- l'equivalente fuori canale (P2);
- la chiusura sotto il minimo in coda senza FOK;
- il reperto 3 (Omega e Safe);
- la quota di parcheggio LAY e la banda;
- la doppia chiusura per selezione.

Prove dal vivo ancora necessarie (ordini piccoli decisi dall'utente): punta e banca da 1,00;
una punta non multipla di 0,50; trim a 0,50; trim LAY con residuo 0,70 (banda); equivalente
7,31 @1,06.

## 11. NON VERIFICATO

- Nessun ordine vero. Quale grandezza confronti Betfair per `INVALID_PROFIT_RATIO` (§2c).
- Comportamento di Omega e Safe DOPO un rifiuto `SOTTO_MINIMO_NON_PIAZZABILE`: ritentano a
  ogni giro? Proposta all'utente?
- Doppia chiusura per selezione nei bot dopo un equivalente; LiveExposureControl.
- Se un bot invii davvero `replace`/`cancel` parziale sul canale per chiusure tradotte.
- Equivalenza sui mercati asiatici a quarti, e sui mercati con `number_of_winners` ≠ 1 a 2
  runner.
- La suite intera e i replay: non lanciati, come da brief (li fa il coordinatore).
- I 121 test conteggiati per parametro: ho contato 111 funzioni, non ho ricontato i parametri
  uno per uno.
- Il riesame dei test della classe B e della classe D è in parte del sotto-agente. Ho
  verificato di persona D4, D7, gli xfail (eseguiti: 8 XFAIL veri, nessun XPASS) e la
  manopola nel `.env`.
