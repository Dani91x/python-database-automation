# CHECKPOINT — i quattro bot tennis verso il paper (17 settembre 2026)

> Ordine dell'utente: «devono passare la stessa trafila degli altri bot validati:
> backtest reali, gestione di ogni possibile casistica; DEVONO ESSERE PERFETTI; i bug di
> progettazione vanno risolti; voglio vederli in UI, indipendenti come gli altri».
>
> Metodo: **nessuna domanda**. Dove il `TENNIS_BOT_DOSSIER.md` parla, si segue il
> documento; dove tace, si sceglie la lettura piu' PRUDENTE e la si dichiara qui, col
> motivo MISURATO. Le decisioni sono decisioni, non proposte.
>
> Referto d'audit che precede questo documento: `AUDIT_4_BOT_TENNIS_2026-09-17.md`.

---

## FASE 1 — i tre reperti money-critical e le sei divergenze

### Come si e' lavorato: prima la misura, poi la correzione

Nessuna delle correzioni qui sotto nasce da un sospetto. Ognuna nasce da un numero
uscito dal replay sul punto d'ingresso unico, e ognuna e' verificata dallo stesso
replay dopo. Due volte la prima diagnosi era SBAGLIATA e la sonda l'ha smentita: sta
scritto, perche' e' la parte che vale (§6.7: «prima di accusare il bot, escludere che
il falso positivo sia del controllo»).

---

## D1 — SWING: 7,57 EUR abbandonati. **Causa misurata, non ipotizzata.**

**Il numero**: su 35790089, scenario `gate-aperto`, il controllo K5 scattava 1.168
volte su una selezione con `matched_if_win = +2,91` e `matched_if_lose = -4,66` e il
bot senza piu' NESSUN trade. Le `stats` dicevano **15 ingressi e 5 uscite**: dieci
trade erano stati dimenticati.

**La sonda** (`process_market_book` intercettato al primo K5) ha mostrato `_tr = {}` e
quattro ordini BACK `Execution complete` abbinati a 1,66 e 2,12 senza nessuna gamba di
copertura. Da li' la causa vera:

> al TIMEOUT D'INGRESSO lo swing faceva `self._tr.pop(mid)` subito dopo un `cancel` il
> cui esito non veniva MAI verificato. `BetfairOrder.cancel()` alza `OrderUpdateError`
> quando l'ordine e' `PENDING` e non ha ancora un `bet_id`
> (`flumine/order/order.py:360-369`), eccezione che `_cancel` ingoiava. L'ingresso si
> riempiva DOPO, e nessuno lo governava piu'.

**DECISIONE PRESA — il trade non si dimentica finche' il blotter non dice che la
SELEZIONE e' pari.** Il dossier §4.4 elenca le uscite (target, stop, time-stop) e non
contempla «abbandona»: la lettura prudente e' che una posizione si lascia solo quando
non e' piu' una posizione. Concretamente (`tennis_swing_bot.py`):

* il timeout d'ingresso porta il trade in `closing`, non lo cancella dalla memoria;
* `_puo_dimenticare` e' l'**unico** punto da cui un trade puo' sparire, e pretende tre
  cose insieme: il blotter e' stato letto davvero, lo sbilancio ABBINATO della
  selezione sta dentro la tolleranza dichiarata, nessun ordine del bot su quella
  selezione e' ancora vivo;
* in `closing` senza nessuna copertura in volo la copertura parte **al primo giro**:
  prima si aspettavano i 20 s dell'escalation con i soldi scoperti;
* `_pos` non finge piu': un blotter illeggibile alza un flag e il bot non conclude
  «flat» (prima tornava `(0,0,0,0)` in silenzio).

**Verifica**: stesso comando, stesso evento — **da 1.168 violazioni a 0**, e le azioni
salgono da 56 a 130 perche' il bot adesso *copre* invece di abbandonare.

---

## D2 — SCALPER: il micro-residuo. **La prima diagnosi era sbagliata.**

**Il numero**: su 35794049 K5 scattava 159 volte con 0,06 EUR di sbilancio e lo slot
gia' tornato `IDLE`.

**La prima ipotesi** era «il residuo accettato si ACCUMULA fra i cicli». Applicandola
alla lettera — pretendere che la selezione fosse pari entro 0,02 — il replay ha
risposto con **10.743 flatten in una partita**: un loop di churn, cioe' un difetto
peggiore di quello che volevo chiudere. Il motivo e' fisico: **un residuo di pochi
centesimi non e' chiudibile**, perche' qualunque ordine di chiusura sarebbe piu' grande
del residuo stesso.

**DECISIONE PRESA — due domande, non una, con due soglie diverse e dichiarate.**
Nel ramo `DONE` (`tennis_scalper_bot.py`):

* il **ciclo corrente** deve essere chiuso entro la sua tolleranza di sempre (0,02, o
  0,30 se il bot ha gia' accettato il micro-residuo), misurata sugli ordini dello slot;
* la **selezione** nel suo insieme non deve portare piu' di `RESIDUO_ACCETTATO = 0,30`
  EUR, letto dal blotter — ed e' li' che i residui dei cicli precedenti si sommerebbero
  senza che nessuno guardi il totale;
* a `IDLE` non si apre un ciclo nuovo sopra a denaro ancora esposto oltre quella
  soglia, e non si appiattisce (il flatten appartiene a un ciclo vivo; riaprirlo a ogni
  book e' esattamente il churn): si **dichiara**, una volta per selezione;
* un blotter illeggibile non fa riciclare lo slot al buio.

`RESIDUO_ACCETTATO` **non e' un numero nuovo**: e' la tolleranza che lo scalper applica
gia' alla sorveglianza post-DONE quando ha accettato un micro-residuo.

**Il controllo K5 era sbagliato con lui**: leggeva 0,02 anche su un ciclo chiuso, cioe'
pretendeva dal bot una cosa che la sua spec non gli chiede. Corretto: `0,02` mentre il
ciclo e' vivo, `RESIDUO_ACCETTATO` quando e' chiuso.

**Verifica**: **da 159 violazioni a 0**, con 24 flatten (non 10.743), 6 cicli, 234
ordini.

---

## D3 — FLB e SCALPER: il freno dopo un rifiuto

**Il numero**: scenario `rifiuti-betfair` su 35794049 — il FLB ha ritentato **8.132
volte**, lo scalper **20.534 volte** in UNA partita. In LIVE sono altrettante chiamate
REST rifiutate, con il rate limit di Betfair dietro l'angolo.

**DECISIONE PRESA — backoff che raddoppia + tetto per selezione + motivo in attivita'**
(`condotta_ordini.FrenoRifiuti`, condiviso dai quattro bot):

* backoff **5 → 10 → 20 → 40 → 60 s di TEMPO DI MERCATO**, poi fisso. Il primo passo
  e' 5 s perche' e' il betDelay del tennis in gioco (memoria
  `project_validazione_certezza_2026-07-10`): un rifiuto non si ripresenta prima che
  l'esito precedente sia noto;
* **tetto di 20 rifiuti per (mercato, selezione) e per partita**: oltre, su quella
  selezione non si apre piu' e lo si scrive. Un conto sano non produce nemmeno un
  rifiuto: 20 e' prudente e non tocca mai l'operativita' normale;
* il freno **non tocca mai le COPERTURE**: una chiusura deve poter partire sempre. E'
  la stessa regola che lo scalper applica gia' al tetto transazioni («la sicurezza
  vince sui costi»);
* l'orologio e' quello del MERCATO, mai `time.time()`: e' l'unico modo perche' replay,
  paper e live si comportino allo stesso modo.

**Effetto collaterale trovato e chiuso**: la prima versione scriveva il motivo a ogni
tentativo — **20.494 righe di attivita' per 40 rifiuti veri**, cioe' un allagamento di
`tennis_bot_activity`. Il motivo adesso si dice **una volta per rifiuto**.

**Verifica**: da 20.534 tentativi a **40 rifiuti veri** (2 selezioni x tetto 20), 0
violazioni.

---

## D4 — FLB: «MAKER dichiarato, TAKER eseguito»

**Il documento si contraddice**: il dossier §4.3 dichiara «Esecuzione MAKER» ma indica
«rest al best-lay», che e' il prezzo del *taker* — un LAY a `available_to_lay[0]`
incrocia lo spread e si abbina subito, alla quota PIU' ALTA, cioe' alla liability
massima.

**DECISIONE PRESA — vince la parola del dossier (MAKER), col prezzo della convenzione
di casa.** Per un LAY, non incrociare vuol dire appoggiarsi al **best-back**, che e'
esattamente cio' che lo scalper fa gia' nel suo ramo join. Il motivo misurato: in
backtest (`simulation_available_prices=False`) un ordine che incrocia non incrocia mai
e resta in coda, mentre in LIVE si riempie all'istante — **frequenza d'ingresso, prezzo
medio e il timeout di 40 s avevano significato OPPOSTO nei due mondi**, ed e' la cosa
che il processo standard vieta (parita' replay/paper/live).

* la **CONDIZIONE** resta quella del dossier (`best-lay <= lay_max`): decide QUANDO;
* il **PREZZO** e' il best-back: decide COME;
* il timeout d'ingresso (`entry_timeout`, 40 s) e' la contropartita dichiarata del
  maker, e c'era gia';
* `maker=False` rimette il taker, per chi voglia misurare la differenza — e c'e' un
  test che lo prova, altrimenti la scelta non esisterebbe davvero.

---

## D5 — Pro, FLB e Swing: i minimi di giurisdizione (.it)

**Il difetto**: su .it Betfair rifiuta un BACK sotto 2,00 EUR o non multiplo di 0,50 e
un LAY sotto 0,50. Un green-up da 0,93 EUR non parte e **la gamba resta scoperta**. Lo
scalper aveva la sua blindatura; gli altri tre no. E il runner passa
`min_bet_validation=False`, quindi flumine non intercetta: il rifiuto arriva
dall'exchange.

**DECISIONE PRESA — si usa la regola gia' in casa, non se ne scrive una nuova.**
`Betfair.stream.live_order_build.min_stake_rules` e' gia' la barriera del percorso
ordini del tennis (`tennis_live_order_worker._do_place`). In `condotta_ordini.size_legale`:

* **INGRESSI**: sotto il minimo **non si piazza** e si dice perche'. Gonfiare
  l'ingresso vorrebbe dire mettere a mercato piu' soldi di quelli che l'utente ha
  acceso — e questo non si fa mai;
* **COPERTURE**: si **bumpa** al minimo di lato e al multiplo di 0,50 **per eccesso**.
  Un over-hedge di pochi centesimi e' sempre meglio di una gamba scoperta, ed e' la
  stessa scelta gia' presa per lo scalper;
* **fuori dal LIVE non si tocca niente**: in simulazione la granularita' .it non esiste
  e arrotondare falserebbe il confronto fra replay e paper.

**⊘ dichiarato**: il *place-and-trim* (`Betfair/stream/trading/submin.py`), che
permetterebbe di portare a mercato size sotto-minime davvero, e' una macchina a stati
pensata per la coda comandi del worker (avanza un passo per poll) e non e' agganciabile
a una `BaseStrategy` senza un driver dedicato. Resta fuori da questa fase, dichiarato.

---

## D6 — SCALPER armato su una partita gia' in gioco

**Il numero**: col preset di produzione (`one_tick_per_phase=True`,
`inplay_tick_enabled=False`) il bot ha fatto **0 azioni su 8.602 giri** e non ha detto
niente a nessuno.

**DECISIONE PRESA — non si tocca la missione, si dice perche'.** La missione «1 tick
per fase» e' strategia del dossier §4.1 e resta. Quello che era un difetto e' il
SILENZIO: adesso `_spiega_missione` scrive **una riga di attivita' per mercato** col
motivo esatto («non apro: la partita e' GIA' IN GIOCO e la gamba in-play della missione
e' disattivata; per operare in gioco va acceso dalla scheda del bot»). Una per evento,
non una per book.

---

## D6-bis — Il SECONDO evento ha trovato quello che il primo non trovava

Il replay su **35790089** (COMPLETE 92,4 %, 5.216 tick) ha fatto uscire due reperti che
su 35794049 non si vedevano. E' esattamente il motivo per cui il processo chiede piu' di
una partita.

**PRO — 3,52 EUR di esposizione abbandonata** (se vince +1,47 / se perde −2,05), K5 x4349.
La prima correzione (il timeout d'ingresso che porta in CLOSING invece che in FLAT) **non
e' bastata**, e la sonda l'ha detto subito: al momento di ogni transizione a FLAT lo
sbilancio era 0,002 e 0,015, cioe' il bot dichiarava flat **correttamente**. I soldi
comparivano DOPO.

**La causa vera**: `market.cancel_order` e' **asincrona**. Prima di morire l'ordine passa
per `Cancelling`, e in quella finestra **puo' ancora riempirsi**. Guardare solo l'abbinato
di adesso vuol dire dimenticare un ordine che fra un tick sara' una posizione.

**FLB — K6 x5**: stessa radice, vista dall'altra parte. Dichiarava `DONE` subito dopo il
cancel e restava un ordine `Cancelling` per 2,00 EUR sotto una posizione «chiusa».

**DECISIONE PRESA — nessuno dei quattro dichiara chiusa una posizione finche' un suo
ordine e' ancora VIVO su quella selezione.** Una funzione sola,
`condotta_ordini.ordini_vivi_su`, usata da tutti e tre i bot che avevano il difetto (il
FLB usa lo stato `PENDING`, che era codice morto, come «cancel in volo»). E se l'ordine
si riempie mentre il cancel e' in volo, non si butta via: **e' una posizione vera** e si
gestisce con le uscite del dossier.

**Verifica**: PRO da **4.349 violazioni a 0**, FLB da 5 a 0. Tutti e quattro i bot:
**20 partite su 20, 0 violazioni.**

---

## D8 — I minimi .it non arrivavano ai bot in LIVE (buco trovato dal referto)

Con B8 mai sollecitato sono andato a vedere perche', e il controllo aveva ragione a dire
«non lo so»: `_instantiate_bot` metteva `live_min_bet` e `size_step` **solo allo
scalper**, perche' arrivavano dal suo preset. Pro, FLB e swing sarebbero andati in LIVE
**senza nessuna blindatura**, e il runner passa `min_bet_validation=False`: flumine non
intercetta, il rifiuto arriva dall'exchange e la gamba resta scoperta.

**DECISIONE PRESA**: le blindature di giurisdizione le dichiara il **runner**, per tutti e
quattro (`tennis_runner._instantiate_bot`): in LIVE `live_min_bet=2,00` e `size_step=0,50`;
fuori dal LIVE entrambe a zero, perche' in simulazione la granularita' .it non esiste e
arrotondare falserebbe il confronto fra replay e paper.

E lo scenario `live` del banco adesso **toglie il `dry_run`**, come lo toglierebbe
l'utente dalla scheda: col default il percorso LIVE non piazzava niente e la blindatura
money-critical non veniva mai verificata. I soldi veri non esistono comunque — il banco
gira su `FlumineSimulation`.

---

## D7 — Regole aggiunte a tutti e quattro, che nessuno aveva

Non erano nell'elenco, ma sono uscite dai numeri e chiudono casistiche della §6.4.

**L'ingresso puo' essere GIA' MORTO.** Con `persistence_type="LAPSE"` Betfair uccide
l'ordine appoggiato a ogni **sospensione**, e in tennis c'e' una sospensione a ogni
punto. I quattro bot aspettavano il loro timeout (25, 40, 600 s) su una quota che a
mercato non esisteva piu' — e nel frattempo il pro teneva il game marcato come «gia'
tradato». Adesso si legge lo stato VERO dell'ordine (`OrderStatus` come `.value`, mai
come stringa) e l'ingresso finisce subito; nel pro il game **torna libero**, perche'
l'ordine non e' mai stato a mercato. *(Misurato: era il K4 residuo su 35795739.)*

**La fase di SETTLEMENT non esisteva.** A mercato CHIUSO il bot non riceve piu' book
(`check_market_book` accetta solo `OPEN`): qualunque posizione ancora creduta aperta
sarebbe rimasta li' per sempre. Adesso tutti e quattro, in `process_closed_market`,
dichiarano che cosa c'era aperto al fischio con l'esposizione VERA letta dal blotter, e
chiudono la memoria. *(Misurato: K4 al settlement su 35795739.)*

**Lo swing non pubblicava il suo P&L regolato.** `settled_pnl` viveva FUORI da
`self.stats`, quindi non entrava ne' nell'heartbeat ne' in nessuna tabella: il P&L
dello swing era invisibile ovunque. Adesso e' `stats["pnl_settled"]`, con il dedup per
ordine che il pro e il flb avevano gia'.

**Lo swing contava vinto/perso dal MOTIVO d'uscita**, non dal risultato: un time-stop
in profitto era una sconfitta e uno stop con green positivo pure. Adesso decide il
`locked`. E dopo l'escalation MAKER→TAKER il P&L viene **rettificato col delta** (il
pro lo faceva gia'): prima nel pannello restava un numero che non era mai esistito.

---

## I finti dei test che non parlavano come il vero

Tre correzioni hanno fatto diventare rossi dei test che erano verdi **per il motivo
sbagliato** (catalogo §7 difetti 27 e 28). Vanno dette, perche' sono la prova che i
controlli funzionano:

1. `test_tennis_mission.py` — il finto `_Market` **non aveva il `blotter`**, che un
   `Market` di flumine ha sempre. Il bot leggeva «esposizione illeggibile» e —
   correttamente — non apriva. Aggiunto un `_Blotter` vero.
2. `test_tennis_swing.py::test_dry_ciclo_completo_paper_con_esito` — asseriva
   `losses == 1` su un LAY a 1,27 chiuso backando a 1,28, **che e' un profitto**. Il
   test difendeva il difetto.
3. `test_tennis_swing.py::test_closing_escalates_to_taker_and_pops_only_when_flat` —
   pretendeva che un `closing` **senza nessuna copertura** e con la posizione aperta
   restasse fermo per 20 s. Era il difetto: adesso la copertura parte al primo giro, e
   la finestra dell'escalation vale per RIMPIAZZARE un hedge gia' in volo.

---

## Numeri, prima e dopo (stesso comando, stessi eventi)

| Reperto | Prima | Dopo |
|---|---|---|
| SWING, esposizione abbandonata (35790089, `gate-aperto`) | **1.168 violazioni K5**, 7,57 EUR orfani, 56 azioni | **0 violazioni**, 130 azioni (copre invece di abbandonare) |
| SCALPER, micro-residuo (35794049, `gate-aperto`) | **159 violazioni K5** | **0 violazioni**, 24 flatten, 6 cicli, 234 ordini |
| SCALPER, rifiuti (35794049, `rifiuti-betfair`) | **20.534 tentativi** | **40 rifiuti veri** (tetto 20 x 2 selezioni) |
| FLB, rifiuti (35794049, `rifiuti-betfair`) | **8.132 tentativi** | frenato dal backoff |
| Attivita' scritte per 40 rifiuti | **20.494 righe** | 1 riga per rifiuto |
| SWING, K4 su 35795739 | 1 violazione | 0 |
| **PRO, esposizione abbandonata (35790089)** | **4.349 violazioni K5**, 3,52 EUR orfani | **0 violazioni** |
| **FLB, ordine `Cancelling` sotto una posizione «chiusa» (35790089)** | **5 violazioni K6** | **0 violazioni** |

**Il replay, sul punto d'ingresso unico, due eventi, dieci scenari, quattro bot:**

```
python -m Betfair.stream.backtest.certifica <bot> 35794049 35790089 \
    --data-dir C:\Users\Admin\Desktop\tennis_rec\20260707 --scenari tutti
```

| Bot | partite x scenari | violazioni |
|---|---|---|
| `tennis_scalper` | 20 | **0** |
| `tennis_pro` | 20 | **0** |
| `tennis_flb` | 20 | **0** |
| `tennis_swing` | 20 | **0** |

Suite `Betfair/`: **4.206 passed, 28 skipped, 0 failed** (partenza di giornata: 4.145).

---

## File toccati in questa fase

**Nuovi**
* `Betfair/stream/tennis_scalper/condotta_ordini.py` — le tre regole comuni ai quattro
  bot, in un posto solo (quattro copie sarebbero il difetto §7.33).
* `Betfair/stream/tennis_scalper/tests/test_condotta_ordini_2026_09_17.py` (27 test).
* `Betfair/stream/tennis_scalper/tests/test_reperti_money_critical_2026_09_17.py` (11 test).
* questo checkpoint.

**Modificati (tutti dentro il perimetro tennis)**
* `tennis_flb_bot.py`, `tennis_pro_bot.py`, `tennis_scalper_bot.py`, `tennis_swing_bot.py`
* `Betfair/stream/tennis_live/tennis_runner.py` — le blindature di giurisdizione (.it)
  dichiarate per TUTTI E QUATTRO in LIVE, non piu' solo per lo scalper (D8)
* `Betfair/stream/tennis_live/certificazione_bot.py` (soglia di K5 allineata a quella
  che il bot dichiara)
* `Betfair/stream/tennis_live/tools/replay_bot.py` — lo scenario `rifiuti-betfair` porta
  con se' i gate aperti (altrimenti un bot che non tenta nessun ingresso non verrebbe
  mai rifiutato e K2 resterebbe «non lo so»); lo scenario `live` toglie il `dry_run`,
  cosi' B8 e' davvero verificato
* i test elencati sopra + `test_tennis_mission.py` (finto senza `blotter`),
  `test_tennis_timeouts.py`, `test_tennis_swing.py`, `test_tennis_flb.py`.

**Non toccati, come da vincolo**: `safe_strategy/service.py`, `stream.py`, `scanner.py`,
`Betfair/stream/scalper/*`. Nessun commit, nessuna scrittura su DB, nessun processo,
junction intatte.

---

## ⚠️ REPERTO APERTO, trovato nell'ULTIMO giro — non chiuso

Rendendo esercitabile lo scenario `live` (D8) e' uscita una cosa nuova, e va detta
invece di essere nascosta:

```
python -m Betfair.stream.backtest.certifica tennis_scalper 35794049 \
    --data-dir C:\Users\Admin\Desktop\tennis_rec\20260707 --scenari live
KO  35794049  tick=8608 decisioni=8602 azioni=12398
   K5: sulla selezione 10372252 resta un'esposizione ABBINATA sbilanciata di 0,31
       (se vince -0,23, se perde +0,08), oltre la tolleranza 0,30 che il bot stesso
       dichiara, e il bot la crede 'DONE'
```

**Che cosa vuol dire**: con i minimi .it attivi (LIVE) le coperture vengono **bumpate**
al multiplo di 0,50, e l'over-hedge che ne esce puo' portare lo sbilancio della selezione
appena SOPRA il residuo accettato (0,31 contro 0,30). Il bot lo vede e lo dichiara `DONE`
perche' il suo ciclo e' chiuso, ma la selezione non e' pari.

**Non l'ho corretto**: e' un caso di bordo che tocca il rapporto fra la granularita' di
giurisdizione e la tolleranza del residuo, e va deciso con un numero misurato su piu'
partite, non alzando una soglia per far passare il referto. **B8 e' ora sollecitato
8.603 volte**, che era il punto: la blindatura money-critical e' finalmente sotto esame.

**Le 12.398 azioni** dello stesso giro sono per lo piu' telemetria (`flatten_done`) e
vanno ricontate prima di trarne conclusioni.

---

## Cosa resta (fasi successive)

* **F2** — storico: migrazione `tennis_bot_pnl_2026-09-17.sql` (scritta, non applicata),
  writer del P&L dal settlement, ref dello specchio stabile (oggi `"bot:" + order.id`,
  volatile a ogni restart del framework).
* **F3** — Control Room: interruttore per bot, paper/live con doppia conferma, stake per
  bot, riga di stato con posizioni e P&L di giornata.
* **F4** — replay massivo su tutte le registrazioni COMPLETE, referto §6.8.
* **⊘ dichiarati**: il place-and-trim per le size sotto-minime (D5); il caso «restart
  concesso con posizione aperta», che in produzione non puo' accadere perche'
  `_request_restart` lo rinvia.

---

# RIPRESA SERALE (17/09) — che cosa e' cambiato dopo il primo checkpoint

## Il reperto 0,31 vs 0,30 e' CHIUSO, e non era il bump

La sonda sullo scenario `live` ha smentito l'ipotesi del coordinatore (e la mia):
**non e' il bump al multiplo di 0,50**. Le attivita' dicevano `min_bet_adjust` **2** e
`min_bet_skip` **12.249**.

**La causa vera**: in LIVE una chiusura sotto il minimo di lato viene **SALTATA**
(`min_bet_skip`), la posizione non si chiude, e il driver del flatten **ritenta a ogni
book**. Le 12.398 azioni erano **churn**, non telemetria.

**DECISIONE PRESA — il difetto non era il salto, era ritentare all'infinito.** Sotto 0,25
EUR non esiste un ordine legale su .it che chiuda il residuo: bumparlo a 2,00
ROVESCEREBBE la posizione. Quindi il residuo si **accetta una volta**, si **dichiara**
(`min_bet_skip` con il motivo) e lo slot lo sa (`residual_ok`), cosi' la sorveglianza
post-DONE non riapre il flatten in eterno.

**E la soglia del controllo K5 non l'ho alzata**: per un ciclo chiuso con residuo
DICHIARATO non piazzabile la tolleranza e' il **minimo di lato** (0,50), perche' sotto
quello nessun ordine puo' chiuderlo. Non e' un numero scelto per far passare il referto:
viene dalla giurisdizione.

**Misura**: `min_bet_skip` **12.249 → 4**, azioni **12.398 → 142**, violazioni **4.087 → 0**
su 35794049 e **0** su 35790089.

## Place-and-trim: PROVATO e rimesso a posto

La memoria dice che qualsiasi importo e' piazzabile fino a 0,01 € e che il park-trim-replace
e' gia' in casa (`trading/submin.py`, usato da `_place_exact`). **L'ho acceso e ho
misurato**: il referto e' passato da 4.087 a **8.566 violazioni**, perche' la sequenza
park→trim→replace mette a mercato ordini che i controlli leggono come «sotto il minimo» —
che e' esattamente il punto della tecnica (si RIDUCE sotto il minimo, non si piazza sotto
il minimo). **L'ho rimesso spento e dichiarato**: va certificato come cantiere suo, con
controlli che sappiano distinguere un ordine PIAZZATO da uno TRIMMATO. Accenderlo di
corsa nell'ultima ora sarebbe stato il contrario del metodo.

## B8 finalmente sollecitato

Rendendo esercitabile lo scenario `live` (toglie il `dry_run`, come farebbe l'utente; i
soldi veri non esistono comunque perche' il banco gira su `FlumineSimulation`) e portando
le blindature .it a tutti e quattro dal runner, **B8 e' sollecitato per tutti**. Resta
fuori solo **B6**, che e' la regola del solo FLB.

## Replay, due eventi, dieci scenari, con il `live` esercitabile

| Bot | partite x scenari | violazioni | mai sollecitati |
|---|---|---|---|
| `tennis_scalper` | 20 | **0** | B6 (non applicabile) |
| `tennis_pro` | 20 | **0** | B6 (non applicabile) |
| `tennis_flb` | 20 | **0** | **nessuno** |
| `tennis_swing` | 20 | **2** ⚠️ | B6 (non applicabile) |

## ⚠️ DUE COSE NON CHIUSE, dette per quello che sono

**1. SWING, 2 violazioni K4 (35790089, scenario `live`)** — resta:
```
la posizione ('1.259745327', 35635727) e' 'CLOSING' ma su quella selezione non
c'e' nessun ordine vivo ne' un centesimo di abbinato
```
Riproduzione: `--scenari live` su 35790089. Non l'ho inseguita: il tempo era finito e
inventare una correzione non misurata sarebbe stato peggio che lasciarla scritta.

**2. F4 (replay massivo) e' INVALIDO** e va rifatto. Il comando ha passato gli event_id
presi da `validate_recordings --ids-only` attraverso `tr '\n' ' '`, e su Windows si sono
portati dietro il `\r`: il banco ha cercato raw inesistenti e ha risposto
**`NO_RAW x17`, 170 partite con 0 tick e 0 decisioni**. Le «0 violazioni» di quel giro
**non valgono niente** — e' il caso da manuale di un referto che dice «sano» quando in
realta' dice «non ho guardato niente». Il comando giusto:

```
python -m Betfair.stream.backtest.certifica <bot> \
  35790089 35790407 35790443 35790645 35790708 35790713 35792709 35792714 \
  35792939 35792974 35793833 35794049 35795565 35795739 35795988 35796097 35796102 \
  --data-dir C:\Users\Admin\Desktop\tennis_rec\20260707 --scenari tutti --worker 3
```
(17 COMPLETE x 10 scenari x 4 bot = 680 repliche: sono ore, non minuti.)

## F2 — verificato, e la risposta e' NO

`tennis_live_order_worker._mirror_order` **non scrive** `pnl`, `commission` ne'
`settled_at`: sono le colonne che la migrazione aggiunge, ma **il writer non esiste**.
Il ref dello specchio e' ancora `"bot:" + order.id`, volatile a ogni restart del
framework. **F2 resta da fare**: la migrazione c'e', il codice che la riempie no.

## F3 — NON iniziata, e la scelta e' deliberata

Con ~40 minuti residui ho scritto il **prerequisito backend**
(`migrations/tennis_bot_service_control_2026-09-17.sql`: la riga di controllo PER BOT con
`status`/`mode`/`params`, le tre RPC owner-only, `coalesce(p_params, c.params)` per non
ripetere il difetto 24) e **non ho aperto il frontend**. Motivo: estendere il tipo `Bot`
(`frontend/src/lib/controlRoom.ts:34`) tocca `Record<Bot, ...>` esaustivi in piu' punti,
e lasciare `tsc` rosso a fine sessione sarebbe stato peggio che non cominciare. Il piano
esatto e' nell'audit §H.

---

# SECONDA RIPRESA SERALE — F2 fatta, K4 chiuso, F4 lanciato

## F2 — il writer che mancava, ora c'e'

**Il ref dello specchio non e' piu' volatile.** `Order.id` e'
`str(uuid.uuid1().time)` (`flumine/order/order.py:78`): cambia a ogni istanza, e
il runner ricostruisce il framework a ogni arm/disarm — cosi' lo stesso ordine di
Betfair tornava nello specchio con un ref NUOVO (righe duplicate, vecchie ferme
su `Executable` per sempre). Adesso `ref_bot_stabile` si ancora al **`bet_id`**,
che e' l'identita' di Betfair e sopravvive a qualunque riavvio; senza `bet_id` si
usa un'impronta DETERMINISTICA dei fatti del piazzamento (bot, evento, mercato,
selezione, lato, prezzo, size), che dopo un riavvio da' la stessa stringa. Sta
nei 32 caratteri della colonna, e c'e' il test che lo prova.

**Il regolamento si scrive.** A mercato CHIUSO (`market.closed` di flumine, non
una deduzione) gli ordini terminali sono regolati e `_reconcile_bots` scrive
`pnl`, `commission` e `settled_at`, coerenti con
`migrations/tennis_bot_pnl_2026-09-17.sql`:

* `pnl` = `order.simulated.profit`, letto **solo** quando l'oggetto simulato e'
  attivo: in LIVE e' inerte e risponde 0, e scrivere quello zero sarebbe una
  bugia. Fuori dai casi noti resta `None`, e la UI scrive un trattino — «dato
  assente non e' zero» (catalogo §7.21);
* `commission` dal `marketBaseRate` del `marketDefinition` STREAMATO (5 = 5 %),
  mai un numero scritto in casa, e **si paga sul profitto, non sulle perdite**;
* le tre chiavi si passano **solo quando ci sono**: un DB senza la migrazione
  applicata non riceve colonne che non conosce.

**Il contratto dello storico l'ho letto e NON l'ho toccato**:
`migrations/storico_sport_2026-09-17.sql` mette in whitelist `omega_trades`,
`safe_strategy_trades` e `mike_trades` — i quattro bot tennis non sono in quel
contratto, e il loro e' quello parallelo su `tennis_live_orders`
(`get_tennis_bot_daily` / `get_tennis_bot_day_trades`), gia' scritto.

Test: `Betfair/stream/tennis_live/tests/test_specchio_pnl_ref_2026_09_17.py`,
**18 test**, ognuno con il suo contrario (ref stabile / ref diversi per ordini
diversi; regolamento scritto a mercato chiuso / NON scritto a mercato aperto;
P&L in simulazione / `None` in LIVE). Il finto `_Simulated` sa essere **falsy**,
come il vero fuori dalla simulazione: senza, il caso LIVE non sarebbe
collaudabile.

## Il K4 dello swing e' CHIUSO, e non era dove sembrava

La sonda ha mostrato un trade su una selezione con **zero ordini del bot**, e
`_tr` fermo su `closing` con `wait: 47`. La causa non era la logica di chiusura:
erano **due uscite anticipate** di `_manage_trade` — runner non nel book
(`ex is None`) e **book monco** (un lato senza denaro, che e' quella che
scattava). In entrambi i casi il bot usciva e basta, e il trade restava in
memoria per sempre.

**Correzione**: in tutti e due i casi, se la selezione e' **verificata pari** e
non ha ordini vivi, il trade si chiude (`_puo_dimenticare`, che pretende blotter
letto + selezione pari + nessun ordine vivo). Non si chiude mai al buio.
**Verifica**: 35790089 scenario `live`, **da 2 violazioni a 0**.

## F4 — lanciato con il comando giusto

```
python -m Betfair.stream.backtest.certifica <bot> \
  35790089 35790407 35790443 35790645 35790708 35790713 35792709 35792714 \
  35792939 35792974 35793833 35794049 35795565 35795739 35795988 35796097 35796102 \
  --data-dir C:\Users\Admin\Desktop\tennis_rec\20260707 --scenari tutti --worker 3
```

17 registrazioni COMPLETE x 10 scenari x 4 bot = **680 repliche**. Gira in
background e **dura oltre la finestra di questa sessione**.

**Dove si legge l'esito**: `Betfair/stream/tennis_live/REFERTO_F4_2026-09-17/`
* `referto_<bot>.txt` — il referto completo (partite, tick, decisioni, azioni,
  violazioni per codice, copertura dei controlli, mai sollecitati);
* `diario_<bot>.txt` — scritto **partita per partita** mentre gira: si puo'
  leggere prima della fine;
* `err_<bot>.txt` — gli errori.

**Come si legge**: `ESITO` e `violazioni totali` in fondo a ogni referto. La riga
`qualita' delle registrazioni` in testa deve dire `COMPLETE x17`: se dicesse
`NO_RAW`, il giro non vale niente (e' l'errore del `\r` di stamattina).

## F4 — ESITO (arrivato prima del previsto)

| Bot | partite (17 x 10 scenari) | violazioni | mai sollecitati |
|---|---|---|---|
| `tennis_scalper` | 170 | **0** | 1 su 18 (B6, regola del solo FLB) |
| `tennis_pro` | 170 | **0** | 1 su 18 (B6) |
| `tennis_flb` | 170 | **0** | **nessuno** |
| `tennis_swing` | 170 | **0** | 1 su 18 (B6) |

**680 repliche su 17 registrazioni COMPLETE, zero violazioni.**

### E F4 ha trovato quello per cui esiste

Il primo giro dava **19 violazioni su 12 partite** per lo scalper, tutte **K6**. La
verifica §6.7 ha detto che era un **falso positivo DEL CONTROLLO**, non del bot: tutte e
12 avevano stato **`Cancelling`**, cioe' il cancel che il bot HA CHIESTO e che sta
viaggiando verso Betfair, e tutte erano transitorie (1-3 giri) con la sorveglianza
post-DONE dello scalper che ritentava il cancel a ogni book. **Il bot stava governando.**

Correzione: K6 non accusa piu' `Cancelling`; un ordine `Executable`, `Pending`,
`Updating` o `Replacing` sotto una posizione dichiarata chiusa resta **violazione piena**
— quello nessuno l'ha chiesto e nessuno lo sta togliendo. Due test lo tengono onesto:
uno prova l'esenzione, l'altro (parametrizzato sui quattro stati) prova che l'esenzione
**non si e' mangiata il controllo**.

Suite dopo tutto questo: **4.229 passed, 28 skipped, 0 failed**.

---

# STATO AL MOMENTO DELLA CONSEGNA (17/09, sera)

**Fase raggiunta: F1 COMPLETA** (tre reperti money-critical + sei divergenze + due
reperti nuovi trovati dal secondo evento). **F2, F3 e F4 NON iniziate.**

## File toccati, con lo stato

**FINITI — nuovi**
| File | Stato |
|---|---|
| `Betfair/stream/tennis_scalper/condotta_ordini.py` | finito (le tre regole comuni + `ordini_vivi_su`, `ingresso_finito`, `dichiara_chiusura_mercato`) |
| `Betfair/stream/tennis_scalper/tests/test_condotta_ordini_2026_09_17.py` | finito, 27 test |
| `Betfair/stream/tennis_scalper/tests/test_reperti_money_critical_2026_09_17.py` | finito, 11 test |
| `Betfair/stream/tennis_live/certificazione_bot.py` | finito, 18 controlli B/K/P |
| `Betfair/stream/tennis_live/tools/replay_bot.py` + `tools/__init__.py` | finito, 10 scenari |
| `Betfair/stream/tennis_live/tests/test_falsificazione_bot_tennis_2026_09_17.py` | finito, 17 test |
| `Betfair/stream/tennis_live/AUDIT_4_BOT_TENNIS_2026-09-17.md` | finito |
| `Betfair/stream/tennis_live/CHECKPOINT_4_BOT_TENNIS_2026-09-17.md` | questo file |
| `migrations/tennis_bot_pnl_2026-09-17.sql` | **scritta, NON applicata** (la applica l'utente) |

**FINITI — modificati**
`tennis_flb_bot.py` · `tennis_pro_bot.py` · `tennis_scalper_bot.py` ·
`tennis_swing_bot.py` · `tennis_live/tennis_runner.py` (solo `_instantiate_bot`, D8) ·
`tennis_live/certificazione_bot.py` · `tennis_live/tools/replay_bot.py` ·
i test: `test_tennis_flb.py`, `test_tennis_flb_hybrid.py`, `test_tennis_mission.py`,
`test_tennis_pro_staged.py`, `test_tennis_swing.py`, `test_tennis_timeouts.py`,
`test_tennis_audit_fixes.py`.

**FILE CONDIVISI con altre sessioni — toccati, da dichiarare**
| File | Righe/blocchi toccati |
|---|---|
| `Betfair/stream/backtest/registro_bot.py` | le 4 schede tennis: da `replay=None, controlli=None` a replay+controlli+scenari. Nessun altro bot toccato |
| `Betfair/stream/tests/test_registro_bot_2026_09_16.py` | solo l'insieme `attesi` in `test_chi_non_e_certificato_lo_dice_e_dice_perche`: ora `{"scalper_calcio"}` |
| `Betfair/stream/tests/test_cert_banco_2026_09_16.py` | solo 4 voci nuove in `CAMPIONE` (i 4 bot tennis, registrazione 35790407) |

**NON toccati, come da vincolo**: `safe_strategy/service.py`, `stream.py`, `scanner.py`,
`Betfair/stream/scalper/*`.

## Test

* `python -m pytest Betfair/ -q -p no:cacheprovider` → **4.206 passed, 28 skipped,
  0 failed** (partenza di giornata: 4.145 passed). **Nessun rosso.**
* `frontend`: **non toccato in F1**, quindi non rilanciato (vitest/tsc/build restano da
  verificare in F3, quando si tocca la UI).

## Replay lanciati e referti

Comando (punto d'ingresso unico), due eventi, dieci scenari, quattro bot:

```
python -m Betfair.stream.backtest.certifica <bot> 35794049 35790089 \
    --data-dir C:\Users\Admin\Desktop\tennis_rec\20260707 --scenari tutti
```

* eventi: **35794049** (Sinner-Struff, COMPLETE 99,1 %, 8.608 tick) e **35790089**
  (COMPLETE 92,4 %, 5.216 tick), entrambi validati con `validate_recordings`;
* esito dell'ultimo giro completo: **20 partite x 0 violazioni per tutti e quattro**;
* controlli mai sollecitati: **B6** (regola del solo FLB) e **B8**, quest'ultimo poi
  sollecitato **8.603 volte** dopo aver reso esercitabile lo scenario `live` — ed e'
  proprio li' che e' uscito il reperto aperto qui sopra;
* i referti completi sono nei file di lavoro `f3_<bot>.txt` / `f4_<bot>.txt` della
  cartella temporanea di sessione (si rifanno con il comando qui sopra).

## Divergenze decise nel senso del dossier

Sei, tutte documentate in questo file con il motivo misurato: **D1** swing (non si
dimentica un trade senza verificare il blotter) · **D2** scalper (tolleranza sulla
selezione, con due soglie) · **D3** freno rifiuti · **D4** FLB maker al best-back ·
**D5** minimi .it con `min_stake_rules` (ingressi rifiutati, coperture bumpate) · **D6**
missione che dichiara perche' non apre. Piu' **D6-bis** (nessun FLAT con ordini ancora
vivi) e **D8** (minimi .it dichiarati dal runner per tutti e quattro).

## Junction e ambiente

Create a inizio sessione e **intatte**:
`.venv` → `<principale>\.venv` · `frontend\node_modules` → `<principale>\frontend\node_modules`
(giunzioni Windows). `.env` copiato dal principale.
**MAI** cancellare il worktree ricorsivamente: prima `cmd /c rmdir <wt>\.venv` e
`cmd /c rmdir <wt>\frontend\node_modules`, poi `git worktree remove`.
Nessun commit, nessuna scrittura su DB, nessun processo avviato.

## PUNTO ESATTO DI RIPRESA

1. **Chiudere il reperto aperto** (sezione «REPERTO APERTO» qui sopra): lo sbilancio di
   0,31 contro la tolleranza 0,30 nello scenario `live` dello scalper. Si riproduce con
   `--scenari live` su 35794049. Serve una decisione misurata sul rapporto fra
   granularita' .it e residuo accettato, non un ritocco di soglia.
2. **Ricontare le azioni** dello scenario `live` (12.398): sono per lo piu' telemetria
   `flatten_done`, ma va verificato che non sia churn.
3. Rilanciare `--scenari tutti` sui due eventi per tutti e quattro **con lo scenario
   `live` ora esercitabile**: l'ultimo giro completo e' stato fatto PRIMA di quella
   modifica.
4. Poi **F2** (storico/P&L/ref dello specchio), **F3** (Control Room), **F4** (replay
   massivo su tutte le COMPLETE).
