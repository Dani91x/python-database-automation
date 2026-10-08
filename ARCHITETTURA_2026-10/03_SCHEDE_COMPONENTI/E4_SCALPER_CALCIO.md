# SCHEDA DI COMPONENTE E4 - SCALPER CALCIO (maker, sniper, theta, media under)

Data: 08/10/2026. Autore: delegato Sonnet (piano di architettura). Prefisso funzionalita': `E4-`.
Regole: solo documento; nessun codice toccato; la logica di trading e' intoccabile (CLAUDE.md, brief comune).
Strumenti usati: `grep -n`, `sed -n`, `wc -l`, `ARCHITETTURA_2026-10/strumenti/e4_gemelli_tennis.py` (rieseguito, anche
con coppie diverse), referti `AUDIT_2026-10-08/banco_attraversa/calcio_prima.txt`, `calcio_prima_tutti.txt`,
`calcio_dopo_5.txt`. Schede gia' pronte e citate (non rifatte): D (contratto runtime), A (connessione), C (porta
ordini), `00_INVENTARIO.md`.

Perimetro (righe = `git ls-files ... | xargs wc -l`):

| Gruppo | File | Righe |
|---|---|---:|
| Strategie calcio | `Betfair/stream/scalper/scalper_bot.py` 3.315, `sniper_bot.py` 1.387, `theta_bot.py` 1.313, `media_under_bot.py` 2.637, `risk_semaphore.py` 92, `bias_resolver.py` 229 | 8.973 |
| Guscio (sessione, supervisore, auto-mode, CLI) | `scalper_session.py` 2.303, `scalper_service.py` 982, `auto_mode.py` 440, `run_scalper.py` 152, `run_scalper_live.py` 292, `run_theta.py` 289, `habitat_scan.py` 196 | 4.654 |
| Banco (adattatore, controlli) | `certificazione.py` 2.472, `tools/replay_registrazioni.py` 3.803 | 6.275 |
| Atlante hazard (NON e' scalper: serve Mike, Omega, Safe) | `atlante_a_domanda.py` 532, `atlante_v4.py` 848, `genera_atlante.py` 1.289, `hazard_atlas.py` 425, `hazard_atlas_sync.py` 213, `tools/` 551, `validazione_hazard/` 2.180 | 6.038 |
| `__init__` | `scalper/__init__.py` 34, `tools/__init__.py` 1 | 35 |
| Totale cartella `Betfair/stream/scalper/` (codice, senza test) | | 25.975 |
| Usati dal di fuori della cartella | `Betfair/stream/trading/{minimi_it 147, freno_rifiuti 124, stato_mercato 267, submin 1.167, controls 524}`, `Betfair/stream/uscite_proposte.py` 309, `live_order_build.py` 942 | 3.480 |
| Frontend (non test) | `components/live/ScalperPanel.tsx` 975, `lib/scalperControlRoom.ts` 662, `lib/mediaUnder.ts` 465, `lib/scalper.ts` 175, `lib/scalperCanale.ts` 131, `lib/mediaUnderAttiva.ts` 22, `anteprima/scalperFinto.ts` 20 | 2.450 |
| Test Python scalper/sniper/theta/media (almeno 16 file in `Betfair/stream/tests/`) | vedi par. 5 | >= 4.879 |
| Test frontend scalper (12 file) | | 1.780 |
| Laboratorio (copia, fuori produzione) | `laboratorio/scalper_lab/*` | 3.943 |

Il nucleo di E4 (strategie + guscio, senza banco e senza Atlante) pesa **13.627 righe** (8.973 + 4.654).

---

## 1. OGGI

### 1.1 Responsabilita' reali (lette dal codice)

Lo scalper calcio e' una famiglia di QUATTRO strategie flumine (`BaseStrategy`) che vivono nello STESSO processo di sessione:
maker `ScalperStrategy` (`scalper_bot.py:390`), sniper `SniperStrategy` (`sniper_bot.py:90`), theta `ThetaStrategy`
(sottoclasse dello sniper, `theta_bot.py:339`), media under `MediaUnderStrategy` (`media_under_bot.py:898`). Il processo di sessione
e' `scalper_session.run_session` (`scalper_session.py:1324`), lanciato UNA VOLTA PER PARTITA dal supervisore `scalper_service`
(`_spawn`, `scalper_service.py:702`): login Betfair e `Flumine` propri (scheda A, riga 6 della tabella dei flussi,
`A_CONNESSIONE_BETFAIR.md:80`). Gli ordini li piazza la strategia stessa con `market.place_order`
(`scalper_bot.py:2924`; scheda C, strada S6, `C_PORTA_ORDINI.md:49`). Nel contratto di D lo scalper e' un `OspiteFlumine`
(`D_RUNTIME_BOT_CONTRATTO.md:403-405`): le classi flumine restano, cambia il guscio.

### 1.2 Dipendenze in ENTRATA (chi importa lo scalper), `grep -rln` su `Betfair/` e `main.py`

- **Altri bot calcio**: `Betfair/mike/engine.py:33` importa `ticks_between` da `scalper_bot` (accoppiamento: Mike dipende dal
  maker per una funzione di 12 righe). `Betfair/mike/dossier.py:30,324`, `Betfair/omega/omega_advisor.py:215`,
  `Betfair/safe_strategy/{engine.py:52, opportunity.py:656-658, selezione.py:87,109, service.py:3427}` importano
  l'ATLANTE (`hazard_atlas`, `atlante_v4`, `hazard_atlas_sync`) che sta nella cartella scalper ma non e' scalper.
- **Tennis**: `Betfair/stream/tennis_live/{auto_mode, paper_execution, certificazione_bot, tennis_runner}.py` e
  `Betfair/stream/tennis_scalper/{condotta_ordini, tennis_scalper_bot, tennis_flb_bot, tennis_pro_bot, tennis_swing_bot, tennis_score,
  run_tennis_scalper, tune_tennis}.py` nominano scalper/scalper_session/scalper_bot (pattern del grep; non ho letto uno per uno cosa
  importano: `tennis_scalper_bot.py:274` dice di se' "COPIA di scalper_bot.ScalperStrategy").
- **Altro**: `Betfair/stream/{canale_bot.py, config_stream.py, reconcile_worker.py}` (citazioni), `Betfair/stream/backtest/registro_bot.py`
  (registrazione del bot nel banco, `registro_bot.py:312-338`), `backtest/tools/misura_punto8/x1_bias.py`.
- **Frontend**: `ScalperPanel.tsx` (pagina Segui Live: `pages/SeguiLive.tsx`), `components/omega/MissionCard.tsx:23` (secondo punto di
  accensione: `activateScalper, stopScalper, fetchScalperState`), `components/controlroom/{PannelloBot.tsx, useControlRoom.ts, chiudiRiga.ts}`,
  `lib/{controlRoom.ts, interruttori.ts}`. Il ladder (`DutchingPanel.tsx`, `XHedgePanel.tsx`) NON opera sullo scalper: li' "Pattern
  ScalperPanel" e' solo un commento (`DutchingPanel.tsx:153`, `XHedgePanel.tsx:220`).

### 1.3 Dipendenze in USCITA

`flumine` (BaseStrategy, Trade, LimitOrder, utils), `betfairlightweight` (filtri stream), `Betfair/stream/auth.build_client`,
`..trading.minimi_it` (minimi `.it`, fonte unica), `..trading.freno_rifiuti`, `..trading.stato_mercato` (guardia mercato sospeso),
`..trading.submin` (place-and-trim), `..uscite_proposte` (proposte e firme), `..live_order_build.round_to_tick`,
`..engine.live_trading_strategy.LiveTradingStrategy` (specchio ordini), `config_stream`, `db_client.get_supabase_client`
(`scalper_session.py:1211`, `scalper_service.py:71`) e, caso notevole, **`Betfair.safe_strategy.execution._live_brake`**
(`scalper_session.py:230-247`): lo scalper dipende dal modulo di Safe per il freno dei soldi veri.

### 1.4 Processi, thread, orologi, stato condiviso

- Processi: supervisore `scalper_service` (1) + una sessione `scalper_session` per partita armata (tetto auto-mode: 2 di serie, 4 al
  massimo, `auto_mode.py:71-72`; ogni sessione = un login e un `Flumine`, scheda A).
- Thread nella sessione: flumine (`threading.Thread(target=framework.run)`, `scalper_session.py:1845`), `mantieni_sessione`
  (keep-alive, `:1857`), specchio ordini (`_order_mirror_loop`, tick 1 s, `:1140-1165`), `scalper-freno` (`:2032`), `ht-watcher`
  (`:1883`), `sniper-line` (`:1902`), `theta-score` (`:1968`), `theta-confirm` (`:1973`), poi il ciclo del battito nel thread principale
  (`while runner.is_alive(): time.sleep(HEARTBEAT_S)`, `HEARTBEAT_S = 5.0`, `:35`, ciclo `:2038-2125`).
- Orologi: le strategie usano il `publish_time` del book (mai il wall-clock) per le regole di mercato
  (`scalper_bot.py:818-821, 842-845`); il wall-clock compare in `max_txn_hour` (`:2846-2854`), nei `dry_run` (`:2856-2866`) e nel
  battito. Supervisore: `POLL_S = 3.0` (`scalper_service.py:43`).
- Stato condiviso: tabella `scalper_control` (una riga per evento: status, params, stats, heartbeat), `scalper_activity` (diario),
  `betfair_live_orders` (specchio), buffer `buf` del sink (`scalper_session.py:1338-1347`, coda massima 400 righe, taglio a 200).

### 1.5 Tabelle del DB: le 20 + 16 chiamate DIRETTE (`grep -n "\.table("`), cosa, quando

**`scalper_session.py` (20 chiamate `.table(`: 8 nella classe `Db` + 12 dirette `db.sb.table`)**, piu' 47 punti di chiamata ai metodi di `Db`
(`grep -c "db\.(set_control|control_status|control_stato_e_params|get_control|follow|prediction|log|log_many)("` = 47):

| Riga | Tabella e operazione | Quando |
|---:|---|---|
| 1220 | `scalper_control` UPDATE (`Db.set_control`) | stato, battito, stats, fine sessione (v. 1384, 1446-1452, 1839, 2051, 2227, 2258) |
| 1229 | `scalper_control` SELECT `status` (`control_status`) | controllo dello stato |
| 1241 | `scalper_control` SELECT `status,params` (`control_stato_e_params`) | **ogni battito (5 s)**, `:2090`: params vivi, stop dalla UI, comando media |
| 1250 | `scalper_control` SELECT `*` (`get_control`) | all'avvio `:1362` |
| 1255 | `live_follow` SELECT (`Db.follow`) | all'avvio `:1399` (mercati e fixture dell'evento) |
| 1262 | `fixture_predictions` SELECT (`Db.prediction`) | all'avvio, bias (`_resolve_bias` `:1286-1323`) |
| 1270, 1281 | `scalper_activity` INSERT (`Db.log`, `Db.log_many`) | `log`: eventi di sessione (47 punti); `log_many`: svuotamento del buffer delle strategie a ogni battito (`flush`, `:1344-1347, 2040`) |
| 709 | `live_alerts` INSERT | esito dell'arresto (`chiudi_all_arresto`, `:667-719`) |
| 859 | `live_alerts` INSERT | crash di flumine (`_handle_flumine_crash`, `:824-872`) |
| 962 | `betfair_live_orders` SELECT | media under: ordini del conto per la ripresa e il riquadro (`leggi_ordini_conto_media`, `:934-976`), un giro per battito, solo soldi veri a posizione aperta (`:2043-2047` commento) |
| 1075 | `live_alerts` INSERT | stream muto/ripreso (`sorveglia_flusso_sessione`, `:1050-1093`) |
| 1699 | `live_alerts` INSERT | allarme in fase di arma (`:1684-1700`) |
| 1756, 1891, 1911 | `live_now` SELECT (minute, inplay, gol) | thread `ht-watcher` / `sniper-line` / `theta-score`: polling del minuto |
| 1936, 1947, 1958 | `theta_confirm_requests` INSERT / SELECT / UPDATE | solo theta in modo conferma manuale (ThetaConfirmBus) |
| 2064 | `live_alerts` INSERT | riconciliazione bot-ordini: divergenze ledger (`:2058-2086`) |

**`scalper_service.py` (16 chiamate: 14 nella classe `Db` + 2 dirette)**:

| Riga | Tabella e operazione | Quando |
|---:|---|---|
| 75, 81 | `scalper_control` SELECT (`.in_` stati) / UPDATE | giro del supervisore (ogni `POLL_S` = 3 s): elenco delle righe vive, stato |
| 86 | `scalper_activity` INSERT | diario del supervisore |
| 94, 102 | `scalper_service_control` (`TABELLA_SERVIZIO`, id=1) SELECT / UPDATE | riga del servizio: battito, stats auto-mode (`_scrivi_stats`, `:570`) |
| 110 | `safe_strategy_scan` SELECT | feed calcio per l'auto-mode (`Db.feed_calcio`) |
| 128 | `safe_strategy_status` SELECT `updated_at` | battito dello scanner |
| 147, 214 | `scalper_control` SELECT | `righe_control`, `riga_control` |
| 163, 184 | `live_follow` SELECT / UPSERT | `follows` / `segui` (l'auto-mode "segue" la partita per far registrare i dati) |
| 195, 197, 208 | `scalper_control` UPSERT / UPDATE | `arma` (nuova riga per l'auto-mode), `ferma_auto` |
| 671 | `live_alerts` INSERT | `marca_orfana` (sessione morta) |
| 890 | `scalper_activity` INSERT | ciclo `_habitat_loop` (`:880-904`) |

Fuori da `.table(`: l'RPC `get_live_settings` (`freno_supervisore` `:685`, `controls.motivo_kill_switch`). **Misura**: il solo supervisore fa
**54 chiamate/min** (18 `GET scalper_control` + 18 `POST rpc/get_live_settings` + 18 `GET scalper_service_control`, finestra 60 s del
02/10 15:15:40-15:16:40; finestra 300 s: 276 chiamate = 55/min) - `SCHEMI_BOT/sistema/MISURE_2026-10-02.md:46, 176-184`. **Le
sessioni di partita non sono nella tabella delle misure del 02/10** (non c'era una sessione viva): per il battito a 5 s il minimo
leggibile dal codice e' 3 giri DB (flush, `set_control` del battito `:2051`, `control_stato_e_params` `:2090`) = 36/min per sessione
piu' lo specchio (par. 1.6): **non misurato**, strumento: lo stesso script di `MISURE_2026-10-02` lanciato con una sessione viva.

**Nessuna chiamata di rete o DB dentro le strategie**: `grep -n "\.table(\|\.rpc(\|requests\.\|urlopen\|time\.sleep\|supabase\|db_client"` su
`scalper_bot.py sniper_bot.py media_under_bot.py theta_bot.py auto_mode.py risk_semaphore.py` = 0 risultati. Le strategie parlano con
l'esterno solo dal sink `event_sink` (buffer in RAM) e dagli oggetti iniettati dalla sessione.

### 1.6 Percorso tick -> decisione -> ordine e DOVE sono le attese

1. Stream Betfair -> thread stream di flumine -> `check_market_book` (`scalper_bot.py:769`) -> `process_market_book` (`:817`).
   Attesa: rete Betfair (scheda A; campi e conflation della sessione: `A_CONNESSIONE_BETFAIR.md:95-99`, non rimisurati qui).
2. Decisione: ciclo sui runner (`:869`); calcolo di `micro_price`, flusso `_update_flow` (`:893`), gate, macchina a stati dello slot. Solo CPU,
   zero I/O (grep del par. 1.5). Costo misurato dal banco, intera sessione (4 strategie, specchio, controlli): **665.941 tick in 53,0 s =
   12.559 tick/s** (`calcio_dopo_5.txt`, riga `tempo: 35797769 [base]`).
3. Cancelli prima dell'invio, in `_place` (`scalper_bot.py:2743-2915`): `guardia_flumine` (stato mercato, `:2811`), **`freno_live()`**
   (`:2818-2833`, solo per le APERTURE: `floor_min`), `FrenoRifiuti.bloccato` (`:2835-2843`), tetto transazioni (`:2846-2854`).
   **Attesa nel percorso critico**: `freno_live` e' `freno_soldi_veri` (`scalper_session.py:1808-1812`) = `Safe._live_brake()`
   (`safe_strategy/execution.py:138-168`) = riga `betfair_live_settings` riletta "al massimo ogni `ETA_RILETTURA_BOT_S`" e kill-switch con
   cache ~2 s (`trading/controls.py:107-135`, RPC `get_live_settings`). E' una LETTURA DB (rete verso Supabase) eseguita nel thread della
   strategia, nel momento di aprire una posizione, quando la cache e' scaduta. Non ho misurato la latenza di quella lettura ne' verificato
   se l'assegnazione `:1808` e' condizionata a soldi veri.
4. Invio: `market.place_order(order)` (`:2924`): flumine mette l'ordine nel suo esecutore; l'HTTP verso Betfair e' fuori dal thread della
   strategia. `_esegui_place` legge solo l'accettazione locale (violazione dei controlli flumine). Attesa: andata e ritorno HTTP +
   bet delay in-play (nel banco "book in ritardo: 589.606", `calcio_dopo_5.txt`).
5. Esito: l'ordine torna dall'order stream (`order_stream: True` anche in paper, `A_CONNESSIONE_BETFAIR.md:80`) e si legge al book
   successivo (`order.status`, `size_matched`): non c'e' callback, la decisione vede l'esito con un giro di ritardo (la sequenza
   park-trim-replace e lo scratch aspettano esplicitamente "close vecchia MORTA", `:2034-2055`).
6. Fuori dal percorso ma nello stesso processo: specchio `betfair_live_orders` ogni 1 s (`:1140-1165`, scrittura DB solo su variazione),
   battito 5 s (3+ giri DB), 3 thread `live_now`. Interferenza con la strategia (GIL, parsing JSON di Supabase): **non misurata**;
   strumento: py-spy o una sonda "tempo da book a `place_order`" nel banco.

---

## 2. FUNZIONALITA' (tutte, lette riga per riga)

Legenda: **[S]** logica di strategia INTOCCABILE; **[C]** condotta ordini (regole `.it`, parcheggio, minimi: regole dell'utente, ma meccanismo
duplicato -> scheda C); **[G]** guscio; **[UI]** visibile (file); **[PAR]** parametro editabile dalla UI (valore di serie). Numeri di riga
verificati con `sed -n`/`grep -n`. I valori di serie "ctor" sono quelli del costruttore (`scalper_bot.py:427-736`, riga = 426 + posizione).

### 2.A Maker pre-match (`scalper_bot.py`) - strategia

- **E4-001 [S] Finestre del KO.** Con `force_flat` oppure (non `allow_inplay` e in-play) = vicino al KO: chiudi tutto e nessun ingresso
  (`:846-860`). Chiusura forzata a `flatten_before_s` (ctor 180 s, `:467`), stop nuovi ingressi a `entry_stop_before_s` (ctor 420 s, `:471`).
  Tempo al KO dal `publish_time` del book vs `market_time` (`_ko_epoch_ms`, `:788`). **[UI] [PAR]** `ScalperPanel.tsx` (serie 180/420, `lib/scalper.ts:106-117`).
- **E4-002 [S] Missione "2 tick".** `one_green_per_phase` (ctor `False`, `:692`; **UI di serie `true`**, `lib/scalper.ts:106-117`): un ciclo verde
  (locked >= `_GREEN_MIN` 0,05, `:1111`) pre-match + uno in-play; fatto il tick di fase niente nuovi cicli (`:864-868`); evento `mission` (`:1137-1139`). **[UI] [PAR]** checkbox.
- **E4-003 [S] Tetto di perdita e target con cricchetto.** `_check_event_guards` (`:1141-1180`): `event_loss_cap` (ctor 0, `:686`; UI di serie 1,5) -> `force_flat`
  totale (`:1159-1170`); `event_profit_target` (ctor 0, `:684`; UI 1,0) + `event_target_giveback` (0,30, `:685`): raggiunto il picco, se il guadagno scende di
  `giveback` stop ingressi (`:1171-1179`). Decisione "2) b" dell'utente: il tetto conta solo le perdite VERE dei cicli chiusi (`:1153-1158`, `pnl_residui` esclusi;
  BIBBIA §13-bis, `BIBBIA_SCALPER_CALCIO.md:861-880`). **[UI] [PAR]** `event_loss_cap`, `event_profit_target`.
- **E4-004 [S] Riconciliazione ledger-ordini in DONE.** Ciclo "chiuso" con esposizione > tolleranza (0,02; con residuo accettato `max(0,30, residuo+0,02)`):
  auto-heal con flatten, CRITICAL oltre 0,5, 3 divergenze = `recon_freeze` (force-flat) (`:963-989`). Mai abbandonare un ordine orfano (`:1004-1017`).
- **E4-005 [S] Cancelli d'ingresso.** Semaforo rischio (`risk_sem.entries_halted`, `:1190`), banda di quota `price_min`/`price_max` (ctor 1,50/4,6, `:481-482`,
  `:1195`), liquidita' ai best >= `min_size` (ctor 300, `:477`, `:1197`), `min_total_matched` (`:478`), spread leggibile (`:1202`), cooldown (`cooldown_ms`
  ctor 20.000, `:548`; `:1207`), guardia anti-gap `max_signal_ticks` (ctor 4, `:490`; `:1210-1213`). **[UI] [PAR]** `min_size`, `price_min`, `price_max`.
- **E4-006 [S] Gate di flusso (modalita' auto/join/maker).** Warmup `warmup_ms` (`:1225`), flusso minimo per lato `min_flow` (ctor 10, `:510`; `:1228`),
  `min_inside_flow` (`:1230`), `require_oscillation` (`:1235-1247`), `flow_balance_min` (`:1248-1257`), WoM `wom_block` 0,90 (`:1259-1261`), filtro deriva
  `max_drift_ticks` (`:1264-1267`). **[PAR]** UI: `min_flow`; gli altri via whitelist (`scalper_session.py:72-105`) ma non nei campi del pannello.
- **E4-007 [S] Bias, trend surf, swing.** Bias dai motori (`self.bias`, `:1269`, `bias_resolver.py`, E4-066), trend automatico `trend_mode`/`trend_min_ticks`/`trend_flow_ratio`
  (`:1273-1285`), `swing_only` (`:1288-1289`), target e stop swing (`swing_target_ticks` `_open_lock` `:2125`; `swing_stop_ticks` `:1939-1940`). Ingresso unilaterale a
  coda del touch (`:1290-1308`).
- **E4-008 [S] Ingresso join e maker a due lati.** `_enter_join` (`:1378-1450`): `join_offset_ticks`, `improve_inside` (`:1402-1409`), `max_queue_wait_s` (`:1419-1432`),
  stake scalato dal flusso `stake_max`/`flow_ref` (`:1436-1438`), due gambe (`:1439-1440`) -> `QUOTING2` (`:1445`). `_enter_maker` (`:1343-1377`): cattura
  tra `capture_min_ticks` e `capture_max_ticks`. **[UI] [PAR]** `capture_min_ticks`, `capture_max_ticks`, `join_max_spread`, `improve_inside`, `reprice_ticks` (whitelist).
- **E4-009 [S] Reversion a una gamba.** `_signal` (`:1775`) + ingresso solo con spread <= `max_spread_ticks` (`:1322-1341`).
- **E4-010 [S] Chiusura pre-dimensionata.** `_presize_close` (`:1451-1523`): al fill dell'ingresso la close e' dimensionata al centesimo sulla posizione abbinata
  (evento `close_presize`).
- **E4-011 [S] Gestione maker 2 lati.** `_manage_maker` (`:1524-1687`): TTL ingresso `entry_ttl_ms` (ctor 600.000, `:1612, 1650, 1682`), stop a `stop_ticks` (`:1614, 1652`),
  reprice a `reprice_ticks` (`:1675, 1679`). **[PAR]** `entry_ttl_ms`, `stop_ticks`.
- **E4-012 [S] Quoting a una gamba e blocco in LOCKING.** `_manage` (`:1814-2093`): requote (`:1839-1844`), TTL, target `_open_lock` (`:2114-2168`, `scalp_ticks`
  ctor 1, `:439`; `compute_green` `:297`). **[UI] [PAR]** `scalp_ticks`.
- **E4-013 [S] Stop duro e stop adattivo.** `eff_stop` (`:1938-1949`): `stop_ticks` ctor 1 (`:440`); con `stop_ticks_far`/`stop_horizon_s` (`:699-700`) lo stop si allarga
  col KO lontano; timeout `lock_ttl_ms` (ctor 3.600.000, `:444`; `:1954`). Evento `stop` (`:1997`), `cooldown_until` (`:1995`). **[UI] [PAR]** `stop_ticks`, `lock_ttl_ms`.
- **E4-014 [S] Scratch a pari.** Se il touch raggiunge il prezzo d'ingresso si ripiazza la chiusura a pari, una volta per ciclo (`:2000-2073`), aspettando che la close
  vecchia sia MORTA (cantiere CP4, `:2034-2055`, `scratch_in_attesa`). `scratch` ctor `True` (`:546`).
- **E4-015 [S] Pipeline.** Ingresso del ciclo dopo in coda dietro la close (`:2074-2092`) e adozione (`:994-1042`); `pipeline` ctor `False` (`:555`).
- **E4-016 [S] Flatten con escalation.** `_begin_flatten` (`:2228`), `_drive_flatten` (`:2247-2453`): piatta entro 0,02 (`:2263`), contabilita' `flatten_done` (`:2276-2281`),
  `circuit_breaker` in-play se un ciclo perde >= `cycle_loss_breaker` (ctor 0,50, `:458`; `:2282-2291`), anti-churn `flatten_min_interval_ms` (`:600`), `flat_tries`.
- **E4-017 [S] Fase in-play e intervallo.** `inplay_from_s`/`inplay_to_s` (`:450-451`; `:1051-1063`), rilevatore reale `ht_active` + clock di sanita',
  `max_inplay_slots` 2 (`:455`; `:1065-1071`), `inplay_close_now` (`:832-841`). **[PAR]** `ht_mode` (whitelist; UI `ScalperPanel.tsx:439-447` [corretto dal verificatore 08/10: il checkbox `htMode` sta a 439-447; 430-433 e' `missionTwoTicks`]).
- **E4-018 [S] Contabilita' di ciclo.** `_on_cycle_closed` (`:1115-1139`: `pnl_prematch`/`pnl_inplay`, `cycle_log` max 200, `greens_*`), `process_closed_market` (`:1079-1107`:
  `pnl_settled` dal settlement simulato, dedup per ordine). **[UI]** `ScalperPanel.tsx:963-965` ("P&L bloccato (lordo)", "settlato (lordo)").

### 2.B Regole d'uscita e minimi `.it` (decisioni dell'utente: INTOCCABILI nei numeri; il meccanismo e' duplicato)

- **E4-020 [C] Chiusure al centesimo.** `spezza_uscita` (`scalper_bot.py:88-122`): una punta di chiusura non multipla di 0,50 esce ESATTA (diretta un passo sotto + resto
  0,50-0,99 col place-and-trim); la regola e' UNA, fonte unica `trading/minimi_it.importo_piazzabile`. `stato_parcheggio` (`:124-156`): parcheggio 1,00 dalla fonte
  unica, LAY alla quota in banda INVALID_PROFIT_RATIO (`submin.quota_parcheggio_lontano`). Esecuzione: `_place_exact` (`:3028-3135`), `_drive_submins` (`:3136-3229`),
  `_cancel_submins` (`:3019`). Eventi `submin_start/step/abort/error` (`:3130-3224`).
- **E4-021 [S] Scavalco (decisione "1) b").** Chiusura sotto 0,50 non piazzabile: DUE ordini legali; primo = scavalco dal lato opposto (`ordine_di_scavalco`, `:158-198`),
  poi chiusura normale al centesimo. Solo con `exact_exits`, mai in dry-run, al piu' `_SCAVALCHI_MAX_PER_CICLO` = 3 per ciclo (costante `scalper_bot.py:2984`, duplicata in `sniper_bot.py:975`; BIBBIA §13-bis), sopra la "polvere" 0,05
  (`_chiusura_oltre_la_polvere`, `:200-226`); `_scavalca` (`:2528-2571`), evento `scavalco` (`:2566`).
- **E4-022 [S] Residuo ricordato e chiusura bloccata.** Residuo non chiudibile dichiarato CRITICAL una volta e RICORDATO per la sessione (`_ricorda_residuo` `:2573`,
  campi `residuo_w/residuo_l` nello `_Slot`, non azzerati da `_reset` `:3277`), `_chiusura_bloccata` (`:2606`), `_resto_davvero_non_piazzabile` (`:2627`), `_tutto_residuo`
  (`:2502`), testo `_msg_residuo` (`:236`); eventi `flatten_residual`, `flatten_residual_forced`, `flatten_bloccato`, `residuo_ricordato` (`:2387, 2424, 2445, 2592`).
- **E4-023 [C] Freno sui rifiuti per la TAGLIA.** `CODICE_TAGLIA = "INVALID_BET_SIZE"` (`:85`), `_leggi_rifiuti_taglia` (`:2465-2501`): 1, 2, 4, 8, 16, poi 30 s nel ciclo
  (campi `rifiuti_taglia`, `taglia_ferma_fino_ms` nello `_Slot`); evento `rifiuto_taglia` (`:2492`).
- **E4-024 [C] Protezioni di `_place`.** Taglia: `size_step` (`:2783-2786`), `live_min_bet` con bump a 0,50 (`:2789-2801`, eventi `min_bet_adjust/skip`), guardia mercato
  (`:2811`), `freno_live` soldi veri (`:2818-2833`, evento `apertura_live_fermata`), `FrenoRifiuti` (`:2835-2843`), `max_txn_hour` (ctor 0; sessione 300, `:2846-2854`, evento `txn_cap`),
  `dry_run` (`:2856-2866`, evento `dry_place`), rifiuto di Betfair (`:2886-2898`, evento `place_rifiutato`), evento `place` (`:2905`).
- **E4-025 [S] Uscite manuali / automatiche.** `uscite_automatiche` di serie `False` dal 25/09 (manuali): `_lascia_uscire` (`:2186-2210`), `_proponi_uscita` (`:2221`),
  `_pubblica_proposte` (`:2211`), `CancelloUscite`/`UltimiPrezzi`/`proposta_di` (`uscite_proposte.py`); stop, timeout e scratch diventano PROPOSTE con i numeri di adesso e
  parte solo la firma dell'utente (`:1970-1990, 2012-2016`). Le protezioni NON passano dal cancello (controlli UM1-UM4). Letto a caldo ogni battito
  (`applica_uscite_automatiche`, `scalper_session.py:1185-1208`). **[UI] [PAR]** interruttore "uscite automatiche" (`lib/interruttori.ts`; `lib/interruttoriScalper.test.ts`), firma
  via RPC `scalper_approva_uscita`, `components/controlroom/chiudiRiga.ts`.

### 2.C Sniper in-play (`sniper_bot.py`)

- **E4-030 [S] Tre cancelli d'innesco.** `_update_micro` (`:342-376`): GATE 1 cadenza (`cadence_n` 2 tick-down in `cadence_window_s` 240 s, ultimo entro `last_dn_max_s` 90 s,
  `:355-360`), GATE 2 coda (size al best <= `queue_frac` 0,35 del massimo del livello, minimo `queue_floor_eur` 60, `:361-366`), GATE 3 spread <= `max_spread_ticks` 1
  (`:367-370`). Valori ctor: `sniper_bot.py:117-124`.
- **E4-031 [S] Ingresso taker.** `_fire` (`:604-631`): BACK al best back, `stake` 10 (ctor `:108`); in dry-run solo `sniper_dry_fire`, anti-spam 120 s per selezione. **[UI] [PAR]** `sniper_mode`, `sniper_stake` (clamp 2-100, `ScalperPanel.tsx:472`), "caccia" `sniperHunt` (`:101, 479`).
- **E4-032 [S] Gestione della posizione.** Close a `target_ticks` 1, stop a `stop_ticks` 2 (`:487`), timeout `max_pos_s` 300 s (`:454`), PRIMO verde = evento chiuso (`profit_target` 0,01,
  `:550-552`), `event_loss_cap` 1,0 (`_loss_capped`, `:587-603`), `max_shots`/`shot_cooldown_s`/`parallel_lines` (`:578-580`), semaforo (`:573`), `min_size` 50 (`:568`),
  finestra `inplay_from_s` 60 - `inplay_to_s` 6.600 (`:126-127`). Linee: `set_line/set_lines` (`:224-253`), `SNIPER_MARKET_TYPES` O/U 0,5-8,5 (`scalper_session.py:112`),
  `applica_linea_sniper` ogni 15 s (`:733-765`).
- **E4-033 [C] Flatten, scavalco, place-and-trim dello sniper** (`sniper_bot.py:770-1363`): copia parallela di E4-016/E4-020/E4-021/E4-022/E4-024 (par. 3.2).

### 2.D Theta in-play (`theta_bot.py`)

- **E4-040 [S] Semaforo d'ingresso.** Hazard (Atlante) <= `hazard_max` 0,085 (`_hazard` `:546`, atlante assente = ROSSO), quiete (EventRiskSemaphore 120 s), spread <= 2,
  best back >= 20 EUR, quota 1,05-3,5, zone rosse 40-45' / 80-90' (`in_red_zone` `:227`), `_entry_go` (`:927`), `_protect_go` (`:955`); docstring `:1-45`.
- **E4-041 [S] Esecuzione.** Coppia atomica `theta_pair` (`:202`), close immediata sui numeri REALI, scratch a `scratch_s` 120 (240 overshoot), post-gol via flatten, `max_shots` 10, `loss_cap` 5,
  `target_greens` (`:982`); preset `classico`/`overshoot`/`cecchino`; pre-match theta `_manage_prematch` (`:1049`), `prematch_timeout_s` (`:159`), `prematch_exit_ticks` (`:169`).
  Verdetto S4 dichiarato: classico EV- (solo raccolta dati). **[UI] [PAR]** `theta_mode`, `theta_stake`, `theta_preset`, `theta_max_shots`, `theta_loss_cap`, `theta_scratch_s`, `theta_hazard_max`, `theta_only`.
- **E4-042 [S] Conferma manuale.** `ThetaConfirmBus` (`:250-338`): proposte entry/scratch/postgol su `theta_confirm_requests`, timeout -> la PROTEZIONE parte comunque. La UI manda sempre `auto` (`lib/scalper.ts` commento su `theta_confirm_mode`).

### 2.E Media under (`media_under_bot.py`, spec `SPEC_MEDIA_UNDER_2026-10-05.md`)

- **E4-050 [S] Macchina a stati.** `FERMO -> INGRESSO -> IN_POSIZIONE -> RIENTRO -> MASSIMO -> LIVE -> FINE` + `BLOCCATA`, `ATTESA_CLIC`, `RIPRESA` (`:173-191`). **[UI]** testi in `lib/mediaUnder.ts:414-441`.
- **E4-051 [S] Parametri.** `VALORI_DI_SERIE` (`:118-141`), obbligatori (`:142`), lettura/validazione `leggi_parametri` (`:308-397`): stake 10, obiettivo 0 (= automatico), tick chiusura 2, tick rientro 2,
  rientri max 5, rischio max 0, quota 1,20-4,00, `min_size` 300, `min_flow` 10, spread max 2, stop ingressi 420 s, TTL punta 30.000 ms, obiettivi live [0; 0,30; 1,00], commissione 5 %, `media_rientro_auto_filtri` `False`. **[UI] [PAR]** tutti (`mediaUnder.ts:41-85`, `ScalperPanel.tsx:555-660`).
- **E4-052 [S] Ingresso con filtri.** `_puo_aprire` (`:1193-1205`: freno, fischio ignoto, finestra di stop, attesa dopo rifiuto), `_perche_non_entra` (`:1273-1296`: prezzi, quota, liquidita', spread, riscaldamento, flusso), `_punta_d_ingresso` (`:1311`, BACK lo stake alla miglior quota, LAPSE).
- **E4-053 [S] Banca di chiusura.** Formule `banca_esatta` (`:539`), `profitto_lordo_con_banca` (`:544`), `rientro_esatto` (`:549`), `obiettivo_automatico` (`:566`), `quota_della_banca` (`:599`, il piu' basso fra "ultimo ingresso - N tick" e media al tick inferiore),
  `_assicura_banca` (`:1495`), `_allinea_banche` (`:1515`), `_banca_nuova` (`:1596`): una sola banca viva per volta, la somma delle banche vive non supera MAI la posizione da coprire.
- **E4-054 [S] Rientri.** `_forse_rientro` (`:1420`: quota salita >= `tick_rientro` dall'ultimo ingresso, rientri < massimo, banche ferme), `_piano_rientro` (`:1439`: importo esatto, `rischio_max`, evento `media_rientro_bloccato`), `_punta_di_rientro` (`:1467`), `_rientro_in_corso` (`:1783`).
- **E4-055 [S] Banca che si sposta (07/10).** `_riduci` (`:1629`), `_sposta` (`:1656`: integrazione poi `replaceOrders`), `_segui_spostamenti` (`:1701`), `_spostamento_fallito` (`:1689`).
- **E4-056 [S] Massimo e live.** `_ciclo_chiuso` (`:1825`), `_nuovo_ciclo` (`:1873`), `_in_live` (`:1890`: in gioco nessun ordine, solo segnalazione), `riquadro_chiusura` (`:626`), `_descrivi_banca` (`:2112`), `testo_ciclo_chiuso` (`:580`). **[UI]** riquadro importi in `ScalperPanel.tsx`/`mediaUnder.ts:278-313`.
- **E4-057 [S] ATTIVA ADESSO (07/10, divergenza voluta).** `ricevi_comando` (`:1961`), `_esegui_comando` (`:2046`), `_in_gioco_a_clic` (`:1922`), `_rientro_automatico` (`:1343`), scadenza 120 s (`ATTESA_MASSIMA_COMANDO_S`, `:161`); consegna dal battito (`scalper_session.py:977-1049`). **[UI]** pulsanti `ScalperPanel.tsx:696-701` (da fermo) e `:850-854` (sessione accesa), `handleAttivaAdesso` `:296-315`, conferma `testoConfermaAttivaAdesso` (`mediaUnder.ts:230`), RPC `scalper_media_attiva_adesso` (`mediaUnderAttiva.ts:17`), attesa esito 20 s (`ATTESA_ESITO_CLIC_MS`, `mediaUnder.ts:258`).
- **E4-058 [G/S] Stop, ripresa dal conto.** `pronta_allo_stop` (`:2347`), `_ritira_la_punta_allo_stop` (`:2379`), `banca_da_lasciare` (`:2320`), `prepara_ripresa` (`:2388`), `_forse_riprendi` (`:2427`), `_ricostruisci` (`:2488`), `ATTESA_RIPRESA_MS` 60 s (`:749`); lettura ordini del conto `scalper_session.py:896-976`.
- **E4-059 [G] Rifiuti e diario.** `_leggi_rifiuti` (`:2206`), `_registra_rifiuto` (`:2218`), `MOTIVI_NON_INGRESSO` (`:861`), `_pubblica` (`:2290`, stats per la UI).

### 2.F Guscio: sessione, supervisore, auto-mode

- **E4-060 [G] Supervisore** `scalper_service.main` (`:844`): giro ogni 3 s (`POLL_S`), `_spawn` (`:702`), `sessione_da_avviare` (`:694`), orfane (`marca_orfana` `:657`, `orfane_giudicabili` `:741`, zombie in arresto `:727`), `freno_supervisore` (`:685`), arresto ordinato di tutte le sessioni (`attendi_e_termina_flat` `:792`, `tempo_supervisore_arresto_s` `:769`), kill-switch (`:905-913`), all'avvio app nessun bot opera (`ferma_sessioni_al_nuovo_avvio` `:233`, `controllo_avvio` `:250`).
- **E4-061 [G] Auto-mode.** `giro_auto` (`:350-569`), `auto_mode.py`: tetto partite (2/4, `:71-72`), vita sessione (maker 600 s, HT 4.200 s, sniper/theta 7.800 s, `:95-97`), assenza feed 60 s (`:85`), scanner vivo 30 s (`:88`), origine `auto`/`manuale` (`:74-75`), conflitto paper/live (`conflitto_modalita` `:344`), `dry_run_alla_nascita` (`:337`), `da_fermare_per_feed` (`:359`). **[UI]** `scalperControlRoom.ts:202-338` (`AutoScalper`, `leggiAutoScalper`, `notaAutoScalper`).
- **E4-062 [G] Habitat scan.** `habitat_scan.py` (196 righe), ciclo `_habitat_loop` (`scalper_service.py:880-904`): fa un PROPRIO login Betfair (`build_client(login=True)`, `:886-887`, riusato fra i giri), `scan(hours=8.0, top=15)` e scrive `scalper_activity` con `event_id="habitat"` (`:890`): un login in piu' nel processo supervisore, da contare nella scheda A.
- **E4-063 [G] Arma la sessione.** `run_session` (`scalper_session.py:1324-2243`): freno (`non_partire_col_freno` `:212`, `non_partire_senza_soldi_veri` `:248`), `build_client`, client paper (`paper_trade=True`) o live (`_order_client_kwargs` `:787-802`; paper = live salvo il client, controllo S6), mercati `SESSION_MARKET_TYPES` (`:107`, MATCH_ODDS + O/U 1,5/2,5/3,5), parametri `VALIDATED_PARAMS` (`:42-70`) + `UI_PARAM_WHITELIST` (`:72-105`, 63 chiavi tra virgolette).
- **E4-064 [G] Battito 5 s** (`:2038-2125`): flush del diario, stato del flusso (`sorveglia_flusso_sessione` `:1050`), `set_control(heartbeat_at, stats)` (`:2051`), params vivi (`control_stato_e_params` `:2090`), stop dalla UI (`stopping/stopped/error` = force-flat `:2118`), partita finita (mercato CLOSED `:2155`, `partita_finita` `:476`), KO passato (`:2172`), cap globale evento (blocco del battito).
- **E4-065 [G] Freno unico.** `motivo_freno` (`:150`), `sorveglia_freno` (`:178`, ogni `FRENO_POLL_S` 2 s), file `STOP_SCALPER` (`:34`), `freno_soldi_veri` (`:230`).
- **E4-066 [G] Arresto ordinato.** `chiudi_all_arresto` (`:667`), `annulla_ordini_vivi_all_arresto` (`:606`), `_sweep_cancel` (`:500`; annulli REST `cancel_orders` per bet_id `:532`, market-wide `:540`), attesa flat 30 s (`FLAT_ATTESA_S` `:568`), `TEMPO_MASSIMO_ARRESTO_S` (`:577`), dichiarazione di stop non flat (`:355-403`), `dichiara_stato_finale` (`:197`).
- **E4-067 [G] Crash e rete.** `_handle_flumine_crash` (`:824`), `mantieni_sessione` (keep-alive, `:805`), stream muto/ripreso (`KIND_FLUSSO_*` `:873-874`).
- **E4-068 [G] Specchio ordini** `betfair_live_orders`, `source="scalper"` (`_make_session_mirror` `:1094-1139`, `SOURCE_SPECCHIO` `:39`), ciclo a 1 s. **[UI]** il ladder e la Control Room leggono la tabella.
- **E4-069 [G] Bias "Model Exec".** `_resolve_bias` (`scalper_session.py:1286`), `bias_resolver.py` (229): consenso ML + Poisson, dominio e orario delle predizioni.
- **E4-070 [G] Risk semaphore** `risk_semaphore.py` (92): momenti caldi dopo sospensione = niente NUOVI ingressi, le chiusure passano.
- **E4-071 [G] Watcher intervallo** `ht_should_start` (`:264`), `HT_STALE_S` 300, minuto 45-48 (`:120-122`), thread `ht-watcher` (`:1883`).
- **E4-072 [G] CLI.** `run_scalper.py` (backtest forward), `run_theta.py` (backtest theta), `run_scalper_live.py` (DISATTIVATO dal 24/09, fail-closed: serve `SCALPER_LIVE_CLI=consentito`).

### 2.G Frontend

- **E4-080 [UI] Pannello "Scalper Bot"** (`ScalperPanel.tsx:67`): modalita' (Tradizionale/Direzionale/Entrambe), stake, ARMATO/prova di serie (`dryRun`, `:424`), 10 campi numerici `SCALPER_PARAM_FIELDS` (`lib/scalper.ts:128-139`: tick profitto 1, tick stop 1, flusso min 10, size min 300, quota 1,5-4,6, stop ingressi 420, chiusura forzata 180, target 1, tetto 1,5), missione 2 tick, sniper (`:453-481`), theta (preset, max colpi `:493-535`), media under (`:555-660`), pulsanti "Attiva in PAPER" / "Attiva ORDINI REALI" (`:692`), "Attiva adesso" (`:696-701`), stato in polling 4 s (`pollMs`, `:67`), tessere (cicli, scratch, stop `:751`, theta `:804-823`), feed attivita', P&L lordo (`:963-965`), "Ferma lo scalper (chiude flat)" (`:945-951`, `handleStop` `:322`).
- **E4-081 [UI] Secondo punto d'accensione** `components/omega/MissionCard.tsx:23, 52, 151, 212-219` (preset theta 1-tick sull'evento, polling proprio).
- **E4-082 [UI] Control Room** `components/controlroom/PannelloBot.tsx` (cadenza di lettura scalper 5 s, riga 104), `scalperControlRoom.ts` (`SessioneScalper` `:49`, `ServizioScalper` `:82`, `OrdineScalper` `:96`, `esposizioneScalper` `:456`, `chiusuraScalper` `:522`, `pnlRealeOrdini` `:565`, `flussoSessioneScalper` `:605`), canale locale `scalperCanale.ts` (topic `scalper_stato` `:28`, `scalper_sessioni` `:29`), chiusura riga (`chiudiRiga.ts:44`, RPC `scalper_stop_sessione`).
- **E4-083 [UI] Media under** `lib/mediaUnder.ts`: `leggiMediaUnder` (`:388`), `erroriMediaUnder` (`:97`), `paramsMediaUnder` (`:125`), `statoDelClic` (`:200`), `pulsanteCliccabile` (`:260`), obiettivi live (`:266`).

Totale funzionalita' numerate: **58** (E4-001..018 [18], 020..025 [6], 030..033 [4], 040..042 [3], 050..059 [10], 060..072 [13], 080..083 [4]); molte voci raggruppano piu' regole (es. E4-005 ha 7 cancelli, E4-024 8 protezioni, E4-080 l'intero pannello) e i 60 e piu' tipi di evento del diario sono elencati con la riga nel par. 2.H, non contati a parte.

### 2.H Diario di attivita' (`scalper_activity.kind`, uno per `_emit`)

Maker (`scalper_bot.py`, righe degli `_emit`): `ledger_divergence` 978, `recon_freeze` 983, `mission` 1138, `loss_cap` 1165, `target_raggiunto` 1177, `trend_surf` 1283, `close_presize` 1492/1513/1520,
`cycle` 1562/1911, `stop` 1997, `scratch` 2067, `flatten_done` 2281, `circuit_breaker` 2291, `flatten_residual` 2387, `flatten_residual_forced` 2424, `flatten_bloccato` 2445, `rifiuto_taglia` 2492, `scavalco` 2566,
`residuo_ricordato` 2592, `min_bet_adjust` 2794, `min_bet_skip` 2799/3062/3082/3086/3111, `apertura_live_fermata` 2826, `freno_rifiuti` 2840, `txn_cap` 2852, `dry_place` 2863, `place_rifiutato` 2891, `place` 2905,
`submin_start` 3130, `submin_error` 3133/3180, `submin_step` 3189, `submin_abort` 3198/3224, `submin_abort_matched` 3206. Sniper: `sniper_fire`, `sniper_dry_fire`, `sniper_loss_cap`. Theta: `theta_dry_fire` e relativi. Media: `media_ingresso`,
`media_punta_abbinata`, `media_comando_eseguito/rifiutato`, `media_rientro_automatico`, `media_attesa_clic`, `media_rientro_bloccato`, `media_rientro_non_piazzabile` (SPEC_MEDIA_UNDER par. 13.1). Sessione: `info/warn/error/critical`, `ht_start/ht_end`, `media_comando`, `flusso_interrotto/ripreso`.

---

## 3. DIFETTI STRUTTURALI

### 3.1 Il maker calcio e il maker tennis sono lo stesso codice (misura)

`python ARCHITETTURA_2026-10/strumenti/e4_gemelli_tennis.py` (righe di codice senza vuote, commenti e docstring; blocchi uguali `difflib.SequenceMatcher`):

| Coppia | Righe file | Righe di codice | Righe di codice UGUALI | % gemella |
|---|---|---|---:|---|
| `scalper/scalper_bot.py` / `tennis_scalper/tennis_scalper_bot.py` | 3.315 / 2.974 | 2.126 / 1.906 | **1.449** | **68,2 % del calcio, 76,0 % del tennis** (ratio 0,719) |
| `scalper/auto_mode.py` / `tennis_live/auto_mode.py` | 440 / 270 | 215 / 132 | 66 | 30,7 % / 50,0 % |
| `scalper/scalper_service.py` / `tennis_live/tennis_bot_service.py` | 982 / 1.183 | 639 / 741 | 51 | 8,0 % / 6,9 % |
| `scalper/scalper_session.py` / `tennis_live/tennis_live_order_worker.py` | 2.303 / 1.831 | 1.471 / 1.248 | 46 | 3,1 % / 3,7 % |
| `scalper/scalper_session.py` / `tennis_live/tennis_runner.py` | 2.303 / 3.483 | 1.471 / 2.345 | 37 | 2,5 % / 1,6 % |

Il guscio NON e' gemello (architetture diverse: una sessione per partita contro un runner unico per tutto il tennis); il motore del maker lo e'.
`tennis_scalper_bot.py:274` lo dichiara: "COPIA di `scalper_bot.ScalperStrategy` (logica di esecuzione bit-identica...". **48 funzioni con lo stesso nome** (A ne ha 68, B 60),
somma righe di codice A=1.786, B=1.783, ratio medio pesato 0,821. **19 funzioni identiche (ratio 1,00)**, con `file:riga` calcio : tennis:

`micro_price` 244:111, `wom_imbalance` 265:132, `ticks_between` 278:145, `compute_green` 297:164, `_emit` 737:639, `settled_orders` 756:649, `_slot` 760:653, `_ko_epoch_ms` 788:802,
`_update_flow` 1688:1692, `_flow_sums` 1728:1732, `_long_drift` 1738:1742, `_long_drift_signed` 1743:1747, `_recent_move` 1763:1767, `_open_lock` 2114:2046, `_chiave_slot` 2169:2098, `_net_position` 2239:2153,
`_track` 2967:2596, `_ordini_in_sequenza` 3006:2614, `_cancel_submins` 3019:2627.

Quasi identiche (ratio 0,88-0,97): `_try_enter` 0,93 (1183:1256), `_enter_maker` 0,95 (1343:1428), `_enter_join` 0,97 (1378:1462), `_manage_maker` 0,96 (1524:1534), `_manage` 0,88 (1814:1811),
`_signal` 0,88 (1775:1779), `check_market_book` 0,92 (769:787), `process_market_book` 0,80 (817:831), `_flatten` 0,94 (2661:2322), `_handle_cancelling` 0,93 (2094:2029), `_drive_submins` 0,90 (3136:2757).
**Divergenti (ratio < 0,70)**, da leggere riga per riga PRIMA di unificare (potrebbero essere regole di sport): `_drive_flatten` 0,57 (2247:2161), `_place_exact` 0,64 (3028:2636), `_place` 0,69 (2743:2413),
`_has_live` 0,50 (3251:2840), `_cancel_if_live` 0,61 (3262:2921), `_prefisso_uscite` 0,60 (2175:2104), `_orologio_s` 0,32 (746:2863), `_side_min` 0,15 (2950:2578), `_size_direct_ok` 0,13 (2960:2584), `_on_cycle_closed` 0,04 (1115:731).
Solo calcio (20): `spezza_uscita` 88, `stato_parcheggio` 124, `ordine_di_scavalco` 158, `_chiusura_oltre_la_polvere` 200, `_quota_chiusura` 228, `_msg_residuo` 236, `_check_event_guards` 1141, `_presize_close` 1451, `_proponi_uscita` 2221,
`_codice_rifiuto` 2454, `_leggi_rifiuti_taglia` 2465, `_tutto_residuo` 2502, `_scavalca` 2528, `_ricorda_residuo` 2573, `_chiusura_bloccata` 2606, `_resto_davvero_non_piazzabile` 2627, `_esegui_place` 2916, `_nel_blotter` 2937, `_ordini_della_close` 2986, `_vivo_o_in_volo` 3230
(sono le regole del 04/10 e 07/10: scavalco, residui, taglia: **mai arrivate nel tennis**). Solo tennis (12): `green_piazzabile` 189, `_phase_green` 662, `_mission_blocks` 667, `_spiega_missione` 677, `_book_locked` 705, `_count_cycle` 720, `_favourite_sel` 766,
`_avvia_uscita_manuale` 1175, `uscita_manuale_finita` 1197, `_should_stop` 2357, `_residuo_non_piazzabile_detto` 2853, `_gamba_orfana` 2877.

Limite dichiarato della misura: difflib su righe uguali e' una stima PER DIFETTO della somiglianza funzionale (una riga con un nome di campo diverso conta come diversa).

### 3.2 Duplicazione INTERNA al calcio: sniper e maker

`sniper_bot.py` rifa' l'esecuzione delle uscite del maker con funzioni omonime: 28 funzioni con lo stesso nome (`_drive_flatten` 2247:786, `_place` 2743:1083, `_place_exact` 3028:1170, `_drive_submins` 3136:1240,
`_scavalca` 2528:977, `_chiusura_bloccata` 2606:926, `_resto_davvero_non_piazzabile` 2627:945, `_tutto_residuo` 2502:1007, `_track`, `_has_live`, `_vivo_o_in_volo`, `_cancel_if_live`, ...).
Misura: scalper_bot/sniper_bot 10,6 % / 22,9 % di righe uguali, ratio medio pesato 0,293 (strutture diverse, stessa regola). Codice delle 16 funzioni di condotta: **593 righe di codice nel maker + 445 nello sniper = 1.038**
(somma delle colonne "righe(cod)" dello strumento). Lo sniper importa solo 6 pezzi puri da `scalper_bot` (`sniper_bot.py:40`: `_chiusura_oltre_la_polvere, compute_green, ordine_di_scavalco, spezza_uscita, stato_parcheggio, ticks_between`); la costante `_SCAVALCHI_MAX_PER_CICLO = 3` e' definita due volte (`scalper_bot.py:2984`, `sniper_bot.py:975`).
`media_under_bot.py` invece e' quasi indipendente (3,2 % / 3,5 % con il maker; solo 7 nomi in comune), ma ha una sua `_piazza` (`:2152`) e un suo `vivo_o_in_volo` (`:712`): quarta copia delle regole di taglia/stato dell'ordine.
Tutte e quattro rifanno `_ko_epoch_ms` (`scalper_bot.py:788`, `sniper_bot.py:295`, `media_under_bot.py:1020`; `theta` eredita).

### 3.3 Copia di laboratorio

`laboratorio/scalper_lab/scalper_bot_base.py` (2.076 righe) = **61,2 % di `scalper_bot.py` e 90,2 % della propria**, 40 funzioni omonime (strumento `e4_gemelli_tennis.py` con coppia aggiunta): copia congelata
di una versione vecchia; `PROCESSO_STANDARD_BOT.md` §7.31 la vieta come banco. Rischio: modifica della produzione senza modifica della copia, o viceversa.

### 3.4 Valori di serie in TRE posti, con valori diversi

| Parametro | ctor (`scalper_bot.py`) | `VALIDATED_PARAMS` (`scalper_session.py:42-70`) | UI (`lib/scalper.ts:106-117`) |
|---|---|---|---|
| `one_green_per_phase` | `False` (`:692`) | `False` ("Off di default: la UI la attiva") | **`true`** |
| `event_loss_cap` | 0,0 (`:686`) | 1,5 | 1,5 |
| `event_profit_target` | 0,0 (`:684`) | 1,0 | 1,0 |
| `exact_exits` | `False` (`:607`) | `True` | non mandato |
| `max_txn_hour` | 0 (`:632`) | 300 | non mandato |
| `capture_min_ticks` | 2 (`:503`) | 3 | non mandato |
| `cooldown_ms` | 20.000 (`:548`) | 30.000 | non mandato |

Il valore efficace in produzione e' l'unione (ctor < `VALIDATED_PARAMS` < params della UI), ma nessun documento lo dice in un punto solo: la stessa soglia vive in tre file. Anche `MEDIA_UNDER_DEFAULTS` (`mediaUnder.ts:41-62`) specchia a mano
`VALORI_DI_SERIE` (`media_under_bot.py:118-141`) (commento "specchio di media_under_bot.VALORI_DI_SERIE"), e `UI_PARAM_WHITELIST` (`scalper_session.py:72-105`) specchia `CHIAVI_UI` del media (commento "gli stessi nomi, test di contratto")
(difetto §7.33: costante nel frontend che duplica una scelta del backend).

### 3.5 Il guscio fa troppo e parla troppo col DB

- 20 + 16 chiamate `.table(` (par. 1.5): il supervisore da solo = 54 chiamate/min misurate; ogni sessione >= 36/min stimate dal codice. Tutte fuori dal percorso del tick tranne la lettura di `freno_live` (par. 1.6, punto 3).
- `scalper_session.py` e' 2.303 righe con `run_session` di ~920 righe (`:1324-2243`): arma, battito, stop, theta, sniper, media, recon, crash in una funzione (`# noqa: C901 - flusso lineare`).
- Il polling del minuto di gioco: 3 thread diversi leggono `live_now` (`:1756, 1891, 1911`) per la stessa partita.
- `scalper_session` -> `Betfair.safe_strategy.execution._live_brake` (par. 1.3): un bot importa un modulo di un altro bot per il freno.
- Il pannello legge `scalper_control` in polling a 4 s (`ScalperPanel.tsx:67`), la Control Room a 5 s (`PannelloBot.tsx:104`), la `MissionCard` omega e' gia' stata ridotta a un poll solo a livello di pannello (`MissionCard.tsx:212-222`, "§18"; da sola ha un poll di cortesia): due cadenze (4 s e 5 s) e due/tre punti d'accesso alla stessa riga.
- Due punti d'accensione dello stesso bot (`ScalperPanel`, `MissionCard`) con default propri (`SCALPER_PARAM_DEFAULTS` condiviso, preset theta diversi).
- L'Atlante hazard (6.038 righe) vive in `scalper/` ma e' consumato da Mike, Omega e Safe (par. 1.2): `scalper/__init__` importa `scalper_bot`, per questo c'e' stato l'incidente 17/09 (`hazard_atlas.py` docstring).
- `Mike` importa `ticks_between` da `scalper_bot` (`mike/engine.py:33`).

### 3.6 Il banco e' troppo lento

`calcio_prima_tutti.txt`: `scalper_calcio` `--scenari tutti` = **47 replay in 115 min 16 s (6.916 s)** contro obiettivo 300 s e tetto 600 s (`CERTIFICA_TETTO_S`), scenario piu' caro `uscite-manuali` 5 min 52 s (352,2 s).
E' un difetto del banco da correggere subito (ordine dell'utente del 29/09, `PROCESSO_STANDARD_BOT.md` §6.9; CLAUDE.md "Replay veloci"). Nei 5 scenari del cantiere 15: 370,7 s (6 min 10,7 s) su 5 replay, sotto il tetto, sopra l'obiettivo.
Inoltre due controlli non sono mai sollecitati dai 5 scenari ("MAI SOLLECITATI 2 su 22": **S7** riavvio, **CP2** copertura dichiarata); nel referto completo del 07/10 CP2 resta `x0`.

---

## 4. DOMANI

### 4.1 Struttura

Una cartella per componente, un contratto, un `COSA_FA.md` (brief del piano §9.1):

```
bots/scalper_calcio/
  COSA_FA.md                 scopo, entrate, uscite, come si sostituisce, come si prova da solo
  contratto.py               plugin OspiteFlumine (D, righe 403-405) + catalogo parametri tipizzato
  catalogo_parametri.py      UNA tabella: nome, tipo, serie, min/max, etichetta UI, in whitelist si/no (sostituisce ctor c.get + VALIDATED_PARAMS + SCALPER_PARAM_FIELDS + MEDIA_UNDER_CAMPI)
  maker.py  sniper.py  theta.py  media_under.py   LE CLASSI FLUMINE, regole identiche (E4-001..059)
  plugin.py                  arma/ricostruisce, uscite di serie, linea sniper, comando media, ripresa dal conto
  banco.py                   adattatore del banco (oggi tools/replay_registrazioni.py + certificazione.py)
  test_contratto.py          generico + test dei controlli di condotta
scalper_core/   (libreria comune scalper calcio+tennis, lo sport come parametro)
  prezzi.py      micro_price, wom_imbalance, ticks_between, compute_green
  flusso.py      _update_flow, _flow_sums, _long_drift(+signed), _recent_move
  slot.py        _Slot e le sue funzioni pure (_chiave_slot, _net_position, _track, _ordini_in_sequenza, _cancel_submins)
  motore_maker.py  ingresso join/maker/reversion, gestione, scratch, flatten, parametrizzato da una piccola "Regola di sport" (vedi 4.3)
```
Condotta ordini (parcheggio, taglia legale, freno rifiuti, scavalco, residui): **scheda C** (una sola copia per tutti i bot). Atlante hazard e generatore: **scheda G** (cloud/algoritmi), fuori da `scalper/`.
Guscio di sessione (login, battito, arresto, freno, crash, specchio, supervisione): **runtime comune D/A/I**; per E4 resta solo il plugin.

### 4.2 Contratto proposto (tipi)

```python
class ScalperCalcioPlugin(OspiteFlumine):                       # D_RUNTIME_BOT_CONTRATTO.md:403-405
    def catalogo_parametri(self) -> Sequence[ParametroDef]: ...  # unica fonte di serie/UI/whitelist
    def strategie(self, event_id: str, p: Parametri) -> Sequence[BaseStrategy]: ...   # maker (+sniper, theta, media): le classi ESISTENTI
    def applica_parametri_vivi(self, strategie, p: Parametri) -> None: ...            # uscite_automatiche, firme, comando media (oggi scalper_session.py:1185, 977)
    def arma(self, event_id, prematch: Prematch, stato: StatoSalvato | None) -> Armo: ...   # bias (oggi :1286), linea sniper, ripresa media (oggi :896-976)
    def su_comando(self, stato, comando: Mapping[str, Any], p) -> Esito: ...          # approva_uscita, attiva_adesso, stop
    def cadenza(self) -> Cadenza: ...                                                   # battito 5 s -> postino asincrono, lettura params da cache locale
@dataclass(frozen=True)
class ParametroDef: nome: str; tipo: type; serie: Any; minimo: float | None; massimo: float | None; etichetta: str; in_ui: bool; strategia: Literal["maker","sniper","theta","media"]
class RegolaSport(Protocol):                                     # per scalper_core
    sport: Literal["calcio","tennis"]
    def fase_verde(self, ...) -> bool: ...                       # tennis: _phase_green; calcio: pre-match/in-play
    def minimo_lato(self, side: str) -> float: ...               # _side_min (0,15 di somiglianza: da leggere)
```
Eventi esposti: `scalper_activity` (kind invariati, par. 2.H), `scalper_stato`/`scalper_sessioni` sul canale (invariati, `scalperCanale.ts:28-29`). Consumati: comandi `approva_uscita`, `media_attiva_adesso`, `stop` (via postino/params).

### 4.3 Cosa diventa libreria comune "scalper" con lo sport come parametro

Senza cambiare le regole: le **19 funzioni identiche** del par. 3.1 e le 11 quasi identiche (ratio >= 0,88) passano a `scalper_core`; calcio e tennis le importano. Le 10 divergenti NON si uniscono finche' l'utente non conferma
che le differenze sono volute (decisione D2). Le 20 solo-calcio restano nel plugin calcio (o passano al tennis solo per decisione dell'utente: sarebbe CAMBIARE la strategia del tennis); le 12 solo-tennis nel plugin tennis.
Altre librerie mature: nessuna riscrittura di flumine/betfairlightweight in questo componente: l'ordine passa da `market.place_order` di flumine (`scalper_bot.py:2924`), i prezzi dalle utilita' flumine (`get_nearest_price`, `price_ticks_away`, `get_price`, `get_size`) gia' usate; il blotter e il ciclo di vita dell'ordine sono di flumine.
Oggi riscritto a mano e candidato a sparire: lettura params/serie (`c.get("`: 67 nel maker, 28 nello sniper, 43 nel theta = 138 letture, piu' 16 chiavi di `VALORI_DI_SERIE` del media = 154: `grep -c 'c\.get("'`), freno rifiuti (gemello in tennis, scheda C), minimi `.it` (due definizioni, scheda C).

### 4.4 Stima delle righe DOPO (con il calcolo)

Classi del nucleo calcio (13.627 righe), conteggio per intervalli di righe dall'indice delle funzioni (commenti e docstring inclusi):

| Classe | Come l'ho contata | Righe oggi |
|---|---|---:|
| **Strategia (resta, invariata)** | maker: `process_market_book`+cicli+gate+maker/join+presize+manage+flatten = 262+74+160+108+73+164+280+20+55+207 = 1.403, piu' regole d'uscita `scalper_bot.py:2454-2742` = 289 -> 1.692; sniper 342-769 (428) + scavalco/residuo 926-1038 (113) = 541; theta 1.313 - 239 (ctor + bus) = 1.074; media 2.637 - 724 (parametri 205, ctor 120, conto/ripresa 399) - 91 (`_piazza`) = 1.822; `risk_semaphore` 92; `bias_resolver` 229 | **5.450** |
| Libreria comune sport-agnostica (`scalper_core`) | maker: flusso/segnale 126 + funzioni pure 79 + `_Slot` 67 = 272 | **272** |
| Condotta ordini (-> scheda C) | maker: `_place` 2743-2949 (207) + submin 2950-3315 (366) + helper `.it` 88-243 (156) + proposte 2169-2246 (78) = 807; sniper 770-925 + 1039-1363 = 481; media `_piazza` 91 | **1.379** |
| Guscio nelle strategie (ctor/parametri/emit/closed-market/ripresa) | maker 87+347+80+30 = 544; sniper 341+24 = 365; theta 239; media 724 | **1.872** |
| Guscio di sessione/supervisione/CLI | `scalper_session` 2.303 + `scalper_service` 982 + `auto_mode` 440 + `run_*` 733 + `habitat_scan` 196 | **4.654** |
| Totale | 5.450 + 272 + 1.379 + 1.872 + 4.654 | **13.627** |

Quota: strategia **40,0 %**, guscio (nelle strategie + di sessione) **47,9 %** (6.526/13.627), condotta ordini **10,1 %**, libreria condivisibile **2,0 %**.

**Dopo (E4, solo Python del nucleo)**:
- Strategia: 5.450 (identica; nessuna regola cambia, quindi nessuna riga di strategia cala).
- `scalper_core`: 272 (condiviso col tennis; vedi sotto il risparmio).
- Guscio nelle strategie: 1.872 -> ~850. Calcolo: via la lettura a mano dei parametri (310 + 119 + 139 + 205 = 773 righe di ctor/parsing) sostituita da 154 voci di catalogo (67 + 28 + 43 + 16) = -619; restano ~1.099 -> ~700 (emit, closed-market, ripresa): 154 + 700 = ~850. Stima.
- Guscio di sessione: 4.654 -> ~950 di plugin specifico (thread `ht-watcher`/`sniper-line`/`theta-score`/`theta-confirm`, comando media e ripresa dal conto `:896-1049`, bias `:1286-1323`, `habitat_scan` 196, `giro_auto` specifico). Il resto (~3.700) diventa runtime comune D/A/I e non e' contato qui.
- Condotta ordini: 1.379 -> scheda C (una copia; il suo conto sta li').
- **Totale E4 dopo: 5.450 + 272 + 850 + 950 = 7.522 righe contro 13.627 (-6.105, -44,8 %)**: 1.022 spariscono (parsing params), ~3.704 vanno al runtime comune, 1.379 alla scheda C.
- **Motore maker calcio+tennis (E4/E5)**: 1.449 righe di codice uguali su 2.126 + 1.906 = 4.032 -> `scalper_core` ne tiene una copia: 1.449 + 677 (solo calcio) + 457 (solo tennis) = 2.583, **-1.449 righe di codice (-35,9 %)**, circa **-2.260 righe di file** (rapporto file/codice del file calcio 3.315/2.126 = 1,56). Contato nella scheda E5 per il tennis; qui e' il risparmio atteso del lato calcio se il tennis smette di tenere la copia.
- Frontend: 2.450 -> ~2.250 (via le tabelle di serie specchiate `scalper.ts:106-117` ~12 e campi `SCALPER_PARAM_FIELDS` 128-139 ~12 e `MEDIA_UNDER_DEFAULTS` `:41-62` ~22 e `MEDIA_UNDER_CAMPI` `:66-83` ~18 generati dal catalogo, piu' il codice del form ~130): stima prudente -200.
- Banco: 6.275 invariato in questa tappa (adattatore e controlli sono del componente H).

### 4.5 Sostituire questo componente: OGGI contro DOMANI

**OGGI** per cambiare una regola (es. la soglia del tetto di perdita o aggiungere un parametro) si toccano: `scalper_bot.py` (ctor `:686` + logica `:1159`), `scalper_session.py` (`VALIDATED_PARAMS` `:42`, `UI_PARAM_WHITELIST` `:72`), `lib/scalper.ts` (serie `:106`, campi `:128`), `ScalperPanel.tsx`, e per sniper/media i loro file e `lib/mediaUnder.ts`; per lo stesso difetto sul tennis `tennis_scalper_bot.py` (copia). Per sostituire l'intero scalper (es. altro motore): `scalper_session` + `scalper_service` + 4 bot + 7 file di frontend + `registro_bot.py:312-338` + `tools/replay_registrazioni.py` + `certificazione.py` (>= 20 file).
**DOMANI**: solo `bots/scalper_calcio/` (classi, catalogo, `COSA_FA.md`, banco) e i suoi test di contratto (`test_contratto.py`); UI e whitelist derivano dal catalogo; il guscio (D) non si tocca; il tennis non cambia.

---

## 5. PARITA'

**Registrazione di riferimento**: `_live_raw` 35797769 (qualita' COMPLETE 95,4 %); seconda registrazione 35760084 (citata dal cantiere 15, `SPECIFICHE_CANTIERI_CLOUD_2026-10-08.md:386`). Comando:
`python -m Betfair.stream.backtest.certifica scalper_calcio 35797769 --scenari base,paper,chiusura-abbinata-in-parte,rifiuti-betfair,sniper-paper`.
Impronta del codice nel referto: "codice bot fa6c7016c31e (12 file)" (`calcio_dopo_5.txt`, riga 2); 22 controlli attivi; flumine 2.13.11, betfairlightweight 2.23.2.

**Stato dei numeri**: i riferimenti sono in revisione. Il banco con la regola del "mercato che attraversa" (`ATTRAVERSAMENTO`) cambia i percorsi: `base` 44 -> **18 azioni**, `chiusura-abbinata-in-parte` **KO** (B2: residuo 0,91 aperto al fischio; CP4: chiusura LAY 1,02 con 0,91 residui),
fill anticipati alle 17:00:06 UTC (BACK 1,66 / LAY 1,65 / BACK 4,20 nello stesso book) - `SPECIFICHE_CANTIERI_CLOUD_2026-10-08.md:360-394`, `calcio_diff_5_scenari.txt`. **Nessuna parita' di E4 si firma prima che il cantiere 15 abbia fissato il nuovo riferimento** (`AUDIT_2026-10-08/riferimenti/`); i numeri sotto sono quelli di prima (07/10) e di dopo (08/10, banco realistico) per il confronto.

| Scenario (35797769) | tick | decisioni | azioni 07/10 (prima) | azioni 08/10 (banco realistico) | esito |
|---|---:|---:|---:|---:|---|
| `base` | 665.941 | 121.012 | 44 | **18** (motivi: place 11, close_presize 1, scratch 1, cycle 1, min_bet_skip 1, scavalco 1) | OK / OK |
| `paper` | 665.941 | 121.012 | 44 | 18 (identico a `base`: paper = live, controllo S6, 86 parametri confrontati, diversi 0) | OK / OK |
| `rifiuti-betfair` | 665.941 | 121.012 | 56 | da leggere in `calcio_dopo_5.txt` | OK / OK (secondo la sintesi del cantiere) |
| `chiusura-abbinata-in-parte` | 665.941 | 121.012 | 215 | | OK / **KO** (B2, CP4) |
| `sniper-paper` | 1.511.913 | 286.052 | 44 | | OK / OK |
| altri 07/10: `senza-missione` 254, `bot-fermo` 44 (233.803 tick, 42.486 decisioni), `kill-switch` 44, `esiti-ignoti` 44, `riavvio` 159 (KO), `sniper` 44, `sniper-uscite-auto` 44, `uscite-manuali` 244, `uscite-manuali-firmate` 64 (KO), `auto-live` 44, `media-under` 5 (78.022 decisioni), `media-under-paper` 5 | | | | | |

Gli scenari sono definiti in `tools/replay_registrazioni.py:767-` (`SCENARI_DESCRITTI`). Controlli (22): condotta K1-K7, B3-B6, S1-S7, P1-P2, CP1-CP4 (scenario `chiusura-abbinata-in-parte`), UM1-UM4 e UF1-UF3 (uscite manuali); volumi di sollecitazione nel referto completo del 07/10 (47 replay): S5 x463.834, P1 x360.868; nei 5 scenari del 08/10: K1 x7.067, S1 x8.668, P1 x33.511

**Cosa deve coincidere dopo la migrazione (stessa registrazione, stessi scenari)**: tick, numero di decisioni, numero di azioni, sequenza `(istante, selezione, lato, prezzo, importo, motivo)` di ogni ordine, stati dello slot visti, P&L bloccato e settlato, righe dello specchio (58.191 in `base` oggi), "book in ritardo" (589.606), fill per mercato che attraversa (3), conteggio dei controlli sollecitati per ognuno dei 22.
Procedura: referto confrontato numero per numero con il nuovo riferimento del cantiere 15, e una **cassetta di decisioni** (registro append-only dei `place/cancel` con prezzo e importo) prodotta dal vecchio e dal nuovo codice sullo stesso replay, differenza automatica = 0.

**Voci di `PROCESSO_STANDARD_BOT.md` coperte**:
- §6.1 dati di mercato: registrazione COMPLETE 95,4 %. §6.2 scanner e feed: "scanner non usato (lo scalper legge il book)" nel referto, quindi **⊘ con causa**; l'auto-mode (`giro_auto`) e' esercitato dallo scenario `auto-live`, non dalla coppia feed-scanner vera.
- §6.3 servizio intero: il banco monta `run_session` (`registro_bot.py:316-322`). §6.4 ciclo di vita dell'ordine: `rifiuti-betfair`, `esiti-ignoti`, `chiusura-abbinata-in-parte`, bet delay (book in ritardo 589.606), parziali.
- §6.5 persistenza e UI: P1/P2 (specchio) sollecitati; **fotografie della UI**: `frontend/src/lib/__fixtures__/replay_bot_media_under_35797769.json` e `__fixtures__/replay_pro/esito_scalper_base_69.json` esistono, ma non ho verificato che coprano ScalperPanel e Control Room per tutti gli stati.
- §6.6 concorrenza: S2 (stop), `bot-fermo`, `kill-switch`, `riavvio` (S7: oggi KO sul 07/10 e "mai sollecitato" nei 5 scenari del 08/10). §6.7 scenari e falsificazione: da rifare a ogni tappa (mutazioni: `AUDIT_2026-09-25/mutazioni_scalper_auto_mode.py` come precedente).
- §6.8 referto riproducibile: impronta `fa6c7016c31e`. §6.9 velocita': **violata** (47 replay = 6.916 s, par. 3.6).
- §7 (numeri del catalogo): 8 (fill scritto a mano: il banco usa il matching di flumine), 10 (Enum `OrderStatus`: K3 x34.266), 12 (bet delay), 17 (sospeso/chiuso: `guardia_flumine`), 19 (stato in RAM perso al riavvio: S7, **non sollecitato**), 21 (paper+live non si sommano: S6), 22 (bot che riparte da solo all'avvio app), 25 (modalita' per strategia), 27 (finti con chiavi e tipi del vero: obbligo per i finti del banco), 28-30 (test che asseriscono il falso / passano a vuoto / mutazioni: obbligatorie sui test nuovi), 31 (copia `scalper_lab`), 33 (costante frontend che duplica il backend: par. 3.4), 36 (consapevolezza: K1-K7), 37 (isolamento dei replay nella pool).
- Test esistenti da tenere verdi (almeno): `Betfair/stream/tests/test_scalper_*`, `test_sniper_*`, `test_theta_*`, `test_whitelist_linee_sniper_2026_09_28.py` (16 file, >= 4.879 righe); frontend 12 file (1.780 righe), `PannelloBotScalper.test.tsx`, `scalperControlRoom.test.ts`, `mediaUnder.test.ts`.

---

## 6. MIGRAZIONE

Ordine rispetto agli altri componenti (D, par. 6 della scheda: "Scalper e tennis per ultimi", `D_RUNTIME_BOT_CONTRATTO.md:510`): dopo A (connessione), C (porta ordini), D (runtime), perche' E4 dipende da tutti e tre.

0. **Prima di tutto**: cantiere 15 chiuso (`SPECIFICHE_CANTIERI_CLOUD_2026-10-08.md:360-394`): nuovo riferimento con banco realistico, `--scenari tutti` su 35797769 e 35760084, 0 violazioni, B2/CP4 spiegati. Il piano non contraddice il cantiere 15: non tocca nessuna regola, e le due prove del cantiere (B2 e CP4) sono i primi test di parita'.
1. **`scalper_core` dalle funzioni IDENTICHE** (le 19 del par. 3.1): estrazione meccanica, calcio e tennis le importano. Parita': `--scenari tutti` calcio e tennis identici al riferimento. Rischio basso. Ritorno: ripristinare gli import.
2. **Catalogo dei parametri** (una tabella): periodo ombra in cui il vecchio ctor/`VALIDATED_PARAMS` e il catalogo vengono CONFRONTATI automaticamente a ogni avvio (86 parametri della strategia gia' confrontati paper/live, `calcio_dopo_5.txt`); differenze = errore. Poi la UI legge dal catalogo.
3. **Condotta ordini a C**: il maker e lo sniper chiamano la copia unica; prima in "ombra" (la condotta di C calcola, quella vecchia piazza; differenze nella cassetta di decisioni = 0), poi taglio.
4. **Plugin `OspiteFlumine`** sul runtime D: il guscio vecchio (`scalper_session`) resta e si spegne per partita con un interruttore nei `params` della riga `scalper_control` (nessun processo nuovo, nessun nuovo servizio): se la partita parte con `engine=legacy` gira il codice di oggi. Un periodo in paper con confronto automatico, poi live SOLO se il paper conferma (§1 del processo; promemoria dovuto: lo scalper e' certificato sul replay vecchio, **non** sul banco realistico, finche' il cantiere 15 non e' chiuso).
5. **Motore maker unico calcio+tennis** (E4+E5) per ULTIMO e solo per le funzioni a ratio >= 0,88; per le 10 divergenti serve la decisione D2.
6. **Atlante e laboratorio**: spostamento dell'Atlante (6.038 righe) alla scheda G, archiviazione di `laboratorio/scalper_lab` (D4).

Rischi: (a) differenze di sport nascoste nelle funzioni a ratio basso (`_side_min` 0,15, `_size_direct_ok` 0,13, `_drive_flatten` 0,57); (b) il guscio e' dentro la stessa funzione `run_session` di 920 righe: lo spostamento puo' alterare l'ordine di avvio dei thread (specchio, freno, ht-watcher); (c) l'ordine dei commenti "07/10 ... C3" nei file mostra che le regole recenti non sono nel tennis: portarle e' CAMBIARE la strategia del tennis (non fare senza permesso); (d) il banco e' lento (115 min): senza correzione ogni tappa di migrazione costa ore.
Ritorno indietro: `engine=legacy` per partita; `git revert` per tappa; nessuna migrazione SQL (CLAUDE.md: le migrazioni le applica l'utente).

---

## 7. MISURE

| Misura | Oggi (fonte) | Obiettivo dopo |
|---|---|---|
| Righe nucleo calcio (strategie + guscio) | 13.627 (`wc -l`) | ~7.522 (-44,8 %, par. 4.4) |
| Chiamate DB del supervisore | 54/min (`MISURE_2026-10-02.md:46`), 3 tabelle/RPC ogni 3 s | <= 6/min (stato nel canale locale, DB solo al cambio; postino asincrono) |
| Chiamate DB per sessione di partita | >= 36/min stimate dal codice (battito 5 s: flush + heartbeat + params); **non misurate** | <= 6/min; params e comandi dal canale locale, stats al cambio |
| Lettura DB nel percorso del tick | 1 (`freno_live`, solo aperture, cache 2-5 s; latenza non misurata) | 0: freno e modo ordini in cache locale aggiornata dal postino |
| Costo CPU del tick (sessione intera, banco) | 12.559 tick/s (`calcio_dopo_5.txt`) | non peggiorare: stesso replay entro +/-5 % |
| Tempo book -> `place_order` nel processo | **non misurato** | misurare con sonda del banco (tempo di mercato e wall-clock) e fissare il tetto con A/C |
| Certificazione completa scalper calcio | 6.916 s (47 replay, `calcio_prima_tutti.txt`); 370,7 s (5 replay, `calcio_dopo_5.txt`) | <= 300 s, tetto 600 (ordine del 29/09) |
| Duplicati del maker col tennis | 1.449 righe di codice uguali (68,2 %/76,0 %) | 0 copie |
| Copie delle regole di condotta d'uscita (calcio) | 4 (maker 593 righe di codice, sniper 445, media `_piazza`, tennis) | 1 (scheda C) |
| Valori di serie | 3 posti (par. 3.4) | 1 (catalogo) |
| Chiamate `.table(` dirette | 20 + 16 | 0 dal guscio di E4 (solo postino e lettura di cache) |
| Memoria / processi | 1 supervisore + 1 processo per partita (tetto 2-4) con login proprio (scheda A) | misurare RSS per sessione (`psutil`) prima e dopo; non misurata ora |

---

## DECISIONI PER L'UTENTE

- **D1 - Un solo posto per i valori di serie.** Oggi `one_green_per_phase` e' `False` nel bot e in `VALIDATED_PARAMS` ma `true` nella UI (par. 3.4); la strategia in produzione e' quella con la UI. Confermi che il catalogo prenda i valori della UI come serie?
- **D2 - Unire il maker calcio e tennis.** 19 funzioni identiche si uniscono senza rischio; 10 funzioni hanno somiglianza < 0,70 (`_side_min`, `_size_direct_ok`, `_drive_flatten`, `_place_exact`, `_place`, ...). Sono differenze volute dello sport o ritardi di allineamento (le regole scavalco/residui/taglia del 04-07/10 esistono solo nel calcio)? Portarle al tennis cambierebbe la strategia del tennis: serve il tuo permesso.
- **D3 - Atlante hazard fuori da `scalper/`.** 6.038 righe usate da Mike, Omega, Safe: passano alla scheda G. Confermi?
- **D4 - `laboratorio/scalper_lab`.** 3.943 righe, 61,2 % uguale alla produzione: archiviare o tenere come sola lettura (§7.31)?
- **D5 - Theta.** Il verdetto S4 dichiara il classico EV- (solo raccolta dati): resta com'e' (nessuna modifica) o va escluso dal guscio nuovo? Non e' una decisione tecnica: il codice resta identico se non dici altro.
- **D6 - Velocita' del banco.** 47 replay = 6.916 s contro il tetto 600 s: il banco va accelerato (parallelismo per scenario, profilo) prima di migrare; nessun controllo si spegne (ordine del 29/09).

---

## COSA HO VERIFICATO DI PERSONA / COSA NON HO POTUTO VERIFICARE

Verificato con il codice (letto, `grep -n`, `sed -n`): indici di tutte le funzioni di `scalper_bot.py`, `scalper_session.py`, `scalper_service.py`, `sniper_bot.py`, `theta_bot.py`, `media_under_bot.py`, `auto_mode.py`; righe di `process_market_book`, `_check_event_guards`,
`_try_enter` (gate), stop/scratch/flatten, `_place`, `_esegui_place`; docstring e regole di `spezza_uscita`, `stato_parcheggio`, `ordine_di_scavalco`; parametri e valori di ctor di maker e sniper e (in parte) theta; i 36 punti `.table(` di sessione e servizio (conteggio 20 + 16 con `grep -c`); l'assenza di DB/rete nelle 6 strategie;
`freno_soldi_veri` -> `_live_brake` -> `motivo_kill_switch` (testi letti); misure di gemellaggio rieseguite con lo strumento del delegato precedente, anche con 5 coppie nuove; referti del banco (`calcio_prima.txt`, `calcio_prima_tutti.txt`, `calcio_dopo_5.txt`, `calcio_diff_5_scenari.txt`).

NON verificato / da fare:
- La latenza reale tick -> `place_order`, la latenza della lettura `freno_live` quando la cache e' scaduta, e se l'assegnazione `strategy.freno_live` (`scalper_session.py:1808`) e' condizionata a soldi veri: strumento = sonda del banco con tempi o py-spy.
- Le chiamate DB al minuto di una SESSIONE di partita (nelle misure del 02/10 ce n'era solo il supervisore): 36/min e' un minimo ricavato dal codice, non una misura.
- Per `theta_bot.py` (1.313 righe) e `media_under_bot.py` (2.637) ho letto docstring, spec e regole chiave (`_puo_aprire`, `_pre_match`, `_perche_non_entra`, `_forse_rientro`, `_piano_rientro`, formule `531-625`), NON ogni riga: le funzionalita' E4-040..042 e E4-050..059 sono complete a livello di funzione e regola, i dettagli (es. `_allinea_banche`, `_ricostruisci`) sono citati per riga ma non riletti uno a uno.
- I parametri di theta oltre quelli elencati e i valori di serie di `theta`/`sniper` non indicati: non riletti tutti.
- Le righe degli `_emit` di sniper, theta e media (par. 2.H) non sono elencate una per una.
- La stima delle classi di righe (par. 4.4) e' per intervalli di righe da indice di funzioni (include commenti e docstring); le percentuali "gemello" sono per righe di CODICE uguali (difflib), un limite per difetto.
- I risultati dei 5 scenari del cantiere 15 per `rifiuti-betfair`, `chiusura-abbinata-in-parte`, `sniper-paper` nel referto del 08/10: letti solo `base` e `paper` e le note di sintesi del cantiere; i numeri vanno ricontrollati nel referto `calcio_dopo_5.txt` e rifatti dopo il cantiere 15.
- Se le fotografie della UI (`__fixtures__`) coprono tutti gli stati di ScalperPanel e Control Room.
- Le registrazioni 35760084 non e' stata aperta.
- La riga esatta di `_SCAVALCHI_MAX_PER_CICLO` (valore 3 letto da BIBBIA §13-bis, non dalla costante).
