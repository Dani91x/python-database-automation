# CANTIERE T (28/09/2026) - tennis: K5 del PRO, K6/K5 e cascata dello SCALPER

Worktree `agent-ad1cc251cd88ed8c8`, base finale origin/master `f26bcb2`, dove il blocco 1 è già
integrato dal coordinatore (`b206b1c`) e c'è il ripiego (`90414b6`). Niente commit, niente push,
niente replay del banco: i replay li ha rilanciati il coordinatore.

## Consegne, in ordine

| File | Stato |
|---|---|
| `CANTIERE_T_blocco2_ripiego.patch` | Ripiego: scalper tennis con `exact_exits` spento. Integrato dal coordinatore (`90414b6`); replay 0 violazioni, azioni 1/228/228/1 |
| `CANTIERE_T_blocco1.patch` | PRO, K5. Integrato dal coordinatore (`b206b1c`) |
| `CANTIERE_T_blocco2.patch` (prima versione) | BOCCIATA dal replay del coordinatore: K5 x7981, 1,47 EUR di sbilancio, azioni 121 |
| `CANTIERE_T_blocco2.patch` (versione attuale, sha1 `AE65A5D8...`) | Da rilanciare sul banco |
| `cantiere_t/falsifica_t.py` | Script di falsificazione, esito in `cantiere_t/falsificazione_esito.txt` |

## 1. Cause radice

### Blocco 1: tennis_pro, K5 «posizione fantasma» da 0,02

- **Dove**: `tennis_pro_bot._surveil_closing`.
- **Cosa faceva**: dichiarava FLAT con `abs(nw - nl) < 0.02`, cioè fino a 0,0199 EUR di sbilancio. Poi scriveva `{"state": FLAT}` e dimenticava la selezione.
- **Perché K5 scatta**: senza credenza, K5 applica EPS 0,011. Anche il runner (`_strategy_is_flat`) usa 0,01. Il test `test_chiudi_ora...[residuo]` documentava già questa incoerenza («il PRO lo chiama pari a 0,02, il runner no a 0,01»).
- **Il residuo si poteva ridurre**: la selezione 10372252 è Sinner, a quota 1,02-1,10 (letta dal raw della registrazione). A quella quota una ri-copertura da 0,01-0,02 porta lo sbilancio entro 0,01. Il bot invece lo abbandonava.
- **Rapporto con D2**: il difetto era preesistente, D2 l'aveva solo scoperto. Prima di D2 l'over-hedge da gonfiatura (0,31) lo copriva.

### Blocco 2: scalper tennis con `exact_exits=True` acceso da D2

La regressione nasce da D2: con il ripiego il replay torna a 0 violazioni. Sono sette difetti, tutti in `tennis_scalper_bot.py`; sei li ho misurati riproducendoli nei test, il settimo (cascata di righe) è solo dedotto dal codice.

1. **K6.** Una chiusura tutta sotto il minimo, oppure il solo resto, fa sì che `_place_exact` avvii la sequenza e torni None. `_drive_flatten` leggeva quel None come «flatten non piazzabile» e accettava il micro-residuo: lo slot andava DONE con il parcheggio da 2,00 ancora Pending.
2. **Cascata di azioni.** In FLATTENING ogni book ritenta il flatten. Ogni ritentativo scriveva `min_bet_skip` senza dedup, mentre prima di D2 `_place` lo scriveva una volta sola (`_residuo_non_piazzabile_detto`).
   - La pausa di 30 s fra sequenze si misurava su `time.time()`, non sull'orologio del mercato come `UsciteEsatte` e il tetto transazioni del 17/09.
   - Questo punto viene dal codice: la causa delle 16.613 azioni la conferma o la smentisce solo il banco.
3. **K5 1,47 EUR (prima versione bocciata).** Il SOSTITUTO del rimpiazzo nasce quando flumine esegue il replace, cioè uno o più book DOPO il passaggio della sequenza a DONE e la sua uscita da `slot.submins`.
   - Nessuno lo agganciava a `flatten_orders`: era abbinato a mercato ma fuori da `_net_position`.
   - Il bot si credeva ancora scoperto e, finita la pausa, ripiazzava la chiusura: posizione ROVESCIATA.
   - Riprodotto con latenza di 4 book: slot fermo in FLATTENING con la selezione già chiusa.
4. **Sequenza bloccata per sempre.** Se il parcheggio viene ritirato da un'altra via (ciclo LOCKING, fine finestra) prima che il taglio sia chiesto, `advance_submin` in PLACED aspetta all'infinito: il ramo «park scomparso» esige `trim_requested_ms > 0`. Lo slot DONE salta allora la sorveglianza (`if slot.submins: continue`) e lo sbilancio resta senza padrone.
5. **Parcheggio orfano.** Il cancel di un ordine PENDING senza bet_id fallisce in silenzio (`BetfairOrder.cancel`). Lo stale di `_drive_flatten` salta per costruzione le quote di parcheggio, quindi il flatten aspettava per sempre un parcheggio che nessuno governava.
6. **Posizione piatta con una sequenza viva.** A posizione piatta restavano vivi ordini dello slot: parcheggi, o sequenze il cui rimpiazzo avrebbe rovesciato la posizione.
7. **LOCKING.** Il ciclo si chiudeva (DONE) anche con un parcheggio ancora PENDING in `flatten_orders`.

## 2. Cosa ho cambiato

### `Betfair/stream/tennis_scalper/tennis_pro_bot.py` (blocco 1, su master)

- `_TOLL_CHIUSA = 0,01`.
- `_centesimo_migliora(nw, nl, d, lato)`: usa la stessa quota della ri-copertura di sorveglianza e la size di `compute_green` al centesimo.
- In `_surveil_closing`, fra 0,01 e 0,02:
  - se un centesimo migliora lo sbilancio entro 0,01, la posizione NON è pari e la ri-copertura esistente continua (`close_retry_s`, place-and-trim);
  - altrimenti resta pari come prima e lo si dichiara una volta (`residuo_centesimi`).
- Nessuna soglia di strategia toccata.

### `Betfair/stream/tennis_scalper/tennis_scalper_bot.py` (blocco 2)

- **`_place_exact`**: orologio del mercato (`_orologio_s`); `min_bet_skip` scritto una volta per (selezione, lato, size). Soglie invariate: 30 s, 5 sequenze, 0,05.
- **`_drive_flatten`**:
  - a posizione piatta, se restano ordini vivi o sequenze: le sequenze si chiudono (`_cancel_submins`), gli ordini si ritirano e DONE arriva solo dopo;
  - un parcheggio si salta nello stale SOLO se la sua sequenza è in corso o se è in REPLACING; altrimenti è orfano e si ritira;
  - nuovo ramo `elif slot.submins`: con una sequenza appena avviata non si accetta il residuo.
- **`_drive_submins`**:
  - a ogni book aggancia a `flatten_orders` tutti gli ordini dei Trade già tracciati (i sostituti);
  - una sequenza in PLACED o TRIMMED con il parcheggio non più vivo si chiude, dichiarata con `submin_abort`.
- **`_ordini_in_sequenza`** (nuovo, di servizio).
- **LOCKING**: close abbinata ma ordini dello slot ancora vivi porta a `return`; si decide al book dopo, a cancel confermati.

### Altri file del blocco 2

- `Betfair/stream/tennis_live/tennis_runner.py`: `exact_exits` di nuovo True per lo scalper, cioè il ripiego tolto. Da integrare SOLO se il replay passa.

### Test

- **Nuovi**:
  - `tennis_live/tests/test_cantiere_t_pro_residuo_2026_09_28.py` (4, su master): contiene la fixture `esecuzione_differita`;
  - `tennis_live/tests/test_cantiere_t_scalper_sequenze_2026_09_28.py` (15).
- **Aggiornati**:
  - `test_chiudi_ora_bot_tennis_2026_09_24.py`: il caso `[residuo]` forza il residuo «non riducibile», per conservare il caso che copre;
  - `test_cantiere_d2_chiusure_esatte_2026_09_28.py`: il runner torna a True.
- **Strumenti** in `AUDIT_2026-09-28/cantiere_t/`: `falsifica_t.py`, `diagnosi_ritardo4.py`, e gli strumenti una tantum `sposta_fixture.py` e `ritocca_test_scalper.py`.

## 3. Test e falsificazione

- **Come girano i test nuovi**:
  - il bot VERO del runner paper riceve book veri dal Flumine con `process_market_book`;
  - l'esecuzione simulata di flumine (`execute_*`) è DIFFERITA di 1 e di 4 book, per imitare latenza, bet delay e coda. Con l'esecuzione sincrona, K6 e il sostituto tardivo non si vedono;
  - a ogni book si verificano le invarianti di K6 (IDLE/DONE senza ordini vivi e senza sequenze) e di K5 (sbilancio della selezione entro la tolleranza che il bot dichiara al banco).
- **Comandi e numeri**:
  - `.venv/Scripts/python.exe -m pytest Betfair/stream/tennis_scalper/tests Betfair/stream/tennis_live/tests -q -p no:cacheprovider`: **858 passed**, 68 s.
  - `.venv/Scripts/python.exe AUDIT_2026-09-28/cantiere_t/falsifica_t.py`: **9 mutazioni, 9 ROSSE**. Ripristino verificato con sha1 e con 0 occorrenze di `MUTAZIONE`; CRLF gestito.
- **Mutazioni**:
  - T1: piatta con un ordine vivo;
  - T2: residuo accettato a sequenza avviata;
  - T3: orologio del PC;
  - T4: niente dedup;
  - T6: sostituto non agganciato;
  - T7: sequenza bloccata;
  - T8: parcheggio orfano;
  - T9: LOCKING con parcheggio PENDING;
  - P1: soglia 0,02 del PRO.
- **Codice tolto perché non falsificabile**: il ritiro del parcheggio a ABORTED (ridondante con T8) e il `now_ms` passato ad `advance_submin`.

## 4. Migrazioni SQL

Nessuna.

## 5. Parità paper/live

- Tutte le modifiche stanno nel codice dei bot, uguale in paper e in live.
- `exact_exits`, `live_min_bet` e `size_step` li mette il runner uguali per PAPER e LIVE, come da D2.
- L'orologio della pausa è ora quello del mercato in tutte le modalità.

## 6. Cosa NON ho fatto e cosa NON ho potuto verificare

- **Replay del banco**: vietato a me. Il criterio di accettazione (K5 e K6 a zero, azioni dell'ordine di 228/245) resta da misurare dal coordinatore sulla patch attuale del blocco 2. Anche il blocco 1 aspetta il suo replay.
- **Abbinamenti PARZIALI**: non provati. Il book finto del banco dei test ha 10 a ogni livello.
- **Limite residuo del blocco 1**: se il residuo del PRO nasce a una quota alta, dove 0,01 di size sposta lo sbilancio di più di 0,01, il PRO resta FLAT come prima (dichiarato) e K5 scatterebbe. È il limite della granularità di Betfair, non corretto e non correggibile senza toccare K5.
- **Limite noto dello scalper in LOCKING**: il ciclo che ritira i `flatten_orders` ritira anche il resto esatto della close. Il resto viene poi chiuso dal flatten con una seconda sequenza (30 s dopo), oppure accettato come micro-residuo dichiarato (`residual_ok`, soglia 0,25 già esistente). Sono più ordini del necessario, ma non attendo violazioni. Non corretto perché cambia il ciclo del maker.
- **Uscite in replay**: il banco non passa `uscite_automatiche`.
  - Il PRO gira con il default della classe, False = MANUALE: scaglione e target non scattano, restano stop e uscita strutturale. K5 del PRO riguarda quindi chiusure automatiche di sicurezza, e il manuale non la spiega.
  - Lo scalper tennis su master non ha ancora l'interruttore: lo porta il cantiere N.
- **Betfair live**: INVALID_PROFIT_RATIO sulle riduzioni da 0,01-0,02 del place-and-trim è un limite già dichiarato da D2 e non verificato.
- **FLB e swing**: nessun test nuovo. Dalla lettura del codice, le loro chiusure dichiarate (`tennis_flb_bot.py`, righe con `ordini_vivi_su(...) is False`; `tennis_swing_bot.py` `ordini_vivi_su(...) is not False`) esigono già blotter senza ordini vivi, sequenza di `UsciteEsatte` compresa. Il test sul PRO (`test_chiusura_esatta_in_corso_mai_flat`) prova l'invariante su `UsciteEsatte.attive`.

## 7. Decisioni per l'utente

Nessuna nuova. Soglie invariate: 30 s, 5 sequenze, 0,05, 0,25 e 0,30 dello scalper; stop, target e `close_retry_s` del PRO.

## 8. Da controllare dal vivo in paper al prossimo avvio

- **Scalper tennis**, solo se il blocco 2 viene integrato:
  - in `tennis_bot_activity`, righe `submin_abort` con nota «parcheggio non piu' vivo»: devono essere rare;
  - `min_bet_skip` al massimo poche per ciclo;
  - nessuno slot DONE con ordini vivi.
- **PRO**:
  - righe `residuo_centesimi`: devono essere rare, e solo a quote alte;
  - dopo `closed_flat`, lo sbilancio della selezione nello specchio `tennis_live_orders` deve restare entro 0,01.
