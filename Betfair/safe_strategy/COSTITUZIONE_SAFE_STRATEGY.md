# ⟶ COSTITUZIONE DI «SAFE STRATEGY» ⟵

Documento vivo. Descrive cosa è Safe Strategy oggi (**stato al 12/09/2026, notte** —
codice pushato su master con il commit **`9d09c81`**, base `1b6b151`), come è costruita,
cosa è stato verificato dal vivo, cosa NON funziona ancora e la strada per il livello
successivo. Nessuna parte del lavoro del 10/09 e dell'11/09 è omessa: quello che è stato
superato porta la nota «superato il …», non viene cancellato.

**Stato operativo in una riga** (aggiornato il **13/09**): audit
`Betfair/AUDIT_2026-09-11_omega_safe_mike.md` applicato per intero su backend e UI,
review indipendenti chiuse; **`safe_strategy_bot_v2.sql` È APPLICATA** (verificato sul DB
il 13/09: `get_safe_aggregates` e `get_safe_activity` rispondono — la vecchia nota
"ANCORA DA APPLICARE" era superata); **🔴 DA APPLICARE:
`migrations/safe_strategy_paper_live_2026-09-13.sql`**; servizi da riavviare, **LIVE
BLOCCATO**. La certificazione del 13/09 — causa per cui BASE e PUNTA non scattavano mai,
esecuzione al centesimo, separazione netta paper/live — è in
`Betfair/safe_strategy/CERTIFICAZIONE_2026-09-13.md`. Dettaglio in §12.

Regola di naming: nel codice si chiama sempre "Safe Strategy". Il manuale operativo
delle 4 strategie (ingressi, uscite, minutaggi) è il file
`C:\Users\Admin\Desktop\PYTHON DATABASE\STRATEGY S.txt` (che contiene l'URL dell'artefatto).

---

## 0. Cos'è Safe Strategy (in tre frasi)

1. Un **radar** che, sul feed unico dello scanner (`safe_strategy_scan`), valuta in tempo
   reale le 4 strategie del manuale (Base, Risultato Esatto, Tennis, Punta) su tutte le
   partite in-play di calcio e tennis.
2. Dal 10/09 un **bot** (`bot_service.py`) che le esegue da solo, paper o live, con
   resoconto in tempo reale, cash out professionale, uscite automatiche dal manuale e
   uscite "a modello" (mai chiudere in perdita quando il margine è ampio).
3. Un **motore di opportunità** che segnala mercati "sostanzialmente improbabili" con
   piccolo profitto: modello tempo×punteggio calibrato, quote anomale, combinazioni a
   rischio zero, tennis.
4. Dall'11/09 una **dashboard con un contratto scritto** (§12.3): tutto quello che il
   servizio decide — perché entra, perché NON entra, cosa tiene, cosa ritenta, cosa ha
   fallito — è leggibile a schermo, in italiano, con la **giornata operativa = giorno di
   PIAZZAMENTO** come unico criterio di attribuzione.

---

## 1. Architettura (aggiornata all'11/09 sera)

```
scanner (service.py/scanner.py/stream.py)  →  safe_strategy_scan (feed unico, write-on-change)
                                              ├─ UI radar (lib/safeStrategy.ts, motore TS)
                                              ├─ Omega (omega_service)
                                              ├─ runner calcio/tennis, board (scan_feed.py)
                                              └─ BOT SAFE (bot_service.py)  ← 10/09
bot ─ engine.py (port Python del motore TS, 103 test di parità)
    ─ execution.py (place / close_trade / settle_group condiviso con Omega)
    ─ exits.py (uscite manuale + decisione a modello)
    ─ risk.py (cap giornalieri/evento/correlati, stop perdita)
    ─ opportunity.py (+ calibration.py, pressure.py, anomaly.py, combos.py, tennis_opportunity.py)
    ─ bot_db.py → tabelle: safe_strategy_control / trades / activity / requests / opportunities
UI  ─ pages/SafeStrategy.tsx (PageShell → BotHeader → ModeBanner → DayBar → KpiRow →
      Calcio|Tennis|Storico, + ActivityFeed del servizio)
    ─ components/trading/* CONDIVISI con Omega e Mike (design system, §12.3)
    ─ lib/safeBot.ts (contratto DB↔UI), lib/format.ts, lib/tradeStatus.ts, lib/dailyHistory.ts
DB  ─ migrations applicate il 10/09: safe_strategy_bot.sql, betfair_live_cashout_v3.sql,
      omega_cashout.sql, daily_history.sql
    ─ applicata l'11/09: safe_strategy_bot_v2.sql (verificato sul DB il 13/09)
    ─ 🔴 DA APPLICARE: safe_strategy_paper_live_2026-09-13.sql — filtro `p_mode` su tutte
      le RPC di lettura, indice unico sulla chiusura in volo, `mode` nella chiave di
      idempotenza, `safe_stop` che riporta la modalità a paper, `safe_set_mode`
exe ─ desktop/main.js: runner `safe-strategy-bot` sotto watchdog, lock 127.0.0.1:47318
```

Regola dei processi: **nessuna chiamata Betfair duplicata**. Il bot legge SOLO il feed
(una SELECT/ciclo, letta per PRIMA in `bot_service.run_once` perché la usa anche il
settlement), piazza tramite la coda flumine del runner quando l'evento è in follow
STREAMING, altrimenti paper fill dal feed / REST FOK in live (stesso layer di Omega).

### 1.1 Feed: blocchi dei mercati a gol (additivi, nessuna chiave rinominata)
- `ou` (Over/Under 0.5–7.5), `btts`, `ht_result` (<45'), `odds_ts_ms`, `mo` selection_id
  già nelle coppie `odds.*`. Ogni blocco porta il **suo** `status`, `market_id`, `line`,
  `bet_delay`, `selections[]` con best back/lay e size (`scanner.build_market_block`,
  tipo TS `ScanMarketBlock` in `lib/safeStrategyScan.ts`). Calcolo inline delle
  opportunità nello scanner: opt-in `SAFE_SCAN_OPPORTUNITIES=1` (default off: lo fa il bot).

### 1.2 Cablaggio C1/C2 dello scanner per le partite di Mike (11/09)
Una posizione di **Mike** su Over 3.5/4.5 rischiava di restare senza quote nel feed
(nessuna copertura, nessun cash out, nessuna uscita: il cash out manuale rispondeva
`feed_assente`). Il feed unico è stato esteso così — nessuna risorsa nuova, solo priorità:

- `db.list_mike_followed_event_ids()` + `db._mike_has_exposure()`: le partite Mike **con
  esposizione reale** (gamba `pending`/`pending_reconcile`/`open` non archiviata, oppure
  `matched > 0`); WATCH/IDLE_LIVE senza gambe **non** sono esenti (review H4: non hanno
  niente da proteggere e peserebbero sul pool stream per niente).
- `service.Scanner._mike_followed()`: cache **10 s**, nessuna lettura nel percorso caldo,
  in `dry` nessuna query; su errore resta valida l'ultima lista buona.
- `scanner.select_opp_candidates()`: le partite seguite sono **ESENTI dal tetto di 20
  eventi** (`scanner.OPP_MAX_EVENTS`), con tetto duro proprio `MIKE_MAX_FOLLOWED = 10`
  (= `max_open_matches` del bot Mike); il tetto normale continua a valere per tutte le altre.
- `service.Scanner._opp_ranked_market_ids()`: l'evento che entra **solo** perché seguito
  porta nel pool **le due sole linee** `scanner.MIKE_OU_MARKET_TYPES` (3.5 e 4.5) e nulla
  più (H4); `scanner.opp_rank_key(..., mike=True)` dà loro **tier 1.5** — dopo i mercati
  core, prima di ogni altro mercato opportunità, così il troncamento dello shard non le
  taglia mai (H5).
- `scanner.is_opp_market_live(..., mike=True)`: le due linee restano vive **anche se già
  decise** (C2: dopo il 4° gol l'Over 4.5 è l'unica gamba ancora chiudibile).
- `scanner.ou_block_decided()` + `service.Scanner._prune_opp_blocks()`: le linee tenute
  vive solo per Mike vengono **marcate** `decided: true` / `for_mike: true` nel payload.
  Il motore opportunità le **ignora** (`opportunity.OpportunityModel` + `_is_live_ou_line`,
  H6: con `max_prob_lay = 0` il bot ci si sarebbe buttato in automatico) e la UI non le
  usa come prezzo di uscita (`safeBot.safeTradeBook` → `safeStrategyScan.isUsableBlock`).
- `service.Scanner.opp_candidates()`: una partita Mike seguita è candidata **anche nei
  primi minuti** (`is_opp_candidate` chiede `minute >= 1` e il ramo pre-KO si spegne al
  calcio d'inizio: per qualche minuto la posizione restava senza nessuna linea, H7).

### 1.3 Budget delle chiamate REST (H-19)
La fonte dei prezzi è il feed; il REST è solo un ripiego, **contabilizzato**:
`bot_service.rest_gate()` — minimo **10 s** fra due letture dello stesso mercato
(`REST_MIN_INTERVAL_S`) e tetto duro di **8 chiamate per ciclo** (`REST_BUDGET_PER_CYCLE`),
fail-closed (budget esaurito → si aspetta il feed). Il **settlement** ci passa attraverso:
`bot_service._settlement_needs_rest()` non chiama Betfair quando il feed dice che il
mercato della posizione è ancora `OPEN` e la partita è viva (un mercato aperto non si
regola). `bot_service.prices_for(..., rest_now_ts=…)` applica il gate nei cicli; le azioni
**manuali** dell'utente lo scavalcano (`allow_rest=True` senza `rest_now_ts`: è un clic,
non un loop). Prima c'era una `listMarketBook` per posizione aperta ogni 2 s.

---

## 2. Le 4 strategie — ingressi (motore `engine.py`, parità col TS)

| # | id | mercato | minuto (SOGLIA) | punteggio | lato | quota ingresso | stake |
|---|----|---------|-----------------|-----------|------|----------------|-------|
| 1 | base | MATCH_ODDS | ≥55' | fav avanti 1-0/2-1/2-0, fav pre 1.40–1.80, dog pre 4–8, fav live 1.20–1.34 | LAY sfavorita | lay dog | stake.laySize (2) |
| 2 | esatto | CORRECT_SCORE "Altro risultato Casa/Ospite" | ≥48' | 0-0/1-0/1-1/2-1, bancata con ≤1 gol | LAY | 30–70 | stake.laySize |
| 3 | punta | MATCH_ODDS | ≥66' | 2-0/3-1/3-0, leader = favorita, ≥3' dal gol | BACK favorita | 1.03–1.10 | stake.backSize |
| 4 | tennis | MATCH_ODDS | — | 1 set + ≥2 game di vantaggio, singolare, no competizioni escluse | BACK leader | 1.01–1.10 | stake.backSize |

Gate d'ingresso del bot: liquidità abbinabile ≥ stake × fattore, **spread
lay/back ≤ 1.6** (il trade 12 del 10/09, back 20 / lay 60, era un'entrata sbagliata),
rischio (`risk.py`), dedup per `signal_key` (= event:variant:situazione, indice univoco
parziale), anti-blip `scoreConfirmSec`, e da 11/09:
- **size minima reale Betfair 2 €** (`execution._min_size_live`, override
  `SAFE_MIN_SIZE_LIVE`): in live un ordine sotto minimo è un rifiuto certo, quindi si
  dichiara l'errore parlante `size_sotto_minimo_betfair:…` invece di buttare la chiamata.
  Vale **solo sulle APERTURE**: Betfair accetta gli ordini sotto minimo che RIDUCONO una
  posizione, e rifiutarli lasciava un residuo da 1,40 € eternamente `retrying`
  (review C2). `params.min_stake = 2.0` è ora dichiarato nei default del bot
  (`bot_service.DEFAULT_PARAMS`): prima la Safe Strategy ereditava in silenzio lo
  `min_stake` 0,50 € di Omega attraverso il codice di coda condiviso.
- **budget dei ritentativi di piazzamento** (H-21): `bot_service.place_allowed()` /
  `_place_fail()` / `seed_place_attempts()`. Un FOK rifiutato dall'exchange non viene più
  ripiazzato ogni 2 s: `place_max_attempts` (default 3) tentativi con backoff
  `exits.RETRY_BACKOFF_S` = 5/15/60/300 s, marker `meta.place`
  (`attempts`, `last_error`, `next_retry_at`, `final`), attività `place_retry` →
  `place_exhausted`; il budget **sopravvive al riavvio** perché viene riletto dalle righe
  `error` (`bot_db.place_attempts()`, ogni 5 minuti). Vale anche per le opportunità
  (`_auto_trade_opps`) e per le combinazioni (`_auto_trade_combos`: una gamba a budget
  esaurito ferma la combo intera).
- **`variants` non può essere vuoto** (H-14): `bot_service.normalize_variants()` —
  `[]`, un non-elenco o soli valori ignoti tornano ai default nell'ordine del manuale
  (`base, esatto, punta, tennis`). Prima una lista vuota sul DB spegneva il bot in
  silenzio mentre la UI mostrava 4 strategie attive.

**SUPERATA IL 13/09** — la nota diceva: «Base e Punta NON scattano per le partite già
in corso all'avvio dello scanner, perché manca la quota pre-match congelata (`pre_ko`)».
Era vera, ed era **la ragione per cui quelle due strategie erano di fatto spente**: nello
storico di 240 trade avevano prodotto **un trade ciascuna**, contro 152 di `esatto` (che
è l'unica a non usare `pre_ko`). Il riferimento viveva solo nella RAM dello scanner e si
perdeva a ogni riavvio; peggio, al primo `publish` il codice sovrascriveva con `None` la
copia che aveva già sul DB.

Dal 13/09 `pre_ko` viene **riletto dal DB** all'avvio, per le sole partite in corso che
non ce l'hanno, una volta per evento (`db.load_scan_pre_ko` +
`Scanner.hydrate_pre_ko`, chiamata PRIMA del publish). Il valore recuperato è marcato
`rehydrated: true` e non sovrascrive mai un riferimento catturato dal vivo. Il motore non
entra comunque "a occhi chiusi": se il riferimento non c'è nemmeno sul DB (partita
iniziata ad app spenta) lo stato resta n/d — ma adesso **lo si legge a schermo**, con lo
scarto `pre_ko_assente` nell'attività, invece di non vedere niente.
Dettaglio in `CERTIFICAZIONE_2026-09-13.md` §0.

---

## 3. Le 4 strategie — USCITE (`exits.py` + `bot_service.process_exits`)

*(§3 riscritta l'11/09 sera: la vecchia intestazione «DA RIVEDERE DOMANI» e la lista
«cose da correggere domani» sono superate dai punti 3.1–3.4. I quattro spunti di
riscrittura strategica restano aperti e sono in §9.1.)*

Regole del manuale implementate:
- **BASE**: profit se la favorita segna ancora; tempo 80'; LOSS immediata (dopo 30 s di
  stabilizzazione) se la sfavorita pareggia; rosso alla favorita → esci.
- **ESATTO**: tempo 72' (uscita "in profitto" del manuale); LOSS immediata se la squadra
  bancata segna.
- **PUNTA**: profit al gol successivo; tempo 83'; LOSS immediata a qualsiasi gol subito.
- **TENNIS**: profit al game successivo vinto (`tennis_take_profit_next_game`, default on);
  loss opzionale al game perso (default off); OBBLIGATORIA con 2 game persi di fila e set
  in parità; cambio set azzera il conteggio.

### 3.1 Decisione a MODELLO, al NETTO della commissione
`exits.decide_time_exit(p_lose, locked, hold_profit, stake)` per le uscite a
tempo/profitto (decisione utente 10/09 pom.): locked ≥ 0 → esci; p_lose ≤ `hold_max_risk`
(2%) → tieni fino al settlement; p_lose ≥ `risk_cap` (10%) → esci; altrimenti confronto
EV(hold) vs bloccato (`ev_margin` 0,10 €). Le uscite LOSS del manuale restano immediate e
incondizionate. p_lose: calcio dalla griglia residua (`OpportunityModel.book`), tennis da
`tennis_winprob.p_match` con il formato dedotto come nel modello
(`bot_service._best_of` → `tennis_opportunity.detect_best_of`, L-12: prima un bo5 all'1-0
veniva valutato come bo3), fallback quota di mercato.

**M-27 (11/09): il confronto avviene su importi NETTI.** `exits.net_of_commission()`
applica l'aliquota solo agli utili (una perdita non paga commissione) e
`bot_service._decide_model_exit` / `_model_gate` la usano su `locked` e su `max_profit` /
`hold_profit`, con l'aliquota della POSIZIONE (`bot_service._commission_of`: colonna
`commission` del trade, poi il parametro corrente). Un profitto lordo di 1,00 € in mano
vale 0,95 € e **cambia il verdetto**.

I motivi di uscita e di hold finiscono a schermo, quindi sono scritti in **formato
italiano**: `exits._eur()` → `+1,20 €` (prima `+1.20 EUR`).

### 3.2 Nessuno stato di uscita è TERMINALE (C-04 / H-05 / H-17)
Prima: `niente_da_chiudere` marcava l'uscita come "inviata" e la liability restava piena
fino al settlement; dopo 3 tentativi (≈6 s in live) `exit_failed` era definitivo; il
residuo esaurito (`residual_exhausted`) non veniva più coperto. Oggi:

- `exits.RETRY_BACKOFF_S = (5, 15, 60, 300)` s + `exits.retry_backoff_s(attempts)`:
  oltre la scala si **ripete l'ultimo gradino, per sempre**, finché il mercato è aperto.
  Una liability viva va coperta, costi quel che costi.
- `bot_service.EXIT_STATES = ('retrying', 'failed', 'waiting_price', 'done')` scritti in
  `meta.exit` da `bot_service._write_exit_state()`: `state`, `kind`, `reason`, `attempts`,
  `residual_attempts`, `wait_attempts`, `last_error`, `next_retry_at`. **`failed` non
  significa "smetto"**: significa "budget veloce superato, continuo col backoff lungo e lo
  dico alla UI".
- `bot_service._exit_candidates()` non esclude più le uscite fallite; il **backoff frena
  solo l'INVIO**, non il tracciamento del feed (review H4: gol, rossi, game vanno seguiti
  a ogni ciclo o `last_goal_ts`/`consecutive_lost` si perdono).
- `bot_service.URGENT_EXIT_KINDS = ('loss', 'red_card', 'mandatory')` +
  `_exit_due()`: una regola **urgente nuova** scavalca il backoff di un tentativo
  precedente — aspettare 5 minuti per chiudere una posizione che sta perdendo non è un
  ritentativo, è un danno.
- Attività dedicate: `exit_retry`, `exit_wait`, `exit_failed` (con `critical: true` e
  `next_retry_at`).

### 3.3 Freschezza del feed: tetto DURO (M-24) e stato dei mercati (M-23)
- `exits.feed_is_fresh(row, now, scanner_ts, max_age_s=20, hard_max_age_s=120)`:
  `FEED_FRESH_S = 20` s oppure heartbeat scanner vivo (write-on-change), **ma oltre
  `FEED_HARD_MAX_S = 120` s la riga non vale MAI**, nemmeno con lo scanner vivo — uno
  scanner che non riscrive quella partita da due minuti non sta osservando quel mercato.
  La UI ha la stessa soglia (`safeBot.FEED_HARD_MAX_MS`, difesa da un test).
- `exits.market_open(trade, payload)` legge il `status` del **mercato della posizione**:
  `mo_status` solo per il Match Odds, altrimenti il blocco riconosciuto per `market_id`
  (una linea O/U non è l'altra) o per tipo via `_STATUS_BLOCK_BY_TYPE`
  (`cs`, `ht`, `btts`, `ht_result`) e la lista `ou`. Prima Over/Under, Gol/NoGol e 1X2
  primo tempo leggevano lo stato di un ALTRO mercato.

### 3.4 `hold_code`: si scrive una volta, non a ogni tick (M-28)
`exits.hold_code(why)` sostituisce ogni numero con `#`: è la **firma stabile** del motivo.
`bot_service._model_gate` / `_write_model_hold` confrontano il *codice*, non il testo (che
contiene P(perdita) e EV, diversi a ogni ciclo), e riscrivono `meta.exit_hold` solo al
cambio di codice o dopo `_HOLD_REWRITE_S`. `meta.exit_hold` porta ora
`{reason, code, kind, exit_reason, p_lose, source, locked, ev_hold, ts}`.

### 3.5 COMBO: tutto-o-niente anche dopo il fill (H-20 / H6)
Il lock di una combinazione vale solo se **tutte** le gambe vivono:
- `bot_service.combo_siblings()` (dalle righe già lette del ciclo, M1) +
  `_combo_leg_prices()`: senza i prezzi di tutte le gambe vive **si aspetta**
  (`exit_wait: combo_prezzi_incompleti`); se si esce, `_close_combo_siblings()` chiude le
  altre con `exit_kind='forced'`.
- In apertura, `_auto_trade_combos`: gamba fillata + gamba in errore → marker
  `meta.combo_incomplete` su ogni gamba viva (`_mark_combo_incomplete`), attività
  `combo_incomplete` (`critical: true`, con `filled_ids`/`pending_ids`) e svolgimento
  immediato delle gambe già abbinate (`_unwind_combo`).
- `bot_service.unwind_incomplete_combos()` gira a **ogni ciclo, anche a bot fermo**: la
  gamba accodata su flumine diventa `open` uno o più cicli dopo, e senza questo passaggio
  la posizione nuda restava aperta (review H6).

### 3.6 Residuo, cecità del feed, mercato sparito
- Residuo dopo chiusura parziale (libro sottile): `residual_retry_s` 20 s,
  `residual_max_attempts` 15 → poi **non si smette**: `state='failed'` +
  backoff lungo (H-17), una sola attività `exit_failed: exit_residual_exhausted`.
- Posizione viva senza riga nel feed = **cecità** (H-18):
  `bot_service.check_feed_blind()` gira su TUTTE le posizioni vive (anche manuali e di
  modello) e scrive `meta.blind_since` una volta sola + attività `feed_blind`
  (`critical`, poi ogni 60 s) e `feed_back` al ritorno. Le posizioni **pre-KO** non sono
  un allarme (`is_blind_relevant`, review M2: lo scanner segue gli in-play).
  `stats.feed_blind` è il **contatore** delle posizioni cieche del ciclo.
- Mercato sparito al settlement (M-25): `bot_service._market_missing()` — né silenzio né
  flood: si marca `meta.market_missing_since` e si logga `market_missing` solo dopo
  `MARKET_MISSING_MIN_FAILS = 3` letture consecutive fallite (review M11: una singola
  eccezione di rete non è un mercato sparito), poi ogni `MARKET_MISSING_LOG_EVERY_S = 300` s;
  `_market_seen()` azzera al primo esito buono.

Trade `model` (modello/anomalie/combo/tennis): uscita se un evento avverso porta p_lose
sopra 10%, tennis 2 game/set persi, take-profit all'80% del massimo, cash out quasi gratis.

**Verificato dal vivo (paper, 10/09)**: trade 11 lay 60 al 72' → cash out avrebbe bloccato
−9,43 → tenuto ("P(perdita)=0,4%") → 20 s dopo chiuso a +0,44. Trade 9/14: uscite a tempo
+1,40 / +0,88. Tennis: take-profit al game successivo eseguito.

---

## 4. Cash out professionale (Betfair/stream + execution.py)

- `compute_greenup(amount=)`: importo QUALSIASI anche decimale, cappato al green pieno.
- `plan_equalize`: profitto uguale su TUTTE le selezioni (side-aware, verifica di
  convergenza, minimizzazione del residuo di arrotondamento).
- Sotto-minimo Betfair (mecc. ufficiale: piazza min @1000/1.01 → cancel sizeReduction →
  replace quota) SOLO sulle gambe di chiusura, via macchina a stati `submin` collaudata;
  `allow_sub_minimum` rifiutato sulle aperture (RPC v3 + worker allineati).
- Follow-through per mercato sulle gambe equal non abbinate.
- `execution.close_trade`: gamba di chiusura con `closes_trade_id`, chiusure parziali
  ripetibili sul residuo, `hedged` solo a residuo < 0,01, `settle_group` netta tutte le
  gambe con commissione sul netto di mercato; settlement resumabile e orfani gestiti.
  Da 11/09 accetta `exit_kind` / `exit_reason` (scritti sulla gamba di chiusura) e
  restituisce anche `planned_lock`, `worst_case`, `hedge_fraction`,
  `remaining_liability`; `locked_pnl` è valorizzato **solo a copertura completa** (L-11:
  su un parziale il valore pianificato non è bloccato e va in `planned_lock`). La gamba di
  chiusura **eredita l'aliquota del trade** e mai `NULL` (L-02).
- UI `CashOutButton`: P&L bloccato live, 25/50/75/100 %, importo decimale, sui parziali
  mostra il CASO PEGGIORE, mode del TRADE (non della pagina), doppia conferma LIVE,
  anti doppio invio, disabilitato con feed stantio o mercato sospeso/chiuso.

### 4.1 Cash out su TUTTI i mercati del feed (R1, 11/09)
I trade manuali sui mercati Over/Under (piazzati dalle Opportunità) mostravano "n/d" in
tabella pur avendo il mercato nel feed con quote di 2,4 s: la UI prezzava solo Match Odds,
Correct Score e Half Time Score. `safeBot.safeTradeBook()` risolve ora **qualsiasi**
mercato pubblicato dal feed, in quest'ordine: (1) `market_id` del trade = `market_id` di un
blocco (`safeStrategyScan.scanBlockByMarketId`, vale per CS, HTS, ogni linea O/U, Gol/NoGol,
1X2 primo tempo e ogni blocco futuro); (2) Match Odds; (3) per TIPO di mercato (con la
**linea** O/U giusta da `OVER_UNDER_35` → 3.5); (4) solo se il trade non porta market_id,
la selezione presente in **un solo** blocco (mai indovinare). `TradeBook` porta
`marketId`, `status`, `runnerStatus`, `source` (`match_odds` | `ou` | `btts` | `cs` | `ht`
| `ht_result`) per il tooltip. Le linee marcate `decided` (tenute nel feed solo per una
posizione Mike) sono scartate: l'esito è certo, non è un prezzo di uscita.
`safeBot.marketBlocked()` spegne il bottone su mercato SOSPESO/CHIUSO o selezione rimossa
(M-23), con il motivo scritto sulla riga.

### 4.2 Copertura PARZIALE: visibile e chiudibile (C-02 / M-06 / M-26)
- `execution.apply_hedge_state` scrive `meta.hedge = {fraction, remaining_liability,
  hedged_size, residual_size, complete}` e `meta.hedging = true` **mentre una gamba di
  chiusura è in volo** (L-01: la UI lo leggeva già, nessuno lo scriveva).
- `execution.remaining_liability` / `residual_liability`: il rischio è **0 SOLO a
  copertura completa e confermata**; con la copertura in volo (`worst_case` assente:
  ordine ancora in coda) il rischio è la **liability PIENA** — review C1: prima tornava 0
  e il cap giornaliero si liberava col 100 % del rischio ancora a mercato. Regola
  generale: **IGNOTO = PIENO** (review C1/M10), mai 0 per default.
- La UI: `safeBot.hedgeState()` espone `inFlight`, la tabella mostra
  «rischio ancora pieno: copertura in volo», lo stato `COPERTA xx %` e il badge
  `parziale` sulla gamba; il cash out resta attivo sul **residuo**
  (`residual={remaining, fraction}`), e `safe_request` valida la `fraction` in (0,1]
  come chiusura del residuo. Prima qualunque chiusura non in errore marcava il cash out
  "in volo" e il residuo era inchiudibile dalla UI (in live metà liability scoperta).
- L'anteprima del cash out usa l'esposizione **attuale**
  (`safeBot.tradeExposureNow`: `meta.if_win`/`if_lose` o `expected_*`), non quella piena.

### 4.3 Un solo evento di regolazione per POSIZIONE (M-04)
`execution.settle_position` calcola il P&L **della posizione** (apertura + chiusure),
scrive `meta.position_id` / `position_pnl` / `position_result`
(`execution.position_result` → vocabolario completo `won | lost | flat | void`) su OGNI
gamba (`settle_row(..., position=…)`, con merge sul meta della riga **corrente** per non
perdere `hedge`/`exit_*` — review M12) ed emette **una sola** attività
`settle_position`. I `settle` per gamba restano come prova dell'ordine di scrittura
(ripresa sicura), **mai come toast**: l'apertura di un green-up in utile non è più
"PERSO" e non ci sono più due notifiche per la stessa partita.
Chiusure **orfane** (apertura già regolata): `bot_service.settle_open` le raggruppa per
apertura e passa le **sorelle** a `execution.settle_orphan_closing(..., siblings=…)`,
rileggendole dopo ogni orfana regolata (M-33 + review M9): senza, commissione e P&L
sarebbero calcolati su una coppia incompleta.

**Verificato dal vivo (10/09)**: Safe calcio (−0,07 parziale, −0,02 totale), tennis (50%), Omega
(−6,6 parziale, −0,35 totale): pareggio esatto confermato AL SETTLEMENT al centesimo.

Limite noto: in live la chiusura è FOK; se il libro non abbina, il trade resta aperto
(riprova). Il paper riempie istantaneamente al best price: NON simula il bet delay 5 s
(gap di fedeltà demo=live ancora aperto).

---

## 5. Opportunità (opportunity.py e satelliti)

### 5.1 Modello tempo×punteggio
λ pre-partita (catena: fixture Omega → fixture per nomi+kickoff → pre-KO → default
1,35/1,15 con confidenza ×0,6) → tassi residui (`inplay_residual_rates`: curva reale dei
gol per minuto, stato partita, rossi, gialli, pressione) → griglia Dixon-Coles residua a
12 gol → probabilità di 1X2, O/U 0.5–7.5, BTTS, HT 1X2, CS, HTS. Devig, edge, EV netto
commissione, confidenza (edge, headroom, profondità, freschezza, cross-check hazard con
l'atlante), cooldown 90 s post-gol, min 20 € abbinabili.

**Calibrazione (10/09)**: 38 registrazioni con stream, 60.911 campioni, 36 tabelle;
Brier 0,0859→0,0818 (CV 0,0849), ECE 0,0143→0,0090. Il modello grezzo è buono sugli
Under alti, **ottimista sui lay** dal 60' in poi.

**Backtest P&L (10/09, stake 5, delay 5 s, commissione)**: grezzo 243 segnali, 87%
abbinati, **ROI −15%**; calibrato in-sample −0,2%, leave-one-out **−18,6%**. Perdite sui
LAY (mo/lay −66%, ou/lay −26%, ht/lay −107%); ou/back +0,1% (n=87). Conclusione onesta:
**il modello puro non ha edge dimostrato**; per questo i default di produzione sono
`max_prob_lay 0` (lay spenti), `min_prob_back 0,95`, `min_edge 0,03`, auto-trade off.

### 5.2 Quote anomale (anomaly.py) — logica di mercato, senza modello
Scala O/U incoerente (Under 7.5 a 1,10 con Under 6.5 a 1,01 → +8,9%), linee già decise dal
punteggio ancora quotate, MO vs CS incoerenti, HT ancora aperto dopo il 45', BTTS deciso.
Esecuzione "cecchino": valutate a ogni ciclo sulle righe con quote cambiate, FOK, dedup 120 s.
Sono i segnali con edge reale per costruzione; ma vivono secondi.

### 5.3 Combinazioni (combos.py) — rischio zero per costruzione
Dutching quando l'overround < 100% (riusa `trading/dutching.py`), under/over stack,
copertura CS: payoff enumerato su tutti i finali, commissione per mercato, lock ≥ 0 sul
caso peggiore, size per gamba verificata. Tutte le gambe o nessuna.

### 5.4 Tennis (tennis_opportunity.py)
Markov a game (`tennis_winprob.p_match`) + tenuta del servizio per giocatore + rischio
ritiro (2%, +1% best-of-5) + momentum (−50% se il leader ha perso gli ultimi 2 game) +
gate tie-break / set decisivo / doppi / competizioni escluse / quote stantie. Back del
leader ≥ 90% con edge ≥ 1,5%; lay dello sfavorito ≤ 10% a quota ≤ 8.

### 5.5 Rischio (risk.py)
Cap liability giornaliero 500 €, per evento 150 € (correlazione 0,7 tra mercati dello
stesso evento), max 3 trade/evento, stop a −50 € giornalieri, stake modello 5 €, cap
modello 150 €. NOTA (10/09): il cap giornaliero è stato raggiunto (572 €) con 4 lay Esatto
a 60 (liability 118 ciascuno): i cap vanno tarati sul tipo di strategia.

**11/09 — il SEGNO dello stop si interpreta, non si azzera** (review H2):
`risk.merge_risk_params` fa `daily_loss_stop = -abs(valore)`. Chi scrive «50» intende
«fermati a −50 €»; il vecchio `min(0.0, …)` lo clampava a **0 = stop perdite SPENTO**
senza dirlo, mentre la scheda mostrava 50. La UI accetta entrambi i segni e mostra sempre
quello vero (`safeBot.normalizeLossStop`).

**La base dei cap è il capitale IMPEGNATO, non il rischio residuo** (review H1):
`bot_db._committed_liability` usa **sempre** la `liability` d'apertura per
`day_liability` / `day_liability_model`, anche dopo una copertura — usare il residuo
liberava il cap giornaliero a ogni green-up e si poteva girare capitale all'infinito.
`open_liability` è invece il rischio **ancora vivo** (residuo dopo la copertura, M-26):
due numeri diversi, e non vanno mai confusi (§12.3).

---

## 6. Dashboard (`pages/SafeStrategy.tsx`)

*(§6 riscritta l'11/09 sera. Il giudizio del 10/09 sera — «illeggibile», con i 5 criteri
di rifacimento — è stato **superato l'11/09**: la pagina è stata ricostruita sui
componenti condivisi del design system e i 5 criteri sono soddisfatti dai punti
6.1–6.6. Il vincolo di verifica resta: il browser dell'agente non raggiunge
127.0.0.1:47330, quindi la prova è test + RPC dal vivo, non uno screenshot.)*

### 6.1 Struttura UNICA delle tre sezioni di trading
Normativa in `frontend/src/components/trading/DESIGN_SYSTEM.md` (documento **normativo**
per `/omega`, `/safe-strategy`, `/mike`). Safe Strategy la rispetta:

```
PageShell (titolo, container)
 └─ BotHeader  (sticky; misura la propria altezza → navH)
     ├─ nome+simbolo bot (accento Safe = text-secondary/oro) + badge stato (BOT …)
     ├─ ServiceHealthChip  (feed + BATTITO del servizio + STREAM/REST + DRY + errore)
     ├─ ModeToggle PAPER|LIVE  (aria-pressed)
     ├─ BotParamsSheet        (o ParamsSheet del radar se il bot non esiste)
     └─ Avvia / Ferma
 ├─ ModeBanner  (LIVE rosso / PAPER verde, errore del control)
 ├─ DayBar      «Giornata operativa»: realizzato, totale, partite, operazioni, V/P,
 │               vive, liability aperta, P&L bloccato, nota sull'attribuzione
 ├─ KpiRow      Segnali attivi · Trade aperti · P&L oggi · P&L totale · Liability
 │               aperta · P&L bloccato · Partite monitorate · RiskPanel
 ├─ Tabs (TabsList sticky a `top: navH`)
 │    ⚽ Calcio  → Segnali | Opportunità modello | Monitor | Trade
 │    🎾 Tennis  → Segnali | Opportunità tennis | Monitor | Trade
 │    📅 Storico → filtro sport + TradingHistory (calendario, statistiche, giornata)
 └─ SectionCard «Attività» → ActivityFeed del servizio
```

Glossario e formati obbligatori: `lib/format.ts` (`fmtMoney` → `12,50 €`, `fmtOdds` →
`2,04`, `fmtPct` → `12,5 %`, `fmtTime` **sempre Europe/Rome**, meno `−` U+2212) e
`lib/tradeStatus.ts` (`statusMeta`, `botStatusMeta`, `sideMeta` BACK=sky / LAY=rose,
glossario `T`: «Liability aperta», «P&L bloccato», «Cash out», «CHIUSO», «giornata
operativa»). `fmtEurIt`/`fmtOddsIt` in `lib/safeBot.ts` restano solo come alias storici.
Niente stati o `kind` in inglese nudo sotto gli occhi del trader.

### 6.2 Giornata operativa = giorno di PIAZZAMENTO, ovunque (C-01)
`operatingDay = bot.operatingDay ?? romeDay()` è l'**unica** giornata della pagina e
alimenta DayBar, KPI, RiskPanel, tab Trade e Storico. Prima: KPI e Storico per giorno di
REGOLAZIONE, tab Trade per giorno di piazzamento, pannello Rischio con due giorni diversi
→ tre numeri per la stessa giornata. Tutti i contatori (`won_today`, `lost_today`,
`legs_today`, `events_today`, `day_liability`) vengono dagli **stessi** aggregati.
Quando la migrazione v2 non c'è, `safeBot.aggregatesHaveDay()` è `false` e la pagina
**lo dichiara** invece di spacciare stime per numeri del servizio:
nota in DayBar e riga `risk-day-estimated` («⚠ impegnato stimato dal client (applica
safe_strategy_bot_v2.sql)»).

### 6.3 Tabella dei trade (`SafeTradesTable.tsx`)
Una riga = una **POSIZIONE**; le gambe di chiusura stanno annidate sotto con «↳ Green-up /
Cash out / Chiusura di #N», con lato, size@quota, aliquota di **quella** chiusura,
stato, P&L e badge `parziale`. 16 colonne fisse:

`Ora (Roma) · Partita · Strategia · Mercato · Selezione · Lato · Quota · Quota ORA ·
Δ tick · Stake · Liability · Se chiudo ora · Live · Stato · P&L · Cash out`

- **Quota ORA** = best del lato con cui si CHIUDE (mirror di `CashOutButton.greenPrice`),
  con tooltip su mercato e blocco del feed di provenienza; **Δ tick** dall'ingresso
  (`riskMath.ticksBetween`, segno a favore/contro); **Se chiudo ora** = `lockedPnlAt`
  **netto della commissione DEL TRADE** (`safeBot.tradeCommission`, L-02).
- **Liability** mostra il **residuo** dopo la copertura, e con la copertura in volo
  aggiunge «rischio ancora pieno: copertura in volo».
- **Stato** in italiano, in ordine di gravità (`safeRowStatus`, pura e testata):
  `ERRORE DEFINITIVO` → `IN VERIFICA SU BETFAIR` → `COMBO INCOMPLETA: in chiusura` →
  `VINTO/PERSO/VOID` → `COPERTA xx %` / `CHIUSO IN GREEN-UP` / `CASH OUT MANUALE` /
  `CHIUSO` → `USCITA FALLITA` → `SENZA FEED da hh:mm` → `APERTO` / `IN CORSO`.
  Sotto lo stato: `ExitBadge`, la riga «cosa sta facendo l'uscita» (`exitRunLine`:
  «USCITA FALLITA, ritento alle 18:07», «uscita: ritento (2°)», «uscita: in attesa di
  prezzo»), il motivo dell'uscita scritto dal servizio, il blocco del mercato, il motivo
  di riconciliazione tradotto in italiano (`safeActivity.safeReasonLabel`), l'**hold**
  («In attesa: …, P(perdita) 0,4 %») e l'**esito dell'ultima richiesta** sulla riga
  (`requestOutcome`: in coda / eseguito / rifiutato / errore + messaggio).
- **Risultato reale** della partita accanto al nome per le posizioni regolate
  (`realScoreOf`, dal feed) e bordo sinistro colorato per l'esito.
- **Annulla** sulle riserve `pending` (kind `cancel`), disabilitato se in riconciliazione;
  il rifiuto del servizio arriva come esito della richiesta.
- Oltre le 200 righe caricate una chiusura può perdere la sua apertura: viene **detto**
  (`safe-orphan-note`, L-04), non mascherato.

### 6.4 Un toast per POSIZIONE, e ogni richiesta ha un esito
- Settlement: `toastSettlement` (formato unico di `lib/toasts.ts`) **una volta per
  posizione**, con il P&L e l'esito della posizione (`positionOutcome`), `✋` se la
  decisione è stata manuale (M-04).
- Richieste operative: `bot.freshOutcomes` → un toast per richiesta, **anche per i
  rifiuti** («Cash out: rifiutato dal servizio» + motivo), una sola volta (L-07/M-21).

### 6.5 Attività del servizio (H-16)
`SectionCard` «Attività» + `ActivityFeed` filtrabile: `safeActivity.SAFE_ACTIVITY_EXTRA`
mappa **tutti** i `kind` scritti dal backend in etichette italiane con colore e
`critical: true` quando l'utente deve accorgersene; `safeActivityLine(payload)` compone la
riga (partita, lato+selezione, mercato, `size @ quota`, P&L, liability, tipo di uscita,
motivo tradotto, errore, «3° tentativo», «ritento alle 18:07», sorgente delle quote,
gambe in sospeso, correzioni dei parametri «salvato X → in uso Y»). L'intestazione conta
quante righe sono «da guardare». Prima nessun componente leggeva
`safe_strategy_activity`: il trader non sapeva **perché** il bot non entrava.

### 6.6 Parametri su `ParamsSheetBase` con valori effettivi e clamp visibile
`BotParamsSheet.tsx` è costruito sul pannello condiviso: gruppi spec-driven, un solo
bottone **Salva parametri**, **Default**, indicatore di modifiche non salvate e
soprattutto **clamp dichiarato campo per campo** — «salvato X / in uso Y» da
`control.stats.params_effective`, più le correzioni dell'attività `params_clamped` e le
chiavi che il servizio ha davvero riscritto sul DB (`params_invalid.persisted`).
I limiti sono gli stessi del servizio (`bot_service.resolve_params`,
`risk.merge_risk_params`, `exits.merge_exit_params`). Senza `params_effective` (servizio
mai avviato) la scheda lo dice invece di mostrare il form come se fosse «in uso».
Salvare **senza nessuna strategia** selezionata viene rifiutato con un avviso (H-14).

### 6.7 Fallback dichiarati senza `safe_strategy_bot_v2.sql`
La pagina funziona anche senza la migrazione, ma **lo dichiara**: contatori di giornata e
capitale impegnato stimati dal client (§6.2), attività letta con la RPC dedicata o assente
(`useSafeBot` prova `fetchSafeActivity` in background, max ogni 30 s, e lo stato vuoto dice
«serve la migrazione safe_strategy_bot_v2.sql o il bot avviato»), cash out rifiutati che
restano `error` invece di `rejected` (`bot_db.set_request_status` ripiega conservando il
motivo in `result.rejected`).

### 6.8 Realtime: un canale, debounce 1,2 s
`useSafeBot` usa UN canale (`subscribeSafeBot` su control+trades+requests) + poll di
sicurezza a 15 s, e **coalizza** le notifiche: `RELOAD_DEBOUNCE_MS = 1_200` (Omega 1,2 s,
Mike 1,5 s). Senza, un solo settlement (apertura + gamba di chiusura + richiesta +
control = 4+ eventi) faceva partire una `get_safe_state` **per notifica**: con dieci
posizioni che si regolano insieme sono decine di RPC in un secondo (rischio di esaurire
l'IO di Supabase) e la tabella che sfarfalla. Le opportunità hanno il loro canale con
flush a 400 ms. Il reload è protetto da sequenza (risultati fuori ordine ignorati) e da
smontaggio.

---

## 7. Storico giornaliero (daily_history.sql, lib/dailyHistory.ts)
RPC `get_safe_daily(from,to,sport)`, `get_safe_day_trades(day,sport)`: per giorno
operativo Europe/Rome P&L regolato, trade piazzati, vinti/persi, win rate, profit factor,
drawdown, streak, breakdown per strategia/sport/origine. Verificate a runtime (10/09:
10 trade, +2,15 €).

**11/09**: `safe_strategy_bot_v2.sql` ridefinisce le due RPC perché passino
`p_day_by = 'placed'` al motore condiviso (C-01: lo storico ora attribuisce la giornata
come KPI e tab Trade). Le funzioni **condivise** `trading_daily_history` /
`trading_day_trades` NON vengono ridefinite qui: la lezione di `mike_history.sql` (bug R2
dell'audit) è che ricrearle con firme diverse le rende **ambigue** e rompe tutti i bot.
Il clamp della finestra a 400 giorni (M-17) vive dentro quelle funzioni condivise ed è
corretto da `mike_history_v2.sql`, che va applicata **prima** (§12.7).
Lato UI il calendario e il dettaglio giornata sono allineati: `DayDetail` non somma più
trade che il calendario attribuisce a un altro giorno (`settled_in_day`, H-11/M-18).

---

## 8. Test dal vivo del 10/09 (paper) — cosa ha funzionato
- Scanner: stream 104 mercati (67 nuovi), heartbeat ok; bot: heartbeat 2 s, nessun crash
  (due eccezioni transitorie Supabase gestite dal fail-closed).
- 14+ trade automatici coerenti col manuale (Esatto lay 30–70 su squadra ≤1 gol; tennis
  back 1,03–1,10 con set+2 game); skip corretti per liquidità e spread.
- Richieste manuali place/cashout, RPC di stato/storico, settlement coppie al centesimo.
- Uscite: tempo in profitto, hold su margine ampio poi chiusura in profitto, tennis
  take-profit; residuo gestito.
- Bug corretti in corsa: λ assenti per partite già in corso; statistiche che contavano le
  gambe di chiusura; entrata su spread anomalo; chiusura a tempo in perdita cieca; log
  duplicati; nome partita mancante su trade manuale Omega; isolamento test calibrazione.

---

## 9. Spunti per il livello successivo (in ordine di valore)

### 9.1 Uscite: cosa resta aperto (strategia, non impianto)
L'impianto delle uscite è stato messo in sicurezza l'11/09 (§3.2–3.6: nessuno stato
terminale, netto di commissione, tetto duro del feed, combo solidale). Restano aperti i
**quattro punti di strategia** sollevati dall'utente il 10/09 sera, ancora validi:
1. riscrivere profit/loss **strategia per strategia** col manuale alla mano: la regola
   «esci comunque a 70–75'» va riscritta come *presa di profitto*, non come chiusura
   cieca (il 10/09 il "tempo 72'" chiuse il trade 12 a −4 su un +1,9 quasi certo; la
   decisione a modello ha tappato il buco, la regola no);
2. «controllo del gioco» per la Base, oggi non misurato — candidato `pressure.py`
   (corner/cartellini);
3. attesa dopo il gol: oggi 30 s fissi (`loss_settle_delay_s`); valutare «attendi che il
   mercato riapra e il prezzo si stabilizzi» (varianza dei tick) invece del timer;
4. uscita **a scala** (parziale) invece di tutto-o-niente sui libri sottili.

### 9.2 Resto della scaletta
1. **Dashboard**: l'uniformazione è fatta (§6); resta la migrazione dei tre pannelli
   parametri al 100 % (Safe è già su `ParamsSheetBase`; Omega e Mike no) e la verifica
   visiva vera, che l'agente non può fare.
2. **Fedeltà paper**: simulare bet delay 5 s e ricontrollo size; oppure instradare sempre
   sulla coda flumine (follow automatico degli eventi tradati).
3. **Base e Punta** anche per partite già in corso: recuperare la quota pre-match dal
   catalogo Betfair pre-KO (snapshot periodico dei mercati del giorno) invece del congelamento
   al calcio d'inizio.
4. **Modello**: validazione su più registrazioni (registrare ogni giorno con REC), pressione
   con dati reali, xG live se mai disponibile; tenere i lay spenti finché il backtest
   leave-one-out non è positivo.
5. **Anomalie**: misurare quante durano > 5 s (bet delay) e quante vengono abbinate; è il
   segnale con edge per costruzione ma la latenza decide tutto.
6. **Rischio**: cap per strategia (un lay a 60 non è un back a 1,05), stop perdita per
   strategia, esposizione correlata tra Safe e Omega sulla stessa partita.
7. **Certificazione liquidità lato back** (dal 09/09): ancora parziale; la sonda
   `liquidity_probe` è solo report; usare le registrazioni REC.
8. **Live**: BLOCCATO — mai prima di una settimana di paper con settlement e uscite tutte
   verificate. `safe_strategy_bot_v2.sql` è applicata; adesso il prerequisito di
   migrazione è `safe_strategy_paper_live_2026-09-13.sql`. Restano da riattivare i cap di
   rischio (`daily_liability_cap` era 0,0 = disattivo il 13/09, `max_open_trades` null) e
   da osservare qualche giorno di paper con BASE e PUNTA finalmente attive: fino al 13/09
   avevano prodotto **un trade ciascuna** su 240.

---

## 10. Comandi utili
```
python -m pytest Betfair/safe_strategy -q                       # 569 test (11/09)
python -m pytest Betfair/safe_strategy Betfair/omega Betfair/mike -q   # 1254 (3 bot)
python -m Betfair.safe_strategy.tools.backtest_opportunity --help
python -m Betfair.safe_strategy.tools.validate_opportunity --build-cache --fit
cd frontend && npx vitest run && npx tsc --noEmit && npm run build    # 1642 test
cd frontend && npx vitest run --config vitest.cert.config.ts    # CERTIFICAZIONE ripetibile
```
Riavvio del solo bot: terminare il figlio python `safe_strategy.bot_service` (il watchdog
lo rilancia in 10 s). **L'exe è l'avviatore del `main.js` vivo**: dopo una modifica si
riavvia l'app, non si ricompila. Parametri: tabella `safe_strategy_control.params`
(scheda Parametri).
Commit: 10/09 → `99fbff8`, `5fd3fae`; **11/09 sera → `9d09c81`** (base `1b6b151`), master.

---

## 11. PIANO «250 AL GIORNO» — panoramica completa del progetto e sei edge strutturali (10/09 sera)

Inventario completo in sola lettura (tre esplorazioni) di TUTTO il repo: bot esistenti,
motori e dati, terminal/runner/UI. Da qui si riparte domani: validare ogni strumento e
iniziare.

### 11.1 Cosa esiste davvero (con i verdetti dei dossier)
- **`Betfair/stream/scalper/theta_bot.py` ("cecchino")** = lo scalp Under a decadimento
  esiste già: coppia back+lay di uscita precalcolata (`theta_pair`, "mai gamba senza
  uscita"), semaforo hazard dall'atlante, `scalper_service`/`scalper_session` = slot per
  partita con heartbeat e kill-switch, `risk_semaphore` (gol = sospensione = stop
  ingressi), `tools/atlas_v0.py` simulatore di coda (PIQ, sospensione uccide l'ordine),
  `run_theta.py` backtest con bet delay reale. Verdetto luglio: EV− in tutte le 18 varianti
  a prezzi medi 1,2–2,0 (migliore −22,07); positiva solo la cella post-gol (+2,12, n=15).
  **Fascia 1,02–1,06 mai testata.** `MISSIONE_250_ROADMAP.md` §1.3 ha la formula del segno:
  hazard/min × durata vs guadagno del tick (hazard 2,6%/min hold 90 s = −0,28; 1,5%/min
  hold 60 s = +0,36).
- **`sniper_bot`** (+0,99 netto/14 eventi, fragile OOS), **`scalper_bot`** (maker pre-match
  edge stretto +0,77, in-play perde per il bet delay), `habitat_scan` (selezione partite
  GO≥60), `bias_resolver`, `tools/mcm.py` (scala tick Betfair).
- **`SCALPING_DEFINITIVO_2026-07-16.md`**: averaging-down, martingala, post-goal fade,
  1-tick in-play = NO-GO; **EV+ solo "cavallo del kickoff"** (back Under pre-KO, chiuso a
  KO+5': +0,79 €/strumento, peggiore −2,25, positivo in tutte le 11 varianti) e 1-tick
  pre-match (calcio 5/6, tennis 2/2). MAI messo in produzione.
- **Tennis** (`tennis_scalper`, `tennis_live`): ~1100 combinazioni su 26 match → nessun edge
  meccanico; FLB +1,84 con n=2. Nessuna serie storica di prezzi in-play nel repo (solo
  192 righe pre-match): non backtestabile oggi.
- **Trading math** (`Betfair/stream/trading/`): greenup, hedging, dutching, xhedge,
  risk_engine (offset/bracket/trailing), daily_pnl, controls (esposizione per
  selezione/evento/lega + rate), submin. Tutto puro e testato.
- **Runner/worker**: `live_order_worker` (coda persistente, claim atomico, client_ref
  univoco; azioni place/cancel/replace/place_submin/greenup/dutch/cashout_all/
  cashout_event), `risk_engine_worker` (offset, bracket con trailing, stop/take-profit,
  stop_entry, chase, auto_hedge), `daily_stop_worker`, `LiveEventExposureControl`.
  **Il "lay di uscita in coda a prezzo fisso" esiste già**: greenup con `params.target_price`
  (greening column). Nessuna migrazione serve per usarlo. Polling coda 0,15 s dal desktop
  (audit 17/07: a 1 s i bot non piazzavano).
- **Dati**: atlante hazard v2 (54.009 partite, 148.001 gol: P(gol nei 2'/3') per
  minuto×gol, lega/squadra/h2h), `match_events` 9,8 M (2,69 M gol con minuto), `matches`
  1,47 M, curva tempi gol (120.542 gol), intensità per lega (206.261 fixture), rho per lega,
  `dynamic_cal`, calibrazione in-play di oggi. **40 registrazioni complete con tutte e 9 le
  linee Under** + FH 0.5/1.5/2.5, MO, HT, HTS, HT/FT, BTTS, CS, DC minuto per minuto con
  profondità; `live_market_snapshots` 1,07 M righe (26 eventi).
- **Manca**: curva di deriva del prezzo per minuto per (linea, minuto, punteggio) e
  liquidità per tick a 1,01–1,06 (i dati ci sono, il calcolo no; `theta_decay/ht_decay.py`
  ha misurato solo l'intervallo); prezzi tennis in-play; archivio Betfair Historical.
- **Motori pre-match/ML/value**: matematica certificata, edge zero o negativo (ROI −2,5%/−9%,
  optimizer's curse): prior, non segnali. `money_management.py` (slot paralleli + Kelly
  frazionario) riusabile per la matematica.
- **Altri progetti** (fuori scopo): KDP, Polymarket suite, MT5 EA, PMI Boost, JobSpy;
  `BOT PRONTI BF USATI SU SERVER` contiene un vecchio `Scalp UNDER_2_5`.

### 11.2 I sei edge strutturali (proposta, ordine di esecuzione)
1. **Kickoff carry** — back Under pre-partita, chiusura KO+5'. EV+ dimostrato (+0,79 €/
   strumento, 11/11 varianti), zero bet delay. Su 30 partite/giorno con stake 200 €:
   40–80 €/giorno. Da produzionizzare: `scalper_lab` config + coda ordini + slot.
2. **Uscita PRIMA del gol** — ogni lay Omega (e Safe) entra con il suo back a riposo già nel
   libro a prezzo fisso con persistenza PERSIST (sopravvive alla sospensione, primo in coda
   alla riapertura). Sul trade 70 di oggi: costo del green-up da −22 a ≈ −8. Strumento:
   greenup `target_price` + persistenza nel worker; regola OCO con `bracket`.
3. **Arbitraggio delle equivalenze** — Under 0.5 ≡ CS 0-0; Under 1.5 ≡ 0-0+1-0+0-1;
   BTTS No ≡ unione porte inviolate; Over 0.5 1T ≡ 1 − HTS 0-0; ecc. Tutti in stream nel
   feed. Divergenza oltre commissione+spread → compra il lato economico, vendi il caro:
   profitto bloccato. Estendere `combos.py` alla tabella completa delle equivalenze.
4. **Finestra di riapertura post-gol** — 10–30 s dopo un gol i mercati riprezzano a velocità
   diverse (scalette Under impossibili, CS in ritardo). Puntare `anomaly.py` su quella
   finestra con esecuzione immediata (`process_anomalies` ogni ciclo) e persistenza.
5. **Scalp Under di coda** — back 1,02–1,06 con P calibrata ≥99%, lay a 1,01 subito in coda,
   ingresso solo con P(gol nei 3') dall'atlante < 4%, slot per partita, stop al gol in
   green-up (costo 1–3 tick). Motore di volume. Prima: curve deriva/liquidità dalle 40
   registrazioni (retarget di `atlas_v0.py`), poi `theta_bot` in quella fascia, paper con
   bet delay reale (`tennis_live/paper_execution.py` come modello).
6. **Intervallo a rischio zero** — 45'→46' hazard = 0 per 15 minuti: uscite a tempo e carry
   si chiudono lì dentro, mai a ridosso del fischio.

### 11.3 Aritmetica dell'obiettivo
Edge per scalp 1–2% netto → 250 €/giorno = 12.500 € abbinati/giorno = 50 scalp da 250 €
su 10–15 slot con 3–4.000 € di capitale rotante sui campionati liquidi; sui minori la
liquidità a 1,01 è 50–900 € per linea. Stima onesta: 100–180 €/giorno con 3–4.000 €;
250 con capitale doppio o campionati maggiori. Nessuna tecnologia manca: mancano le
due curve (deriva, liquidità per tick), la validazione di ogni strumento e il capitale.

### 11.4 Domani: validazione strumento per strumento, poi si parte
Per ciascuno: cosa fa, test verdi, backtest sulle registrazioni con bet delay reale,
paper dal vivo, verdetto GO/NO-GO scritto qui. Ordine: 1 (kickoff carry), 2 (uscita a
riposo), 3+4 (equivalenze, riapertura), 5 (coda Under: prima le curve), 6 (regola).
Le correzioni «§3 uscite, §6 visualizzazione» che chiudevano questo elenco sono state
**fatte l'11/09** (§12): resta la parte di strategia delle uscite (§9.1).

---

## 12. CERTIFICAZIONE 11/09 sera — audit applicato, review, contratto UI (pushato `9d09c81`)

L'audit `Betfair/AUDIT_2026-09-11_omega_safe_mike.md` (quattro revisioni indipendenti +
verifiche sui dati reali del DB) è stato **applicato per intero** su backend e UI, poi
sottoposto a review indipendenti e certificato sui dati reali. Base `1b6b151`, commit
**`9d09c81`** su master. Perimetro Safe Strategy: 39 file, +7.651 / −1.092 righe.

### 12.1 Item dell'audit → fix, con file:funzione

| Item | Cosa era rotto | Dove è risolto |
|---|---|---|
| **R1** (HIGH) | Cash out «n/d» sui trade O/U pur con il mercato nel feed (quote 2,4 s): la UI prezzava solo MO/CS/HTS | `lib/safeBot.ts:safeTradeBook` (risoluzione per `market_id` → MO → tipo+linea → blocco unico), `lib/safeStrategyScan.ts:ScanMarketBlock`/`scanMarketBlocks`/`scanBlockByMarketId`/`isUsableBlock`/`usableMarketBlocks` |
| **C-01** | Tre giornate diverse per lo stesso giorno (KPI/Storico per regolazione, Trade per piazzamento, Rischio con due giorni) | `safe_strategy_bot_v2.sql:safe_aggregates_sql` (`pos_placed_at` = `placed_at` dell'APERTURA), `get_safe_daily`/`get_safe_day_trades` con `p_day_by='placed'`, `bot_db.aggregate_rows`, `bot_service.run_once` (stats dagli stessi aggregati), `pages/SafeStrategy.tsx` (`operatingDay`), `safestrategy/RiskPanel.tsx` |
| **C-02** | Cash out PARZIALE: qualunque chiusura non in errore marcava il cash out «in volo» → residuo inchiudibile | `execution.apply_hedge_state` (`meta.hedge`), `lib/safeBot.ts:hedgeState` (`inFlight`), `SafeTradesTable.tsx` (`canCashOut`, `residual`), `safe_strategy_bot_v2.sql:safe_request` (fraction in (0,1] anche sul residuo) |
| **C-03** (live) | `cancel` dalla UI cancellava una riserva in riconciliazione → ordine reale non più tracciato | `bot_service._request_cancel` (`rejected: in riconciliazione`, attività `cancel_rejected`), `bot_service.reconcile_pending` (ramo `free` → `_terminal_error(reconcile_ordine_assente)`), `bot_service._request_cashout` (rifiuto sulle righe in riconciliazione) |
| **C-04** | `niente_da_chiudere` TERMINALE: uscita «inviata» e liability piena fino al settlement | `bot_service._send_exit` → `state='waiting_price'` + `exits.retry_backoff_s(wait_attempts)`, attività `exit_wait` |
| **H-01** | `exit_kind:'greenup'` non esisteva nel backend: badge e sotto-riga «Green-up» erano codice morto | `exits.EXIT_KINDS` + `exits.ui_exit_kind()` (vocabolario CHIUSO), `execution.close_trade(exit_kind=, exit_reason=)`, `bot_service._stamp_exit_on_parent`/`_stamp_closing_leg` |
| **H-03** | `stats.open_liability` contava i pending in riconciliazione, la RPC no → KPI ≠ Rischio | `bot_db._counts_as_placed`/`_is_reconciling_row` + `reconciling_liability`, `safe_aggregates_sql` (`is_placed`, `is_reconciling`), `RiskPanel` («di cui in verifica su Betfair») |
| **H-05** | Uscita fallita definitivamente = normale «APERTO», nessun badge | `bot_service._write_exit_state` (`meta.exit`), `lib/safeBot.ts:exitRunState`, `SafeTradesTable.safeRowStatus`/`exitRunLine` |
| **H-14** | `variants: []` sul DB → bot muto, UI con 4 strategie «attive» e «Salva» che le riattivava in silenzio | `bot_service.normalize_variants` + `resolve_params`, attività `params_invalid`, `BotParamsSheet.tsx` (salvataggio rifiutato senza strategie, varianti EFFETTIVE) |
| **H-15** | Clamp invisibili: il servizio usava 0, la scheda mostrava 50 | `bot_service.params_effective`/`params_corrections`/`normalize_control_params` (+ attività `params_clamped`), `get_safe_state` → `params_effective`, `BotParamsSheet` (hint «salvato X / in uso Y») |
| **H-16** | Activity log del servizio invisibile: nessuno leggeva `safe_strategy_activity` | `safe_strategy_bot_v2.sql:get_safe_state` (chiave `activity`) e `get_safe_activity()`, `bot_db.recent_activity`, `safestrategy/safeActivity.ts`, `ActivityFeed` in `pages/SafeStrategy.tsx` |
| **H-17** | `exit_failed` terminale dopo 3 tentativi e `residual_exhausted`: liability mai più coperta | `bot_service._process_exit_one` (cap NON terminale → backoff lungo) + `exits.RETRY_BACKOFF_S`/`retry_backoff_s` |
| **H-18** | Posizione viva senza riga nel feed: silenzio totale | `bot_service.check_feed_blind`/`note_feed_blind`/`clear_feed_blind`/`is_blind_relevant`, `stats.feed_blind`, `lib/safeBot.ts:blindSince` |
| **H-19** | Una `listMarketBook` REST per posizione aperta ogni 2 s | `bot_service.rest_gate` (10 s/mercato, 8 per ciclo), `_settlement_needs_rest`, `prices_for(allow_rest=, rest_now_ts=)` |
| **H-20** | COMBO «tutto o niente» valida solo per le riserve: gamba fillata + gamba in errore = posizione nuda | `bot_service.combo_siblings`/`_combo_leg_prices`/`_close_combo_siblings`/`_mark_combo_incomplete`/`_unwind_combo`/`unwind_incomplete_combos` |
| **H-21** | Nessun budget di ritentativi: un FOK rifiutato veniva ripiazzato ogni 2 s | `bot_service.place_allowed`/`_place_fail`/`seed_place_attempts`, `bot_db.place_attempts`, `params.place_max_attempts`, attività `place_retry`/`place_exhausted` |
| **M-04** | Settlement per gamba: l'apertura di un green-up in utile appariva «PERSO» + doppio toast | `execution.settle_position`/`settle_row(position=)`/`position_result`, attività `settle_position`, `lib/safeBot.ts:positionOutcome`, toast unico in `pages/SafeStrategy.tsx` |
| **M-05** | Gamba `error` contata e «in corso per sempre» | `bot_service._terminal_error` (`error_final` + `settled_at`), `execution.close_trade` (errore terminale), `lib/safeBot.ts:errorFinal`/`isLivePosition` |
| **M-06** | Copertura parziale senza via manuale; anteprima cash out sull'esposizione piena | `execution.apply_hedge_state` (`meta.hedge`), `safe_request` (fraction sul residuo), `lib/safeBot.ts:tradeExposureNow`, `CashOutButton` (`residual`) |
| **M-15** | KPI «Trade aperti» contava le chiusure e ignorava le `hedged` parziali | `lib/safeBot.ts:isLivePosition` + `aggregates.open_count` (`safe_aggregates_sql`) |
| **M-16** | `won`/`lost` per status grezzo della gamba (contratto dormiente) | `safe_aggregates_sql` (`total_pnl` per SEGNO della posizione, LATERAL), `bot_db.aggregate_rows` (`won_today`/`lost_today`) |
| **M-21** | Conteggi divergenti fra Rischio e tab, nessun «Annulla» per le riserve, «Investi» spento senza dirlo | `safe_strategy_bot_v2.sql` (`status` 'rejected'), `bot_service._request_state`/`_request_result`, `lib/safeBot.ts:requestOutcome`, `SafeTradesTable` (bottone **Annulla** + esito sulla riga), `pages/SafeStrategy.tsx:countOpps` (i tab contano le OPPORTUNITÀ come il RiskPanel), `OpportunityGroup` (`opp-stale-note`) |
| **M-23** | `market_open` leggeva `mo_status` anche per O/U, BTTS, HT | `exits.market_open` + `exits._STATUS_BLOCK_BY_TYPE`, `lib/safeBot.ts:marketBlocked` |
| **M-24** | Freschezza del feed senza tetto duro nelle uscite/cash out | `exits.FEED_HARD_MAX_S = 120` + `feed_is_fresh(hard_max_age_s=)`, `lib/safeBot.ts:FEED_HARD_MAX_MS`/`feedFreshness.hardOld`/`staleReason` |
| **M-25** | Mercato sparito nel settlement: silenzio oppure flood | `bot_service._market_missing`/`_market_seen` (`MARKET_MISSING_MIN_FAILS`, `MARKET_MISSING_LOG_EVERY_S`, `meta.market_missing_since`) |
| **M-26** | Liability `hedged` contata piena | `execution.remaining_liability`/`residual_liability`, `safe_aggregates_sql` (CASE sulla liability residua), `SafeTradesTable` (colonna Liability = residuo) |
| **M-27** | Decisione a modello al LORDO della commissione | `exits.net_of_commission`, `bot_service._commission_of`/`_decide_model_exit`/`_model_gate` |
| **M-28** | `exit_hold` riscritto a ogni ciclo (motivo con numeri) | `exits.hold_code`, `bot_service._model_gate`/`_write_model_hold` (`meta.exit_hold.code`) |
| **M-29** | `aggregates()` leggeva TUTTA la tabella ogni 2 s | `safe_strategy_bot_v2.sql:get_safe_aggregates`/`safe_aggregates_sql`, `bot_db.aggregates` (RPC + finestra di ripiego 300 s) |
| **M-30** | «Salva» non aggiornava i modelli: serviva un riavvio e nessuno lo sapeva | `bot_service.params_signature` + `main()` (ricostruzione a caldo di engine, `_EXIT_MODEL`, modello tennis) |
| **M-31** | Size minima Betfair 2 € non gestita nel REST live | `execution._min_size_live` + `execution.place` (solo sulle APERTURE), `params.min_stake`, `InvestAction.BETFAIR_MIN_STAKE`/`minStake` |
| **M-32** | `opps_min_confidence`/`opps_min_edge` senza clamp: un valore non numerico = bot «morto» per la UI | `bot_service.resolve_params` |
| **M-33** | Chiusura orfana regolata senza le sorelle | `bot_service.settle_open` (`orphans_by_parent`, rilettura dopo ogni orfana) + `execution.settle_orphan_closing(siblings=)` |
| **L-01** | `meta.hedging` letto dalla UI, mai scritto | `execution.apply_hedge_state` |
| **L-02** | Ore senza fuso; commissione della tabella dal parametro corrente e non dal trade | `lib/format.ts:fmtTime` (sempre Europe/Rome), `execution.close_trade` (aliquota ereditata, mai NULL), `lib/safeBot.ts:tradeCommission`, `SafeTradesTable` (aliquota della singola chiusura) |
| **L-04** | «prec.» fuorviante, `hedged` contate vive, chiusure orfane oltre le 200 righe | `pages/SafeStrategy.tsx` (toggle «solo oggi / mostra tutte»), `lib/safeBot.ts:isLivePosition`, `SafeTradesTable` (`safe-orphan-note`) |
| **L-07** | Badge inglesi in `SignalCard`, errori senza dettaglio, hold con chiavi mai scritte, step stake senza minimo 2 € | `SignalCard.tsx` (stato italiano via `safeRowStatus`, `ExitBadge`, hold, esito richiesta, riga mercato/selezione/best), `InvestAction.tsx` (minimo Betfair + messaggio d'esito), `safeActivity.safeReasonLabel` |
| **L-09** | `meta` sovrascritto negli errori (si perdeva il piano) | `bot_service._terminal_error`, `bot_service._place_fail`, `execution.close_trade` (merge del meta della riserva) |
| **L-10** | Reconcile paper che confermava qualunque pending, inventando una posizione | `bot_service.reconcile_pending` (paper + `X.is_reconciling` → `error` terminale `reconcile_paper_senza_fill`) |
| **L-11** | `locked_pnl` valorizzato anche sul parziale | `execution.close_trade` (`locked_pnl` solo a copertura completa, `planned_lock` altrimenti) |
| **L-12** | bo5 tennis dedotto da «3 set giocati» | `bot_service._best_of` → `tennis_opportunity.detect_best_of` |
| **L-13** | Log duplicati degli skip | `bot_service._log_skip` (dedup per kind+evento+chiave, `skip_log_interval_s`, spurgo `_SKIP_LOG_PRUNE_S`) |
| **L-14** | TTL della cache λ solo sui ripieghi | `bot_service.LAMBDA_TTL_S = 3600` + `resolve_event_lambdas` (`default`/`pre_ko` = 300 s, fonti buone 1 h) |
| **L-15** | Chiavi di Omega usate dal codice condiviso; manuale senza check SUSPENDED/freschezza | `bot_service.DEFAULT_PARAMS` (`execution_mode`, `omega_live_via_flumine`, `paper_fill_ttl_s`, `live_fill_deadline_s`, `min_stake` dichiarate e clampate), `bot_service._request_cashout` (rifiuto su mercato sospeso, book REST su feed stantio) |

### 12.2 Review indipendenti: i finding corretti dopo l'audit
Le review non hanno trovato solo dettagli: hanno trovato **due modi di perdere soldi**
introdotti dalle correzioni stesse. Sono tutti risolti in `9d09c81`.

**Critici**
- **C1 — la copertura IN VOLO non riduce niente: liability PIENA.** `remaining_liability`
  tornava 0 appena esisteva un `meta.hedge`, anche con l'ordine di chiusura ancora in coda:
  il cap giornaliero si liberava con il 100 % del rischio ancora a mercato. Oggi 0 **solo**
  a copertura completa **e confermata**; `worst_case` assente = liability d'apertura.
  Regola generale scritta nel codice: **IGNOTO = PIENO**.
  `execution.remaining_liability`/`residual_liability`, `safe_aggregates_sql` (CASE),
  `lib/safeBot.ts:hedgeState.inFlight`.
- **C2 — il minimo di 2 € vale solo sulle APERTURE.** Betfair accetta gli ordini sotto
  minimo che RIDUCONO una posizione: rifiutarli lasciava un residuo da 1,40 € in
  `retrying` per sempre. `execution.place` → `is_closing = meta.cashout or closes_trade_id`.

**Alti**
- **H1 — due liability diverse, mai confuse.** `day_liability` = capitale **IMPEGNATO**
  nella giornata (liability d'apertura, sempre: coprire NON libera il cap);
  `open_liability` = rischio **vivo adesso** (residuo). `bot_db._committed_liability`,
  `safe_aggregates_sql` (`committed`), `RiskPanel` («impegnato oggi» vs «rischio aperto ora»).
- **H2 — mai riscrivere sul DB una chiave money-critical.** Un clamp persistito distrugge
  l'intenzione dell'utente: `daily_loss_stop: 50` clampato a 0 e salvato = stop perdite
  spento **per sempre**. `bot_service._NEVER_PERSIST` (loss stop, cap, stake, commissione,
  min stake) → correzione solo in memoria + `params_effective` + attività `params_clamped`;
  e il segno si **interpreta**: `risk.merge_risk_params` → `-abs(daily_loss_stop)`.
- **H4 — il backoff frena l'INVIO, non il tracciamento; gli urgenti lo scavalcano.**
  `bot_service._exit_candidates` non filtra più per backoff (gol/rossi/game vanno seguiti a
  ogni ciclo) e `_exit_due` + `URGENT_EXIT_KINDS` mandano subito perdita, rosso e obbligo
  tennis. (Lo stesso identificativo H4 nella review dello scanner: le partite Mike in sola
  osservazione **non** sono esenti dal tetto — `db._mike_has_exposure`.)
- **H5 — cash out manuale su feed stantio: si legge il book REST, non si rifiuta subito.**
  `bot_service._request_cashout` prova il feed fresco, poi `_book_prices` (REST, senza
  budget: è un clic), e `result.source` dice da dove vengono le quote usate
  (`feed` | `rest`), mostrato in UI (`safeActivity.safeSourceLabel`).
- **H6 — la combo incompleta va svolta anche se una gamba è ancora `pending`.** Il fill
  della coda arriva cicli dopo: `_mark_combo_incomplete` mette un marker che sopravvive al
  riavvio e `unwind_incomplete_combos` chiude appena il fill è confermato, a ogni ciclo.

**Medi e bassi (sintesi)**
- **M1**: una sola SELECT delle posizioni vive per ciclo, passata a tutte le fasi
  (`run_once` → `risk_ctx['open']` → `process_exits(open_rows=)`, `combo_siblings`,
  `unwind_incomplete_combos`); `_write_exit_state` non rilegge se il meta locale c'è;
  `blind_since` scritto una volta sola.
  Sul frontend, lo stesso numero: il default di `tennis_exit_on_lost_game` nella scheda
  parametri deve essere quello del servizio — `false`
  (`BotParamsSheet.EXITS_DEFAULTS` = `exits.DEFAULT_EXIT_PARAMS`).
- **M2**: la cecità del feed non è un allarme per le posizioni **pre-KO**
  (`is_blind_relevant`).
- **M3**: «integrale» = chiusura dell'intera posizione (`fraction` 1.0 / `pending_fill`),
  non «residuo già a zero»: con la coda flumine un green-up finiva marcato `profit`
  (`_send_exit` → `integral`).
- **M4**: la RPC degli aggregati è **owner-only nel corpo**, non solo per GRANT: senza,
  qualunque utente autenticato leggerebbe l'esposizione del conto
  (`safe_strategy_bot_v2.sql:get_safe_aggregates`).
- **M5**: indici a supporto della LATERAL degli aggregati
  (`idx_safe_trades_closes_status`, `idx_safe_trades_placed_open`).
- **M9**: le sorelle vengono **rilette** dopo ogni orfana regolata.
- **M10**: chiavi mancanti o illeggibili nel meta → liability piena (con C1).
- **M11**: `market_missing` solo dopo 3 letture consecutive fallite (un timeout di rete
  non è un mercato sparito).
- **M12**: `settle_row` fonde il meta sulla riga **corrente** (rilettura), non sullo
  snapshot: fra la lettura e la scrittura `apply_hedge_state`/`close_trade` possono aver
  scritto `hedge`/`exit_*`.
- **L1**: il gate REST è cablato nei chiamanti (`rest_now_ts`), non nel default: le azioni
  manuali non devono passarci.
- **L3**: la finestra di ripiego di `get_safe_aggregates` si apre sia per eccezione **sia**
  per risposta non utilizzabile, altrimenti ogni ciclo paga un round-trip inutile.
- **L4**: nell'anomalia `decided` non si parla di «scarto» (il `gap` non è uno scarto
  relativo) — test `OpportunityGroup.test.tsx`.
- **L5**: nel tennis «chi serve» si mostra col **nome** del giocatore, non `p1`/`p2`
  (`OpportunityGroup`, stesso file di test).

*(Onestà di tracciamento: gli identificativi di review **M6, M7, M8 e L2** non hanno un
marker proprio nel codice del perimetro Safe — appartengono alla numerazione delle review
di Mike/Omega o sono stati assorbiti dagli item di audit di §12.1. Non vengono attribuiti
qui a un file per non inventare una corrispondenza.)*

**Fix finali della certificazione**
- La regola `ht_open` porta la **sua** etichetta e non si nasconde sotto `decided`
  (`anomaly._emit_decided(..., rule=)` / `_rule_ht_open`, `safeBot.SafeAnomalyRule`,
  `OpportunityGroup` → «Half Time aperto oltre il tempo»).
- Motivi di uscita e di hold in **formato italiano**: `exits._eur()` → `+1,20 €`.
- **Tetto duro del feed 120 s anche in UI**: `safeBot.FEED_HARD_MAX_MS` allineato a
  `exits.FEED_HARD_MAX_S` (test dedicato «soglie di freschezza allineate al servizio»).
- **Debounce realtime 1,2 s**: `useSafeBot.RELOAD_DEBOUNCE_MS`.
- **`payload.kinds` sempre con quattro chiavi** (`model`, `anomaly`, `combo`, `tennis`) su
  ogni sport: `bot_service.process_opportunities` (prima le righe tennis non lo scrivevano
  e quelle calcio non avevano `tennis`: conteggi non confrontabili).
- **`stats.feed_blind` è un CONTATORE**, non un flag (`check_feed_blind` ritorna un int).

### 12.3 CONTRATTO UI (definitivo)

#### `get_safe_state()` → `{control, trades, aggregates, activity, params_effective, operating_day}`
Owner-only (`betfair_live_is_owner`), una sola firma senza argomenti — **mai** aggiungere
un overload con DEFAULT: è l'errore che ha rotto lo storico di Mike.

- `control` = riga `safe_strategy_control` (`status`, `mode`, `params`, `stats`, `error`,
  `heartbeat_at`, …). `control.stats` (scritto da `bot_service.run_once`) contiene:
  `events_total`, `signals_active`, `trades_open`, `open_liability`,
  **`reconciling_liability`**, `realized_today`, `realized_total`, **`won_today`**,
  **`lost_today`**, **`legs_today`**, **`events_today`**, **`feed_blind`** (contatore),
  `last_cycle`, `risk{daily_liability, daily_cap, reconciling_liability,
  loss_stop_active, daily_loss_stop}`, `opps{model, anomaly, combo, tennis}` e
  **`params_effective`** (valori davvero in uso, `bot_service.params_effective`).
- `trades` = ultime 200 righe per `placed_at desc`.
- `aggregates` (`safe_aggregates_sql`, specchio esatto di `bot_db.aggregate_rows`):
  `realized_total`, `realized_today`, `open_liability` (**rischio vivo**, residuo dopo la
  copertura), `open_count`, `reconciling_liability`, `reconciling_count`,
  **`day_liability`** e **`day_liability_model`** (**capitale IMPEGNATO**: base dei cap,
  coprire non libera), `day_trades`, `legs_today`, `events_today`, `won`, `lost`,
  `won_today`, `lost_today`, **`operating_day`** (`YYYY-MM-DD`, Europe/Rome).
- `activity` = ultime 80 righe di `safe_strategy_activity`.
- `operating_day` = `aggregates.operating_day`.

Tipi TS: `lib/safeBot.ts` → `SafeState`, `SafeControl`, `SafeStatsFull`, `SafeRiskStats`,
`SafeParamsEffective`, `SafeAggregates`, `SafeActivityRow`, `SafeTrade`.
`safeBot.aggregatesHaveDay()` distingue la v2 dalla RPC vecchia (§6.2/§6.7).

#### RPC nuove
- **`get_safe_aggregates()`** — owner-only, per il **servizio** (M-29): una scansione
  invece della tabella intera a ogni ciclo. `REVOKE` da `public`/`anon`,
  `GRANT` a `authenticated, service_role`, controllo `betfair_live_is_owner()` **nel
  corpo** (senza, qualunque utente autenticato leggerebbe l'esposizione del conto).
- **`get_safe_activity(p_limit = 100, p_kinds = NULL)`** — owner-only, log filtrabile per
  `kind`, limite clampato in 1…500: la UI non deve leggere 200 trade per vedere 50 righe.
- `safe_aggregates_sql()` resta interna (`GRANT` solo a `service_role`).

#### `safe_strategy_requests`
`status ∈ {pending, processing, done, rejected, error}` — **`rejected`** = richiesta
**RIFIUTATA** dal servizio (non un guasto: in riconciliazione, ordine già a mercato, non
annullabile, mercato sospeso, quote non disponibili). `result` porta **sempre** un
`message` in italiano (`bot_service._request_result`) più, secondo il caso, `ok`, `error`,
`rejected`, `detail`, `reason`, `trade_id`, `closing_trade_id`, `locked_pnl`,
`planned_lock`, `hedge_fraction`, `remaining_liability`, e **`source: 'feed' | 'rest'`**
(da dove venivano le quote usate per chiudere, H5). Senza la migrazione v2 il CHECK del DB
rifiuta `rejected` e `bot_db.set_request_status` ripiega su `error` conservando
`result.rejected = true`. Lettura UI: `safeBot.requestOutcome` →
`{tone: pending|ok|rejected|error, label, message, settled, tradeId, source, sourceLabel}`.

#### Chiavi di `meta` (contratto con la UI)

| chiave | contenuto | letta da |
|---|---|---|
| `exit_kind` | vocabolario **CHIUSO** `exits.EXIT_KINDS` = `greenup, profit, loss, time, red_card, forced, manual, other`. Regola deterministica (`exits.ui_exit_kind`): `manual` → cash out dalla UI; `forced` (o regola `mandatory`) → obbligo/combo; regola di PROFITTO (`profit`/`time`) con chiusura **INTEGRALE** e bloccato ≥ 0 → **`greenup`**; altrimenti `profit`/`time`; `loss`/`red_card` restano; tutto il resto `other` | `ExitBadge`, `dailyHistory.tradeExit`, `SafeTradesTable.safeRowStatus` |
| `exit_reason` | testo italiano dell'uscita (`exits.reason_text`) | riga `safe-exit-reason` |
| `exit` | `{state: retrying \| failed \| waiting_price \| done, kind, reason, attempts, residual_attempts, wait_attempts, last_error, next_retry_at}` | `safeBot.exitRunState`, `SafeTradesTable.exitRunLine` |
| `exit_hold` | `{reason, **code**, kind, exit_reason, p_lose, source, locked, ev_hold, ts}` — `code` = firma senza numeri (M-28) | `safeBot.tradeHold`, riga «In attesa: …» |
| `hedge` | `{fraction, remaining_liability, hedged_size, residual_size, complete}` | `safeBot.hedgeState`, colonna Liability, cash out sul residuo |
| `hedging` | `true` mentre una gamba di chiusura è in volo → **rischio ancora pieno** | `safeBot.hedgeState.inFlight` |
| `position_id` / `position_pnl` / `position_result` | esito della POSIZIONE (`won \| lost \| flat \| void`) su ogni gamba | `safeBot.positionOutcome`, toast unico |
| `error_final` / `error_at` | errore **TERMINALE** (la riga non è più «in corso per sempre») | `safeBot.errorFinal`, stato `ERRORE DEFINITIVO` |
| `place` | `{attempts, last_error, last_ts, next_retry_at, final}` | `safeBot.placeState` |
| `blind_since` | posizione viva che il servizio non vede più nel feed | `safeBot.blindSince`, stato `SENZA FEED da hh:mm` |
| `market_missing_since` | mercato non più leggibile al settlement | `safeBot.blindSince` (stessa riga) |
| `combo_incomplete` | combinazione rotta: il lock non esiste più, il servizio sta svolgendo | `safeBot.comboIncomplete`, stato `COMBO INCOMPLETA: in chiusura` |
| `commission` (colonna) + aliquota sulla **chiusura** | il P&L è tassato con l'aliquota del trade, non col parametro corrente | `safeBot.tradeCommission`, riga della gamba di chiusura |
| `reason` | motivo tecnico (tradotto in italiano da `safeActivity.safeReasonLabel`) | riga `safe-reason` |
| `kind` / `rule` / `combo*` | tipo di opportunità (`model \| anomaly \| combo \| tennis`), regola dell'anomalia, coordinate della gamba di combo — **conservati anche sui piazzamenti manuali** dalle Opportunità (`_request_place`) | `safeBot.tradeOppKind`, badge del tipo, `pLoseEntry` |

#### Attività: TUTTI i `kind` scritti dal servizio
Dal codice (`grep _log(db, …)` su `Betfair/safe_strategy/*.py`), 33 kind propri:
`stop`, `error`, `params_invalid`, `params_clamped`, `place`, `place_pending`,
`place_retry`, `place_exhausted`, `place_exception`, `confirm_failed`, `skip`,
`combo_incomplete`, `reconcile_error`, `reconciled_open`, `reconciled_free`,
`reconciled_error`, `exit`, `exit_hold`, `exit_wait`, `exit_retry`, `exit_failed`,
`cashout`, `cashout_error`, `cancel`, `cancel_rejected`, `settle`, `settle_position`,
`settle_wait`, `settle_error`, `settle_orphan_closing`, `market_missing`, `feed_blind`,
`feed_back`. Più `risk_block` (scritto da `_log_skip(..., kind='risk_block')`) e i kind
della coda condivisa con Omega (`flumine_enqueue`, `flumine_fill`, `flumine_no_fill`,
`flumine_cancel_timeout`, `flumine_recovered`, `flumine_live_freed`,
`flumine_live_orphan`, `flumine_poll_error`). Sono tutti mappati in
`safestrategy/safeActivity.ts:SAFE_ACTIVITY_EXTRA` con etichetta italiana, colore e
`critical: true` dove conta; un kind nuovo va aggiunto **là, con test**.

#### Feed: blocchi dei mercati a gol
`ou[]` (ordinato per linea, ogni voce è un mercato con `market_id`, `line`, `status`,
`selections[]`, `bet_delay`, **`decided`**, **`for_mike`**), `btts`, `ht_result`.
`decided: true` = linea già decisa dal punteggio, tenuta nel feed **solo** per una
posizione Mike: non è un'opportunità e non è un prezzo di uscita.
`for_mike: true` = blocco mantenuto per Mike, non per Safe. Tipi TS:
`lib/safeStrategyScan.ts:ScanMarketBlock` (+ `CalcioScanPayload.ou/btts/ht_result`).
*(Nota storica: `normalizeOppRow` in `lib/safeBot.ts` resta perché il payload delle
opportunità ha due forme, `payload.opportunities` e `payload.opps` — vedi 11/09 pom.)*

### 12.4 Giornata operativa = giorno di PIAZZAMENTO, ovunque
È il principio che tiene insieme i numeri: **KPI, DayBar, pannello Rischio, tab Trade e
Storico attribuiscono una posizione al giorno in cui è stata PIAZZATA** (Europe/Rome), e
una gamba di chiusura appartiene al giorno dell'**apertura** che chiude — un green-up di
mezzanotte non sposta il P&L di ieri sull'oggi. Implementazione:
`safe_aggregates_sql` (`pos_placed_at = coalesce(p.placed_at, o.placed_at)`),
`bot_db.aggregate_rows` (`placed_by_id`/`pos_placed`), `risk.operating_day_start`,
`get_safe_daily`/`get_safe_day_trades` con `p_day_by='placed'`, `pages/SafeStrategy.tsx`
(`operatingDay`, `filterMatchesForDay`), `RiskPanel` (`dayLabel`).

### 12.5 Certificazione sui dati reali
`frontend/vitest.cert.config.ts` + `frontend/src/certification/`: monta le pagine
`/omega`, `/safe-strategy`, `/mike` sui **dati reali** del DB (client con service role,
**solo letture**), cattura `console.error`/`warn` (un crash silenzioso è un KO), un file
per volta, timeout 120 s. I file `.cert.test.*` si **auto-saltano** fuori da questa config
(`env.CERT_RUN`), così `npm test` non interroga mai il DB reale.
File: `safe.cert.test.tsx`, `omega.cert.test.tsx`, `mike.cert.test.tsx`,
`migrations.cert.test.ts`, `realtime.cert.test.ts`.

Ripetibile con:
```
cd frontend && npx vitest run --config vitest.cert.config.ts
```

### 12.6 Numeri delle suite (11/09 sera)
- **Safe Strategy (pytest): 569 test** — nuovi:
  `tests/test_audit_2026_09_11.py` (+1.463 righe), `tests/test_cert_safe_2026_09_11.py`
  (+309), `tests/test_finali_2026_09_11.py`, `tests/test_scanner_mike_followed_c1.py`.
- **Suite dei 3 bot (pytest): 1254 test**.
- **Frontend (vitest): 1642 test** — nuovi per Safe:
  `SafeTradesTable.audit.test.tsx` (+294), `cards.audit.test.tsx`, `safeActivity.test.ts`,
  più `components/trading/designSystem.test.tsx` (+428) e `designGuard.test.ts` (+202) che
  fanno da guardia al design system.

### 12.7 Stato operativo — cosa manca per essere «in linea»
1. 🔴 **Applicare le migrazioni**, nell'ordine di `migrations/APPLY_ORDER_2026-09-11.md`
   (revisione statica già fatta, tutte dichiarate **idempotenti**, nessun dato toccato):
   `mike_bot_v2.sql` → `mike_history_v2.sql` → **`safe_strategy_bot_v2.sql`** →
   `omega_models_v5.sql`. `safe_strategy_bot_v2.sql` va **dopo** `mike_history_v2.sql`
   (lo dichiara la sua intestazione: a quel punto esiste la sola versione a 8/4 argomenti
   delle funzioni condivise). Verifiche dopo l'applicazione:
   ```sql
   select public.get_safe_state();   -- deve avere 'activity' e 'params_effective'
   select public.get_safe_aggregates();
   select status, count(*) from public.safe_strategy_requests group by status;  -- 'rejected' ammesso
   select public.get_safe_daily('2026-09-01','2026-09-12');
   ```
   ⚠️ Avvertenze del file d'ordine: **non** rieseguire `daily_history.sql` o
   `omega_models_v4.sql` da soli (rimettono in vita la firma a 7/3 argomenti e ricreano
   l'overload ambiguo) — se capita, riapplicare subito `mike_history_v2.sql`.
2. 🔁 **Riavviare i servizi**: scanner e bot Safe (`safe_strategy.bot_service`) perché
   rileggano parametri e pubblichino `params_effective`; **riavviare l'app desktop** per la
   UI nuova (l'exe è l'avviatore del `main.js` vivo: **mai** ricompilare).
3. 🔴 **LIVE BLOCCATO**. Prerequisiti: migrazione applicata, giorni di paper con
   settlement e uscite tutte verificate (§9.2 punto 8), certificazione della **liquidità
   lato back** ancora **parziale** (sonda `liquidity_probe` = solo report; usare le
   registrazioni REC), e il gap di fedeltà del paper (bet delay 5 s non simulato, §4).
4. ℹ️ Osservazione di sicurezza segnalata dalla revisione e **non** applicata (fuori dal
   perimetro Safe): `get_mike_aggregates()` in `mike_bot_v2.sql:127-134` è l'unica delle
   tre RPC gemelle senza il controllo `betfair_live_is_owner()` nel corpo — `get_safe_aggregates`
   e `get_omega_aggregates` ce l'hanno.

---

## 13. CHIUSURE, PUNTI APERTI E CONSIGLI (12/09/2026 sera, `cda8e20` + `b267497`)

Analisi completa in `Betfair/CHIUSURE_2026-09-12.md`. Safe è **l'unica delle tre sezioni in
positivo** e le sue chiusure sono risultate corrette: quasi nulla è stato toccato.

### 13.1 Le uscite incondizionate NON sono un difetto (verificato, non cambiate)

Sei uscite per «il lato bancato ha segnato», tutte e sei su lay poi **vincenti**: reale
−20,02 contro +10,08 tenendo. Sembra lo stesso schema che ha affondato Omega e Mike, **ma
non lo è**, e la differenza va scritta qui perché è facile sbagliarsi guardando solo il P&L.

Caso Cesena v US Cremonese: la chiusura ha bloccato **−10,77** dove tenere valeva **−10,72**
al mercato. È un **pareggio**, in cambio del taglio di una coda da **118 € di liability**.
Con un lay che vince circa il 90 % delle volte, sei successi su sei sono esattamente quello
che ci si aspetta: non è un difetto, è la distribuzione.

**NORMA**: prima di dichiarare «difettosa» una chiusura, confrontarla con l'EV **al prezzo di
mercato di quel momento**, non con l'esito realizzato. Chiudere a mercato è neutro per
definizione (vedi §18.1 della costituzione Omega): distrugge valore solo se il modello batte
il mercato. Il senno di poi non è una misura.

### 13.2 Quello che è cambiato (regola condivisa con Omega)

`exits.decide_time_exit` è condivisa: la modifica a `risk_cap` vale anche qui.
Sopra il tetto **non si esce più a qualunque prezzo**, ma solo a un prezzo che vale almeno
`EV(tengo) − ev_margin − premio`, col premio limitato a `risk_premium_pct` (default **5 %**)
della liability. Su un lay la liability è già impegnata all'ingresso: chiudere non riduce il
rischio preso, lo trasforma in una perdita certa. In pratica su Safe questo percorso è raro,
perché quasi tutte le chiusure hanno `locked_pnl ≥ 0` e passano dalla prima regola.

Corretta anche una riga che mentiva: uno scarto con il **lato back assente** veniva
etichettato `spread_anomalo` con rapporto «n/d», cioè una misura mai fatta. Ora è
`book_senza_lato_back`. Due cose diverse non possono avere la stessa etichetta.

### 13.3 Il realtime era MUTO (correzione infrastrutturale)

`subscribeSafeBot` sottoscrive quattro tabelle ma solo due erano pubblicate su
`supabase_realtime`. **`safe_strategy_activity` e `safe_strategy_requests` erano mute dal
giorno in cui il codice è stato scritto**, nonostante il commento dicesse «H-16: il log del
servizio va visto in tempo reale come i trade». Senza publication Postgres non replica nulla:
nessun errore, nessun log, solo aggiornamenti in ritardo di un poll (15 s).

Migrazione `migrations/omega_activity_realtime_2026-09-12.sql`, **applicata e verificata in
diretta** (canale di prova per 60 s: eventi ricevuti; prima sarebbero stati zero).
Il test `Betfair/test_realtime_contratto_2026_09_12.py` lega ora le due cose: ogni tabella
sottoscritta dal TypeScript deve comparire in un `ALTER PUBLICATION` dentro `migrations/`.

### 13.4 Punti aperti

1. **Il profilo di rischio è «monetine davanti al rullo compressore»**, e va tenuto presente
   quando si legge il P&L positivo: 29 aperture vinte su 30 con una **liability media di
   50,47 €** contro incassi di ~2 €. L'unica perdita registrata è stata di **−0,12 €**, cioè
   fortuna, non prova. Le uscite programmate al 72′-73′ sono ciò che tiene in piedi il
   profilo: **non toccarle** senza rifare i conti sulla coda.
2. `model_calibration` resta `off`: il modello di Safe non ha edge dimostrato (backtest
   −18,6 %). Le correzioni rendono le probabilità più oneste, non redditizie. Il backtest va
   rifatto ora che la calibrazione non estrapola e il recupero non produce più segnali.
3. **L'età delle quote PER SINGOLO MERCATO non è pubblicata da nessun servizio.** Quella per
   partita esiste e funziona (`feedFreshness`, soglie 5 s e 20 s; misura dal vivo su 55
   partite: mediana 3,5 s, 90° percentile 15 s, massimo 111 s, il 9 % oltre i 20 s).
   Il payload porta `odds_ts_ms` ma la UI **non lo usa di proposito**: due misure della stessa
   cosa sarebbero due verità diverse sotto gli occhi del trader.

### 13.5 Consigli

1. **Non «correggere» le uscite incondizionate** guardando il P&L realizzato: vedi §13.1.
   Se si vuole cambiarle, il criterio è l'EV al mercato del momento, non l'esito.
2. **Safe è l'unica sezione in positivo**: prima di spostare capitale sulle altre due,
   pretendere da Omega e Mike la stessa cosa che Safe ha già, cioè chiusure che non
   distruggono valore e un profilo di rischio dichiarato.
3. Il tennis resta **mai validato** su serie storiche: tenerlo spento.
