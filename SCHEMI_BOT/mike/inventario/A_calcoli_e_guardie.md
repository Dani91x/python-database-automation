# Inventario Mike - AREA A: la matematica e le guardie

**Intervallo letto (per intero, riga per riga)**
- `Betfair/mike/engine.py` righe 1-2494 (dall'inizio fino a PRIMA di `_entry_guard`, riga 2495).
- `Betfair/mike/config.py` righe 1-480 (tutto).
- Letti "quanto basta" fuori area, per capire le chiamate: `Betfair/stream/trading/greenup.py`
  (`compute_greenup`, `GreenupPlan`, `_place_through`, `FLAT_EPS`), `Betfair/stream/live_order_build.py`
  (`round_to_tick`, `ticks_away`), `Betfair/stream/scalper/scalper_bot.py` (`ticks_between`),
  `engine.py` 2880-2908, 3296-3385, 3500-3584 (chi usa le formule della copertura e delle uscite),
  `service.py` 740-760 e 1255-1276 (legalizzazione degli importi e valvola della lay appoggiata in live).
- Costituzione: `Betfair/mike/COSTITUZIONE_MIKE.md` §0-§7 e §15 (righe 1-481 e 1165-1560).

**Numero di schede: 128** (1-115 logiche e dati, 116-127 parametri di `config.py` per gruppo, 128 costanti
d'ambiente). Nessuna funzione, classe o costante dell'intervallo e' rimasta senza scheda.

## Elenco di TUTTO cio' che c'e' nell'intervallo, con la scheda che lo copre

### engine.py (righe 1-2494)
| Nome | Riga | Scheda |
|---|---|---|
| `MARKET_OU35`, `MARKET_OU45`, `SEL_UNDER`, `SEL_OVER`, `LINE` | 30-35 | 1 |
| `STATES`, `TERMINAL_STATES` | 37-44 | 2 |
| `ROLES`, `OPENING_ROLES`, `CLOSING_ROLES`, `UNDER_ROLES`, `STATUS_RECONCILE`, `EXIT_KINDS` | 46-65 | 3 |
| `IT_BACK_MIN`, `IT_BACK_STEP`, `SUBMIN_FLOOR`, `_EPS`, `_FLAT_EPS` | 67-75 | 4 |
| classe `Book` | 81-91 | 5 |
| classe `Leg` (+ `remaining`, `is_live`, `needs_reconcile`, `filled`, `fill_price`) | 94-155 | 6 |
| classe `Snapshot` (+ `book`) | 158-214 | 7 |
| classe `MatchCtx` | 217-356 | 8 |
| classe `Action` | 359-372 | 9 |
| classe `Decision` | 375-381 | 10 |
| classe `CashoutValue` | 384-394 | 11 |
| classe `SettleResult` | 397-403 | 12 |
| `green_target` | 409 | 13 |
| `locked_pnl_back` | 414 | 14 |
| `cover_size` | 419 | 15 |
| `cover_residual` | 426 | 16 |
| `cover_size_residual` | 438 | 17 |
| `cover_matched_value` | 446 | 18 |
| `under_liability` | 459 | 19 |
| `legalize_back_size` | 468 | 20 |
| `cover_legal_size` | 486 | 21 |
| `needs_submin` | 509 | 22 |
| `cycle_label` | 519 | 23 |
| `STATO_APERTO`, `STATO_SOSPESO`, `STATO_CHIUSO`, `STATO_IGNOTO`, `stato_mercato` | 550-569 | 24 |
| `operabile` | 572 | 25 |
| `appoggiabile_in_gioco` | 577 | 26 |
| `riaprira` | 590 | 27 |
| `price_ok` | 599 | 28 |
| `size_ok` | 617 | 29 |
| `selection_wins` | 628 | 30 |
| `selection_decided` | 635 | 31 |
| `exposure` | 649 | 32 |
| `open_selections` | 668 | 33 |
| `live_open_selections` | 678 | 34 |
| `position` | 684 | 35 |
| `invested` | 700 | 36 |
| `_market_pnl_by_total`, `_net` | 707, 722 | 37 |
| `net_pnl_by_total` | 726 | 38 |
| `cashout_value` | 737 | 39 |
| `MAX_CANCELLED_PER_ROLE` | 810 | 41 |
| `pnl_indipendente_dal_risultato` | 813 | 40 |
| `prune_dead_legs` | 848 | 41 |
| `drift_ticks` | 888 | 42 |
| `active_legs` | 913 | 43 |
| `_assume_matched` | 918 | 44 |
| `event_liability` | 938 | 45 |
| `locked_pnl` | 950 | 46 |
| `exit_kind_for` | 971 | 47 |
| `opening_ref` | 993 | 48 |
| `should_cashout` | 1004 | 49 |
| `loss_exit_ok` | 1010 | 50 |
| `_PROB_KEY`, `_DEAD_PRICE`, `_prob_utilizzabile` | 1018-1034 | 51 |
| `projected_books` | 1037 | 52 |
| `smart_cashout` | 1075 | 53 |
| `blend_totals` | 1135 | 54 |
| `hold_expectation` | 1146 | 55 |
| `loss_exit_model` | 1171 | 56 |
| `cover_timing` | 1212 | 57 |
| `winners_from_total` | 1254 | 58 |
| `settle_legs` | 1260 | 59 |
| `settle_legs_by_market` | 1265 | 60 |
| `pnl_cicli_chiusi` | 1351 | 61 |
| `riepilogo_cicli` | 1370 | 62 |
| `posizione_per_selezione` | 1413 | 63 |
| `_legs`, `_last` | 1464, 1477 | 64 |
| `_cancel_live` | 1482 | 65 |
| `_place` | 1487 | 66 |
| `chiave_richiesta` | 1494 | 67 |
| `registra_rifiuto` | 1501 | 68 |
| `tentativo_gia_rifiutato` | 1522 | 69 |
| `motivo_del_rifiuto` | 1558 | 70 |
| `COVER_BLOCCATA`, `_cover_rifiuti` | 1587, 1590 | 71 |
| `registra_rifiuto_copertura` | 1595 | 72 |
| `copertura_bloccata` | 1618 | 73 |
| `segna_tentativo_copertura` | 1624 | 74 |
| `attesa_ritento_copertura` | 1638 | 75 |
| `sblocca_copertura` | 1653 | 76 |
| `copertura_in_corso` | 1661 | 77 |
| `_under_position` | 1672 | 78 |
| `cashout_base`, `_cashout_base` | 1676, 1684 | 79 |
| `cover_place_price` | 1687 | 80 |
| `liability_room` | 1707 | 81 |
| `size_chiudibile` | 1717 | 82 |
| `ordini_vivi_su` | 1737 | 83 |
| `_close_actions` | 1754 | 84 |
| `MANUAL_ROLE_MAP`, `force_flat_plan` | 1786, 1791 | 85 |
| `force_flat_actions` | 1808 | 86 |
| `_pending_closings` | 1815 | 87 |
| `has_unknown_orders` | 1822 | 88 |
| `ha_esposizione` | 1827 | 89 |
| `_strip_openings` | 1854 | 90 |
| `lay_in_volo` | 1882 | 91 |
| `_una_sola_lay` | 1901 | 92 |
| `copertura_in_volo` | 1954 | 93 |
| `_mai_sovracopertura` | 1972 | 94 |
| `_freno_copertura` | 2023 | 95 |
| `_decide_flatten` | 2077 | 96 |
| `decide` | 2164 | 97 |
| `USCITE_DISCREZIONALI`, `MOTIVI_PROTEZIONE`, `STATI_USCITA_IN_CORSO`, `_CANCEL_SEMPRE`, `APPROVAZIONE_TTL_S` | 2225-2240 | 98 |
| `uscite_automatiche` | 2243 | 99 |
| `categoria_uscita` | 2251 | 100 |
| `chiave_uscita` | 2265 | 101 |
| `_uscita_gia_in_corso` | 2269 | 102 |
| `_approvazione_valida` | 2288 | 103 |
| `_stessa_uscita_firmata` | 2298 | 104 |
| `_con` | 2313 | 105 |
| `_decadi` | 2317 | 106 |
| `gate_uscite` | 2337 | 107 |
| `_dispatch` | 2435 | 108 |

### config.py (tutto)
| Nome | Riga | Scheda |
|---|---|---|
| `OU35`, `OU45`, `FOOTBALL_EVENT_TYPE_ID`, `EXPECTED_SEL`, `CUSTOMER_STRATEGY_REF`, `LOCK_PORT_DEFAULT` | 17-32 | 109 |
| `env_str`, `env_int`, `env_float`, `env_bool` | 38-66 | 110 |
| `Spec`, `PARAM_SPEC`, `DEFAULTS` | 73-379, 426 | 111 |
| `_coerce` | 429 | 112 |
| `_ORDERED_PAIRS`, `merge_params` | 455, 462 | 113 |
| `commission_rate` | 479 | 114 |
| `REMOVED_PARAMS`, `BACKEND_ONLY_PARAMS` | 398, 424 | 115 |
| i 106 parametri di `PARAM_SPEC` | 77-378 | 116-127 |
| variabili d'ambiente lette con gli aiuti di config | - | 128 |

---

## PARTE 1 - COME IL BOT "VEDE" UNA PARTITA (i dati)

### 1. I due mercati e le tre selezioni
- **Cosa fa**: da' un nome fisso ai due mercati che Mike tratta e alle selezioni. `OU35` = mercato Over/Under 3.5 (Mike punta l'UNDER). `OU45` = mercato Over/Under 4.5 (Mike ci compra la copertura OVER e, nel re-ingresso, punta l'UNDER 4.5). La "linea" di ogni mercato: 3.5 e 4.5.
- **Quando scatta**: sempre, sono nomi di riferimento.
- **Cosa succede dopo**: niente; servono a tutti i conti (chi vince con quanti gol).
- **Numeri**: `LINE = {OU35: 3.5, OU45: 4.5}` (costante nel codice).
- **Esempio**: 4 gol -> Under 3.5 perde (4 > 3.5), Under 4.5 vince (4 < 4.5), Over 4.5 perde.
- **Cosa vede l'utente**: i nomi "OU35|UNDER", "OU45|OVER" nelle chiavi della telemetria del cash out.
- **Dove**: `engine.py:30-35`.
- **Paper o live**: uguale.

### 2. Gli stati della partita (le "fasi")
- **Cosa fa**: elenca le 21 fasi in cui una partita puo' trovarsi, e quali sono "finite per sempre".
- **Quando scatta**: sempre; il motore sceglie la regola da applicare in base alla fase (scheda 108).
- **Cosa succede dopo**: le tre fasi finali (`SETTLED`, `ERROR`, `SKIPPED`) non fanno piu' nulla (scheda 97).
- **Numeri**: 21 stati: WATCH, PRE_ENTRY_PENDING, PRE_OPEN, PRE_GREEN_PENDING, HOLD, PRE_LAST_ENTRY_PENDING, IDLE_LIVE, LIVE_KO_GREEN, LIVE_SECOND_ENTRY, LIVE_UNCOVERED, LIVE_COVER_PENDING, LIVE_COVERED, LIVE_CLOSING, FLAT, REENTRY_PENDING, REENTRY_OPEN, REENTRY_GREEN_PENDING, SETTLING, SETTLED, ERROR, SKIPPED. Terminali: SETTLED, ERROR, SKIPPED.
- **Esempio**: partita regolata -> `SETTLED`: il motore risponde "terminale" e basta.
- **Cosa vede l'utente**: il nome della fase sulla card (traduzione nel Glossario).
- **Dove**: `engine.py:37-44`.
- **Paper o live**: uguale.

### 3. I ruoli delle scommesse ("gambe") e i tipi di uscita
- **Cosa fa**: ogni ordine del bot porta un "ruolo" che dice a cosa serve. Il codice divide i ruoli in: aperture (aggiungono rischio), chiusure (lo riducono), e le puntate Under che formano "il nostro prezzo d'ingresso". Definisce anche lo stato speciale "esito ignoto" e i tipi di uscita mostrati nella scheda Trade.
- **Quando scatta**: sempre.
- **Cosa succede dopo**: le guardie usano questi elenchi: es. con un ordine a esito ignoto si tolgono tutte le "aperture" (scheda 90).
- **Numeri**: 11 ruoli (`ROLES`). Aperture (`OPENING_ROLES`): under_entry, under_last, under_second, over_cover, reentry. Chiusure (`CLOSING_ROLES`): under_green, ko_green, under_close, over_close, reentry_green, manual_close. Puntate Under che fanno il prezzo medio (`UNDER_ROLES`): under_entry, under_last, under_second. `STATUS_RECONCILE = "pending_reconcile"`. Tipi di uscita (`EXIT_KINDS`): greenup, profit, loss, time, forced, manual, other.
- **Esempio**: la copertura Over 4.5 (`over_cover`) e' un'APERTURA per il codice: con un ordine a esito ignoto anche la copertura viene bloccata.
- **Cosa vede l'utente**: i ruoli compaiono nelle righe della scheda Trade e nell'Attivita'.
- **Dove**: `engine.py:46-65`.
- **Paper o live**: uguale.

### 4. Gli importi minimi e le tolleranze di calcolo
- **Cosa fa**: fissa il minimo di una puntata diretta sul sito italiano (2,00 euro, a passi di 0,50), il minimo assoluto di un ordine (1 centesimo) e due piccole tolleranze.
- **Quando scatta**: quando si legalizza un importo (schede 20, 22) e quando si decide se una posizione e' "piatta" (scheda 33).
- **Cosa succede dopo**: vedi schede collegate.
- **Numeri**: `IT_BACK_MIN = 2.0` euro; `IT_BACK_STEP = 0.5` euro; `SUBMIN_FLOOR = 0.01` euro; `_EPS = 1e-9` (tolleranza di arrotondamento); `_FLAT_EPS = 0.01` euro (sotto 1 centesimo di differenza fra "se vince" e "se perde" la selezione e' considerata piatta). Tutte costanti nel codice, non modificabili dalla UI.
- **Esempio**: una posizione con +0,14 se vince e +0,14 se perde -> differenza 0 -> piatta.
- **Cosa vede l'utente**: niente di diretto.
- **Dove**: `engine.py:67-75`.
- **Paper o live**: uguale.

### 5. La fotografia di una selezione (`Book`)
- **Cosa fa**: per una selezione tiene: miglior quota a cui si puo' puntare (back) e quanto c'e', miglior quota a cui si puo' bancare (lay) e quanto c'e', stato del mercato (OPEN, SUSPENDED, CLOSED...), se e' in gioco, ritardo di piazzamento (bet delay) in secondi.
- **Quando scatta**: a ogni giro il servizio la costruisce dal feed.
- **Cosa succede dopo**: e' la base di ogni prezzo usato dal motore.
- **Numeri**: default: `back_size 0`, `lay_size 0`, `status "OPEN"`, `inplay False`, `bet_delay 0`.
- **Esempio**: Under 3.5: back 1,50 (120 euro disponibili), lay 1,52 (80 euro), OPEN, non in gioco.
- **Cosa vede l'utente**: le quote nella card.
- **Dove**: `engine.py:81-91`.
- **Paper o live**: uguale (la fonte e' lo stesso feed).

### 6. Una scommessa del bot (`Leg`, "gamba")
- **Cosa fa**: rappresenta un ordine del bot o la posizione che ne e' nata: ruolo, mercato, selezione, punta/banca, quota chiesta, importo chiesto, importo abbinato, quota media abbinata, identificativo, stato, momento del piazzamento, persistenza (LAPSE = muore alla sospensione, PERSIST = resta in gioco), numero di ciclo, se e' "finale", se e' archiviata (ciclo pre-match gia' chiuso), e quale apertura sta chiudendo.
- **Quando scatta**: sempre.
- **Cosa succede dopo**: i conti usano SOLO l'abbinato, mai l'importo chiesto.
- **Numeri / regole**:
  - stati: `pending` (vivo sul mercato, anche se in parte abbinato), `pending_reconcile` (esito ignoto), `open` (non piu' vivo: abbinato tutto oppure residuo ritirato con abbinato > 0), `cancelled` (mai abbinato e ritirato), `settled` (regolato).
  - `remaining` = importo chiesto - abbinato (mai negativo).
  - `is_live` = vero SOLO se stato `pending` (un ordine a esito ignoto NON e' "vivo" per il bot: niente ritiro, niente riprezzo).
  - `needs_reconcile` = stato `pending_reconcile`.
  - `filled` = abbinato >= chiesto - 0,005 euro, oppure stato `open` con abbinato > 0.
  - `fill_price` = quota media abbinata se c'e', altrimenti la quota chiesta.
  - `archived` = la gamba resta per la contabilita' ma non conta piu' come capitale a rischio.
- **Esempio**: punta 10 euro a 1,50, abbinati 6: `remaining` 4, `is_live` vero, `filled` falso.
- **Cosa vede l'utente**: le righe della scheda Trade.
- **Dove**: `engine.py:94-155`.
- **Paper o live**: la struttura e' la stessa; cambia chi riempie `matched` (simulatore paper o Betfair).

### 7. La fotografia del momento (`Snapshot`)
- **Cosa fa**: tutto cio' che il motore sa "adesso": ora, ora del calcio d'inizio, i book, in gioco si/no, minuto, gol, intervallo, freschezza del feed per guardare e (piu' stretta) per mandare ordini, da dove vengono i prezzi, probabilita' di gol nei prossimi 3 minuti (hazard), probabilita' dei 4 gol (mercato e modello), ora dell'ultimo gol, stato del mercato, totale gol finale, scambiato totale (solo diagnostica), risparmio atteso sulla copertura, pressione (corner/cartellini), probabilita' di modello per tre scenari, distribuzioni dei gol totali (modello, empirica, mercato), probabilita' calibrata dell'Under 3.5 dal dossier.
- **Quando scatta**: il servizio la ricostruisce a ogni giro.
- **Cosa succede dopo**: e' l'unico ingresso di dati del motore.
- **Numeri**: default `inplay False`, `ht_active False`, `feed_fresh True`, `order_fresh True`, `fonte_prezzi "feed"` (alternativa `"rest_ripiego"`: scanner fermo, book letto da REST solo per chiudere/coprire; con il ripiego `order_fresh` resta falso -> nessuna apertura), `pressure 1.0` (neutra; il commento dice ">= 1.0"), `market_status "OPEN"`. `total_matched` NON governa nulla. `model_probs` usa chiavi `u35_now`, `u35_goal`, `u35_later` ecc. Distribuzioni dei gol: chiavi 0..8 (8 = 8 o piu').
- **Esempio**: minuto 30, 0 gol, hazard 0,06, P(4) mercato 0,12.
- **Cosa vede l'utente**: minuto, gol, eta' del feed nella card.
- **Dove**: `engine.py:158-214`; `book(market, selection)` a riga 213.
- **Paper o live**: uguale.

### 8. La memoria della partita (`MatchCtx`)
- **Cosa fa**: cio' che il bot ricorda di una partita fra un giro e l'altro (salvato sul database).
- **Quando scatta**: sempre.
- **Cosa succede dopo**: ogni decisione legge e aggiorna questi campi.
- **Numeri / campi (default fra parentesi)**:
  - `state` ("WATCH"), `legs` (vuota), `cycle_no` (0 = primo ciclo in corso), `entry_price_initial`, `last_green_at`, `last_action_at`, `attempts` (0), `reentry_allowed`/`reentry_done` (falso), `close_reason`, `cover_skipped`, `seq` (numerazione degli ordini), `settled_pnl`.
  - `flatten_pending`: chiusura manuale in corso (scheda 96).
  - `no_reentry`: dopo un cash out manuale il bot non rientra finche' l'utente non preme "Riprendi".
  - `ko_price_under`: quota Under al fischio, registrata una volta sola.
  - `live_since`: quando la partita e' stata vista in gioco con Under aperto (da li' parte la finestra dell'uscita al fischio).
  - `ko_goals`: gol al fischio (base per riconoscere il gol precoce); `early_goal_at`: momento del gol precoce; `second_entry_done`: seconda puntata gia' tentata (mai due volte).
  - `cover_stage`: 0 = copertura in una volta; 1 = prima tranche da comprare; 2 = prima tranche abbinata, si aspetta; 3 = seconda tranche (il residuo). `cover_stage1_at`: quando si e' abbinata la prima tranche. `cover_forced`: copertura ordinata dal flusso (salta l'attesa "intelligente").
  - `rifiuti`: l'ultima richiesta rifiutata dal mercato per ogni gamba (scheda 68).
  - `cover_rifiuti`: il conteggio dei rifiuti della copertura per codice d'errore (schede 71-76).
  - `cover_mercato`: ultimo stato visto del mercato 4.5 durante una copertura.
  - `aperture_ferme`: aperture bloccate per una causa che non e' il mercato (modo ordini non LIVE, kill-switch, runner paper giu'): finche' c'e', si tolgono le aperture (scheda 97).
  - `riapertura`: memoria di una sospensione con la lay appoggiata viva ("letto" vero/falso dopo la rilettura da Betfair).
  - `chiuso_dall_utente`: l'utente ha chiuso la posizione FUORI dall'app -> il bot non fa piu' nulla su quella partita (scheda 97).
  - `uscita_proposta` / `uscita_approvata`: proposta di uscita mostrata all'utente e sua firma (schede 98-107).
  - `veto_u35`: il veto sulla probabilita' calibrata dell'Under 3.5 e' scattato (niente ultimo ingresso PERSIST).
- **Esempio**: dopo un gol al 12' con Under aperto: `early_goal_at` = ora del gol, `cover_stage` = 1.
- **Cosa vede l'utente**: indirettamente (fase, motivo, proposte).
- **Dove**: `engine.py:217-356`.
- **Paper o live**: uguale.

### 9. Un ordine da fare (`Action`)
- **Cosa fa**: cio' che il motore chiede al servizio: "piazza" o "ritira", con ruolo, mercato, selezione, punta/banca, quota, importo, persistenza (default LAPSE), gamba da ritirare, "finale", nota, gamba che si sta chiudendo.
- **Quando scatta / dopo**: il servizio le esegue nell'ordine.
- **Numeri**: `persistence` default "LAPSE".
- **Esempio**: piazza banca Under 3.5 10,14 a 1,48.
- **Cosa vede l'utente**: le righe nuove in Trade.
- **Dove**: `engine.py:359-372`.
- **Paper o live**: uguale.

### 10. La decisione di un giro (`Decision`)
- **Cosa fa**: fase successiva + elenco ordini + motivo scritto + campi della memoria da aggiornare + dati per la pagina (telemetria).
- **Dove**: `engine.py:375-381`. **Paper o live**: uguale. Nessun numero proprio.
- **Esempio**: fase `LIVE_CLOSING`, due ordini di chiusura, motivo "profit: 0.75 >= 5.0% di 12.26".
- **Cosa vede l'utente**: il motivo compare nell'Attivita' e sulla card.

### 11. Il valore del cash out (`CashoutValue`)
- **Cosa fa**: contiene il valore NETTO di commissione se si chiudesse tutto adesso, il valore lordo, il valore per selezione (lordo e netto), l'ordine di chiusura previsto per ogni selezione, se il calcolo e' completo (tutte le selezioni vive hanno un prezzo), e le selezioni gia' decise dai gol.
- **Dove**: `engine.py:384-394`. Riempito da `cashout_value` (scheda 39).
- **Esempio / utente**: vedi scheda 39. **Paper o live**: uguale.

### 12. L'esito del regolamento (`SettleResult`)
- **Cosa fa**: per ogni gamba (identificativo, vinta/persa/nulla, P&L netto commissione), netto per mercato, netto totale, P&L lordo per gamba e commissione per mercato.
- **Dove**: `engine.py:397-403`. Riempito da `settle_legs_by_market` (scheda 60).
- **Paper o live**: uguale.

---

## PARTE 2 - I CALCOLI (matematica pura)

### 13. Quota del green-up: N tick sotto l'ingresso
- **Cosa fa**: dato il prezzo a cui abbiamo puntato l'Under, calcola la quota N tick piu' bassa sulla scala ufficiale Betfair: e' la quota della bancata di chiusura in profitto.
- **Quando scatta**: la usano il green pre-match, l'uscita al fischio e il re-ingresso (fuori area, `engine.py` 2751, 2763, 2825, 2994, 3718, 3774).
- **Cosa succede dopo**: nessun ordine qui; restituisce solo la quota.
- **Numeri**: N = `pre_green_ticks` (2), `ko_green_ticks` (2) o `reentry_green_ticks` (2), a seconda di chi la chiama.
- **Esempio**: ingresso 1,50, 2 tick -> 1,48 (fra 1,01 e 2,00 un tick vale 0,01).
- **Cosa vede l'utente**: la quota della bancata di uscita.
- **Dove**: `engine.py:409-411` (usa `ticks_away` di `live_order_build.py:95`, che prima arrotonda al tick valido).
- **Paper o live**: uguale.

### 14. Profitto bloccato chiudendo una punta con una bancata
- **Cosa fa**: con punta S a quota Pe chiusa con bancata a quota p, il profitto lordo uguale su tutti gli esiti e' S x (Pe/p - 1).
- **Quando scatta**: usata una volta, fuori area (`engine.py:2842`, ultimo ingresso: capire se la posizione e' in profitto).
- **Numeri**: nessun parametro.
- **Esempio**: 10 euro a 1,50 chiusi a 1,48 -> 10 x (1,50/1,48 - 1) = +0,135 euro lordi.
- **Dove**: `engine.py:414-416`. **Utente**: niente. **Paper o live**: uguale.

### 15. Importo della copertura Over 4.5 (formula base)
- **Cosa fa**: importo X da puntare sull'Over 4.5 perche', se finisce con 5+ gol, il netto dell'Over valga (fattore) x S. Formula: X = fattore x S / ((quota Over - 1) x (1 - commissione)).
- **Quando scatta**: MAI in produzione: nessun ramo del bot la chiama (solo i test `tests/test_mike_engine.py`, `test_mike_engine_cert_2026_09_12.py`). La copertura vera usa `cover_residual` (scheda 16).
- **Cosa succede dopo**: se la quota Over manca o e' <= 1,0 -> errore (eccezione).
- **Numeri**: fattore = `cover_profit_factor` (1,2); commissione = `commission_pct` (5%).
- **Esempio**: S 10, Over 6,6: 1,2 x 10 / (5,6 x 0,95) = 2,26 euro.
- **Dove**: `engine.py:419-423`. **Utente**: niente. **Paper o live**: uguale.

### 16. Importo RESIDUO della copertura (quella usata davvero)
- **Cosa fa**: come la scheda 15, ma parte dalla perdita netta dell'Under (non dall'importo puntato) e toglie quanto le coperture gia' abbinate garantiscono gia'. Obiettivo: con 5+ gol l'Over vale fattore x perdita-Under. Mai negativo.
- **Quando scatta**: ogni volta che si dimensiona la copertura (fuori area `engine.py:3333`, `3481`, `3587`; anche `certificazione.py`).
- **Cosa succede dopo**: restituisce l'importo; se la quota Over manca o e' <= 1 -> errore.
- **Numeri**: residuo = (fattore x liability - gia'_garantito) / ((quota - 1) x (1 - commissione)); fattore `cover_profit_factor` 1,2.
- **Esempio**: perdita Under 10, Over 6,6, gia' garantito 0 -> 2,26. Se una prima tranche ha gia' garantito 6,00: (12 - 6)/5,32 = 1,13 euro.
- **Dove**: `engine.py:426-435`. **Utente**: l'importo della copertura. **Paper o live**: uguale.

### 17. Residuo dopo un abbinamento parziale (versione a due numeri)
- **Cosa fa**: calcola "gia' garantito" da un solo abbinamento parziale (abbinato x (quota - 1) x (1 - commissione)) e chiama la scheda 16.
- **Quando scatta**: MAI in produzione (nessun chiamante fuori dai test). Superata da `cover_matched_value` (scheda 18).
- **Dove**: `engine.py:438-443`. **Esempio**: 1 euro abbinato a 6,6 -> gia' garantito 5,32. **Utente**: niente. **Paper o live**: uguale.

### 18. Quanto la copertura GIA' abbinata protegge con 5+ gol
- **Cosa fa**: somma, su tutte le gambe non archiviate del mercato 4.5 (coperture, eventuali bancate di chiusura, re-ingresso Under 4.5), il risultato con esattamente 5 gol, e toglie la commissione sul netto positivo del mercato.
- **Quando scatta**: quando si dimensiona la copertura (fuori area 3300, 3440, 3476).
- **Cosa succede dopo**: il numero entra come "gia' garantito" nella scheda 16: non si ricompra Over gia' comprato.
- **Numeri**: commissione `commission_pct` 5%; arrotondamento a 6 decimali.
- **Esempio**: Over 2,26 a 6,6 abbinato: 2,26 x 5,6 = 12,66 lordi -> 12,02 netti.
- **Dove**: `engine.py:446-456`. **Utente**: niente di diretto. **Paper o live**: uguale.

### 19. Quanto perdo sull'Under 3.5 se l'Under perde
- **Cosa fa**: dalla posizione netta abbinata sull'Under 3.5 (punte meno eventuali bancate parziali), l'importo perso se l'Under perde. E' la base della copertura.
- **Quando scatta**: dimensionamento copertura (fuori area 3033, 3299, 3475) e guardia delle lay (commento).
- **Numeri**: arrotondato al centesimo, mai negativo.
- **Esempio**: punta 10 a 1,50 -> 10,00. Se una bancata di green ha abbinato 4 euro -> 6,00: la copertura si calcola su 6, non su 10.
- **Dove**: `engine.py:459-465`. **Utente**: niente. **Paper o live**: uguale.

### 20. Importo "legale" sul sito italiano (arrotondamento a 2,00 / 0,50)
- **Cosa fa**: porta un importo al minimo di 2,00 euro e a multipli di 0,50, e dice di quanto (in %) si e' ecceduto.
- **Quando scatta**: solo se gli "importi esatti" sono SPENTI: per la copertura (scheda 21 e il ripiego "floor" a `engine.py:3375`) e per le punte di apertura in `service.py:746-751`.
- **Numeri**: modo `cover_rounding` = "ceil" (per eccesso, default), "floor" (per difetto), "nearest" (al piu' vicino); minimo 2,00; passo 0,50. Importo <= 0 o non finito -> (0, 0).
- **Esempio**: 1,35 per eccesso -> 1,50, alzato al minimo 2,00; eccesso (2,00/1,35 - 1) = +48,15%.
- **Dove**: `engine.py:468-483`. **Utente**: attivita' `size_legalized` (dal servizio). **Paper o live**: uguale (dipende solo da `exact_sizes`).

### 21. Importo effettivo della copertura
- **Cosa fa**: con "importi esatti" ACCESI (default) la copertura e' l'importo calcolato arrotondato al centesimo, eccesso 0%. Con importi esatti SPENTI la legalizza (scheda 20).
- **Quando scatta**: ogni copertura (fuori area 3337, 3369, 3490).
- **Numeri**: `exact_sizes` True; `cover_rounding` "ceil".
- **Esempio**: 1,354 -> 1,35 (esatti accesi); 2,00 (esatti spenti).
- **Dove**: `engine.py:486-506`. **Utente**: importo della copertura. **Paper o live**: il calcolo e' uguale; in live un importo sotto 2 euro passa dal "place-and-trim" (fuori area).

### 22. Questa punta ha bisogno del "place-and-trim"?
- **Cosa fa**: vero se una PUNTA ha un importo sotto 2,00 euro o non multiplo di 0,50 (ci vuole la tecnica parcheggia-taglia-riprezza). Una bancata risponde sempre falso.
- **Quando scatta**: solo in `service.py:746` quando `exact_sizes` e' spento, per legalizzare le punte.
- **Numeri**: 2,00 / 0,50, tolleranza 0,005.
- **Esempio**: 1,23 -> vero; 2,30 -> vero; 2,50 -> falso.
- **Dove**: `engine.py:509-516`. **Utente**: niente. **Paper o live**: uguale.

### 23. Numero di ciclo "come lo legge il trader"
- **Cosa fa**: il codice conta i cicli chiusi da 0; nei testi per l'utente si scrive da 1.
- **Esempio**: `cycle_no` 0 -> "ciclo 1"; numeri negativi -> 1.
- **Dove**: `engine.py:519-532`; usata in 1399, 2674, 2852. **Utente**: "ciclo N" nei motivi. **Paper o live**: uguale.

---

## PARTE 3 - LO STATO DEL MERCATO, IL PREZZO E L'IMPORTO VALIDI

### 24. In che stato e' il mercato (aperto / sospeso / chiuso / ignoto)
- **Cosa fa**: traduce lo stato Betfair in quattro casi: OPEN = aperto; SUSPENDED = sospeso (riapre, si aspetta); CLOSED o INACTIVE = chiuso; qualunque altra cosa o book mancante = ignoto (non si opera e non si rinuncia).
- **Quando scatta**: ogni volta che serve sapere se si puo' operare.
- **Numeri**: costanti `STATO_APERTO "aperto"`, `STATO_SOSPESO "sospeso"`, `STATO_CHIUSO "chiuso"`, `STATO_IGNOTO "ignoto"`.
- **Esempio**: book assente -> "ignoto"; "suspended" (minuscolo) -> sospeso (maiuscole forzate).
- **Cosa vede l'utente**: es. "copertura: mercato Over 4.5 sospeso, si aspetta la riapertura".
- **Dove**: `engine.py:550-569`. **Paper o live**: uguale.

### 25. Si puo' mandare un ordine adesso?
- **Cosa fa**: si' solo se il mercato e' APERTO. Nel dubbio no.
- **Dove**: `engine.py:572-574`. **Esempio**: sospeso -> no. **Utente**: attese dichiarate nei motivi dei rami. **Paper o live**: uguale.

### 26. Si puo' APPOGGIARE un ordine che deve restare sul book?
- **Cosa fa**: si' solo se il mercato e' aperto E gia' in gioco. Motivo: al fischio Betfair sospende e cancella gli ordini non abbinati; un ordine appoggiato prima morirebbe subito.
- **Quando scatta**: uscita al fischio (fuori area 2976, 2979, 3075).
- **Esempio**: aperto ma non ancora in gioco -> no, si aspetta.
- **Dove**: `engine.py:577-587`. **Paper o live**: uguale.

### 27. Vale la pena aspettare che riapra?
- **Cosa fa**: si' se sospeso o ignoto; no se chiuso.
- **Dove**: `engine.py:590-596`; usata in 2873, 3080. **Esempio**: ignoto -> si' (aspettare costa un giro, rinunciare costa un'uscita). **Paper o live**: uguale.

### 28. La quota e' utilizzabile?
- **Cosa fa**: vera solo se la quota c'e', e' un numero finito e > 1,0. Protegge da quote vuote, "NaN" o 0 del feed.
- **Dove**: `engine.py:599-614`. **Esempio**: 0 -> no; NaN -> no; 1,01 -> si'. **Utente**: prezzo mancante = nessuna azione. **Paper o live**: uguale.

### 29. L'importo e' piazzabile?
- **Cosa fa**: vero se e' un numero finito >= 0,01 euro (mai ordini da 0,00).
- **Dove**: `engine.py:617-625`. **Esempio**: 0,004 -> no; 0,01 -> si'. **Paper o live**: uguale.

---

## PARTE 4 - POSIZIONE, ESPOSIZIONE E P&L PER NUMERO DI GOL

### 30. Chi vince con T gol
- **Cosa fa**: Under vince se T < linea; Over vince se T > linea.
- **Esempio**: T=3: Under 3.5 vince; T=5: Over 4.5 vince.
- **Dove**: `engine.py:628-632`. **Paper o live**: uguale.

### 31. L'esito e' GIA' deciso dai gol segnati?
- **Cosa fa**: i gol non si tolgono: appena i gol superano la linea l'Over ha vinto e l'Under ha perso, qualunque cosa faccia il mercato. Sotto la linea niente e' deciso.
- **Numeri**: gol mancanti -> "non so".
- **Esempio**: 4 gol: Under 3.5 = persa; Over 4.5 = non ancora decisa.
- **Dove**: `engine.py:635-646`. **Utente**: la colonna "decisa" della posizione. **Paper o live**: uguale.

### 32. Esposizione di una selezione ("se vince" / "se perde")
- **Cosa fa**: somma, dai soli abbinamenti e saltando le gambe archiviate, quanto si guadagna se la selezione vince (W) e se perde (L). Punta: W += importo x (quota - 1), L -= importo. Bancata: il contrario.
- **Esempio**: punta 10 a 1,50: W +5,00, L -10,00. Piu' bancata 10,14 a 1,48 abbinata: W +0,13, L +0,14.
- **Dove**: `engine.py:649-665`. **Utente**: "se vince / se perde" nella card. **Paper o live**: uguale.

### 33. Quali selezioni sono ancora aperte
- **Cosa fa**: fra Under 3.5, Over 4.5 e Under 4.5 (in quest'ordine) tiene quelle dove W e L differiscono di almeno 1 centesimo.
- **Dove**: `engine.py:668-675`. **Esempio**: dopo un green perfetto W=L -> non aperta. **Paper o live**: uguale.

### 34. Selezioni aperte ANCORA gestibili
- **Cosa fa**: come la 33 ma toglie quelle il cui esito e' gia' deciso dai gol (nessun prezzo, nessuna azione possibile).
- **Dove**: `engine.py:678-681`. **Esempio**: 4 gol con Under 3.5 aperto -> l'Under esce dall'elenco. **Paper o live**: uguale.

### 35. Posizione: importo abbinato e quota media delle punte di apertura
- **Cosa fa**: somma gli importi abbinati delle PUNTE di certi ruoli su una selezione (non archiviate) e ne fa la quota media pesata.
- **Esempio**: 10 a 1,50 + 5 a 1,95 -> 15 euro a 1,65.
- **Dove**: `engine.py:684-697`. **Utente**: prezzo d'ingresso. **Paper o live**: uguale.

### 36. Capitale investito (base del cash out)
- **Cosa fa**: somma gli importi abbinati di tutte le PUNTE di apertura non archiviate (Under, seconda puntata, copertura Over, re-ingresso).
- **Esempio**: Under 10 + copertura 2,26 = 12,26.
- **Dove**: `engine.py:700-704`; usata anche dal servizio. **Utente**: base della percentuale del cash out. **Paper o live**: uguale.

### 37. P&L lordo di un mercato con T gol, e la commissione sul netto positivo
- **Cosa fa**: `_market_pnl_by_total` somma il risultato di tutte le gambe abbinate di UN mercato se finisce con T gol (qui NON salta le archiviate). `_net` toglie la commissione solo se il risultato e' positivo.
- **Esempio**: +5,00 con commissione 5% -> +4,75; -2,26 resta -2,26.
- **Dove**: `engine.py:707-719`, `722-723`. **Paper o live**: uguale.

### 38. P&L netto della partita per ogni numero di gol (0..8)
- **Cosa fa**: per ogni totale gol da 0 a 8 somma i due mercati, ciascuno netto della propria commissione. E' la tabella "come finisce se...".
- **Numeri**: `max_total` 8; commissione `commission_pct`.
- **Esempio**: Under 10 a 1,50 + Over 2,26 a 6,6: 0-3 gol +2,49; 4 gol -12,26; 5+ gol +2,02.
- **Dove**: `engine.py:726-734`. **Utente**: P&L per gol nella card (dal servizio). **Paper o live**: uguale.

### 39. Quanto incasso se chiudo TUTTO adesso (valore di cash out)
- **Cosa fa**: per ogni selezione aperta: se l'esito e' gia' deciso vale "se vince" o "se perde" senza prezzo; altrimenti calcola l'unico ordine di chiusura totale (green-up) e prende il peggiore dei due risultati dopo la chiusura. Somma per mercato, toglie la commissione per MERCATO sul netto positivo e la ripartisce in proporzione sulle selezioni in utile; l'eventuale centesimo di scarto va sulla selezione di peso maggiore. Se una selezione viva non ha prezzo il calcolo e' "incompleto".
- **Come si chiude (da `compute_greenup`, fuori area)**: se W > L si BANCA al miglior lay; se L > W si PUNTA al miglior back; importo = |W - L| / quota, al centesimo. Con `place_at_ticks` > 0 la quota si sposta di N tick "contro di noi" (bancata piu' alta, punta piu' bassa) per abbinare piu' facilmente. Differenza < 0,01 -> nessun ordine.
- **Numeri**: `cashout_place_at_ticks` (0); `commission_pct` (5).
- **Esempio**: punta Under 10 a 1,50, lay a 1,30: bancata 15/1,30 = 11,54; risultato +1,54 su ogni esito; netto 1,46.
- **Cosa vede l'utente**: "se chiudo ora" nella card (`live.cashout`).
- **Dove**: `engine.py:737-805`; `greenup.py:118-249`.
- **Paper o live**: uguale.

### 40. P&L della partita quando non dipende da come finisce
- **Cosa fa**: se non c'e' nessun abbinamento -> 0,00; se il P&L e' lo stesso su 0..8 gol (entro 0,005) -> quel numero; altrimenti "non si sa" (serve il punteggio). Con un ordine a esito ignoto -> "non si sa".
- **Quando scatta**: dal servizio per chiudere partite il cui punteggio finale non e' recuperabile (fuori area).
- **Esempio**: partita senza ingressi -> 0,00 invece di "DA SISTEMARE".
- **Dove**: `engine.py:813-845`. **Paper o live**: uguale.

### 41. Pulizia delle gambe ritirate e mai abbinate
- **Cosa fa**: delle gambe "ritirate senza abbinato" tiene solo le ultime 5 per ruolo; tutte le altre gambe restano sempre. Serve a non far crescere la scheda della partita (caso reale: 60 KB).
- **Numeri**: `MAX_CANCELLED_PER_ROLE = 5` (costante nel codice). Valore negativo = non toglie niente.
- **Esempio**: 180 coperture rifiutate -> ne restano 5.
- **Dove**: `engine.py:810`, `848-885`; chiamata dal servizio. **Paper o live**: uguale.

### 42. Di quanti tick si e' mosso l'Under fra il nostro ingresso e il fischio
- **Cosa fa**: negativo = la quota e' scesa (a nostro favore); positivo = salita.
- **Esempio**: ingresso 1,50, fischio 1,46 -> -4.
- **Dove**: `engine.py:888-910`; usata dal servizio e da `Betfair/tools/scostamento_fischio_2026_09_13.py`. **Paper o live**: uguale.

### 43. Gambe che portano ancora rischio
- **Cosa fa**: tutte tranne le archiviate. **Dove**: `engine.py:913-915`. **Paper o live**: uguale.

### 44. Ordini a esito ignoto contati come abbinati per intero
- **Cosa fa**: copia le gambe e, per quelle a esito ignoto, mette abbinato = importo pieno (peggior caso), anche se qualcosa risulta gia' abbinato.
- **Esempio**: ordine da 100 con 1 centesimo noto -> conta 100.
- **Dove**: `engine.py:918-935`. **Paper o live**: uguale.

### 45. Rischio vero della partita
- **Cosa fa**: la perdita peggiore possibile, su 0..8 gol, delle gambe non archiviate con gli ignoti al peggior caso. Nessun abbinamento -> 0.
- **Esempio**: Under 10 + Over 2,26 (scheda 38) -> 12,26.
- **Dove**: `engine.py:938-947`; usata da `db.py` e `service.py`. **Utente**: liability della partita. **Paper o live**: uguale.

### 46. P&L gia' BLOCCATO
- **Cosa fa**: se nessuna selezione e' aperta e nessun ordine e' ignoto, il P&L minimo su 0..8 gol (che e' lo stesso ovunque). Se non si e' MAI puntato -> "niente" (non 0,00).
- **Esempio**: green 10 a 1,50 / 10,14 a 1,48 -> +0,13.
- **Dove**: `engine.py:950-968`. **Utente**: "gia' bloccato"; entra nello stop giornaliero (fuori area). **Paper o live**: uguale.

### 47. Tipo di uscita di una riga di chiusura
- **Cosa fa**: `manual_close` o motivo "manual" -> manual; green (under_green, ko_green, reentry_green) -> greenup (o time se motivo "reentry_time"); motivo "profit" -> profit; motivo che inizia con "loss_" -> loss (ma "loss_cap" -> forced); "reentry_time" -> time; altro -> other.
- **Dove**: `engine.py:971-990`; usata dal servizio. **Utente**: colonna tipo uscita in Trade. **Paper o live**: uguale.

### 48. Quale apertura sta chiudendo questa chiusura
- **Cosa fa**: fra le punte di apertura della selezione prende l'ultima abbinata non archiviata; se non ce n'e', l'ultima in assoluto.
- **Dove**: `engine.py:993-1001`; usata in 3864. **Paper o live**: uguale.

---

## PARTE 5 - LE REGOLE DI USCITA (calcoli)

### 49. Cash out pieno: soglia raggiunta?
- **Cosa fa**: vero se il valore netto di chiusura >= base x percentuale. Base <= 0 -> falso.
- **Numeri**: percentuale `cashout_profit_pct` 5%; base da scheda 79.
- **Esempio**: base 12,26 -> soglia 0,613: 0,75 chiude, 0,44 no.
- **Dove**: `engine.py:1004-1007`; chiamata in `_decide_covered` 3527. **Utente**: motivo "profit: ...". **Paper o live**: uguale.

### 50. Uscita in perdita "a regola fissa"
- **Cosa fa**: vero se i gol sono fra min e max e la perdita bloccabile e' entro la percentuale della base (o si e' in utile).
- **Numeri**: pct = `ht_loss_pct` 25 o `h2_loss_pct` 25; gol min/max = `ht_loss_goals_min` 3 / `ht_loss_goals_max` 4 (usati anche nel 2T, vedi 3543).
- **Esempio**: base 24: -5,51 con 3 gol -> chiude (entro -6,00); con 2 gol -> no.
- **Dove**: `engine.py:1010-1015`; chiamata 3570 (solo se il modello non ha dati). **Paper o live**: uguale.

### 51. Probabilita' usabile e quota "morta"
- **Cosa fa**: una probabilita' vale solo se finita e fra 0 (escluso) e 1. `_PROB_KEY` collega Under 3.5 -> "u35", Over 4.5 -> "o45", Under 4.5 -> "u45". `_DEAD_PRICE` = 1000 (quota di una selezione praticamente morta).
- **Dove**: `engine.py:1018-1034`. **Paper o live**: uguale.

### 52. Book "proiettati" in uno scenario (dopo un gol / fra qualche minuto)
- **Cosa fa**: scala le quote di mercato per P_adesso / P_scenario: il margine del book resta. Scenario con P quasi zero (<= 0,000001) -> quota 1000. Quote tenute fra 1,01 e 1000. Qualunque dato mancante o rotto -> nessuna proiezione.
- **Esempio**: Under 3.5 lay 1,30 con P adesso 0,77 e P dopo gol 0,55 -> 1,30 x 1,4 = 1,82.
- **Dove**: `engine.py:1037-1072`. **Paper o live**: uguale.

### 53. Cash out INTELLIGENTE (chiude prima della soglia)
- **Cosa fa**: chiude prima del 5% quando tenere non vale il rischio, ma mai sotto il profitto minimo. In ordine:
  1. valore < minimo -> non chiude;
  2. gol >= "punteggio caldo" -> chiude;
  3. "a un passo" dalla soglia E fase calda (hazard >= soglia O pressione >= soglia) -> chiude;
  4. con probabilita' di modello e hazard: probabilita' di gol nei prossimi N minuti h = 1 - (1 - hazard3')^(N/3); valore atteso dell'attesa = h x valore-dopo-gol + (1 - h) x valore-fra-N-minuti; vicino alla soglia chiude se atteso < valore adesso; lontano chiude se atteso < valore adesso - margine.
- **Quando scatta**: in `LIVE_COVERED`, dopo che la soglia piena non e' stata raggiunta (3531).
- **Numeri**: `cashout_smart_enabled` True; `cashout_profit_pct` 5; `cashout_smart_min_pct` 2; `cashout_smart_tolerance_pct` 2; `cashout_smart_goals_hot` 3; `cashout_smart_hazard_hot` 0,10; `cashout_smart_pressure_hot` 1,15; `cashout_smart_ev_margin_pct` 1; N = `cover_wait_step_min` 5 (minimo 1).
- **Esempio**: base 12,26: minimo 0,245, soglia 0,613, "a un passo" da 0,368. Valore 0,44 con hazard 0,11 -> chiude ("fase calda"). Hazard 0,06 -> h = 1 - 0,94^(5/3) = 0,098.
- **Cosa vede l'utente**: motivo "profit smart: ... (punteggio caldo / fase calda / aspettare vale...)".
- **Dove**: `engine.py:1075-1132`. **Paper o live**: uguale.

### 54. Media delle distribuzioni dei gol
- **Cosa fa**: media delle distribuzioni disponibili (modello, empirica), rinormalizzata a 1. Nessuna -> niente.
- **Dove**: `engine.py:1135-1143`. **Esempio**: P(4) 0,20 e 0,30 -> 0,25. **Paper o live**: uguale.

### 55. Valore atteso di tenere fino alla fine
- **Cosa fa**: somma P(gol = t) x P&L(t). Se c'e' un "pavimento" per P(4) piu' alto, P(4) si alza a quello e il resto si riscala (scelta prudente). P(4) sporca viene tenuta fra 0 e 1.
- **Esempio**: P&L +2 su 0-3 e 5+, -12 su 4; P(4)=0,20 alzata a 0,30 -> 0,7 x 2 + 0,3 x (-12) = -2,20.
- **Dove**: `engine.py:1146-1168`. **Paper o live**: uguale.

### 56. Uscita in perdita "a modello"
- **Cosa fa**: confronta il valore certo di chiudere ora con il valore atteso di tenere meno un premio al rischio = premio% x P(4) x base. Chiude se chiudere >= atteso - premio. Distribuzione: media modello+empirica; se mancano entrambe usa quella del mercato; se manca tutto -> "non so" (il chiamante usa la regola fissa, scheda 50). P(4) prudente: se acceso, P(4) non puo' essere sotto quella del mercato. Tetto: se attivo e la perdita supera tetto% della base -> "si tiene".
- **Numeri**: `loss_exit_risk_premium_pct` 10; `loss_exit_p4_prudent` True; `loss_exit_max_pct` 0 (spento).
- **Esempio**: base 24, chiudo -5,51, tengo -0,79, P(4) 0,22 -> premio 0,53, soglia -1,32 -> TIENE.
- **Cosa vede l'utente**: motivo "uscita a modello (ht|2t): chiudere (...) vale piu' di tenere ..." oppure "tenere vale ...".
- **Dove**: `engine.py:1171-1209`; chiamata 3551. **Paper o live**: uguale.

### 57. Quando comprare la copertura (subito / aspetta / salta)
- **Cosa fa**:
  - gol > massimo -> SALTA;
  - politica "immediate" -> COPRE;
  - almeno 1 gol: se l'ultimo gol e' di meno di X secondi fa -> ASPETTA (riprezzo), altrimenti COPRE;
  - minuto mancante -> COPRE; minuto >= attesa massima -> COPRE;
  - politica "wait" -> ASPETTA;
  - hazard o P(4) mancanti -> COPRE; hazard > soglia -> COPRE; P(4) > soglia -> COPRE; quota Over >= quota buona -> COPRE; risparmio atteso < minimo -> COPRE;
  - altrimenti ASPETTA.
- **Numeri**: `cover_max_goals` 2; `cover_policy` "auto"; `cover_postgoal_delay_s` 45; `cover_wait_max_min` 10; `cover_wait_hazard_max` 0,06; `cover_wait_p4_max` 0,16; `cover_good_price` 7,0; `cover_wait_min_gain_pct` 8.
- **Esempio**: 7', 0-0, hazard 0,04, P(4) 0,12, Over 6,6, risparmio 10% -> ASPETTA; stessa situazione con Over 7,2 -> COPRE.
- **Cosa vede l'utente**: "attendo per coprire" / "copertura saltata: troppi gol".
- **Dove**: `engine.py:1212-1251`; chiamata 3316. **Paper o live**: uguale.

---

## PARTE 6 - IL REGOLAMENTO E CIO' CHE LA SCHEDA MOSTRA

### 58. Chi ha vinto in ogni mercato dato il totale gol
- **Dove**: `engine.py:1254-1257`. **Esempio**: 4 gol -> OU35 Over, OU45 Under. **Paper o live**: uguale.

### 59. Regolamento con il totale gol
- **Cosa fa**: chiama la scheda 60 con i vincitori della scheda 58.
- **Dove**: `engine.py:1260-1262`; chiamata dal regolamento 2455. **Paper o live**: uguale.

### 60. Regolamento per mercato (con mercato annullato)
- **Cosa fa**: per ogni gamba: mai abbinata o mercato annullato -> nulla (0). Altrimenti vinta/persa e P&L. Commissione per mercato = 5% del netto positivo, arrotondata al centesimo, ripartita sulle gambe in utile. Il netto di mercato e' il lordo meno commissione. Lo scarto di arrotondamento va sulla riga piu' pesante (preferendo una in utile) cosi' la somma delle righe = P&L della partita. Mercato non dichiarato -> errore (eccezione).
- **Numeri**: `commission_pct` 5.
- **Esempio**: Under 10 a 1,50 + Over 2,26 a 6,6, finale 2 gol: Under +5,00 (commissione 0,25 -> +4,75), Over -2,26; totale +2,49.
- **Cosa vede l'utente**: righe regolate in Trade/Regolate.
- **Dove**: `engine.py:1265-1336`. **Paper o live**: uguale.

### 61. Contributo dei cicli gia' chiusi
- **Cosa fa**: P&L di tutte le gambe meno P&L delle sole non archiviate; se non e' uguale su ogni totale (tolleranza 0,015) -> "non si sa".
- **Dove**: `engine.py:1351-1367`; usata dal servizio. **Paper o live**: uguale.

### 62. Riepilogo per ciclo
- **Cosa fa**: per ogni ciclo con abbinamenti: importo delle punte d'apertura, quota media di ingresso, quota media di uscita, se e' chiuso (P&L uguale su ogni totale entro 0,015), P&L (solo se chiuso), numero gambe e ruoli.
- **Esempio**: ciclo 1: 10 euro a 1,50, uscita 1,48, chiuso, +0,13.
- **Dove**: `engine.py:1370-1410`; usata dal servizio. **Utente**: elenco cicli. **Paper o live**: uguale.

### 63. Una riga per selezione aperta (posizione + chiusura eseguibile?)
- **Cosa fa**: lato netto, importo netto, abbinato, quota media delle punte, se vince / se perde, se e' gia' decisa, l'ordine di chiusura che farebbe il bot (lato, quota, importo), "se chiudo ora" netto, liquidita' al prezzo di chiusura e "eseguibile" (la liquidita' copre tutto l'importo).
- **Dove**: `engine.py:1413-1461`; usata dal servizio. **Utente**: tabella posizioni. **Paper o live**: uguale.

---

## PARTE 7 - AIUTI INTERNI E RIFIUTI

### 64. Cercare le gambe di un ruolo / l'ultima di un ruolo
- **Dove**: `engine.py:1464-1479`. Filtro per ruolo e per vivo/non vivo; `_last` = ultima della lista. **Paper o live**: uguale.

### 65. Ritirare tutti gli ordini vivi (eventualmente solo certi ruoli)
- **Cosa fa**: un "ritira" per ogni gamba con stato `pending`. Gli ordini a esito ignoto NON sono inclusi.
- **Dove**: `engine.py:1482-1484`. **Paper o live**: uguale.

### 66. Preparare un ordine da piazzare
- **Cosa fa**: arrotonda la quota al tick valido piu' vicino e l'importo al centesimo; persistenza default LAPSE.
- **Esempio**: quota 1,483 -> 1,48; importo 10,137 -> 10,14.
- **Dove**: `engine.py:1487-1491`. **Paper o live**: uguale.

### 67. Chiave di una gamba della strategia
- **Cosa fa**: "ruolo|ciclo|mercato|selezione|lato|finale" (senza prezzo).
- **Dove**: `engine.py:1494-1498`. **Esempio**: `reentry_green|0|OU45|UNDER|lay|0`.

### 68. Ricordare un rifiuto del mercato
- **Cosa fa**: scrive in memoria quota, importo, motivo (max 120 caratteri) e identificativo dell'ULTIMA richiesta rifiutata per quella gamba. La chiama il servizio solo quando l'ordine non e' nato e la risposta e' definitiva (mai su esito ignoto).
- **Dove**: `engine.py:1501-1519`; chiamata da `service.py`. **Paper o live**: uguale.

### 69. La stessa identica richiesta e' gia' stata rifiutata?
- **Cosa fa**: per un "piazza": se esiste un rifiuto per la stessa gamba (ciclo attuale) con la stessa quota (tolleranza 1e-9) e lo stesso importo (tolleranza 0,005) -> si'. Cambia quota o importo -> e' una domanda nuova.
- **Quando scatta**: rami green pre-match, uscita al fischio, re-ingresso (fuori area 2756, 2773, 3146, 3783).
- **Esempio**: bancata 10,11 a 1,75 rifiutata -> al giro dopo, identica, non si rifa'.
- **Dove**: `engine.py:1522-1555`. **Paper o live**: uguale.

### 70. Motivo scritto del "non si ripropone"
- **Cosa vede l'utente**: "gia' rifiutata a mercato (<motivo>): lay 10.11 @ 1.75 non si ripropone identica".
- **Dove**: `engine.py:1558-1563`.

---

## PARTE 8 - IL FRENO DELLA COPERTURA (rifiuti ripetuti e ritmo)

### 71. Nome del blocco e lettura della memoria
- **Cosa fa**: `COVER_BLOCCATA = "LIVE_COVER_BLOCKED"` e' l'etichetta della copertura fermata; `_cover_rifiuti` legge (copia) il conteggio salvato.
- **Dove**: `engine.py:1587-1592`.

### 72. Contare un rifiuto della copertura per codice d'errore
- **Cosa fa**: stesso codice d'errore del precedente -> conteggio +1; codice diverso -> conteggio riparte da 1. Arrivato al massimo -> copertura BLOCCATA. Salva anche ora, identificativo, motivo, massimo.
- **Numeri**: `cover_rifiuti_max` 3 (minimo effettivo 1). Codice lungo al massimo 60 caratteri; senza codice -> "senza_codice".
- **Esempio**: 3 rifiuti "CANCELLED_NOT_PLACED" di fila -> bloccata; un quarto con codice diverso -> conteggio 1, sbloccata.
- **Dove**: `engine.py:1595-1615`; chiamata da `service.py`. **Paper o live**: uguale.

### 73. La copertura e' bloccata?
- **Dove**: `engine.py:1618-1621`. Restituisce il verbale se "bloccata" e' vero.

### 74. Segnare che si e' appena tentata la copertura
- **Cosa fa**: aggiorna l'ora dell'ultimo tentativo PRIMA di sapere l'esito.
- **Dove**: `engine.py:1624-1635`; chiamata da `service.py`.

### 75. Quanto manca al prossimo tentativo di copertura
- **Cosa fa**: ultimo tentativo + ritmo minimo - adesso; se > 0 restituisce i secondi (1 decimale), altrimenti "si puo'".
- **Numeri**: `cover_retry_min_s` 15 s. Parametro 0 -> nessun freno.
- **Esempio**: tentativo alle 18:00:00, adesso 18:00:05 -> mancano 10 s.
- **Dove**: `engine.py:1638-1650`.

### 76. Sblocco a mano ("Riprendi")
- **Cosa fa**: azzera il freno e restituisce il verbale precedente.
- **Dove**: `engine.py:1653-1658`; chiamata dal servizio (e dal commento di `_freno_copertura`).
- **Cosa vede l'utente**: il bottone "Riprendi".

### 77. C'e' una copertura in corso?
- **Cosa fa**: vero se una copertura e' viva o a esito ignoto, oppure la fase e' LIVE_UNCOVERED / LIVE_COVER_PENDING.
- **Dove**: `engine.py:1661-1669`; usata dal servizio (sorveglianza dello stato del mercato 4.5).

---

## PARTE 9 - BASE, PREZZI, TETTI E CHIUSURA FORZATA

### 78. Posizione Under 3.5 (importo e quota media)
- **Dove**: `engine.py:1672-1673` (scheda 35 con i ruoli `UNDER_ROLES`).

### 79. Base percentuale del cash out
- **Cosa fa**: `cashout_base` = "under" -> solo l'importo Under abbinato; altrimenti ("total") il capitale investito (scheda 36).
- **Numeri**: `cashout_base` "total".
- **Esempio**: Under 10 + Over 2,26: total 12,26; under 10,00.
- **Dove**: `engine.py:1676-1684` (`_cashout_base` e' lo stesso, nome vecchio).

### 80. Quota a cui piazzare la copertura (cuscinetto)
- **Cosa fa**: N tick SOTTO il miglior back dell'Over (quota peggiore ma ordine che entra durante il ritardo). N <= 0 -> il best. Quota fuori scala -> il best.
- **Numeri**: `cover_place_at_ticks` 2.
- **Esempio**: best 4,60 -> 4,40.
- **Dove**: `engine.py:1687-1704`; chiamata 3314, 3479 (l'IMPORTO si calcola sul best, vedi Cose strane).

### 81. Spazio di capitale rimasto sulla partita
- **Cosa fa**: tetto - capitale investito (mai negativo). Tetto 0 -> infinito.
- **Numeri**: `max_liability_per_match` 0 (spento).
- **Esempio**: tetto 30, investito 12,26 -> 17,74.
- **Dove**: `engine.py:1707-1714`; usata in 2536, 3212, 3383, 3704.

### 82. Importo di chiusura accettabile?
- **Cosa fa**: vero se piazzabile (>= 0,01) e >= 0,0095.
- **Dove**: `engine.py:1717-1734`.

### 83. Ordini vivi su una selezione (escludendo certi ruoli)
- **Dove**: `engine.py:1737-1751`. Solo stato `pending`.

### 84. Ordini di chiusura del cash out
- **Cosa fa**: per ogni selezione con ordine di chiusura calcolato: salta se l'importo non e' chiudibile; ritira ogni altro ordine vivo sulla stessa selezione (di ruolo diverso da quello di chiusura); piazza la chiusura (Under 3.5 -> `under_close`, Over 4.5 -> `over_close`, Under 4.5 -> `reentry_green`, oppure la mappa passata).
- **Esempio**: bancata Under 11,54 a 1,30 + ritiro della vecchia green appoggiata.
- **Dove**: `engine.py:1754-1783`; usata da cash out, uscite in perdita, cap, chiusure (3528-3621).

### 85. Piano di chiusura forzata (cash out / flatten dalla UI)
- **Cosa fa**: calcola il cash out e restituisce DUE gruppi separati: prima i ritiri di tutti gli ordini vivi, poi le chiusure. `MANUAL_ROLE_MAP`: tutte le chiusure col ruolo `manual_close`.
- **Numeri**: `commission_pct`, `cashout_place_at_ticks`.
- **Dove**: `engine.py:1786-1805`.

### 86. Chiusura forzata in un colpo solo
- **Cosa fa**: ritiri + chiusure in un'unica lista (ruoli di chiusura normali).
- **Dove**: `engine.py:1808-1812`. Nessun chiamante in produzione (solo test).

### 87. Chiusure ancora sul book
- **Cosa fa**: gambe vive con ruolo `under_close`, `over_close` o `manual_close`.
- **Dove**: `engine.py:1815-1816`; usata in 3607.

---

## PARTE 10 - LE GUARDIE

### 88. C'e' un ordine a esito ignoto?
- **Dove**: `engine.py:1822-1824`. Se si', nessuna nuova apertura (scheda 97) e regolamento sospeso (scheda 108).

### 89. La partita ha davvero soldi sopra? (per il tetto partite)
- **Cosa fa**: fasi finali -> no. Fasi diverse da WATCH e IDLE_LIVE -> si'. In WATCH/IDLE_LIVE: si' solo se c'e' una gamba non archiviata abbinata o viva.
- **Numeri**: governa chi consuma un posto di `max_open_matches` (10) nel servizio.
- **Dove**: `engine.py:1827-1851`.

### 90. Togliere le aperture da una decisione
- **Cosa fa**: toglie i "piazza" dei ruoli di apertura; lascia ritiri e chiusure. Se dopo non resta nessun "piazza", la fase resta quella di adesso e gli aggiornamenti si scartano (si riprova al giro dopo).
- **Esempio**: seconda tranche di copertura tolta -> la fase NON passa a "attesa fill copertura".
- **Cosa vede l'utente**: motivo con "(ordine a esito ignoto: nessuna apertura)" o "(aperture ferme (...))".
- **Dove**: `engine.py:1854-1879`.

### 91. C'e' una bancata "in volo" su questa selezione?
- **Cosa fa**: prima bancata viva o a esito ignoto su quel mercato/selezione.
- **Dove**: `engine.py:1882-1898`.

### 92. Mai due bancate a mercato
- **Cosa fa**: ogni nuova bancata su una selezione dove c'e' gia' una bancata viva o in volo viene tolta dalla decisione (il ritiro della vecchia resta). La nuova arriva al giro dopo, a ritiro confermato, dimensionata sulla posizione reale. Se non resta nessun "piazza", fase e aggiornamenti non avanzano.
- **Cosa vede l'utente**: "(lay '<ruolo>' rimandata: '<gamba>' e' ancora viva / a esito ignoto sulla stessa selezione (mai due lay a mercato))".
- **Dove**: `engine.py:1901-1951`.

### 93. C'e' una copertura "in volo"?
- **Dove**: `engine.py:1954-1969` (ruolo `over_cover`, viva o esito ignoto).

### 94. Mai sovracopertura
- **Cosa fa**: stessa regola della 92 per le coperture Over 4.5.
- **Cosa vede l'utente**: "(copertura rimandata: '<gamba>' e' ancora viva ... (mai sovracopertura))".
- **Dove**: `engine.py:1972-2020`.

### 95. Il freno della copertura
- **Cosa fa**: se la decisione vuole piazzare una copertura e (a) la copertura e' bloccata dai rifiuti, oppure (b) non e' passato il ritmo minimo: toglie TUTTE le azioni della copertura (anche il ritiro), scarta tutti gli aggiornamenti; se la fase voluta era LIVE_COVER_PENDING e non c'e' una copertura viva -> LIVE_UNCOVERED.
- **Numeri**: `cover_rifiuti_max` 3; `cover_retry_min_s` 15.
- **Cosa vede l'utente**: "copertura FERMATA dal freno: 3 rifiuti con lo stesso codice (...) - serve l'utente" oppure "copertura: ritento fra 10 s (ritmo minimo fra due tentativi)".
- **Dove**: `engine.py:2023-2074`.

### 96. Chiusura MANUALE in corso (cash out / flatten dalla UI)
- **Cosa fa**, in quest'ordine:
  1. se ci sono ordini vivi (esclusa la chiusura manuale) -> li ritira (fase invariata, motivo "manual");
  2. se c'e' una chiusura manuale sul book: se nessuna e' "vecchia" (>= X s) o i tentativi sono finiti -> aspetta; altrimenti ritira le vecchie e ripiazza il residuo (tentativi +1);
  3. se ci sono chiusure da fare -> le piazza (tentativi 0);
  4. se una selezione viva non ha prezzo -> aspetta;
  5. se resta solo una selezione gia' decisa dai gol -> FLAT (in gioco) o WATCH (pre-match) SENZA archiviare, niente piu' rientri;
  6. altrimenti completa: in gioco -> FLAT, gambe archiviate, niente piu' rientri; pre-match -> WATCH, ciclo +1, gambe archiviate, niente piu' rientri finche' "Riprendi".
- **Numeri**: `close_retry_s` 10; `close_max_attempts` 20; fase di chiusura LIVE_CLOSING (in gioco) o PRE_GREEN_PENDING (pre-match).
- **Cosa vede l'utente**: "chiusura manuale: annullo gli ordini vivi / attendo il fill / riprezzo / chiudo la posizione / completata"; attivita' `chiuso_dall_utente`.
- **Dove**: `engine.py:2077-2161`.
- **Paper o live**: uguale.

### 97. La decisione di ogni giro (`decide`) e l'ordine delle guardie
- **Cosa fa**:
  1. fase finale -> niente;
  2. se il mercato NON e' chiuso e non si sta regolando: chiuso dall'utente fuori app -> niente (fase invariata); chiusura manuale in corso -> scheda 96; `no_reentry` -> spegne ingressi pre-match, re-ingresso e ultimo ingresso PERSIST;
  3. chiede la decisione alla fase (scheda 108);
  4. ordine a esito ignoto -> via le aperture; altrimenti "aperture ferme" -> via le aperture;
  5. freno copertura (95) -> mai due bancate (92) -> mai sovracopertura (94) -> cancello delle uscite (107).
- **Dove**: `engine.py:2164-2216`.
- **Paper o live**: uguale; `aperture_ferme` la scrive il servizio (anche per "runner giu' in paper").

---

## PARTE 11 - IL CANCELLO DELLE USCITE MANUALI / AUTOMATICHE

### 98. Le costanti del cancello
- `USCITE_DISCREZIONALI` = under_green, ko_green, under_close, over_close, reentry_green.
- `MOTIVI_PROTEZIONE` = loss_cap (cap perdita partita: sempre automatico).
- `STATI_USCITA_IN_CORSO` = LIVE_CLOSING, REENTRY_GREEN_PENDING, PRE_GREEN_PENDING.
- `_CANCEL_SEMPRE` = under_entry, under_last, under_second, reentry (ritiri di ingressi che passano sempre).
- `APPROVAZIONE_TTL_S = 120.0` s (validita' di una firma; costante non modificabile dalla UI; copiata in `Betfair/stream/uscite_proposte.py`).
- **Dove**: `engine.py:2225-2240`.

### 99. L'interruttore "uscite automatiche"
- **Cosa fa**: legge `uscite_automatiche` dai parametri del giro; mancante o non vero/falso -> SPENTO (manuali).
- **Numeri**: `uscite_automatiche` False.
- **Dove**: `engine.py:2243-2248`.

### 100. Che tipo di uscita contiene la decisione
- **Cosa fa**: under_close o over_close -> "chiusura"; ko_green -> "ko_green"; under_green -> "green_pre"; reentry_green -> "reentry_green"; nessuna -> niente.
- **Dove**: `engine.py:2251-2262`.

### 101. Chiave della proposta
- **Cosa fa**: "<categoria>|c<ciclo>". **Esempio**: `ko_green|c0`. **Dove**: `engine.py:2265-2266`.

### 102. L'uscita e' il seguito di una gia' partita?
- **Cosa fa**: vero se la fase e' gia' di chiusura in corso, o se nel ciclo esiste gia' una gamba (anche ritirata) dello stesso ruolo di uscita, non archiviata.
- **Dove**: `engine.py:2269-2285`.

### 103. Firma valida?
- **Cosa fa**: stessa chiave e firmata da non piu' di 120 s.
- **Dove**: `engine.py:2288-2295`.

### 104. La firma e' per QUESTA uscita (stesso motivo)?
- **Cosa fa**: confronta il motivo di chiusura della proposta firmata con quello di adesso; senza proposta -> no.
- **Dove**: `engine.py:2298-2310`.

### 105. Copia di una decisione con aggiornamenti nuovi
- **Dove**: `engine.py:2313-2314`.

### 106. La proposta decade
- **Cosa fa**: se c'e' una proposta viva la toglie (e toglie la firma), scrivendo una volta il motivo; se c'e' solo una firma senza proposta, toglie la firma.
- **Cosa vede l'utente**: telemetria `uscita_proposta_decaduta`.
- **Dove**: `engine.py:2317-2334`.

### 107. Il cancello (`gate_uscite`)
- **Cosa fa**:
  - interruttore ACCESO -> la decisione passa intatta, un'eventuale proposta decade;
  - nessuna uscita discrezionale -> passa, proposta decade;
  - motivo "loss_cap" -> passa (protezione);
  - uscita gia' in corso -> passa;
  - firma valida per la stessa uscita -> passa ESATTAMENTE la decisione attuale (prezzi e importi di adesso), firma e proposta si consumano;
  - altrimenti si PROPONE: nessun ordine parte tranne i ritiri di ingressi (`_CANCEL_SEMPRE`); la proposta contiene chiave, categoria, ciclo, fase, fase voluta, motivo, motivo di chiusura, ordini, P&L bloccabile, urgente (motivo che inizia con "loss"), minuto, gol, momento della decisione (fermo finche' la chiave non cambia), momento della proposta. Se la decisione porterebbe a una fase di chiusura o a FLAT, si resta nella fase attuale e si tolgono motivo di chiusura e tentativi. Una firma per un'altra chiave, o per un altro motivo, cade.
- **Cosa vede l'utente**: "uscita proposta all'utente (uscite manuali): <motivo>"; la proposta nella scheda uscite.
- **Dove**: `engine.py:2337-2431`.
- **Paper o live**: uguale.

### 108. Chi decide in ogni fase (`_dispatch`)
- **Cosa fa**: mercato chiuso o fase SETTLING: prima volta -> SETTLING e ritiro di tutti gli ordini vivi; con ordine a esito ignoto -> regolamento sospeso (critico); senza punteggio finale -> attesa; altrimenti regola e va a SETTLED. Le fasi pre-match (WATCH, PRE_ENTRY_PENDING, PRE_OPEN, PRE_GREEN_PENDING, HOLD, PRE_LAST_ENTRY_PENDING) -> `_decide_prematch`. IDLE_LIVE senza gambe -> SETTLED "nessuna operazione" con 0,00; con gambe -> resta. Poi una funzione per ogni fase live (fuori area). Fase sconosciuta -> ERROR e ritiro di tutto.
- **Numeri**: commissione = `commission_pct` / 100.
- **Cosa vede l'utente**: "mercato chiuso", "regolamento sospeso: un ordine ha esito ignoto", "attesa punteggio finale", "regolato T=3", "nessuna operazione".
- **Dove**: `engine.py:2435-2491`.
- **Paper o live**: uguale.

---

## PARTE 12 - config.py

### 109. Costanti fisse di config
- `OU35 = "OVER_UNDER_35"`, `OU45 = "OVER_UNDER_45"`: codici Betfair (usati in `service.py:568`, `4781`).
- `FOOTBALL_EVENT_TYPE_ID = "1"`: nessun uso a runtime trovato in `Betfair/mike`.
- `EXPECTED_SEL`: Under 3.5 1222344, Over 3.5 1222345, Over 4.5 1222346, Under 4.5 1222347 (solo documentale/test).
- `CUSTOMER_STRATEGY_REF = "mike"`: marchio degli ordini su Betfair (`service.py:63`, `131-132`).
- `LOCK_PORT_DEFAULT = 47319`: porta del lucchetto "una sola istanza" (`service.py:47`).
- **Dove**: `config.py:17-32`.

### 110. Lettura delle variabili d'ambiente
- `env_str`, `env_int`, `env_float`, `env_bool`: stringa vuota = assente -> default; valore non leggibile -> default; vero = "1", "true", "yes", "on".
- **Dove**: `config.py:38-66`.

### 111. La lista dei parametri ammessi
- `Spec` = (default, tipo, minimo, massimo, scelte). `PARAM_SPEC` = 106 chiavi (schede 116-127). `DEFAULTS` = i default.
- **Dove**: `config.py:73-379`, `426`.

### 112. Pulizia di un valore
- **Cosa fa**: si/no da testo ("1", "true", "yes", "on"); testo ripulito dagli spazi; numero convertito; valore illeggibile -> default; scelte -> fuori elenco -> default; numeri riportati dentro [min, max].
- **Dove**: `config.py:429-450`.

### 113. Fusione dei parametri dalla UI
- **Cosa fa**: parte dai default, applica SOLO le chiavi note e non vuote. Coppie min/max invertite -> tornano entrambe ai default. Coppie: prezzo d'ingresso min/max; gol min/max dell'uscita in perdita; minuti del 2T.
- **Dove**: `config.py:455-476`; usata in `service.py:3446`, `6050`.

### 114. Tasso di commissione
- **Cosa fa**: `commission_pct` / 100.
- **Dove**: `config.py:479-480`; usata in `service.py`.

### 115. Parametri tolti e parametri solo backend
- `REMOVED_PARAMS` = max_matches, catalogue_refresh_s, stream_extra_lines, min_total_matched (inerti, scartati).
- `BACKEND_ONLY_PARAMS` = vuota.
- **Dove**: `config.py:398`, `424`.

### 116. Parametri - Generale
| chiave | default | range / scelte | cosa governa | dove e' usato |
|---|---|---|---|---|
| `stake` | 10,0 | 0,50-500 | importo per gamba | `engine.py:2526, 2536, 2630, 2844, 3209, 3701` |
| `commission_pct` | 5,0 | 0-20 | commissione | `engine.py:1803, 2437`; `service.py:5253` |
| `entry_hours_before_ko` | 1,0 | 0,25-12 | ore prima del KO in cui si entra | `engine.py:2512`; `feed.py:460`; `service.py:3954, 3973` |
| `competition_filter` | "" | testo | competizioni ammesse (vuoto = tutte) | `feed.py:455` |
| `decide_min_interval_ms` | 500 | 100-5000 | intervallo minimo fra due decisioni | `service.py:3893, 5629, 5631, 6051` |

### 117. Parametri - Freschezza del feed
| chiave | default | range | cosa governa | dove |
|---|---|---|---|---|
| `feed_max_age_s` | 45,0 | 3-180 | eta' massima della riga per guardare | `feed.py:429` |
| `scanner_alive_max_s` | 75,0 | 10-300 | deroga "scanner vivo" | `feed.py:430` |
| `book_seen_max_s` | 90,0 | 5-600 | eta' massima del book visto | `feed.py:401` |
| `order_max_age_s` | 20,0 | 3-120 | freschezza per MANDARE un ordine | `feed.py:368` |
| `order_scanner_max_s` | 30,0 | 5-120 | scanner vivo per mandare un ordine | `feed.py:371` |

### 118. Parametri - Pre-match
| chiave | default | range / scelte | cosa governa | dove |
|---|---|---|---|---|
| `pre_enabled` | vero | - | ingressi pre-match | `engine.py:2502`; `service.py:1273` |
| `pre_entry_price_min` | 1,30 | 1,01-20 | quota minima Under | `engine.py:2524` |
| `pre_entry_price_max` | 3,00 | 1,01-20 | quota massima Under | `engine.py:2524` |
| `pre_min_back_size_factor` | 1,0 | 0,5-5 | liquidita' al best >= fattore x stake | `engine.py:2526, 2878, 3702` |
| `pre_max_spread_ticks` | 6 | 1-20 | spread massimo in tick | `engine.py:2534` |
| `pre_green_ticks` | 2 | 1-10 | tick del green pre-match | `engine.py:2751, 2763, 2825` |
| `pre_exit_mode` | "resting" | resting / taker | green appoggiato o al best | `engine.py:2747, 2824`; `service.py:1262, 1346` |
| `live_resting_enabled` | vero | - | valvola: in live, spenta, forza "taker" | `service.py:1263` |
| `pre_entry_ttl_s` | 60 | 5-3600 | vita dell'ordine d'ingresso | `engine.py:2684, 3735` |
| `pre_max_cycles` | 10 | 0-100 | cicli massimi | `engine.py:2517` |
| `pre_reentry_cooldown_s` | 60 | 0-3600 | pausa dopo un green | `engine.py:2519` |
| `pre_last_entry_min` | 10 | 1-120 | minuti prima del KO dell'ultimo ingresso | `engine.py:2515, 2633` |
| `last_entry_persist` | vero | - | ultimo ingresso in PERSIST | `engine.py:2861`; `service.py:1275` |
| `last_entry_ticks_above` | 0 | 0-3 | tick sopra il best dell'ultimo ingresso | `engine.py:2887` |
| `cancel_unmatched_after_ko_s` | 120 | 0-900 | ritiro del residuo PERSIST dopo il KO | `engine.py:2642, 3419` |

### 119. Parametri - Veto sulla probabilita' calibrata dell'Under 3.5
| chiave | default | range | cosa governa | dove |
|---|---|---|---|---|
| `veto_p_under35_cal` | vero | - | interruttore del veto | `engine.py:2573-2576` |
| `veto_p_under35_soglia_130` | 0,807 | 0-1 | P minima a quota 1,30 | `engine.py:2561` |
| `veto_p_under35_soglia_150` | 0,684 | 0-1 | P minima a quota 1,50 | `engine.py:2562` |
| `veto_p_under35_soglia_200` | 0,514 | 0-1 | P minima a quota 2,00 | `engine.py:2563` |
| `veto_p_under35_soglia_250` | 0,385 | 0-1 | P minima a quota 2,50 | `engine.py:2564` |
| `veto_p_under35_soglia_300` | 0,275 | 0-1 | P minima a quota 3,00 | `engine.py:2565` |

### 120. Parametri - Dal fischio d'inizio
| chiave | default | range | cosa governa | dove |
|---|---|---|---|---|
| `ko_green_enabled` | vero | - | uscita al fischio | `engine.py:2660` |
| `ko_green_ticks` | 2 | 1-10 | tick sotto l'ingresso | `engine.py:2662, 2994, 3124, 3145, 3154` |
| `ko_green_window_s` | 180 | 0-900 | durata della finestra | `engine.py:2981, 3055, 3059, 3151` |
| `ko_green_retry_s` | 5 | 1-60 | NESSUN EFFETTO: nessuno lo legge | nessun uso |
| `second_entry_enabled` | vero | - | seconda puntata dopo gol precoce | `engine.py:3044` |
| `second_entry_stake_pct` | 50,0 | 0-200 | % dello stake | `engine.py:3208` |
| `early_goal_cover_delay_s` | 120 | 0-900 | prima tranche dal gol | `engine.py:3172, 3236` |
| `early_goal_cover_pct` | 50,0 | 0-100 | % della prima tranche | `engine.py:3261` |
| `early_goal_cover2_delay_s` | 180 | 0-900 | seconda tranche dall'abbinamento della prima | `engine.py:3595` |

### 121. Parametri - Copertura live
| chiave | default | range / scelte | cosa governa | dove |
|---|---|---|---|---|
| `cover_enabled` | vero | - | copertura | `engine.py:3284` |
| `cover_profit_factor` | 1,2 | 1-3 | netto con 5+ gol = 20% | `engine.py:3333, 3481` |
| `cover_policy` | "auto" | auto / immediate / wait | come si decide l'attesa | `engine.py:1228` |
| `cover_wait_hazard_max` | 0,06 | 0-1 | attesa solo se hazard basso | `engine.py:1243` |
| `cover_wait_max_min` | 10 | 0-45 | attesa massima (minuto di gioco) | `engine.py:1237, 3363` |
| `cover_wait_p4_max` | 0,16 | 0-1 | attesa solo se P(4) bassa | `engine.py:1245` |
| `cover_good_price` | 7,0 | 1,01-50 | quota gia' buona -> copre | `engine.py:1247` |
| `cover_wait_min_gain_pct` | 8,0 | 0-100 | risparmio minimo per aspettare | `engine.py:1249` |
| `cover_wait_step_min` | 5 | 1-20 | orizzonte in minuti | `engine.py:1120`; `service.py:4229` |
| `cover_postgoal_delay_s` | 45 | 0-300 | attesa di riprezzo dopo un gol | `engine.py:1232, 3328` |
| `cover_max_goals` | 2 | 0-4 | oltre, nessuna copertura | `engine.py:1226` |
| `cover_rounding` | "ceil" | ceil / floor / nearest | arrotondamento con importi esatti spenti | `engine.py:506`; `service.py:751` |
| `cover_max_overshoot_pct` | 30,0 | 0-200 | eccesso massimo della copertura legalizzata | `engine.py:3373` |
| `exact_sizes` | vero | - | importi al centesimo | `engine.py:504, 3267`; `service.py:746` |
| `cover_rifiuti_max` | 3 | 1-20 | rifiuti con lo stesso codice prima del blocco | `engine.py:1609` |
| `cover_retry_min_s` | 15 | 1-300 | ritmo minimo fra due tentativi | `engine.py:1646` |
| `cover_place_at_ticks` | 2 | 0-6 | cuscinetto in tick | `engine.py:1697, 3315` |

### 122. Parametri - Cash out globale e intelligente
| chiave | default | range / scelte | cosa governa | dove |
|---|---|---|---|---|
| `cashout_profit_pct` | 5,0 | 0,5-50 | soglia piena | `engine.py:1092, 3527, 3529`; `service.py:4600` |
| `cashout_base` | "total" | total / under | base | `engine.py:1679` |
| `cashout_place_at_ticks` | 0 | 0-3 | tick "contro di noi" sulla chiusura | `engine.py:1804, 3515, 3534, 3619, 3644, 3667`; `service.py:3344, 4589, 4668` |
| `cashout_smart_enabled` | vero | - | cash out intelligente | `engine.py:1089` |
| `uscite_automatiche` | falso | - | chi esegue le uscite discrezionali | `engine.py:2247` |
| `cashout_smart_min_pct` | 2,0 | 0-50 | profitto minimo | `engine.py:1093` |
| `cashout_smart_tolerance_pct` | 2,0 | 0-50 | "a un passo" | `engine.py:1094` |
| `cashout_smart_hazard_hot` | 0,10 | 0-1 | fase calda: hazard | `engine.py:1103` |
| `cashout_smart_pressure_hot` | 1,15 | 1-1,25 | fase calda: pressione | `engine.py:1104` |
| `cashout_smart_goals_hot` | 3 | 0-8 | punteggio caldo | `engine.py:1100` |
| `cashout_smart_ev_margin_pct` | 1,0 | 0-50 | margine lontano dalla soglia | `engine.py:1125` |
| `close_retry_s` | 10 | 1-600 | riprezzo delle chiusure | `engine.py:2099, 2797, 3457, 3634, 3797` |
| `close_max_attempts` | 20 | 1-100 | tentativi massimi | `engine.py:2100, 2798, 3201, 3458, 3622, 3628, 3798` |

### 123. Parametri - Uscite in perdita HT / 2T
| chiave | default | range / scelte | cosa governa | dove |
|---|---|---|---|---|
| `loss_exit_mode` | "model" | model / fixed | a modello o fissa | `engine.py:3546` |
| `loss_exit_risk_premium_pct` | 10,0 | 0-300 | premio al rischio | `engine.py:1197` |
| `loss_exit_p4_prudent` | vero | - | P(4) mai sotto il mercato | `engine.py:1194` |
| `loss_exit_max_pct` | 0,0 | 0-100 | tetto oltre cui si tiene (0 = spento) | `engine.py:1203` |
| `loss_exit_emp_min_n` | 200 | 20-5000 | casi minimi della tabella HT->FT | `service.py:4231` |
| `ht_loss_exit_enabled` | vero | - | regola all'intervallo | `engine.py:3503` |
| `ht_loss_pct` | 25,0 | 0-100 | perdita tollerata HT | `engine.py:3504` |
| `ht_loss_goals_min` | 3 | 0-8 | gol minimi (HT e 2T) | `engine.py:3543` |
| `ht_loss_goals_max` | 4 | 0-8 | gol massimi (HT e 2T) | `engine.py:3543` |
| `h2_loss_exit_enabled` | vero | - | regola nel 2T | `engine.py:3505` |
| `h2_loss_pct` | 25,0 | 0-100 | perdita tollerata 2T | `engine.py:3507` |
| `h2_loss_from_min` | 46 | 45-100 | inizio finestra 2T | `engine.py:3506` |
| `h2_loss_to_min` | 85 | 45-100 | fine finestra 2T | `engine.py:3506` |

### 124. Parametri - Re-ingresso Under 4.5
| chiave | default | range | cosa governa | dove |
|---|---|---|---|---|
| `reentry_enabled` | vero | - | re-ingresso | `engine.py:3686`; `service.py:1274` |
| `reentry_green_ticks` | 2 | 1-10 | tick del green | `engine.py:3718, 3774` |
| `reentry_max_goals` | 1 | 0-1 | gol ammessi | `engine.py:3691` |
| `reentry_until_min` | 45 | 0-100 | minuto massimo | `engine.py:3693` |
| `reentry_exit_until_min` | 0 | 0-100 | chiusura forzata (0 = mai) | `engine.py:3752` |
| `reentry_price_min_over_entry` | vero | - | quota > primo ingresso | `engine.py:3698` |
| `reentry_hold_if_loss` | falso | - | tiene se in perdita alla chiusura forzata | `engine.py:3754` |

### 125. Parametri - Regolamento e rischio
| chiave | default | range | cosa governa | dove |
|---|---|---|---|---|
| `settle_confirm_s` | 60 | 0-600 | lettura REST a mercato chiuso | `service.py:4084, 4352` |
| `max_open_matches` | 10 | 1-90 | partite con posizione | `service.py:3585, 3626, 4444` |
| `daily_loss_stop` | 50,0 | 0-100000 | stop giornaliero | `service.py:3552` |
| `max_liability_per_match` | 0,0 | 0-100000 | capitale per partita (0 = spento) | `engine.py:1711, 2883, 2884` |
| `event_loss_cap_pct` | 100,0 | 0-500 | cap perdita partita | `engine.py:3579` |
| `skip_log_interval_s` | 300 | 10-3600 | un log ripetuto ogni N s | `service.py:1289` |

### 126. Parametri - Respiro del database (letture)
| chiave | default | range | cosa governa | dove |
|---|---|---|---|---|
| `feed_cache_s` | 4,0 | 0-30 | rilettura del feed | `service.py:5865` |
| `events_reload_s` | 60,0 | 0-600 | rilettura completa delle partite | `service.py:3505` |
| `aggregates_cache_s` | 20,0 | 0-300 | cache aggregati (stop giornaliero) | `service.py:1112` |
| `reconcile_every_s` | 30,0 | 0-600 | riparazione gambe/righe e sorveglianza conto | `service.py:2780, 4029` |
| `idle_cycle_s` | 5,0 | 1-60 | ciclo lento a riposo | `service.py:3894, 6062` |

### 127. Parametri - Respiro del database (scritture e battito)
| chiave | default | range | cosa governa | dove |
|---|---|---|---|---|
| `publish_heartbeat_s` | 5,0 | 0-120 | riscrittura partita con posizione | `service.py:5434` |
| `publish_idle_heartbeat_s` | 60,0 | 0-600 | riscrittura partita solo osservata | `service.py:5435` |
| `events_batch_write` | vero | - | una sola scrittura per tutte le righe | `service.py:5532` |
| `stats_min_s` | 10,0 | 0-300 | cadenza statistiche | `service.py:3780-3781` |
| `heartbeat_min_s` | 20,0 | 0-300 | cadenza battito | `service.py:3779, 3782, 3895` |

### 128. Variabili d'ambiente lette con gli aiuti di config
- `MIKE_LOCK_PORT` (default 47319, `service.py:47`); `MIKE_LIVE_ENABLED` (default falso, `service.py:98`); `MIKE_USE_FLUMINE_QUEUE` (default falso, `service.py:781`); `SAFE_PRE_KO_OU_HOURS` (default 0, `service.py:3953`).

---

## Glossario

- **Book**: la fotografia delle quote di una selezione.
- **Gamba**: una scommessa del bot.
- **pending / pending_reconcile / open / cancelled / settled**: viva sul mercato / esito ignoto / non piu' viva / mai abbinata e ritirata / regolata.
- **archiviata**: gamba di un ciclo chiuso: resta nei conti, non nel rischio.
- **LAPSE / PERSIST**: l'ordine muore alla sospensione / l'ordine resta in gioco.
- **Ruoli**: `under_entry` (ingresso), `under_green` (green pre-match), `under_last` (ultimo ingresso PERSIST), `under_second` (seconda puntata dopo un gol precoce), `ko_green` (uscita al fischio), `over_cover` (copertura Over 4.5), `under_close` / `over_close` (chiusure di cash out), `reentry` (re-ingresso Under 4.5), `reentry_green` (green del re-ingresso), `manual_close` (chiusura manuale).
- **Stati**: WATCH (osserva), PRE_ENTRY_PENDING (ingresso sul book), PRE_OPEN (Under abbinato, green in corso), PRE_GREEN_PENDING (green in attesa), HOLD (tiene l'Under in perdita), PRE_LAST_ENTRY_PENDING (ultimo ingresso sul book), IDLE_LIVE (in gioco senza posizione), LIVE_KO_GREEN (uscita al fischio), LIVE_SECOND_ENTRY (seconda puntata), LIVE_UNCOVERED (Under senza copertura), LIVE_COVER_PENDING (copertura sul book), LIVE_COVERED (coperti), LIVE_CLOSING (chiusura), FLAT (piatto), REENTRY_PENDING / REENTRY_OPEN / REENTRY_GREEN_PENDING (re-ingresso), SETTLING (regolamento), SETTLED (regolata), ERROR (errore), SKIPPED (saltata).
- **Tipi di uscita**: greenup, profit, loss, time, forced, manual, other (scheda 47).
- **Motivi di chiusura**: profit, loss_ht, loss_2t, loss_cap, manual, reentry_time.
- **LIVE_COVER_BLOCKED**: copertura fermata dal freno dei rifiuti.
- **Proposta di uscita / firma**: `uscita_proposta` / `uscita_approvata`.
- **Categorie d'uscita**: chiusura, ko_green, green_pre, reentry_green.
- **Hazard 3'**: probabilita' di un gol nei prossimi 3 minuti.
- **P(4)**: probabilita' che la partita finisca con esattamente 4 gol.
- **Place-and-trim**: parcheggia a quota non abbinabile, taglia, riprezza.
- **Telemetria**: dati che accompagnano la decisione per pagina e attivita'.
- **Aperture ferme**: aperture bloccate per una causa che non e' il mercato.

---

## Differenze dalla Costituzione

1. **Uscite automatiche / manuali.** §15.7-ter: proposte "ANNULLATO... Le uscite di Mike restano automatiche". Codice: `gate_uscite` con `uscite_automatiche` di default FALSO (proposte). `engine.py:2243-2248`, `2337-2431`; `config.py:254`. La Costituzione non nomina ne' `gate_uscite` ne' `uscite_automatiche`.
2. **feed_max_age_s.** §6: 15. Codice: 45. `config.py:95`. §5: "riga > 15 s E scanner muto > 30 s"; codice: `feed_max_age_s` 45, `scanner_alive_max_s` 75, piu' `order_max_age_s` 20 / `order_scanner_max_s` 30 / `book_seen_max_s` 90 non documentati. `config.py:95-116`.
3. **ht_loss_goals_min.** §6: 2; §3 Fase 5: "Solo con 2, 3 o 4 gol". Codice: 3. `config.py:287`.
4. **Numero di parametri.** §6: 72 chiavi. Codice: 106. `config.py:75-379`.
5. **Lay appoggiata in live.** §7: "`_params_for` forza `pre_exit_mode = 'taker'`". Codice: forzato solo se `live_resting_enabled` e' falso (default vero). `service.py:1262-1264`; `config.py:137`.
6. **Finestra pre-match.** §1 e §3 Fase 1: 3 ore. Codice: `entry_hours_before_ko` 1,0. `config.py:85` (la §6 invece e' allineata a 1).
7. **Commissione nel cash out.** §3 Fase 4: "commissione 5% solo sulle selezioni in positivo". Codice: per MERCATO sul netto positivo, ripartita in proporzione. `engine.py:778-802` (la §4.4 invece e' allineata).
8. **Lettura del regolamento.** §3 Fase 7 e §2: "ogni 30 s". Codice: `settle_confirm_s` 60. `config.py:305`.
9. **Formula della copertura.** §3 Fase 3: "S = euro Under abbinati". Codice: la perdita NETTA dell'Under (punte meno bancate abbinate) meno la protezione gia' garantita; importo calcolato sulla quota migliore; ordine piazzato 2 tick piu' in basso. `engine.py:459-465`, `426-435`, `1687-1704`; `3299-3314`.
10. **Parametri non documentati.** Il §6 non elenca `cover_rifiuti_max`, `cover_retry_min_s`, `cover_place_at_ticks`, `veto_p_under35_*`, `live_resting_enabled`, `uscite_automatiche`, `book_seen_max_s`, `order_max_age_s`, `order_scanner_max_s`, `scanner_alive_max_s`. `config.py`.
11. **cashout_place_at_ticks.** §6: "chiusura N tick oltre il best (resting)". Codice: la quota si sposta contro di noi per abbinare subito; non e' un ordine appoggiato. `greenup.py:55-70`.
12. **Numero di stati.** §8: "19 stati". Codice: 21. `engine.py:37-43`.
13. **Freno della copertura.** Non descritto nella Costituzione (§15.7-ter parla solo di `_mai_sovracopertura`); in `decide` il freno viene PRIMA di `_una_sola_lay`. `engine.py:2208-2212`.
14. **"Ultima parola".** §15.7: `_una_sola_lay` e' "l'ultima parola"; nel codice dopo vengono anche `_mai_sovracopertura` e `gate_uscite`. `engine.py:2209-2216`.

---

## Cose strane

1. `cover_size` (scheda 15), `cover_size_residual` (17) e `force_flat_actions` (86) non hanno chiamanti in produzione: solo nei test.
2. `ko_green_retry_s` non e' letto da nessun ramo (`config.py:173`); la docstring di `tentativo_gia_rifiutato` dice che `_decide_ko_green` "da sempre" aspetta `ko_green_retry_s` (`engine.py:1525-1529`): non e' piu' vero.
3. `cover_place_price`: la docstring dice "La size si dimensiona SU QUESTO prezzo, mai sul best" (`engine.py:1693`); il chiamante calcola l'importo sul BEST (`engine.py:3313`) e i due commenti in `3303-3312` si contraddicono fra loro.
4. `gate_uscite`: la docstring dice "interruttore ACCESO (default)" (`engine.py:2340`); il default e' SPENTO (`engine.py:2247`, `config.py:254`).
5. Veto Under 3.5: `config.py:144` dice "ACCESO di default" (vero); `engine.py:352` dice "interruttore veto_p_under35_cal SPENTO".
6. `_close_actions`: il commento dice che sotto i 2 euro non si tenta (`engine.py:1765-1772`); la soglia vera e' 1 centesimo (`size_chiudibile`, `engine.py:1734`). `size_chiudibile` controlla >= 0,0095 dopo che `size_ok` ha gia' preteso >= 0,01: il secondo controllo non serve a niente.
7. `cover_timing`: la docstring dice "ogni dato mancante = si copre"; con i gol mancanti `int(goals or 0)` li conta come 0 e il bot puo' ASPETTARE (`engine.py:1225`). Stesso trattamento in `smart_cashout` (`engine.py:1099`).
8. `_freno_copertura` scarta TUTTI gli aggiornamenti della decisione, non solo tentativi e fase della tranche come dice il commento (`engine.py:2073`).
9. `_decide_flatten`: a tentativi esauriti (20) resta "attendo il fill" senza piu' riprezzare; il cash out manuale puo' restare fermo (`engine.py:2100-2103`).
10. `gate_uscite` a interruttore spento lascia passare solo i ritiri di ingresso: se una decisione contenesse insieme un'uscita e un'apertura (o una copertura), anche l'apertura/copertura verrebbe tolta (`engine.py:2410`). Non ho trovato un ramo che lo faccia oggi (vedi "Non ho capito").
11. `liability_room` e `max_liability_per_match` misurano il capitale PUNTATO (`invested`), non la perdita peggiore (`engine.py:1714`).
12. `_coerce` non respinge "NaN": un valore float NaN passa i confronti min/max e arriva ai calcoli (`config.py:445-449`).
13. `cover_rounding` legalizza anche le punte di apertura (`service.py:751`), non solo la copertura.
14. `cover_max_overshoot_pct` lavora solo con `exact_sizes` spento: con importi esatti l'eccesso e' sempre 0 (`engine.py:505`).
15. `settle_legs_by_market` riusa il nome `winners` per una variabile interna (`engine.py:1330`) che nasconde il parametro: innocuo perche' dopo il primo uso.
16. `_market_pnl_by_total` non salta le gambe archiviate (a differenza di `exposure`): e' voluto per il regolamento ma i nomi non lo dicono (`engine.py:707-719`).
17. `cashout_value` con nessuna selezione aperta restituisce "completo" con valore 0 (`engine.py:750`).
18. `FOOTBALL_EVENT_TYPE_ID` e `env_str` non sono usati in `Betfair/mike` fuori da config.
19. `APPROVAZIONE_TTL_S` (120 s) non e' un parametro della UI (`engine.py:2240`).

---

## Non ho capito / non ho letto

- Non ho letto i rami di strategia (`engine.py` da 2495 in poi) oltre le righe citate: altri delegati.
- Non ho letto `feed.py`: non so con certezza come `feed_max_age_s`, `scanner_alive_max_s`, `book_seen_max_s`, `order_max_age_s`, `order_scanner_max_s`, `competition_filter` ed `entry_hours_before_ko` si combinano.
- Non ho letto le righe di `service.py` che usano i parametri di cadenza, rischio e regolamento: ho solo verificato dove sono letti.
- `frazione_copertura`, `valuta_veto_under35` e `_late_persist_cancel` sono fuori area: non verificati.
- Non ho verificato se esiste oggi un ramo che mette nella stessa decisione un'uscita discrezionale e un'apertura (punto 10 di "Cose strane").
- `compute_greenup` letto solo nella parte usata da Mike; `get_nearest_price` / `price_ticks_away` (flumine) non letti.
- Chi scrive `uscita_approvata` (servizio / `Betfair/stream/uscite_proposte.py`): non letto.
