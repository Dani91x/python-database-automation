# X - Revisione di coerenza delle consegne 00-06 (audit 09/10/2026, sola lettura)

Perimetro: 00_INVENTARIO, 01_CATENA_POISSON, 02_CATENA_ML, 03_COMPONENTI, 04_FLUSSO, 05_ERRORI, 06_PIANO.
Criteri: BRIEF_COMUNE.md + BRIEF_AUDIT_MATEMATICA_ML.md par. 3 e par. 6. Nessuna consegna modificata.
Metodo: lettura integrale di 00-06; verifica a campione di 20 citazioni file:riga di 05 non marcate [C] con sed sul
codice (R); sonda Python in sola lettura (`lam_from_prematch(NaN)`, `devig_pair(2,1)`); grep mirati dentro
ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML/ (mai sulla radice); lettura per indice di ARCHITETTURA_2026-10/08_REVISIONE_CRITICA.md e
03_SCHEDE_COMPONENTI/G_DATI_E_ALGORITMI_DEL_CLOUD.md.

## A. Problemi (numerati; file | punto | problema | correzione suggerita)

### A1. Coerenza di gravita' e di numeri

1. **00 (appendice "gravita' finale", righe ~364-374) e 03 par. 14 (riga 552)** | "Unico reperto ALTO finale: E2-2 (+ B-R3)" /
   "uno solo: E2-2" | 05 ha TRE ALTO (A1 = E2-2, A2 = B-R2 + M, A3 = B-R3); 00 tiene B-R2 a "MEDIO (H)" (anche nelle righe
   ML-13, ML-12) mentre 02 (ML-R2 "ALTO (previsioni)") e 05 lo portano ad ALTO dopo le misure di M. 03 par. 14 vale solo per il perimetro
   03 ma e' scritto come assoluto. | Aggiungere in 00 una colonna/riga "gravita' FINALE = 05" e correggere B-R2; in 03 scrivere
   "nel perimetro 03".
2. **05 intestazione (criteri) vs corpo** | la legenda definisce 4 livelli (CRITICO/ALTO/MEDIO/BASSO) ma il corpo usa anche
   "MEDIO-ALTO", "BASSO-MEDIO", "BASSO/MEDIO", "MEDIO-BASSO" senza definirli; il brief (par. 3) chiede 4 livelli. | Definire i
   livelli intermedi nella legenda o mappare ciascuno a uno dei 4.
3. **05 A3 (gate ML, ALTO)** | la legenda dice "ALTO = soldi veri a rischio su un percorso vivo (anche manuale) oppure previsioni pubblicate senza
   valore informativo"; ma 00 (appendice) e 02 dicono che il gate pesa solo sulla traccia ML del foglio Quant Fund ("non usata dai bot"), e
   MA1 (stesso gate, baseline uniforme) e' MEDIO-ALTO "impatto ridotto". A3 e MA1 descrivono lo stesso gate con gravita' diverse
   senza dire perche'. | Motivare A3 con il criterio (effetto su UI `targets_not_reliable`/scalper) oppure declassarlo; riferire A3 e MA1 l'uno all'altro.
4. **Gravita' intermedie diverse tra file per lo stesso reperto**: (a) B5 = BASSO in 05, ma 01 P-R8 e 00 A-R7 "BASSO-MEDIO";
   (b) M18 (drawdown) = "MEDIO" nella tabella 05 ma "MEDIO-BASSO" in 00, 03, 04 (FL-12) e nella stessa riga; (c) M15 = MEDIO in 05,
   "MEDIO/BASSO" in 00/03; (d) B15 (lordo/netto) = BASSO in 05, "BASSO/MEDIO" in 00/03 (D-R8); (e) FL-1/B7 coerenti, FL-2/B6 coerenti.
   | Allineare a 05 e dichiarare "rivisto dal coordinatore" dove si scosta da H/V2.
5. **Collisioni di identificativi**: 01 usa P-R1..P-R14 ma P-R6 (post-kickoff) non e' A-R6 (rho = P-R7); 02 usa ML-R1..R15 ma ML-R5 e'
   nuovo, quindi 05 M7 "B-R5" = ML-R6, M8 "B-R6" = ML-R7, M9 "B-R7" = ML-R8, M10 "B-R8" = ML-R10; 04 usa FL-n con FL-5 = "post-kickoff" nella
   sez. 2 ma la riga della tabella 1 "target ML" cita FL-5 per la post-calibrazione in try/except, mentre 05 B25 cita "F-5" (chiavi mai lette);
   01 par. 6 usa "M1..M11" e 02 "P1..P10" per le PROPOSTE mentre 05 usa "M1..M18" per i REPERTI e 06 numera 1..25. Un lettore non puo' incrociare
   senza i file lavori/. | Tabella di concordanza ID (01/02/04 -> 05 -> 06) in 05 o in 00; rinominare le proposte di 01/02 con prefisso proprio.
6. **Reperto in 04 assente in 05/02**: 04 tab. 1, riga "target ML": "post-calibrazione in try/except: errore -> probabilita' invariate senza
   traccia" (predict_fixture.py:870-909). Non compare in 04 sez. 2, 02 (ML-R8 parla di post-cal non valutata, non del silenzio dell'errore) ne' in 05
   (B21 cita solo il fallback sul modello vecchio, :795-799). | Aggiungere un reperto BASSO-MEDIO in 05 (e in 04 sez. 2) o toglierlo dalla tabella.
7. **Reperti di 03 assenti in 05** (05 dichiara "Tutti i reperti delle consegne 01-04"): E2-12 (cash-out Mike esclude le gambe `archived` dalla base
   commissione, engine.py:776, "fino a 0,20"), E2-14 (xhedge: media non pesata sulle 81 celle), E2-11 (colonna `commission` aliquota in una RPC e importo in
   un'altra), "euristica xG di edge_scorer (+-|spearman|*0,10)" e "edge MI in punti di probabilita' non confrontabile fra quote" (03 par. 3, 9, 12; M14 copre
   solo bias e Wald), ricalcolo retroattivo del P&L dei vinti con la commissione ATTUALE (money_management.py:1357-1372, 03 par. 13 D-R5; B4 non lo cita),
   tetto 10.000 EUR di vincita e rifiuto back+lay nello stesso placeOrders "NON VERIFICATO che il codice non li violi" (03 par. 4; manca anche nel
   "non verificato trasversale" di 05). | Aggiungere una riga a 05 per ciascuno o scrivere esplicitamente "non riportato perche' ...".
8. **05 B8 e 03 par. 4 (Kelly del foglio)**: "minimo 1,00 dopo il tetto (scatta solo con bankroll < 50)". Contraddetto dall'esempio dello stesso 03:
   p=0,515 @2,0 bankroll 1000, k=0,10 -> Kelly 0,45 -> stake 1,00 (x2,2). A bankroll < 50 il floor SUPERA IL TETTO del 2%; ma il floor gonfia ogni
   stake Kelly < 1 a qualunque bankroll (money_management.py:812, :875 e riduzioni BSS riportate a 1,00, gia' notato in 03 riga 197). | Riformulare B8
   ("il floor 1,00 gonfia gli stake piccoli a qualsiasi bankroll; supera il tetto solo sotto 50") e riconsiderare la gravita' (solo traccia Sheets).
9. **05 B15 / 03 par. 5 / 04 FL-13 (percentuali)**: "hedge stesso mercato sottostimato del 2,6%" (05) = 0,244 EUR su un profitto di 9,5 (2,6% del profitto,
   0,244% dello stake; 03 scrive "0,244 EUR su 100 (2,6%)" ambiguo); 04 scrive "~5% del netto positivo" (5,00 lordo = 4,75 netto, altro fenomeno).
   | Indicare sempre il denominatore.
10. **03 par. 7 vs 00 SQL-18**: l'espressione della commissione in `get_tennis_bot_daily` e' scritta in due modi diversi: 03 "`coalesce(pnl_betfair, pnl -
   commission)` (commission e' un IMPORTO)", 00 "`coalesce(commissione_betfair, commission, 0)`". Uno dei due e' impreciso (non riaperto in questa revisione:
   migrations/tennis_bot_daily_giorno_partita_2026-09-30.sql:55-60). | Riaprire il file e allineare.
11. **05 A2 (ML senza valore informativo)**: titolo e impatto dicono "senza valore informativo misurabile / peggio del tasso base", ma (a) su 1X2 il modello
   batte la climatologia (1,0081 vs 1,0463) - la stessa riga lo ammette; (b) su O2.5 la differenza dalla climatologia e' +0,0019 (0,6905 vs 0,6886) e su BTTS
   +0,0072, senza IC (gli IC citati sono ML vs QUOTE: O2.5 [+0,0058;+0,0336], BTTS [-0,0013;+0,0358] che include 0). "Peggio" non e' dimostrato, "non migliore" si'.
   | Scrivere "su O2.5 e BTTS non migliore della climatologia (diff +0,0019/+0,0072, IC non calcolato)"; ripetere in 02 par. 0(a).
12. **06 n. 5**: "oggi il 69% dei modelli over_1_5 passa senza skill". Il numero esiste solo in B_ml.md:152; la base e' 694/1009 modelli del registry che passano il gate
   di Brier (<0,44) con BSS reale vs tasso base ~ +0,04 (B_ml.md:114), quindi "senza skill" e' eccessivo; H non ha riprodotto over_1_5 (query non
   eseguita, H_verifica:8); il dato non e' in 02 ne' in 05. | "69% (694/1009, B, non riverificato da H) passa il gate con BSS vs tasso base ~ +0,04" oppure toglierlo.
13. **06 n. 10 (prior inter-stagionale / DC-MLE)**: premessa e numeri mal riportati. A_poisson.md:123: su n=528 RPS tattico 0,2166 (PEGGIORE del principale 0,2135 e
   del grezzo 0,2142), quote 0,2032, media(tattico, principale) 0,2111 (differenza 0,0024, non testata). 06 scrive "ensemble misurato meglio dei singoli (0,2111 vs
   0,2135, n=528)" senza dire che il tattico singolo e' peggiore; inoltre 0,2135 coincide con l'RPS dell'ML su n=1.509 (02/05: 0,2135) e con 0,2165 del Poisson su
   n=1.509 (01): tre numeri su tre campioni diversi, facili da confondere. | Riportare la quaterna n=528 e marcare "stima, diff non testata"; dichiarare i due campioni.
14. **06 n. 11 e 01 P-R7**: "~475 leghe" (06: "stima") e' un conteggio che H ha dichiarato NON VERIFICATO (H_verifica:18); 05 B2 non lo usa, 06 si'. | "(conteggio non verificato)".
15. **05 intestazione**: "La matematica dei bot Omega, Mike, Safe (green-up, P&L, commissione, Kelly, tick) e' corretta sui conti fatti a mano" e 04 par. 0 "chiavi lette dai bot
   esistono con lo stesso nome nel DB reale" / "unita' corrette lungo tutta la catena": il secondo poggia su 1 SELECT LIMIT 5, il primo su formule gia' elencate con residui
   NON VERIFICATI (regola arrotondamento commissione, `settle_group` non chiamata da V2, bot_service 11.458 righe lette 5200-5290, tennis, Telegram, runner.py:482).
   | Aggiungere "sui consumatori letti" e rinviare al par. "non verificato trasversale".

### A2. Criteri di accettazione (brief par. 6)

16. **Citazioni di ARCHITETTURA_2026-10/: ZERO** in tutti e sette i file (grep case-insensitive su ARCHITETTURA_2026, 07_MISURE, 08_REVISIONE, 03_SCHEDE, G_DATI = 0 ovunque).
   Il criterio "riletti e citati, dove utili" non e' soddisfatto. Tre punti dove citare: (a) **02 par. 2, riga "quote di chiusura come feature / snapshot_time NULL"** e 05 M6 ->
   `ARCHITETTURA_2026-10/03_SCHEDE_COMPONENTI/G_DATI_E_ALGORITMI_DEL_CLOUD.md` riga 136 (football_data_scraper: nessun workflow, scrive `match_odds` 92,5 M righe/20 GB,
   `max(snapshot_time)` in timeout 8 s) e riga 45 (`fix_snapshot_time.py`): spiega perche' l'orario non e' misurabile e dice chi scrive la tabella; (b) **00 par. 9 (WF-09) /
   01 par. 2 (calibrazione settimanale) / 02 par. 1 (ml_calibration)** -> G par. 1.5 righe 125-129 (freschezza misurata: poisson_calibration `generated_at` 05/10,
   ml_post_calibration 08/10, cron GitHub dell'epoca - da riconciliare con 00 che dal 09/10 dichiara pg_cron); (c) **06 n. 3, 4, 21 (nuovi script/workflow che leggono il DB)** ->
   G riga 54 (`statement_timeout=8s` sul ruolo authenticator) e 08_REVISIONE_CRITICA par. 2.2 (H24) / par. 2.4 (affermazioni senza fonte) e 07_MISURE_OGGI par. 4 (carico),
   come vincolo di costo/timeout della metrica. (Di 08 ho letto solo l'indice: la pertinenza dei rilievi va riverificata.)
17. **Ogni componente di 00 compare in almeno una scheda 01-04?** NO per costruzione: la colonna "scheda" di 00 rimanda a lavori/A..F, non a 01-04. Grep sui nomi dei componenti dentro 01-04:
   assenti X-23 `valuta.py` (conversione GBP->EUR dei libri, tutti i bot; in E "corretto, da non toccare"), X-22 `esposizione_fuori_bot`, X-21 `controls.py`/liability pre-invio,
   SQL-23 `omega_transitions_*` (alimenta Omega V3), SQL-16 `analyze_feature`, SQL-21/22 viste ROI (`v_roi_by_track`...), AN-01 `analytics_settlement` (solo come "D30" nel testo), AN-02
   `analytics_market_stats` (solo come "D31"), FE-08 `journalStats`, P-24/P-29 (atlante: solo "NON VERIFICATO"), WF-10/ML-16 `validate_walkforward` (solo in 06). | Aggiungere a 00 una colonna
   "dove in 01-04" e, in 03, un'appendice "verificato corretto / non analizzato" per i componenti residui.
18. **xG (elencato esplicitamente nel brief par. 1.3)**: 00 non ha una riga dedicata (xG compare dentro P-02/P-03/AN-03); 03 par. 9 ammette "nessun lavoro lo valuta come formula a se'";
   01 marca il blend gol/xG 0,6/0,4 "NON VERIFICATO tarato" e non valuta copertura/qualita' dei dati xG ne' lo stato dell'arte (nessuna fonte); 02 conta 0 occorrenze di xG nelle feature ML.
   | Riga di inventario + paragrafo con verdetto (anche "non valutato" con motivo).
19. **Par. 1.3 del brief ("massimo livello? meglio? omesso? soluzione migliore per performance e risultati?")**: 03 da' per ogni componente "Verdetto" + "Si puo' fare meglio?", ma manca per
   componente "abbiamo omesso qualcosa?" e "e' la soluzione migliore?"; 03 par. 14 non ha queste colonne e non c'e' un verdetto di sintesi (a)-(d) come in 01 e 02 par. 0. (07 non e' nel perimetro
   di questa revisione.) | Aggiungere un blocco di verdetti 1.3 (a-d) in 03 o dichiarare che stanno in 07.
20. **Reperti di 05 senza file:riga completo** (criterio: "ogni reperto ha file:riga e gravita'"): B16 (dailyHistory.ts senza riga), B19 (`get_tennis_bot_daily` senza riga; in 00 SQL-18 e' :55-60),
   B20 (ventaglio_segnali.py senza riga; 00 AN-12 :216-262), B21 (elo_ratings.py; bss_monitor.py senza riga), B25 (rinvio a "F-5"), B31 (report_mm.py senza riga; analytics.ts:494 ok), B10 (order_exec.py; flumine
   senza riga), B15 (solo ladderMath.ts:10 completo). Gravita' presente ovunque. | Copiare le righe da 00/03.
21. **06: proposte senza metrica**: n. 13 (metrica "-"), n. 21 ("-"), n. 24 ("-"). Il brief: "nessuna proposta senza metrica di misura". | n. 13: log-loss/RPS/ECE per lega con IC sul campione M; n. 21: giorni
   di ritardo nel rilevare un guasto simulato + falsi allarmi/settimana; n. 24: % modelli con hash dataset/versioni tracciabili e riproduzione dello stesso modello a parita' di seed.
22. **06 non copre reperti che 03/01/02 propongono di correggere**: P3 di C (una sola funzione di commissione di mercato, B9), P2 di C (una sola funzione tick, B10/B12), P7 di C (`commission_rate`
   default 0,05 nel backtest, B13), etichetta lordo/netto nei due "chiudi-ora" (B15), ripiego tennis 0,7917 (B18, 06 n. 23 cita solo il tie-break), persistere AH/CS (01 par. 6 M11 / B29), B20, B24, B30.
   | Fascia "igiene" in 06 con metrica oppure dichiarare "non proposti perche' BASSO".
23. **06: stime di guadagno non marcate "stima"**: n. 15 ("0,001-0,004 log-loss") senza misura ne' fonte; n. 9 ("verso 0,685") e n. 10 ("0,002-0,004 RPS" in A) sono stime del delegato; solo l'8 e l'11 hanno
   base misurata (M, sonda H 1,24 pp). | Marcare "stima di A/B, non misurata".
24. **Metodo di ricerca/copertura**: solo 00 ha la sezione di metodo e i conteggi; 04 (che deve tracciare "ogni numero mostrato in UI o usato da un bot") ha 22 righe e nessuna dichiarazione di copertura
   (Telegram, bot tennis, runner.py:482, ml_post_calibration non verificati, par. 4). | Aggiungere in 04 il metodo (grep usati: `db_json_analisi`, `markets_calibrated`, ...) e il denominatore ("22 numeri su N").

### A3. Citazioni file:riga (campione, vedi sez. B) - correzioni

25. **`value_engine/devig.py:93-100`, `:93-110`, `:103-110`** (00 P-13, 01 P-R11, 05 B14 e B27): il file ha 29 righe in totale. `devig_multiplicative` = 12-19, `devig_pair` = 22-29 (il ritorno
   della probabilita' grezza con quota opposta <=1 e' alle righe 25-26: la sostanza di B27 e' vera, la riga no). | Correggere in 12-19 / 22-29.
26. **`Ai Engine/ai_engine/seriea_model_export.py:437`** (05 A3; ripreso da B e H "CONFERMATO"): la guardia unica `len(metrics_split) < 10` e' a :401 (commento a :417); a :437 c'e' `if _cal_proba is not None:`
   (celle di calibrazione). | :401.
27. **`Prediction/today_predictions_backfill.py:1593-1594`** (05 MA2; 01 diagramma e par. 5; 00 P-03 "1500-1594"; A): `lambda_home`/`lambda_away` sono a :1589-1590 (1593-1594 sono commenti). | :1589-1590.
28. **`Betfair/safe_strategy/execution.py:1997`** (05 B11; 00 TR-02 "HEDGE_EPS :1997"): :1997 e' `def hedge_state(`; `HEDGE_EPS = 0.01` e' a :1919 e la tolleranza `abs(win-lose)<0.05` a :2023. | :1919 / :2023.
29. **`betfair_report_manager.py:568`** (05 B23): `p = prob / 100.0 if prob > 1 else prob` e' a :569 (errore di 1). **`bias_resolver.py:188`** (05 B6): e' il ramo "prob di mercato mancante"; il Poisson GREZZO
   e' a :86-90 (corretto), mentre il mid non normalizzato nasce in scalper_session.py:1399-1447. | Correggere o scrivere "~".

### A4. Affermazioni "allineato / stato dell'arte" senza fonte esterna aperta

30. **03 par. 4 (Kelly)**: "frazioni 0,10 (K1) e 0,25 (K2) ALLINEATE" con fonte "MacLean-Thorp-Ziemba 2011 (FONTE NON APERTA): frazioni 1/4-1/2". 0,10 e' FUORI dall'intervallo citato; la fonte e' da memoria.
   | "K2 allineata; K1 piu' prudente della forchetta citata (non verificata)".
31. **03 par. 5 (green-up "ALLINEATO")**: Bet Angel/Geeks Toy senza URL ne' pagina aperta. **03 par. 7 (commissione "ALLINEATO")**: fonte non indicata nel paragrafo e l'aliquota reale (5% vs 4,5%) e' dichiarata non
   risolvibile. **03 par. 8 (tick "ALLINEATO per CLASSIC")**: la pagina Betfair "Price Increments" NON e' stata aperta (WebFetch vuoto), solo snippet di ricerca. | Marcare "[RICERCA]/da memoria" accanto ad ALLINEATO.
32. **01 par. 0(d) e par. 4 ("tattico = Dixon-Coles 1997 completo: pratica allineata")** e **02 par. 5 ("walk-forward/purged CV: allineato", Lopez de Prado 2018)**: entrambe FONTE NON APERTA, citate da memoria; 01 la
   formula DC l'ha verificata numericamente (1,7e-7), 02 no. | Aprire la fonte o marcare "allineato (da memoria)".
33. **03 par. 10 ("hazard CORRETTO, processo di Poisson non omogeneo")**, **par. 11 ("la formula chiusa e la ricorsione sono lo standard"; Klaassen-Magnus "non in R, non cercato")**, **par. 3 ("convenzione dei trader (R)")**,
   **02 par. 0(a) ("L'ingegneria e' buona")**: giudizi di stato dell'arte senza fonte. | Citare una fonte o riscrivere come "coerente con la formula standard (nessun confronto esterno)".
34. **02 par. 5** (Walsh-Joshi 2024: numeri da snippet, NBA) e **01 par. 4** ([ricerca] su Boshnakov, Baio-Blangiardo, Koopman-Lit, Constantinou-Fenton): letti solo negli estratti; il limite e' dichiarato in 01 par. 7 ma i verdetti
   "indietro" ne dipendono. | Gia' dichiarato: nessuna correzione, solo non trasformarli in "misurato".

## B. Esito del campione (20 citazioni di 05 non [C], aperte con sed sul codice; R = radice)

| # | Reperto | Citazione | Esito |
|---|---|---|---|
| 1 | A2 | predict_fixture.py:1051-1089 | CONFERMATA (:1051 `model_predictions_json = {`, `"model_name": "ensemble_v2"`; :1089 `update` su fixture_predictions) |
| 2 | A3 | seriea_model_export.py:437 | **NON CORRISPONDE**: guardia `len<10` a :401 (vedi n. 26) |
| 3 | MA1 | money_management.py:629-657 | CONFERMATA (`brier_random=(n_cls-1)/n_cls`, `bss=1-brier/brier_random`, blocco <0,05, scala 0,05-0,12) |
| 4 | MA2 | today_predictions_backfill.py:1593-1594 | IMPRECISA (+4 righe: :1589-1590, vedi n. 27); formula `max(0.05, league_avg*attack*def)` corretta |
| 5 | M6 | feature_pipeline.py:35-82 | CONFERMATA (`pick_value`: senza `snapshot_time` usa la mediana di tutte le righe; 1X2/OU/BTTS) |
| 6 | M10 | seriea_model_export.py:50, :698 | CONFERMATA (`FEATURES_VERSION = "v2"`; `"features_version": FEATURES_VERSION`) |
| 7 | M13 | risk_engine_worker.py:964; XHedgePanel.tsx:40 | CONFERMATE (`_AUTOHEDGE_MIN_STAKE_IT = 2.0`; `MIN_STAKE_IT = 2.0` in components/live/XHedgePanel.tsx, percorso abbreviato in 05) |
| 8 | B6 | bias_resolver.py:86-90, :188 | :86-90 CONFERMATA (Poisson = `db_json_analisi.markets["1x2"]`, grezzo); :188 solo in parte (ramo "prob mercato mancante") |
| 9 | B12 | scalper_bot.py:278; tennis_scalper_bot.py:147 | CONFERMATE (`ticks_between(..., max_ticks=200)` -> None oltre) |
| 10 | B13 | run_backtest.py:56-69 | CONFERMATA (docstring "P&L netto" su `order.simulated.profit`; il carattere lordo viene da flumine, non riaperto qui) |
| 11 | B18 | bot_service.py:5233 | CONFERMATA (`ha, hb = estimate_holds(0, 0, 0, 0)`) |
| 12 | B27 | poisson_total.py:51-61 | CONFERMATA, e verificata con sonda: `lam_from_prematch('over', 2, nan)` = 50.0 |
| 13 | B27 / B14 | value_engine/devig.py:103-110 / :93-100 | **FALSE**: il file ha 29 righe (vedi n. 25); la sostanza (`devig_pair(2.0, 1.0)` = 0,5, cioe' 1/o grezza) confermata dalla sonda |
| 14 | B32 | omega_engine.py:236-245 | CONFERMATA (minimo applicato DOPO l'arrotondamento al target) |
| 15 | M17 | live_engine_pro.py:414-440 | CONFERMATA (`_kelly_lay` ritorna lo stake: `max(0,f)*fraction*bankroll`) |
| 16 | B11 | greenup.py:109; execution.py:1997 | greenup :109 CONFERMATA (`full = round(diff_abs / price, 2)`); execution :1997 IMPRECISA (n. 28) |
| 17 | B23 | edge_scorer.py:202; betfair_report_manager.py:568 | :202 CONFERMATA (`v/100.0 if v > 1.0`); report :569 (errore di 1) |
| 18 | M14 | edge_scorer.py:330 | CONFERMATA (area: `implied_prob = fair_implied.get(mkey, 1.0/odd)`, cioe' la de-viggata; il bias viene da calibration.py) |
| 19 | B26 | poisson_calibrator.py:100-112 | CONFERMATA (`select("league_id,corrections")` senza paginazione) |
| 20 | M12 | stream/db.py:262-285; mike/dossier.py:76, :81-107 | CONFERMATE (prima `tactical_engine_json`, poi `db_json_analisi.inputs`, nessun id del modello; `p_over45_cal: None`; `p_under35_fonte` "calibrated"/"raw") |

Riepilogo: 20 citazioni, 14 confermate senza riserve, 3 confermate con riga imprecisa (4, 16, 17), 1 parziale (8), 2 NON corrispondenti o false (2, 13). Nessuna smentita nella SOSTANZA del reperto; gli errori
sono di numero di riga (probabile deriva del file dopo la lettura dei delegati o copia di H dal delegato: H "CONFERMATO" a :437 ripete la riga di B).

## C. Cosa NON ho verificato in questa revisione
- Le formule e le cifre delle sonde (rinvio a H/V2/03 par. 15); il contenuto di 08_REVISIONE_CRITICA oltre l'indice; l'espressione SQL del n. 10; i consumatori Telegram/tennis.
- Che 06 n. 5/10/11 siano le sole proposte con premessa discutibile: ho incrociato solo i numeri 69%, 0,2111/0,2135, 475.
