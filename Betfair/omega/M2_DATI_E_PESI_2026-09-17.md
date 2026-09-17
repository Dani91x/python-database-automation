# M2 — STUDIO DEI DATI E TARATURA DEI PESI (intensità pre-partita di Omega)

> 17/09/2026, delegato M2. **Sola lettura sul database**: nessuna scrittura, nessun processo
> avviato, nessuna chiamata a Betfair, nessun commit, nessun file del motore di produzione
> toccato (`omega_model.py`, `omega_v3.py`, `omega_engine.py`, `omega_service.py` sono
> intatti). Ogni numero qui sotto è stato **misurato oggi** con il comando riportato accanto;
> quello che non ho potuto misurare sta nel §8, elencato.
>
> **Ordine dell'utente (17/09, h11:30)**: «il bot deve sapere i dati storici: frequenze di
> mercato, ritardi, h2h, dati storici di lega e delle squadre, trovi tutto in dashboard per
> quella specifica partita; deve sfruttare la potenza dei dati che si aggiornano
> automaticamente partita dopo partita; NON sono presenti tutti i dati per tutte le partite,
> quindi studia o fai una simulazione su una partita per tarare i pesi correttamente».
>
> **Vincolo del coordinatore** (`VISIONE_OMEGA_V4_COORDINATORE_2026-09-17.md` §1, §3): la
> consegna produce **(λ_casa, λ_trasferta, cv, fonti_usate, pesi)**. Il `cv` cresce quando le
> fonti mancano; il motore v4 opera sul limite **superiore** di p, quindi meno fonti → più
> prudenza → meno ingressi, **automaticamente**. Le quote devigate sono la fonte più forte; il
> resto entra solo se migliora **fuori campione** con IC che esclude 0.

## Consegna

| file | cos'è |
|---|---|
| `Betfair/omega/tools/m2_pesi.py` | lo strumento riproducibile (5 fasi: `estrai`, `copertura`, `tara`, `simula`, `hazard`) + la funzione di contratto `intensita_prematch` |
| `Betfair/omega/data/pesi_m2_2026-09-17.json` | i pesi, il `cv`, i numeri fuori campione, l'ablazione |
| `Betfair/omega/data/m2_copertura_2026-09-17.json` | la copertura misurata delle fonti |
| `Betfair/omega/data/m2_hazard_2026-09-17.json` | l'hazard di gol per (minuto, punteggio) — input in-play di §3 della visione v4 |
| `Betfair/omega/data/m2_campione_2026-09-17.json.gz`, `m2_righe_2026-09-17.json.gz` | cache del campione (il DB si legge una volta sola) |
| `Betfair/omega/test_m2_pesi_2026_09_17.py` | **22 test di contratto**, ognuno con la sua falsificazione scritta nel docstring |

Comandi (tutti in sola lettura):

```
python -m Betfair.omega.tools.m2_pesi estrai       # scarica il campione una volta sola
python -m Betfair.omega.tools.m2_pesi copertura    # la tabella del paragrafo 1
python -m Betfair.omega.tools.m2_pesi tara         # stima su TRAIN, misura su TEST, bootstrap
#   (la stima e' 700 passi di Nelder-Mead, ~25 min; --stima-nota <json> la riusa e
#    rifa comunque per intero rifit del cv, prova fuori campione, bootstrap, ablazione)
python -m Betfair.omega.tools.m2_pesi simula --fixture 1515877   # evento Betfair 35760084
python -m Betfair.omega.tools.m2_pesi simula --fixture 1548011   # la stessa cosa SENZA fonti
python -m Betfair.omega.tools.m2_pesi hazard       # hazard di gol, dalle transizioni su disco
python -m pytest Betfair/omega/test_m2_pesi_2026_09_17.py -q -p no:cacheprovider
```

---

## 1. INVENTARIO DELLE FONTI PER PARTITA — copertura MISURATA

**Denominatore**: le **14.725 partite giocate con esito** (`status_short` FT/AET/PEN e
`goals_home` non nullo) fra il **20/08 e il 17/09/2026** — le ultime 4 settimane. Di queste,
14.182 hanno anche il punteggio al 45'. Misura: `m2_pesi copertura`, file
`data/m2_copertura_2026-09-17.json`.

| # | Fonte (come la vede la dashboard) | Tabella / RPC | Chiave di join | Copertura 4 settimane | Freschezza — chi la aggiorna e quando | Qualità |
|---|---|---|---|---:|---|---|
| 1 | **Poisson xG-DC** (pannello Poisson) | `fixture_predictions.db_json_analisi` → `inputs.lambda_home/away` (`lib/fixtureModels.ts:68`) | `fixture_id` | **4.183 / 14.725 = 28,4 %** | automatica: GH Actions `today_predictions_backfill` (cron `18 2 * * *` UTC) + `weekly_poisson_calibration` (lun 03:27) | λ per squadra; calibrazione `poisson_calibration` (517 righe) e `dc_rho_by_league.json` solo su 20 leghe |
| 2 | **TacticAI / tactical_engine** | `fixture_predictions.tactical_engine_json` → `lambda_home/away` (`lib/tacticalEngine.ts:56`) | `fixture_id` | **962 / 14.725 = 6,5 %** | **MANUALE**: `tactical_engine/generate_predictions.py` → `serving.py`; **nessun workflow schedulato** | mai calibrata fuori campione |
| 3 | **Percentuali 1X2 di API-Football** (card Predizioni) | `fixture_predictions.percent_home/draw/away` | `fixture_id` | **9.213 / 14.725 = 62,6 %** | automatica, stessa `today_predictions_backfill` | già normalizzate a 100, nessun overround: si devigano da sole |
| 4 | **H2H** (`H2HSection.tsx`) | `fixture_predictions.raw_json.response[0].h2h` | `fixture_id` | **7.438 / 14.725 = 50,5 %** (blocco non vuoto) | automatica, stessa riga | numero di incontri molto variabile; nelle amichevoli quasi sempre vuoto |
| 5 | **Forma e statistiche di lega delle due squadre** | `fixture_predictions.raw_json.response[0].teams.*.league` + calcolabili da `matches` | `fixture_id` / `home_team_id`+`away_team_id` | **1.941 / 1.995 = 97,3 %** nel campione (da `matches`) | automatica: `daily_yesterday_backfill` (cron `12 1 * * *`) su `matches` | la via robusta è `matches`, non `raw_json` |
| 6 | **Forza storica delle squadre** (non è in dashboard: la ricostruisco io) | `matches` (~1,47 M righe) → Maher/Dixon-Coles con decadimento | `league_id`+`home_team_id`+`away_team_id` | **154 leghe su 156** del campione, 5.746 squadre stimate | automatica con `matches` | non esiste oggi nel DB: la stima è dentro `m2_pesi.ForzaSquadre` |
| 7 | **Quote Betfair pre-match** (pannello Quote) | `betfair_market_odds` (158.432 righe), RPC `get_betfair_full_odds(p_fixture_id)` | `fixture_id` | **435 / 14.725 = 3,0 %** | **MANUALE**: `betfair_full_odds.py` (solo eventi di OGGI) e `odds_refresh.py` (pulsante «Aggiorna quote»). **Nessun job schedulato**: ultimo `run_date` = **11/09/2026** | back+lay a 3 livelli su tutti i mercati; è la fonte più forte ed è la meno automatica |
| 8 | **Frequenze per minuto** | `omega_minute_transitions` **1.072.786 righe**, RPC `get_omega_minute_ft(lega,bucket,target)` | `league_id` (non per partita) | per lega | **FERMA**: `built_at` = 11/09/2026 10:49. Vedi §5 | è l'unico numero *contato*, non modellato |
| 9 | **Frequenze HT→FT** | `omega_ht_ft_transitions` **136.272 righe**, RPC `get_omega_ht_ft(lega)` | `league_id` | per lega | **FERMA**: `built_at` = 11/09/2026 09:53 | condizionamento più povero della 8 |
| 10 | **Frequenze di mercato** (pannello Frequenze) | RPC `get_market_frequency(p_league_id, p_market, p_selection, p_line, p_mode, p_last_n, p_season_year)` — `sql/market_frequency_rpc.sql:40` | **`league_id`**, non `fixture_id` | per lega, al volo su `matches` | segue `matches` (automatica) | base-rate di lega: **non** una probabilità della cella del risultato esatto |
| 11 | **Studio Ritardi** (pannello Ritardi) | RPC `get_market_delays(p_league_id, p_market, p_target, p_mode, p_last_n, p_season_year)` — `sql/market_delays_rpc.sql:48` | **`league_id`** | per lega, al volo su `matches` | segue `matches` | **non è una probabilità**: vale come filtro di regime (§8) |
| 12 | **ML ensemble** | `fixture_predictions.model_predictions_json` | `fixture_id` | alta (registry `ai_model_registry` 20.509 righe, retrain cron `19 8 * * *`) | automatica | **non ha il target Correct Score** (escluso by-design): non entra nelle λ |
| 13 | **Direzione** | RPC `get_direction(p_fixture_id)` — `migrations/get_direction_rpc.sql:38` | `fixture_id` | per fixture | segue le sorgenti | parla di 1X2/O-U, non di scoreline: non entra nelle λ |

### Le tre cose che la tabella dice, e che vanno dette

1. **«I dati si aggiornano automaticamente partita dopo partita» è vero solo a metà.**
   Automatiche davvero (GitHub Actions, un cron al giorno): `matches`
   (`daily_yesterday_backfill`, 01:12 UTC), `fixture_predictions` con Poisson e percentuali
   (`today_predictions_backfill`, 02:18), risultati e segnali (`predictions_results_backfill`,
   03:23), calibrazione ML (05:14), retrain (08:19), calibrazione Poisson settimanale (lun
   03:27). **Manuali**: le quote Betfair, TacticAI, e le due tabelle di transizione.
   La fonte **più forte** (il mercato) è quella **meno automatica**: ferma dall'11/09.
2. **La freschezza di `fixture_predictions` è buona ma non garantita.** Sulle 918 partite del
   14-17/09: fra l'ultimo `updated_at` e il calcio d'inizio passano in mediana **7,4 ore**
   (p10 2,0 h, p90 10,6 h) — ma **55 partite su 918 (6,0 %) sono state aggiornate DOPO il
   fischio d'inizio**, cioè per quelle partite in pre-partita la riga non c'era.
3. **Nessuna fonte del database sa dire la probabilità di una cella del risultato esatto.**
   L'ML non ha il target, il Poisson copre il 28 %, TacticAI il 6,5 %. Sul risultato esatto il
   DB sa dire **λ** (fonti 1-3, 5-7) e **frequenze contate** (8-9). È esattamente per questo
   che M2 lavora sulle λ e non su una «probabilità di cella» presa da qualche parte.

### Copertura DENTRO il campione di taratura (dichiarata, perché non è la stessa)

Il campione di taratura è vincolato dalle quote: **2.018 fixture** con quote Betfair
pre-match (24/06 → 11/09/2026), di cui **1.995 con esito**. Su queste:

| fonte | presente | % del campione |
|---|---:|---:|
| mercato (Match Odds back+lay) | 2.018 | 100 % |
| percentuali API-Football | 1.980 | 98,1 % |
| Poisson `db_json_analisi` | 886 | 43,9 % |
| TacticAI | 472 | 23,4 % |
| forma (da `matches`) | 1.941 | 97,3 % |
| h2h (da `matches`, storico dal 01/06/2025) | 1.109 | 55,6 % |
| forza squadre / lega | 154 leghe su 156 | ~99 % |
| **nessuna fonte del DB** (solo mercato) | **33** | 1,7 % |

> **Limite dichiarato**: il campione **non è rappresentativo** della copertura generale —
> TacticAI vale il 23,4 % qui contro il 6,5 % nella popolazione, perché le quote sono state
> catturate nei giorni in cui TacticAI aveva girato. E il **29,4 % del campione (587 partite)
> sono amichevoli di club** (lega 667, luglio): forza e forma valgono meno lì che in
> campionato. Entrambe le cose spingono i pesi delle fonti storiche verso il **basso**: è la
> direzione prudente, non quella comoda.

---

## 2. IL MODELLO DELLE INTENSITÀ PRE-PARTITA

### 2.1 La formula

Per ogni partita si calcolano le λ di **ogni fonte disponibile** e si fondono con un
**pool logaritmico a pesi** (Genest & Zidek 1986; Satopää et al. 2014 — la stessa famiglia già
usata da `omega_v3.fondi_col_mercato`), sulle **sole fonti presenti**:

```
log λ_casa = Σ_s w_s · log λ_casa^(s) / Σ_s w_s          (s = fonti disponibili)
log λ_tras = Σ_s w_s · log λ_tras^(s) / Σ_s w_s
```

Il pool logaritmico, non la media aritmetica: le λ sono grandezze **positive e
moltiplicative** (un errore del 20 % è lo stesso errore a λ 1 e a λ 3), e una media
geometrica pesata non può essere trascinata da una fonte fuori scala come farebbe
l'aritmetica.

La gerarchia bayesiana dell'ordine è **dentro le fonti**, non sopra:

- **prior di lega**: `lega` = media casa/trasferta della lega, stimata su `matches` con
  decadimento esponenziale (emivita 180 giorni). È il livello 0 della gerarchia.
- **forza attacco/difesa** (Maher 1982; Dixon & Coles 1997): `log λ_casa = μ_lega +
  casa_lega + att[casa] + dif[trasferta]`, punto fisso a massima verosimiglianza Poisson con
  pesi a decadimento e **shrinkage verso lo zero di lega** con `PSEUDO_PARTITE = 4`: una
  squadra con 3 partite pesa poco, una con 40 pesa molto. È il livello 1.
- **forma recente**: ultime 6 partite, moltiplicatore (attacco della casa × difesa della
  trasferta) ancorato alla media di lega, con shrinkage `FORMA_K = 4`. Livello 2.
- **h2h**: media dei precedenti della coppia, shrinkata verso la media di lega con
  `H2H_K = 3`. Livello 2.
- **motori del DB**: Poisson `db_json_analisi`, TacticAI, percentuali API-Football
  (devigate con le stesse funzioni della produzione: `total_goals_from_1x2` +
  `split_lambdas_1x2`).
- **mercato**: quote 1X2 Betfair a **metà spread** (mid fra back e lay), devigate e risolte
  con **`omega_model.lambdas_from_pre_ko`**, cioè la funzione della produzione, non una copia
  di laboratorio. È il peso di riferimento, fissato a 1.

### 2.2 L'incertezza dichiarata — la degradazione con grazia

```
cv = cv0 + c_disp · sd_log(fonti) + c_mancanza · (1 − copertura_dei_pesi)
     con cv ∈ [0,10 ; 1,00]
copertura_dei_pesi = Σ w_s (fonti presenti) / Σ w_s (tutte le fonti)
```

Il peso di una fonte mancante **non si redistribuisce in silenzio**: entra nel `cv`. E
`sd_log` è la deviazione standard pesata dei logaritmi dei gol totali attesi fra le fonti:
quando le fonti **litigano**, l'incertezza cresce anche se ci sono tutte.

La catena di conseguenze, che è il punto dell'ordine:

```
meno fonti (o fonti in disaccordo)
   → cv più largo
   → residual_grid con mistura log-normale: coda più grassa (binomiale negativa)
   → p_sup della cella più alto
   → prezzo di riserva L* = (1−c)/(p_sup · k_soglia) + c più BASSO
   → il motore chiede un prezzo migliore e fa MENO ingressi
```

Nessuna soglia scritta a mano, nessun «se mancano i dati salta»: la prudenza è una
conseguenza aritmetica. Due test la fissano
(`test_meno_fonti_piu_incertezza`, `test_piu_incertezza_piu_coda`).

Per chi costruisce v3/v4: `cv` e `forma_gamma` sono lo **stesso numero in due lingue**
(`a = 1/cv²`, perché per una Gamma di media 1 vale `cv = 1/√a`). Helper
`m2_pesi.forma_gamma_da_cv`. Il banco del 16/09 aveva misurato `a` = 6,7-13,3, cioè
cv = 0,27-0,39: il `model_lambda_cv` 0,30 di produzione stava dentro.

---

## 3. LA TARATURA, FUORI CAMPIONE

### 3.1 Il metodo (e perché è fatto così)

Questo repo ha già pagato **tre volte** la maledizione dell'ottimizzatore: `value_betting`
−6,1 % su 2.733 scommesse, `engine_signals` −5,3 %/−8,0 %, consenso −3,5 %. Ogni volta un
numero tarato dove è stato misurato. Qui:

- **split temporale**, non casuale: si stima sulle quote con `run_date < 2026-07-25` e si
  misura su quelle successive. Il buco reale nelle catture (nessuna quota fra il 22/07 e il
  31/08) rende lo stacco netto: nessuna partita a cavallo.
- **metrica**: log-loss multiclasse sulla **cella del risultato esatto** (FT su griglia 9×9 e
  HT su 7×7) — è la cella che Omega banca — più Brier multiclasse e log-loss del totale gol.
- **baseline oneste**: (a) **solo mercato** devigato, (b) **solo `fixture_predictions`**,
  (c) **la catena attuale** di `omega_service._prematch_lambdas` (fixture → pre-KO a prezzi
  back). Ognuna con il **suo** `cv` ottimizzato su TRAIN, se no la fusione vincerebbe solo
  perché ha un parametro in più.
- **bootstrap a grappolo sulle partite** (2.000 giri) sulla **differenza appaiata**: le
  partite sono le unità indipendenti.
- **ablazione**: si toglie una fonte alla volta e si rimisura su TEST. Un peso che non
  migliora con IC che esclude 0 **vale 0** e viene azzerato nel file consegnato.

### 3.2 I numeri

Comando: `python -m Betfair.omega.tools.m2_pesi tara --giri 700 --boot 2000`.
Stima su **1.338** partite (quote con `run_date` fino al 22/07), prova su **657 partite mai
viste** (28/07 - 11/09). Deterministico: stesso punto di partenza, stesso seme del bootstrap.

**Pesi stimati sull'insieme di STIMA** (il mercato e' fissato a 1: nel pool logaritmico conta
solo il rapporto fra i pesi). Obiettivo (log-loss FT + HT) da **5,12706** dei pesi di partenza
a **5,07854**:

| fonte | peso stimato |
|---|---:|
| **mercato** | 1,0000 (riferimento) |
| fixture (Poisson) | 0,1154 |
| forza (Maher/DC) | 0,0905 |
| forma | 0,0683 |
| h2h | 0,0619 |
| tattico (TacticAI) | 0,0541 |
| api (percentuali) | 0,0126 |
| lega (prior) | 0,0000 |

cv: `cv0` 0,0500 · `c_disp` 1,0534 · `c_mancanza` 0,2765.

**Fuori campione, sulle 657 partite mai viste** (la log-loss e' sulla cella del risultato
esatto: piu' bassa e' meglio):

| braccio | n | log-loss CS (FT) | log-loss CS (HT) | Brier FT | coda FT usciti/attesi | coda HT |
|---|---:|---:|---:|---:|---:|---:|
| fusione (tutti i pesi stimati) | 657 | **2,93127** | **2,00819** | **0,92767** | 0,786 | 0,566 |
| **solo mercato** devigato | 657 | 2,93442 | 2,00951 | 0,92778 | 0,763 | 0,511 |
| solo `fixture_predictions` | 223 | 2,95344 | 2,03918 | 0,93054 | 0,833 | 0,969 |
| **catena attuale** `_prematch_lambdas` | 657 | 2,95096 | 2,02316 | 0,92901 | 0,781 | 0,651 |

**Differenze APPAIATE, bootstrap a grappolo sulle partite, 2.000 giri** (negativo = la fusione
e' migliore; il confronto e' sulle partite in comune ai due bracci):

| confronto | differenza log-loss | IC 95 % | verdetto |
|---|---:|---|---|
| fusione - **solo mercato** (FT) | -0,00315 | [-0,01079, **+0,00478**] | **NON migliora**: l'IC contiene 0 |
| fusione - **solo mercato** (HT) | -0,00132 | [-0,00658, **+0,00412**] | **NON migliora** |
| fusione - solo fixture (FT) | -0,07107 | [-0,11856, -0,02831] | migliora |
| fusione - solo fixture (HT) | -0,04169 | [-0,07466, -0,01308] | migliora |
| fusione - **catena attuale** (FT) | **-0,01968** | [-0,03647, **-0,00402**] | **MIGLIORA** |
| fusione - **catena attuale** (HT) | **-0,01496** | [-0,02641, **-0,00408**] | **MIGLIORA** |

**Ablazione - si toglie una fonte alla volta e si rimisura su TEST** (differenza = base meno
senza: negativa significa «la fonte serve»):

| fonte tolta | log-loss FT senza di lei | differenza | IC 95 % | verdetto |
|---|---:|---:|---|---|
| `fixture` | 2,93072 | +0,00055 | [-0,00122, +0,00232] | **peso 0** |
| `tattico` | 2,93090 | +0,00037 | [-0,00019, +0,00100] | **peso 0** |
| `api` | 2,93061 | +0,00066 | [-0,00189, +0,00323] | **peso 0** |
| `forza` | 2,93177 | -0,00050 | [-0,00372, +0,00285] | **peso 0** |
| `forma` | 2,92946 | +0,00182 | [-0,00097, +0,00472] | **peso 0** |
| `h2h` | 2,93105 | +0,00022 | [-0,00156, +0,00191] | **peso 0** |

### 3.3 Il verdetto, senza addolcirlo

> **Nessuna fonte storica del database migliora la stima delle intensita' fuori campione con
> un intervallo di confidenza che escluda lo zero. Il peso e' ZERO per tutte e sei, ed e'
> dichiarato. Le lambda pre-partita di Omega sono le quote devigate del mercato.**

Quattro ablazioni su sei hanno perfino il **segno sbagliato**: togliere la fonte migliora la
metrica, di un'inezia. E' il ritratto esatto del rumore.

Questa e' la **quarta volta** che in questo repo si prova a battere il mercato con i motori di
casa. Le prime tre l'esperimento e' stato dichiarato vincente e poi ha perso soldi: -6,1 % su
2.733 scommesse (`value_betting`), -5,3 %/-8,0 % (`engine_signals`), -3,5 % (consenso). La
memoria `project_calcio_ml_optimizer_curse` chiedeva che la taratura di M2 **non fosse la
quarta ripetizione**: non lo e', perche' questa volta il banco dice **no** prima che ci siano
soldi in gioco. Un peso di 0,1154 sul Poisson «sembrava ragionevole» e avrebbe superato
qualunque revisione a occhio; l'ablazione fuori campione lo azzera.

### 3.4 Le due cose che invece sono VERE, e valgono per il motore

1. **La catena attuale di `_prematch_lambdas` e' misurabilmente peggiore del solo mercato.**
   Differenza **-0,0197** sulla cella FT e **-0,0150** sulla HT, con IC che **esclude lo zero**
   in entrambi i casi. Il motivo e' nell'ordine della catena (`omega_service.py:613`): oggi
   prova **prima** la fixture (TacticAI, poi Poisson) e solo **dopo** le quote pre-KO. Sta
   usando la fonte peggiore mentre ha in mano la migliore. **Invertire l'ordine e' un
   miglioramento misurato**, non un'opinione - ed e' una modifica al motore, quindi la decide
   il coordinatore con l'utente, non io.
2. **`fixture_predictions` da solo e' il peggiore dei quattro bracci** (2,95344 sulle 223
   partite in cui esiste): il Poisson di casa non e' un sostituto del mercato, e' un ripiego.

### 3.5 La calibrazione della coda (dove Omega opera davvero)

La colonna «coda» e' **usciti / attesi** sulle celle a cui il modello da' 2 % o meno:

| braccio | coda FT | coda HT |
|---|---:|---:|
| fusione | 0,786 | 0,566 |
| solo mercato | 0,763 | 0,511 |
| catena attuale | 0,781 | 0,651 |

Tutti sotto 1: il modello **sovrastima** la coda del 21-24 % sul finale e del 35-49 % sul 45-esimo
minuto. E' la direzione **prudente** - stimare la coda piu' grassa del vero significa chiedere un
prezzo migliore e fare meno ingressi, non perdere di nascosto. Va detto pero' che sovrastimare
la coda di un terzo **costa occasioni**: se v4 opera sul limite superiore, questa sovrastima si
somma al `k_soglia` maggiore o uguale a 2 e il cancello diventa molto stretto. E' un numero da
riguardare quando si fissera' `k_soglia`, e va misurato di nuovo sulle quote LIVE, non su queste
pre-match.

### 3.6 Conseguenza: il `cv` va rifittato, e le fonti azzerate restano come RIPIEGO

Due correzioni imposte dal risultato, entrambe applicate:

1. **Il `cv` era stato stimato INSIEME ai pesi.** Azzerarli lo lascerebbe tarato per un modello
   che non esiste piu': con una sola fonte la dispersione e' 0 per costruzione e `cv` sarebbe
   crollato al minimo (0,10) senza che nessuno l'avesse misurato. Lo strumento **rifitta `cv0`
   sui pesi finali**, sull'insieme di stima (`_cv0_ottimo_fusione`).
2. **Peso 0 nella fusione non vuol dire «buttare la fonte».** Quando il mercato **manca**, le
   fonti azzerate sono tutto quello che c'e': entrano come **ripiego** con i pesi
   pre-ablazione, e la **copertura crolla** (il denominatore resta la scala completa, mercato
   incluso), quindi il `cv` si allarga, quindi il motore chiede un prezzo migliore e opera
   meno. E' esattamente la degradazione con grazia chiesta dall'ordine del 17/09, e non un
   ripiego silenzioso: `Intensita.fonti_usate` dice sempre quali fonti hanno parlato. Tre test
   la fissano (`test_ripiego_entra_solo_se_manca_il_peso_misurato`,
   `test_ripiego_e_piu_prudente_del_mercato`,
   `test_mercato_presente_il_ripiego_non_tocca_niente`).

### 3.7 La configurazione FINALE consegnata, misurata

`cv0` rifittato sui pesi finali: **0,05 -> 0,2000** (senza il rifit sarebbe collassato al
minimo 0,10, tarato per un modello che non esiste piu'). Il numero e' vicino al
`model_lambda_cv` 0,30 della produzione e alla forma Gamma misurata dal banco del 16/09
(a = 6,7-13,3, cioe' cv 0,27-0,39): **0,20 corrisponde a `forma_gamma` = 25,0**.

| | pesi | cv | log-loss FT | log-loss HT | Brier FT | coda FT | coda HT |
|---|---|---:|---:|---:|---:|---:|---:|
| **configurazione consegnata** | mercato 1, resto 0 | 0,2000 | **2,93442** | **2,00951** | 0,92778 | 0,763 | 0,511 |

Confronti finali (bootstrap 2.000 giri sulle differenze appaiate, 657 partite):

| confronto | differenza log-loss | IC 95 % | verdetto |
|---|---:|---|---|
| finale - solo mercato (FT) | 0,00000 | [0,00000, 0,00000] | **sono lo stesso modello**, per costruzione |
| finale - catena attuale (FT) | -0,01653 | [-0,03566, **+0,00124**] | migliora, ma l'IC **non** esclude 0: suggestivo, non conclusivo |
| finale - catena attuale (HT) | **-0,01364** | [-0,02748, **-0,00077**] | **MIGLIORA** (IC esclude 0) |

> Onesta' sul punto piu' delicato: con i pesi finali (mercato puro, cv 0,20) il vantaggio
> sulla catena attuale resta **certo solo sulla gamba HT**; sulla FT il segno e' quello giusto
> ma l'IC tocca lo zero (+0,00124). La fusione a pesi pieni batteva la catena anche su FT, ma
> quei pesi l'ablazione li ha azzerati. La lettura corretta e': **la catena attuale non e'
> meglio del mercato, e sulla gamba HT e' peggio in modo misurabile.** Chi tocchera' il motore
> deve sapere questo, non una versione piu' comoda.

**Provenienza del file consegnato.** `data/pesi_m2_2026-09-17.json` porta il campo
`stima_riusata`: `true` significa che i 700 passi di Nelder-Mead non sono stati rifatti in
quella esecuzione (la stima e' deterministica ed era gia' stata prodotta dalla corsa completa,
i cui pesi sono riportati qui sopra riga per riga); **tutto il resto** - rifit del `cv`, prova
fuori campione, bootstrap, ablazione - e' stato ricalcolato per intero. Con
`python -m Betfair.omega.tools.m2_pesi tara` (senza `--stima-nota`) si rifa tutto da zero e si
riottengono gli stessi numeri.

**Il ripiego non e' misurato, ed e' dichiarato.** Nel campione di taratura **tutte** le
partite hanno il mercato (per costruzione: il campione *e'* la tabella delle quote), quindi
**0 su 657** esercitano il ramo di ripiego. I pesi di ripiego sono la stima pre-ablazione,
usati per non lasciare il bot senza lambda: sono una scelta di **prudenza dichiarata**, non
un numero validato. Per validarli serve un campione di partite **senza** quote e **con**
esito, cioe' una misura diversa (e fattibile: le partite ci sono, mancano le quote).

### 3.8 Nota operativa importante: il mercato c'e', anche se la tabella non ce l'ha

La copertura del 3,0 % di `betfair_market_odds` (paragrafo 1) **non** e' la copertura del
mercato per Omega a runtime. Quella tabella e' uno **snapshot storico** popolato a mano. Il
bot, in esercizio, ha le quote da altre due strade che **non passano di li'**:

- `payload.pre_ko` - le quote 1X2 congelate dallo scanner prima del calcio d'inizio
  (`omega_service._prematch_lambdas`, passo 3), disponibili per ogni evento che lo scanner vede;
- il **book live** dello stream, da cui `omega_model.lambdas_from_market_grid` (paragrafo 15.1
  della Costituzione) ricava le lambda dall'intera scala del Correct Score e dalle linee
  Over/Under.

Quindi il verdetto «lambda = mercato» e' **operabile**, non teorico. Il vincolo vero che resta
e' un altro: **le quote storiche servono per MISURARE**, e senza un job che le catturi ogni
giorno nessuna taratura futura (compresa la ri-taratura in gioco) avra' un campione decente.
Oggi quel campione cresce solo quando qualcuno preme un pulsante.

---

## 4. LA SIMULAZIONE SU UNA PARTITA (quella chiesta dall'utente)

L'ordine dell'utente chiedeva di «studiare o fare una simulazione su UNA partita per tarare i
pesi correttamente», e di mostrare cosa succede quando i dati non ci sono. Qui ci sono tre
partite VERE, coi comandi per rifarle.

### 4.1 La partita con TUTTE le fonti — evento Betfair `35760084`

`python -m Betfair.omega.tools.m2_pesi simula --fixture 1515877`
(fixture 1515877 = evento `35760084`, **FK Liepaja v Ogre United**, Virsliga, 30/06/2026;
e' una delle registrazioni `_live_raw` su cui gira il banco del replay.)

**Passo 1 - le fonti trovate, e cosa dice ciascuna:**

| fonte | lambda casa | lambda trasferta | totale | peso misurato | peso di ripiego |
|---|---:|---:|---:|---:|---:|
| **mercato** (mid back/lay, devigato) | 2,678 | 1,014 | **3,692** | **1,000** | - |
| fixture (Poisson xG-DC) | 2,608 | 0,890 | 3,498 | 0,000 | 0,115 |
| tattico (TacticAI) | 2,549 | 0,869 | 3,418 | 0,000 | 0,054 |
| api (percentuali 45/45/10) | 0,903 | 0,297 | **1,200** | 0,000 | 0,013 |
| forza (Maher/DC) | 1,811 | 1,206 | 3,018 | 0,000 | 0,090 |
| forma (ultime 6) | 1,814 | 1,196 | 3,010 | 0,000 | 0,068 |
| h2h | 1,972 | 1,028 | 3,000 | 0,000 | 0,062 |
| lega (prior) | 1,620 | 1,380 | 3,000 | 0,000 | 0,000 |

> Si vede a occhio perche' l'ablazione azzera `api`: le percentuali di API-Football per questa
> partita sono 45/45/10, cioe' un pareggio al 45 %, e la bisezione sui gol totali finisce sul
> **fondo scala** (1,20 gol attesi contro i 3,69 del mercato). Non e' un caso isolato: 348
> righe su 1.980 con le percentuali (17,6 %) vengono scartate a monte perche' il pareggio
> implicito e' fuori da (2 %, 80 %).

**Passo 2 - le lambda fuse e l'incertezza:**

```
lam_casa 2,6777   lam_trasferta 1,0144   totale 3,6922
cv 0,2000   (dispersione fra le fonti 0,0000; copertura dei pesi 100,0 %)
fonti usate: {"mercato": 1.0}
```

Coi pesi misurati la fusione **e'** il mercato: le altre sette fonti restano scritte
nell'audit (il trader le vede) ma non muovono la stima. Il `cv` e' 0,2000 = il `cv0`
rifittato, perche' con una fonte sola la dispersione e' 0 e la copertura e' piena.

**Passo 3 - la griglia pre-partita** (prime celle, su 81):

| cella | P |
|---|---:|
| 2-0 | 9,092 % |
| 2-1 | 8,684 % |
| 1-1 | 7,785 % |
| 3-0 | 7,641 % |
| 3-1 | 7,553 % |
| 1-0 | 6,571 % |

Massa sotto il 2 % per cella: **18,84 %**, distribuita su **66 celle**. E' la coda in cui
Omega lavora.

**Passo 4 - il confronto con le quote Betfair pre-match dello STESSO evento** (Correct Score,
commissione 5 %; `k = p_implicita(lay) / p_nostra`, il margine del cancello):

| cella | lay | p implicita al lay | p equa (mid) | p nostra | k |
|---|---:|---:|---:|---:|---:|
| 2-3 | 100,0 | 0,950 % | 1,333 % | 1,464 % | **0,65x** |
| 0-1 | 48,0 | 1,981 % | 2,604 % | 1,933 % | 1,02x |
| 1-2 | 32,0 | 2,973 % | 3,486 % | 3,290 % | 0,90x |
| 3-2 | 30,0 | 3,172 % | 3,667 % | 3,863 % | 0,82x |
| 0-0 | 40,0 | 2,378 % | 3,250 % | 4,069 % | 0,58x |
| 2-2 | 25,0 | 3,808 % | 4,564 % | 4,292 % | 0,89x |
| 1-0 | 13,5 | 7,063 % | 8,249 % | 6,571 % | **1,07x** |
| 3-1 | 14,5 | 6,574 % | 7,796 % | 7,553 % | 0,87x |
| 3-0 | 13,0 | 7,336 % | 8,846 % | 7,641 % | 0,96x |
| 1-1 | 14,5 | 6,574 % | 7,796 % | 7,785 % | 0,84x |
| 2-1 | 12,0 | 7,950 % | 9,486 % | 8,684 % | 0,92x |
| 2-0 | 11,0 | 8,676 % | 10,101 % | 9,092 % | 0,95x |

**Passo 5 - l'esito vero**: **4-0** (al 45-esimo: 3-0). La nostra P su quella cella era **4,984 %**.

> Il miglior `k` su tutta la scala e' **1,07x**, e serve `k >= 2`. **Omega non aprirebbe
> niente su questa partita in pre-partita** - lo stesso verdetto che il replay V3 del 16/09
> aveva dato dal vivo su questa identica registrazione («miglior margine offerto 0,78x»).
> Due strade diverse, stessa risposta.
>
> Vale la pena confrontare con la stessa simulazione fatta **coi pesi di partenza** (prima
> della taratura): li' la fusione dava lambda 2,241/0,940 e P(0-0) = 8,18 % contro il 3,25 %
> equo del mercato, cioe' un `k` di **0,29x** su quella cella - un errore di 2,5 volte,
> prodotto proprio dal peso dato alle fonti di casa. La taratura non ha solo tolto rumore:
> ha tolto un **errore sistematico** su celle che Omega guarda.

### 4.2 La stessa cosa su una partita SENZA NESSUNA fonte del database

`python -m Betfair.omega.tools.m2_pesi simula --fixture 1548011`
(amichevole di club del 21/07/2026, lega 667: niente Poisson, niente TacticAI, niente
percentuali - una delle **33** partite del campione in quella condizione.)

Coi pesi misurati **non cambia nulla**: l'unica fonte che conta e' il mercato, e il mercato
c'e'. `cv` = 0,2000, identico alla partita ricca. E' un risultato, non una svista: con i pesi
misurati, **avere o non avere i motori di casa non cambia la stima ne' la prudenza**.

### 4.3 La degradazione vera: una partita SENZA MERCATO

`python -m Betfair.omega.tools.m2_pesi simula --fixture 1493129`
(**Huracan v Racing Club**, Liga Profesional Argentina, 14/09/2026: niente quote Betfair -
come il **97 %** delle partite, paragrafo 1.)

| fonte | lambda casa | lambda trasferta | totale | peso di ripiego usato |
|---|---:|---:|---:|---:|
| **mercato** | **ASSENTE** | | | |
| fixture | 1,142 | 0,762 | 1,903 | 0,3695 |
| tattico | 1,044 | 0,852 | 1,896 | 0,1732 |
| forma | 1,149 | 0,642 | 1,791 | 0,2187 |
| h2h | 0,674 | 0,943 | 1,617 | 0,1982 |
| api | 0,903 | 0,297 | 1,200 | 0,0403 |
| forza | **ASSENTE** | | | |
| lega | 1,123 | 0,905 | 2,028 | 0,0000 |

```
lam_casa 1,0044   lam_trasferta 0,7514   totale 1,7558
cv 0,5227   (dispersione 0,1023; copertura dei pesi 22,3 %; RIPIEGO: il mercato manca)
```

**Il `cv` passa da 0,2000 a 0,5227: 2,6 volte piu' largo.** Non e' una soglia scritta a mano:
e' `c_mancanza x (1 - 0,223)` piu' la dispersione fra le cinque fonti superstiti. E questo e'
cio' che il motore v4 ne fa, sulle celle in cui opera (k_soglia = 2, commissione 5 %):

| cella | P con cv 0,20 | P con cv 0,52 | prezzo di riserva L* con 0,20 | L* con 0,52 | rapporto fra le P |
|---|---:|---:|---:|---:|---:|
| 3-3 | 0,2553 % | 0,4571 % | **186,1** | **104,0** | 1,79x |
| 4-2 | 0,2560 % | 0,4582 % | 185,6 | 103,7 | 1,79x |
| 2-4 | 0,1433 % | 0,2564 % | 331,6 | 185,3 | 1,79x |
| 3-2 | 0,9066 % | 1,1436 % | 52,4 | 41,6 | 1,26x |

Sulla cella 3-3 il bot **con** il mercato accetterebbe un lay a 186 o meglio; **senza** il
mercato pretende 104 o meglio. Il book non offre quasi mai 104 su quella cella: il risultato
pratico e' che **la partita senza mercato non produce ingressi**, senza che nessuno abbia
scritto «salta le partite senza quote». La prudenza e' uscita dall'aritmetica.

**Esito vero**: 2-1 (al 45-esimo: 0-0); la nostra P su quella cella era 5,455 %. Niente
confronto con le quote, perche' per questa partita **le quote non esistono nel database** -
ed e' esattamente il punto.

---

## 5. LE TABELLE DI TRANSIZIONE — chi le aggiorna, quanto costa, con che ritmo

**Stato misurato oggi** (sonda in sola lettura su `omega_build_jobs` e `built_at`):

| tabella | righe | `built_at` | come è stata costruita |
|---|---:|---|---|
| `omega_minute_transitions` | 1.072.786 | **11/09/2026 10:49** | `omega_build_minute_transitions_run(90)` a passi; job finito alle **11:16**: **27 minuti**, 1.068.103 righe di `matches` scandite, **939.506 partite valide** contate, `last_id` 1.620.000 |
| `omega_ht_ft_transitions` | 136.272 | **11/09/2026 09:53** | `omega_build_ht_ft_transitions()`, **ricostruzione totale** (`DELETE` + `INSERT` da `matches`) in un'unica istruzione |
| `omega_minute_league_counts` | 1.185 | idem | conteggio partite valide per lega (serve alla potatura delle leghe sotto 1.000 partite) |

**Come sono fatte, e perché questo cambia la proposta.**
`omega_build_minute_transitions_step` (`migrations/omega_models_v3.sql:81`) lavora **un lotto
di `matches.id`** (`p_batch` = 5.000, «~1-2 s per 5.000 con l'indice»), tiene il progresso in
`omega_build_jobs` e — questa è la parte importante — **somma**:
`ON CONFLICT (...) DO UPDATE SET n = omega_minute_transitions.n + EXCLUDED.n`. La tabella si
azzera **solo** quando `last_id = 0`. Quindi **l'aggiornamento incrementale esiste già**: non
serve ricostruire un milione di righe per aggiungere le partite di ieri.

**Quanto costa «partita dopo partita», misurato oggi**: `max(matches.id)` = **1.623.351**,
`last_id` del job = **1.620.000** → **2.848 partite mai contate** (di cui 2.814 con
`status_short = 'FT'`), cioè **un solo lotto** da 5.000: **1-2 secondi** contro i 27 minuti
della costruzione completa. A regime, le partite di un giorno sono ~500: **meno di un
secondo**.

**Cosa manca perché il ritmo sia davvero automatico.** Nessuna funzione oggi riapre il job
quando arrivano partite nuove: `_step` esce subito se `done = true`. La ripresa incrementale è
**due righe di SQL**, che però **nessuno lancia**:

```sql
-- 1) riapri il lavoro sulle sole partite nuove (NON tocca last_id: la tabella e' additiva)
UPDATE public.omega_build_jobs
   SET done = false, max_id = (SELECT max(id) FROM public.matches), updated_at = now()
 WHERE job = 'minute_transitions';
-- 2) lavora (ripetere finche' done = true; con 2.848 partite basta una chiamata)
SELECT public.omega_build_minute_transitions_run(90);
-- controllo
SELECT * FROM public.omega_build_jobs;
```

**Proposta di ritmo (da autorizzare: nessun processo nuovo senza permesso dell'utente).**

| opzione | come | costo | quando |
|---|---|---|---|
| **A — consigliata** | una **migrazione** che aggiunge `omega_build_minute_transitions_catchup()` (le due righe sopra in una funzione) e la schedula con `pg_cron` **una volta al giorno alle 04:00 UTC**, cioè **dopo** `daily_yesterday_backfill` (01:12) e `predictions_results_backfill` (03:23) | **1-2 s/giorno**, ~500 partite, poche migliaia di righe toccate | ogni notte |
| B | la stessa `catchup()` ma lanciata **a mano** dall'utente dall'SQL editor quando gli pare | 1-2 s | quando l'utente vuole |
| C | ricostruzione totale periodica (`_reset()` + `_run`) | **27 minuti**, 1,07 M righe riscritte | solo se i conteggi si corrompono |

Per `omega_ht_ft_transitions` non esiste un percorso incrementale: `omega_build_ht_ft_transitions()`
è una ricostruzione totale in una sola istruzione. Sta dentro il timeout perché legge solo
`matches` (niente join su `match_events`), ma **va eseguita per intero**. Proposta: **una
volta a settimana**, oppure — meglio — **smettere di usarla**: `omega_minute_transitions` con
`target = 'ft'` e `bucket = 45` contiene la stessa informazione condizionata meglio (§2 del
progetto V3, fonte 5 = «ripiego» della 4).

> **Non ho lanciato niente**: né la ricostruzione, né il `catchup`, né `pg_cron`. È una
> proposta; il permesso lo chiede il coordinatore all'utente.
>
> **Difetto dichiarato dell'aggiornamento additivo**: se una riga di `matches` viene
> **corretta** dopo essere già stata contata (punteggio rettificato, gol aggiunto in
> `match_events`), il `catchup` **non** la ricorregge — somma solo le nuove. Con id nuovi per
> le partite nuove il caso è raro, ma esiste, e la difesa è la ricostruzione totale
> periodica (opzione C) o un confronto `processed` contro `count(*)` di `matches` valide.

---

## 6. L'HAZARD DI GOL per (lega, minuto, punteggio) — l'input in-play

Chiesto dal coordinatore (§3 della visione v4). **Costruito senza nessuna lettura nuova**,
dalle 1,07 M transizioni già su disco (`data/transizioni_minuto_2026-09-16.json.gz`).

**Come**: sia `A_h(b,S)` il numero di gol **casa** attesi dallo stato (bucket `b`, punteggio
`S`) alla fine. Con passo `dt = 5/90` di partita e intensità costanti dentro il bucket, la
proprietà della torre dà un sistema **lineare 2×2** in `x = λ_casa·dt`, `y = λ_tras·dt`:

```
A_h(b,S) = x + (1−x−y)·A_h(b+1,S) + x·A_h(b+1,S+casa) + y·A_h(b+1,S+tras)
A_a(b,S) = y + (1−x−y)·A_a(b+1,S) + x·A_a(b+1,S+casa) + y·A_a(b+1,S+tras)
```

Tutti i termini vengono dai conteggi: `A(b,S)` = media pesata di `(risultato − punteggio)` su
`target='ft'`. **Nessun parametro inventato.** Il test
`test_hazard_ritrova_le_intensita_vere` genera conteggi da λ **note** propagando la catena di
Markov in avanti e pretende che la funzione le ritrovi entro 0,05.

**Risultato**: **358 stati** (bucket × punteggio) con n ≥ 300, globale.
Comando: `python -m Betfair.omega.tools.m2_pesi hazard` → `data/m2_hazard_2026-09-17.json`.

| bucket | intensità totale di gol (per 90') | | bucket | intensità totale |
|---|---:|---|---|---:|
| 0'-5' | **1,812** | | 45'-50' | 2,369 |
| 5'-10' | 2,233 | | 50'-55' | 2,804 |
| 10'-15' | 2,292 | | 55'-60' | 2,762 |
| 15'-20' | 2,317 | | 60'-65' | 2,698 |
| 20'-25' | 2,307 | | 65'-70' | 2,694 |
| 25'-30' | 2,337 | | 70'-75' | 2,678 |
| 30'-35' | 2,377 | | 75'-80' | 2,714 |
| 35'-40' | 2,450 | | 80'-85' | **2,779** |
| 40'-45' | *3,594* (contiene il recupero del 1T: intervallo più lungo di 5', non confrontabile) | | | |

**Il profilo è crescente e il fattore è 2,779 / 1,812 = 1,53.** È la conferma indipendente del
`profilo_c1 = 0,41` misurato dal banco dei modelli il 16/09 (`exp(0,41) = 1,51`): due strade
diverse sugli stessi dati danno lo stesso numero. Il profilo di Dixon & Robinson (1998) **è
nei nostri dati**, non è un'assunzione.

Esempi di stati (λ casa / λ trasferta, per 90'):

| stato | λ_casa | λ_tras | n |
|---|---:|---:|---:|
| 0' 0-0 | 1,025 | 0,787 | 939.334 |
| 20' 0-0 | 1,220 | 0,959 | 579.769 |
| 45' 1-0 | 1,359 | 1,027 | 184.250 |
| 60' 1-1 | 1,423 | 1,173 | 110.062 |
| 75' 2-1 | 1,610 | 1,143 | 65.332 |

> **Nota sul segno del «chi è sotto attacca»**: come già visto dal banco del 16/09
> (`beta_squilibrio` negativo), anche qui **chi è avanti ha l'intensità più alta**. Non è un
> paradosso: su dati aggregati chi è avanti è di solito la squadra più forte, e la forza non
> si separa dal comportamento senza condizionare sulle λ della partita. È esattamente il
> motivo per cui l'hazard va usato come **profilo**, moltiplicato per le λ della partita
> (che M2 fornisce), e non come λ assoluta.

**Quello che manca, con il suo costo** (§8 li ripete):

- **effetto del cartellino rosso**: `omega_minute_transitions` non ha la dimensione
  cartellini. Per averlo serve rifare la tabella con una colonna `rossi` partendo da
  `match_events` (`event_type = 'Card'`, `detail = 'Red Card'`): è una **migrazione nuova** +
  una ricostruzione totale (**~30 minuti**, stesso ordine di grandezza della costruzione del
  gol, con un join in più su `match_events`). Non l'ho fatto: è una scrittura sul DB.
- **regime di ritardo**: `get_market_delays` è per lega e calcolata al volo; non è nella
  tabella. Per condizionare l'hazard sul regime serve materializzarlo per (lega, data).
- **shrinkage per lega**: la stima qui è **globale** (`league_id = 0`). Le 60 leghe
  campionate sono già su disco: l'estensione è aritmetica (la stessa formula con
  `shrunk_upper` di `omega_empirical`), ma il numero di stati per lega con n ≥ 300 crolla —
  va misurato prima di prometterlo.

---

## 7. CONSEGNA AL COSTRUTTORE

### 7.1 La firma

```python
from Betfair.omega.tools.m2_pesi import intensita_prematch, Intensita, carica_pesi

lam_casa, lam_tras, cv, fonti_usate, pesi = intensita_prematch(evento)
# None  =>  nessuna fonte, nemmeno di ripiego: si SALTA la partita (mai a occhi chiusi)

# i pesi si leggono una volta sola e si passano espliciti (la funzione resta pura):
pesi, cv, pesi_ripiego = carica_pesi()          # da data/pesi_m2_2026-09-17.json
intensita_prematch(evento, pesi=pesi, cv=cv, pesi_ripiego=pesi_ripiego)
```

`fonti_usate` dice **sempre** quali fonti hanno parlato: se non contiene `"mercato"`, la
stima e' arrivata dal **ripiego** e il `cv` e' gia' piu' largo di conseguenza. Non serve un
flag a parte, e non c'e' modo che la degradazione passi inosservata nell'audit.

`evento` è un dizionario con **le chiavi vere delle tabelle**, tutte facoltative:

| chiave | contenuto | da dove |
|---|---|---|
| `fixture_predictions` | la riga così come la restituisce PostgREST: `db_json_analisi` (dict **o** stringa JSON) con `inputs.lambda_home/lambda_away`, `tactical_engine_json` con `lambda_home/lambda_away`, `percent_home/percent_draw/percent_away` | `fixture_predictions` |
| `quote_1x2` | `{"back_home","lay_home","back_away","lay_away","back_draw","lay_draw"}` | `betfair_market_odds`, mercato `Match Odds`, `sort_priority` 1=casa 2=trasferta 3=pareggio |
| `pre_ko` | `{"home","draw","away"}` (prezzi back) — usato **solo se** `quote_1x2` manca | `payload.pre_ko` dello scanner, come oggi in `_prematch_lambdas` passo 3 |
| `storico` | `{"forza":[λh,λa], "forma":[λh,λa], "h2h":[λh,λa], "lega":[λh,λa]}` | `m2_pesi.ForzaSquadre` e `m2_pesi.Storico` su `matches` |

Ritorna una `NamedTuple` `Intensita`, quindi si spacchetta come 5-upla **e** ha i campi
`lam_casa`, `lam_trasferta`, `cv`, `fonti_usate`, `pesi`. `pesi` sono i pesi **effettivamente
usati**, già normalizzati a 1 sulle fonti presenti: è il blocco di audit da scrivere accanto
alla gamba, come `omega_model.audit_block` fa oggi con `lambda_source`.

La funzione è **pura**: niente rete, niente database, niente orologio
(`test_intensita_prematch_e_pura`).

### 7.2 Dove si innesta (indicazione, non modifica: il motore non l'ho toccato)

`omega_service._prematch_lambdas` (riga ~613) oggi è una **catena a cascata**: prende la prima
fonte che risponde e butta via le altre. La sostituzione naturale è: raccogliere **tutte** le
fonti nel dizionario `evento`, chiamare `intensita_prematch`, e passare il `cv` restituito a
`omega_model.residual_grid` / `omega_v3.griglia_finale` **al posto** del `model_lambda_cv`
fisso 0,30. La catena resta come **ripiego**: se `intensita_prematch` torna `None` si fa
esattamente quello che si fa oggi.

### 7.3 I test di contratto (22, tutti falsificati)

`Betfair/omega/test_m2_pesi_2026_09_17.py` — `python -m pytest Betfair/omega/test_m2_pesi_2026_09_17.py -q -p no:cacheprovider`

| test | cosa fissa | come diventa rosso |
|---|---|---|
| `test_fonti_da_evento_legge_le_chiavi_vere` | legge `db_json_analisi.inputs.lambda_home`, `tactical_engine_json.lambda_home`, `percent_home/draw/away`, `back`/`lay` | togliendo `inputs` la fonte `fixture` sparisce |
| **`test_camelcase_non_viene_letto`** | **la lezione del 15/09**: `lambdaHome` **non** è la chiave vera e non deve essere letta | se il lettore accettasse il camelCase |
| `test_db_json_analisi_come_stringa_json` | PostgREST può dare il JSONB già decodificato o come stringa | senza `_json` la stringa non viene letta |
| `test_pool_logaritmico_e_media_geometrica_pesata` | il numero esatto: pesi 1 e 3 su λ 1 e 2 → `2^0,75` | con la media aritmetica (1,75) è rosso |
| `test_peso_zero_non_entra_nella_fusione` | peso 0 = fonte esclusa, non «quasi esclusa» | se entrasse, `fonti_usate` la conterrebbe |
| `test_nessuna_fonte_torna_none` | nessuna fonte = si salta, mai λ di comodo | un ritorno con λ inventate |
| `test_meno_fonti_piu_incertezza` | **la degradazione con grazia** | con `c_mancanza = 0` i due cv coincidono |
| `test_piu_incertezza_piu_coda` | la conseguenza che il motore usa | se `residual_grid` ignorasse il cv |
| `test_fonti_in_disaccordo_alzano_il_cv` | il disaccordo è incertezza | con `c_disp = 0` |
| `test_intensita_prematch_si_spacchetta_in_cinque` | **la firma promessa** | cambiando l'ordine dei campi |
| `test_intensita_prematch_e_pura` | niente I/O | aggiungendo una chiamata al DB |
| **`test_falsificazione_peso_invertito_peggiora`** | **il banco sa diventare rosso**: spostando il peso dalla fonte vera a una di rumore, log-loss e Brier fuori campione **peggiorano** | invertendo il verso dell'assert |
| `test_bootstrap_dichiara_quando_non_migliora` | bracci identici → differenza 0, IC degenere | se il bootstrap ricampionasse le righe invece delle differenze appaiate |
| `test_hazard_ritrova_le_intensita_vere` | il sistema 2×2 **ritrova** le λ che hanno generato i conteggi | con la differenza grezza `A(b)−A(b+1)` l'errore supera il 5 % |
| `test_hazard_stati_troppo_rari_non_entrano` | sotto `n_min` è «non lo so», non un numero | abbassando la soglia |
| `test_forza_ignora_le_partite_dopo_il_taglio` | **niente leakage temporale** | togliendo il filtro `fixture_date < taglio` |
| `test_forma_e_h2h_non_guardano_la_partita_stessa` | idem, forma e h2h | con `<=` invece di `<` |
| `test_forma_gamma_e_il_cv_detto_in_gamma` | `a = 1/cv²` | con `a = 1/cv` |
| `test_file_dei_pesi_ha_il_contratto` | il file consegnato ha la forma promessa | cambiando la scala di riferimento |
| `test_ripiego_entra_solo_se_manca_il_peso_misurato` | senza mercato si usa il ripiego invece di saltare | senza `pesi_ripiego` la fusione torna `None` |
| `test_ripiego_e_piu_prudente_del_mercato` | **il ripiego ha sempre un `cv` piu' largo** | se la copertura fosse calcolata sulla sola scala del ripiego varrebbe 1 |
| `test_mercato_presente_il_ripiego_non_tocca_niente` | col mercato presente il ripiego non entra | se entrasse, le λ non sarebbero piu' quelle del mercato |

---

## 8. LIMITI DICHIARATI E COSA NON HO POTUTO MISURARE

### Quello che il campione NON permette di dire

1. **Il campione è quello che le quote permettono.** 2.018 fixture con quote Betfair
   pre-match (24/06 → 11/09/2026), 1.995 con esito: il **3,0 %** delle partite giocate nelle
   ultime 4 settimane. E non è un campione casuale: sono i giorni in cui **qualcuno ha premuto
   «Aggiorna quote»**. Tutto ciò che dico sui pesi vale, per costruzione, su quel campione.
2. **Le quote sono PRE-MATCH.** Il peso del mercato **in gioco** — quando il book conosce il
   punteggio, e anche noi — non è misurato qui. Va rimisurato sulle registrazioni `_live_raw`
   con gli esiti (lavoro di M1/M3). Quello che consegno è il **prior del pre-partita**.
3. **La composizione dei due insiemi è diversa.** Stima: 1.338 partite (24/06-22/07), di cui
   **507 amichevoli di club (37,9 %)**, 65 leghe. Prova: 657 partite (28/07-11/09), di cui
   **80 amichevoli (12,2 %)**, 132 leghe. È una prova più severa — il che va bene — ma dei
   pesi tarati sul luglio delle amichevoli non sono automaticamente quelli del campionato.
   **Da rifare** quando ci saranno 4-6 settimane di quote di CAMPIONATO.
4. **La forza delle squadre è congelata al taglio dell'insieme.** Per l'insieme di prova è
   stimata su partite anteriori al **25/07**: per una partita dell'11/09 è vecchia di 48
   giorni. È la difesa contro il leakage temporale, ma **penalizza `forza`**: il suo peso
   misurato è un **limite inferiore**. Rifittarla a ogni data costa (il fit è ~1 minuto per
   taglio) ed è la prima cosa da migliorare.
5. **Lo storico parte dal 01/06/2025** (53.201 partite nelle 156 leghe coinvolte). Il 55,5 %
   di copertura h2h è perciò un **limite inferiore**: con 3-5 stagioni salirebbe.
6. **ρ di Dixon-Coles fisso a −0,13** per tutte le leghe (`dc_rho_by_league.json` ne copre
   20). Non l'ho rifittato: il banco del 16/09 aveva misurato ρ −0,015/−0,031 su dati
   aggregati e concluso «tenerlo, non gonfiarlo». Resta un parametro non mio.

### Quello che NON ho misurato, e che qualcuno dovrà misurare

7. **Ritardi e frequenze di mercato non entrano nelle λ, e il loro valore come FILTRO non
   l'ho misurato.** Sono per **lega**, non per partita, e non sono probabilità di una cella
   del risultato esatto. Per usarli serve un esperimento **diverso**: esito binario
   condizionato al regime («molto in ritardo ≥ 1,6×» contro il resto), con il suo split
   temporale e il suo bootstrap. Dichiarato come **non fatto**.
8. **ML ensemble (`model_predictions_json`) e Direzione (`get_direction`) non entrano** e non
   li ho misurati: il primo **non ha il target Correct Score** (escluso by-design, memoria
   `ml_leak` BUG#3), il secondo parla di 1X2 e Over/Under. Non producono λ.
9. **`ht_predictions.lambda_1h` non è una fonte separata**: viene dalla stessa riga Poisson
   (copertura identica, 4.183 = 28,4 %) e l'informazione è ridondante rispetto a `fixture`.
10. **La latenza operativa.** Ho misurato `updated_at` contro il **calcio d'inizio**, non
    contro il momento in cui il bot decide. Per Omega, che entra al 20'-40' e al 50'-70', la
    domanda giusta è «la riga c'era quando ho deciso?»: quella misura va fatta sul replay.
11. **I conteggi totali di `matches` e `fixture_predictions`**: `count=exact` va in timeout su
    quelle tabelle (errore 500 del gateway). Ho sempre lavorato per **finestre temporali**;
    i numeri di §1 sono esatti sulla finestra, non sull'intera tabella.

### Due reperti tecnici che vanno oltre M2

12. **Difetto di paginazione, trovato e corretto qui, da controllare altrove.** PostgREST con
    `range(offset, offset+n)` e un ordine **non totale** salta e duplica righe **in silenzio**:
    ordinando le quote per `run_date` ho letto **2.003** fixture invece di **2.018** (−0,7 %).
    Corretto nel mio strumento imponendo un ordine totale (`fixture_id` + `selection`).
    **Verifica fatta su `tools/estrai_transizioni.py`** (ordina per `bucket, score, result`
    mentre la chiave primaria ha anche `target`): le **22.193** righe globali del file
    coincidono **bucket per bucket** con la tabella, quindi lì il difetto non si è
    manifestato — ma il rischio è **latente** e una passata su tutti i lettori paginati del
    repo se la merita.
13. **Il costo vero della catena di produzione.** `omega_model.total_goals_from_1x2` +
    `split_lambdas_1x2` costano **0,294 s per partita** (30 bisezioni × 42 griglie 11×11,
    misurato): costruire le λ di mercato per 2.018 partite × 3 varianti ha richiesto **25
    minuti**. In pre-partita, una volta per evento, è irrilevante; ma è il motivo per cui
    `_poisson_grid` è stata memoizzata il 16/09, e va tenuto a mente se qualcuno pensa di
    rifare il fit di mercato **a ogni tick** in gioco.


---

## 9. COSA SERVE DECIDERE (il coordinatore lo porta all'utente: io non ho lanciato niente)

| # | cosa | perche' | costo |
|---|---|---|---|
| 1 | **Un job che catturi le quote Betfair ogni giorno** (`betfair_full_odds.py` e' gia' scritto: manca solo qualcuno che lo lanci). | E' la fonte **unica** che ha superato la prova fuori campione, e il suo storico e' fermo all'11/09. Senza, nessuna taratura futura - compresa quella **in gioco**, che e' quella che conta per v4 - avra' un campione. | una chiamata REST al giorno sugli eventi di oggi; nessun processo nuovo se lo si aggancia a un job esistente |
| 2 | **`omega_build_minute_transitions_catchup()`** + `pg_cron` giornaliero alle 04:00 UTC (paragrafo 5, opzione A). | Le transizioni sono ferme all'11/09 e l'aggiornamento incrementale costa **1-2 secondi**, non 27 minuti. E' letteralmente «i dati che si aggiornano partita dopo partita» chiesti dall'utente. | 1 migrazione + 1-2 s al giorno |
| 3 | **Invertire l'ordine della catena in `omega_service._prematch_lambdas`**: prima le quote, poi la fixture. | Misurato: la catena di oggi e' peggiore del mercato sulla gamba HT con IC che esclude 0 (paragrafo 3.4). E' una modifica al **motore**, quindi non la faccio io. | una riga di ordine + il replay di conferma |
| 4 | **Se e quando rifare la taratura**: con 4-6 settimane di quote di CAMPIONATO (non di amichevoli estive) e, soprattutto, con le quote **in gioco**. | Il peso del mercato live non e' misurato qui, e il campione attuale e' per il 29 % amichevoli. | rilanciare `m2_pesi estrai` + `tara` |
| 5 | **La dimensione «rossi» nelle transizioni**, se si vuole l'hazard condizionato ai cartellini (paragrafo 6). | Oggi l'hazard non sa nulla dei rossi, che sono l'evento che piu' cambia le intensita'. | 1 migrazione + una ricostruzione totale (~30 min) |

## 10. FIRMA DEL LAVORO

- **Nessuna scrittura sul database**, nessun processo avviato, nessuna chiamata a Betfair,
  nessun commit, nessun `git add`. Verificato con `git status --porcelain`: gli unici file
  nuovi sono `Betfair/omega/M2_DATI_E_PESI_2026-09-17.md`,
  `Betfair/omega/tools/m2_pesi.py`, `Betfair/omega/test_m2_pesi_2026_09_17.py` e i file
  `Betfair/omega/data/m2_*` e `pesi_m2_*`. **`omega_model.py`, `omega_v3.py`,
  `omega_engine.py`, `omega_service.py` non sono stati toccati.**
- Test: `python -m pytest Betfair/omega/test_m2_pesi_2026_09_17.py -q -p no:cacheprovider`
  -> **22 verdi**. Ognuno ha la sua falsificazione scritta nel docstring; le tre piu'
  importanti (camelCase, peso invertito, hazard) sono state **rese rosse davvero** durante la
  costruzione, non solo immaginate.
- Le funzioni della produzione usate (`omega_model.lambdas_from_pre_ko`,
  `total_goals_from_1x2`, `split_lambdas_1x2`, `residual_grid`, `ht_residual_share`) sono
  quelle vere, importate, **non ricopiate in laboratorio**.
