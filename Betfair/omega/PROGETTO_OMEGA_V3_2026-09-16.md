# PROGETTO OMEGA V3 — «una gamba nel 1T, una nel 2T, lay 1 €, su tutte le partite»

> 16/09/2026 sera. Documento di **progetto** (gradino §1-§2 di `PROCESSO_STANDARD_BOT.md`:
> si progetta, si mappa; il codice viene dopo). Sola lettura: nessuna riga di codice toccata.
> Ordine dell'utente riportato integralmente in §0. Ogni numero ha la sua fonte; ogni
> affermazione sul codice ha `file:riga`.

## 0. L'ordine (testuale, 16/09 sera)

«Omega deve usare la potenza del nostro database per ogni singola partita (ritardi, frequenze,
poisson, ML, tactics ai ecc, tutto nella dashboard di quella partita); il suo obiettivo è
individuare UNA GAMBA NEL PRIMO TEMPO E UNA GAMBA NEL SECONDO TEMPO, che abbiano le probabilità
MINORI di verificarsi in relazione a tutto quello che abbiamo; sentiti libero di modificare o
migliorare la strategia; voglio 2 ingressi a partita; NON MI INTERESSA LA QUOTA, voglio
raccogliere spicci davanti al rullo compressore; Omega dovrà OPERARE SU TUTTE LE PARTITE
effettuando 2 ingressi per partita; dobbiamo avere le probabilità dalla nostra parte; INGRESSO
STANDARD: 1 euro in LAY; ispeziona realmente tutto quello che può aiutare il sistema a
prediligere il risultato CHE NON SI VERIFICHERÀ».

---

## 1. COSA FA OGGI OMEGA, passo per passo

### 1.1 Il giro

1. **Universo**: eventi calcio Betfair di oggi; ciclo `run_once` (`omega_service.py:4947`),
   cadenza `poll_interval_s` 20 s (`omega_config.py:32`).
2. **Due gambe per partita** (`_LEGS`, `omega_service.py:944`): `ht_cs` su **HALF_TIME_SCORE**
   fra `ht_entry_min` 20' e `ht_entry_max` 40'; `ft_cs` su **CORRECT_SCORE** fra `ft_entry_min`
   50' e `ft_entry_max` 80' (`omega_config.py:60-63`). Minuto e punteggio dal feed unico, mai
   dall'orologio (`_scan_event_legs`, `omega_service.py:1019`).
3. **Quanto si punta** (è la chiave di R1): obiettivo di giornata `daily_goal` **250 €**
   (`omega_config.py:13`); target di gamba = `(G − R) / gambe residue` (`dynamic_target`,
   `omega_engine.py:218`, chiamato a `omega_service.py:1057`); la size è il **backer-stake che
   incassa il target**: `s = target/(1−c)` (`lay_size_from_target`, `omega_engine.py:225`).
   **La size di oggi non è scelta: è dedotta dall'obiettivo.**
4. **Catena λ** (`_prematch_lambdas`, `omega_service.py:591`), in ordine:
   fixture del DB (`get_fixture_prematch_lambdas`, `Betfair/stream/db.py:211` →
   `tactical_engine_json` poi `db_json_analisi.inputs`) → λ persistiti su `omega_events.model`
   → quote 1X2 pre-KO congelate (`lambdas_from_pre_ko`, `omega_model.py:131`) → hint da un trade
   precedente → λ impliciti nell'intero mercato (`lambdas_from_market_grid`, `omega_model.py:1042`)
   → O/U live (`lambdas_from_live_ou`, `omega_model.py:743`). Senza λ **non si entra mai**.
5. **Griglia**: λ residui live (`residual_lambdas`, `omega_model.py:219`; orizzonte 45' per la
   gamba HT via `ht_residual_share`, `omega_model.py:238`), Poisson + Dixon-Coles con incertezza
   log-normale su λ (`residual_grid`, `omega_model.py:300`, `model_lambda_cv` 0,30).
6. **Selezione §11** (`select_by_model`, `omega_model.py:479`). Filtri, nell'ordine del codice:
   prezzo in `[price_min 20, price_max 120]`; liquidità ≥ max(`min_lay_liquidity` 5 €, size
   cappata); solo scoreline numeriche; punteggio raggiungibile; **≥ `model_min_goal_distance` 2
   gol** dal punteggio corrente; P presente nella griglia. Poi il **cancello di valore**
   (`omega_model.py:551,560`): `p_implied = (1−c)/(prezzo−c)` e
   **`if p_sel > p_max or p_sel >= p_implied: continue`**, con `p_sel = max(P modello, P
   empirica)` e `p_max = model_p_max_pct` 2 %. Vince la **P più bassa**; fra i pari-P entro
   `select_p_band_ratio` 2,0 vince l'EV (`rank_by_ev`, `omega_model.py:1125`).
7. **Veto empirico** (`_model_select`, `omega_service.py:826-843`): tabella per minuto
   (`omega_minute_transitions`) se c'è, altrimenti veto HT→FT (`get_omega_ht_ft`) entro
   `model_empirical_max_minute` 60'. La P usata è il **limite superiore di Wilson con shrinkage**
   (`omega_empirical.py:32,58`; `Z_UPPER` 1,64, `MIN_GLOBAL_N` 200).
8. **Cappi e piazzamento** (`_size_and_place`, `omega_service.py:1198`):
   `apply_liability_cap` (`omega_engine.py:253`) su `max_liability_per_match`, taglio alla
   liquidità disponibile, poi `max_open_liability`. **Oggi entrambi valgono 0 = spenti**
   (`omega_config.py:34,36,37`), come `daily_loss_cap`.
9. **Uscita**: green-up §12/§19 (`omega_config.py:105-120`), mai sotto l'EV del tenere;
   settlement da Betfair (`settle_open`, `omega_service.py:2580`). Il motore v1
   (`select_lay_runner`, `omega_engine.py:127` = «quota più alta») è in kill-switch
   (`engine='legs'`, `omega_config.py:57`).

### 1.2 Perché su `35760084` Omega non apre — i numeri

Misurato sulla registrazione reale `_live_raw/35760084/35760084.raw.jsonl` (script
`misura_liability.py` nello scratchpad; ladder ricostruita dai `rc` nativi):

| mercato | minuto | punteggio | runner ACTIVE con lay | quote lay |
|---|---|---|---|---|
| HALF_TIME_SCORE | 25' | 1-0 | 7 | 260 · 160 · **20** · 12,5 · 11 · 3,65 · … |
| CORRECT_SCORE | 60' | 3-0 | 5 | 400 · **75** · 13,5 · 5,9 · 1,44 |

- **R2 confermato coi numeri**: dentro `[20,120]` c'è **UN SOLO candidato** per gamba (20 al 25',
  75 al 60'). Il candidato davvero raro (400) è **fuori** `price_max` 120. Con un solo candidato
  decide tutto il cancello `p_sel < p_implied` (`omega_model.py:560`): a quota 75 la soglia è
  `0,95/74,95 = 1,27 %`, mentre la P empirica prudente con **n = 200 e 0 casi** vale
  `z²/(n+z²) = 1,33 %` (`p_upper`, `omega_empirical.py:58`) → **1,33 % > 1,27 %: scartato per sei
  centesimi di punto**. Non è un difetto: è il veto di coda che fa il suo mestiere su un campione
  troppo piccolo.
- **R1 confermato**: `legs_remaining` (`omega_engine.py:893`) su un giorno con UNA partita dà 2;
  `dynamic_target(250, 0, 2) = 125 €`; `lay_size_from_target(125, c=0,05) = 131,58 €`. A quota 75
  servono **131,58 € di controparte**: il book ne ha 55,56 → `insufficient_liquidity`
  (`omega_service.py:1210`) o taglio della size.
- **R3 confermato**: un lay a 300 con 5,26 € impegna 1.572 € di liability (`liability_from_lay`,
  `omega_engine.py:248`) **con tutti i cap a zero**.

> **Le tre cause hanno una radice sola: la size viene dall'obiettivo di giornata.** Con il lay
> fisso a 1 € dell'ordine di stasera R1 e R3 spariscono per costruzione, e resta il problema
> vero: **quale risultato scegliere, e con quale margine**.

## 2. INVENTARIO DELLE FONTI — spietato

Copertura misurata **oggi 16/09 sul DB** (N = **405** fixture in `fixture_predictions`).
«Aiuta» = ha una calibrazione o una misura di affidabilità. Una fonte non calibrata **non aiuta:
aggiunge rumore** — e su una selezione «prendi la P più bassa» il rumore è sistematicamente
dannoso (§3.4).

| # | Fonte | Dove | Cosa dà per un CS / 1T / 2T | Copertura oggi | Calibrazione nota | Affidabilità MISURATA | Verdetto |
|---|---|---|---|---|---|---|---|
| 1 | **Poisson xG-DC** | `fixture_predictions.db_json_analisi` (`markets`, `markets_calibrated`, `inputs.lambda_*`); letto da `omega_db.py:510` e `Betfair/stream/db.py:211` | λ casa/trasferta → griglia CS intera | **132/405 = 32,6 %** | `poisson_calibration` 517 righe, **fresca 15/09**; `dynamic_cal.json` 15/09 (488 leghe); ρ per lega solo su **20** leghe (`dc_rho_by_league.json`), resto ρ = −0,13 | unico predittore con lift su O/U (hit 66,8 % a P≥0,65, n=18.300 — memoria 5motori); **come scommessa ROI −5,3 %** su 2.969 segnali (memoria engines_roi) | **usare come λ**, mai come segnale |
| 2 | **ML ensemble** | `fixture_predictions.model_predictions_json.targets`; registry `ai_model_registry` 20.509 righe (`trained_at` **oggi 07:53**); `ml_post_calibration` 939 righe (**oggi 13:32**) | ~20 mercati binari; **nessun Correct Score** (i target «count»/`exact_score` sono esclusi by-design — memoria ml_leak BUG#3) | **403/405 = 99,5 %** | gate `targets_not_reliable` (BSS<0,12 o ECE>0,10) per mercato e lega | **ROI −8,0 %** su 1.851 segnali; consenso ML+Poisson **−3,5 %** (n=129) | **non entra nella P del CS** |
| 3 | **TacticAI / tactical_engine** | `fixture_predictions.tactical_engine_json` (`tactical_engine/serving.py:189`) | λ att/dif per squadra (DC + simmetria Z₂ + time-decay): è il **primo anello** della catena λ | **31/405 = 7,7 %** | nessuna calibrazione OOS; PoC World Cup «converge, counterfactual OK, **OOS non batte il baseline**» | mai misurato su leghe di club | prior λ quando c'è; copertura troppo bassa per contarci |
| 4 | **Frequenze per minuto** | `omega_minute_transitions` **1.072.786 righe** + `omega_minute_league_counts` 1.185; RPC `get_omega_minute_ft` (`omega_db.py:675`) | P(risultato \| minuto, punteggio) **sulla cella che si banca** | per lega, non per fixture; `built_at` **11/09 → stantia di 5 giorni** | Wilson one-sided + shrinkage verso il globale K=500 (`omega_empirical.py:32`) | non predice: **conta** | **LA FONTE PRINCIPALE** — da ricostruire (§5) |
| 5 | **Frequenze HT→FT** | `omega_ht_ft_transitions` 136.272 righe; RPC `get_omega_ht_ft` (1.548 righe aggregate, `omega_db.py:662`) | P(FT \| HT), solo se il punteggio è ancora quello del 45' | idem, `built_at` **11/09** | idem | condizionamento più povero della 4 | **ripiego** della 4 |
| 6 | **Studio Ritardi** | **nessuna tabella**: RPC `get_market_delays` (`sql/market_delays_rpc.sql:48`) calcolata al volo su `matches` (~1,47 M) | ritardo/media/record per 13 mercati **di lega** — non per partita, non per scoreline | **0 nella pipeline live**: chiamata solo dagli script di certificazione | certificata 1:1 col foglio Excel, **550/550 PASS** (memoria ritardi) | come **filtro di regime**: «molto in ritardo ≥1,6×» è sempre la colonna peggiore (39-56 % contro 66-68 %) | **non è una probabilità**: vale come filtro EVITA |
| 7 | **Frequenze mercati** | RPC `get_market_frequency` (`sql/market_frequency_rpc.sql:40`), usata da `omega_db.py:518` | base-rate di lega per mercato/selezione | per lega | nessuna | duplicato povero della 4 | **ignorare** |
| 8 | **Quote Betfair storiche** | `betfair_market_odds` **158.432 righe**, RPC `get_betfair_full_odds`; **Correct Score con back/lay a 3 livelli** | la P **implicita** storica della stessa cella che bancheremmo | **0/405 oggi**; ultimo `run_date` **11/09** (113 fixture) | — | mai usata per calibrare | **è la chiave per misurare k** (§3.3) |
| 9 | **Direzione** | RPC `get_direction` (`migrations/get_direction_rpc.sql:38`) | concordanza motori + pagella + banda Wilson, per mercato | per fixture | pagella = hit-rate storico | «1X2 solo-Poisson 41 %, 2 motori concordi 53-56 %» | **non serve**: parla di 1X2/O/U, non di scoreline |
| 10 | **Scanner / opportunità** | `safe_strategy_scan` **36 righe, ferme dal 15/09 14:37**; `safe_strategy_opportunities` 60; `live_signals` 52 | il book live e il minuto reale con cui Omega decide | **lo scanner non sta girando oggi** | — | — | **prerequisito operativo**, non una fonte di P |
| 11 | `league_trust_scores.json` | root | peso di fiducia per lega | — | — | `generated_at` **2026-03-30**: stantio di 5 mesi e mezzo | **non usare** |

**Tre verità scomode che l'inventario impone.**

1. **Il Correct Score non lo predice nessun motore del DB**: l'ML non ha il target, TacticAI
   copre il 7,7 %, il Poisson il 32,6 %. Sulla cella esatta il database sa dire solo **frequenze
   storiche** (4-5) e **λ** (1-3). «Usare tutta la dashboard» per il CS significa, in concreto:
   **λ dai motori + frequenza reale della cella + ritardi come filtro EVITA**.
2. **Ogni volta che questi motori sono stati usati come scommessa hanno perso**: −5,3 % / −8,0 %
   / −3,5 % / −6,1 % (`value_betting`), quattro misure indipendenti. Servono come stimatori di λ.
3. **Metà delle fonti è ferma**: Betfair e transizioni dall'11/09, scanner dal 15/09. Un V3 che
   parte stasera gira con dati vecchi di 1-5 giorni, o non gira affatto.

## 3. PROGETTO V3

### 3.1 I mercati — perché HALF_TIME_SCORE e CORRECT_SCORE restano i giusti

L'ordine fissa **lo stake a 1 €**: l'incasso è fisso (0,95 € netti) e l'unica leva è **quanto
raramente si perde**, quindi serve un mercato dove una singola selezione abbia P dell'ordine
dell'1 %. Solo i mercati a **risultato esatto** ce l'hanno. **1T → `HALF_TIME_SCORE`**, regolato
al 45' (esito noto a metà partita: la gamba 2T si sceglie **sapendo** com'è finito il 1T, §3.5);
**2T/FT → `CORRECT_SCORE`**, regolato al 90'.

Scartati: **O/U** (quote 1,1-10 → con 1 € si incassano centesimi, non «spicci»), **HT/FT**
(9 esiti, P minima 2-3 %), **Match Odds** (3 esiti). Il mercato che esprime letteralmente «il
risultato che non si verificherà» è il risultato esatto: si resta lì.

**Estensione da valutare (domanda 3)**: gli aggregati `Any Unquoted Home/Draw/Away`
(`Betfair/omega/tools/replay_registrazioni.py:118`), oggi esclusi (`include_aggregate=false`,
`omega_config.py:30`; scartati anche in `select_by_model` perché `parse_scoreline` dà None,
`omega_model.py:530`). Sono **la coda vera** — da 1-1 al 60', «Any Unquoted Draw» significa 4-4 o
oltre — e la loro P il modello la sa già calcolare come **somma di celle della griglia**.

### 3.2 UNA probabilità per ogni risultato

Per ogni cella (h,a) si calcolano **tre stime** e si usa la **più alta**, non la media: stiamo
cercando il risultato *meno probabile*, e sbagliare per difetto costa la liability intera mentre
sbagliare per eccesso costa solo un'occasione persa.

- **P₁ — modello**: λ dalla catena `_prematch_lambdas` (`omega_service.py:591`) → `residual_grid`
  con `model_lambda_cv` 0,30 (`omega_model.py:300`). Due migliorie:
  (a) **il grado di fiducia della fonte λ entra nel `cv`** (fixture/tactical = alta, `market_grid`
  = media, `live_ou` = bassa): oggi la fonte è solo scritta nell'audit (`audit_block`,
  `omega_model.py:600`) e non cambia nulla;
  (b) **accendere `select_k_se`** (oggi **0**, `omega_config.py:106`): con due stime (modello ∥
  mercato) la P usata diventa **centro + k·SE**, cioè il limite superiore (`uncertainty_p`,
  `omega_model.py:425`).
- **P₂ — frequenza reale della cella**: `omega_minute_transitions` per (lega, bucket 5',
  punteggio corrente, risultato), shrinkage + Wilson one-sided (`omega_empirical.py:32`).
  È l'unico numero **contato**, non modellato.
- **P₃ — implicita di mercato**: `p_implied = (1−c)/(prezzo−c)` (`omega_model.py:551`): non entra
  nella stima, è **il metro** contro cui si misura.

**P_nostra = max(P₁, P₂)** è già la regola di `select_by_model` (`omega_model.py:559`); la novità
è che **P₂ diventa obbligatoria**: niente tabella con `n ≥ n_min` sulla cella → **niente
ingresso**. Oggi, se la tabella manca, il veto sparisce e resta il solo modello
(`omega_service.py:826-843`).

**I ritardi entrano come FILTRO, non come probabilità**: se il mercato di gol della lega è in
regime «molto in ritardo ≥ 1,6×» — l'unica cella misurata come *sempre peggiore* — la partita si
salta. Un numero che nessuno ha calibrato come probabilità non diventa una probabilità solo
perché è nostro.

### 3.3 «Le probabilità dalla nostra parte» — definizione operativa e come si misura k

Con lay 1 € e commissione 5 %, a **qualunque** quota P si vince **0,95 €** se il risultato non
esce e si perde **(P − 1) €** se esce; il pareggio è `p* = 0,95/(P − 0,05)`, **identico** alla
`p_implied` del codice. Ponendo **P_nostra ≤ p_implied / k**:

> **EV per gamba = 0,95 · (1 − 1/k) €, indipendente dalla quota.**

`k` = 1,0 → EV **0,000 €** (è il cancello di oggi, `p_sel >= p_implied → continue`: **margine
zero**) · 1,5 → 0,317 € · **2,0 → 0,475 € (proposto)** · 3,0 → 0,633 € (il mercato dovrebbe
sbagliare di 3×).

È questo il senso matematico di «non mi interessa la quota»: **la quota non cambia l'EV, cambia
solo la varianza.** Per questo il tetto non va tolto, va **riscritto come tetto di liability**
(§4.5).

**k non si decide a tavolino, si misura (Fase K):**
1. `betfair_market_odds` (158.432 righe, CS con back/lay) × risultati veri in `matches`: per ogni
   **secchio di p_implied** (0,2-0,5 % · 0,5-1 % · 1-2 % · 2-5 %) si conta la frequenza **reale**
   di uscita → `k_mercato = p_implied / p_reale` per secchio, con IC di Wilson. È la misura
   diretta del *favourite-longshot bias* sul nostro book.
2. In parallelo, su registrazioni e paper: per ogni cella che Omega avrebbe scelto si registra
   (P₁, P₂, p_implied, esito) → curva di calibrazione **nostra**.
3. Si opera **solo** nei secchi dove l'estremo inferiore dell'IC di `k_mercato` è > 1, con
   `k_soglia = max(2, 1/estremo_inferiore)`. Se nessun secchio supera 1, **il progetto non ha
   edge e va detto** — non compensato alzando il volume.

### 3.4 Perché serve un margine e non basta «la P più bassa»

Scegliere la cella dove la nostra P è più bassa **della** P di mercato seleziona esattamente
le celle dove il nostro errore è più negativo: optimizer's curse al contrario, già misurato tre
volte qui (`value_betting` −6,1 % su 2.733 bet; `engine_signals` −5,3 %/−8,0 %; consenso −3,5 %).
**L'antidoto è strutturale**: (a) P_nostra = limite **superiore** (Wilson/`k_se`), mai il centro;
(b) **due** stime indipendenti entrambe sotto soglia; (c) `n_min` sulla cella; (d) k misurato.
Senza queste quattro, V3 è la quarta ripetizione dello stesso esperimento fallito.

### 3.5 Timing

- **Gamba 1T**: finestra 20'-40' invariata. Prima del 20' la griglia residua è troppo piatta;
  dopo il 40' il book HT si svuota — misurato su `35760084`: a 35' restano **3** runner con lay e
  la quota massima è 18.
- **Gamba 2T**: decisa **dopo il 45'**, finestra **50'-70'** (oggi 50'-80'). Il tetto va
  abbassato: a 80' il CS ha spesso **zero** runner con lay (su `35760084` dal 66' in poi: 0 runner
  ACTIVE con lay; su `35784105` al 90': nessun candidato).
- **Le due gambe restano indipendenti** e la 2T guadagna informazione: P₂ va condizionata sul
  punteggio vero del 45'.
- **Ritentativi**: restano `LEG_RETRY_MAX` (`omega_service.py:1052`). Con lay 1 € il fallimento
  per liquidità sparisce quasi del tutto (§4.2).

### 3.6 Se il risultato bancato diventa raggiungibile (gol), uscite, settlement

Non cambia nulla rispetto al §19 della Costituzione, e **va lasciato com'è**: la memoria
`chiusure_distruggono_valore` (12/09) misura che **tutte e 5 le chiusure automatiche di Omega v2
erano sbagliate** (−42,39 € contro +79,95 € fatti dalle aperture) e che su un lay *la liability è
già impegnata*: chiudere non riduce il rischio preso, lo trasforma in perdita certa.

Con lay 1 €, però, cambia il **motivo** per cui il green-up esisteva: contenere una liability da
200 €. Quella liability ora è piccola per costruzione (§4.5). **Proposta**: `greenup_mode = 'off'`
di default, con **una sola eccezione**, il caso senza ambiguità del trade 84 — quota rotta
rispetto al modello oltre `greenup_model_break_ratio` (`omega_config.py:120`): lì si esce perché
il prezzo è irreale, non perché si ha paura. **Decisione dell'utente** (domanda 4).

**Settlement** invariato, dal mercato Betfair (`settle_open`, `omega_service.py:2580`): HT al 45',
FT al 90'. **Prima di qualunque live va chiuso R9** (chiusura fatta a mano sul sito Betfair mai
riletta): è l'unico reperto aperto che può produrre un back con soldi veri.

## 4. IL RISCHIO, IN NUMERI

Numeri **misurati** sulle 42 registrazioni reali in `_live_raw/` (script `batch_liability.py` e
`batch_esito.py` nello scratchpad), campionando il book al 25' per HALF_TIME_SCORE e al 60' per
CORRECT_SCORE, sui soli runner **ACTIVE** con controparte ≥ 1 €.

### 4.1 Distribuzione delle quote e liability per 1 € di lay

| | HALF_TIME_SCORE (29 partite) | CORRECT_SCORE (30 partite) |
|---|---|---|
| quote lay di tutti i runner — mediana / p75 / p90 / max | 17,0 / 85 / 190 / **900** | 20,0 / 85 / 230 / **980** |
| quota più alta con controparte ≥ 1 € — mediana / max | 240 / 900 | 420 / 980 |
| **liability con 1 € di lay, SENZA tetto** — mediana / max | **239 € / 899 €** | **419 € / 979 €** |
| quota più alta dentro `[20,120]` — mediana / max | 80 / 120 | 80 / 120 |
| **liability dentro `[20,120]`** — mediana / max | **79 € / 119 €** | **79 € / 119 €** |
| candidati in `[20,120]` per partita (media) | 2,1 | 2,6 |
| partite **senza alcun candidato** in banda | **6/29 = 21 %** | **5/30 = 17 %** |

> **Il numero da guardare**: con 1 € di lay e nessun tetto, la gamba tipica rischia **239-419 €
> per incassarne 0,95**. Il rullo compressore non è una metafora: è il rapporto 1 : 250÷440.

### 4.2 Fattibilità di «tutte le partite»

- **Liquidità**: sparisce come vincolo. Serve 1 € di controparte, non 131,58: su tutte le
  registrazioni ogni runner a quota alta aveva `size ≥ 1`. → `min_lay_liquidity` da 5 a **1,0**.
- **Copertura**: **~80 %** delle partite ha almeno un candidato in `[20,120]`; il restante 20 %
  o non ha book o ha solo quote basse. «Su TUTTE le partite» **non è ottenibile al 100 %**: si
  dichiara, non si forza allargando la banda.
- **Volume**: oggi **405** fixture nel DB; l'ultimo giorno Betfair misurato (11/09) ne aveva
  **113**; lo scanner ha `stream_capacity` 720, oggi ne monitora 36 ed è **fermo**. Base
  prudente: **N = 113 partite/giorno → 226 gambe/giorno**.

### 4.3 P&L atteso, code e drawdown — 226 gambe/giorno

Assumendo `k = 2` **dimostrato** (se non lo è, tutto ciò che segue è zero o negativo):

| scenario | liability mediana/gamba | perdite attese/giorno | P&L medio/giorno | giorno **senza** perdite | giorno a 2 perdite | giorno a 4 perdite |
|---|---|---|---|---|---|---|
| **senza tetto** (quota mediana 420) | 419 € | 0,26 | **+107 €** | +215 € (77 % dei giorni) | **−624 €** (~2,6 %) | −1.460 € |
| **banda `[20,120]`** (quota mediana 80) | 79 € | 1,34 | **+107 €** | +215 € (26 %) | +57 € | **−105 €** |

L'EV è **identico** (§3.3): cambia solo la forma della coda. Senza tetto si vince quasi sempre e
ogni tanto si perde metà mese in una sera; in banda si perde spesso e poco.
**Esposizione lorda cumulata in una giornata**: 226 × 79 = **17.854 €** in banda contro
226 × 419 = **94.694 €** senza tetto. Picco simultaneo (stimando ~15 % delle partite in finestra
insieme, ≈ 17 gambe vive): **1.340 €** in banda, **7.100 €** senza tetto.

### 4.4 Ogni quanto esce davvero il risultato scelto — «non lo so», e perché

Dalle 42 registrazioni **non si può misurare**: solo 11 hanno il punteggio HT vero nel sidecar e
1 il FT; zero perdite su 12 casi non dice nulla su un evento all'1 %. **Lo dichiaro come «non lo
so».** La misura esiste solo nel DB: `omega_minute_transitions` (1,07 M righe) e
`omega_ht_ft_transitions` (136 k) — **ferme all'11/09**, da ricostruire.

C'è poi un **limite di risoluzione strutturale**: con 0 casi su n il limite di Wilson vale
`z²/(n+z²)` → **1,33 % con n = 200**, 0,27 % con n = 1.000. Perché una cella a quota P superi il
cancello con margine k servono **n ≥ z²·(k/p_implied − 1)**: **449 a quota 80** con k=2, **678 a
quota 120**, **2.257 a quota 400**. → **I dati non potranno mai certificare le quote altissime**:
questa, non un'opinione, è la ragione per cui un tetto deve restare.

### 4.5 I cap — proposta, decisione dell'utente

Oggi `max_liability_per_match`, `max_open_liability` e `daily_loss_cap` sono **tutti a 0 = spenti**
(`omega_config.py:34,36,37`). Proposta coerente con «spicci davanti al rullo compressore»:

| cap | valore proposto | perché |
|---|---|---|
| **liability per gamba** (nuovo: `max_liability_per_leg`) | **120 €** | equivale a `price_max` 120 con stake 1 €, ma limita la grandezza giusta; sopra 120 i dati non certificano (§4.4) |
| **liability per partita** | **240 €** | due gambe al tetto |
| **liability aperta simultanea** | **2.000 €** | ~1,5× il picco stimato in banda |
| **perdita giornaliera** (`daily_loss_cap`) | **400 €** | ≈ 5 perdite in banda; oltre si smette di APRIRE, le uscite continuano (`certificazione.py:461`) |
| `daily_goal` | **irrilevante in V3** | la size non viene più dall'obiettivo: resta solo come barra di progresso |

> **Decisione dell'utente.** Questi quattro numeri sono suoi. Il progetto misura e propone; non
> mette un tetto dove non c'era senza ordine diretto.

## 5. PIANO DI COSTRUZIONE

### 5.1 File da toccare

| file | intervento |
|---|---|
| `omega_config.py` | nuovi: `stake_mode` ('fisso'\|'obiettivo'), `stake_eur` 1,0, `select_k_margin` (k), `select_k_se` > 0, `empirical_min_n`, `max_liability_per_leg`, `delay_regime_veto`; default cambiati: `min_lay_liquidity` 5→1, `ft_entry_max` 80→70 |
| `omega_model.py` | `select_by_model:479` — il cancello `p_sel >= p_implied` (riga 560) diventa `p_sel >= p_implied / k`; P₂ obbligatoria con `n ≥ empirical_min_n`; opzione aggregati «Any Unquoted» come somma di celle |
| `omega_engine.py` | accanto a `lay_size_from_target:225` una `lay_size_fisso()`; `apply_liability_cap:253` riusata per il nuovo cap di gamba |
| `omega_service.py` | `_scan_event_legs:992` salta `dynamic_target`/`legs_remaining` in `stake_mode='fisso'`; `_model_select:796` veto empirico obbligatorio + filtro ritardi; `_size_and_place:1198` cap per gamba |
| `omega_empirical.py` | invariato (fa già la cosa giusta): serve solo esporre `n` al chiamante |
| **migrazioni** | `omega_models_v5.sql`: ricostruzione di `omega_minute_transitions` / `omega_ht_ft_transitions` (ferme all'11/09) + `omega_calibration_buckets` per la curva k di §3.3 |
| **fuori Omega** | riaccendere il report Betfair (`betfair_full_odds.py`) e lo scanner: senza, V3 non ha né book né frequenze fresche |

### 5.2 Controlli di certificazione nuovi (stile `certificazione.py`)

- **A8** — «due gambe su OGNI partita seguita»: per ogni evento con finestra aperta, o due gambe
  o una riga di skip col motivo (estende A1, `certificazione.py:228`).
- **A9** — «lay esattamente 1,00 €»: nessuna richiesta con size diversa da `stake_eur`, né in
  paper né in live, con parità campo per campo.
- **A10** — «margine k»: per ogni gamba piazzata `p_sel · k ≤ p_implied`, coi numeri nel referto
  (estende A3, `certificazione.py:260`).
- **A11** — «mai sul risultato corrente né su uno raggiungibile senza margine»: distanza ≥ 2 gol
  **e** `p_sel` sotto soglia (estende A2, `certificazione.py:241`).
- **A12** — «P empirica obbligatoria»: nessuna apertura con `n < empirical_min_n`; tabella
  assente → il bot **non apre** (oggi apre col solo modello).
- **C5** — «cap per gamba»: nessuna liability di gamba oltre `max_liability_per_leg`.
- **Falsificazione obbligatoria**: k=1 → A10 rosso; tabella empirica svuotata → A12 rosso;
  stake 1,01 € → A9 rosso. Un controllo che non sa diventare rosso non certifica.

### 5.3 Registrazioni

- **Riferimento** `35760084` (COMPLETE): confronto prima/dopo obbligatorio. Le **altre 41** di
  `_live_raw/` per la copertura (29 col book HT al 25', 30 col CS al 60').
- **Sintetiche da costruire**: (a) cella con `n` empirico sotto soglia → A12; (b) libro con
  **zero** candidati in banda → A8 col motivo; (c) gol che rende raggiungibile il bancato al 55';
  (d) k al limite (`p_sel·k = p_implied ± 1 tick`).
- **§6.6 multi-evento è un prerequisito** (reperto R1): senza, il banco non sa mostrare un giorno
  con più partite.

### 5.4 Stima ore

**K** misura di k su `betfair_market_odds` × `matches` (lo studio che decide se il progetto ha
senso) **4-6 h** · **1** config + stake fisso + cap di gamba **2 h** · **2** selezione con margine
k + P₂ obbligatoria + filtro ritardi **4 h** · **3** migrazione e ricostruzione delle tabelle di
frequenza **2 h** (+ attesa DB) · **4** sette controlli nuovi + falsificazione + sintetiche
**5 h** · **5** replay su `35760084` e le altre + referto **3 h** →
**totale 20-22 h: non è un lavoro da stasera.**

> **Stasera si può fare onestamente solo** la **Fase K** (la misura di k) e la **Fase 1** (stake
> fisso + cap), che da sole chiudono R1 e R3. Il resto, senza la misura di k, sarebbe costruire il
> quarto esperimento identico ai tre che hanno perso.

### 5.5 LE 5 DOMANDE — prima di scrivere codice

1. **Tetto di quota**: «non mi interessa la quota» significa (a) togliere del tutto `price_max`
   — liability mediana **419 €** per 0,95 € di incasso, e nessun dato storico la può certificare
   (§4.4) — oppure (b) sostituirlo con un **tetto di liability per gamba** (proposto 120 €)?
   Il progetto raccomanda (b) con motivo misurato, ma la scelta è sua.
2. **Cap**: confermi i quattro numeri di §4.5 (gamba 120 € · partita 240 € · aperta 2.000 € ·
   perdita giornaliera 400 €) o ne detti altri? Oggi sono **tutti a zero**.
3. **Aggregati**: si banca anche «Any Unquoted Home/Draw/Away» — la coda vera, oggi esclusa — o
   restano solo le scoreline numeriche?
4. **Uscite**: con liability piccola Omega **tiene fino al settlement** (green-up `off`, salvo
   quota rotta), che è quello che dicono i dati del 12/09 — oppure il green-up resta acceso com'è?
5. **Prerequisiti fermi**: report Betfair fermo dall'**11/09**, tabelle di frequenza dall'**11/09**,
   scanner dal **15/09 14:37**. Li riaccendiamo prima (e chi li riaccende), o V3 si progetta
   sapendo che gira con dati vecchi?

---

## 6. Cosa questo progetto NON fa

Non altera la strategia senza ordine (ciò che è «proposto» resta proposto) · non usa
ML/Direzione/Frequenze-mercato come generatori di segnale (quattro misure indipendenti dicono
che perdono, §2) · non promette edge: promette **una misura di k**, e se `k > 1` non è
dimostrato **non fa aprire nulla** · non parla di live: prima replay flumine con dati reali,
poi paper, poi — solo con R9 chiuso — decide l'utente (`PROCESSO_STANDARD_BOT.md` §3-§5).
