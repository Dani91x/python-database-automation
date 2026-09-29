# Inventario Mike - AREA D: il giro del servizio e i conti

**Intervallo letto (tutto, riga per riga):**
- `Betfair/mike/service.py` righe 3250-6099 (da `_request_cancel` alla fine). Per capire le chiamate
  ho letto anche, fuori area e solo quanto basta: righe 40-99 (costanti), 300-400 (cache), 480-530
  (firma sostanziale), 1027-1346 (regolamento REST, aggregati in cache, ripiego REST, freno dei log,
  parametri per modalita'), 1727-1771 (freni della lay appoggiata).
- `Betfair/mike/feed.py` righe 1-460 (tutto).
- `Betfair/mike/db.py` righe 1-644 (tutto).
- `Betfair/mike/dossier.py` righe 1-411 (tutto).
- `Betfair/mike/config.py` (tutti i valori), `Betfair/mike/COSTITUZIONE_MIKE.md` §0-§7, §9-§13, §16-§17, §16.4-bis blocchi 9-10.
- Fuori area, solo le righe citate: `Betfair/stream/flusso_prezzi.py` 84-323, `Betfair/stream/avvio_app.py` 123-330,
  `Betfair/stream/sveglia_canale.py` 61-84 e 172-202, `Betfair/safe_strategy/risk.py` 123-137,
  `Betfair/mike/engine.py` 44-50, 938-975, 813-830, 1822-1850.

**Numero di schede: 108.**

## Elenco di TUTTE le funzioni e classi dell'intervallo, con la scheda che le copre

### service.py (3250-6099)
| funzione / classe / costante | riga | scheda |
|---|---:|---:|
| `_request_cancel` | 3253 | 62 |
| `_request_flatten` | 3283 | 63 |
| `ferma_al_nuovo_avvio` | 3396 | 4 |
| `run_once` | 3430 | 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19 |
| `_operating_day_start_ts` | 3801 | 21 |
| `_operating_day_key` | 3808 | 21 |
| `_ctx_legs_of` | 3818 | 22 |
| `_open_liability` | 3822 | 22 |
| `posti_occupati_per_modo` | 3841 | 15 |
| `_cadenza_battito` (con dentro `_num`) | 3864 / 3881 | 20 |
| `partite_di_modalita_diversa` | 3898 | 11 |
| `_first_placed_at` | 3911 | 23 |
| `_locked_open_pnl` | 3917 | 23 |
| `_config_warn` | 3949 | 24 |
| `_LOSS_EXIT_DECISO_MIN_S` | 3979 | 25 |
| `_firma_loss_exit_deciso` | 3982 | 25 |
| `_run_event` (con dentro `closes_id`) | 3995 / 4389 | 26-50 (closes_id: 43) |
| `_event_rows` | 4682 | 51 |
| `_trade_ids_by_ref` | 4703 | 52 |
| `_trade_row_for_leg` | 4714 | 53 |
| `_trade_unknown_outcome` | 4722 | 54 |
| `_open_refs_by_event` | 4739 | 55 |
| `_mirror_is_aligned` | 4759 | 56 |
| `_gamba_dalla_riga` | 4775 | 57 |
| `_aggancia_riserve_orfane` | 4813 | 58 |
| `_reconcile_trades` | 4874 | 59 |
| `_reconcile_unknown` | 4977 | 60 |
| `_mark_trade_cancelled` | 5077 | 61 |
| `_SETTLE_ROWS_MAX_TRIES` | 5189 | 64 |
| `_retry_settle_rows` | 5192 | 64 |
| `_settle_params` | 5220 | 65 |
| `_settle_trades` (con dentro `_pnl_of`) | 5256 / 5342 | 66 |
| `_DOSSIER_RETRY_SEC` | 5366 | 14 |
| `dossier_da_ritentare` | 5369 | 14 |
| `_retry_dossier` | 5387 | 14 |
| `_gambe_vive` | 5411 | 67 |
| `_cadenza_pubblicazione` | 5424 | 68 |
| `_scrivi_evento` | 5438 | 69 |
| `_persist` | 5474 | 70 |
| `_svuota_lotto` | 5519 | 71 |
| `_PORTA_CANALE` | 5552 | 72 |
| `_avvia_canale` | 5555 | 72 |
| `_SVEGLIA`, `_ASCOLTO_SCAN` | 5584-5585 | 74 |
| classe `_AlzaSveglia` (`__init__`, `set`) | 5588 / 5603 / 5606 | 74 |
| `_evento_seguito` | 5610 | 74 |
| `_pavimento_sveglia` | 5620 | 75 |
| `_su_sveglia_dal_canale` | 5635 | 74 |
| `_avvia_sveglia` | 5649 | 74 |
| `_client_scan_alza_sveglia` | 5688 | 75 |
| `statistiche_sveglia` | 5697 | 75 |
| `_dormi_o_sveglia` | 5712 | 75 |
| `ENV_MIKE_LEGGE_CANALE`, `_RISINC_FEED_S`, `_CANALE_FEED` | 5754-5761 | 76 |
| `_canale_feed_acceso` | 5764 | 76 |
| `avvia_client_scan` | 5771 | 76 |
| `azzera_canale_scan` | 5812 | 76 |
| `_canale_copre_tutte` | 5828 | 77 |
| `_righe_del_feed` | 5858 | 77 |
| `statistiche_canale_scan` | 5905 | 77 |
| `_FUORI_DAL_PUSH` | 5950 | 73 |
| `_pubblica_evento` | 5953 | 73 |
| `_pubblica_stato` | 5961 | 73 |
| `_ciclo_persistente` | 5971 | 3 |
| `main` (con dentro `_un_giro`) | 5987 / 6035 | 1, 2 |

### feed.py
| funzione / classe | riga | scheda |
|---|---:|---:|
| classe `EventInfo` (`complete`, `market_id`, `selection_id`, `selection_name`) | 26 / 38 / 43 / 46 / 49 | 78 |
| `parse_iso_epoch` | 54 | 79 |
| `_num` | 67 | 79 |
| `blocco_osservato` | 74 | 80 |
| `mercati_fermi` | 98 | 81 |
| `mercati_di_mike` | 107 | 81 |
| `flusso_esito` | 119 | 81 |
| `payload_blocchi_ou` | 131 | 80 |
| `blocco_da_rest` | 143 | 82 |
| `ou_blocks` | 164 | 80 |
| `event_info` | 194 | 78 |
| `_book_for` | 218 | 83 |
| `implied_p4` (con dentro `p_over`) | 233 / 235 | 84 |
| `market_totals` (con dentro `p_over`) | 249 / 265 | 84 |
| `ht_active_from_payload` | 286 | 85 |
| `goals_from_payload` | 294 | 85 |
| `_hard_max_age` | 304 | 86 |
| `feed_fresh` | 316 | 86 |
| `order_fresh` | 339 | 87 |
| `snapshot_from_row` | 374 | 88 |
| `is_candidate` | 443 | 89 |

### db.py
| funzione / costante | riga | scheda |
|---|---:|---:|
| `_CANALE_ACCESO`, `CONTROL_ID`, `T_CONTROL`, `T_EVENTS`, `T_TRADES`, `T_ACTIVITY`, `T_REQUESTS`, `PAGE_SIZE`, `_AGG_RPC`, `_TOTALS`, `_TOTALS_TTL_S` | 30-45 | 90 |
| `_sb` | 48 | 90 |
| `_now_iso` | 52 | 90 |
| `read_control` | 59 | 91 |
| `set_control` | 64 | 91 |
| `log` | 71 | 92 |
| `STATI_TERMINALI` | 88 | 93 |
| `filtro_finestra_eventi` | 91 | 93 |
| `list_events` | 99 | 93 |
| `get_event` | 116 | 93 |
| `upsert_event` | 121 | 93 |
| `upsert_events` | 144 | 93 |
| `delete_events` | 167 | 93 |
| `insert_trade` | 175 | 94 |
| `update_trade` | 183 | 94 |
| `get_trade` | 191 | 94 |
| `open_trades` | 196 | 94 |
| `trades_for_event` | 210 | 94 |
| `live_trades` | 215 | 94 |
| `all_trades` | 240 | 94 |
| `aggregate_rows` (con dentro `_placed_at`, `_in_day`) | 252 / 277 / 281 | 95 |
| `_ERRORI_RPC_ASSENTE`, `_rpc_assente` | 345 / 349 | 95 |
| `aggregates` | 356 | 95 |
| `_cumulative_totals` | 401 | 95 |
| `pending_requests` | 417 | 96 |
| `requests_da_lavorare` | 422 | 96 |
| `set_request_status` | 454 | 96 |
| `fail_stale_processing` | 474 | 96 |
| `fetch_scan_rows` | 508 | 97 |
| `scanner_status` | 518 | 97 |
| `fixture_id_for_event` | 531 | 98 |
| `fixture_lambdas` | 560 | 98 |
| `fixture_analysis` | 576 | 98 |
| `ht_ft_rows` | 588 | 98 |
| `live_follow_status` | 601 | 99 |
| `runner_heartbeat` | 607 | 99 |
| `enqueue_live_order` | 613 | 99 |
| `get_live_order_request_by_ref` | 619 | 99 |
| `get_live_order_request` | 626 | 99 |
| `revoke_live_order_request` | 633 | 99 |
| `get_live_order_mirror` | 641 | 99 |
| (sintesi: cosa si rilegge al riavvio) | - | 100 |

### dossier.py
| funzione / costante | riga | scheda |
|---|---:|---:|
| `DEFAULT_RHO`, `MAX_GOALS`, `_AVVISATO` | 18-22 | 102 / 101 |
| `load_atlas` | 25 | 101 |
| `_p_total` | 42 | 102 |
| `p4_from_lambdas` | 46 | 102 |
| `_id_int` | 59 | 102 |
| `build_prematch` | 66 | 102 |
| `combine_hazard` | 114 | 105 |
| `cover_gain_pct` | 126 | 106 |
| `_EMPIRICAL_CACHE`, `_EMPIRICAL_FAILED`, `_EMPIRICAL_RETRY_S` | 136-138 | 107 |
| `get_empirical` | 141 | 107 |
| `p_total_from_grid` | 174 | 108 |
| `p_total_empirical` (con dentro `totals`) | 183 / 196 | 107 |
| `_p_le` | 213 | 108 |
| `model_probs_from_grids` (con dentro `trio`) | 217 / 225 | 108 |
| `lambdas_con_ripiego` | 241 | 103 |
| `live_frame` | 298 | 104 |

**Costanti del modulo service citate nelle schede (definite fuori intervallo, righe 47-62):**
`_LOCK_PORT` = env `MIKE_LOCK_PORT`, default 47319 (`service.py:47`, `config.py:32`);
`_PENDING_STALE_S` = 120 s (`service.py:50`); `_SETTLE_RETRY_S` = 30 s (`:51`); `_SETTLE_MAX_WAIT_S` = 7200 s = 2 ore (`:52`);
`_ROW_MISSING_GRACE_S` = 600 s = 10 minuti (`:54`); `_MATCH_OVER_S` = 10800 s = 3 ore (`:55`);
`_MATCH_LIKELY_OVER_S` = 6000 s = 100 minuti (`:56`); `_CRITICAL_LOG_EVERY_S` = 45 s (`:61`); `_STALE_REQUEST_MIN` = 10 minuti (`:62`).

---

# PARTE A - IL GIRO PRINCIPALE DEL SERVIZIO

### 1. L'accensione del servizio Mike
- **Cosa fa**: quando il programma di Mike parte, prende il "posto unico" (una sola copia di Mike puo' girare), accende i canali verso lo schermo, la sveglia rapida e l'eventuale lettura veloce dello scanner, poi controlla se l'app e' appena stata riaperta (in quel caso Mike si ferma) e carica l'atlante dei gol.
- **Quando scatta**: all'avvio del processo `python -m Betfair.mike.service`. Due opzioni: `--once` (fa un solo giro ed esce, per collaudo) e `--dry` (nessun ordine vero: le azioni vengono solo scritte come "avrei piazzato").
- **Cosa succede dopo**: 
  1. senza `--once` prende il blocco sulla porta 47319 (se un'altra copia lo tiene, non parte una seconda);
  2. imposta i tempi massimi di attesa del database per il profilo bot (commento: collegamento 5 s, lettura 20 s; non verificato nel codice di `db_client`); se non ci riesce, avviso e si prosegue;
  3. senza `--once`: accende il canale locale 47333 (scheda 72), attiva la rilettura del saldo del conto dopo ogni ordine vero o regolazione (`omega_market.attiva_saldo_su_evento("mike")`), la sveglia (scheda 74) e il lettore del canale dello scanner (scheda 76);
  4. attiva la guardia d'avvio e chiama il controllo "fermo al nuovo avvio" (scheda 4);
  5. carica l'atlante dei gol (scheda 101) e comincia il giro continuo (schede 2 e 3).
- **Numeri**: porta del blocco 47319 (env `MIKE_LOCK_PORT`, default `config.LOCK_PORT_DEFAULT`); porta del canale verso lo schermo 47333 (env `MIKE_LOCAL_WS_PORT`).
- **Esempio**: l'utente riapre l'app alle 14:00; il servizio parte, trova nel database `status=running, mode=live` di ieri: lo riporta a `stopped` e `paper` prima del primo giro.
- **Cosa vede l'utente**: niente di diretto; se Mike e' stato fermato, un'attivita' di tipo avvio app (scheda 4).
- **Dove**: `service.py:5987-6095` (`main`); blocco 5996-5997; timeout 6003-6008; canali 6013-6027; guardia 6031-6032; atlante 6033.
- **Paper o live**: identico.

### 2. Il giro singolo e il suo ritmo (quanto aspetta fra un giro e l'altro)
- **Cosa fa**: ogni giro esegue tutto il lavoro di Mike (scheda 5 e seguenti), poi dorme. Dorme poco se c'e' movimento (partita in gioco, ordine vivo, richiesta dell'utente, azioni fatte), di piu' se non succede niente.
- **Quando scatta**: in continuo, dopo ogni dormita.
- **Cosa succede dopo**:
  1. se la guardia d'avvio non ha ancora concluso il controllo (database muto all'avvio), lo ritenta (scheda 4);
  2. prende i parametri dell'ULTIMO giro (non rilegge il controllo due volte);
  3. passo attivo = massimo fra 1 s e (`decide_min_interval_ms` / 1000 x 2);
  4. ricarica l'atlante se il file e' cambiato (se sparisce resta l'ultimo buono);
  5. esegue il giro (`run_once`);
  6. se non c'e' fretta E non ci sono azioni E nessun regolamento, il passo diventa il massimo fra passo attivo e `idle_cycle_s`;
  7. se ci sono novita' (nuove partite, azioni, regolamenti, richieste) le scrive nel registro del processo;
  8. se un giro solleva un errore imprevisto: lo registra, scrive un'attivita' `error` con motivo `cycle_exception`, e il ciclo NON muore (si dorme e si riprova);
  9. Ctrl+C = fine; con `--once` si esce dopo un giro.
- **Numeri**: `decide_min_interval_ms` = 500 (config, min 100, max 5000; modificabile da UI) -> passo attivo 1,0 s; `idle_cycle_s` = 5,0 s (config, 1-60, UI); passo iniziale di sicurezza 2,0 s se il giro esplode prima di calcolare.
- **Esempio**: di notte, nessuna partita in gioco e nessun ordine: il giro si ripete ogni 5 s. Alle 20:45 una partita va in gioco: `fretta` diventa vera e il giro torna a 1 s.
- **Cosa vede l'utente**: niente; un errore di giro compare come attivita' `error` (`cycle_exception`).
- **Dove**: `service.py:6035-6082` (`_un_giro`); passo 6051; fretta 6061-6062; errore 6070-6077; dormita 6081.
- **Paper o live**: identico.

### 3. L'arresto ordinato chiesto dall'app
- **Cosa fa**: prima di ogni giro controlla se l'app ha chiesto di spegnere i servizi in modo ordinato; se si', Mike esce senza iniziare un altro giro (il guardiano non lo rilancia).
- **Quando scatta**: prima di OGNI giro, tranne con `--once`. La richiesta c'e' se esiste il file d'arresto scritto dopo l'avvio di questo processo (tolleranza 2 s).
- **Cosa succede dopo**: uscita pulita, rilascio del blocco sulla porta 47319.
- **Numeri**: tolleranza 2 s sull'ora del file (`arresto_ordinato.richiesto`).
- **Esempio**: l'utente chiude l'app: il giro in corso finisce, al controllo successivo Mike esce.
- **Cosa vede l'utente**: niente (riga nel registro del processo "ARRESTO ORDINATO richiesto dall'app: esco").
- **Dove**: `service.py:5971-5984` (`_ciclo_persistente`); chiamata 6089; rilascio blocco 6090-6095.
- **Paper o live**: identico. Nota: un giro gia' iniziato non viene interrotto.

### 4. All'avvio nuovo dell'app Mike si ferma da solo
- **Cosa fa**: se il processo appartiene a un'apertura NUOVA dell'app, Mike viene messo in "fermo" e in "paper", e l'interruttore delle uscite torna su manuale. Se invece e' solo un riavvio dopo un crash (stessa apertura dell'app), non tocca niente.
- **Quando scatta**: una volta all'avvio (`main`) e, finche' non riesce, all'inizio di ogni giro.
- **Cosa succede dopo**:
  - lettura della riga di controllo fallita -> nessuna decisione, si riprova al giro dopo; intanto la guardia BLOCCA le aperture (scheda 6);
  - nessuna riga di controllo -> controllo considerato fatto;
  - altrimenti confronta l'identificativo dell'apertura dell'app (`APP_BOOT_ID`) con quello salvato nelle statistiche: uguale -> nulla; diverso o assente -> scrive `status=stopped`, `mode=paper`, `stopped_at`, statistiche con il nuovo identificativo, e parametri con `uscite_automatiche` riportato a manuale; scrive un'attivita' solo se c'era davvero qualcosa da spegnere (era `running`/`stopping`/`error`, o `live`) o se le uscite sono state riportate a manuali.
  - Soglie, importi e tetti NON vengono toccati.
- **Numeri**: nessuno.
- **Esempio**: ieri sera Mike era acceso in live; stamattina l'utente riapre l'app: Mike riparte fermo e in paper; le posizioni gia' aperte restano sorvegliate (coperture, uscite, regolamento continuano).
- **Cosa vede l'utente**: Mike fermo in paper; un'attivita' di avvio app con "i bot li accende l'utente: status=stopped, mode=paper".
- **Dove**: `service.py:3396-3427`; logica vera in `Betfair/stream/avvio_app.py:217-330` (fuori area).
- **Paper o live**: e' proprio il passaggio che riporta il live a paper.

### 5. Inizio del giro: lettura del controllo e della modalita'
- **Cosa fa**: legge la riga di controllo (stato del bot, modalita' paper/live, parametri). Se non riesce a leggerla o non esiste, il giro intero viene saltato.
- **Quando scatta**: ogni giro.
- **Cosa succede dopo**: lettura fallita -> giro saltato (`control_unreadable`); riga assente -> giro saltato (`no_control`). Lo stato di default e' `idle`; la modalita' se non e' `paper` o `live` diventa `paper`. I parametri passano dalla lista ammessa (`config.merge_params`: default, taglio ai minimi/massimi, coppie min/max invertite tornano entrambe al default). Si ricordano come "parametri dell'ultimo giro" per la dormita.
- **Numeri**: tutti i default in `config.PARAM_SPEC`.
- **Esempio**: database irraggiungibile: nessun giro, nessuna azione, nemmeno le protezioni (il giro e' saltato per intero).
- **Cosa vede l'utente**: niente (il battito smette di aggiornarsi; la pagina lo giudica con la cadenza della scheda 20).
- **Dove**: `service.py:3433-3448`.
- **Paper o live**: la modalita' letta qui e' quella del bot; ogni partita tiene pero' la SUA (scheda 26).

### 6. Il bot "in esecuzione" apre, il bot fermo protegge soltanto
- **Cosa fa**: decide se in questo giro sono ammesse nuove aperture. Con bot fermo (o guardia d'avvio non conclusa) si spengono ingresso pre-partita, re-ingresso e ultimo ingresso; coperture, uscite, annulli e regolamento continuano.
- **Quando scatta**: ogni giro.
- **Cosa succede dopo**: `running` = stato `running` E guardia d'avvio non bloccante. Se falso: `pre_enabled`, `reentry_enabled`, `last_entry_persist` forzati a spenti nei parametri effettivi. Inoltre, se la modalita' e' live, `pre_exit_mode=resting` e `live_resting_enabled` spento, l'uscita appoggiata diventa `taker` (scheda 26).
- **Numeri**: nessuno.
- **Esempio**: l'utente preme "Ferma": la partita con un back Under aperto continua a essere coperta e chiusa, ma nessuna partita nuova parte.
- **Cosa vede l'utente**: nelle statistiche `stop_ferma_solo_aperture: true` (il pulsante deve dirlo).
- **Dove**: `service.py:3452-3453`; `_params_for` a `service.py:1268-1276` (fuori area).
- **Paper o live**: identico.

### 7. Le richieste della pagina lette una volta sola, e quelle rimaste appese chiuse
- **Cosa fa**: legge in una sola interrogazione le richieste dell'utente in attesa e quelle rimaste "in lavorazione" dopo un crash; quelle in lavorazione da piu' di 10 minuti vengono chiuse con errore, cosi' la partita torna ad accettare cash out.
- **Quando scatta**: ogni giro, prima di tutto il resto.
- **Cosa succede dopo**: se la lettura unica fallisce, si torna alle due letture separate (dentro `process_requests` e `fail_stale_processing`). Una richiesta appesa diventa `error` con messaggio "richiesta interrotta (servizio riavviato): riprova". Un errore qui non ferma il giro.
- **Numeri**: `_STALE_REQUEST_MIN` = 10 minuti (costante in codice); finestra di lettura = 50 + 200 righe (db.py, scheda 96).
- **Esempio**: l'utente preme Cash out, Mike crasha mentre lo lavora; al riavvio, dopo 10 minuti, la richiesta passa a `error` e il pulsante torna utilizzabile.
- **Cosa vede l'utente**: la richiesta chiusa con "richiesta interrotta (servizio riavviato): riprova".
- **Dove**: `service.py:3462-3484`; `db.py:422-451`, `474-502`.
- **Paper o live**: identico.

### 8. Da dove arrivano i prezzi del giro (righe del feed) e quanto e' vivo lo scanner
- **Cosa fa**: prende le righe di tutte le partite di calcio pubblicate dallo scanner (il "feed unico"), rileggendo il database al massimo ogni `feed_cache_s`, oppure unendole a quelle piu' fresche del canale locale se acceso (scheda 77). Poi misura da quanti secondi lo scanner non scrive il suo stato.
- **Quando scatta**: ogni giro (a meno che il banco di replay non passi le righe gia' pronte).
- **Cosa succede dopo**: le righe vengono indicizzate per evento. L'eta' dello scanner = adesso meno `updated_at` dello stato `safe_strategy_status` id `scanner`; se lo stato non si legge, eta' = sconosciuta. Lo stato dello scanner porta anche il blocco "flusso" (prezzi fermi): viene tenuto per il giro. Se lo scanner e' di una versione che non dichiara il flusso, una sola attivita' critica `flusso_non_dichiarato`.
- **Numeri**: `feed_cache_s` = 4,0 s (config, 0-30, UI); con canale sano 10 s (`_RISINC_FEED_S`).
- **Esempio**: lo scanner riscrive le righe ogni ~22 s; Mike le rilegge ogni 4 s: la freschezza si giudica comunque sull'ora della riga (schede 86-87), non sull'ora della lettura.
- **Cosa vede l'utente**: nelle statistiche `scanner_age_s` e, con canale acceso, `fonte_scan`, `righe_dal_canale`.
- **Dove**: `service.py:3493-3496`; `_scanner_age` `service.py:1216-1232` (fuori area).
- **Paper o live**: identico.

### 9. Quali partite Mike tiene in memoria (lettura delle partite seguite)
- **Cosa fa**: rilegge l'elenco completo delle partite seguite al massimo ogni `events_reload_s`; fra una rilettura e l'altra usa la copia in memoria (Mike e' l'unico che scrive quella tabella). Tornano sempre le partite NON terminali di qualunque eta', e le terminali (regolate, errore, saltate) aggiornate nelle ultime 48 ore.
- **Quando scatta**: ogni giro, con la cadenza detta.
- **Cosa succede dopo**: se la lettura fallisce: attivita' `error` con motivo `events_failed`; se c'e' gia' una copia in memoria si continua con quella (una posizione aperta non resta senza guardia); se non c'e', giro saltato (`events_unreadable`). Ogni partita senza modalita' riceve quella corrente del bot.
- **Numeri**: `events_reload_s` = 60 s (config, 0-600, UI); finestra terminali 48 ore (costante `48 * 3600` nel codice).
- **Esempio**: una partita con un Under aperto finita a servizio spento tre giorni fa torna comunque nel giro (non e' terminale) e viene regolata.
- **Cosa vede l'utente**: niente, salvo l'attivita' `error events_failed`.
- **Dove**: `service.py:3504-3532`; filtro in `db.py:91-113`.
- **Paper o live**: identico.

### 10. Lo stop giornaliero (perdita massima del giorno)
- **Cosa fa**: somma il realizzato di oggi e il profitto gia' bloccato (cicli chiusi non ancora pagati) delle partite piazzate oggi; se la somma e' uguale o peggiore di meno `daily_loss_stop`, il bot non apre piu' niente fino a domani: niente partite nuove, niente ingressi, niente ultimo ingresso, niente re-ingressi. Le chiusure continuano.
- **Quando scatta**: ogni giro; conta SOLO la modalita' corrente del bot (paper o live, mai sommate). "Oggi" = da mezzanotte di Roma, per giorno di PIAZZAMENTO della posizione.
- **Cosa succede dopo**: se scatta, i parametri effettivi hanno `pre_enabled`, `reentry_enabled`, `last_entry_persist` spenti; nessuna candidata viene armata (scheda 13). La prima volta nella giornata: riga di registro e attivita' `daily_stop` con `day_pnl`, `realized_today`, `locked_open`, `stop`, `day`. Con `daily_loss_stop` = 0 lo stop e' spento.
- **Numeri**: `daily_loss_stop` = 50,0 EUR (config, 0-100.000, UI); aggregati rinfrescati al massimo ogni `aggregates_cache_s` = 20 s (config, UI), subito dopo ogni azione.
- **Esempio**: realizzato oggi -38,40 EUR, bloccato su partite ancora da pagare -12,10 EUR -> P&L del giorno -50,50 <= -50 -> STOP.
- **Cosa vede l'utente**: nelle statistiche `daily_stop: true`, `day_pnl`; attivita' `daily_stop` una volta al giorno.
- **Dove**: `service.py:3538-3565`; `_aggregates_cached` `service.py:1099-1146` (fuori area); schede 21, 23.
- **Paper o live**: ogni modalita' ha il suo stop; il P&L del paper non ferma il live e viceversa.

### 11. Allarme: partite ancora vive nell'altra modalita'
- **Cosa fa**: trova le partite non terminali armate in una modalita' diversa da quella attuale del bot (per esempio partite live ancora aperte mentre il bot e' tornato su paper) e lo grida.
- **Quando scatta**: ogni giro.
- **Cosa succede dopo**: riga critica nel registro del processo (fino a 6 partite elencate) e numero pubblicato nelle statistiche (`eventi_altra_modalita`). Quelle partite continuano con le regole della LORO modalita'.
- **Numeri**: nessuno.
- **Esempio**: una partita armata in live alle 15:00; alle 15:30 l'utente rimette paper; la partita continua a coprirsi con soldi veri e la pagina mostra l'avviso.
- **Cosa vede l'utente**: avviso rosso in pagina (dal numero `eventi_altra_modalita`).
- **Dove**: `service.py:3547-3551` e `3898-3908` (`partite_di_modalita_diversa`; una partita senza modalita' vale `paper`).
- **Paper o live**: e' proprio la guardia della convivenza paper/live.

### 12. Le richieste dell'utente e l'indice delle righe aperte
- **Cosa fa**: esegue le richieste della pagina (cash out, flatten, annulla, salta, riprendi, approva uscita...) e poi legge in UNA interrogazione tutte le righe di ordine non chiuse, divise per partita, per il controllo rapido dello specchio (scheda 56).
- **Quando scatta**: ogni giro, prima del giro delle partite.
- **Cosa succede dopo**: il dettaglio delle richieste e' nell'area B (`process_requests`, `service.py:3077`); qui della mia area stanno `_request_cancel` (scheda 62) e `_request_flatten` (scheda 63).
- **Numeri**: nessuno.
- **Esempio**: -
- **Cosa vede l'utente**: l'esito della richiesta.
- **Dove**: `service.py:3567-3570`.
- **Paper o live**: vedi schede 62-63.

### 13. Quali partite nuove entrano nel giro (armare le candidate)
- **Cosa fa**: fra le partite del feed non ancora seguite, arma quelle che hanno entrambe le linee (Under 3.5 e Over 4.5), non sono ancora in gioco, hanno il fischio d'inizio entro la finestra, e passano il filtro competizioni; si ferma quando le partite "operative" della modalita' corrente arrivano al tetto.
- **Quando scatta**: solo a bot in esecuzione E senza stop giornaliero.
- **Cosa succede dopo**: per ogni candidata costruisce il dossier pre-partita (scheda 102) e crea la scheda in stato `WATCH` (ciclo 0, modalita' corrente congelata sulla partita); attivita' `armed` con nome, calcio d'inizio e dossier. Il conto delle "operative" per il tetto qui esclude le terminali e quelle in `WATCH` o `IDLE_LIVE`.
- **Numeri**: `max_open_matches` = 10 (config, 1-90, UI); `entry_hours_before_ko` = 1,0 h (config, 0,25-12, UI); `competition_filter` = "" (tutte).
- **Esempio**: calcio d'inizio fra 50 minuti, entrambe le linee nel feed, non in gioco -> armata in WATCH. Fischio fra 70 minuti con finestra 1 h -> non ancora.
- **Cosa vede l'utente**: la nuova scheda partita in WATCH; attivita' `armed`.
- **Dove**: `service.py:3572-3601`; regole della candidata `feed.py:443-460` (scheda 89).
- **Paper o live**: la partita prende la modalita' del bot in quel momento e la tiene per sempre.

### 14. Il dossier "cieco" viene ritentato ogni 5 minuti
- **Cosa fa**: per ogni partita ancora viva il cui dossier non ha i gol attesi (lambda casa e trasferta), riprova a costruirlo al massimo ogni 300 secondi; se ora li trova, aggiorna fixture e lega.
- **Quando scatta**: ogni giro, per le partite non terminali con dossier senza entrambi i lambda, se l'ultimo tentativo ha almeno 300 s (o il dossier non esiste).
- **Cosa succede dopo**: nuovo dossier con l'ora del tentativo; se risolto: `fixture_id`, `league_id` aggiornati e attivita' `dossier_risolto` (fixture, fonte, lambda). Un errore non ferma niente.
- **Numeri**: `_DOSSIER_RETRY_SEC` = 300 s (costante in codice).
- **Esempio**: partita di lega minore armata alle 19:00 senza fixture abbinata; alle 19:15 Omega ha popolato il catalogo: il ritentativo trova lambda 1,4 e 1,1 e il modello si accende.
- **Cosa vede l'utente**: attivita' `dossier_risolto`; la scheda passa da "nessun modello" a modello attivo.
- **Dove**: `service.py:3612`, `5366-5408` (`dossier_da_ritentare` 5369, `_retry_dossier` 5387).
- **Paper o live**: identico.

### 15. Il tetto delle partite, separato per paper e live, applicato dentro il giro
- **Cosa fa**: conta le partite che hanno davvero soldi sopra (stato operativo, oppure una gamba viva o abbinata non archiviata), separate per modalita'. Nel giro, una partita nuova puo' aprire solo se nella SUA modalita' ci sono meno partite esposte del tetto; appena una partita si espone, il posto e' occupato subito per le successive dello stesso giro. Una partita gia' esposta non viene mai bloccata.
- **Quando scatta**: ogni giro, per ogni partita, prima del suo giro.
- **Cosa succede dopo**: se la partita non puo' aprire, il suo giro avviene lo stesso ma senza aperture (scheda 45) e si conta fra le "bloccate dal tetto".
- **Numeri**: `max_open_matches` = 10 (config, UI); tetto 0 o negativo = nessun tetto nel giro (`cap_partite <= 0`).
- **Esempio**: tetto 1, una vecchia partita paper ancora viva: in live il posto e' libero (i soldi finti non occupano il posto di quelli veri).
- **Cosa vede l'utente**: statistiche `tetto_partite`, `partite_esposte`, `partite_esposte_live`, `partite_esposte_paper`, `aperture_bloccate`, `motivo_blocco` ("tetto partite raggiunto: N su M in live").
- **Dove**: `service.py:3625-3656`; `posti_occupati_per_modo` 3841-3861; `engine.ha_esposizione` `engine.py:1827` (fuori area).
- **Paper o live**: conti separati per modalita'.

### 16. Una partita rotta non ferma le altre; le scritture di cortesia partono sempre
- **Cosa fa**: se il giro di una partita solleva un errore, lo registra e passa alla successiva. Alla fine del giro (anche se esplode a meta') invia in un solo colpo le riscritture "di cortesia" accumulate.
- **Quando scatta**: ogni giro.
- **Cosa succede dopo**: attivita' `error` con motivo `event_cycle` sulla partita rotta; lotto svuotato (scheda 71).
- **Numeri**: nessuno.
- **Esempio**: una scheda con una gamba illeggibile solleva un errore: le altre 9 partite continuano normalmente.
- **Cosa vede l'utente**: attivita' `error event_cycle` su quella partita.
- **Dove**: `service.py:3635-3665`.
- **Paper o live**: identico.

### 17. "In arresto" diventa "fermo"
- **Cosa fa**: se il bot e' nello stato `stopping`, alla fine del giro lo scrive come `stopped` con l'ora.
- **Quando scatta**: fine del giro con stato `stopping`.
- **Cosa succede dopo**: `status=stopped`, `stopped_at`, attivita' `stop`. Errori ignorati.
- **Numeri**: nessuno.
- **Esempio**: -
- **Cosa vede l'utente**: bot fermo, attivita' `stop`.
- **Dove**: `service.py:3667-3673`.
- **Paper o live**: identico.

### 18. I numeri di testata (statistiche) e la "fretta" del prossimo giro
- **Cosa fa**: calcola i numeri della testata della pagina e decide se c'e' fretta (giro a 1 s) o no (giro a 5 s).
- **Quando scatta**: fine di ogni giro. Se nel giro ci sono state azioni, regolamenti o richieste, gli aggregati e il bloccato vengono ricalcolati subito.
- **Cosa succede dopo**: fretta = c'e' almeno una richiesta, oppure una partita non terminale in gioco, oppure una gamba `pending` o `pending_reconcile`. Statistiche pubblicate: partite nel feed, seguite, per stato, righe aperte, capitale a rischio netto (scheda 22), capitale a rischio sommato dalle righe, realizzato oggi e totale, bloccato, P&L del giorno, vinte/perse oggi, cicli e partite di oggi, partite in gioco, eta' scanner, tetto e posti (scheda 15), cadenza del battito (scheda 20), `stop_ferma_solo_aperture`, statistiche sveglia e canale, ora del giro, `dry`, modalita', stop giornaliero, partite in riconciliazione, `live_abilitato` (interruttore `MIKE_LIVE_ENABLED`).
- **Numeri**: nessuno di nuovo.
- **Esempio**: 3 partite in gioco, 2 regolate oggi (+4,20 e -1,10): `realized_today` +3,10.
- **Cosa vede l'utente**: tutta la testata della pagina (arriva subito via canale locale, scheda 73).
- **Dove**: `service.py:3675-3753`.
- **Paper o live**: aggregati, bloccato e rischio filtrati sulla modalita' corrente.

### 19. Il battito sulla riga di controllo (quanto spesso si scrive)
- **Cosa fa**: scrive le statistiche e l'ora del battito sulla riga di controllo, ma non a ogni giro: al massimo ogni `stats_min_s` se qualcosa e' cambiato, e comunque almeno ogni `heartbeat_min_s`. I contatori che crescono da soli (ora, eta' scanner, sveglia, canale) non contano come "cambiamento".
- **Quando scatta**: fine di ogni giro.
- **Cosa succede dopo**: scrittura di `stats` (timbrate con l'identificativo dell'apertura dell'app, altrimenti il crash successivo sembrerebbe un avvio nuovo) e `heartbeat_at`. Errore -> solo avviso. Zero = "a ogni giro" (valvola voluta).
- **Numeri**: `stats_min_s` = 10 s, `heartbeat_min_s` = 20 s (config, 0-300, UI).
- **Esempio**: il P&L cambia ogni secondo: si scrive al piu' ogni 10 s; niente cambia: una scrittura ogni 20 s.
- **Cosa vede l'utente**: il segnale di vita del servizio in pagina.
- **Dove**: `service.py:3772-3795`.
- **Paper o live**: identico.

### 20. La cadenza del battito dichiarata alla pagina
- **Cosa fa**: calcola ogni quanti secondi, nel caso peggiore, il servizio batte, cosi' la pagina giudica "vivo/morto" con il metro vero.
- **Quando scatta**: ogni giro (dentro le statistiche).
- **Cosa succede dopo**: passo = max(1, `decide_min_interval_ms`/1000 x 2); poi max con `idle_cycle_s`; poi max con `heartbeat_min_s`; arrotondato a 0,1. Un valore mancante o <= 0 prende il default indicato nel codice (500 ms, 5 s, 20 s).
- **Numeri**: con i default: max(1,0; 5,0; 20,0) = 20,0 s.
- **Esempio**: l'utente porta `heartbeat_min_s` a 30: la pagina aspetta 30 s prima di dichiarare il servizio lento.
- **Cosa vede l'utente**: il chip di salute del servizio.
- **Dove**: `service.py:3864-3895` (con il passaggio interno `_num` 3881-3891).
- **Paper o live**: identico.

### 21. La giornata operativa (mezzanotte di Roma)
- **Cosa fa**: dice da quale istante comincia "oggi" per lo stop e il bloccato (mezzanotte Europe/Rome) e con quale data si firma lo stop del giorno.
- **Quando scatta**: ogni giro.
- **Cosa succede dopo**: inizio = mezzanotte di Roma in UTC; chiave del giorno = data di (inizio + 12 ore), cosi' vicino alla mezzanotte UTC non si sbaglia giorno.
- **Numeri**: +12 ore (costante nel codice).
- **Esempio**: 28/09 23:30 UTC = 29/09 01:30 a Roma -> inizio 28/09 22:00 UTC -> chiave "2026-09-29".
- **Cosa vede l'utente**: lo stop si scrive una volta per giornata di Roma.
- **Dove**: `service.py:3801-3815`; `safe_strategy/risk.py:123-136`.
- **Paper o live**: identico.

### 22. Il capitale a rischio netto (liability) delle partite aperte
- **Cosa fa**: per ogni partita non terminale della modalita' corrente somma la perdita peggiore possibile della posizione NETTA (un back coperto da una lay conta il residuo, non back + lay; ordini a esito ignoto contati come abbinati).
- **Quando scatta**: fine di ogni giro (statistiche).
- **Cosa succede dopo**: numero `open_liability` nelle statistiche (arrotondato al centesimo). Le gambe vengono lette dalla scheda salvata della partita.
- **Numeri**: commissione `commission_pct` = 5% (config, UI).
- **Esempio**: back Under 3.5 10 EUR a 2,00 senza copertura -> rischio 10,00 EUR.
- **Cosa vede l'utente**: tile "capitale a rischio".
- **Dove**: `service.py:3818-3838`; `engine.event_liability` `engine.py:938` (fuori area).
- **Paper o live**: solo la modalita' corrente.

### 23. Il profitto gia' bloccato (cicli chiusi non ancora pagati)
- **Cosa fa**: somma il risultato gia' certo delle partite non terminali che non hanno piu' esposizione (ciclo chiuso in verde o in perdita, mercato non ancora regolato), solo se il primo piazzamento della partita e' di oggi (mezzanotte di Roma) e solo della modalita' corrente.
- **Quando scatta**: ogni giro, per lo stop (scheda 10) e per le statistiche.
- **Cosa succede dopo**: una partita con una selezione ancora aperta, o una gamba in riconciliazione, o mai giocata, non conta (il suo bloccato e' "niente", non zero).
- **Numeri**: commissione 5%.
- **Esempio**: back 10 EUR a 2,00 e lay 10,10 EUR a 1,98: circa +0,10 su ogni risultato (prima della commissione) -> bloccato +0,10.
- **Cosa vede l'utente**: `locked_open` e `day_pnl` in testata.
- **Dove**: `service.py:3911-3946`; `engine.locked_pnl` `engine.py:950` (fuori area).
- **Paper o live**: solo la modalita' corrente.

### 24. Avviso di configurazione: finestra di Mike piu' larga di quella dello scanner
- **Cosa fa**: se lo scanner non pubblica le linee pre-partita (variabile spenta) o le pubblica da meno ore di quelle in cui Mike vorrebbe entrare, lo scrive: Mike vedrebbe zero candidate senza dirlo.
- **Quando scatta**: ogni giro, ma scrive una sola volta per ogni situazione nuova.
- **Cosa succede dopo**: riga di registro e attivita' `config_warn` critica con il messaggio, le ore di Mike e quelle dello scanner. Nessun blocco.
- **Numeri**: env `SAFE_PRE_KO_OU_HOURS` letta da Mike con default 0 (= spento); `entry_hours_before_ko` = 1,0 h.
- **Esempio**: scanner a 1 h, Mike a 2 h -> "Finestra di ingresso 2 h piu' ampia del ramo pre-KO dello scanner (1 h)...".
- **Cosa vede l'utente**: attivita' `config_warn`.
- **Dove**: `service.py:3949-3974`.
- **Paper o live**: identico.

### 25. La decisione di uscita in perdita si scrive una volta, non a ogni giro
- **Cosa fa**: quando il motore ripete a ogni giro la stessa decisione di chiusura in perdita (con uscite manuali in attesa), l'attivita' si scrive solo se la decisione cambia (finestra, modalita', motivo senza i numeri, percentuale) o ogni 5 minuti.
- **Quando scatta**: nel giro della partita, quando il motore emette `loss_exit_deciso` (scheda 48).
- **Cosa succede dopo**: firma = finestra | modo | motivo con ogni numero sostituito da "#" | percentuale.
- **Numeri**: `_LOSS_EXIT_DECISO_MIN_S` = 300 s (costante in codice).
- **Esempio**: "regola fissa: -9.05 entro 30% di 8.90" e "regola fissa: -9.10 entro 30% di 8.90" hanno la stessa firma: una sola riga ogni 5 minuti.
- **Cosa vede l'utente**: meno righe ripetute in Attivita'.
- **Dove**: `service.py:3979-3991`, uso a `4563-4576`.
- **Paper o live**: identico.

---

# PARTE B - IL GIRO DI UNA PARTITA (`_run_event`)

### 26. Partite finite saltate; regole della modalita' della PARTITA
- **Cosa fa**: una partita regolata, in errore o saltata non viene piu' guardata. Per le altre, i parametri si adattano alla modalita' della partita (non a quella del bot).
- **Quando scatta**: inizio del giro di ogni partita.
- **Cosa succede dopo**: se la partita e' live e l'utente ha spento `live_resting_enabled` con `pre_exit_mode=resting`, l'uscita del ciclo pre-partita e del re-ingresso diventa a mercato (`taker`). Poi si legge il contesto salvato, la firma prima del giro, la riga del feed, i dati della partita e il dossier.
- **Numeri**: `live_resting_enabled` = acceso (config, UI); `pre_exit_mode` = resting (config, UI).
- **Esempio**: -
- **Cosa vede l'utente**: niente.
- **Dove**: `service.py:4008-4021`; `_live_exit_override` `service.py:1235-1265` (fuori area).
- **Paper o live**: live con valvola spenta = uscite taker.

### 27. La riparazione dello specchio gambe/righe ogni 30 secondi
- **Cosa fa**: ogni 30 s per partita confronta cio' che il bot crede delle sue gambe con le righe di ordine nel database e ripara i buchi (scheda 59).
- **Quando scatta**: se sono passati almeno `reconcile_every_s` secondi dall'ultima riparazione di quella partita (memoria di processo: dopo un riavvio si ripara subito).
- **Cosa succede dopo**: vedi scheda 59.
- **Numeri**: `reconcile_every_s` = 30 s (config, 0-600, UI).
- **Esempio**: -
- **Cosa vede l'utente**: attivita' `reconcile_fix` / `reconcile_pending`.
- **Dove**: `service.py:4028-4032`.
- **Paper o live**: vedi scheda 59.

### 28. Quando una partita sparita dal feed vale "mercato chiuso"
- **Cosa fa**: decide se la partita e' finita. E' chiusa se lo stato della linea 3.5 (o, in mancanza, del mercato principale) nel feed e' CLOSED, oppure se la riga manca dal feed da almeno 10 minuti, oppure se il calcio d'inizio e' noto e sono passate piu' di 3 ore, oppure se la partita e' stata vista in gioco e sono passati almeno 100 minuti dal fischio.
- **Quando scatta**: ogni giro della partita.
- **Cosa succede dopo**: riga assente ma non ancora "chiusa" e partita non terminale -> si salva da quando manca e il giro della partita FINISCE qui (nessun'altra sorveglianza, vedi Cose strane). Riga presente -> si dimentica l'assenza.
- **Numeri**: `_ROW_MISSING_GRACE_S` = 600 s; `_MATCH_OVER_S` = 10.800 s (3 h); `_MATCH_LIKELY_OVER_S` = 6.000 s (100 min). Tutte costanti nel codice.
- **Esempio**: al fischio il feed passa dal blocco pre-partita a quello in gioco e la riga sparisce per 4 minuti: NON e' un regolamento.
- **Cosa vede l'utente**: niente finche' non scatta il regolamento.
- **Dove**: `service.py:4039-4055`.
- **Paper o live**: identico.

### 29. Falso regolamento annullato
- **Cosa fa**: se la partita era passata a "in regolamento" ma la riga e' tornata nel feed, il mercato e' aperto e non sono passate 3 ore dal fischio, torna nello stato coerente con le posizioni aperte.
- **Quando scatta**: stato `SETTLING`, non chiusa, riga presente, fischio ignoto o meno di 3 ore fa.
- **Cosa succede dopo**: Over 4.5 aperto -> `LIVE_COVERED`; Under 4.5 aperto -> `REENTRY_OPEN`; Under 3.5 aperto -> `LIVE_UNCOVERED` se in gioco, altrimenti `PRE_OPEN`; niente aperto -> `IDLE_LIVE` se in gioco, altrimenti `WATCH`. Si cancellano gli orologi del regolamento; attivita' `settling_reverted`.
- **Numeri**: 3 ore (`_MATCH_OVER_S`).
- **Esempio**: riga sparita 12 minuti pre-partita, Mike era andato in regolamento; la riga torna con Under 3.5 aperto: stato `PRE_OPEN`.
- **Cosa vede l'utente**: attivita' `settling_reverted` ("riga tornata nel feed, mercato aperto").
- **Dove**: `service.py:4058-4072`.
- **Paper o live**: identico.

### 30. Regolamento: le letture di Betfair a mercato chiuso sono frenate
- **Cosa fa**: a partita chiusa legge da Betfair (lettura REST del book) i risultati delle due linee, ma non piu' spesso di `settle_confirm_s`.
- **Quando scatta**: partita chiusa (scheda 28) e non terminale.
- **Cosa succede dopo**: se non e' ancora ora: si salva la scheda e si esce. Altrimenti si fissa la prossima lettura (almeno 5 s dopo), si ricorda la prima lettura, si leggono i book di 3.5 e 4.5 (una chiamata per mercato), si ricostruiscono i dati della partita dalle selezioni salvate e si deduce il totale gol rappresentativo (3 = Under 3.5 vince; 5 = Over 4.5 vince; 4 = Over 3.5 e Under 4.5 vincono).
- **Numeri**: `settle_confirm_s` = 60 s (config, 0-600, UI); minimo effettivo 5 s; se 0 -> `_SETTLE_RETRY_S` = 30 s.
- **Esempio**: fischio finale alle 22:47, mercato CLOSED: lettura alle 22:47, poi alle 22:48, 22:49... finche' Betfair dichiara i vincitori.
- **Cosa vede l'utente**: stato "in regolamento".
- **Dove**: `service.py:4073-4097`; `final_total_from_books` `service.py:1027-1037` (fuori area).
- **Paper o live**: identico (la lettura dei risultati e' sempre su Betfair).

### 31. Regolamento: mercato annullato da Betfair (void per singolo mercato)
- **Cosa fa**: se una delle due linee e' annullata (stato VOID/VOIDED, oppure CLOSED senza vincitore e con tutti i corridori rimossi/annullati), le gambe di QUELLA linea valgono zero e l'altra si regola coi suoi risultati.
- **Quando scatta**: a mercato chiuso, se entrambe le linee sono regolate o annullate e almeno una e' annullata.
- **Cosa succede dopo**: regolamento per mercato con la commissione fissata sulle righe (scheda 65); partita `SETTLED` con il P&L; aggiornamento delle righe (scheda 66); se le righe non si aggiornano si riprova (scheda 64); attivita' `settled` con `void: true`, mercati annullati, vincitori, P&L, numero gambe.
- **Numeri**: commissione dalle righe (default 5%).
- **Esempio**: Under 3.5 vince (3 gol), la 4.5 viene annullata: le gambe della 3.5 si pagano, quelle della 4.5 valgono 0.
- **Cosa vede l'utente**: partita regolata; attivita' `settled` con motivo `mercato_annullato`.
- **Dove**: `service.py:4109-4130`; `settle_plan` `service.py:1069-1090`, `market_voided` 1047-1066 (fuori area).
- **Paper o live**: identico.

### 32. Regolamento: dopo 2 ore senza esito leggibile
- **Cosa fa**: se Betfair non dice il risultato per 2 ore dalla prima lettura: (a) se la partita e' stata vista in gioco e si conosce l'ultimo punteggio del feed, usa quello; (b) altrimenti, se il risultato non dipende dal punteggio (nessuna posizione, o solo cicli gia' chiusi), chiude la partita con quel risultato; (c) altrimenti ERRORE.
- **Quando scatta**: totale non deducibile e oltre `_SETTLE_MAX_WAIT_S` dalla prima lettura.
- **Cosa succede dopo**: (a) attivita' `settle_fallback` e si prosegue con il regolamento normale; (b) attivita' `settled` "punteggio non recuperabile, ma il risultato non dipende dal punteggio", stato `SETTLED` con quel P&L, **senza aggiornare le righe di ordine** (vedi Cose strane); (c) attivita' `error settle_timeout` critica, stato `ERROR` "regolamento non determinabile" (righe non aggiornate).
- **Numeri**: `_SETTLE_MAX_WAIT_S` = 7200 s (costante).
- **Esempio**: partita di lega minore, book illeggibile per 2 ore, feed ha visto 2-1 all'ultimo aggiornamento: totale 3, Under 3.5 vincente.
- **Cosa vede l'utente**: attivita' `settle_fallback`, oppure partita in "DA SISTEMARE" (ERROR).
- **Dove**: `service.py:4131-4161`.
- **Paper o live**: identico.

### 33. Regolamento normale (in regolamento -> regolata)
- **Cosa fa**: passa al motore una fotografia "mercato chiuso" con il totale dei gol; il motore porta la partita in `SETTLING` e, se il totale c'e', subito in `SETTLED` nello stesso giro; poi scrive l'esito su ogni riga.
- **Quando scatta**: partita chiusa, dopo le schede 30-32.
- **Cosa succede dopo**: commissione fissata dalle righe (scheda 65); se `SETTLED`: righe aggiornate (scheda 66), riprova se falliscono (scheda 64), attivita' `settled` con totale e P&L; se il totale manca resta `SETTLING` e si riprova alla lettura successiva.
- **Numeri**: -
- **Esempio**: totale 5 gol: Over 4.5 coperto vince, Under 3.5 perde; P&L netto scritto per gamba.
- **Cosa vede l'utente**: partita regolata, attivita' `settled`.
- **Dove**: `service.py:4162-4185`; `engine.decide` e `apply_decision` (area engine).
- **Paper o live**: identico.

### 34. Linee assenti dal feed con una posizione aperta (prima della fotografia)
- **Cosa fa**: se la riga c'e' ma una delle due linee non e' nel feed (partita non completa), e la partita ha selezioni aperte, lo grida: niente copertura, niente cash out, niente uscita possibili.
- **Quando scatta**: riga assente o dati partita incompleti (manca 3.5 o 4.5, o Under 3.5, o Over 4.5), e posizione aperta.
- **Cosa succede dopo**: attivita' critica `feed_line_missing` ("linee assenti dal feed", mercati mancanti "MERCATO|SELEZIONE") frenata; la scheda live segna `lines_missing` e `feed_incomplete`; salvataggio; il giro della partita finisce (nessun'altra sorveglianza).
- **Numeri**: freno delle attivita': `skip_log_interval_s` = 300 s (config, UI), 45 s per le critiche (`_CRITICAL_LOG_EVERY_S`).
- **Esempio**: lo scanner ha tolto la 4.5 dal suo tetto di mercati: la scheda mostra "OU45|OVER mancante" in rosso.
- **Cosa vede l'utente**: allarme sulla scheda e attivita' `feed_line_missing`.
- **Dove**: `service.py:4186-4207`; freno `_log_throttled` `service.py:1279-1301`.
- **Paper o live**: identico.

### 35. Gol, intervallo e modello dal vivo
- **Cosa fa**: aggiorna dal feed il totale dei gol (e l'ora dell'ultimo gol se e' salito), ricorda di aver visto la partita in gioco, salva i numeri delle selezioni, fissa il punteggio dell'intervallo la prima volta che il feed dice "half time", e (se in gioco) calcola il quadro del modello: pericolo di gol nei prossimi 3', probabilita' di 4 gol, distribuzione dei gol, risparmio atteso sulla copertura (scheda 104).
- **Quando scatta**: ogni giro, con la riga presente e completa.
- **Cosa succede dopo**: la tabella empirica intervallo->fine gara si chiede solo se c'e' il punteggio dell'intervallo (scheda 107).
- **Numeri**: `cover_wait_step_min` = 5 minuti (config, UI); `loss_exit_emp_min_n` = 200 (config, 20-5000, UI).
- **Esempio**: feed 1-0 al 45', stato "half time": `ht_score` = [1, 0], fissato per sempre.
- **Cosa vede l'utente**: minuto, gol, hazard, probabilita' sulla scheda.
- **Dove**: `service.py:4210-4231`.
- **Paper o live**: identico.

### 36. Flusso dei prezzi interrotto e ripiego sulla lettura diretta di Betfair
- **Cosa fa**: controlla se i prezzi delle due linee di Mike sono vivi (scanner non bloccato e nessuna delle due linee col flusso fermo). Se sono fermi e c'e' una posizione aperta, legge i book direttamente da Betfair (al massimo una volta ogni 10 s per mercato) e li usa SOLO per chiudere, coprire o proteggere; le aperture restano bloccate.
- **Quando scatta**: ogni giro; la lettura diretta solo con posizione aperta e fuori da `--dry`.
- **Cosa succede dopo**: attivita' `flusso_interrotto` (motivo, testo, mercati; critica se c'e' posizione) frenata; se il ripiego ha dato book: attivita' `ripiego_rest` al massimo una ogni 60 s; se il ripiego non ha dato nulla: attivita' critica `flusso_interrotto_senza_rest` con esposizione in euro, da quanti secondi e selezioni ("la posizione resta senza chiusura ne' copertura finche' un prezzo vivo non torna").
- **Numeri**: `_RIPIEGO_REST_MIN_S` = 10 s (costante); promemoria critico ogni 60 s (`flusso_prezzi.AVVISO_CRITICO_OGNI_S`); soglie dello scanner (fuori area): giro fermo oltre 45 s, conferma in gioco 45 s, pre-partita 125 s.
- **Esempio**: Under 3.5 aperto, flusso fermo da 70 s: Mike legge il book Betfair, trova 1,55/1,57 e puo' chiudere; non potrebbe aprire un nuovo ciclo.
- **Cosa vede l'utente**: attivita' `flusso_interrotto`, `ripiego_rest` o `flusso_interrotto_senza_rest`.
- **Dove**: `service.py:4235-4274`; `_books_ripiego_rest` `service.py:1163-1190`; `feed.flusso_esito` (scheda 81).
- **Paper o live**: identico (anche il paper legge Betfair per il ripiego).

### 37. Fotografia del mercato non costruibile
- **Cosa fa**: se il feed non permette di costruire la fotografia (per esempio manca l'ora di inizio), la partita smetterebbe di essere decisa in silenzio: lo scrive.
- **Quando scatta**: fotografia assente.
- **Cosa succede dopo**: attivita' `feed_line_missing` con motivo `snapshot_non_costruibile` (critica se c'e' posizione), salvataggio, fine giro partita.
- **Numeri**: freno come scheda 34.
- **Esempio**: -
- **Cosa vede l'utente**: attivita' `feed_line_missing`.
- **Dove**: `service.py:4275-4283`.
- **Paper o live**: identico.

### 38. Linee mancanti per le selezioni ancora in gioco (dopo la fotografia)
- **Cosa fa**: con una posizione aperta, per ogni selezione ancora "viva" (non gia' decisa dal punteggio) senza prezzo nella fotografia, grida.
- **Quando scatta**: ogni giro con posizione.
- **Cosa succede dopo**: attivita' critica `feed_line_missing` con motivo "flusso prezzi interrotto" o "linee assenti dal feed" e le selezioni; il giro continua.
- **Numeri**: freno come scheda 34.
- **Esempio**: -
- **Cosa vede l'utente**: attivita' `feed_line_missing`.
- **Dove**: `service.py:4289-4296`.
- **Paper o live**: identico.

### 39. Le sorveglianze che girano prima della decisione (rimandi)
- **Cosa fa**: prima di chiedere al motore cosa fare: (paper) legge dal runner l'esito degli ordini paper; controlla sospensione e riapertura del mercato (le lay appoggiate possono essere state fatte scadere); controlla lo stato del mercato della copertura Over 4.5; controlla la posizione di conto su Betfair (se l'utente ha chiuso a mano fuori dall'app), ogni `reconcile_every_s`.
- **Quando scatta**: ogni giro, nell'ordine detto.
- **Cosa succede dopo**: dettagli nell'area B (`_segui_ordini_paper_su_runner` `service.py:1456`, `_sorveglia_sospensione` 2872, `_sorveglia_mercato_copertura` 2965, `_sorveglia_posizione_di_conto` 2760).
- **Numeri**: `reconcile_every_s` = 30 s.
- **Esempio**: -
- **Cosa vede l'utente**: vedi area B.
- **Dove**: `service.py:4304-4322`.
- **Paper o live**: la lettura dal runner e' solo paper.

### 40. Ordini in attesa da troppo tempo (oltre 120 secondi)
- **Cosa fa**: una gamba viva da piu' di 120 s (non una lay appoggiata, che resta legittimamente sul book per ore) viene: messa in riconciliazione se l'esito dell'ordine e' ignoto (o la riga non si legge, o non esiste); altrimenti ritirata DAVVERO (annullo mandato prima al mercato, scheda 61).
- **Quando scatta**: ogni giro, per ogni gamba viva non appoggiata.
- **Cosa succede dopo**: riconciliazione: riga critica nel registro e attivita' `reconcile_pending` ("pending_unknown_outcome") frenata; ritiro: motivo `pending_stale`.
- **Numeri**: `_PENDING_STALE_S` = 120 s (costante).
- **Esempio**: ordine d'ingresso inviato alle 19:00:00 senza risposta; alle 19:02:01 la riga dice "eccezione in piazzamento": la gamba va in riconciliazione, conta nel rischio al peggior caso e blocca nuove aperture.
- **Cosa vede l'utente**: attivita' `reconcile_pending`, oppure `cancel_richiesto`/`cancel_esito`.
- **Dove**: `service.py:4330-4344`.
- **Paper o live**: stessa regola; il ritiro va a Betfair (live) o al runner (paper), scheda 61.

### 41. Ordini a esito ignoto: riconciliazione a ritmo frenato
- **Cosa fa**: se la partita ha gambe a esito ignoto, prova a chiarirle (scheda 60) al massimo ogni `max(5 s, settle_confirm_s)`; nel frattempo il giro continua con tutte le azioni che riducono il rischio (le aperture le toglie il motore).
- **Quando scatta**: almeno una gamba in `pending_reconcile`.
- **Cosa succede dopo**: se dopo il tentativo resta un ignoto: attivita' critica `reconcile_pending` con le gambe, frenata.
- **Numeri**: `settle_confirm_s` = 60 s -> una prova ogni 60 s; se 0 -> 30 s; minimo 5 s.
- **Esempio**: -
- **Cosa vede l'utente**: attivita' `reconcile_pending`; statistica `reconciling`.
- **Dove**: `service.py:4351-4359`.
- **Paper o live**: vedi scheda 60.

### 42. Le lay appoggiate gia' sul book
- **Cosa fa**: in live, per ogni lay appoggiata viva, legge dal book ordini di Betfair se si e' abbinata (mai dedotto dal prezzo). In paper non fa niente qui: l'abbinamento lo dice il runner (scheda 39).
- **Quando scatta**: ogni giro, per ogni gamba viva appoggiata.
- **Cosa succede dopo**: dettaglio in area B (`_segui_resting_live` `service.py:2318`); viene passato anche se c'e' una rilettura dopo riapertura in corso.
- **Numeri**: -
- **Esempio**: -
- **Cosa vede l'utente**: vedi area B.
- **Dove**: `service.py:4366-4382`.
- **Paper o live**: live = lettura Betfair; paper = runner. Il vecchio abbinamento "simulato in casa" non esiste piu'.

### 43. Gli ordini differiti (vecchia coda) e il collegamento chiusura->apertura
- **Cosa fa**: esegue le voci "differite" rimaste in memoria da versioni precedenti (bet delay paper): quando e' scaduta l'attesa, piazza la gamba al prezzo del momento; se il prezzo manca, riprova fino a 30 s dopo la scadenza. Prepara anche il collegamento "questa chiusura chiude quella riga" (legge le righe una sola volta, alla prima chiusura).
- **Quando scatta**: ogni giro; di fatto la lista non viene piu' alimentata da nessuno (vedi Cose strane).
- **Cosa succede dopo**: voce con gamba non piu' viva -> scartata; non ancora ora -> resta; prezzo assente entro 30 s -> resta; altrimenti piazzamento (area B, `execute_place` `service.py:618`), anche con prezzo assente dopo i 30 s.
- **Numeri**: grazia 30 s (costante nel codice, riga 4410).
- **Esempio**: -
- **Cosa vede l'utente**: come un piazzamento normale.
- **Dove**: `service.py:4387-4419` (`closes_id` 4389-4394).
- **Paper o live**: nato per il paper.

### 44. La decisione del motore
- **Cosa fa**: ricorda se c'era un'uscita approvata dall'utente, rilegge le cause di "aperture ferme non di mercato" (se non ci sono piu' si riparte), chiede al motore cosa fare, e capisce se il motore ha eseguito l'uscita approvata.
- **Quando scatta**: ogni giro della partita.
- **Cosa succede dopo**: decisione = nuovo stato + azioni (piazza / annulla) + notizie. Dettaglio del motore nell'area engine; `_aggiorna_aperture_ferme` `service.py:1862`, `_approvazione_eseguita` 3192 (area B).
- **Numeri**: -
- **Esempio**: -
- **Cosa vede l'utente**: -
- **Dove**: `service.py:4425-4430`.
- **Paper o live**: identico.

### 45. Il tetto delle partite applicato dove nascono i soldi
- **Cosa fa**: se la partita non puo' aprire (scheda 15) e il motore vuole piazzare una gamba di APERTURA (ingresso Under, ultimo ingresso, seconda entrata, copertura Over, re-ingresso), toglie le sole aperture; annulli, uscite, coperture gia' in corso e cash out passano sempre.
- **Quando scatta**: partita bloccata dal tetto con almeno una apertura proposta.
- **Cosa succede dopo**: decisione ripulita con motivo "tetto partite aperte raggiunto"; attivita' `tetto_partite` frenata (motivo `max_open_matches`, tetto, stato). Al giro dopo si riprova.
- **Numeri**: `max_open_matches` = 10.
- **Esempio**: 10 partite esposte in paper; l'undicesima vorrebbe entrare a 1,85: niente ingresso finche' un posto non si libera.
- **Cosa vede l'utente**: attivita' `tetto_partite`; statistiche `aperture_bloccate`.
- **Dove**: `service.py:4441-4445`; ruoli d'apertura `engine.OPENING_ROLES` (`engine.py:50`).
- **Paper o live**: identico (conti separati per modalita').

### 46. Gli annulli decisi dal motore
- **Cosa fa**: per ogni annullo deciso dal motore su una gamba viva, toglie la gamba dalla coda differita e manda l'annullo al mercato (scheda 61).
- **Quando scatta**: azione "annulla" nella decisione.
- **Cosa succede dopo**: motivo `cancelled_by_engine`; attivita' `cancel` con gamba, ruolo ed esito (annullata / aperta perche' abbinata nel frattempo / in riconciliazione).
- **Numeri**: -
- **Esempio**: residuo PERSIST non abbinato 120 s dopo il fischio: il motore lo annulla.
- **Cosa vede l'utente**: attivita' `cancel`.
- **Dove**: `service.py:4446-4457`.
- **Paper o live**: live = Betfair; paper con runner = runner.

### 47. Il piazzamento delle gambe nuove
- **Cosa fa**: applica la decisione e piazza ogni gamba nuova. Per una lay APPOGGIATA (uscita al fischio sempre; green del ciclo pre-partita e del re-ingresso se `pre_exit_mode=resting`): 
  1. prezzi non vivi, oppure prezzi dal ripiego REST su una gamba d'APERTURA -> nessun ordine, gamba annullata, attivita' `no_fill` "feed_stantio";
  2. mercato non operabile (sospeso) -> nessun ordine, la gamba torna al motore;
  3. `--dry` -> attivita' `would_place`;
  4. live -> ordine vero appoggiato (area B `_piazza_resting_live` 1903);
  5. paper: se non e' una chiusura e il freno unico paper la ferma -> niente; se c'e' gia' una lay dello stesso ruolo e ciclo in attesa -> annullata, attivita' `place_saltato`; altrimenti ordine sul book del runner (area B `_piazza_resting_paper` 1665).
  Per le altre gambe: piazzamento a mercato (area B `execute_place` 618) con freschezza, fonte dei prezzi, motivo di chiusura e collegamento alla riga aperta. La chiave dell'approvazione dell'utente va solo sulle gambe d'uscita discrezionale.
- **Quando scatta**: gambe nuove nella decisione.
- **Cosa succede dopo**: ogni gamba conta come un'azione.
- **Numeri**: -
- **Esempio**: ingresso Under 3.5 a 1,90 da 10 EUR: gamba a mercato; subito dopo il fill, lay appoggiata a 1,88 (2 tick sotto: sotto quota 2 il passo e' 0,01) sul book.
- **Cosa vede l'utente**: righe in Trade, attivita' di piazzamento.
- **Dove**: `service.py:4458-4528`; `_is_resting_leg` `service.py:1330-1346`.
- **Paper o live**: identica decisione; paper sul runner, live su Betfair.

### 48. Le notizie del motore scritte nell'attivita'
- **Cosa fa**: copia nell'attivita' solo le notizie dichiarate alla pagina: ciclo pre-partita, copertura, attesa copertura, cash out, tentativi di chiusura esauriti, chiusura dell'utente, uscita in perdita, decisione di uscita in perdita (frenata, scheda 25), proposta d'uscita nata/decaduta/eseguita su approvazione, veto sulla probabilita' calibrata dell'Under. Il regolamento NON si scrive da qui.
- **Quando scatta**: la decisione porta notizie.
- **Cosa succede dopo**: cash out, attesa copertura e uscita in perdita vengono anche ricordati sulla scheda (`last_cashout`, `last_cover_wait`, `last_loss_exit`); all'esecuzione su approvazione si aggiunge l'id della richiesta.
- **Numeri**: 300 s per `loss_exit_deciso`.
- **Esempio**: -
- **Cosa vede l'utente**: righe in Attivita'.
- **Dove**: `service.py:4529-4578`.
- **Paper o live**: identico.

### 49. Il cambio di stato registrato una volta
- **Cosa fa**: scrive l'attivita' `state` (da, a, motivo) solo quando lo stato cambia davvero; salva il motivo come "ultimo motivo".
- **Quando scatta**: stato nuovo diverso da quello salvato.
- **Numeri**: -
- **Cosa succede dopo**: -
- **Esempio**: `PRE_OPEN` -> `PRE_GREEN_PENDING`.
- **Cosa vede l'utente**: riga `state` in Attivita'.
- **Dove**: `service.py:4582-4584`.
- **Paper o live**: identico.

### 50. La scheda dal vivo della partita e il suo salvataggio
- **Cosa fa**: calcola tutto cio' che la scheda mostra, gia' netto di commissione: "se chiudo ora" (netto, lordo, base, percentuale sulla base, per selezione, selezioni gia' decise, completezza, soglia), minuto, gol, in gioco, intervallo, punteggio, eta' del feed, eta' scanner, linee mancanti, riconciliazione in corso, rischio, bloccato, divieto di rientro, scambiato, rossi, probabilita' di modello ed empiriche, hazard (atlante e modello, versione, fase, recupero atteso, nota), risparmio atteso copertura, P(4) mercato e modello, fonte dei gol attesi, prezzo Under al fischio e scostamento in tick dall'ingresso, P&L per numero di gol (posizione aperta e partita intera), P&L dei cicli chiusi, riepilogo cicli, investito, posizione per selezione con liquidita', ora di pubblicazione, book, freschezza. Poi salva (scheda 70).
- **Quando scatta**: fine di ogni giro completo della partita.
- **Cosa succede dopo**: salvataggio immediato se e' cambiato un fatto, altrimenti a cadenza.
- **Numeri**: `cashout_place_at_ticks` = 0 (config, UI); `cashout_profit_pct` = 5% (config, UI).
- **Esempio**: back Under 10 EUR + copertura Over 4.5 2,40 EUR (base "total" = 12,40); "se chiudo ora" +0,65 netto = 5,24% della base -> sopra la soglia del 5%.
- **Cosa vede l'utente**: tutta la card della partita.
- **Dove**: `service.py:4587-4679`.
- **Paper o live**: identico.

---

# PARTE C - RIGHE DI ORDINE, RICONCILIAZIONE, RITIRI

### 51. Le righe di ordine della partita, lette una volta per giro
- **Cosa fa**: legge le righe di ordine (`mike_trades`) della partita una volta sola per giro e le tiene per il resto del giro. Se la lettura fallisce risponde "non so" (mai "nessuna riga").
- **Quando scatta**: quando serve una riga (riconciliazione, ritiri, collegamenti).
- **Cosa succede dopo**: "non so" non va nella memoria del giro.
- **Numeri**: -
- **Esempio**: rete che cade: la riparazione NON reinserisce righe (evita P&L doppio).
- **Cosa vede l'utente**: niente.
- **Dove**: `service.py:4682-4700`.
- **Paper o live**: identico.

### 52. Collegare una chiusura alla sua apertura
- **Cosa fa**: costruisce l'elenco "riferimento della gamba -> numero della riga" per scrivere su ogni chiusura quale apertura chiude.
- **Quando scatta**: alla prima chiusura del giro.
- **Numeri**: -
- **Cosa succede dopo**: -
- **Esempio**: lay green `under_green-0-2` chiude la riga 1532 dell'ingresso.
- **Cosa vede l'utente**: cicli raggruppati nella scheda Trade.
- **Dove**: `service.py:4703-4711`.
- **Paper o live**: identico.

### 53. La riga di una gamba
- **Cosa fa**: trova la riga di ordine con lo stesso riferimento della gamba.
- **Quando scatta**: ritiri, riconciliazione.
- **Numeri**: -
- **Cosa succede dopo**: nessuna riga = nulla.
- **Esempio**: -
- **Cosa vede l'utente**: -
- **Dove**: `service.py:4714-4719`.
- **Paper o live**: identico.

### 54. L'esito di un ordine e' ignoto?
- **Cosa fa**: risponde SI' se le righe non si leggono, se la gamba non ha riga, o se la riga dice "eccezione durante il piazzamento, in riconciliazione". Nel dubbio si risponde si' (mai cancellare un ordine che potrebbe essere vivo).
- **Quando scatta**: ordine in attesa oltre 120 s (scheda 40).
- **Numeri**: -
- **Cosa succede dopo**: -
- **Esempio**: -
- **Cosa vede l'utente**: -
- **Dove**: `service.py:4722-4736`.
- **Paper o live**: identico.

### 55. L'indice delle righe aperte di tutte le partite
- **Cosa fa**: con una sola interrogazione (a pagine da 1000) legge tutte le righe `pending`, `open`, `hedged` e le divide per partita.
- **Quando scatta**: una volta per giro.
- **Cosa succede dopo**: lettura fallita = "non so" -> ogni partita legge le sue righe.
- **Numeri**: pagine da 1000 (`db.PAGE_SIZE`).
- **Esempio**: -
- **Cosa vede l'utente**: -
- **Dove**: `service.py:4739-4756`; `db.py:196-207`.
- **Paper o live**: legge insieme paper e live (le righe sono per partita).

### 56. Lo specchio gambe/righe combacia?
- **Cosa fa**: se tutte le gambe non archiviate abbinate o in riconciliazione hanno una riga aperta, nessuna riga aperta e' senza gamba, e nessuna riga aperta appartiene a una gamba annullata senza abbinato, lo specchio combacia e non si legge niente.
- **Quando scatta**: all'inizio della riparazione (scheda 59).
- **Numeri**: -
- **Cosa succede dopo**: indice assente -> "non combacia".
- **Esempio**: -
- **Cosa vede l'utente**: -
- **Dove**: `service.py:4759-4772`.
- **Paper o live**: identico.

### 57. Ricostruire una gamba da una riga rimasta sola
- **Cosa fa**: da una riga `pending` senza gamba ricostruisce una gamba in riconciliazione: mercato dal tipo di mercato, selezione dal numero di selezione (o dal nome "Under..."/"Over..."), lato back/lay, prezzo, importo, persistenza (default LAPSE), ciclo, riga che chiude.
- **Quando scatta**: scheda 58.
- **Cosa succede dopo**: se mercato, selezione o lato non sono leggibili -> niente.
- **Numeri**: -
- **Esempio**: -
- **Cosa vede l'utente**: -
- **Dove**: `service.py:4775-4810`.
- **Paper o live**: identico.

### 58. Le "riserve orfane" (riga scritta ma risposta persa)
- **Cosa fa**: una riga `pending` la cui gamba e' annullata senza abbinato, o che non ha piu' gamba, non si chiude per deduzione: la gamba va (o torna) in riconciliazione e la riga viene marcata "eccezione, in riconciliazione"; sara' la riconciliazione (scheda 60) a decidere con la fonte vera.
- **Quando scatta**: dentro la riparazione (scheda 59), quando lo specchio non combacia.
- **Cosa succede dopo**: riga critica nel registro; attivita' critica `reconcile_pending` con motivo `riserva_orfana` e modo (`gamba_annullata` / `gamba_ricostruita`).
- **Numeri**: -
- **Esempio**: la scrittura della riga va in timeout ma il server l'ha salvata; la gamba era stata annullata "riserva fallita": senza questa regola la copertura dello stesso ruolo resterebbe bloccata per sempre.
- **Cosa vede l'utente**: attivita' `reconcile_pending`.
- **Dove**: `service.py:4813-4871`.
- **Paper o live**: identico qui; l'esito diverge nella scheda 60.

### 59. La riparazione dello specchio gambe <-> righe
- **Cosa fa**: ripara due buchi: (1) gamba abbinata (o in riconciliazione) senza riga -> la riga viene RISCRITTA (con importo e prezzo abbinati e rischio ricalcolato sull'abbinato); (2) riga aperta senza gamba -> in paper chiusa in `error` (zombie, motivo `orphan_paper`), in live solo marcata "orfana" e gridata. Inoltre riporta in colonna il collegamento chiusura->apertura rimasto nei dati extra, e aggancia le riserve orfane (scheda 58).
- **Quando scatta**: ogni 30 s per partita (scheda 27), se lo specchio non combacia (scheda 56).
- **Cosa succede dopo**: righe illeggibili -> nessuna riparazione, attivita' critica `reconcile_pending` "righe_illeggibili". Gambe archiviate, gambe senza abbinato e non ignote, dati partita incompleti -> non si ricostruiscono. Righe con collegamento a un'apertura, o gia' orfane, o non `pending/open/hedged` -> non toccate. Ogni riparazione: attivita' `reconcile_fix` (`riga_ricostruita`, `closes_trade_id_ripristinato`, `riga_orfana`).
- **Numeri**: `reconcile_every_s` = 30 s.
- **Esempio**: crash dopo un fill da 10 EUR a 1,92 prima della scrittura della riga: al riavvio la riga viene ricostruita `open`, 10,00 a 1,92, rischio 10,00.
- **Cosa vede l'utente**: attivita' `reconcile_fix` critiche.
- **Dove**: `service.py:4874-4974`.
- **Paper o live**: riga orfana: paper chiusa in errore, live solo marcata.

### 60. Chiarire un ordine a esito ignoto
- **Cosa fa**: per ogni gamba in riconciliazione con riga: in PAPER, se l'ordine e' sul runner, non fa niente (decide il runner); altrimenti la dichiara "mai piazzata". In LIVE legge gli ordini correnti e regolati da Betfair, riconosce l'ordine della riga (numero scommessa, riferimento `mike-t<id>`, riferimento storico a mercato concorde) e lo consegna alla regola comune che decide: confermato (abbinato), liberato (mai esistito), o attesa.
- **Quando scatta**: scheda 41 (ritmo frenato).
- **Cosa succede dopo**: Betfair non raggiungibile -> attivita' critica `reconcile_pending` "betfair_non_raggiungibile", nessuna ipotesi. Confermata -> gamba `open` con importo e prezzo veri, riga `open` con numero scommessa, attivita' `reconcile_fix` "confermata". Liberata/errore -> gamba annullata, riga `error` "reconciled_not_placed", attivita' `reconcile_fix` "mai_piazzata". Attesa -> attivita' `reconcile_pending` "attesa".
- **Numeri**: -
- **Esempio**: live, green-up inviato, rete caduta: Betfair lo mostra abbinato 10,10 a 1,86 -> confermato; nessun secondo green-up.
- **Cosa vede l'utente**: attivita' `reconcile_fix` / `reconcile_pending`.
- **Dove**: `service.py:4977-5074`; regola `X.reconcile_decision` (safe_strategy/execution, fuori area); `_ordine_della_riga` `service.py:2229` (area B).
- **Paper o live**: paper senza runner = risolto subito; paper con runner = runner; live = Betfair.

### 61. Il ritiro di un ordine (prima si annulla sul mercato, poi si scrive)
- **Cosa fa**: annulla l'ordine sul mercato e solo dopo aggiorna la riga. Tre esiti: annullato confermato -> ritirato; annullato ma abbinato nel frattempo -> la parte abbinata resta posizione aperta; annullo non confermato -> la gamba resta in riconciliazione (mai dichiarata ritirata su un ordine forse vivo).
- **Quando scatta**: annulli dell'utente, del motore, degli ordini in attesa da troppo.
- **Cosa succede dopo**:
  - riga assente o non `pending` -> nessuna chiamata al mercato; gamba `open` se ha abbinato, altrimenti annullata;
  - riga paper sul runner senza numero scommessa: se il runner non ha ancora detto quale ordine e' -> si segna "annullo richiesto" e la gamba va in riconciliazione;
  - riga live (o paper sul runner) con numero scommessa -> attivita' critica `cancel_richiesto`, annullo, attivita' critica `cancel_esito` (confermato, importi annullati e abbinati, codice d'errore); non confermato -> riconciliazione; abbinato durante l'annullo -> attivita' critica `fill_resting` e la gamba resta aperta;
  - riga aggiornata: con abbinato -> `open` con importo e prezzo veri; senza -> `error` con motivo del ritiro.
- **Numeri**: -
- **Esempio**: lay 10,10 a 1,86 in attesa, annullo: Betfair conferma annullati 6,10 e abbinati 4,00 -> gamba aperta 4,00 a 1,86.
- **Cosa vede l'utente**: attivita' `cancel_richiesto`, `cancel_esito`, `fill_resting`.
- **Dove**: `service.py:5077-5186`.
- **Paper o live**: live -> Betfair; paper con runner -> runner (stessa regola); paper senza runner -> solo la riga.

### 62. "Annulla ordini" dalla pagina
- **Cosa fa**: annulla tutti gli ordini ancora in attesa della partita senza toccare la posizione abbinata.
- **Quando scatta**: richiesta dell'utente.
- **Cosa succede dopo**: niente di vivo -> "Nessun ordine vivo da annullare." Altrimenti ritiro di ogni gamba (scheda 61, motivo `cancelled_by_user`), attivita' `cancel` per ognuna, salvataggio; messaggio "Annullati N ordini sul book." con avviso se alcuni annulli non sono confermati ("in verifica, l'ordine potrebbe essere ancora vivo").
- **Numeri**: -
- **Esempio**: 2 lay appoggiate, una confermata e una no: "Annullati 1 ordini sul book. ATTENZIONE: 1 annullamenti non confermati da Betfair, in verifica".
- **Cosa vede l'utente**: il messaggio sopra.
- **Dove**: `service.py:3253-3280`.
- **Paper o live**: scheda 61.

### 63. "Cash out" e "Flatten" dalla pagina
- **Cosa fa**: arma la chiusura manuale: annulla subito gli ordini vivi, poi la chiusura della posizione netta la guida il motore nello stesso giro e nei successivi. Prima del fischio la partita non rientra piu' finche' l'utente non preme "Riprendi".
- **Quando scatta**: richiesta dell'utente (`kind` = cashout o flatten).
- **Cosa succede dopo**:
  1. parametri della modalita' della partita;
  2. partita non nel feed o incompleta -> rifiuto `feed_assente` ("Quote non disponibili...");
  3. fotografia assente -> `snapshot_assente`;
  4. flusso prezzi interrotto -> prova il ripiego REST senza tetto; se non legge -> rifiuto `flusso_interrotto`; se legge -> attivita' `ripiego_rest` e si prosegue con i prezzi Betfair;
  5. prezzi non abbastanza freschi per un ordine (e non dal ripiego) -> rifiuto `feed_stantio`;
  6. niente da annullare ne' da chiudere -> motivo "manual", divieto di rientro se pre-partita, "Nessuna posizione da chiudere." (o "Prezzi non disponibili...");
  7. altrimenti: annulli (motivo `cancelled_manual`, attivita' `cancel`), chiusura armata, tentativi a zero, divieto di rientro se pre-partita, messaggio "Cash out: annullati N ordini sul book, chiusura in corso (netto stimato X EUR)." con avviso se c'e' riconciliazione.
- **Numeri**: `cashout_place_at_ticks` = 0; freschezza d'ordine scheda 87.
- **Esempio**: Under 3.5 aperto a 1,90 pre-partita, lay green appoggiata: la lay viene annullata e la chiusura parte; netto stimato +0,15 EUR.
- **Cosa vede l'utente**: i messaggi sopra.
- **Dove**: `service.py:3283-3393`.
- **Paper o live**: stessa logica; annulli come scheda 61.

---

# PARTE D - LA CHIUSURA DEI CONTI

### 64. Le righe non aggiornate dal regolamento: si riprova
- **Cosa fa**: se le righe di ordine non si aggiornano al regolamento, la partita NON diventa terminale: torna in regolamento e si riprova alla lettura successiva; al quinto fallimento si chiude lo stesso, gridando.
- **Quando scatta**: aggiornamento delle righe fallito (scheda 66).
- **Cosa succede dopo**: tentativi 1-4: attivita' critica `error settle_rows_retry`, stato `SETTLING`; tentativo 5: attivita' critica `error settle_rows_failed` ("righe da sistemare a mano") e la partita si chiude.
- **Numeri**: `_SETTLE_ROWS_MAX_TRIES` = 5 (costante).
- **Esempio**: -
- **Cosa vede l'utente**: attivita' `error`.
- **Dove**: `service.py:5189-5217`.
- **Paper o live**: identico.

### 65. La commissione del regolamento e' quella scritta sulle righe
- **Cosa fa**: regola con la commissione salvata sulle righe della partita al momento del piazzamento, non con quella attuale: se l'utente cambia la commissione a posizione aperta, il vecchio P&L non cambia.
- **Quando scatta**: a ogni regolamento.
- **Cosa succede dopo**: righe illeggibili -> commissione attuale; righe con aliquote diverse -> commissione attuale e attivita' critica `settle_commissione_mista`; un'aliquota sola uguale all'attuale -> nessun cambio; diversa -> si usa quella.
- **Numeri**: `commission_pct` = 5% (config, UI).
- **Esempio**: righe scritte al 5%, oggi il parametro e' 2%: si regola al 5%.
- **Cosa vede l'utente**: attivita' `settle_commissione_mista` se mista.
- **Dove**: `service.py:5220-5253`.
- **Paper o live**: identico.

### 66. Scrivere il regolamento sulle righe
- **Cosa fa**: scrive su ogni riga esito (vinta/persa/nulla) e P&L netto di commissione, con lordo, commissione pagata, commissione del mercato e motivo "mercato annullato" se void. Se due righe hanno lo stesso riferimento, il P&L va solo sulla piu' vecchia e le altre diventano `error` "duplicate_signal_key".
- **Quando scatta**: partita regolata.
- **Cosa succede dopo**: righe gia' chiuse (won/lost/void/error) non toccate. Righe illeggibili -> attivita' critica `error settle_rows_unreadable`, esito "non scritto". Aggiornamento fallito -> attivita' critica `error settle_update_failed`. Gambe regolate senza riga: con P&L non nullo (oltre 0,005) -> attivita' critica `error settle_leg_senza_riga`; tutte a zero -> attivita' `settle_gambe_non_piazzate` (cronaca).
- **Numeri**: soglia 0,005 EUR (costante nel codice).
- **Esempio**: gamba lordo +1,00, netto +0,95: `pnl_gross` 1,00, `commission_paid` 0,05.
- **Cosa vede l'utente**: P&L sulle righe (Trade, Storico); attivita' citate.
- **Dove**: `service.py:5256-5362` (`_pnl_of` 5342-5350).
- **Paper o live**: identico.

---

# PARTE E - SALVATAGGIO E PUBBLICAZIONE VERSO LA PAGINA

### 67. La partita ha soldi sul tavolo?
- **Cosa fa**: risponde si' se ha almeno una gamba non archiviata che non e' ne' annullata ne' regolata.
- **Quando scatta**: per decidere la cadenza di pubblicazione (scheda 68).
- **Numeri**: -
- **Cosa succede dopo**: -
- **Esempio**: -
- **Cosa vede l'utente**: -
- **Dove**: `service.py:5411-5421`.
- **Paper o live**: identico.

### 68. Ogni quanto si rinfresca una scheda che non e' cambiata
- **Cosa fa**: partita terminale -> mai; partita con soldi sul tavolo o in gioco -> ogni `publish_heartbeat_s`; partita solo osservata -> ogni `publish_idle_heartbeat_s`.
- **Quando scatta**: scheda 70.
- **Numeri**: `publish_heartbeat_s` = 5 s; `publish_idle_heartbeat_s` = 60 s (config, UI).
- **Cosa succede dopo**: -
- **Esempio**: partita in WATCH senza gambe: una scrittura al minuto.
- **Cosa vede l'utente**: l'eta' delle quote sulla card (rossa oltre 20 s spegne il cash out).
- **Dove**: `service.py:5424-5435`.
- **Paper o live**: identico.

### 69. Scrivere la scheda della partita (e gridare se fallisce)
- **Cosa fa**: salva la scheda della partita; se il database la rifiuta, lo grida (critico nel registro e attivita' `error` "stato_non_scritto" con stato e se c'e' posizione aperta).
- **Quando scatta**: ogni salvataggio.
- **Numeri**: -
- **Cosa succede dopo**: il bot continua, ma senza memoria salvata di dove si trova.
- **Esempio**: stato nuovo non ammesso dal vincolo del database: attivita' `error stato_non_scritto` in pagina.
- **Cosa vede l'utente**: attivita' `error`.
- **Dove**: `service.py:5438-5471`.
- **Paper o live**: identico.

### 70. Quando si scrive la scheda (solo se cambia un fatto, o a cadenza)
- **Cosa fa**: spinge SEMPRE la scheda sullo schermo; sul database scrive subito se e' cambiato un fatto (stato, gamba, gol, regolamento...), altrimenti solo alla cadenza della scheda 68, e in quel caso nel lotto di fine giro.
- **Quando scatta**: fine del giro della partita e uscite anticipate.
- **Cosa succede dopo**: scrittura immediata toglie la partita dal lotto. I campi che cambiano da soli (ore, eta', book, hazard, probabilita', "ultimo motivo"...) non contano come fatto.
- **Numeri**: schede 68.
- **Esempio**: il book oscilla di un tick: nessuna scrittura; entra un gol: scrittura subito.
- **Cosa vede l'utente**: card aggiornata a ogni giro via canale locale.
- **Dove**: `service.py:5474-5516`; firma `service.py:486-526`.
- **Paper o live**: identico.

### 71. Il lotto delle scritture di cortesia
- **Cosa fa**: invia in una sola scrittura le schede da rinfrescare; se la scrittura in blocco non c'e', e' spenta, o fallisce, scrive riga per riga (mai perdere una scrittura).
- **Quando scatta**: fine del giro (sempre, anche dopo un errore).
- **Numeri**: `events_batch_write` = acceso (config, UI); in blocco solo se piu' di una riga.
- **Cosa succede dopo**: -
- **Esempio**: 8 partite osservate da rinfrescare: una sola POST.
- **Cosa vede l'utente**: -
- **Dove**: `service.py:5519-5540`.
- **Paper o live**: identico.

### 72. Il canale locale verso lo schermo (porta 47333)
- **Cosa fa**: accende un canale locale in sola lettura verso l'app, per mostrare quote, P&L e stato senza passare dal database.
- **Quando scatta**: all'avvio (non con `--once`).
- **Cosa succede dopo**: porta occupata o errore -> avviso; la pagina legge dal database come prima.
- **Numeri**: porta 47333 (`_PORTA_CANALE`), env `MIKE_LOCAL_WS_PORT`.
- **Esempio**: -
- **Cosa vede l'utente**: aggiornamenti al ritmo del bot.
- **Dove**: `service.py:5552-5569`.
- **Paper o live**: identico.

### 73. Cosa si spinge sullo schermo
- **Cosa fa**: spinge la scheda di ogni partita (senza dossier, mercati, contesto e ora di scrittura del database) e i numeri di testata (controllo, aggregati, statistiche, ora).
- **Quando scatta**: a ogni salvataggio della partita e a ogni giro.
- **Cosa succede dopo**: errore -> ignorato. L'ora del database NON si manda: rimanderebbe indietro l'orologio della card e spegnerebbe il cash out.
- **Numeri**: -
- **Esempio**: -
- **Cosa vede l'utente**: card e testata.
- **Dove**: `service.py:5950-5968`.
- **Paper o live**: identico.

---

# PARTE F - LA SVEGLIA AL MILLISECONDO E IL CANALE DELLO SCANNER

### 74. La sveglia del giro (si sveglia quando si muove una partita seguita)
- **Cosa fa**: invece di dormire sempre il tempo pieno, Mike puo' essere svegliato dallo scanner quando cambia una partita che sta seguendo, o dalla pagina (solo messaggio "sveglia", nessun ordine passa di qui).
- **Quando scatta**: solo con interruttore `MIKE_SVEGLIA_CANALE` acceso (di serie SPENTO).
- **Cosa succede dopo**: con anche `MIKE_LEGGE_CANALE` acceso, la sveglia la porta il lettore unico delle righe (scheda 76); altrimenti si apre l'ascolto del canale dello scanner (argomento `scan_calcio`) filtrato sulle partite in memoria. La sveglia da pagina si aggancia al canale 47333 se questo la sa ricevere; minimo fra due sveglie da pagina 1 s.
- **Numeri**: `MINIMO_UI_S` = 1,0 s (sveglia_canale); porta scanner 47336 (env `SAFE_SCAN_WS_PORT`).
- **Esempio**: gol alle 21:14:03.200: lo scanner lo pubblica, Mike si sveglia invece di aspettare la fine della dormita.
- **Cosa vede l'utente**: niente (statistiche `sveglia`).
- **Dove**: `service.py:5584-5617` (`_SVEGLIA`, `_ASCOLTO_SCAN`, `_AlzaSveglia` con `__init__` 5603 e `set` 5606, `_evento_seguito` 5610), `5635-5646` (`_su_sveglia_dal_canale`), `5649-5685` (`_avvia_sveglia`).
- **Paper o live**: identico.

### 75. Il pavimento della sveglia e la dormita
- **Cosa fa**: per quante sveglie arrivino, fra l'inizio di un giro e il successivo passa almeno il passo attivo di oggi, cosi' le letture al minuto non crescono. Con sveglia spenta la dormita e' la solita pausa.
- **Quando scatta**: fine di ogni giro.
- **Cosa succede dopo**: pavimento = max(1 s, `decide_min_interval_ms`/1000 x 2). Statistiche della sveglia pubblicate solo a interruttore acceso.
- **Numeri**: con 500 ms -> pavimento 1,0 s.
- **Esempio**: dormita di 5 s a riposo; arriva una sveglia dopo 0,3 s: Mike aspetta fino a 1,0 s e riparte.
- **Cosa vede l'utente**: -
- **Dove**: `service.py:5620-5632`, `5688-5718` (`_client_scan_alza_sveglia`, `statistiche_sveglia`, `_dormi_o_sveglia`).
- **Paper o live**: identico.

### 76. Le righe dello scanner dal canale locale 47336 (interruttore)
- **Cosa fa**: con `MIKE_LEGGE_CANALE` acceso, un lettore unico (quello di Safe) riceve le righe dello scanner al tick; il database resta la LISTA delle partite e il ripiego.
- **Quando scatta**: acceso all'avvio; l'interruttore si rilegge a ogni chiamata. Di serie SPENTO.
- **Cosa succede dopo**: errore d'avvio -> avviso, si lavora dal database. "Azzera" spegne e dimentica il lettore (usato quando si svuotano le cache).
- **Numeri**: `_RISINC_FEED_S` = 10 s; porta 47336.
- **Esempio**: -
- **Cosa vede l'utente**: statistiche `fonte_scan`, `righe_dal_canale`, `canale_scan`.
- **Dove**: `service.py:5754-5825` (`ENV_MIKE_LEGGE_CANALE`, `_RISINC_FEED_S`, `_CANALE_FEED`, `_canale_feed_acceso`, `avvia_client_scan`, `azzera_canale_scan`).
- **Paper o live**: identico.

### 77. Da dove arrivano le righe del giro (canale o database) e ogni quanto si rilegge
- **Cosa fa**: con il canale acceso prende le righe del canale non piu' vecchie di 5 s; se OGNI partita della lista del database ha una riga fresca del canale almeno altrettanto recente e con l'ora delle quote, il database si rilegge ogni 10 s invece di 4; poi unisce: la riga del canale vince solo se strettamente piu' recente.
- **Quando scatta**: ogni giro.
- **Cosa succede dopo**: canale spento -> righe del database, fonte "db". Qualsiasi dubbio -> cadenza di sempre.
- **Numeri**: eta' massima dal canale `CS.MAX_ETA_CONTESTO_S` = 5 s; `feed_cache_s` = 4 s; `_RISINC_FEED_S` = 10 s.
- **Esempio**: 12 partite in lista, tutte coperte dal canale: una lettura del database ogni 10 s.
- **Cosa vede l'utente**: `fonte_scan` = "canale" o "db".
- **Dove**: `service.py:5828-5919` (`_canale_copre_tutte`, `_righe_del_feed`, `statistiche_canale_scan`).
- **Paper o live**: identico.

---

# PARTE G - FEED.PY: DA DOVE ARRIVANO PREZZI E PUNTEGGI

### 78. I dati della partita (nomi, calcio d'inizio, mercati, selezioni)
- **Cosa fa**: dalla riga dello scanner ricava nome, squadre, competizione, ora del calcio d'inizio (`open_date`), numeri dei mercati 3.5 e 4.5 e numeri delle selezioni Under/Over riconosciuti PER NOME. La partita e' "completa" se ha entrambi i mercati, l'Under 3.5 e l'Over 4.5.
- **Quando scatta**: ogni giro.
- **Cosa succede dopo**: qui NON si scartano i mercati fermi o non osservati (servono per annullare ordini). Nome della selezione = "Under 3.5 Goals" ecc.
- **Numeri**: linee 3.5 e 4.5.
- **Esempio**: -
- **Cosa vede l'utente**: -
- **Dove**: `feed.py:25-51` (`EventInfo`, `complete`, `market_id`, `selection_id`, `selection_name`), `194-215` (`event_info`).
- **Paper o live**: identico.

### 79. Date e numeri letti dal feed
- **Cosa fa**: trasforma le date in secondi (senza fuso = UTC) e i numeri in numeri; illeggibile = niente.
- **Quando scatta**: ovunque.
- **Numeri**: -
- **Cosa succede dopo**: -
- **Esempio**: "2026-09-29T19:00:00Z" -> epoch.
- **Cosa vede l'utente**: -
- **Dove**: `feed.py:54-71`.
- **Paper o live**: identico.

### 80. I blocchi Over/Under e il book "ancora osservato"
- **Cosa fa**: prende i blocchi 3.5 e 4.5. Quando si DECIDE, scarta come assente un blocco non piu' osservato dallo scanner (ultimo book ricevuto piu' vecchio di `book_seen_max_s`) e un blocco col flusso fermo. Uno scanner vecchio senza l'ora di osservazione = osservato.
- **Quando scatta**: fotografia (scheda 88) e regolamento (solo stato).
- **Numeri**: `book_seen_max_s` = 90 s (config, 5-600, UI).
- **Cosa succede dopo**: blocco scartato = nessun prezzo = nessuna azione su quella linea.
- **Esempio**: la 4.5 non e' piu' ricevuta da 3 minuti ma la riga si aggiorna per minuto e punteggio: la 4.5 e' considerata assente.
- **Cosa vede l'utente**: linea mancante sulla card.
- **Dove**: `feed.py:74-95` (`blocco_osservato`), `131-140` (`payload_blocchi_ou`, senza filtri), `164-191` (`ou_blocks`).
- **Paper o live**: identico.

### 81. Il flusso dei prezzi delle linee di Mike e' vivo?
- **Cosa fa**: interroga la regola comune del flusso con lo stato dello scanner e i soli mercati 3.5 e 4.5 (non il mercato principale): se il giro dello scanner e' bloccato o una delle due linee e' dichiarata ferma, il flusso non e' vivo.
- **Quando scatta**: fotografia, chiusura manuale, giro della partita.
- **Cosa succede dopo**: riga senza dati di flusso = "non noto" = vivo (condotta di prima), salvo che lo scanner nuovo dichiari il flusso e la riga no (allora NON vivo).
- **Numeri**: giro scanner fermo oltre 45 s (`STATO_CALCOLO_MAX_S`).
- **Esempio**: -
- **Cosa vede l'utente**: vedi scheda 36.
- **Dove**: `feed.py:98-128`; `flusso_prezzi.py:147-237`.
- **Paper o live**: identico.

### 82. Un book letto da Betfair trasformato nel formato del feed
- **Cosa fa**: converte il book REST in un blocco uguale a quello del feed (prezzi e importi back/lay per selezione), col ritardo di piazzamento preso dal feed; solo se il mercato e' OPEN e ha selezioni.
- **Quando scatta**: ripiego REST (scheda 36).
- **Numeri**: -
- **Cosa succede dopo**: -
- **Esempio**: -
- **Cosa vede l'utente**: -
- **Dove**: `feed.py:143-161`.
- **Paper o live**: identico.

### 83. Il prezzo di una selezione
- **Cosa fa**: per una selezione legge miglior back e importo, miglior lay e importo, stato (default OPEN), in gioco, ritardo di piazzamento (default 0).
- **Quando scatta**: fotografia.
- **Numeri**: -
- **Cosa succede dopo**: -
- **Esempio**: -
- **Cosa vede l'utente**: book sulla card.
- **Dove**: `feed.py:218-230`.
- **Paper o live**: identico.

### 84. Le probabilita' implicite del mercato
- **Cosa fa**: dai back delle due linee, tolto il margine, calcola P(Over 3.5) e P(Over 4.5); da qui P(esattamente 4 gol) = P(O3.5) - P(O4.5), e la distribuzione in tre classi (<=3, 4, >=5).
- **Quando scatta**: fotografia.
- **Numeri**: -
- **Cosa succede dopo**: un prezzo mancante = niente.
- **Esempio**: O3.5 2,10 / U3.5 1,90 -> P(O3.5)=0,475; O4.5 3,60 / U4.5 1,38 -> P(O4.5)=0,277; P(4) = 0,198.
- **Cosa vede l'utente**: P(4) mercato sulla card.
- **Dove**: `feed.py:233-283` (`implied_p4` e `market_totals`, ognuna col suo `p_over`).
- **Paper o live**: identico.

### 85. Punteggio e intervallo
- **Cosa fa**: gol totali = casa + trasferta (se uno manca, niente); intervallo = lo stato della partita contiene "half" e "end", oppure vale "halftime", "half_time", "ht".
- **Quando scatta**: ogni giro.
- **Numeri**: -
- **Cosa succede dopo**: -
- **Esempio**: punteggio 1 e 2 -> 3 gol; stato "HalfTime" -> diventa "halftime" -> intervallo; stato "FirstHalfEnd" -> contiene "half" ed "end" -> intervallo.
- **Cosa vede l'utente**: punteggio e HT sulla card.
- **Dove**: `feed.py:286-301`.
- **Paper o live**: identico.

### 86. Freschezza per DECIDERE
- **Cosa fa**: la riga e' fresca se ha al massimo `feed_max_age_s`; oltre, vale lo stesso se lo scanner ha battuto da poco (scrive solo cio' che cambia); ma oltre il tetto assoluto non vale mai.
- **Quando scatta**: fotografia.
- **Numeri**: `feed_max_age_s` = 45 s (config, 3-180, UI); `scanner_alive_max_s` = 75 s (config, UI); tetto assoluto 180 s (env `SCAN_FEED_HARD_MAX_AGE_SEC`, default 180; se il modulo non si carica 180).
- **Cosa succede dopo**: -
- **Esempio**: riga di 60 s, scanner 20 s fa -> fresca; riga di 200 s -> mai.
- **Cosa vede l'utente**: semaforo feed.
- **Dove**: `feed.py:304-336`.
- **Paper o live**: identico.

### 87. Freschezza per ORDINARE (piu' severa)
- **Cosa fa**: per mandare un ordine: oltre il tetto assoluto mai; entro `order_max_age_s` si'; altrimenti solo se lo scanner ha battuto entro `order_scanner_max_s`.
- **Quando scatta**: fotografia (aperture, chiusura manuale).
- **Numeri**: `order_max_age_s` = 20 s; `order_scanner_max_s` = 30 s (config, UI); tetto 180 s.
- **Cosa succede dopo**: -
- **Esempio**: riga di 25 s, scanner 12 s fa -> si puo' ordinare.
- **Cosa vede l'utente**: rifiuto "Feed non aggiornato" sul cash out.
- **Dove**: `feed.py:339-371`.
- **Paper o live**: identico.

### 88. La fotografia del mercato (cio' su cui il motore decide)
- **Cosa fa**: costruisce la fotografia: book di Under 3.5, Over 4.5, Under 4.5 (solo blocchi osservati e con flusso vivo; con giro scanner bloccato nessun book; col ripiego REST i book di Betfair), in gioco, stato del mercato (dalla 3.5, poi mercato principale, default OPEN), minuto (solo se intero), gol, intervallo, freschezze (col ripiego: decidere si', ordinare no), fonte dei prezzi, hazard, P(4) mercato e modello, ultimo gol, risparmio copertura, pressione, probabilita' modello/empiriche/mercato, P(Under 3.5) calibrata, scambiato (solo diagnostica).
- **Quando scatta**: ogni giro e chiusura manuale.
- **Cosa succede dopo**: riga senza dati o senza ora di calcio d'inizio -> niente fotografia.
- **Numeri**: schede 80, 86, 87.
- **Esempio**: -
- **Cosa vede l'utente**: card.
- **Dove**: `feed.py:374-440`.
- **Paper o live**: identico.

### 89. Quando una partita e' candidata
- **Cosa fa**: completa, con ora di inizio, che passa il filtro competizioni (basta che il nome contenga uno dei testi separati da virgola, senza maiuscole), non in gioco, e con calcio d'inizio fra 0 e `entry_hours_before_ko` ore.
- **Quando scatta**: scheda 13.
- **Numeri**: `entry_hours_before_ko` = 1,0 h; `competition_filter` = "".
- **Cosa succede dopo**: -
- **Esempio**: filtro "serie a" -> passa anche "Serie A Women".
- **Cosa vede l'utente**: -
- **Dove**: `feed.py:443-460`.
- **Paper o live**: identico.

---

# PARTE H - DB.PY: COSA SI SALVA E DOVE

### 90. Le tabelle e il collegamento al database
- **Cosa fa**: definisce le tabelle: `mike_control` (riga unica id 1: stato, modalita', parametri, statistiche, battito), `mike_events` (una scheda per partita: stato, gambe `positions`, `live`, `ctx`, `dossier`, `markets`), `mike_trades` (una riga per gamba), `mike_activity` (attivita'), `mike_requests` (comandi della pagina). Con `MIKE_CANALE_POSIZIONI` acceso le righe scritte escono anche sul canale 47333, DOPO la scrittura riuscita.
- **Quando scatta**: sempre.
- **Numeri**: pagine da 1000; `MIKE_CANALE_POSIZIONI` di serie spento.
- **Cosa succede dopo**: -
- **Esempio**: -
- **Cosa vede l'utente**: -
- **Dove**: `db.py:24-53`.
- **Paper o live**: una sola tabella per modalita'; la modalita' sta sulla riga.

### 91. La riga di controllo
- **Cosa fa**: legge la riga id 1; la scrittura aggiunge sempre l'ora di aggiornamento se non data.
- **Dove**: `db.py:59-68`.
- **Quando scatta**: ogni giro (lettura), battito e arresti (scrittura).
- **Cosa succede dopo**: errori risaliti al chiamante.
- **Numeri**: -
- **Esempio**: -
- **Cosa vede l'utente**: -
- **Paper o live**: identico.

### 92. Le attivita'
- **Cosa fa**: scrive una riga in `mike_activity` (tipo, dati, partita); un errore non ferma mai il bot (solo avviso).
- **Dove**: `db.py:71-80`.
- **Quando scatta**: ovunque.
- **Cosa succede dopo**: se la scrittura fallisce, l'attivita' si perde (resta l'avviso nel registro).
- **Numeri**: -
- **Esempio**: -
- **Cosa vede l'utente**: scheda Attivita'.
- **Paper o live**: identico.

### 93. Le schede delle partite
- **Cosa fa**: legge le partite (non terminali sempre + terminali aggiornate dopo una data); salva una scheda imponendo SEMPRE l'ora di aggiornamento = adesso; salva piu' schede in una sola scrittura. Esistono anche lettura di una partita e cancellazione, non usate da Mike (vedi Cose strane).
- **Dove**: `db.py:88-169`.
- **Quando scatta**: schede 9, 69-71.
- **Numeri**: stati terminali `SETTLED`, `ERROR`, `SKIPPED`.
- **Cosa succede dopo**: -
- **Esempio**: -
- **Cosa vede l'utente**: card aggiornate.
- **Paper o live**: identico.

### 94. Le righe di ordine
- **Cosa fa**: inserisce una riga (torna il numero), aggiorna, legge una riga, legge le righe aperte (`open`, `hedged`, `pending`) a pagine, legge le righe di una partita ordinate per piazzamento, legge "aperte + regolate dopo una data + aperture di quelle chiusure", legge tutto a pagine.
- **Dove**: `db.py:175-249`.
- **Quando scatta**: piazzamenti (area B), riconciliazione, regolamento, aggregati di ripiego.
- **Numeri**: pagine da 1000.
- **Cosa succede dopo**: errori risaliti al chiamante.
- **Esempio**: -
- **Cosa vede l'utente**: scheda Trade.
- **Paper o live**: la colonna `mode` distingue.

### 95. Gli aggregati (realizzato, vinte/perse, aperte, cicli di oggi)
- **Cosa fa**: prima prova la procedura del database `get_mike_aggregates` con la modalita'; se manca davvero (errore di schema) passa per sempre al ripiego nel processo; se e' un guasto temporaneo solleva (il chiamante usa l'ultimo valore buono). Ripiego: righe aperte + regolate oggi, filtrate per modalita', sommate in Python; cumulativi di sempre da una lettura completa tenuta 5 minuti. Regole: giorno = giorno di piazzamento della POSIZIONE (una chiusura eredita quello della sua apertura), P&L gia' netto, riga in riconciliazione = aperta, "piazzata" = in riconciliazione o con numero scommessa o accodata al runner; vinte/perse contate per posizione.
- **Dove**: `db.py:252-411` (`aggregate_rows` con `_placed_at` e `_in_day`, `_rpc_assente`, `aggregates`, `_cumulative_totals`).
- **Quando scatta**: ogni `aggregates_cache_s` (20 s) e dopo ogni azione.
- **Numeri**: `_TOTALS_TTL_S` = 300 s.
- **Cosa succede dopo**: -
- **Esempio**: chiusura alle 00:05 di un trade aperto alle 23:50: conta nel giorno prima.
- **Cosa vede l'utente**: KPI in testata, stop giornaliero.
- **Paper o live**: filtrati per modalita', tranne i cumulativi del ripiego (vedi Cose strane).

### 96. Le richieste della pagina
- **Cosa fa**: legge in una volta richieste `pending` e `processing` (fino a 250, piu' vecchie prima; salvagente: se la finestra e' piena e non ci sono attese, rilegge solo le attese); chiude una richiesta con esito (`rejected` non ammesso dal vecchio schema -> `error`); chiude in errore le `processing` piu' vecchie di 10 minuti.
- **Dove**: `db.py:417-502`.
- **Quando scatta**: ogni giro.
- **Numeri**: limite 50 + 200; 10 minuti.
- **Cosa succede dopo**: -
- **Esempio**: -
- **Cosa vede l'utente**: esito delle richieste.
- **Paper o live**: identico.

### 97. Il feed dello scanner e il suo stato (sola lettura)
- **Cosa fa**: legge tutte le righe calcio di `safe_strategy_scan` (evento, sport, dati, ora) e lo stato `safe_strategy_status` id `scanner`. Una lettura fallita del feed torna "nessuna riga"; dello stato "niente".
- **Dove**: `db.py:508-525`.
- **Quando scatta**: scheda 8.
- **Numeri**: -
- **Cosa succede dopo**: vedi Cose strane (feed fallito = feed vuoto).
- **Esempio**: -
- **Cosa vede l'utente**: -
- **Paper o live**: identico.

### 98. Il ponte partita -> fixture e i dati dei modelli
- **Cosa fa**: cerca il numero di fixture prima in `live_follow`, poi in `omega_events`; legge lambda, lega e id squadre da `fixture_predictions` (tramite `Betfair/stream/db`); legge l'analisi della fixture (rho, mercati calibrati) da Omega; legge le transizioni intervallo->fine gara (Omega). Ogni errore = niente.
- **Dove**: `db.py:531-595`.
- **Quando scatta**: dossier (schede 102, 107).
- **Numeri**: -
- **Cosa succede dopo**: -
- **Esempio**: -
- **Cosa vede l'utente**: fonte del modello sulla card.
- **Paper o live**: identico.

### 99. La coda del runner (copie per il percorso flumine)
- **Cosa fa**: stato della partita in `live_follow`, battito del runner (`betfair_live_heartbeat` id 1), accodamento di un ordine (procedura `request_betfair_live_order`), lettura di una richiesta d'ordine per riferimento o per numero (`betfair_live_order_requests`), revoca di una richiesta ancora `pending` ("revocata da mike (deadline live)"), lettura dello specchio d'ordine (`betfair_live_orders` per modalita' e riferimento).
- **Dove**: `db.py:601-644`.
- **Quando scatta**: dal percorso di esecuzione condiviso (fuori area).
- **Numeri**: -
- **Cosa succede dopo**: -
- **Esempio**: -
- **Cosa vede l'utente**: -
- **Paper o live**: -

### 100. Cosa viene riletto dopo un riavvio del servizio
- **Cosa fa**: al riavvio Mike non ha memoria propria: rilegge la riga di controllo (a ogni giro), le partite seguite (tutte le non terminali, qualsiasi eta', piu' le terminali delle ultime 48 h) con gambe, contesto, dossier e dati live salvati, e le righe di ordine quando servono. Si perdono (e ripartono da zero) solo le memorie di processo: orologi di riparazione, di scrittura, dei log frenati, cache di feed e aggregati, stop gia' registrato, stato della sveglia e del canale.
- **Quando scatta**: primo giro dopo l'avvio.
- **Cosa succede dopo**: la riparazione dello specchio parte subito per ogni partita (orologio a zero); l'attivita' `daily_stop` puo' essere riscritta una volta.
- **Numeri**: -
- **Esempio**: -
- **Cosa vede l'utente**: -
- **Dove**: `service.py:3504-3530`, `db.py:99-113`; memorie di processo `service.py:345-386`.
- **Paper o live**: identico.

---

# PARTE I - DOSSIER.PY: IL DOSSIER DI UNA PARTITA

### 101. L'atlante dei gol
- **Cosa fa**: carica l'atlante condiviso (probabilita' di gol nei prossimi minuti), ricaricato se il file cambia; se manca scrive l'avviso una sola volta e torna niente (Mike allora copre subito).
- **Dove**: `dossier.py:22-39`.
- **Quando scatta**: avvio e ogni giro.
- **Numeri**: -
- **Cosa succede dopo**: -
- **Esempio**: -
- **Cosa vede l'utente**: hazard atlante sulla card.
- **Paper o live**: identico.

### 102. Il dossier pre-partita
- **Cosa fa**: raccoglie: fixture, lega, gol attesi casa e trasferta (lambda), rho (default -0,13), id squadre, P(esattamente 4 gol) pre-partita dalla griglia Dixon-Coles fino a 8 gol, P(Under 3.5) calibrata e la sua fonte ("calibrated" o "raw"), P(Over 4.5) calibrata (sempre vuota, vedi Cose strane), fonte ("fixture" o "none"). Lega e id squadra si prendono anche senza lambda.
- **Dove**: `dossier.py:42-111` (`_p_total`, `p4_from_lambdas`, `_id_int`, `build_prematch`).
- **Quando scatta**: all'armamento e al ritentativo (scheda 14).
- **Numeri**: `DEFAULT_RHO` = -0,13; `MAX_GOALS` = 8.
- **Cosa succede dopo**: ogni errore = chiavi vuote.
- **Esempio**: fixture trovata in `omega_events` con lambda 1,6 e 1,2: fonte "fixture", P(4) pre-partita calcolata dalla griglia (il valore dipende da `omega_model.residual_grid`, non ricalcolato qui); fixture non trovata: tutte le chiavi vuote, fonte "none".
- **Cosa vede l'utente**: fonte del modello, P(4) pre.
- **Paper o live**: identico.

### 103. La catena di ripiego dei gol attesi
- **Cosa fa**: gol attesi dalla fixture; se mancano, dalle quote 1X2 pre-partita congelate dallo scanner ("pre_ko_odds"); se mancano e si conoscono minuto e punteggio, dal mercato Over/Under in gioco ("live_ou"); altrimenti "none".
- **Dove**: `dossier.py:241-295`.
- **Quando scatta**: ogni giro in gioco (scheda 104).
- **Numeri**: -
- **Cosa succede dopo**: -
- **Esempio**: -
- **Cosa vede l'utente**: `lambda_source`.
- **Paper o live**: identico.

### 104. Il quadro del modello dal vivo
- **Cosa fa**: con minuto e punteggio: distribuzione empirica (solo se il punteggio e' ancora quello dell'intervallo), hazard dell'atlante v4 (con tempo, lega, id squadre), pressione (corner/cartellini, massimo fra le due squadre), gol attesi con ripiego, hazard di modello a 3 minuti, griglia del risultato: P(4), distribuzione dei gol, P(Over 4.5) ora e fra `cover_wait_step_min` minuti senza gol (minuto massimo 90), risparmio sulla copertura, probabilita' in tre scenari (ora / dopo / gol subito, pesato lambda casa sul totale), hazard finale prudente.
- **Dove**: `dossier.py:298-411`.
- **Quando scatta**: ogni giro con partita in gioco.
- **Numeri**: orizzonte 3 min; `cover_wait_step_min` = 5; `loss_exit_emp_min_n` = 200.
- **Cosa succede dopo**: ogni pezzo che fallisce resta vuoto.
- **Esempio**: -
- **Cosa vede l'utente**: hazard, P(4), probabilita' sulla card.
- **Paper o live**: identico.

### 105. L'hazard prudente
- **Cosa fa**: il piu' alto fra atlante e modello (quest'ultimo moltiplicato per la pressione, almeno x1, massimo 1).
- **Dove**: `dossier.py:114-123`.
- **Quando scatta**: scheda 104.
- **Numeri**: -
- **Cosa succede dopo**: entrambi mancanti -> niente (il motore copre subito).
- **Esempio**: atlante 0,05, modello 0,04 x pressione 1,2 = 0,048 -> 0,05.
- **Cosa vede l'utente**: hazard.
- **Paper o live**: identico.

### 106. Il risparmio atteso sulla copertura
- **Cosa fa**: stima di quanto si ridurrebbe l'importo di copertura aspettando N minuti senza gol, dalle probabilita' Over 4.5 ora e dopo.
- **Dove**: `dossier.py:126-133`.
- **Quando scatta**: scheda 104.
- **Numeri**: -
- **Cosa succede dopo**: -
- **Esempio**: P ora 0,10, dopo 0,08 -> risparmio 21,74%.
- **Cosa vede l'utente**: `cover_gain_pct`.
- **Paper o live**: identico.

### 107. La tabella empirica intervallo -> fine gara
- **Cosa fa**: per lega (o globale) carica la tabella una volta per processo; se vuota o in errore riprova dopo 10 minuti. Distribuzione finale dei gol dato il punteggio dell'intervallo: lega e globale fuse con peso n_lega/(n_lega+50); niente se i casi globali sono meno di `min_n`.
- **Dove**: `dossier.py:136-210` (`get_empirical`, `p_total_empirical` con `totals`).
- **Quando scatta**: in gioco, con punteggio dell'intervallo fissato.
- **Numeri**: `_EMPIRICAL_RETRY_S` = 600 s; shrink 50; `min_n` = `loss_exit_emp_min_n` = 200.
- **Cosa succede dopo**: -
- **Esempio**: n_lega 150 -> peso lega 0,75.
- **Cosa vede l'utente**: `p_total_emp`.
- **Paper o live**: identico.

### 108. Le distribuzioni dei gol dalla griglia
- **Cosa fa**: somma la griglia per totale gol (ultimo gruppo "8 o piu'"), probabilita' "al massimo N gol", e i tre numeri Under 3.5 / Over 4.5 / Under 4.5 nei tre scenari.
- **Dove**: `dossier.py:174-180`, `213-238` (`p_total_from_grid`, `_p_le`, `model_probs_from_grids` con `trio`).
- **Quando scatta**: scheda 104.
- **Numeri**: 8 gol.
- **Cosa succede dopo**: -
- **Esempio**: -
- **Cosa vede l'utente**: `model_probs`, `p_total_model`.
- **Paper o live**: identico.

---

# GLOSSARIO

**Stati della partita** (`mike_events.state`): `WATCH` osservata, nessuna posizione; `PRE_ENTRY_PENDING` ingresso Under in coda; `PRE_OPEN` Under abbinato pre-partita; `PRE_GREEN_PENDING` lay di chiusura in coda; `PRE_LAST_ENTRY_PENDING` ultimo ingresso (PERSIST) in coda; `HOLD` tenuta in perdita verso il fischio; `LIVE_UNCOVERED` in gioco con Under scoperto; `LIVE_KO_GREEN` uscita al fischio appoggiata; `LIVE_SECOND_ENTRY` seconda entrata dopo gol precoce; `LIVE_COVER_PENDING` copertura Over 4.5 in coda; `LIVE_COVERED` coperta; `LIVE_CLOSING` chiusura globale in corso; `FLAT` tutto chiuso; `REENTRY_PENDING` / `REENTRY_OPEN` / `REENTRY_GREEN_PENDING` re-ingresso Under 4.5; `IDLE_LIVE` in gioco senza posizione; `SETTLING` in regolamento; `SETTLED` regolata; `ERROR` in errore ("da sistemare"); `SKIPPED` saltata dall'utente. Terminali: SETTLED, ERROR, SKIPPED.

**Stato della gamba**: `pending` in coda/viva; `open` abbinata; `cancelled` ritirata/annullata; `settled` regolata; `pending_reconcile` esito ignoto, in riconciliazione; `archived` ciclo chiuso (contabilita' si', rischio no).

**Stato della riga di ordine** (`mike_trades.status`): `pending`, `open`, `hedged`, `won`, `lost`, `void`, `error`.

**Ruoli delle gambe**: `under_entry` ingresso Under 3.5; `under_last` ultimo ingresso; `under_second` seconda entrata; `over_cover` copertura Over 4.5; `reentry` re-ingresso Under 4.5; `under_green` lay di chiusura del ciclo pre-partita; `ko_green` lay d'uscita al fischio; `reentry_green` chiusura del re-ingresso; `under_close` / `over_close` chiusure globali.

**Stato del bot** (`mike_control.status`): `idle`, `running` (apre), `stopping` (si sta fermando), `stopped`, `error`. **Modalita'**: `paper` soldi finti (ordini sul runner simulato), `live` soldi veri.

**Stato delle richieste**: `pending`, `processing`, `done`, `rejected`, `error`.

**Attivita' della mia area**: `armed` partita presa in carico; `daily_stop` stop giornaliero; `config_warn` finestra scanner; `error` (motivi `cycle_exception`, `events_failed`, `event_cycle`, `settle_timeout`, `settle_rows_retry`, `settle_rows_failed`, `settle_rows_unreadable`, `settle_update_failed`, `settle_leg_senza_riga`, `duplicate_signal_key`, `stato_non_scritto`); `stop`; `cancel`, `cancel_richiesto`, `cancel_esito`; `fill_resting` abbinato durante l'annullo; `reconcile_fix` riparazione fatta; `reconcile_pending` riconciliazione in attesa; `settled`, `settle_fallback`, `settling_reverted`, `settle_commissione_mista`, `settle_gambe_non_piazzate`; `dossier_risolto`; `feed_line_missing` linea mancante; `flusso_interrotto`, `ripiego_rest`, `flusso_interrotto_senza_rest`, `flusso_non_dichiarato`; `no_fill` (motivo `feed_stantio`), `would_place` (prova a secco), `place_saltato`; `tetto_partite`; `state`; notizie del motore (`pre_cycle`, `cover`, `cover_wait`, `cashout`, `close_retries_exhausted`, `chiuso_dall_utente`, `loss_exit`, `loss_exit_deciso`, `uscita_proposta`, `uscita_proposta_decaduta`, `uscita_eseguita_su_approvazione`, `veto_under_calibrata`).

**Altri nomi**: feed unico = `safe_strategy_scan`; fotografia = `Snapshot`; `ctx` = memoria del motore per la partita; `extra` = dati di servizio nella scheda (`deferred`, `row_missing_since`, `settle_next_ts`, `settle_first_ts`, `last_goals`, `seen_inplay`, `ht_score`, `selections`, `reconcile_next_ts`, `log_seen`, `no_reentry`); lotto = riscritture di cortesia raggruppate; ripiego REST = lettura diretta del book Betfair quando il flusso e' fermo; runner = il simulatore/esecutore flumine che tiene gli ordini paper; `signal_key` = riferimento della gamba sulla riga; `closes_trade_id` = numero della riga che una chiusura chiude; hazard = probabilita' di un gol nei prossimi 3 minuti; lambda = gol attesi.

---

# DIFFERENZE DALLA COSTITUZIONE

1. **§3 (righe 95-96), "Il servizio gira ogni 1-2 secondi"**: il codice gira a 1,0 s con movimento e a `idle_cycle_s` = 5 s a riposo, svegliabile (`service.py:6051`, `6061-6062`, `6081`).
2. **§5 "Feed stantio: riga > 15 s E scanner muto > 30 s" e §6 `feed_max_age_s` = 15**: il codice ha `feed_max_age_s` = 45 s e `scanner_alive_max_s` = 75 s per decidere, `order_max_age_s` = 20 s e `order_scanner_max_s` = 30 s per ordinare, tetto 180 s, piu' il controllo del flusso prezzi (`config.py:95-116`, `feed.py:316-371`, `feed.py:428-431`).
3. **§17.3 `feed_cache_s` = 2 s** (e "15 s della soglia"): nel codice 4,0 s (`config.py:327`), 10 s con canale sano (`service.py:5887`).
4. **§6 costanti `_HEARTBEAT_MIN_S` = 10 s e `_STATS_MIN_S` = 5 s; §12 H5 "battito al massimo ogni 10 s"**: il codice usa i parametri `heartbeat_min_s` = 20 s e `stats_min_s` = 10 s (`config.py:377-378`, `service.py:3779-3785`). La stessa Costituzione §17.5 riporta 10/20: e' in contraddizione con se stessa.
5. **§2 e §3 Fase 7, regolamento "throttle 30 s" / "ogni 30 s"**: il codice usa `settle_confirm_s` = 60 s (30 s solo se il parametro e' 0) (`service.py:4084`, `config.py:305`).
6. **§12 H2 e §9/§10.A.2 "riconciliazione `mike_trades` <-> `positions` a OGNI ciclo"**: il codice la fa ogni `reconcile_every_s` = 30 s per partita (`service.py:4029-4032`).
7. **§2 tabella, "ponte evento->fixture (`live_follow`)"**: il codice cerca in `live_follow` e poi in `omega_events` (`db.py:548-557`).
8. **§2 "Atlante: JSON caricato una volta"**: il codice lo richiede a ogni giro e lo ricarica se il file cambia (`service.py:6056`, `dossier.py:25-39`).
9. **§5 "Ordine senza esito... In paper si risolve subito (nessun ordine e' mai partito)" e §10.B.2**: il codice, per una riga paper mandata al runner (`meta.canale_ref`), NON risolve: aspetta l'esito dal runner (`service.py:5021-5026`); un annullo paper sul runner senza numero scommessa porta la gamba in riconciliazione (`service.py:5113-5127`).
10. **§7 "In paper e in-play il fill e' DIFFERITO di `bet_delay`... Una LAY appoggiata si considera abbinata solo quando il best back SUPERA il suo prezzo"**: dal 29/09 (D1) gli ordini paper e le lay appoggiate paper stanno sul book del runner; la coda differita non viene piu' alimentata e l'abbinamento "simulato in casa" non esiste (`service.py:4378-4382`, `4508-4521`).
11. **§7, §12 H3, §10.C.2 "In LIVE la lay appoggiata non esiste: `pre_exit_mode` forzato a `taker`, `resting_live_unsupported`"**: nel codice la lay appoggiata live e' cablata (`_piazza_resting_live`, `service.py:4489-4497`); il dirottamento a taker avviene solo con `live_resting_enabled` spento (`service.py:1262-1264`); `ko_green` e' appoggiata sempre.
12. **§10.B.1 sottocaso "3.5 UNDER e 4.5 annullata -> la 4.5 regolata come UNDER"**: il codice gestisce il void per mercato prima del totale (`service.py:4109-4130`, commento 12/09): il rischio descritto non c'e' piu'. La Costituzione non e' aggiornata.
13. **§5 "Processo: stato riletto dal DB ad ogni ciclo"**: la riga di controllo si', le partite (`mike_events`) ogni `events_reload_s` = 60 s (`service.py:3505-3530`).
14. **§5 "Tetto partite: max 10 partite con POSIZIONE"**: nel codice il tetto e' separato per modalita' (`posti_occupati_per_modo`, `service.py:3841-3861`), e l'armamento delle candidate usa un conto diverso (stati non WATCH/IDLE_LIVE, `service.py:3580-3583`).
15. **§2 "Una SELECT per ciclo" sul feed**: una lettura ogni `feed_cache_s` (4 s) o 10 s con canale, con possibile fonte canale 47336 (`service.py:5858-5902`).
16. **§5 e §7, riconciliazione "per `customerOrderRef` `mike-t<id>`"**: il codice riconosce l'ordine per numero scommessa, `mike-t<id>` o riferimento storico a mercato concorde (`service.py:5028-5040`).
17. **§3 Fase 7 "Dopo 2 ore senza esito: ultimo punteggio del feed, altrimenti ERROR"**: il codice ha un terzo esito prima dell'ERROR: chiusura SETTLED se il risultato non dipende dal punteggio (`service.py:4137-4155`).
18. **§12 H1 e §5 "con feed stantio la richiesta [cash out] viene RIFIUTATA"**: con flusso interrotto il codice prova il ripiego REST e, se legge il book, chiude con i prezzi di Betfair (`service.py:3316-3341`).
19. **§6 variabili d'ambiente** (elenca `MIKE_LOCK_PORT`, `MIKE_USE_FLUMINE_QUEUE`, `SAFE_PRE_KO_OU_HOURS`): nella mia area il codice usa anche `MIKE_LIVE_ENABLED`, `MIKE_LOCAL_WS_PORT`, `MIKE_SVEGLIA_CANALE`, `MIKE_LEGGE_CANALE`, `MIKE_CANALE_POSIZIONI`, `SAFE_SCAN_WS_PORT`, `SCAN_FEED_HARD_MAX_AGE_SEC`. Inoltre `SAFE_PRE_KO_OU_HOURS` letta da Mike ha default 0 (`service.py:3953`).
20. **§16.4-bis blocchi 9-10, riferimenti di codice** (`service.py:571`, `:1696`, `:841`, `:851`, `:1566`): non corrispondono piu' alle righe attuali (es. `_reconcile_unknown` e' a 4977, il ramo "risultato indipendente" a 4143).
21. **§2 "Regolamento... 2 chiamate per partita"**: confermato; ma il ripiego REST col flusso fermo (scheda 36) aggiunge letture REST durante la partita, non citate in §2 ne' in §11 ("le sole chiamate REST sono il book a mercato chiuso e la riconciliazione").

---

# COSE STRANE

1. **Regolata senza aggiornare le righe**: nel ramo "punteggio non recuperabile ma risultato indipendente" la partita diventa `SETTLED` senza chiamare `_settle_trades` (`service.py:4143-4155`): le righe `mike_trades` di eventuali cicli chiusi restano `open`/`pending` per sempre (contano nelle righe aperte e nella liability delle righe), contro il principio scritto in `_retry_settle_rows` ("una partita non puo' diventare terminale con righe non aggiornate"). Lo stesso vale per il ramo `ERROR settle_timeout` (`service.py:4156-4161`, gia' dichiarato in §10.B.1).
2. **Feed illeggibile = feed vuoto**: `db.fetch_scan_rows` torna `[]` su errore (`db.py:513-515`), e il valore viene messo in cache come buono (`service.py:5891`). Se il database del feed non risponde per piu' di 10 minuti, OGNI partita risulta "assente da 10 minuti" e va in regolamento con letture REST (`service.py:4042-4047`). Per le righe `mike_trades` invece il codice distingue "non so" da "vuoto".
3. **Riga assente (<10 min) o dati incompleti: niente sorveglianza**: in questi casi il giro della partita esce presto (`service.py:4052-4055`, `4186-4207`): non girano il ritiro degli ordini in attesa da 120 s, la riconciliazione degli ignoti, la sorveglianza della sospensione, il seguito delle lay appoggiate. Gira solo la riparazione dello specchio (prima).
4. **Coda differita alimentata da nessuno**: nessun punto del codice aggiunge voci a `extra["deferred"]` (grep); il ciclo 4396-4419 lavora solo su dati vecchi. Dopo 30 s senza prezzo chiama comunque `execute_place` con prezzo assente (`service.py:4410-4417`).
5. **Orologio diverso nel freno di `loss_exit_deciso`**: usa l'ora del computer (`_time.time()`, `service.py:4570`) invece dell'ora del giro (`now_ts`): in un replay il freno di 5 minuti misura il tempo reale, non quello simulato.
6. **Messaggio di "Annulla ordini" impreciso**: conta come "annullati" anche gli ordini abbinati durante l'annullo (esito `open`) (`service.py:3268-3271`).
7. **Ritiro non mandato al mercato se la riga non e' `pending`**: `_mark_trade_cancelled` chiama Betfair/runner solo su righe `pending` (`service.py:5103-5105`). Se una gamba parzialmente abbinata avesse la riga gia' `open` con un residuo ancora vivo, il residuo non verrebbe annullato sul mercato (vedi "Non ho capito").
8. **Commenti superati**: `service.py:319-321` ("2 s di default, contro i 15 s di `feed_max_age_s`") contro 4 s e 45 s reali; docstring di `_reconcile_trades` "a OGNI ciclo" (`service.py:4878`) contro 30 s; docstring del modulo `service.py:11-13` ("In PAPER e in-play il fill viene DIFFERITO") superata; docstring di `_live_exit_override` (`service.py:1236-1241`) dice "in live si usa SEMPRE la chiusura taker", il codice sotto no; `dossier.py:3` e `:67` citano solo `live_follow` per il ponte.
9. **Due conti diversi per il tetto**: l'armamento delle candidate conta le partite in stato diverso da WATCH/IDLE_LIVE (`service.py:3580-3583`); il blocco delle aperture usa `ha_esposizione`, che conta anche WATCH con una gamba viva (`engine.py:1827-1850`). Il numero che frena l'armamento puo' essere piu' basso di quello che frena le aperture.
10. **Righe di chiusura mai marcate orfane**: una riga con `closes_trade_id` senza gamba non viene mai segnalata (`service.py:4947`), nemmeno in live.
11. **`settle_confirm_s` = 0 diventa 30 s, non 5 s** (`service.py:4084`), mentre il commento di config e la Costituzione parlano di "minimo effettivo 5 s" (vero solo per valori 1-4).
12. **Cumulativi paper+live mescolati nel ripiego degli aggregati**: `db.aggregates` filtra per modalita' le righe della giornata ma aggiunge `_cumulative_totals` calcolato su TUTTE le righe (`db.py:394`, `401-411`): `realized_total`, `won`, `lost` sommano paper e live quando la procedura SQL manca.
13. **`dossier.p_over45_cal` sempre vuoto**: la chiave esiste (`dossier.py:76`) ma nessuna riga la riempie.
14. **Codice non usato da Mike**: `db.get_event` e `db.delete_events` non sono chiamati da nessun file di produzione (grep sui file non di test).
15. **`stats.live_now`** conta anche partite terminali che avevano `inplay` salvato (`service.py:3713`).
16. **`_scrivi_evento`** dichiara "posizione aperta" se esiste una qualunque gamba, anche annullata (`service.py:5462`).
17. **`_settle_params`** rilegge le righe dal database senza la memoria del giro, fino a due volte per tentativo di regolamento (`service.py:5232`, chiamato a 4112/4143/4167).
18. **Riga sparita pre-partita per 10 minuti con posizione**: la partita va in regolamento (market aperto, totale assente) e resta `SETTLING` finche' la riga non torna; se non torna, dopo 2 ore senza essere mai stata vista in gioco finisce in SETTLED "indipendente" o ERROR (`service.py:4045`, `4131-4161`).
19. **Filtro competizioni per "contiene"**: "serie a" accetta anche "Serie A Women" o "Serie A2" (`feed.py:455-457`).
20. **Stato del mercato chiuso preso solo dalla linea 3.5** (poi dal mercato principale): se chiude solo la 4.5 la partita non entra in regolamento (`service.py:4040-4041`).

---

# NON HO CAPITO / NON HO LETTO

1. **Motore (`engine.py`)**: non ho letto `decide`, `apply_decision`, `settle_legs_by_market`, `_strip_openings`, `cashout_value`, `cashout_base`, `net_pnl_by_total`, `riepilogo_cicli`, `posizione_per_selezione`, `pnl_indipendente_dal_risultato` (solo la docstring), `registra_rifiuto`. Rimando al delegato dell'engine.
2. **Service righe 1-3250** (area B): `process_requests`, `execute_place`, `_segui_ordini_paper_su_runner`, `_sorveglia_sospensione`, `_sorveglia_mercato_copertura`, `_sorveglia_posizione_di_conto`, `_segui_resting_live`, `_piazza_resting_live`, `_piazza_resting_paper`, `_freno_resting_paper`, `_resting_in_attesa` (solo inizio), `_aggiorna_aperture_ferme`, `_approvazione_eseguita`, `_ordine_della_riga`, `_insert_trade_row`, `_trade_row`, `_ctx_from_row`, `_row_from_ctx`, `market_winner`: usati ma non letti per intero.
3. **Punto 7 delle Cose strane**: non so se una riga di ordine possa diventare `open` mentre la gamba ha ancora un residuo vivo sul mercato (dipende da come l'area B aggiorna la riga ai fill parziali). Se non succede mai, il punto e' innocuo.
4. **Moduli esterni non letti**: `safe_strategy/execution.reconcile_decision`, `annulla_su_betfair`, `aggiorna_trade`, `liability_of`, `is_reconciling`; `safe_strategy/canale_scan` (`CacheScan`, `ClientScan`, `fondi`, `acceso`); `stream/local_channel`; `stream/sveglia_canale.AscoltoScan`; `omega_market.attiva_saldo_su_evento`; `db_client.timeout_bot` (i valori 5 s / 20 s vengono dal commento, non verificati); `avvio_app.Guardia.timbra`; `omega_model` (griglie, `lambdas_from_pre_ko`, `lambdas_from_live_ou`, `score_probs`); `live_engine_pro.event_goal_hazard`; `atlante_v4.consulta_atlante_v4`; `safe_strategy/pressure.pressure_from_payload` (il tetto x1,25 della pressione e' solo nel commento).
5. **Procedure SQL** (`get_mike_aggregates`, `request_betfair_live_order`) e vincoli delle tabelle: non letti (divieto di interrogare il database; migrazioni non aperte).
6. **Cosa fa esattamente l'app con le statistiche e le schede spinte sul canale**: area UI.
7. `MIKE_USE_FLUMINE_QUEUE` e il percorso della coda flumine: citati nella Costituzione, non presenti nella mia area; le funzioni di coda in `db.py` (scheda 99) sono chiamate dal codice di esecuzione condiviso, non verificato quando.
