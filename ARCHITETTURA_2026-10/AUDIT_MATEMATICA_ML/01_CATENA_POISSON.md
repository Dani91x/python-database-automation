# 01 - CATENA POISSON: dai dati grezzi alla probabilita' usata (audit 09/10/2026)

> Certificato in fase 2 (09/10/2026): correzioni da lavori/fase2/CERT_*.md;
> le gravita' finali valgono in 05_ERRORI_DI_PROGETTAZIONE.md;
> le frasi non verificate sono marcate NON VERIFICATO.

Sintesi del coordinatore. Fonti: `lavori/A_poisson.md` (delegato A), `lavori/M_misure.md` (misure su 1.519
partite), `lavori/H_verifica_avversaria.md` e `lavori/V2_verifica_avversaria.md` (verifiche avversarie),
`lavori/F_flusso.md` (consumatori), `lavori/R_stato_arte.md` (fonti esterne). Sola lettura: nessun file di
produzione toccato. Le righe `file:riga` marcate [C] le ho riaperte io (coordinatore); le altre sono state
riaperte da almeno un verificatore (H o V2) oppure sono marcate NON VERIFICATO.

## 0. Verdetti (domande del brief, par. 1.1)

| Domanda | Verdetto | Prova principale |
|---|---|---|
| (a) Siamo al miglior livello matematico possibile? | **NO** | La matematica e' corretta (tre implementazioni Dixon-Coles coincidono con un riferimento numpy/scipy entro 1,7e-7), ma l'informazione usata e' povera: sullo stesso campione di 1.509 partite (21/09-07/10) le quote de-viggate battono il Poisson calibrato di 0,0156 di RPS 1X2 (0,2008 contro 0,2165; IC95 della differenza [+0,0110; +0,0204]) e di 0,053 di log-loss. Nessuna miscela quote+Poisson migliora le sole quote (peso ottimo 0,0 anche in validazione a 5 fold). |
| (b) Abbiamo omesso qualcosa? | **SI'** | Mancano: quote di mercato come prior; forza degli avversari nel motore principale; memoria tra stagioni (niente previsione prima di 5 partite per squadra); misura continua di qualita' (RPS/log-loss mai calcolati sul Poisson in produzione); rho stimato per ~95% delle leghe (fallback -0,13; fallback dichiarato, DC 1997). La sovradispersione (dispersione misurata 1,14) e' INFO e non un'omissione (A_poisson.md:166). [cert. fase 2] |
| (c) Si puo' migliorare? | **SI'** | Undici proposte con metrica (sez. 6). Le piu' redditizie: cruscotto di qualita' contro le quote (costo basso, prerequisito), prior dalle quote (tocca strategie: decisione utente), pesi di forma meno estremi, prior inter-stagionale, rho stimato. |
| (d) Sono le migliori pratiche? | **IN PARTE** | Il motore tattico e' un Dixon-Coles 1997 completo (MLE congiunta, decadimento temporale, ridge, rho vincolato): pratica allineata. Il motore PRINCIPALE, quello che i bot leggono, e' invece un impianto attacco x difesa a medie mobili della sola stagione, senza stima congiunta: indietro rispetto alla letteratura (Dixon-Coles 1997, Baio-Blangiardo 2010, Koopman-Lit 2015, Egidi-Pauli-Torelli 2018). |

## 1. Diagramma della catena (verificato)

```
API-Football (raccoglitori, catena notturna in fila avviata da pg_cron 00:12 UTC: Daily -> Mapping -> Today Predictions -> Results -> Hazard -> Catchup -> Retrain -> Post-Cal -> Weekly Poisson il lunedi'; ordine approvato dall'utente il 09/10, CRONOSTORIA.md:5598-5600) [cert. fase 2]
  -> tabelle matches, match_team_stats (xG), match_events, fixture_predictions, raw_json_odds
       |
       +-- [P1] MOTORE PRINCIPALE "poisson_xg_hybrid_dc"
       |     Prediction/today_predictions_backfill.py::compute_db_json_analisi
       |     cache per (lega, stagione CORRENTE) :1210-1230 [C]; forma squadra solo con partite < fixture_date :1474-1478 [C]
       |     finestre 5/10/15 pesi 0,5/0,3/0,2; shrink k=8 verso media lega; blend gol/xG 0,6/0,4
       |     lambda_h = max(0.05, Lh*att_h*dif_a); lambda_a = max(0.05, La*att_a*dif_h)   (:1589-1590)
       |     griglia 11x11 x tau DC (rho per lega, altrimenti -0,13) -> rinormalizzata -> 1X2, O1.5/2.5/3.5, BTTS, HT
       |     -> fixture_predictions.db_json_analisi.{inputs, markets}
       |
       +-- [P2] CALIBRAZIONE  poisson_calibrator.py (fattore per bin 0,1 = hit/avg_prob, cap [0,2; 3,0], rinormalizza)
       |     fattori da generate_dynamic_cal.py (tabella poisson_calibration, 499 leghe + globale) ogni lunedi'
       |     seconda copia: update_poisson_calibration.py --apply -> CALIBRATION_TABLE in Betfair/money_management.py
       |     terza copia: dynamic_cal.json nel checkout (money_management la usa prima della tabella statica)
       |     -> db_json_analisi.markets_calibrated (+ calibrated_at, calibration_source)
       |
       +-- [P3] MOTORE TATTICO DC-MLE  tactical_engine/model.py:103-223 (modello); parametri in tactical_engine/serving.py:46,48 (HALF_LIFE_CLUB 420, RIDGE 0,08; campo neutro 1500); default di classe model.py:87-88 = 1800 / 0,05, non usati [cert. fase 2]
       |     log lh = c + a_i - d_j + g ; pesi exp(-ln2/420 * giorni) ; ridge 0,08 ; L-BFGS-B ; rho vincolato su tutte le coppie
       |     -> fixture_predictions.tactical_engine_json (calcolato DOPO il principale, nello stesso script: today_predictions_backfill.py:2730-2752; misurato NULL alle 09:55 UTC del 09/10 col vecchio ordine, NON VERIFICATO oggi; da rimisurare dopo la notte del 10/10) [cert. fase 2]
       |
       +-- [P4] STRATO QUOTE / IN-PLAY  value_engine/ (devig, poisson_total, bivariate=Dixon-Coles, goal_timing, pricing)
             quote -> de-vig moltiplicativo -> lambda dal mercato (bisezione) -> probabilita' condizionate al minuto
             (CDF empirica di 120.542 gol) -> usato da Omega, Safe, live_engine_pro, Telegram (port TS calc.ts)

CONSUMATORI (F_flusso.md tab. 1):
  Mike: markets_calibrated.over_3_5 -> veto U3.5 (ACCESO di default PER DECISIONE UTENTE, CRONOSTORIA.md:3058, 3118; Betfair/mike/config.py:152 [C]) [cert. fase 2]; lambda tattico-o-Poisson + rho della riga
  Omega: lambda tattico-o-Poisson (stream/db.py:262-285), rho dal file locale dc_rho_by_league.json
  Safe: lambda SOLO Poisson nel percorso fixture_match; ht_ratio
  Scalper calcio: markets["1x2"] GREZZO contro ML calibrato e mid di mercato (bias BACK/LAY); legge solo il 1X2, dove grezzo e calibrato differiscono di +0,0003 RPS (n.s.) [cert. fase 2]
  money_management (foglio Quant Fund): markets grezzi + calibrazione propria (dynamic_cal.json o tabella statica)
  UI: PoissonPanel, TacticalEnginePanel; analytics/direzione; Telegram
```

## 2. Formule effettive e parametri (origine)

| Parametro | Valore | Origine | Tarato? |
|---|---|---|---|
| Finestre di forma | 5/10/15 partite, pesi 0,5/0,3/0,2 (peso effettivo ultime 5 = 0,72) | today_predictions_backfill.py:1494 (weights) [cert. fase 2] | NON VERIFICATO: nessuna procedura di taratura trovata; GIA' NOTO e dichiarato by design (AUDIT_2026-09-24/AUDIT_TAB_DASHBOARD_2026-09-24.md:82, AUDIT_2026-10-02/AUDIT_ML_POISSON.md:218) [cert. fase 2] |
| Shrinkage | k=8 verso media lega | :1522 (k_shrink), :1525-1527 (_shrink) [cert. fase 2] | no |
| Blend gol/xG | 0,6/0,4 (vale solo con xG presente: se manca si usa SOLO il gol, 'Policy (user-confirmed)' :1568-1570) [cert. fase 2] | :1523 (eta_goals), :1577-1584 (_coef) [cert. fase 2] | no |
| Minimo partite | 5 per squadra, altrimenti nessuna previsione | :1534-1540 (H) | - |
| rho Dixon-Coles | 24 leghe con stima propria (media -0,081), altre -0,13 | dc_rho_by_league.json, generate_dc_rho.py (min 300 partite, shrink K=300 verso -0,13) | stima MLE con shrink, solo 24 leghe; scelta dichiarata: DC 1997 come fallback globale (today_predictions_backfill.py:1147-1148) [cert. fase 2] |
| Troncamento | 10 gol FT (massa persa 3e-7 a lambda 1,4/1,1), 4 gol HT (~0,4% a lambda_HT 1,0, rinormalizzata) | :1131-1206, :1673 | adeguato |
| HT ratio | prior 0,45 (empirico 0,4348), shrink k=12, banda [0,25; 0,65] | :1640-1690 | parziale |
| Tattico | emivita 420 gg, ridge 0,08, campo per lega | tactical_engine/serving.py:46,48 (HALF_LIFE_CLUB 420, RIDGE 0,08; HALF_LIFE_NEUTRAL 1500); default di classe model.py:87-88 = 1800/0,05, non usati [cert. fase 2] | NON VERIFICATO (nessuna griglia di taratura trovata; indizio: AUDIT_2026-09-25/TACTICAI_P00_NEGATIVA_2026-09-25.md:170, 202-203 osserva che ridge ed emivita valgono per tutte le leghe) [cert. fase 2] |
| Calibrazione | bin 0,1, cap [0,2; 3,0], min_n 30, shrink per lega K=75, monotonicita' solo nella copia dinamica | generate_dynamic_cal.py:354-436; update_poisson_calibration.py | stima settimanale, parzialmente in-sample |

Tau Dixon-Coles (almeno cinque copie: value_engine/bivariate.py, tactical_engine/dixon_coles.py, today_predictions_backfill.py:1196-1206 [C], omega_model.py:275, omega_advisor.py:93; CERT_3 B28) [cert. fase 2]:
tau(0,0)=1-lambda*mu*rho, tau(0,1)=1+lambda*rho, tau(1,0)=1+mu*rho, tau(1,1)=1-rho. Corretta (Dixon & Coles 1997).
Le prime tre copie hanno regole di clamp diverse (il clamp delle altre due NON VERIFICATO) [cert. fase 2] (solo `bivariate` clampa ovunque; `dixon_coles.score_matrix` non clampa;
`today._dc_tau` clampa solo (1,0)/(0,1)); con i parametri reali nessuna diventa negativa (sonda `a_poisson_sonda.py`).

## 3. Calibrazione e validazione: cosa si misura oggi

- In produzione nessuna metrica propria viene calcolata sul Poisson: `master_backtest.py:1056-1160` calcola Brier e
  log-loss solo per la traccia ML; `valida_motore_poisson.py` lavora su 18 fixture fisse (`DEFAULT_FIDS` a :28 e :96; r.20-24 sono import; `master_backtest.py` e' manuale: MANUALE_OPERATIVO.md:227-233, nessun workflow). RPS compare solo in validate_walkforward.py:41,80 (ML in training), mai sul Poisson (CERT_1 M2). [cert. fase 2] Reperto A-2 confermato da V2.
- Misura fatta in questo audit (M_misure.md, campione B, n=1.509 1X2 / 1.006 O2.5 / 1.014 BTTS):

| Mercato | Quote (molt.) | Quote power/Shin | Poisson grezzo | Poisson calibrato | Climatologia |
|---|---|---|---|---|---|
| 1X2 log-loss / RPS | 0,9592 / 0,2008 | 0,9555 / 0,2001 (power) | 1,0128 / 0,2168 | 1,0119 / 0,2165 | 1,0463 / 0,2301 |
| Over 2.5 log-loss | 0,6714 | 0,6733 | 0,6948 | 0,6846 | 0,6886 |
| BTTS log-loss | 0,6790 | 0,6801 | 0,6835 | 0,6799 | 0,6883 |

  Controllo CERT_1 MA2 (n=1.518): RPS 1X2 Poisson grezzo 0,2172, calibrato 0,2169, quote 0,2009; calibrato-quote +0,0160 IC [+0,0112; +0,0206]; grezzo-calibrato +0,0003 IC [-0,0005; +0,0011]. Numeri sopra CONFERMATI entro il campione; GIA' NOTO (CRONOSTORIA.md:4888: 'il MERCATO batte ML, Poisson e TacticAI su tutti i 13 bersagli'). [cert. fase 2]

  Letture: (1) il Poisson ha skill reale sulla climatologia in 1X2 (-0,034 log-loss); (2) su Over 2.5 il Poisson
  GREZZO non e' distinguibile dalla climatologia (+0,0063, IC [-0,0145; +0,0270]; CERT_1 M3) e solo il calibrato la batte, di poco (0,6846 contro 0,6886); [cert. fase 2] (3) la
  calibrazione aiuta in modo significativo solo su O2.5 (-0,0103 [-0,0177; -0,0035]); su 1X2 e BTTS l'effetto non si
  distingue da zero; (4) su BTTS il Poisson calibrato e' indistinguibile dalle quote: e' l'unico mercato dove il
  modello e' al livello del mercato.
- Pendenza di calibrazione O2.5: 0,44-0,47 grezza, 0,58-0,60 calibrata (CERT_1 M3, due stimatori; quote 0,83-0,85); i valori di fase 1 (0,53+-0,08; V2 0,55+-0,13; 'dopo calibrazione 0,81') sono superati. Le probabilita' grezze sono troppo estreme (reperto A-3 = P-R3: BASSO dopo CERT_1 M3, direzione confermata). [cert. fase 2] Reliability grezza O2.5 (sonda CERT_4): bin 0,0-0,2 previsto 16,2% osservato 29,6% (n=27); bin 0,2-0,3 previsto 25,8% osservato 46,9% (n=81). [cert. fase 2]
- Limite delle misure: 17 giorni; bookmaker di riferimento = "Betfair" Sportsbook di API-Football (1.519/1.519), non
  l'exchange; orario delle quote VERIFICATO (lavori/Q_orario_quote.md): unico scrittore today_predictions_backfill.py:893 e 2375-2395,
  righe 'ok' mai riscritte (:2455-2459); `update` delle quote mediana 8,0 h prima del calcio d'inizio, 0/1.519 dopo la
  generazione della previsione (le quote sono ~2 h PIU' VECCHIE della previsione), 20/1.519 dopo il KO di ~1 minuto.
  Ripetuto il confronto solo con quote disponibili alla previsione e previsioni pre-KO (n=1.309): Poisson calibrato
  +0,057 log-loss [0,042; 0,073] peggio delle quote: la conclusione regge e il confronto NON e' sbilanciato. Bootstrap iid, nessuna correzione per lega/giornata.

## 4. Confronto con lo stato dell'arte

| Tema | Stato dell'arte (fonte, vedi R_stato_arte.md) | Noi | Verdetto |
|---|---|---|---|
| Dixon-Coles + decadimento xi | Dixon & Coles 1997, Applied Statistics 46(2) (FONTE NON APERTA, formula verificata numericamente) | Tattico: si'. Principale: no (medie mobili) | in parte |
| Poisson bivariata | Karlis & Ntzoufras 2003, JRSS-D 52(3) (FONTE NON APERTA) | assente; `bivariate.py` e' un Dixon-Coles (nome fuorviante) | indietro, impatto atteso basso |
| Sovradispersione / Weibull count | Boshnakov-Kharrat-McHale 2017, IJF 33(2) [ricerca]: miglior adattamento e rendimento positivo fuori campione | assente; dispersione misurata 1,14 | indietro, priorita' bassa-media |
| Bayesiano gerarchico | Baio & Blangiardo 2010, J. Appl. Stat. 37(2) [ricerca] | shrinkage informale (k=8, ridge 0,08) non stimato | in parte |
| Rating dinamici | Koopman & Lit 2015, JRSS-A 178(1) [ricerca]; pi-ratings Constantinou-Fenton 2013 [ricerca] | forza costante con decadimento | indietro |
| Quote come prior | Egidi-Pauli-Torelli 2018, arXiv 1802.08848 [aperta]: tassi di gol come combinazione convessa di storico e quote; Strumbelj 2014: le quote sono la previsione piu' accurata disponibile | assente | **indietro (il gap piu' grande)** |
| De-vig | Clarke-Kovalchik-Ingram 2017; Strumbelj 2014 (Shin migliore della normalizzazione) [ricerca] | solo moltiplicativo; misurato: power/Shin migliori su 1X2 (-0,0037/-0,0028 log-loss, significativo; NON VERIFICATO, numero non rifatto da CERT_2 B14) [cert. fase 2] | indietro, correzione economica |
| Metriche | RPS (Constantinou-Fenton 2012); Wheatcroft 2021 (arXiv 1908.08980, aperta) preferisce la log-loss | nessuna metrica continua | indietro |
| Calibrazione | isotonica/Platt/beta fuori campione (scikit-learn docs, aperta) | bin discreti, fattori per classe ricombinati, in parte in-sample | in parte |

## 5. Reperti della catena (gravita' finale dopo verifica)

| id | Gravita' | Reperto | file:riga | Stato verifica |
|---|---|---|---|---|
| P-R1 | MEDIO-ALTO (CERT_1 MA2: nessun cambio) [cert. fase 2] | Il Poisson non usa le quote e perde contro di esse (RPS +0,0156 su n=1.509); un "edge" Poisson contro quote e' in media errore del modello | today_predictions_backfill.py:1589-1590 | confermato da H e da M (campione intero); CERT_1 MA2: CONFERMATO, GIA' NOTO (CRONOSTORIA.md:4888; n=1.518: RPS +0,0160, IC [+0,0112; +0,0206]) [cert. fase 2] |
| P-R2 | MEDIO (CERT_1 M2: nessun cambio) [cert. fase 2] | Nessuna misura continua di qualita' (RPS/log-loss/ECE) del Poisson | master_backtest.py:1056-1160; valida_motore_poisson.py:28,96 (DEFAULT_FIDS), :79 (bucket); master_backtest.py e' manuale (MANUALE_OPERATIVO.md:227-233, nessun workflow) [cert. fase 2] | confermato V2; CERT_1 M2: CONFERMATO; la proposta di pagella e' GIA' NOTA (CRONOSTORIA.md:4888, non fatta) [cert. fase 2] |
| P-R3 | BASSO (prima MEDIO; CERT_1 M3) [cert. fase 2] | Probabilita' grezze troppo estreme (pendenza 0,44-0,47 su O2.5 grezza, 0,58-0,60 calibrata: CERT_1 M3) [cert. fase 2] | :1493 (weights) [cert. fase 2] | confermato V2 fuori campione; causa (pesi) NON provata; CERT_1 M3: RIDIMENSIONATO - grezzo contro climatologia non significativo (+0,0063, IC [-0,0145; +0,0270]); lo scalper legge il 1X2 grezzo (bias_resolver.py:79-92), non l'O2.5, e sul 1X2 grezzo ~ calibrato (+0,0003 RPS n.s.); 'confermato fuori campione' NON rifatto [cert. fase 2] |
| P-R4 | BASSO (prima MEDIO; CERT_1 M4) [cert. fase 2] | Niente memoria tra stagioni: nessuna previsione prima di 5 partite/squadra, neopromosse senza prior | :1210-1230 [C], :1534-1540 | confermato H; CERT_1 M4: CONFERMATO nel codice (:1210-1220, :1534-1540), effetto NON VERIFICATO [cert. fase 2] |
| P-R5 | BASSO (prima MEDIO; CERT_1 M5) [cert. fase 2] | Nessun aggiustamento per forza degli avversari nel principale | :1500-1594 | confermato H; il tattico che lo fa non risulta migliore su n=528 (non conclusivo); CERT_1 M5: RIDIMENSIONATO - modello a rapporti classico, scelta di modello, distorsione NON misurata; i numeri su n=528 sono NON VERIFICATI e CRONOSTORIA.md:4888 ('miglior modello nostro = TacticAI', 90 gg/25.330 partite) li contraddice in parte: riportare entrambe le misure [cert. fase 2] |
| P-R6 | MEDIO (CERT_1 M1: nessun cambio) [cert. fase 2] | 10,5% (160/1.519, periodo 21/09-07/10, vecchio orologio con cron GitHub in ritardo mediano 300-370 min, CRONOSTORIA.md:5580-5581) delle previsioni Poisson generate DOPO il calcio d'inizio: non sono previsioni pre-partita ma entrano nelle tabelle di calibrazione e nelle statistiche [cert. fase 2] | M_misure.md par. 3 | misurato su 1.519 partite; nessun auto-leak sulla forma squadra (filtro < fixture_date, :1474-1478 [C]); la media di lega puo' includere la partita stessa: effetto minimo, NON misurato; CERT_1 M1: CONFERMATO il numero, GIA' NOTO (CRONOSTORIA.md:4888); cause rimosse dall'orologio del 09/10 (CRONOSTORIA.md:5580-5600): rimisurare dopo il 10/10 [cert. fase 2] |
| P-R7 | BASSO (prima BASSO-MEDIO; CERT_2 B2) [cert. fase 2] | rho -0,13 di riserva per tutte le leghe tranne 24 (nessuna delle 5 maggiori); con -0,13 invece di -0,081 il pareggio sale di 1,24 pp | dc_rho_by_league.json; :1148, :1186-1189 | confermato H (conteggio "475 leghe" NON VERIFICATO: sono 499 leghe in tabella di calibrazione meno 24 stimate, non il numero di leghe con previsioni); CERT_2 B2: CONFERMATO, SCELTA DICHIARATA (DC 1997 come fallback globale, today_predictions_backfill.py:1147-1148, banda [-0,25; 0,05]) [cert. fase 2] |
| P-R8 | BASSO (prima BASSO-MEDIO; CERT_2 B5) [cert. fase 2] | Tre versioni "calibrate" dello stesso numero (DB rinormalizzata, dynamic_cal.json, tabella statica) con regole diverse | poisson_calibrator.py:174-176; update_poisson_calibration.py; money_management.py:710-760 | confermato F/A; CERT_2 B5: PARZIALMENTE VERIFICATO - la doppia vita e' dichiarata nel codice (poisson_calibrator.py:1-25); le regole delle tre copie non sono state confrontate riga per riga [cert. fase 2] |
| P-R9 | BASSO | `markets_calibrated` scritto anche quando la calibrazione non e' caricata (source "none" = identita'); Mike e UI lo trattano come calibrato | poisson_calibrator.py:86-92 [C]; today:940-955 | latente (oggi source "db"), V2; CERT_4 1.33: CONFERMATO (latente), scrittura today_predictions_backfill.py:947-951 con calibration_source = cal.source [cert. fase 2] |
| P-R10 | BASSO | Lieve lookahead nelle medie di lega delle righe storiche rigenerate | Prediction/backfill_historical_analysis.py:117 | NON VERIFICATO quante righe; CERT_3 B29: NON VERIFICATO (controllata solo la riga del chiamante; il lookahead e' dentro compute_db_json_analisi, today_predictions_backfill.py:1640-1690, non riletto) [cert. fase 2] |
| P-R11 | BASSO | `lam_from_prematch(NaN)` restituisce 50,0; `devig_pair` con quota opposta <=1 restituisce la prob grezza | value_engine/poisson_total.py:51-61; devig.py:22-29 | sonda A; CERT_3 B27: CONFERMATO (lam_from_prematch('over',2,nan)=50.0; devig_pair(2.0,1.0)=0.5); che i chiamanti filtrino NaN/quote <=1 NON VERIFICATO (consumatori vivi: omega_model.py:740-751, live_engine_pro.py:293-301) [cert. fase 2] |
| P-R12 | BASSO | Due convenzioni sulla tau in-play (conditional_markets ovunque, live_engine_pro solo 0-0): scarto massimo 2,1 pp (1-1 al 60') | value_engine/bivariate.py; live_engine_pro.py | E2; CERT_3 B28: CONFERMATO lo scarto (2,12 pp, 1-1 al 60'); live_engine_pro.py:58-83 e' SCELTA DOCUMENTATA (:58-72); nessun bot usa la convenzione 'sempre'; la tau e' in almeno 5 copie, non 3 [cert. fase 2] |
| P-R13 | BASSO | Proxy P(O0.5 1T) = 1 - P(pareggio HT) sottostima (0,559 contro 0,667) | Betfair/betfair_report_manager.py:669-677 [C] | solo ripiego del foglio; CERT_3 B24: RIDIMENSIONATO, dormiente (il proxy scatta solo se manca target_ht_over_0_5, che esiste: predict_fixture.py:345); i numeri 0,559/0,667 NON VERIFICATI [cert. fase 2] |
| P-R14 | BASSO | Mercati AH / risultato esatto / O4.5 non persistiti benche' la matrice esista; `over_4_5` letto da uno strumento ma mai prodotto | A1.4; misura_punto8/estrai_db.py:274-276 | F-4; CERT_3 B25: over_4_5 / p_over45_cal sono campi morti (gravita' NESSUNA); AH/CS non persistiti NON VERIFICATO [cert. fase 2] |

## 6. Miglioramenti (dettaglio e priorita' in 06_PIANO_MIGLIORAMENTI.md)

M1 cruscotto settimanale RPS/log-loss/ECE contro le quote (prerequisito, sola lettura) - M2 prior dalle quote
(decisione utente) - M3 prior inter-stagionale / usare il DC-MLE per tutte le squadre - M4 rho stimato per tutte le
leghe (gerarchico) - M5 calibrazione liscia fuori campione e una sola tabella - M6 pesi di forma meno estremi
(decisione utente: cambia le P su cui sono tarate le soglie di Mike) - M7 taratura emivita/ridge del tattico ed
ensemble tattico+principale - M8 binomiale negativa/Weibull per le linee alte - M9 de-vig power/Shin - M10 guardie NaN
- M11 persistere AH/CS. Rimisurare dopo la notte del 10/10 la quota di previsioni generate dopo il calcio d'inizio (l'orologio del 09/10 dovrebbe eliminarla); poi eventuale marcatura/esclusione dalle statistiche. [cert. fase 2]

## 6-bis. Riferimenti ad ARCHITETTURA_2026-10 (mappa, riverificata dove indicato)
- Scheda G (`ARCHITETTURA_2026-10/03_SCHEDE_COMPONENTI/G_DATI_E_ALGORITMI_DEL_CLOUD.md`, riga della calibrazione):
  `weekly_poisson_calibration.yml` con cron `27 3 * * 1` e `poisson_calibration.generated_at` 05/10: coerente con il
  ricalcolo del lunedi'; oggi i workflow non hanno piu' `cron:` e la catena parte da pg_cron alle 00:12 UTC
  (E_inventario_completezza.md, CRONOSTORIA 09/10): la scheda e' superata su questo punto [cert. fase 2] (CONFERMATO: weekly_poisson_calibration.yml:4-8 'tolto il cron (27 3 * * 1)... gira SOLO il lunedi''; ordine definitivo della catena CRONOSTORIA.md:5598-5600).
- Scheda G riga 54: `statement_timeout=8s` sul ruolo `authenticator`: ogni cruscotto di qualita' (06 n.3) deve leggere
  per finestre di data strette come le sonde di questo audit (nessun 57014 in 20 SELECT).

## 7. Cio' che non ho potuto verificare
- `update` e' il timestamp di API-Football, non l'istante di quotazione del bookmaker (Q).
- Se emivita 420 gg, ridge 0,08, pesi 0,5/0,3/0,2 e k=8 siano mai stati tarati.
- Quante righe storiche provengano dal percorso con lookahead e quante leghe usino davvero il rho di riserva.
- Qualita' per singola lega (campione troppo piccolo per lega).
- Gli articoli citati come [ricerca] sono stati letti solo negli estratti; quelli FONTE NON APERTA sono citati da memoria (tutte le citazioni bibliografiche: NON VERIFICATO, CERT_4 1.36).
- [cert. fase 2] NON VERIFICATO: la tabella `poisson_calibration` sul DB (500 righe; sul file dynamic_cal.json le leghe sono 499); che pesi 5/10/15, k=8, emivita 420 e ridge 0,08 siano mai stati tarati; il numero '~475 leghe' senza rho stimato; chi ha lanciato il tattico alle 09:55 del 09/10.
