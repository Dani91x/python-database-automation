# 05 - ERRORI DI PROGETTAZIONE, ordinati per gravita' (audit 09/10/2026)

Tutti i reperti delle consegne 01-04 in un solo elenco. Gravita' = quella FINALE dopo le verifiche avversarie
(H_verifica_avversaria.md, V2_verifica_avversaria.md) e le riaperture del coordinatore ([C]). Colonna "Id origine" =
numerazione nei file dei delegati in `lavori/` (A, B, C, D, E, E2, F). Criteri di gravita':
CRITICO = perdita di denaro certa o probabile su un percorso vivo dei bot; ALTO = soldi veri a rischio su un percorso
vivo (anche manuale) oppure previsioni pubblicate senza valore informativo; MEDIO = numero sbagliato o fuorviante che
puo' guidare decisioni, o mancanza di controllo che rende invisibile un guasto; BASSO = incoerenza, caso limite non
raggiungibile con dati reali, convenzione discutibile. Gradi intermedi (MEDIO-ALTO, BASSO-MEDIO) = reperto a cavallo
tra due livelli: il motivo e' scritto nella riga. La gravita' di questo file prevale su quella dei file 00-04 e dei
file di lavoro (vedi la tabella di concordanza degli identificativi in fondo).

**Nessun CRITICO.** La matematica dei bot Omega, Mike, Safe (green-up, P&L, commissione, Kelly, tick) e' corretta
sui conti fatti a mano.

## ALTO

| # | Reperto | file:riga | Prova | Impatto | Non verificato | Id origine |
|---|---|---|---|---|---|---|
| A1 | **Dutching "variable" sul lato LAY piazza ordini BACK.** Il worker chiama `dutch_variable` senza guardare il lato richiesto; la funzione restituisce sempre `side="back"`; `build_order` usa il lato del piano. La UI permette variable+lay (blocca solo target+lay) | Betfair/stream/live_order_worker.py:2914-2919 [C]; Betfair/stream/trading/dutching.py:184-244 (side="back" a 224, 239) [C]; frontend/src/lib/liveOrders.ts:286-300 [C]; DutchingPanel.tsx:~380 | Lettura del codice (coordinatore, V2, 03 sez.15). Nessuna guardia a valle (sendDutch, guardBeforeSend, _rate_guard, _check_exposure_guard, build_order) | Con il runner LIVE: rischio dell'intero totale T sul lato opposto a quello voluto; con prezzi lay il book back equivalente e' in perdita attesa ~T*(1-1/book). Strumento manuale dell'utente, non un bot | Non eseguito (serve flumine); se il pannello sia stato usato cosi' in LIVE | E2-2 |
| A2 | **Il modello ML servito non ha valore informativo misurabile oltre il mercato**: su Over 2.5 e BTTS non batte il tasso base (log-loss leggermente peggiore, +0,0019 e +0,0072, differenza non significativa); su 1X2 batte la climatologia ma perde dalle quote in modo significativo; nessuna miscela con le quote lo usa (peso ottimo 0) | output in fixture_predictions.model_predictions_json (predict_fixture.py:1051-1089) | M_misure.md: log-loss O2.5 0,6905 vs clim. 0,6886 vs quote 0,6714; BTTS 0,6955 vs 0,6883 vs 0,6790; 1X2 1,0081 vs 0,9592 (IC esclude 0). Registry: Brier mediano btts 0,5054 (H) | Lo usano la UI (consigli ML), lo scalper (bias BACK/LAY), il foglio Quant Fund e gli analytics: decisioni guidate da un numero che non contiene informazione oltre al mercato | 17 giorni, 1 bookmaker di riferimento (Sportsbook), orario quote non verificato | B-R2 + M |
| A3 | **Il gate di affidabilita' ML seleziona sul rumore**: holdout ~110 righe, unica guardia `len<10`; Brier 0,000 su holdout degeneri passano; un modello perfettamente calibrato fallisce ECE<=0,10 nell'86% dei casi a n=40 | Ai Engine/ai_engine/seriea_model_export.py:401; :234-262 | H (registry), sonde b_ml_sim_ece.py, h_gate.py | Mercati ML attivati o spenti per caso; stake della traccia ML assegnato per caso. ALTO perche' riguarda la stima su cui il gate decide per TUTTI i mercati; MA1 (stessa funzione) e' MEDIO-ALTO perche' riguarda solo la baseline dei binari sbilanciati | conteggio "23 modelli Brier<0,15" non riprodotto | B-R3 |
| A4 | **Safe tennis: P(vittoria) solo dal punteggio dei giochi**: i punti del game in corso sono letti e mai usati; hold uguale per i due giocatori (prior 0,75, `serve_data.csv` assente). Il bot confronta questa P con quote che conoscono la forza dei giocatori e la pressione del punto (selezione avversa) | Betfair/safe_strategy/tennis_opportunity.py:219 vs :250-261 [C]; :223-242 [C] | Sonda z2_punti_nel_game: leader al servizio 4-2 con un set, sullo 0-40: P corretta 0,827, usata 0,924; stesso stato con hold veri diversi: 0,757-0,978 a cavallo della soglia 0,90 | Decide i back sul leader (soldi, se il bot e' acceso); strategia: si porta all'utente, non si cambia. Safe tennis non risulta certificato da questo audit | effetto in soldi su esiti reali | Z2-1, Z2-2 |

## MEDIO-ALTO

| # | Reperto | file:riga | Prova | Impatto | Non verificato | Id |
|---|---|---|---|---|---|---|
| MA1 | Gate BSS con baseline UNIFORME invece che climatologica: un modello che predice solo il tasso base passa (tasso 0,74 -> BSS +0,23) e riceve stake pieno nella traccia ML | confidence_gate.py:170-215 [C :190-193]; predict_fixture.py:1030-1040; money_management.py:629-657 | sonda h_gate.py sul gate di produzione | Solo traccia ML (foglio Quant Fund); per 1X2 il gate e' selettivo | quante scommesse ML reali | B-R1 |
| MA2 | Il Poisson (che i bot leggono) non usa le quote e perde contro di esse (RPS 1X2 +0,0156, IC [+0,011; +0,020]); un "edge" Poisson contro quote e' in media errore del modello | Prediction/today_predictions_backfill.py:1589-1590 | M_misure.md (n=1.509), A, H | Ogni decisione "modello > mercato = valore" (veto U3.5 di Mike, foglio) si appoggia a un numero meno informato del mercato. Non e' un giudizio sulle strategie | orario quote | A-R1 |

## MEDIO

| # | Reperto | file:riga | Prova / impatto | Id |
|---|---|---|---|---|
| M1 | 10-13% delle previsioni "pre-partita" (Poisson 160/1.519, ML 200/1.510) generate DOPO il calcio d'inizio: partite a orari UTC notturni trattate dal batch del mattino; non marcate; entrano in analytics (`oos_valid=True` fisso) e nelle tabelle di calibrazione | M_misure.md par.3; build_analytics_signals.py:298 [C]; merge_engine_signals.py:203 [C] | Statistiche di performance "pre-partita" contaminate; forma squadra senza auto-leak (today:1474-1478 [C]); contaminazione dei dati NON verificata | M, E2-3 |
| M2 | Nessuna misura continua della qualita' del Poisson (RPS/log-loss/ECE mai calcolati in produzione) | master_backtest.py:1056-1160; valida_motore_poisson.py:20-24 | un peggioramento non verrebbe visto | A-R2 |
| M3 | Probabilita' Poisson grezze troppo estreme (pendenza 0,53-0,55 su O2.5, confermata fuori campione) | today_predictions_backfill.py:1500-1555 | il grezzo su O2.5 e' peggio della climatologia (0,6948 vs 0,6886); lo scalper usa il grezzo | A-R3 |
| M4 | Nessuna memoria tra stagioni nel Poisson principale: nessuna previsione prima di 5 partite/squadra; neopromosse senza prior | :1210-1230 [C], :1534-1540 | prime giornate di ogni campionato scoperte | A-R4 |
| M5 | Nessun aggiustamento per forza degli avversari nel Poisson principale | :1500-1594 | stima distorta per calendari sbilanciati | A-R5 |
| M6 | Quote come feature ML senza orario (snapshot_time NULL al 100%); edge ML calcolato contro le stesse quote che entrano nel modello (circolarita') | feature_pipeline.py:35-82 | correlazione ML-quote 0,54-0,74 | B-R4 |
| M7 | Il modello ML servito non vede mai l'ultimo ~25% dei dati (+30 gg) | seriea_model_export.py:234-262, :362-366 | le stagioni piu' recenti escluse | B-R5 |
| M8 | Calibratori ML fragili (isotonica su ~120 righe; T e bias ai limiti; calibratori vuoti nelle leghe piccole) | ensemble_trainer.py:866-872 | contro la raccomandazione scikit-learn | B-R6 |
| M9 | Post-calibrazione ML mai valutata; il gate misura le probabilita' prima della correzione | predict_fixture.py:870-909; compute_ml_post_calibration.py | i numeri del registry non descrivono cio' che si serve | B-R7 |
| M10 | Versionamento ML debole (FEATURES_VERSION "v2" costante dopo il fix leakage, nessun hash dataset) | seriea_model_export.py:50, :698 | non si puo' provare quali modelli siano post-fix | B-R8 |
| M11 | Dutching variable: anteprima UI diversa da cio' che il server piazza (stesso totale, profitti diversi) | DutchingPanel.tsx:194-209 [C] vs dutching.py:184-244 [C] | l'utente conferma -24/+52/-24, ottiene +1,3/+2,5/+1,3 | E2-1 |
| M12 | lambda tattico-o-Poisson senza identificativo; Mike non rilegge il dossier quando arriva il tattico; p4_pre e p_under35_cal possono venire da modelli diversi | Betfair/stream/db.py:262-285; mike/dossier.py:81-107 | numeri non confrontabili nel tempo e tra bot | F-3 |
| M13 | Minimi di stake incoerenti: motore 1,00 (minimi_it.py), UI 2,00 in quattro pannelli, Omega 0,5, ManualPanel 2/0,5, auto-hedge 2,00; documentazione developer Betfair .it dice 2,00 a multipli di 0,50 | minimi_it.py:40-69; risk_engine_worker.py:964; XHedgePanel.tsx:40 ecc. | la regola vera richiede un ordine reale: decisione utente | C-R10 + V2 |
| M14 | market_intelligence: bias stimato sulla quota implicita grezza e sommato alla probabilita' de-viggata; `_wilson_ci` e' in realta' Wald (IC oltre 1, ampiezza 0 a p=1), anche in backtest.py; flag `significant` mai usato | market_intelligence/calibration.py:112-116 [C], :152-165; edge_scorer.py:330; backtest.py:117-120 | segnali value/avoid inclinati di ~1,5 punti vicino alla soglia di 2 | D-R2 |
| M15 | Pagina Decisioni: medie (edge, quota, prob) su tutto il gruppo, hit rate e ROI sulle sole piazzate settlate | migrations/analytics_rpc_veloci_2026-09-26.sql:598-640 | confronti su popolazioni diverse | D-R6 |
| M16 | analyze_sweet_spot: lettura senza paginazione (tetto PostgREST) e soglie scelte sugli stessi dati su cui si valutano | Prediction/analyze_sweet_spot.py:30 [C] | soglie "sweet spot" da dredging | D-R7 |
| M17 | min_edge e Kelly per euro di STAKE sia per back sia per lay: a quota 10 un EV 0,03 per stake e' lo 0,33% sulla liability | money_management.py; live_engine_pro.py:414-440 | strategia: si scrive, non si cambia | C-R6 |
| M18 | Drawdown con due definizioni (SQL senza zero iniziale: 20; TS: 30 sulla stessa serie) | personal_tracking_rpc.sql:643-645; dailyHistory.ts:899-910 | MEDIO-BASSO | D-R4 |
| M19 | Theta usa ancora l'atlante v3 con il livello squadre, trovato peggiorativo dalla validazione interna; il v3 sottostima l'hazard a 88-89' del 44% (M_MAX=87) | Betfair/stream/scalper/theta_bot.py:550; genera_atlante.py:81, :154-170 | strategia Theta e ripiego v3 di Safe/Mike: decisione utente | Z1-1, Z1-2 |
| M20 | Mike `combine_hazard` = max(atlante, modello*1,25): stima distorta verso l'alto, pressione applicata alla probabilita' e non al tasso, 1,25 non calibrato | Betfair/mike/dossier.py:114-123 | copertura anticipata rispetto al dichiarato; strategia | Z1-5 |
| M21 | Omega: tabella empirica per minuto usata su b..b+4 (P dei gol residui sovrastimata fino a x1,57 a 89'); limite di Wilson usato anche per il ranking | omega_empirical.py:150-155; omega_model.py:582-586 | direzione prudente per il lay, ma sistematica e non documentata | Z1-3, Z1-4 |
| M22 | Stop giornaliero con realized lordo di commissione e perimetro asimmetrico (realized = conto, MTM = solo live_strategy, senza profondita') | Betfair/stream/trading/daily_pnl.py:49-104; reconcile_worker.py:555; simulatedorder.py:564 | lo stop scatta tardi di commissione x vincite (circa 10 EUR su +200) | Z2-4, Z2-5 |
| M23 | `win_prob_p1` del tennis in UI sovra-estremo (serviceBreaks sempre 0, best_of=3 fisso) | Betfair/stream/tennis_runner.py:318-319 | solo UI | Z2-3 |

## BASSO (elenco compatto)

| # | Reperto | file:riga | Id |
|---|---|---|---|
| B1 | `round_to_tick(NaN/inf)` -> 1000 nel percorso REST manuale (non i bot); un browser non puo' inviare NaN (BASSO-MEDIO) | Betfair/order_exec.py:115-118 [C] | C-R1 |
| B2 | rho -0,13 di riserva per le leghe senza stima (24 stimate, media -0,081; pareggio +1,24 pp) (BASSO-MEDIO) | dc_rho_by_league.json; today:1148, 1186-1189 | A-R6 |
| B3 | ROI dei lay calcolato su stake (-400% su un lay perso a 5) (BASSO-MEDIO) | personal_tracking_rpc.sql:355-356, :775-812 | D-R3 |
| B4 | CLV su probabilita' grezze: il margine non si cancella se l'overround cambia; "chiusura" a ~5 min; verdetto SKILL senza test (BASSO-MEDIO) | money_management.py:2504-2509 [C] | D-R5 |
| B5 | (BASSO-MEDIO) Tre versioni "calibrate" dello stesso numero con regole diverse; due tabelle di calibrazione | poisson_calibrator.py; update_poisson_calibration.py; money_management.py:710-760 | A-R7, F-2b |
| B6 | Scalper: bias tra ML calibrato, Poisson grezzo e mid non normalizzato, senza controllo d'eta' (BASSO/MEDIO, strategia) | bias_resolver.py:86-90, :188 | F-2 |
| B7 | `markets_calibrated` scritto anche quando e' l'identita' (source "none"), trattato come calibrato da Mike e UI (latente) | poisson_calibrator.py:84-90 [C] | F-1 |
| B8 | Kelly del foglio: minimo 1,00 forzato DOPO il tetto: ogni stake Kelly sotto 1,00 sale a 1,00 (sopra il Kelly sempre, es. 0,45 -> 1,00 con bankroll 1.000; sopra il tetto del 2% solo con bankroll < 50) | money_management.py:812, :875 | C-R3 |
| B9 | Arrotondamento della commissione al centesimo diverso fra Safe, Mike, banco, paper tennis (1 cent per mercato, 12,8% dei mercati per Safe) | safe execution.py:2709-2710; mike/engine.py:1653-1655; cashout_value :1101 non arrotonda | C-R2 |
| B10 | Due regole di pareggio sul tick (order_exec/omega vs flumine): 263 punti su 400.000 | order_exec.py; flumine utils | C-R4 |
| B11 | Hedge al centesimo: asimmetria che cresce col prezzo; soglie assolute che non scalano | greenup.py:109; execution.py:1919 e :2023 | C-R7 |
| B12 | `ticks_between` in tre copie, due con tetto 200 | scalper_bot.py:278; tennis_scalper_bot.py:147 | C-R8 |
| B13 | Backtest: `order_profit` descritto netto ma lordo; commission_rate default 0 | run_backtest.py:56-69 | C-R9 |
| B14 | De-vig moltiplicativo e 0,975 fisso: ignorano il bias favorito-longshot (power/Shin migliori su 1X2 in modo significativo) | value_engine/devig.py:12-19; money_management.py:109, 596, 837 | C-R13, A-R12, M |
| B15 | Lordo e netto di commissione mescolati nei numeri live; hedge stesso mercato sottostimato del 2,6% | ladderMath.ts:10; eventPnl.ts:30; cashOutPartita.ts; tier0_arb.ts:123 | D-R8, E-4 |
| B16 | Metriche con lo stesso nome e definizioni diverse (profit factor, Sharpe non annualizzato, Calmar = recovery, Ulcer) | personal_tracking_rpc.sql:675; dailyHistory.ts | D-R9 |
| B17 | Tennis: tie-break sempre 0,5 e set successivi sempre con A al servizio (latente: hold simmetrici finche' manca serve_data.csv) | Betfair/stream/tennis_scalper/tennis_winprob.py:22, 36-37 [C], 64 | E-1, E-2 |
| B18 | Tennis: ripiego `estimate_holds(0,0,0,0)` = 0,7917 invece del prior 0,75 (commento dice corretto) | safe_strategy/bot_service.py:5233 | E-3 |
| B19 | Win rate del bot tennis per ordine, non per trade | get_tennis_bot_daily | E2-4 |
| B20 | Ventaglio ancorato alla frequenza marginale (A_MAX scatta quasi sempre); solo CLI | ventaglio_segnali.py | E2-6 |
| B21 | Elo minimo; monitor di deriva non schedulato; fallback silenzioso sul modello vecchio; ambiente locale/cloud diverso | elo_ratings.py; bss_monitor.py; predict_fixture.py:795-799 | B-R9..R13 |
| B22 | "edge" con due significati; implied_prob non normalizzata con commento "normalised"; eta' delle quote dei bet_signals non mostrata | value_betting.py:195-197; feature_pipeline.py:800-803 | F-7, B-R14 |
| B23 | Euristica d'unita' `v/100 se v>1` in quattro punti | edge_scorer.py:202; betfair_report_manager.py:569 | F-6, C-R12 |
| B24 | Proxy P(O0.5 1T) = 1 - P(pareggio HT) (0,559 contro 0,667) | betfair_report_manager.py:669-677 [C] | F-8 |
| B25 | Campi mai valorizzati / mai letti (p_over45_cal, over_4_5, generated_at e calibration_source ignorati dai bot) | mike/dossier.py:76; F-5 | F-4, F-5 |
| B26 | Lettura poisson_calibration senza paginazione (500 righe, tetto 1.000); cache advisor Omega senza scadenza | poisson_calibrator.py:100-112; omega_advisor.py:293-311 | F-10 |
| B27 | Fragilita' numeriche: `lam_from_prematch(NaN)` = 50; `devig_pair` con quota opposta <=1 restituisce la prob grezza; tolleranza 2 pp in derive_lambdas | value_engine/poisson_total.py:51-61; devig.py:22-29; bivariate.py:27 | A-R10, R11, R13 |
| B28 | Due convenzioni tau DC in-play (scarto max 2,1 pp); `bivariate.py` non e' una Poisson bivariata; DC in tre copie con clamp diversi | value_engine/bivariate.py; live_engine_pro.py | A-R14, E2 |
| B29 | Lookahead lieve nelle medie lega delle righe storiche; HT a 4 gol e prior 0,45 vs 0,4348; AH/CS non persistiti | backfill_historical_analysis.py:117; today:1640-1690 | A-R8, R9, R15 |
| B30 | `max(es.odds)` nel report Direzioni (oggi senza effetto: nei gruppi doppi max=min) | migrations/direction_report_rpc.sql:103, 418, 540 | D-R1 |
| B31 | Turnover ricostruito come pnl/roi; K=50 fisso; report_mm con conteggio a posteriori | analytics.ts:494; report_mm.py | D-R10 |
| B32 | `lay_size_from_target` alza al minimo oltre il target; `_kelly_lay` restituisce lo stake (etichetta UI non verificata) | omega_engine.py:236-245; live_engine_pro.py:414-440 | C-R11, C-R5 |
| B33 | Post-calibrazione ML in try/except: in caso di errore le probabilita' restano non post-calibrate senza traccia | Ai Engine/ai_engine/predict_fixture.py:895-917 | F (04 tab.1) |
| B34 | Colonne `commission` con unita' diverse (aliquota in trades, importo in tennis_live_orders) | E2_lacune.md n.11 | E2-11 |
| B35 | Cash-out di Mike: gambe `archived` escluse dalla base della commissione; `cashout_value` non arrotonda la commissione mentre il settlement si' | Betfair/mike/engine.py:776, :1101 | E2-12, 03 |
| B36 | xhedge: P&L lordo, un solo passo di copertura | Betfair/stream/trading/xhedge.py:156-215 | E2-14 |
| B37 | market_intelligence: edge composito in punti di probabilita' con termine xG euristico (xG*abs(rho)*0,10) e de-vig proporzionale | market_intelligence/edge_scorer.py:159-190, 316-380 | D32 |
| B38 | Foglio Quant Fund: a ogni `resolve_results` il P&L di TUTTI gli slot vinti viene riscritto con la commissione ATTUALE (ricalcolo retroattivo silenzioso se l'aliquota cambia) | Betfair/money_management.py:1357-1373 [C] | X |
| B39 | Regole .it non gestite nel codice secondo la documentazione developer Betfair: tetto di vincita potenziale 10.000 EUR e rifiuto di back+lay nello stesso placeOrders (NON VERIFICATO se la regola sia ancora in vigore) | 03 par. 4; R_stato_arte.md | R, 03 |
| B40 | Atlante v4: moltiplicatore di forza non neutro per squadre a rating 0 (0,90-1,20); fallback senza `pi` ignora k; pesi stagione non allineati tra leghe; confidenza "alta" sovra-dichiarata | atlante_v4.py:737-760, :611-618, :410-419; genera_atlante.py:317-323 | Z1-6..9 |
| B41 | Tennis: rischio ritiro additivo fisso 2%/3%; liability in tre copie con tolleranze diverse; `netto_size` annulla back e lay a prezzi diversi | tennis_opportunity.py; submin.py:57, 595; esposizione_fuori_bot.py:272-282 | Z2-6..8 |

## Concordanza degli identificativi
| Prefisso | Dove | Corrisponde a |
|---|---|---|
| A1-A4, MA1-MA2, M1-M23, B1-B41 | questo file (05) | elenco unico per gravita' |
| P-R1..P-R14 | 01_CATENA_POISSON.md | A-R* di lavori/A_poisson.md (P-R1=A-R1, P-R2=A-R2, P-R3=A-R3, P-R4=A-R4, P-R5=A-R5, P-R6=M par.3, P-R7=A-R6, P-R8=A-R7, P-R9=F-1, P-R10=A-R8, P-R11=A-R10/R11, P-R12=E2 tau, P-R13=F-8, P-R14=A-R9/F-4) |
| ML-R1..ML-R15 | 02_CATENA_ML.md | B-R* di lavori/B_ml.md (ML-R1=B-R1, R2=B-R2+M, R3=B-R3, R4=B-R4, R5=M, R6=B-R5, R7=B-R6, R8=B-R7, R9=E2-3, R10=B-R8, R11=B-R9, R12=B-R10, R13=B-R11, R14=B-R14/F-7, R15=B-R13) |
| FL-1..FL-18 | 04_FLUSSO_FINO_AL_CONSUMATORE.md | F-* di lavori/F_flusso.md (FL-n = F-n per n<=10) + D/E2/V2 (FL-11=D-R3, FL-12=D-R4, FL-13=D-R8, FL-14=E2-1, FL-15=E2-2, FL-16=C-R10/V2, FL-17=E2-4, FL-18=D-R10) |
| M1..M11 (proposte) in 01, P1..P10 in 02 | proposte, non reperti | numerate di nuovo in 06 (1-25) |

## Nota sul processo dell'audit (non e' un reperto del codice)
Il delegato D, dopo una grep ricorsiva che attraversava il log da 3 GB, ha terminato TUTTI i processi `grep.exe` attivi
sulla macchina, non solo il proprio (dichiarato nel suo referto). Se un'altra sessione stava usando grep in quel
momento, il suo comando e' stato interrotto. Dalla seconda ondata i brief vietano esplicitamente di terminare processi
altrui e di usare grep ricorsivi sulla radice.

## Cio' che non e' stato verificato (trasversale)
Vigenza reale sul DB delle funzioni SQL (dedotta dai nomi dei file); modelli ML cloud; orario delle quote di
riferimento; stato LIVE/PAPER del runner oggi; parte di bot_service.py, enrich_analytics_snapshots.py, funzioni SQL dei
bot (omega_*, mike_*, safe_*); regola vera dei minimi .it e dell'arrotondamento della commissione di Betfair.

## Correzione del coordinatore (09/10, verifica sul codice) — reperto A4
A4 e' formulato male. Gli INGRESSI di Safe tennis (variante 4, `Betfair/safe_strategy/engine.py:1567` `evaluate_tennis`) seguono
regole semplici (vantaggio di set, vantaggio di game nel set, quote, filtri) e NON usano la P(vittoria) del modello Markov.
Il modello di `tennis_opportunity.py` entra in due punti soli: (a) le «Opportunita' tennis», che dal 17/09 sono solo PROPOSTE
all'utente (nessun ordine automatico); (b) il cancello delle uscite in PROFITTO e a tempo di tutte le posizioni tennis
(`bot_service.py:5295` `_model_gate`, `XE.decide_time_exit`): con una P troppo ottimista il bot puo' TENERE invece di
incassare. Stop loss e uscita obbligatoria non passano dal cancello. Gravita' ricalcolata: MEDIA (ritardo/mancato incasso), non
un errore sugli ingressi. Resta da decidere con l'utente se il cancello deve usare i punti del game o restare com'e'.
FALSO anche «Safe tennis non risulta certificato»: replay di safe_tennis col banco comune il 09/10 11:47-12:10 su 35790089,
tutti gli scenari, 18/18 OK, 0 violazioni (CRONOSTORIA.md:5609-5618, referti in `AUDIT_2026-10-09/replay_tennis/`); tutti i bot
tennis certificati sul codice attuale. L'audit non ha letto la cronostoria del giorno: le sue affermazioni sulla certificazione
non valgono.
