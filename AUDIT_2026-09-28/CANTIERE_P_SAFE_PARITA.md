# CANTIERE P — SAFE E CHIUSURE: NESSUN FILL DI CASA IN PAPER, RESIDUI DI PARITA' (28/09/2026)

Delegato P, worktree `agent-aa22788f6dc13aca9`, ramo `worktree-agent-aa22788f6dc13aca9`.
Riallineato su **origin/master `d407b59`** (merge pulito, nessun conflitto). Commit LOCALI di lavoro
(`7f53083` blocco 1, `0b35655` blocco 3, `a82869f` nota replay, `43e9e29` merge): **nessun push**.
Ordine dell'utente: «deve essere lo specchio per tutti i bot».

## 0-bis. RICONSEGNA (correzioni del coordinatore e del revisore) — base `staging-2026-09-28` `e31d65f`

Riallineato con `git merge staging-2026-09-28` (merge pulito). Suite sul codice sommato:
Safe + Omega + Mike + 7 file stream (r3, submin, strada unica, motore ordini, D1-ter caso B e parita')
→ **4531 passed, 6 skipped, 1 xfailed, 0 failed**. Falsificazione completa sul codice sommato:
**28 mutazioni, 28 ROSSE** (`cantiere_p/esito_falsificazione_su_staging.txt`), ripristino SHA-256 identico.

| Richiesta | Esito | Dove |
|---|---|---|
| T. runner giu' NON consuma `place_max_attempts` | **FATTO**: `paper_senza_runner` chiude la riga col motivo, tentativi invariati, mai `final`, ritento dopo `XE.retry_backoff_s(1)` (5 s, nessuna soglia nuova); riga CRITICA (kind `skip`, gia' in catalogo) al piu' 1/min per partita; `bot_db.place_attempts` salta le righe `meta.place.senza_runner` | `bot_service._place_fail_senza_runner`, `bot_db.place_attempts`; test: runner giu' 5 giri poi su = apertura al primo giro, 0 tentativi; 3 rifiuti veri = `place_exhausted`; seme dopo riavvio non riconta (m17-m20) |
| 1. P-O1 Omega | **CORRETTO nel codice** e asserzioni RIMESSE (`state=='done'`, `exit_kind=='greenup'`). `integral = primo invio e (fill in volo o coperto)`; `_greenup_fill_confermato` porta lo stato a 'done' in `_settle_hedged` dopo `apply_hedge_state`. **Doppia chiusura: NO** — la guardia del secondo invio e' `hedge_pending_ids`/'hedged' (`_greenup_candidates`), non `greenup.state`: test `test_p_o1_stato_done_al_fill_e_mai_un_secondo_invio` (un giro prima del fill e tre dopo: sempre 1 gamba) | `omega_service.py` (`_greenup_send`, `_greenup_fill_confermato`, `_settle_hedged`); m21, m22 |
| 3. chiusura a runner giu' | **FATTO**. Prima: `close_trade` riservava una gamba 'error' a OGNI ritentativo; l'uscita Safe consumava `attempts`, dopo `exit_max_retries` (3) diventava 'failed' (visibile, non terminale) col backoff 5/15/60/300 s ripetuto ogni 300 s (`bot_service` ramo `if err:`, `_exit_due`); il green-up Omega arrivava a `greenup_max_attempts` e poi a `GREENUP_FAILED_COOLDOWN_S`. Ora: `close_trade` dice `paper_senza_runner` PRIMA della riserva (`_runner_paper_assente`); Safe: nessun tentativo, stato 'retrying', ritento ogni 5 s, riga CRITICA `exit_retry` 1/min con `esposizione_eur`; Omega: nessun tentativo, riga CRITICA `greenup_retry` 1/min con esposizione; al ritorno del runner l'uscita parte al giro dopo | `execution.close_trade`, `bot_service._log_uscita_senza_runner`, `omega_service._greenup_send`; m23-m25 |
| 2. `canale_cor` | **FATTO**: una strada di ritentativo sulla stessa riga ESISTE (place-and-trim sul canale: parcheggio -> taglio -> riprezzo, flumine da' al nuovo ordine un customerOrderRef nuovo). Il cor corrente si aggiorna a ogni cor nuovo della riga, i vecchi in `meta.canale_cor_storico` (max 8, solo quelli arrivati dagli eventi del ref di QUELLA riga); riconciliazione, cleared e banco usano tutti | `bot_service._risolvi_una_via_canale`, `execution.cor_di_riga`; m26, m27 |
| 4. riepilogo righe storiche | **FATTO**: una riga `reconciled_error` `reconcile_paper_senza_runner_riepilogo` con `n` e `trade_ids` | `bot_service.reconcile_pending`; m28 |
| 5. asserzioni tolte | **§10** qui sotto (+ elenco completo automatico `cantiere_p/asserzioni_tolte_o_cambiate.txt`, 61 righe) | |

## 0. Stato per punto del brief

| # | Punto | Esito |
|---|---|---|
| 1 | Niente fill di casa in paper (`place`, `close_trade`, Safe tutte le strategie + chiusure Omega) | **FATTO, verde, falsificato** |
| 2 | Finti dei test: coda/runner simulato al posto di `follow="NONE"` | **FATTO** (riuso del runner finto di Omega) |
| 3 | S6 sotto-minimo paper sulla strada del runner | **FATTO** (conseguenza di 1: `place_submin` sul runner, niente FOK diretto) |
| 4 | S7 chiusura paper senza size nota | **FATTO** (tolto il rimando solo-paper) |
| 5 | Timeout DB profilo bot in Omega e scanner | **FATTO** (misurato: nessuna query > 6,3 s) |
| 6 | R-2 lato Safe (`meta.canale_cor`) | **FATTO** (funziona anche senza `cor`) |
| 7 | Tennis: apertura sotto il minimo AL minimo su ogni strada | **FATTO** dietro import protetto (attivo quando D2 entra) |
| 8 | Test rosso dell'atlante | **FATTO**: era il TEST fragile, non il codice |

Patch: `AUDIT_2026-09-28/CANTIERE_P_su_master.patch` (= `git diff origin/master HEAD`, tutti i punti,
verificata con `git apply -R --check --cached`), `CANTIERE_P_blocco1.patch` (punti 1-4, contro la base
`4461227`), `CANTIERE_P_blocco3.patch` (= su_master).

## 1. Cause radice (con prova)

1.1 **Fill di casa (S3)** — `execution.place`, ramo `if mode == "paper":` dopo il gate (base: `execution.py:737-790`):
con gate della coda chiuso (runner giu', evento non in streaming, `execution_mode='rest'`) o canale giu' su una
chiusura (`_place_via_canale` torna None, `:454-459`), l'ordine paper veniva riempito da `E.paper_fill` sul libro
del feed dell'istante: istantaneo, senza bet delay, senza coda. Il live nello stesso punto va a Betfair (REST FOK).
Valeva per Safe calcio/tennis e per le chiusure di Omega che passano da `close_trade` (reperto C §6, reperto D2 F-1).

1.2 **S6** — stesso ramo: il sotto-minimo paper era un FOK diretto della size (`:725-736` + fill), mentre il live e'
parcheggio → taglio → riprezzo a LIMITE (puo' restare non abbinato).

1.3 **S7** — `close_trade` (base `:1602-1614`): solo in paper, senza size del book, la chiusura veniva rimandata
(`liquidita_del_book_ignota`); il live mandava l'ordine e decideva Betfair.

1.4 **Cancelli solo-paper collegati** (trovati nel lavoro): `bot_service._execute` rifiutava in paper senza riga del feed
(`paper_prezzi_non_disponibili`, costruiva la ladder per il fill di casa); `reconcile_pending` confermava una riga paper
senza marcatori coi dati della RISERVA (fill inventato, stesso difetto corretto da C su Omega, 1.3 del suo referto).

1.5 **`execution_mode='rest'` in paper** — col fill di casa tolto, 'rest' (scelta del pannello per i soldi veri) avrebbe
reso OGNI ordine paper «non eseguito» mentre il live parte: stessa regola di Omega (`_flumine_paper_gate`) applicata
alle aperture Safe (`bot_service._params_ordine`) e a tutte le chiusure (`close_trade`: chiamano solo Safe e Omega,
entrambi leggono la coda). NON in `execution._gate`: Mike passa apposta `execution_mode='rest'` (non legge la coda).

1.6 **R-2** — un ordine mandato sul canale arriva a Betfair col customerOrderRef di flumine, non `safe-t<id>`: la
riconciliazione per ref non lo trovava. In piu' `porta_ordini.MemoriaComandi.ricevi_evento` sostituiva l'evento per ref:
il `cor` (solo nel primo evento, D2 §2.7) si perdeva al secondo evento.

1.7 **Test atlante (punto 8)** — `test_selezione_esatto…::test_hint_coppia_presente_nellatlante_vero` calcolava l'atteso
da `SEL.ATLAS_PATH` (v2 committato), ma dal 24/09 `selezione.atlante()` legge `hazard_atlas.percorso_atlante()`
(`hazard_atlas_live.json` rigenerato ogni notte, se esiste). Sul PC dell'utente il live c'e' → 1,492 (live) contro 1,446
(v2). **Riprodotto** copiando il live del checkout principale nel worktree: rosso identico; col fix verde con e senza live.
Il codice e' giusto.

## 2. Cosa ho cambiato (file esatti)

Produzione:
- `Betfair/safe_strategy/execution.py`: paper senza runner = `PlaceOutcome("error", …, "paper_senza_runner:<motivo del gate>")`
  (freno unico ancora prima, stesso punto del live); via il ramo del fill di casa; via il rimando S7; `close_trade` valuta
  'rest' come 'auto' per le chiusure paper; `refs_di_riconciliazione` + uso in `reconcile_decision` e `_cleared_match`
  (R-2); tennis: `_e_tennis`, `_porta_al_minimo_tennis`, import protetto di `porta_al_minimo_apertura`.
- `Betfair/safe_strategy/bot_service.py`: `_params_ordine` (aperture paper), via il cancello `paper_prezzi_non_disponibili`,
  `reconcile_pending` paper senza marcatori → `error reconcile_paper_senza_runner`, R-2 in `_risolvi_una_via_canale`.
- `Betfair/safe_strategy/porta_ordini.py`: la memoria conserva il `cor` del primo evento.
- `Betfair/safe_strategy/certificazione_k.py`: `ref_di_riga` include `canale_cor`.
- `Betfair/safe_strategy/service.py` (scanner) `main`: `db_client.usa_timeout_bot()` (protetto).
- `Betfair/omega/omega_service.py` `main`: UNA riga, `usa_timeout_bot()` (punto 5, unico tocco a Omega di produzione).
- `Betfair/safe_strategy/selezione.py`: solo commento su `ATLAS_PATH`.
- `Betfair/safe_strategy/tools/replay_registrazioni.py`: solo la nota dello scenario `paper`.

Test nuovi: `Betfair/safe_strategy/tests/runner_finto.py` (monta il runner paper finto di Omega sul finto di Safe:
`follow`/`heartbeat` restano comandi dei test, payload in `db.queue`, `place_submin` paper; `esito_del_runner` = poll
vero + riallineamento dell'apertura), `test_p_nessun_fill_di_casa_2026_09_28.py` (11), `test_p_blocco3_2026_09_28.py` (18).
Test adeguati (ognuno con commento «CANTIERE P» che dice perche' era sbagliato): Safe `test_bot_service.py` (FakeDB col
runner, `_run`/`_cycle` col poll del giro dopo, 1 test riscritto sulla riga storica), `test_execution.py` (13),
`test_paper_fill_al_best_2026_09_26.py` (riscritto: fissava il fill di casa), `test_audit_2026_09_11.py` (3),
`test_avvio_app`, `test_b25_lascia_e_avvisa`, `test_chiudi_per_bot`, `test_d1_enqueue_ignoto`, `test_selezione_esatto`;
Omega (solo file di TEST, perche' le chiusure di Omega passano da `close_trade`): `test_omega_greenup_2026_09_10.py`
(runner finto nel `_DB`, poll nel `_run`, 2 xfail stretti del reperto P-O1), `test_omega_audit_2026_09_11.py` (4),
`tests/test_porta_ordini_omega_f6_2026_09_24.py` (1); stream `test_r3_freno_unico_2026_09_25.py` (2 Safe).
Strumenti: `AUDIT_2026-09-28/cantiere_p/falsifica_p.py`, `esito_falsificazione_blocco1_2.txt`, `esito_falsificazione_blocco3.txt`.

## 3. Test e falsificazioni

Dopo il merge di `d407b59`, dal worktree:
`.venv\Scripts\python.exe -m pytest Betfair/safe_strategy/tests Betfair/omega Betfair/mike/tests Betfair/stream/tests/test_r3_freno_unico_2026_09_25.py Betfair/stream/tests/test_submin_contratto_chiamanti_2026_09_17.py Betfair/stream/tests/test_db_client_timeout_bot_2026_09_28.py Betfair/stream/tests/test_arresto_ordinato_comportamento_2026_09_28.py Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py Betfair/stream/tests/test_motore_ordini_2026_09_24.py -q -p no:cacheprovider`
→ **4494 passed, 6 skipped, 3 xfailed, 0 failed** (201 s). Solo Safe: 1950 passed (65 s); Omega+Mike: 2372 passed, 2 xfailed.
Prima del merge anche ~30 file di `Betfair/stream` e `Betfair/tests` collegati: verdi salvo rossi PRE-ESISTENTI sulla base
(verificato rimettendo `execution.py`/`bot_service.py` di master: stessi rossi Mike/submin, poi chiusi da D1-bis).

Falsificazioni (`.venv\Scripts\python.exe AUDIT_2026-09-28\cantiere_p\falsifica_p.py`), **16 mutazioni, 16 ROSSE**,
ripristino SHA-256 identico, `MUTAZIONE`=0, `git diff` identico prima/dopo:
m1 fill di casa (11 rossi) · m2 'rest' non ignorato in chiusura (1) · m3 idem in apertura (2) · m4 rimando S7 (2) ·
m5 riga storica confermata dalla riserva (1) · m6 motivo rinominato (2) · m7 cancello `paper_prezzi_non_disponibili` (2) ·
m8 Omega senza timeout (1) · m9 scanner senza timeout (1) · m10 `cor` non salvato (1) · m11 riconciliazione senza `cor` (2) ·
m12 memoria che perde il `cor` (1) · m13 tennis non al minimo (2) · m14 chiusura tennis gonfiata (1) · m15 banco senza `cor` (1) ·
m16 cleared senza `cor` (1). Punto 8: rosso riprodotto col file live, verde dopo (con e senza live).

## 4. Migrazioni
Nessuna.

## 5. PARITA' PAPER / LIVE — Safe (base, esatto, punta, model, tennis) e chiusure Omega via `close_trade`

| # | Ramo | Paper | Live | Verdetto |
|---|---|---|---|---|
| S1 | accodamento a esito ignoto | pending, ref | pending, ref | uguale (D1) |
| S2 | gate della coda aperto | coda, FOK, LAPSE | coda, FOK, LAPSE | uguale |
| S3 | runner non raggiungibile (gate chiuso / canale giu' su chiusura) | **'error' `paper_senza_runner:<motivo>`**, nessun ordine | REST FOK | **CORRETTO**: il paper non inventa un esito; il live ha una strada in piu' perche' Betfair esiste (di natura) |
| S4 | FOK / parziali | li fa il runner (flumine) | Betfair | uguale |
| S5 | prezzo del fill | abbinamento del runner sul book vero | Betfair | uguale (non piu' il livello del feed) |
| S6 | sotto il minimo (place-and-trim) | `place_submin` sul runner, senza FOK | `place_submin` coda / `place_submin_live` REST | **CORRETTO** |
| S7 | chiusura senza size nota | parte (al runner), FOK | parte, FOK | **CORRETTO** |
| S8 | freno unico sulle aperture | stesso punto | stesso punto | uguale |
| S9 | riga pending senza marcatori | 'error' `reconcile_paper_senza_runner` | Betfair per bet_id/ref | **CORRETTO** (mai piu' la riserva confermata) |
| S10 | annullo sul canale senza ack | esito ignoto | ripiego REST | di natura |
| S11 | posizione di conto | non letta | letta | di natura |
| S12 | settlement | calcolo | cleared (ora anche per `canale_cor`) | uguale |
| S13-16 | tetti, richieste UI, proposte, mercati chiusi | — | — | uguale (D1) |
| S17 | `execution_mode='rest'` | valutato 'auto' (runner) | REST | **CORRETTO** (la scelta vale per i soldi veri) |
| S18 | riga del feed assente all'apertura | l'ordine parte come in live | parte | **CORRETTO** (tolto `paper_prezzi_non_disponibili`) |
| S19 | tennis apertura sotto il minimo | al minimo (coda/canale) | al minimo (REST) | **CORRETTO** a D2 integrato; prima: invariato e dichiarato nel log |
| S20 | riga live sul canale senza eventi | — | ritrovata su Betfair anche per `canale_cor` | **CORRETTO** (serve il runner che manda `cor`: tennis da D2) |
| S21 | chiusure Omega via `close_trade` | runner o non eseguita | REST FOK | **CORRETTO**; etichetta UI e stato del green-up: P-O1 corretto (§0-bis) |

## 6. Cosa NON ho fatto / NON ho potuto verificare
- P-O1: CORRETTO nella riconsegna (§0-bis); i 2 xfail sono stati tolti e sostituiti da test normali.
- Omega di produzione toccato: riga del timeout (punto 5), P-O1 e il ramo `paper_senza_runner` di `_greenup_send`
  (su richiesta del coordinatore). Il test `test_omega_audit::test_l03_stats_azzerate_a_bot_fermo` e' rosso SOLO se
  lanciato subito dopo il file greenup (inquinamento di stato di processo osservato gia' prima della riconsegna); verde
  da solo e nella suite intera di Omega. Non indagato oltre.
- L'evento `greenup` di Omega e l'evento `exit` di Safe si scrivono all'INVIO: col runner il fill e' in volo
  (`pending_fill`), quindi portano `state='pending'`/`locked_pnl=None`; lo stato della riga si aggiorna alla conferma.
- **Replay del banco NON lanciati** (li lancia il coordinatore).
- Tennis al minimo: attivo solo quando `porta_al_minimo_apertura` di D2 e' su master; il bump avviene DOPO il taglio a
  `best_size` (stesso comportamento del motore D2: con liquidita' sotto il minimo il FOK al minimo muore). La riga di
  riserva resta con la size calcolata finche' l'esito non la sovrascrive; la nota `meta.size_portata_al_minimo_da` lo dice.
- R-2: il `cor` lo manda oggi solo il runner tennis (D2); per il calcio il campo non c'e' e nulla cambia (testato).
- Mike: la sua ladder a liquidita' zero (`mike/service.py:808`) e `paper_no_fill` in `_NOTE_SENZA_RUNNER` ora sono
  inutili (il motivo nuovo `paper_senza_runner:…` e' gia' riconosciuto): NON tolti.
- `bot_service._paper_ladder` non e' piu' usata dalla produzione (resta, testata come funzione pura).
- Budget: CORRETTO nella riconsegna: col runner giu' nessun tentativo si consuma (§0-bis). Ogni giro a runner giu'
  lascia comunque una riga d'apertura 'error' col motivo per segnale (al piu' una ogni 5 s per segnale): visibile,
  non un tentativo.
- Timeout: misurato con `pg_stat_statements` e `pg_roles` (sola lettura): le query PostgREST di Omega/scanner arrivano
  al massimo a 6,3 s; `authenticator` ha `statement_timeout=8s` (il server taglia prima dei 20 s); l'atlante dello
  scanner usa urllib col suo timeout (180 s), non toccato. Non verificata una caduta di rete reale.

## 7. Decisioni per l'utente
Nessuna soglia, stake, selezione o regola d'uscita toccata. Nessuna decisione aperta (la regola dei tentativi a runner
spento l'ha fissata il coordinatore dal brief standard, par. 2 punti 6-7).

## 10. Asserzioni tolte o cambiate nei test (file per file)

Elenco riga per riga: `cantiere_p/asserzioni_tolte_o_cambiate.txt` (61 righe `-assert` del diff contro staging). Per
ogni test: cosa provava e cosa lo sostituisce. Nessuna asserzione tolta senza sostituto.

| File :: test | Provava | Sostituita da |
|---|---|---|
| safe `test_execution` :: `place_paper_riempie_al_prezzo_e_cappa_alla_liquidita` (4) | fill di casa sincrono open/12/3,0 | `test_place_paper_senza_runner_non_esegue_nulla` + `test_place_paper_col_runner_cappa_alla_liquidita_e_accoda` (size 12 in coda, FOK) |
| `place_paper_eccezione_del_fill_resta_pending` (2) | eccezione di `paper_fill` | `test_place_paper_non_chiama_mai_il_simulatore_di_casa` |
| `close_trade_crea_la_gamba…_marca_hedged` (2) | hedged sincrono, `locked_pnl` del ritorno | stesso test col runner: hedged dopo il poll, `locked_pnl == planned_lock` |
| `gate_chiuso_se_heartbeat_stantio` (1) | open a gate chiuso | stesso test: `paper_senza_runner:runner_heartbeat_stantio` |
| `close_trade_parziale_…_chiude_il_resto` (1) | `r2["hedged"] is True` sincrono | `pending_fill` + stato dopo il poll (hedged, residuo, locked -2) |
| `close_trade_paper_senza_size_del_book_non_riserva_nulla` (3) | rimando S7 solo-paper | `…_va_al_runner_come_il_live` + `test_close_trade_senza_size_paper_e_live_partono_uguali` |
| `place_sotto_il_minimo_senza_coda_paper_si_live_no` (2) | FOK diretto del sotto-minimo | `…_senza_coda_ne_paper_ne_live` + `test_place_sotto_il_minimo_paper_va_al_place_and_trim_del_runner` |
| `place_paper_minimo_non_blocca_la_gamba_di_chiusura` (1) | open 1,4 sincrono | stesso test: `place` FOK che riduce, 1,4 in coda |
| `paper_non_accetta_un_fill_parziale_come_il_fok_live` (3) | `paper_fok_parziale` di casa | stesso test: FOK in coda, runner che uccide -> riga error `flumine_terminal` |
| `paper_accetta_il_fill_completo` (1), `paper_size_cappata…` (1) | open sincrono | open dopo il poll; size 12 in coda |
| `il_piazzamento_in_paper_racconta_come_e_andato` (7) | storia dell'ordine del fill di casa | `test_il_piazzamento_in_paper_con_rest_non_si_simula_in_casa`; la storia dell'ordine paper la scrive chi risolve dal runner (`_risolvi_una_via_canale`, gia' testato) |
| safe `test_paper_fill_al_best` :: `_place` e 4 test (11) | contratto del fill di casa al best | file riscritto: 6 scenari x (`test_a_runner_giu_nessun_fill_di_casa`, `test_col_runner_l_ordine_parte_al_limite_col_fok`) + `_paper_ladder` pura |
| safe `test_bot_service` :: `running_piazza_il_segnale` (1) | kind 'place' | `place_pending` + `flumine_fill` + coda paper |
| `reconcile_paper_riga_storica_…_si_conferma_ancora` (1) | conferma dai dati della riserva | `…_non_si_conferma_piu` (error + riepilogo) |
| `exit_tennis_profit_al_game_vinto`, `uscita_a_tempo_esce_se_il_rischio…`, `uscita_a_tempo_in_profitto…`, `hold_non_blocca…`, `uscita_modello_take_profit` (5) | `locked_pnl` nell'evento 'exit' sincrono | stesso valore letto sull'apertura dopo il poll (`meta.locked_pnl`) + `pending_fill` nell'evento |
| `exit_residuo_dopo_fill_cappato…` (2) | `residual_after` nell'evento | `pending_fill`; il residuo vero (0,92 / <0,01) asserito sull'apertura |
| safe `test_audit` :: `m06_copertura_parziale…` (2) | `residual_size`/`locked_pnl` dal ritorno | stessi valori sull'apertura dopo il poll |
| `m31_in_paper_qualsiasi_importo_si_abbina` (4) | open sotto-minimo di casa | `place_submin` in coda con `target_size` esatta, chiusura FOK che riduce, runner giu' = `paper_senza_runner` |
| safe `test_d1_enqueue_ignoto` :: `accodamento_CERTAMENTE_mancato…` (2) | paper open dal fill di casa | paper `paper_senza_runner:enqueue_failed`, live REST invariato |
| stream `test_r3_freno_unico` :: 2 test Safe (2) | chiusura/apertura paper open | il freno non ferma le chiusure: arrivano al trasporto (`paper_senza_runner`) |
| omega `test_omega_greenup` :: `trigger_gol…` (1) | `g["state"]=="done"` nell'evento all'invio | stato 'done' asserito sulla RIGA dopo la conferma; evento 'pending' + `pending_fill` |
| omega `test_omega_audit` :: `h04…` (1) | idem (evento) | idem |
| omega `test_porta_ordini_f6` :: `cashout_a_canale_giu…` (1) | chiusura open di casa | gamba `pending` sulla coda col marcatore |

## 8. Controlli dal vivo in PAPER (29/09)
| controllo | atteso | dove |
|---|---|---|
| nessun fill di casa | 0 righe paper con `meta.fill` che inizia per `paper_fill:` dal riavvio | `safe_strategy_trades` |
| runner giu' | righe `error` con `meta.reason` `paper_senza_runner:<motivo>` e attivita' `place_retry`; uscite `cashout_error` e `exit_requested.last_error='chiusura_non_eseguita'`, ritentate | `safe_strategy_trades`, `safe_strategy_activity` |
| runner su | aperture/chiusure paper con `flumine_client_ref` o `canale_ref`, `fill='flumine_paper'` | `safe_strategy_trades.meta` |
| chiusure Omega paper | niente fill istantaneo: `pending` poi `open` dal runner | `omega_trades` |
| timeout | log `timeout PostgREST del profilo bot: Timeout(connect=5.0, read=20.0, …)` per `[omega]` e `[safe-scan]` | log dei processi |
| tennis (dopo D2) | apertura BACK < 2,00 piazzata a 2,00, `meta.size_portata_al_minimo_da` | `safe_strategy_trades` |

## 9. Replay di Safe da rilanciare (coordinatore, uno alla volta)
```
python -m Betfair.stream.backtest.certifica safe_base 35760084 --scenari rapidi --trasporto entrambi
python -m Betfair.stream.backtest.certifica safe_esatto 35760084 --scenari rapidi --trasporto entrambi
python -m Betfair.stream.backtest.certifica safe_punta 35760084 --scenari rapidi --trasporto entrambi
python -m Betfair.stream.backtest.certifica safe_tennis 35795993 --scenari rapidi --trasporto entrambi
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari rapidi --trasporto entrambi
```
Atteso: live invariato; lo scenario storico `paper` del replay Safe ora da' zero ingressi (nota aggiornata).
