# FASE C.9 — Backtest Scalper Calcio + 4 bot Tennis: stesso codice o copia?

> Sola lettura. Fonti: `PIANO_CERTIFICAZIONE_DEFINITIVA_2026-09-16.md` (§0, §5.8, C.9), `Betfair/stream/scalper/SCALPER_BOT_DOSSIER.md` + `SCALPER_CALCIO_DOSSIER.md` (radice, avviso 17/07), `BIBBIA_SCALPER_CALCIO.md`, `BIBBIA_SCALPER_TENNIS.md`, memorie `project_calcio_scalper_lab_2026-07-07`, `project_theta_cecchino_2026-07-16`, `project_tennis_1tick_bibbia_2026-07-10`, `project_missione_2tick_bots_2026-07-10`. Riferimenti `file:riga` letti nel codice attuale.

## Architettura generale (verificato)
Scalper calcio + i 4 bot tennis (`tennis_scalper/tennis_pro/tennis_flb/tennis_swing`) sono **fuori dal "banco comune"** che Fase C.0 costruisce per Mike/Omega/Safe (`Betfair/stream/backtest/banco_comune.py`, non importato da nessuno di questi 7 bot). Hanno un harness proprio, più vecchio, su `flumine.FlumineSimulation` + `SimulatedMiddleware`, senza passare da `safe_strategy.service.Scanner`/`safe_strategy_scan`. `run_backtest.py` + `sim_strategy.py` (citati dal piano §5.8) sono in realtà il backtest di **`live_engine_pro`/`SimStrategy`** (`sim_strategy.py:38,100`), motore DIVERSO: gli harness veri sono `run_scalper.py`/`run_theta.py`, che ne importano solo `aggregate_results` come metrica (`run_scalper.py:24`, `run_theta.py:37`).

## CALCIO 1. `scalper_bot.py` → `ScalperStrategy` (maker pre-match/in-play)
**Verificato**: produzione istanzia `ScalperStrategy` (`scalper_bot.py:202`) in `scalper_session.py:613` (import riga 476). `run_scalper.py` importa la STESSA classe (riga 26) e la istanzia riga 80 — nessuna copia. `run_scalper_live.py:32/233` idem.
**Come**: FlumineSimulation su `_live_raw/<event>/<event>.raw.jsonl`, `simulation_available_prices=False` (fill conservativi, coda reale, righe 60-62), betDelay letto dal raw da flumine, nessun delay a mano. `order.status` = Enum `OrderStatus` (`scalper_bot.py:2274,2285`), non stringa. Nessun FOK (solo `LimitOrder`). Price-driven, no score.
**Differenza**: tetti flumine APERTI nel backtest — `max_selection/order_exposure`=1.000.000€ fissi, `max_trade/live_trade_count`=1e9 (`run_scalper.py:83-86`) contro cap da stake (`cap=stake*(price_max-1)*2.0`, `scalper_session.py:608-609`) e 1e6 in produzione (riga 620-621).
**Copia stantia non in uso**: `scalper_lab/scalper_bot_base.py` (dichiarata COPIA da `scalper_lab/__init__.py:3,6`), usata solo da `scalper_lab/bt_lab.py:36`, mai da `run_scalper.py`.
**Risultato**: soldi veri 10/07 sera (Spagna-Belgio, bibbia §12): 7 cicli iniziali a 0,00€ (scratch), poi missione sniper compiuta (v. sotto); bilancio serata precedente ≈ −4,7€. Numeri "certificati" ms300 (§4 bibbia, +0,93) poggiano in parte su 2/12 eventi poi RICLASSIFICATI **PARTIAL** dal validatore registrazioni (avviso 17/07 in `SCALPER_CALCIO_DOSSIER.md`): 35765620 (59,2%) e 35768297 (80,3%) — non ricertificati.
**Non verificato**: nessuna evidenza di rilancio dopo il 17/07 (mtime `scalper_bot.py` 16/07, `run_scalper.py` 17/07); non ho rieseguito nulla io stesso (mandato sola lettura).

## CALCIO 2. `sniper_bot.py` → `SniperStrategy` (S16 in-play)
**Verificato**: produzione istanzia in `scalper_session.py:628` (import riga 625, classe `sniper_bot.py:76`). **Non esiste alcun harness FlumineSimulation nel repo che istanzi `SniperStrategy` su registrazioni reali.** Uniche istanziazioni fuori produzione: 4 test unitari su book sintetici (`test_sniper_bot_2026_07_10.py:78`, `test_scalper_pnl_settled_2026_07_16.py:47,63`, `test_risk_semaphore_2026_07_11.py:71`, `test_theta_bot_2026_07_15.py:542,562`).
**Come "L'Atlante" (`scalper/tools/atlas_v0.py`) funge da backtest, ma È UNA COPIA**: non importa `sniper_bot.py`, usa un parser proprio (`mcm.py`) e reimplementa a mano i 3 gate S16 + il fill (traded dimezzato, righe 193-199), delay **hardcoded** 5.120ms (riga 36) invece del betDelay letto dal raw da flumine. Nessun FlumineSimulation, nessun `order.status`.
**Punteggio**: in produzione il watcher `scalper_session.py:884-907` legge `live_now` e chiama `sniper.set_line/set_lines` (`sniper_bot.py:184,204`); l'Atlante ricostruisce la linea per conto proprio, senza passare da `set_line`.
**Risultato**: demo dry-run live 10/07 (CSL, 3 trigger perfetti, bibbia §6.5); soldi veri 10/07 sera, "missione compiuta" +0,032€ (§12.1); Atlante v0 rigenerato 11/07 (28.310 momenti/12 partite, §6.7).
**Non verificato**: se l'Atlante coincide col codice ATTUALE (multi-colpo/multi-linea F4a/b, risk manager F5, esecuzione .it exact_exits/submin — nessuno è nel replay). Nessuna certificazione flumine end-to-end su partite intere; nessuna rigenerazione dopo l'11/07.

## CALCIO 3. `theta_bot.py` → `ThetaStrategy` (Under gol+N, in-play)
**Verificato**: `ThetaStrategy(SniperStrategy)` (`theta_bot.py:421`). Produzione istanzia in `scalper_session.py:719` (import riga 677). `run_theta.py` importa la STESSA classe (riga 40) e la istanzia riga 122 — harness dedicato, non condiviso con `run_backtest.py`.
**Come**: `set_goals()` (`theta_bot.py:579`) è il PUNTO UNICO di aggiornamento punteggio, usato sia dal watcher live (legge `live_now`, dichiarato nel docstring riga 580) sia dal replay (`_advance_timeline`, righe 592-600, da `scores_timeline` costruito da `_load_scores` in `run_theta.py:37,89`) — stessa funzione, sorgente diversa, NESSUNA duplicazione di logica. `risk_sem` (`EventRiskSemaphore`, cooldown 120s) ricostruito identico (`run_theta.py:132-134`).
**Differenze (stessa classe, config diversa)**: protezioni solo-live spente nel backtest (`exact_exits/size_step/live_min_bet/confirm_mode`=0/False, righe 58-62) contro `exact_exits=True/size_step=0.5/live_min_bet=2.0` in produzione (`scalper_session.py:705-707`); tetti APERTI (1.000.000€+1e9, righe 126-129) contro `theta_stake*4.0`+1e6 (`scalper_session.py:726-729`).
**Copia stantia non in uso**: `scalper_lab/theta_strategy.py` (propria classe, riga 59, NON eredita da SniperStrategy), usata solo da `scalper_lab/bt_theta.py:27`.
**`order.status`**: eredita l'Enum-check di `SniperStrategy` (`sniper_bot.py:932,941-942`); i confronti a stringa in `theta_bot.py:362,396,404` (`p.status=="awaiting"`) sono sullo stato INTERNO della posizione, non su `order.status` flumine — non è il baco Enum/stringa cercato.
**Risultato**: preset "cecchino" 16/07 (commit 1c64426), backtest 26 raw POST-FIX: 0 divergenze ledger, prematch 7 ingressi→5 green+2 timeout, 21 green totali, pnl −20,95 (di cui −14,57 un solo gol). Paper osservato dal vivo 16/07 pomeriggio su 2 partite.
**Non verificato**: nessuna run successiva al 16/07 (mtime `theta_bot.py` 16/07 13:23); checklist F6 "certificazione paper" (bibbia §13) non risulta chiusa.

## TENNIS (4 bot legacy, `tennis_runner.py`) — meccanismo comune
**Verificato**: `_BOT_REGISTRY` (`tennis_runner.py:92-96`) mappa `tennis_scalper→TennisScalperStrategy`, `tennis_pro→TennisProStrategy`, `tennis_flb→TennisFLBStrategy`, `tennis_swing→TennisSwingStrategy` (import righe 50-58); istanziazione generica `_instantiate_bot` (riga 545), `strat=cls(**kwargs)` riga 613. Punteggio: `strat.score = ts` (riga 1065), `ts` da `ScanFeedScoreProvider` (feed unico dello scanner Safe Strategy, stato IPS) con fallback a `in_play_service.get_scores` diretto (righe 1030-1055) — IPS in entrambi i casi.

## TENNIS 4. `tennis_scalper` → `TennisScalperStrategy`
**Verificato**: classe `tennis_scalper_bot.py:218`. `tune_tennis.py` importa la STESSA classe (riga 26) e la istanzia diretta (riga 52). NON usata da `validate.py` (v. sotto) né da `backtest_pro.py`/`flb_backtest.py`.
**Come**: FlumineSimulation, `simulation_available_prices=False` (riga 35), price-only. `size_step=0.0, live_min_bet=0.0` forzati sia nel backtest (riga 47) sia in produzione quando NON live (`tennis_runner.py:592-596`) — qui COINCIDONO per scelta esplicita.
**Differenza**: tetti aperti nel backtest (1.000.000€+1e9, `tune_tennis.py:29,53-56`) contro cap da stake in produzione (`cap=stake*(price_max+2)*3`, `tennis_runner.py:598`).
**Risultato**: bibbia tennis §4 (11/07): pre-match +0,11/+0,18 su 2 eventi liquidi; in-play maker −66,46€/34 ordini → NO-GO strutturale, produzione già allineata (`inplay_tick_enabled: off`).
**Non verificato**: nessuna rigenerazione dopo il 17/07 (mtime); registrazioni tennis ferme al 07/07 (`Desktop/tennis_rec/20260707`), nessuna cartella più recente sul disco.

## TENNIS 5. `tennis_pro` → `TennisProStrategy`
**Verificato**: classe `tennis_pro_bot.py:71`. `backtest_pro.py` definisce `BacktestProStrategy(TennisProStrategy)` (riga 35) — sottoclasse che overrida SOLO `set_timeline`/`process_market_book` (iniezione punteggio da timeline registrata, righe 39-52) e `process_closed_market` (somma P&L settlement, righe 54-60): **nessun override di entrata/uscita/gate** → sostanzialmente la STESSA classe.
**Come**: punteggio sullo stesso attributo `.score` della produzione (`self.score=tl[self._ti][1]`, riga 51) da `.score.jsonl` allineato al `publish_time_epoch` — stesso meccanismo di `tennis_runner.py:1065`, sorgente diversa.
**Differenza**: tetto aperto (1.000.000€, righe 32,126-127) contro cap da stake in produzione; `min_matched` default backtest 10.000€ (riga 111) — NON verificato se coincide col default di produzione.
**Risultato**: bibbia tennis §4 (10/07): 1 evento con fill, −0,20€, "quasi mai fill, e perde".
**Non verificato**: `backtest_pro.py` fermo al 06/07, `tennis_pro_bot.py` modificato il 17/07 — un fix successivo NON risulta ri-testato con questo harness.

## TENNIS 6. `tennis_flb` → `TennisFLBStrategy`
**Verificato**: classe `tennis_flb_bot.py:46`. `flb_backtest.py` importa la STESSA classe diretta (riga 27) e la istanzia senza sottoclassi (riga 38, in `_make_strategy`).
**Come**: FlumineSimulation+`SimulatedMiddleware`, `simulation_available_prices=False` (riga 50); price-only, nessuno score necessario (commento righe 76-78).
**Differenza**: tetto aperto (1.000.000€, righe 29,33-36).
**Risultato**: bibbia tennis §4 (11/07): FLB lay≤1,05/1,10 hold/hybrid, tutte negative su 3-4 eventi (−0,30/−0,68/−0,52), "0 crolli su 4 lay" — né promossa né chiusa, serve n≥50.
**Non verificato**: campione mai cresciuto oltre 4 eventi (nessuna nuova registrazione dopo il 07/07); file fermi al 17/07 (harness) / 16/07 (bot).

## TENNIS 7. `tennis_swing` → `TennisSwingStrategy`
**Verificato**: classe `tennis_swing_bot.py:44`, testata da DUE strumenti con la STESSA classe: (a) `flb_backtest.py:41` (kind="swing", import riga 40); (b) `validate.py:31,53` (`_run_swing`, righe 42-58).
**Differenza di CONFIGURAZIONE (non di classe) in `validate.py`**: `SWING_GRID` usa gate liquidità volutamente APERTO rispetto ai default di produzione — dichiarato nel commento righe 33-34 ("gate APERTO... per vedere se ha segnale"), `min_matched=2000.0, price_min=1.01, price_max=8.0` (riga 38) al posto dei default. Il numero che ne esce **non rappresenta** il bot come configurato in produzione.
**Risultato**: bibbia tennis §4 (11/07): Swing z2.0 maker/taker, −10,19/−7,05€ su 2-4 eventi.
**Non verificato**: se `validate.py` sia mai stato rieseguito dopo l'11/07 (nessun `_validation.json` più recente trovato); tetti aperti come sopra in entrambi gli strumenti.

## `TennisLabStrategy` (`tennis_lab.py`) — copia usata da `validate.py`/`lab_grid*`
**Verificato**: `tennis_lab.py:40` definisce `TennisLabStrategy(BaseStrategy)`, motore di RICERCA separato — NON è uno dei 4 bot in `_BOT_REGISTRY`, riusa solo `compute_green`/`ticks_between` da `tennis_scalper_bot.py` ma ha logica propria. `validate.py` usa `TennisLabStrategy`/`ScoreConditionedLab` per le colonne "P:"/"S:" — **queste NON certificano nessuno dei 4 bot di produzione**, solo "SW:" usa la classe vera (Swing). Bug noti in bibbia §1: doppio delay con `bet_delay_ms="auto"`, etichette maker/taker invertite (righe ~271-279) — copia da non fidarsi se non con `bet_delay_ms=0`.

## Checklist trasversali
- **Tetti flumine** (`max_live_trade_count`, `max_order_exposure`, `max_selection_exposure`): APERTI (1.000.000€ + trade/live_count=1e9) in TUTTI gli harness verificati (`run_scalper.py`, `run_theta.py`, `backtest_pro.py`, `flb_backtest.py`, `validate.py`, `tune_tennis.py`) contro cap legati allo stake in produzione (1e6) — nessuna eccezione.
- **`order.status`**: Enum `OrderStatus` (non `.value`, non stringa) in tutte le classi di produzione verificate. Gli unici confronti a stringa trovati (`theta_bot.py:362,396,404`, `atlas_v0.py:138`) sono su stati interni diversi da `order.status` flumine — non è il baco.
- **FOK**: nessuno dei 7 bot lo usa — solo `LimitOrder`. Non applicabile a questa famiglia.
- **BetDelay**: mai a mano nei backtest verificati; flumine lo applica dal `marketDefinition` del raw. Eccezione NON in uso dai 4 bot: `tennis_lab.py` (`bet_delay_ms="auto"` = doppio delay, bug bibbia §1).
- **Punteggi/gol**: calcio via `live_now` (tabella DB) letta da watcher in `scalper_session.py`; tennis via `ScanFeedScoreProvider`/IPS in `tennis_runner.py`. Nessuno passa da `safe_strategy_scan`. Il backtest ricostruisce fedelmente lo stesso attributo/funzione (`.score`, `set_goals`) per theta e tennis_pro; NON per lo sniper (Atlante = copia).

## Sintesi per il coordinatore
1. Scalper calcio e i 4 bot tennis **non passano dal banco comune** (C.0): harness flumine proprio, indipendente da scanner Safe/`safe_strategy_scan`.
2. `scalper_bot.py`(maker) e `theta_bot.py`: backtest ufficiale = STESSA classe, stesso codice — nessuna copia in uso.
3. `sniper_bot.py`: **nessun backtest flumine reale esiste**. L'Atlante è una reimplementazione manuale (fill a mano, delay hardcoded) che NON esegue il codice attuale (multi-colpo/multi-linea/risk manager F4-F5 esclusi).
4. `tennis_scalper`/`tennis_flb`: backtest sulla stessa classe (`tune_tennis.py`, `flb_backtest.py`) — nessuna copia.
5. `tennis_pro`: backtest è sottoclasse minima (solo iniezione punteggio/telemetria), nessuna logica di trading riscritta — praticamente la stessa classe.
6. `tennis_swing`: stessa classe in due harness, ma `validate.py` la testa con gate liquidità deliberatamente aperto vs produzione — quel numero non è rappresentativo.
7. `validate.py` ("P:"/"S:") e `lab_grid*.py` testano `TennisLabStrategy`, motore di ricerca SEPARATO, non uno dei 4 bot armabili — copia, non produzione.
8. Copie stantie non in uso dai backtest ufficiali: `scalper_lab/*` (maker e theta), `tennis_lab.py`/`tennis_lab_score.py` (bug noti: doppio delay, etichette invertite).
9. Tetti flumine sempre APERTI nei backtest vs cap legati allo stake in produzione (tutti e 7 i bot); `order.status` sempre Enum, mai stringa; nessuno dei 7 bot usa FOK.
10. Punteggi: calcio da `live_now` (DB), tennis da IPS/`ScanFeedScoreProvider` — mai da `safe_strategy_scan`; ricostruiti fedelmente per theta e tennis_pro, NON per lo sniper.
11. Nessun bot/backtest ha attività dopo il 16-17/07/2026 (mtime codice); registrazioni tennis ferme al 07/07, quelle calcio crescono (`_live_raw` fino al 14/09) ma non risultano usate da questi harness da luglio.
12. Reperto: 2 eventi usati per certificare "min_size=300" nello scalper maker sono stati RICLASSIFICATI **PARTIAL** da un validatore successivo (avviso 17/07 in `SCALPER_CALCIO_DOSSIER.md`) — numeri non ricertificati.
13. Nessuna correzione proposta: solo fatti, come da mandato.
