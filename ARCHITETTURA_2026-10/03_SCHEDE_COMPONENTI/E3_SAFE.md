# SCHEDA E3 - SAFE STRATEGY (calcio e tennis; base, esatto, punta, tennis, opportunita', anomalie, combo) + SCANNER del feed `safe_strategy_scan`

Data: 08/10/2026. Autore: delegato Sonnet (piano di architettura 2026-10). Solo documento: nessun codice toccato.
Perimetro (righe con `wc -l` il 08/10, file tracciati):

- Python `Betfair/safe_strategy/` (26 file `.py`, 34.635 righe in totale; di cui 3.786 sono i controlli del banco
  `certificazione*.py`): `bot_service.py` 11.136, `service.py` 3.444 (SCANNER), `execution.py` 3.093, `engine.py` 2.254,
  `certificazione.py` 2.036, `exits.py` 1.273, `certificazione_tennis.py` 1.217, `opportunity.py` 1.103, `bot_db.py` 1.044,
  `scanner.py` 909, `porta_ordini.py` 784, `proposte_opportunita.py` 742, `combos.py` 620, `stream.py` 567, `anomaly.py` 565,
  `canale_scan.py` 529, `selezione.py` 525, `tennis_opportunity.py` 521, `db.py` 502, `calibration.py` 431,
  `certificazione_k.py` 533, `veto_campionati.py` 233, `risk.py` 221, `arresto_bot.py` 198, `pressure.py` 149, `__init__.py` 6.
- Test Python in `Betfair/safe_strategy/tests/`: 92 file, 39.451 righe (`git ls-files | grep tests/ | xargs wc -l`).
- Frontend (non test, somma delle righe del `wc -l` dell'elenco `git ls-files frontend/src | grep -i safe`): `pages/SafeStrategy.tsx` 1.705;
  `components/safestrategy/` (BotParamsSheet 932, SafeTradesTable 873, OpportunityGroup 637, safeActivity 501, useSafeBot 428,
  SafeStrategyProvider 389, InvestAction 375, ParamsSheet 347, SignalCard 268, RiskPanel 188, MonitorCard 129, variantStyles 58) = 5.125;
  `lib/safeBot.ts` 2.256, `lib/safeStrategy.ts` 1.731, `lib/safeStrategyScan.ts` 406, `lib/safeExitStatus.ts` 196;
  `anteprima/safeBotFinto.ts` 227 + `safeRadarFinto.ts` 98. Totale non-test = 11.744. Tutto il file `frontend/src` che nomina "safe": 21.654 righe (test inclusi).
- Banco: `Betfair/stream/backtest/registro_bot.py:255-290` (safe_base, safe_esatto, safe_punta), `Betfair/safe_strategy/tools/replay_registrazioni.py`
  (scenari `SCENARI_DESCRITTI` 211+), `certificazione.py`, `certificazione_k.py`, `certificazione_tennis.py`.
- Altri pannelli dove Safe e' pilotato: Control Room (`frontend/src/components/controlroom/comandiBot.ts`, `PannelloBot.tsx` 24 occorrenze di "safe",
  `useControlRoom.ts` 215, `righeBot.ts` 5).
- Documento di strategia: `Betfair/safe_strategy/COSTITUZIONE_SAFE_STRATEGY.md` (1.217 righe) e `SPEC_STRATEGIA_S.md` (183 righe: **non tracciato**
  da git, `git ls-files SPEC_STRATEGIA_S.md` = vuoto; e' l'unico documento che `registro_bot.py:290` indica come `spec` di Safe).
- Strumento di misura di questa scheda: `ARCHITETTURA_2026-10/strumenti/e3_righe_safe.py` (rieseguibile, solo lettura).

Schede gia' pronte che cito senza rifare: D (`D_RUNTIME_BOT_CONTRATTO.md`: contratto, mappa Safe, gemelle con Mike/Omega), A (`A_CONNESSIONE_BETFAIR.md`: scanner,
stream, riconnessione), C (`C_PORTA_ORDINI.md`: le tre strade), G (dati del cloud), `07_MISURE_OGGI.md`.

---------------------------------------------------------------------------------------------------------------------------------------

## 1. Oggi

### 1.1 Due processi, tre cose diverse in un solo albero di cartelle

| Cosa | Processo | File principali | Ruolo reale (letto dal codice) |
|---|---|---|---|
| **BOT** Safe | `Betfair.safe_strategy.bot_service` (lock porta 47318, `bot_service.py:139`; canale locale 47335, `bot_service.py:10569`) | `bot_service.py`, `engine.py`, `exits.py`, `risk.py`, `execution.py`, `bot_db.py`, `porta_ordini.py`, `canale_scan.py`, `opportunity.py`... | Legge le righe del feed, decide ingressi/uscite, manda gli ordini, regola. Cadenza `poll_interval_s` = 2 s (`bot_service.py:10945-10963`, `DEFAULT_PARAMS` 143) |
| **SCANNER** del feed | `Betfair.safe_strategy.service` (lock porta 47315, `service.py:74`; canale 47336, `service.py:91`) | `service.py`, `scanner.py`, `stream.py`, `db.py`, `pressure.py`, `selezione.py` | NON e' un bot: `registro_bot.py:410-413` lo dichiara `NON_BOT` ("pubblica i fatti, non piazza mai un ordine"). Serve Safe, Mike, Omega, runner calcio, scalper (A, riga 142-147) |
| **GUSCIO UI** | app desktop + browser (Supabase Realtime) | `SafeStrategy.tsx` e `components/safestrategy/*`, `lib/safeBot.ts`, `lib/safeStrategy.ts` | Mostra, modifica parametri, accende/spegne, scrive richieste; **ricalcola da se' le valutazioni di strategia in TypeScript** (vedi 3.1) |

### 1.2 Mappa interna di `bot_service.py` (11.136 righe; intervalli da `grep -n "^def \|^class "`, misura in `strumenti/e3_righe_safe.py`)

| Intervallo righe | Responsabilita' | Righe | Natura |
|---|---|---:|---|
| 1-249 | import, costanti, `DEFAULT_PARAMS` 150-190, `_MercatoSafe` 95-135 (adattatore sul modulo di mercato di Omega) | ~315 (fuori dalle def) | guscio |
| 250-318 | import lazy dei moduli (`_import_engine_module` 250, `_omega_service` 302, `_now` 312) | 69 | guscio |
| 319-696 | `resolve_params` 319, `normalize_strategy_modes` 412, `normalize_uscite_automatiche` 440, `uscite_automatiche_di` 462, `modalita_di_strategia` 477, `normalize_variants` 507, `params_effective` 529, `params_corrections` 566, `normalize_control_params` 623 | 378 | guscio (parametri) + interruttori di sicurezza |
| 697-841 | `prices_from_row` 697, `rest_gate` 764, `prices_for` 786, `poll_flumine` 826 | 145 | guscio (prezzi dal feed e ripiego REST) |
| 842-935 | porta ordini: `_porta_di`/`_porta_kw` 869-910, `_avvia_porta_ordini` 911 | ~95 | guscio |
| 935-2379 | riconciliazione dell'ordine (`reconcile_pending` 1117, `_risolvi_via_canale` 935, consapevolezza 1370-1553, `_adotta_per_mercato` 1577, posizione di conto 1857, `settle_open` 2089, `sync_hedges` 2258, `_read_markets_batch` 2292) | 1.445 | ordini / regolamento |
| 2380-2467 | commissione, eta' delle richieste | 88 | guscio |
| 2468-3827 | marcatore "chiuso dall'utente" 2468-2640; `process_requests` 2669; `_request_place` 2917 (335 righe), `_request_place_combo` 3252, `_request_cashout` 3492, `_request_cashout_event` 3677, `_request_cancel` 4046, `_request_riprendi_evento` 3814 | 1.360 | richieste dalla UI |
| 3829-6014 | uscite: `_uscita_del_bot_approvata` 3829, `process_exits` 4254, `_process_exit_one` 4307, `exit_state` 4155, `_exit_due` 4179, `_decide_model_exit` 4862, `_p_calcio` 4755, `_p_tennis` 4925, `_model_gate` 5021, `_proponi_chiusura` 5503, `_send_exit` 5686 (218 righe), cecita' del feed 5261-5349 | 2.229 | decisione (modello) + esecuzione, mescolate |
| 6015-6536 | `_execute` 6038, `place_allowed` 6217, `_place_fail*` 6233-6371, catena bloccata 6372-6442, skip quote assenti 6516 | 522 | piazzamento |
| 6537-7409 | rischio (`build_risk_ctx` 6688, `_risk_gate` 6775, `_risk_commit` 6804), log di copertura 6860-6962, `scan_and_place` 7052 | 874 | **strategia di ingresso + rischio** |
| 7410-9210 | lambda dal cloud (`resolve_event_lambdas` 7595), `process_opportunities` 7726, `_proponi_opps` 8042, riconciliazione proposte 8355, `_proponi_combo` 8560, `_esegui_combo_riservata` 8710, coperture combo 9016, `unwind_incomplete_combos` 9183 | 1.801 | opportunita' (modello, tennis, combo) |
| 9211-9386 | ripiego REST dei prezzi per le posizioni, uscita combo | 176 | guscio |
| 9387-9511 | `process_anomalies` 9387 | 125 | strategia (anomalie) |
| 9512-10028 | canale scanner lato bot (`avvia_client_scan` 9519, `installa_sveglia_canale` 9554), `_leggi_righe_scan` 9621-9753, **giro veloce** 9754-10028 | 517 | guscio (lettura del feed e cadenza) |
| 10029-11136 | `run_once` 10115 (350 righe), `main` 10902, attese 10662-10838, arresto 10891, `_control_per_il_giro` 10839 | 1.108 | ciclo / guscio |

Mappa di `service.py` (3.444 righe, TUTTO scanner):

| Intervallo | Responsabilita' | Righe |
|---|---|---:|
| 74-330 | costanti: cadenze (`_CATALOGUE_TTL_SEC` 300, `_SCORES_PERIOD_SEC` 2, `_TIMELINE_PERIOD_SEC` 30, `_PUBLISH_MIN_INTERVAL_SEC` 2,5, `_STATUS_PERIOD_SEC` 10, `_BOOK_CHUNK` 25, `_REQ_DELAY` 0,35), finestre del catalogo 6 h passate / 14 h future (189-190) | 257 |
| 329-430 | `SorvegliaFonte` (stream o REST, avvisi `FEED_RIPIEGO_REST`/`FEED_RIENTRO_STREAM`), `_scrivi_avviso` | 100 |
| 431-631 | `Scanner.__init__`: stream, sessione Betfair, canale, workers | 200 |
| 632-835 | catalogo (`refresh_catalogue` 632, `_metas_da_catalogo` 679, `_aggiungi_esposti_mancanti` 715, `_tieni_eventi_vivi` 781, indice mercati 815) | 204 |
| 836-1131 | copertura e flusso prezzi (`_aggiorna_copertura` 836, `flusso_mercato` 975, `flusso_evento` 1005, `_mercato_attivo` 1099) | 296 |
| 1131-1372 | allarmi (`controlla_flumine` 1135, `allarme_quote` 1149), ranking mercati rilevanti (1159-1303), set dello stream (`refresh_stream_set` 1315) | 242 |
| 1372-1910 | applica book/punteggi: `_apply_market_book` 1395, `_apply_cs_book` 1562, `_apply_opp_book` 1598, `poll_books` 1672, IPS `_ips_batch` 1698, `poll_scores` 1738, timeline 1830-1908 | 538 |
| 1909-2440 | candidati e cataloghi dei mercati a gol/CS/HT, `_esposizioni` 1953 (mercati dove Mike/Omega/Safe hanno posizioni), `refresh_mercati_esposti` 2261, `opportunities` 2415 | 531 |
| 2441-2530 | canale locale 47336 (`_avvia_canale` 2441, `_spingi_riga` 2476, `_spingi_stato` 2508) | 90 |
| 2531-2723 | `build_rows`: costruisce il payload di ogni evento | 193 |
| 2724-2960 | `hydrate_schede`, `hydrate_pre_ko`, `purge_orphans`, `publish` 2839, `publish_status` 2856 | 237 |
| 2979-3175 | `tick` (un giro dello scanner) | 197 |
| 3175-3444 | `Cronometro` 3175, `ScoreFeedWorker` 3258 (thread), `main` 3341 | 270 |

### 1.3 Chi lo importa e da chi dipende

- `bot_service.py` importa `engine`, `exits`, `risk`, `execution`, `bot_db`, `porta_ordini`, `canale_scan`, `proposte_opportunita` (riga 58) e
  **`Betfair.omega.omega_service`** (`_omega_service` 302: `poll_flumine_pending` 826-834; `omega_market` per il saldo `main` 10913): Safe dipende dal modulo di un altro bot.
- `registro_bot.py:167-176` elenca i 17 moduli di produzione Safe che il banco carica (`_MODULI_SAFE`).
- `service.py` (scanner) e' letto da: `mike/db.py:553` (`fetch_scan_rows`), `bot_db.py:951`, `scan_feed.py:417`, `auto_follow.py:474`, `scalper_service.py:110` (A, riga 142-147), e dal frontend
  `lib/safeStrategyScan.ts:343-387` (SELECT + Realtime su `safe_strategy_scan` e `safe_strategy_status`).

### 1.4 Tabelle del DB (con chiamata e frequenza misurata)

Bot (frequenze: `07_MISURE_OGGI.md` §4.2, 08/10; riga 02/10: `SCHEMI_BOT/sistema/MISURE_2026-10-02.md:44`):

| Tabella / RPC | Chiamata (file:riga) | 02/10 | 08/10 |
|---|---|---:|---:|
| `safe_strategy_control` GET | `bot_db.py:62` `read_control`; chiamata 2 volte per giro: `bot_service.py:10839` (`_control_per_il_giro`) e `run_once` (10115+) | 36 | 37,9 |
| `safe_strategy_control` PATCH | `bot_db.py:70` `set_control`, 1 per giro in `run_once` (`db.set_control(stats=..., heartbeat_at=...)`) | 19 | 19,0 |
| `safe_strategy_trades` GET | `bot_db.py:128` `list_trades("pending")` (da `reconcile_pending` 1119), `bot_db.py:164` `open_trades` (da `settle_open` 2092 e `build_risk_ctx` 6711), `bot_db.py:181` `trades_pending_o_aperti` (da `_opp_keys_con_ordine_vivo` 8250) | 81 | 82,0 |
| `safe_strategy_requests` GET | `bot_db.py:604` `pending_requests`, chiamata 2 volte per giro (`process_requests` 2698, due passate: corsia chiusure + normale, `run_once`); piu' le letture delle proposte (`bot_db.py:689`, `727`) | 44 | 44,6 |
| `safe_strategy_requests` PATCH | `bot_db.py:858` `fail_stale_processing` (UPDATE incondizionato ogni giro, `bot_service.py:2688-2693`) + transizioni di stato | 53 | 19,1 |
| RPC `get_safe_aggregates` | `bot_db.py:315` `aggregates` (da `build_risk_ctx` 6738) | 19 | 17,9 |
| `safe_strategy_scan` GET | `bot_db.py:951` `fetch_scan_rows` (riallineamento ogni `_RISINC_DB_S` = 10 s, `bot_service.py:9487-9492`, `9647`) | 5 | n.d. |
| `safe_strategy_activity` INSERT | `bot_db.py:77` `log` (33 kind + `risk_block` + `flumine_*`) | (non in tabella) | (non in tabella) |
| `safe_strategy_opportunities` UPSERT/DELETE/PURGE | `bot_db.py:875-915` | 4+1 | n.d. |
| `safe_strategy_status` GET | `bot_db.py:969` `scanner_status` (eta' dello scanner, `_scanner_ts` 4088) | 5 | n.d. |
| `fixtures`, `fixture_analysis` | `bot_db.py:925`, `937` (lambda dal cloud, `resolve_event_lambdas` 7595) | n.d. | n.d. |
| `betfair_live_order_requests` | `bot_db.py:1003-1038` (mirror/richieste d'ordine condivise col runner) | n.d. | n.d. |

Totale processo `safe-strategy-bot`: **254,6 / 265,8 / 232,3 richieste al minuto** (02/10, 04/10, 08/10; `07_MISURE_OGGI.md:213`). Di questo, `control`
(56,9) + `requests` (63,7) + `trades` (82,0) + `get_safe_aggregates` (17,9) = **220,5 su 232,3 = 95 %** il 08/10 (somma mia delle righe di `07` §4.2).

Scanner (`07_MISURE_OGGI.md:215`): **85,1 / 88,9 / 81,7 al minuto**: `safe_strategy_scan` POST 65,4 (`db.py:198`, una upsert a batch per giro,
`service.py:2839-2855`), `mike_events` GET 5,5 (`db.py:295`), `rpc/list_bot_exposures` 5,5 (`db.py:416`), `safe_strategy_status` POST 4,7 (`db.py:221`).

### 1.5 Canali locali, stato condiviso, orologi, thread

- Canale locale scanner 47336 (`service.py:91`): topic `scan_calcio`, `scan_tennis`, `scanner_stato` (`service.py:93-94`). Il bot lo legge col client di `canale_scan.py` (529 righe) se `SAFE_BOT_LEGGE_CANALE`
  e' acceso (`bot_service.py:9512-9553`); in ogni caso rilegge il DB ogni 10 s come riallineamento (`bot_service.py:9487-9492`).
- Canale locale bot 47335 (`bot_service.py:10569`): `_pubblica_stato` 10607 pubblica `safe_stato` (stessi `stats` del `set_control`).
- Porta ordini: `porta_ordini.py` (784 righe) parla col runner sul canale 47331 (calcio) / 47332 (tennis) con il protocollo COMANDO ORDINE (docstring di `porta_ordini.py`); `_avvia_porta_ordini` `bot_service.py:911`.
- Stato in RAM: `_LAST_CONTROL`, `_OPPS_STATE`, `_PLACE_ATTEMPTS`, `_PENDING_CICLO` (TTL 5 s, 6602), `_AGG_ULTIMO_BUONO` (TTL 120 s, 6633), `_BLOCCO` 9459, `_GUARDIA_AVVIO` 9466 e il tracker del motore (`ScoreStability`, segnali attivi in `SafeEngine`, `engine.py:1980`): perso al riavvio (catalogo §7 n.19; copertura: scenario `riavvio`).
- Orologi: ciclo bot 2 s + lavoro (misurato ~3,16 s/giro: 60/19,0 PATCH di control al minuto); scanner `tick` con refresh dei punteggi IPS ogni 2 s (`_SCORES_PERIOD_SEC` 132) da un thread `ScoreFeedWorker` (`service.py:3258`).
- Thread dello scanner: `ScoreFeedWorker` (3258), thread dello stream `StreamShard._run` (A riga 79), canale (`service.py:2441`). Thread del bot: porta ordini, esiti (`_avvia_esiti_ordini` 10628), sveglia canale (9554).
- Chiamate di rete nel percorso critico del bot: ogni giro, 11-15 round-trip verso Supabase prima di decidere (tabella 1.4); la riga del feed ha eta' = freno 2,5 s dello scanner + giro del bot (D, riga 121: "i tre bot a polling NON hanno zero rete tra messaggio e decisione").

### 1.6 Betfair verso lo scanner (non Supabase)

Dalle costanti: `listMarketCatalogue` ogni 300 s per sport (`service.py:120`), cataloghi dei mercati a gol/CS/HT/esposti al piu' ogni 20 s (`_CS_CATALOGUE_MIN_INTERVAL_SEC`, 125), `listMarketBook` a chunk di 25 con pausa 0,35 s solo per i mercati non coperti dallo stream (174, 176, A riga 199), IPS `scoresAndBroadcast` a chunk di 50 ogni 2 s (132, 175, 196; ~30 chiamate/min a calcio in-play), timeline ogni 30 s (136), keepalive ogni 900 s (173). **Il numero reale di queste chiamate al minuto non e' in `07_MISURE_OGGI.md` (misura solo Supabase): non misurato.** Stream: 4 connessioni x 180 mercati, conflate 1000 ms, riconnessione senza `clk` (A righe 79, 170-171; `stream.py:66,275`).

---------------------------------------------------------------------------------------------------------------------------------------

## 2. Funzionalita'

Legenda: [UI file] = visibile nel pannello; [P] = parametro editabile; [I] = intoccabile (strategia). Le regole di strategia non si alterano (CLAUDE.md, §0 del brief).

### 2.A LOGICA DI STRATEGIA (intoccabile, `file:riga`)

**Ingressi calcio (`engine.py`, funzioni PURE sui contesti `FootballMatchCtx`)**

- E3-001 [I] Parametri di serie delle quattro varianti `DEFAULT_PARAMS`: `engine.py:196-320` (base 196-208, esatto 209-221, punta 222-233 [`entryMin` 1,03 `entryMax` 1,1 `minuteMin` 66 `scores` 2-0, 3-1, 3-0 `minMinutesAfterGoal` 3], tennis 234-255, stake 256; `favSuperMax` 1,20 a 320). Visibile: `BotParamsSheet.tsx` [P]. Duplicato in TS `safeStrategy.ts:218`.
- E3-002 [I] **BASE** (banca la squadra che perde, mercato 1X2 `MATCH_ODDS`): `evaluate_base` `engine.py:1227-1328`. Condizioni, nell'ordine: partita in-play (`_inplay_check` 1183), veto campionati (1123, `veto_campionati.py`), minuto >= `minuteMin` 55 (1129; regola utente 14/09 "a partire dal minuto X": soglia, non fascia), secondo tempo (1144), controllo del gioco (`control_check` 918, solo se `requireControl`), punteggio con la favorita avanti in `scores` 1-0, 2-1, 2-0 orientato sulla favorita (`score_in_list_oriented` 172), bande pre-partita favorita 1,40-1,80 e sfavorita 4-8 (`pre_bands_checks` 1203), mercato aperto (1173), punteggio confermato per `scoreConfirmSec` 30 s (1187), nessun rosso alla favorita (`noRedFav`), quota di BANCA della sfavorita 20-34 (`dogLay`, `dogLayMin/Max`). Ordine: LAY, `market_type` MATCH_ODDS. [UI: `MonitorCard.tsx`, `SignalCard.tsx`] [P base.*]
- E3-003 [I] **ESATTO** (banca "Altro risultato Casa/Ospite" nel Correct Score): `evaluate_esatto` `engine.py:1329-1425`: in-play, veto campionati, minuto >= 48, secondo tempo, controllo (`deve_avere=False`: l'OPPOSTO della base), selezione aggiuntiva (`selection_check` 943, `requireSelection`, tasso h2h gol <= 0,58 con >= 3 incontri, subiti dell'avversario <= 1,37), punteggio in 0-0/1-0/1-1/2-1 in qualunque ordine (`score_in_list_any_order` 181), squadra bancata con al massimo 1 gol (`sideGoals`, `maxGoalsLaySide`), punteggio confermato 30 s, mercato Correct Score aperto, quota di banca 30-70 (`entryMin/Max`). Uno solo dei due lati per partita (guardia `_esatto_gia_su_evento` `bot_service.py:7016`). [P esatto.*]
- E3-004 [I] **PUNTA** (back la favorita avanti di due gol): `evaluate_punta` `engine.py:1426-1544`: in-play, veto, minuto >= 66, controllo, punteggio 2-0/3-1/3-0, favorita in vantaggio (`leadFav`), nessun rosso al leader (`noRedLead`), mercato aperto, quota back live 1,03-1,10, almeno 3 minuti dall'ultimo gol (`settled`); le bande pre-partita sono LE STESSE della base (`pre_bands_checks`, Q10 25/09). [P punta.*]
- E3-005 [I] Esito aggregato `state_from_checks` `engine.py:537-545` (un `False` batte `None`, `None` batte `True`: stati `no`/`nd`/`signal`).
- E3-006 [I] Veto dei campionati del corso (lista negativa, serie B incluse; ordine utente 25/09 Q4): `veto_campionati.py` (233 righe), applicato da `campionato_check` `engine.py:1076-1122` (chiave `vetoCampionati`). [P: non editabile in UI]
- E3-007 [I] Selezione aggiuntiva dell'esatto (dato dalla SCHEDA DB della fixture, D5 25/09): `selezione.py` (525 righe), `engine.py:943-1024`.
- E3-008 [I] Indice di pressione (corner, cartellini, tiri dall'IPS): `pressure.py` (149 righe), calcolato dallo scanner nel payload (`service.py:2531+`, `payload["pressure_index"]`).
- E3-009 [I] **TENNIS** (back il leader a ~1,03 dopo 1 set + 2 game): `evaluate_tennis` `engine.py:1567-1731`: set di vantaggio >= 1 (`setsLeadMin`), game di vantaggio >= 2 (`gamesLeadMin`), quota back 1,02-1,10, no doppi, no al meglio dei 5 (`detect_best_of` 893), set giocati <= 1, sfavorito estremo (`tennis_sfavorito_estremo_check` 1047, `favSuperMax` 1,20), competizioni escluse, punteggio confermato 15 s. [P tennis.*]
- E3-010 [I] Anti-blip e persistenza dei segnali: `track_score_stability` 1744, `track_tennis_score_stability` 1762, `signal_key` 1777, `reconcile_signals` 1907-1944 (nuovo -> attivo, assente -> `expired`, storico `SIGNAL_HISTORY_MAX`), `SafeEngine` 1980-2253 (`_ingest` 2010, `evaluate` 2112, `evaluations` 2201, `control_data_coverage` 2183, `pre_match_missing_events` 2133, `fase_ignota_events` 2160).
- E3-011 [I] Stake di serie e per strategia: `merge_params` `engine.py:381-458`, `stake_di_strategia` 477 (laySize 2, backSize 2, `per_strategia` {}) [P stake.*].

**Ingresso automatico, rischio (`bot_service.py`, `risk.py`)**

- E3-012 [I] `scan_and_place` `bot_service.py:7052-7409`: per ogni segnale applica, in sequenza, i filtri `variante_non_abilitata`, `minuto_ingresso_oltre_uscita` (`_minuto_oltre_uscita` 6989: non entrare se il minuto e' gia' oltre quello di uscita), `partita_chiusa_dall_utente` (marcatore 2468), `blocco_di_catena` (6372), idempotenza `(event_id, signal_key)` (`_traded_keys` 3424), `esatto_lato_gia_aperto` (7016), `un_solo_ingresso_per_partita` (`_variante_gia_entrata` 7004), freschezza della riga (`_row_is_fresh` 8502), budget dei ritentativi (`place_allowed` 6217, `place_max_attempts` 3), `max_open_trades` 20, spread (`max_spread_ratio` 1,6), liquidita' (`min_size_available_factor` 1,0), `max_liability_per_trade` 300 (3141), gate di rischio (`_risk_gate` 6775). Ogni scarto scrive un `skip` con motivo. [UI: attivita', `safeActivity.ts`] [P]
- E3-013 [I] Rischio `risk.py` (221 righe): `DEFAULT_RISK_PARAMS` 37-45 (cap giornaliero 500, per evento 150, max 3 trade per evento, correlato 0,7, stop perdita giornaliera -50, stake modello 5, cap modello 150), `check` 185-220 (ordine: stop perdita -> max aperte -> trade per evento -> cap per evento correlato -> cap giornaliero -> cap modello; `soft=True` per le richieste manuali: solo i cap di esposizione), giornata operativa Europe/Rome `operating_day_start` 123. [UI: `RiskPanel.tsx`] [P risk.*]
- E3-014 [I] Contesto di rischio di ciclo `build_risk_ctx` `bot_service.py:6688-6774` (posizioni vive + aggregati; se non leggibile -> `_risk_ctx_cieco` 6642: nessun ingresso), tetto partite aperte per modo (`_BLOCCO` 9459), `_risk_commit` 6804.

**Uscite (`exits.py`, `bot_service.py`)**

- E3-015 [I] Parametri di serie `DEFAULT_EXIT_PARAMS` `exits.py:69-92`: `base_exit_minute` 80, `esatto_exit_minute` 72, `punta_exit_minute` 83, `loss_settle_delay_s` 30, `red_card_fav_exit` True, `base_control_exit` False (nasce spenta: dato non ancora misurato), `tennis_take_profit_next_game` True (min odds 1,03, min 0,01 EUR), `tennis_exit_on_lost_game` False, `exit_max_retries` 3, residuo (`residual_retry_s` 20, `residual_max_attempts` 15), `hold_max_risk` 0,02, `risk_cap` 0,10, `ev_margin` 0,10, `risk_premium_pct` 0,05, modello (`model_exit_p_lose` 0,10, `model_take_profit_frac` 0,8, `model_free_cashout_p_lose` 0,005). Clamp: `merge_exit_params` `exits.py:268-315`. [UI `BotParamsSheet.tsx` gruppo `exits.*`, 22 chiavi] [P]
- E3-016 [I] Uscita BASE `_decide_base` `exits.py:993-1011`: la sfavorita pareggia -> perdita (dopo 30 s), la favorita segna ancora -> profitto, rosso alla favorita -> uscita, controllo passato alla sfavorita (spenta di serie), minuto >= 80 -> a tempo. ESATTO `_decide_esatto` 1012: il lato bancato segna -> perdita; minuto >= 72 -> a tempo. PUNTA `_decide_punta` 1022: la favorita subisce gol -> perdita; segna ancora -> profitto; minuto >= 83. TENNIS `_decide_tennis` 1034-1074: due game persi di fila + parita' nel set -> OBBLIGATORIA; vince il game -> take profit (sotto la soglia di quota minima no); perde il game -> uscita solo se acceso.
- E3-017 [I] Tracciamento `track` `exits.py:748-906` (calcio 772, tennis 833) e freschezza del feed `feed_is_fresh` 424 con tetti `FEED_FRESH_S` 20 s, `FEED_HARD_MAX_S` 120 s (M-24), `SCANNER_HEARTBEAT_MAX_S` 45 s (`exits.py:231,234,245`): con dati vecchi si ASPETTA, mai chiudere al buio. Duplicati in TS `safeBot.ts:1094-1102`.
- E3-018 [I] Decisione a MODELLO per le uscite in profitto con P&L bloccato < 0: `decide_time_exit` `exits.py:460-571`, `ev_hold` 578, `decide_model` 1207-1258, `model_is_blind` 1144, linea O/U decisa contro `line_decided_against` 1096; lato bot: `_decide_model_exit` `bot_service.py:4862`, `_model_gate` 5021, `_p_calcio` 4755, `_p_tennis` 4925. Tiene la posizione (log `exit_hold`, `meta.exit_hold`) quando il margine e' ampio; le uscite in perdita restano incondizionate (Costituzione §13.1).
- E3-019 [I] Nessuno stato di uscita e' terminale (C-04/H-05/H-17), `hold_code` scritto una volta (M-28): `_exit_wait` 5384, `_write_model_hold` 5098, `_write_exit_state` 5145, `_hold_firma` 4644.
- E3-020 [I] Uscita a prezzo/a tick: `close_plan` `execution.py:2228`, `ticks_for_exit` 2203, `locked_pnl` 2283; chiusura `close_trade` 2383-2643 (fill parziali, residuo, `GreenupPlan`).
- E3-021 **Interruttore delle uscite automatiche** (ordine utente 25/09 sera «di default tutte le uscite spente»): mappa completa `uscite_automatiche{base, esatto, punta, tennis, model}` (`STRATEGIE_CON_USCITE` `bot_service.py:437`, `normalize_uscite_automatiche` 440-460, `uscite_automatiche_di` 462-475). Serie: tutte False (`DEFAULT_PARAMS["uscite_automatiche"] = {}` 170-183); il tennis segue il vecchio cancelletto `tennis_exit_approval` (serie True -> manuale; `resolve_params` 372-381 li allinea). Letto a ogni giro (`resolve_params`), identico in paper e live; applicato in `_process_exit_one` `bot_service.py:4457-4464`. Spento = la decisione viene COMUNQUE presa ma diventa una PROPOSTA di chiusura (`_proponi_chiusura` 5503) con i tasti dell'utente; acceso = `_send_exit` 5686 la manda da sola. [UI: Control Room `PannelloBot.tsx`/`comandiBot.ts`; `SafeTradesTable.tsx` proposte; `lib/safeExitStatus.ts`] [P `uscite_automatiche`, `tennis_exit_approval`]
- E3-022 Proposte di chiusura per l'approvazione dell'utente: `_uscita_del_bot_approvata` 3829, `_proponi_chiusura` 5503-5668, decadenza `_decadi_proposta` 5669, `_decadi_proposte_non_eseguibili` 3927 (D1, 28/09), DB `bot_db.py:625-725`. [UI `SafeTradesTable.tsx`]

**Opportunita', anomalie, combo (modello; proposte, non ordini, salvo `auto_trade_*`)**

- E3-023 [I] Modello tempo x punteggio `opportunity.py` (1.103) + `calibration.py` (431; tabelle `data/opp_calibration.json`, 3.630 righe); tennis `tennis_opportunity.py` (521, Markov per game); `process_opportunities` `bot_service.py:7726-7994`, `_proponi_opps` 8042-8163 (card con PIAZZA/RIFIUTA, ordine utente 17/09), riconciliazione 8355-8489. [UI `OpportunityGroup.tsx`] [P `proponi_*`, `auto_trade_opportunities/tennis`, `opps_*`]
- E3-024 [I] Quote anomale senza modello (4 regole `ou_ladder`, `decided`, `mo_cs`, `ht_open`: `anomaly.py` 565; `safeBot.ts:422`): `process_anomalies` `bot_service.py:9387-9511`. [P `proponi_anomaly`, `auto_trade_anomalies`]
- E3-025 [I] Combo a rischio bloccato dai prezzi (famiglie `dutch`, `under_stack`, `over_stack`, `ou_span`, `cs_cover`, `safeBot.ts:423`): `combos.py` (620), `_proponi_combo` 8560, `_esegui_combo_riservata` 8710, tutto-o-niente `_unwind_combo` 9305, gambe lasciate al trader (`gestisci_coperture_combo` 9016, `modo_gamba_manuale` 8886 [P `combo_gamba_manuale`]).
- E3-026 Lambda e dossier dal cloud: `resolve_event_lambdas` `bot_service.py:7595-7664`, abbinamento fixture per nome `_fuzzy_fixture` 7440, `_lambdas_from_fixture` 7519 (vedi G). Tabelle `fixtures`, `fixture_analysis` (`bot_db.py:925-948`).

**Parametri editabili e valori di serie**

- E3-027 [P] Parametri dello scalare di bot, serie in `bot_service.py:150-190`, clamp in `resolve_params` 319-398 e `params_effective` 529: `poll_interval_s` 2 (min 1), `commission_pct` 5 (0-20), `max_open_trades` 20, `max_liability_per_trade` 300, `min_size_available_factor` 1, `opps_interval_s` 10, `opps_stake` 5, `opps_min_confidence` 0,7, `opps_min_edge` 0,03, `place_max_attempts` 3 (1-20), `skip_log_interval_s` 300, `max_spread_ratio` 1,6, `execution_mode` `auto` (o `rest`), `paper_fill_ttl_s` 45 (5-600), `live_fill_deadline_s` 20 (5-300), `min_stake` 2,0, `variants` (tutte e quattro), `strategy_modes` {}.
- E3-028 [P] La scheda parametri `BotParamsSheet.tsx` (932 righe) espone 82 chiavi (`grep -o "key: '...'" | sort -u` = 82): 24 di primo livello (4 `auto_trade_*`, 4 `proponi_*`, `commission_pct`, `live_fill_deadline_s`, `max_liability_per_trade`, `max_open_trades`, `max_spread_ratio`, `min_size_available_factor`, `min_stake`, `opps_interval_s`, `opps_min_confidence`, `opps_min_edge`, `opps_stake`, `paper_fill_ttl_s`, `place_max_attempts`, `poll_interval_s`, `tennis_exit_approval`), 6 `base.*`, 7 `esatto.*`, 6 `punta.*`, 8 `tennis.*`, 22 `exits.*`, 7 `risk.*`, 2 `stake.*`. **Non editabili dalla scheda (solo da DB o Control Room)**: `variants`, `strategy_modes`, `uscite_automatiche` (Control Room), `favPre*/dogPre*` (bande pre-partita), `vetoCampionati`, `excludeCompetitions`, i parametri della selezione (h2h), `execution_mode`, `omega_live_via_flumine`, `skip_log_interval_s`. Conferma dei valori reali (clampati) dentro la scheda: `params_effective` + `data-testid="params-effective"` (`BotParamsSheet.tsx:408`); correzioni scritte in attivita' (`params_clamped`, `params_invalid`, `normalize_control_params` 623).
- E3-029 Valori di serie DUPLICATI Python/TS (vedi 3.1): `engine.py:196-320` / `safeStrategy.ts:218`; `bot_service.py:150-190` / `safeBot.ts:701-749`; `risk.py:37-45` / `safeBot.ts:688-696`; `exits.py:69-92` / `BotParamsSheet.tsx:114` (`mergeExits`); `merge_params` `engine.py:381` / `mergeParams` `safeStrategy.ts:312`; `merge_risk_params` `risk.py:68` / `mergeRiskParams` `safeBot.ts:751`; `resolve_params` / `mergeBotParams` `safeBot.ts:760`.

### 2.B SCANNER del feed (componente a se'; funzionalita' `E3-S..`)

Cosa calcola e scrive: ogni riga di `safe_strategy_scan` (chiave `event_id`, `sport`, `payload`, `updated_at`: `service.py:2531-2723` e `db.py:192-205`) e la riga `safe_strategy_status` (`id='scanner'`, `db.py:221-236`; `publish_status` `service.py:2856`). Chi la legge: bot Safe (`bot_db.py:951`), Mike (`mike/db.py:553`), Omega (`scan_feed.py`/`omega_service`), runner calcio (`scan_feed.py:417`), scalper (`scalper_service.py:110`), `auto_follow.py:474`, UI (`safeStrategyScan.ts:343`). Frequenza: un `tick` continuo (`service.py:2979`), upsert a batch di tutte le righe CAMBIATE (write-on-change, freno 2,5 s per evento `_PUBLISH_MIN_INTERVAL_SEC` 159), 65,4 POST/min il 08/10.

- E3-S01 Catalogo Betfair calcio (id sport 1) e tennis (2), finestra -6 h / +14 h, TTL 300 s, ritenta dopo 30 s: `refresh_catalogue` `service.py:632-678`, `_catalogue_window_iso` 300, costanti 120, 189-190, 217. [calcio e tennis non si mischiano: `SportState` 420]
- E3-S02 Stream dei mercati in 4 connessioni (conflate 1000): `stream.py` 567 righe (`StreamShard`, piano stabile, resubscribe a caldo 30 s, `healthy()`/`serving()` 20 s: A righe 79, 175, 345); `refresh_stream_set` `service.py:1315`, `_diario_pool_stream` 1345.
- E3-S03 Ripiego REST per i mercati senza quote dallo stream: `poll_books` 1672, cadenza `scanner.books_period_calcio/tennis` (`scanner.py:535,544`), `SorvegliaFonte` 329-410 -> avvisi `FEED_RIPIEGO_REST` / `FEED_RIENTRO_STREAM` (`_scrivi_avviso` 412; A riga 206).
- E3-S04 Selezione dei mercati rilevanti (monitorabili, ranking, mercati caldi 55', pre-KO, attesa dopo il KO): `ranked_relevant_markets` 1165, `is_monitorable` `scanner.py:432`, `rank_key` 477, `in_pre_ko_window` 380, `in_post_ko_wait` 411.
- E3-S05 Prezzi: miglior back/lay e profondita' (`price_pair` `scanner.py:265`, `build_market_block` 697), `bet_delay`, `odds_ts_ms`/`odds_pt_ms`/`odds_seen_ms` (istanti per la catena dei tempi), cambio GBP->EUR (`valuta`, `service.py` `"valuta"` nel payload).
- E3-S06 Mercato Correct Score, Half Time Score, mercati a gol (Over/Under, BTTS), pre-KO O/U: `refresh_cs_catalogue` 2200, `refresh_ht_catalogue` 2204, `refresh_opp_catalogue` 2119, `pre_ko_ou_candidates` 1288, `build_cs_block` `scanner.py:750`, blocchi `ou[]`, `btts`, `ht_result` con `decided` e `for_mike` (Costituzione §12.3 righe 1073-1082).
- E3-S07 Punteggio, minuto, rossi, timeline, tennis (set/game): IPS `scoresAndBroadcast` (`_ips_batch` 1698, `poll_scores` 1738 ogni 2 s, `apply_score_state` 1777), timeline del fischio (`poll_timelines` 1880, `applica_timeline_fischio` 1858, finestra 300 s `_FINESTRA_FISCHIO_SEC` 148); thread `ScoreFeedWorker` 3258.
- E3-S08 Conferma del flusso di prezzi per mercato (`flusso_mercato` 975, `flusso_evento` 1005, `conferma_flusso` 909; modulo `Betfair/stream/flusso_prezzi.py`): e' l'unico che produce il segnale "il prezzo e' vivo" (A riga 207). Allarme quote mancanti `allarme_quote` 1149, `controlla_flumine` 1135.
- E3-S09 Scheda DB della fixture e pre-partita congelato (quote pre-KO 1X2 congelate prima del fischio: `freeze_pre_ko` `scanner.py:482`, `freeze_pre_ko_tennis` 509; `hydrate_pre_ko` `service.py:2742`, `hydrate_schede` 2724; `db.py:60-190`: `load_scan_pre_ko`, `fixtures_window`, `load_schede_fixture`, `load_round_fixture`): alimenta bande favorita/sfavorita e selezione dell'esatto.
- E3-S10 Indice di pressione e flag media (`pressure.py`; `media_flags` `scanner.py:682`) nel payload.
- E3-S11 Mercati ESPOSTI: `_esposizioni` 1953, `_mercati_esposti` 2033, `refresh_mercati_esposti` 2261, `db.list_bot_exposures` `db.py:416-500` (RPC `list_bot_exposures`, ripiego su 4 fonti `_list_bot_exposures_a_fonti` 454, finestra 7 giorni `db.py:363`): lo scanner tiene seguiti i mercati dove Mike/Omega/Safe hanno posizioni vive (cross-bot: Safe scanner conosce i bot degli altri) e `mike_followed` (`list_mike_followed_event_ids` `db.py:295`, `_mike_followed` 1926).
- E3-S12 Blocchi opportunita' nel payload (`opportunities` 2415, `opp_model` 2391, `_opp_ranked_market_ids` 1219): il modello di `opportunity.py` e' ESEGUITO dallo scanner per scrivere `payload.opportunities` e `payload.opps` (due forme, `safeBot.ts:1515`).
- E3-S13 Pubblicazione a firma: `scanner.payload_signature` 577, `critical_signature` 608 (cambia -> scrive subito; non critico -> freno 2,5 s); `purge_orphans` 2822 (ogni 300 s, grazia 60 s dopo l'avvio, 168); cancellazione delle righe sparite `db.delete_scan_rows` 208.
- E3-S14 Canale locale 47336 (`service.py:2441-2530`): spinge la STESSA riga prima del freno di scrittura, topic per sport; statistiche `canale_statistiche` 2519; client lato bot `canale_scan.py`.
- E3-S15 Stato dello scanner: `publish_status` 2856-2932 (`safe_strategy_status`, ogni 10 s), `_scarica_avvisi` 2933, battito letto dal bot (`_scanner_ts` `bot_service.py:4088`) e dalla UI (`useControlRoom.ts:971`).
- E3-S16 Cronometro per fasi (catalogo, stream, book, pre_ko, scrittura): `Cronometro` 3175-3257, `riassunto` 3242 (usato dai replay di velocita' `AUDIT_2026-09-30/replay/*_SCANNER_VELOCITA*.txt`).
- E3-S17 Custode di sessione, keepalive 900 s, login (`CustodeSessione`, A riga 182); lock di processo 47315 (`service.py:74`).
- E3-S18 Modalita' `dry` e ciclo singolo (`_ciclo_una_volta` 3319, `_ciclo_persistente` 3331, `main` 3341).

### 2.C GUSCIO (esecuzione, runtime, UI)

**Runtime del bot**

- E3-030 Ciclo `run_once` `bot_service.py:10115-10463`, nell'ordine: control (con degradazione se illeggibile: ultimo noto + SOLO protezione, nessun nuovo ingresso, 10123-10160) -> `resolve_params` -> `normalize_control_params` -> righe del feed (`_leggi_righe_scan` 9621) -> coda flumine (`poll_flumine`) -> `reconcile_pending` -> corsia preferenziale delle chiusure UI (`process_requests(solo_chiusure=True)`, 14/09) -> `settle_open` -> `seed_place_attempts` (ogni 5 min) -> `build_risk_ctx` -> cecita' del feed (`check_feed_blind` 5327, H-18) -> `unwind_incomplete_combos` 9183 -> `gestisci_coperture_combo` -> richieste UI -> `process_exits` -> `_decadi_proposte_non_eseguibili` -> `stopping`->`stopped` -> **ingressi solo se `status='running'`** -> anomalie -> opportunita' -> aggregati -> `stats` (~35 chiavi, fino a `set_control` 10437) -> `set_control(stats, heartbeat_at)`.
- E3-031 Giro veloce su evento di prezzo, SOLO Safe (`run_giro_veloce` 9912, `giro_veloce_se_dovuto` 9997, `_fotografa_giro_lento` 9785, `_attesa_con_giro_veloce` 10769, interruttore `_giro_veloce_acceso` 9754): protegge le posizioni al ms senza attendere il giro da 2 s.
- E3-032 Attese: `_attesa_interrompibile` 10676 (con posizioni aperte sbircia la coda ogni 250 ms, `_sbircia_la_coda` 10744; sveglia del canale), pavimento `_MIN_GIRO_S` 0,25 (9507, `_minimo_fra_due_giri` 10662).
- E3-033 Avvio sicuro: `ferma_al_nuovo_avvio` 10083 (all'avvio nuovo dell'app: `status=stopped`, `mode=paper`, `strategy_modes` tutte paper, attivita' `avvio_app_bot_fermato`; `arresto_app`/`avvio_app.py`), `_GUARDIA_AVVIO` 9466 (nessuna apertura finche' non riesce, `blocca_aperture`), `stats` timbrate (n.23).
- E3-034 Arresto ordinato (`arresto_bot.py` 198 righe; `_chiudi_all_arresto` `bot_service.py:10891`): annulla i PROPRI ordini non abbinati, dichiara le posizioni (02/10).
- E3-035 Errori di ciclo: `_segnala_errore_di_ciclo` 10464, `_pulisci_errore_di_ciclo` 10475 (una sola volta finche' dura), `cycle_exception` con `critical`.
- E3-036 Pubblicazione dello stato sul canale locale `safe_stato` (`_pubblica_stato` 10607) + `_control_per_canale` 10597.

**Paper / live**

- E3-037 Modalita' per strategia: `control.mode` e' un TETTO (in paper tutto paper); in live una strategia e' live SOLO se scritta in `strategy_modes` (mai ereditata): `modalita_di_strategia` `bot_service.py:477-505`, `normalize_strategy_modes` 412, `_avvisa_ereditarieta` 6826 (n.25). [UI: Control Room `PannelloBot.tsx`; `safeBot.ts:152` `liveStrategies`, `181` `modalitaOrdineAMano`]
- E3-038 Aggregati separati per modo: `bot_db.aggregates(mode)` 315 + RPC `get_safe_aggregates` (n.21); UI `aggregatiDellaModalita` `safeBot.ts:336`.
- E3-039 Tre strade d'ordine (C): `execution.place` `execution.py:1061-1515` -> (a) PORTA a comandi sul canale del runner (`_place_via_canale` 795, ramo `execution.py:1219`), (b) coda flumine `enqueue_place` 1766 (`execution.py:1286`), (c) REST diretto `market.place_order_live` (`execution.py:1382`); `_gate` 1741 sceglie coda/REST (`execution_mode`); `_live_brake` 138, `_freno_aperture` 199, minimo 2 EUR e punta sotto 0,50 (`_porta_al_minimo_tennis` 113, `_dichiara_punta_050` 1028). Annullo: `_annulla_via_canale` 975, `annulla_su_betfair` 440.
- E3-040 Paper legacy: `_paper_ladder` `bot_service.py:5986` + `paper_fill_ttl_s` (quasi-FOK) [scenario del banco `paper`: "serve a MISURARE la divergenza"].
- E3-041 Ciclo di vita dell'ordine: `reconcile_pending` 1117, `_risolvi_via_canale` 935, `_adotta_per_mercato` 1577, `reconcile_decision` `execution.py:1607`, riga 'reconciling' (`_reconciling` 1572), bet delay, parziali (`chiusura_con_residuo_vivo` 1955, `hedge_state` 1997), regolamento (`settle_open` 2089, `settle_position` `execution.py:2944`, P&L da `cleared` di Betfair `_posizione_da_cleared` 2879, commissione 5 % `_commission_rate` 2380), orfani (`settle_orphan_closing` 3063).

**Richieste dalla UI (coda `safe_strategy_requests`)**

- E3-042 `process_requests` `bot_service.py:2669-2768`: kind `place` (`_request_place` 2917; con riserva, prezzo visto, modo manuale), `cashout` (3492), `cashout_event` (3677), `cancel` (4046), `riprendi_evento` (3814); scadenza richiesta `_REQUEST_MAX_AGE_S` = 120 s (2399); stati `proposed/pending/processing/done/rejected/error` (`bot_db.py` `REQUEST_STATES`). [UI: `InvestAction.tsx`, `SafeTradesTable.tsx` "Chiudi", `SignalCard.tsx`] 
- E3-043 Marcatore "chiuso dall'utente" e ripresa evento: `bot_service.py:2468-2640` (`segna_chiuso_dall_utente` 2542, `riprendi_evento` 2569). [UI: pulsante riprendi, `riprendiEventoSafe` `safeBot.ts:1247`]
- E3-044 Approvazione di opportunita'/combo dalla UI: `approvaPropostaOpportunita` `safeBot.ts:1363` -> RPC `safe_request_approve` (migrazioni `safe_request_approve_*.sql`), `_request_place_combo` 3252. [UI `OpportunityGroup.tsx`, `InvestAction.tsx`]

**Allarmi e attivita'**

- E3-045 Allarmi critici (righe `critical: true` in `safe_strategy_activity`, mostrati in UI): `feed_blind`/`feed_back` (cecita' del feed su posizione viva, `check_feed_blind` 5327, `_avviso_critico_flusso` 9258, `_annuncia_flusso_fermo` 9290), `control_illeggibile_da_troppo` (`run_once` 10132-10160), `cycle_exception`, `rpc non disponibile`, `place_exhausted`, `blocco_di_catena` (6372, `execution.spiega_blocco_catena` 732), `_avvisa_feed_non_letto` 9599, `risk_block`, `loss_stop` (`RK.loss_stop_active` -> `stats.risk.loss_stop_active`), `fase_ignota`/`pre_match_missing` (6893-6962), copertura dati di controllo (6860).
- E3-046 Attivita' scritte dal servizio: 33 kind propri + `risk_block` + 8 `flumine_*` (Costituzione §12.3 righe 1058-1072), tutti mappati con etichetta italiana e colore in `safeActivity.ts` (`SAFE_ACTIVITY_EXTRA`, 501 righe) [UI: pannello Attivita' di `SafeStrategy.tsx`]. Un kind nuovo va aggiunto li' con test.

**Frontend**

- E3-047 Pagina `SafeStrategy.tsx` (1.705): schede Calcio / Tennis / Storico (`TabsTrigger` 1468-1470); dentro calcio e tennis: Segnali, Opportunita', Monitor, Trade (1477-1489, 1542-1550); testata con stato bot e attivazione paper/live; `RiskPanel.tsx` (188); storico giornaliero (`dailyHistory`, Costituzione §7). Un canale Realtime con debounce 1,2 s (`subscribeSafeBot` `safeBot.ts:1497`, Costituzione §6.8).
- E3-048 `SafeStrategyProvider.tsx` (389): legge la scansione (`safeStrategyScan.ts:343-387`) e per OGNI evento ricalcola in TS contesto, valutazioni e candidati (`SafeStrategyProvider.tsx:316-356`: `buildFootballCtxFromScan`, `evaluateFootballAll`, `evaluateTennis`, `footballCandidates`, `reconcileSignals`). I segnali e i monitor mostrati NON sono quelli del bot: sono i gemelli TS (vedi 3.1).
- E3-049 Tabella dei trade `SafeTradesTable.tsx` (873): gruppi per posizione con gambe di chiusura (`groupClosingLegs` `safeBot.ts:1783`), copertura parziale (`hedgeState` 875, `partialHedge` 1837), stati di uscita (`safeExitStatus.ts`), cash-out in volo (`cashoutInFlight` 827), motivi di attesa (`tradeHold` 1721), pulsante chiudi/riprendi, un toast per posizione (Costituzione §6.4).
- E3-050 `MonitorCard.tsx` (129) e `SignalCard.tsx` (268): mostrano ogni condizione di `ConditionCheck` con valore e verde/rosso/grigio.
- E3-051 `InvestAction.tsx` (375): "Investi" con stake, prezzo visto, modo (paper/live) e verifica della strada (`executionRoute` `safeBot.ts:2225`, `runnerPhase` 2155).
- E3-052 `BotParamsSheet.tsx` (932): vedi E3-028; piu' `ParamsSheet.tsx` (347) per il fallback senza `safe_strategy_bot_v2.sql` (Costituzione §6.7).
- E3-053 `OpportunityGroup.tsx` (637): opportunita'/anomalie/combo/tennis come card con PIAZZA/RIFIUTA e prezzi vivi (`PrezziViviGambe` `safeBot.ts:1346`).
- E3-054 Funzioni di stato e chiamate in `safeBot.ts` (2.256): RPC `get_safe_state`, `safe_activate`, `safe_stop`, `safe_update_params`, `get_safe_activity`, `get_safe_trades`, `safe_request`, `safe_request_approve`, `get_safe_aggregates` (righe 369-1241); Realtime `safe-bot`, `safe_strategy_opportunities`, `safe_strategy_scan`, `safe_strategy_status`; lettura `betfair_live_heartbeat`, `live_follow` (2183-2195). 
- E3-055 Control Room (`comandiBot.ts`): accende/spegne `safe-calcio`/`safe-tennis` per strategia, rilettura fresca prima di un secondo comando (REPERTO A 18/09), `assicuraSoldiVeriServiti`.

---------------------------------------------------------------------------------------------------------------------------------------

## 3. Difetti strutturali

### 3.1 Il motore di strategia esiste due volte (Python nel bot, TypeScript nel browser)

- `engine.py` (2.254) <-> `lib/safeStrategy.ts` (1.731): `evaluateBase` `safeStrategy.ts:898` = `evaluate_base` `engine.py:1227`; `evaluateEsatto` 1129 = 1329; `evaluatePunta` 1214 = 1426; `evaluateTennis` 1413 = 1567; `mergeParams` 312 = `merge_params` 381; `reconcileSignals` 1646 = 1907; `trackScoreStability` 1573 = 1744; `buildFootballCtxFromScan` 648 = `build_football_ctx_from_scan` 691; `DEFAULT_PARAMS` 218 = 196-320.
- Il browser li ESEGUE per costruire segnali e monitor (`SafeStrategyProvider.tsx:316-356`). Se Python e TS divergono, la UI mostra un segnale che il bot non prende (o viceversa): il test di parita' che ho trovato copre solo la banda delle proposte (`genera_oro_banda_strategia.py` -> `frontend/src/lib/bandaStrategia.golden.json`). Un test di parita' completo Python<->TS delle valutazioni **non e' stato trovato nei file che ho letto: non verificato** (Costituzione §2 titolo, riga 125: "parita' col TS").
- Stesso problema per i valori di serie e i clamp (E3-029): sette coppie.

### 3.2 Safe da fermo costa quanto Safe acceso: 232-266 richieste/min (95 % su 4 tabelle)

`run_once` esegue tutte le fasi SEMPRE, anche a bot fermo (commento "SEMPRE, anche a bot fermo: mai posizioni nude", `bot_service.py:10126` e `2395`); solo `scan_and_place` e' dietro `running` (`bot_service.py:10305`). Con ~19 giri/min (60/19,0 PATCH di control = 3,16 s a giro) il costo e' lavoro RIPETUTO, tutto verificato nel codice:

| Chiamata ripetuta | Dove | Per giro | Al minuto (x19) | Misurato 08/10 |
|---|---|---:|---:|---:|
| `read_control` letto due volte nello stesso giro (loop + `run_once`) | `bot_service.py:10839-10850` (da `_un_giro` 10957) e `run_once` 10132 | 2 GET | 38 | 37,9 |
| `set_control(stats, heartbeat_at)` ogni giro, anche senza cambiamenti | `bot_service.py` `run_once` fine (10437), `bot_db.py:70` | 1 PATCH | 19 | 19,0 |
| `pending_requests` due volte (corsia chiusure + passata normale) | `bot_service.py:2698`, chiamata due volte da `run_once` | 2 GET | 38 | 44,6 (con le proposte, +`bot_db.py:689,727`) |
| `fail_stale_processing`: UPDATE incondizionato anche con 0 righe `processing` | `bot_service.py:2688-2693`, `bot_db.py:858-872` | 1 PATCH | 19 | 19,1 |
| Quattro SELECT su `safe_strategy_trades` con filtri vicini: `list_trades("pending")`, `open_trades` x2, `trades_pending_o_aperti` | `bot_service.py:1119`, `2092`, `6711`, `8250` | 4 GET | 76 | 82,0 |
| `get_safe_aggregates` (la cache `_AGG_ULTIMO_BUONO` vale solo come ripiego dopo un guasto) | `bot_service.py:6738`, `bot_db.py:315` | 1 RPC | 19 | 17,9 |

Somma dei sei blocchi per giro: 11 richieste x 19 = 209/min piu' le proposte e il resto = 220,5 misurati (95 % di 232,3). **Nulla di questo cambierebbe una decisione**: sono letture dello stesso stato che il processo gia' possiede. Il 02/10 (254,6) `requests` PATCH erano 53/min contro 19,1 di oggi (`MISURE_2026-10-02.md:44`): non ho verificato quale modifica li abbia ridotti (il salto di `fail_stale_processing` ha una guardia `not solo_chiusure` datata 14/09, `git log -S`, commit `07505baf`, quindi non e' quella). Con posizioni aperte si aggiunge la sbirciata della coda ogni 250 ms (`_sbircia_la_coda` 10744): non misurata separatamente.
Lo scanner fa 81,7/min: `safe_strategy_scan` POST 65,4 (una upsert a batch per giro), `mike_events` GET 5,5, `list_bot_exposures` 5,5, `status` POST 4,7; il POST della scansione e' il 80 % ed esiste per far leggere le righe ad altri processi che poi le rileggono (`bot_db.py:951`, `mike/db.py:553`): scrittura+lettura attraverso Supabase di dati che lo stesso scanner potrebbe consegnare sul canale 47336 (gia' esistente, `service.py:2441`).

### 3.3 Accoppiamenti

- Safe importa `omega_service` (`bot_service.py:302`, `poll_flumine` 826): la coda di fill di flumine vive nel servizio di Omega; D, riga 223 conta la gemella.
- Lo scanner conosce le posizioni degli altri bot (E3-S11): una "scheda dati" fa query su `mike_events`, `omega_*`, `safe_strategy_trades` (`db.py:295-500`).
- Lo scanner ESEGUE il modello `opportunity.py` (`service.py:2391-2440`) e scrive `payload.opportunities`: logica di strategia dentro il produttore dei fatti, e `bot_service.process_opportunities` (7726) la ricalcola con lo stesso modello: due esecuzioni.
- `bot_service.py` mescola decisione e trasporto: `_send_exit` 5686 (218 righe), `_request_place` 2917 (335 righe), `run_once` 350 righe.
- Tre strade d'ordine in `execution.py:1219, 1286, 1382` (C).

### 3.4 Duplicazioni con altri moduli (D, tabella righe 63-88)

| Funzione Safe | Gemella | Somiglianza (D) |
|---|---|---:|
| `ferma_al_nuovo_avvio` `bot_service.py:10083` | mike 3964, omega 7966 | 0,95-0,98 |
| `_avvia_canale` 10572 | mike 6831, omega 8590 | 0,91-0,98 |
| `_ciclo_persistente` 10877 | mike 7289, omega 8773 | 0,87-0,98 |
| `_netto_su_selezione` 1806 | mike 3071 | 0,93 |
| `_richiesta_non_di_questa_riga` 3469 | omega 5943 | 0,98 |
| `_pubblica_stato` 10607 | omega 8753 | 0,90 |
| `_chiudi_all_arresto` 10891 | omega 8789 | 0,98 |
| `_control_per_canale` 10597 | omega 8744 | 1,00 |
| `_scanner_ts`/`_scanner_stato` 4124 | mike 1384 | 0,88 |
| `_avvisa_feed_non_letto` 9599 | mike 7144 | 0,79 |
| `_uscita_del_bot_approvata` 3829 | omega 5891 | 0,80 |
| `bot_db.enqueue_live_order` 1003 | mike 662 | 1,00 |

### 3.5 `bot_db.py` (1.044) contro `db.py` (502): NON sono la stessa cosa

| | `bot_db.py` | `db.py` |
|---|---|---|
| Proprietario | il BOT | lo SCANNER |
| Client | `_sb()` `bot_db.py:51` | `get_supabase_client()` (nel modulo, import di `db.py:16+`) |
| Tabelle | `safe_strategy_control`, `_trades`, `_requests` (coda e proposte), `_activity`, `_opportunities`, `fixtures`, `fixture_analysis`, `betfair_live_order_requests`, RPC `get_safe_aggregates` | `safe_strategy_scan` (upsert/delete), `safe_strategy_status` (upsert), `fixtures`+schede (`load_schede_fixture` 167), `mike_events`/trade degli altri bot per le esposizioni (`list_bot_exposures` 416) |
| Errore su tabella mancante | solleva (il chiamante decide, es. `log` ingoia 77-89) | warning una volta e prosegue (`_warn_missing_table` 27, `_is_missing_table` 40): "mai uccidere lo scanner" |
| Canale locale | pubblica scritte sul canale (`_cb.pubblica_scritte`, 33-50) | nessuno (lo spinge `service.py`) |
| Sovrapposizione | `fixtures_for_window` `bot_db.py:925` ~ `fixtures_window` `db.py:159` (stessa tabella `fixtures`); `fetch_scan_rows` `bot_db.py:951` e `scanner_status` 969 sono il LETTORE di cio' che `db.py:192-236` scrive | |

Domani: una sola cartella per componente: `scanner/` possiede `scan_rows` e `status`; `safe/` possiede `control/trades/requests/activity/opportunities`; la lettura delle fixture e' una libreria condivisa (G).

### 3.6 Stato e conteggi

- Costanti duplicate dei tempi di freschezza fra `exits.py:231-245` e `safeBot.ts:1094-1102` (20 s, 120 s, 45 s).
- `grep -c "^def \|^    def \|^class " bot_service.py` = 302 funzioni in 11.136 righe (media ~37 righe); le piu' lunghe: `_request_place` 335, `run_once` 350, `_proponi_chiusura` 166, `_send_exit` 218, `_process_exit_one` 182.
- `_SPORTS`/`SportState` 420: lo scanner tratta calcio e tennis nello stesso `tick` (calcio e tennis non si mischiano nelle righe, ma condividono il giro).
- Attesa di rete nel percorso critico: il giro del bot spende 11-15 round-trip (1.4) prima di decidere; la riga ha 2,5 s di freno (159) + giro 3,16 s.

---------------------------------------------------------------------------------------------------------------------------------------

## 4. Domani

### 4.1 Struttura (UNA cartella per componente, UN contratto con tipi, UN `COSA_FA.md`)

```
bots/safe/            <- strategia INTOCCABILE (stesse regole, stessi numeri)
   COSA_FA.md
   strategia/  engine.py exits.py risk.py veto.py selezione.py pressure.py
               opportunita/ (opportunity.py tennis_opportunity.py anomaly.py combos.py calibration.py proposte.py)
   adattatore.py     <- Safe come Decisore del contratto D (vedi sotto)
scanner/              <- componente a se' (feed dei fatti): catalogo, stream, punteggi, payload, canale
   COSA_FA.md
bot_runtime/ (D)      <- ciclo, controllo, richieste, coda, arresto, canale, giro veloce
porta_ordini/ (C)     <- piazzamento, annullo, riconciliazione, regolamento
ui/safe/              <- solo vista: legge le valutazioni gia' calcolate, nessun motore
```

### 4.2 Contratto proposto (interfaccia Python; i tipi sono quelli gia' in D)

```python
class SafeDecisore(Decisore):                       # contratto D
    def valuta(self, righe: list[RigaFeed], ctx: CtxCiclo) -> list[Segnale]: ...        # = SafeEngine.evaluate
    def monitor(self, righe: list[RigaFeed]) -> list[Monitor]: ...                     # = SafeEngine.monitors, PUBBLICATO alla UI
    def decidi_uscita(self, pos: Posizione, riga: RigaFeed | None, p: ParamsUscita) -> DecisioneUscita | None: ...  # = exits.decide / decide_time_exit
    def controllo_rischio(self, aperte: list[Posizione], cand: Candidato, agg: Aggregati) -> tuple[bool, str | None]: ...  # = risk.check
    def proposte(self, righe: list[RigaFeed]) -> list[Proposta]: ...                   # = opportunita/anomalie/combo
```

Eventi esposti: `segnale`, `monitor` (nuovo: le valutazioni per la UI), `uscita_decisa`, `proposta`, `scartato(motivo)`. Consumati: `riga_feed`, `esito_ordine`, `controllo`, `richiesta_utente`. Scanner: `publish(riga_feed: RigaFeed)`, `stato_scanner(Stato)`; la riga e' lo STESSO oggetto di oggi (stesse chiavi, `service.py:2531-2723`).

### 4.3 Stima delle righe DOPO (calcolo; sono stime, non misure)

Righe oggi per natura (Python di produzione senza i 3.786 di `certificazione*.py`: 34.635 - 3.786 = 30.849; il resto sotto):

| Blocco | Oggi | Calcolo | Dopo |
|---|---:|---|---:|
| STRATEGIA intoccabile | ~11.800 | `engine` 2.254 + `exits` 1.273 + `risk` 221 + `veto` 233 + `selezione` 525 + `pressure` 149 + `opportunity` 1.103 + `tennis_opp` 521 + `anomaly` 565 + `combos` 620 + `calibration` 431 + `proposte` 742 = 8.637; + parte strategia di `bot_service` (rischio e ingresso 874 + opportunita' 1.801 + `process_anomalies` 125 + decisione d'uscita a modello ~560) = 3.360; totale 11.997 (arrotondato) | **~11.900** (si toglie solo `_proponi*` duplicato nel guscio e le copie di costanti; nessuna regola) |
| SCANNER | ~5.420 | `service` 3.444 + `scanner` 909 + `stream` 567 + `db` 502 | **~4.300**: `db.py` 502 sparisce se le righe viaggiano sul canale/processo (resta un adattatore ~100); `stream.py` condivide il pool con A (stima -150, da confermare con A); tolto il codice del modello opportunita' dal tick (decisione per l'utente) |
| GUSCIO Python | ~13.500 | `execution` 3.093 + `porta_ordini` 784 + `bot_db` 1.044 + `canale_scan` 529 + `arresto_bot` 198 + resto `bot_service` ~7.850 | **~3.500**: ordini/regolamento/piazzamento (1.445 + 522 + `execution` ~2.200 della parte trasporto) passano a C, comuni a tre bot; ciclo/richieste/params/canale (~3.400 di `bot_service`) passano a D (lo scheletro S di D e' 2.301 su 11.136, D riga 45); restano le specificita' Safe (combo, riprendi, proposte, giro veloce ~1.500) + adattatore ~500 + DB specifico ~800 + resto |
| UI TypeScript non test | 11.744 | | **~9.700**: via `safeStrategy.ts` 1.731 (motore gemello) se la UI legge le valutazioni pubblicate; `safeStrategyScan.ts` 406 si riduce (~250); `safeBot.ts` -300 (default duplicati) |
| **Totale Python+TS non test** | ~54.100 (30.849 + 11.744 + banco `certificazione` 3.786 e'a parte) | | **~29.400** |

Calcolo del totale oggi: 30.849 + 11.744 = 42.593 (senza banco). Dopo: 11.900 + 4.300 + 3.500 + 9.700 = 29.400, cioe' -31 %. La strategia (la sola parte che conta per i soldi) NON diminuisce di una regola.

### 4.4 Confronto di intervento

- OGGI per sostituire Safe (cambiare il tipo di segnale o l'ordine) si toccano: `engine.py`, `bot_service.py` (11.136 righe), `execution.py`, `bot_db.py`, `porta_ordini.py`, `risk.py`, `exits.py`, `safeStrategy.ts`, `safeBot.ts`, `BotParamsSheet.tsx`, `SafeStrategyProvider.tsx`, `registro_bot.py`, le migrazioni SQL delle RPC (`safe_*`), e `service.py` se cambia il feed: 13-15 file.
- DOMANI: solo `bots/safe/` + i suoi test di contratto (il banco e il registro leggono il contratto, non il file).
- Per sostituire lo SCANNER oggi: `service.py`, `scanner.py`, `stream.py`, `db.py`, `canale_scan.py`, `mike/db.py:553`, `bot_db.py:951`, `scan_feed.py`, `scalper_service.py:110`, `auto_follow.py:474`, `safeStrategyScan.ts`; domani: la cartella `scanner/` + il contratto `RigaFeed`.

### 4.5 Gia' in una libreria matura e oggi riscritto

- Stream di mercato: flumine/betfairlightweight (`create_stream`, `MarketStream`) fa ripresa con `initialClk/clk`; lo scanner `stream.py:418-427` ricostruisce a ogni riconnessione (A, riga 170-171, D1). Il pool di shard `stream.py:161-567` e' codice nostro.
- Matching/ordini: flumine (blotter, `Order`, FOK, `process_orders`): `_paper_ladder` `bot_service.py:5986` e la riconciliazione REST (1117-1700) sono riscritture parziali di cio' che flumine gia' sa.
- Cambio valuta, retry e rate-limiting: `requests`/betfairlightweight; `_REQ_DELAY` 0,35 s (176) e `_BOOK_CHUNK` 25 (174) sono rate-limit manuali.

---------------------------------------------------------------------------------------------------------------------------------------

## 5. Parita'

Cosa deve coincidere "numero per numero" dopo ogni passo: decisioni (id e `ok` di ogni `ConditionCheck`, stato `signal/no/nd`), segnali (chiave `signal_key`), ordini (market_id, selection_id, side, prezzo, size, `strategy`, `mode`), istanti, uscite (`reason`, `kind`), P&L netto per partita, riga `payload` dello scanner (stessa `payload_signature`), righe di attivita' per `kind`.

Registrazioni e scenari (banco, punto d'ingresso unico `python -m Betfair.stream.backtest.certifica safe_base ...`, registro `registro_bot.py:255-290`):

- Calcio: registrazione `35760084` (referti `AUDIT_2026-09-28/replay/safe_*_rapidi_entrambi_35760084_2026-09-28.txt`); 22 partite nel profilo completo.
- Tennis: registrazione `35795993` (`AUDIT_2026-09-28/replay/safe_tennis_rapidi_entrambi_35795993_2026-09-28.txt`).
- Scenari `SCENARI_DESCRITTI` (`tools/replay_registrazioni.py:211+`): `base` (tre strategie in live come in produzione), `cap-stretto`, `bot_fermo` (nessuna apertura, uscite e protezioni continuano), `esiti_ignoti`, `feed_stantio` (riga E scanner vecchi: nessun ingresso), `riavvio` (difetto 19), `paper` (solo misura), `ordini`/`ordini-manuali` (Investi + Chiudi dalla UI), `due_lay`, `manuale_e_bot` (T12/T13).
- Referti piu' recenti (letti io):
  - `AUDIT_2026-10-04/replay/safe_base_tutti_PUNTE_MULTIPLE.txt`: riga 2143 "22 partite senza violazioni, 0 con violazioni, 0 senza decisioni", riga 2255 `durata=258s` (certificazione completa in 4 min 18 s, dentro il tetto dei 5 min della regola 7: `PROCESSO_STANDARD_BOT.md` §6.9). Il precedente `..._PRIMA_4dd624a.txt`: stesso esito, `durata=287s`.
  - `safe_base_rapidi_entrambi_DOPO.txt` e `..._PUNTE_MULTIPLE.txt`: `ESITO: OK`, 63,4 s e 62,2 s, 18 scenari di trasporto (nei referti PUNTE_050 e DOPO), KO 0. `..._PUNTE_050.txt` riga 141: `ESITO: KO` (causa non letta: reperto aperto da riguardare con il coordinatore; superato da `PUNTE_MULTIPLE` OK).
  - `safe_tennis_rapidi_entrambi_TETTO.txt`: `ESITO: OK`, 8,5 s.
  - `AUDIT_2026-10-02/replay/safe_base_entrambi_MASTER_d56bb3b.txt`: `ESITO: KO` per `PARITA' coda/canale NON RAGGIUNTA` (ordini coda 0, canale 2; 14 scenari di trasporto OK): superato dai referti del 04/10 ma e' la riga da cui nasce la richiesta di parita' sulla strada d'ordine; da citare come precedente.
  - Scanner: `AUDIT_2026-09-30/replay/*_SCANNER_VELOCITA*.txt` (mike/omega/safe) e `AUDIT_2026-10-02/replay/*MASTER*` (non letti per intero: citati come esistenti).
- Controlli: `certificazione.py` (regole B1-B14... da `_b1` 277 a `_b14` 535 e oltre; Base/Esatto/Punta contro `SPEC_STRATEGIA_S.md`), `certificazione_k.py` (consapevolezza dell'ordine, catalogo §7 n.36), `certificazione_tennis.py`.
- Test: Python 92 file / 39.451 righe in `Betfair/safe_strategy/tests/`; frontend `safeStrategy*.test.ts` (829+...), `safeBot.test.ts` 910, `safeBot.contracts.test.ts` 509, `SafeStrategy*.test.tsx`, fotografie `frontend/src/fotografia/snapshot/safe-strategy.{off,v2}.json`.

Per la nuova struttura: (1) replay `certifica` di tutte e 22 le partite e gli scenari sopra devono dare lo STESSO referto (conteggi di decisioni, azioni, violazioni; per la partita 35760084 `decisioni=3512`, riga `PARITA'` del referto d56bb3b); (2) parita' della UI: i `monitor` pubblicati dal bot devono eguagliare, valutazione per valutazione, l'uscita di `safeStrategy.ts` oggi (golden da generare con l'estensione di `genera_oro_banda_strategia.py`); (3) scanner: stessa `payload_signature` per le stesse sequenze di book (registrazioni `registrazioni_banco/`); (4) conteggio richieste al minuto con `strumenti/misure/m04_chiamate_db.py`.

Voci di `PROCESSO_STANDARD_BOT.md`: §6.1 (stream registrato, 35760084), §6.2 (scanner vero, `feed_stantio`, `SCANNER_VELOCITA`), §6.3 (servizio intero: `bot_fermo`, `riavvio`), §6.4 (ordine con parziali e bet delay: `ordini`, `esiti_ignoti`, `due_lay`, `manuale_e_bot`, `certificazione_k`), §6.5 (persistenza e UI: vitest + fotografie), §6.6 (concorrenza: `coord_safe_omega`, scenario manuale+bot), §6.7 (scenari e falsificazione: `tools/falsifica_*`), §6.8 (referto riproducibile), §6.9 (258 s). §7: n.8-16 simulazione (banco comune), n.19 (stato in RAM: `riavvio`), n.21 (paper+live: `aggregates(mode)`), n.22 (`ferma_al_nuovo_avvio`), n.23 (`stats` timbrate), n.24 (RPC activate), n.25 (`modalita_di_strategia`), n.26 (`execution_mode`); copertura dei 35 punti non verificata riga per riga in questa scheda.

---------------------------------------------------------------------------------------------------------------------------------------

## 6. Migrazione

1. **Prima** di toccare Safe: contratto D (`Plugin/Decisore/Ospite`) e C (porta ordini) approvati: Safe e' l'ultimo bot da migrare (il piu' grande, `bot_service.py` 11.136 righe, e il solo con giro veloce).
2. Passo 0 (senza rischio, solo Python): mettere cache e un solo lettore nel giro: una lettura di `control` per giro, una lista di `trades` per giro riusata da settlement/rischio/proposte, `fail_stale_processing` solo ogni N s, heartbeat solo ogni 10 s o a cambio. **Non cambia nessuna decisione**: il referto deve restare identico (replay completo) e il conteggio scende da ~232 a ~60/min stimati (11 richieste/giro x 19 = 209 -> ~3 + eventi). E' lo stesso consiglio che D e 07 danno per i servizi.
3. Passo 1 (ombra): `SafeDecisore` esposto dal nuovo modulo accanto a `bot_service`; per N giorni entrambi valutano le stesse righe, confronto automatico delle `Segnale`/uscite; il vecchio resta l'unico che piazza.
4. Passo 2: la UI legge i `monitor` pubblicati (nuovo evento) e `safeStrategy.ts` va in ombra con confronto automatico (il test di parita' completo Python<->TS e' il prerequisito).
5. Passo 3: scanner come componente a se' con il canale come strada primaria e il DB come ripiego/diario; poi si spegne `fetch_scan_rows` come fonte primaria dei bot.
6. Taglio del vecchio: dopo replay identico, paper di confronto (§4 del processo) e firma di chi ha rieseguito il replay. Ritorno indietro: interruttore per componente (come `SAFE_BOT_LEGGE_CANALE`, `bot_service.py:9512`); le righe di scan e le tabelle `safe_strategy_*` restano le stesse (nessuna migrazione SQL obbligatoria nei primi passi).
7. Rischi: (a) la rimozione del motore TS cambia cio' che la UI mostra se il bot e' fermo (oggi la UI valuta anche a bot fermo): serve che i `monitor` siano pubblicati dallo scanner/dal bot anche a bot fermo; (b) lo scanner e il bot oggi sono sfasati di 2,5-5,7 s: ridurli e' un cambiamento di comportamento nel tempo (non nella regola), da confrontare col replay; (c) il bot dipende da `omega_service` per la coda flumine: estrarre prima la coda in C; (d) `SPEC_STRATEGIA_S.md` non e' tracciato: va committato prima che il banco lo cita come `spec`.

---------------------------------------------------------------------------------------------------------------------------------------

## 7. Misure

| Misura | Oggi (fonte) | Obiettivo dopo |
|---|---|---|
| Richieste Supabase al minuto, bot | 254,6 (02/10), 265,8 (04/10), 232,3 (08/10, p95 259) (`07_MISURE_OGGI.md:213`) | <= 20/min a bot fermo, <= 40 con posizioni (stima: heartbeat 6/min + eventi) |
| Richieste al minuto, scanner | 85,1 / 88,9 / 81,7 (`07:215`) | <= 20 con il canale come strada primaria e il DB solo diario (la scrittura POST scende da 65,4 a ~6-12/min) |
| Giri/min del bot | ~19 (60/19,0 PATCH control; calcolo mio) | invariato per le regole; la cadenza `poll_interval_s` e' un parametro di strategia |
| Latenza riga -> decisione | freno 2,5 s dello scanner + giro 3,16 s + 92-307 ms PostgREST (`LATENZA_TENNIS_2026-09-17.md`, storica; `07:244`) | < 0,5 s sul canale (misura: `ts_pub_ms` vs `ricevuto_ms`, `07` riga 135) |
| Decisione -> ordine sul motore (tennis, `/comando`) | 84, 108, 194 ms (n=3, `07:30,151-153`) | <= oggi |
| Certificazione completa del banco | 258 s (04/10), 287 s (04/10 PRIMA) | <= 300 s |
| Righe Python+TS non test | 42.593 (30.849 + 11.744) | ~29.400 (4.3) |
| Memoria / CPU del bot e dello scanner | `07` righe 265, 267: `safe-strategy-bot` 52,4 (CPU 3,4), `safe-strategy-service` 33,2 (2,1) (unita' della tabella `07`, non riletta qui) | invariate o inferiori |
| Numero di chiamate Betfair/min dello scanner | non misurato (solo Supabase in `07`) | misurare con un contatore per tipo (`listMarketBook`, IPS, catalogo) nel `Cronometro` (`service.py:3175`) |
| Funzioni duplicate fra bot (D) | ~600 righe gemelle fra Safe, Mike, Omega (D tabella 63-88) | 0 (diventano `bot_runtime/`) |

---------------------------------------------------------------------------------------------------------------------------------------

## Decisioni per l'utente

1. **Motore TS nella UI**: eliminare `safeStrategy.ts` (1.731 righe) facendo pubblicare le valutazioni al bot/scanner ha un effetto visibile (la UI non valuta piu' da sola, ne' a bot fermo senza scanner). Le regole non cambiano. Serve il suo OK.
2. **Il modello `opportunity.py` eseguito DUE volte** (scanner per `payload.opportunities`, bot per le proposte): scegliere dove vive. Non cambia le soglie.
3. **`SPEC_STRATEGIA_S.md` non e' tracciato da git** e il registro lo cita come spec: committarlo? Inoltre il suo testo sulla quota della Base ("Lettura A", `favLive` 1,20-1,34) e' SUPERATO dalla decisione del 25/09 (`dogLayMin/Max` 20-34, `migrations/safe_base_banca_20_34_2026-09-25.sql:1-12`; `engine.py:196-208`): il codice e' conforme alla decisione, il documento no: aggiornare il testo.
4. **Safe fermo = 232 richieste/min**: confermare il passo 0 (cache di lettura nel giro) come primo lavoro: non tocca decisioni, ma modifica il codice di un bot che puo' avere posizioni vive (riavvio dell'app a cura dell'utente).
5. **`base_control_exit`** nasce spenta (E3-015): non e' toccata; segnalo che la sua copertura dati (corner/cartellini IPS) e' ancora non misurata (docstring `exits.py:969-987`).

## Cosa ho verificato di persona / cosa non ho potuto verificare

Verificato leggendo il codice: mappa degli intervalli (indici `grep`), `run_once` e `_un_giro` interi (10115-10463, 10902-11050), `process_requests` (2669-2768), `fail_stale_processing` e `read_control`/`set_control`/`aggregates`/`open_trades`/`trades_pending_o_aperti` (`bot_db.py`), `engine.py` 196-320, 1203-1330, ossatura di `evaluate_esatto/punta`, `exits.py` 69-92, 202-315, 949-1074, `risk.py` 37-45, 185-220, `service.py` `tick` 2979-3175, `publish` 2839-2855, `db.py` 192-236, registro del banco 250-290 e 405-416; le conteggi di funzionalita' UI (82 chiavi) con `grep -o | sort -u`; i referti 04/10 con `grep ESITO/durata`; i conteggi di righe con `wc -l` (e `strumenti/e3_righe_safe.py` per la ripartizione di `bot_service.py`).

NON verificato: (1) la causa del `ESITO: KO` di `safe_base_rapidi_entrambi_PUNTE_050.txt` e del crollo di `requests` PATCH 53 -> 19/min fra 02/10 e 08/10; (2) il corpo di `poll_flumine_pending` (omega_service) e quante richieste DB fa; le letture `proposte_opportunita`/`proposte_di_chiusura_vive` per giro (non so se sono gated da `opps_interval_s`); (3) il test di parita' Python<->TS completo delle valutazioni (non trovato); (4) il registro di `safe_tennis` (righe 283-300 di `registro_bot.py` non lette) e il contenuto dei referti SCANNER_VELOCITA; (5) le righe esatte delle singole condizioni di `evaluate_tennis` oltre l'inizio funzione 1567 e i testi dei 12 gate di `scan_and_place` (citati per nome, funzione 7052-7409); (6) il numero reale di chiamate Betfair/min dello scanner; (7) la ripartizione strategia/guscio e' una STIMA (confini scelti da me nella mappa 1.2: ad esempio `exits` in `bot_service` 2.229 righe contano per ~560 righe di strategia); (8) i 35 punti di §7 non sono stati incrociati uno per uno.
