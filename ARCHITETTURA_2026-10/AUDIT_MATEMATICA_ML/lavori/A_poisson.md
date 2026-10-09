# A - CATENA POISSON: dai dati grezzi alla probabilita' (audit matematica, 09/10/2026)

Delegato A, sola lettura. Sonde in `lavori/sonde/` (output salvati accanto). Python di produzione importato in sola lettura.
Letture DB: 3 SELECT con LIMIT 800-1500 su finestra 21/09-08/10/2026 (nessuna scrittura, nessuna RPC).

## 0. Verdetti sintetici

| Domanda | Verdetto | Prova |
|---|---|---|
| (a) Miglior livello matematico possibile? | **NO** | Sul campione misurato (n=800, 21/09-08/10) le quote de-viggate battono il Poisson in modo netto: RPS 1X2 **0,1969 vs 0,2122** (grezzo) / 0,2122 (calibrato). Il blend quote/Poisson peggiora monotonicamente al crescere del peso Poisson (0,1969 -> 0,2011 -> 0,2122): il modello non aggiunge informazione alle quote. Il modello non usa MAI le quote. (sonda `a_poisson_vs_quote_db`) |
| (b) Omesso qualcosa? | **SI** | Vedi reperti 3-9: quote di mercato come prior/feature; aggiustamento per forza degli avversari nel modello principale; memoria cross-stagione (neopromosse); sovradispersione/bivariata; metriche proprie (log-loss/RPS) mai calcolate sul Poisson; confronto sistematico col mercato; mercati AH/CS non persistiti. |
| (c) Si puo' migliorare? | **SI**, con guadagno atteso misurabile soprattutto da (1) usare le quote come feature/prior, (2) strumentare RPS/log-loss + benchmark mercato, (3) rho globale stimato invece di -0,13 fisso, (4) calibrazione liscia (isotonica/beta) fuori campione. Vedi sez. 4. |
| (d) Migliori pratiche? | **IN PARTE** | Pratiche corrette: Dixon-Coles con tau esatta (verificata numericamente), decadimento esponenziale (xi) nel motore tattico, ridge/shrinkage empirical-Bayes, rho per lega con shrinkage, fit leakage-free per il tattico, tau clampata/spenta se negativa, matrice rinormalizzata, calibrazione con cap e monotonicita'. Scostamenti: il motore PRINCIPALE non e' un modello congiunto (medie mobili 5/10/15 della sola stagione corrente), nessuna metrica propria, fallback rho=-0,13 non dai dati, calibrazione con fattori per-bin (non liscia) e parzialmente in-sample. |

Matematica di base: **corretta** (tutte e tre le implementazioni indipendenti coincidono col riferimento numpy/scipy a 1e-7 o meglio; vedi sez. 2.1). I problemi non sono di formula ma di (i) informazione non usata, (ii) assenza di misura continua della qualita', (iii) pochi punti di fragilita' numerica nei casi limite (nessuno raggiungibile da dati realistici, tranne il NaN, reperto 10).

---

## 1. Inventario e diagramma della catena

```
DATI GREZZI (API-Football via raccoglitori)            ->  tabelle matches, match_team_stats(expected_goals), match_events,
                                                            fixture_predictions (partite del giorno), match_odds / raw_json_odds
   |
   +--[A1 MOTORE PRINCIPALE "poisson_xg_hybrid_dc"]  Prediction/today_predictions_backfill.py::compute_db_json_analisi (r.1418)
   |     per (lega, stagione CORRENTE): medie gol/xG casa e trasferta della stagione (r.1214-1301);
   |     per squadra: finestre 5/10/15 partite del contesto (casa-in-casa / trasferta-in-trasferta) pesi 0.5/0.3/0.2 (r.1500-1555);
   |     shrinkage verso media lega k=8 (r.1525); blend gol/xG eta=0.6 (r.1565-1590);
   |     lambda_h = max(0.05, Lh * att_h * dif_a) ; lambda_a = max(0.05, La * att_a * dif_h) (r.1593-1594)
   |     griglia Poisson 11x11 (max_goals=10) x tau DC (rho per lega o -0.13) -> rinormalizzata (r.1612-1620)
   |     mercati: 1X2, O1.5/2.5/3.5, BTTS (r.1621-1632); HT: lambda_HT = lambda * ratio_HT (shrink 0.45,k=12, cap [.25,.65]), griglia 5x5 (r.1640-1690);
   |     "first_half_over_0_5" = blend freq/Poisson con peso n/(n+10) (r.1725-1736)
   |     -> scrive db_json_analisi.{inputs, markets} su fixture_predictions
   |
   +--[A2 CALIBRAZIONE]  poisson_calibrator.py (applicato in _build_analysis_row r.934-962) -> db_json_analisi.markets_calibrated
   |     fattore per (cal_key, bin da 0.1 di prob grezza) = hit_rate/avg_prob, cap [0.2,3.0]; catena lega -> globale -> 1.0;
   |     poi RINORMALIZZAZIONE della distribuzione (poisson_calibrator.py r.174-176)
   |     fattori prodotti da generate_dynamic_cal.py (min_n=30, shrink per-lega K=75, monotonicita' APV leggera, upsert in poisson_calibration)
   |     e update_poisson_calibration.py --apply (riscrive CALIBRATION_TABLE statica in Betfair/money_management.py); rho: generate_dc_rho.py
   |     frequenza: Weekly Poisson Calibration, SOLO il lunedi' nella catena notturna (workflow weekly_poisson_calibration.yml r.1-50)
   |
   +--[A3 MOTORE TATTICO DC-MLE]  tactical_engine/serving.py::run_for_date -> model.py::DixonColesModel.fit (MLE congiunta) -> predict
   |     per lega, partite precedenti (cutoff 4 emivite=~2424 gg), HALF_LIFE_CLUB=420 gg, ridge 0.08, campo neutro per lega 1 (Mondiali);
   |     -> fixture_predictions.tactical_engine_json {lambda_*, markets, markets_ht, top_scores, strength_*}
   |
   +--[A4 STRATO LIVE / PREMATCH DELLE QUOTE]  value_engine/ (devig.py, poisson_total.py, bivariate.py, markets.py, goal_timing.py, pricing.py)
         quote -> de-vig proporzionale -> lambda totale (inversione Poisson per bisezione) -> (lambda,mu) da P(H) e P(O2.5) (bivariate.derive_lambdas)
         -> prob condizionate al minuto/punteggio con CDF empirica dei gol (goal_time_cdf.json, 120.542 gol); pricing (fair/min_back/max_lay)

CONSUMATORI (solo elenco, non analizzati):
  markets_calibrated.over_3_5  -> Mike (Betfair/mike/dossier.py:71-102, engine.py:3534 veto U3.5);
  db_json_analisi.inputs.lambda_* e tactical_engine_json.lambda_* -> Omega/stream (Betfair/stream/db.py:240-265, omega_model.py, omega/tools/m2_pesi.py);
  CALIBRATION_TABLE/dynamic_cal -> Betfair/money_management.py::_apply_calibration r.710 (edge/Kelly), master_backtest.py;
  value_engine.goal_timing/devig/poisson_total -> omega_model.py:261,720,893; safe_strategy/opportunity.py:484; stream/engine/live_engine(_pro).py:57,274;
  tactical_engine.dixon_coles.score_matrix + dc_rho_by_league.json -> live_engine_pro.py:26,37,512;
  UI: frontend/src/components/dashboard/PoissonPanel.tsx, TacticalEnginePanel.tsx, lib/tacticalEngine.ts, fixtureModels.ts;
  Telegram: Telegram bot/supabase/functions/telegram-bot/calc.ts (port TS di value_engine), index.ts:517;
  analytics: build_analytics_signals.py (motore 'poisson' = markets_calibrated), merge_engine_signals.py, market_intelligence/*.
```

### Tabella inventario

| id | file:riga | cosa calcola (formula) | input | output | consumatore |
|---|---|---|---|---|---|
| A1.1 | Prediction/today_predictions_backfill.py:1214-1301 | medie lega casa/trasferta = media gol FT della stagione (tutte le partite giocate della cache) | matches (lega, stagione) | league_home_avg, league_away_avg | A1.3 |
| A1.2 | :1359-1415 | finestra n=5/10/15 ultime partite; blend pesi 0.5/0.3/0.2 rinormalizzati | team_hist | gf/ga/xg/xga blend | A1.3 |
| A1.3 | :1500-1594 | `_shrink = (8*prior + base*n)/(8+n)`; coeff = 0.6*gol_ratio+0.4*xg_ratio; `lambda_h = Lh * att_h * dif_a`, floor 0.05; soglia minima 5 partite | A1.1, A1.2 | lambda_home/away | A1.4, A3 non dipende |
| A1.4 | :1131-1206, 1600-1632 | griglia Poisson indipendente (scipy) 11x11, tau DC su 4 celle, `grid/=sum`; 1X2, O/U 1.5/2.5/3.5, BTTS | lambda, rho_league | db_json_analisi.markets | A2, Mike, UI, analytics |
| A1.5 | :1640-1736 | HT: lambda*ratio_HT, griglia 5x5 (+tau, norm), 1X2 HT; O0.5 HT = w*freq + (1-w)*(1-P00_HT) | home_home/away_away | ht_1x2, first_half_over_0_5, ht_predictions | UI, analytics |
| A1.6 | :1162-1190 | `get_league_rho`: dc_rho_by_league.json (solo 24 leghe) altrimenti -0.13; banda [-0.25, 0.05] | json | rho | A1.4, live_engine_pro |
| A2.1 | poisson_calibrator.py:130-182 | `p_cal_i = p_i*cf(bin(p_i)) / sum_j(...)` | markets, poisson_calibration (DB) o dynamic_cal.json | markets_calibrated | Mike, analytics, UI, Telegram |
| A2.2 | generate_dynamic_cal.py:354-436 | cf = hit/avg_prob, cap [0.2,3], shrink verso globale con w=n/(n+75), monotonicita' | fixture_predictions FT con modello DC | poisson_calibration (lega 0 + per lega) | A2.1 |
| A2.3 | update_poisson_calibration.py:build_calibration_table | stessa formula (min_n 30, cap), `--apply` riscrive CALIBRATION_TABLE in money_management.py | idem | tabella statica | money_management |
| A2.4 | generate_dc_rho.py:140-205 | profile-MLE di rho con lambda memorizzati; `rho = (n*mle + 300*(-0.13))/(n+300)`; min 300 partite/lega | inputs.lambda_*, risultati | dc_rho_by_league.json | A1.6 |
| A3.1 | tactical_engine/model.py:103-223 | `log lh = c + a_i - d_j + g`, `log la = c + a_j - d_i`; loglik = sum w[ log Pois + log Pois + log tau ] - ridge*(sum a^2 + sum d^2); w = exp(-ln2/420 * giorni); L-BFGS-B; 2o stadio con rho vincolato su tutte le coppie | matches lega (FT/AET/PEN) a 90' | FitResult | A3.2 |
| A3.2 | dixon_coles.py:61-118; model.py:239-257 | griglia 11x11 + tau + norm; 1X2, DC, O0.5-3.5, BTTS, CS top5, xG | FitResult | tactical_engine_json | UI, Omega, live_engine_pro |
| A4.1 | value_engine/devig.py | de-vig proporzionale; coppia: `imp/(imp+imp_opp)` | quote | prob | omega, live_pro, safe |
| A4.2 | poisson_total.py:46-81 | inversione bisezione di `P(<=k;L)=p` in [1e-4,50]; `cond_prob_total`: Poisson(L*frac_rimasta) | prob prematch, minuto, gol | prob O/U live | omega, safe, live |
| A4.3 | bivariate.py:52-210 | griglia DC (MAX 15) + `derive_lambdas` (12 iterazioni di bisezione su totale/supremazia) + conditional_markets | p_home, p_over25 | prob mercati a punteggio | Telegram calc.ts (port), omega |
| A4.4 | goal_timing.py + calibrate.py | CDF empirica minuto-gol (120.542 gol), 1o tempo = 43,48% | match_events | frac. gol rimasta | tutti i live |
| A4.5 | pricing.py | fair=1/p; min_back=1+(1-p)/(p(1-c)); max_lay=1+(1-p)(1-c)/p | prob | soglie | calcolatore |

(`value_engine/bivariate.py` NON e' la Poisson bivariata di Karlis-Ntzoufras: e' Dixon-Coles. Il nome e' fuorviante; reperto 14.)

---

## 2. Analisi per componente

### 2.1 Cuore matematico (matrice dei punteggi, tau, troncamento, mercati) - VERIFICATO NUMERICAMENTE
Sonda `a_poisson_sonda.py` (output `a_poisson_sonda_output.txt`).
- tau DC: le tre implementazioni (`bivariate.dc_tau`, `dixon_coles.dc_tau`, `today._dc_tau`) coincidono con la formula di Dixon-Coles 1997: tau(0,0)=1-lambda*mu*rho, tau(0,1)=1+lambda*rho, tau(1,0)=1+mu*rho, tau(1,1)=1-rho. La correzione e' a somma zero sulla massa (verificato: massa totale del riferimento a griglia 200x200 = 1,000000000000), quindi la rinormalizzazione recupera solo la coda troncata.
- Esempi (lambda=1,4, mu=1,1):
  - rho=-0,10: H=0,425402 D=0,291627 A=0,282971 O2,5=0,456187 BTTS=0,515258 (riferimento indipendente); value_engine scarto massimo 1,6e-12; tactical e today 1,7e-7.
  - rho=-0,13: H=0,421609 D=0,299212 A=0,279179 O2,5=0,456187 BTTS=0,519050; stessi scarti.
  - lambda=2,2 mu=0,8 rho=-0,13: scarto max 7,7e-10 (value_engine, MAX 15), 8,4e-6 (griglia 10). Trascurabile.
  - rho=-0,13 sposta H di -0,0038, D di +0,0076 e BTTS di +0,0038 rispetto a rho=-0,10: l'effetto di rho e' di 2o ordine ma non nullo sui mercati del pareggio.
- Massa persa dal troncamento prima della rinormalizzazione: lambda 1,4/1,1: 3,1e-7 (max_goals 10), 1,9e-5 (8), **2,0e-2 (4)**; lambda 2,5/2,0: 7e-5 (10); 3,5/3,0: 1,3e-3 (10); 5/4: 1,65e-2 (10), 7,4e-5 (15). La griglia FT a 10 va bene per ogni lambda calcistico reale (<4 per squadra). La griglia HT a 4 gol (today r.1673) perde ~0,4 % di massa su una squadra con lambda_HT=1,0 (P(Pois(1)>4)=0,0037), rinormalizzata: errore residuo trascurabile, ma e' un limite fisso.
- Non negativita': con rho nella banda produzione [-0,25, 0,05] e lambda realistici tau>0 ovunque. tau negativa solo fuori dominio: (3,3,rho=+0,15) -> P(0,0)=-8,7e-4 in `dixon_coles.score_matrix` (non clampa); `bivariate.score_matrix` clampa tau>=0; `today._dc_tau` clampa solo (1,0),(0,1) (non (0,0),(1,1): con rho<=0,05 e lambda*mu>20 negativa, non raggiungibile). Nel motore tattico il dominio e' garantito da `rho_bounds`/`_rho_limits_all_pairs` (TAU_MIN 1e-3) -> OK. In live_engine_pro `effective_rho` spegne la DC se tau<=0 -> OK.
- Mercati: somme di celle della stessa matrice (coerenza per costruzione), 1X2 rinormalizzato dopo il troncamento. OK.

### 2.2 Motore principale (A1) - correttezza e limiti
Formula effettiva: `lambda_casa = Lh * ( 0.6*gf_h/Lh + 0.4*xg_h/Lxh ) * ( 0.6*ga_a/Lh + 0.4*xga_a/Lxh )` (r.1586-1594) con ogni gf/ga/xg gia' shrinkato verso la media di lega con peso 8/(8+n) e n<=15. E' l'impianto "attacco x difesa x media lega" di Maher (1982) con shrinkage, ma stimato **marginalmente per squadra** e non congiuntamente: l'attacco della squadra A e' la media dei gol segnati contro avversari NON corretta per la loro forza (la difesa della B e' media dei gol subiti contro avversari non corretti). Nessun aggiustamento strength-of-schedule, nessun fattore campo stimato (il campo entra implicitamente dalla separazione casa/trasferta con campioni piccoli e dal rapporto Lh/La).
- Punti positivi: separazione casa/trasferta con coerenza di normalizzatori (r.1558-1575 commento), xG usato solo dove c'e' copertura (r.1565-1590), soglia minima 5 partite, rho per lega, griglia ampia, 1X2 rinormalizzato, nessuna divisione per zero (floor 0,05 e controllo xG baseline r.1473).
- Limiti (matematici):
  1. **Solo la stagione corrente** (`_build_match_cache(league, season_year)` r.1210-1230): a inizio stagione nessuna previsione finche' una squadra non ha 5 partite (ritorna None, r.1534-1540) e con 5-8 partite il prior e' la media lega, non la forza dell'anno prima. Le neopromosse non hanno prior piu' basso della media. Il tattico, invece, usa fino a ~6,6 anni di storico per lega.
  2. Pesi 0,5/0,3/0,2 su finestre annidate 5/10/15: la quota effettiva delle ultime 5 partite e' 0,5+0,3*0,5+0,2*(1/3)=0,72: forte enfasi sulla forma recente su un campione piccolo, partendo da una stima gia' rumorosa. Il reperto empirico e' compatibile con questo (reperto 3): le probabilita' grezze sono **troppo estreme** (reliability O2,5 sotto la diagonale: p=0,17 -> freq 0,33; p=0,26 -> 0,42; p=0,84 -> 0,75).
  3. `n_used` dello shrinkage conta le partite della finestra 15, non le partite effettive pesate, e viene usato anche per i termini xG (che possono avere copertura minore): shrinkage xG sottostimato dove la copertura xG e' parziale.
  4. Lega media calcolata su TUTTE le partite giocate in cache, non solo quelle precedenti alla partita: in live e' corretto, ma `Prediction/backfill_historical_analysis.py:117` richiama la stessa funzione con la cache dell'intera stagione -> **lieve lookahead** nelle medie lega delle righe storiche (la forma della squadra usa `_before_date`, la media lega no). Effetto atteso piccolo (media lega stabile), NON VERIFICATO quante righe in `fixture_predictions` vengano da quel percorso.
  5. Un solo rho per lega; 24 leghe su ~500 hanno rho specifico (reperto 6).
- Misura (sonda `a_poisson_misura_db`, 1.500 FT del 21/09-08/10, modello `poisson_xg_hybrid_dc`): 1X2 grezzo Brier 0,6063, log-loss 1,0142, RPS 0,2197 contro baseline climatologica del campione (0,6378 / 1,0540 / 0,2358): il modello ha skill reale sulla climatologia. Gol attesi totali 3,091 vs reali 3,159 (bias -0,07); dispersione di Pearson condizionata E[(g-lambda)^2/lambda]=1,142 (Poisson perfetto=1,00): **sovradispersione del 14 %** rispetto al Poisson, che mediamente fa sottostimare code e over alti (ma include l'errore di stima di lambda; non separabile senza un modello a effetto casuale).

### 2.3 Calibrazione (A2)
- Meccanica: fattore moltiplicativo per bin da 0,1 = tasso reale / prob media nel bin, poi rinormalizzazione sulle classi. Per i mercati binari equivale a `p*cf_T / (p*cf_T + (1-p)*cf_F)` dove cf_F e' preso dal bin di (1-p): i due fattori sono stimati separatamente e combinati, quindi l'output NON e' il tasso osservato del bin (mismatch fra cio' che e' stimato e cio' che e' applicato). Nei mercati 1X2 stesso discorso a 3 classi.
- Il risultato misurato e' comunque positivo ma modesto (sonda): O2,5 Brier 0,2393 -> **0,2349**, log-loss 0,6728 -> 0,6621; O3,5 0,2305 -> 0,2271; BTTS 0,2485 -> 0,2435 (BTTS grezzo quasi al livello di una moneta: log-loss 0,6915 vs 0,6931 del 50/50); 1X2 RPS 0,2197 -> 0,2192 (differenza ~0,0005, minima). Reliability O2,5 calibrata molto piu' vicina alla diagonale (p 0,645 -> 0,647; 0,739 -> 0,743).
- ATTENZIONE metodologica: la tabella e' ricalcolata ogni lunedi' su TUTTE le fixture FT con modello DC (80.876 al 05/10, 499 leghe, min_n 30), quindi la finestra misurata e' per ~2 % (globale) in-sample; per-lega con n piccolo l'in-sample pesa di piu'. La misura non e' un test fuori campione pulito. La nota di Mike (engine.py:3534: Brier -0,0093 [-0,0155;-0,0034] su 243 partite dal 21/09) e' piu' pulita ma su un mercato solo.
- Debolezze: bin discreti con salti ai bordi (non liscia), cap [0.2,3.0] arbitrario, monotonicita' applicata nei fattori dinamici (generate_dynamic_cal) ma NON in `update_poisson_calibration.py` (tabella statica), nessun intervallo di confidenza, nessun controllo di drift (ECE per settimana), ricalcolo settimanale (frequenza adeguata, il modello cambia lentamente).
- Stato dell'arte: la calibrazione a posteriori con isotonica/Platt/beta e' standard (Niculescu-Mizil & Caruana 2005; Kull et al. 2017 beta calibration - citazioni da memoria, NON riverificate online); qui e' una variante piu' grezza ma funzionale.

### 2.4 Motore tattico DC-MLE (A3)
- Formula: tutte e tre le classi di parametri (attacco, difesa per squadra, costante, campo, rho) stimate congiuntamente per massima verosimiglianza pesata (pesi esponenziali nel tempo, emivita 420 gg ~ xi=0,00165/giorno), ridge 0,08 (= prior gaussiano centrato in 0). E' esattamente il modello Dixon-Coles 1997 con decadimento temporale (xi) + simmetria casa/trasferta (una coppia att/dif per squadra) + campo unico per lega. Test di recupero parametri (sonda, 12 squadre, 700 partite sintetiche con rho vero -0,08, campo 0,25): campo stimato 0,233, rho -0,104, correlazione attacco 0,925, restringimento 0,88 (ridge + decadimento): **il fit e' corretto e converge**.
- Punti forti: vincolo di tau su TUTTE le coppie (2 stadi), leakage-free (`ref_date=start`), pesi su fixture_date ordinati deterministicamente, centratura per identificabilita'.
- Limiti: (i) nessuna fonte di informazione esterna (quote); (ii) forza squadra costante nel tempo salvo il decadimento (no modello di stato Koopman-Lit); (iii) una squadra non vista nel storico della lega viene **saltata** (serving.py:244, `skipped_fixtures`), quindi le neopromosse da una lega inferiore senza storico nel campione non ricevono previsione; se hanno poche partite hanno forza ~0 (media), senza prior "neopromossa"; (iv) emivita 420 gg e ridge 0,08 sono costanti: NON VERIFICATO se tarate (cercate in `tactical_engine/generate_predictions.py`, non trovata una procedura di tuning); (v) ottimizzatore L-BFGS-B con gradiente numerico (costo O(n_param) valutazioni; ok per leghe da 20 squadre).
- Misura (sonda `a_tactical_vs_poisson_db`, n=528 partite con tutti e tre i motori e le quote): RPS tattico **0,2166**, Poisson calibrato 0,2135, Poisson grezzo 0,2142, quote **0,2032**, media(tattico, Poisson cal) 0,2111. Differenza tattico-Poisson ~0,003: dentro il rumore di n=528 (NON c'e' prova che il modello con aggiustamento avversari sia migliore del semplice sulle partite recenti); la media dei due migliora (ensemble), le quote restano nettamente avanti (0,2032).

### 2.5 Strato quote e live (A4)
- `devig_multiplicative`: proporzionale. Sul 1X2 tipico (2,10/3,40/3,60, overround 1,0481): proporzionale 0,4543/0,2806/0,2650; potenza 0,4602/0,2780/0,2618; Shin 0,4587/0,2787/0,2626. Il proporzionale sposta ~0,4-0,6 pp di probabilita' dal favorito all'outsider rispetto a Shin/potenza (favourite-longshot bias, noto: Shin 1993; Strumbelj 2014 - citazioni da memoria). Impatto su lambda derivati: piccolo ma sistematico (sulle sole quote 1X2 e O/U a due esiti).
- `poisson_total.lam_from_prematch`: inversione bisezione robusta nel bracket [1e-4, 50]; prob tagliata a [1e-6, 1-1e-6]. Fragilita': `prob=NaN` -> il bracket non ha controllo di segno valido e **la funzione restituisce 50,0 senza errore** (sonda). `devig_pair(nan,2.0)` restituisce nan. In `live_engine_pro.total_goals_from_ou` le quote vengono filtrate con `over_back and ... > 1` (NaN passa il filtro perche' `nan > 1` e' False? In realta' `nan > 1` e' False quindi viene scartato: verificato per via logica, NON eseguito); in omega_model.py:720-893 il filtro non e' stato letto (NON VERIFICATO).
- `p_le`/`pois` usano `lam**k/factorial(k)` in float: OverflowError per k>=171 (`p_le(180,100)`) o lambda>~700: non raggiungibile (k<=5, lambda<=50); fallisce rumorosamente, non in silenzio. `score_matrix(900,900)` -> ZeroDivisionError (rumoroso).
- `bivariate.derive_lambdas`: round-trip verificato (p_home 0,45 / p_over25 0,55 -> lambda 1,6358, mu 1,2468 -> H 0,4500, O2,5 0,5500 col riferimento a griglia 200); tolleranza 0,02 sul round-trip (alta: 2 pp di errore accettati); quote estreme (0,9/0,95) -> lambda 4,96/1,34 (convergono, senso discutibile). Interazione con rho: lambda derivati dipendono da rho (con rho=-0,5: 1,725/0,949 vs 1,640/1,034 a -0,13).
- CDF dei gol (`calibrate.py`): 120.542 gol, 1o tempo 43,48 %, 2o 56,52 % (coerente con la regolarita' nota ~45/55 e late-surge). Rispetto al lineare, al minuto 60 resta il 40,6 % dei gol contro il 33,3 % lineare; all'89' l'8,3 % vs 1,1 %. **Limite**: la CDF e' marginale su tutte le leghe e non condiziona su punteggio, cartellini, quota; e il fetch usa `.range()` senza ORDER BY su tabella >1M righe (calibrate.py:34-41): la paginazione senza ordine totale puo' duplicare/saltare righe (il docstring lo ammette: "la FORMA della curva e' la garanzia"). Impatto minimo sulla forma, nessuno in produzione (file statico).
- `pricing.py`: formule back/lay con commissione corrette (verificate algebricamente: EV back = p(q-1)(1-c)-(1-p)=0 -> q=1+(1-p)/(p(1-c)); lay: q=1+(1-p)(1-c)/p).
- In-play: `bivariate.conditional_markets` applica la tau DC alla griglia dei gol RIMANENTI per qualsiasi punteggio (commento: "approssimazione in-play"), mentre `live_engine_pro.effective_rho` la applica solo a 0-0. Due convenzioni diverse sullo stesso oggetto (divergenza da portare all'utente, non e' un bug dimostrato).

### 2.6 Confronto con lo stato dell'arte
| Tema | Stato dell'arte (fonte) | Noi |
|---|---|---|
| Dixon-Coles con decadimento xi | Dixon & Coles (1997), Applied Statistics 46(2):265-280 (xi ottimizzato per massimizzare la verosimiglianza predittiva; nel paper emivita ~1 anno) | Tattico: si', emivita 420 gg, non tarata (NON VERIFICATO). Principale: no (medie mobili). |
| Poisson bivariata | Karlis & Ntzoufras (2003), JRSS-D 52(3):381-393: X=X1+X3, Y=X2+X3 (correlazione positiva, nessun parametro di inflazione sui pareggi se non per un modello a mistura) | No (solo DC, correlazione negativa solo sulle 4 celle basse) |
| Sovradispersione / binomiale negativa / zero-inflation | Si usano per goal con eterogeneita' non osservata; in letteratura sul calcio il guadagno predittivo e' modesto rispetto a DC+decadimento (NON VERIFICATO, da memoria) | No. Dispersione misurata 1,14. |
| Bayesiani gerarchici | Baio & Blangiardo (2010), J. Appl. Stat. 37(2):253-264 (attacco/difesa con iperprior, shrinkage verso la media di lega) | Equivalente informale: shrinkage k=8 (principale) e ridge 0,08 (tattico), non stimati con iperparametri |
| Rating dinamici / state-space | Koopman & Lit (2015), JRSS-A 178(1):167-186 (bivariata dinamica con state-space, valutata con strategia di scommessa; vedi https://ideas.repec.org/p/tin/wpaper/20120099.html) | No (decadimento esponenziale, non stocastico) |
| Vantaggio campo per lega | Standard nei modelli recenti | Principale: implicito; tattico: unico per lega (bounds [-1,1]); Mondiali neutro |
| Quote di mercato come prior/feature | Si possono combinare dati storici e quote (letteratura "Combining historical data and bookmakers' odds", arXiv 1705.04356 e lavori successivi di Egidi/Pauli/Torelli - titolo verificato dalla ricerca, contenuto NON letto); le quote de-viggate sono il benchmark piu' forte in qualita' predittiva | **Assente**. Misurato: quote RPS 0,197-0,203 vs modello 0,212-0,217 |
| Metriche | RPS per esiti ordinati (Constantinou & Fenton 2012, J. Quant. Anal. Sports 8(1); https://ideas.repec.org/a/bpj/jqsprt/v8y2012i1n12.html); critica: Wheatcroft (2021) "Evaluating probabilistic forecasts of football matches: the case against the RPS", J. Quant. Anal. Sports 17(4):273-287 (https://arxiv.org/pdf/1908.08980) che preferisce la log-loss (proper e locale) | master_backtest calcola Brier/log-loss/BSS solo per la track ML (r.1056-1160); per il Poisson solo ROI su scommesse. Nessun RPS nel repo (grep). |
| Reliability/calibrazione | Diagrammi di affidabilita', ECE; isotonica/beta | Reliability stampata per le sole ML; `valida_motore_poisson.py` fa bucket di convinzione su 18 partite fisse (DEFAULT_FIDS) |

---

## 3. REPERTI

1. **MEDIO-ALTO** - Il Poisson non usa le quote e perde nettamente contro di esse. `Prediction/today_predictions_backfill.py:1593-1594` (lambda solo da storico). Prova: sonda `a_poisson_vs_quote_db_output.txt`: RPS 1X2 quote 0,1969 vs Poisson grezzo 0,2125 / calibrato 0,2122 (n=800); `a_tactical_vs_poisson_db_output.txt`: quote 0,2032, Poisson cal 0,2135, tattico 0,2166 (n=528); blend 50/50 quote+Poisson 0,2011, mai meglio delle sole quote. Impatto soldi: un "edge" del Poisson contro le quote Betfair/API-football e' in media errore del modello, non valore (la differenza RPS 0,015 e' ampia). Limiti: finestra 17 gg, snapshot orario delle quote NON verificato (se e' vicino al fischio e' una quasi-chiusura, benchmark piu' duro); bookmaker scelto = Betfair sportsbook o primo; solo 1X2.
2. **MEDIO** - Nessuna misura continua della qualita' del Poisson (RPS/log-loss/Brier su `markets` e `markets_calibrated`): `master_backtest.py:1056-1160` lo fa solo per la ML; `valida_motore_poisson.py` su 18 fixture fisse (r.20-24). Senza metrica non si accorge un drift (es. se il modello peggiorasse dopo una modifica dei pesi). Proposta in sez. 4.
3. **MEDIO** - Probabilita' grezze troppo estreme (lambda troppo dispersi): reliability O2,5 grezza (sonda `a_poisson_misura_db_output.txt`): bin 0,1-0,2 p=0,166 freq=0,333; 0,2-0,3 p=0,261 freq=0,420; 0,8-0,9 p=0,835 freq=0,747. Causa plausibile (NON provata): peso 0,5 sulla finestra di 5 partite + shrinkage solo 8/(8+n). La calibrazione a bin corregge parte del difetto (stesso test: 0,645->0,647 ecc.) ma e' un cerotto: la correzione dovrebbe stare nella stima di lambda.
4. **MEDIO** - Memoria cross-stagione assente nel motore principale: `_build_match_cache(league, season_year)` (r.1210-1230): niente previsione prima di 5 partite/squadra (r.1534-1540), prior = media lega corrente (anch'essa su pochi match a inizio stagione), neopromosse senza prior ridotto. Impatto: ~prime 5-6 giornate di ogni stagione senza Poisson (o stimato su campioni minimi). Il tattico e' coperto dal lungo storico ma salta le squadre mai viste (serving.py:244).
5. **MEDIO** - Nessun aggiustamento per forza degli avversari nel motore principale (medie marginali). Il tattico lo fa, ma sul campione n=528 non e' risultato migliore (RPS 0,2166 vs 0,2135-0,2142): non conclusivo.
6. **BASSO-MEDIO** - rho di fallback -0,13 e' la stima 1997 su calcio inglese: `dc_rho_by_league.json` contiene solo 24 leghe, media -0,081 (min -0,1997, max -0,0229; generato 05/10/2026), pur con shrinkage verso -0,13 (K=300) che gonfia in modulo; le ~475 leghe restanti usano -0,13. Probabile sovrastima della correlazione per la maggior parte delle leghe (effetto su D/BTTS dell'ordine di 0,3-0,8 pp per lambda 1,4/1,1: sonda sez.1 rho -0,10 vs -0,13: D +0,76 pp, BTTS +0,38 pp). Fonte: generate_dc_rho.py:75 (MIN_MATCHES_RHO=300) e 149-163.
7. **BASSO-MEDIO** - La calibrazione e' parzialmente in-sample e a bin discreti; fattori stimati per classe e applicati dopo rinormalizzazione (poisson_calibrator.py:174-176): output non coincide col tasso del bin; `update_poisson_calibration.py` non impone la monotonicita' (la impone `generate_dynamic_cal.py:354-377`): due tabelle (CALIBRATION_TABLE statica in money_management.py e poisson_calibration/dynamic_cal) con regole diverse. Il guadagno misurato e' reale ma piccolo (RPS 1X2 -0,0005; Brier O2,5 -0,0044).
8. **BASSO** - Lieve lookahead nelle medie lega delle righe storiche rigenerate da `Prediction/backfill_historical_analysis.py:117` (cache dell'intera stagione); queste righe entrano nelle tabelle di calibrazione (`model == poisson_xg_hybrid_dc`, update_poisson_calibration.py:compute_calibration). NON VERIFICATO quante righe.
9. **BASSO** - Mercati non persistiti: Asian Handicap, risultato esatto (solo nel tattico, top 5), O0.5/O4.5 FT, linee HT oltre 0,5. La matrice c'e' (A1.4/A3.2); derivarli e' a costo zero. Nessun consumatore li chiede oggi oltre ai live (che calcolano linee arbitrarie, live_engine_pro.py:520-530).
10. **BASSO (fragilita' numerica)** - `value_engine/poisson_total.py:51-61`: con `prob=NaN` `lam_from_prematch` restituisce **50,0** senza errore (verificato in sonda). I chiamanti filtrano le quote prima (live_engine_pro.py:290 richiede `over_back and ... > 1`), quindi non e' raggiungibile dai dati verificati; la regola "FALLISCI RUMOROSAMENTE" di bivariate.py non e' applicata qui. Un NaN da quote sospese/corrotte produrrebbe over ~100 %. Stessa famiglia: `devig_pair(nan,.)` -> nan.
11. **BASSO** - `devig_pair(1.9, 1.0)` restituisce 0,526 (=1/1,9): quota opposta <=1 (mercato sospeso) tratta come "non c'e'" e restituisce la prob implicita grezza (con margine), non una prob de-viggata. Rischio: usata come se fosse de-viggata (impatto tipico +2-5 pp sul favorito). `value_engine/devig.py:103-110`.
12. **BASSO** - De-vig solo proporzionale (devig.py:93-100): favourite-longshot bias non corretto (differenza ~0,4-0,6 pp sul favorito rispetto a Shin/potenza, sonda sez. 6). Rilevante solo dove i lambda sono derivati dalle quote (omega/live).
13. **BASSO** - `bivariate.derive_lambdas`: tolleranza round-trip 0,02 (r.27) = 2 pp di errore accettato; `_bisect` a 64 iterazioni su [-12,12] e' piu' che sufficiente: la tolleranza e' generosa rispetto alla precisione reale (1e-10). Rischio: accettare quote incoerenti con errore fino a 2 pp. Nessun caso reale misurato.
14. **BASSO (documentazione)** - Il nome `value_engine/bivariate.py` suggerisce Poisson bivariata (Karlis-Ntzoufras) ma implementa Dixon-Coles; e' anche duplicata la matematica DC in 3 posti (bivariate.py, tactical_engine/dixon_coles.py, today_predictions_backfill.py) con regole di clamp diverse (reperto sez. 2.1). Le tre danno lo stesso risultato per input validi (scarti <=1,7e-7 a lambda 1,4/1,1).
15. **BASSO** - HT: griglia a 4 gol e ratio HT con tetto [0,25, 0,65] e prior 0,45 (empirico: 43,48 % dalla CDF globale): prior non allineato (0,45 vs 0,4348), differenza -> lambda_HT sovrastimato del 3,5 % nel prior; impatto su HT 1X2 e O0,5 HT minimo (r.1640-1690, goal_time_cdf.json first_half_share 0,4348).
16. **INFO (non e' un difetto)** - Dispersione di Pearson 1,14 sul campione di 1.500 partite: il Poisson e' lievemente sovradisperso nei dati. Un modello binomiale negativo o un effetto casuale per partita sono candidati per i mercati d'alta linea (O3,5+).

NON VERIFICATO (riepilogo): emivita 420 gg e ridge 0,08 tarati o no; quante righe storiche provengono dal percorso backfill con lookahead; istante di acquisizione di raw_json_odds; filtro NaN in omega_model.py; efficienza delle 8-9 leghe principali separatamente (campione troppo piccolo, non misurato); contenuto degli articoli citati oltre ai titoli verificati (tutte le citazioni di sez. 2.6 non marcate da URL sono da memoria).

---

## 4. Miglioramenti proposti

| # | Proposta | Guadagno atteso | Costo | Metrica | Rischio | Cosa tocca |
|---|---|---|---|---|---|---|
| M1 | **Cruscotto di qualita'**: job settimanale che calcola RPS, log-loss, Brier, ECE, reliability per `markets` e `markets_calibrated`, per lega e globale, + benchmark quote de-viggate (stessa partita) e storico per drift | Rende visibile reperto 1-3; basso rischio; prerequisito per ogni altro cambio | Basso (sonde gia' pronte in `lavori/sonde/`) | RPS/log-loss walk-forward 4 settimane | Nullo (sola lettura) | Nuovo script e tabella di misura (con permesso) |
| M2 | **Quote come feature/prior**: shrinkare i lambda del Poisson verso i lambda impliciti nelle quote (via `derive_lambdas` su quote pre-match de-viggate, Shin), con peso scelto per walk-forward | Atteso: avvicinare RPS a ~0,197-0,200 (blend monotono nel test: w=0,75 -> 0,1981); piu' valore informativo se l'uso e' "modello vs mercato" a scopo diverso dall'edge | Medio | RPS e CLV su 1 mese | **Cambia il significato dell'edge: Poisson non sarebbe piu' indipendente dalle quote** | Tocca consumatori che calcolano edge (Mike veto U3.5, money_management): DECISIONE UTENTE |
| M3 | Prior inter-stagionale: partire dai valori finali della stagione precedente (decaduti) + prior neopromossa (media dei neopromossi storici) nel motore principale; oppure usare il DC-MLE come stimatore di lambda anche per il principale | Copre le prime giornate; riduce varianza | Medio | RPS giornate 1-8 vs oggi | Medio (cambia il modello su cui la calibrazione e' stata fatta -> ricalibrare) | today_predictions_backfill.py, calibrazione |
| M4 | rho globale stimato (profile-MLE su tutte le leghe, o gerarchico) al posto del -0,13 fisso | D e BTTS piu' calibrati per ~475 leghe; 0,3-0,8 pp | Basso | log-loss 1X2/BTTS | Basso | generate_dc_rho.py, DC_RHO |
| M5 | Calibrazione liscia (isotonica o beta) con validazione walk-forward e IC; applicare a ogni classe binaria senza rinormalizzare ad hoc | Meno salti ai bordi dei bin; effetto in-sample misurato | Medio | Brier/ECE fuori campione | Basso | poisson_calibrator.py, generate_dynamic_cal.py, update_poisson_calibration.py |
| M6 | Ridurre la sovrastima della forma: pesi finestre meno concentrati (p.es. 0,34/0,33/0,33 o decadimento esponenziale), k_shrink piu' alto; scegliere per walk-forward | Reliability piu' vicina alla diagonale PRIMA della calibrazione (reperto 3) | Basso | RPS/Brier walk-forward | Medio: tocca la "strategia" del modello; ricalibrare | today_predictions_backfill.py |
| M7 | Tarare emivita e ridge del tattico (griglia + walk-forward), ensemble con il principale (media misurata: 0,2111 vs 0,2135 sul n=528) | ~0,002-0,004 RPS | Medio | RPS | Basso | tactical_engine/serving.py |
| M8 | Binomiale negativa o bivariata (copula/fattore comune) solo sulle linee alte; Poisson bivariata per correlazione positiva (vedi Karlis-Ntzoufras 2003) | Incerto, modesto (dispersione 1,14) | Alto | log-loss O3,5/O4,5 | Medio | Da valutare dopo M1 |
| M9 | De-vig Shin o potenza al posto del proporzionale per i lambda derivati dalle quote | ~0,4-0,6 pp sul favorito | Basso | log-loss | Basso | value_engine/devig.py (parita' con il port TS calc.ts da mantenere) |
| M10 | Robustezza: controllo `isnan`/`isfinite` in `lam_from_prematch`, `devig_pair`; `devig_pair` con quota opposta <=1 deve rifiutare invece di restituire 1/o | Elimina reperti 10-11 | Minimo | Test rossi su NaN/1.0 | Nullo | value_engine/poisson_total.py, devig.py + port TS |
| M11 | Persistere AH e CS dalla matrice esistente | Nessun costo di stima | Basso | - | Basso | A1.4 |

## 5. Decisioni che spettano all'utente

- **M2** (quote come prior) e **M6/M3** cambiano la distribuzione su cui si basano il veto U3.5 di Mike (engine.py:3534 e soglie VETO_U35_NODI) e l'edge in money_management: toccano strategie dei bot, quindi vanno portate all'utente; ogni cambio richiede ricalibrazione e riconferma sul replay prima del paper (standard `PROCESSO_STANDARD_BOT.md`).
- Divergenza da scrivere: due convenzioni diverse sulla tau DC in-play (`value_engine.bivariate.conditional_markets` ovunque vs `live_engine_pro.effective_rho` solo a 0-0). Non si altera.
- Il fatto misurato "le quote battono il Poisson di ~0,015 RPS" va letto dall'utente: se una strategia e' "Poisson > quote = valore", il segnale medio e' dominato dall'errore del modello. Non e' un giudizio sulle strategie, e' un limite di informazione del modello.

## 6. Metodo di ricerca

- Lettura integrale (grep + Read): value_engine/{poisson_total,devig,markets,pricing,goal_timing,calibrate,bivariate}.py; tactical_engine/{dixon_coles,model,serving}.py; poisson_calibrator.py; update_poisson_calibration.py (r.1-330); generate_dynamic_cal.py (r.1-60, 338-436); generate_dc_rho.py (intero); valida_motore_poisson.py (r.1-80); weekly_poisson_calibration.yml (r.1-120); Prediction/today_predictions_backfill.py (r.917-964, 1103-1820); Betfair/money_management.py `_apply_calibration`; Betfair/stream/engine/live_engine_pro.py (r.26-100, 262-330, 500-540); master_backtest.py (indice sezioni; grep "brier|rps").
- Consumatori: `git grep -lE "poisson_xg_hybrid_dc|markets_calibrated|db_json_analisi|tactical_engine_json|value_engine|poisson_calibration|dynamic_cal|CALIBRATION_TABLE|dc_rho_by_league|tactical_engine"` (circa 110 file, esclusi AUDIT_*, _checkpoint*, ARCHITETTURA, .claude); `git grep value_engine` (consumatori diretti: omega_model.py:261,720,893; safe_strategy/opportunity.py:484; stream/engine/live_engine.py:57, live_engine_pro.py:274-275; build_inplay_intensity.py:31; Telegram calc.ts:1,10).
- Scheda G consultata (`ARCHITETTURA_2026-10/03_SCHEDE_COMPONENTI/G_DATI_E_ALGORITMI_DEL_CLOUD.md`) solo come mappa: conferma che la calibrazione gira su `weekly_poisson_calibration.yml` e tabelle `poisson_calibration`/`fixture_predictions`.
- `grep -n "rps|ranked"` su master_backtest/calibration_analysis/tactical_engine: 0 occorrenze di RPS nel repo (campione dei file indicati).
- Sonde: `lavori/sonde/a_poisson_sonda.py` (+ output), `a_poisson_misura_db.py` (1.500 righe), `a_poisson_vs_quote_db.py` (800 righe), `a_tactical_vs_poisson_db.py` (1.200 righe lette, 528 utili). Eseguite col `.venv`, sola lettura. Ricerche web: 2 (RPS di Constantinou-Fenton; Koopman-Lit e Karlis-Ntzoufras).
- Non letti (per budget): migrazioni SQL che ricalcolano probabilita' (nessuna funzione SQL Poisson individuata nei file trovati dal grep; elenco `migrations/analytics_*.sql`, `get_direction_*.sql`, `poisson_calibration.sql` non aperto: NON VERIFICATO se contengono calcoli Poisson); `calibration_analysis.py`, `backfill_poisson_calibrated.py`, `load_poisson_calibration_to_db.py` solo per il ruolo (grep), non per intero; tactical_engine/generate_predictions.py, run_worldcup.py; frontend PoissonPanel.tsx (solo consumatore, non analizzato).
