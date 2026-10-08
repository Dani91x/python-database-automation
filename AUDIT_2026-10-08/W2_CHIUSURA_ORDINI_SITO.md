# W2 - CHIUDERE DALL'APP GLI ORDINI FATTI SUL SITO (backend) - referto del delegato

Data: 08/10/2026. Worktree: `/home/user/python-database-automation/.claude/worktrees/agent-a1c21d4fd7008caf6`
(portato in avanti, fast-forward senza commit, da `8226d76` a `b5547eb`, la cima richiesta).
Nessun commit, nessun `git add`. Container cloud: nessun Betfair vero, nessun DB di produzione.

## 1. Che cosa c'era

Ordine dell'utente: «se apro dal sito devo poter chiudere anche dall'app». Il `greenup` del runner
(`Betfair/stream/live_order_worker.py::_do_greenup`) legge l'esposizione da
`blotter.get_exposures(strategy, ...)` (`_read_matched_exposures`), cioe' dai soli ordini che flumine
conosce per la strategia del runner. Gli ordini del sito non ci sono mai: flumine li riceve dallo
stream ordini (il runner e' iscritto senza filtro di strategia) e li scarta
(`flumine/order/process.py`, "Strategy not available to create order"; nota gia' scritta in
`esiti_ordini_canale.py` ~632-641). Quindi dalla pagina un ordine del sito si vede (RPC
`get_live_orders_account_open`) ma il `greenup` su quella selezione trova "posizione piatta" (o,
peggio, copre la posizione manuale del runner, che e' un'altra cosa).

## 2. Che cosa ho cambiato (file:riga, worktree)

| file | righe | cosa |
|---|---|---|
| `Betfair/stream/trading/esposizione_fuori_bot.py` (NUOVO, 267 righe) | tutto | logica PURA: costanti del contratto, riconoscimento per riferimenti e per riga di coda, normalizzazione (riusa `esiti_ordini_canale.ordine_del_conto`), esposizione abbinata (riusa `flumine.utils.calculate_matched_exposure`, la stessa del blotter), netto a size e formula del "vivo" dei verdetti di conto dei bot, effetto della copertura sui bot |
| `Betfair/stream/live_order_worker.py` | 1889-1892 | `_ft_enqueue_rehedge`: il re-hedge di una copertura fuori bot porta `params.esposizione` (senza, rileggerebbe il blotter: un'altra posizione). Per le altre righe il payload e' identico (test di parita') |
| `Betfair/stream/live_order_worker.py` | 2224-2503 | blocco nuovo: `_ordini_del_conto` (listCurrentOrders del mercato, paginato), `_proprietari_bot` (letture DB), `_classifica_conto`, `_netti_per_bot`, `_do_greenup_fuori_bot` |
| `Betfair/stream/live_order_worker.py` | 2518-2525 | `_do_greenup`: se `params.esposizione` e' presente (non null) si va a `_do_greenup_fuori_bot`; altrimenti NESSUNA riga del green-up di sempre e' cambiata (il diff del file e' di sole aggiunte: 294 righe +, 0 righe -) |
| `Betfair/stream/tests/test_greenup_fuori_bot_2026_10_08.py` (NUOVO) | 39 funzioni, 56 casi | vedi par. 4 |
| `Betfair/stream/tests/dati/greenup_parita_b5547eb.json` (NUOVO, 34 KB) | | fotografia di 51 scenari del `greenup` di b5547eb (vedi par. 4.6) |

Nessuna migrazione: la RPC `request_betfair_live_order` (ultima versione
`migrations/betfair_live_cashout_event_v2.sql`) passa `params` cosi' com'e' e il CHECK delle azioni non
cambia (`greenup` esiste gia'). Nessun file fuori perimetro toccato (frontend, mike/omega/safe,
`esiti_ordini_canale.py`, `engine/live_trading_strategy.py`, tennis: intatti).

### 2.1 Il contratto, come e' implementato

`{action:'greenup', mode:'live', market_id, selection_id, handicap:0, params:{esposizione:'fuori_bot'}}`

1. **Instradamento** (`_do_greenup`): `params.esposizione` assente o `null` -> green-up di sempre, byte
   per byte. Presente con qualunque altro valore che `'fuori_bot'` -> RIFIUTO esplicito (un refuso non
   deve mai ripiegare sul blotter: coprirebbe un'altra posizione). Oggi nessuno manda `esposizione`
   (verificato con grep su `frontend/src` e `Betfair/`): nessun flusso esistente cambia.
2. **Rifiuti espliciti, nessun ordine** (riga `error` col motivo): `mode != 'live'` ("solo LIVE - in
   prova gli ordini del sito non esistono"); parametri del green-up parziale o di un bot (`amount`,
   `target_price`, `place_at_ticks`, `cancel_unmatched`, `risk_rule_id`, `comando` = comando di un
   attore del motore, `fraction` diversa da 1); runner senza client reale; mercato non sottoscritto;
   strategy assente; conto non leggibile (REST KO, risposta inattesa, piu' di 10 pagine); DB non
   leggibile (una qualunque delle 5 letture); esposizione aperta senza prezzo (mercato sospeso / book
   vuoto, come oggi); copertura dell'app ancora appesa sul lato della copertura; copertura che farebbe
   dichiarare a un bot la sua posizione "chiusa dall'utente" (par. 3).
3. **Lettura del conto**: `client.betting_client.betting.list_current_orders(market_ids=[mid],
   from_record, record_count=1000)` sul client REALE della riga (`_client_for_mode`), stessa via di
   `reconcile_worker._fetch_current_orders`, senza filtro di strategia, paginata su `moreAvailable`.
   Ordini normalizzati nella grafia di Betfair con la funzione del canale del conto.
4. **Chi e' di un bot** (nel dubbio e' del bot, mai coperto). Solo regole che esistono gia':
   - `customerStrategyRef`: ammessi solo assente (sito) e `live` (`CUSTOMER_STRATEGY_REF` del terminale
     manuale calcio). Ogni altro valore e' escluso (mike/omega/safe REST, attori del motore, strategie
     flumine di scalper/sniper/theta/media under col nome della strategia, `tennis`, sconosciuti);
   - `customerOrderRef` con prefisso di bot: `reconcile_worker._OUR_ORDER_REF_PREFIXES` piu'
     `<attore>-` per ogni attore di `motore_ordini.ATTORI_COMANDO` tranne `desktop`;
   - le esclusioni della RPC `get_live_orders_account_open`: `bet_id` in `omega_trades` /
     `safe_strategy_trades` / `mike_trades` (mode live, QUALUNQUE `role`, anche `utente`, come la RPC),
     riga di `betfair_live_orders` con `source` diversa da `runner`/`account`;
   - in piu' la riga di `betfair_live_order_requests` con quel `bet_id`: `client_ref` con prefisso di
     bot, `params.source` di un bot (o `scalper`), `params.comando.attore` diverso da `desktop`. Serve
     per la finestra in cui un bot ha piazzato DALLA CODA del runner (`customerStrategyRef` 'live', ref
     di flumine) e non ha ancora scritto il `bet_id` nella sua tabella.
   Letture DB: 5 select per blocco di 100 `bet_id` (solo gli ordini della selezione, e dell'altra nel
   mercato a due esiti).
5. **Matematica**: W/L dell'ABBINATO dei soli ordini fuori bot con `calculate_matched_exposure` di
   flumine (la funzione con cui il blotter calcola `matched_profit_if_win/lose`); mercato a due esiti
   esaustivi letto sul mercato come nel green-up di sempre (punto 9 del 02/10); `compute_greenup`
   (fraction 1, nessun tick oltre, nessun prezzo scelto) al miglior prezzo opposto (`_best_prices`);
   gamba costruita e piazzata con `_costruisci_chiusura` + `_place_closing_leg` (place-and-trim sotto il
   minimo, stessa regola di oggi). La copertura e' un ordine MANUALE della strategia del runner
   (`customerStrategyRef` 'live', specchio `source='runner'`).
6. **Idempotenza**: il conto si rilegge a ogni comando; la copertura gia' abbinata e' un ordine 'live'
   fuori bot e rientra nell'esposizione: secondo comando -> "esposizione fuori bot gia' piatta: nessun
   ordine" (riga `done`, `size` null, nessun follow-through). Se la copertura precedente e' ancora
   EXECUTABLE non abbinata sul lato della copertura -> rifiuto (mai due coperture vive).
7. **Follow-through A4**: la riga `done` ha `bet_id`/`customer_order_ref`/`size` come il green-up di
   sempre, quindi `_ft_legs_from_result` la segue; il re-hedge riaccoda `greenup` con
   `{fraction:1.0, ft_parent, ft_retry, esposizione:'fuori_bot'}` e rilegge il conto.
8. **Esito** (`result`, chiavi ADDITIVE solo su questo ramo): `esposizione:'fuori_bot'`,
   `conto:{fuori_bot:[bet_id], bot:[{bet_id, motivo}], w, l}`, ed eventualmente
   `bot_toccati_nel_verdetto` (par. 3). Il `detail` riassume (troncato a 300 come sempre).

Tennis: fuori (decisione dell'utente: niente ordini manuali tennis nella pagina). Il ramo vive solo nel
worker calcio; `tennis_live_order_worker` non e' toccato.

## 3. La verifica sui verdetti di conto di Mike / Omega / Safe - REPERTO

Il brief chiede di verificare che dopo la copertura Mike/Omega/Safe non dichiarino "chiuso dall'utente"
una loro posizione intera. Ho usato le funzioni VERE (`mike.service._verdetto_di_conto`,
`omega_service.sorveglia_posizione_di_conto`, `safe_strategy.bot_service._netto_su_selezione` + la stessa
formula) sulle righe normalizzate da `omega_market._riga_corrente`.

**I tre verdetti confrontano SIZE (BACK meno LAY dell'abbinato), non soldi.** Un green-up corretto
della parte del sito ha una size diversa dalla puntata del sito appena il prezzo si e' mosso
(size = (W-L)/prezzo). Risultato, provato nei test:

| caso (posizione del bot sulla stessa selezione) | copertura | netto di conto | verdetto VERO del bot |
|---|---|---|---|
| Mike BACK 10; sito BACK 5 @1,50; lay 1,50 (prezzo fermo) | LAY 5,00 | 10 | intera |
| idem, lay 1,60 (prezzo salito) | LAY 4,69 | 10,31 | intera |
| idem, lay 1,40 (prezzo sceso) | LAY 5,36 | 9,64 | **"ridotta_dall_utente"** (solo dichiarazione critica, Mike continua a proteggere) |
| Mike BACK 2; sito BACK 10 @5,0; lay 1,50 | LAY 33,33 | -21,33 | **"chiusa_dall_utente"**: Mike smetterebbe di gestire la partita |
| Omega LAY 5,26; sito BACK 5 @3; lay 2,5 | LAY 6,00 | -6,26 | intera |
| Omega LAY 5,26; sito LAY 5 @3; back 2,5 | BACK 6,00 | -4,26 | **"ridotta_dall_utente"** |
| Safe BACK 10; sito BACK 5 @1,50; lay 1,40 | LAY 5,36 | 9,64 | stessa aritmetica: ridotta |

Che cosa fa il worker (nel mio perimetro, senza toccare i bot):
- calcola, con la STESSA formula dei tre verdetti, che cosa vedra' ogni bot presente sulla selezione
  (posizione = netto delle sue gambe abbinate sul conto, raggruppate per bot: tabella > strategia >
  ref);
- **"chiusa" -> RIFIUTO, nessun ordine** ("la copertura ... porterebbe il netto di conto ... e il bot
  X la dichiarerebbe CHIUSA DALL'UTENTE");
- **"ridotta" -> l'ordine parte** e l'esito lo DICE (`bot_toccati_nel_verdetto`, numeri identici al
  verdetto vero: test `test_mike_ridotta...`, `test_omega_ridotta...`, `test_safe_stessa_aritmetica...`).

Il difetto vero e' nei verdetti dei bot (perimetro W3): andrebbero calcolati in esposizione (soldi), non
in size, oppure dovrebbero escludere dall'"altrui" un gruppo di ordini dell'utente che e' piatto in soldi.
Vale anche OGGI senza questo cantiere: lo stesso green-up fatto dall'utente direttamente sul sito, o un
green-up dell'app su ordini manuali dell'app, produce gli stessi verdetti. Vedi "Decisioni per l'utente".

## 4. Test (tutti in `Betfair/stream/tests/test_greenup_fuori_bot_2026_10_08.py`)

Finti: il conto e' `flumine.clients.BetfairClient` VERO attorno all'`APIClient` VERO di
betfairlightweight con il SOLO trasporto (`betting.request`) sostituito: la risposta e' il JSON di
`listCurrentOrders` (chiavi camelCase di Betfair, chiavi facoltative ASSENTI per il sito) e la
trasforma in `CurrentOrders` la libreria. Book = `MarketBook` vero. Tabelle con le colonne vere. Il
runner LIVE registra i due client (reale + simulato) come in produzione.

1. Solo sito BACK -> LAY 6,00 @2,5 (`customerStrategyRef` 'live', client reale, un solo
   `listCurrentOrders` col solo `marketIds`, blotter MAI letto). Solo sito LAY -> BACK 5,00 @2,0.
2. Sito + app (si sommano: LAY 9,20). Sito + Mike REST + Omega dalla coda (bet_id in omega_trades) +
   scalper (specchio) + Safe appena piazzato (solo riga di coda `safe-t4`): copertura SOLO del sito,
   motivi di esclusione esatti. Cinque `customerStrategyRef` non dell'utente esclusi. `mike_trades`
   `role='utente'` escluso come nella RPC.
3. Parziale (conta solo l'abbinato: LAY 4,80); solo non abbinati -> nessun ordine; idempotenza
   (secondo comando dopo la copertura abbinata: W=L=1,00, nessun ordine); copertura dell'app appesa ->
   rifiuto; ordine del SITO appeso -> non ferma; mercato a due esiti piatto sul mercato -> nessun
   ordine; paginazione (3 pagine, `fromRecord` 0/2/4).
4. Rifiuti: paper (motivo "solo LIVE", nessuna lettura del conto), conto illeggibile, DB illeggibile
   (x3 tabelle), runner senza client reale, runner PAPER, 7 parametri non ammessi, 5 valori di
   `esposizione` sconosciuti (blotter mai letto); `fraction=1.0`+`ft_*` ammessi; cammino vero della
   coda `_process_once` (pending -> claim -> done).
5. Follow-through: re-hedge fuori bot porta `esposizione`; re-hedge di sempre IDENTICO (dict esatto);
   `_ft_legs_from_result` segue la copertura.
6. **Parita'** (`test_parita_byte_per_byte_con_il_greenup_di_b5547eb`): 51 scenari (lay-led, back-led,
   piatta x 16 combinazioni di params: None, {}, fraction, amount, amount cappato, target_price,
   place_at_ticks, persistence, cancel_unmatched, `esposizione:null`, malformati, sotto-minimo con
   `allow_sub_minimum=False`, ft; piu' 3 sul mercato a due esiti). La fotografia
   `dati/greenup_parita_b5547eb.json` e' stata PRODOTTA dal worker di b5547eb (script differenziale
   che carica `git show b5547eb:Betfair/stream/live_order_worker.py` come modulo a parte ed esegue gli
   stessi scenari sui due worker): **51 scenari, 0 diversi** (ordini con lato/prezzo/size/persistenza/
   kwargs, righe di coda scritte senza `processed_at`, errori, tabelle toccate). Il test confronta il
   worker di oggi con quella fotografia: 27 scenari con ordine, 11 rifiuti, il resto no-op.
7. Logica pura e contratti: riferimenti, riga di coda, esposizione (numeri a mano = flumine), un
   `CurrentOrder` vero normalizzato, `effetto_sui_bot`; `STRATEGIA_MANUALE_APP ==
   CUSTOMER_STRATEGY_REF`, `TABELLE_BOT == reconcile_worker._TABELLE_BOT`, prefissi di reconcile
   inclusi, testo della migrazione della RPC (source e tre tabelle); `EPS_VERDETTO_BOT >=` le tre
   tolleranze; la formula del "vivo" presente identica nei tre verdetti (se un bot la cambia, rosso).
8. Bot dopo la copertura, funzioni VERE: Mike intera (x2 prezzi), Mike ridotta = previsione, Mike
   "chiusa" -> rifiuto + prova che senza rifiuto il verdetto vero direbbe `chiusa_dall_utente`; Omega
   intera; Omega ridotta = previsione; Safe stessa aritmetica.

### 4.1 Falsificazioni (script `AUDIT_2026-10-08/W2_CHIUSURA_ORDINI_SITO/strumenti/falsifica.py`, ripristino verificato con sha256)

sha prima e dopo: `live_order_worker.py` 6b856a3e...700e, `esposizione_fuori_bot.py` 6b36c5a8...2377;
`git diff` identico prima/dopo (cmp), `grep -c MUTAZIONE` = 0 su entrambi.

| # | mutazione | esito |
|---|---|---|
| M1 | instradamento fuori_bot spento (`if False`) | ROSSO 1 |
| M2 | ogni `customerStrategyRef` accettato | ROSSO 6 |
| M3 | tabelle dei bot non lette | ROSSO 2 |
| M4 | source dello specchio ignorata | ROSSO 1 |
| M5 | riga di coda ignorata | ROSSO 1 |
| M6 | il chiesto (`priceSize.size`) al posto dell'abbinato | ROSSO 1 |
| M7 | nessun rifiuto per modalita' paper | ROSSO 1 |
| M8 | DB illeggibile = "nessun bot" | ROSSO 3 |
| M9 | copertura appesa non vista | ROSSO 1 |
| M10 | "chiusa" non rifiutata | ROSSO 1 |
| M11 | mercato a due esiti ignorato | ROSSO 1 |
| M12 | paginazione ignorata | ROSSO 1 |
| M13 | re-hedge senza `esposizione` | ROSSO 1 |
| M14 | `esposizione:null` instradata al ramo nuovo (parita') | ROSSO 1 |
| M15 | valore ignoto ripiega sul green-up del blotter | ROSSO 5 |
| M16 | parametri del parziale ammessi | ROSSO 6 (1 verde: `fraction 0.5` ha il suo controllo a parte) |
| M17 | verso della copertura invertito nel verdetto dei bot | ROSSO 2 |
| M18 | il ramo VECCHIO cambiato (persistenza di default PERSIST) | ROSSO 1 (parita') |
| M19 | `live` non piu' riconosciuto come app | ROSSO 2 |

19 mutazioni, 19 rosse, 0 non catturate.

### 4.2 Comandi ed esiti veri

- `python3 -m pytest Betfair/stream/tests/test_greenup_fuori_bot_2026_10_08.py -q -p no:cacheprovider`
  -> **56 passed** in 1,4 s.
- Test collegati (greenup, cash-out, follow-through, strada unica, hedging, journal, risk engine,
  minimi 02/10, audit 07, reconcile): `... test_live_order_greenup.py test_cashout_complete_ft.py
  test_cashout_pro_2026_09_10.py test_contratto_strada_unica_2026_09_25.py test_hedging.py
  test_live_journal.py test_risk_engine_worker.py test_runner_minimi_correzioni_2026_10_02.py
  test_audit_fixes_2026_07.py test_reconcile_worker.py` -> **367 passed** in 36 s.
- Suite intera `python3 -m pytest Betfair/ -q -p no:cacheprovider` -> **2 failed, 10813 passed, 87
  skipped, 6 xfailed** in 596 s (macchina con load average 24-27 su 4 CPU condivise). I 2 rossi sono
  test di LATENZA con soglia 20 ms (`test_auto_follow_2026_09_25.py::test_latenza_logica_aggancio_
  sotto_i_20_ms`, `test_motore_ordini_2026_09_24.py::test_latenza_logica_comando_place_sotto_20_ms`):
  rilanciati alternando il worker di b5547eb e il nuovo (script `strumenti/latenza_head.py`, 4 giri ciascuno):
  HEAD 2F/1F/1F/2F, NUOVO 1F/2F/2F/1F -> stesso comportamento, dovuto al carico. Da rilanciare sul PC.
- Replay PRIMA/DOPO: vedi par. 5.

## 5. Banco

- Scenario del banco per gli ordini manuali del runner / ordini del sito: **non esiste** (⊘). Causa: il
  banco non ha un CONTO con ordini esterni e gira su client simulati; il ramo nuovo e' solo LIVE e
  rifiuta per costruzione un client simulato. Coperto da test con oggetti veri (par. 4).
- Non regressione del `_dispatch` del runner sul banco: replay di Omega sul trasporto `canale` (porta
  vera -> motore ordini -> `live_order_worker._dispatch`), `35760084`, `--worker 1`, PRIMA (worker di
  b5547eb) e DOPO: risultati in `AUDIT_2026-10-08/W2_CHIUSURA_ORDINI_SITO/` (vedi par. 5.1).

### 5.1 Esito del replay PRIMA/DOPO

Script `AUDIT_2026-10-08/W2_CHIUSURA_ORDINI_SITO/strumenti/replay_prima_dopo.py` / `replay_mike.py`: decomprime `registrazioni_banco/35760084`
in `_live_raw/` (ignorato da git), mette nel worktree il worker di b5547eb (`git show`), lancia, rimette
il worker nuovo e ne verifica lo sha256 (6b856a3e...700e, identico).

| comando | PRIMA (b5547eb) | DOPO | diff dei referti |
|---|---|---|---|
| `python -m Betfair.stream.backtest.certifica omega 35760084 --trasporto canale --worker 1` | OK, 0 violazioni, 438 decisioni, 0 ordini; 58,1 s | identico; 50,8 s | solo le 2 righe dei tempi (`diff_omega.txt`) |
| `python -m Betfair.stream.backtest.certifica mike 35760084 --trasporto canale --worker 1` | OK, 0 violazioni, 5879 decisioni, 6 azioni, 5 ordini reali sul canale -> `_dispatch`, 10 stati; 93,3 s | identico; 97,5 s | solo le 2 righe dei tempi (`diff_mike.txt`) |

File: `AUDIT_2026-10-08/W2_CHIUSURA_ORDINI_SITO/{omega,mike}_canale_{prima,dopo}.{txt,err}`, `diff_*.txt`.
Tempi misurati con load average 25-28 su 4 CPU condivise (altri cantieri in parallelo): la differenza
di tempo e' rumore della macchina, non del codice (il ramo nuovo non e' eseguito dai bot). Omega sullo
scenario base non piazza: prova debole per Omega, quella forte e' Mike (5 ordini). Il `greenup` dei
bot non e' stato sollecitato da questi replay (nessuna uscita via `greenup` nello scenario base): la
parita' del `greenup` e' provata dal differenziale di 51 scenari (par. 4.6).

## 6. Parita' paper/live

Il ramo nuovo e' SOLO live per contratto (il sito non esiste in prova): in paper la riga e' rifiutata
con motivo esplicito, prima di qualunque lettura. Tutto il resto (green-up di sempre, paper e live) e'
identico a prima (parita' byte per byte, par. 4.6). Nessun ramo paper nuovo.

## 7. Cosa NON ho fatto / NON ho potuto verificare

- Nessuna chiamata vera a `listCurrentOrders`: la forma della risposta e' quella della libreria
  (`CurrentOrders`/`CurrentOrder` veri) e della documentazione; il comportamento di Betfair su un conto
  vero (es. ordini del sito senza `customerStrategyRef`) e' quello gia' osservato e scritto nel repo
  (`reconcile_worker._account_order_row`, `esiti_ordini_canale`), non riverificato qui.
- Nessuna lettura del DB vero: le colonne usate (`bet_id`, `mode`, `source`, `client_ref`, `params`)
  sono quelle delle migrazioni e delle letture gia' esistenti (`reconcile_worker._proprietari`,
  `_check_manual_followthrough`).
- Il ramo e' servito dalla CODA DB (`betfair_live_order_requests`, come da contratto). Dal canale
  locale con il motore ordini le letture DB nel percorso dell'ordine sono vietate (`_SbDifferito`
  solleva `LetturaNelPercorsoOrdine`): la riga verrebbe rifiutata con "conto non leggibile". Il W1 deve
  usare la coda (il contratto lo dice gia').
- Latenza: il comando aggiunge al percorso UNA chiamata REST (listCurrentOrders) e 5 select per blocco
  di 100 bet_id, dentro `LUCCHETTO_ORDINI` (gli altri thread ordini aspettano quella durata). Non
  misurata contro Betfair vero.
- Le punte (BACK) di copertura da 1,00 in su sono arrotondate PER DIFETTO al multiplo di 0,50 (regola
  dell'utente del 04/10, `build_order`, gia' valida per ogni green-up): coprendo un LAY del sito resta
  un residuo fino a 0,49 di size non coperto, dichiarato nel log di `build_order` ma NON nell'esito.
  Le LAY sono al centesimo.
- Tennis: fuori per decisione dell'utente.
- Il frontend (W1) non e' toccato: il contratto e' quello del coordinatore.

## 8. Decisioni per l'utente

1. **I verdetti "chiusa/ridotta dall'utente" di Mike, Omega e Safe contano in SIZE** (W3:
   `mike/service.py::_verdetto_di_conto`, `omega_service.py::sorveglia_posizione_di_conto`,
   `safe_strategy/bot_service.py::_sorveglia_posizione_di_conto`). Un green-up dell'utente su un suo
   ordine (dal sito, dall'app, o ora dalla pagina) sulla STESSA selezione di un bot, con il prezzo
   mosso, fa dire al bot "ridotta" (falso, solo una dichiarazione critica) e, se la posizione
   dell'utente e' molto piu' grande di quella del bot e il prezzo e' sceso molto, "chiusa" (falso, e
   il bot smette di proteggere). Proposta per W3: verdetto in esposizione (W/L, soldi) invece che in
   size, oppure escludere dall'"altrui" un gruppo di ordini dell'utente piatto in soldi. Nel frattempo
   questo worker RIFIUTA la copertura che produrrebbe "chiusa" e DICHIARA nell'esito quella che produce
   "ridotta". Se l'utente preferisce che la copertura parta comunque anche nel caso "chiusa", e' una
   riga da togliere (M10).
2. **Copertura di un ordine del sito che era a sua volta la chiusura di un bot**: se l'utente ha
   chiuso dal sito la posizione di un bot e poi chiede "chiudi" su quell'ordine del sito, la copertura
   riapre l'esposizione di conto (fa esattamente cio' che chiede: neutralizza il suo ordine). La riga
   `mike_trades role='utente'` (scritta al regolamento) lo esclude solo dopo il regolamento. Da
   decidere se la pagina deve avvisare.
3. **Ordine dell'app non abbinato sul lato della copertura**: rifiuto (per non avere due coperture
   vive). Se l'utente tiene un take-profit appeso dall'app sulla stessa selezione, deve annullarlo
   prima. Alternativa: annullarlo in automatico (come `cancel_unmatched`), oggi NON fatto.

## 9. Da controllare dal vivo (LIVE, primo uso dalla pagina)

- Un ordine del sito su una selezione calcio seguita: "chiudi" -> riga di coda `done` con
  `result.esposizione='fuori_bot'`, `result.conto.fuori_bot` = il bet_id del sito, `result.conto.bot`
  = gli ordini dei bot presenti; ordine LAY/BACK con `customerStrategyRef` 'live' sul conto; dopo
  l'abbinamento, il P&L della selezione uguale su entrambi gli esiti (pagina Betfair).
- Secondo "chiudi" sulla stessa selezione: `done` con "gia' piatta", nessun ordine.
- Log del runner: nessun `[live-order] richiesta ... fallita` per la riga; tempo fra `requested_at` e
  `processed_at` della riga (contiene la REST).

## 10. Blocco per la cronostoria

> **W2 (08/10, delegato, worktree agent-a1c21d4fd7008caf6, non committato)** - Chiusura dall'app degli
> ordini fatti sul sito: `greenup` con `params.esposizione='fuori_bot'` = green-up pieno
> dell'esposizione abbinata FUORI BOT letta dal conto (`listCurrentOrders` del mercato), bot
> riconosciuti con le regole esistenti (strategia, ref, tabelle dei bot, specchio, riga di coda), solo
> LIVE, rifiuti espliciti, idempotente (rilettura), follow-through coerente. Senza `esposizione` il
> green-up e' quello di b5547eb (51 scenari, 0 diversi). File: `live_order_worker.py` (+294/-0),
> `trading/esposizione_fuori_bot.py` (nuovo), test nuovo (56 casi, 19 mutazioni tutte rosse), dati di
> parita'. Suite Betfair: 10813 passati, 2 rossi di latenza <20 ms identici su b5547eb (carico).
> Replay prima/dopo (omega e mike, trasporto canale, 35760084, --worker 1): referti identici tolti i tempi.
> REPERTO per W3: verdetti di conto dei bot in size -> "ridotta"/"chiusa" falsi dopo un green-up
> dell'utente a prezzo mosso; il worker rifiuta il caso "chiusa" e dichiara il "ridotta".
> Ripresa: il coordinatore rilegge il diff, rilancia test e replay, integra con W1 (frontend).

## Verifica del coordinatore cloud (08/10)
- Diff riletto: solo aggiunte in `live_order_worker.py`; senza `params.esposizione` il `_do_greenup` di sempre (ramo non toccato).
- Test rilanciati nel checkout integrato: file nuovo + `test_live_order_greenup.py` + `test_greenup.py` + `test_cashout_complete_ft.py` verdi.
- MIE MUTAZIONI (rosse = rilevate): M1 tabelle dei bot ignorate nella classificazione -> 1 rosso; M2 prova ammessa -> 1 rosso;
  M3 ramo nuovo mai chiamato -> 43 rossi; M4 ordini dei bot coperti come fuori bot -> 13 rossi; M5 mercato a due esiti ignorato -> 1 rosso.
  Ripristino verificato con sha256 (6b856a3e8321bdcd prima e dopo).
- Reperto «verdetti a size» (punto aperto 1) girato al cantiere W3a. Dopo W3a il controllo `effetto_sui_bot` resta prudente
  (puo' rifiutare una copertura che il verdetto nuovo accetterebbe): da riallineare se W3a cambia l'aritmetica.
