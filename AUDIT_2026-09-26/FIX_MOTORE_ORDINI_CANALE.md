# FIX MOTORE ORDINI via canale: reperti del riavvio 2 (26/09)

Worktree `agent-a1f3418de07ca7726`, base `36e7795`. Niente commit. **`runner.py` e `tennis_runner.py` NON toccati.**
Fonti dei reperti: `AUDIT_2026-09-25/E2E_FASE2_BOT_PAPER_2026-09-26.md` (R-F2-16/18/19), `AUDIT_2026-09-25/e2e_fase2/ADMIN26_ORDINI_SCHEDE.md` (R9-R12).

## File toccati
- `Betfair/stream/motore_ordini.py`: lato, riduzione, fase, aggancio, source, seq (solo la doc), ref interni
- `Betfair/stream/db.py`: hook `source` dello specchio + ripiego se il CHECK la rifiuta
- `Betfair/stream/live_order_worker.py`: lato nel journal, `_base_rid_avvio` / `_LOCAL_RID`
- `Betfair/stream/tennis_live/tennis_live_order_worker.py`: `_base_sid_avvio` / `_LOCAL_SID`, `source` in `_track_manual`
- `Betfair/stream/reconcile_worker.py`: voce della composizione dalla `source` di un bot
- `migrations/betfair_live_orders_source_bot_2026-09-26.sql` (NUOVA, **da applicare a cura dell'utente**)
- test nuovo: `Betfair/stream/tests/test_motore_ordini_riavvio2_2026_09_26.py` (38 test)
- test esistenti adeguati al nuovo comportamento voluto: `test_motore_ordini_2026_09_24.py:344` ('back' ora ammesso, lato non valido = 'Back'),
  `test_porta_banco_f4_2026_09_24.py:103` (idem), `test_auto_follow_2026_09_25.py` (`test_runner_fermo_accetta_in_aggancio_e_chiede_l_aggancio`),
  `test_tempi_ordine_f0_2026_09_25.py:292,400` (il ref non comincia più con `awlq9`/`awtq9`)
- `AUDIT_2026-09-26/falsifica_motore_canale.py` (script di falsificazione)

## 1. JOURNAL KO (alert 511, R-F2-18), priorità 1
- **Causa**: `motore_ordini.valida_comando` accettava solo `"BACK"`/`"LAY"` e metteva nella riga il valore GREZZO (`riga["side"] = lato`).
  La riga va a `_job_locale`, quindi a `_record_local_request` (coda, `CHECK side IN ('back','lay')`) e poi a `_journal_scrivi`
  (`betfair_live_journal_side_check`). Tutte e due le insert venivano rifiutate: giornale bucato, e **anche la riga della coda** (storico e follow-through).
- **Correzione**: `motore_ordini.py:419-425`: si accettano `BACK/LAY/back/lay` e la forma si normalizza UNA volta (`lato.lower()`, la forma della coda).
  In più `live_order_worker.py:1144` (`_journal_scrivi`) abbassa il lato anche da solo, come difesa in profondità.
  Rischio collaterale chiuso: `riduce_esposizione` confrontava `side == "BACK"`, quindi un 'back' veniva letto come LAY.
  Ora `motore_ordini.py:473` usa `str(side).upper()`. Il resto del motore usava già `.lower()`, `build_order` accetta entrambe le forme,
  il tennis fa `.upper()` (`tennis_live_order_worker.py:587`).
- **Test**: `test_comando_col_lato_api_scrive_giornale_e_coda_in_minuscolo[4]`: DB finto con i CHECK veri, giornale e coda scritti, nessun alert JOURNAL,
  l'ordine flumine resta BACK/LAY. Poi `test_lato_non_ammesso_resta_rifiutato[5]`, `test_journal_scrivi_abbassa_il_lato_anche_da_solo`,
  `test_riduzione_uguale_per_lato_maiuscolo_e_minuscolo[4]`.

## 2. source = nome del bot (R9 / R-F2-16), priorità 2
- **Causa (calcio)**: la riga dello specchio la costruisce `LiveTradingStrategy._order_row` senza `source`, quindi prende il DEFAULT 'runner'.
  **Causa (tennis)**: `_track_manual` scriveva `"source": "manual"` fisso.
- **Correzione (calcio)**: `motore_ordini.py:1352` `sorgente_ordine(payload)` restituisce l'attore del comando, cercato in RAM in `_rif_interni` per ref interno e mode.
  Il desktop non ha source (resta 'runner'), e nemmeno un ordine non nato da un comando. Lo hook si registra in `avvia`/`ferma`
  (`db.aggiungi_sorgente_ordini`/`rimuovi_sorgente_ordini`). `db.upsert_live_order` (`db.py:567-576`) aggiunge `source` **solo alla riga del DB**:
  publish ed eventi restano la riga di sempre, quindi il contratto «riga identica» degli eventi è rispettato.
  **Il CHECK di produzione ammette solo `('runner','account','scalper')`.** Per questo `_upsert_specchio` (`db.py:589`), se il DB rifiuta
  `betfair_live_orders_source_check`, riscrive la riga SENZA source: lo specchio non si perde mai, anche prima della migrazione.
  Serve la migrazione `migrations/betfair_live_orders_source_bot_2026-09-26.sql` (NOT VALID, idempotente, stessa regola della sezione 7 dello scalper).
- **Correzione (tennis)**: `tennis_live_order_worker.py:966`. `source` = `_CONTESTO.strategy_ref`, impostato solo dal motore e uguale all'attore
  (es. 'safe_tennis'). Coda DB, /order del desktop e attore 'desktop' restano 'manual'. `tennis_live_orders.source` non ha CHECK.
- `reconcile_worker._fonte_di` (`reconcile_worker.py:787-793`): source 'omega'/'mike'/'safe'/'safe_tennis' vanno alla voce del bot
  (prima finivano in «manuale_app»). La riga del bot trovata per bet_id ha comunque la precedenza, come prima.
- **Test**: `test_specchio_di_un_comando_porta_il_nome_del_bot[omega,safe,mike]`, `test_specchio_del_desktop_resta_runner`,
  `test_specchio_senza_migrazione_si_scrive_lo_stesso`, `test_specchio_con_migrazione_applicata_tiene_la_source`,
  `test_upsert_sincrono_senza_scrittore_ripiega_senza_source`, `test_migrazione_source_ammette_i_bot_e_non_il_desktop`,
  `test_tennis_track_manual_source_dell_attore`, `test_reconcile_voce_della_source_del_bot`.

## 5. R11 ref interni univoci fra avvii (MONEY-CRITICAL in live), priorità 3
- **Causa**: `live_order_worker.py` (prima alla riga 3087) aveva `_LOCAL_RID = count(9_000_000_000)`, e il tennis `_LOCAL_SID` uguale (prima alla riga 1302).
  A ogni avvio `awlq9000000000` si ripete e lo specchio fa upsert su `(mode, client_order_ref)`. In più `local<rid>`/`cmd<sid>`
  (client_ref UNIQUE della coda) venivano rifiutati dal secondo avvio in poi.
- **Correzione**: `live_order_worker.py:3091-3104` `_base_rid_avvio()` = ms d'avvio × 1000, e `tennis_live_order_worker.py:1308-1316`
  `_base_sid_avvio()` identico. L'id ha 16 cifre: è sopra la serie vecchia e il bigserial, sotto 2**53 (intero esatto in JSON/JS),
  e `awlq`+rid+suffisso gamba sta in 32 caratteri. Il riconoscimento del ref nel motore non assume più 10 cifre fisse
  (`motore_ordini.py:1337` `_rif_interno_di`: tutte le cifre dopo il prefisso; le gambe `...x1`/`...d0` restano legate al comando).
  Il `customerRef` anti-DUPLICATE_TRANSACTION non cambia: è quello di flumine (name_hash+uuid, per tentativo), il nostro `awlq` non viaggia verso Betfair.
- **Test**: `test_rid_di_due_avvii_successivi_mai_uguali`, `test_rid_valido_per_bigint_json_e_ref_betfair`, `test_rid_tennis_univoco_fra_avvii`,
  `test_eventi_dallo_specchio_con_ref_lunghi_e_gambe`.
- **Limite dichiarato**: l'univocità presuppone che l'orologio non torni indietro fra due avvii più di (comandi/1000) ms.

## 3 + 8. Aggancio (R12, omega-t124, safe_tennis-t346), priorità 4
- **Causa**: con runner senza framework, `motore_ordini._controlla` (prima alla riga 872) chiedeva l'aggancio ma RIFIUTAVA (`runner_non_agganciato`).
  Nel caso di mercato non ancora sottoscritto, la scadenza di 3000 ms era troppo corta (dal vivo: 1113 e 2176 ms quando riuscito, t124 scaduto).
- **Correzione**: `motore_ordini.py:890-900`. Se l'aggancio è preso in carico (`richiedi` restituisce None), il piano viene marcato e
  `_serve_aggancio` (`:1101`) risponde ack ACCETTATO `in_aggancio`: il comando resta parcheggiato. `avanza_aggancio` (invariato) lo esegue
  solo quando c'è il framework e il mercato è servibile, rifacendo TUTTE le guardie. Oltre la scadenza c'è l'evento terminale 'rifiutato',
  senza nessun ordine. Il tetto pieno resta un rifiuto `runner_non_agganciato` con motivo; cancel/replace restano rifiutati.
  `AGGANCIO_MAX_MS_DEFAULT` passa a 10000 (`:121`), sempre regolabile con `MOTORE_AGGANCIO_MAX_MS`. L'età del comando si misura all'ARRIVO
  (`ricevuto_ms`), come già faceva il codice in `avanza_aggancio`. Mai un doppio invio: il ref è registrato nel dedup all'ack, e il parcheggio esegue una volta sola.
- **Test**: `test_aggancio_di_serie_dimensionato_sui_tempi_veri`, `test_runner_senza_framework_accetta_in_aggancio_e_serve_all_arrivo`
  (un solo invio), `test_runner_senza_framework_scadenza_rifiuto_certo_senza_ordine`, `test_eta_del_comando_contata_all_arrivo_non_durante_l_aggancio`,
  `test_runner_senza_framework_tetto_pieno_rifiuto_dichiarato`, `test_runner_senza_framework_cancel_resta_rifiutato`.
- **Per Betfair/omega (NON toccato)**: un rifiuto terminale con motivo che comincia per `in_aggancio`, o ack `runner_non_agganciato`, NON è un tentativo
  consumato: nessun ordine è partito. `omega_service` (fill/no-fill del canale, `_flumine_no_fill_error(reason="canale_rifiutato")`) deve riconoscere
  questo motivo e non incrementare `attempt` (R-F2-12, cantiere FIX-A della sessione B). Lo stesso vale per Safe (`execution.py:537-543`, `canale_rifiutato:<motivo>`).

## 7. R10 canale_fase, priorità 5
- **Causa motore**: `fase_da_riga` dava 'abbinato_parziale' a qualsiasi riga EXECUTABLE con size_matched>0, anche abbinata per intero.
- **Correzione**: `motore_ordini.py:498-504`: con size>0 e size_matched ≥ size la fase è 'abbinato' (terminale).
  Test: `test_fase_segue_l_abbinato_reale[3]`, più i parametri esistenti di `test_fase_da_riga`, che restano verdi.
- **NON FATTO (fuori perimetro, lato bot)**: `canale_fase` NULL su omega-t124/t125 e safe-t349. La colonna si scrive solo negli eventi INTERMEDI
  (`omega_service.py:2940-2942` `_aggiorna_da_evento`, `safe_strategy/bot_service.py:967-970`). Gli eventi terminali passano da
  `_flumine_confirm`/`_flumine_no_fill_error`, che non scrivono `canale_fase`. Da correggere in Betfair/omega e Betfair/safe_strategy
  (scrivere `canale_fase`/`canale_seq` anche sul terminale).

## 4. seq duplicato fra attori (R-F2-19), priorità 6
- **Decisione (una sola, documentata in `motore_ordini._prossimo_seq`)**: il seq resta **PER ATTORE**. La porta di ogni bot (`safe_strategy/porta_ordini.py:379-399`
  `_avanza_seq`) conta i buchi sul seq contiguo del suo attore: un seq globale aprirebbe un buco (e un `da_seq`) a ogni messaggio di un altro bot.
- Consumatori verificati: porte omega/safe (una connessione = un attore); `omega_service.py:2940` e `bot_service.py:967` confrontano il seq dentro la STESSA riga
  (stesso attore); UI `esitoAbbinamento.ts:562-569` lo mostra soltanto; `esiti_ordini_canale.py` non lo usa; banco: nessun uso.
  `_rispondi_da_seq` usa `_memoria[attore]`/`_seq[attore]`. Nessun consumatore usa il seq da solo fra bot diversi.
- **Test**: `test_seq_per_attore_contiguo_e_da_seq_per_attore` (contiguità per attore, stesso numero fra attori, `da_seq` che rimanda solo i messaggi dell'attore).

## Falsificazione (eseguita, tutte ROSSE, file ripristinati con sha256)
`python AUDIT_2026-09-26/falsifica_motore_canale.py`:
M1 lato grezzo 4 rossi · M2 niente source 6 · M3 runner fermo rifiuta 3 · M4 rid da 9000000000 4 · M5 seq globale 1 · M6 fase parziale 1 ·
M7 niente ripiego source 2 · M8 journal grezzo 1 · M9 tennis 'manual' fisso 1 · M10 aggancio 3000 1 · M11 riduzione case-sensitive 2 · M12 source anche al desktop 1.

## Comandi per rieseguire
```
set SUPABASE_URL=http://127.0.0.1:9 & set SUPABASE_SERVICE_ROLE_KEY=x & set SUPABASE_KEY=x
python -m pytest Betfair/stream/tests/test_motore_ordini_riavvio2_2026_09_26.py -q -p no:cacheprovider      # 38 passed
python -m pytest Betfair/stream/tests/test_motore_ordini_2026_09_24.py Betfair/stream/tests/test_auto_follow_2026_09_25.py Betfair/stream/tests/test_db_live_order.py Betfair/stream/tests/test_live_trading_strategy.py Betfair/stream/tests/test_live_journal.py Betfair/stream/tests/test_reconcile_worker.py Betfair/stream/tests/test_scalper_auto_mode_2026_09_25.py Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py Betfair/stream/tests/test_submin_contratto_chiamanti_2026_09_17.py Betfair/stream/tests/test_tempi_ordine_f0_2026_09_25.py Betfair/stream/tennis_live/tests/test_motore_ordini_tennis_2026_09_25.py Betfair/stream/tests/test_porta_banco_f4_2026_09_24.py Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py Betfair/stream/tests/test_scalper_certificazione_2026_09_24.py Betfair/omega/tests/test_porta_ordini_omega_f6_2026_09_24.py Betfair/safe_strategy/tests/test_porta_ordini_f5_2026_09_24.py Betfair/safe_strategy/tests/test_safe_tennis_canale_f8_2026_09_25.py -q -p no:cacheprovider
python AUDIT_2026-09-26/falsifica_motore_canale.py
```

## Esiti dei test esistenti
Tutti verdi, con due eccezioni.
- `test_auto_follow_2026_09_25.py::test_latenza_logica_aggancio_sotto_i_20_ms` è ROSSO **anche sul codice di HEAD**: 37 ms misurati con i moduli originali rimessi al loro posto.
  Sul mio codice ho misurato 65-335 ms, con la macchina carica (un singolo test impiega 12-41 s). È un test di tempo, sensibile al carico: da rilanciare a macchina scarica.
- `Betfair/omega/tests/test_esiti_ordini_canale_2026_09_23.py`: 11 rossi **identici su HEAD** (`db.trades[0]` IndexError in `_piazza_in_coda`). Sono preesistenti e non legati a questo diff.

## NON FATTO / non verificato
- Il replay del banco `certifica safe_base/omega/safe_tennis --scenari rapidi --trasporto entrambi` NON è stato lanciato: lo rilancia il coordinatore.
  Da guardare: gli ordini via canale ora portano il lato minuscolo nella riga (la parità coda/canale dovrebbe migliorare) e i rid hanno 16 cifre.
- `canale_fase` NULL sui terminali: lato bot (vedi §7), file `Betfair/omega/omega_service.py:2934-2950` e `Betfair/safe_strategy/bot_service.py:955-975`.
- Tentativo di Omega non consumato per `in_aggancio`/`runner_non_agganciato`: lato bot (vedi §3).
- Migrazione `betfair_live_orders_source_bot_2026-09-26.sql` da applicare. Senza, le righe restano 'runner' (con un warning nel log per ogni riga
  di un bot), senza perdite. Nota: anche le righe `bot:<ref>` della riconciliazione (`reconcile_worker.py:323`) violano lo stesso CHECK, se esiste in produzione. È un reperto preesistente, non toccato.
- Journal: `origin` resta 'manual' anche per i comandi dei bot (`_journal_scrivi`, `live_order_worker.py:1087`). Non toccato perché la colonna potrebbe avere un CHECK: da decidere.
- Non ho letto il DB di produzione: che il CHECK della source esista è dedotto dalle migrazioni.

## Rischi residui
- Il warning del ripiego della source si ripete a ogni scrittura di una riga di un bot, finché la migrazione non è applicata (rumore nel log, nessun danno).
- Con 10 s di aggancio un ordine può partire fino a 10 s dopo la decisione del bot. Il prezzo resta il limite del bot (Safe FOK, Omega limite) e l'età è misurata all'arrivo.
  I bot vedono ack «accettato in_aggancio» e la riga resta `pending` fino all'evento terminale.
