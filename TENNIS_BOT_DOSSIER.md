# TENNIS BOT — DOSSIER COMPLETO (Alpha Score)

> Documento di handoff **esaustivo** sulla sezione Tennis: strategie, fonti dati, logica,
> dove sta il codice e **perché è scritto così**, registrazioni storiche, backtest/validazione,
> motore live, database, frontend, e la **verità onesta sull'edge**.
>
> Obiettivo del documento: un altro agente (o persona) deve poter capire **all'istante**
> cosa abbiamo costruito, da quali fonti, quante e quali strategie, e con quale metodo le
> abbiamo provate. **Nulla è omesso.** Data: 08/07/2026. Branch: `feat/tennis-section`.
>
> ⚠️ **Le fonti sono in fondo (§16) e citate inline.** Sono parte fondamentale del documento.

---

## 0. Indice

1. Obiettivo del progetto + verità sull'edge
2. Architettura complessiva (diagramma) + principio single-stream + separazione dal calcio
3. FONTI DATI (Stream API prezzi · InPlayService punteggi · librerie · feed terzi)
4. LE STRATEGIE (5 armabili + motore Lab, ~1100 combo testate, 9 famiglie)
5. REGISTRAZIONI STORICHE (dove, come eseguite, formato, perché)
6. BACKTEST / VALIDAZIONE (harness, metrica LOCKED, golden-rule, VERDETTO) + **6.6 storia bug** + **6.7 cronologia**
7. MOTORE LIVE costruito (backend dedicato `tennis_live`)
8. DATABASE (migrazioni `tennis_*`, RPC, RLS, realtime)
9. FRONTEND (3 screen + `lib/tennis.ts` + riuso `LadderView`)
10. SEPARAZIONE TENNIS ↔ CALCIO (garanzia)
11. STATO ATTUALE + code-review + cosa manca
12. COME RIPRODURRE TUTTO (comandi end-to-end)
13. MAPPA FILE (dove sta ogni cosa)
14. GLOSSARIO
15. NOTE ONESTE
16. **FONTI (bibliografia completa)**

---

## 1. Obiettivo del progetto + verità sull'edge

**Obiettivo dichiarato:** costruire uno strumento di trading tennis su **Betfair Exchange**
di livello professionale (parità con Bet Angel / Geeks Toy / Fairbot / Cymatic / Betting
Toolkit), con **bot armabili** (esecuzione automatica) e un **terminale** per il trading
manuale + supervisione, alimentato **solo** da dati Betfair via backend (credenziali mai nel
browser).

**Verità onesta sull'edge (fondamentale, non ometterla mai):**
Dopo una campagna esaustiva (vedi §6) — **~1100 combinazioni** su **9 famiglie di strategie**,
con harness **validato** (golden-rule), fill/coda/bet-delay **reali** e split **train/test** —
**NON è emerso alcun edge meccanico robusto sul tennis in-play (mercato MATCH_ODDS).**
Il "muro" ricorrente è lo **spread**: il movimento di prezzo predicibile è ~= allo spread, quindi
il taker perde e il maker reale è adverse-selected (~5% di fill). L'unica tesi con **struttura**
è **FLB** (lay del favorito estremo, no-stop: liability minuscola vs crollo del quasi-certo), ma
è validata solo su pochi match ed è comunque **direzionale** (locked<0), non garantita.

→ Conseguenza operativa: **il valore reale del sistema è come cockpit di esecuzione/controllo
umano e come banco di prova per cercare un edge**, non come autopilota da accendere e
lasciar girare. Ogni operatività reale va tenuta in **dry-run/PAPER** finché una strategia non
regge su un campione grande. (Fonte interna: memoria `project_tennis_pro_bot_2026-07-06`, §6.)

---

## 2. Architettura complessiva

**Principio 1 — fonti dati ottimizzate al massimo (nessun feed doppio/triplo).**
Per ogni evento seguito c'è **UNA sola sottoscrizione Betfair Stream** (flumine). Da quell'unico
stream derivano tutte le proiezioni, e **i bot girano DENTRO lo stesso stream** (non aprono
sottoscrizioni proprie). L'unica chiamata REST aggiuntiva è **un** poll `get_scores` per evento
(punteggio). Verificato contro `flumine==2.13.11` in code-review.

**Principio 2 — il browser non tocca mai Betfair.** Il frontend legge **solo** Supabase
(RPC + Realtime, anon key). I worker Python locali (con le credenziali Betfair) parlano con
Betfair e scrivono su Supabase. Il browser non vede mai segreti.

**Principio 3 — separazione totale dal calcio.** Tabelle, RPC, worker, componenti: tutto
`tennis_*` **dedicato**. Nessun accesso a tabelle del calcio (§10).

```
   BETFAIR                          RUNNER LOCALE (PC)                 SUPABASE            BROWSER
 ┌──────────────┐   Stream API    ┌───────────────────────┐  upsert  ┌────────────┐  RT ┌──────────┐
 │ Exchange     │───prezzi/ladder►│ tennis_runner.py      │─────────►│ tennis_    │────►│ Screen 3 │
 │ Stream API   │   (1 subscr/ev) │  · ladder_worker      │          │ live_ladder│     │ Ladder   │
 │ (prezzi)     │                 │  · score+now worker   │          │ tennis_    │────►│ Screen 3 │
 └──────────────┘                 │  · HOSTA i BOT (stesso│          │ live_now   │     │ Stats    │
 ┌──────────────┐   REST poll ~2s │    stream, no doppie) │          │ tennis_bot_│◄───►│ Screen 3 │
 │ InPlayService│───punteggio────►│  · order client OFF/  │          │ control    │     │ BotPanel │
 │ get_scores   │   (IPS)         │    PAPER/LIVE         │          └────────────┘     └──────────┘
 └──────────────┘                 └───────────────────────┘  upsert  ┌────────────┐  RPC┌──────────┐
 ┌──────────────┐   REST snapshot ┌───────────────────────┐─────────►│ tennis_    │────►│ Screen 2 │
 │ listMarket*  │───catalogo+book►│ betfair_tennis_odds.py│          │ markets    │     │ Partite  │
 │ (odds giorno)│                 └───────────────────────┘          └────────────┘     └──────────┘
                                  ┌───────────────────────┐  drena   ┌────────────┐
                                  │ tennis_live_order_    │◄─────────│ tennis_live│◄─── ordini manuali
                                  │ worker.py (ordini)    │          │ _order_    │     (ladder Screen 3)
                                  └───────────────────────┘          │ queue      │
                                                                     └────────────┘
```

---

## 3. FONTI DATI (dettaglio massimo)

### 3.1 Betfair Exchange **Stream API** — PREZZI / LADDER (NON punteggi)
- **Cosa fornisce:** push a bassa latenza di **mercato/prezzi/ordini**: `atb`/`atl` (available-to-back/lay),
  `trd` (volume tradato per prezzo, **cumulativo**), `ltp`, `tv` (total matched), `marketDefinition`
  (con `eventTypeId`, `marketType`, `inPlay`, `status`, **`betDelay`**, `runners[{id,status,sortPriority}]`).
- **Cosa NON fornisce:** **nessun punteggio/statistica**. Lo Stream è solo dati di mercato.
- **Come lo usiamo:** una `MarketSubscription` flumine per evento (`streaming_market_filter(market_ids=[...])`),
  filtro dati `EX_ALL_OFFERS + EX_TRADED + EX_TRADED_VOL + EX_LTP + EX_MARKET_DEF`, `ladder_levels=10`.
- **Perché:** best practice Betfair = usare lo Stream (push) per prezzi in-play, non il polling
  (Fonte: [Betfair Best Practice], [optimise API performance] §16). Un solo stream = zero doppioni.

### 3.2 Betfair **InPlayService (IPS)** — PUNTEGGIO / STATISTICHE
- **È un servizio REST separato** (`https://ips.betfair.com/inplayservice/v1.1/...`), **solo polling,
  nessun push**. Verificato leggendo il sorgente di `betfairlightweight` ([inplayservice.py] §16):
  espone **3 metodi, tutti GET**:
  - `get_scores(event_ids, lightweight)` → `.../scores` ← **quello che usiamo**
  - `get_event_timeline(event_id, ...)` → `.../eventTimeline` (cronologia eventi, più ricca — comunque poll)
  - `get_event_timelines(event_ids, ...)` → `.../eventTimelines`
- **Campi restituiti da `get_scores` (per giocatore `home`/`away`):** `name`, `score` (punto: `0/15/30/40/A`
  o numero tie-break), `games`, `sets`, `gameSequence` (storico game per set, es. `["6","3"]`),
  `isServing` (chi serve), `serviceBreaks`, `highlight`. A livello match: `currentSet`, `currentGame`,
  `fullTimeElapsed`, `status` (matchStatus). Schema completo → §5 e `tennis_score.py`.
- **Cadenza:** poll **default 2.0s** (nostra scelta, non un limite — vedi sotto). Non è push.
- **Chi calcola cosa:** la **win-probability** (`p_match`) la calcoliamo **noi** (modello Markov
  `tennis_winprob.py`), NON viene da Betfair.
- **Limiti reali (importante):**
  - Rate limit Betfair: **1.000 req/min** (free) / **5.000** (paid) — una `get_scores` copre più eventi
    in una chiamata (lista `event_ids`), quindi a 2s siamo a ~30 chiamate/min. **Si può scendere a ~1s**
    senza problemi. (Fonte: [data/request limits] §16.)
  - Il vero pavimento **non è il nostro poll** ma la **latenza a monte** del feed punteggi Betfair
    (provider → Betfair → IPS, alcuni secondi) + il **ritardo in-play** dei mercati (1–12s).
  - **Copertura:** Betfair ha **rimosso le WTA** dal feed punteggi (cambio fornitore), **ATP resta**,
    **ITF** è discontinuo → sui tornei minori il punteggio può mancare. Il parser ritorna `None`
    → sistema **fail-safe** (i bot score-driven non entrano). (Fonti: [forum tennis score], [Bet Angel WTA] §16.)
- **Real-time "vero" (sub-secondo, per-punto):** NON esiste da Betfair (nessuno stream punteggi).
  Richiederebbe un **feed terzo licenziato** — Sportradar, **Tennis Data Innovations (TDI, dati ufficiali
  ATP/WTA)**, Genius Sports — da scrivere in `tennis_live_now.score` al posto/oltre l'IPS. Scelta di
  costo/licenza, non ancora fatta.

### 3.3 Librerie
- **`betfairlightweight`** (betcode-org): client REST (login cert, `listEvents`/`listMarketCatalogue`/
  `listMarketBook`/`placeOrders`) + `in_play_service`. ([repo] §16.)
- **`flumine==2.13.11`**: framework di trading su stream (strategie `BaseStrategy`, `BackgroundWorker`,
  `FlumineSimulation` per backtest, `SimulatedMiddleware`). Le strategie tennis sono flumine.

### 3.4 Odds del giorno (Screen 2) — snapshot REST
- `betfair_tennis_odds.py`: `list_events(["2"])` (tennis) → per evento `listMarketCatalogue` (TUTTI i
  market type) + `listMarketBook` (`EX_BEST_OFFERS + EX_TRADED_VOLUME`) → riga TennisFixtureRow →
  upsert `tennis_markets`. **Un solo snapshot per ciclo** (rispetto limiti: BATCH=39 mercati/chiamata,
  `REQ_DELAY=0.6s`), niente polling per-riga.

---

## 4. LE STRATEGIE

Package: **`Betfair/stream/tennis_scalper/`** (nome storico; NON tocca il calcio, hash verificato).
Tutte sono flumine `BaseStrategy`, configurate via un **dict dedicato** (`scalper_params`/`pro_params`/
`flb_params`/`swing_params`/`lab_params`) + `dry_run` + `event_sink` (telemetria). Il prezzo arriva da
`process_market_book` (Stream), il punteggio da `self.score`/`self.point_pressure` (worker IPS).

**Quante e quali:** **5 classi** (4 armabili dal Bot Panel + 1 motore di ricerca), più il **motore Lab**
che copre parametricamente le famiglie direzionali. Registry frontend: `frontend/src/lib/tennis.ts`
→ `TENNIS_BOT_REGISTRY` (4 armabili).

**Basi teoriche / fonti PER STRATEGIA** (autore/concetto **citato esplicitamente nel codice** → riferimento
canonico in §16 per approfondire; onestà: nel repo è citato per autore/concetto, non c'è il PDF):

| Strategia | Base teorica citata nel codice | File:riga | Riferimento canonico (§16) |
|---|---|---|---|
| Scalper | market-making / **mean-reversion** sul micro-prezzo (nessun paper specifico; eredita lo scalper calcio) | `tennis_scalper_bot.py:1,39,202` | Avellaneda-Stoikov (market-making) |
| Pro | **Klaassen-Magnus** (il mercato SOVRA-reagisce a punto/break) + regime via **Efficiency Ratio di Kaufman** | `tennis_pro_bot.py:89-97,231`, `tennis_lab_score.py:20` | Klaassen & Magnus; Kaufman |
| FLB ⭐ | **favourite-longshot bias** (il mercato sovra-prezza le quasi-certezze, di più agli estremi) | `tennis_flb_bot.py:1,6,47`, `tennis_lab.py:14` | Thaler & Ziemba; Ottaviani & Sørensen |
| Swing | **z-score robusto** (mediana/MAD) mean-reversion + **Efficiency Ratio (Kaufman)** + **RSI (Wilder)** | `tennis_swing_bot.py:3-4,87,151` | Kaufman; Wilder; robust stats (MAD) |
| Lab / ScoreCond | combina le sopra; condizioni score su **Klaassen-Magnus**; fair-value da **modello Markov (O'Malley)** | `tennis_lab.py`, `tennis_lab_score.py:20-21`, `research_data.py:4,68`, `tennis_winprob.py:1,5,25` | O'Malley; Klaassen & Magnus |

Il **modello win-probability** (`tennis_winprob.py`, Markov game→set→match; `research_data.py` variante
O'Malley point-level) alimenta le condizioni `model_over/model_under` (fade dell'over-reazione vs fair value).

### 4.1 ✅ Tennis Scalper — `tennis_scalper_bot.py::TennisScalperStrategy`
- **Tipo:** MAKER neutrale (quota entrambi i lati). **Fase:** in-play continuo.
- **Logica:** micro-scalp **mean-reversion** sul micro-prezzo; entra su deviazione (`signal_ticks`),
  con gate su flusso (`min_flow`) e liquidità (`min_size`), nella banda `price_min..price_max`.
  Gap-guard su `point_pressure` (break/set point) per non farsi trovare in mezzo a uno strappo.
- **Uscita:** chiude a `scalp_ticks` di profitto per ciclo; scratch/stop a `stop_ticks`.
- **Param chiave (default preset live):** `scalp_ticks=1, stop_ticks=1, signal_ticks=1, min_flow=10,
  min_size=5, price_min=1.20, price_max=6.0`. (La logica esecutiva è "re-inhabited" dallo scalper calcio,
  con la timing-da-fischio del calcio **neutralizzata** — vedi `tests/test_tennis_config.py`.)
- **Esito backtest:** ❌ perde coi fill reali (adverse selection, +€4 "ottimistico" = finzione → −€2.90 reale).

### 4.2 ✅ Tennis Pro — `tennis_pro_bot.py::TennisProStrategy`
- **Tipo:** DIREZIONALE **score-driven** (usa `self.score` = `TennisScore` dal worker IPS + `name_to_sel`).
  **Fase:** in-play. Surface-aware (`grass/fast/clay/wta`).
- **6 setup interni** (ognuno on/off + target/stop tick):
  `break_point` (gioca il break point) · `fade` (fade over-reaction post-punto, salto quota) ·
  `serving_for_set` (chi serve per il set) · `double_break` (doppio break) · `set_transition`
  (fine/inizio set) · `compressed_fav` (favorito compresso ≤ `cf_max_price=1.20`).
- **Uscita:** staged exit (`staged_frac`) + stop **asimmetrico** per-setup.
- **Esito backtest:** ❌ tutti i 6 setup perdono nel backtest reale (tenuto per riferimento).

### 4.3 ✅ Tennis FLB — `tennis_flb_bot.py::TennisFLBStrategy` ⭐ (unica tesi con struttura)
- **Tipo:** DIREZIONALE **lay**, **price-driven** (no score, no name-map). **Fase:** in-play.
- **Logica:** **favourite-longshot bias** — il mercato sovra-prezza le quasi-certezze, di più agli estremi.
  **Lay del favorito ESTREMO** a quota ≤ `lay_max` (1.10): liability minuscola (~€0.10 su €2), upside pieno
  se il quasi-certo **crolla**. **NO STOP** è la chiave (gli stop scuotono via prima del crollo; l'hold-to-end
  vince sui crolli — idea di daniele).
- **Uscita:** `exit_mode` = `green | hold | hybrid`; `green_ticks`, `green_frac`; riarmo su `rearm_mult`.
- **Esito backtest:** ✅ **UNICA POSITIVA** con fill reali: **+€1.84** (best +1.90, `lay<=1.05 hold`) su 2 match
  (De Minaur `35790054` = favorito crolla; Dimitrov-Fery `35790695` = favorito arriva a 1.01 e perde).
  **Ma:** direzionale (locked<0), validata solo su 2 match (uno col crollo ideale) → **serve campione grande**.

### 4.4 ✅ Tennis Swing — `tennis_swing_bot.py::TennisSwingStrategy`
- **Tipo:** MAKER mean-reversion, **price-driven**. **Fase:** in-play.
- **Logica:** **fade degli estremi del favorito** con z-score **robusto** (mediana/MAD, finestra `N`, soglia
  `zin`) + gate di regime **Efficiency-Ratio** (`er_max`) + conferma **RSI reversal**.
- **Uscita:** `target_frac`, `stop_ticks`, time-stop `tmax` (90s).
- **Param:** `N=40, zin=2.0, er_max=0.4, stop_ticks=8, tmax=90`.
- **Esito backtest:** 🟡 struttura buona (evita il crollo, 73% win, 0 trade su De Minaur) ma **net negativo**
  coi fill reali (−2.90) e con gate stretto fa **0 ingressi**. Da ri-validare a gate aperto.

### 4.5 🔬 Tennis Lab — `tennis_lab.py::TennisLabStrategy` (+ `tennis_lab_score.py::ScoreConditionedLab`)
- **NON armabile dal pannello** (escluso dal registry): è il **motore di ricerca/sweep**.
- **Cosa fa:** ingresso direzionale **configurabile** (side `LAY/BACK` × target `favorite/underdog` × banda
  prezzo) + gate `inplay/prematch/any` + maker/taker + **bet-delay modellato** (`bet_delay_ms="auto"`→betDelay
  reale) + **motore uscita che BLINDA il profitto**: `hold | green fisso | lock_trail` (blocca appena
  `lockable>=lock_profit`, trascina uno stop che concede max `trail_give_back`) + `stop_ticks` opzionale
  + **piramide/averaging-down** (`pyramid/max_units/add_spacing_ticks`: se la posizione va contro di N tick
  aggiunge un'unità e abbassa la media, tiene per il crollo).
- **`ScoreConditionedLab`:** inietta la timeline `.score.jsonl` allineata al `publish_time` e filtra gli
  ingressi su condizioni: SIDE-AGNOSTIC (`any/set1/set2plus/pressure/calm/setlead/early/post_game`),
  SIDE-AWARE (`serving/receiving/broke/gotbroken/fav_ahead`, via `side_map` sel→home/away, **fail-safe**:
  lato ignoto ⇒ niente trade), MODEL (`model_over/model_under` = fade over-reaction vs win-prob Markov).
- **Perché esiste:** serve a **trovare** i parametri/famiglie con un edge, non a operare live. Ha prodotto
  il verdetto "no edge" (§6).

**Nota mappa nomi (2 runner, no draw):** MATCH_ODDS tennis ha **2 runner attivi** (favorito = best-back più
basso). La mappa sel→home/away per la logica score-aware è per **cognome** tra catalogo Betfair e IPS
(`build_side_map`), ambiguo ⇒ non mappato (fail-safe). Cache `_names.json`.

---

## 5. REGISTRAZIONI STORICHE (match registrati)

### 5.1 Dove sono
**`C:\Users\Admin\Desktop\tennis_rec\`** (65 MB totali):
- `20260707/` → **100 cartelle-evento** (MATCH_ODDS), ognuna: `<event>/<event>.raw.jsonl` (book) +
  `<event>.score.jsonl` (punteggio). Es. `20260707/35790089/35790089.raw.jsonl` (841 KB) + `.score.jsonl` (72 KB).
- `setbetting_20260707/` → **27 eventi**, SET_BETTING (solo raw, no score).

⚠️ Non confondere con `_live_raw/` nel repo: quello è **calcio** (eventTypeId "1").

### 5.2 Come sono state eseguite (comandi reali)
Campagna live del **07/07/2026 ~14:28** (60 mercati big + ITF: Djokovic-Auger, Osaka-Muchova,
Sinner-Struff, Lehecka-Zverev, ecc.), con il recorder **multi-partita self-contained**:

```bash
# Campagna massiva (quella che ha prodotto tennis_rec/20260707)
python -m Betfair.stream.tennis_scalper.record_multi \
    --out C:\Users\Admin\Desktop\tennis_rec\20260707 \
    --start-within-hours 4 --max-markets 60 --score-interval 3
# Variante SET_BETTING (parallela → setbetting_20260707/)
python -m Betfair.stream.tennis_scalper.record_multi --out ...\setbetting_20260707 --market-types SET_BETTING

# Registrazione di un SINGOLO match (book+score sincronizzati)
python -m Betfair.stream.tennis_scalper.run_tennis_pro --event-id <EVENT_ID> --record <DIR>

# Recorder singolo alternativo
python -m Betfair.stream.tennis_scalper.record_tennis --event-id <EVENT_ID> --out <DIR>
```
- `record_multi.py`: scopre TUTTI i MATCH_ODDS tennis in-play + in partenza entro N ore, **senza gate
  liquidità** (la liquidità arriva durante il match — richiesta esplicita), tee del book **nativo grezzo**,
  auto-routing per-evento dalla `marketDefinition`; worker: score (batch), keepalive (300s), rediscover (180s).
  È **self-contained** (NON tocca `raw_listener`/`recorder` condivisi col calcio).

### 5.3 Formato (perché così)
- **`<event>.raw.jsonl`** = stream MCM **nativo** Betfair, una riga `{"op":"mcm",...,"pt":<epoch_ms>,"mc":[...]}`
  per messaggio, **esattamente come Betfair lo invia** → **replayabile** da `betfairlightweight` e da
  `FlumineSimulation` (`market_filter={"markets":[raw_path]}`). Contiene `atb/atl/**trd** (cumulativo)/ltp/tv`
  e `marketDefinition` (`betDelay:3`, `inPlay`, status, runners).
  **Perché il `trd` cumulativo è cruciale:** abilita il **fill maker tick-perfetto** in backtest (coda/PIQ reale).
- **`<event>.score.jsonl`** = una riga per **cambio di punteggio**: `{"t":<epoch_s>,"score":<record IPS grezzo>}`.
  Allineato al book per timestamp in fase di backtest.

---

## 6. BACKTEST / VALIDAZIONE (come proviamo l'edge)

### 6.1 Harness (fill reali)
- **`FlumineSimulation` + `SimulatedMiddleware`** con **`simulation_available_prices=False`** → i fill avvengono
  **solo sul volume tradato** (coda/PIQ rispettata), non su prezzi "disponibili" fittizi. È il backtest
  **più realistico possibile**.
- **Bet delay:** il backtest puro flumine rispetta la coda ma **non** applica il `time.sleep(betDelay)` (scatta
  solo in `paper_trade`). Il delay tennis (`betDelay:3` confermato nei raw) è quindi **modellato a livello
  strategia**: l'ordine diventa vivo `pt+3000ms` dopo la decisione.

### 6.2 Script di backtest/sweep + output
```bash
# Harness FLB/Swing multi-partita (P&L per-match + aggregato per config)
python -m Betfair.stream.tennis_scalper.flb_backtest --data <DIR>

# Sweep massivo PRICE (multi-strategia in 1 FlumineSimulation, blotter isolato)
python -m Betfair.stream.tennis_scalper.lab_grid --data <DIR>          # → _lab_leaderboard.json
# Sweep SCORE-condizionato (inietta timeline .score.jsonl + side_map)
python -m Betfair.stream.tennis_scalper.lab_grid_score --data <DIR>    # → _lab_score_leaderboard.json
# Validazione TRAIN/TEST (split match attivi pari/dispari, verdetto su ENTRAMBI)
python -m Betfair.stream.tennis_scalper.validate --data <DIR> --min-matched 2000   # → _validation.log
# Backtest score-injected del PRO bot
python -m Betfair.stream.tennis_scalper.backtest_pro --data <DIR>
# Tuning parametri
python -m Betfair.stream.tennis_scalper.tune_tennis --data <DIR>
```
(Watcher storici: `scratchpad/watcher.sh` rilanciava sweep+validate ogni 30 min → `_leaderboard.log`,
`_lab_leaderboard.log`, `_validation.log`.)

### 6.3 Metrica **LOCKED** (fondamentale)
`locked = Σ min(P&L_se_vince, P&L_se_perde)` = P&L **result-independent**. Distingue un **TRADE**
(locked>0, chiude in profit **garantito**) da una **SCOMMESSA** (locked<0, direzionale/fortuna). È la
metrica che ha **smascherato** le trappole longshot (settled positivo ma liability catastrofica). Nel
`validate.py` il **verdetto PRIMARIO è su `locked`**, il `settled_pnl` è solo riferimento.

### 6.4 Golden-rule (l'harness è validato, il "no edge" non è un bug)
`tests/test_harness_golden.py` (PERMANENTE, 4 scenari con stream MCM sintetici e `trd` cumulativo):
CRASH fav perde → pnl≈+stake; HOLD fav vince → piccola liability; DEAD 0 volume → 0 fill; SCALP round-trip
verde → pnl>0. ⇒ **l'harness registra il profitto quando c'è**: il verdetto "tutto perde tranne FLB" **non**
è artefatto di metrica. (Audit contro la checklist bug-backtest del calcio: metrica = `Σ order.simulated.profit`
(no naked-leg), classifica su settled reale, delay reale letto da `betDelay`.)

### 6.5 VERDETTO (definitivo, su 26 match attivi, train/test)
- Testate **~1100 combinazioni** su **9 famiglie**: FLB, direzionali (6 setup Pro), scalp/maker, reversione,
  trend, piramide/averaging-down, score-condizionato, momentum-post-break, modello serve-hold, z-swing.
- **NESSUN edge meccanico** sul tennis in-play MATCH_ODDS. Ogni "vincente" a settlement = **trappola longshot**
  (win piccolo spesso, coda catastrofica −12..−148, **EV negativo** ~−£220/100match). La metrica LOCKED lo
  ha dimostrato. La **momentum-post-break** (il 90% del movimento avviene dopo il segnale-punteggio) NON si
  converte in profitto dopo il delay 3s reale + train/test.
- **FLB** resta l'unica tesi con **struttura** (liability piccola vs crollo) ma anch'essa direzionale.
- **Avenue NON testate** (dati/infrastruttura diversi): **SET_BETTING** (recorder attivo `setbetting_20260707/`,
  serve modello set-score multi-runner); **pre-match value lower-tier**; **latenza con feed sub-secondo**
  (courtsiding vero = infrastruttura, non modello — noi handicappati dal poll 3s).
- **Il deliverable reale della campagna** è l'**infrastruttura di test affidabile** che *prova* il no-edge
  invece di sospettarlo, e la **metrica locked** che smaschera le trappole.

(Fonte completa: memoria `project_tennis_pro_bot_2026-07-06.md`.)

### 6.6 STORIA DEI BUG NEI BACKTEST + CHECKLIST DI AUDIT (per scovare i bug senza cercare)

Ogni bug trovato e come è stato risolto. **Chi ri-audita i backtest deve rileggere questa lista prima
di fidarsi di un risultato.** (Tutti tracciati in `project_tennis_pro_bot_2026-07-06.md`.)

1. **Metrica P&L ricostruita a mano = trappola naked-leg.** All'inizio il P&L era ricostruito come
   `min(net_win, net_lose)`: sbagliato (conta una gamba nuda). **Fix:** usare **`Σ order.simulated.profit`**
   dal blotter flumine (mai ricostruito a mano). → metrica IMMUNE.
2. **`ticks_between(low, high)` ritorna `None` se gli argomenti sono INVERTITI.** In `_manage` erano passati
   invertiti in **3 punti** → la **PIRAMIDE non aggiungeva**, lo **STOP lato-LAY** e il **GREEN lato-BACK**
   **non scattavano MAI** (⇒ tutte le run a 826 combo *precedenti* avevano quelle uscite **ROTTE**).
   **Fix:** helper `_ticks(a,b) = ticks_between(min(a,b), max(a,b))`. Test unitario piramide OK.
3. **Errore di SEGNO su LAY.** "lay 1.10 → back 1.05 = +profit" era **SBAGLIATO** (è **−0.10€**). Per un LAY
   si guadagna se la quota **SALE** (crollo del quasi-certo). ⇒ lo scalp naive era **doppiamente fittizio**;
   la lettura giusta è **piramide-hold** (FLB). Corretto esplicitamente a daniele.
4. **Maker fill "ottimistico" = FINZIONE.** Con fill ideali il maker faceva **+€4**; coi fill **reali**
   (`simulation_available_prices=False`, riempimento solo sul volume tradato + coda) fa **−€2.90**. ⇒ ogni P&L
   maker "a occhio" va verificato con l'harness reale. (Ripetuto anche sul miraggio Sinner: +73€ ideale → +0.11€ reale.)
5. **BUG #6 — gate liquidità che NASCONDE i match.** `min_matched=10k` → solo **2-3/47** match "attivi"; a gate
   **aperto (0)** → **46/47** attivi. Il gate faceva 0 ingressi sugli ITF sottili (= GATE, non "no signal") e
   **nascondeva ~43 match**, dando l'illusione di pochi dati. **Fix:** override **`--min-matched`** in `validate.py`.
6. **`serviceBreaks` dell'IPS è sempre 0.** Le condizioni `broke/gotbroken` erano **MORTE**. **Fix:** rilevare il
   break dai **GAMES** (chi vince un game ≠ chi serviva = break); aggiunta condizione `post_game` (finestra 15s).
7. **Il TAKER LAY non attraversa nel sim.** Con `simulation_available_prices=False` piazza a best-back e resta
   `size_matched=0` (il taker si riempie solo con `=True`). ⚠️ **Ancora aperto** (il MAKER lay invece si riempie).
8. **Allineamento orologi score↔book.** score = `t` locale, poll **3s**; book = `publish_time` Betfair.
   Disallineamento **~±1-2s** + poll 3s + delay 3s = **handicap ~6s** ⇒ le condizioni sono valide su scala
   **set/servizio/break** (minuti), **NON per micro-timing sub-secondo**. Non trarre conclusioni di latenza fine.
9. **Bet delay non applicato dal backtest puro.** flumine rispetta la **coda** ma NON esegue `time.sleep(betDelay)`
   (scatta solo in `paper_trade`). ⇒ il delay tennis (`betDelay:3`, confermato nei raw) è **modellato a livello
   strategia** (`bet_delay_ms="auto"` → l'ordine diventa vivo `pt+3000ms`). Chi confronta risultati deve sapere
   quale modalità (pure-sim vs paper) sta usando.
10. **Metrica LOCKED (il fix che smaschera le trappole).** `locked = Σ min(P&L_se_vince, P&L_se_perde)`
    (result-independent). Distingue **TRADE** (locked>0, profit garantito) da **SCOMMESSA** (locked<0). Ha
    smascherato il finto oro "laydog 10-40": settled **+20 (10/10) train / +16 (8/10) test** ma liability
    garantita **−12..−148** per posizione ⇒ **EV reale ~−£220/100 match**. Senza `locked` sarebbe passato per edge.

**Golden-rule (l'harness è validato — `tests/test_harness_golden.py`, PERMANENTE):** 4 scenari con stream MCM
sintetici e `trd` **cumulativo** → CRASH fav perde `pnl≈+stake` · HOLD fav vince piccola liability · DEAD 0
volume `entries=0` · SCALP round-trip verde `pnl>0`. ⇒ **l'harness registra il profitto quando c'è**: il
verdetto "tutto perde tranne FLB" **non è artefatto di metrica**.

**Checklist di audit ereditata dal calcio (scalper_lab), applicata e verificata:**
`#1` metrica = `Σ order.simulated.profit` (no ricostruzione) · `#2` classifica su `settled_pnl` reale (non su
`stats`) · `#5` detector gated (z+ER) fa 0 ingressi → integrare a gate aperto · `#6` gate liquidità nasconde
match · `#7` mappare finestra pre/in-play (60 reg → 27 con pre-match, 33 solo in-play) · `#8` delay = leggere
`betDelay` reale (3), non hardcoded.

**Strumenti/artefatti di ricerca (dove guardare i risultati):** `scratchpad/sweep_all.py` (sweep 49 config →
`sweep_result.json`), `scratchpad/watcher.sh` (ri-gira sweep+validate ogni 30 min → `_leaderboard.log`,
`_lab_leaderboard.log`, `_lab_score_leaderboard.log`, `_validation.log`), `scratchpad/latency_analysis.py`
(analisi latenza post-break), `scratchpad/synth_harness_test.py` (test golden-rule). Le classifiche/log stanno
accanto ai dati in `tennis_rec/.../`.

**Totale testato (per ricostruzione storica):** ~**1070–1100 combinazioni** = 682 price + 376 score + 12 swing
(più varianti piramide/stop). **9 famiglie:** FLB, direzionali (6 setup Pro), scalp/maker, reversione, trend,
piramide/averaging-down, score-condizionato, momentum-post-break, modello serve-hold, z-swing. **Verdetto su
26 match attivi (13 train / 13 test):** nessun edge garantito (§6.5).

### 6.7 CRONOLOGIA DELLA CAMPAGNA (per ricostruire la storia, giorno per giorno)

- **06/07** — Creato package `tennis_scalper/` (non tocca il calcio). **FLB** risulta l'unica strategia positiva
  in backtest reale (**+€1.84**), ma solo su **2 match**. Harness `flb_backtest.py` (multi-partita, fill reali).
  46/46 test verdi, code-review MAX (0 CRITICAL/HIGH).
- **07/07 (1)** — **Campagna registrazione massiva** con `record_multi.py`: ~14:28, **60 mercati** (Djokovic-Auger,
  Osaka-Muchova, Sinner-Struff, Lehecka-Zverev + ITF) → `tennis_rec/20260707/`. Harness verificato end-to-end.
- **07/07 (2)** — Motore sweep **544 config** (`lab_grid.py`), delay-aware (bet delay modellato a livello strategia).
- **07/07 (3)** — **FASE 2 score-condizionato** (`lab_grid_score.py`, +264 config → **808** totali): condizioni
  set1/set2plus/pressure/serving/receiving/broke/model_over/under.
- **07/07 (4)** — **Miraggio Sinner smascherato** (swing "perfetto" +73€ ideale → +0.11€ reale). Nasce `validate.py`
  (train/test split, verdetto su entrambi).
- **07/07 (5)** — **Piramide/averaging-down** in TennisLab. **Fix bug `ticks_between` invertito** (§6.6 #2) e
  **correzione errore di segno LAY** (§6.6 #3). 586 price + 264 score = 850 combo.
- **07/07 (6)** — **Harness VALIDATO** (golden-rule `test_harness_golden.py`). Emerge **bug #6** (gate `min_matched`
  nasconde 43 match).
- **07/07 (7)** — **Metrica LOCKED** (result-independent) + uscite close-ASAP. **Modello serve-hold** `tennis_winprob.py`
  (Markov, Klaassen-Magnus/O'Malley) + condizioni model_over/under. Bug #6 confermato enorme (3/47 → 46/47 a gate aperto).
  Totale **1070** combinazioni.
- **07/07 (8)** — **VERDETTO su 20 match** (10 train/10 test): **nessun edge reale**. La metrica locked smaschera
  "laydog 10-40" (settled +oro ma EV −£220/100).
- **07/07 (9)** — "prova tutto": **momentum-post-break** (90% del movimento dopo il segnale-punteggio; fix condizioni
  break dai games, §6.6 #6). Scoperta: **O/U games NON esiste su Betfair.it** (solo MATCH_ODDS, SET_BETTING,
  TOURNAMENT_WINNER) → avviato recorder **SET_BETTING** (`setbetting_20260707/`, 27 eventi).
- **07/07 (10)** — **VERDETTO FINALE su 26 match** (13 train/13 test): **NESSUN edge** (momentum incluso). Restano
  non testate: SET_BETTING (serve modello set-score multi-runner), pre-match value lower-tier, latenza con feed
  sub-secondo (courtsiding = infrastruttura, non modello).
- **08/07** — **Questa sessione:** costruita la **sezione Tennis** completa (Screen 1 Sport Selector, Screen 2
  Partite del Giorno, Screen 3 Trading Terminal) + **backend live dedicato** (`tennis_live/`, migrazioni `tennis_*`,
  odds job) riusando le strategie/score esistenti. Code-review a 4 revisori, fix money-critical applicate. Push su
  `feat/tennis-section`.

---

## 7. MOTORE LIVE costruito (backend dedicato)

Package **`Betfair/stream/tennis_live/`** (creato in questa sessione; scrive SOLO tabelle `tennis_*`):
- **`tennis_runner.py`** — il **runner single-stream**. Legge gli eventi PENDING da `tennis_live_follow`,
  risolve il MATCH_ODDS market_id, apre **una** MarketSubscription. BackgroundWorkers su quell'unico stream:
  `ladder_worker` (→ `tennis_live_ladder`), `score_and_now_worker` (`tennis_score_poll_full` → `tennis_live_now.score`
  + `state{markets,order_mode}`), `positions_worker`. **Ospita i bot armati** attaccandoli allo **stesso** stream
  (stesso `market_data_filter` → flumine li raggruppa in **un** MarketStream — verificato vs flumine 2.13.11).
  Arm/disarm via `tennis_bot_control`: disarmare **disabilita subito** il bot (dry_run + caps a zero) e riavvia
  il framework (`TerminationEvent`). Order client OFF/PAPER/LIVE: **OFF/PAPER forzano `paper_trade=True`**
  (kill-switch assoluto: ordini reali impossibili fuori da LIVE).
- **`tennis_db.py`** — writer Supabase **per-thread** (`threading.local`): `upsert_tennis_ladder/now`,
  `register/set_tennis_follow_status`, read/scrittura `tennis_bot_control/activity`, drena `tennis_live_order_queue`,
  `upsert_tennis_order/position`.
- **`tennis_live_order_worker.py`** — drena la coda ordini **manuali** (place/cancel/replace/greenup): claim
  atomico + idempotenza su `client_ref`; **cross-mode reject** (righe con mode ≠ runner → error, non eseguite);
  `replace` = cancel-then-place (bet delay); mirror in `tennis_live_orders` (con `source`=manuale/bot_key) e
  `positions_worker` → `tennis_live_positions`; `greenup` **fail-loud** (non ancora implementato → error esplicito).
- **`tennis_bot_service.py`** — supervisore: registra i follow per gli eventi con bot armati e avvia il runner;
  backoff idle (evita loop di re-login Betfair).
- **`betfair_tennis_odds.py`** (repo root) — job odds del giorno (§3.4) → `tennis_markets`.

**Perché single-stream:** ottimizzazione richiesta (nessun feed doppio/triplo). I bot dentro lo stream = zero
sottoscrizioni Betfair extra, una sola `get_scores` per evento.

---

## 8. DATABASE (migrazioni `tennis_*`)

`migrations/` — **da applicare in QUEST'ORDINE** (dipendenza di tipo tra file):
`tennis_markets.sql` → `tennis_live.sql` → `tennis_orders.sql` → `tennis_bots.sql`.

| Tabella | File | Scopo | Letta da (frontend) |
|---|---|---|---|
| `tennis_markets` | tennis_markets.sql | odds del giorno (PK event_id) | `get_tennis_fixtures`/`get_tennis_full_odds` |
| `tennis_live_follow` | tennis_live.sql | eventi da streammare (PENDING) | `get_tennis_follows`/`tennis_follow_event` |
| `tennis_live_now` | tennis_live.sql | stato evento + **score** (realtime) | `subscribeTennisNow` |
| `tennis_live_ladder` | tennis_live.sql | profondità per-mercato (realtime, UNIQUE `market_id`) | `subscribeTennisLadder` |
| `tennis_live_order_queue` | tennis_orders.sql | coda comandi ordine (UNIQUE `client_ref`) | `request/get_tennis_live_order` |
| `tennis_live_orders` | tennis_orders.sql | blotter ordini (manuali+bot) | `get_tennis_live_orders` |
| `tennis_live_positions` | tennis_orders.sql | esposizioni | `get_tennis_live_positions` |
| `tennis_bot_control` | tennis_bots.sql | stato/arm bot (PK event_id,bot_key) | `tennis_bot_arm/disarm`, `get_tennis_bots_state` |
| `tennis_bot_activity` | tennis_bots.sql | telemetria bot | `get_tennis_bots_state` |

**Sicurezza:** base table `REVOKE` da anon/authenticated; accesso solo via **RPC SECURITY DEFINER**
(search_path pinnato); RPC ordini/bot **owner-only** (`tennis_is_owner()`); realtime SELECT solo su
`tennis_live_now`/`tennis_live_ladder` (come il calcio). Ordini validati (whitelist action + prezzo [1.01,1000]
+ size>0), idempotenti (`client_ref UNIQUE`). Tutto **idempotente** (re-runnable).

---

## 9. FRONTEND (3 screen)

App: `frontend/` (Vite + React 19 + TS + Tailwind + shadcn + react-router + supabase). Design: dark, verde
`--primary: 155 84% 42%`, oro `--secondary: 45 93% 55%`, font Sora/Inter, `glass-card`. Auth owner-only.

- **Screen 1 — `pages/SelectSport.tsx`** (`/select-sport`): scelta Football/Tennis. Redirect post-login
  spostati qui (`LandingPage.tsx`, `AuthSection.tsx`). Football → `/dashboard` (invariato), Tennis → `/tennis`.
- **Screen 2 — `pages/TennisDashboard.tsx` + `components/tennis/TennisMatchesList.tsx`** (`/tennis`): partite
  del giorno, accordion per torneo, moneyline P1/P2 back/lay (`PriceCell` sky/rose), volume, stato, star
  (favoriti localStorage). "APRI TERMINAL" → registra l'evento (`followTennisEvent`) e naviga allo Screen 3.
- **Screen 3 — `pages/TennisTerminal.tsx`** (`/tennis/terminal`): griglia `[340px | 1fr | 360px]`:
  - **`components/tennis/TennisBotPanel.tsx`** — card per bot (arm/disarm multipli, dry-run default, param
    editor, stato, stats) + **`TennisBotEquityChart.tsx`** (equity live recharts).
  - **`components/tennis/TennisLadderColumn.tsx`** — **riusa `components/live/LadderView.tsx`** via
    **dependency-injection** (`ladderSource`/`orderApi` tennis, `sport="tennis"`, `enableDragMove`): il ladder
    del calcio resta **byte-identical** (default = funzioni calcio); il tennis legge/scrive **solo** tabelle
    tennis. **drag-to-move = cancel-then-replace** (mai `replaceOrders`, per il bet delay in-play).
  - **`components/tennis/TennisMatchStats.tsx`** — punteggio set/game/point, server, pressure, win-prob,
    punto-per-punto (da `tennis_live_now.score`).
- **Data layer:** `frontend/src/lib/tennis.ts` (contratto CONGELATO): tutte le RPC/subscribe + `TENNIS_BOT_REGISTRY`.
  Ordini speculari al calcio (`sendTennisOrderCommand`: retry 3× enqueue, idempotente, su timeout "NON reinviare").
- **Nav condivisa tennis:** `components/tennis/TennisNav.tsx`.

---

## 10. SEPARAZIONE TENNIS ↔ CALCIO (garanzia)

Richiesta esplicita utente: **zero contaminazione**. Verificata dai revisori:
- Nessun accesso a tabelle/RPC del calcio (`live_ladder`, `live_now`, `betfair_market_odds`,
  `betfair_live_order_queue`, `scalper_control`, `fixture_predictions`, `engine_signals`): gli unici match
  nel codice tennis sono **commenti** che documentano quale file calcio è stato "mirrorato".
- `LadderView` riusato via DI con **default = calcio** → football byte-identical (test 4/4 verdi).
- Strategie tennis in package separato, non toccano lo scalper calcio (hash verificato).

---

## 11. STATO ATTUALE + code-review + cosa manca

**Stato:** pushato su `feat/tennis-section` (commit `3f17659`), **non ancora su `master`** (prod). Build FE
verde; **363 test FE + 36 tennis_live + 50 tennis_scalper** verdi; ruff clean.

**Code-review approfondita** (4 revisori: frontend/security/DB/python) → fix money-critical **applicate**:
kill-switch OFF/PAPER→paper_trade, cross-mode reject, validazione ordini, `followTennisEvent` al mount,
retry enqueue, confirm arm LIVE, single-stream verificato, arm/disarm reale.

**Cosa manca / da cablare live insieme (3 item onesti):**
1. Il restart del runner **ri-autentica Betfair** ad ogni arm/disarm → validare sotto rate limit.
2. Posizioni **per-strategia**, non aggregate cross-strategy sulla stessa selezione.
3. Continuità del mirror ordini-bot dopo un restart del framework.
+ `tennis_live_positions` si popola solo con `orders_enabled`. + merge su `master` per il deploy di produzione.

---

## 12. COME RIPRODURRE TUTTO (end-to-end)

```bash
# 0) Migrazioni (in ordine) — sul DB Supabase
#    tennis_markets.sql → tennis_live.sql → tennis_orders.sql → tennis_bots.sql

# 1) Odds del giorno (Screen 2)
python betfair_tennis_odds.py                 # tutti gli eventi tennis di oggi
python betfair_tennis_odds.py --interval 300  # loop ogni 5 min

# 2) Stream live + bot (Screen 3). Env: BETFAIR_* + SUPABASE_SERVICE_ROLE_KEY + TENNIS_LIVE_ORDER_MODE
TENNIS_LIVE_ORDER_MODE=PAPER python -m Betfair.stream.tennis_live.tennis_bot_service
#   (OFF/PAPER = nessun ordine reale garantito; LIVE = reale)

# 3) Registrare match (per backtest futuri)
python -m Betfair.stream.tennis_scalper.record_multi --out <DIR> --start-within-hours 4 --max-markets 60

# 4) Backtestare / validare l'edge sui registrati
python -m Betfair.stream.tennis_scalper.validate --data <DIR> --min-matched 2000   # → _validation.log

# Frontend
cd frontend && npm run build      # tsc no-op + vite build
cd frontend && npx vitest run     # 363 test
```

---

## 13. MAPPA FILE (dove sta ogni cosa)

**Strategie (esistenti):** `Betfair/stream/tennis_scalper/` → `tennis_scalper_bot.py`, `tennis_pro_bot.py`,
`tennis_flb_bot.py`, `tennis_swing_bot.py`, `tennis_lab.py`, `tennis_lab_score.py`, `tennis_score.py` (IPS),
`tennis_winprob.py` (Markov), `tennis_serve_data.py`, `research_data.py`.
**Recording/backtest:** `record_multi.py`, `record_tennis.py`, `run_tennis_pro.py`, `run_tennis_scalper.py`,
`flb_backtest.py`, `backtest_pro.py`, `lab_grid.py`, `lab_grid_score.py`, `validate.py`, `tune_tennis.py`,
`tests/test_harness_golden.py` (+ altri test).
**Motore live (nuovo):** `Betfair/stream/tennis_live/` → `tennis_runner.py`, `tennis_db.py`,
`tennis_live_order_worker.py`, `tennis_bot_service.py`, `tests/`. + `betfair_tennis_odds.py` (root).
**DB:** `migrations/tennis_markets.sql`, `tennis_live.sql`, `tennis_orders.sql`, `tennis_bots.sql`.
**Frontend:** `frontend/src/lib/tennis.ts`; `frontend/src/pages/{SelectSport,TennisDashboard,TennisTerminal}.tsx`;
`frontend/src/components/tennis/{TennisNav,TennisMatchesList,TennisBotPanel,TennisBotEquityChart,TennisLadderColumn,TennisMatchStats}.tsx`;
`frontend/src/components/live/LadderView.tsx` (refactor DI); `frontend/src/App.tsx` (routing).
**Registrazioni:** `C:\Users\Admin\Desktop\tennis_rec\{20260707, setbetting_20260707}`.

---

## 14. GLOSSARIO
- **Back/Lay:** puntare a favore / contro una selezione. **LTP:** last traded price. **TV:** total matched.
- **WOM:** weight of money (sbilanciamento back/lay vicino al best). **PIQ:** position-in-queue (coda maker).
- **Bet delay:** ritardo Betfair in-play prima che un ordine diventi vivo (tennis = 3s).
- **FLB:** favourite-longshot bias. **Locked:** P&L result-independent (edge garantito). **MCM:** market change message (stream).
- **IPS:** InPlayService (REST punteggi). **Maker/Taker:** fornisce liquidità (in coda) / la prende (attraversa lo spread).

---

## 15. NOTE ONESTE (ripetere sempre)
1. **Nessun edge meccanico automatico** dimostrato sul tennis in-play MATCH_ODDS (§6). Non fabbricare verdi
   finti (overfitting su 1 partita = truffa). FLB = unica tesi con struttura, **da validare su campione grande**.
2. **Il punteggio è REST poll (~2s) + latenza feed Betfair**, non real-time per-punto. Il micro-timing
   serve-per-serve è fuori portata senza feed terzo licenziato (§3.2).
3. **Copertura punteggi:** WTA rimosse da Betfair, ATP ok, ITF discontinuo.
4. Usare **dry-run/PAPER** finché non c'è un edge validato. LIVE solo con micro-stake e con conferma.

---

## 16. FONTI (bibliografia)

### Fonti esterne (verificate)
- **Betfair — data/request limits (Exchange API):** https://support.developer.betfair.com/hc/en-us/articles/115003864671-What-data-request-limits-exist-on-the-Exchange-API
- **Betfair — optimise API performance (Stream vs polling):** https://support.developer.betfair.com/hc/en-us/articles/115003887451-How-do-I-optimise-the-performance-of-my-API-application
- **Betfair — Best Practice:** https://docs.developer.betfair.com/display/1smk3cen4v3lu3yomq5qye0ni/Best+Practice
- **Betfair Exchange API — guida ufficiale:** https://developer.betfair.com/exchange-api/
- **betfairlightweight — inplayservice.py (get_scores / get_event_timeline, endpoint ips.betfair.com):** https://github.com/betcode-org/betfair/blob/master/betfairlightweight/endpoints/inplayservice.py
- **Betfair Developer Forum — how to get current tennis score:** https://forum.developer.betfair.com/forum/sports-exchange-api/exchange-api/30495-how-to-get-current-tennis-score
- **Bet Angel forum — Betfair Tennis Scores API: WTA no longer available:** https://forum.betangel.com/viewtopic.php?t=22747
- **Bet Angel — Tennis Scores:** https://www.betangel.com/tennis-scores/
- **flumine** (framework trading su stream, v2.13.11): https://github.com/betcode-org/flumine
- Feed real-time terzi (opzione, non integrati): Sportradar, **Tennis Data Innovations (TDI)** (dati ufficiali ATP/WTA), Genius Sports.

### Fonti accademiche / teoriche (per strategia)
> Legenda: **[CODICE]** = autore/concetto **citato esplicitamente nel codice**; **[CONTESTO]** = riferimento
> canonico che **aggiungo io** per rintracciabilità (il concetto è nel codice, l'autore non è citato). Non è
> stato salvato alcun PDF nel repo: questi sono i riferimenti per ricostruire la teoria.

- **[CODICE] O'Malley, A. J. (2008)** — *Probability Formulas and Statistical Analysis in Tennis*, Journal of
  Quantitative Analysis in Sports 4(2). → modello Markov / fair-value punteggio. Usato in `research_data.py:4,68`,
  `tennis_winprob.py`.
- **[CODICE] Klaassen, F. J. G. M. & Magnus, J. R. (2001)** — *Are Points in Tennis Independent and Identically
  Distributed? Evidence from a Dynamic Binary Panel Data Model*, JASA 96(454). **+ (2003)** *Forecasting the winner
  of a tennis match*, European Journal of Operational Research 148(2). → over-reazione del mercato a punto/break;
  condizioni score. Usato in `tennis_winprob.py:5`, `tennis_lab_score.py:20-21`.
- **[CODICE] Kaufman, P. J.** — *Efficiency Ratio / Adaptive Moving Average* (in *Smarter Trading*, 1995;
  *Trading Systems and Methods*). → gate di regime trend/range. Usato in `tennis_pro_bot.py:96,231`, `tennis_swing_bot.py`.
- **[CODICE] Wilder, J. Welles (1978)** — *New Concepts in Technical Trading Systems* (RSI). → conferma d'inversione.
  Usato in `tennis_swing_bot.py:87,151`.
- **[CODICE] Favourite-Longshot Bias** — **Thaler, R. H. & Ziemba, W. T. (1988)** *Anomalies: Parimutuel Betting
  Markets*, JEP 2(2); **Ottaviani, M. & Sørensen, P. N. (2008)** *The Favorite-Longshot Bias: An Overview of the
  Main Explanations*. → tesi FLB. Citato in `tennis_flb_bot.py:1,6`, `tennis_lab.py:14`.
- **[CONTESTO] Avellaneda, M. & Stoikov, S. (2008)** — *High-frequency trading in a limit order book*,
  Quantitative Finance 8(3). → cornice teorica del market-making/mean-reversion (scalper/swing).
- **[CONTESTO] Statistica robusta (mediana/MAD)** — Huber (1981); Rousseeuw & Croux (1993). → z-score robusto in
  `tennis_swing_bot.py`.

### Fonti interne (documenti del repo)
- `TOOL_DEFINITIVO_ROADMAP.md` — roadmap parità con Bet Angel/Geeks Toy/Fairbot/Cymatic/Betting Toolkit (design terminale).
- `HANDOFF_TOOL_DEFINITIVO.md`, `LIVE_TRADING_SOFTWARE_PLAN.md`, `HANDOFF_LIVE_TRADING.md` — piani/architettura trading software.
- `Betfair/stream/trading/INTERFACES.md` — contratto ordini/interfacce (mirrorato per il tennis).
- `Betfair/stream/scalper/SCALPER_BOT_DOSSIER.md` — dossier scalper calcio (template).
- **Memoria di progetto (Claude):** `project_tennis_pro_bot_2026-07-06.md` (campagna backtest, ~1100 combo,
  verdetto no-edge, FLB, metrica locked, comandi), `project_tennis_section_terminal_2026-07-08.md`
  (questa sessione: 3 screen + backend live + code-review).

### Fonti dati Betfair usate nel codice
- **Exchange Stream API** (prezzi/ladder) — via flumine `MarketSubscription`.
- **InPlayService** `get_scores` (punteggi) — `ips.betfair.com/inplayservice/v1.1/scores`, poll ~2s.
- **REST** `listEvents(["2"])`/`listMarketCatalogue`/`listMarketBook`/`placeOrders` — via `betfairlightweight` / `Betfair/client.py`.

---
*Fine dossier. Se qualcosa non torna, la fonte primaria è il codice ai path in §13 + la memoria in §16.*
