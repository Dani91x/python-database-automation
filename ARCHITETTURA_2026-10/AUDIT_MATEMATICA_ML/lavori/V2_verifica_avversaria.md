# V2 - Verifica avversaria dei reperti MEDIO+ di E, E2, F e dei reperti C/B/A scelti (09/10/2026)

Sola lettura. Sonde in `lavori/sonde/`: `v2_dutch.py`, `v2_tennis_tb.py`, `v2_commissione.py`,
`v2_calib_slope.py`, `v2_poisson_slope_db.py`, `v2_db_live_now.py`. DB: 2 SELECT (live_now LIMIT 5;
fixture_predictions LIMIT 500). Radice = R.

## Riepilogo verdetti

| Reperto | Verdetto | Gravita' finale |
|---|---|---|
| E2-1 Dutching variable: anteprima UI != server | CONFERMATO CON GRAVITA' DIVERSA | MEDIO (stesso totale T, il server e' il piano coerente; la UI mostra -24 sulle gambe che il server non piazza) |
| E2-2 Dutching variable + LAY piazza BACK | CONFERMATO, nessuna guardia a valle | ALTO |
| E2-3 oos_valid=True hardcoded | CONFERMATO | MEDIO (invariato; non verificato sul DB) |
| E2-4 win rate tennis per ordine | CONFERMATO (per lettura SQL) | BASSO (solo statistica; i soldi sono giusti) |
| E2-5 target/anteprima lordi di commissione | CONFERMATO (sonda) | BASSO |
| E2-6 Ventaglio ancorato alla base | CONFERMATO CON GRAVITA' DIVERSA | BASSO (CLI di ricerca, le costanti sono dichiarate "benchmark validati", esiste `valida_ventaglio.py`) |
| E2-7 Kelly K1 con minimo 1.00 arriva al Telegram | SMENTITO | - (il Telegram legge un altro Kelly: `Ai Engine/ai_engine/value_betting.py:220`, senza minimo 1.00) |
| E-1 tie-break fisso 0.5 | CONFERMATO CON GRAVITA' DIVERSA | BASSO, LATENTE oggi (effetto zero finche' gli hold sono simmetrici: `serve_data.csv` non esiste) |
| F-1 markets_calibrated con source "none" | CONFERMATO, latente | BASSO (doppio fallback DB->json; oggi source="db") |
| F-2 scalper: ML calibrato vs Poisson grezzo vs mid | CONFERMATO nel codice; gravita' ridotta | BASSO/MEDIO: il mid (back+lay)/2 ha somma ~1, "non de-viggato" pesa poco; resta il grezzo-vs-calibrato e l'assenza di controllo d'eta' |
| F-3 lambda tattico o Poisson senza id | CONFERMATO | MEDIO (invariato, nessuna perdita provata) |
| C min stake .it | CONFERMATO divergenza | MEDIO (coerenza), nessuna perdita dimostrata |
| C4 arrotondamento commissione | CONFERMATO e quantificato | BASSO |
| B R9 Elo senza vantaggio casa/margine | CONFERMATO CON GRAVITA' DIVERSA | BASSO (e' una feature del modello, non una probabilita') |
| B R10 bss_monitor in nessun workflow | CONFERMATO CON GRAVITA' DIVERSA | BASSO (dichiarato "uso manuale"; legge `mm_history.json` legacy) |
| A-2 nessuna misura continua del Poisson | CONFERMATO | MEDIO |
| A-3 probabilita' grezze troppo estreme su O2.5 | CONFERMATO, replicato fuori campione | MEDIO |

## 1. Dutching (E2-1, E2-2) e raggiungibilita' LIVE

Guardie cercate a valle e NON trovate:
- `frontend/src/lib/liveOrders.ts:244-300` (`sendDutch`): valida solo numero selezioni >=2, total/target >0, nominated >1. Nessun rifiuto di `variable`+`lay`.
- `DutchingPanel.tsx`: `guardBeforeSend` (r.~236-262) blocca solo `lay`+`target` e richiede la spunta "Confermo dutching REALE"; il select Modalita' disabilita solo `target` per lay (r.~380). `variable` + `lay` e' selezionabile.
- Worker `Betfair/stream/live_order_worker.py:2914-2919`: `if dmode == "variable": ... plan = dutch_variable(triples, total)` senza guardare `side`; `dutch_variable` ritorna sempre `side="back"` (`trading/dutching.py:~184-244`). `build_order(..., side=plan.side)` (r.2957): il lato viene dal piano, non dalla richiesta. Il ramo `target` rifiuta lay (r.2923-2924), `variable` no.
- `DutchPlan.actionable` (dutching.py:~46-48) controlla solo `legs` non vuote e `total_stake>0`: nessun controllo su `worst_profit<0` (un dutch BACK a book>100% e' piazzato lo stesso).
- `_rate_guard`, `_check_exposure_guard` (r.2941-2945) e `_effective_cap` limitano importi/esposizione, non coerenza del lato. `build_order` non conosce il lato richiesto dall'utente.
- Backend Node: `git grep -il dutch` fuori da frontend/ e dal worker non trova altro codice di produzione (solo `safe_strategy/combos.py` e test, `ARCHITETTURA_*` tsv): il comando `dutch` va in coda e lo esegue solo il worker.

Raggiungibilita' LIVE: `SeguiLive.tsx:814-822` monta `DutchingPanel mode={mode}`; `mode` viene da `live_now.state.order_mode` del runner (`SeguiLive.tsx:194`). Con runner LIVE il pannello e' operativo (spunta "Confermo dutching REALE" unica barriera). SELECT live_now (LIMIT 5, righe del 30/09, quindi non attuali): 4 PAPER e 1 LIVE. Oggi NON verificato (dato vecchio di 9 giorni): dipende da chi ha acceso il runner.

Sonda `v2_dutch.py` (quote 2.5/3.0/4.0, pesi 1/2/1, T=100):
- UI anteprima: stake 30.38/50.63/18.99, profitti -24.05/+51.89/-24.04.
- Server `dutch_variable`: stake 40.51/34.18/25.32, profitti +1.26/+2.53/+1.27.
- Il totale piazzato e' lo stesso (T=100): la discrepanza e' di semantica (UI = stake proporzionale a w/p; server = profitto proporzionale a w). Il server non peggiora il rischio rispetto all'anteprima in questo esempio, ma l'utente conferma una cosa e ne ottiene un'altra. Per pesi forti con book>100% il server rifiuta (stake negativo) dove la UI mostra un piano. Per questo la gravita' e' MEDIO, non ALTO.
- Variable+lay: il server emette side="back" con stake totale T sui prezzi "lay" mostrati. Con prezzi lay, la somma 1/L e' tipicamente >=~1 (book lato lay favorevole) quindi il dutch BACK equivalente e' in perdita garantita (stimata ~T*(1-1/book)); non c'e' guardia che la fermi. Rischio piazzato = T (non la liability), lato opposto a quello voluto. ALTO confermato: soldi veri e lato sbagliato; non l'ho eseguito (richiede flumine).

## 2. Minimi di stake .it (C)

Costante canonica: `Betfair/stream/trading/minimi_it.py`: `IT_MIN_BACK = 1.00`, `IT_MIN_LAY = 1.00`, `IT_FLOOR_LEGGE = 0.50`, passo 0.50 per difetto sulle punte dirette >=1.00, `SUBMIN_IMPORTO_FINALE_MIN = 0.50`. Tutto il motore (live_order_build, submin, Mike, scalper, banco) la usa. Il codice usa quindi 1.00 (non 2.00); C_betfair_math.md ha ragione.

Valori che DIVERGONO dalla canonica (git grep -n -i "min_stake|MIN_STAKE|IT_MIN|ABS_MIN"):
| Dove | Valore | Effetto |
|---|---|---|
| `live_order_worker.py:393-405` `_min_stake()` env BETFAIR_MIN_STAKE | 2.00 (default; solo ripiego di `_sub_minimum_floor`, r.410-422) | usato solo se `place_min_size` fallisce: basso |
| `live_order_worker.py:2950` commento "min-stake .it EUR 2" | 2.00 (commento stantio) | nessuno sul codice |
| `stream/risk_engine_worker.py:964` `_AUTOHEDGE_MIN_STAKE_IT` | 2.00 | auto-hedge di size 1.00-1.99 va su `place_submin` invece che `place` diretto (r.1062): percorso piu' complesso del necessario, non perdita provata |
| `safe_strategy/bot_service.py:239,361,867` `min_stake` | 2.0 (parametro utente, default) | e' un pavimento di preferenza; il pavimento vero e' `execution.ABS_MIN_SIZE = 0.01` (execution.py:51) e poi `min_stake_rules` |
| `omega/omega_config.py:31` `min_stake` | 0.5 (range 0.5-1000) | sotto 1.00 il motore decide place-and-trim/rifiuto (omega_market.py:731-745) |
| `frontend XHedgePanel.tsx:40`, `replay/MarketPanel.tsx:35,67,121`, `safestrategy/InvestAction.tsx:34`, `BotParamsSheet.tsx:833` | 2 | la UI spegne/avvisa stake 1.00-1.99 che il motore accetterebbe |
| `omega/ManualPanel.tsx:35` `OMEGA_MIN_STAKE` | back 2, lay 0.5 | diverso sia dalla canonica (1.00/1.00) sia da Omega config |
| `live_order_build.py:96` `COM_MIN_STAKE` | 2.00 | .com (giurisdizione non usata): ok |
Verdetto: divergenza REALE (sei valori diversi: 0.01, 0.5, 1.0, 2.0 + due UI), contro la regola scritta in `minimi_it.py` ("non ridefinire questi numeri altrove"). Nessuna perdita di soldi dimostrata; MEDIO per coerenza. Il minimo vero .it resta NON VERIFICATO con prova reale (nota di C, reperto 10).

## 3. C4 arrotondamento della commissione (sonda `v2_commissione.py`)

Righe confermate: Mike `engine.py:1666-1668` (`comm_market = round(max(0,v)*c, 2)`, netto = lordo - comm), Safe `execution.py:2706-2711` (`total = round(net - net*c, 2)`), tennis paper `tennis_live_order_worker.py:1256-1280` (`round(totale*p/utile, 2)` per quota), banco `pnl()` totale vs `pnl_betfair()` per mercato (C5, non riletto da me: NON RIVERIFICATO).
Numeri (c=5%, formula Safe replicata a mano, non chiamata `settle_group`; NON RIVERIFICATO con la funzione vera):
- Lordi 0.01-30.00 a passo 1 cent (n=3000): Safe != half-up 75, Mike != half-up 31, Safe != Mike 96 (C dice 92: differenza dovuta a come costruisco il float). Deriva media Safe-halfup +0.025 cent/mercato, Mike +0.010.
- Lordi realistici (stake {1,1.5,2,5,7,10,15,25} x quote tick, vincente, n=20000): Safe != half-up nel 12.8% dei mercati, sempre di +1 cent a favore del trader (lordi multipli di 0.5 danno tie al mezzo centesimo: Safe arrotonda il netto, half-up arrotonda la commissione); deriva +0.128 cent/mercato (1.3 EUR ogni 1000 mercati).
- Paper tennis: su 5000 mercati sintetici la somma delle quote differisce dalla commissione del mercato in 668 casi (13%), scarto massimo 0.02 EUR.
Verdetto: CONFERMATO, BASSO. Direzione: Safe paper un po' ottimista rispetto a half-up; la regola esatta di Betfair resta non verificata.

## 4. Tennis: tie-break fisso (E-1) (sonda `v2_tennis_tb.py`)

Caso richiesto: hold A=0.85, B=0.65. Inversione di `hold_from_serve_point` (tennis_opportunity.py:126): P(punto al servizio) A=0.6627, B=0.5614. Tie-break a 7 punto per punto (1-2-2): P(A vince TB)=0.6610 (apre A o B), contro 0.5 di produzione.
- P(A vince match) bo3 al 6-6 del primo set: produzione 0.7847, tie-break modellato 0.8568 (+7.2 pp).
- bo3, A avanti di un set e 6-6: 0.8923 -> 0.9344 (+4.2 pp). Da 0-0: 0.8809 -> 0.9022; bo5 da 0-0: 0.9297 -> 0.9470.
- Gate Safe tennis (min_prob_back 0.90, tennis_opportunity.py:55,429): griglia di tutti gli stati set/game (312 in bo3, 702 in bo5) x 7 coppie di hold: il gate cambia verso in 2-47 stati per coppia (es. hold .85/.65 bo3: 16 stati; .9/.6: 33). Nella maggior parte il modello corretto e' PIU' alto: la produzione e' prudente (non scatta). Pero' 1-4 stati per coppia vanno in direzione NON prudente (produzione >=0.90, modello <0.90): sono i casi in cui il leader nel set e' il giocatore con hold piu' BASSO (es. hold .85 vs .80, B avanti 6-5 al secondo set: 0.9000 contro 0.8901).
- MA: oggi l'effetto e' ZERO. `tennis_serve_data.get_serve_prob` legge `Betfair/stream/tennis_scalper/serve_data.csv`, che NON esiste (ls: nessun file; `git ls-files` non lo contiene); il docstring dice che per i challenger ritorna None. Senza dati `_holds` (tennis_opportunity.py:236-243) usa lo stesso prior per i due giocatori (0.75) e il ripiego di bot_service.py:5233 usa `estimate_holds(0,0,0,0)` simmetrico: con hold uguali la sonda da' differenza 0.0000 su tutti gli stati. Verdetto: difetto reale ma latente; diventa attivo se si popola serve_data.csv o se un chiamante passa hold asimmetrici. Gravita' oggi BASSO, MEDIO se si attivano i dati di servizio.
- E-2 collegato (set successivo parte sempre con A al servizio): con hold simmetrici nessun effetto.

## 5. Altri reperti

E2-3 `oos_valid`: `build_analytics_signals.py:298` e `merge_engine_signals.py:203` scrivono True sempre; il filtro `p_ml_clean` (`migrations/analytics_strategy_rpc.sql:114,217`) usa `bool_and(oos_valid)` (`analytics_strategy.sql:226`), quindi il filtro vale solo `ml_reliable`. I test `*_kickoff_2026_09_26.py` riguardano la data del kickoff, non `generated_at < kickoff`. CONFERMATO, MEDIO; contaminazione reale NON verificata sul DB.

E2-4: `migrations/tennis_bot_daily_giorno_partita_2026-09-30.sql:55-60`: `vinti` = ordini con pnl_betfair>0, `persi` = <0, per ordine. Un round trip chiuso in green ha un ordine in utile e uno in perdita: vinti ~ persi per costruzione. Il segno dei pnl per ordine nella tabella vera NON verificato (0 SELECT). BASSO.

E2-5: sonda: target 5.00 -> profitti lordi 5.00, netti 4.75 (c=5%), 4.90 (c=2%). BASSO.

E2-6: `ventaglio_segnali.py:46-54` ha il commento "Accuratezza direzionale attesa ... quando il segnale e' AGISCI (benchmark validati)", non "frequenza marginale"; esiste `valida_ventaglio.py` (hit per tier e per mercato su 18 partite). Aritmetica verificata (r.220-258): base 0.76 con penalita' massima -0.03 (pconv 0.55-0.60) = 0.73 >= 0.72, quindi A_MAX scatta per O/U 1.5 e HT Over 0.5 salvo pconv<0.55 o regime "ritardo": "quasi automatico" e' vero. Manca il lift sul base-rate e il campione e' 18 partite del 19/06; usato solo da CLI (`git grep ventaglio_segnali`: solo `valida_ventaglio.py`). BASSO.

E2-7 SMENTITO: `Telegram bot/supabase/functions/telegram-bot/index.ts:591` stampa `sig.kelly_stake`, ma i `bet_signals` li scrive `predict_fixture.py:945-955` da `value_betting.py:219-220` (`kelly_stake = round(kelly*bankroll, 2)`), senza il `max(...,1.0)` di `money_management.calculate_kelly_stake` (K1). K1 e' chiamato solo da `money_management.py:960-1178` (foglio). Il reperto C-R3 resta per K1, ma non raggiunge il Telegram per questa via. (Altri difetti del Kelly di value_betting: NON esaminati.)

F-1: `poisson_calibrator.py:84-90` (`source="none"` se DB e json falliscono), `Prediction/today_predictions_backfill.py:944-952` scrive comunque `markets_calibrated` e `calibration_source=cal.source` ("none" incluso). Mike `dossier.py:102-107` imposta `p_under35_fonte="calibrated"` se esiste `markets_calibrated`; veto acceso di default (`mike/config.py:152`, default True); `PoissonPanel.tsx:81` badge da `!!markets_calibrated`. Il calibratore ha un doppio ripiego (DB, poi json): servono entrambi guasti. Latente. BASSO.

F-2: `bias_resolver.py:80-86` usa `db_json_analisi.markets["1x2"]` grezzo; `edge = p_avg/p_mkt - 1` (r.188); `scalper_session.py:1436-1458`: p_mkt = 1/mid per runner, nessuna normalizzazione; `prediction()` (scalper_session.py:1399-1407) seleziona `created_at,updated_at` e non li usa (confermato). Correzione del giudizio: con mid fra best back e best lay la somma delle 1/mid e' ~1 (il margine back>lay si compensa), quindi il "non de-viggato" e' un effetto di secondo ordine; il punto vero e' la natura mista (Poisson grezzo + ML calibrato) e l'assenza di controllo d'eta'. Strategia: da portare all'utente.

F-3: `stream/db.py:262-285` prova prima `tactical_engine_json` poi `db_json_analisi.inputs`; nessun id del modello nel risultato. CONFERMATO.

B R9: `Ai Engine/ai_engine/elo_ratings.py:62-78`: `exp_h = 1/(1+10^((a-h)/400))` senza offset casa, risultato 1/0.5/0, nessun margine di gol, K 56 (primi 10 match) poi 32, squadre nuove a 1500. Usato SOLO come feature (`feature_pipeline.py:833-845`, `elo_diff`) in un modello che ha gia' le feature casa/trasferta: l'offset casa viene assorbito dal modello. Per questo non e' una probabilita' sbagliata: BASSO.

B R10: `git grep -n bss_monitor` fuori da AUDIT/ARCHITETTURA/.md: solo `.gitignore:26` (`Betfair/bss_monitor_state.json`); nessun workflow in `.github/workflows` (10 file) lo cita. Il docstring dice "Uso manuale". Legge `Betfair/mm_history.json` (43 MB, gitignored, usato da `money_management.py:2012-2024`: percorso foglio/legacy). BASSO.

A-2: `update_poisson_calibration.py` (606 righe) e `weekly_poisson_calibration.yml` non calcolano Brier/log-loss/RPS ne' hanno un gate sul miglioramento (grep brier|log.loss|rps|gate: nessuna riga); `--apply` riscrive la tabella con soli filtri `min_n`. Nessun file dei workflow misura il Poisson. CONFERMATO, MEDIO.

A-3: Dalle 8 celle gia' misurate (n=1490, `a_poisson_misura_db_output.txt`:19): regressione pesata freq = 0.284 + 0.533*p, pendenza 0.533 +- 0.075 (z=-6.2 rispetto a 1); celle estreme: p=0.261 freq 0.420 (z=+2.6), p=0.745 freq 0.671 (z=-2.6), p=0.835 freq 0.747 (z=-2.2). Replica indipendente (`v2_poisson_slope_db.py`, SELECT LIMIT 500, FT 02/09-07/10/2026): GREZZE n=500 pendenza logistica 0.55 +- 0.125; Brier 0.2425; CALIBRATE pendenza 0.81 +- 0.185, Brier 0.2380. Quindi "troppo estreme" e' stabile fuori campione e la calibrazione la corregge solo in parte. Cautela: la causa (pesi finestre) resta NON provata; campione 500 e 1490 sono estratti senza randomizzazione (`order by fixture_id`/LIMIT). MEDIO confermato.

## 6. Metodo
git grep mirati (min stake, dutch, oos_valid, kelly_stake, bss_monitor, poisson metrics), Read per estratti, 6 sonde Python con il `.venv` (sola lettura), 2 SELECT con LIMIT <=500. Non riverificati: C5 (banco `pnl()` vs `pnl_betfair()`), `settle_group` chiamata realmente (formula replicata), contenuto di `live_now` di oggi, base-rate reale del ventaglio, segno dei pnl per ordine nella tabella tennis.
