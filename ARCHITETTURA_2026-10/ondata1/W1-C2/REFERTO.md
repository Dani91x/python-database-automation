# REFERTO W1-C2 — libro ordini del conto, P&L di mercato, riconciliazione in ombra (09/10/2026)

Ramo `architettura/w1-c2` da `559a96df`. Agente W1-C2 (ondata 1). Nessun file esistente modificato: solo file nuovi del
dominio C2. Doc del comparto: `Betfair/nucleo/ordini/doc/C2_LIBRO_RICONCILIAZIONE.md`.

## 1. Cosa ho costruito (e cosa NON fa)

| File (righe) | Punti chiave |
|---|---|
| `Betfair/nucleo/ordini/attribuzione.py` (398) | `regole_di_oggi` `:106` (costanti IMPORTATE, import pigro, una volta per processo); `attribuisci_riferimenti` `:224` (rfs/rfo); `_da_attore` `:256` (ref storico condiviso e Safe tennis REST); `Indizio` `:189` + `indizio_da_motivo` `:274`, `indizi_da_riga_coda` `:293`, `indizio_da_riga_bot` `:311`; `attribuisci` `:359` (il piu' forte indizio di un bot vince, conflitto scritto); `attribuisci_dichiarato` `:381` (paper) |
| `Betfair/nucleo/ordini/libro_conto.py` (383) | `OrdineInProva` `:61` + `SorgenteOrdiniProva` `:71` (protocollo paper); `ordine_da_riga_conto` `:97` / `ordine_da_corrente` `:137` (grafia di `listCurrentOrders`, campo essenziale mancante = `ValueError`); `fase_dell_ordine` `:150` (riuso `motore_ordini.fase_da_riga`); `componi_ordine_conto` `:161`; `LibroConto` `:184` (chiave `(modo, bet_id)`, `RLock`, messaggio piu' vecchio ignorato `:244`, tetto che dimentica solo i terminali `:276`, consumatori fuori dal lucchetto `:312`); `comandi_ammessi` `:378` (proposta) |
| `Betfair/nucleo/ordini/pnl_mercato.py` (198) | `esposizioni_per_selezione` `:87` (CHIAMA `flumine.utils.calculate_matched_exposure`); `pnl_se_vince` `:107` (`pnlSeVince` del ladder riga per riga); `pnl_bloccato` `:122` (`lockedPnlAt`); `calcola` `:151` (totale e per autore, abbinato e prezzo medio per lato con `flumine.utils.wap`, esposizione massima, mercati a linee) |
| `Betfair/nucleo/ordini/riconciliazione.py` (383) | `in_volo_dal_diario` `:136` (regole di R2); `RiconciliatoreOmbra.giro` `:204`; `_conto_contro_specchio` `:244` e `_specchio_contro_conto` `:289` (regole di R1, giri consecutivi come `_MISSING_SEEN`); `_blotter_contro_conto` `:321`; `_posizioni` `:364` |
| test `Betfair/nucleo/ordini/tests/test_c2_{aiuti,attribuzione,libro_conto,pnl_mercato,riconciliazione,revisione}.py` | 197 test (dopo la revisione, par. 10) |

NON fa: nessuna rete, DB, file o thread propri; non piazza ne' annulla; non scrive lo specchio ne' gli alert (l'ombra
NON SCRIVE: provato anche sul sorgente); non legge il DB per gli indizi (li riceve come dati: la lettura resta
`esposizione_fuori_bot.proprietari_bot` / `reconcile_worker._proprietari`); non applica la commissione (vedi par. 3);
non calcola il «se vince» dei mercati a linee asiatiche (vuoto + esposizione prudente, dichiarato).

## 2. Contratto

Implementati: `LibroOrdiniConto` (`LibroConto`), consumati `FlussoOrdiniConto` e `OrdineDalConto` (A), prodotti
`OrdineConto`, `PosizioneMercato`, `StatoOrdine`, `PosizioneConto` (C). Contratti NON toccati.

Estensioni proposte (tipi miei, additivi, da portare nel contratto se il coordinatore vuole):
1. `SorgenteOrdiniProva` + `OrdineInProva` (`libro_conto.py:61-75`): la sorgente paper con l'attore dichiarato.
2. `EsposizioneSelezione` (`pnl_mercato.py:54`): «se vince / se perde» della selezione DA SOLA (cio' che il ladder mostra
   per riga, oggi `matched_if_win/lose` di `betfair_live_positions`); `PosizioneMercato` ha solo il P&L di mercato.
3. `Attribuzione` (motivo, fonte, conflitto) accanto a `OrdineConto.autore`: la UI puo' mostrare il perche'.
4. `PosizioneConto` non ha `handicap`: le selezioni a linee si contano e si saltano (`posizioni_a_linee_saltate`).
5. `FaseOrdine` del contratto e fasi del motore hanno due vocabolari (`abbinato_parziale` vs `parziale`,
   `accettato_betfair` vs `accettato`): `OrdineConto.stato` porta la fase del MOTORE (quella che la UI conosce gia'),
   `StatoOrdine.fase` quella del contratto (mappa `riconciliazione.FASE_CONTRATTO`).

## 3. Parita'

| Funzione di oggi (file:riga) | Nuova | Test | Esito |
|---|---|---|---|
| `esposizione_fuori_bot.motivo_bot_da_riferimenti` `:171` + `bot_di` `:226` (W2/W3a) | `attribuisci_riferimenti` | `test_c2_attribuzione.py::test_parita_con_la_classificazione_di_oggi` (48 riferimenti GENERATI dal codice di produzione, compresi i runner standalone, tabella sotto) | uguale su 39; 9 divergenze in elenco chiuso D1 (2), D2 (4), D3 (1), D9 (1), D5+D9 (1) (par. 9) |
| `reconcile_worker._classify_cleared_order` `:670` (R1 storico) | idem | idem | idem |
| `esposizione_fuori_bot.proprietari_bot` `:85` + `motivo_bot_da_coda` `:191` (client supabase VERO, MockTransport) | `indizio_da_motivo` + `attribuisci` | `::test_indizi_dai_motivi_della_lettura_di_oggi_sul_client_vero` | stesso bot di `bot_di` sui 4 motivi |
| `reconcile_worker._proprietari` `:842` (riga `role='utente'` di Mike resta dell'utente) | `indizio_da_riga_bot` | `::test_indizi_tabella_vince_e_il_conflitto_si_scrive` | uguale |
| `motore_ordini.fase_da_riga` `:538` | `fase_dell_ordine` (riuso) | `test_c2_libro_conto.py::test_stato_e_la_fase_del_motore_di_oggi` | identico (5 stati: accettato, parziale, abbinato, parziale poi annullato, LAPSE) |
| `esiti_ordini_canale.ordine_del_conto` `:737` | `ordine_da_corrente` (riuso) | `::test_rest_e_stream_danno_lo_stesso_ordine` | REST (`CurrentOrders`) e stream (`OrderBookCache`) danno lo stesso `OrdineDalConto` |
| `flumine Blotter.get_exposures` (`markets/blotter.py:237`, oggetti VERI) | `esposizioni_per_selezione` | `test_c2_pnl_mercato.py::test_esposizioni_per_selezione_identiche_al_blotter_di_flumine` (8 griglie) + `::test_blotter_caso_fisso_non_a_vuoto` | identico al centesimo (stessa funzione) |
| `replayOperazioni.ts:189-197` `pnlSeVince` | `pnl_se_vince`, `PosizioneMercato.se_vince` | `::test_se_vince_identico_alla_formula_del_ladder` (12 griglie, totale e per autore) + `::test_il_sorgente_ts_contiene_ancora_le_formule_citate` | identico non arrotondato; `se_vince` = `round(.,2)` |
| `ladderMath.ts:10-13` `lockedPnlAt` | `pnl_bloccato` | `::test_green_up_e_lockedpnl_sulla_stessa_posizione` | identico |
| `trading/greenup.py:118` `compute_greenup` (f=1, target) | `pnl_bloccato` sulla stessa posizione | idem | uguale entro lo scarto della size arrotondata al centesimo dell'ordine vero (0,005 x prezzo + 0,01) |
| `reconcile_worker._reconcile_orders` `:359` (R1, client supabase VERO, 8 scenari x 2 giri) | `RiconciliatoreOmbra.giro` | `test_c2_riconciliazione.py::test_parita_con_r1_giro_per_giro` | stessi upsert, update, avvisi «assente da 2 giri» e conteggio esterni, giro per giro; `ATTESI_R1` prova che R1 scrive davvero |
| `motore_ordini.MotoreOrdini.riprendi_da_diario` `:2506` (R2, `Diario` VERO) | `in_volo_dal_diario` | `::test_parita_con_r2_riavvio_con_ordini_in_volo` (+ secondo riavvio con le righe `ripresa`) | stessi esiti: ritrovato, non_trovato, mai_inviato_place, perso_paper |

COMMISSIONE: non applicata, come nelle viste di oggi per lo stesso numero (`lockedPnlAt`, `pnlSeVince`,
`get_exposures` sono lordi); la regola per ordine (`commissioni_per_ordine`, F-009) resta al regolato. Dichiarato in
`pnl_mercato.py` e provato da `::test_commissione_non_applicata`.

Tabella dei riferimenti (GENERATA da `tabella_parita()` del test, non scritta a mano; il `customerOrderRef` di flumine
e' `name_hash-<id>` di `Order.customer_order_ref`):

| origine (codice di oggi che lo scrive) | customerStrategyRef | customerOrderRef | autore | W2 (fuori_bot + bot_di) | R1 storico | div. |
|---|---|---|---|---|---|---|
| runner calcio coda/desktop | `live` | `<name_hash>-<id>` (flumine) | **sconosciuto** | utente | manual_app | D9 |
| runner tennis coda/desktop | `tennis` | `<name_hash>-<id>` (flumine) | **sconosciuto** | tennis | manual_app | D5+D9 |
| motore calcio attore desktop | `desktop` | `<name_hash>-<id>` (flumine) | **desktop** | desktop | ours | D1 |
| motore tennis attore desktop | `desktop` | `<name_hash>-<id>` (flumine) | **desktop** | desktop | ours | D1 |
| motore calcio attore mike | `mike` | `<name_hash>-<id>` (flumine) | **mike** | mike | ours |  |
| motore tennis attore mike | `mike` | `<name_hash>-<id>` (flumine) | **mike** | mike | ours |  |
| motore calcio attore omega | `omega` | `<name_hash>-<id>` (flumine) | **omega** | omega | ours |  |
| motore tennis attore omega | `omega` | `<name_hash>-<id>` (flumine) | **omega** | omega | ours |  |
| motore calcio attore safe | `safe` | `<name_hash>-<id>` (flumine) | **safe** | safe | ours |  |
| motore tennis attore safe | `safe` | `<name_hash>-<id>` (flumine) | **safe** | safe | ours |  |
| motore calcio attore safe_tennis | `safe_tennis` | `<name_hash>-<id>` (flumine) | **safe_tennis** | safe_tennis | ours |  |
| motore tennis attore safe_tennis | `safe_tennis` | `<name_hash>-<id>` (flumine) | **safe_tennis** | safe_tennis | ours |  |
| motore calcio attore tennis_flb | `tennis_flb` | `<name_hash>-<id>` (flumine) | **tennis_flb** | tennis_flb | ours |  |
| motore tennis attore tennis_flb | `tennis_flb` | `<name_hash>-<id>` (flumine) | **tennis_flb** | tennis_flb | ours |  |
| motore calcio attore tennis_pro | `tennis_pro` | `<name_hash>-<id>` (flumine) | **tennis_pro** | tennis_pro | ours |  |
| motore tennis attore tennis_pro | `tennis_pro` | `<name_hash>-<id>` (flumine) | **tennis_pro** | tennis_pro | ours |  |
| motore calcio attore tennis_scalper | `tennis_scalper` | `<name_hash>-<id>` (flumine) | **tennis_scalper** | tennis_scalper | ours |  |
| motore tennis attore tennis_scalper | `tennis_scalper` | `<name_hash>-<id>` (flumine) | **tennis_scalper** | tennis_scalper | ours |  |
| motore calcio attore tennis_swing | `tennis_swing` | `<name_hash>-<id>` (flumine) | **tennis_swing** | tennis_swing | ours |  |
| motore tennis attore tennis_swing | `tennis_swing` | `<name_hash>-<id>` (flumine) | **tennis_swing** | tennis_swing | ours |  |
| omega REST gamba | `omega` | `omega-t7` | **omega** | omega | ours |  |
| omega REST storico | `omega` | `omega-t7` | **omega** | omega | ours |  |
| omega REST storico | `omega` | `omega-m7` | **omega** | omega | ours |  |
| omega REST storico | `omega` | `omega-t7` | **omega** | omega | ours |  |
| omega REST storico | `omega` | `omega-34567890` | **omega** | omega | ours |  |
| omega REST default | `omega` | `omega-34567890` | **omega** | omega | ours |  |
| omega REST submin default | `omega` | `submin-34567890` | **omega** | omega | ours |  |
| mike REST | `mike` | `mike-t7` | **mike** | mike | ours |  |
| safe calcio REST | `safe` | `safe-t7` | **safe** | safe | ours |  |
| safe tennis REST | `safe` | `safe_tennis-t7` | **safe_tennis** | safe | ours | D2 |
| safe calcio REST storico | `omega` | `safe-t7` | **safe** | omega | ours | D2 |
| safe tennis REST storico | `omega` | `safe_tennis-t7` | **safe_tennis** | omega | ours | D2 |
| mike REST storico (pre L1) | `omega` | `mike-t7` | **mike** | omega | ours | D2 |
| scalper maker | `scm34567890` | `<name_hash>-<id>` (flumine) | **scalper** | scm34567890 | ours |  |
| scalper media | `mu34567890` | `<name_hash>-<id>` (flumine) | **scalper** | mu34567890 | ours |  |
| scalper sniper | `scn34567890` | `<name_hash>-<id>` (flumine) | **scalper** | scn34567890 | ours |  |
| scalper theta | `sct34567890` | `<name_hash>-<id>` (flumine) | **scalper** | sct34567890 | ours |  |
| bot tennis tennis_flb in flumine | `TennisFLBStrate` | `<name_hash>-<id>` (flumine) | **tennis_flb** | tennisflbstrate | ours |  |
| bot tennis tennis_pro in flumine | `TennisProStrate` | `<name_hash>-<id>` (flumine) | **tennis_pro** | tennisprostrate | ours |  |
| bot tennis tennis_scalper in flumine | `TennisScalperSt` | `<name_hash>-<id>` (flumine) | **tennis_scalper** | tennisscalperst | ours |  |
| bot tennis tennis_swing in flumine | `TennisSwingStra` | `<name_hash>-<id>` (flumine) | **tennis_swing** | tennisswingstra | ours |  |
| standalone run_scalper.py ScalperStrategy | `ScalperStrategy` | `<name_hash>-<id>` (flumine) | **scalper** | scalperstrategy | ours |  |
| standalone run_scalper_live.py ScalperStrategy | `ScalperStrategy` | `<name_hash>-<id>` (flumine) | **scalper** | scalperstrategy | ours |  |
| standalone run_theta.py ThetaStrategy | `ThetaStrategy` | `<name_hash>-<id>` (flumine) | **scalper** | thetastrategy | ours |  |
| standalone run_tennis_pro.py TennisProStrategy | `TennisProStrate` | `<name_hash>-<id>` (flumine) | **tennis_pro** | tennisprostrate | ours |  |
| standalone run_tennis_scalper.py TennisScalperStrategy | `TennisScalperSt` | `<name_hash>-<id>` (flumine) | **tennis_scalper** | tennisscalperst | ours |  |
| terminale vecchio order_exec | `watchlist` | - | **sconosciuto** | watchlist | ours | D3 |
| sito Betfair | - | - | **sito** | utente | manual |  |

Ingressi veri: nessuna registrazione di ordini del conto esiste in `registrazioni_banco/` (sono stream di MERCATO);
gli ordini dei test sono il JSON di `listCurrentOrders` e i messaggi `ocm` passati dalle classi VERE di
betfairlightweight. La parita' su ordini reali e' l'ombra di T11 (N giornate, par. 8).

## 4. Migliorie misurate

Nessuna miglioria rivendicata (nessun equivalente di oggi da battere: il ladder legge oggi lo specchio dal DB o il
topic `conto` senza autore ne' P&L di mercato). Costi misurati (macchina condivisa, carico ~8, `time.perf_counter_ns`,
`tracemalloc`): `ricevi_live` p50 15 us / p95 29 us / p99 78 us (2000 ordini); libro con 2000 ordini ~1,4 MB;
`posizione` 0,2 ms (30 ordini) / 24 ms (2000); giro dell'ombra 112 ms (2000 conto, 1000 specchio); primo
`regole_di_oggi()` 3,6 s (import pigri): va chiamato all'avvio, mai nel percorso del ladder.

## 5. Test e falsificazioni

- Test W1-C2 (prima della revisione): **164 verdi**; dopo la revisione **197 verdi** (par. 10) (`python -m pytest Betfair/nucleo/ordini/tests/ -q -p no:cacheprovider`).
- Falsificazione: **43 mutazioni, 43 rosse** (11 attribuzione, 10 libro, 10 P&L, 12 riconciliazione), una alla volta su
  una copia (`scratchpad/w1c2/mutazioni_c2.py`), ripristino con sha256 uguale. Al primo giro 6 sopravvissute (M05 precedenza
  degli indizi, M17 lucchetto, M30 prezzo medio non > 1, M31 esposizione positiva, M38 righe `ripresa`, M41 app scambiata
  per sito): test rafforzati (commit `f79855e5`). Al giro finale M17 (lucchetto tolto) e' sopravvissuta UNA volta su due
  giri (il test di concorrenza dipende dal caso): aggiunto `test_lettura_aspetta_lo_scrittore_deterministico` (lo scrittore
  si ferma dentro la composizione, il lettore deve aspettarlo); M17 poi rossa 3 volte su 3. Esito finale **43/43 rosse**
  (giro completo `scratchpad/w1c2/mutazioni_c2_finale.txt` + rilancio di M12-M31 sui file finali `mut_libro_pnl.txt`).
  sha256 dopo ogni ripristino = file committati:
  `attribuzione.py` 0d65e11c30bd5b1c410e54fd1de97df4b8c71f63d2fe987d6ad4b62238e8e55d,
  `libro_conto.py` 71ce44bafe30ef090881c4f35b6efc1acdae75ecb3e8cb5f0f25c813a577bd3b,
  `pnl_mercato.py` fd4d60773dd1bbd7f2c4d3e5b92371f587c9cc8b83d58a6c370ba5989f949683,
  `riconciliazione.py` 2a84db25a2d441dbd94278339a5ae24da3822f574e07fdd92feed3bd79173175.
- Suite intera a meta' (`python -m pytest Betfair/ -q -p no:cacheprovider`): **11.732 verdi, 2 rossi, 87 saltati, 6 xfailed**
  (628 s). I 2 rossi sono soglie di latenza su macchina condivisa (`test_auto_follow_2026_09_25.py::test_latenza_logica_aggancio_sotto_i_20_ms`
  20,05 ms contro 20; `test_motore_ordini_2026_09_24.py::test_latenza_logica_comando_place_sotto_20_ms`): rilanciati da soli
  = 2 verdi; non toccano file miei.
- Suite intera alla fine (cima `e2646912`): **11.735 verdi, 0 rossi, 87 saltati, 6 xfailed** (491 s).

Nota di metodo: lo `scratchpad` della sessione e' CONDIVISO fra i 7 agenti (un mio script e un'uscita della suite sono
stati sovrascritti da altri agenti con lo stesso nome di file: rifatti in `scratchpad/w1c2/`). Da dire agli altri.

## 6. Funzionalita' di `01_FUNZIONALITA.md`

Coperte (nuovo/ombra): F-007, F-008 (indizio-dato), F-016 e D-045 (R1 in ombra), C-055 e D-045 (R2 in ombra), C-050
(riuso), F-040 e F-059 (sulla posizione del libro), J-078 (dati del ladder, aggancio in ondata 2), G-012 in parte.
Restano al vecchio: C-052, C-054, D-046, D-054, F-009, ogni scrittura (specchio, alert, settled), R3..R9.

## 7. PSB par. 6/7

| Voce | Stato |
|---|---|
| 6.4 esito riletto da oggetti veri | sollecitata: `CurrentOrder` veri (REST e stream), `BetfairOrder` di flumine veri nel blotter |
| 6.4 parziali | sollecitata: parziale, parziale poi annullato (fase e `StatoOrdine`), P&L solo sull'abbinato |
| 6.4 esito ignoto, riconciliazione per ref | sollecitata: diario in volo (R2 vero), riga dello specchio senza bet_id |
| 6.4 LAPSE al fischio | sollecitata: `sizeLapsed`, fase `scaduto`, divergenza di stato contro lo specchio |
| 6.4 esposizione sull'abbinato, non sul chiesto | sollecitata: `pnl_mercato` (M28 rossa) |
| 6.4 settlement con commissione | ⊘: fuori comparto (F-009 resta al regolato); dichiarato «lordo» |
| 6.4 bet delay, place-and-trim, FOK | ⊘: il libro LEGGE ordini, non li piazza (porta: W1-C1) |
| 6.5 campi che la UI mostra (chiesto, abbinato, residuo, prezzo medio, stato, aggiornamento) | sollecitata: `OrdineConto` |
| 6.6 concorrenza | sollecitata: 4 scrittori + 2 lettori con switch interval 1 us, piu' prova deterministica del lucchetto (M17 rossa) |
| 6.7 scenari e falsificazione | sollecitata: 7 scenari obbligatori + 63 mutazioni (par. 10) |
| 6.8 referto riproducibile | comandi par. 5 |
| 6.1/6.2/6.3/6.9 | ⊘: nessun replay in questa ondata (brief comune par. 2) |
| 7 n.1 grafia delle chiavi | sollecitata: chiavi camelCase di Betfair, snake_case non letto (`::test_conversione_rifiuta_i_campi_mancanti`) |
| 7 n.3 campo inesistente / prezzo inventato | sollecitata: abbinato senza prezzo medio fuori dal P&L e dichiarato; `ValueError` su campi essenziali |
| 7 n.4 e n.6 ref di riconciliazione / ref senza mercato | sollecitata: R2 per `customerOrderRef` VERO (diario `ordine`), divergenze per `bet_id` |
| 7 n.7 bet_id solo se abbinato | sollecitata: ordini non abbinati nel libro e nello `StatoOrdine` (`accettato`) |
| 7 n.21 paper e live sommati, zero al posto di assente | sollecitata: chiave `(modo, bet_id)`, `ValueError` se mescolati (M13, M14, M23 rosse); prezzo medio assente = `None` |
| 7 n.27 finti con chiavi diverse dal vero | sollecitata: JSON di Betfair + classi vere; supabase vero su MockTransport |
| 7 n.29 test a vuoto | sollecitata: `ATTESI_R1`, caso fisso del blotter, copertura di tutti gli autori |
| 7 n.35 test mai visto rosso | sollecitata: 63/63 dopo la revisione; i test nuovi visti rossi sul codice di `5b958ba7` |
| 7 n.36 consapevolezza (cio' che il bot crede vs il mercato) | sollecitata in parte: l'ombra confronta specchio/blotter/diario col conto; il confronto con R4/R5/R6 dei bot e' ondata 2 |
| 7 n.2, 5, 8-20, 22-26, 28, 30-34, 37 | ⊘: riguardano piazzamento, banco, strategie, DB dei bot o UI, fuori da questo comparto |

## 8. Aggancio proposto (ondata 2) — nessun file toccato oggi

1. **Libro nel runner** (calcio e tennis): `Betfair/stream/engine/live_trading_strategy.py:176` (dove oggi si installa
   `esiti_ordini_canale.osserva_conto_su_flumine(flumine, _LC.publish)`) e `:214` (gemello paper). Ponte immediato, prima
   che W1-A2 sia agganciato: la `pubblica` del topic `conto` porta gia' la grafia di `listCurrentOrders` ->
   `libro_conto.ordine_da_riga_conto` -> `LibroConto.ricevi_live`; il topic `conto_paper` -> `ricevi_prova`. Poi
   `LibroConto.collega_live(FlussoOrdiniConto di A2)`. `regole_di_oggi()` chiamato all'avvio (3,6 s).
2. **Topic per la UI** sul canale locale ESISTENTE (47331 calcio, 47332 tennis; `local_channel.publish` `:802`), nuovo
   topic `libro_conto` (il topic `conto` resta identico: lo leggono Mike e i bot), dietro `ARCH_LIBRO_CONTO=1`, push per
   mercato a ogni ordine cambiato (consumatore del libro), coalescenza minima 20 ms come il ladder (A2). Schema:
   `{"market_id", "modo": "live"|"paper", "ricevuto_ms", "ordini": [{"bet_id", "selection_id", "handicap", "lato",
   "prezzo", "importo", "abbinato", "residuo", "prezzo_medio", "stato", "autore", "motivo", "ref", "aggiornato_ms",
   "comandi": [...]}], "posizione": {"se_vince": {sel: eur}, "se_vince_per_autore": {autore: {sel: eur}},
   "abbinato_back", "abbinato_lay", "prezzo_medio_back", "prezzo_medio_lay", "esposizione_massima"},
   "selezioni": {sel: {"se_vince", "se_perde"}}}`. UN messaggio per modo: paper e live mai nello stesso messaggio.
   Frontend: `frontend/src/components/live/LadderView.tsx:248-303` (`buildLadder`: oggi `position.matched_if_win/lose`
   dallo specchio) e la tabella ordini del ladder (J-078): colonna «autore», P&L per selezione da `selezioni`, P&L di
   mercato da `posizione.se_vince`. Contratto TS generato dallo schema (nessuna costante duplicata, PSB 7 n.33).
3. **Comandi**: `comandi_ammessi` (`libro_conto.py:378`): annulla/sposta SOLO sugli ordini dell'utente (`desktop`,
   `sito`); sugli ordini dei bot, `risk` e `sconosciuto` SPENTI. Decisione dell'utente (U-nuova): permettere l'annullo
   di un ordine di un bot dal ladder? (oggi W3a/W3b fermano il bot quando l'utente interviene sui suoi mercati).
4. **Ombra**: `ARCH_RICONCILIA=ombra` (di serie `vecchio`): nel `reconcile_worker` (`:1300-1320`, dopo la lettura dello
   specchio) e all'avvio accanto a `riprendi_da_diario` (`motore_ordini.py:2506`), `RiconciliatoreOmbra.giro(...)` con
   gli STESSI dati gia' letti (nessuna lettura in piu'), referto nel diario della Salute. Criterio «uguale o meglio»:
   per N giornate (N dall'utente) le divergenze dell'ombra che corrispondono alle azioni di R1/R2 coincidono una per una
   (stesso bet_id, stesso tipo) e quelle in piu' dell'ombra (blotter, attribuzione, specchio senza bet_id) sono
   spiegate; poi il confronto con R4/R5/R6 per `ref` e `StatoOrdine`.

## 9. Divergenze per l'utente, rischi, dubbi

- **D1** il desktop dal MOTORE scrive `customerStrategyRef="desktop"` (`motore_ordini.valida_comando` `:419-424`: ref =
  attore). W2 (`motivo_bot_da_riferimenti`) lo dice «di un bot» (`strategia:desktop`): la copertura «fuori bot» del
  greenup non lo conterebbe; R1 storico «ours». Qui: `desktop`. Oggi l'app manda gli ordini come `order` (ref `live`),
  quindi il caso nasce solo da un `comando` con attore `desktop`.
- **D2** stesso esito «bot», NOME piu' preciso: `safe`+`safe_tennis-t<id>` -> `safe_tennis`; `omega`+`safe-t<id>`/
  `safe_tennis-t<id>`/`mike-t<id>` (ordini REST di Safe e Mike prima del 24/09) -> `safe`/`safe_tennis`/`mike`, con la
  stessa regola con cui Safe legge i suoi (`bot_service._SAFE_REFS_STORICI`, `_SAFE_PREFISSI_ORDINE`); `bot_di` dice
  `omega`/`safe`.
- **D3** terminale vecchio `order_exec.py` (`customerStrategyRef="watchlist"`): oggi «altri_bot»; qui `sconosciuto`
  (nessun autore nel contratto). E' un ordine dell'utente da un terminale dismesso? Decisione dell'utente.
- **D4** (non generato: nessun percorso nostro lo produce) ordine senza `customerStrategyRef` ma con un
  `customerOrderRef` non nostro: W2 = utente, R1 = `ambiguous`; qui `sconosciuto` (comandi spenti).
- **D5** il terminale manuale TENNIS (`tennis`): la regola calcio di W2 lo dice «di un bot», il tennis W3b
  (`ordini_esterni.classifica`, `rif_manuali`) e R1 «utente». Divergenza GIA' presente fra due funzioni di oggi; qui
  `desktop`.
- **D6** `esposizione_fuori_bot.proprietari_bot` legge `mike_trades` SENZA `role`: un ordine dell'utente «adottato» da
  Mike (`role='utente'`) per W2 e' di Mike, per `reconcile_worker._proprietari` resta dell'utente. Qui come R1
  (`indizio_da_riga_bot`). Divergenza fra due funzioni di oggi.
- **D7** il `risk engine` non ha un ref suo verso Betfair (passa dalla coda: `live` + `risk<id>`): solo l'indizio della
  riga di coda lo distingue dal desktop; senza, un ordine del risk e' `desktop` (come oggi `manuale_app`).
- **D8** Safe tennis via la coda tennis (`tennis`) con la riga nella tabella di Safe: qui `safe_tennis` (lo sport
  dal ref del terminale tennis); `reconcile_worker._fonte_di` usa `eventTypeId`, che `OrdineDalConto` non porta.
  Proposta: aggiungere `event_type_id` a `OrdineDalConto` (A) se il coordinatore lo vuole.
- **RISCHIO (per W1-A2 e il coordinatore)**: `betfairlightweight` 2.23.2 `UnmatchedOrder.__init__` ha `rfo` e `rfs`
  OBBLIGATORI (`streaming/cache.py:419-436`): un messaggio `ocm` senza quelle chiavi solleva `TypeError` nella cache
  (provato: `OrderBookCache.update_cache` con un `uo` senza `rfo`/`rfs`). Se Betfair omette `rfo`/`rfs` per gli ordini
  del SITO, lo stream degli ordini del conto cadrebbe proprio sugli ordini che vogliamo vedere. Da verificare su un
  messaggio `ocm` reale con un ordine del sito prima dell'ondata 2.
- Mercati a linee (handicap): `se_vince` vuoto, esposizione prudente; la UI deve dirlo, non mostrare zero.
- `regole_di_oggi()` importa ~3,6 s di codice di oggi: mai nel percorso caldo.
- Nessun ordine reale del conto nelle registrazioni: la prova sul campo e' l'ombra di T11.

## 10. Correzioni dopo la revisione (09/10, revisione indipendente di `5b958ba7`: «DA CORREGGERE»)

Tutto sul ramo `architettura/w1-c2`, nessun file esistente toccato, contratti invariati. I test proposti dal revisore
(`scratchpad/rev/test_rev_{pnl,libro,tol}.py`) sono incorporati con nomi miei; ogni test nuovo e' stato eseguito sul codice
di `5b958ba7` ed e' ROSSO (uscita in `scratchpad/w1c2/rossi_su_vecchio.txt`), verde sul codice corretto.

| Reperto | Correzione (file:riga) | Test (rosso prima, verde dopo) |
|---|---|---|
| **G1** ordini dei bot e del risk dalla CODA del runner (`live` + ref di flumine) visti come `desktop` e annullabili | `attribuzione.py:282`: il ref manuale (`live`, `tennis`) senza evidenza da' `sconosciuto` PROVVISORIO (`Attribuzione.provvisoria`), quindi `comandi_ammessi` = `()`; `desktop` solo con evidenza POSITIVA: indizio `utente` dalla riga di coda non di un bot (`indizi_da_riga_coda`) o dagli ack del desktop (`indizio_ack_desktop` `:351`); un indizio di un bot vince sempre sull'evidenza dell'utente | `test_c2_attribuzione.py::test_rev_g1_ordine_di_bot_dalla_coda_non_e_desktop_ne_annullabile`, `::test_indizi_coda_risk_attore_source`, tabella generata (D9) |
| **G2** esposizione massima con l'esito fittizio «vince un runner senza ordini» (tennis back 10@2,2 su A e B -> -20 invece di 0) | `pnl_mercato.py:194` `calcola`: con l'elenco dei runner l'esposizione e' esatta; senza, `CalcoloPosizione.esposizione_massima` = `None` (`NaN` nel float del contratto) e motivo `runner_ignoti`; il libro prende runner, tipo e vincitori dal book (`LibroConto.imposta_mercato` `:492`) | `test_c2_pnl_mercato.py::test_rev_g2_tennis_back_su_entrambi_esposizione_zero_non_meno_venti`, `::test_rev_g2_dutch_su_tutti_i_runner`, `::test_esposizione_massima_con_e_senza_elenco_dei_runner` |
| **G3** dopo una sottoscrizione nuova lo stream non porta gli EXECUTION_COMPLETE (doc Betfair, `AUDIT_2026-10-02/_fonti_betfair/bf_2687396.txt:941`): «se vince» sottostimato in silenzio | `libro_conto.py:191` `SorgenteOrdiniCorrenti` (protocollo; la REST vera e' di A1) + `semina` `:276` (all'avvio da `collega_live(..., correnti=)` e in `riconnesso(con_ripresa=False)` `:308`), con `ordine_da_corrente`; `seme_fatto()`; senza seme la posizione dichiara `seme_non_fatto`; `verifica_abbinato` `:508` confronta `mb`/`ml` dell'`OrderRunnerChange` con l'abbinato noto e dichiara `abbinato_mancante` (WARNING); l'ombra con `conto_completo=False` (`riconciliazione.py:210`) NON emette `specchio_senza_conto` (i giri non avanzano) e un R2 «non trovato» diventa `in_volo_da_verificare` | `test_c2_revisione.py::test_g3_*` (5 test) |
| **M1** un seme REST piu' vecchio consegnato dopo faceva regredire l'ordine | `libro_conto.py:357` `_regressione`: abbinato che cala (salvo `sizeVoided`) o completo che torna eseguibile = rifiutato, WARNING, contatore `regressioni` | `test_c2_revisione.py::test_m1_*` (3 test) |
| **M2** il tetto dimenticava ordini terminali di mercati APERTI cambiando il P&L in silenzio | `libro_conto.py:413` `_rispetta_tetto`: prima i mercati chiusi (`imposta_mercato(..., chiuso=True)`); per gli aperti l'abbinato resta nel P&L come riassunto per (selezione, handicap, lato, autore) (`_riassumi` `:442`), WARNING, motivo `ordini_riassunti` | `test_c2_revisione.py::test_m2_*` (2 test) |
| **M3** `_indizi` senza limite e mai liberato | niente duplicati; indizi di bet_id mai arrivati potati oltre `max_indizi` (`_pota_indizi` `:351`); tolti con l'ordine (`_togli`) e con `dimentica_mercato` | `test_c2_revisione.py::test_m3_indizi_senza_duplicati_ne_crescita` |
| **M4** asiatico con la sola linea 0,0 trattato come vincitore unico | `pnl_mercato.py:72` `TIPI_UN_VINCITORE = {"ODDS"}`, `_non_supportato` `:179`: tipo assente o non `ODDS`, piu' vincitori o handicap -> non supportato (se vince VUOTO, stima prudente, motivi); `CalcoloPosizione.solo_abbinato` dichiara che i non abbinati non entrano nell'esposizione (da mostrare nella UI) | `test_c2_pnl_mercato.py::test_rev_m4_asiatico_con_sola_linea_zero_non_supportato` |
| **M5** runner standalone (`run_scalper.py:85`, `run_scalper_live.py:271`, `run_theta.py:127`) senza `name` -> nome della classe -> `sconosciuto` | `attribuzione.py:177` `_classi_scalper`: le 4 classi dello scalper calcio importate nelle regole; la tabella generata include ogni `run_*.py` che crea una strategia senza `name` (AST) | `test_c2_attribuzione.py::test_rev_m5_runner_standalone_senza_name` + 5 righe nuove della tabella |
| **Basso** notifiche ai consumatori fuori ordine | `libro_conto.py:546` `_avvisa`: consegna SERIALIZZATA (lucchetto di consegna) dello stato PIU' RECENTE dell'ordine | `test_c2_revisione.py::test_consegna_ai_consumatori_mai_una_versione_vecchia_dopo_una_nuova` (deterministico) |
| **Basso** `TOLLERANZA_ABBINATO` 0,01 -> 0,5 sopravviveva | test oltre il centesimo (2,98 contro 3,00 = divergenza; 2,995 no) | `test_c2_revisione.py::test_tolleranza_abbinato_oltre_un_centesimo_e_divergenza` (M61 rossa) |

Verifica fatta io: rilanciato il rischio del revisore sul formato reale dello stream: `rfo=""`/`rfs=""` (ordine del
sito) -> `sito` (`test_rev_sito_vero_dallo_stream_con_rfo_rfs_vuoti`); `uo` SENZA `rfo`/`rfs` (esempio della
documentazione Betfair, `bf_2687396.txt:1108`) -> `TypeError` nella cache di betfairlightweight 2.23.2
(`test_rev_rischio_ocm_senza_rfo_rfs_nella_libreria`: il rischio per W1-A2 resta, ora provato da un test).

Falsificazione dopo la revisione: **63 mutazioni, 63 rosse** (le 43 di prima, con le stringhe aggiornate dove il codice e'
cambiato, piu' 20 nuove M44-M63 sulle correzioni); giro completo `scratchpad/w1c2/mutazioni_c2_rev.txt` (62/63: M41 era
sopravvissuta perche' l'unico ordine `desktop` del test era diventato provvisorio; aggiunto un ordine confermato da
indizio, poi rilancio di M32-M43 e M61-M63 in `mutazioni_c2_rev_ric.txt`: 15/15). sha256 dopo ogni ripristino = file
committati: `attribuzione.py` 92e306c569961b70198029d299ec8ee5e42e62c18a745198d873c536183e898e,
`libro_conto.py` c49e540b8005929068d555728ab2274645827c58f48b4daec3834817caf3c54d,
`pnl_mercato.py` 6c609783f489b35e231d5a1dc931724d8ad794a51b7e06bcd62bbc0b1524c7fe,
`riconciliazione.py` c65da0decef50ef8606f8649a92275e824b068d37a3c6269bef0a09b2a594bbd.

Test W1-C2 dopo la revisione: **197 verdi**. Suite intera (una volta, alla fine, cima `99e75fbe`): **11.768 verdi, 0 rossi, 87 saltati, 6 xfailed** (391 s).

**Verifica del coordinatore su `83f376e0` (09/10): una mutazione sua SOPRAVVISSUTA.** In `libro_conto.py` `_regressione`
il ramo `if float(nuovo.abbinato) < float(vecchio.abbinato) - annullati - 1e-9:` sostituito con `if False:` lasciava i
197 test verdi: l'unico test di M1 passava gia' dal primo ramo (completo -> eseguibile). Il mio «63/63» non provava
ogni ramo delle correzioni. Corretto cosi':
- test nuovi (in `test_c2_revisione.py`): abbinato che cala fra due EXECUTABLE (6 poi 4, residuo coerente) e fra due
  EXECUTION_COMPLETE senza `sizeVoided` (10 poi 8); in piu' il completo che torna eseguibile A PARITA' di abbinato
  (cosi' ognuno dei due rami ha un test che passa solo da lui); poi un test per ogni ramo delle correzioni G1-G3/M1-M5
  che nessuna mutazione toccava (riga `bot:tennis` dello specchio, riga «utente» di Mike come conferma, ack del
  desktop, riga di coda del risk, seme con un ordine illeggibile, riconnessione senza ripresa senza sorgente, mancanza
  sul lato lay e su un'altra selezione, annullato senza abbinato dimenticato dal tetto, `dimentica_mercato` che toglie
  riassunti/mancanze/info, `imposta_mercato` con vincitori e tipo, tipo `LINE`): **14 test nuovi, 211 verdi**;
- la mutazione del coordinatore (M64) e' ROSSA (`1 failed`) e col ripristino tutto torna verde, sha256 di
  `libro_conto.py` uguale (`c49e540b8005...`);
- script delle mutazioni NEL REPO: `ARCHITETTURA_2026-10/ondata1/W1-C2/mutazioni.py`, eseguibile dalla radice con
  `python ARCHITETTURA_2026-10/ondata1/W1-C2/mutazioni.py .` (anche `... . M64 M65` per alcune); ogni mutazione lancia
  TUTTI i test W1-C2 con `-x`, ripristina i byte, ricontrolla lo sha256, codice d'uscita 1 se qualcosa sopravvive o non
  si trova. 93 mutazioni: M01-M43 della consegna, M44-M63 della revisione, **M64-M93 nuove, una per ramo** (M1 x2,
  G1 x6, G3 x7, M2 x7, M3 x1, `imposta_mercato` x4, G2 x2, M4 x1);
- giro completo nel repo: **TOTALE rosse 93/93 (guasti 0)**, uscita committata in
  `ARCHITETTURA_2026-10/ondata1/W1-C2/mutazioni_esito.txt`; sha256 dopo ogni ripristino = file committati (quelli
  sopra: i moduli non sono cambiati, solo test, script e referto). Suite intera non rilanciata (nessun modulo toccato).

**Divergenza nuova per l'utente — D9**: un ordine col ref del terminale manuale (`live`/`tennis`) e il
customerOrderRef di flumine, senza riga di coda ne' ack, oggi e' «dell'utente» per W2 e per R1; qui e' `sconosciuto`
PROVVISORIO (nessun comando sul ladder) perche' gli ordini dei bot e del risk dalla coda sono indistinguibili dai
riferimenti. Scelta prudente (mai annullare un ordine di un bot credendolo dell'utente); da confermare con l'utente.

**Aggancio aggiornato (ondata 2)**, in aggiunta al par. 8:
- G1: il runner tiene in memoria gli ack dei comandi del desktop (`order`/comando `desktop`: `motore_ordini` diario
  `inviato`+`ordine`) e li passa al libro come `indizio_ack_desktop`; per gli ordini col ref manuale ancora
  provvisori si RILEGGE la riga di `betfair_live_order_requests` con quel `bet_id` (stessa lettura di
  `esposizione_fuori_bot.proprietari_bot`, una per bet_id nuovo, fuori dal percorso degli ordini) finche' la riga
  non ha il `bet_id`, poi `indizi_da_riga_coda`. Finche' resta provvisorio: nessun comando, autore mostrato «da
  confermare».
- G3: `LibroConto.collega_live(flusso, correnti=<ClienteRest di A1 che fa listCurrentOrders paginato>)`;
  `riconnesso(con_ripresa=...)` dal `FlussoOrdiniConto` di A2 (proposta di estensione: un evento di riconnessione con
  l'indicazione della ripresa, e `mb`/`ml` per runner -> `verifica_abbinato`); `RiconciliatoreOmbra.giro(...,
  conto_completo=libro.seme_fatto())`.
- G2/M4: `imposta_mercato(market_id, runner=..., tipo_scommessa=marketDefinition.bettingType,
  vincitori=marketDefinition.numberOfWinners, chiuso=status=="CLOSED")` dal book di A2 a ogni marketDefinition.
- Schema UI del topic `libro_conto` (par. 8) con in piu': per ordine `"provvisoria"`; per la posizione `"supportato"`,
  `"motivi"`, `"esposizione_massima": null` quando non calcolabile, `"solo_abbinato": true` (la UI scrive che gli
  ordini non abbinati non sono nell'esposizione).

Estensioni del contratto proposte (in piu' del par. 2): `PosizioneMercato.esposizione_massima: Optional[float]` (oggi
float: uso `NaN`); `FlussoOrdiniConto` con riconnessione/ripresa e `mb`/`ml`; `OrdineDalConto.event_type_id` (D8).

## 11. Seconda revisione (09/10, revisione di `0e05d04d`: «DA CORREGGERE», correzioni piccole)

Promossi dal revisore: G2, G3, M1, M3, M4, M5 e il P&L (6 casi a mano; 0 differenze con `pnlSeVince`/`lockedPnlAt`,
`flumine.calculate_matched_exposure` su 3000 casi e `greenup.compute_greenup` su 2000); 93/93 mutazioni rosse. Le
correzioni sono nel commit `a89c8c25` (codice e test) e nel commit di questo referto. Contratti invariati, nessun
file esistente toccato.

| Punto | Correzione (file:riga) | Test (in `test_c2_revisione2.py` salvo dove detto) |
|---|---|---|
| **1a** G1: il place dal ladder (`local<id>`) ha la colonna `bet_id` NULL (`live_order_worker.py:3649-3653` `_LOCAL_ROW_KEYS`, `:3777-3786` `_record_local_request`); il bet_id nuovo e' solo in `result` | `attribuzione.py` `bet_id_della_riga` (`:361`): prima `result.bet_id` (la chiave che `live_order_worker._result` `:880` scrive), poi la colonna; `result` anche come stringa JSON (`_risultato` `:347`). `indizi_da_riga_coda(riga, bet_id=...)` (`:371`) prova solo per QUEL bet_id | `test_g1a_place_dal_ladder_riconosciuto_dal_result_della_riga_vera` (la riga e' il corpo VERO dell'INSERT di `_record_local_request` sul client supabase vero; il `result` e' `_result` vero con un ordine flumine vero), `test_g1a_riga_della_coda_db_col_bet_id_in_colonna`, `test_g1_result_come_stringa_json_e_rotto` |
| **1b** G1: coda tennis `tennis_live_order_queue` (`tennis_live_order_worker.py:1830`, `local<sid>`, colonne `client_ref`, `payload`, `result`; comandi del motore `cmd<id>` con `payload.comando`, `esecutore_tennis.py:266`) | `indizi_da_riga_tennis` (`:405`): stessa regola su `payload.action`, `payload.comando`/`source`, `result.bet_id` | `test_g1b_coda_tennis_place_del_ladder_e_comando_di_un_bot` (`_result` VERO del worker tennis) |
| **1c** G1: un CANCEL o REPLACE dell'utente su un ordine di un bot NON prova che l'ordine sia suo | `AZIONI_CHE_PIAZZANO` (`:339`): `place`, `place_submin`, `greenup`, `dutch`, `cashout_all`, `cashout_event`; ogni altra azione (e le righe senza azione) non prova niente, ne' per l'utente ne' per un bot ne' per il risk | `test_g1c_cancel_o_replace_dell_utente_su_un_ordine_di_un_bot_non_e_prova[cancel/replace]` (righe vere), `test_g1c_greenup_dell_utente_e_un_suo_ordine` |
| **1d** G1: i ritentativi `ft<rid>...` (`live_order_worker.py:1867-1877`, `params.ft_parent`) | `indizi_da_riga_coda(..., genitore=riga)`: eredita gli indizi della riga genitore (stesso `id`); senza genitore (o con un altro id) nessuna prova | `test_g1d_ritentativo_ft_eredita_l_autore_del_genitore` |
| **2** M2: dopo il tetto un riseme o un aggiornamento tardivo faceva rientrare l'ordine riassunto: P&L raddoppiato (`probe_m2.py`: 120 invece di 60) e autore di nuovo provvisorio | `libro_conto.py` `_Riassunto` (`:220`) ricorda per (modo, mercato) ogni bet_id riassunto con stato, attore, indizi e la sua parte; `_rientro_da_riassunto` (`:423`): stesse guardie (vecchio/regressione) contro l'ultimo stato, poi la parte si STORNA, tornano indizi e attore, contatore `riassunti_rientrati`; `dimentica_mercato` li toglie | `test_m2_seme_dopo_il_tetto_non_raddoppia` (60, anche due risemi), `test_m2_aggiornamento_tardivo_di_un_riassunto_storna_e_conserva_l_autore`, `test_m2_rientro_vecchio_o_in_regressione_rifiutato`, `test_m2_paper_riassunto_rientra_con_l_attore_dichiarato`, `test_m2_dopo_dimentica_mercato_il_riassunto_non_ferma_un_ordine_nuovo` |
| **3** mutanti R14 (riassunto a prezzo 2,0) e R18 (`ASIAN_HANDICAP_SINGLE_LINE` a vincitore unico) | solo test | `test_m2_riassunto_con_prezzo_diverso_da_due` (3 x 10 @ 3,0 = 60), `test_m4_tipi_non_a_vincitore_unico[SINGLE_LINE/DOUBLE_LINE/LINE/RANGE]` |
| **4** `vincitori_ignoti` | `pnl_mercato.py:208`: tipo `ODDS` senza `numberOfWinners` -> non supportato (se vince vuoto, stima prudente), salvo i `marketType` a vincitore unico PER DEFINIZIONE (`TIPI_MERCATO_UN_VINCITORE` `:81`: `MATCH_ODDS`, `CORRECT_SCORE`, `HALF_TIME`, `HALF_TIME_SCORE`, `BOTH_TEAMS_TO_SCORE`, e i prefissi `OVER_UNDER_`, `FIRST_HALF_GOALS_`; `vincitore_unico_per_definizione` `:86`); `LibroConto.imposta_mercato(tipo_mercato=...)` | `test_vincitori_ignoti_e_tipi_a_vincitore_unico_per_definizione` |
| **5** NaN nel contratto | `posizione_per_json` (`pnl_mercato.py:296`): `NaN` -> `None`, chiavi in testo; il serializzatore dell'ondata 2 DEVE usarla (o scrivere `null`): `json.dumps(..., allow_nan=False)` passa | `test_posizione_per_json_nan_diventa_null` |

I 21 test nuovi (`test_c2_revisione2.py`) sono stati eseguiti sul codice di `0e05d04d`: **14 rossi** (tutti quelli
delle correzioni); i 7 verdi uccidono mutanti su comportamenti gia' giusti (R14, R18 x4, R04) o proteggono un ramo
nuovo (`dimentica_mercato` coi bet_id riassunti). Uscita:
`scratchpad/w1c2/rossi_rev2_su_vecchio.txt`. Test W1-C2: **232 verdi**.

Mutazioni: lo script del repo ha ora **136** mutazioni: le 93 di prima, le **21 del revisore** (R01-R21, R13/R14
adeguate al riassunto riscritto) e **22 nuove** (M94-M115, una per ramo delle correzioni). Giro completo
(`python ARCHITETTURA_2026-10/ondata1/W1-C2/mutazioni.py .`): **TOTALE rosse 136/136 (guasti 0)**. Al primo giro 2 sopravvissute: R04 (una
tabella che non e' di un bot non deve bloccare la conferma dell'utente: mancava il test,
`test_g1_indizio_che_non_dice_nulla_non_blocca_la_conferma_dell_utente`) e M104 (il rientro di un messaggio piu'
vecchio passava inosservato perche' il test usava gli stessi numeri: ora con un prezzo medio diverso e il contatore
`fuori_ordine`); poi giro completo ripetuto: 136/136, uscita in
`ARCHITETTURA_2026-10/ondata1/W1-C2/mutazioni_esito.txt`. sha256 dopo ogni ripristino = file committati in
`a89c8c25`: `attribuzione.py` 0acd6ee24a718da0c978150d88d45dea5e2c8092cae03bea70202dc9b1ab11da,
`libro_conto.py` 34a337aabed021ddc1c9802aabe3551b24055fb0074ff201dcc9d07eef3cffbd,
`pnl_mercato.py` c765f43856999e08b2dbed1626af95f6009d4ce294091185cd944ade6f6d76d7,
`riconciliazione.py` c65da0decef50ef8606f8649a92275e824b068d37a3c6269bef0a09b2a594bbd.
Suite intera (una volta, alla fine): **11.803 verdi, 0 rossi, 87 saltati, 6 xfailed** (367 s).

**Aggancio aggiornato (ondata 2), riconferma degli ordini aperti dell'utente all'AVVIO** (un ordine PERSIST
dell'utente deve tornare `desktop`, quindi cancellabile dal ladder, dopo il riavvio del runner o dell'app). Per ogni
ordine live ancora PROVVISORIO (ref `live`/`tennis`), fuori dal percorso degli ordini, una lettura per bet_id nuovo
(come `esposizione_fuori_bot.proprietari_bot`), a blocchi di 100:
- calcio: `betfair_live_order_requests` colonne `id, client_ref, action, params, bet_id, result`, `mode=live`,
  filtro `bet_id=in.(...)` OPPURE `result->>bet_id=in.(...)` (le righe `local<id>` hanno il bet_id solo nel
  `result`); per le righe `ft...` la riga genitore per `id=params->>ft_parent`; poi `indizi_da_riga_coda(riga,
  bet_id=..., genitore=...)`;
- tennis: `tennis_live_order_queue` colonne `client_ref, payload, result`, filtro `result->>bet_id=in.(...)`; poi
  `indizi_da_riga_tennis(riga, bet_id=...)`;
- le tabelle dei bot (`omega_trades`, `safe_strategy_trades`, `mike_trades` con `role`) e lo specchio come oggi
  (`proprietari_bot`, `indizio_da_riga_bot`);
- il diario del motore (righe `inviato` con attore `desktop` e `ordine` col customerOrderRef vero) come
  `indizio_ack_desktop`.
Finche' nessuna lettura risponde l'ordine resta provvisorio (nessun comando); una lettura fallita si ritenta
(`RIPROVA_PROPRIETARI_S` come W3a). Il serializzatore del topic `libro_conto` usa `posizione_per_json` (mai `NaN`
nel JSON).

**Divergenze aggiornate (da provare nell'ombra, per l'utente):**
- ~~D10 replaceOrders~~: **tolta**, non era una decisione dell'utente ma una regressione di parita'; corretta nel par. 12.
- **D11 elenco dei `marketType` a vincitore unico per definizione** (punto 4): scelto prudente e chiuso; un
  mercato fuori elenco senza `numberOfWinners` resta `vincitori_ignoti` (se vince vuoto). Da confermare.
- D9 resta (ref manuale senza prove = provvisorio).

## 12. Terza verifica (09/10, verifica del coordinatore su `3ceac891`): replaceOrders, il nuovo eredita

La D10 non era una decisione dell'utente ma una regressione da evitare: oggi un ordine dell'utente spostato dal ladder
resta suo e comandabile. Corretto nel commit `d1430036` (codice, test, mutazioni) e nel commit di questo referto.
Contratti invariati, nessun file esistente toccato.

**Regola** (`attribuzione.py:467` `eredita`): l'ordine NUOVO nato da un replace prende autore, conflitto e
PROVVISORIETA' dell'ordine SOSTITUITO, qualunque fosse (utente, bot, sito, sconosciuto): un sostituito provvisorio da' un
nuovo provvisorio, niente si inventa. Restano solo le prove PROPRIE del nuovo che dicono un bot (una riga di tabella
o di coda col SUO bet_id; se dicono un autore diverso dal sostituito il conflitto si scrive) e l'attore dichiarato
della sorgente in prova. I riferimenti del nuovo cedono al sostituito: li porta Betfair dall'ordine sostituito.

**Le fonti del legame vecchio -> nuovo (grafia verificata nel codice):**

| Fonte | Cosa c'e' davvero | Uso |
|---|---|---|
| (a) `betfair_live_order_requests`, `action=replace` | `live_order_worker._do_replace` (`:1639-1678`): la colonna `bet_id` e `params` portano il bet_id VECCHIO (comando); il `result` e' `_result(...order=order)` (`:1674-1677`) preso sull'ordine SOSTITUITO, quindi `result.bet_id` = VECCHIO. **Il bet_id nuovo non e' in nessuna colonna della riga** (provato: `test_fonti_calcio_il_replace_porta_il_vecchio_lo_specchio_lega_il_nuovo`, riga = corpo vero dell'INSERT di `_record_local_request`) | il legame si prende per ORIGINE: flumine crea il rimpiazzo con `Trade.create_order_replacement` (`flumine/order/trade.py:111`, `context=order.context` `:131`; `execution/betfairexecution.py:194`), quindi il `context["customer_order_ref"]` = `awlq<origine>` messo da `live_order_build._create_order` (`:940-941`) passa al nuovo e lo specchio `betfair_live_orders` (`LiveTradingStrategy._order_row` `:376`, `_client_order_ref` `:121`, `_request_id_from_ref` `:114`) lo scrive con `client_order_ref=awlq<origine>`, `request_id=origine`, anche dopo piu' replace. `attribuzione.origine_della_riga_specchio` (`:430`) e `indizi_da_origine(riga_specchio, riga_coda)` (`:449`): la richiesta d'origine (`id`=origine per la coda DB, `client_ref=local<origine>` per il canale locale) da' gli indizi del NUOVO bet_id con la regola di sempre (`indizi_da_riga_coda`) |
| (b) `tennis_live_order_queue`, `payload.action=replace` | `tennis_live_order_worker._do_replace` (`:798-816`): `payload.bet_id` = VECCHIO; il worker traccia il TRADE sotto il ref del comando (`_track_manual` `:812`), quindi la riga `tennis_live_orders` del rimpiazzo (`riga_specchio` `:508`) ha `client_order_ref` = `result.customer_order_ref` della riga di coda (`awtq<sid>`) e `bet_id` = NUOVO | `attribuzione.legame_da_replace_tennis(riga_coda, riga_specchio)` (`:486`) -> (vecchio, nuovo) -> `LibroConto.lega_sostituzione` |
| (c) tabelle dei bot | quando il replace lo fa il bot stesso, il bot scrive il bet_id NUOVO (Omega place-and-trim: `omega_market.py:1276` `nuovo_bet = esito_rep.get("bet_id")` -> `PlaceResult.bet_id`) | prova PROPRIA del nuovo (`indizio_da_riga_bot`), coerente col sostituito; se discorde, conflitto scritto |
| (d) stream ordini | flumine (`flumine/order/process.py:63-70`, "replaceOrder handling") trova il rimpiazzo col customerOrderRef del SOSTITUITO e poi lo cerca per bet_id: Betfair porta sul rimpiazzo lo STESSO `rfo` | `LibroConto._lega_dallo_stream` (`libro_conto.py:450`): stesso mercato, selezione, lato e `customerOrderRef` non vuoto, il bet_id MINORE completo (`EXECUTION_COMPLETE`) e' il sostituito del MAGGIORE, in qualunque ordine arrivino i messaggi (anche il completo tardivo), solo dopo le guardie (un messaggio rifiutato non lega). **Prova in piu', da provare nell'ombra**: contatore `legami_dallo_stream` accanto a `legami` (fonti a-c); criterio: per N giornate ogni legame dallo stream coincide con uno delle fonti a-c (stesso vecchio, stesso nuovo), altrimenti si spegne |

**Libro** (`libro_conto.py`): `lega_sostituzione(vecchio, nuovo, modo)` (`:380`, idempotente, `modo` controllato, mai
un ordine con se stesso); `_componi` (`:567`) applica `eredita` quando c'e' il legame; l'attribuzione del sostituito
(`_attribuzione_del_sostituito` `:415`) e' quella nota (anche di un ordine RIASSUNTO dal tetto: `_Riassunto.attribuzione`
`:231`, `_attribuzione_nota` `:404`), altrimenti (riavvio: il sostituito annullato puo' non tornare dal conto) i suoi
indizi riletti dalle righe, altrimenti risalendo la catena; cicli fermati. Il legame vale prima o dopo l'arrivo del
nuovo e del sostituito; nuove prove sul sostituito (o sulla radice di una catena) riattribuiscono e AVVISANO tutti i
successori (`_ricomponi_successori` `:435`). `dimentica_mercato` (`:663`) toglie i legami (`_slega` `:655`), anche
degli ordini riassunti.

**Test** (`test_c2_revisione3.py`, 33 nuovi, righe e ordini nella grafia vera: corpo vero dell'INSERT/UPDATE della
coda dal client supabase vero, `_result` veri del worker calcio e tennis, ordini flumine veri creati da
`live_order_build._create_order` e rimpiazzi da `Trade.create_order_replacement`, righe specchio da
`LiveTradingStrategy._order_row` e `tennis_live_order_worker.riga_specchio`):
- replace di un ordine dell'UTENTE: il nuovo e' `desktop` con comandi `annulla`/`sposta`
  (`test_replace_dell_utente_dallo_specchio_il_nuovo_e_desktop_e_comandabile`, `..._nel_libro_il_nuovo_eredita`);
- replace di un ordine di OMEGA (riga di coda di Omega `omega-t9`, spostato dall'utente): il nuovo e' `omega`, senza
  comandi (`test_replace_di_un_ordine_di_omega_il_nuovo_e_omega`); Omega che riprezza da solo
  (`test_omega_riprezza_da_solo_la_sua_tabella_e_prova_del_nuovo`);
- replace di un PROVVISORIO: resta provvisorio e senza comandi; quando arriva la prova sul sostituito il nuovo la segue
  (`test_replace_di_un_provvisorio_resta_provvisorio`);
- CATENA di due replace: specchio (`awlq40` sopravvive a due rimpiazzi), libro (prova sulla radice -> tutti e tre
  `desktop`, avvisati tutti), dopo un RIAVVIO con solo l'ultimo ordine vivo, ciclo senza fine fermato;
- tennis (`test_tennis_replace_dell_utente_legame_dalla_coda_e_dallo_specchio`, `test_tennis_un_cancel_non_lega`);
  stream (7 test: legame, completo tardivo, ref/lato/selezione diversi, verso dal bet_id, bet_id non numerici,
  messaggio rifiutato); tetto e dimenticanza (4 test); paper (l'attore dichiarato non cambia).
I 33 test nuovi sul codice di `3ceac891` (i due moduli di allora rimessi al loro posto e poi ripristinati, sha256 ricontrollato): **33 rossi** (le funzioni del legame non esistono: nessuna eredita'). Uscita: `scratchpad/w1c2/rossi_rev3_su_vecchio.txt`.

**Falsificazione**: 39 mutazioni nuove nello script (M116-M154, una per ramo), fra cui **M116 «il nuovo non eredita»**
(`a = attr.eredita(...)` -> `pass`): ROSSA. Al primo giro M149 (ciclo senza guardia nella risalita) sopravviveva:
aggiunto il ciclo di tre legami scritti prima dell'arrivo dell'ordine, ora rossa. Giro completo (175 mutazioni): al primo giro 174/174 rosse e 1 guasto, M109 (la sua stringa non c'era piu': `dimentica_mercato` ora slega i bet_id riassunti; adeguata a `_riassunti_bet.get` al posto di `.pop`); giro completo ripetuto: **TOTALE rosse 175/175 (guasti 0)**, uscita in
`ARCHITETTURA_2026-10/ondata1/W1-C2/mutazioni_esito.txt`. sha256 dopo ogni ripristino = file di `d1430036`:
`attribuzione.py` 469a20c30c2cd9fe86b743b0d8031f1540509789dae466e867427bcafb87f858,
`libro_conto.py` 74a081169de75f017ff0d9254c47ba01a2077bccbe9a20ab480ef0867b3a940c (`pnl_mercato.py` e
`riconciliazione.py` invariati). Test W1-C2: **265 verdi**. Suite intera (una volta, alla fine): **11.836 verdi, 0 rossi, 87 saltati, 6 xfailed** (360 s).

**Aggancio aggiornato (ondata 2): il legame dopo un riavvio si RILEGGE dalle righe** (in aggiunta alla riconferma
all'avvio del par. 11; stesse regole: fuori dal percorso degli ordini, a blocchi di 100, lettura fallita = si ritenta,
nel frattempo l'ordine resta provvisorio):
- calcio: per ogni ordine live provvisorio, la riga di `betfair_live_orders` col suo `bet_id` (colonne `bet_id,
  client_order_ref, request_id`); se ha un'origine (`origine_della_riga_specchio`), la richiesta d'origine in
  `betfair_live_order_requests` per `id=in.(...)` OPPURE `client_ref=in.(local<id>,...)`; poi
  `LibroConto.aggiungi_indizi(bet_id, indizi_da_origine(riga_specchio, riga_coda))`. Copre il piazzato e ogni suo
  rimpiazzo, in catena, senza bisogno del sostituito;
- tennis: le righe `tennis_live_order_queue` con `payload->>action=replace` del giorno e la riga `tennis_live_orders`
  con `client_order_ref` = `result->>customer_order_ref`: `lega_sostituzione(*legame_da_replace_tennis(...))`; per il
  sostituito la riga di coda che lo ha piazzato (par. 11, `indizi_da_riga_tennis`) -> `aggiungi_indizi(vecchio, ...)`;
  il nuovo eredita anche se il sostituito, annullato, non torna dal conto;
- bot: le tabelle col bet_id nuovo come oggi (`indizio_da_riga_bot`);
- in esercizio (non solo all'avvio) gli stessi agganci all'arrivo della riga (canale locale o Realtime), piu' lo stream
  (d) in ombra.

D11 resta per l'utente (par. 11). D9 resta.
