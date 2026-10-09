# E2 - Lacune lasciate da C e D (audit matematica 09/10/2026)

Sola lettura. Sonde: `lavori/sonde/e2_kelly_tau.py`, `lavori/sonde/e2_dutch_tennis_combos.py` (importano il codice di
produzione, nessuna rete). Tutte le cifre sotto vengono da queste esecuzioni. Cio' che non ho verificato e' marcato NON VERIFICATO.

Esito in breve: Kelly back/lay di live_engine_pro, `_best_split`, `dutch_*` lato server, `price()` Telegram, `suggest_cs_hedge` e il
green-up del CashOutButton sono CORRETTI (verificati a mano e per massimizzazione numerica). Trovati 2 reperti ALTI sul dutching
(UI variable e modo variable+lay), piu' reperti MEDI/BASSI.

## 1. Inventario

| id | file:riga | formula | consumatore |
|----|-----------|---------|-------------|
| K2 | stream/engine/live_engine_pro.py:414-440 | `_kelly_back` f=p-(1-p)/b, b=(o-1)(1-c); `_kelly_lay` stake=(1-p)/(L-1)-p/(1-c), per `fraction*bank` | segnali live UI, sim_strategy, MarketSignal.kelly_stake |
| E1 | live_engine_pro.py:588-600 | EV per 1 EUR di stake back/lay, netto commissione; gate `decided` p<=.03 o >=.97; min_edge su EV; min_liquidity | segnali UI |
| T1 | live_engine_pro.py:58-83,510-513 | `effective_rho`: DC solo a 0-0 e solo se tau>0 sulle 4 celle | evaluate_event |
| T2 | value_engine/bivariate.py:167-181 | `conditional_markets`: tau DC sulla griglia dei gol RIMANENTI a qualunque punteggio | solo value_engine (generate_battery, markets.evaluate) e il port TS del bot Telegram (calc.ts:165-176) |
| N1 | safe_strategy/tennis_opportunity.py:126-137 | hold da P(punto servizio): p^4+4p^4q+10p^4q^2+20p^3q^3*p^2/(p^2+q^2) | `_holds` |
| N2 | tennis_opportunity.py:244-275 | adj = raw -/+ retire_risk (2% bo3, 3% bo5), leader perde rr, chi insegue guadagna rr | p_win, evaluate, bot_service.5200-5240 (uscite) |
| N3 | tennis_opportunity.py:414-480 | back: p>=0.90, edge=p-1/q>=0.015, EV netto>0; lay: p<=0.10, q<=8; conf = .35 c_edge+.25 c_head+.20 c_depth+.20 c_fresh, x(1-min(.5,5rr)) | segnali tennis Safe |
| N4 | safe_strategy/combos.py:194-246 | `_net_from_units` (commissione per MERCATO sul positivo), `_best_split` (ternaria su min dei saldi netti) | combo Safe (coppie) |
| N5 | combos.py:520-534 + trading/dutching.py | dutch_back sui runner vivi se book<1; stake round(T*(1/p)/sum,2) | combo `dutch` |
| M1 | mike/engine.py:1045-1127 | `cashout_value`: lordo=min(W',L') per chiave di mercato, commissione per MERCATO pro-rata, residuo sulla cella piu' pesante | uscite smart Mike, UI cash-out Mike |
| S1 | build_analytics_signals.py:232-314 | estrattori prob, `n_engines_agree`, `consensus_prob` = media delle prob dei SOLI motori che scelgono la selezione, `oos_valid=True` fisso (riga 298) | analytics_signals -> bet_features |
| S2 | merge_engine_signals.py:120-205 | stesso `oos_valid=True` (203); prob per-scommessa solo in analytics_decisions | analytics_decisions/pagella |
| S3 | build_direzione.py:196-232 | hit rate per fascia di prob (.30/.40/.50/.60/.70), n minimo 20 globale / 10 per lega, base_rate = media hit | direction_pagella -> get_direction (UI Direzione) |
| S4 | ventaglio_segnali.py:216-262 | score euristico = MARKET_BASE + bonus (conv. Poisson, concordanza, ML calibrato, regime) clamp [.40,.85]; tier A_MAX>=.72 | solo CLI + valida_ventaglio.py |
| S5 | direzione.py | thin client (nessuna matematica propria) | CLI |
| F1 | frontend DutchingPanel.tsx:194-209 | anteprima: stake_i=T*w_i/sum w, w_i=(1/q_i)*peso_utente; profit_i=stake_i*q_i-T; liability=stake*(q-1) | UI Dutching |
| F2 | trading/dutching.py:184-244 (server) | variable: s_i=(T+k w_i)/p_i, k=T(1-sum 1/p)/sum(w/p) (profitto ~ peso) | live_order_worker.py:2916-2919 |
| F3 | CashOutButton.tsx:46-73 | stake pieno=|W-L|/p; lato=LAY se W>L; esiti dopo copertura; netto = pnl*(1-c) se >0 | UI cash-out Safe/Omega |
| F4 | trading/xhedge.py:156-215 | x*=(m_altri-P(w))/O, un solo back CS sullo scoreline peggiore | XHedgePanel |
| F5 | ReportPersonale.tsx | solo visualizzazione (Sharpe/Sortino/Calmar/DD arrivano dalla RPC get_personal_report, gia' coperta in D) | UI |
| Q1 | migrations/giornata_di_riferimento_giorno_partita_2026-10-01.sql:237-484 | `trading_daily_history` (vigente): P&L per giorno, win/lost per TRADE, commissione per mercato | get_omega/safe/mike_daily |
| Q2 | migrations/tennis_bot_daily_giorno_partita_2026-09-30.sql | `get_tennis_bot_daily`: vinti/persi per ORDINE, pnl netto = coalesce(pnl_betfair, pnl-commission) | UI tennis |
| TG | Telegram bot/.../calc.ts:193-199 | `price()`: minBack=1+(1-p)/(p(1-c)), maxLay=1+(1-p)(1-c)/p | bot Telegram |

## 2. Analisi per componente

### 2.1 Kelly di live_engine_pro (K2) - CORRETTO
- Back: sonda p=.55, o=2, c=.05, k=1, bank 100 -> 7.6316 = a mano f=.55-.45/.95=0.07632. Massimo numerico del log-growth: 7.63.
- Lay: sonda p=.30, L=3, c=.05 -> stake 3.421, massimo numerico del log-growth sullo stake 3.420 (liability 6.84). Per p=.10 L=10 e p=.45 L=2.5 sia Kelly sia il massimo numerico sono 0 (EV<0). La formula f=(1-p)/(L-1)-p/(1-c) e' esatta se la frazione di bankroll e' misurata sullo STAKE e la perdita e' stake*(L-1) (derivazione: rischio r=stake*(L-1), b=(1-c)/(L-1), f_r=(1-p)-p/b, stake=f_r/(L-1)).
- Coerenza con EV (E1): `kelly>0` solo se best_ev>=min_edge e c'e' liquidita'; un EV>0 e un Kelly>0 coincidono (stesso p, prezzo, c): nessuna divergenza gate/Kelly.
- Casi limite: odds<=1 -> 0; `b<=0` -> 0; mercato `decided` (p<=.03 o >=.97) non da' segnale; p calibrata e rinormalizzata (`_cal`) solo se `_CALIBRATION_ENABLED` (False oggi, riga 114) -> comportamento = identita'.
- Lato scelto = max EV PER STAKE fra back e lay, non per rischio (gia' reperto R6 di C): su quote alte il lay risulta sistematicamente "piu' redditizio" per stake mentre rischia (L-1) volte di piu'.
- Etichetta: `kelly_stake` e' lo STAKE (backer) anche per il lay, la liability e' stake*(L-1) (C: R5). Il Telegram mostra "Puntata Ottimale: {kelly_stake}" senza lato (vedi 2.7).

### 2.2 Tau Dixon-Coles in-play (T1 vs T2) - divergenza QUANTIFICATA
- `live_engine_pro.effective_rho` (58-83) usa rho=0 se il punteggio non e' 0-0 (motivo dichiarato: la tau e' calibrata sui RISULTATI FINALI bassi, a 1-1 colpirebbe il finale 2-2). `bivariate.conditional_markets` (167-181) applica sempre rho=-0.13 alla griglia dei gol rimanenti.
- Sonda (lambda pre-match 1.5/1.2, rho -0.13; prima cifra live_engine_pro, seconda conditional_markets):

| punteggio, minuto | H | D | A | O2.5 |
|---|---|---|---|---|
| 0-0, 30' | .3741/.3741 | .3608/.3608 | .2650/.2650 | .2694/.2694 |
| 1-0, 60' | .7808/.7913 | .1794/.1689 | .0398/.0398 | .2275/.2381 |
| 1-1, 60' | .2887/.2781 | .4920/.5132 | .2192/.2087 | .5934/.5829 |
| 0-1, 70' | .0352/.0352 | .1912/.1848 | .7736/.7800 | .1219/.1282 |
| 2-1, 75' | .8554/.8595 | .1307/.1266 | .0139/.0139 | 1/1 |

  Scarto massimo 2.1 punti percentuali (pareggio a 1-1: 49.2% vs 51.3%). Per un back del pareggio a quota 2.1 (q implicita 47.6%) il segno dell'edge cambia fra le due convenzioni (49.2% > 47.6% edge +1.6; 51.3% edge +3.7): il motore live e' il piu' prudente. Nessuna delle due e' dimostrata migliore (la tau DC da letteratura, Dixon & Coles 1997 J. R. Stat. Soc. C 46, e' definita sul punteggio finale a bassi punteggi): e' una divergenza di convenzione. Consumatori di `conditional_markets`: solo `value_engine/*` e il port TS `calc.ts` del Telegram (non i bot di trading), quindi nessun impatto diretto sui soldi; impatto sui prezzi "minBack/maxLay" mostrati dal bot Telegram. Da portare all'utente, non si altera.

### 2.3 Tennis (N1-N5)
- N1 `hold_from_serve_point(0.65)` = 0.8296 (formula chiusa standard: giochi a 40-40 con deuce p^2/(p^2+q^2)); corretto.
- `_holds`: prior 0.75 (sonda), dato reale per giocatore se c'e'. `estimate_holds(0,0,0,0)` = 0.7917 (il difetto del 12/09 e del 13/09): vive ancora come RIPIEGO in bot_service.py:5230 (`ha, hb = estimate_holds(0, 0, 0, 0)`), usato solo se `_p_tennis_dal_modello` ritorna None (modulo non importabile, payload senza `sets`/`games` interpretabili). In quel ramo la P(vittoria) e' gonfiata (0.9311 vs 0.9038 a 1 set + 4-2, misura dichiarata nel codice) e manca il rischio di ritiro. BASSO (ramo di emergenza), ma e' lo stesso difetto gia' corretto altrove.
- Sonda p_win: 1 set + 3-1, hold .75 -> raw .9039, adj (ritiro 2%) .8839 -> sotto la soglia di back .90: nessun segnale; 1 set + 4-2 -> raw .9238, adj .9038 -> segnale possibile. La soglia .90 sta quindi circa a 1 set + 4-2 con servizio ignoto.
- N2 asimmetria: a 0-0 senza servizio noto raw=.50 -> `raw1 >= 0.5` e' vero per p1 -> adj p1 = .48, p2 = .52 (sonda). Il pareggio esatto penalizza sempre p1. Irrilevante sui soldi (le soglie .90/.10 non sono raggiungibili da .48/.52) ma e' un effetto di bordo del confronto `>= 0.5`. BASSO.
- N2 modello di ritiro: l'intero rischio rr viene tolto al leader e dato a chi insegue (se si ritira il leader), mentre l'evento "si ritira chi insegue" (leader vince a tavolino) e' trascurato; scelta prudente dichiarata nel docstring ("perdita totale"), non un errore.
- N3: EV back = p(q-1)(1-c)-(1-p) e lay = (1-p)(1-c)-p(q-1): coincidono con live_engine_pro E1. Gate edge lordo p-1/q >= 0.015 poi EV netto>0: con c=5% e q=1.05, p=.93: edge .0 ... il gate `min_back_price` 1.02 evita lo scenario. `p_implied` (devig) e' solo informativo, l'edge usa 1/price grezzo: coerente con il commento.
- N4 `_best_split`: la funzione `min_k net_k(b)` e' concava (somma di f(v)=v se v<=0, (1-c)v se v>0, concava, di funzioni lineari in b, poi minimo di concave). Sonda: mercato stesso Over2.5@2.2 + Under2.5@2.1: griglia fine (1/1000) max 0.06992 a b=.488, ternaria b=.4884 valore 0.07070 (la ternaria e' piu' fine della griglia); mercati diversi senza lock: griglia e ternaria concordano (-0.5 a b=0). Con `tol>0` (arrotondamento) la funzione non e' piu' concava (max(0,s-tol) e' convessa) ma `_best_split` la chiama con tol=0. CORRETTO.
- N5: `dutch_back` usa gli stake arrotondati al centesimo: `total_stake` pubblicato puo' superare il richiesto di qualche centesimo (variable, sonda: 100.01 per T=100); BASSO.
- Dutching server: back equal profitto = T(1-B)/B (sonda quote 2.5/3/4, T=100: profitti 1.70/1.70/1.68 a centesimi), lay = T - l_k p_k; dutch_variable profitto ~ peso (1.26/2.53/1.27 per pesi 1/2/1). `dutch_back_for_target`: T=target*B/(1-B) (sonda: target 5.00 -> totale 295.00, profitto LORDO 5.00, netto 4.75): il "target" e' LORDO di commissione, non e' scritto in UI (vedi reperto 5).

### 2.4 Frontend (F1-F5)
- F1 vs F2 (variable): anteprima e server calcolano due cose DIVERSE (sonda, quote 2.5/3.0/4.0, pesi 1/2/1, T=100):
  - server: stake 40.51/34.18/25.32, profitto 1.26/2.53/1.27 (profitto proporzionale al peso);
  - anteprima UI: stake 30.38/50.63/18.99, profitto -24.05/+51.89/-24.04 (stake ~ peso/quota).
  L'utente conferma guardando numeri sbagliati (vedi reperto 1). In modo equal/target UI e server coincidono.
- F3 CashOutButton: green pieno stake=|W-L|/p, lato LAY se W>L: verificato a mano (W=+10, L=-5, lay@2: stake 7.5 -> 2.5/2.5; W=-5, L=10, back@2: 7.5 -> 2.5/2.5). Commissione netAfterCommission: solo sul positivo, accetta 0.05 o 5 (soglia >1): c=1 viene letto come 1 (cioe' 100%), c=1.0 e' ambiguo con "1%" (BASSO, stesso difetto di `calc_edge`).
- F4 xhedge: x*=(m-P(w))/O verificato algebricamente (P(w)+x(O-1)=m-x); un solo passo, non porta il worst a pareggio con tutti gli scoreline, ma lo alza sempre (m-x>P(w) perche' O>1). Griglia 0..8 gol; il P&L e' LORDO di commissione (la commissione del CS e' per mercato e puo' differire dal mercato delle posizioni). BASSO.
- F5 ReportPersonale.tsx: nessuna matematica propria (visualizza i campi della RPC); DD/Sharpe gia' in D (R3-R5).

### 2.5 Mike cashout_value vs netto realizzabile (M1)
- Dal 29/09 (M3.4) `exposure()` e `open_selections` lavorano PER MERCATO con UNA chiave per mercato (engine.py:760-790, 883-896): una gamba sull'altra selezione pesa rovesciata. Quindi `cashout_value` somma min(W',L') per mercato: la somma dei lock per selezione che C marcava "approssimazione" non esiste piu'. Per mercato il green-up chiude le due uscite allo stesso importo, quindi lock lordo = min(W',L') con W'~L' (arrotondamento a centesimo): e' realizzabile al centesimo, `min` e' prudente.
- Commissione: per MERCATO sul lordo totale (`net=sum(_net(v))`, riga 1109): corretto per Betfair. Esempio: OU45 lordo +10.00, OU35 lordo -3.00 -> net = 10*0.95 + (-3) = 6.50 (mercati diversi non si compensano) = a mano. Un solo mercato +10 / -3 per selezione non puo' accadere (una chiave per mercato).
- Slippage: il prezzo e' il best del libro + `place_at_ticks`; il valore non include la profondita' (size disponibile): se la size al prezzo e' inferiore alla chiusura, il numero mostrato non e' garantito. NON VERIFICATO se `books` porta la size o solo il prezzo (richiede replay/UI, vietato).
- Gambe `archived` (ciclo pre-match chiuso in green) sono ESCLUSE da exposure e quindi dalla base della commissione del mercato (engine.py:776). Betfair netta per mercato su TUTTE le puntate: un lock pre-match archiviato +X e un cash-out in-play +Y pagano c*(X+Y) in totale; il modello paga c*Y qui e c*X (da archivio) altrove, uguale solo se le due parti hanno lo stesso segno: con segni opposti (X=+10 pre-match, Y=-4 in-play) la commissione reale e' 0.05*6=0.30 contro 0.50 stimata (sovrastima 0.20). NON VERIFICATO se l'archivio liquida la commissione separatamente (engine.py:2435 e 5319-5322 non letti per budget). BASSO.
- Non si replica: nessun replay.

### 2.6 Script analytics (S1-S5): soglie, medie, leakage
- S1 (build_analytics_signals): `oos_valid=True` e' scritto SEMPRE (riga 298; merge_engine_signals.py:203 idem), mentre la colonna esiste per marcare "ML puo' essere false" (migrations/analytics_signals.sql:85). Nessun controllo `generated_at < kickoff`. Le RPC usano `p_ml_clean = ml_oos_valid AND ml_reliable` (analytics_strategy_rpc.sql:114,217): la meta' `ml_oos_valid` e' quindi sempre vera e il filtro "pulito" dipende SOLO da `ml_reliable`. Il rischio di leakage temporale (predizioni ML rigenerate DOPO la partita, o modelli addestrati includendo la partita) NON e' escluso dalla colonna. NON VERIFICATO sul DB (richiede confrontare `generated_at` e `kickoff` su campione): MEDIO. Il forward (populator) e' pre-partita per costruzione solo se gira prima del calcio d'inizio.
- S1 `consensus_prob` = media delle prob dei soli motori il cui top-pick e' QUELLA selezione (righe 308-313): e' condizionata all'accordo (se un solo motore sceglie la selezione, consensus = prob di quel motore) e vale None per le selezioni non-top; non e' una prob di consenso fra tutti i motori. BASSO; dipende da come la usano i consumatori (non letti).
- S1 estrattore Poisson: usa `markets_calibrated` quando c'e' e il grezzo come ripiego per fixture diverse nello stesso dataset: le righe mescolano prob calibrate e grezze (ma `prob_raw` e' sempre salvato). BASSO.
- S2: `prob` e' lasciata al populator (commento 99-118 coerente con il codice: la dict `prediction` non ha 'prob').
- S3 (build_direzione): la pagella usa TUTTO lo storico settled, incluse le partite ricalibrate: per i `poisson_prob` storici ripopolati dalla calibrazione (fix_storico_prob) la hit rate per fascia e' IN-SAMPLE rispetto alla calibrazione per lega (calibrazione e pagella sullo stesso storico). Non e' leakage per le partite future, ma qualsiasi backtest della pagella sullo stesso storico e' ottimistico. NON VERIFICATO quanto sia forte (richiede ricostruire la calibrazione point-in-time). Soglie: n>=20 globale e n>=10 per lega e' molto basso per una hit rate a 6 fasce (errore standard fino a 0.16 a n=10): il Wilson e lo shrinkage stanno nella RPC `get_direction`, che qui NON ho riletto (il file vigente `get_direction_eta_2026-09-25.sql` contiene solo le funzioni di eta' del dato, non la matematica). BASSO/MEDIO.
- S4 (ventaglio): lo score e' ancorato a MARKET_BASE che coincide quasi con la frequenza marginale dell'evento (HT Over 0.5 0.76, O/U 1.5 0.76, O/U 3.5 0.74): rispondere sempre "Over 1.5" darebbe gia' ~76% in molte leghe (base-rate non verificata qui). L'indice quindi parte alto senza alcun contenuto informativo e A_MAX (>=0.72) si raggiunge per O/U 1.5 e HT Over 0.5 quasi sempre; "benchmark validati point-in-time su 65k partite" non e' verificabile (NON VERIFICATO). MEDIO come indicatore di fiducia; consumatore solo CLI/valida_ventaglio, nessun bot.
- S4 `get_market_delays(p_last_n=None, p_mode='all')` usa lo storico completo: per una partita gia' giocata include la partita stessa (leakage) quando si valida a posteriori. BASSO.
- S5: nessuna matematica.

### 2.7 SQL dei bot (Q1, Q2) e Telegram
- Q1 `trading_daily_history` (vigente 01/10): win/lost per TRADE (originale + chiusure) con status da total_pnl>0/<0/=0 ('scratch'); win_rate=won/(won+lost); profit_factor=gross_profit/gross_loss su trade_tot; `commission_paid` per mercato: se manca `commission_paid` nei meta usa net*c/(1-c) con net=somma dei pnl (NETTI) del mercato nel giorno: coerente (net=gross*(1-c) -> commissione = net*c/(1-c)) SE `pnl` e' netto e `commission` e' un'ALIQUOTA (il codice assume c<1). Esempio: lordo 10 -> net 9.50 -> 9.5*0.05/0.95 = 0.50 (a mano OK). `coalesce(avg(commission),0.05)`: media semplice delle aliquote delle righe, non pesata (BASSO). Gia' D: pnl_realized per op_day vs gross su settled_day (partizione diversa): confermato nel testo SQL (op_settled_day vs settled_day sono lo stesso valore per `p_day_by`, ma `trade_tot` somma i closers ANCHE se regolati in giorni diversi). NON VERIFICATO numericamente.
- Q2 `get_tennis_bot_daily`: vinti/persi contano gli ORDINI, non i trade: per un trade scalper chiuso in green (ordine di ingresso + ordine di chiusura) i due pnl d'ordine hanno segni opposti in un esito, quindi vinti ~ persi indipendentemente dall'andamento. Il numero `vinti/persi` NON e' un win-rate di trade. MEDIO (statistica ingannevole; i soldi `pnl_netto` sono giusti). Da confermare: il significato di `tennis_live_orders.pnl` per ordine (C4 dice per ordine; non riletto). Il giorno usa `tennis_live_follow.open_date` con `LIMIT 1` SENZA ORDER BY: con piu' righe follow per lo stesso event_id il giorno e' non deterministico (BASSO).
- Q2: pnl_stimato usa `o.pnl - o.commission` dove `commission` e' un IMPORTO (paper); in `trading_daily_history` `commission` e' un'aliquota: stesso nome colonna, due unita' diverse fra tabelle (BASSO, rischio di errore nelle query future).
- Non letti: `get_omega_*` aggregati/`storico_sport`/`posizioni_chiuse_giornata`/`live_backtest`/`get_personal_report` rivisti (D) - NON VERIFICATI qui per budget (storico_sport 356 righe, posizioni_chiuse 220 righe, omega_aggregati 51 righe).
- Telegram `calc.ts`: e' un PORT TS di value_engine (stessa tau DC su ogni punteggio, GOAL_CDF letto da array, de-vig moltiplicativo). `price()`: minBack = 1+(1-p)/(p(1-c)) e maxLay=1+(1-p)(1-c)/p sono le quote di pareggio EV=0 con commissione: verificate algebricamente (back: p(b-1)(1-c)=1-p; lay: (1-p)(1-c)=p(L-1)). Le quote vengono da `devigMultiplicative` (lancia se quota<=1) e `devigPair`. In `index.ts:586-591` il bot mostra edge e "Puntata Ottimale: {kelly_stake} EUR" prodotti da `bet_signals` (money_management K1, quindi con il minimo forzato 1.00 EUR di C-R3): quel difetto arriva a un consumatore reale (il Telegram), non solo al foglio. `edge` 0 viene stampato '?' (falsy) e la riga "Edge: +x%" ha SEMPRE il segno +; l'azione 'False' diventa 'No / Under' anche per mercati non under (es. first_half_over_0_5). BASSO.

## 3. Reperti

1. **ALTO - Dutching "variable": anteprima UI e server calcolano due ripartizioni diverse** (DutchingPanel.tsx:194-209 vs trading/dutching.py:184-244, usato da live_order_worker.py:2916-2919). Prova (sonda, quote 2.5/3.0/4.0, pesi 1/2/1, T=100): server stake 40.51/34.18/25.32 profitto +1.26/+2.53/+1.27; anteprima UI stake 30.38/50.63/18.99 profitto -24.05/+51.89/-24.04. Impatto: l'utente conferma (anche in LIVE) guardando stake e profitti che non saranno quelli piazzati; il server e' autoritativo e puo' piazzare stake molto diversi sulle gambe. In equal/target UI e server coincidono. Falsificabile con un test che confronti i due calcoli.
2. **ALTO - Dutching "variable" con lato LAY piazza ordini BACK** (live_order_worker.py:2916-2919: `dmode == "variable"` chiama sempre `dutch_variable` che ritorna side="back"; riga ~2960 `side=plan.side`; DutchingPanel.tsx:380-381 blocca solo target per lay; liveOrders.ts:244-300 non rifiuta variable+lay). Impatto: l'utente sceglie lay (bookmaking) con modo variable, il server piazza BACK con stake=T sulle quote lay mostrate (rischio T invece della liability). Verificato leggendo il codice; NON eseguito (richiede flumine/ordini). Fix minimo: rifiutare mode=variable con side=lay nel worker e nella UI (come target).
3. **MEDIO - `oos_valid=True` hardcoded** (build_analytics_signals.py:298, merge_engine_signals.py:203): il filtro `p_ml_clean` (ml_oos_valid AND ml_reliable) dipende solo da `ml_reliable`; nessun controllo `generated_at < kickoff`. Rischio di previsioni ML post-partita non marcate. NON VERIFICATO sul DB.
4. **MEDIO - Win rate tennis per ORDINE** (tennis_bot_daily_giorno_partita_2026-09-30.sql, `vinti`/`persi`): conta ordini; per trade chiusi in green i due ordini hanno segni opposti. I soldi sono corretti, la statistica no. NON VERIFICATO il segno dei pnl per ordine nella tabella vera (C4 lo dice per ordine).
5. **MEDIO - Dutching "target" e anteprima sono LORDI di commissione**: profitto obiettivo 5.00 -> netto 4.75 (sonda, c=5%); la UI non lo dice (DutchingPanel.tsx:186-193, dutching.py:119-144). BASSO se l'utente lo sa.
6. **MEDIO - Ventaglio: score ancorato alla frequenza marginale** (ventaglio_segnali.py:216-262, MARKET_BASE 0.76 per O/U1.5 e HT Over0.5): tier A_MAX quasi automatico, nessuna misura di lift. Solo CLI. NON VERIFICATA la base-rate.
7. **MEDIO - Kelly K1 con minimo 1.00 forzato raggiunge il Telegram** (index.ts:586-591 mostra `kelly_stake`; C-R3). Vedi C per la matematica.
8. **BASSO - Divergenza tau DC in-play: live_engine_pro (solo 0-0) vs conditional_markets/calc.ts (ovunque)**: scarto massimo 2.1 pp (1-1 al 60': D 49.2% vs 51.3%); nessuna e' dimostrata migliore; non tocca i bot di trading. Da portare all'utente.
9. **BASSO - `estimate_holds(0,0,0,0)` = 0.7917 vive ancora come ripiego** (bot_service.py:5230) gonfiando la P(vittoria) rispetto al prior corretto 0.75 se il modello non risponde.
10. **BASSO - Asimmetria p1 a pareggio** (tennis_opportunity.py:~266, `raw1 >= 0.5`): a 0-0 senza servizio p1 .48 / p2 .52.
11. **BASSO - Commissione colonne con unita' diverse** (trades: aliquota; tennis_live_orders: importo).
12. **BASSO - Cash-out Mike: archived esclusi dalla base commissione** (engine.py:776); NON VERIFICATO l'effetto.
13. **BASSO - `consensus_prob` condizionata** (build_analytics_signals.py:308-313); **BASSO - n minimo 10/20 della pagella**; **BASSO - `LIMIT 1` senza ORDER BY** nel giorno tennis.
14. **BASSO - xhedge: P&L lordo, un solo passo di copertura** (xhedge.py:156-215).
15. **INFO - Cio' che e' CORRETTO (verificato)**: Kelly back/lay (massimo numerico), `_best_split` concava, dutch equal/lay/target lato server, green-up CashOutButton, `price()` Telegram, cashout_value per mercato.

## 4. Miglioramenti proposti

| proposta | guadagno | costo | metrica | rischio | tocca |
|---|---|---|---|---|---|
| P1: far calcolare l'anteprima variable con la stessa formula del server (s_i=(T+k w_i)/p_i) o chiamare il calcolo server in sola anteprima | elimina R1 | piccolo (10 righe TS + test di parita' UI/server) | test: stessi stake a 1 cent per 1000 casi casuali | basso | DutchingPanel.tsx |
| P2: rifiutare `variable`+`lay` (UI e worker) o implementare variable lay | elimina R2 | piccolo | test rosso/verde sul worker | basso | live_order_worker.py, DutchingPanel.tsx, liveOrders.ts |
| P3: `oos_valid = generated_at < kickoff` e confrontare nel populator | sblocca p_ml_clean | piccolo | % righe con oos_valid false su storico | nullo | build_analytics_signals.py, merge_engine_signals.py |
| P4: win-rate tennis per TRADE (raggruppa per trade/coppia) | numero onesto | medio | confronto con vinti/persi attuali | basso | RPC tennis |
| P5: nota "lordo" accanto al target di dutching | evita sorprese | banale | - | nullo | UI |
| P6: ventaglio con lift sul base-rate di lega (hit - base) | indice informativo | medio | AUC/log-loss su storico | nullo | ventaglio_segnali.py |

## 5. Decisioni che spettano all'utente
- Quale convenzione usare per la tau DC in-play (solo 0-0 come Omega/Safe/live_engine_pro o ovunque come value_engine/Telegram): tocca i numeri dei bot se si unifica sul secondo.
- Se il dutching lay in modo variable deve esistere (R2): decide il comportamento atteso.

## 6. Metodo di ricerca
- `git grep -n "def conditional_markets|def residual_grid|def inplay_residual_rates"`, `git grep conditional_markets -- '*.py'` (consumatori: solo value_engine), `git grep dutch_variable|dutch_back_for_target|dutch_lay`, `git grep oos_valid`, `git grep ventaglio_segnali`.
- Letti per estratto: live_engine_pro.py 56-172, 347-444, 477-633; value_engine/bivariate.py 120-215; tennis_opportunity.py 20-160, 205-495; combos.py 120-246, 400-535; dutching.py 1-290; live_order_worker.py 2865-2990; DutchingPanel.tsx 1-30, 160-300; CashOutButton.tsx 33-95; xhedge.py 156-215; mike/engine.py 760-790, 883-896, 962-972, 1030-1127; build_analytics_signals.py 112-316; merge_engine_signals.py 1-30, 120-215; build_direzione.py intero (senza commenti); direzione.py; ventaglio_segnali.py 1-60, 92-120, 185-268; migrations pnl_betfair_reale, tennis_bot_daily_giorno_partita, mike_storico_giorno_regolamento, giornata_di_riferimento_giorno_partita (trading_daily_history), get_direction_eta; Telegram calc.ts 1-219 e index.ts 566-592; bot_service.py 5200-5290.
- NON letti per budget: bot_service.py (11458 righe) oltre le righe 5200-5290 e le righe tennis individuate con grep; tennis_bot_service (stream/tennis_live) non ha funzioni di sizing con `stake|size|liab|stop|target|green` (grep: nessun match matematico); enrich_analytics_snapshots.py (583 righe, solo lista di funzioni: la matematica degli snapshot `Snapshot` vive in un altro modulo non cercato); storico_sport, posizioni_chiuse_giornata, omega_aggregati_servizio_per_modalita, live_backtest SQL; XHedgePanel.tsx/MikeCashOutButton.tsx (solo grep); ReportPersonale.tsx (solo visualizzazione).
- Sonde eseguite oggi: `e2_kelly_tau.py`, `e2_dutch_tennis_combos.py` (output riportati sopra).
