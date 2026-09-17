# AUDIT DEI QUATTRO BOT TENNIS — 17 settembre 2026

> Ordine dell'utente: «occupati dei 4 bot tennis (tennis_scalper, tennis_pro, tennis_flb,
> tennis_swing) e portali nella Control Room; vanno ricontrollati PER INTERO nella logica e
> nella struttura, controllo maniacale e approfondito; se incappi in errori di progettazione
> fixali; devono seguire l'iter che ha seguito Safe prima di passare al paper».
>
> Criteri di accettazione: `PROCESSO_STANDARD_BOT.md` §6 (copertura obbligatoria del banco)
> e §7 (catalogo dei 37 errori gia' visti). Fonte della strategia: `TENNIS_BOT_DOSSIER.md` §4.
>
> **Questo documento e' la mappa (gradino 2). Il gradino 3 — il replay — e' stato costruito
> e girato nella stessa giornata: `Betfair/stream/tennis_live/tools/replay_bot.py` +
> `Betfair/stream/tennis_live/certificazione_bot.py`, punto d'ingresso unico
> `python -m Betfair.stream.backtest.certifica <bot> <event_id>`.**

---

## 0. In una riga, il verdetto

I quattro bot **non sono pronti per il paper**. Adesso sono *registrati e certificabili*
(replay + controlli dal punto d'ingresso unico), i difetti di consapevolezza dell'ordine del
catalogo §7 sono corretti e falsificati, ma restano **tre reperti money-critical misurati**
(§E) e **sei divergenze di strategia** che solo l'utente puo' decidere (§I). E i quattro bot
**non esistono nel modello della Control Room**: portarli dentro richiede una decisione di
progetto, non una riga di codice (§H).

---

## A. Che cosa fa ciascun bot, e ogni sua condizione

Tutti e quattro sono `flumine.BaseStrategy` in `Betfair/stream/tennis_scalper/`, ospitati dal
runner di produzione `Betfair/stream/tennis_live/tennis_runner.py`. Nessuno di loro tocca il
database: leggono il `MarketBook` e il punteggio (`self.score`, `self.point_pressure`) e
piazzano con `market.place_order`.

### A.1 `tennis_scalper` — `tennis_scalper_bot.py` (2.351 righe)

**Una frase**: market-making a due gambe sul MATCH_ODDS — quota BACK e LAY insieme (join ai
touch con spread stretto, dentro lo spread con spread largo) e, quando una gamba si riempie,
chiude l'altra a +1 tick o appiattisce, con stop a 3 tick.

**Ingresso** (tutti in `_try_enter`, salvo indicato). Default = preset `TENNIS_PARAMS` del
runner standalone, che `_instantiate_bot` applica con `setdefault`
(`tennis_runner.py:588-597`):

| # | Condizione | Parametro / default | file:riga |
|---|---|---|---|
| 1 | best back/lay/micro-price presenti | — | `tennis_scalper_bot.py:1011-1012` |
| 2 | `price_min <= best_back <= price_max` | 1.20 / 6.0 | `:305-306`, gate `:1013-1014` |
| 3 | liquidita' su ENTRAMBI i best | `min_size` 5.0 | `:301`, gate `:1015-1016` |
| 4 | total matched del runner | `min_total_matched` 0.0 (**gate morto**) | `:302`, gate `:1017-1019` |
| 5 | spread calcolabile sulla ladder | — | `:1020-1022` |
| 6 | cooldown post-gap/post-stop | `cooldown_ms` 20000 | `:372`, gate `:1025-1026` |
| 7 | anti-gap sul micro-price | `max_signal_ticks` 10.0 / `signal_window_ms` 15000 | `:314-315`, gate `:1028-1031` |
| 8 | warm-up del runner | `warmup_ms` 30000 | `:355`, gate `:1037-1038` |
| 9 | flusso tradato per lato | `min_flow` 2.0 / `flow_window_ms` 90000 | `:334,353`, gate `:1039-1041` |
| 10-14 | prints dentro lo spread, oscillazione, equilibrio del flusso, WoM, anti-deriva | tutti OFF nel preset | `:349,345,340,316,391` |
| 15-16 | loss cap evento, cricchetto post-target | OFF | `:483,481-482` |
| 17-19 | bias, trend-surf, `swing_only` | OFF | `:404-410,466-468,475` |
| 20-22 | routing: JOIN se `st <= join_max_spread` 3; MAKER se `2 <= st <= 20` | `:325,327-328,358` | `:1146-1153` |
| 23-24 | ramo REVERSION (`max_spread_ticks` 6, `signal_ticks` 1.0) | **MORTO** con `mode="auto"` | `:1034,1157-1159` |
| 25-27 | JOIN: room >= 1 tick, fattibilita' di coda, `improve_inside` | `max_queue_wait_s` OFF | `:1247-1266` |
| 32 | runner ACTIVE | — | `:785-786` |
| 33 | **`runner_filter="favorite"`**: solo il best-back piu' basso; se un ACTIVE non ha best-back, **nessun ingresso su nessun runner** | `:536`, `_favourite_sel` `:649-667`, gate `:941-944` |
| 34-37 | in-play consentito, finestra in-play, slot in-play, stop pre-KO | tutti aperti/spenti dal preset | `:510-514` |
| 38-39 | slot IDLE, cicli sotto `max_cycles` 500 | `:272,903,930` |

**Uscita**: target `scalp_ticks`=1 sul prezzo medio abbinato (`_open_lock` `:1756-1787`);
target «gratis» riusando la gamba opposta resting (`:1338-1349`, `:1380-1391`); stop avverso
`stop_ticks`=3 sul prezzo d'ingresso (`:1627-1673`); TTL ingresso `entry_ttl_ms`=600.000 ms;
TTL lock `lock_ttl_ms`=3.600.000 ms; scratch a pari una volta per ciclo (`:1674-1711`);
requote a `reprice_ticks`=2 (`:1415-1441`, `:1575-1596`); roundtrip equalizzato entro 0,02 →
DONE (`:1305-1325`); **flatten garantito** con escalation fino a 8 tick (`:1810-1913`);
accettazione micro-residuo se il peggior esito >= −0,25 EUR (`:1885-1906`); sorveglianza
post-DONE (`:866-878`). **Nessun trailing, nessun time-stop di mercato.**

**Sicurezza**: mercato non OPEN → il bot non fa NULLA (`:670-672`); transizione
pre-match→in-play con cancel + flatten immediato (`:720-737`); `force_flat` (`:446`);
gap-guard su `point_pressure` (`:519,771-772,931-933`); missione «1 tick per fase»
(`:578-586,614-647`); circuit breaker per ciclo `cycle_loss_breaker`=0,50 (`:285,1835-1844`);
tetto transazioni `max_txn_hour`=300 (`:434-435`); `dry_run`; minimo Betfair `live_min_bet`
2,00 e granularita' `size_step` 0,50 in LIVE, azzerati in PAPER (`:417,421`,
`tennis_runner.py:598-601`); anti-cascata submin (`:2129-2131`).
**Feed stantio: nessun controllo** (il bot non guarda l'eta' del `publish_time`).

### A.2 `tennis_pro` — `tennis_pro_bot.py` (783 righe)

**Una frase**: direzionale score-driven che, a ogni CAMBIO di punteggio IPS, apre un solo
trade per game su uno di sei setup e lo chiude a target/stop in tick o alla risoluzione del
game.

**Gate globali**: book OPEN (`:196-197`); runner ACTIVE (`:526`); nessun trade OPEN/CLOSING
(`:547-555`); `market_book.inplay` (`:558`); `min_matched` 50.000 (`:115`, gate `:560`);
`self.score is not None` (`:561-562`); **cambio** di `score.key()` (`:564-567`); un solo trade
per game (`_last_game_traded`, `:570-572`); banda `price_min` 1.08 / `price_max` 3.6
(`:117-118`, gate `:369`); profondita' `min_book_size` 10.0 (`:116`, gate `:371-372`).

**I sei setup** (priorita' fissa `:575-586`): `break_point` (ricevitore a 40 e servitore <=15,
`:233`; direzione per superficie `:413`; target 5 / stop 3); `fade` (salto >= `fade_jump_ticks`
8 entro `fade_max_game` 3, `:434-436`; target 4 / stop 4); `set_transition` (finestra
`st_window_games` 2, `:449-451`; target 5 / stop 4); `serving_for_set` (`:465`; target 6 /
stop 4); `double_break` (`db_lead_games` 3, `:479`; target 6 / stop 4); `compressed_fav`
(`cf_max_price` 1.20, `:495`; target 4 / stop 3).
⚠️ **Con il preset del runner (`surface="grass"`) gli ultimi tre sono SPENTI** (`_enable_rev`
False, `:114,152,156,166`): 3 setup su 6 non esistono e il banner non lo dice (`run_tennis_pro.py:141-144`).

**Uscite**: target (`:636-639`), stop (`:640-643`), uscita STRUTTURALE al cambio di
(games, sets) (`:644-650`), scaglione `staged_frac` 0.4 a meta' strada (`:629-634`), timeout
ingresso `entry_timeout_s` 25 s (`:598-612`), sorveglianza CLOSING con escalation TAKER
(`:721-746`). **Nessun target in denaro, nessun trailing.**

**Sicurezza**: `dry_run` (`:318-320`); un solo trade per mercato; **nessun cooldown
temporale, nessun max-trade, nessun max-perdita**; tetto di esposizione solo dall'esterno
(`tennis_runner.py:599`); **nessun controllo di eta' del punteggio**.

### A.3 `tennis_flb` — `tennis_flb_bot.py` (349 righe)

**Una frase**: laya il favorito ESTREMO (best-lay <= `lay_max` 1.10) con stake minuscolo,
**senza stop**, e lo chiude con un green-up quando la quota risale di `green_ticks` 8, o lo
tiene fino al settlement.

**Ingresso**: `total_matched >= min_matched` 10.000 (`:64`, gate `:183`); book OPEN e runner
ACTIVE (`:90-91`, `:189`); entrambi i touch quotati (`:195-199`); nessuna posizione viva
(`:200-204`); ri-armo solo se `bl > lay_max * rearm_mult` 1.10 (`:207-211`); gate in-play
`require_inplay` True (`:213-216`); `bl <= lay_max` (`:219`); `min_lay_size` 5.0 (`:197,219`);
stake `max(2.0, stake)` (`:39,55`).

**Uscita**: timeout ingresso `entry_timeout` 40 s di publish-time (`:247-261`); green a
`ticks_between(entry, bb) >= green_ticks` (`:292-296`) per frazione `green_frac` 0.5 in
`hybrid` (default) o 1.0 in `green` (`:297`); cancel del residuo d'entry dopo il green
(`:310-314`); conferma del green solo a hedge completamente abbinato (`:234-242`);
ripiazzamento dell'hedge morto (`:279-289`); **in `hold` nessuna uscita: si tiene fino alla
chiusura del mercato** (`:315`). **Nessuno stop-loss, per progetto** (`:9-11`).

### A.4 `tennis_swing` — `tennis_swing_bot.py` (352 righe)

**Una frase**: price-driven (nessun punteggio) che rileva un estremo del favorito con z
robusto mediana/MAD, lo filtra con Efficiency Ratio + conferma d'inversione + cross RSI, entra
MAKER contro l'estremo ed esce verso l'ancora.

**Ingresso**: book OPEN (`:86`); nessun trade aperto (`:285-288`); `min_matched` 10.000
(`:70`); favorito individuabile (`:107-115`); entrambi i touch (`:293-294`); warm-up `N` 40
(`:51`, `:302`); `mad > 0` (`:309-310`); `|z| >= zin` 2.0 (`:52`, `:311-319`); regime
`_er(tk, 20) < er_max` 0.4 (`:53`, `:312`); banda 1.08-8.0 sul mid (`:71-72`, `:313`);
conferma d'inversione `conf_ticks` 2 (`:314-315`); cross RSI 65/35 (`:317,319`); ingresso
maker a `price_ticks_away(±maker_offset 1)` (`:318,320`).
⚠️ **Nessun gate `inplay`** (il bot puo' firmare segnali PRE-MATCH) e **nessun gate di
profondita'/spread**.

**Uscita**: target `target_frac` 0.5 verso l'ancora (`:244-246`); stop `stop_ticks` 8
(`:247`); time-stop `tmax` 90 s (`:60,251-252`); timeout ingresso **40 s cablati**
(`:236-238`); escalation MAKER→TAKER dopo `close_retry_s` 20 s (`:214-225`).
**Nessun cooldown, nessun max-trade, nessun max-perdita.**

---

## B. La mappa della CONSAPEVOLEZZA DELL'ORDINE (§6.4)

La riga `tennis_live_orders` NON e' scritta dai bot: la scrive
`tennis_live_order_worker._reconcile_bots` (`:821-859`) leggendo il **blotter** di flumine e
passando da `_mirror_order` (`:300-340`). Quindi «cosa sa il bot» e «cosa sa la riga» sono
due cose diverse, e vanno guardate separate.

### B.1 Che cosa legge ogni bot da un ordine

| Campo | scalper | pro | flb | swing |
|---|---|---|---|---|
| `size_matched` | si (`:841,1291,1569,1742,1989`) | si (`:299`) | si (`:103`) | si (`:123`) |
| `average_price_matched` | si (`:1992`) | si (`:300`) | si (`:104`) | si (`:124`) |
| `size_remaining` | si (`:2292,2302`) | **no** | solo sull'hedge (`:273`) | **no** |
| `status` (Enum) | si, **come Enum** (`:2290,2301`) | **mai** | solo sull'hedge (`:176-179`) | **mai** |
| `bet_id` | solo in un log (`:2310`) | **mai** | **mai** | **mai** |
| `violation_msg` | dal 17/09 (fix) | dal 17/09 (fix) | dal 17/09 (fix) | dal 17/09 (fix) |
| esito di `place_order` | **dal 17/09 (fix)** | **dal 17/09 (fix)** | **dal 17/09 (fix)** | **dal 17/09 (fix)** |
| esito di `cancel_order` | mai verificato | mai verificato | mai verificato | mai verificato |
| `simulated.profit` | si (`:995-996`) | si (`:762-763`) | si (`:330`) | si (`:340-341`) |

### B.2 La matrice per esito (§2 del processo)

| Esito dell'ordine | il bot lo SA? | che cosa FA | la riga `tennis_live_orders` lo sa? |
|---|---|---|---|
| abbinato tutto | si (`size_matched` dal blotter) | chiude / green | **si** (`size_matched`, `average_price_matched`) |
| parziale subito | **solo in aggregato**: nessun bot confronta `size_matched` con lo stake chiesto; lo scalper e' l'unico con rami espliciti (`:1304-1331,1357-1413`) | scalper: hedge di size esatta; pro/flb/swing: continuano col netto | **si** (`size_matched` + `size_remaining`) |
| appoggiato poi parziale, poi intero | scalper si; gli altri no | — | si |
| mai abbinato e scaduto | solo per TIMEOUT (scalper `entry_ttl_ms`, pro 25 s, flb 40 s, swing 40 s cablati). **Nessuno legge lo stato `Expired`/`Lapsed`** | cancel non verificato | si (`status`) |
| annullato dal bot | **no**: `cancel_order` torna un bool e nessuno lo legge; su un ordine PENDING senza `bet_id` `BetfairOrder.cancel()` alza `OrderUpdateError`, ingoiata | il bot lo dimentica comunque | si |
| **rifiutato da Betfair** | **SI, dal 17/09**: prima nessuno leggeva il bool di `place_order` | non registra la posizione, emette `place_rejected` | si (`status = Violation`) |
| esito ignoto (timeout/eccezione) | no: nessuna gamba `pending_reconcile`, nessun `bet_id` salvato | — | no |
| prezzo migliore | solo via `average_price_matched` | — | si |
| mercato annullato | no | — | si (`size_voided`) |

**Dove la riga `tennis_live_orders` NON sa**:
1. **il ref non e' un riferimento Betfair**: lo specchio dei bot usa `"bot:" + order.id`
   (`tennis_live_order_worker.py:847`), cioe' l'id dell'oggetto flumine, non il
   `customer_order_ref` mandato all'exchange. Dopo un restart del framework gli id
   ricominciano: **righe duplicate e righe vecchie che restano `Executable` per sempre** (la
   guardia `framework_gen` esiste solo per gli ordini MANUALI, `:757-772`);
2. **nessun P&L e nessun `settled_at`**: la tabella non ha quelle colonne
   (`migrations/tennis_orders.sql:80-115`). E' la ragione per cui lo Storico non puo'
   sommare nulla (§F);
3. `request_id` viene da `_request_id_from_ref` che si aspetta `awtq<id>`: per i bot e' sempre
   `NULL`.

---

## C. Stati e fasi

| Bot | stati dichiarati | stati DAVVERO usati | osservati nel replay del 17/09 |
|---|---|---|---|
| scalper | `IDLE, QUOTING, QUOTING2, CANCELLING, LOCKING, FLATTENING, DONE` (`:83-85`) | tutti tranne `QUOTING` (usato solo nei rami bias/reversion, morti col preset) | **IDLE, QUOTING2, LOCKING, CANCELLING, FLATTENING, DONE** (scenario `gate-aperto`) |
| pro | `FLAT, OPEN, CLOSING, DONE` (`:52`) | `OPEN`, `CLOSING`, `FLAT`. **`DONE` e' costante morta** | `OPEN`, `CLOSING` |
| flb | `IDLE, PENDING, OPEN, DONE` (`:43`) | `OPEN`, `DONE`. **`IDLE` e `PENDING` sono codice morto** | `OPEN`, `DONE` |
| swing | **nessuna costante**: la fase e' una chiave booleana `closing` creata al volo (`:276`) | assente → pending-entry → open → closing | `OPEN`, `CLOSING` |

Fasi di prodotto (solo scalper): `greens_prematch` / `greens_inplay`, `mission_done`,
`force_flat`, `point_pressure` (`:519,539,544-547`).

---

## D. Come entrano in paper e in live (percorso ordini)

- **Modalita'**: `TENNIS_LIVE_ORDER_MODE` = OFF | PAPER | LIVE, riletta a ogni chiamata
  (`tennis_runner.py:97-99`). Kill-switch a tripla difesa: solo LIVE costruisce un client con
  `paper_trade=False`; OFF e PAPER forzano `paper_trade=True`; in OFF il worker ordini non
  viene nemmeno registrato e i bot sono forzati in dry-run (`:102-155`, `:580-584`).
- **Bet delay**: in PAPER lo dorme flumine dal `marketDefinition` streamato, con
  `FreshDelaySimulatedExecution` che rilegge il betDelay VIGENTE al momento dell'esecuzione
  (`paper_execution.py`, fix GAP-5). La latenza di rete nostra e' `TENNIS_PAPER_LATENCY_MS`
  = 600 ms (`tennis_runner.py:86`).
- **FOK**: **nessuno dei quattro bot lo usa**. Tutti piazzano `LimitOrder(...,
  persistence_type="LAPSE")` senza `time_in_force` ne' `min_fill_size`.
- **Place-and-trim / submin**: esiste SOLO nello scalper (`_place_exact` `:2142-2229`,
  `_drive_submins` `:2231-2278`) ed e' **codice morto** perche' `exact_exits` non e' in
  `TENNIS_PARAMS`. Gli altri tre non ce l'hanno.
- **Coda `tennis_live_order_queue`**: e' la coda degli ordini **MANUALI** dal ladder, non dei
  bot. I bot piazzano direttamente su flumine (`market.place_order`).
- **Minimi .it**: solo lo scalper li applica (`live_min_bet` 2,00 / `size_step` 0,50 in LIVE).
  **Pro, FLB e Swing non hanno alcuna blindatura**: un green-up da 0,93 EUR o da 2,03 EUR
  viene rifiutato da Betfair e la gamba resta scoperta — e il runner passa
  `min_bet_validation=False` (`tennis_runner.py:124,142,147`), quindi flumine non intercetta.
- **Parita' paper/live**: in LIVE `_instantiate_bot` mette `dry_run=True` di default
  (`:583-584`), in PAPER `dry_run=False`. Non e' una divergenza di strategia ma **rende il
  percorso LIVE non esercitabile finche' l'utente non toglie il flag a mano**.

---

## E. I difetti trovati, con il catalogo §7 e la gravita'

Legenda gravita': **M** money-critical · **A** alta · **B** media/bassa.
«misurato» = provocato e visto nel replay del 17/09 sulla registrazione 35794049 / 35790089.

### E.1 CORRETTI IN QUESTA GIORNATA (con falsificazione rossa)

| # | Bot | Difetto | Catalogo | Grav. | Prova |
|---|---|---|---|---|---|
| 1 | tutti e 4 | **`market.place_order` torna un bool e nessuno lo leggeva.** Un rifiuto dei trading control lasciava l'ordine in `Violation` fuori dal blotter, ma il bot lo trattava come vivo: lo scalper bloccava lo slot per i 10 minuti di `entry_ttl_ms`, il pro marcava il game come gia' tradato e non riprovava, il flb e lo swing registravano una posizione inesistente | **§7.2** | **M** | replay `rifiuti-betfair` PRIMA: K1/K2/K4 rossi ×13; DOPO: K2 sollecitato ×3211, 0 violazioni |
| 2 | scalper | **gamba ORFANA**: se una sola delle due gambe partiva, l'altra spariva da ogni contabilita' (`slot` restava IDLE, `_net_position` non la vedeva) e il cancel su un ordine `PENDING` senza `bet_id` falliva in silenzio. Caso ordinario: basta che `max_txn_hour`=300 tagli la seconda gamba | §7.7 | **M** | test `test_scalper_la_gamba_superstite_resta_nella_contabilita` |
| 3 | scalper | **il tetto transazioni usava `time.time()`**: in replay un'ora di mercato scorre in secondi reali, la finestra non si svuotava mai e il cap bloccava ogni ingresso per il resto della partita. Parita' replay/paper/live rotta | §7.12 (parente) | **A** | test `test_scalper_il_tetto_transazioni_usa_l_orologio_del_mercato` |
| 4 | flb | **P&L di settlement contato DUE volte**: nessun dedup per ordine, e flumine puo' richiamare `process_closed_market` sullo stesso mercato. Il pro aveva gia' lo stesso fix (`tennis_pro_bot.py:757-761`) | §7.3 | **A** | test `test_flb_pnl_non_raddoppia_se_il_mercato_chiude_due_volte` |
| 5 | flb | **GREEN contato senza che nessuna copertura fosse partita**: il ramo `go is None` confondeva «posizione gia' pari» con «l'hedge non e' partito» e incrementava `stats["greens"]` su una posizione ancora aperta | §7.3 | **A** | test `test_flb_non_conta_un_green_se_l_hedge_non_e_partito` |
| 6 | test | **7 finti che non parlavano come il vero**: `place_order` ritornava `None` invece del bool. Certificavano il difetto 1 | **§7.27** | **A** | i 7 file allineati, 4 test diventati rossi e poi verdi per il motivo giusto |

### E.2 REPERTI APERTI, MISURATI NEL REPLAY (decisione dell'utente: sono STRATEGIA)

| # | Bot | Reperto | Catalogo | Grav. |
|---|---|---|---|---|
| 7 | **swing** | **7,57 EUR di esposizione abbinata sbilanciata ABBANDONATA** su 35790089 (se vince +2,91, se perde −4,66) con il bot che non ha piu' NESSUNA posizione: `self._tr.pop(mid)` (`:204,241,268`) dimentica il trade dopo un cancel mai verificato. Su uno stake di 2 EUR | §7.7 / §6.4 | **M** |
| 8 | **scalper** | **residuo accettato che si ACCUMULA fra cicli**: `_reset` riporta lo slot a IDLE e la sorveglianza post-DONE smette di guardare; misurato 0,06 EUR di sbilancio residuo con il bot che crede `IDLE`, oltre la sua stessa tolleranza 0,02 | §7.7 | **A** |
| 9 | **swing** | posizione creduta `OPEN` senza nessun ordine vivo ne' un centesimo di abbinato (K4 ×1 su 35795739) | §7.4 | **A** |
| 10 | **flb**, **scalper** | **nessun freno sui rifiuti ripetuti**: nello scenario `rifiuti-betfair` il FLB ha ritentato l'ingresso **8.132 volte** e lo scalper **20.534 volte** in UNA partita. In LIVE sono altrettante chiamate REST rifiutate, con il rate limit di Betfair dietro l'angolo. Nessuno dei due ha un cooldown dopo un rifiuto (lo swing ne ha fatti 50, il pro 0) | §7.1 (loop) | **A** |

### E.3 REPERTI APERTI, NON PROVOCABILI SU QUESTA PARTITA (⊘ con causa)

| # | Bot | Reperto | ⊘ perche' |
|---|---|---|---|
| 11 | pro, flb, swing | **nessuna blindatura .it**: green-up sotto 2,00 EUR o non multiplo di 0,50 → `INVALID_BET_SIZE` e gamba scoperta. Lo scalper ce l'ha (`:412-422`) | il controllo **B8** non e' mai stato sollecitato: in LIVE `_instantiate_bot` forza `dry_run=True` e nessun ordine parte |
| 12 | tutti e 4 | **stato tutto in RAM**: `_slots`, `_trade`, `_pos_state`, `_tr` e le `stats` non sopravvivono a un restart del framework, che avviene a ogni arm/disarm. Il runner mitiga (restart solo a bot flat, `tennis_runner.py:818-822`) ma solo lo scalper ha `force_flat`: un pro/flb/swing con posizione aperta **rinvia il restart all'infinito** fino alla grazia di 180 s, e in LIVE il restart non viene MAI forzato | provocato dallo scenario `riavvio`: sul FLB di 35794049, con la lay aperta, il restart e' stato **correttamente RINVIATO** e non e' mai avvenuto. ⊘ resta il caso opposto (restart concesso con posizione aperta), che in produzione non puo' accadere |
| 13 | tutti e 4 | **finestre temporali che scorrono a mercato SOSPESO**: `check_market_book` accetta solo `"OPEN"`, quindi durante una sospensione non si gestisce nulla, ma i timer sono ancorati al `publish_time` e alla riapertura scattano tutti insieme, sul book peggiore | 1 sola sospensione con ordini vivi nella registrazione (`lapse alla sospensione: 1`) |
| 14 | scalper | `_recent_move` torna `None` quando nessun campione cade nella finestra (dopo una sospensione o un buco di feed) e la gap-guard viene SALTATA: **fallisce aperta proprio nei momenti di gap** (`:1029,1526-1527`) | non provocato: servirebbe uno scenario con buco di feed iniettato |
| 15 | scalper | `history` ha `maxlen=64` e viene appesa a ogni book: su un mercato veloce copre ~1-2 s, non i 15 s dichiarati da `signal_window_ms` (`:194,212-213,315`) | misurabile solo con una registrazione ad alta frequenza |
| 16 | tutti e 4 | **`pnl`/`pnl_settled` sono SEMPRE 0 in LIVE**: `order.simulated.profit` calcola su `size_matched` dell'oggetto simulato, che in live e' 0 (`flumine/order/order.py:186`). Il `cleared_profit` reale non viene MAI letto | ⊘ il replay e' sempre simulato |
| 17 | pro | 3 setup su 6 spenti dal preset (`surface="grass"` → `_enable_rev=False`) senza che l'operatore lo veda | e' configurazione, non un bug |

---

## F. I difetti di PROGETTAZIONE

1. **`tennis_bot_control.stats` e' una fotografia, non una serie.** L'heartbeat la RISCRIVE
   PER INTERO a ogni battito (`tennis_runner.py:1275-1280`) e il riarmo la azzera
   (`tennis_bot_arm` scrive `stats = NULL`). Il carry-over esiste
   (`tennis_runner.py:615-625`) ma copre solo un restart, non un riarmo. **Il P&L della
   partita vive li' dentro e li' muore.** E' il catalogo §7.23.
2. **`tennis_live_orders` non ha ne' `pnl` ne' `settled_at` ne' `commission`**
   (`migrations/tennis_orders.sql:80-115`). Non c'e' nessuna RPC `get_tennis_bot_daily`.
   ⚠️ **Una rotta `/storico/tennis` non esiste**: le rotte sono elencate in
   `frontend/src/App.tsx:48-204` e non ce n'e' nessuna `/storico*`. Lo «Storico» e' un TAB
   dentro le pagine dei bot (`frontend/src/components/trading/TradingHistory.tsx:45`), e
   accetta solo `HistoryVariant = 'omega'|'safe'|'mike'`
   (`frontend/src/lib/dailyHistory.ts:121`); lo «storico tennis» di oggi e' il tab di Safe
   Strategy col filtro sport (`frontend/src/pages/SafeStrategy.tsx:1529-1559`), cioe' la
   *strategia tennis di Safe*, non i quattro bot. **I quattro bot sono esclusi per assenza
   del dato, non per un filtro**: i fetcher esistenti sono `get_omega_daily`,
   `get_safe_daily`, `get_mike_daily` e un `get_tennis_bot_daily` non e' mai esistito perche'
   non esiste una tabella da cui prenderlo. Rimedio scritto e **non applicato**:
   `migrations/tennis_bot_pnl_2026-09-17.sql`.
3. **Doppia fonte di verita' sul P&L**: `stats.pnl` / `stats.pnl_settled` (in RAM, lorda,
   per-evento, avvertenza gia' scritta in `frontend/src/lib/tennis.ts:552`) contro il blotter
   di flumine. Nessuna delle due e' netta di commissione.
4. **Il ref dello specchio non e' un riferimento Betfair** (`"bot:" + order.id`): non
   sopravvive a un restart, non si riconcilia con l'order stream, non permette una
   riconciliazione per `bet_id`. E' §7.6 in forma tennis.
5. **Orologio**: corretto il tetto transazioni dello scalper (§E.1 #3); resta che il sidecar
   dei punteggi e' timbrato con `time.time()` locale (`tennis_score.py:260-262`) mentre i book
   portano il `publish_time` di Betfair — skew sistematico dichiarato nel replay.
6. **Parita' paper/live**: `dry_run=True` di default in LIVE rende il percorso live
   inesercitabile; in dry-run i bot registrano posizioni che non esistono (il solo swing
   simula una posizione virtuale, `:180-192`): **il dry-run non e' lo specchio del paper**.
7. **Nessun bot ha una spec numerata propria.** `TENNIS_BOT_DOSSIER.md` e' un ottimo
   documento di handoff ma non e' una Costituzione con regole numerate come
   `COSTITUZIONE_MIKE.md`: i controlli citano il §4 del dossier, non una regola per numero.
8. **La guardia d'avvio C'E'** — verificata, non e' un difetto: `tennis_bot_service.
   ferma_bot_al_nuovo_avvio` (`:47-100`) e' chiamata da `tennis_runner.setup_and_run:1471-1476`
   e da `tennis_bot_service:195`. *(Nota di metodo: la prima ricerca l'aveva data per mancante
   perche' cercava il nome del calcio `ferma_al_nuovo_avvio`. §6.7: prima di accusare, si
   verifica il controllo.)*

---

## G. Che cosa esisteva come backtest, e quanto valeva

| File | Classe usata | Fill | Bet delay | Commissione | Verdetto |
|---|---|---|---|---|---|
| `flb_backtest.py` | **produzione** `TennisFLBStrategy` (`:26,37`) | coda flumine, `simulation_available_prices=False` (`:48-49`) | **no** | **no** (`:52-55`) | veritiero sulla logica, **non certificante** (fuori dal banco) |
| `backtest_pro.py` | sottoclasse della produzione (`:27,34`), ma `process_closed_market` **riscritto** (`:53-59`) senza dedup | coda flumine (`:112-113`) | no | no | logica si, **contabile no** |
| `validate.py` | **lab** `TennisLabStrategy` (`:29`) + swing di produzione (`:30`) | coda flumine | solo nel lab | no | **copia di laboratorio — §7.31** |
| `tennis_lab.py` / `tennis_lab_score.py` | **lab** (`:40`, `:48`) | — | modella 3 s a livello di strategia | — | **§7.31** |
| `lab_grid.py` / `lab_grid_score.py` | **lab** (`:27,152`; `:24,183`) | coda flumine | solo lab | no | **§7.31** |

Il `tennis_lab` **non e' il FLB**: stati diversi, selezione del target diversa, uscite che il
FLB non ha (`lock_trail`, `stop_ticks`, piramide) e maker/taker invertiti rispetto alla
convenzione di casa. **Il verdetto «no edge» della campagna di luglio e' stato prodotto in
gran parte da quella copia, non dai bot di produzione.**

**Dal 17/09 esiste il banco vero**: `Betfair/stream/tennis_live/tools/replay_bot.py` passa dal
servizio di produzione (`tennis_runner._instantiate_bot`), dal punteggio di produzione
(`parse_tennis_scores` alla cadenza del worker) e dallo specchio di produzione
(`_mirror_order`, `_position_row`), col bet delay dormito da flumine e la `place_latency` del
paper tennis.

---

## H. Come si portano nella Control Room (e perche' non basta una riga)

**Oggi i quattro bot NON esistono nel modello della Control Room.** L'unico posto da cui si
accendono e' la scheda per-evento in `/tennis/terminal`
(`frontend/src/components/tennis/TennisBotPanel.tsx:441`), via
`tennis_bot_arm(event_id, bot_key, dry_run, stake, params)`.

I blocchi, in ordine:

1. `frontend/src/lib/controlRoom.ts:34` — `Bot` e' un tipo CHIUSO a `'omega'|'safe'|'mike'`;
   `BOT_LABEL` (`:36-40`) va esteso in parallelo.
2. `frontend/src/lib/interruttori.ts:61-63` — `InterruttoreId` chiuso; `:85-116` —
   `INTERRUTTORI` ha sei voci fisse e nessuna e' un bot tennis (la voce `safe-tennis` e' la
   *strategia tennis di Safe*, un'altra cosa).
3. `frontend/src/lib/interruttori.ts:487-502` — `avviaBot`/`fermaBot` instradano solo a
   omega/mike/safe (l'`else` finale e' Omega).
4. `frontend/src/components/controlroom/useControlRoom.ts:765-778` — `bots` e' costruito con
   tre righe cablate; `:562` e `:1014` iterano `['omega','safe','mike']`.
5. **Il modello di comando e' incompatibile**: la Control Room accende un SERVIZIO globale
   (`mode: paper|live` + `status`), il tennis arma un BOT SU UN EVENTO
   (`dry_run: boolean` + `orderMode` di processo). Serve una decisione dell'utente: o una riga
   «armabile globalmente» (nuova RPC/tabella, tutti gli eventi seguiti), o una riga per evento
   dentro la Control Room.
6. Lo Storico non e' agganciabile finche' il P&L non esiste (§F.2).

**Quando la decisione c'e', il lavoro e' meccanico**: la riga la disegna gia'
`RigaBot` (`frontend/src/components/controlroom/PannelloBot.tsx:257-492`) con i campi
`id, bot, etichetta, acceso, modalita, statoNoto, stato, etaPushS, motivoBlocco, ...`
(`:74-98`), dentro `<Card className="glass-card border-white/10 p-0 overflow-hidden">`
(`:172`), con `STATO_TESTO`/`STATO_CLS` (`:51-67`), il badge «soldi veri» (`:299-308`) e la
doppia conferma live con inerzia 400 ms (`:255`). Nota di design: le schede tennis di oggi
(`TennisBotPanel.tsx:66-91`) hanno un design system PARALLELO (accenti per bot): riusare
`PannelloBot` vuol dire abbandonare quegli accenti o aggiungere un campo accento a
`RigaInterruttore`.

---

## I. LE DIVERGENZE DI STRATEGIA — non le tocco, le porto all'utente

Sono cose che cambierebbero *come opera il bot*. La regola e' che non si alterano di
iniziativa (`CLAUDE.md`). Ognuna e' misurata.

1. **FLB: MAKER dichiarato, TAKER eseguito.** La docstring dice «esecuzione MAKER (rest al
   best-lay)» (`:21`) ma `_place` usa `available_to_lay[0]`, cioe' il prezzo a cui si laya
   SUBITO: incrocia lo spread, alla quota piu' alta = liability massima. In backtest
   (`simulation_available_prices=False`) non incrocia mai e resta in coda; in LIVE si riempie
   all'istante. **Frequenza d'ingresso, prezzo medio e il timeout di 40 s hanno significato
   opposto nei due mondi.** Convenzione di casa opposta: nello scalper il LAY maker sta al
   best-back (`tennis_scalper_bot.py:1233`).
2. **Swing: 7,57 EUR abbandonati** (§E.2 #7). Chiudere il trade solo a esposizione verificata
   dal blotter cambierebbe quando lo swing esce: e' una regola, non un bug di lettura.
3. **Scalper: il micro-residuo accettato si accumula fra cicli** (§E.2 #8). Guardare
   l'esposizione della SELEZIONE invece che quella dello SLOT cambierebbe quando il bot
   riapre il flatten.
4. **FLB e scalper: nessun freno dopo un rifiuto** (§E.2 #10): 8.132 e 20.534 tentativi in
   una partita. Mettere un cooldown e' mettere un tetto dove non c'era.
5. **Pro/FLB/Swing: nessun minimo .it** (§E.3 #11). Arrotondare le size cambierebbe l'importo
   eseguito.
6. **Scalper: con `one_tick_per_phase=True` e `inplay_tick_enabled=False` (il preset), un bot
   armato su una partita GIA' in-play non apre MAI nulla e non lo dice.** Nel replay questo si
   vede subito: con i default di produzione lo scalper fa 0 azioni su 8.602 giri. Non c'e'
   nessuna telemetria che spieghi all'utente perche'.

---

## J. Il replay: comando, numeri, copertura

```
python -m Betfair.stream.backtest.certifica tennis_flb 35794049 \
    --data-dir C:\Users\Admin\Desktop\tennis_rec\20260707 --scenari tutti
```

Partita: **35794049** (Sinner - Struff, 07/07/2026), `COMPLETE 99,1 %`, 8.608 tick,
180 campioni di punteggio, catalogo dichiarato da `_names.json`.
flumine 2.13.11 · betfairlightweight 2.23.2.

| Bot | decisioni | azioni | stati visti | violazioni | mai sollecitati |
|---|---|---|---|---|---|
| `tennis_scalper` | 8.602 | 278 (`gate-aperto`) · 20.534 rifiuti (`rifiuti-betfair`) | IDLE, QUOTING2, LOCKING, CANCELLING, FLATTENING, DONE | **159 (K5)** | 2 (B6 non applicabile, B8 ⊘) |
| `tennis_pro` | 8.602 | 55 (`gate-aperto`) | OPEN, CLOSING | **0** | — |
| `tennis_flb` | 8.602 | 1 (`base`) · 8.132 rifiuti | OPEN, DONE | **0** | — |
| `tennis_swing` | 8.602 | **0 su questa partita** | — | 0 | 13 — ⊘ con causa: il favorito non ha dispersione (`mad <= 0`, `tennis_swing_bot.py:309-310`) e il detector non firma mai |
| `tennis_swing` su 35795739 / 35792939 | — | 13 / 2 | OPEN, CLOSING | **1 (K4)** | — |
| `tennis_swing` su **35790089**, 10 scenari (5.216 tick, COMPLETE) | 5.212 | 56 (`gate-aperto`) · 50 rifiuti | OPEN, CLOSING | **1.168 (K5)** — il reperto §E.2 #7 | — |

**Dieci scenari**, che cambiano **solo** parametri, freschezza del feed o guasti iniettati —
mai la partita, mai i prezzi, mai la strategia:
`base` · `gate-aperto` · `dry-run` · `bot-fermo` (disarm vero a meta' partita con il
`_disable_strategy` di produzione) · `rifiuti-betfair` (trading control di flumine che rifiuta
ogni piazzamento: `place_order` torna False e lo stato diventa `Violation`, come in
`Transaction._validate_controls`) · `feed-stantio` (blackout IPS dopo il primo terzo) ·
`parziali` (stake alto) · `catalogo-assente` (limite 1 del banco) · `live` · **`riavvio`**
(il rebuild dello stream a meta' partita, concesso SOLO a bot flat con la regola di
produzione `_request_restart` / `_strategy_is_flat`; con una posizione aperta viene RINVIATO,
ed e' quello che si e' visto sul FLB di 35794049).

**Controlli**: 18 (famiglie B/K/P), ognuno con `quando=`. Sul bot che opera di piu'
(`tennis_scalper`) restano **2 controlli mai sollecitati su 18**, entrambi dichiarati:
**B6** (regola specifica del FLB, non applicabile) e **B8** (minimi .it — ⊘ perche' in LIVE
`_instantiate_bot` fa nascere il bot in dry-run e nessun ordine parte, §D).

**Falsificazione**: sei difetti reintrodotti uno per uno, **tutti e sei ROSSI**
(`Betfair/stream/tennis_live/tests/test_falsificazione_bot_tennis_2026_09_17.py`, 17 test).

**Il banco gira nella suite**: i quattro bot sono nel `CAMPIONE` di
`Betfair/stream/tests/test_cert_banco_2026_09_16.py` con la registrazione corta 35790407
(1.050 tick, ~8 s a bot, scenari `base,riavvio`). E' un campione **di sola catena** e va detto:
su quella partita i bot non operano. Certifica che il collegamento
`_instantiate_bot` → punteggio → `process_market_book` → ordini su flumine → specchio non si
rompa; **non** certifica la condotta.

---

## K. Che cosa manca prima del paper

1. Decidere i sei punti di §I (sono strategia: li decide l'utente).
2. Chiudere i tre reperti money-critical §E.2 #7, #8, #9.
3. Applicare `migrations/tennis_bot_pnl_2026-09-17.sql` e scrivere il writer che riempie
   `pnl`/`commission`/`settled_at` dal settlement (oggi non esiste).
4. Stabilizzare il ref dello specchio dei bot (§F.4): senza, dopo ogni arm/disarm lo storico
   raddoppia le righe.
5. Decidere il modello di Control Room (§H.5) e poi cablarlo.
6. Un secondo e un terzo evento per il replay, scelti perche' provocano cio' che 35794049
   non provoca (una sospensione lunga con ordini vivi; un favorito con dispersione, per lo
   swing). Oggi lo swing e' gia' girato su 35795739 / 35792939 / 35790089 e proprio li' sono
   usciti i due reperti piu' gravi.
7. Un campione CORTO in cui almeno un bot **apra davvero**, per far girare la condotta nella
   suite e non solo la catena (§J).

Solo dopo si parla di paper. E il paper non autorizza il live: lo autorizza il paper che
conferma (`PROCESSO_STANDARD_BOT.md` gradini 4 e 5).
