# 03 - Componenti matematici (consegna 03, audit sola lettura, 09/10/2026)

> Certificato in fase 2 (09/10/2026): correzioni da lavori/fase2/CERT_*.md; le gravita' finali valgono in 05_ERRORI_DI_PROGETTAZIONE.md; dove una frase non e' stata verificata e' marcata NON VERIFICATO.
> I punti modificati portano il suffisso "[cert. fase 2]" (registro: lavori/fase2/APPLICATE_00_03.md).
> I giudizi ALLINEATO/INDIETRO sulle fonti esterne ([RICERCA], [APERTA], FONTE NON APERTA) e le misure su DB non sono stati rifatti in fase 2 (nessuna rete, nessuna SELECT): valgono come dichiarati dal documento.
> Unico ALTO finale: dutching variable+lay (E2-2), CORRETTO in fase 2 il 09/10/2026 (lavori/fase2/FIX_DUTCHING_delegato.md).

R = radice del repo. Documento di COMPILAZIONE (nessun codice di produzione toccato) dai lavori:
C_betfair_math, D_frontend_sql_analytics, E_inventario_completezza, E2_lacune, R_stato_arte (parte EXCHANGE MATH),
M_misure, e dai verdetti finali di H_verifica_avversaria e V2_verifica_avversaria (tutti in `lavori/`).

Regole di lettura:
- **Quando H o V2 hanno cambiato gravita' o smentito, vale il verificatore**: e' scritto esplicitamente
  "gravita' rivista da H" / "gravita' rivista da V2".
- "(sonda X)" = numero ottenuto da una sonda in `lavori/sonde/` (X = nome). "(a mano)" = calcolo a mano, rifatto da me in
  questa compilazione sulla formula letta nel codice; "(a mano, C)" = a mano ma riportato dal delegato.
- Fonti esterne: marcatura di R_stato_arte.md: [APERTA] = pagina letta; [RICERCA] = solo snippet di ricerca;
  FONTE NON APERTA = citazione da memoria, non verificata in rete.
- Cio' che nessun delegato ha verificato e' marcato NON VERIFICATO.
- Le strategie dei bot non si giudicano: dove un reperto tocca una strategia e' scritto "decisione dell'utente".

Sonde citate (tutte in `lavori/sonde/`): `sonda_C_betfair_math.py` (sezioni tick, comm, green, sizing, kelly, devig, media),
`D_sonda_formule.py`, `e2_kelly_tau.py`, `e2_dutch_tennis_combos.py`, `e_probe_tennis.py`, `e_probe_trading.py`,
`v2_dutch.py`, `v2_tennis_tb.py`, `v2_commissione.py`, `v2_calib_slope.py`, `v2_poisson_slope_db.py`,
`h_c.py`, `h_dd.py`, `h_gate.py`, `h_poisson.py`, `h_engine_signals.py`, `m_misure.py`/`m_extra.py`.

---------------------------------------------------------------------------------------------------

## 1. Probabilita' implicite e rimozione del margine (devig)

**Formula e file:riga (copie)**
| copia | file:riga | formula |
|---|---|---|
| D1 omega | Betfair/omega/omega_model.py:119-129 | devig moltiplicativo 1X2: p_i = (1/q_i)/sum(1/q_j) |
| D2 omega V3 | Betfair/omega/omega_v3.py:524-553 | mid(1/back, 1/lay) per runner, normalizzato su tutto il book (>=6 runner, somma>0.5) |
| D3 safe anomalie | Betfair/safe_strategy/anomaly.py:109-119 | moltiplicativo dai back validi |
| D4 money_management | Betfair/money_management.py:109, 596, 837 | `implied = (1/odds)*0.975` (overround fisso 2.5%) |
| tennis | Betfair/safe_strategy/tennis_opportunity.py:140-147 | `devig_pair` i1/(i1+i2) (solo informativo, l'edge usa 1/prezzo grezzo) |
| D32 edge_scorer | market_intelligence/edge_scorer.py:159-190 | proporzionale per gruppo (1x2, o/u 2.5, btts) |
| D33 calibrazione MI | market_intelligence/calibration.py (bias su 1/odd GREZZA) | vedi reperto R2 di D |
| D34 CLV | Betfair/money_management.py:2494-2511 | 1/closing - 1/entry su probabilita' GREZZE (vedi sez. 13) |
| bot Telegram | Telegram bot/.../calc.ts (`devigMultiplicative`, `devigPair`) | moltiplicativo, lancia se quota<=1 |
| generate_dynamic_cal | generate_dynamic_cal.py:191-228 | moltiplicativo poi ri-normalizzato (quote bookmaker API-Football) |

**Esempio numerico (sonda sonda_C_betfair_math.py, sez. devig)**: 1X2 (1.50, 4.20, 7.00), somma 1/q = 1.0476.
Moltiplicativo [0.63636, 0.22727, 0.13636]; Shin [0.6471, 0.2234, 0.1295]; potenza [0.6519, 0.2199, 0.1283]. Il moltiplicativo
sovrastima l'esito lungo (7.00: 0.1364 vs 0.1295, ~5% relativo) e sottostima il favorito. Verifica a mano del moltiplicativo:
(1/1.5)/1.0476 = 0.6667/1.0476 = 0.6364 (coincide).

**Misura su dati reali (NON VERIFICATO in fase 2: misura su DB non rifatta; M, 1519 partite 21/09-07/10, quote "Betfair" Sportsbook di API-Football, NON l'exchange)**: 1X2 logloss
moltiplicativo 0.9592, power 0.9555 (-0.0037 [-0.0064,-0.0009], significativo), Shin 0.9564 (-0.0028 [-0.0046,-0.0010], significativo);
ECE10 0.0321 / 0.0215 / 0.0237. Over 2.5 e BTTS: power e Shin NON migliorano (differenze con IC che include 0; O25 +0.0019/+0.0010,
BTTS +0.0011/+0.0006). Quindi: per 1X2 il moltiplicativo e' il piu' debole dei tre (favourite-longshot bias nelle curve di
affidabilita': [0.7] pred 0.75 osservato 0.87 n=77; [0.0] pred 0.07 osservato 0.02 n=123); per i mercati a due esiti il
moltiplicativo basta.

**Casi limite**: `devig_1x2` quota 0/None/NaN -> None; quota 1.0 -> (0.6,0.2,0.2) formalmente valido (nessun controllo q>1, C 2.5);
D4: overround fisso 2.5% anche dove il vero overround e' 1.0476 (esempio sopra) o >1.05 sui mercati sottili.

**Copie e divergenze**: SI, quattro definizioni di "implicita" nello stesso repo (D 2.9): proporzionale (D1, D3, D32, Telegram),
mid-book normalizzato (D2), grezza 1/odd (D33, D34 CLV), fattore fisso 0.975 (D4). Non sono lo stesso numero.

**Stato dell'arte (R)**: Clarke-Kovalchik-Ingram 2017 (metodi additivo, normalizzazione, Shin) [RICERCA, abstract]; Strumbelj 2014
IJF 30 "On determining probability forecasts from betting odds" (Shin migliora la normalizzazione) [RICERCA, snippet]; penaltyblog
`implied` (power/logaritmico) [RICERCA]; Shin 1991/1993 FONTE NON APERTA; Smith-Paton-Vaughan Williams 2006 (sugli exchange il
favourite-longshot bias e' minore) [RICERCA]. Verdetto di R: **INDIETRO** (solo moltiplicativo), ma sulle quote EXCHANGE il guadagno
pratico e' ridotto; rilevante per le quote bookmaker usate come input Poisson/ML.

**Reperti**: C-13 `OVERROUND_CORRECTION=0.975` fisso (BASSO); D-R2 market_intelligence (vedi sez. 12/13); nessun reperto sulla
correttezza algebrica del moltiplicativo.
**Verdetto: CORRETTO CON LIMITI** (algebra giusta; metodo non allo stato dell'arte per l'1X2).
**Si puo' fare meglio?** SI, come METRICA e per i consumatori che usano quote bookmaker: confrontare power/Shin (C P5, D proposta 5,
M: guadagno logloss ~0.003 su 1X2, nullo su O25/BTTS). Non cambia nessun bot: nessuna decisione strategica richiesta per la sola misura.

---------------------------------------------------------------------------------------------------

## 2. Prezzi equi (fair price) e quote di pareggio

**Formula e file:riga**
- Fair price = 1/p (motore live): Betfair/stream/engine/live_engine_pro.py (fair overlay UI: frontend/src/lib/fairOverlay.ts:47-54, D05).
- Quote di pareggio EV=0 con commissione: Telegram `calc.ts:193-199` `price()`: minBack = 1+(1-p)/(p(1-c)), maxLay = 1+(1-p)(1-c)/p
  (E2-TG: verificate algebricamente: back p(b-1)(1-c)=1-p; lay (1-p)(1-c)=p(L-1)).
- Poisson/ML -> probabilita' servite: catena A/B (fuori da questa consegna, vedi 01 e 02).

**Esempio a mano**: p=0.50, c=0.05: minBack = 1+0.5/(0.5*0.95)=2.0526; maxLay = 1+0.5*0.95/0.5 = 1.95 (a mano; coerente con la
derivazione di E2). Con c=0: 2.0 e 2.0.

**Casi limite**: p=0 o 1 -> divisioni per zero (nel Telegram `devigMultiplicative` lancia per quota<=1; `price()` con p fuori (0,1) NON VERIFICATO).
`decided` (p<=0.03 o >=0.97) tolgono il segnale nel motore live (E2 2.1).

**Qualita' dell'input (l'unico vero limite)**: il prezzo equo e' buono quanto la probabilita'. Misure:
- M: il Poisson calibrato non batte le quote (1X2 RPS 0.2165 vs 0.2008; differenza significativa); su Over 2.5 il ML non batte il tasso base
  (0.6905 vs 0.6886); BTTS: Poisson calibrato ~ quote (0.6799 vs 0.6790), ML peggio della climatologia (0.6955 vs 0.6883).
- V2 A-3 (**BASSO** dopo CERT_1 M3 [V2: CONFERMATO, MEDIO]: pendenza grezza O2.5 misurata 0,44-0,47; la differenza di log-loss grezzo-vs-climatologia (+0,0063, IC [-0,0145; +0,0270]) NON e' significativa; lo scalper legge solo il 1X2 grezzo (`bias_resolver.py:79-92`), dove grezzo e calibrato differiscono di +0,0003 RPS (n.s.); misure V2 replicate fuori campione, [cert. fase 2] sonda v2_calib_slope.py / v2_poisson_slope_db.py): le probabilita' Poisson
  grezze sono "troppo estreme" su O2.5: pendenza di calibrazione 0.533 +- 0.075 sulle 8 celle (n=1490); replica n=500 grezze 0.55 +- 0.125,
  calibrate 0.81 +- 0.185. La calibrazione corregge solo in parte; la causa NON e' provata.
- V2 F-2 (**BASSO/MEDIO, rivisto da V2**): scalper: p_mkt = 1/mid (somma ~1, il "non de-viggato" pesa poco); resta la natura mista
  (Poisson grezzo + ML calibrato) e nessun controllo d'eta' del dato (`prediction()` seleziona created_at/updated_at e non li usa).
  Strategia: da portare all'utente.
- V2 F-1 (**BASSO latente**): `markets_calibrated` con `source="none"` scritto lo stesso (poisson_calibrator.py:86-92;
  today_predictions_backfill.py:944-952); doppio ripiego DB->json, oggi source="db".
- V2 F-3 (**MEDIO, invariato**): lambda tattico o Poisson senza id del modello (stream/db.py:262-285): non si sa quale motore ha prodotto il numero.
- M par. 3: il 10.5% dei Poisson (160/1519) e il 13.2% degli ML (200/1510) hanno `generated_at` DOPO il calcio d'inizio (leghe a orari
  antelucani + batch ~08 UTC); reperto MEDIO, GIA' NOTO (CERT_1 M1): i conteggi 160/1.519 Poisson (10,5%) e 200/1.510 ML (13,2%) con `generated_at` dopo il KO sono stati riprodotti; `oos_valid=True` costante (`build_analytics_signals.py:298`, `merge_engine_signals.py:203`); CRONOSTORIA.md:4888, nessuna modifica per ordine utente 02/10. [cert. fase 2]

**Stato dell'arte (R)**: Strumbelj 2014 e Hubacek-Sourek-Zelezny 2019 [RICERCA]: le quote de-viggate sono la previsione piu' accurata
disponibile; un modello indipendente che non le batte non ha edge medio. Misura interna coerente (M, H A-1 CONFERMATO). Egidi-Pauli-Torelli 2018
[APERTA, arXiv 1802.08848]: usano le quote come prior di un Poisson gerarchico; il nostro Poisson non le usa mai.

**Reperti**: V2 A-3 BASSO (CERT_1 M3); [cert. fase 2] V2 F-3 MEDIO; V2 F-2 BASSO/MEDIO; V2 F-1 BASSO; M previsioni scritte dopo il calcio d'inizio MEDIO (non e' leakage: CRONOSTORIA.md:4888), GIA' NOTO (CERT_1 M1).
**Verdetto: CORRETTO CON LIMITI** (le formule dei prezzi sono giuste; il prezzo equo da modello e' mediamente PEGGIORE di quello di mercato).
**Si puo' fare meglio?** SI: usare le quote de-viggate come benchmark continuo (cruscotto), eventuale miscela quote+Poisson su BTTS
(M: -0.0021 in-sample ma CV +0.0004, NON confermata). Nessun peso modello oltre 0-20% in miscela (M). Decisione dell'utente se tocca un bot.

---------------------------------------------------------------------------------------------------

## 3. Valore atteso / edge

**Formula e file:riga (copie)**
| copia | file:riga | formula |
|---|---|---|
| E1 motore live | Betfair/stream/engine/live_engine_pro.py:588-600 | EV per 1 EUR di STAKE: back p(b-1)(1-c)-(1-p); lay (1-p)(1-c)-p(L-1) |
| E2 safe | Betfair/safe_strategy/opportunity.py:998-1020, anomaly.py:132-142 | edge lordo p-1/q (back) o 1/q-p (lay) con gate min_edge, poi EV netto >0 |
| E3 report | Betfair/betfair_report_manager.py:566-571 | `calc_edge` = p(q-1)(1-c)-(1-p); p=prob/100 se prob>1 |
| tennis N3 | tennis_opportunity.py:414-480 | back p>=0.90, edge=p-1/q>=0.015, EV netto>0; lay p<=0.10, q<=8 |
| UI | frontend/src/lib/fairOverlay.ts:47-54 (D05); valutaProposta.ts:122-135 (E27) | stessa formula E1 (default c=0.05) |
| SQL | direction_report_rpc.sql:143 | pnl direzione (odds-1)(1-c) se hit, -1 altrimenti |
| edge_scorer MI | market_intelligence/edge_scorer.py:316-380 | 0.4*cal_bias + 0.6*(ml_prob-implied)*corr + xG*|rho|*0.10 in PUNTI di probabilita' (soglia 0.02) |

**Esempio numerico**: tutte le copie E1/E2/E3/D05/E27/N3 coincidono per costruzione (C, D, E: "Identica a E1"). Verifica a mano:
p=0.55, quota 2.0, c=0.05: EV = 0.55*1*0.95 - 0.45 = 0.0725 per EUR di stake. (Non e' una sonda: calcolo mio sulla formula del codice.)

**Casi limite**: p>1 interpretata come percentuale in `calc_edge` (prob=1 ambiguo: 1% o 100%) - C-12 BASSO; stesso difetto di lettura in
`netAfterCommission` del CashOutButton (c>1 -> percento, c=1.0 ambiguo con 1%) - E2 2.4 BASSO. c=1: b=0 -> Kelly 0 (live_engine_pro.py:420-422 letto).

**Copie e divergenze**: le formule EV coincidono; DIVERGE l'UNITA' dei gate: min_edge su EV per STAKE sia per back sia per lay
(C-6 / C 2.4 R6, **MEDIO strategia, da portare all'utente**: un EV 0.03 per stake e' 3% sul rischio di un back a 2.0 ma 0.33% sul rischio
di un lay a 10). edge_scorer usa PUNTI di probabilita' (non EV%), quindi non e' confrontabile tra quote (+2 pp ~ EV +3% a quota 1.5, +20% a quota 10; D 2.7).

**Stato dell'arte**: EV netto di commissione sul solo positivo e' la convenzione dei trader (R, commissione sul netto di mercato). Nessun
confronto aggiuntivo in R per l'EV puro. Che l'"edge" Poisson vs quote sia in media errore del modello e' provato (H A-1, M).

**Reperti**: C-6 MEDIO (strategia; non verificato dal verificatore, resta il giudizio di C); D-R2 BASSO (edge MI; CERT_2 M14: Wald con nome Wilson, `significant` mai usato nel punteggio) [cert. fase 2]; C-12 BASSO.
**Verdetto: CORRETTO** (formula EV), **CORRETTO CON LIMITI** (gate non comparabili tra lati; edge MI in punti-probabilita').
**Si puo' fare meglio?** SI (metrica): riportare EV anche per unita' di rischio (liability per i lay). Tocca strategia: decisione dell'utente.

---------------------------------------------------------------------------------------------------

## 4. Kelly, stake, tetti e minimi .it

**Formula e file:riga**
| id | file:riga | formula |
|---|---|---|
| K1 | Betfair/money_management.py:765-815 (riga di floor: 812; stessa nel filtro :874-875) | odds_net=(o-1)(1-c)+1; f=(b p - q)/b; stake=min(B f k, B cap) poi `max(round,1.0)`; sqrt(BSS) opzionale |
| K2 | Betfair/stream/engine/live_engine_pro.py:414-440 | `_kelly_back` f=p-(1-p)/b, b=(o-1)(1-c); `_kelly_lay` f=(1-p)/(L-1)-p/(1-c) = STAKE del lay |
| value_betting | Ai Engine/ai_engine/value_betting.py:219-220 | `kelly_stake=round(kelly*bankroll,2)` senza floor (e' quello che arriva al Telegram: V2 E2-7) |
| S2 omega | Betfair/omega/omega_engine.py:216-262 | `lay_size_from_target`=t/(1-c) poi alzata al minimo; `apply_liability_cap` floor al centesimo |
| S1 build_order | Betfair/stream/live_order_build.py:166-285 + stream/trading/minimi_it.py:45-66 | min .it: back>=1.00 a multipli di 0.50 PER DIFETTO; lay>=1.00 al centesimo; .com 2.00 (COM_MIN_STAKE live_order_build.py:96) |

**Esempi numerici**
- K2 back (sonda e2_kelly_tau.py): p=0.55, o=2, c=0.05, k=1, bank 100 -> 7.6316; a mano: b=0.95, f=(0.95*0.55-0.45)/0.95=0.07632 -> 7.63
  (a mano, ricontrollato). Massimo numerico del log-growth: 7.63.
- K2 lay (sonda e2_kelly_tau.py): p=0.30, L=3, c=0.05 -> stake 3.421, massimo numerico 3.420; a mano 0.7/2-0.3/0.95=0.03421 -> 3.42
  (liability reale 6.84). Per p=0.10 L=10 e p=0.45 L=2.5 Kelly e massimo numerico sono 0 (EV<0).
- K1 (sonda sonda_C_betfair_math.py sez. kelly e h_c.py): bankroll 1000, p=.55 @2.0, k=0.10 -> 7.63, tetto 20 (2%): floor non attivo.
  Bankroll 30, cap 2% (0.60) -> stake 1.00 (floor SUPERA il tetto). p=.515 @2.0 bank 1000: Kelly frazionato 0.45 -> stake 1.00 (2.2x).
- apply_liability_cap (sonda sonda_C_betfair_math.py sez. sizing): price 1000, cap 20 -> size 0.02, liability 19.98; price 1.01 -> 1999.99, 20.00;
  price 3.0 size 10.01 -> 10.00. `lay_size_from_target`: target 1.00 con minimo 2.00 -> 2.00 (a mano 1.05); target 0.10 min 1.00 -> 1.00.

**Casi limite**: odds<=1 -> 0 (K2); b<=0 -> 0 (verificato leggendo 418-422, 432-437); c=1 in K1 -> b=0 -> `kelly_full<=0` -> 0 (letto 800-807);
`lay_size_from_target` con c=1.0: denominatore 1e-6 -> size 5e6, protetto da clamp di config 0-20% e dal tetto di liability (C #11 BASSO);
bankroll piccolo: floor 1.00 > tetto.

**Minimi .it: la divergenza 1.00 vs 2.00 (codice, commenti, UI, documentazione Betfair)**
| dove | valore | note |
|---|---|---|
| `minimi_it.py:46-48` IT_MIN_BACK / IT_MIN_LAY | **1.00** (floor di legge 0.50, passo 0.50 per difetto sulle punte dirette, riga 50-54) | costante canonica; il motore (live_order_build, submin, Mike, scalper, banco) la usa (V2 par. 2). Letta di persona. |
| `live_order_worker.py:393-405` `_min_stake()` env BETFAIR_MIN_STAKE | 2.00 | solo ripiego di `_sub_minimum_floor` |
| `live_order_worker.py:2950` commento "min-stake .it EUR 2" | 2.00 | commento stantio (V2) |
| `risk_engine_worker.py:964` `_AUTOHEDGE_MIN_STAKE_IT` | 2.00 | auto-hedge 1.00-1.99 va su `place_submin` invece di `place` (percorso piu' complesso) |
| `safe_strategy/bot_service.py:239,361,867` `min_stake` | 2.0 (preferenza utente); pavimento vero `execution.ABS_MIN_SIZE=0.01` (execution.py:51) | |
| `omega/omega_config.py:31` | 0.5 (range 0.5-1000) | |
| frontend `XHedgePanel.tsx:40`, `replay/MarketPanel.tsx:35,67,121`, `safestrategy/InvestAction.tsx:34`, `BotParamsSheet.tsx:833` | 2 | la UI avvisa/spegne stake 1.00-1.99 che il motore accetterebbe |
| frontend `omega/ManualPanel.tsx:35` `OMEGA_MIN_STAKE` | back 2, lay 0.5 | diverso sia dalla costante canonica sia da Omega config |
| Betfair developer docs "Betting On Italian Exchange" [APERTA, R] | back **minimo 200 Euro Cents, multipli di 50 cent**; lay: la puntata del back corrispondente almeno 50 cent; vincita potenziale massima 10.000 EUR; back e lay insieme in un placeOrders -> respinto; max 50 istruzioni | la doc ufficiale (2,00, multipli 0,50) e' SMENTITA dal conto: punta 7,47 accettata e abbinata (CRONOSTORIA.md:4790) [cert. fase 2] |
| prove interne (AUDIT_2026-10-01/RICERCA_STAKE_MINIMI_BETFAIR.md, citata da C) | rifiuto INVALID_BET_SIZE del 04/10 su 7.27 (quindi non multiplo di 0.50); accettazione di 7.47 dal sito | dicono che 1.00 funziona; la doc e' SMENTITA dal conto: punta 7,47 accettata e abbinata (CRONOSTORIA.md:4790) |
Verdetto del verificatore (V2): divergenza REALE (sei valori 0.01, 0.5, 1.0, 2.0 + due UI) contro la regola scritta in `minimi_it.py`
("non ridefinire questi numeri altrove"); **BASSO dopo CERT_2 M13** (V2 aveva MEDIO per coerenza, nessuna perdita dimostrata): le costanti a 2,00 di XHedgePanel, MarketPanel, InvestAction, BotParamsSheet e auto-hedge sono piu' alte del motore, quindi prudenti; `ManualPanel.tsx:35` back 2/lay 0.5; unificare i commenti stantii (`live_order_worker.py:2950`) resta igiene. [cert. fase 2]
Il minimo .it e' GIA' MISURATO e deciso (CRONOSTORIA.md:4790-4793: punta 7,47 abbinata, minimi 1,00/1,00, floor di legge 0,50). Il tetto di vincita potenziale 10.000 EUR e' GESTITO (`live_order_build.py:99`, `build_order` :875-886 solleva ValueError, verificato in CERT_5); back+lay nello stesso placeOrders e' impossibile per costruzione (flumine `Market.place_order` apre una Transaction per ordine, `flumine/markets/market.py:84-96`, e `git grep "\.transaction("` nel codice di produzione: 0 occorrenze). Resta da verificare solo la guardia payout sui percorsi diretti di Mike/Omega/scalper (CERT_3 B39). [cert. fase 2]

**Copie e divergenze**
| grandezza | copie | divergono? |
|---|---|---|
| Kelly | K1 (netto, floor 1.00, sqrt(BSS)); K2 (netto, frazione 0.25, nessun floor); value_betting.py:219-220 (Telegram) | SI nel floor e nella frazione; formula netta coincide |
| minimo stake | vedi tabella sopra | SI (6 valori) |

**Reperti (gravita' finale)**
- C-3 / H "C 3": floor 1.00 dopo il cap, **BASSO, gravita' rivista da H** (C diceva MEDIO se live): con la config reale (bankroll 1000, k=0.10, cap 2%)
  il floor NON e' attivo (sonda h_c.py); supera il tetto SOLO con bankroll < 50. Il track e' il "Quant Fund" su Google Sheets (CRONOSTORIA 08/10: "non usato dai bot").
  Effetto collaterale non citato da C: il floor in `_apply_safety_filters:875` riporta a 1.00 le riduzioni dei moltiplicatori BSS/affidabilita' quando lo stake e' piccolo.
- E2-7 / E-7: "il Kelly K1 con minimo 1.00 arriva al Telegram" **SMENTITO da V2**: il Telegram legge `value_betting.py:220`, senza floor. Gli altri difetti del
  Kelly di value_betting: NON esaminati.
- C-5 `_kelly_lay` ritorna lo STAKE e non la liability (BASSO; etichetta UI NON VERIFICATA). Il Telegram mostra "Puntata Ottimale: {kelly_stake}" senza lato.
- C-6 min_edge per stake (MEDIO strategia, vedi sez. 3).
- C-11 `lay_size_from_target` alza la size sopra il target (BASSO, dichiarato nel codice).
- C-10 / V2: minimi .it **BASSO** (CERT_2 M13; V2: MEDIO per coerenza). [cert. fase 2]

**Stato dell'arte (R)**: Kelly 1956 BSTJ 35; Thorp 2006; MacLean-Thorp-Ziemba 2011 (FONTE NON APERTA): frazioni 1/4-1/2 Kelly con p stimata. Frazioni 0.10 (K1) e
0.25 (K2): K2 0.25 e' dentro la forchetta 1/4-1/2, K1 0.10 e' piu' prudente (non allineato, piu' conservativo) [cert. fase 2] (fonte esterna NON VERIFICATA in fase 2); floor forzato **INDIETRO** rispetto alla teoria; `sqrt(BSS)` e' euristica, non Kelly. Hubacek et al. usano Markowitz invece di Kelly puro [RICERCA, NBA].
**Verdetto: CORRETTO CON LIMITI** (Kelly e cap corretti; floor 1.00 oltre il tetto; minimi .it: regola gia' misurata e decisa, CRONOSTORIA.md:4790-4793; costanti UI/commenti a 2,00 piu' prudenti del motore; doc ufficiale smentita dal conto). [cert. fase 2]
**Si puo' fare meglio?** SI: (P4 di C) applicare il minimo solo se <= cap, altrimenti stake 0 - **tocca strategia: decisione dell'utente**;
unificare i minimi in UI/commenti sulla costante canonica (nessuna strategia toccata); la prova reale per fissare 1.00 vs 2.00 e' gia' stata fatta (CRONOSTORIA.md:4790-4793). [cert. fase 2]

---------------------------------------------------------------------------------------------------

## 5. Green-up, hedge, cash-out

**Formula e file:riga (copie)**
| copia | file:riga | formula |
|---|---|---|
| G1 greenup | Betfair/stream/trading/greenup.py:101-111 (riga della size: **109**; C cita :105, citazione stantia) | `full = round(diff_abs/price, 2)`; diff=W-L; LAY se W>L; W'=W-size(p-1), L'=L+size |
| G2 safe hedge_state | safe_strategy/execution.py:1965-2057 | hedged += size_c*p_c/p_open; complete se residuo<=0.01 o abs(win-lose)<0.05 |
| G3 omega V3 | omega/omega_v3.py:944-977 | profitto bloccabile lay: sb=s*L/B, netto=lordo*(1-c) se >0 |
| G4 mike | mike/engine.py:435-501 | `locked_pnl_back`=S(Pe/p-1); `cover_size`=f*S/((q-1)(1-c)); `cover_residual(_lay)` |
| G5 mike cashout_value | mike/engine.py:1045-1127 (commissione non arrotondata a :1101) | somma min(W',L') per MERCATO (una chiave per mercato dal 29/09), commissione per mercato pro-rata |
| G6 media_under | media_under_bot.py:469-640 | `al_centesimo` Decimal HALF_UP, banca esatta L=(sv-sp)/c |
| UI D01/D03 | frontend/src/lib/ladderMath.ts:10-13; eventPnl.ts:20-62 | locked = L + (W-L)/price (LORDO); MTM con best_lay se W>L, best_back se W<L |
| UI D04 | frontend/src/lib/cashOutPartita.ts:1-140 | green-up per (mercato,selezione), commissione per MERCATO, pro-rata, fail-closed |
| UI F3 | frontend CashOutButton.tsx:46-73 | stake=|W-L|/p; netto = pnl*(1-c) se >0 |
| UI F4 / E10 | stream/trading/xhedge.py:156-215 | x*=(m_altri-P(w))/O, un solo back CS sul punteggio peggiore (LORDO, griglia 0..8) |
| E09 hedging | stream/trading/hedging.py:157-377 | equalizzazione a stake netti somma zero (commissione IGNORATA) |
| tier1 UI E25 | frontend/src/lib/opportunities/tier1_quasi.ts:70-137 | `backLayLock`: layStake=S*B/L, gross=S(B-L)/L (verificate a mano da E) |
| tier0_arb D09 | frontend/src/lib/opportunities/tier0_arb.ts:123-127 | hedgeLayStake = S((O-1)(1-c)+1)/(lo-c) (convenzione PER-SCOMMESSA) |
| theta E11 | stream/scalper/theta_bot.py:202-224 | coppia atomica entry BACK / green LAY, `None` se locked<=0 |
| daily_pnl E21 | stream/trading/daily_pnl.py:49-90 | MTM; se prezzi mancanti min(worst_win,worst_lose) + flag degraded (conservativa) |

**Esempi numerici**
- Back 10@3.00 chiuso con lay@2.80 -> LAY 10.71 (a mano 30/2.8=10.7143), W'/L'=0.72/0.71 (sonda sonda_C_betfair_math.py sez. green);
  back 10@3 lay@3.5 -> 8.57, -1.43/-1.43; lay 10@3 back@3.2 -> 9.38 (9.375), 0.64/0.62; Mike `locked_pnl_back(10,3,2.8)`=0.714286;
  `cover_size(10,4.0,.05,1.2)`=4.2105 = 12/(3*.95); `cover_residual_lay`=12.6316 = 12/.95.
- UI ladderMath (sonda D_sonda_formule.py): back 10@3 -> W=+20, L=-10; chiusura lay@2.0: locked = -10+30/2 = +5.00; controllo diretto
  stake lay 15 -> W 20-15=5, L -10+15=5. CashOutButton: W=+10, L=-5, lay@2 -> stake 7.5 -> 2.5/2.5 (a mano, E2).
- Omega V3 `profitto_bloccabile`: B=22, lay 2@20 -> sb=1.82, netto 0.1727 (= 0.1818*0.95).
- Hedge nello STESSO mercato (sonda D_sonda_formule.py): S=100, O=2.2, lo=2.0, c=5%: tier0_arb stake 109.744 -> min(win,lose)=9.256; stake esatto
  S*O/lo = 110.000 -> 9.500 su entrambi (la commissione si cancella). Profitto "garantito" sottostimato di 0.244 EUR su 100 (2.6%): conservativo.
  Verifica a mano: 100*(1.2*0.95+1)/(2-0.05)=214/1.95=109.74.
- Equalize/xhedge (sonda e_probe_trading.py): back 10@3 su 1-0: worst -10, best +20, mean -9.63 (media NON pesata sulle 81 celle).
- Mike cashout_value (E2, a mano): OU45 lordo +10, OU35 lordo -3 -> net=10*0.95-3 = 6.50 (mercati diversi non si compensano).

**Casi limite**: NaN in W/L -> nessun ordine (greenup.py:172); prezzo lay None/<=1 -> nessun ordine; |diff|<0.01 -> piatta; amount<=0 o non finito -> nessun ordine;
target_price fuori (1,1000] -> nessun ordine; back 2@1.01 chiuso a 1.01 -> locked 0 (C 2.2). D01 price<=1 -> ritorna L (fail-safe). Limite intrinseco di arrotondamento
al centesimo: errore <= 0.005*(p-1) per esito; back 100@1000 chiuso lay@990 -> 101.01 e W'/L' = 1.11/1.01 (10 cent di asimmetria, caso estremo valido per costruzione).
Tolleranze ASSOLUTE `HEDGE_EPS=0.01` (execution.py:1919 e :2023) e `abs(win-lose)<0.05`: non scalano con lo stake (2.5% su stake 2 EUR) - C-7 BASSO.
Cash-out Mike: slippage/profondita' NON incluso nel numero mostrato (NON VERIFICATO se `books` porta la size); gambe `archived` escluse dalla base commissione
(engine.py:776; effetto misurato in CERT_3 B35: 5% dell'utile archiviato nello stesso mercato, es. 0,62 EUR su utile 12,5, sempre < 1 EUR) - BASSO. [cert. fase 2]

**Copie e divergenze (tabella)**
| copia | convenzione di commissione | allineata alle altre? |
|---|---|---|
| greenup.py / ladderMath.ts / eventPnl.ts / CashOutButton (formula del lock) | identica S*B/L; ladder/eventPnl LORDI | SI sul lordo (D 2.9) |
| cashOutPartita.ts, Mike cashout_value, G2 hedge_state | NETTO per mercato | SI fra loro; DIVERGE dalle viste lorde per costruzione (5.00 lordo vs 4.75 netto a c=5%) |
| tier0_arb.ts:123 hedgeLayStake | PER-SCOMMESSA | NO: in stesso mercato sottostima del profitto garantito (2.6% nell'esempio); NON VERIFICATO quali detector (:428, :518, :584) usino gambe nello stesso mercato |
| hedging.py / xhedge.py / dutching.py | commissione ignorata (lordo) | quarta convenzione (E-4) |
| UI chiudi-ora: etichetta lordo/netto | NON VERIFICATO quale etichetta mostri la UI nei punti D01/D03 | - |

**Stato dell'arte (R)**: green-up = back*B/L (Bet Angel / Geeks Toy), "greening" prezzo-per-prezzo di ladder; eguagliare il P&L LORDO e' corretto anche con commissione
(il netto e' P(1-c) su entrambi gli esiti). **ALLINEATO**. flumine ha `calculate_matched_exposure/unmatched_exposure` (utils.py:210-229): il repo non le usa
(formule proprie coerenti fra loro; parita' con flumine NON testata).
**Reperti**: C-7 BASSO; D-R8 BASSO/MEDIO (non rivalutato da H/V2); E-4 BASSO; E2-12 BASSO; E2-14 BASSO.
**Verdetto: CORRETTO** (formula del green-up verificata a mano in 6 copie; nessun difetto sui soldi).
**Si puo' fare meglio?** SI, a basso costo: etichetta "lordo/netto" accanto ai due chiudi-ora; hedge stesso mercato con S*O/lo; soglie relative (% dello stake) al posto di 0.01/0.05 assoluti
(ultima: tocca soglie di un bot, decisione dell'utente).

---------------------------------------------------------------------------------------------------

## 6. Dutching (modalita' equal / target / lay / variable)

**Formula e file:riga**
- Server: Betfair/stream/trading/dutching.py: `dutch_back` s_i=T*(1/p_i)/sum(1/p_j) (67-116, side="back" a :113); `dutch_back_for_target` T=target*B/(1-B) (119-144);
  `dutch_lay` P_k=T-l_k*p_k (147-181, side="lay" a :178); `dutch_variable` s_i=(T+k w_i)/p_i, k=T(1-sum(1/p))/sum(w/p) (184-244, **side="back" fisso a :224 e :239**).
- Worker: Betfair/stream/live_order_worker.py:2914-2924 (letto di persona): `if dmode == "variable": ... plan = dutch_variable(triples, total)` senza guardare `side`;
  il ramo `target` rifiuta il lay (riga 2922-2924), `variable` no; `build_order(..., side=plan.side)` (r.~2957, E2/V2).
- UI: frontend DutchingPanel.tsx:194-209 (anteprima: stake_i=T*w_i/sum w, w_i=(1/q_i)*peso utente), `guardBeforeSend` (~236-262) blocca solo lay+target; liveOrders.ts:244-300 `sendDutch` valida solo conteggi/importi.
- Altre copie: tier0_arb.ts (dutching stake_i ~ 1/o_i), combos.py:520-534 (`dutch_back` se book<1).

**Esempi numerici**
- Equal (sonda e_probe_trading.py / E2): quote 2.0/3.5/4.2, T=100: book 102.38%, profitto -2.33 per gamba = T(1/B-1) = -2.325. Quote 2.5/3/4, T=100: profitti 1.70/1.70/1.68
  (a mano: B=0.98333, stake 40.68/33.90/25.42, profitto 40.68*2.5-100=1.70).
- Lay (sonda e_probe_trading.py): book 113.49%, profitto 11.88-11.91 = T(1-1/B)=11.89 (NON VERIFICATO in fase 2: ingressi non indicati, non rifatto). [cert. fase 2]
- Target (sonda e2_dutch_tennis_combos.py): target 5.00 -> totale 295.00, profitto LORDO 5.00, NETTO 4.75 (c=5%) o 4.90 (c=2%). Con book 102% (B>1) rifiuta (total=0, corretto).
- **Variable, anteprima UI vs server** (sonda v2_dutch.py ed e2_dutch_tennis_combos.py, quote 2.5/3.0/4.0, pesi 1/2/1, T=100): UI stake 30.38/50.63/18.99,
  profitti -24.05/+51.89/-24.04; server stake 40.51/34.18/25.32, profitti +1.26/+2.53/+1.27. Stesso totale T=100: cambia la ripartizione e la semantica
  (UI = stake proporzionale a w/p; server = profitto proporzionale a w).

**Reperti del modo variable (gravita' finali)**
1. **ALTO, CONFERMATO da V2 e dal coordinatore; CORRETTO in fase 2 il 09/10/2026** (lavori/fase2/FIX_DUTCHING_delegato.md: il worker rifiuta variable+lay con ValueError, la UI disabilita Variable sul lato Lay; le righe e i fatti citati di seguito descrivono lo stato PRIMA del fix) [cert. fase 2] - modo `variable` con lato LAY piazza ordini BACK (live_order_worker.py:2914-2919 + dutching.py:224,239). V2 ha cercato guardie a valle e NON ne ha trovate
   (liveOrders.ts:244-300, DutchingPanel `guardBeforeSend` ~236-262 e select Modalita' ~380 bloccano solo target+lay; `DutchPlan.actionable` controlla solo legs non vuote e total_stake>0, non `worst_profit<0`).
   Impatto: soldi veri e lato opposto a quello voluto; rischio piazzato = T (non la liability); sui prezzi "lay" mostrati la somma 1/L e' tipicamente >=~1, quindi il dutch BACK equivalente e' in perdita garantita
   (stimata ~T*(1-1/book)). Raggiungibilita' LIVE: `SeguiLive.tsx:814-822` monta `DutchingPanel mode={mode}` con `mode` da `live_now.state.order_mode` (SeguiLive.tsx:194): con runner LIVE l'unica barriera e' la spunta
   "Confermo dutching REALE". Stato di `live_now` oggi **NON VERIFICATO** (righe del 30/09: 4 PAPER, 1 LIVE). Non eseguito (richiede flumine/ordini). Fix minimo: rifiutare variable+lay come target (UI e worker).
2. **MEDIO, gravita' rivista da V2** (E2 lo aveva ALTO; anteprima allineata al server nel fix di fase 2, lavori/fase2/FIX_DUTCHING_delegato.md) [cert. fase 2] - anteprima UI diversa dal server nel modo variable (stato PRIMA del fix): stesso totale T, il server e' il piano coerente; la UI mostra -24 sulle gambe che il server non piazza.
   Per pesi forti con book>100% il server rifiuta (stake negativo) dove la UI mostra un piano. In equal/target UI e server coincidono. L'utente conferma una cosa e ne ottiene un'altra.
3. **BASSO** (E2-5, confermato da V2 sonda) - target e anteprima LORDI di commissione (target 5.00 -> 4.75 netto): non e' scritto in UI.
4. **BASSO** (E2 N5) - `dutch_back` arrotonda gli stake al centesimo: `total_stake` pubblicato puo' superare il richiesto di qualche centesimo (variable: 100.01 per T=100, sonda e2_dutch_tennis_combos.py).

**Casi limite**: book>=100% in target -> total=0; variable con pesi forti -> stake negativo -> rifiuto; quote<=1 NON VERIFICATO per ogni copia; il `lay` ha tetto a esposizione tramite `_check_exposure_guard`
(r.2941-2945, limita importi/esposizione, non coerenza del lato).
**Stato dell'arte**: n.a. in R (nessuna fonte specifica sul dutching: formula algebrica standard). **Verdetto: DIFETTOSO** (il modo variable: un ALTO e un MEDIO, entrambi CORRETTI in fase 2 il 09/10/2026, lavori/fase2/FIX_DUTCHING_delegato.md; equal/lay/target lato server CORRETTI). [cert. fase 2]
**Si puo' fare meglio?** SI: P1 (anteprima = formula server o chiamata al server in sola anteprima, test di parita' a 1 cent su 1000 casi) e P2 (rifiutare variable+lay in UI e worker, o implementare variable-lay), P5 (nota "lordo").
Se il dutching lay in variable deve ESISTERE: decisione dell'utente.

---------------------------------------------------------------------------------------------------

## 7. P&L e commissione

**Formula e file:riga (copie)**
| id | file:riga | cosa fa |
|---|---|---|
| C6 omega | omega/omega_engine.py:248-284, 815-843 | liability=round(size(p-1),2); net_profit_if_win=size(1-c); `settle_pnl` |
| C2 safe `settle_group` | safe_strategy/execution.py:2686-2722 (righe di arrotondamento **2709-2710**, letto) | net=somma lordi; `comm = net*c if net>0`; `total = round(net-comm, 2)` (commissione NON arrotondata); pro-rata sulle gambe in utile; drift sull'ultima |
| C1 mike settlement | mike/engine.py:1614-1692 (calcolo commissione **1653-1655**, letto: `round(max(0.0,v)*float(commission),2)`; netto del mercato 1672) | commissione arrotondata al centesimo per mercato; pro-rata; residuo sulla riga piu' pesante |
| G5 mike cash-out | mike/engine.py:1101 | commissione `v*c` NON arrotondata (stima; il settlement arrotonda): osservazione mia dalla lettura, scarto <= mezzo centesimo per mercato; non misurata |
| C3 reale | stream/reconcile_worker.py:747-800 | commissione REALE di listClearedOrders per mercato, ripartita sui profit>0, ultima quota = resto |
| C4 tennis paper | tennis_live/tennis_live_order_worker.py:1256-1280 | max(0,somma P&L)*aliquota, ripartita, round(,2) per quota (senza correzione del resto) |
| C5 banco/backtest | stream/backtest/run_backtest.py:98-170; banco_comune.py:1392-1520 | `pnl()` somma non arrotondata, totale round; `pnl_betfair()` round per mercato |
| C8 | opportunity.py:149-175 | `resolve_commission`: `commission` > `commission_pct`/100 > default 0.05; [0,1) |
| G6 | media_under_bot.py | Decimal HALF_UP al centesimo |
| SQL D25 | migrations/personal_tracking_manual_entry.sql:57-162 | net/gross back/lay, commissione sul vinto |
| SQL Q1 | migrations/giornata_di_riferimento_giorno_partita_2026-10-01.sql:237-484 | commissione per mercato; se manca `commission_paid`: net*c/(1-c) (a mano: 9.5*0.05/0.95=0.50 OK) |
| SQL Q2 | migrations/tennis_bot_daily_giorno_partita_2026-09-30.sql | `coalesce(pnl_betfair, pnl - commission)` (qui `commission` e' un IMPORTO; in `trading_daily_history` e' un'ALIQUOTA) |

**Esempi numerici (sonda sonda_C_betfair_math.py sez. comm; sonda v2_commissione.py)**
- `settle_pnl` omega: lay perso -20.00, lay vinto +9.50 (10*0.95), back vinto +19.00 (10*2*0.95), commissione 1.0 -> 0.0; `liability_from_lay` p=1.01 -> 0.10, p=1000 -> 9990.00.
- Lordo 0.10, c=5%: commissione esatta 0.005. Safe `round(0.10-0.005,2)` = 0.10 (accredito 0.10); Mike `round(0.005,2)` = 0.01 -> netto 0.09; half-up Decimal -> commissione 0.01, accredito 0.09 (osservato dal banco RG1 su Betfair:
  mike/engine.py:1668-1672). Lordi 0.01..30.00 a passo 1 cent (n=3000): Safe != half-up in 75 casi, Mike != half-up in 31, Safe != Mike in 92 (C; V2 conta 96: differenza dovuta alla costruzione del float).
  Lordi realistici (stake {1,1.5,2,5,7,10,15,25} x quote tick, vincente, n=20000, sonda v2_commissione.py): Safe != half-up nel 12.8% dei mercati, sempre +1 cent a favore del trader, deriva +0.128 cent/mercato (1.3 EUR ogni 1000 mercati);
  attenzione: la formula Safe e' stata REPLICATA da V2, non chiamata `settle_group` (NON RIVERIFICATO con la funzione vera). Paper tennis: su 5000 mercati sintetici la somma delle quote differisce dalla commissione del mercato in 668 casi (13%), scarto max 0.02 EUR.
- Backtest: flumine `order.simulated.profit` e' LORDO (commission_base applicata solo al dizionario cleared, market.py:252; `# not implemented` in baseclient.py:45); la commissione e' applicata una volta in aggregate_results: nessun doppio conteggio.

**Casi limite**: commissione 0: net = gross (tutte le copie; `omega commissione 1.0 -> 0.0` e' il caso di settle_pnl con c=1.0 letto come aliquota piena? la sonda riporta "commissione 1.0 -> 0.0" come pnl 0.0 di una scommessa a lordo zero: NON ulteriormente indagato);
commissione piena c=1.0: Kelly 0 (K1/K2), `lay_size_from_target` denominatore 1e-6 (sez. 4), `netAfterCommission` accetta 0.05 o 5 e legge c>1 come percento (c=1.0 ambiguo con 1%; E2 2.4);
perdita netta del mercato: commissione zero (tutte le copie "solo sul netto positivo PER MERCATO"); `run_backtest` `commission_rate` default 0.0 (run_backtest.py:98/205/481) -> total_pnl LORDO se non passato (banco usa 0.05, banco_comune.py:656; C-9 BASSO).
`_commission_fallback` (execution.py:2655-2673) distingue 0 esplicito da assente (catalogo difetto 21 evitato).
Arrotondamento half-even vs half-up: Python `round()` e' half-even sul valore binario esatto (Safe, Mike); Decimal ROUND_HALF_UP e' di media_under, minimi/submin e flumine `get_nearest_price`; regola esatta di Betfair NON VERIFICATA (un solo caso osservato).

**Copie e divergenze**: SI sull'ARROTONDAMENTO (5 convenzioni nel perimetro bot + 1 nello SQL tennis + 1 nel backtest): Safe (arrotonda il netto), Mike (arrotonda la commissione, float), banco `pnl()` vs `pnl_betfair()`, media_under (Decimal half-up), tennis paper (quota per quota, senza resto);
il conto reale (C3) usa direttamente la commissione di Betfair, quindi lo scarto riguarda solo stime/paper/replay. Unita' diverse nelle colonne `commission` (aliquota vs importo; E2-11 BASSO). L'aliquota reale dell'utente e' NON VERIFICATA.
**Aliquota default**: 5% ovunque (money_management.py:56, opportunity.py:74, combos.py:46, mike/config.py:78, execution.py:2652, report 564); fonte secondaria track360 5%, altra fonte 4.5% (R: non risolvibile con fonti aperte; la doc developer italiana NON specifica la commissione).
**Stato dell'arte (R)**: commissione sul netto del mercato (Market Base Rate), nessuna sul netto in perdita: **ALLINEATO** sul metodo.
**Reperti**: C-2 / C4: **BASSO, CONFERMATO e quantificato da V2**; D-R8 BASSO/MEDIO; C-9 BASSO; E2-11 BASSO; E-4 BASSO.
**Verdetto: CORRETTO CON LIMITI** (nessun errore sui soldi reali; scarti di 1 centesimo fra stime/paper/replay).
**Si puo' fare meglio?** SI: P3 (una sola funzione "commissione di mercato" Decimal HALF_UP + resto sull'ultima gamba, test di parita' con listClearedOrders su un campione); P7 (default 0.05 nel backtest).

---------------------------------------------------------------------------------------------------

## 8. Scala dei prezzi e tick (round_to_tick)

**Formula e file:riga (copie)**
| copia | file:riga | regola di pareggio | NaN |
|---|---|---|---|
| T1 order_exec (REST legacy) | Betfair/order_exec.py:95-119 (letto: `_TICK_BANDS` 95-99; `round_to_tick` 115-118 = `max(1.01, min(1000.0, float(price)))` poi `min(_TICKS, key=abs)`) | piu' vicino con float; sul punto medio vince il tick PIU' BASSO (per rumore float a volte) | **NaN -> 1000.0** (sonda sonda_C_betfair_math.py sez. tick: `OX nan -> 1000.0`) |
| T2 omega | omega/omega_engine.py:21-85 | `round_to_tick` <= verso il basso | ValueError (corretto, "Certificazione 12/09") |
| T3 live_order_build / flumine | stream/live_order_build.py:146-163; flumine utils.py:150-160 | Decimal ROUND_HALF_UP | InvalidOperation (fallisce) |
| T4 risk_engine | stream/trading/risk_engine.py:58-100 | `snap`=flumine; `ticks_between` via indice | ValueError |
| T5 scalper/tennis_scalper | scalper_bot.py:278, tennis_scalper_bot.py:147 | `ticks_between` con `max_ticks=200` (None oltre) | - |
| T6 tennis_swing | tennis_swing_bot.py:48-56 | `_LAD` == flumine PRICES_FLOAT (350/350, sonda sez. 7c) | - |
| T8 media_under | media_under_bot.py:572-595 | `tick_sotto` snap flumine poi -1 tick | - |
| D08 frontend | frontend/src/lib/riskMath.ts:13-92 | bande, nearestTick | NON VERIFICATO |
| tier2/matching UI | frontend lib/matching.ts, ladderBacktest.ts | coerente con scala flumine (NON provato; E28) | - |
| strumenti T7 | habitat_scan.py:27, mcm.py:20, superficie_liability.py:110-125 | `tick_di`, `frac_tick` (ritorna un INDICE, non un prezzo) | solo misura |

**Esempi numerici (sonda sonda_C_betfair_math.py sez. tick, 400000 prezzi passo 0.0025, 1.0..1001)**: 263 punti divergono da flumine, tutti di 1 tick, solo su prezzi FUORI scala (punto medio esatto):
1.015 -> 1.01 vs 1.02; 2.01 -> 2.0 vs 2.02; 10.25 -> 10.0 vs 10.5; 52.5 -> 50 vs 55; oltre 1000 flumine ritorna int 1000, T1/T2 float 1000.0. I prezzi dal book sono gia' tick validi (no-op).
Scala ufficiale CLASSIC (R, URL Betfair developer docs "Price Increments" [RICERCA: tabella nel risultato; WebFetch ha dato pagina VUOTA, quindi NON aperta]): 1.01-2 0.01, 2-3 0.02, 3-4 0.05, 4-6 0.1, 6-10 0.2, 10-20 0.5, 20-30 1, 30-50 2, 50-100 5, 100-1000 10; la tabella T1 (letta di persona) coincide.

**Casi limite**: 1.01, 1000 e clamp corretti nelle tre famiglie (sonda); `flumine.price_ticks_away` su prezzo fuori scala solleva ValueError (il repo snappa prima: live_order_build.py:153, risk_engine.py:67); `ticks_between` ha 3 versioni: scalper/tennis_scalper (`max_ticks=200`: 1.01->1000 ritorna None, 1.01->5.0 = 179 ok), risk_engine (indice, 349 senza tetto);
`tick_sotto(1.01,1)` e `tick_sotto_la_media(1.01)` ritornano 1.01 (docstring "STRETTAMENTE sotto" non vera sul bordo; nessun effetto pratico); `superficie_liability.tick_di`: <1.01 e >=1000 -> 10.0 (solo misura).
Ladder FINEST/LINE_RANGE: **NON VERIFICATO** che il codice li gestisca (non coperti da C; R lo segnala).
**Reperto NaN->1000 (gravita' rivista da H)**: C-1 lo dava **MEDIO**; H lo porta a BASSO-MEDIO e CERT_2 B1 a **BASSO** (percorso REST manuale, nessun bot, JSON standard non ammette NaN) [cert. fase 2]: il percorso e' `place_order` REST, raggiunto da `order_worker.py:96-98` (`float(r["price"])`) e `stream/odds_http.py:155-185` (`_opt_float` accetta "NaN"; il json di Python accetta il letterale NaN);
sonda h_c.py: `round_to_tick(nan)=1000.0`, `inf=1000.0`; `min_stake_rules(lay,1000,2.0).valid=True`, nessun altro guard sul prezzo in `place_order` (:260-340). Un browser non puo' mandare NaN (JSON.stringify -> null -> 400 "price mancante"): serve un client non-browser o una riga corrotta.
Percorso = ordini MANUALI dell'utente (Invia Giocate / coda UI), non i bot (flumine/live_order_build non hanno il difetto: affermato da C, non riletto da H). Un LAY a 1000 ha liability size*999. Fix a una riga, costo minimo: va fatto comunque.
**Copie**: DIVERGONO in 3 punti (pareggio, NaN, `ticks_between` con/senza tetto); sui prezzi del book non c'e' differenza. C-4 BASSO.
**Stato dell'arte**: **ALLINEATO** per CLASSIC; la libreria matura e' flumine `get_nearest_price`/`price_ticks_away` (utils.py:150,198), gia' usata da T3-T6/T8.
**Verdetto: CORRETTO CON LIMITI** (uso reale corretto; un ramo legacy con NaN->1000).
**Si puo' fare meglio?** SI: P1 (`order_exec.round_to_tick` su `get_nearest_price`, solleva su NaN/inf; test rosso/verde) e P2 (una sola funzione tick, test di parita' su 400000 prezzi). Nessuna strategia toccata.

---------------------------------------------------------------------------------------------------

## 9. xG, Elo e rating

Nota: l'xG e l'Elo sono componenti di CATENA Poisson/ML (consegne 01 e 02); qui solo come componenti matematici e per quanto riportato dai lavori C-D-E-H-V2.
**Elo (B M3)**: Ai Engine/ai_engine/elo_ratings.py:62-78 (letto da V2): exp_h = 1/(1+10^((a-h)/400)) senza offset casa, risultato 1/0.5/0, nessun margine di gol, K=56 (prime 10 partite) poi 32, squadre nuove a 1500; usato SOLO come feature
(`feature_pipeline.py:833-845`, `elo_diff`, merge_asof backward senza match esatto) dentro un modello che ha gia' le feature casa/trasferta (il vantaggio campo e' assorbito dal modello).
**Reperto B R9**: **BASSO, gravita' rivista da V2** (B lo dava MEDIO): e' una feature, non una probabilita'; l'effetto di un Elo migliore e' una possibile guadagno di feature, non un errore.
**Stato dell'arte (R)**: Hvattum-Arntzen 2010 (IJF 26; Elo con vantaggio casa e margine di gol; citata da B_ml, NON in R); Constantinou-Fenton 2013 pi-ratings (JQAS) [RICERCA]: "outperform considerably" Elo, profittevoli contro le quote su 5 stagioni EPL;
Berrar-Lopes-Dubitzky 2019 [RICERCA]: feature/rating di dominio contano piu' del classificatore. Verdetto R: **INDIETRO**.
**Rating nel motore hazard (E12, E14, E15, E16, E17; letti da E, formule giuste)**: atlante_v4.py:296-322 `lambda_da_forza` (lh = mu_h*exp(att_h+dif_a), rientro 0.7 a cambio stagione, squadra mai vista -> 0);
validazione_hazard/forza.py:22-50 `lambda_prepartita` (gradiente della loglik Poisson con eta=0.05, mu += 0.01*(gol-mu)); K empirical-Bayes (candidati.py:102-156) per cella con tau2>0 e mediana. **Giusti**; `assembla_v4` e `consulta_atlante_v4`, `genera_atlante.assembla`: **NON VERIFICATO** (E13, E18).
**xG**: nessun lavoro C-H-V2 lo valuta come formula a se': in Poisson e' blend gol/xG eta=0.6 (A_poisson, r.1565-1590, citato da A: non rivalutato qui); in market_intelligence `edge_scorer.py` il boost xG e' ±|spearman_r|*0.10 (D 2.7: un coefficiente di correlazione di rango usato come ampiezza di probabilita', euristica senza fondamento statistico; **non rivalutato da H/V2**); nel ML 0 occorrenze di xG nelle feature (B: grep `injur|lineup|xg|rest_days` = 0).
**Copie e divergenze**: due motori di forza/rating indipendenti (Elo nel ML, rating online Poisson nell'atlante hazard) e rho/lambda in Poisson principale vs tattico: nessuna confronto fra loro e' stato fatto da C-H-V2.
**Verdetto: CORRETTO CON LIMITI** (Elo minimale ma innocuo; rating hazard formalmente corretti; euristica xG in MI non fondata).
**Si puo' fare meglio?** SI (B P6): Elo v2 con vantaggio casa (~+60-100 punti), margine di gol, regressione a inizio stagione, K tarato walk-forward; xG come feature ML (dati gia' scaricati); pi-ratings (costo alto, guadagno non quantificato da fonte aperta). Nessun bot toccato.

---------------------------------------------------------------------------------------------------

## 10. Statistiche live, hazard e intensita'

**Formula e file:riga**
- H1 `event_goal_hazard`: Betfair/stream/engine/live_engine_pro.py:188-247: p = 1-exp(-lam_res*share), share=(w_now-w_then)/w_now (CDF empirica dei tempi-gol, processo di Poisson non omogeneo).
- H2 `combine_hazard`: mike/dossier.py:114-123: max(Atlante, modello*pressione<=1.25) (regola "hazard 3' prudente").
- Atlante hazard v3/v4: hazard_atlas.py:271-372 `consulta_atlante` (E17): mult = 0.5*(fa_att*fb_def + fb_att*fa_def), p = 1-(1-p_cella)^mult (spazio hazard / PH, fail-closed p=None); atlante_v4.py:609-622 `_p_recupero2` (E13): P = 1 - E[exp(-r*min(k,D-j)) | D>j].
- `effective_rho` live (T1 di E2): live_engine_pro.py:58-83: DC solo a 0-0, solo se tau>0; `conditional_markets`: value_engine/bivariate.py:167-181 e port TS calc.ts:165-176: tau su griglia dei gol RIMANENTI a qualunque punteggio.
- Tennis in-play: vedi sez. 11.

**Esempio numerico (divergenza tau DC in-play, sonda e2_kelly_tau.py; lambda pre-match 1.5/1.2, rho -0.13; prima cifra live_engine_pro, seconda conditional_markets)**:
0-0 30': D .3608/.3608; 1-0 60': H .7808/.7913, D .1794/.1689; 1-1 60': H .2887/.2781, D .4920/.5132, O2.5 .5934/.5829; 0-1 70': D .1912/.1848; 2-1 75': H .8554/.8595.
Scarto massimo 2.1 pp (pareggio a 1-1: 49.2% vs 51.3%); per un back del pareggio a 2.1 (q 47.6%) l'edge resta positivo (+1,6 contro +3,7 punti); cambia l'eventuale superamento della soglia min_edge [cert. fase 2]: il motore live e' il piu' prudente.
Consumatori di `conditional_markets`: solo value_engine e il port TS del Telegram, NON i bot di trading. Nessuna delle due convenzioni e' dimostrata migliore. **BASSO** (E2-8, non rivalutato da H/V2); **decisione dell'utente** se unificare.

**Casi limite**: `decided` p<=0.03 o >=0.97 -> nessun segnale; calibrazione live `_CALIBRATION_ENABLED=False` (riga 114): identita'; hazard con w_now=0 -> NON VERIFICATO (non letto); valori numerici dell'atlante (richiedono dati di lega) **NON VERIFICATI** (C 2.6).
**Copie e divergenze**: SI (tau DC in-play: 0-0 vs ovunque; sopra). L'hazard prudente `max(Atlante, modello*1.25)` e' una scelta di strategia dichiarata: non si giudica.
**Stato dell'arte (R)**: Boshnakov-Kharrat-McHale 2017 (IJF 33, conteggio Weibull, hazard non costante) [RICERCA]: **INDIETRO** (Poisson puro; dispersione di Pearson misurata 1.142 da A); Koopman-Lit 2015 (state-space) [RICERCA]: INDIETRO, costo alto. Karlis-Ntzoufras 2003: assente (FONTE NON APERTA). Impatto atteso modesto.
**Verdetto: CORRETTO** (formule hazard coerenti; processo di Poisson non omogeneo), con limiti di valori non verificati.
**Si puo' fare meglio?** SI ma basso priorita': sovradispersione/Weibull per linee alte O3.5+ dopo il cruscotto di misura (R). Nessun bot toccato senza decisione.

---------------------------------------------------------------------------------------------------

## 11. Tennis (tennis_winprob, tennis_opportunity)

**Formula e file:riga**
- `p_set` (Betfair/stream/tennis_scalper/tennis_winprob.py:21-47, letto di persona): ricorsione sul game, `ha*P(hold)+(1-ha)*P(break)`; a 6-6 ritorna `p_tb` (default **0.5**, righe 36-37).
- `p_match` (:51-66): `ps*P(win_next)+(1-ps)*P(lose_next)`; chiama `p_set(...)` SENZA `p_tb` (riga 60) e ogni set nuovo ricomincia con `a_serves=True` (righe 64-65).
- `estimate_holds` (:69-84): ha = w*(1-breaks/serves)+(1-w)*prior, w=min(1,serves/6), clamp [0.5,0.95].
- `hold_from_serve_point` (tennis_opportunity.py:126-137): P(hold)=p^4(1+4q+10q^2)+20p^3q^3*p^2/(p^2+q^2) (E: formula chiusa verificata); clamp [0.5,0.98] a :239-241.
- `_retire_risk`/`_p_raw_p1` (:244-275): adj = raw -/+ retire_risk (2% bo3, 3% bo5), leader perde rr, chi insegue guadagna rr. Gate N3 (:414-480): back p>=0.90, edge>=0.015, EV netto>0; lay p<=0.10, q<=8.
- Ripiego `bot_service.py:5230-5233`: `estimate_holds(0,0,0,0)`.

**Esempi numerici**
- `hold_from_serve_point(0.65)` = 0.8296 (sonda e2_dutch_tennis_combos.py, formula chiusa standard). `_holds` prior 0.75; `estimate_holds(0,0,0,0)` = (0.7917, 0.7917) (sonda e_probe_tennis.py) invece del prior 0.75.
- Sonda e2_dutch_tennis_combos.py p_win: 1 set + 3-1, hold .75 -> raw .9039, adj (ritiro 2%) .8839 < .90: nessun segnale; 1 set + 4-2 -> raw .9238, adj .9038 -> segnale possibile. Ripiego: 0.9311 vs 0.9038 a 1 set + 4-2 (misura dichiarata nel codice; 0,9311 e' senza rischio ritiro: la sola differenza dovuta agli hold e' 0,9311 contro 0,9238 raw, +0,73 punti; i restanti 2 punti sono il ritiro: bot_service.py:5224). [cert. fase 2]
- **Tie-break fisso 0.5 (sonda v2_tennis_tb.py, hold A=0.85, B=0.65)**: P(punto al servizio) A=0.6627, B=0.5614 (inversione di `hold_from_serve_point`); P(A vince il TB a 7 punti)=0.6610 contro 0.5 di produzione. P(A vince match) bo3 al 6-6 del primo set: produzione 0.7847, tie-break modellato 0.8568 (+7.2 pp) (NON VERIFICATO in fase 2: richiede il modello di servizio della sonda V2, non rifatto) [cert. fase 2];
  bo3 A avanti di un set e 6-6: 0.8923 -> 0.9344 (+4.2 pp); da 0-0: 0.8809 -> 0.9022; bo5 da 0-0: 0.9297 -> 0.9470. Sonda e_probe_tennis.py: `p_set(6,6,True,.9,.6)=0.5`.
- Gate Safe tennis (griglia di tutti gli stati set/game: 312 in bo3, 702 in bo5, x 7 coppie di hold, sonda v2_tennis_tb.py): il gate .90 cambia verso in 2-47 stati per coppia; nella maggior parte il modello corretto e' PIU' ALTO (la produzione e' prudente);
  1-4 stati per coppia vanno in direzione NON prudente (produzione >=0.90, modello <0.90: es. hold .85 vs .80, B avanti 6-5 al secondo set: 0.9000 vs 0.8901).
- Asimmetria a 0-0 senza servizio (sonda e2_dutch_tennis_combos.py): raw=0.50 -> `raw1 >= 0.5` vero -> adj p1=.48, p2=.52; soglie .90/.10 non raggiungibili da .48/.52: irrilevante sui soldi.

**Casi limite**: hold uguali -> la differenza dovuta al tie-break e' 0.0000 su tutti gli stati (sonda v2_tennis_tb.py): **oggi l'effetto e' ZERO** perche' `tennis_serve_data.get_serve_prob` legge `Betfair/stream/tennis_scalper/serve_data.csv` che NON esiste (V2: ls vuoto, `git ls-files` non lo contiene) e il ripiego usa hold simmetrici.
Senza dati `_holds` (tennis_opportunity.py:236-243) usa lo stesso prior 0.75 per i due giocatori. Ritiro: modello prudente "perdita totale" (l'evento "si ritira chi insegue" e' trascurato, dichiarato nel docstring). Costruzione `_probs` e gate (262-521): **NON VERIFICATO** (E05).
**Copie**: `devig_pair` (tennis_opportunity.py:140-147) = proporzionale; EV N3 = E1. Nessuna copia SQL/UI della formula di P(set) trovata.
**Reperti (gravita' finale)**
- E-1 tie-break fisso 0.5: **BASSO, LATENTE oggi (MEDIO se si popola serve_data.csv o un chiamante passa hold asimmetrici), gravita' rivista da V2** (E lo dava MEDIO). Direzione: prudente per i back, NON prudente per lay/uscite del leader. Toccarlo = strategia: decisione dell'utente.
- E-2 servizio del set successivo fisso ad A: BASSO (non rivalutato da V2; con hold simmetrici nessun effetto).
- E-3 ripiego `estimate_holds(0,0,0,0)` = 0.7917: BASSO (ramo di emergenza se `_p_tennis_dal_modello` ritorna None); stesso difetto gia' corretto altrove; da portare all'utente.
- E2-10 asimmetria p1 a pareggio: BASSO.
- E2-4 win rate tennis per ORDINE (SQL `get_tennis_bot_daily`, migrations/tennis_bot_daily_giorno_partita_2026-09-30.sql:55-60): **BASSO, gravita' rivista da V2** (E2 lo dava MEDIO): confermato per lettura SQL; i soldi sono giusti, e' solo statistica; il segno dei pnl per ordine nella tabella vera NON verificato (0 SELECT).
**Stato dell'arte**: nessuna fonte in R sul modello di Markov del tennis (**FONTE NON APERTA / non cercata**); la formula chiusa dell'hold e la ricorsione sono lo standard (Klaassen-Magnus: NON in R, non citato). **Verdetto: CORRETTO CON LIMITI** (formule giuste; semplificazioni del tie-break e del servizio; ripiego difettoso; effetto oggi nullo).
**Si puo' fare meglio?** SI (E-1/E-2/E-3): tie-break dedotto dagli hold + alternanza del servizio; ricertificare sul banco tennis dopo ogni modifica (Safe tennis e' CERTIFICATO sul banco il 09/10: CRONOSTORIA.md:5609-5618, 18/18 OK, 0 violazioni, codice `25cab047`; l'audit non ha lanciato replay). [cert. fase 2] Tocca una strategia: decisione dell'utente.

---------------------------------------------------------------------------------------------------

## 12. Soglie

Le soglie sono parametri di strategia: qui si verifica solo che siano coerenti con la matematica (unita', scala), NON si giudica il valore.
| soglia | file:riga | come e' costruita | osservazione verificata |
|---|---|---|---|
| gate BSS `MIN_BSS=0.12`, blocco <0.05, moltiplicatore 1.0 se >=0.12 | Ai Engine/ai_engine/confidence_gate.py:36,170-215; predict_fixture.py:1030-1040; money_management.py:629-657 | BSS con baseline UNIFORME brier_random=(n-1)/n | **B R1: MEDIO** (CERT_1 MA1: traccia ML = foglio Quant Fund, non bot; era MEDIO-ALTO CONFERMATO da H) [cert. fase 2] con impatto soldi ridotto: un forecaster "tasso base esatto" q=0.74 passa (Brier 0.385, BSS_unif +0.23, `passed=True`; sonda h_gate.py); MC holdout n=110: P(passa) 91% a q=0.74, 71% a q=0.70/0.30; per 1x2 il gate e' davvero selettivo (climatologia = BSS +0.03). Percorso vivo SOLO come "Quant Fund" su Sheets ("non usato dai bot"); il flag `targets_not_reliable` e' pero' consumato come "affidabilita'" da UI/JSON: li' il gate inganna. R: baseline climatologica e' la pratica standard (Wilks 2011, FONTE NON APERTA): INDIETRO. Tocca lo stake: decisione dell'utente |
| min_edge (Safe/live) | opportunity.py:998-1020; live_engine_pro.py:588-600 | EV per STAKE su entrambi i lati | C-6 MEDIO (strategia): non confrontabile sul rischio fra back e lay |
| MIN_COMPOSITE_EDGE 0.02 | market_intelligence/edge_scorer.py | punti di probabilita' | D 2.7: +2 pp = EV ~+3% a quota 1.5, ~+20% a quota 10 (non comparabile tra quote); consumatore: pipeline/audit MI, collegamento a consigli UI NON VERIFICATO |
| gate Safe tennis .90 / .015 / lay .10 q<=8 | tennis_opportunity.py:55,414-480 | probabilita' del modello Markov | vedi sez. 11 (tie-break fisso) |
| tau/rho fallback -0.13 | today_predictions_backfill.py:1148,1186-1189; live_engine_pro.py:40,88; dc_rho_by_league.json | `dc_rho_by_league.json`: 24 leghe, media -0.0809, min -0.1997, max -0.0229, global_fallback -0.13, min_matches 300, shrink_k 300 | A 6: **BASSO** (CERT_2 B2: scelta dichiarata, rho -0,13 = stima originale Dixon-Coles; era BASSO-MEDIO CONFERMATO da H) [cert. fase 2]; il conteggio "~475 leghe" NON VERIFICATO. Sonda h_poisson.py: rho -0.13 vs -0.081 a lambda 1.4/1.1: D +1.24 pp, H e A -0.62 pp, BTTS +0.62, O1.5 +0.62, O2.5 0.00 (effetto massimo 1.2 pp su X, sotto il rumore di 800 partite) |
| MIN_MATCHES_FOR_POISSON=5, nessuna memoria cross-stagione | today_predictions_backfill.py:1216-1224,1534-1540 | filtro lega+stagione | A 4: **BASSO** (CERT_1 M4: copertura ridotta, nessun numero sbagliato; era MEDIO CONFERMATO da H) [cert. fase 2] |
| n minimo pagella 20 globale / 10 per lega; K=50 fisso | build_direzione.py:196-232; get_direction_rpc.sql:182-218 | hit rate per fascia | E2-13 BASSO/MEDIO; D 2.4 BASSO (K non stimato, Wilson su eff_n = n_l+K tratta il prior come dati veri) |
| `HEDGE_EPS=0.01`, `abs(win-lose)<0.05` | execution.py:1919 e :2023,2020-2024 | assolute in EUR | C-7 BASSO (non scalano con lo stake) |
| A_MAX>=0.72 (ventaglio) | ventaglio_segnali.py:216-262 | MARKET_BASE 0.74-0.76 + bonus - penalita' | **E2-6 BASSO, gravita' rivista da V2** (E2 lo dava MEDIO): CLI di ricerca (solo `valida_ventaglio.py`), "benchmark validati"; aritmetica verificata (0.76-0.03=0.73>=0.72: "quasi automatico" vero per O/U 1.5 e HT Over 0.5); manca il lift sul base-rate, campione 18 partite del 19/06 |
| `oos_valid` / `ml_reliable` (p_ml_clean) | build_analytics_signals.py:298; merge_engine_signals.py:203; analytics_strategy_rpc.sql:114,217 | `oos_valid=True` sempre scritto | **E2-3 MEDIO, CONFERMATO da V2**: il filtro vale solo `ml_reliable`; contaminazione reale NON verificata sul DB |
| `analyze_sweet_spot` soglie in-sample | Prediction/analyze_sweet_spot.py:9-80 | top-10 per hit rate con n>=20, `select` senza paginazione | D-R7 BASSO (CERT_2 M16: strumento CLI manuale, nessun consumatore; tetto PostgREST NON VERIFICATO) [cert. fase 2] |
**Verdetto: CORRETTO CON LIMITI** (soglie coerenti come unita' ma tre problemi di costruzione: baseline uniforme del gate, edge in punti-probabilita', `oos_valid` hardcoded).
**Si puo' fare meglio?** SI: baseline climatologica + IC nel gate (B P1), edge in EV%, `oos_valid = generated_at < kickoff` (E2 P3, costo piccolo, effetto nullo sui bot). Le soglie dei bot NON si toccano senza l'utente.

---------------------------------------------------------------------------------------------------

## 13. Aggregazioni e metriche di report (ROI/yield, drawdown, profit factor, Sharpe, CLV, Wilson/Wald)

**Formula e file:riga**
| metrica | copie (file:riga) | formula |
|---|---|---|
| ROI | D21 analytics_rpc_veloci_2026-09-26.sql:219-249,567-646 (pnl/stake sulle piazzate SETTLATE); D23 direction_report_rpc.sql:99-147 (Σpnl/N, stake 1); D25/D26 personal_tracking_rpc.sql:355-356, 775,794,812 (net/STAKE anche per i lay; liability salvata a parte :295); D34 money_management.py (yield pnl/staked); run_backtest.py:174 (pnl/stake, non letto) | denominatori diversi |
| Drawdown | D26 personal_tracking_rpc.sql:643-645 (letto: peak = max(equity) sulle sole righe); D10 frontend/src/lib/dailyHistory.ts:899-910 (letto: `peak = 0` iniziale) | peak senza/con punto 0 |
| Profit factor | D10/D27 (per TRADE, gross_profit/gross_loss da trade_tot); D26 (per GIORNO) | stesso nome, definizione diversa |
| Sharpe/Sortino/Ulcer/CVaR/Kurtosis | D26 personal_tracking_rpc.sql:594-840 | Sharpe = mean/dev.std(n-1) del P&L giornaliero in EUR, non annualizzato; Sortino target 0; Ulcer su equity cumulata (:675); CVaR5; Kurtosis (Excel KURT) |
| CLV | D34 money_management.py:2494-2511,2971-2985 | clv = 1/closing - 1/entry su probabilita' GREZZE |
| Wilson | D20 analytics_rpc_veloci_2026-09-26.sql:405-412 (corretto); D24 get_direction_rpc.sql:182-218 (su eff_n=n_l+K); D33 market_intelligence/calibration.py:112-116 (`_wilson_ci`, letto: z*sqrt(p(1-p)/n) = WALD con nome Wilson); copia in market_intelligence/backtest.py:117-120 | -- |
| win rate / hit rate | D14 SplitSport.tsx:244, D27, D21, D23 | stessa formula, popolazioni diverse |
| expectancy | dailyHistory.ts (D10) | Σpnl_realized / Σsettled |

**Esempi numerici (a mano / sonde)**
- ROI su stake vs liability (sonda D_sonda_formule.py): lay 10@5 perso: -40 -> -400% su stake, -100% su liability; vinto +9.50 -> +95% / +23.75%. Aggregato di 4 vinte + 1 persa: -2.00 EUR = -4.0% su stake, -1.0% su liability.
- Drawdown (sonda h_dd.py, pnl giornalieri [-10,-20]): SQL equity -10,-30, peak -10, max_drawdown -20; TS peak 0, cum -30, drawdown 30 (a mano: coincide).
- Wilson vs Wald (sonda D_sonda_formule.py): n=30, p=0.9 -> Wilson (0.744, 0.965); Wald (0.793, 1.007) (>1); p=1 -> Wald ampiezza 0, Wilson (0.886, 1.0). A mano Wald: 1.96*sqrt(0.09/30)=0.107, 0.9+-0.107 = (0.793,1.007).
- CLV (sonda D_sonda_formule.py, riverificato a mano): prob fair 0.50, overround 1.04 all'ingresso e 1.02 alla chiusura -> 1/closing - 1/entry = 0.51-0.52 = -0.0100 con valore vero ZERO.
- Ulcer: peak 1 EUR con -20 EUR -> -2100% (DD% su equity cumulata da 0, non sul capitale; D 2.5).
- Calcolo `get_direction_report`: odds = `max(es.odds)` per (fixture, mercato, selezione) a :103 (e in due varianti a :418 e :540, osservato di persona); `when r.hit then (bf.odds - 1) * (1 - v_comm)` a :143.

**Casi limite**: `roi = v_net / NULLIF(t.stake,0)` (divisione per zero evitata); conf_bin prob=1.0 -> floor(20)=20 -> least(...,19) (bordo ok); `turnover = total_pnl / roi` (analytics.ts:494, ricostruzione approssimata; roi=0 -> null; D-R10 BASSO);
profit factor con gross_loss=0 NON VERIFICATO; Kurtosis/CVaR verificate corrette.

**Reperti (gravita' finale)**
- **D-R1 `max(es.odds)` (direction_report_rpc.sql:103,142-143)**: **BASSO, gravita' rivista da H** (D lo dava ALTO "da misurare"). Pattern CONFERMATO, impatto SMENTITO nella finestra misurata: sonda h_engine_signals.py (1 SELECT, 2000 righe, run_date>=2026-09-15): 1095 gruppi (fixture,mercato); 894 (82%) con 2 righe, in TUTTI i 894 max=min (scarto 0.000): quota unica (NON VERIFICATO in fase 2: misura su DB non rifatta). [cert. fase 2] Limiti: finestra solo dal 15/09 e primi ~74 fixture per id; le righe da backfill di `mm_history.json` (storico piu' vecchio) non misurate: rischio LATENTE, non misurato come reale. L'unica definizione nel repo e' questa (nessuna migrazione successiva la ridefinisce); che sia applicata cosi' sul DB NON verificato.
- **D-R3 ROI = net/stake anche per i lay**: **BASSO** (CERT_2 B3: convenzione; H BASSO-MEDIO, D MEDIO) [cert. fase 2]: convenzione, non errore di formula; nessun effetto sui soldi; ROI di back e lay nello stesso aggregato non confrontabili.
- **D-R4 drawdown SQL vs TS**: **BASSO** (CERT_2 M18; H MEDIO-BASSO, D MEDIO) [cert. fase 2]: la definizione TS (peak da 0) e' quella corretta; il commento SQL a :636 dice "equity cumulativa da 0" ma il codice non include la riga zero.
- **D-R5 CLV su probabilita' grezze**: **BASSO RIDIMENSIONATO** (CERT_2 B4: scelta dichiarata nel codice, money_management.py:2503-2509; limite reale = overround variabile; H BASSO-MEDIO, D MEDIO) [cert. fase 2]: indicatore solo su foglio Sheets (Quant Fund); chiusure con margine piu' stretto rendono il CLV sistematicamente negativo. "Chiusura" = quote a ~5 minuti dal KO (`update_closing_odds`), non l'ultima; verdetto "SKILL_SIGNAL" se media>0 senza test (t = media/(std/sqrt(n)) non calcolato). Il ricalcolo retroattivo (:1357-1372) riscrive il P&L dei vinti con la commissione ATTUALE di config.
- D-R2 market_intelligence (bias su implicita grezza sommata alla devigata, `_wilson_ci` Wald con flag `significant` calcolato su Wald e mai usato, edge in punti): **BASSO** (CERT_2 M14: Wald con nome Wilson, `significant` mai usato nel punteggio; prima MEDIO, non rivalutato da H/V2) [cert. fase 2]. Sonda D_sonda_formule.py: raw 0.40, fair 0.385, real 0.40 -> true_prob 0.385 (-0.015, quasi la soglia 0.02). Nota mia: la stessa funzione Wald-con-nome-Wilson esiste in DUE file (calibration.py:112-116 e backtest.py:117-120).
- D-R6 (avg_edge/avg_odds/avg_prob su tutto il gruppo, hit_rate/roi sulle sole piazzate settlate; analytics_rpc_veloci_2026-09-26.sql:598-640): BASSO (CERT_2 M15: numeri mostrati) [cert. fase 2]; "le scartate non hanno quota" NON VERIFICATO.
- D-R9 Sharpe non annualizzato/in EUR, Calmar = recovery_factor (formula identica), Ulcer su equity cumulata, expectancy con numeratore/denominatore disomogenei, profit factor per trade vs per giorno: BASSO, non rivalutato.
- D-R10 BASSO (turnover approssimato, K=50, report_mm con look-ahead e commissione 0 e W=50% fisso, `media` dei ritardi). D-R7 vedi sez. 12.
- E2-4 win rate tennis per ordine: BASSO (rivisto da V2, sez. 11). Q1: win/lost per TRADE; pnl_realized per op_day vs gross su settled_day: partizione diversa, NON VERIFICATO numericamente.
- Positivi verificati (D): Wilson SQL D20 esatta; settlement hit D30 corretto (punteggio 90', linee X.5 senza push); finestre D31 "in entrata" senza look-ahead; riepilogo = somme esatte (non medie di percentuali); frontend "mai inventare un numero" (null/unpriced, fail-closed), mai stantio (signalsStale > 120-150 s -> nascosto).

**Copie e divergenze (tabella)**
| grandezza | divergono? | esempio |
|---|---|---|
| ROI | SI (stake unitario / stake / liability; popolazioni diverse) | lay 10@5: -400% vs -100% |
| Drawdown | SI | [-10,-20]: 30 (TS) vs 20 (SQL) |
| Profit factor | SI (per trade vs per giorno) | stesso nome |
| Win/hit rate | SI (popolazioni) | formula uguale |
| Wilson | SI (D33/backtest.py Wald) | n=30,p=.9: [0.744,0.965] vs [0.793,1.007] |
| Implicita / devig | SI (4 definizioni, sez. 1) | - |
| Settlement hit Python vs SQL `market_frequency_rpc` | NON VERIFICATO (SQL non letto) | - |

**Stato dell'arte (R)**: ROI/yield = profitto / capitale a rischio (liability per i lay) (D "da memoria", FONTE NON APERTA); Wilson 1927; Brown-Cai-DasGupta 2001 (da memoria); CLV come predittore di abilita': Pinnacle/Buchdahl "chiusura de-viggata (spesso con metodo potenza)" - R: solo fonti vendor/blog, [RICERCA, debolmente affidabili], nessuna fonte accademica aperta: **INDIETRO (probabile)**.
**Verdetto: CORRETTO CON LIMITI** (le aggregazioni SQL principali sono esatte; i nomi coprono definizioni diverse; un'unica definizione di ROI/drawdown/profit factor manca).
**Si puo' fare meglio?** SI: (D prop. 2) una definizione unica con test di contratto Python/SQL/TS sugli stessi 20 trade; (D 1) Direzioni con la quota dell'ultima rilevazione PRIMA del KO invece del max; (D 4) CLV su chiusura devigata (Shin/power) con errore standard e t-stat; (D 3) Wilson reale e `significant` nell'MI.
Decisioni dell'utente (D par. 5): se il ROI dei lay debba passare a base liability (cambia numeri storici); se la quota del report Direzioni debba cambiare; se la commissione dei P&L storici di money_management debba restare ricalcolata con la config attuale (:1357).

---------------------------------------------------------------------------------------------------

## 14. Tabella riassuntiva

| componente | verdetto | reperti (id e gravita' FINALE) | NON VERIFICATO |
|---|---|---|---|
| 1. Probabilita' implicite e devig | corretto con limiti | C-13 BASSO (0.975 fisso); metodo moltiplicativo INDIETRO per 1X2 (M: power/Shin -0.003/-0.004 logloss, significativi; O25/BTTS nulli) | Shin/potenza non usati in nessun bot; fonti Shin 1991/93 non aperte |
| 2. Prezzi equi | corretto con limiti | V2 A-3 BASSO (CERT_1 M3) [cert. fase 2]; V2 F-3 MEDIO; V2 F-2 BASSO/MEDIO (rivisto); V2 F-1 BASSO; M previsioni post-KO (non leakage) MEDIO, GIA' NOTO (CERT_1 M1) | causa del sovra-estremo Poisson; origine del leakage nello storico delle feature (non letto; il conteggio post-KO e' riprodotto in CERT_1 M1); timestamp delle quote |
| 3. Valore atteso / edge | corretto (formula); con limiti (gate) | C-6 MEDIO strategia; D-R2 BASSO (CERT_2 M14) [cert. fase 2]; C-12 BASSO | collegamento edge MI -> consigli UI |
| 4. Kelly, stake, tetti, minimi .it | corretto con limiti | C-3 BASSO (rivisto da H, era MEDIO); E2-7 SMENTITO (V2); C-5 BASSO; C-11 BASSO; minimi .it BASSO (CERT_2 M13; V2: MEDIO coerenza) [cert. fase 2] | tetto 10.000 EUR GESTITO (`live_order_build.py:875-886`) e back+lay nello stesso placeOrders impossibile per costruzione (CERT_5 5.2); guardia payout sui percorsi diretti di Mike/Omega/scalper (CERT_3 B39); K1 attivo oggi?; etichetta UI del lay |
| 5. Green-up / hedge / cash-out | corretto | C-7 BASSO; D-R8 BASSO/MEDIO; E-4 BASSO; E2-12 BASSO; E2-14 BASSO | netto realizzabile Mike (replay); profondita' nel cash-out; etichetta lordo/netto UI; detector tier0 su stesso mercato; parita' con flumine exposure |
| 6. Dutching | **difettoso** (modo variable; CORRETTO in fase 2 il 09/10/2026, lavori/fase2/FIX_DUTCHING_delegato.md) [cert. fase 2] | E2-2 **ALTO** (variable+lay piazza BACK; confermato V2 e coordinatore; corretto in fase 2); E2-1 **MEDIO** (anteprima != server; rivisto da V2, era ALTO); E2-5 BASSO; N5 BASSO | stato LIVE di `live_now` oggi; esecuzione reale via flumine (non eseguito) |
| 7. P&L e commissione | corretto con limiti | C-2/C4 BASSO (confermato e quantificato da V2); C-9 BASSO; E2-11 BASSO; E-4 BASSO | regola di arrotondamento di Betfair; aliquota reale dell'utente (4.5% vs 5%); C5 banco `pnl()` vs `pnl_betfair()` non riverificato; `settle_group` vera non chiamata da V2 |
| 8. Scala dei prezzi e tick | corretto con limiti | C-1 `round_to_tick(NaN)->1000` BASSO (CERT_2 B1: percorso REST manuale, nessun bot, NaN non ammesso da JSON standard; H BASSO-MEDIO, era MEDIO) [cert. fase 2]; C-4 BASSO; C-8 BASSO; C-14 INFO | ladder FINEST/LINE_RANGE; riskMath.ts (frontend) non riverificato |
| 9. xG, Elo, rating | corretto con limiti | B-R9 Elo BASSO (rivisto da V2, era MEDIO); xG-boost MI euristico (D, non rivalutato) | `assembla_v4`, `consulta_atlante_v4`, `genera_atlante.assembla`; blend xG Poisson (catena A) non rivalutato qui |
| 10. Statistiche live, hazard | corretto | E2-8 BASSO (tau in-play 0-0 vs ovunque, scarto 2.1 pp; decisione utente) | valori numerici atlante; w_now=0 |
| 11. Tennis | corretto con limiti | E-1 BASSO LATENTE (rivisto da V2, era MEDIO); E-2 BASSO; E-3 BASSO; E2-10 BASSO; E2-4 BASSO (rivisto da V2, era MEDIO) | costruzione `_probs`/gate (tennis_opportunity 262-521); segno pnl per ordine; (Safe tennis CERTIFICATO sul banco il 09/10, CRONOSTORIA.md:5609-5618: 18/18 OK, 0 violazioni, codice `25cab047`; l'audit non ha lanciato replay) [cert. fase 2] |
| 12. Soglie | corretto con limiti | B-R1 gate BSS MEDIO (CERT_1 MA1; impatto soldi solo Sheets) [cert. fase 2]; A-6 BASSO (CERT_2 B2); A-4 BASSO (CERT_1 M4); E2-3 MEDIO; E2-6 BASSO (rivisto da V2); D-R7 BASSO (CERT_2 M16) | numero di leghe servite dal fallback rho; contaminazione `oos_valid` sul DB; tetto PostgREST |
| 13. Aggregazioni e metriche | corretto con limiti | D-R1 BASSO (rivisto da H, era ALTO); D-R3 BASSO (CERT_2 B3); D-R4 BASSO (CERT_2 M18); D-R5 BASSO RIDIMENSIONATO (CERT_2 B4); D-R2 BASSO (CERT_2 M14); D-R6 BASSO (CERT_2 M15); [cert. fase 2] D-R9/R10 BASSO | `max(odds)` sulle righe da backfill storico; coerenza settlement Python/SQL; funzioni SQL dei bot (omega_*, mike_*, safe_*, storico_sport...); `get_market_delays/frequency` e `backtest_strategy` (IC del ROI) |

Reperti ALTO finali dell'intero perimetro 03: **uno solo: E2-2 (dutching variable + lay piazza BACK)**, CORRETTO in fase 2 il 09/10/2026 (lavori/fase2/FIX_DUTCHING_delegato.md). [cert. fase 2] Nessun CRITICO. Nessun ALTO sui soldi in Betfair math/C (C aveva gia' concluso "nessun CRITICO, nessun ALTO"; H e V2 non hanno trovato nulla di diverso).

---------------------------------------------------------------------------------------------------

## 15. Verifica a campione di persona (Read/Grep su file:riga, 09/10/2026)

Letti di persona 14 punti. Esito:
1. `Betfair/order_exec.py:95-119` - **CONFERMATA**: `_TICK_BANDS` (95-99) coincide con la scala ufficiale; `round_to_tick` a 115-118 = `max(1.01, min(1000.0, float(price)))` poi `min(_TICKS, key=abs)`; con NaN `min(1000.0, nan)` restituisce 1000.0 (confermato il percorso NaN->1000).
2. `Betfair/stream/trading/greenup.py` - **FORMULA CONFERMATA, CITAZIONE STANTIA**: `full = round(diff_abs / price, 2)` e' a riga **109** (in `_hedge_size`, 101-111), non 105 come scrive C.
3. `Betfair/money_management.py:800-813` - **CONFERMATA**: Kelly netto (800-804), `stake = min(stake, max_stake)` (811), floor `max(round(stake,2), 1.0)` a riga **812** (H aveva ragione; C citava 813-814); `kelly_full<=0 -> 0.0` (806-807) copre c=1.
4. `Betfair/safe_strategy/execution.py:2702-2715` - **CONFERMATA**: `comm = net * c if net > 0` (2709), `total = round(net - comm, 2)` (2710), pro-rata per gambe in utile (2711-2713). V2 cita 2706-2711: ok (2706 e' il `max(0.0,float(commission))`).
5. `Betfair/mike/engine.py:1653-1672` - **CONFERMATA CON CITAZIONE CORRETTA**: `comm_market[m] = round(max(0.0, v) * float(commission), 2)` e' a **1653-1655**; V2 e C citano 1666-1668 (stantio: lì c'e' il commento RG1 e `by_market`); netto del mercato `round(v - comm_market.get(m,0.0), 2)` a 1672. In piu': a **1101** `cashout_value` usa `v * float(commission)` senza arrotondare (osservazione mia, non misurata).
6. `Betfair/stream/live_order_worker.py:2908-2927` - **CONFERMATA**: `dmode == "variable"` chiama `dutch_variable(triples, total)` senza considerare `side` (2914-2919); `target` rifiuta lay (2922-2924).
7. `Betfair/stream/trading/dutching.py` (grep `side=`) - **CONFERMATA**: `dutch_variable` ritorna `side="back"` fisso (righe 224 e 239); `dutch_lay` ha side="lay" (178).
8. `Betfair/stream/trading/minimi_it.py:40-69` - **CONFERMATA**: IT_MIN_BACK=1.00, IT_MIN_LAY=1.00, IT_FLOOR_LEGGE=0.50, IT_PASSO_PUNTA_DIRETTA=0.50, SUBMIN_IMPORTO_FINALE_MIN=0.50; la nota cita "multiples of 50 Euro Cents" della documentazione sviluppatori.
9. `migrations/personal_tracking_rpc.sql:636-647` - **CONFERMATA**: `max(equity) OVER (... UNBOUNDED PRECEDING ...)` senza riga zero (643-645); la serie [-10,-20] da' 20 contro 30 del TS.
10. `frontend/src/lib/dailyHistory.ts:898-910` - **CONFERMATA**: `let peak = 0` (900); commento "partenza da 0 = nessun trade".
11. `Betfair/stream/tennis_scalper/tennis_winprob.py:20-66` - **CONFERMATA**: `p_tb: float = 0.5` (22), `return p_tb` a 6-6 (36-37), `p_match` chiama `p_set(ga, gb, a_serves, ha, hb)` senza `p_tb` (60), `a_serves=True` ai set successivi (64-65).
12. `market_intelligence/calibration.py:112-116` - **CONFERMATA, CITAZIONE STANTIA**: `_wilson_ci` = `z*sqrt(p*(1-p)/n)` (Wald con docstring "Wilson"); D cita ~150/152,165. **NUOVO**: stessa funzione in `market_intelligence/backtest.py:117-120` (non citata da D).
13. `Betfair/stream/engine/live_engine_pro.py:414-440` - **CONFERMATA**: `_kelly_back` f=p-(1-p)/b con b=(o-1)(1-c); `_kelly_lay` f=(1-p)/(L-1)-p/(1-c), per `fraction*bankroll` (cioe' lo STAKE).
14. `migrations/direction_report_rpc.sql` (grep) - **CONFERMATA**: `max(es.odds) as odds` a :103 e `(bf.odds - 1) * (1 - v_comm)` a :143; **NUOVO**: lo stesso `max(es.odds)` compare anche a :418 e :540 (varianti `_matches`/`_fixture`), con la stessa conversione a :450 e :569.
Citazioni stantie trovate: 3 (greenup.py:105 -> 109; mike 1666-1668 -> 1653-1655; calibration.py ~150 -> 112-116) e 1 (money_management 813-814 -> 812, gia' corretta da H). Nessuna citazione smentita nella sostanza.
Non rilette di persona (si fidano dei delegati e dei verificatori): tutte le cifre delle sonde, le query al DB di H/V2/M, le formule di tier1_quasi.ts, hedging.py, xhedge.py, atlante_v4.py, omega_empirical.py, i valori R_stato_arte (fonti web).


---------------------------------------------------------------------------------------------------
(Sezioni 16-18 aggiunte dal coordinatore dopo l'ondata finale; gravita' finali in 05_ERRORI_DI_PROGETTAZIONE.md, che
prevale sulla tabella 14: dopo la scrittura di questo file sono emersi altri reperti, rivalutati in fase 2: ML senza valore oltre il mercato MEDIO-ALTO (A2), gate ML sul rumore MEDIO-ALTO (A3), modello tennis di sez. 17 MEDIO (A4); l'unico ALTO resta E2-2, CORRETTO in fase 2 il 09/10/2026.) [cert. fase 2]

## 16. Catena hazard in-play e stimatori empirici (lavori/Z1_hazard.md, sonde z1_*)

Componenti: atlante v3 (`Betfair/stream/scalper/genera_atlante.py`, `hazard_atlas.py:271-372`), atlante v4
(`atlante_v4.py`: forza `lh=mu_h*exp(att_h+dif_a)`, `_p_recupero2`, `assembla_v4`, `consulta_atlante_v4`), taratura
(`validazione_hazard/forza.py`, `candidati.py`), `combine_hazard` di Mike (`mike/dossier.py:114-123`), stimatori Omega
(`omega/omega_empirical.py`: Wilson unilaterale z=1,64 con shrink, `max(P_modello, P_empirica)`), tabelle di
transizione SQL (`migrations/omega_transitions_*`).
- Correttezza: `_p_recupero2` e `shrunk_upper` ricalcolati a mano coincidono (esempio del docstring 1,265%). Nei bucket
  regolari atlante v3 e Poisson con CDF dei gol (value_engine/goal_timing.py) concordano entro il 5% (rapporto 1,01-1,06).
- Leakage: nessuno nel live; validazione walk-forward per stagione (addestra <=2023 valuta 2024, poi <=2024 valuta 2025).
- Limiti (MEDIO per il v3; BASSO per Theta, tabella Omega e combine_hazard, vedi sotto) [cert. fase 2]: il v3 sottostima l'hazard a 88-89' del 44% (M_MAX=87, recupero schiacciato a 90; genera_atlante.py:81,
  :154-170) e Theta (opt-in: `theta_mode`, scalper_session.py:1560,1709; non e' nella decisione D2, CRONOSTORIA.md:3045-3047: BASSO) usa ancora il v3 con il livello squadre che la validazione ha trovato peggiorativo (theta_bot.py:550);
  `omega_empirical.py:166-176` (BUCKET_STEP=5): la tabella per minuto non ha tetto di minuto, ma la finestra d'ingresso e' ft_entry_max 80 (v3: 85: omega_config.py:61-63, 251-253): in finestra il bias di bucket e' al massimo ~x1,3 (CERT_2 M21, BASSO); [cert. fase 2] limite di Wilson usato anche per il ranking (premia n grandi);
  `combine_hazard` di Mike = SCELTA DOCUMENTATA (COSTITUZIONE_MIKE.md:157-158: comanda la fonte piu' prudente); resta aperta solo la taratura del 1,25 (CERT_2 M20). [cert. fase 2]
- Stato dell'arte: modelli di intensita' in-play dipendenti da minuto e punteggio (Dixon & Robinson 1998, "A birth process
  model for association football matches", The Statistician; [ricerca] in Z1) e empirical Bayes per tassi con poche
  osservazioni: l'atlante v4 (forza + shrink + validazione walk-forward) e' ALLINEATO nell'impianto; il v3 no; il max() di Mike e' scelta documentata (CERT_2 M20). [cert. fase 2]
- Verdetto: corretto con limiti; si puo' fare meglio togliendo il v3 dove resta e sostituendo il max() con una media pesata
  per varianza (decisione utente: strategie Theta e Mike).

## 17. Tennis (lavori/Z2_tennis_residui.md, sonde z2_*) e matematica residua dei servizi

- **MEDIO** (CERT_1 A4: la P usa solo i giochi, ma gli ingressi di Safe tennis (`engine.py:1567` `evaluate_tennis`) non usano il modello; il modello decide proposte (`auto_trade_tennis` default False, `bot_service.py:193`) e il cancello delle uscite in PROFITTO (`bot_service.py:5295-5330`); strategia, da portare all'utente) [cert. fase 2]: la P(vittoria) di Safe tennis non usa i punti del game in corso: letti in
  `_state` (tennis_opportunity.py:219) e mai usati da `_p_raw_p1` (:250-261) [C]. Esempio: leader al servizio sul 4-2 con un
  set di vantaggio, sullo 0-40: P corretta 0,827, P usata 0,924 (sonda z2_punti_nel_game). L'edge apparente e' massimo
  proprio sui break point.
- **MEDIO** (CERT_1 A4, stesso perimetro: cancello delle uscite in profitto e proposte, non gli ingressi; strategia) [cert. fase 2]: hold uguale per i due giocatori (prior 0,75) perche' `serve_data.csv` non esiste
  (tennis_opportunity.py:223-242 [C]): la P dipende solo dal punteggio; sullo stesso stato varia da 0,757 a 0,978 al
  variare degli hold veri. La soglia 0,90 e il min_edge 0,015 operano dentro questa banda; contro quote che conoscono la
  forza dei giocatori il segnale e' esposto a selezione avversa. Effetto in soldi NON VERIFICATO (nessun esito reale letto).
- Gia' noti e confermati: tie-break fisso 0,5 e servizio non alternato tra set (sez. 11, latenti finche' gli hold sono
  simmetrici); ripiego `estimate_holds(0,0,0,0)` = 0,7917 (bot_service.py:5233).
- BASSO (CERT_2 M23, solo display `TennisMatchStats.tsx:405`; era MEDIO) [cert. fase 2]: `win_prob_p1` mostrato in UI sovra-estremo (serviceBreaks sempre 0 nel sidecar, hold fino a 0,95; best_of=3 fisso;
  tennis_runner.py:318-319): solo UI.
- BASSO (CERT_2 M22; era MEDIO): lo stop di conto e' SPENTO di serie (`daily_loss_limit` NULL: daily_stop_worker.py:124-134), decisione dell'utente CRONOSTORIA.md:2956; stop propri: Mike 50 (acceso), Omega 0 (spento) [cert. fase 2]. Se acceso: stop giornaliero (`Betfair/stream/trading/daily_pnl.py`) con realized LORDO di commissione (reconcile_worker.py:555,
  simulatedorder.py:564): con +200 lordi lo stop a -50 equivale a circa -60 netti; perimetro asimmetrico (realized = conto
  intero, MTM = solo live_strategy, MTM senza profondita' del book).
- Corretti (sonde): `hold_from_serve_point` contro programmazione dinamica esatta; Theta: locked>0 implica netto>0 su 282
  coppie; conversione GBP->EUR (valuta.py) con errore <= 0,005 EUR per livello. BASSI: rischio ritiro additivo fisso
  2%/3% (prudente per back leader), liability in tre copie con tolleranze diverse, `netto_size` che annulla back e lay a
  prezzi diversi (esposizione_fuori_bot.py:272-282).
- Stato dell'arte: modelli a catena di Markov punto-gioco-set con probabilita' al servizio per giocatore (Newton & Keller
  2005; Klaassen & Magnus 2003; Barnett & Clarke 2005: citati in Z2 per nome, FONTE NON APERTA). L'impianto e' quello
  giusto ma senza i due ingressi che lo rendono informativo (punti, forza dei giocatori): INDIETRO.

## 18. Verdetto di sintesi per il par. 1.3 del brief (componenti matematici)

| Domanda | Verdetto | Perche' |
|---|---|---|
| Sono al massimo livello? | **IN PARTE** | La matematica dell'esecuzione (green-up S*B/L, P&L back/lay, commissione sul netto per mercato, Kelly al netto, scala dei tick, liability, conversione valuta) e' corretta sui conti a mano e coerente con la documentazione Betfair e con flumine. Sotto il livello: de-vig solo moltiplicativo (power/Shin migliori, misurato), modello tennis senza punti e senza forza dei giocatori, hazard v3 ancora in uso, scelta documentata `max()` di Mike (COSTITUZIONE_MIKE.md:157-158; resta aperta la taratura del 1,25). [cert. fase 2] |
| Si puo' fare meglio? | **SI'** | Regola unica per commissione e tick; de-vig power/Shin; tennis con punti e hold per giocatore; v4 al posto del v3; metriche di report con una sola definizione (06). |
| Abbiamo omesso qualcosa? | **SI'** | Regole .it della documentazione developer: GESTITE (tetto vincita 10.000 EUR in `live_order_build.py:875-886`; back+lay nello stesso placeOrders impossibile per costruzione; resta da verificare solo la guardia payout sui percorsi diretti di Mike/Omega/scalper, CERT_3 B39) [cert. fase 2]; commissione nello stop giornaliero (stop di conto spento di serie, CERT_2 M22); CLV de-viggato. |
| E' la soluzione migliore per performance e risultati? | **NO per i segnali, SI' per l'esecuzione** | Dove il numero decide se entrare (edge, P tennis, hazard max) l'informazione e' inferiore al mercato o distorta; dove il numero esegue (stake, hedge, P&L) la matematica e' giusta. Unico errore di esecuzione con soldi veri: dutching variable+lay (sez. 6), CORRETTO in fase 2 il 09/10/2026 (lavori/fase2/FIX_DUTCHING_delegato.md). [cert. fase 2] |

xG: non e' calcolato da noi; si usa l'xG di API-Football (`match_team_stats.expected_goals`) nel blend del Poisson
(peso 0,4, non tarato: 01 sez. 2) e come termine euristico nell'edge di market_intelligence (xG*abs(rho)*0,10,
edge_scorer.py:316-380); l'ML non lo usa (B). Verdetto: uso corretto ma non tarato.

Kelly: il foglio usa frazione 0,10, piu' prudente della forchetta 1/4-1/2 di Kelly citata in letteratura
(MacLean-Thorp-Ziemba, FONTE NON APERTA): non e' "allineato", e' piu' conservativo; con probabilita' meno informate del
mercato e' la scelta coerente.
