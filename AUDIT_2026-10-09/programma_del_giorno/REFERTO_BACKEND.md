# Programma del giorno (/board) — REFERTO BACKEND (09/10/2026)

Delegato backend (Python), worktree isolato, contratto `CONTRATTO.md` §1-§4 (la copia di
riferimento e' nel checkout principale, `AUDIT_2026-10-09/programma_del_giorno/CONTRATTO.md`).
Dominio toccato: solo `Betfair/` (+ questo referto e i suoi allegati). Nessuna strategia di bot
toccata (soglie, stake, tetti, gambe): il lavoro e' sul board, sul canale e sull'instradamento
del `/order` manuale del desktop. Paper e live restano separati (client della modalita' della
richiesta, test dedicato), calcio e tennis restano in processi e canali distinti.

## 1. Cosa e' cambiato (file:riga)

### 1.1 Board anche da PARCHEGGIATO (bug: «per tennis il tabellone non parte proprio»)
Causa: il board era SOLO un `BackgroundWorker` di flumine; il runner senza partite resta nel
ciclo d'attesa e non crea il framework -> nessun board (tennis senza follow: mai; calcio:
difetto latente identico).
- `Betfair/stream/board_worker.py:777` `giro_da_parcheggiato(session, et, intervallo)`: STESSA
  funzione del worker, STESSO stato di modulo, STESSA cadenza (`LIVE_BOARD_POLL_SEC`, 10 s):
  un giro solo se l'ultimo giro vero (`_STATE["giro_ts"]`, scritto da chiunque lo faccia) e'
  piu' vecchio della cadenza. Zero costo senza desktop (esce su `is_active()`), mai solleva.
- `board_worker.py:100,758` `_LOCK_GIRO`: un giro alla volta (worker di flumine o ciclo
  d'attesa), acquisizione NON bloccante (chi arriva secondo salta). Nessun thread nuovo.
- Calcio `Betfair/stream/runner.py:1616` `_attesa_board_e_canale`, chiamata nei due rami del
  ciclo d'attesa accanto a `run_account_sync_if_due` (`runner.py:2837`, `:2893`).
- Tennis `Betfair/stream/tennis_live/tennis_runner.py:3139` `_attesa_board_e_canale`, chiamata
  nei due rami d'attesa accanto a `_pubblica_battito_attesa` (`:3253`, `:3283`).
  `session.context_api_client` e' gia' impostato prima del ciclo (`tennis_runner.py:~3147`,
  calcio `runner.py:~2672`): verificato, nessun login in piu'.
- Nota cadenza: nel ramo «follow presenti ma nessun mercato» il ciclo dorme 15 s, quindi li' il
  board gira ogni ~15 s (non 10).

### 1.2 Righe `board` estese (§1) — `board_worker.py`
- `_selezione_da_runner` (:212) / `row_from_scan_payload` (:251): `back_size`/`lay_size`
  (REST con `scanner.best_size`, che tollera i livelli-dizionario di flumine; feed dal pair
  `scanner.price_pair`).
- `_row_from_book` (:232): `bet_delay` dal book REST.
- `arricchisci_riga` (:358): `score` SOLO se la riga e' in gioco E c'e' la riga FRESCA del feed
  (`score_calcio` :309, `score_tennis` :329), `fixture_id` (:352, calcio, da
  `selection_hint.fixture_id`), `bet_delay` (book REST o feed), `updated_ms`.
  Calcio `ht` = intervallo dallo stato IPS (`intervallo_da_stato_ips` :294, stessa lista di
  stati di `atlante_v4.tempo_da_stato_ips`); stato assente = `null`.
  Tennis: `sets`/`games` dal payload (gia' parsati dallo scanner), `points`/`server` dallo stato
  IPS grezzo col parser di sempre `parse_tennis_scores` (p1 = casa).
- `total_matched`: `_collect_rows` (:428) — la REST di sempre (blocchi da 25, al piu' ogni
  60 s) ora interroga TUTTI i mercati del programma (<= 60 -> al piu' 3 chiamate/60 s), e il
  suo `total_matched` vince su quello del feed. Motivo verificato nel codice dello scanner
  (`safe_strategy/service.py:~1432-1443`): lo stream dello scanner non porta `tv`, il feed ha
  `mo_total_matched` None oppure FERMO all'ultima REST dello scanner (che a mercato coperto dallo
  stream non rilegge piu'). Nessuna chiamata per riga.

### 1.3 `market_types` (§2) — `board_worker.py`
- `_refresh_market_types` (:515): UNA `listMarketTypes` sugli eventi del programma, cache 300 s
  (stessa del catalogo). `tipi_da_risultato`: MATCH_ODDS primo, poi per numero di mercati.
- `tipo_escluso` (:472): calcio esclude ogni tipo che contiene `CORRECT_SCORE` e
  `HALF_TIME_SCORE`; tennis nessuna esclusione (contratto).
- `nome_tipo`: `listMarketTypes` NON porta nomi -> tabella italiana dei tipi comuni + nome
  derivato dal codice (`OVER_UNDER_25` -> «Under/Over 2.5 gol»; ignoti: codice leggibile).
- Se `listMarketTypes` non e' mai riuscito la chiave `market_types` e' ASSENTE (non noto), mai
  `[]`; il board esce comunque.

### 1.4 `board_mercato` (§3)
- Canale `Betfair/stream/local_channel.py:36,42` metodo `board_mercato` in `_ALLOWED_METHODS`,
  NON in `_METODI_CHE_ESEGUONO`; `:440` instradamento PRIMA della coda comandi; `:455`
  `_servi_board_mercato` risponde SUBITO dal thread del canale (`{id, ok:true}` o
  `{id, ok:false, e}`); `:473` `set_board_mercato(cb)`. Senza board nel processo: «board non
  attivo su questo canale». Canali dei bot (`solo_lettura`) e lettori: rifiuto di sempre.
  Nessun token richiesto, la connessione senza token resta aperta.
- `board_worker.py:533` `richiedi_mercato` (thread del canale, zero I/O, sotto lock): rifiuta
  tipo mancante, MATCH_ODDS («board di sempre»), escluso, tipi non ancora caricati, tipo non
  presente nei `market_types`; **tetto `TETTO_TIPI_RICHIESTI = 3` tipi vivi per sport** (un
  quarto e' RIFIUTATO col motivo, nessun tipo altrui espulso); rinnovo sempre ammesso;
  `TTL_RICHIESTA_S = 75` (`tipi_richiesti` dimentica i tipi e il loro stato).
- Push `board_mercato` (`_pubblica_mercati`), uno per tipo vivo a ogni giro:
  `{market_type, rows, updated_ms}`; righe `{event_id, market_id, market_name, status, inplay,
  total_matched, selections:[{selection_id, name, handicap, back, lay, ltp, back_size,
  lay_size}]}`. Catalogo per tipo (eventi del programma, `max_results=60`, cache 300 s); prezzi
  dal feed dove copre quel `market_id` (calcio: blocchi `ou`/`btts`/`ht_result`, LTP non
  presente nel feed -> `null`), altrimenti REST a blocchi da 25 al piu' ogni 60 s per tipo;
  volume dalla REST come sopra. Tipi con piu' linee (ASIAN_HANDICAP): una riga per mercato,
  `handicap` per selezione, ordine `sortPriority`.

### 1.5 Ordini dal tabellone su mercato NON sottoscritto (§4)
VERIFICA prima della modifica (codice di oggi):
- calcio, motore ordini acceso (`MOTORE_ORDINI_CANALE=1`, il caso di produzione): `/order` ->
  `MotoreOrdini._servi_order` -> `live_order_worker._process_local_requests` -> `_resolve_market`
  -> **«market … non sottoscritto nel runner»**; runner parcheggiato -> «runner senza framework
  attivo … NON eseguito». Solo i `/comando/` dei bot agganciavano al volo.
- calcio senza motore: dentro il framework idem «non sottoscritto»; **parcheggiato: nessuno
  drenava la coda** -> richiesta senza risposta (timeout pagina 10 s) ed ESEGUITA minuti dopo,
  alla nascita del framework (difetto latente, ora chiuso).
- tennis: il motore tennis NON serve `/order` (`CanaleSoloComandi`), il `/order` va sempre al
  worker tennis -> «non sottoscritto nel runner tennis»; **parcheggiato: nessuno drenava** (stesso
  difetto latente del calcio).
- ripiego DB (`request_betfair_live_order` / `request_tennis_live_order`): NON aggancia (vedi §5).

CORREZIONE (stesso meccanismo dei comandi, nessuna connessione nuova, stesso tetto):
- Calcio `Betfair/stream/motore_ordini.py:142-146` costanti; `:2291` `_servi_order(reqs,
  aggancio)`; `:2334` `_order_da_agganciare`: `place` su mercato non servibile (o runner senza
  framework, o dietro a un place dello stesso mercato gia' in attesa: FIFO) -> `AutoFollow.richiedi`
  (lo stesso dei comandi) -> richiesta PARCHEGGIATA in RAM; tetto pieno -> `ok:false`
  `tetto_mercati_pieno: … - ordine NON piazzato` SUBITO. `:2385` `avanza_order_aggancio`
  (chiamato da `avanza_aggancio` :1651, thread del motore a 50 ms): al primo book nuovo la
  richiesta riparte da `_servi_order(aggancio=False)`, cioe' guardia d'avvio, modo, kill-switch,
  dedup RIFATTI adesso; oltre la scadenza `ok:false` `in_aggancio: … - ordine NON piazzato`.
  Un errore servendo le richieste pronte non risponde a quelle parcheggiate (`:2320`).
- **Attesa massima `/order` = 7000 ms (`MOTORE_AGGANCIO_ORDER_MAX_MS`, tetto 8000)**, sempre
  sotto i 10 s di `LOCAL_REQUEST_TIMEOUT_MS` del frontend (test che legge la costante del
  frontend): mai un ordine piazzato dopo che la pagina ha gia' dichiarato l'errore di trasporto.
- Calcio runner parcheggiato SENZA motore (`runner.py:1589-1625`): la coda del canale si drena a
  ogni giro d'attesa e ogni richiesta riceve SUBITO `ok:false` col motivo
  (`_MOTIVO_PARCHEGGIATO_SENZA_MOTORE`). Col motore la coda la serve il motore (non si tocca).
- Tennis `Betfair/stream/tennis_live/tennis_live_order_worker.py:1565-1730`: `_parcheggia_o_rifiuta`
  usa l'`AgganciaTennis` del runner (`session.aggancio_desktop`, impostato in
  `tennis_runner.py:3018`, tolto a `:3030`, default `:602`): iscrizione a caldo sulla STESSA
  connessione, stesso tetto; `_avanza_locali_in_aggancio` (:1633, a ogni tick del worker ordini
  `:1922`, prima dei comandi nuovi) riparte con TUTTE le regole del canale rifatte; guardia
  armata -> i parcheggiati ricevono subito il motivo della guardia (`:1916`).
  `servi_comandi_da_parcheggiato` (:1663, dal ciclo d'attesa del runner tennis): snapshot -> vuoto
  (come il worker); OFF / guardia -> rifiuto; `place` con aggancio disponibile e regole di
  apertura soddisfatte (modo servibile, modo effettivo, kill-switch) -> aggancio chiesto (il
  runner parte con quella partita alla build successiva, `follows_con_comandi`) e attesa con la
  stessa scadenza; tutto il resto -> rifiuto immediato col motivo.

COSA SUCCEDE COL RUNNER PARCHEGGIATO (dichiarazione):
| caso | esito |
|---|---|
| calcio, motore acceso (produzione) | place accettato in attesa, l'auto-follow mette il mercato nel piano, il runner esce dall'attesa e costruisce il framework; se il primo book arriva entro 7 s -> piazzato e `ok`; altrimenti `ok:false in_aggancio … riprova` (il mercato resta nel piano: il secondo clic e' immediato) |
| calcio, motore spento o OFF | `ok:false` subito: «runner calcio parcheggiato … senza motore ordini … Apri la partita (Trading) e riprova» |
| tennis, motore tennis acceso (`MOTORE_ORDINI_CANALE_TENNIS=1`) | come il calcio col motore (aggancio a comando, build alla giro d'attesa successivo, 7 s) |
| tennis, motore tennis spento (default di codice) | `ok:false` subito: «runner tennis parcheggiato … (aggancio al volo spento: motore ordini tennis non attivo)» |
| qualunque, OFF / guardia d'avvio armata | `ok:false` subito col motivo |

## 2. Payload VERO prodotto (generato dal codice, non scritto a mano)
Generati dai test `test_push_board_mercato_feed_dove_copre_rest_altrove_e_handicap` (calcio) e
`test_esempio_tennis_per_il_referto` con
`BOARD_ESEMPIO_DIR=<cartella> python -m pytest Betfair/stream/tests/test_board_programma_2026_10_09.py -k "esempio or push_board_mercato"`.
File completi: `esempio_payload_calcio.json`, `esempio_payload_tennis.json` (questa cartella).
Estratto calcio (riga in gioco dal feed + riga pre-partita dalla REST):
```json
{"event_id": "35000001", "event_name": "Casa v Ospite", "open_date": "2026-10-09T18:00:00+00:00",
 "market_id": "1.101", "status": "OPEN", "inplay": true, "total_matched": 15234.5,
 "selections": [{"selection_id": 11, "name": "Casa", "back": 1.5, "lay": 1.52, "ltp": 1.5,
                 "back_size": 100.0, "lay_size": 50.0}, "..."],
 "bet_delay": 5,
 "score": {"sport": "calcio", "minute": 67, "home": 2, "away": 1, "red_home": 0, "red_away": 1, "ht": false},
 "fixture_id": 1234567, "updated_ms": 1791545355689}
{"event_id": "35000002", "...": "...", "inplay": false, "total_matched": 288.8, "bet_delay": 0,
 "score": null, "fixture_id": null, "updated_ms": 1791545355689}
"market_types": [{"market_type": "MATCH_ODDS", "name": "Esito finale (1X2)", "count": 2},
 {"market_type": "BOTH_TEAMS_TO_SCORE", "name": "Goal / No goal", "count": 5},
 {"market_type": "OVER_UNDER_25", "name": "Under/Over 2.5 gol", "count": 2},
 {"market_type": "ASIAN_HANDICAP", "name": "Handicap asiatico", "count": 1}]
```
Estratto tennis:
```json
{"event_id": "35790084", "market_id": "1.401", "inplay": true, "total_matched": 43210.0,
 "bet_delay": 3,
 "score": {"sport": "tennis", "sets": {"p1": 1, "p2": 0}, "games": {"p1": 3, "p2": 2},
           "points": {"p1": "40", "p2": "AD"}, "server": "p2"},
 "fixture_id": null}
{"market_type": "SET_BETTING", "rows": [{"event_id": "35790084", "market_id": "1.402",
  "market_name": "Set Betting", "status": "OPEN", "inplay": true, "total_matched": 900.0,
  "selections": [{"selection_id": 1, "name": "2 - 0", "handicap": 0.0, "back": 3.1, "lay": 3.3,
                  "ltp": 3.1, "back_size": 12.0, "lay_size": 4.0}, "..."]}], "updated_ms": 1791545355696}
```

## 3. Test
Nuovi:
- `Betfair/stream/tests/test_board_programma_2026_10_09.py` — 24 test: chiavi lette = chiavi
  scritte dallo scanner (sorgente di `build_rows`), righe calcio/tennis, intervallo IPS (6 stati),
  score solo in gioco, REST a blocchi da 25 e al piu' ogni 60 s, market_types (calcio/tennis/KO),
  richiesta board_mercato (validazioni, tetto 3, TTL 75 s), push board_mercato (feed/REST/handicap),
  tipo scaduto, canale su WebSocket VERO (senza token, mai in coda; bot e lettore rifiutano),
  un giro alla volta, cadenza condivisa, **`setup_and_run` VERO di calcio e tennis fermato al
  primo sonno del ciclo d'attesa: board pubblicato e richiesta del desktop risposta**.
- `Betfair/stream/tests/test_board_ordini_aggancio_2026_10_09.py` — 15 test: calcio (motore +
  `AutoFollow` veri) aggancio e piazzamento, gia' servibile, tetto pieno, scadenza e nessun
  ordine dopo, runner senza framework, FIFO + paper/live sul client della loro modalita',
  guardia rifatta, errore del giro che non tocca i parcheggiati, cancel/senza auto-follow come
  prima, attesa < timeout della pagina (letto da `frontend/src/lib/localChannel.ts`), runner
  parcheggiato senza motore; tennis (framework/stream VERI del banco dell'iscrizione a caldo)
  aggancio a caldo e piazzamento, senza aggancio come prima, parcheggiato (risposte, aggancio,
  scadenza), guardia e OFF.
Finti: oggetti VERI di betfairlightweight (`MarketCatalogue`, `MarketBook`, `MarketTypeResult`)
dalle risposte grezze; payload dello scanner con le chiavi di `build_rows` e valori dai parser
veri (`parse_score_dict`, `parse_tennis_scores`, `price_pair`, `build_market_block`); cache del
feed = `ScanRowCache` vera con lettura iniettata; canale = `LocalChannel` vero.

Test esistente modificato (rafforzato, non indebolito):
`test_scan_feed_2026_09_09.py::test_board_riga_dal_payload_scanner` — l'uguaglianza ESATTA della
selezione ora include `back_size`/`lay_size` (+ verifica `None` quando il feed non li ha).

Numeri:
- nuovi + vicini (`test_board_*`, motore ordini, auto-follow, motore tennis): 178 passati, 1 saltato.
- suite intera `python -m pytest Betfair/ -q -p no:cacheprovider` (codice finale):
  **11440 passati, 87 saltati, 6 xfailed, 0 falliti** (352 s).

## 4. Falsificazioni
A) I test nuovi sul codice di PRIMA (sorgenti `git checkout HEAD`, test nuovi): tutti rossi
tranne il test di parita' delle chiavi dello scanner (che non dipende dal codice nuovo). In
particolare: «runner tennis parcheggiato: nessun board pubblicato», «runner calcio parcheggiato:
nessun board pubblicato», `/order` -> «market 1.555 non sottoscritto nel runner», runner fermo ->
«runner senza framework attivo», `board_mercato` -> «metodo sconosciuto».
B) 21 mutazioni sul codice NUOVO, ciascuna ROSSA (script `falsificazione_backend.py`,
riproducibile: `python AUDIT_2026-10-09/programma_del_giorno/falsificazione_backend.py`):
M1 volume REST non integrato · M2 correct score non escluso · M3 score fuori gioco · M4 tetto
tipi `>=`->`>` · M5 TTL mai scaduto · M6 board_mercato in coda comandi · M7 giro senza lucchetto
· M8 REST a ogni giro · M9 calcio parcheggiato senza board · M10 tennis parcheggiato senza board
· M11 intervallo invertito · M12 battuta p1/p2 scambiata · M13 `/order` mai agganciato · M14
`/order` mai scaduto · M15 attesa oltre il timeout della pagina · M16 FIFO ignorata · M17
guardia non rifatta all'uscita · M18 parcheggiato senza motore non risponde · M19 tennis mai
agganciato · M20 regole d'apertura saltate da parcheggiato · M21 errore del giro che risponde ai
parcheggiati.

## 5. Limiti noti e divergenze dal contratto
1. **`ht` del calcio**: nel payload dello scanner `ht` e' il BLOCCO Half Time Score (Omega), non
   un booleano. Il contratto chiede `ht: bool|null` = intervallo: lo derivo dallo stato IPS
   (`matchStatus` FirstHalfEnd/HalfTime). Non letto il blocco `ht` (sarebbe un errore §7.1).
2. **`name` dei `market_types`**: `listMarketTypes` non porta nomi; tabella + derivazione dal
   codice (nessuna chiamata in piu'). Se servono i nomi Betfair esatti servirebbe il catalogo di
   ogni tipo (piu' peso): non fatto.
3. **Aggancio entro 7 s**: dal runner PARCHEGGIATO la costruzione del framework puo' superare 7 s
   (il 26/09 i comandi ne hanno richiesti fino a ~10); allora il primo clic riceve
   `in_aggancio … riprova` e il secondo e' immediato (mercato gia' nel piano). Scelta prudente:
   mai un ordine piazzato dopo che la pagina ha smesso di aspettare (10 s). Il frontend deve
   mostrare il motivo e invitare a riprovare.
4. **Tennis con motore tennis spento**: l'aggancio al volo del `/order` usa l'`AgganciaTennis`
   del motore tennis (stesso meccanismo dei comandi); spento (default di codice
   `MOTORE_ORDINI_CANALE_TENNIS`) -> rifiuto esplicito su partita non seguita. Non ho acceso
   l'aggancio senza motore per non aggiungere un thread (`aggancio-comandi-tennis`) non chiesto.
   Va verificato nel `.env` dell'utente se `MOTORE_ORDINI_CANALE_TENNIS=1` (il C-21 del 02/10 non
   lo elenca fra gli accesi).
5. **Ripiego DB** (`request_betfair_live_order` / `request_tennis_live_order`): NON aggancia;
   errore esplicito «non sottoscritto». Scelta prudente: la coda DB e' condivisa con altri
   produttori e una riga 'pending' parcheggiata cambierebbe la semantica della coda. Il ripiego
   DB scatta solo senza canale utilizzabile (canale giu' o senza token), cioe' quando il board
   (che arriva SOLO dal canale) non e' nemmeno a schermo.
6. **Calcio con motore spento**: dentro il framework resta il rifiuto «non sottoscritto»
   (l'`AutoFollow` esiste solo col motore). In produzione il motore e' acceso (C-21).
7. **Tennis, framework con ordini OFF**: senza worker ordini nessuno drena il 47332 mentre il
   framework gira (comportamento di prima, non toccato); da parcheggiato invece ora si risponde.
8. **Volume**: `total_matched` e' quello REST, vecchio al piu' 60 s; prima della prima REST resta
   quello del feed (o `null`).
9. **Primo push `board_mercato`**: arriva al giro successivo alla richiesta, cioe' entro
   `LIVE_BOARD_POLL_SEC` (10 s). Non ho accelerato il giro (cadenza del worker invariata).
10. **Costo REST**: MATCH_ODDS ora <= 3 `listMarketBook`/60 s sempre (prima solo per i non
    coperti); ogni tipo richiesto <= 1 catalogo/300 s + <= 3 book/60 s; tetto 3 tipi; +1
    `listMarketTypes`/300 s. Tutto solo con il desktop collegato.
11. Il ciclo d'attesa del calcio fa il giro del board in linea: ogni 10 s, quando scade la REST
    (60 s) o il catalogo (300 s), il giro puo' durare quanto le chiamate REST e ritardare di
    tanto il controllo dei follow (di norma 2 s). Nessun thread nuovo, come chiesto.

## 6. Commit
Ramo del worktree, commit unico (vedi messaggio). Non pushato.

## 7. Correzione: modo ordini da parcheggiato (revisione del coordinatore)

DIFETTO (trovato in revisione): il tabellone abilita il box quota solo se conosce il modo
ordini EFFETTIVO dal canale (topic `modo_ordini` o `hello.modo_ordini`; `hello.mode` e' il solo
tetto del .env). Entrambi i runner rileggevano i settings e pubblicavano il modo SOLO dentro i
worker di flumine: calcio `live_order_worker._process_once` -> `_refresh_settings` ->
`_pubblica_modo_ordini_se_cambiato`; tennis `tennis_live_order_worker` ->
`guardie_tennis.aggiorna_impostazioni` -> `pubblica_modo_ordini_se_cambiato`. Col runner
PARCHEGGIATO (il caso normale del tennis, e del calcio senza auto-follow) nessuno li leggeva:
«ORDINI: NON NOTA», conferma spenta, dal tabellone non si puntava mai.
VERIFICA della freschezza (stesso difetto, confermato sul codice di 69a4ca7f):
- tennis: `servi_comandi_da_parcheggiato` decideva con `_low._SETTINGS` mai letto
  (kill-switch = False di default: un place a freno tirato chiedeva l'aggancio) e con
  «Ordini reali» non letto (= PAPER di default: una scelta OFF non fermava l'aggancio);
- calcio: la copia dei settings che il motore ordini controlla all'uscita dall'aggancio
  (`eta_settings_s`, kill-switch, `modo_ordini.valore_db`) era quella dell'avvio (o nessuna):
  dopo 30 s il modo scadeva a OFF e l'eta' superava i 10 s del motore (rifiuto `M_SETTINGS`
  finche' il worker della coda non rileggeva). Fail-closed, ma il tabellone non lo sapeva.

CORREZIONE (nessun thread/processo nuovo, nessuna lettura in piu' col framework):
- Calcio `Betfair/stream/runner.py:1616` `_attesa_impostazioni`, chiamata per PRIMA da
  `_attesa_board_e_canale` (`:1662`, gia' nei due rami del ciclo d'attesa `:2879`, `:2935`):
  STESSO cancello del worker (`_LOW._modo_processo()` OFF -> inerte, nessuna lettura), STESSA
  dichiarazione d'avvio del worker guardato a guardia disarmata (`:1638`
  `_dichiara_modo_ordini_all_avvio`, no-op quando gia' fatta, suo orologio da 10 s), STESSA
  funzione `_LOW._refresh_settings(sb)` (che pubblica `modo_ordini` + hello al cambio) con lo
  STESSO orologio di cadenza del worker (`:1647` `_LOW._throttled("settings_refresh", 1.0)`):
  nel passaggio parcheggiato -> framework il primo giro del worker NON rilegge (e viceversa).
  Supabase non disponibile -> giro saltato come nel worker; ogni eccezione contenuta e loggata.
- Tennis `Betfair/stream/tennis_live/tennis_runner.py:3156` `_attesa_impostazioni`, chiamata
  da `_attesa_board_e_canale` (`:3151`) PRIMA di `servi_comandi_da_parcheggiato` (kill-switch e
  modo freschi per la decisione): STESSO cancello (`_runner_mode()` OFF -> inerte), STESSA
  funzione e STESSO orologio del worker ordini tennis (`:3177`
  `_gt.aggiorna_impostazioni(tennis_db.get_tennis_client())`, `_IMPOSTAZIONI_RILETTE` da 1 s),
  che pubblica lo stato del TENNIS (`stato_tennis`, `sport: "tennis"`), mai quello del calcio
  (la funzione del calcio non pubblica fuori dal 47331). Eccezioni contenute e loggate.

TEST nuovi: `Betfair/stream/tests/test_modo_ordini_parcheggiato_2026_10_09.py` (13 test).
Harness del 09/10 riusati (`setup_and_run` VERO fermato al primo sonno, `_Canale` =
`LocalChannel` vero col publish registrato); riga di `get_live_settings` con le chiavi del vero,
RPC `live_order_mode_avvio` come in `test_modo_ordini_ui_2026_09_24`.
- `test_runner_calcio_parcheggiato_pubblica_modo_ordini`: `setup_and_run` calcio PAPER, nessuna
  partita -> dopo un giro d'attesa topic `modo_ordini` e `hello.modo_ordini` con `effettivo`
  PAPER letto, `hello.mode` resta il tetto; chiamate DB = dichiarazione d'avvio + UNA lettura.
- `test_calcio_parcheggiato_kill_switch_e_modo_freschi`: freno della UI letto
  (`_db_kill_switch`), eta' < 1 s, modo effettivo letto; rilascio + OFF visti al giro dopo.
- `test_calcio_nessuna_doppia_lettura_nel_passaggio_al_framework`: due giri d'attesa nello stesso
  secondo = 1 lettura; poi il `_process_once` VERO del worker della coda non rilegge.
- `test_calcio_dichiarazione_d_avvio_riprovata_da_parcheggiato`: dichiarazione d'avvio fallita
  all'avvio -> a guardia armata non si dichiara (modo OFF), a guardia disarmata si'.
- `test_runner_tennis_parcheggiato_pubblica_modo_ordini`: `setup_and_run` tennis col tetto LIVE
  e «Ordini reali» LIVE in questo avvio -> `modo_ordini` `effettivo` LIVE (senza lettura sarebbe
  PAPER di default), `sport: "tennis"`, nell'hello.
- `test_tennis_parcheggiato_kill_switch_e_modo_dai_settings` [freno tirato / OFF]: il place da
  parcheggiato (con aggancio disponibile) e' rifiutato col motivo, nessun aggancio chiesto.
- `test_tennis_nessuna_doppia_lettura_nel_passaggio_al_framework`: la riga del worker ordini
  tennis subito dopo il giro d'attesa non rilegge.
- `test_calcio_tetto_off_nessuna_lettura`, `test_tennis_tetto_off_nessuna_lettura`,
  `test_calcio_ciclo_d_attesa_non_cade`, `test_tennis_ciclo_d_attesa_non_cade`,
  `test_calcio_e_tennis_non_si_mischiano` (47332 solo il tennis col suo tetto, 47331 solo il
  calcio).

FALSIFICAZIONI
A) Test nuovi sul codice di 69a4ca7f (sorgenti dei due runner da `git show HEAD:`, test nuovi):
   **9 rossi su 13** (i 2 `setup_and_run` pubblica-modo, kill/modo calcio, kill/modo tennis x2,
   doppia lettura calcio e tennis, dichiarazione d'avvio, non-si-mischiano). Messaggi: «runner
   calcio parcheggiato: modo_ordini mai pubblicato (NON NOTA)», «runner tennis parcheggiato:
   modo_ordini mai pubblicato (NON NOTA)», `assert 0 == 1` sulle letture. I 4 verdi sono le
   guardie di regressione gia' vere prima (tetto OFF x2, ciclo che non cade x2), falsificate
   dalle mutazioni M4, M5, M11, M12 qui sotto.
B) 13 mutazioni sul codice NUOVO, **13 rosse**, sorgenti verificati identici dopo ogni giro
   (`python AUDIT_2026-10-09/programma_del_giorno/falsificazione_modo_parcheggiato.py`):
   M1 calcio senza rilettura · M2 orologio diverso dal worker · M3 nessuna cadenza · M4 nessun
   cancello OFF · M5 eccezione che esce dal ciclo · M6 dichiarazione d'avvio non riprovata ·
   M7 dichiarazione anche a guardia armata · M8 tennis senza rilettura · M9 settings riletti
   DOPO i comandi · M10 orologio scavalcato (`forza=True`) · M11 nessun cancello OFF · M12
   eccezione che esce dal ciclo · M13 tennis con la funzione del calcio (pubblica solo sul 47331).

NUMERI
- file toccati + vicini (nuovo, board 09/10 x2, punto 6, modo UI, modo tennis, R3 freno):
  176 passati.
- `test_modo_ordini_parcheggiato_2026_10_09.py`: 13 passati.
- suite intera `python -m pytest Betfair/ -q -p no:cacheprovider` (codice finale):
  **11453 passati, 87 saltati, 6 xfailed, 0 falliti** (378 s; = 11440 di prima + 13 nuovi).

LIMITI / RISCHI RESIDUI
1. Tetto OFF: come col framework (worker inerti) nessuna lettura e nessun `modo_ordini`: il
   tabellone resta «NON NOTA» (il box sarebbe comunque inutile, ogni ordine e' rifiutato). Se si
   vuole «OFF» esplicito serve una scelta (pubblicare senza leggere), non fatta.
2. Ramo «follow presenti ma nessun mercato» del ciclo d'attesa: dorme 15 s, quindi li' la copia
   dei settings puo' avere fino a ~15 s (> 10 s del motore). Il modo resta valido (30 s) sul
   tabellone; all'aggancio il worker della coda rilegge al suo primo giro (cadenza scaduta), il
   caso peggiore e' un rifiuto `M_SETTINGS` dichiarato, mai un ordine con dati vecchi.
3. Calcio, guardia d'avvio ARMATA (ripresa fallita all'avvio): da parcheggiato la ripresa NON si
   riprova (difetto preesistente, fuori da questo incarico: la riprova la fa solo il worker
   guardato); i settings si leggono comunque (lo fanno anche risk/daily-stop col framework), la
   dichiarazione d'avvio no (come il worker guardato). Da valutare a parte.
4. Il giro d'attesa del calcio ora fa una RPC `get_live_settings` ogni ~2 s (cadenza del ciclo,
   sotto il tetto di 1/s del worker) solo con tetto PAPER/LIVE: e' la stessa lettura che il
   worker fa ogni secondo col framework vivo.
