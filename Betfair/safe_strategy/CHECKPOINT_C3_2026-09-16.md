# CHECKPOINT C.3 — SAFE CALCIO SUL BANCO (16/09/2026) — **FATTO**

> Punto di ripresa del delegato C.3. Stato al termine del lavoro: tutto quello
> che segue e' stato eseguito e verificato. Suite: `python -m pytest
> Betfair/safe_strategy Betfair/stream -q -p no:cacheprovider` → **2424 verdi,
> 0 rossi**. Working tree coerente: nessun file esistente modificato (le
> falsificazioni sono state rimesse a posto e verificate).

## 1. I file consegnati

| file | righe | che cosa e' |
|---|---|---|
| `Betfair/safe_strategy/certificazione.py` | 1663 | **58 controlli**, uno per voce di `RISCONTRO_CALCIO_2026-09-14.md` / `SPEC_STRATEGIA_S.md`. I numeri della SPEC sono COSTANTI (`SPEC_BASE:63`, `SPEC_ESATTO`, `SPEC_PUNTA`): letti dai params, il controllo confronterebbe il parametro con se stesso. |
| `Betfair/safe_strategy/tools/replay_registrazioni.py` | ~1480 | il replay sul banco comune, **11 scenari**, `certifica_scenario` con la firma del registro. |
| `Betfair/safe_strategy/tests/test_certificazione_c3_2026_09_16.py` | ~1000 | **120 test verdi** (sano tace / violazione certa scatta + introspezione del DB + segmento `pytest -m cert`). |

Nessuna modifica a file esistenti. Il registro (`registro_bot.py`) lo ha
collegato il coordinatore.

## 2. Partita di riferimento e classifica delle partite nelle bande

Scansione del corpus con le funzioni VERE (`scanner.freeze_pre_ko`,
`scanner.selection_sides`, `Scanner.apply_score_state`,
`engine.favorite_side/in_range/score_in_list_*`) — script
`scratchpad/cerca_partite_safe.py`, esito in `scratchpad/corpus_safe.json`.
39 registrazioni con raw (`_synth_*` escluse).

- **14 hanno il `pre_ko` INCOMPLETO** (manca un back del 1X2 prima del fischio):
  su quelle BASE e PUNTA non scattano mai. E' il difetto 19 del catalogo nella
  sua forma di DATO, non di codice.
- **BASE** (favorita 1,40-1,80 **e** sfavorita 4-8 **e** punteggio ammesso dal 55'):
  1. **35797769** COMPLETE 95,4 % — fav home 1,64 / dog away 5,40 — finale 2-1 ← **SCELTA**
  2. 35768297 PARTIAL 80,3 % — fav 1,66 / dog 5,70 — finale 2-1
  Nessun'altra in tutto il corpus.
- **PUNTA** (sfavorita 4-8 + favorita avanti 2-0/3-1/3-0 dal 66'): **NESSUNA**.
  Le partite con quel punteggio hanno la sfavorita a 9,2-11,5, fuori banda.
- **ESATTO** (0-0/1-0/1-1/2-1 dal 48'): 13 candidate; migliori 35780184 (99,1 %),
  35781607 (99,1 %), 35774000 (98,1 %), 35797538 (98,0 %), 35777617 (97,1 %).
- ⚠️ Nel brief «ESATTO 3-1/3-0» e' l'elenco della PUNTA: ho misurato entrambi
  con gli elenchi della SPEC (§2 e §4).

**35760084** resta la prima partita di riferimento ma **non e' una partita da
BASE**: pre-KO 1,35 / 9,2, fuori da entrambe le bande (`favPre:no` e `dogPre:no`
su tutte e 3.060 le valutazioni). **35797769 e' la seconda partita di
riferimento calcio per Safe.**

## 3. Stato dei tre controlli chiesti in corsa

### T12 — «mai due lay a mercato sulla stessa selezione», **ristretto al BOT**
- `certificazione.py`: `_e_del_bot` e `_riga_del_ref` (contano solo le righe
  `origin='auto'` e gli ordini riconducibili a esse), `_lay_in_volo`, `_t12`.
- Chiarimento dell'utente onorato: due «Investi» manuali **non** sono una
  violazione del bot. Scenario `due-lay` su 35797769: T12 **non ha nemmeno un
  caso e tace**; le gambe del bot restano identiche.
- Conta anche le lay **gia' abbinate**: col FOK due lay non coesistono mai «a
  mercato», ma abbinate due volte la responsabilita' e' gia' raddoppiata.
- **Manca**: due lay AUTOMATICHE sulla stessa selezione non sono provocabili sul
  banco senza alterare la strategia (`bot_service.py:4253` `esatto_lato_gia_aperto`
  + indice unico `uq_safe_trades_signal`). Rosso provato solo a livello unitario.

### T13 — «le operazioni manuali non alterano le decisioni del bot»
- `_t13` + scenario `manuale-e-bot` (riga manuale VIVA sulla STESSA selezione che
  il bot banca, Correct Score 9063254).
- **Verde e sollecitato.** Gambe del bot identiche allo scenario `base`: 335
  segnali ESATTO, size 2,00, prezzi 32,0/34,0, stessi stati.
- Il bot non puo' toccare una riga manuale per **TRE barriere indipendenti**:
  `bot_service.py:2013` (`origin != 'auto'`), `bot_service.py:2015` (`strategy`
  non in `EXIT_STRATEGIES`; il manuale nasce `strategy='manual'`,
  `bot_service.py:1619`), `exits.py:879` (`decide` non ha nessun ramo per
  'manual').
- **Falsificazione sul replay: ⊘** — tolte DUE barriere su tre il bot continua a
  non toccarla (`scratchpad/falsifica_t13.py`, provato). Il rosso e' provato a
  livello unitario (4 test).
- **REPERTO (non corretto)**: le USCITE filtrano `origin`, i CAP no.
  `bot_db.py:130` (`open_trades`) e `bot_db.py:348` (`aggregate_rows`) non
  filtrano per origine → le righe del trader entrano in `build_risk_ctx`
  (`bot_service.py:3886`) e pesano su `max_open_trades`, sul cap di
  responsabilita' per evento e sugli aggregati di giornata **del bot**
  (misurato: 32,80 EUR di responsabilita' manuale dentro i cap del bot).

### T14 — «dopo il cash-out globale il bot non fa altro» → **VIOLATO (x282)**
- `_t14` + scenario `cashout-globale` (una richiesta `cashout` per ogni riga
  viva, cioe' il percorso VERO `process_requests` → `_request_cashout:1709`).
- **Safe NON ha un cash-out globale**: le sue richieste sono `place`, `cashout`
  (per singolo `trade_id`) e `cancel` (`bot_service.py:1466-1470`).
  `cashout_event`/`cashout_all` vivono nella coda del runner
  (`frontend/src/lib/liveOrders.ts:284,306` → `live_order_worker`) e **non
  passano dalle tabelle di Safe**: chiudendo da li', `safe_strategy_trades`
  resta 'open' e il bot crede di avere ancora la posizione.
- **Non esiste nessuno stato per evento «chiuso dall'utente»** (cercato: zero
  occorrenze in `Betfair/safe_strategy/`).
- Misurato su 35797769: dopo la chiusura del trader il bot ha **aggiunto una
  gamba automatica da 0,04 EUR** sulla posizione gia' chiusa e ha continuato a
  far girare la macchina delle uscite (`exit_hold` x282). Non apre righe nuove
  solo perche' la chiave del segnale non cambia; con un gol cambierebbe
  (`bot_db.py:192` blocca solo la stessa chiave).
- **Patch proposta, NON applicata** (e' comportamento, decide l'utente): kind
  `cashout_event` in `process_requests` (`bot_service.py:1466`) che chiude tutte
  le righe vive dell'evento e scrive un marcatore per evento letto da
  `scan_and_place` (`bot_service.py:4140`) prima della riserva e da
  `_exit_candidates` (`bot_service.py:1999`).

### Falsi positivi esclusi prima di accusare (PROCESSO §6.7)
1. J1/J3/J6 leggevano la riga **dentro** `execution.place`, cioe' prima della
   conferma: giudizio spostato a fine giro (`_certifica_ordini`).
2. T8 accusava il percorso manuale, che non passa da `strategy_modes`.
3. T13/T14 contavano i kind `cashout`, `place`, `exit_wait`, che
   `execution.py:1376` scrive **anche** per il bottone del trader: ristretti a
   `exit`/`exit_retry`/`exit_hold`. T13 e' passato da 1-2 violazioni a 0.

## 4. Gli 11 scenari

`base` · `cap-stretto` · `bot-fermo` · `esiti-ignoti` · `feed-stantio` ·
`riavvio` · `paper` · `ordini-manuali` · `due-lay` · `manuale-e-bot` ·
`cashout-globale`. Cambiano SOLO parametri, freschezza del feed, guasti
iniettati o richieste della UI: mai la partita, mai i prezzi, mai la strategia.

## 5. Replay eseguiti — numeri e comandi per rifarli

Comando (a registro collegato):
`python -m Betfair.stream.backtest.certifica safe_calcio <id> --scenari <...> --diario <file>`

| partita | scenari | tick | giri | ordini | violazioni |
|---|---|---|---|---|---|
| 35760084 | tutti e 9 | 61.292 | 3.556 | 0-3 | **60**, tutte T12 nello scenario `due-lay` *(prima della restrizione al bot: oggi tacerebbe)* |
| 35797769 | `base` | 161.948 | 6.486 | **3** | 335, tutte **E10** |
| 35797769 | `manuale-e-bot` | 161.869 | 6.484 | 4 | 335 (E10) — **T13 verde** |
| 35797769 | `cashout-globale` | 161.980 | 6.485 | 3 | 336 (E10) + **282 T14** |
| 35797769 | `due-lay` | 161.683 | 6.480 | 6 | 335 (E10) — **T12 tace** |

35797769 `base`: 335 segnali ESATTO, lay «Altro risultato Casa» a 32,0 poi
chiusura back a 34,0, 2 fill per 4,00 EUR, 189 uscite valutate.
Controlli sollecitati **in piu'** rispetto a 35760084: **E4, E8, E9, E10, T1,
T4, T8**. «Non lo so» scesi da 25 a **19 su 58**.

## 6. Test

120 verdi in `test_certificazione_c3_2026_09_16.py`: per ogni voce il caso sano
che TACE e la violazione certa che SCATTA; 42 test di introspezione sulle firme
di `bot_db.py`/`db.py` contro `DbSafeMemoria`; 14 su T12/T13/T14; un segmento
`pytest -m cert` (9 s, campione 35823616).

Falsificazioni provate sul **replay vero** (difetto messo e tolto, file
ripristinato verificato), `scratchpad/falsifica_c3.py`:
1. `engine.DEFAULT_PARAMS["base"]["favPreMin"]` 1,4 → 1,2 → **B6 rosso x3064**;
2. `_execute` scrive `price=row["price"], size=row["size"]` (catalogo §7.1/§7.3)
   → **J1 e J3 rossi**;
3. T12 (prima della restrizione) provocato dallo scenario `due-lay` → **60 rossi**.
⊘ dichiarati: T13 (tre barriere, vedi §3), T12 su righe automatiche.

## 7. Che cosa resta aperto

- **PUNTA non e' certificabile su nessuna registrazione del corpus** (nessuna
  partita con sfavorita 4-8 e favorita avanti di due gol dal 66').
- **BASE**: 35797769 ha le bande pre-match giuste ma la quota live della
  favorita non entra mai in 1,20-1,34 (`favLive:no` x3507) → ingresso mai
  esercitato. Serve il replay massivo.
- E10 (⊗ «selezione aggiuntiva» del Risultato Esatto) resta non implementata:
  335 violazioni per partita, gia' nota dal RISCONTRO del 14/09.
- ⊘ residui: minimo .it e place-and-trim (flumine non ha minimo), combo /
  opportunita' / anomalie (fuori perimetro C.3), settlement `won/lost/void`,
  multi-evento e concorrenza (§6.6), tennis (C.4).
- Reperti per il banco (C.0): `MercatoFlumine.place_order_live` non popola
  `size_requested`/`size_remaining` nel `PlaceResult`; `DbMemoria.log` ha tre
  argomenti mentre `bot_db.log` ne ha due; `save_event_model` chiamato dal
  servizio e assente dal banco.
