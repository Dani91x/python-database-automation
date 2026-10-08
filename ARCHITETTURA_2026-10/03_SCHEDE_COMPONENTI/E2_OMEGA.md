# SCHEDA E2 - BOT OMEGA (CALCIO) (prefisso `E2-`)

Perimetro (righe da `wc -l` sui file tracciati, `git ls-files`; 08/10/2026; autore: delegato Sonnet):
- **Codice di produzione Omega** (i 12 moduli dichiarati in `Betfair/stream/backtest/registro_bot.py:156-162`): `omega_service.py` 8.936 · `omega_market.py` 1.794 ·
  `omega_engine.py` 1.331 · `omega_v3.py` 1.248 · `omega_proposte.py` 1.235 · `omega_model.py` 1.182 · `omega_db.py` 1.081 · `omega_config.py` 463 ·
  `omega_advisor.py` 400 · `omega_empirical.py` 249 · `porta_ordini.py` 237 · `tools/misura_k.py` 499 = **18.655 righe**. Elenco completo `git ls-files Betfair/omega`
  senza test/tools/data/md: 21.002 righe (in piu': `certificazione.py` 2.160, `liquidity_probe.py` 402, `omega_validate.py` 183, `conftest.py` 89, `__init__.py` 12).
- **Banco di Omega**: `Betfair/omega/certificazione.py` 2.160 (controlli di condotta) + `Betfair/omega/tools/replay_registrazioni.py` 2.593 (adattatore del replay);
  tutta `Betfair/omega/tools/` = 11.136 righe (`git ls-files Betfair/omega/tools | xargs wc -l`: ricerca e misure, non produzione).
- **Test dentro la cartella**: 39 `test_*.py` fuori da `tests/` (16.498 righe) + 35 file in `tests/` (10.551 righe) = 27.049 righe, ~1.300 funzioni `test_`
  (`grep -c "^def test_\|^    def test_"`). **Fuori perimetro del codice** (sono test, esclusi dalle stime).
- **Frontend**: `frontend/src/lib/{omega 1.655, omegaMatches 350, omegaMissions 319, omegaProposte 369}.ts` · `pages/Omega.tsx` 912 ·
  `components/omega/{ManualPanel 644, MatchTradesTable 709, MissionCard 723, MissionPanel 946, OmegaParamsSheet 116, PartiteChiuseDallUtente 124}.tsx` ·
  `components/controlroom/SchedaChiusuraOmega.tsx` 326 · `anteprima/{omegaFinto 213, omegaMissioniFinto 93}.ts` = **7.499 righe** non-test
  (`git ls-files frontend/src | grep -i omega | grep -v "test\.\|snapshot\|fixtures\|golden" | xargs cat | wc -l`) + 5.432 righe di test. Piu' la parte di Omega dentro
  moduli comuni (`lib/interruttori.ts`, `lib/controlRoom.ts`, `lib/dailyHistory.ts`, `components/controlroom/PannelloBot.tsx`, `lib/replayBotCatalogo.ts` 11.099): non conteggiate.
- **Migrazioni SQL**: 20 file `migrations/omega_*.sql` (`git ls-files | grep omega`).
- **Documenti**: `Betfair/omega/COSTITUZIONE_OMEGA.md` (2.109 righe, §1 invarianti I1-I8, §21 Any Other) - letta per le regole; `AUDIT_2026-10-07/OMEGA_APERTURA_35760084.md` (383).

Abbreviazioni in tutta la scheda: **OS** = `Betfair/omega/omega_service.py`; **OV3** = `omega_v3.py`; **OE** = `omega_engine.py`; **OM** = `omega_model.py`; **OP** = `omega_proposte.py`;
**OC** = `omega_config.py`; **ODB** = `omega_db.py`; **OMK** = `omega_market.py`; **OEMP** = `omega_empirical.py`; **OAD** = `omega_advisor.py`; **OPO** = `porta_ordini.py` (tutti sotto `Betfair/omega/`);
**RR** = `Betfair/omega/tools/replay_registrazioni.py`; **TS** = `frontend/src/lib/omega.ts`.

Fonti gia' pronte usate e NON rifatte: scheda D (`D_RUNTIME_BOT_CONTRATTO.md`: scheletro, contratto `Plugin/Decisore`, righe S di Omega 1.763), scheda C (`C_PORTA_ORDINI.md`: S1-S4, R5),
scheda G (`G_DATI_E_ALGORITMI_DEL_CLOUD.md`: G-019..G-026, G-035 cache empiriche), `00_INVENTARIO.md`. Strumenti miei, rieseguibili, in `ARCHITETTURA_2026-10/strumenti/`:
`E2_omega_righe.py` (righe di `omega_service.py` per fascia e ruolo) e `E2_param_confronto.py` (+ `E2_param_confronto_output.txt`: i 87 parametri Python contro TS).

---------------------------------------------------------------------------------------------------

## 1. OGGI

### 1.1 Cos'e' davvero Omega (letto dal codice)

Un bot **a polling**, un processo, che gioca il **lay sul Correct Score**: due celle per partita, una nel 1T (gamba `ht_cs`, "A") e una nel 2T (gamba `ft_cs`, "B"), con stake fisso
1,00 EUR (motore **V3**, di serie dal 17/09: `OC:221`), l'uscita e' una **proposta** che firma l'utente (o, per scelta, la esegue il bot: `OC:322`). Restano accesi nel codice due motori vecchi:
**v2** (due gambe, size dal target di giornata, green-up automatico) e **v1** (una gamba, quota piu' alta), selezionabili con `strategy_version` 2|3 e `engine` `legs`|`single` (`OC:59,221`).

- **Processo**: `Betfair.omega.omega_service` lanciato dal watchdog di `desktop/main.js:450` (`spawnRunner('omega-service', [..., 'Betfair.stream.watchdog', '--', 'Betfair.omega.omega_service'])`);
  lock di istanza su 127.0.0.1:47313 (`desktop/main.js:446-447`; copia propria `OS:8563` `_acquire_single_instance_lock`, D-055); canale locale del bot ws 47334 (`pages/Omega.tsx:569`).
  `main` `OS:8800` -> `_ciclo_persistente` `OS:8773` -> `_un_giro` `OS:8841` -> `run_once` `OS:8149-8516` (368 righe).
- **Cadenza**: `poll_interval_s` 20 (min 5, `OC:35`); a riposo `idle_cycle_s` 60 (`OC:211`) salvo "fretta" (`_c_e_fretta` `OS:7906`); sveglia dal canale locale che anticipa il giro con pavimento
  `GIRO_MINIMO_CANALE_S` 5 s (`OS:571`, `_pavimento_sveglia` `OS:8635`).
- **Dati in ingresso**: riga del FEED unico dello scanner (blocchi `cs`, `ht`, `flusso`) dal canale 47336 o dal DB (`avvia_client_scan` `OS:715`, `_riga_del_giro` `OS:682`, `_feed_row` `OS:913`);
  REST fresco solo come ripiego (`_leg_market` `OS:1771`); punteggio e minuto REALI dal feed, poi `live_now` (`_build_score_lookup` `OS:8905`, `_live_state_for` `OS:1106`).
- **Dati dal cloud nel percorso di decisione**: lambda pre-match (`_prematch_lambdas` `OS:1169-1306`, cache 900 s `OS:1059`), tabelle empiriche HT->FT e per minuto (RPC `get_omega_ht_ft`
  `ODB:1055`, `get_omega_minute_ft` `ODB:1068`; cache 6 h `OS:106`, `_empirical_table` `OS:1350`, `_minute_table` `OS:1319`) = G-035: una RPC **sincrona** dentro `_model_select`/`_v3_p_empirica`.
- **Tabelle** (da `ODB`): `omega_control` (singleton, `ODB:49,55`), `omega_trades` (`ODB:75-280,720,945-1031`), `omega_activity` (`ODB:61`), `omega_manual_requests` (`ODB:281-423`: richieste e proposte),
  `omega_events` (`ODB:300,436-564`), `omega_market_snapshot` (`ODB:481`), `omega_missions` (`ODB:697-717`), `omega_daily_goal` (`ODB:1041`); in lettura `live_now` (`ODB:595`), `live_follow` (`ODB:618`),
  `fixture_predictions` (`ODB:742,756`); coda ordini `betfair_live_order_requests` + specchio `betfair_live_orders` + `betfair_live_heartbeat` (`ODB:628-690`). RPC: `request_betfair_live_order` `ODB:638`,
  `get_market_frequency` `ODB:767`, `get_omega_aggregates_modalita` `ODB:823`, `get_omega_aggregates` `ODB:875`, `get_omega_ht_ft`, `get_omega_minute_ft`. Frequenza misurata (scheda G, `07 §4.2`): Omega ~12,7 richieste/min
  il 04/10 (`omega_trades` GET 5,6/min); il servizio risulta fermo il 02/10 (G, tabella T10).
- **Chiamate di rete nel percorso critico**: REST `list_today_football_events` (referto 02/10: x444 in 438 giri), RPC empiriche sincrone, `insert_trade` di riserva PRIMA dell'ordine (reserve-first, `OS:2709-2791`),
  lettura dell'aggregato giornaliero (RPC, cache 20 s `OC:174`). Nessun book via stream in-process: il bot legge il feed scritto da un altro processo (scanner).
- **Orologi**: 20/60 s giro; cache `feed_cache_s` 2 s, `scanner_status_cache_s` 10, `aggregates_cache_s` 20, `sets_cache_s` 30, `results_every_s` 60, `missions_every_s` 5, `conto_every_s` 120, `events_refresh_s` 1800,
  `idle_stats_s` 60 (tutti `OC:161-211`); tetti di freschezza NON editabili nel codice: `FEED_MAX_AGE_S` 15 (`OS:85`), `DECISION_MAX_AGE_S` 25 (`OS:89`), `SELECT_SCORE_MAX_AGE_S` 25 (`OS:90`),
  `GREENUP_MAX_AGE_S` 90 (`OS:91`), `CASHOUT_FEED_MAX_AGE_S` 20 (`OS:99`), `SCORE_MAX_AGE_S` 180 (`OS:48`).

### 1.2 Dipendenze (grep)

In uscita da Omega: `Betfair.stream.{arresto_ordinato, avvio_app, esiti_ordini_canale, local_channel, sveglia_canale, canale_bot, flusso_prezzi, scores.scan_feed, scores.betfair_inplay, trading.stato_mercato}`
(`OS:22-36`, `ODB:13-15`); `Betfair.odds_refresh.get_shared_client` (`OMK:63,71,94`); `value_engine.{devig, poisson_total, goal_timing}` (`OM:261,720-721,893`) e `tactical_engine` (lambda da `fixture_predictions`,
`OM:9`, `OS:1177`); `Betfair.stream.engine.{live_engine, live_engine_pro}` (`OM:238`, `OE:1226`, `OS:1380`); **`Betfair.safe_strategy.execution` importato "pigro" in 19 punti di `OS`**
(`grep -c "safe_strategy import execution as X" omega_service.py` = 19; 24 simboli `X.*` usati: `close_trade`, `aggiorna_trade`, `ricorda_tradotto`, `nei_termini_della_riga`, `annulla_su_betfair`, `settle_position`,
`settle_orphan_closing`, `close_plan`, `apply_hedge_state`, `locked_pnl`, `net_exposures`, `known_closings`, `esposizione_eur`, `blocco_di_catena`, `rifiuto_catena_asincrono`, `_place_via_canale`, `_live_brake`...) e
`safe_strategy.exits` in altri 7 (`XE.decide_time_exit`, `XE.ev_hold`, `XE.track`, `XE.TRACK_KEY`...). `OP` richiama `OS` in 8 punti (`from . import omega_service as S`) e `OS` richiama `OP` in 3 (`OS:309,1518,5998`): **ciclo**.
Cicli gia' censiti in `00_INVENTARIO.md` (safe_strategy <-> omega).

In entrata (altri bot e banco) - tabella in 1.5.

### 1.3 Mappa interna di `omega_service.py` (strumento `E2_omega_righe.py`, rieseguito)

S = strategia, G = guscio, M = missioni (funzione utente con suggerimenti). Le fasce sono un MIO giudizio sulla responsabilita' dominante, controllato sull'indice `grep -n "^def "` di `OS`.

| Righe | N | Responsabilita' | Ruolo |
|---|---:|---|---|
| 1-40 | 40 | docstring, import | G |
| 41-250 | 210 | orologio `_now`, tetti di freschezza, retry gambe, `_Cache` 169-185, stato di processo | G |
| 251-848 | 598 | `svuota_le_cache` 260, `_fase_dovuta` 325, `_insieme_cached` 336, `_aggregati_cached` 367, `_con_modalita` 409, `_feed_riga_cached` 435, `_scanner_eta_cached` 489, sveglia 595-640, client scan 715-848 | G |
| 849-1137 | 289 | feed -> stato: `cs_snapshot_from_payload` 848, `_feed_state` 1063, `_feed_fresh_for_decision` 1095, `_live_state_for` 1106, `_flusso_*` 959-1011 | G (cancelli di freschezza) |
| 1138-1396 | 259 | catena lambda `_prematch_lambdas` 1169, `_minute_table` 1319, `_empirical_table` 1350, `_rho_for` 1378 | **S** |
| 1397-1770 | 374 | `_model_select` (v2) 1397, `_v3_tarature` 1503, `_v3_finestra` 1532, `_v3_p_empirica` 1543, `_v3_select` 1590, `_v3_esposizione_di_partita` 1711 | **S** |
| 1771-1879 | 109 | `_leg_market` 1771, `_mercato_in_attesa` 1802, `_log_dedup` 1861 | G |
| 1880-2094 | 215 | `scan_and_place_legs` 1880, `_scan_event_legs` 1941 (finestre, ordine dei cancelli) | **S** |
| 2095-2354 | 260 | gambe fallite 2095-2185, freni REST 2185-2243, catena 2243-2294 | G |
| 2355-2427 | 73 | `_size_and_place` (stake, cap) | **S** |
| 2428-2634 | 207 | motore v1: `estimate_minute` 2428, `matches_remaining` 2461, `scan_and_place` 2489 | **S** (legacy) |
| 2635-4970 | 2.336 | `_confirm_open_trade` 2635, `_place_one` 2709, gate/porta 3019-3232, canale 3232-3535, enqueue 3535-3670, poll flumine 3670-4195, paper 4195-4337, `reconcile_pending` 4337, orfani/stale 4465-4583, chiuso dall'utente 4583-4970 | G |
| 4971-5424 | 454 | `settle_open` 4971, `_settle_hedged` 5106, `track_event_results` 5268, `_snapshot_daily_goal` 5321, `refresh_events` 5381 | G |
| 5425-6315 | 891 | `process_manual` 5425, `_manual_place` 5514, `_cashout_prices` 5850, `_manual_cashout` 6014, `_dopo_il_cashout` 6237 | G |
| 6316-6411 | 96 | `chiudi_eventi_in_attesa` 6316, costanti green-up | G |
| 6412-6923 | 512 | green-up v2: candidati 6534, P(perdita) 6679, `_greenup_decide` 6760, hold/blind/residuo 6830-6904 | **S** (legacy v2) |
| 6924-7171 | 248 | `_greenup_send` 6924, `_nota_flusso_greenup` 7133 | G |
| 7172-7368 | 197 | `_greenup_one` 7172, `process_auto_greenup` 7341 | **S** (legacy v2) |
| 7369-7751 | 383 | missioni: `_cs_suggestion` 7408, `_scalp_suggestion` 7512, `_process_one_mission` 7544, `process_missions` 7705 | M |
| 7752-8936 | 1.185 | cadenza 7755-7966, `_stop_perdita` 7819, `_idle_stats` 7836, `ferma_al_nuovo_avvio` 7966, `_fasi_di_gestione` 8035, `_giro_senza_controllo` 8110, `run_once` 8149, lock/sveglia/canale 8532-8744, `main` 8800, `_build_score_lookup` 8905 | G |

Totali: **S 1.837 (20,6%)**, **G 6.716 (75,1%)**, **M 383 (4,3%)** su 8.936. Concorda con la scheda D (S di Omega 1.763 = scheletro del runtime sulle sole def, D §1.2) e conferma che
Omega e' al **75% guscio**. Dentro S, **1.023 righe sono motori legacy** (v1 207 + `_model_select` 107 + green-up v2 709): raggiungibili solo con `strategy_version=2` (`OC:221`) e coperte dagli scenari `base`/`apertura`/`paper` del banco (RR:977-984).

### 1.4 Gli altri file, per ruolo (misura `E2_omega_righe.py`; ruolo = mio giudizio)

| File | Righe | Strategia | Guscio | Condiviso con altri bot | Non classificato (costanti, docstring, import) |
|---|---:|---:|---:|---:|---:|
| `omega_service.py` | 8.936 | 1.837 (+383 M) | 6.716 | - | - |
| `omega_v3.py` (modello V3, cancelli, uscita) | 1.248 | 1.248 | - | - | - |
| `omega_engine.py` | 1.331 | 403 (`select_lay_runner` 127, `dynamic_target` 218, `lay_size_from_target` 225, `apply_liability_cap` 253, `mission_phase` 866, `legs_remaining` 982, `seleziona_v3` 1231...) | 698 (contabilita' 338-637, riconciliazione 638-790, regolamento 791-852, paper_fill 271-335, risultati 1053-1167) | 8 simboli usati da Safe (1.5) | 230 |
| `omega_proposte.py` (uscita a proposta) | 1.235 | 446 (`_una_gamba` 379, `esito_uscita_al_prezzo` 1119, cap 239-290...) | 529 (`_scrivi` 689, `_esegui_da_solo` 801, `_decadi` 670, `process_proposte_uscita` 313) | - | 260 |
| `omega_config.py` (87 parametri + whitelist) | 463 | 463 (valori di serie = strategia) | - | - | - |
| `tools/misura_k.py` (tabella k per secchio, caricata da `OE:1299`, `OS:1523`) | 499 | 499 | - | - | - |
| `omega_model.py` (lambda, griglia, selezione v2, calibrazione) | 1.182 | - | - | **1.182** (Safe, Mike) | - |
| `omega_empirical.py` | 249 | - | - | **249** (Mike) | - |
| `omega_market.py` | 1.794 | - | - | **1.794** (Mike, Safe, banco) | - |
| `omega_db.py` | 1.081 | - | 1.081 | 2 funzioni usate da Safe/Mike | - |
| `porta_ordini.py` | 237 | - | 237 | - | - |
| `omega_advisor.py` (consulente dati delle missioni) | 400 | (M) 400 | - | - | - |
| **Totale 12 moduli di produzione** | **18.655** | **4.896** (+783 M) | **9.261** | **3.225** | **490** |

Controllo: 4.896 + 783 + 9.261 + 3.225 + 490 = 18.655. **Strategia 26%**, missioni 4%, **guscio 50%**, condiviso 17%, resto 3%.
Non in tabella: `certificazione.py` 2.160 + `RR` 2.593 (banco, scheda H), `liquidity_probe.py` 402 + `omega_validate.py` 183 (strumenti di misura, non importati dal servizio).

### 1.5 Quali moduli di Omega usano Mike e Safe (codice condiviso che deve trovare casa)

| Modulo/simbolo Omega | Chi lo usa (fonte) | Stato oggi |
|---|---|---|
| `OMK` (letture mercato 1-609, ordini REST 610-1443, conto 1445-1794) | **Mike**: `mike/service.py` 12 import "pigri"; simboli `call`, `place_order_live`, `place_submin_live`, `cancel_order_live`, `list_current_orders(_account)`, `list_cleared_orders(_account)`, `market_profit_and_loss`, `order_state_by_bet_id`, `read_book`, `attiva_saldo_su_evento`, e PRIVATI `_riga_corrente`/`_riga_regolata` (`grep -o "omega_market\.[a-z_]*"` su `mike/service.py`); `_RealMarket` `mike/service.py:131-302` **riassegna la costante di modulo** `omega_market.CUSTOMER_STRATEGY_REF` (`:133-143`) e poi chiama; **Safe**: `bot_service.py:54,137` (`_real_market = _MercatoSafe(_omega_market)`), `:10919`; `execution.py:40,980,1560-1563` (`PlaceRifiutato`, `CancelResult`, `piano_submin_live`); **banco**: `banco_comune.py` (`PlaceRifiutato`, `PlaceResult`, `CancelResult`, `OM`), `tools` di replay Safe (`MarketSnapshot`) | un modulo "di Omega" che e' in realta' il client Betfair di tre bot |
| `OM` (lambda, `residual_grid`, `lambdas_from_pre_ko`, `LiveState`, `score_probs`) | Safe `safe_strategy/opportunity.py` (`M.residual_grid`, `M.lambdas_from_pre_ko`, `M.MAX_GOALS_GRID_HT`), `safe_strategy/tools/validate_opportunity.py`; Mike `mike/dossier.py` (`residual_grid`, `LiveState`, `score_probs`, `_M`); a sua volta `OM:401` importa `safe_strategy.calibration` | modello probabilistico condiviso, vive nella cartella di un bot |
| `OEMP` (`EmpiricalTable`) | Mike `mike/dossier.py` | idem |
| `OE` (8 simboli) | Safe `execution.py`: `E.RECON_GRACE_S`, `E._age_seconds`, `E._order_matches`, `E.liability_from_lay`, `E.round_to_tick`, `E.settle_pnl`, `E.tick_down`, `E.tick_up`; `safe_strategy/opportunity.py` `parse_scoreline`; `tools/verifica_pnl_2026_09_12.py` | tick, riconciliazione e P&L: contabilita' ordine comune |
| `ODB` (`fixtures_for_window`, `fixture_analysis`) | `safe_strategy/bot_db.py:926-942` e `mike/db.py:629-631` "delegano a omega_db"; il resto di `bot_db.py`/`mike/db.py` e' copia (scheda G, G-019..G-026) | accesso DB duplicato 3 volte |
| `OS` (gate flumine `_flumine_gate`, `_flumine_enqueue_place/_cancel`) | Safe `execution.py:221-229` `_omega_service()` ("riuso 1:1 di `omega_service._flumine_gate`", `:1277`; `:1773` "PORT fedele di `_flumine_enqueue_place`"), `arresto_bot.py` (`OS._flumine_enqueue_cancel`), `bot_service.py` (`_os`); banco `trasporto_rapido.py`, `proposte_modello.py`, `trasporto.py` (`OPO`) | Safe dipende dal SERVIZIO di Omega |
| `OPO` | banco `trasporto.py`/`trasporto_rapido.py` (`OPO`) | adattatore del canale ordini |

**Dove deve trovare casa il condiviso (proposta)**, senza toccare nessuna regola:
1. `nucleo/mercato_betfair/` = `OMK` spezzato: letture 1-609 e 1445-1794 (959 righe) -> componente A; ordini 610-1443 (834) -> componente C (porta ordini unica, `C_PORTA_ORDINI.md` S3/S4: "REST diretto" e "place-and-trim").
   `CUSTOMER_STRATEGY_REF` diventa un argomento della chiamata, non una costante di modulo da riassegnare (oggi due difese: riassegnazione `mike/service.py:142-143` e `strategy_ref=` `:159`).
2. `nucleo/modello_gol/` = `OM` + `OEMP` (1.431 righe) + `value_engine`: UNA casa per lambda, griglia residua, tabelle; Mike/Safe/Omega la importano.
3. `nucleo/contabilita_ordine/` = i simboli `OE` di Safe (tick, `_order_matches`, `settle_pnl`, riconciliazione) + i 24 simboli `safe_strategy.execution` che Omega gia' usa: oggi la meta' del guscio di Omega e' dentro `safe_strategy/execution.py` (3.093 righe).
4. Il resto di `ODB` -> scheda G (accesso DB per bot generato da uno schema).

---------------------------------------------------------------------------------------------------

## 2. FUNZIONALITA' (E2-001 ... E2-109)

Legenda: **[UI]** visibile nella UI (file del pannello); **[P]** parametro editabile (chiave in 2.12); **[S]** strategia intoccabile; **[G]** guscio.

### 2.1 Decisione di ingresso - motore V3 (di serie)

- **E2-001** [S] Motore V3 acceso di serie: solo CORRECT_SCORE, lay, stake 1,00 EUR, margine k sulla probabilita' fusa, uscita a proposta. `OC:221`, `OV3:114` `STAKE_STANDARD`, `OS:1590` `_v3_select`. [P `strategy_version`, `v3_stake_eur`]
- **E2-002** [S] Due gambe per partita, due celle DIVERSE in due momenti: A = 1'-44' (`ht_cs`), B = 46'-85' (`ft_cs`). `OC:250-253`, `OS:1874-1877` `_LEGS`, `OS:1532` `_v3_finestra`, `OS:1987-1990`, `OV3:917` `in_finestra`. [P 4 finestre]
- **E2-003** [S] Minuto e punteggio SEMPRE reali (feed, poi `live_now`), mai l'orologio; fase da stato IPS o minuto. `OS:1961` `_live_state_for`, `OS:1967`, `OE:866-903` `mission_phase`, `OS:8905` `_build_score_lookup`.
- **E2-004** [S] Una gamba per (partita, fase): `(event_id, leg) in traded_legs` salta; la partita conta UNA volta (`max_events`: niente partite nuove oltre il tetto, ma la seconda gamba si fa sempre). `OS:1948-1950,1985,2051-2053`. [P `max_events`]
- **E2-005** [S] Cella diversa fra le due gambe e celle gia' bancate escluse (`escludi`). `OS:1711` `_v3_esposizione_di_partita`, `OS:2026-2030`, `OV3:753`.
- **E2-006** [S] Pre-filtro sul calcio d'inizio (non si perde tempo su partite lontane >25 min dalla finestra): `OS:1951-1960`.
- **E2-007** [S] Riserva PRIMA dell'ordine (reserve-first): riga `pending` in `omega_trades` con unique su evento/gamba; violazione = `already_reserved`; altro errore = `reserve_failed`. `OS:2709-2791`, `OS:2692` `_e_violazione_unica`; Costituzione I1.
- **E2-008** [S] Stop all'obiettivo di giornata: `stop_on_goal` e `realized >= daily_goal` (serie 250) fermano le NUOVE aperture, in v2 E in v3 (il controllo precede il ramo v3). `OS:1890-1900`, `OC:13,33`. [P `stop_on_goal`, `__daily_goal` colonna `omega_control.daily_goal`] [UI `pages/Omega.tsx:899-912`]
- **E2-009** [S] Stop alla perdita giornaliera: `daily_loss_cap` (v2) o `v3_daily_loss_cap` 300 (v3) su `E.realized_effective` dei soli numeri del bot. `OS:1904-1909`, `OS:1626` (`cap_perdita_giornaliera`), `OS:7819` `_stop_perdita` (solo lettura per la UI). [P]
- **E2-010** [S] Partita CHIUSA DALL'UTENTE: nessuna apertura finche' non preme "Riprendi". `OS:1917-1925`, `OS:4939` `eventi_chiusi_dall_utente`.
- **E2-011** [G] Un evento rotto non ferma gli altri (isolamento per evento). `OS:1935-1937`.
- **E2-012** [S] Senza stato live: `no_live_state`, nessuna gamba (skip loggato UNA volta ogni 600 s). `OS:1962-1965`, `OS:1861` `_log_dedup`, `OS:1789`.
- **E2-013** [S] Prezzi vivi o niente: se il blocco `flusso` dello scanner dice che MATCH_ODDS/CS non sono vivi, nessuna apertura (`flusso_interrotto`); l'HT conta solo per le decisioni SULL'HT e solo in fase pre/1T (correzione 07/10 della regressione del 29/09). `OS:1970-1983`, `OS:940` `_ht_ancora_in_gioco`, `OS:959` `_flusso_della_riga`, `OS:994` `_flusso_feed`, `OS:1991-2000`.
- **E2-014** [S] Mercato non OPEN, chiuso o non in gioco: nessuna apertura (`market_not_open`). `OS:2011-2019`.
- **E2-015** [S] Ritenti della gamba dopo un esito CERTO negativo (FOK ucciso, rifiuto): max 3, uno ogni 30 s; sopravvivono al riavvio (`load_failed_legs`). `OS:100-101,2095-2185`, `OS:2294` `_leg_certain_failure`.
- **E2-016** [S] Catena dei lambda pre-match: quote 1X2 pre-KO devigate PRIMA (O1, di serie), poi fixture del DB, poi lambda salvati dell'evento, poi mercato Over/Under live (ultimo ripiego); la FONTE e' dichiarata nell'audit. `OS:1138-1306`, `OS:1169` `_prematch_lambdas`, `OC:107` `lambda_quote_prima`, `OC:100` `lambda_live_fallback`, `OM:759` `lambdas_from_live_ou`. [P]
- **E2-017** [S] Lambda impliciti nell'INTERO mercato (scala CS + linee O/U), sempre calcolati per l'audit: `lambda_market_grid`. `OM:826-1090`, `OS:1414`, `OC:86`. [P]
- **E2-018** [S] Modello V3 `gamma_poisson` (aggiornamento bayesiano, binomiale negativa; alternative `poisson`, `dixon_coles`, `dixon_robinson`, `bivariato`): griglia dei gol residui, tau Dixon-Coles, recupero 2'/4', max 6/10 gol residui. `OV3:99-115,297-476`, `OC:229,329`. [P `v3_modello`]
- **E2-019** [S] Fusione col mercato (pool logaritmico in logit, pesi per fascia): `OV3:491-564` (`_logit`, `peso_fusione`, `fondi_col_mercato`, `p_mercato_devigata`), `OE:1285-1289`. [P `v3_fusione_mercato`]
- **E2-020** [S] Cartellini rossi del feed nell'intensita' residua, in ingresso E in uscita (coefficienti globali). `OE:1198` `moltiplicatori_rossi_v3`, `OC:306`. [P `model_red_cards`]
- **E2-021** [S] Veto di coda empirico OBBLIGATORIO dove i dati esistono: `P_nostra = max(P fusa, P storica)` se n >= `v3_empirical_min_n` (200); shrinkage con prior globale (`SHRINK_K` 500, `Z_UPPER` 1,64). `OV3:819`, `OS:1543` `_v3_p_empirica`, `OEMP:26-72`. [P]
- **E2-022** [S] Selezione V3: i 14 cancelli in ordine, con il motivo di ogni scarto: tabella 2.2.
- **E2-023** [S] Regola di scelta: fra i candidati che passano vince la P_nostra minima, poi il margine piu' alto, poi il prezzo piu' basso (`(p_nostra, -margine, prezzo)`). `OV3:857-861`.
- **E2-024** [S] "Any Other Home Win/Away Win/Draw" candidati come i numerici, con le STESSE condizioni (decisione dell'utente 07/10, Costituzione §21): P = somma della griglia sui punteggi coperti non quotati + coda oltre la griglia; distanza dal punteggio coperto piu' vicino. `OV3:132-218,753-786`, `OE:1312-1321`, `OC:279`. [P `v3_include_aggregate`]
- **E2-025** [S] Tetti di sicurezza di V3 (non zero): cap di gamba 95 EUR, di partita 190, aperto 1.000, perdita 300. Gamba: la cella oltre il cap si SCARTA (`oltre_il_cap_di_gamba`, `v3_cap_gamba` critico), non si taglia la size; partita `cap_partita`; aperto `cap_aperto`; tolleranza 0,011. `OC:259-262`, `OV3:838-841`, `OS:1695-1708` (in `_v3_select`), `OS:2394-2421` (in `_size_and_place`). [P]
- **E2-026** [S] Stake fisso, mai tagliato: o si entra interi o no (`insufficient_liquidity` se la controparte < stake). `OS:2386-2391`, `OC:225,264`. [P `v3_stake_eur`, `v3_min_lay_liquidity`]
- **E2-027** [S] Tarature V3 caricate una volta: parametri vincenti `data/parametri_vincenti_2026-09-16.json` (`OP:148`, `OP:153` `parametri_modello`) e tabella k (`misura_k.carica_tabella_k`, `OS:1503-1529` `_v3_tarature`). Nella chiamata di produzione `k_tab=None` (`OS:1646`): vale `v3_k_minimo` (1,11) per tutti i secchi (`OV3:828-831`).
- **E2-028** [S] Audit completo di ogni decisione V3 (modello, lambda e fonte, finestra, k, scartati max 12, mult. rossi, P modello/fusa/storica, EV, liability, motivo testuale): `OS:1659-1693`, salvato nel `meta` della riga.
- **E2-029** [S] Motivi di non-ingresso dichiarati (A8): `no_live_state`, `fuori_finestra`, `cap_perdita_giornaliera`, `no_market`, `no_model_lambdas`, `nessun_candidato`, `cap_partita`, `cap_aperto`, `v3_cap_di_gamba`, `insufficient_liquidity`, `max_open_liability`. `OS:1590-1710,2376-2421`; verificati dal banco (A8 `certificazione.py:1278`).

### 2.2 I cancelli di selezione V3 (`OV3._seleziona`, `omega_v3.py:699-868`), nell'ordine in cui scartano

| # | Cancello | Motivo scritto | `file:riga` | Parametro (serie) |
|---|---|---|---|---|
| 1 | cella gia' bancata nella partita | `cella_gia_bancata` | `OV3:753` | - |
| 2 | aggregato con interruttore spento | `aggregato_escluso` | `OV3:759` | `v3_include_aggregate` True |
| 3 | nessun prezzo lay valido (`<= 1,0`) | `senza_lay` | `OV3:763` | - |
| 4 | controparte lay < minimo | `liquidita_insufficiente` | `OV3:767` | `v3_min_lay_liquidity` 1,0 |
| 5 | punteggio ormai impossibile | `irraggiungibile` | `OV3:772,781` | - |
| 6 | gol aggiuntivi < soglia (numeriche; aggregati: distanza dal coperto piu' vicino) | `troppo_vicino_al_punteggio` | `OV3:776,786` | `v3_distanza_minima_gol` 2 |
| 7 | modello senza P per la cella | `fuori_griglia` | `OV3:791` | - |
| 8 | prezzo non convertibile in p implicita | `prezzo_non_valido` | `OV3:795` | commissione 5 % (`commission_pct`) |
| 9 | p implicita sotto la fascia | `p_impl_sotto_fascia` | `OV3:804` | `v3_p_min_pct` 1,0 % |
| 10 | p implicita sopra la fascia | `p_impl_oltre_fascia` | `OV3:807` | `v3_p_max_pct` 2,0 % |
| 11 | P_nostra = max(fusa, storica) sopra il tetto duro | `p_oltre_il_tetto` | `OV3:819-824` | `v3_p_max_pct` 2,0 % |
| 12 | margine: `P_nostra <= p_impl / k`, `k = max(k_minimo, k_tab[secchio])` | `margine Nx, ne serve Ky` | `OV3:828-836` | `v3_k_minimo` 1,11 |
| 13 | liability della cella oltre il cap di gamba | `oltre_il_cap_di_gamba` | `OV3:838-841` | `v3_max_liability_per_leg` 95 |
| 14 | tra i superstiti: P_nostra minima, margine massimo, prezzo minimo | (scelta) | `OV3:857-861` | - |

Prima di questi, in `_v3_select` (`OS:1590-1710`): finestra, cap perdita, mercato presente, lambda disponibili; dopo: cap di gamba/partita/aperto sul candidato.

### 2.3 Decisione di ingresso - motori legacy (ancora raggiungibili)

- **E2-030** [S] Motore v2 (`strategy_version=2`): selezione per MODELLO sul risultato con P piu' bassa: quota in banda `price_min` 20 - `price_max` 120, liquidita' >= size necessaria, mai aggregati (salvo `include_aggregate`), irraggiungibile, distanza >= `model_min_goal_distance` 2, `P_sel = max(modello, empirica)`, scarto se `P_sel > model_p_max_pct` (2 %) o `>= P implicita`. `OM:495-604` `select_by_model` (cancelli `OM:532-577`), `OS:1397-1489` `_model_select`. [P]
- **E2-031** [S] v2 - costo di copertura: fra i risultati a P equivalente (entro `select_p_band_ratio` 2,0 x la piu' bassa) vince il piu' economico da coprire, ranking EV con `select_p_hedge` 0,5 e `select_ev_kappa` 1,0; `select_k_se` 0 (conservativa sull'incertezza). `OM:1118-1180`, `OM:592-604`. [P x5]
- **E2-032** [S] v2 - sizing dal target di giornata: `target = (goal - realized) / gambe_residue` (`OE:218`), `lay_size_from_target` con commissione e `min_stake` 0,50 (`OE:225-247`), `apply_liability_cap` (`OE:253`), size ridotta alla liquidita' (`size_reduced`), `insufficient_liquidity`; gambe residue `OE:982-1050`. `OS:2355-2427`, `OS:2058-2072`. [P `max_liability_per_match`, `max_open_liability`, `min_stake`]
- **E2-033** [S] v2 - finestre ht 20-40 e ft 50-80 sul minuto reale, `entry_window_source` `score`|`clock`. `OC:34,60-63`, `OS:1987-1990`. [P]
- **E2-034** [S] v2 - calibrazione e fattore di coda: P > 5 % intatta, <= 5 % moltiplicata per `model_tail_factor` 1,3 (usato solo se manca la tabella del calibratore condiviso, `model_calibration` 'off' di serie). `OM:374-470`, `OC:73,96`. [P]
- **E2-035** [S] v2 - veto empirico HT->FT per la gamba 2T (se il punteggio e' ancora quello del 45') e per MINUTO a ogni minuto; `model_empirical` 'veto', `model_empirical_max_minute` 60. `OS:1319-1389,1424-1489`, `OEMP:106-249`, `OC:78,82`. [P]
- **E2-036** [S] v2 - cartellini gialli nei tassi residui (`model_use_yellow_cards`), incertezza sui lambda `model_lambda_cv` 0,30. `OM:1091`, `OM:292-354`, `OC:92,110`. [P]
- **E2-037** [S] Motore v1 (una gamba, quota piu' alta, `engine='single'`): `scan_and_place` `OS:2489-2634`, `estimate_minute` `OS:2428`, `matches_remaining` `OS:2461`, `OE:127-172` `select_lay_runner`, `OE:949-975` `is_eligible` (non gia' giocata, in gioco, nella finestra `entry_minute_min/max` 30-60, `max_events`, `stop_on_goal`). [P]

### 2.4 Esecuzione degli ordini: paper e live

- **E2-038** [G] Paper e live per MODALITA' della riga (`omega_control.mode`, scelta dalla UI; all'avvio dell'app sempre paper): ogni trade porta il suo `mode`; paper e live non si sommano (aggregati per modalita' `ODB:823,875`, `OS:367-409`). [UI `ModeToggle`, `ModeBanner`, `LiveConfirmDialog` in `pages/Omega.tsx:23-27`]
- **E2-039** [G] PAPER: l'ordine passa SEMPRE dal runner flumine (simulatore con coda e bet delay); se il runner non c'e' la riga resta senza ordine e il servizio scrive `paper_runner_non_disponibile` (nessun fill "di casa"). `OS:2824-2870`, `OS:3098` `_flumine_paper_gate`, `OS:3086` `_avvisa_rest_in_paper`, `OC:46` `paper_fill_ttl_s` 45. [P]
- **E2-040** [G] LIVE: via coda del runner con FOK vero (`timeInForce=FILL_OR_KILL`, lo esegue Betfair); gate fail-closed: kill-switch `omega_live_via_flumine`, runner in modo LIVE, contratto di revoca, heartbeat <= 90 s (`RUNNER_HB_MAX_AGE_S` `OS:3008`), evento in follow. `OS:3039` `_flumine_gate`, `OS:3113` `_live_flumine_expected`, `OC:51,55`. [P `omega_live_via_flumine`, `live_fill_deadline_s` 20]
- **E2-041** [G] LIVE di ripiego sul REST (FOK diretto) quando il gate non passa o `execution_mode='rest'`; freni dedicati. `OS:2896`, `OS:2185,2202` `_freno_rest_aperture/_live`, `OMK:704` `place_order_live`, `OC:42`. [P `execution_mode`]
- **E2-042** [G] Porta ordini sul canale locale del runner (`OMEGA_ORDINI_VIA_CANALE`, SPENTO di serie): `OPO:48-237` (`adatta_comando` 88, `VistaOmega` 129), `OS:3135-3232`, scheda C S1.
- **E2-043** [G] Coda DB `betfair_live_order_requests`: `OS:3535` `_flumine_enqueue_place`, `OS:3636` `_flumine_enqueue_cancel`; scrive la riga di riserva, accoda, ritorna `_ENQUEUE_UNKNOWN` se ignoto. `OS:3016`.
- **E2-044** [G] Place-and-trim sotto il minimo di giurisdizione (importi esatti al centesimo): `OMK:1008` `piano_submin_live`, `OMK:1043` `place_submin_live`, minimo .it 0,50 (`OC:31`).
- **E2-045** [G] Esito dall'ordine: poll dello specchio `poll_flumine_pending` (`OS:4108`), `_poll_one_flumine_trade` 3822 (paper) e `_poll_one_flumine_live_trade` 3966; `_mirror_fill` 3670, `_flumine_confirm` 3706, `_flumine_no_fill_error` 3761, orfani `_recover_flumine_orphan` 3934; cancel residuo oltre il TTL `FLUMINE_CANCEL_GRACE_S` 60 (`OS:3009`).
- **E2-046** [G] Conferma robusta dell'apertura con retry; se fallisce, CRITICAL con `bet_id`. `OS:2635` `_confirm_open_trade`, log `confirm_failed`.
- **E2-047** [G] Esito ignoto = riconciliazione, mai secondo invio: `place_exception_reconciling` critico. `OS:2923-2940`, `OMK:801-803` (scheda C).
- **E2-048** [G] Riconciliazione dei `pending`: paper conferma, live interroga Betfair per `customerOrderRef` deterministico, apre col fill reale / attende / libera / marca errore (grazia `RECON_GRACE_S` 120). `OS:4337` `reconcile_pending`, `OE:718` `reconcile_decision`, `OE:658-700` ref, `OMK:1462` `order_state_by_bet_id`. [`omega-<id>`, `CUSTOMER_STRATEGY_REF='omega'` `OC:19`]
- **E2-049** [G] Orfani e "stale": ordine live orfano oltre 48 h (`ORPHAN_GONE_MAX_H` `OS:4462`), apertura ferma oltre 8 h (`STALE_OPEN_MAX_H` `OS:4522`) -> allarme `stale_open_alert`. `OS:4465,4525`.
- **E2-050** [G] Catena di rifiuti: dopo certi rifiuti prima del mercato (`_RIFIUTI_PRIMA_DEL_MERCATO` `OS:2226`) la catena si BLOCCA e si ripristina. `OS:2243-2294`.

### 2.5 Regolamento, risultati, contabilita'

- **E2-051** [G] Regolamento dal mercato: P&L dal WINNER/LOSER, solo quando OGNI runner e' terminale; `CLOSED` non finalizzato si ritenta (I3). `OS:4971` `settle_open`, `OS:5106` `_settle_hedged`, `OE:794-852` `resolve_settlement`/`settle_pnl`, `OS:5086` `_read_markets_batch`.
- **E2-052** [G] Regolamento del PAPER senza mercato: `vince_col_risultato` (con la correzione "Any Other" del 07/10). `OE:1121-1155`.
- **E2-053** [G] Risultati reali 1T/2T timbrati sulle posizioni recenti (rete di sicurezza contabile, ogni 60 s, finestra 36 h). `OS:5268` `track_event_results`, `OS:5245`, `OE:1063` `results_from_payload`, `OC:185`. [P `results_every_s`]
- **E2-054** [G] Commissione 5 % applicata UNA volta sul netto vincente. `OC:29`, `OE:265`, `OE:815`. [P `commission_pct`]
- **E2-055** [G] Aggregati del giorno operativo (Europe/Rome) PER MODALITA': R, liability aperta, eventi del giorno; ripiego a calcolo da righe se la RPC manca; cache 20 s con ricalcolo forzato dopo piazzamento/regolamento. `OS:367` `_aggregati_cached`, `OS:409` `_con_modalita`, `ODB:777-934`, `OE:392-537` `aggregate_trades`, `OE:173-195`. [UI KPI/DayBar `pages/Omega.tsx`]
- **E2-056** [G] Posizioni manuali dell'utente escluse dai numeri del bot. `OE:338` `posizione_manuale`, `ODB:201` `manual_event_ids`, `OS:8317`.
- **E2-057** [G] Snapshot dell'obiettivo giornaliero (storico: "centrato" solo sull'obiettivo di QUEL giorno). `OS:5321`, `ODB:1041`, `OC:13`.
- **E2-058** [G] Eventi del giorno e cache partite: `refresh_events` (REST + replace in `omega_events`), arricchimento fixture. `OS:5381`, `OS:5341`, `ODB:300,436`, `OC:201`. [P `events_refresh_s`] [UI ManualPanel "aggiorna partite"]

### 2.6 Uscite: proposta, interruttore, esecuzione automatica

- **E2-059** [S] Proposta di uscita (V3, di serie): per ogni gamba lay aperta calcola il bloccabile e SCRIVE una proposta se chiudere batte tenere; non invia MAI un ordine (salvo E2-063). Motivi: `blocca_il_profitto`, `protezione`, `cap`, `rischio`. `OP:313` `process_proposte_uscita`, `OP:379-525` `_una_gamba`, `OP:79`, `OV3:1118` `proposta_uscita`, `OV3:949-1096` (`profitto_bloccabile`, `ev_di_tenere`, `p_punteggio_invariato`, `traiettoria_bloccabile`). [UI `SchedaChiusuraOmega.tsx`, `MatchTradesTable.tsx`]
- **E2-060** [S] Saltata con motivo dichiarato quando mancano i dati: `feed_assente`, `punteggio_assente`, `prezzi_non_freschi`, `mercato_sospeso`, `gamba_ht_finita` (HT dopo il 45'), `posizione_senza_numeri`, ...; transitori `controparte_insufficiente`, `nessun_prezzo_di_back`. `OP:86-96`, `OP:426-429`.
- **E2-061** [S] Rischio massimo tollerato: `proposta_p_lose_max_pct` (0 = SPENTA, regola "nessuna soglia nuova si accende da sola"). `OC:313`, `OP:465`. [P]
- **E2-062** [S] Cap che scattano generano la proposta `cap`: globali (perdita giornaliera, aperto) e di gamba/partita, tolleranza 0,011. `OP:98-109,239-290`.
- **E2-063** [S][G] INTERRUTTORE USCITE (condizione 4-bis): `uscite_protezione` `avvisa_e_proponi` (di serie, fail-closed: qualunque altro valore vale proposta) | `automatico` (il bot esegue la stessa uscita, con audit della scelta dell'utente sulla riga e nell'attivita'). Esecuzione `OP:801` `_esegui_da_solo`, max 3 tentativi (`OP:136`), `uscita_automatica`/`_fallita`/`_esaurita`; lettura `OP:292` `modo_uscite`; whitelist `OC:322,361-364`; reset a `avvisa_e_proponi` ad OGNI avvio nuovo dell'app: `OS:7966` `ferma_al_nuovo_avvio` -> `avvio_app.py:182,199`. [UI TS:1252-1257, `interruttori.ts:1257,1333,1386`, `OmegaParamsSheet.tsx:66`, TS:1239] [P]
- **E2-064** [G] Approva / ignora proposta (firma dell'utente): richiesta `cashout` IDENTICA a quella del bottone, distinta con `_uscita_del_bot_approvata` (NON marca la partita "chiusa dall'utente"); condizione caduta -> rifiuto; senza firma -> `proposta_non_firmata`. `OS:5891,5917,5943,5970,5986`, `OS:6014` `_manual_cashout`, `OP:206` `firma_ancora_valida`. [UI `SchedaChiusuraOmega.tsx:265-287` (approva, approva con prezzo, conferma live, ignora), `omegaProposte.ts:320,345`]
- **E2-065** [S] Proposta viva si AGGIORNA senza perdere l'istante della decisione; si ripropone solo se il prezzo si e' mosso di 2 tick o il bloccabile di 0,10 EUR; ricontrollo ogni 20 s; decade se non piu' valida. `OP:68-74,636-690,1173`, log `proposta_riproposta`/`proposta_decaduta`/`proposta_non_piu_valida`.
- **E2-066** [S] Esito dell'uscita al prezzo (anteprima per la UI): `OP:1119` `esito_uscita_al_prezzo`; **duplicata in TS** `omegaProposte.ts:210` `esitoUscitaAlPrezzo` con file d'oro `lib/omegaUscita.golden.json` (527 righe) e `omegaUscita.test.ts`.
- **E2-067** [S] Green-up AUTOMATICO v2 (spento in V3: `OC:417-420` e `OE:1180` `greenup_automatico_attivo`): trigger a distanza <= `greenup_trigger_distance` 1 o quota lay <= 0,5 x ingresso, assestamento dopo un gol 30 s, decisione `exit`/`hold` con le regole di `safe_strategy/exits.decide_time_exit` (bloccato >= 0 -> esce; bloccato >= EV(tengo) - margine 0,10 - premio 5 % -> esce; altrimenti tiene), P(perdita) del modello con floor di mercato (max 3 x, `OS:6646`), take-profit 0,9 x dal 80', retry 20 s max 15. `OS:6436` `_greenup_active`, `OS:6760` `_greenup_decide`, `OS:6679`, `OS:7172` `_greenup_one`, `OS:7341`, `OC:118-139`. [P x14]
- **E2-068** [G] Green-up: invio e stati (`pending/done/hold/failed/blind/residual_dropped`), cieco dopo 3 cicli senza prezzi, residuo, quota implausibile. `OS:6924` `_greenup_send`, `OS:6460-6482`, `OS:6409`, `OS:6448`. [UI TS:824-945 `greenupBadge`]
- **E2-069** [G] Cash-out MANUALE ("Chiudi ora"), anche parziale (frazione/importo), con exit_kind `manual` e motivo scritti su apertura e gamba di chiusura: `OS:6014-6216` `_manual_cashout`, prezzi `OS:5850` `_cashout_prices` (feed max 20 s), `OS:6237` `_dopo_il_cashout`. [UI `MatchTradesTable.tsx:493`, `CashOutGlobale` in Control Room]
- **E2-070** [G] Chiusura delle partite in attesa: `chiudi_eventi_in_attesa` `OS:6316-6411` (cashout globale sulla partita; il bot lo capisce, controllo E4 del banco).

### 2.7 Manuale, missioni, "chiuso dall'utente"

- **E2-071** [G] Coda richieste dell'utente con stale a 10 min: `refresh_events`, `load_markets`, `load_book`, `place`, `cashout`. `OS:5425-5461` `process_manual`, `ODB:281-348`. [UI `ManualPanel.tsx`: aggiorna (371), carica mercati (406), carica book (422), back/lay (434-435), paper/live (438-439), target/stake (462-463), "usa" runner (575), suggerisci il meno probabile (537), conferma "SOLDI VERI" (634-636)]
- **E2-072** [G] Piazzamento MANUALE back/lay con conferma live per ordine; stessa riserva, stessa via paper/live. `OS:5514-5849` `_manual_place`, `OS:5498` `_back_liability`.
- **E2-073** [G] Missioni (centro di controllo per partita): attivare/fermare/chiudere, punteggio e fase, suggerimenti. `OS:7544` `_process_one_mission`, `OS:7705` `process_missions`, `OS:7682` `_mission_scores`, `OS:7664` `_event_really_over`, `ODB:697-717`, `OC:190`. [UI `MissionPanel.tsx` 946, `MissionCard.tsx` 723 (scalper 584-632, "Chiudi missione" 632), `omegaMissions.ts:147-213`]
- **E2-074** [S] Suggerimento lay CS: il runner MENO probabile in assoluto con liquidita' minima e distanza >= 2 gol (`CS_MIN_GOAL_DISTANCE` `OS:7405`); suggerimento scalp: BACK "Under X.5" con linea = gol + 2,5. `OS:7408-7543`, `OE:906,918` (`scalp_market_types`, `pick_under_runner`).
- **E2-075** [G] Consulente dati (INFORMATIVO, mai blocca): Poisson interno, frequenza lega, H2H, budget 1 s. `OAD:316` `advisor_for_suggestion`, `OAD:45`. [UI `formatAdvisorParts` `omegaMissions.ts:292`]
- **E2-076** [G] "Chiuso dall'utente": se l'utente chiude (nell'app o su Betfair) la partita viene marcata, gli ordini vivi annullati, nessuna apertura finche' "Riprendi". `OS:4676` `_marca_chiuso_dall_utente`, `OS:4692` `sorveglia_posizione_di_conto` (2 REST per mercato ogni `conto_every_s` 120), `OS:4826` `annulla_ordini_vivi_del_bot`, `OS:4883`, `OS:4894`, `ODB:491-577`. [UI `PartiteChiuseDallUtente.tsx`, `omegaEventoRiprendi` TS:1418] [P `conto_every_s`]

### 2.8 Ciclo, controllo, avvio/arresto

- **E2-077** [G] Ciclo persistente con isolamento (`except` -> `cycle_exception`), arresto ordinato sentito PRIMA di ogni giro. `OS:8773,8841,8800`.
- **E2-078** [G] Sequenza di `run_once`: controllo -> guardia d'avvio -> richieste manuali -> refresh eventi -> missioni -> `stopping`->`stopped` / bot fermo (solo gestione) -> id dei gia' toccati/aggregati/manuali/missioni -> aperture -> obiettivo -> stats. `OS:8149-8516` (`8166,8194,8205,8219,8224,8232,8284-8337,8363,8377,8388,8469`).
- **E2-079** [G] Controllo illeggibile: giro DEGRADATO di sola gestione con l'ultimo controllo valido (max 300 s), mai aperture. `OS:8110` `_giro_senza_controllo`, `OS:8018`.
- **E2-080** [G] Fasi di gestione che girano SEMPRE (anche a bot fermo): riconciliazione, poll flumine, settlement, uscite (proposte o green-up), risultati. `OS:8035-8107` `_fasi_di_gestione` (D-013).
- **E2-081** [G] Accensione/spegnimento dalla UI: `omega_activate`/stop RPC -> `status` `running|stopping|stopped`. [UI `activateOmega`/`stopOmega` TS:1314-1329]. All'avvio dell'app il bot e' FERMO, `mode='paper'`, uscite MANUALI, senza toccare i `params`: `OS:7966` `ferma_al_nuovo_avvio`, `OS:241` `_GUARDIA_AVVIO`.
- **E2-082** [G] Cadenza adattiva "con fretta"/"a riposo". `OS:7906` `_c_e_fretta`, `OS:7755-7796`, `OC:35,211`. [P `poll_interval_s`, `idle_cycle_s`]
- **E2-083** [G] Sveglia dal canale locale che anticipa il giro (OMEGA_SVEGLIA_CANALE). `OS:8590-8744` (`_avvia_canale`, `_su_sveglia_dal_canale`, `_avvia_sveglia`, `_dormi_o_sveglia`, `statistiche_sveglia`), `OS:570-574`.
- **E2-084** [G] Client del feed unico (canale 47336) con risincronizzazione dal DB ogni 10 s; fonte del giro dichiarata. `OS:715` `avvia_client_scan`, `OS:567` `_RISINC_DB_S`, `OS:695` `fonte_scan_del_giro`, `OS:777` `_applica_esiti_dal_canale`.
- **E2-085** [G] Esiti ordini dal canale (ESITI_ORDINI_CANALE, spento di serie) al posto del poll DB. `OS:790` `avvia_esiti_ordini`, `OS:813`, `OS:824`.
- **E2-086** [G] Cache con TTL tutte dichiarate e regolabili (a 0 = senza cache). `OC:161-204`, `OS:169-185,260-505`. [P x10]
- **E2-087** [G] Battito e stats per la UI: `goal`, `goal_pct`, `stop_perdita` (soglia/chiave/scattato), `motivo_blocco`, liability, target per gamba/partita; a bot fermo `_idle_stats` ogni 60 s; pubblicazione sul canale. `OS:8469-8494`, `OS:7836`, `OS:8753` `_pubblica_stato`, `OS:7782` `_cadenza_battito`. [UI `StatTile`, `KpiRow`, `ServiceHealthChip`]
- **E2-088** [G] Keepalive della sessione Betfair e saldo. `OS:8541` `_maybe_keepalive`, `OMK:140` `keep_alive`, `OMK:129` `attiva_saldo_su_evento`.
- **E2-089** [G] Arresto ordinato dell'app: annulla gli ordini del bot e dichiara le posizioni. `OS:8789` `_chiudi_all_arresto`, `Betfair/safe_strategy/arresto_bot.py` (D).
- **E2-090** [G] Lock di istanza (47313, copia propria), logging, thread di sveglia. `OS:8563`, `OS:8800`.
- **E2-091** [G] Schema DB mancante dichiarato (avviso una volta, non crash). `ODB:355-366` `pare_schema_mancante`, `ODB:512` `_avvisa_una_volta`, log `schema_warn`.

### 2.9 Allarmi e attivita' scritte

- **E2-092** [G] Attivita' scritte in `omega_activity` con `db.log(kind, payload)`: **62 kind distinti** in `OS`+`OP` (`grep -oh "db\.log(\"[a-z_0-9]*\""`): `place`, `place_parziale`, `place_rifiutato`, `place_reconciling`, `hedged`, `settle`, `settle_hedged`, `settle_orphan`, `skip`, `stop`, `size_reduced`, `greenup*` (7), `uscita_*` (4), `proposta_*` (3), `flumine_*` (8), `reconciled_*` (3), `manual_place`, `cashout_manual`, `chiuso_dall_utente`, `model_lambda_live/market`, `flusso_interrotto`, `flusso_non_dichiarato`, ... Diario poi sul canale locale (`omega_attivita`, `canale_bot.py`). [UI `ActivityFeed` `pages/Omega.tsx`, etichette TS: `OMEGA_ACTIVITY_EXTRA` 395-503 (77 chiavi), `OMEGA_ERROR_REASON` 512-578 (46), `OMEGA_WAIT_REASON` 670-703 (3), `activityLine` 607]
- **E2-093** [G] Allarmi critici (flag `critical`, 32 occorrenze nel codice di `OS`+`OP`, `grep -c`): ordine live orfano `orphan_live_alert` (`OS:3441`), apertura ferma `stale_open_alert` (`OS:4525`), green-up cieco, flusso dati non dichiarato (`OS:1973`), cap di gamba v3 (`OS:2400`), esito ignoto (`OS:2940`), controllo d'avvio non riuscito (`OS:7966-8013` `logger.critical`), lettore aggregati senza modalita' (`OS:427`). [UI banner/attivita' in Control Room]
- **E2-094** [G] Log senza rumore: `_log_dedup` (600 s per chiave), `greenup_wait` solo al cambio di motivo. `OS:1861`, `OS:6818`.
- **E2-095** [G] Diagnosi (`diagnosi`), errori per fase (`reconcile_phase_failed`, `flumine_poll_failed`, `settle_phase_failed`, `greenup_phase_failed`, `results_phase_failed`): `OS:8044-8105`.

### 2.10 Interfaccia (Omega)

- **E2-096** [UI] Pagina `/omega`: testata, salute del servizio, toggle paper/live con conferma, equity curve, KPI e barra del giorno, "Partite di oggi/tutte", attivita' del giorno, storico, parametri. `pages/Omega.tsx` (912; sezioni 768-840), `components/trading/*`.
- **E2-097** [UI] Tabella partite con le gambe, P&L (`settled/locked/partial/open/none`), "Chiudi ora" (493), raggruppamento per partita. `MatchTradesTable.tsx` 709, `lib/omegaMatches.ts` (`groupTradesByMatch` 193, `legPnl` 150, `legKindOf` 141, `summarizeMatches` 307).
- **E2-098** [UI] Scheda di chiusura: approva/approva con prezzo/ignora/conferma live; ordinamento proposte per priorita'; anteprima di esito al prezzo. `SchedaChiusuraOmega.tsx` 326, `omegaProposte.ts` 369 (`ordinaProposteOmega` 277, `motivoNonApprovabileOmega` 149, `fetchProposteOmega` 291).
- **E2-099** [UI] Pannello manuale (E2-071/072) e missioni (E2-073). `ManualPanel.tsx` 644, `MissionPanel.tsx` 946, `MissionCard.tsx` 723.
- **E2-100** [UI] Parametri: foglio con i gruppi della whitelist + "Obiettivo"; `omegaParamsPatch` TS:1280, `obiettivoVuoto` 1269, `updateOmegaParams` 1330 (RPC `omega_activate` che SOVRASCRIVE i params: `interruttori.ts:490`, catalogo errori n. 24). `OmegaParamsSheet.tsx` 116, `pages/Omega.tsx:899-912`.
- **E2-101** [UI] Control Room: scheda del bot, interruttore uscite, esiti. `lib/interruttori.ts:141,1061,1190,1332,1385`, `W_B2EsitiOmegaSafe`.
- **E2-102** [UI] Notifiche di regolamento e curva di equity. TS `settlementNotifications` 1602, `buildEquitySeries` 1646.
- **E2-103** [UI] Realtime: `subscribeOmega` TS:1368 (debounce 1.200 ms `pages/Omega.tsx:86`), canale locale 47334 (`Omega.tsx:569`).
- **E2-104** [UI] Anteprima con dati finti (`anteprima/omegaFinto.ts` 213, `omegaMissioniFinto.ts` 93) e fotografie `fotografia/snapshot/omega.{off,v2}.json` + `.guscio.json`.

### 2.11 Banco, registro, certificazione

- **E2-105** Voce di registro: `registro_bot.py:244-253` (`nome="omega"`, `moduli_produzione=_MODULI_OMEGA` 156-162, `replay=RR:certifica_scenario`, `parametri=RR:parametri_modificabili`, `scenari=RR:SCENARI_DESCRITTI`, `controlli=Betfair.omega.certificazione`, `spec=COSTITUZIONE_OMEGA.md`).
- **E2-106** Replay sul codice di produzione: `RR:2497` `certifica_scenario`, `RR:1997-2113` `certifica_evento`, finti del banco `DbMemoriaOmega` (246-676, 431 righe), `MercatoOmega` (677-859, 183), `FeedReplay` (860-963, 104), `Sonde` (1766-1962, 197), `AmbienteOmega` (1963-1996).
- **E2-107** 20 scenari (`RR:977-1146`): `base`, `giornata-reale`, `apertura`, `paper`, `cap-stretto`, `bot-fermo`, `feed-stantio`, `esiti-ignoti`, `riavvio`, `manuale-e-bot`, `cashout-globale`, `chiuso-fuori-app`, `v4`, `v4-riavvio`, `v4-bot-fermo`, `v3`, `proposta-approvata`, `uscite-automatiche`, `rifiuti-betfair`, `chiusura-abbinata-in-parte`.
- **E2-108** 52 controlli di condotta attivi (referto 02/10): famiglie A (decisione A1-A12), B (target/obiettivo B1-B4), C (cap C1-C5), D (green-up D1-D6), E (ordini E1-E5), F (F1-F2), G (uscite G1-G4), J (J1-J7), K (consapevolezza K1-K7). `certificazione.py:283-1709`, `elenco_controlli` 1734, `verifica` 1709, `verifica_consapevolezza` 2128.
- **E2-109** Rilevatori di difetti di progettazione (stesso ordine reale ripetuto 5 volte, skip ripetuto 200): `certificazione.py:1817-1845`.

### 2.12 Parametri editabili e valori di serie (87 chiavi; duplicati Python/TS)

Sorgente Python `OC:23-323` (`_SPEC`: default, tipo, min, max) -> `DEFAULTS` `OC:332` -> `resolve_params` `OC:379` (coercizione, clamp, scambio min/max, regole G1: in V3 forza `greenup_mode='off'`, `greenup_enabled=False`, `engine='legs'`, `OC:417-420`). Copie scritte a MANO in TS: `OMEGA_PARAM_DEFAULTS` `TS:959-1053`,
`OMEGA_PARAM_GROUPS` `TS:1067-1250` (etichette, hint, min/max/step), `OMEGA_PARAM_KEYS` `TS:1258`, obiettivo `pages/Omega.tsx:899-912`, e il catalogo del banco `parametri_modificabili` `RR:2438` che finisce in `lib/replayBotCatalogo.ts`. **Verifica** (`E2_param_confronto.py`, rieseguito): 87 chiavi in `_SPEC`, 87 in `PARAM_DEFAULTS`, 87 in `GROUPS`; **0 differenze di default e di limiti oggi** - ma la parita' dipende dalla disciplina di chi edita 2 file.

Valori di serie (chiave = serie, `OC:riga`; tutti [P]):
- **Ingresso e limiti v1/v2** - `price_min`=20 (24), `price_max`=120 (25), `entry_minute_min`=30 (26), `entry_minute_max`=60 (27), `max_events`=0 (28), `commission_pct`=5 (29), `min_lay_liquidity`=5 (30), `min_stake`=0,5 (31), `include_aggregate`=False (32), `stop_on_goal`=True (33), `entry_window_source`='score' (34), `poll_interval_s`=20 (35), `max_liability_per_match`=0 (36), `daily_loss_cap`=0 (37), `max_open_liability`=0 (38).
- **Esecuzione** - `execution_mode`='auto' (42), `paper_fill_ttl_s`=45 (46), `omega_live_via_flumine`=True (51), `live_fill_deadline_s`=20 (55).
- **Modello v2** - `engine`='legs' (59), `ht_entry_min/max`=20/40 (60-61), `ft_entry_min/max`=50/80 (62-63), `model_p_max_pct`=2,0 (64), `model_min_goal_distance`=2 (65), `model_calibration`='off' (73), `model_calibration_path`='' (74), `model_empirical`='veto' (78), `model_empirical_max_minute`=60 (82), `lambda_market_grid`=True (86), `select_cost_aware`=True (89), `select_p_band_ratio`=2,0 (90), `model_use_yellow_cards`=True (92), `model_tail_factor`=1,3 (96), `lambda_live_fallback`=True (100), `lambda_quote_prima`=True (107), `model_lambda_cv`=0,30 (110), `select_k_se`=0 (113), `select_p_hedge`=0,5 (115), `select_ev_kappa`=1,0 (116).
- **Green-up v2** - `greenup_enabled`=True (118), `greenup_mode`='auto' (119), `greenup_trigger_distance`=1 (120), `greenup_price_trigger_ratio`=0,5 (121), `greenup_settle_delay_s`=30 (122), `greenup_hold_max_risk`=0,02 (123), `greenup_risk_cap`=0,15 (124), `greenup_ev_margin`=0,10 (125), `greenup_risk_premium_pct`=0,05 (129), `greenup_take_profit_frac`=0,9 (130), `greenup_take_profit_minute`=80 (131), `greenup_retry_s`=20 (132), `greenup_max_attempts`=15 (133), `greenup_market_floor_max_ratio`=3,0 (139) (tutti spenti in V3 da `OC:417-420`).
- **Respiro del DB (cache e ritmi)** - `feed_cache_s`=2 (161), `scanner_status_cache_s`=10 (168), `aggregates_cache_s`=20 (174), `sets_cache_s`=30 (180), `results_every_s`=60 (185), `missions_every_s`=5 (190), `conto_every_s`=120 (198), `events_refresh_s`=1800 (201), `idle_stats_s`=60 (204), `idle_cycle_s`=60 (211).
- **V3** - `strategy_version`=3 (221), `v3_stake_eur`=1,0 (225), `v3_modello`='gamma_poisson' (229), `v3_k_minimo`=1,11 (237), `v3_empirical_min_n`=200 (239), `v3_ht_entry_min/max`=1/44 (250-251), `v3_ft_entry_min/max`=46/85 (252-253), `v3_max_liability_per_leg`=95 (259), `v3_max_liability_per_match`=190 (260), `v3_max_open_liability`=1000 (261), `v3_daily_loss_cap`=300 (262), `v3_min_lay_liquidity`=1 (264), `v3_distanza_minima_gol`=2 (268), `v3_include_aggregate`=True (279), `v3_p_max_pct`=2,0 (293), `v3_p_min_pct`=1,0 (294), `v3_fusione_mercato`='auto' (297), `model_red_cards`=True (306).
- **Uscite** - `proposta_p_lose_max_pct`=0 (313), `uscite_protezione`='avvisa_e_proponi' (322).
- Fuori whitelist: obiettivo giornaliero `DEFAULT_DAILY_GOAL`=250 (`OC:13`, colonna `omega_control.daily_goal`, tetto 100.000 `TS:957`).

**Valori di serie con altri valori, scritti ANCHE nel codice** (dormienti ma tranelli): `OV3:115` `K_MINIMO = 2.0` (serie reale 1,11, `OC:237`); `OV3:899-904` `FINESTRE_DEFAULT` HT 25-44, FT 55-85 (serie reale 1-44 e 46-85, `OC:250-253`; il servizio passa sempre i minuti, `OS:1989`); `OV3:114` `STAKE_STANDARD`; `OP:153` file `parametri_vincenti_2026-09-16.json`; tetti di freschezza (E2 sez. 1.1) non editabili.

### 2.13 Tracciabilita' 1:1 con la Costituzione

Invarianti I1-I8 (`COSTITUZIONE_OMEGA.md:38-84`) -> E2-007 (I1), E2-038/039/040 (I2), E2-051/048 (I3), E2-032 (I4), I5 (RLS in `migrations/omega_bot.sql`, scheda G), E2-011 (I6), E2-077/081 (I7), liability aperta in UI E2-087 (I8).

---------------------------------------------------------------------------------------------------

## 3. DIFETTI STRUTTURALI

1. **Il guscio di Omega vive in altri bot.** `omega_service.py` importa `safe_strategy.execution` in 19 punti e `safe_strategy.exits` in 7 (24+6 simboli); a sua volta `safe_strategy/execution.py:221-229,1277,1773` riusa il SERVIZIO di Omega (gate flumine, `enqueue_place`
   "PORT fedele"). `omega_proposte.py` <-> `omega_service.py` si importano a vicenda (8 + 3 punti). Non si puo' sostituire Omega senza toccare Safe e viceversa (`00_INVENTARIO.md`: cicli). Conteggi: `grep -c` indicati in 1.2.
2. **Il client Betfair di tre bot sta nella cartella di uno** (`OMK` 1.794: Mike 12 import, Safe 3 siti, banco 5) e Mike **rilega una costante di modulo** per marchiare i propri ordini (`mike/service.py:142-143`), difesa raddoppiata da `strategy_ref=` (`:159`). Con tre processi separati regge; con due bot nello stesso processo (futuro runtime unico) marchierebbe gli ordini dell'altro.
3. **Whitelist dei 87 parametri scritta 4 volte** a mano: `OC:23-323`, `TS:959-1053`, `TS:1067-1250`, catalogo del banco -> `replayBotCatalogo.ts` (11.099 righe, 20 menzioni di Omega) piu' le etichette di attivita' (`TS:395-703`: 126 chiavi che rispecchiano i 62 kind Python). Oggi 0 differenze (misurato); nessun test di contratto che le obblighi a restare uguali. Catalogo errori n. 33 ("costante nel frontend che duplica una scelta del backend").
4. **Tre serie di default diverse per la stessa cosa** (finestre, k, stake): `OC` / `OV3:115,899` / `OS` (`_v3_finestra` `OS:1532`). Vince `OC` perche' il servizio passa sempre i valori, ma chi chiamasse `V3` senza parametri (strumenti `misura_punto8`, `o5_rossi.py`) userebbe 2,0 e 25-44.
5. **Il finto del banco non ha la firma del vero** (catalogo errori n. 27 e n. 21): `DbMemoriaOmega.aggregates(self, day_start=None)` e `aggregates_coppia(self, day_start=None)` (`RR:609,615`) non hanno `mode`, mentre `omega_db.aggregates(day_start=None, mode=None)` e `aggregates_coppia(day_start=None, mode=None)` (`ODB:777,787`).
   Risultato: ogni referto di Omega del 02/10 apre con `CRITICAL:omega.service:[omega] il lettore degli aggregati non separa le modalita': paper e live SOMMATI nelle decisioni (catalogo 7.21)` (`OS:427`, `_con_modalita` `OS:409-431`; in `omega_base_MASTER_parita.txt` e `_runner.txt`, riga 1):
   il percorso "aggregati per modalita'" (`OS:380-405`) NON e' esercitato dal replay. **Il replay certifica una condotta diversa da quella di produzione su questo punto.** Non l'ho corretto (perimetro: solo documenti); e' un lavoro per il banco (H).
6. **Strategia e guscio mescolati nello stesso file**: in `omega_service.py` 1.837 righe di regole (20,6%) fra 6.716 di guscio; `_scan_event_legs` (155 righe) intreccia finestre, flusso, ritenti, mercato, ordine, conteggio partita. Una regola non si legge senza attraversare il guscio. Le funzioni gia' pure sono poche: `OV3.valuta_runner`, `OE.seleziona_v3`, `OP.esito_uscita_al_prezzo`; `OP._una_gamba` e `_v3_select` leggono DB/mercato/servizio.
7. **Motori legacy vivi**: 1.023 righe in `OS` (v1 207, `_model_select` 107, green-up v2 709) piu' `select_by_model`/`cover_cost` in `OM` e `select_lay_runner`/`is_eligible`/`legs_remaining` in `OE`, raggiungibili con `strategy_version=2` (`OC:221`) e coperti da 3 scenari del banco. In V3 il green-up e' forzato OFF da `OC:417-420` ma i 14 parametri `greenup_*` restano editabili in UI (TS:1067-1250): la UI espone controlli che `resolve_params` annulla.
8. **Rete sincrona nel percorso di decisione**: RPC `get_omega_ht_ft`/`get_omega_minute_ft` dentro `_model_select`/`_v3_p_empirica` (G-035; cache 6 h, `OS:106,1313-1374`), `list_today_football_events` x444 in 438 giri (referto 02/10), riserva `insert_trade` prima dell'ordine, aggregati RPC (cache 20 s). Contro il requisito §9.3 (nessuna rete tra messaggio e decisione), gia' rilevato in D §1.5.
9. **Copie del guscio**: `ferma_al_nuovo_avvio` (mike 3964, omega 7966, safe 10083), `_avvia_sveglia`, `_avvia_canale`, `_ciclo_persistente`, `_pubblica_stato`, `_chiudi_all_arresto`, `_control_per_canale`, `_Cache`, `_richiesta_non_di_questa_riga` (omega 5943 ~ safe 3469, 0,98), `_uscita_del_bot_approvata` (omega 5891 ~ safe 3829, 0,80), `_acquire_single_instance_lock` copia propria `OS:8563` (esiste `stream/single_instance.py`, 36 righe): tabella completa in D §1.3 (~284 righe ridondanti). `reconcile_pending` Omega 128 righe + `poll_flumine_pending` 87 ~ 330 con `OE:718`, una delle 3 copie (C R5).
10. **Paper "a due velocita'" nel banco**: lo scenario `paper` del banco registra `skip paper_runner_non_disponibile x5` perche' il banco non ha il runner per il paper (`OMEGA_APERTURA_35760084.md` §6-bis, reperto RB-4): l'esecuzione paper di Omega non e' esercitata come in produzione.
11. **Regressione scoperta solo ricontrollando il numero di azioni** (29/09 -> 07/10): il referto del 29/09 diceva "Omega 13 OK" senza confrontare le azioni col 25/09; Omega e' rimasto cieco per tutto il 2T (438/0 invece di 467/2) fino al 07/10 (`OMEGA_APERTURA_35760084.md` §0, §1). Lezione per la parita' di §5.

---------------------------------------------------------------------------------------------------

## 4. DOMANI

### 4.1 Struttura (UNA cartella, UN contratto, UN `COSA_FA.md`)

```
bots/omega/
  COSA_FA.md                  # E2-001..E2-109 in italiano per l'utente (derivato da questa scheda)
  parametri.py                # UNICA fonte dei 87 parametri (tipo, serie, min, max, etichetta, gruppo, hint)
  strategia/                  # [S] INVARIATA riga per riga
    v3.py  (= omega_v3.py 1.248)   uscita.py (= OP strategia 446)   selezione.py (= OE strategia 403 + OV3 glue)
    catena_lambda.py (= OS 1138-1396)   ingresso_v3.py (= OS 1397-1770 e 1880-2094 depurati dal guscio)
    sizing.py (= OS 2355-2427)   legacy_v2_v1/ (= 1.023 + OM.select_by_model: da decidere, sez. DECISIONI)
  missioni/                   # [M] omega_advisor 400 + OS 7369-7751
  plugin.py                   # adattatore Decisore (~350 righe stimate)
  test_contratto.py           # generico del runtime: uscite di serie MANUALI, stato ricostruibile, parametri nel catalogo, fasi
  replay/                     # scenari e controlli di Omega (certificazione.py) - perimetro scheda H
```

Il resto sparisce da qui e va nei componenti condivisi: `runtime/` (D), `nucleo/mercato_betfair` (A + C), `nucleo/modello_gol`, `nucleo/contabilita_ordine` (C/F), accesso dati (G).

### 4.2 Contratto (si appoggia a `D_RUNTIME_BOT_CONTRATTO.md` §4.2: `Plugin`, `Decisore`, `Esito`, `Intento`, `Quadro`, `Libro`, `Parametri`, `Prematch`, `Cadenza`)

```python
class OmegaDecisore(Decisore):
    nome = "omega"; sport = "calcio"
    def catalogo_parametri(self) -> Sequence[Mapping[str, Any]]: ...   # 87 chiavi da parametri.py (genera TS defaults, gruppi UI, catalogo banco)
    def uscite_di_serie(self) -> UsciteModo: return "MANUALE"          # = 'avvisa_e_proponi' (OC:322)
    def chiave_uscite(self) -> str: return "uscite_protezione"         # automatico <-> AUTOMATICO
    def arma(self, event_id: str, prematch: Prematch, stato: StatoOmega | None) -> StatoOmega: ...
        # ricostruisce traded_legs/gambe_fallite/celle bancate da omega_trades (oggi OS:2095, 8350-8353, 1711)
    def osserva(self, stato, libri: Mapping[str, Libro], quadro: Quadro, orologio: Orologio,
                p: Parametri, prematch: Prematch) -> Esito: ...
        # = _scan_event_legs + _v3_select + _size_and_place SENZA I/O: libri["CORRECT_SCORE"], quadro.minuto/punteggio/rossi/fase,
        # prematch.dossier(event) -> lambda e FONTE, prematch.tabella_empirica(lega) -> (P, n)  [oggi RPC sincrona, G-035]
        # Intento("piazza", {lato:'LAY', selezione, prezzo, stake:1.00, gamba:'ht_cs'|'ft_cs', audit:{...}}, ref=...)
    def fine_giro(self, stati, p, orologio) -> Mapping[str, Esito]: ...  # stop_on_goal, daily_loss_cap, cap partita/aperto con gli aggregati per MODALITA'
    def su_fase(self, stato, fase, orologio) -> Esito: ...                # proposte di uscita (OP._una_gamba) + risultati 1T/2T
    def su_comando(self, stato, comando, p) -> Esito: ...                 # place, cashout, approva_uscita, riprendi_evento, missioni
    def su_esito_ordine(self, stato, ordine, orologio) -> Esito: ...      # fill/parziale/rifiuto: oggi poll + reconcile (OS:3670-4465)
    def cadenza(self) -> Cadenza: return Cadenza("giro", 20.0, 60.0, True, 5.0)   # poll_interval_s, idle_cycle_s, sveglia_su_prezzo, GIRO_MINIMO_CANALE_S
```
Eventi esposti dal bot al runtime: `Intento` `piazza` (E2-001/002/025/026), `proponi_uscita` (E2-059), `chiudi` (E2-064/067/069), `annulla` (E2-076), `diario` (i 62 kind, E2-092), `allarme` (E2-093).
Eventi consumati: libro CS/HT (stream in-process, A), `Quadro` (fase/minuto/punteggio/rossi), esiti ordine (C), comandi UI (`approva_uscita`, `cashout`, `place`, `riprendi_evento`), tabella empirica e dossier (`Prematch`, G).
**Prerequisiti di purezza** (lavoro, non decisione): `_v3_select` e `_una_gamba` oggi leggono DB e servizio: i dati che prendono (lambda, tabelle, aggregati, prezzi) passano da `Prematch`/`Quadro`/`stato`; `_log_dedup` (600 s) e `_LAMBDA_CACHE` (900 s) usano l'`Orologio` iniettato.

### 4.3 Dove vive ogni funzionalita' domani

| Funzionalita' | Domani |
|---|---|
| E2-001..029, 030..037 (decisione V3 e legacy), 059..062, 066, 067 (uscite: calcolo) | `bots/omega/strategia/` (identiche) |
| E2-038..050 (paper/live, coda, porta, place-and-trim, riconciliazione, orfani, catena) | porta ordini unica C; il bot emette solo `Intento` |
| E2-051..058 (regolamento, risultati, aggregati, obiettivo, eventi) | F (regolamento) + G (aggregati/eventi) |
| E2-063, 064, 068..070 (interruttore uscite, approva, cashout manuale/globale) | `runtime/controllo.py` + `Parametri.uscite` (mappa `chiave_uscite`); esecuzione dalla porta C |
| E2-071..076 (manuale, missioni, chiuso dall'utente) | `runtime/comandi.py` (D-034..D-040) + `bots/omega/missioni/` |
| E2-077..091 (ciclo, controllo, avvio, cadenza, sveglia, cache, stats, arresto, lock) | `runtime/{cicli,controllo,battito,arresto,lock}.py` (D 4.3) |
| E2-092..095 (diario, allarmi) | `runtime/diario.py`; i 62 kind e le etichette UI da UNA tabella generata |
| E2-096..104 (UI) | J: pannello DERIVATO dal Plugin (catalogo parametri, stati, attivita') |
| E2-105..109 (banco) | `Registro` unico (D) + H |
| `OMK`, `OM`+`OEMP`, 8 simboli `OE` | `nucleo/mercato_betfair` (A+C), `nucleo/modello_gol`, `nucleo/contabilita_ordine` |

### 4.4 Stima delle righe DOPO (metodo: righe oggi per fascia 1.3/1.4 - cosa si sposta - cosa sparisce perche' ripetuto)

| Blocco | Oggi | Domani in `bots/omega/` | Dove va il resto |
|---|---:|---:|---|
| Strategia (V3, uscita, selezione, catena lambda, sizing, config) | 4.896 | **4.896** (intoccabile; `omega_config` si trasforma in `parametri.py`: i 87 valori NON cambiano) | - |
| Missioni (OS 383 + OAD 400) | 783 | **783** | - |
| Guscio `omega_service.py` | 6.716 | ~**350** (plugin) | runtime D 2.033 (OS 1-250, 251-848, 7752-8936: conteggiate nella stima 3.510 di D, dove il contributo di Omega e' quello); dati/A 398 (849-1137, 1771-1879); porta ordini C 2.844 (2095-2354, 2635-4970, 6924-7171: `reconcile_pending`, flumine, paper, catena, greenup send); regolamento F 454; comandi/cashout D+C 987 (5425-6411) |
| Guscio `omega_engine.py` (contabilita', riconciliazione, regolamento, paper_fill) | 698 | 0 | C/F (`nucleo/contabilita_ordine`) |
| Guscio `omega_proposte.py` (scrittura, esecuzione automatica) | 529 | **529** (formato e ciclo di vita della proposta sono di Omega) | eventuale taglio: lo dira' la scheda F |
| `omega_db.py` | 1.081 | 0 | G (accesso generato dallo schema: 3 copie `omega_db`/`bot_db`/`mike/db` ~3.687 righe) |
| `porta_ordini.py` | 237 | 0 | C |
| Condiviso `OM`+`OEMP` | 1.431 | 0 | `nucleo/modello_gol` (1.431: stessa riga, UNA casa) |
| Condiviso `OMK` | 1.794 | 0 | A (959) + C (834): i tagli sono delle loro schede |
| Non classificato (costanti, import) | 490 | ~150 | resto sparisce con le spostate |
| **Totale cartella Omega** | **18.655** | **~6.700** (4.896 + 783 + 350 + 529 + ~150) | 11.955 righe migrano nei componenti comuni, dove le schede A, C, D, F, G stimano le proprie riduzioni |

**Calcolo e onesta'**: nella MIA scheda i tagli reali sono solo (a) il guscio che coincide con il runtime unico di D e (b) i 24+6 simboli di Safe che Omega non dovra' piu' importare; il resto e' un TRASLOCO verso cartelle condivise. Ridurre
`omega_service.py` da 8.936 a ~6.700 nella cartella e' uno spostamento (-36% della cartella), non una cancellazione di funzioni: la riduzione netta di righe del sistema dipende da D (runtime scritto una volta: -53% sullo scheletro, D §4.4) e da C
(`reconcile_pending` 3 copie -> 1). **Strategia + missioni = 5.679 righe restano identiche**: la strategia e' il 85% di quanto resta in cartella. Altro: i 3 file di default dentro `OV3` (D4 sopra) spariscono (-~25 righe), 4 whitelist -> 1 fonte (TS defaults+gruppi
`TS:959-1250` = ~292 righe generate; `OC` -> `parametri.py`).

### 4.5 Criterio §9.1: per sostituire Omega

**OGGI tocco** (tutti fuori dalla cartella tranne i primi): `Betfair/omega/` (12 moduli di produzione + `certificazione.py` + `tools/replay_registrazioni.py` + `tools/misura_k.py`) **e** `Betfair/safe_strategy/execution.py` (19 import, 24 simboli) e `exits.py` (7 import, 6 simboli),
`safe_strategy/arresto_bot.py` (`OS._flumine_enqueue_cancel`), `bot_service.py` (`_os`, `_omega_market`, `_MercatoSafe`), `Betfair/mike/service.py` (12 import di `omega_market`, `_RealMarket` 131-302) e `mike/db.py:629`, `mike/dossier.py` (modello+tabelle), `safe_strategy/opportunity.py` e `bot_db.py:926-942`,
`registro_bot.py:156-162,244-253`, `avvio_app.py:182,199`, `desktop/main.js:446-450,249-294`, 20 migrazioni `omega_*.sql`, il frontend (8 file in `lib/`+`pages/`+`components/` = 7.499 righe, piu' `interruttori.ts`, `controlRoom.ts`, `dailyHistory.ts`, `replayBotCatalogo.ts`, 5 fotografie), il banco (`banco_comune.py` `OM`/`PlaceRifiutato`, `trasporto.py`, `trasporto_rapido.py`, `proposte_modello.py`). **Almeno 12 aree fuori dalla cartella del bot**, tre delle quali sono altri bot.
**DOMANI tocco solo** `bots/omega/` e i suoi test di contratto (`test_contratto.py` generico + gli scenari del banco di Omega). Registro, avvio, menu del banco e pannello UI si derivano dal Plugin; Mike e Safe non cambiano perche' importano `nucleo/*`.

### 4.6 Gia' in una libreria matura e oggi riscritto

- **flumine**: ciclo ordini e fill del PAPER -> Omega li riscrive: `OE:271-335` `paper_fill`, specchio paper in RAM `OS:4269-4319` (`_ricorda_ordine_paper`), poll e riconciliazione manuale `OS:3670-4465` (~800 righe) invece di `process_orders`/blotter (la scheda D 4.5 lo dice per Omega/Mike/Safe; `Mike _segui_ordini_paper_su_runner` 229 righe e' il gemello). In produzione il paper passa gia' dal runner (E2-039): resta il codice del ripiego e il suo specchio.
- **betfairlightweight**: login/keepalive/retry `OMK:62-150` (`get_client`, `call`, `call_mutating`, `keep_alive`) e `OS:8541` (`_maybe_keepalive`): tre copie di una chiamata di libreria (D §4.5); `list_current_orders`/`list_cleared_*` `OMK:1565-1706` sono wrapper normalizzatori (A/C).
- **Tick ladder**: `OE:24-90` (`_LADDER`, `round_to_tick`, `tick_up/_down`) - esiste utilita' equivalente in flumine/bfl: **non verificato** su libreria installata (nessun accesso a pacchetti in questa sessione).
- **Cache con TTL**: `_Cache` `OS:169-185` e 10 cache a dict di processo (`OS:194-241`) - sostituibili da una cache standard (`cachetools.TTLCache`): non e' una libreria del progetto oggi (non verificato nei requisiti).
- **Single instance lock**: `OS:8563` contro `Betfair/stream/single_instance.py` (36 righe, gia' nel repo).

---------------------------------------------------------------------------------------------------

## 5. PARITA'

**Criterio** (`PROCESSO_STANDARD_BOT.md` §3, regola dell'utente): stessa identica cosa, **numero per numero**, sulle registrazioni reali, con il codice di produzione e DOPO ogni tappa; il referto di oggi si confronta con quello PRECEDENTE (decisioni E azioni E tick E chiamate al mercato), non solo "OK".

### 5.1 Registrazioni e scenari gia' usati per Omega

- Registrazioni in `_live_raw/` (83 voci, `ls _live_raw | wc -l`): **35760084** (in gioco 16:00:25, 483.985 tick, 21 mercati nel catalogo ricostruito) e **35797769** (referto 07/10); `registrazioni_banco/` ha 35760084, 35797769 e un `LEGGIMI.md`.
- Comando unico: `python -m Betfair.stream.backtest.certifica omega 35760084 --scenari base|apertura|tutti` (referto: `AUDIT_2026-10-02/replay/omega_base_MASTER_parita.txt`, `_runner.txt`, 135 righe ciascuno; `AUDIT_2026-10-07/OMEGA_APERTURA_35760084.md`; referti 07/10 in `AUDIT_2026-10-07/omega_apertura_35760084/replay/`).
- Strumenti del 07/10 riusabili: `strumenti/sonda_modello.py`, `sonda_flusso.py`, `muta.py`, `falsifica.sh`.

### 5.2 Numeri che DEVONO coincidere (da questi referti; non rieseguiti da me)

| Scenario | Numero | Valore di riferimento | Fonte |
|---|---|---|---|
| `base` 35760084 (v2 dichiarato, 02/10) | decisioni / azioni / tick | 438 / 0 / 483.985; `ht_cs:no_runner_by_model x59`; `skip x2`, `flusso_non_dichiarato x1`; chiamate al mercato `list_today_football_events x444`; 50,4 s, 9.594 tick/s; 52 controlli attivi; 1 partita senza violazioni | `omega_base_MASTER_parita.txt` |
| `base` dopo la correzione 07/10 | idem | 438 / 0, ora `ft_cs:no_runner_by_model x75` (la 2T si valuta) | `OMEGA_APERTURA...md` §6-bis |
| `apertura` 35760084 | decisioni / azioni / tick / chiamate | **467 / 2 / 482.034**; `list x473`, `read_market x108`; lay '3 - 3' @300 al 52' (3-0), vinta, +5,00 EUR (5,26 EUR di stake nello scenario con obiettivo 5); le 2 azioni = 1 ordine + il suo regolamento | `OMEGA_APERTURA...md` §1, §6 |
| `apertura` 35797769 | decisioni / azioni | 686 / 0; `ft_cs` valutata x79, `ht_cs` x56; `flusso_interrotto x1`; 89 s | idem §6-bis |
| `--scenari tutti` 35760084 | esito | **20/20 OK, 0 violazioni**; 435 s (dopo) / 458 s (prima) | idem §6-bis |
| 13 scenari col motore di serie | valutazioni | `ht_cs` x121 + `ft_cs:nessun_candidato` x56 (dopo il 07/10) | idem |
| `v3` (cancello del 16/09) | valutazioni | `ht_cs` x53 + `ft_cs` x56 | idem |
| `manuale-e-bot` | decisioni / azioni | 467 / 1 | idem |
| `paper` | skip | `paper_runner_non_disponibile x5` (reperto RB-4, limite del banco) | idem |

**Da far coincidere dopo ogni tappa**: decisioni, azioni (ordini + regolamenti + green-up + missioni, `RR:1422-1424`), tick, `read_market`/`list_*` per tipo, righe `omega_trades` per stato, `motivi dichiarati`, gambe aperte per fase, scartati per cella (i 14 cancelli di 2.2, con i numeri `margine Nx, ne serve Ky`), importi e prezzi dei fill, P&L lordo/netto, istanti (minuto della decisione), `exit_kind`/`exit_reason`, numero e testo delle attivita' per kind (62).
Aggiungo (nuovo, da costruire): un confronto **decisione per decisione** (stesso `Quadro`+`Libro`+`Prematch` -> stesso `Esito`) fra il codice di oggi e `OmegaDecisore.osserva`, sugli stessi tick (periodo ombra, sez. 6).

### 5.3 Fotografie UI e golden

`frontend/src/fotografia/snapshot/omega.off.json`, `omega.v2.json` (+ `.guscio.json`), `lib/omegaUscita.golden.json` (527 righe: oro dell'uscita Python vs TS, `omegaUscita.test.ts`, generatore `Betfair/omega/tools/genera_oro_uscita.py`), `lib/__fixtures__/replay_pro/esito_omega_apertura_84.json`.
Test: 39+35 file di test Python (27.049 righe, ~1.300 test) e 17 file di test frontend (5.432 righe), tra cui i contratti `test_omega_ui_contratto_2026_09_11.py`, `test_omega_allineamento_ui_2026_09_15.py`, `omega.cert.test.tsx`, `Omega.certificazione.test.tsx`.

### 5.4 Voci di `PROCESSO_STANDARD_BOT.md` coperte

- **§6.1** dati di mercato: stream registrato 35760084/35797769 (E2-013, 014). **§6.2** scanner vero: 434 righe di scan scritte dallo scanner VERO, 299 letture del feed di Omega (referto 02/10). **§6.3** servizio intero a cadenza reale: giri `run_once` 438 (poll 20 s, a vuoto 60 s). **§6.4** ciclo di vita dell'ordine con parziali e bet delay: scenari `esiti-ignoti`, `rifiuti-betfair`, `chiusura-abbinata-in-parte`, `riavvio`; controlli K1-K7 (E2-108). **§6.5** persistenza e UI: righe `omega_trades` scritte, fotografie 5.3. **§6.6** concorrenza e limiti: `cap-stretto`, `bot-fermo`, `manuale-e-bot`, `chiuso-fuori-app`. **§6.7** scenari e falsificazione: 20 scenari + 8 mutazioni del 07/10 (M1-M8: 7, 3, 3, 1, 1, 2, 1, 1 test rossi, `OMEGA_APERTURA...md` §4). **§6.8** referto riproducibile: impronta del codice `ff8f89cbccdc (13 file)` / `819f2cfabdc6` e ambiente dichiarato nei referti. **§6.9** velocita': `--scenari tutti` 435-458 s = **7,3-7,6 min: sopra l'obiettivo di 5 min, sotto il tetto di 10** (`certifica` stampa "obiettivo 300 s, tetto 600 s"): va dichiarato all'utente prima di lanciare.
- **§7 catalogo** - copre (controlli K, scenari): 1-7 (consapevolezza dell'ordine: K1-K7, F2, J1-J7), 8-16 (simulazione: banco comune), 17 (sospeso/chiuso: `market_not_open`, B4), 18 (CHECK DB, `omega_trades_status_cancelled_lapsed_2026-09-17.sql`), 19 (stato in RAM al riavvio: scenari `riavvio`, `v4-riavvio`), 21 (paper+live sommati: **NON coperto dal replay**, vedi difetto 5), 22 (bot che riparte da solo: `ferma_al_nuovo_avvio`, scenario `bot-fermo`), 23 (stats che cancellano l'impronta d'avvio: `_GUARDIA_AVVIO.timbra`), 24 (RPC `*_activate` con `coalesce`: `interruttori.ts:490`), 26 (`execution_mode='rest'`), 33 (costante nel frontend che duplica il backend: difetto 3), 34 (fase di protezione dopo la riconciliazione: `_fasi_di_gestione` `OS:8035`), 36 (K: consapevolezza). **Da dichiarare ⊘ o da aggiungere**: 21 (firma del finto `aggregates`), 25 (modalita' per strategia), 27 (finti con chiavi/tipi del vero), 29-30 (mutazioni delle regole V3: k, p_min, p_max, distanza: da fare), 35.
- **Falsificazione obbligatoria dei test nuovi** (per la futura tappa): mutare (a) `v3_k_minimo` 1,11 -> 1,10 (deve diventare rosso A10), (b) `v3_p_max_pct` 2 -> 3 (A3/A10), (c) il gate `distanza_minima_gol` (A11), (d) `uscite_protezione` fail-open (G1/G4), (e) togliere l'esclusione della cella gia' bancata (E2-005), (f) `aggregates(mode)` ignorato (21): ognuno deve far diventare rosso almeno un controllo del banco.

---------------------------------------------------------------------------------------------------

## 6. MIGRAZIONE

Ordine rispetto agli altri componenti: **dopo** A (stream in-process e `nucleo/mercato_betfair`), C (porta ordini unica, `reconcile`) e D (`runtime/` + `Plugin`), **prima** di J (pannello derivato). Omega e' il bot a rischio minore (V3 con stake 1 EUR; "fermo il 02/10", G T10) e il suo guscio e' la fonte principale del runtime: e' il candidato naturale a primo bot calcio migrato dopo Mike-paper.

1. **Passo 0 - referto zero** sul codice di oggi: `certifica omega 35760084 --scenari tutti` e `... 35797769 --scenari apertura` (e `base`), commit del referto con l'impronta del codice; dichiarare all'utente i 7,5 min.
2. **Passo 1 - spostamento senza cambiare il comportamento**: `nucleo/modello_gol/` (OM+OEMP) e `nucleo/mercato_betfair/` (OMK) con RE-EXPORT dai vecchi percorsi (`Betfair.omega.omega_model`, `omega_market`) cosi' Mike, Safe e banco restano verdi; stesso referto numero per numero. Eliminare la riassegnazione di `CUSTOMER_STRATEGY_REF` (E2 sez. 3.2) SOLO con il test K del ref per attore (`tests/test_ref_strategia_per_attore_r1_2026_09_24.py`).
3. **Passo 2 - catalogo unico dei parametri**: `parametri.py` genera TS defaults/gruppi e il catalogo del banco; test di contratto "generato = scritto" (oggi 0 differenze, `E2_param_confronto.py` diventa un test); nessun valore cambia (condizione dell'utente).
4. **Passo 3 - purificare la strategia**: estrarre `ingresso_v3`/`uscita` come funzioni pure `(stato, libri, quadro, orologio, parametri, prematch) -> Esito`; i dati oggi letti dal DB entrano da `Prematch`. **Periodo ombra con confronto automatico**: il banco esegue il percorso vecchio e il nuovo sugli stessi tick e confronta `Esito` decisione per decisione (stessa cella, stesso prezzo, stesso stake, stessi scartati con gli stessi numeri). Interruttore: variabile d'ambiente per bot, SPENTA di serie; il bot lo accende solo l'utente.
5. **Passo 4 - guscio sul runtime**: `plugin.py` (350 righe) sostituisce `omega_service.py` 1-1137 e 7752-8936; ordini e riconciliazione sulla porta C (E2-038..050 spariscono da Omega); regolamento su F. Ogni sotto-passo con referto identico.
6. **Passo 5 - taglio del vecchio**: via `omega_service.py`, `omega_db.py`, `porta_ordini.py`, shim di re-export (dopo aver aggiornato Mike/Safe a `nucleo/*`), solo dopo ALMENO un giorno di **paper** in cui replay e paper coincidono, e solo con la firma dell'utente per il live (regola: «prima chiedi se e' certificato sul replay»; oggi Omega e' certificato sui 20 scenari del 07/10 su UNA registrazione completa, non su un paper recente).
7. **Rischi**: (R1) il ciclo `execution.py` <-> `omega_service.py` va rotto PRIMA (C e F); (R2) il replay NON esercita il percorso aggregati-per-modalita' e il paper-con-runner (difetti 5 e 10): rischio di migrare una condotta non certificata; (R3) la regressione del 29/09 dimostra che "OK" non basta: serve il confronto numerico di 5.2; (R4) 11,1k righe di `tools/` e 27k di test importano i vecchi percorsi (`o1_catena_lambda.py`, `o5_rossi.py`...) e vanno aggiornati con gli shim; (R5) nessun processo nuovo senza permesso.
8. **Ritorno indietro**: lo shim e l'interruttore ombra permettono di tornare al percorso vecchio con una variabile d'ambiente per bot; `git revert` per passo (un commit per passo, mai `git add -A`); le migrazioni SQL non toccano i dati di Omega (nessuna migrazione prevista da questa scheda).

---------------------------------------------------------------------------------------------------

## 7. MISURE

| Cosa | Oggi (fonte) | Obiettivo dopo | Strumento |
|---|---|---:|---|
| Righe cartella Omega (12 moduli produzione) | 18.655 (`wc -l`) | ~6.700 (4.4) | `E2_omega_righe.py` |
| `omega_service.py` | 8.936; S 20,6 % | non esiste; plugin ~350 | idem |
| Importazioni di `safe_strategy` dentro Omega | 19 + 7 punti, 30 simboli (`grep -c`) | 0 | `grep -c` |
| Moduli di Omega importati da Mike/Safe/banco | `omega_market` (3+12+5 siti), `omega_model`, `omega_engine` (8), `omega_empirical`, `omega_db` | 0 (solo `nucleo/*`) | `grep -rn "from Betfair.omega"` |
| Whitelist dei 87 parametri | 4 copie a mano (0 differenze) | 1 fonte | `E2_param_confronto.py` |
| Richieste al DB al minuto | ~12,7 (04/10, G/07 §4.2); `omega_trades` GET 5,6 | non peggiorare; RPC sincrone nel ciclo = 0 (G-035 -> prefetch in memoria) | **da scrivere**: contatore di chiamate DB per giro sul `DbMemoriaOmega` (`RR:246-676`) |
| Rete nel percorso critico | 3 punti (REST eventi, RPC empiriche, riserva `insert_trade`) | 0 REST/RPC tra feed e decisione | test "rete finta che rifiuta tutto" (G 6) |
| Latenza giro (`run_once`) | non misurata per fase | n.m. | **da scrivere**: profilo `cProfile` di `run_once` nel replay (gia' 9.594 tick/s) |
| Replay completo | `--scenari tutti` 435-458 s; `base` 50,4 s | <= 300 s (obiettivo §6.9) | `certifica` stampa il tempo; profilo del banco |
| Memoria / CPU del servizio | non misurate | n.m. | `psutil` su `omega_service` (lettura, richiede permesso) |
| Frontend Omega | 7.499 righe non-test | defaults+gruppi generati (-~290) | `wc -l` |

---------------------------------------------------------------------------------------------------

## DECISIONI PER L'UTENTE

1. **Motori legacy v1 e v2** (1.023 righe in `omega_service.py` + `select_by_model`/`cover_cost` in `omega_model.py` + helper in `omega_engine.py`; coperti da 3 scenari): tenerli, spostarli in `legacy/`, oppure ritirarli? Ritirarli toglie il kill-switch `strategy_version=2` (`OC:221`) e 14 parametri `greenup_*` + 20 di v2 dalla UI: **non cambia alcuna decisione di V3**, ma e' una funzione che l'utente ha oggi. Non lo faccio di iniziativa.
2. **Obiettivo giornaliero 250 EUR con stake fisso 1 EUR**: `stop_on_goal` e `daily_goal` (`OS:1898`) valgono anche per V3 (il controllo precede il ramo V3). Osservazione, non proposta di modifica: confermare che e' voluto.
3. **Default duplicati nel codice con valori diversi** (`OV3:115` `K_MINIMO=2.0`, `OV3:899` finestre 25-44/55-85): allinearli a `OC` (o toglierli) NON cambia le decisioni di produzione (il servizio passa sempre i valori, `OS:1989`, `OS:1646`), ma cambia cosa calcolano gli strumenti `misura_punto8` e le sonde chiamate senza parametri. Serve il permesso.
4. **Il finto del banco senza `mode`** (difetto 5): correggere `DbMemoriaOmega.aggregates(...)` per accettare `mode` cambierebbe i referti di Omega (togliendo il CRITICAL, esercitando il percorso per modalita'). Va fatto dal banco (H) con referto prima/dopo.
5. **Dove vive `omega_market`**: oggi "di Omega" ma usato da 3 bot; spezzarlo fra A e C (proposta 1.5) tocca il file piu' condiviso del sistema: chiedere conferma sull'ordine (dopo C).
6. **I 62 kind di attivita' e le 126 etichette TS**: generarle da una tabella unica significa scegliere un solo testo italiano per kind (oggi i testi sono nel frontend `TS:395-703`): confermare che le etichette in UI non cambiano.

## COSA HO VERIFICATO DI PERSONA / COSA NON HO POTUTO VERIFICARE

**Verificato** (letto o misurato in questa sessione): righe con `wc -l` su tutti i file di 1.1; mappa di `omega_service.py` dall'indice delle `def` e `E2_omega_righe.py` (rieseguito); `omega_config.py` letto per intero (87 chiavi) e confrontato con `omega.ts` da `E2_param_confronto.py`
(0 differenze, rieseguito); `omega_v3._seleziona` (cancelli con riga), `omega_service._v3_select`, `_scan_event_legs`, `scan_and_place_legs`, `_size_and_place`, `_greenup_decide`, `process_manual`, `ferma_al_nuovo_avvio`, `_fasi_di_gestione`, `_con_modalita`, `omega_model.select_by_model` (cancelli), `omega_engine` (sizing, `is_eligible`, `seleziona_v3`), `omega_proposte` (costanti, `process_proposte_uscita`);
grep degli import di Omega in tutto il repo (Mike, Safe, banco, strumenti); `RR:609,615` contro `ODB:777,787` (firma dei finti); referti `omega_base_MASTER_parita.txt`/`_runner.txt` (testa e coda) e `OMEGA_APERTURA_35760084.md` (§0-§6-bis); catalogo §7 di `PROCESSO_STANDARD_BOT.md`; schede D, C, G (righe su Omega).

**Non verificato**: (1) l'interno di `_place_one` (2709-3019), `_manual_place` (5514-5849), `_manual_cashout` (6014-6216) e dei 29 `_greenup_*` oltre `_greenup_decide`: le funzionalita' E2-040..050, 064, 067-072 sono descritte dai nomi, dagli indici, dalle docstring e dalle costanti, non riga per riga; (2) i referti del 07/10 `FINALE_*.txt`/`DOPO_*.txt` non sono stati riaperti: i numeri 467/2, 686/0, 20/20, 435/458 s sono citati dal documento `OMEGA_APERTURA_35760084.md`;
(3) il contenuto riga per riga di `certificazione.py` (52 controlli: da referto e dall'indice delle `def`); (4) `odb`: non ho eseguito RPC ne' letto il DB; (5) l'uguaglianza Python/TS di `esito_uscita_al_prezzo` (garantita dal golden `omegaUscita.golden.json`, test non rieseguito); (6) le equivalenze con flumine/bfl/cachetools (4.6): nessun accesso alla documentazione delle librerie;
(7) la differenza fra "13 file" del referto e i 12 nomi di `_MODULI_OMEGA` (`registro_bot.py:156-162`) non e' spiegata; (8) le fasce di 1.3 e le colonne di 1.4 sono un mio giudizio di ruolo (rieseguibile cambiando le liste in `E2_omega_righe.py`); (9) frequenze DB, memoria, CPU e latenza per fase: non misurate (7, strumenti proposti); (10) il perimetro frontend esclude le parti di Omega dentro moduli comuni.
