# SCHEDA E5 - I BOT TENNIS (pro, FLB, swing, scalper tennis) + dati tennis + replay tennis + UI tennis + adattatore del banco

Data: 08/10/2026. Autore: delegato Sonnet (tappa 2). Prefisso funzionalita': `E5-`.

**Perimetro (righe = `wc -l` sui file tracciati):**
- `Betfair/stream/tennis_live/` ESCLUSI runner/registratore/canale (sono la scheda A: `tennis_runner.py` 3.483, `tennis_recorder.py` 384,
  `canale_bot_tennis.py` 357, `iscrizione_a_caldo.py` 322, `mercati_registrati.py` 95): `tennis_live_order_worker.py` 1.831,
  `tennis_bot_service.py` 1.183, `certificazione_bot.py` 1.189, `tennis_db.py` 869, `esecutore_tennis.py` 618, `guardie_tennis.py` 487,
  `chiusura_manuale.py` 425, `auto_mode.py` 270, `paper_execution.py` 113, `__init__.py` 12 = **6.997** + `tools/replay_bot.py` 1.679 = **8.676**.
- `Betfair/stream/tennis_scalper/` **8.943** righe: `tennis_scalper_bot.py` 2.974, `tennis_pro_bot.py` 1.317, `condotta_ordini.py` 867,
  `tennis_swing_bot.py` 810, `tennis_flb_bot.py` 727, `record_multi.py` 333, `run_tennis_scalper.py` 329, `superficie.py` 322,
  `tennis_score.py` 265, `backtest_pro.py` 169, `tune_tennis.py` 161, `run_tennis_pro.py` 159, `flb_backtest.py` 141,
  `research_data.py` 130, `tennis_winprob.py` 97, `record_tennis.py` 71, `tennis_serve_data.py` 71, `__init__.py` 0.
- `Betfair/stream/tennis_replay/` **811** (`convertitore.py` 523, `importa.py` 165, `caricamento.py` 112, `__init__.py` 11).
- `betfair_tennis_odds.py` (radice) **322**.
- Frontend tennis (non test): `lib/tennis.ts` 1.129, `lib/tennisReplay.ts` 504, `lib/tennisReplayVerificaBarra.ts` 198; pagine
  `TennisReplay.tsx` 811, `TennisTerminal.tsx` 320, `TennisDashboard.tsx` 33; `components/tennis/` `TennisBotPanel` 685, `TennisMatchStats` 633,
  `TennisMatchesList` 535, `TennisLadderColumn` 241, `TennisBotEquityChart` 166, `TennisNav` 152, `TennisBotServiceParamsSheet` 137;
  `components/tennis-replay/` 104 + 65; `components/controlroom/` `soloTennis.ts` 190, `tennisAuto.ts` 127, `useTennisVivo.ts` 260;
  anteprima `tennisDati.ts` 580 + `tennisFinto.ts` 153 = **7.023**.
- Banco: parte tennis di `Betfair/stream/backtest/registro_bot.py` (`_MODULI_TENNIS` `:190`, `BotRegistrato` `:348, :361, :374, :387`).
- **Totale perimetro E5 = 25.775 righe di file** (somma dei blocchi sopra: 8.676 + 8.943 + 811 + 7.023 + 322).

**Fuori perimetro, citati come dipendenze (NON rifatti):** scheda A (`tennis_runner`, registratore, canale 47332/47337, stream unico,
login), scheda C (`tennis_live_order_worker`, `esecutore_tennis`, `guardie_tennis`, `condotta_ordini`: C-024, C-027, C-070..C-072), scheda D
(`OspiteFlumine`, ponte `tennis_bot_service`, D-006/D-007/D-032/D-033/D-035/D-037/D-046/D-047/D-049/D-051/D-053), scheda E4 (lo scalper tennis e'
copia al 76% di quello calcio: E4 par. 3.1, `E4_SCALPER_CALCIO.md:304-330`), scheda G (`tennis_db.py` client parallelo, G-006/G-007/G-028..G-030).
Per i file che stanno sia in C/D sia qui, E5 ne da' le funzionalita' per utente e rimanda a C/D per l'analisi di dettaglio.

**Strumenti miei (rieseguibili, in `ARCHITETTURA_2026-10/strumenti/`):** `e5_righe_tennis.py` (+ `e5_righe_tennis_output.txt`: righe di codice
strategia/parametri/guscio per bot, con gli intervalli scritti nel file), `e5_gemelli.py` e `e5_gemelli_funzioni.py` (gemelli per riga e per
funzione, difflib, normalizzazione senza vuote/commenti). Piu' `grep -n`, `sed -n`, `wc -l`, `ls`.

**Altri bot tennis cercati (registro del banco e UI):** nel registro ci sono 5 bot tennis: `safe_tennis` (`registro_bot.py:301`, Safe: scheda E3)
e i quattro `tennis_scalper/tennis_pro/tennis_flb/tennis_swing` (`registro_bot.py:348-399`). La UI arma esattamente quattro bot
(`TENNIS_BOT_REGISTRY`, `frontend/src/lib/tennis.ts:719-848`, chiavi = `_BOT_KEYS` `tennis_bot_service.py:220` = `_BOT_REGISTRY`
`tennis_runner.py:126-131`). **Non esistono altri bot tennis in produzione.** `TennisLabStrategy` (il motore di ricerca del dossier) NON sta
piu' in `tennis_scalper/`: e' in `laboratorio/tennis_lab/` (8 file tracciati, `git ls-files | grep tennis_lab`), fuori produzione: il dossier
`TENNIS_BOT_DOSSIER.md:218-232` e' invecchiato su questo punto.

---

## 1. OGGI

### 1.1 File, righe e responsabilita' reali

| Blocco | Righe | Responsabilita' reale (letta dal codice) |
|---|---:|---|
| `tennis_scalper/tennis_scalper_bot.py` | 2.974 | scalper tennis: `TennisScalperStrategy`, "COPIA di scalper_bot.ScalperStrategy" (`:274`, E4 `:317`); 72 chiamate `c.get("` (`grep -c`) |
| `tennis_scalper/tennis_pro_bot.py` | 1.317 | `TennisProStrategy`: 6 setup score-driven, regime ER, superficie; 44 `c.get("` |
| `tennis_scalper/tennis_swing_bot.py` | 810 | `TennisSwingStrategy`: z robusto + ER + RSI; 18 `c.get("` |
| `tennis_scalper/tennis_flb_bot.py` | 727 | `TennisFLBStrategy`: lay del favorito estremo; 13 `c.get("` |
| `tennis_scalper/condotta_ordini.py` | 867 | regole d'ordine condivise dai 4 bot: `size_legale :97`, `FrenoRifiuti`, `UsciteEsatte :259`, `ResiduiRicordati :524`, `_OpsCattura :612`, `ingresso_finito :669`, `piatta :794`, `chiedi_uscita_manuale :842` |
| `tennis_scalper/tennis_score.py` | 265 | `TennisScore :49`, `parse_tennis_scores :131`, `tennis_score_poll :178`, `tennis_score_poll_full :226` |
| `tennis_scalper/superficie.py` | 322 | tabella torneo -> superficie (`Superficie :253`, `risolvi :298`, `voci_per_superficie :317`), usata da `tennis_runner._instantiate_bot` |
| `tennis_scalper/tennis_winprob.py` | 97 | modello Markov game->set->match (`p_set :21`, `p_match :51`, `estimate_holds :69`); in produzione serve SOLO a un numero mostrato (`tennis_runner.py:313` "P(vittoria p1)" per `tennis_live_now`), non a decisioni dei bot; la Safe lo usa (`bot_service.py`, `tennis_opportunity.py`) |
| `tennis_scalper/` 7 file CLI/ricerca (`record_multi` 333, `backtest_pro` 169, `tune_tennis` 161, `run_tennis_pro` 159, `flb_backtest` 141, `research_data` 130, `record_tennis` 71) | **1.164** | lanciati a mano; `grep -rlE "(import|from) ... <modulo>"` su `Betfair/` (escluso `tests/`) non trova NESSUN importatore per nessuno dei sette. `tennis_serve_data.py` (71) e' importato solo da `safe_strategy/tennis_opportunity.py` |
| `tennis_scalper/run_tennis_scalper.py` | 329 | `TENNIS_PARAMS :41-77` (preset dello scalper tennis, importato da `tennis_runner.py:72`) + CLI di lancio a mano (un login e un Flumine propri, A) |
| `tennis_live/tennis_db.py` | 869 | accesso Supabase del tennis (client per-thread `:54`, 31 funzioni, **39 chiamate `.table(`**: par. 1.4) |
| `tennis_live/tennis_bot_service.py` | 1.183 | ponte UI <-> runner: riconcilia gli interruttori dei 4 bot (`riconcilia_interruttori :420-732`, 313 righe), segue le partite dal feed, auto-mode (D-006, D-032) |
| `tennis_live/certificazione_bot.py` | 1.189 | i controlli di condotta per il banco (`_b1.._b9 :548-708`, `_q_* :477-537`, `credenze :333`, `rifiuti_taglia_nuovi :739`): 22 controlli attivi sul pro, 19 sul FLB (intestazioni dei referti) |
| `tennis_live/tools/replay_bot.py` | 1.679 | adattatore del banco: `certifica_scenario :1225`, `parametri_scenario :213`, 17 scenari (`h_scenari_per_bot_output.txt:11-12`), istanzia il bot con la `_instantiate_bot` di produzione |
| `tennis_live/tennis_live_order_worker.py` | 1.831 | coda ordini + specchio + posizioni del runner tennis (scheda C: C-070) |
| `tennis_live/esecutore_tennis.py` 618, `guardie_tennis.py` 487, `chiusura_manuale.py` 425, `auto_mode.py` 270, `paper_execution.py` 113 | 1.913 | motore ordini tennis spento di serie (C-071), guardie di modalita' e kill-switch (C-027), "chiudi ora" (D-037), arming dal feed (D-032), esecuzione paper con bet delay fresco |
| `tennis_replay/` | 811 | pipeline a mano: registrazione raw -> righe -> Supabase (`importa.py` CLI, `convertitore.py` puro, `caricamento.py` idempotente) |
| `betfair_tennis_odds.py` | 322 | job "Partite del Giorno" (par. 1.6) |
| frontend tennis | 7.023 | par. 2 (UI) |

### 1.2 Dipendenze in entrata e in uscita (grep)

- In entrata su `tennis_db`: `chiusura_manuale.py:52`, `esecutore_tennis.py:58`, `guardie_tennis.py:437` (import locale), `tennis_bot_service.py:41`,
  `tennis_live_order_worker.py:32`, `tennis_runner.py:94` (`grep -rn "tennis_db" ... | grep import`).
- In entrata sui 4 bot: solo `tennis_runner._BOT_REGISTRY :126-131` e il banco (`registro_bot.py:190-211`, `_MODULI_TENNIS`).
- In entrata su `condotta_ordini`: i 4 bot, `certificazione_bot.py`, `chiusura_manuale.py`, `tennis_live_order_worker.py`, `registro_bot.py`.
- In entrata su `superficie`: solo `registro_bot.py` e `tennis_runner.py`.
- In uscita: flumine (`BaseStrategy`, `LimitOrder`, `get_price`, `price_ticks_away`), `..trading.stato_mercato` (`AttesaRiapertura`), `..uscite_proposte`
  (`CancelloUscite`, `proposta_di`), `tennis_scalper_bot` (FLB importa `compute_green, green_piazzabile, ticks_between` da li': `tennis_flb_bot.py:50`).
  I 3 bot non-scalper dipendono quindi dallo scalper tennis per 3 funzioni di calcolo del green.

### 1.3 Orologi, thread, canali, processi del perimetro

- Un solo processo di gioco: il runner tennis (A). I bot sono `BaseStrategy` nello STESSO `Flumine` e nello STESSO stream (`tennis_runner.py:893-925`, D `:119`).
- Orologio dei bot: `publish_time` del book (`self._now_ms` FLB `:337`; swing `_pt` `:640`; pro `self._now_pt`, `process_market_book :793-876`): non l'orologio di sistema.
- Worker del runner con cadenze (tutte lette): `score_and_now_worker` 2,0 s (`tennis_runner.py:111, 3355`), `bot_control_worker` 3,0 s (`:112`,
  cadenza scelta da `_intervallo_bot_control`), `record_flag_worker` 5,0 s (`:113`), `follow_worker` 20,0 s (`:114`), `tennis_live_order_worker` e `positions_worker`
  1,0 s (`:115, 3370-3375`), `lifecycle_worker` 60 s (`:3384`), `arresto_worker` 1 s (`:3388`), `stall_worker` 10 s (`:3392`). Ponte `ENSURE_POLL_SEC = 15,0`
  (`tennis_bot_service.py:46`).
- Processi esterni al runner: ponte (`tennis_bot_service`, porta lock 47312 - D), job quote `betfair_tennis_odds.py` (lock 47316, `:310`), CLI a mano.

### 1.4 Le 39 chiamate `.table(` di `tennis_db.py` (`grep -c "\.table("` = 39): cosa, quando

Dove non scrivo la frequenza e' perche' non l'ho misurata io; le frequenze per tabella sono quelle di G (che cita `07_MISURE_OGGI.md` par. 4.2:
runner-tennis 28,4 richieste/min, tennis-bot 44,4/min - `G_DATI_E_ALGORITMI_DEL_CLOUD.md:79`; `tennis_live_follow` GET 27,1/min, `tennis_bot_control` GET 21,5/min,
`tennis_bot_service_control` PATCH 14,3/min + GET 3,6/min - `G:103`).

| # | riga | tabella | operazione | funzione | chi la chiama e quando |
|--:|---|---|---|---|---|
| 1 | 118 | `tennis_live_follow` | upsert su `event_id` | `register_tennis_follow :86` | ponte `tennis_bot_service.py:195`: una volta per ogni partita nuova del feed unico (giro `_ensure_loop`, ogni 15 s) |
| 2 | 152 | `safe_strategy_scan` | select | `list_tennis_feed_rows :141` | ponte `:808` (`_leggi_feed`): il FEED UNICO dello scanner (riletto dal DB quando il canale 47336 non copre) |
| 3 | 180 | `safe_strategy_status` | select `payload,updated_at` | `scanner_heartbeat :175` | ponte `:820`: l'heartbeat dello scanner per dire "feed vivo" |
| 4 | 198 | `tennis_live_now` | select `event_id,status` | `list_tennis_now_status :189` | ponte `:740` (`_stato_now`): per sapere quali partite sono CLOSED |
| 5 | 214 | `tennis_bot_control` | update `uscite_automatiche` | `set_tennis_bot_uscite :207` | ponte `:896` (`_propaga_uscite`): quando l'utente cambia l'interruttore uscite |
| 6 | 231 | `tennis_live_follow` | update status | `set_tennis_follow_status :226` | runner `:657, 829, 2113, 2478, 2550, 2636, 2653, 3400`: transizioni PENDING/STREAMING/CLOSED/ERROR |
| 7 | 240 | `tennis_live_follow` | select pending | `list_pending_tennis_follows :236` | runner `:2147, 2758, 2860, 3183` (`follow_worker` 20 s) e ponte `:144` |
| 8 | 260 | `tennis_live_ladder` | upsert su `market_id` | `upsert_tennis_ladder :251` | runner `:1499`: write-on-change, tetto 2 s per ladder (A `:155`) |
| 9 | 292 | `tennis_live_now` | upsert su `event_id` | `upsert_tennis_now :266` | runner `:1685` (`score_and_now_worker`): una riga per partita non CLOSED ogni 2 s |
| 10 | 306 | `tennis_live_now` | update CLOSED | `chiudi_tennis_now :295` | runner `:662` (fine partita) |
| 11 | 313 | `tennis_live_now` | upsert (ripiego) | `chiudi_tennis_now :295` | stesso, se la riga non esiste |
| 12-14 | 335, 342, 351 | `tennis_live_orders`, `tennis_live_positions`, `tennis_live_order_queue` | 3 select | `soldi_sull_evento_tennis :323` | runner `:719`: prima di dichiarare chiusa una partita, "ci sono soldi?" |
| 15-17 | 369, 377, 384 | `tennis_live_now`, `tennis_live_follow`, `tennis_live_now` | select + select + update | `chiudi_tennis_now_orfani :360` | runner `:3149`: una volta all'avvio |
| 18 | 399 | `tennis_bot_control` | select `*` | `list_tennis_bot_controls :393` | ponte `:170`; runner `:1155, 1179, 1260, 2443, 3067` (`bot_control_worker`, 3 s) |
| 19-20 | 444, 451 | `tennis_bot_control` | update (con/senza colonna) | `set_tennis_bot_status :407` | runner, 17 siti (`:1801 ... :3338`): armed/running/error/stopped |
| 21 | 468 | `tennis_bot_control` | update `params` | `set_tennis_bot_params :460` | runner `:1094` (superficie scritta nei params) |
| 22-24 | 501, 503, 508 | `tennis_bot_control` | update `error` (3 rami) | `set_tennis_bot_wait_reason :480` | runner `:1271, 1282`: motivo "[ATTESA]" benigno |
| 25 | 518 | `tennis_bot_activity` | **insert** | `write_tennis_bot_activity :513` | runner, 12 siti (`:850 ... :2260`): ogni evento d'attivita' dei bot |
| 26 | 535 | `tennis_live_order_queue` | select pending | `list_pending_tennis_orders :532` | order worker `:1726` (1 s) |
| 27-29 | 549, 568, 580 | `tennis_live_order_queue` | update claim / done / error | `claim :545`, `write_..._done :560`, `write_..._error :578` | order worker `:1741-1825` |
| 30 | 604 | `tennis_live_orders` | upsert (specchio) | `upsert_tennis_order :593` | order worker `:565` (`_mirror_order`) |
| 31 | 627 | `tennis_live_positions` | upsert | `upsert_tennis_position :616` | order worker `:1468, 1497` |
| 32-33 | 662, 710 | `tennis_bot_service_control` | select / update | `list_tennis_bot_services :653`, `set_tennis_bot_service_state :678` | ponte `:436, 970` e `:676, 1005` |
| 34-35 | 764, 777 | `tennis_bot_control` | upsert su `event_id,bot_key` (2 varianti, con/senza colonna `mode`) | `upsert_tennis_bot_control :721` | ponte `:587, 644`: arma i 4 bot sulle partite |
| 36-37 | 818, 831 | `tennis_live_order_queue` | 2 chiamate | `fail_stale_pending_tennis_orders :807` | `guardie_tennis.py:446` (ripresa all'avvio) |
| 38-39 | 854, 863 | `tennis_live_orders`, `tennis_live_positions` | 2 update | `chiudi_specchio_paper_orfano :846` | `guardie_tennis.py:447` (ripresa all'avvio) |

Lettura per tipo di operazione (sulle righe `.table(`): 8 upsert, 1 insert, 12 select, 18 update/altre (le chiamate `:818` e `:831` non le ho classificate); le select di polling di controllo sono le righe 2, 3, 4, 7, 18, 26, 32 e quelle di 12-14; le scritture periodiche del runner sono 8, 9, 19-20 e 25. Le 8 scritture idempotenti con `on_conflict` sono a `:118, 260, 292, 313, 604, 627, 764, 777` (G `:69`). Il client e' PER-THREAD e un secondo client
rispetto a `stream/db.py` (G-007, `tennis_db.py:54-60`).

### 1.5 Stato della partita di tennis (game/set/servizio): da dove arriva e con quale ritardo

Catena letta dal codice (nessun numero di latenza e' stato misurato da me):
1. **Fonte**: l'InPlayService (IPS) di Betfair, servizio NON ufficiale (`safe_strategy/service.py:193`, `betfairlightweight.in_play_service`), che non ha stream.
2. **Scanner Safe** (processo `safe_strategy/service.py`): un thread dedicato `ScoreFeedWorker` fa poll batch a **`_SCORES_PERIOD_SEC = 2,0 s`**
   (`service.py:126-134`; chunk da 50, `get_scores(..., lightweight=True)` `:1731`) e riscrive la riga di scan con throttle 2,5 s (`scan_feed.py:44-51`,
   commento). Il commento di `scan_feed.py:40-43` dice "poll IPS a 3s": il codice dice 2,0 s (`service.py:134`): vale il codice.
3. **Runner tennis**: `score_and_now_worker` ogni **2,0 s** (`tennis_runner.py:111, 3355`) legge `ScanFeedScoreProvider.get_raw_state` (`:1619-1640`); la riga e'
   "fresca" se piu' giovane di **15,0 s** (`scan_feed.py:44` `DEFAULT_MAX_AGE_SEC`), con limite assoluto `HARD_MAX_AGE_SEC` (`:44-51`) e scanner "vivo" se
   l'heartbeat e' sotto 30 s (`:36-38`). Riga assente o stantia: **chiamata diretta** `trading.in_play_service.get_scores` per evento (`tennis_runner.py:1619-1650`), contata in `feed.direct_calls`.
4. `parse_tennis_scores` (`tennis_score.py:131`) -> `TennisScore` (set, game, punto, servizio `home/away`, nomi). Il worker lo passa ai bot ospitati
   (`strat.score = ts`, `strat.point_pressure`; `score_and_now_worker :1619-1680`), lo scrive su `tennis_live_now` (`upsert_tennis_now`, par. 1.4 #9), accoda l'evento punto (`point_event :360`),
   e lo tee-a su `.score.jsonl` se la partita e' in registrazione (`RAW_TEE.write_score`).
5. **Ritardo, calcolato sulle costanti**: le tre cadenze nostre in cascata sommano al massimo 2,0 (poll scanner) + 2,5 (throttle di riscrittura) + 2,0 (worker runner)
   = **6,5 s** nel caso peggiore, piu' la latenza propria dell'IPS (non misurata). Non c'e' nessun legame con l'orologio del mercato: il referto del banco lo
   dichiara ("punteggi: 104 campioni dal sidecar (orologio del poll IPS, non del mercato)", `AUDIT_2026-10-08/applica_bot_tennis/certifica_dopo.txt` riga 8).
   **Strumento che lo misurerebbe**: per ogni cambio di punteggio del sidecar `.score.jsonl` (campo `t`) trovare il primo book in cui la quota si muove oltre
   2 tick; lo scarto e' il ritardo effettivo del punteggio rispetto al mercato (script da scrivere in `strumenti/`, sola lettura sulle registrazioni).
6. Il pro e' il solo bot che DECIDE dal punteggio (6 setup + uscita strutturale `tennis_pro_bot.py:984-990`); gli altri tre usano solo `point_pressure` (scalper) o niente.
   Fail-safe dichiarato: con `ts None` la gap-guard resta invariata (commento in `score_and_now_worker :1619-1680`).

### 1.6 `betfair_tennis_odds.py` ogni 30 minuti: cosa fa

- Lanciato da `desktop/main.js:470-482`: una volta all'avvio e poi `setInterval(runTennisOdds, 30 * 60 * 1000)`; se la run precedente e' ancora viva la salta;
  in piu' lock di singola istanza sulla porta 47316 (`betfair_tennis_odds.py:310`).
- **A ogni run (processo breve)**: `BetfairClient().login_cert()` (`:311-312`: un login Betfair nuovo a ogni run = **48 login al giorno**, calcolo 24 x 2),
  `list_events(["2"], from=now-12 h, to=fine giornata)` (`:197-205`), poi per blocchi di 10 eventi `listMarketCatalogue` (`CAT_CHUNK = 10`) e per ogni evento
  `listMarketBook` in lotti da 8 mercati (`BATCH = 8`, EX_BEST_OFFERS + EX_TRADED, `:25-27`) con pause `REQ_DELAY = 0,6 s` e `EVENT_DELAY = 0,2 s`.
- Costruisce una riga per evento (`_build_event_record :84`: player1/2, moneyline back/lay, `total_matched`, `markets[]`, `full_odds[]`), **cancella**
  `tennis_markets` del giorno (`:274`) e **riscrive** a blocchi da 200 (`:278`). Se Betfair risponde `TOO_MANY_REQUESTS`/`TOO_MUCH_DATA` si ferma (`BetfairLimitHit`).
- Chi la legge: la lista "Partite del Giorno" (`TennisMatchesList.tsx`) e il ponte (`_market_row_for`, `tennis_bot_service.py:147`) per i nomi dei giocatori delle partite
  da seguire. Frequenza misurata in DB: 0,1 scritture/min (G `:295`).
- Rischio letto: tra la delete (`:274`) e gli upsert (`:278`) la tabella del giorno e' vuota o parziale (finestra breve, non misurata).

### 1.7 Dove sono le registrazioni tennis usate dal banco (verifica della affermazione di 07)

- 07 ha ragione: **in `_live_raw/` non c'e' nessuna registrazione tennis**. `_live_raw/` ha 83 cartelle (`ls _live_raw | wc -l`), e' ignorata da git (`.gitignore:20`),
  e `find . -maxdepth 4 -name "*35790089*"` non la trova li'. Non esiste `_live_raw_tennis/` in questo checkout.
- `registrazioni_banco/` (tracciata) contiene solo DUE partite di CALCIO (`35760084`, `35797769`; `registrazioni_banco/LEGGIMI.md`).
- Il banco legge il tennis da **`~/Desktop/tennis_rec/<ultimo giorno numerico>`** (`registro_bot.py:48-56`, `_cartella_tennis`, override `TENNIS_RECORD_DIR`):
  oggi `C:\Users\Admin\Desktop\tennis_rec\20260707` (`ls`): **89 sottocartelle**, ciascuna `<id>/<id>.raw.jsonl` + `<id>.score.jsonl` (es. `35790089`: raw 841.467 byte,
  score 71.604 byte, `ls -la`), piu' 12 file `_*.log/json` di campagna (`_names.json`, `_validation*.log`, ...). Totale `du -sh` = **65 MB**. Esiste anche `setbetting_20260707`
  (non cifre: il banco lo ignora, `registro_bot.py:55` `d.isdigit()`).
- **Fatto rilevante**: tutta la certificazione tennis poggia su **UNA giornata (07/07/2026)** e su **UNA macchina fuori dal repository**. Un'altra sessione senza il PC dell'utente non
  puo' rieseguire il replay tennis (i referti del 07/10 sono stati fatti in un ambiente con copia `_live_raw_tennis/20260707`, vedi riga 1 di
  `AUDIT_2026-10-07/replay_conformita_tennis_pro/tennis_pro_tutti_dopo_COORDINATORE.txt`, non presente qui). Il Replay Tennis della UI importa le stesse registrazioni
  nelle tabelle `tennis_replay_*` (G `:105`: 137.171 snapshot, 257 MB).

---

## 2. FUNZIONALITA'

Legenda: **[UI]** visibile in UI (file del pannello); **[PAR]** parametro editabile in UI; **[S]** logica di strategia INTOCCABILE; **[G]** guscio.
La separazione strategia/guscio: la strategia e' l'insieme delle regole di ingresso/uscita; tutto il resto (piazzare, cancellare, residui, uscite manuali,
telemetria) e' guscio. Per lo scalper tennis rimando a E4 (E4 `:304-330`).

### 2.A Tennis PRO - `tennis_pro_bot.py` (1.317 righe; strategia **427** + parametri 61 + guscio 516 righe di codice: `e5_righe_tennis_output.txt`)

Valori di serie Python: `:102-253` (ctor); UI: `lib/tennis.ts` registry `tennis_pro`.

- **E5-001 [S]** Ingresso solo in-play (`:846`), con `total_matched >= min_matched` (`:848`, serie `50_000.0` EUR `:157`; UI 50000), solo se esiste un `TennisScore` (`:850`) e solo sul CAMBIO di stato
  del punteggio (`:853` `_last_key`): un setup al massimo per punto; mai due trade nello stesso game (`_last_game_traded`, nel blocco `process_market_book :793-876`).
- **E5-002 [S]** Ordine di valutazione dei setup fisso: break_point, fade, set_transition, serving_for_set, double_break, compressed_fav (`:793-876`, in coda); il primo che scatta vince.
- **E5-003 [S]** Setup `break_point` (`_sig_break_point :628`): break point = ribattitore a 40 contro servitore a 0/15 (`_is_break_point :348-357`, `return rr == 3 and rs <= 1`, esclude 30-40);
  BACK del servitore se superficie `grass/fast`, altrimenti BACK del ribattitore (`:632`); target/stop in tick `bp_target_ticks=5`, `bp_stop_ticks=3` [PAR target e stop in UI].
- **E5-004 [S]** Setup `fade` (`_sig_fade :639`): solo nei primi `fade_max_game=3` game (`:643`), sul favorito, dopo un break precoce del set (`_break_precoce_del :760`), se la quota e' salita
  di almeno `fade_jump_ticks=8` dall'inizio del set (`:660`); BACK, `fade_target_ticks=4` [PAR target in UI], `fade_stop_ticks=4`.
- **E5-005 [S]** Setup `set_transition` (`:665`): finestra di `st_window_games=2` game dopo che un set e' stato vinto (`_set_won`, `_track_sets :772`), direzione dal regime (`_setup_side`); target 5, stop 4 tick.
- **E5-006 [S]** Setup `serving_for_set` (`:683`): servitore con >= 5 game e vantaggio >= 1 (`:690`); direzione dal regime; target 6, stop 4.
- **E5-007 [S]** Setup `double_break` (`:699`): vantaggio di game >= `db_lead_games=3` (`:704`); direzione dal regime; target 6, stop 4.
- **E5-008 [S]** Setup `compressed_fav` (`:713`): favorito con quota <= `cf_max_price=1,20` (`:721`); direzione dal regime; target 4, stop 3.
- **E5-009 [S]** Regime = Efficiency Ratio di Kaufman sulla finestra `er_window_ms=60_000` ms (`:152`, serie con `_`): `trend` se ER >= `er_trend=0,45` (`:410`), `range` se <= `er_range=0,30` (`:412`),
  altrimenti nessun regime (`_regime :396-415`; serve almeno 6 campioni).
- **E5-010 [S]** Direzione dei setup di dominio (`_setup_side :416-428`): con `adapt` acceso (serie True): trend -> BACK, range -> LAY, regime neutro -> **non entra**; con `adapt` spento: BACK se `trend` altrimenti LAY.
  `trend`, `adapt`, `maker` [PAR in UI come select on/off, serie 'on'].
- **E5-011 [S]** Abilitazione dei setup per superficie (`:139, :156`): `_lay_rev = surface not in (grass, fast)`; `serving_for_set`, `double_break`, `compressed_fav` sono accesi se `_lay_rev or trend or adapt` (serie: accesi); `break_point`, `fade`, `set_transition` accesi di serie.
- **E5-012 [S]** Filtri d'ingresso comuni a tutti i setup (`_open_trade :579-627`): quota nel range `price_min=1,08`..`price_max=3,6` (UI: `price_max` [PAR]); size al best >= `min_book_size=10`; ingresso maker a `maker_offset=1` tick dal best.
- **E5-013 [S]** Uscita: scaglione a meta' strada (`move_t >= target_t // 2`, `:966`) green di `staged_frac=0,4`; TARGET (`:974`) green totale; STOP (`:979`, `(not favorable) and move_t >= stop_t`); USCITA STRUTTURALE quando game/set che ha innescato si risolve (`:984-990`) -> scratch.
- **E5-014 [S]** Timeout d'ingresso `entry_timeout_s=25` secondi di `publish_time` (`:877-960` blocco `_manage`), cancel e attesa conferma.
- **E5-015 [S]** Mappa nomi IPS -> selezione (`_lookup_sel :313`): nome completo, cognome (solo se unico), prefisso del nome del catalogo (nome IPS troncato, fix 07/10, 35790089: "Marcelo Tomas Barrios V"); ambiguo = nessun match (fail-safe).
- **E5-016 [S]** Superficie per partita: decisa dal runner dal nome del torneo (`superficie.risolvi :298`, tabella 322 righe) e SEMPRE vincente sul `surface` dei params; torneo ignoto = `hard` dichiarato (`tennis_runner.py:893-1040` docstring e codice `sup = superficie_della_partita`). **[UI]** badge superficie con fonte (`TennisBotPanel.tsx:238`, `data-testid="tennis-pro-superficie"`, `superficieDaParams` `tennis.ts:703`).
- **E5-017 [G]** Piazzamento ordini (`_place :467-549`), cancel (`:550`), chiusura a prezzo (`_close_at :554`), `_finish :1026`, sorveglianza della chiusura (`_surveil_closing :1082-1198`, 117 righe), residuo non piazzabile (`:1199`), uscita manuale "chiudi ora" (`_avvia_uscita_manuale :1239`), settlement (`process_closed_market :1287`), proposte d'uscita al cancello (`_cancello_lascia :274`, `_pubblica_proposte :304`).

### 2.B Tennis FLB - `tennis_flb_bot.py` (727 righe; strategia **161** + parametri 14 + guscio 343)

- **E5-020 [S]** Gate di liquidita': `total_matched >= min_matched` (`:344`; serie `10_000.0` `:89`; UI 10000 [PAR]).
- **E5-021 [S]** Gate in-play: `require_inplay` (serie True, `:376`): nessun ingresso pre-match (le posizioni aperte restano gestite).
- **E5-022 [S]** INGRESSO: LAY di un runner ACTIVE quando il suo best-lay `<= lay_max` (serie 1,10, `:82`, `:384`) e la size al best-lay `>= min_lay_size=5` (`:90`); stake `max(2, stake)` (`:80`); [PAR `lay_max` in UI, 1,01..1,50].
- **E5-023 [S]** Prezzo d'ingresso: MAKER (serie True, `:111`): LAY appoggiato al BEST-BACK (non incrocia); con `maker=False` al best-lay (taker). Decisione 17/09 scritta nel commento di `:100-111`.
- **E5-024 [S]** Riarmo: dopo un ingresso il runner e' disarmato finche' il best-lay non esce dalla zona oltre `lay_max * rearm_mult` (`:370`; `rearm_mult=1,10`, `:84`) [PAR in UI].
- **E5-025 [S]** Timeout d'ingresso `entry_timeout=40` secondi di `publish_time` (`:95`; `_manage :431-597`).
- **E5-026 [S]** Uscita `exit_mode` in `hybrid` (serie) / `hold` / `green` (`:86`) [PAR select in UI]: `green_ticks=8` (`:87`) di movimento in favore -> green-up della frazione `green_frac=0,5` (hybrid) o 1,0 (green) [PAR in UI]; `hold` = nessuna uscita fino al settlement; **nessuno stop** (tesi del dossier).
  Il green passa dal cancello delle uscite (`:552`, `cancello_uscite.lascia_uscire`): di serie `uscite_automatiche=False` (`:62-65`) = solo proposta all'utente.
- **E5-027 [G]** `_place :188-268`, `_green :274`, `_matched :165`, residuo non piazzabile `:409`, uscita manuale `:608-687`, `process_closed_market :695`, "chiudi ora" (`:338-343`: da li' il bot solo chiude e non rientra).

### 2.C Tennis SWING - `tennis_swing_bot.py` (810 righe; strategia **91** + parametri 19 + guscio 490)

- **E5-030 [S]** Segnale (`process_market_book :635-708`, ramo ingresso `:661-707`): solo sul favorito (`_favourite :205`); gate `total_matched >= min_matched` (`:661`, serie `10_000.0` `:98`); storia di
  tick-index del mid (`deque(maxlen=200)`); serve `len > N` (`:674`, N=40).
- **E5-031 [S]** z-score ROBUSTO: mediana e MAD della finestra `tk[-N:-2]`; `z = 0,6745 * (tmid - med) / mad` (`:683`); se `mad <= 0` NESSUN segnale (`:681`, fix 16/07: z astronomico su book piatto).
- **E5-032 [S]** Gate di regime: `ER(20) >= er_max=0,4` blocca (`:684`); gate di prezzo `price_min=1,08 <= mid <= price_max=8` (`:685`).
- **E5-033 [S]** Conferma: inversione di `conf_ticks=2` tick (`turned_down/up :686-688`) e RSI (periodo 14) che attraversa 65 verso il basso (BACK, `:689`) o 35 verso l'alto (LAY, `:691`); soglia `zin=2,0`.
- **E5-034 [S]** Prezzo d'ingresso maker a `maker_offset=1` tick (BACK sopra il best-lay, LAY sotto il best-back); `maker=False` = taker.
- **E5-035 [S]** Uscita sulla SELEZIONE TRADATA (non sul favorito corrente, fix 09/07): target = ancora + (ingresso-ancora) * (1 - `target_frac=0,5`) (`:575`); stop avverso di `stop_ticks=8` (`:577`); time-stop `tmax=90` s di `publish_time` (`:581`); entry timeout 40 s; riprovo di chiusura a `close_retry_s=20`/`close_retry_ticks=20`.
  Parametri in UI [PAR]: `N`, `zin`, `er_max`, `stop_ticks`, `tmax` (5 dei 18 `c.get`).
- **E5-036 [G]** `_place :244-313`, `_close :314`, `_pos :215`, residuo `:341`, `_puo_dimenticare :367`, uscita manuale `:709-773`, `process_closed_market :782`.

### 2.D Scalper tennis - `tennis_scalper_bot.py` (2.974 righe, 1.906 di codice)

Non rifaccio E4. Fatti utili: il motore maker e' la stessa logica dello scalper calcio (1.449 righe di codice uguali = 76,0% del tennis, E4 `:310`; 19 funzioni identiche, `:318`).
Solo tennis (E4 `:330`): `green_piazzabile :189`, `_phase_green :662`, `_mission_blocks :667`, `_spiega_missione :677`, `_book_locked :705`, `_count_cycle :720`, `_favourite_sel :766`.

- **E5-040 [S]** Preset di serie (`run_tennis_scalper.py:41-77`, importato da `tennis_runner.py:72`; la UI ha gli stessi valori, `tennis.ts` `defaults`): `scalp_ticks=1`, `stop_ticks=3`, `signal_ticks=1,0`, `min_flow=2,0`, `min_size=5`, `price_min=1,20`, `price_max=6`,
  `one_tick_per_phase=True`, `inplay_tick_enabled=False`, `runner_filter='favorite'`; piu' non esposti in UI: `max_spread_ticks=6`, `join_max_spread=3`, `capture_min/max_ticks=2/20`, `max_signal_ticks=10`, `warmup_ms=30000`, `max_txn_hour=300`, `live_min_bet=2,0`, `size_step=0,5`.
  **Il dossier e' sbagliato** (`TENNIS_BOT_DOSSIER.md:177-186`, sezione 4.1: `stop_ticks=1`, `min_flow=10`): il codice dice 3 e 2.
- **E5-041 [S]** "Missione 1 tick per fase": un tick di profitto PRE-MATCH per partita e poi stop automatico (stato "Concluso"); la gamba in-play e' spenta per il verdetto del backtest (commento `run_tennis_scalper.py:58-63`); [PAR select `one_tick_per_phase`, `inplay_tick_enabled` in UI].
- **E5-042 [S]** Solo il favorito (`runner_filter`, [PAR select]); anti-gap su `point_pressure` (da `strat.point_pressure`, par. 1.5); gate flusso/size/prezzo [PAR: `scalp_ticks`, `stop_ticks`, `signal_ticks`, `min_flow`, `min_size`, `price_min`, `price_max`].
- **E5-043 [G]** `_place :2413` (162 righe), `place_order :2557`, uscite manuali, `uscite_automatiche` di classe `:312`.

### 2.E Condotta degli ordini condivisa - `condotta_ordini.py` (867 righe) [G, condivisibile]

- **E5-050** `size_legale :97`: taglia legale .it (back 2, multipli di 0,5; chiusure bumpate); `diretta_ok :138`; `spezza_esatta :151` (place-and-trim); `OrdineComposto :167`; `UsciteEsatte :259` (chiusure esatte, avanza di un passo per book).
- **E5-051** `ResiduiRicordati :524` (decisione 1 del 04/10: residui non piazzabili ricordati e regolati col mercato; D-046); `FrenoRifiuti` (gemello di `trading/freno_rifiuti.py`, C-024); `_OpsCattura :612`.
- **E5-052** `stato_ordine :651`, `ordine_vivo :662`, `ingresso_finito :669`, `abbinato_selezione :690`, `sbilancio_selezione :716`, `ordini_vivi_su :735`, `dichiara_chiusura_mercato :761`, `piatta :794`.
- **E5-053** Uscita manuale: `supporta_uscita_manuale :833`, `chiedi_uscita_manuale :842`, `registra_esito_manuale :852` (D3 del 24/09).

### 2.F Punteggio, win-probability, superficie

- **E5-060** `TennisScore :49`: sets/games/punto/servizio/nomi/`raw`; `key()` per il write-on-change (`tennis_score.py`, usato in `score_and_now_worker :1619-1680`); `point_pressure` (break/set point).
- **E5-061** `parse_tennis_scores :131`: dict IPS -> `TennisScore`, punteggio dal campo `score` o da `currentPoint` ("40-15"); `tennis_score_poll :178` / `_full :226` (CLI e laboratorio).
- **E5-062** `tennis_winprob.p_match :51` (Markov): mostrato in `tennis_live_now` (`tennis_runner.py:313`), non decide nulla nei 4 bot.
- **E5-063** `superficie.py` (par. E5-016).

### 2.G Servizio ponte (D-006): `tennis_bot_service.py` (1.183 righe) [G]

- **E5-070** Arma i 4 bot sulle partite seguite e su quelle del feed unico con tetto: `ensure_follows_for_bots :165`, `riconcilia_interruttori :420-732`, `_riga_armatura :856`, `_segui_dal_feed :835`, `_leggi_feed :803`, `_stato_auto :910`; `stats.auto` in `tennis_bot_service_control` -> **[UI]** `tennisAuto.ts` (frasi) e `TennisBotServiceParamsSheet.tsx`.
- **E5-071** Interruttori per bot (`stato_desiderato :352`, `_modalita_dichiarata :345`, `_stats_battito :382`, `_propaga_uscite :889`), spegne i bot al nuovo avvio (`ferma_bot_al_nuovo_avvio :60`, `ferma_interruttori_al_nuovo_avvio :958`), ripresa (`ripresa_ponte :1020`), `arma_guardia_ponte :1042`.
- **E5-072** Loop `_ensure_loop :1050` (15 s) + sveglia dal canale 47337 (`_avvia_canale :247`, `_su_sveglia_dal_canale :299`, `_dormi_o_sveglia :336`), `run :1081`, `_main :1127` (rilancio dopo 10 s, D).
- **E5-073** Partite uscite dal feed e fine fuori feed (`_aggiorna_fuori_feed :760`, `_fine_fuori_feed_s :751`, `_origine_assente_ora :775`).
- **E5-074** `auto_mode.py` (270): `tetto_partite :89`, `params_per_strategia :105`, `origine_follow :116`, `partite_dal_feed :141`, `scegli_partite :181`, `uscite_automatiche_riga :215`, `uscite_automatiche_bot :223`, `motivo_blocco :244`. [PAR: interruttore auto, tetto partite, uscite automatiche per bot]

### 2.H Guardie, modalita', esecuzione, chiusura (C-027, C-070..72, D-037)

- **E5-080** `guardie_tennis.py`: `modalita_riga :75`, `modalita_esecuzione_bot :87` (LIVE solo se runner LIVE E riga `mode='live'`), `dry_run_esplicito_falso :101`, `MercatoConClient :109` / `instrada_ordini_su_client :134` / `build_client_paper_affiancato :163`
  (un bot PAPER dentro un runner LIVE non muove soldi veri), `ControlloModalitaBotTennis :184`, `ControlloKillSwitchTennis :324`, `ControlloModoOrdiniTennis :340`, `kill_switch_attivo :279`, `ordine_riduce_il_rischio :291`, `aggiorna_impostazioni :220`, `pubblica_modo_ordini_se_cambiato :250`, `motivo_reale_fermo :381`, `ripresa_all_avvio :426`, `guardia_blocca :464`.
- **E5-081** `chiusura_manuale.py` (425): "chiudi ora" in 3 fasi (`comando_da_riga :98`, `richiesta_ambigua :163`, `prendi_in_carico :187`, `gestisci_riga :245`, `avanza :294`, `_concludi :374`, `chiusi_dall_utente :417`). **[UI]** pulsante "Chiudi" (RPC `tennis_chiudi_bot`, migrazione `tennis_chiudi_bot_2026-09-24.sql`).
- **E5-082** `paper_execution.py` (113): `FreshDelaySimulatedExecution :43` rilegge il bet delay del mercato a ogni ordine (`_refresh_bet_delay :62`, `install_fresh_delay_execution :97`); paper tennis con `place_latency` 600 ms (`TENNIS_PAPER_LATENCY_MS_DEFAULT = 600`, `tennis_runner.py:124`).
- **E5-083** `esecutore_tennis.py` (618): adattatore del motore ordini del calcio al tennis, SPENTO di serie (`acceso :76`, `MOTORE_ORDINI_CANALE_TENNIS`, C `:44-49`): `AgganciaTennis :364`, `costruisci_motore :604`, `_dispatch :219`, `CanaleSoloComandi :298`.
- **E5-084** `tennis_live_order_worker.py` (1.831): coda `tennis_live_order_queue`, specchio `tennis_live_orders`, posizioni, riconciliazione, cross-mode (C-070, `:1699`); 22 funzioni omonime del gemello calcio (C).

### 2.I Banco (adattatore) - `registro_bot.py`, `tools/replay_bot.py`, `certificazione_bot.py`

- **E5-090** Registrazione dei 4 bot (`registro_bot.py:348-399`: servizio di produzione `_MODULI_TENNIS :190`, mercato `MATCH_ODDS`, replay `replay_bot:certifica_scenario_tennis_<bot>`, parametri `parametri_modificabili_tennis_<bot>`, controlli `certificazione_bot`, spec `TENNIS_BOT_DOSSIER.md`, cartella `_cartella_tennis`).
- **E5-091** 17 scenari (`h_scenari_per_bot_output.txt:11-12`): base, gate-aperto, dry-run, bot-fermo, rifiuti-betfair, feed-stantio, parziali, riavvio, catalogo-assente, live, `<CP.SCENARIO>`, chiudi-ora, `<UM.SCENARIO_MANUALI>`, `<UM.SCENARIO_FIRMATE>`, soldi-veri, soldi-veri-prova, soldi-veri-paper.
- **E5-092** Il replay istanzia il bot con la SUA `_instantiate_bot` (preset, dry_run dalla modalita', tetti, scoping per mercato: `registro_bot.py:340-346` commento), passa il punteggio con `parse_tennis_scores` alla cadenza del `score_and_now_worker`, e giudica anche le righe di `_mirror_order`.
- **E5-093** Controlli di condotta (`certificazione_bot.py`): B1 dry-run senza ordini, B2 prezzo nella ladder, B3 bot disabilitato non apre, B4 mercato non operabile, B5 stake del control, B6 FLB ingresso = LAY di favorito estremo, B7 tetto esposizione, B8 minimi .it, B9 "chiudi ora" una sola chiusura, B10 rifiuto per taglia non rimandato identico, CP*, UM1-UM4, UF1-UF3 (testi nelle righe `COPERTURA DEI CONTROLLI` dei referti).

### 2.J Replay Tennis (pipeline e UI)

- **E5-100** `tennis_replay/importa.py` (CLI a mano, `trova_registrazioni :39`, `anagrafica_dal_db :67`, `converti_registrazione :110`, `main :126`; `--evento`, `--prova`): la STESSA partita in piu' cartelle (es. `20260707` MATCH_ODDS + `setbetting_20260707` SET_BETTING) si unisce.
- **E5-101** `convertitore.py` puro (523): decodifica i `mcm` raw con `betfairlightweight.StreamListener` (`decodifica_raw :143`), unisce (`unisci_decodifiche :186`), punteggi (`leggi_punteggi :237`), eventi di gioco (`eventi_tennis :277`: BREAK, SET_START/END, TIEBREAK, MATCH_END, SALTO), `converti_evento :405`.
- **E5-102** `caricamento.py` idempotente (112): upsert evento/mercati, delete+insert snapshot per mercato, punteggio solo se presente (`carica_replay :55`); tabelle `tennis_replay_eventi/_mercati/_snapshots/_punteggio` (migrazioni `replay_tennis_2026-10-07.sql`, `replay_tennis_mercati_elenco_2026-10-08.sql`).
- **E5-103 [UI]** Pagina `TennisReplay.tsx` (811) + `lib/tennisReplay.ts` (504): lista per torneo (`raggruppaPerTorneo :472`), barra con simboli (`simboliTennis :304`, `NOME_SIMBOLO :263`), velocita' x1..x5 (`SPEED_OPTIONS :88`, `PLAY_NORMAL_MS 1000`, `PLAY_FAST_MS 300`), passi da `TIMELINE_BUCKET_MS = 10_000` (`:89`),
  categorie di mercato (`CATEGORIE_TENNIS :362`), ladder training con selettore mercato (`:690`) e "Azzera TUTTI gli ordini simulati" (`:702`), 3 rilevatori d'opportunita' (`RILEVATORI_TENNIS :95`: orderFlowImbalance, weightOfMoney, spreadScalp), delay del mercato (`delayMercatoMs :431`), fase di gioco (`faseTennis :456`), motivo "nessun bot" (`motivoNessunBotTennis :500`).
- **E5-104 [UI]** `tennisReplayVerificaBarra.ts` (198): verificatore della barra con controlli di dominio (break = game vinto da chi riceveva; fine set fa salire i set; tie-break; set non scendono).
- **E5-105 [UI]** `TennisReplayList.tsx` (104), `TennisTimelineSymbols.tsx` (65).

### 2.K UI tennis (live)

- **E5-110 [UI]** `TennisBotPanel.tsx` (685): per ognuno dei 4 bot una scheda (`TennisBotCard :112`): badge di stato (`TENNIS_BOT_STATUS_LABEL`, pallino pulsante), "agg. Ns fa" con segnale di stantio, "dry-run", banner d'errore rosso o ambra "[ATTESA]" (`:262-276`), campo Stake € (`:258`, serie 5 per tutti i bot), checkbox dry-run, pannello parametri a tendina,
  badge superficie del pro (`:238`), pulsante Arma/Disarma (`handleArm :550-557`, `handleDisarm :581-586`: toast "disarmo richiesto - chiusura flat in corso"), contatore bot armati, lista "Attivita'" (`:647-651`, `get_tennis_bots_state` RPC), `TennisBotEquityChart.tsx` (166; P&L aggregato `total/locked`).
  Dalla scheda un bot si arma SEMPRE in prova (`tennis_bot_arm` scrive `mode='paper'`: commento `:114-119`).
- **E5-111 [PAR]** Parametri editabili e valori di serie (`lib/tennis.ts:719-848`, ogni campo con min/max/step/hint): scalper 10 (`scalp_ticks 1`, `stop_ticks 3`, `signal_ticks 1`, `min_flow 2`, `min_size 5`, `price_min 1,2`, `price_max 6`, `one_tick_per_phase on`, `inplay_tick_enabled off`, `runner_filter favorite`);
  pro 8 (`bp_target_ticks 5`, `bp_stop_ticks 3`, `fade_target_ticks 4`, `min_matched 50000`, `price_max 3,6`, `trend on`, `adapt on`, `maker on`); FLB 6 (`lay_max 1,1`, `green_ticks 8`, `green_frac 0,5`, `rearm_mult 1,1`, `min_matched 10000`, `exit_mode hybrid`); swing 5 (`N 40`, `zin 2,0`, `er_max 0,4`, `stop_ticks 8`, `tmax 90`). **29 parametri in UI su 147 `c.get("`** (72 + 44 + 13 + 18, `grep -c`).
  Verifica a campione dei serie: tutti e 29 coincidono con i `c.get("<chiave>", <serie>)` che ho letto (pro `:152-160`, FLB `:80-90`, swing `:78-100`, scalper preset `:41-77`).
- **E5-112 [UI][PAR]** `TennisBotServiceParamsSheet.tsx` (137): il foglio parametri dei 4 bot COME SERVIZIO (`tennis_bot_service_control`, `updateTennisBotService`): stesso registro, stesso schema `ParamsSheetBase`, nessuna traduzione di chiave (commento `:1-34`).
- **E5-113 [UI]** `TennisMatchesList.tsx` (535): "Partite del Giorno" da `tennis_markets` (quote back/lay con `PriceCell :98`, `PlayerOdds :123`, badge in-play `StatusBadge :518`), preferiti in localStorage (`readFavorites :43`, `writeFavorites :55`), aggiornamento forzato (`refreshTennisOdds`, `lib/tennis.ts:122`, timeout `60_000`).
- **E5-114 [UI]** `TennisMatchStats.tsx` (633): tabellone set/game/punto con pallino del servizio (`ServerDot :122`, `SetCells :135`), storia punto per punto (`PointRow :249`, `PointTag :233`), etichetta di freschezza (`freshnessLabel :54`, `STALE_MS = 15_000` `:38`: **stesso valore di `DEFAULT_MAX_AGE_SEC = 15.0` in `scan_feed.py:44`, due costanti scritte a mano**).
- **E5-115 [UI]** `TennisLadderColumn.tsx` (241): ladder tennis (`TENNIS_LADDER_SOURCE :51`, `TENNIS_ORDER_API :60`, `normalizeMode :83` OFF/PAPER/LIVE), ordini manuali; `TennisTerminal.tsx` (320; `defaultBucketMs={5_000}` `:309`), `TennisDashboard.tsx` (33), `TennisNav.tsx` (152).
- **E5-116 [UI]** Control Room: `useTennisVivo.ts` (260; tennis vivo nella scheda partita: una sottoscrizione per evento, fonte 'canale' o 'database'), `tennisAuto.ts` (127; `leggiAutoTennis :48`, `notaAutoTennis :85`, `avvisoUsciteManuali :118`: frasi veritiere dell'auto-mode), `soloTennis.ts` (190: percorso "solo tennis a 3 euro" = Safe tennis, `STAKE_TENNIS = 3`, E3).
- **E5-117 [UI]** `lib/tennis.ts` (1.129): tipi e RPC/Realtime (`subscribeTennisMarkets :220`, `subscribeTennisNow :238`, `subscribeTennisLadder :271`, `subscribeTennisOrders :533`, `subscribeTennisPositions :551`, `subscribeTennisBots :849`, `fetchTennisBotsState`, `armTennisBot`, `disarmTennisBot`, `updateTennisBotService`, righe giornaliere `TennisBotDailyRow :1043`).
- **E5-118** Anteprima (`anteprima/tennisDati.ts` 580, `tennisFinto.ts` 153): dati finti per le fotografie della UI (`frontend/src/fotografia/snapshot/*tennis*`, 5 schermate x 4 varianti = 20 json tracciati).

### 2.L Job quote

- **E5-120** `betfair_tennis_odds.py` (par. 1.6): "Partite del Giorno" ogni 30 min, rispetto dei limiti Betfair (BATCH 8, REQ_DELAY 0,6, stop su TOO_MANY_REQUESTS), lock 47316.

Totale funzionalita' elencate: **74 voci `E5-`** (`grep -c "^- \*\*E5-"` = 74; la numerazione ha buchi fra i gruppi: 001-017 pro, 020-027 FLB, 030-036 swing, 040-043 scalper, 050-053 condotta, 060-063 punteggio, 070-074 ponte, 080-084 guardie/esecuzione, 090-093 banco, 100-105 replay, 110-118 UI, 120 job quote). Alcune voci raggruppano piu' funzioni (es. E5-080 elenca 16 funzioni di `guardie_tennis.py`, E5-081 7 di `chiusura_manuale.py`, E5-093 i controlli B1-B10/CP/UM/UF): il numero di funzioni nominate con `file:riga` e' molto piu' alto di 74.

---

## 3. DIFETTI STRUTTURALI

1. **Tre bot, tre gusci "parenti" ma NON uguali.** `e5_gemelli_funzioni.py` (stesso nome, similarita' >= 0,80 gemella, 0,50-0,80 parente):
   FLB<->PRO 9 righe in funzioni gemelle (2,0%) e 77 parenti (16,8%); FLB<->SWING 4 (0,9%) e 90 (19,6%); PRO<->SWING 2 (0,2%) e 70 (7,5%). Funzioni omonime con ratio bassissimo:
   `_residuo_non_piazzabile` 0,33 (FLB `:409-429` / PRO `:1199-1236`), 0,43 (FLB / SWING `:341-365`), 0,28 (PRO / SWING); `process_closed_market` 0,50 / 0,59 / 0,49 (FLB `:695`, PRO `:1287`, SWING `:782`);
   `_place` 0,78 / 0,70 / 0,60 (FLB `:188`, PRO `:467`, SWING `:244`); `_emit` 1,00 FLB<->PRO ma 0,00 con SWING (`:137`). Per riga: FLB<->SWING 125 righe uguali (24,1% / 20,8%), FLB<->PRO 155 (29,9% / 15,4%), PRO<->SWING 132 (13,1% / 22,0%) (`e5_gemelli.py`). Il guscio dei tre = **1.349 righe di codice su 2.122 (63,6%)** (`e5_righe_tennis_output.txt`).
   Rischio: una correzione sul residuo o sul settlement va applicata a mano in tre posti; la divergenza e' o un fix fatto in un posto solo o una scelta voluta: **non lo so, serve la lettura riga per riga** (decisione D1).
2. **Lo scalper tennis e' una copia**: 76,0% del tennis (68,2% del calcio) uguale a `scalper_bot.py` (E4 `:310`), 48 funzioni omonime, 19 identiche; le regole del 04/10 e 07/10 (scavalco, residui, taglia) non sono mai arrivate nel tennis (E4 `:330`).
3. **Codice gemello del calcio, misurato**: `tennis_live_order_worker.py` vs `live_order_worker.py`: 233 righe uguali = 7,6% del calcio / 16,1% del tennis, in blocchi >= 5 righe 113 (3,7% / 7,8%), blocchi maggiori `:346-364` ~ `:836-854` e `:836-852` ~ `:1753-1769`; 22 funzioni omonime (C). `tennis_bot_service` vs `scalper_service` 6,9%; `auto_mode` 50,0% del tennis (E4 `:311-313`).
   `tennis_db._exec_retry :63` ~ `stream/db.py:44` al 96% (G `:58`); `FrenoRifiuti` del tennis gemello di `trading/freno_rifiuti.py` (C-024); `size_legale` e' una seconda definizione delle regole di taglia (C-036).
4. **Valori di serie in due lingue, 29 su 147**: la UI conosce 29 parametri su 147 `c.get(` (19,7%); gli altri non sono editabili ne' visibili. I valori sono scritti due volte (Python e `lib/tennis.ts`), con letterali Python con `_` (`50_000.0` `tennis_pro_bot.py:157`; `10_000.0` `tennis_flb_bot.py:89`, `tennis_swing_bot.py:98`; `60_000` `:152`) che un `grep 50000` non trova;
   e TS (`lib/tennis.ts:122` `60_000`, `:412` `90_000`; `tennisReplay.ts:210` `60_000`; `TennisReplay.tsx:89` `10_000`; `TennisTerminal.tsx:309` `5_000`; `TennisMatchStats.tsx:38` `15_000`). E' il difetto n. 33 del catalogo (`condotta_ordini.py:7-9` lo cita: "costante nel frontend che duplica una scelta del backend"). Il test `lib/tennisRegistry.test.ts` esiste (intestazione "scheda tennis_pro (fix audit #9)"; non l'ho letto per intero: non so se copre le chiavi degli altri tre bot).
5. **Dossier invecchiato come "spec" del banco**: `registro_bot.py` indica `TENNIS_BOT_DOSSIER.md` come spec dei 4 bot ma il dossier dice cose false (stop 1/min_flow 10 dello scalper; Lab in `tennis_scalper/`; 5 classi). Il dossier ha 655 righe e non e' piu' la verita'.
6. **Package di produzione con 1.164 righe di ricerca a mano** (7 file senza importatori, par. 1.1) e `tennis_serve_data.py` che serve solo la Safe: i bot tennis non ne hanno bisogno, il registro del banco non li elenca.
7. **Attese di rete nel percorso critico**: il bot non aspetta la rete (riceve `strat.score` dal worker), ma il punteggio arriva con tre cadenze in cascata (fino a 6,5 s calcolati, par. 1.5) e il fallback `get_scores` diretto per evento e' una chiamata REST sincrona dentro il worker del runner (`tennis_runner.py:1619-1650`).
8. **Il job quote fa un login Betfair nuovo a ogni run: 48 al giorno** (`betfair_tennis_odds.py:311-312`, `desktop/main.js:481`) e svuota la tabella del giorno prima di riscriverla (`:274, 278`).
9. **Letture di polling del DB: 44,4 richieste/min (ponte) + 28,4 (runner)** secondo 07 (via G `:79`), in gran parte lettura di `tennis_live_follow`, `tennis_bot_control`, `tennis_bot_service_control`: sono controlli che il canale 47337 (sveglia) puo' sostituire (G `:295`).
10. **Registrazioni tennis solo su una macchina e un giorno** (par. 1.7): non riproducibile fuori dal PC dell'utente; una sola giornata di mercato (07/07/2026), 89 partite, 65 MB.
11. **Controlli mai sollecitati nei referti**: sul pro `B6` (FLB, ovvio non applicabile), `B10` e `CP2` ("MAI SOLLECITATI: 3 controlli su 22", `AUDIT_2026-10-08/banco_attraversa/tennis_dopo.txt`, in coda) = il referto dice "non lo so", non "sano" (catalogo §7 / §6.9: falsificazione).

---

## 4. DOMANI

### 4.1 Dove vive ogni funzionalita'

```
bots/tennis/
  COSA_FA.md                     (E5-001..E5-120 in prosa)
  contratto.py                   (RegoleBot, Decisione, StatoPartita, Parametro)
  catalogo_parametri.json        (UNICA fonte dei 147 parametri: chiave, tipo, serie, min, max, step, hint, in_ui: bool)
  pro/regole.py                  (E5-001..E5-016, solo decisioni: segnali, regime, uscite in tick; ~488 righe di codice)
  flb/regole.py                  (E5-020..E5-026; ~175)
  swing/regole.py                (E5-030..E5-035; ~110)
  scalper/regole.py              (E5-040..E5-042 + parte tennis; ~457, E4)
  guscio/                        (piazza, cancella, residui, uscita manuale, settlement: UNA copia con ganci; E5-017/-027/-036/-043/-050..053)
  punteggio/                     (TennisScore, parse, winprob, superficie: E5-060..063)
  replay/                        (importa, convertitore, caricamento: E5-100..102)
  test_contratto.py
```
La UI (registro TS, fogli parametri, `parametri_modificabili_*` del banco) **deriva** da `catalogo_parametri.json`: sparisce la copia a mano in `lib/tennis.ts:719-848` e il rischio dei letterali con `_`.

### 4.2 Contratto proposto (Python)

```python
class StatoPartita(TypedDict):            # da tennis_score.TennisScore
    sets: tuple[int,int]; games: tuple[int,int]; punto: tuple[str,str]
    servizio: Literal["home","away",None]; point_pressure: bool; eta_s: float | None

class Decisione(TypedDict):
    azione: Literal["nessuna","apri","chiudi_parziale","chiudi_tutto"]
    selezione: int; lato: Literal["BACK","LAY"]; prezzo: float; motivo: str   # motivo = nome del setup/regola

class RegoleBot(Protocol):
    nome: str
    def parametri(self) -> list[Parametro]: ...          # dal catalogo
    def decidi(self, book: BookView, punteggio: StatoPartita | None,
               posizione: PosizioneView, ora_ms: int) -> Decisione: ...
# eventi esposti: entry, entry_timeout, green_placed, staged_green, stop, scratch, residuo, uscita_proposta (gia' emessi da _emit)
# eventi consumati: book (publish_time_ms), punteggio, chiudi_ora, modalita (OFF/PAPER/LIVE), uscite_automatiche
```
Interfaccia TS: `TennisBotDescriptor` generata dal catalogo (tipi gia' in `lib/tennis.ts:650-680`, `TennisBotParamField`, `TennisBotDescriptor`).
**Le decisioni NON cambiano**: `decidi()` e' l'estrazione meccanica delle funzioni `[S]` di questa scheda (stesse soglie, stessi tick, stesso ordine dei setup).

### 4.3 Stima righe DOPO (righe di CODICE, calcolo mostrato)

| Voce | Oggi | Domani | Come |
|---|---:|---:|---|
| Strategia pro + parametri | 427 + 61 | 488 | resta (e' strategia) |
| Strategia FLB | 161 + 14 | 175 | resta |
| Strategia swing | 91 + 19 | 110 | resta |
| Guscio dei 3 (pro/FLB/swing) | 1.349 | ~1.020 | stima: nomi comuni a tutti e tre (`_emit,_place,_cancel,_residuo_non_piazzabile,process_closed_market,_orologio_s,_pubblica_proposte,uscita_manuale_finita,check_market_book`) = FLB 130 + PRO 145 + SWING 151 = 426 righe -> una copia con ganci ~170: -256; uscita manuale (PRO 37 + SWING 65 + FLB ~80 = ~182) -> ~100: -80; totale ~ **-330** (25% del guscio). Il resto del guscio (`_manage`, `_surveil_closing`, `_green`) e' specifico e diverge: non si unisce senza lettura |
| Scalper tennis | 1.906 | 457 + 1.449 condivisi | E4: `scalper_core` tiene 1.449 una volta sola (E4 `:456`), il tennis tiene 457 solo suoi |
| Totale codice tennis-owned dei 4 bot | 4.028 | ~2.250 | 773 + 1.020 + 457; i 1.449 condivisi sono contati in E4 |

Altre voci (righe di file, non di codice): 7 file di ricerca (1.164) fuori dal package di produzione (in `laboratorio/`, decisione D2: -1.164 dal perimetro produzione, 0 cancellate); `tennis_db.py` (869): client + retry (`get_tennis_client :54-60`, `_exec_retry :63-77`, `_now_iso :79`) assorbiti da `db_client.py` unico (G `:340`, G-006/G-007): ~-40; `tennis_live_order_worker.py` + `condotta_ordini.py`: assorbiti dalla porta ordini unica (C), non quantificato qui.
**Condivisibile col calcio ("sport come parametro")**: motore maker 1.449 (E4), `FrenoRifiuti` e `size_legale` (C-024, C-036), `_exec_retry`, le 19 funzioni identiche dello scalper (E4 `:318`), `_place`/ordini (C). Specifico del tennis: punteggio/IPS, superficie, regime ER del pro, z-score del swing, FLB, replay tennis.
Ripartizione 3 bot oggi: strategia 679 (32,0%) / parametri 94 (4,4%) / guscio 1.349 (63,6%) su 2.122.

### 4.4 Cosa cambia per sostituire un bot

- **OGGI**, per cambiare una regola del FLB tocco: `tennis_flb_bot.py` (ctor `:80-111`, regole `:332-597`), `lib/tennis.ts` (registro `:719-848`), `tennis_live/tools/replay_bot.py` (`parametri_modificabili_tennis_flb`), `registro_bot.py:374`, `TENNIS_BOT_DOSSIER.md`, `tennis_runner.py:126-131` (`_BOT_REGISTRY`), `tennis_bot_service.py:220` (`_BOT_KEYS`) e la UI.
  **DOMANI** tocco solo `bots/tennis/flb/` (regole + riga del catalogo) e i suoi test di contratto.
- **Gia' in librerie mature e oggi riscritto**: i tick e i prezzi (`ticks_between`, `get_nearest_price`, `price_ticks_away`) sono di flumine (`flumine.utils`) e il codice li usa (OK); `parse_tennis_scores` + `TennisScore` ricostruiscono a mano cio' che `betfairlightweight.in_play_service` restituisce (dict lightweight) - resta (formato non ufficiale);
  `with_backoff` in `net_retry.py` riscrive un retry che `tenacity`/`urllib3.Retry` darebbero (G-006, non verificato che si possa sostituire senza cambiare i tempi 3 x 0,15-1,0 s).

---

## 5. PARITA'

**Registrazione**: `C:\Users\Admin\Desktop\tennis_rec\20260707\` (par. 1.7), partita di riferimento `35790089` (raw 841.467 B, 5.216 tick, 5.212 decisioni, qualita' COMPLETE 92,4% con 5 buchi dichiarati, 104 campioni di punteggio dal sidecar); per FLB `35794049` (8.608 tick).
**Comando**: `python -m Betfair.stream.backtest.certifica tennis_pro 35790089 --scenari tutti` (e `tennis_flb`, `tennis_swing`, `tennis_scalper`); entrata unica del banco (CLAUDE.md).
**Scenari**: i 17 del par. E5-091. Tempo: **18,9 s su 17 replay** (`AUDIT_2026-10-08/banco_attraversa/tennis_dopo.txt`, ultima riga) e 23,2 s su 17 (`AUDIT_2026-10-07/replay_conformita_tennis_pro/tennis_pro_tutti_dopo_COORDINATORE.txt`): obiettivo 300 s, tetto 600 s. FLB su 35794049: 15,7 s su 6 replay (`AUDIT_2026-10-04/replay/tennis_flb_35794049_TETTO.txt:122`). **Dichiaro: durata attesa ~20 s, ben sotto i 10 minuti.**
**Numeri che devono coincidere (pro, 35790089, riferimento coordinatore 07/10)**: `base` tick=5.216 decisioni=5.212 azioni=0; `gate-aperto` azioni=7 stati=OPEN,CLOSING, residui dichiarati 1 (0,03 EUR, sbilancio 0,04), regolati col mercato 1 (se vince -0,04 / se perde 0,00); `dry-run` azioni=0; `bot-fermo` decisioni=2.483; `rifiuti-betfair` azioni=2; `live` azioni=7 (stati OPEN,CLOSING). Piu' i tempi non vincolanti (4,2 s in `certifica_dopo.txt` riga `tempo:`, 1.230 tick/s).
**UI**: fotografie `frontend/src/fotografia/snapshot/{tennis,tennis-terminal,tennis-terminal-match,tennis-replay,storico-tennis}.{off,v2}[.guscio].json` (20 file); `lib/__fixtures__/replay_tennis_35790089.json`; `esito_tennis_scalper.json`, `esito_tennis_swing.json`; test `tennisRegistry.test.ts`, `tennisReplay.test.ts`, `tennisReplayVerificaBarra.test.ts`, `TennisBotPanel.test.tsx`, `TennisBotServiceParamsSheet.test.tsx`, `soloTennis.test.ts`, `tennisAuto.test.ts`, `useTennisVivo*.test.ts`.
**Prova che l'estrazione `decidi()` non cambia nulla**: replay prima/dopo con `--scenari tutti` su `35790089` per i 4 bot, referto identico "numero per numero" (decisioni, azioni, stati, residui) e `impronta` del codice diversa e dichiarata (il referto riporta "codice bot <hash> (N file)").
**Voci di `PROCESSO_STANDARD_BOT.md`**: §6 (dati di mercato reali raw; servizio intero via `_instantiate_bot`; ciclo di vita dell'ordine con parziali e bet delay `paper_execution.py:43`; persistenza `_mirror_order`; scenari; falsificazione; referto riproducibile) e §7 n. 33 (costante frontend che duplica il backend: E5 difetto 4), n. 19 (stato in RAM perso al riavvio: scenario `riavvio`), parita' paper/live (scenari `live`, `soldi-veri-paper`), stati e fasi (`OPEN,CLOSING`). **Copertura mancante**: nessuna registrazione di un cambio di superficie/torneo diverso da quelli di una giornata; il pro non e' mai stato esercitato con `B10` e `CP2` (difetto 11).

## 6. MIGRAZIONE

1. **Passo 0 (zero rischio)**: copiare 3-5 partite tennis scelte (es. `35790089`, `35794049`, `35797566`) in `registrazioni_banco/` compresse (come le 2 del calcio, ~5 MB) cosi' il banco gira ovunque (decisione D3). Aggiornare `_cartella_tennis` per cercare anche li'.
2. **Passo 1**: `catalogo_parametri.json` generato dai 147 `c.get(` + genera `lib/tennis.ts` registro e `parametri_modificabili_*`. Parita': test che confronta serie Python vs catalogo vs TS (rosso se un `50_000.0` e `50000` divergono: falsificazione cambiando un valore).
3. **Passo 2 (ombra)**: `bots/tennis/<bot>/regole.py` estratte meccanicamente; il bot vecchio e il nuovo girano in replay sulla stessa registrazione e il banco confronta le `Decisione` book per book (interruttore `TENNIS_REGOLE_V2` spento di serie, lo accende solo l'utente).
4. **Passo 3**: guscio unico con ganci (-330 righe) un bot per volta: FLB (il piu' semplice), swing, pro; ogni passo con `--scenari tutti` identico. Le funzioni a ratio < 0,5 si uniscono SOLO dopo la decisione D1.
5. **Passo 4**: scalper tennis dopo E4 (`scalper_core`, ordine di E4 `:503-510`).
6. **Passo 5**: 7 file di ricerca in `laboratorio/` (D2); `tennis_replay` sotto `bots/tennis/replay/`.
7. **Ordine rispetto agli altri**: dopo A (connessione/punteggio feed), C (porta ordini, `condotta_ordini`), D (OspiteFlumine), G (client unico) ed E4 (D `:510` "Scalper e tennis per ultimi"). Il tennis e' paper (il live lo accende solo l'utente); nessun passo tocca la modalita'.
8. **Rischi**: divergenza silenziosa tra i gusci (D1); le regole del 04/10 e 07/10 assenti nel tennis che un'unione porterebbe dentro (E4: cambiare la strategia: serve decisione); registrazioni su una sola macchina.
9. **Ritorno indietro**: interruttore spento = classe vecchia (rimasta); il catalogo si rigenera.

## 7. MISURE

| Cosa | Oggi (fonte) | Obiettivo dopo |
|---|---|---|
| Righe di file del perimetro | 25.775 (somma `wc -l` sopra) | ~22.000 (stima: -1.164 ricerca, -330 guscio ~ -430 file, -1.949 scalper via E4, -40 db) - da rimisurare |
| Righe di codice dei 4 bot | 4.028 (1.004 + 518 + 600 + 1.906) | ~2.250 + 1.449 condivise (E4) |
| Letterali numerici con `_` nel perimetro tennis | Py 10 (`grep -rnE`: 4 nei 3 bot, 6 nello scalper), TS 6 | 0 duplicati: valori solo nel catalogo |
| Parametri visibili in UI / totali | 29 / 147 (19,7%) | deciso dall'utente (D5); campo `in_ui` nel catalogo |
| `.table(` in `tennis_db.py` | 39 (31 funzioni) | 39 invariate come dati; client/retry uniti (G) |
| Richieste DB al minuto (tennis) | ponte 44,4 + runner 28,4 (07 via G `:79`) | polling di controllo -> sveglia dal canale 47337 (G `:295`); misura con `m04_chiamate_db.py` (G `:362`) |
| Latenza punteggio -> bot | fino a 6,5 s calcolati (2,0 + 2,5 + 2,0); IPS non misurata | misurata con lo script descritto nel par. 1.5 punto 5; obiettivo: 1 sola cadenza (il bot legge dal canale) |
| Login Betfair del job quote | 48/giorno (calcolo) | 1 sessione unica o riuso (A) |
| Certificazione tennis | 18,9 s / 17 replay (`tennis_dopo.txt`) | invariata (<= 25 s) |
| Giornate di registrazione tennis | 1 (07/07/2026), 89 partite, 65 MB | >= 3 giornate, di cui 3-5 partite nel repo |

---

## Decisioni per l'utente

- **D1** Le funzioni omonime dei gusci di pro/FLB/swing divergono (residuo 0,28-0,43, settlement 0,49-0,59, `_place` 0,60-0,78). Quale versione e' quella giusta per ognuna? Senza risposta si unisce solo il banale (`_cancel`, `_emit`, `check_market_book`).
- **D2** Spostare i 7 file di ricerca (`record_multi`, `backtest_pro`, `tune_tennis`, `run_tennis_pro`, `flb_backtest`, `research_data`, `record_tennis`: 1.164 righe) fuori dal package di produzione `tennis_scalper/` verso `laboratorio/`?
- **D3** Copiare 3-5 partite tennis (compresse) in `registrazioni_banco/` e/o registrare altre giornate tennis, cosi' il banco non dipende da `~/Desktop/tennis_rec` e da un solo giorno?
- **D4** Vuole che l'UI mostri/modifichi piu' dei 29 parametri su 147 (non cambia la strategia, cambia solo cosa e' visibile)?
- **D5** Il dossier `TENNIS_BOT_DOSSIER.md` e' la "spec" dichiarata del banco ma e' invecchiato (stop 1/min_flow 10, Lab): lo si riscrive dal codice (COSA_FA.md) e si smette di chiamarlo spec?
- **D6** (E4 D2) Le regole del 04/10 e 07/10 dello scalper calcio arrivano al tennis? Sarebbe cambiare la strategia: non lo faccio di iniziativa.
- **D7** Il job quote fa un login Betfair a ogni run (48/giorno): lo si porta sul processo unico di connessione (A) o va bene cosi'?

## Cosa ho verificato di persona

- Contati con `wc -l`: tutti i file del perimetro; `grep -c "\.table("` = 39 e ogni riga letta con `grep -n`; `grep -c 'c\.get("'` = 72/44/13/18.
- Letto per intero: `tennis_flb_bot.py:1-143` e le regole `:332-400`, `:431-597`; swing `:73-135`, `:402-470`, `:635-708`; pro `:102-255`, `:313-428`, `:579-726`, `:793-876`, `:984-994`; `run_tennis_scalper.py:40-100`; `betfair_tennis_odds.py:1-38, 197-322`; `desktop/main.js:470-500`; `tennis_runner.py:124-140, 893-1040, 1595-1740`; `scan_feed.py:36-52`; `registro_bot.py:20-60, 160-420`.
- Eseguito (sola lettura, nessun codice di produzione): `e5_righe_tennis.py`, `e5_gemelli.py` (flb/swing, flb/pro, pro/swing, swing/scalper, flb/scalper, live_order_worker, db), `e5_gemelli_funzioni.py` (3 coppie).
- Registrazioni: `ls`, `du`, `find` su `tennis_rec` e `_live_raw`; letti i referti `tennis_dopo.txt`, `certifica_dopo.txt`, `tennis_pro_tutti_dopo_COORDINATORE.txt`, `tennis_flb_35794049_TETTO.txt`.

## Cosa NON ho potuto verificare

- La latenza reale dell'IPS e il ritardo punteggio->bot (solo calcolo sulle costanti; manca lo script di misura).
- Il corpo di `tennis_scalper_bot.py` (2.974) e di `tennis_live_order_worker.py`, `esecutore_tennis.py`, `tennis_bot_service.py` oltre agli indici: le funzionalita' E5-040..043, 070..084 poggiano sugli indici di funzione e sulle schede C/D/E4, non sulla lettura riga per riga.
- Il contenuto di `superficie.py` (tabella torneo->superficie), `TennisMatchStats/MatchesList/Terminal/LadderColumn` oltre ai nomi dei componenti e ai commenti d'intestazione, `tennisRegistry.test.ts` per intero, `certificazione_bot.py` oltre all'indice e ai testi dei referti.
- Quali controlli del banco coprono FLB nel suo referto (19 controlli): ho solo l'intestazione; per il pro "mai sollecitati" sono 3 su 22.
- Le frequenze per tabella sono quelle di 07/G, non rimisurate; il numero esatto di funzionalita' UI (la UI e' stata letta per intestazioni e stringhe, non pannello per pannello).
- Le righe `:858-860` (controllo "mai due trade nello stesso game") e `_intervallo_bot_control :1580`-area sono indicate come area, non come riga esatta.
