# BANCO - l'annullo sul canale confermato come da Betfair (reperto M1, 30/09)

Delegato di costruzione, worktree `agent-acaf761dc3a83d49a`, base = master `117f5a3` +
`MIKE_BOT_ONDATA_2.patch` (commit temporaneo `e9c60a2` nel worktree, fuori dalla patch).
Patch: `AUDIT_2026-09-30/BANCO_ANNULLO_CONFERMATO.patch` (solo il mio diff, verificata con
`git apply --cached --check` sulla base). Nessun commit, nessun file di Mike toccato.

## Verdetto in una riga

**Difetto del BANCO, non del bot.** Il socket NON e' chiuso al momento dell'annullo:
l'annullo arriva al motore vero, e' accettato, ma flumine della simulazione lo mette in coda
fino al book successivo di quel mercato, e il book successivo non arriva mai finche' il bot
aspetta (il thread del bot e' il thread del replay). Il bot aspetta 3 s d'orologio, non vede
l'esito e va in riconciliazione. In produzione (paper col runner, live REST) l'annullo e'
confermato.

## 1. La catena dell'annullo (file:riga, misurata)

Misura: spia su `execution._annulla_via_canale` nel replay `base` (solo lettura, script
fuori dal codice), riga per riga:

```
DIAG annullo bet=100000000004 disponibile=True collegato=True
DIAG coda prima=[]
DIAG coda dopo=[('OrderPackageType.CANCEL', '1.259475537', 0.0, 0.17)]
DIAG ack={'mike-c100000000004': {... 'accettato': True, 'motivo': None ...}}
     evento_bet={... 'size_remaining': 10.12, 'size_cancelled': 0.0, 'status': 'CANCELLING', 'fase': 'inviato' ...}
DIAG esito=None dt=3.01s t_mercato=2026-06-30T16:03:31.193000+00:00
CRITICAL:mike:[mike] 35760084: annullo NON confermato su ko_green-0-4 (bet 100000000004) -> riconciliazione
```

1. **Chi manda**: `mike/service.py:5471` (`sul_runner`: riga paper con `canale_ref`) ->
   `:5492` `porta_kw = {"porta": MP.vista(), "mode": "paper"}` -> `:5493`
   `X.annulla_su_betfair(...)`.
2. `safe_strategy/execution.py:445` (porta `via_canale`) -> `_annulla_via_canale` ->
   `:630` `porta.invia(comando)` (ref `mike-c<bet_id>`, `mike/porta_ordini.py` `VistaMike`
   -> `PortaCanale.invia`, `safe_strategy/porta_ordini.py:699`) -> `WsBanco.send` ->
   `PortaBanco._dal_socket` (`stream/backtest/porta_banco.py:642`) -> `MotoreOrdini._gestisci`
   (`:670`) -> `motore_ordini.py:438` (cancel) -> `live_order_worker._dispatch` ->
   `Market.cancel_order` di flumine: ordine in `CANCELLING`, pacchetto CANCEL in
   `handler_queue` con `simulated_delay` = `config.cancel_latency` = 0,17 s. **Ack accettato**.
3. **Chi rilegge**: `execution.py:636` `porta.attendi_esito_bet(bet_id, 3.0)`
   (`porta_ordini.py:722`): aspetta un evento `order` terminale o a residuo zero.
4. **Perche' `riletto` e' falso (esito `None`)**: nella simulazione
   `FlumineSimulation.process_order_package` (`flumine/simulation/simulation.py:153-155`)
   mette il pacchetto in coda; lo esegue `_check_pending_packages(market_id)` SOLO all'arrivo
   di un book di quel mercato (`banco_comune.py:1516`, come `simulation.py:113-115`). Il bot
   e' dentro `process_market_book` del replay: nessun book arriva, flumine non annulla, lo
   specchio non ha niente da dire, dopo 3 s d'orologio `attendi_esito_bet` torna `None` ->
   `_annulla_via_canale` torna `None` -> `service.py:5495` `confermato=False` -> `:5510`
   CRITICAL e `STATUS_RECONCILE`. L'ora di mercato resta FERMA per tutti i 3 s (sopra:
   `t_mercato` 16:03:31.193 prima e dopo). Al giro dopo il book arriva, flumine annulla, lo
   specchio manda `annullato`, e la riconciliazione risolve la riga (`no_fill`
   `runner_annullato`, 16:03:32.382).
5. **Il "socket del banco chiuso" NON e' la causa**: al momento dell'annullo
   `disponibile=True collegato=True`. Il WARNING e' lo SMONTAGGIO di fine replay:
   `trasporto._smonta` (`trasporto.py:383-392`) chiama `client.ferma()` e `pb.metti_giu()`,
   `WsBanco.recv` solleva `ConnectionError("socket del banco chiuso")`
   (`porta_banco.py:189-195`) e il thread del client lo scrive una volta
   (`porta_ordini.py:620`). Nel referto `mike_tutti_G_bot.txt` le righe sono mescolate perche'
   stderr di 3 processi della pool si intreccia; nei miei replay `base` (un processo) il
   WARNING non compare affatto e il CRITICAL si'.

## 2. In produzione l'annullo e' confermato?

**Paper (runner vero)**: si'. Il runner e' un `Flumine` LIVE: `BaseFlumine.process_order_package`
(`flumine/baseflumine.py:217-219`) manda il pacchetto SUBITO a `execution.handler`; il client
paper del runner e' `BetfairClient(paper_trade=True, order_stream=True)` (`stream/runner.py:2123-2131`),
quindi `SimulatedExecution.handler` lo esegue sul thread pool (`simulatedexecution.py:27-28`),
dopo `sleep(cancel_latency)` annulla sul book CORRENTE (`:55-70`, nessun book nuovo richiesto)
e lo `SimulatedOrderStream` (ogni `order_streaming_timeout` = 0,25 s,
`streams/simulatedorderstream.py:28-35`, aggiunto da `streams.py:90-93` per `paper_trade`)
porta l'ordine a `process_orders` -> specchio -> motore -> evento `annullato` sul canale:
circa 0,2-0,5 s, dentro i 3 s del bot.
Test con oggetti veri: `test_in_produzione_paper_l_annullo_si_conferma_senza_book_nuovi`
(registrazione vera, `PortaBanco`/`MotoreOrdini`/client di Mike veri, `annulla_su_betfair` di
produzione; le due righe di flumine LIVE prese dalla classe `BaseFlumine` e `paper_trade`
acceso come nel runner; attesa del banco SPENTA; un filo a 0,25 s fa lo specchio come lo stream
ordini): annullo `ok`, `riletto`, `size_cancelled=2.0`, in meno di 2 s, **zero book passati**.
Verde anche PRIMA della correzione (non dipende dal banco).

**Live (REST)**: la riga live non passa dal canale (`service.py:5490-5492`: `porta_kw` solo per
`sul_runner`): `omega_market.cancel_order_live` (`omega_market.py:1227`) chiama `cancelOrders`
e RILEGGE l'ordine (`riletto`), sincrono, senza dipendere dallo stream. Non tocca questo difetto
(non verificato contro Betfair vero: vedi sotto).

## 3. La correzione (minima, nel banco)

- `stream/backtest/porta_banco.py`: `PortaBanco.attendi_esecuzione` (None di serie) e
  `_attendi_annulli()`, chiamata in `_dal_socket` subito dopo `_gestisci` di un comando
  `cancel`: per ogni mercato con un pacchetto CANCEL in coda chiama l'attesa del motore del
  replay, **solo pacchetti CANCEL**. Nessun esito inventato: annulla flumine, rilegge lo
  specchio, l'evento lo manda il motore vero.
- `stream/backtest/banco_comune.py`: `MotoreReplay.attendi_esecuzione(market_id, tipi=None)`:
  `tipi` filtra i pacchetti attesi (None = identico a prima, la coda). Serve perche' sul canale
  un PLACE dello stesso mercato puo' essere in volo col bet delay e l'annullo non deve aspettarlo.
- `stream/backtest/trasporto.py` (`_monta_canale`): `pb.attendi_esecuzione = motore.attendi_esecuzione`.
- `stream/backtest/trasporto_rapido.py` (`BancoRapido.monta_porta`): lo stesso aggancio, perche'
  il profilo rapido resti uguale al replay.

La regola del tempo e' QUELLA della coda (`MercatoFlumine.cancel_order_live` ->
`_attendi_betfair` -> `attendi_esecuzione`, `banco_comune.py:673-683`): il tempo di mercato
scorre finche' `elapsed_seconds > simulated_delay` (0,17 s), poi si esegue sul book di quel
momento; i book passati vanno a flumine e allo scanner, non al giro del bot. Bot, strategia,
`engine.py`, `service.py`, `certificazione.py`, `replay_registrazioni.py`: non toccati.

## 4. Referto `base` prima/dopo

Comando (ambiente neutro di `replay_mike.sh`), una sola coppia, ~1 minuto ciascuno:
`python -m Betfair.stream.backtest.certifica mike 35760084 --scenari base --trasporto canale --worker 0 --data-dir .../_live_raw`

Controllo di partenza: la sezione `[base]` del mio «prima» e' **identica riga per riga** a quella
di `mike_tutti_G_bot.txt` (tolto il tempo).

`diff prima dopo` (tutto il resto, compresa la tabella dei 43 controlli, e' identico):

| voce | prima | dopo | perche' |
|---|---|---|---|
| CRITICAL «annullo NON confermato» | 1 (ko_green-0-4) | **0** | la correzione |
| `tick=` | 56226 | 56223 | 41 book passano mentre il bot e' fermo sull'annullo (0,28 s di mercato): il bot non li vede, come sulla coda; 3 giri in meno alla sua cadenza. `decisioni=5863` e `azioni=6` identiche |
| attivita' `no_fill` | x3 | x2 | prima la riga si chiudeva dalla riconciliazione (`no_fill runner_annullato`); ora dall'annullo confermato (`cancel_esito confermato=true`), che non scrive `no_fill` |
| motivi dichiarati | `runner_scaduto x2, punteggio_assente_tornato x1, runner_annullato x1` | `runner_scaduto x2, punteggio_assente_tornato x1` | stessa causa: la nota conta solo `error/reconcile_pending/skip/no_fill` |
| `bet delay: N book passati mentre i piazzamenti aspettavano Betfair` | 0 | 41 | il contatore `motore.pompati` conta anche l'attesa dell'annullo (come fa gia' la coda). L'etichetta dice "piazzamenti": e' in `replay_registrazioni.py`, fuori dal mio perimetro |
| tempo | 52,3 s (totale 53,6) | 59,8 s (totale 61,1) | rumore della macchina: le due corse diagnostiche identiche hanno dato 61 s (prima) e 57 s (dopo). L'annullo ora NON consuma piu' i 3 s d'orologio morti |

**Identici** (verificato sul diff): esito OK, 0 violazioni, `ordini reali piazzati: 5`, righe
`{'open': 2, 'error': 3}`, fill `2 abbinamenti su 2 ordini per 22.63 EUR (prezzi [1.33, 1.71])`,
**P&L -14,17**, proposte (`uscita_proposta x18`, `decaduta x16`), stati, tutti i motivi di
decisione, tabella dei controlli (J4 x1, B3 x0, D3 x975, K1-K4 x5854, ...).

**La riga `ko_green` (trade 4)**, cronologia dal servizio (spia su `DbMemoria.log`):

- prima: 16:03:31.193 `cancel_esito confermato=false` -> gamba `pending_reconcile` -> 16:03:32.382
  `no_fill runner_annullato` -> riga `error`, meta `reason=runner_annullato`,
  `esito_ordine=ritirato_da_noi`;
- dopo: 16:03:31.474 `cancel_esito confermato=true size_cancelled=10.12 size_matched=0.0` ->
  gamba `cancelled` -> riga `error`, meta `reason=cancelled_by_engine`, `esito_ordine=ritirato_da_noi`.

Il motivo NON e' piu' `runner_annullato`: e' `cancelled_by_engine`, che e' cio' che il servizio
scrive su un annullo confermato (`service.py:5528-5531`, identico al ramo live REST). Coerente:
ritirato da noi, confermato, 10,12 annullati, 0 abbinati. Lo segnalo perche' il brief si
aspettava `runner_annullato`.

**J4 e B3**: J4 in `base` resta x1 perche' il suo `quando` scatta sull'AZIONE `cancel`
(`certificazione.py:660-663`), non sulla riconciliazione: in `mike_tutti_G_bot.txt` J4 x21 =
esattamente le 21 azioni di annullo. B3 in `base` era gia' x0. La riconciliazione in `base`
durava un solo giro (1,19 s di mercato) e si risolveva prima della decisione successiva.

**La finestra dei 3 minuti al fischio in `base`: NON cambia, e non poteva cambiare.** L'annullo
di `base` e' quello dell'uscita `ko_green-0-4` A FINESTRA GIA' SCADUTA ("uscita non abbinata in
3': copertura Over 4.5", 16:03:31). La banca pre-partita `under_green-0-2` era gia' morta
(LAPSE, `runner_scaduto` 16:00:25) prima del fischio (16:00:30), quindi `_decide_ko_green` non ha
aspettato nessuna banca. Effetto dell'annullo confermato su `base`: la copertura parte al giro
dopo in entrambi i casi (16:03:32.382 prima, 16:03:32.485 dopo), stesso prezzo 1,33 e size
12,63, abbinata 16:03:37.987 / 16:03:38.609; P&L identico. Il caso M1 della finestra consumata
riguarda la riga `under_green-0-2` di UN altro scenario di `tutti`: non l'ho rieseguito (vedi
sotto).

## 5. Test e falsificazione

Nuovo: `Betfair/stream/tests/test_banco_annullo_confermato_2026_09_30.py` (6 test, registrazione
vera 35760084, oggetti veri; unico finto: i pacchetti del test 6, con le stesse chiavi del vero
`market_id/package_type/simulated_delay/elapsed_seconds`).

Prima della correzione: 5 rossi su 6 (1 rosso con la firma del replay: `annulla_su_betfair`
torna `None`), verde solo quello di produzione, che non dipende dal banco. Dopo: 6 verdi.

Falsificazione (`_diag_annullo/falsifica.py`, ripristino dalla copia in memoria, md5 di
`git diff` e del test identici prima e dopo):

| mutazione | test | esito |
|---|---|---|
| F1 nessuna attesa dell'annullo in `_dal_socket` | confermato_e_riletto | ROSSO (`None`) |
| F2 il replay non aggancia l'attesa | montaggio del canale | ROSSO |
| F3 l'attesa ignora `tipi` | solo annulli / PLACE in volo | ROSSO |
| F4 il banco "inventa" l'annullo (residuo azzerato a mano) | rifiutato da flumine | ROSSO (`ok=True`) |
| F5 niente stream ordini nel runner paper | produzione | ROSSO (`None`) |
| F6 attesa di serie fuori dal replay | porta senza motore | ROSSO |

Suite (ambiente neutro): `Betfair/stream/tests` 3155 passed, 25 skipped; `Betfair/mike` 1301
passed; `Betfair/safe_strategy/tests` + `Betfair/omega/tests` 2442 passed, 5 skipped, 1 xfailed.
Il profilo rapido (`test_profilo_rapido_verde_sulla_registrazione_vera[safe_base|omega]`, che
ora monta l'attesa) e' verde.

## COSA NON HO POTUTO VERIFICARE

- **Gli altri 22 scenari di Mike** (`--scenari tutti`): da brief un solo replay, solo `base`.
  Attesa, non misurata: le 21 righe CRITICAL scompaiono (stessa catena), e in ognuno la riga
  cambia motivo come in `base`. Il caso `under_green-0-2` (banca annullata al fischio e
  `_decide_ko_green` che aspetta) e' quello in cui la finestra dei 3 minuti puo' cambiare:
  non l'ho visto. Anche il tempo totale di `tutti` dovrebbe calare di circa 21 x 3 s d'attesa
  morta: non misurato.
- **Safe e Omega sul canale**: la correzione vale per ogni attore (stesso banco). I loro annulli
  sul canale passano dalla stessa `_annulla_via_canale` e con ogni probabilita' avevano lo stesso
  difetto; i loro referti sul canale possono cambiare. Non rieseguiti (vincolo: solo `base` di
  Mike). Le loro suite e il profilo rapido sono verdi.
- **Il runner vero in esecuzione**: la prova di produzione usa il codice di flumine LIVE e del
  runner (classi vere) dentro il banco, con un filo di prova al posto dello
  `SimulatedOrderStream`; non ho acceso il runner (vietato) ne' misurato la latenza reale del
  canale 47331.
- **Live REST contro Betfair**: letto il codice (`omega_market.cancel_order_live`), nessuna
  chiamata vera.
- **Latenza dello stream ordini nel banco**: il banco specchia a ogni book (0 ms), il runner ogni
  0,25 s: differenza gia' esistente, non modellata qui.
- **Tempo del replay**: la differenza 52 s -> 60 s della corsa ufficiale l'ho attribuita al carico
  della macchina (due corse diagnostiche: 61 s prima, 57 s dopo); non ho profilato.
- L'etichetta del referto "book passati mentre i piazzamenti aspettavano Betfair" ora conta anche
  l'annullo: e' in `replay_registrazioni.py`, file di un altro delegato, non toccato.

## File

- `Betfair/stream/backtest/porta_banco.py`, `banco_comune.py`, `trasporto.py`,
  `trasporto_rapido.py` (modificati); `Betfair/stream/tests/test_banco_annullo_confermato_2026_09_30.py` (nuovo).
- Referti e spie nel worktree: `_diag_annullo/base_prima.txt`, `base_dopo.txt`, `diag_base.txt`,
  `tl_prima.txt`, `tl_dopo.txt`, `falsifica.out`, `suite_*.txt` (fuori dalla patch).
