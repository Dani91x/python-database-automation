# Piano — Sezione LIVE come software di trading (livello Bet Angel/Fairbot) su flumine

> Obiettivo: trasformare la sezione live in-play in un vero software di trading sul Betfair
> Exchange, su TUTTI i mercati della partita, back e lay, sfruttando **tutto** ciò che
> flumine 2.13.11 offre nativamente. Esecuzione NON autonoma: ordini solo su comando.
> Doppia modalità con toggle esplicito: PAPER (soldi finti, prezzi live) e LIVE (reale).
>
> Path PRE-MATCH (`Betfair/order_exec.py`) = INVARIATO. Tutto il nuovo vive nel processo del
> runner stream (`Betfair/stream/`).

## ⏱️ STATO AVANZAMENTO (aggiornato 2026-06-30) — PARTIRE DA QUI DOMANI

### ✅ FATTO e su master
- **Fase 1 — Foundation** (commit 9b4cdd2 / e43299b / 7d87787 / 4d25ac1): place/cancel/replace
  tutti i mercati back+lay, toggle `LIVE_ORDER_MODE` via `.env`, coda DB + RPC owner-only,
  worker nel runner (claim atomico, kill-switch+cap runtime), validazione/tick, place-and-trim
  `.it`, specchio ordini+posizioni (da `blotter.get_exposures`), controlli nativi flumine,
  pannelli `LiveTradingPanel`+`PlacedOrdersPanel`. PAPER E2E funzionante.
- **Ladder Step 1+2** (commit 1559901): pipeline realtime `live_ladder` (runner `ladder_worker`
  dallo stream già sottoscritto, ZERO API extra, write-on-change, cadenza 2.0s) + UI `LadderView`
  8 colonne, WOM, colori standard (BACK=blu/LAY=rosa). Migrazione `migrations/live_ladder.sql` applicata.
- **Ⓐ One-click + Ⓑ Green-up/Cash-out** (commit 074cd0c): one-click place/cancel mode-aware (OFF/
  PAPER/LIVE + arm "1-click"), colonna PIQ; green-up totale+parziale calcolato dalle esposizioni
  MATCHED reali di flumine (`trading/greenup.py`), preview al prezzo di esecuzione reale.
  Migrazione `migrations/betfair_live_greenup.sql` applicata. 295 pytest + 236 vitest + tsc OK,
  review code+database recepita.

### 🔜 DA FARE DOMANI (ordine consigliato)
1. **Fase 3 — Risk engine** (§9) ← **INIZIARE DA QUI**
   - `Betfair/stream/trading/risk_engine.py` (worker): **Offset** (al fill piazza opposto a N tick,
     `price_ticks_away`), **Stop-loss/Take-profit** (soglie P&L o prezzo → chiusura/green-up),
     **Trailing stop** (soglia che insegue il prezzo). Riusa coda + `greenup.py` già costruiti.
   - config per-ordine in `params jsonb` (azione `stoploss_set`) + migrazione coda; bottoni UI.
2. **Fase 5 — Dutching & Hedging** (§10): `trading/dutching.py` (stake su N selezioni, profitto/
   liability uguale) + `trading/hedging.py` (mercati correlati) + azione `dutch` + bottoni UI.
3. **Fase 6 — Controlli avanzati / audit / velocità** (§11–§12):
   - trading_controls CUSTOM (max esposizione per selezione/mercato + rate-limit ordini/min);
   - **kill-switch dalla UI** (oggi solo env `LIVE_KILL_SWITCH`);
   - **audit log** DB di ogni comando/ordine; **pannello impostazioni velocità** UI;
   - verifica restart framework LIVE (`create_order_from_current`).
4. **Rifiniture UI** (§13): pannello **posizioni/P&L dedicato** (da `betfair_live_positions`);
   **cancel/replace inline** in `PlacedOrdersPanel`; **replace via drag** sul ladder.

### 🔒 A CARICO UTENTE (soldi veri — non Claude)
- E2E PAPER di green-up + one-click su partita vera; **test empirico place-and-trim .it**;
  **cert LIVE minimale** (stake minimo per ogni azione: place/cancel/replace/green-up).

### ❓ DECISIONI APERTE
- Persistenza in-play di default (oggi `LAPSE`) → confermare `LAPSE` vs `PERSIST`.
- Stake/preset/cap di default (oggi cap €10, preset 2/5/10/25).

### ⚠️ LIMITI NOTI da rifinire
- Green-up chiude solo la posizione **MATCHED**: gli ordini non abbinati NON sono auto-cancellati
  prima dell'hedge (un vero "cash out" li cancella prima) → cancellali col one-click, poi green-up.
  Valutare un "cash-out completo" = cancel-all + hedge.
- Green-up al best opposto con `LAPSE`: se il book è sottile l'hedge può abbinarsi in parte e il
  resto lapsa (riclicca). Possibile versione più aggressiva (cross dello spread) in futuro.
- Ladder passa `handicap=0` (OK MATCH_ODDS/O-U/BTTS; estendere per handicap asiatici).
- TODO separato: riconciliazione P&L/chiusura ordini **pre-match** via `listCurrentOrders`/`listClearedOrders`.

---

## 0. Principi
- **Riusare flumine, non reinventare.** Usiamo: modello ordini (Trade/BetfairOrder/LimitOrder),
  `market.place_order/cancel_order/replace_order/update_order`, **order stream** (fill reali),
  **blotter** (posizioni), **matematica esposizione** (`utils.calculate_matched_exposure`,
  `calculate_unmatched_exposure`, `wap`; `blotter.get_exposures/selection_exposure/market_exposure`),
  **ladder tick** (`utils.get_nearest_price`, `price_ticks_away`, `PRICES_FLOAT`),
  **esecuzione simulata** (`paper_trade=True`), **controlli** (`min_bet_validation`,
  `transaction_limit`, `trading_controls`).
- **Money-critical.** Ogni ordine combacia esattamente con market_id+selection_id reali
  (nessuna mappa hardcoded — i dati vengono dal catalogo già sottoscritto). Validazione tick,
  size/liability, stake minimo, regola payout/rounding, cap.
- **Toggle esplicito** `LIVE_ORDER_MODE ∈ {OFF, PAPER, LIVE}` (default OFF). Badge UI
  PAPER / 🔴 LIVE REALE. Passaggio a LIVE solo con env dichiarata.
- **Velocità regolabile per-modalità** (LIVE veloce, PAPER rilassato).
- **Jurisdiction-aware** (.it vs .com) per la regola dello stake minimo.

## 1. Stake minimo e sotto-minimo (regole Betfair, da rispettare)
Regole documentate:
- **.com/UK ecc.**: minimo £2/€2. **Minimum Bet Payout**: stake piccolo valido se payout
  (stake×quota) ≥ £10/€20 (es. £1@10).
- **Italian Exchange (.it)** (doc ufficiale Betfair): **back min €2,00, incrementi €0,50**;
  **lay**: la puntata corrispondente (size del lay) può scendere fino a **€0,50**; **Minimum Bet
  Payout NON disponibile**; max vincita €10.000 (incl. stake); placeOrders ≤ 50 istruzioni; vietato
  mischiare back+lay nello stesso ordine.
- **Sotto-minimo per riduzione liability** (green-up/hedge): permesso, soggetto alla regola
  anti-rounding (rifiuto `INVALID_PROFIT_RATIO` se ritorni −20%/+25% del dovuto).
- Helper `min_stake_rules(jurisdiction, side, price, size, reduces_liability)` → valido/non valido
  + motivo + size legalizzata (arrotondamento a incremento per .it). Config `BETFAIR_JURISDICTION` (it|com).

## 1bis. Sotto-minimo "place-and-trim" (come Bet Angel/Geeks Toy)
Tecnica per piazzare size < minimo (sfrutta che il minimo è controllato solo al `placeOrders`
iniziale, non su cancel/replace). **flumine la supporta nativamente** (place + cancel size_reduction
+ replace):
1. `place_order` size = minimo (€2) a quota non abbinabile (BACK→1000, LAY→1.01), persistence LAPSE.
2. atteso `EXECUTABLE` con bet_id e size_remaining pieno → `cancel_order(size_reduction = min − target)`
   → resta `target` (es. €0,57) non abbinato.
3. `replace_order(new_price = quota_target)` → sposta il piccolo ordine alla quota voluta.
- Modulo `Betfair/stream/trading/submin.py` orchestrato dal worker (azione `place_submin`), macchina
  a stati idempotente (riprende se interrotto), con **guardia rischio**: se lo step 1 si abbina a 1000
  → stop+alert (mai ripetere). Mitigazione: quota estrema = match quasi impossibile.
- **Jurisdiction-aware**: su .com applica Min Bet Payout prima di ricorrere al trim; su .it il trim è
  da **verificare empiricamente** (la doc tace; il lay €0,50 è invece diretto). Vedi §Verifica.

## 2. Toggle modalità & client flumine
- `config_stream.py`: `LIVE_ORDER_MODE`, `BETFAIR_JURISDICTION`, e parametri velocità per-modalità.
- In `runner.setup_and_run`, costruzione client per modalità:
  - OFF → `BetfairClient(api_client, order_stream=False)` (= comportamento attuale, zero regressioni).
  - PAPER → `paper_trade=True` (SimulatedExecution su dati live).
  - LIVE → `order_stream=True` (fill reali via order stream).
- Log cubitale all'avvio + scrittura modalità in `live_now`/alert → badge UI.
- **Verifica preliminare**: wiring `paper_trade`/SimulatedExecution con stream live (baseflumine).

## 3. Strategia di trading (advisory, no auto)
- `Betfair/stream/engine/live_trading_strategy.py` → `LiveTradingStrategy(BaseStrategy)`:
  - `process_market_book` = **NO-OP** (nessun ordine automatico).
  - `process_orders(market, orders)` = hook per **specchiare** gli ordini nel DB (write-on-change).
  - Convive con `MarketRecorderStrategy`. market_filter = stessi market_id (tutti i mercati).

## 4. Coda comandi DB (place/cancel/replace + bulk)
- Migrazione `migrations/betfair_live_order_queue.sql`:
  - tabella `betfair_live_order_requests`: `id, client_ref UNIQUE, action(place|cancel|replace|greenup|dutch|stoploss_set), mode(paper|live), market_id, selection_id, handicap, side, order_type(LIMIT|LOC|MOC), price, size, liability, persistence(LAPSE|PERSIST|MARKET_ON_CLOSE), time_in_force(FILL_OR_KILL|null), min_fill_size, bet_id, new_price, size_reduction, params jsonb, status, result jsonb, error, requested_at, processed_at`.
  - RPC `request_betfair_live_order(jsonb)` (idempotente su client_ref) + `get_betfair_live_order(id)`; grant/RLS come le altre code.
- Idempotenza + de-dup (customerRef deterministico).

## 5. Worker dentro il runner
- `Betfair/stream/live_order_worker.py` → `BackgroundWorker` aggiunto al framework (come `score_worker`), poll ~1–2s (config per-modalità):
  - risolve `Market` da `framework.markets.markets[market_id]` (già sottoscritto = tutti i mercati);
  - **place**: valida (helper §6) → `Trade`+`BetfairOrder` → `market.place_order(order, market_version=…, customer_strategy_ref='live')`;
  - **cancel/replace**: trova l'ordine per `bet_id` nel blotter → `market.cancel_order`/`replace_order`;
  - scrive esito nella riga; fill (size_matched/avg_price) arrivano async dallo stream → aggiornati nello specchio (§7).
- Sicurezza: claim atomico, cap, kill-switch, `transaction_limit`.

## 6. Helper build + validazione (blindato)
- `Betfair/stream/live_order_build.py`:
  - prezzo → `utils.get_nearest_price` (tick valido); offset via `utils.price_ticks_away`.
  - LAY: `size = liability/(price−1)`; BACK: size diretto. Arrotondamento 2 decimali.
  - validazione: side, tick, **min_stake_rules** (§1), FoK vs persistenza, cap `max_stake`.
  - costruzione `LimitOrder`/`LimitOnClose`/`MarketOnClose` + `BetfairOrder`.
- Unit test esaustivi (tick, lay/liability, jurisdiction, payout/rounding, FoK, caps).

## 7. Specchio ordini & posizioni per la UI
- `betfair_live_orders` (write-on-change da `process_orders`): bet_id, market, selection, side, price, size, size_matched, size_remaining, avg_price, status, persistence, mode, ts.
- `betfair_live_positions` (da `blotter.get_exposures` per selezione): matched_if_win/lose, worst_on_win/lose, net position, P&L corrente, mode.
- RPC di lettura per il frontend; aggiornamento periodico nel runner.

## 8. Green-up / Cash-out (totale + parziale)
- `Betfair/stream/trading/greenup.py`: dalle esposizioni blotter calcola lo stake opposto al
  prezzo corrente che **pareggia** profit-se-vince/perde (totale) o una frazione (slider %).
  Rispetta `min_stake_rules` (riduzione liability). Emissione ordine via coda (action `greenup`).
- Test su scenari (back→lay green, lay→back, parziale 50%, a quote variate).

## 9. Stop-loss / Take-profit / Trailing / Offset
- `Betfair/stream/trading/risk_engine.py` (worker): per ordine/mercato monitora P&L/prezzo e
  scatena azioni:
  - **Offset**: al fill, piazza ordine opposto a N tick (`price_ticks_away`).
  - **Stop-loss / Take-profit**: soglie su P&L o prezzo → green-up/chiusura.
  - **Trailing stop**: soglia che segue il prezzo a favore.
- Config per ordine (in `params jsonb`); attivo solo se l'utente lo imposta. Mai autonomo oltre le regole impostate.

## 10. Dutching & Hedging
- `Betfair/stream/trading/dutching.py`: ripartisce uno stake totale su N selezioni per profitto
  uguale (back) o liability uguale (lay). Output = lista ordini.
- `hedging.py`: copertura tra mercati correlati (es. O/U vs CS) dalle esposizioni.

## 11. Sicurezza & controlli
- `trading_controls` flumine + controlli custom: max esposizione per selezione/mercato, max
  ordini/min (rate), max stake per ordine, **kill-switch** globale (blocca tutti i place),
  guardia `INVALID_PROFIT_RATIO`. `min_bet_validation=True`.
- **Controlli NATIVI flumine cablati (FIX 6)**: in `runner.build_order_client` su tutte e 3 le
  modalità (OFF/PAPER/LIVE) il client flumine è costruito con `min_bet_validation=True`
  (control nativo `OrderValidation`) e `transaction_limit=LIVE_TRANSACTION_LIMIT`
  (control nativo `MaxTransactionCount`, default 1000/h, sotto la soglia Betfair di 5000/h).
  In OFF sono inerti (nessun place possibile) → zero regressioni.
- **RINVIATO a Fase 6** (non nativo, non triviale → non improvvisato ora): i `trading_controls`
  custom di **max esposizione per selezione/mercato** e di **rate-limit ordini/min**. Vanno
  implementati come `BaseControl` custom (`StrategyExposure` è basato su `Strategy.max_*`, qui
  serve un control proprio agganciato allo specchio posizioni) e registrati via
  `framework.add_trading_control(...)`. Deferral tracciato qui per non essere silenzioso.
- **Audit log** di ogni comando/ordine (chi, cosa, modalità, esito) in DB.
- Gestione restart framework (F3): in LIVE l'order stream ri-sincronizza gli ordini aperti
  (`create_order_from_current`); in PAPER stato in-memory (documentato).

## 12. Velocità (regolabile, per-modalità)
- Prezzi: `STREAM_CONFLATE_MS` (0 = max velocità) + `LADDER_DEPTH`.
- Ordini: `order_stream_conflate_ms`, `order_streaming_timeout` (0.25s).
- Poll worker coda. Preset LIVE (veloce) vs PAPER (rilassato), tutti settabili da config e UI.

## 13. Frontend — la UI da trading software (`frontend/src/pages` + components)
- **Ladder per selezione**: prezzi + volume tradato (`trd`) + WOM (weight of money dalle size) +
  i tuoi ordini sui livelli; **one-click** back/lay; stake preset e default.
- **Pannello posizioni/P&L** per selezione e mercato, live.
- **Order book personale**: pending/matched/cancelled; cancel/replace inline.
- **Bottoni trading**: Green-up (full + slider parziale), Stop-loss/Take-profit, Offset, Dutching, Hedge.
- **Multi-mercato**: tab per tutti i mercati della partita.
- **Badge modalità** PAPER / 🔴 LIVE, **kill-switch**, pannello impostazioni velocità.

## Fasi (ognuna: TDD → E2E paper → cert live minimale)
1. **Foundation**: toggle+client, `LiveTradingStrategy`, coda+RPC, worker, build/validazione,
   **place/cancel/replace**, specchio ordini, UI minima (order entry + lista ordini + posizioni).
2. **Posizioni & Green-up/Cash-out** (full + parziale).
3. **Risk engine**: stop-loss / take-profit / trailing / offset.
4. **Ladder UI** one-click + WOM + multi-mercato.
5. **Dutching & Hedging**.
6. **Controlli avanzati, audit, kill-switch, tuning velocità**.

## Protocollo di verifica & validità matematica (per OGNI sezione)
Nessuna sezione si considera "fatta" senza:
1. **Unit test** (TDD, ≥80% copertura) sulla logica pura: tick, lay/liability, min_stake_rules,
   place-and-trim (macchina a stati), green-up, dutching, stop-loss/offset.
2. **Validità matematica provata**: green-up pareggia profit-se-vince/perde entro 1 cent;
   dutching → stesso profitto su tutte le selezioni; esposizioni riconciliate contro
   `blotter.get_exposures` di flumine (non ricalcolate a mano).
3. **Riconciliazione fill reali**: size_matched/avg_price/P&L letti dall'order stream coincidono
   con la dashboard (specchio DB) e col conto Betfair (cleared orders).
4. **E2E in PAPER** su partita vera (prezzi live, soldi finti) per ogni funzione.
5. **Cert LIVE minimale**: una prova reale con stake minimo per ogni azione critica, incluso il
   **test empirico place-and-trim sul conto reale** (la prova definitiva per .it).
6. **UI chiara**: ogni numero in UI ha una fonte tracciabile (specchio DB ↔ flumine), badge
   modalità sempre visibile, nessun valore "stimato" spacciato per reale.

## Fasi (ognuna chiusa dal Protocollo di verifica sopra)
- Fase 1 = foundation (place/cancel/replace, tutti i mercati, specchio, UI minima) + modulo
  place-and-trim con test empirico .it.

## Aperto / da confermare
- **Giurisdizione conto: .it o .com** → determina le regole sotto-minimo (§1) e il test place-and-trim.
- Default persistenza in-play (LAPSE vs PERSIST).
- Stake/preset di default e cap iniziali.
