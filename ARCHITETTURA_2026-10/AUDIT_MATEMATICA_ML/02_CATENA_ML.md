# 02 - CATENA ML: addestramento, validazione, calibrazione, produzione (audit 09/10/2026)

> Certificato in fase 2 (09/10/2026): correzioni da lavori/fase2/CERT_*.md;
> le gravita' finali valgono in 05_ERRORI_DI_PROGETTAZIONE.md;
> le frasi non verificate sono marcate NON VERIFICATO.

Sintesi del coordinatore. Fonti: `lavori/B_ml.md` (delegato B), `lavori/M_misure.md` (misura del modello SERVITO
contro quote e Poisson su 1.509 partite), `lavori/H_verifica_avversaria.md`, `lavori/V2_verifica_avversaria.md`,
`lavori/R_stato_arte.md`. [C] = riga riaperta dal coordinatore.

## 0. Verdetti (domande del brief, par. 1.2)

| Domanda | Verdetto | Prova principale |
|---|---|---|
| (a) E' al massimo livello possibile? | **NO** | L'ingegneria e' buona (split temporale 75/15/10 con purge di 30 giorni, walk-forward per stacking e Optuna, scaler/selezione adattati solo sul train, seed fissi, librerie pinnate). Ma il modello servito non batte il mercato in nessun mercato e su Over 2.5 e BTTS non e' distinguibile dal tasso base (O2.5 ML-clim +0,0019 IC [-0,0144; +0,0186]; BTTS +0,0073 IC [-0,0097; +0,0253]; CERT_1 A2): log-loss [cert. fase 2] O2.5 0,6905 contro climatologia 0,6886 e quote 0,6714; BTTS 0,6955 contro 0,6883 e 0,6790 (M_misure.md). In 1X2 batte la climatologia (1,0081 contro 1,0463) ma resta lontano dalle quote (0,9592). |
| (b) Abbiamo omesso qualcosa? | **SI'** | Benchmark contro le quote; baseline climatologica nel gate (oggi uniforme); log-loss e RPS in holdout; intervalli di confidenza; refit finale su tutti i dati; monitor di deriva schedulato (`bss_monitor.py` non e' schedulato, ma `_auto_bss_check` del foglio controlla la deriva BSS ogni 7 giorni, `money_management.py:1333, 2608`) [cert. fase 2]; orario delle quote usate come feature; feature su riposo, assenze, xG; versionamento delle feature (FEATURES_VERSION fermo a "v2"). I 5 gap che `Ai Engine/CALIBRATION_RESEARCH.md` dichiara "non ancora implementati" sono tutti ancora aperti (NON VERIFICATO: file non riletto in fase 2). [cert. fase 2] |
| (c) Si puo' fare meglio? | **SI'** | P1-P10 (sez. 6), quasi tutte senza toccare le strategie dei bot. |
| (d) Pratiche non usate che migliorano performance, tempi, risultati? | **SI'** | Gate con baseline climatologica + bootstrap; Platt/pooling invece di isotonica con meno di ~1.000 campioni (scikit-learn); refit finale; Elo con vantaggio casa e margine (Hvattum-Arntzen 2010); decorrelazione dal mercato (Hubacek et al. 2019); selezione per calibrazione (Walsh-Joshi 2024); monitor ECE rolling; profilazione dei tempi di training (mai misurati). |

**Chi consuma l'ensemble** (verificato da B e F): NON Omega, Mike, Safe (leggono il Poisson in `db_json_analisi`).
Lo consumano: la traccia ML di `Betfair/money_management.py` (foglio "Quant Fund", non usata dai bot secondo
CRONOSTORIA.md:5384-5385; il report lo lancia l'utente a mano, `aggiorna_report.bat`, CRONOSTORIA.md:3607), lo scalper calcio per il bias BACK/LAY (`Betfair/stream/scalper/bias_resolver.py:79-92`) [cert. fase 2], UI
(MLPanel), analytics, Telegram. Quindi oggi il difetto del gate pesa sui segnali, sulla UI e sullo scalper, non sui
tre bot principali.

## 1. Catena (verificata)

```
DB (matches, team stats, eventi, match_odds senza orario, raw_json_odds)
 -> training_dataset.py + feature_pipeline.py:509-850 (forma 5/10/15, H2H < data, Elo pre-partita, quote 1X2/OU/BTTS)
 -> temporal_split.py:51-120 (75/15/10 cronologico, purge 30 gg)
 -> ensemble_trainer.py:1001-1197 (RF/LGB/XGB/LogReg, OOF walk-forward, meta LogReg; MLP Keras solo in locale)
    Optuna TPE su NLL OOF (15/20/30 prove) ; pesi tempo emivita 365 gg (NON VERIFICATO: non ritrovato nel codice) [cert. fase 2]
 -> calibratori su val: temperature(+bias) multiclasse, IsotonicRegression binari (ensemble_trainer.py:705-888)
 -> metriche su holdout: Brier (somma classi) + ECE 10 bin (seriea_model_export.py:204-476) -> ai_model_registry
 -> post-calibrazione per decile dalle celle dello stesso holdout (compute_ml_post_calibration.py, ml_calibration.yml)
 -> serving predict_fixture.py:667-1100 (download con TTL, post-cal, EV/Kelly, gate) -> fixture_predictions.model_predictions_json
 -> gate confidence_gate.py: BSS >= 0,12 con baseline UNIFORME [C :190-193], ECE <= 0,10
 -> consumatori: money_management (stake ML per BSS), scalper bias, UI, analytics, Telegram
Retrain: retrain_models.yml (3 shard di default, time-budget 240 min: smette di prendere NUOVE leghe, non e' il tetto del job; `timeout-minutes` rivisto il 09/10, valore vigente NON riletto), leghe scelte da RPC leagues_needing_retrain; 20.535 modelli, 1.027 leghe (NON VERIFICATO: registry non riletto; CRONOSTORIA.md:4888 dice 20.500). [cert. fase 2]
```

## 2. Controlli obbligatori del brief

| Controllo | Esito | Prova |
|---|---|---|
| Leakage classifiche di fine stagione | Risolto nel codice dal 16/06 (prefisso `standings_` scartato); i modelli locali vecchi lo contenevano ma non sono serviti | feature_pipeline.py:768-796; seriea_model_export.py:634; cloud NON VERIFICATO (nessun modello cloud scaricato); NON VERIFICATO in fase 2: feature_pipeline.py:768-796 non riletto, CRONOSTORIA.md:4888 conferma solo 'split temporale corretto, nessuna fuga' [cert. fase 2] |
| Aggregati, forma, H2H | OK: merge_asof backward senza match esatto; H2H `< match_date` | feature_pipeline.py:297-302, :479 (NON VERIFICATO in fase 2: righe non rilette; Elo idem) [cert. fase 2] |
| Elo aggiornato col risultato stesso | OK (valore pre-partita, con un ritardo di una partita: conservativo) | elo_ratings.py:55-60 |
| Quote di chiusura come feature | **Non dimostrabile**: `match_odds.snapshot_time` NULL nel 100% di 1.500 righe (NON VERIFICATO: il 100% NULL non rifatto da CERT_1 M6; il codice, feature_pipeline.py:44-56, conferma l'assenza di taglio d'orario) [cert. fase 2]; senza orario si usa la mediana di tutte le righe. L'unico scrittore trovato inserisce apertura E chiusura (entrambe pre-partita): nessun leak post-fischio trovato, ma skew apertura/chiusura contro le quote del mattino al serving | feature_pipeline.py:35-82; football_data_scraper/backfill.py (H) |
| Statistiche della partita stessa | OK, scartate | seriea_model_export.py:622-623 |
| Scaler/imputer/selezione | OK, solo sul train | seriea_model_export.py:261-273 |
| Calibratore sui dati di test | OK (val); ma la post-calibrazione usa le celle dello stesso holdout che misura il gate | compute_ml_post_calibration.py; predict_fixture.py:870-909 |
| Split casuali | Solo nel percorso legacy mai schedulato | model_suite.py:97,135 |
| Previsioni generate dopo il calcio d'inizio | **13,2% (200/1.510)** dei target ML serviti ha `generated_at` dopo il kickoff (periodo 21/09-07/10, vecchio orologio con cron in ritardo di 300-370 min, CRONOSTORIA.md:5580; l'orologio del 09/10, 5586-5600, dovrebbe eliminarlo: rimisurare dopo il 10/10) [cert. fase 2]; conclusioni invariate restringendo alle pre-partita | M_misure.md par. 3; GIA' NOTO (CRONOSTORIA.md:4888, 'Nessuna modifica fatta') [cert. fase 2] |

## 3. Qualita' misurata del modello servito (M_misure.md, campione B)

| Mercato | ML log-loss | Quote | Poisson cal. | Climatologia | ML vs quote (IC95) |
|---|---|---|---|---|---|
| 1X2 (n=1.509) | 1,0081 (RPS 0,2135) | 0,9592 (0,2008) | 1,0119 | 1,0463 | +0,0489 [+0,0334; +0,0638] |
| Over 2.5 (n=1.006) | 0,6905 (ECE 0,0485) | 0,6714 (ECE 0,0149) | 0,6846 | 0,6886 | +0,0191 [+0,0051; +0,0337] [cert. fase 2] |
| BTTS (n=1.014) | 0,6955 | 0,6790 | 0,6799 | 0,6883 | +0,0165 [+0,0005; +0,0348] (al limite della significativita', non 'n.s.' netto) [cert. fase 2] |

- Peso ottimo dell'ML nella miscela con le quote: 0 su 1X2, ~0,05 su O2.5 (nessun guadagno visibile), 0,25 su BTTS (guadagno log-loss 0,0008, in-sample, trascurabile ma non zero; CERT_1 A2); in CV O2.5 e BTTS +0,0006/+0,0003 (dato di fase 1, non rifatto). [cert. fase 2] ML contro climatologia: non distinguibile (O2.5 +0,0019, BTTS +0,0073; gli IC contengono 0). [cert. fase 2]
- GIA' NOTO [cert. fase 2]: A2, A3, MA1, MA2 e M1 sono gia' in `AUDIT_2026-10-02/AUDIT_ML_POISSON.md` e CRONOSTORIA.md:4888 ('il MERCATO batte ML, Poisson e TacticAI su tutti i 13 bersagli'; 'Nessuna modifica fatta').
- Uscite degeneri: 5 partite con P(BTTS) = 0,01 con esito osservato 0,60; tre Over 2.5 a 0,01.
- Registry (H, 2.000 righe): Brier mediano btts 0,5054 (peggio di qualsiasi costante), over_2_5 0,4945; il gate
  blocca gia' il 95% dei btts (NON VERIFICATO: registry non rifatto in fase 2). Holdout mediano ~90 (limite basso 87 dal codice dello split, 500 modelli over_2_5), medio ~170, 43% dei modelli sotto 60 righe (CERT_1 A3); Brier 0,000 su holdout degeneri NON riscontrato (minimo 0,2446 su over_2_5; altri bersagli NON VERIFICATO). [cert. fase 2]

## 4. Reperti (gravita' finale dopo verifica)

| id | Gravita' | Reperto | file:riga | Verifica |
|---|---|---|---|---|
| ML-R1 | MEDIO (prima MEDIO-ALTO; CERT_1 MA1) [cert. fase 2] | Gate BSS con baseline uniforme: un modello che predice solo il tasso base passa (tasso 0,74 -> BSS +0,23; 0,70/0,30 -> +0,16). Per 1X2 il gate e' selettivo, per i binari sbilanciati no. Stake pieno nella traccia ML con BSS >= 0,12 | confidence_gate.py:170-215 [C]; predict_fixture.py:1030-1040; money_management.py:629-657 | H (sonda sul gate di produzione); gravita' ridotta da ALTO perche' il consumatore a soldi e' il foglio Quant Fund; CERT_1 MA1: CONFERMATO, GIA' NOTO (CRONOSTORIA.md:4888); BSS=(1-2p)^2, passa sopra il tasso 0,673 [cert. fase 2] |
| ML-R2 | MEDIO-ALTO (prima ALTO (previsioni); CERT_1 A2) [cert. fase 2] | Il modello servito non e' distinguibile dalla climatologia su O2.5 e BTTS (IC contengono 0) e perde dalle quote ovunque; mediana registry btts/over_2_5 senza skill [cert. fase 2] | M_misure.md; registry | M + H; CERT_1 A2: CONFERMATO nei numeri, GIA' NOTO (AUDIT_ML_POISSON.md, CRONOSTORIA.md:4888); 'mediana registry btts/over_2_5 senza skill' NON VERIFICATO [cert. fase 2] |
| ML-R3 | MEDIO-ALTO (prima ALTO (selezione); CERT_1 A3) [cert. fase 2] | Holdout mediano ~90 e medio ~170 (43% dei modelli sotto 60 righe), unica guardia `len<10`: il gate seleziona su rumore (modelli perfettamente calibrati falliscono ECE<=0,10 nell'89% dei casi con n=40, 98% a n=20, 54% a n=87, 40% a n=110; Brier 0,000 su holdout degeneri NON riscontrato: minimo 0,2446 su over_2_5) [cert. fase 2] | seriea_model_export.py:401 | H; CERT_1 A3: CONFERMATO, GIA' NOTO (AUDIT_ML_POISSON.md:21,110,114; CRONOSTORIA.md:4888); simulazione di CERT_1 [cert. fase 2] |
| ML-R4 | MEDIO | Quote come feature senza orario; circolarita' dell'edge (edge calcolato contro le stesse quote usate in input); correlazione ML-quote 0,54-0,74 | feature_pipeline.py:35-82 | H (gravita' ridotta: nessun leak post-fischio trovato); CERT_1 M6: CONFERMATO nel codice (feature_pipeline.py:44-56), il '100% NULL' NON VERIFICATO [cert. fase 2] |
| ML-R5 | MEDIO | Previsioni "pre-partita" generate dopo il calcio d'inizio (13,2%) (21/09-07/10, vecchio orologio con cron in ritardo di 300-370 min, CRONOSTORIA.md:5580; causa probabile rimossa dall'orologio del 09/10, 5586-5600: rimisurare dopo il 10/10) [cert. fase 2] | predict_fixture.py:1051-1089 (scrittura); batch del mattino | M (fatto temporale verificato; contaminazione NON verificata); CERT_1 M1: CONFERMATO il numero (200/1.510), GIA' NOTO (CRONOSTORIA.md:4888) [cert. fase 2] |
| ML-R6 | BASSO-MEDIO (prima MEDIO; CERT_1 M7; scelta di progetto) [cert. fase 2] | Il modello servito non vede mai l'ultimo ~25% dei dati (+30 gg), cioe' le stagioni piu' recenti | seriea_model_export.py:234-262, :362-366 | H; CERT_1 M7: CONFERMATO, SCELTA DI PROGETTO documentata nel codice (seriea_model_export.py:238-243); proposta di refit P4 in B_ml.md [cert. fase 2] |
| ML-R7 | MEDIO | Calibratori fragili: isotonica su ~120 righe, temperature ai limiti dell'ottimizzatore (T=5, bias=2), calibratori vuoti nelle leghe piccole | ensemble_trainer.py:866-872 | H; CERT_1 M8: CONFERMATO nel codice, GIA' NOTO (AUDIT_ML_POISSON.md:65); 'T e bias ai limiti' non riletto [cert. fase 2] |
| ML-R8 | MEDIO | Post-calibrazione mai valutata fuori campione; il gate misura le probabilita' PRIMA della post-calibrazione | predict_fixture.py:870-909; compute_ml_post_calibration.py:48, :74-77 | H; CERT_1 M9: CONFERMATO (predict_fixture.py:870-909; gate su calibration_metrics prima della post-cal) [cert. fase 2] |
| ML-R9 | MEDIO | `oos_valid=True` scritto sempre: il filtro analytics dipende solo da `ml_reliable`, nessun controllo generated_at < kickoff | build_analytics_signals.py:298 [C]; merge_engine_signals.py:203 [C] | V2; CERT_4 2.18: CONFERMATO (`oos_valid=True` costante in build_analytics_signals.py:298 e merge_engine_signals.py:203) [cert. fase 2] |
| ML-R10 | BASSO (prima MEDIO (BASSO se tutti i modelli sono post-fix); CERT_1 M10) [cert. fase 2] | Versionamento: FEATURES_VERSION "v2" costante dopo il fix leakage; nessun hash del dataset o versioni librerie nel pickle; 409 cartelle di modelli vecchi su disco (408 `league_*` confermate; 'alcuni con leakage' NON VERIFICATO) [cert. fase 2] | seriea_model_export.py:50, :698 | H; CERT_1 M10: CONFERMATO (FEATURES_VERSION 'v2' costante, seriea_model_export.py:50) [cert. fase 2] |
| ML-R11 | BASSO | Elo minimo (niente vantaggio casa, margine, regressione tra stagioni) | elo_ratings.py:29-86 | V2 (e' solo una feature); CERT_3 B21: Elo minimo NON riletto in fase 2 [cert. fase 2] |
| ML-R12 | BASSO | `bss_monitor.py` non schedulato (manuale, legge mm_history.json legacy); `_auto_bss_check` del foglio controlla la deriva BSS ogni 7 giorni (`money_management.py:1333, 2608`) [cert. fase 2] | bss_monitor.py | V2; CERT_3 B21: RIDIMENSIONATO [cert. fase 2] |
| ML-R13 | BASSO | Fallback sul modello vecchio se il download fallisce, con warning nel log (`predict_fixture.py:795-799`, 'Using stale cached model') ma non nel payload, senza limite d'eta'; fillna con mediane al serving [cert. fase 2] | predict_fixture.py:795-799; ensemble_trainer.py:1242 | B; CERT_3 B21: RIDIMENSIONATO (non silenzioso nel log) [cert. fase 2] |
| ML-R14 | BASSO | "edge" con due significati (prob - 1/quota non de-viggata in UI; EV netto nel foglio); `implied_prob_*` non normalizzate con commento "normalised" | value_betting.py:195-197; money_management.py:572; feature_pipeline.py:800-803 | F, B; CERT_3 B22: CONFERMATO in parte, RIDIMENSIONATO (fair_prob_* normalizzate subito dopo, feature_pipeline.py:808-810) [cert. fase 2] |
| ML-R15 | BASSO | Ambiente: meta MLP Keras in locale, LogReg nel cloud; Optuna 4.7 nel requirements contro 4.9 nella documentazione | ensemble_trainer.py:933; requirements-train.txt | B; CERT_4 2.24: NON VERIFICATO (ambiente Keras/LogReg non riletto) [cert. fase 2] |

## 5. Stato dell'arte (fonti in R_stato_arte.md)

| Tema | Fonte | Noi | Verdetto |
|---|---|---|---|
| Benchmark contro il mercato e decorrelazione | Hubacek-Sourek-Zelezny 2019, IJF 35(2) [ricerca] (NBA) | nessun benchmark; ML usa le quote come feature | indietro |
| Selezione per calibrazione | Walsh-Joshi 2024, ML with Applications 16:100539 [ricerca, numeri dallo snippet, NBA] (NB: l'URL arXiv 2410.21484 citato in B e' un'altra rassegna) | gate su ECE ma con holdout troppo piccoli | in parte |
| Feature engineering e rating | Berrar-Lopes-Dubitzky 2019, Machine Learning 108 [ricerca] | forma, H2H, Elo minimo | in parte |
| Walk-forward / purged CV | Lopez de Prado 2018 cap. 7 (FONTE NON APERTA) | presente, manca embargo e IC | allineato |
| Isotonica vs Platt | scikit-learn calibration [aperta]: isotonica sopra ~1.000 campioni | isotonica su ~120 | indietro |
| BSS con baseline climatologica | Wilks 2011 (FONTE NON APERTA) | baseline uniforme | indietro |
| Metriche proprie | Wheatcroft 2021, arXiv 1908.08980 [aperta]: log-loss primaria | Brier + ECE | indietro |
| Deriva | pratica (FONTE NON APERTA) | `bss_monitor.py` non schedulato, ma `_auto_bss_check` settimanale nel foglio (`money_management.py:1333, 2608`) [cert. fase 2] | indietro |

Nota sulle fonti: Hubacek e Walsh-Joshi sono su basket NBA, non calcio: i numeri non si trasferiscono, il principio si'.

## 6. Miglioramenti (dettaglio in 06)

P1 gate con baseline climatologica + limite inferiore dell'IC (decisione utente: cambia stake della traccia ML) -
P2 metriche complete nel registry (log-loss, RPS, ECE con IC, benchmark quote) - P3 Platt/pooling gerarchico dei
calibratori - P4 refit finale su train+val+holdout - P5 orario delle quote (ETL) e variante senza quote per misurare
la circolarita' - P6 Elo v2 + riposo + assenze - P7 monitor di deriva per il Poisson/ML dei bot (workflow nuovo: permesso; esiste gia' `_auto_bss_check` settimanale nel foglio, quindi non e' 'il primo') [cert. fase 2] - P8 versionamento e
pulizia - P9 post-calibrazione con min_n >= 50 e test fuori campione - P10 profilazione tempi di training. In piu':
rimisurare la quota di previsioni post-fischio dopo la notte del 10/10 (causa probabile rimossa dall'orologio del 09/10) e poi, se restano, marcarle e non contarle come pre-partita. [cert. fase 2]

## 6-bis. Orario delle quote e riferimenti ad ARCHITETTURA_2026-10
- Le quote di confronto (raw_json_odds) sono anteriori alla previsione in 1.519/1.519 casi (mediana 2 h prima) e
  anteriori al calcio d'inizio salvo 20 casi di ~1 minuto: il confronto ML contro quote non e' sbilanciato; ML +0,052
  log-loss [0,037; 0,068] sul campione con tutto pre-KO (lavori/Q_orario_quote.md).
- Scheda G (righe 45 e 136): `match_odds` ha ~92,5 milioni di righe (20 GB) scritte dal solo `football_data_scraper/`,
  lanciato a mano, con uno strumento `fix_snapshot_time.py`; `max(snapshot_time)` va in timeout (8 s). Coerente con il
  reperto ML-R4 (snapshot_time NULL nel campione): l'orario delle quote usate come feature va risolto nell'ETL prima di
  qualsiasi misura su tutta la tabella. `ml_calibration.yml` (post-calibrazione) non ha piu' cron dal 09/10: e' l'ottavo anello della catena notturna, incrementale dopo il retrain (solo leghe riaddestrate), FULL il lunedi' (`ml_calibration.yml:11-15`; CRONOSTORIA.md:5586-5588). [cert. fase 2]

## 7. Cio' che non ho potuto verificare
- Feature e calibratori reali dei modelli CLOUD serviti (non scaricati); se l'ML serviti usino le quote come feature.
- Tempi di training per lega; quante scommesse ML reali generino stake.
- Se una previsione generata dopo il calcio d'inizio possa vedere dati della partita stessa (solo il fatto temporale e' misurato).
- Il conteggio "23 modelli over_1_5 con Brier < 0,15 nel registry" (non riprodotto da H).
- [cert. fase 2] NON VERIFICATO: pesi tempo con emivita 365 gg; registry (20.535 modelli, 1.027 leghe, 95% dei btts bloccati); leakage classifiche e H2H; `timeout-minutes` vigente del retrain; `snapshot_time` NULL al 100%; ML-R15.
