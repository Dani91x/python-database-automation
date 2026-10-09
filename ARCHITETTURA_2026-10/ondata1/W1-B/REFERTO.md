# REFERTO W1-B - comparto B, stato della partita calcolato UNA volta (ondata 1, 09/10/2026)

Ramo `architettura/w1-b` da `559a96df`. Agente W1-B (Opus). Nessun file esistente modificato: solo file nuovi
del dominio (`Betfair/nucleo/stato_partita/{calcolo,freschezza,servizio}.py`, `adattatori/*.py`,
`tests/test_b_*.py`, `doc/B_STATO_PARTITA.md`, questo referto). Nessuna rete, nessun DB, nessun processo nuovo;
nessun replay del banco salvo la parita' per tick chiesta dal brief (servizio PASSIVO sul banco comune).

## 1. Cosa ho costruito e cosa NON fa

| File | Righe | Punti chiave |
|---|---|---|
| `calcolo.py` | 408 | `stato_calcio_da_grezzo` :181 (parse_score_dict + tempo_da_stato_ips + mission_phase), `stato_calcio_da_riga` :203 (numeri della riga che i bot leggono), `stato_calcio_da_api_football` :254 (fase DEDOTTA come Omega, seconda revisione), `StatoPartitaEsteso` :89, `punteggio_tennis` :293 (parser con la guardia del runner), `stato_tennis_da_grezzo` :304 / `_da_riga` :327, `chiave_tennis` :285, `fase_partita` :142 / `fase_come_omega` :156, `ko_epoch_ms` :343, `KoPerMercato` :368 (`dimentica` :376), `KoUnico` :397, `ko_ms_intero` :361, `minuto_da_orologio` :163 |
| `freschezza.py` | 91 | SOLO eta': `eta_riga_s` :46 (= `row_age_sec`), `eta_punteggio_s` :53 (= `score_age_sec`), `eta_scanner_da_stato_s` :60, `calcola_eta` :76. Nessuna soglia (U-08, contraddizione 4) |
| `servizio.py` | 525 | `ServizioStatoPartita` :268 (`segui` :300, `stato`/`stato_a` :320/:324, `istante_dato_s` :336, `iscrivi` :341, `iscrivi_eventi` :344, `osserva_book` :360, `aggiorna` :382 con `_calcola_uno` :413 e `_senza_dato` :446, `prezzi_vivi` :465, `avvia`/`ferma` :482/:504), `stato_da_lettura` :154, `esito_flusso` :143 (= `flusso_prezzi.valuta`), `eventi_fra` :213, eventi :79-127 |
| `adattatori/lettura.py` | 52 | la busta comune di ogni `FonteStato.leggi` |
| `adattatori/ips.py` | 139 | `FonteIpsScanner` :52 (righe senza filtro), `FonteIpsRunner` :85 (regola del runner: `fresh_payload` poi IPS diretto; fonte vera per evento) |
| `adattatori/ips_tennis.py` | 81 | `FonteIpsTennisRunner` :37 (strada di `score_and_now_worker`) |
| `adattatori/api_football.py` | 127 | `FonteApiFootball` :41, `FonteCircuitoCalcio` :84 (UN `ScorePoller` di oggi per evento, U-10 invariata) |
| `adattatori/registrazione.py` | 89 | `FonteRegistrazione` :38 (`carica_punteggi` del banco, `bisect_right` come `_replay_evento`) |
| `adattatori/canale.py` | 59 | `FonteCanale` :32 (righe, battito e stato dal `ClientScan` di oggi, nessuna SELECT) |

NON fa: nessuna soglia di freschezza (restano nei file dei bot); nessuna scrittura (`live_now`, `tennis_live_now`, canale
47332 restano al codice di oggi); nessun poll batch dello scanner (B-017, lato scanner per ultimo); nessuna timeline
(B-006, B-019, B-020, B-025); nessuna decisione. Importare il comparto non apre file, socket o thread (provato).

## 2. Contratto

Implementati: `StatoPartitaService` (`ServizioStatoPartita`, stesse firme: `test_rispetta_il_contratto`), `FonteStato`
(6 adattatori). `StatoPartita`, `Eta`, `TennisSet` usati come sono. Contratto NON modificato.

Estensioni (in file miei, proposte per il contratto):
0. (seconda revisione) `calcolo.StatoPartitaEsteso(StatoPartita)` con `fase_dedotta: bool = False`: la fase NON e'
   letta da uno stato del fornitore ma dedotta dal minuto (ripiego API-Football). Proposta: campo nel contratto.
1. `iscrivi_eventi(cb)` con `StatoCambiato`, `GolSegnato`, `FaseCambiata`, `FlussoInterrotto`, `FlussoRipreso` (il
   contratto li nomina in commento; qui sono classi). `GolSegnato` solo se il totale SALE fra due stati noti.
2. `osserva_book(event_id, market_book)`: KO e "in gioco" per le fonti senza riga (IPS diretto, ripiego).
3. `prezzi_vivi(event_id, mercati)`: la cond. 11 per i mercati di una decisione (ogni bot passa i suoi, come oggi).
3-bis. (correzione) `stato_a(event_id, adesso_s)` e `istante_dato_s(event_id)`: eta' oneste e istante dell'ultimo dato.
4. La busta di `leggi` (`adattatori/lettura.py`) con `trasporto` (`db`/`canale`/`http`/`file`) e `origine`.
5. Proposte di tipo: `FasePartita` e' solo calcio (il tennis resta `sconosciuta`; proporrei `in_corso`);
   `TennisSet` dichiara `int`/`str` ma il parser di oggi produce anche None (un lato assente): lo stato li porta
   TALI E QUALI (nessun valore inventato), il tipo andrebbe `Optional`.

## 3. Parita'

Arbitri importati nei test, mai copiati. "Ingressi veri": i due sidecar `.scores.jsonl` (220 righe: 96 + 124) e i
`MarketBook` VERI di betfairlightweight dalle due registrazioni; per tick: lo SCANNER VERO del banco comune.

| Funzione di oggi (file:riga) | Nuova | Test | Esito |
|---|---|---|---|
| `parse_score_dict` (`betfair_inplay.py:50`): minuto, gol, rossi, corner, gialli | `stato_calcio_da_grezzo` | `test_parita_ogni_riga_dei_sidecar_con_parse_score_dict` + 14 casi limite | **220/220 righe identiche**; 14/14 casi |
| `tempo_da_stato_ips` (`atlante_v4.py:550`) | `tempo_partita` | `test_parita_ogni_riga_tempo_e_fase` | **220/220** |
| `mission_phase` (`omega_engine.py:866`) come `_ht_ancora_in_gioco` (`omega_service.py:945`) | `fase_partita` / `fase_come_omega` | idem | **220/220** |
| numeri registrati dal runner nel sidecar (`runner.py:384-405`) | stato col parser della SUA fonte | `test_le_righe_registrate_dicono_la_loro_fonte` | **220/220** (207 IPS, 13 API-Football) |
| `parse_fixture_response` (`api_football.py:34`) | `stato_calcio_da_api_football` | idem + `test_api_football_fase_e_tempo_dal_solo_minuto` | 13/13 |
| riga dello scanner (`apply_score_state`, `service.py:1777`) e `tempo_da_payload` (`atlante_v4.py:588`) | `stato_calcio_da_riga` | `test_b_parita_banco` (cert) | **17.796/17.796 giri identici** (6.076 + 11.720) |
| `flusso_prezzi.valuta` (`flusso_prezzi.py:218`) per tick, anche con i mercati di una decisione (MO + CS) | `StatoPartita.prezzi_vivi`, `prezzi_vivi` | `test_b_parita_banco` | **17.796/17.796 Esito identici** (campo per campo, testo compreso); esiti "fermi" sollecitati: 3 + 20 |
| `ScanFeedScoreProvider.score_age_sec` (`scan_feed.py:506`) | `eta_punteggio_s` | `test_b_parita_banco`, `test_punteggio_s_e_score_age_sec` (14 eta') | **17.796/17.796**; 14/14 |
| `row_age_sec` (`scan_feed.py:440`), `scanner_age_sec` (:324) | `eta_riga_s`, `eta_scanner_da_stato_s` | `test_b_freschezza` | 14/14, 5/5; per tick 17.796/17.796 |
| `ScanFeedScoreProvider.get_score` (`scan_feed.py:524`: `fresh_payload` + diretto) | `FonteIpsRunner` | `test_runner_sceglie_come_scan_feed` | **56/56 casi** (stessa strada, stessi contatori, stesse chiamate, stesso snapshot) |
| `ScorePoller.poll` (`poller.py:75`) con `ApiFootballProvider` | `FonteCircuitoCalcio` | `test_circuito_identico_al_poller_di_oggi` | 9/9 passi (circuito chiuso, ripiego prima della soglia, aperto, half-open, rientro) |
| `score_and_now_worker` strada del punteggio (`tennis_runner.py:1631-1653`) | `FonteIpsTennisRunner` | `test_tennis_feed_diretto_errore` | feed, diretto (id numerico), errore, id non numerico |
| `parse_tennis_scores` (`tennis_score.py:131`), `TennisScore.key()` (:63), `point_pressure` (:113) | `stato_tennis_da_grezzo`, `chiave_tennis` | `test_tennis_chiave_e_pressione_uguali_al_parser` | 9/9 casi costruiti; **parita' su registrazione tennis: ⊘** (le registrazioni tennis NON sono nel cloud: T0B (5), le porta il PC) |
| `_ko_epoch_ms` x4: `scalper_bot.py:788`, `tennis_scalper_bot.py:804`, `sniper_bot.py:295`, `media_under_bot.py:1020` | `ko_epoch_ms`, `KoPerMercato` (1-3), `KoUnico` (4) | `test_ko_identico_alle_4_copie_sui_book_veri`, `test_ko_bordi_*` | **>10.000 MarketBook veri, >=20 mercati: 4/4 copie identiche**; 7 bordi (anche con fuso del processo Europe/Rome); `float(ko_ms) == ko` sul 100% |
| `minute_from_clock` (`omega_engine.py:932`) | `minuto_da_orologio` | `test_minuto_da_orologio_e_quello_di_omega` | 7/7 |
| `carica_punteggi` + `bisect_right` (`banco_comune.py:3040, :3235`) | `FonteRegistrazione` | `test_registrazione_scorre_come_il_banco` | 220/220 record, ritardo aggiunto dichiarato |
| `in gioco` del runner (`runner.py:358-363`) | `osserva_book` | `test_osserva_book_ko_e_in_gioco_dai_book_veri` | identico su 3.273 giri (65.445 book veri, uno ogni 20 + l'ultimo; False e True visti) |

I 9 punti di ricalcolo del minuto (scheda B par. 3.3) e come li copre lo stato:
1. `parse_score_dict` -> `StatoPartita.minuto` (fonte grezza) - identico;
2. `minute_from_clock` -> `minuto_da_orologio` (ripiego a orologio, resta di Omega) - identico;
3. `estimate_minute` (`omega_service.py:2441`): usa `minute` dello snapshot se fresco, altrimenti 2 -> il minuto che legge e'
   quello di 1; la freschezza `_is_fresh` resta in Omega (U-08);
4. `tempo_da_stato_ips` -> `StatoPartita.tempo` - identico;
5. Safe `_fase_da_scan` (`engine.py:789`) = 4 sulla riga con `score_raw` (identico per tick); senza `score_raw` Safe da'
   None, l'atlante deduce dal minuto: divergenza teorica (sotto), 0 casi nelle registrazioni (la riga ha sempre
   `score_raw` quando ha il minuto);
6. Omega `_ht_ancora_in_gioco` + `mission_phase` -> `StatoPartita.fase` - identico;
7. `sniper_bot._minute` (:632), `theta_bot._match_minute` (:535): leggono `live_minute` (= minuto di `live_now` = 1) e
   ripiegano sull'orologio dal KO: il loro ingresso e' `StatoPartita.minuto`/`ko_ms`; il ripiego resta nella strategia;
8. osservatori dello scalper (`scalper_session.py:1734-1925`): leggono `live_now.minute` (= 1) ogni 15-20 s: domani
   `iscrivi` (U-11, non deciso: oggi non agganciati);
9. `curator._minute_at` (`curator.py:82`): offline, ultimo minuto della timeline: resta alla registrazione (fuori ondata 1).

## 4. Migliorie misurate

Nessuna dichiarata sul risultato (zero cambi di valore). Strutturali, misurabili solo in ombra: `iscrivi` sveglia in
processo (0 SELECT per chi legge, contro 1 SELECT/s per processo e i 3 SELECT `live_now` dello scalper oggi); `fonte` vera
per evento (oggi "betfair" per feed e diretto). Tempi dei test (questa macchina, condivisa): non-cert ~45 s; cert ~150 s.

## 5. Test e falsificazioni

- Test del comparto: **151 non-cert verdi** (calcolo 38, freschezza 38, adattatori 65, servizio 9, import 1) + **2 cert
  verdi** (per tick, 150 s).
- Falsificazione: **29 mutazioni, 29 rosse** (`python ARCHITETTURA_2026-10/ondata1/W1-B/mutazioni.py <radice>`; per ogni mutazione: sostituzione esatta, test del
  file, ripristino, sha256 identico prima/dopo verificato per tutte e 29). Le 4 della scheda B par. 5:
  (1) `riga_s` sempre 0 -> ROSSO (`test_feed_stantio_ha_l_eta_vera`); (2) ritardo IPS tolto -> ROSSO
  (`test_punteggio_s_e_score_age_sec`); (3) scanner vivo tolto da `fresh_payload` nell'adattatore -> ROSSO
  (`test_zero_a_zero_fermo_con_scanner_vivo_resta_sul_feed`); (4) dato assente letto come fresco -> ROSSO
  (`test_dato_assente_non_e_zero`). Le altre 25: stato da `status`, intervallo come 2t, supplementari non distinti, tempo
  senza minuto, rossi scambiati, minuto della riga ricalcolato, cache KO per mercato tolta, cache unica diventata per
  mercato, naive non UTC, pressione tennis falsa, chiave tennis senza servizio, gol anche quando scende, firma con le eta',
  flusso senza istante, mercati ignorati, callback che ferma gli altri, in gioco dal book ignorato, `ferma` senza join,
  `bisect_left`, ritardo ignorato, battito ignoto = 0, circuito che etichetta tutto `ips_scanner`, contatore del
  diretto, id tennis non convertito, `betfair_inplay` importato in testa (socket all'import).
  Tre mutazioni erano sopravvissute al primo giro (cache del None, naive con fuso UTC della macchina, firma con le eta'):
  la prima era equivalente (sostituita con una non equivalente), le altre due hanno portato a test piu' forti (fuso
  Europe/Rome nel test dei bordi; giro con solo il tempo che passa).
- **5-bis Falsificazione a livello di banco** (`mutazioni_cert.py`, test cert per tick, stesso metodo, sha256 uguale dopo ognuna):
  ritardo IPS tolto -> ROSSO su 35760084 (65 s); stato dello scanner ignorato nella cond. 11 -> ROSSO su 35797769
  (290 s, macchina condivisa); minuto della riga ricalcolato dallo `score_raw` -> VERDE: mutazione EQUIVALENTE sui dati
  veri (sulle due registrazioni `payload.minute` e `score_raw.timeElapsed` coincidono su 17.793 giri su 17.793 con
  `score_raw`), presa dal test unitario `test_riga_dello_scanner_usa_i_numeri_che_i_bot_leggono` (riga con 62 contro 61).
- **5-ter Suite intera** (`python -m pytest Betfair/ -q -p no:cacheprovider`, UNA volta, sul codice finale di questo
  ramo, test cert compresi): **11.667 verdi, 0 rossi, 87 saltati, 6 xfailed, 689,9 s**. La seconda esecuzione non e'
  stata necessaria: dopo la prima sono cambiati solo questo referto, il doc e due caratteri di una docstring di
  `adattatori/canale.py` (virgolette non ASCII -> ASCII), con i test del comparto rilanciati: 151 non-cert verdi.

## 6. Funzionalita' coperte (01_FUNZIONALITA.md)

Coperte con test (dettaglio in `doc/B_STATO_PARTITA.md` par. 5): B-001..B-005, B-007..B-016, B-018, B-030..B-032,
B-034 (strada del punteggio), B-036/B-037 (valuta), B-044, B-045, B-047, B-049 (lettura), B-050, A-082, A-083, D-014,
D-017 (parte), D-020, E3-S08 (lettura del segnale), E5-060, E5-061.
Restano al codice di oggi: B-006, B-017, B-019..B-029, B-033, B-035, B-038..B-043, B-046, B-048, B-051..B-053, A-070,
D-015, D-016, E3-S07, G-011 (scritture, scanner, timeline, involucri e soglie dei bot, osservatori dello scalper).

## 7. PROCESSO_STANDARD_BOT par. 6 / 7

| Voce | Stato |
|---|---|
| 6.1 punteggi dal sidecar con il ritardo di produzione | SOLLECITATA: `FonteRegistrazione` usa `ts_ms` (ricezione del runner: ritardo IPS gia' dentro) e `ritardo_s` aggiuntivo dichiarato come il banco; per tick l'iniezione e' quella del banco (`apply_score_state` a `ts_ms`); `punteggio_s` = riga + 3 s. Formato nativo, qualita' COMPLETE delle due registrazioni |
| 6.2 scanner vero, freschezza, dato assente non e' zero | SOLLECITATA: scanner VERO del banco per tick; `riga_s`/`scanner_s` separati; riga senza `updated_at` = None (falsificazione 4) |
| 6.3 servizio intero a cadenza reale | parziale: il servizio gira alla cadenza del banco (1 s di mercato); ⊘ per i bot (non agganciati in ondata 1) |
| 6.4 ciclo di vita dell'ordine | ⊘ (il comparto B non piazza) |
| 6.5 persistenza e UI | ⊘ (nessuna scrittura in ondata 1; `live_now` resta al vecchio) |
| 6.6 concorrenza | SOLLECITATA per il servizio (aggiornata alla seconda revisione): lettura + calcolo serializzati sotto `_giro_lock`; callback MAI sotto un lock del servizio (coda + un solo consegnatore, ordine di calcolo, rientranza dallo stesso thread accodata); `avvia`/`ferma` sotto lock, una generazione per thread, `ferma` dal thread del giro senza `join` su se stesso; callback isolate (un'eccezione non ferma le altre); una partita rotta non ferma le altre (servizio e adattatori, log una volta al minuto). Test: lock invertito, rientranza, giri concorrenti, giro lento, `avvia` concorrenti, stress segui/iscrivi/aggiorna. ⊘ piu' partite su banco |
| 6.7 scenari: feed stantio, 0-0 fermo, flusso interrotto | SOLLECITATI in unita' (stantio 200 s, 0-0 fermo con scanner vivo/morto, `FlussoInterrotto`/`Ripreso`); per tick gli esiti "fermi" reali (3 + 20) |
| 6.7 falsificazione | 29/29 rosse + cert (par. 5-bis) |
| 6.8 referto riproducibile | comandi nel doc par. 8; numeri attesi fissati nei test (220 righe, 6.076 e 11.720 giri) |
| 6.9 velocita' | cert 150 s per due registrazioni intere (sotto il tetto) |
| 7 n.9, n.27 (finti con chiavi/tipi diversi) | evitati: `MarketBook`, `ScanRowCache`, `ScanFeedScoreProvider`, `BetfairInPlayProvider`/`APIClient`, `ScorePoller`, `ApiFootballProvider`/`APIFootballClient`, `ClientScan` VERI; sostituita solo la chiamata di rete, con dati veri dei sidecar; il `self` delle copie di `_ko_epoch_ms` ha il solo attributo letto, col tipo vero |
| 7 n.15 (snapshot di scan a mano) | evitato per tick (scanner vero); in unita' le righe hanno la forma vera della tabella |
| 7 n.21 (paper e live sommati, zero al posto di assente) | nessun aggregato; assente = None ovunque (coppie, eta', battito) |
| 7 n.28, n.29, n.35 (test sbagliati, a vuoto, mai rossi) | ogni test falsificato; contatori attesi fissati (righe, giri, esiti fermi > 0, contatori del circuito) |
| 7 n.32 (sidecar col nome sbagliato) | il nome lo sceglie `carica_punteggi` del banco (riuso) |
| 7 n.33 (costanti duplicate) | `IPS_SCORE_LAG_SEC`, `DEFAULT_MAX_AGE_SEC` letti da `scan_feed`, mai riscritti |
| 7 n.37 (cache di processo fra test) | la `shared_cache` di processo non si tocca nei test (cache iniettate); `PUNTEGGI_CANALE` tolto dall'ambiente nei test |
| altre voci di 7 (ordini, DB, UI) | ⊘: fuori dal comparto B |

## 8. Aggancio proposto (ondata 2)

Interruttore `ARCH_STATO_PARTITA=vecchio|ombra|nuovo` (letto a ogni giro, regola di `canale_bot.acceso`; di serie
`vecchio`). Un modulo `stato_partita/interruttore.py` (nuovo) lo legge. Ordine dei tagli (dal meno rischioso; il lato
scanner per ULTIMO perche' serve 4 bot, rischio a della scheda B):

1. **Runner calcio, ombra** - `Betfair/stream/runner.py:350` (dopo `snap = poller.poll(event_id)`): con `ombra` si
   costruisce la busta dallo stesso `snap` (nessuna chiamata in piu': `grezzo=snap.payload`, fonte da
   `poller.current_source` + delta di `feed_hits` del primario) e `stato_da_lettura`; a `:376-381` (prima di
   `update_live_now`) si confrontano `minute`/`score_home`/`score_away`/`inplay` con lo stato e si scrive la
   discrepanza nel log dell'ombra. Nessun SELECT di `live_now`: il confronto e' in processo, sugli stessi numeri.
2. **Runner tennis, ombra** - `Betfair/stream/tennis_live/tennis_runner.py:1652` (dopo `parse_tennis_scores`):
   `stato_tennis_da_grezzo` sullo stesso `raw`; confronto `chiave_tennis` con `ts.key()` e `point_pressure` prima di
   `:1685` (`upsert_tennis_now`).
3. **Lettori della riga (Omega, Mike, Safe), ombra** - `omega_service.py:8905` (`_build_score_lookup`),
   `mike/feed.py:425-475`, `safe_strategy/bot_service.py:3214,3409`: `stato_calcio_da_riga` sulla stessa riga;
   confronto minuto/gol/rossi/tempo/fase, `in_gioco` contro `payload.inplay` (non contro `live_now`, divergenza 9) e
   `prezzi_vivi` contro l'esito che il bot ha appena calcolato.
4. **Nuovo, runner calcio** - `runner.py:2203-2207`: `ScorePoller` -> `FonteCircuitoCalcio(FonteIpsRunner(...),
   provider_api_football)` dentro un `ServizioStatoPartita` per sessione; `score_worker` legge `stato()`.
5. **Scalper (U-11, solo con decisione dell'utente)** - `scalper_session.py:1734-1925`: i 3 osservatori diventano
   `iscrivi` sul servizio del runner.
6. **Lato scanner per ultimo** - `safe_strategy/service.py:1698-1905, 3258-3320`: il poll batch resta; l'applicazione
   dello stato passa da `calcolo` (stessi numeri: parita' per tick gia' provata).

Criterio "uguale o meglio" per passare da ombra a nuovo: 0 discrepanze su minuto/gol/rossi/fase/tempo e sull'esito del
flusso su N giornate vere (calcio, poi tennis) con le sole 3 tolleranze di U-59; `eta.punteggio_s` riportata in ogni
referto; tempi del giro non peggiori. Ritorno: interruttore su `vecchio`.

## 9. Divergenze per l'utente, rischi, dubbi

(Le voci 8-11 sono state aggiunte con le correzioni dopo la revisione, par. 10.)

Divergenze di OGGI (non scelte: lo stato riporta il valore di ciascun chiamante; test che le fissano):
1. **Fase di Omega contro tempo di Safe/Mike su uno stato vecchio**: 'KickOff' con `timeElapsed` 88 (caso 35833626):
   Omega `mission_phase` = '1t', atlante `tempo_da_stato_ips` = None ("non si sa"). `test_divergenza_kickoff_vecchio`.
   0 casi nelle due registrazioni (220 righe, 17.796 giri).
2. **`matchStatus` contro `status`**: Omega legge solo `matchStatus`; `parse_score_dict` e `tempo_da_stato_ips` ripiegano su
   `status`. Con solo `status`='FirstHalfEnd' al 47': tempo 1 (atlante), fase '2t' (Omega). `test_divergenza_solo_status_*`.
3. **Cache di `_ko_epoch_ms`**: `media_under_bot.py:1020` tiene UN KO per istanza (il primo, per qualunque mercato), le
   altre 3 copie uno per mercato. Tutte e 4 non seguono un KO spostato dopo il primo valore. `test_ko_bordi_*`.
4. **Righe di ripiego API-Football nel banco**: il banco passa il record API-Football al parser IPS (minuto None) mentre
   `live_now` aveva il minuto di API-Football: 3 righe su 220 (35760084 1'; 35797769 1' e 2').
   `test_divergenza_banco_live_now_sulle_righe_di_ripiego`.
5. **Safe senza `score_raw`**: `_fase_da_scan` da' tempo None (fail-closed), `tempo_da_payload` deduce dal minuto: 0 casi
   nelle registrazioni (lo scanner scrive minuto e `score_raw` insieme).
6. **`_is_fresh(None) = True`** (`omega_service.py:62-66`): resta in Omega (decisione B dec. 2 non presa); lo stato non
   tratta mai un dato assente come fresco.
7. **API-Football parte dopo UN fallimento** (`poller.py:81-82`, U-10): riprodotto identico.
8. **Fase dal ripiego API-Football** (riscritta nella seconda revisione: la prima versione diceva, SBAGLIANDO, che oggi
   nessuno la calcola). OGGI Omega la calcola: quando il punteggio arriva dal ripiego (`score_lookup` su `live_now`)
   `_live_state_for` torna `status=None` (`omega_service.py:1129-1139`) e la fase della missione e'
   `mission_phase(status=None, minute, kickoff=ev.open_date, now)` (`:1980`): 30'/45' = '1t', 67'/90' = '2t', cioe' una fase
   DEDOTTA dal minuto, che puo' essere sbagliata ('HT' al 45' = '1t', 'FT' = '2t' mai 'finita'). Le strategie non si
   alterano: lo stato restituisce la STESSA fase (funzione di oggi importata), marcata `fase_dedotta=True`
   (`StatoPartitaEsteso`), tempo None (Safe e Mike non leggono il ripiego). `FaseCambiata` scatta solo fra fasi LETTE (niente
   falso 'intervallo -> 1t' al passaggio al ripiego). Per l'utente, due possibili decisioni NON prese: (a) dichiarare
   'sconosciuta' la fase del ripiego (Omega cambierebbe condotta), (b) leggere `status.short` di API-Football (regola nuova).
   `test_api_football_fase_identica_a_mission_phase` (minuti 0, 30, 45, 46, 67, 90, 95, None x 3 istanti x 11 `status.short`),
   `test_passaggio_al_ripiego_non_inventa_fasi`, `test_fase_dedotta_non_fa_scattare_fase_cambiata`.
9. **"In gioco": riga dello scanner contro regola del runner**: la riga porta `payload.inplay` (cio' che leggono Mike,
   Omega, Safe); il runner calcio scrive `live_now.inplay` dai book (`runner.py:358-363`: un mercato CLOSED non e' in
   gioco). A mercato chiuso con la riga ancora `inplay=True` le due letture divergono. Lo stato: con un book osservato
   vince la regola del runner (il runner osserva sempre i book), senza book vale la riga (i bot lettori). L'ombra (par. 8)
   confronta il runner con `live_now.inplay` e i lettori con `payload.inplay`, MAI incrociati.
   `test_in_gioco_segue_il_book_quando_osservato`.
10. **Record con soli `timeElapsedSeconds`**: lo scanner calcola `minute` sul record intero (1500 s = 25') ma pubblica
    uno `score_raw` spogliato dei secondi (`strip_volatile_state`, `scanner.py:637`): chi legge la riga vede 25, chi
    riparsa lo `score_raw` (runner sul feed) vede None. 0 casi nelle registrazioni (17.793 giri con `score_raw`).
    `test_divergenza_record_con_soli_secondi`.
11. **Cache del KO senza tetto**: le 4 copie di `_ko_epoch_ms` non potano mai la cache per mercato (vita del bot). Il
    servizio pota la sua quando una partita esce da `segui` (`KoPerMercato.dimentica`); proposta per i bot che leggeranno
    `ko_ms` dallo stato: nessuna cache propria (o tetto ai mercati sottoscritti, 200 per sottoscrizione).

Rischi e dubbi:
- Il comparto importa funzioni pure da pacchetti di bot (`omega_engine`, `atlante_v4`, `tennis_score`): consentito come
  riuso, ma la regola 10 ("nessun comparto importa un bot") andra' chiusa col trasloco in T9.
- Lo stato tennis ha `fase='sconosciuta'` (il contratto non ha fasi tennis) e `TennisSet` puo' portare None (par. 2).
- `ko_ms` e' `int(round(float))`: identico sul 100% dei book veri (KO al secondo); un KO con frazioni di ms sarebbe
  arrotondato (le copie tengono il float: `KoPerMercato`/`KoUnico` lo restituiscono com'e').
- La parita' per tick usa la riga di stato dello scanner costruita dal suo blocco `flusso` di quell'istante (il banco non
  ha `safe_strategy_status`): `scanner_s` per tick e' quindi 0 per costruzione.
- Nessuna dipendenza nuova.

## 10. Correzioni dopo la revisione indipendente di `be3cf075`

Esito della revisione: DA CORREGGERE. Correzioni in un commit nuovo sullo stesso ramo (storia non riscritta). File
temporanei solo in `scratchpad/w1b/`.

| # | Difetto | Correzione | Test (falsificato) |
|---|---|---|---|
| 1 | ALTA: `mutazioni.py` nel referto era lo script di W1-G2 (lo scratchpad condiviso l'aveva sovrascritto prima della copia) | script VERO ricostruito: le 29 mutazioni di B (righe adeguate al codice corretto) + 17 nuove per le correzioni | `python ARCHITETTURA_2026-10/ondata1/W1-B/mutazioni.py .`: **46/46 ROSSE**, sha256 uguale dopo ogni ripristino (`calcolo` `37c0e16a53cb`, `servizio` `cdd462d874a5`, `freschezza` `bce82b0608e7`, `ips` `5e3148fc87f7`, `registrazione` `3bad506c8758`, `canale` `32053b612eb7`, `api_football` `a429d08b6ba0`, `ips_tennis` `c73030e5cb35`) |
| 2 | ALTA: un'eccezione nel calcolo di UNA partita (es. tennis con `score` stringa/lista: `parse_tennis_scores` solleva `AttributeError`) faceva perdere per sempre gli eventi delle partite gia' calcolate e bloccava le successive | guardia sul parser tennis come nel worker del runner (`calcolo.punteggio_tennis`: record rotto = nessun punteggio, motivo nel log); guardia PER PARTITA in `_calcola_uno` (log al piu' una volta al minuto per partita con `flusso_prezzi.Promemoria`, la partita resta com'era, le altre proseguono) | `test_tennis_malformato_vale_nessun_punteggio_come_il_runner` (2 forme), `test_calcolo_che_solleva_non_perde_gli_eventi_delle_altre` |
| 3 | MEDIA-ALTA: eta' congelate quando la fonte tace (dopo 600 s `riga_s` restava 1,0) | `stato()` ricalcola eta' e verdetto del flusso all'istante della chiamata dall'ultimo dato (`stato_a` per un istante dato); `istante_dato_s` esposto (fonti senza riga: eta' None come oggi); tennis con la fonte muta = senza punteggio, come `strat.score = None` del runner tennis | `test_eta_crescono_quando_la_fonte_tace` (601 s, flusso "scanner bloccato"), `test_diretto_senza_riga_eta_none_ma_istante_esposto`, `test_tennis_fonte_muta_toglie_il_punteggio_come_oggi` |
| 4 | MEDIA: fase da API-Football dedotta dal minuto (HT->1t, FT->2t...) e `FaseCambiata` falsa al passaggio al ripiego | fase 'sconosciuta' e tempo None dal ripiego; `FaseCambiata` solo fra fasi NOTE (confronto con l'ultima nota); divergenza 8 | `test_api_football_fase_sconosciuta_e_tempo_assente` (11 `status.short`), `test_passaggio_al_ripiego_non_inventa_fasi`, `test_servizio_con_busta_api_football` |
| 5 | MEDIA: `in_gioco` sul ramo feed seguiva `payload.inplay` e non la regola del runner | con un book osservato vince la regola del runner per ogni fonte; senza book la riga; divergenza 9 e criterio dell'ombra corretto | `test_in_gioco_segue_il_book_quando_osservato` |
| 6 | MEDIA-BASSA: `ferma` scaduto + `avvia` rianimava il vecchio thread; `avvia` fuori lock; giri concorrenti consegnati fuori ordine; `FlussoRipreso` spurio passando al diretto (NON_NOTO vivo=True) | una generazione per thread con il SUO stop e la SUA sveglia (`_Giro`), `avvia`/`ferma` sotto lock, `ferma` dice se il thread e' uscito; giro serializzato (calcolo + consegna) con un RLock; `FlussoInterrotto`/`FlussoRipreso` solo fra esiti NOTI (ultimo verdetto noto per partita) | `test_ferma_scaduto_poi_avvia_non_rianima_il_vecchio`, `test_riavvio_dopo_ferma`, `test_avvia_concorrenti_un_solo_thread`, `test_due_giri_concorrenti_consegnano_in_ordine`, `test_segui_iscrivi_aggiorna_concorrenti`, `test_nessuna_ripresa_senza_prova` |
| 7 | mutazioni sopravvissute al revisore | test nuovi: rigori/supplementari, firma con `set_game`, rossi, corner, gialli, servizio con busta API-Football e tennis, `ko_ms_intero` arrotondato (0,6 ms), casi strani del KO contro le 4 copie (date, int, NaN, Decimal, anno 1 e 9999, fuso +2), riavvio dopo `ferma`, potatura della cache del KO | `test_rigori_e_supplementari_sono_supplementari`, `test_cambia_solo_rossi_corner_o_gialli_e_lo_stato_cambia` (3), `test_ogni_punto_del_tennis_e_un_cambio`, `test_ko_arrotondato_non_troncato`, `test_ko_casi_strani_come_le_4_copie`, `test_segui_pota_la_cache_del_ko` |
| 8 | divergenze e limiti non scritti; il doc diceva "spento = codice di oggi" senza interruttore | divergenze 8-11 (par. 9); doc par. 6 corretto (l'interruttore non esiste ancora: nessun codice di produzione importa il comparto) e par. 9-bis | `test_divergenza_record_con_soli_secondi` |

Le prove del revisore (`test_rev_servizio.py`, `test_rev_parita.py`, `test_rev_conc.py`) sono incorporate con nomi miei
in `tests/test_b_correzioni.py`, rovesciate: oggi asseriscono il comportamento CORRETTO (le originali asserivano il
difetto). Unica scelta diversa dalla proposta del revisore: per l'API-Football 'sconosciuta' invece di una mappatura di
`status.short` (la mappatura e' una regola nuova: decisione dell'utente).

Numeri dopo la correzione:
- test del comparto: **175 non-cert verdi** (calcolo 38, freschezza 38, adattatori 65, servizio 9, correzioni 24, import 1)
  + 2 cert (parita' per tick, invariata: il servizio ricalcola le eta' allo stesso istante del giro, numeri identici);
- mutazioni: **46/46 rosse** (29 della consegna + 17 delle correzioni);
- suite intera (`python -m pytest Betfair/ -q -p no:cacheprovider`, UNA volta, dopo questa correzione, test cert
  compresi): **11.770 verdi, 0 rossi, 65 saltati, 6 xfailed, 616 s**. La falsificazione a livello di banco
  (`mutazioni_cert.py`, par. 5-bis) non e' stata rilanciata: il test cert e `esito_flusso`/`eta_punteggio_s` non sono
  cambiati.

## 11. Seconda revisione (di `67775f35`)

Esito: DA CORREGGERE (deadlock e fase del ripiego verificati dal coordinatore). Commit nuovo sopra `67775f35`, nessuna
riscrittura. Mutazioni: `mutazioni.py` per intero, **61/61 ROSSE** (29 della consegna + 17 della prima revisione + 15 di
questa), sha256 uguale dopo ogni ripristino. sha256 (12 cifre) dei file dopo la correzione: `servizio.py` `d4d6a370a30b`,
`calcolo.py` `72e1d3c98951`, `adattatori/ips.py` `872c79dfd2bb`, `adattatori/ips_tennis.py` `6ffb812d4a45`,
`adattatori/api_football.py` `d40ab6a56293`, `freschezza.py` `bce82b0608e7` (invariato).

| # | Punto | Correzione (file:riga) | Test | Mutazione rossa |
|---|---|---|---|---|
| a | DEADLOCK: callback sotto `_giro_lock` (regressione della prima correzione) | `servizio.py:412` `aggiorna` calcola sotto lock e ACCODA; `:451` `_svuota_coda`: un solo consegnatore, fuori dai lock, ordine di calcolo; un giro annidato (callback che chiama `aggiorna`) o concorrente si accoda e torna | `test_lock_invertito_fra_iscritto_e_chiamante_non_si_blocca` (exp2), `test_rientranza_consegna_nell_ordine_di_calcolo` (exp1/E3), `test_giri_serializzati_un_giro_lento_non_sovrascrive_quello_dopo` | "a consegna sotto _giro_lock (deadlock)", "a rientranza: il giro annidato consegna subito", "R6 giro non serializzato" |
| b | `eta.scanner_s` congelata | `servizio.py:352` `_ricalcolato`: `scanner_s` + tempo passato dall'istante della lettura | `test_scanner_s_cresce_col_silenzio` (2,0 -> 602,0 dopo 600 s) | "b scanner_s non ricalcolato" |
| c | stato "flusso fermo" senza `FlussoInterrotto` quando la fonte tace | `servizio.py:505` `_senza_dato`: calcio senza dato = ultimo stato con eta' e verdetto RICALCOLATI nel giro (eventi dal confronto) | `test_flusso_interrotto_al_giro_in_cui_il_verdetto_diventa_fermo` | "c fonte muta: verdetto non ricalcolato nel giro" |
| d | fase dal ripiego: Omega oggi la deduce dal minuto | `calcolo.py:254` `mission_phase(status=None, minute, kickoff=ko_ms, now)` importata; `:89` `StatoPartitaEsteso.fase_dedotta`; `servizio.py:246` `_fase_letta`: `FaseCambiata` solo fra fasi lette; divergenza 8 riscritta (par. 9), doc 9-bis, docstring | `test_api_football_fase_identica_a_mission_phase` (24 combinazioni x 11 `status.short`), `test_le_fasi_ips_sono_lette_non_dedotte`, `test_fase_dedotta_non_fa_scattare_fase_cambiata`, `test_passaggio_al_ripiego_non_inventa_fasi` | "R4/d fase del ripiego 'sconosciuta'", "d kickoff ignorato", "d fase dedotta dichiarata letta", "d FaseCambiata anche da fasi dedotte" |
| e | `ferma()` dal thread del giro: `RuntimeError` | `servizio.py:584`: dal proprio thread niente `join`, torna False | `test_ferma_dal_thread_del_giro_non_solleva` | "e ferma dal thread del giro: join su se stesso" |
| f | una partita rotta scartava il giro delle altre negli adattatori | `adattatori/ips.py:92` `FonteIpsRunner.leggi` try per partita (`continue`, come `runner.py:351-353`); `ips.py:42` `LogRaro` (`flusso_prezzi.Promemoria`, una riga al minuto per partita); `ips_tennis.py:58` idem; `api_football.py` circuito idem | `test_runner_una_partita_rotta_non_scarta_le_altre` (`rows_for` che solleva su una), `test_tennis_una_partita_rotta_non_scarta_le_altre` (`grezzo_dal_feed` che solleva su una) | "f runner...", "f tennis...", "f log a ogni errore" |
| g | mutanti sopravvissute T13, T15, T21, T24 | (codice gia' corretto; mancavano i test) | `test_t13_chi_esce_da_segui_dimentica_fase_e_flusso`, `test_t15_osserva_book_ignora_le_partite_non_seguite`, `test_t21_chi_esce_da_segui_durante_la_lettura_non_torna`, `test_t24_tennis_muto_con_riga_non_conserva_la_lettura_vecchia` | "g T13", "g T15", "g T21", "g T24" |
| h | finti nei book di `osserva_book` | `test_b_correzioni._libro`: `MarketBook` VERO di betfairlightweight costruito dal suo dict con la `MarketDefinition` VERA della registrazione 35760084 (`market_time` sostituito solo per i bordi che una registrazione non ha) | tutti i test con `_libro` | - |
| i | referto | par. 7 riga 6.6, questa sezione, `mutazioni.py` aggiornato | - | - |

Numeri: test del comparto **212 non-cert verdi** (175 della prima revisione, meno il vecchio test unico della fase
"sconosciuta", piu' 24 casi del test di parita' con `mission_phase`, `test_le_fasi_ips_sono_lette_non_dedotte` e i 13 di
`test_b_seconda_revisione.py`) + 2 cert. Suite intera: riga in coda.

Suite intera (`python -m pytest Betfair/ -q -p no:cacheprovider`, UNA volta, dopo questa correzione, test cert compresi):
**11.807 verdi, 0 rossi, 65 saltati, 6 xfailed, 834 s**.
