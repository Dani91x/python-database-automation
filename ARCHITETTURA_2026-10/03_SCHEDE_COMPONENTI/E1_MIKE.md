# SCHEDA DI COMPONENTE E1 - Bot Mike (calcio: Under 3.5 pre-KO + copertura Over 4.5 + re-ingresso)

Data: 08/10/2026. Autore: delegato Sonnet 5.5. Prefisso funzionalita': `E1-`. Commit di riferimento del codice letto: `e5f4c1e3`.
Solo documento: nessun codice, test, migrazione o replay toccato/eseguito. Strumenti di misura usa-e-getta (statici, ASCII-only, rieseguibili,
non importano codice di produzione) in `ARCHITETTURA_2026-10/strumenti/e1/`: `e1_impronta_strategia.py` (+ `.tsv`), `e1_parametri_py_vs_ts.py`
(+ `_uscita.txt`), `e1_service_per_gruppo.py` (+ `_uscita.txt`), `e1_tabella_parametri.py` (+ `.md`).

**Perimetro (righe da `wc -l`, tutte uguali a `00_INVENTARIO.md` e a `D_RUNTIME_BOT_CONTRATTO.md`)**

| Parte | File | Righe |
|---|---|---:|
| Codice Python di Mike | `Betfair/mike/service.py` 7.551, `engine.py` 5.359, `certificazione.py` 2.084, `db.py` 693, `feed.py` 583, `config.py` 491, `dossier.py` 411, `regolato_conto.py` 359, `porta_ordini.py` 224 | **17.755** |
| Strumenti del banco specifici di Mike | `Betfair/mike/tools/replay_registrazioni.py` 2.370, `synth_mike.py` 779, `banco.py` 48 | **3.197** |
| Test Python di Mike | `Betfair/mike/tests/` 99 file, 1.358 funzioni `test` (`grep -c "def test"`) | 28.605 |
| Frontend specifico (non test) | `frontend/src/lib/mike.ts` 2.454, `pages/Mike.tsx` 799, `components/mike/MikeMatchCard.tsx` 1.174, `useMike.ts` 393, `MikeCashOutButton.tsx` 245, `MikeEventPnlTable.tsx` 139, `MikeParamsSheet.tsx` 82, `useMikeEventoAlMs.ts` 70, `useMikeClock.ts` 45 | **5.401** (+ `anteprima/mikeFinto.ts` 321) |
| Frontend condiviso che nomina Mike | 92 file non-test con "mike" (1.470 righe in tutto): `useControlRoom.ts` (155 righe), `lib/mike.ts`, `ControlRoom.tsx` (50), `interruttori.ts` (28), `cashOutPartita.ts` (27), `controlRoom.ts` (26), `dailyHistory.ts` (24), `CashOutGlobale.tsx` (24), `provaGiornata.ts` (21), `composizioneObiettivo.ts` (20), `chiudiRiga.ts` (17), `PropostaUscitaMike.tsx`, `EsitoChiusuraMike.tsx`, `InterruttoreUscite.tsx` ... | non contate come E1 |
| Banco comune che ospita Mike | `registro_bot.py:219-243` (voce `mike`), `certifica.py`, `banco_comune.py` (tabelle in RAM con le firme di `mike/db.py`: 249, 346, 376), `porta_banco.py`, `minimi_banco.py` | scheda H |
| SQL | 11 file in `migrations/` con "mike" nel nome (`mike_bot.sql:224` `mike_update_params`, `:304` `mike_request`, `uscite_automatiche_mike_2026-09-25.sql:42`, ...) | - |

Fonti gia' pronte e citate (non rifatte): `D_RUNTIME_BOT_CONTRATTO.md` (scheletro, contratto `Plugin/Decisore`, righe di `service.py` per ruolo),
`C_PORTA_ORDINI.md` (Mike live = REST diretto `omega_market.py:704`), `G_DATI_E_ALGORITMI_DEL_CLOUD.md` (G-019..G-025, G-033, G-034, G-040),
`00_INVENTARIO.md`, `07_MISURE_OGGI.md` (§4.1-4.2), `PROCESSO_STANDARD_BOT.md` §6 e §7, `Betfair/mike/COSTITUZIONE_MIKE.md` (2.177 righe, specifica).

---------------------------------------------------------------------------------------------------------------------------------

## 1. OGGI

### 1.1 Come e' fatto (letto dal codice)

- **Un processo, un ciclo a giro** (`service.py:7416` `main`, `_ciclo_persistente` 7289, `_un_giro` 7471). Ogni giro: `D.load_atlas()` (7492), `run_once` (3998, 374
  righe: richieste utente, riconciliazione, apertura partite, per partita `_run_event` 4739-5516, 778 righe, regolamento, stats, battito).
  La decisione e' UNA chiamata a una funzione **pura**: `E.decide(ctx, snap, params) -> Decision` (`engine.py:3089`; chiamata in `service.py:5007` per il
  regolamento e `:5264` per la partita). Il resto del servizio e' tutto IO: feed, DB, ordini, riconciliazione, regolamento, UI.
- **Stato per partita** = una riga `mike_events` con `ctx` JSON + `positions` (gambe) + `dossier` + `live`; `mike_trades` una riga per gamba; RAM `_CACHE_EVENTI`
  (`service.py:426`); scrittura solo se la firma cambia (`_persist` 6706, `_signature`, lotto `_svuota_lotto` 6751).
- **Dati**: righe del feed unico `safe_strategy_scan` (payload con blocchi `ou`) dal canale locale 47336 se acceso (`avvia_client_scan`, `_righe_del_feed` 7167)
  altrimenti da DB (`mike/db.py:553` `fetch_scan_rows`); `feed.snapshot_from_row` (`feed.py:493`) costruisce `engine.Snapshot`; REST di ripiego
  (`_books_ripiego_rest`, `_RealMarket`); dossier pre-partita dal cloud una volta per evento (`dossier.py:66`, G-033) e tabella empirica HT->FT (`dossier.py:141`, G-034).
- **Ordini**: paper = canale locale del runner (`porta_ordini.py` `VistaMike` 115 / `PortaCanaleMike` 161; `_segui_ordini_paper_su_runner` `service.py:1694`);
  **live = REST diretto sempre** (`execute_place` `service.py:739`, `_piazza_resting_live` 2190, `omega_market.place_order_live` `:704`; C card S3). Riserva di riga PRIMA
  dell'invio (C card), kill-switch `MIKE_LIVE_ENABLED` (`service.py:103-128`), kill-switch condiviso solo sulle aperture REST (C-026).
- **Comandi dall'app**: tabella `mike_requests` (`mike/db.py:462-552`), sei tipi `cashout | flatten | skip_event | resume_event | cancel | approva_uscita`
  (`frontend/src/lib/mike.ts:18-20`), smistati da `process_requests` (`service.py:3636`) con gestori `_request_approva_uscita` 3775, `_request_cancel` 3820,
  `_request_flatten` 3850; stale 10 min (D-034).
- **Controllo**: riga singleton `mike_control` (id=1) con `status`, `mode` (paper|live), `params`, `stats`, battito (`mike/db.py:59-70`).
- **Processi / canali**: processo `mike-service`; porta lock 47319 (`config.py:32`); canale locale di Mike 47333 (D card §1.1); sveglia dal canale (`service.py:6864-7039`).

### 1.2 Tabelle del DB (con frequenze misurate)

Fonte delle frequenze: `ARCHITETTURA_2026-10/strumenti/misure/uscite/m04_chiamate_db.txt` (righe 5-9 = 08/10, 86-92 = 04/10, 168-173 = 02/10; assegnazione delle sessioni dedotta dai valori di `mike_trades` 99,1 / 107,8 / 10,4 e dai totali di `07` §4.2) e `07_MISURE_OGGI.md` §4.2.

| Tabella / RPC | Chi la tocca in `mike/db.py` | 02/10 (stream attivo) | 04/10 (stream attivo) | 08/10 (nessun evento) |
|---|---|---:|---:|---:|
| `mike_control` GET | `read_control` 59 | 54,9/min | 48,8/min | 10,4/min |
| `mike_control` PATCH | `set_control` 64 (battito + stats) | 3,0/min | 3,0/min | 2,7/min |
| `mike_requests` GET | `requests_da_lavorare` 467 | 54,9/min | 48,8/min | 10,4/min |
| `mike_trades` GET | `open_trades` 196, `trades_for_event` 210, `live_trades` 252 | 99,1/min | **107,8/min** | 10,4/min |
| `safe_strategy_scan` GET | `fetch_scan_rows` 553 | n.d. | 13,5/min (cache `feed_cache_s` 4 s) | 10,4/min |
| `rpc/get_mike_aggregates` | `aggregates` 393 | n.d. | n.d. | 2,6/min |
| `mike_events` POST/GET | `upsert_events` 144, `list_events` 99 | n.d. | POST 25/min (G, T09) | ~0 |
| `mike_activity` POST | `log` 71 | n.d. | n.d. | n.d. (14.931 righe / 7 MB, `07_MISURE_OGGI.md` riga 352) |
| `betfair_live_order_requests` / `betfair_live_orders` | `enqueue_live_order` 662, `get_live_order_mirror` 690 | n.d. | n.d. | n.d. |
| **Servizio mike, totale** | | **251,9/min** | **256,1/min** | **48,0/min (p95 54)** |

Altre tabelle lette in sola lettura dal cloud (G): `fixture_predictions` (`mike/db.py:609,625`), RPC `get_omega_ht_ft` (637), `live_follow` (650).
Il conto delle `.execute()` nude in `mike/db.py` e' 34 (nessuna eccezione tipizzata: G, 00 §3).

### 1.3 PERCHE' le richieste al DB di Mike sono scese da ~255 a ~48 al minuto (04/10 -> 06/10)

`07_MISURE_OGGI.md:226-227` scrive «non ho verificato nel codice quale cambiamento l'ha prodotto». Verificato qui. **Non c'e' stato nessun cambiamento di codice che l'abbia
prodotto: e' la stessa cadenza adattiva, osservata in due stati del mondo diversi.**

1. **Il codice di Mike non e' cambiato fra le due misure.** `git log --since=2026-10-02 --until=2026-10-08 -- Betfair/mike/{service,db,feed,config}.py` da tre commit:
   `f34a2816` (02/10 16:05), `16776a22` (04/10 18:19, ordini veri) e `8f538e78` (04/10 19:06, regola della banca della copertura). Nessun commit nei file di servizio, DB, feed e
   config fra il 04/10 19:06 e l'08/10. Nei tre commit ho contato **0 righe di diff** (`git diff <c>~1 <c> -- service.py db.py config.py | grep -c 'fretta|idle_cycle|interval|trades_for_event|open_trades|read_control|requests_da_lavorare|fetch_scan_rows'` = 0 per tutti e tre): nessuno tocca cadenza o letture per giro. La logica `c_e_fretta` e' del 13/09 (`git log -S c_e_fretta` = `506fe7cb`).
2. **Meccanismo (letto riga per riga).** L'attesa fra due giri e' `interval = max(1.0, decide_min_interval_ms/1000*2)` = **1,0 s** (`service.py:7487-7488`, default 500 ms
   `config.py:87`) e viene alzata a `idle_cycle_s` = **5,0 s** (`config.py:350`) SOLO quando `not res.get("fretta")` e il giro non ha prodotto azioni ne' regolamenti
   (`service.py:7497-7498`). `fretta` e' vera se c'e' una richiesta della UI oppure se esiste una partita non terminale in gioco o con una gamba `pending`/`pending_reconcile`
   (`service.py:4259-4264`, commento 4255-4258: «girare ogni secondo vuol dire solo consumare il budget di IO»). La cadenza adattiva e' stata introdotta il 13/09 (`git log -S idle_cycle_s`:
   `506fe7cb perf(mike): il software deve lasciar respirare il database`).
3. **I numeri tornano.** Ogni giro fa UNA lettura di `mike_control`, UNA di `mike_requests`, UNA di `mike_trades` (la riconciliazione `open_trades` `service.py:5581`) e, a riposo, una del feed (in fretta il feed e' in cache `feed_cache_s` = 4 s: 13,5/min il 04/10).
   08/10: 10,4 richieste/min per ciascuna delle 4 tabelle = un giro ogni 5,8 s = 5,0 s di riposo + ~0,8 s di lavoro (il lavoro non e' misurato). 04/10: `mike_control` 48,8/min =
   un giro ogni 1,23 s = 1,0 s + ~0,23 s di lavoro (02/10: 54,9/min = 1,09 s). Il rapporto fra le frequenze di giro e' 5,8/1,23 = **4,7**, quello dei totali del servizio 256,1/48,0 = **5,3**; il resto e' `mike_trades` a
   107,8/min contro 10,4 (10,4x, non 4,7x): in fretta si leggono anche le righe per partita (`trades_for_event` `service.py:5529, 6041, 6100, 6422`), ~2,2 letture di trade a giro.
4. **Le sessioni misurate sono di due tipi.** `07` §4.1: 02/10 14:25 e 04/10 14:18 sono sessioni «stream attivo» (partite in gioco); 06/10 15:38 ha p50 = 0 richieste/min e 08/10
   06:03 e' «quasi sempre nessun evento». Quindi 255 = Mike con partite in gioco (fretta), 48 = Mike a riposo (nessun evento in gioco).
5. **Conseguenza (previsione falsificabile)**: nel prossimo giorno con partite in gioco Mike tornera' a ~250/min. Strumento: `strumenti/misure/m04_chiamate_db.py` sulla sessione. Quello che
   resta a 48/min a riposo e' il PAVIMENTO del polling: 4 letture per giro x 12 giri/min, tutte «a vuoto» (nessuna partita, nessuna richiesta). E' il bersaglio della migrazione (§7).
6. **Non verificato**: la causa esatta dello 0,8 s di lavoro per giro e l'assenza di eventi il 06-08/10 (non ho interrogato `mike_events` ne' i log del servizio: sola lettura, e il log e' da 3 GB).

### 1.4 Dipendenze

- **In entrata** su `Betfair/mike/*`: `registro_bot.py:219-243` (impronta dei 9 moduli), `avvio_app.py:173-215` (conosce Mike per NOME: `uscite_automatiche -> False`), `certifica.py`/`banco_comune.py`
  (firme di `mike/db.py`), `frontend/src/lib/mike.ts` (via RPC e realtime `mike-live`), `safe_strategy/db.py:307` (legge `mike_events`).
- **In uscita (dal motore, quindi vincolanti per qualunque spostamento)**: `engine.py:25-37` importa `Betfair.stream.live_order_build` (`round_to_tick`, `ticks_away`),
  `Betfair.stream.trading.minimi_it` (minimi .it, fonte unica), **`Betfair.stream.scalper.scalper_bot.ticks_between`** (la strategia di Mike dipende da un modulo dello scalper: accoppiamento da
  cambiare SOLO spostando la funzione identica) e `Betfair.stream.trading.greenup` (`GreenupPlan`, `compute_greenup`). `feed.py:18-19` usa `stream.flusso_prezzi` e `trading.xhedge`.
  Il servizio importa `safe_strategy`, `omega` (omega_market per gli ordini veri, `omega_db`/ht_ft) e `stream/trading` (D inventario 00: Mike -> safe_strategy 10 import, -> omega 7, -> stream/trading 9).
- **Rete nel percorso critico**: il ciclo legge DB/canale prima di decidere; REST `listCurrentOrders` e `get_market_book` solo in ripiego/riconciliazione/regolamento; `place_order_live` REST
  per ogni ordine live (bet delay 5 s in gioco).

---------------------------------------------------------------------------------------------------------------------------------

## 2. FUNZIONALITA' (E1-001 ...)

Legenda: **[S]** strategia, intoccabile; **[G]** guscio, riducibile; **[UI]** visibile nella UI (file); **[P]** parametro editabile (chiave in 2.3). Le righe `file:riga` sono quelle lette; dove
scrivo «(da indice)» ho letto solo l'intestazione e la docstring della funzione, non il corpo: sono i punti da rileggere prima di una tappa di codice.

### 2.1 LOGICA DI STRATEGIA - [S] - inventario che garantisce che non cambi

**Garanzia meccanica.** `strumenti/e1/e1_impronta_strategia.py scrivi` ha scritto `e1_impronta_strategia.tsv`: **386 impronte** (SHA-1 dell'AST senza docstring, commenti e numeri di riga) =
228 elementi di primo livello di `engine.py` + 29 di `feed.py` + 21 di `dossier.py` + `PARAM_SPEC` e le sue 107 chiavi di `config.py` (una impronta per chiave: default, tipo, limiti, scelte).
Il comando `... confronta` rilancia il calcolo e deve dire «differenze: 0». Verificato oggi: 0 differenze (sullo stato `e5f4c1e3`). Uno spostamento di una funzione in un altro file
cambia il file ma non l'impronta: il confronto e' per NOME e per contenuto, quindi ammette lo spostamento e rifiuta qualunque modifica di una soglia, di una condizione, di un ramo.

**Macchina a stati**
- E1-001 [S] 21 stati e 11 ruoli (aperture 5, chiusure 6): `STATES` `engine.py:43-49`, `TERMINAL_STATES` 50 (SETTLED/ERROR/SKIPPED), `ROLES` 52-65 (`under_entry|under_last|under_second|over_cover|reentry` aperture 56, chiusure 58), `EXIT_KINDS` 71. Smistamento `_dispatch` 3417-3480 (uno `if` per stato; stato sconosciuto -> `ERROR` 3480).
- E1-002 [S] Entrata unica `decide` 3089-3144: terminale -> nessuna azione (3091); posizione chiusa dall'utente fuori app -> nessuna azione (3101); `flatten_pending` -> solo `_decide_flatten` (3105); `no_reentry` (dopo un cash out manuale) spegne `pre_enabled`, `reentry_enabled`, `last_entry_persist` (3109-3111); ordine a esito ignoto -> via le APERTURE, restano le riduzioni di rischio (3114-3116, `_strip_openings` 2442); aperture ferme per causa esterna (3117-3122); poi i filtri in catena: `_freno_copertura` 3133 (def 2619), `_una_sola_lay` 3134 (2493), `_mai_sovracopertura` 3137 (2568), `gate_uscite` 3141 (3304), `_ultime_guardie` 3144 (3079).

**Scelta della partita e ingresso pre-match**
- E1-003 [S][P] Partita da armare: `is_candidate` `feed.py:566-583`: entrambe le linee nel feed e `info.complete`; KO nel futuro e entro `entry_hours_before_ko` ore; `competition_filter` (sottostringhe, case-insensitive); **mai una partita gia' in corso** (L4: Mike non entra mai in-play da zero).
- E1-004 [S][P] Guardie d'ingresso `_entry_guard` 3484-3527, in quest'ordine: rientro disabilitato (3486), chiusura manuale in corso (3489), `pre_enabled` (3491), dato fresco `snap.order_fresh` (3493-3500), fuori finestra `now < ko - entry_hours_before_ko*3600` (3501-3503), finestra chiusa `now >= ko - pre_last_entry_min*60` (3504), `cycle_no >= pre_max_cycles` (3506), cooldown `pre_reentry_cooldown_s` dall'ultimo green (3508), book assente/non operabile/in-play (3510-3512), quota fuori `[pre_entry_price_min, pre_entry_price_max]` (3513-3514), liquidita' `back_size < stake*pre_min_back_size_factor` (3515-3517), spread > `pre_max_spread_ticks` (3521-3524), tetto `stake > liability_room` (3525-3526; `liability_room` 2268 = `max_liability_per_match - investito`, 0 = nessun tetto).
- E1-005 [S][P] Freschezza del dato, due soglie: per GUARDARE `feed_max_age_s` / `scanner_alive_max_s` (`feed.feed_fresh` 435), per ORDINARE `order_max_age_s` / `order_scanner_max_s` / `book_seen_max_s` (`feed.order_fresh` 458-492; `Snapshot.order_fresh` `engine.py:180-233`). Il commento di `config.py:88-117` documenta la misura (13/09) che ha fissato 45/75/90/20/30 s.
- E1-006 [S][P] Ingresso: BACK Under 3.5 di `stake` EUR al miglior back (`_decide_prematch` 3617-3701, ruolo `under_entry`, ingresso ciclo N), importo a multiplo di 0,50 per difetto da 1 EUR in su (`punta_a_multiplo` 1861; regola dell'utente 04/10), importo libero al centesimo con `exact_sizes` (place-and-trim) o legalizzato (`legalize_back_size` 513, `needs_submin` 556), `_place` 1876.
- E1-007 [S][P] TTL dell'ingresso non abbinato: oltre `pre_entry_ttl_s` l'ordine si ritira (`3694-3698`); ingresso parziale -> `PRE_OPEN` con il matched.
- E1-008 [S][P] Uscita pre-match **appoggiata** (`pre_exit_mode=resting`, default): subito dopo il fill dell'ingresso una LAY a `pre_green_ticks` tick sotto l'ingresso (`_after_entry_fill` 3809-3822, `green_target` 435, `3737-3751`); modalita' `taker`: chiude al best quando i tick ci sono (3753-3767). `live_resting_enabled` (config.py:137) = valvola per tornare all'uscita a mercato in live, dichiarata in pagina.
- E1-009 [S][P] Green non abbinata / parziale / ritiro e rimessa: `close_retry_s`, `close_max_attempts` (3772-3798). In perdita prima del KO: si tiene fino al live (3801).
- E1-010 [S][P] Ciclo chiuso: `_cycle_done` 3825-3846 (P&L bloccato, `cycle_no+1`, `last_green_at`), `cycle_label` 566, `riepilogo_cicli` 1726, `pnl_cicli_chiusi` 1707.
- E1-011 [S][P] **Ultimo ingresso (PERSIST)** a `pre_last_entry_min` minuti dal KO: solo se Mike e' piatto, tutte le condizioni d'ingresso vere, riprova fino al fischio (`_ultimo_ingresso` 3907-3954, `_after_final_green` 3848-3895, innesco 3677-3678); `last_entry_persist` lo spegne (3851); tetto di liability (3873-3875); `last_entry_ticks_above` sposta il prezzo di N tick (3877-3879: letto qui, mentre l'etichetta UI lo dichiara «NON ATTIVO», `mike.ts` campo `last_entry_ticks_above`: **da verificare**, §3 D8).
- E1-012 [S][P] **Veto M1 sulla P calibrata dell'Under 3.5** (acceso di serie dal 25/09): `valuta_veto_under35` 3590-3614, `soglia_veto_under35` 3569-3587 (interpolazione lineare fra i nodi 1,30/1,50/2,00/2,50/3,00 = 0,807/0,684/0,514/0,385/0,275, `VETO_U35_NODI` 3549-3555), `veto_u35_acceso` 3559. Esiti `veto | nessun_veto | non_valutabile` (P o quota assenti = nessun veto). Dopo un veto non si rientra (3853-3856, 3941-3943). Una posizione che il veto chiude e' un'uscita IN PERDITA (`VETO_U35_NOTE` 3556, 3224).
- E1-013 [S][P] Non abbinati dopo il fischio: `cancel_unmatched_after_ko_s` (3631, `_late_persist_cancel` 4774).
- E1-014 [S] Passaggio al live (`_decide_prematch` 3650-3671): banca abbinata -> `IDLE_LIVE` o `LIVE_KO_GREEN` (`ko_green_enabled`, 3665-3667) o `LIVE_UNCOVERED` (3670); nessuna posizione -> `IDLE_LIVE` (3671).

**Dal fischio: uscita a +N tick, gol precoce, seconda entrata**
- E1-015 [S][P] Uscita al fischio `ko_green`: `_decide_ko_green` 4050-4245, piano `piano_uscita_ko` 4030-4043 (`ko_green_ticks` sotto l'ingresso), finestra `finestra_uscita_scaduta` 4009-4027 (`ko_green_window_s` dal fischio), lay APPOGGIATA in ogni modalita' (`ko_green_retry_s` non e' letto da nessun ramo: parametro morto, §3 D7). Banca parziale, attesa dell'annullo, ripresentazione: 4157-4245.
- E1-016 [S] Gol dopo il fischio: `gol_dopo_il_fischio` 3980, `momento_del_gol` 3991. Dentro la finestra e ancora scoperti -> `LIVE_SECOND_ENTRY` se `second_entry_enabled` e non gia' fatta (4116-4121), altrimenti copertura (4121); finestra scaduta senza uscita -> copertura piena (4127-4139).
- E1-017 [S][P] Seconda entrata sull'Under 3.5 al miglior prezzo, `second_entry_stake_pct` % dello stake (4297-4298), con cap liability (4302), tentativi `close_max_attempts` (4290), `LIVE_UNCOVERED` se non piazzabile (4288) (`_decide_second_entry` 4249-4314).

**Copertura Over 4.5 / banca Under 4.5**
- E1-018 [S][P] Quando coprire: `cover_timing` 1558-1599 -> `cover | wait | skip`: punteggio assente = aspetta (1572); `g > cover_max_goals` = salta (1574); `cover_policy` immediate/wait/auto (1576-1588); dopo un gol attesa `cover_postgoal_delay_s` (1580); a 0 gol si aspetta SOLO se minuto < `cover_wait_max_min`, hazard 3' <= `cover_wait_hazard_max`, P(4) mercato <= `cover_wait_p4_max`, quota Over < `cover_good_price`, risparmio atteso >= `cover_wait_min_gain_pct` (1583-1599; ogni dato mancante = si copre); passo `cover_wait_step_min`.
- E1-019 [S][P] Quanto coprire: `cover_residual` 452 / `cover_residual_lay` 464 / `cover_size` 445 / `cover_size_residual` 483 (`cover_profit_factor` x perdita Under, commissione, meno il gia' coperto), forma `cover_form` 477 (`lay_under45` banca, default dal 29/09; `back_over45` punta), arrotondamento `cover_rounding`/`cover_legal_size` 531, tetto di sovra-copertura `cover_max_overshoot_pct` (4573), due tranche (`frazione_copertura` 4329-4356: `early_goal_cover_pct`; seconda dopo `early_goal_cover2_delay_s` dall'abbinamento della prima, 5033).
- E1-020 [S][P] A che prezzo: `cover_place_price` 2230 (N tick SOTTO il best back), `cover_place_price_lay` 2250 (N tick SOPRA il best lay), `cover_place_at_ticks` (default 2). Fuori prezzo: `_punta_over45_fuori_prezzo` 2116, `banca_under45_equivalente` 2104, `COVER_FUORI_PREZZO` 2100. Regola 04/10 (commit `8f538e78`): la copertura parte solo se la banca U4.5 e' minore della banca U3.5 (`COVER_BLOCCATA` 2096).
- E1-021 [S] `_decide_uncovered` 4468-4615 (copertura a punta), `_copertura_banca` 4625-4761 (copertura a banca), `_decide_cover_pending` 4784-4874 (fill, ridimensionamento, rimessa a prezzo con `close_retry_s`/`close_max_attempts`), `_riprezzo_copertura_banca` 4877-4934. Rami di rinuncia: troppi gol (4540, 4673), nessuna liability (4543, 4676), copertura gia' sufficiente (4567, 4700), cap liability (4596, 4740, 4747), liquidita' (4603), size non piazzabile (4606).
- E1-022 [S][P] **Freno sui rifiuti ripetuti**: `_freno_copertura` 2619-2672 (ordine dell'utente 17/09): dopo `cover_rifiuti_max` rifiuti con lo STESSO codice d'errore la copertura si ferma (fail-closed) finche' l'utente non preme «Riprendi» (`sblocca_copertura` 2196) o arriva un codice diverso; fra due tentativi almeno `cover_retry_min_s` (`attesa_ritento_copertura` 2181, `copertura_bloccata` 2161, `registra_rifiuto_copertura` 2138). Altri freni: `tentativo_gia_rifiutato` 1923, feed stantio 1986-2020, `chiusura_gia_rifiutata` 2037.
- E1-023 [S] **MAI due lay vive o in volo** sullo stesso mercato/selezione (`_una_sola_lay` 2493-2545; ordine dell'utente 16/09 h16:15) e **MAI sovracopertura** (`_mai_sovracopertura` 2568-2618; `copertura_in_volo` 2546, `lay_in_volo` 2470): il riprezzo e' in DUE giri (annullo confermato, poi ordine nuovo).
- E1-024 [S] Chiusura in profitto se la copertura non e' eseguibile: Under 3.5 in profitto di almeno `CHIUSURA_PROFITTO_TICK_MIN` = 2 tick (4370) chiude l'Under senza coprirsi (`_chiusura_in_profitto_se_non_copribile` 4387-4435, `_segui_chiusura_in_profitto` 4437-4461, `COPERTURA_NON_ESEGUIBILE` 4374; commit `22e86381`).

**Uscite dalla posizione coperta**
- E1-025 [S][P] Cash out a soglia: `should_cashout` 1345 (netto >= `cashout_profit_pct` % della base), base `cashout_base` total|under (`cashout_base` 2219), valore `cashout_value` 1045-1126 (a `cashout_place_at_ticks`), azioni di chiusura `_close_actions` 2339.
- E1-026 [S][P] Cash out intelligente `smart_cashout` 1416-1478: mai sotto `cashout_smart_min_pct`; punteggio caldo (>= `cashout_smart_goals_hot` gol); vicino alla soglia (`cashout_smart_tolerance_pct`) e fase calda (hazard >= `cashout_smart_hazard_hot` o pressione >= `cashout_smart_pressure_hot`); valore atteso dell'attesa (`projected_books` 1378, margine `cashout_smart_ev_margin_pct`).
- E1-027 [S][P] Uscita in perdita tollerata: `_loss_rule` 4939-4945 (HT: `ht_loss_exit_enabled`, `ht_loss_pct`; 2T: `h2_loss_exit_enabled`, `h2_loss_pct`, dal minuto `h2_loss_from_min` al `h2_loss_to_min`), gol fra `ht_loss_goals_min` e `ht_loss_goals_max` (4982-4983); modalita' `model` (`loss_exit_model` 1517-1555: chiude se il valore certo >= EV(tenere) - premio `loss_exit_risk_premium_pct` x P(4) x base; P(4) prudente `loss_exit_p4_prudent`; tetto `loss_exit_max_pct`; dati empirici `loss_exit_emp_min_n`) o `fixed` (`loss_exit_ok` 1351). Decisione in `_decide_covered` 4949-5041.
- E1-028 [S][P] Chiusura in corso: `_decide_closing` 5044-5132 (`close_retry_s`, `close_max_attempts`, riprezzo 5099-5131, attesa del ritento `attesa_ritento_chiusura` 2061), residuo non chiudibile `residuo_non_chiudibile` 5135 / `_decide_flat` 5158-5164 (si porta al regolamento).
- E1-029 [S][P] **Interruttore delle uscite** (`uscite_automatiche`, di serie FALSE dal 25/09 sera): `gate_uscite` 3304-3413; le uscite DISCREZIONALI (`USCITE_DISCREZIONALI` 3153: green pre-match, uscita al fischio, cash out/uscita in perdita, green del re-ingresso) diventano una PROPOSTA nella scheda (`uscita_proposta`, 3375-3391) che l'utente approva (`approva_uscita`, TTL `APPROVAZIONE_TTL_S` 120 s, 3168, 3251). Passano SEMPRE: la copertura, le protezioni (`MOTIVI_PROTEZIONE` = `loss_cap`, 3157), l'uscita gia' in corso (3227), l'uscita IN PROFITTO (3341-3344; dal 29/09), il regolamento, annulli e riconciliazione. `uscita_in_perdita` 3197-3224 decide cosa e' «in perdita» (`close_reason` `loss*`, `reentry_time` con P&L bloccato < 0, veto M1). Firma valida solo per la stessa uscita (`_stessa_uscita_firmata` 3261).
- E1-030 [S][P] Re-ingresso Under (gol + 3.5): `_decide_flat` 5167-5187 (`reentry_enabled`, una volta per partita, 1..`reentry_max_goals` gol, entro `reentry_until_min`, mercato U4.5 aperto, quota U4.5 > ingresso iniziale se `reentry_price_min_over_entry`, liquidita' `stake*pre_min_back_size_factor`, cap), `_decide_reentry_pending` 5192, `_decide_reentry_open` 5224-5275 (green a `reentry_green_ticks`; chiusura a mercato dopo `reentry_exit_until_min`, 0 = mai; `reentry_hold_if_loss`), `_decide_reentry_green_pending` 5278.
- E1-031 [S][P] Chiusura manuale / cash out manuale / flatten: `_decide_flatten` 2673-2814, `MANUAL_ROLE_MAP` 2374, `force_flat_plan` 2379, `force_flat_actions` 2396. Residuo scoperto dichiarato con le alternative: `_ordini_che_chiudono` 2831, `_proposta_residuo` 2886, `_dichiara_residuo` 3012, `CATEGORIA_RESIDUO` 2815 (da indice). Ultime guardie (da indice): `_guardia_minimo_listino` 2927, `_controllo_di_piatto` 2982, `_proposta_residuo_finale` 3054, `_ultime_guardie` 3079.
- E1-032 [S] Mercato chiuso -> `SETTLING` con annullo dei vivi (3422-3424), ordine ignoto = regolamento sospeso (3430-3434), attesa punteggio finale (3435), poi `settle_legs` 1608-1706 -> `SETTLED` col P&L (3437-3442). Verita' di mercato: `stato_mercato` 603 (aperto/sospeso/chiuso/ignoto), `operabile` 619, `appoggiabile_in_gioco` 624, `riaprira` 637.
- E1-033 [S] Contabilita' pura: `exposure` 760, `net_pnl_by_total` 966, `locked_pnl` 1267, `cashout_value`, `cover_matched_value` 491, `under_liability` 504, `event_liability` 1255, `puntata_equivalente` 983, `ripiego_chiusura_sotto_minimo` 1005, `pnl_indipendente_dal_risultato` 1130, `prune_dead_legs` 1165 (`MAX_CANCELLED_PER_ROLE` 1127), `drift_ticks` 1205, `exit_kind_for` 1288, `opening_ref` 1321, minimi e vie d'ordine `minimo_listino` 709 / `via_ordine` 714 (diretto|submin|legalizzata|non_si_manda), `residuo_non_piazzabile` 826, `tolleranza_piatto_ou45` 806.
- E1-034 [S][P] Modello pre-match e hazard (`dossier.py`): `build_prematch` 66-111 (lambda, rho, `p_under35_cal`, `p4_pre`; una volta per evento), `combine_hazard` 114, `cover_gain_pct` 126, `get_empirical` 141 (cache senza scadenza, ritento a 600 s: G-034), `model_probs_from_grids` 217, `lambdas_con_ripiego` 241, `live_frame` 298, `load_atlas` 25; snapshot `feed.snapshot_from_row` 493-565, `implied_p4` 352, `market_totals` 368.
- E1-035 [S][P] **Regole che vivono nel SERVIZIO e non nel motore (da spostare identiche)**: stop giornaliero `daily_loss_stop` (`service.py:4120-4130`: P&L del giorno operativo = regolato + bloccato aperto <= -stop => spegne `pre_enabled`, `reentry_enabled`, `last_entry_persist`), tetto partite per modalita' `max_open_matches` (`service.py:4153`, `4194-4211`, `5279`; `posti_occupati_per_modo`), giorno operativo (`_operating_day_key`), commissione fissata sulle righe (`_settle_params`). Sono 3 punti di strategia fuori da `engine.py`: non coperti dall'impronta di `engine.py` (D8 in §3).
- E1-036 [S][P] Paper e live **stessa strategia, cambia solo CHI esegue** (`porta_ordini.py:5-15`): ordine live = FOK sui taker, lay appoggiata `LAPSE`; interruttore di sicurezza `MIKE_LIVE_ENABLED` (`service.py:103-128`).

Dichiarazione di completezza: l'inventario [S] sopra copre i 228 elementi di `engine.py` (le funzioni citate piu' le costanti e i dataclass `Book`/`Leg`/`Snapshot`/`MatchCtx`/`Action`/`Decision`/`CashoutValue`/`SettleResult` 103-433)
tramite l'impronta; i punti marcati «da indice» sono quelli di cui ho letto intestazione e docstring ma non il corpo.

### 2.2 GUSCIO - [G] - riducibile (E1-037 ...)

Classificazione delle 165 def/class di `service.py` per ruolo (strumento `e1_service_per_gruppo.py`, uscita `e1_service_per_gruppo_uscita.txt`; i totali sono righe di def fino alla def successiva, quindi includono
commenti e righe vuote interne: somma 7.450 su 7.552 righe di file):

| Gruppo | Righe | Dove va |
|---|---:|---|
| Scheletro del runtime (cicli, sveglia, canale, battito, cache, avvio/arresto, comandi in ingresso) | 1.671 | runtime D (comune) |
| Porta ordini e ciclo di vita dell'ordine (`execute_place` 339 righe, resting live/paper, riconciliazione, sorveglianza sospensione) | 3.258 | porta C + riconciliatore unico |
| Regolamento e conto Betfair | 868 | F |
| Colla di Mike (`_run_event` 778, `run_once` 374, codec ctx/righe, gestori di richiesta, dossier) | 1.631 | resta nel plugin |

Funzionalita' di guscio (letto da indice e docstring salvo dove ho citato righe):
- E1-037 [G] Ciclo persistente, cadenza adattiva `idle_cycle_s`/`decide_min_interval_ms` (`service.py:7289`, `_un_giro` 7471-7519), sveglia dal canale locale (6864-7039, D-009), pavimento giri/min (`_pavimento_sveglia` 6896).
- E1-038 [G] Avvio: `ferma_al_nuovo_avvio` 3964-3997 (il bot non riparte da solo: stato `stopped` all'avvio dell'app, `uscite_bot="mike"` 3991), lock di processo (`single_instance`, `LOCK_PORT_DEFAULT` `config.py:32`), timeout PostgREST del bot (7433), saldo su evento (7437).
- E1-039 [G][UI] Controllo e modo: `mike_control` (`db.py:59-70`), `status running|stopping|stopped|idle|error`, `mode paper|live` globale + `ev["mode"]` per partita (D-026), partite di modalita' diversa ancora vive dichiarate (`partite_di_modalita_diversa`, CRITICAL 4116), tetto e aggregati separati per modalita' (`posti_occupati_per_modo`, `get_mike_aggregates` per modo, `db.py:289-461`).
- E1-040 [G] Lettura dati: feed da canale 47336 (`avvia_client_scan` 7047, `_canale_copre_tutte`) o DB (`fetch_scan_rows`), ripiego REST del book (`_books_ripiego_rest` 1297), scanner age (`_scanner_age` 1413), allarme feed non letto (`_avvisa_feed_non_letto` 7144), episodio «dato assente» (`_episodio_dato_assente` 1518).
- E1-041 [G] Cache: `_Cache` 396-415 (fresco/metti/svuota), `_aggregates_cached` 1233, `svuota_le_cache` 436, `azzera_cache_di_processo` 3016; cadenze `feed_cache_s`, `events_reload_s`, `aggregates_cache_s`.
- E1-042 [G] Persistenza: `_persist` 6706 (solo se cambia, `_signature`), `_scrivi_evento` 6670, lotto `events_batch_write` 6751, battito rinfrescato `publish_heartbeat_s`/`publish_idle_heartbeat_s` (`_cadenza_pubblicazione`), `_ctx_from_row` 501 / `_row_from_ctx` (codec dello stato), riga trade `_trade_row`, `_insert_trade_row`, tabelle `mike_events`/`mike_trades`.
- E1-043 [G][UI] Stats di testata (~40 chiavi, blocco `stats = {...}` di `run_once` ~4285-4343), battito rate-limitato `stats_min_s`/`heartbeat_min_s` (4347-4364, `_cadenza_battito` 4435).
- E1-044 [G] Coda richieste: `process_requests` 3636-3738, `fail_stale_processing` (stale 10 min, `_STALE_REQUEST_MIN` 73), scarto richieste di altra partita (`_richiesta_non_di_questa_partita` 3591), esiti `done/failed` con codici (`MIKE_REQUEST_CODE_MESSAGE` `mike.ts:1873`).
- E1-045 [G][UI] Comandi: `cashout` (cash out manuale), `flatten` (chiudi ora, `_request_flatten` 3850-3963), `cancel` (`_request_cancel` 3820), `skip_event`/`resume_event` («Riprendi» sblocca anche la copertura, 2196), `approva_uscita` (`_request_approva_uscita` 3775, `_approvazione_eseguita`, `PropostaUscitaMike.tsx:212`).
- E1-046 [G] Porta ordini paper/live: `execute_place` 739-1079, `_piazza_resting_live` 2190-2378, `_segui_resting_live` 2620-2741, `_piazza_resting_paper` 1925, `_segui_ordini_paper_su_runner` 1694-1924, `porta_ordini.py` (224: `VistaMike` 115, `PortaCanaleMike` 161, `adatta_comando` 63, `ref_ordine`/`ref_annullo` 50/56), `omega_market.place_order_live`/`place_submin_live` (via C). Riserva di riga prima dell'invio (`service.py:2198-2204`), kill-switch sulle aperture REST (2210-2224).
- E1-047 [G] Riconciliazione e consapevolezza degli ordini: `_reconcile_trades` 5713-5815, `_reconcile_unknown` 5816-5915 («mai un'ipotesi»: senza `listCurrentOrders` si RESTA in riconciliazione), `_mark_trade_cancelled` 119 righe, `_aggancia_riserve_orfane`, `_sorveglia_posizione_di_conto` / `_sorveglia_sospensione` 3405-3504 / `_sorveglia_mercato_copertura` / `_sorveglia_gambe`, `_applica_esito_riapertura` (rilettura alla riapertura dopo una sospensione, §15.6 costituzione), `_chiudi_gamba_scaduta`.
- E1-048 [G] Regolamento: `_settle_trades` 6403-6600, `_leggi_regolato_conto` 6144-6267 (P&L dal conto Betfair), `_applica_conto`, `_retry_settle_rows` (`settle_confirm_s`), `regolato_conto.py` 359 (funzioni PURE: `componi_regolato` 114-234, `riga_utente` 311, `ordine_non_di_mike` 235; separa le righe dell'utente da quelle di Mike), `market_winner`/`final_total_from_books`/`market_voided`/`settle_plan`.
- E1-049 [G] Arresto ordinato: `arresto_con_ordini` 7315-7390 (annulla gli ordini non abbinati con tetto 10 s e dichiara le posizioni; copia propria, Omega/Safe passano da `arresto_bot.py`, D-057), segnali (7391-7413).
- E1-050 [G][UI] Attivita' scritte (diario): `db.log(kind, payload)` (`db.py:71-85`) con **almeno 51 tipi** (regex inline su `service.py`: `db.log("...")` e `_log_throttled`, non salvata come strumento): da `armed`, `state`, `place`, `place_pending`, `place_resting`, `fill_resting`, `cancel`, `cancel_esito`, `place_rifiutato`, `no_fill`, `skip`, `settled`, `daily_stop`, `config_warn`, `schema_warn`, `reconcile_fix`, `reconcile_pending`, `pnl_differenza_betfair`, `arresto_ordini_non_annullati`, `posizione_lasciata_per_arresto`, `chiuso_dall_utente`, `uscita_approvata`, `uscita_proposta`* (*: visto nei referti del banco, scritto per altra via), `mercato_sospeso`, `rilettura_alla_riapertura`, `ordine_scaduto_alla_sospensione`, `residuo_non_piazzabile`, `cover_resto_sotto_minimo`, `flusso_non_dichiarato`, `feed_line_missing`, `ripiego_rest`, `ordini_utente_nel_conto`, `error` ... Throttle `skip_log_interval_s` (`_log_throttled` 1487). Letti dalla UI: `MIKE_ACTIVITY_KINDS` 64 tipi (`mike.ts:1331`), `MIKE_ACTIVITY_EXTRA` 51 etichette (1422), `mikeActivityLine` 1493-1777 (285 righe di formattazione), `MIKE_REASON_LABEL` 48 motivi (1796). Pubblicazione sul canale (topic `mike_attivita`, D-051).
- E1-051 [G][UI] **Allarmi**: backend `config_warn` (`service.py:4520-4552`: finestra `entry_hours_before_ko` incoerente con `SAFE_PRE_KO_OU_HOURS`), `daily_stop` (4120), `_avvisa_feed_non_letto` 7144, `arresto_ordini_non_annullati`, `pnl_differenza_betfair`, CRITICAL su ordine reale bloccato (`service.py:117-128`) e regolamento sospeso per `ordine a esito ignoto` (`engine.py:3430`). UI: «DUE ALLARMI CHE NON DEVONO MAI MANCARE» `Mike.tsx:461-` (`mike-allarme-modalita-mista` 474, `mike-live-non-abilitato`), `ServiceHealthChip` (`Mike.tsx:430`, servizio morto a 45 s), badge «FEED FERMO» (`MikeMatchCard.tsx:540,639`), freschezza `feedFreshness` `mike.ts:797`, stato del mercato `MIKE_MARKET_STATUS` 815, toast di esito di OGNI richiesta (`Mike.tsx:112-121`) e di regolamento (109), toast di modo live (301, 330), errori dello storico `mikeHistoryErrorMessage` 857.
- E1-052 [G][UI] Pagina e schede: `pages/Mike.tsx` 799 (testata, `ModeToggle`, banner, tre sezioni `pre | live | fix` `splitMikeEvents` `mike.ts:748`, storico per partita `groupMikeTradesByEvent` 2129, equity `mikeEquitySeries` 2212, P&L giorno `romeDayStartMs` 2031), `MikeMatchCard.tsx` 1174 (fase, punteggio, quote, gambe `positionRows` 1228, cash out con barra `cashoutBarPct` 1020, uscita intelligente/in perdita, copertura `MIKE_COVER_FORM_LABEL` 1143, pulsanti 1103-1137: Cash out, Annulla, Chiudi ora, Salta, Riprendi), `MikeEventPnlTable.tsx`, `MikeCashOutButton.tsx` 245, `useMike.ts` 393 (RPC `mike_activate/mike_stop/mike_update_params/get_mike_state/get_mike_trades/mike_request` `mike.ts:2228-2274`; realtime canale `mike-live` 2360), `useMikeClock.ts`, `useMikeEventoAlMs.ts` (aggiornamento «al ms» dal canale).
- E1-053 [G][UI][P] Foglio parametri: `MikeParamsSheet.tsx` 82 (sopra `trading/ParamsSheetBase.tsx` 365; l'interruttore `uscite_automatiche` e' gestito a parte, riga 46), 8 gruppi `MIKE_PARAM_GROUP_LABEL` (`mike.ts:435`): `generale` 11, `pre` 20, `fischio` 9, `cover` 18, `cashout` 12, `uscite` 14, `reentry` 7, `rischio` 16 = 107 campi (17 bool, 6 scelte, 1 testo, 83 numeri; `e1_parametri_py_vs_ts.py`). Salvataggio `parametriMikeDaSalvare` `mike.ts:642` (un campo numerico svuotato RESTA assente e vale il default del servizio).
- E1-054 [G][UI] Control Room con Mike: interruttore «Uscite» (`controlroom/InterruttoreUscite.tsx:28-47`, `lib/interruttori.ts:1258`), proposte d'uscita da approvare (`PropostaUscitaMike.tsx`), esito chiusura (`EsitoChiusuraMike.tsx`), «Chiudi ora» (`BottoneChiudiRiga.tsx`, `chiudiRiga.ts`), cash out globale/partita (`CashOutGlobale.tsx`, `cashOutPartita.ts`), posizioni chiuse, P&L giorno (`dailyHistory.ts`): **non E1, scheda UI**; sono i punti dove Mike e' citato per nome.
- E1-055 [G] Registro e banco: voce `mike` in `registro_bot.py:219-243` (moduli di produzione = i 9 file, replay `certifica_scenario`, `parametri_modificabili`, `SCENARI_DESCRITTI`, controlli `Betfair.mike.certificazione`, `TRASPORTO_OBBLIGATO`); `certifica mike <ev> --scenari tutti` (`certifica.py:5`); catalogo del Match Replay generato dal registro (`replayBotCatalogo.ts`, header 1-9: «FILE GENERATO», test rosso se non allineato).
- E1-056 [G] Controlli di condotta del banco: `certificazione.py` 2.084 righe, **49 controlli** (`MASTER_FINALE`: A2, B6, B7, H1, H2, J1-J6, R1-R3, KG1, S1-S4, K1-K4, M1, G4, RG1, CP1-CP4, L2, ...), sono INVARIANTI della strategia/ordini espresse come controlli: restano, non si riducono.
- E1-057 [G] Replay e sintetiche: `tools/replay_registrazioni.py` 2.370 (parte SPECIFICA di Mike: `certifica.py:19-20`), `tools/synth_mike.py` 779 (5 scenari sintetici: `reingresso`, `reingresso_2gol`, `prezzo_migliore`, `ultimo_ingresso`, `ultimo_ingresso_riprova`), `tools/banco.py` 48.
- E1-058 [G] Migrazioni SQL: 11 file `migrations/*mike*` (tabelle `mike_control/requests/trades/events/activity`, RPC `mike_activate/stop/update_params/request/get_mike_state/get_mike_trades`, aggregati per modalita', storico per giorno, vincoli `flusso_fischio`, `reentry_max_goals` 29/09). Non toccare: le applica l'utente.

### 2.3 Parametri editabili e valori di serie (107): Python `config.py` <-> frontend `mike.ts`

Tabella generata da `strumenti/e1/e1_tabella_parametri.py` (default, limiti, riga in `config.py`, riga del campo in `mike.ts`, gruppo, file in cui la chiave e' letta). Le colonne «config.py» e «mike.ts» sono le righe dove la chiave e' DEFINITA.

| chiave | default | limiti / scelte | config.py | mike.ts | gruppo UI | letto in |
|---|---|---|---:|---:|---|---|
| `stake` | 10.0 | 0.5..500.0 | 77 | 442 | generale | engine |
| `commission_pct` | 5.0 | 0.0..20.0 | 78 | 443 | generale | engine,service |
| `entry_hours_before_ko` | 1.0 | 0.25..12.0 | 85 | 444 | generale | engine,service,feed |
| `competition_filter` | '' | - | 86 | 445 | generale | feed |
| `decide_min_interval_ms` | 500 | 100..5000 | 87 | 446 | generale | service |
| `feed_max_age_s` | 45.0 | 3.0..180.0 | 95 | 447 | generale | feed |
| `scanner_alive_max_s` | 75.0 | 10.0..300.0 | 101 | 448 | generale | feed |
| `book_seen_max_s` | 90.0 | 5.0..600.0 | 114 | 450 | generale | feed |
| `order_max_age_s` | 20.0 | 3.0..120.0 | 115 | 451 | generale | feed |
| `order_scanner_max_s` | 30.0 | 5.0..120.0 | 116 | 452 | generale | feed |
| `pre_enabled` | True | - | 118 | 453 | pre | engine,service |
| `pre_entry_price_min` | 1.3 | 1.01..20.0 | 119 | 454 | pre | engine |
| `pre_entry_price_max` | 3.0 | 1.01..20.0 | 120 | 455 | pre | engine |
| `pre_min_back_size_factor` | 1.0 | 0.5..5.0 | 121 | 456 | pre | engine |
| `pre_max_spread_ticks` | 6 | 1..20 | 124 | 457 | pre | engine |
| `pre_green_ticks` | 2 | 1..10 | 125 | 458 | pre | engine |
| `pre_exit_mode` | 'resting' | {resting/taker} | 128 | 459 | pre | engine,service |
| `live_resting_enabled` | True | - | 137 | 449 | generale | service |
| `pre_entry_ttl_s` | 60 | 5..3600 | 138 | 460 | pre | engine |
| `pre_max_cycles` | 10 | 0..100 | 139 | 461 | pre | engine |
| `pre_reentry_cooldown_s` | 60 | 0..3600 | 140 | 462 | pre | engine |
| `pre_last_entry_min` | 10 | 1..120 | 141 | 464 | pre | engine |
| `last_entry_persist` | True | - | 142 | 465 | pre | engine,service |
| `last_entry_ticks_above` | 0 | 0..3 | 143 | 466 | pre | engine |
| `veto_p_under35_cal` | True | - | 152 | 469 | pre | engine |
| `veto_p_under35_soglia_130` | 0.807 | 0.0..1.0 | 153 | 470 | pre | engine |
| `veto_p_under35_soglia_150` | 0.684 | 0.0..1.0 | 154 | 471 | pre | engine |
| `veto_p_under35_soglia_200` | 0.514 | 0.0..1.0 | 155 | 472 | pre | engine |
| `veto_p_under35_soglia_250` | 0.385 | 0.0..1.0 | 156 | 473 | pre | engine |
| `veto_p_under35_soglia_300` | 0.275 | 0.0..1.0 | 157 | 474 | pre | engine |
| `cancel_unmatched_after_ko_s` | 120 | 0..900 | 158 | 475 | pre | engine |
| `ko_green_enabled` | True | - | 163 | 476 | fischio | engine |
| `ko_green_ticks` | 2 | 1..10 | 164 | 477 | fischio | engine |
| `ko_green_window_s` | 180 | 0..900 | 165 | 478 | fischio | engine |
| `ko_green_retry_s` | 5 | 1..60 | 173 | 482 | fischio | NESSUNO |
| `second_entry_enabled` | True | - | 177 | 483 | fischio | engine |
| `second_entry_stake_pct` | 50.0 | 0.0..200.0 | 178 | 484 | fischio | engine |
| `early_goal_cover_delay_s` | 120 | 0..900 | 183 | 485 | fischio | engine |
| `early_goal_cover_pct` | 50.0 | 0.0..100.0 | 184 | 486 | fischio | engine |
| `early_goal_cover2_delay_s` | 180 | 0..900 | 185 | 487 | fischio | engine |
| `cover_enabled` | True | - | 187 | 488 | cover | engine |
| `cover_profit_factor` | 1.2 | 1.0..3.0 | 188 | 489 | cover | engine |
| `cover_policy` | 'auto' | {auto/immediate/wait} | 189 | 490 | cover | engine |
| `cover_wait_hazard_max` | 0.06 | 0.0..1.0 | 194 | 491 | cover | engine |
| `cover_wait_max_min` | 10 | 0..45 | 195 | 492 | cover | engine |
| `cover_wait_p4_max` | 0.16 | 0.0..1.0 | 196 | 493 | cover | engine |
| `cover_good_price` | 7.0 | 1.01..50.0 | 197 | 494 | cover | engine |
| `cover_wait_min_gain_pct` | 8.0 | 0.0..100.0 | 198 | 495 | cover | engine |
| `cover_wait_step_min` | 5 | 1..20 | 199 | 496 | cover | engine,service |
| `cover_postgoal_delay_s` | 45 | 0..300 | 200 | 497 | cover | engine |
| `cover_max_goals` | 2 | 0..4 | 201 | 498 | cover | engine |
| `cover_rounding` | 'ceil' | {ceil/floor/nearest} | 202 | 499 | cover | engine,service |
| `cover_max_overshoot_pct` | 30.0 | 0.0..200.0 | 203 | 500 | cover | engine |
| `cover_form` | 'lay_under45' | {lay_under45/back_over45} | 212 | 502 | cover | engine,service |
| `exact_sizes` | True | - | 215 | 503 | cover | engine,service |
| `cover_rifiuti_max` | 3 | 1..20 | 235 | 506 | cover | engine |
| `cover_retry_min_s` | 15 | 1..300 | 236 | 507 | cover | engine |
| `cashout_profit_pct` | 5.0 | 0.5..50.0 | 238 | 508 | cashout | engine,service |
| `cashout_base` | 'total' | {total/under} | 239 | 509 | cashout | engine |
| `cashout_place_at_ticks` | 0 | 0..3 | 240 | 510 | cashout | engine,service |
| `cover_place_at_ticks` | 2 | 0..6 | 249 | 511 | cover | engine |
| `cashout_smart_enabled` | True | - | 253 | 512 | cashout | engine |
| `uscite_automatiche` | False | - | 263 | 519 | uscite | engine |
| `cashout_smart_min_pct` | 2.0 | 0.0..50.0 | 264 | 520 | cashout | engine |
| `cashout_smart_tolerance_pct` | 2.0 | 0.0..50.0 | 265 | 521 | cashout | engine |
| `cashout_smart_hazard_hot` | 0.1 | 0.0..1.0 | 266 | 522 | cashout | engine |
| `cashout_smart_pressure_hot` | 1.15 | 1.0..1.25 | 267 | 523 | cashout | engine |
| `cashout_smart_goals_hot` | 3 | 0..8 | 268 | 524 | cashout | engine |
| `cashout_smart_ev_margin_pct` | 1.0 | 0.0..50.0 | 269 | 525 | cashout | engine |
| `close_retry_s` | 10 | 1..600 | 270 | 526 | cashout | engine |
| `close_max_attempts` | 20 | 1..100 | 271 | 527 | cashout | engine |
| `loss_exit_mode` | 'model' | {model/fixed} | 276 | 530 | uscite | engine |
| `loss_exit_risk_premium_pct` | 10.0 | 0.0..300.0 | 287 | 531 | uscite | engine |
| `loss_exit_p4_prudent` | True | - | 288 | 532 | uscite | engine |
| `loss_exit_max_pct` | 0.0 | 0.0..100.0 | 289 | 533 | uscite | engine |
| `loss_exit_emp_min_n` | 200 | 20..5000 | 290 | 534 | uscite | service |
| `ht_loss_exit_enabled` | True | - | 291 | 528 | uscite | engine |
| `ht_loss_pct` | 25.0 | 0.0..100.0 | 292 | 529 | uscite | engine |
| `ht_loss_goals_min` | 3 | 0..8 | 296 | 535 | uscite | engine |
| `ht_loss_goals_max` | 4 | 0..8 | 297 | 536 | uscite | engine |
| `h2_loss_exit_enabled` | True | - | 298 | 537 | uscite | engine |
| `h2_loss_pct` | 25.0 | 0.0..100.0 | 299 | 538 | uscite | engine |
| `h2_loss_from_min` | 46 | 45..100 | 300 | 539 | uscite | engine |
| `h2_loss_to_min` | 85 | 45..100 | 301 | 540 | uscite | engine |
| `reentry_enabled` | True | - | 303 | 541 | reentry | engine,service |
| `reentry_green_ticks` | 2 | 1..10 | 304 | 542 | reentry | engine |
| `reentry_max_goals` | 2 | 0..2 | 307 | 545 | reentry | engine |
| `reentry_until_min` | 45 | 0..100 | 308 | 546 | reentry | engine |
| `reentry_exit_until_min` | 0 | 0..100 | 310 | 547 | reentry | engine |
| `reentry_price_min_over_entry` | True | - | 311 | 548 | reentry | engine |
| `reentry_hold_if_loss` | False | - | 312 | 549 | reentry | engine |
| `settle_confirm_s` | 60 | 0..600 | 316 | 550 | rischio | service |
| `max_open_matches` | 10 | 1..90 | 317 | 551 | rischio | service |
| `daily_loss_stop` | 50.0 | 0.0..100000.0 | 318 | 552 | rischio | service |
| `max_liability_per_match` | 0.0 | 0.0..100000.0 | 319 | 553 | rischio | engine |
| `event_loss_cap_pct` | 100.0 | 0.0..500.0 | 320 | 557 | rischio | NESSUNO |
| `skip_log_interval_s` | 300 | 10..3600 | 323 | 558 | rischio | service |
| `feed_cache_s` | 4.0 | 0.0..30.0 | 338 | 559 | rischio | service |
| `events_reload_s` | 60.0 | 0.0..600.0 | 342 | 560 | rischio | service |
| `aggregates_cache_s` | 20.0 | 0.0..300.0 | 344 | 561 | rischio | service |
| `reconcile_every_s` | 30.0 | 0.0..600.0 | 347 | 562 | rischio | service |
| `idle_cycle_s` | 5.0 | 1.0..60.0 | 350 | 563 | rischio | service |
| `publish_heartbeat_s` | 5.0 | 0.0..120.0 | 373 | 564 | rischio | service |
| `publish_idle_heartbeat_s` | 60.0 | 0.0..600.0 | 378 | 565 | rischio | service |
| `events_batch_write` | True | - | 381 | 566 | rischio | service |
| `stats_min_s` | 10.0 | 0.0..300.0 | 388 | 567 | rischio | service |
| `heartbeat_min_s` | 20.0 | 0.0..300.0 | 389 | 568 | rischio | service |

**Esito del confronto Python <-> TypeScript** (`e1_parametri_py_vs_ts.py`, uscita `e1_parametri_py_vs_ts_uscita.txt`): 107 chiavi in `PARAM_SPEC` (`config.py:76-390`), 107 campi in `MIKE_PARAM_FIELDS`
(`mike.ts:441-570`), 107 default in `MIKE_PARAM_DEFAULTS` (`mike.ts:571-608`). **Default: 0 differenze. Limiti: 0 differenze. Scelte dei 6 campi `choice`: 0 differenze** (controllato anche a mano: `daily_loss_stop` e `max_liability_per_match` hanno `max: 100_000` in `mike.ts:552-553` come `config.py:318-319`; una prima versione dello script leggeva `100_000` come `100` per un errore nella regex, corretto: i letterali con `_` sono ora gestiti). **Differenze Python/TS vere rimaste: nessuna.** Il frontend e' dichiarato «SPECCHIO» a mano (`mike.ts:440`,
«stesso ordine, stessi limiti») e il contratto lo controlla con un test (`config.py:411-435` commento su `BACKEND_ONLY_PARAMS`, tupla vuota alla riga 435 che «DEVE RESTARE VUOTA»); **la terza copia** e' il catalogo generato `replayBotCatalogo.ts`
(dal registro; non scritta a mano).
Dove i valori di serie sono copiati altrove: il veto M1 ripete i 5 nodi in `engine.py:3549-3555` (default di ripiego di `soglia_veto_under35` 3574-3578) e nel TS; `uscite_automatiche=False` e' in `config.py:263`,
`engine.py:3175`, `avvio_app.py:180-191`, `mike.ts` DEFAULTS, `mike_request` SQL (`uscite_automatiche_mike_2026-09-25.sql:42`).

---------------------------------------------------------------------------------------------------------------------------------

## 3. DIFETTI STRUTTURALI

- **D1. Il guscio e' il 50% del Python di Mike e la strategia il 39%** (`wc -l`): strategia = `engine.py` 5.359 + `feed.py` 583 + `dossier.py` 411 + `config.py` 491 = 6.844 (38,5% di 17.755); guscio = `service.py` 7.551 + `db.py` 693 + `porta_ordini.py` 224 + `regolato_conto.py` 359 = 8.827 (49,7%); `certificazione.py` 2.084 (11,7%) e' banco. In `service.py` solo 1.631 righe di def (22%) sono colla specifica di Mike; 5.797 (78%) sono scheletro (1.671), porta ordini e ciclo d'ordine (3.258) e regolamento (868) che D, C ed F sostituiscono.
- **D2. Tre funzioni enormi** nel servizio: `_run_event` 778 righe, `run_once` 374, `execute_place` 339 (`service.py:4739, 3998, 739`) mescolano IO, DB, rete e decisione. La decisione e' gia' una funzione pura (`engine.decide`): il guscio puo' ridursi senza toccarla.
- **D3. Polling a vuoto**: a riposo Mike fa 48 richieste/min (4 letture per giro x 12 giri/min, §1.3); in fretta ~256. Controllo, richieste e trade vengono riletti anche se nessuno li ha toccati; la riga di controllo e le richieste hanno gia' un canale locale (D-021, D-034) ma il giro le legge comunque.
- **D4. Copie dello scheletro**: `ferma_al_nuovo_avvio` mike 3964(32) ~ omega 7966 ~ safe 10083 (somiglianza 0,95-0,98), `_avvia_sveglia` mike 6925 ~ omega 8671 (0,90), `_ciclo_persistente` 7289(14) ~ 8773 ~ 10877, `_Cache` mike 396 ~ omega 169 (0,94-1,00), `_netto_su_selezione` mike 3071 ~ safe 1806 (0,93), `_avvisa_feed_non_letto` mike 7144 ~ safe 9599 (0,79), `arresto_con_ordini` mike 7315-7388 e' una copia propria di `arresto_bot.py` (D §1.3). Gemelle in DB: `mike/db.py:59,64,71` ~ `omega_db.py:49,55,61` ~ `bot_db.py:62,70,77` (G-019); coda flumine `mike/db.py:650-693` ~ `omega_db.py:586-696` ~ `bot_db.py:987-1044` al 99-100% (G-025).
- **D5. Due porte per due modalita'**: paper passa dal runner (S1), live in REST diretto (S3) senza diario, senza dedup per ref, senza kill-switch del runner (C, §1 e C-026): due percorsi che la parita' paper/live deve far coincidere a mano (`porta_ordini.py:5-15`). Mike e' l'unico bot calcio il cui live NON passa dal motore.
- **D6. RITIRATO** (reperto falso, corretto su segnalazione del coordinatore): il confronto dei limiti Python/TS leggeva male i numeri con separatore `_` (`100_000` -> `100`). Verificato a mano: `daily_loss_stop` `0..100_000` in `config.py:318` e `mike.ts:552`, `max_liability_per_match` `0..100_000` in `config.py:319` e `mike.ts:553`. Rieseguito lo script corretto: 107 chiavi, 107 campi, 107 default, 0 differenze di default, limiti e scelte. Nessun rischio di abbassamento silenzioso dei valori salvati. Il numero D6 resta occupato per non rinumerare i rimandi.
- **D7. Parametri morti: 2 su 107 non sono letti da nessuna parte** (`e1_tabella_parametri.py`, colonna «letto in» = NESSUNO): `ko_green_retry_s` (`config.py:173`, dichiarato morto nel commento 165-172 «NON HA PIU' EFFETTO») e `event_loss_cap_pct` (`config.py:320`; l'etichetta UI e' «NON ATTIVO», `mike.ts:557`; il `loss_cap` e' citato in `engine.py:3157, 5019` e `certificazione.py:587,682,716` ma nessun ramo calcola un cap su `event_loss_cap_pct`). Restano nella whitelist per non rompere i parametri salvati; nel foglio parametri sono 2 campi che non fanno nulla.
- **D8. Regole di strategia fuori da `engine.py`** (E1-035): stop giornaliero, tetto partite per modalita', giorno operativo vivono in `service.py:4116-4211` dentro `run_once`; la garanzia a impronta di `engine.py` non le vede e nessun replay a partita singola le esercita (il referto `MASTER_FINALE` e' su UNA partita). Inoltre `last_entry_ticks_above` e' letto dal motore (`engine.py:3877`) ma il TS lo dichiara «NON ATTIVO» (`mike.ts`, campo omonimo): una delle due descrizioni e' falsa (da verificare con la costituzione §M2).
- **D9. Valori di serie duplicati a mano in 3-5 posti** (§2.3): il catalogo dei parametri e' definito in Python (`PARAM_SPEC`), riscritto a mano in TS (campi + default + hint + gruppi) e riprodotto in modo generato nel catalogo del replay; i 5 nodi del veto sono una quarta copia nel motore (`engine.py:3549-3555`). `PROCESSO_STANDARD_BOT.md` §7 n.33 («costante nel frontend che duplica una scelta del backend») e' esattamente questo.
- **D10. Dipendenza della strategia da moduli di altri bot**: `engine.py` importa `ticks_between` da `Betfair.stream.scalper.scalper_bot` (`engine.py:33`): per spostare o sostituire lo scalper bisogna prima portare quella funzione identica altrove; `omega_market` e' il client REST dei soldi veri di Mike (`service.py` via `_RealMarket` 146).
- **D11. Copertura di parita' sottile**: il banco certifica Mike con **UNA sola registrazione completa** (`35760084`, `qualita' delle registrazioni: COMPLETE x1`, referto `MASTER_FINALE`): su quella partita **7 stati non vengono mai visti** (`PRE_LAST_ENTRY_PENDING`, `LIVE_SECOND_ENTRY`, `REENTRY_PENDING`, `REENTRY_OPEN`, `REENTRY_GREEN_PENDING`, `ERROR`, `SKIPPED`) e **6 controlli su 49 non sono mai sollecitati** (A2, B6, B7, H1, H2, J5B). Il re-ingresso, l'ultimo ingresso e la seconda entrata sono esercitati solo dalle 5 sintetiche (`mike_sintetiche_INTEGRATA.txt`: 20 controlli su 49 mai sollecitati, 8 stati mai visti). Su `ht_ft_rows` (tabella empirica) il referto dice «NON ESERCITABILE» (non e' nella registrazione di una partita).
- **D12. Il referto di riferimento e' STALE.** `AUDIT_2026-10-02/replay/mike_tutti_MASTER_FINALE.txt` e' stato prodotto il 02/10 col codice `1fa090ef6631`; dopo sono entrati commit che cambiano la condotta di Mike (04/10: `22e86381` chiusura in profitto di 2 tick, `8f538e78` banca U4.5 < banca U3.5, `787be8d6`/`4dd624af` regola delle punte .it, `991fbd49`). I numeri di §5.2 sono quindi la FORMA del baseline, **non il baseline di oggi**: va rieseguito su `HEAD` prima di toccare.
- **D13. Il banco e' lento**: `MASTER_FINALE` dichiara «TEMPO TOTALE 12m08.4s (728.4 s) su 26 replay | obiettivo 300 s, tetto 600 s» e «LENTO ... e' un AVVISO». Contro l'ordine dell'utente del 29/09 (`PROCESSO_STANDARD_BOT.md` §6.9: 5 min, tetto 10) e contro la regola «mai lanciare un replay da piu' di 10 minuti senza dirlo». Scenario piu' caro `chiuso-fuori-app` 95,3 s; `base` 92,5 s a 563 tick/s. Difetto del banco (scheda H), non di Mike, ma blocca la parita' di Mike.
- **D14. Stato in piu' posti**: Mike usa un `status` di controllo e uno `status` per partita, due `mode` (globale e per partita), tre firme (`_signature`, `before_sig`, `uscita_proposta.sostanza`): lo stato e' in piu' posti (riga di controllo, riga evento, RAM `_CACHE_EVENTI`, ctx JSON, righe `mike_trades`, specchio `betfair_live_orders`) e la riparazione fra specchi (`_reconcile_trades`, `_mirror_is_aligned`, `reconcile_every_s`) esiste perche' sono copie.

---------------------------------------------------------------------------------------------------------------------------------

## 4. DOMANI

### 4.1 Struttura nuova (UNA cartella, UN contratto, UN `COSA_FA.md`)

```
bots/mike/                      # tutto cio' che e' di Mike, e SOLO di Mike
  COSA_FA.md                    # questa scheda, ridotta a: cosa fa, parametri, stati, allarmi
  strategia/                    # LOGICA INTOCCABILE: engine.py (spostato, identico), feed.py (snapshot/candidate),
                                #   dossier.py (modello), regole_di_conto.py (daily stop, tetto partite: dal servizio, identiche)
  parametri.py                  # PARAM_SPEC (107 chiavi) = UNICA definizione; il TS e il catalogo del replay si GENERANO da qui
  plugin.py                     # adattatore Decisore (osserva = feed.snapshot_from_row + engine.decide), codec dello stato, su_comando
  banco/                        # controlli di condotta (certificazione.py), scenari dichiarativi, sintetiche
  tests/                        # test di contratto + i 99 file di oggi
frontend/src/bots/mike/         # schede e testi di Mike (MikeMatchCard, etichette di attivita'/motivi)
```

### 4.2 Mappa di Mike sul contratto `Plugin/Decisore` di `D_RUNTIME_BOT_CONTRATTO.md` §4.2

| Contratto D | Mike oggi | Mike domani |
|---|---|---|
| `catalogo_parametri()` | `config.PARAM_SPEC` 107 chiavi (`config.py:76-390`) | `parametri.py`, identico; TS e catalogo del replay generati |
| `uscite_di_serie()` / `chiave_uscite()` | `uscite_automatiche=False` (`config.py:263`) | `MANUALE`; chiave nativa `uscite_automatiche` (bool); `avvio_app.py:180-191` smette di conoscere Mike per nome |
| `arma(event_id, prematch, stato)` | `_run_event` arma + `dossier.build_prematch` (`service.py:4159`) + `_ctx_from_row` 501 | `plugin.arma`: ricostruisce il `MatchCtx` dal salvato (codec ~260 righe, stesse chiavi) e carica il dossier dal `Prematch` (G-033) |
| `osserva(stato, libri, quadro, orologio, p, prematch) -> Esito` | `feed.snapshot_from_row` (`feed.py:493`) + `E.decide` (`engine.py:3089`) + `E.apply_decision` (5304) | **identica**: `Snapshot` costruito dal `Quadro/Libri`, `decide` invariata. Il feed del riquadro dell'evento (`safe_strategy_scan`) resta l'ingresso dati finche' non c'e' lo stream in-process (G/A) |
| `su_comando(stato, comando, p)` | `_request_approva_uscita` 3775, `_request_cancel` 3820, `_request_flatten` 3850 (~190 righe) | `plugin.su_comando`: stessa logica, `Intento(tipo="chiudi" ...)`; la coda e lo stale sono del runtime |
| `su_esito_ordine(stato, ordine, orologio)` | riconciliazione per polling (`_reconcile_trades` 5713, `_reconcile_unknown` 5816) e `_segui_resting_live` 2620 | `plugin.su_esito_ordine` guidato da fill/parziale/rifiuto dalla porta C; il polling `listCurrentOrders` resta SOLO come riconciliazione di sicurezza («mai un'ipotesi») |
| `su_fase(stato, fase, orologio)` | `ARMATO..REGOLATO`: stati `E.STATES` + sospensione 3405 + regolamento 6403 | `Fase` comune; Mike mappa i suoi 21 stati in `Fase` senza cambiarli |
| `cadenza()` | 1,0 s in fretta / 5,0 s a riposo (`service.py:7487-7498`) | `Cadenza(modo="giro", periodo_s=1.0, riposo_s=5.0, sveglia_su_prezzo=<canale 47336>)` |
| `fine_giro(stati, p, orologio)` | stop giornaliero (4120), tetto partite (4153-4211) | `regole_di_conto.fine_giro`: stesse formule, stessi default |
| `Intento` `piazza/annulla/chiudi/proponi_uscita/diario/allarme` | `execute_place` + riga di riserva + log | `piazza` verso la porta C (paper e live con lo stesso trasporto: sparisce `VistaMike`); `proponi_uscita` = `uscita_proposta` di `gate_uscite`; `allarme` = i `db.log` critici |

Cio' che NON cambia (vincolo di §0 del brief del piano): tutte le funzioni di §2.1 (impronta a 386 voci), la semantica di `uscite_automatiche`, i default, la separazione paper/live, gli stati, i ruoli delle gambe, i codici di motivo
scritti nelle attivita' (la UI li legge: `MIKE_REASON_LABEL` 48 voci, `MIKE_ACTIVITY_KINDS` 64).

### 4.3 Stima delle righe (metodo esplicito)

Righe Python di Mike, esclusi test:

| Blocco | OGGI | DOMANI | Come ho calcolato |
|---|---:|---:|---|
| **Strategia: `engine.py`** | 5.359 | 5.359 | identica; al piu' si spezza in moduli (`stato`, `costi`, `uscite`, ...) con lo stesso contenuto: l'impronta lo garantisce |
| Strategia: `feed.py` (snapshot, candidate, freschezza) | 583 | 583 | identica |
| Strategia: `dossier.py` | 411 | 411 | identica (cache e TTL dei dati cloud sono di G) |
| Strategia: `config.py` (`PARAM_SPEC` + env helper) | 491 | 491 | identica; diventa l'UNICA fonte (il TS si genera) |
| Strategia: regole nel servizio (E1-035) | ~100 (inc. in `service.py`) | 100 | si SPOSTANO come funzioni pure (`service.py:4116-4130`, `4153-4211`, `5279`): stesso codice |
| **Totale strategia** | **6.844 (+~100)** | **6.944** | 0 righe risparmiate: e' cio' che il brief vieta di toccare |
| Scheletro del runtime (`service.py`) | 1.671 | 0 | diventa runtime comune D: il costo e' contato UNA volta in D (3.510 per tutti i bot, `D` §4.4), non qui |
| Porta ordini + ciclo d'ordine (`service.py`) + `porta_ordini.py` | 3.258 + 224 = 3.482 | 800-1.300 | `C` §4: i punti d'invio dei bot calcio 1.222 -> 360 (-71%); resta di Mike cio' che e' regola: freni sulla copertura (gia' in `engine.py`), uscite appoggiate `LAPSE`, rilettura alla riapertura, sorveglianza sospensione. Prudente 1.300 (se resta il 37%), ottimista 800 (23%) |
| Regolamento e conto (`service.py` 868 + `regolato_conto.py` 359) | 1.227 | ~450 | `F`: un solo regolamento dal conto; resta la separazione righe-utente/righe-Mike (`componi_regolato`, funzione pura) e il mapping al P&L di Mike |
| Colla di Mike (`_run_event`, `run_once`, codec, gestori) | 1.631 | ~700 | `run_once`/`_run_event` perdono IO, DB, stats, battito, riconciliazione (ora runtime/porta); restano costruzione dello `Snapshot`, chiamata a `decide`, traduzione `Decision.actions -> Intento`, `su_comando` (~120), codec dello stato (~260: D §4.4) |
| `db.py` (34 funzioni) | 693 | ~150 | G: 3 funzioni di controllo/log triplicate, coda flumine copia 1:1 (G-025), aggregati, scan, fixture: restano `insert_trade`/`update_trade`/eventi/`approva` come DB generico per bot |
| **Guscio (service + db + porta + regolato)** | **8.827 (-100 spostate = 8.727)** | **~2.350** (banda 1.900-3.000) | somma sopra: 0 + 1.050 + 450 + 700 + 150 |
| **Variazione del guscio** | | **-73%** (banda -66 / -78%) | confronto D: `-59%` sullo scheletro dei 7 file; qui e' piu' alto perche' in Mike il guscio e' dominato da ordini e conto che C/F sostituiscono |
| Banco di Mike: `certificazione.py` + `replay_registrazioni.py` + `synth_mike.py` + `banco.py` | 2.084 + 2.370 + 779 + 48 = 5.281 | ~3.460 | i 49 controlli (2.084) e le sintetiche (779) restano: sono la garanzia; `replay_registrazioni.py` 2.370 -> ~600 con scenari dichiarativi sul banco comune H; `banco.py` sparisce |
| **TOTALE Python di Mike (esclusi test)** | **17.755 + 3.197 tools = 20.952** | **~12.750** | strategia 6.944 + guscio 2.350 + banco 3.460; **-39%** complessivo, **-58%** sul solo non-strategia (14.008 -> 5.810) |

Il 33% (6.944 su 20.952 oggi; 54% del totale di domani) e' strategia che non si tocca: ecco perche' il ribasso complessivo non puo' arrivare a -80% senza toccare le regole. Il -73% del guscio dipende dalle schede C, D, F, G, H: le cifre
di quelle schede sono ipotesi finche' non esistono. Frontend: 5.401 righe specifiche oggi; domani **~4.700-5.000** (-7/-13%): sparisce a mano `MIKE_PARAM_FIELDS`+`MIKE_PARAM_DEFAULTS` (`mike.ts:441-608`, 168 righe, generate) e `mergeMikeParams`/`parametriMikeDaSalvare`
(`mike.ts:612-655`, 44) diventano generici, `useMike.ts` 393 si riduce a un hook per bot; restano schede, etichette e formattazione delle attivita' (`mike.ts:1331-1777`), che SONO la presentazione della strategia.

### 4.4 Dove vive ogni funzionalita' domani

- E1-001..036 (strategia) -> `bots/mike/strategia/` (stesso codice; spostamento verificato col confronto delle impronte); E1-035 -> `strategia/regole_di_conto.py` come funzioni pure testate da sole.
- E1-037..043 (cicli, avvio, controllo, dati, cache, persistenza, stats) -> runtime D (`Cicli`, `Avvio`, `Controllo`, `Persistenza`, `Battito`), configurati dal `Plugin`.
- E1-044, E1-045 (comandi) -> `runtime/comandi.py` smista a `Plugin.su_comando`; gestori di Mike in `plugin.py`.
- E1-046, E1-047 (ordini e riconciliazione) -> porta unica e riconciliatore unico (C), con la regola «live = paper nello stesso trasporto».
- E1-048 (regolamento) -> F; E1-049 (arresto) -> `runtime/arresto`.
- E1-050, E1-051 (attivita' e allarmi) -> `runtime/diario` + `Intento("diario"/"allarme")`; i testi UI restano in `frontend/src/bots/mike`.
- E1-052..054 (UI) -> `frontend/src/bots/mike/` + componenti generici per bot; E1-053 -> foglio parametri generato dal catalogo (UNA definizione).
- E1-055..057 (registro, banco, replay) -> `Registro` unico (`plugin` e `cartella`), adattatore del banco UNO (H); controlli e sintetiche restano in `bots/mike/banco/`.

### 4.5 Gia' in una libreria matura e oggi riscritto

- **Stato degli ordini**: Mike legge lo stato degli ordini con `listCurrentOrders` a polling (`_reconcile_trades` 5713, `_rileggi_ordine_appoggiato` 2781, `_segui_resting_live` 2620, `regolato_conto.py:242-263`, C-082) e lo ricostruisce a mano, mentre `betfairlightweight` espone l'`OrderStream` e flumine tiene `order.status`/`order.simulated`/`order.execution_complete`: e' la riconciliazione R6 di C (560 righe) da sostituire con l'evento di fill dalla porta. **Non l'ho verificato contro la documentazione di flumine in questa sessione** (non e' nel perimetro e non ho usato rete): e' un'ipotesi coerente con `C_PORTA_ORDINI.md`, da confermare in C.
- **Ladder**: `round_to_tick`/`ticks_away` sono del repo (`live_order_build`), `ticks_between` e' preso dallo scalper; flumine/betfairlightweight hanno utilita' di prezzo (`price_ticks_away`, `get_nearest_price`): non le ho confrontate per identita' numerica (i tick sono strategia: un'eventuale sostituzione richiede prova numerica sui replay).
- **Calcolo di green-up**: `trading/greenup.compute_greenup` e' interno al repo (gia' condiviso con lo scalper). Nessuna riduzione proposta.

---------------------------------------------------------------------------------------------------------------------------------

## 5. PARITA'

### 5.1 Che cosa dimostra «stessa identica cosa»

1. **Impronta della strategia** (nuova, E1): `python -I ARCHITETTURA_2026-10/strumenti/e1/e1_impronta_strategia.py confronta` -> «differenze: 0» dopo ogni tappa; l'elenco `.tsv` e' il registro delle 386 voci. Fa rosso se una soglia, un `default`, una condizione, un ramo cambia; NON fa rosso se una funzione cambia di file o di commento.
2. **Replay del banco comune sul codice di produzione** (unico punto d'ingresso, regola 2 dello standard): `python -m Betfair.stream.backtest.certifica mike 35760084 --scenari tutti` (26 coppie evento x scenario) + le 5 sintetiche (`Betfair/mike/tools/synth_mike.py`) + `--trasporto canale` e `--trasporto coda` (i referti ne hanno entrambi). Stessa registrazione, stessi scenari -> stessi numeri riga per riga PRIMA e DOPO.
3. **Test Python**: `python -m pytest Betfair/mike/ -q -p no:cacheprovider` (99 file, 1.358 funzioni) invariato; il test di contratto UI (`test_mike_certificazione_ui`) e il test che il TS e' specchio del Python.
4. **Frontend**: `npx vitest run` (28 file con «mike» e «test» nel nome, `ls -R`) e `npx tsc -p tsconfig.app.json --noEmit` a 0 errori; fotografie delle schede (`MikeMatchCard`, foglio parametri, due allarmi) prima/dopo.
5. **Controllo automatico di parita' dei parametri**: confronto Python/TS (`e1_parametri_py_vs_ts.py`, corretto per i letterali con `_`) rosso su qualunque differenza di default, limite o scelta (oggi: 0).

### 5.2 Numeri da far coincidere (forma del baseline: referto del 02/10, `AUDIT_2026-10-02/replay/mike_tutti_MASTER_FINALE.txt`)

Registrazione `35760084` (COMPLETE), flumine 2.13.11, betfairlightweight 2.23.2, codice `1fa090ef6631` (9 file), 49 controlli attivi, 26 replay; **da ririlasciare su `HEAD` (D12)**. Colonne: tick / decisioni / azioni per scenario.

| Scenario | tick | decisioni | azioni | Scenario | tick | decisioni | azioni |
|---|---:|---:|---:|---|---:|---:|---:|
| base | 52.082 | 5.246 | 6 | copertura-rifiutata | 53.262 | 5.367 | 6 |
| taker | 53.466 | 5.531 | 4 | copertura-rifiutata-legacy | 53.213 | 5.354 | 6 |
| cap-stretto | 52.082 | 5.246 | 6 | copertura-legacy | 52.094 | 5.243 | 6 |
| bot-fermo | 56.229 | 1.024 | 0 | cashout-dopo-copertura | 53.027 | 5.354 | 8 |
| senza-seconda-puntata | 52.082 | 5.246 | 6 | rifiuti-betfair | 53.703 | 5.543 | 5 |
| feed-stantio | 56.229 | 1.024 | 0 | chiusura-abbinata-in-parte | 52.082 | 5.246 | 6 |
| esiti-ignoti | 52.137 | 5.262 | 9 | ko-green-parziale | 52.082 | 5.246 | 6 |
| taker-esiti-ignoti | 53.470 | 5.531 | 7 | fermo-copertura | 52.134 | 5.246 | 7 |
| riavvio | 52.082 | 5.246 | 6 | lettura-dati-ko | 51.806 | 5.219 | 8 |
| gol-precoce | 52.082 | 5.246 | 6 | firma-dopo-gol-decisivo | 52.170 | 5.267 | 9 |
| cashout-globale | 56.220 | 5.885 | 2 | firma-dopo-gol-decisivo-senza-chiusura | 52.170 | 5.265 | 9 |
| chiuso-fuori-app | 56.216 | 5.882 | 1 | uscite-in-perdita-firmate | 51.964 | 5.237 | 8 |
| | | | | uscite-automatiche | 51.959 | 5.236 | 8 |
| | | | | punteggio-ko | 52.133 | 5.245 | 6 |

Altri numeri dello stesso referto, scenario `base`: ordini reali piazzati 5, righe `mike_trades` scritte 5, fill 2 abbinamenti su 2 ordini per 22,63 EUR (prezzi 1,33 e 1,71), **P&L del replay -14,17 EUR** (lordo = netto: commissione 0), conto Betfair
-14,17 = Mike -14,17 + utente 0,0, 601 giri dopo l'ultimo book, stato finale `SETTLED`, 1.703 book passati durante il bet delay, 1 ordine appoggiato ucciso dal passaggio in gioco (`LAPSE`), 1.862 letture a Betfair (0,35 per giro),
attivita': `uscita_proposta` x16, `uscita_proposta_decaduta` x14, `state` x7, `place_resting` x3, `loss_exit_deciso` x3, `place` x2, `rilettura_alla_riapertura` x2, `ordine_scaduto_alla_sospensione` x2; motivo piu' frequente «tengo» x2.347. Il P&L -14,17 compare in
9 scenari; gli altri valori del referto: -10,00 (2), -2,05 (2), -0,23, -0,68, -2,01, -2,11, -11,88, -14,04, +0,00 (2). Con `--trasporto canale` lo stesso `base` da 56.146 tick e 5.879 decisioni (`mike_base_riavvio_stantio_MASTER_parita.txt`,
`mike_coperture_INTEGRATA.txt`): **i numeri sono confrontabili solo a parita' di comando e di trasporto**.
Sintetiche (`mike_sintetiche_INTEGRATA.txt`): `reingresso` 3.236 tick / 1.618 decisioni / 6 azioni; `reingresso_2gol` 3.236/1.618/6; `prezzo_migliore` 3.240/1.620/3; `ultimo_ingresso` 3.238/1.619/5; `ultimo_ingresso_riprova` 3.238/1.619/5; 97,4 s in tutto.
Tempi: 728,4 s per la batteria piena, 1m32,5s per `base` (563 tick/s) - l'obiettivo dello standard e' 300 s.

### 5.3 Voci di `PROCESSO_STANDARD_BOT.md` coperte

- **§6.1** dati di mercato (stream registrato, `book arrivati in ritardo` 560.388): coperta dal replay. **§6.2** scanner/feed vero (`righe di scan scritte dallo SCANNER VERO` 2.344): coperta. **§6.3** servizio intero a cadenza reale (601 giri a mercato chiuso, stati visti/mai visti): coperta per i 14 stati su 21 visti sulla registrazione (10 nel solo `base`); **NON** per i 7 mai visti (D11, coperti solo dalle sintetiche).
- **§6.4** ciclo di vita dell'ordine con parziali e bet delay (J1-J6, K1-K4, S1-S4, CP1-CP4, R1-R3, KG1): coperta. **§6.5** persistenza e UI (RG1 e fotografie UI): coperta per la persistenza; la UI dipende dalle fotografie della tappa. **§6.6** concorrenza: parziale (un solo giro per volta nel banco). **§6.7** scenari e falsificazione: 26 + 5, falsificazione da rifare per OGNI test nuovo (regola 4 dello standard). **§6.8** referto riproducibile: coperta (comando, versioni, impronta del codice). **§6.9** velocita': NON rispettata (728 s, D13).
- **§7 catalogo** (numeri dell'elenco 1-37): n.1/3/9 (chiavi e campi, `getattr` su dict): K1-K4; n.2/10 (`res.ok`, enum stato): K2; n.4/5/6/7 (ref e riconciliazione, `bet_id`): K3, K4; n.8/15/31 (fill a mano, snapshot a mano, copie di laboratorio): vietati dal banco comune (stesso scanner e flumine veri); n.12/13/14 (bet delay, resting, FOK): bet delay e LAPSE misurati nel referto; n.16 (falso positivo del controllo); n.17 (sospeso/chiuso: `stato_mercato` 603, R1); n.19 (stato in RAM perso al riavvio): scenario `riavvio`; n.21 (paper+live sommati): `posti_occupati_per_modo`, aggregati per modalita' - da coprire con una fotografia UI; n.22 (riparte da solo): `ferma_al_nuovo_avvio` 3964; n.23/24 (stats, RPC `activate`): `mike_stop`/`mike_activate` SQL, da fotografare; n.27-30,35 (finti, test passa a vuoto, mutazioni): regola di falsificazione nella tappa; n.32 (PARTIAL contate come complete): il referto dichiara «COMPLETE x1»; **n.33 (costante nel frontend che duplica il backend): E1 D9**; n.34 (fase di protezione dopo la riconciliazione): la copertura e' sempre automatica (E1-029); n.36 (difetti di consapevolezza): K1-K4 e CP1-CP4; n.37 (pool di processi): il banco isola i replay. Il dettaglio di quale numero richiede la mia lettura riga per riga del catalogo non e' stato riletto qui oltre l'elenco: **la copertura §7 va ricontrollata punto per punto in sede di tappa**.

---------------------------------------------------------------------------------------------------------------------------------

## 6. MIGRAZIONE

Ordine nel piano: dopo D (runtime con pilota Omega, `D` §6), C (porta unica), F (regolamento) e G (DB): Mike NON e' il primo bot da migrare (poco traffico, ma il piu' costoso in soldi veri: live REST senza motore).

1. **Passo 0 (adesso, a costo zero, senza toccare Mike)**: ririlasciare il baseline su `HEAD` (D12) con `certifica mike 35760084 --scenari tutti` (durata ~12 min: **da dichiarare all'utente prima di lanciarlo** e da ridurre prima, D13) e conservare l'uscita; scrivere l'impronta (`e1_impronta_strategia.py scrivi` e' gia' stata scritta su `e5f4c1e3`). Tutto il resto confronta con questo.
2. **Passo 1 - parametri generati**: `PARAM_SPEC` come unica definizione; il TS (`MIKE_PARAM_FIELDS`, `MIKE_PARAM_DEFAULTS`) e il catalogo del replay si generano, con il test «TS allineato» rosso se diverge. Nessun cambio di valore (prima si decide D7 con l'utente).
3. **Passo 2 - strategia spostata**: `engine.py/feed.py/dossier.py` in `bots/mike/strategia/`; `regole_di_conto.py` estratto da `service.py:4116-4211` come funzioni pure con test propri. Confronto delle impronte: 386 voci + le nuove. Nessuna modifica di contenuto.
4. **Passo 3 - ombra**: il plugin `Decisore` di Mike gira in PARALLELO al servizio vecchio, in sola decisione: ogni giro le due `Decision` si confrontano (stesso `ctx`, stesso `snap`) e ogni differenza e' un allarme; periodo: almeno una giornata di partite in gioco (le 4 sintetiche non bastano, D11). Non piazza ordini.
5. **Passo 4 - taglio per modalita'**: prima **paper** sul runtime comune e sulla porta C (ordini via canale), poi **live** SOLO con l'ordine esplicito dell'utente e dopo avergli ricordato lo stato di certificazione sul replay (regola 1 dello standard). Mike live passera' dalla porta unica: significa che per la prima volta un ordine live di Mike passa dal motore del runner e dal suo diario (C §1: oggi non lo fa).
6. **Passo 5 - taglio del vecchio**: spegnere `service.py` solo quando il confronto in ombra ha 0 differenze e il replay a 26 scenari + 5 sintetiche e' identico riga per riga.

**Rischi**: (a) live = REST diretto oggi, domani porta C: e' il cambio piu' pericoloso (bet delay, `customerOrderRef` `mike-t<id>`, kill-switch); (b) il reparto di strategia nei punti «da indice» (E1-031) ha corpi non riletti; (c) lo stato in `mike_events.ctx` deve restare leggibile dalla nuova versione (n.18/19 del catalogo); (d) la UI legge JSON di `mike_events` con le chiavi attuali (`live`, `ctx`, `positions`, `dossier`: `mike.ts:175-330`): il codec deve mantenerle. **Ritorno indietro**: finche' il servizio vecchio non e' cancellato, l'interruttore del plugin e' il solo cambio; il vecchio resta avviabile; nessuna migrazione SQL distruttiva (le applica l'utente).

---------------------------------------------------------------------------------------------------------------------------------

## 7. MISURE

| Grandezza | Oggi (fonte) | Obiettivo dopo | Strumento |
|---|---|---|---|
| Richieste al DB, riposo | **48,0/min** (p95 54), `07` §4.2; 10,4/min per ciascuna delle 4 tabelle | **<= 5/min** (controllo e richieste dal canale locale, D-021/D-034; `get_mike_aggregates` a cache; le altre a evento) - ipotesi da confermare con D/I/G | `m04_chiamate_db.py` su una sessione senza eventi |
| Richieste al DB, fretta (partite in gioco) | **251,9 (02/10) - 256,1 (04/10)/min**; `mike_trades` 107,8 | **<= 40/min** (nessuna lettura di trade per giro: stato in RAM + eventi di fill) | idem, su un giorno di partite |
| Giri a riposo | 12/min (5,8 s) | invariati o a evento (la cadenza `idle_cycle_s` non e' strategia ma e' un parametro dell'utente: non si cambia il default senza dirlo) | `statistiche_sveglia` (`service.py:6973`) |
| Latenza messaggio -> decisione | non misurata per Mike; D lo dichiara per i 3 bot a polling (`D` §1.5: il DB sta fra feed e decisione) | stream in-process: «nessuna rete tra messaggio e decisione» (§9.3 del brief) | `ricevuto_ms - ts_pub_ms` (`service.py:7274`, brief `07`) |
| Righe Python (non test) | 17.755 + 3.197 tools = **20.952** | **~12.750** (-39%); guscio 8.727 -> ~2.350 (-73%) | `git ls-files | wc -l` per cartella |
| Righe frontend specifiche | 5.401 | ~4.700-5.000 | idem |
| Strategia | 6.844 righe, 386 impronte | **identiche** | `e1_impronta_strategia.py confronta` = 0 |
| Parametri: definizioni a mano | 3 (Python, TS campi+default, hint) | 1 (Python); gli altri generati | test «TS allineato» |
| Parametri senza effetto | 2 (D7) | 0 o dichiarati | `e1_tabella_parametri.py` colonna «NESSUNO» |
| Differenze Python/TS (default, limiti, scelte) | 0 (verificato, 107 parametri) | 0, mantenuto da un test che fallisce se divergono | `e1_parametri_py_vs_ts.py` |
| Tempo del banco, batteria piena | 728,4 s (12m08), 26 replay | **<= 300 s** (tetto 600) | `certifica` (riga `TEMPO TOTALE`) |
| Copertura di stati reali | 14 su 21 stati visti sulla registrazione `35760084` (tutti gli scenari); 7 mai visti | tutti, con registrazioni aggiuntive | riga `STATI MAI VISTI` del referto |

---------------------------------------------------------------------------------------------------------------------------------

## 8. CRITERIO §9.1 - «per sostituire Mike»

**OGGI tocco** (tutti insieme, perche' il guscio non ha un contratto): i 9 file di `Betfair/mike/` (17.755 righe) + `tools/` (3 file, 3.197) + 99 file di test (28.605); `registro_bot.py:219-243`; `avvio_app.py:173-215` (conosce Mike per nome); `certifica.py` e `banco_comune.py` (firme di `mike/db.py`) e il catalogo generato del replay; `omega_market.py` (ordini veri) e `omega_db.py` (tabella empirica) da cui Mike importa; `safe_strategy/db.py:307` (legge `mike_events`); `Betfair/stream/canale_bot.py` e `local_channel.py` (porta 47333, topic `mike_attivita`); 11 file SQL `migrations/*mike*`; e nel frontend `lib/mike.ts`, `pages/Mike.tsx`, 9 file di `components/mike/`, + i 92 file non-test che nominano Mike (Control Room, interruttori, storico, cash out) e `App.tsx` (rotta).

**DOMANI tocco solo** la cartella `bots/mike/` (strategia invariata, `parametri.py`, `plugin.py`, `banco/`, `tests/`) + `frontend/src/bots/mike/` + i suoi test di contratto (`COSA_FA.md`, catalogo, uscite di serie MANUALI, stato ricostruibile, fasi gestite: D §4.6). Registro, avvio, menu del banco, foglio parametri, Control Room, SQL dei controlli si DERIVANO dal `Plugin` e dal suo catalogo: niente piu' «Mike per nome» in `avvio_app.py`.

---------------------------------------------------------------------------------------------------------------------------------

## DECISIONI PER L'UTENTE

1. **D7, due parametri morti** (`ko_green_retry_s`, `event_loss_cap_pct`): toglierli dal foglio (restando accettati dal backend per i salvati) o lasciarli etichettati. Il «cap perdita per partita» e' un'attesa dell'utente che il codice non soddisfa: vuoi che diventi attivo? (cambierebbe la strategia: va deciso da te).
2. **D8, `last_entry_ticks_above`**: il motore lo legge (`engine.py:3877-3879`) e l'etichetta dice «NON ATTIVO»: quale delle due e' la verita' voluta?
3. **Prima di toccare qualunque cosa di Mike**: autorizzare il replay baseline su `HEAD` (12 minuti, sopra il tetto di 10: prima il banco va reso piu' veloce, standard §6.9) e il reperimento di registrazioni COMPLETE aggiuntive con re-ingresso, ultimo ingresso e seconda entrata (D11): senza di loro la parita' di Mike resta a UNA partita.
4. **Live di Mike dalla porta unica**: oggi il live non passa dal motore (REST diretto, nessun diario). Va deciso se il cambio avviene PRIMA o DOPO l'unificazione della porta (C), perche' sposta il rischio piu' alto della migrazione.
5. **Giri a riposo**: i 48 richieste/min a riposo non sono un errore; ridurli (canale locale al posto del polling) NON cambia la strategia. Conferma che puo' entrare nel piano D/I senza un tuo ordine specifico, oppure vuoi vedere il confronto prima.

## COSA HO VERIFICATO DI PERSONA / COSA NON HO POTUTO VERIFICARE

**Verificato (letto o misurato con strumenti statici)**
- Le righe di tutti i file di §Perimetro (`wc -l`) e le somme (17.755; 5.401).
- Il perche' del calo 255 -> 48: codice (`service.py:7471-7519, 4255-4264`, `config.py:87,350`), `git log` dei 4 file di Mike e `git log -S idle_cycle_s`, e le tabelle di `m04_chiamate_db.txt`/`07` §4.1-4.2 (frequenze e tipo di sessione). Il collegamento con le partite in gioco e' ricavato dai tipi di sessione e dal codice, non da una lettura di `mike_events`.
- Le citazioni di strategia di §2.1 (engine 1345-1356, 1416-1478, 1517-1555, 1558-1599, 2230-2275, 2493-2640, 3089-3144, 3153-3413, 3417-3480, 3484-3614, 3617-3954, 4009-4314, 4329-4461, 4468-5316) sono state lette riga per riga nei punti citati; per le funzioni marcate «da indice» ho letto solo l'intestazione.
- I 107 parametri, i loro limiti e default (Python e TS) con `e1_parametri_py_vs_ts.py` (0 differenze di default, limiti e scelte, dopo la correzione del 08/10 per i letterali `100_000`) e la lettura delle chiavi con `e1_tabella_parametri.py` (2 chiavi mai lette).
- L'impronta della strategia: 386 voci, 0 differenze alla rilettura immediata.
- I numeri di parita' di §5.2 sono copiati dai referti `AUDIT_2026-10-02/replay/mike_tutti_MASTER_FINALE.txt`, `mike_sintetiche_INTEGRATA.txt`, `mike_coperture_INTEGRATA.txt`, `mike_base_riavvio_stantio_MASTER_parita.txt`.

**Non verificato**
- Nessun replay e nessuna suite sono stati rieseguiti (regola del brief comune): i numeri di §5.2 sono del 02/10 e il codice e' cambiato dopo (D12).
- Il corpo di `_ultime_guardie`, `_guardia_minimo_listino`, `_controllo_di_piatto`, `_dichiara_residuo`, `_decide_flatten` 2673-2814 e le funzioni di contabilita' 760-1340: non rilette; i corpi di `service.py` sono stati classificati per nome e docstring (strumento) e non letti per intero (sono 7.551 righe).
- Il numero di tipi di attivita' scritti dal backend (51) e' una regex su `service.py` (`db.log("...")` e `_log_throttled`): potrebbero essercene altri scritti per altre vie.
- La comparazione con le funzioni di flumine/betfairlightweight (§4.5): nessuna lettura della documentazione, nessuna rete.
- Il conteggio dei file Python di produzione fuori da `Betfair/mike` che nominano Mike: non fatto (il primo tentativo era inquinato dagli script di audit); la lista in §8 e' quella dei punti che ho incontrato.
- La stima del -73% di guscio e del -39% totale dipende dalle schede C, D, F, G, H: sono ipotesi calcolate qui sopra, non misure.
