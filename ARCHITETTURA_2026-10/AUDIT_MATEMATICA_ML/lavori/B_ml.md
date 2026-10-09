# B - Catena ML (dataset, feature, training, validazione, calibrazione, serving, consumatori)

Audit in SOLA LETTURA del 09/10/2026. R = radice repo. Sonde in `R/ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML/lavori/sonde/`
(b_ml_metriche_modelli.py, b_ml_analisi.py, b_ml_feature.py, b_ml_sim_gate.py, b_ml_sim_ece.py + output json).
DB: solo SELECT aggregati (ai_model_registry, matches con tablesample 0.5% limit 2000, match_odds tablesample 0.02% limit 1500).

## VERDETTI sulle 4 domande

(a) Al massimo livello possibile? NO. La parte di INGEGNERIA e' buona (split temporale 75/15/10 con purge, walk-forward OOF per lo
stacking, scaler/imputer/selezione feature adattati solo sul train, calibratori su val, metriche su holdout mai visto, seed fissi,
versioni librerie pinnate). Ma la parte che decide i SOLDI (gate di affidabilita', metriche, calibrazione) e' debole:
il gate BSS usa una baseline uniforme (modelli senza alcuna skill passano), gli holdout sono piccoli e il gate decide su stime puntuali,
e per btts / over_2_5 / over_3_5 la mediana dei modelli in produzione NON batte il tasso base della lega (vedi R1, R2).
(b) Omesso qualcosa? SI: RPS (non calcolato da nessuna parte nel training), confronto con il benchmark delle quote (fair_prob del
bookmaker) in log-loss/Brier, IC/bootstrap sulle metriche, baseline climatologica, ri-addestramento finale su tutti i dati,
monitoraggio periodico di deriva (bss_monitor.py non e' schedulato), feature standard della letteratura (riposo/calendario, assenze
e formazioni, xG), versionamento delle feature (FEATURES_VERSION resta "v2" dopo il fix leakage del 16/06).
Il documento interno CALIBRATION_RESEARCH.md (par. "Verdetto e gap") elenca 5 gap dichiarati "NON ancora implementati": ho verificato nel codice
che TUTTI e 5 sono ancora aperti (isotonic ancora sui binari, gate su BSS puntuale, niente shrinkage gerarchico, niente RPS/climatologia, niente monitor REL).
(c) Si puo' fare meglio? SI, in modo misurabile e senza toccare le strategie dei bot (le proposte toccano gate/metriche/training, vedi par. 4-5).
(d) Pratiche non usate che migliorano performance/tempi/risultati? SI: baseline climatologica nel gate, bootstrap sul BSS, Platt invece di isotonic con N<1000,
refit finale su tutti i dati, Elo con vantaggio casa e margine, feature da quote (probabilita' "fair" come baseline e come feature con orario noto),
partial pooling tra leghe, monitor ECE/REL rolling, early-stopping/warm start e cache gia' presenti per Optuna (ok).

## 1. Inventario

| id | file:riga | cosa calcola | input | output | consumatore |
|---|---|---|---|---|---|
| M1 dataset | Ai Engine/ai_engine/training_dataset.py:19-60 | tabella partite + feature pre_match + target | matches/odds/eventi/stat via db_adapter | DataFrame | seriea_model_export.train_and_save_all |
| M2 feature | feature_pipeline.py:509-850 | form 5/10/15, finestre team stats, H2H (<match_date), Elo, quote 1X2/OU/BTTS, implied/fair prob | history_df, match_odds, raw_json_odds | colonne home_*/away_*/odds_* | M1, predict_fixture |
| M3 Elo | elo_ratings.py:29-86 | Elo pre-partita, K=56 (prime 10 partite) poi 32, nessun home advantage, nessun margine | storico partite per lega | home_elo, away_elo, elo_diff | M2 (merge_asof backward, no exact match: feature_pipeline.py:828-846) |
| M4 split | preprocessing/temporal_split.py:51-120 | train/val/holdout cronologici 75/15/10, purge 30gg tra train e val | df con fixture_date | 3 df | seriea_model_export.py:234 |
| M5 walk-forward | temporal_split.py:123-178 | split espansivi (fold su ultimo 80%) con purge 30gg | df | (idx_train, idx_val) | OOF stacking, Optuna |
| M6 ensemble | ensemble_trainer.py:1001-1197 | RF/LGB/XGB/LogReg (+GB) -> OOF walk-forward -> meta LogReg C=0.5 (MLP Keras solo se TF presente) | X train scalato | EnsemblePayload | M9 |
| M7 Optuna | ensemble_trainer.py:152-316; seriea_model_export.py:316-358 | TPE su NLL OOF walk-forward (15/20/30 prove per tier SMALL/MEDIUM/LARGE, TINY 0), cache json per lega | train | iperparametri | M6 |
| M8 calibratori | ensemble_trainer.py:705-888 | multiclasse: temperature scaling (+bias per MEDIUM/LARGE, T in [0.1,5], bias in [-2,2]); binario: IsotonicRegression su P(True) | val (15%) | dict calibratori | M9, predict_ensemble |
| M9 export/metriche | seriea_model_export.py:204-476 | Brier + ECE (10 bin per classe) su holdout via predict_ensemble; celle di calibrazione per decile; salva .pkl.gz + upload + registry | holdout | ai_model_registry (brier, ece, calibration_cells, train_rows...) | gate, post-calibrazione |
| M10 pesi tempo | seriea_model_export.py:99-113 | decadimento esponenziale emivita 365gg, pavimento 0.05 | date train | sample_weight | M6 |
| M11 retrain | retrain_all_leagues.py; cloud_retrain_shard.py; training_planner.py; .github/workflows/retrain_models.yml | selezione leghe (RPC leagues_needing_retrain, soglia max(10, squadre/2)), shard, time budget 240 min, 20 stagioni | DB | modelli su Storage + registry | catena notturna |
| M12 post-calibrazione | compute_ml_post_calibration.py:47-160; ml_calibration.yml | cf per (lega,target,classe,decile)=out_sum/pred_sum, min_n=20, clamp [0.3,3.0], globale = somma leghe | calibration_cells dal registry | tabella ml_post_calibration | predict_fixture.py:878-909 |
| M13 serving | predict_fixture.py:667-1100; serving_batch.py | scarica modello (TTL 24h, sidecar trained_at), predice, applica post-cal, EV/Kelly, gate | feature DB | model_predictions_json | fixture_predictions |
| M14 gate | confidence_gate.py:40,170-240; predict_fixture.py:1020-1048 | 4 gate: dati, accordo, valore, calibrazione (BSS>=0.12 con base uniforme, ECE<=0.10) | brier/ece del registry | bet_signals gated | M13 |
| M15 value betting | value_betting.py:44-240 | EV netto commissione 5%, MIN_EDGE 5%, Kelly frazionato cap 2% | probabilita' + quote | segnali | M13 |
| M16 consumatore soldi | Betfair/money_management.py:548-640, 1058-1141 | scan_best_market_ml: edge su prob ML; BSS<0.05 blocca, 0.05-0.12 riduce stake, >=0.12 stake pieno | ai_data + calibration_metrics | stake ML | traccia ML dei segnali |
| M17 altri consumatori | frontend MLPanel.tsx, fixtureModels.ts; build_analytics_signals.py; market_intelligence/*; scalper/bias_resolver.py:82 | solo lettura delle previsioni | model_predictions_json | UI/analytics | - |
| M18 validazione | validate_walkforward.py; validate_models.yml; tools/omega_validate_models.py | walk-forward vecchia vs nuova config, Brier classe positiva, RPS 1x2 | DB | log | manuale (nessun gate automatico) |
| M19 legacy | model_suite.py, runner.py, models/trainer.py, backtest.py | StratifiedKFold(shuffle=True)+train_test_split casuale (model_suite.py:97,135) | - | - | solo runner.py (CLI legacy, nessun workflow) |

Fatto verificato: Omega, Mike e Safe NON leggono l'ensemble ML: leggono `db_json_analisi` (Poisson/mercati calibrati: omega_advisor.py:7,294; mike/engine.py:229;
safe_strategy/opportunity.py:231). Il consumatore a soldi dell'ensemble e' la traccia ML di `money_management.py` (da me letta solo nella parte BSS, non per intero)
+ UI/analytics. Registry: 20.535 modelli, 1.027 leghe, tutti features_version "v2"/targets "v1", trained_at da 06/2026 a 10/2026,
train_rows medio 1.256, feature_count medio 16,7 (query al DB).

## 2. Analisi per componente

### 2.1 Leakage (controlli obbligatori)
- Classifiche/standings di fine stagione: PROBLEMA STORICO RISOLTO NEL CODICE. feature_pipeline.py:768-796 prefissa `standings_` e seriea_model_export.py:634 le scarta
  (fix del 16/06). PROVA del problema passato: nei modelli locali di `Ai Engine/models_cache/league_135/39/140/78/61` (trained_at 03/2026-09/06/2026) le feature includono
  home_rank, home_points, home_draw, home_goals_for, away_played... (sonda b_ml_feature.py), cioe' lo snapshot di fine stagione. Quei file NON sono serviti (il serving usa
  `models_cache/downloaded`, predict_fixture.py:736) quindi sono peso morto (409 cartelle). Che i modelli CLOUD odierni siano puliti: NON VERIFICATO (non ho scaricato un modello cloud);
  indizio favorevole: registry tutti ri-addestrati da 06/2026, feature_count medio 14-19 contro 25-40 dei locali; ma 8.114 modelli sono di giugno e `features_version` non distingue pre/post fix (R8).
- Aggregati/form/H2H: merge_asof backward con allow_exact_matches=False (feature_pipeline.py:297-302), H2H `m[0] < match_date` (:479): corretto, nessun leak.
- Elo: il valore registrato e' PRE-partita (elo_ratings.py:55-60). Poi merge_asof senza match esatto: il match T riceve l'Elo registrato prima dell'ULTIMA partita della squadra,
  quindi ignora l'ultimo risultato: ritardo di una partita (conservativo, non leak). Stessa logica train/serve.
- Statistiche della partita stessa: colonne home_stats_/away_stats_/home_events_ servono solo come etichette e sono scartate (seriea_model_export.py:622-623). OK.
- Target encoding: non presente. Scaler/imputer: adattati solo sul train (seriea_model_export.py:261-273, ensemble_trainer.py:1084). Selezione feature (varianza/correlazione/MI top-60): sul train. OK.
- Calibratore: adattato su val, metriche su holdout separato (ensemble_trainer.py:1181; seriea_model_export.py:234). OK. Limite: la post-calibrazione (M12) e' stimata sullo stesso holdout
  che produce le metriche del gate (R7).
- QUOTE come feature: ci sono (odds_1x2_*, odds_over_2_5, implied_prob_*; presenti in 4/5 dei grandi campionati locali e tra le feature piu' frequenti, sonda b_ml_feature.py).
  `_odds_features` (feature_pipeline.py:35-82) prende l'ultimo snapshot SE esiste snapshot_time, altrimenti la MEDIANA di tutte le righe. Sul campione di 1.500 righe di match_odds
  snapshot_time e' NULL al 100%: non c'e' nessun modo di garantire che la quota usata in training sia pre-partita/apertura invece che di chiusura. Timing NON VERIFICATO (R4).
- Split casuali: nel percorso di produzione NON ci sono. KFold/shuffle esistono solo nel legacy model_suite.py:97,135 (mai schedulato) e nel meta MLP Keras (StratifiedShuffleSplit 20%, ensemble_trainer.py:933,
  solo se TensorFlow c'e': nel cloud requirements-train.txt NON installa TF, quindi cloud=LogReg, locale=MLP: modelli diversi per ambiente).

### 2.2 Training e selezione
- Walk-forward con purge per l'OOF (ensemble_trainer.py:1049-1080) e per Optuna (seriea_model_export.py:331): corretto e in linea con de Prado (purged CV).
  Verificato che gli indici di walk_forward_splits sono posizioni nell'array ordinato per data: coincidono con X perche' train_split e' gia' ordinato per data (latente: se qualcuno rimuovesse l'ordinamento a monte gli indici si sposterebbero in silenzio).
- Selezione iperparametri: obiettivo NLL OOF dentro il train, 15-30 prove, seed 42: nessuna selezione sul test. Rischio overfitting di selezione basso. Cache Optuna riusata se n_train in +-20% (seriea_model_export.py:289-300).
- SMOTE (solo MEDIUM/LARGE con imbalance<0.35) e class_weight bilanciati spostano le priors: le probabilita' vengono poi corrette solo da temperature+bias o isotonic su val (poche centinaia di righe).
- Il modello servito e' addestrato SOLO sul 75% piu' vecchio dei dati (meno 30 gg di purge): val (15%) e holdout (10%) non rientrano mai nel fit (seriea_model_export.py:234-262, 362; payload costruito con X_train_sel). Con emivita dei pesi 365 gg
  la parte piu' informativa (le stagioni piu' recenti) e' proprio quella esclusa (R5).
- Ensemble: stacking con meta LogReg su probabilita' OOF (non logit): corretto come pratica; pesi base_weights 1/logloss quasi uguali (~1.0, sonda) quindi irrilevanti.

### 2.3 Calibrazione e metriche
- Multiclasse: temperature scaling su val. Sonda sui 68 modelli locali con T: mediana 0,81 ma range [0,19 ; 5,0]: valori sui limiti dell'ottimizzatore (T=5.0, bias=2.0 in lega 78) = fit degenere.
- Binario: IsotonicRegression su val (15% ~ 100-250 righe, minimo 50 e 5 positivi). La doc scikit-learn sconsiglia isotonic sotto ~1000 campioni (https://scikit-learn.org/stable/modules/calibration.html)
  e il documento interno CALIBRATION_RESEARCH.md par. 2 lo dice come "punto piu' rischioso": ancora non corretto. Nel cache locale 146/294 modelli 1x2 hanno calibratori vuoti (nessuna calibrazione, leghe piccole); nel cloud la frazione e' NON VERIFICATA.
- Metriche: solo Brier (somma sulle classi) ed ECE (10 bin per classe). Mancano log-loss in holdout, RPS (il 1x2 e' ordinale: Constantinou & Fenton 2012, "Solving the problem of inadequate scoring rules for assessing probabilistic football forecast models", J. Quant. Anal. Sports 8(1)),
  e il confronto con il benchmark delle quote. Walsh & Joshi 2024 (Machine Learning with Applications 16:100539, https://arxiv.org/pdf/2410.21484 per la rassegna) mostrano che selezionare per CALIBRAZIONE rende molto piu' dell'accuracy: coerente con la scelta del progetto, ma richiede metriche stabili, che qui non ci sono (R3).
- ECE: formula per-classe (Guo et al. 2017). Sonda di rumore b_ml_sim_ece.py: un modello PERFETTAMENTE calibrato ha ECE medio 0,129 con n=40, 0,064 con n=170, 0,027 con n=1000; fallisce il gate ECE<=0,10 nell'86% (1x2) / 66% (binario) dei casi con n=40 e nel 16-21% con n=100.

### 2.4 Stato dell'arte (confronto)
- Hubacek, Sourek, Zelezny (2019) "Exploiting sports-betting market using machine learning", Int. J. Forecasting 35(2): il modello va valutato contro le quote di chiusura (benchmark), con RPS/log-loss, e le quote sono la feature piu' forte; qui il benchmark non c'e'.
- Dixon & Coles (1997) / modelli Poisson e Elo di Hvattum & Arntzen (2010), "Using ELO ratings for match result prediction in association football", Int. J. Forecasting 26: Elo con vantaggio casa e margine di gol; qui Elo e' la versione minima (nessun home advantage, nessun margine, nessuna regressione tra stagioni, K=56/32 non tarato).
- de Prado (2018) "Advances in Financial Machine Learning" cap. 7: purged/embargoed CV, walk-forward: implementato bene (purge 30 gg), manca l'embargo dopo il val e un IC sulla stima.
- Scikit-learn calibration: Platt per piccoli campioni, isotonic > ~1000 (link sopra). Guo et al. 2017 (ICML): temperature scaling: implementato.
- Nessuna feature su riposo/calendario, assenze/formazioni (injuries_backfill.py esiste ma non entra in feature_pipeline.py: grep injur|lineup|xg|rest_days = 0 occorrenze), xG.

### 2.5 Serving e fallback
- Download dal registry con sidecar trained_at: se il registry e' piu' nuovo si riscarica subito (predict_fixture.py:758-790). Se il download fallisce si usa la cache vecchia con solo un `logger.warning` (:795-799), senza limite di eta'.
- Nessun modello per il target -> target saltato (TARGET_SKIPPED), nessun fallback a Poisson: corretto (non inventa).
- fillna(0) dopo le mediane (ensemble_trainer.py:1242-1243): una colonna assente al serving diventa la mediana del train in silenzio; il gate "copertura >=50%" (confidence_gate.py:31) e' la sola protezione.
- Probabilita' servite = modello + calibratore + POST-CALIBRAZIONE (predict_fixture.py:878-909), ma Brier/ECE/BSS del gate descrivono le probabilita' PRIMA della post-calibrazione (R7).

### 2.6 Versionamento e riproducibilita'
Seed fissi (42/0), requirements-train.txt pinna numpy 2.4.6, scikit-learn 1.8.0, lightgbm 4.6.0, xgboost 3.2.0, optuna 4.7.0 (nota: il doc ML_TRAINING_AND_STACK.md dice optuna 4.9: discrepanza documentale). Nel pickle
si salva trained_at ma NON versioni librerie, hash del dataset, ne' elenco stagioni usate (c'e' trained_range nel registry). FEATURES_VERSION="v2" non e' stata incrementata dopo il fix leakage.
Il retrain e' incrementale (RPC leagues_needing_retrain), 3 shard, budget 240 min (retrain_models.yml): tempi per lega NON MISURATI da me.

## 3. Reperti

R1 - ALTO - Gate BSS con baseline uniforme: modelli SENZA skill passano. confidence_gate.py:170-215 e predict_fixture.py:1030-1040: brier_random=(n-1)/n. Per mercati sbilanciati un forecaster che predice SOLO il tasso base ottiene BSS alto.
Prova (sonda b_ml_sim_gate.py, 20.000 leghe simulate, holdout 170, train 1.270, modello = tasso base stimato): over_1_5 (tasso 0,74) passa il gate BSS>=0.12 nell'82,2% dei casi con BSS vs tasso-base = 0,000;
over_3_5 (tasso 0,29) 66,8%. Dati reali (registry, 1.009 modelli over_1_5): 694 passano il gate di Brier (<0,44), Brier mediano 0,370 vs climatologia 2*0,74*0,26=0,385 (BSS reale vs tasso base ~ +0,04).
Impatto: money_management.py:1058-1141 scala/blocca lo stake in base al BSS (>=0,12 stake pieno): su over_1_5/over_0_5/HT over 0.5 lo stake pieno e' assegnato a modelli indistinguibili dal tasso base. Il rischio e' economico solo se l'edge ML genera davvero scommesse (EV vs quote): NON VERIFICATO quante scommesse ML reali ci siano.
Il documento CALIBRATION_RESEARCH.md par. 4(a) lo aveva gia' identificato e non e' stato corretto.

R2 - ALTO - btts, over_2_5, over_3_5: nessuna skill dimostrata. Registry (aggregato su 1.017-1.022 modelli per target): Brier mediano btts 0,505, over_2_5 0,495, over_3_5 0,459. Tasso base su 2.000 partite (tablesample, indicativo, mix leghe): btts 0,524 -> Brier climatologico 0,499; over_2_5 0,512 -> 0,4997; over_3_5 0,294 -> 0,415.
Quindi btts e over_3_5 mediani sono PEGGIORI della climatologia, over_2_5 pari (+0,9%). 1x2: Brier mediano 0,610 vs climatologia 0,648 (1-sum p^2 con 44,5/26,5/29,0), skill +6%; le quote di chiusura dei top-campionati stanno attorno a 0,57-0,59 in letteratura (Hubacek 2019) NON VERIFICATO sul nostro DB.
Limite: tasso base misurato su campione non stratificato per lega; il confronto e' indicativo, non definitivo. Il confronto per lega con la baseline climatologica va fatto con la sonda proposta in par. 4.

R3 - ALTO - Holdout piccoli e gate su stima puntuale. Holdout = 10% di ~1.690 righe medie ~ 170 righe; guardia unica `len<10` (seriea_model_export.py:437). Brier per modello rumoroso: registry mostra 23 modelli over_1_5 con Brier<0,15 (BSS>=0,7, impossibile in modo onesto) e 5 nel cache locale (lega 746 over_1_5 Brier 0,000; lega 255 over_2_5 0,076): holdout degeneri/di una sola classe che PASSANO il gate.
Dal lato opposto un modello perfettamente calibrato fallisce il gate ECE<=0,10 con probabilita' alta nelle leghe piccole (sonda b_ml_sim_ece.py). Il gate seleziona su rumore (winner's curse). Over_2_5: 172/1.021 passano con Brier<0,44 mentre un modello senza skill ne farebbe passare ~4,4% (~45): un eccesso che puo' essere skill reale in leghe con tasso base estremo oppure rumore: NON VERIFICATO.

R4 - ALTO (timing NON VERIFICATO) - Quote come feature senza orario certo. feature_pipeline.py:35-82: in assenza di snapshot_time si usa la mediana di tutte le righe (tutti i bookmaker, tutti gli snapshot). match_odds.snapshot_time NULL nel 100% di 1.500 righe campionate.
Rischi: (i) quote di chiusura in training vs quote del mattino al serving (skew di distribuzione, il modello sovrastima il valore informativo delle quote); (ii) circolarita': edge = P_modello - P_implicita_quote dove P_modello e' funzione delle stesse quote (il modello copia il mercato: l'edge residuo e' prevalentemente rumore/shrinkage). serving_batch.py non usa quote Betfair live, usa raw_json_odds del DB (:docstring).
Impatto sulle previsioni: potenzialmente grande ma non misurato. Misura proposta: ri-addestrare 20 leghe con e senza le feature odds e confrontare log-loss in holdout.

R5 - MEDIO - Il modello in produzione non vede mai gli ultimi ~25% dei dati (+30 gg). seriea_model_export.py:234-262 e :362. Perdita attesa: piccola ma sistematica soprattutto con pesi a emivita 365 gg (miglioramento tipico 0,001-0,004 di log-loss: stima mia da pratica, NON misurata qui).

R6 - MEDIO - Calibratori fragili. Isotonic su val (~100-250 righe) per i binari (ensemble_trainer.py:866-872), temperature su limiti [0,1;5] con bias [-2;2] (valori a 5.0 e 2.0 osservati), calibratori vuoti per leghe piccole (146/294 locali). Nessuna regolarizzazione/pooling.

R7 - MEDIO - La post-calibrazione modifica le probabilita' servite ma non e' mai valutata. compute_ml_post_calibration.py: cf = out_sum/pred_sum per cella decile, min_n=20 (errore standard del tasso su 20 campioni ~0,11), clamp [0,3; 3,0] molto largo, correzione costante per decile con salti ai bordi, globale = somma delle leghe (leghe grandi dominano), le celle vengono dallo stesso holdout usato per Brier/ECE/BSS del gate (le metriche descrivono probabilita' PRE post-cal, predict_fixture.py:878-909 le cambia). Nessun test out-of-sample dell'effetto netto (Brier prima/dopo su dati nuovi).

R8 - MEDIO - Versionamento debole. FEATURES_VERSION="v2" costante (seriea_model_export.py:50) anche dopo il fix leakage (C1) e dopo il passaggio a storico pieno; nessun hash dataset/versioni librerie nel payload; non si puo' provare quali modelli del registry (8.114 di giugno) siano pre- o post-fix. 409 cartelle `Ai Engine/models_cache/league_*` con modelli vecchi (alcuni leaky) restano su disco.

R9 - MEDIO - Elo minimale (elo_ratings.py): niente vantaggio casa nell'atteso (exp_h usa solo la differenza), niente margine di gol, K non tarato, squadre che cambiano campionato ripartono da 1500, ritardo di una partita. Hvattum & Arntzen (2010) mostrano guadagni da margine di gol e vantaggio casa.

R10 - MEDIO - Nessun monitoraggio di deriva schedulato. bss_monitor.py non e' in nessun workflow (grep); validate_walkforward.py / validate_models.yml sono manuali e producono log, non un gate. CALIBRATION_RESEARCH.md par. 5 (REL rolling) non implementato. Per le previsioni gia' pubblicate esistono dati (predictions_results_backfill.yml) per un monitor reale: NON VERIFICATO se qualcosa li usa per ML.

R11 - BASSO - Fallback silenzioso su modello vecchio se il download fallisce (predict_fixture.py:795-799), senza soglia di eta' ne' alert; fillna(0)/mediana al serving (ensemble_trainer.py:1242).

R12 - BASSO - Percorso legacy con split casuale: model_suite.py:97,135 (StratifiedKFold(shuffle=True), train_test_split random) usato solo da runner.py (nessun workflow). Rischio solo se qualcuno lo rilancia; da marcare/rimuovere (K_CARTELLE_E_CODICE_MORTO).

R13 - BASSO - Discrepanza ambiente: meta-learner Keras MLP (locale, se c'e' TF) vs LogReg (cloud): i modelli locali di test non rappresentano quelli cloud. Doc ML_TRAINING_AND_STACK.md dice optuna 4.9, requirements-train.txt 4.7.0.

R14 - BASSO - Quota "implied_prob_*" calcolata come 1/odds con commento "normalised" (feature_pipeline.py:800-803): solo fair_prob_* sono normalizzate; le implied_* includono l'overround (non e' un bug, il commento inganna). Nei modelli visti entrano implied_prob_home/draw non fair_prob.

## 4. Miglioramenti proposti

P1 Gate con baseline climatologica + IC. Sostituire brier_random con la Brier del tasso base (per lega e target, dal train) e richiedere limite inferiore IC90% (bootstrap a blocchi temporali) > 0; ri-tarare la soglia (oggi 0,12 e' calcolata sulla base uniforme).
 Guadagno: elimina i falsi positivi R1/R3 (su over_1_5 ~69% dei modelli passano senza skill). Costo: ~1 giorno + sonda di ritaratura. Misura: % modelli che passano prima/dopo, e ROI/Brier realizzato per i segnali passati vs bloccati. Rischio: riduce i mercati attivi (e' l'effetto voluto). Tocca: confidence_gate.py, predict_fixture.py, retrain_all_leagues.py, money_management.py (stake BSS). **Decisione utente (tocca il dimensionamento dello stake della traccia ML).**
P2 Metriche complete: log-loss, RPS (1x2), Brier, ECE con IC; confronto con benchmark fair_prob delle quote sulla stessa holdout; salvare nel registry. Costo ~1-2 giorni. Misura: "skill vs mercato" per lega. Tocca: seriea_model_export.py, migrazione registry (la applica l'utente).
P3 Calibrazione: Platt/sigmoid o pooling gerarchico verso un calibratore globale per N<1000; limiti stretti su T e bias; isotonic solo LARGE. Atteso: ECE e log-loss migliori nelle leghe piccole (gap P1 di CALIBRATION_RESEARCH.md). Misura: ECE/Brier su holdout temporale con bootstrap. Rischio basso.
P4 Refit finale: dopo aver scelto iperparametri e calibratori sul 75/15/10, rifit dei modelli base su train+val(+holdout) con gli stessi iperparametri (tenere il calibratore, o ricalibrare con CV sul periodo recente). Atteso 0,001-0,004 log-loss (da misurare con walk-forward su 3 stagioni di test, validate_walkforward.py gia' lo fa). Costo ~+30% tempo di training.
P5 Quote: salvare snapshot_time/orario (apertura, T-24h, T-1h) e usare nel training solo quote con orario <= quello disponibile al serving; addestrare anche una variante SENZA quote per misurare il contributo e la circolarita' (R4). Tocca ETL (altro perimetro) + feature_pipeline.py.
P6 Elo v2: vantaggio casa (~+60-100 punti), margine di gol, regressione verso la media a inizio stagione, K tarato con walk-forward; aggiungere riposo/calendario e assenze (injuries gia' scaricate). Atteso: +feature utili senza costo di dati nuovi.
P7 Monitor di deriva: schedulare ECE/Brier rolling per lega/target (basta uno script SQL sulle predizioni risolte) con allarme in live_alerts; rifare solo il calibratore quando REL sale. Tocca un workflow nuovo: **richiede permesso**.
P8 Versionamento: FEATURES_VERSION incrementale + hash dataset + versioni librerie nel pickle e nel registry; pulizia dei 409 dir locali (cleanup_models.py) previa conferma.
P9 Post-calibrazione: min_n >= 50, smoothing beta, clamp [0,7; 1,5], valutazione prima/dopo su dati fuori campione prima di attivarla.
P10 Tempi/costi: i tempi di training per lega non sono misurati (NON VERIFICATO). Da misurare con profilo su 3 leghe (piccola/media/grande); candidati classici: Optuna con pruner (MedianPruner), n_jobs coerente, LightGBM `max_bin`, riuso del dataset costruito tra target (gia' in cache). Nessuna riduzione di controlli.

## 5. Decisioni che spettano all'utente
- P1 e P9 cambiano quali mercati ML sono attivi e lo stake della traccia ML in money_management.py (BSS >=0,12 stake pieno, 0,05-0,12 ridotto, <0,05 blocco): e' una divergenza di strategia da portare a lui, non da applicare di iniziativa.
- P5/P7 richiedono modifiche all'ETL e un workflow nuovo (permesso esplicito).
- Dire all'utente PRIMA di qualsiasi "paper/live" della traccia ML: il gate di affidabilita' non e' ancora certificato come selettore di skill (R1-R3); le strategie Omega/Mike/Safe non dipendono da questo ensemble.

## 6. Metodo di ricerca
- Letti per intero o per estratti con numeri di riga: training_dataset.py, validation.py, model_suite.py, elo_ratings.py, temporal_split.py, ensemble_trainer.py (righe 140-316, 505-888, 1001-1197), seriea_model_export.py (60-470, 540-720), feature_pipeline.py (35-121, 263-308, 578-850), confidence_gate.py, predict_fixture.py (856-1048 + grep strutturale), compute_ml_post_calibration.py (testa+grep), value_betting.py (grep), money_management.py (548-640, 1058-1110), retrain_models.yml (testa), docs CALIBRATION_RESEARCH.md (par. 2-5), ML_TRAINING_AND_STACK.md (grep).
- Grep: `train_test_split|KFold|shuffle|TimeSeriesSplit|GroupKFold` (solo legacy + commenti), `rps|log_loss|brier_score_loss`, `injur|lineup|xg|rest_days`, `MIN_BSS`, `model_suite|bss_monitor`, consumatori `model_predictions|ensemble_v2|db_json_analisi|predict_fixture` (53 file, di cui solo money_management/UI/analytics leggono l'ensemble).
- Sonde: b_ml_metriche_modelli.py (1.126 pickle locali dei 4 target; solo lettura, import in -I), b_ml_analisi.py, b_ml_feature.py, b_ml_sim_gate.py (20.000 leghe simulate/mercato), b_ml_sim_ece.py (1.500 repliche per cella).
- DB (SELECT, project dqbwaocvlzbxfrpacsac): aggregati su ai_model_registry (20.535 righe), tablesample 0,5% matches (2.000 righe), tablesample 0,02% match_odds (1.500 righe).
- Web: 1 ricerca (Walsh & Joshi 2024, Machine Learning with Applications 16:100539). Le altre fonti (Hubacek et al. 2019, Constantinou & Fenton 2012, Hvattum & Arntzen 2010, Guo et al. 2017, de Prado 2018, scikit-learn calibration docs) sono citate da conoscenza, non riaperte oggi: NON RIVERIFICATE sul testo.
- NON VERIFICATO: modelli cloud correnti (feature realmente usate, calibratori vuoti), orario delle quote in training, tempi di training per lega, quante scommesse ML reali generino stake, parte restante di money_management.py.
