# TETTO_TENNIS_CANTIERE - «soldi veri» sul tennis governati da «Ordini reali» (04/10/2026)

Ramo: `worktree-agent-a07fd1ab50fc74bfe` (master + merge `20ff0ae` del delegato «TENNIS_SOLDI_VERI_COERENTE»,
merge pulito, nessun conflitto). Decisione dell'utente (04/10, «1) si»): i soldi veri del tennis li governa lo
STESSO interruttore «Ordini reali» del calcio (`betfair_live_settings.order_mode`, RPC `set_live_order_mode`),
nessun interruttore tennis separato, nessuna migrazione.

Consegna a passi (un commit per passo). Questo referto cresce a ogni passo.

---

## PASSO 1 - MAPPA (sola lettura)

### 1.1 Come lo fa il CALCIO (il modello da copiare)

| Pezzo | Dove | Che cosa fa |
|---|---|---|
| Tetto (capacita' del processo) | `live_order_worker._modo_processo` (`live_order_worker.py:142-165`) | `LIVE_ORDER_MODE` del `.env` (via `config_stream.live_order_mode`), default OFF; dice QUALI client esistono. Il client reale nasce solo con tetto LIVE (`runner.build_order_client`). |
| Scelta dalla UI | `modo_ordini.registra_settings` (`modo_ordini.py:141-156`) alimentato da `live_order_worker._refresh_settings` (`:486-513`) | la STESSA lettura `get_live_settings` (~1/s, gia' fatta per il kill-switch) porta `order_mode`: zero letture in piu'. Lettura valida 30 s (`VALIDITA_S`), poi OFF. |
| Modo effettivo | `live_order_worker._live_order_mode` (`:168-181`) = `modo_ordini.modo_effettivo(tetto, valore_db())` (`modo_ordini.py:85-94`) | il piu' restrittivo; illeggibile -> OFF. |
| Avvio dell'app | `runner._dichiara_modo_ordini_all_avvio` (`runner.py:2424-2443`) + `modo_ordini.richiedi_avvio`/`dichiara_avvio` (`modo_ordini.py:248-336`) | a un `APP_BOOT_ID` nuovo la riga SCENDE a PAPER e prende `order_mode_boot_id` = questo avvio; finche' non e' fatto, `valore_db()` = None -> aperture OFF. |
| Aperture vs chiusure | `live_order_worker._blocco_apertura_modo` (`:184-205`) | una riga che NON chiude (`_is_closing_row`: cancel/greenup/`reduces_liability`) e il cui `mode` non e' servibile dall'EFFETTIVO e' rifiutata col motivo «si cambia da Control Room, Ordini reali». Chiusure: servite dal TETTO. |
| Righe servibili | `_servable_modes` (`:235-247`) | tetto LIVE -> ('live','paper'); PAPER -> ('paper',); OFF -> (). |
| Client per riga | `_client_for_mode` (`:276-314`) | client scelto dal `mode` DELLA RIGA; manca -> `live_client_assente`/`paper_client_assente`, nessuna esecuzione. |
| Paper e live separati | `_strategy_for_mode` (`:337-350`) + runner `runner.py:2881-2900` | DUE `LiveTradingStrategy` (nome diverso, stesso stream): blotter, esposizioni, specchio e settled per modalita'. |
| Motore ordini (canale 47331) | `motore_ordini._controlla` (`motore_ordini.py:1074-1110`) | tetto -> `_servable_modes`/`_client_for_mode`/`_strategy_for_mode`; poi `_blocco_modo` (= `_blocco_apertura_modo` dell'esecutore) sulle aperture, chiusura dichiarata solo se VERIFICATA sulle esposizioni della strategia DELLA MODALITA' (`_riduzione_verificata` `:1381-1408`). |
| Ladder a mano | `runner.py:312-322` (`live_now.state.order_mode = _MO.modo_corrente()`, + `order_mode_tetto`, `order_mode_scelto`) -> `LadderView.tsx:1468-1471` (`mode` = `orderMode` minuscolo) | il ladder manda la modalita' EFFETTIVA (riportata a PAPER a ogni avvio): un clic e' reale solo dopo «Ordini reali» = LIVE in questo avvio. |
| Canale | `live_order_worker._pubblica_modo_ordini_se_cambiato` (`:529-566`) | topic `modo_ordini` = `stato_corrente()`, SOLO sul canale calcio (`:549`): sul 47332 oggi non esce niente (il reperto 5 del delegato precedente e' gia' chiuso da questa riga; il tennis non dichiara pero' un effettivo suo). |

### 1.2 Che cosa MANCA nel TENNIS, punto per punto

| # | Calcio | Tennis oggi | Dove |
|---|---|---|---|
| M1 | tetto `LIVE_ORDER_MODE` dal `.env` | tetto `TENNIS_LIVE_ORDER_MODE`, FORZATO a `'PAPER'` da `desktop/main.js:382` se l'ambiente del processo Electron non lo porta (il `.env` non arriva a `process.env`: `readEnvFile` e' usato solo per il login, `main.js:768`; `load_dotenv` non sovrascrive) | `tennis_runner.live_order_mode` `:138-140`, `tennis_live_order_worker._runner_mode` `:56-74`, `esecutore_tennis._modo_processo` `:124-127` |
| M2 | modo effettivo = tetto x «Ordini reali» | NON ESISTE: `modo_ordini.registra_settings` riceve gia' la riga nel processo tennis (`guardie_tennis.aggiorna_impostazioni` `:220-233` -> `_low._refresh_settings`, ~1/s, dal worker ordini) ma nessuno la usa per il modo | - |
| M3 | validita' per QUESTO avvio | il runner tennis non chiama `richiedi_avvio`; `registra_settings` non conserva `order_mode_boot_id` (la RPC lo restituisce: `get_live_settings` = `to_jsonb(s.*)`, `migrations/live_order_mode_control_2026-09-24.sql:39,93`) | `modo_ordini.py:141-156` |
| M4 | `_blocco_apertura_modo` sulle aperture | `esecutore_tennis._blocco_apertura_modo` ritorna SEMPRE None (`:150-154`) | motore tennis (Safe tennis) |
| M5 | coda/canale: righe `paper`+`live` servite per riga, aperture filtrate dall'effettivo | il worker accetta SOLO `mode == tetto`: `/order` locale `tennis_live_order_worker.py:1397`, coda DB `:1561` (`_reject_cross_mode` `:1335-1351`). Con tetto LIVE il ladder in prova SPARISCE e ogni clic e' reale | worker tennis |
| M6 | due strategie per modalita' | UNA capture per tutto (`tennis_runner.py:3119-3131`; a caldo `:2541`); gli ordini a mano e i comandi del motore vivono tutti sotto di lei (`_capture_strategy` `tennis_live_order_worker.py:537-544`, usata da `_do_place` `:600`, `_do_greenup` `:817`, `_cancel_unmatched_selection` `:758-789`; `esecutore_tennis._read_matched_exposures` `:177-183`; `_strategy_for_mode` `:138-147` «una sola per tutte le modalita'»). `_read_matched_exposures` (`:736-755`) non filtra per client: green-up, cash-out e verifica `reduces_liability` SOMMEREBBERO paper e live (reperto B2, catalogo §7.21) | worker + esecutore + runner |
| M7 | specchio posizioni per modalita' | `positions_worker` (`:1225-1329`) chiave `(mode_s, ...)` con `mode_s = _modo_strategia` (`:1071-1080`): la capture NON porta `_tennis_modalita_esecuzione` -> vale `_session_mode` = tetto. In un runner LIVE le posizioni del ladder in prova sarebbero scritte 'live' | worker |
| M8 | `live_now.state.order_mode` = EFFETTIVO (+ tetto + scelto) | `tennis_live_now.state.order_mode = live_order_mode()` = TETTO (`tennis_runner.py:1500`) (reperto B1) | runner |
| M9 | ladder: mode = effettivo | `TennisLadderColumn.tsx:83-88,121` -> `LadderView`/`GridView`; testata `TennisTerminal.tsx:109-110,187-197` («LIVE · REALE»/«PAPER · SIMULATO»), `TennisBotPanel` (`orderMode` dalla testata) e `StandaloneLadder` (ramo tennis = `TennisLadderColumn`): tutti dal TETTO | frontend tennis |
| M10 | il canale dichiara l'effettivo | hello/battito del 47332 portano `mode = live_order_mode()` (tetto) (`tennis_runner.py:2933,2988`); nessun effettivo tennis | runner |
| M11 | aperture dei bot ospitati seguono l'effettivo | i 4 bot: `modalita_esecuzione_bot(control, tetto)` (`guardie_tennis.py:87-98`), nessuna lettura di «Ordini reali» | runner/guardie |
| M12 | testo UI | `TennisLadderColumn.tsx:160-165` «imposta TENNIS_LIVE_ORDER_MODE=PAPER e riavvia»; `TennisBotPanel.tsx:540-560` chiede conferma «ORDINI REALI» e annuncia «· ORDINI REALI» quando il runner e' LIVE, ma `tennis_bot_arm` scrive SEMPRE `mode='paper'` (`migrations/tennis_bot_control_mode_2026-09-24.sql:96-105`): la scheda direbbe il falso | frontend tennis |

### 1.3 TUTTI i produttori di ordini tennis e dove nasce il loro `mode`

| # | Produttore | Strada | Dove nasce `mode` | Chi lo accetta oggi |
|---|---|---|---|---|
| P1 | Ladder / Grid / ladder staccato / multi-ladder del Tennis Terminal (place, cancel, replace, drag-move, green-up, cash-out) | canale 47332 `/order` (`localOrderApi('tennis')`) oppure coda DB `request_tennis_live_order` (`lib/tennis.ts:410-460`) | `tennis_live_now.state.order_mode` (= TETTO, `tennis_runner.py:1500`) -> `LadderView.tsx:1468-1471` | worker tennis: `mode == tetto` (`:1397`, `:1561`) |
| P2 | Safe tennis (servizio Safe) | canale 47332 `/comando/safe_tennis` -> `MotoreOrdini` con `esecutore_tennis` | `safe_strategy_control.params.strategy_modes.tennis` (scritto dal gesto; a ogni avvio torna prova) | motore: `mode in _servable_modes(tetto)` (`motore_ordini.py:1075`), `_blocco_apertura_modo` = None |
| P3 | 4 bot ospitati (scalper, pro, flb, swing) | `market.place_order` dentro il runner (strategie flumine proprie) | riga `tennis_bot_control.mode` (ponte `tennis_bot_service._riga_armatura` `:861-877` dall'interruttore della Control Room; `tennis_bot_arm` dalla scheda = sempre 'paper') x tetto (`modalita_esecuzione_bot`) + `dry_run` ESATTAMENTE False per il reale (`guardie_tennis.dry_run_esplicito_falso`) | seconda rete `ControlloModalitaBotTennis` (client <-> modalita' del bot) |
| P4 | «Chiudi ora» di un bot tennis (Control Room `chiudiRiga.ts:21-27`) | coda DB, azione `chiudi_bot` -> `chiusura_manuale.gestisci_riga` | `mode` della riga = modalita' del bot | worker: confronto con la modalita' DEL BOT (`:1551-1559`), e' una chiusura |
| P5 | Annulli a guardia d'avvio armata | canale 47332 `/order` cancel | come P1 | `_rispondi_comandi_locali_in_guardia` (`:1467-1505`) |
| P6 | Ripresa / reconcile | nessun ordine nuovo (solo specchio) | `rec.mode` per ordine (`_track_manual` `:964-987`) | - |

Altri piazzamenti NON trovati: nel pacchetto `tennis_live` (test esclusi) gli unici `place_order` sono quelli
del worker (`tennis_live_order_worker.py:657` place, `:917` green-up) e la vista `MercatoConClient`
(`guardie_tennis.py:125`, bot paper in runner LIVE); i bot ospitati piazzano con `market.place_order` dentro
flumine. Nessun `placeOrders` REST verso Betfair per il tennis.

### 1.4 Conseguenze per i passi successivi (piano, nessuna decisione presa)

- Passo 2 (B2): capture degli ordini PER MODALITA' (la capture di lettura del book resta una), modalita' scritta
  sull'istanza (`_tennis_modalita_esecuzione`) cosi' specchio posizioni e `ControlloModalitaBotTennis` la vedono;
  `_capture_strategy(session, market_id, mode)`; l'esecutore porta la modalita' fino a `_read_matched_exposures`.
- Passo 3: `modo_ordini` conserva `order_mode_boot_id`; regola tennis = `modo_effettivo(tetto_tennis,
  scelta valida SOLO se boot_id della riga == APP_BOOT_ID)`; `esecutore_tennis._blocco_apertura_modo` come il
  calcio; worker: righe servibili dal tetto + blocco aperture dall'effettivo; terza rete DENTRO flumine (un
  ordine sul client REALE che non riduce il rischio parte solo con effettivo LIVE: copre anche i 4 bot).
  Nessuna lettura in piu' (la riga arriva gia' ~1/s).
- Passo 4 (B1): `state.order_mode` = effettivo (+ `order_mode_tetto`, `order_mode_scelto`): ladder, grid, testata e
  scheda bot seguono da soli; testi veritieri.
- Passo 5: tetto da `main.js` con funzione pura + test node; SOLO dopo 2-4 verdi.
- Passo 6: topic `modo_ordini` del 47332 con lo stato TENNIS (dall'esecutore tennis, nessuna modifica a
  `live_order_worker.py`, fuori perimetro).
- Passo 7: reperto confermato in lettura: il ponte scrive `"dry_run": d["mode"] == "live"`
  (`tennis_bot_service.py:874`): «soldi veri» dalla Control Room = bot LIVE in dry-run (nessun ordine) finche' non si
  toglie il dry-run partita per partita. Correzione da PORTARE al coordinatore (cambia chi manda soldi veri).
  -> Superato dall'ordine dell'utente ricevuto dopo la mappa: corretto al passo 7.

---

## Commit dei passi 2-8 (ramo `worktree-agent-a07fd1ab50fc74bfe`, niente push)
`b8d3e85` passo 2 · `d93bac4` passo 3 · `76a74c9` passo 4 · `a61ef38` (controlli del runner testabili) ·
`c6af6ef` passo 5 · `07ccbaf` passo 6 · `93d1d6d` + `5afb13b` passo 7 · `9118338` + `52a03f9` passo 8.
Falsificazione: `AUDIT_2026-10-04/strumenti/falsifica_tetto_tennis.py <gruppo>` (b2 b3 b4 ui4 b5 b6 ui6 b7 b8),
ripristino `git checkout -- <file>`, `git status` pulito dopo ogni giro.

## PASSO 2 - B2: paper e live MAI sommati nel runner tennis
- `tennis_runner.py`: `_make_capture(..., nome=, solo_ordini=)`; `NOME_CAPTURE_LIVE`; `capture_degli_ordini()`
  (paper = la capture dei book, invariata; live = strategia `_CaptureOrdiniLive` SOLO col tetto LIVE, stesso
  filtro -> stesso stream, `check_market_book` falso = zero lavoro per book; entrambe con
  `_tennis_modalita_esecuzione`); `session.capture_ordini` (azzerata a `reset_streams`); build: `add_strategy`.
- `tennis_live_order_worker.py`: `_capture_strategy(session, market_id, mode)` (mappa presente -> SOLO la
  strategia di quella modalita', mai l'altra; assente -> capture unica: banco/runner PAPER); `_do_place` e
  `_do_greenup` con `cmd["mode"]` (green-up, resting annullati ed esposizioni della sola modalita');
  `_iter_tracked_strategies` include le strategie degli ordini (specchio posizioni per modalita', M7).
- `esecutore_tennis.py`: `CaptureDiModo`; `_strategy_for_mode` rifiuta la modalita' senza strategia;
  `_read_matched_exposures` per modalita' (verifica `reduces_liability` del motore).
- `ControlloModalitaBotTennis` ora vale anche per le capture (ordine paper su client reale, o viceversa,
  rifiutato DENTRO flumine).
- Test nuovi: `test_paper_live_separati_tennis_2026_10_04.py` (9; Flumine/client/Blotter VERI, gamba reale con
  `CurrentOrder` vero di betfairlightweight, nessun ordine eseguito su client reale). Falsificazione b2:
  F1-F6 ROSSE 6/6.

## PASSO 3 - modo effettivo del tennis = tetto x «Ordini reali» di QUESTO avvio
- `modo_ordini.py`: `registra_settings` conserva `order_mode_boot_id`; `scelta_per_questo_avvio()` (valida
  solo se letta, fresca e `order_mode_boot_id == APP_BOOT_ID`; banco dichiarato = valida);
  `modo_effettivo_tennis(tetto)` (scelta non valida -> PAPER, mai LIVE; OFF esplicito = OFF);
  `stato_tennis(tetto)` (effettivo, tetto, scelta, motivo `ok|tetto_ambiente|db_assente|avvio_diverso`).
  Il calcio non cambia.
- `tennis_live_order_worker.py`: `_modo_effettivo`, `_servibili`, `_blocco_apertura_modo` (regola del calcio,
  chiusure sempre servite); `/order` del canale: righe paper E live servite per riga (prima solo
  `mode == tetto`), aperture fermate col motivo; coda DB idem (riga 'error' esplicita, mai 'pending');
  specchio del canale sotto la modalita' DELL'ORDINE (prima quella del runner: difetto).
- `esecutore_tennis._blocco_apertura_modo` -> la stessa funzione (prima `None`: Safe tennis live col solo tetto).
- TERZA RETE `guardie_tennis.ControlloModoOrdiniTennis` (+ `motivo_reale_fermo`), montata da
  `tennis_runner.aggiungi_controlli_ordini`: un ordine sul client REALE che non riduce il rischio parte solo
  con effettivo LIVE; fail-closed se il tetto riletto non e' LIVE; log al piu' 1 ogni 60 s.
- Avvio dell'app: la riga resta quella di ieri (boot diverso) finche' il runner calcio non la riporta a PAPER
  (`dichiara_avvio`); in entrambi i casi il tennis e' in PROVA (`test_avvio_nuovo_dell_app_tutto_in_prova`).
- Test nuovi: `test_modo_effettivo_tennis_2026_10_04.py` (34, con passo 6 e montaggio della terza rete). Test
  MODIFICATI (dichiarato; col tetto LIVE un'apertura live ora vuole «Ordini reali» LIVE di questo avvio):
  `test_modalita_e_guardie_tennis_2026_09_24.py` (fixture `worker_finto` dichiara la scelta LIVE con la riga
  vera; `_stato_pulito` azzera `modo_ordini`), `test_cantiere_d2_minimo_e_specchio_2026_09_28.py`
  (`dichiara_per_banco("live")` attorno al solo comando live). Falsificazione b3: E1-E13 ROSSE 13/13.
- Chiamate: DB 0 in piu' (`test_nessuna_lettura_db_in_piu`: un giro = 1 lettura settings + 1 coda, come prima);
  Betfair 0.

## PASSO 4 - B1: ladder e ordini a mano del Tennis Terminal
- `tennis_runner._build_now_state`: `order_mode` = EFFETTIVO, + `order_mode_tetto`, `order_mode_scelto`,
  `order_mode_motivo`. Ladder, grid, ladder staccato, multi-ladder, testata «LIVE · REALE»/«PAPER · SIMULATO»
  (`TennisTerminal.tsx`, invariato) leggono gia' questo campo: con tetto LIVE e «Ordini reali» in prova il clic
  manda `paper`; un `live` stantio e' fermato dal worker (passo 3).
- `TennisLadderColumn.tsx`: testo OFF col perche' (tetto del runner o «Ordini reali» su OFF). Fotografia
  `tennis-terminal-match.{off,v2}.json`: cambia SOLO il banner (verificato col diff; `.guscio.json` ripristinati).
- `TennisBotPanel.tsx` (M12): la scheda arma SEMPRE in prova (`tennis_bot_arm` scrive `mode='paper'`): tolti
  conferma e annuncio «ORDINI REALI» (falsi); default come la prova; avviso «i soldi veri si accendono
  dall'interruttore del bot (Control Room)».
- Test nuovi: `test_ladder_modo_effettivo_tennis_2026_10_04.py` (7). Vitest MODIFICATI (dichiarato, §7.28:
  asserivano la conferma di soldi veri che non partivano): `TennisBotPanel.test.tsx` casi 2-5 e «LIVE: default».
  Falsificazione b4: L1-L2 ROSSE; ui4: U1-U3 ROSSE.

## PASSO 5 - tetto da `main.js`
- `desktop/ambiente_runner.js` (nuovo, funzioni PURE `costruisciEnvRunner`/`tettoTennis`):
  `TENNIS_LIVE_ORDER_MODE` scritto (ambiente, poi `.env`) vince; altrimenti `LIVE_ORDER_MODE` = LIVE -> LIVE;
  altrimenti PAPER (mai OFF; valore illeggibile -> PAPER). Il `.env` NON viene copiato nell'ambiente.
- `desktop/main.js` (`spawnRunner`): usa la funzione; log «tetto ordini del runner tennis: X».
  `desktop/package.json`: `ambiente_runner.js` fra i file dell'exe (serve solo se un giorno si ricompila).
- Test di contratto `desktop/ambiente_runner.test.js` (`node --test desktop/ambiente_runner.test.js`, Node 22,
  nessuna installazione): 6/6. Falsificazione b5: T1-T5 ROSSE 5/5. `node --check desktop/main.js` OK.
- Applicato DOPO i passi 2-4 verdi.

## PASSO 6 - il runner tennis dichiara il suo modo
- `guardie_tennis.pubblica_modo_ordini_se_cambiato` (da `aggiorna_impostazioni`, ~1/s, gia' esistente): topic
  `modo_ordini` + `hello.modo_ordini` sul 47332 = `stato_tennis`, solo al cambio, zero IO. `hello.mode` e
  `battito.mode` restano il TETTO. La funzione del calcio resta muta sul 47332 (test).
- `frontend/src/lib/interruttori.ts` `motivoSoldiVeriNonServiti`, ramo tennis (contratto `CatenaLive`
  INVARIATO): oltre al tetto del runner tennis serve «Ordini reali» = LIVE (letta al gesto; il tetto del CALCIO
  non conta per il tennis). `soldiVeriCatena.test.ts` +3 (17/17).
- Falsificazione b6: C1-C4 ROSSE; ui6: G1-G3 ROSSE.

## PASSO 7 - i 4 bot tennis e Safe tennis
- `tennis_bot_service._riga_armatura`: `"dry_run": False` anche in live (prima `d["mode"] == "live"`: «soldi
  veri» = bot in dry-run, nessun ordine). `live_in_dry_run` VERO solo se una partita live e' davvero in dry-run.
- Test nuovi `test_soldi_veri_bot_tennis_2026_10_04.py` (22): per ognuno dei 4 bot (riga del ponte VERO +
  `_instantiate_bot` + controlli del runner): live + «Ordini reali» LIVE -> pacchetto sul client REALE; live +
  «Ordini reali» in prova -> nessun pacchetto; prova -> client simulato; scelta di ieri -> niente reale. Safe
  tennis dal motore VERO: LIVE -> client reale sotto `_CaptureOrdiniLive`; in prova -> ack rifiutato «Ordini
  reali» e la prova parte sul client simulato sotto la capture paper.
- Test MODIFICATI (dichiarato, ordine dell'utente del 04/10): `test_ponte_interruttori_2026_09_17.py`
  (`test_in_LIVE_il_bot_nasce_in_dry_run` -> `..._pronto_a_operare`), `test_tennis_auto_mode_2026_09_25.py`
  (live -> dry False, + test `live_in_dry_run`), `test_modalita_e_guardie...::test_ponte_scrive_la_modalita_esplicita`.
- Falsificazione b7: S1-S5 ROSSE (S5 rossa dopo il rafforzamento del test, `5afb13b`).

## PASSO 8 - banco
- `trasporto_rapido.py`: R11b TENNIS non piu' N/A (`_r11b_tennis`: tetto LIVE, «Ordini reali» in prova, funzione
  VERA del runner nel motore; condotta di catena di Safe; motivo «Ordini reali»; ladder (worker): aperture reali
  ferme, prova e chiusure servite; terza rete DENTRO flumine su un'apertura col client live del banco:
  ControlError) - 15 controlli. R11d NUOVO (tennis; N/A calcio): «Ordini reali» LIVE -> comando live accettato,
  ordine sul `ClienteLiveBanco` (l'«ordine reale» simulato del banco), terza rete passa - 5 controlli; posto PRIMA
  di R2b (dopo R2b il MATCH_ODDS tennis non riapre: «Market is not open»).
- `certifica safe_tennis 35795993 --scenari rapidi --trasporto entrambi`: **13 s**, 18 scenari KO 0; parita' coda
  1053 decisioni / 2 azioni, canale 1054 / 2: IDENTICA al riferimento (`replay/safe_tennis_rapidi_entrambi_DOPO.txt`);
  le 114 righe degli altri scenari IDENTICHE riga per riga. Referto `replay/safe_tennis_rapidi_entrambi_TETTO.txt`.
- 4 bot tennis, `--scenari base,live,gate-aperto,parziali,uscite-manuali,uscite-manuali-firmate` su 35794049
  (`--data-dir C:/Users/Admin/Desktop/tennis_rec/20260707`), uno alla volta: flb 20 s, pro 91 s, swing 22 s,
  scalper 48 s. flb 6 OK (azioni 1) e swing 6 OK (azioni 0): IDENTICI al giro del 29/09. **pro (2 KO) e scalper
  (4 KO): GIA' KO su master 23e1fb3**: rilanciati dal codice del master (sola lettura, `PYTHONDONTWRITEBYTECODE=1`),
  referti IDENTICI ai miei salvo id d'ordine e hash (`*_MASTER_23e1fb3.txt` vs `*_TETTO.txt`). Reperto R4.
- Test del banco MODIFICATI (dichiarato: scenari 14 -> 18 = R11/R11b/R11c del cantiere precedente + R11d; erano
  GIA' rossi, 17 != 14): `test_motore_ordini_tennis_2026_09_25.py::test_profilo_rapido_safe_tennis...` (+ R11b
  e R11d OK), `stream/tests/test_strada_unica_banco_2026_09_25.py::test_profilo_rapido_verde...`.
- Falsificazione b8 (replay canale): R1 motore senza «Ordini reali», R3 terza rete assente, R4 effettivo = tetto,
  R5 chiusure del ladder frenate: ROSSE. R2 (scelta di un altro avvio valida): VERDE nel banco per costruzione
  (il banco dichiara la scelta con `dichiara_per_banco`, che vale come «questo avvio»): coperta dai test E1/L2.

## Numeri finali
- pytest `Betfair/stream Betfair/safe_strategy` (meno il file strada unica, lanciato a parte): **6681 passed**,
  28 skipped, 9 xfailed, 0 falliti (358 s); `test_strada_unica_banco` + `Betfair/omega`: 1461 passed;
  `Betfair/mike`: 1548 passed.
- `npx tsc -p tsconfig.app.json --noEmit` = 0. vitest `src/components/tennis src/components/live
  src/lib/soldiVeriCatena.test.ts src/lib/interruttori* src/components/controlroom src/fotografia`:
  **107 file, 1473 passed**. Node: 6/6.

## Parita' paper/live
Paper e live passano dalle STESSE funzioni (`_do_place`, `_do_greenup`, motore, controlli); cambiano solo il client
e la strategia degli ordini (una per modalita'). La prova non e' frenata da «Ordini reali» salvo un OFF esplicito
(come il calcio). Il runner PAPER e' invariato (stessa capture di prima).

## Reperti e decisioni per il coordinatore
- R1 (ponte, gesto su un bot GIA' acceso in prova): «soldi veri» cambia solo le partite NUOVE; quelle gia'
  armate in prova restano in prova fino alla fine (`tennis_bot_service`: `if ev in attive: continue` e
  `_escludi` per il feed, scelta del 28/09). Proposta: al cambio di modalita' riarmare nella modalita' nuova
  le partite SENZA posizione (quelle con posizione restano fino al flat). Non applicata (cambia la condotta del
  ponte). Oggi il gesto sicuro e' spegnere il bot e riaccenderlo in soldi veri.
- R2 (scheda per partita del Terminal): arma sempre in prova; «soldi veri» da li' vuole una RPC `tennis_bot_arm`
  con `p_mode` (migrazione). Oggi la scheda lo DICE.
- R3 (`components/controlroom/tennisAuto.ts:107`, fuori perimetro): «LIVE: le partite nascono in dry-run...» ora
  esce solo se una partita live e' davvero in dry-run; la parola «nascono» non e' piu' vera.
- R4 (fuori perimetro, GIA' su master): tennis_pro KO («BACK per 1.0: sotto il minimo .it di 2.0 ->
  INVALID_BET_SIZE, gamba scoperta») e tennis_scalper KO (K1: posizione FLATTENING su un ordine che a mercato
  non esiste) su 35794049. Il banco dei minimi usa 2,00, la decisione del 01/10 e' 1,00. Da affidare.
- R5: con «Ordini reali» in prova il ladder mostra solo ordini/posizioni PAPER (filtro per `mode`, come il calcio).
- R6: a runner tennis in ATTESA (nessuna partita) i settings non si rileggono: il topic `modo_ordini` del 47332
  resta l'ultimo; la guardia del gesto legge «Ordini reali» dal DB al clic.
- R7 Safe tennis via strada DIRETTA (`SAFE_TENNIS_ORDINI_VIA_CANALE=0`): non toccata, non passa dal runner
  tennis (REST dal processo Safe col suo `_live_brake` = `LIVE_ORDER_MODE` x «Ordini reali», senza il controllo
  d'avvio del tennis). Terza rete e controllo d'avvio valgono SOLO sulla strada del canale. In prova la strada
  diretta non esegue (`paper_senza_runner`, Cantiere P): invariato.

## Non verificato
App viva ed Electron (solo `node --check` + test della funzione pura); ladder e testata nell'app; scrittura di
`tennis_live_now` sul DB vero; il `.env` del principale (non letto: segreti; il delegato precedente dichiara
`LIVE_ORDER_MODE=LIVE`); ordini veri su Betfair (mai inviati); replay calcio completi (solo i profili rapidi
safe_base/omega nella suite pytest, verdi).

## Che cosa deve fare l'utente (in parole semplici)
1. A posizioni live chiuse (Mike): integrare il ramo, `npm run build` in `frontend/`, riavviare l'app. Nel log
   dell'app: «tetto ordini del runner tennis: LIVE» (con `LIVE_ORDER_MODE=LIVE` nel `.env`).
2. A ogni apertura dell'app tutto parte in PROVA. Per i soldi veri: Control Room, riga «Ordini reali» -> LIVE
   (doppia conferma). E' lo stesso interruttore del calcio: vale per calcio e tennis.
3. Safe tennis: Control Room, scheda tennis, «soldi veri» su Safe tennis.
4. Ognuno dei 4 bot tennis: interruttore del bot -> soldi veri (se era gia' acceso in prova: spegnerlo e
   riaccenderlo in soldi veri, R1). Gli ordini reali partono subito, senza togliere il dry-run partita per partita.
5. Ladder del Tennis Terminal: con «Ordini reali» LIVE la testata dice «LIVE · REALE» e i clic sono reali; per
   cliccare in prova si riporta «Ordini reali» su PROVA.
