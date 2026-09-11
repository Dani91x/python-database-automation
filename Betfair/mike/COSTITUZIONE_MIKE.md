# COSTITUZIONE MIKE — bot di trading Under 3.5 / Over 4.5

Documento normativo e spiegazione completa del bot Mike (sezione "Mike" dell'app, `/mike`).
Come le costituzioni di Omega e Safe Strategy: ciò che è scritto qui vale più di ogni parametro.
Aggiornato all'11/09/2026 (codice in `Betfair/mike/`, UI in `frontend/src/components/mike/`).

---

## §0 Verdetto di partenza e gate

- La struttura STATICA del bot legacy MIKE2 (back Under 3.5 + back Over 4.5 tenuti fino al 90')
  è **NO-GO** su 18.441 partite reali: ROI −9,67%, con le regole esatte di MIKE2 −6,36%.
  La probabilità reale di "esattamente 4 gol" è 14,7% ed è prezzata correttamente dal mercato:
  non esiste un edge a tenere la scommessa fino alla fine.
- Mike NON è quella scommessa. È un bot di **TRADING**: guadagna i tick del green-up pre-match,
  si copre in-play sull'Over 4.5, esce a profitto o con una perdita piccola prima che il 4° gol
  possa farlo perdere tutto. L'obiettivo dichiarato è **evitare tassativamente la somma gol 4**
  senza uscire troppo presto.
- Fatti noti che impongono prudenza: il green-up in-play simulato dell'Under resta negativo
  (−9,4% → −3,4% con modello equo); il back Under in-play (theta) è EV− in tutte le varianti
  testate; a 0-0 l'Under 3.5 decade solo ~0,5 tick al minuto.
- Quindi: **paper-first**. GO/NO-GO al live solo dopo almeno 40 partite paper complete e un
  backtest sulle registrazioni REC con haircut −1 tick sui fill taker. Il verdetto va scritto QUI,
  in questo paragrafo, con i numeri.

---

## §1 Che cos'è Mike in una frase

Per ogni partita di calcio con calcio d'inizio entro 3 ore, Mike punta l'Under 3.5 pre-match e lo
chiude subito a +2 tick (green-up, ripetuto finché c'è tempo); se arriva in-play con l'Under
aperto, compra una copertura sull'Over 4.5 dimensionata per guadagnare il 20% se finisce 5+ gol,
poi chiude tutto al primo profitto del 5% (o prima, se il rischio lo consiglia), oppure esce
con una perdita piccola all'intervallo o nel secondo tempo quando i 4 gol sono troppo probabili.

Unica famiglia di esiti: con 0-3 gol vince l'Under, con 5+ gol vince l'Over, con **esattamente 4**
gol perdono entrambi. Tutto il bot è costruito attorno a questa casella.

---

## §2 Da dove arrivano i dati (regola dei processi: nessuna chiamata Betfair duplicata)

| Dato | Fonte | Note |
|---|---|---|
| Quote back/lay, size, stato mercato, in-play, betDelay | **feed unico** `safe_strategy_scan` (scanner della Safe Strategy) | ramo pre-KO O/U acceso con env `SAFE_PRE_KO_OU_HOURS=3`: pubblica le linee 3.5 e 4.5 già 3 ore prima del KO. Una SELECT per ciclo |
| Minuto, punteggio, espulsioni, intervallo, corner/cartellini | stesso feed (`score_raw`, `timeline`) | ritardo punteggi 2-3 s: ricordarlo |
| λ Dixon-Coles per squadra, ρ, calibrati | `fixture_predictions` via ponte evento→fixture (`live_follow`) | letture DB, zero Betfair |
| Hazard di gol nei 3' successivi | Atlante hazard (theta, 54.009 partite) | JSON caricato una volta |
| Distribuzione HT→FT | tabella empirica Omega (RPC `get_omega_ht_ft`) | cache per lega, retry ogni 10' |
| Regolamento (esito dei runner) | REST `listMarketBook`, 2 chiamate per partita, solo a mercato chiuso | throttle 30 s |
| Ordini | `safe_strategy/execution.place` (paper = fill sul feed; live = REST FOK con la sessione condivisa) | stessa macchina di Omega e Safe |

Mike NON ha un login proprio, NON apre connessioni stream, NON ha un catalogo proprio.
Costo aggiunto alla piattaforma: un processo (`mike-service` sotto watchdog, lock porta 47319) e
2 mercati per partita in finestra sul pool stream dello scanner (tier 2, capacità 720, ~100 usati).

I selection ID vengono risolti PER NOME dal catalogo ad ogni partita e confrontati con quelli
attesi (Under 3.5 = 1222344, Over 3.5 = 1222345, Over 4.5 = 1222346, Under 4.5 = 1222347):
uno scostamento è loggato come WARN. Certificazione dell'11/09: 44 selezioni su 11 partite, zero scostamenti.

---

## §3 La vita di una partita, fase per fase

Ogni partita è una macchina a stati indipendente (`engine.py`, logica pura senza I/O).
Il servizio (`service.py`) gira ogni 1-2 secondi: legge il feed, costruisce lo `Snapshot`
(book, minuto, gol, hazard, probabilità di modello), chiama `decide`, esegue le azioni, salva.

```
WATCH → PRE_ENTRY_PENDING → PRE_OPEN → PRE_GREEN_PENDING → WATCH (ciclo+1) …
                                │ KO − 10'
                                ├─ in perdita → HOLD → LIVE_UNCOVERED
                                └─ in profitto → green taker + PRE_LAST_ENTRY_PENDING (PERSIST) → LIVE_UNCOVERED
LIVE_UNCOVERED ─copertura─► LIVE_COVER_PENDING → LIVE_COVERED ─profitto / uscita─► LIVE_CLOSING → FLAT
FLAT ─1 gol, chiusura precedente in profitto─► REENTRY_PENDING → REENTRY_OPEN → REENTRY_GREEN_PENDING → FLAT
mercato CLOSED → SETTLING → SETTLED · errore → ERROR · "Salta" dalla UI → SKIPPED
```

### Fase 1 — Pre-match: ingresso e green-up ciclico (da KO − 3h a KO − 10')

Condizioni di ingresso (tutte insieme, ogni ciclo):
```
mercato Under/Over 3.5 APERTO, non in-play, feed fresco
quota BACK Under 3.5 fra 1,30 e 3,00
liquidità al best ≥ stake (fattore 1,0)
spread back/lay ≤ 6 tick    (ingresso MOLTO anticipato: i book larghi sono normali ore prima)
cicli fatti < 10 · cooldown 60 s dall'ultimo green · stop giornaliero non attivo · tetto partite non raggiunto
```
Cosa fa:
```
BACK Under 3.5 stake (10 €) al best, LAPSE, TTL 60 s (non abbinato → annullato, si riprova)
appena abbinato → LAY resting a −2 tick (green-up) appoggiata SUBITO sul book
lay abbinata → profitto bloccato su entrambi gli esiti, ciclo +1 → WATCH → nuovo ingresso
lay non abbinata → si aspetta (mai chiudere in perdita pre-match)
```
Esempio: BACK 10 € @ 1,50 → LAY 10,14 € @ 1,48 sul book. Presa: +0,14 € lordi qualunque sia
il finale. Con 10 cicli in 3 ore: ~+1,3 €. Fill parziali: la lay è sempre dimensionata
sull'esposizione NETTA abbinata (mai sulla size chiesta).

### Fase 2 — Ultimo ingresso (KO − 10')

```
posizione in PROFITTO (lay a +2 tick abbinabile ora) → green taker al best + NUOVO BACK Under 3.5
                                                       con persistenza PERSIST (resta valido in-play)
posizione in PERDITA                                 → HOLD: si tiene l'Under e si entra live scoperti
residuo PERSIST non abbinato 120 s dopo il KO       → annullato (niente fill su spike post-gol)
```
Perché PERSIST: il mercato sospende al calcio d'inizio e gli ordini LAPSE vengono cancellati.

### Fase 3 — Live: copertura sull'Over 4.5 ("intelligente ma non lenta")

Formula: `X = 1,2 × S / ((Po − 1) × (1 − c))` con S = euro Under abbinati, Po = quota Over 4.5,
c = 5% commissione. Con 5+ gol il netto è **+20% di S**; con 0-3 gol si perde X; con 4 gol
si perde S + X.

Quando copre:
```
0 gol e TUTTE le seguenti → ASPETTA (max 10'): hazard 3' ≤ 6% · P(4) mercato ≤ 16% ·
                            quota Over < 7,0 · risparmio atteso in 5' ≥ 8%
una sola che cade          → COPRE nello stesso ciclo
dopo un gol                → 45 s di riprezzo, poi COPRE (X raddoppia: la quota Over si dimezza)
3+ gol                     → nessuna copertura (la gestione passa al cash-out / uscita)
dati mancanti              → COPRE subito (mai attesa al buio)
```
Hazard 3' = MAX fra Atlante empirico (minuto, gol, lega, squadre) e modello λ-residue
amplificato dalla pressione (corner/cartellini, fino a ×1,25). Comanda la fonte più prudente.
Esempi: S = 10 € @ 1,50 · 7' 0-0 quota 6,6 → BACK 2,26 € · 12' 1-0 quota 3,5 → BACK 5,05 €.

### Fase 4 — Cash-out globale a profitto (stato LIVE_COVERED)

Ogni ciclo il bot calcola "quanto incasso se chiudo ORA entrambe le selezioni con una LAY di
full green ciascuna" (stessa aritmetica del ladder, `compute_greenup`), commissione 5% solo sulle
selezioni in positivo. Base = capitale investito S + X (parametro: total | under).

Regola piena: **valore netto ≥ 5% della base → chiude tutto** (LIVE_CLOSING).
Esempio (10 € @ 1,50 + 2,26 € @ 6,6, base 12,26 €, soglia 0,61 €):
```
30' 0-0  Under lay 1,30 → +1,46 | Over lay 12 → −1,02 → +0,44 € (3,6%)  TIENE
40' 0-0  Under lay 1,22 → +2,18 | Over lay 18 → −1,43 → +0,75 € (6,1%)  CHIUDE: +0,75 € certi, anche con 4 gol
```

**Cash-out intelligente** (chiude PRIMA della soglia, mai sotto il profitto minimo del 2%):
1. **punteggio caldo**: 3+ gol (il prossimo è il 4°) → chiude appena sopra il minimo;
2. **fase calda a un passo dalla soglia**: entro 2 punti dal 5% E (hazard 3' ≥ 10% O pressione ≥ 1,15) → chiude;
3. **valore atteso dell'attesa** (modello): `EV = h·V_gol + (1−h)·V_dopo` con h = P(gol entro 5')
   dall'hazard, V_gol/V_dopo = valore del cash-out con i book proiettati dal modello (quota di
   mercato scalata per P_ora/P_scenario). Vicino alla soglia basta EV < valore attuale; lontano
   serve un margine di 1 punto.
Esempi: 30' 0-0 +0,44 € con 5 corner in 8' e hazard 11% → CHIUDE · 55' 2-1 +0,30 € → CHIUDE
(3 gol) · 40' 0-0 +0,20 € (1,6%) → TIENE (sotto il minimo).

### Fase 5 — Uscita in perdita all'intervallo e nel 2° tempo (a MODELLO)

Finestre: intervallo (feed "half time") e dal 46' all'85'. Solo con **2, 3 o 4 gol** totali
(con 0-1 gol l'Under è avanti: si va verso il profitto). Precedenza: profitto → intelligente →
uscita in perdita → cap.

Decisione a modello (`loss_exit_mode = model`):
```
CHIUDO ORA = valore certo del cash-out (negativo)
TENGO      = Σ P(gol totali = t) × P&L(t)  −  premio al rischio (50% × P(4) × capitale)
chiude se CHIUDO ORA ≥ TENGO − premio
```
P(gol totali) = media fra griglia Omega (λ, minuto, punteggio, rossi) e tabella empirica HT→FT
(parla finché il punteggio è quello dell'intervallo); P(4) prudente = la più pessimista fra
modello/empirico e mercato. Senza dati di modello → regola fissa "perdita ≤ 25% del capitale".
Esempi (Under 20 € @ 1,50 + Over 4 € @ 8, capitale 24 €):
```
HT 1-1  chiudo −5,51 (23%)  tengo −0,79 · P(4) 22% · premio 2,64 → soglia −3,43 → TIENE
        (la regola fissa avrebbe chiuso: uscita troppo presto)
HT 2-1  chiudo −6,53 (27%)  tengo −3,08 · P(4) 30% · premio 3,60 → soglia −6,68 → CHIUDE
        (la regola fissa avrebbe tenuto: il 4° gol era troppo probabile)
HT 1-1  mercato prezza P(4) al 45%                                           → CHIUDE
```
Dopo un'uscita in perdita → FLAT senza re-ingresso.

### Fase 6 — Re-ingresso live (una sola volta per partita)

```
SOLO se la chiusura precedente della partita è stata in PROFITTO
SOLO dopo un gol: esattamente 1 gol totale, nel 1° tempo (minuto ≤ 45)
quota BACK Under 4.5 > quota del primo ingresso Under 3.5 · liquidità ≥ stake · feed fresco
BACK Under 4.5 stesso stake → LAY resting a +2 tick
lay abbinata → profitto, FLAT · lay non abbinata → resta sul book fino a fine gara (Under 4.5 vince con ≤ 4 gol)
```
Nessuna chiusura forzata (parametro `reentry_exit_until_min` = 0 = mai; esiste solo come opzione).

### Fase 7 — Fine gara, regolamento, sicurezze

Regolamento: mercato CLOSED nel feed → lettura REST del book ogni 30 s → Under 3.5 WINNER = 0-3
gol, Over 4.5 WINNER = 5+, Over 3.5 + Under 4.5 WINNER = 4 gol → ogni gamba abbinata won/lost,
commissione per mercato sul netto positivo, gambe mai abbinate void → SETTLED → scheda "Regolate"
e storico giornaliero. Dopo 2 ore senza esito: ultimo punteggio del feed (`settle_fallback`), altrimenti ERROR.

Una riga ASSENTE dal feed vale come mercato chiuso solo dopo 10 minuti di assenza (o partita
finita): al calcio d'inizio il feed passa dal blocco pre-KO a quello in-play e la riga può
sparire per qualche minuto. Un SETTLING falso viene annullato ricostruendo lo stato dalle posizioni.

Partite arrivate in-play senza mai avere una gamba (KO senza ingresso, o armate a partita già
iniziata) → SETTLED "nessuna operazione" subito, senza P&L.

---

## §4 Matematica certificata (invarianti money-critical)

1. Esposizioni SOLO dai fill (`Leg.matched`, `avg_price`), mai dalla size chiesta. Ogni ordine
   sul lato opposto (green, copertura, chiusura, riprezzo) è dimensionato sull'esposizione NETTA
   abbinata: i fill parziali sono coerenti per costruzione (test dedicati).
2. Green-up e cash-out con `compute_greenup` (stessa aritmetica del ladder):
   posizione back W/L → LAY al best lay, bloccato = L + (W − L)/lay.
3. Copertura `X = factor·S/((Po−1)(1−c))`; residuo con `cover_size_residual` sui fill parziali:
   con 5+ gol il netto è ESATTAMENTE +20% di S.
4. Commissione per MERCATO sul netto positivo (come `execution.settle_group`).
5. P&L per gol totali (`net_pnl_by_total`) coerente con `pnl_by_scoreline`.
6. Prezzo mancante → nessuna azione (`cashout_value.complete = False`), mai numeri inventati.
7. Cicli pre-match chiusi = `Leg.archived`: contabilità sì, capitale a rischio no.
8. Riprezzo di una chiusura parzialmente abbinata = SOLO il residuo, sull'esposizione inclusiva.
9. `max_liability_per_match` è un clamp DENTRO l'engine (vale anche a UI mal configurata).
10. Mode (paper | live) SOLO da `mike_control.mode`; il codice non promuove mai a live.
11. Un ordine live con esito REST IGNOTO non è mai "dato per non piazzato": partita in ERROR,
    riconciliazione manuale.

---

## §5 Sicurezze sempre attive

| Sicurezza | Regola |
|---|---|
| Stop giornaliero | P&L realizzato della giornata operativa (Europe/Rome) ≤ −50 € → nessuna partita nuova, niente ingressi né re-ingressi, SOLO chiusure. Tile rossa "STOP giornaliero ATTIVO" |
| Tetto partite | max 10 partite con POSIZIONE (WATCH e in-play senza posizione non contano) |
| Capitale per partita | `max_liability_per_match` (0 = off): blocca ingresso, copertura e re-ingresso oltre il tetto |
| Cap perdita partita | `event_loss_cap_pct`: chiude tutto a qualsiasi minuto se la perdita bloccabile lo raggiunge |
| Feed stantio | riga > 15 s E scanner muto > 30 s → nessun ingresso/re-ingresso; chiusure permesse |
| Ordine senza esito | pending > 120 s con esito ignoto → gamba `pending_reconcile` (MAI `cancelled`/`error` per TTL): conta nella liability al peggior caso, blocca ogni nuovo ingresso sulla partita, attività `reconcile_pending`; in paper si risolve subito (nessun ordine è mai partito), in live si riconcilia contro `listCurrentOrders`/`listClearedOrders` per `customerOrderRef` `mike-t<id>`. La lay appoggiata è esclusa: resta sul book legittimamente |
| PERSIST al KO | residuo non abbinato annullato 120 s dopo il KO |
| Processo | lock porta 47319 (una istanza), watchdog, stato riletto dal DB ad ogni ciclo |
| Bot fermo | nessun ingresso; posizioni aperte gestite fino al regolamento |

Comandi UI (mai su SETTLED/ERROR): **Cash out** (chiude tutte le gambe al best, senza soglia),
**Flatten**, **Salta** / **Riprendi**, **Ferma bot**.

---

## §6 Parametri (tutti editabili dalla UI, gruppo per gruppo)

Whitelist in `config.PARAM_SPEC` (default, tipo, min, max, scelte), specchiata in
`frontend/src/lib/mike.ts`. Chiavi ignote scartate, valori fuori banda riportati nel range,
coppie min/max invertite → default. `mode` NON è un parametro.

**Generale**
| chiave | default | significato |
|---|---|---|
| stake | 10,0 (0,50–500) | importo LIBERO per gamba (anche 1,23 €): sotto-minimo via place-and-trim |
| commission_pct | 5 | commissione Betfair |
| entry_hours_before_ko | 3 | finestra pre-match (deve combaciare con `SAFE_PRE_KO_OU_HOURS`) |
| competition_filter | "" | CSV di competizioni ammesse (vuoto = tutte) |
| feed_max_age_s | 15 | età massima della riga del feed |
| decide_min_interval_ms | 500 | intervallo minimo fra due decisioni |

**Pre-match**
| chiave | default | significato |
|---|---|---|
| pre_enabled | on | |
| pre_entry_price_min / max | 1,30 / 3,00 | banda di quota dell'Under 3.5 |
| pre_min_back_size_factor | 1,0 | liquidità al best ≥ fattore × stake |
| pre_max_spread_ticks | 6 | spread massimo back/lay |
| pre_green_ticks | 2 | tick del green-up |
| pre_exit_mode | resting | resting = lay appoggiata subito; taker = chiude al best quando disponibile |
| pre_entry_ttl_s | 60 | vita dell'ordine di ingresso |
| pre_max_cycles | 10 | cicli massimi per partita |
| pre_reentry_cooldown_s | 60 | pausa dopo un green |
| pre_last_entry_min | 10 | minuti prima del KO per l'ultimo ingresso |
| last_entry_persist | on | ultimo ingresso in PERSIST |
| last_entry_ticks_above | 0 | ultimo ingresso N tick sopra il best |
| cancel_unmatched_after_ko_s | 120 | annullo del residuo PERSIST dopo il KO |

**Copertura Over 4.5**
| chiave | default | significato |
|---|---|---|
| cover_enabled | on | |
| cover_profit_factor | 1,2 | +20% di S con 5+ gol |
| cover_policy | auto | auto / immediate / wait |
| cover_wait_hazard_max | 0,06 | attende solo se hazard 3' ≤ 6% |
| cover_wait_max_min | 10 | attesa massima |
| cover_wait_p4_max | 0,16 | attende solo se P(4) mercato ≤ 16% |
| cover_good_price | 7,0 | copre subito se la quota Over è già ≥ 7 |
| cover_wait_min_gain_pct | 8 | attende solo se il risparmio atteso in N' ≥ 8% |
| cover_wait_step_min | 5 | orizzonte del risparmio (e dell'EV del cash-out) |
| cover_postgoal_delay_s | 45 | riprezzo dopo un gol |
| cover_max_goals | 2 | nessuna copertura oltre |
| cover_rounding, cover_max_overshoot_pct, exact_sizes | ceil, 30, on | legalizzazione .it solo se `exact_sizes` = off |

**Cash-out globale**
| chiave | default | significato |
|---|---|---|
| cashout_profit_pct | 5 | soglia piena |
| cashout_base | total | total = S + X; under = solo S |
| cashout_place_at_ticks | 0 | chiusura N tick oltre il best (resting) |
| cashout_smart_enabled | on | cash-out intelligente |
| cashout_smart_min_pct | 2 | profitto minimo per chiudere prima |
| cashout_smart_tolerance_pct | 2 | "a un passo" = entro N punti dalla soglia |
| cashout_smart_hazard_hot | 0,10 | fase calda: hazard 3' |
| cashout_smart_pressure_hot | 1,15 | fase calda: pressione |
| cashout_smart_goals_hot | 3 | punteggio caldo |
| cashout_smart_ev_margin_pct | 1 | margine EV lontano dalla soglia |
| close_retry_s / close_max_attempts | 10 / 20 | riprezzo del residuo di chiusura |

**Uscite HT / 2T**
| chiave | default | significato |
|---|---|---|
| loss_exit_mode | model | model / fixed |
| loss_exit_risk_premium_pct | 50 | premio al rischio (% capitale × P(4)) |
| loss_exit_p4_prudent | on | P(4) = max(modello/empirico, mercato) |
| loss_exit_max_pct | 0 | tetto "non cristallizzare oltre" (0 = off) |
| loss_exit_emp_min_n | 200 | casi minimi della tabella HT→FT |
| ht_loss_exit_enabled / ht_loss_pct | on / 25 | regola fissa all'intervallo (fallback) |
| ht_loss_goals_min / max | 2 / 4 | gol per cui vale l'uscita (HT e 2T) |
| h2_loss_exit_enabled / h2_loss_pct | on / 25 | regola fissa nel 2T (fallback) |
| h2_loss_from_min / to_min | 46 / 85 | finestra del 2T |

**Re-ingresso**
| chiave | default | significato |
|---|---|---|
| reentry_enabled | on | |
| reentry_green_ticks | 2 | |
| reentry_max_goals | 1 | 1 = linea Under 4.5 (unica nel feed) |
| reentry_until_min | 45 | gol nel 1° tempo |
| reentry_exit_until_min | 0 | 0 = mai chiusura forzata |
| reentry_price_min_over_entry | on | solo se la quota supera il primo ingresso |
| reentry_hold_if_loss | off | vale solo con una chiusura forzata impostata |

**Rischio**
| chiave | default | significato |
|---|---|---|
| max_open_matches | 10 | partite con posizione |
| daily_loss_stop | 50 | stop giornaliero (0 = off) |
| max_liability_per_match | 0 | capitale massimo per partita (0 = off) |
| event_loss_cap_pct | 100 | cap perdita partita |
| settle_confirm_s | 60 | intervallo fra due letture REST del book a mercato chiuso (minimo effettivo 5 s) |
| skip_log_interval_s | 300 | dedup dei log ripetitivi per partita (skip, no fill, linee assenti, riconciliazione) |

Variabili d'ambiente (pattern `os.getenv(X, "").strip() or default`): `MIKE_LOCK_PORT` (47319),
`MIKE_USE_FLUMINE_QUEUE` (0), `MIKE_ATLAS_PATH`, `SAFE_PRE_KO_OU_HOURS` (3, nello scanner).

---

## §7 Esecuzione e fedeltà paper

- Ordini via `safe_strategy/execution.place` (reserve-first su `mike_trades`, `client_ref`
  `mike-t<id>`): **paper** = fill sul feed al prezzo richiesto SOLO se ancora disponibile, size
  cappata alla liquidità al best; **live** = REST FOK con la sessione condivisa
  (`omega_market.place_order_live`).
- In paper e in-play il fill è DIFFERITO di `bet_delay` (dal feed) e rieseguito al prezzo
  allora disponibile: mai più ottimista del live. Una LAY appoggiata si considera abbinata solo
  quando il best back SUPERA il suo prezzo (regola stretta).
- Importi liberi: con `exact_sizes = on` la size esatta passa in paper; in live il sotto-minimo /
  fuori passo va via place-and-trim (`Betfair/stream/trading/submin.py`, come i tool pro).
- Rinviato alla fase F6 (live): riconciliazione `listCurrentOrders/listClearedOrders` come il
  Safe bot; `persistence` PERSIST su `place_order_live`; cancel/replace REST per il sotto-minimo;
  lay appoggiata in live (REST senza FOK) o coda flumine (`MIKE_USE_FLUMINE_QUEUE=1`).

---

## §8 La UI (`/mike`) e come leggerla

- **Barra**: stato bot (INATTIVO / IN CORSA / IN ARRESTO / FERMO / IN ERRORE), chip feed
  (vivo / fermo) e battito del servizio, toggle PAPER/LIVE (LIVE richiede conferma), Parametri, Avvia/Ferma.
- **Banner modalità** e **KPI**: partite seguite (nel feed · con posizione), trade aperti, P&L
  oggi (giornata operativa Europe/Rome), P&L totale, capitale a rischio con stop giornaliero, ultimo ciclo.
- **Schede**: ⚽ Partite (card attive) · 📋 Trade (ogni gamba: ora, partita, ruolo, lato, quota, size,
  stato, P&L) · 🧾 Attività (log: ARMATA, FASE, ORDINE, ANNULLO, NO FILL, CICLO PRE, COPERTURA,
  REGOLATA, ERRORE…) · ✅ **Regolate** = partite FINITE E PAGATE: mercato chiuso, esito dichiarato
  da Betfair, P&L definitivo · 📅 Storico (calendario giornaliero per ruolo).
- **Card di una partita** (bordo per fase: teal pre-match, viola live, verde flat):
  punteggio grande con espulsioni, minuto / KO fra X, badge di fase; quadro P(4) modello, P(4)
  mercato, hazard 3', pressione (🔥 se calda) o λ; quote live U3.5 e O4.5 back/lay (tooltip con
  market_id e selection_id); tabella **Posizioni**: lato netto (BACK sky / LAY rose), euro
  abbinati, prezzo medio d'ingresso, quota ora, **Δ tick** (verde a favore, rosso contro), **se chiudo
  ora** in euro netti; ordini sul book con distanza dal best; strip "a fine gara per gol totali"
  con la cella **4 in rosso** e i gol attuali evidenziati; cash-out ora con % e barra verso la
  soglia, riga "intelligente" e riga "uscita a modello"; bottoni Cash out / Salta / Riprendi
  (spenti con feed stantio).
- Etichette di fase: IN ATTESA, INGRESSO…, UNDER APERTO (PRE), GREEN-UP…, HOLD → LIVE,
  ULTIMO INGRESSO (PERSIST), LIVE · NESSUNA POSIZIONE, LIVE · SCOPERTO, COPERTURA…,
  LIVE · COPERTO, CHIUSURA…, FLAT, RE-INGRESSO…, REGOLAMENTO, REGOLATA, ERRORE, SALTATA.

---

## §9 Operatività

- Migrazioni (manuali, in ordine): `migrations/mike_bot.sql`, `migrations/mike_history.sql`,
  `migrations/mike_bot_v2.sql`, `migrations/mike_history_v2.sql` (queste due DOPO
  `omega_daily_v2.sql` e `omega_models_v4.sql`: `mike_history_v2.sql` elimina gli overload
  a 7/3 argomenti delle funzioni condivise dello storico e ammette `mike_trades`).
- Env: `SAFE_PRE_KO_OU_HOURS=3` nel `.env` (lo scanner pubblica le linee pre-match).
- L'exe è l'avviatore del `main.js` vivo: dopo una modifica al codice si RIAVVIA l'app (mai
  ricompilare). Il servizio `mike-service` parte con l'app sotto watchdog; il bot lavora solo
  dopo "Avvia" in `/mike` (stato `running` in `mike_control`).
- Test: `python -m pytest Betfair/mike -q` (108) · `npx vitest run src/lib/mike.test.ts src/pages/Mike.test.tsx` (14)
  · `npm run build`.
- Diagnosi rapida: `select * from mike_control` (stats: by_state, daily_stop, scanner_age_s),
  `mike_events` (state, positions, live, ctx.last_reason), `mike_activity`.

---

## §10 Limiti noti e cose da fare

1. **Ponte evento→fixture** sulle leghe minori: dossier vuoto (`source: none`) → niente λ, niente
   hazard/P(4) di modello, niente EV per cash-out e uscite. Effetto: copertura immediata e
   regola fissa. Da sistemare per primo dopo le prime partite paper.
2. Live (F6): riconciliazione ordini, PERSIST reale, sotto-minimo REST, lay appoggiata in live.
3. Re-ingresso oltre la linea 4.5 (2+ gol) richiede una linea extra nel feed: non implementato
   (il parametro `stream_extra_lines` era inerte ed è stato rimosso dalla whitelist).
4. Manca una tabella di frequenza "4 gol esatti" per lega; oggi la P(4) viene da griglia, empirico HT→FT e mercato.
5. Gate F5: certificazione paper (n ≥ 40) + backtest REC; il verdetto va scritto in §0.

---

## §11 Cosa Mike NON fa

- Non entra mai in-play "da zero": l'unico ingresso live è il re-ingresso dopo un profitto e dopo un gol.
- Non apre posizioni a bot fermo o con stop giornaliero attivo (chiusure e regolamento restano attivi).
- Non chiude in perdita fuori dalle regole HT/2T (a modello o fisse) e dal cap di perdita evento.
- Non opera linee non presenti nel feed.
- Non fa chiamate Betfair per i dati e non ha un login proprio.
- Non passa mai a LIVE da solo.

---

## §12 Audit 11/09/2026 (sera) — correzioni applicate al backend

Riferimento: `Betfair/AUDIT_2026-09-11_omega_safe_mike.md`, sezione 1 (MIKE) + sezione 4 (storico).

| Item | Regola che ora vale |
|---|---|
| C1 | Le linee di una partita SEGUITA restano nel feed: lo scanner ha `select_opp_candidates(followed=…)` (partite Mike esenti dal tetto dei 20 eventi) e `is_opp_market_live(..., mike=True)`. Se una linea manca comunque, Mike NON inventa prezzi: attività `feed_line_missing` (critica) e `live.lines_missing` sulla card |
| C2 | Dopo il 4° gol la partita NON si congela: una selezione con esito già deciso vale 0/1 SENZA prezzo (`engine.selection_decided`), `complete=true` se tutte le selezioni VIVE hanno prezzo, il cash out agisce sulle sole gambe vive e una chiusura in attesa su una selezione decisa viene annullata |
| C3 | Esito ordine IGNOTO → gamba `pending_reconcile`: mai `cancelled`/`error` per TTL, conta nella liability al peggior caso, blocca i nuovi ingressi, attività `reconcile_pending` / `reconcile_fix` |
| H1 | Cash out manuale: PRIMA i cancel (attesa conferma), POI la chiusura della posizione netta; il contesto NON viene azzerato; pre-KO il ciclo è chiuso E `no_reentry=true` (solo "Riprendi" riabilita il rientro); con feed stantio la richiesta viene RIFIUTATA |
| H2 | Riconciliazione `mike_trades` ↔ `positions` a OGNI ciclo: gamba senza riga → riga ricostruita, riga senza gamba → `meta.orphan` (in live mai chiusa in silenzio) |
| H3 | In LIVE la lay appoggiata NON esiste (finché non è cablata): `pre_exit_mode` forzato a `taker`, nessun fill simulato con o senza coda flumine |
| H4 | `pnl` di ogni riga NETTO commissione (somma righe = `settled_pnl`); ogni chiusura porta `closes_trade_id` + `meta.exit_kind` ∈ {greenup, profit, loss, time, forced, manual, other} + `meta.exit_reason`; lo storico conta i CICLI |
| H5 | Log `state` solo al cambio di stato, battito su `mike_control` al massimo ogni 10 s, lettura incrementale di `mike_trades` (`live_trades`) e aggregati via RPC SQL |
| M1 | Ogni richiesta chiusa con `status` ∈ {done, rejected, error} e `result` = {code, message in italiano} |
| M2 | `fail_stale_processing` a ogni ciclo |
| M3 | Rimossi (inerti): `max_matches`, `catalogue_refresh_s`, `stream_extra_lines`, `min_total_matched`; cablati: `settle_confirm_s`, `skip_log_interval_s`, `cover_max_overshoot_pct`. `catalogue.py` (codice morto) rimosso |
| M4 | "Capitale a rischio" = liability delle posizioni NETTE (`engine.event_liability`), non la somma delle gambe |
| M5 | "Se chiudo ora" SEMPRE netto commissione lato servizio: `live.cashout.{net, gross, base, per, per_gross, decided, complete, commission, pct, target_pct}` |
| M6 | Giornata operativa = giorno di PIAZZAMENTO (Europe/Rome) per KPI, regolate e storico |
| M7 | In paper nessun fill (anche resting) con feed stantio: motivo `feed_stantio` |
| M8 | All'avvio, `entry_hours_before_ko` > ramo pre-KO dello scanner (o ramo spento) → attività `config_warn` |
| M9 | Mercato VOID/abbandonato → gambe `void`, partita `SETTLED` con `settled_pnl = 0` e motivo |
| M10/R2 | `migrations/mike_history_v2.sql`: una sola firma delle funzioni condivise (8/4 argomenti) con `mike_trades` ammessa; `get_mike_daily`/`get_mike_day_trades` passano tutti gli argomenti con `p_day_by='placed'` |
| L1..L5 | `customerStrategyRef` = `mike` sugli ordini live; stop giornaliero per giorno di Roma e comprensivo del P&L BLOCCATO; partite già in gioco non armate; tutti i `kind` di attività dichiarati (test) |
