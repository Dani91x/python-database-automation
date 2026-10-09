# D - Componenti matematici fuori da bot e motori Poisson/ML: frontend, SQL, script di analisi (audit 09/10/2026)

Delegato D, SOLA LETTURA. R = radice del repo. Sonda numerica: `R/ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML/lavori/sonde/D_sonda_formule.py`
(eseguita con `.venv/Scripts/python.exe -I`, nessun import di produzione, nessuna scrittura).
Budget di ~60 chiamate rispettato: la copertura e' per CAMPIONE ragionato, NON esaustiva (vedi par. 6 e 2.9 "NON VERIFICATO").
Fonti esterne: citate dalla letteratura nota, NON riaperte in rete in questa sessione (nessuna WebSearch fatta: marcate "da memoria").

## 1. Inventario

| id | file:riga | cosa calcola (formula) | input | output | consumatore |
|----|-----------|------------------------|-------|--------|-------------|
| D01 | frontend/src/lib/ladderMath.ts:10-13 | green-up: locked = L + (W-L)/price (lordo commissione) | win, lose, prezzo | P&L bloccato | LadderView (:767,:964,:1118) |
| D02 | frontend/src/lib/ladderMath.ts:92-104 | placeProjection: back +S(P-1)/-S; lay -S(P-1)/+S; lay con liability S=L/(P-1) (lordo) | lato, prezzo, importo | ifWin/ifLose | popup conferma ordine |
| D03 | frontend/src/lib/eventPnl.ts:20-62 | MTM evento = somma positionMtm (= D01 con p=best_lay se W>L, best_back se W<L) | posizioni, book | mtm/priced/unpriced | MarketWatch.tsx:77, SeguiLive.tsx:345 |
| D04 | frontend/src/lib/cashOutPartita.ts:1-140 (+ r2 :~85) | cash out partita: green-up pieno per (mercato,selezione), importo round(abs(W-L)/p,2), commissione per MERCATO sul netto, pro-rata | gambe abbinate, prezzi | netto/lordo, fail-closed | Control Room (scheda partita) |
| D05 | frontend/src/lib/fairOverlay.ts:47-54 | EV back = p(P-1)(1-c)-(1-p); EV lay = (1-p)(1-c)-p(P-1) | prob modello, prezzo, c | EV per livello ladder | LadderView overlay |
| D06 | frontend/src/lib/kellySuggest.ts:37-54 | nessun calcolo: filtra kelly_stake del motore Python (live_engine_pro.py), arrotonda al centesimo | segnali live | chip stake | ladder |
| D07 | frontend/src/lib/riskMath.ts:111-120 | bookPercentage = 100 * somma(1/quota) (quote > 1) | quote | overround | UI rischio/ladder |
| D08 | frontend/src/lib/riskMath.ts:13-92 | scala tick Betfair (bande), nearestTick, tick a favore | prezzo | tick | regole rischio |
| D09 | frontend/src/lib/opportunities/tier0_arb.ts:66-126 | scenarioProfit (commissione per mercato sul netto positivo), dutching stake_i ∝ 1/o_i, hedgeLayStake = S((O-1)(1-c)+1)/(lo-c) | quote, stake, c | profitto garantito | pannello opportunita' (tier0-2) |
| D10 | frontend/src/lib/dailyHistory.ts:~830-960 | equity, drawdown (peak da 0), streaks, profitFactor = Σgross_profit/Σ|gross_loss|, expectancy = Σpnl/Σsettled, goalHitRate | righe giornaliere (RPC) | KPI storico | PerformancePanel, calendario |
| D11 | frontend/src/lib/dailyHistory.ts:~800-880 | summarizeDayTrades: pnl = Σ total_pnl regolati + chiusure regolate di aperte; V/P per SEGNO pnl (outcomeOf) | DayTrade[] | riepilogo giornata | dettaglio giornata |
| D12 | frontend/src/lib/analytics.ts:481-501 | mapResultToBacktestRow: turnover = total_pnl / roi (approssimato) | riga backtest flumine | BacktestRow | pagina backtest |
| D13 | frontend/src/lib/journalStats.ts:109-165 | bucket minuto da 15', Σ size, join settled per market_id (somma) | journal | pattern | Trade Journal |
| D14 | frontend/src/components/controlroom/SplitSport.tsx:244 | winRate = won/(won+lost) | contatori | % | Control Room |
| D15 | frontend/src/components/dashboard/DirezioniReport.tsx, DecisionsView.tsx, CreateStrategy.tsx | SOLO formattazione di hit_rate/roi/avg_odds calcolati lato SQL (nessuna ricostruzione) | RPC | tabelle/colori | pagine dashboard |
| D20 | migrations/analytics_rpc_veloci_2026-09-26.sql:405-412 (get_analytics, vigente) | Wilson 95% (z=1.96) su hit_rate; calib_gap = hit_rate - avg_prob | analytics_signals / riepilogo | wilson_low/high | pagina Analytics |
| D21 | migrations/analytics_rpc_veloci_2026-09-26.sql:219-249,567-646 (get_decisions, vigente) | hit_rate = hits/settled_placed; roi = pnl/stake sulle piazzate SETTLATE; avg_edge/avg_odds/avg_prob sull'INTERO gruppo | analytics_decisions / riepilogo | gruppi | pagina Decisioni |
| D22 | migrations/analytics_rpc_veloci_2026-09-26.sql:196-249 | riepilogo: conf_bin = least(floor(prob*20),19)*5, somme esatte (n, hit_sum, prob_sum) | signals, fixture_predictions (fonte API: pct/100 per H/D/A) | tabelle riepilogo | D20/D21 |
| D23 | migrations/direction_report_rpc.sql:99-147,297 (get_direction_report) | pnl per direzione = (odds-1)(1-c) se hit, -1 altrimenti; odds = MAX(engine_signals.odds); roi = Σpnl/N_prezzate; fasce quota | analytics_signals(poisson), engine_signals | report Direzioni | DirezioniReport.tsx |
| D24 | migrations/get_direction_rpc.sql:182-218 (get_direction) | affid = (n_l*hr_l+K*hr_g)/(n_l+K), K=50; Wilson su eff_n=n_l+K; lift = affid - base_g | pagella direzioni | affidabilita'/banda | UI Direzione, direzione.py |
| D25 | migrations/personal_tracking_manual_entry.sql:57-162 (recompute_personal_trade, vigente; copia vecchia personal_tracking_rpc.sql:273) | net/gross per back/lay (commissione sul vinto), cash-out back S(Oe-Ox)/Ox, lay S(Ox-Oe)/Ox; roi = net/STAKE; hourly_yield | trade personali | net_pnl, roi | Report Personale |
| D26 | migrations/personal_tracking_rpc.sql:594-840 (get_personal_report) | serie giornaliera, equity, drawdown, Sharpe=mean/vol(n-1), Sortino (target 0), Ulcer, CVaR5, Kurtosis campionaria, profit_factor (a livello GIORNO), roi per strategia | personal_trades | metrics jsonb | ReportPersonale.tsx |
| D27 | migrations/giornata_di_riferimento_giorno_partita_2026-10-01.sql:412-458 (trading_daily_history) | pnl_realized, gross_profit/loss per TRADE (trade_tot), win_rate = won/(won+lost), profit_factor, goal_pct | trades bot | righe giornaliere | D10/D11 |
| D28 | migrations/refresh_analytics_bets_range_v2_2026-09-24.sql:196-262 | pivot analytics_bets: odds_betfair = max(odds PLACED) altrimenti avg(odds); hit = bool_or | signals+decisions | analytics_bets | UI analytics |
| D30 | analytics_settlement.py:75-125 | hit per mercato (1x2, over/under linee, btts, DC, clean sheet, ht_ft) su punteggio 90' | match | True/False/None | merge_engine_signals, build_analytics_signals |
| D31 | analytics_market_stats.py:105-182 | baseline, mm10 a finestra piena, ritardi, versioni "in entrata" senza look-ahead | serie 0/1 | snapshot frequenza/ritardo | enrich_analytics_snapshots |
| D32 | market_intelligence/edge_scorer.py:159-190,316-380 | devig proporzionale per gruppo (1x2, o/u 2.5, btts); edge = 0.4*cal_bias + 0.6*(ml_prob-implied)*corr + xG*|rho|*0.10 (in PUNTI di probabilita') | raw_json_odds, calibrazione, ML, xG | composite_edge, direction | pipeline MI |
| D33 | market_intelligence/calibration.py:156-180 | per fascia di quota: implied_mean = media(1/odd GREZZA), real_rate, bias = real - implied, CI = z*sqrt(p(1-p)/n) chiamato "Wilson" | storico | tabella calibrazione | D32 |
| D34 | Betfair/money_management.py:2477-2535,1420-1440,1650-1668,2960-2985 | CLV = 1/closing - 1/entry (probabilita' grezze), P&L slot (1-c) sul vinto, yield = pnl/staked, verdetto SKILL_SIGNAL se media CLV > 0 | slot Poisson/ML | report Sheets | foglio "Google Sheets" |
| D35 | report_mm.py:17-120 | simulazione Masaniello/lineare/SL/flat su mm_history.json | storico slot | report a console | analisi manuale |
| D36 | Prediction/analyze_sweet_spot.py:9-80 | hit rate per soglie prob e lambda, "sweet spot" per lega (n>=20) | fixture_predictions + matches | JSON | soglie manuali |
| D37 | direzione.py (CLI) | nessun calcolo: thin client di get_direction | RPC | stampa | utente |

## 2. Analisi per componente

### 2.1 Formule di green-up / MTM / EV (D01-D07): corrette
- D01 verificata a mano: back 10@3 -> W=+20, L=-10; chiusura lay a 2.0: locked = -10 + 30/2 = +5.00 (sonda riga "lockedPnlAt = 5.00"); controllo diretto: stake lay 15 -> W 20-15=5, L -10+15=5. OK per back e lay, price<=1 -> ritorna L (fail-safe).
- Convenzione dei prezzi (D03): se W>L si chiude "layando" a best_lay (prezzo che il layer ottiene attraversando), se W<L backando a best_back: coerente con la terminologia Betfair (availableToLay[0] = prezzo al quale si puo' fare lay subito). Corretto.
- D05: evBack/evLay giuste (per 1 EUR di stake del backer; per il lay l'unita' e' lo stake, NON la liability: un +2% EV lay su 1 EUR di stake equivale a un EV/liability piu' basso di (P-1) volte; l'etichetta "B +4.2%/L +1.3%" non e' quindi confrontabile tra lati. BASSO).
- D06/D05: il Kelly vero e il fair 1/prob nascono in `Betfair/stream/engine/live_engine_pro.py` (perimetro bot: NON VERIFICATO qui). Il frontend e' solo filtro/formattazione (stantio > 120-150 s -> nascosto: corretto, mai fingere freschezza).
- D02: la proiezione e' LORDA di commissione (corretto dichiararlo; vedi R8).
- D07 bookPercentage corretto; ignora quote <=1.

### 2.2 Commissione: tre convenzioni nello stesso repo (R8)
- D01/D03/D02: lordo. D04 (cashOutPartita): per MERCATO sul netto positivo (come Betfair). D09 scenarioProfit: per mercato (corretto), MA hedgeLayStake (:123-127) deriva lo stake con la convenzione PER-SCOMMESSA (commissione sul profitto del back prima di sottrarre la perdita del lay).
  - Se le due gambe sono in mercati DIVERSI la formula equalizza davvero (sonda: win=lose=4.2564).
  - Se sono nello STESSO mercato (hedge back+lay sullo stesso runner) lo stake esatto e' S*O/lo (la commissione si cancella perche' entrambi i netti sono positivi). Esempio sonda: S=100, O=2.2, lo=2.0, c=5%: stake formula = 109.744 -> min(win,lose)=9.256; stake esatto 110.000 -> 9.500 su entrambi. Il profitto "garantito" esposto e' sottostimato di 0.244 EUR su 100 (2.6%) ed e' sub-ottimo. Conservativo, non pericoloso. Non verificato quali detector (:428, :518, :584) usino gambe nello stesso mercato (NON VERIFICATO).

### 2.3 Aggregati SQL di Analytics/Decisioni (D20-D22)
- Wilson (D20): centro (p + z²/2n)/(1+z²/n), semi-ampiezza z*sqrt((p(1-p)+z²/4n)/n)/(1+z²/n): identico alla definizione (Wilson 1927; Brown, Cai, DasGupta 2001, da memoria). CORRETTA.
- Il riepilogo usa somme esatte e divide a valle: "percentuale di somme", non media di percentuali: giusto. Parita' con il ramo diretto dichiarata nel file (stessa formula, stessa divisione numeric).
- ROI decisioni (D21): pnl/stake sulle SOLE piazzate settlate (stessa popolazione di hit_rate): coerente e dichiarato. `stake>0` evita la divisione per zero.
- Disomogeneita' (R6): avg_edge, avg_odds, avg_prob sono sull'INTERO gruppo (PLACED+REJECTED+NO_SIGNAL) mentre hit_rate/roi sono su piazzate-settlate. Un confronto hit_rate vs avg_prob nello stesso gruppo (calibrazione) confronta popolazioni diverse. La nota nel codice assume che "le scartate non hanno quota": NON VERIFICATO (non ho letto lo scrittore di analytics_decisions).
- Fonte 'api' (D22): H/D/A trattati come tre segnali: nei gruppi 1x2 hit_rate e avg_prob convergono a 1/3 per costruzione (utile solo per fascia di confidenza). Non e' un errore, ma il campo calib_gap aggregato per mercato non e' interpretabile. BASSO.
- conf_bin: prob=1.0 -> floor(20)=20 -> least(...,19): bordo ok.

### 2.4 Report Direzioni (D23) e get_direction (D24)
- D23: ROI = Σpnl / N_prezzate (stake fisso 1): definizione standard (ROI = profitto / stake totale; Betfair/Buchdahl "yield", da memoria). Commissione applicata sul vinto (corretto per un back singolo). Casi limite ok (priced_n>0).
- PROBLEMA (R1): la quota e' `max(es.odds)` su TUTTE le righe di engine_signals per (fixture, mercato, selezione), senza vincolo temporale ne' di motore: si sceglie a posteriori la quota piu' alta vista. E' selezione ottimistica: il ROI mostrato (con titolo "ROI alle quote Betfair") e' sistematicamente gonfiato. Dimensione dell'effetto NON MISURATA (DB non interrogato: la molteplicita' di righe per gruppo non e' stata contata).
- D24: shrinkage beta-binomiale con K=50 fisso (non stimato dai dati; empirical Bayes lo stimerebbe dalla varianza tra leghe). Wilson su eff_n = n_l+K tratta il prior come dati veri (banda piu' stretta del dovuto). BASSO.

### 2.5 Report Personale (D25-D26)
- Cash-out back S(Oe-Ox)/Ox e lay S(Ox-Oe)/Ox verificati a mano: coincidono con green-up (back 10@3 chiuso a 2: 5.00). Commissione solo sul positivo: ok.
- ROI = net_pnl / STAKE anche per i LAY (R3): lay 10@5: perde -40 -> ROI -400%; vince +9.50 -> +95%; stessa posizione su liability: -100% / +23.75%. Aggregato di 4 vinte + 1 persa: -2.00 EUR = -4.0% su stake ma -1.0% su liability (sonda). Roi per strategia (`get_personal_report` :776,794,812) e `profit_per_stake` (:~740) mescolano back e lay dividendo per lo stake: scala non confrontabile con i back e con i ROI di D23/D21 (che sono su stake del back). Convenzione di mercato: ROI/yield = profitto / capitale a rischio (liability per i lay) (da memoria: definizione di yield nei tipster/Betfair).
- Drawdown (R4): SQL `peak = max(equity)` sulle righe, SENZA il punto iniziale 0; il frontend `drawdown()` parte da peak=0. Serie [-10,-20]: SQL max_drawdown = -20, frontend = 30 (sonda). Le due viste (Report Personale vs storico bot) chiamano "max drawdown" cose diverse; per chi inizia in perdita il SQL non conta la prima discesa.
- Ulcer index (:675): DD% = (equity-peak)/peak*100 con peak = massimo dell'equity CUMULATA da 0 (non del capitale): con peak piccolo (es. 1 EUR) un -20 EUR da' -2100%; con peak<=0 forza 0. Non e' l'ulcer di Martin (capitale). MEDIO/BASSO.
- Sharpe = media/dev.std (n-1) del P&L giornaliero in EUR (non annualizzato, non su rendimenti): etichetta fuorviante (BASSO). Calmar e recovery_factor hanno formula IDENTICA (tot/|maxDD|): duplicato. Kurtosis (formula Excel KURT) e CVaR 5% verificate: corrette.
- profit_factor: qui a livello di GIORNO (somma giorni positivi / somma giorni negativi), nel D10/D27 a livello di TRADE (gross_profit/gross_loss da trade_tot): stesso nome, definizioni diverse (R9).

### 2.6 Storico bot (D10, D11, D27)
- pnl_realized = Σ settled_rows per op_day; gross_profit/loss = Σ total_pnl per trade con settled_day. Le due attribuzioni non sono la stessa partizione (op_day vs settled_day): Σgross_profit - Σgross_loss puo' differire da pnl_realized per costruzione (le chiusure regolate di posizioni ancora aperte sono in pnl ma non in gross). NON VERIFICATO numericamente.
- win_rate = won/(won+lost) esclude i void (coerente con SplitSport D14); expectancy (D10) = Σpnl_realized / Σsettled dove settled include i void e pnl_realized include coperture di posizioni ancora aperte: numeratore e denominatore su popolazioni diverse. BASSO.
- Drawdown e streaks a granularita' GIORNALIERA (peggior intraday non visto). BASSO.
- outcomeOf (V/P per segno del P&L) dichiarato identico alle RPC SQL: coerente.

### 2.7 Script Python di analisi (D30-D36)
- D30 settlement: hit corretto su punteggio 90' (fulltime_* primario, AET/PEN senza fulltime -> None); linee X.5 senza push; clean sheet, DC, ht_ft verificati leggendo il codice. Positivo.
- D31: finestre "in entrata" senza look-ahead (positivo); `media` dei ritardi = media dei contatori correnti per ogni partita con rit!=0, NON la lunghezza media dei ritardi conclusi (un intervallo di lunghezza g contribuisce 1..g, media (g+1)/2): descrittivo, semantica da dichiarare. BASSO.
- D32 edge_scorer: devig PROPORZIONALE (p/Σp). Alternative note: Shin (1993), power/odds-ratio: correggono il favourite-longshot bias (Štrumbelj 2014, "On determining probability forecasts from betting odds", IJF; Clarke et al. 2017 – da memoria): miglioramento di precisione, non errore.
  - L'edge e' in PUNTI di probabilita' con soglia fissa 0.02 (MIN_COMPOSITE_EDGE): +2 pp equivalgono a EV ~ +3% a quota 1.5 ma ~ +20% a quota 10: non comparabile tra quote.
  - Con una sola componente l'edge non e' scalato dal peso (solo ML: edge_raw = ml_div intero; con entrambe media 0.4/0.6): ampiezze incoerenti.
  - Boost xG = ±|spearman_r|*0.10: un coefficiente di correlazione di rango usato come ampiezza di probabilita' (euristica senza fondamento statistico).
- D33 calibrazione (R2): (a) bias = real_rate - media(1/odd GREZZA) ma in D32:330 si somma a implied_prob DEVIGATA: true_prob = fair + (real - raw) sottostima la realta' del margine. Sonda: raw 0.40, fair 0.385, real 0.40 -> true_prob 0.385 (-0.015, quasi la soglia 0.02). (b) `_wilson_ci` (calibration.py:~150) e' in realta' WALD z*sqrt(p(1-p)/n): n=30,p=0.9 -> (0.793,1.007) (>1), p=1 -> ampiezza 0; Wilson reale (0.744,0.965) e (0.886,1.0) (sonda). Flag `significant` calcolato su Wald. (c) edge_scorer usa la cella con n>=5 (:226-250) senza controllare `significant`; le celle in cache hanno gia' n>=30 (MIN_BRACKET_SAMPLES=30, mi_config.py:19), ma con n=30, p=.5 l'errore standard e' ~0.09 contro soglia edge 0.02: segnali di calibrazione dominati dal rumore, con molteplicita' (mercati x fasce x leghe) non corretta.
- D34 CLV (R5): `clv = 1/closing - 1/entry` con probabilita' GREZZE e commento "il margine si cancella": falso se il margine cambia tra ingresso e chiusura (stessa prob fair 0.50, overround 1.04 -> 1.02: CLV = -0.0100 con valore vero zero, sonda). Definizione standard: confronto con la quota di chiusura SENZA margine (Pinnacle/Buchdahl, da memoria) oppure rapporto quote entry/close-1. "Chiusura" = quote a ~5 minuti dal KO (`update_closing_odds`), non l'ultima. Verdetto "SKILL_SIGNAL" se media>0 senza test (std calcolata ma non usata: t = media/(std/sqrt(n))). P&L slot: (1-c) sul vinto per singola puntata = esatto per un back isolato; il ricalcolo retroattivo (:1357-1372) riscrive il P&L dei vinti con la commissione ATTUALE di config (storico non immutabile).
- D35 report_mm: usa N = numero di segnali dell'intera giornata gia' conosciuto (look-ahead), `avg_q` medio al posto della quota di ogni segnale, nessuna commissione, W=50% fisso: simulazione illustrativa, non evidenza. BASSO (solo report).
- D36 analyze_sweet_spot: `sb.table(...).select(...).execute()` senza paginazione (:~20): PostgREST restituisce al massimo 1000 righe di default (NON VERIFICATO il tetto configurato) -> campione troncato; soglie e leghe scelte in-sample (top-10 per hit rate con n>=20): data dredging, nessuna correzione. MEDIO se i risultati guidano soglie operative; non verificato che lo facciano.

### 2.8 Frontend: cosa NON ricalcola
La maggior parte delle KPI delle pagine (DirezioniReport, DecisionsView, CreateStrategy, PerformancePanel) legge numeri gia' calcolati da SQL/RPC e li formatta; le copie reali della stessa formula sono quelle della tabella al par. 2.9.

### 2.9 Coppie di copie e divergenze (coerenza Python/SQL/frontend)
| grandezza | copie | divergono? | esempio |
|-----------|-------|------------|---------|
| Green-up locked | ladderMath.lockedPnlAt (:10) = eventPnl.positionMtm (:30) = CashOutButton (commento :8) = greenup.py (non letto) | identiche (lordo) | back 10@3 chiuso a 2 = +5.00 |
| Chiudi-ora lordo vs netto | lockedPnlAt/eventMtm (lordo) vs cashOutPartita (netto per mercato, :37-40) | SI per costruzione (differenza = commissione sul netto positivo) | +5.00 lordo vs +4.75 netto a c=5% sullo stesso mercato; NON VERIFICATO quale etichetta mostri la UI nei punti D03/D01 |
| ROI | D21 (pnl/stake piazzate settlate), D23 (Σpnl/N, stake 1), D25/D26 (net/stake anche lay), D34 (yield pnl/staked), run_backtest.py:174 (pnl/stake, non letto) | SI: denominatore diverso (stake unitario / stake / liability), popolazioni diverse | lay 10@5: -400% vs -100% |
| Drawdown | D10 (peak da 0) vs D26 (peak da prima riga) | SI | [-10,-20]: 30 vs 20 |
| Profit factor | D10/D27 (per trade) vs D26 (per giorno) | SI | stesso nome |
| Win rate / hit rate | D14, D27 (won/(won+lost)), D21 (hits/settled_placed), D23 (hit su direzioni) | popolazioni diverse, formula uguale | - |
| Wilson | D20 (SQL, corretta) vs D24 (SQL, su eff_n) vs D33 (Wald mascherata) | SI (D33) | n=30,p=.9: [0.744,0.965] vs [0.793,1.007] |
| Implicita/devig | D32 (proporzionale) vs D33 (grezza) vs D34 (grezza) vs engine ML gate (0.975, citato in money_management.py:~2500) | SI: 4 definizioni | R2, R5 |
| Settlement hit | D30 (Python) vs SQL market_frequency_rpc (dichiarata coerente nel docstring) | NON VERIFICATO (non ho letto l'RPC SQL) | - |

## 3. Reperti

R1 - ALTO (da misurare) - direction_report_rpc.sql:103,142-143 - `max(es.odds)` per (fixture,mercato,selezione) su tutte le righe di engine_signals: quota scelta a posteriori. Prova: `select es.fixture_id, mp.market, mp.selection, max(es.odds) as odds ... group by` poi `when r.hit then (bf.odds - 1) * (1 - v_comm)`. Impatto: il "ROI alle quote Betfair" delle Direzioni e' ottimistico di una quantita' non misurata; guida la fiducia dell'utente nel segnale. Se per ogni gruppo esiste una sola riga l'effetto e' nullo (NON VERIFICATO: DB non toccato).

R2 - MEDIO - market_intelligence/calibration.py:152,165 + edge_scorer.py:330 + :226-250 - bias su implicita grezza sommato a implicita devigata; `significant` mai usato; `_wilson_ci` e' Wald; edge in punti probabilita' con soglia fissa. Prova sonda (par. 2.7). Impatto: segnali "value/avoid" di market_intelligence inclinati di ~-1.5 pp e dominati dal rumore a n=30; non e' collegato a ordini (consumatore: pipeline/audit MI; NON VERIFICATO se alimenta consigli UI).

R3 - MEDIO - personal_tracking_manual_entry.sql:94 e personal_tracking_rpc.sql:776,794,812 - ROI = net/stake anche per i lay. Prova sonda (par. 2.5). Impatto: ROI del Report Personale non confrontabile tra back e lay, e distorto in presenza di lay a quote alte; nessun effetto sui soldi, effetto sul giudizio.

R4 - MEDIO - get_personal_report SQL :639-645 vs dailyHistory.ts drawdown() - peak senza punto 0 vs peak da 0. Prova: serie [-10,-20] -> 20 vs 30. Impatto: max drawdown sottostimato nel Report Personale per chi parte in perdita.

R5 - MEDIO - Betfair/money_management.py:2494-2511,2971-2985 - CLV su probabilita' grezze (il margine non si cancella), "chiusura" a ~5 min dal KO, verdetto senza test. Prova: stessa prob fair 0.50, overround 1.04->1.02 -> CLV -0.0100 (sonda). Impatto: indicatore di "skill" non affidabile come criterio di promozione del motore (consumatore: foglio Sheets).

R6 - MEDIO/BASSO - analytics_rpc_veloci_2026-09-26.sql:598-640 - avg_edge/avg_odds/avg_prob su tutto il gruppo, hit_rate/roi sulle sole piazzate settlate. Impatto: confronti di calibrazione sulle Decisioni su popolazioni diverse.

R7 - MEDIO (non verificato il tetto) - Prediction/analyze_sweet_spot.py (select senza paginazione + soglie in-sample). Impatto: soglie "sweet spot" potenzialmente fondate su 1000 righe e su dredging.

R8 - BASSO/MEDIO - ladderMath.ts:10 / eventPnl.ts:30 (lordo) vs cashOutPartita.ts (netto) vs tier0_arb.ts:123 (per-scommessa). Prova sonda hedge stesso mercato: 9.256 vs 9.500. Impatto: differenze di ~5% del netto tra due "chiudi ora" e profitto garantito sottostimato di ~2.6% se le gambe sono nello stesso mercato.

R9 - BASSO - definizioni diverse con lo stesso nome (profit factor per trade vs per giorno; Sharpe non annualizzato; Calmar = recovery_factor; Ulcer su equity cumulata, personal_tracking_rpc.sql:675; expectancy con numeratore/denominatore disomogenei, dailyHistory.ts).

R10 - BASSO - analytics.ts:494 `turnover = total_pnl / roi` (ricostruzione approssimata, NaN-safe solo se roi=0 -> null); get_direction K=50 fisso; report_mm look-ahead; `media` ritardi in analytics_market_stats.py:123-145.

Positivi verificati: Wilson SQL (D20) esatta; settlement hit (D30) corretto; frontend "mai inventare un numero" (null/unpriced, fail-closed); frontend mai stale (signalsStale); riepilogo = somme esatte (non medie di percentuali); finestre "in entrata" senza look-ahead (D31); cash-out personale = green-up; Kurtosis/CVaR corrette.

## 4. Miglioramenti proposti
1. Direzioni: usare la quota dell'ultima rilevazione PRIMA del KO (o quella del segnale piazzato), non il max; guadagno: ROI onesto; costo: 1 migrazione (SQL), misura: confronto ROI vecchio/nuovo sugli ultimi 30 giorni; rischio basso; tocca get_direction_report.
2. Una sola definizione di ROI/drawdown/profit factor documentata in un modulo SQL/TS condiviso (ROI su liability per i lay, peak da 0); misura: test di contratto che confronta Python/SQL/TS sugli stessi 20 trade; costo medio.
3. Calibrazione MI: bias su implicita devigata, Wilson reale, uso di `significant`, soglia edge in EV%; metrica: log-loss/Brier fuori campione (walk-forward) con e senza; costo medio; non tocca bot.
4. CLV: confrontare con quota di chiusura devigata (Shin/power) e riportare media, errore standard e t-stat; metrica: stabilita' rank tra periodi.
5. Devig Shin/power al posto del proporzionale (Štrumbelj 2014); metrica: log-loss delle probabilita' implicite sul risultato su 1X2.
6. Etichetta UI "lordo/netto commissione" accanto ai due chiudi-ora; hedge stesso mercato con S*O/lo.
7. Paginare analyze_sweet_spot e valutare le soglie su split temporale.

## 5. Decisioni per l'utente
Nessuna di queste proposte altera soglie/stake/gambe dei bot. Da decidere dall'utente: (a) se il ROI dei lay nel Report Personale debba passare a base liability (cambia numeri storici); (b) se la quota usata nel report Direzioni debba cambiare (cambia il ROI mostrato); (c) se la commissione dei P&L storici di money_management debba restare ricalcolata con la config attuale (:1357).

## 6. Metodo di ricerca e limiti
- Frontend: `grep -rIlE "toFixed|Math\.|reduce\(|roi|yield|pnl|commission|kelly|implied"` su frontend/src (non test) -> ~60 file con >500 righe; letti per intero o per estratti solo i moduli puri di calcolo (`lib/ladderMath`, `riskMath`, `eventPnl`, `journalStats`, `kellySuggest`, `fairOverlay`, `cashOutPartita` :1-140, `dailyHistory` :760-1000, `analytics` :470-520, `opportunities/tier0_arb` estratti). Grep mirati di roi|yield|hitRate|profitFactor|drawdown|clv|kelly|implied.
- SQL: `grep -rInE "\broi\b|hit_rate|avg_odds|profit_factor|win_rate|yield"` su sql/ e migrations/ -> 20 file; letti: analytics_rpc_veloci (vigente), direction_report_rpc, get_direction_rpc, personal_tracking_rpc + manual_entry, giornata_di_riferimento (estratto), refresh_analytics_bets_range_v2 (estratto).
- Python: letti analytics_settlement, analytics_market_stats (105-182), market_intelligence (edge_scorer, calibration, mi_config), report_mm, analyze_sweet_spot, direzione.py, money_management.py (estratti CLV/P&L/stats); grep di definizioni su ventaglio_segnali, valida_ventaglio, tactical_engine/report.py, season_aggregates.py (quest'ultimo e' logica di copertura, non matematica).
- xG/Elo: `git grep -liE "\bxg\b|expected_goals|\belo\b"` -> file fuori da Ai Engine in Betfair/omega, Betfair/safe_strategy, Betfair/mike, stream/scalper, tactical_engine, market_intelligence, training_planner.py: appartengono ai perimetri bot/Poisson degli altri delegati; qui trattato solo l'uso in market_intelligence (xG boost D32).
- Nota: una prima grep ricorsiva senza `git grep` ha attraversato il log da 3 GB ed e' stata interrotta; poi uso di `git grep` (solo file tracciati) e kill dei `grep.exe` lanciati da me. Nessun file di produzione toccato.

NON VERIFICATO (non letti per budget): funzioni SQL dei bot (omega_*, mike_*, safe_*, tennis_bot_pnl, pnl_betfair_reale, storico_sport, posizioni_chiuse, live_backtest) e il loro ROI/pnl; Kelly in live_engine_pro.py; build_analytics_signals.py, enrich_analytics_snapshots.py, refresh_analytics_bets (parte pnl), merge_engine_signals (origine di pnl/stake delle decisioni), build_direzione.py, ventaglio_segnali.py, build_inplay_intensity.py; frontend: DutchingPanel, XHedgePanel, CashOutButton, MultiTradeForm, ReportPersonale.tsx/personalReport.ts, storicoSport.ts, posizioniChiuse.ts, tennis.ts; Telegram bot; fusi orari delle aggregazioni (solo get_direction_report usa Europe/Rome in modo esplicito, :60-63,:96).
