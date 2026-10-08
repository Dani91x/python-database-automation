# D-2 - Place-and-trim: un rimpiazzo rifiutato non e' piu' una chiusura completa

Delegato Opus, 08/10/2026 sera. Worktree `C:\Users\Admin\Desktop\PYTHON DATABASE\wt-d2`, ramo
`cantiere-d2` da master `d257abea`. Niente commit, niente `git add`, nessun push, nessun processo nuovo.

## IN TESTA: una riga fuori da `trading/submin.py` (dichiarata prima del resto)

`Betfair/stream/live_order_worker.py`: 2 righe in `_submin_state_to_dict` e 2 in `_submin_state_from_dict`
(persistenza del nuovo campo `giri_senza_sostituto`, default 0). Senza, la coda `place_submin` e il
motore ordini (Mike/Omega/Safe passano da `_advance_submin_row`, che RILEGGE lo stato dal dizionario a ogni
giro) non conterebbero mai il secondo giro: la sequenza aspetterebbe fino al timeout del motore invece di
chiudersi con la riga giusta. Nessuna decisione di strategia, nessun altro chiamante toccato: scalper,
sniper, scalper tennis e uscite esatte rifanno gia' la chiusura dopo un ABORTED (stessa strada del
«parcheggio non piu' vivo»).

## 1. Esito in una riga

`advance_submin` passa REPRICED -> DONE solo se il SOSTITUTO del replace e' nato; replace in volo -> attesa;
replace eseguito senza sostituto -> conferma al giro dopo, poi ABORTED «rimpiazzo NON nato (replaceOrders
rifiutato; codice non restituito)». Sulla traccia del cloud il «submin completato» falso sparisce e al suo
posto c'e' l'abort, 1,1 s dopo il replace; ordini del bot IDENTICI (impronta `3fe97f9be154db71` su 30).
`rifiuti-betfair-codici` resta **KO RC3 x1**: RC3 pretende il codice `BET_TAKEN_OR_LAPSED` nell'attivita',
e quel codice non arriva a nessuno (flumine lo scarta); vedi sez. 5 e decisione D-2a.

**AGGIORNAMENTO (seconda consegna, ordine del coordinatore): D-2a e D-2b fatti, sez. 1bis.** Con D-2a
`rifiuti-betfair-codici` e' **OK** (132 azioni, ordini identici). Le sez. 2-7 sotto sono la prima consegna:
i numeri validi dopo la seconda sono quelli della sez. 1bis.

## 1bis. Seconda consegna: D-2b (tetto del replace in volo) e D-2a (RC3 del banco)

### File e righe (diff totale contro `d257abea`: 3 file, +136 / -2)
- `Betfair/stream/trading/submin.py` (+119 in tutto):
  - 113-119 `_REPLACE_IN_VOLO_TIMEOUT_MS = 15_000` (commento: replaceOrders e' REST e risponde in ben meno
    di 15 s, bet delay compreso; 15 s = `_TRIM_TIMEOUT_MS`; oltre = pacchetto perso da flumine);
  - 145-148 campo `SubminState.replace_in_volo_ms: int = 0` (prima osservazione del replace in volo);
  - 1222-1251 ramo «in volo» di REPRICED: orologio come lo step2 (`now_ms`, altrimenti `time.time()`,
    nel replay dello scalper = orologio di mercato); prima osservazione -> registra l'istante; sotto il tetto
    -> attesa; al tetto -> ritiro BEST EFFORT di ogni ordine della sequenza vivo o in volo con residuo
    (`ops.cancel(market, o, None)` in `try/except`: flumine rifiuta il cancel di un REPLACING con
    `OrderUpdateError`, l'abort non si perde), poi ABORTED con nota
    «rimpiazzo in volo da N ms senza esito; sequenza chiusa, la chiusura si rifa'».
  - Percorso A e `order=None`: invariati (il ramo sta dentro `if state.serve_replace and order is not None`).
- `Betfair/stream/live_order_worker.py` (+6 in tutto): 3257 e 3280, persistenza di `replace_in_volo_ms`
  (default 0) accanto a `giri_senza_sostituto`.
- `Betfair/stream/backtest/scavalco_rifiuti.py` (+12 / -2, SOLO BANCO, D-2a opzione 1): 60-63 docstring di
  RC3; 76 `from ..trading.submin import NOTA_RIMPIAZZO_NON_NATO` (fonte unica del testo); 854-861 in
  `_giudica_rifiuti`: testi ammessi = il codice; SOLO se `operazione == "replaceOrders"` anche la riga
  `NOTA_RIMPIAZZO_NON_NATO`. Place e cancel: come prima.
- Test: `Betfair/stream/tests/test_submin_rimpiazzo_non_nato_2026_10_08.py`, ora 42 test (+17):
  - D-2b: `test_tetto_in_volo_vale_quanto_il_tetto_del_trim`; (a) `test_in_volo_sotto_il_tetto_attesa` x2
    (14 999 ms: attesa, nessun cancel); (b) `test_in_volo_oltre_il_tetto_abort_e_ritiro` x2 (15 000 ms:
    ABORTED, nota esatta, un cancel sul parcheggio) e `..._cancel_rifiutato_da_flumine_abort_comunque`
    (cancel che solleva col metodo vero `BetfairOrder.cancel` su REPLACING: abort comunque); (c)
    `test_sostituto_nato_prima_del_tetto_done` x2; `test_tetto_in_volo_persistito_fra_i_giri_coda_e_motore`;
    `test_parita_bot_tetto_in_volo` per scalper, sniper, scalper tennis (`time.time` dei bot = orologio
    finto: 14 s attesa, 15 s `submin_abort` con la nota); `test_worker_sincrono_timeout_piu_stretto_esito_di_prima`
    (vedi sotto); `test_conteggio_azzerato...` esteso al caso con attesa gia' iniziata.
  - D-2a: `test_rc3_replace_con_la_riga_rimpiazzo_non_nato_ok`; `test_rc3_replace_senza_la_riga_resta_ko`
    x2 (riga assente; riga «submin completato» di prima); `test_rc3_place_la_riga_del_replace_non_basta`
    (placeOrders con la sola riga del replace -> KO come prima; col codice -> OK). Il banco e' il `_Banco`
    dei test del cantiere 9 (importato, non copiato).

**Worker e motore.** Il worker sincrono (`_place_sub_minimum`) e il motore (`avanza_submin`) hanno il loro
tetto `_submin_timeout_sec()` = 20 s (env `BETFAIR_SUBMIN_TIMEOUT_SEC`) contato dall'INIZIO della sequenza:
dato che il replace arriva dopo parcheggio e taglio, in pratica il loro tetto scade prima dei nostri 15 s dal
replace (non sempre: se parcheggio e taglio durano meno di 5 s il nostro scade prima, con ABORTED e la
nota nuova invece del «timeout della sequenza place-and-trim»; esito per i soldi uguale: sequenza chiusa,
ritiro, errore esplicito). Il test prova che con il loro tetto piu' stretto l'esito e' identico a prima
(«timeout della sequenza place-and-trim», nessuna riga nuova).

### Mutazioni (tutte rosse, ripristino sha256 identico; `replay/mutazioni_d2b_d2a.txt`, `replay/mut_d2b.py`;
le 12 della prima consegna rilanciate sul codice nuovo: `replay/mutazioni_d2_rilancio.txt`, 12/12 rosse)

| mutazione | rossi |
|---|---|
| B1 nessun tetto | 8 |
| B2 tetto 20 s invece di 15 | 7 |
| B3 abort subito col replace in volo | 10 |
| B4 prima osservazione non registrata | 18 |
| B5 ordine in volo non ritirato allo scadere | 3 |
| B6 errore del cancel non assorbito | 1 |
| B7 worker: inizio attesa non persistito | 1 |
| B8 worker: inizio attesa non riletto | 1 |
| A1 RC3: la riga del replace vale anche per place | 1 |
| A2 RC3: la riga del replace non vale | 1 |
| M1-M12 (prima consegna, rilanciate) | 29 / 10 / 13 / 2 / 4 / 2 / 1 / 1 / 4 / 1 / 1 / 11 |

(M7 alla prima rilancio sopravviveva: il test del conteggio passava dal ramo «prima osservazione»; esteso il
test al caso con attesa gia' iniziata, ora 1 rosso.)

### Replay (seconda consegna)
| comando | esito | confronto |
|---|---|---|
| `certifica scalper_calcio 35797769 --scenari rifiuti-betfair-codici,base --worker 3` (211 s) | **OK 132** / OK 44, ESITO 2 senza violazioni | `base` identico a `controllo_finale` (0 righe); `rifiuti-betfair-codici` contro la prima consegna: solo KO->OK, «scritto col codice: si'» sul rimpiazzo, righe RC3 sparite; ordini identici (impronta `3fe97f9be154db71` su 30); `replay/confronto_dopo2_scalper_con_riferimenti.txt` |
| `certifica tennis_scalper 35790089 --scenari tutti --worker 1` DOPO (277 s) e PRIMA a HEAD (200 s) | 17 OK / 17 OK | 1 riga: l'`id()` di processo nella chiave UF2 «non giudicabili»; `replay/confronto_tennis_scalper_w1_prima_dopo2.txt` |

(Il riferimento `AUDIT_2026-10-07/.../tennis_finale_tennis_scalper.txt` e' di un codice precedente: intestazione,
23 controlli contro 22, righe dei parametri; non confrontabile riga per riga, per questo il PRIMA l'ho rigirato
io a `--worker 1`.)

### Suite (seconda consegna)
- Test nuovi + cantiere 9 (`test_banco_scavalco_rifiuti_2026_10_08.py`, `test_banco_uf2_parcheggio_lay_2026_10_08.py`):
  **135 passed** (42 + 37 + 56).
- `pytest Betfair/stream/tests -n 3`: **4467 passed, 56 skipped, 0 failed** (120 s).
- In piu': `pytest Betfair/stream/tennis_live Betfair/stream/scalper Betfair/mike -n 3`: **2548 passed, 1 skipped,
  5 xfailed, 0 failed**.
- La suite intera `Betfair/` a corsa normale NON l'ho rilanciata dopo la seconda consegna (l'ultima, 11339
  passed, e' della prima).

### Non verificato (seconda consegna)
- Il ritiro allo scadere su un parcheggio ancora REPLACING in LIVE fallisce sempre: flumine rifiuta il cancel
  di un ordine REPLACING (`OrderUpdateError`), quindi la gamba resta a mercato finche' flumine non la rimette
  eseguibile o la stream non la chiude. La sequenza si chiude (non e' piu' cieca: lo scalper/sniper/tennis
  agganciano a ogni book gli ordini dei Trade gia' tracciati, quindi un sostituto nato tardi entra nella
  contabilita'), ma un ritiro vero del parcheggio REPLACING non e' possibile dal nostro codice senza toccare
  flumine. Non provato su Betfair vero.
- Nei replay tennis e Mike `time.time` e' l'orologio REALE (solo il banco dello scalper lo sostituisce con
  l'orologio di mercato): il tetto dei 15 s li' conterebbe tempo reale. Sui replay girati nessun replace e'
  restato in volo cosi' a lungo (referti identici), ma il caso non e' esercitato da un replay.
- Il tetto non e' sollecitato da nessun replay (nessun pacchetto perso nel banco): provato solo dai test.

## 2. Il diff riga per riga

`Betfair/stream/trading/submin.py` (+86 righe, nessuna tolta):

| righe (dopo) | cosa | perche' |
|---|---|---|
| 101-117 | `_STATI_IN_VOLO = ("REPLACING",)`, `_GIRI_SOSTITUTO_ASSENTE_MAX = 2`, `NOTA_RIMPIAZZO_NON_NATO` | flumine mette il parcheggio in REPLACING al `replace_order` e lo toglie solo quando esegue il pacchetto (`execute_replace`); la stream degli ordini non cambia uno stato REPLACING (`order/process.py`, `process_current_order` agisce solo su PENDING/EXECUTABLE). Due giri: in `betfairexecution.py` 178-209 il parcheggio diventa `execution_complete()` un istante PRIMA che `create_order_replacement` metta il sostituto nel Trade (stesso blocco del thread di esecuzione): una sola osservazione in quel buco non basta per dire «rifiutato». |
| 136-139 | campo `SubminState.giri_senza_sostituto: int = 0` | giri CONSECUTIVI «eseguito, senza sostituto». Default 0: uno stato persistito prima si comporta come nuovo. |
| 538-552 | `_ordini_della_sequenza(order)` | l'ordine osservato + gli ordini del suo Trade. Il worker e il motore passano il PARCHEGGIO (lo ritrovano per `bet_id`, `_find_submin_order`), scalper/sniper/tennis/uscite esatte passano l'ULTIMO del Trade: si guardano tutti e due, cosi' il comportamento e' lo stesso per ogni chiamante (senza, il worker avrebbe abortito anche i replace riusciti: mutazione M5). |
| 555-567 | `_sostituto_nato(order, state)` | nato = un ordine della sequenza alla `target_price` con stato flumine valorizzato. La simulazione di flumine, su un place fallito, lascia il sostituto nel Trade con `status=None` (`simulatedexecution.py` 136-159): non e' nato (M4). |
| 1204-1238 | ramo REPRICED | solo se `serve_replace` (percorso B) e `order` osservato. Sostituto nato -> DONE come prima (stessa nota, stessi campi). Parcheggio REPLACING -> stato invariato (azzera il conteggio se c'era). Altrimenti giro 1 -> resta REPRICED con `giri_senza_sostituto=1` e nota «step3: replace eseguito, sostituto non ancora visto (conferma al giro dopo)»; giro 2 -> se un ordine della sequenza e' ancora EXECUTABLE con residuo (replace rimesso a eseguibile da flumine, `reset_orders`) si ritira con `ops.cancel(market, o, None)`; poi ABORTED con nota `NOTA_RIMPIAZZO_NON_NATO + ": nessun ordine alla quota <q>, parcheggio annullato; sequenza chiusa, la chiusura si rifa'"`. Percorso A e `order=None`: DONE come prima. |

`Betfair/stream/live_order_worker.py` (+4): righe 3255-3256 e 3277-3278, vedi IN TESTA.

Test nuovo: `Betfair/stream/tests/test_submin_rimpiazzo_non_nato_2026_10_08.py` (25 test).

Nessuna soglia, stake, tetto, gamba o pausa cambiata. La chiusura dopo l'abort la rifanno i chiamanti con
le regole di sempre (anti-cascata 30 s inclusa: sulla traccia il nuovo tentativo parte alle 16:53:12.801,
come prima).

## 3. Prima / dopo sulla traccia del cloud (35797769, `rifiuti-betfair-codici`, sel 58805)

Tracce rifatte da me col replay vero (`replay/traccia_prima_sel58805.txt`, `replay/traccia_dopo_sel58805.txt`,
strumento `replay/traccia_d2.py` = `cantiere_9/strumenti/traccia_c9.py` col solo percorso dati assoluto).
La PRIMA e' identica a quella del cloud (`cantiere_9/traccia_codici_sel58805.txt`, id esclusi).

```
PRIMA
16:52:43.766 submin_step placed   "step1 place 1.00@1000.0 (LAPSE)"
16:52:46.050 submin_step trimmed  "step2 VERIFICATO su osservazione: residuo 0.97 <= target 0.97"
16:52:47.184 submin_step repriced "step3 replace -> 3.65"
16:52:47.184 submin_step done     "submin completato: ordine sotto-minimo a riposo alla target_price"   <- FALSO
16:52:47.549 min_bet_skip BACK 0.97
16:52:48.271 min_bet_skip BACK 0.97
DOPO
16:52:43.766 submin_step placed   (identica)
16:52:46.050 submin_step trimmed  (identica)
16:52:47.184 submin_step repriced (identica)        <- giro 1 nello stesso istante: conferma rimandata
16:52:47.549 min_bet_skip BACK 0.97
16:52:48.271 submin_step aborted  "rimpiazzo NON nato (replaceOrders rifiutato; codice non restituito): nessun ordine alla quota 3.65, parcheggio annullato"
16:52:48.271 submin_abort         "rimpiazzo NON nato (...): ...; sequenza chiusa, la chiusura si rifa'", matched 0.0
```
Da 16:52:51.373 in poi le due tracce sono identiche (min_bet_skip fino alla pausa, nuova sequenza
16:53:12.801, DONE vero 16:53:21.535 col sostituto BACK 0,97 @3,65 abbinato @4,1, `flatten_done` -0,05). Gli
ordini del blotter sono identici riga per riga (id esclusi). L'unica differenza di conteggio del referto e'
`min_bet_skip x79 -> x78`: alle 16:52:48.271 al posto del min_bet_skip c'e' l'abort.

## 4. Test e falsificazione

Test nuovi (25), oggetti VERI di flumine (`Trade`, `BetfairOrder`, `LimitOrder`, client paper): stato e
importi cambiano solo coi metodi veri, nell'ordine del codice di flumine citato in ogni esito (rifiuto
LIVE `pass # todo`, rifiuto della simulazione, `reset_orders`, successo, buco fra annullo e sostituto).
- (a) `test_replace_rifiutato_non_va_a_done` x4 (live/simulazione x parcheggio/ultimo), `..._lay`,
  `test_replace_rimesso_eseguibile_ritira_il_parcheggio_vivo` x2;
- (b) `test_replace_riuscito_done_come_prima` x2 (stato identico campo per campo a quello di prima),
  `test_sostituto_abbinato_e_completo_e_done`;
- (c) `test_in_volo_poi_assente_un_giro_poi_nato_nessun_abort` x2, `test_conteggio_azzerato_se_il_replace_torna_in_volo`;
- invarianti: `test_percorso_a_nessun_replace_done_come_prima`, `test_ordine_non_osservato_come_prima`;
- (d) parita': `test_parita_bot_replace_rifiutato` e `..._riuscito` per scalper, sniper, scalper tennis
  (il `_drive_submins` VERO di ciascuno: riga `submin_abort` con la nota nuova, nessun `done`; nel riuscito
  la sola riga `submin_step done` di sempre e il sostituto in contabilita'), `test_parita_uscite_esatte_tennis`
  (`UsciteEsatte.avanza` vero), `test_parita_worker_coda_e_motore_persistenza_fra_i_giri` (giro per giro
  attraverso `_submin_state_to_dict/_from_dict`, piu' stato vecchio senza la chiave),
  `test_parita_worker_sincrono_riuscito/_rifiutato` (`_place_sub_minimum` vero dall'INIT, `find_order` che
  ritrova il parcheggio come `_find_submin_order`).

Mutazioni (`replay/mutazioni_d2.txt`, script `replay/mut_d2.py`; ogni file ripristinato da copia e sha256
verificato IDENTICO: `submin.py` 636aee97842eb91f, `live_order_worker.py` a9ccaa319eb705a2):

| mutazione | rossi |
|---|---|
| M1 REPRICED->DONE come prima (blocco spento) | 19 |
| M2 abort alla prima osservazione | 10 |
| M3 nessuna attesa col replace in volo | 3 |
| M4 sostituto senza stato contato come nato | 2 |
| M5 solo l'ordine osservato, non il Trade | 3 |
| M6 parcheggio vivo non ritirato all'abort | 2 |
| M7 conteggio non azzerato quando torna in volo | 1 |
| M8 controllo anche sul percorso A | 1 |
| M9 testo dell'abort diverso | 4 |
| M10 worker: conteggio non persistito | 1 |
| M11 worker: conteggio non riletto | 1 |
| M12 DONE anche senza sostituto se l'osservato e' completo | 11 |

12 su 12 rosse. Nota su M1: con il codice di prima anche i test «riuscito» dei bot sono rossi, perche' la
macchina dichiarava DONE gia' col replace in volo (sostituto non ancora esistente).

## 5. Replay (punto d'ingresso unico, file in `replay/`)

| comando | PRIMA (HEAD d257abea) | DOPO | confronto |
|---|---|---|---|
| `certifica scalper_calcio 35797769 --scenari rifiuti-betfair-codici,base,ingresso-abbinato-in-parte --worker 3 --data-dir ...\_live_raw` | KO 132 (RC3 x1) / OK 44 / OK 49, 122 s | KO 132 (RC3 x1) / OK 44 / OK 49, 148 s | 1 riga: `min_bet_skip x79 -> x78` (sez. 3) |
| blocchi `base` e `ingresso-abbinato-in-parte` contro `controllo_finale/scalper/scalper_35797769_tutti.txt` | 0 righe diverse | 0 righe diverse | `confronto_scalper_con_riferimento_controllo_finale.txt` |
| `certifica tennis_scalper 35790089 --scenari tutti --worker 3 --data-dir ...\tennis_rec\20260707` | 17 OK, 93 s | 17 OK, 112 s | 1 riga: l'id di processo di un ordine nella chiave UF2 «non giudicabili» (`id()` di Python, cambia a ogni giro) |
| `certifica tennis_pro 35790089 --scenari tutti --worker 3` (uscite esatte) | 20 OK, 28 s | 20 OK, 41 s | 0 righe |
| `certifica mike 35760084 --scenari base,copertura-rifiutata,copertura-rifiutata-legacy --worker 3` (motore ordini) | 3 OK, 80 s | 3 OK, 115 s | 0 righe |

Il PRIMA l'ho girato io su questo PC con i due file riportati a HEAD (ripristino con sha256 identico).
Confronti con `python -m Betfair.stream.backtest.tools.confronta_referti` (`confronto_*_prima_dopo.txt`).

**Perche' RC3 resta KO (stessa riga, causa ora spiegata)**: RC3 cerca il testo `BET_TAKEN_OR_LAPSED`
nell'attivita' del bot. In produzione quel codice non raggiunge il nostro codice: `BetfairExecution.execute_replace`
(flumine 2.13.11, `execution/betfairexecution.py` 210-213) ha `pass  # todo` sul FAILURE del place e non
crea alcun ordine che porti la risposta; nel banco il finto lo toglie dal Trade per lo stesso motivo. Il bot
ora scrive «rimpiazzo NON nato (replaceOrders rifiutato; codice non restituito)» entro un giro: e' tutto
cio' che puo' sapere. Per diventare OK serve una delle due (decisione D-2a, non fatta: fuori perimetro):
1. banco: RC3 accetta, SOLO per `replaceOrders`, la riga `NOTA_RIMPIAZZO_NON_NATO` al posto del codice;
2. produzione: un nostro involucro di `execute_replace` che legga `place_instruction_reports.error_code`
   e lo consegni al bot (flumine non si tocca; tocca il runner, va deciso e certificato a parte).

Durate: ogni comando sotto i 10 minuti (il piu' lungo 148 s); tempi a PC carico (suite e replay in
sequenza).

## 6. Suite

- `python -m pytest Betfair/ -q -p no:cacheprovider` (corsa normale, DOPO, file `replay/pytest_betfair_dopo.txt`):
  **11339 passed, 71 skipped, 6 xfailed, 0 failed** in 706 s (14 avvisi preesistenti).
- Prima della scrittura dei test nuovi, stessa suite con `-n 3`: 11314 passed, 71 skipped, 6 xfailed.
- Test nuovi da soli: 25 passed.

## 7. Cosa NON ho verificato

- **Betfair vero**: nessun `replaceOrders` rifiutato dal vivo; la forma del rifiuto e' quella del codice di
  flumine 2.13.11 letto riga per riga, non osservata sul conto.
- **Thread veri**: il buco fra `execution_complete()` e `create_order_replacement` e' coperto da un test che lo
  riproduce in sequenza, non da una corsa concorrente reale. La conferma e' per GIRI (deterministica nei
  replay), non per tempo: due chiamate nello stesso buco di microsecondi darebbero un abort falso (la
  chiusura si rifarebbe su una posizione che il sostituto sta chiudendo); lo ritengo trascurabile ma non
  l'ho misurato.
- **Replace in volo per sempre**: se flumine perde il pacchetto («Execution unknown error», nessun reset)
  il parcheggio resta REPLACING e la sequenza aspetta senza limite (prima: DONE falso). Nel worker sincrono
  e nel motore c'e' il timeout della sequenza; nello scalper/sniper/tennis no (lo slot resta con la
  sequenza in corso). Nessun timeout aggiunto: cambierebbe una condotta, decisione dell'utente.
- **`order=None` in REPRICED** e **percorso A**: DONE come prima, per scelta di modifica minima.
- Lo scenario Mike `copertura-rifiutata-legacy` e i replay tennis sono identici, ma i referti non dicono se
  attraversano il ramo del rimpiazzo rifiutato: per il motore e le uscite esatte la prova e' nei test.
- Sniper e worker sincrono: nessun replay che li porti a un rimpiazzo rifiutato (solo test).
- Laboratorio (`laboratorio/scalper_lab`): usa la stessa macchina, non verificato (non e' produzione).
- Frontend, DB: non toccati.

## 8. Blocco per `CRONOSTORIA.md`

```
### 08/10 sera - D-2 place-and-trim: rimpiazzo rifiutato non e' piu' "completato" - delegato Opus (worktree wt-d2, ramo cantiere-d2 da d257abea)
- trading/submin.py: REPRICED -> DONE solo col SOSTITUTO nato (ordine della sequenza alla target_price con stato
  flumine); parcheggio REPLACING -> attesa; replace eseguito senza sostituto -> conferma al giro dopo, poi ABORTED
  "rimpiazzo NON nato (replaceOrders rifiutato; codice non restituito)", parcheggio ancora vivo ritirato; percorso
  A e order=None invariati. Campo nuovo SubminState.giri_senza_sostituto (default 0).
- live_order_worker.py: +4 righe, persistenza del campo (coda place_submin e motore ordini). Nessun'altra riga
  nei chiamanti, nessuna decisione di strategia.
- Test nuovo test_submin_rimpiazzo_non_nato_2026_10_08.py (25, oggetti veri di flumine; parita' scalper, sniper,
  scalper tennis, uscite esatte, worker coda/motore, worker sincrono). Mutazioni 12/12 rosse, ripristino sha256
  identico.
- Replay PRIMA/DOPO sul PC: scalper 35797769 (rifiuti-betfair-codici, base, ingresso-abbinato-in-parte) identici
  salvo min_bet_skip 79->78 (l'abort al posto di uno skip, 16:52:48.271); base e ingresso identici a
  controllo_finale; ordini identici (impronta 3fe97f9be154db71). tennis_scalper tutti 17 OK identico (salvo un id
  di processo), tennis_pro tutti 20 OK identico, mike base+coperture-rifiutate 3 OK identico.
- (prima consegna) rifiuti-betfair-codici restava KO RC3 x1: il codice BET_TAKEN_OR_LAPSED non arriva a nessuno (flumine
  execute_replace "pass # todo"). Decisione D-2a aperta: RC3 accetta la riga "codice non restituito" per
  replaceOrders, oppure involucro nostro di execute_replace che consegni il codice.
- Suite Betfair/ corsa normale: 11339 passed, 71 skipped, 6 xfailed, 0 failed (706 s).
- SECONDA CONSEGNA (ordine del coordinatore): D-2b tetto del replace in volo _REPLACE_IN_VOLO_TIMEOUT_MS = 15 s
  (come il trim): allo scadere ritiro best effort (flumine rifiuta il cancel di un REPLACING: l'abort resta) e
  ABORTED "rimpiazzo in volo da N ms senza esito; sequenza chiusa, la chiusura si rifa'"; campo
  replace_in_volo_ms persistito dal worker. D-2a SOLO BANCO: RC3 accetta per replaceOrders la riga
  NOTA_RIMPIAZZO_NON_NATO (place/cancel come prima). Test 42 nel file nuovo; mutazioni B1-B8, A1-A2 10/10
  rosse, M1-M12 rilanciate 12/12 rosse. Replay: scalper 35797769 rifiuti-betfair-codici OK 132 (era KO RC3),
  base OK 44 identico al controllo finale; tennis_scalper 35790089 tutti --worker 1 17 OK, identico al PRIMA
  salvo un id() di processo. Suite: Betfair/stream/tests -n 3 4467 passed; tennis_live+scalper+mike -n 3 2548
  passed; nuovi+cantiere 9 135 passed. Limite: un parcheggio REPLACING non si puo' ritirare da flumine.
- Referto: AUDIT_2026-10-08/decisioni_sera/D2_SUBMIN_REPLACE_RIFIUTATO.md
```
