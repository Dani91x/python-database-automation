# CANTIERE D1-bis (28/09/2026) - MIKE: freno delle coperture sulla strada del runner

Worktree `agent-af0e83caa1c852875`, base `03e484d` (identica a `origin/master` 8c3ce13 sui file
toccati). Lavoro NON committato. Replay del banco NON lanciato (lo rilancia il coordinatore).

## 0. In cima: cosa conta per i soldi

1. **Freno delle coperture (punto 1)**: CONFERMATA la causa radice del coordinatore, CORRETTA.
2. **Freno unico R3 sulla strada del runner (punto 4) - DIFETTO TROVATO E CORRETTO**: da D1
   un'APERTURA paper di Mike a freno tirato NON veniva fermata nel processo di Mike:
   `execution.place` manda il comando al canale (`execution.py:684-690`) PRIMA del punto in cui
   applica il freno paper (`execution.py:744`). La fermava solo il motore del runner
   (`motore_ordini.py:943-948`, `M_KILL`). La CHIUSURA a freno tirato passa davvero (verificato,
   non era un difetto: i 4 test erano rossi per la preparazione, senza runner installato).
3. **Divergenza paper/live sulla copertura SOTTO MINIMO (non corretta, fuori perimetro, decisione
   del coordinatore)**: in LIVE Mike passa da `place_submin_live(fill_or_kill=True)`
   (`omega_market.py:918`), che con FOK rifiuta SEMPRE una copertura sotto 2,00 EUR senza ordini
   (`SUBMIN_NESSUNA_CONTROPARTE`, `omega_market.py:987-991`; quota abbinabile -> percorso B vietato
   di default -> `SUBMIN_PIANO_RIFIUTATO`, `:981-983`). In PAPER sul canale `execution` manda
   `time_in_force=None` sotto il minimo (`execution.py:485`) e il motore esegue il place-and-trim
   VERO del worker: parcheggio 2,00 EUR alla quota target, taglio, residuo a riposo. Nel replay del
   coordinatore la riga 6 del canale e' una copertura APERTA da 2,00 @ 2,6 che il live non avrebbe
   mai avuto. E' lo stesso difetto C-1 del 13/09 descritto in `omega_market.py:932-937`, rinato in
   paper. Proposta in §7.
4. **Eccezione del motore (punto 3)**: analisi in §4.3; possibile ordine ORFANO sul runner e gamba
   di Mike data per annullata su un esito ignoto (J4). Nel motore e in Mike (fase `errore`): non
   corretto, proposta con file:riga.

## 1. Cause radice

### 1.1 Freno coperture (punto 1)
- Il conteggio `E.registra_rifiuto_copertura` stava SOLO nel ramo sincrono di
  `service.execute_place` (prima: `service.py:896-926` su master). Il ramo asincrono di D1
  `_segui_ordini_paper_su_runner` (master `service.py:1404-1426`), su «terminale senza abbinato»,
  chiamava solo `_rifiutata` e scriveva `no_fill`: il freno non poteva scattare in paper. Il
  motore ripropone la copertura (S3 x4, S1 x0 nel referto del coordinatore).
- Il ramo sincrono in paper NON arriva mai al conteggio: dopo l'attesa dell'esito
  (`service.py:815-830` master) chiama `_segui_ordini_paper_su_runner` e ritorna `cancelled`.
  Quindi il conteggio del paper doveva stare nel lettore degli esiti.
- **Il codice d'errore (INVALID_BET_SIZE) non esiste sulla strada del canale, e non si perde in
  Mike**:
  a) nel banco il rifiuto provocato vive SOLO nel finto REST: `banco_comune.py:528-562`
     (`MercatoFlumine.place_order_live`), armato da `replay_registrazioni.py:854-863` su
     `strategia.mercato`. Sul canale il motore piazza direttamente su flumine
     (`motore_ordini.py:1047-1048`, `LOW._dispatch`): il guasto non si applica mai. Le coperture
     del canale sono morte per il matching di flumine (`runner_annullato` x3 = FOK/residuo
     annullato, `runner_scaduto` x1 = LAPSE), non per un rifiuto con codice;
  b) anche se ci fosse, l'evento `order` NON porta un codice: chiavi = `CHIAVI_SPECCHIO`
     (`motore_ordini.py:141-147`) + `ref/seq/fase/esito_ms`; `riga_specchio_da_esito`
     (`:511-541`) non copia `result["error"]`; `fase_da_riga` (`:482-508`) guarda solo stato e
     numeri; flumine tiene l'`error_code` della risposta simulata nell'ordine
     (`simulatedorder.py:84-88,145-149`), non nella riga dello specchio.
  Quindi il ramo asincrono passa `error_code=None` (nessun campo inventato, catalogo n.3) e come
  motivo `runner_<fase>`, lo stesso scritto sulla riga. E' l'analogo esatto del sincrono: per un
  FOK senza controparte il live passa `error_code=None` e `motivo=live_not_matched:EXPIRED`
  (`execution.py:865-871`), stabile fra un tentativo e l'altro. `annullato` (FOK ucciso,
  `size_cancelled`) e `scaduto` (LAPSE / `BET_TAKEN_OR_LAPSED`, `size_lapsed`) restano codici
  diversi, come in live `live_not_matched:EXPIRED` e `...:EXPIRED:<codice>`.
  Proposte (NON fatte, fuori perimetro): P1 `motore_ordini.py` - aggiungere all'evento `order` un
  `error_code` (da `result.get("error")` e da `order.responses.place_response.error_code`);
  P2 `banco_comune.py:528` / `porta_banco.py` - applicare `place_rifiuto`/`rifiuta_sotto_minimo`
  anche sul trasporto canale (prima di `LOW._dispatch`), altrimenti lo scenario
  `copertura-rifiutata` confronta un rifiuto (coda) con un matching di flumine (canale).
- **Il LIVE non ha il difetto**: la copertura e' un taker BACK (`engine.py:3344`), mai appoggiata
  (`_is_resting_leg` solo lay `*_green`), quindi `_segui_resting_live` non la tocca; in live
  l'esito della copertura e' sempre sincrono (REST) ed e' contato. Resta un caso di bordo
  dichiarato: esito IGNOTO in live (eccezione al place) -> `_reconcile_unknown` -> `free`
  (`reconciled_not_placed`) NON conta, per regola scritta di `registra_rifiuto_copertura`
  («su un esito IGNOTO non si conta niente»). Idem in paper `runner_senza_esito` (60 s senza
  eventi) e fase `errore`: non contati.

### 1.2 Freno unico R3 (punto 4)
Vedi §0.2. I 4 test erano rossi perche' senza porta installata Mike paper dichiara
`paper_senza_runner` (e `_SENZA_RUNNER_LOGGATO` silenzia il secondo `skip` per 60 s: `[db]`
senza righe). Riscritta la preparazione, il test dell'apertura restava ROSSO per il difetto vero
(il comando arrivava al runner finto e si abbinava): corretto in Mike.

## 2. Cosa ho cambiato (ELENCO ESATTO)
Modificati:
- `Betfair/mike/service.py`
  - nuova `_esito_rifiuto_mercato` (`:915`): conteggio del freno SOLO per `over_cover`, riga
    `place_rifiutato` col conteggio se c'e' un codice, riga `error copertura_bloccata` allo scatto.
    Stesso testo e stesse chiavi del blocco sincrono di prima, che ora la chiama (`:907`).
  - `_segui_ordini_paper_su_runner`, terminale senza abbinato (`:1450-1484`): per un taker con
    fase `rifiutato|annullato|scaduto` e `seq > canale_seq` gia' applicato chiama la stessa
    funzione (`error_code=None`, `motivo=runner_<fase>`); il `no_fill` porta `conteggio`/`max`.
    Fase `errore` e lay appoggiate: NON contate. Nessuna soglia toccata.
  - `execute_place` (`:810-830`): freno unico sulle APERTURE paper del runner, nel punto e con
    l'esito del live (`PlaceOutcome('error', motivo)` dopo la riserva della riga); chiusure
    (`cashout`/`closes_trade_id` nel meta, stessa regola di `execution`) passano sempre.
- `Betfair/stream/tests/test_submin_contratto_chiamanti_2026_09_17.py`: UNA voce
  (`Betfair/mike/porta_ordini.py`) col suo commento, subito prima di `trading/submin.py`.
- `Betfair/stream/tests/test_r3_freno_unico_2026_09_25.py`: SOLO la preparazione dei 4 test di
  Mike (fixture `mike_strade`, `_mike`, `_ordini_partiti`); nomi e id dei test invariati;
  asserzioni non indebolite (aggiunte: nessun ordine partito, gemello LIVE nello stesso test).
Nuovi:
- `Betfair/mike/tests/test_mike_d1bis_freno_coperture_runner_2026_09_28.py` (8 test)
- `AUDIT_2026-09-28/d1bis/falsifica.py` (script di falsificazione, ripristino SHA-256)
- `AUDIT_2026-09-28/CANTIERE_D1BIS_FRENO_COPERTURE.md`, `AUDIT_2026-09-28/CANTIERE_D1BIS_su_master.patch`
NON toccati: `engine.py` (non serviva), `porta_ordini.py` (rispetta il contratto, §4.2),
`motore_ordini.py`, `porta_banco.py`, `banco_comune.py`, `execution.py`.

## 3. Test e falsificazioni
Comandi (dal worktree, `.venv` = junction):
- `python -m pytest Betfair/mike/tests/test_mike_d1bis_freno_coperture_runner_2026_09_28.py -q -p no:cacheprovider`
  PRIMA della correzione: **4 rossi, 3 verdi** (paper conteggio 0 contro live 1-2-3). DOPO: 8 verdi.
- `python -m pytest Betfair/mike/tests Betfair/stream/tests/test_submin_contratto_chiamanti_2026_09_17.py Betfair/stream/tests/test_r3_freno_unico_2026_09_25.py Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py -q -p no:cacheprovider`
  -> **1022 passati, 0 falliti**, 69 s (suite di Mike intera compresa).
- `test_r3_freno_unico_2026_09_25.py`: 25/25 (su master 4 rossi, 21 verdi).
- `test_submin_contratto_chiamanti_2026_09_17.py`: verde (su master rosso).

Falsificazioni (`python AUDIT_2026-09-28/d1bis/falsifica.py [porta|r3]`), ripristino byte-identico
(SHA-256) dopo ognuna, `grep -c MUTAZIONE` = 0 a fine giro:
| id | mutazione | esito |
|---|---|---|
| a | ramo asincrono non chiama il conteggio | ROSSO (4 test) |
| b | conta anche le gambe non `over_cover` | ROSSO (2) |
| c1 | `error_code=None` fisso nella funzione | ROSSO (1: sincrono con INVALID_BET_SIZE) |
| c2 | `error_code=None` fisso dal ramo sincrono | ROSSO (1) |
| d | stesso evento terminale contato di nuovo (tolto `seq > gia`) | ROSSO (1) |
| e | ramo sincrono non conta piu' | ROSSO (2) |
| f | motivo instabile (`runner_<fase>_<seq>`) | ROSSO (3) |
| p1 | porta di Mike forza FOK sotto il minimo | ROSSO (1) |
| p2 | porta ritocca l'importo | ROSSO (1) |
| r1 | nessun freno sulle aperture paper | ROSSO (`apertura_ferma[env]`, `[db]`) |
| r2 | freno anche sulle chiusure | ROSSO (`chiusura_passa_col_freno`) |
Nota sulla (c): sul ramo del runner `error_code` e' SEMPRE None (l'evento non lo porta), quindi
la mutazione (c) puo' essere vista solo sul ramo sincrono, che ora usa la stessa funzione.

## 4. Punti aggiunti dal coordinatore

### 4.1 Punto 1 - PARITA' coda/canale sullo scenario `copertura-rifiutata` (attesa, NON misurata)
Coda: la copertura t2 (1,26 < 2,00) -> `place_submin_live` finto -> rifiuto provocato
`CANCELLED_NOT_PLACED` -> sincrono -> conteggio 1 = `cover_rifiuti_max` (1, taratura dello
scenario) -> freno. Righe 2, ordini 2. Canale, dopo la correzione: t2 resta `pending` finche' il
runner non da' l'esito (il motore NON propone un'altra copertura con una gamba viva: motivo
«ordine a esito ignoto: nessuna apertura» x335 nel referto); all'esito terminale
`annullato|scaduto` il lettore conta -> freno scattato al primo esito -> nessuna copertura in
piu'. Righe 2, comandi 2. Le 4 righe di copertura del canale nel referto di stamattina chiudono
tutte `runner_annullato`/`runner_scaduto`, quindi anche t2. **Condizione**: se l'esito terminale
di t2 fosse `errore` (place-and-trim abbandonato, §4.3) NON si conta (esito ignoto) e la parita'
tornerebbe a mancare. Differenze di CONTENUTO che restano (non mie, dichiarate): il codice
(`CANCELLED_NOT_PLACED` coda, `runner_annullato|scaduto` canale, §1.1 P2) e `fok` True (coda:
`banco_comune.py:763-767` passa il place-and-trim al `place_order_live` con FOK di default) contro
False (canale, `execution.py:485`).

### 4.2 Punto 2 - censimento del place-and-trim (`porta_ordini.py`)
`Betfair/mike/porta_ordini.py` compare nella scansione SOLO perche' il docstring (`:71`) nomina
`place_submin_live`. Contro `INTERFACES.md` «Place-and-trim: contratto del modulo UNICO»:
- nessuna copia della sequenza: RISPETTA - nessuna chiamata a `place_submin_live`,
  `start_submin`, `advance_submin`; la macchina e' quella del worker nel motore
  (`motore_ordini.py:955-979`, `1036-1061`);
- importo e quota: RISPETTA - `adatta_comando` non tocca `size`/`price` (test p2); nessuna regola
  di passo imposta (il contratto dice «il modulo NON impone nessuna regola di passo», i minimi
  .it 2,00/0,50 li applica il nucleo);
- niente FOK sotto il minimo: RISPETTA - la porta tiene il `time_in_force` di `execution`
  (None sotto il minimo), altrimenti il motore rifiuterebbe (`motore_ordini.py:967-970`) (test p1);
- guardia cap sul parcheggio: la porta e' NEUTRA - non aggiunge ne' toglie un cap. Il comando del
  canale (`CHIAVI_COMANDO`, `safe_strategy/porta_ordini.py:107-110`) non ha `params`, quindi nel
  motore vale solo il cap globale d'ambiente (`live_order_worker.py:1208-1218`); ugualmente il REST
  di Mike non passa `max_stake` a `place_submin_live` (`execution.py:819-823`). Limite comune a
  tutti gli attori del canale, fuori dalla porta: dichiarato, non corretto.
Registrata con commento. Vedi pero' §0.3: il contratto e' rispettato, la PARITA' col live di Mike
no (decisione del FOK sotto il minimo in `execution.py:485`).

### 4.3 Punto 3 - `OrderUpdateError: Order does not currently have a betId`
- Chi: il MOTORE, `motore_ordini.py:1270-1290` (`_abbandona_submin`), sul timeout della sequenza
  (`:1226-1228`, `time.monotonic()` contro `_submin_timeout_sec()` = 20 s di tempo VERO,
  `live_order_worker.py:423-431`). `_find_submin_order` trova l'ordine flumine per id del blotter
  (`live_order_worker.py:805-811`), ma l'ordine non ha ancora `bet_id` (pacchetto ancora nella
  coda del bet delay simulato) e `order.cancel` solleva (`flumine/order/order.py:362`). Non e' Mike:
  Mike annulla solo con `bet_id` noto (`_mark_trade_cancelled`, `service.py` `sul_runner and not
  bet_id` -> `annullo_richiesto` e riconciliazione).
- Cosa resta: l'eccezione e' presa (`:1284-1285`), poi `_write_error` e `_chiudi_submin(False)`
  emettono il terminale `errore` (`:1305-1309`). Il ritiro NON e' avvenuto: quando il pacchetto
  viene eseguito, se il mercato e' OPEN nasce il parcheggio (2,00 EUR BACK alla quota target,
  percorso A) che NESSUNO segue; se e' sospeso flumine lo annulla (`ERROR_IN_ORDER`, void). Gli
  eventi successivi di quell'ordine arrivano ancora allo stesso ref (`_rif_interni`), ma la
  memoria della porta scarta ogni evento non terminale dopo un terminale
  (`safe_strategy/porta_ordini.py:431`); un terminale successivo (`abbinato`) entra, ma Mike ha
  gia' chiuso la gamba.
- La gamba di Mike: fase `errore` -> `cancelled`, riga `error runner_errore`
  (`service.py:1450-1452`), NON contata dal freno (la mia correzione la tratta da esito ignoto).
  Cioe' un esito IGNOTO dato per annullato: e' il caso che J4 vieta. Se il parcheggio si abbina,
  posizione paper da 2,00 EUR sconosciuta al bot.
- Produzione: stesso codice del motore nel runner, paper (flumine simulato, tempo vero) e live
  del canale (Safe/Omega; Mike live e' REST e non passa di qui). Serve un place che resta senza
  `bet_id` oltre 20 s (runner lento, Betfair lento, coda del bet delay): raro ma possibile. In
  PAPER di Mike oggi SI', perche' ogni copertura sotto minimo passa dal place-and-trim (§0.3).
- Proposte (NON fatte): M1 `motore_ordini.py:1276-1290` - se l'ordine non ha `bet_id` o `cancel`
  solleva, NON chiudere la sequenza: tenere lo stato con `ritiro_pendente` e ritentare il ritiro
  ad ogni `avanza_submin` finche' l'ordine non ha `bet_id` (o e' `EXECUTION_COMPLETE`), emettere
  il terminale solo a ordine confermato morto. M2 Mike `service.py:1450` - fase `errore` ->
  `E.STATUS_RECONCILE` (non `cancelled`) finche' il runner non da' un terminale definitivo, con un
  termine e l'annullo sul runner via `bet_id`; da decidere col coordinatore perche' blocca le
  aperture finche' dura. M3 (§0.3) eliminerebbe il caso per Mike alla radice.

### 4.4 Punto 4 - i 4 test del freno unico
Riscritta SOLO la preparazione: runner finto di Mike (`Betfair/mike/tests/runner_finto.py`,
protocollo vero) installato con `porta_ordini.installa`, la gamba nel `ctx` come in produzione,
e per il live un mercato REST con `place_order_live` che torna un `PlaceResult` vero; il modo
ordini (non il freno) aperto su LIVE. Ogni test prova paper E live: a freno tirato nessun
ordine parte (ne' comando al runner ne' REST), nessuna riga aperta, `skip` col motivo del freno
(`live_kill_switch_attivo`/`db_kill_switch_attivo`) identico nei due modi; la chiusura passa in
paper (comando al runner con `reduces_liability=True`) e in live; freno rilasciato: aperto in
entrambi. Falsificazioni r1/r2 ROSSE.

## 5. Parita' paper/live
- Freno coperture: stessa funzione, stessa dinamica: test di parita' (FOK senza controparte x3,
  `cover_rifiuti_max=3`): live `[(1,F),(2,F),(3,T)]`, paper identico; una sola riga
  `copertura_bloccata` per modo. Differenza residua: il codice (`live_not_matched:EXPIRED` contro
  `runner_annullato`), che conta solo per il raggruppamento.
- Freno unico: paper ora si ferma dove e come il live (riga riservata, `error` col motivo,
  `skip`); per una copertura a freno tirato il conteggio del freno copertura avviene in entrambi
  (comportamento del live gia' esistente, ora anche in paper).
- NON pari (§0.3): copertura sotto minimo = 0 ordini in live, place-and-trim vero in paper.

## 6. Cosa NON ho fatto / NON ho potuto verificare
- Replay del banco non lanciato (regola): la parita' coda/canale (§4.1) e' ragionata sul codice e
  sul referto del coordinatore, NON misurata.
- Non corretti (fuori perimetro): P1/P2 (§1.1), M1/M2 (§4.3), la divergenza del FOK sotto il
  minimo (§0.3), il cap del parcheggio assente dai comandi del canale (§4.2).
- Non verificato il contenuto della riga 6 del canale (copertura aperta 2,00 @ 2,6): lettura mia
  = parcheggio del place-and-trim abbinato prima del taglio; va confermato sul diario del motore.
- Non verificato perche' la sequenza di t5 e' arrivata al timeout (ipotesi: sospensione durante il
  bet delay simulato).
- Il freno R3 in paper legge `controls.motivo_kill_switch` (DB, cache ~2 s) a ogni apertura sul
  runner: stessa lettura del percorso paper di prima di D1, nessuna chiamata nuova.

## 7. Decisioni per il coordinatore / l'utente
- **Copertura sotto minimo in paper** (§0.3): in live non nasce mai (rifiuto certo, 0 ordini);
  in paper nasce e puo' abbinarsi. Proposta M3: per Mike (bot a taker FOK) la porta paper, o
  `execution` sul canale, deve dare lo stesso esito del live per un'apertura sotto minimo
  (rifiuto `SUBMIN_NESSUNA_CONTROPARTE`/`SUBMIN_PIANO_RIFIUTATO`, 0 ordini), non il
  place-and-trim a riposo. Non l'ho fatto: cambia il tipo d'ordine di una strada condivisa.
- Nessuna soglia di strategia toccata (`cover_rifiuti_max`, `cover_retry_min_s` invariati).

## 8. Da controllare dal vivo in PAPER
| controllo | atteso | dove |
|---|---|---|
| copertura non abbinata sul runner | `no_fill reason=runner_annullato` con `conteggio`/`max`; al terzo di fila `error copertura_bloccata` | `mike_activity` |
| freno scattato | nessuna nuova riga `over_cover` finche' «Riprendi» | `mike_trades` |
| freno unico acceso | apertura paper: riga `error` + `skip reason=db_kill_switch_attivo`, nessun comando `/comando/mike` nel log del runner | `mike_trades`, `mike_activity`, log runner |
| chiusura a freno acceso | comando al runner con `reduces_liability=true`, riga `open` | log runner, `mike_trades` |
| `place-and-trim mike-t... ritiro del residuo KO` | se compare: controllare sul runner che non resti un parcheggio da 2,00 | log runner, specchio ordini |
