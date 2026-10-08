# W3b - I BOT DENTRO FLUMINE SANNO SUBITO DEGLI ORDINI ESTERNI (scalper calcio, 4 bot tennis)

Delegato di costruzione, 08/10/2026. Worktree `agent-aa6d8083bb40b34bd`, partenza
`3b8ce19` (cima integrata `claude/blissful-sagan-hri7o6`, fast-forward). Niente commit.
File dei replay: `AUDIT_2026-10-08/W3B/`. Non dichiaro "certificato": va rieseguito e
firmato dal coordinatore.

## 0. Il fatto che cambia la premessa del brief (verificato sul codice)

Il brief dice "lo scalper gira NELLO STESSO processo del runner calcio". **Non e' cosi'.**
`Betfair/stream/scalper/scalper_service.py:1-8` e `scalper_session.py:1-14`: ogni partita
gira in un PROCESSO SEPARATO (`python -m Betfair.stream.scalper.scalper_session <evento>`)
con il SUO login Betfair e il SUO flumine (`run_session`, `framework = Flumine(client=...)`
~riga 1890; due framework nello stesso processo davano WinError 10035 il 02/07).
Conseguenze, entrambe sfruttate o dichiarate:
* LIVE: la sessione ha gia' il PROPRIO stream ordini del conto
  (`_order_client_kwargs`: `order_stream=True`, `paper_trade=False`; flumine 2.13.11
  `streams/orderstream.py`: `customer_strategy_refs=None` perche'
  `flumine/config.py:8 customer_strategy_ref = None`): riceve OGNI ordine del conto, anche
  quelli del sito e del terminale manuale, e flumine li scarta
  (`order/process.py` "Strategy not available to create order"). Monto lo STESSO
  osservatore del runner calcio (`esiti_ordini_canale.osserva_conto_su_flumine`) sul
  flumine della sessione, con una `pubblica` in memoria: nessun canale, nessuna chiamata
  Betfair in piu', nessuna lettura del topic `conto` di un altro processo.
* PAPER: il "blotter della strategia manuale del runner in prova" sta in un ALTRO processo
  (runner calcio): una lettura in-process e' impossibile. Ho scritto l'interfaccia
  (sez. 7) e NON ho inventato un canale: la sessione scalper in prova resta identica a
  oggi (gap paper/live dichiarato, decisione D5).

Il runner tennis invece ospita i 4 bot nel SUO flumine: li' live e paper sono entrambi
in-process.

## 1. Lacune verificate (al commit di partenza)

* Scalper calcio: nessuna lettura della posizione di conto
  (`grep` in `Betfair/stream/scalper`: zero usi di `esiti_ordini_canale`/`list_current_orders`
  per ordini altrui; l'unico `list_current_orders` e' `leggi_ordini_media_dal_conto`
  filtrato sul nome della propria strategia, riga ~906).
* Tennis: `tennis_runner._strategy_is_flat` (~1183) legge SOLO il blotter della strategia
  del bot; gli ordini manuali del ladder stanno sotto la capture
  (`tennis_live_order_worker._capture_strategy` ~591, `_do_place` ~713); lo dichiara
  `chiusura_manuale.py` righe 6-9. Nessun osservatore dello stream ordini nel runner tennis.

## 2. La soluzione (una sola regola, un solo modulo, nessuna copia)

**Modulo comune** `Betfair/stream/tennis_scalper/ordini_esterni.py` (NUOVO, puro, nessun
I/O; sta in `tennis_scalper` per restare nel perimetro: il coordinatore puo' spostarlo in
`trading/` cambiando solo l'import):
* `classifica` (r.156): ordine del conto (camelCase di `ordine_del_conto`) ->
  `proprio` (bet_id del blotter della strategia, prefisso `name_hash` del
  `customerOrderRef` di flumine, `customerStrategyRef` = nome[:15]) | `bot` (la regola di
  W2, RIUSATA: `trading.esposizione_fuori_bot.motivo_bot_da_riferimenti` + `prefissi_ref_bot`;
  il ref del terminale manuale dello sport - `live` calcio, `tennis` tennis - vale
  "dell'utente") | `utente` (sito: nessun riferimento; app: ref manuale).
* `Sorveglianza` (r.193): per UN bot, con la modalita' con cui ESEGUE (paper|live).
  Intervento = ordine dell'UTENTE con ABBINATO NUOVO (> 0,005) su un mercato del bot.
  Linea di base (r.232): un ordine dell'utente piazzato PRIMA dell'accensione conta solo per
  l'abbinato che cresce dopo (l'immagine iniziale dello stream non e' un intervento).
  Scatta UNA volta (`_scatta` r.292) e chiama la reazione del bot.
* `Registro` (r.339): la `pubblica` di `osserva_conto_su_flumine`; la fotografia entra nella
  `MemoriaConto` VERA (mai una piu' vecchia sopra una piu' nuova) e va SOLO alle
  sorveglianze live, che decidono nel thread di flumine, al messaggio.
* `proteggi_strategia` (r.406): involucro per ISTANZA di `check_market_book` (come
  `tennis_runner._scope_to_market`): fatto l'intervento il bot non decide piu'; in paper
  qui si legge la fonte paper a ogni book. `ferma_strategia` (r.422) e `annulla_vivi`
  (r.440, `market.cancel_order`, la via delle strategie).
* Interruttore `BOT_ORDINI_ESTERNI`: ACCESO di serie (come `MIKE_CONTO_CANALE`); `0` = tutto
  identico a prima (nessun involucro, nessun osservatore).

**Scalper calcio** (`scalper_session.py`):
* `CAUSA_INTERVENTO` in `CAUSE_ARRESTO` (r.566-571): all'uscita annullo dei vivi e
  dichiarazione della posizione che resta (CRITICAL `SCALPER_ARRESTO`), MAI chiusa.
* `installa_ordini_esterni` (r.759) e `_ordini_della_sessione` (r.742): solo LIVE e
  interruttore acceso; mercati del bot = catalogo della sessione + mercati con suoi ordini;
  reazione nel thread di flumine: tutte le strategie ferme, vivi della sessione annullati,
  attivita' `intervento_utente` nel buffer (nessun I/O nel thread di flumine).
* `run_session`: installazione dopo `add_strategy` (r.~1929); al battito (r.~2156) la
  sessione esce `stopped` con `causa_arresto = intervento_utente`, SENZA force-flat (nessuna
  copertura); marcatore `stats.intervento_utente` nella riga (r.~2350). Lo stato 'stopped'
  e' "chiusa a mano" per l'auto-mode (`auto_mode.motivo_esclusione`): mai riarmata.

**4 bot tennis** (`Betfair/stream/tennis_live/ordini_esterni_tennis.py`, NUOVO, + 5 punti
in `tennis_runner.py`):
* `registro_per_framework` (r.43): un `Registro` per framework; LIVE: osservatore montato
  sul flumine del runner tennis (`tennis_runner.py` ~3301, dopo `_attiva_saldo_su_evento`).
* `proteggi_bot` (r.106): una sorveglianza per bot ospitato (build ~3357 e armamento a caldo
  ~2739), modalita' dalla funzione della UI (`tennis_live_order_worker._modo_strategia`),
  mercato = `_tennis_scoped_market_id`; bot in dry-run o modalita' OFF: nessuna sorveglianza.
  Reazione nel thread di flumine: annullo dei vivi del bot + `_disable_strategy` VERO.
* `FontePaperManuali` (r.59): gli ordini MANUALI simulati del ladder
  (`session.tracked_orders`, `source='manual'`, `mode='paper'`, quel mercato), ricordati
  anche dopo che il worker li toglie dal tracking (terminali).
* `concludi_interventi` (r.168), chiamato dal `bot_control_worker` (~1766) PRIMA
  dell'heartbeat: riga `stopped` con `stats.chiusura_manuale = {come: intervento_utente,...}`
  (il marcatore che il ponte legge per NON riarmare: `chiusura_manuale.chiusi_dall_utente`),
  `stats.intervento_utente`, attivita' `intervento_utente`.
* `TennisLiveSession.__init__` (~607): `ordini_esterni`, `interventi_esterni`.

**Banco** (additivo, `Betfair/stream/backtest/` + replay dello scalper):
* `backtest/ordini_esterni_banco.py` (NUOVO): scenari `ordine-esterno` e
  `ordine-esterno-altro-mercato`, controlli OE1-OE5 (testo nel modulo). L'ordine
  dell'utente e' VERO su flumine (BACK 2,00 a 1,01 taker, senza riferimenti = dal sito); lo
  stream ordini e' prodotto con la cache VERA (`OrderBookCache`) dagli ordini del mercato
  (`banco_comune.MercatoFlumine.ordini_conto_come_stream`, riusata) e dal produttore VERO
  (`pubblica_conto_da_evento`), serializzato JSON come il canale, consegnato a
  `Registro.ricevi_conto` della sessione a ogni cambio degli ordini di un suo mercato.
  Il caso duro si PROVOCA: l'ordine dell'utente parte appena la sessione ha un ordine VIVO
  (l'annullo si esercita), altrimenti a meta' finestra, al piu' tardi all'ultimo istante.
* `scalper/tools/replay_registrazioni.py`: scenari descritti, attributo `esterni_banco`
  (None fuori dagli scenari nuovi: nessun lavoro in piu'), aggancio dopo ogni book,
  `_istanti_evento` estratta da `_evento_scenario` SENZA cambiarne i numeri, referto OE.
  Credenze di una strategia FERMATA dall'intervento non giudicate dalla famiglia K (il bot
  non governa piu' niente; al loro posto OE3/OE4; S3 resta): scritto nel codice e qui.
* `backtest/applica_bot.py`: i due scenari fra gli scartati (gesto dell'utente).
* `backtest/registro_bot.py`: `ordini_esterni` nell'impronta dello scalper e dei tennis,
  `ordini_esterni_tennis` in quella dei tennis (test di contratto dell'impronta).
* `tests/test_contratto_strada_unica_2026_09_25.py`: `ordini_esterni_banco.py` fra i
  chiamanti autorizzati (strada BANCO, col motivo: l'ordine dell'utente non blocca il motore).

**Elenco esatto dei file.** Modificati: `Betfair/stream/scalper/scalper_session.py`,
`Betfair/stream/tennis_live/tennis_runner.py`,
`Betfair/stream/scalper/tools/replay_registrazioni.py`,
`Betfair/stream/backtest/applica_bot.py`, `Betfair/stream/backtest/registro_bot.py`,
`Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py`. Nuovi:
`Betfair/stream/tennis_scalper/ordini_esterni.py`,
`Betfair/stream/tennis_live/ordini_esterni_tennis.py`,
`Betfair/stream/backtest/ordini_esterni_banco.py`, i due file di test, questo referto e
`AUDIT_2026-10-08/W3B/` (replay, diff, falsificazioni, script). NON toccati:
`esiti_ordini_canale.py`, Mike/Omega/Safe, `live_order_worker.py`, frontend. `_live_raw/`
decompresso nel worktree (ignorato da git).

## 3. Test (comandi ed esiti VERI)

Nuovi: `Betfair/stream/tests/test_w3b_ordini_esterni_scalper_2026_10_08.py` (24),
`Betfair/stream/tennis_live/tests/test_w3b_ordini_esterni_tennis_2026_10_08.py` (21, x4 bot
dove parametrico). Oggetti VERI: `Flumine` + `BetfairClient` (nessun login),
`OrderBookCache`, `CurrentOrdersEvent`, ordini del bot creati DA FLUMINE dal ref dello
stream, bot tennis da `_instantiate_bot`, `_disable_strategy`/`_strategy_is_flat` del runner,
marcatore letto da `chiusura_manuale.chiusi_dall_utente`. Sostituiti: `Market.cancel_order`
(confine con la rete) e il DB tennis (firme di `tennis_db`).

Coprono le cinque richieste del brief: ordine esterno sulla selezione -> stop (sito e app,
live e paper, x4 bot tennis); ordine su un ALTRO mercato -> nulla cambia; ordini del bot
stesso e degli altri bot (Mike, Omega, Safe, motore, un altro bot tennis) non esterni; paper
e live non mescolati (client paper affiancato, sorveglianza paper nel registro, bot paper in
runner live, bot live con ordini manuali simulati); senza osservatore/interruttore spento/
dry-run -> identico a oggi.

ESITI: vedi sez. 10 (compilata a fine lavoro).

## 4. Falsificazioni

### 4.1 Unitarie (script `W3B/strumenti/mutazioni_w3b.py`: contenuto salvato, mutazione,
pytest, ripristino, sha verificato; 0 `MUTAZIONE` residue, `git diff --stat` identico).
Ultimo giro completo sul codice FINALE: 15/15 ROSSE (fra parentesi i test rossi).

| # | Mutazione | Esito |
|---|---|---|
| M1 | ordine dal SITO preso per un bot | ROSSO (12) |
| M2 | ogni mercato e' del bot | ROSSO (2) |
| M3 | gli ordini del bot non riconosciuti come suoi | ROSSO (10) |
| M4 | il registro manda lo stream anche alle sorveglianze paper | VERDE al primo giro -> test nuovo `test_il_registro_non_manda_lo_stream_alle_sorveglianze_paper` -> ROSSO (1) |
| M5 | fonte paper con ordini live e dei comandi dei bot | ROSSO (1) |
| M6 | sorveglianza montata anche in prova / interruttore spento | ROSSO (2) |
| M7 | all'intervento nessun annullo dei vivi | ROSSO (2) |
| M8 | all'intervento le strategie non si fermano | VERDE al primo giro (l'involucro fermava comunque) -> asserzione `_fermo_per_intervento` -> ROSSO (1) |
| M9 | linea di base tolta (ordini vecchi = intervento) | ROSSO (1) |
| M10 | dopo l'intervento la sessione fa force-flat (copre) | ROSSO (1) |
| M11 | tennis: riga senza il marcatore che il ponte legge | ROSSO (4) |
| M12 | tennis: il ladder manuale (`tennis`) preso per un bot | ROSSO (7) |
| M13 | tennis: all'intervento il bot non si disabilita | ROSSO (8) |
| M14 | tennis: conclusione tolta dal `bot_control_worker` | ROSSO (1) |
| M15 | l'intervento si ripete | VERDE al primo giro (il registro saltava gia' chi era intervenuto) -> test `test_la_sorveglianza_reagisce_una_volta_sola...` -> ROSSO (1) |

### 4.2 A livello di REPLAY (famiglia OE, `certifica scalper_calcio 35797769`)

| # | Mutazione | Scenario | Esito |
|---|---|---|---|
| RM1 | ordine dal sito preso per un bot | ordine-esterno | KO OE2 |
| RM2 | ogni mercato e' del bot | ordine-esterno-altro-mercato | KO OE5 |
| RM3 | ordini del bot presi per ordini dell'utente | ordine-esterno-altro-mercato | KO OE1 + OE5 |
| RM4 | all'intervento nessun annullo dei vivi | ordine-esterno | KO OE4 (vivi non in annullo al primo book) |
| RM5 | involucro che non blocca (resta il fermo per istanza) | ordine-esterno | OK: seconda rete, atteso |
| RM6 | involucro E fermo tolti (il bot continua a decidere) | ordine-esterno | KO K4 (il bot crede vivo uno slot i cui ordini sono stati annullati) |

Referti: `W3B/falsificazioni/mut_RM*.txt`; script `W3B/strumenti/mutazioni_replay_w3b.py`
e `mutazione_rm6.py`.

## 5. Replay PRIMA/DOPO (scalper calcio, `--worker 1`)

Comando (identico prima e dopo; PRIMA su una copia `git archive` di `3b8ce19` in scratchpad,
DOPO nel worktree):
```
python -m Betfair.stream.backtest.certifica scalper_calcio <ev> --scenari base,paper,chiusura-abbinata-in-parte,rifiuti-betfair,sniper-paper[,ordine-esterno,ordine-esterno-altro-mercato] --worker 1
```
Registrazioni decompresse da `registrazioni_banco/` in `_live_raw/` (LEGGIMI).

DATI E DIFF: sez. 10.

## 6. Latenze misurate

* Banco (35797769 `ordine-esterno`): fotografia dello stream con l'ordine dell'utente
  abbinato -> decisione nello STESSO messaggio: **0 ms di tempo di mercato**; primo book
  successivo +100 ms (bot gia' fermo, vivi gia' in annullo: OE4). 35760084: 0 ms, primo
  book +202 ms. Il motore della decisione e' l'arrivo del messaggio dello stream ordini
  (thread di flumine, `Registro.ricevi_conto`), non il book: e' meglio del requisito
  "decisione al primo book/tick dopo il messaggio".
* Produzione (atteso, NON misurato: niente Betfair vero): push dello stream ordini di
  Betfair (ms) -> `_process_current_orders` di flumine -> stessa chiamata: annullo e fermo
  in pochi ms; riga `stopped` al battito (<= 5 s scalper; <= 3 s tennis); la decisione non
  aspetta il battito.
* Paper tennis: decisione al primo book del mercato del bot dopo l'abbinato dell'ordine
  manuale simulato (in gioco: decine-centinaia di ms).
* Unitari: `latenza_ms` fra `ricevuto_ms` (produttore) e decisione < 1000 ms (asserito).

## 7. PAPER dello scalper calcio: l'interfaccia (per allinearsi con W3a)

La sessione scalper in prova non ha una fonte in-process (sez. 0). Cio' che serve, gia'
pronto dal lato del bot: `Sorveglianza(..., modo="paper", fonte_paper=<callable>)`, dove
`fonte_paper()` ritorna le righe degli ordini MANUALI SIMULATI del ladder (solo
`mode='paper'`, solo ordini dell'utente) nella grafia del conto:
`{betId, marketId, selectionId, side, sizeMatched, averagePriceMatched, placedDate,
customerStrategyRef: "live", customerOrderRef}`; la reazione e' la stessa del live
(`installa_ordini_esterni` va solo esteso al ramo paper con la fonte). Due trasporti
possibili, da decidere col coordinatore/W3a:
1. la fotografia gemella di W3a (topic dichiarato, `mode='paper'`) letta con
   `esiti_ordini_canale.ClientEsiti` + `MemoriaConto` dentro la sessione (stessa classe del
   topic `conto`): e' la soluzione coerente con "una fonte per tutti";
2. le righe dello specchio del runner (topic `order`): NON bastano da sole, perche' gli
   ordini di Omega/Safe passati dalla coda DB hanno la stessa `source='runner'` del
   terminale manuale (serve la riga di coda: `motivo_bot_da_coda`).
Finche' non c'e', paper e live dello scalper NON sono specchio su questo punto (D5).

## 8. Parita' paper/live

* Tennis: stessa regola, stessa reazione (annullo + `_disable_strategy` + riga `stopped` col
  marcatore + attivita'); cambia solo la fonte (stream del conto reale / ordini manuali
  simulati dello stesso runner). Mai mescolati: la sorveglianza ha la modalita' del bot; il
  registro manda lo stream solo alle live; la fonte paper filtra `mode='paper'`; lo stream
  del client paper affiancato non e' pubblicato (`pubblica_conto_da_evento`). Test dedicati.
* Scalper: live sorvegliato, paper identico a oggi (gap D5).

## 9. Tennis: replay da rieseguire SUL PC (registrazioni assenti qui)

Il replay tennis (`tennis_live/tools/replay_bot.py`) istanzia i bot con `_instantiate_bot`
e NON passa da `setup_and_run`/`_arma_a_caldo`/`bot_control_worker` veri: i tre agganci
nuovi non vengono toccati. ATTESO: referti IDENTICI a quelli del cantiere 5 salvo la riga
`codice bot` (impronta: +2 moduli, `ordini_esterni` e `ordini_esterni_tennis`). Comandi
(PowerShell, radice del repo):
```
$D = "C:\Users\Admin\Desktop\tennis_rec\20260707"
$O = "AUDIT_2026-10-08\W3B"
foreach ($b in "tennis_scalper","tennis_pro","tennis_flb","tennis_swing") {
  python -m Betfair.stream.backtest.certifica $b 35790089 --data-dir $D --scenari tutti --worker 1 *> "$O\${b}_35790089_<prima|dopo>.txt"
}
foreach ($b in "tennis_pro","tennis_scalper") {
  python -m Betfair.stream.backtest.certifica $b 35794049 --data-dir $D --scenari tutti --worker 1 *> "$O\${b}_35794049_<prima|dopo>.txt"
}
```
Confronto: diff escluse `tempo:`, `TEMPO TOTALE`, `codice bot`: deve essere VUOTO. Il banco
tennis NON ha (ancora) uno scenario "ordine esterno": la condotta tennis e' coperta dai test
con oggetti veri (sez. 3). Proposta: scenario gemello nel replay tennis (porta additiva come
`ordini_esterni_banco.Iniettore`, che ha bisogno solo del quadro e delle strategie).

## 10. Esiti (numeri VERI; macchina con 4 CPU condivise, carico 12-16 per tutto il lavoro)

### 10.1 Test
* Nuovi: `python3 -m pytest Betfair/stream/tests/test_w3b_ordini_esterni_scalper_2026_10_08.py
  Betfair/stream/tennis_live/tests/test_w3b_ordini_esterni_tennis_2026_10_08.py -q -p no:cacheprovider`
  -> **45 passed** (24 + 21), ~1 s.
* Collegati (tutti i test di `Betfair/stream/tests` che nominano scalper_session,
  esiti_ordini_canale, replay dello scalper, ordini_esterni, registro_bot, applica_bot,
  strada unica; `-m "not cert"`): **1274 passed, 1 skipped** (84 s). Prima delle due
  correzioni di contratto (sez. 2, banco): 5 rossi attesi (impronta x4, strada unica x1) ->
  corretti in modo additivo.
* Tennis: `Betfair/stream/tennis_live/tests Betfair/stream/tennis_scalper/tests -m "not cert"`
  -> **1145 passed, 4 skipped, 5 xfailed** (80 s).
* Suite intera `python3 -m pytest Betfair/ -q -p no:cacheprovider` (570 s): **1 failed,
  11000 passed, 64 skipped, 6 xfailed**. L'unico rosso e'
  `test_motore_ordini_2026_09_24.py::test_latenza_logica_comando_place_sotto_20_ms`
  (p95 21,3 ms contro 20): misura di tempo sotto carico, gia' segnalata intermittente nel
  checkpoint W2. Rilanciato 4+4 volte alternando worktree e copia di PRIMA (`3b8ce19`):
  p95 worktree 23,8 / 20,5 / 21,8 / 19,9 ms, PRIMA 23,4 / 24,1 / 23,9 / 12,6 ms: stessa
  distribuzione, rosso anche su PRIMA; il percorso (motore ordini -> `live_order_worker`)
  non tocca nessun file di questo lavoro. Da rilanciare sul PC.

### 10.2 Replay PRIMA/DOPO (5 scenari di riferimento)
File: `W3B/prima_<ev>.txt` (copia `git archive` di `3b8ce19`), `W3B/dopo_<ev>.txt`
(worktree, impronta `d525a7b2bec9`), `W3B/dopo_finale_*` (codice FINALE, dopo la sola
correzione ASCII dei commenti: impronta `11203cda7d8d`, 13 file; 35760084 7 scenari e
35797769 `ordine-esterno` IDENTICI al DOPO riga per riga, tolti tempi e impronta). PRIMA:
impronta `585a8d4a2562` (12 file, uguale al cantiere 15). Diff:
`W3B/diff_prima_dopo.txt` (`strumenti/diff_referti.py`: esclusi tempi, impronta, comando).

| evento | scenario | PRIMA | DOPO |
|---|---|---|---|
| 35797769 | base | OK 44 azioni | OK 44, blocco IDENTICO |
| 35797769 | paper | OK 44 | OK 44, IDENTICO |
| 35797769 | chiusura-abbinata-in-parte | KO (B2 0,04, D1 del cantiere 15) | KO identico, IDENTICO |
| 35797769 | rifiuti-betfair | OK 56 | OK 56, IDENTICO |
| 35797769 | sniper-paper | OK 44 | OK 44, IDENTICO (*) |
| 35760084 | i 5 | OK, 0 azioni | OK, 0 azioni, IDENTICI (*) |

(*) l'unica riga diversa di `sniper-paper` e' la riga VUOTA che chiudeva l'ultimo blocco
del referto PRIMA: nel DOPO dopo `sniper-paper` vengono gli scenari nuovi. Le altre righe
diverse del referto sono la coda (ESITO e copertura dei controlli), che somma anche i due
scenari nuovi; sulla 35760084 P1/P2 passano da x0 a x3 per l'ordine dell'UTENTE che lo
specchio della sessione vede nel quadro condiviso (limite dichiarato del banco: lo scalper
su quella partita non opera mai).

Scenari nuovi (solo DOPO):

| evento | scenario | esito | fatti |
|---|---|---|---|
| 35797769 | ordine-esterno | OK, `stopped` | utente BACK 2,00@1,01 sul MO sel 22 appena la sessione ha 2 ordini vivi; fotografia -> decisione 0 ms; annullo 2/2; primo book +100 ms; OE1-OE4 sollecitati, 0 violazioni |
| 35797769 | ordine-esterno-altro-mercato | OK, `done`, 44 azioni come `base` | 57 fotografie (56 prima dell'abbinato dell'utente), 513 giudizi "proprio", 0 "utente" sul mercato della sessione, 1 "fuori dal bot"; OE1 e OE5 sollecitati |
| 35760084 | ordine-esterno | OK, `stopped` | lo scalper non quota mai su questa partita: ordine dell'utente all'ultimo istante utile sul MO (catalogo), decisione 0 ms, primo book +202 ms; OE1 solo x1 (nessun ordine della sessione) |
| 35760084 | ordine-esterno-altro-mercato | OK, `done` | identico a `base` (0 azioni) |

Tempi (macchina carica, confrontabili solo all'ingrosso): 35797769 5 scenari PRIMA 961,8 s,
DOPO 767,6 s; nuovi `ordine-esterno` 4,2 s, `altro-mercato` 135,5 s; totale DOPO 7 scenari
908,8 s (LENTO come PRIMA: il tetto e' superato gia' da `sniper-paper`, 378-458 s, non da
questo lavoro). 35760084: PRIMA 133,5 s, DOPO 143,6 s per 7 scenari (5 di riferimento
126 s circa).

### 10.3 Falsificazioni a livello di replay
`W3B/falsificazioni/mutazioni_replay.txt` e `mut_RM*.txt`: RM1 KO OE2, RM2 KO OE5, RM3 KO
OE1+OE5, RM4 KO OE4, RM5 OK (seconda rete, atteso), RM6 KO K4. Sha dei file ripristinati
identici; 0 `MUTAZIONE` residue.

## 11. Cosa NON ho fatto / NON ho potuto verificare

* Nessuna prova con lo stream ordini VERO di Betfair (vietato): come arriva un ordine del
  SITO (`rfo`/`rfs` assenti) e' verificato solo con la cache vera di betfairlightweight;
  l'immagine iniziale dopo una riconnessione e' gestita con la linea di base (placedDate) ma
  non osservata dal vivo.
* Paper dello scalper calcio: nessuna fonte (sez. 7).
* Replay tennis: da rieseguire sul PC (sez. 9); nessuno scenario tennis nel banco.
* Gli ordini di Omega/Safe passati dalla CODA DB del runner calcio portano
  `customerStrategyRef='live'` come il terminale manuale (nota di W2): senza leggere il DB lo
  stream non li distingue (D2, CHIUSA al secondo giro con la verifica sul DB, sez. 14).
  La conferma in thread di produzione (`ConfermaBot`) e' provata nei test unitari ma NON
  nel replay (il banco usa `ConfermaBanco`, stessa regola W2, lettura a tempo di mercato);
  le latenze delle letture PostgREST vere sono un'ASSUNZIONE (120 ms per select). Con `*_ORDINI_VIA_CANALE=1` (motore) portano il nome
  dell'attore e sono riconosciuti; via REST diretta portano `omega`/`mike`/... e sono
  riconosciuti.
* Non ho toccato `esiti_ordini_canale.py`, Mike/Omega/Safe, `live_order_worker.py`,
  frontend. W3a non e' nel ramo: nessun allineamento fatto.

## 12. Decisioni per l'utente (non prese da me)

* **D1 - "mercato del bot"**: ho preso i mercati su cui il bot e' ARMATO (scalper: tutti i
  mercati della sessione - Esito finale e Under/Over 1,5/2,5/3,5, con lo sniper tutte le
  linee Under/Over; tennis: il Match Odds della partita), non solo quelli dove ha ordini.
  Effetto: un tuo ordine abbinato su uno di quei mercati ferma il bot anche se in quel
  momento non aveva ordini li' (cosi' non entra mai sopra una tua posizione). Alternativa:
  solo i mercati dove il bot ha ordini.
* **D2 - CHIUSA al secondo giro (sez. 14)**: verifica sul DB con la regola di W2,
  sospensione prudente nel frattempo. Testo originale del primo giro, per memoria:
  Omega/Safe che piazzano dalla coda DB del runner
  calcio (non dal canale) sullo stesso mercato dello scalper sembrano tuoi ordini dall'app:
  lo scalper si fermerebbe. Proposta: tenere cosi' (prudente) e usare il canale per i bot
  (`*_ORDINI_VIA_CANALE=1`), oppure conferma dal DB come W2 (`_proprietari_bot`) prima di
  fermarsi solo per gli ordini con ref `live`, al prezzo di 0,5-1 s e qualche lettura DB.
  Stesso discorso per il tennis con ref `tennis` (Safe tennis dalla coda DB).
* **D3 - chiusura forzata a fine finestra dopo il tuo intervento**: NON parte. La posizione
  che il bot aveva (se il tuo ordine non la chiudeva tutta) resta a mercato: si annullano
  solo i suoi ordini non abbinati, la riga dice `stopped` + `intervento_utente` e parte il
  CRITICAL "posizione lasciata a mercato per arresto [intervento_utente]". Alternativa: far
  girare la protezione di fine finestra (rischio: copre una posizione che tu stai gestendo,
  la doppia copertura che il brief vuole evitare).
* **D4 - media under**: all'intervento si annulla anche la banca PERSIST (diversamente
  dall'arresto per stop/freno, P1, dove resta appoggiata): e' una copertura, e coprire dopo
  il tuo intervento e' cio' che la regola vieta. Da confermare.
* **D5 - scalper in prova**: non sa degli ordini manuali del ladder in prova finche' non si
  collega una fonte (sez. 7): paper non specchio del live su questo punto.
* **D6 - soglia**: qualunque tuo abbinato nuovo (anche 2 EUR, anche una tua banca appoggiata
  da prima che si abbina dopo) ferma il bot sulla partita. Nessuna soglia minima.

## 13. Da controllare dal vivo

* Log sessione scalper LIVE all'avvio: `[conto-ws] ordini del conto dallo stream pubblicati`
  e `[scalper-sess] <ev>: ordini esterni dallo stream ordini del conto (osservatore montato)`.
* Runner tennis LIVE: `[conto-ws] ...` una volta per build.
* Primo intervento vero: attivita' `intervento_utente` (scalper_activity /
  tennis_bot_activity) con `dove`, `latenza_ms`, `annullo`; riga `stopped`; nessun ordine
  del bot dopo l'istante dell'attivita'.
* Tennis in prova: un ordine manuale simulato dal ladder sul Match Odds di un bot in prova
  -> il bot si ferma, riga `stopped` con `stats.chiusura_manuale.come = intervento_utente`.

## 14. Secondo giro (revisione del coordinatore, 08/10): D2 chiusa

Richiesta: un ordine di Omega/Safe piazzato dalla CODA DB del runner (stesso
`customerStrategyRef` del terminale manuale) non deve fermare scalper/bot tennis. Si usa la
STESSA classificazione "del bot / fuori bot" di W2; mai una lettura DB nel giro caldo; una
lettura per bet_id nuovo, in cache; finche' non si sa il bot e' SOSPESO su quella selezione
(non fermo); di un bot -> riprende; fuori bot -> stop; DB illeggibile -> resta sospeso e lo
scrive.

### 14.1 Cosa ho cambiato
* Worktree portato sulla cima `7633e20` (cantiere 6) con fast-forward; le mie aggiunte a
  `applica_bot.py`/`registro_bot.py` riapplicate (3-way pulito) accanto a quelle del cantiere
  6, poi tolte dall'indice (nessun file in stage).
* `tennis_scalper/ordini_esterni.py`:
  * ogni ordine che i soli riferimenti danno all'UTENTE (sito o ref manuale) su un mercato del
    bot non decide piu' da solo: `Sorveglianza` lo mette IN VERIFICA, sospende la (mercato,
    selezione) e chiede l'esito alla `ConfermaBot`; esito `fuori_bot` -> intervento come
    prima; `bot:<motivo>` -> sospensione rilasciata, attivita' `ordine_esterno_di_un_bot`;
    errore del DB -> resta sospeso, attivita' `ordine_esterno_non_verificabile` (una volta),
    nuova lettura non prima di `RIPROVA_DB_S` (30 s, il "respiro" del DB del progetto);
    attivita' `ordine_esterno_in_verifica` all'inizio. La decisione si prende in `rivedi()`
    (thread di flumine: al book successivo o alla sveglia).
  * `ConfermaBot`: thread suo, coda di bet_id, UNA lettura per bet_id mai visto, esito in
    cache (tetto 5000), errori con istante; `sveglia` dopo ogni lettura.
  * `controllo_sospensione`/`monta_controllo`: trading control di flumine `ORDINI_ESTERNI`
    che rifiuta PLACE/REPLACE di una strategia sorvegliata sulla selezione sospesa (e dopo
    l'intervento); gli annulli passano. Via di produzione del rifiuto (`order.violation`,
    `place_order` falso: il bot lo gestisce come ogni rifiuto, freno compreso).
  * `Registro.rivedi()` e `prima_di_valutare` (gancio per il runner tennis).
* `scalper_session.py`: `conferma_dei_bot(db, framework, registro)` = `ConfermaBot` con
  `live_order_worker._proprietari_bot(db.sb, ...)` (la regola DB di W2, RIUSATA: tabelle dei
  bot, specchio con `source`, riga della coda del runner con `motivo_bot_da_coda`) e sveglia
  = `CustomEvent` nella coda di flumine (decisione nel thread di flumine appena il DB
  risponde); `installa_ordini_esterni(..., db=db)` monta conferma e controllo.
* Tennis: `tennis_live_order_worker._track_manual(..., coda=cmd)` (additivo, 4 chiamate)
  ricorda `client_ref`/`params` della riga di coda che il runner ha eseguito;
  `ordini_esterni_tennis.MemoriaOrdiniRunner` li tiene anche dopo che il worker toglie i
  terminali e li fotografa PRIMA di giudicare ogni messaggio dello stream; la conferma tennis
  guarda prima li' (regola di W2 in-process: attore del motore o `motivo_bot_da_coda`), poi il
  DB (`_proprietari_bot` col client tennis). In PROVA la fonte del ladder esclude gli ordini
  dei bot con la stessa regola (nessun DB: in prova e' esatta in-process).
* Banco: `ConfermaBanco` (regola VERA di W2 sul DB del replay, esito visibile dopo `n select x
  LATENZA_LETTURA_S` di mercato, deterministica); il DB finto del replay applica i filtri
  `eq`/`in_` SOLO sulle tabelle della verifica dichiarate dallo scenario (altrove identico a
  prima); la sveglia di produzione e' emulata al passo del motore dopo qualunque book.
  Scenari nuovi: `ordine-esterno-app`, `ordine-esterno-di-un-bot` (riga di coda di Omega con
  quel bet_id), `ordine-esterno-db-giu` (ogni lettura delle tabelle della verifica solleva);
  controlli OE6/OE7; OE2 ora pretende la sospensione al messaggio e la decisione DOPO che la
  verifica e' pronta. `applica_bot.py`: i tre scenari fra gli scartati.

### 14.2 Test (falsificati)
* Scalper 31, tennis 25 (56 in tutto, 0,9 s). Nuovi del secondo giro: Omega dalla coda
  (riga di coda) e Omega in `omega_trades` -> nessuno stop; ordine manuale con la stessa
  forma ma senza riga di bot -> stop; DB giu' -> sospeso, controllo che rifiuta il PLACE sulla
  selezione (BetfairOrder VERO, `ControlError`, stato VIOLATION), altre selezioni e annulli
  passano, un solo avviso, una sola lettura; DB che torna -> decide; una lettura per bet_id;
  conferma di PRODUZIONE in thread con la sveglia `CustomEvent` nella coda VERA di flumine;
  tennis: Safe tennis dalla coda riconosciuto in-process (0 letture DB), bot noto al DB,
  DB giu'; paper: ordine di Safe tennis dalla coda escluso anche dopo la potatura.
* Il DB nei test e' un client con la grafia di supabase-py (`table().select().eq().in_()
  .execute().data`) con filtri veri: la funzione di W2 `_proprietari_bot` gira VERA sopra.
* Mutazioni unitarie (script `W3B/strumenti/mutazioni_w3b.py`, ultimo giro sul codice
  finale): **23/23 ROSSE** (M1-M15 del primo giro, ripuntate dove il testo e' cambiato, piu'
  M16 verifica che ignora il DB, M17 "di un bot" trattato come fuori bot, M18 DB giu' = fuori
  bot, M19 controllo che non rifiuta, M20 nessuna sospensione, M21 decisione dai soli
  riferimenti, M22 tennis: riga di coda ignorata, M23 esito non tenuto in cache). Al primo
  giro M23 era VERDE (mutava un controllo ridondante): mutazione riscritta sulla cache vera.
* Mutazioni di replay del secondo giro (script `W3B/strumenti/mutazioni_replay_giro2.py`,
  `certifica scalper_calcio 35797769 --worker 1`, esiti in `W3B/giro2/mutazioni_replay_giro2*.txt`
  e `W3B/giro2/falsificazioni/`; sha `14f893ed26a8` ripristinato dopo ognuna, 0 `MUTAZIONE`
  residue):
  - RM7 "di un bot" trattato come fuori bot [di-un-bot] -> **KO OE6**;
  - RM8 DB illeggibile = fuori bot in `ConfermaBot._gira` [db-giu] -> **OK (verde)**: il banco
    sostituisce `ConfermaBot` con `ConfermaBanco` (lettura a tempo di mercato), quella riga
    nel replay non gira per costruzione. Difetto coperto dal test unitario M18 (rosso) e,
    nel percorso di decisione di produzione, da RM11;
  - RM9 il controllo non rifiuta sulla selezione sospesa [db-giu] -> **KO OE7**;
  - RM10 decisione dai soli riferimenti (verifica saltata) [di-un-bot] -> **KO OE6**;
  - RM11 DB illeggibile = fuori bot in `Sorveglianza.rivedi` [db-giu] -> **KO OE7**.
  Esito: 4/5 rosse; la verde e' un limite dichiarato del banco (la conferma in thread non
  gira nel replay), non un controllo cieco.

### 14.3 Replay PRIMA/DOPO sulla cima `7633e20` (`--worker 1`)
PRIMA: copia `git archive` di `7633e20` (impronta `585a8d4a2562`, 12 file). DOPO: impronta
`6eca8b981bb8` (13 file). File: `W3B/giro2/prima_*.txt`, `dopo_*.txt`, `diff_prima_dopo.txt`.

* I 5 scenari di riferimento: **IDENTICI** su 35797769 (base 44, paper 44,
  chiusura-abbinata-in-parte KO identico = D1 del cantiere 15, rifiuti 56, sniper-paper 44) e
  su 35760084 (5 OK, 0 azioni). Unica riga diversa: la riga vuota di fine blocco di
  `sniper-paper` (nel DOPO seguono altri scenari) e la coda dei conteggi.
* Scenari nuovi, tutti OK:

| scenario | 35797769 | 35760084 |
|---|---|---|
| ordine-esterno (sito) | stop; sospensione +0 ms; verifica 5 select = 600 ms; decisione definitiva **1018 ms** dopo il messaggio (nessun book fra +600 e +1018); annullo 2/2 | stop; **886 ms** |
| ordine-esterno-app | identico al sito (stop, 1018 ms) | stop, 886 ms |
| ordine-esterno-di-un-bot | NESSUNO stop; motivo `bot:coda:omega-t9`; ripresa a +1018 ms; 0 ordini accettati sulla selezione sospesa; 44 azioni come `base` | nessuno stop, ripresa +886 ms |
| ordine-esterno-db-giu | NESSUNO stop; resta sospesa fino a fine sessione; 38 piazzamenti del bot sulla selezione RIFIUTATI dal controllo (freno dei rifiuti attivo), 0 accettati; rilettura del DB ogni 30 s di mercato; attivita' `non_verificabile` | idem, 0 azioni |
| ordine-esterno-altro-mercato | come base (44), nessuna sospensione | come base |

* Tempi (macchina carica): 35797769 10 scenari 1036,6 s (5 di riferimento 751,8 s contro
  526,5 s del PRIMA, che e' girato con meno carico: i numeri non cambiano); 35760084 138,1 s.

### 14.4 Latenze (risposta alla richiesta "misura nel banco")
* messaggio dello stream -> SOSPENSIONE della selezione: **0 ms** (stessa chiamata);
* messaggio -> esito della verifica: **600 ms** = 5 select di `_proprietari_bot` x 120 ms
  (ASSUNZIONE del banco comune `LATENZA_LETTURA_S`, non una misura);
* messaggio -> decisione definitiva: **1018 ms** (35797769) e **886 ms** (35760084): verifica
  + attesa del primo passo del motore (nel banco la sveglia non ha un istante suo). In
  produzione la sveglia `CustomEvent` fa decidere appena il DB risponde: atteso = tempo delle
  5 letture PostgREST (stima, da misurare sul PC).

### 14.5 Decisioni per l'utente (aggiornate)
* **D2: CHIUSA** come chiesto dal coordinatore (verifica sul DB con la regola di W2).
* **D7 (nuova)**: durante la sospensione (verifica in corso o DB illeggibile) il controllo
  rifiuta OGNI ordine nuovo del bot su quella selezione, anche le sue chiusure/coperture
  (esempio 35797769 `db-giu`: 38 piazzamenti rifiutati). Con il DB giu' a lungo la posizione
  del bot su quella selezione resta come era (i suoi ordini gia' vivi non si annullano: e' una
  sospensione, non uno stop). Alternativa: lasciare passare le sole chiusure (riduzione del
  rischio) durante la verifica. Lo porta il coordinatore.

### 14.6 Allineamento al cantiere 9 e alla cima `31fa6433` (messaggi del coordinatore)
* Worktree portato in fast-forward a `1ac69d0` (cantiere 9) e poi, dopo `git fetch origin
  claude/blissful-sagan-hri7o6`, a `31fa6433` (`d0cf8b94` piu' un commit di sola
  documentazione; fra `1ac69d0` e `31fa6433` nessun file `Betfair/` cambia). Le modifiche
  W3b sono state riapplicate con `git apply --3way`, poi tolte dall'indice (nessun
  `git add`, nessun commit).
* **CONFLITTI: due, entrambi fra righe aggiunte vicine, risolti tenendo ENTRAMBE le parti**:
  - `backtest/applica_bot.py`: i 4 scenari del cantiere 9 (`ingresso-abbinato-in-parte[-paper]`,
    `rifiuti-betfair-codici[-paper]`) seguiti dai 5 di W3b in `SCENARI_SCARTATI`;
  - `scalper/tools/replay_registrazioni.py`: l'import `scavalco_rifiuti as SR` (cantiere 9)
    e `ordini_esterni_banco as OEB` (W3b).
  Gli altri hunk del cantiere 9 (`sorveglianze_extra`, scenari, `scalper_bot.py`
  `submin_abort`) sono entrati senza conflitto. Verifica dell'unione: le 326 righe aggiunte
  da W3b sono tutte presenti, nessuna in piu' e nessuna tolta, e nessuna delle 33 righe
  aggiunte dal cantiere 9 nei due file manca (script `verifica_unione.py` nello scratchpad).
* Test sulla cima unita: suite intera `python3 -m pytest Betfair/ -q -p no:cacheprovider`
  **11167 passati, 64 saltati, 6 xfailed, 0 rossi** (492 s, `W3B/giro2_c9/suite_intera.txt`);
  mirati W3b + cantiere 9 + contratti 1293 passati (e 119 dopo l'ultimo fast-forward).
* Replay PRIMA sulla cima `1ac69d0` (copia `git archive` con le stesse registrazioni,
  sha verificati), 5 di riferimento + 4 del cantiere 9 (`W3B/giro2_c9/prima_*.txt`):
  35797769: base 44 OK, paper 44 OK, chiusura-abbinata-in-parte KO (D1 del cantiere 15),
  rifiuti 56 OK, sniper-paper 44 OK, **ingresso-abbinato-in-parte OK 49**, -paper OK,
  **rifiuti-betfair-codici KO RC3 132**, -paper KO (i valori attesi dal coordinatore);
  35760084: i 5 di riferimento OK, 0 azioni; i 4 del cantiere 9 NE (non esercitati).
* Replay DOPO: **INTERROTTO per ordine del coordinatore** (i DOPO li lancia lui su macchine
  separate). Prima dell'interruzione erano finiti 12 scenari su 14 su 35797769
  (`W3B/giro2_c9/dopo_35797769_PARZIALE_interrotto.txt`): le righe di esito dei 9 scenari
  in comune con il PRIMA sono IDENTICHE, `rifiuti-betfair-codici` ha ancora KO RC3 x1 e 132
  azioni; `ordine-esterno`, `-app` e `-di-un-bot` sono OK. Non conta come certificazione:
  il confronto completo dei blocchi e 35760084 restano da fare.
* **Comandi `certifica` del DOPO** (dalla radice del worktree, uno per processo; si possono
  spezzare per scenario con `--scenari <uno>` su macchine diverse):

```
python -m Betfair.stream.backtest.certifica scalper_calcio 35797769 --worker 1 --scenari base,paper,chiusura-abbinata-in-parte,rifiuti-betfair,sniper-paper,ingresso-abbinato-in-parte,ingresso-abbinato-in-parte-paper,rifiuti-betfair-codici,rifiuti-betfair-codici-paper,ordine-esterno,ordine-esterno-app,ordine-esterno-di-un-bot,ordine-esterno-db-giu,ordine-esterno-altro-mercato
python -m Betfair.stream.backtest.certifica scalper_calcio 35760084 --worker 1 --scenari base,paper,chiusura-abbinata-in-parte,rifiuti-betfair,sniper-paper,ingresso-abbinato-in-parte,ingresso-abbinato-in-parte-paper,rifiuti-betfair-codici,rifiuti-betfair-codici-paper,ordine-esterno,ordine-esterno-app,ordine-esterno-di-un-bot,ordine-esterno-db-giu,ordine-esterno-altro-mercato
```
  Attesi: i 9 scenari di riferimento e del cantiere 9 identici a `W3B/giro2_c9/prima_*.txt`;
  i 5 W3b come in sez. 14.3 (35797769: stop a 1018 ms per sito e app, nessuno stop per
  `di-un-bot` con 44 azioni, `db-giu` sospeso con 38 rifiuti e 0 accettati, `altro-mercato`
  44 come `base`; 35760084: 886 ms, 0 azioni). Falsificazione di replay (facoltativa, 4
  replay da circa 2 min): `python3 AUDIT_2026-10-08/W3B/strumenti/mutazioni_replay_giro2.py`
  (RM7, RM9, RM10 e RM11 rosse; RM8 verde per costruzione, sez. 14.2).

## Blocco per la cronostoria

- CHECKPOINT W3b - I BOT DENTRO FLUMINE SANNO SUBITO DEGLI ORDINI ESTERNI (delegato, DA
  VERIFICARE dal coordinatore). Premessa del brief corretta: lo scalper calcio NON gira nel
  runner calcio, e' un processo per partita col SUO flumine e il SUO stream ordini del conto.
  LIVE: lo STESSO osservatore del runner (`esiti_ordini_canale.osserva_conto_su_flumine`)
  montato sul flumine della sessione scalper e del runner tennis con una `pubblica` in
  memoria (`tennis_scalper/ordini_esterni.py`, nuovo, regola unica; riconoscimento dei bot
  con la regola di W2). Ordine dell'UTENTE (sito o terminale manuale) abbinato su un mercato
  del bot -> nel thread di flumine, al messaggio: bot fermo, vivi annullati, nessuna
  copertura; riga `stopped` col marcatore (scalper `stats.intervento_utente`, tennis
  `stats.chiusura_manuale.come=intervento_utente`, mai riarmato) e attivita'
  `intervento_utente`. PAPER tennis: ordini manuali simulati del ladder (stesso runner).
  PAPER scalper: NESSUNA fonte (processo separato) -> interfaccia scritta per W3a (D5).
  Banco: scenari `ordine-esterno` e `ordine-esterno-altro-mercato` (OE1-OE5); 5 scenari di
  riferimento IDENTICI prima/dopo su 35797769 e 35760084; latenza 0 ms di mercato (decisione
  sul messaggio dello stream), primo book +100/+202 ms. Test 45 nuovi; mutazioni unitarie
  15/15 rosse, di replay 5/6 rosse + 1 seconda rete attesa. Suite 11000 verdi / 1 rosso di
  latenza intermittente (rosso anche su PRIMA). Tennis: replay da rieseguire sul PC
  (atteso identico, sez. 9). Decisioni D1-D6 all'utente. Referto
  `AUDIT_2026-10-08/W3B_CONSAPEVOLEZZA_FLUMINE.md`, file in `AUDIT_2026-10-08/W3B/`.
- CHECKPOINT W3b SECONDO GIRO - D2 CHIUSA (delegato, DA VERIFICARE dal coordinatore).
  Worktree portato sulla cima `31fa6433` di `claude/blissful-sagan-hri7o6` (cantieri 6
  e 9 dentro); i due conflitti, con il cantiere 9 in `applica_bot.py` e
  `replay_registrazioni.py`, sono risolti tenendo le due parti, senza righe perse.
  Suite 11167 verdi, 0 rossi. PRIMA su `1ac69d0` fatto; DOPO interrotto per ordine del
  coordinatore, i comandi sono nella sez. 14.6.
  Un ordine con riferimenti "dell'utente" (`live`/`tennis`/nessuno) abbinato sul mercato
  del bot non ferma piu' subito: la SELEZIONE si SOSPENDE (controllo di trading
  `ORDINI_ESTERNI`, rifiuta PLACE/REPLACE del bot su quella selezione) e il bet_id passa
  alla classificazione di W2 (`live_order_worker._proprietari_bot`: tabelle dei bot,
  specchio, coda del runner con `motivo_bot_da_coda`). La lettura e' una sola per bet_id
  nuovo, in thread suo con cache, e la sveglia `CustomEvent` porta la decisione nel thread
  di flumine. Esiti: "di un bot" -> riprende; "fuori bot" -> stop come al primo giro; DB
  illeggibile -> resta sospeso, attivita' `ordine_esterno_non_verificabile`, riprova ogni
  30 s. Nel tennis la coda del runner si riconosce in-process (`_track_manual` salva la
  riga di coda). Banco: scenari nuovi `ordine-esterno-di-un-bot` e `ordine-esterno-db-giu`
  (OE6, OE7); `ConfermaBanco` usa la regola VERA di W2 sul DB del replay. I 5 scenari di
  riferimento sono IDENTICI prima/dopo su 35797769 e 35760084. Latenza messaggio ->
  decisione definitiva: 1018/886 ms, con le letture DB ASSUNTE a 120 ms/select. Test W3b
  56; mutazioni unitarie 23/23 rosse; di replay 4/5 rosse (RM8 verde per costruzione: la
  conferma in thread non gira nel banco, coperta da M18 e RM11). Nuova decisione D7:
  durante la sospensione sono rifiutate anche le chiusure del bot.

## Verifica del coordinatore cloud (08/10)
- Diff riletto (sessione scalper e runner tennis montano l'osservatore dello stream ordini gia' esistente; sospensione della selezione e
  classificazione «del bot / fuori bot» di W2 per i bet_id nuovi, in thread, con cache; stop solo per gli ordini fuori bot).
- Test W3b + contratto strada unica 82 verdi nel checkout integrato. MIE MUTAZIONI: sospensione che lascia passare gli ordini -> 7 rossi;
  sorveglianza montata anche in prova -> 1 rosso; un ordine di un altro bot trattato come intervento al punto della cache -> 1 rosso e al
  punto di `rivedi` -> 6 rossi (i due test che li separano sono stati aggiunti dal delegato su mia richiesta: prima il punto della cache
  sopravviveva da solo).
- REPLAY DOPO su macchina cloud separata (`AUDIT_2026-10-08/W3B/dopo_cloud/`, 14 scenari x 2 registrazioni, blocchi paralleli): nessuna
  differenza dagli attesi; i 9 scenari in comune col PRIMA identici.
- Decisioni per l'utente: D1, D3, D4, D6, D7 (sospensione che blocca anche le chiusure del bot); D5 prova dello scalper senza fonte degli
  ordini manuali (processo separato).
