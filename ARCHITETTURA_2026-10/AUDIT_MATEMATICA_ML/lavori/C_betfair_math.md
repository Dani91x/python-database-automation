# C - Componenti matematici Betfair (audit sola lettura, 09/10/2026)

Perimetro: omega, mike, safe_strategy, stream (scanner, scalper calcio, tennis), money_management,
order_exec, order_worker, betfair_report_manager, reject_categories, odds_refresh, tools. Escluso ML/Poisson.
Sonda: `lavori/sonde/sonda_C_betfair_math.py` (sezioni tick, comm, green, sizing, kelly, devig, media), lanciata con
`R/.venv/Scripts/python.exe -I <sonda> <sezione>`. Importa il codice di produzione, nessuna rete/ordine/servizio/scrittura.
Tutte le righe citate sono lette nel codice; cio' che non e' verificato e' marcato NON VERIFICATO.

Esito in breve: la matematica centrale (green-up S*B/L, lay<->liability, P&L back/lay, commissione solo sul netto
positivo PER MERCATO, Kelly al netto di commissione) e' CORRETTA e coincide con i calcoli a mano. Nessun CRITICO,
nessun ALTO sui soldi. Restano divergenze fra copie (tick, arrotondamento della commissione), un caso NaN->1000 nel
percorso REST legacy, e alcune scelte di strategia da portare all'utente.

## 1. Inventario

| id | file:riga | formula | input | output | consumatore |
|----|-----------|---------|-------|--------|-------------|
| T1 | order_exec.py:96-119 | scala `_TICK_BANDS`, `round_to_tick` = min su tick di abs(t-p), clamp [1.01,1000] | prezzo | tick (pareggio -> tick PIU' BASSO) | `place_order` REST (order_exec.py:260) |
| T2 | omega/omega_engine.py:21-85 | `_LADDER`, `_tick_bounds`, `round_to_tick` (<= verso il basso), `tick_up/down`; NaN -> ValueError | prezzo | tick | omega_service (5887), safe execution `_su_tick` (execution.py:2208), misura_* |
| T3 | stream/live_order_build.py:146-163 | `get_nearest_price` di flumine (Decimal ROUND_HALF_UP), `ticks_away` = price_ticks_away dopo snap | prezzo | tick | build_order, mike, scalper, tennis, live_order_worker |
| T4 | stream/trading/risk_engine.py:58-100 | `snap`=flumine, `ticks_between` via indice, `pct_price` | prezzo | tick / n tick | risk engine |
| T5 | scalper_bot.py:278, tennis_scalper_bot.py:147 | `ticks_between` con `max_ticks=200` (None oltre) | p_low,p_high | n tick | scalper calcio/tennis |
| T6 | tennis_swing_bot.py:48-56 | `_LAD` rigenerata a mano (uguale a flumine: verificato 350/350) | prezzo | indice | swing tennis |
| T7 | scalper/habitat_scan.py:27, scalper/tools/mcm.py:20, omega/tools/superficie_liability.py:110-125, misura_*.py | altre copie della scala / `tick_di` / `frac_tick` (ritorna un INDICE, non un prezzo) | prezzo | passo/indice | solo strumenti di misura |
| T8 | media_under_bot.py:572-595 | `tick_sotto`, `tick_sotto_la_media` (snap flumine poi -1 tick) | prezzo | tick | bot media-under |
| G1 | stream/trading/greenup.py:118-260 | diff=W-L; size = round(diff/p, 2); side LAY se W>L; W'=W-size(p-1), L'=L+size | W,L,best back/lay | piano ordine | safe/omega (close_plan execution.py:2228), mike cashout, scalper, UI |
| G2 | safe_strategy/execution.py:1965-2057 | `hedge_state`: hedged = somma size_chiusura*p_chiusura/p_apertura; locked = min(W,L) lordo, netto = locked*(1-c) se >0 | trade+chiusure | stato hedge | safe, omega |
| G3 | omega/omega_v3.py:944-977 | profitto bloccabile lay: sb=s*L/B, lordo=s-sb, netto=lordo*(1-c) se >0 | posizione, B | EUR | omega V3 (uscita) |
| G4 | mike/engine.py:435-501 | `locked_pnl_back`=S(Pe/p-1); `cover_size`=f*S/((q-1)(1-c)); `cover_residual(_lay)` | stake,prezzo,c,f | stake copertura | mike |
| G5 | mike/engine.py:1045-1127 | `cashout_value`: somma min(W',L') per selezione, commissione per MERCATO pro-rata | legs, books | netto cash-out | mike (uscite smart) |
| G6 | media_under_bot.py:469-640 | posizione (se_vince/se_perde), banca esatta L=(sv-sp)/c, rientro esatto, `al_centesimo` (Decimal HALF_UP) | punte/banche | importi | bot media-under |
| C1 | mike/engine.py:1614-1692 | lordo per mercato in centesimi; comm = round(v*c,2); pro-rata sulle gambe in utile; residuo sulla riga piu' pesante | legs | netto per riga/mercato | mike (settlement) |
| C2 | safe_strategy/execution.py:2686-2722 | `settle_group`: net=somma lordi, comm=net*c (NON arrotondata), total=round(net-comm,2), pro-rata, drift sull'ultima | trade+chiusure | pnl netti | safe, omega (`_settle_hedged` omega_service.py:5415) |
| C3 | stream/reconcile_worker.py:747-800 | commissione REALE di listClearedOrders per mercato, ripartita sui profit>0, ultima quota = resto | ordini, gruppi | quota per bet | conto reale, mike/regolato_conto.py |
| C4 | tennis_live/tennis_live_order_worker.py:1256-1280 | paper: max(0,somma P&L)*aliquota, ripartita, round(,2) per quota (senza correzione del resto) | ordini | quota | paper tennis |
| C5 | stream/backtest/run_backtest.py:98-170 e banco_comune.py:1392-1520 | commissione per mercato: `pnl()` somma non arrotondata, totale round; `pnl_betfair()` round per mercato | ordini flumine | netto replay | banco, backtest |
| C6 | omega_engine.py:248-284, 815-843 | `liability_from_lay`=round(size(p-1),2); `net_profit_if_win`=size(1-c); `settle_pnl` (lay/back per singola scommessa) | size,price,c | pnl | omega |
| C7 | safe_strategy/exits.py:193 | `net_of_commission` (solo utili) | valore,c | netto | safe exits |
| C8 | opportunity.py:149-175 | `resolve_commission`: `commission` > `commission_pct`/100 > default 0.05; [0,1) | params | frazione | safe, combos, tennis |
| K1 | money_management.py:765-815 | Kelly back netto: odds_net=(o-1)(1-c)+1; f=(b p - q)/b; stake=min(B f k, B cap) poi max(round,1.0); sqrt(BSS) opzionale | p,odds | stake | track Poisson/ML (foglio Sheets) |
| K2 | stream/engine/live_engine_pro.py:414-440 | `_kelly_back`: f=p-(1-p)/b, b=(o-1)(1-c); `_kelly_lay`: f=(1-p)/(L-1)-p/(1-c) (e' lo STAKE del lay) | p,odds,k,bank | stake suggerito | segnali UI, sim_strategy (315) |
| E1 | live_engine_pro.py:588-600 | EV per 1 EUR di stake: back=p(b-1)(1-c)-(1-p), lay=(1-p)(1-c)-p(L-1) | p,prezzi | edge | segnali |
| E2 | opportunity.py:998-1020, anomaly.py:132-142 | edge lordo p-1/q (back) o 1/q-p (lay) con gate min_edge, poi EV netto (>0 obbligatorio) | p_model,prezzo | opp | safe |
| E3 | betfair_report_manager.py:566-571 | `calc_edge`=p(q-1)(1-c)-(1-p); p=prob/100 se prob>1 | prob,quota | edge | report foglio |
| D1 | omega/omega_model.py:119-129 | devig moltiplicativo 1X2 | 3 quote | 3 P | omega |
| D2 | omega/omega_v3.py:524-553 | mid(1/back,1/lay) normalizzato su tutto il book (>=6 runner, somma>0.5) | runner CS | P(nome) | omega V3 fusione |
| D3 | safe_strategy/anomaly.py:109-119 | devig moltiplicativo dai back validi | runner | P | anomalie safe |
| D4 | money_management.py:109, 596, 837 | `implied = (1/odds)*0.975` (overround fisso) | odds | P | gate ML, hallucination filter |
| S1 | stream/live_order_build.py:166-285, trading/minimi_it.py | min .it: back>=1.00 a multipli di 0.50 PER DIFETTO, lay>=1.00 al centesimo; .com 2.00/payout 20 | side,size | size legale+residuo | tutti i bot (build_order) |
| S2 | omega_engine.py:216-245, 253-262 | `lay_size_from_target`=t/(1-c) con minimo; `apply_liability_cap` floor al centesimo | target,c | size | omega |
| H1 | live_engine_pro.py:188-247 | hazard p=1-exp(-lam_tot*share), CDF empirica dei tempi-gol | minuto,punteggio | p_next | UI, mike |
| H2 | mike/dossier.py:114-123 | `combine_hazard`=max(Atlante, modello*pressione<=1.25) | p,p,mult | p | mike cover_timing |

## 2. Analisi per componente

### 2.1 Scala prezzi e arrotondamento al tick
- La scala di produzione coincide con quella ufficiale (docs Betfair "Price Increments" / CLASSIC ladder: 1.01-2 0.01, 2-3 0.02, 3-4 0.05, 4-6 0.1, 6-10 0.2, 10-20 0.5, 20-30 1, 30-50 2, 50-100 5, 100-1000 10; fuori scala = INVALID_ODDS; https://betfair-developer-docs.atlassian.net/wiki/x/ZCwp). `tennis_swing_bot._LAD == flumine.PRICES_FLOAT` (350/350, sonda sez. 7c).
- DUE regole di pareggio. T3/T4 (flumine `get_nearest_price`, utils.py:150-160) arrotondano ROUND_HALF_UP con Decimal. T1 (order_exec) e T2 (omega) scelgono "il piu' vicino" con float: sul punto medio esatto (solo prezzi FUORI scala) vincono il tick PIU' BASSO, e a volte per rumore float. Sonda (400000 prezzi, passo 0.0025, 1.0..1001): 263 punti divergono da flumine, tutti di 1 tick: 1.015 -> 1.01 vs 1.02; 2.01 -> 2.0 vs 2.02; 10.25 -> 10.0 vs 10.5; 52.5 -> 50 vs 55; oltre 1000 flumine ritorna int 1000, T1/T2 float 1000.0. I prezzi che arrivano dal book sono gia' tick validi (no-op), quindi la divergenza tocca solo prezzi calcolati.
- Casi limite (sonda): 1.01, 1000 e clamp corretti nelle tre famiglie; `omega.round_to_tick(NaN)` -> ValueError (bene), `risk_engine.snap(NaN)` -> ValueError, `live_order_build.round_to_tick(NaN)` -> InvalidOperation (fallisce, bene), MA **`order_exec.round_to_tick(NaN)` -> 1000.0** (vedi reperto R1). `flumine.price_ticks_away` su prezzo fuori scala solleva ValueError (non gestito dalla libreria): il repo lo evita snappando prima (live_order_build.py:153, risk_engine.py:67); `price_ticks_away` oltre i bordi satura a 1.01/1000 senza errore (verificato sonda).
- `ticks_between` ha tre versioni: scalper_bot/tennis_scalper_bot (loop, `max_ticks=200`: 1.01->1000 ritorna None, 1.01->5.0 = 179 ok), risk_engine (indice, 349 senza tetto). Divergono oltre 200 tick (spread/stop molto larghi): None invece del numero.
- `superficie_liability.tick_di`: <1.01 e >=1000 ritornano 10.0 (sbagliato sotto 1.01, irrilevante: solo strumento di misura). `mcm.frac_tick` ritorna l'indice nella scala (2.0 -> 99), non il passo: nome fuorviante. `misura_prezzo_appaiata.tick_giu` usa `_tick_bounds(p*(1-1e-6))`: workaround dichiarato.
- `tick_sotto(1.01,1)` e `tick_sotto_la_media(1.01)` ritornano 1.01 (non c'e' un tick sotto): la docstring dice "STRETTAMENTE sotto", sul bordo non lo e'. Nessun effetto pratico (chiudere a 1.01 su back a 1.01).
- Verdetto: CORRETTO per l'uso reale; da unificare le copie (flumine come unica fonte).

### 2.2 Green-up / hedge (formula S*B/L)
- Formula effettiva: greenup.py:105 `full = round(diff_abs / price, 2)`; con back S@B: W=S(B-1), L=-S, diff=S*B -> size = S*B/L esatta. Sonda: back 10@3.00 chiuso lay@2.80 -> LAY 10.71 (a mano 10.7143), W'/L'=0.72/0.71; back 10@3 lay@3.5 -> 8.57, -1.43/-1.43; lay 10@3 back@3.2 -> 9.38 (9.375), 0.64/0.62; Mike `locked_pnl_back(10,3,2.8)`=0.714286 = a mano; `cover_size(10,4.0,.05,1.2)`=4.2105 = 12/(3*.95); `cover_residual_lay`=12.6316 = 12/.95.
- Coincide con la pratica dei trader (Bet Angel/Geeks Toy: lay stake = back stake * B / L; la colonna "greening" prezzo-per-prezzo di ladder). Eguagliare il P&L LORDO e' giusto anche con commissione: se i due esiti hanno lo stesso lordo P, il netto e' P(1-c) su entrambi (commissione solo sul netto positivo del mercato); sonda: locked 0.71 -> 0.67 netto. Nel calcolo del netto-obiettivo (mike cover_size, omega lay_size_from_target) il fattore 1/(1-c) e' presente dove serve.
- Limite intrinseco: la size e' arrotondata al centesimo, quindi l'errore del P&L e' <= 0.005*(p-1) per esito. A quote basse e' <=1 cent; a quote alte cresce: back 100@1000 chiuso lay@990 -> 101.01 e W'/L' = 1.11/1.01 (10 cent di asimmetria, caso estremo ma valido per costruzione). Con la legalizzazione .it (multiplo di 0.50 per difetto sulle PUNTE) la copertura puo' restare scoperta fino a 0.49 di stake: gestito con "residuo" (decisione utente 04/10, minimi_it.py:46-66, execution.py:2303-2380).
- Casi limite verificati: NaN in W/L -> nessun ordine (greenup.py:172); prezzo lay None/<=1 -> nessun ordine; |diff|<0.01 -> piatta; amount<=0 o non finito -> nessun ordine; target_price fuori (1,1000] -> nessun ordine; back 2@1.01 chiuso a 1.01 -> locked 0.
- `hedge_state` (execution.py:2020-2024): hedged += size_c * p_c / p_apertura: stessa identita' (S_open = size_c*p_c/p_open). Complete se residuo<=0.01 o |win-lose|<0.05: la tolleranza 0.05 EUR e' assoluta e non scala con lo stake (su stake 1000 EUR 5 cent sono trascurabili, su stake 2 EUR sono il 2.5%). BASSO.
- `profitto_bloccabile` omega V3: B=22, lay 2@20 -> sb=1.82, netto 0.1727 (= 0.1818*0.95). `ev_gamba`: 0.703 = a mano.
- Mike `cashout_value`: somma min(W',L') per SELEZIONE e poi commissione sul lordo del MERCATO (engine.py:1086-1109). Per un mercato a due selezioni dove sono aperte sia Over sia Under la somma dei minimi per selezione e' un'approssimazione prudente del minimo del mercato. NON VERIFICATO se coincide col netto realizzabile (richiederebbe un replay; fuori budget).

### 2.3 P&L, liability, commissione
- Lay: liability = round(size*(p-1),2) (omega_engine.py:248); sonda p=1.01 -> 0.10, p=1000 -> 9990.00. `lay_size_from_liability` (live_order_build.py:166) rifiuta price<=1. `settle_pnl` omega: lay perso -20.00, lay vinto +9.50 (10*0.95), back vinto +19.00 (10*2*.95), commissione 1.0 -> 0.0: tutto = a mano.
- Commissione (Betfair): "commissione sulle vincite nette di un mercato, nessuna se il netto e' in perdita", = Net winnings x Market Base Rate (regola citata nel codice stesso, tennis_live_order_worker.py:1259-1262; docs Betfair "What is Commission"). Il default del repo e' 5% ovunque (money_management.py:56, opportunity.py:74, combos.py:46, mike/config.py:78 range [0,20], execution.py:2652, report 564). La ricerca web conferma 5% come base rate tipico per l'Italia (fonti: https://track360.io/it/blog/betting-exchange-italia-guida-operatori-2026; Betfair applica sul netto, nessuna commissione se perdita; il tetto di legge citato e' 10%). L'aliquota REALE del conto (sconti) e' letta da `listClearedOrders.commission` in reconcile_worker (C3): NON VERIFICATO quale aliquota esatta abbia l'utente.
- Il netto per MERCATO e' implementato in modo coerente nelle copie principali (C1, C2, C3, C5) e sui bot a due gambe (omega `_settle_hedged` -> `settle_group`). Divergenza nell'ARROTONDAMENTO (reperto R2): sonda su lordi 0.01..30.00 a passo 1c con 5%:
  - Safe `settle_group` (round(net - net*c, 2)) differisce dal metodo "commissione arrotondata half-up al centesimo" (Decimal ROUND_HALF_UP, la regola che il banco RG1 ha osservato su Betfair: 0.10 lordo -> commissione 0.01, accredito 0.09, engine.py:1668-1672) in 75 casi su 3000 (es. lordo 0.10: Safe 0.10 vs 0.09; 1.10: 1.05 vs 1.04);
  - Mike `round(v*c,2)` (float, half-even sul binario) differisce da half-up in 31 casi su 3000 (es. lordo 0.30: Mike 0.29 vs half-up 0.28; 2.30: 2.19 vs 2.18);
  - Safe e Mike divergono fra loro in 92 lordi su 3000 (es. 0.70: Safe 0.66 / Mike 0.67 quando half-up dice 0.67 ... vedi sonda).
  Ogni scarto e' di 1 centesimo per mercato; la regola esatta di arrotondamento di Betfair e' NON VERIFICATO (un solo caso osservato). Il conto reale (C3) usa direttamente la commissione di Betfair, quindi lo scarto riguarda solo stime/paper/replay.
- `settle_group` e `reconcile` redistribuiscono il resto correttamente (somma esatta); `tennis_live_order_worker._commissioni_per_ordine` (C4) arrotonda ogni quota senza correggere il resto: la somma delle quote puo' differire dalla commissione di 1-2 cent (solo paper).
- Backtest: `order_profit` dice "P&L netto" ma `order.simulated.profit` e' LORDO (flumine applica commission_base solo al dizionario cleared, market.py:252; `# not implemented` in baseclient.py:45). La commissione e' applicata una volta in aggregate_results; assenza di doppio conteggio: OK. Ma `commission_rate` ha default 0.0 in run_backtest.py:98/205/481: se il chiamante non lo passa, total_pnl e' lordo. Il banco comune usa 0.05 (banco_comune.py:656). BASSO.

### 2.4 Stake, minimi, tetti
- Minimi .it nel codice: back >=1.00 a multipli di 0.50 PER DIFETTO (1.24 -> 1.00 residuo 0.24; 7.27 -> 7.00), lay >=1.00 al centesimo, sotto 1.00 non piazzabile (sonda sez. 4b); .com 2.00 o payout 20. La ricerca web riporta per la regolazione italiana del 2014 un minimo di 2.00 EUR; il codice usa 1.00 e il floor di legge 0.50 (minimi_it.py:46-66, "DM 47/2013 art. 8") sulla base di prove vere (AUDIT_2026-10-01/RICERCA_STAKE_MINIMI_BETFAIR.md, rifiuto INVALID_BET_SIZE del 04/10 su 7.27, accettazione di 7.47 dal sito). NON VERIFICATO quale sia la regola attuale di Betfair Italia: i due dati sono in tensione e l'unica prova definitiva e' un ordine vero (vietato qui).
- Effetto di scelta: troncare per difetto riduce stake e copertura fino al 49% nella banda 1.00-1.49 (back); su stake >=7 al massimo ~7%. Decisione gia' presa dall'utente il 04/10.
- `lay_size_from_target` (omega_engine.py:216): size=target/(1-c), arrotondata al centesimo, poi ALZATA al minimo: target 1.00 con min 2.00 -> size 2.00 (a mano 1.05), target 0.10 min 1.00 -> 1.00. L'ingresso supera il target di giornata: e' dichiarato nel codice ("minimo DOPO l'arrotondamento") ma e' una scelta di strategia da conoscere. Con c=1.0 il denominatore e' 1e-6 -> size 5e6 (protetto da clamp di config 0-20% e dal tetto di liability).
- `apply_liability_cap`: floor al centesimo, mai sopra il cap (price 1000, cap 20 -> 0.02, liability 19.98; price 1.01 -> 1999.99, 20.00; price 3.0 size 10.01 -> 10.00). CORRETTO.
- `calculate_kelly_stake` (K1): Kelly al netto di commissione corretto (p=.55, odds 2, c=.05 -> 7.63 su 1000 con k=0.10... ovvero 76.3*0.10; sonda = a mano). Difetto (R3): `stake = max(round(stake,2), 1.0)` DOPO il cap `max_stake_pct`: con bankroll 30 e cap 2% (0.60) lo stake e' 1.00; e poco sopra il pareggio (p=.515, odds 2.0, bankroll 1000, k=.10: Kelly 0.45) lo stake viene portato a 1.00, 2.2x il Kelly frazionato. Con gate `min_edge` 6% a monte il caso e' raro; il consumatore (track Poisson/ML su foglio Sheets) e' legacy: NON VERIFICATO se e' in produzione live oggi.
- Kelly di riferimento: Kelly 1956 (Bell System Technical Journal 35, "A New Interpretation of Information Rate"); Thorp 1969/2006 (frazione di Kelly come riduzione della varianza, "The Kelly Criterion in Blackjack, Sports Betting and the Stock Market"). Frazione 0.10 (K1) e 0.25 (K2 default) sono prudenti e in linea con la pratica (1/4-1/2 Kelly). Con p stimata (modello) la sovrastima e' il rischio dominante: la frazione bassa e' appropriata. `sqrt(BSS)` (K1) e' una scelta euristica, non teoria Kelly.
- `_kelly_lay` ritorna lo STAKE del lay (backer), non la liability: f_stake = f_liab/(L-1); sonda p=.30, L=3, c=.05, bank 100 -> 3.42 (liability reale 6.84). Coerente con `sim_strategy` (usa come size). NON VERIFICATO se la UI lo etichetta come stake o liability (reperto R5).
- Asimmetria dei gate (R6): `min_edge` applicato a EV per 1 EUR di STAKE per entrambi i lati (live_engine_pro.py:588-600, safe opportunity.py:998-1020). Per un lay il rischio per stake e' (L-1): a quota 10 un EV di 0.03 per stake e' 0.33% sul rischio, per un back a quota 2 e' 3% sul rischio. Strategia, non bug.

### 2.5 Devig e probabilita' implicite
- D1/D3: devig moltiplicativo (proporzionale). Esempio 1X2 (1.50, 4.20, 7.00), somma 1/q=1.0476: moltiplicativo [0.63636, 0.22727, 0.13636]; Shin [0.6471, 0.2234, 0.1295]; potenza [0.6519, 0.2199, 0.1283] (calcolati in sonda). Il moltiplicativo sovrastima l'esito lungo di ~5% relativo (7.00: 0.1364 vs 0.1295) e sottostima il favorito: e' il noto favorito-longshot bias (Shin 1991/1993; Strumbelj 2014, "On determining probability forecasts from betting odds", Int. J. Forecasting 30). Consigliato un confronto Shin/potenza come metrica, NON come modifica di strategia.
- D4 (money_management): `OVERROUND_CORRECTION=0.975` fisso (implied = 1/odds * 0.975): ipotizza un overround 2.5% su OGNI mercato; con quote exchange il vero overround dipende dal mercato (back-book tipicamente 1.00-1.03, ma >1.05 su mercati sottili; sonda: 1X2 di esempio 1.0476). Un valore fisso e' una scorciatoia legacy.
- D2 (V3): mid(1/back, 1/lay) normalizzato su tutto il book; si rifiuta se <6 runner o somma<=0.5: scelta corretta per il Correct Score; stessa limitazione moltiplicativa.
- Casi limite: `devig_1x2` quota 0/None/NaN -> None; quota 1.0 -> (0.6,0.2,0.2) (1/1.0=1: valido formalmente); non c'e' controllo che le quote siano >1.

### 2.6 Hazard / intensita'
- `event_goal_hazard`: p=1-exp(-lam_res*share), share=(w_now-w_then)/w_now con orizzonte intero in minuti: formula corretta per un processo di Poisson non omogeneo (CDF dei tempi-gol). Dipende dai lambda del modello (fuori perimetro). `combine_hazard`=max(Atlante, modello*1.25): scelta prudente dichiarata (regola "hazard 3' prudente"). Non rilevate incoerenze matematiche; NON VERIFICATI i valori numerici (richiedono i dati di lega).

### 2.7 Libreria matura e prassi
- flumine `get_nearest_price`/`price_ticks_away` (flumine/utils.py:150, 198) sono usati da T3/T4/T5/T6/T8: e' la fonte da preferire. Il repo non usa `flumine.utils.calculate_matched_exposure`/`calculate_unmatched_exposure` (utils.py:210-229) per il P&L bloccato: ha formule proprie (execution.exposures, tennis compute_green) coerenti fra loro; la parita' con flumine non e' stata testata qui (non richiesto).
- Pratica trader: green-up = back*B/L; hedge parziale = frazione; take-profit "uno tick" = locked(S,B,L) positivo solo se L<B per un back: coerente con green_target e `tick_sotto_la_media`.

## 3. Reperti

1. **MEDIO - `order_exec.round_to_tick(NaN)` ritorna 1000.0** (order_exec.py:115-118: `max(1.01, min(1000.0, float(NaN)))`). Sonda: `OX nan -> 1000.0`. Nel percorso REST legacy (`place_order`, order_exec.py:260) un prezzo NaN diventerebbe un ordine a 1000: un LAY a 1000 si abbina subito al miglior back (e' un ordine a mercato in pratica: il limite del lay e' la quota massima accettata), con liability fino a 999x la size. Omega ha gia' corretto lo stesso difetto (omega_engine.py:50-55, "Certificazione 12/09"). Probabilita' bassa (il prezzo arriva da UI/DB validati), impatto potenzialmente alto: lo marco MEDIO per la bassa probabilita'. Il percorso principale (flumine, live_order_build) NON ha il difetto (solleva InvalidOperation).
2. **BASSO - Arrotondamento della commissione diverso fra copie** (2.3): Safe `round(net-net*c,2)`, Mike `round(v*c,2)` float, banco `pnl()` totale vs `pnl_betfair()` per mercato, media_under `al_centesimo` Decimal half-up, tennis paper senza resto. Sonda: Safe vs half-up 75/3000, Mike vs half-up 31/3000, Safe vs Mike 92/3000, scarto 1 cent per mercato. Impatto: confronti paper/replay/live al centesimo; il conto reale usa la commissione di Betfair. NON VERIFICATA la regola esatta di Betfair.
3. **MEDIO (se live) - Kelly: il minimo forzato a 1.00 EUR supera il tetto `max_stake_pct` e il Kelly** (money_management.py:813-814 `stake = max(round(stake, 2), 1.0)` dopo il cap; stessa riga in `_apply_safety_filters` 874). Sonda: bankroll 30, cap 2% (0.60) -> 1.00. NON VERIFICATO se questo track e' attivo oggi (foglio Sheets legacy).
4. **BASSO - Due regole di pareggio sul tick** (2.1): order_exec/omega vs flumine: 263/400000 punti, 1 tick, solo su prezzi non-scala (punto medio esatto). Unificare su flumine.
5. **BASSO - `_kelly_lay` ritorna lo stake (non la liability)**; etichetta UI NON VERIFICATA. Rischio di lettura errata del suggerimento lay (liability = stake*(L-1)).
6. **MEDIO (strategia, da portare all'utente) - `min_edge` e Kelly per STAKE su back e lay** non confrontabili sul rischio (2.4). Non si modifica: e' strategia.
7. **BASSO - Hedge size al centesimo**: l'asimmetria W'/L' cresce con il prezzo (101.01 lay@990 -> 1.11/1.01). Piu' la legalizzazione .it a 0.50 per difetto. Inerente; gestita da "residuo". Soglie assolute `HEDGE_EPS=0.01` (execution.py:1997) e `abs(win-lose)<0.05` non scalano con lo stake.
8. **BASSO - `ticks_between` triplo, con `max_ticks=200` che ritorna None** (scalper_bot.py:278, tennis_scalper_bot.py:147) mentre risk_engine non ha tetto (349 su 1.01->1000). Solo per distanze >200 tick.
9. **BASSO - Backtest `order_profit` descritto come netto ma lordo; `commission_rate` default 0.0** (run_backtest.py:56-69, 98, 205, 481). Se il chiamante lo omette total_pnl e' lordo.
10. **BASSO - Minimo .it: tensione fra fonti** (web 2.00 EUR 2014 vs codice 1.00/0.50). NON VERIFICATO; richiede prova reale (utente).
11. **BASSO - `lay_size_from_target` alza la size al minimo oltre il target** e con c->1 il denominatore 1e-6 (omega_engine.py:236-245); protezioni a monte.
12. **BASSO - `calc_edge` interpreta `prob>1` come percentuale** (betfair_report_manager.py:568): prob=1 ambiguo (1% vs 100%). Solo report.
13. **BASSO - `OVERROUND_CORRECTION=0.975` fisso** nel gate ML e nel filtro "hallucination" (money_management.py:109, 596, 837): equivale a assumere un margine uniforme; il devig reale cambia per mercato.
14. **INFO - Strumenti**: `superficie_liability.tick_di` (<1.01 -> 10.0), `mcm.frac_tick` (indice), `distanza_tick` approssimata per bande miste: irrilevanti per i soldi.
15. **Nota catalogo §7**: nessuna ricomparsa dei difetti 1-17 nel perimetro matematico letto (chiavi/enum/NaN gestiti in greenup.py, omega `_tick_bounds`, opportunity.resolve_commission, `_commission_fallback` execution.py:2655-2673 che distingue 0 esplicito da assente). Il difetto "zero scritto al posto di assente" (n. 21) e' evitato in `_commission_fallback` e `_net_locked` (default 5% se manca).

## 4. Miglioramenti proposti

| proposta | guadagno | costo | metrica | rischio | tocca |
|---|---|---|---|---|---|
| P1: `order_exec.round_to_tick` -> usa `get_nearest_price` e solleva su NaN/inf | elimina R1 e R4 sul percorso REST | 5 righe + test con NaN | test NaN rosso/verde (falsificazione) | molto basso | order_exec.py |
| P2: una sola funzione tick (live_order_build) importata da omega/safe/risk/scalper; `ticks_between` unico | un solo comportamento al pareggio | medio (importazioni, test di parita' su 400000 prezzi) | sonda sez. tick = 0 divergenze | basso | omega_engine, risk_engine, scalper_bot, tennis_scalper_bot |
| P3: una sola funzione "commissione di mercato" (Decimal HALF_UP sul centesimo, resto sull'ultima gamba) condivisa da Safe/Mike/banco/paper tennis | niente scarti da 1 cent fra paper e replay | medio | sonda sez. comm: 0 divergenze fra copie; confronto con listClearedOrders reale su un campione | basso (solo stime/paper) | execution.py, mike/engine.py, banco_comune.py, tennis worker |
| P4: Kelly: applicare il minimo di 1.00 solo se <= cap, altrimenti stake 0 (non piu' del cap) | rispetta tetto e Kelly | piccolo | test bankroll 30 | tocca STRATEGIA (decisione utente) | money_management.py |
| P5: confronto Shin/potenza vs moltiplicativo come metrica di calibrazione (non cambia i bot) | misura il bias su dati reali | medio | log-loss/CLV su registrazioni | nullo | strumento di misura |
| P6: rinominare/documentare `_kelly_lay` come stake e esporre anche la liability | evita letture errate | piccolo | test UI | basso | live_engine_pro.py, frontend |
| P7: backtest: `commission_rate` default 0.05 e docstring "lordo" | niente P&L lordo scambiato per netto | piccolo | test | basso | run_backtest.py |

## 5. Decisioni che spettano all'utente
- P4 (Kelly: minimo 1.00 vs cap) e la scelta del gate min_edge per stake su back/lay (R6): toccano la strategia, non si cambiano di iniziativa.
- Conferma della regola attuale dei minimi .it (1.00, multipli di 0.50 per difetto): serve una prova reale con ordine vero; qui vietata.
- Se il track Kelly di `money_management` (foglio Sheets) e' ancora operativo in live o solo storico.

## 6. Metodo di ricerca
- `grep -rnE "def .*(tick|round_to_tick|snap|devig|kelly|green|hedge|cashout|hazard|implied|fair|liability|stake)" --include=*.py Betfair` (escluso tests): 4 definizioni di scala/tick di produzione + 7 copie nei tool; `grep -rniE "kelly"` -> 7 file; `grep -rciE "commission|commissione"` per file: letti tutti i file con >=20 occorrenze nel perimetro (execution.py, bot_service.py [solo righe commissione, NON letto per intero], reconcile_worker, media_under_bot, run_backtest, money_management, omega_v3, regolato_conto, banco_comune, tennis_live_order_worker, live_engine_pro, opportunity) e verificati per estratto engine.py (mike), omega_engine, omega_service (sizing e settle), greenup.py, live_order_build.py, minimi_it.py, risk_engine.py.
- Non letti per intero / NON VERIFICATI: safe_strategy/bot_service.py (43 occorrenze), mike/service.py, omega_service.py oltre gli estratti, tennis_opportunity (formule hold/p), combos `_best_split` (ricerca ternaria su funzione concava: la concavita' del min dei saldi netti con commissione per mercato non e' stata dimostrata), order_worker.py/odds_refresh.py/reject_categories.py (nessuna matematica: solo trasporto e categorie), frontend (colonne EV/Kelly).
- Fonti web (3 ricerche): docs Betfair price increments (https://betfair-developer-docs.atlassian.net/wiki/x/ZCwp); commissione Italia 5% (https://track360.io/it/blog/betting-exchange-italia-guida-operatori-2026); Kelly 1956 e Thorp 2006, Shin 1991/1993, Strumbelj 2014 citati da conoscenza bibliografica (NON riaperti online).
- Sonda: `lavori/sonde/sonda_C_betfair_math.py` (sezioni tick, comm, green, sizing, kelly, devig, media); tutti gli output riportati sopra vengono dalle esecuzioni di oggi.
