# CERT 4 - affermazioni di fatto di 01, 02, 04, 06, 07 e DECISIONI_PER_L_UTENTE (09/10/2026, sola lettura)

R = C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation. Righe = ATTUALI (HEAD master 852b717f, albero con soli README e CRONOSTORIA modificati).
Sonda mia: `lavori/fase2/sonde/cert4_calib.py` (reliability per bin su `lavori/sonde/m_dati.json`, python -I, nessun DB, nessuna rete).
Altre verifiche: lettura del codice, `git grep`, lettura di `dc_rho_by_league.json` e `dynamic_cal.json` con il venv. 0 SELECT.
Non rifaccio i reperti gia' certificati (CERT_1/2/3): li cito. Verdetti: CONFERMATO / FALSO / RIDIMENSIONATO / SCELTA DOCUMENTATA / GIA' NOTO / NON VERIFICATO.

## 0. Esito in sintesi (le cose che cambiano il messaggio all'utente)

1. DECISIONI_PER_L_UTENTE.md, intestazione: "Safe tennis non risulta certificato; nessun replay e' stato lanciato oggi" e' FALSO. Il 09/10 11:47-12:10 il coordinatore, su ordine dell'utente, ha rieseguito `safe_tennis` col banco comune su 35790089: 18/18 OK, 0 violazioni, codice 25cab047 (CRONOSTORIA.md:5609-5618, "TUTTI I BOT TENNIS CERTIFICATI sul codice attuale"). Stessa frase in 06 n.23.
2. D6 (Mike max(atlante, modello x1,25)) e' una SCELTA DOCUMENTATA (COSTITUZIONE_MIKE.md:157-158, "comanda la fonte piu' prudente"): va TOLTA. Stessa cosa nella meta' di 06 n.30 e nella riga 07 n.10.
3. D16 (minimo di puntata, "prova vera") e' GIA' DECISO dall'utente (CRONOSTORIA.md:4790, 4792, 4793, 4947: regola 1,00 / multipli di 0,50 sopra l'euro / place-and-trim sotto; "Non sei autorizzato a fare operazioni, ti ho gia' risposto io"): va TOLTA; resta solo l'allineamento delle costanti UI (06 n.7, BASSO).
4. D17 (tetto 10.000 EUR e back+lay) e' FALSO: tetto gestito (`live_order_build.py:99, 875-886`), back+lay misti impossibili per costruzione (CERT_3 B39). TOLTA. Stessa frase in 07 (sez. 3) e 06 n.32.
5. D3 e 06 n.31: la parte "perimetro conto/strategia, esposizione aperta" e' E34, DECISIONE UTENTE "resta com'e'" (CRONOSTORIA.md:2956). Resta aperta solo la commissione. Lo stop di conto e' SPENTO di serie (NULL).
6. D20 / 06 n.4 / 01 P-R6 / 02 ML-R5 / 04 FL-5 / 07: la CAUSA del 10-13% di previsioni post-fischio (cron GitHub con ritardo mediano 300-370 min, CRONOSTORIA.md:5580-5581) e' stata rimossa il 09/10: orologio pg_cron 00:12 UTC e ordine della catena approvati dall'utente (CRONOSTORIA.md:5586-5591, 5598-5600); Today Predictions e' ora il 3 anello. Il numero (160/1.519 e 200/1.510) e' CONFERMATO ma riguarda il periodo 21/09-07/10 sotto il vecchio orologio: da RIMISURARE dopo la prima notte vera (10/10, CRONOSTORIA.md:5595), non da "decidere".
7. 07: "4 ALTI, nessun CRITICO" e' superato: dopo CERT_1 e' ALTO solo A1 (A2, A3 -> MEDIO-ALTO; A4 -> MEDIO; MA1 -> MEDIO).
8. 07: "dicono 17% dove succede 33%" non ha prova nei file e la mia sonda dice altro: Over 2.5 grezzo, bin 0,0-0,2: previsto 16,2%, osservato 29,6% (n=27); bin 0,2-0,3: previsto 25,8%, osservato 46,9% (n=81).
9. 02 / 01: il parametro "emivita 420, ridge 0,08" sta in `tactical_engine/serving.py:46,48`, NON in `model.py` (i default di classe in `model.py:87-88` sono 1800 e 0,05 e non sono usati in produzione, `serving.py:230`).
10. 07 sez. 3 / 06 n.23, n.29: il tennis di Safe e' il cancello delle USCITE IN PROFITTO; gli ingressi sono regole dell'utente (CERT_1 A4); `auto_trade_tennis` default False (`bot_service.py:193`, CRONOSTORIA.md:1101).

---

## 1. File 01_CATENA_POISSON.md

| # | affermazione | verdetto | prova |
|---|---|---|---|
| 1.1 | Pesi finestre 5/10/15 = 0,5/0,3/0,2, riga ":1500-1555" | CONFERMATO il valore; RIGA da correggere; SCELTA DI PROGETTO | `Prediction/today_predictions_backfill.py:1493` `weights = {5: 0.5, 10: 0.3, 15: 0.2}`. GIA' NOTO e dichiarato "by design": `AUDIT_2026-09-24/AUDIT_TAB_DASHBOARD_2026-09-24.md:82`, `AUDIT_2026-10-02/AUDIT_ML_POISSON.md:218`. Peso effettivo ultime 5 = 0,72 (aritmetica 0,5+0,3*0,5+0,2/3, anche `A_poisson.md:106`) |
| 1.2 | Shrinkage k=8 verso media lega, ":1525" | CONFERMATO; riga | `k_shrink = 8.0` a :1522; la funzione `_shrink` e' a :1525-1527 |
| 1.3 | Blend gol/xG 0,6/0,4, ":1565-1590" | CONFERMATO; riga | `eta_goals = 0.6` :1523; `_coef` :1577-1584; se manca xG si usa SOLO il gol, "Policy (user-confirmed)" :1568-1570. Quindi 0,6/0,4 vale solo con xG presente |
| 1.4 | Minimo 5 partite per squadra, ":1534-1540" | CONFERMATO | :1535 `MIN_MATCHES_POISSON = 5`, :1536-1540 `return None`. Commento: "money_management usa 8 per scommettere" |
| 1.5 | lambda = max(0.05, Lh*att*dif) a :1589-1590 | CONFERMATO | :1589-1590 |
| 1.6 | Cache per (lega, stagione CORRENTE) :1210-1230; forma con partite < fixture_date :1474-1478 | CONFERMATO | :1210-1220 chiave `(league_id, season_year)` con filtro `eq season_year`; :1475 `m["fixture_date"] < fixture_date` (CERT_1 M4) |
| 1.7 | Griglia 11x11 (10 gol FT), HT 4 gol, ":1131-1206, :1673" | CONFERMATO | :1607 `max_goals = 10`; :1674 `max_goals_ht = 4`; tau DC :1196-1206 (dc_tau con clamp solo su (1,0)/(0,1), docstring :1196-1197) |
| 1.8 | HT ratio prior 0,45, shrink k=12, banda [0,25; 0,65] | CONFERMATO | :1640-1665 (`prior=0.45, k=12`, `max(0.25, min(0.65, shrunk))`) |
| 1.9 | rho: 24 leghe stimate, media -0,081, altre -0,13 | CONFERMATO | `dc_rho_by_league.json`: `rho_by_league` 24 voci, media -0,0809, `global_fallback` -0,13, `generated_at` 2026-10-05; `generate_dc_rho.py:62-63` `MIN_MATCHES_RHO = 300`, `K_RHO = 300.0` |
| 1.10 | "nessuna delle 5 maggiori" ha rho stimato | CONFERMATO | ID 39, 140, 135, 78, 61 assenti dalle 24 chiavi (che sono 40-43, 50-51, 76, 99, 128-134, 141, 205, 253-256, 488, 542, 667, 706, 906, 909, 1196) |
| 1.11 | rho di riserva -0,13: P-R7 BASSO-MEDIO | CONFERMATO; SCELTA DICHIARATA | `today_predictions_backfill.py:1147-1148` commento "original Dixon & Coles (1997) estimate as the GLOBAL FALLBACK"; banda [-0,25; 0,05] :1158-1159; CERT_2 B2. Il testo di P-R7 deve dirlo |
| 1.12 | "~475 leghe" senza rho stimato (06 n.11) | NON VERIFICATO | e' 499 (leghe in `dynamic_cal.json`) meno 24: conta le leghe della TABELLA di calibrazione, non le leghe con previsioni. Il 01 stesso lo marca NON VERIFICATO (par. 5 P-R7, par. 7) |
| 1.13 | Tattico: emivita 420, ridge 0,08, "model.py:103-223" | CONFERMATO il valore; FILE da correggere | `tactical_engine/serving.py:46` `HALF_LIFE_CLUB = 420.0`, :48 `RIDGE = 0.08`, :230 `DixonColesModel(max_goals=10, half_life_days=hl, ridge=RIDGE)`, campo neutro `HALF_LIFE_NEUTRAL = 1500.0` :47; i default di classe `model.py:87-88` sono 1800/0,05. L-BFGS-B `model.py:168, 203` |
| 1.14 | Emivita 420 / ridge 0,08 / pesi / k=8 "mai tarati" | NON VERIFICATO (resta tale); indizio nuovo | `AUDIT_2026-09-25/TACTICAI_P00_NEGATIVA_2026-09-25.md:170, 202-203` valuta RIDGE 0,08 ed emivita 420 e osserva che valgono per tutte le leghe (propone ridge piu' forte per leghe a pochi dati); nessuna griglia di taratura trovata in CRONOSTORIA (git grep) |
| 1.15 | Calibrazione: bin 0,1, cap [0,2; 3,0], min_n 30, shrink per lega K=75, monotonicita' solo nella copia dinamica | CONFERMATO | `generate_dynamic_cal.py:318` `min(int(prob*10), 9)`, :351 `SHRINK_K = 75`, :14-15 `--min-n 30`; `poisson_calibrator.py:178` cap [0.2,3.0]; `_enforce_monotonic` solo in `generate_dynamic_cal.py:354` (git grep: nessuna occorrenza in poisson_calibrator, update_poisson_calibration, money_management) |
| 1.16 | "poisson_calibration 499 leghe + globale", 500 righe | NON VERIFICATO sul DB; CONFERMATO sul file | `dynamic_cal.json`: `by_league` = 499 chiavi. La tabella DB non e' stata letta |
| 1.17 | Tre copie "calibrate" (DB, dynamic_cal.json, tabella statica) | CONFERMATO ma DICHIARATO nel codice | `poisson_calibrator.py:1-25` docstring "oggi vive duplicata..."; CERT_2 B5 (regole non confrontate riga per riga) |
| 1.18 | Cron: scheda G "cron 27 3 * * 1" superata; catena pg_cron 00:12 UTC | CONFERMATO | `git grep schedule:/cron:` su `.github/workflows`: nessuna occorrenza; header di `weekly_poisson_calibration.yml:4-8` ("tolto il cron (27 3 * * 1)... gira SOLO il lunedi'"); pg_cron 00:12 UTC CRONOSTORIA.md:5586, 5591; ordine definitivo 5598-5600 |
| 1.19 | Diagramma: "batch del mattino" e "tattico NULL alle 09:55 UTC del 09/10" | RIDIMENSIONATO (superato) | Today Predictions e' il 3 anello di una catena che parte alle 00:12 UTC (CRONOSTORIA.md:5598-5600; header `today_predictions_backfill.yml:4-7`: "pronte prima delle 09:00 italiane, decisione dell'utente"). Il tattico gira DENTRO lo stesso script dopo il principale (`today_predictions_backfill.py:2730-2752`: ML poi `tactical_engine.serving.run_for_date`): "calcolato DOPO il principale" CONFERMATO; il dato 09:55 e' una misura datata, NON VERIFICATO oggi |
| 1.20 | Misure: RPS 1X2 quote 0,2008, Poisson cal 0,2165, diff 0,0156 IC [0,0110; 0,0204] | CONFERMATO (GIA' NOTO) | CERT_1 MA2 (n=1.518: 0,2172/0,2169/0,2009, diff 0,0160 IC [0,0112; 0,0206]). GIA' NOTO CRONOSTORIA.md:4888 ("il MERCATO batte ML, Poisson e TacticAI su tutti i 13 bersagli") |
| 1.21 | Log-loss O2.5: Poisson grezzo 0,6948 peggio della climatologia 0,6886 | CONFERMATO il numero; RIDIMENSIONATO la lettura | CERT_1 M3: differenza +0,0063 IC [-0,0145; +0,0270], non significativa. La frase "peggio della climatologia" va scritta "non distinguibile" |
| 1.22 | Pendenza di calibrazione O2.5 grezzo 0,53+-0,08 (V2: 0,55); "dopo calibrazione 0,81" | RIDIMENSIONATO | CERT_1 M3: grezzo 0,44-0,47, calibrato 0,58-0,60 (non 0,81), quote 0,83-0,85. Direzione confermata (troppo estremo), numeri da correggere |
| 1.23 | Reliability grezza O2.5 sovra-sicura | CONFERMATO (sonda mia) | `cert4_calib.py`: grezzo bin 0,0-0,2 pred 0,162 obs 0,296 (n=27); 0,2-0,3 pred 0,258 obs 0,469 (n=81); 0,3-0,4 pred 0,360 obs 0,481 (n=183); bin alti 0,8-1,0 pred 0,845 obs 0,782 (n=55). Calibrato: 0,2-0,3 pred 0,275 obs 0,440 (n=25), coda bassa ancora sotto-prevista |
| 1.24 | Calibrazione aiuta solo su O2.5 (-0,0103), non su 1X2/BTTS | CONFERMATO in segno | 1X2: grezzo-calibrato RPS +0,0003 IC [-0,0005; +0,0011] (CERT_1 MA2). BTTS e O2.5 non rifatti da me oltre al bin sopra |
| 1.25 | Previsioni generate dopo il KO: 10,5% (160/1.519) | CONFERMATO (numero), GIA' NOTO, CAUSA SUPERATA | CERT_1 M1; CRONOSTORIA.md:4888 ("13% ML e 11% Poisson scritte DOPO il fischio"); causa del ritardo CRONOSTORIA.md:5580-5581 e orologio nuovo 5586-5600 (vedi 0.6). "Nessun auto-leak sulla forma" :1475 CONFERMATO |
| 1.26 | Veto U3.5 di Mike ACCESO di default, `mike/config.py:152` | CONFERMATO; ACCESO PER DECISIONE UTENTE | `config.py:152` `"veto_p_under35_cal": (True, ...)`; soglie 0,807/0,684/0,514/0,385 :153-156 (curva isotonica di MISURA_PUNTO8); CRONOSTORIA.md:3058 ("DECISIONI UTENTE: (1) O1+M1 SI"), :3118 ("A DEFAULT ACCESO"), `PIANO_MODIFICHE_MIKE_2026-09-29.md:105, 114-116` ("il resto del veto resta com'e' oggi") |
| 1.27 | Consumatori: Omega (`stream/db.py:262-285`, tattico-o-Poisson) | CONFERMATO | `stream/db.py` loop `("tactical_engine_json", None), ("db_json_analisi","inputs")`: prima il tattico, poi il Poisson, nessun identificativo del motore (CERT_1 M12) |
| 1.28 | Mike: stessi lambda via `mike/db.py:620-632` -> `dossier.py`; `p_under35` da `markets_calibrated` | CONFERMATO | `mike/db.py` `fixture_lambdas` delega a `stream.db.get_fixture_prematch_lambdas`; `dossier.py:100-107` `p_under35_cal` da `markets_calibrated` o `markets`, `p_under35_fonte` "calibrated"/"raw" |
| 1.29 | Safe: lambda SOLO Poisson nel percorso fixture_match | CONFERMATO in lettura (chiamante non ritracciato) | `safe_strategy/opportunity.py:230-262` `resolve_lambdas` legge `inputs.lambda_home/away` della fixture (db_json_analisi) poi `pre_ko`; la docstring :250-252 parla di "tactical_engine / Poisson" ma la sorgente letta e' `inputs` del Poisson |
| 1.30 | Scalper: `markets["1x2"]` GREZZO contro ML calibrato | CONFERMATO | `bias_resolver.py:79-92` `extract_1x2`; chiamato da `scalper_session.py:1426-1458, 1583`; CERT_2 B6. Sul 1X2 grezzo ~ calibrato (diff RPS +0,0003 n.s.): ESITO_VERIFICA "FALSO sullo scalper" per la parte O2.5 |
| 1.31 | money_management: markets grezzi + calibrazione propria (dynamic_cal.json o statica) | CONFERMATO | CERT_2 B5 (`money_management.py:710-722` catena by_league -> global -> CALIBRATION_TABLE) |
| 1.32 | P-R2 (nessuna misura continua) | CONFERMATO; la riga va corretta | CERT_1 M2: `valida_motore_poisson.py:28,96` (non 20-24), `master_backtest.py` manuale (`MANUALE_OPERATIVO.md:227-233`) |
| 1.33 | P-R9 `markets_calibrated` scritto anche con sorgente "none" | CONFERMATO (latente) | `poisson_calibrator.py:84-90` (`source = "none"` se DB e json mancano), `:172-182` identita'; scrittura `today_predictions_backfill.py:947-951` con `calibration_source = cal.source`. Oggi source "db" (non riletto sul DB) |
| 1.34 | P-R12 tau in-play: scarto massimo 2,1 pp; "tre copie" della tau | CONFERMATO lo scarto; "tre" e' SBAGLIATO | CERT_3 B28: 2,12 pp; copie contate: almeno 5 (omega_model:275, omega_advisor:93, today:1193, bivariate:46, tactical dixon_coles). `live_engine_pro.py:58-72` e' SCELTA DOCUMENTATA. Nessun bot usa la convenzione "sempre" |
| 1.35 | Sovradispersione "misurata 1,14" tra le OMISSIONI (par. 0 b) e priorita' 22 | RIDIMENSIONATO | `A_poisson.md:166` la classifica "INFO (non e' un difetto)"; il 01 la elenca fra le omissioni |
| 1.36 | Tutte le citazioni bibliografiche | NON VERIFICATO | il 01 stesso le marca [ricerca]/FONTE NON APERTA; non le riverifico |

### Correzioni da applicare (01)
| punto | testo sbagliato -> testo giusto |
|---|---|
| par. 1 diagramma [P3] | "model.py:103-223 ... emivita 420 ; ridge 0,08" -> "model.py:103-223 (modello); parametri in tactical_engine/serving.py:46,48 (HALF_LIFE_CLUB 420, RIDGE 0,08; campo neutro 1500); default di classe model.py:87-88 = 1800 / 0,05, non usati" |
| par. 1 diagramma intestazione | "catena notturna pg_cron 00:12 UTC + batch del mattino" -> "catena notturna in fila avviata da pg_cron 00:12 UTC (Daily -> Mapping -> Today Predictions -> Results -> Hazard -> Catchup -> Retrain -> Post-Cal -> Weekly Poisson il lunedi'), ordine approvato dall'utente il 09/10 (CRONOSTORIA.md:5598-5600)" |
| par. 1 [P3] | "NULL alle 09:55 UTC del 09/10" -> "misurato alle 09:55 UTC del 09/10 col vecchio ordine; il tattico gira nello stesso script dopo il principale (today_predictions_backfill.py:2730-2752); da rimisurare dopo la notte del 10/10" |
| par. 2 tabella | righe ":1500-1555" -> ":1493 (weights)"; ":1525" -> ":1522 (k_shrink) e :1525-1527 (_shrink)"; ":1565-1590" -> ":1523 (eta_goals), :1577-1584 (_coef)"; "Tattico: model.py" -> "serving.py:46,48"; aggiungere ai pesi "GIA' NOTO e dichiarato by design (AUDIT_TAB_DASHBOARD_2026-09-24.md:82)" |
| par. 2 tabella rho | aggiungere "scelta dichiarata: DC 1997 come fallback globale (today_predictions_backfill.py:1147-1148)" |
| par. 3 pendenza | "0,53+-0,08 ... dopo calibrazione 0,81" -> "0,44-0,47 grezza, 0,58-0,60 calibrata (CERT_1 M3, due stimatori)" |
| par. 3 lettura (2) | "il Poisson GREZZO e' peggio della climatologia" -> "non distinguibile dalla climatologia (+0,0063, IC [-0,0145; +0,0270])" |
| par. 5 P-R6 | aggiungere "cause rimosse dall'orologio del 09/10 (CRONOSTORIA.md:5580-5600); rimisurare dopo il 10/10" |
| par. 5 P-R7 e 6 M4 | "475 leghe" -> "499 leghe in tabella di calibrazione meno 24 stimate (non e' il numero di leghe con previsioni)"; aggiungere "fallback dichiarato (DC 1997)" |
| par. 0 (b) e 4 | togliere "sovradispersione (dispersione misurata 1,14)" dalle omissioni, oppure scrivere "INFO (A_poisson.md:166)" |
| par. 5 P-R12 | "tre copie" -> "almeno cinque copie; live_engine_pro e' scelta documentata (:58-72); nessun bot usa la convenzione 'sempre'" |
| par. 5 P-R2 | "valida_motore_poisson.py:20-24" -> ":28,96"; aggiungere "master_backtest.py e' manuale (MANUALE_OPERATIVO.md:227-233)" |

---

## 2. File 02_CATENA_ML.md

| # | affermazione | verdetto | prova |
|---|---|---|---|
| 2.1 | Split cronologico 75/15/10, purge 30 giorni | CONFERMATO | `preprocessing/temporal_split.py:53-55` `val_ratio=0.15, holdout_ratio=0.10, purge_days=30`; il purge e' UNICO fra train e val (docstring :72-74), nessuno fra val e holdout |
| 2.2 | Optuna TPE su NLL OOF, 15/20/30 prove | CONFERMATO | `seriea_model_export.py:305` `{"TINY":0,"SMALL":15,"MEDIUM":20,"LARGE":30}`; `ensemble_trainer.py:164, 249` TPE su NLL |
| 2.3 | Pesi tempo con emivita 365 gg | NON VERIFICATO | git grep su `Ai Engine/ai_engine` per "365"/"HALF_LIFE" nessuna occorrenza utile; non ritrovato |
| 2.4 | Gate: BSS >= 0,12 con baseline UNIFORME, ECE <= 0,10 | CONFERMATO (GIA' NOTO) | `confidence_gate.py:40-41` `MIN_BSS = 0.12`, `MAX_ECE_SCORE = 0.10`; :190-193 `brier_random = (n_classes-1)/n_classes`. CERT_1 MA1. GIA' NOTO `AUDIT_ML_POISSON.md:21,110` -> CRONOSTORIA.md:4888 ("skill misurata contro la moneta invece che contro la media storica") |
| 2.5 | Holdout "~110 righe", "86% a n=40", "Brier 0,000 su holdout degeneri" | RIDIMENSIONATO | CERT_1 A3: mediana ~87-90 (limite basso dal codice dello split), media ~170, 43% dei modelli < 60 righe; 89% a n=40 (98% a n=20, 54% a n=87, 40% a n=110); Brier 0,000 NON riscontrato (min 0,2446 su over_2_5). Guardia `len(metrics_split) < 10` :401 CONFERMATA |
| 2.6 | Qualita' misurata: ML vs quote O2.5 +0,0191 [+0,0058; +0,0336], BTTS +0,0165 [-0,0013; +0,0358], 1X2 +0,0489 | CONFERMATO i punti, RIDIMENSIONATI gli IC | CERT_1 A2: O2.5 [+0,0051; +0,0337], BTTS [+0,0005; +0,0348] (con altro seme il BTTS e' al limite della significativita', non "n.s." netto), 1X2 log-loss ML 1,0081 / quote 0,9592 |
| 2.7 | "Nessuna miscela con peso > 0 sull'ML migliora le quote" | RIDIMENSIONATO | CERT_1 A2: 1X2 w=0,00; O2.5 w~0,05 senza guadagno; BTTS w=0,25 con guadagno 0,0008 (trascurabile ma non zero) |
| 2.8 | ML non batte la climatologia su O2.5/BTTS | CONFERMATO come punto, non significativo | CERT_1 A2: O2.5 ML-clim +0,0019 IC [-0,0144; +0,0186]; BTTS +0,0073 IC [-0,0097; +0,0253]. Scrivere "non distinguibile" |
| 2.9 | "Chi consuma l'ensemble: NON Omega, Mike, Safe" | CONFERMATO | `git grep -l model_predictions_json -- Betfair` (esclusi test/md): solo `betfair_report_manager.py`, `stream/scalper/bias_resolver.py`, `scalper_session.py`, `tools/misura_punto8/*`; Omega e Safe compaiono solo in .md. Fuori da Betfair/: `frontend/src/components/dashboard/MLPanel.tsx`, `frontend/src/lib/fixtureModels.ts`, `Telegram bot/.../index.ts`, `build_analytics_signals.py`, `master_backtest.py`, `Ai Engine/ai_engine/predict_fixture.py`/`serving_batch.py` |
| 2.10 | Scalper "bias_resolver.py:73-80" | CONFERMATO; riga | `bias_resolver.py:79-92` (`extract_1x2`: ML da `targets.target_1x2`, Poisson da `markets["1x2"]`) |
| 2.11 | Foglio "Quant Fund" non usato dai bot "secondo CRONOSTORIA 08/10" | CONFERMATO; data della riga non riletta | CRONOSTORIA.md:5384-5385 ("`money_management.py` e' il Quant Fund su Google Sheets (non usato dai bot; riscritto dal workflow settimanale)"); il report lo lancia l'utente a mano (`aggiorna_report.bat`, CRONOSTORIA.md:3607 "deve restare manuale", :3626) |
| 2.12 | Gate duplicato in money_management (stake pieno con BSS >= 0,12) | CONFERMATO | `money_management.py:629-657` (`BSS_FULL = 0.12`, `BSS_FLOOR = 0.05`); CERT_1 MA1: costante a tasso p => BSS=(1-2p)^2, passa sopra tasso 0,673 |
| 2.13 | Retrain "3 shard, 240 min" | RIDIMENSIONATO | `retrain_models.yml:79-81, 192` default 3 shard; `:92-94, 302` `time_budget_min` default 240 (smette di prendere NUOVE leghe, non e' il tetto del job). Il tetto del job (`timeout-minutes`) e' stato rivisto il 09/10 (CRONOSTORIA.md:5614-5617 "tetti dei job dalle durate misurate"): valore vigente NON riletto |
| 2.14 | `ml_calibration.yml` "gira ogni giorno e dopo il retrain" | RIDIMENSIONATO | senza cron dal 09/10: e' l'8 anello della catena, incrementale dopo il retrain (solo leghe riaddestrate), FULL il lunedi' (`ml_calibration.yml:11-15`; CRONOSTORIA.md:5586-5588) |
| 2.15 | 20.535 modelli, 1.027 leghe (registry) | NON VERIFICATO | registry non riletto; CRONOSTORIA.md:4888 dice "20.500 modelli", coerente |
| 2.16 | 409 cartelle di modelli locali vecchi | CONFERMATO nel numero; "alcuni con leakage" NON VERIFICATO | `ls "Ai Engine/models_cache"` = 409 voci (408 `league_*`) |
| 2.17 | FEATURES_VERSION "v2" costante | CONFERMATO | `seriea_model_export.py:50` |
| 2.18 | `oos_valid=True` scritto sempre | CONFERMATO | `build_analytics_signals.py:298`, `merge_engine_signals.py:203` |
| 2.19 | 13,2% (200/1.510) dei target ML con generated_at dopo il KO | CONFERMATO (GIA' NOTO), CAUSA SUPERATA | CERT_1 M1; CRONOSTORIA.md:4888; vedi 0.6 |
| 2.20 | ML-R12 "monitor di deriva non schedulato" e P7 "workflow nuovo" | RIDIMENSIONATO | `money_management.py:1333, 2608` `_auto_bss_check` ogni 7 giorni (CERT_3 B21). Non schedulato e' solo `bss_monitor.py` (CLI) |
| 2.21 | ML-R13 "fallback silenzioso sul modello vecchio" | RIDIMENSIONATO | `predict_fixture.py:795-799` `logger.warning("Using stale cached model")`: non silenzioso nel log; manca solo nel payload (CERT_3 B21) |
| 2.22 | ML-R6 "il modello non vede l'ultimo 25%" | CONFERMATO, SCELTA DI PROGETTO | CERT_1 M7: `seriea_model_export.py:234-243` commento M4; proposta di refit P4 in B_ml.md |
| 2.23 | ML-R4 `snapshot_time` NULL nel 100% di 1.500 righe | NON VERIFICATO | CERT_1 M6: il codice (`feature_pipeline.py:44-56`) conferma l'assenza di taglio d'orario, il 100% NULL non rifatto |
| 2.24 | ML-R14, ML-R15 | CONFERMATO per ML-R14 (B22), NON VERIFICATO per ML-R15 | CERT_3 B22; ambiente Keras/LogReg non riletto |
| 2.25 | Leakage classifiche di fine stagione risolto dal 16/06; Elo, H2H `< match_date` | NON VERIFICATO da me | non rilette `feature_pipeline.py:297-302, 479, 768-796`; CRONOSTORIA.md:4888 conferma solo "split temporale corretto, nessuna fuga" |
| 2.26 | "Il gate blocca gia' il 95% dei btts", "Brier mediano btts 0,5054", "23 modelli over_1_5 con Brier < 0,15" | NON VERIFICATO | registry (2.000 righe di H) non rifatto; il 02 dichiara il terzo non riprodotto |
| 2.27 | "I 5 gap di `CALIBRATION_RESEARCH.md` sono tutti ancora aperti" | NON VERIFICATO | file non riletto |

### Correzioni da applicare (02)
| punto | testo sbagliato -> testo giusto |
|---|---|
| par. 0 (a) e par. 4 | "holdout ~110 righe" / "86% a n=40" -> "holdout mediano ~90 e medio ~170 (43% sotto 60 righe); 89% a n=40" ; togliere "Brier 0,000 su holdout degeneri passano" (non riscontrato) |
| par. 3 | "Nessuna miscela con peso > 0 sull'ML migliora le quote" -> "peso ottimo 0 su 1X2, ~0,05 su O2.5, 0,25 su BTTS (guadagno 0,0008)"; IC BTTS ML-quote -> "[+0,0005; +0,0348], al limite" |
| par. 4 ML-R2, ML-R3, ML-R1, ML-R6, ML-R10 | gravita': R2 ALTO -> MEDIO-ALTO; R3 ALTO -> MEDIO-ALTO; R1 MEDIO-ALTO -> MEDIO; R6 -> BASSO-MEDIO + "scelta di progetto"; R10 -> BASSO (CERT_1) |
| par. 4 ML-R12 | "Monitor di deriva non schedulato" -> "`bss_monitor.py` non schedulato; `_auto_bss_check` del foglio controlla la deriva ogni 7 giorni (`money_management.py:1333, 2608`)" |
| par. 4 ML-R13 | "Fallback silenzioso" -> "fallback con warning nel log, non nel payload" |
| par. 1 e 0 | "bias_resolver.py:73-80" -> "bias_resolver.py:79-92"; "retrain_models.yml (3 shard, 240 min)" -> "3 shard di default, time-budget 240 min (tetto del job rivisto il 09/10, non riletto)"; "ml_calibration.yml gira ogni giorno" -> "ottavo anello della catena, incrementale dopo il retrain, FULL il lunedi'" |
| par. 4 ML-R5 e par. 2 ultima riga | aggiungere "causa rimossa dall'orologio del 09/10; rimisurare dopo il 10/10" |
| par. 1 | "pesi tempo emivita 365 gg" -> contrassegnare NON VERIFICATO (non ritrovato nel codice) |
| par. 2 | "13,2% ... " -> aggiungere "GIA' NOTO CRONOSTORIA.md:4888"; aggiungere GIA' NOTO anche ad A2, A3, MA1, MA2 (riferimento `AUDIT_2026-10-02/AUDIT_ML_POISSON.md`) |

---

## 3. File 04_FLUSSO_FINO_AL_CONSUMATORE.md

| # | affermazione | verdetto | prova |
|---|---|---|---|
| 3.1 | Unita' corrette lungo la catena (0-1, lambda gol FT, chiavi lette esistono) | NON VERIFICATO integralmente | rilette solo `stream/db.py:262-285` (chiavi `lambda_home/lambda_away`), `dossier.py:100-107`, `bias_resolver.py:79-92`; non ho rifatto la verifica di tutte le chiavi. Nessuna contraddizione trovata |
| 3.2 | "nessun bot legge `generated_at` (solo la UI, soglia 36 h)" | CONFERMATO per la parte bot | `git grep generated_at -- Betfair` (esclusi test/md): solo `stream/scalper/validazione_hazard/raccogli.py:131` (strumento). Soglia 36 h UI non riletta |
| 3.3 | Tattico arriva dopo il Poisson; Mike non rilegge il dossier | CONFERMATO | `today_predictions_backfill.py:2730-2752`; `mike/service.py:6945-6985` (CERT_1 M12). GIA' NOTO in parte: CRONOSTORIA.md:4888 ("un solo motore di lambda (3-4 gg)", non fatto) |
| 3.4 | 10-13% generato DOPO il KO | CONFERMATO (numero), CAUSA SUPERATA | vedi 0.6; 04 par. 0 e FL-5 vanno aggiornati |
| 3.5 | Riga lambda Poisson: Omega `stream/db.py:262-285` "dopo il tattico" | CONFERMATO ma frase ambigua | il codice legge PRIMA il tattico e poi il Poisson; "dopo il tattico" va scritto "il tattico ha la precedenza" |
| 3.6 | Safe: `opportunity.py:244-262` solo Poisson; catena fino a `DEFAULT_LAMBDAS` `bot_service.py:7892-7960` | CONFERMATO | `bot_service.py:7691` `DEFAULT_LAMBDAS = (1.35, 1.15)`, :7942/8010/8150 `source: "default"`; cache per event_id con ritentativi per i default deboli (:7897-7900) |
| 3.7 | `markets_calibrated` -> Mike veto U3.5 (acceso `config.py:152`) | CONFERMATO | vedi 1.26; veto in `mike/engine.py:3590-3640` (`valuta_veto_under35`) |
| 3.8 | `p_under35_cal`: assente -> "non_valutabile", veto tace | CONFERMATO | `engine.py:3594-3604` (`esito="non_valutabile"`, "nessun veto") |
| 3.9 | `p_over45_cal` MAI scritto, `over_4_5` mai prodotto | CONFERMATO | `dossier.py:69,76` (CERT_3 B25: nessun lettore; gravita' NESSUNA) |
| 3.10 | FL-1 `markets_calibrated` = identita' se la calibrazione non si carica | CONFERMATO (latente) | vedi 1.33 |
| 3.11 | FL-2 scalper: bias tra ML calibrato, Poisson GREZZO e mid non normalizzato, nessun controllo d'eta' | RIDIMENSIONATO | solo 1X2 (grezzo ~ calibrato +0,0003 RPS n.s.); ESITO_VERIFICA "FALSO sullo scalper" per O2.5; "nessun controllo d'eta'" e "mid non normalizzato" NON VERIFICATI (CERT_2 B6) |
| 3.12 | FL-3 .. FL-18: FL-15 (A1) | CONFERMATO | CERT_1 A1; file `live_order_worker.py` e `dutching.py` NON modificati dopo il 08/10 (git log): reperto ancora aperto |
| 3.13 | FL-14 anteprima dutching diversa dal server (esempio 2,5/3/4, pesi 1/2/1, UI 30,38/50,63/18,99, server 40,51/34,18/25,32) | CONFERMATO il difetto; esempi NON rifatti | CERT_1 M11 (formule diverse, esempi propri) |
| 3.14 | FL-12 drawdown 20 vs 30 | CONFERMATO | CERT_2 M18 |
| 3.15 | FL-13 lordo/netto UI (~5% del netto positivo) | CONFERMATO il difetto; "~5%" NON VERIFICATO | CERT_2 B15 |
| 3.16 | FL-16 minimi stake; "documentazione developer .it dice 2,00 (pagina forse stantia)" | CONFERMATO l'incoerenza di costanti; "forse stantia" e' SBAGLIATO: GIA' DECISO | CERT_2 M13; CRONOSTORIA.md:4790 (doc SMENTITO sul conto: punta 7,47 abbinata), 4792, 4793, 4947 |
| 3.17 | FL-6 euristica `v/100 se v>1` in "quattro punti" | RIDIMENSIONATO | CERT_3 B23: riletti 2 punti su 4 (`edge_scorer.py:202`, `betfair_report_manager.py:569`); nessun bot |
| 3.18 | FL-8 proxy O0.5 1T 0,559 vs 0,667 | RIDIMENSIONATO | CERT_3 B24: proxy attivo solo se manca `target_ht_over_0_5`, che esiste (`predict_fixture.py:345`); dormiente |
| 3.19 | FL-9 rho -0,13 senza traccia | RIDIMENSIONATO | scelta dichiarata (1.11) |
| 3.20 | FL-10 poisson_calibration senza paginazione, cache advisor senza scadenza | CONFERMATO la cache; paginazione NON VERIFICATA | CERT_3 B26 (aggiunta: dopo un errore di lettura `omega_advisor.py:309` mette None in cache) |
| 3.21 | FL-11 ROI dei lay su stake; FL-18 turnover pnl/roi | CONFERMATO | CERT_2 B3; CERT_3 B31 |
| 3.22 | FL-17 win rate tennis per ordine | NON VERIFICATO | CERT_2 B19 |
| 3.23 | FL-5 `oos_valid=True` fisso | CONFERMATO | 2.18 |
| 3.24 | par. 3 "Omega ha controlli d'eta' veri sui lambda (TTL, `saved_stale:`)" | CONFERMATO | `Betfair/omega/certificazione.py:224-232` (prefisso `saved_stale:`); `EMPIRICAL_CACHE_TTL_S = 6 h` (`omega_service.py:106`) riguarda le tabelle empiriche, non i lambda |
| 3.25 | par. 3 "Edge back netto commissione del foglio corretto", "analytics senza look-ahead" | NON VERIFICATO | non rilette |
| 3.26 | par. 4 "bot tennis: nessuna lettura di fixture_predictions" | NON VERIFICATO | `git grep model_predictions_json` su Betfair/ non mostra file tennis; `db_json_analisi` non cercato nei bot tennis |
| 3.27 | Intestazione: "dutching variable sul lato LAY piazza ordini BACK (ALTO)" | CONFERMATO | CERT_1 A1. Sfumatura da aggiungere: con pricing best/in_front e lato lay i prezzi sono quelli lay, l'ordine back resta probabilmente non abbinato: danno immediato non provato (serve flumine) |

### Correzioni da applicare (04)
| punto | testo sbagliato -> testo giusto |
|---|---|
| par. 0 Tempestivita' e FL-5 | "il 10-13% e' generato DOPO il calcio d'inizio (partite notturne UTC)" -> "il 10-13% (21/09-07/10, vecchio orologio con cron in ritardo di 300-370 min, CRONOSTORIA.md:5580) e' generato dopo il fischio; l'orologio del 09/10 (5586-5600) dovrebbe eliminarlo: rimisurare dopo il 10/10" |
| tab. riga lambda Poisson | "Omega (..., dopo il tattico)" -> "Omega (stream/db.py:262-285, il tattico ha la precedenza sul Poisson)" |
| FL-2 | "Poisson GREZZO ... nessun controllo d'eta'" -> "1X2 Poisson grezzo (praticamente uguale al calibrato sul 1X2); O2.5/BTTS non letti dallo scalper; controllo d'eta' e mid non normalizzato NON VERIFICATI" |
| FL-16 | "documentazione developer .it dice 2,00 (pagina forse stantia)" -> "doc Betfair dice 2,00 a multipli di 0,50, SMENTITO sul conto (punta 7,47 abbinata); regola decisa dall'utente: 1,00, multipli di 0,50 sopra l'euro, place-and-trim sotto (CRONOSTORIA.md:4790-4793, 4947); le 4 costanti UI a 2,00 sono piu' prudenti del motore" |
| FL-4 | gravita' BASSO -> NESSUNA (campo morto, CERT_3 B25) |
| FL-6 | "quattro punti" -> "due punti verificati su quattro" |
| FL-8 | aggiungere "dormiente: il target `ht_over_0_5` esiste" |
| FL-9 | aggiungere "rho di riserva = stima originale Dixon-Coles, dichiarata nel codice" |
| FL-15 | aggiungere "al 09/10 `live_order_worker.py` e `dutching.py` non modificati dopo il 08/10; il danno immediato non e' provato" |

---

## 4. File 06_PIANO_MIGLIORAMENTI.md

| n. | proposta / affermazione | verdetto | prova e correzione |
|---|---|---|---|
| intest. | "Safe tennis non risulta certificato" (n.23) | FALSO | CRONOSTORIA.md:5609-5618 (18/18, 0 violazioni, 09/10, codice 25cab047) |
| 1 | Bloccare dutching variable+LAY | CONFERMATO | CERT_1 A1; strumento manuale; la fase 2 e' in corso |
| 2 | Allineare l'anteprima | CONFERMATO | CERT_1 M11 |
| 3 | Cruscotto di qualita'; "sonde esistono gia' (lavori/sonde/m_*.py)" | CONFERMATO | `lavori/sonde/m_estrai.py`, `m_extra.py`, `m_dati.json` esistono. Aggiungere GIA' NOTO: CRONOSTORIA.md:4888 propone "pagella contro media storica e mercato (1-2 gg)" |
| 4 | Previsioni notturne prima del KO / marcatura | RIDIMENSIONATO | causa superata dall'orologio del 09/10 (CRONOSTORIA.md:5586-5600, approvato dall'utente); riscrivere: "rimisurare la % post-KO dopo la prima notte vera (10/10); marcatura `post_kickoff` e `oos_valid` fisso restano (`build_analytics_signals.py:298`, `merge_engine_signals.py:203`)"; togliere "[PERMESSO per un nuovo orario della catena]" (orario gia' deciso) |
| 5 | Gate ML con baseline climatologica; "694/1.009 modelli over_1_5 passano" | CONFERMATO la sostanza; il dato 694/1.009 NON VERIFICATO | CERT_1 MA1 (tasso 0,74 -> BSS 0,23 passa); il 06 stesso dice "non riprodotto da H" |
| 6 | Guardie numeriche "Elimina B1, B7, B27" | CONFERMATO B1, B27; B7 non rivalutato | CERT_2 B1, CERT_3 B27 |
| 7 | "Una sola costante dei minimi .it ... [DECISIONE UTENTE sulla regola]" | CONTRADDICE UNA SCELTA GIA' PRESA | regola decisa (CRONOSTORIA.md:4792, 4947). Riscrivere: "allineare le 4 costanti UI e l'auto-hedge (`risk_engine_worker.py:964`) a `minimi_it.py`; nessuna decisione sulla regola; gravita' BASSO (le costanti UI sono piu' prudenti)" |
| 8 | De-vig power/Shin, -0,0037/-0,0028 | NON VERIFICATO (numero) | non rifatto da CERT_2 B14; la proposta e' una DECISIONE UTENTE corretta |
| 9, 11, 12, 18 | Cambiano le P su cui sono tarate le soglie del veto Mike | CONFERMATO, SCELTA DOCUMENTATA | soglie `mike/config.py:153-156` da curva isotonica; veto acceso per decisione utente (CRONOSTORIA.md:3058, 3118); "il resto del veto resta com'e'" (`PIANO_MODIFICHE_MIKE_2026-09-29.md:114-116`). Giusto marcarle DECISIONE UTENTE; n.11 "~475 leghe" -> 1.12 |
| 10 | Prior inter-stagionale; "su n=528 il tattico RPS 0,2166 non migliore del principale 0,2135; la media 0,2111 in-sample" | NON VERIFICATO (numeri); GIA' NOTO l'indirizzo | CRONOSTORIA.md:4888 ("miglior modello nostro = TacticAI") contraddice in parte la lettura "tattico non migliore" su n=528 vs 90 giorni/25.330 partite: riportare entrambe le misure |
| 13-15, 24, 25 | ML: metriche, calibratori, refit, versioning, tempi | CONFERMATO come proposte | CERT_1 M7-M10 |
| 16 | Identificativo del modello nei consumatori | CONFERMATO | GIA' NOTO CRONOSTORIA.md:4888 ("un solo motore di lambda") |
| 21 | Monitor di deriva "[PERMESSO: workflow nuovo]" | RIDIMENSIONATO | esiste `_auto_bss_check` settimanale (`money_management.py:1333, 2608`); il nuovo monitor sarebbe per il Poisson/ML dei bot, non "il primo" |
| 23, 29 | Tennis Safe: "cambia il gate del bot"; "non risulta certificato" | RIDIMENSIONATO + FALSO | certificato (vedi intest.); il modello e' il cancello delle uscite IN PROFITTO (`bot_service.py:5295-5330`), gli ingressi sono regole dell'utente (`engine.py:1567-1715`); `auto_trade_tennis` False (`bot_service.py:193`). Riscrivere "cambia il cancello degli incassi" |
| 26 | Una sola regola commissione/tick | CONFERMATO (BASSO) | CERT_2 B9, B10 (196 su 99.900, non 263 su 400.000), B13; CERT_3 B35 |
| 28 | Foglio Quant Fund: niente ricalcolo retroattivo | RIDIMENSIONATO | CERT_3 B38: ricalcolo limitato agli slot del giorno, con `logger.info`; foglio manuale dell'utente; priorita' BASSA |
| 30 | Hazard: v4 al posto del v3 in Theta e ripieghi; media pesata al posto di max() in Mike; tabella Omega | PARTE FALSA/CONTRADDICE SCELTA DOCUMENTATA | max() di Mike = SCELTA DOCUMENTATA (`COSTITUZIONE_MIKE.md:157-158`, CERT_2 M20): TOGLIERE. Safe e Mike usano GIA' il v4 con ripiego v3 dichiarato (CRONOSTORIA.md:3045-3047, D2 "collegalo"); Theta e' opt-in (`theta_mode`, `theta_bot.py:546-551`, CERT_2 M19) e non e' nella decisione D2: resta solo Theta. Omega bucket: BASSO (finestra ft_entry_max 80, ~x1,3; CERT_2 M21) |
| 31 | Stop giornaliero al netto e stesso perimetro | RIDIMENSIONATO; PARTE GIA' DECISA | perimetro/esposizione = E34, "resta com'e'" (CRONOSTORIA.md:2956); stop di conto SPENTO di serie (`daily_stop_worker.py:124-134`, `betfair_live_risk_limits_v4.sql:15-21`); stop propri: Mike 50 acceso su regolato+bloccato (`mike/config.py:318`, `service.py:4447-4455`), Omega 0 spento; resta aperta solo la commissione (CRONOSTORIA.md:5384, 5632). Gravita' BASSO |
| 32 | Regole .it: tetto 10.000 EUR e back+lay | FALSO | tetto GESTITO `live_order_build.py:99, 875-886`; back+lay misti impossibili (una `Transaction` per ordine, flumine `markets/market.py:84-96`) - CERT_3 B39. TOGLIERE o ridurre a "estendere la guardia payout ai percorsi diretti dei bot (NON VERIFICATO che manchi)" |
| Ordine | "29 e 31 da portare subito all'utente (Safe tennis e stop giornaliero)" | FALSO come urgenza | Safe tennis certificato e senza ingressi dal modello; stop giornaliero deciso (2956) |

### Correzioni da applicare (06)
- n.4: sostituire il corpo con "rimisurare dopo la notte del 10/10; poi eventuale marcatura/esclusione"; rimuovere [PERMESSO].
- n.7: riscrivere come sopra (regola GIA' DECISA, solo allineamento costanti).
- n.21: "nessun monitor" -> "esiste `_auto_bss_check` settimanale nel foglio".
- n.23, n.29: togliere "Safe tennis non risulta certificato" e "cambia il gate del bot"; scrivere "cancello delle uscite in profitto, certificato 18/18 il 09/10".
- n.28: "storico P&L stabile (B38)" -> "limitato agli slot del giorno; BASSA".
- n.30: togliere "media pesata per varianza al posto di max() in Mike" (scelta documentata); precisare Theta opt-in e che Safe/Mike usano gia' v4.
- n.31: restringere alla sola commissione; togliere "stesso perimetro per realized e MTM" (E34 deciso); aggiungere "stop di conto spento di serie".
- n.32: come D17 (TOGLIERE).
- "Ordine consigliato": togliere 29 e 31 dalle urgenze all'utente.
- n.11: "~475 leghe" -> "499 in tabella meno 24".

---

## 5. File 07_RIEPILOGO_PER_L_UTENTE.md (ogni frase: e' un fatto certificato?)

| # | frase | verdetto | prova / correzione |
|---|---|---|---|
| 7.1 | "oltre 190 voci d'inventario" | NON VERIFICATO | `00_INVENTARIO_MATEMATICO.md` non contato da me (il contatore con le mie regole non ha trovato righe: formato diverso). Va ricontrollato o tolto il numero |
| 7.2 | "misurato la qualita' su 1.519 partite (21 settembre - 7 ottobre)" | CONFERMATO | sonda `cert4_calib.py` n=1.519; `A_poisson.md` dice 21/09-08/10: data finale da uniformare |
| 7.3 | "Nessun file toccato, nessun ordine piazzato, nessun bot avviato" | RIDIMENSIONATO | vero per file di produzione (git status: solo README/CRONOSTORIA), ma un delegato ha terminato tutti i `grep.exe` della macchina (DECISIONI, nota finale; CRONOSTORIA.md "Incidente" nel checkpoint 12:56): la frase iniziale va completata |
| 7.4 | "I conti che muovono i soldi sono giusti: green-up, P&L, commissione, puntate, scala" | RIDIMENSIONATO | generico: CERT_2/3 trovano discrepanze di centesimi (B9 arrotondamento, B10 pareggi di tick 196/99.900, B35 commissione archiviata < 1 EUR, B1 NaN) e il lordo/netto UI (B15). Scrivere "verificati a campione; differenze di centesimi documentate" |
| 7.5 | "un solo errore con soldi veri: dutching variabile LAY" | CONFERMATO | CERT_1 A1 (strumento manuale; danno immediato non provato) |
| 7.6 | "le quote prevedono meglio sia del nostro Poisson sia del nostro ML" | CONFERMATO, GIA' NOTO | CERT_1 MA2, A2; CRONOSTORIA.md:4888 |
| 7.7 | "il modello del tennis guarda solo il punteggio dei giochi" (riassunto e sez. 3) | RIDIMENSIONATO | fatto matematico vero (`tennis_opportunity._p_raw_p1`, `tennis_winprob.py:51`, `serve_data.csv` assente) ma e' il cancello delle uscite in profitto; ingressi = regole dell'utente; `auto_trade_tennis` False. Il bot E certificato (5609-5618) |
| 7.8 | "Manca un termometro: nessuno misura ogni settimana" | RIDIMENSIONATO | per RPS/log-loss del Poisson/ML: CONFERMATO (CERT_1 M2); ma `_auto_bss_check` controlla la deriva BSS ogni 7 giorni nel foglio (CERT_3 B21) |
| 7.9 | "errore medio piu' basso di circa il 7% sull'1X2" | CONFERMATO | RPS 0,2008 contro 0,2165 = -7,3% |
| 7.10 | "le quote usate nel confronto erano disponibili PRIMA della previsione: il confronto e' onesto" | RIDIMENSIONATO | `update` e' il timestamp di API-Football, non l'istante di quotazione (01 par. 7, NON VERIFICATO); scrivere "secondo il timestamp di API-Football" |
| 7.11 | "correlazione dei gol (rho) stimato per quasi tutte le leghe: si usa un numero fisso" | CONFERMATO, SCELTA DICHIARATA | 24 stimate su ~500; -0,13 = stima originale Dixon-Coles dichiarata nel codice |
| 7.12 | "dicono 17% dove succede 33%" | FALSO / da riscrivere | sonda: O2.5 grezzo previsto 16% osservato 30% (n=27), previsto 26% osservato 47% (n=81). Scrivere "dicono 16% dove succede 30%" |
| 7.13 | "la calibrazione settimanale aiuta, ma davvero solo sull'Over 2.5" | CONFERMATO | 1.24 |
| 7.14 | "motore tattico = Dixon-Coles con memoria; il principale e' piu' semplice" | CONFERMATO | `tactical_engine/model.py` (MLE, decadimento, ridge) vs `today_predictions_backfill.py:1493-1590` |
| 7.15 | "niente sbirciate nel futuro nella forma delle squadre, validazione in ordine di tempo" | CONFERMATO | `today_predictions_backfill.py:1475`; CRONOSTORIA.md:4888 ("split temporale corretto, nessuna fuga"); `temporal_split.py` |
| 7.16 | "il modello in produzione non aggiunge niente alle quote; su O2.5 e GG/NG non fa meglio della media" | CONFERMATO, non significativo | CERT_1 A2 (IC del confronto con la climatologia contengono 0): scrivere "non fa meglio in modo misurabile" |
| 7.17 | "il cancello ... campioni di circa 110 partite" | RIDIMENSIONATO | mediana ~90, media ~170 (CERT_1 A3) |
| 7.18 | "il cancello lo confronta con il lancio di una moneta" | CONFERMATO, GIA' NOTO | `confidence_gate.py:190-193`; CRONOSTORIA.md:4888 |
| 7.19 | "Le quote usate per addestrare non hanno l'orario" | NON VERIFICATO | CERT_1 M6: il codice non taglia per orario, il 100% NULL non rifatto. Scrivere "possono non avere l'orario" |
| 7.20 | "Il 13% delle previsioni pre-partita e' stato generato a partita gia' iniziata" | CONFERMATO come misura, CAUSA SUPERATA | vedi 0.6: aggiungere "con il vecchio orologio; da rimisurare dopo il 10/10" |
| 7.21 | "riaddestrare anche sugli ultimi mesi (oggi esclusi)" | CONFERMATO, SCELTA DI PROGETTO | CERT_1 M7 |
| 7.22 | "Omega, Mike e Safe NON usano questo ML; lo usano scalper, foglio Quant Fund, UI, statistiche" | CONFERMATO | 2.9, 2.11 |
| 7.23 | Sez. 3: "il tennis di Safe ... ignora i punti del game e chi e' piu' forte" | RIDIMENSIONATO | vedi 7.7 |
| 7.24 | "l'atlante gol vecchio (v3) e' ancora usato da Theta" | RIDIMENSIONATO | vero (`theta_bot.py:546-551`) ma Theta e' opt-in (`theta_mode`); Safe/Mike usano il v4 (CRONOSTORIA.md:3045-3047) |
| 7.25 | "Mike prende sempre la stima piu' alta tra due" (come sotto-livello) | SCELTA DOCUMENTATA | `COSTITUZIONE_MIKE.md:157-158` ("comanda la fonte piu' prudente"): togliere dalle "debolezze" |
| 7.26 | "Lo stop giornaliero conta i guadagni prima della commissione (scatta tardi)" | RIDIMENSIONATO | codice lordo CONFERMATO (`daily_pnl.py:49-55`); ma stop di conto spento di serie (NULL), E34 deciso (2956), stop Mike 50 su regolato+bloccato |
| 7.27 | "regole .it (vincita massima 10.000 EUR, minimo 2 EUR) non gestite o in contrasto (codice usa 1 EUR: da verificare con prova vera)" | FALSO | tetto gestito (`live_order_build.py:99, 875-886`); minimo 1 EUR e' la regola decisa dall'utente (CRONOSTORIA.md:4790-4793, 4947), che ha vietato altre operazioni di prova |
| 7.28 | "Le schermate mostrano numeri diversi (drawdown, ROI lay, lordo/netto)" | CONFERMATO (BASSO) | CERT_2 M18, B3; CERT_2 B15 |
| 7.29 | "Per eseguire si', per decidere no" | NON UN FATTO | giudizio di sintesi: marcare come tale |
| 7.30 | Sez. 4 "nessun bot controlla quanto e' vecchia la previsione" | RIDIMENSIONATO | nessun bot legge `generated_at` (3.2), ma Omega marca `saved_stale:` i lambda persistiti oltre il limite (`omega/certificazione.py:224-232`) |
| 7.31 | Sez. 4 "un bot non sa se i gol attesi vengono dal tattico o dal Poisson" | CONFERMATO | CERT_1 M12 |
| 7.32 | Top 10 n.2 "Safe tennis (D2, CORRETTO dal coordinatore)" | INCOERENTE con D2 | 07 dice "Il bot E certificato"; D2 e l'intestazione di DECISIONI dicono il contrario |
| 7.33 | Top 10 n.7 "Stop giornaliero al netto" e n.8 "prova vera minimo .it" | GIA' DECISO | 2956; 4947 |
| 7.34 | Top 10 n.6 "Previsioni delle partite notturne prima del fischio (D20)" | SUPERATO | 0.6 |
| 7.35 | Top 10 n.10 "media pesata al posto del massimo in Mike (D6)" | SCELTA DOCUMENTATA | 7.25 |
| 7.36 | "05: 4 ALTI, nessun CRITICO" | FALSO dopo CERT | solo A1 e' ALTO (A2/A3 MEDIO-ALTO, A4 MEDIO, MA1 MEDIO) |
| 7.37 | "32 proposte" (06), "23 decisioni" | CONFERMATO i conteggi | 06 ha n.1-32; DECISIONI D1-D23. Dopo le correzioni il numero delle decisioni scende (vedi sez. 6) |
| 7.38 | "limiti: misure su 17 giorni; modelli cloud non scaricati; regole .it non provate; vigenza SQL dedotta" | CONFERMATO (con riserva) | "regole .it non provate" e' superato per minimo e tetto (decisi/gestiti) |

### Correzioni da applicare (07)
- Riga "La risposta in tre righe" n.1: "I conti che muovono i soldi sono giusti" -> "verificati a campione; differenze di centesimi documentate (B9, B10, B35); un solo errore con soldi veri (dutching variabile LAY, strumento manuale)".
- n.2: "il modello del tennis guarda solo il punteggio dei giochi" -> "il modello di probabilita' del tennis (usato solo come cancello delle uscite in profitto di Safe tennis) guarda solo il punteggio dei giochi".
- Sez. 1: "(dicono 17% dove succede 33%)" -> "(dicono 16% dove succede 30%, su 27 partite; 26% contro 47% su 81)".
- Sez. 2: "campioni di circa 110 partite" -> "campioni di circa 90 partite (mediana), molti sotto 60"; "Le quote usate per addestrare non hanno l'orario" -> "potrebbero non averlo (da verificare)"; "il 13% ... a partita iniziata" -> aggiungere "(fino al 07/10; l'orologio del 09/10 dovrebbe eliminarlo: da rimisurare)".
- Sez. 3: togliere "Mike prende sempre la stima piu' alta tra due" (scelta documentata); "Theta" -> "Theta, se acceso (opt-in)"; "Lo stop giornaliero..." -> "Lo stop di conto e' spento di serie; il suo conto e' lordo di commissione"; "regole .it (...)" -> togliere (tetto gestito; minimo deciso).
- Sez. 5: riscrivere n.2 (coerente con D2 riscritta), n.6 (rimisurare dopo il 10/10), n.7 (solo commissione), n.8 (togliere: regola decisa), n.10 (solo Theta).
- "Dove leggere": "4 ALTI, nessun CRITICO" -> "1 ALTO (A1), nessun CRITICO"; "23 decisioni" -> numero dopo la sez. 6.
- Aggiungere all'apertura l'incidente `grep.exe` (gia' in DECISIONI).

---

## 6. File DECISIONI_PER_L_UTENTE.md: decisione per decisione

Criterio (b): una decisione si TOGLIE se poggia su un reperto FALSO o su una scelta gia' presa dall'utente; si RISCRIVE se la premessa e' in parte vera.

| D | esito | motivo (prova) |
|---|---|---|
| intest. | RISCRIVERE | "Safe tennis non risulta certificato; nessun replay lanciato oggi" e' FALSO: replay Safe tennis 18/18 OK il 09/10 11:47-12:10 (CRONOSTORIA.md:5609-5618). Scrivere "Safe tennis e' certificato sul codice 25cab047" (promemoria dovuto dalle regole: dire lo stato di certificazione) |
| D1 | TENERE | A1 CONFERMATO (CERT_1); aggiungere "il danno immediato non e' provato, ordine back a prezzo lay resta probabilmente non abbinato"; fase 2 in corso |
| D2 | RISCRIVERE | premessa vera solo in parte: P(vittoria) dai soli giochi con hold 0,75/0,75 e' CONFERMATA (0,9238 sullo 0-40; la P attraversa 0,90 al variare degli hold, CERT_1 A4), ma agisce solo sul cancello delle uscite in profitto (`bot_service.py:5295-5330`); gli ingressi sono regole dell'utente (`engine.py:1567-1715`); `auto_trade_tennis` False (`bot_service.py:193`, CRONOSTORIA.md:1101); il bot e' certificato. "Spegnerlo finche' il modello non usa..." non e' proporzionato: la domanda vera e' "vuoi che il modello (hold per giocatore, punti del game) regoli il cancello degli incassi?" (06 n.29) |
| D3 | RISCRIVERE | la parte "stesso perimetro conto/strategia, esposizione aperta" e' E34: DECISIONE UTENTE "resta com'e'" (CRONOSTORIA.md:2956). Resta: "commissione nello stop?" (non deciso: CRONOSTORIA.md:5384, 5632). Precisare: stop di conto spento di serie (NULL) |
| D4 | RISCRIVERE come informazione | veto acceso per decisione utente (CRONOSTORIA.md:3058, 3118) e "il resto del veto resta com'e'" (`PIANO_MODIFICHE_MIKE_2026-09-29.md:114-116`); "il Poisson perde dalle quote" e' GIA' NOTO dal 02/10 (CRONOSTORIA.md:4888, "Nessuna modifica fatta"). Domanda reale: "vuoi la misura del veto fuori campione (proposta 4888, 1-2 gg)?" |
| D5 | TENERE, aggiungere riferimento | M12 CONFERMATO; GIA' NOTO CRONOSTORIA.md:4888 ("un solo motore di lambda 3-4 gg", non fatto) |
| D6 | TOGLIERE | SCELTA DOCUMENTATA (`COSTITUZIONE_MIKE.md:157-158`: max fra atlante e modello amplificato, "comanda la fonte piu' prudente"; CERT_2 M20, ESITO_VERIFICA). Al piu' una nota BASSO "1,25 non calibrato" |
| D7 | RISCRIVERE | Safe e Mike gia' sul v4 con ripiego v3 dichiarato (CRONOSTORIA.md:3045-3047); Theta opt-in, non nella decisione D2 (CERT_2 M19). Domanda residua: solo "Theta sul v4?"; "-44% a 88-89'" NON rifatto |
| D8 | RIDURRE a nota | M21 BASSO: finestra d'ingresso 80 (v3 85), bias ~x1,3 in finestra, e tende a togliere ingressi (prudente) (CERT_2 M21); "x1,57 a 89'" cade fuori dalla finestra |
| D9 | RISCRIVERE | lo scalper legge solo il 1X2 (grezzo ~ calibrato, +0,0003 RPS n.s.); "su O2.5/BTTS nemmeno il tasso base" riguarda il ML ma non entra nello scalper; ESITO_VERIFICA: FALSO sullo scalper. Lo stato di certificazione dello scalper calcio non e' riverificato qui (CRONOSTORIA.md:4943 "non certificato" il 04/10, poi cantiere 4965: verificare l'ultima riga prima di citarlo) |
| D10 | TOGLIERE | nessun bot usa la convenzione "sempre" (`value_engine/bivariate.py`: solo UI/Telegram); `live_engine_pro.py:58-72` e' scelta documentata (CERT_3 B28) |
| D11 | TENERE | M17 CONFERMATO (CERT_2), nessuna decisione trovata; "si scrive, non si cambia" |
| D12 | TENERE con riserva | numero -0,0037 non rifatto; e' una decisione di strategia legittima |
| D13 | TENERE, ridurre | MA1 MEDIO; consumatore = foglio (non bot), CRONOSTORIA.md:5384-5385; GIA' NOTO 4888 |
| D14 | RISCRIVERE | foglio manuale dell'utente (CRONOSTORIA.md:3607); B38 limitato agli slot del giorno, con log (CERT_3); la domanda "e' ancora usata?" resta valida |
| D15 | TENERE (BASSO) | consigli UI su ML senza valore oltre il mercato: fatto CONFERMATO |
| D16 | TOGLIERE | GIA' DECISO: CRONOSTORIA.md:4792 ("L'UTENTE ha corretto il mio 2,00 prudente: punta minima 1,00"), 4947 ("SOPRA 1 EURO, MULTIPLI DI 0.50 FUNZIONANO ... Non sei autorizzato a fare operazioni"), 4790 (doc 2,00 SMENTITO). Resta 06 n.7 (costanti UI) |
| D17 | TOGLIERE | FALSO: tetto gestito, back+lay misti impossibili (CERT_3 B39). Eventuale residuo "guardia payout sui percorsi diretti" NON VERIFICATO |
| D18 | RIDURRE | nessuna decisione trovata (git grep aliquota: solo CRONOSTORIA.md:4666, aliquota per riga); "fonti 4,5% o 5%" (03 sez. 7) non rilette; il conto usa la commissione vera. Tenere solo se confermata da una fonte |
| D19 | TENERE, correggere | processo nuovo, serve permesso; aggiungere che esiste `_auto_bss_check` settimanale (CERT_3 B21) |
| D20 | RISCRIVERE | causa gia' rimossa dall'orologio approvato il 09/10 (CRONOSTORIA.md:5586-5600); nuova decisione: "rimisurare dopo il 10/10 e poi marcare/escludere i residui" |
| D21 | TENERE | migrazioni a mano dell'utente; M15, M18, B3 BASSO |
| D22 | TENERE (BASSO) | 409 voci (408 `league_*`) CONFERMATO; "alcuni con leakage" NON VERIFICATO |
| D23 | TENERE, riscrivere | "snapshot_time NULL" NON VERIFICATO (CERT_1 M6); scrivere "se l'orario manca" |
| Nota finale | CONFERMATO | incidente grep.exe riportato anche in CRONOSTORIA (checkpoint 12:56 del 09/10, riga "Incidente") |

### Decisioni da togliere/riscrivere (sintesi)
- TOGLIERE: D6, D10, D16, D17.
- RISCRIVERE: intestazione, D2, D3, D4, D7, D9, D14, D20 (+ D8 ridotta a nota, D18 ridotta, D23 e D19 con correzioni).
- Restano 15-17 decisioni vive (D1, D5, D11, D12, D13, D15, D19, D21, D22, D23 piu' le riscritte D2, D3, D4, D7, D9, D14, D20).

---

## 7. Controlli obbligatori del brief

(a) Stato di certificazione/attivazione, riscontro CRONOSTORIA:
- Safe tennis: CERTIFICATO 18/18, 09/10 (CRONOSTORIA.md:5609-5618). Il 04/10 Safe girava con `variants=["tennis"]` live (CRONOSTORIA.md:5040-area e sez. 2026-10-04, "Safe running/live"); `auto_trade_tennis` propone soltanto dal 17/09 (CRONOSTORIA.md:1101).
- Mike veto U3.5: acceso di default per decisione utente (3058, 3118); Mike in live "va sorvegliato a mano" il 04/10 (4943): stato di certificazione di Mike oggi NON riverificato da me.
- Theta: nessuna riga di certificazione/attivazione in CRONOSTORIA (git grep); opt-in via `theta_mode` (CERT_2 M19).
- Stop giornaliero: E34 deciso (2956); stop di conto spento (NULL); lordo di commissione = verifica "DA FARE" (5632).
- Foglio Quant Fund: "non usato dai bot" (5384-5385), manuale (3607, 3626).
(b) Decisioni basate su reperto FALSO / scelta gia' presa: sez. 6.
(c) Proposte di 06 che contraddicono scelte documentate: n.7 (minimi), n.30 (max Mike), n.31 (E34), n.32 (tetto gestito), n.23/29 (certificazione).
(d) Frasi di 07 non fatti certificati: sez. 5 (7.1, 7.3, 7.4, 7.7, 7.8, 7.10, 7.12, 7.17, 7.19, 7.20, 7.23-7.27, 7.29, 7.30, 7.32-7.36).

## 8. NON VERIFICATO (riepilogo)
Valore vigente di `timeout-minutes` del retrain; pesi tempo emivita 365; registry (20.535 modelli, 95% btts bloccati, 23 over_1_5); leakage classifiche e H2H; tabella `poisson_calibration` DB (500 righe); chi ha lanciato il tattico alle 09:55 del 09/10; power/Shin -0,0037; numero di voci dell'inventario; stato attuale di certificazione di Mike e dello scalper calcio; `daily_loss_limit` effettivo sul DB; fonti 4,5%/5% della commissione; se `snapshot_time` e' NULL al 100%.
