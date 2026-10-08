# SCHEDA D - RUNTIME DEI BOT E CONTRATTO COMUNE (prefisso `D-`)

Perimetro (righe da `wc -l` sui file tracciati, `git ls-files`): servizi dei bot
`Betfair/mike/service.py` 7.551 · `Betfair/omega/omega_service.py` 8.936 · `Betfair/safe_strategy/bot_service.py` 11.136 ·
`Betfair/stream/scalper/scalper_service.py` 982 · `scalper_session.py` 2.303 · `run_scalper_live.py` 292 ·
`Betfair/stream/tennis_live/tennis_bot_service.py` 1.183 · `tennis_runner.py` 3.483 (l'hosting dei 4 bot tennis) = **35.574 righe**
nei 7 file misurati (escluso `run_scalper_live.py`); guscio condiviso gia' esistente `avvio_app.py` 336, `arresto_ordinato.py` 77,
`single_instance.py` 36, `sveglia_canale.py` 390, `canale_bot.py` 426, `arresto_bot.py` 198; accessori DB per bot `mike/db.py` 693,
`omega_db.py` 1.081, `bot_db.py` 1.044, `tennis_db.py` 869; registro e banco `registro_bot.py` 440, `applica_bot.py` 892,
`varianti_bot.py` 461 (+ `banco_comune.py` 3.046, `certifica.py` 1.084, 6 adattatori di replay 14.114 righe: componente H).
Data 08/10/2026. Autore: delegato Sonnet. Strumenti rieseguibili in `ARCHITETTURA_2026-10/strumenti/`:
`D_gemelle_servizi.py gemelle` (rieseguito, funziona: 57 nomi di funzione presenti in >=2 servizi con somiglianza difflib) e
`D_scheletro_righe.py {misura|elenca|db}` (nuovo, scritto da me: righe per ruolo e funzioni DB gemelle).
La strategia di ogni bot e' trattata dalle schede E: qui solo lo SCHELETRO che i servizi ripetono.
Fonti gia' pronte e usate: `00_INVENTARIO.md`, `07_MISURE_OGGI.md` (§4.2, richieste/min per servizio), `A_CONNESSIONE_BETFAIR.md`
(tabella porte, riga 158-162).

---------------------------------------------------------------------------------------------------

## 1. OGGI

### 1.1 Come e' fatto davvero il runtime (letto dal codice, non dai nomi)

Non esiste UN runtime: esistono **cinque famiglie di servizio** che realizzano lo stesso scheletro con codice diverso.

| Famiglia | Processo | Unita' di lavoro | Come decide | Dove vive lo stato |
|---|---|---|---|---|
| Mike | 1 processo, ciclo a giro | una partita = una macchina a stati (`E.STATES`) | funzione PURA `engine.decide(ctx, snap, params) -> Decision` (`mike/engine.py:3089`), chiamata da `_run_event` (`service.py:4739-5514`, 776 righe) in `service.py:5007` | riga `mike_events` (ctx JSON) + `mike_trades`; RAM `_CACHE_EVENTI` (`service.py:426`) |
| Omega | 1 processo, ciclo a giro | una partita x 2 gambe (`_LEGS`, `omega_service.py:1874`) | selezione DENTRO il servizio con accesso al DB: `_scan_event_legs` 1941, `_model_select` 1397, `_v3_select` 1590 | righe `omega_trades`; RAM `_LAMBDA_CACHE` 1057, `_EMPIRICAL_CACHE` 1313, `_MINUTE_CACHE` 1316 |
| Safe (5 varianti: base, esatto, punta, tennis + opportunita'/anomalie/combo) | 1 processo `bot_service` + 1 processo scanner `service.py` (NON_BOT, `registro_bot.py:410-413`) | TUTTE le righe del feed insieme | `SafeEngine.evaluate(rows) -> List[Signal]` (`safe_strategy/engine.py:1980,2112`) stateful (tracker anti-blip `_stab`, segnali attivi), chiamato da `scan_and_place` (`bot_service.py:7052`, riga ~7068); poi `process_opportunities` 7726, `process_anomalies` 9387, `process_exits` 4254 | righe `safe_strategy_trades`; RAM `_OPPS_STATE`, tracker del motore (persi al riavvio: catalogo §7 n.19) |
| Scalper calcio | **supervisore** (`scalper_service.py`) + **1 processo per partita** (`scalper_session.py`, flumine proprio con login proprio: docstring `scalper_service.py:1-12`) | un MarketBook di una partita | flumine chiama `check_market_book`/`process_market_book` a ogni aggiornamento (`scalper_bot.py:769,817`; `sniper_bot.py:322,377`; `theta_bot.py:564,612`; `media_under_bot.py:1098,1116`) | riga `scalper_control` per partita + blotter di flumine in RAM del processo figlio |
| Tennis (scalper, pro, FLB, swing) | **ponte** (`tennis_bot_service.py`) + **runner** (`tennis_runner.py`) che OSPITA i 4 bot nello stesso framework flumine (`_BOT_REGISTRY` `tennis_runner.py:126-131`) | un MarketBook di un evento, stream unico condiviso | flumine come lo scalper (classi `tennis_scalper/*_bot.py`) | riga `tennis_bot_control` + blotter in RAM del runner |

### 1.2 Misura dello scheletro (strumento `D_scheletro_righe.py misura`, riga di comando in 1.6)

Righe delle sole `def`/`class` di primo livello, classificate per nome da me (elenco S scritto nello script, rieseguibile).
S = scheletro del runtime; M = misto (`run_session`, `setup_and_run`, `_instantiate_bot`: scheletro e configurazione di strategia
insieme); R = resto (strategia, ordini, regolamento: schede C, E, F). Il testo FUORI dalle def (import, costanti, commenti di
modulo) non e' contato: 4.842 righe in piu' sui 7 file.

| File | Righe file | def/class | **S scheletro** | M misto | R resto |
|---|---:|---:|---:|---:|---:|
| `mike/service.py` | 7.551 | 6.556 | **2.033** | 0 | 4.523 |
| `omega/omega_service.py` | 8.936 | 7.748 | **1.763** | 0 | 5.985 |
| `safe_strategy/bot_service.py` | 11.136 | 9.617 | **2.301** | 0 | 7.316 |
| `scalper/scalper_service.py` | 982 | 856 | **856** | 0 | 0 |
| `scalper/scalper_session.py` | 2.303 | 1.985 | **798** | 918 | 269 |
| `tennis_live/tennis_bot_service.py` | 1.183 | 969 | **969** | 0 | 0 |
| `tennis_live/tennis_runner.py` | 3.483 | 3.001 | **1.432** | 512 | 1.057 |
| **Totale** | **35.574** | 30.732 | **10.152** | **1.430** | **19.150** |

Lo scheletro e' il **28,5%** delle righe dei 7 file (32,5% con il misto). Il 54% (19.150) e' strategia/ordini/regolamento.
Nota di metodo: la classificazione e' per nome di funzione (un giudizio mio): `run_once` conta tutta come S perche' e' in
maggioranza orchestrazione (control, params, richieste, apertura partite, loop per evento, stats, battito), ma contiene anche
poche righe di regole (es. stop giornaliero `service.py:~4040`); `_RealMarket` (131-302) conta S perche' e' un adattatore.

### 1.3 Copie letterali dello scheletro (strumento `D_gemelle_servizi.py gemelle`)

Funzioni gemelle con somiglianza difflib >= 0.85 (righe ridondanti = tutte le copie tranne la piu' lunga):

| Funzione | Copie (file:riga(righe)) | Somiglianza | Ridondanti |
|---|---|---:|---:|
| `ferma_al_nuovo_avvio` | mike 3964(32), omega 7966(30), safe 10083(30) | 0,95-0,98 | 60 |
| `_avvia_sveglia` | mike 6925(37), omega 8671(34) | 0,90 | 34 |
| `_avvia_canale` | mike 6831(15), omega 8590(15), safe 10572(17) | 0,91-0,98 | 30 |
| `_ciclo_persistente` | mike 7289(14), omega 8773(14), safe 10877(12) | 0,87-0,98 | 26 |
| `_netto_su_selezione` | mike 3071(26), safe 1806(27) | 0,93 | 26 |
| `_richiesta_non_di_questa_riga` | omega 5943(25), safe 3469(21) | 0,98 | 21 |
| `_su_sveglia_dal_canale` | mike 6911(12), omega 8656(13), tennis_svc 299(8) | 0,97-1,00 | 20 |
| `_pubblica_stato` | omega 8753(18), safe 10607(19) | 0,90 | 18 |
| `_Cache` (`fresco/metti/svuota/__init__`) | mike 396-415, omega 169-185 | 0,94-1,00 | 10 |
| `_chiudi_all_arresto` | omega 8789(9), safe 10891(9) | 0,98 | 9 |
| `_evento_seguito` | mike 6886(8), omega 8623(10) | 0,92 | 8 |
| `_control_per_canale` | omega 8744(7), safe 10597(8) | 1,00 | 7 |
| `_scanner_stato` | mike 1384(5), safe 4124(5) | 0,88 | 5 |
| `_now`, `_now_iso`, `_al_segnale` | mike 305/omega 41/safe 312; scalper 51/304; mike 7391/scalper_sess 2276 | 1,00 | 10 |
| **Totale copie letterali** | | | **~284 righe (2,8% di S)** |

**Reperto 1 (il piu' importante di questa scheda)**: le copie letterali sono POCHE (284 righe). Il grosso dello scheletro non e'
copia-incolla ma **lo stesso ruolo realizzato quattro volte in modo diverso** (somiglianza 0,05-0,60): `run_once` (mike 3998-4369 372 righe,
omega 8149-8516 366, safe 10115-10461 336: somiglianza 0,10-0,15), `main` (0,49-0,60), `process_requests` (mike 3636 / safe 2669, 0,28),
`_un_giro`, `_cadenza_battito` (0,41-0,69), `svuota_le_cache` (0,20-0,35). Quasi-gemelle (0,70-0,85, uniformabili con piccole
varianti da preservare): `_avvisa_feed_non_letto` mike 7144 / safe 9599 (0,79), `_uscita_del_bot_approvata` omega 5891 / safe 3829 (0,80),
`_dormi_o_sveglia` mike 6988 / omega 8724 (0,71), `_pavimento_sveglia` mike 6896 / omega 8635 (0,72), `_un_giro` mike 7471 / omega 8841 (0,72).
Quindi la riduzione NON viene dal dedup ma dall'**implementare una volta il ruolo**. Accessori DB (`D_scheletro_righe.py db`): su
mike_db/omega_db/bot_db/tennis_db le funzioni omonime sono 34; gemelle quasi letterali `_now_iso`, `_sb` (1,00),
`enqueue_live_order` mike 662 ~ safe 1003 (1,00), `get_live_order_request` omega 655 ~ safe 1018 (0,93), `live_follow_status` omega 615 ~ safe 987
(0,92), `proposta_di_chiusura_viva` omega 366 ~ safe 625 (0,91), `get_live_order_mirror` (0,88), `runner_heartbeat` (0,86); `read_control`/`set_control`/`log`
sono 3 copie da 3-10 righe in 3 moduli (`mike/db.py:59,64,71`, `omega_db.py:49,55,61`, `bot_db.py:62,70,77`) con tre tabelle diverse.

### 1.4 Ciclo, cadenza e attese (tutti gli orologi)

- **Mike**: giro `run_once` (`service.py:3998`); attesa `interval = max(1.0, decide_min_interval_ms/1000*2)` (`_un_giro` 7471-7519), allungata a
  `idle_cycle_s` se il giro non ha "fretta" (`res.fretta` calcolata in `run_once` da richieste/gambe in attesa/in-play); dormita interrompibile
  `_dormi_o_sveglia` 6988 (sveglia dal canale `_AlzaSveglia` 6864). Battito `set_control(stats, heartbeat_at)` rate-limitato da
  `stats_min_s`/`heartbeat_min_s` (`service.py:4347-4364`). Eventi dal DB riletti ogni `events_reload_s` (cache `_CACHE_EVENTI` 426, lettura in `run_once`).
- **Omega**: `interval = 20` di riserva, poi `params["poll_interval_s"]`, allungato a `idle_cycle_s` senza "fretta" (`_un_giro` 8841-8891, `omega_service.py`);
  `_dormi_o_sveglia` 8724; fasi a cadenza propria con `_fase_dovuta` 325 (`results_every_s`, `missions_every_s`, `sets_cache_s`: `_cadenza` 250);
  rinfresco eventi ogni `EVENTS_REFRESH_EVERY_S = 1800` (7751); stats a bot fermo ogni `IDLE_STATS_EVERY_S = 60` (7742); keepalive Betfair ogni
  `KEEPALIVE_EVERY_S = 600` (8526, `_maybe_keepalive` 8541).
- **Safe**: `interval = poll_interval_s` (default 2.0, `_un_giro` 10945-11018); attesa `_attesa_interrompibile` 10676 / `_attesa_con_giro_veloce` 10769;
  minimo `_MIN_GIRO_S = 0.25` (blocco 9466-9511); **giro veloce** su evento di prezzo (`run_giro_veloce` 9912, `giro_veloce_se_dovuto` 9997,
  `_fotografa_giro_lento` 9785): esiste SOLO in Safe.
- **Scalper**: supervisore `POLL_S = 3.0` (`scalper_service.py:43`); sessione `HEARTBEAT_S = 5.0` (`scalper_session.py:35`), watcher in thread
  (HT: 1734-1760; linea sniper 1886-1895 ogni `SNIPER_LINEA_OGNI_S = 15` (733); `set_goals`/`live_minute` 1906-1915); habitat scan ogni 1800 s
  (`scalper_service.py:880-903`); auto-mode `giro_auto` 350-569.
- **Tennis**: ponte `ENSURE_POLL_SEC = 15.0` (`tennis_bot_service.py:46`), `_ensure_loop` 1050-1079 con sveglia `_dormi_o_sveglia` 336; nel runner
  `bot_control_worker` 1738-1980 con cadenza `_intervallo_bot_control` 1730 e sveglia di armamento 1715; worker `lifecycle_worker` 2125, `stall_worker` 2280,
  `score_and_now_worker` 1619 (punteggio ogni 2 s), `ladder_worker` 1455.

### 1.5 Lettura del book e del punteggio (chi legge cosa, da dove)

| Bot | Book | Punteggio / minuto | Fonte | Rete verso il DB nel percorso della decisione |
|---|---|---|---|---|
| Mike | righe del FEED unico `safe_strategy_scan` (payload con blocchi `ou`...) via `_righe_del_feed` 7167-7222: canale locale 47336 se acceso (`avvia_client_scan` 7047), altrimenti `fetch_scan_rows` (`mike/db.py:553`); REST di ripiego `_books_ripiego_rest` 1297 / `_RealMarket.read_book` 146 (che chiama `omega_market.read_book`) | dal payload (`feed.py`, `Snapshot.minute/goals/ht_active` `engine.py:180-210`) | DB o canale 47336, NON lo stream in-process | SI: lettura feed ogni `feed_cache_s`/`_RISINC_FEED_S` |
| Omega | blocco Correct Score del feed (`_riga_del_giro` 682, `_fondi_riga` 669, `_feed_row` 913) con REST fresco se il feed non e' fresco per decidere (`_feed_fresh_for_decision` 1095, `_leg_market` 1771) | `_build_score_lookup` 8905-8934 (feed, poi `db.read_live_now`) | DB/canale 47336 + REST | SI (e tabelle empiriche dal DB, cache 6 h) |
| Safe | righe del feed `_leggi_righe_scan` 9621-9753 (canale 47336 con riallineamento DB ogni `_RISINC_DB_S = 10` s, blocco 9466-9511) e prezzi `prices_for` 786 / `rest_gate` 764 | dal payload della riga (`build_football_ctx_from_scan` `engine.py:691`, tennis 804) | DB o canale | SI |
| Scalper | `MarketBook` dello stream flumine del PROPRIO processo (login proprio) | tabella `live_now` letta da thread watcher della sessione (`scalper_session.py:1756,1891,1911`) | stream in-process + **DB per il punteggio** | si', solo per minuto/gol |
| Tennis | `MarketBook` dello stream unico del runner (capture + bot sulla STESSA subscription, `tennis_runner.py:893-925`) | `score_and_now_worker` 1619 con `ScanFeedScoreProvider` sul feed unico (`_scan_feed` 1611) | stream in-process + feed scanner | solo punteggio |

Conseguenza (verifica del requisito utente §9.3 «nessuna rete tra messaggio e decisione»): **i tre bot a polling (Mike, Omega, Safe) NON
rispettano il requisito oggi**: leggono il feed dal DB/canale, cadenza di giro, non il tick dello stream. Scalper e tennis lo
rispettano per il book ma leggono il minuto da `live_now`. Misure dell'eta' del feed e del percorso: `07_MISURE_OGGI.md` §1-§3 (non rifatte qui).

### 1.6 Comandi e controllo dall'app

| Bot | Tabella di controllo | Tabella comandi | Comandi gestiti | Righe |
|---|---|---|---|---|
| Mike | `mike_control` (id=1) `mike/db.py:32-37,59-70` | `mike_requests` (`requests_da_lavorare` db 467, `fail_stale_processing` 519, `set_request_status` 499) | `approva_uscita` (`service.py:3679,3775`), `cancel` (3820), `flatten`/cash out (3850), altri in `process_requests` 3636-3738 | stale 10 min `_STALE_REQUEST_MIN` 73 |
| Omega | `omega_control` (`omega_db.py:49`) | `pending_manual_requests` 281, `set_manual_status` 289 | `process_manual` 5425 -> `_manual_place` 5514, `_manual_cashout` 6014; chiusura utente 4939; `chiudi_eventi_in_attesa` 6316 | |
| Safe | `safe_strategy_control` (`bot_db.py:62`) | `safe_strategy_requests` (`pending_requests` 604, `fail_stale_processing` 858) | `process_requests` 2669: `_request_place` 2917, `_request_place_combo` 3252, `_request_cashout` 3492, `_request_cashout_event` 3677, `_request_cancel` 4046, `_request_riprendi_evento` 3814 | |
| Scalper | `scalper_control` (per PARTITA) + `scalper_service_control` (interruttore globale auto-mode) (`scalper_service.py` `Db` 69-218, `TABELLA_SERVIZIO`) | colonna `comando` (media under: `consegna_comando_media` `scalper_session.py:1000`) | armare/fermare = cambio di `status` (`requested`, `stopping`); freno `freno_supervisore` 685 | |
| Tennis | `tennis_bot_control` (per bot x evento) `tennis_db.py:214,391` | `tennis_live_follow`, `chiusura_manuale.py` (425 righe, "chiudi ora") | `bot_control_worker` 1738; `_cm.avanza` per il chiudi ora; `uscite_proposte` | |

### 1.7 Accensione/spegnimento, paper/live, interruttore uscite (condizioni 4-bis, 4-ter)

- **Indipendenza dei bot (4-ter)**: ogni servizio e' un processo con la sua riga di controllo; verificato nel codice che l'accensione di uno scrive solo la
  sua tabella. Nel tennis i 4 bot condividono un solo runner ma hanno una riga ciascuno (`_desired_controls` 1154, `_stopping_controls` 1178).
- **Avvio app = nessun bot opera** (cond. 22 del catalogo §7): `avvio_app.Guardia` 113-160 e `ferma_al_nuovo_avvio` 217-300 (336 righe, condiviso) usato da
  Mike (`service.py:3964-3995`, `uscite_bot="mike"` 3991), Omega (7966), Safe (10083, `_GUARDIA_AVVIO` 9466), scalper (`ferma_sessioni_al_nuovo_avvio`
  `scalper_service.py:233`, `controllo_avvio` 250), tennis (`ferma_bot_al_nuovo_avvio` `tennis_bot_service.py:60`, `ferma_interruttori_al_nuovo_avvio` 958,
  `ripresa_ponte` 1020).
- **Interruttore uscite MANUALE/AUTOMATICO: cinque forme diverse della stessa informazione** (la mappa unica e' `avvio_app.uscite_a_manuali` 173-215):

| Bot | Chiave nativa | Valore MANUALE | Dove si applica a caldo |
|---|---|---|---|
| Mike | `uscite_automatiche` bool (`mike/config.py:263`, default False) | False | letta da `merge_params` a ogni `run_once` |
| Scalper | `uscite_automatiche` bool nei params della riga | False / assente | `applica_uscite_automatiche` `scalper_session.py:1185-1206`, riletta ogni battito (2090-2101) su maker e sniper |
| Omega | `uscite_protezione` `'avvisa_e_proponi'` / `'automatico'` (`omega_config.py:322,325,361`) | `avvisa_e_proponi` | `_greenup_active(params)` 6436 sceglie `process_auto_greenup` 7341 o `process_proposte_uscita` (in `_fasi_di_gestione` 8035) |
| Safe | mappa `uscite_automatiche{strategia: bool}` + `tennis_exit_approval` (`bot_service.py:170-183,440-475`) | tutte False + approval True | `uscite_automatiche_di(params, strategia)` 462 |
| Tennis | colonna `tennis_bot_control.uscite_automatiche` per bot (`tennis_db.py:209-214`, `auto_mode.py:33,215`) | False | attributo di classe `uscite_automatiche` (`tennis_scalper_bot.py:312`, `tennis_pro_bot.py:100`), `_aggiorna_uscite` `tennis_runner.py:2003` |

- **Paper/live: granularita' diversa**: globale (Mike `control.mode` + gate `mike_live_abilitato` `service.py:103-128`, e per partita `ev["mode"]`,
  `partite_di_modalita_diversa` 4469; Omega `control.mode`, `_porta_per` 3144), per strategia (Safe `modalita_di_strategia` 477, `strategy_modes_a_paper` 10029), per
  sessione (scalper `session_paper`, `_order_client_kwargs` 787, `_theta_dry_run` 766), per bot-riga + modo del runner (tennis `live_order_mode` `tennis_runner.py:139`,
  `modalita_esecuzione_bot` in `guardie_tennis.py`). Divergenza da preservare, non da uniformare di iniziativa.

### 1.8 Persistenza, riavvio, fasi

- **Mike**: `_persist` 6706 (con `before_sig`, scrive solo se cambia), `_scrivi_evento` 6670, lotto `_svuota_lotto` 6751; ctx <-> riga `_ctx_from_row` 501,
  `_row_from_ctx` 541, `_legs_from_json` 464; ricostruzione: `db.list_events(since 48 h)` in `run_once`, riconciliazione `_reconcile_trades` 5713 e `_reconcile_unknown` 5816,
  `_aggancia_riserve_orfane` 5652. Fasi = stati di `engine` (`_decide_prematch` 3617, `_decide_ko_green` 4050, `_decide_second_entry` 4249, `_decide_uncovered` 4468,
  `_decide_cover_pending` 4784, `_decide_covered` 4949, `_decide_closing` 5044, `_decide_flat` 5158, `_decide_reentry_*` 5192-5278); terminali SETTLED/ERROR/SKIPPED (`mike/db.py:86-90`).
- **Omega**: stato = righe `omega_trades` (`open_trades` db 246, `traded_event_ids` 191, `traded_legs` 212, `failed_legs` 136), niente macchina a stati in RAM; riavvio:
  `load_failed_legs` 2095, `reconcile_pending` 4337, `settle_open` 4971. Fasi: `omega_engine.mission_phase` (866) e `_LEGS` 1874.
- **Safe**: stato = `safe_strategy_trades` (`_safe_open_trades` 9211, `build_risk_ctx` 6688 a ogni giro); tracker del motore in RAM (persi al riavvio, §7 n.19);
  `seed_place_attempts` 6191 riallinea i tentativi dal DB. Fase da scan `_fase_da_scan` (`engine.py:789`), log `_log_fase_ignota` 6931.
- **Scalper**: catena di `status` `requested -> arming -> armed -> running -> stopping -> stopped|error` (`scalper_session.py:1384,1452,1839,2228`; `sessione_da_avviare`
  `scalper_service.py:694`); orfane `marca_orfana` 657 dopo `ORPHAN_HEARTBEAT_S`; ripresa media under `prepara_ripresa_media` 916; crash flumine `_handle_flumine_crash` 824.
- **Tennis**: `_ARMED_STATUSES` 133; riavvio del framework per armare (`_request_restart` 1298) oppure armamento a caldo (`_arma_a_caldo` 2674,
  `_allinea_follow_a_caldo` 2488); residui dopo riavvio `ResiduiRicordati` (`condotta_ordini.py:524`); controlli orfani `_cleanup_orphan_bot_controls` 3048.

### 1.9 Attivita'/diario per la UI, logging, battito, lock, errori

- **Diario**: `log(kind, payload)` e' scritto in 3 moduli con tabelle diverse (`mike_activity` `mike/db.py:71-85`, `omega_activity` `omega_db.py:61-72`, `bot_db.py:77`),
  poi `pubblica_scritte` sul canale locale (`canale_bot.py`, topic `mike_attivita`/`omega_attivita`); scalper `Db.log`/`log_many` (`scalper_session.py:1268-1284`);
  tennis `tennis_bot_activity` + `_make_sink` (`tennis_runner.py:847`).
- **Stats per la UI**: Mike ~40 chiavi (`run_once` blocco `stats = {...}` ~4285-4343), Omega `_idle_stats` 7836 + stats di `run_once` (8508), Safe `stats` di `run_once`
  (con `risk`, `opps`, `params_effective`), scalper `_stats()` in `run_session` e `PubblicaSessioni` 619, tennis `_stats_battito` 382. Le chiavi NON sono uguali fra bot.
- **Logging Python**: `logging.basicConfig(...)` ripetuto in ogni `main` (mike 7430, omega 8801, safe 10905, scalper 845, tennis 1128).
- **Lock di processo**: `single_instance.acquire_single_instance_lock` (36 righe, porta localhost). Usato da Mike 7426, Safe `_SINGLE_INSTANCE_PORT = 47318` (`bot_service.py:139`),
  scalper (47314), tennis ponte (47312); **Omega ha una COPIA propria** `_acquire_single_instance_lock` 8563 (porta 47313, 8520). `run_scalper_live.py` (292 righe, CLI fail-closed
  `SCALPER_LIVE_CLI`, 44-64) usa la stessa porta del supervisore.
- **Errori e ritenti**: ogni `_un_giro` ha `except Exception` che scrive `db.log("error", {reason: "cycle_exception"})` (mike ~7490, omega ~8880, safe 10990 con `critical` +
  `_segnala_errore_di_ciclo` 10464); il supervisore scalper azzera `db_sano_dal` (FIX-C, `scalper_service.py:~970`); il ponte tennis rilancia dopo 10 s (`_main` 1127-1180).
- **Arresto ordinato**: `arresto_ordinato.richiesto()` (77 righe, scritto da `main.js`) controllato PRIMA di ogni giro in `_ciclo_persistente` (mike 7289, omega 8773, safe 10877);
  Mike annulla gli ordini non abbinati con tetto 10 s e dichiara le posizioni (`arresto_con_ordini` 7315-7388, copia propria), Omega/Safe passano da `arresto_bot.chiudi_bot_all_arresto`
  (198 righe), scalper `chiudi_all_arresto` 667 + `attendi_e_termina_flat` 792 + kill-switch file `STOP_SCALPER`, tennis `arresto_worker` 2074 / `chiudi_alla_uscita_tennis` 2087.

---------------------------------------------------------------------------------------------------

## 2. FUNZIONALITA' (D-001 ... D-072) - elenco dello scheletro, con file:riga

Legenda UI: [UI] visibile nell'app (pannelli Control Room dei bot); [P] parametro editabile.

Ciclo e orologi
- D-001 Ciclo principale persistente Mike - `mike/service.py:7416-7548`, `_ciclo_persistente` 7289 - gira finche' l'app non chiede l'arresto.
- D-002 Ciclo Omega - `omega/omega_service.py:8800-8902`, `_ciclo_persistente` 8773.
- D-003 Ciclo Safe - `safe_strategy/bot_service.py:10902-11034`, `_ciclo_persistente` 10877.
- D-004 Supervisore scalper (un processo per partita) - `scalper_service.py:844-979`, `_ciclo_supervisore` 827.
- D-005 Sessione scalper per partita - `scalper_session.py:1324-2241`.
- D-006 Ponte tennis follow/interruttori - `tennis_bot_service.py:1050-1124`.
- D-007 Hosting dei 4 bot tennis nel runner - `tennis_runner.py:3121-3463`, `bot_control_worker` 1738.
- D-008 Cadenza adattiva "con fretta"/"a riposo" - mike 7471-7519 + `res.fretta`; omega `_c_e_fretta` 7906; safe `_un_giro` 10945. [P: `idle_cycle_s`, `poll_interval_s`, `decide_min_interval_ms`]
- D-009 Sveglia dal canale locale che anticipa il giro - mike 6864-7039, omega 8619-8740, safe 9554-9578 e `_attesa_interrompibile` 10676, tennis `tennis_bot_service.py:299-340`.
- D-010 Giro veloce su evento di prezzo (solo Safe) - `bot_service.py:9754-10028`.
- D-011 Battito rate-limitato (`stats_min_s`/`heartbeat_min_s`) - mike 4347-4364, `_cadenza_battito` mike 4435 / omega 7782 / safe 10054. [P]
- D-012 Keepalive della sessione Betfair del bot - omega 8541 (tennis `_maybe_keepalive` `tennis_runner.py:1583`; scalper `mantieni_sessione` `scalper_session.py:805`).
- D-013 Fasi di gestione che girano SEMPRE anche a bot fermo - omega `_fasi_di_gestione` 8035-8108; mike/safe: richieste, riconciliazione e regolamento prima dell'apertura (`run_once`).

Lettura dati
- D-014 Feed unico dal canale locale 47336 con fusione col DB - mike `_righe_del_feed` 7167, safe `_leggi_righe_scan` 9621, omega `_riga_del_giro` 682.
- D-015 Eta' massima del dato per decidere/aprire - omega `FEED_MAX_AGE_S` 85, `DECISION_MAX_AGE_S` 89; mike `Snapshot.order_fresh` `engine.py:180`; safe `_row_is_fresh` 8502.
- D-016 Ripiego REST se il feed e' fermo - mike `_books_ripiego_rest` 1297; safe `rest_gate` 764, `_prezzi_ripiego_rest` 9226; omega `_leg_market` 1771.
- D-017 Punteggio/minuto dal feed o da `live_now` - omega `_build_score_lookup` 8905; scalper watcher `scalper_session.py:1734-1915`; tennis `score_and_now_worker` 1619.
- D-018 Dossier pre-partita (cloud) all'armamento - mike `D.build_prematch` `service.py:4159`, ritenti `_retry_dossier` 6619; omega `_prematch_lambdas` 1169; safe `resolve_event_lambdas` 7595.
- D-019 Tabelle empiriche dal cloud con cache - omega `_empirical_table` 1350 (`EMPIRICAL_CACHE_TTL_S` 106 = 6 h), `_minute_table` 1319; mike `D.load_atlas` (main).
- D-020 Eta' dello scanner (battito del feed) - mike `_scanner_age` 1413, safe `_scanner_ts` 4088, omega `_scanner_eta_cached` 489.

Controllo, parametri, modo
- D-021 Lettura della riga di controllo ogni giro - mike `db.read_control`, omega `_leggi_controllo` 8021, safe `_control_per_il_giro` 10839. [UI: stato running/stopping/stopped]
- D-022 Controllo illeggibile: tre politiche diverse (mike salta il giro `run_once`; omega `_giro_senza_controllo` 8110 con `_ULTIMO_CONTROLLO_MAX_ETA_S = 300`, 8018; safe cache `_LAST_CONTROL` e protezione in `run_once`).
- D-023 Fusione parametri col default e correzioni - mike `C.merge_params`, omega `omega_config.resolve_params`, safe `resolve_params` 319, `params_corrections` 566, `normalize_control_params` 623. [P]
- D-024 Parametri effettivi mostrati in UI - safe `params_effective` 529; mike `_params_for` 1476. [UI]
- D-025 Ricostruzione dei modelli se i parametri cambiano - safe `params_signature` 10517 e `_un_giro`.
- D-026 Modo paper/live con gate di abilitazione live - mike `mike_live_abilitato` 103, `_pretendi_live_abilitato` 117; omega `_porta_per` 3144.
- D-027 Tetto partite aperte e blocco per modo - mike `posti_occupati_per_modo` 4412, `cap_partite` in `run_once`; safe `_BLOCCO`, `_risk_gate` 6775; omega `_stop_perdita` 7819.
- D-028 Stop giornaliero per perdita - mike (`daily_loss_stop` in `run_once`), omega `_stop_perdita` 7819, safe `RK.loss_stop_active` (in `stats.risk`). [P]
- D-029 Interruttore uscite MANUALE/AUTOMATICO per bot (5 forme, §1.7) - `avvio_app.py:173-215`. [UI: pulsante uscite di ogni bot] [P]
- D-030 Reset a MANUALE e bot fermo ad ogni avvio dell'app - `avvio_app.py:113-300` + gemelle (`ferma_al_nuovo_avvio` 60 righe ridondanti).
- D-031 Accensione indipendente di ogni bot (4-ter) - riga di controllo propria per bot/partita.
- D-032 Auto-arming delle partite dal feed con tetto - scalper `giro_auto` 350-569 + `auto_mode.py` 440; tennis `_stato_auto` 910, `auto_mode.py` 270. [UI: interruttore globale] [P]
- D-033 Freno di sistema che impedisce nuove sessioni - scalper `freno_supervisore` 685, `motivo_freno` (session) 150, `risk_semaphore.py`; tennis `guardie_tennis.py` 487.

Comandi dall'app
- D-034 Coda richieste con stato e stale a 10 min - mike `process_requests` 3636 + `fail_stale_processing`; safe 2669/858; omega 5425/314.
- D-035 Approva uscita proposta dall'utente - mike `_request_approva_uscita` 3775; omega `_uscita_del_bot_approvata` 5891; safe 3829; tennis `uscite_proposte.py`. [UI: proposte d'uscita]
- D-036 Annulla ordine su richiesta - mike `_request_cancel` 3820; safe 4046; omega `annulla_ordini_vivi_del_bot` 4826.
- D-037 Cash out / flatten manuale - mike `_request_flatten` 3850; omega `_manual_cashout` 6014; safe `_request_cashout` 3492; tennis `chiusura_manuale.py`. [UI: "Chiudi ora"]
- D-038 Piazzamento manuale dalla UI - omega `_manual_place` 5514; safe `_request_place` 2917, `_request_place_combo` 3252.
- D-039 Marcatore "chiuso dall'utente" e ripresa evento - omega 4579-4690, 4939; safe 2468-2640, `_request_riprendi_evento` 3814. [UI]
- D-040 Richiesta non di questa riga/partita (scarto) - omega 5943, safe 3469, mike 3591 (0,98 fra omega e safe).

Stato, persistenza, ricostruzione
- D-041 Stato per partita e sua serializzazione - mike 464-603; scrittura solo se cambia 6706.
- D-042 Cache di lettura con TTL (eventi, aggregati, feed) - mike `_Cache` 396, `_aggregates_cached` 1233; omega `_Cache` 169, `_aggregati_cached` 367, `_insieme_cached` 336; safe `_agg_recente` 6591.
- D-043 Aggregati del giorno e P&L del giorno operativo - mike 4372-4390, omega `_aggregati_cached` 367, safe `db.aggregates` (`bot_db.py:315`). [UI: P&L oggi]
- D-044 Svuotamento delle cache di processo (test/riavvio) - mike `svuota_le_cache` 436, `azzera_cache_di_processo` 3016; omega 260; safe 11050.
- D-045 Riconciliazione ordini al riavvio - mike `_reconcile_trades` 5713; omega `reconcile_pending` 4337; safe 1117 (scheda C).
- D-046 Residui e posizioni dopo il riavvio - tennis `ResiduiRicordati` `condotta_ordini.py:524`; scalper `prepara_ripresa_media` 916.

Fasi e regolamento (il guscio, non le regole)
- D-047 Ciclo di vita pre-partita -> in gioco -> intervallo -> fine -> regolato: mike stati `engine.py` (§1.8); omega `mission_phase` 866; scalper watcher HT 1734; tennis `lifecycle_worker` 2125.
- D-048 Regolamento e conto reale - mike `_settle_trades` 6403, `_leggi_regolato_conto` 6144; omega `settle_open` 4971; safe 2089 (schede F).
- D-049 Sorveglianza sospensione/mercato chiuso - mike `_sorveglia_sospensione` 3405; omega `_mercato_in_attesa` 1802; scalper `partita_finita` 476; tennis `fine_da_rileggere` 693.

Attivita', stato per la UI, canali
- D-050 Diario attivita' per la UI - (§1.9). [UI: registro attivita' di ogni bot]
- D-051 Publicazione stato sul canale locale (porte 47333/47334/47335/47337/47338, `A_CONNESSIONE_BETFAIR.md:158-162`) - mike `_pubblica_stato` 7279, omega 8753, safe 10607, scalper `PubblicaSessioni` 619, tennis `canale_bot_tennis.py`.
- D-052 Stats per partita e per bot (liability aperta, P&L, tetti, stato scanner) - mike `run_once` stats; omega `_idle_stats` 7836; safe stats `run_once`. [UI]
- D-053 Allarmi "dato fermo" (feed/flusso) con episodio - mike `_avvisa_feed_non_letto` 7144, `_episodio_dato_assente` 1518; scalper `sorveglia_flusso_sessione` 1050; tennis `_sorveglia_flusso_tennis` 2219, `stall_worker` 2280. [UI: alert]
- D-054 Esiti ordini dal canale locale (terminali) - omega `avvia_esiti_ordini` 790, safe `_avvia_esiti_ordini` 10628, mike `installa_conto_canale` 6787.

Processo, salute, arresto
- D-055 Lock di singola istanza - `single_instance.py` 36; omega copia 8563.
- D-056 Segnali di arresto -> arresto ordinato - mike 7391-7413, scalper `scalper_session.py:2276-2300`, omega/safe `arresto_bot.installa_segnali`.
- D-057 Arresto con annullo ordini non abbinati (tetto 10 s) e posizioni dichiarate - mike 7315-7388; omega/safe `arresto_bot.py`; scalper 667/792; tennis 2074.
- D-058 Orfane: sessione con battito fermo marcata errore - scalper `marca_orfana` 657, `ORPHAN_HEARTBEAT_S`; tennis 3048.
- D-059 Riavvio del servizio caduto - tennis `_main` 1127-1180 (10 s); scalper crash `_handle_flumine_crash` 824; watchdog (`NON_BOT`, `registro_bot.py:410`).
- D-060 Timeout PostgREST del profilo bot - mike 7433, omega 8815, safe 10881 (`_usa_timeout_bot`).
- D-061 Saldo conto su evento - `omega_market.attiva_saldo_su_evento(nome)` chiamato da mike 7437, omega 8821, safe 10914.

Registro e banco
- D-062 Registro dei bot in produzione (11 voci) - `registro_bot.py:217-399` (mike 219, omega 244, safe_base 256, safe_esatto 271, safe_punta 286, safe_tennis 301, scalper_calcio 314, tennis_scalper 348, tennis_pro 361, tennis_flb 374, tennis_swing 387).
- D-063 Elenco dei processi NON bot - `registro_bot.py:410-419`.
- D-064 Certificabile = replay + controlli - `BotRegistrato.certificabile` 71-130.
- D-065 Catalogo scenari e parametri per "Applica bot" - `applica_bot.py:282-365` (`scenari_del_bot`, `catalogo_del_bot`), `varianti_bot.voce`/`valida` 49-140. [UI: pannello Applica bot] [P]
- D-066 Accensione simulata al tempo `dal_ms` - `varianti_bot.Accensione` 178-209.
- D-067 Cartelle delle registrazioni calcio/tennis - `registro_bot._cartella_calcio` 42, `_cartella_tennis` 48; `applica_bot.risolvi_cartella_tennis` 466.
- D-068 Specchio ordini del banco (stessa riga di `betfair_live_orders`) - `varianti_bot.SpecchioOrdini` 329-455.
- D-069 Test di contratto: bot in produzione non registrato = rosso - `Betfair/stream/tests/test_registro_bot_2026_09_16.py` (citato da `registro_bot.py:22-26`).
- D-070 Esito conto regolato dal raw e P&L del banco - `applica_bot.conto_regolato` 602, `esiti_dal_raw` 541.
- D-071 CLI di laboratorio fail-closed dello scalper - `run_scalper_live.py:44-64`, `main` 202.
- D-072 Variante "tennis safe" dentro Safe - `engine.py:804` (`build_tennis_ctx_from_scan`), `evaluate_tennis` 1567.

---------------------------------------------------------------------------------------------------

## 3. DIFETTI STRUTTURALI

1. **Ruolo realizzato 4-5 volte** (reperto 1, §1.3): 284 righe di copie letterali ma ~9.500 righe di scheletro con la stessa funzione e codice diverso. Per cambiare una regola
   dello scheletro (es. «dopo il riavvio le uscite sono MANUALI») si toccano cinque punti: `avvio_app.py:173-215` conosce per NOME i bot (`mike`, `scalper`, `omega`, `safe`; il tennis ha
   un percorso suo `tennis_bot_service.py:958`). Un bot nuovo obbliga a modificare `avvio_app.py`.
2. **Cinque modelli di esecuzione diversi** (§1.1): polling del DB (Mike, Omega, Safe) contro tick dello stream (scalper, tennis); 2 processi per Safe, N+1 per lo scalper, 2 per il tennis. Il
   requisito del millisecondo (§9.3 del piano) non e' rispettato dai tre bot a polling (§1.5) e oggi `run_once` NON puo' girare su un tick.
3. **Tre politiche diverse per il controllo illeggibile** (D-022): Mike salta TUTTO il giro (`return {"skipped": "control_unreadable"}`: nessuna gestione delle posizioni aperte in quel giro); Omega gestisce le
   posizioni con l'ultimo controllo fino a 300 s; Safe entra in protezione ("niente nuovi ingressi"). E' una divergenza di sicurezza: da portare all'utente (Decisione 1).
4. **Copie del guscio che divergono**: arresto di Mike (`service.py:7315-7388`, 74 righe) vs `arresto_bot.py` condiviso da Omega e Safe; lock di Omega (`omega_service.py:8563`) vs `single_instance.py`;
   `_RealMarket` di Mike (131-302) che delega a `omega_market` (Mike importa Omega: `service.py:146-149`, e Safe importa Omega: `bot_service.py:302 _omega_service`): il bot "indipendente" (4-ter) dipende
   da codice di un altro bot.
5. **Parametri e controllo in 5 forme**: chiave dell'interruttore uscite in 5 forme (§1.7); `control.mode` globale vs per strategia vs per sessione; le chiavi delle `stats` non coincidono
   (Mike ~40, Omega e Safe set diversi): ogni pannello UI e modello `frontend` per bot rilegge a modo suo (J).
6. **Traffico al cloud nel ciclo**: da `07_MISURE_OGGI.md` §4.2 (08/10): safe-bot 232,3/min, mike 48,0, scalper-service 52,5, tennis-bot-service 43,0, omega 12,2 = **388,0 richieste/min** dei servizi dei bot
   su 707,5/min totali dell'app (+ runner-tennis 27,2). Sono quasi tutte letture della riga di controllo/richieste/trade (es. `scalper_control` 17,5/min, `safe_strategy_trades` 82,0/min, `tennis_bot_control` 21,5/min):
   stato condiviso copiato su DB e riletto da tutti. Mike e' sceso da 256 a 48/min fra 04/10 e 08/10 per ragione NON verificata nel codice (`07_MISURE_OGGI.md:226`).
7. **Stato in RAM perso al riavvio** dove la ricostruzione e' parziale: tracker del motore Safe e `_OPPS_STATE` (catalogo §7 n.19 gia' visto in `pre_ko`); `_CACHE_EVENTI` Mike si ricarica dal DB ma entro `events_reload_s`.
8. **Registro con granularita' diversa dall'esecuzione**: `registro_bot.py:314` ha UNA voce `scalper_calcio` ma la sessione ospita 4 strategie (maker, sniper `scalper_session.py:1525`, theta 1620, media under 1673);
   gli scenari `sniper`/`media-under` esistono in `scalper/tools/replay_registrazioni.py:135-146`. E 5 adattatori di replay (14.114 righe: mike 2.370, omega 2.593, safe 2.092, scalper 3.803, tennis 1.679 + safe_tennis 1.577)
   replicano il servizio nel banco (componente H).
9. **Unita' di decisione incompatibili con una firma sola** (§4): vedi la verifica dettagliata.

---------------------------------------------------------------------------------------------------

## 4. DOMANI

### 4.1 Verifica della firma del brief §4 `osserva(book, stato_partita, orologio) -> decisioni`

**Non regge come scritta.** Sei fatti letti nel codice:

1. **Decide per partita con STATO PROPRIO e parametri vivi**, non solo sull'osservazione: `decide(ctx, snap, params)` di Mike (`mike/engine.py:3089`) riceve `ctx` (macchina a stati, gambe, ref) e `params` riletti a ogni
   giro; lo scalper rilegge `params_vivi` ogni 5 s (`scalper_session.py:2090`). Servono `stato` e `parametri` come argomenti e `stato` nuovo come ritorno.
2. **Mike usa il dossier pre-partita e l'atlante** dentro lo `Snapshot` (`p_under35_cal`, `hazard`, `model_probs`, `p_total_model/emp`: `engine.py:180-238`), costruiti da `D.build_prematch` (`service.py:4159`) e `D.load_atlas()`:
   dati del cloud entrati all'armamento, non nel tick. -> argomento `prematch` fornito dal runtime all'armamento e rinfrescato con TTL.
3. **Omega usa le cache empiriche** (`_empirical_table` `omega_service.py:1350`, `_MINUTE_CACHE` 1316, TTL 6 h) tramite `db` DENTRO la selezione (`_model_select(db=...)` 1397): non e' una funzione pura di (book, partita, orologio).
   Le tabelle sono dati di contorno: vanno iniettate come `FornitoreDati` (cache locale in sola lettura), mai lette dal DB nel percorso della decisione.
4. **Safe valuta TUTTE le partite insieme e conserva stato fra i giri**: `SafeEngine.evaluate(rows)` (`engine.py:2112`) fa `_ingest` sui tracker, `reconcile_signals` fra candidati di eventi diversi e restituisce segnali ATTIVI; le uscite sono un secondo motore
   (`process_exits` `bot_service.py:4254`), le opportunita'/anomalie/combo altri tre (`process_opportunities` 7726, `process_anomalies` 9387, `_proponi_combo` 8560). -> serve un hook `fine_giro(tutti_gli_stati)` oltre a `osserva` per partita.
5. **Lo scalper e il tennis decidono a ogni TICK dello stream** dentro flumine (`process_market_book` `scalper_bot.py:817`, tennis `tennis_*_bot.py`) e **non RESTITUISCONO decisioni**: piazzano/annullano da dentro il callback
   (verificato per il tennis `tennis_runner.py:893-925` «i bot tennis gateano ogni `market.place_order`»; per lo scalper non ho riletto riga per riga). Le loro strategie NON si toccano: per loro il contratto e' un
   **ospite** (`OspiteFlumine`) che offre ciclo di vita, params vivi, stato e diario, non una funzione pura.
6. **Gli eventi dell'ordine arrivano a parte**: fill parziali, rifiuti, bet delay, scadenze non sono nel book. Mike li chiude con `_reconcile_trades` 5713 / `_mark_trade_cancelled` 5916; flumine li chiama come `process_orders`;
   Omega `reconcile_pending` 4337; Safe 1117. -> callback `su_esito_ordine`.
7. **Comandi dell'utente e fasi sono eventi**, non osservazioni: `approva_uscita`, `cancel`, `flatten` (§1.6) e il passaggio pre-partita/in gioco/intervallo/fine.

### 4.2 Contratto proposto (Python tipato; due livelli)

Livello 1 (OBBLIGATORIO per ogni bot): ciclo di vita, parametri, stato, diario, uscite. Livello 2 (due varianti): decisore puro `Decisore` (Mike, Omega, Safe) oppure `OspiteFlumine` (scalper, tennis).

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Mapping, Protocol, Sequence

UsciteModo = Literal["MANUALE", "AUTOMATICO"]          # cond. 4-bis: di serie e dopo ogni riavvio MANUALE
Modo = Literal["paper", "live"]
Sport = Literal["calcio", "tennis"]

class Fase(str, Enum):                                 # gli eventi del ciclo di vita (uniti da tutti i bot)
    ARMATO = "armato"; PRE_PARTITA = "pre_partita"; IN_GIOCO = "in_gioco"; INTERVALLO = "intervallo"
    SOSPESO = "sospeso"; FINE_GIOCO = "fine_gioco"; MERCATO_CHIUSO = "mercato_chiuso"; REGOLATO = "regolato"
    DATO_MANCANTE = "dato_mancante"

@dataclass(frozen=True)
class Orologio:                                        # un solo orologio per tutti (componente A)
    mono_ms: int                                       # monotono locale
    publish_ms: int | None                             # publish time Betfair del book (None = non da stream)

@dataclass(frozen=True)
class Libro:                                           # il MarketBook di un mercato, SENZA copie (vista su flumine)
    market_id: str; tipo: str; stato: str; bet_delay: int
    selezioni: Mapping[int, Any]

@dataclass(frozen=True)
class Quadro:                                          # lo "stato_partita" del brief, esteso con eta' e fonte
    event_id: str; fase: Fase; minuto: int | None; punteggio: tuple[int, int] | None
    rossi: tuple[int, int] | None; in_gioco: bool
    eta_dato_ms: int; fonte_prezzi: Literal["stream", "feed", "rest_ripiego"]

@dataclass(frozen=True)
class Parametri:                                       # uno schema SOLO, generato dal catalogo del bot
    modo: Modo; uscite: UsciteModo; valori: Mapping[str, Any]      # i valori sono il catalogo `parametri_modificabili` del registro

@dataclass(frozen=True)
class Intento:                                         # cio' che il bot vuole; il runtime lo esegue dalla porta unica (C)
    tipo: Literal["piazza", "annulla", "chiudi", "proponi_uscita", "diario", "allarme"]
    dati: Mapping[str, Any]; ref: str | None = None

@dataclass(frozen=True)
class Esito:
    stato: Any                                         # nuovo stato serializzabile del bot per quella partita
    intenti: Sequence[Intento] = field(default_factory=tuple)

class Prematch(Protocol):                              # dati del cloud, in sola lettura, cache locale con TTL
    def dossier(self, event_id: str) -> Mapping[str, Any] | None: ...
    def tabella_empirica(self, chiave: str) -> Any | None: ...

class Plugin(Protocol):                                # livello 1: identico per tutti i bot
    nome: str; sport: Sport
    def catalogo_parametri(self) -> Sequence[Mapping[str, Any]]: ...          # = parametri_modificabili del registro
    def uscite_di_serie(self) -> UsciteModo: ...                              # MANUALE
    def chiave_uscite(self) -> str: ...                                        # mappa verso la chiave nativa (§1.7)
    def arma(self, event_id: str, prematch: Prematch, stato: Any | None) -> Any: ...   # nuovo o RICOSTRUITO dal salvato
    def su_fase(self, stato: Any, fase: Fase, orologio: Orologio) -> Esito: ...
    def su_comando(self, stato: Any, comando: Mapping[str, Any], p: Parametri) -> Esito: ...  # approva_uscita, cancel, flatten
    def su_esito_ordine(self, stato: Any, ordine: Mapping[str, Any], orologio: Orologio) -> Esito: ...  # fill/parziale/rifiuto
    def cadenza(self) -> "Cadenza": ...

class Decisore(Plugin, Protocol):                      # livello 2a: Mike, Omega, Safe
    def osserva(self, stato: Any, libri: Mapping[str, Libro], quadro: Quadro,
                orologio: Orologio, p: Parametri, prematch: Prematch) -> Esito: ...   # firma del brief + stato/parametri/prematch
    def fine_giro(self, stati: Mapping[str, Any], p: Parametri, orologio: Orologio) -> Mapping[str, Esito]: ...  # Safe: reconcile_signals, tetti

class OspiteFlumine(Plugin, Protocol):                 # livello 2b: scalper, sniper, theta, media under, 4 bot tennis
    def strategie(self, event_id: str, p: Parametri) -> Sequence[Any]: ...   # le classi flumine ESISTENTI, invariate
    def applica_parametri_vivi(self, strategie: Sequence[Any], p: Parametri) -> None: ...  # es. applica_uscite_automatiche

@dataclass(frozen=True)
class Cadenza:
    modo: Literal["tick", "giro"]; periodo_s: float; riposo_s: float
    sveglia_su_prezzo: bool; minimo_s: float           # = _MIN_GIRO_S 0.25 di Safe
```

**Runtime unico** (una sola istanza di codice, il "ciclo di Mike/Omega/Safe" scritto UNA volta; modulo `runtime/`): `Controllo` (legge/scrive la riga con cache e fallback, UNA politica per «controllo illeggibile»),
`Comandi` (coda con stale), `Cicli` (giro/tick + sveglia + giro veloce opzionale), `Persistenza` (stato per partita, scrive solo se cambia, ricostruzione al riavvio),
`Diario` (attivita' + canale), `Battito` (stats con le STESSE chiavi), `Arresto` (segnali, annullo con tetto, posizioni dichiarate), `Avvio` (Guardia + reset uscite MANUALI), `Lock`, `Supervisore` (processi/ospiti),
`Registro` (= `registro_bot.py`, esteso con `plugin` e `cartella`).

### 4.3 Dove vive ogni funzionalita' domani

| Funzionalita' | Domani |
|---|---|
| D-001..D-013 (cicli, cadenza, sveglia, giro veloce, battito, keepalive, fasi sempre attive) | `runtime/cicli.py`, `runtime/battito.py`; il plugin dichiara solo `Cadenza` |
| D-014..D-020 (feed, eta', ripiego, punteggio, dossier, empiriche) | componente A (nucleo Betfair, book in-process) + `Prematch` (cache locale del cloud); il plugin non legge piu' il DB nel percorso critico |
| D-021..D-033 (controllo, parametri, modo, tetti, uscite, avvio, auto-arming) | `runtime/controllo.py`; `Parametri.uscite` unico con mappa verso la chiave nativa nel plugin (`chiave_uscite`); `selettore_partite` per auto-mode (le regole di `auto_mode.py` restano nella cartella del bot) |
| D-034..D-040 (comandi) | `runtime/comandi.py` smista a `Plugin.su_comando`; l'esecuzione degli ordini resta nella porta unica (C) |
| D-041..D-046 (stato, cache, riconciliazione) | `runtime/persistenza.py` + componente C (riconciliazione) |
| D-047..D-049 (fasi, regolamento) | `Fase` nel contratto; regolamento in F |
| D-050..D-054 (diario, canali, stats, allarmi) | `runtime/diario.py`, `runtime/battito.py` con le stesse chiavi per tutti |
| D-055..D-061 (lock, arresto, orfane, riavvio) | `runtime/{lock,arresto,supervisore}.py` |
| D-062..D-070 (registro, banco) | `Registro` unico; `applica_bot`/`certifica` leggono il Plugin; adattatore del banco UNO (H) |

### 4.4 Stima delle righe (metodo esplicito)

Oggi (misurato, §1.2): **S = 10.152 righe, S+M = 11.582** (7 file). Domani = runtime scritto UNA volta + un adattatore piccolo per plugin. Il runtime unico e' stimato per ruolo,
prendendo come base l'implementazione piu' ricca oggi esistente per quel ruolo:

| Blocco del runtime unico | Base di calcolo (righe oggi) | Stima domani |
|---|---|---:|
| Cicli, cadenza, sveglia, giro veloce | Safe `9754-10028` (275) + `10662-10838` (177) = 452 | 450 |
| Controllo, parametri, modo, uscite | Safe `319-700` (~380), ora dichiarativo dal catalogo gia' esistente nel registro | 250 |
| Comandi e marcatori utente | Safe `2468-2768` (~300) + Mike `process_requests` 102 + Omega `process_manual` 37 | 350 |
| Canali, client del feed, esiti | Safe `9512-9753` (~242) | 250 |
| Battito, stats, pubblicazione | Mike stats ~60 + Omega `_idle_stats` 70 + 3 `_pubblica_stato` ~45 | 200 |
| Avvio, arresto, lock, segnali | Mike `arresto_con_ordini` 74 + `arresto_bot.py` 198 + `avvio_app.py` 336 (gia' condiviso, resta) | 250 |
| Persistenza stato e ricostruzione | Mike 464-603 + 6670-6786 ~ 256 | 260 |
| Ospite flumine (sessione scalper + hosting tennis) | scalper_session S+M 1.716 + tennis_run S+M 1.944 = 3.660; ruoli gemelli: flat/arresto (`_strategy_flat` 277 / `_strategy_is_flat` 1183), flusso fermo (1050 / 2219), freno, armamento a caldo | 1.000 |
| Supervisore processi + auto-arming | scalper_svc 856 + tennis_svc 969 = 1.825 | 500 |
| **Runtime unico** | | **~3.510** |
| Adattatori dei plugin (7 cartelle: mike, omega, safe, scalper, tennis + 2 varianti) ~150-400 ciascuno | catalogo parametri, `chiave_uscite`, dossier/`Prematch`, codec dello stato (Mike ~260), preset dei 4 bot tennis | ~1.250 |
| **Totale domani** | | **~4.760** |

Confronto: 4.760 contro **S+M = 11.582 -> -59%**; contro S = 10.152 -> -53%. **Non raggiunge il -80% sul solo scheletro** e non lo prometto: il -80% e' possibile solo sommando
i tagli delle altre schede (porta ordini/riconciliazione C: `reconcile_pending` ha 3 copie di 119/222/101 righe; regolamento F; DB G: i 4 moduli `*_db` = 3.687 righe con le sole 3 funzioni di controllo/log
triplicate; banco H: 14.114 righe di adattatori). Stima prudente con banda: **-50% (cautelativa, flumine non unificato) ... -65% (hosting unico calcio+tennis e DB per bot sostituiti)**.
Quello che resta e' strategia: R = 19.150 righe NON toccate qui (la logica di trading e' intoccabile).

### 4.5 Gia' in una libreria matura e oggi riscritto

- **flumine** gestisce gia' ciclo `process_market_book`/`process_orders`, blotter, simulazione paper con bet delay: lo scalper e il tennis lo usano, Mike/Omega/Safe NO (riscrivono polling, riconciliazione ordini e fill di
  paper a mano: `_segui_ordini_paper_su_runner` `mike/service.py:1694-1922` 229 righe, `poll_flumine_pending` omega 4108, `poll_flumine` safe 826) - schede C/E.
- **flumine `BackgroundWorker`** per i worker periodici: i worker del tennis lo usano (`bot_control_worker`, `lifecycle_worker`...); lo scalper usa thread a mano (`scalper_session.py:1845`, watcher 1734-1915).
- **betfairlightweight**: keep-alive e login (`omega_service.py:8541`, `tennis_runner.py:1583`, `scalper_session.mantieni_sessione` 805) sono tre copie di una chiamata di libreria.

### 4.6 Criterio §9.1 «per sostituire un bot»

- **OGGI**, per sostituire Mike (stesso discorso per gli altri): `Betfair/mike/{service.py 7.551, engine.py 5.359, db.py 693, config.py 491, feed.py 583, dossier.py 411, porta_ordini.py, regolato_conto.py, certificazione.py, tools/replay_registrazioni.py 2.370}` +
  `registro_bot.py:219-243` (voce) + `avvio_app.py:173-215` (ramo `mike`) + il launcher in `desktop/main.js` (citato da `registro_bot.py:27-30`: i moduli di produzione sono quelli che lancia `main.js`) + le 5 tabelle SQL del bot
  (`mike_control/events/trades/activity/requests`, `mike/db.py:32-37`) in `migrations/` + il modello frontend del bot (J) + la fotografia delle porte (`A_CONNESSIONE_BETFAIR.md:158-162`).
  **Almeno 6 file/aree FUORI dalla cartella del bot** (registro, avvio_app, main.js, migrazioni, frontend, banco).
- **DOMANI**: solo la cartella `bots/<nome>/` (plugin `Decisore`/`OspiteFlumine`, `COSA_FA.md`, catalogo parametri, replay del banco) e i suoi test di contratto (`test_plugin_contratto.py` generico che istanzia il plugin
  e verifica: uscite di serie MANUALI, stato ricostruibile, parametri nel catalogo, fasi gestite). Registro, avvio, menu del banco e pannello UI si derivano dal Plugin.

---------------------------------------------------------------------------------------------------

## 5. PARITA'

Il runtime non cambia le decisioni: la parita' si dimostra a tre livelli.

1. **Decisioni e ordini (banco, componente H)**: `python -m Betfair.stream.backtest.certifica <bot>` con il Plugin al posto del servizio, sulle stesse registrazioni (`registrazioni_banco/`, calcio `config_stream.DATA_DIR`,
   tennis `TENNIS_RECORD_DIR`) e gli stessi scenari (`SCENARI_DESCRITTI` dei 6 adattatori; per lo scalper anche `sniper`, `sniper-paper`, `sniper-uscite-auto`, `media-under`...: `scalper/tools/replay_registrazioni.py:135-146`).
   Devono coincidere numero per numero: decisioni, ordini, importi, istanti, P&L. Riferimenti da CONGELARE prima di iniziare: i referti del 02/10 gia' presenti in `AUDIT_2026-10-02/replay/`
   (`mike_tutti_MASTER_FINALE.txt`, `omega_base_MASTER_parita.txt`, `safe_base_entrambi_MASTER_d56bb3b.txt`; non riletti da me in questa scheda: da riverificare dal coordinatore prima del congelamento).
2. **Scheletro (nuovo, questa scheda)**: modalita' OMBRA, vedi §6; confronto automatico per ogni giro di: riga di controllo scritta (stesso `status`, `heartbeat_at` entro tolleranza), **insieme di chiavi di `stats`**
   (stesso set e tipi), sequenza dei `kind` del diario, esito di `ferma_al_nuovo_avvio` (stato `stopped`, `mode` paper, uscite MANUALI: test esistenti `Betfair/omega/test_omega_uscite_manuali_al_riavvio_2026_09_28.py`,
   `Betfair/stream/tennis_live/tests/test_tennis_uscite_manuali_al_riavvio_2026_09_28.py`), arresto (annullati/non_annullati/posizioni di `arresto_con_ordini` 7315 e `arresto_bot`).
3. **Suite esistenti da NON rompere**: `Betfair/omega/test_omega_service.py` (1.274 righe), `Betfair/stream/tennis_live/tests/test_tennis_bot_service_lock.py`, test di contratto del registro
   (`test_registro_bot_2026_09_16.py`), `python -m pytest Betfair/ -q -p no:cacheprovider`, `npx vitest run`, `tsc` a 0 errori.

Voci di `PROCESSO_STANDARD_BOT.md` coperte da questa scheda: **§6.3** (servizio intero a cadenza reale: il banco deve far girare il runtime vero, non il solo `decide`), **§6.4** (ciclo di vita dell'ordine: `su_esito_ordine`,
parziali e bet delay), **§6.5** (persistenza e UI: stats e diario con le stesse chiavi), **§6.6** (concorrenza: lock, indipendenza 4-ter), **§6.7** (scenari + falsificazione), **§6.8** (referto riproducibile), **§6.9** (replay veloci:
il Plugin non deve rallentare il banco). Catalogo §7: **n.19** (stato in RAM perso al riavvio: `arma(stato salvato)`), **n.20** (battito vivo != coda utilizzabile), **n.22** (bot che riparte da solo), **n.23** (stats riscritte
per intero cancellano l'impronta di avvio: `_GUARDIA_AVVIO.timbra`), **n.25** (modalita' ereditata), **n.21** (tetto che somma paper e live), **n.27/n.29/n.30/n.35** (finti identici al vero, test a vuoto, mutazioni, test mai visto rosso),
**n.34** (fase di protezione dopo la riconciliazione: `_fasi_di_gestione` deve restare PRIMA dell'apertura), **n.37** (cache di modulo fra scenari: `svuota_le_cache`/`azzera_cache_di_processo` diventano `Runtime.reset()`).
Falsificazione obbligatoria: (a) togliere il reset MANUALE in `Avvio` -> deve diventare rosso il test «dopo il riavvio uscite MANUALI»; (b) far restituire al plugin finto uno stato non ricostruibile -> rosso il test di riavvio;
(c) togliere il controllo `_AO.richiesto()` dal ciclo -> rosso il test «l'arresto fa uscire davvero il ciclo» (esiste per mike/omega/safe, cantiere K2).

---------------------------------------------------------------------------------------------------

## 6. MIGRAZIONE

Principio: un bot alla volta, interruttore per bot, periodo OMBRA con confronto automatico, taglio del vecchio solo dopo parita'.

0. **Congelare** i referti di riferimento (§5.1) e il set di chiavi `stats`/`kind` di oggi (script d'impronta, come `AUDIT_2026-09-25/impronta_transizioni_*.json` ma per lo scheletro).
1. **Scrivere il contratto e il test generico** (`runtime/contratto.py`, `test_plugin_contratto.py`) con un plugin finto a chiavi/tipi identici al vero (catalogo §7 n.27). Nessun bot toccato.
2. **Pilota Omega** (S piu' piccolo fra i polling: 1.763; traffico minimo 12,2 richieste/min; nessun giro veloce, nessuna variante): Plugin `Decisore` che avvolge `_scan_event_legs`/`_model_select` SENZA cambiarli.
   Interruttore `.env` per bot (modello gia' usato: `SAFE_BOT_LEGGE_CANALE`, `OMEGA_LEGGE_CANALE` `omega_service.py:564`): `RUNTIME_OMEGA=vecchio|ombra|nuovo`.
3. **Ombra** (2-3 giorni di partite reali, paper): il vecchio opera; il nuovo gira in sola lettura e confronta (§5.2). Zero scritture di ordini dal nuovo.
4. **Mike** (decide gia' pura: adattatore sottile, Plugin `Decisore` su `E.decide`; l'arresto proprio di Mike confluisce in `Arresto` comune: unica divergenza da dichiarare, Decisione 1).
5. **Safe** (5 varianti; giro veloce diventa capacita' del runtime ma resta spento per Mike/Omega finche' l'utente non decide: Decisione 5).
6. **Scalper e tennis** per ultimi: `OspiteFlumine` su `scalper_session.py` e `tennis_runner.py`; dipende dal nucleo Betfair (A) e dalla porta ordini (C). Le classi flumine non cambiano.
7. **Taglio**: rimuovere i vecchi `_ciclo_persistente`/`main`/lock/arresto copie e il ramo per nome di `avvio_app.uscite_a_manuali`.
Rischi: (a) il ciclo unico altera la cadenza di un bot (soglie di `fretta`): misurare con `07_MISURE_OGGI.md` §4.2 prima/dopo; (b) differenza nella politica del controllo illeggibile (Decisione 1);
(c) Safe/Mike importano Omega (`_RealMarket`): sciogliere prima l'accoppiamento; (d) i bot tennis condividono il processo: un errore del runtime fermerebbe 4 bot (4-ter): mantenere un'ospite per bot.
Ritorno indietro: l'interruttore per bot torna a `vecchio` senza toccare DB ne' tabelle (il nuovo non cambia lo schema; se i dati vanno in un archivio locale, e' G).

---------------------------------------------------------------------------------------------------

## 7. MISURE

| Misura | Oggi (fonte) | Obiettivo domani | Strumento |
|---|---|---|---|
| Righe scheletro (7 file) | S 10.152 / S+M 11.582 (`D_scheletro_righe.py misura`) | ~4.760 (§4.4) | stesso script, rieseguibile |
| Copie letterali dello scheletro | ~284 (`D_gemelle_servizi.py gemelle`) | 0 | stesso |
| Richieste al DB dei servizi bot | **388,0/min** = safe-bot 232,3 + scalper 52,5 + mike 48,0 + tennis-bot 43,0 + omega 12,2 (`07_MISURE_OGGI.md:208-218`, 08/10; totale app 707,5/min) | stato vivo e comandi sul canale/archivio locale, scritture al cloud via postino a lotti: obiettivo <= 60/min complessivi (obiettivo, non misura) | `strumenti/misure/` + log PostgREST |
| Latenza messaggio -> decisione dei bot a polling | giro di Mike >= 1,0 s (`interval = max(1.0, decide_min_interval_ms/1000*2)`), Omega 20 s di riserva / `poll_interval_s`, Safe 2,0 s (`_un_giro`) | decisione sul tick per chi lo richiede (A); cadenza dichiarata dal plugin | non misurata nel percorso bot: manca lo strumento «messaggio -> `decide`»; da scrivere (vedi `07_MISURE_OGGI.md` §2.4) |
| CPU/RAM dei processi bot | NON misurabile oggi (app spenta, `07_MISURE_OGGI.md` §5.1) | processi: da 8+ a 3-4 (calcio-ospite, tennis-ospite, scanner, supervisore) | `m05b_campiona_processi.ps1` |
| Tempo del banco per la certificazione completa | tetto 10 min (standard 7) | invariato | `certifica` |
| Righe da toccare per sostituire un bot | >= 6 aree fuori cartella (§4.6) | 1 cartella | contratto |

---------------------------------------------------------------------------------------------------

## DECISIONI PER L'UTENTE

1. **Controllo illeggibile**: oggi Mike salta TUTTO il giro (nessuna gestione delle posizioni aperte), Omega continua a gestire con l'ultimo controllo fino a 300 s, Safe entra in protezione. Quale politica unica? Uniformare Mike
   cambia un comportamento (e' una divergenza di sicurezza, non una regola di trading: la porto qui per te).
2. **Granularita' di paper/live**: oggi globale (Mike, Omega), per strategia (Safe), per sessione (scalper), per bot (tennis). Il contratto propone `Modo` per (bot, variante, partita); non cambio nulla senza tuo ordine.
3. **Registro dello scalper**: una voce `scalper_calcio` o quattro (maker, sniper, theta, media under)? Oggi il banco ha scenari separati ma una voce sola.
4. **Bot flumine (scalper, tennis)**: confermi che restano «ospitati» come sono (ordini piazzati dentro la strategia) e NON riscritti per restituire intenti? Il piano lo assume: riscriverli sarebbe un intervento sulla strategia.
5. **Giro veloce di Safe** (decisione sul prezzo, `bot_service.py:9912`): estenderlo a Mike e Omega e' un cambio di temporizzazione delle loro decisioni. Lo faccio solo se lo ordini.

## COSA HO VERIFICATO DI PERSONA / COSA NON HO POTUTO VERIFICARE

Verificato leggendo il codice (grep/sed): i cicli `run_once`/`main`/`_ciclo_persistente`/`_un_giro` di Mike, Omega, Safe, il supervisore scalper, il ponte tennis; `registro_bot.py` quasi per intero;
la mappa `avvio_app.uscite_a_manuali`; la firma di `engine.decide` e `Snapshot` di Mike; `SafeEngine.evaluate`; l'elenco delle `def` di tutti i file del perimetro (indici con riga). Rieseguiti: `D_gemelle_servizi.py gemelle`
(57 nomi omonimi) e `D_scheletro_righe.py misura/elenca/db`, che hanno prodotto i numeri di §1.2-§1.3.
**Non verificato**: (1) la classificazione S/M/R e' un giudizio per nome di funzione (rieseguibile e correggibile in `D_scheletro_righe.py`); la stima del "dopo" (§4.4) e' una stima per ruolo, non un prototipo;
(2) le righe `~` indicate con tilde (battito Mike 4347-4364, stats Mike ~4285-4343, `_un_giro` interni, `scalper_service.py:~970`) sono approssimate dall'indice delle def, non lette riga per riga;
(3) i **chiamanti in entrata** dei servizi (chi importa `omega_service`, ecc.) non sono stati misurati con `grep -rn` in questa scheda: vedi `00_INVENTARIO.md` / grafo import `strumenti/inventario/uscite/s02_*`;
(4) non ho riletto `scalper_bot.py`/`sniper_bot.py` per confermare che piazzino ordini dentro `process_market_book` (verificato solo per il tennis nella docstring `tennis_runner.py:893-925`);
(5) il perche' del calo del traffico di Mike (256 -> 48/min) resta non verificato (anche in `07_MISURE_OGGI.md:226`);
(6) le righe `tabelle SQL` degli altri bot oltre alle 5 di Mike (`mike/db.py:32-37`) sono desunte dai nomi nei file, non dalle migrazioni (scheda G);
(7) non ho eseguito alcun servizio, replay o test (vincolo del brief); i referti del 02/10 sono citati per nome, non riletti.
